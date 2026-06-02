# 分层状态机 (HSM) 与 Pushdown Automata

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 01-04 (所有 FSM 教程)

---

## 1. 概念讲解

### 状态爆炸：为什么平铺 FSM 不够用？

在 Tutorial 01 中，我们学习了有限状态机的基本概念。一个典型的敌人 AI 可能有 5-8 个状态：`Patrol`、`Chase`、`Attack`、`Flee`、`Dead`。这个规模下，平铺 FSM 工作得很好。

现在，让我们逐步增加复杂度。假设我们要设计一个完整的 Boss 战 AI，需要同时表达以下维度：

| 维度 | 选项 | 数量 |
|------|------|------|
| Boss 阶段 | Phase1, Phase2, Phase3 | 3 |
| 行为模式 | Idle, Patrol, Chase, MeleeAttack, RangedAttack, SpecialSkill, Stunned, Retreat, Dead | 9 |
| 目标优先级 | NearestPlayer, LowestHealth, HighestThreat, Healer | 4 |
| 情绪状态 | Calm, Alert, Enraged | 3 |

平铺 FSM 的状态数 = 各维度选项的笛卡尔积。即使只考虑前两个维度，就有 `3 × 9 = 27` 个状态。加上后两个维度，状态数暴增至 `3 × 9 × 4 × 3 = 324`。

这就是**状态爆炸（State Explosion）**问题。核心矛盾是：

> **独立关注点（concern）的笛卡尔积导致了状态的组合爆炸。平铺 FSM 强迫你将所有维度拍平到单一状态集合中。**

更糟糕的是，这些状态之间存在大量**重复行为**。`Phase1_MeleeAttack` 和 `Phase2_MeleeAttack` 的 80% 逻辑完全相同——只有伤害数值和技能冷却不同。在平铺 FSM 中，你只能复制粘贴。

### 分层状态机（Hierarchical State Machine, HSM）的核心思想

HSM 的解决方案优雅而直接：**状态可以有父子关系。父状态封装子状态共享的行为，子状态只处理差异。**

```
                    ┌─────────────────────────────────┐
                    │           Combat                 │
                    │  (共享: 锁定目标, 评估威胁,      │
                    │   接收伤害事件, 护盾管理)         │
                    │                                  │
                    │   ┌──────────┐  ┌──────────┐    │
                    │   │  Melee   │  │  Ranged  │    │
                    │   │ 攻击逻辑 │  │ 射击逻辑 │    │
                    │   └──────────┘  └──────────┘    │
                    └─────────────────────────────────┘
```

在 HSM 中：

1. **父状态（Superstate）** 定义了其所有子状态共用的行为和转移。`Combat` 父状态处理"收到伤害 → 检查是否死亡/撤退"，所有子状态自动继承。
2. **子状态（Substate）** 是当前真正活动的状态。`Melee` 和 `Ranged` 各自实现攻击逻辑，但不需要重复实现护盾管理或死亡检测。
3. **默认子状态（Default Substate）** 是首次进入父状态时自动激活的子状态。进入 `Combat` 时，根据与目标的距离自动选择 `Melee` 或 `Ranged` 作为默认子状态。
4. **转移继承（Transition Inheritance）**：父状态定义的转移对所有子状态生效。在 `Melee` 中、在 `Ranged` 中，"血量归零 → Dead"的转移规则相同——只需在 `Combat` 父状态中定义一次。

#### HSM 的转移查找规则

当事件到达时，HSM 从最内层的活动子状态开始，逐级向外（向上）查找转移规则：

```
事件输入: PlayerDetected
当前状态链: Root → Combat → Melee

查找顺序:
  1. Melee 是否处理 PlayerDetected？  → 是 → 执行转移, 结束
  2. Combat 是否处理 PlayerDetected？  → (未到达)
  3. Root 是否处理 PlayerDetected？    → (未到达)
```

如果 `Melee` 没有为 `PlayerDetected` 定义转移，HSM 自动向上走到 `Combat`。如果 `Combat` 也没有，继续向上到 `Root`。如果没有任何层级处理该事件，事件被丢弃——等价于 FSM 中的"自转移/忽略"。

这套规则和面向对象中的**虚函数重写（virtual method override）**完全同构：
- 子状态 = 子类的 override 方法
- 父状态 = 基类的 virtual 方法
- 子状态未处理 → 调用基类实现（向上查找）

#### 具体例子：Boss 三阶段

用 HSM 而非平铺 FSM，Boss 战的层次结构如下：

```
BossRoot
├── Phase1 (父状态)
│   ├── Idle
│   ├── MeleeAttack
│   └── RangedAttack
├── Phase2 (父状态)          ← 继承 Phase1 的所有子状态结构，但修改伤害参数
│   ├── Idle
│   ├── MeleeAttack           ← 增加了 AOE 近战技能
│   ├── RangedAttack
│   └── SummonMinions         ← Phase2 新增
└── Phase3 (父状态)           ← 再次修改
    ├── Idle
    ├── MeleeAttack           ← 攻击速度翻倍
    ├── RangedAttack
    ├── SummonMinions
    ├── DesperationSkill      ← Phase3 新增
    └── SelfDestruct
```

关键设计决策：

- **Phase 之间的转移**（如 `Phase1 → Phase2`）在 `BossRoot` 层定义，条件是 `health < 66%`。无论 Phase1 的哪个子状态在活动，血量跌破阈值时都会触发阶段切换。
- **Phase 内部的转移**（如 `Idle → MeleeAttack`）在对应的 Phase 父状态中定义。
- **所有 Phase 共用的转移**（如 `health <= 0 → Dead`）在 `BossRoot` 中定义，只需一次。

这个设计将 30+ 个平铺状态压缩为 3 个父状态 + 约 12 个子状态，且去除了所有重复代码。

### Pushdown Automata：状态历史与中断

HSM 解决了"状态太多"的问题，但还有另一个平铺 FSM 无法处理的需求：**中断后恢复**。

经典场景：一个 NPC 在巡逻（`Patrol`），突然检测到玩家。它切换到 `Chase` → `Combat`。战斗结束后，它应该回到哪里？

- **回到巡逻路径的起点？** 不好——玩家每次都从同一点出现，显得很傻。
- **回到巡逻路径的最后一个检查点？** 好一些，但不够自然。
- **从中断点继续巡逻？** 这才是符合玩家预期的行为。NPC 应该记得自己巡逻到哪一步了。

平铺 FSM 的问题在于：从 `Patrol` 切换到 `Chase` 时，`Patrol` 状态的内部信息（当前路径点索引、已巡逻时间、面朝方向等）**丢失了**。`Patrol` 被彻底替换成了 `Chase`。当 `Chase` 结束后想"回去"，FSM 并不知道"回去"是什么意思——它只能硬编码一个静态目标状态。

**Pushdown Automata（下推自动机）** 通过一个**状态栈**来解决这个问题：

```
初始状态:
  [ Patrol ]              ← 栈顶 = 当前状态

检测到玩家 → Push(Combat):
  [ Patrol, Combat ]      ← Combat 在栈顶, Patrol 被压在下面

战斗结束 → Pop():
  [ Patrol ]              ← Patrol 回到栈顶，从中断点继续
```

Pushdown Automata 与平铺 FSM 相比，在原语上有三个操作：

| 操作 | 效果 | 使用场景 |
|------|------|----------|
| **Push(state)** | 将新状态压入栈顶，新状态成为当前状态 | 开始一个会中断当前行为的新行为 |
| **Pop()** | 弹出栈顶状态，暴露下一个状态并恢复 | 中断行为结束，回到之前的状态 |
| **Switch(state)** | 替换栈顶状态（等价于 Pop + Push） | 常规的状态转移（与平铺 FSM 一致） |

这个区别至关重要：**HSM 解决的是"同时存在的状态维度太多"的问题（用层次结构压缩组合空间）；Pushdown Automata 解决的是"需要记住我从哪来"的问题（用栈保存历史）。**

两者可以组合使用：一个 HSM 的每个层级内部可以使用 Pushdown 机制来处理中断。事实上，很多生产级游戏 AI ——包括 Halo 2——同时使用了层次化组织 + 行为栈。

#### 中断示例：更复杂的 NPC 行为栈

```
时间线          状态栈                          说明
──────────────────────────────────────────────────────────
T0:  [ Patrol ]                              正常巡逻
T1:  [ Patrol, InvestigateSound ]            听到枪声 → Push
T2:  [ Patrol, InvestigateSound, Combat ]     发现敌人 → Push
T3:  [ Patrol, InvestigateSound, Combat,     护盾破裂 → Push
       SelfPreservation ]
T4:  [ Patrol, InvestigateSound, Combat ]     护盾恢复 → Pop
T5:  [ Patrol, InvestigateSound ]             击败敌人 → Pop
T6:  [ Patrol, InvestigateSound ]             继续调查声音来源
T7:  [ Patrol ]                               调查完毕 → Pop
T8:  [ Patrol ]                               回到巡逻路径的中断点
```

这个栈深度为 4 的行为序列如果用平铺 FSM 实现，需要 `4! = 24` 个状态（每个栈组合对应一个"复合状态"）来追踪"从哪来，到哪去"。Pushdown Automata 用 4 个状态 + 1 个栈实现了同样的效果。

### 与行为树的关系（预告）

如果你已经听说过行为树（Behavior Tree, BT），可能注意到上面的"状态栈"与行为树的"行为堆栈"看起来很相似。这并非巧合：

- **HSM 的本质是在状态间共享转移逻辑**（层次继承），行为树在节点间共享条件判断（Decorator/Condition 向上传播）。
- **Pushdown Automata 的本质是用栈管理执行上下文**，行为树用类似的栈来管理复合节点（Composite）的执行进度。

事实上，Halo 2 的 AI 系统——Damian Isla 在 GDC 2005 著名的演讲 *"Managing Complexity in the Halo 2 AI"* 中将其描述为"有限状态机与模糊逻辑引擎的私生子"——本质上就是一个**优先级排序的行为树**，其中行为节点组成层次化子树，并通过 impulse 机制实现 Push/Pop 式的中断。

我们将在 Tutorial 06-10 中深入学习行为树。届时你会看到 HSM 和 Pushdown Automata 的概念如何自然地过渡到行为树架构。

### 真实游戏案例

#### Halo 2: 从平铺 FSM 到行为树

Halo 1 使用的是传统平铺 FSM。一个精英（Elite）的状态转移图约有 15-20 个状态。随着 AI 设计需求在 Halo 2 中急剧增长（更多种族、更多武器、载具战、小队协作），Bungie 面临两个关键的复杂度问题：

1. **状态数量爆炸**：15 种行为 × 3 种情绪 × 3 种武器类型 = 135 个理论状态。
2. **中断行为的不可预测性**：精英在战斗中可能因护盾破裂而中断攻击去寻求掩体，掩体行为结束后应回到之前的战斗状态——而非"重置到空闲"。

Bungie 的解决方案是引入**行为树 + 优先级系统**。从 Behavior List 中可以看到清晰的层次结构：

- `Root` → `Engage`（有敌人时运行）→ `Fight` / `MeleeCharge` / `GrenadeImpulse` ...
- `Root` → `SelfPreservation`（危险时运行）→ `Cover` / `Avoid` / `EvasionImpulse` ...
- `Root` → `Search`（敌人丢失后运行）→ `Investigate` / `Pursuit` ...
- `Root` → `Idle`（无敌人时运行）→ `Wander` / `Patrol` / `FallAsleep` ...

关键设计：**impulse 行为**。标注为 *impulse* 的行为（如 `GrenadeImpulse`、`DangerCoverImpulse`）会临时插入到行为栈顶部。这一机制正是 Pushdown Automata 的 Push/Pop 操作——当前行为被暂停，impulse 执行完成后自动恢复。

Halo 2 的行为系统虽然被称为"行为树"，但其**层次化的根行为 → 子树结构**加上**impulse 的中断-Push-执行-Pop 机制**，完美体现了 HSM + Pushdown Automata 的核心设计。

#### Unreal Engine 3: UnrealScript 状态继承

Unreal Engine 3 的 UnrealScript 在语言级别支持状态继承——这是 HSM 在游戏引擎中最直接的实现：

```unrealscript
// UnrealScript 中的状态继承（UE3 语法）
state Idle {
    // 所有 idle 子状态共享的事件处理
    event SeePlayer() {
        GotoState('Combat');
    }
}

state IdlePatrol extends Idle {
    // 继承 SeePlayer → Combat 的转移
    // 添加巡逻专属逻辑
    event BeginState() { /* 沿路径点移动 */ }
}
```

UnrealScript 的 `extends` 关键字直接作用于状态，使得 `IdlePatrol` 自动继承 `Idle` 中定义的所有事件处理函数和转移规则。这与 HSM 的"父状态定义转移，子状态继承"完全一致。

#### Unreal Engine 5: StateTree

UE5 的 StateTree 系统是 HSM 理念的现代演进。StateTree 支持：

- **层次化状态**：父状态可以包含子状态树，形成多级层次。
- **条件驱动的转移**：不再使用"事件 + 条件"二元组，而是每个 tick 评估所有转移条件（类似行为树的 Condition）。
- **Task 节点**：状态内部可以包含多个 Task（类似行为树的 Action 节点），实现状态行为的模块化。
- **Evaluator 动态切换**：在状态内部运行的持续性评估器，可以驱动子状态的动态选择。

StateTree 本质上是 **HSM + BT 的融合体**——用 HSM 的层次结构管理"模式切换"，用 BT 的 Task/Evaluator 管理"模式内的行为"。

---

### 平铺 FSM vs HSM：状态数对比

以下是具体场景下的状态数对比：

| 场景 | 平铺 FSM 状态数 | HSM 状态数 | 压缩比 |
|------|----------------|-----------|--------|
| 基础敌人 AI（4 行为 × 2 武器） | 8 | 父 2 + 子 4 = 6 | 25% |
| Boss 三阶段（3 阶段 × 6 行为） | 18 | 父 3 + 子 ~12 = 15 | ~17% |
| 玩家角色（站立/蹲伏/跳跃 × 持枪/空手 × 健康/受伤） | 12 | 父 5 + 子 ~10 = 15 | -25% |
| 复杂 NPC（4 情绪 × 8 行为 × 3 目标优先级） | 96 | 父 ~4 + 子 ~20 = 24 | 75% |
| RTS 单位（5 姿态 × 4 指令 × 3 阵型） | 60 | 父 ~7 + 子 ~15 = 22 | 63% |

注意最后一行：HSM 在某些场景下可能比平铺 FSM 有更多"声明"状态（因为你需要显式定义层次）。但**维护成本**远低于平铺 FSM——因为每个状态只包含其特有的逻辑，共享逻辑在父状态中定义一次。

实际上，压缩比并非关键指标——**更重要的是你的代码中消除了跨状态的重复**。一个 20 状态的 HSM 比一个 18 状态的平铺 FSM 容易维护 10 倍。

---

## 2. 代码示例

### 示例 A: HSM in C# (Unity)

下面的实现展示了一个完整的 HSM 框架，包括父状态/子状态的层次化管理、转移向上查找、Enter/Exit 生命周期。

```csharp
// ============================================================
// HSM Framework for Unity (C#)
// 核心: HierarchicalState 支持父子关系, 转移逐级向上查找
// ============================================================

using System;
using System.Collections.Generic;

// --- 1. 定义转移条件 ---
public struct Transition
{
    public Type TargetState;      // 目标状态类型
    public Func<bool> Condition;   // 转移条件

    public Transition(Type target, Func<bool> condition)
    {
        TargetState = target;
        Condition = condition;
    }
}

// --- 2. 分层状态基类 ---
public abstract class HierarchicalState
{
    protected HierarchicalStateMachine fsm;

    // 层次关系
    public HierarchicalState Parent { get; private set; }
    public HierarchicalState CurrentChild { get; private set; }

    // 转移列表——每个状态维护自己的转移规则
    protected List<Transition> transitions = new List<Transition>();

    // 默认子状态类型（首次进入时激活）
    protected virtual Type DefaultChildType => null;

    // --- 生命周期 ---
    public virtual void OnEnter() { }
    public virtual void OnExit() { }
    public virtual void OnUpdate() { }

    // --- 层次管理 ---
    public void SetParent(HierarchicalState parent)
    {
        Parent = parent;
    }

    protected void ActivateChild(Type childType)
    {
        if (childType == null) return;

        // 如果同类型子状态已激活，不重复进入
        if (CurrentChild != null && CurrentChild.GetType() == childType)
            return;

        // 退出旧子状态
        CurrentChild?.OnExit();

        // 激活新子状态
        CurrentChild = fsm.GetOrCreateState(childType);
        CurrentChild.SetParent(this);
        CurrentChild.OnEnter();

        // 递归激活默认子状态（进入链）
        var defaultChild = CurrentChild.DefaultChildType;
        if (defaultChild != null)
        {
            CurrentChild.ActivateChild(defaultChild);
        }
    }

    // --- 转移查找：从最深层子状态逐级向上 ---
    public virtual Type FindTransition()
    {
        // 1. 先让当前子状态查找（深度优先）
        if (CurrentChild != null)
        {
            var childTransition = CurrentChild.FindTransition();
            if (childTransition != null) return childTransition;
        }

        // 2. 本状态查找
        foreach (var t in transitions)
        {
            if (t.Condition()) return t.TargetState;
        }

        // 3. 向上委托给父状态
        return Parent?.FindTransition();
    }

    // 添加转移规则
    protected void AddTransition<T>(Func<bool> condition) where T : HierarchicalState
    {
        transitions.Add(new Transition(typeof(T), condition));
    }
}

// --- 3. HSM 机器管理器 ---
public class HierarchicalStateMachine
{
    private HierarchicalState rootState;
    private HierarchicalState currentState;

    // 状态实例缓存（避免重复分配）
    private Dictionary<Type, HierarchicalState> stateCache
        = new Dictionary<Type, HierarchicalState>();

    public HierarchicalStateMachine(HierarchicalState root)
    {
        rootState = root;
        stateCache[root.GetType()] = root;
    }

    public T GetOrCreateState<T>() where T : HierarchicalState, new()
    {
        var type = typeof(T);
        if (!stateCache.TryGetValue(type, out var state))
        {
            state = new T();
            stateCache[type] = state;
        }
        return (T)state;
    }

    public HierarchicalState GetOrCreateState(Type type)
    {
        if (!stateCache.TryGetValue(type, out var state))
        {
            state = (HierarchicalState)Activator.CreateInstance(type);
            stateCache[type] = state;
        }
        return state;
    }

    // 初始化：激活根状态 + 根状态的默认子状态链
    public void Start()
    {
        currentState = rootState;
        rootState.OnEnter();

        var defaultChild = rootState.DefaultChildType;
        if (defaultChild != null)
        {
            rootState.ActivateChild(defaultChild);
        }
    }

    // 每帧更新
    public void Update()
    {
        if (currentState == null) return;

        // 1. 评估转移（从最深子状态开始向上查找）
        var targetType = currentState.FindTransition();

        if (targetType != null)
        {
            ChangeState(targetType);
        }

        // 2. 更新最深层的活动子状态
        GetDeepestActiveState()?.OnUpdate();
    }

    // 获取当前最深层的活动子状态
    private HierarchicalState GetDeepestActiveState()
    {
        var node = currentState;
        while (node?.CurrentChild != null)
        {
            node = node.CurrentChild;
        }
        return node;
    }

    // 切换状态
    public void ChangeState(Type targetType)
    {
        var target = GetOrCreateState(targetType);

        // 找到当前状态和目标状态的共同祖先
        var ancestor = FindCommonAncestor(currentState, target);

        // 从当前状态逐级退出到共同祖先
        var exitNode = currentState;
        while (exitNode != null && exitNode != ancestor)
        {
            exitNode.OnExit();
            exitNode = exitNode.Parent;
        }

        // 如果目标在祖先的另一个分支，清空祖先的当前子状态
        if (ancestor != null)
        {
            ancestor.CurrentChild = null;
        }

        // 从共同祖先逐级进入目标状态
        var enterPath = new List<HierarchicalState>();
        var enterNode = target;
        while (enterNode != null && enterNode != ancestor)
        {
            enterPath.Add(enterNode);
            enterNode = enterNode.Parent;
        }
        enterPath.Reverse();

        HierarchicalState currentParent = ancestor;
        foreach (var state in enterPath)
        {
            if (currentParent != null)
            {
                currentParent.CurrentChild = state;
                state.SetParent(currentParent);
            }
            state.OnEnter();
            currentParent = state;
        }

        currentState = target;

        // 激活目标的默认子状态链
        var defaultChild = target.DefaultChildType;
        if (defaultChild != null)
        {
            target.ActivateChild(defaultChild);
        }
    }

    // 找到两个状态在层次树中的最近共同祖先
    private HierarchicalState FindCommonAncestor(HierarchicalState a, HierarchicalState b)
    {
        if (a == null || b == null) return null;

        var ancestors = new HashSet<HierarchicalState>();
        var node = a;
        while (node != null)
        {
            ancestors.Add(node);
            node = node.Parent;
        }

        node = b;
        while (node != null)
        {
            if (ancestors.Contains(node)) return node;
            node = node.Parent;
        }

        return null;
    }
}

// ============================================================
// 具体 AI 实现：嵌套敌人 AI
// ============================================================

// --- 根状态 ---
public class EnemyRoot : HierarchicalState
{
    public EnemyRoot()
    {
        // 所有子状态共用的全局转移
        AddTransition<DeadState>(() => fsm.GetOrCreateState<EnemyData>().health <= 0);
    }

    protected override Type DefaultChildType => typeof(IdleParent);
}

// --- Idle 父状态 ---
public class IdleParent : HierarchicalState
{
    public IdleParent()
    {
        // idle 状态下，检测到玩家 → 进入 Combat
        AddTransition<CombatParent>(() => fsm.GetOrCreateState<EnemyData>().HasDetectedPlayer());
    }

    protected override Type DefaultChildType => typeof(PatrolState);

    public override void OnEnter()
    {
        // 共享的进入 Idle 逻辑：放松姿态, 收起武器
        Debug.Log("[Idle] Relaxing posture");
    }
}

// --- Idle 子状态: Patrol ---
public class PatrolState : HierarchicalState
{
    private EnemyData data => fsm.GetOrCreateState<EnemyData>();
    private int currentWaypoint = 0;

    public PatrolState()
    {
        // 巡逻中站太久 → 切换到 Stand
        AddTransition<StandState>(() => data.idleTimer > 10f);
    }

    public override void OnEnter()
    {
        currentWaypoint = 0;
        Debug.Log("[Patrol] Starting patrol route");
    }

    public override void OnUpdate()
    {
        // 沿路径点移动
        var target = data.patrolWaypoints[currentWaypoint];
        data.MoveTowards(target);

        if (data.DistanceTo(target) < 0.5f)
        {
            currentWaypoint = (currentWaypoint + 1) % data.patrolWaypoints.Length;
        }

        data.idleTimer += Time.deltaTime;
    }

    public override void OnExit()
    {
        Debug.Log("[Patrol] Stopping patrol");
    }
}

// --- Idle 子状态: Stand ---
public class StandState : HierarchicalState
{
    public override void OnEnter()
    {
        Debug.Log("[Stand] Standing guard");
    }

    public override void OnUpdate()
    {
        // 原地站立，缓慢环顾
    }
}

// --- Combat 父状态 ---
public class CombatParent : HierarchicalState
{
    public CombatParent()
    {
        // Combat 共享转移：丢失目标 → 回到 Idle
        AddTransition<IdleParent>(() =>
            fsm.GetOrCreateState<EnemyData>().timeSinceLastSighting > 5f);
    }

    protected override Type DefaultChildType
    {
        get
        {
            // 根据与目标的距离选择默认子状态
            var data = fsm.GetOrCreateState<EnemyData>();
            return data.distanceToTarget < 3f ? typeof(MeleeState) : typeof(RangedState);
        }
    }

    public override void OnEnter()
    {
        Debug.Log("[Combat] Engaging target!");
    }
}

// --- Combat 子状态: Melee ---
public class MeleeState : HierarchicalState
{
    private float attackCooldown = 0f;

    public MeleeState()
    {
        // 目标远离 → 切换到 Ranged
        AddTransition<RangedState>(() =>
            fsm.GetOrCreateState<EnemyData>().distanceToTarget > 5f);
    }

    public override void OnUpdate()
    {
        attackCooldown -= Time.deltaTime;
        var data = fsm.GetOrCreateState<EnemyData>();

        if (attackCooldown <= 0)
        {
            data.MeleeAttack();
            attackCooldown = 1.2f;
        }

        data.FaceTarget();
    }
}

// --- Combat 子状态: Ranged ---
public class RangedState : HierarchicalState
{
    private float fireCooldown = 0f;

    public RangedState()
    {
        // 目标靠近 → 切换到 Melee
        AddTransition<MeleeState>(() =>
            fsm.GetOrCreateState<EnemyData>().distanceToTarget < 2f);
    }

    public override void OnUpdate()
    {
        fireCooldown -= Time.deltaTime;
        var data = fsm.GetOrCreateState<EnemyData>();

        data.MaintainDistance();
        if (fireCooldown <= 0)
        {
            data.RangedAttack();
            fireCooldown = 0.8f;
        }
    }
}

// --- Dead 状态（终态） ---
public class DeadState : HierarchicalState
{
    public override void OnEnter()
    {
        Debug.Log("[Dead] Playing death animation");
    }

    // 终态：不处理任何转移，不定义任何子状态
    public override Type FindTransition() => null;
}

// --- 共享数据容器 ---
public class EnemyData : HierarchicalState
{
    // EnemyData 不作为逻辑状态存在，而是数据持有者
    // 放在状态缓存中方便所有状态访问
    public float health = 100f;
    public float distanceToTarget;
    public float timeSinceLastSighting;
    public float idleTimer;
    public Vector3[] patrolWaypoints;

    public bool HasDetectedPlayer() => distanceToTarget < 15f;
    public void MoveTowards(Vector3 target) { /* ... */ }
    public float DistanceTo(Vector3 target) => 0f;
    public void MeleeAttack() { /* ... */ }
    public void RangedAttack() { /* ... */ }
    public void FaceTarget() { /* ... */ }
    public void MaintainDistance() { /* ... */ }

    public override Type FindTransition() => null; // 数据状态不参与转移
}
```

**代码要点解析**：

1. **`FindTransition()` 的递归向上查找**：这是 HSM 的核心机制。最深子状态先查找，未命中则委托给父状态。与 OOP 虚函数的调用链完全一致。

2. **`ChangeState()` 中的共同祖先查找**：当从 `PatrolState`（位于 `IdleParent` 下）切换到 `MeleeState`（位于 `CombatParent` 下）时，需要先退出 `PatrolState → IdleParent`，再进入 `CombatParent → MeleeState`。共同祖先是 `EnemyRoot`。

3. **转移定义在构造函数中**：每个状态在构造时声明自己的转移规则。这种声明式风格便于阅读和调试——你一眼就能看出每个状态会响应哪些条件。

4. **`DefaultChildType`**：首次进入父状态时自动激活的默认子状态。`CombatParent` 根据距离动态选择，体现了数据驱动的默认状态选择。

5. **状态实例缓存**：`stateCache` 字典确保同一类型的状态只有一个实例（享元模式）。如果你的状态需要存储每个实体的独立数据（如 `PatrolState.currentWaypoint`），将数据放在共享数据容器中（如 `EnemyData`），而不是状态实例中——因为可能有多个敌人同时使用同一个 `PatrolState`。

### 示例 B: Pushdown Automata in C++ (Unreal)

下面的实现展示了一个完整的 Pushdown Automata 系统，支持 Push/Pop/Switch 三种操作，以及中断驱动的事件响应。

```cpp
// ============================================================
// Pushdown Automata for Unreal Engine (C++)
// 核心: 状态栈 + Push/Pop 实现中断-恢复语义
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "AIPushdownState.h"
#include "AIPushdownStateMachine.generated.h"

// --- 1. 状态基类 ---
UCLASS(Abstract)
class UAIPushdownState : public UObject
{
    GENERATED_BODY()

public:
    // 状态名称（调试用）
    UPROPERTY(BlueprintReadOnly)
    FName StateName;

    // --- 生命周期 ---
    // Enter: 首次进入状态（Push 或 Switch 触发）
    virtual void OnEnter(AAIController* Owner) {}

    // Exit: 离开状态（Pop 或 Switch 触发）
    virtual void OnExit(AAIController* Owner) {}

    // Resume: 从被压住的状态恢复到栈顶（Pop 触发）
    // 与 OnEnter 不同：Resume 意味着状态之前被中断过，需要恢复上下文
    virtual void OnResume(AAIController* Owner) {}

    // Pause: 被新状态压住（Push 触发）
    // 保存当前上下文以便后续 Resume 恢复
    virtual void OnPause(AAIController* Owner) {}

    // Tick: 每帧更新（仅栈顶状态被 tick）
    virtual void OnTick(AAIController* Owner, float DeltaTime) {}

    // HandleEvent: 处理事件。返回 true 表示事件被消费
    virtual bool HandleEvent(AAIController* Owner, FName EventName) { return false; }
};

// --- 2. Pushdown 状态机 ---
UCLASS()
class UAIPushdownStateMachine : public UObject
{
    GENERATED_BODY()

public:
    void Initialize(AAIController* InOwner)
    {
        Owner = InOwner;
    }

    // --- 状态栈操作 ---

    /**
     * Push: 将新状态压入栈顶。
     * 当前栈顶状态被"暂停"（OnPause），新状态成为活动状态（OnEnter）。
     * 使用场景: 战斗中断巡逻、调查声音中断巡逻、护盾破裂中断战斗。
     */
    void PushState(TSubclassOf<UAIPushdownState> StateClass)
    {
        if (!StateClass) return;

        // 1. 暂停当前栈顶状态
        if (StateStack.Num() > 0)
        {
            StateStack.Top()->OnPause(Owner);
            UE_LOG(LogTemp, Log, TEXT("[PDA] Paused: %s"),
                *StateStack.Top()->StateName.ToString());
        }

        // 2. 创建并压入新状态
        UAIPushdownState* NewState = NewObject<UAIPushdownState>(this, StateClass);
        StateStack.Push(NewState);

        // 3. 进入新状态
        NewState->OnEnter(Owner);
        UE_LOG(LogTemp, Log, TEXT("[PDA] Pushed: %s (depth=%d)"),
            *NewState->StateName.ToString(), StateStack.Num());
    }

    /**
     * Pop: 弹出栈顶状态。
     * 当前状态被销毁（OnExit），下面的状态恢复（OnResume）。
     * 使用场景: 战斗结束恢复巡逻、调查完毕恢复巡逻。
     */
    void PopState()
    {
        if (StateStack.Num() == 0) return;

        // 1. 退出并销毁栈顶状态
        UAIPushdownState* OldState = StateStack.Pop();
        OldState->OnExit(Owner);
        UE_LOG(LogTemp, Log, TEXT("[PDA] Popped: %s (depth=%d)"),
            *OldState->StateName.ToString(), StateStack.Num());

        // 2. 恢复新的栈顶状态
        if (StateStack.Num() > 0)
        {
            StateStack.Top()->OnResume(Owner);
            UE_LOG(LogTemp, Log, TEXT("[PDA] Resumed: %s"),
                *StateStack.Top()->StateName.ToString());
        }
    }

    /**
     * Switch: 替换栈顶状态。
     * 等价于 Pop() + Push() 但不触发 Resume/Pause。
     * 使用场景: 巡逻 → 追击（不是中断关系，而是替换关系）。
     */
    void SwitchState(TSubclassOf<UAIPushdownState> StateClass)
    {
        if (StateStack.Num() > 0)
        {
            UAIPushdownState* OldState = StateStack.Pop();
            OldState->OnExit(Owner);
        }

        UAIPushdownState* NewState = NewObject<UAIPushdownState>(this, StateClass);
        StateStack.Push(NewState);
        NewState->OnEnter(Owner);

        UE_LOG(LogTemp, Log, TEXT("[PDA] Switched to: %s"),
            *NewState->StateName.ToString());
    }

    /**
     * PopUntil: 弹出直到指定类型的状态成为栈顶。
     * 用于"从任何嵌套中断中直接回到某个基线状态"。
     */
    void PopUntil(TSubclassOf<UAIPushdownState> StateClass)
    {
        while (StateStack.Num() > 0 &&
               !StateStack.Top()->IsA(StateClass))
        {
            PopState();
        }
    }

    /**
     * SendEvent: 向状态栈分发事件。
     * 从栈顶向下遍历，第一个消费事件的状态处理它。
     * 这提供了类似 HSM 的"向上冒泡"语义。
     */
    bool SendEvent(FName EventName)
    {
        for (int i = StateStack.Num() - 1; i >= 0; --i)
        {
            if (StateStack[i]->HandleEvent(Owner, EventName))
            {
                return true;
            }
        }
        return false;
    }

    // --- 每帧更新 ---
    void Tick(float DeltaTime)
    {
        if (StateStack.Num() > 0)
        {
            StateStack.Top()->OnTick(Owner, DeltaTime);
        }
    }

    // --- 调试辅助 ---
    void DebugPrintStack() const
    {
        UE_LOG(LogTemp, Log, TEXT("=== PDA Stack (top first) ==="));
        for (int i = StateStack.Num() - 1; i >= 0; --i)
        {
            UE_LOG(LogTemp, Log, TEXT("  [%d] %s"), i,
                *StateStack[i]->StateName.ToString());
        }
    }

    UAIPushdownState* GetCurrentState() const
    {
        return StateStack.Num() > 0 ? StateStack.Top() : nullptr;
    }

    int32 GetStackDepth() const { return StateStack.Num(); }

private:
    UPROPERTY()
    AAIController* Owner;

    UPROPERTY()
    TArray<UAIPushdownState*> StateStack;
};

// ============================================================
// 具体状态实现
// ============================================================

// --- Patrol 状态 ---
UCLASS()
class UPatrolState : public UAIPushdownState
{
    GENERATED_BODY()

public:
    UPatrolState() { StateName = TEXT("Patrol"); }

    int32 CurrentWaypointIndex = 0;

    virtual void OnEnter(AAIController* Owner) override
    {
        UE_LOG(LogTemp, Log, TEXT("[Patrol] Starting patrol from waypoint %d"),
            CurrentWaypointIndex);
    }

    virtual void OnPause(AAIController* Owner) override
    {
        // 保存巡逻上下文已在成员变量中，无需额外操作
        UE_LOG(LogTemp, Log, TEXT("[Patrol] Pausing at waypoint %d"),
            CurrentWaypointIndex);
    }

    virtual void OnResume(AAIController* Owner) override
    {
        UE_LOG(LogTemp, Log, TEXT("[Patrol] Resuming from waypoint %d"),
            CurrentWaypointIndex);
        // CurrentWaypointIndex 被保留——从中断点继续
    }

    virtual void OnTick(AAIController* Owner, float DeltaTime) override
    {
        // 沿路径点移动巡逻逻辑
    }

    virtual bool HandleEvent(AAIController* Owner, FName EventName) override
    {
        if (EventName == TEXT("EnemyDetected"))
        {
            // 巡逻中检测到敌人→ Push Combat (中断巡逻)
            if (auto* FSM = Owner->FindComponentByClass<UAIPushdownStateMachine>())
            {
                FSM->PushState(UCombatState::StaticClass());
            }
            return true;
        }
        return false;
    }
};

// --- Combat 状态 ---
UCLASS()
class UCombatState : public UAIPushdownState
{
    GENERATED_BODY()

public:
    UCombatState() { StateName = TEXT("Combat"); }

    virtual void OnEnter(AAIController* Owner) override
    {
        UE_LOG(LogTemp, Log, TEXT("[Combat] Engaging enemy!"));
    }

    virtual bool HandleEvent(AAIController* Owner, FName EventName) override
    {
        if (EventName == TEXT("ShieldBroken"))
        {
            // 护盾破裂 → Push SelfPreservation (中断战斗)
            if (auto* FSM = Owner->FindComponentByClass<UAIPushdownStateMachine>())
            {
                FSM->PushState(USelfPreservationState::StaticClass());
            }
            return true;
        }
        if (EventName == TEXT("EnemyDefeated"))
        {
            // 击败敌人 → Pop 回到巡逻
            if (auto* FSM = Owner->FindComponentByClass<UAIPushdownStateMachine>())
            {
                FSM->PopState(); // Combat 被 Pop，Patrol 自动恢复
            }
            return true;
        }
        return false;
    }

    virtual void OnTick(AAIController* Owner, float DeltaTime) override
    {
        // 战斗逻辑：移动、射击、评估威胁
    }
};

// --- SelfPreservation 状态 (护盾破裂后寻求掩体) ---
UCLASS()
class USelfPreservationState : public UAIPushdownState
{
    GENERATED_BODY()

public:
    USelfPreservationState() { StateName = TEXT("SelfPreservation"); }

    float ShieldRegenTimer = 0f;

    virtual void OnEnter(AAIController* Owner) override
    {
        ShieldRegenTimer = 3.0f;
        UE_LOG(LogTemp, Log, TEXT("[SelfPreserve] Taking cover!"));
        // 寻找最近的掩体并移动过去
    }

    virtual void OnTick(AAIController* Owner, float DeltaTime) override
    {
        ShieldRegenTimer -= DeltaTime;
        if (ShieldRegenTimer <= 0)
        {
            // 护盾恢复 → Pop 回到战斗
            if (auto* FSM = Owner->FindComponentByClass<UAIPushdownStateMachine>())
            {
                FSM->PopState();
            }
        }
    }

    virtual bool HandleEvent(AAIController* Owner, FName EventName) override
    {
        if (EventName == TEXT("HealthCritical"))
        {
            // 血量极低 → 不回到战斗，直接撤退
            if (auto* FSM = Owner->FindComponentByClass<UAIPushdownStateMachine>())
            {
                FSM->PopUntil(UPatrolState::StaticClass()); // 弹出到 Patrol
                FSM->SwitchState(URetreatState::StaticClass()); // 替换为 Retreat
            }
            return true;
        }
        return false;
    }
};

// --- Retreat 状态 ---
UCLASS()
class URetreatState : public UAIPushdownState
{
    GENERATED_BODY()

public:
    URetreatState() { StateName = TEXT("Retreat"); }

    virtual void OnEnter(AAIController* Owner) override
    {
        UE_LOG(LogTemp, Log, TEXT("[Retreat] Running away!"));
    }
};

// --- 使用示例 (在 AIController 中) ---
// void AMyAIController::BeginPlay()
// {
//     StateMachine = NewObject<UAIPushdownStateMachine>(this);
//     StateMachine->Initialize(this);
//     StateMachine->PushState(UPatrolState::StaticClass());
// }
//
// void AMyAIController::Tick(float DeltaTime)
// {
//     StateMachine->Tick(DeltaTime);
// }
//
// void AMyAIController::OnPerceptionUpdated(AActor* Actor, FAIStimulus Stimulus)
// {
//     if (Stimulus.WasSuccessfullySensed())
//     {
//         StateMachine->SendEvent(TEXT("EnemyDetected"));
//     }
// }
```

**代码要点解析**：

1. **Push/Pop 的语义严格区分**：`PushState` 触发 `OnPause`（保存上下文）+ `OnEnter`（进入新状态）。`PopState` 触发 `OnExit`（清理）+ `OnResume`（恢复上下文）。这四个回调的调用顺序是 PDA 正确性的核心。

2. **`OnResume` vs `OnEnter`**：这是最容易混淆的地方。`OnEnter` 是"第一次进入"，可能需要初始化所有数据。`OnResume` 是"从中断恢复"，应该利用之前 `OnPause` 中保存的上下文。例如 `PatrolState` 的 `CurrentWaypointIndex` 在 `OnPause` 时不重置，在 `OnResume` 时继续使用。

3. **`PopUntil`** 用于异常情况下的快速回到基线状态。`HealthCritical` 事件中，我们不希望 `Pop` 一层后回到 `Combat`（因为血量不足无法战斗），而是直接清空到 `Patrol` 再切换到 `Retreat`。

4. **事件冒泡**：`SendEvent` 从栈顶向下遍历，第一个消费事件的状态处理它。这提供了类似 HSM 的"向上查找"语义——深层的子行为可以拦截事件，也可以让它冒泡到更底层的父行为。

### 示例 C: HSM in Lua

Lua 的 metatable 机制天然适合实现 HSM——`__index` 元方法恰好实现了"子状态未处理时向上查找父状态"的语义。

```lua
-- ============================================================
-- HSM Framework for Lua
-- 核心: 嵌套 table + __index 继承实现分层状态
-- ============================================================

-- --- 1. HSM 机器 ---
local HSM = {}
HSM.__index = HSM

function HSM.new(rootState)
    local self = setmetatable({}, HSM)
    self.root = rootState
    self.current = nil         -- 当前最深层活动状态
    self.activePath = {}       -- 从 root 到最深子状态的路径表
    self.eventQueue = {}
    return self
end

-- 启动 HSM：激活 root 及其默认子状态链
function HSM:start(context)
    self:activatePath(self.root, nil, context)
end

-- 激活一条状态链（从某个父状态到最深子状态）
function HSM:activatePath(state, parent, context)
    if not state then return end
    state._hsm_parent = parent
    table.insert(self.activePath, state)
    self.current = state

    -- 调用 OnEnter
    if state.OnEnter then state:OnEnter(context) end

    -- 递归激活默认子状态
    local defaultChild = state.DefaultChild
    if type(defaultChild) == "function" then
        defaultChild = defaultChild(state, context)
    end
    if defaultChild then
        self:activatePath(defaultChild, state, context)
    end
end

-- 退出状态链（从最深子状态向上退出到指定祖先）
function HSM:deactivateToAncestor(ancestor, context)
    while #self.activePath > 0 do
        local top = self.activePath[#self.activePath]
        if top == ancestor then
            self.current = top
            return
        end
        if top.OnExit then top:OnExit(context) end
        table.remove(self.activePath)
    end
    self.current = nil
end

-- 每帧更新
function HSM:update(context, dt)
    if not self.current then return end

    -- 1. 查找目标转移（从最深子状态向上）
    local target = self:findTransition(context)

    if target then
        self:changeState(target, context)
    end

    -- 2. 更新最深活动状态
    local deepest = self.activePath[#self.activePath]
    if deepest and deepest.OnUpdate then
        deepest:OnUpdate(context, dt)
    end
end

-- 转移查找：从最深子状态向上遍历
function HSM:findTransition(context)
    for i = #self.activePath, 1, -1 do
        local state = self.activePath[i]
        if state.Transitions then
            for _, trans in ipairs(state.Transitions) do
                if trans.condition(state, context) then
                    return trans.target
                end
            end
        end
    end
    return nil
end

-- 切换状态：找到共同祖先，退出旧路径，进入新路径
function HSM:changeState(target, context)
    -- 检查是否需要切换
    if self.current == target then return end

    -- 找到共同祖先
    local targetPath = self:buildPathToRoot(target)
    local ancestor = self:findCommonAncestor(targetPath)

    -- 退出到共同祖先
    self:deactivateToAncestor(ancestor, context)

    -- 进入目标路径（从共同祖先的下一层开始）
    local startIdx = 1
    if ancestor then
        -- 找到 target 在 ancestor 之后的路径
        for i, state in ipairs(targetPath) do
            if state == ancestor then
                startIdx = i + 1
                break
            end
        end
    end

    for i = startIdx, #targetPath do
        local state = targetPath[i]
        local parent = i > 1 and targetPath[i - 1] or nil
        state._hsm_parent = parent
        table.insert(self.activePath, state)
        self.current = state
        if state.OnEnter then state:OnEnter(context) end
    end

    -- 激活目标状态下的默认子状态链
    local current = self.current
    while current do
        local defaultChild = current.DefaultChild
        if type(defaultChild) == "function" then
            defaultChild = defaultChild(current, context)
        end
        if defaultChild then
            defaultChild._hsm_parent = current
            table.insert(self.activePath, defaultChild)
            self.current = defaultChild
            if defaultChild.OnEnter then defaultChild:OnEnter(context) end
            current = defaultChild
        else
            break
        end
    end
end

-- 构建从状态到 root 的路径
function HSM:buildPathToRoot(state)
    local path = {}
    local current = state
    while current do
        table.insert(path, 1, current)
        current = current._hsm_parent
    end
    return path
end

-- 找到当前 activePath 和目标路径的共同祖先
function HSM:findCommonAncestor(targetPath)
    -- 将当前路径转为 set
    local currentSet = {}
    for _, state in ipairs(self.activePath) do
        currentSet[state] = true
    end

    -- 从目标路径的 root 侧（最深祖先）开始查找
    for i = #targetPath, 1, -1 do
        if currentSet[targetPath[i]] then
            return targetPath[i]
        end
    end
    return nil
end

-- --- 2. 使用 metatable 实现状态继承 ---
-- 子状态的 __index 指向父状态，自动继承未定义的处理函数
local function createChildState(parentState, childDef)
    childDef.__index = childDef -- 自身属性
    local child = setmetatable(childDef, {
        __index = function(t, k)
            -- 先在子状态自身查找
            if childDef[k] ~= nil then return childDef[k] end
            -- 然后在父状态中查找
            if parentState and parentState[k] ~= nil then return parentState[k] end
            -- 最后在父状态的元表链中查找
            if parentState then
                local parentMt = getmetatable(parentState)
                if parentMt and parentMt.__index then
                    local v = parentMt.__index
                    if type(v) == "function" then
                        return v(parentState, k)
                    elseif type(v) == "table" then
                        return v[k]
                    end
                end
            end
            return nil
        end
    })
    return child
end

-- ============================================================
-- 具体 AI 实现
-- ============================================================

-- --- Root 状态 ---
local RootState = {
    Name = "Root",

    OnEnter = function(self, ctx)
        print("[Root] AI initialized")
    end,

    -- 全局转移：死亡 → 任何状态下都触发
    Transitions = {
        {
            condition = function(self, ctx) return ctx.health <= 0 end,
            target = nil  -- 将在下面定义 DeadState 后设置
        }
    },

    DefaultChild = nil  -- 将在下面设置为 IdleParent
}

-- --- Idle 父状态 ---
local IdleParent = {
    Name = "IdleParent",

    OnEnter = function(self, ctx)
        print("[Idle] Entering idle mode")
        ctx:RelaxPosture()
    end,

    OnExit = function(self, ctx)
        print("[Idle] Exiting idle mode")
    end,

    -- Idle 状态下检测到玩家 → Combat
    Transitions = {
        {
            condition = function(self, ctx)
                return ctx:HasDetectedPlayer()
            end,
            target = nil  -- 将在下面设置为 CombatParent
        }
    },

    DefaultChild = nil  -- 将在下面设置为 PatrolState
}

-- --- Idle 子状态: Patrol ---
local PatrolState = createChildState(IdleParent, {
    Name = "Patrol",

    OnEnter = function(self, ctx)
        print("[Patrol] Starting patrol route at waypoint " .. ctx.currentWaypoint)
    end,

    OnUpdate = function(self, ctx, dt)
        -- 沿路径点移动
        local target = ctx.patrolWaypoints[ctx.currentWaypoint]
        ctx:MoveTowards(target)

        if ctx:DistanceTo(target) < 0.5 then
            ctx.currentWaypoint = (ctx.currentWaypoint % #ctx.patrolWaypoints) + 1
        end

        ctx.idleTimer = ctx.idleTimer + dt
    end,

    -- 站太久 → 切换到 Stand
    Transitions = {
        {
            condition = function(self, ctx) return ctx.idleTimer > 10 end,
            target = nil  -- 设置为 StandState
        }
    }
})

-- --- Idle 子状态: Stand ---
local StandState = createChildState(IdleParent, {
    Name = "Stand",

    OnEnter = function(self, ctx)
        print("[Stand] Standing guard")
    end,

    OnUpdate = function(self, ctx, dt)
        -- 原地站立，缓慢环顾
        ctx:LookAround(dt)
    end
})

-- --- Combat 父状态 ---
local CombatParent = {
    Name = "CombatParent",

    OnEnter = function(self, ctx)
        print("[Combat] Engaging target!")
        ctx:PlayAlertSound()
    end,

    -- Combat 下丢失目标太久 → 回到 Idle
    Transitions = {
        {
            condition = function(self, ctx)
                return ctx.timeSinceLastSighting > 5
            end,
            target = nil  -- IdleParent
        }
    },

    -- 根据距离选择默认子状态
    DefaultChild = function(self, ctx)
        if ctx.distanceToTarget < 3 then
            return MeleeState
        else
            return RangedState
        end
    end
}

-- --- Combat 子状态: Melee ---
local MeleeState = createChildState(CombatParent, {
    Name = "Melee",

    OnEnter = function(self, ctx)
        print("[Melee] Closing in for melee!")
    end,

    OnUpdate = function(self, ctx, dt)
        ctx.attackCooldown = ctx.attackCooldown - dt
        if ctx.attackCooldown <= 0 then
            ctx:MeleeAttack()
            ctx.attackCooldown = 1.2
        end
        ctx:FaceTarget()
    end,

    Transitions = {
        {
            condition = function(self, ctx) return ctx.distanceToTarget > 5 end,
            target = nil  -- RangedState
        }
    }
})

-- --- Combat 子状态: Ranged ---
local RangedState = createChildState(CombatParent, {
    Name = "Ranged",

    OnUpdate = function(self, ctx, dt)
        ctx:MaintainDistance()
        ctx:ShootAtTarget()
    end,

    Transitions = {
        {
            condition = function(self, ctx) return ctx.distanceToTarget < 2 end,
            target = nil  -- MeleeState
        }
    }
})

-- --- Dead 状态 ---
local DeadState = {
    Name = "Dead",

    OnEnter = function(self, ctx)
        print("[Dead] Playing death animation")
        ctx:DisableCollision()
    end,

    -- 终态：无转移
    Transitions = {}
}

-- --- 回填循环引用 ---
-- Lua 使用前向声明，需要在所有状态定义后回填 target 引用
RootState.Transitions[1].target = DeadState
RootState.DefaultChild = IdleParent

IdleParent.Transitions[1].target = CombatParent
IdleParent.DefaultChild = PatrolState

PatrolState.Transitions[1].target = StandState
StandState.Transitions = {}  -- Stand 没有额外转移，继承 IdleParent 的转移

CombatParent.Transitions[1].target = IdleParent
MeleeState.Transitions[1].target = RangedState
RangedState.Transitions[1].target = MeleeState

-- --- 使用示例 ---
-- local context = {
--     health = 100,
--     currentWaypoint = 1,
--     patrolWaypoints = { ... },
--     idleTimer = 0,
--     -- ... 其他字段和方法
-- }
-- local hsm = HSM.new(RootState)
-- hsm:start(context)
--
-- function love.update(dt)
--     hsm:update(context, dt)
-- end
```

**代码要点解析**：

1. **`createChildState` + metatable**：这是 Lua 实现 HSM 最优雅的地方。`MeleeState` 的 `Transitions` 是合并了自身的 `{距离>5→Ranged}` 和继承自 `CombatParent` 的 `{丢失目标5秒→IdleParent}`。如果 `MeleeState` 没有定义 `OnExit`，则自动使用 `CombatParent` 的 `OnExit`。

2. **前向声明 + 回填引用**：Lua 没有 C++/C# 的前向声明机制。所有状态之间的 target 引用需要在定义完成后回填。对于大型 HSM，可以考虑使用字符串名称 + 注册表来延迟解析。

3. **`activePath` 表**：HSM 维护从 root 到当前最深活动状态的完整路径，使得 `findTransition`（向上查找）和 `deactivateToAncestor`（向上退出）能够在 O(depth) 时间内完成。

4. **`DefaultChild` 作为函数**：`CombatParent` 的 `DefaultChild` 是一个函数，根据上下文动态选择默认子状态。这比静态指定更灵活——战斗距离远就默认远程，距离近就默认近战。

---

## 3. 练习

### 练习 1: 设计一个 Boss 三阶段 HSM

**目标**：为一个 Boss 战设计完整的 HSM 层次结构。

**场景**：Boss 有三个阶段，血量阈值分别为 100%-66%（Phase1）、66%-33%（Phase2）、33%-0%（Phase3）。每个阶段有相似的子行为（Idle、Melee、Ranged、SpecialSkill、Stunned），但行为和数值随阶段变化。

**要求**：

1. 画出 HSM 的层次结构图（嵌套框形式），标明每个父状态包含的子状态。
2. 为每一层（Root、Phase1/2/3、各子状态）列出以下内容：
   - 该层定义的**转移规则**（从什么条件到哪个目标状态）。
   - 该层**不定义**但**继承自父层**的转移规则。
3. 给出 Phase1 → Phase2、Phase2 → Phase3 的转移条件及实现位置。解释为什么这些转移不应放在子状态中。
4. 设计 Phase3 独有的 `DesperationSkill` 状态。它与 Phase2 的 `SpecialSkill` 有何不同？是否需要在子状态 `DesperationSkill` 中重新定义"血量归零 → Dead"的转移？

**思考要点**：

- 转移规则应定义在"能覆盖最多子状态的最高层级"。
- 子状态只需要定义"与父状态/兄弟状态不同的转移"。不必要的重复定义是设计缺陷。
- 数据驱动设计：阶段的数值差异（伤害倍率、冷却时间）应放在数据容器中，而非硬编码在状态里。

### 练习 2: 实现 Pushdown Automata 的中断-恢复

**目标**：在你选定的引擎中实现一个支持中断-恢复的 Pushdown Automata。

**场景**：一个 NPC 有三种基线行为：`Idle`（闲逛）、`Work`（工作）、`Socialize`（社交）。NPC 可以被以下事件中断：

- `InvestigateSound`：听到异常声音 → 调查 → 回到基线行为。
- `Combat`：检测到敌人 → 战斗 → 敌人死亡 → 回到基线行为。
- `Flee`：血量过低 → 逃跑 → 安全后 → 回到基线行为（注意：从 `Flee` Pop 后不应该回到 `Combat`）。

**要求**：

1. 实现状态栈，支持 `Push`、`Pop`、`Switch` 三种操作。
2. 实现每个状态的 `OnEnter`、`OnExit`、`OnPause`、`OnResume` 回调。确保 `OnResume` 和 `OnEnter` 的行为有区别（提示：`Idle` 的 `OnEnter` 选择一个随机闲逛目标，但 `OnResume` 应该继续之前的闲逛目标）。
3. 实现事件分发系统。事件从栈顶向栈底传播，第一个消费事件的状态处理它。
4. 处理"组合中断"场景：NPC 在 `Idle` → `InvestigateSound` → `Combat` → `Flee` 的栈深度为 4 的情况下，依次 `Pop`，验证每一步恢复的行为是否正确。
5. （可选）实现 `PopUntil(TargetState)` 操作：对于血量过低导致的逃跑，直接从栈中剥离所有中断层，回到基线行为后切换到撤退。

**验证方式**：编写一个简单的测试脚本，使用日志打印每一步的状态栈快照。验证栈的 Push/Pop 序列符合预期。

### 练习 3（选做）: 用你偏好的引擎实现完整 Boss 战 HSM

**目标**：将练习 1 的设计转化为可运行的代码。

**要求**：

1. 使用本节中示例 A（C# Unity）、示例 B（C++ Unreal）或示例 C（Lua）的框架作为基础。
2. 实现完整的 Enter/Exit/Update 生命周期。
3. 实现至少以下转移：
   - Phase1 → Phase2（血量 < 66%）
   - Phase2 → Phase3（血量 < 33%）
   - 任意 Phase → Dead（血量 <= 0）
   - Idle → MeleeAttack（目标靠近）
   - Idle → RangedAttack（目标远离但可见）
   - MeleeAttack ↔ RangedAttack（基于距离切换）
   - 任意子状态 → Stunned（受到重击，有冷却时间）
4. 实现 `OnEnter` 的合理行为（Phase2 进入时播放阶段转换动画和台词，Phase3 进入时改变场景光照等）。
5. 添加调试功能：在控制台打印当前活动状态路径（如 `Root → Phase2 → MeleeAttack`）。

**验收标准**：

- Boss 在不同阶段切换时，子状态正确退出和重新进入。
- 阶段切换动画播放期间，Boss 不应执行任何子状态逻辑。
- 所有状态转移都可以通过修改模拟数据（血量、距离等）来触发和验证。
- 无状态泄露（每个 Enter 对应恰好一次 Exit）。

---

## 4. 扩展阅读

### 必读

| 资源 | 说明 |
|------|------|
| **Game Programming Patterns — State** (Robert Nystrom) | 免费在线阅读。深入讲解 FSM → 并发状态机 → HSM → Pushdown Automata 的整套演化路径。本章大量核心概念来源于此。必读。 |
| **GDC 2005: Managing Complexity in the Halo 2 AI** (Damian Isla) | 讲解 Halo 2 如何从 Halo 1 的平铺 FSM 演化到优先级行为树。包含行为栈、impulse 机制、以及层级化行为组织的设计哲学。可在 GDC Vault 找到演讲视频。 |
| **UE5 StateTree 官方文档** | Epic Games 对 StateTree 的全面介绍——这是 HSM 理念在现代商业引擎中的最新实现形态。理解 StateTree 的层次状态、Evaluator、Task 如何将 HSM 和 BT 融合。 |

### 推荐阅读

| 资源 | 说明 |
|------|------|
| *Programming Game AI by Example* (Mat Buckland), Chapter 2 | 虽然主要覆盖 FSM，但末尾讨论了层次化状态的实现思路。如果你在阅读本教程前已经完成 Tutorial 01-04，这本书的 FSM 章节应该已经读过了。 |
| *Artificial Intelligence for Games* (Ian Millington, 2nd ed.), Chapter 5.3 | 包含 HFSM 的形式化定义和分析。偏理论，适合深入理解层次化转移的数学基础。 |
| *Game AI Pro 1*, Chapter 12: *A Reusable, Light-Weight Finite State Machine* (David "Rez" Graham) | 讨论了如何设计可复用的状态机框架，包含层次化扩展的思路。 |
| **Building a Better Battle: HALO 3 AI Objectives** (Damian Isla, GDC 2008) | Halo 3 在 Halo 2 的行为树基础上引入了"目标系统"（Objective System），进一步提升了 AI 行为的层次化和动态性。是 HSM 理念在 AAA 项目中演进的典型案例。 |

### 在线资源

- [Game Programming Patterns — State](https://gameprogrammingpatterns.com/state.html) — 本章的核心参考。免费在线阅读。
- [GDC Vault — Damian Isla 演讲](https://www.gdcvault.com/) — 搜索 "Managing Complexity in the Halo 2 AI" 和 "Building a Better Battle"。
- [UE5 StateTree Overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/overview-of-state-tree-in-unreal-engine) — StateTree 的官方文档。
- [Halo 2 AI Behavior List (Microsoft Learn)](https://learn.microsoft.com/en-us/halo-master-chief-collection/h2/ai/aibehaviorlist) — Halo 2 完整的行为列表，展示了层次化行为树的工业实现。
- [Halo 2 AI Engineering Outline](https://learn.microsoft.com/en-us/halo-master-chief-collection/h2/ai/aiengineeringoutline) — Halo 2 AI 系统的工程架构概览。

---

## 常见陷阱

### 1. 父状态转移遮蔽 (Parent Transition Shadowing)

**症状**：你在 `CombatParent` 中定义了"血量归零 → Dead"的转移。但在 `MeleeState` 中，血量归零时没有任何反应——敌人继续攻击。

**根因**：`MeleeState` 也定义了"血量归零"的转移处理，但你写的是一个**空处理**（没有切换到 Dead，而是 `return` 了）。因为子状态的转移查找优先级高于父状态，子状态"拦截"了事件，阻止了父状态的处理。

```csharp
// ❌ 错误：子状态拦截了事件但不处理，导致父状态的转移被遮蔽
public class MeleeState : HierarchicalState
{
    public MeleeState()
    {
        // 错误地添加了一个条件为 true 的自转移，遮蔽了父状态
        AddTransition<MeleeState>(() => health > 0);  // 始终匹配！
    }
}
```

**解法**：

1. **子状态只定义自己特有的转移**。不要重复定义父状态已经处理的转移。
2. 如果确实需要子状态拦截某个事件（例如 Phase3 的 `DesperationSkill` 中血量归零时先播放特殊动画再死亡），确保子状态的处理最终会触发正确的转移。
3. **一致性检查**：在 HSM 初始化时验证每个子状态的转移不会无意中遮蔽父状态的关键转移。

### 2. 状态历史未正确保存/恢复

**症状**：NPC 被中断（Push Combat），战斗结束后 Pop 回 Patrol，但 NPC 从路径点 0 开始巡逻，而不是之前的路径点 5。

**根因**：`Pop` 触发的是 `OnEnter` 而不是 `OnResume`，重置了巡逻状态的内部数据。或者 `OnPause` 没有正确保存上下文。

**解法**：

1. **严格区分 OnEnter 和 OnResume**。OnEnter 初始化数据，OnResume 恢复数据。如果你在 OnEnter 中设置 `currentWaypoint = 0`，确保 OnResume 不会调用 OnEnter。
2. 在 Pushdown Automata 中，将需要保存的上下文数据（如当前路径点索引、计时器状态）作为状态的成员变量。`OnPause` 不需要做任何事——数据自然被保留（因为状态对象仍然存在，只是被压在栈下面）。
3. 如果你使用的是享元模式（单例状态对象），状态内部不应该存储任何实体特定数据——将数据放在上下文对象中，通过 `OnPause`/`OnResume` 参数传递。

### 3. Push/Pop 不匹配（栈泄露）

**症状**：运行一段时间后，状态栈深度持续增长（10, 15, 20...），NPC 行为越来越奇怪，最终栈溢出。

**根因**：有 Push 没有对应的 Pop。常见原因：

- 某个中断状态的退出条件永远不满足（例如 `SelfPreservation` 等待护盾恢复，但 NPC 没有护盾）。
- 某个 Push 后的代码路径抛出了异常，跳过了 Pop。
- `PopUntil` 的目标状态不在栈中，导致无限 Pop（如果实现不当）。

**解法**：

1. **每个 Push 必须有一个明确的 Pop 条件**。在 Push 的调用点，确保你知道什么事件会触发对应的 Pop。
2. **添加栈深度断言**：在调试模式下，如果栈深度超过合理值（如 8），打印警告并截断。
3. **超时保护**：每个被 Push 的状态可以有一个 `MaxDuration`。如果持续时间超过上限，强制 Pop 并记录日志。
4. **防御性编程**：在 `PopState` 中检查栈是否为空。在 `PopUntil` 中，如果找不到目标状态，弹到栈底后停止。

### 4. 深层层次的调试困难

**症状**：当 HSM 的层次深度超过 4-5 层时，你无法快速搞清楚"当前到底在哪个状态"。一个 `OnUpdate` 没有执行，你需要追踪 5 层转移查找才能确定是哪个父状态的转移条件触发了提前切换。

**根因**：HSM 将复杂度从"状态数量"转移到了"层次深度"。当层次过深时，转移的查找路径变得不透明。

**解法**：

1. **日志工具**：在每个状态的 `OnEnter` 和 `OnExit` 中打印带缩进的状态名称。使用当前层次深度作为缩进级别。

   ```
   [HSM] → Root
   [HSM]   → CombatParent
   [HSM]     → MeleeState
   [HSM]     ← MeleeState  (transition to RangedState)
   [HSM]     → RangedState
   ```

2. **可视化工具**：在 Editor 模式下，绘制当前活动状态路径的可视化树。Unreal 的 Gameplay Debugger 和 Unity 的 Gizmos 都可以做到。
3. **限制层次深度**：作为经验法则，HSM 的层次深度不应超过 4 层（Root → Phase → Behavior → SubBehavior）。如果超过，考虑是否可以将某些层次合并，或拆分为多个独立的 HSM。
4. **转移跟踪**：在调试模式下记录每次转移的完整路径——哪个状态发起了查找、在哪个层级找到了匹配、目标状态路径是什么。

### 5. 将 HSM 当作万能钥匙

**症状**：你用 HSM 实现了一个完整的 RPG 角色 AI，结果层次越来越深，转移规则互相纠缠，调试一次转移需要理解 6 个层级的状态交互。

**根因**：HSM 擅长"状态之间存在明确的层次和继承关系"的场景。但不是所有问题都适合 HSM。以下信号表明你可能需要切换到其他范式：

- 你的子状态经常需要"绕过父状态"直接与其他子状态通信。
- 你发现自己在父状态中写了大量 `if` 来区分不同子状态的差异化行为。
- 状态的组合关系远比继承关系重要（例如"攻击 + 移动 + 防御"的组合，而不是"近战攻击 继承自 战斗 继承自 活动"）。

**替代方案**：

- **行为树**：当行为之间是"优先级选择"关系而非"层次继承"关系时。Tutorial 06-13 会深入讲解。
- **效用 AI**：当行为选择需要同时评估多个加权因素时。
- **组合优于继承**：使用组件模式（如 Unity 的 ECS 或 Unreal 的 Actor Component），将独立关注点的行为实现为独立的组件，而不是硬塞进一个 HSM 层次中。

---

> **下一步**: 完成本教程后，进入 Tutorial 06 [行为树基础理论](06-bt-fundamentals.md)，了解如何将状态的"层次继承"思维转化为行为的"优先级组合"思维。你将看到 Halo 2 的行为树如何从 HSM 的概念中自然演化而来。
