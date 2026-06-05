---
title: "综合项目: 完整游戏 AI 系统"
updated: 2026-06-05
---

# 综合项目: 完整游戏 AI 系统

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 180min
> 前置知识: 全部先前教程 (01-19)

---

## 1. 概念讲解

### 项目愿景

这是整个学习计划的终点——也是你面试时展示的作品。你要构建一个完整的小型竞技场战斗游戏 AI 系统。玩家进入竞技场，面对一波又一波的敌人。每个敌人都不是简单的"看到玩家→冲过去→攻击"——它们巡逻、感知（视觉+听觉）、追击、近战/远程攻击、寻找掩体、低血量撤退、呼叫队友支援。更重要的是，不同原型（兵种）的行为截然不同：小兵疯狂冲锋，狙击手远程压制并不断换位，重装兵缓慢推进但攻击力强悍，Boss 有多阶段的 HSM 行为。

这不是一个玩具项目。这是一个**可展示的系统设计能力证明**——它涉及行为树、黑板、感知系统、导航、战斗、动画集成、多智能体协调、性能优化。每一个模块都是游戏 AI 岗位面试中的高频话题。

**为什么这很重要**：面试官问"你做过什么游戏 AI 项目"时，你不需要说"我在课程作业里实现过一个简单的 FSM"。你可以打开这个项目，展示架构图，解释每个设计决策，讨论你遇到的性能瓶颈和如何解决的。这比任何理论回答都有说服力。

### 项目范围

| 系统 | 包含内容 |
|:-----|:---------|
| **感知系统** | 视觉锥 (sight cone) + 听觉半径 (hearing radius)。支持玩家脚步声、枪声、队友呼救信号的检测 |
| **行为决策** | 基于行为树 (BT)，每个 agent 一棵独立树实例。复合节点 (Selector/Sequence/Parallel)、装饰节点 (Inverter/Cooldown/Repeat)、条件节点、动作节点 |
| **黑板系统** | per-agent Blackboard (私有) + Squad Blackboard (小队共享)。字典存储 + 类型化读写 |
| **导航** | Unity NavMeshAgent 驱动。巡逻路径点循环、追击路径动态更新、寻找掩体位置查询 |
| **战斗** | 近战 (range + damage + cooldown)、远程 (projectile spawn + line-of-sight check + cooldown)、AoE (range + damage falloff)、伤害计算、死亡处理 |
| **小队协调** | 共享 Blackboard 传播"发现敌人"事件。低血量敌人向同小队成员发出 help 信号，收到信号的成员评估是否支援 |
| **动画集成** | 动画 FSM 与 AI 行为树分离。BT 通过黑板写入动画参数 (Speed, IsAttacking, AttackType)，Animator 读取 |
| **原型系统** | 4 种兵种：Grunt (近战冲锋)、Sniper (远程+换位)、Heavy (缓慢+高血量+AoE)、Boss (多阶段 HSM + 行为树混合) |
| **游戏循环** | 波次生成系统、玩家胜利/失败条件、AI LOD (距离分级 tick 频率) |
| **调试可视化** | Gizmos 绘制视觉锥、听觉半径、巡逻路径、当前 BT 活跃节点路径 |

### 架构总览

```
┌─────────────────────────────────────────────────┐
│                  AIController                     │
│  (MonoBehaviour — one per agent)                  │
│                                                   │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Blackboard│  │  BT Engine   │  │ Perception │ │
│  │ (dict)   │  │  (root node) │  │ (sight/    │ │
│  │          │  │              │  │  hearing)  │ │
│  └────┬─────┘  └──────┬───────┘  └──────┬─────┘ │
│       │               │                  │       │
│  ┌────┴───────────────┴──────────────────┴─────┐ │
│  │              Shared Squad Data               │ │
│  │  (static SquadBlackboard + event bus)        │ │
│  └──────────────────────────────────────────────┘ │
└───────────────────────┬─────────────────────────┘
                        │ drives
                        ▼
┌─────────────────────────────────────────────────┐
│                 Agent Body (GameObject)           │
│  NavMeshAgent  │  Animator  │  Health/Damage     │
│  (pathfinding) │  (visual)  │  (combat)          │
└─────────────────────────────────────────────────┘
```

**分层设计**：
- **决策层 (Think)**：行为树每帧从根节点开始深度优先遍历。从"是否战斗"到"攻击还是撤退"到"移动到哪个点"，决策全部在 BT 中完成。
- **执行层 (Act)**：BT 的动作节点不直接操作 Transform——它们写黑板 (`MoveTarget`, `AttackTarget`)，由 AIController 的 Agent 驱动组件执行。NavMeshAgent 从黑板读 `MoveTarget`，Animator 从黑板读 `Speed` / `IsAttacking`。
- **感知层 (Sense)**：每 N 帧运行一次（默认每 3 帧），执行视线射线检测和听觉范围检测，结果写入黑板。

### 实现计划

#### 阶段 1: 核心框架 (2h)

**目标**：框架代码编译通过，巡逻 + 追击可用。

1. **BTNode 基类**：`BTNodeState` 枚举 (Success/Failure/Running)，`BTNode` 抽象基类 (`Tick()` 纯虚方法)
2. **复合节点**：`Selector` (优先级选择，任一子节点 Running/Success 即返回，全 Failure 才 Failure)，`Sequence` (顺序执行，任一子节点 Failure 即返回，全 Success 才 Success)
3. **装饰节点**：`Inverter` (反转子节点结果)，`Repeater` (重复执行 N 次)，`Cooldown` (冷却时间内跳过子节点并返回 Failure)，`Succeeder` (将子节点 Failure 转为 Success——用于可选行为)
4. **叶子节点**：`ActionNode` (接收 `Func<BTNodeState>` 委托)，`ConditionNode` (接收 `Func<bool>` 委托，true→Success, false→Failure)。**注意：委托不是 lambda 捕获游戏对象——所有需要的上下文通过 `Blackboard` 传入。**
5. **Blackboard**：`Dictionary<string, object>` 内部存储。`T Get<T>(string key)`, `void Set<T>(string key, T value)`, `bool HasKey(string key)`, `bool TryGet<T>(string key, out T value)`。`T` 约束为值类型和 UnityEngine.Object 引用。
6. **PerceptionComponent**：管理视觉锥 (角度 + 距离 + LayerMask) 和听觉半径。提供 `bool CanSeeTarget(Transform target)`, `bool CanHearTarget(Vector3 position, float volume)`, `List<Transform> perceivedThreats`。
7. **AIController**：持有 Blackboard + BT root + PerceptionComponent + NavMeshAgent 引用。`Update()` 中调用 Perceive → Tick BT → ApplyMovement。

#### 阶段 2: 基础行为 (2h)

**目标**：敌人能巡逻、检测玩家后追击、靠近后近战攻击、丢失目标后返回巡逻。

1. **巡逻**：`ActionNode` — 沿 waypoint 列表循环移动。移动到当前 waypoint 的 1m 范围内时切换到下一个。黑板 key: `"patrol_index"`, `"move_target"`。
2. **追击**：`ActionNode` — 持续更新 `move_target` 为 `target.transform.position`。黑板 key: `"target"`, `"move_target"`。
3. **近战攻击**：`ActionNode` — 检查与 target 距离 < attackRange，启动攻击 cooldown，触发伤害。黑板 key: `"target"`, `"attack_cooldown_timer"`, `"attack_range"`。
4. **目标丢失**：Condition "HasTarget" 返回 false（目标跑出视野且超过记忆时间），树回退到 Patrol。

此时各兵种共享这些基础行为节点，通过黑板中的参数（`movement_speed`, `attack_range`, `attack_damage`, `attack_cooldown`, `sight_range`, `sight_angle`）区分。

#### 阶段 3: 高级行为 (2h)

**目标**：远程攻击 + 掩体寻路、低血量撤退、小队呼救。

1. **远程攻击**：`ActionNode` — 在 line-of-sight (射线检测) 通过时才开火。黑板 key: `"has_los"` (由 Service 节点每帧更新)。
2. **寻找掩体**：`ActionNode` — 从玩家位置反向寻找最近的 NavMesh 位置 + 障碍物后面的掩体点。移动到掩体后短暂停留。黑板 key: `"cover_position"`, `"is_in_cover"`。
3. **撤退**：Condition `"health_percent < retreat_threshold"` → 从玩家位置反方向跑 + 寻找掩体。
4. **小队呼救**：Action `"CallForHelp"` — 写入 Squad Blackboard: `"help_requested" = true`, `"help_position" = transform.position`。其他 squad 成员的 Service 节点定期检查 Squad Blackboard，当 `help_requested == true` 时评估是否支援（距离 + 自身状态）。

#### 阶段 4: 原型系统 (2h)

**目标**：4 种兵种各有不同的行为树配置。

| 原型 | 速度 | 血量 | 攻击 | 行为特点 |
|:-----|:-----|:-----|:-----|:---------|
| **Grunt** | 中 (5m/s) | 低 (100) | 近战 (15dmg, 1s CD) | 激进。看到玩家直接冲锋。撤退阈值 20% |
| **Sniper** | 低 (3m/s) | 极低 (60) | 远程 (40dmg, 3s CD) | 远距离压制。每次射击后换掩体。撤退阈值 50% |
| **Heavy** | 极低 (2m/s) | 高 (300) | AoE 近战 (30dmg, 2.5s CD, 4m 范围) | 缓慢推进。不会撤退。攻击前摇长但范围大 |
| **Boss** | 阶段1: 3m/s, 阶段2: 6m/s | 高 (1000) | 阶段1 远程投射 + 召唤小兵, 阶段2 近战狂暴 | 使用 HSM 管理阶段转移 (Phase1 → Phase2 at 50% HP) |

Boss 的 HSM 设计：
```
Phase1 (ranged + summons):
  States: Idle → SpawnMinions → RangedAttack → Evade → Idle
  Transitions: HP < 50% → Phase2

Phase2 (melee berserk):
  States: Roar → Charge → MeleeCombo → LeapSmash → Charge
  Death at HP = 0
```

Boss 的 BT 根节点是一个 Selector，第一个子节点检查 `hp_percent < 0` → 执行 Death 序列，第二个子节点检查 `phase == Phase2` → 运行 Phase2 子树，否则运行 Phase1 子树。

#### 阶段 5: 润色 (可选, 2h)

**目标**：AI LOD、调试可视化、波次系统、胜负条件。

1. **AI LOD**：距离玩家 > 50m 的敌人每 5 帧 tick 一次 BT，> 100m 每 10 帧。视觉锥和听觉检测也降频。
2. **调试可视化**：`OnDrawGizmos` 绘制视觉锥 (半透明扇形)、听觉半径 (线框球体)、当前 BT 活跃路径 (文本标签)、巡逻路径点连线、掩体位置标记。
3. **波次系统**：`WaveManager` MonoBehaviour，配置波次数据 (每波敌人类型+数量+间隔)。波间有倒计时和 UI 提示。
4. **胜负条件**：玩家死亡 → 失败。所有波次清完 → 胜利。UI 显示剩余敌人数量。

---

## 2. 代码示例

以下提供完整的核心框架代码。这是你的起点——复制到 Unity 项目中，在阶段 1 让巡逻和追击跑起来。

### 架构决策

在开始写代码之前，先理解四个关键设计决策，它们影响整个框架的结构：

**决策 1：每个 agent 持有独立的 BT 节点实例，而非共享一棵树。**

原因：行为树节点在 Tick 过程中可能处于 `Running` 状态（例如 `MoveTo` 节点需要多帧才能到达目标）。如果多个 agent 共享同一个节点对象，agent A 的 `_startedMoving` 标记会覆盖 agent B 的状态。解决方式：每个 AIController 持有自己的一套 BT 节点，在 `Awake()` 中通过 `BuildTree()` 工厂方法创建。

**决策 2：Tick 是深度优先、左到右的递归遍历。**

这是标准 BT 语义。Selector 从左到右找第一个不返回 Failure 的子节点；Sequence 从左到右找第一个不返回 Success 的子节点。节点状态用 per-instance 字段存储（不是全局状态），所以递归调用不用传任何上下文参数——每个节点实例知道自己"上次运行到哪一步"。

**决策 3：Blackboard 是 `Dictionary<string, object>`，配合泛型访问器。**

这提供了最大的灵活性——新行为节点可以动态添加新 key，不需要修改类定义。`object` 的装箱开销在每帧几十个 key 的读写量下可以忽略（现代 C# 的泛型 value type 装箱已经优化），但如果你需要极致性能，可以改为 `Dictionary<string, (Type, byte[])>` 的无装箱方案。**本项目保持简单方案，因为 AI 决策本身不是性能瓶颈——NavMesh 寻路和物理检测才是。**

**决策 4：BT 节点不持有 GameObject / MonoBehaviour 引用，通过 Blackboard 间接访问。**

`ActionNode` 的委托不应捕获 `this.transform` 或 `GetComponent<NavMeshAgent>()`。所有需要的外部对象引用都存储在 Blackboard 中（`"agent_transform"`, `"nav_agent"`, `"animator"` 等），节点通过 `blackboard.Get<T>(key)` 获取。这样节点可以脱离 Unity 对象生命周期进行单元测试。

### BTNode.cs — 节点基类与枚举

```csharp
// BTNodeState.cs
namespace ArenaAI
{
    public enum BTNodeState
    {
        Success,
        Failure,
        Running
    }
}
```

```csharp
// BTNode.cs
namespace ArenaAI
{
    /// <summary>
    /// Abstract base for all behavior tree nodes.
    /// Each AIController owns its own instance set — nodes are never shared across agents.
    /// </summary>
    public abstract class BTNode
    {
        /// <summary>
        /// Execute one tick of this node. Called every frame the node is active.
        /// Returns Running if the action is still in progress.
        /// Subclasses that need per-instance state should store it in fields on this instance.
        /// </summary>
        public abstract BTNodeState Tick(Blackboard blackboard, float deltaTime);

        /// <summary>
        /// Called when this node becomes active for the first time in a tick sequence.
        /// Override to reset internal state (e.g., clear a "started" flag).
        /// Default implementation is a no-op.
        /// </summary>
        public virtual void OnEnter(Blackboard blackboard) { }

        /// <summary>
        /// Called when this node transitions out of Running (to Success or Failure),
        /// or when its parent aborts it. Override to clean up side effects.
        /// </summary>
        public virtual void OnExit(Blackboard blackboard) { }

        /// <summary>
        /// Optional name for debugging. Set by the tree builder.
        /// </summary>
        public string NodeName { get; set; } = "Unnamed";
    }
}
```

### Composites.cs — Selector, Sequence, Parallel

```csharp
// Selector.cs
using System.Collections.Generic;
using UnityEngine;

namespace ArenaAI
{
    /// <summary>
    /// Priority selector: ticks children left-to-right.
    /// Returns on first child that does NOT return Failure.
    /// Returns Failure only if all children return Failure.
    /// </summary>
    public class Selector : BTNode
    {
        private readonly List<BTNode> _children;
        private int _currentChildIndex = 0;

        public Selector(List<BTNode> children, string name = "Selector")
        {
            _children = children;
            NodeName = name;
        }

        public override void OnEnter(Blackboard blackboard)
        {
            _currentChildIndex = 0;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            while (_currentChildIndex < _children.Count)
            {
                BTNode child = _children[_currentChildIndex];
                BTNodeState state = child.Tick(blackboard, deltaTime);

                switch (state)
                {
                    case BTNodeState.Running:
                        return BTNodeState.Running;
                    case BTNodeState.Success:
                        return BTNodeState.Success;
                    case BTNodeState.Failure:
                        _currentChildIndex++;
                        continue;
                }
            }
            return BTNodeState.Failure;
        }
    }
}
```

```csharp
// Sequence.cs
using System.Collections.Generic;

namespace ArenaAI
{
    /// <summary>
    /// Sequence: ticks children left-to-right.
    /// Returns on first child that does NOT return Success.
    /// Returns Success only if all children return Success.
    /// </summary>
    public class Sequence : BTNode
    {
        private readonly List<BTNode> _children;
        private int _currentChildIndex = 0;

        public Sequence(List<BTNode> children, string name = "Sequence")
        {
            _children = children;
            NodeName = name;
        }

        public override void OnEnter(Blackboard blackboard)
        {
            _currentChildIndex = 0;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            while (_currentChildIndex < _children.Count)
            {
                BTNode child = _children[_currentChildIndex];
                BTNodeState state = child.Tick(blackboard, deltaTime);

                switch (state)
                {
                    case BTNodeState.Running:
                        return BTNodeState.Running;
                    case BTNodeState.Failure:
                        return BTNodeState.Failure;
                    case BTNodeState.Success:
                        _currentChildIndex++;
                        continue;
                }
            }
            return BTNodeState.Success;
        }
    }
}
```

```csharp
// Parallel.cs
using System.Collections.Generic;

namespace ArenaAI
{
    /// <summary>
    /// Parallel composite: ticks all children every frame.
    /// Configurable policy for how many children must succeed/fail before the parallel returns.
    /// </summary>
    public class Parallel : BTNode
    {
        private readonly List<BTNode> _children;
        private readonly int _requiredSuccesses;
        private readonly int _requiredFailures;

        /// <param name="requiredSuccesses">Number of children that must return Success.
        /// Use children.Count for "all must succeed".</param>
        /// <param name="requiredFailures">Number of children that must return Failure.
        /// Use 1 for "fail on any child failure".</param>
        public Parallel(List<BTNode> children, int requiredSuccesses, int requiredFailures,
            string name = "Parallel")
        {
            _children = children;
            _requiredSuccesses = requiredSuccesses;
            _requiredFailures = requiredFailures;
            NodeName = name;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            int successes = 0;
            int failures = 0;

            foreach (BTNode child in _children)
            {
                BTNodeState state = child.Tick(blackboard, deltaTime);
                if (state == BTNodeState.Success) successes++;
                if (state == BTNodeState.Failure) failures++;
            }

            if (successes >= _requiredSuccesses)
                return BTNodeState.Success;
            if (failures >= _requiredFailures)
                return BTNodeState.Failure;
            return BTNodeState.Running;
        }
    }
}
```

### Decorators.cs — Inverter, Repeater, Cooldown, Succeeder

```csharp
// Inverter.cs
namespace ArenaAI
{
    /// <summary>
    /// Inverts the result of its child: Success → Failure, Failure → Success.
    /// Running passes through unchanged.
    /// </summary>
    public class Inverter : BTNode
    {
        private readonly BTNode _child;

        public Inverter(BTNode child, string name = "Inverter")
        {
            _child = child;
            NodeName = name;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            BTNodeState state = _child.Tick(blackboard, deltaTime);
            return state switch
            {
                BTNodeState.Success => BTNodeState.Failure,
                BTNodeState.Failure => BTNodeState.Success,
                _ => BTNodeState.Running
            };
        }
    }
}
```

```csharp
// Repeater.cs
namespace ArenaAI
{
    /// <summary>
    /// Repeats its child N times (-1 = infinite).
    /// Each time the child returns Success or Failure, the counter increments
    /// and the child is re-entered. Repeater itself only returns Success or
    /// Failure when the repeat count is exhausted.
    /// </summary>
    public class Repeater : BTNode
    {
        private readonly BTNode _child;
        private readonly int _maxRepeats;
        private int _repeatCount;

        /// <param name="maxRepeats">-1 for infinite repeat</param>
        public Repeater(BTNode child, int maxRepeats = -1, string name = "Repeater")
        {
            _child = child;
            _maxRepeats = maxRepeats;
            NodeName = name;
        }

        public override void OnEnter(Blackboard blackboard)
        {
            _repeatCount = 0;
            _child.OnEnter(blackboard);
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            if (_maxRepeats > 0 && _repeatCount >= _maxRepeats)
                return BTNodeState.Success;

            BTNodeState state = _child.Tick(blackboard, deltaTime);

            if (state != BTNodeState.Running)
            {
                _repeatCount++;
                _child.OnEnter(blackboard);

                if (_maxRepeats > 0 && _repeatCount >= _maxRepeats)
                    return BTNodeState.Success;
                // For infinite repeater, we never return Success — just keep running
                return _maxRepeats < 0 ? BTNodeState.Running : BTNodeState.Running;
            }
            return BTNodeState.Running;
        }
    }
}
```

```csharp
// Cooldown.cs
using UnityEngine;

namespace ArenaAI
{
    /// <summary>
    /// Decorator that enforces a cooldown between executions of its child.
    /// Returns Failure while the cooldown timer is active.
    /// When the cooldown elapses, ticks the child normally.
    /// </summary>
    public class Cooldown : BTNode
    {
        private readonly BTNode _child;
        private readonly float _cooldownSeconds;
        private float _timer;

        public Cooldown(BTNode child, float cooldownSeconds, string name = "Cooldown")
        {
            _child = child;
            _cooldownSeconds = cooldownSeconds;
            NodeName = name;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            if (_timer > 0f)
            {
                _timer -= deltaTime;
                return BTNodeState.Failure;
            }

            BTNodeState state = _child.Tick(blackboard, deltaTime);
            if (state != BTNodeState.Running)
            {
                _timer = _cooldownSeconds;
            }
            return state;
        }
    }
}
```

```csharp
// Succeeder.cs
namespace ArenaAI
{
    /// <summary>
    /// Always returns Success, regardless of child's result.
    /// Used for optional behaviors that should not cause a parent Sequence to fail.
    /// </summary>
    public class Succeeder : BTNode
    {
        private readonly BTNode _child;

        public Succeeder(BTNode child, string name = "Succeeder")
        {
            _child = child;
            NodeName = name;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            BTNodeState state = _child.Tick(blackboard, deltaTime);
            return state == BTNodeState.Running ? BTNodeState.Running : BTNodeState.Success;
        }
    }
}
```

### LeafNodes.cs — Action 与 Condition

```csharp
// ConditionNode.cs
using System;

namespace ArenaAI
{
    /// <summary>
    /// Leaf node that evaluates a condition function.
    /// Returns Success if the condition is true, Failure otherwise.
    /// Condition functions MUST NOT mutate Blackboard state — they are pure queries.
    /// </summary>
    public class ConditionNode : BTNode
    {
        private readonly Func<Blackboard, bool> _condition;

        public ConditionNode(Func<Blackboard, bool> condition, string name = "Condition")
        {
            _condition = condition;
            NodeName = name;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            return _condition(blackboard) ? BTNodeState.Success : BTNodeState.Failure;
        }
    }
}
```

```csharp
// ActionNode.cs
using System;

namespace ArenaAI
{
    /// <summary>
    /// Leaf node that executes an action function each tick.
    /// The action returns BTNodeState: Running while in progress, Success/Failure when done.
    /// The action function receives deltaTime for frame-rate-independent logic.
    /// </summary>
    public class ActionNode : BTNode
    {
        private readonly Func<Blackboard, float, BTNodeState> _action;

        public ActionNode(Func<Blackboard, float, BTNodeState> action, string name = "Action")
        {
            _action = action;
            NodeName = name;
        }

        public override BTNodeState Tick(Blackboard blackboard, float deltaTime)
        {
            return _action(blackboard, deltaTime);
        }
    }
}
```

### Blackboard.cs — 数据总线

```csharp
// Blackboard.cs
using System;
using System.Collections.Generic;
using UnityEngine;

namespace ArenaAI
{
    /// <summary>
    /// Per-agent key-value store for behavior tree data.
    /// Keys are strings; values are typed via generic accessors.
    /// 
    /// Design notes:
    /// - Uses Dictionary{string, object} internally. The boxing overhead is negligible
    ///   for the ~20-50 reads/writes per frame that a typical BT generates.
    /// - All Unity object references (Transform, NavMeshAgent, Animator, etc.) are
    ///   stored here rather than captured in node lambdas, enabling testability.
    /// - A shared squad Blackboard (static) exists for inter-agent communication.
    /// </summary>
    public class Blackboard
    {
        private readonly Dictionary<string, object> _data = new Dictionary<string, object>();

        /// <summary>
        /// Set a value. Overwrites any existing value for the same key.
        /// </summary>
        public void Set<T>(string key, T value)
        {
            _data[key] = value;
        }

        /// <summary>
        /// Get a value. Throws KeyNotFoundException if the key does not exist.
        /// Use TryGet for safe access.
        /// </summary>
        public T Get<T>(string key)
        {
            if (_data.TryGetValue(key, out object value))
            {
                if (value is T typed) return typed;
                // Handle Unity's destroyed object references: a destroyed GameObject
                // compared with == null returns true, but its type is still UnityEngine.Object.
                if (value == null && typeof(T).IsSubclassOf(typeof(UnityEngine.Object)))
                    return default;
                throw new InvalidCastException(
                    $"Blackboard key '{key}' is {value?.GetType().Name ?? "null"}, not {typeof(T).Name}");
            }
            throw new KeyNotFoundException($"Blackboard key '{key}' not found");
        }

        /// <summary>
        /// Try to get a value. Returns true if the key exists and the type matches.
        /// </summary>
        public bool TryGet<T>(string key, out T value)
        {
            if (_data.TryGetValue(key, out object obj))
            {
                if (obj is T typed)
                {
                    value = typed;
                    return true;
                }
                if (obj == null && typeof(T).IsSubclassOf(typeof(UnityEngine.Object)))
                {
                    value = default;
                    return true;
                }
            }
            value = default;
            return false;
        }

        /// <summary>
        /// Check if a key exists in the blackboard.
        /// </summary>
        public bool HasKey(string key) => _data.ContainsKey(key);

        /// <summary>
        /// Remove a key. Does nothing if the key doesn't exist.
        /// </summary>
        public void Remove(string key) => _data.Remove(key);

        /// <summary>
        /// Clear all entries. Called when the agent is recycled (object pool).
        /// </summary>
        public void Clear() => _data.Clear();

        /// <summary>
        /// Increment a float value. Creates the key with value=0 if it doesn't exist,
        /// then adds delta. Useful for timers.
        /// </summary>
        public void AddFloat(string key, float delta)
        {
            float current = TryGet<float>(key, out float val) ? val : 0f;
            Set(key, current + delta);
        }
    }
}
```

### PerceptionComponent.cs — 视觉与听觉

```csharp
// PerceptionComponent.cs
using System.Collections.Generic;
using UnityEngine;

namespace ArenaAI
{
    /// <summary>
    /// Handles sight (cone-shaped) and hearing (radius-based) detection.
    /// Results are written into the agent's Blackboard.
    /// 
    /// Called from AIController.Update() before the behavior tree tick.
    /// </summary>
    public class PerceptionComponent
    {
        private readonly Transform _agentTransform;
        private readonly Blackboard _blackboard;
        private readonly LayerMask _sightBlockMask;
        private readonly LayerMask _targetMask;

        public float SightRange { get; set; } = 15f;
        public float SightHalfAngle { get; set; } = 60f;
        public float HearingRadius { get; set; } = 30f;

        /// <summary>
        /// How long the agent "remembers" a target after losing sight (seconds).
        /// </summary>
        public float MemoryDuration { get; set; } = 3f;

        private float _memoryTimer;
        private Transform _lastSeenTarget;

        public PerceptionComponent(Transform agentTransform, Blackboard blackboard,
            LayerMask sightBlockMask, LayerMask targetMask)
        {
            _agentTransform = agentTransform;
            _blackboard = blackboard;
            _sightBlockMask = sightBlockMask;
            _targetMask = targetMask;
        }

        /// <summary>
        /// Run perception for this frame. Should be called before BT tick.
        /// Writes "target", "target_last_known_position" to blackboard.
        /// </summary>
        public void UpdatePerception(List<Transform> potentialTargets, float deltaTime)
        {
            Transform detected = null;
            Vector3 detectedPosition = Vector3.zero;
            bool sawTarget = false;

            // 1. Sight check: raycast to each potential target within range + cone
            foreach (Transform target in potentialTargets)
            {
                if (target == null) continue;

                Vector3 dirToTarget = target.position - _agentTransform.position;
                float dist = dirToTarget.magnitude;

                if (dist > SightRange) continue;

                float angle = Vector3.Angle(_agentTransform.forward, dirToTarget.normalized);
                if (angle > SightHalfAngle) continue;

                if (Physics.Raycast(_agentTransform.position, dirToTarget.normalized,
                    out RaycastHit hit, dist, _sightBlockMask))
                {
                    // Something blocked the line of sight — skip
                    continue;
                }

                // We can see this target
                detected = target;
                detectedPosition = target.position;
                sawTarget = true;
                break; // take the first visible target
            }

            // 2. Hearing check: any loud sounds within radius
            if (!sawTarget)
            {
                foreach (Transform target in potentialTargets)
                {
                    if (target == null) continue;
                    float dist = Vector3.Distance(_agentTransform.position, target.position);
                    if (dist <= HearingRadius)
                    {
                        // In a real implementation, each target would have a "noise level"
                        // based on their current action (walking=10, running=20, shooting=50).
                        // For the capstone, we simplify: if within hearing radius, detect.
                        detected = target;
                        detectedPosition = target.position;
                        break;
                    }
                }
            }

            // 3. Write to blackboard
            if (detected != null)
            {
                _blackboard.Set("target", detected);
                _blackboard.Set("target_last_known_position", detectedPosition);
                _memoryTimer = MemoryDuration;
                _lastSeenTarget = detected;
            }
            else if (_lastSeenTarget != null && _memoryTimer > 0f)
            {
                _memoryTimer -= deltaTime;
                if (_memoryTimer <= 0f)
                {
                    _blackboard.Remove("target");
                    _blackboard.Remove("target_last_known_position");
                    _lastSeenTarget = null;
                }
                // Else: keep the last known position (memory system)
            }
        }

        /// <summary>
        /// Check if a specific point has line of sight from the agent.
        /// Used by ranged enemies to verify they have a clear shot.
        /// </summary>
        public bool HasLineOfSight(Vector3 point)
        {
            Vector3 dir = point - _agentTransform.position;
            float dist = dir.magnitude;
            if (dist > SightRange) return false;
            return !Physics.Raycast(_agentTransform.position, dir.normalized, dist, _sightBlockMask);
        }

        #region Debug Visualization

        public void DrawGizmos()
        {
            Vector3 pos = _agentTransform.position;

            // Sight cone
            Gizmos.color = new Color(1f, 1f, 0f, 0.15f);
            DrawGizmoCone(pos, _agentTransform.forward, SightRange, SightHalfAngle);

            // Hearing radius
            Gizmos.color = new Color(0f, 0.5f, 1f, 0.1f);
            Gizmos.DrawWireSphere(pos, HearingRadius);

            // Target indicator
            if (_blackboard.TryGet<Transform>("target", out Transform tgt) && tgt != null)
            {
                Gizmos.color = Color.red;
                Gizmos.DrawLine(pos, tgt.position);
                Gizmos.DrawSphere(tgt.position, 0.3f);
            }
        }

        private static void DrawGizmoCone(Vector3 origin, Vector3 direction, float range, float halfAngle)
        {
            int segments = 20;
            float angleStep = (halfAngle * 2f) / segments;
            Vector3[] points = new Vector3[segments + 2];
            points[0] = origin;
            Quaternion baseRot = Quaternion.LookRotation(direction);

            for (int i = 0; i <= segments; i++)
            {
                float angle = -halfAngle + angleStep * i;
                Quaternion rot = baseRot * Quaternion.Euler(0f, angle, 0f);
                points[i + 1] = origin + rot * Vector3.forward * range;
            }

            // Draw filled arc
            for (int i = 1; i < points.Length - 1; i++)
            {
                Gizmos.DrawLine(points[0], points[i]);
                Gizmos.DrawLine(points[0], points[i + 1]);
                Gizmos.DrawLine(points[i], points[i + 1]);
            }

            // Draw arc outline
            Gizmos.color = new Color(1f, 1f, 0f, 0.3f);
            for (int i = 1; i < points.Length - 1; i++)
            {
                Gizmos.DrawLine(points[i], points[i + 1]);
            }
        }

        #endregion
    }
}
```

### AIController.cs — AI 大脑

```csharp
// AIController.cs
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

namespace ArenaAI
{
    /// <summary>
    /// The brain of an AI agent. Owns the Blackboard, Behavior Tree, Perception,
    /// and drives the agent's body (NavMeshAgent, Animator).
    /// 
    /// Usage: Attach to an enemy GameObject that has a NavMeshAgent.
    /// In Awake, call BuildMyBehaviorTree() to construct the BT.
    /// </summary>
    public abstract class AIController : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] protected NavMeshAgent _navAgent;
        [SerializeField] protected Animator _animator;
        [SerializeField] protected Transform _eyesTransform; // optional: move sight origin up from feet

        [Header("Perception")]
        [SerializeField] protected LayerMask _sightBlockMask = ~0;
        [SerializeField] protected LayerMask _targetMask = ~0;

        [Header("Ticking")]
        [SerializeField] protected int _tickIntervalFrames = 1; // set > 1 for AI LOD
        [SerializeField] protected bool _showDebugGizmos = true;

        // Core components
        protected Blackboard _blackboard;
        protected PerceptionComponent _perception;
        protected BTNode _rootNode;

        // Target tracking
        private List<Transform> _potentialTargets = new List<Transform>();
        private int _frameCounter;

        #region Unity Lifecycle

        protected virtual void Awake()
        {
            _blackboard = new Blackboard();
            _perception = new PerceptionComponent(
                _eyesTransform != null ? _eyesTransform : transform,
                _blackboard,
                _sightBlockMask,
                _targetMask
            );

            // Register agent's own components on the blackboard
            _blackboard.Set("agent_transform", transform);
            _blackboard.Set("nav_agent", _navAgent);
            _blackboard.Set("animator", _animator);
            _blackboard.Set("controller", this);

            // Build the behavior tree — defined by the subclass
            _rootNode = BuildBehaviorTree();
        }

        protected virtual void Start()
        {
            // Find the player (or any target) — replace with your own target management
            GameObject player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
            {
                _potentialTargets.Add(player.transform);
            }
        }

        protected virtual void Update()
        {
            _frameCounter++;
            if (_frameCounter % _tickIntervalFrames != 0) return;

            float deltaTime = Time.deltaTime * _tickIntervalFrames;

            // 1. Sense
            _perception.UpdatePerception(_potentialTargets, deltaTime);

            // 2. Think
            _rootNode?.Tick(_blackboard, deltaTime);

            // 3. Act — apply movement from blackboard
            ApplyMovement();
            ApplyAnimation();
        }

        protected virtual void OnDrawGizmos()
        {
            if (!_showDebugGizmos) return;
            _perception?.DrawGizmos();
            DrawBTDebugGizmos();
        }

        #endregion

        #region Behavior Tree (override in subclass)

        /// <summary>
        /// Override in subclass to construct the agent's behavior tree.
        /// Example:
        ///   return new Selector(new List{BTNode} {
        ///       CombatSubtree(),
        ///       PatrolSubtree(),
        ///   });
        /// </summary>
        protected abstract BTNode BuildBehaviorTree();

        #endregion

        #region Act — movement and animation

        private void ApplyMovement()
        {
            if (_blackboard.TryGet<Vector3>("move_target", out Vector3 target))
            {
                _navAgent.isStopped = false;
                _navAgent.SetDestination(target);
                _blackboard.Set("is_moving", true);
            }
            else
            {
                _navAgent.isStopped = true;
                _blackboard.Set("is_moving", false);
            }
        }

        private void ApplyAnimation()
        {
            if (_animator == null) return;

            bool isMoving = _blackboard.TryGet<bool>("is_moving", out bool mv) && mv;
            float speed = isMoving ? _navAgent.velocity.magnitude : 0f;
            _animator.SetFloat("Speed", speed);

            if (_blackboard.TryGet<bool>("is_attacking", out bool att))
                _animator.SetBool("IsAttacking", att);
        }

        #endregion

        #region Debug Visualization

        [Header("BT Debug")]
        [SerializeField] private bool _debugShowActivePath = true;

        // Tracks which node is currently Running for debug display
        private string _lastRunningNodePath = "";

        private void DrawBTDebugGizmos()
        {
            if (_rootNode == null || !_debugShowActivePath) return;

            // Display the currently-running node's name above the agent
            Vector3 labelPos = transform.position + Vector3.up * 2.5f;
            UnityEditor.Handles.Label(labelPos, $"BT: {_lastRunningNodePath}");
        }

        #endregion

        #region Public API

        /// <summary>
        /// Register a potential target for perception checks.
        /// </summary>
        public void RegisterTarget(Transform target)
        {
            if (!_potentialTargets.Contains(target))
                _potentialTargets.Add(target);
        }

        /// <summary>
        /// Access the blackboard for external systems (e.g., squad coordination).
        /// </summary>
        public Blackboard GetBlackboard() => _blackboard;

        /// <summary>
        /// Configure perception parameters at runtime (useful for archetype setup).
        /// </summary>
        public void ConfigurePerception(float sightRange, float sightHalfAngle, float hearingRadius)
        {
            _perception.SightRange = sightRange;
            _perception.SightHalfAngle = sightHalfAngle;
            _perception.HearingRadius = hearingRadius;
        }

        #endregion
    }
}
```

### 完整示例：Grunt 兵种行为树

这是 Grunt（近战冲锋小兵）的完整行为树定义。继承 `AIController`，在 `BuildBehaviorTree()` 中组装：

```csharp
// GruntAI.cs
using System.Collections.Generic;
using UnityEngine;

namespace ArenaAI
{
    /// <summary>
    /// Grunt archetype: aggressive melee unit.
    /// - Patrols waypoints when no target
    /// - Charges directly at detected player
    /// - Attacks in melee range
    /// - Retreats at low health
    /// </summary>
    public class GruntAI : AIController
    {
        [Header("Grunt Config")]
        [SerializeField] private Transform[] _waypoints;
        [SerializeField] private float _attackRange = 2f;
        [SerializeField] private float _attackDamage = 15f;
        [SerializeField] private float _attackCooldown = 1f;
        [SerializeField] private float _retreatHealthPercent = 0.2f;
        [SerializeField] private float _moveSpeed = 5f;

        private float _maxHealth = 100f;
        private float _currentHealth;

        protected override void Awake()
        {
            base.Awake();

            // Configure perception for Grunt
            _perception.SightRange = 12f;
            _perception.SightHalfAngle = 70f;
            _perception.HearingRadius = 20f;

            // Configure NavMeshAgent
            _navAgent.speed = _moveSpeed;
            _navAgent.stoppingDistance = _attackRange * 0.8f;

            // Initialize health
            _currentHealth = _maxHealth;
            _blackboard.Set("health", _currentHealth);
            _blackboard.Set("max_health", _maxHealth);
            _blackboard.Set("health_percent", 1f);
        }

        protected override BTNode BuildBehaviorTree()
        {
            // Root: Priority selector
            // Priority order: Dead > Retreat > Combat > Patrol
            return new Selector(new List<BTNode>
            {
                // Priority 1: Death
                new Sequence(new List<BTNode>
                {
                    new ConditionNode(bb => bb.Get<float>("health_percent") <= 0f, "IsDead"),
                    BuildDeathSequence(),
                }, "DeathSeq"),

                // Priority 2: Retreat at low health
                new Sequence(new List<BTNode>
                {
                    new ConditionNode(bb =>
                        bb.TryGet<Transform>("target", out _) &&
                        bb.Get<float>("health_percent") <= _retreatHealthPercent,
                        "ShouldRetreat"),
                    BuildFleeAction(),
                }, "RetreatSeq"),

                // Priority 3: Combat
                new Sequence(new List<BTNode>
                {
                    new ConditionNode(bb => bb.TryGet<Transform>("target", out Transform t) && t != null,
                        "HasTarget"),
                    BuildCombatSubtree(),
                }, "CombatSeq"),

                // Priority 4: Patrol (default)
                BuildPatrolSubtree(),
            }, "GruntRoot");
        }

        private BTNode BuildCombatSubtree()
        {
            return new Selector(new List<BTNode>
            {
                // Sub-priority A: Attack if in range
                new Sequence(new List<BTNode>
                {
                    new ConditionNode(bb =>
                    {
                        if (!bb.TryGet<Transform>("target", out Transform tgt) || tgt == null)
                            return false;
                        float dist = Vector3.Distance(
                            bb.Get<Transform>("agent_transform").position,
                            tgt.position);
                        return dist <= _attackRange;
                    }, "InAttackRange"),
                    BuildMeleeAttackAction(),
                }, "MeleeAttack"),

                // Sub-priority B: Chase the target
                BuildChaseAction(),
            }, "CombatSubtree");
        }

        #region Leaf Actions

        private BTNode BuildMeleeAttackAction()
        {
            return new Cooldown(new ActionNode((bb, dt) =>
            {
                bb.Set("is_attacking", true);

                if (!bb.TryGet<Transform>("target", out Transform tgt) || tgt == null)
                {
                    bb.Set("is_attacking", false);
                    return BTNodeState.Failure;
                }

                // Face the target
                Transform self = bb.Get<Transform>("agent_transform");
                Vector3 dir = (tgt.position - self.position).normalized;
                dir.y = 0;
                if (dir != Vector3.zero)
                    self.rotation = Quaternion.LookRotation(dir);

                // Deal damage (once per attack — handled by Cooldown decorator)
                // In production: send event to damage system instead of direct call
                float currentHealth = bb.Get<float>("health");
                bb.Set("health", currentHealth - _attackDamage); // self-damage for testing

                bb.Set("is_attacking", false);
                return BTNodeState.Success;
            }, "MeleeAttack"), _attackCooldown, "AttackCooldown");
        }

        private BTNode BuildChaseAction()
        {
            return new ActionNode((bb, dt) =>
            {
                if (!bb.TryGet<Transform>("target", out Transform tgt) || tgt == null)
                    return BTNodeState.Failure;

                bb.Set("move_target", tgt.position);
                return BTNodeState.Running; // keep chasing
            }, "ChaseTarget");
        }

        private BTNode BuildFleeAction()
        {
            return new ActionNode((bb, dt) =>
            {
                if (!bb.TryGet<Transform>("target", out Transform tgt) || tgt == null)
                    return BTNodeState.Failure;

                Transform self = bb.Get<Transform>("agent_transform");
                Vector3 fleeDir = (self.position - tgt.position).normalized;
                Vector3 fleePos = self.position + fleeDir * 15f;

                // Try to find a valid NavMesh position in the flee direction
                if (UnityEngine.AI.NavMesh.SamplePosition(fleePos,
                    out UnityEngine.AI.NavMeshHit hit, 10f, UnityEngine.AI.NavMesh.AllAreas))
                {
                    bb.Set("move_target", hit.position);
                }
                else
                {
                    bb.Set("move_target", fleePos);
                }

                return BTNodeState.Running;
            }, "Flee");
        }

        private BTNode BuildPatrolSubtree()
        {
            return new Sequence(new List<BTNode>
            {
                new ActionNode((bb, dt) =>
                {
                    if (_waypoints == null || _waypoints.Length == 0)
                        return BTNodeState.Failure;

                    int index = bb.TryGet<int>("patrol_index", out int i) ? i : 0;
                    Vector3 target = _waypoints[index].position;

                    bb.Set("move_target", target);

                    float dist = Vector3.Distance(
                        bb.Get<Transform>("agent_transform").position, target);
                    if (dist < 1.5f)
                    {
                        index = (index + 1) % _waypoints.Length;
                        bb.Set("patrol_index", index);
                    }

                    return BTNodeState.Running;
                }, "Patrol"),
            }, "PatrolSeq");
        }

        private BTNode BuildDeathSequence()
        {
            return new Sequence(new List<BTNode>
            {
                new ActionNode((bb, dt) =>
                {
                    bb.Set("is_attacking", false);
                    bb.Set("is_moving", false);
                    bb.Get<UnityEngine.AI.NavMeshAgent>("nav_agent").isStopped = true;
                    bb.Get<Animator>("animator")?.SetTrigger("Death");
                    return BTNodeState.Success;
                }, "Die"),
            }, "DeathSeq");
        }

        #endregion

        #region Public API

        public void TakeDamage(float amount)
        {
            _currentHealth = Mathf.Max(0, _currentHealth - amount);
            _blackboard.Set("health", _currentHealth);
            _blackboard.Set("health_percent", _currentHealth / _maxHealth);
        }

        #endregion

        private void OnValidate()
        {
            if (_navAgent == null) _navAgent = GetComponent<NavMeshAgent>();
            if (_animator == null) _animator = GetComponent<Animator>();
        }
    }
}
```

### 小队黑板 (SquadBlackboard.cs)

```csharp
// SquadBlackboard.cs
using System.Collections.Generic;
using UnityEngine;

namespace ArenaAI
{
    /// <summary>
    /// Shared blackboard for squad-level coordination.
    /// All agents in the same squad share this instance.
    /// Agents read from it in their BT Condition nodes, and write to it in Action nodes.
    /// </summary>
    public class SquadBlackboard
    {
        private readonly Dictionary<string, object> _data = new Dictionary<string, object>();

        public void Set<T>(string key, T value)
        {
            lock (_data) { _data[key] = value; }
        }

        public T Get<T>(string key)
        {
            lock (_data)
            {
                if (_data.TryGetValue(key, out object value) && value is T typed)
                    return typed;
                return default;
            }
        }

        public bool TryGet<T>(string key, out T value)
        {
            lock (_data)
            {
                if (_data.TryGetValue(key, out object obj) && obj is T typed)
                {
                    value = typed;
                    return true;
                }
            }
            value = default;
            return false;
        }

        public bool HasKey(string key)
        {
            lock (_data) { return _data.ContainsKey(key); }
        }

        public void Remove(string key)
        {
            lock (_data) { _data.Remove(key); }
        }
    }
}
```

---

## 3. 练习

整个教程本身就是一个练习。你从框架代码开始，逐步构建完整的 AI 系统。

### 里程碑 1: 框架 + 巡逻 + 追击

**目标**：AIController + Blackboard + BT 引擎能跑起来。Grunt 在场景中巡逻，检测到玩家后追击。

**验收清单**：
- [ ] 所有框架代码编译通过，无错误
- [ ] 场景中放置一个 Grunt，配置 3 个以上 waypoint，它能循环巡逻
- [ ] 玩家进入 Grunt 视觉锥后，Grunt 停止巡逻并追击玩家
- [ ] 玩家跑出视觉锥并超过记忆时间后，Grunt 返回巡逻
- [ ] `OnDrawGizmos` 能正确绘制视觉锥和听觉半径
- [ ] 巡逻路径点索引正确循环，不会越界

**验证方式**：在 Unity Editor 中 Play，观察 Scene 视图中的 Gizmos。手动移动玩家靠近/远离 Grunt，确认行为切换。

**预期耗时**：2 小时。约 1 小时把框架代码集成到项目 + 配置 waypoint，1 小时调试视觉检测和追击逻辑。

### 里程碑 2: 战斗 + 撤退 + 小队支援

**目标**：完整的战斗循环。近战攻击有伤害 + 冷却、血量低于阈值自动撤退、小队成员之间互相支援。

**验收清单**：
- [ ] Grunt 进入攻击范围后执行近战攻击，攻击有 cooldown（两次攻击之间有明显间隔）
- [ ] 攻击时 Grunt 面朝玩家，且 Animator 播放攻击动画（通过黑板驱动）
- [ ] Grunt 血量低于 20% 时自动撤退（远离玩家方向移动）
- [ ] 同一小队的两个 Grunt，一个发现玩家后写入 Squad Blackboard，另一个也进入战斗状态
- [ ] 低血量 Grunt 呼救后，附近的小队成员评估并决定是否支援
- [ ] 死亡动画触发后 NavMeshAgent 停止、Collider 禁用

**验证方式**：放置 2 个同小队 Grunt。让玩家靠近其中一个——另一个也应该响应。观察战斗过程中的攻击间隔和血量变化。确认撤退行为在阈值触发。

**预期耗时**：2 小时。战斗 cooldown + 伤害系统需要小心地调试伤害事件的触发时机（确保只触发一次，而非每帧）。

### 里程碑 3: 全部 4 种兵种 + 波次系统

**目标**：Sniper、Heavy、Boss 都能工作。WaveManager 按波次生成敌人。

**验收清单**：
- [ ] Sniper: 在远距离检测到玩家后远程开火，每次射击后移动到新掩体位置
- [ ] Heavy: 缓慢推进到玩家附近，AoE 攻击对范围内的所有玩家单位造成伤害，从不撤退
- [ ] Boss: Phase1 远程投射 + 召唤小兵，Phase2 (50% HP) 转移为近战狂暴模式
- [ ] WaveManager 按配置在每波间隔后生成指定类型和数量的敌人
- [ ] HUD 显示当前波次数和剩余敌人数量
- [ ] 所有敌人被消灭 → 胜利 UI；玩家死亡 → 失败 UI

**验证方式**：单独测试每个兵种——放置一个进入场景，确认其特有行为（Sniper 换掩体、Heavy AoE、Boss 阶段转移）。然后配置波次数据，从头到尾打一次确认游戏循环完整。

**预期耗时**：2 小时。Boss 的 HSM 需要比较多的工作——管理阶段转移数据和 Phase1/Phase2 的行为切换逻辑。

### 里程碑 4: 润色 + 调试工具 (可选)

**目标**：AI LOD 优化、更好的调试可视化、性能调优。

**验收清单**：
- [ ] 场景中同时存在 50+ 敌人，帧率保持 > 30fps（通过 AI LOD 降频 + NavMeshAgent 距离限制）
- [ ] 调试可视化显示当前 BT 活跃节点名称（在 Scene 视图的敌人头顶）
- [ ] 选中任何敌人时，Inspector 中显示其 Blackboard 当前所有 key-value（可通过自定义 Editor 脚本实现）
- [ ] 运行时可以暂停/单步执行 BT（通过 `_tickIntervalFrames = 999` 冻结 + 手动调用 Tick）
- [ ] 视觉锥和听觉半径参数在运行时调整立即生效

**预期耗时**：2 小时。

### 扩展方向 (让你的作品集与众不同)

以下是超出基本要求的可选特性——任何一个都会让面试官印象深刻：

1. **可视化行为树编辑器**：用 Unity GraphView API 构建一个节点图编辑器，拖拽节点编辑行为树，保存为 ScriptableObject 资产。替代代码手写的 `BuildBehaviorTree()`。
2. **行为树回放系统**：记录最近 10 秒的 BT 决策路径和 Blackboard 状态变化，在 Inspector 中逐帧回放。调试"为什么这个敌人在那一帧做了那个决定"时极其有用。
3. **Utility AI 混合**：将 Grunt 的行为树改为 Utility AI（每个行为有 score 函数，每帧选最高分的执行），与现有 BT 系统并存。展示你对多种范式的掌握。
4. **GOAP 规划器**：替代 Boss 的 Phase1 行为树，使用 GOAP（Goal-Oriented Action Planning）动态规划行动序列。展示你理解"静态树 vs 动态规划"的权衡。
5. **网络多人 AI**：让波次中的敌人由服务器控制（AI 只运行在服务器端），客户端通过 NetworkTransform 同步。展示你理解游戏 AI 在网络架构中的位置。
6. **机器学习整合**：使用 Unity ML-Agents 训练一个基于强化学习的 AI agent，与基于 BT 的敌人对战。展示你理解数据驱动 AI 与传统 AI 的互补关系。
7. **性能基准测试**：编写自动化测试，测量 100/200/500 个 agent 同时活跃时的帧时间和 BT tick 开销。生成性能报告图表。展示你有关注生产级性能的意识。

---

## 4. 扩展阅读

### 开源游戏 AI 项目学习

| 项目 | 链接 | 学习重点 |
|:-----|:-----|:---------|
| **UE4/UE5 Behavior Tree Sample** | [Unreal Engine Documentation: Behavior Trees](https://dev.epicgames.com/documentation/en-us/unreal-engine/behavior-trees-in-unreal-engine) | 世界最成熟的商业 BT 实现。重点看 Decorator 的条件中断 (Conditional Abort)、Service 的并行更新、EQS (Environment Query System) 的空间查询 |
| **Halo 2 AI GDC 演讲** | Damian Isla 的 [GDC 2005: "Managing Complexity in Halo 2 AI"](https://www.gdcvault.com/play/1013282/Managing-Complexity-in-the-Halo) | BT 在 AAA 游戏中的首次大规模应用。理解 Halo 的"刺激-行为"模型和树的重评估策略 |
| **Killzone AI** | [GDC 2009: "Creating the AI for Killzone 2"](https://www.gdcvault.com/play/1434/Creating-the-AI-for-Killzone) | 分层 AI 架构的实战案例。重点看 Commander → Squad → Individual 的三层战术协调 |
| **F.E.A.R. GOAP** | Jeff Orkin 的 ["Three States and a Plan: The AI of F.E.A.R."](https://alumni.media.mit.edu/~jorkin/gdc2006_orkin_jeff_fear.pdf) | GOAP 在商业游戏中的第一个成功案例。理解"世界状态 + 目标 + 动作前置条件/效果"的规划模型 |
| **Rainbow Six: Siege AI** | [GDC 2018: "The AI of Rainbow Six: Siege"](https://www.youtube.com/watch?v=3E0LKNIECIo) | 多层 AI + 环境交互的案例。理解"通视" (line-of-sight) 不是简单的 raycast——需要考虑掩体的部分遮挡 |
| **PandAI (Panda3D)** | [GitHub: PandAI](https://github.com/panda3d/panda3d) 中的 `pandai/` 目录 | 完整的开源游戏 AI 框架，包含 FSM + BT + 路径规划的集成。适合学习"C++ 游戏引擎的 AI 子系统"的代码组织方式 |
| **Bonsai Behavior Tree** | [GitHub: bonsai-bt](https://github.com/j0ty/bonsai-behavior-tree) | 模型驱动的 C++17 行为树库。独特的"在编译时定义树结构"方法——使用模板元编程而不是运行时组装 |

### 作品集托管

| 平台 | 适合展示什么 | 建议 |
|:-----|:------------|:-----|
| **GitHub** | 完整项目源码 + README + Wiki | 写一篇详细的 `README.md`：架构图 (ASCII art 或截图)、GIF 演示、设计决策记录 (ADR)。把代码组织成清晰的目录结构。加上 CI (GitHub Actions) 自动运行测试 |
| **itch.io** | 可玩的 WebGL 构建 | 上传一个 WebGL 版本，让面试官直接在浏览器中体验。加上简单的操作说明和关卡 |
| **个人博客/网站** | 技术深入文章 | 写 2-3 篇技术博客："我是如何设计 AI 感知系统的"、"行为树 vs HSM 在 Boss AI 中的混合实践"、"优化 100+ agent 的性能实践" |
| **YouTube / Bilibili** | 游戏玩法 + 技术讲解视频 | 5-10 分钟的视频：先展示游戏玩法（玩家战斗 + AI 行为），再切到技术讲解（架构图 + 代码亮点）。这是最容易被分享和传播的形式 |

### 游戏 AI 求职资源

| 资源 | 链接 | 说明 |
|:-----|:-----|:-----|
| **AI Game Programmer Guild** | [aigameprogrammer.com](https://aigameprogrammer.com/) | 游戏 AI 程序员的专业社群，有专属的 Slack/Discord 和工作列表 |
| **Game AI Pro 系列** | [gameaipro.com](https://www.gameaipro.com/) | 三卷免费在线书籍，包含 AAA 游戏 AI 程序员的实战文章。面试前必读至少 10 篇 |
| **GDC Vault** | [gdcvault.com](https://www.gdcvault.com/) | GDC (Game Developers Conference) 演讲的录像和幻灯片。AI 相关的 session 很多是免费的 |
| **AI and Games (YouTube)** | [youtube.com/@AIandGames](https://www.youtube.com/@AIandGames) | Tommy Thompson 的频道，深度分析商业游戏的 AI 设计。适合在通勤或休息时观看 |
| **LinkedIn 搜索** | 搜索 "Gameplay AI Programmer" / "AI Engineer" 在游戏公司 | 阅读职位描述，了解行业需求。把职位描述中的关键词整合到你的 GitHub 项目 README 中 |
| **r/gameai (Reddit)** | [reddit.com/r/gameai](https://www.reddit.com/r/gameai/) | 游戏 AI 社区。可以发布你的项目获取反馈 |

---

## 常见陷阱

### 陷阱 1: 范围蔓延——在行为树完成前就想加"酷炫的功能"

**症状**：阶段 1 才完成一半，就开始想"粒子特效在攻击时怎么触发"、"要不要加一个潜行系统"、"是不是应该让敌人有情绪状态"。

**后果**：框架永远无法达到"跑起来"的状态。你花了两周时间在无关系统上，核心的巡逻+追击+攻击循环还没工作。

**正确做法**：严格遵循阶段顺序。每个阶段有一个明确的"可以玩"的状态——阶段 1 是"敌人巡逻+追击"，阶段 2 是"完整的战斗循环"。在达到当前阶段的"可以玩"状态之前，绝不跳到下一个阶段的功能。**先让它工作，再让它变好。**

### 陷阱 2: 过度设计框架——在没看到行为之前就写"完美的抽象"

**症状**：在实现第一个 `ActionNode` 之前，已经定义了 `BTNodeFactory`、`IBTNodeSerializer`、`BTBehaviorTreeAsset`、`BTBehaviorTreeImporter`、`BTVisualEditorWindow`……但是没有一行代码让敌人动起来。

**后果**：当你终于开始写实际行为时，发现框架的抽象与你需要的行为不匹配——你过度设计的东西反而成为了障碍。更糟糕的是，你可能已经花了 10+ 小时在这些"基础设施"上。

**正确做法**：在阶段 1，框架代码就是你上面看到的那些——`BTNode` 抽象类 + 四个复合节点 + 两个叶子节点 + `Blackboard` + `AIController`。这五个文件，不超过 400 行代码，足够支撑前三个阶段的所有行为。**在行为驱动框架的形状**——等你写过 Patrol、Chase、Attack 三个行为后，你会自然看到"哪些代码可以提取为可复用的模式"。那时再抽象，不提前。

### 陷阱 3: 不测试多 agent

**症状**：一直在场景中用一个 Grunt 测试。确认它的巡逻、追击、攻击都正常后，就认为"系统完成了"。

**后果**：当你最终在阶段 3 同时生成 10 个 Grunt 时，可能出现以下问题：所有 agent 共享了同一个 Blackboard（因为你的 Blackboard 不小心被设为了静态字段）、BT 节点状态在多 agent 间串扰（因为你的 Clone 逻辑有 bug）、NavMeshAgent 互相推挤导致死锁、性能暴跌（因为每个 agent 每帧都做射线检测）。

**正确做法**：从阶段 1 开始，就至少在场景中放置 2 个 Grunt。如果你用我们提供的代码（每个 AIController 在 Awake 中 `new Blackboard()`），它们天然隔离。但如果你修改了架构，确保在修改后立即测试多 agent 场景。**在阶段 2 就生成 5 个 agent，而不是等到阶段 4。**

### 陷阱 4: 调试可视化被推迟到"最后"

**症状**：觉得"Gizmos 可以后面再加，先把功能做完"。或者只在 Scene 视图中手动点选 agent 来观察状态。

**后果**：当行为树变得复杂（Selector 嵌套 Sequence 嵌套 Condition → Action → Cooldown → Action），你完全不知道"为什么这个敌人在这一帧做了这个决定"。你可能花了 2 小时在一个 bug 上，而这个 bug 只要画出当前 BT 活跃节点路径就能在 30 秒内定位。

**正确做法**：阶段 1 就加上视觉锥的 Gizmos（代码已提供）。在 BT Tick 过程中打印当前 Running 节点的 `NodeName` 到一个 `StringBuilder`，在 `OnDrawGizmos` 中用 `Handles.Label` 显示在 agent 头顶。**这个"简陋版"调试器花费不到 15 分钟实现，但能省下无数小时的调试时间。**

### 陷阱 5: 不保存中间工作状态

**症状**：在一个分支上连续工作 6 小时，没有 commit。然后尝试一个"大规模重构"（比如把 Blackboard 从 Dictionary 改成无装箱方案），重构失败后无法回到之前的工作状态。

**后果**：损失数小时的工作。更糟糕的是，你可能因为"差不远了"的沉没成本心理，继续在失败的重构上耗费更多时间。

**正确做法**：在每个阶段内部，每完成一个"可以玩"的子状态就做一次 git commit。例如：`commit: "feat: patrol + chase working with 1 grunt"` → `commit: "feat: melee attack with cooldown"` → `commit: "feat: retreat at low health"`。这样你可以随时回到上一个工作状态，也可以让面试官看到你的开发过程（commit 历史是项目的一部分）。

### 陷阱 6: 在 Tick 路径中分配内存

**症状**：在 `ActionNode` 的委托中使用 LINQ、`new List<>()`、字符串拼接、闭包捕获等会在堆上分配内存的操作。

**后果**：在 50 个 agent 的场景中，每帧的 GC Alloc 可能达到数 KB。Unity 的 Boehm GC 会在分配达到阈值时触发 stop-the-world 回收，导致 50-200ms 的帧停顿——这在战斗中是无法接受的。

**正确做法**：
- 节点的委托**绝不使用 LINQ**（`.Where()`, `.Select()`, `.ToList()` 等）。写显式循环。
- 不要在 `Tick()` / `ActionNode` 委托中 `new` 任何引用类型对象。字符串拼接改用 `StringBuilder`（在 BT 初始化时创建，存储在 Blackboard 中复用）。
- 频繁计算的 `Vector3`（如方向向量）声明为局部变量——它们是值类型，在栈上分配，不产生 GC 压力。
- 使用 Unity 的 Profiler（Window → Analysis → Profiler）的 Deep Profile 模式，确认 BT Tick 路径没有 `GC.Alloc` 条柱。

---

> **系列完结**。这是本学习计划的最后一个教程。回顾你从 FSM 核心概念一路走到完整 AI 系统的路径——你已经具备了在游戏 AI 领域求职和实战所需的核心知识和能力。将这个项目作为你的起点，继续深入探索和构建。
>
> 如果需要持续学习，参考 [扩展阅读](#4-扩展阅读) 中的资源，以及 [练习](#3-练习) 中的扩展方向——每一个都是值得深入探索的方向。
