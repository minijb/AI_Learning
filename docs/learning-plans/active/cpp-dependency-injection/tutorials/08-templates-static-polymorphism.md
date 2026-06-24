---
title: 模板与静态多态：编译期 DI
updated: 2026-06-23
tags: [dependency-injection, cpp, templates, static-polymorphism]
---

# 模板与静态多态：编译期 DI

> 所属计划: [[plan|C++ 依赖注入完整学习计划]]
> 预计耗时: 75min
> 前置知识: [[04-cpp-interfaces-abc]]

---

## 1. 概念讲解

### 1.1 武器是在背包里换，还是在工厂焊死？

想象你正在做一款 ARPG：

- **动态多态**像是给角色背了一个「武器插槽」。玩家可以在战斗中打开背包，把铁剑换成长弓，角色下一帧就能使用新的武器逻辑。武器类型在**运行时**决定。
- **静态多态**则像是角色出厂时就把某把武器「焊」在了手上。铁剑版 Hero 和长弓版 Hero 在装配流水线上就已经是两种不同的类型，运行时无法改变，但挥剑动作没有任何中间环节。

C++ 里，前者靠**抽象基类 + 虚函数**（运行时多态），后者靠**模板**（编译期多态）。两种方案都能把 `Hero` 和具体的 `Sword`/`Bow` 解耦，但它们的注入时机、运行时开销和灵活性截然不同。

### 1.2 动态多态：vtable 与运行期替换

这是 [[04-cpp-interfaces-abc]] 里讲过的方式：

```cpp
class IWeapon { /* 纯虚函数 */ };
class Hero {
public:
    Hero(IWeapon& weapon, ILogger& logger);
    void attack();
private:
    IWeapon& weapon_;
};
```

调用 `weapon_.damage()` 时，编译器通常要通过**虚表（vtable）**做间接跳转。它的好处是**运行时实现可替换**：

- 脚本层、配置表或装备系统可以在运行时决定注入 `Sword` 还是 `Bow`。
- 可以构建异构容器，例如 `std::vector<std::unique_ptr<IWeapon>>`。

代价是每次调用都有间接跳转，且编译器很难把跨动态类型的调用内联到调用点 [INFERENCE]。

### 1.3 静态多态：模板注入与零开销抽象

把依赖改成模板参数，依赖在编译期确定：

```cpp
template<typename WeaponT>
class Hero {
public:
    Hero(WeaponT& weapon, ILogger& logger);
    void attack();
private:
    WeaponT& weapon_;
};
```

`Hero<Sword>` 和 `Hero<Bow>` 是两种完全不同的类型。编译器看到 `weapon_.damage()` 时，知道具体类型是 `Sword` 还是 `Bow`，于是可以：

- 直接调用具体实现，跳过 vtable。
- 把整个 `attack()` 调用链内联展开 [INFERENCE]。

在游戏的热循环（hot loop）里——比如每帧更新成千上万个角色的 `attack`、`update`、物理积分——这种消除间接跳转的机会对指令缓存和分支预测都很有价值 [INFERENCE]。

### 1.4 CRTP：把「接口」也放到编译期

CRTP（Curiously Recurring Template Pattern，奇异递归模板模式）是静态多态的一种惯用法。它用模板基类提供统一接口，用 `static_cast` 把调用转发到派生类：

```cpp
template<typename Derived>
class IWeaponBase {
public:
    int damage() const {
        return static_cast<const Derived*>(this)->damage();
    }
};

class Sword : public IWeaponBase<Sword> {
public:
    int damage() const { return 15; }
};
```

`Sword` 继承自 `IWeaponBase<Sword>`，基类通过模板参数知道真实类型，因此调用无需虚函数。CRTP 适合想要「像接口一样的静态约束」、但又不想承担 vtable 开销的场景。

### 1.5 决策指南表：静态多态 vs 动态多态

下面这张表不是「永远正确」的教条，而是你在游戏项目中做取舍时的起点。

| 维度 | 动态多态（虚函数） | 静态多态（模板/CRTP） | 游戏中通常选它的场景 |
|------|-------------------|----------------------|----------------------|
| 运行时替换实现 | 可以：运行时 `new Bow()` 即可切换 | 不可以：类型在编译期固定 | 装备系统、脚本配置、MOD 热插拔 → 动态 |
| 调用开销 | 需 vtable 间接跳转，难内联 [INFERENCE] | 直接调用，可内联 [INFERENCE] | 热循环里成千上万次 `attack`/`update` → 静态 |
| 异构容器 | 容易：`std::vector<std::unique_ptr<IWeapon>>` | 困难：同容器只能放同一 `Hero<T>` | 背包、场景对象列表 → 动态 |
| 编译时间/二进制体积 | 较小 | 较大（每种类型实例化一份代码） | 武器类型极少且追求性能 → 静态 |
| 调试与错误信息 | 相对友好 | 模板实例化栈可能很长 | 原型阶段快速迭代 → 动态 |

> [!warning] 不要把静态多态当成默认方案
> 只有当你确实处在性能敏感路径，并且武器/技能类型可以在编译期确定时，才值得付出代码膨胀和编译时间的代价。UI、配置读取、网络回调等「冷路径」用虚函数通常更清晰。

### 1.6 代价：没有免费的午餐

静态多态不是银弹，它的代价在大型项目中非常明显：

| 代价 | 说明 |
|------|------|
| 代码膨胀 | `Hero<Sword>`、`Hero<Bow>`、未来的 `Hero<Spear>` 各生成一份代码，二进制变大 |
| 编译时间增加 | 模板实例化、深度内联会显著拖慢编译 |
| 失去运行时灵活性 | 运行中不能把 `Hero<Sword>` 改成 `Hero<Bow>`，类型已经焊死 |
| 调试体验下降 | 错误信息往往是一长串实例化栈，定位更费劲 |

### 1.7 链接期依赖注入（link-time DI）

除了模板，C++ 还可以用**链接期选择实现**：把接口声明放在头文件，把不同实现放在不同 `.cpp` 文件中，通过构建配置决定链接哪一个目标文件。例如 `release` 链接高性能日志实现，`test` 链接静默桩实现。这种方式同样是零运行时开销，只是依赖不是在编译期通过模板参数、而是通过链接器选择实现。

---

## 2. 代码示例

下面的程序把**模板版 StaticHero** 与**接口版 DynamicHero** 放在一起对比。二者都依赖 `IWeapon`/`ILogger` 的语义，但前者的 `WeaponT` 在编译期确定，后者在运行时通过引用替换。

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>

// ---------- 动态多态接口 ----------
class IWeapon {
public:
    virtual ~IWeapon() = default;
    virtual int         damage() const = 0;
    virtual std::string name() const   = 0;
};

class Sword : public IWeapon {
public:
    int         damage() const override { return 15; }
    std::string name() const override   { return "铁剑"; }
};

class Bow : public IWeapon {
public:
    int         damage() const override { return 12; }
    std::string name() const override   { return "长弓"; }
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

// ---------- 静态多态：模板注入 ----------
template<typename WeaponT>
class StaticHero {
public:
    StaticHero(WeaponT& weapon, ILogger& logger)
        : weapon_(weapon), logger_(logger) {}

    void attack() const {
        logger_.log("StaticHero 用 " + weapon_.name() + " 造成 " +
                    std::to_string(weapon_.damage()) + " 点伤害");
    }

private:
    WeaponT& weapon_;
    ILogger& logger_;
};

// ---------- 动态多态：虚接口注入 ----------
class DynamicHero {
public:
    DynamicHero(IWeapon& weapon, ILogger& logger)
        : weapon_(weapon), logger_(logger) {}

    void attack() const {
        logger_.log("DynamicHero 用 " + weapon_.name() + " 造成 " +
                    std::to_string(weapon_.damage()) + " 点伤害");
    }

private:
    IWeapon& weapon_;
    ILogger& logger_;
};

// 一个热循环风格的批量攻击函数
template<typename HeroT>
void runHotLoop(std::vector<HeroT>& heroes) {
    for (auto& hero : heroes) {
        hero.attack();
    }
}

int main() {
    ConsoleLogger logger;
    Sword sword;
    Bow   bow;

    StaticHero<Sword> staticSwordHero(sword, logger);
    StaticHero<Bow>   staticBowHero(bow, logger);

    DynamicHero dynamicSwordHero(sword, logger);
    DynamicHero dynamicBowHero(bow, logger);

    std::cout << "== 静态多态热循环 ==\n";
    std::vector<StaticHero<Sword>> swordHeroes = { staticSwordHero };
    std::vector<StaticHero<Bow>>   bowHeroes   = { staticBowHero };
    runHotLoop(swordHeroes);
    runHotLoop(bowHeroes);

    std::cout << "== 动态多态运行时切换 ==\n";
    dynamicSwordHero.attack();
    dynamicBowHero.attack();

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 main.cpp -o demo
./demo
```

**预期输出:**

```text
== 静态多态热循环 ==
[log] StaticHero 用 铁剑 造成 15 点伤害
[log] StaticHero 用 长弓 造成 12 点伤害
== 动态多态运行时切换 ==
[log] DynamicHero 用 铁剑 造成 15 点伤害
[log] DynamicHero 用 长弓 造成 12 点伤害
```

> [!note] 关于性能的说明
> 模板版的 `weapon_.damage()` 在编译期就能确定调用 `Sword::damage()` 或 `Bow::damage()`，编译器有很高的概率把整段调用链内联展开 [INFERENCE]。虚函数版的 `IWeapon::damage()` 通常需要一次间接跳转，编译器难以在调用点做内联 [INFERENCE]。本示例不输出也不声称任何具体计时数字，因为真实收益取决于编译器、优化级别、调用频率和硬件。

---

## 3. 练习

### 练习 1: 基础

编译并运行上面的示例。把 `StaticHero<Sword>` 改成 `StaticHero<Bow>`，观察输出变化，并解释为什么不需要修改 `StaticHero` 的源码就能切换武器类型。

### 练习 2: 进阶

用 CRTP 改写 `Sword` 和 `Bow`：

1. 写一个 `template<typename Derived> class WeaponBase`，其中 `damage()` 通过 `static_cast<const Derived*>(this)->damage()` 转发。
2. 让 `Sword` 和 `Bow` 继承 `WeaponBase<Sword>` 和 `WeaponBase<Bow>`。
3. 写一个 `template<typename WeaponT> class CrtpHero`，通过 `WeaponBase<WeaponT>&` 使用武器。
4. 在 `main()` 中创建 `CrtpHero<Sword>` 和 `CrtpHero<Bow>` 各一个并调用 `attack()`。

### 练习 3: 挑战（可选）

设计一个「热循环 + 装备切换」的混合方案：

- 玩家可以通过 UI/脚本在**运行时**切换当前武器（动态多态）。
- 进入战斗热循环后，当前武器类型在**编译期**确定并批量处理（静态多态）。

给出代码框架：用 `IWeapon&` 保存玩家装备，在切换到战斗状态时用模板函数 `enterCombat<CurrentWeapon>(...)` 把当前具体武器注入给 `StaticHero` 进行批量攻击。说明这种组合方式的优势与局限。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 把 `Sword sword;` 保留，`StaticHero<Sword>` 改为 `StaticHero<Bow>` 后，需要先有 `Bow bow;`，再构造 `StaticHero<Bow> staticBowHero(bow, logger);`。
>
> 模板在编译期为每种武器类型生成一个 `StaticHero` 实例。`WeaponT` 可以是任何满足「有 `name()` 和 `damage()` 方法」的类型，所以切换武器类型只是换个模板参数，不需要改 `StaticHero` 的源码——这正是静态多态的鸭子类型特性。

> [!tip]- 练习 2 参考答案
> ```cpp
> template<typename Derived>
> class WeaponBase {
> public:
>     int damage() const {
>         return static_cast<const Derived*>(this)->damage();
>     }
>     std::string name() const {
>         return static_cast<const Derived*>(this)->name();
>     }
> };
>
> class Sword : public WeaponBase<Sword> {
> public:
>     int         damage() const { return 15; }
>     std::string name() const   { return "铁剑"; }
> };
>
> class Bow : public WeaponBase<Bow> {
> public:
>     int         damage() const { return 12; }
>     std::string name() const   { return "长弓"; }
> };
>
> template<typename WeaponT>
> class CrtpHero {
> public:
>     CrtpHero(WeaponBase<WeaponT>& weapon, ILogger& logger)
>         : weapon_(weapon), logger_(logger) {}
>
>     void attack() const {
>         logger_.log("CRTP Hero 用 " + weapon_.name() + " 造成 " +
>                     std::to_string(weapon_.damage()) + " 点伤害");
>     }
>
> private:
>     WeaponBase<WeaponT>& weapon_;
>     ILogger&             logger_;
> };
> ```
>
> `main()` 中这样使用：
> ```cpp
> Sword s;
> Bow   b;
> CrtpHero<Sword> ch1(s, logger);
> CrtpHero<Bow>   ch2(b, logger);
> ch1.attack();
> ch2.attack();
> ```

> [!tip]- 练习 3 参考答案（可选）
> 代码框架：
> ```cpp
> class CombatSession {
> public:
>     void setWeapon(IWeapon& w) { weapon_ = &w; }
>
>     template<typename ConcreteWeapon>
>     void startCombat(std::vector<StaticHero<ConcreteWeapon>>& heroes) {
>         // 进入热循环前，由脚本层根据 weapon_ 的实际类型决定模板参数
>         runHotLoop(heroes);
>     }
> private:
>     IWeapon* weapon_ = nullptr;
> };
> ```
>
> 优势：装备切换保留动态多态的灵活性；热循环内使用静态多态获得更好的内联和缓存表现 [INFERENCE]。
>
> 局限：需要把热循环代码写成模板，或在外层做一次类型分发（`if`/`switch` 或 `std::variant`），无法真正在运行时把 `StaticHero<Sword>` 变成 `StaticHero<Bow>`。类型一旦进入热循环函数就已经固定。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [C++ Core Guidelines - T.1: Use templates to raise the level of abstraction of code](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rt-raise)
- [C++ Reference - Templates](https://en.cppreference.com/w/cpp/language/templates)
- [Wikipedia - Curiously Recurring Template Pattern](https://en.wikipedia.org/wiki/Curiously_recurring_template_pattern)
- Andrei Alexandrescu, *Modern C++ Design*：第 1 章对策略模式、CRTP 与编译期多态有深入讨论

---

## 常见陷阱

- **对不需要优化的代码使用模板**：配置读取、UI 回调、每帧只调用几次的逻辑，用虚函数足够清晰。强行模板化只会增加编译时间和二进制体积。
- **在需要运行时替换的场景误用静态多态**：如果武器类型必须由脚本或玩家背包在运行时切换，不要让 `Hero` 完全模板化，否则无法把 `Hero<Sword>` 换成 `Hero<Bow>`。
- **忽视代码膨胀**：每新增一种武器类型就多生成一份 `StaticHero` 代码。高频类型可以模板化，低频或未来可能动态扩展的类型应保留动态接口。
- **模板实现留在源文件**：模板的实现通常必须放在头文件中（或在实例化点可见），否则会出现链接错误。如果团队对头文件膨胀敏感，需要权衡。
- **盲目相信「零开销」**：模板能消除间接跳转，但过度内联、寄存器压力、代码体积膨胀反而可能让缓存失效 [INFERENCE]。始终用实际场景的性能分析（profiler）做最终判断。
