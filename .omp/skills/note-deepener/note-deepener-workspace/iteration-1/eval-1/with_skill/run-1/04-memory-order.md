# Memory Order 在无锁队列中的应用

> 基于笔记: drafts/test-lockfree-queue.md
> 所属教程: Lockfree Queue 深度分析
> 章: 4/6

---

> **前置知识**：本章假设你已理解 `memory_order_relaxed`、`acquire`、`release` 的基础语义。如需回顾，请先阅读 [`docs/deep-dives/cpp-memory-order-game-engine.md`](../../../../docs/deep-dives/cpp-memory-order-game-engine.md)，其中覆盖了六种 memory_order 的定义、happens-before 关系、以及编译器/CPU 重排序的底层原理。

本章聚焦**queue 特有的内存序模式**——和 stack（Treiber Stack）相比，queue 的同步需求不同，因此内存序的选择也不同。

## 1. 为什么 SPSC Queue 需要 acquire/release？

回顾第 1 章的 V1 实现——全部使用 `memory_order_relaxed`。它在 x86 上**碰巧**工作，因为 x86 的硬件内存模型提供了 acquire-release 语义（TSO）。但在 ARM/PowerPC 等弱内存序架构上，relaxed 版本会出 bug。

**问题的本质**：生产者和消费者之间存在**生产者先写 buffer 再更新 tail，消费者先读 tail 再读 buffer 的数据流**。如果这两种操作的顺序被 CPU 或编译器重排，消费者就会读到未初始化的数据。

### 具体场景：生产者端的 release

```cpp
// 生产者线程
buffer_[tail] = item;    // (1) 写数据到 buffer
tail_.store(t + 1, ?);   // (2) 通知消费者
```

**我们需要保证**：(1) 必须在 (2) 之前对消费者可见。即：消费者看到新 `tail` 时，必须同时看到 `buffer_[tail]` 的新值。

如果 (1) 和 (2) 被重排（先更新 tail，后写 buffer），消费者会看到 `tail` 推进了，但 `buffer` 还是旧值 → 读到脏数据。

```cpp
// 修正：用 release 保护
buffer_[tail] = item;                           // (1) 非原子写
tail_.store(t + 1, std::memory_order_release);  // (2) release store
```

`release` 保证：(1) 和所有在它之前的内存操作**不会被重排到 (2) 之后**。

### 具体场景：消费者端的 acquire

```cpp
// 消费者线程
size_t t = tail_.load(?);    // (3) 读取 tail
item = buffer_[head];         // (4) 读取 buffer 数据
```

**我们需要保证**：(4) 必须在读到 (3) 对应版本的数据之后执行（确切地说，(4) 不能读到比 (3) 更旧的数据）。

```cpp
// 修正：用 acquire 保护
size_t t = tail_.load(std::memory_order_acquire);  // (3) acquire load
item = buffer_[head];                               // (4) 读取数据
```

`acquire` 保证：(4) 和所有在它之后的内存操作**不会被重排到 (3) 之前**。

### synchronize-with 配对

当消费者通过 acquire load 读到了生产者通过 release store 写入的值时：

```
生产者:  buffer_[t] = item  ──(sequenced-before)──→  tail_.store(t+1, release)
                                                            │
                                              (synchronize-with if consumer reads t+1)
                                                            │
消费者:  tail_.load(acquire)  ──(sequenced-before)──→  item = buffer_[h]
```

此时，生产者写入 `buffer_[t]` 的副作用**happens-before** 消费者读取 `buffer_[h]` → 消费者保证看到正确的数据。

> [来源] C++11 standard §29.3; 也参见 preshing.com, "The Synchronizes-With Relation"

## 2. 完整 SPSC 实现（正确内存序）

```cpp
#include <atomic>
#include <cstddef>
#include <type_traits>

template<typename T, size_t SIZE>
class SPSCQueue {
    static_assert((SIZE >= 2) && ((SIZE & (SIZE - 1)) == 0),
                  "SIZE must be a power of 2 and >= 2");
    static_assert(std::is_trivially_copyable_v<T>,
                  "T must be trivially copyable for memcpy-like access");

    T buffer_[SIZE];

    // head 和 tail 使用独立 cache line 避免 false sharing
    alignas(64) std::atomic<size_t> head_{0};  // 消费者
    alignas(64) std::atomic<size_t> tail_{0};  // 生产者

    const size_t mask_ = SIZE - 1;

public:
    SPSCQueue() = default;
    SPSCQueue(const SPSCQueue&) = delete;
    SPSCQueue& operator=(const SPSCQueue&) = delete;

    // ========================================
    // 生产者接口 — 仅在单生产者线程调用
    // ========================================

    // 尝试入队，满时返回 false（非阻塞）
    bool try_push(const T& item) {
        // relaxed: 生产者不和其他生产者竞争 tail
        // head 用 acquire: 看到消费者最新的 head，保证读到消费者已经读取的 slot
        size_t t = tail_.load(std::memory_order_relaxed);
        size_t h = head_.load(std::memory_order_acquire);

        // Full check
        if ((t - h) >= SIZE - 1) {
            return false;
        }

        // 写入数据到 buffer（非原子操作）
        buffer_[t & mask_] = item;

        // release: 保证 buffer 写入在 tail 更新之前对所有线程可见
        // 消费者通过 acquire 读 tail 时能看到完整的 buffer 内容
        tail_.store(t + 1, std::memory_order_release);
        return true;
    }

    // ========================================
    // 消费者接口 — 仅在单消费者线程调用
    // ========================================

    // 尝试出队，空时返回 false（非阻塞）
    bool try_pop(T& item) {
        // relaxed: 消费者不和其他消费者竞争 head
        // tail 用 acquire: 看到生产者最新的 tail，保证能看到已写入的 buffer 内容
        size_t h = head_.load(std::memory_order_relaxed);
        size_t t = tail_.load(std::memory_order_acquire);

        // Empty check
        if (h == t) {
            return false;
        }

        // 读取数据
        item = buffer_[h & mask_];

        // release: 保证 buffer 读取在 head 更新之前完成
        // 生产者通过 acquire 读 head 时能看到 slot 已释放
        head_.store(h + 1, std::memory_order_release);
        return true;
    }

    // 获取当前积压量（近似值，调试用）
    size_t size_approx() const {
        size_t h = head_.load(std::memory_order_relaxed);
        size_t t = tail_.load(std::memory_order_relaxed);
        return t - h;
    }
};
```

### 内存序选择注解

| 操作 | 内存序 | 为什么选择这个 |
|------|--------|---------------|
| 生产者读 `tail_` | `memory_order_relaxed` | 没有其他生产者竞争，且 `tail_` 是本线程写-本线程读的结构。只需要看到本线程最新写的值 |
| 生产者读 `head_` | `memory_order_acquire` | 需要看到消费者释放的 head 更新，以及在该更新之前消费者已完成的 buffer 读取。这保证该 slot 已被消费者读完，可以安全覆盖 |
| 生产者写 `buffer_[t]` | 非原子 | 此时该 slot 已经被"预订"（生产者拿到了唯一的 tail 位置），消费者不会碰它 |
| 生产者写 `tail_` | `memory_order_release` | 保证 buffer 写入发生在 tail 更新之前。消费者通过 acquire 读 tail 来触发 synchronize-with |
| 消费者读 `head_` | `memory_order_relaxed` | 没有其他消费者竞争 |
| 消费者读 `tail_` | `memory_order_acquire` | 需要看到生产者释放的 tail 更新，触发 synchronize-with，进而看到对应的 buffer 内容 |
| 消费者读 `buffer_[h]` | 非原子 | synchronize-with 已经保证了可见性 |
| 消费者写 `head_` | `memory_order_release` | 保证 buffer 读取在 head 更新前完成，生产者通过 acquire 读 head 得知 slot 可重用 |

## 3. SPSC vs Treiber Stack 的内存序差异

在 `docs/deep-dives/cpp-memory-order-game-engine.md` 中分析的 Treiber Stack，push 操作用 `compare_exchange_weak` 更新 `head_`：

```cpp
// Treiber Stack push (回顾)
newNode->next = head_.load(acquire);
while (!head_.compare_exchange_weak(newNode->next, newNode, release, acquire)) {}
```

这里用 `release` 作为 success order 是因为 CAS 修改的是 head——所有消费者通过 head 找到节点。release 保证 newNode 的构造在 head 更新前完成。

**SPSC queue 不需要 CAS 的原因**：queue 的两个指针各有一个 owner，而 stack 的 head 被所有生产者/消费者共享修改。这就是为什么 structure 的选择直接影响同步复杂度。

## 4. 为什么 head 的 load 用 acquire 而不是 relaxed？

一个常被讨论的微优化：生产者读 head 只是为了判断队列是否满——它不需要看到 buffer 的内容（buffer 是消费者读的，生产者只管写）。那为什么还要用 `acquire`？

**答案**：为了知道 slot 可写。当 head 推进时，意味着消费者已经完成了对该 slot 的读取。如果生产者使用 relaxed 读 head，它可能看到旧的 head 值（slot 实际上已释放但不可见），导致队列"假满"——浪费容量。

**但是**：如果你能接受偶尔的假满（队列容量大，多等一次重试无妨），生产者读 head 可以降级为 `relaxed`——这是一个合法的性能取舍：

```cpp
// 更激进的优化版本
bool try_push_fast(const T& item) {
    size_t t = tail_.load(std::memory_order_relaxed);
    // relaxed: 可能假满，但不会假空（因为 head 不会回退）
    size_t h = head_.load(std::memory_order_relaxed);

    if ((t - h) >= SIZE - 1) {
        return false;
    }

    buffer_[t & mask_] = item;
    tail_.store(t + 1, std::memory_order_release);
    return true;
}
```

> 这个优化的安全性前提：head 是单调递增的（从不减小）。你看到的旧 head 总是**小于或等于**真实的 head，所以满的判断最多是假阳性（假满），不会是假阴性（假空导致覆盖未消费数据）。

## 5. 完整的内存序表（SPSC + MPMC 对比）

| 数据结构 | 操作 | 变量 | 访问类型 | 内存序 | 理由 |
|---------|------|------|---------|--------|------|
| SPSC push | 读 head | head_ | 单读 | acquire (或 relaxed*) | 确认 slot 可写 |
| SPSC push | 读 tail | tail_ | 单读单写 | relaxed | 无竞争 |
| SPSC push | 写 tail | tail_ | 单写 | release | 消费者同步点 |
| SPSC pop | 读 tail | tail_ | 单读 | acquire | 生产者同步点 |
| SPSC pop | 读 head | head_ | 单读单写 | relaxed | 无竞争 |
| SPSC pop | 写 head | head_ | 单写 | release | 生产者同步点 |
| MPMC enqueue | CAS enq | enqueue_pos | CAS | relaxed | slot 预订，同步由 sequence 负责 |
| MPMC enqueue | 读 seq | slot.sequence | 单读 | acquire | 等候 slot 就绪 |
| MPMC enqueue | 写 seq | slot.sequence | 单写 | release | 通知消费者 |
| MPMC dequeue | CAS deq | dequeue_pos | CAS | relaxed | slot 认领 |
| MPMC dequeue | 读 seq | slot.sequence | 单读 | acquire | 等候数据就绪 |
| MPMC dequeue | 写 seq | slot.sequence | 单写 | release | 通知生产者 |

## 6. 测试内存序错误的技巧

在 x86 上，由于 TSO（Total Store Order），内存序错误通常不会暴露。验证正确性需要：

1. **使用 ThreadSanitizer (TSan)**：
   ```bash
   g++ -fsanitize=thread -O2 -g test_spsc.cpp -o test_spsc
   ./test_spsc
   ```
   TSan 不依赖硬件内存模型，它从 C++ 抽象机层面检测 happens-before 关系的缺失。

2. **在 ARM 设备上测试**（如树莓派、Apple Silicon）——弱内存序会暴露 acquire/release 缺失。

3. **使用 `rr` (Record and Replay)** + chaos mode 来复现罕见的调度交错。

---

*上一章: [MPMC 多生产者多消费者队列](03-mpmc-queue.md)* | *下一章: [Disruptor 模式对比](05-disruptor-comparison.md)*
