# ECS (Entity Component System) 深度分析

> 基于笔记 `drafts/test-ecs.md` 深化而成，系统分析 ECS 架构的核心概念、内存布局、库对比及与传统模式的差异。

## 来源

- [Wikipedia: Entity Component System](https://en.wikipedia.org/wiki/Entity_component_system)
- [ECS Back and Forth — Part 1 (skypjack)](https://skypjack.github.io/2019-02-14-ecs-baf-part-1/)
- [ECS Back and Forth — Part 2 (skypjack)](https://skypjack.github.io/2019-03-07-ecs-baf-part-2/)
- [EnTT GitHub](https://github.com/skypjack/entt)
- [Flecs GitHub](https://github.com/SanderMertens/flecs)
- [Flecs FAQ](https://github.com/SanderMertens/flecs/blob/master/docs/FAQ.md)
- [Building an ECS #2: Archetypes and Vectorization (Sander Mertens)](https://ajmmertens.medium.com/building-an-ecs-2-archetypes-and-vectorization-fe21690805f9)
- [Game Programming Patterns — Component (Robert Nystrom)](https://gameprogrammingpatterns.com/component.html)

## 章节导航

| # | 章节 | 文件 | 内容 |
|---|------|------|------|
| 1 | ECS 基本概念深入 | [01-ecs-basics.md](01-ecs-basics.md) | Entity/Component/System 定义，水平切割思维，实现演进（Map→Entity 作为索引→现代方案） |
| 2 | ECS 与 OOP 继承的区别 | [02-ecs-vs-oop.md](02-ecs-vs-oop.md) | 钻石问题，组合替代继承，概念消失，代码对比 |
| 3 | 内存布局深入 | [03-memory-layout.md](03-memory-layout.md) | AoS vs SoA，Archetype vs Sparse Set 两种存储模型详解 |
| 4 | System 之间的依赖管理 | [04-system-dependencies.md](04-system-dependencies.md) | 阶段/Pipeline，EnTT flow 执行图，Flecs Pipeline，数据依赖自动推导 |
| 5 | EnTT 与 Flecs 对比 | [05-entt-vs-flecs.md](05-entt-vs-flecs.md) | 存储模型、性能特征、API 风格、独特功能、选择指南 |
| 6 | Unity GameObject-Component vs 纯 ECS | [06-unity-gameobject-vs-ecs.md](06-unity-gameobject-vs-ecs.md) | 传统 Unity vs 纯 ECS 六维对比，Unity DOTS 简介 |

## 原始笔记的三个问题

1. **System 之间的依赖怎么管理？** → 见第 4 章
2. **EnTT 和 Flecs 的区别在哪？** → 见第 5 章
3. **和 Unity 的 GameObject-Component 模式有什么本质不同？** → 见第 6 章

## 阅读路径建议

- **快速了解 ECS**：1 → 2 → 6
- **深入技术决策**：3 → 4 → 5
- **库选型**：3 + 5（理解存储模型差异是选择的关键）

## 核心要点

1. ECS 的本质是**数据与行为的彻底分离**：Entity = ID，Component = 纯数据，System = 逻辑
2. ECS 用**组合替代继承**，消除了 OOP 的钻石问题和类爆炸
3. **SoA 内存布局**是同类型组件连续存储的根本优势——cache 友好，适合 SIMD/多线程
4. Archetype 和 Sparse Set 是两大主流存储模型，各有优势场景
5. EnTT 是高性能 C++ ECS 工具箱（Sparse Set），Flecs 是 C/C++ 功能丰富的 ECS 框架（Archetype）
6. Unity 传统 GameObject-Component 是"披着 ECS 外衣的 OOP"；Unity DOTS 才是真正的纯 ECS
