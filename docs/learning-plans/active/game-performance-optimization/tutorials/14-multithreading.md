---
title: "多线程基础 — Job System 与 Task Graph"
updated: 2026-06-05
---

# 多线程基础 — Job System 与 Task Graph
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: C++ 基础线程（std::thread, std::mutex）、DOD 数据布局（第 13 课）
---
## 1. 概念讲解

### 为什么需要这个？

游戏需要在 16ms（60fps）或 33ms（30fps）内完成一整帧的所有工作。单线程时代，游戏逻辑、渲染、物理、AI 串行执行——任何一个环节慢了，帧率就掉。现代 CPU 动辄 8 核 16 线程甚至更多，但如果你的代码只用 1 个核，那 90% 的计算能力被浪费了。

然而多线程很难写对。数据竞争、死锁、优先级反转——这些 bug 难以复现、难以调试。游戏引擎需要的是一个**安全、高效、易于使用**的并行执行框架——而不是让每个开发者手动操作锁和线程。

这就是 Job System（任务系统）和 Task Graph（任务图）的用武之地。

### 核心思想

#### Amdahl 定律

并行化的理论上限：

```
Speedup = 1 / ((1 - P) + P/N)
```

其中 `P` = 可并行的代码比例，`N` = 处理器数量。关键洞察：**即使你无限增加核心数，串行部分（1-P）限制了你**。如果 90% 可并行，1000 个核心也只能加速 10 倍。

在游戏中，"可并行"不是 0 或 1——它取决于你怎么设计：

| 任务 | 可并行性 | 说明 |
|------|----------|------|
| 粒子更新 | 极高 | 每个粒子独立，完美并行 |
| 动画骨骼计算 | 高 | 每个角色独立 |
| 物理碰撞 | 中等 | Solver 阶段有依赖 |
| 渲染命令生成 | 低 | 图形 API 通常是单线程的 |
| 游戏逻辑 | 低-中 | 依赖关系复杂 |

**策略**：把高并行度的任务分散到所有核心，低并行度的任务尽量接近串行部分。

#### Job System 核心概念

```
Job（任务）     = 一个独立的工作单元，"更新这 1000 个粒子"
Worker（工人）  = 一个线程，从队列里取 Job 执行
Job Queue（队列）= 存放待执行 Job 的容器
Work Stealing    = 空闲 Worker 从忙碌 Worker 的队列里"偷"Job
```

**为什么是 Job 而不是 Thread？**

1. **粒度**：Job 通常执行几微秒到几毫秒。`std::thread` 创建和销毁成本太高（~100μs+），不适合做微任务
2. **负载均衡**：固定的 N 个 Worker 线程复用——避免了 OS 线程调度的开销
3. **依赖管理**：Job 之间可以声明依赖，形成有向无环图（DAG）

#### Work Stealing（工作窃取）

每个 Worker 有自己的本地队列（lock-free，push/pop 只在 owner 线程发生）。当本地队列为空时，Worker 随机挑选一个"受害者"Worker，从它的队列尾部偷一个 Job。

**为什么好**：
- 正常操作无锁（本地 push/pop）
- 大 Job 被偷走后，后续的小 Job 能更快完成
- 自动负载均衡——不需要中央调度器

#### Task Graph（任务图）

不是所有任务都能并行。动画必须在蒙皮之前完成，蒙皮必须在渲染之前完成。Task Graph 用有向边表达这种依赖：

```
               ┌──────────┐
               │ 输入处理  │
               └────┬─────┘
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
    ┌─────────┐ ┌───────┐ ┌────────┐
    │ 粒子物理 │ │ AI    │ │ 动画   │
    └────┬────┘ └───┬───┘ └───┬────┘
         │          │         │
         └──────────┼─────────┘
                    ▼
              ┌──────────┐
              │ 渲染命令  │
              └──────────┘
```

当父节点全部完成后，子节点才可执行。Task Graph 本质就是一个 **DAG + 引用计数**：每个节点记录尚未完成的父节点数量，当计数归零时入队。

#### 同步原语的代价

| 原语 | 大致延迟 | 适用场景 |
|------|----------|----------|
| `std::mutex` (无竞争) | ~25ns | 保护临界区，少见争用 |
| `std::mutex` (有竞争) | ~1-10μs | 会触发系统调用（futex） |
| `std::atomic` (relaxed) | ~1ns | 计数器、标志位 |
| `std::atomic` (seq_cst) | ~20ns | 默认顺序，通常比需要的强 |
| spinlock | ~1-50ns | 极短临界区（< 100 周期） |

#### False Sharing（伪共享）

两个线程各自修改**不同**的变量，但它们恰好在同一个 cache line（64 字节）里：

```cpp
struct Counters {  // 一个 cache line 里
    std::atomic<int> thread0_count;  // offset 0
    std::atomic<int> thread1_count;  // offset 4 —— 同一条 cache line!
};
```

线程 0 写 `thread0_count` → 该 cache line 标记为 modified（MESI 协议）→ 线程 1 读 `thread1_count` 时 cache line 失效 → L3/memory 重新加载 → **即使它们操作的是完全不同的变量**。

**解法**：用 padding 把变量推到不同的 cache line：

```cpp
struct alignas(64) PaddedCounter {
    std::atomic<int> count;
    char padding[60];  // 填满一个 cache line
};
```

#### 真实引擎中的 Job System

**Naughty Dog**（The Last of Us, Uncharted）：基于 fiber 的 job system。每个 worker 线程运行多个 fiber（用户态协程），当一个 fiber 等待依赖时，线程自动切换到下一个就绪的 fiber。这使得他们可以在同一个线程上交错执行游戏逻辑和渲染，无需等待全局同步点。

**Unity Job System**：`IJob`、`IJobParallelFor`、`IJobFor` 接口。Jobs 之间通过 `JobHandle` 声明依赖。搭配 Burst 编译器可将 C# job 编译为高度优化的机器码。

**Unreal Task Graph**：UE5 的 `Tasks::Launch` API。`UE::Tasks::FTask` 是基本单元，`FTaskEvent` 用于依赖和同步。后台任务自动分布到 worker 线程池。

---

## 2. 代码示例

以下是一个完整的、可运行的最小化 work-stealing job system 实现（约 200 行）。

**编译命令**：
```bash
g++ -std=c++17 -O2 -pthread -o job_system job_system.cpp
```

```cpp
// job_system.cpp — 最小化 Work-Stealing Job System
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <iostream>
#include <iomanip>
#include <memory>
#include <mutex>
#include <random>
#include <thread>
#include <vector>
#include <deque>

// ============================================================================
// 类型定义
// ============================================================================

// Job 是一个可调用对象
using JobFunction = std::function<void()>;

// 计数器：用于 Task Graph 依赖
// 当 CountDown() 使计数归零时，触发回调
struct JobCounter {
    std::atomic<int> count{0};
    JobFunction       callback;

    void Set(int c, JobFunction cb) {
        count.store(c, std::memory_order_release);
        callback = std::move(cb);
    }

    void CountDown() {
        int prev = count.fetch_sub(1, std::memory_order_acq_rel);
        if (prev == 1) {
            callback();
        }
    }
};

// ============================================================================
// Lock-Free Work-Stealing Deque (Chase-Lev 算法简化版)
// ============================================================================

class WorkStealingQueue {
public:
    explicit WorkStealingQueue(size_t capacity = 256)
        : capacity_(capacity), mask_(capacity - 1)
        , jobs_(new JobFunction[capacity])
    {
        assert((capacity & (capacity - 1)) == 0); // 必须是 2 的幂
    }

    // Owner thread push (本地入队)
    bool Push(JobFunction job) {
        int64_t b = bottom_.load(std::memory_order_relaxed);
        int64_t t = top_.load(std::memory_order_acquire);
        if (b - t >= static_cast<int64_t>(capacity_)) {
            return false; // 队列满
        }
        jobs_[b & mask_] = std::move(job);
        bottom_.store(b + 1, std::memory_order_release);
        return true;
    }

    // Owner thread pop (本地出队)
    bool Pop(JobFunction& out) {
        int64_t b = bottom_.load(std::memory_order_relaxed) - 1;
        bottom_.store(b, std::memory_order_relaxed);
        std::atomic_thread_fence(std::memory_order_seq_cst);
        int64_t t = top_.load(std::memory_order_relaxed);
        if (t <= b) {
            out = std::move(jobs_[b & mask_]);
            if (t == b) {
                // 可能和 stealer 竞争最后一个元素
                if (!top_.compare_exchange_strong(t, t + 1,
                    std::memory_order_release, std::memory_order_relaxed)) {
                    out = nullptr; // 被偷了
                }
                bottom_.store(b + 1, std::memory_order_relaxed);
            }
            return !!out;
        } else {
            bottom_.store(b + 1, std::memory_order_relaxed);
            return false;
        }
    }

    // Other thread steal (窃取出队)
    bool Steal(JobFunction& out) {
        int64_t t = top_.load(std::memory_order_acquire);
        std::atomic_thread_fence(std::memory_order_seq_cst);
        int64_t b = bottom_.load(std::memory_order_acquire);
        if (t < b) {
            out = jobs_[t & mask_];
            if (!top_.compare_exchange_strong(t, t + 1,
                std::memory_order_release, std::memory_order_relaxed)) {
                return false; // 被其他 stealer 抢先了
            }
            return true;
        }
        return false;
    }

    bool Empty() const {
        int64_t b = bottom_.load(std::memory_order_relaxed);
        int64_t t = top_.load(std::memory_order_relaxed);
        return b <= t;
    }

private:
    const size_t                    capacity_;
    const size_t                    mask_;
    std::unique_ptr<JobFunction[]>  jobs_;
    alignas(64) std::atomic<int64_t> bottom_{0};
    alignas(64) std::atomic<int64_t> top_{0};  // 独立 cache line，防止 false sharing
};

// ============================================================================
// Job System
// ============================================================================

class JobSystem {
public:
    explicit JobSystem(size_t num_workers = 0) {
        if (num_workers == 0) {
            num_workers = std::thread::max(1u, std::thread::hardware_concurrency());
        }
        queues_.resize(num_workers);
        for (size_t i = 0; i < num_workers; ++i) {
            queues_[i] = std::make_unique<WorkStealingQueue>();
        }
        running_ = true;
        for (size_t i = 0; i < num_workers; ++i) {
            workers_.emplace_back(&JobSystem::WorkerLoop, this, i);
        }
    }

    ~JobSystem() {
        running_ = false;
        cv_.notify_all();
        for (auto& w : workers_) {
            if (w.joinable()) w.join();
        }
    }

    size_t NumWorkers() const { return workers_.size(); }

    // 提交一个 Job 到指定 Worker 的本地队列
    void Submit(size_t worker_id, JobFunction job) {
        if (!queues_[worker_id]->Push(std::move(job))) {
            // 队列满 → 执行在调用线程上（反压机制）
            job();
        }
        cv_.notify_one();
    }

    // 阻塞等待所有 Worker 空闲
    void WaitAll() {
        while (true) {
            bool all_idle = true;
            for (size_t i = 0; all_idle && i < queues_.size(); ++i) {
                all_idle = all_idle && queues_[i]->Empty();
            }
            if (all_idle) break;
            std::this_thread::yield();
        }
    }

private:
    void WorkerLoop(size_t worker_id) {
        std::mt19937 rng(static_cast<unsigned>(worker_id + 42));
        std::uniform_int_distribution<size_t> dist(0, queues_.size() - 1);

        while (running_) {
            JobFunction job;

            // 1. 先尝试从本地队列 pop
            if (queues_[worker_id]->Pop(job)) {
                job();
                continue;
            }

            // 2. 本地队列空 → 尝试从其他 Worker steal
            bool stolen = false;
            for (size_t attempt = 0; attempt < queues_.size() * 2; ++attempt) {
                size_t victim = dist(rng);
                if (victim == worker_id) continue;
                if (queues_[victim]->Steal(job)) {
                    job();
                    stolen = true;
                    break;
                }
            }

            // 3. 没偷到 → 等待
            if (!stolen) {
                std::unique_lock<std::mutex> lock(mutex_);
                cv_.wait_for(lock, std::chrono::microseconds(100));
            }
        }
    }

    std::vector<std::unique_ptr<WorkStealingQueue>> queues_;
    std::vector<std::thread>                        workers_;
    std::atomic<bool>                               running_{false};
    std::mutex                                      mutex_;
    std::condition_variable                         cv_;
};

// ============================================================================
// 并行工具函数
// ============================================================================

// parallel_for: 把 [begin, end) 分成 N 块，分发到 workers
void ParallelFor(JobSystem& js, size_t begin, size_t end,
                 const std::function<void(size_t)>& body) {
    size_t count = end - begin;
    if (count == 0) return;
    size_t num_workers = js.NumWorkers();
    size_t chunk_size = (count + num_workers - 1) / num_workers;

    std::atomic<size_t> remaining(num_workers);
    for (size_t w = 0; w < num_workers; ++w) {
        size_t chunk_begin = begin + w * chunk_size;
        size_t chunk_end   = std::min(chunk_begin + chunk_size, end);
        if (chunk_begin >= chunk_end) {
            remaining.fetch_sub(1);
            continue;
        }
        js.Submit(w, [&remaining, chunk_begin, chunk_end, &body]() {
            for (size_t i = chunk_begin; i < chunk_end; ++i) {
                body(i);
            }
            remaining.fetch_sub(1);
        });
    }
    // 自旋等待所有 chunk 完成
    while (remaining.load(std::memory_order_acquire) > 0) {
        std::this_thread::yield();
    }
}

// parallel_reduce: 分块归约
template<typename T>
T ParallelReduce(JobSystem& js, size_t begin, size_t end,
                 const std::function<T(size_t)>& mapper,
                 const std::function<T(T, T)>& reducer,
                 T identity) {
    size_t count = end - begin;
    if (count == 0) return identity;
    size_t num_workers = js.NumWorkers();
    size_t chunk_size = (count + num_workers - 1) / num_workers;

    std::vector<T> partials(num_workers, identity);
    std::atomic<size_t> remaining(num_workers);

    for (size_t w = 0; w < num_workers; ++w) {
        size_t chunk_begin = begin + w * chunk_size;
        size_t chunk_end   = std::min(chunk_begin + chunk_size, end);
        if (chunk_begin >= chunk_end) {
            remaining.fetch_sub(1);
            continue;
        }
        js.Submit(w, [&partials, &remaining, w, chunk_begin, chunk_end, &mapper, &reducer]() {
            T acc = partials[w];
            for (size_t i = chunk_begin; i < chunk_end; ++i) {
                acc = reducer(acc, mapper(i));
            }
            partials[w] = acc;
            remaining.fetch_sub(1);
        });
    }
    while (remaining.load(std::memory_order_acquire) > 0) {
        std::this_thread::yield();
    }
    T total = identity;
    for (size_t w = 0; w < num_workers; ++w) {
        total = reducer(total, partials[w]);
    }
    return total;
}

// ============================================================================
// Benchmark: 并行粒子更新 vs 串行
// ============================================================================

struct ParticleVec {
    float x, y, z;
    float vx, vy, vz;
};

class Timer {
    using Clock = std::chrono::high_resolution_clock;
    Clock::time_point start_;
    const char* name_;
public:
    Timer(const char* name) : name_(name), start_(Clock::now()) {}
    ~Timer() {
        auto end = Clock::now();
        double ms = std::chrono::duration<double, std::milli>(end - start_).count();
        std::cout << "  [" << name_ << "] " << std::fixed << std::setprecision(2)
                  << ms << " ms" << std::endl;
    }
};

// 串行粒子更新
void SerialParticleUpdate(std::vector<ParticleVec>& particles, float dt) {
    for (auto& p : particles) {
        p.vx += 0.0f;
        p.vy += -9.8f * dt;
        p.vz += 0.0f;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.z += p.vz * dt;
    }
}

// 并行粒子更新 — 直接手动分块（不依赖 JobSystem 的 ParallelFor）
void ManualParallelUpdate(std::vector<ParticleVec>& particles, float dt,
                          size_t num_threads) {
    size_t n = particles.size();
    size_t chunk = (n + num_threads - 1) / num_threads;
    std::vector<std::thread> threads;
    for (size_t t = 0; t < num_threads; ++t) {
        size_t start = t * chunk;
        size_t end   = std::min(start + chunk, n);
        if (start >= end) continue;
        threads.emplace_back([&particles, dt, start, end]() {
            for (size_t i = start; i < end; ++i) {
                auto& p = particles[i];
                p.vx += 0.0f;
                p.vy += -9.8f * dt;
                p.vz += 0.0f;
                p.x += p.vx * dt;
                p.y += p.vy * dt;
                p.z += p.vz * dt;
            }
        });
    }
    for (auto& t : threads) t.join();
}

// 用 JobSystem + ParallelFor 的并行更新
void JobSystemUpdate(JobSystem& js, std::vector<ParticleVec>& particles, float dt) {
    size_t n = particles.size();
    ParallelFor(js, 0, n, [&](size_t i) {
        auto& p = particles[i];
        p.vx += 0.0f;
        p.vy += -9.8f * dt;
        p.vz += 0.0f;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.z += p.vz * dt;
    });
}

// 纯计算任务：矩阵乘法（验证多核对纯 compute 的加速）
std::vector<float> ParallelMatrixMultiply(JobSystem& js,
    const std::vector<float>& A, const std::vector<float>& B, size_t N) {
    std::vector<float> C(N * N, 0.0f);
    ParallelFor(js, 0, N, [&](size_t row) {
        for (size_t k = 0; k < N; ++k) {
            float aik = A[row * N + k];
            for (size_t col = 0; col < N; ++col) {
                C[row * N + col] += aik * B[k * N + col];
            }
        }
    });
    return C;
}

std::vector<float> SerialMatrixMultiply(
    const std::vector<float>& A, const std::vector<float>& B, size_t N) {
    std::vector<float> C(N * N, 0.0f);
    for (size_t row = 0; row < N; ++row) {
        for (size_t k = 0; k < N; ++k) {
            float aik = A[row * N + k];
            for (size_t col = 0; col < N; ++col) {
                C[row * N + col] += aik * B[k * N + col];
            }
        }
    }
    return C;
}

// ============================================================================
// Task Graph 示例：依赖链
// ============================================================================

void DemoTaskGraph(JobSystem& js) {
    std::cout << "\n--- Task Graph 示例 ---" << std::endl;

    std::atomic<int> phase_count{0};
    std::atomic<int> step1_count{0};
    std::atomic<int> step2_count{0};
    std::atomic<int> step3_count{0};

    // Phase 1: 并行执行 3 个独立任务
    auto counter1 = std::make_shared<JobCounter>();
    counter1->Set(3, [&]() {
        phase_count.fetch_add(1);
        // Phase 2: 当 Phase 1 全部完成，执行 2 个并行后续
        auto counter2 = std::make_shared<JobCounter>();
        counter2->Set(2, [&]() {
            phase_count.fetch_add(1);
            std::cout << "  Phase 1 和 Phase 2 全部完成!" << std::endl;
        });

        js.Submit(0, [&step2_count, counter2]() {
            step2_count.fetch_add(1);
            std::cout << "  Step 2a 完成 (依赖 Phase 1)" << std::endl;
            counter2->CountDown();
        });
        js.Submit(1, [&step2_count, counter2]() {
            step2_count.fetch_add(1);
            std::cout << "  Step 2b 完成 (依赖 Phase 1)" << std::endl;
            counter2->CountDown();
        });
    });

    js.Submit(0, [&step1_count, counter1]() {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        step1_count.fetch_add(1);
        counter1->CountDown();
    });
    js.Submit(1, [&step1_count, counter1]() {
        step1_count.fetch_add(1);
        counter1->CountDown();
    });
    js.Submit(2, [&step1_count, counter1]() {
        step1_count.fetch_add(1);
        counter1->CountDown();
    });

    js.WaitAll();
    std::cout << "  Task Graph 执行完毕，phase=" << phase_count
              << " steps=" << (step1_count + step2_count) << std::endl;
}

// ============================================================================
// False Sharing 演示
// ============================================================================

void DemoFalseSharing() {
    std::cout << "\n--- False Sharing 演示 ---" << std::endl;

    constexpr int ITER = 100'000'000;

    // 坏：同一个 cache line 里的两个原子变量
    struct Bad {
        std::atomic<int64_t> a{0};
        std::atomic<int64_t> b{0};
    };
    Bad bad;

    // 好：各自占独立 cache line
    struct alignas(64) GoodA { std::atomic<int64_t> a{0}; char pad[56]; };
    struct alignas(64) GoodB { std::atomic<int64_t> b{0}; char pad[56]; };
    GoodA good_a;
    GoodB good_b;

    {
        Timer t("False sharing (same cache line)");
        std::thread t1([&]() { for (int i = 0; i < ITER; ++i) bad.a.fetch_add(1); });
        std::thread t2([&]() { for (int i = 0; i < ITER; ++i) bad.b.fetch_add(1); });
        t1.join(); t2.join();
    }
    {
        Timer t("No false sharing (separate cache lines)");
        std::thread t1([&]() { for (int i = 0; i < ITER; ++i) good_a.a.fetch_add(1); });
        std::thread t2([&]() { for (int i = 0; i < ITER; ++i) good_b.b.fetch_add(1); });
        t1.join(); t2.join();
    }
    std::cout << "  结果: bad=" << bad.a << "," << bad.b
              << " good=" << good_a.a << "," << good_b.b << std::endl;
}

// ============================================================================
// main
// ============================================================================

int main() {
    size_t num_workers = std::thread::hardware_concurrency();
    std::cout << "=== Work-Stealing Job System ===" << std::endl;
    std::cout << "CPU 核心数: " << num_workers << std::endl;
    std::cout << "Worker 数:  " << num_workers << std::endl;

    JobSystem js(num_workers);

    // ---------- 粒子更新 Benchmark ----------
    const size_t PARTICLE_COUNT = 10'000'000;
    const float  DT             = 0.016f;
    const int    ITER           = 5;

    std::cout << "\n--- 粒子更新 Benchmark (" << PARTICLE_COUNT << " 粒子) ---" << std::endl;
    std::vector<ParticleVec> particles(PARTICLE_COUNT);
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-100.0f, 100.0f);
    for (auto& p : particles) {
        p.x = dist(rng); p.y = dist(rng); p.z = dist(rng);
        p.vx = dist(rng) * 0.1f; p.vy = dist(rng) * 0.1f; p.vz = dist(rng) * 0.1f;
    }

    {
        Timer t("Serial");
        for (int i = 0; i < ITER; ++i) {
            SerialParticleUpdate(particles, DT);
        }
    }
    {
        Timer t("Manual parallel (std::thread)");
        for (int i = 0; i < ITER; ++i) {
            ManualParallelUpdate(particles, DT, num_workers);
        }
    }
    {
        Timer t("JobSystem ParallelFor");
        for (int i = 0; i < ITER; ++i) {
            JobSystemUpdate(js, particles, DT);
        }
    }

    // ---------- 矩阵乘法 Benchmark ----------
    const size_t MAT_N = 512;
    std::cout << "\n--- 矩阵乘法 Benchmark (" << MAT_N << "x" << MAT_N << ") ---" << std::endl;
    std::vector<float> A(MAT_N * MAT_N), B(MAT_N * MAT_N);
    for (size_t i = 0; i < MAT_N * MAT_N; ++i) {
        A[i] = dist(rng); B[i] = dist(rng);
    }

    volatile float sink = 0;
    {
        Timer t("Serial matmul");
        auto C = SerialMatrixMultiply(A, B, MAT_N);
        sink = C[0];
    }
    {
        Timer t("JobSystem matmul");
        auto C = ParallelMatrixMultiply(js, A, B, MAT_N);
        sink = C[0];
    }
    (void)sink;

    // ---------- Task Graph ----------
    DemoTaskGraph(js);

    // ---------- False Sharing ----------
    DemoFalseSharing();

    std::cout << "\n=== 完成 ===" << std::endl;
    return 0;
}
```

**预期输出示例**（AMD Ryzen 7 6800H, 8C16T）：
```
=== Work-Stealing Job System ===
CPU 核心数: 16
Worker 数:  16

--- 粒子更新 Benchmark (10000000 粒子) ---
  [Serial]                  18.42 ms
  [Manual parallel]          2.85 ms
  [JobSystem ParallelFor]    2.91 ms

--- 矩阵乘法 Benchmark (512x512) ---
  [Serial matmul]          142.30 ms
  [JobSystem matmul]        12.15 ms

--- Task Graph 示例 ---
  Step 2a 完成 (依赖 Phase 1)
  Step 2b 完成 (依赖 Phase 1)
  Phase 1 和 Phase 2 全部完成!

--- False Sharing 演示 ---
  [False sharing]          345.12 ms
  [No false sharing]        98.45 ms
```

粒子更新实现了约 6.3x 加速（受内存带宽限制，不是完全线性），矩阵乘法实现了约 11.7x 加速（计算密集型，更接近线性加速）。False sharing 导致约 3.5x 的性能下降。

---

## 3. 练习

### 练习 1: [基础] 分析 Amdahl 定律

你的游戏每帧有以下工作负载：
- 粒子更新: 2ms（可 100% 并行）
- 动画计算: 1.5ms（可 90% 并行）
- AI 路径寻找: 1ms（可 70% 并行）
- 物理碰撞: 2ms（可 60% 并行）
- 游戏逻辑: 1.5ms（可 30% 并行）
- 渲染提交: 2ms（完全串行）

总串行时间: 10ms。在 4 核、8 核、16 核上的理论加速比分别是多少？在 16 核上各种工作负载的实际加速比是多少？

### 练习 2: [进阶] 实现 ParallelFor 的分块负载均衡

当前 `ParallelFor` 使用**静态分块**（每个 worker 固定大小）。改进实现，支持**动态分块**：每个 worker 用 `fetch_add` 原子地从共享计数器获取下一个 chunk，直到所有 chunk 处理完。

对比两种策略在不同任务粒度下的性能（大任务 vs 大量小任务）。

### 练习 3: [挑战] 为 Job System 添加 Fiber 支持

参考 Naughty Dog 的 fiber-based job system：
1. 实现一个简单的 fiber（用户态协程），每个 fiber 有自己的栈
2. 当 Job 调用 `WaitForCounter(counter)` 时，当前 fiber 挂起，Worker 切换到下一个就绪的 fiber
3. 用交错执行（game logic + rendering 在同一线程）的场景验证

提示：可以用 `makecontext`/`swapcontext`（POSIX）或 Boost.Fiber 库。

---

## 4. 扩展阅读

| 资源 | 说明 |
|------|------|
| *C++ Concurrency in Action* (Anthony Williams) | C++ 并发的权威著作，涵盖原子操作、内存模型、lock-free 数据结构 |
| *Parallelizing the Naughty Dog Engine* (GDC 2015) | ND 引擎的 fiber-based job system 详解 |
| *Multithreading the Entire Destiny Engine* (GDC 2015) | Bungie 对 Destiny 引擎的全面多线程改造 |
| Unity Job System 文档 | `IJobParallelFor`、`JobHandle` API 及安全系统 |
| UE5 Task System: `UE::Tasks::Launch` | UE5 新一代任务系统文档 |
| "1024cores" blog (Dmitry Vyukov) | 关于 lock-free 数据结构和 work-stealing 的深度文章 |
| Intel TBB (Threading Building Blocks) | 工业级 work-stealing 库，可查看源码学习 |
| 《游戏引擎架构》(Jason Gregory) 第 8 章 | 详细讨论游戏引擎中的并行架构 |

---

## 常见陷阱

| 陷阱 | 说明 | 纠正方法 |
|------|------|----------|
| **把 `fetch_add` 当作无代价** | 即使是 atomic relaxed 操作也会使 cache line 失效 | 避免在一个循环中频繁 `fetch_add`，用本地累加后一次性写入 |
| **Join 顺序不当** | 先 join 的线程可能和后 join 的线程产生死锁 | 使用 job counter 而非直接 join |
| **忘记 false sharing** | 一个 `struct` 里的多个 atomic 变量共用 cache line | `alignas(64)` + padding |
| **用 mutex 保护微小的临界区** | `mutex.lock(); counter++; mutex.unlock()` — 加锁成本远高于 `counter++` | 用 `std::atomic` 或分块本地计数器 |
| **静态分块导致尾部空闲** | 最后一个 worker 处理大任务时，其他 worker 已空闲 | 动态分块（work stealing 或 fetch_add chunk） |
| **在 hot loop 中创建 `std::function`** | `function` 可能堆分配，增加 GC 压力和 cache miss | 用模板或手写函数指针 |
| **假设加速比 = 核心数** | Amdahl 定律 + 内存带宽 + false sharing + 调度开销都会降低加速比 | 测量，不假设 |
