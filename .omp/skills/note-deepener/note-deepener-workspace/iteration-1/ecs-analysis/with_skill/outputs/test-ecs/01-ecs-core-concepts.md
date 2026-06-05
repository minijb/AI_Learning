# ECS 核心概念：Entity、Component、System

> 基于笔记: drafts/test-ecs.md
> 所属教程: ECS 架构深度剖析
> 章: 1/5

## 直觉理解：从 OOP 的"竖切"到 ECS 的"横切"

想象你把游戏里的所有对象平铺在一张桌子上：一个矮人、一个精灵、一个玩家角色、一块石头……它们各有各的属性（位置、血量、模型、速度等）。

**面向对象（OOP）的做法是"竖切"**——每个对象自成一列。矮人有矮人的类，精灵有精灵的类，各自封装了所有的属性和行为。当你想要更新所有对象时，你遍历每一列，调用每个对象的 `update()` 方法。

**ECS 的做法是"横切"**——按属性的类型切分行。所有对象的 Position 被放在一起，所有 Velocity 被放在一起，所有 Mesh 被放在一起。当你想要移动所有东西时，你不需要关心它是矮人还是石头——你只需要遍历所有同时拥有 Position 和 Velocity 的实体，然后更新它们的位置。

这种"横切"视角是理解 ECS 的核心直觉 [来源: EnTT ECS back and forth Part 1](https://skypjack.github.io/2019-02-14-ecs-baf-part-1/)。

## Entity：只是一个 ID

在纯 ECS 中，Entity（实体）**不包含任何数据，也不包含任何行为**。它仅仅是一个唯一标识符——通常是一个整数。

```
// Entity 本质上就是一个数字
using Entity = uint64_t;

Entity player = 42;  // 第 42 号实体就是"玩家"
Entity rock = 99;    // 第 99 号实体就是"石头"
```

这个设计是刻意的。Entity 本身"是什么"完全由它挂载的 Component 来决定。如果你给实体 42 挂上 `Position`、`Health`、`PlayerInput`，那它就是一个玩家；如果你给它挂上 `Position`、`Mesh`、`Collider`，那它就是一个障碍物。同一个实体可以随时改变自己的"身份"——只需增删 Component。

**为什么不用对象？** 因为一旦你让 Entity 成为一个对象，你就隐式地给了它一个"类型"。类型一旦固定，组合就受限了——而这正是 ECS 想要打破的束缚。

## Component：纯数据，无行为

Component（组件）是挂在 Entity 上的纯数据结构。它不包含任何方法（除了可能的数据访问辅助函数），更不包含游戏逻辑。

```cpp
// C++ 中的典型 Component 定义
struct Position {
    float x, y, z;
};

struct Velocity {
    float dx, dy, dz;
};

struct Health {
    int current;
    int maximum;
};

// 这也是合法的 Component —— 但纯粹是数据
struct Transform {
    glm::mat4 matrix;
};
```

关键特征：
- **POD（Plain Old Data）**：Component 应该尽量是平凡数据类型，便于 memcpy、序列化、连续存储
- **可组合**：任何 Entity 可以拥有任意 Component 的任意组合
- **无行为**：这是与 Unity GameObject-Component 模式最本质的区别（详见第五章）

## System：逻辑的归属地

System（系统）是**唯一**包含逻辑的地方。每个 System 只做一件事，它声明自己关心的 Component 集合（称为 query），然后 ECS 框架自动找到所有满足条件的 Entity，System 只负责处理它们。

```cpp
// 一个典型的 MovementSystem：遍历所有有 Position 和 Velocity 的实体
void movement_system(registry &reg) {
    // 查询：所有同时拥有 Position 和 Velocity 的实体
    auto view = reg.view<Position, Velocity>();

    for (auto [entity, pos, vel] : view.each()) {
        pos.x += vel.dx * delta_time;
        pos.y += vel.dy * delta_time;
        pos.z += vel.dz * delta_time;
    }
}
```

System 的关键设计原则：
1. **单一职责**：一个 System 只做一件事。`MovementSystem` 只更新位置；`RenderSystem` 只负责渲染；`CollisionSystem` 只检测碰撞
2. **按需声明**：System 明确声明自己读/写哪些 Component，框架据此进行依赖分析和并行调度
3. **无副作用（在声明之外）**：一个 System 不应修改它未声明的 Component 类型

## 三者协作的全景

```
┌─────────────────────────────────────────────────────┐
│                    ECS World                         │
│                                                      │
│  Entities:  [0] [1] [2] [3] [4] [5] [6] ...        │
│                                                      │
│  Components:                                          │
│    Position: [P0] [P1]  -   [P3]  -   -   [P6]      │
│    Velocity: [V0]  -   [V2]  -   [V4]  -    -       │
│    Health:    -    [H1] [H2] [H3]  -    -    -      │
│    Render:   [R0]  -    -    -    -    -   [R6]     │
│                                                      │
│  Systems:                                             │
│    MovementSystem → query<Position, Velocity>         │
│                   → entities: [0]                    │
│    DamageSystem   → query<Health>                    │
│                   → entities: [1, 2, 3]             │
│    RenderSystem   → query<Position, Render>          │
│                   → entities: [0, 6]                │
└─────────────────────────────────────────────────────┘
```

注意：Entity 2 只有 `Velocity` 和 `Health`，没有 `Position`——所以它不会被 `MovementSystem` 处理（尽管有速度），也不会被渲染（尽管也许它应该有个位置）。这在工程上是设计者需要考虑的——数据完整性由你保证。

## ECS 不是什么

ECS 经常被误解为"带组件的对象系统"。以下几个对比帮助澄清：

| 概念 | OOP 中的对应 | ECS 中的实际 |
|------|-------------|-------------|
| "玩家"这个类型 | `class Player` 继承自 `class GameObject` | Entity 42 挂着 `{Position, Health, PlayerInput, Inventory}` |
| 移动逻辑 | `Player::move()` 或 `MoveComponent::update()` | `MovementSystem` 处理所有带 `Position+Velocity` 的实体 |
| 组件 | `MonoBehaviour`（含数据和 Update 方法） | 纯 struct，只有数据字段 |
| 查找所有敌人 | `FindObjectsOfType<Enemy>()` | `view<EnemyTag, Position, Health>()` |

> ECS 是一种**架构模式**（architectural pattern），不是库、不是引擎、不是银弹。它规定了数据和行为的组织方式，具体的存储和调度策略因实现而异。 [来源: ECS FAQ](https://github.com/SanderMertens/ecs-faq)

## 下一步

理解了核心概念后，下一章将深入探讨为什么 ECS 能取代 OOP 继承——钻石问题的根源、组合优于继承的原则，以及在内存布局层面 ECS 带来的实质性性能优势。
