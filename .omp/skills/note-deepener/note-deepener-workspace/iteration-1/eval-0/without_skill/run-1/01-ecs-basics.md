# 1. ECS 基本概念深入

## 来源

- [Wikipedia: Entity Component System](https://en.wikipedia.org/wiki/Entity_component_system)
- [ECS Back and Forth — Part 1 (skypjack)](https://skypjack.github.io/2019-02-14-ecs-baf-part-1/)
- [ECS Back and Forth — Part 2 (skypjack)](https://skypjack.github.io/2019-03-07-ecs-baf-part-2/)

## 核心三要素

### Entity（实体）

实体本身**不包含任何数据和行为**——它只是一个唯一标识符（ID）。在大多数实现中，实体就是一个整数（如 `uint32_t` 或 `uint64_t`），有时会附带一个 generation 计数器用于检测"悬空引用"（dangling reference）。

```cpp
// Entity 就是这样一个东西：
using Entity = uint32_t;  // 或者带上 generation
struct Entity {
    uint32_t index;
    uint32_t generation;  // 回收后递增，防止误用已销毁的实体
};
```

### Component（组件）

组件是**纯数据**，没有任何方法。它被"挂载"到 Entity 上。一个 Entity 可以拥有任意数量的 Component，每个 Component 类型在每个 Entity 上最多只能有一个实例。

```cpp
// 典型的 Component 定义：只包含数据，没有行为
struct Position {
    float x, y, z;
};

struct Velocity {
    float dx, dy, dz;
};

struct Health {
    int current;
    int max;
};

struct Renderable {
    int meshId;
    int materialId;
};
```

### System（系统）

System 包含**所有逻辑**。它不拥有数据，而是对满足特定 Component 组合的 Entity 集合进行操作。System 通常以函数或函数对象的形式存在，由 ECS 框架在每一帧调用。

```cpp
// 一个 MovementSystem 例子（伪代码）
void movement_system(World& world) {
    // 只处理同时拥有 Position 和 Velocity 的实体
    for (auto [entity, pos, vel] : world.query<Position, Velocity>()) {
        pos.x += vel.dx * delta_time;
        pos.y += vel.dy * delta_time;
        pos.z += vel.dz * delta_time;
    }
}
```

## ECS 的"水平切割"思维

skypjack 用一个精彩的类比解释了 ECS 与 OOP 的根本思维差异：

想象把所有游戏对象平铺在一张平面上——矮人、精灵、玩家角色、石头、等等。

|          | Dwarf | Elf   | Player | Rock  |
|----------|-------|-------|--------|-------|
| Position | ✓     | ✓     | ✓      | ✓     |
| Velocity | ✓     | ✓     | ✓      |       |
| Health   | ✓     | ✓     | ✓      |       |
| Render   | ✓     | ✓     | ✓      | ✓     |
| AI       | ✓     | ✓     |        |       |

- **OOP 做法（垂直切割）**：以"对象"为单位 —— 一个 `Dwarf` 类自包含所有它需要的数据和行为，遍历时是一个对象接一个对象地处理。
- **ECS 做法（水平切割）**：以"组件类型"为单位 —— `MovementSystem` 遍历所有 `Position + Velocity`，`RenderSystem` 遍历所有 `Position + Renderable`，一次处理一种组件类型的数组。

这种水平切割是实现数据导向设计（Data-Oriented Design）和缓存友好性的基础。

## ECS 的实现演进

skypjack 在他的系列文章中描述了从 OOP 到 ECS 的演进路径：

### 阶段一：Map 方案（半 OOP 半 ECS）

每个"游戏对象"内部持有一个 `map<ComponentType, Component>`，System 遍历所有对象并检查其是否拥有所需组件。

```cpp
void system(std::vector<GameObject>& objects) {
    for (auto& obj : objects) {
        if (obj.has<Position, Velocity>()) {
            auto& pos = obj.get<Position>();
            auto& vel = obj.get<Velocity>();
            // ...
        }
    }
}
```

- ✅ 简单直观，OOP 开发者容易理解
- ❌ 组件在内存中分散，每次访问都是随机跳转
- ❌ 必须遍历所有对象才能找到匹配的

### 阶段二：Entity 作为索引

摒弃 Game Object 类，Entity 退化为数组索引。每种 Component 类型放在一个独立数组中，Entity ID 直接作为该数组的索引。

```
Entity 0 → Position[0], Velocity[0], Health[0]
Entity 1 → Position[1], Renderable[1]
Entity 2 → Position[2], Velocity[2], Renderable[2]
```

- ✅ 迭代速度大幅提升
- ❌ 稀疏数组浪费大量内存（即使 Entity 5 没有 Velocity，Velocity[5] 仍然占位）
- ❌ 遍历中的"空洞"导致 cache miss

### 阶段三：Archetype / Sparse Set

这是现代高性能 ECS 的两大主流方向，详见第 3 章"内存布局深入"。
