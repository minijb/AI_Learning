---
title: 玩法解耦
updated: 2026-06-22
tags: [game-architecture, mvc, mvp, gameplay-tags, data-binding, decoupling, csharp]
---

> 所属计划: 游戏架构设计
> 预计耗时: 60min
> 前置知识: [[13-game-state-management|13]]、[[14-event-driven-architecture|14]]

---

## 1. 概念讲解

### 为什么需要这个？

游戏玩法代码是**变化最剧烈、耦合最容易失控**的区域。一个典型症状是：`PlayerController` 直接调用 `Enemy.TakeDamage()`，UI 代码里塞满了 `FindObjectOfType<HealthSystem>()`，策划改一个数值就要重新编译整个项目。当项目规模扩大，这些隐式依赖会形成"意大利面条"——牵一发而动全身，Bug 修复引入新 Bug，功能迭代越来越慢。

玩法解耦的本质是**建立清晰的模块边界**，让"数据是什么""如何表现""如何响应"三件事独立演化。这与 [[03-coupling-cohesion-di|第3章]] 的依赖注入思想一脉相承，但聚焦于游戏特有的动态性：运行时状态多变、表现层与逻辑层交织、策划需要频繁调整规则。

### 核心思想

#### 1.1 游戏内 MVC/MVP/MVVM

经典 MVC 在游戏语境下的映射：

| 角色 | 职责 | 游戏典型实现 |
|:---|:---|:---|
| `Model` | 纯数据 + 业务规则 | `ScriptableObject` 资产、POCO 类、ECS 中的 Component 数据 |
| `View` | 视觉/听觉表现 | `MonoBehaviour` 渲染、UI Toolkit、粒子系统 |
| `Controller/Presenter` | 输入转换、协调 M 与 V | 输入处理、动画触发、状态机推进 |

Unity 的常见变体是 **Model（ScriptableObject）+ View（MonoBehaviour）+ Controller（MonoBehaviour 或纯类）**。Model 作为资产可独立编辑，View 只负责"显示什么"，Controller 回答"何时改变"。

与 [[10-component-based|第10章]] 的组件模式结合：一个 `HealthComponent` 可以是 Model（存数据）+ 小 Controller（处理死亡逻辑），而 `HealthBarUI` 是 View。

#### 1.2 GameplayTags：解决 bool 爆炸

游戏实体常处于复合状态：`IsBurning && !IsFrozen && (IsStunned || IsRooted)`。用 bool 字段表达会导致组合爆炸，且隐式规则（"燃烧时不能冰冻"）散落在各处。

GameplayTags 是**层级化的字符串标签**，如 `Status.Burning`、`Ability.Melee.Damage.Physical`。核心能力：
- `HasTag(tag)`：精确匹配
- `MatchesTag(parent)`：层级匹配（`Status.Burning` 匹配 `Status`）
- `GameplayTagContainer`：标签集合，支持批量查询
- `GameplayTagQuery`：复杂逻辑表达式（如 `Status.Burning AND NOT Status.Wet`）

Unreal Engine 原生提供完整实现；Unity 需自行构建或采用第三方方案。Tag 系统让状态从"字段"变成"数据"，规则从"硬编码"变成"可配置"。

#### 1.3 数据绑定：消灭手动同步

传统做法：每次 `HP` 变化，手动调用 `healthBar.UpdateSlider(hp / maxHp)`。问题：遗漏更新点、UI 与逻辑耦合、测试困难。

数据绑定建立**自动同步管道**：
- **单向绑定**：`Model.HP → View.Slider.value`（模型驱动 UI）
- **双向绑定**：`InputField.text ↔ Model.PlayerName`（UI 与模型互相同步）

.NET 的 `INotifyPropertyChanged` 是标准机制；Unity UI Toolkit（2023+）内置 `DataBinding` 系统，支持路径表达式如 `binding-path="hp"`。

#### 1.4 数据驱动：规则外置

将数值、概率、条件判断从 C# 代码迁移到**可编辑资产**：

```csharp
// 数据定义
[CreateAssetMenu]
public class DamageType : ScriptableObject {
    public GameplayTagContainer tags;
    public float baseDamage;
    public DamageType[] weaknesses; // 克制关系
}

// 逻辑代码只解释数据
public float CalculateDamage(DamageType attacker, DamageType defender) {
    if (defender.weaknesses.Contains(attacker)) return attacker.baseDamage * 2;
    return attacker.baseDamage;
}
```

这与 [[13-game-state-management|第13章]] 的状态管理结合：运行时状态是"动态数据"，资产配置是"静态数据"，两者分离。

#### 1.5 模块边界：物理隔离

按功能划分 Assembly/Namespace：

```
Core/           ← 无外部依赖，定义接口与事件
├── ITarget.cs
├── IDamageable.cs
└── EventBus.cs

Gameplay/       ← 依赖 Core
├── HealthModel.cs
├── EffectSystem.cs
└── GameplayTag.cs

UI/             ← 依赖 Core + Gameplay（仅读 Model）
├── HealthBarView.cs
└── InventoryView.cs

Input/          ← 依赖 Core
└── PlayerInputController.cs
```

**禁止跨层直接引用**：UI 不能 `new Enemy()`，只能订阅 `EventBus<EnemyDamaged>`；AI 不能调用 `PlayerInventory.AddItem()`，只能通过 `IInventory` 接口。

#### 1.6 避免 Gameplay 紧耦合：意图表达

反模式：`playerController.OnAttackButton += enemy.TakeDamage;`（直接操控）

正模式：通过**能力/命令/事件**表达意图：

```csharp
// 攻击者只发出"意图"
var command = new DamageCommand {
    source = this,
    target = targetSelector.CurrentTarget, // 可能是 ITarge
    damage = weapon.CalculateDamage()
};
command.Execute(); // 内部走事件或系统处理

// 或完全事件化
EventBus.Publish(new AttackEvent(this, targetSelector.CurrentTarget, weapon.DamageType));
```

这与 [[17-command-ability-system|第17章]] 的命令模式、[[14-event-driven-architecture|第14章]] 的事件架构形成连续谱。

---

## 2. 代码示例

以下 .NET 6+ 控制台程序演示两个核心机制：
1. **GameplayTag 系统**：层级标签、容器查询、基于 Tag 的 EffectSystem
2. **MVC 数据绑定**：`HealthModel` 通过事件驱动 `HealthBarView`

```csharp
using System;
using System.Collections.Generic;
using System.Linq;

// ==================== GameplayTag 核心 ====================

public readonly record struct GameplayTag(string Name)
{
    // 层级匹配：Status.Burning 匹配 Status
    public bool Matches(GameplayTag other) =>
        Name == other.Name || Name.StartsWith(other.Name + ".");
    
    public GameplayTag Parent => Name.Contains('.') 
        ? new GameplayTag(Name[..Name.LastIndexOf('.')]) 
        : new GameplayTag("");
}

public class GameplayTagContainer
{
    private readonly HashSet<GameplayTag> tags = new();
    
    public void AddTag(GameplayTag tag) => tags.Add(tag);
    public void RemoveTag(GameplayTag tag) => tags.Remove(tag);
    public bool HasTag(GameplayTag tag) => tags.Any(t => t.Matches(tag));
    public bool HasAny(params GameplayTag[] query) => query.Any(q => HasTag(q));
    public bool HasAll(params GameplayTag[] query) => query.All(q => HasTag(q));
    
    public override string ToString() => string.Join(", ", tags.Select(t => t.Name));
}

// ==================== 基于 Tag 的 EffectSystem ====================

public readonly record struct GameplayEffect(
    GameplayTag Tag,
    float TickInterval,      // 0 = 立即生效
    Action<Character> OnApply,
    Action<Character> OnTick,
    Action<Character> OnRemove
);

public class Character
{
    public string Name { get; }
    public GameplayTagContainer Tags { get; } = new();
    public float HP { get; set; }
    public float MaxHP { get; }
    
    public Character(string name, float maxHp)
    {
        Name = name;
        MaxHP = maxHp;
        HP = maxHp;
    }
    
    public bool CanMove => !Tags.HasTag(new GameplayTag("Status.Stunned"));
    
    public override string ToString() => 
        $"{Name}: HP={HP:F1}/{MaxHP:F1}, Tags=[{Tags}]";
}

public class EffectSystem
{
    private readonly List<(Character target, GameplayEffect effect, float elapsed)> activeEffects = new();
    private float globalTime = 0;
    
    public void ApplyEffect(Character target, GameplayEffect effect)
    {
        target.Tags.AddTag(effect.Tag);
        effect.OnApply?.Invoke(target);
        
        if (effect.TickInterval > 0)
            activeEffects.Add((target, effect, globalTime));
        else
            effect.OnRemove?.Invoke(target); // 立即效果直接移除
    }
    
    public void Update(float deltaTime)
    {
        globalTime += deltaTime;
        
        for (int i = activeEffects.Count - 1; i >= 0; i--)
        {
            var (target, effect, startTime) = activeEffects[i];
            
            if (!target.Tags.HasTag(effect.Tag))
            {
                // 标签被外部移除，清理记录
                activeEffects.RemoveAt(i);
                continue;
            }
            
            var elapsed = globalTime - startTime;
            var ticks = (int)(elapsed / effect.TickInterval);
            var lastTick = (int)((elapsed - deltaTime) / effect.TickInterval);
            
            if (ticks > lastTick)
            {
                effect.OnTick?.Invoke(target);
                
                if (target.HP <= 0)
                {
                    target.Tags.RemoveTag(effect.Tag);
                    effect.OnRemove?.Invoke(target);
                    activeEffects.RemoveAt(i);
                }
            }
        }
    }
    
    public void RemoveEffect(Character target, GameplayTag tag)
    {
        if (target.Tags.HasTag(tag))
        {
            target.Tags.RemoveTag(tag);
            var entry = activeEffects.FindIndex(e => e.target == target && e.effect.Tag.Equals(tag));
            if (entry >= 0)
            {
                activeEffects[entry].effect.OnRemove?.Invoke(target);
                activeEffects.RemoveAt(entry);
            }
        }
    }
}

// ==================== MVC：Model 与 View ====================

public class HealthModel
{
    private float _hp;
    private float _maxHp;
    
    public float HP
    {
        get => _hp;
        set
        {
            var old = _hp;
            _hp = Math.Clamp(value, 0, MaxHP);
            if (!MathF.Abs(old - _hp).Equals(0))
                OnChanged?.Invoke(this);
        }
    }
    
    public float MaxHP
    {
        get => _maxHp;
        set
        {
            _maxHp = value;
            _hp = Math.Min(_hp, _maxHp); // 保持约束
            OnChanged?.Invoke(this);
        }
    }
    
    public float Percent => MaxHP > 0 ? HP / MaxHP : 0;
    
    public event Action<HealthModel> OnChanged;
    
    public HealthModel(float maxHp)
    {
        _maxHp = maxHp;
        _hp = maxHp;
    }
}

// View：纯显示，无业务逻辑
public class HealthBarView
{
    private readonly string _name;
    
    public HealthBarView(string name)
    {
        _name = name;
    }
    
    public void Bind(HealthModel model)
    {
        model.OnChanged += OnHealthChanged;
        OnHealthChanged(model); // 初始同步
    }
    
    public void Unbind(HealthModel model)
    {
        model.OnChanged -= OnHealthChanged;
    }
    
    private void OnHealthChanged(HealthModel model)
    {
        var barLength = 20;
        var filled = (int)(model.Percent * barLength);
        var empty = barLength - filled;
        var bar = new string('█', filled) + new string('░', empty);
        Console.WriteLine($"[{_name}] {bar} {model.HP:F0}/{model.MaxHP:F0} ({model.Percent:P0})");
    }
}

// ==================== 演示场景 ====================

class Program
{
    static void Main()
    {
        Console.WriteLine("=== GameplayTag + EffectSystem Demo ===\n");
        
        // 预定义标签
        var burning = new GameplayTag("Status.Burning");
        var stunned = new GameplayTag("Status.Stunned");
        var statusRoot = new GameplayTag("Status");
        
        var hero = new Character("Hero", 100f);
        var enemy = new Character("Enemy", 50f);
        
        var effectSystem = new EffectSystem();
        
        // 定义燃烧效果：每2秒扣5血，持续
        var burnEffect = new GameplayEffect(
            Tag: burning,
            TickInterval: 2f,
            OnApply: c => Console.WriteLine($"[FX] {c.Name} 身上燃起火焰！"),
            OnTick: c => { c.HP -= 5; Console.WriteLine($"[FX] {c.Name} 受到燃烧伤害 -5 HP"); },
            OnRemove: c => Console.WriteLine($"[FX] {c.Name} 的火焰熄灭了")
        );
        
        // 定义眩晕效果：立即生效，禁止移动
        var stunEffect = new GameplayEffect(
            Tag: stunned,
            TickInterval: 0, // 立即效果，但标签保留
            OnApply: c => Console.WriteLine($"[FX] {c.Name} 被眩晕了！"),
            OnTick: null,
            OnRemove: c => Console.WriteLine($"[FX] {c.Name} 恢复清醒")
        );
        
        // 应用效果
        effectSystem.ApplyEffect(hero, burnEffect);
        effectSystem.ApplyEffect(enemy, stunEffect);
        
        Console.WriteLine($"初始状态: {hero}");
        Console.WriteLine($"初始状态: {enemy}");
        Console.WriteLine($"敌人 CanMove? {enemy.CanMove}");
        Console.WriteLine();
        
        // 模拟时间推进
        for (int tick = 0; tick < 6; tick++)
        {
            Console.WriteLine($"--- Tick {tick} (time={tick * 1.0f:F1}s) ---");
            effectSystem.Update(1.0f);
            
            // 第3秒移除眩晕
            if (tick == 3)
            {
                Console.WriteLine(">>> 移除敌人眩晕");
                effectSystem.RemoveEffect(enemy, stunned);
            }
            
            // 第4秒英雄燃烧也熄灭
            if (tick == 4)
            {
                Console.WriteLine(">>> 英雄火焰熄灭");
                effectSystem.RemoveEffect(hero, burning);
            }
            
            Console.WriteLine($"  {hero}");
            Console.WriteLine($"  {enemy}");
            Console.WriteLine();
        }
        
        Console.WriteLine("\n=== MVC Data Binding Demo ===\n");
        
        var heroHealth = new HealthModel(100f);
        var healthBar = new HealthBarView("Hero");
        
        healthBar.Bind(heroHealth);
        
        Console.WriteLine(">>> 受到攻击 -30");
        heroHealth.HP -= 30;
        
        Console.WriteLine(">>> 治疗 +20");
        heroHealth.HP += 20;
        
        Console.WriteLine(">>> 最大生命值提升 (MaxHP=150)");
        heroHealth.MaxHP = 150;
        
        Console.WriteLine(">>> 受到致命攻击 -999");
        heroHealth.HP -= 999;
        
        healthBar.Unbind(heroHealth);
    }
}
```

**运行方式:**

```bash
# 需要 .NET 6 SDK 或更高版本
dotnet new console -n GameplayDecouplingDemo
cd GameplayDecouplingDemo
# 将上述代码覆盖 Program.cs
dotnet run
```

**预期输出:**

```text
=== GameplayTag + EffectSystem Demo ===

[FX] Hero 身上燃起火焰！
[FX] Enemy 被眩晕了！
初始状态: Hero: HP=100.0/100.0, Tags=[Status.Burning]
初始状态: Enemy: HP=50.0/50.0, Tags=[Status.Stunned]
敌人 CanMove? False

--- Tick 0 (time=0.0s) ---
  Hero: HP=100.0/100.0, Tags=[Status.Burning]
  Enemy: HP=50.0/50.0, Tags=[Status.Stunned]

--- Tick 1 (time=1.0s) ---
  Hero: HP=100.0/100.0, Tags=[Status.Burning]
  Enemy: HP=50.0/50.0, Tags=[Status.Stunned]

--- Tick 2 (time=2.0s) ---
[FX] Hero 受到燃烧伤害 -5 HP
  Hero: HP=95.0/100.0, Tags=[Status.Burning]
  Enemy: HP=50.0/50.0, Tags=[Status.Stunned]

--- Tick 3 (time=3.0s) ---
>>> 移除敌人眩晕
[FX] Enemy 恢复清醒
  Hero: HP=95.0/100.0, Tags=[Status.Burning]
  Enemy: HP=50.0/50.0, Tags=[]

--- Tick 4 (time=4.0s) ---
[FX] Hero 受到燃烧伤害 -5 HP
>>> 英雄火焰熄灭
[FX] Hero 的火焰熄灭了
  Hero: HP=90.0/100.0, Tags=[]
  Enemy: HP=50.0/50.0, Tags=[]

--- Tick 5 (time=5.0s) ---
  Hero: HP=90.0/100.0, Tags=[]
  Enemy: HP=50.0/50.0, Tags=[]

=== MVC Data Binding Demo ===

[Hero] ████████████████████ 100/100 (100 %)
>>> 受到攻击 -30
[Hero] ██████████████░░░░░░ 70/100 (70 %)
>>> 治疗 +20
[Hero] █████████████████░░░ 90/100 (90 %)
>>> 最大生命值提升 (MaxHP=150)
[Hero] █████████████░░░░░░░ 90/150 (60 %)
>>> 受到致命攻击 -999
[Hero] ░░░░░░░░░░░░░░░░░░░░ 0/150 (0 %)
```

---

## 3. 练习

### 练习 1: 基础

为角色扩展 GameplayTag 驱动的状态机：

1. 实现 `Frozen` 标签：角色有 `Status.Burning` 时，若获得 `Status.Frozen`，则两者抵消（移除 Burning，保留 Frozen 1 回合后融化）
2. 实现 `Regenerating` 标签：每 3 秒回复 3 HP，与 `Burning` 可同时存在（先扣后回或先回后扣，需确定顺序）
3. 在 `Character` 上添加 `Move()` 方法，检查 `Status.Stunned` 或 `Status.Frozen` 时禁止移动并输出提示

要求：用 `EffectSystem` 的 Tick 顺序控制处理优先级，用 Tag 查询替代任何 bool 字段。

### 练习 2: 进阶

将 `HealthModel` 改造为完整的数据绑定系统：

1. 实现 `INotifyPropertyChanged` 接口（或模拟其模式），支持 `PropertyChangedEventArgs` 指明变更属性名
2. 创建 `ManaModel`（法力值），与 `HealthModel` 共享同一接口
3. 实现 `CompositeView`：同时显示 HP 和 MP，当任一变化时只刷新对应部分
4. 添加 `TwoWayBinding`：通过 View 的模拟输入（如 `SetHealthFromInput(float value)`）反向修改 Model，验证双向同步

### 练习 3: 挑战（可选）

设计三个模块的边界：AI、Player、Inventory。

约束：
- 三个模块位于不同 Assembly，互不直接引用
- AI 需要"寻找目标"和"拾取掉落物"
- Player 需要"打开背包"和"死亡掉落"
- Inventory 需要"添加物品"和"触发装备效果"

要求：
- 在 `Core` Assembly 定义共享接口（如 `ITarget`、`ILootable`、`IInventory`）
- 用 `EventBus` 广播跨模块事件（如 `EntityDied`、`ItemPickedUp`）
- 画出模块依赖图（Mermaid `graph TD`），标注哪些是接口依赖、哪些是事件依赖

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 核心思路：利用 `EffectSystem.Update` 中的**处理顺序**控制优先级，用 Tag 的增删表达状态转换。
> 
> ```csharp
> // 扩展的 EffectSystem，支持优先级
> public class PriorityEffectSystem : EffectSystem
> {
>     // 按优先级排序：先处理负面，再处理正面
>     protected override IEnumerable<GameplayEffect> GetEffectsInPriorityOrder()
>     {
>         return activeEffects.OrderBy(e => 
>             e.effect.Tag.Name switch {
>                 var s when s.Contains("Burning") => 0,
>                 var s when s.Contains("Frozen") => 1,
>                 var s when s.Contains("Regenerating") => 2,
>                 _ => 99
>             });
>     }
> }
> 
> // Frozen 效果定义：应用时检查并抵消 Burning
> var frozenEffect = new GameplayEffect(
>     Tag: new GameplayTag("Status.Frozen"),
>     TickInterval: 1f, // 每回合检查
>     OnApply: c => {
>         if (c.Tags.HasTag(new GameplayTag("Status.Burning"))) {
>             c.Tags.RemoveTag(new GameplayTag("Status.Burning"));
>             Console.WriteLine($"[FX] {c.Name} 的火焰被寒冰抵消！");
>         }
>     },
>     OnTick: c => {
>         // 冰冻持续1回合后融化
>         Console.WriteLine($"[FX] {c.Name} 的寒冰开始融化...");
>         // 实际实现：用持续计数器，此处简化
>     },
>     OnRemove: c => Console.WriteLine($"[FX] {c.Name} 完全解冻")
> );
> 
> // Character.Move 完全基于 Tag 查询
> public void Move(Vector3 direction)
> {
>     if (Tags.HasTag(new GameplayTag("Status.Stunned"))) {
>         Console.WriteLine($"{Name} 被眩晕，无法移动！");
>         return;
>     }
>     if (Tags.HasTag(new GameplayTag("Status.Frozen"))) {
>         Console.WriteLine($"{Name} 被冰冻，无法移动！");
>         return;
>     }
>     Position += direction;
> }
> ```
> 
> 关键设计：没有 `_isStunned` bool 字段，所有状态查询走 `Tags.HasTag()`；状态转换是**添加/移除 Tag** 的副作用，由 `EffectSystem` 统一协调。

> [!tip]- 练习 2 参考答案
> 
> ```csharp
> // 统一接口
> public interface IBindableModel : INotifyPropertyChanged
> {
>     string ModelName { get; }
> }
> 
> public class HealthModel : IBindableModel
> {
>     private float _hp, _maxHp;
>     
>     public float HP { 
>         get => _hp; 
>         set { _hp = Math.Clamp(value, 0, MaxHP); OnPropertyChanged(nameof(HP)); } 
>     }
>     public float MaxHP { 
>         get => _maxHp; 
>         set { _maxHp = value; HP = _hp; OnPropertyChanged(nameof(MaxHP)); } 
>     }
>     
>     public event PropertyChangedEventHandler PropertyChanged;
>     protected void OnPropertyChanged(string name) => 
>         PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
>     
>     public string ModelName => "Health";
> }
> 
> public class ManaModel : IBindableModel
> {
>     private float _mp, _maxMp;
>     public float MP { get => _mp; set { _mp = value; OnPropertyChanged(nameof(MP)); } }
>     public float MaxMP { get => _maxMp; set { _maxMp = value; OnPropertyChanged(nameof(MaxMP)); } }
>     
>     public event PropertyChangedEventHandler PropertyChanged;
>     protected void OnPropertyChanged(string name) => 
>         PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
>     
>     public string ModelName => "Mana";
> }
> 
> // 复合视图，精准刷新
> public class CompositeStatusView
> {
>     public void Bind(IBindableModel model)
>     {
>         model.PropertyChanged += (s, e) => {
>             if (model is HealthModel && e.PropertyName == nameof(HealthModel.HP))
>                 RefreshHealthBar(((HealthModel)model).HP, ((HealthModel)model).MaxHP);
>             else if (model is ManaModel && e.PropertyName == nameof(ManaModel.MP))
>                 RefreshManaBar(((ManaModel)model).MP, ((ManaModel)model).MaxMP);
>         };
>     }
>     
>     void RefreshHealthBar(float hp, float max) => Console.WriteLine($"[HP] {hp}/{max}");
>     void RefreshManaBar(float mp, float max) => Console.WriteLine($"[MP] {mp}/{max}");
> }
> 
> // 双向绑定：View 通过 Command 模式回写
> public class TwoWayHealthBinding
> {
>     private HealthModel _model;
>     
>     public void Bind(HealthModel model) => _model = model;
>     
>     // 模拟 UI 输入
>     public void SetHealthFromInput(string input)
>     {
>         if (float.TryParse(input, out var value))
>             _model.HP = value; // 触发 PropertyChanged，View 自动刷新
>     }
> }
> ```
> 
> 关键：.NET 的 `INotifyPropertyChanged` 是标准数据绑定契约；Unity UI Toolkit 的 `binding-path` 底层同样依赖此机制。精准刷新（按属性名过滤）避免无关 UI 重绘。

> [!tip]- 练习 3 参考答案
> 
> **Core Assembly（无外部依赖）：**
> 
> ```csharp
> // Interfaces.cs
> public interface ITarget { Vector3 Position { get; } bool IsAlive { get; } }
> public interface ILootable { IEnumerable<Item> GetDrops(); }
> public interface IInventory { bool AddItem(Item item); void RemoveItem(Item item); }
> 
> // Events.cs
> public record EntityDied(ITarget Entity, ILootable LootSource);
> public record ItemPickedUp(IInventory Inventory, Item Item);
> public record EquipmentActivated(IInventory Owner, Item Equipment);
> ```
> 
> **AI Assembly（仅引用 Core）：**
> 
> ```csharp
> public class AIController
> {
>     // 通过接口查询，不依赖 Player 类型
>     public ITarget FindNearestTarget(IEnumerable<ITarget> candidates) => 
>         candidates.Where(t => t.IsAlive).OrderBy(t => DistanceTo(t)).FirstOrDefault();
>     
>     // 拾取通过事件，不直接调用 Inventory
>     public void AttemptLoot(ILootable loot)
>     {
>         foreach (var item in loot.GetDrops())
>             EventBus.Publish(new ItemPickedUp(null, item)); // null 表示待分配
>     }
> }
> ```
> 
> **Player Assembly（引用 Core）：**
> 
> ```csharp
> public class Player : ITarget, ILootable, IInventory
> {
>     public void Die()
>     {
>         EventBus.Publish(new EntityDied(this, this));
>     }
>     
>     public bool AddItem(Item item) { /* ... */ return true; }
>     public IEnumerable<Item> GetDrops() => inventory.Where(i => !i.IsEquipped);
> }
> ```
> 
> **Inventory Assembly（引用 Core）：**
> 
> ```csharp
> public class InventorySystem
> {
>     public InventorySystem()
>     {
>         EventBus.Subscribe<ItemPickedUp>(OnItemPickedUp);
>     }
>     
>     void OnItemPickedUp(ItemPickedUp e)
>     {
>         e.Inventory?.AddItem(e.Item);
>         // 触发装备效果
>         if (e.Item.IsEquipment)
>             EventBus.Publish(new EquipmentActivated(e.Inventory, e.Item));
>     }
> }
> ```
> 
> **模块依赖图：**
> 
> ```mermaid
> graph TD
>     Core["Core (Interfaces + Events)"]
>     AI["AI (AIController)"]
>     Player["Player (Player)"]
>     Inventory["Inventory (InventorySystem)"]
>     
>     AI -->|"ITarget, ILootable"| Core
>     Player -->|"ITarget, ILootable, IInventory"| Core
>     Inventory -->|"IInventory"| Core
>     
>     AI -.->|"EventBus.Publish<br/>EntityDied, ItemPickedUp"| Core
>     Player -.->|"EventBus.Publish<br/>EntityDied"| Core
>     Inventory -.->|"EventBus.Subscribe<br/>ItemPickedUp, EquipmentActivated"| Core
>     
>     style Core fill:#f9f,stroke:#333
> ```
> 
> 实线 = 接口依赖（编译时）；虚线 = 事件依赖（运行时松散耦合）。没有任何 Assembly 直接引用其他业务 Assembly。

> [!note] 答案使用方式
> 如果你的实现通过了测试或达到了题目要求，就是正确的。参考答案展示的是**一种可行路径**，而非唯一标准。练习 1 的优先级策略、练习 2 的绑定框架选择、练习 3 的接口粒度，均可根据项目实际调整。核心检验标准：是否消除了直接引用、是否用 Tag/事件/接口建立了清晰边界。
>
> ---

## 4. 扩展阅读

- [Unity Manual — ScriptableObject](https://docs.unity3d.com/6000.0/Documentation/Manual/class-ScriptableObject.html) — Unity 官方数据驱动资产系统
- [Unity Manual — Data Binding (UI Toolkit)](https://docs.unity3d.com/6000.4/Documentation/Manual/best-practice-guides/ui-toolkit-for-advanced-unity-developers/data-binding.html) — UI Toolkit 数据绑定完整指南
- [Unreal Docs — Using Gameplay Tags](https://dev.epicgames.com/documentation/unreal-engine/using-gameplay-tags-in-unreal-engine) — GameplayTags 设计哲学与 API 参考
- [Nystrom — Component · Game Programming Patterns](https://gameprogrammingpatterns.com/component.html) — 组件模式与解耦的经典论述

---

## 常见陷阱

- **View 直接修改 Model 导致双向依赖**：`HealthBarView` 中发现点击治疗按钮就 `model.HP += 10`。正确做法：View 只发事件/命令，由 Presenter 或 Controller 决定如何修改 Model；Model 变更后通过绑定机制回流到 View。

- **GameplayTag 层级滥用导致大量隐式规则**：`Status.Burning.Immune` 和 `Status.Burning.Resistant` 层级过深，新成员难以推断 `MatchesTag("Status.Burning")` 是否包含子标签。正确做法：建立 Tag 词典文档，对关键 `MatchesTag` 调用写单元测试，限制层级深度（建议最多 4 层）。

- **数据绑定未处理对象销毁/取消订阅，造成泄漏或空引用**：Unity 中 `HealthBarView` 订阅了 `HealthModel.OnChanged`，但场景切换时 View 被销毁、Model 仍在全局存活，导致回调调用已销毁的 MonoBehaviour。正确做法：在 `OnDestroy`/`Dispose` 中显式 `Unbind()`，或使用弱事件模式（`WeakEventManager`）；Unity 中也可用 `OnDisable` 自动清理绑定。