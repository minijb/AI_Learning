# MPMC 多生产者多消费者队列

> 基于笔记: drafts/test-lockfree-queue.md
> 所属教程: Lockfree Queue 深度分析
> 章: 3/6

---

## 1. SPSC vs MPMC：为什么 MPMC 难得多

在 SPSC 队列中，我们有一个关键的不变量：

> **每个指针只有一个写入者**

| 指针 | 写入者 | 读取者 |
|------|--------|--------|
| `head` | 消费者（唯一） | 生产者（唯一） |
| `tail` | 生产者（唯一） | 消费者（唯一） |

这保证了写入指针不需要 CAS——因为不存在竞争。你只需要 atomic load 读到对方的最新值，atomic store 写入自己的新值。

MPMC 打破了这个不变量：

| 指针 | 写入者 | 读取者 |
|------|--------|--------|
| `head` | **多个消费者** | **多个生产者** |
| `tail` | **多个生产者** | **多个消费者** |

现在，两个生产者同时调用 `push()`，它们都需要更新 `tail` —— 竞争产生了。你不能简单地 `tail_.store(t + 1)`，因为这会导致**丢失更新（lost update）**：

```
时间轴: 生产者A 读 tail=0, 生产者B 也读 tail=0
        生产者A store tail=1
        生产者B store tail=1  ← B 的写入覆盖了 A！
        结果：只有 B 的 item 被记录，A 的 item 写入 slot 0 但被永远忽略
```

## 2. 解决方案：CAS 循环

生产者**不能**直接 store，而必须**原子地** "如果 tail 还是 t，就设置为 t+1"——这正是 `compare_exchange` 做的事情：

```cpp
// 错误（MPMC 中）：
tail_.store(t + 1);  // ← 可能与另一个生产者的 store 竞争

// 正确（MPMC）：
// 只有 tail 没被其他线程改过，才推进
tail_.compare_exchange_weak(t, t + 1);
```

但这还不够——因为如果 CAS 成功了，该生产者获得了 slot `t` 的**独占写入权**，但**写入 buffer[t] 必须发生在 CAS 之前还是之后**？

**答案**：CAS 之后。因为 CAS 只是"预订"了一个 slot。在你 CAS 成功之前，你不应该写入 buffer——其他生产者也可能在等待同一个 slot。

但这就带来了新的问题：

```cpp
// 生产者 A 和 B 竞争 slot 0:
// A: reads tail=0, B: reads tail=0
// A: CAS tail from 0 to 1 → 成功！A 获得 slot 0
// B: CAS tail from 0 to 1 → 失败！tail 已变成 1
// B: 重试，reads tail=1, CAS from 1 to 2 → 成功！B 获得 slot 1

// 现在 A 写入 buffer[0]，B 写入 buffer[1]
// 问题：如果 A 的 buffer 写入比 B 慢，消费者能否仍然正确？
```

## 3. 关键同步问题：多生产者的"写后通知"顺序

当一个生产者写入 `buffer[slot]` 后，消费者怎么知道 slot 已经就绪？

SPSC 中，消费者只看 `tail`——因为只有一个生产者，`tail` 的推进和 buffer 的写入是同一线程顺序保证的。

MPMC 中，多个生产者各自写入 buffer，但只有一个 `tail`。如果 producer A 获得 slot 0 但写入较慢，而 producer B 获得 slot 1 且写入很快——tail 已经被 CAS 推到了 2。消费者看到 `tail=2`，以为 slot 0 和 slot 1 都就绪了，但 slot 0 可能还没写完！

**这就是 MPMC 的核心挑战：生产者的写入完成顺序 ≠ CAS 获得 slot 的顺序。**

### 解决：per-slot 写入标志

每个 slot 额外维护一个 `sequence` 标志（或 `write_complete` 标志），生产者写入完毕后设置，消费者在读取前检查：

```cpp
struct Slot {
    std::atomic<uint64_t> sequence;  // 写入完成标志
    T data;
};

template<typename T, size_t SIZE>
class MPMCQueue {
    Slot buffer_[SIZE];
    std::atomic<size_t> head_{0};
    std::atomic<size_t> tail_{0};

public:
    MPMCQueue() {
        for (size_t i = 0; i < SIZE; ++i) {
            buffer_[i].sequence.store(i, std::memory_order_relaxed);
        }
    }
};
```

sequence 的初始化值等于 slot 索引——这允许我们编码"这个 slot 准备好被第 N 轮写入"：

- 当 `sequence == slot_index`：slot 空闲，生产者可以写入
- 当 `sequence == slot_index + 1`：slot 已写入完成，消费者可以读取
- 当 `sequence == slot_index + SIZE`：slot 已被消费者读取完毕，可以再次写入

这就是 **Dmitry Vyukov 的 Bounded MPMC Queue** 设计。

> [来源] Dmitry Vyukov, [1024cores.net - Bounded MPMC Queue](http://www.1024cores.net/home/lock-free-algorithms/queues/bounded-mpmc-queue)

## 4. 完整 C++ 实现：Vyukov 风格 Bounded MPMC Queue

```cpp
#include <atomic>
#include <cstddef>
#include <memory>
#include <new>

template<typename T, size_t SIZE>
class MPMCBoundedQueue {
    static_assert((SIZE >= 2) && ((SIZE & (SIZE - 1)) == 0),
                  "SIZE must be a power of 2 and >= 2");

    struct Cell {
        std::atomic<size_t> sequence;
        T data;
    };

    Cell* buffer_;  // 动态分配以保证对齐
    const size_t buffer_mask_;
    alignas(CACHE_LINE_SIZE) std::atomic<size_t> enqueue_pos_{0};
    alignas(CACHE_LINE_SIZE) std::atomic<size_t> dequeue_pos_{0};

    static constexpr size_t CACHE_LINE_SIZE = 64;

public:
    MPMCBoundedQueue()
        : buffer_mask_(SIZE - 1)
    {
        // 使用 aligned_alloc 保证对齐，避免 false sharing
        buffer_ = static_cast<Cell*>(
            std::aligned_alloc(CACHE_LINE_SIZE, sizeof(Cell) * SIZE)
        );

        for (size_t i = 0; i < SIZE; ++i) {
            // sequence = i 表示"第 0 轮写入可以占据 slot i"
            buffer_[i].sequence.store(i, std::memory_order_relaxed);
        }
    }

    ~MPMCBoundedQueue() {
        std::free(buffer_);
    }

    // 禁止拷贝（atomic 成员不可拷贝）
    MPMCBoundedQueue(const MPMCBoundedQueue&) = delete;
    MPMCBoundedQueue& operator=(const MPMCBoundedQueue&) = delete;

    // ========== 生产者（多线程安全）==========
    bool enqueue(const T& data) {
        Cell* cell;
        size_t pos = enqueue_pos_.load(std::memory_order_relaxed);

        for (;;) {
            cell = &buffer_[pos & buffer_mask_];
            size_t seq = cell->sequence.load(std::memory_order_acquire);

            // seq == pos: slot 准备好被第 N 轮写入
            intptr_t diff = static_cast<intptr_t>(seq) - static_cast<intptr_t>(pos);

            if (diff == 0) {
                // 尝试"预订"这个 slot
                if (enqueue_pos_.compare_exchange_weak(
                        pos, pos + 1,
                        std::memory_order_relaxed,
                        std::memory_order_relaxed))
                {
                    // 成功了！可以安全写入
                    break;
                }
                // CAS 失败，pos 已被更新为最新值，继续循环
            } else if (diff < 0) {
                // 队列满了（seq < pos 表示第 N-1 轮的数据还没被消费）
                return false;
            } else {
                // 其他生产者已经推进了 enqueue_pos，更新 pos
                pos = enqueue_pos_.load(std::memory_order_relaxed);
            }
        }

        // 写入数据
        cell->data = data;

        // 标记写入完成：sequence = pos + 1
        // release 保证 data 的写入对所有线程可见
        cell->sequence.store(pos + 1, std::memory_order_release);

        return true;
    }

    // ========== 消费者（多线程安全）==========
    bool dequeue(T& data) {
        Cell* cell;
        size_t pos = dequeue_pos_.load(std::memory_order_relaxed);

        for (;;) {
            cell = &buffer_[pos & buffer_mask_];
            size_t seq = cell->sequence.load(std::memory_order_acquire);

            // seq == pos + 1: slot 已写入完成，可以消费
            intptr_t diff = static_cast<intptr_t>(seq)
                          - static_cast<intptr_t>(pos + 1);

            if (diff == 0) {
                // 尝试"认领"这个 slot
                if (dequeue_pos_.compare_exchange_weak(
                        pos, pos + 1,
                        std::memory_order_relaxed,
                        std::memory_order_relaxed))
                {
                    // 成功了！可以安全读取
                    break;
                }
            } else if (diff < 0) {
                // 队列空了
                return false;
            } else {
                // 其他消费者已经推进了 dequeue_pos
                pos = dequeue_pos_.load(std::memory_order_relaxed);
            }
        }

        // 读取数据
        data = cell->data;

        // 标记读取完成：sequence = pos + SIZE
        // release 确保 data 的读取在 sequence 更新前完成
        cell->sequence.store(pos + buffer_mask_ + 1, std::memory_order_release);

        return true;
    }
};
```

> [来源] 实现参考 Dmitry Vyukov 的 bounded MPMC queue 算法，`[推测]` 原算法发表于 1024cores.net 及 Intel TBB 的 `concurrent_bounded_queue`

## 5. 为什么 `enqueue_pos` 和 `dequeue_pos` 使用 `alignas(CACHE_LINE_SIZE)`？

这解决的是 **false sharing（伪共享）** 问题：

```
未对齐的布局：
+------------------+------------------+
| enqueue_pos (8B) | dequeue_pos (8B) |
+------------------+------------------+
        ← 同一个 64B cache line →

生产者写 enqueue_pos → 该 cache line 被标记为 modified（core 1）
消费者读 dequeue_pos → cache line 被 invalidate（core 2）
虽然它们访问的是不同变量，但因为在同一 cache line，每次写入都强制另一个 core 重新从内存加载。
```

`alignas(64)` 强制每个变量独占一个 cache line：

```
对齐后的布局：
+------------------+--padding 56B--+------------------+--padding 56B--+
| enqueue_pos (8B) |    unused     | dequeue_pos (8B) |    unused     |
+------------------+---------------+------------------+---------------+
    cache line 1                     cache line 2

生产者写 cache line 1 → 不影响消费者读 cache line 2
```

> [来源] Herb Sutter, "Eliminate False Sharing", Dr. Dobb's Journal, 2009

## 6. SPSC vs MPMC 性能对比

| 维度 | SPSC | MPMC |
|------|------|------|
| Push 的原子操作 | 1 load + 1 store | 1 load + CAS loop (+1 store on success) |
| Pop 的原子操作 | 1 load + 1 store | 1 load + CAS loop (+1 store on success) |
| 竞争概率 | 0（唯一写入者） | 生产者之间、消费者之间分别竞争 |
| Cache 一致性流量 | 2 cache line 传递/操作 | 每个 CAS 失败产生额外 coherence 流量 |
| 每个 slot 额外开销 | 0 | 8 bytes（sequence） |
| 适用场景 | 1P1C | NP MC |

**数量级差异**（基于公开 benchmark，x86-64）：

| 操作 | SPSC | MPMC | 比率 |
|------|------|------|------|
| Push（无竞争） | ~10 ns | ~25 ns | 2.5x |
| Push（2P 竞争） | — | ~80 ns | — |
| Pop（无竞争） | ~10 ns | ~25 ns | 2.5x |
| Pop（2C 竞争） | — | ~80 ns | — |

> 数据来源 `[推测]` — 基于典型 x86-64 上的 folly::ProducerConsumerQueue 与 MoodyCamel 的 ConcurrentQueue 的相对表现。精确值取决于 CPU 型号、缓存状态和负载模式。

## 7. 你的游戏引擎用哪种？

```
你需要多生产者吗？
├── 不需要（只有主线程生产）
│   → SPSC。总是 SPSC。没有理由用 MPMC。
│
└── 需要（多个工作线程可能竞争提交任务）
    └── 你需要多消费者吗？
        ├── 不需要 → MPSC。更简单、更快。
        │   注意：很多"MPMC"场景实际上是 MPSC！
        │   渲染线程收集所有工作线程的结果 → 工作线程生产，渲染线程消费 → MPSC
        │
        └── 需要 → MPMC。接受 2-8x 的性能代价。
            但先问自己：能不能每个消费者分配独立的 SPSC？
```

**关键洞察**：大多数游戏引擎场景中，所谓的"MPMC"实际可以通过设计消除：

- 为每个消费者分配独立的 SPSC（工作分发）
- 使用 MPSC 收集结果（工作完成通知）
- 只在确实需要动态工作窃取时才用 MPMC

---

*上一章: [CPU 自旋优化策略](02-spin-optimization.md)* | *下一章: [Memory Order 在无锁队列中的应用](04-memory-order.md)*
