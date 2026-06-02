# Decorator、Service 与并行节点

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 11-blackboard-data-flow

---

## 1. 概念讲解

Tutorial 07 中对 Decorator 和 Parallel 节点做了初步介绍。本节将这两个概念深化到生产级别，并引入 UE 行为树中最重要的架构概念之一：**Service**。如果你在面试中被问到"UE 行为树的 Service 是什么？它和 Decorator 的区别是什么？Observer Abort 的三种模式分别解决什么问题？"——本节就是你要的答案。

### Decorator 深度剖析

回顾基础：Decorator 只有一个子节点，它不执行具体行为，而是**修改子节点的返回值、控制执行条件、限制执行频率或次数**。但生产级 Decorator 的能力远不止 Tutorial 07 中提到的几种。

#### 条件装饰器（Conditional Decorator）的三种形态

条件装饰器的本质是"当条件 C 为真时才允许执行子节点"。根据条件的来源和求值方式，分为三种形态：

**形态 1：Blackboard-based Conditional**——最常见的形式。Decorator 直接读取 Blackboard 中的某个键值，与期望值比较。UE 的 `BTDecorator_BlackboardBase` 及其子类（如 `BTDecorator_Blackboard`）就属于此类。优点是设计师可以在编辑器中自由配置检查哪个键；缺点是只能做简单的值比较。

```
BTDecorator_Blackboard:
  BlackboardKey: "TargetActor"
  KeyQuery: IsSet           // 只要键有值就通过
  ObserverAborts: LowerPriority  // 条件变真时抢断低优先级分支
```

**形态 2：Custom Bool Check**——你写一个 C++ 函数 `CalculateRawConditionValue()` 实现任意复杂逻辑。可以检查血量、距离、冷却时间、技能资源、甚至调用外部系统。灵活性最高，但设计师无法在编辑器中修改逻辑。

```cpp
bool UBTDecorator_HasClearShot::CalculateRawConditionValue(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
{
    // Perform a line trace from AI to target
    FHitResult Hit;
    FCollisionQueryParams Params;
    Params.AddIgnoredActor(OwnerComp.GetOwner());
    bool bHit = GetWorld()->LineTraceSingleByChannel(
        Hit, AILocation, TargetLocation, ECC_Visibility, Params);
    return !bHit; // No obstacle = clear shot
}
```

**形态 3：Event-Driven Conditional**——不做每帧轮询，而是订阅一个事件/委托，当事件触发时才重新评估条件。这是最高性能的形态，适合条件很少变化但变化时需要立即响应的场景（如"收到伤害事件"→ 触发 Abort）。

#### Observer Abort：行为树反应性的核心

这是面试中的高频考点，也是理解 UE Behavior Tree 与"自己写的简单 BT"差异的关键。

标准 Selector 的问题回顾（Tutorial 07 中已详述）：一旦 Selector 的某个子节点返回 `Running`，后续帧中它**不会重新评估前面的条件节点**。这意味着 NPC 在巡逻时即使玩家走到面前，也不会切换去攻击——因为 Patrol 在 Running，Selector 不再往前看。

**Observer Abort 解决了这个问题**，但它不是通过修改 Selector 的行为实现的，而是通过 Decorator 主动注册 Blackboard 键的观察者来实现的：

1. Decorator 在激活时调用 `OnBecomeRelevant()`，向 Blackboard 注册成为某个键的观察者。
2. 当该键的值发生变化时，Blackboard 通知 Decorator。
3. Decorator 立即重新计算 `CalculateRawConditionValue()`。
4. 根据配置的 `FlowAbortMode`，触发相应作用域的中止。

三种 `FlowAbortMode` 的精确语义：

| FlowAbortMode | 条件变为 false 时 | 条件变为 true 时 | 典型场景 |
|---|---|---|---|
| `None` | 不中止 | 不中止 | 轮询模式——只在进入分支时检查一次 |
| `Self` | **中止自身所在分支**，让父节点重新选择 | 不中止 | "弹药用完了 → 中止射击 → 去装弹" |
| `LowerPriority` | 不中止 | **中止父节点中优先级更低的分支**，强制父节点重新评估，使该分支获得执行机会 | "看到敌人 → 中止巡逻 → 去攻击" |
| `Both` | 同 Self | 同 LowerPriority | 双向反应：条件消失时退出，条件出现时抢断 |

**Self 的精确作用范围**：当 Decorator 的条件从 true 变为 false 时，它中止的是**该 Decorator 所在的 Composite 节点中，Decorator 自身及其右侧（更低优先级）的所有兄弟节点**。不包括左侧（更高优先级）的节点。这保证了更高优先级的行为不会被误伤。

**LowerPriority 的精确作用范围**：当 Decorator 的条件从 false 变为 true 时，它中止的是**父 Composite 中，Decorator 所在分支右侧（更低优先级）的所有正在运行的兄弟分支**。父 Composite 随后会重新从左到右评估——Decorator 所在分支（以及它左侧更优先的分支）获得优先执行权。

理解两种模式的"方向性"是关键：

```
Selector
├── Decorator: Health<20% (LowerPriority)    ← 条件从 false→true 时，中止右侧的 Patrol
│   └── Action: Flee
├── Decorator: HasAmmo? (Self)               ← 条件从 true→false 时，中止自己 + 右侧
│   └── Action: Shoot
└── Action: Patrol                            ← 最低优先级兜底
```

事件序列推演：
- NPC 正在 Patrol（第 3 个分支 Running）。
- 突然 Health < 20%：第 1 个 Decorator（LowerPriority）条件变为 true → 中止 Patrol → Selector 重新评估 → 进入 Flee。
- NPC 在 Flee 时血量恢复 > 20%：第 1 个 Decorator 条件变为 false。因为是 LowerPriority，不做任何事情——Flee 继续运行。这是一个重要的设计考量：你通常不希望"血量刚恢复就立即切回巡逻"。如果需要双向反应，使用 Both。
- NPC 在 Shoot 时弹药耗尽：第 2 个 Decorator（Self）条件变为 false → 中止 Shoot 及其右侧（无） → Selector 重新评估 → 可能进入 Patrol。

#### 时序装饰器（Timing Decorators）

**Cooldown（冷却）** 在 Tutorial 07 中已介绍。这里补充两个重要的时序装饰器：

**TimeLimit**：限制子节点的最大执行时间。超时后强制中止子节点并返回 `Failure`。

```
TimeLimit.Tick(dt):
  elapsed += dt
  if elapsed > limit:
    child.OnAbort()
    return Failure
  return child.Tick(dt)
```

经典用法：NPC 追逐玩家时最多追 10 秒，超过则放弃：

```
Selector
├── TimeLimit(10.0s)
│   └── Action: ChasePlayer()
└── Action: ReturnToPost()
```

注意与 Cooldown 的区别：Cooldown 限制的是"多久后才能再次执行"，TimeLimit 限制的是"最多执行多久"。两者可组合——例如"每次追逐最多持续 5 秒，且两次追逐之间至少间隔 8 秒"：

```
Cooldown(8.0s)
└── TimeLimit(5.0s)
    └── Action: ChasePlayer()
```

**Cooldown 的两种实现策略**：

| 策略 | 描述 | 优势 | 劣势 |
|---|---|---|---|
| Lock-based（锁模式） | 子节点成功后锁定 cooldownTime 秒，期间直接返回 Failure | 简单、低开销 | 冷却期间连条件检查都跳过 |
| Observation-based（观察模式） | 子节点成功后启动计时器，期间 Decorator 持续 tick 但不执行子节点 | 允许在冷却期间更新内部状态 | 稍高的每帧开销 |

UE 的 `BTDecorator_Cooldown` 使用 Lock-based 策略。

#### 循环装饰器（Looping Decorators）

Tutorial 07 介绍了 Repeater 的三种模式。这里深入其与 Observer Abort 的交互。

**Repeater + Observer Abort 的陷阱**：如果一个 `Repeater(forever)` 包裹的子树内部有一个带 `LowerPriority` Abort 的 Decorator，当该 Decorator 触发时，实际中止的是 Repeater 内部的分支，Repeater 会重新开始。这对大多数场景是正确的——但如果你希望 Abort 穿透 Repeater（即中止 Repeater 本身），你需要将 Abort Decorator 放在 Repeater 之外。

**UE 的 `UBTDecorator_Loop`**：UE 的 Loop 装饰器支持 `NumLoops`（循环次数）和 `InfiniteLoop`（无限循环），并且与 UE 的 Observer Abort 机制完全集成——如果 Loop 的条件不满足，整个被循环的子树会被中止。

#### ForceSuccess / ForceFailure（树形塑造）

这两个装饰器在简单版的 Succeeder/Failer 基础上，有一个重要的生产级特性：**它们可以改变树的结构而不改变行为语义**。

经典场景——"树形塑造"（Tree Shaping）：你有一个 Sequence 需要在中间某一环"无论如何都继续"，但你不希望这个环节的失败导致 Sequence 失败。

```
Sequence
├── Action: OpenDoor()          // 必须成功
├── ForceSuccess                // "可选"步骤——失败也不影响
│   └── Action: PlayBark("DoorStuck")  // 播放语音吐槽门卡住了
└── Action: EnterRoom()         // 开门（或吐槽后）进入房间
```

这里 `PlayBark` 可能失败（音频资源丢失、同一时间只能播放一条语音等），但无论成功与否，都不应阻止 NPC 进入房间。`ForceSuccess` 确保 Sequence 的"AND"语义不会因这个非关键步骤而中断。

**注意**：`ForceSuccess` 不吞掉 `Running`——如果子节点返回 `Running`，`ForceSuccess` 也返回 `Running`。只有当子节点返回 `Success` 或 `Failure` 时，它才将两者都转换为 `Success`。`ForceFailure` 同理。

#### Gate（门控装饰器）

Gate 是一种可手动开关的条件装饰器。与普通 Conditional 不同，Gate 的条件不是自动计算的，而是由外部系统（如脚本、任务完成事件、GameMode 状态）控制的。

```
Gate.Tick(dt):
  if !isOpen: return Failure
  return child.Tick(dt)

// External control:
Gate.Open()    // 允许子节点执行
Gate.Close()   // 阻止子节点执行
```

**经典场景：Boss 阶段控制**。Boss 在 Phase 1 不能使用 Phase 2 的技能：

```
Selector
├── Gate(Phase2Unlocked)       // Phase 2 开始时由 Boss Controller 打开
│   └── Action: UltimateAttack()
└── Action: NormalAttack()
```

Gate 也可以和 Conditional 组合：`Gate(Phase2Unlocked) + Conditional(HasMana)` ——两者的语义不同：Gate 是"设计师/脚本控制的阶段锁"，Conditional 是"运行时数据驱动的条件"。

#### Tag-based Decorators（UE GameplayTags 集成）

UE 的 GameplayTags 系统提供了一种层级化的标签机制。`UBTDecorator_TagCooldown` 和 `UBTDecorator_SetTagCooldown` 将行为树的冷却管理与 GameplayTags 集成：

- **TagCooldown**：检查某个 GameplayTag 是否处于冷却状态。适合跨实体共享冷却（如"同一阵营的所有 AI 共享'呼叫支援'的冷却"）。
- **SetTagCooldown**：在子节点完成后，在指定 GameplayTag 上设置冷却。适合在行为树中为特定行为打标签。

```
Cooldown(5s, Tag="Ability.FireBreath")
└── Action: FireBreath()
// 5 秒内，所有检查 Tag="Ability.FireBreath" 的 TagCooldown 装饰器都会返回 Failure
```

---

### Service 深度剖析

Service 是 UE Behavior Tree 独有的概念，在其他行为树实现中通常不存在或通过不同机制实现。理解 Service 是区分"了解 UE BT"和"真正用过 UE BT"的分水岭。

#### Service 是什么？

Service **不是控制流节点**。它不参与树的 Success/Failure/Running 决策。Service 是挂载在 Composite 节点上的**后台持续运行的任务**——当 Composite 处于活跃状态时，Service 按照配置的频率自动执行。

```
Selector                                    ← Composite（父节点）
├─ [Service: UpdateCombatRange @0.3s]      ← 挂在 Selector 上的 Service
├── Sequence
│   ├── Action: ChasePlayer
│   └── Action: MeleeAttack
└── Action: Patrol
```

当 Selector 活跃时（即它内部的某个子节点正在 Running），`UpdateCombatRange` Service 每 0.3 秒执行一次。当 Selector 退出时（所有子节点完成或被中止），Service 也停止执行。

#### Service vs Decorator vs Action

这是面试中的经典辨析题：

| | Decorator | Service | Action (Task) |
|---|---|---|---|
| 挂载位置 | 挂在 Composite/Task 上 | 挂在 Composite 上 | 作为 Composite 的子节点 |
| 执行时机 | 在父节点 tick 期间，装饰子节点之前 | 异步按间隔 tick（与父节点的 tick 并行） | 当被 Composite 选中时执行 |
| 控制流角色 | **条件的守卫**——决定是否允许执行 | **数据的准备者**——更新 Blackboard 信息 | **行为的执行者**——做具体事情 |
| 影响返回值 | 是（修改/覆盖子节点返回值） | **否**——Service 不返回任何状态 | 是（Success/Failure/Running） |
| 中止行为 | 可以触发分支 Abort | **不能**直接中止分支（但可以通过更新 BB 键间接触发 Decorator 的 Abort） | 通过返回 Failure 间接触发 |
| 典型场景 | "有弹药才能射击" | "每 0.5 秒更新最近的敌人位置" | "移动到目标位置" |

**何时用 Service 而非 Decorator**：
- 你需要**持续更新数据**而不关心条件结果 → Service。
- 你需要**根据数据决定是否允许执行** → Decorator（Conditional）。
- 你需要**基于数据的周期性操作**（如更新战术评分、查询 EQS）→ Service。

**何时用 Service 而非 Action**：
- 行为是**纯后台数据维护**，不产生可见行为（不移动、不播放动画）→ Service。
- 行为需要**独立于树的控制流运行**——即使当前 Task 还在 Running，这个逻辑也需要按时执行 → Service。
- 行为是**短暂的、无状态的**（一帧内完成）→ Service。

#### Service Tick Rate 与性能

Service 的 `TickInterval`（通常默认 0.5s）是性能的关键杠杆。每帧 tick 的 Service（Interval=0）只适用于极少数场景（如平滑更新 UI 指示器）。默认 0.3-0.5 秒对大多数游戏 AI 足够——人类玩家通常感知不到 0.3 秒的延迟。

性能预算估算：假设 100 个 AI，每个 AI 有 2 个活跃 Service，Interval 平均 0.5s。则：
- 每秒执行次数 = 100 × 2 × (1 / 0.5) = **400 次/秒**
- 如果 Service tick 耗时 0.1ms（简单 Blackboard 读写），总开销 = **0.04ms/帧** @ 60fps——可忽略
- 如果 Service tick 耗时 1ms（EQS 查询、路径搜索），总开销 = **0.4ms/帧**——仍可接受但需谨慎

**性能优化策略**：
1. **使用合理的 Interval**：不要为了"更快响应"而把 Interval 设为 0。如果数据变化频率本身就低（如目标位置变化每秒几次），高频 tick 是浪费。
2. **通过 Observer Abort 替代高频轮询**：与其让 Service 每 0.1s 更新距离并让 Conditional Decorator 轮询，不如让 Decorator 注册 Observer，只在距离真正变化时触发。
3. **LOD（Level of Detail）衰减**：远处 AI 的 Service Interval 可以降到 1-2 秒甚至暂停。

#### Service 的激活/停用生命周期

```
Composite 被激活
  └→ Service::OnBecomeRelevant(OwnerComp, NodeMemory)
       ├─ 初始化 NodeMemory
       ├─ 注册 Blackboard Observer（如果需要）
       └─ 第一次 Tick 安排在 Interval 后

每 Interval 秒:
  └→ Service::TickNode(OwnerComp, NodeMemory, DeltaSeconds)

Composite 退出（子节点全部完成 / 被 Abort）
  └→ Service::OnCeaseRelevant(OwnerComp, NodeMemory)
       ├─ 注销 Blackboard Observer
       └─ 清理 NodeMemory
```

**关键细节**：`OnBecomeRelevant` 在 Composite 被激活时调用，而不是在 Service 第一次 tick 时。这意味着 Service 可以在 Composite 刚激活时立即执行一次初始化逻辑（通过覆写 `OnBecomeRelevant`），而不需要等待第一个 TickInterval。

#### Service + Blackboard 更新模式

这是 Service 最经典的使用模式——Service 负责将传感器数据写入 Blackboard，Decorator 负责从 Blackboard 读取数据并做条件判断：

```
[Service: PerceptionUpdate @0.3s]               ← 数据生产者
  └── 每 0.3s: 查询 Perception 系统
       ├── 找到最近敌人 → BB.SetValue("TargetActor", ...)
       └── 计算敌人距离 → BB.SetValue("TargetDistance", ...)
Selector                                          ← 数据消费者
├── Decorator: TargetDistance < 300 (LowerPriority)
│   └── Action: MeleeAttack
├── Decorator: TargetDistance < 1000 (LowerPriority)
│   └── Action: RangedAttack
└── Action: Patrol
```

**职责分离**清晰：Service 只管"世界是什么样的"，Decorator 只管"基于已知信息我应该做什么"。这正是行为树的核心设计哲学——**数据与行为的分离**。

---

### Parallel 节点深度剖析

Tutorial 07 介绍了 Parallel 节点的基本策略。这里深入讨论工程实践中的关键问题。

#### UE 的 SimpleParallel

UE 的 `UBTComposite_SimpleParallel` 不是真正的"所有子节点同时执行"的 Parallel，而是一种**非对称并行**：

- **主任务（Main Task）**：第一个子节点，通常是 Action（如 MoveTo）。它的返回值决定整个 SimpleParallel 的返回值。
- **后台子树（Background Tree）**：第二个子节点，可以是任意复杂的子树。在后台独立运行，不影响主任务的返回值。

```
SimpleParallel (FinishMode: Immediate)
├── Action: MoveTo(TargetLocation)     ← 主任务
└── Sequence                           ← 后台子树
    ├── Condition: ThreatInRange?
    └── Action: Dodge()
```

`FinishMode` 参数：
- `Immediate`：主任务完成时，立即中止后台子树，SimpleParallel 返回主任务的结果。
- `Delayed`：主任务完成后，等待后台子树也完成（或失败），然后返回主任务的结果。

**SimpleParallel 的使用约束**：
1. 主任务只能是一个节点（不能是子树）。
2. 后台子树可以是任意复杂度的子树。
3. 后台子树的 Decorator 的 Observer Abort 仍然生效——这是"移动中受到攻击 → 立即闪避"的关键机制。

#### 真正的 Parallel（All Children Tick Simultaneously）

在自研行为树或某些中间件中，你可能需要真正的并行节点——所有子节点在同一帧中都被 tick。关键设计决策：

**1. 完成策略（Completion Policy）**：

| 策略 | 含义 | 返回值决策 |
|---|---|---|
| `SucceedOnOne` | 任一子节点成功即整体成功 | 返回 Success，中止其余子节点 |
| `SucceedOnAll` | 所有子节点成功才成功 | 全部成功才 Success，任一失败则 Failure |
| `FailOnOne` | 任一子节点失败即整体失败 | 返回 Failure，中止其余子节点 |
| `SucceedOnN(n)` | 至少 n 个子节点成功 | 满足时返回 Success |

**2. 子节点 Tick 顺序**：子节点按从左到右的顺序 tick，但顺序**不应影响行为正确性**。任何依赖特定顺序的 Parallel 都是设计错误。

**3. 中止传播**：当一个子节点满足完成条件时，其余仍在运行的子节点必须被中止。中止操作可以立即执行（同一帧）或延迟到下一帧。

#### 竞态条件与同步

Parallel 节点中最棘手的问题是竞态条件——多个子节点同时修改共享状态。

**竞态示例**：

```
Parallel (SucceedOnAll)                    ← 两个 Action 同时运行
├── Action: LookAt(Target)                 ← 修改 NPC 的朝向
└── Action: StrafeLeft()                   ← 修改 NPC 的位置和朝向
```

`LookAt` 设置 NPC 面向目标，`StrafeLeft` 设置 NPC 向左移动（通常需要 NPC 面向移动方向而非目标）。两个 Action 在同一帧中对朝向的修改以未定义的顺序发生，导致帧末的朝向是"最后一个执行的 Action 设置的"——完全不可预测。

**解决方案**：

1. **分层状态写入**：将状态分为"意图"和"结果"。Action 写入意图（"我想面向目标"），由统一的 Animation/Movement 系统在 Action 之后解析意图并计算最终结果。
2. **状态分区**：不同 Action 写入不同的状态键。`LookAt` 写入 `DesiredLookDirection`，`StrafeLeft` 写入 `MovementInput`。
3. **避免冲突 Action 放在同一 Parallel**：如果两个 Action 都控制朝向，它们不应该在同一个 Parallel 中。

#### Parallel 的使用场景

| 场景 | 节点类型 | 完成策略 | 说明 |
|---|---|---|---|
| 移动 + 扫描（Cover Move） | SimpleParallel | Immediate (主任务完成) | 移动到掩体的同时扫描威胁；到达掩体后后台子树被中止 |
| 战斗 + 监视血量（Fight + Monitor） | Parallel | FailOnOne (血量=0) | 战斗和血量监视同时进行；血量归零时整体失败，进入死亡行为 |
| 巡逻 + 监听声音（Patrol + Listen） | Parallel | SucceedOnOne (听到声音) | 巡逻中听到声音立即切换到调查分支；这个 Parallel 本身可能被更外层的 Selector 的 LowerPriority Abort 中止 |
| 多传感器融合 | Parallel | SucceedOnN(2) | 视觉、听觉、嗅觉传感器同时评估，至少 2 个确认才认为"检测到目标" |

---

## 2. 代码示例

### 示例 A: C# Decorator 实现集

以下代码基于 Tutorial 08 中的 `BTNode` 基类。所有 Decorator 都是 `BTNode` 的子类，包装单个子节点。

```csharp
// ============================================================
// DECORATOR BASE
// ============================================================
public abstract class BTDecorator : BTNode
{
    protected BTNode child;

    public BTDecorator(BTNode child)
    {
        this.child = child;
    }

    public override void OnAbort()
    {
        child.OnAbort();
    }
}

// ============================================================
// CONDITIONAL — Blackboard-based with Observer Abort
// ============================================================
public class BTConditional : BTDecorator
{
    private Func<bool> condition;
    private Blackboard blackboard;
    private string observedKey;

    // Observer abort mode
    public enum ObserverMode { None, Self, LowerPriority, Both }
    private ObserverMode observerMode;

    private bool lastConditionResult;
    private bool wasActive; // tracks whether condition was already true

    public BTConditional(BTNode child, Func<bool> condition,
        ObserverMode observerMode = ObserverMode.None)
        : base(child)
    {
        this.condition = condition;
        this.observerMode = observerMode;
    }

    // Register a Blackboard observer for event-driven abort
    public BTConditional ObserveBlackboard(Blackboard bb, string key)
    {
        this.blackboard = bb;
        this.observedKey = key;
        bb.OnKeyChanged += OnObservedKeyChanged;
        return this; // fluent API
    }

    private void OnObservedKeyChanged(string key, object newValue)
    {
        if (key != observedKey) return;
        if (observerMode == ObserverMode.None) return;

        bool currentResult = condition();
        if (currentResult != lastConditionResult)
        {
            lastConditionResult = currentResult;
            RequestAbort(); // This must be handled by the tree executor
        }
    }

    // Called by tree executor when abort is requested
    public bool EvaluateAbort(out bool shouldAbortSelf, out bool shouldAbortLowerPriority)
    {
        shouldAbortSelf = false;
        shouldAbortLowerPriority = false;

        bool current = condition();

        if (observerMode == ObserverMode.Self || observerMode == ObserverMode.Both)
        {
            // Condition was true, now false → abort self
            if (wasActive && !current)
                shouldAbortSelf = true;
        }

        if (observerMode == ObserverMode.LowerPriority || observerMode == ObserverMode.Both)
        {
            // Condition was false, now true → abort lower priority
            if (!wasActive && current)
                shouldAbortLowerPriority = true;
        }

        wasActive = current;
        return shouldAbortSelf || shouldAbortLowerPriority;
    }

    public override BTStatus Tick(float dt)
    {
        if (!condition())
        {
            wasActive = false;
            return BTStatus.Failure;
        }
        wasActive = true;
        return child.Tick(dt);
    }
}

// ============================================================
// COOLDOWN — Lock-based
// ============================================================
public class BTCooldown : BTDecorator
{
    private float cooldownTime;
    private float lastSuccessTime = float.MinValue;

    public BTCooldown(BTNode child, float cooldownTime) : base(child)
    {
        this.cooldownTime = cooldownTime;
    }

    public override BTStatus Tick(float dt)
    {
        if (Time.time - lastSuccessTime < cooldownTime)
            return BTStatus.Failure;

        BTStatus status = child.Tick(dt);
        if (status == BTStatus.Success)
            lastSuccessTime = Time.time;

        return status;
    }
}

// ============================================================
// TIME LIMIT
// ============================================================
public class BTTimeLimit : BTDecorator
{
    private float timeLimit;
    private float elapsed;

    public BTTimeLimit(BTNode child, float timeLimit) : base(child)
    {
        this.timeLimit = timeLimit;
    }

    public override void OnEnter()
    {
        elapsed = 0f;
        child.OnEnter();
    }

    public override BTStatus Tick(float dt)
    {
        elapsed += dt;
        if (elapsed >= timeLimit)
        {
            child.OnAbort();
            return BTStatus.Failure;
        }
        return child.Tick(dt);
    }
}

// ============================================================
// REPEATER — finite, infinite, until-fail
// ============================================================
public class BTRepeater : BTDecorator
{
    public enum RepeaterMode { Count, Forever, UntilFail }

    private RepeaterMode mode;
    private int maxCount;
    private int completedCount;

    // Static factory methods for expressive construction
    public static BTRepeater Forever(BTNode child) =>
        new BTRepeater(child, RepeaterMode.Forever, 0);

    public static BTRepeater Count(BTNode child, int n) =>
        new BTRepeater(child, RepeaterMode.Count, n);

    public static BTRepeater UntilFail(BTNode child) =>
        new BTRepeater(child, RepeaterMode.UntilFail, 0);

    private BTRepeater(BTNode child, RepeaterMode mode, int maxCount)
        : base(child)
    {
        this.mode = mode;
        this.maxCount = maxCount;
    }

    public override void OnEnter()
    {
        completedCount = 0;
        base.OnEnter();
    }

    public override BTStatus Tick(float dt)
    {
        BTStatus status = child.Tick(dt);

        switch (mode)
        {
            case RepeaterMode.Count:
                if (status != BTStatus.Running)
                {
                    if (status == BTStatus.Success) completedCount++;
                    if (completedCount >= maxCount)
                        return BTStatus.Success;
                    child.OnEnter(); // reset child for next iteration
                    return BTStatus.Running;
                }
                return BTStatus.Running;

            case RepeaterMode.Forever:
                if (status != BTStatus.Running)
                {
                    child.OnEnter();
                }
                return BTStatus.Running; // Never returns Success

            case RepeaterMode.UntilFail:
                if (status == BTStatus.Failure)
                    return BTStatus.Failure; // stop repeating on failure
                if (status == BTStatus.Success)
                    child.OnEnter(); // restart on success
                return BTStatus.Running;

            default:
                return status;
        }
    }
}

// ============================================================
// INVERTER
// ============================================================
public class BTInverter : BTDecorator
{
    public BTInverter(BTNode child) : base(child) { }

    public override BTStatus Tick(float dt)
    {
        BTStatus status = child.Tick(dt);
        if (status == BTStatus.Success) return BTStatus.Failure;
        if (status == BTStatus.Failure) return BTStatus.Success;
        return status;
    }
}

// ============================================================
// FORCE SUCCESS
// ============================================================
public class BTForceSuccess : BTDecorator
{
    public BTForceSuccess(BTNode child) : base(child) { }

    public override BTStatus Tick(float dt)
    {
        BTStatus status = child.Tick(dt);
        if (status == BTStatus.Running) return BTStatus.Running;
        return BTStatus.Success;
    }
}

// ============================================================
// GATE — externally controlled open/close
// ============================================================
public class BTGate : BTDecorator
{
    private bool isOpen;

    public BTGate(BTNode child, bool startOpen = true) : base(child)
    {
        this.isOpen = startOpen;
    }

    public void Open() => isOpen = true;
    public void Close() => isOpen = false;
    public void Toggle() => isOpen = !isOpen;

    public override BTStatus Tick(float dt)
    {
        if (!isOpen) return BTStatus.Failure;
        return child.Tick(dt);
    }
}
```

### 示例 B: C# Service 实现

Service 不继承 `BTNode`——它有自己的生命周期，独立于树的控制流。

```csharp
// ============================================================
// SERVICE BASE — attached to Composite nodes
// ============================================================
public abstract class BTService
{
    private float tickInterval;
    private float timeSinceLastTick;
    private bool isActive;

    // The Composite this service is attached to
    public BTComposite Owner { get; internal set; }

    public BTService(float tickInterval = 0.5f)
    {
        this.tickInterval = Math.Max(tickInterval, 0.01f);
    }

    // Called by Owner Composite when it becomes active
    public void NotifyActivation()
    {
        isActive = true;
        timeSinceLastTick = 0f;
        OnActivation();
    }

    // Called by Owner Composite when it becomes inactive
    public void NotifyDeactivation()
    {
        isActive = false;
        OnDeactivation();
    }

    // Called by tree executor every frame (not just on tick interval)
    public void Update(float dt)
    {
        if (!isActive) return;

        timeSinceLastTick += dt;
        if (timeSinceLastTick >= tickInterval)
        {
            timeSinceLastTick -= tickInterval; // carry over remainder
            TickNode(dt); // note: pass the actual dt, not tickInterval
        }
    }

    // --- Override these in subclasses ---

    protected virtual void OnActivation() { }
    protected virtual void OnDeactivation() { }
    protected abstract void TickNode(float dt);
}

// ============================================================
// CONCRETE SERVICE: Enemy Proximity Service
// ============================================================
public class EnemyProximityService : BTService
{
    private Blackboard blackboard;
    private string targetKey;
    private string distanceKey;
    private string threatLevelKey;
    private Transform ownerTransform;

    public EnemyProximityService(
        Blackboard blackboard,
        Transform ownerTransform,
        string targetKey = "Target",
        string distanceKey = "TargetDistance",
        string threatLevelKey = "ThreatLevel",
        float tickInterval = 0.3f)
        : base(tickInterval)
    {
        this.blackboard = blackboard;
        this.ownerTransform = ownerTransform;
        this.targetKey = targetKey;
        this.distanceKey = distanceKey;
        this.threatLevelKey = threatLevelKey;
    }

    protected override void TickNode(float dt)
    {
        // Find nearest enemy within perception range
        Enemy nearest = PerceptionSystem.FindNearestEnemy(
            ownerTransform.position, maxRange: 50f);

        if (nearest != null)
        {
            float distance = Vector3.Distance(
                ownerTransform.position, nearest.transform.position);

            blackboard.Set(targetKey, nearest);
            blackboard.Set(distanceKey, distance);

            // Calculate threat level
            int threatLevel = CalculateThreatLevel(nearest, distance);
            blackboard.Set(threatLevelKey, threatLevel);
        }
        else
        {
            blackboard.Clear(targetKey);
            blackboard.Set(distanceKey, float.MaxValue);
            blackboard.Set(threatLevelKey, 0);
        }
    }

    private int CalculateThreatLevel(Enemy enemy, float distance)
    {
        int level = 0;
        if (distance < 10f) level += 3;
        else if (distance < 25f) level += 2;
        else level += 1;

        if (enemy.IsElite) level += 2;
        if (enemy.IsAttackingPlayer) level += 1;

        return level;
    }
}
```

### 示例 C: UE C++ 自定义 Decorator——带 Observer Abort 的生命值检查

这是一个完整的、可编译的 UE5 Decorator 示例，展示 Observer Abort 的生产级用法。核心要点：Observer Abort 不是通过轮询实现的，而是通过 Blackboard 的通知机制。

```cpp
// BTDecorator_HealthCheck.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/BTDecorator.h"
#include "BTDecorator_HealthCheck.generated.h"

/**
 * Checks AI health percentage against a threshold.
 * Supports Observer Abort: when health drops below threshold,
 * aborts lower-priority branches (e.g., stops patrol, enters flee).
 */
UCLASS()
class UBTDecorator_HealthCheck : public UBTDecorator
{
    GENERATED_BODY()

public:
    UBTDecorator_HealthCheck();

protected:
    /** Health threshold as percentage (0.0 - 1.0). */
    UPROPERTY(EditAnywhere, Category = "Condition",
        meta = (ClampMin = "0.0", ClampMax = "1.0"))
    float HealthThreshold = 0.3f;

    /** Abort mode: Self (condition became false → abort self),
        LowerPriority (condition became true → abort lower),
        Both (bidirectional). */
    UPROPERTY(EditAnywhere, Category = "FlowControl")
    EBTFlowAbortMode::Type FlowAbortMode = EBTFlowAbortMode::LowerPriority;

    /** If true, use Blackboard key instead of direct health query. */
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    bool bUseBlackboardHealth = true;

    /** Blackboard key storing current health percentage. */
    UPROPERTY(EditAnywhere, Category = "Blackboard",
        meta = (EditCondition = "bUseBlackboardHealth"))
    FBlackboardKeySelector HealthBlackboardKey;

    // --- UBTDecorator overrides ---
    virtual bool CalculateRawConditionValue(
        UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const override;

    virtual void OnBecomeRelevant(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;

    virtual void OnCeaseRelevant(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;

    virtual FString GetStaticDescription() const override;

    virtual EBTFlowAbortMode::Type GetFlowAbortMode() const override
    {
        return FlowAbortMode;
    }

    virtual bool IsObserverActive() const override { return true; }

    // Called when an observed Blackboard key changes value
    virtual void OnBlackboardKeyValueChange(
        const UBlackboardComponent& BlackboardComp,
        FBlackboard::FKey ChangedKeyID) override;

    /** Actually reads health — supports both BB and direct query. */
    float GetHealthPercent(const UBehaviorTreeComponent& OwnerComp) const;

    /** Whether this decorator needs to observe the BB key. */
    bool ShouldObserverActivate() const
    {
        return FlowAbortMode != EBTFlowAbortMode::None
            && bUseBlackboardHealth;
    }
};
```

```cpp
// BTDecorator_HealthCheck.cpp
#include "BTDecorator_HealthCheck.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "BehaviorTree/Blackboard/BlackboardKeyType_Float.h"
#include "GameFramework/Actor.h"
#include "AIController.h"

UBTDecorator_HealthCheck::UBTDecorator_HealthCheck()
{
    NodeName = TEXT("Health Check");

    // Notify when the node becomes relevant — required for Observer Abort
    bNotifyBecomeRelevant = true;
    bNotifyCeaseRelevant = true;

    // Accept only float keys — prevents designer error
    HealthBlackboardKey.AddFloatFilter(this,
        GET_MEMBER_NAME_CHECKED(UBTDecorator_HealthCheck, HealthBlackboardKey));
}

bool UBTDecorator_HealthCheck::CalculateRawConditionValue(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
{
    float Health = GetHealthPercent(OwnerComp);
    return Health <= HealthThreshold;
}

void UBTDecorator_HealthCheck::OnBecomeRelevant(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    Super::OnBecomeRelevant(OwnerComp, NodeMemory);

    // Register as observer if using Blackboard + observer mode
    if (ShouldObserverActivate())
    {
        UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
        if (BB)
        {
            BB->RegisterObserver(HealthBlackboardKey.GetSelectedKeyID(),
                this, FOnBlackboardChangeNotification::CreateUObject(
                    this, &UBTDecorator_HealthCheck::OnBlackboardKeyValueChange));
        }
    }
}

void UBTDecorator_HealthCheck::OnCeaseRelevant(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    // Unregister observer
    if (ShouldObserverActivate())
    {
        UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
        if (BB)
        {
            BB->UnregisterObserversFrom(this);
        }
    }

    Super::OnCeaseRelevant(OwnerComp, NodeMemory);
}

void UBTDecorator_HealthCheck::OnBlackboardKeyValueChange(
    const UBlackboardComponent& BlackboardComp,
    FBlackboard::FKey ChangedKeyID)
{
    // Only react if the changed key is the one we observe
    if (ChangedKeyID != HealthBlackboardKey.GetSelectedKeyID())
        return;

    // Re-evaluate condition — UE's BT component handles the abort flow
    UBehaviorTreeComponent* OwnerComp = Cast<UBehaviorTreeComponent>(
        BlackboardComp.GetBrainComponent());
    if (!OwnerComp) return;

    bool bCurrentValue = CalculateRawConditionValue(*OwnerComp, nullptr);

    // UE internally compares this against cached value and triggers abort
    // This is handled by UBehaviorTreeComponent's observer processing
}

float UBTDecorator_HealthCheck::GetHealthPercent(
    const UBehaviorTreeComponent& OwnerComp) const
{
    if (bUseBlackboardHealth)
    {
        const UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
        if (BB)
        {
            return BB->GetValue<UBlackboardKeyType_Float>(
                HealthBlackboardKey.GetSelectedKeyID());
        }
    }

    // Fallback: read directly from controlled pawn
    APawn* ControlledPawn = OwnerComp.GetAIOwner()->GetPawn();
    if (!ControlledPawn) return 1.0f;

    // Assume the pawn implements IHealthInterface
    if (IHealthInterface* HealthInterface =
        Cast<IHealthInterface>(ControlledPawn))
    {
        return HealthInterface->GetHealthPercent();
    }

    return 1.0f;
}

FString UBTDecorator_HealthCheck::GetStaticDescription() const
{
    return FString::Printf(TEXT("Health <= %.0f%%%s"),
        HealthThreshold * 100.0f,
        (FlowAbortMode == EBTFlowAbortMode::LowerPriority)
            ? TEXT("\n[Abort LowerPriority]")
            : TEXT(""));
}
```

### 示例 D: UE C++ 自定义 Service——定期更新目标距离

```cpp
// BTService_UpdateTargetDistance.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Services/BTService_BlackboardBase.h"
#include "BTService_UpdateTargetDistance.generated.h"

/**
 * Periodically calculates distance from AI to its target
 * and writes the result to a Blackboard float key.
 * Standard service pattern: sensor → Blackboard → decorator → action.
 */
UCLASS()
class UBTService_UpdateTargetDistance : public UBTService_BlackboardBase
{
    GENERATED_BODY()

public:
    UBTService_UpdateTargetDistance();

protected:
    /** Blackboard key for the target actor. */
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector TargetActorKey;

    /** Blackboard key to write the calculated distance to. */
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector TargetDistanceKey;

    /** Max distance — if no target or target is farther, write this. */
    UPROPERTY(EditAnywhere, Category = "Settings")
    float MaxDistance = 9999.0f;

    // --- UBTService overrides ---
    virtual void TickNode(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;

    virtual void OnBecomeRelevant(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;

    virtual FString GetStaticDescription() const override;
};
```

```cpp
// BTService_UpdateTargetDistance.cpp
#include "BTService_UpdateTargetDistance.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "BehaviorTree/Blackboard/BlackboardKeyType_Object.h"
#include "BehaviorTree/Blackboard/BlackboardKeyType_Float.h"
#include "AIController.h"
#include "GameFramework/Actor.h"

UBTService_UpdateTargetDistance::UBTService_UpdateTargetDistance()
{
    NodeName = TEXT("Update Target Distance");

    // Default tick interval — service runs every 0.3 seconds
    Interval = 0.3f;
    RandomDeviation = 0.05f; // ±0.05s jitter to avoid spike alignment

    // Accept only Object keys for target
    TargetActorKey.AddObjectFilter(this,
        GET_MEMBER_NAME_CHECKED(UBTService_UpdateTargetDistance, TargetActorKey),
        AActor::StaticClass());

    // Accept only Float keys for distance
    TargetDistanceKey.AddFloatFilter(this,
        GET_MEMBER_NAME_CHECKED(UBTService_UpdateTargetDistance, TargetDistanceKey));
}

void UBTService_UpdateTargetDistance::OnBecomeRelevant(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    Super::OnBecomeRelevant(OwnerComp, NodeMemory);

    // Write initial distance immediately on activation — don't wait for first interval
    // TickNode with 0 delta so consumers see immediate data
    TickNode(OwnerComp, NodeMemory, 0.0f);
}

void UBTService_UpdateTargetDistance::TickNode(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds)
{
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return;

    AActor* TargetActor = Cast<AActor>(
        BB->GetValue<UBlackboardKeyType_Object>(
            TargetActorKey.GetSelectedKeyID()));

    float Distance = MaxDistance;

    if (TargetActor && TargetActor->IsValidLowLevel())
    {
        APawn* ControlledPawn = OwnerComp.GetAIOwner()->GetPawn();
        if (ControlledPawn)
        {
            Distance = FVector::Dist(
                ControlledPawn->GetActorLocation(),
                TargetActor->GetActorLocation());
        }
    }

    BB->SetValue<UBlackboardKeyType_Float>(
        TargetDistanceKey.GetSelectedKeyID(), Distance);
}

FString UBTService_UpdateTargetDistance::GetStaticDescription() const
{
    return FString::Printf(TEXT("Update distance to target every %.1fs\nTarget: %s\nOutput: %s"),
        Interval,
        *TargetActorKey.SelectedKeyName.ToString(),
        *TargetDistanceKey.SelectedKeyName.ToString());
}
```

---

## 3. 练习

### 练习 1：构建带 Observer Abort 的反应式守卫 AI

设计一个完整的行为树，实现一个"守卫 NPC"，满足以下需求：

1. **默认行为**：沿指定路径巡逻。
2. **警戒行为**：当玩家进入 20 米检测半径时，立即中断巡逻，转向玩家并进入警戒状态（不攻击，只面向玩家）。注意：这里的"立即"是关键——不能等巡逻动作完成。
3. **战斗行为**：当玩家进入 8 米攻击范围时，立即中断巡逻/警戒，开始攻击玩家。攻击包含冷却（每次攻击间隔 1.5 秒）。
4. **回归巡逻**：当玩家离开 30 米范围超过 3 秒后，返回巡逻。

要求：
- 画出完整的树结构，标注每个 Decorator 的 Observer Abort 模式（Self/LowerPriority/Both）。
- 解释为什么在"进入警戒"和"进入战斗"分支上使用 LowerPriority。
- 分析：为什么"回归巡逻"的条件使用 30 米而非 20 米（提示：迟滞/Hysteresis）。
- 写 5 tick 追踪表：假设玩家从远处走入 20 米→进入 8 米→离开 8 米→离开 30 米。

### 练习 2：实现 Parallel 节点——移动 + 开火

在你选择的框架中（Unity C# 或 UE C++），实现一个并行节点，创建可以**同时移动和射击**的 AI。

要求：
- 实现 Parallel 节点的完整逻辑，包括子节点同时 tick 和中止传播。
- 将 Parallel 用于以下 AI 行为树：在追逐玩家时同时射击。
- 处理边界情况：移动到达目标后射击是否也应该停止？射击的子弹打完了怎么办？
- 考虑：如果移动失败（路径不可达），应该中止射击吗？反之——如果弹药耗尽，应该中止移动吗？解释你的完成策略选择。

### 练习 3（可选）：设计 Squad 血量监控 Service

设计一个 Service，不依赖任何具体游戏引擎，描述其逻辑和集成方式：

1. Service 挂载在整个小队的"战斗"Composite 节点上，每 1.0 秒执行一次。
2. Service 遍历小队所有成员的血量。
3. 当小队阵亡比例超过 60% 时，Service 更新 Blackboard 中的 `ShouldRegroup` 键为 true。
4. 一个带 `LowerPriority` Observer Abort 的 Decorator 检查 `ShouldRegroup`，触发小队撤退行为。
5. 当 `ShouldRegroup` 变为 true 后，Service 的角色是什么？撤退过程中还需要继续监控血量吗？

要求：
- 描述 Service 的数据访问模式——它如何获取每个队员的血量（Blackboard？直接访问？事件系统？）。
- 分析：60% 的阈值选择——如果瞬时损失从 50% 跳到 70%（一发火箭弹击杀多人），这个逻辑是否仍然正确？
- 讨论性能：100 个 AI + 每个都有这个 Service，每秒执行 100 次全队血量遍历，是否可接受？如何优化？

---

## 4. 扩展阅读

- **Unreal Engine 官方——Behavior Tree Observer Aborts**：UE 文档中关于 `FlowAbortMode` 的详细说明，包括每种模式的行为树图表演示。
  - [Behavior Tree User Guide: Decorators](https://docs.unrealengine.com/5.3/en-US/behavior-tree-node-reference-decorators-in-unreal-engine/)
  - [Behavior Tree Aborts](https://docs.unrealengine.com/5.3/en-US/behavior-tree-how-aborts-work/)
- **Alex J. Champandard — "Parallelizing Behavior Trees" (AiGameDev.com, 2008)**：讨论了并行节点中的竞态条件、执行顺序语义和确定性保证。这是行为树并行节点的理论奠基文章之一。
- **Colledanchise & Ögren — *Behavior Trees in Robotics and AI: An Introduction* (CRC Press, 2018)**：第 5 章给出了 Parallel 节点的形式化定义和收敛性分析，适合想从数学角度理解 Parallel 语义的读者。
- **Chris Simpson — "Behavior trees for AI: How they work" (Gamasutra, 2014)**：包含 Decorator 栈叠顺序的直观图解。
- **Game AI Pro 3 — "The Simplest AI Trick in the Book: Reactive Behavior Tree Aborts" (Rabin, 2017)**：讨论 Observer Abort 在实际项目中的模式——如何避免 abort 循环、与动画状态机的集成、性能预算管理。
- **UE4/UE5 Source Code**：`UBTDecorator` 和 `UBTService` 的实现是学习 C++ 行为树框架设计的最佳参考。关注 `BehaviorTreeComponent.cpp` 中 `ProcessObserverAborts` 函数的实现——这是整个 Observer Abort 机制的运行时核心。

---

## 常见陷阱

### 1. Observer Abort 循环（Abort Ping-Pong）

**症状**：NPC 在两个行为之间快速切换——例如在 Attack 和 Patrol 之间每帧来回跳转。

**根因**：Decorator 的条件在边界值附近振荡。例如 `DistanceToPlayer < 500` 触发 Attack；Attack 的第一步是向玩家靠近——但靠近时距离刚好超过 500（因为攻击有最小距离），条件变为 false → Self Abort 回 Patrol → Patrol 让 NPC 远离玩家 → 距离又 < 500 → 又触发 Attack。每帧都在 abort 和 re-enter。

**解法**：
1. **使用迟滞（Hysteresis）**：进入条件 ≠ 退出条件。Attack 进入条件 `dist < 500`，Attack 退出条件 `dist > 700`。200 单位的缓冲区吸收边界振荡。
2. **使用 LowerPriority 而非 Both**：在不需要双向反应的场景中，只用单向 Abort。例如"血量 < 20% → Flee"用 LowerPriority（只在血量变低时抢断），但血量恢复时不自动切回——避免 NPC 在 19% 和 21% 之间抖动。
3. **加最小稳定时间**：条件必须连续满足 N 帧才算"真"，避免瞬时波动触发 abort。

### 2. Service Tick 在规模下的性能问题

**症状**：当场景中有 200+ 个 AI 时，帧率明显下降。Profiler 显示大量时间消耗在 Service 的 `TickNode` 中。

**根因**：Service 的 Interval 设得太激进（如 0.1s 或 0.0s），导致大量 AI 每帧都在执行代价高昂的查询（EQS、路径搜索、多目标排序）。

**解法**：
1. **提高 Interval**：大多数感知更新不需要每秒 10 次。0.3-0.5s 对人类玩家已足够。
2. **使用 `RandomDeviation`**：UE 的 `UBTService` 内置 `RandomDeviation` 参数——Service 的 tick 会加上一个随机偏移，避免所有 AI 在同一帧 tick，导致帧级 CPU 尖峰（Tick Alignment 问题）。
3. **LOD 衰减**：根据 AI 与玩家的距离或屏幕占比，动态调整 Interval。远处 AI 的 Service 可以 2 秒 tick 一次甚至暂停。
4. **用 Observer Abort 替代轮询**：如果 Service 的唯一目的是"更新数据以便 Decorator 检查"，考虑直接让 Decorator 注册 Observer，减少不必要的中间层。

### 3. 忘记在 Service 中调用 Super::OnBecomeRelevant

**症状**：Service 虽能编译运行，但行为异常——Blackboard Observer 未注册、NodeMemory 未初始化、Service 在编辑器中显示为灰色（未激活）。

**根因**：UE 的 `UBTService::OnBecomeRelevant` 和 `UBTService::OnCeaseRelevant` 内部有框架级的初始化逻辑。如果你覆写它们而没有调用 `Super::`，框架无法完成节点内存分配和 Observer 注册。

**解法**：
```cpp
void UMyService::OnBecomeRelevant(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    Super::OnBecomeRelevant(OwnerComp, NodeMemory); // ALWAYS call this first
    // Your custom init logic here
}
```

### 4. Parallel 节点子节点顺序的未定义行为

**症状**：Parallel 中两个 Action 写入同一个 Blackboard 键，或修改同一个 Transform。行为因平台（或运行次数）而异——有时正确，有时错误。

**根因**：Parallel 节点的子节点在同一帧内 tick，但 tick 顺序是**实现定义的**（即 C++ 标准所说的"unspecified behavior"——它有一个确定的顺序，但这个顺序可能因实现而异，程序员不能依赖它）。依赖特定 tick 顺序的 Parallel 是 fragile 设计。

**解法**：
1. **状态分层**：使用"意图"层和"应用"层。Action 写入意图，单一的后处理步骤将所有意图合并为最终输出。
2. **Key 分区**：不同子节点使用不同的 Blackboard 键，避免写入冲突。
3. **不要在同一 Parallel 中运行冲突的操作**：如果两个 Action 都需要控制朝向（LookAt + Strafe），它们不应该在同一个 Parallel 中。

### 5. Decorator Self/LowerPriority/Both 作用域混淆

**症状**：给一个 Decorator 设置了 `Both` Abort，期望它"条件为假时退出自己，条件为真时抢断别人"，但实际行为与预期不符。

**根因**：`Self` 和 `LowerPriority` 的作用域是**不同的方向**。`Self` 中止当前分支及**右侧同级**分支；`LowerPriority` 只中止**右侧**分支（不中止自己）。`Both` 是两者叠加。

**常见误解场景**：
```
Selector
├── Decorator: HasTarget? (LowerPriority)   ← A
│   └── Attack
└── Patrol                                  ← B
```

当 `HasTarget?` 变为 false 时，**什么都不会发生**（因为 `LowerPriority` 只在变为 true 时触发）。这是正确的——但开发者常常以为"目标丢失 → 自动停止攻击"，这需要 `Self` 或 `Both`。

**规则速查卡**：

| 条件变化 | Self | LowerPriority | Both |
|---|---|---|---|
| true → false | 中止自己 + 右侧 | 无操作 | 中止自己 + 右侧 |
| false → true | 无操作 | 中止右侧 | 中止右侧 |

### 6. Service 数据过时（Stale Data）

**症状**：AI 在目标已死/已消失后仍然向目标位置移动，因为 Service 还没到下一个 tick 周期，Blackboard 中仍保留着旧目标。

**根因**：Service 的数据生产是异步的——它有自己的 tick 周期。在两次 Service tick 之间，Blackboard 中的数据可能是过时的。

**解法**：
1. **事件驱动失效**：当目标死亡/消失时，通过事件系统立即清空 Blackboard 中的 `Target` 键，不等 Service 下次 tick。Services 适合**周期性更新**，不适合**事件响应**。
2. **结合 Observer Abort**：让 Decorator 注册 Blackboard Observer。当目标失效事件清除 Blackboard 键时，Decorator 立即触发 Abort。
3. **在 Task 内部做最终验证**：Task 在 `ExecuteTask` 中检查目标是否仍有效（`IsValid()` + `IsAlive()`），无效时返回 `Failed` 而非盲目使用过时数据。

---

> **下一步**: 完成本教程后，进入 Tutorial 13 [行为树调试、可视化与性能优化](13-bt-debugging-visualization.md)，学习如何在实际项目中定位行为树的问题、使用可视化调试工具、以及优化大规模 AI 场景的性能。
