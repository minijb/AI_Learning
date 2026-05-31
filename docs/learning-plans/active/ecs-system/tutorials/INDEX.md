# 教程索引

> ECS 系统 — 从原理到实践
> 教程文件按知识依赖关系排序。共 34 个知识点，分为 5 大部分。

## 第一部分: ECS 原理

| 序号 | 知识点 | 文件 | 预计耗时 |
|:-----|--------|------|:---------|
| 1 | ECS 概述 — 架构起源与核心思想 | [01-ecs-overview.md](01-ecs-overview.md) | 60min |
| 2 | Entity — 轻量级标识符的本质 | [02-entity.md](02-entity.md) | 50min |
| 3 | Component — 纯数据的艺术 | [03-component.md](03-component.md) | 50min |
| 4 | System — 纯逻辑的执行单元 | [04-system.md](04-system.md) | 60min |
| 5 | World / Coordinator — 容器的设计与职责 | [05-world.md](05-world.md) | 60min |
| 6 | Archetype — 原型存储模式与 SOA 布局 | [06-archetype.md](06-archetype.md) | 70min |
| 7 | 查询与迭代 — Query、Filter、Iterator 设计 | [07-query.md](07-query.md) | 60min |
| 8 | 缓存局部性与数据导向设计 | [08-cache-locality.md](08-cache-locality.md) | 60min |
| 9 | 调度与依赖 — 系统排序、并行执行、同步屏障 | [09-scheduling.md](09-scheduling.md) | 70min |
| 10 | ECS vs 其他架构模式 — OOP、DOD、Actor 对比 | [10-ecs-vs-others.md](10-ecs-vs-others.md) | 60min |

## 第二部分: ECS 应用实践

| 序号 | 知识点 | 文件 | 预计耗时 |
|:-----|--------|------|:---------|
| 11 | 游戏开发中的 ECS — 角色、武器、技能系统 | [11-game-development-ecs.md](11-game-development-ecs.md) | 90min |
| 12 | 物理模拟与 ECS — 位置/速度、碰撞检测 | [12-physics-ecs.md](12-physics-ecs.md) | 90min |
| 13 | UI 系统与 ECS — 事件驱动、组件化界面 | [13-ui-ecs.md](13-ui-ecs.md) | 60min |
| 14 | 网络同步与 ECS — 实体复制、快照插值 | [14-networking-ecs.md](14-networking-ecs.md) | 60min |
| 15 | ECS 反模式与工程实践 — 何时不该用 ECS | [15-ecs-anti-patterns.md](15-ecs-anti-patterns.md) | 60min |

## 第三部分: Unity ECS (DOTS)

| 序号 | 知识点 | 文件 | 预计耗时 |
|:-----|--------|------|:---------|
| 16 | Unity DOTS 总览 — 架构、生态与版本演进 | [16-unity-dots-overview.md](16-unity-dots-overview.md) | 60min |
| 17 | IComponentData 与组件定义 | [17-icomponentdata.md](17-icomponentdata.md) | 90min |
| 18 | ISystem / SystemBase / SystemAPI — 系统编写 | [18-isystem.md](18-isystem.md) | 90min |
| 19 | Baking 与 Authoring — 从 GameObject 到 Entity | [19-baking.md](19-baking.md) | 90min |
| 20 | Jobs + Burst 编译器 — 并行化与高性能 | [20-jobs-burst.md](20-jobs-burst.md) | 90min |
| 21 | Blob Assets 与共享组件 | [21-blob-assets.md](21-blob-assets.md) | 60min |
| 22 | EntityCommandBuffer — 延迟操作与同步点 | [22-ecb.md](22-ecb.md) | 60min |
| 23 | 完整案例 — 弹幕射击游戏 | [23-unity-project.md](23-unity-project.md) | 120min |

## 第四部分: Unreal Engine ECS (Mass)

| 序号 | 知识点 | 文件 | 预计耗时 |
|:-----|--------|------|:---------|
| 24 | Mass 框架总览 — 架构与设计理念 | [24-ue-mass-overview.md](24-ue-mass-overview.md) | 60min |
| 25 | Mass Entity 与 Fragment — 数据结构层 | [25-mass-entity-fragment.md](25-mass-entity-fragment.md) | 90min |
| 26 | Mass Processors — 处理器与查询系统 | [26-mass-processors.md](26-mass-processors.md) | 90min |
| 27 | Mass Traits 与实体模板 | [27-mass-traits.md](27-mass-traits.md) | 60min |
| 28 | Mass LOD 与 Replication | [28-mass-lod-replication.md](28-mass-lod-replication.md) | 60min |
| 29 | 完整案例 — 万人同屏 AI 人群 | [29-ue-mass-project.md](29-ue-mass-project.md) | 120min |

## 第五部分: 开源 ECS 框架

| 序号 | 知识点 | 文件 | 预计耗时 |
|:-----|--------|------|:---------|
| 30 | EnTT — C++ 最流行的 ECS 库深入剖析 | [30-entt.md](30-entt.md) | 120min |
| 31 | Flecs — 模块化 C ECS 与查询 DSL | [31-flecs.md](31-flecs.md) | 90min |
| 32 | Bevy ECS — Rust 现代游戏引擎的 ECS 设计 | [32-bevy-ecs.md](32-bevy-ecs.md) | 90min |
| 33 | Legion、Arch 等 Rust ECS 对比 | [33-rust-ecs-comparison.md](33-rust-ecs-comparison.md) | 60min |
| 34 | 从零实现一个 ECS 框架 | [34-implement-ecs.md](34-implement-ecs.md) | 120min |
