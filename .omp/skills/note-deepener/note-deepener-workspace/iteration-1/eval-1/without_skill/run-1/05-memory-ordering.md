# 第 5 章：Q3 — memory_order_acquire/release 怎么用？

## 问题回顾

笔记中的伪代码没有任何内存序控制：

```
buffer[tail] = item       // 写数据
tail = (tail + 1) % SIZE  // 更新索引
```

在多核 CPU 上，其他核心可能**先看到 tail 更新，后看到 buffer 写入** — 读到未初始化的垃圾数据。

## 为什么 CPU 会重排指令？

两个原因：

1. **编译器重排**：优化器可能将不相关的 store/load 重新排序以减少寄存器溢出或改善指令调度。
2. **CPU 重排**：Store Buffer、Load Buffer、Cache 一致性协议（MESI）都可能让不同核心看到的写入顺序不一致。

C++ 内存模型用 `std::memory_order` 控制这两种重排。

## 六种内存序

（引自 [cppreference.com — std::memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)）

| 内存序 | 含义 | 典型用途 |
|--------|------|---------|
| `relaxed` | 无排序约束，仅保证原子性 | 递增计数器 |
| `consume` | load: 后续依赖该值的操作不可前移 | 已弃用（C++26），不推荐 |
| `acquire` | load: 后续读写不可重排到此 load 之前 | **消费者读索引** |
| `release` | store: 之前的读写不可重排到此 store 之后 | **生产者写索引** |
| `acq_rel` | RMW 操作：同时具有 acquire 和 release | CAS 循环中的 RMW |
| `seq_cst` | 全局顺序一致性（默认，最强） | 需要全局顺序时 |

## SPSC 的核心同步模式

### 生产者视角

```cpp
// Producer: enqueue
buffer_[tail & mask_] = item;                              // (1) 写数据
tail_.store(tail + 1, std::memory_order_release);          // (2) 发布
```

`release` 确保：(1) 发生在 (2) 之前 — 无论在编译器层面还是 CPU 层面。消费者看到 `tail` 更新时，保证 `buffer_[tail_old & mask_]` 的数据已写入。

### 消费者视角

```cpp
// Consumer: dequeue
size_t tail = tail_.load(std::memory_order_acquire);       // (3) 获取
item = buffer_[head & mask_];                              // (4) 读数据
```

`acquire` 确保：(3) 发生在 (4) 之前。消费者读到最新的 `tail` 后，后续对 `buffer_` 的读取能正确看到生产者写入的数据。

### 同步配对

```
Producer:               Consumer:
  write buffer_[i]  ──┐
  tail.store(release)  │  happens-before ──→  tail.load(acquire)
                       └────────────────→    read buffer_[i]
```

当消费者的 `acquire` load **读取到** 生产者的 `release` store 写入的值时，这两个操作之间形成 **synchronizes-with** 关系 — C++ 标准保证生产者在 `release` 之前的所有写入，对消费者在 `acquire` 之后的所有读取可见。

## 完整的 SPSC 内存序标注

```cpp
template <typename T>
class SPSCQueue {
    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    alignas(64) std::vector<T> buffer_;
    size_t mask_;

public:
    bool enqueue(const T& item) {
        // relaxed: 读自己的 tail — 只有本线程会写它，无需同步
        size_t tail = tail_.load(std::memory_order_relaxed);
        // acquire: 读对方的 head — 需要看到消费者释放的 slot
        size_t head = head_.load(std::memory_order_acquire);

        if ((tail - head) > mask_) return false;

        buffer_[tail & mask_] = item;

        // release: 确保 buffer_ 写入对消费者可见
        tail_.store(tail + 1, std::memory_order_release);
        return true;
    }

    bool dequeue(T& item) {
        // relaxed: 读自己的 head
        size_t head = head_.load(std::memory_order_relaxed);
        // acquire: 读对方的 tail — 需要看到生产者写入的数据
        size_t tail = tail_.load(std::memory_order_acquire);

        if (head == tail) return false;

        item = buffer_[head & mask_];

        // release: 确保读取完成后再释放 slot
        head_.store(head + 1, std::memory_order_release);
        return true;
    }
};
```

### 为什么读"自己的"索引用 relaxed？

- 生产者只写 `tail_`、只读 `tail_` → 单线程访问，不存在竞争。
- 消费者只写 `head_`、只读 `head_` → 同理。
- 读自己的索引不需要任何同步，`relaxed` 足够且更高效。

### 为什么读"对方的"索引用 acquire？

- 生产者读 `head_`（消费者写的）→ 需要 acquire 来看到消费者在 `release` 之前的写入。
- 消费者读 `tail_`（生产者写的）→ 需要 acquire 来看到生产者在 `release` 之前写入 `buffer_` 的数据。

## MPMC 的内存序模式

MPMC 更复杂，因为多个线程并发修改 `enqueue_pos_` 和 `dequeue_pos_`。Vyukov 算法的技巧是将同步责任从 `pos` 原子变量转移到**每个 slot 的 sequence 号**：

```cpp
// Enqueue 中 CAS 预约 slot 用 relaxed：
enqueue_pos_.compare_exchange_weak(pos, pos + 1,
                                   std::memory_order_relaxed);
// 实际的 happens-before 由 cell->sequence 提供：
cell->sequence.load(std::memory_order_acquire);   // 等 slot 空闲
// ... 写入数据 ...
cell->sequence.store(pos + 1, std::memory_order_release);  // 发布
```

`enqueue_pos_` 的 CAS 仅是"抢号"机制，不承载数据同步语义。数据同步完全靠每个 slot 的 `sequence` 字段的 acquire/release 配对。

## 常见误区

### 误区 1：全部用 `seq_cst` 就安全了

`seq_cst` 确实最安全，也是 C++ atomics 的默认值。但它：
- 在 x86 上会插入不必要的 `MFENCE` 指令（或阻止编译器重排）
- 在 ARM 上每条 `seq_cst` 操作约贵 2–3 倍于 `acq_rel`

无锁数据结构的设计价值之一就是**精确控制同步范围**。滥用 `seq_cst` ≈ 关掉优化。

### 误区 2：x86 不会重排所以不需要内存序

x86 的 TSO (Total Store Order) 模型中，普通 load 自带 acquire 语义，普通 store 自带 release 语义。但：

- **编译器仍可能重排** — 内存序同时约束编译器。
- **代码可能运行在 ARM 上**（Apple Silicon、手机、游戏主机 Switch）。
- Store-Load 重排在 x86 上仍然可能发生。

### 误区 3：`volatile` 等价于 `atomic`

`volatile` 不提供：
- 原子性（多线程读写非对齐类型是 UB）
- 内存序保证
- happens-before 关系

在 C++11 之后，多线程同步应始终使用 `std::atomic`。

## 验证工具

无锁代码的正确性很难靠 Code Review 保证。推荐工具：

- **ThreadSanitizer (TSan)**：`-fsanitize=thread` 检测数据竞争。
- **relacy**（Dmitriy V'jukov）：C++ 内存模型的详尽模拟器，可重现所有合法的交错执行。
- **CDSChecker**：学术界的 C++ 内存模型模型检查器。

---

*上一章：[04-spsc-vs-mpmc.md](./04-spsc-vs-mpmc.md)*
*下一章：[06-disruptor-comparison.md](./06-disruptor-comparison.md) — Q4: 和 Disruptor 模式比谁更快？*
