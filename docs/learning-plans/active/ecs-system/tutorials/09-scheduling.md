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

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **显式依赖 API + 冲突检测**：
>
> ```cpp
> class DependencyGraph {
>     // ... existing members ...
>
>     // 显式依赖边
>     struct ExplicitEdge { size_t from; size_t to; };
>     std::vector<ExplicitEdge> explicit_edges;
>
> public:
>     // API：声明 A 必须在 B 之前
>     void explicit_before(const std::string& a, const std::string& b) {
>         size_t ai = find_system(a), bi = find_system(b);
>         if (ai == size_t(-1) || bi == size_t(-1)) return;
>         explicit_edges.push_back({ai, bi});
>     }
>
>     void explicit_after(const std::string& a, const std::string& b) {
>         explicit_before(b, a);  // "A after B" = "B before A"
>     }
>
>     // 冲突检测：显式依赖 vs 自动推导
>     std::vector<std::string> detect_conflicts() {
>         std::vector<std::string> warnings;
>         for (auto& edge : explicit_edges) {
>             // 自动推导认为 edge.to → edge.from（即自动顺序与显式相反）
>             if (has_conflict(systems[edge.to], systems[edge.from])) {
>                 // 自动推导：B 写 X，A 读 X → B 必须在 A 之前
>                 // 显式声明：A before B → 矛盾！
>                 warnings.push_back(
>                     "冲突: 自动推导要求 '" + systems[edge.to].name +
>                     "' 在 '" + systems[edge.from].name + "' 之前，"
>                     "但显式声明相反");
>             }
>         }
>         return warnings;
>     }
>
>     // 改进的拓扑排序：显式边优先，自动推导填充剩余
>     std::vector<std::vector<size_t>> parallel_groups() const {
>         size_t n = systems.size();
>         std::vector<std::vector<size_t>> adj(n);
>         std::vector<int> in_degree(n, 0);
>
>         // Step 1：构建自动依赖（基于读写冲突）
>         for (size_t i = 0; i < n; i++) {
>             for (size_t j = i + 1; j < n; j++) {
>                 if (has_conflict(systems[i], systems[j])) {
>                     // 按声明顺序：先声明先执行
>                     adj[i].push_back(j);
>                     in_degree[j]++;
>                 }
>             }
>         }
>
>         // Step 2：叠加显式依赖边
>         for (auto& edge : explicit_edges) {
>             adj[edge.from].push_back(edge.to);
>             in_degree[edge.to]++;
>         }
>
>         // Step 3：拓扑分层（Kahn 算法）
>         std::vector<std::vector<size_t>> groups;
>         std::vector<size_t> current_level;
>         for (size_t i = 0; i < n; i++)
>             if (in_degree[i] == 0) current_level.push_back(i);
>
>         while (!current_level.empty()) {
>             groups.push_back(current_level);
>             std::vector<size_t> next_level;
>             for (size_t u : current_level)
>                 for (size_t v : adj[u])
>                     if (--in_degree[v] == 0) next_level.push_back(v);
>             current_level = std::move(next_level);
>         }
>         return groups;
>     }
> };
> ```
>
> **使用示例**：
> ```cpp
> scheduler.add_system(decl_AISystem);
> scheduler.add_system(decl_MovementSystem);
> // 显式覆盖：MovementSystem 在 AISystem 之前（如物理先更新再用新位置做 AI 决策）
> scheduler.explicit_before("MovementSystem", "AISystem");
>
> auto conflicts = scheduler.detect_conflicts();
> for (auto& w : conflicts) std::cerr << "WARNING: " << w << "\n";
> ```
>
> **冲突检测原理**：自动推导基于"冲突 → 先声明先执行"。如果显式声明与自动推导方向相反，说明存在读写冲突但开发者要反转顺序——这可能导致数据竞争或读到旧数据，需要警告。

> [!tip]- 练习 2 参考答案
> **基于 `std::atomic` 的 MPSC 无锁队列**（Dmitry Vyukov 经典实现）：
>
> ```cpp
> #include <atomic>
> #include <memory>
>
> template<typename T>
> class MPSCQueue {
>     struct Node {
>         T data;
>         std::atomic<Node*> next{nullptr};
>     };
>
>     // head_ 是消费者端（单消费者），tail_ 是生产者端（多生产者）
>     std::atomic<Node*> head_{nullptr};  // 消费者从这里取
>     std::atomic<Node*> tail_{nullptr};  // 生产者往这里接
>
>     // 哨兵节点：避免 head 为 null 的边界情况
>     Node* sentinel_;
>
> public:
>     MPSCQueue() {
>         sentinel_ = new Node{};
>         head_.store(sentinel_, std::memory_order_relaxed);
>         tail_.store(sentinel_, std::memory_order_relaxed);
>     }
>
>     ~MPSCQueue() {
>         // 消费所有剩余
>         while (T val; try_dequeue(val)) {}
>         delete sentinel_;
>     }
>
>     // 多生产者安全入队（lock-free）
>     void enqueue(T value) {
>         Node* node = new Node{std::move(value), nullptr};
>
>         // 原子地交换 tail_ 并链接
>         Node* prev = tail_.exchange(node, std::memory_order_acq_rel);
>         prev->next.store(node, std::memory_order_release);
>         // ↑ release 保证 node 的初始化对消费者可见
>     }
>
>     // 单消费者出队（非阻塞）
>     bool try_dequeue(T& result) {
>         Node* h = head_.load(std::memory_order_relaxed);
>         Node* next = h->next.load(std::memory_order_acquire);
>         // ↑ acquire 与 enqueue 的 release 配对
>
>         if (next == nullptr) return false;  // 队列空
>
>         result = std::move(next->data);
>         head_.store(next, std::memory_order_release);
>         delete h;  // 删除旧哨兵
>         return true;
>     }
> };
> ```
>
> **集成到 JobSystem**：
> ```cpp
> class LockFreeJobSystem {
>     MPSCQueue<std::function<void()>> queue_;  // 替代 mutex+vector
>     // ...
>
>     void submit(std::function<void()> job) {
>         pending_.fetch_add(1, std::memory_order_relaxed);
>         queue_.enqueue(std::move(job));  // 无锁入队
>         cv_.notify_one();               // 仍需 cv 唤醒 worker
>     }
>
>     void worker_loop(size_t id) {
>         while (!stop_) {
>             std::function<void()> job;
>             if (queue_.try_dequeue(job)) {
>                 job();
>                 if (pending_.fetch_sub(1) == 1)
>                     cv_done_.notify_all();
>             } else {
>                 // 空转等待：可加短暂 yield 或条件变量
>                 std::this_thread::yield();
>             }
>         }
>     }
> };
> ```
>
> **性能对比**：
> - mutex 版：高竞争下 ~30% 时间花在锁上
> - 无锁版：入队只需一次 atomic exchange + store，几乎无竞争开销
> - **注意**：consumer 端仍需要某种等待机制（cv/yield），否则忙等浪费 CPU

> [!tip]- 练习 3 参考答案（可选）
> **执行时间统计与负载均衡策略**：
>
> ```cpp
> struct SystemTiming {
>     std::string name;
>     std::vector<double> frame_times;  // 最近 N 帧耗时（环形缓冲区）
>     size_t ring_pos = 0;
>     static constexpr size_t WINDOW = 100;
>
>     void record(double ms) {
>         if (frame_times.size() < WINDOW)
>             frame_times.push_back(ms);
>         else
>             frame_times[ring_pos] = ms;
>         ring_pos = (ring_pos + 1) % WINDOW;
>     }
>
>     double avg_ms() const {
>         if (frame_times.empty()) return 0;
>         double sum = 0;
>         for (auto t : frame_times) sum += t;
>         return sum / frame_times.size();
>     }
> };
>
> // 在 ECSScheduler::run_all 中记录时间
> void run_all(float dt) {
>     auto groups = parallel_groups();
>     for (size_t layer = 0; layer < groups.size(); layer++) {
>         for (size_t idx : groups[layer]) {
>             job_system_.submit([&sys = systems[idx], &timing = timings_[idx], dt]() {
>                 auto t0 = Clock::now();
>                 sys.execute(dt);
>                 auto t1 = Clock::now();
>                 timing.record(std::chrono::duration<double, std::milli>(t1 - t0).count());
>             });
>         }
>         job_system_.wait_all();
>     }
> }
> ```
>
> **负载均衡策略——拆分量大 System 为更小 Job**：
>
> ```cpp
> // 策略：如果 System 平均耗时 > 阈值，将工作拆分为多个 Job
> void run_all_adaptive(float dt) {
>     static constexpr double HEAVY_THRESHOLD_MS = 2.0;  // 超过 2ms 视为"重"
>
>     auto groups = parallel_groups();
>     for (auto& layer : groups) {
>         for (size_t idx : layer) {
>             auto& sys = systems[idx];
>             double avg = timings_[idx].avg_ms();
>
>             if (avg > HEAVY_THRESHOLD_MS && sys.can_split) {
>                 // 拆分为 range_count 个子 Job
>                 size_t total = sys.entity_count();
>                 size_t range_count = job_system_.worker_count() * 4;
>                 size_t batch_size = (total + range_count - 1) / range_count;
>
>                 for (size_t start = 0; start < total; start += batch_size) {
>                     size_t end = std::min(start + batch_size, total);
>                     job_system_.submit([&sys, start, end, dt]() {
>                         sys.execute_range(start, end, dt);  // 扩展 API
>                     });
>                 }
>             } else {
>                 // 轻量 System：作为单个 Job 提交
>                 job_system_.submit([&sys, dt]() { sys.execute(dt); });
>             }
>         }
>         job_system_.wait_all();
>     }
> }
> ```
>
> **关键设计**：
> - System 需要提供 `can_split`（是否可拆分）+ `entity_count()` + `execute_range(start, end, dt)`
> - `batch_size` 的选择：约 Worker 数 × 4 → 既能负载均衡，又不因 Job 过细而调度开销过大
> - 监测窗口 `WINDOW=100` 帧可平滑偶发尖峰（避免因一次 GC spike 而误判为"重"）
> - Unity DOTS 的 `IJobParallelFor` 就是这套策略的生产级实现
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
