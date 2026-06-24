---
title: 依赖注入教程索引
updated: 2026-06-23
tags: [dependency-injection, tutorials]
---

# 教程索引

> 教程文件按知识依赖关系排序。建议按序号依次学习，但已掌握的部分可跳过。全程围绕一个**逐步演进的游戏战斗系统**展开（角色 `Hero` + 武器 `IWeapon` + 日志 `ILogger` → 伤害计算 + 事件总线 + 测试）。C++ 为主线，C# 为对照。

## 第一阶段 · 建立概念全景

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 1 | 依赖注入是什么：从紧耦合说起 | [[01-what-is-di-coupling]] | 60min |
| 2 | IoC、DIP 与 DI：辨析三大原则 | [[02-ioc-dip-di-principles]] | 60min |
| 3 | 依赖注入的三种形式 | [[03-three-forms-of-di]] | 60min |

## 第二阶段 · C++ 手动落地

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 4 | C++ 的接口：抽象基类与纯虚函数 | [[04-cpp-interfaces-abc]] | 60min |
| 5 | 构造器注入：引用、指针与所有权 | [[05-constructor-injection-ownership]] | 75min |
| 6 | 智能指针与依赖生命周期 | [[06-smart-pointers-lifetime]] | 75min |
| 7 | 组合根与手动装配 | [[07-composition-root-wiring]] | 60min |

## 第三阶段 · 进阶 C++ 技术

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 8 | 模板与静态多态：编译期 DI | [[08-templates-static-polymorphism]] | 75min |
| 9 | 类型擦除与 `std::function` 注入 | [[09-type-erasure-std-function]] | 60min |
| 10 | 现代手动 DI 模式：Builder 与分层装配 | [[10-builder-layered-wiring]] | 60min |

## 第四阶段 · 容器与跨语言对照

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 11 | DI 容器概念与 C# 内置容器 | [[11-di-containers-csharp]] | 75min |
| 12 | C++ DI 容器：`boost::di` 实战 | [[12-boost-di-cpp]] | 75min |
| 13 | 服务生命周期与作用域管理 | [[13-service-lifetimes-scopes]] | 60min |

## 第五阶段 · 测试与工程化

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 14 | 用 DI 做测试：Mock 与桩 | [[14-testing-with-di-mocks]] | 75min |
| 15 | DI 反模式与何时不用 | [[15-antipatterns-when-not]] | 60min |

## 最终项目

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 16 | 综合项目：可测试的游戏战斗系统 | [[16-capstone-game-combat]] | 150min |

---

> [!info] 学习路径图
> ```mermaid
> flowchart TD
>     S1["01 紧耦合与 DI"] --> S2["02 IoC/DIP/DI"]
>     S1 --> S3["03 三种注入形式"]
>     S1 --> S4["04 C++ 抽象基类"]
>     S4 --> S5["05 构造器注入/所有权"]
>     S5 --> S6["06 智能指针/生命周期"]
>     S5 --> S7["07 组合根/手动装配"]
>     S4 --> S8["08 模板静态多态"]
>     S4 --> S9["09 类型擦除/std::function"]
>     S7 --> S10["10 Builder/分层装配"]
>     S3 --> S11["11 C# DI 容器"]
>     S7 --> S12["12 boost::di"]
>     S11 --> S13["13 服务生命周期"]
>     S6 --> S14["14 测试与 Mock"]
>     S2 --> S15["15 反模式"]
>     S10 & S13 & S14 & S15 --> S16["16 综合项目"]
> ```
