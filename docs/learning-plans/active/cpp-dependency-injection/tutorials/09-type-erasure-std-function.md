---
title: 类型擦除与 std::function 注入
updated: 2026-06-23
tags: [dependency-injection, cpp, type-erasure, std-function, events, callbacks]
---

# 类型擦除与 `std::function` 注入

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 60min
> 前置知识: [[04-cpp-interfaces-abc]]

---

## 1. 概念讲解

### 1.1 先用一个游戏场景理解“事件与回调”

想象你在做一款 ARPG：玩家控制的 `Hero` 挥剑命中敌人时，系统需要同时做很多事情——

- 在屏幕中央飘一个伤害数字。
- 记录本次伤害，用来统计 DPS。
- 检查是否触发了暴击成就。
- 通知音效系统播放命中音效。
- 如果敌人在联机对战中，还要把伤害事件同步给服务器。

这些行为有一个共同点：**它们都不是 `Hero` 这个类的核心职责**。`Hero` 只应该关心“我造成了多少伤害”，至于伤害数字怎么飘、成就怎么判、网络怎么同步，应该交给外部系统决定。

在 C++ 里，这种“外部系统决定行为”的机制通常叫**回调（callback）**或**事件（event）**。本章要讲的 `std::function` 注入，就是一种把回调作为依赖注入到 `Hero` 中的方式。

---

### 1.2 为什么需要类型擦除：按值拥有一个“多态对象”

在 [[04-cpp-interfaces-abc]] 和 [[05-constructor-injection-ownership]] 里我们学过：C++ 的抽象基类不能按值传递或持有，因为切片（slicing）会丢失多态行为。所以注入多态依赖时，通常用引用、指针或智能指针：

```cpp
Hero(IWeapon& weapon, ILogger& logger);  // 引用注入
```

但回调的情况不太一样。一个回调可能是：

- 一个普通函数指针。
- 一个带捕获列表的 lambda。
- 一个重载了 `operator()` 的仿函数（functor）。
- 一个成员函数绑定（`std::bind`）。

它们的类型各不相同。如果 `Hero` 的构造函数写成：

```cpp
Hero(IWeapon& weapon, ILogger& logger, ??? onDamage);
```

`???` 该填什么？填函数指针就不能接收 lambda；填模板参数（见 [[08-templates-static-polymorphism]]）又会让 `Hero` 变成类模板，编译期绑定，无法运行时换行为。

**类型擦除（type erasure）** 就是解决这个问题的：它把“各种不同的具体类型”擦成同一个统一的接口类型，让你可以按值持有、传递、存储一个多态对象。`std::function` 是 C++ 标准库里最常用的类型擦除工具之一。

---

### 1.3 `std::function`：可注入的可调用对象容器

`std::function<Signature>` 是一个类模板，它可以擦除任何**可调用对象**的类型，只要签名匹配。例如：

```cpp
std::function<void(int)> onDamage;
```

这个 `onDamage` 可以持有：

| 可调用对象 | 示例 |
|-----------|------|
| 普通函数 | `void printDamage(int dmg)` |
| Lambda | `[](int dmg){ ... }` |
| 带捕获的 Lambda | `[&total](int dmg){ total += dmg; }` |
| 仿函数 | `struct DamagePrinter { void operator()(int) const; };` |
| `std::bind` 绑定 | `std::bind(&Achievements::onDamage, &achievements, _1)` |

对 `Hero` 来说，构造函数写成：

```cpp
Hero(IWeapon& weapon, ILogger& logger, std::function<void(int)> onDamage);
```

外部在组合根里注入什么样的回调都可以，运行时还能换行为——这是抽象基类注入做不到的灵活性。

---

### 1.4 值语义多态简介

`std::function` 带来的是一种**值语义多态（value semantics polymorphism）**：

- 你可以把它当作普通成员变量按值持有。
- 它可以拷贝、移动、默认构造、交换。
你不用操心 `new`/`delete` 或生命周期（内部可能用 small-buffer 优化避免堆分配，也可能堆分配，见后文性能讨论）。

除了 `std::function`，C++ 里还有其他类型擦除的例子：

- `std::any`：可以持有任意类型，但只能“先存再取”，没有统一接口。
- 自定义 small-buffer 包装：例如 C++ Software Design 里常见的 `any_storage` 思路，用一小块栈内存避免堆分配，适合性能敏感的 ECS 组件。

本章不深究自定义实现，但你应该记住：**类型擦除是一种设计技术，不是 `std::function` 的专利**。当你发现“想按值持有接口、又想运行时换实现”时，就是类型擦除出场的时候。

---

### 1.5 `std::function` vs 函数指针 vs 模板回调

游戏热循环里每一微秒都宝贵，所以必须理解三种回调方案的区别：

| 方案 | 灵活性 | 运行时开销 | 绑定时机 | 适用场景 |
|------|--------|-----------|----------|----------|
| `std::function` | 极高，可接 lambda/仿函数/函数指针 | 间接调用 + 可能堆分配 | 运行期 | 事件总线、UI 回调、配置化行为 |
| 函数指针 | 低，只能接无状态函数 | 接近零 | 运行期/编译期 | C 风格回调、插件接口、热循环中的简单分发 |
| 模板回调 | 高，可接任意可调用对象 | 零开销（内联优化） | 编译期 | 游戏热循环、ECS 系统、已知回调类型 |

一句话总结：

- 不知道回调具体是什么类型，但需要运行时灵活 → `std::function`。
- 知道回调类型且追求极致性能 → 模板回调（见 [[08-templates-static-polymorphism]]）。
- 只需要无状态全局函数，且想和 C 库/插件对接 → 函数指针。

---

### 1.6 EventBus 模式：用 `std::function` 做事件总线

回调注入还有一种更“广播”的用法：**事件总线（EventBus）**。

思路是：有一个全局或场景级的事件总线，任何系统都可以向它**订阅**某种事件，也可以向它**发布**事件。`Hero` 不需要知道谁在处理伤害事件，只需要把事件发到总线上。

```cpp
class EventBus {
public:
    using Handler = std::function<void(const DamageEvent&)>;
    void subscribe(Handler handler);
    void emit(const DamageEvent& event);
private:
    std::vector<Handler> handlers_;
};
```

这种模式在 Unity 的 `EventManager`、Unreal 的 `Delegates`、游戏 ECS 的消息系统里都很常见。它的好处是**发布者与订阅者完全解耦**：新增一个成就系统，不需要改 `Hero` 的构造函数，只需要在组合根里多 subscribe 一个 handler。

---

## 2. 代码示例

### 示例 1：`Hero` 注入 `std::function` 伤害回调

下面的代码中，`Hero` 通过构造函数注入一个 `std::function<void(int)>`。`main` 里给两个不同的 `Hero` 注入不同的 lambda：一个打印伤害，一个累加总伤害。

```cpp
#include <functional>
#include <iostream>
#include <memory>
#include <string>

// 武器接口
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

// 日志接口
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

// Hero：注入武器、日志、以及一个伤害回调
class Hero {
public:
    Hero(IWeapon& weapon,
         ILogger& logger,
         std::function<void(int)> onDamage)
        : weapon_(weapon)
        , logger_(logger)
        , onDamage_(std::move(onDamage)) {}

    void attack() {
        int dmg = weapon_.damage();
        logger_.log("Hero 使用 " + weapon_.name() +
                    " 造成 " + std::to_string(dmg) + " 点伤害");
        if (onDamage_) {
            onDamage_(dmg);
        }
    }

private:
    IWeapon& weapon_;
    ILogger& logger_;
    std::function<void(int)> onDamage_;
};

int main() {
    Sword sword;
    Bow bow;
    ConsoleLogger logger;

    // 注入：打印伤害
    Hero hero1(sword, logger, [](int dmg) {
        std::cout << "[回调] 本次伤害: " << dmg << "\n";
    });

    // 注入：累加总伤害
    int totalDamage = 0;
    Hero hero2(bow, logger, [&totalDamage](int dmg) {
        totalDamage += dmg;
        std::cout << "[回调] 累计伤害: " << totalDamage << "\n";
    });

    hero1.attack();
    hero2.attack();
    hero2.attack();

    return 0;
}
```

**运行方式：**

```bash
g++ -std=c++17 hero_callback.cpp -o hero_callback
./hero_callback
```

**预期输出：**

```text
[log] Hero 使用 铁剑 造成 15 点伤害
[回调] 本次伤害: 15
[log] Hero 使用 长弓 造成 12 点伤害
[回调] 累计伤害: 12
[log] Hero 使用 长弓 造成 12 点伤害
[回调] 累计伤害: 24
```

---

### 示例 2：注入 `EventBus`，实现订阅/发布解耦

下面给出一个最简 `EventBus`，以及两个订阅者：一个记录伤害日志，一个做累计统计。`Hero` 只负责 `emit` 事件，不关心谁在处理。

```cpp
#include <functional>
#include <iostream>
#include <string>
#include <vector>

// 事件定义
struct DamageEvent {
    int amount;
    std::string weaponName;
    std::string attacker;
};

// 最简事件总线
class EventBus {
public:
    using Handler = std::function<void(const DamageEvent&)>;

    void subscribe(Handler handler) {
        handlers_.push_back(std::move(handler));
    }

    void emit(const DamageEvent& event) {
        for (const auto& handler : handlers_) {
            handler(event);
        }
    }

private:
    std::vector<Handler> handlers_;
};

// 武器接口
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

// 日志接口
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

// Hero：通过 EventBus 发布事件
class Hero {
public:
    Hero(std::string name,
         IWeapon& weapon,
         ILogger& logger,
         EventBus& bus)
        : name_(std::move(name))
        , weapon_(weapon)
        , logger_(logger)
        , bus_(bus) {}

    void attack() {
        int dmg = weapon_.damage();
        logger_.log(name_ + " 使用 " + weapon_.name() +
                    " 造成 " + std::to_string(dmg) + " 点伤害");
        bus_.emit(DamageEvent{dmg, weapon_.name(), name_});
    }

private:
    std::string name_;
    IWeapon& weapon_;
    ILogger& logger_;
    EventBus& bus_;
};

// 订阅者：伤害记录器
class DamageLogger {
public:
    void onDamage(const DamageEvent& event) {
        std::cout << "[DamageLogger] " << event.attacker
                  << " 用 " << event.weaponName
                  << " 造成 " << event.amount << " 点伤害\n";
    }
};

// 订阅者：DPS 统计器
class DamageAccumulator {
public:
    void onDamage(const DamageEvent& event) {
        total_ += event.amount;
        std::cout << "[DamageAccumulator] 当前总伤害: " << total_ << "\n";
    }
    int total() const { return total_; }
private:
    int total_ = 0;
};

int main() {
    Sword sword;
    ConsoleLogger logger;
    EventBus bus;

    DamageLogger damageLogger;
    DamageAccumulator accumulator;

    // 在组合根里装配订阅者
    bus.subscribe([&damageLogger](const DamageEvent& e) {
        damageLogger.onDamage(e);
    });
    bus.subscribe([&accumulator](const DamageEvent& e) {
        accumulator.onDamage(e);
    });

    Hero hero("亚瑟", sword, logger, bus);
    hero.attack();
    hero.attack();

    std::cout << "最终总伤害: " << accumulator.total() << "\n";
    return 0;
}
```

**运行方式：**

```bash
g++ -std=c++17 hero_eventbus.cpp -o hero_eventbus
./hero_eventbus
```

**预期输出：**

```text
[log] 亚瑟 使用 铁剑 造成 15 点伤害
[DamageLogger] 亚瑟 用 铁剑 造成 15 点伤害
[DamageAccumulator] 当前总伤害: 15
[log] 亚瑟 使用 铁剑 造成 15 点伤害
[DamageLogger] 亚瑟 用 铁剑 造成 15 点伤害
[DamageAccumulator] 当前总伤害: 30
最终总伤害: 30
```

---

## 3. 练习

### 练习 1: 基础

在示例 1 的基础上，把 `std::function<void(int)>` 改成 `std::function<void(int, const std::string&)>`，让回调同时收到伤害值和武器名。修改 `Hero::attack()` 和 `main` 中的两个 lambda，输出格式为：

```text
[回调] 铁剑 造成 15 点伤害
```

### 练习 2: 进阶

给 `EventBus` 增加一个**取消订阅**的能力。思路：让 `subscribe` 返回一个句柄（例如 `std::size_t` 索引），并提供 `unsubscribe(handle)` 方法。在 `main` 中先订阅 `DamageLogger`，攻击一次后取消订阅，再攻击一次，观察输出变化。

### 练习 3: 挑战（可选）

写一个微型性能对比：在循环里分别调用：

- 通过 `std::function<void()>` 调用的空 lambda。
- 直接调用的空 lambda。
- 通过函数指针调用的空函数。

比较三者在 `1'000'000` 次调用下的耗时（可以用 `std::chrono` 计时）。讨论在什么情况下 `std::function` 的额外开销会成为问题。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> class Hero {
> public:
>     Hero(IWeapon& weapon,
>          ILogger& logger,
>          std::function<void(int, const std::string&)> onDamage)
>         : weapon_(weapon)
>         , logger_(logger)
>         , onDamage_(std::move(onDamage)) {}
>
>     void attack() {
>         int dmg = weapon_.damage();
>         std::string weaponName = weapon_.name();
>         logger_.log("Hero 使用 " + weaponName +
>                     " 造成 " + std::to_string(dmg) + " 点伤害");
>         if (onDamage_) {
>             onDamage_(dmg, weaponName);
>         }
>     }
> private:
>     IWeapon& weapon_;
>     ILogger& logger_;
>     std::function<void(int, const std::string&)> onDamage_;
> };
>
> // main 中的注入示例
> Hero hero(sword, logger, [](int dmg, const std::string& name) {
>     std::cout << "[回调] " << name << " 造成 " << dmg << " 点伤害\n";
> });
> ```

> [!tip]- 练习 2 参考答案
> 一种简单实现是给每个 handler 分配一个 id，取消订阅时从列表中移除该 handler：
>
> ```cpp
> #include <algorithm>
> class EventBus {
> public:
>     using Handler = std::function<void(const DamageEvent&)>;
>     using Handle = std::size_t;
>
>     Handle subscribe(Handler handler) {
>         Handle id = nextId_++;
>         handlers_.push_back({id, std::move(handler)});
>         return id;
>     }
>
>     void unsubscribe(Handle id) {
>         auto it = std::find_if(handlers_.begin(), handlers_.end(),
>             [id](const auto& pair) { return pair.first == id; });
>         if (it != handlers_.end()) {
>             handlers_.erase(it);
>         }
>     }
>
>     void emit(const DamageEvent& event) {
>         for (const auto& [id, handler] : handlers_) {
>             handler(event);
>         }
>     }
>
> private:
>     std::size_t nextId_ = 0;
>     std::vector<std::pair<Handle, Handler>> handlers_;
> };
> ```
>
> 在 `main` 里：
>
> ```cpp
> auto handle = bus.subscribe([&damageLogger](const DamageEvent& e) {
>     damageLogger.onDamage(e);
> });
> hero.attack();          // DamageLogger 会输出
> bus.unsubscribe(handle);
> hero.attack();          // DamageLogger 不再输出
> ```

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <chrono>
> #include <functional>
> #include <iostream>
>
> void plainFunction() {}
>
> int main() {
>     const int N = 1'000'000;
>
>     auto t1 = std::chrono::high_resolution_clock::now();
>     for (int i = 0; i < N; ++i) {
>         [](){}();  // 直接调用 lambda
>     }
>     auto t2 = std::chrono::high_resolution_clock::now();
>
>     std::function<void()> f = [](){};
>     auto t3 = std::chrono::high_resolution_clock::now();
>     for (int i = 0; i < N; ++i) {
>         f();  // 通过 std::function 调用
>     }
>     auto t4 = std::chrono::high_resolution_clock::now();
>
>     void(*fp)() = plainFunction;
>     auto t5 = std::chrono::high_resolution_clock::now();
>     for (int i = 0; i < N; ++i) {
>         fp();  // 函数指针
>     }
>     auto t6 = std::chrono::high_resolution_clock::now();
>
>     std::cout << "直接 lambda: "
>               << std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count()
>               << " us\n";
>     std::cout << "std::function: "
>               << std::chrono::duration_cast<std::chrono::microseconds>(t4 - t3).count()
>               << " us\n";
>     std::cout << "函数指针: "
>               << std::chrono::duration_cast<std::chrono::microseconds>(t6 - t5).count()
>               << " us\n";
> }
> ```
>
> 通常你会看到 `std::function` 比直接调用慢一个数量级左右，主要原因是间接调用和类型擦除带来的额外跳转。在每秒调用几十万次的物理、动画、ECS 热循环里，这种开销可能无法接受；但在事件总线、UI 回调、网络回调等低频路径上，它带来的灵活性完全值得。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [cppreference: std::function](https://en.cppreference.com/w/cpp/utility/functional/function)
- [cppreference: std::any](https://en.cppreference.com/w/cpp/utility/any) —— 另一种标准库类型擦除
- [Klaus Iglberger: C++ Software Design](https://www.oreilly.com/library/view/c-software-design/9781098113155/) —— 第 19 章详细讲解类型擦除设计
- [Arthur O'Dwyer: "Back to Basics: Type Erasure" (CppCon 2019)](https://www.youtube.com/watch?v=tbUCHifyK24)
- [Game Programming Patterns: Event Queue](https://gameprogrammingpatterns.com/event-queue.html)
- Unity 对照：[`UnityEvent`](https://docs.unity3d.com/ScriptReference/Events.UnityEvent.html) 与 C# `event Action<T>` 也是事件/回调注入的常见形式。

---

## 5. 常见陷阱

- **在热循环里无差别使用 `std::function`**：`std::function` 有间接调用开销，且捕获较大的 lambda 时可能触发堆分配 [INFERENCE]。在 ECS 更新、物理回调、渲染提交等每帧百万次的路径上，优先考虑模板回调或函数指针；事件总线、UI、网络等低频路径再用 `std::function`。

- **默认构造的 `std::function` 直接调用会抛 `std::bad_function_call`**：调用前一定要检查 `if (callback)` 或确保构造时已注入有效回调。在 `Hero::attack()` 里我们用 `if (onDamage_)` 做了保护。

- **用 `std::function` 接收有状态的 lambda，却忘了捕获对象的生命周期**：如果 lambda 捕获了局部对象的引用，而 `std::function` 被持有到局部对象销毁之后，调用时会产生悬空引用。务必保证捕获对象的生命周期长于 `std::function`。

- **把所有交互都改成 EventBus，导致调试困难**：EventBus 解耦很强，但也会让调用链变得不直观。建议保留关键路径的直接注入（如 `ILogger`），只在真正的“一对多广播”场景使用 EventBus。

- **忽略 `std::function` 的拷贝语义**：如果回调持有重资源（例如捕获了一个大缓冲区），拷贝 `std::function` 会变成昂贵的深拷贝。需要时用 `std::move` 转移，或改用 `std::unique_ptr` 持有资源再由 lambda 按引用捕获。

---

学完本节，你应该掌握了用 `std::function` 注入回调和事件处理器的方法，也理解了它的灵活性代价。下一节 [[10-builder-layered-wiring]] 会进入更现代的装配模式，学习如何用 Builder 把武器、防具、技能、日志等复杂依赖一次性组装成完整的 `Hero`。
