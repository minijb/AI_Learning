# 行为树在 Unity 中的实现 (C#)

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: [06-bt-fundamentals.md](06-bt-fundamentals.md), [07-bt-node-types.md](07-bt-node-types.md)

---

## 1. 概念讲解

### 为什么需要这个？

Tutorial 06 和 07 用语言无关的方式讲解了行为树的核心理论和节点类型。现在我们要把这些理论在 Unity 的 GameObject/Component 架构中落地。行为树与 FSM 有一个关键区别：**FSM 是"当前处于哪个状态"，行为树是"每帧从根开始一路评估到叶子"**。这个差异直接影响了在 Unity 中的实现策略。

最直接的冲动——把行为树写死在一个 `MonoBehaviour` 里：

```csharp
// 不要在生产环境这样写——它是不可组合的
public class EnemyBT : MonoBehaviour
{
    void Update()
    {
        // 每帧"重新思考"：先看玩家是否在视野内
        if (Vector3.Distance(transform.position, player.position) < detectRange)
        {
            // 在视野内：追击或攻击
            if (Vector3.Distance(transform.position, player.position) < attackRange)
                Attack();
            else
                Chase();
        }
        else
        {
            // 不在视野内：巡逻或调查
            if (hasLastKnownPosition)
                Investigate();
            else
                Patrol();
        }
    }
}
```

这段代码只有两层嵌套，但当行为树节点扩展到三层、四层时，嵌套的 `if-else` 就直接崩塌。更关键的问题是：**它不能复用**——想给另一个敌人用 `Chase` 行为？只能复制粘贴。**策划不能配置**——修改行为意味着改 C# 代码。

### Unity 中行为树实现的架构全景

在 Unity 生态中，行为树实现有三种主流架构路径：

| 方案 | 复杂度 | 适用规模 | 核心思想 |
|:------|:-------|:---------|:---------|
| **Class-based BT (代码行为树)** | 中 | 中型项目、程序员驱动 | BTNode 抽象类，节点在代码中组装，BehaviorTree 类在 Update 中 Tick |
| **ScriptableObject BT (资产化行为树)** | 高 | 中大型项目、策划可配置 | 节点是 ScriptableObject 资产，树结构在 Inspector 中可视编辑，运行时克隆 per-agent 实例 |
| **Visual BT (可视化行为树)** | 高+ | 大型/商业项目、设计师驱动 | 在 Editor 中通过节点图编辑器拖拽搭建，如 Behavior Designer、NodeCanvas |

三种方案不是互斥的。你可以在项目初期用 class-based 快速验证，后期再升级为 ScriptableObject 方案。

### 核心架构：BTNode 基类、Tree Runner、Blackboard

行为树在 Unity 中的标准三层架构：

```
┌──────────────────────────────────────┐
│  BehaviorTree (MonoBehaviour)         │
│  ├─ BTNode _root                     │
│  ├─ Blackboard _blackboard           │
│  └─ void Update() → _root.Tick()     │
└──────────┬───────────────────────────┘
           │ holds reference
           ▼
┌──────────────────────────────────────┐
│  BTNode (abstract class)             │
│  ├─ BTNodeState Tick()               │
│  ├─ void OnEnter()                   │  ← 可选：节点首次激活时调用
│  └─ void OnExit()                    │  ← 可选：节点离开 Running 时调用
│                                      │
│  Composite Nodes:                    │
│  ├─ Selector (list<BTNode> children) │
│  ├─ Sequence                         │
│  └─ Parallel                         │
│                                      │
│  Decorator Nodes:                    │
│  ├─ Inverter                         │
│  ├─ Repeater                         │
│  └─ Cooldown                         │
│                                      │
│  Leaf Nodes:                         │
│  ├─ ActionNode (执行行为)             │
│  └─ ConditionNode (检测条件)          │
└──────────┬───────────────────────────┘
           │ reads/writes
           ▼
┌──────────────────────────────────────┐
│  Blackboard                          │
│  ├─ Dictionary<string, object> _data │
│  ├─ T Get<T>(string key)             │
│  └─ void Set<T>(string key, T val)   │
└──────────────────────────────────────┘
```

**关键设计原则**：BehaviorTree（MonoBehaviour）只做两件事——持有 root 节点引用并在 Update 中调用 `_root.Tick()`。它不知道树的具体结构。所有行为逻辑都在节点内部。

### 设计决策：Class-based vs ScriptableObject 节点

这是行为树在 Unity 实现中的第一个关键决定。

**Class-based 节点**（`BTNode` 是纯 C# 类）：

```csharp
public abstract class BTNode
{
    public abstract BTNodeState Tick();
}
var root = new Selector(new List<BTNode> {
    new Sequence(...),
    new ActionNode(() => { /* do something */; return BTNodeState.Success; })
});
```

- **优点**：零序列化开销，完全由代码控制，适合快速迭代。性能最优——没有 ScriptableObject 的序列化/反序列化成本。
- **缺点**：策划不能配置，树结构不在 Inspector 中可见，调试依赖日志或自定义 Gizmos。

**ScriptableObject 节点**（`BTNodeSO` 继承 `ScriptableObject`）：

```csharp
public abstract class BTNodeSO : ScriptableObject
{
    public abstract BTNodeState Tick(BehaviorTreeRunner runner);
}
```

- **优点**：策划在 Inspector 中拖拽组装行为树，资产化复用（一个 `EnemyChase.asset` 被多个 Prefab 引用），版本控制友好（`.asset` 文件是 YAML，Git 可 diff）。
- **缺点**：ScriptableObject 在 Editor 和 Runtime 的行为不同——在 Editor 中修改资产会**永久改变磁盘上的 `.asset` 文件**。如果运行时将节点状态写回 ScriptableObject，会导致资产被污染，且多个 agent 共享同一资产时状态会相互覆盖。

**推荐策略**：ScriptableObject 用于定义树的结构（设计时），运行时克隆一份 per-agent 的节点状态数据。这是 Behavior Designer、NodeCanvas 等商业方案的核心模式。

### 节点状态持久化策略

这是行为树实现中最容易出错的环节。行为树的每个节点在 Tick 过程中可能处于 `Running` 状态（例如"移动到目标点"需要多帧完成）。下次 Tick 时，节点需要"记得"自己上次在做什么。

有两种策略：

**策略 A：节点级状态（node-level memory）**

节点自身持有状态字段。例如 `MoveToNode` 内部有一个 `bool _isMoving` 字段。

```csharp
public class MoveToNode : BTNode
{
    private bool _isMoving = false;  // state stored on the node itself
    private Vector3 _target;

    public override BTNodeState Tick()
    {
        if (!_isMoving)
        {
            _target = GetNextPatrolPoint();
            _isMoving = true;
            agent.SetDestination(_target);
        }
        if (agent.remainingDistance < 0.5f)
        {
            _isMoving = false;
            return BTNodeState.Success;
        }
        return BTNodeState.Running;
    }
}
```

**问题**：如果多个 agent 共享同一个 `MoveToNode` 实例（例如 ScriptableObject 方案），agent A 的 `_isMoving` 状态会覆盖 agent B 的状态。

**策略 B：Blackboard 级状态（blackboard-level memory）**

节点自身不存储状态，而是通过 Blackboard 以 instance ID 为 key 读写状态。

```csharp
public class MoveToNodeSO : BTNodeSO
{
    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        int id = runner.InstanceId;
        bool isMoving = runner.Blackboard.Get<bool>($"{id}_move_isMoving");
        // ...
    }
}
```

**问题**：每个节点都要手动拼接 key，代码冗长且容易 key 冲突。

**策略 C：克隆 + 隔离（clone + isolate）——推荐**

ScriptableObject 定义树结构（不可变），运行时为每个 agent 创建一份节点的克隆拷贝，克隆体持有运行时状态，原始资产保持清洁。

```csharp
// BehaviorTreeAsset.cs — 设计时资产
public class BehaviorTreeAsset : ScriptableObject
{
    public BTNodeSO root; // tree definition, never mutated at runtime
}

// BehaviorTreeRunner.cs — 运行时
public class BehaviorTreeRunner : MonoBehaviour
{
    public BehaviorTreeAsset treeAsset;
    private BTNodeSO _rootInstance; // cloned at Awake(), this instance holds runtime state

    void Awake()
    {
        _rootInstance = Instantiate(treeAsset.root); // ScriptableObject.Instantiate creates a copy
    }
}
```

`ScriptableObject.Instantiate()` 创建运行时拷贝，asset 本身保持不变。这是 Unity 行为树方案的标准范式。

### Tick 集成：每帧 Update vs 事件驱动

**每帧 Update 方案（pull-based）**：

```csharp
void Update()
{
    _root.Tick();
}
```

行为树在渲染帧中被"拉取"执行。这是最常见的方案，适合大多数 AI。

**事件驱动方案（push-based）**：

```csharp
void OnEnemySpotted(Enemy enemy)
{
    _blackboard.Set("target", enemy);
    _root.Tick(); // only tick when something changed
}
```

只在外部事件发生时重新评估行为树。适合对性能要求极高的场景（数百个单位），因为大多数单位在大多数帧中不做任何决策。

**混合方案**：大多数单位用 Update-driven，特殊单位（Boss）用 Update；低优先级的非玩家单位降低 tick 频率（每 3 帧 tick 一次）。

### 内存管理：per-agent 节点状态

这是 Unity 特有的问题。在 C++ 中，每个 agent 拥有自己的行为树实例是天然的（栈上或堆上分配）。在 C#/Unity 中，你需要显式处理：

1. **ScriptableObject.Instantiate()**：为每个 agent 克隆树节点。优点是与 Unity 序列化集成好，缺点是 `Instantiate` 有 GC 分配（但只在 `Awake` 时一次）。

2. **new BTNode()**：纯 C# 类，无 Unity 序列化开销。在 `Awake` 中分配，生命周期内不再分配。

3. **对象池**：对于频繁创建/销毁的 agent（如波次刷怪），预分配行为树实例到对象池。

**关键原则**：Tick 路径中不应该有任何 `new`。所有节点对象在 `Awake` 或 `Start` 中创建完毕。

### 与 Asset Store 方案的对比

了解商业方案有助于在面试中讨论自研 vs 购买的权衡：

| 特性 | Behavior Designer | NodeCanvas | 自研 ScriptableObject BT |
|:-----|:-----------------|:-----------|:-------------------------|
| 可视化编辑 | ✅ 完整节点图编辑器 | ✅ 完整节点图编辑器 | ❌ 需自己实现 |
| 运行时性能 | 经过深度优化 | 良好 | 取决于实现质量 |
| 与 Unity 集成 | 深（Animator、NavMesh、Physics 节点内置） | 深（FSM + BT 统一编辑） | 需自己封装 |
| 学习曲线 | 低 | 中 | 高（但可控） |
| 授权成本 | $90+/seat | $100+/seat | 无 |
| 源码可修改 | 是（需要源码授权） | 是（需要源码授权） | 完全自主 |
| 策划可配置 | ✅ | ✅ | 取决于 Editor 工具投入 |

**Behavior Designer** 的核心设计值得学习：
- 所有节点是 `Task` 的子类，`OnUpdate()` 返回 `TaskStatus`
- 运行时为每个 agent 创建 `Task` 实例的深拷贝（通过 `JSON Serialization` 或反射克隆）
- Blackboard 是全局共享的（同 agent 的所有节点共享），通过 `SharedVariable<T>` 泛型引用

**NodeCanvas** 的核心设计：
- 节点图在 Editor 中通过 Graph Editor 框架实现
- 行为树和 FSM 共用同一套 Blackboard 和变量系统
- 支持条件性中断（Conditional Abort）——当更高优先级的条件满足时，中断当前 Running 节点

---

## 2. 代码示例

### 示例 A：从零搭建完整行为树框架

这是最基础的 class-based 行为树实现。完整可编译运行（在 Unity 中）。

**BTNode.cs** — 所有节点的抽象基类：

```csharp
// BTNodeState.cs
public enum BTNodeState
{
    Success,
    Failure,
    Running
}

// BTNode.cs
public abstract class BTNode
{
    public abstract BTNodeState Tick();
}
```

**CompositeNode.cs** — Selector 和 Sequence：

```csharp
using System.Collections.Generic;

// CompositeNode.cs
public abstract class CompositeNode : BTNode
{
    protected readonly List<BTNode> _children = new List<BTNode>();

    public void AddChild(BTNode child) => _children.Add(child);
    public void RemoveChild(BTNode child) => _children.Remove(child);
}

// Selector.cs — 从左到右依次尝试子节点，直到一个返回 Success 或 Running
public class Selector : CompositeNode
{
    public override BTNodeState Tick()
    {
        foreach (var child in _children)
        {
            var state = child.Tick();
            if (state != BTNodeState.Failure)
                return state; // Success or Running — stop here
        }
        return BTNodeState.Failure; // all children failed
    }
}

// Sequence.cs — 从左到右依次执行子节点，直到一个返回 Failure 或 Running
public class Sequence : CompositeNode
{
    public override BTNodeState Tick()
    {
        foreach (var child in _children)
        {
            var state = child.Tick();
            if (state != BTNodeState.Success)
                return state; // Failure or Running — stop here
        }
        return BTNodeState.Success; // all children succeeded
    }
}
```

**DecoratorNode.cs** — Inverter（装饰器基类）：

```csharp
// DecoratorNode.cs
public abstract class DecoratorNode : BTNode
{
    protected BTNode _child;

    public DecoratorNode(BTNode child)
    {
        _child = child;
    }
}

// Inverter.cs — 翻转结果：Success → Failure, Failure → Success, Running → Running
public class Inverter : DecoratorNode
{
    public Inverter(BTNode child) : base(child) { }

    public override BTNodeState Tick()
    {
        var state = _child.Tick();
        return state switch
        {
            BTNodeState.Success => BTNodeState.Failure,
            BTNodeState.Failure => BTNodeState.Success,
            BTNodeState.Running => BTNodeState.Running,
            _ => BTNodeState.Failure
        };
    }
}
```

**叶子节点** — ActionNode 和 ConditionNode：

```csharp
using System;

// ActionNode.cs — 执行一个行为，通过 Func 委托注入
public class ActionNode : BTNode
{
    private readonly Func<BTNodeState> _action;

    public ActionNode(Func<BTNodeState> action)
    {
        _action = action;
    }

    public override BTNodeState Tick() => _action();
}

// ConditionNode.cs — 检测一个条件
public class ConditionNode : BTNode
{
    private readonly Func<bool> _condition;

    public ConditionNode(Func<bool> condition)
    {
        _condition = condition;
    }

    public override BTNodeState Tick()
    {
        return _condition() ? BTNodeState.Success : BTNodeState.Failure;
    }
}
```

**BehaviorTree.cs** — MonoBehaviour 驱动的行为树容器：

```csharp
using UnityEngine;

public class BehaviorTree : MonoBehaviour
{
    [SerializeField] private bool _tickOnUpdate = true;

    private BTNode _root;

    public BTNode Root
    {
        get => _root;
        set => _root = value;
    }

    private void Update()
    {
        if (_tickOnUpdate && _root != null)
            _root.Tick();
    }

    // For event-driven ticks
    public void ManualTick()
    {
        _root?.Tick();
    }

    // Builder pattern for tree setup
    public void SetRoot(BTNode root)
    {
        _root = root;
    }
}
```

**使用示例** — 组装一棵简单的行为树：

```csharp
public class SimpleBTDemo : MonoBehaviour
{
    private BehaviorTree _bt;

    void Start()
    {
        _bt = GetComponent<BehaviorTree>();

        // Tree: if playerInRange → Chase, else Patrol
        var chaseSeq = new Sequence();
        chaseSeq.AddChild(new ConditionNode(() => IsPlayerInRange()));
        chaseSeq.AddChild(new ActionNode(() => Chase()));

        var root = new Selector();
        root.AddChild(chaseSeq);
        root.AddChild(new ActionNode(() => Patrol()));

        _bt.SetRoot(root);
    }

    private bool IsPlayerInRange()
    {
        var player = GameObject.FindGameObjectWithTag("Player");
        if (player == null) return false;
        return Vector3.Distance(transform.position, player.transform.position) < 10f;
    }

    private BTNodeState Chase()
    {
        Debug.Log("Chasing...");
        return BTNodeState.Running; // takes multiple frames
    }

    private BTNodeState Patrol()
    {
        Debug.Log("Patrolling...");
        return BTNodeState.Running;
    }
}
```

> **注意**：上面的 `Func<BTNodeState>` 和 `Func<bool>` 委托在初始化时绑定到 MonoBehaviour 的方法，这意味着 `ActionNode` 和 `ConditionNode` 可以安全访问 `transform`、`GetComponent` 等 Unity API。Lambda 捕获 `this` 在这个场景中是安全的——`ActionNode` 的生命周期与 `MonoBehaviour` 绑定。

### 示例 B：Enemy BT — patrol, chase, attack, investigate

这个示例展示了一个完整的敌人 AI，集成了 NavMeshAgent。

```csharp
using UnityEngine;
using UnityEngine.AI;

public class EnemyBTController : MonoBehaviour
{
    [Header("Detection")]
    [SerializeField] private float _detectRange = 15f;
    [SerializeField] private float _attackRange = 2f;
    [SerializeField] private float _loseRange = 20f;
    [SerializeField] private float _fieldOfViewAngle = 120f;

    [Header("Patrol")]
    [SerializeField] private Transform[] _patrolPoints;
    [SerializeField] private float _patrolWaitTime = 2f;

    [Header("Investigation")]
    [SerializeField] private float _investigationTime = 5f;

    // References
    private BehaviorTree _bt;
    private NavMeshAgent _agent;
    private Transform _player;

    // State (would be better in a Blackboard — see Example C)
    private Vector3 _lastKnownPlayerPos;
    private float _lastSeenPlayerTime = float.MinValue;
    private int _currentPatrolIndex;
    private float _waitTimer;
    private bool _isWaiting;

    // Threshold for "arrived at destination"
    private const float ARRIVED_THRESHOLD = 1.5f;

    void Awake()
    {
        _bt = GetComponent<BehaviorTree>();
        _agent = GetComponent<NavMeshAgent>();
        _player = GameObject.FindGameObjectWithTag("Player")?.transform;
    }

    void Start()
    {
        BuildBehaviorTree();
    }

    private void BuildBehaviorTree()
    {
        // Branch 1: Attack (highest priority)
        var attackSeq = new Sequence();
        attackSeq.AddChild(new ConditionNode(() => CanSeePlayer() && DistToPlayer() < _attackRange));
        attackSeq.AddChild(new ActionNode(() => Attack()));

        // Branch 2: Chase
        var chaseSeq = new Sequence();
        chaseSeq.AddChild(new ConditionNode(() => CanSeePlayer()));
        chaseSeq.AddChild(new ActionNode(() => Chase()));

        // Branch 3: Investigate last known position
        var investigateSeq = new Sequence();
        investigateSeq.AddChild(new ConditionNode(() => HasRecentSighting()));
        investigateSeq.AddChild(new ActionNode(() => Investigate()));

        // Branch 4: Patrol (default / fallback)
        var patrolAction = new ActionNode(() => Patrol());

        // Root: Selector tries Attack → Chase → Investigate → Patrol
        var root = new Selector();
        root.AddChild(attackSeq);
        root.AddChild(chaseSeq);
        root.AddChild(investigateSeq);
        root.AddChild(patrolAction);

        _bt.SetRoot(root);
    }

    // --- Perception ---

    private bool CanSeePlayer()
    {
        if (_player == null) return false;

        float dist = DistToPlayer();
        if (dist > _detectRange) return false;

        // Field of view check
        Vector3 dirToPlayer = (_player.position - transform.position).normalized;
        float angle = Vector3.Angle(transform.forward, dirToPlayer);
        if (angle > _fieldOfViewAngle * 0.5f) return false;

        // Raycast to check line of sight
        if (Physics.Raycast(transform.position + Vector3.up, dirToPlayer, out var hit, dist))
        {
            if (!hit.transform.CompareTag("Player"))
                return false;
        }

        // Update last known position
        _lastKnownPlayerPos = _player.position;
        _lastSeenPlayerTime = Time.time;
        return true;
    }

    private float DistToPlayer()
    {
        return _player == null ? float.MaxValue
            : Vector3.Distance(transform.position, _player.position);
    }

    private bool HasRecentSighting()
    {
        return Time.time - _lastSeenPlayerTime < _investigationTime;
    }

    // --- Actions ---

    private BTNodeState Attack()
    {
        _agent.isStopped = true;
        _agent.ResetPath();

        // Face the player
        Vector3 dir = (_player.position - transform.position).normalized;
        dir.y = 0;
        if (dir != Vector3.zero)
        {
            var targetRot = Quaternion.LookRotation(dir);
            transform.rotation = Quaternion.Slerp(transform.rotation, targetRot, Time.deltaTime * 10f);
        }

        // Attack logic — in a real game, this would trigger an animation event
        Debug.Log("Attacking player!");

        // If player moves out of attack range, stop attacking
        if (DistToPlayer() > _attackRange * 1.2f)
            return BTNodeState.Failure;

        return BTNodeState.Running;
    }

    private BTNodeState Chase()
    {
        _agent.isStopped = false;
        _agent.speed = 5f;
        _agent.SetDestination(_player.position);

        // If we lost sight
        if (DistToPlayer() > _loseRange)
        {
            _lastKnownPlayerPos = _player.position;
            return BTNodeState.Failure;
        }

        return BTNodeState.Running;
    }

    private BTNodeState Investigate()
    {
        _agent.isStopped = false;
        _agent.speed = 3.5f;
        _agent.SetDestination(_lastKnownPlayerPos);

        // Arrived at investigation point — look around briefly
        if (_agent.remainingDistance < ARRIVED_THRESHOLD && !_agent.pathPending)
        {
            if (!_isWaiting)
            {
                _isWaiting = true;
                _waitTimer = 2f;
            }

            _waitTimer -= Time.deltaTime;
            if (_waitTimer <= 0f)
            {
                _isWaiting = false;
                _lastSeenPlayerTime = float.MinValue; // clear investigation
                return BTNodeState.Failure; // done investigating, fall through to Patrol
            }
        }

        return BTNodeState.Running;
    }

    private BTNodeState Patrol()
    {
        _agent.isStopped = false;
        _agent.speed = 2f;

        if (_patrolPoints == null || _patrolPoints.Length == 0)
        {
            // No patrol points defined — just idle
            return BTNodeState.Running;
        }

        Transform target = _patrolPoints[_currentPatrolIndex];
        _agent.SetDestination(target.position);

        // Arrived at patrol point
        if (_agent.remainingDistance < ARRIVED_THRESHOLD && !_agent.pathPending)
        {
            if (!_isWaiting)
            {
                _isWaiting = true;
                _waitTimer = _patrolWaitTime;
            }

            _waitTimer -= Time.deltaTime;
            if (_waitTimer <= 0f)
            {
                _isWaiting = false;
                _currentPatrolIndex = (_currentPatrolIndex + 1) % _patrolPoints.Length;
            }
        }

        return BTNodeState.Running;
    }

    // --- Debug ---

    void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireSphere(transform.position, _detectRange);

        Gizmos.color = Color.red;
        Gizmos.DrawWireSphere(transform.position, _attackRange);

        Gizmos.color = Color.blue;
        Vector3 forward = transform.forward * _detectRange;
        float halfFov = _fieldOfViewAngle * 0.5f * Mathf.Deg2Rad;
        Vector3 left = Quaternion.Euler(0, -_fieldOfViewAngle * 0.5f, 0) * forward;
        Vector3 right = Quaternion.Euler(0, _fieldOfViewAngle * 0.5f, 0) * forward;
        Gizmos.DrawRay(transform.position, left);
        Gizmos.DrawRay(transform.position, right);

        if (_patrolPoints != null)
        {
            Gizmos.color = Color.green;
            for (int i = 0; i < _patrolPoints.Length; i++)
            {
                if (_patrolPoints[i] != null)
                    Gizmos.DrawWireSphere(_patrolPoints[i].position, 0.3f);
            }
        }
    }
}
```

**这个示例的关键设计点**：

1. **`CanSeePlayer()` 包含完整的感知管线**：距离检测 → 视野角度 → 射线检测遮挡。Raycast 从 `transform.position + Vector3.up` 发出（眼睛高度），避免射线从脚底发出被地面遮挡。

2. **`HasRecentSighting()` 实现了"最后已知位置"的记忆**：当玩家跑出视线，敌人会记住最后看到玩家的位置并前往调查。`_investigationTime` 秒后如果仍未发现，调查行为失败，退回巡逻。

3. **Attack 行为的退出条件**：当玩家跑出攻击范围时返回 `Failure`，而不是继续"追着空气攻击"。这保证了行为树的 fallback 机制正常工作——Attack 失败后 Selector 尝试下一个分支（Chase）。

4. **`_isWaiting` 和 `_waitTimer` 处理了 BT 特有的"等待"语义**：行为树节点没有"等待"的概念——它们必须每帧返回 Success/Failure/Running。通过 `_isWaiting` 标志和计时器模拟等待。

### 示例 C：ScriptableObject 行为树——工业标准方案

这是生产环境的方案。ScriptableObject 定义树结构（设计时），`BehaviorTreeRunner` 在运行时为每个 agent 创建节点实例。

**BTNodeSO.cs** — ScriptableObject 节点基类：

```csharp
using UnityEngine;

public abstract class BTNodeSO : ScriptableObject
{
    [HideInInspector] public string guid; // unique ID for editor serialization
    [HideInInspector] public Vector2 editorPosition; // position in node graph editor

    /// <summary>
    /// Returns the result of evaluating this node.
    /// The runner carries per-agent blackboard and instance data.
    /// </summary>
    public abstract BTNodeState Tick(BehaviorTreeRunner runner);

    /// <summary>
    /// Called once when this node is first activated in the current tick cycle
    /// (transitioning from not-Running to Running).
    /// Override in subclasses that need initialization per activation.
    /// </summary>
    public virtual void OnEnter(BehaviorTreeRunner runner) { }

    /// <summary>
    /// Called when this node exits — either Success, Failure, or aborted.
    /// </summary>
    public virtual void OnExit(BehaviorTreeRunner runner) { }

    /// <summary>
    /// Create a runtime clone for use by a specific agent.
    /// Override if your node has mutable runtime state fields.
    /// </summary>
    public virtual BTNodeSO Clone()
    {
        return Instantiate(this);
    }
}
```

**CompositeNodeSO.cs** — Selector 和 Sequence 的 SO 版本：

```csharp
using System.Collections.Generic;
using UnityEngine;

public abstract class CompositeNodeSO : BTNodeSO
{
    public List<BTNodeSO> children = new List<BTNodeSO>();

    public override BTNodeSO Clone()
    {
        var clone = (CompositeNodeSO)Instantiate(this);
        clone.children = new List<BTNodeSO>(children.Count);
        foreach (var child in children)
            clone.children.Add(child.Clone());
        return clone;
    }
}

// SelectorSO.cs
[CreateAssetMenu(menuName = "BehaviorTree/Selector")]
public class SelectorSO : CompositeNodeSO
{
    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        foreach (var child in children)
        {
            var state = child.Tick(runner);
            if (state != BTNodeState.Failure)
                return state;
        }
        return BTNodeState.Failure;
    }
}

// SequenceSO.cs
[CreateAssetMenu(menuName = "BehaviorTree/Sequence")]
public class SequenceSO : CompositeNodeSO
{
    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        foreach (var child in children)
        {
            var state = child.Tick(runner);
            if (state != BTNodeState.Success)
                return state;
        }
        return BTNodeState.Success;
    }
}
```

**InverterSO.cs** — 条件取反装饰器：

```csharp
using UnityEngine;

[CreateAssetMenu(menuName = "BehaviorTree/Inverter")]
public class InverterSO : BTNodeSO
{
    public BTNodeSO child;

    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        var result = child.Tick(runner);
        return result switch
        {
            BTNodeState.Success => BTNodeState.Failure,
            BTNodeState.Failure => BTNodeState.Success,
            _ => BTNodeState.Running
        };
    }

    public override BTNodeSO Clone()
    {
        var clone = (InverterSO)Instantiate(this);
        clone.child = child.Clone();
        return clone;
    }
}
```

**ActionNodeSO.cs** — 叶子节点：行为 Action（由子类 override）：

```csharp
using UnityEngine;

public abstract class ActionNodeSO : BTNodeSO
{
    // Subclasses override Tick to implement specific behavior.
    // They access the runner and its Blackboard for per-agent data.
}

// --- Concrete Action Examples ---

[CreateAssetMenu(menuName = "BehaviorTree/Actions/MoveToTarget")]
public class MoveToTargetActionSO : ActionNodeSO
{
    public string targetKey = "target";      // blackboard key for target Transform
    public string speedKey = "moveSpeed";    // blackboard key for movement speed
    public float stoppingDistance = 1.5f;

    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        var agent = runner.NavMeshAgent;
        var bb = runner.Blackboard;

        if (!bb.TryGetValue<Transform>(targetKey, out var target) || target == null)
            return BTNodeState.Failure;

        float speed = bb.TryGetValue<float>(speedKey, out var s) ? s : 3.5f;
        agent.speed = speed;
        agent.isStopped = false;
        agent.SetDestination(target.position);

        if (agent.remainingDistance <= stoppingDistance && !agent.pathPending)
            return BTNodeState.Success;

        return BTNodeState.Running;
    }
}

[CreateAssetMenu(menuName = "BehaviorTree/Actions/Wait")]
public class WaitActionSO : ActionNodeSO
{
    public float duration = 2f;

    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        int instanceId = runner.InstanceId;
        float elapsed = runner.Blackboard.Get<float>($"{instanceId}_wait_elapsed", 0f);

        elapsed += Time.deltaTime;
        runner.Blackboard.Set($"{instanceId}_wait_elapsed", elapsed);

        if (elapsed >= duration)
        {
            runner.Blackboard.Remove($"{instanceId}_wait_elapsed");
            return BTNodeState.Success;
        }

        return BTNodeState.Running;
    }
}
```

**ConditionNodeSO.cs** — 叶子节点：条件判断：

```csharp
using UnityEngine;

public abstract class ConditionNodeSO : BTNodeSO
{
    // Subclasses override Tick to check a condition.
    // Return Success if true, Failure if false. Never Running.
}

// --- Concrete Condition Examples ---

[CreateAssetMenu(menuName = "BehaviorTree/Conditions/IsTargetInRange")]
public class IsTargetInRangeSO : ConditionNodeSO
{
    public string targetKey = "target";
    public float range = 10f;

    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        var bb = runner.Blackboard;
        var self = runner.transform;

        if (!bb.TryGetValue<Transform>(targetKey, out var target) || target == null)
            return BTNodeState.Failure;

        float dist = Vector3.Distance(self.position, target.position);
        return dist <= range ? BTNodeState.Success : BTNodeState.Failure;
    }
}

[CreateAssetMenu(menuName = "BehaviorTree/Conditions/HasBlackboardKey")]
public class HasBlackboardKeySO : ConditionNodeSO
{
    public string key;

    public override BTNodeState Tick(BehaviorTreeRunner runner)
    {
        return runner.Blackboard.ContainsKey(key) ? BTNodeState.Success : BTNodeState.Failure;
    }
}
```

**BehaviorTreeAsset.cs** — 设计时资产，定义整棵树的结构：

```csharp
using UnityEngine;

[CreateAssetMenu(menuName = "BehaviorTree/BehaviorTreeAsset")]
public class BehaviorTreeAsset : ScriptableObject
{
    [SerializeField] private BTNodeSO _root;

    public BTNodeSO Root => _root;

    /// <summary>
    /// Create a deep clone of this tree for runtime use by a specific agent.
    /// </summary>
    public BTNodeSO CreateRuntimeInstance()
    {
        return _root?.Clone();
    }
}
```

**BehaviorTreeRunner.cs** — 运行时驱动器：

```csharp
using UnityEngine;
using UnityEngine.AI;

public class BehaviorTreeRunner : MonoBehaviour
{
    [SerializeField] private BehaviorTreeAsset _treeAsset;

    private BTNodeSO _rootInstance;
    private Blackboard _blackboard;
    private NavMeshAgent _navMeshAgent;
    private static int _nextInstanceId = 0;

    public int InstanceId { get; private set; }
    public Blackboard Blackboard => _blackboard;
    public NavMeshAgent NavMeshAgent => _navMeshAgent;

    void Awake()
    {
        InstanceId = _nextInstanceId++;
        _blackboard = new Blackboard();
        _navMeshAgent = GetComponent<NavMeshAgent>();

        if (_treeAsset != null)
            _rootInstance = _treeAsset.CreateRuntimeInstance();
    }

    void Update()
    {
        if (_rootInstance != null)
            _rootInstance.Tick(this);
    }
}
```

**Blackboard.cs** — 节点间共享数据的键值存储：

```csharp
using System.Collections.Generic;

public class Blackboard
{
    private readonly Dictionary<string, object> _data = new Dictionary<string, object>();

    public void Set<T>(string key, T value)
    {
        _data[key] = value;
    }

    public T Get<T>(string key, T defaultValue = default)
    {
        if (_data.TryGetValue(key, out var obj) && obj is T val)
            return val;
        return defaultValue;
    }

    public bool TryGetValue<T>(string key, out T value)
    {
        if (_data.TryGetValue(key, out var obj) && obj is T val)
        {
            value = val;
            return true;
        }
        value = default;
        return false;
    }

    public bool ContainsKey(string key) => _data.ContainsKey(key);

    public void Remove(string key)
    {
        _data.Remove(key);
    }

    public void Clear()
    {
        _data.Clear();
    }
}
```

**如何使用 ScriptableObject BT**：

1. 在 Project 窗口中右键创建 `BehaviorTreeAsset`、`SelectorSO`、`SequenceSO`、`IsTargetInRangeSO`、`MoveToTargetActionSO` 等资产。
2. 在 `BehaviorTreeAsset` 的 Inspector 中拖入 `SelectorSO` 作为 root。
3. 在 `SelectorSO` 的 `children` 列表中拖入 `SequenceSO`（追击分支）和 `MoveToTargetActionSO`（巡逻分支——作为 fallback）。
4. 将 `BehaviorTreeAsset` 拖入场景中 Enemy Prefab 的 `BehaviorTreeRunner._treeAsset` 字段。
5. 在 `Awake` 中通过 `Blackboard.Set("target", playerTransform)` 注入目标引用。
6. 运行 — `BehaviorTreeRunner.Update()` 每帧调用 `_rootInstance.Tick(this)`。

**与示例 B（class-based）的关键区别**：

| 方面 | 示例 B (Class-based) | 示例 C (ScriptableObject) |
|:-----|:---------------------|:--------------------------|
| 树结构定义 | 在 `BuildBehaviorTree()` 中用代码组装 | 在 Inspector 中拖拽 SO 资产拼装 |
| 节点状态存储 | 直接存储在 `EnemyBTController` 的字段中 | 存储在 `Blackboard` 中以 instance ID 为 key |
| 策划可配置性 | 需改代码 | 无需改代码，拖拽 + 填写字段即可 |
| 复用性 | 复制粘贴代码 | 资产引用到多个 Prefab |
| 调试 | 在代码中打断点 | 可在 Inspector 中查看当前节点状态（需额外实现） |
| Clone 成本 | 无 clone | `Awake` 时深度 clone 整棵树（一次性成本） |

---

## 3. 练习

### 练习 1：扩展框架 — Repeater 装饰器 + 循环巡逻守卫

**目标**：在示例 A 的框架中实现 `Repeater` 装饰器，并用于创建无限循环巡逻的守卫。

**Repeater 规格**：

- 构造函数接受两个参数：`BTNode child` 和 `int repeatCount`（0 表示无限循环）
- `Tick()` 逻辑：
  - 如果 `repeatCount == 0`：执行子节点 → 无论子节点返回什么，`Repeater` 永远返回 `Running`
  - 如果 `repeatCount > 0`：执行子节点，如果子节点返回 Success 则计数器 +1；累计到 `repeatCount` 次后返回 Success；任意一次 Failure 立即返回 Failure
- 在 `Awake` 中构建树（不要修改框架代码）：

```csharp
// 预期树结构:
// Selector
//   ├─ Sequence (检测到玩家 → 追击链)
//   │    ├─ ConditionNode(IsPlayerNear)
//   │    └─ ActionNode(ChasePlayer)
//   └─ Repeater(∞) (默认巡逻循环)
//        └─ Sequence (巡逻一个循环)
//             ├─ ActionNode(MoveToNextWaypoint)
//             └─ ActionNode(WaitAtWaypoint)
```

**要求**：

1. 实现 `Repeater` 继承 `DecoratorNode`
2. 实现 `MoveToNextWaypoint` ActionNode：递归巡逻点数组
3. 实现 `WaitAtWaypoint` ActionNode：到达后等待 2 秒
4. 在场景中创建 3 个巡逻点，测试守卫在检测到玩家前无限循环巡逻，检测到玩家后中断巡逻进行追击
5. 验证追击结束后守卫回到 `Repeater(∞)` 重新开始巡逻（注意 `Repeater` 的子节点中 `MoveToNextWaypoint` 和 `WaitAtWaypoint` 的状态是否被正确重置）

**思考题**：`Repeater(∞)` 的子节点中包含 `WaitAtWaypoint`（多帧 Running 节点）。当守卫检测到玩家、Selector 切换到追击分支、追击结束后回到巡逻分支时，`WaitAtWaypoint` 上次的 `_waitTimer` 还保留着吗？如果不处理会有什么后果？你有哪两种策略来解决？（提示：`OnEnter` 重置 / 每次 Tick 都重新评估起始状态）

---

### 练习 2：Cooldown 装饰器 + Blackboard

**目标**：为框架添加 `Cooldown` 装饰器和完整的 `Blackboard` 类。

**Cooldown 规格**：

- 构造函数：`Cooldown(BTNode child, float cooldownSeconds)`
- 行为：
  - 第一次 Tick：执行子节点，记录当前时间作为上次执行时间
  - 后续 Tick：如果 `Time.time - lastExecuteTime < cooldownSeconds`，直接返回 Failure（跳过子节点）
  - 如果冷却时间已过，重置 `lastExecuteTime` 并再次执行子节点
- 注意：Cooldown 必须写入 Blackboard 以 `instanceId` 为 key 存储 `lastExecuteTime`，避免多 agent 共享状态的问题

**Blackboard 规格**：

```csharp
public class Blackboard
{
    // T Get<T>(string key) — 读取
    // void Set<T>(string key, T value) — 写入
    // bool TryGetValue<T>(string key, out T value) — 安全读取
    // bool ContainsKey(string key)
    // void Remove(string key)
    // void Clear()
}
```

**要求**：

1. 实现 `Blackboard` 类
2. 修改 `BTNode` 基类，添加 `public Blackboard Blackboard { get; set; }` 属性
3. 修改 `BehaviorTree`，在 `Awake` 中创建 `Blackboard` 实例并在设置 `Root` 时注入到整棵树（递归设置每个节点的 Blackboard 引用）
4. 实现 `Cooldown` 装饰器继承 `DecoratorNode`
5. 测试：创建一个攻击序列，攻击一次后进入 3 秒冷却，冷却期间攻击条件不成立（回退到巡逻），冷却结束后可以再次攻击

**验证**：创建两个 Enemy Prefab 实例（agent A 和 agent B），确保 agent A 的 Cooldown 状态不会影响 agent B。在 Blackboard 中打印 key 列表来验证隔离。

---

### 练习 3（可选）：简易 ScriptableObject BT 创作工具

**目标**：创建一个简单的 Editor 工具，允许在 Hierarchy 视图中可视化行为树节点的 `Running/Success/Failure` 状态。

**要求**：

1. 给 `BTNodeSO` 添加 `[HideInInspector] public BTNodeState lastTickResult;` 字段（在 Clone 时重置）
2. 在 `BehaviorTreeRunner` 上实现 `OnDrawGizmos` / custom Editor，绘制当前 tick 的节点路径：
   - 使用 GUI 或 Handles 在 Scene 视图中显示节点名称和状态颜色（Running = 黄色, Success = 绿色, Failure = 红色）
   - 只显示"活跃路径"——从 root 到当前 Running 叶子的路径上的节点
3. 在 Inspector 中为 `BehaviorTreeRunner` 显示当前行为树的运行状态摘要（哪些节点在 Running 路径上）

**提示**：用 `Resources.FindObjectsOfTypeAll<BehaviorTreeRunner>()` 找到场景中所有 BT runner，在 OnDrawGizmos 中遍历并绘制。

**挑战**：如果有 100+ 个 enemy，Gizmos 绘制会让编辑器卡顿。你如何限制只绘制选中的或最近的 N 个单位？

---

## 4. 扩展阅读

### BT 框架与资产

| 资源 | 说明 |
|:-----|:-----|
| [Behavior Designer 文档](https://opsive.com/support/documentation/behavior-designer/) | 目前 Unity Asset Store 上最成熟的行为树可视化编辑器。其 `Task` 基类设计、`SharedVariable` 系统、Conditional Abort 机制值得深入学习。**强烈推荐阅读其架构文档**。 |
| [NodeCanvas 文档](https://nodecanvas.paradoxnotion.com/documentation/) | 同时支持 FSM 和行为树的可视化脚本工具。其 Blackboard 系统和变量绑定机制的设计思路值得参考。 |
| [Panda BT](https://github.com/pandabehaviour/panda-bt) | 开源的行为树框架，轻量级，代码驱动，无可视化编辑器。适合学习 BT 实现细节。 |
| [BehaviorTree.CPP](https://github.com/BehaviorTree/BehaviorTree.CPP) | C++ 行为树库，被 ROS 生态广泛使用。其 Groot 可视化编辑器是开源的参考实现。 |

### Unity 官方资源

| 资源 | 说明 |
|:-----|:-----|
| [Unity ML-Agents](https://github.com/Unity-Technologies/ml-agents) | Unity 官方的机器学习框架。ML-Agents 内部使用行为树作为训练环境中的 NPC 控制器（Behavior Parameters + Decision Requester 组件）。理解 ML-Agents 如何与传统 BT 结合：BT 处理日常行为，ML 处理特殊决策。 |
| [Unity DOTS AI 导航](https://docs.unity3d.com/Packages/com.unity.ai.navigation@latest) | Unity 新一代的 NavMesh 系统（基于 DOTS）。当行为树驱动数百个 agent 时，NavMeshQuery 的批量查询能力是关键优化。 |
| [Unite 2017: Game Architecture with Scriptable Objects](https://www.youtube.com/watch?v=raQ3iHhE_Kk) | Ryan Hipple 的经典演讲。虽然不是专门讲 BT 的，但它奠定了脚本对象在 Unity 中作为数据容器/节点定义的哲学基础。**必看**。 |

### 书籍章节

| 书籍 | 章节 | 说明 |
|:-----|:-----|:-----|
| *AI Game Programming Wisdom* 系列 | 多章 | 行为树在各种商业游戏中的实战案例。特别推荐第 1 卷中关于 Halo 2 的 BT 实现和第 4 卷中的 Dynamic BT 章节。 |
| *Behavioral Mathematics for Game AI* (Dave Mark) | Chapter 9: Behavioral Trees | 从数学/决策论角度分析行为树的优缺点和适用边界。 |
| *Game AI Pro* 系列 | Volume 1, Chapter 6; Volume 3, Chapter 9 | 行业实践——包括 Behavior Tree debugging tools 和 behavior tree optimization。 |

### 面试相关

- **Behavior Designer 的 Conditional Abort 机制**：它允许低优先级节点被高优先级条件中断。在面试中讨论 BT 时，这是一个常见的深入话题——"如何处理实时条件变化？"的答案就是 Conditional Abort。
- **BT vs FSM 在 Unity 中的性能对比**：BT 每帧从根遍历到叶子，复杂度 O(depth) × O(branching)；FSM 一次状态查询 O(1)。当深度 ≤5 且 branching ≤8 时，差距可忽略。但需能解释两者的复杂度差异。
- **自研 BT 的评估清单**：面试中可能被问到"你会自己写一个 BT 框架吗？"——回答要点：节点模型（Tick/OnEnter/OnExit）、状态持久化策略（clone vs blackboard vs 节点级字段）、编辑器工具（Gizmos 至少够用）、性能（避免 GC、降低 tick 频率选项）。

---

## 常见陷阱

### 1. 节点状态在 agent 间泄露

**症状**：场景中有 10 个敌人，都引用同一个 `ChaseActionSO.asset`。敌人 A 的追逐正常，敌人 B 的追逐行为异常——有时不追逐，有时目标位置指向敌人 A 的目标。

**根因**：`BTNodeSO` 的子类在 `Tick()` 中修改了自身的实例字段（比如 `_targetPosition`），而所有 agent 共享同一个 SO 实例。

**解法**：在 `Awake` 中为每个 agent 调用 `ScriptableObject.Instantiate()` 创建节点实例的深拷贝。或者将可变状态写入 `Blackboard`，以 `runner.InstanceId + node.guid` 为 key。

```csharp
// ❌ WRONG — shared mutable state on SO asset
private Vector3 _targetPosition; // all agents share this field

// ✅ CORRECT — per-agent state via Blackboard
string stateKey = $"{runner.InstanceId}_{guid}_target";
Vector3 target = runner.Blackboard.Get<Vector3>(stateKey);
```

### 2. 每帧 Tick 中创建新的节点对象

**症状**：在 `BTNode.Tick()` 中写 `new Sequence()` 或 `new List<BTNode>()` 动态构建子树。

**根因**：行为树的节点结构应在初始化时一次性构建。每帧 `new` 会产生大量 GC 分配，导致帧率周期性尖刺（GC.Collect 的卡顿）。

**解法**：在 `Awake`/`Start` 中构建树结构。Tick 路径上零分配。

### 3. Update() 性能：大量 agent 时每帧全树遍历

**症状**：场景中有 100 个敌人，每个敌人在 `Update()` 中执行完整行为树。Profiler 显示 `BTNode.Tick` 占总 CPU 的 40%+。

**根因**：行为树是"全量评估"——即使只有 2 个敌人实际可见玩家，所有 100 个敌人都在执行感知检测。

**解法**：

- **分层 LOD**：将 AI 更新分为 full-tick（每帧）、medium-tick（每 3 帧）、low-tick（每 10 帧）。离玩家远的敌人降低 tick 频率。
- **空间分区**：只 tick 玩家周围一定半径内的敌人。用 `Physics.OverlapSphereNonAlloc` 或简单的按距离排序 + early-out。
- **条件短路**：在 Selector/Sequence 中，一旦节点返回 `Failure`，后续子节点不执行。确保感知条件（最昂贵的检查）放在树的最顶层，尽早失败。

```csharp
// ✅ Correct — tick frequency by distance
void Update()
{
    if (Time.frameCount % GetTickInterval() != 0)
        return;
    _root.Tick();
}

int GetTickInterval()
{
    float dist = DistToPlayer();
    if (dist < 20f) return 1;  // every frame
    if (dist < 50f) return 3;  // every 3 frames
    return 10;                  // every 10 frames
}
```

### 4. ScriptableObject 资产在运行时被意外修改

**症状**：在 Play Mode 中调整了 `MoveSpeed` 字段的值，退出 Play Mode 后值被持久化到了 `.asset` 文件中（或者反过来——退出后值丢失）。

**根因**：Unity Editor 中，ScriptableObject 的字段修改在 Play Mode 期间默认不会持久化，但某些情况下（如 `EditorUtility.SetDirty` 被调用，或使用了 `[SerializeField]` 的引用类型字段指向了运行时创建的对象）会导致数据污染。

**解法**：

- 永远在 `Clone()` 后的实例上修改运行时数据，原始资产仅作只读模板
- 在 `OnValidate()` 中添加 Editor-only 的防御性检查
- 使用 `HideFlags.DontSave` 标记运行时克隆的节点，避免被意外序列化

```csharp
public virtual BTNodeSO Clone()
{
    var clone = Instantiate(this);
    clone.hideFlags = HideFlags.DontSave; // prevent accidental serialization
    return clone;
}
```

### 5. `foreach` 在 Composite 节点中的分配

**症状**：使用 Profiler 的 Deep Profile 发现 `Selector.Tick()` 中的 `foreach (var child in _children)` 每帧产生 40B 的 GC 分配。

**根因**：`List<T>.GetEnumerator()` 本身不产生分配（`List<T>.Enumerator` 是值类型）。但如果 `_children` 声明为 `IEnumerable<BTNode>` 或 `IList<BTNode>`，编译器会装箱枚举器。

**解法**：将 `_children` 声明为 `List<BTNode>` 或 `BTNode[]`。对于数组，`foreach` 在 C# 中直接编译为 `for` 循环，零分配。

### 6. `OnEnter`/`OnExit` 与 `Running` 状态的交互

**症状**：行为树的 `Sequence` 中有 3 个子节点 `[A → B → C]`。A 返回 Success，B 返回 Running。下一帧重新 Tick 时，B 再次被 Tick（正确）——但 B 的 `OnEnter` 也被调用了（错误）。

**根因**：`Sequence.Tick()` 中从第一个子节点开始遍历，对每个子节点调用 `Tick()`。但没有记录"哪个子节点正在 Running"，导致每次 Tick 都重新对 B 调用 `OnEnter`。

**解法**：Composite 节点需要跟踪"当前活跃子节点的索引"。当进入一个新的子节点时，对上一个子节点调用 `OnExit`，对新子节点调用 `OnEnter`。

```csharp
public class Sequence : CompositeNode
{
    private int _currentChildIndex = 0;

    public override BTNodeState Tick()
    {
        for (int i = _currentChildIndex; i < _children.Count; i++)
        {
            var child = _children[i];
            var state = child.Tick();

            if (state == BTNodeState.Running)
            {
                _currentChildIndex = i;
                return BTNodeState.Running;
            }

            // Child finished — reset for next activation
            child.OnExit();
        }

        // All children succeeded — reset index
        _currentChildIndex = 0;
        return BTNodeState.Success;
    }
}
```
