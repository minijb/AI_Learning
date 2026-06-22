---
title: 学习资源 — 游戏架构设计
updated: 2026-06-22
tags: [game-architecture, resources]
---

# 学习资源: 游戏架构设计

> 配套 [[plan]]。各章末「扩展阅读」会给出更细粒度的链接，本页是权威书/站汇总。

## 书籍（架构根基）

- **《Game Engine Architecture》(3rd ed.)** — Jason Gregory（Naughty Dog）。游戏引擎子系统分解的权威教材。覆盖循环、内存、渲染、物理、音频、工具链。<https://gameenginebook.com/>
- **《Game Programming Patterns》** — Robert Nystrom。游戏专属设计模式（游戏循环、状态、组件、事件队列、Service Locator、命令、Type Object…）。在线全本免费。<https://gameprogrammingpatterns.com/>
- **《Data-Oriented Design》** — Richard Fabian。DoD 思维与缓存友好的数据布局。<https://www.dataorienteddesign.com/site.php>
- **《Clean Architecture》** — Robert C. Martin。依赖倒置与同心圆分层。<https://www.oreilly.com/library/view/clean-architecture/9780134494166/>
- **《Domain-Driven Design》** — Eric Evans。战略设计、限界上下文、统一语言。
- **《Working Effectively with Legacy Code》** — Michael Feathers。「接缝」概念，重构与可测试性。

## 在线系列与文章

- **Gaffer On Games** — Glenn Fiedler。游戏物理、网络代码权威系列。<https://gafferongames.com/>
- **Fast-Paced Multiplayer** — Gabriel Gambetta。客户端预测 / 服务器调和 / 兴趣管理经典四部曲。<https://www.gabrielgambetta.com/client-server-game-architecture.html>
- **Sander Mertens — ECS FAQ**。ECS 概念的清晰辨析（Entity/Component/System、archetype）。<https://github.com/SanderMertens/ecs-faq>
- **Mike Acton — Data-Oriented Design (CppCon 2014)**。<https://www.youtube.com/watch?v=rX0ItVEVjA>
- **Overwatch Gameplay Architecture & Netcode (GDC 2017)** — Tim Ford。ECS + 网络在大型项目中的落地。

## 架构方法论

- **C4 Model** — Simon Brown。结构化画架构图。<https://c4model.com/>
- **Architecture Decision Records (ADRs)** — Michael Nygard 原文。<https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>
- **Hexagonal Architecture (Ports & Adapters)** — Alistair Cockburn。<https://alistair.cockburn.us/hexagonal-architecture/>
- **The Strangler Fig Pattern** — Martin Fowler。增量重构遗留系统。<https://martinfowler.com/bliki/StranglerFigApplication.html>

## 引擎 / 框架参考实现

- **Unity Scriptable Render Pipeline (SRP)** — 渲染管线抽象的工业实现。<https://docs.unity3d.com/Manual/universal-render-pipeline.html>
- **Unreal Gameplay Ability System (GAS)** — 技能/效果/标签系统架构。<https://github.com/tranek/GASDocumentation>
- **Dear ImGui** — 即时模式 UI 的代表实现。<https://github.com/ocornut/imgui>
- **Box2D / PhysX** — 物理 broadphase/narrowphase/solver 管线参考。
- **entt (C++)** — archetype-style ECS 工业实现。<https://github.com/skypjack/entt>
- **Unity DOTS / Entities** — 面向数据 ECS + Job System。<https://unity.com/dots>

## 社区与进阶

- **r/EnginesAreUs** 与 **r/gameai**（Reddit）
- **Game AI Pro** 系列（免费在线，AI 架构与算法合集）：<http://www.gameaipro.com/>
- **Amit Patel — Red Blob Games**（空间分区、寻路、网格）：<https://www.redblobgames.com/>
