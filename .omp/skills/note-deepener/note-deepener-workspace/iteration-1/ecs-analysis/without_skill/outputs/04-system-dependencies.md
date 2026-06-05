# 4. System 之间的依赖管理

## 原始问题

> 但是 System 之间的依赖怎么管理？如果 MovementSystem 要先跑，CollisionSystem 要后跑？

这是 ECS 架构中最常见的实际问题之一。答案取决于你使用的 ECS 框架，但通用模式是相似的。

## 为什么需要顺序

典型的游戏循环系统执行顺序：

```
InputSystem        ← 读取玩家输入
    ↓
MovementSystem     ← 根据速度更新位置
    ↓
CollisionSystem    ← 检测碰撞（需要最新位置）
    ↓
DamageSystem       ← 处理伤害（需要碰撞结果）
    ↓
RenderSystem       ← 渲染最终画面
```

如果顺序错误——比如 `CollisionSystem` 在 `MovementSystem` 之前运行——碰撞检测会使用上一帧的旧位置，导致穿模（tunneling）。

## 方案一：阶段/管线（Pipeline / Phase）

这是最直观的方案。将 System 分组到顺序执行的阶段中。

### EnTT 的方式：手动调用

EnTT **不内置** System 依赖管理。你需要自己按顺序调用 System：

```cpp
void game_loop(entt::registry& registry, float dt) {
    input_system(registry);          // 阶段 1
    movement_system(registry, dt);   // 阶段 2
    collision_system(registry);      // 阶段 3
    damage_system(registry);         // 阶段 4
    render_system(registry);         // 阶段 5
}
```

EnTT 也提供了 **`entt::flow`（执行图）**——一个通用的有向无环图任务调度器，可以用于声明 System 依赖：

```cpp
entt::flow flow;

auto input    = flow.bind("input");
auto move     = flow.bind("move");
auto collision = flow.bind("collision");
auto damage   = flow.bind("damage");
auto render   = flow.bind("render");

// 声明依赖关系：render 依赖所有之前的阶段
move.depends(input);
collision.depends(move);
damage.depends(collision);
render.depends(damage);

// 自动按拓扑排序执行
flow.execute([](const auto& name) {
    // 根据 name 调用对应的 system
});
```

### Flecs 的方式：Pipeline

Flecs 内置了 Pipeline 系统。你可以声明 Phase 标签，把 System 分配给不同的 Phase：

```cpp
flecs::world ecs;

// 定义阶段标签（它们的顺序决定了执行顺序）
auto OnInput    = ecs.entity();
auto OnMove     = ecs.entity();
auto OnCollide  = ecs.entity();
auto OnDamage   = ecs.entity();
auto OnRender   = ecs.entity();

// 构建 pipeline——明确指定阶段间的依赖顺序
ecs.pipeline()
    .with(flecs::System)  // phase 的基类必须是 System
    .with(OnInput)
    .with(OnMove).depends_on(OnInput)
    .with(OnCollide).depends_on(OnMove)
    .with(OnDamage).depends_on(OnCollide)
    .with(OnRender).depends_on(OnDamage)
    .build();

// 把 system 注册到相应 phase
ecs.system<Position, const Velocity>("Move")
    .kind(OnMove)
    .each([](Position& p, const Velocity& v) {
        p.x += v.x;
        p.y += v.y;
    });

ecs.system<>("Collide")
    .kind(OnCollide)
    .each([](flecs::entity e) { /* ... */ });

// 主循环——pipeline 自动按顺序执行
ecs.progress();  // 自动: OnInput → OnMove → OnCollide → OnDamage → OnRender
```

## 方案二：数据依赖自动推导

有些 ECS 通过分析 System 对 Component 的读写模式来**自动推导**依赖关系：

```
MovementSystem:  write<Position>, read<Velocity>
CollisionSystem: read<Position>, write<CollisionResult>
DamageSystem:    read<CollisionResult>, write<Health>

推理：
- CollisionSystem 读 Position → 必须在 MovementSystem（写 Position）之后
- DamageSystem 读 CollisionResult → 必须在 CollisionSystem（写 CollisionResult）之后
- MovementSystem 和 DamageSystem 不冲突 → 可并行
```

这种方案的理论更优雅，但由于需要运行时或编译期分析，实现复杂度高。实际上，**显式声明阶段**是工业界最常用的方案——简单、可预测、易于调试。

## 方案三：System 内的 Barrier / 同步点

当多个 System 可以在同一阶段并行运行时，需要在"读-写冲突"的点插入 barrier：

```
Phase:  OnUpdate
    ┌── MovementSystem ──┐
    │  (w:Position,       │
    │   r:Velocity)      │  并行
    │                     │
    ├── AISystem ─────────┤
    │  (w:AIState,        │
    │   r:Position)      │
    └─────────────────────┘
              │
         [Barrier]  ← 确保所有写操作完成
              │
    ┌── CollisionSystem ─┐
    │  (w:Collision,      │
    │   r:Position)      │
    └─────────────────────┘
```

Flecs 的锁无关调度器（lockless scheduler）就是基于这种模型：它分析 System 的组件访问权限，自动决定哪些 System 可以并行。

## 实践建议

对于绝大多数游戏项目：

1. **优先使用显式阶段**（EnTT 手动顺序调用 / Flecs Pipeline）——简单、无魔法、易于理解
2. 阶段粒度设为 **3-7 个** 即可，太少会限制并行性，太多会增加复杂度
3. **不要过度设计依赖图**——如果 `MovementSystem` 永远要在 `CollisionSystem` 之前运行，直接写在主循环里比构建复杂的 DAG 更清晰
4. 使用 **Profiler** 而不是猜测来优化执行顺序——有时候直觉的"这必须在那个之前"实际上并不存在数据依赖
