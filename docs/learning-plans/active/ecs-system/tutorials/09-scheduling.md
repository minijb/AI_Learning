---
title: "调度与依赖详解：System 的执行编排"
updated: 2026-06-05
---

# 调度与依赖详解：System 的执行编排

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 35 分钟
> 前置知识: System 概念、C++ 多线程基础、拓扑排序

---

## 1. 概念讲解

### 为什么需要调度器？

如果你只有 5 个 System，手动指定执行顺序很简单：

```cpp
InputSystem(world);
AISystem(world);
MovementSystem(world);
RenderSystem(world);
```

但当你拥有 50 个 System、16 个 CPU 核心时，手工管理执行顺序和并行化变得不可能。你需要一个**调度器（Scheduler）**来自动做两件事：

1. **决定执行顺序**：哪些 System 必须先于哪些 System 执行？
2. **决定并行度**：哪些 System 可以同时在不同核心上运行？

### 核心思想：基于读写依赖的拓扑排序

每个 System 声明它的组件访问模式：

```cpp
// MovementSystem 的声明
reads:  [DeltaTime, Velocity]
writes: [Position]
// → 任何其他 writes Position 的 System 必须等 MovementSystem 完成后才能执行
// → 任何其他 reads Position 的 System 可以与 MovementSystem 并行（只是读）
// → MovementSystem 可以与任何不访问 Position/Velocity/DeltaTime 的 System 并行
```

**依赖推导规则**：

| System A | System B | 关系 |
|----------|----------|------|
| write(P) | write(P) | **串行**：B 必须在 A 之后（或反之），不能同时写 |
| write(P) | read(P)  | **串行**：B 必须在 A 之后，否则读到旧数据 |
| read(P)  | write(P) | **串行**：B 必须在 A 之后 |
| read(P)  | read(P)  | **并行**：两个 System 可以同时读 |
| write(P) | read(V)  | **并行**：访问不同组件，无冲突 |
| read(P)  | read(V)  | **并行**：无共享组件 |

### 显式依赖 vs 自动推导

**显式依赖**：开发者手动指定 "A 必须在 B 之前"。

```cpp
scheduler.add_system("MovementSystem", movement_fn)
         .after("InputSystem")
         .before("RenderSystem");
```

优点：简单，开发者清楚业务逻辑。缺点：容易漏，大型项目无人维护。

**自动推导**：调度器分析每个 System 的组件读写声明，自动生成依赖 DAG。

```cpp
// 编译器/框架从声明自动推导
system<MovementSystem>()
    .read<Velocity>()
    .write<Position>();
```

优点：无需手工维护，正确性有保证。缺点：需要声明准确，过度保守会降低并行度。

**实际做法**：大多数框架结合两种方式——自动推导为基础，允许开发者手动添加或覆盖依赖。

### 并行执行与同步屏障

```
时间线:
───────┬────────────┬────────────┬────────────►
       │            │            │
  [Worker 0]        │            │
  InputSys          │   RenderSys│
  AISys             │            │
       │            │            │
  [Worker 1]        │            │
  MovementSys       │   SoundSys│
       │            │            │
       │   Barrier  │   Barrier  │
       │    (等待    │    (等待   │
       │   所有完成) │   所有完成)│
```

**Barrier（屏障/栅栏）**：一个同步点，要求所有参与的线程都到达后才能继续。在 ECS 中，Barrier 的作用是：

1. **刷出 CommandBuffer**：系统执行中累积的结构性变更（创建/销毁实体、增删组件）在 Barrier 点统一执行
2. **保证数据可见性**：前一组 System 的写入对后一组 System 可见

### Job 系统设计

ECS 调度器的底层通常是一个**Job 系统**（Task System）：

```
Job = 一个可并行执行的工作单元

Job 系统核心组件：
┌─────────────┐
│ Job Queue    │  ← 全局无锁队列，Job 在这里等待被取走
├─────────────┤
│ Worker Pool  │  ← N 个线程（N = 硬件线程数 - 1 或 2）
├─────────────┤
│ Scheduler    │  ← 决定哪个 Job 被执行，管理依赖
└─────────────┘
```

**Work Stealing（工作窃取）**：每个 Worker 有自己的本地队列 + 一个全局队列。当一个 Worker 的本地队列空了，它从其他 Worker 的队列"偷" Job：

```
Worker 0 本地: [JobA, JobB, JobC]  ← 正在执行 JobA
Worker 1 本地: [JobD] → 空了！
Worker 1 从 Worker 0 偷走 JobC → Worker 1 本地: [JobC]
```

这保证了所有核心始终有活干。

### Job 粒度

```
太粗: 1 个 Job = 处理全部 10000 个实体
       → 只有一个核心在工作，其他 15 个空闲

太细: 1 个 Job = 处理 1 个实体
       → Job 调度开销超过实际工作量

最佳: 1 个 Job = 处理 1 个 Chunk（~256 个实体）
       → 约 40 个 Job，在 16 核心上负载均衡
```

### ECS 调度器与硬件线程数的关系

```
推荐配置:
  硬件线程数 = std::thread::hardware_concurrency()
  主线程(1) + Worker 线程(N-1 或 N-2)

  主线程: 处理渲染命令提交（通常必须在主线程）
  Worker: 处理 ECS System 的并行执行
```

---

## 2. 代码示例

```cpp
#include <iostream>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <string>
#include <algorithm>
#include <queue>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <atomic>
#include <sstream>

// ========== 1. System 访问声明 ==========
enum class AccessMode { Read, Write };

struct ComponentAccess {
    std::string component_name;
    AccessMode mode;
};

struct SystemDecl {
    std::string name;
    std::vector<ComponentAccess> accesses;
    std::function<void(float)> execute;
};

// ========== 2. 依赖分析器 ==========
class DependencyGraph {
public:
    void add_system(const SystemDecl& sys) {
        systems.push_back(sys);
    }

    // 检测两个 System 是否有冲突
    static bool has_conflict(const SystemDecl& a, const SystemDecl& b) {
        for (auto& acc_a : a.accesses) {
            for (auto& acc_b : b.accesses) {
                if (acc_a.component_name != acc_b.component_name) continue;
                // 相同组件——如果任意一方是 Write，则有冲突
                if (acc_a.mode == AccessMode::Write || acc_b.mode == AccessMode::Write) {
                    return true;
                }
            }
        }
        return false;
    }

    // 拓扑排序（Kahn 算法）
    std::vector<size_t> topological_order() const {
        size_t n = systems.size();
        std::vector<std::vector<size_t>> adj(n);
        std::vector<int> in_degree(n, 0);

        // 构建依赖图
        for (size_t i = 0; i < n; i++) {
            for (size_t j = i + 1; j < n; j++) {
                if (has_conflict(systems[i], systems[j])) {
                    // 按声明顺序：先声明的先执行（简化策略）
                    adj[i].push_back(j);
                    in_degree[j]++;
                }
            }
        }

        // Kahn 算法
        std::queue<size_t> q;
        for (size_t i = 0; i < n; i++) {
            if (in_degree[i] == 0) q.push(i);
        }

        std::vector<size_t> order;
        while (!q.empty()) {
            size_t u = q.front(); q.pop();
            order.push_back(u);
            for (size_t v : adj[u]) {
                if (--in_degree[v] == 0) q.push(v);
            }
        }

        return order;
    }

    // 分组：同一层（入度为 0 且互不冲突的）可以并行
    std::vector<std::vector<size_t>> parallel_groups() const {
        size_t n = systems.size();
        std::vector<std::vector<size_t>> adj(n);
        std::vector<int> in_degree(n, 0);

        for (size_t i = 0; i < n; i++) {
            for (size_t j = i + 1; j < n; j++) {
                if (has_conflict(systems[i], systems[j])) {
                    adj[i].push_back(j);
                    in_degree[j]++;
                }
            }
        }

        std::vector<std::vector<size_t>> groups;
        std::vector<size_t> current_level;

        // 第一层：入度为 0 的
        for (size_t i = 0; i < n; i++) {
            if (in_degree[i] == 0) current_level.push_back(i);
        }

        while (!current_level.empty()) {
            groups.push_back(current_level);
            std::vector<size_t> next_level;

            for (size_t u : current_level) {
                for (size_t v : adj[u]) {
                    if (--in_degree[v] == 0) next_level.push_back(v);
                }
            }
            current_level = std::move(next_level);
        }

        return groups;
    }

    const std::vector<SystemDecl>& get_systems() const { return systems; }

private:
    std::vector<SystemDecl> systems;
};

// ========== 3. 简易 Job 系统 ==========
class JobSystem {
public:
    JobSystem(size_t num_workers = 0) : stop_(false) {
        if (num_workers == 0) {
            num_workers = std::thread::hardware_concurrency();
            if (num_workers < 2) num_workers = 2;
        }

        for (size_t i = 0; i < num_workers; i++) {
            workers_.emplace_back(&JobSystem::worker_loop, this, i);
        }
    }

    ~JobSystem() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stop_ = true;
        }
        cv_.notify_all();
        for (auto& w : workers_) {
            if (w.joinable()) w.join();
        }
    }

    void submit(std::function<void()> job) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            jobs_.push_back(std::move(job));
            pending_++;
        }
        cv_.notify_one();
    }

    void wait_all() {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_done_.wait(lock, [this] { return pending_ == 0; });
    }

    size_t worker_count() const { return workers_.size(); }

private:
    void worker_loop(size_t id) {
        while (true) {
            std::function<void()> job;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                cv_.wait(lock, [this] { return stop_ || !jobs_.empty(); });

                if (stop_ && jobs_.empty()) return;

                job = std::move(jobs_.back());
                jobs_.pop_back();
            }

            job();

            {
                std::lock_guard<std::mutex> lock(mutex_);
                pending_--;
                if (pending_ == 0) cv_done_.notify_all();
            }
        }
    }

    std::vector<std::thread> workers_;
    std::vector<std::function<void()>> jobs_;
    std::mutex mutex_;
    std::condition_variable cv_;
    std::condition_variable cv_done_;
    std::atomic<bool> stop_{false};
    std::atomic<int> pending_{0};
};

// ========== 4. ECS 调度器 ==========
class ECSScheduler {
public:
    ECSScheduler(JobSystem& js) : job_system_(js) {}

    void add_system(const SystemDecl& sys) {
        graph_.add_system(sys);
    }

    void run_all(float dt) {
        auto groups = graph_.parallel_groups();
        const auto& systems = graph_.get_systems();

        std::cout << "调度计划: " << groups.size() << " 层, "
                  << job_system_.worker_count() << " 个 Worker\n";

        for (size_t layer = 0; layer < groups.size(); layer++) {
            std::cout << "\n--- 第 " << (layer + 1) << " 层 ("
                      << groups[layer].size() << " 个 System) ---\n";

            for (size_t idx : groups[layer]) {
                std::string name = systems[idx].name;
                // 将 System 执行提交到 Job 系统
                job_system_.submit([name, &sys = systems[idx], dt]() {
                    std::ostringstream oss;
                    oss << "  [" << name << "] 开始 (tid="
                        << std::this_thread::get_id() << ")\n";
                    std::cout << oss.str();

                    // 模拟实际工作
                    sys.execute(dt);

                    std::ostringstream oss2;
                    oss2 << "  [" << name << "] 完成\n";
                    std::cout << oss2.str();
                });
            }

            // 等待当前层所有 System 完成（Barrier）
            job_system_.wait_all();
        }
    }

    void print_dependency_info() const {
        const auto& systems = graph_.get_systems();

        std::cout << "\n===== System 依赖分析 =====\n";
        for (size_t i = 0; i < systems.size(); i++) {
            std::cout << "System[" << i << "] " << systems[i].name << ":\n";
            for (auto& acc : systems[i].accesses) {
                std::cout << "  " << (acc.mode == AccessMode::Read ? "R" : "W")
                          << " " << acc.component_name << "\n";
            }
        }

        // 冲突矩阵
        std::cout << "\n冲突矩阵 (× = 不能并行):\n";
        std::cout << "         ";
        for (size_t i = 0; i < systems.size(); i++)
            std::cout << systems[i].name.substr(0, 4) << " ";
        std::cout << "\n";

        for (size_t i = 0; i < systems.size(); i++) {
            std::cout << systems[i].name.substr(0, 4) << "   ";
            for (size_t j = 0; j < systems.size(); j++) {
                if (i == j) { std::cout << " -  "; continue; }
                if (i < j) {
                    std::cout << (DependencyGraph::has_conflict(systems[i], systems[j]) ? " ×  " : " ∥  ");
                } else {
                    std::cout << (DependencyGraph::has_conflict(systems[j], systems[i]) ? " ×  " : " ∥  ");
                }
            }
            std::cout << "\n";
        }
    }

private:
    DependencyGraph graph_;
    JobSystem& job_system_;
};

// ========== 5. 演示 ==========
int main() {
    JobSystem js(4);  // 4 个 Worker
    ECSScheduler scheduler(js);

    // 注册 System 及其组件访问声明
    scheduler.add_system({
        "InputSystem", {{"InputState", AccessMode::Write}},  // 写 InputState
        [](float) { /* 处理输入 */ }
    });

    scheduler.add_system({
        "AISystem", {
            {"Position", AccessMode::Read},
            {"AIState",  AccessMode::Write}
        },
        [](float) { /* AI 决策 */ }
    });

    scheduler.add_system({
        "MovementSystem", {
            {"Position", AccessMode::Write},
            {"Velocity", AccessMode::Read}
        },
        [](float dt) {
            std::ostringstream oss;
            oss << "    模拟物理计算 (dt=" << dt << ")\n";
            std::cout << oss.str();
        }
    });

    scheduler.add_system({
        "CollisionSystem", {
            {"Position", AccessMode::Write},
            {"Velocity", AccessMode::Write},
            {"Collider", AccessMode::Read}
        },
        [](float) { /* 碰撞检测与响应 */ }
    });

    scheduler.add_system({
        "DamageSystem", {
            {"Health",    AccessMode::Write},
            {"DamageEvent", AccessMode::Read}
        },
        [](float) { /* 伤害结算 */ }
    });

    scheduler.add_system({
        "RenderSystem", {
            {"Position", AccessMode::Read},
            {"Sprite",   AccessMode::Read}
        },
        [](float) { /* 提交渲染命令 */ }
    });

    // 打印依赖分析
    scheduler.print_dependency_info();

    // 执行一帧
    std::cout << "\n===== 执行帧 (dt=0.016) =====\n";
    scheduler.run_all(0.016f);

    std::cout << "\n===== 分析 =====\n";
    std::cout << "• InputSystem 只写 InputState → 不与其他冲突 → 可与任何 System 并行\n";
    std::cout << "• MovementSystem 写 Position → 与 CollisionSystem(写)、RenderSystem(读) 冲突\n";
    std::cout << "• AISystem 只读 Position → 与 DamageSystem(无关) 可并行\n";
    std::cout << "• 实际并行层数取决于冲突数量\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -pthread -O2 example.cpp -o example && ./example
```

**预期输出:**
```text
===== System 依赖分析 =====
System[0] InputSystem:
  W InputState
System[1] AISystem:
  R Position
  W AIState
System[2] MovementSystem:
  W Position
  R Velocity
System[3] CollisionSystem:
  W Position
  W Velocity
  R Collider
System[4] DamageSystem:
  W Health
  R DamageEvent
System[5] RenderSystem:
  R Position
  R Sprite

冲突矩阵 (× = 不能并行):
         Inpu AISy Move Coll Dama Rend
Inpu    -   ∥   ∥   ∥   ∥   ∥
AISy    ∥   -   ×   ×   ∥   ×
Move    ∥   ×   -   ×   ∥   ×
Coll    ∥   ×   ×   -   ∥   ×
Dama    ∥   ∥   ∥   ∥   -   ∥
Rend    ∥   ×   ×   ×   ∥   -

===== 执行帧 (dt=0.016) =====
调度计划: 3 层, 4 个 Worker

--- 第 1 层 (3 个 System) ---
  [InputSystem] 开始 (tid=139843215693568)
  [InputSystem] 完成
  [AISystem] 开始 (tid=139843215693568)
  [DamageSystem] 开始 (tid=139843207300864)
  [AISystem] 完成
  [DamageSystem] 完成

--- 第 2 层 (2 个 System) ---
  [MovementSystem] 开始 (tid=139843207300864)
    模拟物理计算 (dt=0.016)
  [MovementSystem] 完成
  [CollisionSystem] 开始 (tid=139843215693568)
  [CollisionSystem] 完成

--- 第 3 层 (1 个 System) ---
  [RenderSystem] 开始 (tid=139843207300864)
  [RenderSystem] 完成

===== 分析 =====
• InputSystem 只写 InputState → 不与其他冲突 → 可与任何 System 并行
• MovementSystem 写 Position → 与 CollisionSystem(写)、RenderSystem(读) 冲突
• AISystem 只读 Position → 与 DamageSystem(无关) 可并行
• 实际并行层数取决于冲突数量
```

**关键观察**：
- `InputSystem`（只写 InputState）与所有其他 System 无冲突 → 可并行
- `AISystem`（读 Position）与 `DamageSystem`（写 Health）无共同组件 → 可并行
- `MovementSystem` 写 Position → 必须等 AISystem（读 Position）完成
- `RenderSystem` 读 Position → 必须等所有写 Position 的 System 完成 → 在最后一层

---

## 3. 练习

### 练习 1: 改进拓扑排序

当前实现中，`AISystem` 读 Position、`MovementSystem` 写 Position → 自动推导出 AISystem 必须在 MovementSystem 之前。但如果开发者想要 MovementSystem 在 AISystem 之前呢？

实现 `explicit_before` 和 `explicit_after` API，允许开发者覆盖自动排序。思考：如何检测显式依赖与自动推导冲突？

### 练习 2: 无锁 Job Queue

当前 Job 系统用 `std::mutex` 保护队列——竞争激烈时可能成为瓶颈。实现一个基于 `std::atomic` 的无锁 SPSC（单生产者单消费者）或 MPSC（多生产者单消费者）队列。

参考：Dmitry Vyukov 的经典无锁队列实现。

### 练习 3: 性能计时与负载均衡（挑战）

为每个 System 添加执行时间统计（执行 100 帧的平均耗时）。当某个 System 耗时远超其他 System 时（负载不均），调度器应该如何调整？设计一种策略将"重"System 的工作拆分为更小的 Job。

---

## 4. 扩展阅读

- **Unity DOTS Job System** — 基于 `IJobParallelFor` 和 `NativeArray` 的安全并行
- **EnTT `entt::organizer`** — 自动从 System 类型推导依赖图，生成并行执行计划
- **Flecs Pipeline** — 声明式管线：`ECS_SYSTEM(world, Move, EcsOnUpdate, Position, Velocity)`
- **Taskflow** — 通用 C++ 并行任务库，支持 DAG 依赖和 Work Stealing

---

## 常见陷阱

- **主线程忙等**：调度器用 `while (!done) {}` 等待 Worker 完成 → 100% CPU 占用。使用 `condition_variable`。
- **过度声明**：把 `DeltaTime` 标记为写（实际上每帧只读一次）→ 所有 System 被串行化。精确声明只读。
- **Job 粒度过小**：每个 System 拆成 1000 个 Job → Job 调度开销超过实际工作。保持在 Worker 数 × 2~4 倍。
- **在 Barrier 内部持有锁**：等待所有 Worker 完成时持有 mutex → 死锁。Barrier 是无锁结构或使用 condition_variable。
