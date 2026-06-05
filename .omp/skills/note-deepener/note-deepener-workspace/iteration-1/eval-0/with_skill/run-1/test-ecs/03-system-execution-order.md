# System 执行顺序与依赖管理

> 基于笔记: drafts/test-ecs.md
> 所属教程: ECS 架构深度剖析
> 章: 3/5

> 回答笔记问题 #1：System 之间的依赖怎么管理？如果 MovementSystem 要先跑，CollisionSystem 要后跑？

## 问题本质

在 ECS 中，System 之间没有"调用关系"——你不能在 `MovementSystem` 里面 `collisionSystem.run()`。所有 System 由 ECS 框架统一调度。那么问题来了：

- `MovementSystem` 必须先执行（更新位置），然后 `CollisionSystem` 才能检测基于新位置的碰撞
- `DamageSystem` 必须在 `CollisionSystem` 检测到碰撞之后、`RenderSystem` 渲染之前执行
- 某些 System 可以并行，某些必须串行

## 方案一：显式依赖声明（Flecs / Unity DOTS）

最工业化的方案是让每个 System **显式声明它依赖哪些 System**。框架根据声明构建依赖图，用拓扑排序确定执行顺序。

### Flecs 的 Pipeline 和 Phase

Flecs 使用 **Pipeline**（管道）概念来组织 System 的执行。Pipeline 将 System 分组到不同的 Phase（阶段）中：

```cpp
// Flecs C++ 中定义 System 的执行阶段和依赖
world.system<Position, const Velocity>("Move")
    .kind(flecs::OnUpdate)     // 在 OnUpdate 阶段执行
    .each([](Position& p, const Velocity& v) {
        p.x += v.x;
        p.y += v.y;
    });

world.system<Position>("Collide")
    .kind(flecs::OnUpdate)     // 同样在 OnUpdate 阶段
    .each([](Position& p) {
        // 碰撞检测
    });
```

Flecs 内置的默认 Pipeline 包含这些阶段（按执行顺序）：

```
OnStart → OnLoad → PostLoad → PreUpdate → OnUpdate → OnValidate → PostUpdate → PreStore → OnStore
```

每个阶段内的 System 按声明的依赖关系排序。如果需要更细粒度的控制：

```cpp
// 显式声明依赖
world.system("Collide")
    .depends_on("Move")     // Collide 依赖 Move，在 Move 之后执行
    .each([](Position& p) { /* ... */ });
```

[来源: Flecs FAQ - What is a pipeline?](https://www.flecs.dev/flecs/md_docs_2FAQ.html)

### Unity DOTS 的 System Group

Unity 的 Entities 包采用类似的思路，但用 C# 属性声明：

```csharp
// Unity DOTS 中定义 System
[UpdateInGroup(typeof(SimulationSystemGroup))]
[UpdateBefore(typeof(CollisionSystem))]   // 在 CollisionSystem 之前执行
public partial class MovementSystem : SystemBase
{
    protected override void OnUpdate()
    {
        Entities.ForEach((ref Translation trans, in Velocity vel) =>
        {
            trans.Value += vel.Value * SystemAPI.Time.DeltaTime;
        }).ScheduleParallel();
    }
}

[UpdateInGroup(typeof(SimulationSystemGroup))]
[UpdateAfter(typeof(MovementSystem))]     // 在 MovementSystem 之后执行
public partial class CollisionSystem : SystemBase { /* ... */ }
```

Unity DOTS 提供了三个根级 System Group：
- `InitializationSystemGroup`：初始化阶段
- `SimulationSystemGroup`：游戏逻辑模拟
- `PresentationSystemGroup`：渲染准备

[来源: Unity Entities Manual - System groups](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-update-order.html)

## 方案二：拓扑排序（EnTT 的 Graph）

EnTT 库没有内置的 System 执行顺序概念（System 在 EnTT 中不是一等公民），但它提供了一个通用的**任务图（task graph）**工具，可以用来构建 System 依赖图：

```cpp
#include <entt/graph/flow.hpp>

entt::flow graph;

// 将 System 封装为 task 节点
auto& move_task = graph.bind("Move");
auto& collision_task = graph.bind("Collision");
auto& render_task = graph.bind("Render");

// 声明依赖关系：Move → Collision → Render
collision_task.sync(move_task);
render_task.sync(collision_task);

// 拓扑排序 + 执行
graph.sort();
graph.run([](const std::string& name) {
    // 根据 name 调用对应的 System 函数
    execute_system(name);
});
```

EnTT 的 flow graph 支持并行执行：如果两个 task 之间没有依赖边，它们可以并行运行。框架自动处理一切。

[来源: EnTT README - "General purpose execution graph builder"](https://github.com/skypjack/entt)

## 方案三：通过数据依赖隐式推导

更激进的方案：不显式声明依赖，而是**从 System 读/写的 Component 类型自动推导**。

```
MovementSystem:  writes<Position>, reads<Velocity>
CollisionSystem:  reads<Position, Collider>  writes<CollisionEvent>
DamageSystem:     reads<CollisionEvent, Health>  writes<Health>
RenderSystem:     reads<Position, Mesh>
```

从这些声明可以推导：
- `MovementSystem` 和 `CollisionSystem` 之间：后者读取前者写入的 `Position` → 必须 `MovementSystem` 先执行
- `CollisionSystem` 产生 `CollisionEvent`，`DamageSystem` 消费它 → `CollisionSystem` 先执行
- `RenderSystem` 只需要 `Position`（不关心它是否最新），可以和 `MovementSystem` 并行（读取上一帧的位置），也可以串行（读取本帧最新位置）——取决于设计选择

这种方案的最大好处是**不需要手动维护依赖关系**，添加新 System 时自动分析依赖。缺点是实现复杂，且某些逻辑顺序（如"音效必须在特效之后"）无法从数据依赖中推导。

目前还没有主流 ECS 库完全依赖此方案，但它是活跃的研究方向。 [来源: ECS FAQ - How are entities matched with systems?](https://github.com/SanderMertens/ecs-faq) [推测: 隐式推导的局限性分析]

## 方案四：手动分组（简单的项目）

对于小项目，最简单的做法是手动分组：

```cpp
void game_loop() {
    // Phase 1: Input processing
    process_input_systems(world);

    // Phase 2: Game logic
    movement_system(world);
    collision_system(world);
    damage_system(world);

    // Phase 3: Rendering
    animation_system(world);
    render_system(world);
}
```

这没有任何自动依赖分析，但代码清晰、调试方便。许多独立游戏项目直接使用这种方式。

## 对比总结

| 方案 | 代表库 | 复杂度 | 灵活性 | 并行支持 | 适合场景 |
|------|-------|--------|--------|----------|---------|
| 显式声明 | Flecs, Unity DOTS | 中 | 高 | 内置 | 中大型项目 |
| 拓扑排序 | EnTT (flow) | 中 | 高 | 手动控制 | 需要精细控制 |
| 数据推导 | 实验性 | 高 | 最高 | 自动 | 前沿探索 |
| 手动分组 | 自定义 | 低 | 低 | 无 | 小型项目/原型 |

## 一个常见陷阱：同一帧内的读-写竞争

假设你有一个 `DamageSystem`，它既读取 `Health`（判断是否死亡）又写入 `Health`（扣血）。同时 `AISystem` 也读取 `Health`（判断是否逃跑）。执行顺序很重要：

```
错误顺序：AISystem → DamageSystem
AISystem 读到"满血"的敌人 → 决定不逃跑
DamageSystem 把该敌人的血扣到 0
→ 敌人站着死了

正确顺序：DamageSystem → AISystem
DamageSystem 先把血扣到 0
AISystem 读到"空血" → 触发逃跑/死亡逻辑
```

此类问题在 ECS 中比 OOP 更容易暴露——因为 System 之间的解耦让你**必须显式思考数据流**，而这恰好是好事：它迫使你把隐式的时序问题显式化。

## 下一步

理解了 System 执行顺序之后，下一章将深入 ECS 的两种核心存储策略——Archetype（Flecs 采用）和 Sparse Set（EnTT 采用），并回答笔记问题 #2：EnTT 和 Flecs 的实质区别。
