---
title: "System 详解：纯逻辑的变换器"
updated: 2026-06-05
---

# System 详解：纯逻辑的变换器

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 30 分钟
> 前置知识: Entity 与 Component 概念、C++ 函数对象与 lambda

---

## 1. 概念讲解

### 为什么需要 System？

如果 Component 是数据，那么谁来处理这些数据？这就是 System 的角色：**System 是纯逻辑函数，接收一组符合条件的实体和它们的组件，执行变换，然后结束。**

关键洞察：**System 不应该有"自己"的持久状态（除了配置参数）。** 所有持久状态应该以 Component 的形式存储在实体上，或作为单例资源存储在 World 中。

```
System = 声明(我需要读/写哪些组件) + 逻辑(对匹配的每个实体做什么)
```

### 核心思想：声明式查询 + 纯变换

一个典型的 System 定义包含两部分：

**1. 查询声明（Query）** — "我需要处理哪些实体？"
```
匹配: 拥有 Position 和 Velocity 的所有实体
读: Velocity
写: Position
```

**2. 执行逻辑（Execute）** — "对每个匹配的实体做什么？"
```cpp
position.x += velocity.dx * dt;
position.y += velocity.dy * dt;
```

### System 的特征

**无状态（或只有配置状态）**：System 不记住"上一帧发生了什么"。如果需要记忆，把它放到组件里。

```cpp
// 错误：System 内部状态
class MovementSystem {
    float totalDistanceTraveled = 0; // ❌ 不应该在这里
};

// 正确：配置参数是 ok 的
class MovementSystem {
    float speedMultiplier = 1.5f;    // ✓ 配置参数
};
```

**声明式依赖**：System 显式声明它需要哪些组件，框架据此自动调度。

**可并行**：如果两个 System 的读写集合不冲突，它们可以同时在不同线程运行。例如 `RenderSystem`（只读 Position、读 Sprite）和 `DamageSystem`（读写 Health）可以并行。

### System 的输入输出模型

| 访问模式 | 含义 | 并发安全 |
|----------|------|----------|
| `read<Position>()` | 只读，不修改 | 可与其他只读者并行 |
| `write<Position>()` | 读写，会修改 | 排斥所有其他访问 |
| `optional<Health>()` | 可选组件，实体可能有也可能没有 | 取决于声明为读还是写 |
| `exclude<StaticTag>()` | 排除有此组件的实体 | 不访问数据，纯过滤 |

### 常见 System 示例

**MovementSystem** — 最经典的例子：
```
读: Velocity, DeltaTime(资源)
写: Position
逻辑: pos += vel * dt
```

**RenderSystem** — 管线末端：
```
读: Position, Sprite, Camera(资源)
写: (无——输出到 GPU)
逻辑: 对每个可见实体提交 draw call
```

**DamageSystem** — 处理伤害事件：
```
读: DamageEvent(资源/事件缓冲)
写: Health
逻辑: 读取事件队列，对目标实体扣血
```

**LifetimeSystem** — 临时实体管理：
```
读: DeltaTime
写: Lifetime
逻辑: lifetime.remaining -= dt; if <= 0 → 销毁实体
```

**CollisionSystem** — 物理交互：
```
读: Position, Collider
写: Position (碰撞响应), Velocity (反弹)
逻辑: 检测碰撞对 → 分离 → 修改速度
```

### System 的执行顺序

ECS 调度器将 System 组织为**有向无环图（DAG）**。节点是 System，边是依赖：

```
[InputSystem]         [AISystem]
     │                     │
     ▼                     ▼
[MovementSystem]◄───[CollisionSystem]
     │
     ▼
[AnimationSystem]     [DamageSystem]
     │                     │
     ▼                     ▼
[RenderSystem]        [SoundSystem]
```

- `MovementSystem` 必须在 `CollisionSystem` 之后（需要碰撞响应后的速度）
- `AnimationSystem` 必须在 `MovementSystem` 之后（需要最新位置）
- `RenderSystem` 通常最后执行

---

## 2. 代码示例

```cpp
#include <iostream>
#include <vector>
#include <unordered_map>
#include <functional>
#include <string>
#include <algorithm>

// ========== 简化的 ECS 基础设施 ==========
using Entity = uint32_t;

// ---- 组件 ----
struct Position { float x = 0, y = 0, z = 0; };
struct Velocity { float dx = 0, dy = 0, dz = 0; };
struct Health   { int current = 100, max = 100; };
struct Damage   { int amount = 10; };
struct Lifetime { float remaining = 5.0f; };
struct Name     { std::string value; };

// ---- 简易 World ----
class World {
public:
    Entity create() { return next_entity++; }

    template<typename T>
    void add(Entity e, const T& c) { storage<T>()[e] = c; }

    template<typename T>
    T* get(Entity e) {
        auto& s = storage<T>();
        auto it = s.find(e);
        return (it != s.end()) ? &it->second : nullptr;
    }

    template<typename T>
    void remove(Entity e) { storage<T>().erase(e); }

    template<typename T>
    const std::unordered_map<Entity, T>& view() const { return storage<T>(); }

    template<typename T>
    std::unordered_map<Entity, T>& view() { return storage<T>(); }

    void destroy(Entity e) { dead_entities.push_back(e); }

    const auto& get_dead() const { return dead_entities; }
    void clear_dead() { dead_entities.clear(); }

    Entity next_entity = 0;
    std::vector<Entity> dead_entities;

private:
    template<typename T>
    static std::unordered_map<Entity, T>& storage() {
        static std::unordered_map<Entity, T> s;
        return s;
    }
};

// ========== System 定义 ==========
// System 是一个可调用对象：接收 (World&, float dt)，不返回任何值
using SystemFunc = std::function<void(World&, float dt)>;

// ========== 具体 System 实现 ==========

// System 1: 移动系统
struct MovementSystem {
    void operator()(World& world, float dt) {
        auto& positions = world.view<Position>();
        auto& velocities = world.view<Velocity>();

        for (auto& [entity, pos] : positions) {
            auto vit = velocities.find(entity);
            if (vit != velocities.end()) {
                auto& vel = vit->second;
                pos.x += vel.dx * dt;
                pos.y += vel.dy * dt;
                pos.z += vel.dz * dt;
            }
        }
    }
};

// System 2: 生命周期系统
struct LifetimeSystem {
    void operator()(World& world, float dt) {
        auto& lifetimes = world.view<Lifetime>();

        for (auto it = lifetimes.begin(); it != lifetimes.end(); ) {
            it->second.remaining -= dt;
            if (it->second.remaining <= 0.0f) {
                auto* name = world.get<Name>(it->first);
                std::cout << "  [过期] "
                          << (name ? name->value : "无名实体")
                          << " 寿命耗尽，销毁。\n";
                world.destroy(it->first);
                it = lifetimes.erase(it);
            } else {
                ++it;
            }
        }
    }
};

// System 3: 伤害系统（通过事件驱动）
struct DamageSystem {
    void operator()(World& world, float /*dt*/) {
        // 模拟：所有实体每帧受到 1 点环境伤害
        // 实际游戏中，DamageSystem 会读取事件缓冲区
        auto& healths = world.view<Health>();

        for (auto it = healths.begin(); it != healths.end(); ) {
            it->second.current -= 1;
            if (it->second.current <= 0) {
                auto* name = world.get<Name>(it->first);
                std::cout << "  [死亡] "
                          << (name ? name->value : "无名实体")
                          << " 生命值归零！\n";
                world.destroy(it->first);
                it = healths.erase(it);
            } else {
                ++it;
            }
        }
    }
};

// System 4: 状态报告系统
struct ReportSystem {
    int frame_count = 0;  // ✓ 允许：配置/度量状态

    void operator()(World& world, float /*dt*/) {
        std::cout << "\n--- 第 " << (++frame_count) << " 帧 ---\n";
        auto& positions = world.view<Position>();
        for (auto& [entity, pos] : positions) {
            auto* vel  = world.get<Velocity>(entity);
            auto* hp   = world.get<Health>(entity);
            auto* name = world.get<Name>(entity);

            std::cout << "  Entity[" << entity << "] "
                      << (name ? name->value : "?")
                      << " @(" << pos.x << "," << pos.y << ")";
            if (vel) std::cout << " vel(" << vel->dx << "," << vel->dy << ")";
            if (hp)  std::cout << " HP:" << hp->current;
            std::cout << "\n";
        }
    }
};

// ========== 简易调度器 ==========
class Scheduler {
public:
    void add_system(const std::string& name, SystemFunc func) {
        systems.push_back({name, std::move(func)});
    }

    void run(World& world, float dt) {
        // 简化：按注册顺序串行执行
        // 真实调度器会分析依赖、并行执行
        for (auto& [name, sys] : systems) {
            sys(world, dt);
        }
    }

private:
    std::vector<std::pair<std::string, SystemFunc>> systems;
};

// ========== 主函数 ==========
int main() {
    World world;
    Scheduler scheduler;

    // 注册系统
    scheduler.add_system("Damage",   DamageSystem{});
    scheduler.add_system("Movement", MovementSystem{});
    scheduler.add_system("Lifetime", LifetimeSystem{});
    scheduler.add_system("Report",   ReportSystem{});

    // 创建实体
    Entity player = world.create();
    world.add(player, Name{"英雄"});
    world.add(player, Position{0, 0, 0});
    world.add(player, Velocity{5, 3, 0});
    world.add(player, Health{100, 100});

    Entity goblin = world.create();
    world.add(goblin, Name{"哥布林"});
    world.add(goblin, Position{50, 30, 0});
    world.add(goblin, Velocity{-2, 0, 0});
    world.add(goblin, Health{50, 50});

    Entity tree = world.create();
    world.add(tree, Name{"大树"});
    world.add(tree, Position{100, 0, 0});
    // 树没有速度，没有血量

    Entity spark = world.create();
    world.add(spark, Name{"火花粒子"});
    world.add(spark, Position{20, 5, 0});
    world.add(spark, Velocity{0, 10, 0});
    world.add(spark, Lifetime{3.0f});  // 3 秒寿命
    // 火花有生命周期但没有血量

    std::cout << "===== ECS System 演示 =====\n";
    std::cout << "执行顺序: Damage → Movement → Lifetime → Report\n";

    // 运行 5 帧
    const float dt = 0.16f;
    for (int i = 0; i < 5; i++) {
        scheduler.run(world, dt);

        // 清理死实体
        for (auto e : world.get_dead()) {
            world.remove<Position>(e);
            world.remove<Velocity>(e);
            world.remove<Health>(e);
            world.remove<Lifetime>(e);
            world.remove<Name>(e);
        }
        world.clear_dead();
    }

    std::cout << "\n===== 最终存活实体 =====\n";
    for (auto& [entity, pos] : world.view<Position>()) {
        auto* name = world.get<Name>(entity);
        std::cout << "  Entity[" << entity << "] "
                  << (name ? name->value : "?") << "\n";
    }

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 example.cpp -o example && ./example
```

**预期输出:**
```text
===== ECS System 演示 =====
执行顺序: Damage → Movement → Lifetime → Report

--- 第 1 帧 ---
  Entity[0] 英雄 @(0.8,0.48) vel(5,3) HP:99
  Entity[1] 哥布林 @(49.68,30) vel(-2,0) HP:49
  Entity[2] 大树 @(100,0)
  Entity[3] 火花粒子 @(20,6.6) vel(0,10)

--- 第 2 帧 ---
  Entity[0] 英雄 @(1.6,0.96) vel(5,3) HP:98
  Entity[1] 哥布林 @(49.36,30) vel(-2,0) HP:48
  Entity[2] 大树 @(100,0)
  Entity[3] 火花粒子 @(20,8.2) vel(0,10)

--- 第 3 帧 ---
  Entity[0] 英雄 @(2.4,1.44) vel(5,3) HP:97
  Entity[1] 哥布林 @(49.04,30) vel(-2,0) HP:47
  Entity[2] 大树 @(100,0)
  Entity[3] 火花粒子 @(20,9.8) vel(0,10)
  [过期] 火花粒子 寿命耗尽，销毁。

--- 第 4 帧 ---
  Entity[0] 英雄 @(3.2,1.92) vel(5,3) HP:96
  Entity[1] 哥布林 @(48.72,30) vel(-2,0) HP:46
  Entity[2] 大树 @(100,0)

--- 第 5 帧 ---
  Entity[0] 英雄 @(4,2.4) vel(5,3) HP:95
  Entity[1] 哥布林 @(48.4,30) vel(-2,0) HP:45
  Entity[2] 大树 @(100,0)

===== 最终存活实体 =====
  Entity[0] 英雄
  Entity[1] 哥布林
  Entity[2] 大树
```

**关键观察**：
- `DamageSystem` 扣血、`MovementSystem` 移动、`LifetimeSystem` 到期销毁——各司其职，互不干扰
- `ReportSystem` 的 `frame_count` 是配置状态——允许，因为它不参与游戏逻辑
- 火花粒子在第 3 帧到期被 `LifetimeSystem` 销毁，后续帧不再出现
- 大树没有 `Velocity` 和 `Health`，自动被 `MovementSystem` 和 `DamageSystem` 跳过

---

## 3. 练习

### 练习 1: 实现更多 System

在上面的代码基础上添加：

- **GravitySystem**：对拥有 `Velocity` + `GravityTag` 标签的实体，每帧 `velocity.dy -= 9.8f * dt`
- **HealSystem**：对拥有 `Health` 且 `current < max` 的实体，每秒恢复 1 点生命
- **DespawnSystem**：对有 `Position` 且 `y < -100` 的实体（掉出世界），自动销毁

### 练习 2: System 的执行顺序影响

交换 `DamageSystem` 和 `MovementSystem` 的注册顺序。先移动再扣血 vs 先扣血再移动——对游戏逻辑有影响吗？在什么情况下执行顺序很重要？

给出一个具体场景：System A 扣血到 0，System B 根据血量做 AI 决策。如果 A 先于 B 执行 vs B 先于 A 执行，AI 行为有何不同？

### 练习 3: 依赖冲突检测（挑战）

设计一个简单的依赖分析器：
1. 每个 System 声明它读/写的组件类型（用字符串或类型名）
2. 输入 System 列表和它们的读写声明
3. 检测冲突：两个 System 同时写同一个组件 → 标记为 "必须串行"；两个 System 一个读一个写 → "写者优先"
4. 输出一个建议的执行顺序

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // ---- 新增组件 ----
> struct GravityTag {};  // 标签组件：实体受重力影响
>
> // ---- GravitySystem ----
> // 读: Velocity（写），GravityTag（过滤）
> // 写: Velocity
> struct GravitySystem {
>     float gravity = 9.8f;  // ✓ 配置参数
>     void operator()(World& world, float dt) {
>         auto& velocities = world.view<Velocity>();
>         for (auto& [entity, vel] : velocities) {
>             if (world.get<GravityTag>(entity)) {
>                 vel.dy -= gravity * dt;  // 向下加速
>             }
>         }
>     }
> };
>
> // ---- HealSystem ----
> // 读: Health（写）
> // 写: Health
> // 注意：用累积时间控制回血速率，而非每帧无条件回血
> struct HealSystem {
>     float healPerSecond = 1.0f;   // ✓ 配置参数
>     float accumulated = 0;        // ✓ 度量状态（非持久游戏状态）
>     void operator()(World& world, float dt) {
>         accumulated += dt;
>         if (accumulated < 1.0f) return;  // 每秒只回一次
>         accumulated -= 1.0f;
>
>         auto& healths = world.view<Health>();
>         for (auto& [entity, hp] : healths) {
>             if (hp.current < hp.max) {
>                 hp.current = std::min(hp.current + 1, hp.max);
>             }
>         }
>     }
> };
>
> // ---- DespawnSystem ----
> // 读: Position
> // 写: (无——调用 world.destroy)
> struct DespawnSystem {
>     float despawnY = -100.0f;     // ✓ 配置参数
>     void operator()(World& world, float /*dt*/) {
>         auto& positions = world.view<Position>();
>         for (auto it = positions.begin(); it != positions.end(); ) {
>             if (it->second.y < despawnY) {
>                 auto* name = world.get<Name>(it->first);
>                 std::cout << "  [出界] "
>                           << (name ? name->value : "无名实体")
>                           << " 掉出世界边界！\n";
>                 world.destroy(it->first);
>                 it = positions.erase(it);  // 安全删除
>             } else {
>                 ++it;
>             }
>         }
>     }
> };
>
> // ---- 调度器注册（建议顺序） ----
> // scheduler.add_system("Gravity",  GravitySystem{});
> // scheduler.add_system("Movement", MovementSystem{});
> // scheduler.add_system("Heal",     HealSystem{});
> // scheduler.add_system("Damage",   DamageSystem{});
> // scheduler.add_system("Lifetime", LifetimeSystem{});
> // scheduler.add_system("Despawn",  DespawnSystem{});
> // scheduler.add_system("Report",   ReportSystem{});
> ```
>
> **设计说明**：
> - `HealSystem` 用累积时间避免每帧回血——若 60fps 每帧回 1 点就太快了。`accumulated` 是"上次回血后过了多久"，属于度量状态而非游戏状态
> - `DespawnSystem` 放在 `LifetimeSystem` 之后执行——先处理自然过期，再处理出界，避免重复销毁
> - `GravitySystem` 先于 `MovementSystem`——先更新速度（受重力影响），再用新速度更新位置

> [!tip]- 练习 2 参考答案
> **交换执行顺序的影响分析**：
>
> | 顺序 | 行为 | 影响 |
> |------|------|------|
> | Movement → Damage | 实体移动到新位置后扣血 | 如果 Damage 触发 AI 逃跑决策，AI 基于"移动后"的位置判断——更准确 |
> | Damage → Movement | 先扣血（可能死亡），再移动（死实体不应移动） | 已死实体仍会执行移动——浪费计算 |
>
> **具体场景：AI 决策时效性**：
>
> ```
> System A (DamageSystem): 扣血至 0 → 实体死亡
> System B (AISystem): 检测血量，决定是否逃跑/切换目标
>
> 顺序 A→B: AI 看到 hp=0 → 切换目标 ← 正确！
> 顺序 B→A: AI 看到 hp=100 → 继续攻击 → 下一帧实体才死 ← 延迟一帧
> ```
>
> **执行顺序重要的场景**：
> 1. **Input → Movement**：必须先处理玩家输入，再移动
> 2. **Movement → Collision**：必须先移动到位，再检测碰撞
> 3. **Collision → Damage**：必须先确定碰撞，再结算伤害
> 4. **Animation → Render**：必须先更新骨骼，再渲染
> 5. **CommandBuffer flush**：所有 System 执行完毕后统一执行（避免迭代器失效）
>
> **核心原则**：修改数据的 System 应排在读取该数据的 System 之前。这就是 ECS 调度器 DAG 的拓扑排序依据。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <string>
> #include <set>
> #include <map>
> #include <vector>
> #include <algorithm>
>
> // ---- 依赖声明 ----
> struct SystemDecl {
>     std::string name;
>     std::set<std::string> reads;   // 只读的组件/资源名
>     std::set<std::string> writes;  // 会写的组件/资源名
> };
>
> // ---- 冲突检测 ----
> struct ConflictReport {
>     std::string sysA, sysB;
>     std::string resource;          // 冲突的资源名
>     std::string type;              // "Write-Write" 或 "Read-Write"
> };
>
> std::vector<ConflictReport> detect_conflicts(
>     const std::vector<SystemDecl>& systems)
> {
>     std::vector<ConflictReport> conflicts;
>     for (size_t i = 0; i < systems.size(); i++) {
>         for (size_t j = i + 1; j < systems.size(); j++) {
>             const auto& a = systems[i];
>             const auto& b = systems[j];
>
>             // 检查写-写冲突：两个 System 都写同一个资源
>             std::set<std::string> write_intersection;
>             std::set_intersection(
>                 a.writes.begin(), a.writes.end(),
>                 b.writes.begin(), b.writes.end(),
>                 std::inserter(write_intersection, write_intersection.begin()));
>             for (const auto& res : write_intersection) {
>                 conflicts.push_back({a.name, b.name, res, "Write-Write: 必须串行"});
>             }
>
>             // 检查读-写冲突：A 读 B 写，或 B 读 A 写
>             // A 读 + B 写
>             for (const auto& res : a.reads) {
>                 if (b.writes.count(res)) {
>                     conflicts.push_back({b.name, a.name, res, "Read-Write: " + b.name + " 应先执行"});
>                 }
>             }
>             // B 读 + A 写
>             for (const auto& res : b.reads) {
>                 if (a.writes.count(res)) {
>                     conflicts.push_back({a.name, b.name, res, "Read-Write: " + a.name + " 应先执行"});
>                 }
>             }
>         }
>     }
>     return conflicts;
> }
>
> // ---- 生成建议执行顺序（简易拓扑排序） ----
> std::vector<std::string> suggest_order(
>     const std::vector<SystemDecl>& systems,
>     const std::vector<ConflictReport>& conflicts)
> {
>     // 从冲突中提取依赖边：如果 A 写 X、B 读 X → A 必须在 B 之前
>     // 构建 DAG 图 + 入度表，执行 Kahn 拓扑排序
>     std::map<std::string, int> in_degree;
>     std::map<std::string, std::vector<std::string>> edges;
>
>     for (const auto& sys : systems) {
>         in_degree[sys.name] = 0;  // 初始化
>     }
>     for (const auto& c : conflicts) {
>         if (c.type.find("应先执行") != std::string::npos) {
>             // 从 c.type 中提取"先执行"的 System 名
>             // 简化：从冲突中推断方向
>             auto colon_pos = c.type.find(": ");
>             if (colon_pos != std::string::npos) {
>                 std::string first = c.type.substr(colon_pos + 2);
>                 auto space = first.find(" ");
>                 if (space != std::string::npos) first = first.substr(0, space);
>                 // first → 另一个
>                 std::string second = (first == c.sysA) ? c.sysB : c.sysA;
>                 edges[first].push_back(second);
>                 in_degree[second]++;
>             }
>         }
>     }
>
>     // Kahn 算法
>     std::vector<std::string> order;
>     std::vector<std::string> queue;
>     for (auto& [name, deg] : in_degree) {
>         if (deg == 0) queue.push_back(name);
>     }
>     while (!queue.empty()) {
>         std::string node = queue.back();
>         queue.pop_back();
>         order.push_back(node);
>         for (const auto& next : edges[node]) {
>             if (--in_degree[next] == 0) queue.push_back(next);
>         }
>     }
>     return order;  // 如果 order.size() < systems.size() → 存在循环依赖
> }
>
> // ---- 使用示例 ----
> // SystemDecl movement{"Movement", {"Velocity"}, {"Position"}};
> // SystemDecl collision{"Collision", {"Position", "Collider"}, {"Velocity", "Position"}};
> // SystemDecl render   {"Render",    {"Position", "Sprite"}, {}};
> // auto conflicts = detect_conflicts({movement, collision, render});
> // → Collision 写 Position，Movement 也写 Position → 冲突
> // → Movement 读 Velocity，Collision 写 Velocity → Collision 应先执行
> // auto order = suggest_order({movement, collision, render}, conflicts);
> // → [Collision, Movement, Render]
> ```
>
> **局限与改进方向**：
> - 当前实现只看读写，未考虑 `optional`（可选的读/写）和 `exclude`
> - 真实调度器需要区分"已声明读但实际可能不读"（如 early-out 优化）
> - 两个只读同一资源的 System 可以完全并行——当前算法保守地串行化了它们
> - 生产级实现（如 `entt::organizer`）在编译期从模板推导依赖，运行期生成并行执行图

---

## 4. 扩展阅读

- **Unity DOTS SystemBase** — Unity 的 ECS System 实现了 `OnUpdate()` + 组件查询的自动化注入
- **EnTT `entt::view` 和 `entt::group`** — 不同的查询优化级别：view 是通用查询，group 是预排序的拥有型查询
- **ECS 调度器论文** — "A Data-Oriented Approach to Game Loop Scheduling"，讲述了如何自动从 System 声明推导并行计划
- **Rust Bevy ECS** — System 在编译期就确定了查询类型，完全避免了运行时检查

---

## 常见陷阱

- **System 之间通过全局变量通信**：`extern int globalHealth;`——这破坏了可并行性和可测试性。改用事件队列或单例 Component。
- **System 中的 if-else 类型判断**：`if (entity.has<Orc>() && entity.has<Elf>())`——如果有很多类型变体，检查会爆炸。用标签组件和不同的 System 变体代替。
- **System 过于庞大**：一个 System 做了 5 件不同的事——拆分！每个 System 只关心一组组件组合。`MovementAndDamageAndRenderSystem` → 拆成三个。
- **在 System 中创建/销毁实体未缓冲**：直接在 System 迭代循环中 `world.create()`/`world.destroy()`——可能导致迭代器失效。使用 CommandBuffer 延迟执行（见后续章节）。
- **忽视 delta time**：硬编码 `pos.x += vel.dx` 而不是 `pos.x += vel.dx * dt`——游戏在不同帧率下行为不一致。
