---
title: 综合项目：可测试的游戏战斗系统
updated: 2026-06-23
tags: [dependency-injection, cpp, capstone, testing, game-development]
---

# 综合项目：可测试的游戏战斗系统

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 150min
> 前置知识: 全部前置章节，核心为 [[05-constructor-injection-ownership]]、[[07-composition-root-wiring]]、[[09-type-erasure-std-function]]、[[14-testing-with-di-mocks]]

---

## 1. 概念讲解

### 1.1 从「全耦合的 `MonoBehaviour`」到「可测试的核心逻辑」

想象你正在 Unity 里写一个 `CombatManager`：它直接 `GameObject.Find("Hero")` 拿角色、直接读取 `PlayerPrefs` 里的装备配置、直接调用 `Instantiate(bloodEffect)` 播放特效。这种写法在原型期很快，但一到测试就头疼——想跑一个「勇者攻击史莱姆」的单元测试，必须先启动渲染线程、加载场景、初始化物理。

本节的思路是：**把战斗核心逻辑从「真实环境」里剥出来**。所谓真实环境，包括渲染、输入、网络、存档、音效。核心逻辑只关心：

- 谁持有哪把武器？
- 伤害怎么算？
- 生命值怎么扣？
- 击杀后触发什么事件？

这些逻辑不依赖 `UnityEngine`、不依赖 `std::cin`、不依赖真实文件系统，因此可以在纯 C++ 测试框架里直接验证。这正是依赖注入（DI）在游戏开发里最常见的价值之一。

> [!info] 项目目标
> 交付一个多文件 C++17 项目：含抽象接口、具体实现、事件总线、战斗角色、组合根与单元测试。核心逻辑零外部依赖，可脱离游戏引擎运行。

### 1.2 项目架构一览

| 文件 | 职责 | 对应章节 |
|------|------|----------|
| `interfaces.hpp` | 定义 `IWeapon`、`ILogger`、`IDamageCalculator`、`IHealth` | [[04-cpp-interfaces-abc]] |
| `implementations.hpp` / `.cpp` | `Sword`、`Bow`、`ConsoleLogger`、`NormalDamageCalculator` | [[04-cpp-interfaces-abc]]、[[06-smart-pointers-lifetime]] |
| `event_bus.hpp` | 基于 `std::function` 的伤害事件总线 | [[09-type-erasure-std-function]] |
| `combatant.hpp` / `.cpp` | `Combatant`（即 `Hero` / `Enemy`），构造器注入所有依赖 | [[05-constructor-injection-ownership]]、[[06-smart-pointers-lifetime]] |
| `composition_root.cpp` | `main()` 组合根，一次性装配所有对象 | [[07-composition-root-wiring]] |
| `combat_tests.cpp` | GoogleTest 测试，注入 Mock 对象 | [[14-testing-with-di-mocks]] |
| `CMakeLists.txt` | 构建配置，自动拉取 GoogleTest | — |

### 1.3 最终对象图

下面的 mermaid 图展示了组合根里创建的所有对象及依赖关系。注意 `logger`、`eventBus`、`calculator` 被 `Hero` 和 `Enemy` **共享**（类似 Singleton/Scoped 生命周期），而 `sword` 和 `bow` 分别属于两个角色（Transient 生命周期）。

```mermaid
classDiagram
    direction LR
    class main["main() 组合根"]

    class logger["logger (ConsoleLogger)"]
    class bus["eventBus (EventBus)"]
    class calc["calculator (NormalDamageCalculator)"]
    class sword["sword (Sword)"]
    class bow["bow (Bow)"]
    class hero["hero (Combatant)"]
    class enemy["enemy (Combatant)"]

    main ..> logger : std::make_shared
    main ..> bus : std::make_shared
    main ..> calc : std::make_shared
    main ..> sword : std::make_shared
    main ..> bow : std::make_shared
    main ..> hero : 注入所有共享依赖
    main ..> enemy : 注入所有共享依赖

    hero o-- sword : IWeapon
    hero o-- calc : IDamageCalculator
    hero o-- logger : ILogger
    hero o-- bus : EventBus

    enemy o-- bow : IWeapon
    enemy o-- calc : IDamageCalculator
    enemy o-- logger : ILogger
    enemy o-- bus : EventBus

    bus ..> hero : subscribe lambda
```

### 1.4 为什么「可测试」？

`Combatant` 不直接 `new Sword()`，也不调用全局 `Logger::Instance()`。它通过构造器接收接口：

```cpp
Combatant(std::string name, int maxHealth,
          std::shared_ptr<IWeapon> weapon,
          std::shared_ptr<IDamageCalculator> calc,
          std::shared_ptr<ILogger> logger,
          std::shared_ptr<EventBus> eventBus);
```

测试时，我们可以传入 `MockWeapon`、`MockCalculator`、`MockLogger`，完全控制输入与观测输出：

- 把 `MockCalculator` 的返回值固定为 `30`，就能断言敌人从 `30` 血被一击必杀。
- 订阅 `EventBus`，就能断言攻击确实发布了 `DamageEvent`。
- 检查 `MockLogger` 收到的消息，就能断言日志内容。

这种能力在真实游戏开发中极其宝贵：你可以在 CI 里几秒跑完几百个战斗规则测试，而不用启动整个游戏客户端。

---

## 2. 代码示例

### 2.1 `interfaces.hpp` — 抽象接口

```cpp
#pragma once
#include <memory>
#include <string>

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

class IDamageCalculator {
public:
    virtual ~IDamageCalculator() = default;
    virtual int calculate(int baseDamage, bool isCritical) const = 0;
};

class IHealth {
public:
    virtual ~IHealth() = default;
    virtual int current() const = 0;
    virtual int max() const = 0;
    virtual bool isAlive() const = 0;
    virtual void takeDamage(int amount) = 0;
};
```

> `IHealth` 在本项目中作为「可进一步拆分为独立生命值组件」的接口保留；当前实现把生命值直接内聚在 `Combatant` 里，读者可在扩展练习中将其抽离。

### 2.2 `event_bus.hpp` — 类型擦除事件总线

```cpp
#pragma once
#include <functional>
#include <vector>
#include <string>

struct DamageEvent {
    std::string attacker;
    std::string defender;
    int damage;
    bool fatal;
};

class EventBus {
public:
    using DamageHandler = std::function<void(const DamageEvent&)>;

    void subscribe(DamageHandler handler) {
        handlers_.push_back(std::move(handler));
    }

    void publish(const DamageEvent& event) const {
        for (const auto& handler : handlers_) {
            handler(event);
        }
    }
private:
    std::vector<DamageHandler> handlers_;
};
```

### 2.3 `implementations.hpp` / `.cpp` — 具体实现

`implementations.hpp`：

```cpp
#pragma once
#include "interfaces.hpp"
#include <iostream>

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

class Axe : public IWeapon {
public:
    int damage() const override { return 18; }
    std::string name() const override { return "战斧"; }
};

class ConsoleLogger : public ILogger {
public:
    void log(const std::string& msg) override;
};

class NormalDamageCalculator : public IDamageCalculator {
public:
    explicit NormalDamageCalculator(int critMultiplier = 2, int armorReduction = 0);
    int calculate(int baseDamage, bool isCritical) const override;
private:
    int critMultiplier_;
    int armorReduction_;
};
```

`implementations.cpp`：

```cpp
#include "implementations.hpp"
#include <algorithm>

void ConsoleLogger::log(const std::string& msg) {
    std::cout << "[战斗日志] " << msg << "\n";
}

NormalDamageCalculator::NormalDamageCalculator(int critMultiplier, int armorReduction)
    : critMultiplier_(critMultiplier), armorReduction_(armorReduction) {}

int NormalDamageCalculator::calculate(int baseDamage, bool isCritical) const {
    int damage = baseDamage;
    if (isCritical) {
        damage *= critMultiplier_;
    }
    damage = std::max(0, damage - armorReduction_);
    return damage;
}
```

### 2.4 `combatant.hpp` / `.cpp` — 战斗角色

`combatant.hpp`：

```cpp
#pragma once
#include "interfaces.hpp"
#include "event_bus.hpp"
#include <memory>
#include <string>

class Combatant {
public:
    Combatant(std::string name, int maxHealth,
              std::shared_ptr<IWeapon> weapon,
              std::shared_ptr<IDamageCalculator> calc,
              std::shared_ptr<ILogger> logger,
              std::shared_ptr<EventBus> eventBus);

    const std::string& name() const;
    int health() const;
    int maxHealth() const;
    bool isAlive() const;

    void attack(Combatant& target);
    void takeDamage(int amount, const std::string& attackerName);

private:
    std::string name_;
    int health_;
    int maxHealth_;
    std::shared_ptr<IWeapon> weapon_;
    std::shared_ptr<IDamageCalculator> calc_;
    std::shared_ptr<ILogger> logger_;
    std::shared_ptr<EventBus> eventBus_;
};

using Hero = Combatant;
using Enemy = Combatant;
```

`combatant.cpp`：

```cpp
#include "combatant.hpp"
#include <algorithm>

Combatant::Combatant(std::string name, int maxHealth,
                     std::shared_ptr<IWeapon> weapon,
                     std::shared_ptr<IDamageCalculator> calc,
                     std::shared_ptr<ILogger> logger,
                     std::shared_ptr<EventBus> eventBus)
    : name_(std::move(name)),
      health_(maxHealth),
      maxHealth_(maxHealth),
      weapon_(std::move(weapon)),
      calc_(std::move(calc)),
      logger_(std::move(logger)),
      eventBus_(std::move(eventBus)) {}

const std::string& Combatant::name() const { return name_; }
int Combatant::health() const { return health_; }
int Combatant::maxHealth() const { return maxHealth_; }
bool Combatant::isAlive() const { return health_ > 0; }

void Combatant::attack(Combatant& target) {
    if (!isAlive()) {
        logger_->log(name_ + " 已阵亡，无法攻击");
        return;
    }
    if (!target.isAlive()) {
        logger_->log(target.name() + " 已经死亡，无需再攻击");
        return;
    }

    int base = weapon_->damage();
    // 为示例简洁，以武器伤害值的奇偶性决定暴击：偶数伤害暴击
    bool critical = (base % 2 == 0);
    int finalDamage = calc_->calculate(base, critical);

    logger_->log(name_ + " 使用 " + weapon_->name() +
                 (critical ? " 暴击" : " 攻击") + " " +
                 target.name() + "，造成 " + std::to_string(finalDamage) + " 点伤害");

    target.takeDamage(finalDamage, name_);
}

void Combatant::takeDamage(int amount, const std::string& attackerName) {
    amount = std::max(0, amount);
    health_ = std::max(0, health_ - amount);

    DamageEvent event{attackerName, name_, amount, !isAlive()};
    eventBus_->publish(event);

    if (!isAlive()) {
        logger_->log(name_ + " 被击败了！");
    }
}
```

### 2.5 `composition_root.cpp` — 组合根

```cpp
#include "interfaces.hpp"
#include "implementations.hpp"
#include "combatant.hpp"
#include "event_bus.hpp"
#include <iostream>
#include <memory>

int main() {
    auto logger = std::make_shared<ConsoleLogger>();
    auto eventBus = std::make_shared<EventBus>();
    auto calculator = std::make_shared<NormalDamageCalculator>(2, 2);

    auto sword = std::make_shared<Sword>();
    auto bow = std::make_shared<Bow>();

    auto hero = std::make_shared<Combatant>("勇者", 100, sword, calculator, logger, eventBus);
    auto enemy = std::make_shared<Combatant>("史莱姆", 40, bow, calculator, logger, eventBus);

    eventBus->subscribe([](const DamageEvent& e) {
        std::cout << "[事件] " << e.attacker << " 对 " << e.defender
                  << " 造成 " << e.damage << " 点伤害"
                  << (e.fatal ? "（致命）" : "") << "\n";
    });

    std::cout << "=== 战斗开始 ===\n";
    while (hero->isAlive() && enemy->isAlive()) {
        hero->attack(*enemy);
        if (enemy->isAlive()) {
            enemy->attack(*hero);
        }
    }
    std::cout << "=== 战斗结束 ===\n";

    std::cout << (hero->isAlive() ? hero->name() : enemy->name()) << " 获胜！\n";
    return 0;
}
```

### 2.6 `combat_tests.cpp` — Mock 测试

```cpp
#include <gtest/gtest.h>
#include "interfaces.hpp"
#include "implementations.hpp"
#include "combatant.hpp"
#include "event_bus.hpp"
#include <memory>
#include <vector>
#include <string>

class MockWeapon : public IWeapon {
public:
    int damage() const override { return mockDamage; }
    std::string name() const override { return mockName; }
    int mockDamage = 10;
    std::string mockName = "MockWeapon";
};

class MockCalculator : public IDamageCalculator {
public:
    int calculate(int baseDamage, bool isCritical) const override {
        lastBase = baseDamage;
        lastCritical = isCritical;
        return mockResult;
    }
    int mockResult = 10;
    mutable int lastBase = 0;
    mutable bool lastCritical = false;
};

class MockLogger : public ILogger {
public:
    void log(const std::string& msg) override { messages.push_back(msg); }
    std::vector<std::string> messages;
};

TEST(DamageCalculatorTest, NormalAndCriticalDamage) {
    NormalDamageCalculator calc(2, 0);
    EXPECT_EQ(calc.calculate(10, false), 10);
    EXPECT_EQ(calc.calculate(10, true), 20);
}

TEST(DamageCalculatorTest, ArmorReducesDamage) {
    NormalDamageCalculator calc(2, 5);
    EXPECT_EQ(calc.calculate(10, false), 5);
    EXPECT_EQ(calc.calculate(10, true), 15);
}

TEST(CombatantTest, AttackTriggersDamageEvent) {
    auto weapon = std::make_shared<MockWeapon>();
    auto calc = std::make_shared<MockCalculator>();
    auto logger = std::make_shared<MockLogger>();
    auto bus = std::make_shared<EventBus>();

    std::vector<DamageEvent> events;
    bus->subscribe([&events](const DamageEvent& e) { events.push_back(e); });

    Combatant hero("Hero", 100, weapon, calc, logger, bus);
    Combatant enemy("Enemy", 100, weapon, calc, logger, bus);
    calc->mockResult = 25;

    hero.attack(enemy);

    ASSERT_EQ(events.size(), 1u);
    EXPECT_EQ(events[0].attacker, "Hero");
    EXPECT_EQ(events[0].defender, "Enemy");
    EXPECT_EQ(events[0].damage, 25);
    EXPECT_FALSE(events[0].fatal);
}

TEST(CombatantTest, HealthReducesAndKill) {
    auto weapon = std::make_shared<MockWeapon>();
    auto calc = std::make_shared<MockCalculator>();
    auto logger = std::make_shared<MockLogger>();
    auto bus = std::make_shared<EventBus>();

    Combatant hero("Hero", 100, weapon, calc, logger, bus);
    Combatant enemy("Enemy", 30, weapon, calc, logger, bus);
    calc->mockResult = 30;

    hero.attack(enemy);

    EXPECT_EQ(enemy.health(), 0);
    EXPECT_FALSE(enemy.isAlive());
}

TEST(DamageCalculatorTest, DamageCannotBeNegative) {
    NormalDamageCalculator calc(2, 20);
    EXPECT_EQ(calc.calculate(10, false), 0);
    EXPECT_EQ(calc.calculate(10, true), 0);
}

TEST(CombatantTest, CalculatorReceivesCorrectBaseDamageAndCrit) {
    auto weapon = std::make_shared<MockWeapon>();
    weapon->mockDamage = 12; // 偶数伤害 → 暴击
    auto calc = std::make_shared<MockCalculator>();
    auto logger = std::make_shared<MockLogger>();
    auto bus = std::make_shared<EventBus>();

    Combatant hero("Hero", 100, weapon, calc, logger, bus);
    Combatant enemy("Enemy", 100, weapon, calc, logger, bus);

    hero.attack(enemy);

    EXPECT_EQ(calc->lastBase, 12);
    EXPECT_TRUE(calc->lastCritical);
}

TEST(CombatantTest, EventMarksFatalOnKill) {
    auto weapon = std::make_shared<MockWeapon>();
    auto calc = std::make_shared<MockCalculator>();
    auto logger = std::make_shared<MockLogger>();
    auto bus = std::make_shared<EventBus>();

    std::vector<DamageEvent> events;
    bus->subscribe([&events](const DamageEvent& e) { events.push_back(e); });

    Combatant hero("Hero", 100, weapon, calc, logger, bus);
    Combatant enemy("Enemy", 10, weapon, calc, logger, bus);
    calc->mockResult = 10;

    hero.attack(enemy);

    ASSERT_EQ(events.size(), 1u);
    EXPECT_TRUE(events[0].fatal);
}

TEST(CombatantTest, DeadCombatantCannotAttack) {
    auto weapon = std::make_shared<MockWeapon>();
    auto calc = std::make_shared<MockCalculator>();
    auto logger = std::make_shared<MockLogger>();
    auto bus = std::make_shared<EventBus>();

    std::vector<DamageEvent> events;
    bus->subscribe([&events](const DamageEvent& e) { events.push_back(e); });

    Combatant hero("Hero", 100, weapon, calc, logger, bus);
    Combatant enemy("Enemy", 0, weapon, calc, logger, bus);
    calc->mockResult = 10;

    hero.attack(enemy);
    enemy.attack(hero);

    EXPECT_EQ(hero.health(), 100);
    EXPECT_TRUE(events.empty());
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
```

### 2.7 `CMakeLists.txt`

```cmake
cmake_minimum_required(VERSION 3.14)
project(CapstoneCombat VERSION 1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(combat_lib
    combatant.cpp
    implementations.cpp
)

add_executable(combat_game composition_root.cpp)
target_link_libraries(combat_game combat_lib)

include(FetchContent)
FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()
add_executable(combat_tests combat_tests.cpp)
target_link_libraries(combat_tests combat_lib gtest_main)
include(GoogleTest)
gtest_discover_tests(combat_tests)
```

### 2.8 编译与运行

**方式一：CMake（推荐，自动下载 GoogleTest）**

```bash
mkdir build && cd build
cmake ..
cmake --build .
./combat_game
ctest --output-on-failure
```

**方式二：直接用 g++ 编译可执行程序**

```bash
g++ -std=c++17 composition_root.cpp combatant.cpp implementations.cpp -o combat_game
./combat_game
```

**方式三：手动编译测试（需系统已安装 GoogleTest）**

```bash
g++ -std=c++17 combat_tests.cpp combatant.cpp implementations.cpp \
    -lgtest -lgtest_main -pthread -o combat_tests
./combat_tests
```

### 2.9 预期输出

**运行 `./combat_game`：**

```text
=== 战斗开始 ===
[战斗日志] 勇者 使用 铁剑 攻击 史莱姆，造成 13 点伤害
[事件] 勇者 对 史莱姆 造成 13 点伤害
[战斗日志] 史莱姆 使用 长弓 暴击 勇者，造成 22 点伤害
[事件] 史莱姆 对 勇者 造成 22 点伤害
[战斗日志] 勇者 使用 铁剑 攻击 史莱姆，造成 13 点伤害
[事件] 勇者 对 史莱姆 造成 13 点伤害
[战斗日志] 史莱姆 使用 长弓 暴击 勇者，造成 22 点伤害
[事件] 史莱姆 对 勇者 造成 22 点伤害
[战斗日志] 勇者 使用 铁剑 攻击 史莱姆，造成 13 点伤害
[事件] 勇者 对 史莱姆 造成 13 点伤害
[战斗日志] 史莱姆 使用 长弓 暴击 勇者，造成 22 点伤害
[事件] 史莱姆 对 勇者 造成 22 点伤害
[战斗日志] 勇者 使用 铁剑 攻击 史莱姆，造成 13 点伤害
[事件] 勇者 对 史莱姆 造成 13 点伤害（致命）
[战斗日志] 史莱姆 被击败了！
=== 战斗结束 ===
勇者 获胜！
```

> 计算说明：铁剑伤害 `15` 为奇数 → 不暴击，经 `armorReduction=2` 后造成 `13` 点；长弓伤害 `12` 为偶数 → 暴击，经 `2` 倍放大与护甲减免后造成 `22` 点。勇者 `100` 血可承受 `4` 次攻击剩余 `12` 血，史莱姆 `40` 血在第 `4` 次攻击中被击杀。

**运行 `ctest` 或 `./combat_tests`：**

```text
[==========] Running 8 tests from 3 test suites.
[----------] Global test environment set-up.
[----------] 3 tests from DamageCalculatorTest
[ RUN      ] DamageCalculatorTest.NormalAndCriticalDamage
[       OK ] DamageCalculatorTest.NormalAndCriticalDamage (0 ms)
[ RUN      ] DamageCalculatorTest.ArmorReducesDamage
[       OK ] DamageCalculatorTest.ArmorReducesDamage (0 ms)
[ RUN      ] DamageCalculatorTest.DamageCannotBeNegative
[       OK ] DamageCalculatorTest.DamageCannotBeNegative (0 ms)
[----------] 5 tests from CombatantTest
[ RUN      ] CombatantTest.AttackTriggersDamageEvent
[       OK ] CombatantTest.AttackTriggersDamageEvent (0 ms)
[ RUN      ] CombatantTest.HealthReducesAndKill
[       OK ] CombatantTest.HealthReducesAndKill (0 ms)
[ RUN      ] CombatantTest.CalculatorReceivesCorrectBaseDamageAndCrit
[       OK ] CombatantTest.CalculatorReceivesCorrectBaseDamageAndCrit (0 ms)
[ RUN      ] CombatantTest.EventMarksFatalOnKill
[       OK ] CombatantTest.EventMarksFatalOnKill (0 ms)
[ RUN      ] CombatantTest.DeadCombatantCannotAttack
[       OK ] CombatantTest.DeadCombatantCannotAttack (0 ms)
[==========] 8 tests from 3 test suites ran. (0 ms total)
[  PASSED  ] 8 tests.
```

---

## 3. 练习

### 练习 1: 基础 — 给 Combatant 加入护甲减伤

当前 `NormalDamageCalculator` 的 `armorReduction` 是全局固定的。请改造设计，让**每个 `Combatant` 拥有自己的护甲值**，并且伤害计算时读取**目标**的护甲。

思考：是否需要修改 `IDamageCalculator` 的签名？护甲应该通过构造器注入，还是作为 `takeDamage` 的参数？

### 练习 2: 进阶 — 多敌人与 AI 目标选择

把战斗从 `1v1` 扩展为 `1vN`：一个 `Hero` 面对多个 `Enemy`。为 `Hero` 增加一个目标选择策略接口 `ITargetSelector`，实现「优先攻击生命值最低敌人」的逻辑，并通过构造器注入。

### 练习 3: 挑战 — 用 boost::di 或 Builder 模式重构装配

选择下面任意一个方向：

- **boost::di**：把 `EventBus`、`NormalDamageCalculator`、`ConsoleLogger` 的创建从 `main()` 移到 `boost::di::make_injector`，体验 [[12-boost-di-cpp]] 的自动装配。
- **Builder 模式**：实现一个 `CombatantBuilder`，支持链式调用 `setWeapon(...).setHealth(...).setLogger(...).build()`，参考 [[10-builder-layered-wiring]]。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 推荐做法：把护甲变成 `Combatant` 的成员，并在 `IDamageCalculator::calculate` 中增加 `targetArmor` 参数。
>
> ```cpp
> class IDamageCalculator {
> public:
>     virtual int calculate(int baseDamage, bool isCritical, int targetArmor) const = 0;
> };
> ```
>
> `Combatant::attack` 调用时传入目标护甲：
>
> ```cpp
> int finalDamage = calc_->calculate(base, critical, target.armor());
> ```
>
> 这样做的好处：护甲与角色绑定，不同敌人可以有不同护甲；`MockCalculator` 也能在测试中验证传入的护甲值是否正确。

> [!tip]- 练习 2 参考答案
> 定义策略接口：
>
> ```cpp
> class ITargetSelector {
> public:
>     virtual ~ITargetSelector() = default;
>     virtual Combatant* selectTarget(std::vector<Combatant*>& enemies) = 0;
> };
> ```
>
> 实现「最低血量优先」：
>
> ```cpp
> class LowestHealthTargetSelector : public ITargetSelector {
> public:
>     Combatant* selectTarget(std::vector<Combatant*>& enemies) override {
>         Combatant* best = nullptr;
>         for (auto* e : enemies) {
>             if (e->isAlive() && (!best || e->health() < best->health()))
>                 best = e;
>         }
>         return best;
>     }
> };
> ```
>
> 将 `ITargetSelector` 注入 `Combatant` 或通过独立的 `BattleManager` 控制回合。推荐后者：让 `Combatant` 只负责「攻击一个目标」，而「选谁打」交给 `BattleManager` 或策略对象，避免 `Combatant` 过度膨胀。

> [!tip]- 练习 3 参考答案
> **boost::di 方向**（核心片段）：
>
> ```cpp
> auto injector = di::make_injector(
>     di::bind<ILogger>().to<ConsoleLogger>().in(di::singleton),
>     di::bind<EventBus>().to<EventBus>().in(di::singleton),
>     di::bind<IDamageCalculator>().to<NormalDamageCalculator>().in(di::singleton),
>     di::bind<IWeapon>().to<Sword>()
> );
> auto hero = injector.create<std::shared_ptr<Combatant>>();
> ```
>
> 注意：`Combatant` 当前依赖 `IWeapon` 作为个体武器，如果 `Hero` 和 `Enemy` 需要不同武器，需要为它们分别创建 injector 或用命名绑定（`di::bind<IWeapon>().named<HeroTag>()`）。
>
> **Builder 方向**（核心片段）：
>
> ```cpp
> auto hero = CombatantBuilder("勇者", 100)
>                 .setWeapon(std::make_shared<Sword>())
>                 .setCalculator(calculator)
>                 .setLogger(logger)
>                 .setEventBus(eventBus)
>                 .build();
> ```
>
> Builder 内部通过 `std::make_shared<Combatant>(...)` 创建对象，把多参数构造器的装配细节封装起来，组合根会更易读。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [GoogleTest 官方文档](https://google.github.io/googletest/) — 断言、参数化测试、测试夹具的完整参考。
- [boost::di 文档](https://boost-ext.github.io/di/) — 现代 C++ 依赖注入容器，支持构造器注入与生命周期管理。
- [[12-boost-di-cpp]] — 本计划第 12 节，`boost::di` 在游戏战斗系统中的具体用法。
- [[10-builder-layered-wiring]] — 本计划第 10 节，手动 DI Builder 模式。
- 《Game Programming Patterns》中 *Service Locator* 与 *Event Queue* 章节 — 理解游戏中事件总线与定位器模式的取舍。

---

## 5. 复盘：16 节知识地图

| 章节 | 在项目中的体现 |
|------|----------------|
| [[01-what-is-di-coupling\|01 紧耦合与 DI]] | 从 `Hero` 直接 `new Sword()` 改为通过接口注入武器 |
| [[02-ioc-dip-di-principles\|02 IoC/DIP/DI]] | `Combatant` 高层逻辑依赖 `IWeapon` / `IDamageCalculator` 等抽象，而非具体实现 |
| [[03-three-forms-of-di\|03 三种注入形式]] | 本项目统一使用**构造器注入** |
| [[04-cpp-interfaces-abc\|04 C++ 抽象基类]] | `IWeapon`、`ILogger`、`IDamageCalculator` 均用纯虚函数 + 虚析构函数定义 |
| [[05-constructor-injection-ownership\|05 构造器注入与所有权]] | `Combatant` 通过构造器接收 `std::shared_ptr`，明确依赖所有权 |
| [[06-smart-pointers-lifetime\|06 智能指针与生命周期]] | `logger`、`eventBus`、`calculator` 作为共享服务；`sword`、`bow` 作为个体武器 |
| [[07-composition-root-wiring\|07 组合根与手动装配]] | `composition_root.cpp` 的 `main()` 一次性创建并连接所有对象 |
| [[08-templates-static-polymorphism\|08 模板与静态多态]] | 性能敏感的热循环中，可把 `Combatant<IWeaponImpl>` 替换为模板版本 |
| [[09-type-erasure-std-function\|09 类型擦除与 std::function]] | `EventBus` 使用 `std::function<void(const DamageEvent&)>` 解耦发布者与订阅者 |
| [[10-builder-layered-wiring\|10 Builder 与分层装配]] | 练习 `#3` 中可用 `CombatantBuilder` 隐藏复杂构造 |
| [[11-di-containers-csharp\|11 C# DI 容器]] | 可与 `Microsoft.Extensions.DependencyInjection` 的 `AddSingleton` / `AddTransient` 对照 |
| [[12-boost-di-cpp\|12 boost::di]] | 练习 `#3` 中可用 `make_injector` 替换手动组合根 |
| [[13-service-lifetimes-scopes\|13 生命周期与作用域]] | `logger` / `eventBus` / `calculator` 类似 Singleton，`weapon` 类似 Transient |
| [[14-testing-with-di-mocks\|14 测试与 Mock]] | `combat_tests.cpp` 注入 `MockWeapon`、`MockCalculator`、`MockLogger` |
| [[15-antipatterns-when-not\|15 反模式]] | 本项目没有 Service Locator，没有全局单例，没有环境上下文 |
| [[16-capstone-game-combat\|16 综合项目]] | 本章本身：把前 15 节串成可运行、可测试的战斗系统 |

---

## 常见陷阱

- **陷阱 1：在核心逻辑里混用 `std::cout` 或引擎 API。** 正确做法：核心逻辑只依赖 `ILogger`、`EventBus` 等抽象；`ConsoleLogger` 只在组合根或测试桩里出现。
- **陷阱 2：把 `EventBus` 做成全局单例。** 正确做法：通过 `std::shared_ptr<EventBus>` 注入，测试时创建独立总线，避免测试间互相污染。
- **陷阱 3：在 `Combatant` 里直接决定暴击随机数，导致测试不稳定。** 正确做法：把随机/判定逻辑外移到 `IDamageCalculator` 或独立的 `ICritStrategy`，测试中注入确定性策略。
- **陷阱 4：忽视接口生命周期。** 正确做法：武器、防具等个体装备用 Transient 或 unique 所有权；日志、配置、事件总线用共享/单例所有权。
- **陷阱 5：把组合根逻辑散落到多个 `main()` 或模块初始化里。** 正确做法：整个程序只有一个组合根（或按子系统分层组合根），所有对象装配位置一目了然。
