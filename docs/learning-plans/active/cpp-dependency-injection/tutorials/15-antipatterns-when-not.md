---
title: DI 反模式与何时不用
updated: 2026-06-23
tags: [dependency-injection, cpp, antipatterns, service-locator, ambient-context]
---

# DI 反模式与何时不用

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 60min
> 前置知识: [[02-ioc-dip-di-principles]]

---

## 1. 概念讲解

### 1.1 从「快捷小路」说起

想象你正在做一个动作 RPG。第 `#1` 天，你写了一个 `Hero` 类，让它直接用 `ServiceLocator::Get<IWeapon>()` 拿武器；第 `#2` 天，你在伤害计算里写 `Time::deltaTime`；第 `#3` 天，某个技能系统内部 `new SqlRepo()` 存数据。三条路看起来都省了几分钟，半年后它们变成了测试灾难：

- 想给 `Hero` 写一个单元测试？先设置全局定位器。
- 想验证技能在 60fps 和 30fps 下的伤害一致性？改不了 `Time::deltaTime`。
- 想离线跑战斗系统？`SqlRepo` 连不上数据库就崩。

这些就是 **DI 反模式（Antipatterns）**：它们不是「错误代码」，而是**短期内方便、长期拖慢团队的惯用法**。学会识别它们，才能知道 DI 真正在保护什么，也才能在游戏引擎（Unity/Unreal）的现实中做出不教条的选择。

---

### 1.2 Service Locator（服务定位器）反模式

**Service Locator** 让类不在构造器里声明依赖，而是在运行时主动问一个全局注册表要对象：

```cpp
class Hero {
public:
    void attack() {
        auto& weapon = ServiceLocator::Get<IWeapon>();
        weapon.use();
    }
};
```

表面看，这和构造器注入都能换实现；但本质区别在于：

| 维度 | 构造器注入 | Service Locator |
|------|-----------|-----------------|
| 依赖是否可见 | `Hero(IWeapon&, ILogger&)` 一眼看完 | 从签名看不出依赖 |
| 测试替换 | 直接传 `MockWeapon` | 必须先设置全局定位器状态 |
| 生命周期 | 由调用方/组合根决定 | 隐藏在定位器内部 |
| 错误时机 | 编译期即可发现缺依赖 | 运行时才可能 `Get` 失败 |

> [!warning] Service Locator 不等于 DI 容器
> DI 容器在应用启动时一次性解析依赖（[[07-composition-root-wiring]]），之后对象拿到的是**已注入**的依赖。Service Locator 则是业务类在运行时**主动索取**。前者是「装配厂把零件装好再交货」，后者是「零件自己跑去仓库拿」。

Unity 的 `FindObjectOfType<T>()`、Unreal 某些老代码里的 `GEngine->Get...()` 静态单例、自研引擎的 `g_WeaponManager`，本质都是 Service Locator。原型期它们很快；项目成长后，任何测试都要先「污染」全局状态，任何依赖变更都要全局搜调用点。

---

### 1.3 Ambient Context（环境上下文）反模式

Ambient Context 把依赖藏得更深：不是通过参数，而是通过**全局可访问的静态状态**进入你的代码。

```cpp
float DamageSystem::compute() {
    return baseDamage * Time::deltaTime;   // 隐式依赖全局时间
}
```

游戏里常见的 Ambient Context 包括：

- `Time::deltaTime`、`Time::time`、`DateTime.Now`
- `Input::isPressed(Action.Attack)`
- `Random::range(0, 100)`（不可种子化）
- 全局帧计数器、全局物理世界

问题：**你的函数签名撒谎了**。`compute()` 看起来只依赖 `baseDamage`，实际上还依赖时间。测试时你无法控制时间流逝，也无法并行跑两个不同时间的测试用例。

正确做法是把环境依赖显式化：

```cpp
float compute(float deltaTime) {
    return baseDamage * deltaTime;
}
```

或者通过接口注入（[[03-three-forms-of-di]]），让测试传入一个冻结的时间源。

---

### 1.4 Control Freak / 内部 new

**Control Freak** 指业务类自己 `new` 出依赖，牢牢控制依赖创建：

```cpp
class Hero {
    Sword weapon_;          // 直接依赖具体类
    ConsoleLogger logger_;  // 内部创建
public:
    void attack() { weapon_.use(); logger_.log("攻击"); }
};
```

这在 [[01-what-is-di-coupling]] 里已经批判过：高层 `Hero` 直接依赖低层 `Sword`，违反 DIP。更隐蔽的写法是内部 `new` 一个接口实现：

```cpp
class Hero {
    std::unique_ptr<IWeapon> weapon_;
public:
    Hero() : weapon_(std::make_unique<Sword>()) {}  // 仍然写死
};
```

即使注入的是抽象类型，只要创建逻辑锁死在类内部，就失去了可替换性和可测试性。

---

### 1.5 过度抽象：给唯一实现硬造接口

不是所有类都需要接口。如果你的 `Hero` 目前只有一种武器 `Sword`，却硬抽出 `IWeapon`，代码会变成：

```cpp
class IWeapon { virtual int damage() const = 0; ... };
class Sword : public IWeapon { ... };
class Hero { Hero(IWeapon& w) ... };
```

如果未来半年都不会有第二种武器，这就是 **YAGNI（You Aren't Gonna Need It）**。接口带来虚函数开销、头文件膨胀、心智负担。判断标准：

| 应该抽象 | 不该抽象 |
|----------|----------|
| 有多个实现（Sword/Bow/Staff） | 只有一个实现，且短期看不到第二个 |
| 需要单元测试替换（数据库、网络、随机数） | 纯值对象、工具函数 |
| 由不同团队维护、需要稳定契约 | 只在模块内部使用的辅助类 |

> [!tip] 延迟抽象
> 可以先写具体类，等出现第二个实现或第一个测试需要 Mock 时，再抽取接口。C++ 里这比 Java/C# 更实际，因为抽接口会改变二进制布局和性能特征。

---

### 1.6 构造器过度注入：是 DI 问题还是 SRP 问题？

当一个类的构造器出现 10+ 个参数：

```cpp
class Hero {
public:
    Hero(IWeapon&, IArmor&, ISkill&, IBuff&, ILogger&, IAnalytics&,
         IInput&, IInventory&, IAchievement&, INetwork&, IAssetLoader&);
};
```

不要第一反应是「DI 不好用」。这通常是 **SRP（单一职责原则）Violation**。`Hero` 已经不是一个「战斗角色」，而是一个什么都管的上帝类。解法不是减少依赖（瞒天过海），而是拆分：

- `CombatController`：武器、防具、技能、Buff
- `InventoryController`：背包
- `AchievementTracker`：成就
- `AnalyticsEmitter`：埋点

每个子系统再通过 [[10-builder-layered-wiring]] 里的 Builder 或 [[07-composition-root-wiring]] 里的组合根装配。DI 只是把问题**显式化**；问题本身要靠设计解决。

---

### 1.7 何时不用 DI

DI 不是宗教。以下几种情况，教条式注入反而碍事：

1. **一次性脚本与原型验证**
   - Game Jam、关卡编辑器脚本、编辑器工具脚本。目标是快，不是可测试。

2. **性能极致的内核循环**
   - ECS 的 System 里处理 10k 个实体，每帧调用。此时虚函数分发都可能成为瓶颈，应使用静态多态（[[08-templates-static-polymorphism]]）或直接内联调用。

3. **依赖极少且极其稳定**
   - 一个只依赖 `<cmath>` 的 `Vec3` 工具类，没有可变性需求，没必要注入。

4. **纯数据/值对象**
   - `WeaponConfig` 结构体、JSON 配置数据，直接传值即可。

5. **框架已接管生命周期**
   - Unity 的 `MonoBehaviour` 由引擎创建，强行用 C# DI 容器注入反而和引擎生命周期打架。可以在高层用 Service Locator 做桥接，但要有意识它是技术债。

> [!note] 判断标准
> 当「替换依赖」或「独立测试」的收益小于「抽象成本」时，就不用 DI。这个边界随项目阶段移动：原型期靠右，上线前夕靠左。

---

### 1.8 游戏开发现实：Service Locator 到 DI 的演进

Unity 和 Unreal 的代码库里，Service Locator 随处可见：

| 引擎/框架 | Service Locator 形式 |
|-----------|----------------------|
| Unity | `FindObjectOfType<T>()`、`GameObject.Find` |
| Unreal | 静态单例、Subsystem 的 `Get()`、各种 `GEngine` 访问 |
| 自研引擎 | 全局管理器、静态 `g_XxxManager` |

它们不是恶魔。原型期让你第 `#1` 天就能看到角色挥剑；但成长后：

- 测试需要「伪造」整个场景。
- 多人协作时不知道一个类到底依赖什么。
- 生命周期 bug 在运行时才暴露。

**演进建议**：

1. **原型期**：允许 Service Locator，但要明确标记为「技术债」。
2. **成长期**：把核心系统（战斗、输入、存档、网络）迁移到构造器注入 + 组合根。
3. **稳定期**：对仍需引擎单例的边界，用 Adapter/Facade 包装，把 Service Locator 隔离在组合根，不让它渗透到业务逻辑。

---

## 2. 代码示例

下面的完整示例对比了两种 `Hero`：一种用 Service Locator，一种用构造器注入。你会看到前者在测试中需要设置全局状态，而后者只需传一个 `MockWeapon`。

```cpp
// main.cpp
#include <iostream>
#include <memory>
#include <string>
#include <stdexcept>
#include <unordered_map>
```

// ==================== 核心接口与实现 ====================
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

// ==================== Service Locator 反模式 ====================
class ServiceLocator {
public:
    template<typename T>
    static T& Get() {
        auto it = instance().services_.find(typeid(T).name());
        if (it == instance().services_.end()) {
            throw std::runtime_error("Service not registered");
        }
        return *static_cast<T*>(it->second.get());
    }

    template<typename T, typename Impl>
    static void Register() {
        auto deleter = [](void* p) { delete static_cast<Impl*>(p); };
        instance().services_[typeid(T).name()] = {
            std::make_unique<Impl>().release(),
            deleter
        };
    }

    static void Reset() {
        instance().services_.clear();
    }

private:
    static ServiceLocator& instance() {
        static ServiceLocator loc;
        return loc;
    }
    std::unordered_map<std::string, std::shared_ptr<void>> services_;
};

class ServiceLocatorHero {
public:
    void attack() {
        auto& weapon = ServiceLocator::Get<IWeapon>();
        auto& logger = ServiceLocator::Get<ILogger>();
        logger.log(weapon.name() + " 造成 " + std::to_string(weapon.damage()) + " 点伤害");
    }
};

// ==================== 构造器注入（正确做法） ====================
class Hero {
public:
    Hero(IWeapon& weapon, ILogger& logger)
        : weapon_(weapon), logger_(logger) {}

    void attack() {
        logger_.log(weapon_.name() + " 造成 " + std::to_string(weapon_.damage()) + " 点伤害");
    }
private:
    IWeapon& weapon_;
    ILogger& logger_;
};

// ==================== 测试替身 ====================
class MockWeapon : public IWeapon {
public:
    int damage() const override { return 999; }
    std::string name() const override { return "测试之剑"; }
};

class MockLogger : public ILogger {
public:
    std::string lastMsg;
    void log(const std::string& msg) override { lastMsg = msg; }
};

// ==================== 测试 ====================
void testServiceLocatorHero() {
    std::cout << "\n--- Service Locator Hero 测试 ---\n";
    ServiceLocator::Reset();
    ServiceLocator::Register<IWeapon, Sword>();
    ServiceLocator::Register<ILogger, ConsoleLogger>();

    ServiceLocatorHero hero;
    hero.attack();

    // 想换 MockWeapon？必须改全局状态，影响其他测试
}

void testConstructorInjectedHero() {
    std::cout << "\n--- 构造器注入 Hero 测试 ---\n";
    MockWeapon weapon;
    MockLogger logger;
    Hero hero(weapon, logger);
    hero.attack();
    std::cout << "捕获日志: " << logger.lastMsg << "\n";
}

int main() {
    testServiceLocatorHero();
    testConstructorInjectedHero();
    return 0;
}
```

**运行方式：**

```bash
g++ -std=c++17 main.cpp -o demo
./demo
```

**预期输出：**

```text
--- Service Locator Hero 测试 ---
[log] 铁剑 造成 15 点伤害

--- 构造器注入 Hero 测试 ---
捕获日志: 测试之剑 造成 999 点伤害
```

关键观察：构造器注入的测试里，`MockWeapon` 和 `MockLogger` 是**局部创建**的，测试之间互不污染；而 Service Locator 版本必须依赖全局定位器的状态，多个测试并行时容易互相影响。

---

## 3. 练习

### 练习 1: 基础

列举 Service Locator 相比构造器注入的三个缺点，并说明为什么它们在游戏开发中尤其危险。

### 练习 2: 进阶

下面的 `DamageSystem` 使用了 Ambient Context 反模式。请把它改写成「显式依赖」风格，并写一个简单的测试，验证在 `deltaTime = 0.5f` 时伤害被正确缩放。

```cpp
class DamageSystem {
    int baseDamage_ = 100;
public:
    int compute() {
        return static_cast<int>(baseDamage_ * Time::deltaTime);
    }
};
```

### 练习 3: 挑战（可选）

你正在维护一个 Unreal 项目，核心战斗逻辑大量通过 `GetGameInstance()->GetSubsystem<UWeaponSubsystem>()` 获取武器数据。请给出一份分阶段迁移到 DI 的路线图，说明每个阶段保留什么、替换什么、风险点在哪里。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 1. **依赖隐藏**：构造器签名无法告诉你 `Hero` 需要武器和日志，新人阅读代码时必须翻遍函数体才能发现依赖关系。在大型游戏代码库里，这会让重构变成「全局搜索大冒险」。
> 2. **测试污染**：每次测试都要先 `Register` 全局服务，测试之间会互相泄漏状态。一旦并发跑测试，定位器里的实现可能被另一个测试覆盖，导致 flaky test。
> 3. **运行时失败**：如果某个服务忘记注册，`ServiceLocator::Get<T>()` 会在运行时才抛异常；而构造器注入在创建对象时就能发现缺依赖，错误提前到编译/启动期。

> [!tip]- 练习 2 参考答案
> 把全局 `Time::deltaTime` 改成参数传入：
>
> ```cpp
> class DamageSystem {
>     int baseDamage_ = 100;
> public:
>     int compute(float deltaTime) {
>         return static_cast<int>(baseDamage_ * deltaTime);
>     }
> };
> ```
>
> 测试：
>
> ```cpp
> int main() {
>     DamageSystem ds;
>     int result = ds.compute(0.5f);
>     std::cout << (result == 50 ? "PASS" : "FAIL") << "\n";
>     return 0;
> }
> ```
>
> 更进一步，如果 `Time` 本身复杂（比如需要暂停、缩放、网络同步），可抽象出 `ITimeSource` 接口并通过构造器注入。

> [!tip]- 练习 3 参考答案（可选）
> 分三阶段迁移：
>
> | 阶段 | 保留 | 替换 | 风险 |
> |------|------|------|------|
> | 第 `#1` 阶段：隔离边界 | Subsystem 继续存在 | 在 Subsystem 里加 `GetWeaponData(id)` 接口，减少业务代码直接访问引擎 API | 接口设计不稳定 |
> | 第 `#2` 阶段：业务层注入 | Unreal 的 Actor/Component 生命周期 | 战斗 System 内部改为依赖接口，例如 `IWeaponDataProvider`，由某个 `UCombatSetupComponent` 注入 | 需要改大量现有测试 |
> | 第 `#3` 阶段：组合根装配 | Subsystem 作为底层数据源 | 在 GameMode/GameInstance 初始化时一次性装配所有战斗对象，业务代码只认识抽象 | 启动顺序和生命周期变复杂 |
>
> 关键原则：不要一次性全改；先把 Service Locator 赶到代码边缘，再逐步替换。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- Martin Fowler, [Inversion of Control Containers and the Dependency Injection pattern](https://martinfowler.com/articles/injection.html) —— 区分 Service Locator 与 DI 的经典文章。
- Mark Seemann & Steven van Deursen, *Dependency Injection Principles, Practices, and Patterns* —— 第 5 章详细讨论 Service Locator 为什么是反模式，以及 Ambient Context 的危害。
- Unity 官方文档：[Scene Search](https://docs.unity3d.com/Manual/SceneSearch.html) 与 `FindObjectOfType` 的局限性。
- Unreal Engine 文档：[Game Features and Modular Gameplay](https://docs.unrealengine.com/5.0/en-US/game-features-and-modular-gameplay-in-unreal-engine/) —— 了解 Unreal 推荐的模块化替代方案。

---

## 常见陷阱

- **把 Service Locator 当成 DI 容器**：DI 容器在组合根一次性装配，业务代码不直接调用容器；Service Locator 把全局查找散落到业务代码里。混淆二者会让团队以为「已经在做 DI」，实际上依赖仍然隐藏。
- **为了测试而造接口**：不是每个类都需要接口。先观察是否真的有第二个实现或测试替换需求，再决定是否抽象，避免 YAGNI。
- **构造器参数过多就责怪 DI**：10+ 参数的构造器通常是类职责过大的信号，应该拆分职责并用 Builder 装配（[[10-builder-layered-wiring]]），而不是放弃 DI。
- **Ambient Context 披着「工具类」外衣**：`Time::deltaTime`、`Random::value` 看起来人畜无害，但它们让你的函数签名撒谎，也让测试无法控制。优先把环境依赖显式化。
- **「引擎就是单例，所以 DI 不现实」**：引擎单例可以作为组合根的数据源，但不应该渗透到业务规则层。用 Adapter 把它们隔离在边界。

---

下一节是综合项目：[[16-capstone-game-combat]]。
