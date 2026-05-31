# 引擎中的多线程架构

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 20-原子操作与C++内存序精讲

---

## 1. 概念讲解

### 1.1 为什么游戏引擎需要自己的线程模型？

通用 C++ 并发工具——`std::async`、`std::thread`、裸 `std::mutex`——在游戏引擎中**几乎从不直接使用**。原因不是它们"不好"，而是它们的设计目标与游戏引擎的硬实时约束根本冲突。

**帧预算（16.6ms @ 60fps）要求一切可预测。** 通用线程模型的问题：

| 问题 | 具体表现 | 引擎后果 |
|------|---------|---------|
| `std::async` 隐式创建/销毁线程 | 每个异步调用可能启动新线程，OS 调度不可控 | 帧内线程数波动，上下文切换不可预测 |
| `std::mutex` 无条件内核态睡眠 | 竞争时线程被 OS 挂起，恢复延迟可达毫秒级 | 音频线程被挂起 → 爆音；渲染线程被挂起 → 掉帧 |
| 通用调度器不知道引擎语义 | OS 平等对待所有线程，不知道"渲染线优先于加载线" | 关键路径被后台任务抢占 |
| 动态内存分配 | `std::async` 可能堆分配任务对象 | 每帧大量小分配 → 内存碎片 → 卡顿 |

**引擎的正确做法**：启动时创建固定数量的持久化工作线程，每帧主线程向工作线程派发任务，帧边界做同步。线程永不销毁，任务永不堆分配（用侵入式队列或预分配环形缓冲区）。

```
帧模型（60 FPS = 16.6ms/帧）：
│←═══════════════════ 16.6ms ═══════════════════→│
│                                                  │
│[主线程] Update → Submit Jobs → Wait → Render     │
│[Worker0]  ←────────── Execute Jobs ──────────→  │
│[Worker1]  ←────────── Execute Jobs ──────────→  │
│[Worker2]  ←────────── Execute Jobs ──────────→  │
│[音频线程] ←──────────────── 独立循环 ──────────→│
│                                                  │
│ Wait = fence：所有帧内 Job 完成后再继续          │
```

### 1.2 线程创建与生命周期（C++11）

C++11 引入了 `std::thread`，这是游戏引擎的线程构建块。

```cpp
#include <thread>
#include <iostream>

void worker_main(int id) {
    std::cout << "Worker " << id << " started\n";
}

std::thread t1(worker_main, 1);  // 立即开始执行
std::thread t2{std::move(t1)};   // 线程可移动，不可拷贝

// join：等待线程结束，清理资源
t2.join();   // 调用前必须检查 joinable()，否则 std::terminate

// detach：放弃所有权，线程独立运行（引擎中几乎不应使用）
// t2.detach();  // 危险：无法同步，无法安全访问引擎数据
```

**引擎中的线程生命周期**：

```cpp
class EngineThreadPool {
    std::vector<std::thread> workers_;
    std::atomic<bool> running_{true};

public:
    EngineThreadPool(unsigned count) {
        workers_.reserve(count);
        for (unsigned i = 0; i < count; ++i) {
            workers_.emplace_back([this, i] {
                workerLoop(i);
            });
        }
    }

    ~EngineThreadPool() {
        running_.store(false, std::memory_order_release);
        for (auto& t : workers_) {
            if (t.joinable()) t.join();  // 安全等待
        }
    }

private:
    void workerLoop(unsigned id) {
        while (running_.load(std::memory_order_acquire)) {
            // 从队列取任务，执行
        }
    }
};
```

**`thread_local` 存储**：每个线程拥有独立副本的变量，是引擎中最高频的并发工具之一。

```cpp
// 每个线程独立的临时分配器——无锁，缓存友好
thread_local char tls_frame_buffer[1024 * 1024];  // 1MB 每线程
thread_local size_t tls_buffer_offset = 0;
thread_local uint64_t tls_thread_id = 0;  // 缓存线程 ID 避免系统调用

// 引擎中使用：每线程性能计数器、临时分配器、日志缓冲
```

### 1.3 线程亲和性（Thread Affinity）与钉扎（Pinning）

默认情况下，OS 调度器可以任意将线程迁移到不同 CPU 核心。迁移会导致：
- **缓存失效**：L1/L2 缓存内容全部作废，必须从 L3/内存重新加载
- **NUMA 问题**：线程访问的数据在"另一个"内存节点上，延迟加倍
- **不可预测性**：你不知道你的 Job 到底在哪个核心上执行

**解决方案**：将线程"钉"在特定核心上。

**Windows（SetThreadAffinityMask）**：

```cpp
#ifdef _WIN32
#include <windows.h>

void pin_thread_to_core(unsigned core_index) {
    DWORD_PTR mask = 1ULL << core_index;
    DWORD_PTR result = SetThreadAffinityMask(GetCurrentThread(), mask);
    if (result == 0) {
        // 处理失败（例如核心编号超出范围）
    }
}
#endif
```

**Linux/POSIX（pthread_setaffinity_np）**：

```cpp
#ifdef __linux__
#include <pthread.h>

void pin_thread_to_core(unsigned core_index) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(core_index, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
}
#endif
```

**跨平台封装（引擎中常见的模式）**：

```cpp
class ThreadAffinity {
public:
    static void pin_to_core(unsigned core) {
        // 通过 std::thread::native_handle() 获取平台句柄
        // Windows: HANDLE (实际上是线程句柄)
        // Linux:   pthread_t
    }

    // 典型引擎配置：
    // Core 0:     主线程（游戏逻辑 + 调度）
    // Core 1-2:   渲染线程组
    // Core 3-5:   工作线程（物理、AI、粒子）
    // Core 6:     音频线程
    // Core 7:     OS / 后台 I/O
};
```

**线程优先级**：确保延迟敏感的线程（音频 1ms、渲染 16.6ms）不被其他线程抢占。

```cpp
// Windows
SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST);

// Linux
struct sched_param param;
param.sched_priority = sched_get_priority_max(SCHED_FIFO);
pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
```

### 1.4 Job System 架构

Job System 是现代游戏引擎并发模型的核心。核心理念：将工作分解为**独立的小任务（Job）**，工作线程从队列中拉取执行。

**基础架构**：

```
主线程                      Job 队列                工作线程池
   │                    ┌──────────────┐
   │──push(JobA)───────→│ JobA │ JobB  │←──pop()──── Worker 0
   │──push(JobB)───────→│ JobC │       │←──pop()──── Worker 1
   │──push(JobC)───────→│      │       │←──pop()──── Worker 2
   │                    └──────────────┘
   │                         ↑
   │                    工作窃取：空闲线程从其他线程的队列"偷"任务
```

**关键设计决策**：

| 决策 | 选项 | 引擎适用性 |
|------|------|----------|
| 队列数 | 全局单队列 vs 每线程队列 | 单队列有争用瓶颈；多队列+窃取是最佳实践 |
| 窃取策略 | 随机窃取 vs 从尾部窃取 | 从尾部窃取（LIFO）减少竞争 |
| Job 粒度 | 大 Job vs 微 Job | 太细：调度开销占比高；太粗：并行度不足 |
| 依赖管理 | 无依赖 vs DAG | 物理约束求解需要依赖图 |
| 内存管理 | 堆分配 vs 预分配池 | 必须预分配，帧内零分配 |

### 1.5 Fiber（纤程）——用户态协程

Fiber 是比线程更轻量的并发原语：**用户态协作式多任务**。线程切换需要陷入内核（~1-10μs），Fiber 切换只是保存/恢复寄存器和栈指针（~10-50ns）。

**与线程的对比**：

| 特性 | 线程（Thread） | Fiber |
|------|---------------|-------|
| 调度者 | OS 内核（抢占式） | 用户代码（协作式） |
| 切换成本 | ~1-10μs | ~10-50ns |
| 栈 | 内核分配（~1MB） | 用户态分配（可自定义大小） |
| 并发 | 真正并行 | 同一线程内串行，需多线程才能并行 |
| 暂停点 | 任何时刻（抢占） | 只在显式 yield 点 |

**引擎中 Fiber 的使用场景**：

```cpp
// 场景：加载一个关卡资源，需要多次异步 I/O
// 传统回调写法（地狱）：
load_mesh("hero.mesh", [](Mesh* m) {
    load_texture("hero.tex", [](Texture* t) {
        load_anim("hero.anim", [](Anim* a) {
            assemble_hero(m, t, a);
        });
    });
});

// Fiber 写法（同步风格，异步执行）：
void load_hero_fiber() {
    auto mesh    = fiber_await(load_mesh_async("hero.mesh"));
    auto texture = fiber_await(load_texture_async("hero.tex"));
    auto anim    = fiber_await(load_anim_async("hero.anim"));
    assemble_hero(mesh, texture, anim);
    // fiber_yield() —— 控制权归还调度器
}
```

**Fiber 实现要点**（概念模型）：

```cpp
struct FiberContext {
    void* rsp;          // 栈指针
    void* rip;          // 指令指针
    // 其他被调用者保存的寄存器...
    char  stack[65536]; // 64KB 栈
};

// 切换：保存当前上下文，恢复目标上下文
void switch_fiber(FiberContext* from, FiberContext* to) {
    // 汇编实现：保存 from 的寄存器，加载 to 的寄存器
    // x86_64: mov [from], rsp; mov rsp, [to]; ret
}
```

### 1.6 工作窃取（Work Stealing）

工作窃取是 Job System 保持负载均衡的**标准范式**：

```
每个 Worker 拥有自己的双端队列（deque）：
  Worker 从自己队列的头部 pop（LIFO——最近提交的 Job 先执行，缓存热）
  空闲 Worker 从其他队列的尾部 steal（FIFO——最早提交的大块工作）
```

**为什么这样设计？**
- **LIFO pop**：刚被当前 Worker 提交的子 Job 数据还在缓存中，立即执行最热
- **FIFO steal**：窃取者拿到的是"最大块"的旧 Job，粒度大，窃取开销占比低

### 1.7 帧内同步点（Frame Fences）

游戏循环是天然的分段流水线，每一段之间有明确的同步点：

```
帧开始
  │
  ▼ Fence: 等待前一帧的 GPU 完成
  │
  ▼ Phase 1: 输入处理（主线程，无需同步）
  │
  ▼ Fence: 等待物理 Job 全部完成
  │
  ▼ Phase 2: 游戏逻辑更新（可部分并行）
  │
  ▼ Fence: 等待所有逻辑 Job 完成
  │
  ▼ Phase 3: 提交渲染命令（主线程）
  │
  ▼ Fence: 渲染线程消费命令列表
  │
  ▼ Phase 4: GPU 执行 + Vsync 等待
  │
帧结束
```

**关键同步原语**：

```cpp
// C++20 std::latch —— 一次性倒计时门闩
std::latch frame_latch{num_workers};
// 每个 Worker 完成工作后：frame_latch.count_down();
// 主线程等待：frame_latch.wait();

// C++20 std::barrier —— 可复用的阶段同步
std::barrier frame_barrier{num_workers};
// 每个线程到达后：frame_barrier.arrive_and_wait();
// 自动重置，下一帧可继续使用
```

### 1.8 GPU/CPU 同步——多重缓冲

GPU 是异步处理器：提交命令后 CPU 不等待，直接继续。这引入了**数据竞争**：CPU 正在修改下一帧的数据时，GPU 还在读当前帧的数据。

**解决方案：多重缓冲（Double/Triple Buffering）**

```
Double Buffering（双缓冲）：
┌─────────┐    ┌─────────┐
│ Buffer 0│    │ Buffer 1│
│ (GPU读) │    │ (CPU写) │
└─────────┘    └─────────┘
        ↑ swap at fence ↓
┌─────────┐    ┌─────────┐
│ Buffer 0│    │ Buffer 1│
│ (CPU写) │    │ (GPU读) │
└─────────┘    └─────────┘

Triple Buffering（三缓冲）：
   Buffer 0: GPU 正在渲染
   Buffer 1: 渲染完成，等待 Vsync 呈现
   Buffer 2: CPU 正在填充下一帧数据
→ 消除 CPU 等待 GPU 的空闲时间，保持流水线满载
```

### 1.9 引擎操作的线程安全性

| 操作 | 策略 | 实现 |
|------|------|------|
| **日志** | 无锁环形缓冲区 | 每个线程写自己的 slot，消费者线程批量刷盘 |
| **性能计数** | `thread_local` + 帧末合并 | 每线程独立计数，帧结束时原子加总 |
| **内存分配** | 每线程分配器池 | `thread_local` Arena 或 Pool，零锁 |
| **实体创建/销毁** | 命令队列 | 不能直接在 Worker 中改 ECS，提交"创建命令"给主线程 |

---

## 2. 代码示例

### 2.1 完整的 Job System（含工作窃取）

```cpp
#include <atomic>
#include <functional>
#include <thread>
#include <vector>
#include <memory>
#include <cassert>
#include <random>

// ===== 基础 Job =====
struct Job {
    std::function<void()> func;
    Job* parent = nullptr;          // 父 Job
    std::atomic<int> unfinished{1}; // 未完成计数（自身 + 子Job）
};

// ===== 每 Worker 的双端 Job 队列 =====
class WorkStealingQueue {
    static constexpr size_t CAPACITY = 256;

    struct alignas(64) { // 缓存行对齐防止 false sharing
        std::atomic<size_t> head{0};
        std::atomic<size_t> tail{0};
        Job* jobs[CAPACITY];
    } data_;

public:
    // Worker 自己 push/pop（LIFO——从尾部操作）
    bool push(Job* job) {
        size_t t = data_.tail.load(std::memory_order_relaxed);
        if (t - data_.head.load(std::memory_order_acquire) >= CAPACITY)
            return false; // 队列满
        data_.jobs[t % CAPACITY] = job;
        data_.tail.store(t + 1, std::memory_order_release);
        return true;
    }

    bool pop(Job*& job) {
        size_t t = data_.tail.load(std::memory_order_relaxed);
        if (t == 0) return false;
        t--;
        data_.tail.store(t, std::memory_order_relaxed);
        size_t h = data_.head.load(std::memory_order_acquire);
        if (h <= t) {
            job = data_.jobs[t % CAPACITY];
            if (h != t) return true;
            // h == t: 最后一个 Job，需要和窃取者竞争
            size_t expected = h;
            if (data_.head.compare_exchange_strong(
                    expected, h + 1, std::memory_order_release, std::memory_order_relaxed)) {
                return true;
            }
            // 竞争失败，恢复 tail
            data_.tail.store(h + 1, std::memory_order_release);
        } else {
            data_.tail.store(h, std::memory_order_release);
        }
        return false;
    }

    // 其他 Worker steal（FIFO——从头部操作）
    bool steal(Job*& job) {
        size_t h = data_.head.load(std::memory_order_acquire);
        size_t t = data_.tail.load(std::memory_order_acquire);
        if (h >= t) return false;
        job = data_.jobs[h % CAPACITY];
        size_t expected = h;
        if (data_.head.compare_exchange_strong(
                expected, h + 1, std::memory_order_release, std::memory_order_relaxed)) {
            return true;
        }
        return false; // CAS 失败，被其他窃取者抢先
    }
};

// ===== Job System =====
class JobSystem {
    std::vector<std::thread> threads_;
    std::vector<WorkStealingQueue> queues_;
    std::atomic<bool> running_{true};

    void workerLoop(unsigned worker_id) {
        WorkStealingQueue& my_queue = queues_[worker_id];
        std::mt19937 rng{worker_id + 42}; // 随机窃取

        while (running_.load(std::memory_order_acquire)) {
            Job* job = nullptr;

            // 1. 先从自己的队列取（LIFO）
            if (my_queue.pop(job)) {
                executeJob(job, worker_id);
                continue;
            }

            // 2. 自己空了——从其他队列窃取（FIFO）
            unsigned num_workers = static_cast<unsigned>(queues_.size());
            unsigned start = rng() % num_workers;
            for (unsigned i = 0; i < num_workers; ++i) {
                unsigned target = (start + i) % num_workers;
                if (target == worker_id) continue;
                if (queues_[target].steal(job)) {
                    executeJob(job, worker_id);
                    break;
                }
            }

            // 3. 什么都没拿到——短暂让出 CPU
            if (!job) {
                std::this_thread::yield();
            }
        }
    }

    void executeJob(Job* job, unsigned worker_id) {
        job->func();
        // Job 完成——递减父 Job 的未完成计数
        if (job->parent) {
            int prev = job->parent->unfinished.fetch_sub(1, std::memory_order_acq_rel);
            if (prev == 1) {
                // 父 Job 的所有子 Job 都完成了，将父 Job 重新入队
                queues_[worker_id].push(job->parent);
            }
        }
    }

public:
    explicit JobSystem(unsigned num_workers) : queues_(num_workers) {
        threads_.reserve(num_workers);
        for (unsigned i = 0; i < num_workers; ++i) {
            threads_.emplace_back([this, i] { workerLoop(i); });
        }
    }

    ~JobSystem() {
        running_.store(false, std::memory_order_release);
        for (auto& t : threads_) {
            if (t.joinable()) t.join();
        }
    }

    // 提交根 Job（无父 Job）
    void submit(Job* job) {
        // 简单策略：轮询分发到各 Worker 队列
        static std::atomic<unsigned> rr{0};
        unsigned idx = rr.fetch_add(1, std::memory_order_relaxed) % queues_.size();
        queues_[idx].push(job);
    }

    // 提交子 Job（依赖于父 Job）
    void submit_child(Job* parent, Job* child) {
        child->parent = parent;
        parent->unfinished.fetch_add(1, std::memory_order_relaxed);
        submit(child);
    }

    // 等待 Job 完成
    void wait(Job* job) {
        while (job->unfinished.load(std::memory_order_acquire) > 0) {
            std::this_thread::yield();
        }
    }
};
```

### 2.2 Thread Pool 含亲和性设置

```cpp
#include <thread>
#include <vector>
#include <functional>
#include <atomic>
#include <mutex>
#include <condition_variable>
#include <queue>

#ifdef _WIN32
#include <windows.h>
#elif defined(__linux__)
#include <pthread.h>
#endif

class PinnedThreadPool {
public:
    using Task = std::function<void()>;

    explicit PinnedThreadPool(unsigned count = std::thread::hardware_concurrency()) {
        workers_.reserve(count);
        for (unsigned i = 0; i < count; ++i) {
            workers_.emplace_back([this, i] {
                pin_to_core(i);
                set_priority_high();
                worker_loop();
            });
        }
    }

    ~PinnedThreadPool() {
        {
            std::lock_guard lk(mtx_);
            stop_ = true;
        }
        cv_.notify_all();
        for (auto& t : workers_) {
            if (t.joinable()) t.join();
        }
    }

    void enqueue(Task task) {
        {
            std::lock_guard lk(mtx_);
            tasks_.push(std::move(task));
        }
        cv_.notify_one();
    }

private:
    void worker_loop() {
        while (true) {
            Task task;
            {
                std::unique_lock lk(mtx_);
                cv_.wait(lk, [this] { return stop_ || !tasks_.empty(); });
                if (stop_ && tasks_.empty()) return;
                task = std::move(tasks_.front());
                tasks_.pop();
            }
            task();
        }
    }

    static void pin_to_core(unsigned core) {
#ifdef _WIN32
        SetThreadAffinityMask(GetCurrentThread(), 1ULL << core);
#elif defined(__linux__)
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(core, &cpuset);
        pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
#endif
    }

    static void set_priority_high() {
#ifdef _WIN32
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST);
#elif defined(__linux__)
        struct sched_param param;
        param.sched_priority = sched_get_priority_max(SCHED_FIFO) - 1;
        pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
#endif
    }

    std::vector<std::thread> workers_;
    std::queue<Task> tasks_;
    std::mutex mtx_;
    std::condition_variable cv_;
    bool stop_{false};
};
```

### 2.3 parallel_for 实现

```cpp
#include <thread>
#include <vector>
#include <functional>
#include <atomic>

// 简单的 parallel_for：将 [begin, end) 均分给 N 个 Worker
template<typename IndexType, typename Func>
void parallel_for(IndexType begin, IndexType end, Func&& func,
                  unsigned num_threads = std::thread::hardware_concurrency()) {
    if (end - begin <= 0) return;

    IndexType total = end - begin;
    IndexType chunk = (total + num_threads - 1) / num_threads;

    std::vector<std::thread> threads;
    threads.reserve(num_threads);

    for (unsigned t = 0; t < num_threads; ++t) {
        IndexType start = begin + t * chunk;
        IndexType stop  = std::min(start + chunk, end);
        if (start >= stop) break;

        threads.emplace_back([start, stop, &func] {
            for (IndexType i = start; i < stop; ++i) {
                func(i);
            }
        });
    }

    for (auto& t : threads) {
        if (t.joinable()) t.join();
    }
}

// 使用示例：
// float positions[10000];
// parallel_for(0, 10000, [&](int i) {
//     positions[i] = std::sin(positions[i]);
// });
```

### 2.4 双缓冲渲染命令列表

```cpp
#include <atomic>
#include <vector>
#include <cstring>

struct RenderCommand {
    enum Type { DrawMesh, SetMaterial, SetTransform, Clear };
    Type type;
    union {
        struct { unsigned mesh_id; unsigned material_id; } draw;
        struct { float mat[16]; } transform;
        struct { float r, g, b, a; } clear;
    };
};

class DoubleBufferedCommandList {
    alignas(64) RenderCommand buffers_[2][4096]; // 两个 4096 命令的缓冲区
    alignas(64) std::atomic<uint32_t> write_count_{0};
    alignas(64) std::atomic<uint32_t> read_index_{0};  // 0 或 1

public:
    // CPU 线程：写入命令到后台缓冲区
    RenderCommand* begin_write() {
        uint32_t back = 1 - read_index_.load(std::memory_order_acquire);
        write_count_.store(0, std::memory_order_relaxed);
        return buffers_[back];
    }

    void end_write(uint32_t count) {
        write_count_.store(count, std::memory_order_release);
    }

    // 交换缓冲区（帧边界调用）
    void swap() {
        uint32_t current = read_index_.load(std::memory_order_acquire);
        read_index_.store(1 - current, std::memory_order_release);
    }

    // GPU 线程：读取前缓冲区命令
    uint32_t begin_read(const RenderCommand*& commands) {
        uint32_t front = read_index_.load(std::memory_order_acquire);
        commands = buffers_[front];
        return write_count_.load(std::memory_order_acquire);
    }
};
```

---

## 3. 练习

### 练习 1（必做）：为 Job System 添加 `parallel_for` 支持

在 `JobSystem` 类中实现一个 `run_parallel` 方法，接受一个 `std::function<void(int)>` 和一个范围 `[0, N)`，自动将范围拆分为子 Job，使用 `submit_child` 构建一棵 Job 树：

```
Root Job（等待所有子 Job）
 ├── Sub Job: [0, N/4)
 ├── Sub Job: [N/4, N/2)
 ├── Sub Job: [N/2, 3N/4)
 └── Sub Job: [3N/4, N)
```

验证：创建一个 100 万元素的数组，使用 `parallel_for` 填充每个元素的平方，使用 `wait` 等待完成，验证结果正确。

### 练习 2（必做）：为 `PinnedThreadPool` 添加 benchmark 对比

编写一个 benchmark，比较：
1. 未设置 affinity 的线程池
2. 设置了 affinity 的线程池
3. 使用 `std::async` 的版本

每种方式执行 1000 次矩阵乘法（4x4 矩阵，每个任务做 10 万次乘法），测量总耗时。分析结果差异的原因。

### 练习 3（可选·挑战）：实现 Fiber 协作式调度器

在单个线程内实现一个微型 Fiber 调度器：

1. 定义 `Fiber` 结构（栈指针、状态）。
2. 实现 `create_fiber(func)`、`yield()`、`resume(fiber)`。
3. 用汇编（`__asm__` 或 `__asm`）实现 `switch_context(from, to)` 保存/恢复 `rsp`、`rbp`、`rbx`、`r12-r15`（x86-64 callee-saved 寄存器）。
4. 实现一个简单的生产者-消费者 demo：两个 Fiber 通过共享队列协作。

---

## 4. 扩展阅读

- **[必读]** *Game Engine Architecture (3rd ed.)* — Jason Gregory，第 7 章 "Concurrency and Parallelism"，详述 Naughty Dog 的 Fiber-based Job System 设计
- **[必读]** *C++ Concurrency in Action (2nd ed.)* — Anthony Williams，第 9 章 "Advanced thread management"（线程池实现），第 10 章 "Parallel algorithms"
- **[推荐]** "The Task-based Parallelism Model in Unreal Engine 4" — CppCon 2016 演讲，UE4 的 Task Graph 系统
- **[推荐]** "Parallelizing the Naughty Dog Engine Using Fibers" — Christian Gyrling（GDC 2015），业界标杆的 Fiber Job System 实践
- **[推荐]** `Taskflow`（https://github.com/taskflow/taskflow） — 现代 C++ 任务并行库，源码值得学习
- **[进阶]** "Is Parallel Programming Hard, And, If So, What Can You Do About It?" — Paul McKenney（免费在线），第 5 章工作窃取分析
- **[工具]** ThreadSanitizer（`-fsanitize=thread`），编译时加上此标志运行程序，自动检测数据竞争

---

## 常见陷阱

### 陷阱 1：在主线程的循环中 `join()` 而非使用持久化 Worker 线程

```cpp
// ❌ 错误：每帧创建/销毁线程
void game_loop_bad() {
    while (running) {
        std::thread t1(update_physics);
        std::thread t2(update_ai);
        t1.join(); t2.join(); // 每次 join 后线程销毁，下一帧重新创建
        render();
    }
}
```

每帧创建线程的开销：内核对象分配 + 新栈分配 + TLB flush。在 16.6ms 帧预算中，这些开销可能占 1-2ms。

```cpp
// ✅ 正确：启动时创建 Worker，循环复用
class GameLoop {
    std::vector<std::thread> workers_;
    std::atomic<bool> running_{true};
public:
    GameLoop() {
        for (int i = 0; i < num_workers; ++i)
            workers_.emplace_back(&GameLoop::worker_main, this);
    }
    void frame() {
        submit_jobs();
        wait_all_jobs(); // 同步点
    }
};
```

### 陷阱 2：忘记 `thread_local` 分配器导致全局锁竞争

```cpp
// ❌ 错误：每帧在 Worker 线程中调用全局 new
void worker_bad() {
    while (running) {
        auto* data = new TempData;  // malloc 内部的全局锁 → 所有线程排队
        process(data);
        delete data;
    }
}

// ✅ 正确：使用 thread_local 帧分配器
void worker_good() {
    thread_local FrameAllocator alloc(64 * 1024); // 每线程 64KB
    while (running) {
        auto* data = alloc.allocate<TempData>();  // 仅移动指针，零锁
        process(data);
        alloc.reset(); // 帧末一次性释放
    }
}
```

### 陷阱 3：子 Job 完成后访问已被释放的父 Job

```cpp
// ❌ 错误：父 Job 在栈上，子 Job 完成后可能已出作用域
void submit_bad(JobSystem& js) {
    Job parent;
    parent.func = []{ /* ... */ };
    Job child;
    child.parent = &parent;     // parent 在栈上
    js.submit_child(&parent, &child);
} // parent 被销毁！但 child 可能还在执行
  // → child 完成后 fetch_sub(&parent->unfinished) → 悬垂指针 → UB

// ✅ 正确：所有 Job 从预分配的池中分配，生命周期由 JobSystem 管理
class JobSystem {
    Job* alloc_job() { return job_pool_.allocate(); }
    // Job 的生命周期 > 最后一次访问它的时间
};
```

### 陷阱 4：在 Worker 线程中直接修改 ECS 组件

```cpp
// ❌ 错误：多 Worker 同时迭代 Entity，可能发生读写冲突
void physics_bad() {
    parallel_for(0, entity_count, [&](int i) {
        auto& transform = registry.get<Transform>(entities[i]);
        transform.position += velocity * dt; // 如果其他 Worker 在同时读...
    });
}
// 这在"只写不读"的场景是安全的，但一旦有读-改-写，就需要同步

// ✅ 正确：预先拆分数据，每个 Worker 处理不相交的子集
// 或使用命令队列，Worker 提交修改命令，主线程在同步点批量应用
```

### 陷阱 5：过度分解 Job 导致调度开销淹没实际工作

```cpp
// ❌ 错误：每个元素一个 Job
for (int i = 0; i < 1000000; ++i) {
    js.submit(make_job([]{ tiny_work(); })); // 100 万个 Job！
}
// 每个 Job 的入队/出队成本 ~100ns，100 万 Job = 100ms 调度开销
// 实际工作可能只需 50ms → 调度开销 2 倍于工作

// ✅ 正确：合并为适当粒度的 Job
// 经验规则：每个 Job 至少 1000-10000 次迭代的工作量
constexpr int CHUNK_SIZE = 4096;
for (int i = 0; i < 1000000; i += CHUNK_SIZE) {
    int end = std::min(i + CHUNK_SIZE, 1000000);
    js.submit(make_job([i, end]{ work_range(i, end); }));
}
```
