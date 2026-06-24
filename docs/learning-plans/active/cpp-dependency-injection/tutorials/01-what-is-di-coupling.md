---
title: 依赖注入是什么：从紧耦合说起
updated: 2026-06-23
tags: [dependency-injection, cpp, coupling, tight-coupling, fundamentals]
---

# 依赖注入是什么：从紧耦合说起

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 60min
> 前置知识: 无

---

## 1. 概念讲解

### 1.1 先用一个游戏类比理解「耦合」

想象你正在写一款动作 RPG。游戏里的勇者一出生，右手就焊着一把铁剑——不是「装备」了一把剑，而是**剑和手掌长在一起**，卸不下来、换不了、修不了。

策划突然说：「第 `#3` 章我们想给玩家弓。」

你打开 `Hero.cpp`，发现 `Sword weapon_;` 是 `Hero` 类的值成员，`attack()` 里直接调用 `weapon_.damage()`。想把剑换成弓，必须：

1. 修改 `Hero` 的私有成员类型。
2. 修改 `Hero` 构造函数里的初始化逻辑。
3. 重新编译所有依赖 `Hero` 的代码。
4. 如果以后再加法杖、双刀、拳套……每次都要回来改 `Hero`。

这就是**紧耦合（tight coupling）**：`Hero` 和 `Sword` 被焊死在一起，一动全动。

更好的设计是：勇者有一个「武器槽」。剑、弓、法杖都是可插拔的武器，只要满足同一个接口，就能在运行时装备进去。`Hero` 不再关心武器具体是什么，只关心「这把武器能造成多少伤害」。

依赖注入（Dependency Injection，DI）要做的，就是把「武器槽」这个想法翻译成代码：

> **把类 A 需要的类 B，从「A 自己创建」改为「由外部传入」。**

在 C++ 里，这个「传入」可以是指针、引用、智能指针，也可以是模板参数、回调函数等。本节先用最朴素的**裸指针版**演示核心思想；引用、智能指针与所有权问题会在 [[05-constructor-injection-ownership]] 和 [[06-smart-pointers-lifetime]] 中深入。

---

### 1.2 耦合：为什么紧是坏事

**耦合（coupling）** 描述两个模块之间相互依赖的程度。

| 耦合程度 | 表现 | 对游戏开发的影响 |
|---------|------|-----------------|
| 松耦合 | 模块通过接口交互，彼此不知道具体实现 | 换武器、换输入设备、换渲染后端都不影响核心逻辑 |
| 紧耦合 | 模块直接创建或依赖对方的具体类型 | 改一个武器的数值，可能牵连 `Hero`、UI、存档、网络同步 |

紧耦合在游戏项目里尤其危险：

- **迭代成本高**：策划调一个武器伤害，要改武器类、英雄类，甚至测试代码。
- **无法单元测试**：想单独测 `Hero::attack()` 的伤害计算，却不得不把真实的 `Sword` 编译进来。
- **难以扩展**：加新武器类型要改 `Hero` 源码，违反「开闭原则」。
- **编译依赖扩散**：`Hero.h` 里 `#include "Sword.h"`，所有 `#include "Hero.h"` 的文件都间接依赖 `Sword.h`，大型项目编译时间爆炸。

> [!warning] 一个常见错觉
> 「我的项目小，紧耦合没关系。」项目总会长大；等它长大再解耦，重构成本是指数级上升的。养成注入依赖的习惯，从第 `#1` 行代码开始。

---

### 1.3 `new` 是胶水

C++ 里有一句行话：

> **new is glue。**

只要在类 A 的内部写 `B b;` 或 `new B()`，你就把 A 和 B 粘在了一起。胶水的危害不是不能拆，而是**拆的时候掉漆**——改一处，牵连十处。

看下面这行代码：

```cpp
class Hero {
    Sword weapon_; // 这就是胶水
};
```

`Hero` 不仅知道 `Sword` 存在，还决定了：

- 武器必须是 `Sword`，不能是 `Bow`。
- `Sword` 的生命周期和 `Hero` 绑定（值成员随 `Hero` 构造/析构）。
- 任何使用 `Hero` 的地方都间接依赖 `Sword` 的定义。

依赖注入的解耦思路是：把 `new Sword()` 从 `Hero` 身体里移出去，放到 `main()`（或某个工厂、组合根）里。

```cpp
Sword sword;
Hero hero("勇者", &sword); // 由外部创建并传入
```

此时 `Hero` 只需要知道「有一种东西叫 `IWeapon`，它有 `damage()` 和 `name()`」。具体是 `Sword` 还是 `Bow`，由调用方决定。

---

### 1.4 依赖注入最朴素的定义

> **依赖注入 = 依赖由外部提供，而不是在内部创建。**

用更正式的话说：

- **依赖（Dependency）**：`Hero` 要完成功能，必须借助的另一个对象（这里是武器）。
- **注入（Injection）**：这个对象不是 `Hero` 自己 `new` 出来的，而是在构造（或使用）时由外部「注射」进来的。

注入的方式有很多种：

| 方式 | 示例 | 适用场景 |
|-----|------|---------|
| 构造器注入 | `Hero(IWeapon* w)` | 最常用，依赖不可或缺 |
| Setter 注入 | `void setWeapon(IWeapon* w)` | 依赖可在运行期替换 |
| 接口注入 | 实现某个 `IWeaponUser` 接口 | 框架回调、插件系统 |

本节只看构造器注入的指针版；三种形式的详细对比见 [[03-three-forms-of-di]]。

---

### 1.5 紧耦合 vs 依赖注入：一张图看懂

```mermaid
classDiagram
    subgraph "紧耦合：武器焊死在 Hero 内部"
        class TightHero {
            -Sword weapon_
            +attack()
        }
        class TightSword {
            +damage()
            +name()
        }
        TightHero --> TightSword : 直接创建/拥有
    end

    subgraph "依赖注入：自由装备任何武器"
        class InjectedHero {
            -IWeapon weapon_
            +attack()
        }
        class IWeapon {
            <<interface>>
            +damage()*
            +name()*
        }
        class InjectedSword {
            +damage()
            +name()
        }
        class InjectedBow {
            +damage()
            +name()
        }
        InjectedHero --> IWeapon : 由外部传入
        InjectedSword --|> IWeapon
        InjectedBow --|> IWeapon
    end
```

左边：`Hero` 和 `Sword` 双向绑定，换武器要改 `Hero`。

右边：`Hero` 只依赖抽象的 `IWeapon`；`Sword`、`Bow` 都实现 `IWeapon`。想加新武器？新增一个类即可，`Hero` 一行不改。

---

## 2. 代码示例

下面给出两段**完整可运行**的 C++17 代码。第 `#1` 段演示紧耦合的问题，第 `#2` 段演示重构后的依赖注入版本。

---

### 2.1 紧耦合版：Hero 直接拥有 Sword

```cpp
#include <iostream>
#include <string>

class Sword {
public:
    int damage() const { return 15; }
    std::string name() const { return "铁剑"; }
};

class Hero {
public:
    explicit Hero(const std::string& name) : name_(name) {}

    void attack() {
        std::cout << name_ << " 用 " << weapon_.name()
                  << " 造成 " << weapon_.damage() << " 点伤害\n";
    }

private:
    std::string name_;
    Sword weapon_; // 紧耦合：Hero 内部直接创建 Sword
};

int main() {
    Hero hero("勇者");
    hero.attack();
    return 0;
}
```

**运行方式：**

```bash
g++ -std=c++17 tight_coupling.cpp -o tight_coupling
./tight_coupling
```

> 在 Windows 上若使用 MSVC，可执行：`cl /std:c++17 /EHsc /utf-8 tight_coupling.cpp`。

**预期输出：**

```text
勇者 用 铁剑 造成 15 点伤害
```

这段代码能跑，但有一个致命问题：**所有勇者都只能用铁剑**。如果你想让弓箭手用弓、法师用法杖，就必须为每种职业写一个不同的 `Hero`，或者不断往 `Hero` 里加 `std::variant`、`if/else` 判断武器类型——代码会迅速腐化。

---

### 2.2 依赖注入版：Hero 持有 IWeapon*

```cpp
#include <iostream>
#include <string>

// 武器接口：Hero 只依赖这个抽象
class IWeapon {
public:
    virtual ~IWeapon() = default;
    virtual int damage() const = 0;
    virtual std::string name() const = 0;
};

// 具体武器：Sword
class Sword : public IWeapon {
public:
    int damage() const override { return 15; }
    std::string name() const override { return "铁剑"; }
};

// 具体武器：Bow
class Bow : public IWeapon {
public:
    int damage() const override { return 12; }
    std::string name() const override { return "长弓"; }
};

// Hero 不再自己创建武器，而是由外部传入
class Hero {
public:
    Hero(const std::string& name, IWeapon* weapon)
        : name_(name), weapon_(weapon) {}

    void attack() {
        std::cout << name_ << " 用 " << weapon_->name()
                  << " 造成 " << weapon_->damage() << " 点伤害\n";
    }

private:
    std::string name_;
    IWeapon* weapon_; // 由外部传入，Hero 不再负责创建
};

int main() {
    Sword sword;
    Bow bow;

    Hero hero1("剑士", &sword);
    hero1.attack();

    Hero hero2("弓箭手", &bow);
    hero2.attack();

    return 0;
}
```

**运行方式：**

```bash
g++ -std=c++17 dependency_injection.cpp -o dependency_injection
./dependency_injection
```

> 在 Windows 上若使用 MSVC，可执行：`cl /std:c++17 /EHsc /utf-8 dependency_injection.cpp`。

**预期输出：**

```text
剑士 用 铁剑 造成 15 点伤害
弓箭手 用 长弓 造成 12 点伤害
```

现在 `Hero` 不再焊死任何具体武器。同一个 `Hero` 类，既可以拿剑，也可以拿弓；以后加法杖、双刀、拳头，只需要新增一个继承 `IWeapon` 的类，**`Hero` 一行不改**。

> [!note] 关于裸指针
> 本节故意使用 `IWeapon*` 来把注意力集中在「注入」本身。它的好处是简单、零开销；坏处是 `Hero` 不拥有武器，调用方必须保证武器的生命周期比 `Hero` 更长。游戏中到底用指针、引用还是智能指针，会在 [[05-constructor-injection-ownership]] 和 [[06-smart-pointers-lifetime]] 详细讨论。

---

## 3. 练习

### 练习 1: 基础

用自己的话回答：什么是紧耦合？为什么在游戏开发中，「`Hero` 直接包含 `Sword` 成员」是一种紧耦合？

### 练习 2: 进阶

在上面的依赖注入版代码基础上，新增一个 `Staff`（法杖）类，伤害为 `20`，名称为「火球法杖」。在 `main()` 里创建一个法师英雄，让它装备法杖并攻击一次。

### 练习 3: 挑战（可选）

假设策划要求「武器伤害会暴击」。请在**不改 `Hero::attack()` 源码**的前提下，设计一种方式让武器的伤害输出可以被扩展（提示：可以在 `IWeapon` 里增加一个方法，或在 `Sword` 内部实现暴击逻辑）。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **紧耦合**是指两个类彼此高度依赖，改动其中一个很容易牵连另一个。
>
> 在「`Hero` 直接包含 `Sword` 成员」的设计里，`Hero` 不仅知道 `Sword` 的存在，还决定了武器的类型、生命周期和创建方式。如果策划想换成弓，必须修改 `Hero` 的私有成员、构造函数，并重新编译依赖 `Hero` 的所有代码。这就是紧耦合。

> [!tip]- 练习 2 参考答案
> 参考实现如下（只需新增 `Staff` 并在 `main()` 中使用）：
>
> ```cpp
> class Staff : public IWeapon {
> public:
>     int damage() const override { return 20; }
>     std::string name() const override { return "火球法杖"; }
> };
>
> int main() {
>     Sword sword;
>     Bow bow;
>     Staff staff;
>
>     Hero hero1("剑士", &sword);
>     hero1.attack();
>
>     Hero hero2("弓箭手", &bow);
>     hero2.attack();
>
>     Hero hero3("法师", &staff);
>     hero3.attack();
>
>     return 0;
> }
> ```
>
> 输出：
>
> ```text
> 剑士 用 铁剑 造成 15 点伤害
> 弓箭手 用 长弓 造成 12 点伤害
> 法师 用火球法杖 造成 20 点伤害
> ```

> [!tip]- 练习 3 参考答案（可选）
> 核心思路是「扩展武器，而不是修改英雄」。可以在 `IWeapon` 接口里增加一个虚函数，例如：
>
> ```cpp
> class IWeapon {
> public:
>     virtual ~IWeapon() = default;
>     virtual int damage() const = 0;
>     virtual std::string name() const = 0;
>     virtual bool isCritical() const { return false; } // 默认不暴击
> };
> ```
>
> 然后在 `Sword` 中重写 `isCritical()`，让暴击逻辑封装在武器内部。`Hero::attack()` 只需要调用 `weapon_->isCritical()` 来决定是否翻倍伤害，无需知道是哪种武器。
>
> 这体现了「开闭原则」：对扩展开放（新增武器类型），对修改关闭（`Hero` 不随新机制而改）。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Cody Morterud: Dependency Injection in C++](https://www.codymorterud.com/design/2018/09/07/dependency-injection-cpp.html) —— 用简单例子解释 DI 的基本思想，适合初学者。
- [Peter Muldoon: Refactoring C++ Code for Unit testing with Dependency Injection - CppCon 2024](https://www.youtube.com/watch?v=as5Z45G59Ws) —— 通过一个真实重构案例，展示如何用 DI 让 C++ 代码变得可测试。
- 下一节概念铺垫：[[02-ioc-dip-di-principles]] —— 辨析 IoC、DIP 与 DI 三者的关系。
- C++ 接口实现细节：[[04-cpp-interfaces-abc]] —— 深入了解抽象基类、纯虚函数、虚析构函数为什么是 DI 的基础设施。

---

## 常见陷阱

- **把 DI 当成「一定要用容器」**：依赖注入是一种设计思想，不是框架专属。本节用手动传指针就已经完成了 DI。容器只是让装配更方便的工具，见 [[11-di-containers-csharp]] 和 [[12-boost-di-cpp]]。

- **一开始就纠结指针 vs 引用 vs 智能指针**：初学者容易卡在「到底该用 `IWeapon*`、`IWeapon&` 还是 `std::unique_ptr<IWeapon>`」。第 `#1` 节课的核心是「外部传入」这个思想；所有权和生命周期问题留到 [[05-constructor-injection-ownership]] 和 [[06-smart-pointers-lifetime]] 再细究。

- **认为「接口」是画蛇添足**：小项目里 `Hero` 直接依赖 `Sword` 似乎更省事。但随着武器类型增多、测试需求出现，接口的价值会指数级放大。早写接口，就是给未来的自己留退路。

- **注入之后又偷偷 `new` 回去**：有些代码把依赖从构造函数传进去，却在 `Hero::attack()` 里又 `new Sword()` 计算伤害。这样做只是把耦合从成员变量挪到了局部变量，没有真正解耦。

- **忽略生命周期**：裸指针版本要求调用方保证武器对象比 `Hero` 活得更久。如果武器在 `Hero` 之前被销毁，`Hero::attack()` 会访问悬空指针。游戏中常见做法是把武器交给组合根或智能指针管理，详见后续章节。
