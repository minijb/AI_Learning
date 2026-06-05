---
title: "行为树基础理论"
updated: 2026-06-05
---

# 行为树基础理论

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 90min
> 前置知识: 01-fsm-core-concepts

---

## 1. 概念讲解

### FSM 的天花板：状态爆炸与复用危机

在 Tutorial 01-04 中，我们学习了有限状态机（FSM）。在 Tutorial 05 中，我们看到了 HSM 如何通过层次化组织来缓解状态爆炸。但 FSM 体系——包括 HSM——在某些场景下仍然存在根本性的局限。

假设你要设计一个游戏中的队友 AI，需要处理以下行为：

- 发现敌人时开枪
- 低血量时找掩体并使用治疗物品
- 没有敌人时跟随玩家
- 玩家倒地时优先救援
- 弹药不足时切换到次要武器
- 听到枪声时警惕并报告

用一个平面 FSM 表达这些行为，你会立刻撞上三个问题：

**问题一：状态数量的组合爆炸。**每个"在做什么"和"为什么这样做"的组合都需要一个独立状态。`Combat_Healthy_PrimaryWeapon`、`Combat_LowHealth_Cover`、`Combat_LowHealth_Heal`、`Idle_FollowPlayer`、`Alert_RescuePlayer`、`Combat_LowAmmo_SwitchWeapon`……如果你有 6 种顶层行为、4 种状态修饰、3 种武器条件，理论上需要 `6 × 4 × 3 = 72` 个状态。HSM 能压缩到约 20-30 个，但仍然需要你手动管理层次结构。

**问题二：行为片段不可复用。**"找掩体"这个行为在 `Combat_LowHealth` 和 `Alert_UnderFire` 中都需要。在 FSM 中，你要么复制代码到两个状态里，要设计一个共享的"掩体子状态"并保证两个父状态都能正确地转换进去再转出来。行为树从根本上解决了这个问题——"找掩体"就是一个子树，任何需要它的地方都可以插入。

**问题三：优先级表达笨拙。**FSM 通过转移表表达"什么条件下切换到哪个状态"。但如果多个条件同时满足（敌人很近、血量低、玩家倒地），你需要显式编码优先级——先检查 A，再检查 B，再检查 C。修改优先级意味着重新排列 if-else 或转移表顺序。行为树通过树结构的物理排列直接表达优先级——左子树先于右子树。修改优先级 = 拖动节点在树中的位置。

这三类问题在 AAA 游戏中尤为严重。一个典型的 3A 敌人 AI 有几十种变体、不同难度下的行为差异、与关卡脚本的交互、和其他 AI 协同。Bungie 在 Halo 1 中用传统 FSM 驱动敌人 AI 还算可控（约 15-20 个状态），但到 Halo 2 时，设计需求暴增——多兵种、载具战、小队协作、动态难度调整——FSM 彻底不够用了。

### 历史起源：Halo 2 与 GDC 2005

2005 年 GDC（Game Developers Conference）上，Bungie 的 AI 工程师 **Damian Isla** 做了一场影响深远的演讲：*"Managing Complexity in the Halo 2 AI"*。

演讲的核心问题是：**当你需要 50+ 种行为、它们之间互相抢占优先级、设计团队每两周就要新增行为时，FSM 还能用吗？**

Isla 的答案——"坦率地说，不能"——导致了行为树在游戏 AI 中的诞生。Halo 2 的 AI 系统不是教科书行为树（那个术语当时还未定型），而是一个"优先级排序的行为列表"——每个行为节点是一个自包含的、可被抢占的决策模块，系统每帧从根开始按优先级评估。这种**从根重新评估**的特性和**树形结构组织**后来被形式化为现代行为树。

Halo 2 的行为树系统带来了几个革命性的设计：

1. **从根重新评估**：不记住"上一次在哪个状态"，每帧从头遍历树。这意味着行为是**无状态的**（stateless）——没有隐藏的"当前模式"需要追踪。
2. **优先级即树结构**：节点的左右顺序直接编码优先级。设计师拖拽节点就能调整 AI 的决策优先级，不需要改动代码。
3. **行为可组合**：一个"开火"行为可以被"投掷手雷"行为抢占，手雷行为结束后系统自然回到"开火"（如果条件仍满足）——不需要显式的"返回上一状态"转移。

自 Halo 2 之后，行为树迅速成为游戏 AI 的标准工具：CryEngine、Unreal Engine 3/4/5、Killzone、The Last of Us、Alien: Isolation、StarCraft II 的战役 AI……几乎所有需要复杂 NPC 行为的游戏都选择了行为树或其变体。

### 核心隐喻：树形计划执行，而非状态机

行为树的思维方式与 FSM 截然不同。如果说 FSM 是"我处于什么状态？什么事件会改变我的状态？"，那么行为树是"我现在应该执行**哪一个计划**？"

一棵行为树看起来像这样：

```
                        ┌──────────┐
                        │ Selector │  ← 根节点：按顺序尝试子节点
                        │ (根)     │
                        └────┬─────┘
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
      ┌───────────┐  ┌───────────┐  ┌───────────┐
      │ 战斗子树  │  │  搜索     │  │  巡逻      │
      │(高优先级) │  │  子树     │  │  子树      │
      └───────────┘  └───────────┘  └───────────┘
```

- **根节点**通常是一个 Selector（选择器），尝试以从左到右的顺序执行子节点。一旦左侧子树成功（返回 Success），右侧子树根本不会被评估。
- **每个子树**可以进一步展开为 Sequence（顺序节点）、Decorator（装饰器）、或 Leaf（叶子节点——实际执行动作或检查条件）。
- **叶子节点**是树的"末端"——它们执行具体动作（`FireWeapon`、`MoveTo`、`PlayAnimation`）或检查条件（`HasTarget`、`IsInRange`、`IsAlive`）。

整个树的执行过程就像一个**树形计划执行器**：从根开始，逐级沿树向下传递"执行信号"（tick），每个节点根据自身类型和孩子节点的返回结果决定自己的返回值，最终返回给上一层，直到根节点。

### Tick 机制：深度优先遍历与三值返回

行为树的核心执行单元是 **Tick**。一次 Tick 从一个指定节点（通常是根节点）开始，进行深度优先遍历。

每个节点在收到 Tick 后，必须返回以下三种状态之一：

| 返回状态 | 含义 | 典型使用场景 |
|----------|------|-------------|
| **Success** | 节点的任务已完成 | `HasTarget` 条件为真，`PlayAnimation` 播放完毕 |
| **Failure** | 节点的任务无法完成（暂时或永久） | `IsInRange` 条件为假，`Pathfind` 找不到路径 |
| **Running** | 节点的任务正在执行中，尚未完成 | `MoveTo` 正在移动中（跨越多帧），`Attack` 正在播放攻击动画 |

**Success 和 Failure** 是终端状态——它们向上传播，影响父节点的决策。**Running** 是特殊的：它表示"我还没完，请下帧继续 tick 我"。

遍历过程如下：

```
Tick 从根节点 Selector 开始:

  根 Selector 收到 tick
  ├─→ tick 第一个子节点 (Sequence: "战斗")
  │    ├─→ tick 第一个子节点 (Condition: HasTarget)
  │    │    └─→ 返回 Success (有目标)
  │    ├─→ tick 第二个子节点 (Condition: IsInRange)
  │    │    └─→ 返回 Success (在射程内)
  │    └─→ tick 第三个子节点 (Action: Attack)
  │         └─→ 返回 Running (正在攻击中，需要多帧)
  │    ← Sequence 返回 Running (因为最后一个孩子还在 Running)
  ← 根 Selector 返回 Running (第一个子树在 Running)
```

下一帧：
- Tick 再次从根开始。
- Selector 继续 tick 它的第一个子树（战斗 Sequence）。
- Sequence 跳过已返回 Success 的前两个孩子（或从头 tick，取决于实现），直接 tick `Attack` 节点。
- `Attack` 返回 Running。整个路径保持 Running。

当攻击完成时：
- `Attack` 返回 Success。
- Sequence 所有孩子都返回了 Success → Sequence 返回 Success。
- Selector 的第一个子树返回 Success → Selector 返回 Success。
- 树执行完毕（或者根节点根据策略决定下一帧重头开始）。

### Tick 与 FSM Update 的本质区别

这是理解行为树最重要的分水岭。如果你从 FSM 转过来，最大的思维转换就在这里：

| 维度 | FSM | 行为树 |
|------|-----|--------|
| 状态 | **有状态**：系统处于一个确定的状态，状态存储了执行进度 | **无状态**（per-tick）：系统不记忆"上次在哪"。每帧从头评估 |
| 决策 | 事件驱动：收到事件 → 查转移表 → 切换状态 | 条件驱动：每帧从根遍历，条件在遍历过程中被评估 |
| 执行进度 | 隐含在"当前状态"中。在 `Attack` 状态中 = 正在攻击 | 通过 Running 返回值显式保留。树"停在"返回 Running 的节点上 |
| 中断 | 显式转移：必须有 `Attack → Retreat` 这样一条边 | 每帧重新评估：树自然"绕过"不再满足条件的子树 |
| 优先级 | 编码在转移条件中，分散在各处 | 编码在树结构中（左 → 右），集中可见 |

**stateless per-tick** 这个特性是最容易被误解的。行为树**看起来**像是"停在某个节点上"有状态——确实，大多数实现会缓存"上次在哪"，但这纯粹是性能优化。正确的理解是：**每帧行为树从头重新考虑"现在该做什么"，如果上次的选择仍然最优，树自然会 tick 到同一个节点。如果新的条件出现（如血量降低），树会自动选择更高优先级的路径。**

用一个例子说明区别：

**场景**：敌人在攻击玩家，但血量突然降到危险阈值。

**FSM 做法**：`Attack` 状态中每帧检查 `health < threshold`，如果为真，`TransitionTo(Flee)`。这是一条**显式编码的转移边**。如果后来你加了一个 `Berserk` 状态（低血量时反而更激进），你需要修改 `Attack` 状态的转移规则，加入"如果角色类型是 Berserker，则走另一条边"。

**BT 做法**：树的结构是这样——

```
Selector
├── Sequence (最高优先级: 生存)
│   ├── Condition: IsHealthCritical?
│   └── Action: Flee
├── Sequence (中优先级: 战斗)
│   ├── Condition: HasTarget?
│   ├── Condition: IsInRange?
│   └── Action: Attack
└── Action: Idle (最低优先级: 空闲)
```

每帧从根 Selector 开始。正常情况下，`IsHealthCritical?` 返回 Failure，Select 跳到下一个子树——战斗 Sequence 执行 `Attack`。一旦血量降低，**下一帧** `IsHealthCritical?` 返回 Success → Flee 被 tick。不需要显式的"从 Attack 到 Flee 的转移边"。树结构本身就是优先级。

这个设计的强大之处在于：**新增行为只需要在树中插入一个新的子树**。要加入 Berserker 的低血量突袭模式？在 Flee 子树之前插入一个条件判断即可——不需要修改攻击、撤退或空闲的任何代码。

### 基本节点类别

行为树节点分为三大类：

#### Composite（组合节点）

组合节点有多个子节点，根据策略决定 tick 哪些子节点以及以什么顺序。

| 类型 | 策略 | 类比 |
|------|------|------|
| **Selector**（选择器/优先级节点） | 按顺序 tick 子节点，**只要一个返回 Success/Running 就停止**。全 Failure 则返回 Failure | if-else if-else 链 |
| **Sequence**（顺序节点） | 按顺序 tick 子节点，**只要一个返回 Failure 就停止**。全 Success 则返回 Success | AND 链接的一组操作 |
| **Parallel**（并行节点） | 同时 tick 多个子节点，根据策略决定成功条件（如"全部成功"、"任意一个成功"） | 同时进行多个操作 |

**Selector 的执行语义**：

```
Selector 收到 tick:
  for each child (从左到右):
    status = child.Tick()
    if status == Success:  return Success   // 找到一个能执行的，停止
    if status == Running:  return Running   // 正在执行，停止
    // status == Failure:  继续下一个
  return Failure  // 所有孩子都失败了
```

**Sequence 的执行语义**：

```
Sequence 收到 tick:
  for each child (从左到右):
    status = child.Tick()
    if status == Failure:  return Failure   // 一个失败，全部失败
    if status == Running:  return Running   // 正在执行，停止
    // status == Success:  继续下一个
  return Success  // 所有孩子都成功了
```

#### Decorator（装饰器节点）

装饰器只有一个子节点，用于修改或约束其行为。它像一个"条件门"。

| 类型 | 作用 | 例子 |
|------|------|------|
| **Condition** / **Blackboard Condition** | 检查一个条件，条件为真时 tick 子节点，为假时返回 Failure | `HasTarget`、`IsHealthLow` |
| **Inverter**（取反） | 反转子节点的返回值：Success→Failure, Failure→Success | 把"敌人在视野内"变成"敌人不在视野内" |
| **Repeat** | 重复执行子节点，直到某个条件满足 | "巡逻" = 重复"沿路径点移动" |
| **Timeout** / **Limit** | 限制子节点的执行时间或次数 | "搜索玩家"最多持续 5 秒 |
| **UntilSuccess** / **UntilFailure** | 重复 tick 子节点直到它返回 Success/Failure | "不断尝试寻找掩护位置直到成功" |
| **ForceSuccess** / **ForceFailure** | 无论子节点返回什么，总是返回 Success/Failure | 记录日志节点——不管记录成功与否，不影响树 |

#### Leaf（叶子节点）

叶子节点没有子节点，是树的末端。

| 类型 | 作用 | 返回值语义 |
|------|------|-----------|
| **Action** | 执行一个动作，通常涉及多帧执行 | `Running` = 执行中，`Success` = 完成，`Failure` = 无法执行 |
| **Condition** | 检查一个布尔条件（只读，无副作用） | `Success` = 条件为真，`Failure` = 条件为假，永不返回 `Running` |

**关键区别**：`Condition` 节点 MUST NOT 有副作用。检查"敌人在视野内"不应移动实体、修改状态或触发事件。这保证了行为树的"每帧从根重新评估"在语义上是安全的——不管 condition 被 tick 多少次，游戏状态不变。违反这个规则是行为树 bug 的第一大来源（见"常见陷阱"）。

### 可视化表示与读法

行为树通常表示为倒置的树（根在顶部，叶在底部）：

```
                              ┌──────────┐
                              │ Selector │
                              │   (?)    │
                              └────┬─────┘
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
            ┌────────────┐ ┌────────────┐ ┌────────────┐
            │  Sequence  │ │  Sequence  │ │   Action   │
            │    (→)     │ │    (→)     │ │   Patrol   │
            └─────┬──────┘ └─────┬──────┘ └────────────┘
       ┌──────────┼──────────┐   │
       ▼          ▼          ▼   ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Condition │ │ Condition │ │  Action  │ │ Condition │
│HasTarget? │ │IsInRange? │ │  Attack  │ │HasTarget? │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

读法约定：

- **Selector 节点**通常标为 `?` 或写全称。
- **Sequence 节点**通常标为 `→`。
- **Condition 节点**通常为菱形或椭圆。
- **Action 节点**通常为矩形。

从左到右读优先级递减，从上到下读执行顺序。

**如何通过阅读树来分析 AI 行为**：

1. 从根节点开始，它是 Selector 还是 Sequence？
2. 如果是 Selector → AI 在"多个可选计划中选一个"，从左到右优先级递减。
3. 如果是 Sequence → AI 在"按顺序执行一组步骤"。
4. 从左到右依次追踪每个子树：当前条件下哪个会成功？哪个会 Running？
5. 如果最左边的子树失败 → 自动 fall-through 到下一个。

这棵树的行为逻辑：**"有目标且在射程内 → 攻击；有目标但不在射程内 → 移动到目标；都没有 → 巡逻。"**

### Tick 频率：每帧 vs 事件驱动 vs 自传播

行为树的 tick 频率有三种常见策略：

| 策略 | 机制 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|---------|
| **每帧 tick** | 游戏循环每帧调用 `root.Tick()` | 实现简单，响应最快 | CPU 开销大（即使什么都不做也要遍历） | 玩家角色、Boss AI、关键 NPC |
| **事件驱动** | 外部事件（如感知到敌人）触发 tick | 闲置时零开销 | 响应可能滞后；需要仔细设计哪些事件触发重新评估 | 大量非关键 NPC、环境生物 |
| **固定频率** | 每 N 帧 tick 一次（如每 3 帧），但用 `Running` 节点的子树可以在帧间自传播 | 平衡开销与响应性 | 实现更复杂 | 大规模 RTS 单位、群组 AI |
| **自传播** | tick 传播到 `Running` 节点后，后续帧只 tick 从该节点往下的子树，不重新从根遍历 | 大幅减少 CPU 开销 | 失去了"每帧重新评估"的优先级中断能力 | 需要优化的大规模场景，需配合事件唤醒 |

**实际混合策略**：

绝大多数生产级行为树同时使用多种策略：

```
主循环 (每帧):
  if (shouldReevaluate):     // 由事件或计时器决定
    root.Tick()              // 从根重新评估
  else:
    lastRunningNode.Tick()   // 只 tick 上次 Running 的节点

事件回调:
  OnHealthChanged(health):
    if (health < threshold):
      shouldReevaluate = true  // 强制下一帧从根重新评估
```

这种设计在 UE5 的 Behavior Tree 系统中叫做 **Observer Aborts** —— Decorator 可以注册事件监听，相应事件触发时强制从该 Decorator 的父节点重新评估。

### 入门示例：门卫的行为树

让我们用一棵简单但完整的行为树来理解上述所有概念。

**需求**：一个门卫 NPC。如果有人试图闯入 → 拦截；如果有可疑人物 → 盘问；否则 → 站岗。

**行为树**：

```
                            ┌──────────┐
                            │ Selector │ (根)
                            │   (?)    │
                            └────┬─────┘
               ┌─────────────────┼─────────────────┐
               ▼                 ▼                 ▼
       ┌────────────┐    ┌────────────┐    ┌────────────┐
       │  Sequence  │    │  Sequence  │    │   Action   │
       │    (→)     │    │    (→)     │    │  StandGuard│
       └─────┬──────┘    └─────┬──────┘    └────────────┘
      ┌──────┼──────┐    ┌─────┼──────┐
      ▼      ▼      ▼    ▼     ▼      ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Condition │ │  Action  │ │  Action  │ │ Condition │ │  Action  │ │  Action  │
│IsIntruder│ │ShoutAlert│ │Intercept │ │IsSuspicious│ │Question  │ │WarnAnd   │
│   ?      │ │          │ │          │ │    ?      │ │          │ │Release   │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

**执行追踪（假设一个可疑人物靠近）**：

```
帧 N:
  Selector tick 子节点 1 (拦截 Sequence):
    IsIntruder? → Failure             (不是闯入者)
    Sequence 1 返回 Failure
  Selector tick 子节点 2 (盘问 Sequence):
    IsSuspicious? → Success           (是可疑人物)
    Question → Running                (正在询问中...)
    Sequence 2 返回 Running
  Selector 返回 Running

帧 N+1 到 N+30:
  (假设实现为从 Running 节点继续):
  继续 tick Sequence 2 的 Question 节点
  Question → Running

帧 N+31:
  Question → Success                  (询问完毕)
  WarnAndRelease → Running            (警告并放行...)
  Sequence 2 返回 Running

帧 N+31 到 N+50:
  继续 tick WarnAndRelease

帧 N+51:
  WarnAndRelease → Success
  Sequence 2 返回 Success
  Selector 返回 Success
  树执行完毕 → 下一帧重新从根开始，StandGuard 成为唯一可选
```

这棵树清晰地表达了门卫的决策逻辑，而且可以轻松扩展——比如在拦截子树之前插入一个"检测到武器 → 呼叫增援"的 Sequence，不需要修改任何已有节点。

---

## 2. 代码示例

### 示例 A：伪代码行为树框架

下面是一个最小但完整的行为树框架，包含 Selector、Sequence、Condition、Action：

```cpp
// ============================================================
// BT Framework: Minimal behavior tree in C++ style pseudocode
// ============================================================

// ---- 1. Node return status ----
enum class BTStatus {
    Success,
    Failure,
    Running
};

// ---- 2. Base node ----
class BTNode {
public:
    virtual ~BTNode() = default;

    // Tick returns one of {Success, Failure, Running}.
    // The tick is stateless: the same call with the same world state
    // MUST produce the same result.  Any "memory" (like "where am I
    // in my Sequence children") lives in the node, NOT in the tree.
    virtual BTStatus Tick() = 0;

    // Optional lifecycle (called by parent or tree runner):
    virtual void OnEnter() {}
    virtual void OnExit() {}
};

// ---- 3. Composite: Selector ----
class Selector : public BTNode {
    std::vector<std::unique_ptr<BTNode>> m_children;
    size_t m_currentIndex = 0; // carried across frames → Running behavior

public:
    void AddChild(std::unique_ptr<BTNode> child) {
        m_children.push_back(std::move(child));
    }

    BTStatus Tick() override {
        // Resume from the child that returned Running last frame,
        // or fall through to subsequent children.
        for (; m_currentIndex < m_children.size(); ++m_currentIndex) {
            BTStatus s = m_children[m_currentIndex]->Tick();
            if (s == BTStatus::Success) {
                m_currentIndex = 0; // reset for next root tick
                return BTStatus::Success;
            }
            if (s == BTStatus::Running) {
                return BTStatus::Running; // resume here next tick
            }
            // Failure → try next child
        }
        m_currentIndex = 0;
        return BTStatus::Failure; // all children failed
    }

    void OnEnter() override { m_currentIndex = 0; }
};

// ---- 4. Composite: Sequence ----
class Sequence : public BTNode {
    std::vector<std::unique_ptr<BTNode>> m_children;
    size_t m_currentIndex = 0;

public:
    void AddChild(std::unique_ptr<BTNode> child) {
        m_children.push_back(std::move(child));
    }

    BTStatus Tick() override {
        for (; m_currentIndex < m_children.size(); ++m_currentIndex) {
            BTStatus s = m_children[m_currentIndex]->Tick();
            if (s == BTStatus::Failure) {
                m_currentIndex = 0;
                return BTStatus::Failure; // one fails → all fail
            }
            if (s == BTStatus::Running) {
                return BTStatus::Running; // resume here next tick
            }
            // Success → advance to next child
        }
        m_currentIndex = 0;
        return BTStatus::Success; // all children succeeded
    }

    void OnEnter() override { m_currentIndex = 0; }
};

// ---- 5. Leaf: Condition ----
// Conditions MUST be side-effect-free.
class Condition : public BTNode {
    std::function<bool()> m_predicate;

public:
    explicit Condition(std::function<bool()> pred) : m_predicate(std::move(pred)) {}

    BTStatus Tick() override {
        return m_predicate() ? BTStatus::Success : BTStatus::Failure;
    }
};

// ---- 6. Leaf: Action ----
// Actions represent in-game behavior that may span multiple frames.
// m_operation returns Running while underway, Success on completion.
class Action : public BTNode {
    std::function<BTStatus()> m_operation;

public:
    explicit Action(std::function<BTStatus()> op) : m_operation(std::move(op)) {}

    BTStatus Tick() override {
        return m_operation();
    }
};

// ---- 7. Tree runner ----
class BehaviorTree {
    std::unique_ptr<BTNode> m_root;

public:
    explicit BehaviorTree(std::unique_ptr<BTNode> root) : m_root(std::move(root)) {}

    void Tick() {
        m_root->Tick(); // ignored return; root drives everything
    }
};
```

**关键设计决策说明**：

- **`m_currentIndex` 跨帧保持**。这是 Sequence 和 Selector "记忆"当前活跃子节点的机制。虽然行为树在概念上是"每帧重评估"的，但 Running 状态要求我们从上次中断的地方继续。
- **OnEnter 重置 `m_currentIndex`**。如果你选择每帧从根重新评估（根 Selector 每帧调用 `OnEnter`），索引会重置，树会重新从第一个孩子开始。这是实现"重新评估"的正确位置。
- **Condition 是纯函数**。它只读取世界状态，不修改。这保证了无论 Condition 被 tick 多少次，语义保持一致。
- **`Tick()` 是递归的**。深度优先遍历天然由递归实现，简单、不出错。对于深度超过 100 的极端情况，可以用显式栈替代递归，但绝大部分游戏行为树深度不超过 20。

### 示例 B：手动执行追踪

考虑以下树：

```
Selector                           (根)
├── Sequence A
│   ├── Condition: enemyInSight?
│   └── Action: Shoot
└── Sequence B
    ├── Condition: hasPatrolPath?
    └── Action: Patrol
```

**场景设定**：敌人不在视野中。Patrol 动作每帧返回 Running（巡逻是持续行为），永远不会"完成"——它在树中的角色就是一个"兜底"行为，只在没有任何更高优先级的行为可执行时运行。

**逐帧追踪**：

```
帧 1: 初始状态 — enemyInSight = false, hasPatrolPath = true
─────────────────────────────────────────────────────────────
  Selector::Tick()
    child 0 (Sequence A):
      Sequence A::Tick()
        child 0 (enemyInSight?):
          Condition::Tick() → Failure       // 没有敌人
        Sequence A 返回 Failure             // 第一个孩子就失败了
    Selector 继续下一个孩子
    child 1 (Sequence B):
      Sequence B::Tick()
        child 0 (hasPatrolPath?):
          Condition::Tick() → Success       // 有巡逻路径
        child 1 (Patrol):
          Action::Tick() → Running          // 正在巡逻...
        Sequence B 返回 Running             // Patrol 还在跑
    Selector 返回 Running                   // 停在 Sequence B

帧 2: 仍然没有敌人; Selector 从 m_currentIndex=1 继续
─────────────────────────────────────────────────────────────
  Selector::Tick()
    child 0 (Sequence A):                  // 如果实现为"每帧重评估"
      Sequence A::Tick()
        child 0: Condition::Tick() → Failure
      Sequence A 返回 Failure
    child 1 (Sequence B):
      Sequence B::Tick()
        child 0: Condition::Tick() → Success
        child 1: Action::Tick() → Running  // 继续巡逻
      Sequence B 返回 Running
    Selector 返回 Running

帧 3-50: 同上 — Patrol 持续 Running
─────────────────────────────────────────────────────────────

帧 51: 敌人进入视野! enemyInSight = true
─────────────────────────────────────────────────────────────
  Selector::Tick()
    child 0 (Sequence A):
      Sequence A::Tick()
        child 0: Condition::Tick() → Success  // 看到敌人!
        child 1 (Shoot):
          Action::Tick() → Running            // 开火... (Shoot 可能持续多帧)
      Sequence A 返回 Running
    Selector 返回 Running
    // Sequence B 完全被跳过 — Selector 在第一个 Running 处停止

帧 52: 继续战斗
─────────────────────────────────────────────────────────────
  Selector::Tick()
    child 0 (Sequence A): Sequence A 从 Shoot 继续 → Running
    Selector 返回 Running

帧 60: 敌人被消灭; enemyInSight 再次为 false
─────────────────────────────────────────────────────────────
  Selector::Tick()
    child 0 (Sequence A):
      Sequence A::Tick()
        child 0: Condition::Tick() → Failure  // 没有敌人了
      Sequence A 返回 Failure
    child 1 (Sequence B):
      Sequence B::Tick()
        child 0: hasPatrolPath? → Success
        child 1: Patrol → Running             // 自然回归巡逻
      Sequence B 返回 Running
    Selector 返回 Running
```

注意：从 Shoot 回到 Patrol **不需要任何显式的转移代码**。当 `enemyInSight?` 条件变为 false 时，Sequence A 自动失败，Select 自然 fall-through 到 Sequence B。这就是行为树"自动优先级"的威力。

### 示例 C：完整敌人 AI 行为树

```cpp
// ============================================================
// Pseudocode: Complete enemy AI behavior tree
// ============================================================

BehaviorTree BuildEnemyBT() {
    auto root = std::make_unique<Selector>();   // Priority-based plan selection

    // ---- Priority 1: Attack while in range ----
    {
        auto attackSeq = std::make_unique<Sequence>();
        attackSeq->AddChild(std::make_unique<Condition>([&]() {
            return ai.HasTarget();              // do we have a target?
        }));
        attackSeq->AddChild(std::make_unique<Condition>([&]() {
            return ai.IsInRange();              // are we close enough?
        }));
        attackSeq->AddChild(std::make_unique<Action>([&]() {
            return ai.Attack();                 // multi-frame attack action
        }));
        root->AddChild(std::move(attackSeq));
    }

    // ---- Priority 2: Move toward target ----
    {
        auto moveSeq = std::make_unique<Sequence>();
        moveSeq->AddChild(std::make_unique<Condition>([&]() {
            return ai.HasTarget();              // have a target...
        }));
        moveSeq->AddChild(std::make_unique<Action>([&]() {
            return ai.MoveToTarget();           // ...but not in range yet
        }));
        root->AddChild(std::move(moveSeq));
    }

    // ---- Priority 3: Default — patrol ----
    {
        root->AddChild(std::make_unique<Action>([&]() {
            return ai.Patrol();                 // lowest priority, always runs if nothing else does
        }));
    }

    return BehaviorTree(std::move(root));
}
```

**这个 AI 的完整行为逻辑**：

1. 有目标且在攻击范围内 → 攻击。
2. 有目标但不在攻击范围内 → 向目标移动。
3. 没有目标 → 巡逻。

要新增"低血量逃跑"？只需在 Priority 1 之前插入：

```cpp
// ---- Priority 0: Flee when low health ----
{
    auto fleeSeq = std::make_unique<Sequence>();
    fleeSeq->AddChild(std::make_unique<Condition>([&]() {
        return ai.IsHealthLow();
    }));
    fleeSeq->AddChild(std::make_unique<Action>([&]() {
        return ai.Flee();
    }));
    root->AddChild(std::move(fleeSeq));  // Insert at position 0 = highest priority
}
```

不需要修改 `Attack`、`MoveToTarget`、`Patrol` 任何一个节点。这是行为树"组合优于侵入"设计的直接体现。

---

## 3. 练习

### 练习 1：绘制并追踪守卫 NPC 的行为树

**需求**：设计一个守卫 NPC，行为逻辑如下：

1. 默认在指定区域巡逻。
2. 发现玩家进入视野范围 → 追击玩家。
3. 追击中玩家进入攻击范围 → 攻击。
4. 攻击中玩家脱离视野超过 3 秒 → 回到巡逻。
5. （延伸）如果血量低于 30% → 逃跑。

**任务**：

(A) 用纸笔绘制这棵行为树。写出每个节点（Composite/Decorator/Leaf）的类型和名称。

(B) 用类似"示例 B"的格式，手动追踪以下时间线的 10-15 帧：
   - 帧 1-5: 守卫在巡逻（没有玩家）
   - 帧 6: 玩家进入视野（但不在攻击范围）
   - 帧 7-9: 守卫追击
   - 帧 10: 玩家进入攻击范围
   - 帧 11-13: 守卫攻击
   - 帧 14: 玩家脱离视野
   - 帧 15-17: 3 秒超时后，守卫回到巡逻

(C) 标注每个 tick 中哪些节点被访问，每个节点的返回值是什么。

**参考答案要点**：

- 根节点应为 Selector。
- "逃跑"子树应在"战斗"子树之前（Selector 中的更高优先级）。
- "脱离视野 3 秒"需要用 Decorator（Timeout 或自定义 Cooldown/UntilFailure 包装器）。
- 如果 `HasTarget` 为 false，战斗 Sequence 失败 → Selector fall-through 到巡逻 Action。
- 如果 `HasTarget` 为 true 但 `IsInRange` 为 false，移动到目标的 Action 返回 Running。

### 练习 2：与 FSM 对比——复杂性度量

**任务**：

将练习 1 的行为树**翻写为等价行为的 FSM**（用 Tutorial 01 中介绍的转移图表示）。行为包括：`Patrol`、`Chase`、`Attack`、`Flee`。

完成后，对比以下指标：

| 指标 | FSM | BT |
|------|-----|----|
| 状态/节点数量 | ？ | ？ |
| 转移边数量（FSM）/ 节点连接数（BT） | ？ | ？ |
| 需要显式处理的中断/回归逻辑 | ？ | ？ |
| 新增"低血量逃跑"需要修改多少地方 | ？ | ？ |
| 新增"警惕状态"（发现可疑但未确认的玩家）需要修改多少地方 | ？ | ？ |

**参考答案要点**：

- FSM 至少需要 4 个状态 + 约 8-10 条转移边（包括"攻击中丢失目标→搜索"、"追击中玩家消失→巡逻"、"任意状态血量低→逃跑"等）。
- FSM 每条跨状态转移边都是手动维护的。丢一条边 = 一个 bug。
- BT 用 Selector 的 fall-through 自动处理"条件不满足时做什么"，不需要显式转移。
- 新增行为：FSM 需要修改每个相关状态的转移表（可能 4-5 处）。BT 只需要在 Selector 中插入一个新子树（1 处）。
- 但当 BT 中需要"从任意状态可被中断"的行为时（类似 FSM 的 Any-State Transition），需要在每个子树中都加入条件判断，反而可能繁琐。

### 练习 3（可选）：RTS 单位的 BT 设计

**需求**：设计一个 RTS 工人单位的 AI，需要处理：

- 采集资源（Gather）
- 建造建筑（Build）
- 受到攻击时逃跑到安全位置（Retreat）
- 基地被攻击时参与维修（Repair）
- 空闲时回到待命点（Idle）

**任务**：

(A) 绘制完整的行为树。

(B) 讨论以下问题（每个 2-3 句即可）：

1. "受到攻击时逃跑"应该放在树的哪个位置？为什么？
2. "基地被攻击时维修"和"自己受攻击时逃跑"哪个优先级更高？为什么？
3. 如果在 FSM 中实现这个 AI，大概需要多少状态？行为树用多少节点？
4. 树中是否有"自己受攻击但基地也在被攻击"的冲突？你如何处理？
5. 这个场景下 BT 相比 FSM 的最大优势是什么？最大劣势是什么？

---

## 4. 扩展阅读

### 必读：Halo 2 的起源演讲

- **Damian Isla. (2005).** *"Managing Complexity in the Halo 2 AI."* GDC 2005. — 行为树在游戏中的奠定性演讲。Isla 讲述了 Halo 2 的 AI 系统如何从 Halo 1 的 FSM 演进而来，以及他们如何解决多行为抢占、优先级管理和设计迭代的问题。**这是理解行为树"为什么存在"的第一手资料。**GDC Vault 上可找到录音和幻灯片。

- **Damian Isla. (2006).** *"Handling Complexity in the Halo 2 AI."* (Extended version with additional technical details.) 包含了比 GDC 演讲更细节的技术讨论，特别是 impulse 行为和树评估流程。

### 行为树理论与实践

- **Chris Simpson. (2014).** *"Behavior Trees for AI: How They Work."* Gamasutra / Game Developer. — 一篇经典的行为树入门文章，从零开始构建一棵行为树，配有清晰的图解和伪代码。适合作为本文的补充阅读。

- **Mikael Hedberg. (2013).** *"Behavior Trees: An Introduction."* — 从工业机器人控制到游戏 AI 的行为树跨学科背景介绍。

- **Alex J. Champandard. (2007).** *"Understanding Behavior Trees."* AiGameDev.com. — Champandard 是游戏 AI 社区的核心人物之一，他的系列文章深入讨论了行为树的语义和历史，以及它与 GOAP、效用系统的关系。

- **Bjoern Knafla.** *"Behavior Trees for Next-Gen Game AI."* — Knafla 的系列博客文章涵盖了行为树的性能分析、并行节点语义、大型树的调试技术等进阶主题。对于要实装生产级 BT 的人来说，他的并行节点分析尤其有价值。

### 书籍章节

- **Rabin, Steve (ed.).** *Game AI Pro: Collected Wisdom of Game AI Professionals.* — 多卷本系列。建查找以下章节：
  - *"The Behavior Tree Starter Kit"* — 实用的 BT 框架设计指南。
  - *"An Introduction to Behavior Trees"* — 补充的基础理论。
  - *"Behavior Trees for Next-Gen Game AI"* — Bjoern Knafla 在 Game AI Pro 中的版本，涵盖更多结构化内容。

- **Millington, Ian & Funge, John.** *Artificial Intelligence for Games* (2nd/3rd Edition). — 第 5 章对行为树有严谨的理论介绍（虽然书名含"AI"，但本书的核心受众是 gameplay 工程师而非 AI 研究者，内容扎实且无学术腔）。

- **DaGraca, Marco & Canniff, Mike.** *"The Simplest AI Trick in the Book: Reactive AI Through Behavior Trees."* — 讨论如何用极简的行为树实现高度反应性的 NPC，尤其适合手游或独立游戏开发。

### 源码参考

- **Unreal Engine Behavior Tree.** `Engine/Source/Runtime/AIModule/` — UE 的原生行为树系统是工业级 BT 实现的最佳参考。从 `UBTNode`、`UBTCompositeNode`、`UBTTaskNode` 的源码中可以直接看到 Selector、Sequence、Decorator 的生产级实现。UE5 还引入了 `StateTree`，融合了 BT 和 HSM 的设计。

- **O3DE (Open 3D Engine).** Behavior Context / Script Canvas — O3DE 的行为上下文系统提供了另一个开源的 BT 实现参考。

---

## 常见陷阱

### 1. 把行为树当成决策树（Decision Tree）

**症状**：用 Condition 节点构建一棵"纯判断树"——所有节点都是 Condition，没有 Action。树的返回值被解释为"当前应该处于哪个状态"。

**为什么是错的**：

行为树和决策树是两个完全不同的东西。决策树是**分类器**：给定输入，输出一个类别。行为树是**执行器**：它在遍历过程中**执行动作**。行为树的叶子节点不仅仅是"回答一个问题"，而是**驱动游戏行为**——移动实体、播放动画、造成伤害。

一个正确的行为树中，Action 节点会返回 Running 来告诉父节点"我还在执行"。决策树没有"执行中"这个概念。把 BT 当决策树用意味着你放弃了 BT 最核心的能力——多帧行为的协调。

### 2. Condition 中有副作用

**症状**：在 Condition 节点的检查函数中修改游戏状态——比如 `Condition("HasTarget?")` 内部调用了 `FindNearestTarget()` 并改变了 AI 的当前目标。

**为什么是错的**：

行为树的语义依赖于"每帧重新评估时条件可以安全地任意次重复调用"。如果 Condition 有副作用，每次重新评估都会改变游戏状态，导致行为树的行为不可预测——这次 tick 可能和上次 tick 有完全不同的条件结果，不是因为世界变了，而是因为你自己的 Condition 改变了世界。

**正确做法**：将"查找目标"做成一个 Action 节点，放在 Sequence 的最前面；将"检查是否有已找到的目标"做成 Condition 节点。两者分离：

```
Sequence
├── Action: FindTarget   ← 有副作用（更新内部目标引用）
├── Condition: HasTarget  ← 无副作用（只读检查）
└── Action: Attack
```

### 3. 无限 Tick 循环

**症状**：行为树的某个节点在本帧内触发了需要多帧才能完成的操作，但同步地在同一帧内反复 tick 直到完成，导致游戏逻辑在一帧内"快进"。

**为什么是错的**：

Tick 的语义是**单帧增量推进**。如果你的 `MoveTo` Action 在单次 Tick 内移动了整个路径，你等于在让 AI 瞬移。更隐蔽的问题是：如果 `MoveTo` 在同一帧内 tick 了子节点并期望子节点也同步完成，你实际上破坏了"一帧一个 tick"的契约。

**正确做法**：Action 节点的 Tick 方法每次调用只推进一帧的工作量。移动只移动一帧的距离，攻击只推进一帧的动画。返回 Running 表示"没完"。

### 4. 把行为树当成有状态的

**症状**：在 Action 节点中存储"我在做什么"的状态信息，并期望下次 tick 来到同一节点时这些状态仍然有效。然后惊讶地发现，当某帧树走了不同的路径后（因为条件变了），之前的状态丢失了。

**为什么是错的**：

行为树的 stateless-per-tick 特性意味着它不保证"下次 tick 时我还在这个节点上"。你的 Attack 节点的 m_currentFrame 变量在下一次 Tick 时可能根本不会被用到——因为在那之前 Selector 可能选择了别的子树。

**正确做法**：如果一个行为需要在切换走后再回来时"记住进度"，将状态存储在 Blackboard（外部键值存储）或 AI 组件的成员变量中，而不是行为树节点本身。行为树节点可以读取 Blackboard 中的进度来恢复执行。

### 5. 过早优化树的深度

**症状**：因为"担心性能"，把本该是一棵 3-4 层深的树拍平为 1-2 层，用复杂的 Condition 判断替代树结构的优先级语义。

**为什么是错的**：

行为树的 CPU 开销在绝大多数场景下可以忽略不计。一棵 20 节点的树，即使每帧完整遍历（包括已返回 Success 的节点），在现代 CPU 上通常 < 0.01ms。行为树的性能瓶颈几乎永远不在遍历本身，而在叶子节点的实际工作上（寻路、物理查询、动画计算）。

**正确做法**：先把树的语义写对、写清楚。用层次结构表达优先级、组合关系和意图。优化是最后一步——只有当 profiler 告诉你行为树遍历是热点时，再引入"子树休眠"、"Running 节点自传播"、"事件驱动唤醒"等优化。

过早拍平行为树会直接抹杀 BT 最大的设计优势——可读性和可维护性。一棵被拍平的 BT 不如直接写 FSM。

### 6. Selector 和 Sequence 的语义混淆

**症状**：在 Selector 中放一个永远返回 Running 的节点作为第一个孩子，导致所有后续子树永远不被评估。

**为什么是错的**：

Selector 在遇到第一个返回 Success 或 Running 的子节点时停止。如果你的"巡逻" Action 永远返回 Running，那么 Selector 中 Patrol 之前的所有子树如果不满足条件（Failure），就会掉到最后执行 Patrol。但只要 Patrol 在 Running，下一帧如果你做"重新从根评估"，Selector 会在 Patrol 之前的所有子节点上再次尝试。这是正确的。

但如果**不重新从根评估**（即从 Running 节点继续 tick），Selector 会卡在 Patrol 永远不重新评估前面的子树——AI 永远不会对新的刺激做出反应。

**正确做法**：选择合适的重评估策略。如果你的树依赖"任何时候有更高优先级的行为出现就抢占当前行为"，必须确保每帧从根重新评估——要么全树 tick，要么至少从 Selector 层级重新评估。这正是 UE5 的 Observer Aborts 解决的问题。
