---
title: 依赖注入的三种形式
updated: 2026-06-23
tags: [dependency-injection, cpp, constructor-injection, setter-injection, interface-injection]
---

# 依赖注入的三种形式

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 60min
> 前置知识: [[01-what-is-di-coupling]]

---

## 1. 概念讲解

### 1.1 从「给英雄配装备」说起

想象你在做一款 ARPG：英雄出场时要拿一把武器，战斗中还可能切换护甲、药水或技能。你至少有三种方式把装备交到英雄手里：

1. **出生时就配好**：英雄在创建瞬间必须拿到武器，没有武器的英雄不能存在。
2. **出生后随时换**：英雄先创建，之后通过背包界面把武器塞进去，战斗中也能切换。
3. **由外部系统主动装配**：英雄暴露一个「请给我武器」的接口，由装备管理员扫描后统一发放。

这三种方式，正好对应依赖注入的三种经典形式：

- **构造器注入（Constructor Injection）**
- **Setter / 属性注入（Setter Injection）**
- **接口注入（Interface Injection）**

Martin Fowler 在《Inversion of Control Containers and the Dependency Injection pattern》中把这三者并列为 DI 的主要实现形式。游戏开发里，我们打交道最多的是前两种；第三种在现代 C++ / C# 中已非常罕见，了解即可。

---

### 1.2 构造器注入：出生即完整

构造器注入把依赖作为参数传给构造函数，对象一创建就拿到全部必需品：

```cpp
class Hero {
public:
    Hero(IWeapon* weapon, ILogger* logger)
        : weapon_(weapon), logger_(logger) {}
    void attack();
private:
    IWeapon* weapon_;
    ILogger* logger_;
};
```

**优点：**

- **依赖在创建时即明确**：看一眼构造签名就知道 `Hero` 需要什么。
- **可声明为不可变**：在 C++ 里可以用 `IWeapon&` 或 `const` 指针成员表达「这把武器不会再换」；C# 里用 `readonly` 字段或 `{ get; init; }` 属性。
- **构造完成即处于有效状态**：调用者不可能拿到一个「有日志但没有武器」的半初始化英雄。
- **最符合游戏启动流程**：在 `main()` 或关卡加载时一次性装配好，进入热循环后不再分配。

**缺点：**

- **参数膨胀**：当英雄需要武器、护甲、技能、日志、输入、动画、音效……构造函数会变得很长。这正是第 10 节 [[10-builder-layered-wiring]] 要解决的场景。
- **循环依赖棘手**：如果 `Hero` 依赖 `Inventory`，`Inventory` 又依赖 `Hero`，构造器注入会互相卡住。

> **游戏开发建议**：构造器注入是默认选择。英雄的核心武器、必须的生命周期依赖，都通过构造函数传入。

---

### 1.3 Setter 注入：可选与热替换

Setter 注入在对象创建之后，通过 `setXxx()` 方法把依赖补进去：

```cpp
class Hero {
public:
    void setWeapon(IWeapon* weapon) { weapon_ = weapon; }
    void setArmor(Armor* armor)      { armor_ = armor; }
    void attack();
private:
    IWeapon* weapon_ = nullptr;
    Armor*   armor_  = nullptr;
};
```

**优点：**

- **可选依赖**：护甲、技能槽、临时 buff 可能没有，对象仍能创建。
- **运行时可热替换**：战斗中切换武器、换装备、切换坐骑，天然适合 Setter。
- **破解循环依赖**：`Hero` 用构造器注入 `Inventory`，`Inventory` 再用 Setter 把自身回注给 `Hero`。

**缺点：**

- **对象可能处于半初始化状态**：如果你忘了调用 `setWeapon()`，`attack()` 时可能空指针崩溃。
- **依赖变成「可选」容易被遗漏**：每个调用者都要记得 set，否则行为不稳定。
- **多线程下需要额外同步**：热替换依赖时，若另一个线程正在使用，需要锁或原子指针。

> **游戏开发建议**：把 Setter 留给「可选」或「运行中会变」的依赖，例如护甲、技能、皮肤、坐骑、运行时切换的武器。

---

### 1.4 接口注入：外部容器主动装配

接口注入要求被注入方实现一个专门的「接收接口」，注入器通过该接口把依赖塞进去：

```cpp
class IWeaponConsumer {
public:
    virtual ~IWeaponConsumer() = default;
    virtual void injectWeapon(IWeapon* weapon) = 0;
};

class Hero : public IWeaponConsumer {
public:
    void injectWeapon(IWeapon* weapon) override { weapon_ = weapon; }
    void attack();
private:
    IWeapon* weapon_ = nullptr;
};
```

容器/注入器会遍历所有实现了 `IWeaponConsumer` 的对象，统一调用 `injectWeapon()`。这种形式在 Martin Fowler 的原文里有提及，但在现代 C++/C# 生态里几乎绝迹，原因是：

- 每个依赖都要定义一个对应的 `IXxxConsumer` 接口，样板代码爆炸。
- 它把「业务类」和「注入协议」耦合在一起，反而增加了侵入性。
- 构造器注入和 Setter 注入已经能覆盖 99% 的场景。

> **游戏开发建议**：接口注入在 C++/C# 游戏中罕见。如果你在旧框架或某些 Java 容器里看到它，知道「这是 DI 的一种历史形式」即可，新项目不必采用。

---

### 1.5 三者取舍速览

| 形式 | 何时用 | 强制性 | 可变性 | 典型游戏场景 |
|------|--------|--------|--------|--------------|
| 构造器注入 | 依赖是对象运行的**必需品** | 强（无则无法创建） | 低（通常为只读/引用） | 英雄的核心武器、日志、渲染器 |
| Setter 注入 | 依赖**可选**或**运行中会变** | 弱（可后设） | 高（可热替换） | 护甲、技能、坐骑、战斗中切换武器 |
| 接口注入 | 旧容器/框架强制要求 | 中 | 中 | 现代游戏项目基本不用 |

一个简单记忆法：

- **构造器注入** = 出厂配置，不能没有。
- **Setter 注入** = 背包格子，可有可无，能随时换。
- **接口注入** = 老式装备管理员统一派发，现在很少见。

---

## 2. 代码示例

下面的 C++ 程序把三种注入形式放在同一个可运行示例里。为清晰起见，我们用原始指针；关于指针、引用和所有权的深入讨论在第 5 节 [[05-constructor-injection-ownership]]，智能指针在第 6 节 [[06-smart-pointers-lifetime]]。

```cpp
#include <iostream>
#include <memory>
#include <string>

// ========== 核心接口与实现 ==========
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

class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void log(const std::string& msg) = 0;
};

class ConsoleLogger : public ILogger {
public:
    void log(const std::string& msg) override {
        std::cout << "[log] " << msg << "\n";
    }
};

// ========== 接口注入协议 ==========
class IWeaponConsumer {
public:
    virtual ~IWeaponConsumer() = default;
    virtual void injectWeapon(IWeapon* weapon) = 0;
};

// ========== 英雄：支持三种注入形式 ==========
class Hero : public IWeaponConsumer {
public:
    // 1. 构造器注入：核心武器 + 日志
    Hero(IWeapon* weapon, ILogger* logger)
        : weapon_(weapon), logger_(logger) {
        std::cout << "Hero 创建完成，装备: " << weapon_->name() << "\n";
    }

    // 2. Setter 注入：可选护甲（本例简化为一个整数减伤）
    void setArmorReduction(int reduction) {
        armor_reduction_ = reduction;
        logger_->log("装备了护甲，减伤 " + std::to_string(reduction));
    }

    // 3. 接口注入：外部容器统一调用
    void injectWeapon(IWeapon* weapon) override {
        weapon_ = weapon;
        logger_->log("接口注入切换武器: " + weapon->name());
    }

    void attack() {
        int dmg = std::max(0, weapon_->damage() - armor_reduction_);
        logger_->log("Hero 用 " + weapon_->name() + " 造成 " +
                     std::to_string(dmg) + " 点伤害");
    }

private:
    IWeapon* weapon_;
    ILogger* logger_;
    int armor_reduction_ = 0;
};

// 一个极简的「注入器」，扫描并调用接口注入
class SimpleInjector {
public:
    void registerWeapon(IWeapon* weapon) { weapon_ = weapon; }
    void injectInto(IWeaponConsumer& consumer) {
        consumer.injectWeapon(weapon_);
    }
private:
    IWeapon* weapon_ = nullptr;
};

int main() {
    Sword sword;
    Bow bow;
    ConsoleLogger logger;

    // 构造器注入：英雄出生就有武器和日志
    Hero hero(&sword, &logger);

    // Setter 注入：后续装备护甲
    hero.setArmorReduction(3);

    hero.attack();

    // 接口注入：外部注入器把长弓注入英雄
    SimpleInjector injector;
    injector.registerWeapon(&bow);
    injector.injectInto(hero);

    hero.attack();

    return 0;
}
```

**运行方式：**

```bash
g++ -std=c++17 three-forms.cpp -o three-forms
./three-forms
```

**预期输出：**

```text
Hero 创建完成，装备: 铁剑
[log] 装备了护甲，减伤 3
[log] Hero 用 铁剑 造成 12 点伤害
[log] 接口注入切换武器: 长弓
[log] Hero 用 长弓 造成 9 点伤害
```

---

### 2.1 C# 对照

C# 里构造器注入和属性注入（Property Injection）非常常见。Unity 老代码常见 `[SerializeField]` 字段注入，.NET Core 服务容器则普遍用构造器注入。

```csharp
using System;

public interface IWeapon {
    int Damage { get; }
    string Name { get; }
}

public interface ILogger {
    void Log(string msg);
}

public sealed class Sword : IWeapon {
    public int Damage => 15;
    public string Name => "铁剑";
}

public sealed class Bow : IWeapon {
    public int Damage => 12;
    public string Name => "长弓";
}

public sealed class ConsoleLogger : ILogger {
    public void Log(string msg) => Console.WriteLine($"[log] {msg}");
}

public sealed class Hero {
    // 构造器注入：核心武器（必需）
    private readonly IWeapon _weapon;
    private readonly ILogger _logger;

    // 属性注入：可选护甲，运行中可换
    public int ArmorReduction { get; set; } = 0;

    public Hero(IWeapon weapon, ILogger logger) {
        _weapon = weapon;
        _logger = logger;
    }

    public void Attack() {
        int dmg = Math.Max(0, _weapon.Damage - ArmorReduction);
        _logger.Log($"Hero 用 {_weapon.Name} 造成 {dmg} 点伤害");
    }
}

class Program {
    static void Main() {
        var sword = new Sword();
        var logger = new ConsoleLogger();

        var hero = new Hero(sword, logger);
        hero.ArmorReduction = 3;
        hero.Attack();
    }
}
```

**运行方式：**

```bash
dotnet new console -n DiThreeForms
cd DiThreeForms
# 将上面的代码写入 Program.cs
dotnet run
```

**预期输出：**

```text
[log] Hero 用 铁剑 造成 12 点伤害
```

> [!note] C# 的 `[property]IWeapon Weapon` 注入
> 某些旧版 Unity 或属性注入框架允许 `[Inject] public IWeapon Weapon { get; set; }`。在 .NET 泛型容器（`Microsoft.Extensions.DependencyInjection`）中，构造器注入是首选；属性注入一般只用于 Unity 场景脚本里的 `[SerializeField]` 拖拽赋值。第 11 节 [[11-di-containers-csharp]] 会展开容器注册与解析。

---

## 3. 练习

### 练习 1: 基础

把上面 C++ 示例中的 `Hero` 改成「核心武器用构造器注入、可选护甲用 Setter 注入、武器仍可用接口注入切换」，但让 `Hero` 在构造器中要求 `ILogger` 而不能为 `nullptr`。写出新的构造函数签名。

### 练习 2: 进阶

假设你的游戏有一个 `PlayerInput` 依赖（处理键盘/手柄输入），它必须在游戏运行中切换（例如本地双人模式切换 `#1`/`#2` 号玩家的输入源）。你会选择哪种注入形式？说明理由，并写出关键代码片段。

### 练习 3: 挑战（可选）

在不使用接口注入的情况下，用构造器注入 + Setter 注入实现一个「装备管理器」：

- `Hero` 构造时必须拿到 `IWeapon*` 和 `ILogger*`。
- 提供一个 `equip(IWeapon*)` 方法在运行时切换武器。
- 在 `main()` 中先创建一把 `Sword`，然后中途切换为 `Bow`。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 构造器强制要求 `ILogger*`，核心武器也通过构造器传入，护甲通过 Setter 后设：
>
> ```cpp
> class Hero {
> public:
>     Hero(IWeapon* weapon, ILogger* logger)
>         : weapon_(weapon), logger_(logger) {
>         if (!logger_) throw std::invalid_argument("logger cannot be null");
>     }
>     void setArmorReduction(int reduction) { armor_reduction_ = reduction; }
>     void attack();
> private:
>     IWeapon* weapon_;
>     ILogger* logger_;
>     int armor_reduction_ = 0;
> };
> ```
> 这样 `Hero` 创建时一定有武器和日志，但护甲是可选的。

> [!tip]- 练习 2 参考答案
> 选择 **Setter 注入**（或属性注入）。
>
> 理由：
> - `PlayerInput` 是运行中可替换的依赖，不同玩家、不同控制设备都可能变化。
> - 构造器注入会把「输入源」变成创建时就必须确定的强依赖，不利于热切换。
> - Setter 注入允许在游戏循环中随时 `hero.setInput(&gamepadInput)`。
>
> 关键片段：
>
> ```cpp
> class Hero {
> public:
>     void setInput(IPlayerInput* input) { input_ = input; }
>     void update() {
>         if (input_ && input_->attackPressed()) attack();
>     }
> private:
>     IPlayerInput* input_ = nullptr;
> };
> ```

> [!tip]- 练习 3 参考答案（可选）
> 下面是一个完整可运行实现：
>
> ```cpp
> #include <iostream>
> #include <string>
> #include <algorithm>
>
> class IWeapon {
> public:
>     virtual ~IWeapon() = default;
>     virtual int damage() const = 0;
>     virtual std::string name() const = 0;
> };
>
> class Sword : public IWeapon {
> public:
>     int damage() const override { return 15; }
>     std::string name() const override { return "铁剑"; }
> };
>
> class Bow : public IWeapon {
> public:
>     int damage() const override { return 12; }
>     std::string name() const override { return "长弓"; }
> };
>
> class ILogger {
> public:
>     virtual ~ILogger() = default;
>     virtual void log(const std::string& msg) = 0;
> };
>
> class ConsoleLogger : public ILogger {
> public:
>     void log(const std::string& msg) override {
>         std::cout << "[log] " << msg << "\n";
>     }
> };
>
> class Hero {
> public:
>     Hero(IWeapon* weapon, ILogger* logger)
>         : weapon_(weapon), logger_(logger) {}
>
>     void equip(IWeapon* weapon) {
>         weapon_ = weapon;
>         logger_->log("切换武器为: " + weapon->name());
>     }
>
>     void attack() {
>         logger_->log("Hero 用 " + weapon_->name() +
>                      " 造成 " + std::to_string(weapon_->damage()) +
>                      " 点伤害");
>     }
>
> private:
>     IWeapon* weapon_;
>     ILogger* logger_;
> };
>
> int main() {
>     Sword sword;
>     Bow bow;
>     ConsoleLogger logger;
>
>     Hero hero(&sword, &logger);
>     hero.attack();
>     hero.equip(&bow);
>     hero.attack();
> }
> ```
>
> 运行输出：
>
> ```text
> [log] Hero 用 铁剑 造成 15 点伤害
> [log] 切换武器为: 长弓
> [log] Hero 用 长弓 造成 12 点伤害
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Martin Fowler: Inversion of Control Containers and the Dependency Injection pattern](https://martinfowler.com/articles/injection.html) —— 三种注入形式的经典原文。
- [Martin Fowler: Constructor Injection](https://martinfowler.com/articles/dipInTheWild.html) —— 更深入的构造器注入讨论。
- [Microsoft: Dependency injection in .NET](https://learn.microsoft.com/en-us/dotnet/core/extensions/dependency-injection) —— C# 服务容器默认使用构造器注入。
- [Unity Manual: Serialized fields](https://docs.unity3d.com/Manual/UnityAttributes.html) —— Unity 中 `[SerializeField]` 字段注入与 DI 的关系。
- 后续章节：
  - 构造器注入与所有权 → [[05-constructor-injection-ownership]]
  - C# DI 容器 → [[11-di-containers-csharp]]
  - Builder 与分层装配 → [[10-builder-layered-wiring]]

---

## 5. 常见陷阱

- **把所有依赖都做成 Setter**：这会让对象随时处于半初始化状态，调用前必须检查 `nullptr`。核心依赖（武器、日志、渲染器）应优先用构造器注入，只有可选/可热切换依赖才用 Setter。

- **构造器参数过多时硬撑**：当 `Hero` 需要 7 个依赖时，不要继续拉长构造函数，而是引入一个 Builder 或工厂（见第 10 节 [[10-builder-layered-wiring]]）。

- **误以为接口注入更「正统」**：Martin Fowler 列出三种形式并不等于三者同样推荐。现代 C++/C# 游戏里，接口注入基本消失，新项目不必为了「完整」而引入它。

- **C# 里滥用 `[SerializeField]` 注入**：Unity 拖拽赋值很方便，但它本质上是运行时装配，容易在场景丢失引用时报错。对于跨场景的持久服务，应使用真正的构造器注入或服务定位器容器（第 11 节 [[11-di-containers-csharp]]）。

- **忽略多线程下的 Setter 注入**：如果游戏循环线程和装备切换线程同时访问 `weapon_`，裸指针或引用可能引发数据竞争。热替换依赖时请使用原子指针、`std::shared_ptr` 或显式锁保护（第 6 节 [[06-smart-pointers-lifetime]]）。
