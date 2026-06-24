---
title: 依赖注入学习资源汇总
updated: 2026-06-23
tags: [dependency-injection, resources]
---

# 依赖注入学习资源汇总

> 本文件汇总依赖注入（DI）学习过程中的优质资源，按主题分类。带 ✅ 的为本计划**强烈推荐**的起点。C++ 资源为主线，C#/.NET 资源为对照。

---

## 经典书籍与论文

- ✅ 📘《C++ Software Design》— Klaus Iglberger（2022）。第 4-6 章系统讲解依赖注入、类型擦除、值语义，是 C++ 现代设计观念的代表，强烈推荐游戏开发者阅读。
- 📘《Dependency Injection Principles, Practices, and Patterns》— Steven van Deursen & Mark Seemann。DI 领域的权威书，以 C# 为主但原则通用；深入讲组合根、生命周期、反模式。
- 📘《Adaptive Code: Agile coding with design patterns and SOLID principles》— Gary McLean Hall。以 .NET 讲 SOLID 与 DI 落地，第 1-3 节概念部分可参考。
- 📄 Martin Fowler《Inversion of Control Containers and the Dependency Injection pattern》(2004) — DI 概念的奠基文章，辨析 Service Locator 与 DI，第 2、15 节核心依据。[在线全文](https://martinfowler.com/articles/injection.html)

## 官方文档

- [boost::ext DI 文档](https://boost-ext.github.io/di/) — 本计划第 12 节主力框架的权威参考，含教程与配置参考。
- [Microsoft.Extensions.DependencyInjection 官方文档](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection) — .NET 内置 DI 容器，第 11、13 节核心。
- [.NET 中的依赖注入指南](https://learn.microsoft.com/dotnet/core/extensions/dependency-injection-guidelines) — 容器使用最佳实践。
- [GoogleTest / gMock 文档](https://google.github.io/googletest/gmock_cook_book.html) — 第 14 节 C++ Mock 测试工具。

## 经典演讲（视频）

- ✅ 🎥 *Dependency Injection in C++ - A Practical Guide* — Peter Muldoon，CppCon 2024。本计划第 1、14 节的核心理念来源：用 DI 让 C++ 代码可测试，避免"宇宙测试"。[YouTube](https://www.youtube.com/watch?v=kCYo2gJ3Y38)
- 🎥 *Refactoring C++ Code for Unit Testing with Dependency Injection* — Peter Muldoon，CppCon 2024。第 14、16 节的实战重构演示。[YouTube](https://www.youtube.com/watch?v=as5Z45G59Ws)
- 🎥 *Dependency Injection–A Practical Guide* — Peter Muldoon，C++Now 2024（同主题另一版本）。
- 🎥 *Boost.DI - C++ Dependency Injection* — Krzysztof Jusiak（作者），介绍 boost::di 设计与用法。[YouTube](https://www.youtube.com/watch?v=yVogS4NbL6U)

## 精选文章

- ✅ [Dependency Injection in C++ — Cody Morterud](https://www.codymorterud.com/design/2018/09/07/dependency-injection-cpp.html) — 极简清晰的 C++ DI 入门，"汽车/加油站/油桶"类比，第 1 节灵感来源。
- [SOLID 原则与游戏开发](https://www.gamedeveloper.com/programming/solid-development-principles--in-motivation) — 游戏语境下的 SOLID，配合第 2 节。
- [Type Erasure — A Real-World Comparison](https://www.modernescpp.com/index.php/type-erasure-) — 现代 C++ 类型擦除与面向对象多态对比，配合第 9 节。
- [Link-time Dependency Injection](https://nerudaj.medium.com/) 系列 — 链接期/编译期 DI，配合第 8 节进阶。

## 工具速查

| 类别 | 工具 | 说明 | 出现于 |
|------|------|------|--------|
| C++ DI 容器 | [boost::ext DI](https://github.com/boost-ext/di) | 单头文件 C++14 DI 库 | 第 12 节 |
| C++ 单头 DI | [reyesr/injection](https://github.com/reyesr/injection) | <100 行的极简 DI，适合理解原理 | 拓展阅读 |
| .NET DI 容器 | `Microsoft.Extensions.DependencyInjection` | .NET 内置，Unity 也常用 | 第 11、13 节 |
| C++ 测试框架 | GoogleTest / gMock | 第 14 节 Mock 测试 | 第 14、16 节 |
| C++ 测试框架 | Catch2 | 轻量替代，BDD 风格 | 第 14 节备选 |
| 在线编译 | Wandbox / Compiler Explorer | 无需本地环境跑 C++ 示例 | 全程 |

## 进阶方向（学完本计划后）

- **依赖注入与 ECS**：实体组件系统架构下的依赖管理（共享 World/Registry 是单例还是注入？）
- **Unreal Engine 的子系统**：`UGameInstanceSubsystem` / `UWorldSubsystem` 的设计如何呼应 DI 思想。
- **Zenject / Extenject (Unity)**：Unity 生态成熟的 DI 框架，对照本计划的 C# 容器部分。
- **编译期依赖图**：用 C++20 concepts 与 constexpr 构建零运行时开销的对象图（如 [fruit](https://github.com/google/fruit)）。
- **可测试的游戏架构**：把渲染、物理、音频都抽象成可注入接口，实现"无引擎"单元测试。
