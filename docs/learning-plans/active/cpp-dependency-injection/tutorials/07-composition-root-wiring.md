---
title: 组合根与手动装配
updated: 2026-06-23
tags: [dependency-injection, cpp, composition-root, wiring, lifetime]
---

# 组合根与手动装配

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 60min
> 前置知识: [[05-constructor-injection-ownership]]

---

## 1. 概念讲解

### 1.1 从一个 RPG 场景说起

想象你正在做一款动作 RPG：玩家控制 `Hero`，手持一把 `Sword`，每次攻击都要把伤害写到日志里。游戏里还有 `Enemy` 站在对面挨揍。

代码写久了，你会发现 `Hero` 如果顺手 `new ConsoleLogger()` 再 `new Sword()`，就会像角色自己跑到铁匠铺买剑、自己跑到文具店买笔记本一样奇怪。业务类应该只关心「我要攻击」，而不是「我的剑和日志从哪来」。

组合根（Composition Root）就是把这个「谁来创建、谁来连接」的问题，集中到程序入口附近一次性解决。它是对象图的装配车间，而不是业务逻辑的一部分。

### 1.2 什么是组合根

**组合根**是应用程序中**唯一**负责构造整个对象图的地方，通常紧挨着入口点：

- C++：在 `main()` 里，或游戏的 `Game::init()` / `Application::startup()` 中。
- C# / .NET：在 `Program.cs` 或 `Startup.ConfigureServices` 中（这会把我们自然引向第 11 节的 DI 容器）。
- Unity 编辑器：某种程度上，场景里拖拽赋值组件、暴露 `public` 字段并手动连线，就是可视化的组合根。

在组合根里，你会看到一连串的 `new` 和构造器调用，把依赖逐层注入进去。业务代码里则**不应该**再出现 `new` 依赖。

### 1.3 为什么要集中装配

| 分散装配（反模式） | 集中组合根 |
|---|---|
| 业务类里藏着 `new Sword()`、`new ConsoleLogger()` | 业务类只声明构造器参数：`Hero(IWeapon&, ILogger&)` |
| 想换武器或日志实现时，要进业务类改代码 | 在组合根改一行，业务类完全不动 |
| 单元测试需要真实依赖（耗时、有副作用） | 测试时直接注入 `MockWeapon`、`MockLogger` |
| 生命周期由每个业务类自己猜 | 入口统一控制：依赖必须比使用者活得长 |

集中之后，业务类只做一件事：**声明自己需要什么**。这正是我们在 [[05-constructor-injection-ownership]] 里讲过的构造器注入思想的延伸。

### 1.4 组合根就像 Unity 编辑器里的拖拽赋值

在 Unity 里，你可能会把 `PlayerController` 脚本挂到角色上，然后在 Inspector 里把 `Weapon` 字段拖到 `Sword` 预制体上。这个拖拽面板就是**可视化的组合根**：

- 集中：所有引用关系一目了然。
- 可见：打开场景就知道 `Hero` 用的是哪把剑。
- 可审计：审查 PR 时直接看到依赖变化。

代码里的组合根是这个过程的纯代码版本。它不如编辑器直观，但更可控、更易于版本管理，也更适合 C++ 这种没有 Unity Inspector 的运行时。

### 1.5 装配顺序与对象图

组合根里的核心规则是：**先创建叶子依赖，再创建依赖它们的对象**。叶子节点是没有注入依赖、或只依赖基础设施的具体类。

以本节的战斗系统为例，对象图如下：

```mermaid
graph LR
    Logger[ConsoleLogger<br/>实现 ILogger]
    Sword[Sword<br/>实现 IWeapon]
    Hero[Hero<br/>依赖 IWeapon + ILogger]
    Enemy[Enemy]

    Logger -->|ILogger&| Hero
    Sword -->|IWeapon&| Hero
    Hero -->|attack()| Enemy
```

装配顺序：

1. 创建 `ConsoleLogger`（叶子）。
2. 创建 `Sword`（叶子）。
3. 创建 `Hero(logger, sword)`（依赖前两步）。
4. 创建 `Enemy`（本示例中无依赖，叶子）。
5. 让 `Hero` 攻击 `Enemy`。

因为 C++ 的局部对象按**构造顺序**分配、按**析构逆序**销毁，只要我们按上面的顺序在 `main()` 里定义变量，`Logger` 和 `Sword` 一定比 `Hero` 活得更久——不会出现悬垂引用。

---

## 2. 代码示例

下面的完整示例把「散落各处的 `new`」改成「集中在 `main()` 的组合根」。注意 `Hero` 和 `Enemy` 的构造器里没有任何 `new`。

```cpp
// composition_root_demo.cpp
// 编译：g++ -std=c++17 composition_root_demo.cpp -o composition_root_demo
#include <iostream>
#include <memory>
#include <string>

// ---------- 抽象接口 ----------
class IWeapon {
public:
    virtual ~IWeapon() = default;
    virtual int damage() const = 0;
    virtual std::string name() const = 0;
};

class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void log(const std::string& msg) = 0;
};

// ---------- 叶子依赖 ----------
class ConsoleLogger : public ILogger {
public:
    void log(const std::string& msg) override {
        std::cout << "[log] " << msg << "\n";
    }
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

// ---------- 业务类 ----------
class Enemy {
public:
    explicit Enemy(int hp) : hp_(hp) {}

    void takeDamage(int amount) {
        hp_ -= amount;
        if (hp_ < 0) hp_ = 0;
    }

    int hp() const { return hp_; }
private:
    int hp_;
};

class Hero {
public:
    Hero(std::string name, IWeapon& weapon, ILogger& logger)
        : name_(std::move(name)), weapon_(weapon), logger_(logger) {}

    void attack(Enemy& enemy) {
        logger_.log(name_ + " 使用 " + weapon_.name() + " 攻击！");
        enemy.takeDamage(weapon_.damage());
        logger_.log(name_ + " 造成 " + std::to_string(weapon_.damage()) + " 点伤害");
    }

private:
    std::string name_;
    IWeapon& weapon_;
    ILogger& logger_;
};

// ---------- 组合根 ----------
int main() {
    // 1. 先创建叶子依赖
    ConsoleLogger logger;
    Sword         sword;

    // 2. 再创建依赖它们的对象
    Hero hero("亚瑟", sword, logger);
    Enemy enemy(100);

    // 3. 运行游戏逻辑
    hero.attack(enemy);
    std::cout << "敌人剩余生命值：" << enemy.hp() << "\n";

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 composition_root_demo.cpp -o composition_root_demo
./composition_root_demo
```

**预期输出:**

```text
[log] 亚瑟 使用 铁剑 攻击！
[log] 亚瑟 造成 15 点伤害
敌人剩余生命值：85
```

### 2.1 生命周期顺序是如何被保证的

在 `main()` 中，局部对象的销毁顺序与构造顺序相反：

1. `logger` 构造
2. `sword` 构造
3. `hero` 构造（持有 `logger` 和 `sword` 的引用）
4. `enemy` 构造
5. 运行攻击逻辑
6. `enemy` 析构
7. `hero` 析构（此时引用的 `logger` 和 `sword` 仍然存活）
8. `sword` 析构
9. `logger` 析构

`Hero` 析构时，`logger_` 和 `weapon_` 指向的对象都还没有销毁，因此不存在悬垂引用。这就是「依赖比使用者活得更长」在栈对象中的自然表达。

### 2.2 C# 对照：Program.cs 中的组合根

C# 里手动装配的组合根看起来和 C++ 非常像：

```csharp
// Program.cs（手动装配版）
var logger = new ConsoleLogger();
var weapon = new Sword();
var hero   = new Hero("亚瑟", weapon, logger);
var enemy  = new Enemy(100);

hero.Attack(enemy);
```

等学到第 11 节 [[11-di-containers-csharp]]，我们会把这段替换成 `IServiceCollection` 注册：

```csharp
builder.Services.AddSingleton<ILogger, ConsoleLogger>();
builder.Services.AddTransient<IWeapon, Sword>();
builder.Services.AddTransient<Hero>();
```

但无论是手动装配还是容器装配，**组合根的位置不变**：都在程序启动入口附近。

---

## 3. 练习

### 练习 1: 基础

把上面的示例改成让 `Hero` 装备 `Bow` 而不是 `Sword`。只修改 `main()` 中的组合根，不要改动 `Hero`、`Enemy` 或任何接口。

### 练习 2: 进阶

在 `main()` 中同时创建两名英雄：一个用 `Sword`，一个用 `Bow`，共享同一个 `ConsoleLogger`。让两名英雄轮流攻击同一个 `Enemy`，直到 `Enemy` 的生命值降到 `0` 或以下。观察输出顺序是否符合预期。

### 练习 3: 挑战（可选）

给 `Hero` 增加一个 `heal(int amount)` 方法，让 `Hero` 可以治疗自己。然后在 `main()` 组合根里添加一个 `Potion` 类作为新的叶子依赖，通过构造器注入到 `Hero` 中。要求：

- `Potion` 实现 `IHealingItem` 接口（自己定义）。
- `Hero` 的治疗方法依赖 `Potion`。
- 组合根里仍然一次性创建所有对象。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 只需把组合根中的 `Sword sword;` 换成 `Bow bow;`，并把 `hero` 构造里的 `sword` 换成 `bow`：
>
> ```cpp
> int main() {
>     ConsoleLogger logger;
>     Bow           bow;        // 替换这里
>
>     Hero hero("亚瑟", bow, logger);  // 替换这里
>     Enemy enemy(100);
>
>     hero.attack(enemy);
>     std::cout << "敌人剩余生命值：" << enemy.hp() << "\n";
> }
> ```
> 预期输出里武器名会从「铁剑」变成「长弓」，伤害从 `15` 变成 `12`。

> [!tip]- 练习 2 参考答案
> 多名英雄共享同一个 `logger` 是组合根的典型用法。注意 `bow` 和 `sword` 必须都活到 `hero2` 和 `hero1` 析构之后：
>
> ```cpp
> int main() {
>     ConsoleLogger logger;
>     Sword sword;
>     Bow   bow;
>
>     Hero hero1("剑士", sword, logger);
>     Hero hero2("弓手", bow, logger);
>     Enemy enemy(30);
>
>     while (enemy.hp() > 0) {
>         hero1.attack(enemy);
>         if (enemy.hp() > 0) hero2.attack(enemy);
>     }
>
>     std::cout << "战斗结束，敌人剩余生命值：" << enemy.hp() << "\n";
> }
> ```
> 预期敌人会在剑士的第二次攻击后倒下，因为 `15 + 12 + 15 = 42 > 30`。

> [!tip]- 练习 3 参考答案
> 新增接口与 `Potion` 实现，然后在组合根中注入。注意 `Hero` 的构造器签名会变化，因此组合根需要同步更新。
>
> ```cpp
> class IHealingItem {
> public:
>     virtual ~IHealingItem() = default;
>     virtual int healAmount() const = 0;
>     virtual std::string name() const = 0;
> };
>
> class Potion : public IHealingItem {
> public:
>     int healAmount() const override { return 20; }
>     std::string name() const override { return "生命药水"; }
> };
>
> class Hero {
> public:
>     Hero(std::string name, IWeapon& weapon, ILogger& logger, IHealingItem& potion)
>         : name_(std::move(name)), weapon_(weapon), logger_(logger), potion_(potion) {}
>
>     void attack(Enemy& enemy) {
>         logger_.log(name_ + " 使用 " + weapon_.name() + " 攻击！");
>         enemy.takeDamage(weapon_.damage());
>         logger_.log(name_ + " 造成 " + std::to_string(weapon_.damage()) + " 点伤害");
>     }
>
>     void heal() {
>         logger_.log(name_ + " 喝下 " + potion_.name() + "，恢复 "
>                     + std::to_string(potion_.healAmount()) + " 点生命");
>     }
>
> private:
>     std::string name_;
>     IWeapon& weapon_;
>     ILogger& logger_;
>     IHealingItem& potion_;
> };
>
> int main() {
>     ConsoleLogger logger;
>     Sword sword;
>     Potion potion;
>
>     Hero hero("亚瑟", sword, logger, potion);
>     Enemy enemy(100);
>
>     hero.attack(enemy);
>     hero.heal();
> }
> ```
> 关键要点：`Potion` 作为新的叶子依赖，必须定义在 `Hero` 之前；组合根里的构造顺序保证了 `potion` 比 `hero` 活得更久。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- Mark Seemann, *Dependency Injection in .NET*, 第 4 章「Composition Root」——组合根概念的经典出处。
- CppCoreGuidelines: [C.31: All resources acquired by a class must be released by the class's destructor](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#c31-all-resources-acquired-by-a-class-must-be-released-by-the-classs-destructor) ——RAII 与对象生命周期的底层保证。
- Unity 文档：[Inspector 中的引用赋值](https://docs.unity3d.com/Manual/UsingTheInspector.html) ——可视化的组合根实践。
- 如果你想把手动装配演进成更系统的模式，请看第 10 节 [[10-builder-layered-wiring]]。
- 如果你想让 C++ 的组合根由容器自动完成，请看第 12 节 [[12-boost-di-cpp]]。

---

## 常见陷阱

- **在业务类里 `new` 依赖。** `Hero` 如果自己创建 `Sword` 或 `Logger`，就回到了紧耦合的老路，单元测试时很难替换。正确做法：把所有 `new` 留在组合根。
- **组合根里生命周期顺序写错。** 如果先定义 `Hero hero(...)`，再定义 `ConsoleLogger logger;`，`logger` 会在 `hero` 之后构造、却在 `hero` 之前析构，导致 `hero` 析构时引用已销毁对象。正确做法：依赖者必须后构造、先析构。
- **把组合根和业务逻辑混在一起。** 组合根只负责「创建和连接」，不应该包含游戏规则、AI 判定或网络同步。正确做法：组合根完成装配后，立刻把控制权交给业务系统。
- **认为组合根只适用于手动 DI。** 即使使用 DI 容器（如 .NET 的 `IServiceCollection` 或 C++ 的 `boost::di`），容器的配置代码仍然是组合根。正确做法：无论手动还是容器，装配逻辑都靠近入口点。
- **在组合根里硬编码所有条件分支。** 如果游戏有「开发模式 / 发布模式 / 测试模式」，不同模式下要装配不同实现，可以考虑工厂或配置对象辅助组合根。后续第 15 节 [[15-antipatterns-when-not]] 会讨论 Service Locator 等错误替代方案。
