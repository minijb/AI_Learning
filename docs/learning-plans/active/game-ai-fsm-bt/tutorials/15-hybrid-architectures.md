---
title: "混合架构与 AI 系统设计"
updated: 2026-06-05
---

# 混合架构与 AI 系统设计

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 14-fsm-vs-bt

---

## 1. 概念讲解

### 为什么需要混合架构？

Tutorial 14 用一整章的篇幅比较了 FSM 和 BT，但这个问题的前提是"二选一"。真实游戏不在这个前提下运作——AI 系统从来不是单一范式。如果你打开任何 AAA 游戏的 AI 代码库，你不会看到一个"纯 BT"或"纯 FSM"的系统，你会看到**一个分层的、多范式协作的架构**。

三层分层是工业界经过 20 年迭代后收敛的模式：

```
┌─────────────────────────────────────────┐
│  High-Level: Decision Making            │
│  BT / GOAP / Utility AI                 │
│  "What should I do?"                    │
├─────────────────────────────────────────┤
│  Mid-Level: Behavior Execution          │
│  FSM / HSM / Pushdown                   │
│  "How do I do it?"                      │
├─────────────────────────────────────────┤
│  Low-Level: Animation & Motion          │
│  Animation State Machine / Motion Match │
│  "What does it look like?"              │
└─────────────────────────────────────────┘
```

**为什么不是一层**？每一层解决不同时间尺度和不同抽象级别的问题：

| 层级 | 时间尺度 | 抽象级别 | 典型工具 | 示例决策 |
|------|---------|---------|---------|---------|
| High | 秒~分钟 | 战术/战略 | BT, GOAP | "追击还是撤退？" |
| Mid | 100ms~秒 | 行为/动作 | FSM, HSM | "追击的子步骤：寻路→靠近→攻击" |
| Low | 帧~100ms | 动画/姿态 | Animator, Motion Matching | "奔跑动画以0.7速度混合 strafe 偏移动画" |

试着把三层塞进一个纯 BT：你会得到数百个节点，最深的叶子节点既要处理"敌人是否在视野内"（高层决策），又要处理"当前动画是否播放完毕"（低层反馈）。每帧从根遍历这棵巨树——性能上可行，但**认知上不可维护**。

试着把三层塞进一个平面 FSM：你会得到笛卡尔积爆炸——"在追击状态 + 右手持剑 + 左脚受伤 + 能量低于30% + 处于火海中"需要多少个组合状态？

**分层不是奢侈——是工程上的生存策略。**

### 常见分层模式

#### 模式 1: BT 驱动 FSM

最普遍的 AAA 模式。BT 在顶层做出战术决策，每个决策映射到一个 FSM 状态。

```
BT (top-level Selector):
├── Sequence "Combat"
│   ├── Condition: HasTarget
│   └── SetFSMState(Combat)       ← triggers FSM transition
├── Sequence "Investigate"
│   ├── Condition: HeardSound
│   └── SetFSMState(Investigate)
└── Sequence "Idle"
    └── SetFSMState(Idle)
```

BT 每帧重新评估，当条件变化时（如目标丢失），BT 选择不同的分支，触发 FSM 转移。**BT 管理"why"（为什么切换），FSM 管理"how"（如何执行）。**

关键设计决策：BT 节点是**即时触发转移**还是**等待当前 FSM 状态可中断**？两种设计各有场景：
- **即时转移**：战斗中发现血量过低 → 立即打断当前攻击动作，进入撤退。适合生存优先的场景。
- **延迟转移**：当前攻击动作的 Recovery 阶段完成前不响应转移请求。适合动画质量优先的场景（没有凭空消失的挥砍）。

UE5 的 StateTree 本质上就是这种模式的形式化——它混合了 BT 的条件选择和 FSM 的状态转移。

#### 模式 2: FSM 状态运行 BT 子树

反向模式。FSM 管理宏观状态（Idle / Combat / Dead），每个状态内部用 BT 子树做局部的条件决策。

```
FSM:
  Idle ──[spotted]──→ Combat ──[hp=0]──→ Dead

  Idle state → runs BT subtree "IdleBehaviors":
      Selector:
      ├── Sequence: HasWaypoint → Patrol
      └── Action: StandGuard

  Combat state → runs BT subtree "CombatBehaviors":
      Selector (priority-ordered):
      ├── Sequence: HealthLow → Flee
      ├── Sequence: EnemyClose → MeleeAttack
      ├── Sequence: HasAmmo → RangedAttack
      └── Action: MoveToEnemy
```

这种模式的优点：**FSM 的顶层状态提供行为分组**——你不需要在 BT 根节点反复检查"我死了吗？"因为 `Dead` 状态的 BT 子树根本就不包含 Combat 相关的节点。BT 子树更小、更专注、更快。

这在 Unreal 中特别常见：用枚举状态（AI 的 `BehaviorState`）决定运行哪棵 BT 子树，每个子树是独立的 `UBehaviorTree` 资产。

#### 模式 3: Blackboard 是共享总线

两个模式都依赖一个关键基础设施：**跨层 Blackboard**。

```
┌─────────────────────────────────────────┐
│          Shared Blackboard              │
│  TargetActor, MoveDestination,          │
│  CurrentWeapon, Health, Ammo,           │
│  AlertLevel, CoverPosition...           │
├────────────┬────────────┬───────────────┤
│  BT reads: │ FSM reads: │ Animator      │
│  Target    │ MoveDest   │ reads: Speed, │
│  Health    │ WeaponType │ Direction,    │
│            │            │ IsAttacking   │
└────────────┴────────────┴───────────────┘
```

Blackboard 的关键设计原则：
- **BT 写入，FSM 读取**：BT 决定 `MoveDestination`，FSM 的 `MoveTo` 状态读取并执行。
- **FSM 写入，BT 读取**：FSM 的 `Attack` 状态在执行过程中填充 `CurrentAttackPhase`，BT 的 Condition 节点读取它来判断是否允许中断。
- **Animator 只读不写**：动画层是纯粹的消费者——它读取高层决策的结果并渲染为视觉表现，但绝不回写 Blackboard（否则耦合方向反转，调试变噩梦）。

#### 模式 4: 事件总线

Blackboard 解决"状态共享"，但不适合"发生了什么"的瞬时通知。事件总线填补这个缺口：

```cpp
// FSM state transition → event
EventBus::Emit("AI.StateChanged", {.From = "Combat", .To = "Flee"});

// BT Condition node reacts
bool IsFleeing::Check(Blackboard& bb) {
    return bb.GetLastEvent("AI.StateChanged").To == "Flee";
}

// Animator layer subscribes
EventBus::Subscribe("AI.StateChanged", [](const EventData& data) {
    TriggerCrossfadeAnimation(data.From, data.To);
});
```

事件总线的设计原则：
- **单向为主**：高→低层用事件，低→高层用 Blackboard（因为事件是瞬时的，BT 每帧评估不能依赖"上帧发了什么事件"，应该轮询 Blackboard）。
- **类型安全**：使用强类型事件 ID（枚举或哈希），不使用字符串比较。
- **订阅者不修改事件**：事件是不可变数据包，订阅者只读。

### 架构模式

#### AI Controller 模式

将 AI 大脑从角色实体中分离：

```
Character (APawn / GameObject)
  ├── Mesh, Collider, Health, Inventory...
  └── pointer → AIController (brain)

AIController (owns AI logic, no visual)
  ├── BehaviorTree (or FSM root)
  ├── Blackboard
  ├── Perception (sight, hearing, damage events)
  └── Action Queue
```

**为什么要分离？**
- **热重载**：AI Controller 可以在运行时替换（切换行为模式），角色本身不重建。
- **多角色共享**：同一个 AI Controller 类可以被多种敌人复用（"近战小兵"和"远程小兵"共享决策逻辑，差异仅在 Blackboard 参数）。
- **网络复制**：AI Controller 运行在服务器端，角色在客户端被同步——AI 决策不需要同步到客户端，只需同步结果（位置、动画）。

UE 的 `AAIController` 和 Unity 的 `NavMeshAgent` + 自定义 `AIController` MonoBehaviour 都是这个模式的实例。

#### Sense / Think / Act 管道

这是游戏 AI 中最古老、最稳定的架构模式：

```
┌─────────┐     ┌─────────┐     ┌──────────────┐
│  Sense  │ ──→ │  Think  │ ──→ │     Act      │
│ (收集)  │     │ (决策)  │     │ (执行+动画)   │
└─────────┘     └─────────┘     └──────────────┘
     │               │                  │
     ▼               ▼                  ▼
Perception       BT / GOAP        Action Queue
System           / Utility AI      → FSM
                                   → Animation
```

**每帧不一定是 S→T→A 线性执行。** 很多引擎把 Sense 放在单独的更新频率中（如 UE 的 `UAISense` 有独立的 tick 间隔）。Think 也不一定是每帧——BT 每帧 tick，但 GOAP 可能每 500ms 才重新规划一次。Act 的 Action Queue 是帧级的消费者。

#### AI Command Queue（带优先级的缓冲动作队列）

这是连接 Think 层和 Act 层的关键组件：

```cpp
struct AICommand {
    EAICommandType Type;       // Move, Attack, UseItem, PlayEmote...
    float Priority;            // higher = more important
    float InterruptThreshold;  // commands below this priority can be preempted
    FVector TargetLocation;
    AActor* Target;
    float Timeout;             // auto-discard if not executed within this time
};
```

工作流程：
1. BT/GOAP 产生命令，以 `(Type, Priority)` 入队。
2. FSM 的当前状态从队首取命令（最高优先级）。
3. 如果新命令的优先级超过当前执行命令的 `InterruptThreshold`，当前命令被抢占，新命令立即执行。
4. 队列有最大长度（如 3-5），新的高优先级命令可以踢掉队尾的低优先级命令。

这个模式解决了 **BT 每帧重评估可能产生的"决策抖动"**——命令入队后除非被高优先级抢占，否则稳定执行到完成。

#### Subsumption（包容架构）启发式分层

Brooks 的包容架构虽然原意是机器人学，但它的核心理念在游戏 AI 中仍有生命力：**低层行为可以被高层行为抑制（subsume）**。

```
Layer 3: Combat tactics (suppresses Layer 1-2)
Layer 2: Navigation & obstacle avoidance (suppresses Layer 1)
Layer 1: Idle animation & ambient behavior (always running when not suppressed)
```

在游戏中实现方式不是 Brooks 的原始形式，而是一个**优先级抑制系统**：
- Layer 1 始终运行（如空闲动画循环）。
- 当 Layer 2 产生输出（如导航方向），它抑制 Layer 1 的输出。
- 当 Layer 3 产生输出（如闪避方向），它抑制 Layer 2 的输出。

Halo 系列在行为树底层大量使用这种"优先级覆盖"模式。

### 具体引擎架构

#### Unreal Engine 模式

```
AAIController (AI brain)
  ├── UAIPerceptionComponent
  │     ├── UAISense_Sight
  │     ├── UAISense_Hearing
  │     └── UAISense_Damage
  ├── UBehaviorTreeComponent
  │     └── UBehaviorTree asset
  │           ├── BTDecorator (conditions)
  │           ├── BTService (parallel ticks)
  │           └── BTTask (actions)
  │                 ├── BTTask_MoveTo
  │                 ├── BTTask_PlayAnimation
  │                 └── BTTask_RunBehavior (subtree)
  ├── UBlackboardComponent (shared data)
  └── UGameplayAbilitySystem (optional, for combat)

APawn (the body)
  ├── USkeletalMeshComponent
  ├── UCharacterMovementComponent
  └── Animation Blueprint
        └── State Machine (Locomotion → Idle/Walk/Run/Jump)
```

UE 的关键设计：
- **BT 不直接操作动画**：BTTask 通过修改 Blackboard 值（如 `MoveSpeed`）来影响动画蓝图，动画蓝图的状态机独立从 Blackboard 读取。
- **GameplayAbilitySystem 是独立层**：GAS 通过 GameplayTags 事件系统与 BT 通信——BT 触发 Ability（"Boss.Attack.Phase2"），Ability 执行结束后通过 GameplayTag 事件通知 BT。
- **BT 子树**：`BTTask_RunBehavior` 允许在任务节点中运行另一个 BT 资产，实现类似"FSM 状态运行 BT 子树"的模式。

#### Unity 模式

```
AIController (MonoBehaviour, the brain)
  ├── NavMeshAgent (pathfinding)
  ├── BehaviorTreeRunner (custom or Asset Store)
  │     └── BehaviorTree asset
  │           ├── Condition nodes
  │           └── Action nodes
  │                 ├── MoveTo (drive NavMeshAgent)
  │                 ├── PlayAnimation (set Animator params)
  │                 └── Attack (deal damage)
  ├── Blackboard (ScriptableObject or Dictionary)
  └── EventBus (C# events or custom)

GameObject (the body)
  ├── Animator
  │     └── AnimatorController
  │           └── State Machine (Idle/Walk/Attack/Death)
  ├── Collider
  └── HealthComponent
```

Unity 与 UE 的关键差异：
- Unity 没有内置的 BT 系统——需要自己实现或使用 Asset Store 方案（如 Behavior Designer、NodeCanvas）。这意味着**你有更多架构自由，但也需要自己做更多设计决策**。
- `Animator` 已经是一个完整的层次状态机——不要与 AI FSM 混淆。AI FSM 管理"做什么"，Animator 管理"怎么动"。两者通过 `Animator.SetFloat/SetBool/SetTrigger` 通信。
- NavMeshAgent 相当于 UE 的 `UCharacterMovementComponent` + `UNavigationSystem` 的简化版。BT 的 `MoveTo` 节点设置 `NavMeshAgent.destination`，由 Unity 物理引擎驱动实际移动。

#### 自定义引擎模式 (C++ 引擎 + Lua 行为)

```
C++ Layer (Performance-critical)
  ├── AI Manager (singleton, manages all AI entities)
  ├── BT Engine (tick, node evaluation, Blackboard)
  ├── Perception System (spatial queries, raycasts)
  ├── Pathfinding (NavMesh or grid-based)
  └── Lua VM binding (expose AI APIs)

Lua Layer (Designer-facing)
  ├── Behavior definitions (tree structures)
  ├── Node implementations (Lua callbacks)
  ├── Animation state table (FSM in Lua table)
  └── Event handlers (subscribe to C++ events)
```

这种模式常见于自研引擎（CD Projekt RED 的 REDengine、CryEngine 的 Lua AI、许多日本工作室的自研引擎）：

- **C++ 提供性能和基础设施**：BT 引擎的核心 tick 循环、Blackboard 的哈希表查找、感知系统的空间查询——这些都在 C++ 中，每帧执行数百个 AI 实体的开销可控。
- **Lua 提供迭代速度**：行为树的结构、节点逻辑、动画状态——这些由设计师通过 Lua 配置，修改后不需要重新编译 C++。
- **热重载是关键特性**：Lua 脚本可以在游戏运行时重新加载，设计师修改行为后立即看到效果。

关键设计点：
- **C++ 和 Lua 的边界要薄**：Lua 回调不应每帧分配大量临时对象。使用对象池或预先分配的 buffer。
- **Lua 只做决策，不做计算**：路径查询、可见性检测、物理碰撞都应该在 C++ 层完成并缓存到 Blackboard，Lua 只读取结果。
- **事件系统是桥梁**：C++ 层产生事件（`"DamageTaken"`, `"EnemySpotted"`），Lua 层订阅事件并更新行为。

### 状态传递：有状态 vs 无状态的混合

混合架构的一个核心设计问题是：**状态信息如何在层之间流动？**

#### 选项 A: BT 无状态 + FSM 有状态

BT 每帧从根重新评估（无状态），将决策结果写入 Blackboard。FSM 从 Blackboard 读取"应该做什么"并维护执行状态。

**优点**：BT 的灵活性完全保留——条件变化时立即切换决策。
**缺点**：BT 需要在 Blackboard 中编入足够的上下文让 FSM 能够"接续"上一个决策。例如，如果 BT 上一帧写入 `Attack`，这一帧因为某个瞬间条件不满足而写入 `Idle`，帧后又切回 `Attack`——FSM 应该从头开始攻击还是继续之前的攻击？需要在 Blackboard 中显式管理 `AttackProgress` 这样的恢复状态。

#### 选项 B: BT 有状态（通过 Running）+ FSM 无状态

BT 的 Action 节点通过返回 `Running` 来"记住"执行进度，FSM 的每个状态做最简单的"收到什么指令就执行什么"。

**优点**：FSM 的实现极度简单——每个状态是一个短小的行为片段。
**缺点**：BT 的"无状态"优势被削弱——`Running` 节点阻止了父 Selector 重新评估条件（除非使用 UE 的 Observer Aborts 或类似机制）。这正是 Tutorial 14 陷阱 3 讨论的问题。

#### 选项 C（推荐）: 分层有状态——每层管理自己的状态

每层只管理自己抽象级别的状态，不侵入其他层：

- **BT 层的状态**：当前激活的子树路径（隐式，通过 `Running` 节点）、短期目标（Blackboard: `CurrentGoal`）。
- **FSM 层的状态**：当前行为状态（`MoveTo`, `Attack`, `UseItem`）、行为子阶段（`Windup`, `Active`, `Recovery`）。
- **动画层的状态**：当前动画状态机的 active state、混合参数（速度、方向、姿态）。

每层通过定义良好的接口（Blackboard key 集合 + 事件类型集合）通信，但**不共享执行状态**。

### 团队工作流

混合架构的设计必须考虑**团队结构**——因为不同的层由不同角色维护：

| 角色 | 负责内容 | 工具需求 |
|------|---------|---------|
| **AI 程序员** | BT/FSM 运行时、Blackboard、感知系统、事件总线、AI Command Queue。构建框架，不定义具体行为。 | C++ IDE，性能分析器，调试可视化工具 |
| **AI 设计师** | 行为树结构、Blackboard 参数配置、FSM 状态定义（Lua 或编辑器）。定义"敌人如何行为"。 | 可视化 BT 编辑器、Lua 脚本编辑器、游戏内 AI 调试面板 |
| **动画师** | Animation Blueprint / Animator Controller、动画状态机、混合空间。定义"行为看起来什么样"。 | 动画编辑器、状态机可视化编辑器 |
| **关卡设计师** | AI 放置、巡逻路径、触发区域。定义"敌人在哪、何时出现"。 | 关卡编辑器、AI 放置工具 |

**工作流关键点**：
1. **AI 程序员交付框架 + 示例**：设计师不应从零开始写 BT——程序员提供一套经过测试的 BT 模板（"巡逻+追击+近战攻击"、"哨兵+远程攻击+呼叫增援"等），设计师基于模板修改参数和添加关卡特定行为。
2. **迭代瓶颈通常是设计师**：如果设计师每做一个修改都需要等待程序员的 C++ 编译，迭代速度被严重限制。这就是为什么 Lua 绑定如此重要——它消除了设计师对程序员的运行时依赖。
3. **动画师独立工作**：只要 Blackboard/Animator 参数约定稳定，动画师可以在不需要 AI 程序员参与的情况下迭代动画状态机。Animator 参数就是合约。
4. **调试工具是共享语言**：AI 调试面板（显示当前 BT 路径、Blackboard 值、FSM 状态）是程序员和设计师之间的共同参考——当设计师说"敌人不应该在这里撤退"，程序员打开调试面板，看到 `Health=15` → BT 的 `IsHealthLow` 条件为 true → 得出结论"阈值需要从 30 调到 15"——不需要读代码。

---

## 2. 代码示例

### 示例 A: Unity C# — AIController + FSM + BT + Blackboard

完整的 Unity AI 控制器，展示三层混合架构的实际代码。在这个示例中，一个敌方 NPC 使用 FSM 管理 Idle/Combat/Dead 顶层状态，每个 FSM 状态内运行一个 BT 子树，Blackboard 在 FSM 和 BT 之间共享。

```csharp
// ================================================================
// Example A: Unity - Layered AI (FSM top + BT per state + Blackboard)
// ================================================================

using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

// --- Blackboard (shared data across all layers) ---
[CreateAssetMenu(menuName = "AI/Blackboard")]
public class AIBlackboard : ScriptableObject
{
    // Perception
    public Transform Target;
    public Vector3 LastKnownTargetPosition;
    public float DistanceToTarget;
    public bool CanSeeTarget;

    // State
    public float Health;
    public float MaxHealth;
    public float AlertLevel; // 0-100, decays over time

    // Navigation
    public Vector3 MoveDestination;
    public float MoveSpeed;

    // Combat
    public bool IsAttacking;
    public string CurrentAttackPhase; // "windup", "active", "recovery"

    // Utility
    public float HealthRatio => Health / MaxHealth;
}

// --- BT Node base (minimal but functional) ---
public enum BTStatus { Success, Failure, Running }

public abstract class BTNode
{
    public abstract BTStatus Tick(AIBlackboard bb, GameObject owner);
}

// --- Composite nodes ---
public class Selector : BTNode
{
    private List<BTNode> children;
    public Selector(List<BTNode> children) => this.children = children;

    public override BTStatus Tick(AIBlackboard bb, GameObject owner)
    {
        foreach (var child in children)
        {
            var status = child.Tick(bb, owner);
            if (status != BTStatus.Failure) return status;
        }
        return BTStatus.Failure;
    }
}

public class Sequence : BTNode
{
    private List<BTNode> children;
    public Sequence(List<BTNode> children) => this.children = children;

    public override BTStatus Tick(AIBlackboard bb, GameObject owner)
    {
        foreach (var child in children)
        {
            var status = child.Tick(bb, owner);
            if (status != BTStatus.Success) return status;
        }
        return BTStatus.Success;
    }
}

// --- Condition nodes (read from Blackboard, no side effects) ---
public class HasTarget : BTNode
{
    public override BTStatus Tick(AIBlackboard bb, GameObject owner)
        => bb.Target != null ? BTStatus.Success : BTStatus.Failure;
}

public class IsHealthLow : BTNode
{
    private float threshold;
    public IsHealthLow(float threshold) => this.threshold = threshold;

    public override BTStatus Tick(AIBlackboard bb, GameObject owner)
        => bb.HealthRatio < threshold ? BTStatus.Success : BTStatus.Failure;
}

public class IsInMeleeRange : BTNode
{
    private float range;
    public IsInMeleeRange(float range) => this.range = range;

    public override BTStatus Tick(AIBlackboard bb, GameObject owner)
        => bb.DistanceToTarget <= range ? BTStatus.Success : BTStatus.Failure;
}

// --- Action nodes ---
public class ActionNode : BTNode
{
    private Func<AIBlackboard, GameObject, BTStatus> action;
    public ActionNode(Func<AIBlackboard, GameObject, BTStatus> action) => this.action = action;
    public override BTStatus Tick(AIBlackboard bb, GameObject owner) => action(bb, owner);
}

// --- FSM State interface ---
public enum FSMStateID { Idle, Combat, Dead }

public abstract class FSMState
{
    public FSMStateID ID { get; protected set; }
    protected BTNode behaviorTree; // subtree for this state

    public virtual void OnEnter(AIBlackboard bb, GameObject owner) { }
    public virtual void OnExit(AIBlackboard bb, GameObject owner) { }
    public virtual FSMStateID Update(AIBlackboard bb, GameObject owner)
    {
        // Default: run the BT subtree; BT determines behavior within this state
        behaviorTree?.Tick(bb, owner);
        return ID; // no transition by default
    }
}

// --- Concrete FSM States ---
public class IdleState : FSMState
{
    public IdleState()
    {
        ID = FSMStateID.Idle;
        // BT subtree for Idle: patrol if waypoints exist, otherwise stand guard
        behaviorTree = new Selector(new List<BTNode> {
            new Sequence(new List<BTNode> {
                new ActionNode((bb, owner) => {
                    // Move between patrol points
                    Patrol(bb, owner);
                    return BTStatus.Running;
                })
            })
        });
    }

    private void Patrol(AIBlackboard bb, GameObject owner)
    {
        // Simplified patrol logic
        var agent = owner.GetComponent<NavMeshAgent>();
        if (agent != null && !agent.pathPending && agent.remainingDistance < 0.5f)
        {
            // Pick next waypoint and set bb.MoveDestination
            bb.MoveDestination = GetNextPatrolPoint();
            agent.SetDestination(bb.MoveDestination);
        }
    }

    private Vector3 GetNextPatrolPoint() => Vector3.zero; // placeholder
}

public class CombatState : FSMState
{
    public CombatState()
    {
        ID = FSMStateID.Combat;
        // BT subtree for Combat: priority-ordered selection
        //   health low? → flee
        //   in melee? → attack
        //   can see target? → chase
        //   else → move to last known position
        behaviorTree = new Selector(new List<BTNode> {
            new Sequence(new List<BTNode> {
                new IsHealthLow(0.25f),
                new ActionNode(FleeAction)
            }),
            new Sequence(new List<BTNode> {
                new IsInMeleeRange(2.5f),
                new ActionNode(MeleeAttackAction)
            }),
            new Sequence(new List<BTNode> {
                new HasTarget(),
                new ActionNode(ChaseAction)
            }),
            new ActionNode(MoveToLastKnownAction)
        });
    }

    private static BTStatus FleeAction(AIBlackboard bb, GameObject owner)
    {
        if (bb.Target == null) return BTStatus.Success;
        // Move away from target
        var agent = owner.GetComponent<NavMeshAgent>();
        var fleeDir = (owner.transform.position - bb.Target.position).normalized;
        bb.MoveDestination = owner.transform.position + fleeDir * 20f;
        agent?.SetDestination(bb.MoveDestination);
        bb.MoveSpeed = agent != null ? agent.speed : 0f;
        return BTStatus.Running;
    }

    private static BTStatus MeleeAttackAction(AIBlackboard bb, GameObject owner)
    {
        bb.IsAttacking = true;
        bb.CurrentAttackPhase = "active";
        // Face target
        var dir = (bb.Target.position - owner.transform.position).normalized;
        owner.transform.rotation = Quaternion.LookRotation(dir);
        // Attack logic would trigger animation event to deal damage
        return BTStatus.Running;
    }

    private static BTStatus ChaseAction(AIBlackboard bb, GameObject owner)
    {
        var agent = owner.GetComponent<NavMeshAgent>();
        bb.MoveDestination = bb.Target.position;
        agent?.SetDestination(bb.MoveDestination);
        bb.MoveSpeed = agent != null ? agent.speed : 0f;
        return BTStatus.Running;
    }

    private static BTStatus MoveToLastKnownAction(AIBlackboard bb, GameObject owner)
    {
        var agent = owner.GetComponent<NavMeshAgent>();
        agent?.SetDestination(bb.LastKnownTargetPosition);
        bb.MoveSpeed = agent != null ? agent.speed : 0f;
        return BTStatus.Running;
    }
}

public class DeadState : FSMState
{
    public DeadState()
    {
        ID = FSMStateID.Dead;
        // No BT — dead enemies don't make decisions
        behaviorTree = null;
    }

    public override void OnEnter(AIBlackboard bb, GameObject owner)
    {
        // Stop all movement, disable collider, play death animation
        var agent = owner.GetComponent<NavMeshAgent>();
        if (agent) agent.isStopped = true;
        bb.MoveSpeed = 0f;
        bb.IsAttacking = false;
    }
}

// --- AIController: the brain ---
public class AIController : MonoBehaviour
{
    [SerializeField] private AIBlackboard blackboard;

    private Dictionary<FSMStateID, FSMState> states;
    private FSMState currentState;
    private NavMeshAgent agent;

    // --- Transitions are evaluated HERE (top-level FSM) ---
    private void Start()
    {
        agent = GetComponent<NavMeshAgent>();

        states = new Dictionary<FSMStateID, FSMState> {
            { FSMStateID.Idle,   new IdleState() },
            { FSMStateID.Combat, new CombatState() },
            { FSMStateID.Dead,   new DeadState() }
        };

        TransitionTo(FSMStateID.Idle);
    }

    private void Update()
    {
        // --- Sense ---
        UpdatePerception();

        // --- Think (top-level FSM transitions) ---
        var nextState = EvaluateTopLevelTransitions();

        // --- Act ---
        if (nextState != currentState.ID)
            TransitionTo(nextState);

        currentState.Update(blackboard, gameObject);

        // Update animator parameters for animation layer
        UpdateAnimator();
    }

    private void UpdatePerception()
    {
        // Simplified perception — in production, use a perception system
        if (blackboard.Target != null)
        {
            blackboard.DistanceToTarget = Vector3.Distance(
                transform.position, blackboard.Target.position);
            blackboard.CanSeeTarget = !Physics.Linecast(
                transform.position, blackboard.Target.position);
            if (blackboard.CanSeeTarget)
                blackboard.LastKnownTargetPosition = blackboard.Target.position;
        }
        else
        {
            blackboard.CanSeeTarget = false;
        }

        blackboard.Health = GetComponent<HealthComponent>()?.CurrentHealth ?? 100f;
        blackboard.MaxHealth = GetComponent<HealthComponent>()?.MaxHealth ?? 100f;
    }

    private FSMStateID EvaluateTopLevelTransitions()
    {
        // Dead → Dead (terminal)
        if (currentState.ID == FSMStateID.Dead)
            return FSMStateID.Dead;

        // Any → Dead
        if (blackboard.Health <= 0f)
            return FSMStateID.Dead;

        // Idle → Combat: spotted target
        if (currentState.ID == FSMStateID.Idle && blackboard.CanSeeTarget)
            return FSMStateID.Combat;

        // Combat → Idle: alert level decays, no target
        if (currentState.ID == FSMStateID.Combat
            && !blackboard.CanSeeTarget
            && blackboard.AlertLevel <= 0f)
            return FSMStateID.Idle;

        return currentState.ID;
    }

    private void TransitionTo(FSMStateID newStateID)
    {
        currentState?.OnExit(blackboard, gameObject);

        if (states.TryGetValue(newStateID, out var newState))
        {
            currentState = newState;
            currentState.OnEnter(blackboard, gameObject);
        }
    }

    private void UpdateAnimator()
    {
        // Drive the animation state machine (low-level layer)
        var animator = GetComponent<Animator>();
        if (animator == null) return;

        animator.SetFloat("MoveSpeed", blackboard.MoveSpeed);
        animator.SetBool("IsAttacking", blackboard.IsAttacking);
        // Animator reads these and its own state machine decides which
        // animation clip to play and how to blend
    }
}
```

**关键架构点**：
1. **FSM 管理顶层状态转移**（`EvaluateTopLevelTransitions`），状态转移规则集中在控制器中，不散落在各层。
2. **每个 FSM 状态内嵌一个 BT 子树**——`CombatState` 的 BT 子树不需要关心"死亡"条件，因为死亡在 FSM 层就被拦截了。
3. **Blackboard 是共享数据结构**——BT 的 Action 节点写入 `MoveDestination`，`UpdateAnimator` 从 `MoveSpeed` 读取，各自消费同一份数据的不同切面。
4. **动画层完全独立**——`UpdateAnimator` 只是设置 Animator 参数，动画状态机自行决定如何混合。

### 示例 B: UE C++ — AIController + BT + GAS + Animation Blueprint

UE5 的混合架构展示了引擎原生支持的多层 AI 系统。此示例展示一个 Boss AI 控制器，它使用 BT 进行战术决策，通过 GameplayAbilitySystem 执行战斗动作，Animation Blueprint 独立驱动动画层。

```cpp
// ================================================================
// Example B: UE5 - Boss AI with BT + GAS + Animation Blueprint
// ================================================================

// --- BossAIController.h ---
#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "BossAIController.generated.h"

class UBehaviorTree;
class UBlackboardComponent;
class UAbilitySystemComponent;

UCLASS()
class ABossAIController : public AAIController
{
    GENERATED_BODY()

public:
    ABossAIController(const FObjectInitializer& ObjectInitializer);

    virtual void OnPossess(APawn* InPawn) override;
    virtual void Tick(float DeltaSeconds) override;

    // --- AI Command Queue ---
    UFUNCTION(BlueprintCallable)
    void EnqueueCommand(
        FGameplayTag CommandTag,
        float Priority,
        AActor* Target = nullptr,
        FVector Location = FVector::ZeroVector);

    UFUNCTION(BlueprintCallable)
    void CancelCurrentCommand();

protected:
    virtual void BeginPlay() override;

    // BT asset (assigned in Blueprint or DataAsset)
    UPROPERTY(EditDefaultsOnly, Category = "AI")
    UBehaviorTree* BossBehaviorTree;

    // Maximum number of pending commands
    UPROPERTY(EditDefaultsOnly, Category = "AI")
    int32 MaxCommandQueueSize = 5;

private:
    // Perception → Blackboard update
    void UpdatePerception();

    // Manage phase transitions (BT writes phase to BB, evaluated here)
    void UpdateBossPhase();

    UBlackboardComponent* BB;
    UAbilitySystemComponent* AbilitySystem;

    // Current boss phase (1-3)
    int32 CurrentPhase = 1;

    struct FAICommand
    {
        FGameplayTag Tag;
        float Priority;
        TWeakObjectPtr<AActor> Target;
        FVector Location;
        float TimeQueued;
    };

    TArray<FAICommand> CommandQueue;
    TOptional<FAICommand> ActiveCommand;
};

// --- BossAIController.cpp ---
#include "BossAIController.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "BehaviorTree/BehaviorTreeComponent.h"
#include "AbilitySystemComponent.h"
#include "GameplayTagContainer.h"
#include "Perception/AIPerceptionComponent.h"
#include "Perception/AISense_Sight.h"
#include "Perception/AISense_Damage.h"
#include "AIController.h"

ABossAIController::ABossAIController(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    // BT component
    BehaviorTreeComponent = CreateDefaultSubobject<UBehaviorTreeComponent>(
        TEXT("BehaviorTreeComponent"));
    // Blackboard
    BlackboardComponent = CreateDefaultSubobject<UBlackboardComponent>(
        TEXT("BlackboardComponent"));
    // Perception
    PerceptionComponent = CreateDefaultSubobject<UAIPerceptionComponent>(
        TEXT("PerceptionComponent"));

    // Register senses
    PerceptionComponent->ConfigureSense(*UAISense_Sight::StaticClass());
    PerceptionComponent->ConfigureSense(*UAISense_Damage::StaticClass());
}

void ABossAIController::BeginPlay()
{
    Super::BeginPlay();
    RunBehaviorTree(BossBehaviorTree);
}

void ABossAIController::OnPossess(APawn* InPawn)
{
    Super::OnPossess(InPawn);

    // Initialize blackboard
    if (BossBehaviorTree && BlackboardComponent)
    {
        BlackboardComponent->InitializeBlackboard(
            *BossBehaviorTree->BlackboardAsset);
    }

    // Cache AbilitySystemComponent
    AbilitySystem = InPawn->FindComponentByClass<UAbilitySystemComponent>();

    // Start BT
    if (BossBehaviorTree)
    {
        RunBehaviorTree(BossBehaviorTree);
    }
}

void ABossAIController::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);

    // --- Sense: update perception into Blackboard ---
    UpdatePerception();

    // --- Phase management (between BT and GAS) ---
    UpdateBossPhase();

    // --- Command Queue: consume commands from BT ---
    // BT writes commands to Blackboard (as GameplayTags or enums).
    // The command queue buffers them and feeds to AbilitySystem.

    if (BB)
    {
        // BT writes a command tag to Blackboard when it wants to trigger an action
        FName CommandKey = TEXT("PendingCommand");
        if (BB->IsValidKey(BlackboardComponent->GetKeyID(CommandKey)))
        {
            FGameplayTag CommandTag = FGameplayTag::RequestGameplayTag(
                *BB->GetValueAsName(CommandKey).ToString(), false);
            if (CommandTag.IsValid())
            {
                float Priority = BB->GetValueAsFloat(TEXT("CommandPriority"));
                AActor* Target = Cast<AActor>(
                    BB->GetValueAsObject(TEXT("TargetActor")));

                EnqueueCommand(CommandTag, Priority, Target);

                // Clear the pending command so BT doesn't re-enqueue every frame
                BB->ClearValue(CommandKey);
            }
        }
    }
}

void ABossAIController::UpdatePerception()
{
    if (!BB || !PerceptionComponent) return;

    TArray<AActor*> PerceivedActors;
    PerceptionComponent->GetCurrentlyPerceivedActors(
        UAISense_Sight::StaticClass(), PerceivedActors);

    AActor* CurrentTarget = nullptr;
    float ClosestDist = FLT_MAX;

    for (AActor* Actor : PerceivedActors)
    {
        if (Actor->ActorHasTag(FName("Player")))
        {
            float Dist = FVector::Dist(
                GetPawn()->GetActorLocation(), Actor->GetActorLocation());
            if (Dist < ClosestDist)
            {
                ClosestDist = Dist;
                CurrentTarget = Actor;
            }
        }
    }

    BB->SetValueAsObject(TEXT("TargetActor"), CurrentTarget);
    BB->SetValueAsBool(TEXT("HasTarget"), CurrentTarget != nullptr);
    BB->SetValueAsFloat(TEXT("DistanceToTarget"), ClosestDist);
}

void ABossAIController::UpdateBossPhase()
{
    if (!BB || !AbilitySystem) return;

    // Phase is determined by HP ratio, stored in Blackboard
    float HealthRatio = BB->GetValueAsFloat(TEXT("HealthRatio"));

    int32 NewPhase;
    if (HealthRatio > 0.66f)       NewPhase = 1;
    else if (HealthRatio > 0.33f)  NewPhase = 2;
    else                           NewPhase = 3;

    if (NewPhase != CurrentPhase)
    {
        CurrentPhase = NewPhase;
        BB->SetValueAsInt(TEXT("BossPhase"), CurrentPhase);

        // Phase transition: cancel all pending commands, trigger phase ability
        CommandQueue.Empty();
        ActiveCommand.Reset();

        // Trigger phase transition ability via GAS
        FGameplayTag PhaseTag = FGameplayTag::RequestGameplayTag(
            *FString::Printf(TEXT("Boss.Phase.Transition.%d"), CurrentPhase),
            false);
        if (AbilitySystem && PhaseTag.IsValid())
        {
            // Send GameplayEvent to trigger transition ability
            FGameplayEventData EventData;
            AbilitySystem->HandleGameplayEvent(PhaseTag, &EventData);
        }
    }
}

void ABossAIController::EnqueueCommand(
    FGameplayTag CommandTag,
    float Priority,
    AActor* Target,
    FVector Location)
{
    FAICommand NewCommand{ CommandTag, Priority, Target, Location,
        GetWorld()->GetTimeSeconds() };

    // Insert sorted by priority (highest first)
    int32 InsertIdx = 0;
    for (; InsertIdx < CommandQueue.Num(); ++InsertIdx)
    {
        if (NewCommand.Priority > CommandQueue[InsertIdx].Priority)
            break;
    }
    CommandQueue.Insert(NewCommand, InsertIdx);

    // Trim to max size
    while (CommandQueue.Num() > MaxCommandQueueSize)
        CommandQueue.RemoveAt(CommandQueue.Num() - 1);

    // Check preemption: if new command has higher priority than active,
    // cancel active and start new one immediately
    if (ActiveCommand.IsSet() && NewCommand.Priority > ActiveCommand->Priority)
    {
        CancelCurrentCommand();
    }

    // If no active command, start next
    if (!ActiveCommand.IsSet() && CommandQueue.Num() > 0)
    {
        ActiveCommand = CommandQueue[0];
        CommandQueue.RemoveAt(0);

        // Trigger via GAS
        FGameplayEventData EventData;
        EventData.Target = ActiveCommand->Target.Get();
        EventData.TargetData.Data.Add(MakeShareable(
            new FGameplayAbilityTargetData_LocationInfo()));
        AbilitySystem->HandleGameplayEvent(
            ActiveCommand->Tag, &EventData);
    }
}

void ABossAIController::CancelCurrentCommand()
{
    if (!ActiveCommand.IsSet()) return;

    // Send cancel event to GAS
    FGameplayTag CancelTag = FGameplayTag::RequestGameplayTag(
        TEXT("AI.Command.Cancel"), false);
    if (AbilitySystem && CancelTag.IsValid())
    {
        FGameplayEventData CancelData;
        AbilitySystem->HandleGameplayEvent(CancelTag, &CancelData);
    }

    ActiveCommand.Reset();
}
```

```cpp
// ================================================================
// BT Task: Execute Boss Phase-specific action
// ================================================================

// --- BTTask_BossPhaseAttack.h ---
#pragma once

#include "BehaviorTree/BTTaskNode.h"
#include "GameplayTagContainer.h"
#include "BTTask_BossPhaseAttack.generated.h"

UCLASS()
class UBTTask_BossPhaseAttack : public UBTTaskNode
{
    GENERATED_BODY()

public:
    UBTTask_BossPhaseAttack();

    // Tag for this specific attack (e.g. "Boss.Attack.Phase2.Slam")
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FGameplayTag AttackTag;

    // Priority — higher priority attacks preempt lower ones
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    float Priority = 1.0f;

    // Don't enqueue if already queued
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    bool bAllowDuplicate = false;

protected:
    virtual EBTNodeResult::Type ExecuteTask(
        UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) override;

    virtual void TickTask(
        UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;

    virtual EBTNodeResult::Type AbortTask(
        UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) override;

private:
    bool bCommandSent = false;
};

// --- BTTask_BossPhaseAttack.cpp ---
#include "BTTask_BossPhaseAttack.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"

UBTTask_BossPhaseAttack::UBTTask_BossPhaseAttack()
{
    NodeName = TEXT("Boss Phase Attack");
    bNotifyTick = true;
    bCreateNodeInstance = true;
}

EBTNodeResult::Type UBTTask_BossPhaseAttack::ExecuteTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return EBTNodeResult::Failed;

    // Check which boss phase we're in
    int32 BossPhase = BB->GetValueAsInt(TEXT("BossPhase"));
    FString PhaseKey = FString::Printf(TEXT("%d"), BossPhase);

    // Does this attack match the current phase? (AttackTag contains phase info)
    if (!AttackTag.ToString().Contains(PhaseKey))
        return EBTNodeResult::Failed;

    // Check cooldown or availability via Blackboard
    FName CooldownKey = FName(*(TEXT("Cooldown_") + AttackTag.ToString()));
    float CooldownRemaining = BB->GetValueAsFloat(CooldownKey);
    if (CooldownRemaining > 0.f)
        return EBTNodeResult::Failed;

    // Enqueue the command via AIController
    AAIController* AICon = OwnerComp.GetAIOwner();
    if (!AICon) return EBTNodeResult::Failed;

    // Write command to Blackboard — AIController::Tick reads it
    BB->SetValueAsName(TEXT("PendingCommand"),
        FName(*AttackTag.ToString()));
    BB->SetValueAsFloat(TEXT("CommandPriority"), Priority);
    bCommandSent = true;

    return EBTNodeResult::InProgress;
}

void UBTTask_BossPhaseAttack::TickTask(
    UBehaviorTreeComponent& OwnerComp,
    uint8* NodeMemory, float DeltaSeconds)
{
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return;

    // Check if the executed ability is still active via Blackboard
    bool bAbilityActive = BB->GetValueAsBool(TEXT("AbilityActive"));
    if (!bAbilityActive && bCommandSent)
    {
        // Ability finished — set cooldown
        FName CooldownKey = FName(*(TEXT("Cooldown_") + AttackTag.ToString()));
        BB->SetValueAsFloat(CooldownKey, 8.0f); // 8 second cooldown

        FinishLatentTask(OwnerComp, EBTNodeResult::Succeeded);
    }
}

EBTNodeResult::Type UBTTask_BossPhaseAttack::AbortTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    // Phase transition or higher priority action preempted us
    bCommandSent = false;
    return EBTNodeResult::Aborted;
}
```

**关键架构点**：
1. **BT → Blackboard → AIController → GAS 的命令流**：BT 节点不直接触发能力，而是写入 `PendingCommand` 到 Blackboard。AIController 的 `Tick` 读取并入队命令。这提供了**缓冲和优先级管理**——BT 每帧重评估不会导致每帧触发新能力。
2. **AIController 是协调中心**：它拥有感知系统、BT、命令队列、GAS 引用的缓存——它是各子系统之间的胶水代码。
3. **Phase 管理独立于 BT**：`UpdateBossPhase` 在 AIController 的 Tick 中单独执行——它修改 Blackboard 的 `BossPhase` 值，BT 的 Decorator 条件节点响应这个变化而切换子树路径。
4. **GAS 标签是这个架构的关键**：GameplayTags（`Boss.Attack.Phase2.Slam`）在整个系统中作为标识符流动——BT 节点配置 AttackTag，AIController 通过 Tag 入队，GAS 通过 Tag 查找并执行匹配的能力。这使得设计师可以在数据表中配置完整的"BT 节点 → 标签 → 能力"映射，而不需要修改 C++。

### 示例 C: Lua — C++ 引擎 + Lua 定义的行为混合架构

在自研引擎中，常见的模式是 C++ 提供高性能 BT 引擎和 Blackboard，Lua 定义树结构和叶子行为。下面展示一个简化但完整的 C++/Lua 混合 AI 架构。

```cpp
// ================================================================
// Example C: C++ BT Engine (performance layer)
// ================================================================

// --- AI/BTEngine.h ---
#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <functional>
#include <variant>
#include <chrono>
#include <queue>

// Minimal Lua binding — in production use sol2, LuaBridge, or tolua++
struct lua_State;
using LuaRef = int; // stack index placeholder for illustration

// --- Blackboard (C++ side, high-performance) ---
using BBValue = std::variant<int, float, bool, std::string, void*>;

class Blackboard {
    std::unordered_map<std::string, BBValue> data;
    // Event queue for cross-layer communication
    struct AIEvent {
        std::string type;
        std::unordered_map<std::string, BBValue> params;
        uint64_t frameIssued;
    };
    std::vector<AIEvent> eventsThisFrame;

public:
    template<typename T>
    T Get(const std::string& key) const {
        auto it = data.find(key);
        if (it != data.end()) return std::get<T>(it->second);
        return T{};
    }

    template<typename T>
    void Set(const std::string& key, const T& value) {
        data[key] = value;
    }

    bool Has(const std::string& key) const {
        return data.find(key) != data.end();
    }

    // Event system
    void EmitEvent(const std::string& type,
                   const std::unordered_map<std::string, BBValue>& params) {
        eventsThisFrame.push_back({type, params, CurrentFrame});
    }

    const std::vector<AIEvent>& GetEvents() const { return eventsThisFrame; }
    void ClearEvents() { eventsThisFrame.clear(); }

    static uint64_t CurrentFrame;
};

// --- BT Node types (C++ fast path) ---
enum class NodeStatus { Success, Failure, Running, Invalid };

struct BTNode {
    std::string name;
    virtual ~BTNode() = default;
    virtual NodeStatus Tick(Blackboard& bb) = 0;
    virtual void Reset() { } // reset Running state when re-entered
};

// Composite: Selector (fallback)
class SelectorNode : public BTNode {
    std::vector<std::unique_ptr<BTNode>> children;
public:
    explicit SelectorNode(std::vector<std::unique_ptr<BTNode>> c)
        : children(std::move(c)) { name = "Selector"; }

    NodeStatus Tick(Blackboard& bb) override {
        for (auto& child : children) {
            NodeStatus status = child->Tick(bb);
            if (status != NodeStatus::Failure) return status;
        }
        return NodeStatus::Failure;
    }

    // Allow adding children after construction (for Lua-defined trees)
    void AddChild(std::unique_ptr<BTNode> child) {
        children.push_back(std::move(child));
    }
};

// Composite: Sequence
class SequenceNode : public BTNode {
    std::vector<std::unique_ptr<BTNode>> children;
    size_t currentIndex = 0;
public:
    explicit SequenceNode(std::vector<std::unique_ptr<BTNode>> c)
        : children(std::move(c)) { name = "Sequence"; }

    NodeStatus Tick(Blackboard& bb) override {
        while (currentIndex < children.size()) {
            NodeStatus status = children[currentIndex]->Tick(bb);
            if (status == NodeStatus::Failure) {
                currentIndex = 0; // reset for next evaluation
                return NodeStatus::Failure;
            }
            if (status == NodeStatus::Running) return NodeStatus::Running;
            // Success → move to next
            currentIndex++;
        }
        currentIndex = 0; // reset
        return NodeStatus::Success;
    }

    void Reset() override { currentIndex = 0; }

    void AddChild(std::unique_ptr<BTNode> child) {
        children.push_back(std::move(child));
    }
};

// Lua callback node — bridges C++ BT engine to Lua behavior logic
class LuaActionNode : public BTNode {
    lua_State* L;
    LuaRef callbackRef;
public:
    LuaActionNode(lua_State* lua, LuaRef ref, const std::string& n)
        : L(lua), callbackRef(ref) { name = n; }

    NodeStatus Tick(Blackboard& bb) override;
};

// Decorator: Inverter
class InverterNode : public BTNode {
    std::unique_ptr<BTNode> child;
public:
    explicit InverterNode(std::unique_ptr<BTNode> c)
        : child(std::move(c)) { name = "Inverter"; }

    NodeStatus Tick(Blackboard& bb) override {
        NodeStatus status = child->Tick(bb);
        if (status == NodeStatus::Success) return NodeStatus::Failure;
        if (status == NodeStatus::Failure) return NodeStatus::Success;
        return status;
    }
};

// --- C++ BT Engine ---
class BTEngine {
    std::unique_ptr<BTNode> root;
    Blackboard blackboard;

public:
    void SetRoot(std::unique_ptr<BTNode> r) { root = std::move(r); }
    Blackboard& GetBlackboard() { return blackboard; }

    void Tick() {
        if (root) root->Tick(blackboard);
        blackboard.ClearEvents(); // events consumed each frame
    }
};

// --- AI Manager (manages all AI entities) ---
class AIManager {
    struct AIEntity {
        int id;
        BTEngine btEngine;
        // Animation FSM — Lua-defined state table
        // In production, this would be a Lua table reference.
        // For simplicity, we use a C++ enum-driven state machine.
        enum class AnimState { Idle, Walk, Run, Attack, Death, Stagger };
        AnimState currentAnimState = AnimState::Idle;
        AnimState targetAnimState = AnimState::Idle;
        float animTransitionTime = 0.f;
    };

    std::vector<AIEntity> entities;
    lua_State* L;

public:
    void Initialize(int entityCount, lua_State* lua);
    void TickAll(float dt);
    void LoadBehaviorFromLua(int entityId, const std::string& luaModule);
};
```

```lua
-- ================================================================
-- Example C: Lua behavior definition layer
-- ================================================================

-- boss_behaviors.lua — defines a boss AI using the C++ BT engine API

-- The C++ engine exposes these to Lua:
--   BTEngine:SetRoot(node)
--   SelectorNode.new(children) / AddChild(node)
--   SequenceNode.new(children) / AddChild(node)
--   ConditionNode.new(name, check_fn)
--   ActionNode.new(name, tick_fn)
--   EventBus:Subscribe(event_type, handler)
--   AnimFSM:TransitionTo(state_name, blend_time)

local bb = ... -- Blackboard reference passed by C++

local function BuildBossPhase1Tree()
    -- Phase 1 behaviors: simple attack patterns, no desperation mechanics
    local root = SelectorNode.new()

    -- Priority 1: If health low enough, transition to Phase 2
    -- (Blackboard "BossPhase" is also checked by C++ UpdateBossPhase)
    root:AddChild(SequenceNode.new({
        ConditionNode.new("HealthBelow66%", function()
            return bb:Get("HealthRatio") < 0.66
        end),
        ActionNode.new("TransitionToPhase2", function()
            bb:Set("BossPhase", 2)
            EventBus:Emit("Boss.PhaseChanged", { from = 1, to = 2 })
            return "Success"
        end),
    }))

    -- Priority 2: If player is close, use melee slam
    root:AddChild(SequenceNode.new({
        ConditionNode.new("PlayerInMeleeRange", function()
            return bb:Get("DistanceToTarget") < 4.0
        end),
        ConditionNode.new("SlamNotOnCooldown", function()
            return bb:Get("Cooldown_Slam") <= 0
        end),
        ActionNode.new("ExecuteSlam", function()
            -- Enqueue command to the AI Command Queue (C++ side)
            AIManager:EnqueueCommand(bb:Get("EntityID"), {
                type = "Boss.Attack.Slam",
                priority = 2.0,
                target = bb:Get("TargetActor"),
            })
            bb:Set("Cooldown_Slam", 5.0)
            return "Success"
        end),
    }))

    -- Priority 3: If player is at range, fire projectile
    root:AddChild(SequenceNode.new({
        ConditionNode.new("PlayerInRangedRange", function()
            return bb:Get("DistanceToTarget") < 20.0
        end),
        ActionNode.new("FireProjectile", function()
            AIManager:EnqueueCommand(bb:Get("EntityID"), {
                type = "Boss.Attack.Projectile",
                priority = 1.0,
                target = bb:Get("TargetActor"),
                aim_offset = { x = 1.0, y = 0.0, z = 1.5 }, -- aim slightly ahead
            })
            return "Success"
        end),
    }))

    -- Priority 4: Default — move toward player
    root:AddChild(ActionNode.new("ApproachPlayer", function()
        local playerPos = bb:Get("TargetPosition")
        AIManager:EnqueueCommand(bb:Get("EntityID"), {
            type = "Move.To",
            priority = 0.5,
            location = playerPos,
        })
        return "Running"
    end))

    return root
end

-- Build Phase 2 tree (more aggressive, new attacks, area denial)
local function BuildBossPhase2Tree()
    local root = SelectorNode.new()

    -- Phase transition to Phase 3
    root:AddChild(SequenceNode.new({
        ConditionNode.new("HealthBelow33%", function()
            return bb:Get("HealthRatio") < 0.33
        end),
        ActionNode.new("TransitionToPhase3", function()
            bb:Set("BossPhase", 3)
            EventBus:Emit("Boss.PhaseChanged", { from = 2, to = 3 })
            return "Success"
        end),
    }))

    -- Phase 2: new attack — arena-wide fire wave
    root:AddChild(SequenceNode.new({
        ConditionNode.new("CanDoArenaAttack", function()
            return bb:Get("TimeSinceLastArenaAttack") > 20.0
        end),
        ActionNode.new("ArenaFireWave", function()
            AIManager:EnqueueCommand(bb:Get("EntityID"), {
                type = "Boss.Attack.FireWave",
                priority = 3.0, -- high priority, preempts most actions
            })
            bb:Set("TimeSinceLastArenaAttack", 0.0)
            return "Success"
        end),
    }))

    -- ... other Phase 2 behaviors ...

    return root
end

-- Event-driven cross-layer communication
-- When "DamageTaken" event fires (from C++ damage system), update behavior
EventBus:Subscribe("DamageTaken", function(event)
    -- Lua handler runs in response to C++ events
    bb:Set("HealthRatio", event.current_hp / event.max_hp)

    -- If a big hit, trigger stagger animation through Animation FSM
    if event.damage > event.max_hp * 0.2 then
        -- The Animation FSM is a Lua table (see below)
        AnimFSM:Trigger("Stagger", { blend_time = 0.1 })
        -- Emit event for other systems (audio, VFX, etc.)
        EventBus:Emit("AI.Staggered", { entity = bb:Get("EntityID") })
    end
end)

-- Called by C++ AIManager when this AI is initialized
function Init(entityId, blackboard)
    bb = blackboard
    bb:Set("EntityID", entityId)
    bb:Set("BossPhase", 1)

    -- Build initial tree based on current phase
    local root = BuildBossPhase1Tree()
    -- Register with C++ BT engine
    BTEngine:SetRoot(entityId, root)
end

-- Called by C++ every frame when phase changes
function OnPhaseChanged(newPhase)
    local newRoot
    if newPhase == 2 then
        newRoot = BuildBossPhase2Tree()
    elseif newPhase == 3 then
        -- Phase 3 tree: extreme aggression, enrage mechanics
        newRoot = BuildBossPhase3Tree()
    end
    if newRoot then
        BTEngine:SetRoot(bb:Get("EntityID"), newRoot)
    end
end

--- ================================================================
--- Animation FSM (Lua-defined, driven by AI layer)
--- ================================================================

-- anim_fsm.lua — Animation state machine for the boss
-- Driven by Blackboard values and AI events

local AnimFSM = {}

local states = {
    Idle = {
        onEnter = function() CppAnim:Crossfade("Boss_Idle", 0.3) end,
        transitions = {
            { to = "Walk",   condition = function() return bb:Get("MoveSpeed") > 0.1 end },
            { to = "Attack", condition = function() return bb:Get("IsAttacking") end },
            { to = "Death",  condition = function() return bb:Get("Health") <= 0 end },
        },
    },
    Walk = {
        onEnter = function()
            CppAnim:Crossfade("Boss_Walk", 0.2)
            CppAnim:SetFloat("WalkSpeed", bb:Get("MoveSpeed") / 600.0)
        end,
        onUpdate = function()
            CppAnim:SetFloat("WalkSpeed", bb:Get("MoveSpeed") / 600.0)
        end,
        transitions = {
            { to = "Idle",   condition = function() return bb:Get("MoveSpeed") < 0.1 end },
            { to = "Attack", condition = function() return bb:Get("IsAttacking") end },
        },
    },
    Attack = {
        onEnter = function()
            local attackName = bb:Get("CurrentAttackAnim") or "Boss_Attack_Generic"
            CppAnim:Play(attackName)
        end,
        onUpdate = function()
            -- Check if animation finished via C++ callback
            if CppAnim:IsFinished() then
                bb:Set("IsAttacking", false)
            end
        end,
        transitions = {
            { to = "Idle",  condition = function() return not bb:Get("IsAttacking") end },
            { to = "Death", condition = function() return bb:Get("Health") <= 0 end },
        },
    },
    Death = {
        onEnter = function() CppAnim:Play("Boss_Death") end,
        transitions = {}, -- terminal
    },
    Stagger = {
        onEnter = function() CppAnim:Play("Boss_Stagger") end,
        transitions = {
            { to = "Idle", condition = function() return CppAnim:IsFinished() end },
        },
    },
}

local currentState = "Idle"

function AnimFSM.Update(dt)
    local state = states[currentState]
    if not state then return end

    if state.onUpdate then state.onUpdate(dt) end

    -- Evaluate transitions in order
    for _, trans in ipairs(state.transitions) do
        if trans.condition() then
            AnimFSM.TransitionTo(trans.to)
            break
        end
    end
end

function AnimFSM.TransitionTo(newState, blendTime)
    local state = states[newState]
    if not state then return end

    currentState = newState
    if state.onEnter then state.onEnter() end
end

function AnimFSM.Trigger(stateName, params)
    -- Force transition (for event-driven triggers like Stagger)
    if states[stateName] then
        currentState = stateName
        if states[stateName].onEnter then states[stateName].onEnter() end
    end
end

return AnimFSM
```

**关键架构点**：
1. **C++ 层只做"引擎"**——BT 的复合节点（Selector, Sequence）、Blackboard、事件系统的核心数据结构在 C++ 中，保证每帧 Tick 的性能。
2. **Lua 层做"定义"**——行为树的叶子节点逻辑、动画状态表、事件处理回调由 Lua 编写。设计师修改行为不需要 C++ 编译。
3. **阶段切换通过树的整体替换实现**——`OnPhaseChanged` 构建全新的 BT 子树并替换。这是"FSM 状态运行 BT 子树"模式在 Lua 层的体现——FSM 状态（Boss Phase 1/2/3）在 Blackboard 中，BT 引擎重新加载对应的子树。
4. **Animation FSM 完全独立于 AI 逻辑**——它只读取 Blackboard 值（`MoveSpeed`, `IsAttacking`），通过条件判断自行决策动画切换。AI 层不知道也不关心动画的状态。
5. **事件系统是跨层桥梁**：C++ 伤害系统产生 `DamageTaken` 事件 → Lua 层的 BT/动画逻辑订阅处理 → 可能反过来通过事件触发音效、粒子、屏幕震动等其他系统。

---

## 3. 练习

### 练习 1: 设计 Boss 分层 AI 架构（60min）

为一个三阶段 Boss 设计完整的混合架构。Boss 的战斗规格：

- **阶段 1（100%-66% HP）**：近距离近战攻击（重击 + 连击）、中距离追踪、偶尔释放追踪弹。
- **阶段 2（66%-33% HP）**：增加横扫 AOE、召唤小兵、保留阶段 1 的攻击（但频率降低）。
- **阶段 3（33%-0% HP）**：全图火焰波（每 20 秒）、狂暴近战（加速）、小兵变为自爆型。
- **动画需求**：所有攻击有 windup → active → recovery 三段。阶段切换有过渡动画（2-3 秒无敌帧）。被暴击时可能触发硬直动画（打断当前动作）。

**你的任务**：

1. 画出三层架构图（High/Mid/Low），标注每一层使用什么范式（BT/FSM/Animator）。
2. 设计 Blackboard 的 key 集合——写出至少 15 个 key 并标注哪些层读写它们。
3. 设计阶段切换的数据流：从"HP 降到 66%"到"阶段 2 过渡动画播放完毕"的完整的事件/数据流程。
4. 标注至少 3 个设计决策点：为什么要这样分层而不是合并？为什么某个行为在 BT 层而不是 FSM 层（或反过来）？

**评判标准**：
- 架构能够无歧义地支持所有三个阶段的行为，不出现"当一个系统在控制时另一个系统的决策被忽略"的情况。
- 阶段过渡平滑——玩家不应看到动画跳变或逻辑撕裂。
- 设计师可以独立调整每个阶段的攻击概率和优先级，不需要修改 C++。

### 练习 2: 实现 AI Command Queue（60min）

实现一个带优先级的 AI Command Queue。语言自选（C++/C#/Lua），但要求：

**核心功能**：
1. **入队（Enqueue）**：接受 `(Type, Priority, Target, Params)` 的命令，按优先级排序插入队列（更高优先级排在前面）。队列最大长度可配置（默认 5）。超出时踢掉最低优先级的命令。
2. **抢占（Preemption）**：如果新命令的优先级 > 当前执行命令的优先级 + `InterruptThreshold`，取消当前命令并立即执行新命令。被抢占的命令不回到队列（丢弃）。
3. **超时（Timeout）**：命令在队列中超过配置的超时时间（默认 3 秒）后自动丢弃，并触发 `OnCommandExpired` 回调。
4. **完成回调**：当前命令执行完毕后，调用 `OnCommandCompleted` 回调，然后自动出队下一个命令。

**测试场景**：模拟以下命令序列并验证最终执行顺序：

```
t=0.0: Enqueue(MoveTo, Priority=1, Target=WaypointA)
t=0.5: Enqueue(Attack, Priority=3, Target=Player)     // 应抢占 MoveTo
t=2.0: Enqueue(Dodge, Priority=5, Target=None)        // 应抢占 Attack
t=2.5: Dodge completes → Dequeue next (Attack 恢复?)
t=3.0: Enqueue(Flee, Priority=4, Target=None)         // 优先级低于 Attack(3)?
t=5.0: Enqueue(Heal, Priority=10, Target=Self)        // 应抢占一切
```

先用手算预期顺序，再运行代码验证。解释任何偏差。特别关注 **t=3.0** 的时刻：Attack(prio=3) 是否还在队列中？Flee(prio=4) 是否应该抢占它？

### 练习 3（可选）：设计团队工作流（30min）

你是一个中型游戏工作室的 AI 技术负责人。项目是一个开放世界动作 RPG，预计有 30+ 种敌人类型，5 个 Boss，NPC 日常系统，以及丰富的环境交互（可破坏物体、陷阱、机关）。团队构成：3 名 AI 程序员（C++），2 名 AI 设计师（Lua），2 名动画师，4 名关卡设计师。

**你的任务**：

1. 列出 AI 程序员需要构建的基础设施清单（至少 8 项），说明每项的用途和交付形式（API / 数据资产 / 编辑器工具）。
2. 列出 AI 设计师需要的工具清单（至少 5 项），说明每项如何帮助他们"不依赖程序员"完成工作。
3. 描述 AI 程序员和 AI 设计师之间的数据契约：哪些数据结构是合约（一旦定义就不能随意修改）？哪些是设计师可以自由扩展的？
4. 设计一个"新敌人类型"的完整工作流：从关卡设计师说"我需要一个会召唤僵尸的巫妖"到可玩的 AI，每个角色做什么、交付什么、什么人需要等什么人。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **Boss 分层 AI 架构设计**。
>
> **1. 三层架构图**：
> ```
> ┌─────────────────────────────────────────────────────────┐
> │ HIGH: Boss Phase Selector (BT)                          │
> │   Selector:                                             │
> │   ├── Phase3 [Decorator: HP < 33%]                      │
> │   │   └── RunBehavior(Phase3_BT)                        │
> │   ├── Phase2 [Decorator: HP < 66%]                      │
> │   │   └── RunBehavior(Phase2_BT)                        │
> │   └── Phase1_Default                                    │
> │       └── RunBehavior(Phase1_BT)                        │
> │   [Service: UpdateBossStats @0.3s]                      │
> ├─────────────────────────────────────────────────────────┤
> │ MID: Attack Pattern FSM (per-phase)                     │
> │   Phase1_FSM: MeleeHeavy → Tracking → Orb               │
> │   Phase2_FSM: SweepAOE → Summon → MeleeLight → Orb(rare)│
> │   Phase3_FSM: FlameWave → BerserkMelee → ExplodeMinions │
> │   — 硬直中断：任意状态 → Stunned(FlinchAnim) → 恢复前状态│
> ├─────────────────────────────────────────────────────────┤
> │ LOW: Animation State Machine (Animator/AnimBP)          │
> │   Idle ↔ Walk ↔ Run ↔ Attack_Windup → Attack_Active     │
> │     → Attack_Recovery ↔ Stunned → Death                 │
> │   Phase_Transition (2-3s crossfade)                     │
> └─────────────────────────────────────────────────────────┘
> ```
>
> **2. Blackboard Key 集合（≥15 个）**：
>
> | Key | 类型 | 写权限 | 读权限 | 用途 |
> |-----|------|--------|--------|------|
> | `BossPhase` | Enum(1/2/3) | BT(PhaseSelector) | FSM, Animator | 当前阶段 |
> | `HPPercent` | Float | Service | BT, FSM, Animator | 血量百分比 |
> | `TargetActor` | Object | BT(Perception) | FSM(Action) | 当前目标 |
> | `CurrentAttackPattern` | String/Enum | FSM | Animator | 当前攻击模式名 |
> | `AttackStage` | Enum(Windup/Active/Recovery) | FSM | Animator | 攻击动画阶段 |
> | `IsTransitioning` | Bool | BT | FSM, Animator | 阶段切换中 |
> | `IsStunned` | Bool | FSM(Stunned) | BT, Animator | 硬直状态 |
> | `MinionCount` | Int | Service | BT, FSM | 存活小兵数 |
> | `FlameWaveCooldown` | Float | FSM(Phase3) | BT | 火焰波冷却计时器 |
> | `Phase1AttackProb` | Float | DataAsset | FSM | 阶段1各攻击概率(设计师可调) |
> | `Phase2AttackProb` | Float | DataAsset | FSM | 阶段2攻击概率 |
> | `Phase3AttackProb` | Float | DataAsset | FSM | 阶段3攻击概率 |
> | `BerserkSpeedMult` | Float | BT(Phase3) | Animator | 狂暴加速倍率 |
> | `LastStunnedByCrit` | Bool | FSM | BT(Service) | 最近一次硬直是否来自暴击 |
> | `TransitionTargetPhase` | Int | BT | Animator | 目标阶段(用于播放过渡动画) |
>
> **3. 阶段切换数据流（HP 66% → 阶段2 完成）**：
> ```
> 1. Service(UpdateBossStats) 每 0.3s 更新 BB.HPPercent
> 2. PhaseSelect BT 的 Decorator: HP<66% 条件从 false→true(LowerPriority Abort)
> 3.   → 中断 Phase1_BT → Selector 选择 Phase2 分支
> 4. Phase2 Sequence:
>     ├── Task: SetBlackboard(IsTransitioning=true, TransitionTargetPhase=2)
>     ├── Task: PlayPhaseTransitionAnimation()  ← 2-3秒无敌帧
>     │     └── Animator 播放过渡动画，过渡期间：
>     │         - CurrentAttackPattern="" (无攻击)
>     │         - 伤害系统读取 IsTransitioning=true → 无敌
>     │         - 收到 Damage 事件 → 无视（被过渡保护）
>     ├── Task: InitializePhase2FSM()  ← 设置 Phase2_FSM 初始状态
>     └── Task: SetBlackboard(IsTransitioning=false)
> 5. Phase2_FSM 开始正常运行
> ```
>
> **4. 设计决策点**：
> - **为什么阶段选择用 BT 而非 FSM？** 三个阶段是条件驱动的（HP 阈值 + 行为优先级），BT 的每帧条件重评估使得 HP 跨越阈值时瞬间切换——不需要在 Phase1 FSM 的每个状态中检查 "HP<66%？"。另外，如果将来添加"第 4 阶段"或"隐藏阶段（HP<5% 触发）"，只需在 BT Selector 中插入新分支，不影响已有阶段。
> - **为什么阶段内攻击序列用 FSM 而非 BT？** 攻击之间存在严格的顺序和时序依赖（"技能 A 后必须等 2 秒接技能 B"），这对应 FSM 的确定性优势。BT 的 Sequence 可以表达顺序但难以精确控制 2 秒的等待——Wait 节点不区分"等待中可中断"和"等待是必须的冷却"。FSM 的状态 + 计时器对此表达得更精确。
> - **为什么硬直用 HSM 的子状态（而非独立 BT 分支）？** 硬直是**中断性**行为——它可能在任何攻击阶段发生，结束后需要恢复到被打断前的状态。这在 BT 中需要 Pushdown Automaton（行为树不天然支持"中断后返回"），但在 HSM 中，父状态 `CombatActive` 内置一个 `OnFlinch → Stunned → Recovery → 回到之前子状态` 的通用转移即可。这正是"状态性需求强的层用有状态的机制"原则的体现。

> [!tip]- 练习 2 参考答案
> **AI Command Queue 实现**（C++ 风格，语言无关核心逻辑）。
>
> ```cpp
> struct AICommand {
>     int Type;       // MoveTo=0, Attack=1, Dodge=2, Flee=3, Heal=4
>     int Priority;
>     void* Target;   // 目标对象或位置
>     float EnqueueTime;
>     float Timeout = 3.0f;  // 默认 3 秒超时
>
>     bool operator<(const AICommand& other) const {
>         return Priority < other.Priority; // 高优先级在前
>     }
> };
>
> class AICommandQueue {
>     static const int MAX_SIZE = 5;
>     std::priority_queue<AICommand> _queue;
>     AICommand* _currentCommand = nullptr;
>     int _interruptThreshold = 2; // 新命令需高出当前 2 点优先级才能抢占
>
> public:
>     void Enqueue(const AICommand& cmd) {
>         // 1. 检查是否抢占当前命令
>         if (_currentCommand && cmd.Priority > _currentCommand->Priority + _interruptThreshold) {
>             OnCommandPreempted(*_currentCommand); // 被抢占命令丢弃（不回到队列）
>             _currentCommand = nullptr;
>         }
>         // 2. 入队
>         _queue.push(cmd);
>         // 3. 超出容量 → 踢掉最低优先级
>         if (_queue.size() > MAX_SIZE) {
>             // std::priority_queue 不直接支持移除最低优先级；
>             // 实际实现用 std::vector + std::make_heap + pop_back
>             RemoveLowestPriorityCommand();
>         }
>         // 4. 如果当前无命令 → 立即出队
>         if (!_currentCommand) DequeueNext();
>     }
>
>     void CompleteCurrent() {
>         if (_currentCommand) OnCommandCompleted(*_currentCommand);
>         _currentCommand = nullptr;
>         DequeueNext();
>     }
>
>     void Tick(float dt) {
>         // 超时检查
>         float now = GetTime();
>         // 遍历队列中所有命令检查超时（需要底层容器支持）
>         for (auto& cmd : _queue) {
>             if (now - cmd.EnqueueTime > cmd.Timeout)
>                 OnCommandExpired(cmd);
>         }
>     }
> };
> ```
>
> **测试场景推演**：
> ```
> t=0.0: Enqueue(MoveTo, P=1)  → 队: [MoveTo(1)], 当前: MoveTo(1) 执行中
> t=0.5: Enqueue(Attack, P=3)  → Attack(3) > MoveTo(1) + 2? 3>3? 否 → 不抢占
>                                → 队: [Attack(3), MoveTo(1)], 当前: MoveTo(1) 继续
> t=1.0: MoveTo 完成 → CompleteCurrent → 出队 Attack(3)
>        → 当前: Attack(3) 执行中, 队: 空
> t=2.0: Enqueue(Dodge, P=5)   → Dodge(5) > Attack(3) + 2? 5>5? 否 → 不抢占
>                                → 队: [Dodge(5)], 当前: Attack(3)
>        **关键争议**: 设计者可能期望 Dodge(5) 抢占 Attack(3)。如果 InterruptThreshold=1，
>        则 5>3+1=4 → 抢占。阈值的选择是设计权衡：高阈值减少抖动，低阈值提升响应性。
>        此处用默认阈值 2，Dodge 不抢占。
> t=2.5: Dodge 完成 → CompleteCurrent → 出队 Dodge(5) → 但 Dodge 已完成（无意义）
>        → 注意**时序 bug**: Dodge 在 2.0 入队但从未成为当前命令，2.5 时它被认为"完成"是不对的。
>        修正：只有当前命令才能被 CompleteCurrent。
>        → 重新推演：t=2.0 Dodge(5) 入队但 Attack(3) 仍在执行。
>        → t=2.5 Dodge 未被出队（因为没有当前 Dodge 在执行）
>          → 需要明确：Dodge 是"抢占后被立即执行"还是"排队等待"？
>        **设计修正**: 如果 Dodge 的语义是"立即闪避"，应该设计为抢占源（来自外部事件触发），
>        不受 InterruptThreshold 限制。给 Dodge 命令加 `bool bForcePreempt = true` 标志。
> t=3.0: Enqueue(Flee, P=4) → Flee(4) > Attack(3) + 2? 4>5? 否 → 不抢占
>        → 队: [Dodge(5), Flee(4)]
>        疑问: Attack(3) 是否还在队中？不在——因为它从未被 Enqueue（在 t=0.5 时入队，t=1.0 时出队执行）。
>        **Flee(4) 优先级低于 Dodge(5) 但高于 Attack(3)。** 队中 Dodge(5) 在 Flee(4) 前面。
>        → Flee 不应该抢占 Attack，因为优先级差 < 阈值。
> t=5.0: Enqueue(Heal, P=10) → Heal(10) > Attack(3) + 2? 10>5? 是 → 抢占！
>        → OnCommandPreempted(Attack) → Attack 被丢弃
>        → 队: [Heal(10), Dodge(5), Flee(4)]（Heal 入队 + 立即出队）
>        → 当前: Heal(10) 执行中
> ```
>
> **最终执行顺序**：`MoveTo(1) → Attack(3) → Heal(10)`（Dodge 和 Flee 被排在 Attack 之后但 Attack 被 Heal 抢占；Dodge 和 Flee 在 Heal 完成后依次出队执行）。
>
> **关键偏差分析**：t=3.0 时刻，Attack(3) 正在执行中（1.0-5.0 之间）。Flee(4) 的优先级不比 Attack(3) 高出阈值 → 不抢占。这是正确的——如果 AI 正在攻击，而"逃跑"的优先级增量不足以证明"立刻中断攻击"，Flee 应排队。如果需求是"Flee 永远立即执行"，应该设置 Priority=极大值或 bForcePreempt。

> [!tip]- 练习 3 参考答案（可选）
> **团队工作流设计**。
>
> **1. AI 程序员基础设施清单（≥8 项）**：
>
> | 项 | 用途 | 交付形式 |
> |----|------|---------|
> | AI Controller 基类 | 所有 AI 实体的决策框架，内含 BT Runner + Blackboard + Perception | C++ 类 + 蓝图可继承 |
> | 行为树运行时 | Tick 循环、节点生命周期、Observer Abort、并行执行 | C++ 引擎库 |
> | Blackboard 系统 | 三层作用域 + Observer 通知 + 跨语言读写 | C++ 类 + Lua API |
> | 感知系统 | Sight/Hearing/Damage 感知，输出为 Blackboard 写入 | C++ System + GameplayTag 事件 |
> | AI Command Queue | 带优先级的命令缓冲、抢占、超时 | C++ 组件（挂 AIController） |
> | 行为树节点库（~30 个节点） | MoveTo、PlayAnimation、Attack、FindCover 等通用节点 | C++ 类 + 编辑器暴露参数 |
> | Lua Bridge | C++ 节点 ↔ Lua 闭包的映射，Blackboard 的 userdata 封装 | C++ 绑定层 + Lua API 文档 |
> | 调试可视化 | Gameplay Debugger 扩展、行为树状态叠加、性能 profiler | C++ 组件 + Editor 面板 |
> | 数据资产管线 | 敌人配置表（行为树引用+参数覆盖）、Blackboard 模板 | DataAsset/DataTable + 编辑器 |
>
> **2. AI 设计师工具清单（≥5 项）**：
>
> | 项 | 如何帮助不依赖程序员 |
> |----|---------------------|
> | 可视化行为树编辑器 | 拖拽节点组装树结构、调整优先级、配置 Decorator 条件。不需要理解 C++。 |
> | Blackboard 变量管理器 | 在数据资产中定义新 Key、设置默认值、配置 Observer 监听关系。不需要修改代码。 |
> | 数据表驱动的参数配置 | 通过 Excel/CSV 或编辑器表格修改攻击距离、移动速度、冷却时间等可调参数。不需编译。 |
> | Lua 脚本行为定义 | 编写自定义 Action/Condition 的简单逻辑（5-20 行 Lua），热重载即时生效。不需等待 C++ 编译。 |
> | 行为树模板库 | 从程序员提供的模板（"近战战士模板""巡逻守卫模板"）开始，在此基础上修改。 |
> | 单元行为测试场景 | 一个隔离的测试关卡，设计师可以单独运行某个敌人的 BT 并观察行为。 |
>
> **3. AI 程序员 ↔ 设计师数据契约**：
>
> **合约（不可随意修改）**：
> - Blackboard Key 的类型定义（`TargetActor: Object`, `Health: Float`）——修改影响所有引用它的节点
> - BT 节点的函数签名（`ExecuteTask` 的参数列表和返回值语义）
> - 事件类型枚举（`AI.StateChanged`, `Combat.DamageReceived`）——修改破坏所有订阅者
> - C++ → Lua API 的函数签名——修改导致设计师的 Lua 脚本报错
> - World State 的 Key 集合（用于 GOAP/HTN）——修改导致规划器行为不可预测
>
> **设计师可自由扩展**：
> - 行为树的结构排列（节点顺序、新增子树）
> - Blackboard Key 的新增（不删除或修改已有 Key，只新增）
> - 数值参数（攻击距离、冷却时间、移动速度、伤害量）
> - Lua 脚本中叶子节点的具体逻辑（使用已提供的 API）
> - 敌人类型变体（基于已有 BT 模板 + 参数覆盖 + 新子树）
>
> **4. "新敌人类型"完整工作流**：
>
> ```
> Day 1: 关卡设计师提需求 "需要会召唤僵尸的巫妖"
>        → 与 AI 设计师讨论规格：巫妖的行为骨架、召唤机制细节
>
> Day 2-3: AI 设计师检查现有资源：
>     已有：远程法师 BT 模板（CasterBase_BT）、召唤系统（已有 SummonMinion Task 节点）
>     缺失：巫妖专属的"吸取生命"和"诅咒光环"行为
>     → 提需求给 AI 程序员：需要 UBTTask_DrainLife 和 UBTDecorator_CurseAura
>
> Day 3-5: AI 程序员实现两个新节点（C++）：
>     - UBTTask_DrainLife: 引导技能，类似 Channeling Spell Task
>     - UBTDecorator_CurseAura: 检查周围敌人数量，Observer Abort = Both
>     → 交付：编译后的 DLL + 在 BT Editor 中可用的新节点
>     同时：动画师制作"吸取生命"和"诅咒光环"的动画资产
>
> Day 4-6: AI 设计师在编辑器中构建巫妖 BT：
>     1. 以 CasterBase_BT 为模板
>     2. 添加"DrainLife"子树（HP<50% 时优先吸取生命）
>     3. 修改召唤逻辑：召唤僵尸（而非骷髅），增加召唤间隔
>     4. 配置 Blackboard 参数：攻击距离、施法时间、冷却
>     → 不需要等待程序员（除了节点功能已交付）
>
> Day 5-7: 关卡设计师在关卡中放置巫妖：
>     1. 拖入 AICharacter → 选择 BT 资产 → 配置 Patrol 路径
>     2. 场景中加入召唤所需的"尸体"标记点
>     → 反馈给 AI 设计师：僵尸召唤后寻路有问题（尸体标记点的 NavMesh 未 bake）
>
> Day 7-8: 迭代修复（AI 设计师 + 关卡设计师协作，很少需要程序员）
>     → 可玩版本交付
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——架构设计有多种合理方案，只要分层清晰、职责明确、数据流可追踪，就是好的设计。

## 4. 扩展阅读

### 必读材料

1. **Naughty Dog — "AI Architecture for Uncharted Series" (GDC 2012)**
   Jason Gregory 和 Jonathan Stein 详细描述了 Uncharted 的混合 AI 架构：BT 用于通用敌人行为，脚本 FSM 用于关卡特定行为，以及两者之间的"提升"（promotion）机制。重点关注他们对"什么应该在 BT 中，什么应该在脚本中"的决策框架。

2. **Bungie — "Building the AI for Destiny" (GDC 2015)**
   Damian Isla 和 David Aldridge 讨论 Destiny 的 AI 架构如何扩展 Halo 的 BT 模式以支持在线合作游戏、开放世界、以及大量不同种类的敌人。特别是"Activity Tree"概念——把行为树从单个实体扩展到管理多个 AI 实体的"活动"。

3. **Game AI Pro 1 — "Architecture" 章节**
   Game AI Pro 1 中有几篇关于架构的文章：
   - Chapter 1: "What Is Game AI?" — 定义游戏 AI 的范围和分层思想
   - Chapter 5: "Architecture of a Game AI System" — 完整的 AI 系统架构描述
   - Chapter 17: "The Simplest AI Trick in the Book" — 展示了优先级系统在简单架构中的惊人威力

4. **UE5 GameplayAbilitySystem + AI 集成**
   Epic 的官方文档和示例项目（Action RPG、Lyra）展示了 GAS 如何与 Behavior Tree 集成。重点阅读：
   - `AbilitySystemComponent` 如何通过 GameplayTags 与 BT 通信
   - `AbilityTask` 如何替代部分 BT Task 的功能（如 `AbilityTask_MoveTo`）
   - StateTree 如何作为 BT 的替代品提供状态机式的条件分支

### 推荐材料

5. **CD Projekt RED — "AI in The Witcher 3" (GDC 2015)**
   The Witcher 3 使用了一个有趣的混合方案：C++ 的 BT 引擎 + 脚本定义的子树 + 基于效用的对话选择系统。重点关注社区 NPC 的日常行为（Schedule 系统）如何与战斗 AI 共存。

6. **Rocksteady — "AI for Batman: Arkham Series" (various GDC talks)**
   Arkham 系列的"捕食者 AI"需要 BT（战术决策） + FSM（恐惧状态转换） + 严格的动画同步。John Abercrombie 的演讲讨论了如何在混合架构中处理"AI 行为看起来像是动画的一部分，动画看起来像是 AI 的一部分"的高耦合场景。

7. **Michele Colledanchise & Petter Ögren — "Behavior Trees in Robotics and AI" (2018)**
   如果你已经读了 Tutorial 14 推荐的这本学术专著，继续深入第 6-7 章。这两章讨论了 BT 与混合架构的形式化分析——特别是如何数学上证明一个混合系统（BT + FSM）的可达性和活性。

### 补充查阅

8. **Unity Behavior (2024+)**
   Unity 2024 推出了 Behavior 包（Unity Behavior），这是一个官方 BT 编辑器 + 运行时。它本身就是一个混合架构：BT + 事件系统 + Unity Animation 集成。研究它的架构如何划分"内置节点"（由 Unity 提供）和"自定义节点"（由用户扩展）。

9. **StateTree (UE5.2+)**
   StateTree 是 UE 对混合架构的形式化尝试——它在概念上融合了 FSM 的状态转移语义和 BT 的条件选择语义。阅读 UE5 的 StateTree 文档，对比它和传统 BT 的差异：什么场景下 StateTree 是更好的选择？什么场景下 BT 仍然更合适？

---

## 常见陷阱

### 陷阱 1: 过度分层导致延迟

**症状**：AI 的行为决策需要经过 4-5 层抽象才到达动画层。每层都有自己的数据结构转换和条件评估开销。

**后果**：从"检测到敌人"到"攻击动画开始播放"的延迟可能达到 2-5 帧（60fps 下 33-83ms），对玩家而言看起来"迟钝"。更严重的是，某些紧急行为（如格挡、闪避）可能因为层间传递延迟而失效。

**正确做法**：
- **紧急行为走快速通道**：格挡、闪避、被击中的硬直——这些不应该通过完整的 BT → FSM → Animator 路径。在 AIController 中增加一个 `HandleUrgentEvents()` 方法，在每帧的 Sense 阶段后、Think 阶段前运行，直接驱动 Animation 层。
- **限制层级不超过 3 层**：高层决策（BT/GOAP）、中层执行（FSM）、底层动画。如果发现需要第 4 层（如"FSM → SubFSM → SubSubFSM → Animator"），那是架构信号的警示——你可能在用 FSM 做 BT 的决策工作，考虑把决策提升到 BT 层。
- **测量端到端延迟**：在调试可视化中加入"从 Blackboard 值变化到动画状态变化的帧数"指标。如果发现有 >2 帧的延迟路径，标记为需要优化的路径。

### 陷阱 2: 过度抽象——每个行为都是独立类

**症状**：受到"干净架构"理念影响，为每一个 AI 行为创建一个 `IBehavior` 实现类。`PatrolBehavior`, `ChaseBehavior`, `AttackMeleeBehavior`, `AttackRangedBehavior`, `FleeBehavior`... 30 种行为 → 30 个类文件。

**后果**：修改一个参数（如所有攻击类行为共用的 `attackRange`）需要在 5 个类中修改。新增一个"给所有近战行为加冲锋距离"的功能需要修改每个近战行为类。**类层次提供了复用（继承），但它也创造了隐式耦合——调用方不知道哪些行为共享哪些参数。**

**正确做法**：
- **数据驱动优先于类层次**：把行为参数放到数据表或配置资产中，行为类变成通用的"参数执行器"。例如，不只 `MeleeAttack` 和 `RangedAttack` 两个类，而是一个 `AttackAction` 类 + `AttackConfig` 数据资产（包含 `range`, `damage`, `animationName`, `cooldown`）。
- **组合优于继承**：行为的差异通过组合不同组件实现，而非通过创建子类。一个 `AttackAction` + `MovementComponent` + `CooldownComponent` 的组合可以产生比单独的 `ChargedMeleeAttack` 类 + `QuickStabAttack` 类更丰富且更容易配置的行为。
- **类数量 = 行为变化轴 × 参数组合数**。如果这个乘积 < 10，用类层次是可以的。如果 > 20，切换到数据驱动。

### 陷阱 3: 层间紧耦合

**症状**：BT 的 Action 节点直接调用 FSM 的转移方法；FSM 的 OnExit 回调直接修改 BT 的节点激活状态；Animation Blueprint 读取 BT 的内部状态（而非 Blackboard）来决定动画混合。

**后果**：修改一个层的内部实现破坏另一个层的行为。例如，重构 BT 的 `Attack` 节点从 `BTTask_Attack` 拆分为 `BTTask_Windup` + `BTTask_Swing` + `BTTask_Recovery`——但因为 Animation Blueprint 直接检查"当前 BT Task 是不是 `BTTask_Attack` 类"来决定播放哪个动画，拆分后动画层全部失效。**层间的耦合应通过接口（Blackboard key + 事件类型），而非通过内部实现细节（类名、对象引用）。**

**正确做法**：
- **Blackboard 是唯一的层间状态总线**。任何层都可以读 Blackboard，但只有特定层可以写特定 key。在代码规范中明确标注每个 Blackboard key 的"写权限"（BT 写 / FSM 写 / 两者都可写）。
- **事件用于瞬态通知，不用于状态传递**。`"AttackStarted"` 事件是瞬间的——它通知"攻击开始了"，但"当前攻击的阶段"应该从 Blackboard 读取。事件不能替代状态查询——如果你发现自己在"记住上一次收到的事件"来推断当前状态，那就是用错了工具。
- **契约测试**：为 Blackboard key 和事件类型编写契约测试——验证"如果 BT 不再写入某个 key，FSM 的行为会如何？"这类测试可以及早发现层间耦合。

### 陷阱 4: 程序员 vs 设计师的工作流断裂

**症状**：程序员构建了一个强大的混合 AI 架构（BT + FSM + GAS + Blackboard + 事件系统），但设计师无法独立配置任何行为——每个新敌人类型都需要程序员参与，因为行为树的节点是 C++ 类、Blackboard 的 key 是硬编码的枚举、事件类型需要添加新的枚举值。

**后果**：设计师的迭代循环是：设计想法 → 提需求给程序员 → 等待程序员空闲 → 程序员在 2-3 天后的代码修改中实现（可能已经忘了原始需求的细节） → 设计师测试 → 发现需要调整 → 再次提需求。这个循环的单位是**天**而非**分钟**，导致设计师要么积压大量微调需求，要么放弃迭代。

**正确做法**：
- **Blackboard key 应该是字符串（或 GameplayTag），不是枚举**。设计师可以在数据资产中定义新的 key，而不需要修改 C++。
- **BT 节点的参数应该在编辑器中暴露**：一个 `BTTask_MoveTo` 不应该硬编码 `BlackboardKeyName = "MoveTarget"`，而是暴露一个 `FBlackboardKeySelector`，让设计师在编辑器中选择。
- **提供"模板行为树"**：设计师的工作不是从零构建树，而是从程序员提供的模板（"近战小兵模板"、"哨兵模板"、"Boss 阶段模板"）开始，修改参数和添加少量关卡特定节点。
- **Lua 或脚本语言的 ROI 非常高**：让行为逻辑可脚本化消除了设计师对程序员编译周期的依赖。即使只是在 Lua 中暴露 20 个最常用的 AI API（`MoveTo`, `Attack`, `FindCover`, `PlayAnimation`...），迭代速度也会有数量级的提升。

### 陷阱 5: 事件总线变成意大利面

**症状**：任何系统都可以向事件总线发布任何事件，任何系统都可以订阅任何事件。随着功能增加，谁也说不清"当 Boss 的横扫攻击命中时，到底哪些系统会响应"。

**后果**：调试场景——"为什么 Boss 攻击时会有 3 帧卡顿？" ——你发现事件处理链是：`Boss.Attack.Sweep` → ① 伤害系统（预期）② 粒子系统（预期）③ 屏幕震动（预期）④ 音效系统（预期）⑤ AI 感知系统（预期）⑥ 任务系统更新"造成伤害统计"（半预期）⑦ 一个废弃的功能原型还在监听这个事件并执行无效查询（完全意外）。

**正确做法**：
- **事件要有明确的分类和文档**：`AI.*` 事件只在 AI 系统内部使用，`Combat.*` 事件跨越 AI、伤害、动画系统，`Boss.*` 事件是 Boss 特定的。每个事件类型有明确的所有者（哪个系统负责发布它）和预期的订阅者列表。
- **事件流应该是单向的**（至少在设计意图上）。如果 AI 发布 `Combat.Attack.Hit` → 伤害系统处理 → 伤害系统发布 `Health.Changed` → AI 订阅并更新 Blackboard → BT 基于新 Health 值做决策——这是一条清晰的单向链。如果 AI 订阅了 `Combat.Attack.Hit` 而 `Combat.Attack.Hit` 又来自 AI... 你有一个事件循环。
- **运行时事件统计**：在调试构建中，记录每个事件的订阅者数量和总处理时间。如果某个事件有 >10 个订阅者，考虑是否所有订阅都是必要的。如果某个事件的平均处理时间 >1ms，考虑批量处理或降低发布频率。
- **事件不是行为定义的好工具**：不要用事件序列来编排复杂行为（"先发事件 A，等回调 B，再发事件 C..."）。这是状态机的领域。事件适合"通知"，不适合"编排"。

---

> **下一篇**: [[16-utility-ai-goap|Tutorial 16: Utility AI / GOAP / HTN 及其他范式]] — 将视野扩展到行为树和状态机之外，探索游戏 AI 的更多决策范式。
