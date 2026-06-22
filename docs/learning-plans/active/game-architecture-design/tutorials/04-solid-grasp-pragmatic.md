---
title: SOLID、GRASP 与务实原则
updated: 2026-06-22
tags: [solid, grasp, design-principles, code-smells, pragmatic-design, game-architecture, c-sharp, refactoring]
---

> 所属计划: 游戏架构设计
> 预计耗时: 90min
> 前置知识: [[03-coupling-cohesion-di|第3章 耦合、内聚与依赖管理（IoC/DI）]]

---

## 1. 概念讲解

### 为什么需要这个？

游戏代码有一个 notorious 的 reputation：快速迭代、需求多变、截止日期紧迫，导致"能跑就行"的代码迅速堆积成山。三个月后，一个看似简单的"让 Boss 也能被冰冻"的需求，会牵一发而动全身，引发长达一周的调试噩梦。

这不是因为开发者能力不足，而是因为**缺乏有意识的责任分配原则**。当 20 个系统都直接操作玩家的坐标，当武器的伤害计算散落在 8 个 `switch` 分支里，当"敌人"的继承树为了复用代码而强行把 Boss 和史莱姆绑在一起——架构的腐化就开始了。

SOLID、GRASP 与务实原则提供的是一套**决策框架**：不是告诉你"必须这样做"，而是帮你在写下一行代码前问出正确的问题——"这个变化点应该封装在哪里？""谁应该拥有这个数据？""这个依赖关系是否可替代？"

游戏开发尤其需要这种框架，因为我们是**在不确定中建造**。玩法机制可能在下周被推翻，性能瓶颈可能在压测时才暴露，平台移植可能要求替换整个子系统。没有原则的指导，"临时方案"会永久化；但盲目遵循教条，又会在"Hello World"级别的问题上建造抽象金字塔。

### 核心思想

#### SOLID：五个责任分配原则

SOLID 由 Robert C. Martin 总结，是面向对象设计的基石。每条原则都回答一个具体的"谁该负责什么"问题。

**SRP：单一职责原则（Single Responsibility Principle）**

> "一个类应该只有一个引起变化的原因。"

不是"一个类只做一件事"这种模糊说法，而是**变化源的收敛**。如果"伤害数值调整"和"动画触发逻辑"都会让你打开同一个文件，这个类就承载了多个职责。

游戏反例：一个 `Player` MonoBehaviour 处理输入、移动、动画、音效、存档、UI 更新。任何子系统的需求变更都迫使你修改这个 God 对象，引发不必要的回归测试。

**OCP：开闭原则（Open/Closed Principle）**

> "对扩展开放，对修改关闭。"

不是禁止修改代码，而是**将变化点隔离到可插入的扩展点**。当新增武器类型时，应该创建新类而不是在现有 `switch` 里添加分支。

游戏反例：武器系统用 `switch(weaponType)` 分发行为，每次新增武器都要修改核心战斗逻辑，引入回归风险。

**LSP：里氏替换原则（Liskov Substitution Principle）**

> "子类型必须能够替换其基类型，而不改变程序的正确性。"

继承是"is-a"的强承诺。如果 `Boss : Enemy` 但 Boss 无法被击飞（而所有 Enemy 都应该可以），这个继承关系就撒谎了。

游戏反例：为了复用 `Unit` 类的代码，让 `Boss` 继承 `Unit`，但 Boss 免疫位移效果，于是在 `TakeDamage` 中 `if (this is Boss) return;`——这破坏了多态的根基，调用方无法信任抽象。

**ISP：接口隔离原则（Interface Segregation Principle）**

> "客户端不应被迫依赖它们不使用的接口。"

巨大的 `IEntity` 接口强迫所有实现者提供 `Serialize()`、`Render()`、`PlaySound()`，即使某个系统只关心 `TakeDamage()`。

游戏反例：所有游戏对象实现 `IGameObject`，包含 15 个方法。一个只参与碰撞检测的粒子效果，被迫实现存档、AI、动画接口。

**DIP：依赖倒置原则（Dependency Inversion Principle）**

> "高层模块不应依赖低层模块，二者都应依赖抽象。"

不是"用接口代替类"的形式主义，而是**控制权的反转**。`PlayerController` 决定何时攻击，但"如何攻击"由注入的 `IWeapon` 决定。

游戏反例：`PlayerController` 直接 `new PhysicsEngine()` 或 `GameObject.Find("AudioManager")`，将自身绑定到具体的生命周期和实现细节。

---

#### GRASP：通用责任分配软件模式

GRASP 由 Craig Larman 提出，比 SOLID 更具体地回答"给新行为分配给谁"的问题。9 个模式分为创建型、结构型、行为型。

| 模式 | 核心问题 | 游戏映射 |
|------|---------|---------|
| **Information Expert** | 谁拥有数据，谁负责相关计算 | `DamageCalculator` 不该凭空知道护甲公式，应该由 `ArmorStats` 提供 |
| **Creator** | 谁应该创建 A | 容器创建部件，`WeaponFactory` 创建 `IWeapon` 实例 |
| **Controller** | 谁接收系统事件 | `CombatController` 接收攻击输入，而非 `Player` 直接处理 |
| **Low Coupling** | 如何减少依赖影响 | 玩家通过 `IInventory` 接口操作背包，而非直接访问 `List<Item>` |
| **High Cohesion** | 如何保持类的聚焦 | `MonsterAI` 只处理决策，不处理动画播放 |
| **Indirection** | 如何解耦直接依赖 | `EventBus` 作为发布者与订阅者的中介 |
| **Polymorphism** | 如何根据类型变化行为 | `IWeapon` 替代 `switch(weaponType)` |
| **Protected Variations** | 如何保护稳定点不受变化影响 | 存档格式变化时，`ISaveSystem` 接口保护游戏逻辑 |
| **Pure Fabrication** | 当 Expert 导致耦合时，创造不代表现实概念的类 | `DamageCalculator` 不是"真实物体"，但集中计算逻辑减少耦合 |

GRASP 与 SOLID 是互补的：SOLID 告诉你"什么是好的"，GRASP 告诉你"怎么做到"。例如，应用 **Information Expert** 自然导向 **SRP**；**Indirection** 和 **Polymorphism** 是实现 **OCP** 和 **DIP** 的具体手段。

---

#### 务实原则：当教条撞上现实

SOLID 和 GRASP 是**启发式**，不是**算法**。游戏开发中有明确的务实边界：

- **KISS（Keep It Simple, Stupid）**：能工作且可理解的代码，优于"理论上更优雅"但无人维护的代码。一个 50 行的线性脚本，比 5 个类协作的框架更适合一次性过场动画。

- **YAGNI（You Aren't Gonna Need It）**：不要为"未来可能"的需求创建抽象。如果你只有两种武器且短期内不会增加，`switch` 比策略模式更诚实。当第三种武器出现时，重构的成本往往低于维护不必要抽象的沉没成本。

- **DRY（Don't Repeat Yourself）**：但游戏开发中有**有原则的重复**。热路径中的内联（如每帧执行的碰撞检测）可能故意复制计算以避免函数调用开销。两个子系统的相似代码，如果变化原因不同（如"玩家受伤"和"环境伤害"），复制比错误的抽象更安全。

- **Law of Demeter**：不要遍历对象图（`player.Weapon.Enchantment.DamageBonus`）。但游戏实体组件系统中，`transform.position` 的链式访问是领域惯例，强行封装反而增加噪音。

**务实的核心判断**：这个抽象的保护对象是否存在？变化的频率是否值得封装成本？团队能否理解并维护这个设计？

---

#### 设计坏味：识别腐化的早期信号

坏味（Code Smell）是 Martin Fowler 提出的概念：不是 Bug，但暗示深层设计问题。

| 坏味 | 表现 | 游戏案例 |
|------|------|---------|
| **God Object** | 类知道太多、做太多 | `Monster` 类含 AI、动画、音效、掉落、存档、粒子 |
| **Feature Envy** | 类频繁访问其他类的数据 | `DamageCalculator` 不断读取 `Player` 的私有字段 |
| **Shotgun Surgery** | 一个变化需要修改多个类 | 新增伤害类型时，修改 `Weapon`、`Enemy`、`UI`、`SaveSystem` |
| **Primitive Obsession** | 用原始类型代替领域概念 | `int health` 而非 `Health` 值对象，导致负数、溢出到处检查 |
| **Data Clumps** | 多个数据总是一起出现 | `x, y, z` 散落各处，而非 `Vector3` |
| **Speculative Generality** | 为不存在的需求创建抽象 | `IWeapon` 接口在只有一把剑的原型阶段 |
| **Divergent Change** | 一个类因不同原因被修改 | `Player` 因输入系统更新和存档格式更新而同时修改 |

识别坏味的能力，比记住原则更重要。原则是目标，坏味是路标——它们告诉你当前代码与目标的偏离方向。

---

#### 游戏案例映射

| 系统 | 常见错误 | 原则/坏味 |
|------|---------|----------|
| 武器系统 | `switch(weaponType)` 分发伤害 | OCP 违反；用策略模式 + OCP |
| 敌人继承树 | `Boss : Enemy` 但免疫位移 | LSP 违反；用组合代替继承 |
| 玩家控制器 | 直接 `new` 或 `Find` 依赖 | DIP 违反；构造函数注入 |
| 伤害计算 | 散落在各处的 `if-else` | SRP + Information Expert |
| 存档系统 | 直接序列化内部结构 | Protected Variations；`ISaveSystem` 隔离格式变化 |

---

## 2. 代码示例

本节展示一个典型的"坏味道→重构"过程：武器系统从枚举+`switch` 演进为基于策略模式的扩展设计。

### 坏味道版：枚举与 switch 的陷阱

```csharp
// 违反 OCP、SRP：新增武器必须修改此类
public enum WeaponType { Sword, Axe, Bow }

public class Weapon
{
    public WeaponType Type { get; set; }
    
    public void Attack()
    {
        switch (Type)
        {
            case WeaponType.Sword:
                Console.WriteLine("Slash! Damage: 10");
                break;
            case WeaponType.Axe:
                Console.WriteLine("Chop! Damage: 15, Armor Pierce");
                break;
            case WeaponType.Bow:
                Console.WriteLine("Shoot! Damage: 8, Range: 20");
                break;
            default:
                throw new ArgumentOutOfRangeException();
        }
    }
    
    // 新增：暴击逻辑也塞在这里
    public void CriticalHit()
    {
        switch (Type)
        {
            case WeaponType.Sword: /* ... */ break;
            case WeaponType.Axe: /* ... */ break;
            // 漏了 Bow！编译通过，运行时崩溃
        }
    }
}
```

**问题诊断**：
- **OCP 违反**：新增武器类型需要修改 `Weapon` 类，每次修改引入回归风险
- **SRP 违反**：`Weapon` 同时承担"数据持有"和"行为分发"和"伤害计算"
- **DIP 违反**：`PlayerCombat` 若使用此类，直接依赖具体实现

---

### 重构版：策略模式 + 依赖注入

```csharp
using System;

// ============================================
// 抽象：变化点被隔离到可扩展的接口
// ============================================
public interface IWeapon
{
    string Name { get; }
    int BaseDamage { get; }
    void Attack();
}

// ============================================
// 具体策略：每个武器独立封装，互不影响
// ============================================
public class Sword : IWeapon
{
    public string Name => "Sword";
    public int BaseDamage => 10;
    
    public void Attack() => Console.WriteLine("Slash! Swift blade cuts through!");
}

public class Axe : IWeapon
{
    public string Name => "Axe";
    public int BaseDamage => 15;
    
    public void Attack()
    {
        Console.WriteLine("Chop! Heavy blow with armor piercing!");
        Console.WriteLine("  [Passive] Armor Pierce: Ignores 50% defense");
    }
}

// ============================================
// 工厂：集中创建逻辑，隔离"new"的细节
// ============================================
public static class WeaponFactory
{
    public static IWeapon Create(string weaponName) => weaponName.ToLower() switch
    {
        "sword" => new Sword(),
        "axe" => new Axe(),
        _ => throw new ArgumentException($"Unknown weapon: {weaponName}")
    };
}

// ============================================
// 高层模块：依赖抽象，运行时切换
// ============================================
public class PlayerCombat
{
    private IWeapon _weapon;
    
    // 构造函数注入：DIP 的具体实现
    public PlayerCombat(IWeapon weapon)
    {
        _weapon = weapon ?? throw new ArgumentNullException(nameof(weapon));
    }
    
    public void PerformAttack()
    {
        Console.WriteLine($"[Player] Wielding {_weapon.Name} (DMG: {_weapon.BaseDamage})");
        _weapon.Attack();
    }
    
    // 运行时切换武器，无需重新实例化 PlayerCombat
    public void Equip(IWeapon newWeapon)
    {
        _weapon = newWeapon ?? throw new ArgumentNullException(nameof(newWeapon));
        Console.WriteLine($"[Player] Switched to {newWeapon.Name}");
    }
}

// ============================================
// 程序入口：组合根（Composition Root）
// ============================================
class Program
{
    static void Main()
    {
        // 组合根：唯一知道具体类的地方
        var player = new PlayerCombat(WeaponFactory.Create("sword"));
        
        player.PerformAttack();
        Console.WriteLine();
        
        // 运行时切换：OCP 的胜利——无需修改 PlayerCombat
        player.Equip(WeaponFactory.Create("axe"));
        player.PerformAttack();
    }
}
```

**运行方式:**

```bash
dotnet new console -n WeaponSystem
cd WeaponSystem
# 将上述代码写入 Program.cs
dotnet run
```

**预期输出:**

```text
[Player] Wielding Sword (DMG: 10)
Slash! Swift blade cuts through!

[Player] Switched to Axe
[Player] Wielding Axe (DMG: 15)
Chop! Heavy blow with armor piercing!
  [Passive] Armor Pierce: Ignores 50% defense
```

**关键设计决策解析**：

| 结构 | 体现的原则 | 替代方案的代价 |
|------|-----------|-------------|
| `IWeapon` 接口 | OCP + DIP + Polymorphism | 枚举+switch 的修改扩散 |
| `WeaponFactory` | Creator + Pure Fabrication | `new` 散布在业务代码中 |
| 构造函数注入 `IWeapon` | DIP + Low Coupling | 直接 `new Sword()` 的硬绑定 |
| `Equip()` 运行时切换 | 状态模式雏形 | 重新创建 `PlayerCombat` 的冗余 |

---

## 3. 练习

### 练习 1: 基础

新增 `Bow` 武器并实现远程攻击特性。要求：**不修改 `PlayerCombat` 或现有武器类**（`Sword`、`Axe`），验证 OCP 的"对扩展开放"。

- `Bow` 的 `BaseDamage` 为 8
- `Attack()` 输出包含 "Range: 20" 的远程攻击描述
- 在 `Main` 中演示玩家从 Sword 切换到 Bow 的过程

---

### 练习 2: 进阶

用**装饰器模式**给武器附加"中毒"效果。创建 `PoisonedWeapon : IWeapon`，包装另一个 `IWeapon`：

- 转发 `Name` 和 `BaseDamage`（可加成或保持原值）
- `Attack()` 先执行被包装武器的 `Attack()`，然后追加毒伤日志
- 演示：给 `Sword` 附加中毒效果后，通过 `PlayerCombat` 使用

要求：保持 `IWeapon` 接口不变，体现"组合优于继承"。

---

### 练习 3: 挑战（可选）

分析以下类违反了哪些 SOLID/GRASP/设计坏味，并给出重构方向：

```csharp
class Monster
{
    public void UpdateAI() { /* 100 行：寻路、决策、状态机 */ }
    public void PlayAnimation(string anim) { /* 直接调用 Animator */ }
    public void TakeDamage(int dmg) 
    { 
        /* 修改 HP，播放粒子，更新 UI，记录日志，检查掉落 */ 
    }
    public string Serialize() { /* JSON 序列化内部字段 */ }
    public void SpawnParticles() { /* 直接操作 ParticleSystem */ }
    public void HandleLoot() { /* 计算掉落，修改玩家背包 */ }
}
```

要求：指出至少 3 个具体违反的原则/坏味，给出拆分后的类结构和协作方式。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 
> ```csharp
> // 新增文件：Bow.cs —— 零修改现有代码
> public class Bow : IWeapon
> {
>     public string Name => "Bow";
>     public int BaseDamage => 8;
>     
>     public void Attack()
>     {
>         Console.WriteLine("Twang! Arrow flies true!");
>         Console.WriteLine("  [Passive] Range: 20, Precision: Headshot bonus beyond 15m");
>     }
> }
> 
> // Program.cs 修改：组合根是唯一变化点
> class Program
> {
>     static void Main()
>     {
>         var player = new PlayerCombat(WeaponFactory.Create("sword"));
>         player.PerformAttack();
>         Console.WriteLine();
>         
>         // 运行时切换：PlayerCombat 完全无感知
>         player.Equip(WeaponFactory.Create("bow"));
>         player.PerformAttack();
>     }
> }
> 
> // WeaponFactory 扩展（唯一需要修改的"注册点"）
> public static class WeaponFactory
> {
>     public static IWeapon Create(string weaponName) => weaponName.ToLower() switch
>     {
>         "sword" => new Sword(),
>         "axe" => new Axe(),
>         "bow" => new Bow(),        // 新增：集中注册
>         _ => throw new ArgumentException($"Unknown weapon: {weaponName}")
>     };
> }
> ```
> 
> 设计要点：工厂是"有节制的修改点"——虽然需要添加 `case`，但业务逻辑（`PlayerCombat`、现有武器）完全封闭。这是 OCP 的务实边界：完全消除修改是不可能的，但将修改限制在"注册/配置"层，而非核心逻辑。

> [!tip]- 练习 2 参考答案
> 
> ```csharp
> // 装饰器：包装任何 IWeapon，附加中毒效果
> public class PoisonedWeapon : IWeapon
> {
>     private readonly IWeapon _inner;
>     private readonly int _poisonDamage;
>     
>     public PoisonedWeapon(IWeapon inner, int poisonDamage = 3)
>     {
>         _inner = inner ?? throw new ArgumentNullException(nameof(inner));
>         _poisonDamage = poisonDamage;
>     }
>     
>     // 转发：装饰器保持被包装者的身份
>     public string Name => $"{_inner.Name} [Poisoned]";
>     public int BaseDamage => _inner.BaseDamage + _poisonDamage;
>     
>     public void Attack()
>     {
>         _inner.Attack();  // 先执行原始行为
>         Console.WriteLine($"  [Poison] {_poisonDamage} damage/sec for 5 seconds!");
>     }
> }
> 
> // 使用演示
> class Program
> {
>     static void Main()
>     {
>         // 基础武器
>         IWeapon sword = new Sword();
>         
>         // 动态附加效果：运行时组合，非编译时继承
>         IWeapon poisonedSword = new PoisonedWeapon(sword, poisonDamage: 5);
>         
>         var player = new PlayerCombat(poisonedSword);
>         player.PerformAttack();
>         Console.WriteLine();
>         
>         // 甚至可以双重装饰（虽然此例中 Name 会变得冗长）
>         IWeapon doublePoisoned = new PoisonedWeapon(poisonedSword, poisonDamage: 2);
>         player.Equip(doublePoisoned);
>         player.PerformAttack();
>     }
> }
> ```
> 
> 输出：
> ```
> [Player] Wielding Sword [Poisoned] (DMG: 15)
> Slash! Swift blade cuts through!
>   [Poison] 5 damage/sec for 5 seconds!
> 
> [Player] Switched to Sword [Poisoned] [Poisoned] (DMG: 17)
> Slash! Swift blade cuts through!
>   [Poison] 5 damage/sec for 5 seconds!
>   [Poison] 2 damage/sec for 5 seconds!
> ```
> 
> 设计要点：装饰器模式是 OCP 的极致体现——新增"效果"这种横切关注点，无需修改任何武器类或 `PlayerCombat`。`PoisonedWeapon` 是 **Pure Fabrication**：现实中不存在"被中毒的剑"这种独立物体，但代码中它是合理的责任分配。

> [!tip]- 练习 3 参考答案
> 
> **违反分析：**
> 
> | 问题 | 违反原则/坏味 | 具体表现 |
> |------|-------------|---------|
> | 类过大、职责混杂 | **God Object** + **SRP** | AI、动画、伤害、存档、粒子、掉落六类变化源 |
> | `TakeDamage` 做太多 | **SRP** + **Information Expert** | HP 修改、UI 更新、日志、掉落检查——不属于 Monster 的专业领域 |
> | `HandleLoot` 修改玩家背包 | **Feature Envy** + **Low Coupling** | Monster 直接操作 Player 的数据 |
> | `Serialize` 硬编码格式 | **Protected Variations** | JSON 格式变化将扩散到所有 Monster 实例 |
> | 动画/粒子直接调用 | **DIP** | 硬依赖 Unity 具体 API，无法测试 |
> 
> **重构方向：**
> 
> ```csharp
> // 拆分后的结构：每个类有单一变化原因
> 
> public class MonsterStats  // Information Expert：拥有数据
> {
>     public int HP { get; private set; }
>     public int MaxHP { get; }
>     public void TakeRawDamage(int amount) => HP = Math.Max(0, HP - amount);
> }
> 
> public class MonsterAI    // 变化源：AI 算法迭代
> {
>     public void Update(MonsterStats stats, Transform transform) { /* ... */ }
> }
> 
> public class MonsterAnimator  // 变化源：动画系统升级
> {
>     public void PlayHitReaction() { /* 通过 IAnimationSystem 抽象 */ }
> }
> 
> public class MonsterLoot      // 变化源：掉落规则调整
> {
>     public void GenerateDrop(Vector3 position, IInventory targetInventory) { /* ... */ }
> }
> 
> public class MonsterCombat    // 协调者：非 Expert，但集中战斗流程
> {
>     private readonly MonsterStats _stats;
>     private readonly MonsterAnimator _animator;
>     private readonly MonsterLoot _loot;
>     private readonly IEventBus _events;  // Indirection：解耦通知
>     
>     public void TakeDamage(int damage, DamageSource source)
>     {
>         _stats.TakeRawDamage(damage);
>         _animator.PlayHitReaction();
>         _events.Publish(new DamageTakenEvent(this, damage, source));
>         
>         if (_stats.HP <= 0)
>         {
>             _loot.GenerateDrop(transform.position, source.LooterInventory);
>             _events.Publish(new MonsterDiedEvent(this));
>         }
>     }
> }
> 
> public class MonsterSerializer : ISerializer<MonsterData>  // Pure Fabrication
> {
>     public string Serialize(MonsterData data) { /* 格式隔离 */ }
> }
> ```
> 
> 协作方式：`MonsterCombat` 作为 **Controller** 协调流程，但将具体行为委托给 Expert。通过 `IEventBus` 实现 **Indirection**，`MonsterDiedEvent` 可被任务系统、成就系统、音频系统订阅，无需 `Monster` 知道它们存在。

> [!note] 答案使用方式
> 如果你的实现通过了测试或达到了题目要求，就是正确的。参考答案展示的是"符合原则的走向"，而非唯一标准答案。例如，练习 2 的装饰器可以改为 `PoisonEffect : IEffect` 与 `IWeapon` 正交的设计；练习 3 的拆分粒度可根据团队规模调整——小团队可能合并 `MonsterAnimator` 和 `MonsterVFX`，但 `MonsterStats` 与 `MonsterLoot` 的分离是硬边界。
>
> ---

## 4. 扩展阅读

- Robert C. Martin, "Solid Relevance"：https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html —— SOLID 在现代开发中的相关性讨论，包括对"SOLID 已死"论点的回应。
- Martin Fowler, "Code Smell"：https://martinfowler.com/bliki/CodeSmell.html —— 设计坏味的经典定义，强调"坏味是深层问题的表面迹象"。
- Craig Larman, GRASP 原则（Tübingen 课程讲义）：https://ps.informatik.uni-tuebingen.de/teaching/ss19/se/5_grasp.pdf —— 控制器、信息专家、低耦合高内聚等模式的系统化讲解。
- Martin Fowler, "Refactoring: Improving the Design of Existing Code"（第2版）—— 坏味目录与重构手法的权威参考，游戏代码同样适用。
- Casey Muratori, "Clean Code, Horrible Performance"：https://www.computerenhance.com/p/clean-code-horrible-performance —— 对教条式抽象的批判，游戏热路径优化的务实视角。

---

## 常见陷阱

- **把 SOLID 当作绝对律令，对简单工具类也强行拆分，导致过度设计**。一个 30 行的 `Vector2` 扩展方法类，不需要拆成 `Vector2Adder`、`Vector2Multiplier`、`Vector2Normalizer`。正确做法：用"变化频率"和"团队规模"作为拆分阈值，[[30-performance-budgets|第30章 性能预算]] 会深入讨论热路径的务实边界。

- **用继承复用代码却违反 LSP，子类覆盖父类行为抛出异常或破坏不变式**。`FlyingEnemy : Enemy` 但 `FlyingEnemy.TakeDamage` 抛出 `NotSupportedException`（"飞行单位不受重力伤害"）。正确做法：用组合代替继承，`FlyingEnemy` 包含 `Enemy` 而非继承它；或提取 `IDamageable` 接口，让 `FlyingEnemy` 和 `Enemy` 平行实现。

- **为"未来可能的需求"创建抽象（Speculative Generality），YAGNI 违反**。原型阶段就设计 `IWeaponEffect`、`IWeaponEnchantment`、`IWeaponDurabilitySystem` 接口体系，但当前只有一把无特性的剑。正确做法：让代码"有味道地"工作，当第三种变化出现时再抽象——"三次法则"：第一次复制，第二次复制，第三次抽象。