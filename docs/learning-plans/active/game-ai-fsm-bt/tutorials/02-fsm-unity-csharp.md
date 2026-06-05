---
title: "FSM 在 Unity 中的实现 (C#)"
updated: 2026-06-05
---

# FSM 在 Unity 中的实现 (C#)

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: [[01-fsm-core-concepts]]

---

## 1. 概念讲解

### 为什么需要这个？

Tutorial 01 用语言无关伪代码讲解了 FSM 的核心理论。现在我们把理论落地到 Unity 引擎中。Unity 是一个基于 GameObject/Component 架构的引擎，所有脚本继承自 `MonoBehaviour`，由引擎在每帧自动调用 `Update()`（或 `FixedUpdate()`/`LateUpdate()`）。这个架构给 FSM 实现带来了特定的约束和设计选择。

**最直接的冲动**——把 FSM 塞进一个 `MonoBehaviour` 的 `Update()` 里：

```csharp
// 新人最常写的代码——不要在生产环境这样写
public class EnemyAI : MonoBehaviour
{
    enum State { Patrol, Chase, Attack, Death }
    State currentState = State.Patrol;

    void Update()
    {
        float dist = Vector3.Distance(transform.position, player.position);

        switch (currentState)
        {
            case State.Patrol:
                PatrolUpdate();
                if (dist < detectRange) currentState = State.Chase;
                break;
            case State.Chase:
                ChaseUpdate();
                if (dist < attackRange) currentState = State.Attack;
                else if (dist > loseRange) currentState = State.Patrol;
                break;
            case State.Attack:
                AttackUpdate();
                if (health <= 0) currentState = State.Death;
                else if (dist > attackRange * 1.5f) currentState = State.Chase;
                break;
            case State.Death:
                // Death handled once, no update needed
                break;
        }
    }
}
```

这段代码在只有 4 个状态时勉强可用，但当我们讨论生产级游戏 AI 时，它会暴露出几个 Unity 特有的问题：

**问题 1: `Update()` tick 爆炸。** 每一个 `Update()` 调用都要执行整个 `switch` 块，无论当前状态是什么。当状态增加到 8 个、12 个时，每个 `case` 分支内部又会嵌着条件判断，`Update()` 函数最终变成 300 行的巨型方法。后续任何修改都需要在层层嵌套中找到正确的分支点——每改一处都可能引入 bug。

**问题 2: 没有进入/退出语义。** 上面的代码直接修改 `currentState`，没有任何回调通知"刚刚进入了 Attack 状态"或"即将离开 Patrol 状态"。这意味着状态初始化和清理逻辑必须散布在状态切换之前的代码中。比如进入 Chase 要播放警觉动画、将 NavMeshAgent speed 设为 chaseSpeed；切换到 Patrol 又要恢复 patrolSpeed。这些逻辑写在各自 `case` 块的开头还是转移到之前的行的末尾？没有统一入口，代码很快就变得不一致。

**问题 3: 无法在 Inspector 中配置。** 上面的 FSM 完全是硬编码的。策划想让"巡逻范围从 10 米改成 15 米"，程序必须改代码。想让"这个敌人用巡逻 A，那个敌人用巡逻 B"，代码开始出现一堆 `bool usePatrolVariantB` 的配置字段——这本质上是把状态信息重新编码成了条件标志。

**问题 4: MonoBehaviour 生命周期交互缺失。** Unity 的对象有 `OnEnable()`/`OnDisable()`/`OnDestroy()` 生命周期回调——当 GameObject 被 (de)activate 或销毁时，这些回调保证被调用。一个设计良好的 FSM 应该利用这些回调来进行状态资源的初始化和释放，而不是把所有逻辑都塞在 `Update()` 里靠 `if (firstFrameOfState)` 判断。

**问题 5: 不可组合。** 每个敌人的 FSM 是单体的 `MonoBehaviour`。你想让两个不同类型的敌人共享"Chase"行为？只能复制粘贴代码。

### Unity 中三种 FSM 实现路径

在 Unity 生态中，根据项目规模和团队结构，有三种主要的 FSM 实现路径：

| 方案 | 复杂度 | 适用规模 | 核心思想 |
|------|--------|---------|----------|
| **Enum + Switch (简单 FSM)** | 低 | 5 个状态以内的小型敌人、UI 流程 | 在一个 MonoBehaviour 中通过 `switch` 分发状态更新 |
| **State Pattern (经典状态模式)** | 中 | 5-15 个状态的中型系统、角色控制器 | 每个状态是一个实现了 `IState` 接口的独立类，状态机控制器持有当前状态引用 |
| **ScriptableObject FSM (工业级)** | 高 | 15+ 状态、跨项目复用、策划可配置的大型系统 | 状态和转移都是 `ScriptableObject` 资产，运行时由轻量 `MonoBehaviour` Runner 驱动 |

这三种路径不是互斥的——它们在同一个项目中可以共存。一个简单的拾取物可能用 enum+switch，一个 Boss 可能用 ScriptableObject FSM，而主角控制器可能用 State Pattern。

### Enum + Switch 的定位

Enum + Switch 不是"坏的"方案——它是**最快启动**的方案。当你的需求明确且状态数 ≤5 时，直接写 switch 没有任何问题。其优点：

- **零抽象开销**：没有接口调用、没有虚函数分发、没有额外对象分配
- **易读**：所有逻辑在一个文件里，新人可以直接看懂
- **调试直接**：在 `switch` 行打断点，一眼看到当前状态

其痛点出现在状态数 ≥6 时：代码行数爆炸、状态切换逻辑分散、无法复用。

**实践经验**：如果 enum+switch 的 `Update()` 超过 100 行，就应该考虑升级到 State Pattern。

### State Pattern：抽象状态基类

State Pattern 的核心是将每个状态封装为一个实现了统一接口的独立类。在 C# 中，这个接口通常定义为：

```csharp
public interface IState
{
    void Enter();           // 首次进入状态时调用一次
    void Update();          // 每帧由状态机调用
    void FixedUpdate();     // 每物理帧由状态机调用（可选）
    void Exit();            // 离开状态时调用一次
}
```

状态机控制器 (`StateMachine`) 持有当前状态的引用，并在每帧委托给当前状态对象：

```csharp
public class StateMachine
{
    private IState _currentState;

    public void ChangeState(IState newState)
    {
        _currentState?.Exit();
        _currentState = newState;
        _currentState?.Enter();
    }

    public void Update() => _currentState?.Update();
    public void FixedUpdate() => _currentState?.FixedUpdate();
}
```

状态类通过持有对宿主 `MonoBehaviour`（或 `StateMachine` 自身）的引用来访问 Unity API（`transform`、`NavMeshAgent`、`Animator` 等）：

```csharp
public class PatrolState : IState
{
    private readonly EnemyAI _owner;
    private readonly NavMeshAgent _agent;

    public PatrolState(EnemyAI owner)
    {
        _owner = owner;
        _agent = owner.GetComponent<NavMeshAgent>();
    }

    public void Enter()
    {
        _agent.speed = _owner.patrolSpeed;
        _owner.animator.SetBool("IsPatrolling", true);
    }

    public void Update()
    {
        // Patrol logic here
    }

    public void Exit()
    {
        _owner.animator.SetBool("IsPatrolling", false);
    }

    public void FixedUpdate() { }
}
```

**State Pattern 的关键设计决策**：

1. **IState 是接口还是抽象类？** 如果每个状态都需要持有 `owner` 引用，可以用抽象基类 `StateBase` 包含 `protected readonly EnemyAI owner;` 构造函数注入，避免每个状态类重复写注入代码。
2. **状态对象是 new 出来的还是缓存的？** 避免在状态切换时 `new PatrolState()`——这会在每次状态切换时产生 GC 分配。应该在初始化时预创建所有状态对象并缓存：
   ```csharp
   _patrolState = new PatrolState(this);
   _chaseState = new ChaseState(this);
   // ...
   ```
3. **状态间如何通信？** 状态切换的触发条件由状态自身判断还是由外部判断？两种方式：
   - **状态自己判断**（`Update()` 方法返回下一个状态或 null）——简单直接，但状态类之间需要相互引用。
   - **外部仲裁**（状态机持有所有转移规则）——解耦，但需要额外的转移规则数据结构。

4. **与 MonoBehaviour 生命周期的交互**：`Enter()` 和 `Exit()` 可以映射到 `OnEnable()`/`OnDisable()` 语义——当宿主 GameObject 被禁用时，状态机应调用 `Exit()`；重新激活时调用 `Enter()`。如果不做这个映射，暂停再恢复可能导致状态不同步。

### ScriptableObject FSM：工业标准方案

ScriptableObject FSM 是目前 Unity 游戏工业的主流方案，被大量 AAA 和独立游戏项目使用。它的核心思想是将 FSM 的**定义**（有哪些状态、状态间如何转移）从**执行**（运行时驱动状态切换的 MonoBehaviour）中分离出来。

**架构分层**：

```
┌─────────────────────────────────────┐
│  ScriptableObject 资产层 (设计时)     │
│  ├─ StateSO: 状态定义                │
│  │   └─ Actions: 状态中的行为列表     │
│  ├─ TransitionSO: 转移定义           │
│  │   └─ Decision: 转移条件评估        │
│  └─ Action/Decision 子 SO            │
│      ├─ PatrolAction                 │
│      ├─ ChaseAction                  │
│      ├─ InRangeDecision              │
│      └─ HealthZeroDecision           │
└─────────────────────────────────────┘
            ↓  运行时读取
┌─────────────────────────────────────┐
│  MonoBehaviour 运行时层              │
│  ├─ StateMachineRunner: 驱动状态更新  │
│  └─ EnemyController: 持有数据（血量等）│
└─────────────────────────────────────┘
```

**为什么 ScriptableObject？**

1. **策划可配置**：策划在 Inspector 中拖拽 StateSO 资产来拼装 AI 行为，不需要碰代码。
2. **资产化复用**：一个 `ChaseState.asset` 可以被多个敌人 Prefab 引用，修改一处即全局生效。
3. **版本控制友好**：`.asset` 文件是 Unity 序列化的 YAML，Git 可 diff、可 merge。
4. **热重载安全**：ScriptableObject 在 Domain Reload 后仍然保持引用，不会丢失状态定义（运行时状态数据需要在 MonoBehaviour 上处理）。

**ScriptableObject FSM 的核心类型**：

```csharp
// StateSO.cs — 状态资产
[CreateAssetMenu(menuName = "FSM/State")]
public class StateSO : ScriptableObject
{
    public StateActionSO[] actions;          // 状态激活时执行的持续行为
    public TransitionSO[] transitions;       // 从本状态出发的所有转移
    public Color sceneGizmoColor = Color.gray; // 编辑器可视化颜色
}

// TransitionSO.cs — 转移资产
[CreateAssetMenu(menuName = "FSM/Transition")]
public class TransitionSO : ScriptableObject
{
    public DecisionSO decision;              // 转移条件（返回 true/false）
    public StateSO trueState;               // 条件满足时移入的状态
    public StateSO falseState;              // 条件不满足时的状态（对反向转移有用）
}

// StateMachineRunner.cs — 运行时驱动器
public class StateMachineRunner : MonoBehaviour
{
    [SerializeField] private StateSO _currentState;
    [SerializeField] private StateSO _remainState; // 默认"保持当前状态"

    private void Start()
    {
        // 进入初始状态的 actions
        foreach (var action in _currentState.actions)
            action.OnStateEnter(this);
    }

    private void Update()
    {
        // 1. 执行当前状态的 actions
        foreach (var action in _currentState.actions)
            action.OnStateUpdate(this);

        // 2. 评估转移条件
        foreach (var transition in _currentState.transitions)
        {
            if (transition.decision.Decide(this))
            {
                TransitionTo(transition.trueState);
                break; // 只取第一个满足条件的转移
            }
        }
    }

    public void TransitionTo(StateSO nextState)
    {
        // Exit current
        foreach (var action in _currentState.actions)
            action.OnStateExit(this);

        // Switch
        _currentState = nextState;

        // Enter next
        foreach (var action in _currentState.actions)
            action.OnStateEnter(this);
    }
}
```

注意这里的一个重要设计选择：**Action 和 Decision 是进一步抽象的 ScriptableObject**，而不是直接在 State 里写死逻辑：

```csharp
// 行为 Action 的抽象基类
public abstract class StateActionSO : ScriptableObject
{
    public abstract void OnStateEnter(StateMachineRunner runner);
    public abstract void OnStateUpdate(StateMachineRunner runner);
    public abstract void OnStateExit(StateMachineRunner runner);
}

// 决策 Decision 的抽象基类
public abstract class DecisionSO : ScriptableObject
{
    public abstract bool Decide(StateMachineRunner runner);
}
```

这样每种具体的 Action（`ChaseAction`、`PatrolAction`、`AttackAction`）和 Decision（`InRangeDecision`、`HealthBelowDecision`、`TimerDecision`）都是可以独立创建和组合的 ScriptableObject 资产。策划可以在 Inspector 中为每个状态拖入不同的 Action 组合。

### Update vs FixedUpdate：状态切换放到哪里？

Unity 提供三个主要的更新回调：

| 回调 | 频率 | 用途 |
|------|------|------|
| `Update()` | 每渲染帧 | 大部分游戏逻辑、输入检测、AI 感知 |
| `FixedUpdate()` | 固定物理步长（默认 0.02s） | 物理相关操作、Rigidbody 运动 |
| `LateUpdate()` | Update 之后、渲染之前 | 摄像机跟随、动画后处理 |

**FSM 的转移评估应该放在 `Update()` 还是 `FixedUpdate()`？**

**原则**：感知相关逻辑（检测玩家距离、视线）放在 `Update()`——因为这些依赖于渲染帧的 Transform 位置；物理相关逻辑（NavMeshAgent 导航、Rigidbody 移动）放在 `FixedUpdate()`——因为 Unity 的物理引擎在 `FixedUpdate()` 中更新。

实践中，最常见的做法是：
- **转移评估**和**感知逻辑**在 `Update()` 中处理
- **状态更新**中涉及物理的操作（如 `agent.SetDestination()`）可以放在 `Update()` 中调用（NavMeshAgent 内部会处理），但如果状态更新是在 `FixedUpdate()` 中驱动 Rigidbody 移动，则对应部分的转移逻辑也应该在 `FixedUpdate()` 中进行

**避免在两个时机都评估转移——会出现同一帧切换两次状态的 bug。**

### 方案对比总结

| 维度 | Enum + Switch | State Pattern | ScriptableObject FSM |
|------|--------------|---------------|---------------------|
| 代码量 | 最少（一个文件） | 中等（每个状态一个类） | 多（多个 SO 类型） |
| 状态数上限 | ~5 | ~15 | 理论上无限 |
| 可配置性 | 无（硬编码） | 有限（通过 MonoBehaviour 的 public 字段） | 完整（Inspector 拖拽配置） |
| 策划友好度 | ★☆☆☆☆ | ★★☆☆☆ | ★★★★★ |
| 性能 | 最快（零抽象） | 快（接口虚调用） | 中等（多次虚调用，但通常不是瓶颈） |
| 单元测试 | 困难（耦合 Unity API） | 较易（状态类可独立测试） | 较易（Decision/Action SO 可独立测试） |
| 复用性 | 无 | 状态类可跨对象复用 | 资产级复用，可跨项目 |
| 调试 | 简单直接 | 需要在状态类中打断点 | 需要理解 SO 引用链 |
| 适用项目规模 | 小型 / 原型 | 中型 / 独立游戏 | 中大型 / 商业项目 |

---

## 2. 代码示例

### 2.1 示例 A：Enum + Switch — 简单敌人 AI（含 NavMeshAgent）

这是一个完整的、可直接挂载到 GameObject 上的敌方 AI，使用 enum + switch 驱动 Patrol/Chase/Attack/Death 四态 FSM。依赖：挂载 `NavMeshAgent` 和 `Animator` 组件。

```csharp
// ============================================================
// EnemyAI_Simple.cs — Enum+Switch FSM with NavMeshAgent
// Attach to a GameObject with NavMeshAgent and Animator
// ============================================================
using UnityEngine;
using UnityEngine.AI;

public class EnemyAI_Simple : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private Transform _player;
    [SerializeField] private Transform[] _patrolPoints;
    [SerializeField] private Animator _animator;

    [Header("Settings")]
    [SerializeField] private float _detectRange = 20f;
    [SerializeField] private float _attackRange = 3f;
    [SerializeField] private float _loseRange = 25f;
    [SerializeField] private float _patrolSpeed = 2f;
    [SerializeField] private float _chaseSpeed = 5f;
    [SerializeField] private int _maxHealth = 100;
    [SerializeField] private float _attackCooldown = 1.5f;
    [SerializeField] private float _patrolWaitTime = 2f;

    private enum State { Patrol, Chase, Attack, Death }
    private State _currentState = State.Patrol;
    private NavMeshAgent _agent;
    private int _currentPatrolIndex;
    private float _patrolWaitTimer;
    private float _attackTimer;
    private int _currentHealth;

    // Animator parameter hashes — cached for performance
    private static readonly int IsMovingHash = Animator.StringToHash("IsMoving");
    private static readonly int AttackHash = Animator.StringToHash("Attack");
    private static readonly int DeathHash = Animator.StringToHash("Death");
    private static readonly int SpeedHash = Animator.StringToHash("Speed");

    private void Awake()
    {
        _agent = GetComponent<NavMeshAgent>();
        _currentHealth = _maxHealth;
    }

    private void Start()
    {
        // Start in Patrol state
        _agent.speed = _patrolSpeed;
        if (_patrolPoints.Length > 0)
            _agent.SetDestination(_patrolPoints[0].position);
    }

    private void Update()
    {
        // Check for state transitions first
        EvaluateTransitions();
        // Then execute current state logic
        UpdateCurrentState();
        // Update animator
        _animator.SetFloat(SpeedHash, _agent.velocity.magnitude);
    }

    private void EvaluateTransitions()
    {
        if (_currentState == State.Death) return;

        float dist = Vector3.Distance(transform.position, _player.position);

        if (_currentHealth <= 0)
        {
            ChangeState(State.Death);
            return;
        }

        switch (_currentState)
        {
            case State.Patrol:
                if (dist < _detectRange) ChangeState(State.Chase);
                break;

            case State.Chase:
                if (dist < _attackRange) ChangeState(State.Attack);
                else if (dist > _loseRange) ChangeState(State.Patrol);
                break;

            case State.Attack:
                if (dist > _attackRange * 1.5f) ChangeState(State.Chase);
                break;
        }
    }

    private void UpdateCurrentState()
    {
        switch (_currentState)
        {
            case State.Patrol: PatrolUpdate(); break;
            case State.Chase: ChaseUpdate(); break;
            case State.Attack: AttackUpdate(); break;
            // Death: no update needed
        }
    }

    private void ChangeState(State newState)
    {
        // Exit logic
        switch (_currentState)
        {
            case State.Chase:
                _animator.SetBool(IsMovingHash, false);
                break;
            case State.Attack:
                _animator.SetBool(AttackHash, false);
                break;
        }

        _currentState = newState;

        // Enter logic
        switch (_currentState)
        {
            case State.Patrol:
                _agent.speed = _patrolSpeed;
                _agent.isStopped = false;
                GoToNextPatrolPoint();
                break;

            case State.Chase:
                _agent.speed = _chaseSpeed;
                _agent.isStopped = false;
                _animator.SetBool(IsMovingHash, true);
                break;

            case State.Attack:
                _agent.isStopped = true;
                _attackTimer = 0f;
                break;

            case State.Death:
                _agent.isStopped = true;
                _agent.enabled = false;
                _animator.SetTrigger(DeathHash);
                // Disable collider so player can walk through corpse
                var col = GetComponent<Collider>();
                if (col) col.enabled = false;
                this.enabled = false; // Stop Update from being called
                break;
        }
    }

    // ── Patrol State Logic ──
    private void PatrolUpdate()
    {
        if (_patrolPoints.Length == 0) return;

        if (!_agent.pathPending && _agent.remainingDistance < 0.5f)
        {
            _patrolWaitTimer -= Time.deltaTime;
            _agent.isStopped = true;

            if (_patrolWaitTimer <= 0f)
            {
                _agent.isStopped = false;
                GoToNextPatrolPoint();
            }
        }
    }

    private void GoToNextPatrolPoint()
    {
        if (_patrolPoints.Length == 0) return;
        _agent.SetDestination(_patrolPoints[_currentPatrolIndex].position);
        _currentPatrolIndex = (_currentPatrolIndex + 1) % _patrolPoints.Length;
        _patrolWaitTimer = _patrolWaitTime;
    }

    // ── Chase State Logic ──
    private void ChaseUpdate()
    {
        _agent.SetDestination(_player.position);
        _animator.SetBool(IsMovingHash, _agent.velocity.magnitude > 0.1f);
    }

    // ── Attack State Logic ──
    private void AttackUpdate()
    {
        // Face the player
        Vector3 dir = (_player.position - transform.position).normalized;
        dir.y = 0;
        if (dir != Vector3.zero)
            transform.rotation = Quaternion.Slerp(
                transform.rotation, Quaternion.LookRotation(dir), Time.deltaTime * 10f);

        _attackTimer -= Time.deltaTime;
        if (_attackTimer <= 0f)
        {
            _attackTimer = _attackCooldown;
            _animator.SetTrigger(AttackHash);
            // Damage would be applied via animation event or direct call
        }
    }

    // ── Public damage API ──
    public void TakeDamage(int amount)
    {
        _currentHealth = Mathf.Max(0, _currentHealth - amount);
    }

    // ── Editor helper: visualize ranges ──
    private void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireSphere(transform.position, _detectRange);

        Gizmos.color = Color.red;
        Gizmos.DrawWireSphere(transform.position, _attackRange);

        if (_patrolPoints != null)
        {
            Gizmos.color = Color.green;
            foreach (var pt in _patrolPoints)
                if (pt) Gizmos.DrawSphere(pt.position, 0.3f);
        }
    }
}
```

**关键设计点**：

1. **`ChangeState()` 统一入口**——这是最小的防御性实践，确保每次状态切换都经过 exit/enter 逻辑。注意里面又有两个 `switch`（exit 和 enter），这已经是 "switch 开始长胖" 的信号。
2. **Animator hash 缓存**——`Animator.StringToHash()` 在静态字段中只计算一次，避免每帧字符串哈希。
3. **Death 状态直接禁用脚本**——`this.enabled = false` 阻止后续 `Update()` 调用，比在 `Update()` 开头检查 `if (isDead) return;` 更干净。
4. **转移优先于更新**——`EvaluateTransitions()` 在 `UpdateCurrentState()` 之前调用，保证本帧使用正确的状态。

**这个方案的硬伤**：当你想加一个 `Flee` 状态（血量低于 30% 时逃跑）时，需要在 4 个地方修改代码：枚举定义、`EvaluateTransitions` 中为每个现有状态添加判断、`ChangeState` 的 exit 和 enter switch、以及一个新的 `FleeUpdate()` 方法。这是 `switch` 方案的扩展瓶颈。

---

### 2.2 示例 B：State Pattern — 接口抽象状态类

改用 State Pattern 后，每个状态是一个实现了 `IState` 的独立类。状态切换由统一的 `StateMachine` 控制器处理，宿主 `MonoBehaviour` 只需持有状态机和状态实例。

```csharp
// ============================================================
// IState.cs — The state interface
// ============================================================
public interface IState
{
    void Enter();
    void Update();
    void FixedUpdate();
    void Exit();
}
```

```csharp
// ============================================================
// StateMachine.cs — Universal state machine controller
// ============================================================
using System;
using UnityEngine;

public class StateMachine
{
    public IState CurrentState { get; private set; }
    public Type CurrentStateType => CurrentState?.GetType();

    // Event fired whenever state changes — useful for UI / debugging
    public event Action<IState, IState> OnStateChanged;

    public void ChangeState(IState newState)
    {
        if (newState == CurrentState) return;

        IState previousState = CurrentState;

        CurrentState?.Exit();
        CurrentState = newState;
        CurrentState?.Enter();

        OnStateChanged?.Invoke(previousState, CurrentState);
    }

    public void Update()
    {
        CurrentState?.Update();
    }

    public void FixedUpdate()
    {
        CurrentState?.FixedUpdate();
    }
}
```

```csharp
// ============================================================
// EnemyAI_StatePattern.cs — Enemy controller using State Pattern
// ============================================================
using UnityEngine;
using UnityEngine.AI;

public class EnemyAI_StatePattern : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private Transform _player;
    [SerializeField] private Transform[] _patrolPoints;
    [SerializeField] private Animator _animator;

    [Header("Settings")]
    [SerializeField] private float _detectRange = 20f;
    [SerializeField] private float _attackRange = 3f;
    [SerializeField] private float _loseRange = 25f;
    [SerializeField] private float _patrolSpeed = 2f;
    [SerializeField] private float _chaseSpeed = 5f;
    [SerializeField] private int _maxHealth = 100;
    [SerializeField] private float _attackCooldown = 1.5f;

    // Public properties — states access these via the owner reference
    public Transform Player => _player;
    public Transform[] PatrolPoints => _patrolPoints;
    public Animator Animator => _animator;
    public NavMeshAgent Agent { get; private set; }
    public float DetectRange => _detectRange;
    public float AttackRange => _attackRange;
    public float LoseRange => _loseRange;
    public float PatrolSpeed => _patrolSpeed;
    public float ChaseSpeed => _chaseSpeed;
    public float AttackCooldown => _attackCooldown;
    public int CurrentHealth { get; private set; }

    private StateMachine _stateMachine;

    // Cached state instances — created once, reused forever
    private PatrolState _patrolState;
    private ChaseState _chaseState;
    private AttackState _attackState;
    private DeathState _deathState;

    private void Awake()
    {
        Agent = GetComponent<NavMeshAgent>();
        CurrentHealth = _maxHealth;
        _stateMachine = new StateMachine();

        // Pre-create all states
        _patrolState = new PatrolState(this);
        _chaseState = new ChaseState(this);
        _attackState = new AttackState(this);
        _deathState = new DeathState(this);
    }

    private void Start()
    {
        _stateMachine.ChangeState(_patrolState);
    }

    private void Update()
    {
        _stateMachine.Update();
    }

    private void FixedUpdate()
    {
        _stateMachine.FixedUpdate();
    }

    public void TakeDamage(int amount)
    {
        CurrentHealth = Mathf.Max(0, CurrentHealth - amount);
    }

    private void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireSphere(transform.position, _detectRange);
        Gizmos.color = Color.red;
        Gizmos.DrawWireSphere(transform.position, _attackRange);
    }
}
```

```csharp
// ============================================================
// PatrolState.cs — Patrol state implementation
// ============================================================
using UnityEngine;

public class PatrolState : IState
{
    private readonly EnemyAI_StatePattern _owner;
    private readonly NavMeshAgent _agent;
    private readonly Transform[] _patrolPoints;
    private int _currentIndex;
    private float _waitTimer;

    public PatrolState(EnemyAI_StatePattern owner)
    {
        _owner = owner;
        _agent = owner.Agent;
        _patrolPoints = owner.PatrolPoints;
    }

    public void Enter()
    {
        _agent.speed = _owner.PatrolSpeed;
        _agent.isStopped = false;
        GoToNextPoint();
    }

    public void Update()
    {
        // ── Transition evaluation ──
        float dist = Vector3.Distance(_owner.transform.position, _owner.Player.position);

        if (_owner.CurrentHealth <= 0)
        {
            _owner.StateMachine.ChangeState(_owner.DeathState);
            return;
        }

        if (dist < _owner.DetectRange)
        {
            _owner.StateMachine.ChangeState(_owner.ChaseState);
            return;
        }

        // ── Behavior ──
        if (_patrolPoints.Length == 0) return;

        if (!_agent.pathPending && _agent.remainingDistance < 0.5f)
        {
            _waitTimer -= Time.deltaTime;
            _agent.isStopped = true;
            if (_waitTimer <= 0f)
            {
                _agent.isStopped = false;
                GoToNextPoint();
            }
        }
    }

    public void FixedUpdate() { }

    public void Exit()
    {
        _agent.isStopped = false;
    }

    private void GoToNextPoint()
    {
        if (_patrolPoints.Length == 0) return;
        _agent.SetDestination(_patrolPoints[_currentIndex].position);
        _currentIndex = (_currentIndex + 1) % _patrolPoints.Length;
        _waitTimer = 2f;
    }

    // These are exposed via the owner — the state machine needs to pass them
    // through EnemyAI_StatePattern so concrete states can invoke transitions
    public EnemyAI_StatePattern Owner => _owner;
}

// Expose state references on the owner for states to access
public partial class EnemyAI_StatePattern
{
    public StateMachine StateMachine => _stateMachine;
    public PatrolState PatrolState => _patrolState;
    public ChaseState ChaseState => _chaseState;
    public AttackState AttackState => _attackState;
    public DeathState DeathState => _deathState;
}
```

```csharp
// ============================================================
// ChaseState.cs
// ============================================================
using UnityEngine;

public class ChaseState : IState
{
    private readonly EnemyAI_StatePattern _owner;
    private readonly NavMeshAgent _agent;
    private readonly Transform _player;
    private static readonly int IsMovingHash = Animator.StringToHash("IsMoving");

    public ChaseState(EnemyAI_StatePattern owner)
    {
        _owner = owner;
        _agent = owner.Agent;
        _player = owner.Player;
    }

    public void Enter()
    {
        _agent.speed = _owner.ChaseSpeed;
        _agent.isStopped = false;
    }

    public void Update()
    {
        float dist = Vector3.Distance(_owner.transform.position, _player.position);

        if (_owner.CurrentHealth <= 0)
        {
            _owner.StateMachine.ChangeState(_owner.DeathState);
            return;
        }

        if (dist < _owner.AttackRange)
        {
            _owner.StateMachine.ChangeState(_owner.AttackState);
            return;
        }

        if (dist > _owner.LoseRange)
        {
            _owner.StateMachine.ChangeState(_owner.PatrolState);
            return;
        }

        _agent.SetDestination(_player.position);
        _owner.Animator.SetBool(IsMovingHash, _agent.velocity.magnitude > 0.1f);
    }

    public void FixedUpdate() { }

    public void Exit()
    {
        _owner.Animator.SetBool(IsMovingHash, false);
    }
}
```

```csharp
// ============================================================
// AttackState.cs
// ============================================================
using UnityEngine;

public class AttackState : IState
{
    private readonly EnemyAI_StatePattern _owner;
    private readonly NavMeshAgent _agent;
    private readonly Transform _player;
    private readonly Animator _animator;
    private float _attackTimer;
    private static readonly int AttackHash = Animator.StringToHash("Attack");

    public AttackState(EnemyAI_StatePattern owner)
    {
        _owner = owner;
        _agent = owner.Agent;
        _player = owner.Player;
        _animator = owner.Animator;
    }

    public void Enter()
    {
        _agent.isStopped = true;
        _attackTimer = 0f;
    }

    public void Update()
    {
        float dist = Vector3.Distance(_owner.transform.position, _player.position);

        if (_owner.CurrentHealth <= 0)
        {
            _owner.StateMachine.ChangeState(_owner.DeathState);
            return;
        }

        if (dist > _owner.AttackRange * 1.5f)
        {
            _owner.StateMachine.ChangeState(_owner.ChaseState);
            return;
        }

        // Face the player
        Vector3 dir = (_player.position - _owner.transform.position).normalized;
        dir.y = 0;
        if (dir != Vector3.zero)
            _owner.transform.rotation = Quaternion.Slerp(
                _owner.transform.rotation, Quaternion.LookRotation(dir), Time.deltaTime * 10f);

        _attackTimer -= Time.deltaTime;
        if (_attackTimer <= 0f)
        {
            _attackTimer = _owner.AttackCooldown;
            _animator.SetTrigger(AttackHash);
        }
    }

    public void FixedUpdate() { }

    public void Exit() { }
}
```

```csharp
// ============================================================
// DeathState.cs
// ============================================================
using UnityEngine;

public class DeathState : IState
{
    private readonly EnemyAI_StatePattern _owner;
    private static readonly int DeathHash = Animator.StringToHash("Death");

    public DeathState(EnemyAI_StatePattern owner)
    {
        _owner = owner;
    }

    public void Enter()
    {
        var agent = _owner.Agent;
        agent.isStopped = true;
        agent.enabled = false;

        _owner.Animator.SetTrigger(DeathHash);

        var col = _owner.GetComponent<Collider>();
        if (col) col.enabled = false;

        _owner.enabled = false;
    }

    public void Update() { }
    public void FixedUpdate() { }
    public void Exit() { }
}
```

**State Pattern 的改进**：

- 每个状态是独立的类，可以独立测试和修改，不会影响其他状态
- 新加状态只需新建一个类 + 在 `Awake()` 中实例化，不需修改已有状态代码
- `ChangeState()` 统一处理 Exit/Enter 顺序，不会遗漏
- 状态类之间通过构造函数注入获得所需引用，显式声明依赖

**仍然存在的问题**：

- 状态间的转移条件仍然硬编码在各状态的 `Update()` 中
- 策划无法在不改代码的情况下修改行为逻辑
- 状态和敌人类型是紧耦合的——如果一个新的敌人只需要 Patrol 和 Chase 但没有 Attack，你需要写一组新的状态类

---

### 2.3 示例 C：ScriptableObject FSM — 工业标准方案

这是最完整的实现，也是你应该在面试和实际项目中使用的方法。我们将 FSM 的定义完全资产化。

```csharp
// ============================================================
// StateActionSO.cs — Abstract base for state actions
// ============================================================
using UnityEngine;

public abstract class StateActionSO : ScriptableObject
{
    /// <summary>Called when the state is entered.</summary>
    public abstract void OnStateEnter(StateMachineRunner runner);

    /// <summary>Called every frame while the state is active.</summary>
    public abstract void OnStateUpdate(StateMachineRunner runner);

    /// <summary>Called when the state is exited.</summary>
    public abstract void OnStateExit(StateMachineRunner runner);
}
```

```csharp
// ============================================================
// DecisionSO.cs — Abstract base for transition decisions
// ============================================================
using UnityEngine;

public abstract class DecisionSO : ScriptableObject
{
    /// <summary>
    /// Evaluate the condition for the given runner.
    /// Returns true if the transition should be taken.
    /// </summary>
    public abstract bool Decide(StateMachineRunner runner);
}
```

```csharp
// ============================================================
// StateSO.cs — State asset definition
// ============================================================
using UnityEngine;

[CreateAssetMenu(menuName = "FSM/State")]
public class StateSO : ScriptableObject
{
    [Tooltip("Actions executed while this state is active")]
    public StateActionSO[] actions;

    [Tooltip("Transitions evaluated in order — first true match wins")]
    public TransitionItem[] transitions;

    [Tooltip("Color used in editor debugging / gizmos")]
    public Color sceneGizmoColor = Color.gray;

    /// <summary>
    /// Evaluate all transitions. Returns the first matching next state,
    /// or null if no transition condition is met.
    /// </summary>
    public StateSO EvaluateTransitions(StateMachineRunner runner)
    {
        foreach (var item in transitions)
        {
            if (item.decision.Decide(runner))
                return item.trueState;
        }
        return null;
    }
}

[System.Serializable]
public struct TransitionItem
{
    [Tooltip("The decision that triggers this transition")]
    public DecisionSO decision;

    [Tooltip("Target state when the decision returns true")]
    public StateSO trueState;
}
```

```csharp
// ============================================================
// StateMachineRunner.cs — Runtime driver MonoBehaviour
// ============================================================
using UnityEngine;
using UnityEngine.Events;

public class StateMachineRunner : MonoBehaviour
{
    [Header("Configuration")]
    [SerializeField] private StateSO _initialState;
    [SerializeField] private bool _runOnStart = true;

    [Header("Debug")]
    [SerializeField] private StateSO _currentState;
    [SerializeField] private bool _logTransitions;

    // Events for external systems to hook into
    public UnityEvent<StateSO, StateSO> OnStateChanged;

    public StateSO CurrentState => _currentState;

    private void Start()
    {
        if (_runOnStart && _initialState != null)
            TransitionTo(_initialState);
    }

    private void Update()
    {
        if (_currentState == null) return;

        // STEP 1: Execute current state actions
        foreach (var action in _currentState.actions)
        {
            if (action != null)
                action.OnStateUpdate(this);
        }

        // STEP 2: Evaluate transitions — only one transition per frame
        StateSO nextState = _currentState.EvaluateTransitions(this);
        if (nextState != null)
            TransitionTo(nextState);
    }

    public void TransitionTo(StateSO nextState)
    {
        if (nextState == null) return;
        if (nextState == _currentState) return;

        StateSO previousState = _currentState;

        // Exit current state
        if (_currentState != null)
        {
            foreach (var action in _currentState.actions)
            {
                if (action != null)
                    action.OnStateExit(this);
            }
        }

        // Switch
        _currentState = nextState;

        // Enter new state
        foreach (var action in _currentState.actions)
        {
            if (action != null)
                action.OnStateEnter(this);
        }

        if (_logTransitions)
            Debug.Log($"[FSM] {previousState?.name ?? "null"} → {nextState.name}");

        OnStateChanged?.Invoke(previousState, _currentState);
    }

    /// <summary>Force a specific state regardless of transitions.</summary>
    public void ForceState(StateSO state)
    {
        if (state != null) TransitionTo(state);
    }
}
```

现在来看具体的 Action 和 Decision 实现。这些才是真正包含游戏逻辑的类：

```csharp
// ============================================================
// NavMeshMoveAction.cs — Handles NavMeshAgent movement
// ============================================================
using UnityEngine;

[CreateAssetMenu(menuName = "FSM/Actions/NavMesh Move")]
public class NavMeshMoveAction : StateActionSO
{
    [SerializeField] private float _speed = 3.5f;
    [SerializeField] private bool _setDestinationOnEnter = true;
    [SerializeField] private TargetType _targetType = TargetType.CustomTransform;

    private enum TargetType { Player, PatrolPoints, CustomTransform }

    public override void OnStateEnter(StateMachineRunner runner)
    {
        var agent = runner.GetComponent<UnityEngine.AI.NavMeshAgent>();
        if (agent == null) return;

        agent.speed = _speed;
        agent.isStopped = false;

        if (_setDestinationOnEnter)
        {
            Vector3? destination = GetDestination(runner);
            if (destination.HasValue)
                agent.SetDestination(destination.Value);
        }
    }

    public override void OnStateUpdate(StateMachineRunner runner)
    {
        var agent = runner.GetComponent<UnityEngine.AI.NavMeshAgent>();
        if (agent == null) return;

        // Continuously update destination for dynamic targets
        if (_targetType == TargetType.Player)
        {
            Vector3? destination = GetDestination(runner);
            if (destination.HasValue)
                agent.SetDestination(destination.Value);
        }
    }

    public override void OnStateExit(StateMachineRunner runner)
    {
        var agent = runner.GetComponent<UnityEngine.AI.NavMeshAgent>();
        if (agent != null)
            agent.isStopped = true;
    }

    private Vector3? GetDestination(StateMachineRunner runner)
    {
        switch (_targetType)
        {
            case TargetType.Player:
                var player = GameObject.FindGameObjectWithTag("Player");
                return player ? player.transform.position : (Vector3?)null;

            case TargetType.PatrolPoints:
                // Patrol point handling would go here
                return runner.transform.position;

            default:
                return runner.transform.position;
        }
    }
}
```

```csharp
// ============================================================
// PlayAnimationAction.cs — Triggers animator parameters
// ============================================================
using UnityEngine;

[CreateAssetMenu(menuName = "FSM/Actions/Play Animation")]
public class PlayAnimationAction : StateActionSO
{
    [SerializeField] private string _enterTrigger;
    [SerializeField] private string _enterBoolName;
    [SerializeField] private bool _enterBoolValue;
    [SerializeField] private string _exitBoolName;
    [SerializeField] private bool _exitBoolValue;

    public override void OnStateEnter(StateMachineRunner runner)
    {
        var animator = runner.GetComponentInChildren<Animator>();
        if (animator == null) return;

        if (!string.IsNullOrEmpty(_enterTrigger))
            animator.SetTrigger(Animator.StringToHash(_enterTrigger));

        if (!string.IsNullOrEmpty(_enterBoolName))
            animator.SetBool(Animator.StringToHash(_enterBoolName), _enterBoolValue);
    }

    public override void OnStateUpdate(StateMachineRunner runner)
    {
        // Animation is driven by trigger/bool, no per-frame update needed
    }

    public override void OnStateExit(StateMachineRunner runner)
    {
        var animator = runner.GetComponentInChildren<Animator>();
        if (animator == null) return;

        if (!string.IsNullOrEmpty(_exitBoolName))
            animator.SetBool(Animator.StringToHash(_exitBoolName), _exitBoolValue);
    }
}
```

```csharp
// ============================================================
// LookAtAction.cs — Rotates toward a target
// ============================================================
using UnityEngine;

[CreateAssetMenu(menuName = "FSM/Actions/Look At")]
public class LookAtAction : StateActionSO
{
    [SerializeField] private string _targetTag = "Player";
    [SerializeField] private float _rotationSpeed = 10f;

    public override void OnStateEnter(StateMachineRunner runner) { }

    public override void OnStateUpdate(StateMachineRunner runner)
    {
        var target = GameObject.FindGameObjectWithTag(_targetTag);
        if (target == null) return;

        Vector3 dir = (target.transform.position - runner.transform.position).normalized;
        dir.y = 0;
        if (dir != Vector3.zero)
        {
            var targetRot = Quaternion.LookRotation(dir);
            runner.transform.rotation = Quaternion.Slerp(
                runner.transform.rotation, targetRot, Time.deltaTime * _rotationSpeed);
        }
    }

    public override void OnStateExit(StateMachineRunner runner) { }
}
```

```csharp
// ============================================================
// DistanceDecision.cs — Condition: is target within range?
// ============================================================
using UnityEngine;

[CreateAssetMenu(menuName = "FSM/Decisions/Distance")]
public class DistanceDecision : DecisionSO
{
    [SerializeField] private string _targetTag = "Player";
    [SerializeField] private float _range = 10f;
    [SerializeField] private CompareMode _compare = CompareMode.LessThan;

    private enum CompareMode { LessThan, GreaterThan }

    public override bool Decide(StateMachineRunner runner)
    {
        var target = GameObject.FindGameObjectWithTag(_targetTag);
        if (target == null) return false;

        float dist = Vector3.Distance(runner.transform.position, target.transform.position);

        return _compare switch
        {
            CompareMode.LessThan => dist < _range,
            CompareMode.GreaterThan => dist > _range,
            _ => false
        };
    }
}
```

```csharp
// ============================================================
// HealthDecision.cs — Condition: health below threshold?
// ============================================================
using UnityEngine;

[CreateAssetMenu(menuName = "FSM/Decisions/Health")]
public class HealthDecision : DecisionSO
{
    [SerializeField] private float _threshold = 30f;
    [SerializeField] private CompareMode _compare = CompareMode.LessThan;

    private enum CompareMode { LessThan, GreaterThan }

    public override bool Decide(StateMachineRunner runner)
    {
        var health = runner.GetComponent<HealthComponent>();
        if (health == null) return false;

        return _compare switch
        {
            CompareMode.LessThan => health.CurrentHealth < _threshold,
            CompareMode.GreaterThan => health.CurrentHealth > _threshold,
            _ => false
        };
    }
}
```

```csharp
// ============================================================
// TimerDecision.cs — Condition: has N seconds elapsed?
// ============================================================
using UnityEngine;

[CreateAssetMenu(menuName = "FSM/Decisions/Timer")]
public class TimerDecision : DecisionSO
{
    [SerializeField] private float _duration = 3f;

    private float _elapsed;
    private bool _started;

    public override bool Decide(StateMachineRunner runner)
    {
        _elapsed += Time.deltaTime;
        if (_elapsed >= _duration)
        {
            _elapsed = 0f;
            return true;
        }
        return false;
    }

    // TimerDecision is stateful — be careful with SO lifetime.
    // In production, timer state should be on the runner, not the SO asset.
    // This simplified version works for single-instance use.
}
```

**在 Unity Editor 中的工作流**：

1. 创建 `StateSO` 资产：右键 → Create → FSM → State，命名为 `Enemy_Patrol`、`Enemy_Chase`、`Enemy_Attack`、`Enemy_Death`
2. 创建 `DecisionSO` 资产：右键 → Create → FSM → Decisions → Distance，配置为距离 < 10 米时返回 true
3. 创建 `StateActionSO` 资产：右键 → Create → FSM → Actions → NavMesh Move，配置速度 3.5，目标类型 Player
4. 在 StateSO 的 Inspector 中拖入 Actions 和 Transitions
5. 将 `StateMachineRunner` 挂载到敌人 Prefab 上，拖入 `_initialState` 为 `Enemy_Patrol`

**ScriptableObject FSM 的优势总结**：

- **数据驱动**：AI 行为定义全部是 `.asset` 文件，策划可以用 Unity Editor 直接配置，不需要编程
- **原子化复用**：一个 `ChaseState.asset` 可以被项目中所有敌人的 FSM 引用
- **版本控制**：`.asset` 是文本化的 YAML，Git 可 diff
- **逻辑与执行分离**：`StateMachineRunner` 只负责调度，不包含任何具体 AI 逻辑
- **可测试性**：`DecisionSO.Decide()` 和 `StateActionSO.OnStateUpdate()` 可以脱离 Unity 场景进行单元测试

---

## 3. 练习

### 练习 1：门的 FSM（State Pattern 方案）

**目标**：实现一个游戏中的自动门，使用 State Pattern（`IState` + `StateMachine`）。

**门的行为规格**：

```
Closed ──[playerNear]──→ Opening ──[animationComplete]──→ Open
  ↑                                                          │
  └──────── Closing ←──[animationComplete]←──[!playerNear]───┘
```

- `Closed`：门关闭，碰撞体激活，阻挡通行
- `Opening`：播放"开门"动画，动画结束后自动转移到 `Open`
- `Open`：门完全打开，碰撞体禁用，玩家可通行；当玩家离开触发区域后开始计时 2 秒，然后转移到 `Closing`
- `Closing`：播放"关门"动画，动画结束后自动转移到 `Closed`

**要求**：

1. 实现 `IState` 接口（或抽象基类）和 `StateMachine` 控制器
2. 实现四个状态类：`DoorClosedState`、`DoorOpeningState`、`DoorOpenState`、`DoorClosingState`
3. 使用 `OnTriggerEnter`/`OnTriggerExit` 检测玩家距离
4. 通过 `Animator.SetTrigger("Open")` / `Animator.SetTrigger("Close")` 控制动画
5. 通过 `AnimationEvents` 或等待动画时长来完成 `animationComplete` 判断
6. 在 `OnDrawGizmos` 中可视化当前状态名称和触发区域

**提示**：在 `DoorOpeningState.Enter()` 中触发动画，在 `DoorOpeningState.Update()` 中检查动画是否播放完毕（`Animator.GetCurrentAnimatorStateInfo(0).normalizedTime >= 1f`），确认完毕后调用状态机切换。

---

### 练习 2：重构为 ScriptableObject FSM

**目标**：将练习 1 中的门 FSM 重构为 ScriptableObject 方案。

**要求**：

1. 创建 `StateSO` 资产分别对应四个门状态
2. 为 `Opening`/`Closing` 创建 `PlayAnimationAction`（触发 Animator 触发器）
3. 为 `Closed`/`Open` 创建 `SetColliderAction`（控制 Collider 的启用/禁用）
4. 创建 `PlayerInRangeDecision` 和 `AnimationCompleteDecision` 两种 `DecisionSO`
5. 在 `Door` Prefab 上挂载 `StateMachineRunner`，配置完整的 FSM 资产引用

**思考题**：对比练习 1 和练习 2 的开发和调试体验。ScriptableObject 方案中，如果策划把 `Door_Open` 状态错误地连回了 `Door_Closed`（跳过了关门动画），你如何从工具层面防止这种错误？

---

### 练习 3（可选）：角色武器状态系统

**目标**：使用 ScriptableObject FSM 实现一个游戏角色的武器状态系统。

**状态规格**：

```
          ┌──────────┐
          │ Unarmed  │
          └────┬─────┘
   [Press 1]   │   [Press 2]
       ┌───────┴───────┐
       ▼               ▼
┌──────────┐    ┌──────────┐
│  Melee   │    │  Ranged  │
└────┬─────┘    └────┬─────┘
     │  [Ammo=0]     │  [Press R]
     ▼               ▼
┌──────────┐    ┌──────────┐
│Reloading │    │Reloading │
└────┬─────┘    └────┬─────┘
     │ [timer=2s]    │ [timer=3s]
     └───────┬───────┘
             ▼
      (return to weapon state)
```

**要求**：

1. 创建 `EquipWeaponAction`：切换角色持有的武器模型（启用/禁用子 GameObject）
2. 创建 `ReloadAction`：播放装弹动画，2-3 秒后自动回到对应武器状态
3. 创建 `InputDecision`：检测玩家按键输入（1/2/R）
4. 创建 `AmmoDecision`：检测当前弹药量是否为 0
5. 在 Inspector 中通过拖拽不同的 StateSO/DecisionSO 资产来配置"近战角色"和"远程角色"两种 Prefab

**挑战**：Reloading 完成后需要"回到之前的武器状态"，但普通 FSM 没有状态记忆能力。你有两种解决方案：(a) 在 `StateMachineRunner` 上记录 `_lastWeaponState` 字段，Reloading 完成时手动跳转回去；(b) 给 Reloading 状态创建两个副本——`ReloadingFromMelee` 和 `ReloadingFromRanged`，各自连到正确的回退状态。讨论两种方案的优缺点。

---

## 4. 扩展阅读

### Unity 官方与社区资源

| 资源 | 说明 |
|------|------|
| [Unity Learn: Pluggable AI With Scriptable Objects](https://learn.unity.com/tutorial/pluggable-ai-with-scriptable-objects) | Unity 官方教程，演示 SO-based 可插拔 AI 架构。本教程的 ScriptableObject FSM 模式直接来源于此。**必读**。 |
| [Unite 2017: Game Architecture with Scriptable Objects](https://www.youtube.com/watch?v=raQ3iHhE_Kk) | Ryan Hipple 的经典演讲，奠定了 ScriptableObject 在 Unity 中作为数据容器的使用哲学。虽然不是专门讲 FSM 的，但理解这个演讲才能理解为什么 SO-based FSM 会流行。**强烈推荐**。 |
| [Unity Animator Controller 文档](https://docs.unity3d.com/Manual/class-AnimatorController.html) | Mecanim 的状态机系统。当你的 FSM 主要驱动动画时，Animator Controller 本身就是一个可视化的分层状态机。 |
| [State Machine behaviours (Unity)](https://docs.unity3d.com/ScriptReference/StateMachineBehaviour.html) | 当 AI 状态与动画状态高度重合时，可以直接在 Animator 的状态上挂载 `StateMachineBehaviour` 脚本来驱动 AI 逻辑。适合简单的敌人 AI。 |

### 书籍章节

| 书籍 | 章节 | 说明 |
|------|------|------|
| *Game Programming Patterns* (Robert Nystrom) | [Chapter 7: State](https://gameprogrammingpatterns.com/state.html) | 用 C++ 示例讲解状态模式在游戏中的应用。包含了 FSM + 状态栈（Pushdown Automata）的实现。可直接在线免费阅读。 |
| *Unity in Action* (Joseph Hocking, 3rd ed.) | Chapter 8: Creating Enemy AI | 在 Unity 中构建敌人 AI 的完整实战章节，包括 FSM 和 NavMesh 集成。 |
| *Learning C# by Developing Games with Unity* | Chapter on AI | 面向初学者的 FSM 实现。如果你需要 C# 语法的额外巩固，可以参考。 |

### Asset Store FSM 方案（仅供参考，非必须购买）

了解这些商业方案有助于你在面试中讨论"自研 vs 购买"的权衡：

| 插件 | 特点 |
|------|------|
| **Playmaker** | 可视化 FSM 编辑器。设计师可以直接创建和编辑状态机，不需要写代码。适合原型和设计师驱动的项目。缺点是性能和扩展性有限，复杂逻辑难以维护。 |
| **Node Canvas** | 同时支持 FSM 和行为树的可视化脚本工具。比 Playmaker 更强大，提供了更丰富的节点类型和调试工具。 |
| **Behavior Designer** | 以行为树为主，但包含 FSM 节点。社区活跃，文档完善。 |

**选型建议**：对于商业项目，如果团队中有专职技术策划或 AI 设计师，购买或自研可视化工具是合理的。如果团队以程序员为主，ScriptableObject FSM 方案在灵活性、性能和版本控制方面都优于第三方可视化工具，且无需额外学习成本。

---

## 常见陷阱

### 1. 混淆 Animator 状态机和代码 FSM

**症状**：Animator Controller 里有一套状态（Idle/Walk/Attack），代码里又写了一套状态（Patrol/Chase/Attack），两套状态的转移条件不同步。结果动画播着 Walk 但代码认为在 Attack。

**根因**：把动画状态机当作 AI 状态机使用，或者反过来。Animator 是**视觉呈现层**，代码 FSM 是**逻辑决策层**。两者应该分离——代码 FSM 做决策（什么时候攻击），Animator 做表现（攻击时播放什么动画）。代码 FSM 通过 `Animator.SetTrigger`/`SetBool` 驱动动画状态机，而不是让动画状态机反过来驱动 AI 逻辑。

**解法**：代码 FSM 是"源"，Animator 是"目标"。只在代码 FSM 的状态 Enter/Exit 中设置 Animator 参数，**永远不要**在 `StateMachineBehaviour.OnStateEnter` 中修改 AI 逻辑状态。

### 2. 每帧 `GameObject.Find` 或 `GetComponent`

**症状**：在 `Update()` 中调用 `GameObject.FindWithTag("Player")` 或 `GetComponent<NavMeshAgent>()`，导致每帧都有不必要的查找开销。

**根因**：不了解 Unity 的组件查找成本。`Find` 遍历整个场景层级，`GetComponent` 虽然快但也应避免在热路径中调用。

**解法**：在 `Awake()` 或 `Start()` 中缓存所有组件引用。对于 `Player` 这样的单例目标，在状态类构造函数或 `Enter` 中缓存，或者通过依赖注入传入。

```csharp
// ❌ WRONG — every frame
void Update() {
    var player = GameObject.FindGameObjectWithTag("Player");
    var agent = GetComponent<NavMeshAgent>();
    agent.SetDestination(player.transform.position);
}

// ✅ RIGHT — cached
private Transform _player;  // set in Awake or via serialized field
private NavMeshAgent _agent; // set in Awake

void Update() {
    _agent.SetDestination(_player.position);
}
```

### 3. ScriptableObject 中存储运行时状态

**症状**：在 `DecisionSO` 或 `StateActionSO` 中使用了实例字段来存储计时器、上一个位置等运行时数据。在 Editor 中 Play 后退出，这些数据残留在 SO 资产中；或者多个敌人共享同一个 SO 资产，导致互相干扰。

**根因**：`ScriptableObject` 是**资产**，在 Editor 中的修改会持久化。它**不是**一个安全的运行时状态容器。

**解法**：运行时状态数据必须存储在外部的 `MonoBehaviour` 上（通常是 `StateMachineRunner` 或敌人自身的组件）。SO 中的 `OnStateUpdate` 方法通过 `runner` 参数访问运行时数据：

```csharp
// ❌ WRONG — runtime state on ScriptableObject (shared by all instances!)
public class TimerDecision : DecisionSO
{
    private float _elapsed; // 💣 ALL enemies share this!

    public override bool Decide(StateMachineRunner runner)
    {
        _elapsed += Time.deltaTime;
        return _elapsed >= 3f;
    }
}

// ✅ RIGHT — runtime state on the runner
public class TimerDecision : DecisionSO
{
    // The runner provides a blackboard or state dictionary
    public override bool Decide(StateMachineRunner runner)
    {
        float elapsed = runner.GetState<float>("timer_elapsed");
        elapsed += Time.deltaTime;
        runner.SetState("timer_elapsed", elapsed);
        return elapsed >= 3f;
    }
}
```

### 4. `Update` vs `FixedUpdate` 中的转移时机

**症状**：在 `Update()` 中评估转移条件（检测玩家位置），但物理移动在 `FixedUpdate()` 中执行。敌人有时在视觉上还未到达目标位置时就被转移条件判定为"已到达"。

**根因**：`Update()` 和 `FixedUpdate()` 的调用频率不同。`Update()` 每帧跑一次（帧率波动），`FixedUpdate()` 固定频率跑。在 `Update()` 中读取的物理位置可能落后于实际物理状态。

**解法**：
- 如果是基于 Transform 位置的距离判断（大多数 AI 感知），放在 `Update()` 中——因为 Transform 的渲染位置在 `Update` 之后才会更新
- 如果是基于 Rigidbody 的运动状态，放在 `FixedUpdate()` 中
- **不要**在 `Update()` 和 `FixedUpdate()` 中同时评估转移——这会导致同一帧内的重复状态切换
- 折中方案：在 `FixedUpdate()` 中评估转移并缓存结果，在 `Update()` 中读取缓存并执行切换

### 5. Exit 回调中的 `null` 引用

**症状**：状态切换到 `Death` 时，`Death.Enter()` 中调用了 `Destroy(gameObject)` 或禁用了 `MonoBehaviour`，但 `StateMachine.Update()` 在后续帧仍然被调用（因为 `enabled = false` 只禁止当前脚本的 `Update`，如果 `StateMachine` 是独立的 C# 类而非 MonoBehaviour，则不受影响）。

**根因**：没有检查 `this == null` 或 GameObject 是否已销毁。

**解法**：Death 状态的 `Enter()` 除了禁用组件，还应该阻止状态的进一步更新：

```csharp
public void Enter()
{
    // ... disable physics, play animation ...
    _owner.enabled = false; // Stops Update on the owning MonoBehaviour
    
    // Also: make state transitions impossible
    _owner.StateMachine.ChangeState(null); // Or have a dedicated TerminalState
}
```

或者在 `StateMachine.Update()` 开头检查宿主是否仍存活：

```csharp
public void Update()
{
    if (_owner == null || !_owner.isActiveAndEnabled) return;
    CurrentState?.Update();
}
```

### 6. 状态类中的 GC 分配

**症状**：使用 Profiler 发现每帧有 GC.Alloc，追踪后发现是状态机的 `Update()` 路径中分配了临时对象。

**常见元凶**：
- 字符串拼接用于日志/调试
- `GetComponent<T>()` 在每帧调用
- Lambda 表达式捕获（在状态切换回调中）
- `foreach` 遍历某些 Unity 集合类型（`Transform` 枚举器有分配，`List<T>` 和数组没有）
- 装箱：把值类型传给接受 `object` 的参数

**解法**：
- 使用 `StringBuilder` 或不分配字符串的日志方式
- 缓存所有组件引用
- 避免在热路径中使用 lambda/闭包
- 用 `for` 替代 `foreach` 遍历 `IEnumerable`（特别是 `Transform`）
- 在 Editor 中用 Profiler 的 Deep Profile 模式定位具体分配点

### 7. ScriptableObject 的 `OnEnable` / `OnDisable` / `OnDestroy` 陷阱

**症状**：在 `StateActionSO` 中重写了 `OnEnable()` 来做初始化，但在运行时加载场景时被意外多次调用。

**根因**：`ScriptableObject` 也有类似 `MonoBehaviour` 的生命周期回调，但它们的行为不同——`OnEnable()` 在资产被加载到内存时调用（包括 Editor 中的 Domain Reload），`OnDisable()` 在资产被卸载时调用。这些回调在运行时不可靠。

**解法**：不要在 `ScriptableObject` 的生命周期回调中做运行时初始化。运行时初始化应该放在 `StateActionSO.OnStateEnter()`（当状态被激活时）、或依赖 `StateMachineRunner` 的 `Awake()`/`Start()` 回调。

