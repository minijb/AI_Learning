---
title: "Blackboard 系统与数据流"
updated: 2026-06-05
---

# Blackboard 系统与数据流

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: [[08-bt-unity-csharp]], [[09-bt-unreal-cpp]], [[10-bt-lua]]

---

## 1. 概念讲解

### 什么是 Blackboard？

行为树的节点是纯粹的决策逻辑——它们决定"做什么"和"什么顺序做"，但它们不应该知道自己操作的具体实体是谁。"当前目标是谁？"、"上次看到敌人的位置在哪？"、"弹药还剩多少？"——这些数据不属于任何单个节点，也不属于行为树的静态结构。

Blackboard 就是解决这个问题的：**它是一个共享知识库**。行为树的节点通过 key（字符串或 FName）读写 Blackboard 中的数据，而不需要互相知道对方的存在。

用三个关键概念来定义 Blackboard：

- **Key**：数据的标识符，是一个字符串（C#/Lua）或 `FName`（UE）。例如 `"TargetActor"`、`"AlertLevel"`、`"LastKnownPosition"`。
- **Value**：key 对应的运行时值。类型可以是基本类型（int、float、bool、string）、对象引用（GameObject*、AActor*）、或复合类型（Vector3、Transform）。
- **Namespace**：key 的前缀机制。例如 `"Enemy.TargetActor"` vs `"Ally.TargetActor"` ——相同的 key 本体在不同的 namespace 下指代不同的数据。这是多棵行为树共享数据、以及 squad AI 的基础。

最简单的 Blackboard 就是一个 `Dictionary<string, object>`：

```csharp
var bb = new Dictionary<string, object>();
bb["TargetActor"] = enemy;       // Write
var target = bb["TargetActor"];  // Read (需要 cast)
```

这种实现可以工作，但一个真正的 Blackboard 系统必须解决六个问题：类型安全、未注册 key 的防御、变更通知、跨层作用域、内存效率和跨语言桥接。

### 为什么不用成员变量？

"为什么要在 Blackboard 里存 `TargetActor`，而不是直接在 BTNode 上声明一个 `public GameObject Target`？"——这是在面试中会被追问的深层设计问题。

**第一，解耦。** 行为树的节点不应该知道数据的生产者是谁。`TargetActor` 可能来自 Perception 系统（通过 `OnTargetPercepted` 回调写入 Blackboard），也可能来自于另一个行为树（squad leader 将 attack target 广播给 squad members）。如果 `TargetActor` 是节点上的成员变量，你需要显式地管理谁在什么时候更新它——这引入了跨系统的耦合，而 Blackboard 将耦合从"节点→节点"转换为"节点→Blackboard→节点"。

**第二，设计师友好。** 当策划在行为树编辑器中拖拽一个 `CheckTargetDistance` Decorator 时，他可以下拉选择 Blackboard 中的 `TargetActor` key，而不需要理解 C++ 成员变量、序列化、或代码引用。UE 的 `FBlackboardKeySelector` 就是为了这个目的——它在编辑器中呈现为下拉菜单，在运行时转换为整数索引。

**第三，AI 感知集成。** 现代游戏 AI 通常有一个独立的感知系统（Vision、Hearing、Damage events）。感知系统发现了一个敌人时，它会将结果写入 Blackboard：`bb.Set("TargetActor", sensedEnemy)`。Decorator 通过 Observer 模式监听这个 key 的变更，立即触发行为树的条件重评估。如果使用成员变量，你需要手动轮询或自定义事件系统。

**第四，squad AI 的共享数据。** squad leader 发现敌人后，需要通知所有 squad members。如果每个 member 都有自己独立的成员变量，你需要手动遍历 squad 并逐个设置。Blackboard 方案下，squad leader 将自己的 Blackboard 中的 `"SquadTarget"` key 共享给 members 的 Blackboard 作为只读引用——一次写入，全员可见。

### Blackboard 架构：层次化作用域

工业级 Blackboard 系统通常有层次化的作用域（scope），类似于编程语言的变量作用域：

```
Global Blackboard (所有 AI 共享)
  ├─ 关卡级别的数据：当前警报等级、天气状态
  │
  ├─ Agent Blackboard (单个 AI 独占)
  │   ├─ 实体特定的数据：自身血量、弹药、当前位置
  │   │
  │   └─ Tree Blackboard (单棵行为树的作用域)
  │       ├─ 树特定的临时数据：当前巡逻路径索引、计时器
  │       └─ 随行为树切换而清理
```

**Global Blackboard** 适用于所有 AI 都需要感知的全局状态：警报等级、昼夜切换、Boss 阶段。通常是单例或 `WorldSubsystem`（UE）实现。

**Agent Blackboard** 是每个 AI agent 私有的实例。UE 的 `UBlackboardComponent` 就处在这一层。当 AI 死亡或销毁时，整个 Agent Blackboard 被回收。

**Tree Blackboard** 是一棵特定行为树的临时数据。当行为树切换时（例如从 Patrol BT 切换到 Combat BT），上层作用域的 key 保留，但 Tree 作用域的 key 被清理。这一层通常通过 key prefix 实现（例如 `"Tree.Combat.Timer"`）。

三种作用域的实现策略：

| 策略 | 实现方式 | 优点 | 缺点 |
|:-----|:---------|:-----|:-----|
| Key prefix | `"Global.AlarmLevel"`, `"Agent.Health"` | 简单，无额外数据结构 | key 名字长，查找需要字符串操作 |
| 多实例堆叠 | 多个 Dictionary 按 scope 链式查找 | 自动隔离，清理方便 | 查找需要遍历 scope 链 |
| UE 的资产分离 | `UBlackboardData` 资产定义 key，`UBlackboardComponent` 存值 | 类型安全，编辑器友好 | 学习曲线陡峭，仅 UE 可用 |

### Observer 模式：变更驱动的行为中断

这是 Blackboard 系统中最强大的机制，也是面试中最常被问到的深度问题。

**问题场景**：一个 AI 正在 `Patrol` 行为中（`MoveTo` Task 处于 Running 状态）。突然，它受到了伤害——`Health` 从 100 降到了 50。行为树上有一个高优先级的 Selector 分支："如果 `Health < 30`，进入 `Flee`"。但当前 `Patrol` 正在 Running，行为树不会重新评估已通过的 Selector。

**轮询方案**：在 `Patrol` 的每次 `Tick` 中都检查 `Health`。问题：检查频率受限（每帧一次），且每个 Running Task 都必须记得做这个检查。这是"遗忘性 bug"的热土。

**Observer 方案**：Decorator 注册为特定 Blackboard key 的观察者。当 `Health` 的值发生变化时：

```
Blackboard.SetValue("Health", 50)
  → 遍历 "Health" key 的所有观察者
    → Decorator_WatchHealth::OnBlackboardKeyChanged()
      → 重新评估 condition: health < 30? → false → 无需 abort
    → ... (其他观察者)

Blackboard.SetValue("Health", 25)
  → Decorator_WatchHealth::OnBlackboardKeyChanged()
    → 重新评估 condition: health < 30? → true
      → 触发 LowerPriority abort
        → 中断当前 Running 的 Patrol 分支
        → Selector 重新评估，进入 Flee 分支
```

UE 将这个过程封装为 `FlowAbortMode`：

- `None` — 不注册观察者，纯轮询。
- `Self` — 当条件变为 false 时，abort 自己所在的分支。
- `LowerPriority` — 当条件变为 true 时，abort 当前运行的更低优先级分支，抢断执行。
- `Both` — 同时启用 Self 和 LowerPriority。

**实现 Observer 的核心数据结构**：

```
Blackboard
  ├─ Dictionary<KeyName, Value> _data
  └─ Dictionary<KeyName, List<IObserver>> _observers
       ├─ "Health" → [DecoratorA, DecoratorB, ServiceC]
       └─ "TargetActor" → [DecoratorD]
```

每次 `SetValue` 调用会遍历该 key 的观察者列表并触发回调。关键优化：使用事件合并（在同一帧内对同一 key 的多次写入只触发一次回调），避免观察者链中的无限递归。

### UE Blackboard 系统深度剖析

UE 的 Blackboard 系统有四个核心类，理解它们之间的关系是正确使用的前提：

**UBlackboardData**（资产层）：在编辑器中创建的不可变数据资产，定义了 Blackboard 中有哪些 key、每个 key 是什么类型。它是 `UDataAsset` 的子类，可以像其他资产一样在 Content Browser 中管理。

```
UBlackboardData (资产，存储为 .uasset)
  ├─ Parent: UBlackboardData*  (支持继承——子 Blackboard 自动拥有父 Blackboard 的所有 key)
  └─ Keys: TArray<FBlackboardEntry>
       ├─ Entry[0]: KeyName="TargetActor",  KeyType=UBlackboardKeyType_Object
       ├─ Entry[1]: KeyName="TargetLocation", KeyType=UBlackboardKeyType_Vector
       └─ Entry[2]: KeyName="IsAlerted",    KeyType=UBlackboardKeyType_Bool
```

Blackboard 继承是 UE 独有的特性：你可以定义一个"基础敌人 Blackboard"包含通用 key（`TargetActor`、`MoveSpeed`），然后派生出"Boss Blackboard"额外添加 `PhaseIndex`、`EnrageTimer` 等 key。

**UBlackboardKeyType**（类型系统）：UE 的每种 Blackboard 类型都是一个 `UBlackboardKeyType` 的子类。内置类型包括：

| KeyType 类 | 对应 C++ 类型 | 编辑器 UI |
|:-----------|:-------------|:----------|
| `UBlackboardKeyType_Object` | `UObject*` | Actor/Component 拾取器 |
| `UBlackboardKeyType_Class` | `UClass*` | 类选择器 |
| `UBlackboardKeyType_Enum` | `uint8` | 枚举下拉菜单 |
| `UBlackboardKeyType_Int` | `int32` | 整数输入框 |
| `UBlackboardKeyType_Float` | `float` | 浮点数输入框 |
| `UBlackboardKeyType_Bool` | `bool` | 复选框 |
| `UBlackboardKeyType_Vector` | `FVector` | X/Y/Z 输入框 |
| `UBlackboardKeyType_Rotator` | `FRotator` | Pitch/Yaw/Roll |
| `UBlackboardKeyType_Name` | `FName` | Name 输入框 |
| `UBlackboardKeyType_String` | `FString` | 字符串输入框 |

你可以扩展 `UBlackboardKeyType` 定义自定义类型（如 `EThreatLevel` 枚举或 `FGameplayTag`），这在示例 B 中演示。

**UBlackboardComponent**（运行时实例）：每个 AI agent 的 `AAIController` 持有一个 `UBlackboardComponent` 实例。它在运行时存储每个 key 的当前值，并提供变更通知机制。

核心 API：

```cpp
// 获取指定 key 的当前值
UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
AActor* Target = Cast<AActor>(BB->GetValueAsObject("TargetActor"));
FVector Loc   = BB->GetValueAsVector("TargetLocation");
bool bAlerted = BB->GetValueAsBool("IsAlerted");

// 设置值（自动触发 Observer 通知）
BB->SetValueAsObject("TargetActor", NewTarget);
BB->SetValueAsBool("IsAlerted", true);

// 以 FBlackboardKeySelector 的方式访问（推荐——类型安全 + 编辑器下拉）
BB->SetValue<UBlackboardKeyType_Vector>(TargetLocationKey.GetSelectedKeyID(), NewLoc);
```

**FBlackboardKeySelector**（元数据包装器）：这是 UE 最精巧的设计之一。它不是直接存储 key 的字符串名称，而是在编辑器中呈现为下拉菜单（只显示兼容类型的 key），在运行时通过整数 ID 进行 O(1) 查找。它通过 `AddObjectFilter`、`AddVectorFilter` 等 API 限制可选 key 的类型——避免设计师误将 Bool key 选为 Vector key。

### 自定义 Blackboard 设计模式

不同引擎和需求场景下，Blackboard 有三种典型设计：

**模式 1：泛型字典式（最小实现）**

```csharp
public class Blackboard
{
    private Dictionary<string, object> _data = new();

    public T Get<T>(string key) => (T)_data[key];
    public void Set<T>(string key, T value) => _data[key] = value;
    public bool TryGet<T>(string key, out T value) { /* ... */ }
}
```

优点：零依赖，三分钟实现。缺点：无类型检查（运行时 `InvalidCastException`），无变更通知，无 key 注册验证。适合 jam 或原型。

**模式 2：类型安全模板式（中规模项目）**

```csharp
public class Blackboard
{
    private Dictionary<string, BlackboardEntry> _entries = new();

    public BlackboardKey<T> RegisterKey<T>(string name, T defaultValue = default)
    {
        var key = new BlackboardKey<T>(name);
        _entries[name] = new BlackboardEntry { Value = defaultValue, KeyType = typeof(T) };
        return key;
    }

    public T Get<T>(BlackboardKey<T> key) { /* 编译时类型安全 */ }
    public void Set<T>(BlackboardKey<T> key, T value) { /* 编译时类型安全 + 变更通知 */ }
}
```

优点：编译时类型安全（通过泛型 key 对象），支持 key 注册以验证存在性。缺点：比字典式多一层抽象。

**模式 3：ScriptableObject 式（Unity 大型项目）**

```csharp
[CreateAssetMenu]
public class BlackboardData : ScriptableObject
{
    public List<BlackboardVariable> Variables; // 设计时定义 key
}

public class BlackboardInstance
{
    private Dictionary<string, object> _runtimeData; // 运行时存值
    private BlackboardData _definition; // 引用设计时定义

    public void Initialize(BlackboardData definition) { /* 根据定义初始化 _runtimeData */ }
}
```

优点：策划在 Inspector 中定义 key（名称和类型），资产可复用，UI 友好。缺点：需要 Editor 工具链支持，`ScriptableObject` 序列化成本。

### 数据流模式：写一次 vs 读多次 vs 发布-订阅

Blackboard 中的数据流动有四种典型模式：

**Write-Once（感知写入）**：感知系统发现敌人后，一次性写入 Blackboard。之后不再更新——除非感知系统再次检测到变化。

```
PerceptionSystem.OnTargetSensed(enemy)
  → bb.Set("TargetActor", enemy)   // Write-Once
```

**Write-Conditionally（Decorator 写入）**：Decorator 在评估条件时可能写入 Blackboard。例如 `FindCoverPoint` Decorator 在条件满足时写入 `"CoverLocation"` 供下游 Action 使用。

```
Decorator_FindCover:
  if (hasCoverNearby):
    bb.Set("CoverLocation", bestCover)  // Write-Conditionally
    return true
```

**Read-Many（多 Action 读取）**：一个 key 被多个节点读取。`TargetActor` 可能被 `LookAt` Action、`MoveTo` Action、`CheckDistance` Decorator 同时读取。这是最常见的模式。

**Pub-Sub（Observer Abort）**：一个 Service 持续更新 key（如 `UpdateThreatLevel`），Decorator 作为订阅者监听该 key 变化，触发行为中断。

```
Service_UpdateThreatLevel (每 500ms):
  threat = CalculateThreat()
  bb.Set("ThreatLevel", threat)     // Publish

Decorator_ThreatAboveThreshold:
  observes "ThreatLevel"
  if threat > threshold: abort LowerPriority  // Subscribe + React
```

### 多 Agent 共享 Blackboard：Squad AI

squad AI 是 Blackboard 共享的最常见场景。一个 squad leader 发现敌人后，所有 squad members 需要知道攻击目标。有三种实现策略：

**策略 1：共享引用**。Squad leader 的 Blackboard 中对特定 key 的值以只读方式暴露给 members。

```csharp
// Squad leader
public class SquadLeader : MonoBehaviour
{
    public Blackboard LeaderBlackboard; // agent-local

    void Start()
    {
        foreach (var member in squadMembers)
        {
            member.AgentBlackboard.BindShared("SquadTarget",
                () => LeaderBlackboard.Get<GameObject>("TargetActor"));
        }
    }
}
```

**策略 2：独立写入器 + 消息广播**。Squad leader 通过消息系统广播目标变更，各 member 独立更新自己的 Blackboard。比共享引用更解耦，但延迟更高。

**策略 3：全局 Blackboard**。一个独立的全局 Blackboard（单例）存储 squad 共享数据。简单但有线程安全和生命周期管理的挑战。

**内存考量**：每增加一个 Blackboard key，就多一份 per-agent 内存开销。对于 200 个 AI agent，如果每个 Blackboard 有 30 个 key，总内存开销约 `200 × 30 × (sizeof(value) + key_string_overhead)`。key 应使用 interned string（C# 的 `string.Intern`、UE 的 `FName`）来避免重复字符串分配。不活跃的 key 可以延迟分配或使用默认值避免存储。

---

## 2. 代码示例

### 示例 A：完整 Blackboard 实现 (C# / Unity)

下面是一个生产级别的 Unity Blackboard，包含类型化 Get/Set、key 注册、变更事件和 namespace 支持。

```csharp
// ============================================================
// Blackboard.cs — Typed, observable, namespace-aware Blackboard for Unity BT
// ============================================================

using System;
using System.Collections.Generic;

namespace GameAI
{
    /// <summary>
    /// Type-safe handle for a blackboard key. Obtained via Blackboard.RegisterKey<T>().
    /// Using this instead of raw strings prevents key name typos and type mismatches.
    /// </summary>
    public sealed class BlackboardKey<T>
    {
        public string Name { get; }
        internal BlackboardKey(string name) => Name = name;
    }

    /// <summary>
    /// Delegate for blackboard value change notifications.
    /// </summary>
    public delegate void BlackboardValueChanged(string key, object oldValue, object newValue);

    /// <summary>
    /// Scoped, observable blackboard with typed key registration and namespace support.
    /// </summary>
    public class Blackboard
    {
        // Internal storage — one entry per registered key
        private sealed class Entry
        {
            public object Value;
            public Type ValueType;
            public bool IsRegistered;
        }

        private readonly Dictionary<string, Entry> _entries = new();
        private readonly string _scopePrefix;

        /// <summary>
        /// Invoked AFTER a value is set. Handlers receive the full key, old value, new value.
        /// </summary>
        public event BlackboardValueChanged OnValueChanged;

        // --- Construction ---

        /// <param name="scope">Optional namespace prefix (e.g. "Agent", "Global", "Tree.Combat")</param>
        public Blackboard(string scope = null)
        {
            _scopePrefix = string.IsNullOrEmpty(scope) ? "" : scope + ".";
        }

        /// <summary>
        /// Create a child blackboard whose keys inherit the parent's scope prefix.
        /// A missing key in the child will fall through to the parent.
        /// </summary>
        public Blackboard CreateChildScope(string childScope, Blackboard parentFallback = null)
        {
            var child = new Blackboard((_scopePrefix + childScope).TrimEnd('.'));
            if (parentFallback != null)
            {
                // Wire fallback: child delegates reads to parent for unregistered keys
                child._parentFallback = parentFallback;
            }
            return child;
        }

        private Blackboard _parentFallback;

        // --- Key Registration ---

        /// <summary>
        /// Register a typed key with an optional default value.
        /// Returns a typed handle for compile-time safety.
        /// </summary>
        public BlackboardKey<T> RegisterKey<T>(string name, T defaultValue = default)
        {
            string fullName = _scopePrefix + name;
            if (_entries.TryGetValue(fullName, out var existing))
            {
                if (existing.ValueType != typeof(T))
                    throw new InvalidOperationException(
                        $"Key '{fullName}' already registered as {existing.ValueType.Name}, " +
                        $"cannot re-register as {typeof(T).Name}");
                return new BlackboardKey<T>(fullName);
            }

            _entries[fullName] = new Entry
            {
                Value = defaultValue,
                ValueType = typeof(T),
                IsRegistered = true
            };
            return new BlackboardKey<T>(fullName);
        }

        // --- Typed Access ---

        public T Get<T>(BlackboardKey<T> key)
        {
            string fullName = key.Name;
            if (_entries.TryGetValue(fullName, out var entry))
                return (T)entry.Value;

            if (_parentFallback != null)
                return _parentFallback.Get(key);

            throw new KeyNotFoundException($"Blackboard key '{fullName}' not registered.");
        }

        public void Set<T>(BlackboardKey<T> key, T value)
        {
            string fullName = key.Name;
            if (!_entries.TryGetValue(fullName, out var entry))
            {
                if (_parentFallback != null)
                {
                    _parentFallback.Set(key, value);
                    return;
                }
                throw new KeyNotFoundException($"Blackboard key '{fullName}' not registered. " +
                    "Use RegisterKey<T>() first.");
            }

            object oldValue = entry.Value;
            if (EqualityComparer<T>.Default.Equals((T)oldValue, value))
                return; // No change — suppress notification

            entry.Value = value;
            OnValueChanged?.Invoke(fullName, oldValue, value);
        }

        public bool TryGet<T>(BlackboardKey<T> key, out T value)
        {
            string fullName = key.Name;
            if (_entries.TryGetValue(fullName, out var entry))
            {
                value = (T)entry.Value;
                return true;
            }
            if (_parentFallback != null)
                return _parentFallback.TryGet(key, out value);

            value = default;
            return false;
        }

        // --- String-based access (for debug / designer-driven systems) ---

        public T GetByString<T>(string keyName)
        {
            string fullName = _scopePrefix + keyName;
            if (_entries.TryGetValue(fullName, out var entry))
                return (T)entry.Value;
            if (_parentFallback != null)
                return _parentFallback.GetByString<T>(keyName);
            throw new KeyNotFoundException($"Blackboard key '{fullName}' not found.");
        }

        public void SetByString<T>(string keyName, T value)
        {
            string fullName = _scopePrefix + keyName;
            if (!_entries.TryGetValue(fullName, out var entry))
            {
                // Auto-register for string-based access (less safe, but designer-friendly)
                entry = new Entry { ValueType = typeof(T), IsRegistered = false };
                _entries[fullName] = entry;
            }

            object oldValue = entry.Value;
            if (EqualityComparer<T>.Default.Equals((T)(oldValue ?? default), value))
                return;
            entry.Value = value;
            OnValueChanged?.Invoke(fullName, oldValue, value);
        }

        // --- Key existence & cleanup ---

        public bool HasKey(string keyName)
        {
            return _entries.ContainsKey(_scopePrefix + keyName) ||
                   (_parentFallback?.HasKey(keyName) ?? false);
        }

        public void ClearScope()
        {
            _entries.Clear();
        }
    }
}
```

**使用示例**：

```csharp
// --- Setup: register keys (done once per agent, typically in Awake) ---
var bb = new Blackboard("Agent");
var key_Target   = bb.RegisterKey<GameObject>("TargetActor");
var key_Health   = bb.RegisterKey<float>("Health", 100f);
var key_AlertLvl = bb.RegisterKey<int>("AlertLevel", 0);
var key_Position = bb.RegisterKey<Vector3>("LastKnownPosition");

// --- Observer: abort running behavior when health drops ---
bb.OnValueChanged += (key, oldVal, newVal) =>
{
    if (key == "Agent.Health" && (float)newVal < 30f)
    {
        Debug.Log("Health critical! Aborting current branch.");
        // behaviorTree.RequestAbortLowerPriority();
    }
};

// --- BT node usage ---
// In a Condition node:
if (bb.Get(key_Health) > 50f) return BTNodeState.Success;

// In an Action node:
bb.Set(key_Target, sensedEnemy);
bb.Set(key_Position, sensedEnemy.transform.position);

// --- Scoped child blackboard (e.g., sub-tree for combat) ---
var combatBB = bb.CreateChildScope("Combat", parentFallback: bb);
var key_CombatTimer = combatBB.RegisterKey<float>("Timer", 0f);
// combatBB can read combatBB keys directly, falls back to bb for "Agent.*" keys
```

**Observer Abort 集成**：Observer 模式的关键不是"值变了就 abort"，而是"值变了 → 重新评估条件 → 条件不满足时才 abort"。下面的 `ObservingDecorator` 封装了这个逻辑：

```csharp
public abstract class ObservingDecorator : BTNode
{
    protected Blackboard Blackboard;
    private readonly string _watchedKey;

    protected ObservingDecorator(Blackboard bb, string watchedKey)
    {
        Blackboard = bb;
        _watchedKey = watchedKey;
        bb.OnValueChanged += OnBlackboardValueChanged;
    }

    private void OnBlackboardValueChanged(string key, object oldVal, object newVal)
    {
        if (key != _watchedKey) return;

        // Re-evaluate: if condition is no longer met, request abort
        if (!EvaluateCondition())
        {
            RequestAbort(); // implemented by concrete BT engine
        }
    }

    protected abstract bool EvaluateCondition();
    protected abstract void RequestAbort();
}
```

### 示例 B：UE C++ Blackboard 深度使用

下面的示例展示 UE 中 Blackboard 的三个核心使用场景：自定义 Key 类型、Service 更新、Decorator Observer abort。

**场景**：AI 需要根据感知数据计算一个"威胁等级"（`EThreatLevel`），该值由 Service 每 500ms 更新一次，Decorator 监听该值变化以触发行为切换。

**步骤 1：自定义 Blackboard Key 类型**

```cpp
// ThreatLevelBlackboardKeyType.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Blackboard/BlackboardKeyType.h"
#include "ThreatLevelBlackboardKeyType.generated.h"

UENUM()
enum class EThreatLevel : uint8
{
    None        UMETA(DisplayName = "None"),
    Low         UMETA(DisplayName = "Low"),
    Medium      UMETA(DisplayName = "Medium"),
    High        UMETA(DisplayName = "High"),
    Critical    UMETA(DisplayName = "Critical")
};

UCLASS(EditInlineNew, meta = (DisplayName = "Threat Level"))
class UBlackboardKeyType_ThreatLevel : public UBlackboardKeyType
{
    GENERATED_BODY()

public:
    UBlackboardKeyType_ThreatLevel()
    {
        // ValueSize must match the underlying type size
        ValueSize = sizeof(EThreatLevel);
    }

    // --- Required overrides ---

    virtual FString DescribeValue(const UBlackboardComponent& OwnerComp,
        const uint8* RawData) const override
    {
        const EThreatLevel ThreatLevel = GetValueFromMemory<EThreatLevel>(RawData);
        switch (ThreatLevel)
        {
            case EThreatLevel::None:     return TEXT("None");
            case EThreatLevel::Low:      return TEXT("Low");
            case EThreatLevel::Medium:   return TEXT("Medium");
            case EThreatLevel::High:     return TEXT("High");
            case EThreatLevel::Critical: return TEXT("Critical");
            default: return TEXT("Unknown");
        }
    }

    virtual bool CompareValues(const UBlackboardComponent& OwnerComp,
        const uint8* MemoryBlock, const UBlackboardKeyType* OtherKeyOb,
        const uint8* OtherMemoryBlock) const override
    {
        const EThreatLevel MyValue = GetValueFromMemory<EThreatLevel>(MemoryBlock);
        const EThreatLevel OtherValue = GetValueFromMemory<EThreatLevel>(OtherMemoryBlock);
        return MyValue == OtherValue;
    }

    virtual void Clear(UBlackboardComponent& OwnerComp, uint8* RawData) override
    {
        SetValueInMemory<EThreatLevel>(RawData, EThreatLevel::None);
    }

    virtual bool IsEmpty(const UBlackboardComponent& OwnerComp,
        const uint8* RawData) const override
    {
        return GetValueFromMemory<EThreatLevel>(RawData) == EThreatLevel::None;
    }

    virtual bool WrappedIsEmpty(const UBlackboardComponent& OwnerComp,
        const uint8* RawData) const override
    {
        return IsEmpty(OwnerComp, RawData);
    }

    virtual FString DescribeSelf() const override
    {
        return TEXT("Threat Level (Enum)");
    }

    virtual UBlackboardKeyType* UpdateDeprecatedKey() override
    {
        return nullptr;
    }

    // --- Test support ---

    virtual bool TestBasicOperation(const UBlackboardComponent& OwnerComp,
        const uint8* MemoryBlock, EBasicKeyOperation::Type Op) const override
    {
        const EThreatLevel Value = GetValueFromMemory<EThreatLevel>(MemoryBlock);
        switch (Op)
        {
            case EBasicKeyOperation::Set:   return true;
            case EBasicKeyOperation::NotSet: return Value == EThreatLevel::None;
            default: return false;
        }
    }
};
```

**步骤 2：Service 每 Tick 更新 ThreatLevel**

```cpp
// BTService_UpdateThreatLevel.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Services/BTService_BlackboardBase.h"
#include "BTService_UpdateThreatLevel.generated.h"

UCLASS()
class UBTService_UpdateThreatLevel : public UBTService_BlackboardBase
{
    GENERATED_BODY()

public:
    UBTService_UpdateThreatLevel();

    /** Distance below which threat is considered Critical. */
    UPROPERTY(EditAnywhere, Category = "Threat")
    float CriticalDistance = 300.0f;

    /** Distance below which threat is High. */
    UPROPERTY(EditAnywhere, Category = "Threat")
    float HighDistance = 800.0f;

    /** Distance below which threat is Medium. */
    UPROPERTY(EditAnywhere, Category = "Threat")
    float MediumDistance = 2000.0f;

protected:
    virtual void TickNode(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;
};
```

```cpp
// BTService_UpdateThreatLevel.cpp
#include "BTService_UpdateThreatLevel.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"
#include "Perception/AIPerceptionComponent.h"
#include "Perception/AISense_Sight.h"

UBTService_UpdateThreatLevel::UBTService_UpdateThreatLevel()
{
    NodeName = TEXT("Update Threat Level");

    // This service writes to a Threat Level key — filter accordingly
    BlackboardKey.AddClassFilter<UBlackboardKeyType_ThreatLevel>(this,
        GET_MEMBER_NAME_CHECKED(UBTService_UpdateThreatLevel, BlackboardKey));

    // Run every 500ms — threat assessment is not per-frame critical
    Interval = 0.5f;
    RandomDeviation = 0.1f; // ±100ms jitter to avoid synchronized spikes
}

void UBTService_UpdateThreatLevel::TickNode(UBehaviorTreeComponent& OwnerComp,
    uint8* NodeMemory, float DeltaSeconds)
{
    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return;

    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return;

    APawn* ControlledPawn = AIController->GetPawn();
    if (!ControlledPawn) return;

    // --- Threat evaluation logic ---
    // Query perception system for the nearest sensed hostile actor
    UAIPerceptionComponent* Perception =
        AIController->FindComponentByClass<UAIPerceptionComponent>();
    if (!Perception) return;

    EThreatLevel NewThreat = EThreatLevel::None;

    TArray<AActor*> HostileActors;
    Perception->GetCurrentlyPerceivedActors(UAISense_Sight::StaticClass(), HostileActors);

    if (HostileActors.Num() > 0)
    {
        // Find nearest hostile
        float ClosestDistSq = FLT_MAX;
        const FVector MyLocation = ControlledPawn->GetActorLocation();

        for (AActor* Hostile : HostileActors)
        {
            if (!Hostile) continue;
            float DistSq = FVector::DistSquared(MyLocation, Hostile->GetActorLocation());
            if (DistSq < ClosestDistSq) ClosestDistSq = DistSq;
        }

        float ClosestDist = FMath::Sqrt(ClosestDistSq);

        // Map distance to threat level
        if (ClosestDist <= CriticalDistance)
            NewThreat = EThreatLevel::Critical;
        else if (ClosestDist <= HighDistance)
            NewThreat = EThreatLevel::High;
        else if (ClosestDist <= MediumDistance)
            NewThreat = EThreatLevel::Medium;
        else
            NewThreat = EThreatLevel::Low;
    }

    // Write to Blackboard — this triggers Observer notification if the value changed
    const FBlackboard::FKey KeyID = BlackboardKey.GetSelectedKeyID();
    BB->SetValue<UBlackboardKeyType_ThreatLevel>(KeyID,
        reinterpret_cast<uint8*>(&NewThreat));
}
```

**步骤 3：Decorator 监听 ThreatLevel 并触发 Observer Abort**

```cpp
// BTDecorator_ThreatAbove.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Decorators/BTDecorator_BlackboardBase.h"
#include "BTDecorator_ThreatAbove.generated.h"

UCLASS()
class UBTDecorator_ThreatAbove : public UBTDecorator_BlackboardBase
{
    GENERATED_BODY()

public:
    UBTDecorator_ThreatAbove();

    /** The threshold threat level. Condition passes when current >= this. */
    UPROPERTY(EditAnywhere, Category = "Condition")
    EThreatLevel ThreatThreshold = EThreatLevel::High;

protected:
    virtual bool CalculateRawConditionValue(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) const override;

    virtual EBlackboardNotificationResult OnBlackboardKeyValueChange(
        const UBlackboardComponent& Blackboard, FBlackboard::FKey ChangedKeyID) override;

    virtual FString GetStaticDescription() const override;
};
```

```cpp
// BTDecorator_ThreatAbove.cpp
#include "BTDecorator_ThreatAbove.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"

UBTDecorator_ThreatAbove::UBTDecorator_ThreatAbove()
{
    NodeName = TEXT("Threat Above Threshold");

    // Enable Observer Abort: when threat level changes, re-evaluate
    bNotifyBecomeRelevant = true;
    bNotifyCeaseRelevant = true;

    // Self: if condition becomes false, abort the branch containing this decorator
    // LowerPriority: if condition becomes true, abort the currently running lower-priority branch
    FlowAbortMode = EBTFlowAbortMode::Both;

    // Restrict key selection to Threat Level type only
    BlackboardKey.AddClassFilter<UBlackboardKeyType_ThreatLevel>(this,
        GET_MEMBER_NAME_CHECKED(UBTDecorator_ThreatAbove, BlackboardKey));
}

bool UBTDecorator_ThreatAbove::CalculateRawConditionValue(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
{
    const UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return false;

    const FBlackboard::FKey KeyID = BlackboardKey.GetSelectedKeyID();
    const uint8* RawData = BB->GetValueRaw<UBlackboardKeyType_ThreatLevel>(KeyID);
    if (!RawData) return false;

    const EThreatLevel CurrentThreat =
        *reinterpret_cast<const EThreatLevel*>(RawData);

    return static_cast<uint8>(CurrentThreat) >= static_cast<uint8>(ThreatThreshold);
}

EBlackboardNotificationResult UBTDecorator_ThreatAbove::OnBlackboardKeyValueChange(
    const UBlackboardComponent& Blackboard, FBlackboard::FKey ChangedKeyID)
{
    // Only react if the changed key is the one we're observing
    if (ChangedKeyID != BlackboardKey.GetSelectedKeyID())
        return EBlackboardNotificationResult::RemoveObserver;

    // The BT framework will automatically call CalculateRawConditionValue
    // and trigger the appropriate FlowAbortMode based on the result
    return EBlackboardNotificationResult::ContinueObserving;
}

FString UBTDecorator_ThreatAbove::GetStaticDescription() const
{
    return FString::Printf(TEXT("Threat Level >= %s"),
        *StaticEnum<EThreatLevel>()->GetNameStringByValue(
            static_cast<int64>(ThreatThreshold)));
}
```

**步骤 4：Task 读取 Blackboard 值**

```cpp
// BTTask_ReactToThreat.cpp (excerpt)
EBTNodeResult::Type UBTTask_ReactToThreat::ExecuteTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return EBTNodeResult::Failed;

    // Read the current threat level from the blackboard
    const uint8* RawData = BB->GetValueRaw<UBlackboardKeyType_ThreatLevel>(
        ThreatLevelKey.GetSelectedKeyID());
    const EThreatLevel Threat =
        *reinterpret_cast<const EThreatLevel*>(RawData);

    // Execute behavior based on threat level
    switch (Threat)
    {
        case EThreatLevel::Critical: FleeImmediately(); break;
        case EThreatLevel::High:     TakeCover(); break;
        case EThreatLevel::Medium:   HoldPosition(); break;
        default:                     Patrol(); break;
    }

    return EBTNodeResult::Succeeded;
}
```

**数据流完整链路**：

```
UAIPerceptionComponent (每帧检测敌人)
  → UBTService_UpdateThreatLevel::TickNode() (每 500ms 执行)
    → 计算距离 → 映射到 EThreatLevel
    → BB->SetValue<UBlackboardKeyType_ThreatLevel>(KeyID, &Threat)
      → UBlackboardComponent 通知所有观察者
        → UBTDecorator_ThreatAbove::OnBlackboardKeyValueChange()
          → 框架调用 CalculateRawConditionValue()
            → Threat >= High? true → LowerPriority abort
              → 中断当前 Patrol / Idle 分支
              → 行为树重新 tick，进入 Combat 分支
```

### 示例 C：Lua Blackboard

Lua 的 table 本身就是天然的 key-value 存储。一个完整的 Lua Blackboard 需要额外实现：key 注册验证、变更回调和默认值回退。

```lua
-- ============================================================
-- Blackboard.lua — Observable Blackboard with metatable defaults
-- ============================================================

local Blackboard = {}
Blackboard.__index = Blackboard

--- Create a new Blackboard instance.
--- @param defaults table|nil  Keys with default values (used as fallback via __index)
--- @return table  Blackboard instance
function Blackboard.new(defaults)
    local self = setmetatable({}, Blackboard)
    self._observers = {}  -- { [key] = { callback1, callback2, ... } }
    self._defaults = defaults or {}
    return self
end

--- Register an observer for a specific key.
--- @param key string
--- @param callback function(key, old_value, new_value)
--- @return function  Call this returned function to unregister.
function Blackboard:observe(key, callback)
    if not self._observers[key] then
        self._observers[key] = {}
    end
    table.insert(self._observers[key], callback)

    -- Return an unregister function
    return function()
        local list = self._observers[key]
        if list then
            for i = #list, 1, -1 do
                if list[i] == callback then
                    table.remove(list, i)
                    break
                end
            end
        end
    end
end

--- Internal: notify all observers of a key change.
function Blackboard:_notify(key, old_value, new_value)
    local list = self._observers[key]
    if list then
        for _, cb in ipairs(list) do
            cb(key, old_value, new_value)
        end
    end
end

--- Set a value. Triggers observer callbacks if value actually changes.
function Blackboard:set(key, value)
    local old_value = rawget(self, key)
    if old_value == value then return end  -- suppress redundant notification
    rawset(self, key, value)
    self:_notify(key, old_value, value)
end

--- Get a value. Falls back to _defaults if key is not set on this instance.
function Blackboard:get(key)
    local value = rawget(self, key)
    if value ~= nil then
        return value
    end
    return self._defaults[key]
end

--- Check if a key exists (on this instance, not counting defaults).
function Blackboard:has(key)
    return rawget(self, key) ~= nil
end

--- Clear all keys set on this instance. Defaults remain intact.
function Blackboard:clear()
    for key, _ in pairs(self) do
        if key ~= "_observers" and key ~= "_defaults" then
            rawset(self, key, nil)
        end
    end
end

--- Create a child Blackboard that falls back to this parent.
--- @param child_defaults table|nil
--- @return table  Child blackboard
function Blackboard:create_child(child_defaults)
    local child = Blackboard.new(child_defaults or {})

    -- Override child's get to fall back to parent
    local parent_get = child.get
    child.get = function(inst, key)
        local val = rawget(inst, key)
        if val ~= nil then return val end
        if inst._defaults[key] ~= nil then return inst._defaults[key] end
        return self:get(key)  -- fall back to parent
    end

    return child
end

-- ============================================================
-- Shared Blackboard (squad AI)
-- ============================================================

local SharedBlackboard = {}
SharedBlackboard.__index = SharedBlackboard

--- A SharedBlackboard allows multiple agents to read the same key
--- while only the owner can write.
function SharedBlackboard.new(owner_bb, shared_keys)
    local self = setmetatable({}, SharedBlackboard)
    self._owner_bb = owner_bb
    self._shared_keys = shared_keys  -- { "SquadTarget", "FormationType", ... }
    return self
end

--- Read a shared key from the owner.
function SharedBlackboard:get(key)
    for _, sk in ipairs(self._shared_keys) do
        if sk == key then
            return self._owner_bb:get(key)
        end
    end
    error("Key '" .. key .. "' is not shared")
end

--- Subscribe to changes on a shared key.
function SharedBlackboard:observe(key, callback)
    return self._owner_bb:observe(key, callback)
end

-- ============================================================
-- Usage example
-- ============================================================

-- Squad leader blackboard
local leader_bb = Blackboard.new({ Health = 100, AlertLevel = 0 })
leader_bb:set("SquadTarget", nil)
leader_bb:set("Formation", "line")

-- Squad member blackboard (with per-member defaults)
local member_bb = Blackboard.new({ Health = 80, Ammo = 30 })

-- Share leader's squad-level keys with members
local shared = SharedBlackboard.new(leader_bb, { "SquadTarget", "Formation" })

-- BT node: Condition — "has squad target?"
local function condition_has_target(bb, shared_bb)
    local target = shared_bb:get("SquadTarget")
    return target ~= nil
end

-- BT node: Action — move to squad formation position
local function action_formation_move(agent, bb, shared_bb)
    local formation = shared_bb:get("Formation")
    local position = calculate_formation_position(agent, formation)
    move_toward(agent, position)
    if arrived(agent, position) then
        return "success"
    end
    return "running"
end

-- Observer: abort patrol when squad target appears
local unreg = shared_bb:observe("SquadTarget", function(key, old, new)
    if new ~= nil then
        print("Squad target acquired! Aborting patrol to engage.")
        -- In real BT: request AbortLowerPriority on the Patrol branch
    end
end)

-- Leader discovers enemy → writes to blackboard → all members see it
leader_bb:set("SquadTarget", { x = 100, y = 200, id = "EnemyBoss" })
-- Output: "Squad target acquired! Aborting patrol to engage."

-- Cleanup: unsubscribe when behavior tree is destroyed
unreg()
```

---

## 3. 练习

### 练习 1：为 Unity Blackboard 添加作用域支持

**目标**：扩展示例 A 的 `Blackboard` 类，实现完整的三层作用域（Global → Agent → Tree）和共享 squad Blackboard。

**要求**：
1. 实现 `BlackboardScope` 枚举（`Global`、`Agent`、`Tree`）和对应的 `Blackboard` 构造函数。
2. 实现链式查找：`Tree` 作用域找不到 key 时，自动 fallback 到 `Agent` 作用域，再到 `Global` 作用域。
3. 实现 `SharedBlackboard` 类：一个 squad leader 的 `Blackboard` 可以将指定 key 集共享给 squad members，members 对这些 key 只读。
4. 编写单元测试（至少 5 个 test case）：作用域隔离、fallback 查找、作用域清理不污染父作用域、共享 key 变更通知 member、注册冲突检测。

**关键考量**：
- `Set` 操作应该写入当前作用域还是 fallback 链中最接近的已注册 key？设计并解释你的选择。
- 共享 Blackboard 的变更通知是否会向所有 member 广播？如果有 20 个 member，性能如何？

---

### 练习 2：UE 自定义 Blackboard Key 类型

**目标**：在 UE 5.3+ 中创建一个自定义 `UBlackboardKeyType` 用于"装备状态"（Equipment State），并编写配套的 Service 和 Task。

**要求**：
1. 定义 `EEquipmentState` 枚举：`Unequipped`、`Melee`、`Ranged`、`Throwable`。
2. 实现 `UBlackboardKeyType_EquipmentState`，覆写所有必要的虚函数（`DescribeValue`、`CompareValues`、`Clear`、`IsEmpty`、`TestBasicOperation`）。
3. 实现 `UBTService_DetectEquipment`：每 200ms 检测 AI 当前装备的武器类型，将结果写入 Blackboard。
4. 实现 `UBTDecorator_HasRangedWeapon`：监听 EquipmentState key，当装备远程武器时，通过 `LowerPriority` abort 中断当前 Melee 行为。
5. 实现 `UBTTask_SwitchToBestWeapon`：读取 EquipmentState key，在武器不合适时切换到最优武器（ranged > melee > throwable > unequipped 的优先级），切换完成后返回 `Succeeded`。

**验证方法**：在 BT Editor 中创建一棵包含这些节点的测试行为树，用 `GameplayDebugger` 或 `Visual Logger` 观察 Blackboard 值的变化和 abort 触发时机。

---

### 练习 3（选做）：实现基于 Blackboard 变更的条件性 Abort

**目标**：在你选择的引擎（Unity/UE/Lua）中实现一个完整的 Observer Abort 系统。

**要求**：
1. 在 Blackboard 中实现 `Observe(key, callback)` 注册机制和 `Unobserve(key, callback)` 反注册。
2. 实现 `ObservingDecorator` 节点：在激活时注册 Observer，在 deactivate 时反注册。
3. 当观察的 key 值变化时，重新评估条件——如果条件从 true 变为 false，abort 当前分支（Self abort）；如果条件从 false 变为 true，检查是否有更低优先级的分支需要 abort（LowerPriority abort）。
4. **关键**：实现 abort 安全机制——防止 `SetValue → Notify → Abort → 重新 Tick → 再次 SetValue → ...` 的无限循环。至少实现两种防护：帧内去重（同一帧同一 key 多次写入只触发一次 abort）和递归深度限制（abort 嵌套深度不超过 3）。

**测试场景**：
- Agent A 正在 Patrol（优先级 2，Running）。ThreatLevel 从 Low 变为 High → 触发 LowerPriority abort → 切换到 Flee（优先级 1）。
- Agent B 正在 Flee（优先级 1，Running）。ThreatLevel 从 High 变为 Low → 触发 Self abort → Flee 分支中断 → 重新评估 → 回到 Patrol（优先级 2）。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **三层作用域 + Shared Blackboard 实现**。基于示例 A 的 `Blackboard` 类扩展。
>
> **1. 作用域枚举和链式构造**：
> ```csharp
> public enum BlackboardScope { Global, Agent, Tree }
>
> public class Blackboard
> {
>     private readonly BlackboardScope _scope;
>     private Blackboard _parent; // fallback 链：Tree → Agent → Global → null
>     private readonly Dictionary<string, Entry> _entries = new();
>     // ... Entry 及 RegisterKey/Get/Set 不变
>
>     public Blackboard(BlackboardScope scope, Blackboard parent = null)
>     {
>         _scope = scope;
>         _parent = parent;
>     }
>
>     public T Get<T>(BlackboardKey<T> key)
>     {
>         if (_entries.TryGetValue(key.Name, out var entry))
>             return (T)entry.Value;
>         if (_parent != null)
>             return _parent.Get(key); // 链式 fallback
>         throw new KeyNotFoundException(key.Name);
>     }
>
>     public void Set<T>(BlackboardKey<T> key, T value)
>     {
>         // 设计选择：写入当前作用域（而非 fallback 链中最近的已注册 key）
>         // 原因：如果 Set 写回到 Agent 作用域，Tree 作用域无法覆盖 Agent 的值，
>         // 这违反了作用域隔离的原则。Tree 作用域的 Set 应该只在 Tree 作用域生效。
>         if (!_entries.TryGetValue(key.Name, out var entry))
>         {
>             // 当前作用域未注册此 key → 注册一个新 entry（隔离写）
>             entry = new Entry { ValueType = typeof(T), IsRegistered = true };
>             _entries[key.Name] = entry;
>         }
>         object old = entry.Value;
>         if (EqualityComparer<T>.Default.Equals((T)old, value)) return;
>         entry.Value = value;
>         OnValueChanged?.Invoke(key.Name, old, value);
>     }
> }
> ```
> **设计理由**：`Set` 写入当前作用域确保子作用域的修改不污染父作用域。当行为树切换时，只需清除 Tree 作用域的 entries（GC 友好），Agent/Global 作用域保持不变。
>
> **2. SharedBlackboard 类**：
> ```csharp
> public class SharedBlackboard
> {
>     private readonly Blackboard _leaderBB;
>     private readonly HashSet<string> _sharedKeys;
>     private readonly List<Blackboard> _memberReadViews = new();
>
>     public SharedBlackboard(Blackboard leaderBB, params string[] sharedKeys)
>     {
>         _leaderBB = leaderBB;
>         _sharedKeys = new HashSet<string>(sharedKeys);
>     }
>
>     public void AddMember(Blackboard memberBB)
>     {
>         // 为 member 创建一个只读视图：订阅 leader 的 OnValueChanged，
>         // 当共享 key 变更时，同步到 member 的 Agent 作用域
>         _leaderBB.OnValueChanged += (key, oldVal, newVal) => {
>             if (_sharedKeys.Contains(key))
>                 memberBB.SetDirect(key, newVal); // 绕过 Set 的变更通知（避免递归）
>         };
>         _memberReadViews.Add(memberBB);
>     }
> }
> ```
> **性能考量**：20 个 member 时，一次 `Set` 会触发 20 次回调。如果频率高（每帧多次），优化为**帧末批量通知**——用 `List<(string key, object value)> _pendingUpdates` 收集变更，在 `LateUpdate` 中统一同步所有 member。
>
> **3. 单元测试（≥5 个）**：
> ```csharp
> [Test] public void ScopeIsolation_TreeWrite_DoesNotPolluteAgent()
> {   // Tree 作用域写入 key，Agent 作用域的同名 key 值不变
>     var global = new Blackboard(BlackboardScope.Global);
>     var agent = new Blackboard(BlackboardScope.Agent, global);
>     var tree = new Blackboard(BlackboardScope.Tree, agent);
>     var k = agent.RegisterKey("Health", 100f);
>     tree.Set(k, 50f); // 写入 Tree 作用域
>     Assert.AreEqual(50f, tree.Get(k));  // Tree 看到自己的值
>     Assert.AreEqual(100f, agent.Get(k)); // Agent 值未变
> }
> [Test] public void FallbackLookup_TreeReadsAgentWhenNotSet()
> {   // Tree 未注册 key → fallback 到 Agent
>     var agent = new Blackboard(BlackboardScope.Agent);
>     var tree = new Blackboard(BlackboardScope.Tree, agent);
>     var k = agent.RegisterKey("Ammo", 30);
>     Assert.AreEqual(30, tree.Get(k)); // 从 Agent 读取
> }
> [Test] public void ScopeCleanup_TreeDispose_ParentUnaffected()
> {   // 清除 Tree → Agent/Global 的 key 仍可用
>     var agent = new Blackboard(BlackboardScope.Agent);
>     var tree = new Blackboard(BlackboardScope.Tree, agent);
>     var k = agent.RegisterKey("Score", 0);
>     tree.Set(k, 100);
>     tree = null; GC.Collect(); // 模拟 BT 切换
>     Assert.AreEqual(0, agent.Get(k)); // Agent 值不变
> }
> [Test] public void SharedBB_MemberReceivesLeaderUpdate()
> {   // Leader 写入共享 key → Member 自动同步
>     var leaderBB = new Blackboard(BlackboardScope.Agent);
>     var memberBB = new Blackboard(BlackboardScope.Agent);
>     var k = leaderBB.RegisterKey("SquadTarget", (object)null);
>     var shared = new SharedBlackboard(leaderBB, "SquadTarget");
>     shared.AddMember(memberBB);
>     var enemy = new GameObject();
>     leaderBB.Set(k, enemy);
>     Assert.AreSame(enemy, memberBB.Get(k));
> }
> [Test] public void RegisterConflict_ThrowsOnTypeMismatch()
> {   // 同一 key 注册不同类型应抛异常
>     var bb = new Blackboard(BlackboardScope.Agent);
>     bb.RegisterKey("Value", 1.0f);
>     Assert.Throws<InvalidOperationException>(() => bb.RegisterKey<int>("Value", 5));
> }
> ```

> [!tip]- 练习 2 参考答案
> **UE 自定义 Blackboard Key 类型 `EEquipmentState`**。
>
> **1. 枚举定义和 KeyType 头文件**：
> ```cpp
> // EquipmentStateTypes.h
> #pragma once
> #include "EquipmentStateTypes.generated.h"
>
> UENUM()
> enum class EEquipmentState : uint8
> {
>     Unequipped UMETA(DisplayName="Unequipped"),
>     Melee      UMETA(DisplayName="Melee"),
>     Ranged     UMETA(DisplayName="Ranged"),
>     Throwable  UMETA(DisplayName="Throwable"),
> };
> ```
>
> ```cpp
> // BlackboardKeyType_EquipmentState.h
> #pragma once
> #include "BehaviorTree/Blackboard/BlackboardKeyType.h"
> #include "EquipmentStateTypes.h"
> #include "BlackboardKeyType_EquipmentState.generated.h"
>
> UCLASS(EditInlineNew, meta=(DisplayName="EquipmentState"))
> class UBlackboardKeyType_EquipmentState : public UBlackboardKeyType
> {
>     GENERATED_BODY()
> public:
>     UBlackboardKeyType_EquipmentState();
>     static EEquipmentState GetValue(const uint8* MemoryBlock);
>     static bool SetValue(uint8* MemoryBlock, EEquipmentState Value);
>
>     virtual FString DescribeValue(const uint8* RawData) const override;
>     virtual bool CompareValues(const uint8* MemoryBlockA, const uint8* MemoryBlockB) const override;
>     virtual void Clear(uint8* MemoryBlock) const override;
>     virtual bool IsEmpty(const uint8* MemoryBlock) const override;
>     virtual bool TestBasicOperation(const uint8* MemoryBlock, EBasicKeyOperation::Type Op) const override;
>     virtual uint16 GetValueSize() const override { return sizeof(EEquipmentState); }
> };
> ```
>
> ```cpp
> // 实现
> EEquipmentState UBlackboardKeyType_EquipmentState::GetValue(const uint8* MemoryBlock)
> {
>     return *reinterpret_cast<const EEquipmentState*>(MemoryBlock);
> }
> bool UBlackboardKeyType_EquipmentState::CompareValues(const uint8* A, const uint8* B) const
> {
>     return GetValue(A) == GetValue(B);
> }
> FString UBlackboardKeyType_EquipmentState::DescribeValue(const uint8* RawData) const
> {
>     return StaticEnum<EEquipmentState>()->GetDisplayNameStringByValue(
>         static_cast<int64>(GetValue(RawData)));
> }
> void UBlackboardKeyType_EquipmentState::Clear(uint8* MemoryBlock) const
> {
>     SetValue(MemoryBlock, EEquipmentState::Unequipped);
> }
> bool UBlackboardKeyType_EquipmentState::IsEmpty(const uint8* MemoryBlock) const
> {
>     return GetValue(MemoryBlock) == EEquipmentState::Unequipped;
> }
> // TestBasicOperation: 支持相等性比较
> bool UBlackboardKeyType_EquipmentState::TestBasicOperation(const uint8* MemoryBlock, EBasicKeyOperation::Type Op) const
> {
>     return Op == EBasicKeyOperation::Set || Op == EBasicKeyOperation::Equal || Op == EBasicKeyOperation::NotEqual;
> }
> ```
>
> **2. UBTService_DetectEquipment**：
> ```cpp
> void UBTService_DetectEquipment::TickNode(UBehaviorTreeComponent& OwnerComp,
>     uint8* NodeMemory, float DeltaSeconds)
> {
>     auto* BB = OwnerComp.GetBlackboardComponent();
>     APawn* Pawn = OwnerComp.GetAIOwner()->GetPawn();
>     // 假设 Pawn 有一个 IEquipmentInterface
>     IEquipmentInterface* Equip = Cast<IEquipmentInterface>(Pawn);
>     EEquipmentState State = Equip ? Equip->GetCurrentEquipment() : EEquipmentState::Unequipped;
>     BB->SetValue<UBlackboardKeyType_EquipmentState>(EquipmentKey.GetSelectedKeyID(), State);
> }
> ```
>
> **3. UBTDecorator_HasRangedWeapon**：
> ```cpp
> bool UBTDecorator_HasRangedWeapon::CalculateRawConditionValue(
>     UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
> {
>     auto* BB = OwnerComp.GetBlackboardComponent();
>     EEquipmentState State = BB->GetValue<UBlackboardKeyType_EquipmentState>(
>         EquipmentKey.GetSelectedKeyID());
>     return State == EEquipmentState::Ranged;
> }
> // 构造函数中设置 Observer Abort
> UBTDecorator_HasRangedWeapon::UBTDecorator_HasRangedWeapon()
> {
>     bNotifyBecomeRelevant = true;
>     bNotifyCeaseRelevant = true;
>     FlowAbortMode = EBTFlowAbortMode::LowerPriority; // 装备远程武器时抢断
> }
> ```
>
> **4. UBTTask_SwitchToBestWeapon**：
> ```cpp
> EBTNodeResult::Type UBTTask_SwitchToBestWeapon::ExecuteTask(
>     UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
> {
>     auto* BB = OwnerComp.GetBlackboardComponent();
>     EEquipmentState Current = BB->GetValue<UBlackboardKeyType_EquipmentState>(EquipmentKey.GetSelectedKeyID());
>     // 优先级: Ranged > Melee > Throwable > Unequipped
>     static const EEquipmentState Priority[] = {
>         EEquipmentState::Ranged, EEquipmentState::Melee,
>         EEquipmentState::Throwable, EEquipmentState::Unequipped };
>     for (auto Target : Priority)
>     {
>         if (Target == Current) return EBTNodeResult::Succeeded; // 已是最优
>         if (CanSwitchTo(Target))
>         {
>             DoSwitch(Target);
>             BB->SetValue<UBlackboardKeyType_EquipmentState>(EquipmentKey.GetSelectedKeyID(), Target);
>             return EBTNodeResult::Succeeded;
>         }
>     }
>     return EBTNodeResult::Failed;
> }
> ```
>
> **验证**：在 GameplayDebugger 中观察 `EquipmentState` key 的值变化，当 AI 拾取远程武器时，Service 更新 Blackboard → Decorator(LowerPriority) 触发 abort → 当前 Melee 行为被中断 → 切换到 Ranged 分支。

> [!tip]- 练习 3 参考答案（可选）
> **完整的 Observer Abort 系统实现**（适用于 Unity C#）：
>
> **1. Blackboard 中的 Observer 注册机制**：
> ```csharp
> public class Blackboard
> {
>     private Dictionary<string, List<Action<string, object, object>>> _observers = new();
>
>     public void Observe(string key, Action<string, object, object> callback)
>     {
>         if (!_observers.ContainsKey(key)) _observers[key] = new();
>         _observers[key].Add(callback);
>     }
>     public void Unobserve(string key, Action<string, object, object> callback)
>     {
>         _observers[key]?.Remove(callback);
>     }
>     public void Set<T>(BlackboardKey<T> key, T value)
>     {
>         // ... 值变更检测
>         entry.Value = value;
>         // 帧内去重：同一帧同一 key 多次写入只触发一次
>         if (!_notifiedThisFrame.Contains(key.Name))
>         {
>             _notifiedThisFrame.Add(key.Name);
>             // 收集通知到 pending 列表，帧末统一分发
>             _pendingNotifications.Add((key.Name, oldValue, value));
>         }
>     }
>     // LateUpdate 中处理 pending notifications
>     public void FlushNotifications()
>     {
>         foreach (var (key, oldV, newV) in _pendingNotifications)
>         {
>             if (_observers.TryGetValue(key, out var callbacks))
>                 foreach (var cb in callbacks) cb(key, oldV, newV);
>         }
>         _pendingNotifications.Clear();
>         _notifiedThisFrame.Clear();
>     }
> }
> ```
>
> **2. ObservingDecorator 节点**：
> ```csharp
> public class ObservingDecorator : BTDecorator
> {
>     private Func<bool> _condition;
>     private bool _lastConditionResult;
>     private ObserverMode _mode; // Self, LowerPriority, Both
>     private Blackboard _bb;
>     private string _observedKey;
>     private static int _abortDepth = 0;
>     private const int MaxAbortDepth = 3;
>
>     public void OnBecomeRelevant()
>     {
>         _lastConditionResult = _condition();
>         _bb.Observe(_observedKey, OnKeyChanged);
>     }
>     public void OnCeaseRelevant()
>     {
>         _bb.Unobserve(_observedKey, OnKeyChanged);
>     }
>     private void OnKeyChanged(string key, object oldVal, object newVal)
>     {
>         // 递归深度限制
>         if (_abortDepth >= MaxAbortDepth) return;
>         bool current = _condition();
>         if (current == _lastConditionResult) return; // 无变化
>         _lastConditionResult = current;
>         _abortDepth++;
>         try
>         {
>             if (_mode.HasFlag(ObserverMode.Self) && !current)
>                 RequestAbort(AbortTarget.Self);
>             if (_mode.HasFlag(ObserverMode.LowerPriority) && current)
>                 RequestAbort(AbortTarget.LowerPriority);
>         }
>         finally { _abortDepth--; }
>     }
> }
> ```
>
> **3. 测试场景验证**：
> - Agent A 在 Patrol(Running, priority=2)，外部设置 `ThreatLevel = High` → Observer 触发 LowerPriority abort(深度=1) → Patrol 被中断 → Selector 重新评估 → 进入 Flee(priority=1)。
> - Agent B 在 Flee(Running, priority=1)，外部设置 `ThreatLevel = Low` → Observer 触发 Self abort(深度=1) → Flee 分支中断 → 回退到 Patrol。
> - **防止无限循环测试**：在 Flee 的 OnEnter 中写入 `ThreatLevel = Medium`（模拟恢复），但 `Medium != Low` 且 `Medium != High`，不触发 Observer 条件状态切换——安全。如果错误地写入 `High`，递归深度限制（MaxAbortDepth=3）会阻止无限循环。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- **Unreal Engine 官方文档**：[Behavior Tree Overview](https://docs.unrealengine.com/5.3/en-US/behavior-tree-in-unreal-engine/) — 包含 Blackboard 资产管理、Key Selector 使用指南和调试工作流。
- **GDC 2009: Halo 3 — Building a Better Battle** (Damian Isla) — 经典演讲，详细介绍了 Halo 3 的 AI 架构，其中 Blackboard 系统是核心。讨论了 squad AI 的数据共享和"knowledge representation"。
- **GDC 2013: The AI of Halo 4** (David "Rez" Graham) — 讨论了 Halo 4 中行为树和 Blackboard 的演进，包括 per-agent 实例化和数据共享策略。
- **AI Game Programming Wisdom 4** — Section 3.2 "A Data-Driven Approach to Blackboard Architectures" (Kevin Dill)，深入讨论 Blackboard 的作用域层次和序列化。
- **论文**：Hayes-Roth, B. (1985). "A Blackboard Architecture for Control." *Artificial Intelligence*, 26(3), 251-321. — 这是 Blackboard 架构的原始学术论文，讨论了分布式问题求解中的共享数据模型。虽然年代久远，但其分层抽象思想至今仍在游戏 AI 中使用。
- **Unity Behavior Designer 文档**：[Shared Variables](https://opsive.com/support/documentation/behavior-designer/shared-variables/) — Business Designer 中 `SharedVariable<T>` 的设计，展示了商业方案如何实现类型安全的 Blackboard 变量共享。

---

## 常见陷阱

### 1. Key 类型不匹配（最难调试的 bug）

```cpp
// 在编辑器中，设计师不小心将 TargetLocation key 选成了 Bool 类型
BB->SetValueAsBool(BlackboardKey.GetSelectedKeyID(), true); // 编译通过！
// 运行时：Blackboard 内部存储的是 bool，读取时当 FVector 解析 → 未定义行为
```

**防御**：在自定义 Task / Decorator / Service 的构造函数中，使用 `AddObjectFilter`、`AddVectorFilter` 等 API 限制 `FBlackboardKeySelector` 可选 key 的类型。示例 B 展示了完整做法：`BlackboardKey.AddClassFilter<UBlackboardKeyType_ThreatLevel>(...)`。

在 Unity 中，使用泛型 `BlackboardKey<T>` 而非字符串作为 key 句柄——编译器帮你杜绝类型错误。

### 2. Observer Abort 无限循环

```
SetValue("Health", 0)
  → Observer fires → Decorator evaluates → condition false
    → Self abort triggered → branch interrupted
      → BT re-tick from root → reaches OnEnter of some node
        → OnEnter calls SetValue("Health", initialHealth)  ← BUG!
          → Observer fires again → infinite loop
```

**防御**：
- **帧内去重**：同一帧内对同一 key 的多次写入只触发一次 Observer 通知。
- **递归深度限制**：abort 嵌套深度不超过 3（UE 的实现有 `MaxAbortDepth` 限制）。
- **条件不满足抑制**：仅当条件状态**切换**时才触发 abort（从 true 变 false，或从 false 变 true），不要每次 `SetValue` 都无条件 abort。
- **OnEnter 中不重置 Blackboard 值**：节点的 `OnEnter` 不应将 Blackboard 重置为"默认值"——这会导致 Observer 再次触发。Blackboard 值应该由专门的数据生产者（Perception、Service）写入。

### 3. 共享 Blackboard 竞争条件

当多个 agent 同时写入同一个 Blackboard key 时：

```
Frame N:
  Agent A: bb.Set("SquadTarget", targetX)  → observer fires on all members
  Agent B: bb.Set("SquadTarget", targetY)  → observer fires again on all members
  Members: receive two target changes in one frame → thrashing
```

**防御**：
- 明确 key 的**写入者**（通常只有一个，如 squad leader）。
- 如果必须多写者，使用 last-write-wins 策略 + 帧末批量通知（推迟 Observer 回调到帧末统一触发）。
- 对于共享 squad Blackboard，只允许 leader 写入，members 只读——通过 `SharedBlackboard` 的接口设计强制执行。

### 4. Key Name 字符串 vs FName 性能

```cpp
// Bad: FString key lookup — O(n) string comparison
BB->GetValueAsBool(FString("IsAlerted")); // heap allocation + comparison

// Good: FName key lookup — O(1) hash comparison
BB->GetValueAsBool(FName("IsAlerted"));   // interned, fast hash compare
```

UE 的 `FBlackboardKeySelector` 在运行时使用整数 `FBlackboard::FKey`（即 key ID），查找是 O(1) 的数组索引——比 `FName` 的哈希查找更快。但如果你手动使用字符串 API，确保使用 `FName` 而不是 `FString`。

在 C# 中，使用 `string.Intern()` 或直接使用 `BlackboardKey<T>` 避免重复字符串分配。

### 5. Blackboard 膨胀

这是最容易被忽视的长期问题。随着开发进行，Blackboard 中的 key 数量会从最初的 5 个增长到 40 个甚至更多。

**问题**：
- 每个 key 都在 per-agent 内存中占用空间（即使从未被访问）。
- 每次 `GetValue` 调用需要遍历所有 key（如果使用线性查找实现）。
- 设计师在编辑器中面对 40 个 key 的下拉菜单，选择错误 key 的概率大幅增加。

**防御**：
- 定期 audit Blackboard 资产：删除不再使用的 key。
- 使用 Blackboard 继承（UE）：将通用 key 放在 Base Blackboard，特定敌人的 key 放在 Child Blackboard。
- 对于临时数据（如"当前 Tick 计数"），使用节点实例内存（UE 的 `GetInstanceMemorySize()`）而不是 Blackboard。
- 如果某个 key 只在单个 BT 子树中使用，将其作用域限制在子树内（通过 key prefix 或 tree-local Blackboard）。