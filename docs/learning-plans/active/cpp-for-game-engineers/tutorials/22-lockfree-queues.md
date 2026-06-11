---
title: "Lock-Free 队列实现"
updated: 2026-06-05
---

# Lock-Free 队列实现

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 5h
> 前置知识: 20-原子操作与C++内存序精讲, 21-引擎中的多线程架构

---

## 1. 概念讲解

### 1.1 Lock-Free vs Wait-Free：精确区分

这两个术语经常被混用，但它们在 C++ 内存模型中有精确定义（[intro.progress]）：

| 属性 | 定义 | 引擎意义 |
|------|------|---------|
| **Lock-Free** | 在任何时刻，**至少有一个**线程能在有限步内完成操作 | 整体系统前进，但个别线程可能永远饥饿 |
| **Wait-Free** | **所有**线程都能在有限步内完成操作 | 每个线程都有硬延迟保证，无饥饿 |
| **Obstruction-Free** | 单个线程在无竞争时能在有限步内完成 | 最弱，很少在引擎中单独使用 |

**在 16.6ms 帧预算下**：Lock-Free 通常是足够的——我们关心中位数延迟，不要求每个线程有绝对上界。Wait-Free 主要用于**音频线程**（绝不能有弹出/爆音）和**渲染 vsync 路径**。

### 1.2 为什么不用 `std::mutex` 队列？

```cpp
// 标准做法：std::mutex + std::queue
template<typename T>
class MutexQueue {
    std::queue<T> queue_;
    std::mutex mtx_;

public:
    void push(T val) {
        std::lock_guard lk(mtx_);  // 可能进入内核态
        queue_.push(std::move(val));
    }
    bool pop(T& val) {
        std::lock_guard lk(mtx_);
        if (queue_.empty()) return false;
        val = std::move(queue_.front());
        queue_.pop();
        return true;
    }
};
```

**问题**：
1. **内核态开销**：竞争时 `futex_wait` 系统调用——数十微秒延迟
2. **优先级反转**：低优先级线程持有锁 → 高优先级渲染线程阻塞
3. **无法在信号处理器/中断上下文中使用**：`mutex::lock` 不可重入
4. **队列操作触发堆分配**：`queue_.push()` 可能分配新节点，违反帧内零分配约束

**Lock-Free 队列的优势**：
- **固定内存**：环形缓冲区预分配，永不触发 `malloc`
- **无系统调用**：`compare_exchange` 在用户态自旋
- **可预测延迟**：最坏情况是 CAS 失败重试，而非内核调度
- **信号安全**：可在中断/信号处理器中安全使用

### 1.3 SPSC 队列：最简且最速

**Single Producer Single Consumer（SPSC）**——单个生产者、单个消费者——是 Lock-Free 队列中最简单、性能最高的变体。引擎中无处不在：

| 引擎用途 | 生产者 | 消费者 |
|---------|--------|--------|
| 音频环形缓冲区 | 音频解码线程 | 音频输出回调 |
| 命令列表提交 | 主线程 | 渲染线程 |
| 日志缓冲 | 任意线程 | 日志刷盘线程 |
| 网络包接收 | 网络 I/O 线程 | 游戏逻辑线程 |

**核心设计**：两个原子索引（`head`、`tail`），预分配的固定大小环形缓冲区。

```
环形缓冲区（capacity = 8）：
        head=3              tail=6
         ↓                    ↓
  ┌───┬───┬───┬───┬───┬───┬───┬───┐
  │   │   │   │ A │ B │ C │   │   │
  └───┴───┴───┴───┴───┴───┴───┴───┘
  已消费 ←  → 未消费 →  → 空闲

  push: 写入 data[tail % CAP] → tail++
  pop:  读取 data[head % CAP] → head++
```

**为什么 SPSC 不需要 CAS？** 因为 `head` 只被消费者写，`tail` 只被生产者写——没有竞争写。只需要 `store`/`load` + 正确的内存序。

### 1.4 SPSC 内存序完整推导

```cpp
// 生产者
void push(const T& item) {
    size_t t = tail_.load(std::memory_order_relaxed);  // ①
    buffer_[t % CAPACITY] = item;                       // ② 写入数据
    tail_.store(t + 1, std::memory_order_release);      // ③ 发布
}

// 消费者
bool pop(T& item) {
    size_t h = head_.load(std::memory_order_relaxed);   // ④
    if (h == tail_.load(std::memory_order_acquire))     // ⑤ 获取最新 tail
        return false;                                    // 队列空
    item = buffer_[h % CAPACITY];                        // ⑥ 读取数据
    head_.store(h + 1, std::memory_order_release);      // ⑦ 释放 slot
    return true;
}
```

**为什么 ③ 用 `release`？** 保证 ②（数据写入）在 ③（tail 更新）之前对所有后续 `acquire` 可见。如果 ③ 用了 `relaxed`，消费者可能在 ⑥ 读到旧/未完成的数据。

**为什么 ⑤ 用 `acquire`？** 保证一旦看到 ③ 写入的 `tail` 值，② 的数据写入必定可见（synchronize-with 关系建立）。

**为什么 ① 和 ④ 用 `relaxed`？** 因为各自只从自己专用的原子变量读取——生产者不会与自己的 `tail` 有竞争；消费者同理。

**完整的 synchronize-with 链**：
```
生产者: ②(data写入) → [sequenced-before] → ③(release tail)
                                      ↘ synchronize-with
消费者: ⑤(acquire tail) → [sequenced-before] → ⑥(data读取)
```

### 1.5 MPSC 队列：多个生产者，一个消费者

当多个线程需要向同一个消费端提交数据时（例如：多个物理 Job 向渲染线程提交绘制命令），需要 MPSC 队列。

**核心思路**：不能像 SPSC 那样各自拥有独立索引——多个生产者会竞争 `tail`。解决方法：**先 CAS 抢占一个 slot，再写入数据，最后标记 slot 为就绪**。

```
每个 slot 除了数据，还有一个"sequence"标记：

struct Slot {
    T data;
    std::atomic<size_t> sequence;  // 0 = 空闲, 1 = 已写入, 2 = 已被消费...
};

生产者：
  1. CAS tail 抢占一个 slot index
  2. 写入 data
  3. 设置 sequence = tail（标记为就绪）

消费者：
  1. 等待 head slot 的 sequence 变为期望值
  2. 读取 data
  3. 更新 sequence（标记为已消费），head++
```

### 1.6 MPMC 队列：Dmitry Vyukov 的经典设计

**Multiple Producer Multiple Consumer**——完全通用的无锁队列。Dmitry Vyukov 在 2010 年提出的设计至今仍是最广泛使用的 MPMC 实现（被 Rust `crossbeam`、Facebook `folly` 等库采用）。

**核心：每 cell 一个 sequence 原子，enqueue/dequeue 通过 CAS 抢占 cell。**

```
Enqueue(dequeue 对称):

1. 用 CAS 递增 tail，获取写入位置 pos：
   pos = tail.fetch_add(1, relaxed)
   
2. 等待 cell[pos % CAPACITY].sequence 变为 pos：
   while (cell[pos].sequence.load(acquire) != pos) { /* spin */ }
   
3. 写入数据：
   cell[pos].data = value;
   
4. 发布 cell（release）：
   cell[pos].sequence.store(pos + 1, release);
```

**为什么这个设计是 Lock-Free？** 每一步都可能失败，但失败的线程只是重试——没有线程被阻塞等待锁。在任何时刻，至少有一个线程会成功推进。

**为什么需要 sequence？**

- 解决 **ABA 问题**：环形缓冲区中，`tail` 绕一圈回到同一位置时，仅凭 index 无法区分"这个 slot 是空的"还是"上一轮的数据还在"。
- sequence 是单调递增的（与 queue 的全局 push/pop 计数联动），永不回绕。
- 因此：`cell[pos % CAP].sequence == pos` 意味着该 cell 正好对应第 `pos` 次操作。

### 1.7 False Sharing（伪共享）

两个线程访问物理上相邻但逻辑上无关的变量，它们落在同一缓存行（64 字节），导致缓存一致性协议（MESI）不断互相失效对方的缓存行。

**在队列中的表现**：

```cpp
// ❌ 错误：head 和 tail 可能在同一缓存行
struct alignas(64) SPSCQueue_Bad {
    std::atomic<size_t> head_{0};  // offset 0
    std::atomic<size_t> tail_{0};  // offset 8 ← 与 head 同一缓存行！
    T buffer_[256];
};
// 生产者写 tail → 消费者读 head 的缓存行被失效 → 每次 pop 都要重新加载

// ✅ 正确：padding 到不同缓存行
struct SPSCQueue_Good {
    alignas(64) std::atomic<size_t> head_{0};   // 缓存行 0（消费者专属）
    alignas(64) std::atomic<size_t> tail_{0};   // 缓存行 1（生产者专属）
    T buffer_[256];                              // 缓存行 2+
};
```

**检测工具**：Linux `perf c2c`（cache-to-cache）可以精确检测伪共享热点。

### 1.8 ABA 问题与解决

**问题**：线程 A 读到一个值，线程 B 将其改为另一个值，线程 C 又改回原值。线程 A 的 CAS 成功执行——但它不知道值"曾经变过"。

在无锁栈中：A 读 `head = &NodeX`，B 弹出 NodeX，释放它，分配新 NodeY 恰好复用了 NodeX 的地址，将 NodeY push。A 的 CAS 成功——`head` 现在指向 `NodeY`，但 `NodeY->next` 可能指向已被释放的内存。

**解决方案**：

1. **双字 CAS（`cmpxchg16b`）**：在指针旁附加一个版本号。x86-64 上 `std::atomic<std::pair<void*, uint64_t>>` 配合 `compare_exchange_strong`，如果平台支持 128-bit CAS。
2. **Sequence 计数（MPMC 队列的解法）**：每 cell 的 sequence 是单调递增的，绕过地址复用问题。
3. **Hazard Pointer / Epoch-Based Reclamation**：不立即释放节点，等待所有可能访问它的线程"离开危险区域"。

**引擎中的实用主义**：优先选择基于 sequence 的环形缓冲区而非基于链表的无锁栈。环形缓冲区天然避免了 ABA（索引与 sequence 绑定）。

### 1.9 性能特征速查

| 队列类型 | 吞吐 (M op/s) | 延迟 (ns) | 内存 | 竞争特性 |
|---------|--------------|----------|------|---------|
| SPSC (环形) | ~200-400 | ~5-15 | O(capacity) | 零竞争 |
| MPSC (环形) | ~100-200 | ~10-30 | O(capacity) | 仅 tail 竞争 |
| MPMC (Vyukov) | ~30-80 | ~20-50 | O(capacity) | head + tail 竞争 |
| `std::mutex` + `std::deque` | ~5-15 | ~100-1000 | O(N) + 动态 | 满竞争（锁） |

*注：数据为典型 x86-64 系统上的数量级估计，实际值取决于硬件、编译器优化、队列大小。*

---

## 2. 代码示例

### 2.1 完整 SPSC 队列（含完整测试）

```cpp
#include <atomic>
#include <array>
#include <thread>
#include <cassert>
#include <vector>
#include <iostream>

template<typename T, size_t Capacity>
class SPSCQueue {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");

    struct Slot {
        T data;
    };

    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    std::array<Slot, Capacity> buffer_;

public:
    // 生产者调用
    bool push(const T& item) {
        size_t t = tail_.load(std::memory_order_relaxed);
        size_t next = t + 1;
        if (next - head_.load(std::memory_order_acquire) > Capacity)
            return false; // 队列满
        buffer_[t & (Capacity - 1)].data = item;
        tail_.store(next, std::memory_order_release);
        return true;
    }

    // 性能优化版 push：避免每次 load head
    bool push_fast(const T& item) {
        static thread_local size_t cached_head = 0;
        size_t t = tail_.load(std::memory_order_relaxed);

        if (t - cached_head >= Capacity) {
            cached_head = head_.load(std::memory_order_acquire);
            if (t - cached_head >= Capacity)
                return false;
        }

        buffer_[t & (Capacity - 1)].data = item;
        tail_.store(t + 1, std::memory_order_release);
        return true;
    }

    // 消费者调用
    bool pop(T& item) {
        size_t h = head_.load(std::memory_order_relaxed);
        if (h == tail_.load(std::memory_order_acquire))
            return false; // 队列空
        item = buffer_[h & (Capacity - 1)].data;
        head_.store(h + 1, std::memory_order_release);
        return true;
    }

    bool empty() const {
        return head_.load(std::memory_order_acquire) ==
               tail_.load(std::memory_order_acquire);
    }
};

// ===== 自动测试 =====
void test_spsc_basic() {
    SPSCQueue<int, 16> q;
    int val;

    assert(q.empty());
    assert(!q.pop(val));

    for (int i = 0; i < 10; ++i)
        assert(q.push(i * 10));

    for (int i = 0; i < 10; ++i) {
        assert(q.pop(val));
        assert(val == i * 10);
    }

    assert(q.empty());
    std::cout << "[PASS] basic push/pop\n";
}

void test_spsc_full() {
    SPSCQueue<int, 4> q;
    for (int i = 0; i < 4; ++i)  // capacity=4, 最多存3个(一个slot用于区分满/空)
        assert(q.push(i));
    assert(!q.push(999)); // 满
    std::cout << "[PASS] full queue detection\n";
}

void test_spsc_threaded() {
    SPSCQueue<int, 1024> q;
    constexpr int N = 1000000;
    std::atomic<bool> start{false};
    std::atomic<int> sum{0};

    std::thread producer([&] {
        while (!start.load(std::memory_order_acquire));
        for (int i = 0; i < N; ++i) {
            while (!q.push(i)) { /* spin */ }
        }
    });

    std::thread consumer([&] {
        int local_sum = 0;
        int received = 0;
        while (!start.load(std::memory_order_acquire));
        while (received < N) {
            int val;
            if (q.pop(val)) {
                local_sum += val;
                ++received;
            }
        }
        sum.store(local_sum, std::memory_order_release);
    });

    start.store(true, std::memory_order_release);
    producer.join();
    consumer.join();

    int expected = (N - 1) * N / 2;
    assert(sum.load(std::memory_order_acquire) == expected);
    std::cout << "[PASS] threaded test (sum=" << sum.load() << ")\n";
}
```

### 2.2 MPSC 队列

```cpp
#include <atomic>
#include <vector>
#include <memory>

template<typename T, size_t Capacity>
class MPSCQueue {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");

    struct Slot {
        std::atomic<size_t> sequence;
        T data;
    };

    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    std::vector<Slot> buffer_;

public:
    MPSCQueue() : buffer_(Capacity) {
        for (size_t i = 0; i < Capacity; ++i)
            buffer_[i].sequence.store(i, std::memory_order_relaxed);
    }

    // 多个生产者调用
    bool push(const T& item) {
        size_t pos = tail_.fetch_add(1, std::memory_order_relaxed);
        Slot& slot = buffer_[pos & (Capacity - 1)];

        // 等待 slot 就绪（只能有一个生产者在等）
        while (slot.sequence.load(std::memory_order_acquire) != pos) {
            // 被消费者超越？队列满
            if (pos - head_.load(std::memory_order_acquire) >= Capacity)
                return false;
        }

        slot.data = item;
        slot.sequence.store(pos + 1, std::memory_order_release);
        return true;
    }

    // 单个消费者调用
    bool pop(T& item) {
        size_t h = head_.load(std::memory_order_relaxed);
        Slot& slot = buffer_[h & (Capacity - 1)];

        if (slot.sequence.load(std::memory_order_acquire) != h + 1)
            return false; // 队列空

        item = slot.data;
        slot.sequence.store(h + Capacity, std::memory_order_release);
        head_.store(h + 1, std::memory_order_release);
        return true;
    }
};
```

### 2.3 MPMC 队列（Dmitry Vyukov 设计）

```cpp
#include <atomic>
#include <vector>

template<typename T, size_t Capacity>
class MPMCQueue {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");
    static_assert(Capacity >= 2, "Capacity must be >= 2");

    struct Cell {
        std::atomic<size_t> sequence;
        T data;
    };

    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    std::vector<Cell> buffer_;
    const size_t mask_;

public:
    MPMCQueue() : buffer_(Capacity), mask_(Capacity - 1) {
        for (size_t i = 0; i < Capacity; ++i)
            buffer_[i].sequence.store(i, std::memory_order_relaxed);
    }

    bool enqueue(const T& data) {
        Cell* cell;
        size_t pos = tail_.load(std::memory_order_relaxed);
        for (;;) {
            cell = &buffer_[pos & mask_];
            size_t seq = cell->sequence.load(std::memory_order_acquire);
            intptr_t diff = static_cast<intptr_t>(seq) - static_cast<intptr_t>(pos);

            if (diff == 0) {
                // Cell 可用，尝试 CAS 抢占 tail
                if (tail_.compare_exchange_weak(pos, pos + 1,
                        std::memory_order_relaxed, std::memory_order_relaxed))
                    break;
            } else if (diff < 0) {
                // 队列满
                return false;
            } else {
                // 被其他生产者抢先了，更新 pos 重试
                pos = tail_.load(std::memory_order_relaxed);
            }
        }

        cell->data = data;
        cell->sequence.store(pos + 1, std::memory_order_release);
        return true;
    }

    bool dequeue(T& data) {
        Cell* cell;
        size_t pos = head_.load(std::memory_order_relaxed);
        for (;;) {
            cell = &buffer_[pos & mask_];
            size_t seq = cell->sequence.load(std::memory_order_acquire);
            intptr_t diff = static_cast<intptr_t>(seq) - static_cast<intptr_t>(pos + 1);

            if (diff == 0) {
                if (head_.compare_exchange_weak(pos, pos + 1,
                        std::memory_order_relaxed, std::memory_order_relaxed))
                    break;
            } else if (diff < 0) {
                return false; // 队列空
            } else {
                pos = head_.load(std::memory_order_relaxed);
            }
        }

        data = cell->data;
        cell->sequence.store(pos + mask_ + 1, std::memory_order_release);
        return true;
    }
};
```

### 2.4 Benchmark：四种队列对比

```cpp
#include <chrono>
#include <mutex>
#include <deque>
#include <iostream>

// std::mutex + std::deque（基准对比）
template<typename T>
class MutexDequeQueue {
    std::deque<T> deque_;
    std::mutex mtx_;
public:
    void push(T val) {
        std::lock_guard lk(mtx_);
        deque_.push_back(std::move(val));
    }
    bool pop(T& val) {
        std::lock_guard lk(mtx_);
        if (deque_.empty()) return false;
        val = std::move(deque_.front());
        deque_.pop_front();
        return true;
    }
};

template<typename Queue>
double benchmark_spsc(int items_per_thread, int num_threads) {
    Queue q;
    std::atomic<bool> start{false};
    std::atomic<size_t> produced{0}, consumed{0};

    auto t1 = std::chrono::high_resolution_clock::now();

    std::vector<std::thread> producers, consumers;
    for (int i = 0; i < num_threads; ++i) {
        producers.emplace_back([&, i] {
            while (!start.load(std::memory_order_acquire));
            for (int j = 0; j < items_per_thread; ++j)
                q.push(j);
            produced.fetch_add(1, std::memory_order_release);
        });
    }
    for (int i = 0; i < num_threads; ++i) {
        consumers.emplace_back([&] {
            while (!start.load(std::memory_order_acquire));
            int consumed_count = 0;
            while (consumed_count < items_per_thread) {
                int val;
                if (q.pop(val)) ++consumed_count;
            }
            consumed.fetch_add(1, std::memory_order_release);
        });
    }

    start.store(true, std::memory_order_release);
    for (auto& t : producers) t.join();
    for (auto& t : consumers) t.join();

    auto t2 = std::chrono::high_resolution_clock::now();
    return std::chrono::duration<double, std::milli>(t2 - t1).count();
}

// 使用示例：
// auto ms = benchmark_spsc<SPSCQueue<int, 1024>>(1'000'000, 1);
// std::cout << "SPSC: " << ms << "ms\n";
```

### 2.5 音频环形缓冲区（引擎实战）

```cpp
// 音频线程场景：解码线程（生产者）填充 1024-sample 块，
// 音频回调（消费者）以固定速率消费
template<size_t NumFrames>
class AudioRingBuffer {
    static constexpr size_t NUM_CHANNELS = 2;

    struct alignas(64) {
        std::atomic<size_t> write_frame_{0};  // 生产者写入位置
    };
    struct alignas(64) {
        std::atomic<size_t> read_frame_{0};   // 消费者读取位置
    };

    float buffer_[NumFrames][NUM_CHANNELS];

public:
    // 解码线程调用：写入交错立体声数据
    size_t write(const float* interleaved, size_t frame_count) {
        size_t w = write_frame_.load(std::memory_order_relaxed);
        size_t r = read_frame_.load(std::memory_order_acquire);
        size_t available = NumFrames - (w - r);
        size_t to_write = std::min(frame_count, available);

        for (size_t i = 0; i < to_write; ++i) {
            size_t idx = (w + i) % NumFrames;
            buffer_[idx][0] = interleaved[i * 2];
            buffer_[idx][1] = interleaved[i * 2 + 1];
        }

        write_frame_.store(w + to_write, std::memory_order_release);
        return to_write;
    }

    // 音频回调调用：读取并输出
    size_t read(float* output, size_t frame_count) {
        size_t r = read_frame_.load(std::memory_order_relaxed);
        size_t w = write_frame_.load(std::memory_order_acquire);
        size_t available = w - r;
        size_t to_read = std::min(frame_count, available);

        for (size_t i = 0; i < to_read; ++i) {
            size_t idx = (r + i) % NumFrames;
            output[i * 2]     = buffer_[idx][0];
            output[i * 2 + 1] = buffer_[idx][1];
        }

        read_frame_.store(r + to_read, std::memory_order_release);
        return to_read;
    }

    // 欠载检测（音频爆音诊断）
    size_t available_frames() const {
        return write_frame_.load(std::memory_order_acquire) -
               read_frame_.load(std::memory_order_acquire);
    }
};
```

---

## 3. 练习

### 练习 1（必做）：SPSC vs `std::mutex+deque` Benchmark

实现一个 benchmark，在单生产者单消费者场景下比较 `SPSCQueue<int, 1024>` 和 `MutexDequeQueue<int>` 的吞吐量：

1. 分别传输 100 万个 `int`，测量耗时。
2. 分别传输 100 万个 `std::string`（64 字节），测量耗时。
3. 分析差异：为什么 `int` 的差异和 `string` 的差异不同？（提示：`std::deque` 对 string 会触发堆分配）
4. 用 `perf stat` 或类似工具测量两种方案的 cache-misses 和 branch-misses。

### 练习 2（必做）：给 SPSC 队列添加缓存行 Padding

1. 在教程的 `SPSCQueue` 基础上，创建一个不加 padding 的变体（移除 `alignas(64)`），故意让 `head_` 和 `tail_` 在相邻地址。
2. 分别 benchmark 并排和无 padding 版本的吞吐量（使用 2 核运行）。
3. 使用 Linux `perf c2c`（或 Windows Performance Toolkit）检测伪共享。
4. 报告差异百分比并解释。

### 练习 3（可选·挑战）：实现带优先级的渲染命令队列

基于 MPSC 队列设计一套渲染命令提交系统：

1. 定义 `RenderCommand` 结构（至少包含：`DrawMesh`、`SetMaterial`、`SetTransform`）。
2. 实现 **三层优先级** 的 MPSC 命令队列（高/中/低优先级各一个内部队列）。
3. 消费者（渲染线程）总是优先 drain 高优先级队列。
4. 实现命令批处理：消费者一次性 drain 最多 64 个命令再提交 GPU，减少 CPU-GPU 同步次数。
5. Benchmark：不同优先级混合 vs 单队列的延迟分布。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> #include <chrono>
> #include <iostream>
> #include <atomic>
> #include <thread>
> #include <string>
> #include <deque>
> #include <mutex>
>
> // 复用教程中的 SPSCQueue 和 MutexDequeQueue
> // (此处假定已定义——完整代码见 2.1 和 2.4 节）
>
> template<typename T>
> class MutexDequeQueue {
>     std::deque<T> deque_;
>     std::mutex mtx_;
> public:
>     void push(T val) {
>         std::lock_guard lk(mtx_);
>         deque_.push_back(std::move(val));
>     }
>     bool pop(T& val) {
>         std::lock_guard lk(mtx_);
>         if (deque_.empty()) return false;
>         val = std::move(deque_.front());
>         deque_.pop_front();
>         return true;
>     }
> };
>
> // ===== Benchmark 模板 =====
> template<typename Queue>
> double bench_spsc(int num_items) {
>     Queue q;
>     std::atomic<bool> start{false};
>     std::atomic<long long> checksum{0};
>
>     std::thread producer([&] {
>         while (!start.load(std::memory_order_acquire));
>         for (int i = 0; i < num_items; ++i) {
>             while (!q.push(i)) {} // spin until success
>         }
>     });
>
>     std::thread consumer([&] {
>         long long sum = 0;
>         int received = 0;
>         while (!start.load(std::memory_order_acquire));
>         while (received < num_items) {
>             int val;
>             if (q.pop(val)) {
>                 sum += val;
>                 ++received;
>             }
>         }
>         checksum.store(sum, std::memory_order_release);
>     });
>
>     auto t0 = std::chrono::high_resolution_clock::now();
>     start.store(true, std::memory_order_release);
>     producer.join();
>     consumer.join();
>     auto t1 = std::chrono::high_resolution_clock::now();
>
>     // 验证正确性
>     long long expected = static_cast<long long>(num_items - 1) * num_items / 2;
>     if (checksum.load() != expected) {
>         std::cerr << "CHECKSUM MISMATCH!\n";
>     }
>     return std::chrono::duration<double, std::milli>(t1 - t0).count();
> }
>
> int main() {
>     constexpr int N = 1'000'000;
>
>     std::cout << "=== SPSC vs Mutex+Deque Benchmark ===\n\n";
>
>     // 测试 1: int 类型
>     std::cout << "--- int (1M items) ---\n";
>     double t_spsc_int = bench_spsc<SPSCQueue<int, 1024>>(N);
>     double t_mtx_int  = bench_spsc<MutexDequeQueue<int>>(N);
>     std::cout << "SPSC:        " << t_spsc_int << " ms\n";
>     std::cout << "Mutex+Deque: " << t_mtx_int << " ms\n";
>     std::cout << "Speedup:     " << t_mtx_int / t_spsc_int << "x\n\n";
>
>     // 测试 2: std::string (64 字节）
>     // 需要特化——string 不能直接用 int 的 push/pop
>     std::cout << "--- std::string(64B, 1M items) ---\n";
>     // 此处略去 string 版本 benchmark 模板（结构与 int 版相同）
>     // 只需将 Queue 模板参数改为 SPSCQueue<std::string, 1024>
>     // 和 MutexDequeQueue<std::string>
>
>     return 0;
> }
> ```
>
> **差异分析**：
> - `int` 差异主要来自锁开销（atomic + futex/临界区 vs 无锁 CAS）
>   - SPSC: push 约 2 条 atomic 操作 + 1 次内存写入；pop 同理
>   - Mutex+Deque: push 需获取锁（原子操作+可能的系统调用）+ deque 扩容的堆分配
> - `std::string` 差异更大：
>   - SPSC: string 的短字符串优化（SSO）使 ≤15 字节的 string 无堆分配，64 字节触发堆分配但每次 move 只是指针交换
>   - Mutex+Deque: `push_back(std::move(val))` 仍触发 deque 内部节点的堆分配，且锁持有期间可能阻塞其他操作
> - `perf stat` 测量：
>   - SPSC 的 cache-misses 通常低 3-10x（数据在同一个缓存行上，无锁竞争导致的缓存行弹跳少）
>   - SPSC 的 branch-misses 也低（无锁版本的分支预测更稳定——循环中的 CAS 失败路径极少触发）

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <atomic>
> #include <array>
> #include <thread>
> #include <chrono>
> #include <iostream>
>
> // 无 padding 版本：head_ 和 tail_ 紧密相邻
> template<typename T, size_t Capacity>
> class SPSCQueue_NoPad {
>     static_assert((Capacity & (Capacity - 1)) == 0);
>
>     struct Slot { T data; };
>     // 注意：没有 alignas(64)，head_ 和 tail_ 相邻！
>     std::atomic<size_t> head_{0};
>     std::atomic<size_t> tail_{0};
>     std::array<Slot, Capacity> buffer_;
>
> public:
>     bool push(const T& item) {
>         size_t t = tail_.load(std::memory_order_relaxed);
>         size_t next = t + 1;
>         if (next - head_.load(std::memory_order_acquire) > Capacity)
>             return false;
>         buffer_[t & (Capacity - 1)].data = item;
>         tail_.store(next, std::memory_order_release);
>         return true;
>     }
>
>     bool pop(T& item) {
>         size_t h = head_.load(std::memory_order_relaxed);
>         if (h == tail_.load(std::memory_order_acquire))
>             return false;
>         item = buffer_[h & (Capacity - 1)].data;
>         head_.store(h + 1, std::memory_order_release);
>         return true;
>     }
> };
>
> // 有 padding 版本（教程中的 SPSCQueue——带 alignas(64)）
> // SPSCQueue_Padded 即教程的 SPSCQueue，此处省略重复定义
>
> template<typename Queue>
> double bench_throughput(int num_items) {
>     Queue q;
>     std::atomic<bool> start{false};
>     volatile long long checksum = 0;  // volatile 防优化
>
>     std::thread producer([&] {
>         while (!start.load(std::memory_order_acquire));
>         for (int i = 0; i < num_items; ++i)
>             while (!q.push(i)) {}
>     });
>
>     std::thread consumer([&] {
>         int received = 0;
>         while (!start.load(std::memory_order_acquire));
>         while (received < num_items) {
>             int val;
>             if (q.pop(val)) ++received;
>         }
>     });
>
>     auto t0 = std::chrono::high_resolution_clock::now();
>     start.store(true, std::memory_order_release);
>     producer.join();
>     consumer.join();
>     auto t1 = std::chrono::high_resolution_clock::now();
>
>     return std::chrono::duration<double, std::milli>(t1 - t0).count();
> }
>
> int main() {
>     constexpr int N = 10'000'000;
>
>     // 应在双核系统上运行以获得明显差异
>     double t_nopad = bench_throughput<SPSCQueue_NoPad<int, 1024>>(N);
>     double t_pad   = bench_throughput<SPSCQueue<int, 1024>>(N);
>
>     std::cout << "=== Cache Line Padding Impact ===\n";
>     std::cout << "No padding: " << t_nopad << " ms\n";
>     std::cout << "Padded:     " << t_pad << " ms\n";
>     std::cout << "Slowdown without padding: "
>               << ((t_nopad / t_pad) - 1.0) * 100 << "%\n";
>
>     return 0;
> }
> ```
>
> **伪共享解释**：
> - 无 padding 时，`head_` 和 `tail_` 在同一缓存行（64 字节）
> - 生产者写 `tail_` → 该缓存行在生产者核心标记为 Modified
> - 消费者写 `head_` → 同一缓存行需要从生产者核心 Invalidate + 传输到消费者核心
> - 即便 head 和 tail 是独立变量，它们共享一个缓存行 → 每次写入都使对方核心的缓存行失效
> - 预期差异：无 padding 版本慢 20-50%（取决于核心拓扑）
> - 检测工具：Linux `perf c2c` 显示 HITM（Hit Modified）计数；Windows Performance Toolkit 的 Contention 视图

> [!tip]- 练习 3 参考答案（挑战）
> ```cpp
> #include <atomic>
> #include <array>
> #include <vector>
> #include <memory>
> #include <cstring>
> #include <chrono>
> #include <iostream>
> #include <thread>
>
> // ===== 渲染命令定义 =====
> struct RenderCommand {
>     enum Type : uint8_t { DrawMesh, SetMaterial, SetTransform, Nop } type = Nop;
>     union {
>         struct { unsigned mesh_id; unsigned material_id; } draw;
>         struct { unsigned material_id; } material;
>         struct { float matrix[16]; } transform;
>     };
> };
>
> // ===== 简化 SPSC 队列（无锁，用作内部队列） =====
> template<typename T, size_t Capacity>
> class SPSCQueue_Simple {
>     static_assert((Capacity & (Capacity - 1)) == 0);
>     struct alignas(64) { std::atomic<size_t> head{0}; };
>     struct alignas(64) { std::atomic<size_t> tail{0}; };
>     T buffer_[Capacity];
> public:
>     bool push(const T& item) {
>         size_t t = tail_.load(std::memory_order_relaxed);
>         if (t - head_.load(std::memory_order_acquire) >= Capacity)
>             return false;
>         buffer_[t & (Capacity - 1)] = item;
>         tail_.store(t + 1, std::memory_order_release);
>         return true;
>     }
>     bool pop(T& item) {
>         size_t h = head_.load(std::memory_order_relaxed);
>         if (h == tail_.load(std::memory_order_acquire))
>             return false;
>         item = buffer_[h & (Capacity - 1)];
>         head_.store(h + 1, std::memory_order_release);
>         return true;
>     }
>     bool empty() const {
>         return head_.load(std::memory_order_acquire) ==
>                tail_.load(std::memory_order_acquire);
>     }
> };
>
> // ===== 三层优先级 MPSC 渲染命令队列 =====
> class PriorityRenderQueue {
> public:
>     static constexpr size_t BATCH_SIZE = 64;
>     static constexpr size_t Q_CAPACITY = 1024;
>
>     // 生产者（游戏线程）调用
>     void submit(RenderCommand cmd, int priority) {
>         // priority: 0=高, 1=中, 2=低
>         if (priority < 0 || priority > 2) priority = 2;
>         queues_[priority].push(cmd);
>     }
>
>     // 消费者（渲染线程）调用：drain 最多 BATCH_SIZE 个命令
>     size_t drain(std::vector<RenderCommand>& out) {
>         out.clear();
>         out.reserve(BATCH_SIZE);
>
>         // 总是优先 drain 高优先级队列
>         for (int prio = 0; prio < 3 && out.size() < BATCH_SIZE; ++prio) {
>             RenderCommand cmd;
>             while (out.size() < BATCH_SIZE && queues_[prio].pop(cmd)) {
>                 out.push_back(cmd);
>             }
>         }
>         return out.size();
>     }
>
>     // 检查是否全空
>     bool all_empty() const {
>         return queues_[0].empty() && queues_[1].empty() && queues_[2].empty();
>     }
>
> private:
>     // 高/中/低 三个内部 SPSC 队列（单个生产者到单个消费者）
>     SPSCQueue_Simple<RenderCommand, Q_CAPACITY> queues_[3];
> };
>
> // ===== Benchmark: 优先级混合 vs 单队列延迟分布 =====
> void bench_priority_latency() {
>     PriorityRenderQueue pq;
>     SPSCQueue_Simple<RenderCommand, 1024> single_q;
>
>     std::atomic<bool> start{false};
>     std::atomic<size_t> high_latency_sum{0}, low_latency_sum{0};
>     std::atomic<int> total_submitted{0};
>
>     constexpr int NUM_FRAMES = 1000;
>     constexpr int CMDS_PER_FRAME = 64;
>
>     // 生产者线程
>     std::thread producer([&] {
>         while (!start.load(std::memory_order_acquire));
>         for (int frame = 0; frame < NUM_FRAMES; ++frame) {
>             // 每帧混合提交：20 高优先 + 30 中优先 + 14 低优先
>             for (int i = 0; i < 20; ++i)
>                 pq.submit(RenderCommand{DrawMesh, {0, 0}}, 0);
>             for (int i = 0; i < 30; ++i)
>                 pq.submit(RenderCommand{SetMaterial, {1}}, 1);
>             for (int i = 0; i < 14; ++i)
>                 pq.submit(RenderCommand{SetTransform, {}}, 2);
>             total_submitted.fetch_add(64);
>         }
>     });
>
>     // 消费者线程
>     std::thread consumer([&] {
>         while (!start.load(std::memory_order_acquire));
>         size_t processed = 0;
>         std::vector<RenderCommand> batch;
>
>         while (processed < NUM_FRAMES * CMDS_PER_FRAME) {
>             size_t n = pq.drain(batch);
>             if (n > 0) {
>                 // 模拟提交 GPU（此处简单累加）
>                 processed += n;
>             }
>         }
>     });
>
>     auto t0 = std::chrono::high_resolution_clock::now();
>     start.store(true, std::memory_order_release);
>     producer.join();
>     consumer.join();
>     auto t1 = std::chrono::high_resolution_clock::now();
>
>     double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
>     std::cout << "Priority queue: " << NUM_FRAMES << " frames in " << ms << " ms\n";
>     std::cout << "Average: " << (ms / NUM_FRAMES) << " ms/frame\n";
> }
> ```
>
> **设计要点**：
> - 三个独立 SPSC 队列使不同优先级的命令互不阻塞——即使低优先级队列满，高优先级命令仍可入队
> - 批处理（`BATCH_SIZE=64`）减少 CPU-GPU 同步点：64 个命令合并为一次 `vkQueueSubmit`/`ID3D12CommandQueue::ExecuteCommandLists`
> - 延迟分布：高优先级命令总是先被 drain，保证交互渲染命令（如 UI）的低延迟
> - 扩展：可引入时间戳——命令入队时记录时间，出队时计算实际延迟，按优先级分别统计 p50/p99

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- **[必读]** *C++ Concurrency in Action (2nd ed.)* — Anthony Williams，第 7 章 "Lock-free concurrent data structures"
- **[必读]** "1024cores.net" — Dmitry Vyukov 的博客，MPMC 队列原作者的详细解释（http://www.1024cores.net/home/lock-free-algorithms/queues）
- **[推荐]** "Single Producer Single Consumer Lock-free FIFO From the Ground Up" — Charles Frasch (CppCon 2023)，从零构建 SPSC 的精彩演讲
- **[推荐]** "C++ and the Perils of Double-Checked Locking" — Scott Meyers, Andrei Alexandrescu（Dr. Dobb's 2004），理解内存序的历史背景
- **[进阶]** *Is Parallel Programming Hard, And, If So, What Can You Do About It?* — Paul McKenney，附录 D "Lock-Free Data Structures"
- **[工具]** `relacy`（https://github.com/dvyukov/relacy） — Dmitry Vyukov 的 C++ 无锁算法验证工具，在模型检查器中穷举所有线程交错

---

## 常见陷阱

### 陷阱 1：忘记 `capacity` 为 2 的幂的前提

```cpp
// ❌ 错误：取模运算 `% Capacity` 在非 2 的幂时编译器生成除法指令
size_t idx = pos % capacity;  // 编译器生成 div 指令 → 20-80 cycles

// ✅ 正确：2 的幂可以用位与，编译器生成单条 and 指令
static_assert((CAPACITY & (CAPACITY - 1)) == 0);
size_t idx = pos & (CAPACITY - 1);  // 单周期 and
```

在 16.6ms 帧预算中，热点路径上多一条 `div` 指令可能吃掉数百微秒。

### 陷阱 2：SPSC 队列中生产者和消费者都用 `relaxed`

```cpp
// ❌ 错误：全都用 relaxed
void push_bad(const T& item) {
    size_t t = tail_.load(std::memory_order_relaxed);
    buffer_[t % CAP] = item;
    tail_.store(t + 1, std::memory_order_relaxed);  // ❌ 没有 release
}
bool pop_bad(T& item) {
    size_t h = head_.load(std::memory_order_relaxed);
    if (h == tail_.load(std::memory_order_relaxed)) return false;  // ❌ 没有 acquire
    item = buffer_[h % CAP];
    head_.store(h + 1, std::memory_order_relaxed);
    return true;
}
// 后果：x86 上可能侥幸工作（x86 硬件有较强的隐式内存序），
// ARM 上 100% 出 bug——消费者可能读到旧数据（数据写入还在 store buffer 中）

// ✅ 正确：tail store用release，tail load用acquire
```

### 陷阱 3：认为 Lock-Free 意味着"不需要考虑竞争"

```cpp
// ❌ 错误：MPMC 队列中，认为每个 cell 只有一个线程在写就安全
// 实际情况：生产者线程 A 抢到 pos=5 的 cell，写入了一半数据
//           生产者线程 B 抢到 pos=5+CAPACITY 的 cell（绕了一圈）
//           如果不使用 sequence 区分，B 会覆盖 A 还在写入的 cell！

// ✅ 正确：MPMC 队列的 sequence 协议保证：
//   - 生产者只写入 sequence == pos 的 cell
//   - 消费者只读取 sequence == pos+1 的 cell
```

### 陷阱 4：`pop` 后没有检查返回值

```cpp
// ❌ 错误：queue 为空时未检查
void process_commands() {
    Command cmd;
    queue_.pop(cmd);  // 不检查返回值！
    execute(cmd);     // cmd 未初始化 → UB
}

// ✅ 正确：总是检查
void process_commands() {
    Command cmd;
    if (queue_.pop(cmd)) {
        execute(cmd);
    }
    // 或批量 drain：
    Command cmds[64];
    int count = 0;
    while (count < 64 && queue_.pop(cmds[count])) ++count;
    for (int i = 0; i < count; ++i) execute(cmds[i]);
}
```

### 陷阱 5：SPSC 的 `push` 中每次调用都 `load(acquire)` head

```cpp
// ❌ 次优：每次 push 都从内存加载 head（跨缓存行访问）
bool push_slow(const T& item) {
    size_t t = tail_.load(relaxed);
    if (t - head_.load(acquire) >= CAP) return false; // 每次都读
    // ...
}

// ✅ 优化：缓存 head 的线程局部副本，只在可能满时才同步
bool push_fast(const T& item) {
    thread_local size_t cached_head = 0; // 每线程缓存
    size_t t = tail_.load(relaxed);
    if (t - cached_head >= CAP) {
        cached_head = head_.load(acquire); // 只在必要时同步
        if (t - cached_head >= CAP) return false;
    }
    // ...
}
// 在典型 SPSC 场景中，减少 99% 的跨缓存行读取
```
