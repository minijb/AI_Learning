---
title: IoC、DIP 与 DI：辨析三大原则
updated: 2026-06-23
tags: [dependency-injection, cpp, solid, ioc, dip, principles]
---

# IoC、DIP 与 DI：辨析三大原则

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 60min
> 前置知识: [[01-what-is-di-coupling|依赖注入是什么：从紧耦合说起]]

---

## 1. 概念讲解

### 1.1 从一个 RPG 战斗场景说起

想象你正在做一款 ARPG。`Hero` 是核心战斗单位，每次点击鼠标左键，角色就要挥剑、射箭或施法。最容易想到的写法是：

```cpp
class Hero {
    Sword weapon_;          // 直接依赖具体武器
public:
    void attack() {
        std::cout << "Hero 用 " << weapon_.name()
                  << " 造成 " << weapon_.damage() << " 点伤害\n";
    }
};
```

这段代码能跑，但问题很大：`Hero`（高层业务逻辑）被 `Sword`（低层实现细节）死死绑住。策划说「第 `#3` 章要加入长弓」，你就得打开 `Hero` 改代码；测试想给 `Hero` 一个伤害固定的木桩武器，也得改 `Hero`。这种「高层依赖低层」的写法，正是我们要破的依赖关系。

本章要搞清三个经常混为一谈的概念：

- **DIP（Dependency Inversion Principle，依赖倒置原则）**：设计原则，告诉你依赖方向应该怎么指。
- **IoC（Inversion of Control，控制反转）**：一种更宏观的思想，描述「控制权从应用代码移交到框架/外部」。
- **DI（Dependency Injection，依赖注入）**：实现 IoC 的众多技术之一，本章之后所有章节都在讲它。

---

### 1.2 SOLID 简要回顾：重点是 D

`SOLID` 是面向对象设计的五条原则首字母缩写：

| 字母 | 原则 | 一句话解释 |
|------|------|-----------|
| S | 单一职责 | 一个类只应有一个引起它变化的原因 |
| O | 开闭原则 | 对扩展开放，对修改关闭 |
| L | 里氏替换 | 子类型必须能替换父类型而不破坏程序 |
| I | 接口隔离 | 客户端不应被迫依赖它不需要的接口 |
| **D** | **依赖倒置** | **高层与低层都依赖抽象；抽象不依赖细节** |

在游戏开发里，`Hero`、`EnemyAI`、`DamageSystem` 都属于高层业务；`SqlDatabase`、`Renderer`、`AudioClip`、具体武器实现都属于低层细节。DIP 想说的是：

> 高层业务代码不应该因为低层细节换了实现而被迫重写。

---

### 1.3 依赖倒置原则 DIP

Robert C. Martin（Uncle Bob）对 DIP 的定义有两条：

1. **高层模块不应依赖低层模块，二者都应依赖抽象。**
2. **抽象不应依赖细节，细节应依赖抽象。**

用战斗系统翻译一下：

- `Hero` 是高层模块，`Sword`、`Bow`、`SqlDatabase`、`Renderer` 是低层细节。
- `Hero` 不应该直接 `new Sword()` 或调用 `SqlDatabase::save()`。
- `Hero` 应该依赖 `IWeapon`、`IStorage`、`IRenderer` 这些抽象接口。
- 具体实现（`Sword`、`Bow`、`MySqlStorage`、`VulkanRenderer`）去实现这些接口，但接口本身不关心谁是实现者。

下面的 mermaid 图展示了依赖方向的反转：

```mermaid
classDiagram
    direction LR

    subgraph "违反 DIP"
        Hero1["Hero\n（高层业务）"] --> Sword1["Sword\n（低层细节）"] : 直接依赖
    end

    subgraph "满足 DIP"
        Hero2["Hero\n（高层业务）"] --> IWeapon["IWeapon\n（抽象接口）"] : 依赖抽象
        Sword2["Sword\n（低层细节）"] --|> IWeapon : 实现抽象
        Bow["Bow\n（低层细节）"] --|> IWeapon : 实现抽象
    end
```

左边的高层直接指向低层，改动会级联传染；右边高层和低层都指向抽象，`Sword` 换成 `Bow` 根本不需要改 `Hero`。

---

### 1.4 控制反转 IoC：好莱坞原则

IoC 常被概括为 **「好莱坞原则」（Hollywood Principle）**：

> Don't call us, we'll call you.
> 不要调用框架，让框架调用你。

在游戏开发里，这个画面再熟悉不过：

- 你写了一个 Unity 脚本 `PlayerController : MonoBehaviour`，把 `Update()` 逻辑填好，游戏运行时 Unity 引擎的主循环会每帧调用你的 `Update()`。
- 你在 Unreal 里覆写 `Tick(float DeltaTime)`，引擎自己调度何时调用它。
- 你向输入系统注册回调：`InputComponent->BindAction("Jump", IE_Pressed, this, &APlayer::Jump);`，当玩家按下空格，输入系统反向调用你的函数。

在这些场景里，**流程的控制权不在你手里，而在框架/引擎手里**。你的代码从「主动调用别人」变成「被别人调用」，这就是控制反转。

IoC 不是某个具体 API，也不是某个容器，它是一种设计思想。实现 IoC 的手段有很多：

| 手段 | 游戏开发示例 |
|------|-------------|
| 回调 / 事件 | 引擎主循环调用 `Update()`；伤害事件触发命中回调 |
| 模板方法 | 游戏框架定义 `Game::Initialize()` / `Game::Shutdown()` 钩子 |
| 服务定位 | `ServiceLocator::Get<AudioService>()`，但注意这是反模式起点 |
| **依赖注入** | `Hero(IWeapon& weapon)`，由外部决定 `Hero` 用什么武器 |

> [!warning] DI 不是 IoC 的全部
> 很多人把 IoC 容器和 DI 混为一谈。实际上 DI 只是实现 IoC 的一种具体技术；IoC 的范围更宽。

---

### 1.5 DI 与 IoC 的关系

如果把 IoC 比作「目标」——让控制权从类内部反转到外部，那么 DI 就是达到这个目标的一条「路径」。

```text
IoC（控制反转：设计思想）
  ├── DI（依赖注入：把依赖从外部注入）
  ├── 事件/回调
  ├── 模板方法
  ├── 服务定位（Service Locator，易沦为反模式）
  └── ...
```

在 DI 的视角下，一个类不再自己 `new` 出它的依赖，而是把依赖通过构造器、Setter 或接口「注入」进来。外部装配点（后面 [[07-composition-root-wiring|组合根]] 会细讲）掌握了创建和组装的控制权。构造器注入、Setter 注入、接口注入三种形式将在 [[03-three-forms-of-di|依赖注入的三种形式]] 中详细对比。

Martin Fowler 在经典文章 *Inversion of Control Containers and the Dependency Injection pattern* 中把「IoC 容器」重新命名为「DI 容器」，正是因为 IoC 含义太广，而容器真正做的是**依赖注入**这件事。

---

### 1.6 辨析表：IoC / DIP / DI

| 维度 | IoC（控制反转） | DIP（依赖倒置原则） | DI（依赖注入） |
|------|----------------|---------------------|---------------|
| **定义** | 控制权从应用代码反转到框架/外部 | 高层与低层都应依赖抽象 | 由外部把依赖提供给对象 |
| **关注点** | 控制流、生命周期、调用方向 | 模块间的依赖方向 | 如何给对象传入依赖 |
| **是原则还是技术** | 设计思想/原则 | SOLID 中的设计原则 | 具体技术手段 |
| **关系** | 最宽泛 | 指导如何设计抽象 | 实现 IoC 的一种方式 |
| **游戏示例** | 引擎调用你的 `Tick()` | `Hero` 依赖 `IWeapon` 而非 `Sword` | `Hero hero(sword, logger);` |

记住一个简洁公式：

> **DIP 告诉你依赖应该指向哪里；IoC 描述控制权谁持有；DI 是把依赖送进去的机制。**

---

## 2. 代码示例

下面用同一个战斗系统展示「违反 DIP」和「满足 DIP」两种写法。两个示例都是完整可运行程序。

### 2.1 违反 DIP：Hero 直接依赖 Sword

```cpp
// main_violation.cpp
#include <iostream>
#include <string>

class Sword {
public:
    int damage() const { return 15; }
    std::string name() const { return "铁剑"; }
};

// Hero 直接依赖具体类 Sword —— 违反 DIP
class Hero {
    Sword weapon_;                 // 高层依赖低层细节
public:
    void attack() {
        std::cout << "Hero 用 " << weapon_.name()
                  << " 造成 " << weapon_.damage() << " 点伤害\n";
    }
};

int main() {
    Hero hero;
    hero.attack();
    // 想换成长弓？必须修改 Hero 类内部。
}
```

**运行方式：**

```bash
g++ -std=c++17 main_violation.cpp -o violation
./violation
```

**预期输出：**

```text
Hero 用 铁剑 造成 15 点伤害
```

这个版本的 `Hero` 被 `Sword` 绑死，无法装备 `Bow`，也无法在测试里换成伤害固定的木桩武器。

---

### 2.2 满足 DIP：Hero 依赖 IWeapon 抽象

```cpp
// main_refactored.cpp
#include <iostream>
#include <memory>
#include <string>

// 抽象接口：高层与低层都依赖它
class IWeapon {
public:
    virtual ~IWeapon() = default;
    virtual int damage() const = 0;
    virtual std::string name() const = 0;
};

class Sword : public IWeapon {
public:
    int damage() const override { return 15; }
    std::string name() const override { return "铁剑"; }
};

class Bow : public IWeapon {
public:
    int damage() const override { return 12; }
    std::string name() const override { return "长弓"; }
};

// Hero 依赖抽象 IWeapon —— 满足 DIP
class Hero {
    IWeapon& weapon_;
public:
    explicit Hero(IWeapon& weapon) : weapon_(weapon) {}

    void attack() {
        std::cout << "Hero 用 " << weapon_.name()
                  << " 造成 " << weapon_.damage() << " 点伤害\n";
    }
};

int main() {
    Sword sword;
    Bow bow;

    Hero meleeHero(sword);
    Hero rangedHero(bow);

    meleeHero.attack();
    rangedHero.attack();
}
```

**运行方式：**

```bash
g++ -std=c++17 main_refactored.cpp -o refactored
./refactored
```

**预期输出：**

```text
Hero 用 铁剑 造成 15 点伤害
Hero 用 长弓 造成 12 点伤害
```

现在 `Hero` 不再关心手中是剑还是弓，只关心对方是不是 `IWeapon`。新增武器类型时，不需要打开 `Hero` 源码。

---

## 3. 练习

### 练习 1: 基础

用自己的话解释：为什么说「`Hero` 直接 `new Sword()`」违反了 DIP？用一句话概括依赖倒置后 `Hero` 与 `Sword` 之间的关系变化。

### 练习 2: 进阶

假设你的游戏里有 `Hero`（高层）和 `SqlDatabase`（低层，用于存档）。请仿照第 2.2 节代码，把直接依赖改造为依赖抽象 `IStorage`。写出 `IStorage`、`SqlDatabase`、`Hero` 的核心代码片段，并说明 `Hero` 的构造器签名应该如何设计。

### 练习 3: 挑战（可选）

Unity 的 `MonoBehaviour` 是 IoC 思想的经典例子：引擎主循环调用你的 `Update()`。请从「控制权归属」角度解释：

1. `Update()` 体现了哪种 IoC 实现方式？
2. 这与构造器注入 `Hero(IWeapon&)` 有什么相同点和不同点？

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> `Hero` 是高层战斗业务，`Sword` 是低层具体实现。直接 `new Sword()` 让高层依赖低层，违反了 DIP 的「高层不应依赖低层」。
> 依赖倒置后，`Hero` 依赖的是 `IWeapon` 抽象；`Sword` 通过继承实现 `IWeapon`。二者都依赖抽象，而不是高层依赖低层。

> [!tip]- 练习 2 参考答案
> 核心思路是引入 `IStorage` 抽象，由外部注入实现。
>
> ```cpp
> class IStorage {
> public:
>     virtual ~IStorage() = default;
>     virtual void save(const std::string& heroData) = 0;
> };
>
> class SqlDatabase : public IStorage {
> public:
>     void save(const std::string& heroData) override {
>         std::cout << "[SQL] 存档: " << heroData << "\n";
>     }
> };
>
> class Hero {
>     IStorage& storage_;
> public:
>     explicit Hero(IStorage& storage) : storage_(storage) {}
>     void save() { storage_.save("Hero 状态"); }
> };
> ```
>
> `Hero` 的构造器签名应接受 `IStorage&`（或 `std::unique_ptr<IStorage>`，视生命周期而定，详见 [[06-smart-pointers-lifetime]]）。这样 `Hero` 不依赖具体数据库，测试时也可以注入内存里的假存储。

> [!tip]- 练习 3 参考答案（可选）
> 1. `Update()` 体现的是**回调/事件驱动**式的 IoC：游戏引擎持有主循环控制权，每帧反向调用你写的 `Update()`。
> 2. 相同点：都是把控制权从对象内部反转到外部。不同点：`Update()` 是引擎**调用对象的行为**；构造器注入是外部**给对象提供依赖**。前者是「何时调用我」的反转，后者是「依赖从哪来」的反转。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- Martin Fowler, *Inversion of Control Containers and the Dependency Injection pattern*（2004）：IoC 与 DI 概念的经典来源，[原文链接](https://martinfowler.com/articles/injection.html)
- Robert C. Martin, *The Dependency Inversion Principle*：DIP 的原始论文，Uncle Bob 对「依赖抽象」的系统阐述
- SOLID 原则总览：理解 DIP 在 S/O/L/I 中的位置，有助于判断何时该抽象、何时该保留具体类
- [[04-cpp-interfaces-abc|C++ 的接口：抽象基类与纯虚函数]]：下一节会深入讲解 `IWeapon` 这类抽象基类在 C++ 中的技术细节
- [[15-antipatterns-when-not|DI 反模式与何时不用]]：避免把「依赖抽象」当成处处建接口的迷信

---

## 常见陷阱

- **把 IoC 等同于 DI 容器**：IoC 是思想，DI 是实现之一，DI 容器只是帮你在运行时自动装配依赖的工具。没有容器也可以写 DI（比如手动 `Hero hero(sword, logger);`），参见 [[07-composition-root-wiring|组合根与手动装配]]。
- **把 DIP 等同于「用接口」**：引入接口只是手段，不是目的。DIP 的真正目标是让高层业务不随低层实现变化而重写。如果一个接口没有稳定语义、只是套了一层抽象，反而会增加复杂度。
- **所有地方都追求依赖抽象**：稳定的、不会变的内部工具类（如 `Vector3`、`Quaternion`）不需要抽象。DIP 的价值在「会变化或需要替换」的边界上最大，比如武器、渲染后端、存档方式、输入源。
- **忽略抽象的所有权方向**：抽象不依赖细节，但细节要实现抽象。不要把 `IWeapon` 设计成知道 `Sword` 的存在，否则方向又反了。
- **把 IoC 与「框架调用你」完全等同**：回调只是 IoC 的一种形态。构造器注入、事件总线、插件系统、脚本 VM 都是 IoC 的不同实现。
