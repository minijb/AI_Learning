# 学习资源: ECS 系统 — 从原理到实践

## 学术论文与基础理论

- [Entity Component Systems & Data Locality](https://shaneenishry.com/blog/2014/12/27/entity-component-systems-and-data-locality/) — 最早系统介绍 ECS 与缓存局部性的文章之一
- Scott Meyers, *Effective Modern C++* — 模板元编程、类型擦除、移动语义在 ECS 实现中的关键应用
- [What is Data-Oriented Game Engine Design?](https://www.dataorienteddesign.com/dodbook/) — Richard Fabian 的数据导向设计在线书
- Mike Acton, [CppCon 2014: Data-Oriented Design and C++](https://www.youtube.com/watch?v=rX0ItVEVjHc) — 改变了整个行业的演讲
- [Pitfalls of Object Oriented Programming](http://research.scee.net/files/presentations/gcapaustralia09/Pitfalls_of_Object_Oriented_Programming_GCAP_09.pdf) — Tony Albrecht 用具体数据展示 OOP 的性能问题
- Robert Nystrom, *Game Programming Patterns* — 组件模式的权威讲解（第 14 章）

## ECS 原理与实现

### 必读文章

- [Sander Mertens — Building an ECS](https://ajmmertens.medium.com/building-an-ecs-1-types-hierarchies-and-prefabs-9e0767b87391) — Flecs 作者的三部分系列
- [Michele Caini (skypjack) — ECS back and forth](https://skypjack.github.io/) — EnTT 作者的 ECS 设计思考系列
- [Our Machinery — ECS](https://rubmle.com/ecs/) — ECS 相关的多篇深入分析
- [Adam Martin — Entity Systems are the future of MMOG development](https://t-machine.org/index.php/2007/09/03/entity-systems-are-the-future-of-mmog-development-part-1/) — 2007 年的前瞻性系列文章
- [Sparse Set vs Archetype](https://github.com/skypjack/entt/wiki/Crash-Course:-entity-component-system) — 两种存储策略的直观对比

### 存储引擎深入研究

- [bitsquid blog — Building a Data-Oriented Entity System](https://bitsquid.blogspot.com/2014/08/building-data-oriented-entity-system.html) — Niklas Frykholm 的系列（已被 Our Machinery 继承）
- [Ming-Lun "Allen" Chou — ECS Storage](https://allenchou.net/2021/05/ecs-storage/) — 图文并茂的 Chunk 内存布局讲解
- [Archetype-based ECS in detail](https://docs.google.com/presentation/d/1fWXfN4gDWIJys4iDxJGgmnnQy3i2Z3cLkDjGQsrTAdk/edit) — Unity DOTS 团队的内部技术分享

## 开源 ECS 框架

### 主要框架

| 框架 | 语言 | 存储策略 | 许可证 | GitHub |
|------|------|---------|--------|--------|
| EnTT | C++17 | Sparse Set | MIT | [skypjack/entt](https://github.com/skypjack/entt) |
| Flecs | C99 | Archetype | MIT | [SanderMertens/flecs](https://github.com/SanderMertens/flecs) |
| Bevy ECS | Rust | Archetype | MIT/Apache 2.0 | [bevyengine/bevy](https://github.com/bevyengine/bevy) |
| Legion | Rust | Archetype | MIT/Apache 2.0 | [amethyst/legion](https://github.com/amethyst/legion) |
| Arch ECS | C# | Archetype | Apache 2.0 | [genaray/Arch](https://github.com/genaray/Arch) |
| Shipyard | Rust | Sparse Set | MIT/Apache 2.0 | [leudz/shipyard](https://github.com/leudz/shipyard) |

### 框架对比资源

- [ecs_benchmark](https://github.com/abeimler/ecs_benchmark) — 多语言 ECS 框架的性能基准对比（C++、Rust、C# 等）
- [flecs-hub/ecs-tracker](https://github.com/flecs-hub/ecs-tracker) — ECS 框架的全面对比追踪
- [ECS FAQ](https://github.com/SanderMertens/ecs-faq) — Flecs 作者维护的 ECS 常见问题集

## Unity DOTS

### 官方文档

- [Unity Entities 官方文档](https://docs.unity3d.com/Packages/com.unity.entities@1.2/manual/index.html)
- [Unity DOTS 最佳实践指南](https://unity.com/how-to/unity-dots-beginners-guide)
- [Unity ECS 论坛](https://forum.unity.com/forums/data-oriented-technology-stack.147/)

### 推荐教程与视频

- [Code Monkey — Unity DOTS 完整教程系列](https://www.youtube.com/playlist?list=PLzDRvYVwl53tMCMni1R1TK1AoYN__4ojj)
- [Turbo Makes Games — Unity ECS 实战系列](https://www.youtube.com/@TurboMakesGames)
- [Wayn Group — ECS 深入解析](https://wayn.dev/series/dots/)
- [Unity DOTS 官方 Samples](https://github.com/Unity-Technologies/EntityComponentSystemSamples)

### 书籍

- *Unity DOTS: Building High-Performance Games* — 尚未正式出版，关注 Manning 早期预览

## Unreal Engine Mass

### 官方文档

- [UE5 Mass Entity 官方文档](https://docs.unrealengine.com/5.3/en-US/mass-entity-in-unreal-engine/)
- [UE5 Mass Community Plugin](https://github.com/Megafunk/MassCommunitySample) — 社区维护的 Mass 学习项目
- [City Sample 项目](https://docs.unrealengine.com/5.3/en-US/city-sample-project-unreal-engine-demonstration/) — Epic 官方使用 Mass 的大规模城市示例

### 推荐教程

- [Unreal Engine — Inside Mass (GDC 2023)](https://www.youtube.com/watch?v=WwFRIFGKk6s) — Epic 工程师的技术分享
- [Reuben Ward — UE5 Mass AI Tutorial](https://www.youtube.com/@ReubenWard) — 实战教程系列
- [Alex Forsythe — Mass Entity Tutorial Series](https://www.youtube.com/@AlexForsythe)
- [UE5 Mass 内部代码分析](https://zhuanlan.zhihu.com/p/606773267) — 社区深度源码分析（中文）

## 社区与讨论

- [r/EntityComponentSystem](https://www.reddit.com/r/EntityComponentSystem/) — Reddit ECS 社区
- [ECS Discord](https://discord.gg/ecs) — ECS 框架开发者聚集地
- [GameDev.net — ECS 讨论区](https://www.gamedev.net/forums/forum/17-ecs/)
- [知乎 — ECS 标签](https://www.zhihu.com/topic/20197870) — 中文 ECS 讨论
- [CppCon / GDC ECS 相关演讲合集](https://www.youtube.com/results?search_query=cppcon+ecs)
