# 行为树节点类型深度剖析

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 06-bt-fundamentals

---

## 1. 概念讲解

行为树（Behavior Tree, BT）的所有节点可以归入四大类别：**Composite（组合节点）**、**Decorator（装饰节点）**、**Leaf（叶子节点）**、以及 UE 特有的 **Service（服务节点）**。本节逐一剖析每一种节点的语义、返回值规则、执行时机和设计意图。

在学习每种节点之前，回顾基础：每个节点 `Tick()` 返回三个状态之一——`Success`、`Failure`、`Running`。父节点根据子节点的返回值决定下一步行为。这才是行为树的精髓：**控制流由返回值驱动，而非显式跳转**。

### Composite Nodes（组合节点）

组合节点拥有一个或多个子节点，按特定策略依次或并行执行它们。组合节点的核心职责是：**定义子节点之间的控制流关系**。

#### Selector（选择节点 / 优先级节点）

Selector 是最常用的组合节点之一。它的语义是"或"（OR）：从左到右依次执行子节点，遇到第一个返回 `Success` 或 `Running` 的子节点时立即停止，并将该返回值向上传播。如果所有子节点都返回 `Failure`，Selector 自身返回 `Failure`。

```
Selector 的 Tick 伪代码:
  for each child:
    status = child.Tick()
    if status != Failure:
      return status   // Success 或 Running
  return Failure
```

**设计意图**：Selector 实现了**带优先级的行为选择**。左边的子节点优先级高于右边的。经典应用场景是敌人的行为优先级链：

```
Selector (Root)
├── Condition: IsDead?         → Action: Die        // 最高优先级：死亡覆盖一切
├── Condition: Health < 20%?   → Action: Flee       // 危险时逃跑
├── Condition: EnemyInSight?   → Action: Attack     // 看到敌人就攻击
└── Action: Patrol                                   // 兜底：什么都没发生就巡逻
```

关键细节：**Selector 只在子节点返回 `Failure` 时继续尝试下一个子节点**。一旦某个子节点返回 `Running`（例如 `Attack` 是一个需要多帧执行的动画），Selector 停止遍历，下一帧直接从当前 `Running` 的子节点继续——它**不会重新评估前面的条件**。这是大多数标准 Selector 的默认行为，也是"优先级只在进入时评估一次"的来源。

#### Sequence（序列节点）

Sequence 的语义是"与"（AND）：从左到右依次执行子节点，遇到第一个返回 `Failure` 或 `Running` 的子节点时立即停止。如果所有子节点都返回 `Success`，Sequence 自身返回 `Success`。

```
Sequence 的 Tick 伪代码:
  for each child starting from currentIndex:
    status = child.Tick()
    if status != Success:
      return status   // Failure 或 Running
  return Success
```

**设计意图**：Sequence 确保一系列步骤按顺序全部完成。经典场景是"开门"的多步操作：

```
Sequence
├── Action: MoveTo(doorPosition)     // 先走到门旁边
├── Action: PlayAnimation("OpenDoor") // 播放开门动画
└── Action: EnterRoom()               // 进入房间
```

这里的精妙之处在于：每一步都可能跨越多帧。`MoveTo` 在 NPC 到达门前一直返回 `Running`；到达后返回 `Success`，Sequence 才会推进到 `PlayAnimation`。如果中途 `MoveTo` 返回 `Failure`（例如门被锁住、路径不可达），Sequence 整体失败，后续步骤不会执行。

#### Selector vs Sequence 的对称性

| | Selector | Sequence |
|---|---|---|
| 逻辑 | OR（或） | AND（与） |
| 停止条件 | 第一个 Success/Running | 第一个 Failure/Running |
| 遍历方向 | 左→右（优先级递减） | 左→右（步骤递增） |
| 全部成功时 | 返回 Success | 返回 Success |
| 全部失败时 | 返回 Failure | 返回 Failure |

这种对称性让你可以用 Selector 和 Sequence 表达几乎所有的条件-动作组合。Selector 问"我应该做什么？"，Sequence 回答"怎么做"。

#### Parallel（并行节点）

Parallel 同时执行所有子节点，而非顺序执行。它有一个**策略参数**（Policy）决定何时返回：

| 策略 | 含义 | 典型场景 |
|---|---|---|
| `SucceedOnOne` | 任一子节点成功即返回 Success | 多个感知条件任满足其一 |
| `SucceedOnAll` | 所有子节点都成功才返回 Success | 多步并行操作必须全部完成 |
| `FailOnOne` | 任一子节点失败即返回 Failure | 任意一个关键条件不满足就中止 |
| `SucceedOnN(n)` | 至少 n 个子节点成功 | 投票制（如 3 个传感器中至少 2 个确认目标） |
| `MainTask + Background` | 指定一个"主任务"子节点，其余为后台任务 | 移动 + 持续扫描敌人 |

**重要实现细节**：Parallel 节点在某个子节点满足停止条件时需要**终止（Abort）剩余仍在运行的子节点**。被终止的子节点通常执行 `OnAbort()` 回调来清理状态。这是行为树中最复杂的生命周期管理之一。

**经典场景**：

```
Parallel (SucceedOnOne)
├── Condition: EnemyInMeleeRange?
├── Condition: EnemyInRangedRange?
└── Condition: HeardGunshot?
```

这个 Parallel 在**任一**感知条件满足时返回 Success，用于触发"进入战斗"状态。与 Selector 的区别在于：三个条件被**同时**评估（在同一帧），而非顺序评估。

另一个常见用法：

```
Parallel (MainTask: MoveToCover)
├── Action: MoveTo(coverPosition)       // 主任务
└── Action: ScanForThreats()            // 后台持续运行
```

这里 `MoveToCover` 和 `ScanForThreats` 同时执行——NPC 可以边移动边扫描威胁。`ScanForThreats` 可能永远不会返回 Success（纯后台任务），Parallel 的返回值由主任务决定。

#### Random Selector / Random Sequence

这两个变体是在标准 Selector/Sequence 的基础上，将子节点的**执行顺序随机化**（打乱）。语义不变，但优先级/步骤顺序变为随机。

```
RandomSelector:
  1. 随机打乱子节点顺序
  2. 其余逻辑与 Selector 完全相同
```

**用途**：为 AI 行为引入不可预测性，但仍保持确定性框架。例如，一个 Boss 在 Phase 2 随机选择不同的特殊攻击：

```
RandomSelector
├── Action: GroundSlam()
├── Action: FireBreath()
└── Action: SummonMinions()
```

每一轮循环中，Boss 随机选择一种特殊攻击执行。与"在 Action 内部随机选择"的区别在于：RandomSelector 可以给不同选项配置不同的 Decorator（例如 `Cooldown` 限制某技能的频率）。

#### Active Selector（动态重评估选择器）

标准 Selector 在首次找到 `Success`/`Running` 的子节点后，后续帧**不再重新评估前面的节点**。这是性能优化，但也意味着一个高优先级的条件在低优先级行为运行期间发生变化时，Selector 不会自动切回高优先级行为。

**Active Selector** 解决了这个问题：**每一帧都从头重新评估所有子节点**。如果某个更高优先级的子节点（排在更左边）突然返回了 `Success` 或 `Running`，当前正在运行的低优先级子节点会被中止。

```
ActiveSelector 的 Tick 伪代码:
  for each child:
    status = child.Tick()
    if status != Failure:
      // 中止当前运行中的子节点（如果有）
      if (currentRunningChild != null && currentRunningChild != child)
        currentRunningChild.OnAbort()
      currentRunningChild = child
      return status
  return Failure
```

**对比**：

| 特性 | 标准 Selector | Active Selector |
|---|---|---|
| 每帧重新评估前面的条件 | 否 | 是 |
| 高优先级条件触发时切换 | 不（除非当前子节点已完成） | 立即切换 |
| 性能开销 | 低（只 tick 当前子节点） | 高（每帧 tick 多个子节点） |
| 适用场景 | 大部分行为选择 | 需要快速响应环境变化的 AI |

**经典案例**：NPC 正在 Attack，突然血量跌破阈值。使用 Active Selector，`Health < 20% → Flee` 的条件每帧都会被评估，一旦满足，NPC 立即中止攻击逃跑。使用标准 Selector，NPC 必须等 Attack 执行完毕才会重新评估。

> **UE 对应**：在 Unreal Engine 的行为树中，这由 Decorator 的 **Observer Aborts** 机制实现——Decorator 可以配置为在条件变化时触发所在分支的重评估。我们将在 Tutorial 12 中深入讨论这一机制。

---

### Decorator Nodes（装饰节点）

装饰节点只有一个子节点。它不执行具体行为，而是**修改子节点的返回值、控制子节点的执行条件、或限制子节点的执行次数/时间**。

#### Inverter（取反）

将子节点的 `Success` 变为 `Failure`，`Failure` 变为 `Success`，`Running` 不变。

```
Inverter.Tick():
  status = child.Tick()
  if status == Success: return Failure
  if status == Failure: return Success
  return status  // Running
```

**经典用法**：

```
Selector
├── Sequence
│   ├── Condition: HasTarget?
│   └── Action: Attack()
└── Inverter
    └── Condition: IsPatrolComplete?
        → Action: NextWaypoint()
```

这里 `Inverter(IsPatrolComplete?)` 的语义是"如果巡逻**还未**完成"→ 继续移动到下一个路径点。在行为树中没有原生的"否则"节点，Inverter 是表达"NOT"逻辑的标准方式。

#### Repeater（重复执行）

让子节点重复执行。有三种模式：

```
Repeater(count=N):  执行 N 次后返回 Success
Repeater(forever):  永远执行（永远不会返回 Success/Failure，始终 Running）
Repeater(untilFail): 重复执行直到子节点返回 Failure
```

**实现要点**：每次子节点返回 `Success` 或 `Failure` 后，Repeater 重置子节点状态然后重新 tick。`Repeater(count=N)` 记录已成功完成的次数。

**经典场景**：

```
Repeater(forever)
└── Sequence
    ├── Action: MoveTo(randomPatrolPoint)
    ├── Action: Wait(3.0)
    └── Action: LookAround()
```

NPC 永远在"移动到随机点 → 等待 3 秒 → 四处张望"的循环中。`Repeater(forever)` 确保 Sequence 完成后立即重新开始。注意 `Repeater(forever)` 自身永远不会返回 `Success`——它永远返回 `Running`，因此它的父节点（如 Selector）中的后续兄弟子节点永远不会被执行。这正是设计意图：巡逻逻辑作为一个整体，始终活跃。

#### Succeeder / Failer（强制成功/失败）

忽略子节点的返回值，强制返回 `Success`（Succeeder）或 `Failure`（Failer）。`Running` 仍然原样传递。

```
Succeeder.Tick():
  status = child.Tick()
  if status == Running: return Running
  return Success  // 吞掉 Success 和 Failure
```

**经典用法**：在 Selector 中，你希望某个子节点即使失败了也不影响后续子节点的尝试：

```
Selector
├── Sequence
│   ├── Action: TryStealthKill()    // 可能失败
│   └── Succeeder                   // 即使潜行失败也继续
│       └── Action: PlayGloatAnimation()  // 无论如何都播放嘲讽动画
└── Action: DirectAttack()
```

注意这里的微妙之处：`TryStealthKill()` 如果失败，Sequence 就失败了，Selector 会尝试 `DirectAttack()`。但如果我们省略 Succeeder 并把 `PlayGloatAnimation` 直接放在 Sequence 中，那么 `TryStealthKill` 成功后 Sequence 才会播放动画——这不是我们想要的效果。

#### Conditional（条件装饰器）

Conditional 是最常用的 Decorator 之一。它在 tick 子节点**之前**先检查一个条件——如果条件不满足，直接返回 `Failure`（不执行子节点）；如果条件满足，tick 子节点并传递其返回值。

```
Conditional.Tick():
  if !CheckCondition(): return Failure
  return child.Tick()
```

**与 Condition Leaf 的区别**：

| | Conditional Decorator | Condition Leaf |
|---|---|---|
| 位置 | 包裹另一个节点 | 作为独立的叶子节点 |
| 失败时行为 | 跳过被包裹的子节点 | 返回 Failure 给父节点 |
| 典型用法 | "在满足条件时才做 X" | 在 Selector 中作为条件分支 |

**经典场景**：

```
Selector
├── Conditional(HasAmmo?)
│   └── Action: Shoot()
└── Action: Reload()
```

如果 `HasAmmo?` 为真，执行 `Shoot()`；否则 Conditional 返回 Failure，Selector 转而执行 `Reload()`。

> **UE 对应**：在 UE 中，这是 `BTDecorator_BlackboardBase` 的标准用法——Decorator 检查 Blackboard 键值，决定是否允许其父节点（通常是 Task）执行。

#### Cooldown（冷却装饰器）

限制子节点的执行频率：子节点成功完成后，在 `cooldownTime` 秒内再次访问时直接返回 `Failure`。

```
Cooldown.Tick():
  if (Time.now - lastSuccessTime < cooldownTime):
    return Failure
  status = child.Tick()
  if status == Success:
    lastSuccessTime = Time.now
  return status
```

**经典场景**：限制 Boss 的特殊技能使用频率：

```
Selector
├── Cooldown(5.0s)
│   └── Action: FireBreath()
└── Action: MeleeAttack()
```

`FireBreath` 执行后 5 秒内，Cooldown 阻止再次执行，Selector 自动 fallthrough 到 `MeleeAttack`。

#### TimeLimit（时间限制装饰器）

限制子节点的总执行时间。超过 `timeLimit` 秒后，强制终止子节点并返回 `Failure`。

```
TimeLimit.Tick():
  if (elapsedTime >= timeLimit):
    child.OnAbort()
    return Failure
  return child.Tick()
```

**经典场景**：NPC 追逐玩家最多 10 秒，超时后放弃：

```
TimeLimit(10.0s)
└── Action: ChasePlayer()
```

如果 10 秒内追到（ChasePlayer 返回 Success），TimeLimit 向上传递 Success。如果超时，TimeLimit 终止追逐并返回 Failure。

#### Loop（循环装饰器）

与 Repeater 类似，但允许在每次循环前检查一个退出条件。Loop 在每次子节点完成（Success 或 Failure）后检查条件——如果条件仍为真，重置并重新执行；如果条件为假，返回子节点的最终状态。

```
Loop(condition):
  while condition():
    status = child.Tick()
    if status == Running: return Running
    // status is Success or Failure → reset and check condition again
  return lastStatus
```

#### ForceSuccess（强制执行成功）

等价于 Succeeder，但名称更直观地表达了意图。在某些 BT 框架中 ForceSuccess 是一个独立节点类型。

#### Gate（门控装饰器）

Gate 是一个状态性的条件检查器：一旦门"打开"（条件首次满足），它就保持打开状态，允许子节点反复执行。门只有在被外部信号"关闭"后才重新检查条件。这在某些需要"锁定"状态的场景中很有用。

```
Gate.Tick():
  if isOpen:
    return child.Tick()
  if CheckCondition():
    isOpen = true
    return child.Tick()
  return Failure
```

**经典场景**：NPC 检测到玩家后进入"警觉状态"——即使玩家短暂脱离视野，NPC 仍保持警觉并搜索最后已知位置：

```
Gate(PlayerDetected?)
└── Sequence
    ├── Action: MoveTo(lastKnownPosition)
    └── Action: SearchArea()
```

`PlayerDetected?` 一旦为真，Gate 打开，NPC 开始搜索。即使玩家跑出视野（条件变假），Gate 保持打开，NPC 继续搜索行为。当搜索完成（SearchArea 返回 Success），整个序列成功，Gate 被父节点重置。

---

### Leaf Nodes（叶子节点）

叶子节点是树的末端，没有子节点。它们分为两类：**Action（动作节点）**和 **Condition（条件节点）**。

#### Action（动作节点）

Action 执行实际的游戏逻辑——移动、攻击、播放动画、修改 Blackboard 等。Action 是所有实际"工作"发生的地方。

```
Action 的 Tick 伪代码:
  OnStart()             // 首次进入时调用一次
  while (not done):
    OnUpdate(dt)         // 每帧调用
    if (done): break
  OnEnd()                // 完成时调用一次
  return finalStatus
```

关键在于 Action 可以跨越多帧。一个 `MoveTo(target)` Action 可能在 200 帧里持续返回 `Running`，每帧更新位置。这给了行为树"时间跨度"——不需要在 Action 内部维护复杂的状态机。

**Action 的设计原则**：

1. **单一职责**：一个 Action 只做一件事。`MoveAndShoot` 应该拆成 Parallel(`MoveTo`, `Shoot`) 或 Sequence(`MoveTo`, `Shoot`)。
2. **可重入**：Action 应该能安全地从任何父节点被重新启动（因为父节点可能中止它）。
3. **无副作用的条件检查**：Action 执行前已经有 Condition/Conditional 检查前提条件。不要在 Action 内部再次检查"能不能做"——把条件检查留给上层节点。

#### Condition（条件节点）

Condition 是对游戏世界状态的**纯查询**——没有副作用，不修改任何状态。它只在被 tick 时返回 `Success`（条件满足）或 `Failure`（条件不满足）。

```
Condition.Tick():
  return CheckCondition() ? Success : Failure
```

**Condition 绝不返回 `Running`**。它是瞬时的、原子的查询。常见例子：

- `HasTarget?` — 是否有当前目标？
- `IsHealthBelow(30)?` — 血量是否低于 30？
- `CanSeePlayer?` — 视线是否可达？
- `IsCooldownReady("Fireball")?` — 技能冷却是否就绪？
- `IsDoorOpen?` — 门是否开着？

**何时用 Condition Leaf vs Conditional Decorator**：

- **Condition Leaf**：在 Selector 中作为分支条件。`Condition: HasTarget? → 子行为` 是一个完整的分支。
- **Conditional Decorator**：包裹在某个 Action 外面，作为"护卫"。"只有在这个条件下才执行这个 Action"。

实际上，Conditional Decorator 等价于 `Sequence(Condition, Action)` 的语法糖。选择哪个取决于你的树的可读性偏好。

---

### Service Nodes（服务节点 — UE 特有概念）

Service 是 Unreal Engine 行为树系统引入的独特概念，在其他 BT 框架中较少见。Service 本身不是控制流的一部分——它**不返回值**，也不影响树的结构。

**Service 的本质**：附着在 Composite 节点上的后台任务，以可配置的频率（默认每 tick）执行，通常用于更新 Blackboard 数据。

```
Service 伪代码:
  OnSearchStart()  // 首次进入所在的 Composite 子树时
  while (parentComposite is active):
    OnTick(dt)     // 按 interval 频率调用
```

**经典场景**：一个 `UpdateTargetService` 每 0.5 秒运行一次，计算最近的敌人并写入 Blackboard：

```
Selector  ← Service: UpdateTargetService (interval=0.5s)
├── Sequence
│   ├── Condition: HasTarget?         ← 读取 Blackboard Target 键
│   └── Action: Attack()
└── Action: Patrol()
```

`UpdateTargetService` 每 0.5 秒扫描周围敌人，将最近的敌人写入 Blackboard 的 `Target` 键。`HasTarget?` Condition 读取该键。这样，决策层（行为树结构）和数据层（Blackboard 更新）被清晰分离。

**为什么需要 Service**？如果不用 Service，`HasTarget?` 的检查逻辑必须在 `Condition: HasTarget?` 内部每帧执行感知查询——这意味着每次 tree tick 到该节点时都做一次查询。Service 将它移出关键路径，以独立的频率和生命周期运行。

> Service 是引擎级优化 + 架构模式。如果你从零实现自己的 BT 系统，可以省略 Service，将数据更新逻辑放在 Condition 内部或行为树外部的感知系统中。但理解 Service 的设计意图有助于你设计清晰的 AI 数据流。

---

### Node Memory / Statefulness（节点状态记忆）

行为树的一个核心概念是：**部分节点在多次 tick 之间需要"记住"内部状态**。这种有状态的节点称为 **stateful node**。

#### 哪些节点需要 memory？

| 节点类型 | 需要 memory | 记住什么 |
|---|---|---|
| Selector | 是 | `currentChildIndex`——当前正在执行第几个子节点 |
| Sequence | 是 | `currentChildIndex` |
| Repeater | 是 | `executionCount`——已完成的次数 |
| Cooldown | 是 | `lastSuccessTime` |
| TimeLimit | 是 | `elapsedTime` |
| Action (多帧) | 是 | 内部执行进度 |
| Inverter | 否 | 无状态，简单转发 |
| Condition | 否 | 无状态，瞬时查询 |
| Succeeder/Failer | 否 | 无状态 |

#### 何时重置 memory？

当一个有状态节点从 `Running` 变为 `Success` 或 `Failure` 时（即完成执行），**它的 memory 被重置**。下一次从根节点重新 tick 这棵树时，该节点从初始状态开始。

但如果父节点**中止**了一个正在运行的子节点（例如 Active Selector 切到更高优先级的子节点），被中止节点的 memory 是否重置取决于实现策略。UE 的传统做法是：**被 Abort 的节点在下一次被重新执行时，从初始状态开始**（memory 被清空）。

#### Memory 与 Behavior Tree Instance 的关系

在 UE 中，每个运行行为树的 Actor 有一个 `UBehaviorTreeComponent`，它持有整棵树的运行时状态（包括所有节点的 memory）。这意味着同一棵行为树资产（`UBehaviorTree`）可以被多个 Actor 同时使用，每个 Actor 的运行时状态是独立的。

---

### Preconditions 与 Runtime Conditions

区分两种条件检查位置至关重要：

| | Precondition（前置条件） | Runtime Condition（运行时条件） |
|---|---|---|
| 检查时机 | 进入子树/节点**之前** | 执行过程中**持续**检查 |
| 失败后果 | 不进入该分支 | 中止当前执行，向上返回 Failure |
| 实现方式 | Conditional Decorator / Condition Leaf | Conditional Decorator with Observer Abort / Active Selector |
| 典型场景 | "有弹药才能射击" | "弹药耗尽时立即停止射击" |

**核心区别示例**：

```
Sequence
├── Conditional: HasAmmo?           ← Precondition
│   └── Action: FireWeapon()        ← 射击是一个持续动作
```

这里 `HasAmmo?` 只在进入 `FireWeapon` 前检查一次。如果 `FireWeapon` 需要 30 帧，而弹药在第 10 帧耗尽，这个树不会自动中止——`HasAmmo?` 已经通过了。

要处理"弹药耗尽时立即停止"，需要 Observer Abort（UE 概念）或 Active Selector：

```
ActiveSelector
├── Conditional(HasAmmo?, observeOnValueChange=true)
│   └── Action: FireWeapon()
└── Action: Reload()
```

当 `HasAmmo?` 从 true 变为 false 时，`FireWeapon` 被立即中止，`Reload` 被激活。

> 这是行为树设计中最容易被忽视的细节之一。99% 的"AI 反应太慢" bug 的根因是：代码只检查了 Precondition，但没有设置 Runtime Condition 的 Observer。

---

## 2. 代码示例

### 示例 A: 完整节点类型实现（C# 伪代码）

以下代码实现了一个完整的 BT 节点类型系统。注释标注了每种节点的关键逻辑。

```csharp
// ============================================================
// BT Node Type System — Complete Implementation (C#)
// Four categories: Composite, Decorator, Leaf, Service
// ============================================================

using System;
using System.Collections.Generic;

// --- 1. Shared Enums & Base Class ---

public enum BTStatus { Success, Failure, Running }

public abstract class BTNode
{
    protected List<BTNode> children = new List<BTNode>();
    public BTNode Parent { get; set; }

    // Node memory: reset when execution completes or parent composites restart
    public virtual void Reset() { }

    // Main entry: called every tick
    public abstract BTStatus Tick(float deltaTime);

    // Lifecycle: called when parent aborts this node mid-execution
    public virtual void OnAbort() { Reset(); }

    // --- Builder helpers ---
    public BTNode AddChild(BTNode child)
    {
        children.Add(child);
        child.Parent = this;
        return this;
    }
}

// ============================================================
// COMPOSITE NODES
// ============================================================

// --- Selector (Priority / Fallback) ---
public class Selector : BTNode
{
    private int currentIndex = 0;

    public override BTStatus Tick(float dt)
    {
        while (currentIndex < children.Count)
        {
            BTStatus status = children[currentIndex].Tick(dt);
            switch (status)
            {
                case BTStatus.Running:
                    return BTStatus.Running;  // stay on this child next tick
                case BTStatus.Success:
                    Reset();                   // done → reset for next time
                    return BTStatus.Success;
                case BTStatus.Failure:
                    currentIndex++;            // try next child
                    break;
            }
        }
        Reset();
        return BTStatus.Failure;  // all children failed
    }

    public override void Reset() { currentIndex = 0; }
}

// --- Sequence ---
public class Sequence : BTNode
{
    private int currentIndex = 0;

    public override BTStatus Tick(float dt)
    {
        while (currentIndex < children.Count)
        {
            BTStatus status = children[currentIndex].Tick(dt);
            switch (status)
            {
                case BTStatus.Running:
                    return BTStatus.Running;
                case BTStatus.Failure:
                    Reset();
                    return BTStatus.Failure;  // one fails → all fail
                case BTStatus.Success:
                    currentIndex++;            // advance to next step
                    break;
            }
        }
        Reset();
        return BTStatus.Success;  // all steps completed
    }

    public override void Reset() { currentIndex = 0; }
}

// --- Parallel ---
public enum ParallelPolicy { SucceedOnOne, SucceedOnAll, FailOnOne }

public class Parallel : BTNode
{
    private readonly ParallelPolicy policy;
    private readonly HashSet<BTNode> runningChildren = new HashSet<BTNode>();

    public Parallel(ParallelPolicy policy) { this.policy = policy; }

    public override BTStatus Tick(float dt)
    {
        int successCount = 0;
        int failureCount = 0;

        // If no children are currently running, start all of them
        if (runningChildren.Count == 0)
        {
            foreach (var child in children)
                runningChildren.Add(child);
        }

        foreach (var child in children)
        {
            if (!runningChildren.Contains(child)) continue;
            BTStatus status = child.Tick(dt);
            switch (status)
            {
                case BTStatus.Success:
                    runningChildren.Remove(child);
                    successCount++;
                    break;
                case BTStatus.Failure:
                    runningChildren.Remove(child);
                    failureCount++;
                    break;
                // BTStatus.Running: keep in set
            }
        }

        // Evaluate policy
        switch (policy)
        {
            case ParallelPolicy.SucceedOnOne:
                if (successCount >= 1) { AbortAll(); return BTStatus.Success; }
                if (runningChildren.Count == 0) return BTStatus.Failure;
                break;
            case ParallelPolicy.SucceedOnAll:
                if (failureCount >= 1) { AbortAll(); return BTStatus.Failure; }
                if (successCount == children.Count) return BTStatus.Success;
                break;
            case ParallelPolicy.FailOnOne:
                if (failureCount >= 1) { AbortAll(); return BTStatus.Failure; }
                if (runningChildren.Count == 0) return BTStatus.Success;
                break;
        }

        return BTStatus.Running;
    }

    private void AbortAll()
    {
        foreach (var child in runningChildren) child.OnAbort();
        runningChildren.Clear();
    }

    public override void Reset() { runningChildren.Clear(); }
}

// --- Random Selector ---
public class RandomSelector : BTNode
{
    private Selector innerSelector;
    private bool shuffled = false;

    public override BTStatus Tick(float dt)
    {
        if (!shuffled)
        {
            // Fisher-Yates shuffle
            var rng = new Random();
            for (int i = children.Count - 1; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                (children[i], children[j]) = (children[j], children[i]);
            }
            shuffled = true;
            innerSelector = new Selector();
            foreach (var child in children)
                innerSelector.AddChild(child);
        }
        return innerSelector.Tick(dt);
    }

    public override void Reset() { shuffled = false; innerSelector?.Reset(); }
}

// --- Active Selector (re-evaluates from left every tick) ---
public class ActiveSelector : BTNode
{
    private BTNode currentRunning = null;

    public override BTStatus Tick(float dt)
    {
        for (int i = 0; i < children.Count; i++)
        {
            // Skip previously-running child? No — re-evaluate from the top.
            // If this child is already running and still the highest priority,
            // it just continues.
            BTStatus status = children[i].Tick(dt);

            if (status == BTStatus.Failure)
            {
                if (children[i] == currentRunning)
                    currentRunning = null; // stopped being running
                continue;
            }

            // Status is Success or Running
            if (children[i] != currentRunning)
            {
                // Higher-priority node activated → abort old one
                currentRunning?.OnAbort();
                currentRunning = children[i];
            }

            if (status == BTStatus.Success)
            {
                currentRunning = null;
                return BTStatus.Success;
            }
            return BTStatus.Running;
        }

        currentRunning = null;
        return BTStatus.Failure;
    }

    public override void Reset() { currentRunning = null; }
}

// ============================================================
// DECORATOR NODES
// ============================================================

// --- Inverter ---
public class Inverter : BTNode
{
    public override BTStatus Tick(float dt)
    {
        BTStatus status = children[0].Tick(dt);
        if (status == BTStatus.Success) return BTStatus.Failure;
        if (status == BTStatus.Failure) return BTStatus.Success;
        return BTStatus.Running;
    }
}

// --- Repeater ---
public class Repeater : BTNode
{
    private readonly int? maxCount;      // null = forever
    private readonly bool untilFailure;  // if true, stop on first child Failure
    private int executionCount = 0;

    public Repeater(int? maxCount = null, bool untilFailure = false)
    {
        this.maxCount = maxCount;
        this.untilFailure = untilFailure;
    }

    public override BTStatus Tick(float dt)
    {
        while (true)
        {
            BTStatus status = children[0].Tick(dt);

            if (untilFailure && status == BTStatus.Failure)
            {
                Reset();
                return BTStatus.Failure;
            }

            if (status == BTStatus.Running)
                return BTStatus.Running;

            // Child completed (Success or Failure for non-untilFailure)
            executionCount++;

            if (maxCount.HasValue && executionCount >= maxCount.Value)
            {
                Reset();
                return BTStatus.Success;
            }

            children[0].Reset(); // restart child for next iteration
            // Loop back to tick the child again in the same frame
            // (or wait till next frame — implementation choice)
        }
    }

    public override void Reset() { executionCount = 0; }
}

// --- Succeeder ---
public class Succeeder : BTNode
{
    public override BTStatus Tick(float dt)
    {
        BTStatus status = children[0].Tick(dt);
        if (status == BTStatus.Running) return BTStatus.Running;
        return BTStatus.Success; // swallow both Success and Failure
    }
}

// --- Failer ---
public class Failer : BTNode
{
    public override BTStatus Tick(float dt)
    {
        BTStatus status = children[0].Tick(dt);
        if (status == BTStatus.Running) return BTStatus.Running;
        return BTStatus.Failure;
    }
}

// --- Conditional Decorator ---
public class Conditional : BTNode
{
    private readonly Func<bool> condition;

    public Conditional(Func<bool> condition) { this.condition = condition; }

    public override BTStatus Tick(float dt)
    {
        if (!condition()) return BTStatus.Failure;
        return children[0].Tick(dt);
    }
}

// --- Cooldown ---
public class Cooldown : BTNode
{
    private readonly float cooldownTime;
    private float lastSuccessTime = float.MinValue;

    public Cooldown(float cooldownTime) { this.cooldownTime = cooldownTime; }

    public override BTStatus Tick(float dt)
    {
        if (Time.time - lastSuccessTime < cooldownTime)
            return BTStatus.Failure;

        BTStatus status = children[0].Tick(dt);
        if (status == BTStatus.Success)
            lastSuccessTime = Time.time;
        return status;
    }

    public override void Reset() { lastSuccessTime = float.MinValue; }
}

// --- TimeLimit ---
public class TimeLimit : BTNode
{
    private readonly float timeLimit;
    private float elapsed = 0f;

    public TimeLimit(float timeLimit) { this.timeLimit = timeLimit; }

    public override BTStatus Tick(float dt)
    {
        elapsed += dt;
        if (elapsed >= timeLimit)
        {
            children[0].OnAbort();
            return BTStatus.Failure;
        }
        return children[0].Tick(dt);
    }

    public override void Reset() { elapsed = 0f; }
}

// --- Loop ---
public class Loop : BTNode
{
    private readonly Func<bool> condition;

    public Loop(Func<bool> condition) { this.condition = condition; }

    public override BTStatus Tick(float dt)
    {
        while (condition())
        {
            BTStatus status = children[0].Tick(dt);
            if (status == BTStatus.Running) return BTStatus.Running;
            children[0].Reset();
        }
        return BTStatus.Success;
    }
}

// --- ForceSuccess (alias for Succeeder, semantically clearer) ---
public class ForceSuccess : Succeeder { }

// ============================================================
// LEAF NODES
// ============================================================

// --- Action Base ---
public abstract class ActionNode : BTNode
{
    private bool started = false;

    public override BTStatus Tick(float dt)
    {
        if (!started)
        {
            OnStart();
            started = true;
        }

        BTStatus status = OnUpdate(dt);

        if (status != BTStatus.Running)
        {
            OnEnd(status);
            started = false;
        }

        return status;
    }

    protected virtual void OnStart() { }
    protected abstract BTStatus OnUpdate(float dt);
    protected virtual void OnEnd(BTStatus finalStatus) { }

    public override void Reset() { started = false; }
}

// Concrete action examples
public class MoveTo : ActionNode
{
    private Vector3 target;
    private float speed;
    public MoveTo(Vector3 target, float speed) { this.target = target; this.speed = speed; }

    protected override BTStatus OnUpdate(float dt)
    {
        Vector3 toTarget = target - Owner.Position;
        if (toTarget.magnitude < 0.1f)
            return BTStatus.Success;
        Owner.Position += toTarget.normalized * speed * dt;
        return BTStatus.Running;
    }
}

public class Attack : ActionNode
{
    private float duration = 0.6f;
    private float elapsed = 0f;

    protected override BTStatus OnUpdate(float dt)
    {
        elapsed += dt;
        Owner.PlayAnimation("Attack");
        if (elapsed >= duration)
        {
            Owner.DealDamage(Target, 25);
            return BTStatus.Success;
        }
        return BTStatus.Running;
    }

    protected override void OnEnd(BTStatus finalStatus) { elapsed = 0f; }
}

// --- Condition Base ---
public abstract class ConditionNode : BTNode
{
    public override BTStatus Tick(float dt)
    {
        return Check() ? BTStatus.Success : BTStatus.Failure;
    }

    protected abstract bool Check();
    // Condition NEVER returns Running
}

// Concrete condition examples
public class HasTarget : ConditionNode
{
    protected override bool Check() => Owner.CurrentTarget != null;
}

public class IsHealthBelow : ConditionNode
{
    private float threshold;
    public IsHealthBelow(float threshold) { this.threshold = threshold; }
    protected override bool Check() => Owner.Health < threshold;
}

public class IsInRange : ConditionNode
{
    private float range;
    public IsInRange(float range) { this.range = range; }
    protected override bool Check() =>
        Vector3.Distance(Owner.Position, Target.Position) <= range;
}

// ============================================================
// SERVICE NODE (UE-inspired — background ticker)
// ============================================================
public abstract class ServiceNode
{
    private float interval;
    private float timeSinceLastTick;
    private bool active = false;

    public ServiceNode(float interval = 0.5f) { this.interval = interval; }

    public void OnEnter()
    {
        active = true;
        timeSinceLastTick = 0f;
        OnActivation();
    }

    public void OnExit()
    {
        active = false;
        OnDeactivation();
    }

    public void Tick(float dt)
    {
        if (!active) return;
        timeSinceLastTick += dt;
        if (timeSinceLastTick >= interval)
        {
            timeSinceLastTick = 0f;
            OnTick();
        }
    }

    protected virtual void OnActivation() { }
    protected virtual void OnDeactivation() { }
    protected abstract void OnTick(); // user overrides this
}

// Example: updates Blackboard Target every 0.5s
public class UpdateTargetService : ServiceNode
{
    private Blackboard bb;
    public UpdateTargetService(Blackboard bb) : base(0.5f) { this.bb = bb; }

    protected override void OnTick()
    {
        Enemy nearest = PerceptionSystem.FindNearestEnemy(Owner.Position);
        bb.Set("Target", nearest);
    }
}
```

### 示例 B: 复杂行为树 Tick 追踪

假设我们有以下 NPC 行为树：

```
Repeater(forever)                                          ← Root
└── Selector                                               ← S1
    ├── Sequence                                           ← Seq1
    │   ├── Condition: HealthBelow30?
    │   ├── Action: Flee(duration=2s)
    │   └── Action: Heal()
    ├── Sequence                                           ← Seq2
    │   ├── Conditional: HasTarget?
    │   │   └── Inverter → Condition: IsTargetDead?
    │   │       └── Action: Attack()
    │   └── Conditional: CanSeePlayer?
    │       └── Cooldown(2.0s)
    │           └── Action: Shoot()
    └── Action: Patrol()
```

追踪以下 10 帧的执行过程。假设 NPC 初始状态：血量 = 80，无目标，在巡逻。

| Tick | 访问节点 | 返回值 | 效果 / 说明 |
|---|---|---|---|
| 1 | Root→S1→Seq1→HealthBelow30? | Failure | 血量 80 > 30，条件不满足 |
| 1 | S1→Seq2→Conditional(HasTarget?) | Failure | 无目标，跳过整个 Seq2 |
| 1 | S1→Patrol | Running | 进入巡逻，开始移动到第一个路径点 |
| 2 | Root→S1→Seq1→HealthBelow30? | Failure | 血量仍 80，不变 |
| 2 | S1→Seq2→Conditional(HasTarget?) | Failure | 仍无目标 |
| 2 | S1→Patrol | Running | 继续巡逻移动中（第 2 帧） |
| 3 | Root→S1→Seq1→HealthBelow30? | Failure | 血量仍 80 |
| 3 | S1→Seq2→Conditional(HasTarget?) | Success | 玩家进入感知范围，HasTarget 为真 |
| 3 | S1→Seq2→Inverter(IsTargetDead?)→Attack | Success→Failure→Invert→Success? | 目标未死，Inverter 不触发（此处 Inverter 包裹的是"目标已死"条件——如果不死则条件返回 Failure，Inverter 转为 Success，Attack 可执行）。**等一下，此处树的结构有问题——让我修正** |

> **修正树结构**。上面树中的 Inverter 位置不清晰。更正后的 Seq2 应该是：
>
> ```
> Sequence                                 ← Seq2
> ├── Condition: HasTarget?                ← 有目标？
> ├── Sequence                             ← Seq2b: 战斗子序列
> │   ├── Inverter                         ← 目标**未**死
> │   │   └── Condition: IsTargetDead?
> │   └── Action: Attack()                 ← 执行近战攻击
> ├── Condition: CanSeePlayer?             ← 能看到玩家？
> └── Cooldown(2.0s)
>     └── Action: Shoot()                  ← 射击
> ```

重新追踪（使用修正后的树）：

| Tick | 访问节点 | 返回值 | 效果 |
|---|---|---|---|
| 1 | Root→S1→Seq1→HealthBelow30? | Failure | HP 80 > 30 |
| 1 | S1→Seq2→HasTarget? | Failure | 无目标，Seq2 整体失败 |
| 1 | S1→Patrol | Running | 巡逻中 |
| 2 | Root→S1→Seq1→HealthBelow30? | Failure | — |
| 2 | S1→Seq2→HasTarget? | Success | 感知到玩家，HasTarget 为真 |
| 2 | Seq2→Seq2b→Inverter(IsTargetDead?) | Inverter 执行：Condition 返回 Failure（目标未死）→ Inverter 转 Success |
| 2 | Seq2→Seq2b→Attack | Running | 开始近战攻击动画（需 0.6s） |
| 3 | Root→S1→Seq1→HealthBelow30? | Failure | 仍 > 30 |
| 3 | S1→Seq2→HasTarget? | Success | 仍有目标 |
| 3 | Seq2→Seq2b→Inverter(IsTargetDead?) | 同 Tick 2 |
| 3 | Seq2→Seq2b→Attack | Running | 攻击进行中（第 2 帧） |
| 4 | Root→S1→Seq1→HealthBelow30? | Failure | — |
| 4 | S1→Seq2→…→Attack | Running | 攻击第 3 帧 |
| 5 | …→Attack | **Success** | 攻击完成！Seq2b 全部成功 |
| 5 | Seq2→CanSeePlayer? | Success | 目标仍在视野内 |
| 5 | Seq2→Cooldown→Shoot | Cooldown 刚重置→执行 Shoot | 射击开始 |
| 6 | Root→S1→Seq1→HealthBelow30? | Failure | — |
| 6 | S1→Seq2→HasTarget? | Success | — |
| 6 | Seq2→Seq2b→Attack | Running | 再次攻击（Seq2b 重新执行） |
| 7-9 | …→Attack | Running→Success | 攻击完成 |
| 9 | Seq2→CanSeePlayer? | Success | 仍可见 |
| 9 | Seq2→Cooldown→Shoot | **Failure** | Cooldown 未就绪（上次射击在 Tick 5，2s 未到） |
| 9 | Seq2→S1 无更多子节点 | **Failure** | Shoot 失败导致 Seq2 失败，S1 无更多子节点 → S1 失败 |
| 9 | Root→Repeater | Repeater 收到 Failure → 重置所有节点，重新开始 | — |
| 10 | Root→S1→Seq1→HealthBelow30? | Failure | — |
| 10 | S1→Seq2→HasTarget? | Success | — |
| 10 | Seq2→Seq2b→Attack | Running | 再次攻击 |

**关键观察**：

1. **Tick 1-2**：标准 Selector 在 Patrol 返回 Running 后，每帧仍需重新 tick HealthBelow30? 和 HasTarget?。这是标准 Selector 的行为——虽然它不会"跳过"Running 节点的重新评估，但**当它到达 Running 的子节点时，前面的条件节点仍然被每帧 tick（返回成功/失败是瞬时操作）**。只有遇到第一个返回 Success 或 Running 的非条件子节点时，才停止遍历。
2. **Tick 5**：Attack 完成后 Seq2b 全部成功，树立即前进到 CanSeePlayer? 和 Shoot。
3. **Tick 9**：Cooldown 导致 Shoot 失败，Seq2 整体失败，S1 无更多子节点也失败。Repeater(forever) 收到 Failure 后重置整棵树并重新开始下一帧。

---

## 3. 练习

### 练习 1：设计 NPC 行为树并追踪执行

设计一个行为树，使用 **Selector**、**Sequence**、**Repeater** 和 **Inverter** 四种节点，实现以下 NPC 行为：

1. **巡逻**（默认行为）：沿预设路径点循环移动。
2. **调查声音**：当听到枪声时，移动到声音来源位置并停留观察 2 秒。
3. **追击玩家**：当看到玩家时，取消巡逻/调查，开始追击。
4. **近战攻击**：追击到近战范围后攻击。
5. **返回巡逻**：当玩家脱离视野超过 5 秒后，回到巡逻路径。

要求：
- 画出完整的树结构。
- 写一个 5 tick 的追踪表格，假设以下事件序列：Tick 1 正常巡逻 → Tick 2 听到枪声 → Tick 3 看到玩家 → Tick 4 追击中 → Tick 5 到达近战范围。
- 标注每个 tick 中哪些节点被评估、返回了什么值。

### 练习 2：添加 Cooldown 装饰器

在练习 1 的基础上，为近战攻击添加 Cooldown 装饰器：NPC 攻击一次后 2 秒内不能再次攻击。

要求：
- 修改树结构，标注 Cooldown 在哪里。
- 分析：如果 NPC 攻击后 1 秒，玩家仍然在近战范围内，行为树会执行什么？攻击 Action 是否被 tick？Cooldown 返回什么？

### 练习 3（可选）：实现 Parallel 移动+扫描

设计一个 Parallel 子树，让 NPC 在追击玩家时**同时**执行以下两个行为：

1. 导航移动到玩家位置。
2. 每 0.3 秒扫描周围是否有更近的敌人（如果有，切换目标）。

要求：
- 使用 Parallel 的哪种策略？为什么？
- 当扫描到新目标时，如何处理正在执行的 MoveTo？

---

## 4. 扩展阅读

- **Unreal Engine 官方 — Behavior Tree 文档**：UE 原生行为树的完整参考，包括节点类型、Blackboard、Decorator Observer Aborts 的详细说明。
  - [Behavior Tree Overview](https://docs.unrealengine.com/5.3/en-US/behavior-trees-in-unreal-engine/)
  - [Behavior Tree Node Reference](https://docs.unrealengine.com/5.3/en-US/behavior-tree-node-reference-in-unreal-engine/)
- **Opsive Behavior Designer**（Unity 最流行的 BT 插件）：
  - [Behavior Designer Documentation](https://opsive.com/support/documentation/behavior-designer/)
  - 特别推荐其 Node 参考页面，每种节点都有清晰的流程图和使用示例。
- **Chris Simpson — "Behavior trees for AI: How they work" (Gamasutra/Game Developer, 2014)**：行为树概念的经典入门文章，解释了节点类型和 tick 机制。
- **Damian Isla — "Managing Complexity in the Halo 2 AI" (GDC 2005)**：虽以 HSM 为中心，但阐述了行为树思想的前身——Halo 2 的行为优先级系统。理解这个演进过程有助于深入理解为什么行为树是这样设计的。
- **Alex J. Champandard — "Behavior Trees for Next-Gen Game AI" (AiGameDev.com 系列, 2007-2012)**：行为树理论的重要早期推动者。系列文章深入讨论了形式化语义、节点设计模式、与规划器的对比。
- **Colledanchise & Ögren — *Behavior Trees in Robotics and AI: An Introduction* (CRC Press, 2018)**：学术级别的行为树专著，包含严格的数学形式化定义和收敛性证明。适合想要理解 BT 理论基础的读者。

---

## 常见陷阱

### 1. Selector 的 Fallthrough Bug（缺少兜底行为）

**症状**：Selector 的所有子节点在某种状态下都返回 `Failure`，Selector 自身也返回 `Failure`，导致树的根节点收到 `Failure` 而"空转"——NPC 站在原地什么都不做。

**根因**：Selector 的最后一个子节点不应该是"有可能失败"的行为。它应该是**兜底行为**——一个几乎永远不会失败的默认 Action（如 `Idle` 或 `Patrol`）。

**解法**：

```
Selector
├── Sequence(HasTarget? → Attack)   // 有目标时攻击
├── Sequence(HeardSound? → Investigate) // 有声音时调查
└── Action: Idle()                  // 兜底：什么都不做
```

确保最后一个子节点（兜底行为）在正常条件下始终返回 `Running`。

### 2. Parallel 节点的竞态条件（Race Condition）

**症状**：Parallel 中的多个 Action 同时修改同一个共享状态（如 Blackboard 键、Transform），导致不可预测的行为。例如 `MoveTo(PointA)` 和 `MoveTo(PointB)` 在一个 Parallel 中同时运行，NPC 在两个目标之间抖动。

**根因**：Parallel 节点在**同一帧**内以未定义的顺序 tick 子节点。如果两个子节点都写入同一个 Blackboard 键，最后一个写入的值会"获胜"，但谁先谁后是不确定的。

**解法**：

1. **区分主任务和后台任务**：给 Parallel 添加"主任务"概念。只有主任务决定返回值，后台任务只读取数据但不冲突。
2. **Blackboard 分区**：为不同子任务分配不同的 Blackboard 键。如 `Movement.Target` 和 `Scanning.Target`。
3. **避免在同一 Parallel 中运行冲突的 Action**：如果两个 Action 都会修改 Transform，它们不应该放在同一个 Parallel 中。

### 3. Decorator 求值顺序混淆

**症状**：一个节点外面包了多个 Decorator（如 `Cooldown(Inverter(Conditional(HasAmmo?, Shoot)))`），你预期 Cooldown 最先检查，但实际执行顺序与你预期不同。

**根因**：Decorator 从最外层到最内层依次 tick。外层 Decorator 的 `Tick()` 调用内层 Decorator 的 `Tick()`，依此类推。执行顺序 = 从外到里。

```
Cooldown                     ← 1st: check cooldown
  └── Conditional            ← 2nd: check condition
      └── Shoot              ← 3rd: execute if both pass
```

**正确做法**：明确你的 Decorator 顺序意图。如果你想让"条件"在"冷却"之前检查（即：如果没子弹就直接失败，不用等冷却），把 Conditional 放在外层：

```
Conditional(HasAmmo?)        ← 1st: check ammo (fast fail)
  └── Cooldown(2s)           ← 2nd: check cooldown
      └── Shoot              ← 3rd: shoot
```

### 4. Repeater(forever) 导致的无限循环

**症状**：使用 `Repeater(forever)` 后，整个行为树永远在同一个子树上循环，更高优先级的 Selector 分支永远不会被重新评估。

**根因**：`Repeater(forever)` 永远返回 `Running`。它作为 Selector 的子节点时，会阻塞 Selector 后续所有兄弟节点，以及每帧重新评估 Selector 前面节点的机会（除非使用 Active Selector）。

**解法**：

1. **将 Repeater 作为树的根节点**（如示例 B 中的结构），确保它包裹整个行为逻辑。
2. **用 Active Selector 替代标准 Selector**，这样即使 Repeater 返回 Running，高优先级条件仍被重新评估。
3. **限制 Repeater 的作用域**：不要让 Repeater 成为 Selector 的直接子节点；在 Selector 之上放 Repeater。

**正确 vs 错误**：

```
// ❌ 错误：Repeater 阻塞 Selector
Selector
├── Sequence(HasTarget? → Attack)
└── Repeater(forever)       ← 永远 Running，Attack 分支永远不会被重新评估
    └── Patrol              ← NPC 永远在巡逻，不会切换去攻击
```

```
// ✅ 正确：Repeater 在顶部包裹一切
Repeater(forever)
└── Selector
    ├── Sequence(HasTarget? → Attack)
    └── Patrol
```

### 5. Conditional Abort 与 Sequence 的交互死锁

**症状**：使用 Active Selector + Conditional Decorator（带 Observer Abort），NPC 在 Attack 和 Patrol 之间快速抖动——每帧都在切换行为。

**根因**：Conditional 的条件在边界值附近振荡。例如 `DistanceToPlayer < 3.0f` 作为 Condition——NPC 走到 2.99m 时触发 Attack；Attack 的第一步是"移动到最佳攻击距离 2.5m"——移动了 0.5m 后距离变成 3.01m，Condition 立即变为 false，Attack 被 Abort，NPC 回到 Patrol；Patrol 让 NPC 移动，距离再次 < 3.0m……循环往复。

**解法**：

1. **使用迟滞（Hysteresis）**：进入条件 `dist < 3.0f`，退出条件 `dist > 4.0f`。两者之间有 1m 的缓冲区。
2. **给 Condition 添加最小满足时间**：Condition 必须连续满足 N 帧才算真。
3. **避免在条件中使用连续变化的浮点值**：改用离散状态（"进入近战范围"是一个事件，而不是每帧检查距离阈值）。

---

> **下一步**: 完成本教程后，进入 Tutorial 08 [行为树在 Unity 中的实现 (C#)](08-bt-unity-csharp.md)，将本文中的伪代码转化为可运行的 Unity 行为树引擎，并在实际场景中测试 NPC AI。
