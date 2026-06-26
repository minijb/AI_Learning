---
title: "学习计划: 设计模式 (C# + C++)"
updated: 2026-06-08
tags: [design-patterns, csharp, cpp, gof, oop, architecture]
---

# 学习计划: 设计模式 (C# + C++)

> 创建日期: 2026-06-08
> 预计总耗时: ~28 小时（每节约 60 分钟，含阅读 + 代码练习）
> 目标水平: 进阶 — 能在项目中选择并实现合适的设计模式

---

## 学习目标

完成本计划后，你能：

1. 识别并命名 23 种 GoF 设计模式，理解每种模式解决的问题
2. 用 C# 和 C++ 实现所有 23 种经典设计模式，代码可直接运行
3. 对比 C# 与 C++ 的实现差异，理解语言特性如何影响模式表达
4. 根据 UML 类图 / Mermaid 类图理解模式结构
5. 在实际项目中选择合适的模式，避免过度设计
6. 运用 C# 语言特性（泛型、`record`、`delegate`、`event`、`yield`、DI 容器等）和 C++ 语言特性（模板、RAII、智能指针、移动语义、`constexpr`、CRTP 等）实现惯用写法

## 前置要求

- [x] C# 基础语法（类、接口、继承、泛型）或 C++ 基础语法（类、继承、模板）
- [x] 面向对象基本概念（封装、继承、多态）
- [x] .NET SDK 已安装（建议 .NET 8+）或 C++ 编译器（建议 GCC 11+ / Clang 14+ / MSVC 2022+，C++17 标准）

## 学习路径

### 第一阶段：基础与原则（2 节）

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 1 | 设计模式概述 + SOLID 原则 | 60min | 基础 | 无 |
| 2 | 创建型模式总览 + 简单工厂 | 50min | 基础 | 1 |

### 第二阶段：创建型模式（5 节）

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 3 | 单例模式 Singleton | 50min | 核心 | 2 |
| 4 | 工厂方法模式 Factory Method | 60min | 核心 | 2 |
| 5 | 抽象工厂模式 Abstract Factory | 60min | 核心 | 4 |
| 6 | 建造者模式 Builder | 60min | 核心 | 2 |
| 7 | 原型模式 Prototype | 50min | 核心 | 2 |

### 第三阶段：结构型模式（8 节）

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 8 | 结构型模式总览 | 40min | 基础 | 1 |
| 9 | 适配器模式 Adapter | 50min | 核心 | 8 |
| 10 | 桥接模式 Bridge | 60min | 核心 | 8 |
| 11 | 组合模式 Composite | 60min | 核心 | 8 |
| 12 | 装饰器模式 Decorator | 60min | 核心 | 8 |
| 13 | 外观模式 Facade | 45min | 核心 | 8 |
| 14 | 享元模式 Flyweight | 50min | 进阶 | 8 |
| 15 | 代理模式 Proxy | 60min | 核心 | 8 |

### 第四阶段：行为型模式（11 节）

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 16 | 行为型模式总览 | 40min | 基础 | 1 |
| 17 | 责任链模式 Chain of Responsibility | 60min | 核心 | 16 |
| 18 | 命令模式 Command | 60min | 核心 | 16 |
| 19 | 迭代器模式 Iterator | 50min | 核心 | 16 |
| 20 | 中介者模式 Mediator | 60min | 核心 | 16 |
| 21 | 备忘录模式 Memento | 50min | 核心 | 16 |
| 22 | 观察者模式 Observer | 60min | 核心 | 16 |
| 23 | 状态模式 State | 60min | 核心 | 16 |
| 24 | 策略模式 Strategy | 50min | 核心 | 16 |
| 25 | 模板方法模式 Template Method | 50min | 核心 | 16 |
| 26 | 访问者模式 Visitor | 70min | 进阶 | 16 |

### 第五阶段：C# 惯用模式与实战（2 节）

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 27 | C# 惯用模式实现 | 60min | 进阶 | 1-26 |
| 28 | 依赖注入 + DI 容器 | 60min | 实战 | 27 |

## 里程碑

- [ ] 第一阶段完成：理解设计模式的全景地图和 SOLID 原则
- [ ] 第二阶段完成：能用 C# 和 C++ 实现 5 种创建型模式，理解"对象创建"的设计维度
- [ ] 第三阶段完成：能用 C# 和 C++ 实现 7 种结构型模式，理解"对象组合"的设计维度
- [ ] 第四阶段完成：能用 C# 和 C++ 实现 11 种行为型模式，理解"对象通信"的设计维度
- [ ] 最终目标：在 C# 和 C++ 项目中灵活运用设计模式，能用 Mermaid 画出类图，能用 DI 容器组装依赖，能用 C++ 模板和 CRTP 实现零成本抽象

## 模式速查表
### 创建型 — 关注"如何创建对象"
| 模式 | 一句话 | 核心 C# 特性 | 核心 C++ 特性 |
|------|--------|-------------|--------------|
| Singleton | 全局唯一实例 | `Lazy<T>`、静态构造器 | `std::call_once`、`std::once_flag`、Meyers' Singleton |
| Factory Method | 子类决定创建哪个类 | 虚方法、泛型约束 | 虚函数、模板工厂（Policy-based） |
| Abstract Factory | 创建产品族 | 接口、依赖注入 | 纯虚接口、抽象基类 |
| Builder | 分步骤构建复杂对象 | 链式 API、`with` 表达式 | 链式返回 `T&`、named parameters 模拟 |
| Prototype | 克隆已有对象 | `ICloneable`、`MemberwiseClone`、`record` | 虚析构 + `clone()` 纯虚函数、CRTP |
### 结构型 — 关注"如何组合对象"
| 模式 | 一句话 | 核心 C# 特性 | 核心 C++ 特性 |
|------|--------|-------------|--------------|
| Adapter | 接口转换 | 显式接口实现、扩展方法 | 多重继承适配、模板适配器 |
| Bridge | 分离抽象与实现 | 接口组合、依赖注入 | Pimpl（Pointer to Implementation）、编译防火墙 |
| Composite | 树形结构统一处理 | 递归组合、`IEnumerable<T>` | `std::vector<unique_ptr>`、递归遍历 |
| Decorator | 动态添加职责 | 装饰器模式 + 扩展方法对比 | 运行时：基于接口；编译时：CRTP、mixin 继承 |
| Facade | 简化复杂子系统 | 静态门面类、最小 API | Pimpl 封装、单一头文件门面 |
| Flyweight | 共享细粒度对象 | `Dictionary` 缓存、`string.Intern` | `std::shared_ptr` 缓存、`std::map`、自定义 allocator |
| Proxy | 控制对象访问 | 显式接口、`DispatchProxy` | `std::shared_ptr` 代理、智能指针代理 |
### 行为型 — 关注"对象间通信"
| 模式 | 一句话 | 核心 C# 特性 | 核心 C++ 特性 |
|------|--------|-------------|--------------|
| Chain of Responsibility | 请求沿链传递 | 链表、`Action`/`Func` 链 | `std::function`、`std::vector` 链、模板参数链 |
| Command | 请求封装为对象 | `Action<T>`、`ICommand` | `std::function` / lambda、`std::bind`、命令队列 |
| Iterator | 顺序遍历集合 | `IEnumerable<T>`、`yield return` | 重载 `operator++`/`*`/`==`、`std::ranges`（C++20） |
| Mediator | 集中通信枢纽 | `event`、`MediatR` | `std::function` 回调注册、观察者列表 |
| Memento | 保存/恢复状态 | `record` 不可变性、序列化 | 深拷贝（`unique_ptr` 管理）、拷贝构造 |
| Observer | 状态变化通知 | `event`/`IObserver<T>`、`INotifyPropertyChanged` | `std::function`、`std::vector` 回调、信号-槽 |
| State | 状态驱动行为 | 状态类 + 上下文、`enum` 对比 | `std::unique_ptr<State>`、虚函数多态 |
| Strategy | 算法族可互换 | `delegate`、`Func<T>`、接口 | `std::function`、模板策略（Policy-based design）、虚函数 |
| Template Method | 算法骨架 + 可变步骤 | `abstract` 方法、`virtual` | `virtual` + `final`、NVI（Non-Virtual Interface） |
| Visitor | 分离操作与数据结构 | 双分派、`dynamic`、模式匹配 | `std::visit`（`std::variant`）、`std::type_index`、CRTP 双分派 |