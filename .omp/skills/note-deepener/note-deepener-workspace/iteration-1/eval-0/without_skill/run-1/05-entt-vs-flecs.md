# 5. EnTT 与 Flecs 对比

## 来源

- [EnTT GitHub (skypjack)](https://github.com/skypjack/entt)
- [Flecs GitHub (SanderMertens)](https://github.com/SanderMertens/flecs)
- [Flecs FAQ: How does Flecs compare with EnTT?](https://github.com/SanderMertens/flecs/blob/master/docs/FAQ.md)
- [ECS Back and Forth — Part 2 (skypjack)](https://skypjack.github.io/2019-03-07-ecs-baf-part-2/)

## 概览

| 维度 | EnTT | Flecs |
|------|------|-------|
| 作者 | Michele Caini (skypjack) | Sander Mertens |
| 语言 | C++17/20 (header-only) | C99 + C++17 API |
| 存储模型 | Sparse Set | Archetype |
| 编译 | 仅需 `#include` | 可单文件编译，也可模块化构建 |
| 核心设计哲学 | "pay for what you use" | "batteries included" |
| 知名用户 | **Minecraft** (Mojang), ArcGIS (Esri), Ragdoll | 多种商业项目 |
| 许可证 | MIT | MIT |

## 存储模型：Sparse Set vs Archetype

这是两者最根本的区别，决定了一整套性能特征。

### EnTT 的 Sparse Set 存储

每种 Component 类型维护一个独立的 Sparse Set。Entity 的 Component 数据存储在 Component 类型所属的 Packed Array 中。

```
Registry:
  Position pool:  Sparse Set → [E0:Pos, E1:Pos, E2:Pos, ...]  ← 紧密排列
  Velocity pool:  Sparse Set → [E0:Vel, E3:Vel, E7:Vel, ...]
  Health pool:    Sparse Set → [E0:HP, E3:HP, E8:HP, ...]
```

- 查询 `Position + Velocity`：默认找最短的 pool 遍历并检查另一个 pool（EnTT 称之为 **View**）
- 如果用 **Group** 优化：将同时拥有 Position 和 Velocity 的 Entity 挤到各自 pool 的前部，然后无检查遍历

### Flecs 的 Archetype 存储

Entity 的完整 Component 集合决定它属于哪个 Archetype。

```
Archetype [Pos, Vel]:
  Column 0 (Entity):  [E0, E1, E3]
  Column 1 (Position):[P0, P1, P3]
  Column 2 (Velocity):[V0, V1, V3]

Archetype [Pos, HP]:
  Column 0 (Entity):  [E2, E5]
  Column 1 (Position):[P2, P5]
  Column 2 (Health):  [H2, H5]
```

- 查询 `Position + Velocity`：只需扫描 [Pos, Vel] archetype（以及包含这些组件的超集 archetype）

## 性能特征（据 Flecs FAQ 总结）

| 操作 | 更快 | 原因 |
|------|------|------|
| 单组件查询/迭代 | **EnTT** | Packed Array 遍历，无 Archetype 跳转开销 |
| 多组件查询/迭代 | **Flecs** | 所有匹配 Entity 已在同一 Archetype 中的相邻列 |
| 添加/移除组件 | **EnTT** | swap-and-pop，O(1)；Flecs 需要迁移 Archetype |
| 批量创建 Entity | **Flecs** | 可在同一 Archetype 中连续分配 |
| Entity 销毁（多组件时） | **Flecs** | 一次释放整个 Chunk |
| 单 Entity 多组件访问 | **Flecs** | 同一 Archetype 内各列索引相同 |

**注意**：这些是"大致趋势"，实际性能取决于具体的使用模式。两个库在正确使用下都能达到极高的吞吐量。瓶颈通常在别处（渲染、物理、网络等）。

## API 风格

### EnTT (C++17)

```cpp
#include <entt/entt.hpp>

struct Position { float x, y; };
struct Velocity { float dx, dy; };

entt::registry registry;

// 创建 entity
auto entity = registry.create();
registry.emplace<Position>(entity, 0.f, 0.f);
registry.emplace<Velocity>(entity, 1.f, 0.f);

// 查询——使用 lambda
auto view = registry.view<Position, const Velocity>();
view.each([](Position& pos, const Velocity& vel) {
    pos.x += vel.dx;
    pos.y += vel.dy;
});

// 或者 range-for
for (auto [entity, pos, vel] : view.each()) {
    // ...
}
```

### Flecs (C++17 API)

```cpp
#include <flecs.h>

struct Position { float x, y; };
struct Velocity { float x, y; };

flecs::world ecs;

// System 方式（声明式）
ecs.system<Position, const Velocity>()
    .each([](Position& p, const Velocity& v) {
        p.x += v.x;
        p.y += v.y;
    });

auto e = ecs.entity()
    .set<Position>({10, 20})
    .set<Velocity>({1, 2});

ecs.progress();  // 自动执行所有 system
```

### Flecs (C API)

```c
ECS_COMPONENT(ecs, Position);
ECS_COMPONENT(ecs, Velocity);

ECS_SYSTEM(ecs, Move, EcsOnUpdate, Position, Velocity);

ecs_entity_t e = ecs_new(ecs);
ecs_set(ecs, e, Position, {10, 20});
ecs_set(ecs, e, Velocity, {1, 2});

ecs_progress(ecs, 0);
```

## 独特功能

### EnTT 的独特功能

- **Group**：针对特定查询模式优化，将匹配实体聚集到 pool 前部
- **Runtime Reflection**：内置的、非侵入式、无宏的运行时反射系统
- **Resource Management**：内置的 cache、loader、handle 系统
- **Cooperative Scheduler**：协程风格的进程调度器
- **Signal/Delegate/Event Dispatcher**：完整的事件系统
- **容器库**：Sparse Set 实现的 hash map、dense map 等

EnTT 本质上是一个**C++ 游戏编程工具箱**，不仅仅是 ECS。

### Flecs 的独特功能

- **Entity Relationships**：首个支持原生 Entity 关系的开源 ECS——Entity 可以作为"关系的目标"挂载到其他 Entity 上
- **Hierarchies（层级）**：Entity 可以有父子关系，作为一等公民
- **Prefabs（预制体）**：内置预制体支持，可实例化 Entity 模板
- **反射 + JSON 序列化**：内置反射框架，支持运行时组件和 JSON 序列化
- **Query DSL**：强大的查询语言，支持 join、继承
- **Web Dashboard (Explorer)**：基于 Web 的实时监控和调试 UI
- **C API 可嵌入性**：纯 C 核心，可从几乎任何语言调用
- **编译速度**：EnTT 作为 header-only 库编译较慢；Flecs 核心可在 5 秒内编译完成

## 选择指南

| 如果你…… | 选 EnTT | 选 Flecs |
|-----------|---------|----------|
| 已经在 C++ 生态中，需要 Header-only | ✅ | 也可以，但非 header-only |
| 需要 C 语言支持 | ❌ | ✅ |
| 频繁动态改变组件组合 | ✅ (swap-and-pop) | ⚠️ (迁移成本) |
| 组件组合稳定（如底层系统） | ✅ | ✅ |
| 需要 Entity 层级/预制体/关系 | ❌ (需自己实现) | ✅ 内置 |
| 编译速度敏感 | ❌ (header-only 模板) | ✅ |
| 需要 Web 调试 Dashboard | ❌ | ✅ |
| 想要 ECS + 工具全家桶 | ✅ (signal, scheduler, etc.) | ✅ (pipeline, explorer, etc.) |
| 安装简单 | ✅ (`#include <entt.hpp>`) | ✅ (单文件/CMake/vcpkg) |

## 结论

两者都是工业级质量的 ECS 库。**EnTT 更像一个高性能工具箱**（给了你最快的原料，你决定怎么组合），**Flecs 更像一个完整的框架**（提供了开箱即用的高层抽象）。skypjack 自己也说两者"处于同一联盟"——选择更多取决于接口风格偏好和功能需求，而非纯粹的原始性能。
