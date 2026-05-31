# 20. 原子操作与 C++ 内存序精讲

> **所属计划**: C++ 游戏工程师详细攻略 — 阶段 6：并发与原子操作
> **预计耗时**: 5 小时
> **前置知识**: [2-对象生命周期与内存布局](02-object-lifetime-memory-layout.md)
> **C++ 标准**: C++11 (atomic, memory_order), C++20 (atomic_ref, atomic_wait)
> **参考深度探索**: `docs/deep-dives/cpp-memory-order-game-engine.md`

---

## 1. 概念讲解

### 1.1 C++ 内存模型的核心问题

多核 CPU 上，每个核心有自己的 L1/L2 缓存和**写缓冲区 (Store Buffer)**。CPU 为了性能会对指令重排序——在不违反单线程语义的前提下，实际的执行顺序可能和代码顺序完全不同。

```cpp
// 你写的代码：
int a = 1;          // (1)
int b = 2;          // (2)
ready = true;       // (3)

// CPU 实际可能执行顺序：
int b = 2;          // (2)
ready = true;       // (3) ← 重排到这里
int a = 1;          // (1) ← 重排到这里
```

在单线程中这没有问题——没人看得见中间态。但多线程中，另一个线程可能在 `ready=true` 可见时读到 `a=0`（旧值）。

**C++ 内存模型定义了解决此问题的规则体系**。

### 1.2 数据竞争：UB 的唯一定义

**数据竞争** (Data Race)：两个线程并发访问同一内存位置，至少一个是写操作，且两个操作之间没有任何同步（happens-before 关系）。**有数据竞争的 C++ 程序 = 未定义行为**。

```cpp
int counter = 0;

// 线程 A: counter++;   // 读-修改-写，非原子
// 线程 B: counter++;   // 同时执行 → 数据竞争 → UB
```

### 1.3 std::atomic<T>：消除数据竞争的基础设施

`std::atomic<T>` 保证对 `T` 的读写是**不可分割的**（原子的）——要么完全执行，要么完全不执行。所有 C++ 内存序体系都建立在 `std::atomic` 之上。

```cpp
#include <atomic>

std::atomic<int> counter{0};

void increment() {
    counter.fetch_add(1);  // ✅ 原子操作：读-修改-写，无数据竞争
}
```

**lock-free 检测**：
```cpp
std::atomic<int> a;
if (a.is_lock_free()) {
    // 硬件原子指令（x86: LOCK 前缀，ARM: LDREX/STREX）
} else {
    // 编译器使用内部互斥锁实现原子性（罕见，仅在大型 struct 上发生）
}
```

### 1.4 happens-before 与 synchronize-with

C++ 内存模型用 **happens-before** 定义可见性：

- **sequenced-before**：同一线程内，A 在源码中先于 B → A happens-before B
- **synchronize-with**：线程间原子操作——如果 A 是 release 写，B 是读取该值的 acquire 读 → A synchronize-with B → A happens-before B
- **传递性**：A→B 且 B→C ⇒ A→C

```cpp
// 线程 1
data = 42;                          // (1) 写 data
flag.store(true, release);          // (2) release 写

// 线程 2
while (!flag.load(acquire)) {}      // (3) acquire 读，读到 true → 与 (2) synchronize-with
assert(data == 42);                 // (4) data 的写入对线程 2 可见 ✅
```

**关键**：synchronize-with 只在**同一个原子变量**的 release 写和后续 acquire 读之间建立。不同原子变量之间没有这个关系！

### 1.5 六种内存序

| memory_order | 保证 | CPU 指令开销 | 使用场景 |
|-------------|------|-------------|---------|
| `relaxed` | 仅原子性，无顺序保证 | 最低 | 统计计数器、进度追踪 |
| `consume` | 依赖序（C++17 起不推荐） | 低 | 几乎不用 |
| `acquire` | 后续读写不能重排到此 load 之前 | ARM: DMB；x86: 仅编译器 | 锁的 lock、消费者读取 |
| `release` | 之前的读写不能重排到此 store 之后 | ARM: DMB；x86: 仅编译器 | 锁的 unlock、生产者写入 |
| `acq_rel` | acquire + release | 两者开销之和 | RMW 操作如 fetch_add |
| `seq_cst` | 全局统一顺序（最强） | 最高（可能触发总线锁） | 需严格定序的场景 |

**合法组合表**：

| 操作 | 允许的 memory_order |
|------|-------------------|
| `load()` | `relaxed`, `consume`, `acquire`, `seq_cst` |
| `store()` | `relaxed`, `release`, `seq_cst` |
| `exchange`, `fetch_add`, `fetch_sub` 等 RMW | `relaxed`, `acquire`, `release`, `acq_rel`, `seq_cst` |

**注意**：`store` 不能用 `acquire`，`load` 不能用 `release`——编译器会报错。

### 1.6 relaxed：只有原子性，没有顺序

```cpp
std::atomic<size_t> frame_counter{0};

// 渲染线程
frame_counter.fetch_add(1, std::memory_order_relaxed);  // 只关心值最终正确

// 主线程（读取到屏幕上显示）
size_t frames = frame_counter.load(std::memory_order_relaxed);
// 不关心和其他变量的相对顺序——只做性能统计
```

**relaxed 的合法用途**：单纯的计数器、进度追踪——不需要和其他变量建立 happens-before 关系。

### 1.7 acquire/release：锁和队列的基石

```cpp
// 标志位同步模式（最常见）
std::atomic<bool> data_ready{false};
Payload             shared_payload;

// 生产者线程
void produce() {
    shared_payload = compute_payload();    // (A) 准备数据
    data_ready.store(true, release);       // (B) release 写：保证 (A) 在 (B) 之前完成
}

// 消费者线程
void consume() {
    while (!data_ready.load(acquire)) {}   // (C) acquire 读
    process(shared_payload);               // (D) (A) 的结果对 (D) 保证可见
    // (B) synchronize-with (C) → (A) happens-before (D)
}
```

### 1.8 seq_cst：最易理解也最贵

`seq_cst` 保证**所有 seq_cst 操作之间有一个全局统一的顺序**——每个线程看到的所有 seq_cst 操作的顺序是一致的。

```cpp
std::atomic<bool> x{false}, y{false};
std::atomic<int>  z{0};

// 线程 1                      线程 2
x.store(true, seq_cst);      y.store(true, seq_cst);
if (y.load(seq_cst))         if (x.load(seq_cst))
    z++;                         z++;

// 使用 seq_cst：线程 1 和 2 不可能同时看到对方为 false → z 至少为 1
// 使用 acquire/release：可能同时为 false → z = 0！（x86 上不会，ARM 上可能）
```

**引擎使用建议**：当你对内存序不确定时，先用 `seq_cst`。profile 后用 `acquire/release` 替换热路径上的 seq_cst 操作。

### 1.9 compare_exchange：lock-free 的核心

`compare_exchange` 是原子化的"如果值等于预期就替换"操作——lock-free 编程的基础原语。

```cpp
// compare_exchange_weak(expected, desired, success_order, failure_order)
// 如果 atomic == expected → atomic = desired，返回 true
// 否则 → expected = atomic，返回 false

std::atomic<int> head{0};

void push() {
    int old_head = head.load(acquire);
    do {
        // 尝试：head = new_value，前提是 head 没变
    } while (!head.compare_exchange_weak(old_head, new_value,
                                          release,   // 成功时的内存序
                                          acquire));  // 失败时的内存序
}
```

**weak vs strong**：
| 特性 | compare_exchange_weak | compare_exchange_strong |
|------|----------------------|------------------------|
| 伪失败 | 允许 | 不允许 |
| 指令 | 通常更简单、更快 | 在 LL/SC 架构上需要额外循环 |
| 使用场景 | **循环中**（重试是预期行为） | 不需要循环时 |

**引擎建议**：几乎所有 lock-free 模式都在循环中使用 CAS，用 `weak`。

### 1.10 ABA 问题

**情景**：线程 A 读到 head=A，线程 B 将 A→B→A，线程 A 的 CAS 发现 head 还是 A（认为没变），CAS 成功——但实际上链表结构已经变了。

```cpp
// 线程 A：读取 head=A
// 线程 B：pop A, pop B, push A
// 线程 A：CAS(A, B) → 成功！（但 B 可能已被释放 → use-after-free）
```

**解决方案**：
- **Tagged pointer**：指针高位存版本号，每次操作递增
- **Hazard Pointer**：延迟释放，直到确认没有线程还在引用
- **Epoch-Based Reclamation (EBR)**：分 epoch，只有进入新 epoch 后才释放旧 epoch 的内存

### 1.11 Memory Fences

`std::atomic_thread_fence` 是不绑定具体原子变量的独立屏障：

```cpp
// 等价于 atomic.store(release) 但不绑定变量
data = 42;
std::atomic_thread_fence(std::memory_order_release);
flag.store(true, relaxed);  // 配合 fence，保证 data 的写入对后续 acquire 可见
```

**引擎使用**：fence 在定义复杂的同步协议时有用（如多变量同时发布），但通常直接使用带内存序的原子操作更清晰。

### 1.12 volatile vs atomic

| | volatile | std::atomic |
|--|----------|-------------|
| 防止编译器优化掉读写 | ✅ | ✅ |
| 防止编译器重排序 | ✅（仅 vs 其他 volatile） | ✅ |
| 防止 CPU 重排序 | ❌ | ✅ |
| 保证原子性 | ❌ | ✅ |
| 建立 happens-before | ❌ | ✅ |
| 多线程正确 | ❌ **绝对不行** | ✅ |

**volatile 的正当用途**：内存映射 I/O（MMIO）、信号处理函数内。多线程同步**必须**用 atomic。

### 1.13 引擎中的模式速查

| 引擎模式 | 内存序 | 说明 |
|---------|--------|------|
| 每帧计数器 | `relaxed` | 只管最终值正确 |
| Job 依赖计数 | `fetch_sub(1, acq_rel)` | 读见前一个完成者，写通知下一个 |
| SPSC 队列 enqueue | `store(release)` | 保证数据在 head 更新前完成 |
| SPSC 队列 dequeue | `load(acquire)` | 保证看到 tail 更新后的数据 |
| Mutex::lock | `exchange(acquire)` | 获取锁 = 获取先前的 release 写入 |
| Mutex::unlock | `store(release)` | 释放锁 = 发布所有写入 |
| 全局状态标志 | `seq_cst` | 简单、正确、易调试 |

---

## 2. 代码示例

### 示例 1：完整的 Lock-Free SPSC Bounded Queue

```cpp
#include <atomic>
#include <vector>
#include <cstddef>
#include <cassert>

template<typename T, size_t Capacity>
class SPSCQueue {
    static_assert((Capacity & (Capacity - 1)) == 0,
                  "Capacity must be power of 2");

    struct alignas(64) {  // 避免伪共享
        std::atomic<size_t> head{0};
        char _pad1[64 - sizeof(std::atomic<size_t>)];
    } producer_;

    struct alignas(64) {
        std::atomic<size_t> tail{0};
        char _pad2[64 - sizeof(std::atomic<size_t>)];
    } consumer_;

    T buffer_[Capacity];

public:
    // 生产者：入队
    bool enqueue(const T& item) {
        size_t head = producer_.head.load(std::memory_order_relaxed);
        size_t tail = consumer_.tail.load(std::memory_order_acquire);

        // 队列满？
        if (head - tail >= Capacity) return false;

        buffer_[head & (Capacity - 1)] = item;

        // release：保证数据写入发生在 head 更新之前
        producer_.head.store(head + 1, std::memory_order_release);
        return true;
    }

    // 消费者：出队
    bool dequeue(T& item) {
        size_t tail = consumer_.tail.load(std::memory_order_relaxed);
        size_t head = producer_.head.load(std::memory_order_acquire);

        // 队列空？
        if (tail == head) return false;

        item = buffer_[tail & (Capacity - 1)];

        // release：保证读取完成再更新 tail（通知生产者）
        consumer_.tail.store(tail + 1, std::memory_order_release);
        return true;
    }

    // 批量出队
    size_t dequeue_bulk(T* out, size_t max_count) {
        size_t tail = consumer_.tail.load(std::memory_order_relaxed);
        size_t head = producer_.head.load(std::memory_order_acquire);
        size_t available = head - tail;
        size_t count = (available < max_count) ? available : max_count;

        for (size_t i = 0; i < count; ++i) {
            out[i] = buffer_[(tail + i) & (Capacity - 1)];
        }
        consumer_.tail.store(tail + count, std::memory_order_release);
        return count;
    }
};
```

### 示例 2：原子计数器基准测试

```cpp
#include <atomic>
#include <thread>
#include <vector>
#include <iostream>
#include <chrono>

template<typename F>
double benchmark(F func, int iterations) {
    double best = 1e18;
    for (int i = 0; i < iterations; ++i) {
        auto s = std::chrono::high_resolution_clock::now();
        func();
        auto e = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(e - s).count();
        if (ms < best) best = ms;
    }
    return best;
}

void counter_benchmark() {
    constexpr int64_t OPS_PER_THREAD = 10'000'000;

    // relaxed fetch_add
    {
        std::atomic<int64_t> counter{0};
        auto f = [&]() {
            std::vector<std::thread> threads;
            for (int t = 0; t < 4; ++t) {
                threads.emplace_back([&]() {
                    for (int64_t i = 0; i < OPS_PER_THREAD; ++i)
                        counter.fetch_add(1, std::memory_order_relaxed);
                });
            }
            for (auto& t : threads) t.join();
        };
        double ms = benchmark(f, 5);
        std::cout << "relaxed fetch_add: " << ms << " ms  ("
                  << (4 * OPS_PER_THREAD / ms * 1000 / 1e9) << " B ops/s)\n";
    }

    // seq_cst fetch_add
    {
        std::atomic<int64_t> counter{0};
        auto f = [&]() {
            std::vector<std::thread> threads;
            for (int t = 0; t < 4; ++t) {
                threads.emplace_back([&]() {
                    for (int64_t i = 0; i < OPS_PER_THREAD; ++i)
                        counter.fetch_add(1, std::memory_order_seq_cst);
                });
            }
            for (auto& t : threads) t.join();
        };
        double ms = benchmark(f, 5);
        std::cout << "seq_cst fetch_add: " << ms << " ms  ("
                  << (4 * OPS_PER_THREAD / ms * 1000 / 1e9) << " B ops/s)\n";
    }
}
```

### 示例 3：用原子操作实现 Mutex

```cpp
#include <atomic>
#include <thread>

class SpinMutex {
    std::atomic<bool> locked_{false};

public:
    void lock() {
        // 快速路径：尝试直接获取
        bool expected = false;
        if (locked_.compare_exchange_strong(expected, true,
                std::memory_order_acquire,
                std::memory_order_relaxed)) {
            return;  // 成功获取锁
        }

        // 慢速路径：自旋等待
        while (true) {
            expected = false;
            // 自旋读取，不唤醒总线
            while (locked_.load(std::memory_order_relaxed)) {
                #if defined(__x86_64__) || defined(_M_X64)
                    __builtin_ia32_pause();  // PAUSE 指令：省电、减少总线争用
                #endif
            }
            // 尝试获取
            if (locked_.compare_exchange_weak(expected, true,
                    std::memory_order_acquire,
                    std::memory_order_relaxed)) {
                return;
            }
        }
    }

    void unlock() {
        locked_.store(false, std::memory_order_release);
    }

    bool try_lock() {
        bool expected = false;
        return locked_.compare_exchange_strong(expected, true,
            std::memory_order_acquire, std::memory_order_relaxed);
    }
};
```

### 示例 4：Job System 计数器

```cpp
#include <atomic>
#include <functional>
#include <vector>
#include <thread>

class SimpleJobSystem {
public:
    using Job = std::function<void()>;

    struct Counter {
        std::atomic<int> value{0};

        void add_ref()  { value.fetch_add(1, std::memory_order_relaxed); }
        void release()  {
            // acq_rel：读部分看到之前 release 的递减，写部分通知后续 acquire
            if (value.fetch_sub(1, std::memory_order_acq_rel) == 1) {
                // 我是最后一个引用者 → 执行 completion
                completion();
            }
        }
        Job completion;
    };

    // 提交带有计数器的任务
    void submit_with_counter(Job task, Counter* counter) {
        counter->add_ref();
        queue_.push_back([task, counter]() {
            task();
            counter->release();
        });
    }

    // 等待计数器归零（主线程同步点）
    void wait(Counter* counter) {
        counter->completion = []{};  // 空操作（实际业务逻辑在此）
        counter->release();          // 释放主线程的 ref
        // 实际实现中需要某种等待机制（condition_variable 或 spin-wait）
        while (counter->value.load(std::memory_order_acquire) > 0) {
            std::this_thread::yield();
        }
    }

private:
    std::vector<Job> queue_;
};
```

### 示例 5：ABA 问题演示

```cpp
#include <atomic>
#include <thread>
#include <iostream>

// 简化版无锁栈（展示 ABA 问题）
template<typename T>
class UnsafeStack {
    struct Node { T data; Node* next; };
    std::atomic<Node*> head_{nullptr};

public:
    void push(const T& val) {
        Node* n = new Node{val, nullptr};
        n->next = head_.load(std::memory_order_acquire);
        while (!head_.compare_exchange_weak(n->next, n,
                std::memory_order_release, std::memory_order_acquire)) {}
    }

    bool pop(T& out) {
        Node* old_head = head_.load(std::memory_order_acquire);
        while (old_head) {
            if (head_.compare_exchange_weak(old_head, old_head->next,
                    std::memory_order_acquire, std::memory_order_acquire)) {
                out = old_head->data;
                // ⚠️ ABA 漏洞：此线程在读取 old_head 后到 CAS 成功之间，
                // 另一个线程可能 pop(old_head)→pop(old_head->next)→push(old_head)
                // 此时 CAS 成功但 old_head->next 已被释放 → use-after-free
                delete old_head;
                return true;
            }
        }
        return false;
    }
};
```

### 示例 6：游戏主循环 + Job 计数器

```cpp
#include <atomic>
#include <vector>
#include <thread>
#include <functional>
#include <chrono>

class GameLoopWithJobs {
    std::atomic<int> jobs_remaining_{0};
    std::atomic<bool> running_{true};
    std::atomic<int> frame_number_{0};
    std::vector<std::thread> workers_;

public:
    GameLoopWithJobs(int num_workers) {
        for (int i = 0; i < num_workers; ++i) {
            workers_.emplace_back([this, i]() { worker_loop(i); });
        }
    }

    // 从主线程提交 Job（每帧调用）
    void kick_job(std::function<void()> job) {
        jobs_remaining_.fetch_add(1, std::memory_order_release);
        // 在真实系统中，job 被放入无锁队列
        // 简化：worker 直接获取并执行
    }

    // 等待所有 Job 完成（帧结束的栅栏点）
    void wait_all_jobs() {
        while (jobs_remaining_.load(std::memory_order_acquire) > 0) {
            // 自旋或 yield——实际引擎用条件变量或 fiber 切换
            std::this_thread::yield();
        }
    }

    // 主循环（每帧）
    void frame() {
        int frame = frame_number_.fetch_add(1, std::memory_order_relaxed);

        // 1. 提交并行任务
        kick_job([frame]() { /* 物理更新 */ });
        kick_job([frame]() { /* 动画更新 */ });
        kick_job([frame]() { /* 音频处理 */ });

        // 2. 等待所有任务完成
        wait_all_jobs();

        // 3. 渲染（单线程，在 GPU 提交前）
        // render();
    }

private:
    void worker_loop(int worker_id) {
        while (running_.load(std::memory_order_acquire)) {
            // 从队列中获取 job（简化：空循环检查）
            if (jobs_remaining_.load(std::memory_order_acquire) > 0) {
                // execute job
                jobs_remaining_.fetch_sub(1, std::memory_order_release);
            } else {
                std::this_thread::yield();
            }
        }
    }

public:
    ~GameLoopWithJobs() {
        running_.store(false, std::memory_order_release);
        for (auto& w : workers_) if (w.joinable()) w.join();
    }
};
```

---

## 3. 练习

### 练习 1（必修）：实现 Lock-Free SPSC 队列

实现一个完整的 Single Producer Single Consumer 有界队列：

1. 使用 `std::atomic<size_t>` 管理 head/tail 索引
2. 使用 `alignas(64)` 分隔 head 和 tail 避免伪共享
3. 实现 `enqueue(const T&)` → `bool` 和 `dequeue(T&)` → `bool`
4. 明确注释每个原子操作使用的内存序及其理由
5. 写一个测试：一个线程连续入队 1M 元素，另一个线程出队，验证数据完整性
6. 额外要求：`Capacity` 必须是 2 的幂，用 `static_assert` 强制

### 练习 2（必修）：构建简单的 Job System 计数器

实现一个 Job System 的依赖计数器：

1. 定义 `struct JobCounter { std::atomic<int> count; std::function<void()> on_complete; }`
2. `add_dependency()` 增加计数（relaxed）
3. `release_dependency()` 减少计数——当计数归零时调用 `on_complete`
4. `release_dependency()` 必须使用 `fetch_sub(1, acq_rel)` 确保所有之前的工作对完成回调可见
5. 写测试：创建 10 个 Job，每个 Job 完成时调用 `release_dependency()`，验证 `on_complete` 只被调用一次且在所有 Job 完成后

### 练习 3（选做挑战）：多生产者单消费者（MPSC）队列

将练习 1 的 SPSC 队列扩展为 MPSC（Multiple Producer Single Consumer）：

1. 生产者端需要 CAS 循环获取 slot（因为多个线程竞争 head）
2. 消费者端保持简单（单消费者，只需 load(acquire)）
3. 使用 `compare_exchange_weak` 在循环中获取 head
4. 处理"slot 已被占用但数据尚未写完"的同步——这需要额外的同步标志
5. 对比 SPSC 和 MPSC 的单操作延迟和总吞吐量
6. 提供两种实现：一种使用 `seq_cst`（易于推理），一种优化为 `acq_rel`（高性能），对比两者延迟

---

## 4. 扩展阅读

- **C++ Concurrency in Action (2nd ed.)** (Anthony Williams) — 第 5 章是内存序的权威参考
- **"Memory Barriers: a Hardware View for Software Hackers"** (Paul McKenney) — 理解内存屏障的经典
- **1024cores.net** (Dmitry Vyukov) — Lock-free 算法详解，包括著名的 MPSC/MPMC 队列
- **"Is Parallel Programming Hard, And, If So, What Can You Do About It?"** (Paul McKenney) — Linux RCU 作者的全书，免费在线
- **C++ Reference: [std::memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)** — 完整的内存序文档
- **Unity DOTS / Unreal Engine Task Graph** — 工业级 Job System 参考实现
- **MoodyCamel ConcurrentQueue** (https://github.com/cameron314/concurrentqueue) — 工业级 MPMC 队列源码
- `docs/deep-dives/cpp-memory-order-game-engine.md` — 游戏引擎特定的内存序模式深度剖析
- **Compiler Explorer** — 观察不同内存序在 x86 vs ARM 下生成的汇编指令

---

## 常见陷阱

### 陷阱 1：用 `relaxed` 实现标志位同步

```cpp
// ❌ 绝对错误的标志位同步
std::atomic<bool> ready{false};
Payload data;

// 线程 1
data = compute();              // (A)
ready.store(true, relaxed);   // (B) relaxed 不阻止 (A) 被重排到 (B) 之后！

// 线程 2
if (ready.load(relaxed)) {    // (C) relaxed 不阻止后续操作被重排到 (C) 之前
    process(data);            // (D) → 可能读到未完成的 data！UB！
}

// ✅ 正确：线程 1 store(release)，线程 2 load(acquire)
// 或者直接使用 seq_cst
```

### 陷阱 2：store 用 acquire，load 用 release

```cpp
std::atomic<int> a{0};
a.store(1, std::memory_order_acquire);  // ❌ 编译错误！store 不能用 acquire
a.load(std::memory_order_release);      // ❌ 编译错误！load 不能用 release
```

**规则**：store 只能用 `relaxed` / `release` / `seq_cst`；load 只能用 `relaxed` / `acquire` / `seq_cst`。编译器会拒绝非法组合。

### 陷阱 3：认为 `std::atomic` 自动保护关联数据

```cpp
// ❌ 错误理解
std::atomic<bool> flag{false};
int shared_data = 0;

// 线程 1
shared_data = 42;   // 非原子！
flag = true;        // 原子，但没有指定内存序 → 默认 seq_cst

// 线程 2
if (flag) {
    // 编译器可能在优化时重排 shared_data 的读写
    // flag 的原子性不保护 shared_data！
    process(shared_data);  // 可能看到 0
}

// ✅ 正确：必须通过 synchronize-with 建立 happens-before
// 线程 1：shared_data = 42; flag.store(true, release);
// 线程 2：while (!flag.load(acquire)); process(shared_data);
```

### 陷阱 4：volatile 用于多线程同步

```cpp
volatile int counter = 0;   // ❌ volatile 不提供任何多线程保证

// 线程 A: counter++;  // 不是原子的！读-修改-写会丢失更新
// 线程 B: counter++;  // 数据竞争 — UB

// ✅ 使用 std::atomic<int> counter{0};
```

**volatile 的唯一正当用途**：内存映射 I/O、信号处理函数中修改的变量。对多线程，用 `std::atomic`。

### 陷阱 5：CAS 循环中忘记更新 expected 变量

```cpp
std::atomic<int> head{0};

void buggy_push(int val) {
    int old = head.load(acquire);
    // ❌ 如果 CAS 失败，old 在 weak 下已被更新，但循环没继续尝试
    head.compare_exchange_weak(old, val, release, acquire);
}

void correct_push(int val) {
    int old = head.load(acquire);
    while (!head.compare_exchange_weak(old, val, release, acquire)) {
        // old 被 weak 自动更新为当前值，继续循环 ✅
    }
}
```

### 陷阱 6：伪共享导致原子操作性能暴跌

```cpp
// ❌ 两个原子变量在同一个缓存行
struct BadCounters {
    std::atomic<uint64_t> a{0};  // 线程 A 频繁写入
    std::atomic<uint64_t> b{0};  // 线程 B 频繁写入 → 缓存行弹跳
};

// ✅ 使用 alignas 分隔
struct alignas(64) GoodCounter {
    std::atomic<uint64_t> value{0};
};
// 每个计数器独立缓存行，无伪共享

// C++17 建议：
// alignas(std::hardware_destructive_interference_size) std::atomic<int> a;
// 注意：该常量在 C++20 前仅为建议值（非强制），实际实现中可能为 64
```

### 陷阱 7：忽视 x86 与 ARM 的内存模型差异

```cpp
// x86 上这段代码能通过测试，ARM 上失败
std::atomic<int> a{0}, b{0};
int x = 0, y = 0;

// 线程 1                       线程 2
x = 1;                        y = 1;
a.store(1, relaxed);           b.store(1, relaxed);
if (b.load(relaxed) == 0)     if (a.load(relaxed) == 0)
    assert(x == 1);               assert(y == 1);
// 两个 assert 可能同时失败！→ 无 synchronize-with

// x86：Store-Load 重排序是唯一允许的重排序，所以 x86 上可能通过
// ARM：几乎所有重排序都允许——代码会崩溃
// ⚠️ 绝对不能依赖特定 CPU 的重排序行为来"证明"代码正确
```
