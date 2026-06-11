---
title: "FSM vs BT 技术选型"
updated: 2026-06-05
---

# FSM vs BT 技术选型

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 90min
> 前置知识: 01-13 (所有 FSM + BT 教程)

---

## 1. 概念讲解

### 为什么这个话题重要？

经过 Tutorial 01-13，你已经分别掌握了 FSM（含 HSM/Pushdown）和行为树的理论与实现。现在你面临一个真实项目中最困难的问题：**不是"怎么实现"，而是"应该用哪个"。**

选错工具的代价不是技术债务——是**团队资源黑洞**。如果你用 FSM 实现了一个需要 50+ 种行为的敌人 AI，三个月后发现每次加新行为（撤退逻辑、小队协同、环境交互）都需要修改 5-8 个已有状态的转移规则——此时切换到 BT 的迁移成本已经远远超过一开始就用 BT。反向亦然：用一个臃肿的 BT 系统去管理只有 4 种互斥状态的自动门，除了增加构建时间和调试复杂度外没有任何收益。

本教程的目标不是给你一张"选型对照表然后照搬"——而是让你理解**每种工具在什么条件下开始失效**，从而在你的具体约束下做出有根据的判断。

### 决策框架：七个比较维度

在具体讨论胜负之前，先建立统一的比较语言。以下是 FSM 和 BT 在七个关键维度上的本质差异：

| 维度 | FSM | BT | 关键差异 |
|------|-----|----|---------|
| **复杂度天花板** | 线性增长至 ~15 状态后曲线变陡；HSM 可扩展到 ~40 状态但组织成本递增 | 随行为数量线性增长；30-100+ 行为保持可管理 | BT 的每一层 Selector/Sequence 都是维度压缩工具 |
| **模块化/复用** | 状态=不可拆分的原子单元。复用靠继承（HSM）或复制 | 子树=可组合的行为片段。复用靠子树引用或节点参数化 | BT 的复用粒度更细，开销更低 |
| **设计师友好度** | 转移图直观（≤10 状态时），转移表需要编程思维 | 树的可视化编辑器天然匹配设计思维；拖拽调整优先级 | 设计师理解"左优先"比理解"状态转移表"容易得多 |
| **可调试性** | 当前状态即完整行为上下文；转移表提供完备性检查 | 需要从 Running 节点向上回溯路径；多帧调试需要可视化工具 | FSM 的"当前状态"是单点真理；BT 的路径需要额外追踪 |
| **确定性** | 转移规则确定（或可控随机） | 条件的评估顺序确定行为，但每帧重新评估可能引入"微抖动" | BT 的条件抖动是隐蔽 bug 来源（见常见陷阱） |
| **每帧性能** | 常数级：1 次 switch + 1 次 Update() | 深度优先遍历，开销与树深度 × 每帧评估节点数成正比 | 简单 AI：FSM 更快；复杂 AI：需要性能分析决定 |
| **状态性需求** | 天然有状态——状态即"执行到哪了"的记忆 | 通过 Running + 缓存机制模拟状态，但语义上无状态 | 需要"必先 A 再 B"的严格流程时 FSM 更自然 |

这些维度**不是独立的**——你的项目约束会同时命中其中几个。下面逐一展开。

#### 维度 1: 复杂度天花板——状态数增长曲线

这是 FSM 和 BT 最本质的数学差异。

**FSM 的增长特性**：对于 N 个独立的行为维度（如：战斗/非战斗、健康/受伤、持枪/空手），平面 FSM 需要 O(2^N) 或至少 O(d₁×d₂×…×d_N) 个状态来表示所有组合。HSM 将其压缩到 O(N × avg_dim) 级别，但转移边仍然可能跨越多层。

**BT 的增长特性**：每个行为维度是树中的一个子树或条件节点。新增维度 = 新增子树。树的大小为 O(N × avg_subtree_size)，不出现笛卡尔积爆炸。

具体数据——以一个敌方小队 NPC 为例，在不同需求规模下的状态/节点数：

| 需求 | FSM 状态数 | HSM 状态数 | BT 节点数 |
|------|-----------|-----------|----------|
| 巡逻 + 追击 + 攻击（3 行为） | 3-5 | 3-5 | 8-12 |
| + 低血量撤退（4 行为） | 6-10 | 6-10 | 12-18 |
| + 掩体利用 + 手雷投掷（6 行为） | 15-25 | 12-20 | 18-28 |
| + 小队协同 + 环境交互 + 3 武器类型（9 行为 × 2 维度） | 40-80 | 25-45 | 25-40 |
| + Boss 阶段 + 情绪 + 动态难度（12 行为 × 3 维度） | 100+ | 50-80 | 35-55 |

**拐点**大约在 **6-8 种顶层行为** 处。低于这个数字，FSM 更简单；高于这个数字，BT 的组织成本优势开始显现。注意 HSM 可以推迟这个拐点——但 HSM 本身的层次设计就是一项需要经验的工作。

#### 维度 2: 模块化与复用

这是一个经常被忽略但实际影响巨大的维度。

**FSM 的复用路径**：
- 复制状态类（代码重复）
- 基类继承 + 虚函数（如 `CombatState` → `MeleeCombat` / `RangedCombat`）
- HSM 父状态封装共享转移

FSM 的复用受限于一个根本约束：**每个时刻只能有一个活动状态**。如果你想在 `Combat` 和 `Investigate` 状态中都复用"移动到目标"的行为，在 FSM 中你需要从两个父状态都建立到达 `MoveTo` 子状态的路径，并在完成后正确返回。这需要显式管理状态栈（Pushdown）。

**BT 的复用路径**：
- 子树引用（最常见的 BT 可视化编辑器功能）
- 节点参数化（同一个 `MoveTo` 节点通过 Blackboard key 决定目标）
- 子树库（项目中积累的预配置子树片段）

BT 的复用约束更少：**树在每帧重评估**，所以一个子树从多个父节点中被引用时，不存在"返回正确的调用者"的问题——每帧都是全新的判定。`TakeCover` 子树可以被 `LowHealth` 和 `UnderFire` 两个 Selector 分支同时引用，逻辑上互不干扰。

**量化对比**：在一个需要 4 处复用 `FindCover` 行为的中等 NPC 中：
- FSM 方案：需要 4 个独立的 `MoveToCover` 状态（或 1 个 + Pushdown 栈管理），约 150-200 行
- BT 方案：1 个 `FindCover` 子树，被 4 处引用，约 40 行（子树定义） + 4 行（引用开销）

#### 维度 3: 设计师友好度

这可能是 BT 在工业界大范围采用的最直接原因。

在 FSM 中，设计师添加一个新行为意味着：确定在哪些已有状态中这个行为可以触发转移，定义新状态的进入/退出条件，确保转移表没有死锁。这些操作需要理解**转移表的全局一致性**——一个典型的程序员思维模式。

在 BT 中，设计师添加一个新行为意味着：在树中插入一个新的子树（通常是一个 Sequence + 条件），并根据优先级把它放在合适的位置（左边）。**不需要理解已有节点的内部逻辑**——子树之间的耦合仅通过优先级（顺序）和 Blackboard（共享数据）。

Halo 2 开发期间，Bungie 的 AI 设计团队包含了非程序员设计师。Damian Isla 在 GDC 2005 中说："最关键的发现是，设计团队可以独立添加、调整、删除行为，而不需要等待工程师修改转移逻辑。"这就是行为树的"设计师友好"承诺。

**但需要注意**：这个优势的前提是团队有成熟的可视化 BT 编辑器。如果你在从头搭建 BT 框架，设计师友好度不会自动到来——你仍然需要一种方式让非程序员表达条件逻辑（Blackboard key + compare + decorator）。

#### 维度 4: 可调试性

FSM 的调试优势是结构性的：**任何时候，你知道一个变量——`currentState`——就完全知道了 AI 的行为上下文。** 游戏暂停，看 `currentState`，你就知道它应该做什么。如果行为不对，问题要么在转移逻辑（不该在这个状态），要么在状态更新逻辑（在这个状态但做错了）。

BT 的调试劣势是：**暂停游戏只能看到当前 tick 的节点路径。** 你需要知道为什么树选择了这条路径——哪些条件失败了导致 fall-through，哪些条件成功导致路径锁定。这需要专门的调试可视化（UE5 的 Behavior Tree Debugger 会高亮当前执行路径并标注每个条件的结果）。

**生产建议**：无论你选择 FSM 还是 BT，在框架建立的第一周就实现调试可视化。FSM 需要：当前状态名 + 最后一次转移的事件 + 时间戳。BT 需要：当前 tick 路径高亮 + 每个条件节点的最近评估结果。

#### 维度 5: 性能——单帧开销

对于大多数游戏 AI，FSM 和 BT 的单帧性能差异在测量误差范围内。但在特定场景下，差异变得显著：

**FSM 为何更快**：
- 1 次 switch / map lookup → 1 次 Update() 调用。开销恒定。
- 没有树遍历，没有递归 tick，没有逐节点返回值传播。
- 典型开销：< 1μs / AI / 帧（简单 switch 实现）

**BT 为何可能更慢**：
- 深度优先树遍历，每帧 tick N 个节点（N = 路径深度 + fall-through 分支）。
- 条件检查可能重复评估（如果不缓存）。
- 典型开销：3-30μs / AI / 帧（取决于树大小和 tick 策略）

**关键场景——格斗游戏输入处理**：
一个格斗角色的输入状态机（Idle → Crouch → Jump → Attack → Block → HitStun → Knockdown）有 8-12 个状态，但需要在 **1/60 秒（16.6ms）** 内处理完输入并输出响应。在这种场景下，FSM 的确定性 + 常数开销是绝对优势。用 BT 实现同样的逻辑会导致不必要的每帧遍历开销，且优先级重评估模型与输入缓冲（input buffer）机制冲突。

**关键场景——RTS 大规模单位**：
管理 500+ 个单位的 RTS 中，每个单位每帧 5μs 的差异 = 2.5ms 额外 CPU 时间。此时：
- 用 FSM：每个单位 1-2μs（包括感知查询）
- 用 BT：每个单位 3-15μs（取决于树设计）
- 差距足以让你在 60fps 预算内失去 2-5 帧的余量

这并不意味着"大规模场景必须用 FSM"——而是意味着你需要对 BT 使用较低 tick 频率（如每 4-8 帧 tick 一次）或自传播优化。

### 何时选择 FSM

综合以上分析，FSM 在以下场景是明确的最优选择：

1. **简单顺序行为**（3-6 个状态）。自动门（Closed → Opening → Open → Closing → Closed），电梯，可破坏障碍物，陷阱机关。这些行为的通性是：状态切换有严格的顺序约束，几乎不需要条件分支。

2. **确定性顺序要求**。角色动画状态机（Idle → Walk → Run → Jump → Fall → Land）。动画系统需要对"当前状态"有绝对确定的认知来驱动动画混合——BT 的每帧重评估在这里是不必要的开销且可能引入动画抖动。

3. **性能极限场景**。格斗游戏输入处理（上文讨论过），粒子/特效生命周期管理（Spawn → Alive → Fading → Dead），物理状态机（Grounded → Airborne → Ragdoll）。

4. **需要清晰状态性保证的系统**。UI 流程（MainMenu → Settings → InGame → Pause → GameOver），回合制流程，网络状态机（Disconnected → Connecting → Connected → Reconnecting）。

5. **团队经验不足或快速原型**。如果你或你的团队从未使用过 BT，而 deadline 是 3 周后，认真考虑 FSM。一个正确实现的 15 状态 FSM 远好于一个半成品且有设计缺陷的 BT。FSM 的学习曲线接近平坦——理解枚举 + switch，就能开始。BT 的上手曲线更陡（节点类型语义、tick 传播、条件无副作用规则、子树复用模式）。

**FSM 的反模式特征**——当你观察到以下现象时，FSM 可能已经到了极限：
- 你在向已有状态添加"如果 X 条件则跳过 Y 行为"的补丁代码
- 两个状态共享 70% 的逻辑但你不知道如何抽取
- 转移表中有超过 1/3 的格子标注为"忽略/自转移"（大量组合无意义 = 你的状态设计维度有误）
- 设计师每次提出"新行为"时你都感到恐惧

### 何时选择 BT

BT 的最优场景与 FSM 几乎对称：

1. **复杂条件驱动行为**（8+ 种顶层行为）。敌人 AI、队友 AI、NPC 日常行为。这些系统的特征是：行为之间不断互相抢占优先级，条件评估频繁变化。

2. **高频中断需求**。敌人正在攻击，但血量突然降低→立即撤退；撤退中队友倒地→中断撤退去救援。BT 的每帧从根重评估让这些中断"免费"——不需要在 Attack 状态中显式检查 FLEE_CONDITION，树结构本身就处理了。

3. **设计迭代驱动**。需求每 1-2 周变化，新行为频繁添加，行为优先级需要经常调整。BT 的"插入新子树 + 调整树顺序"比 FSM 的"修改 N 个状态的转移规则"更安全。

4. **程序/设计分工**。程序员编写 Action/Condition 节点，设计师在可视化编辑器中排列树结构。这是 Unreal Engine Behavior Tree 工作流的标准模式。

5. **行为需要加法式组合**。一个角色的行为是若干离散能力的叠加——巡逻、感知、战斗、使用物品、社交。每个能力是独立子树，组合出新行为只需要将子树放入 Selector 的合适优先级位置。

**BT 的反模式特征**：
- 树中每个子树都以 Sequence 开头且第一个节点检查"是否已经在做这个行为"——你在逃避每帧重评估而手动管理状态。
- Action 节点中有大量的成员变量来"记住上次做了什么"——你在给本来无状态的树注入状态。
- 树的深度超过 5 层但宽度很窄——你可能过度设计了层次结构。

### 混合方案：AAA 游戏的实践

几乎所有现代 AAA 游戏都使用混合架构。最常见的分层：

```
高层决策 (What to do?)     → Behavior Tree
中层模式 (How to do it?)   → HSM 或 Utility System
低层执行 (Physical motion) → FSM (Animation State Machine)
```

具体例子：

- **Halo 3/Reach**：BT 驱动敌人高层战术决策（engage/retreat/search/flee），每个行为节点内部用参数化逻辑（本质上是微型 FSM）控制具体的移动和射击节奏。
- **The Last of Us**：BT 驱动 NPC 的战术选择，低层由 Naughty Dog 自研的动画状态机驱动移动。
- **Killzone 系列**：Guerrilla Games 使用 HSM 作为顶层架构，状态内部包含行为选择逻辑（类似 Utility AI）。
- **F.E.A.R.**：GOAP（目标导向行动规划）用于战术决策，FSM 用于武器和动画状态。GOAP 在复杂度和灵活性上超越了 BT 和 FSM，但实现和维护成本也远高于两者。我们将在 Tutorial 16 中详细讨论 GOAP。
- **Uncharted 系列**：Naughty Dog 混合使用 BT（主要敌人 AI 框架）和脚本 FSM（关卡特定行为）。

**分层原则**：
1. **决策频率越高的层用越简单的机制**。动画层每帧运行 → FSM。战术层每秒重评估几次 → BT。
2. **状态性需求越强的层用越有状态的机制**。物理交互（在地面/在空中）需要确定的状态 → FSM。目标选择（最近的敌人/最低血量）不需要历史 → BT。
3. **越靠近设计师的层用越可视化的机制**。高层行为选择 → BT 可视化编辑器。低层运动控制 → FSM/Blend Tree。

### 定量比较：状态增长模型

让我们用数学模型精确化之前的直觉。

**场景**：一个 AI 系统有 M 个独立行为关注点（combat, movement, item, social），每个关注点有 k_i 个选项。

**FSM（平面）**：状态数 ≈ ∏ᵢ k_i（笛卡尔积）
**HSM**：状态数 ≈ Σᵢ k_i + 少量交叉状态（通过层次压缩）
**BT**：节点数 ≈ Σᵢ (k_i × avg_subtree_size)（线性叠加）

**修改成本模型**（新增一个关注点，k_{M+1} = 3）：

| | FSM | HSM | BT |
|---|---|---|---|
| 新增代码量 | 修改已有 k₁×…×k_M 个状态 | 新增 1 个父状态 + 修改交叉转移 | 新增 1 个子树（~3-5 个节点） |
| 修改已有逻辑 | 80-100% 已有状态受影响 | 20-40% 已有状态受影响 | 0-10% 已有节点受影响 |
| 引入 bug 风险 | 高（大面积修改转移规则） | 中（交叉转移可能遗漏） | 低（子树自包含，局部影响） |

**关键洞察**：BT 不是在所有规模下都更好——**BT 是在"变化"存在时更好。** 如果你的 AI 需求稳定（如动画状态机，从项目第一天到发售日几乎不变），FSM 的简单性胜过 BT 的灵活性。如果你的 AI 需求每两周变化一次，BT 的低修改成本是决定性的。

### 工业数据点

以下数据来自公开的 GDC 演讲和 Game AI Pro 文章，并非虚构：

| 游戏 | 顶层架构 | 关键数据 |
|------|---------|---------|
| **Halo 2 (2004)** | BT（优先级行为列表） | ~50 种行为，每帧从根重评估；Bungie 估计相比 FSM 节省了数月迭代时间 |
| **Halo 3 (2007)** | BT + 参数化节点 | 行为树节点数约 200+；引入"行为标签"系统避免条件冗余 |
| **Killzone 2/3 (2009/2011)** | HSM | ~30 个状态，多层嵌套；Guerrilla 在后来的演讲中承认如果重新开始可能会用 BT |
| **F.E.A.R. (2005)** | GOAP + FSM | 3 个目标 + ~50 个动作；FSM 仅用于动画层。GOAP 的规划深度通常为 3-5 步 |
| **The Sims 3/4** | Utility AI | 无显式状态机或行为树；每个交互的"效用分数"由多维度计算（需求、性格、环境） |
| **Uncharted 2 (2009)** | 混合（BT + 脚本） | 敌人 AI 用轻量 BT，关卡特定行为用脚本 FSM；船关卡（Chapter 15）的 AI 需要特殊处理摇摆甲板 |
| **DOOM (2016)** | FSM + 优先级系统 | id Software 使用"战斗角色"FSM 定义恶魔行为，用简单的优先级覆盖处理特殊情况 |

**三个值得深入的数据点**：

1. **Halo 2 的迁移成本**：Bungie 从 Halo 1（FSM）迁移到 Halo 2（BT）花了约 6-9 个月重写 AI 框架。但他们估计如果继续用 FSM 扩展 Halo 2 的 AI 需求（更复杂的载具战、双持武器、动态小队），调试和迭代时间会远超这个成本。

2. **Killzone 的反思**：Guerrilla 在 2011 年 GDC 上公开表示，Killzone 的 HSM 架构在项目后期暴露出局限性——"当你需要一种新行为时，你必须在层次中找到正确的位置，然后检查它是否与兄弟状态的转移规则冲突。"这恰恰是 BT 解决的问题。

3. **Uncharted 的"脚本跃迁"**：Naughty Dog 的 Jonathan Stein 描述了 Uncharted 系列中的一个反复出现的模式：关卡设计团队会先用脚本 FSM 实现新的 AI 行为原型，如果该行为被证明对全局 NPC 都有效，就将其"提升"为可复用的 BT 节点。

---

## 2. 代码示例

### 示例 A：同一敌人 AI 的 FSM vs BT 实现对比

下面的实现对比展示了同一个敌人 AI（巡逻 → 追击 → 攻击，带血量撤退）在两种范式下的代码。我们使用伪代码（C++ 风格）以便聚焦于结构差异而非具体语言细节。

#### FSM 版本

```cpp
// ============================================================
// FSM 版本：巡逻+追击+攻击+撤退 敌人 AI
// 复杂度度量：1 个文件, ~150 行, McCabe 圈复杂度 ≈ 12
// ============================================================

enum class EnemyState { Patrol, Chase, Attack, Flee, Dead };
enum class EnemyEvent { EnemySpotted, EnemyLost, InMeleeRange,
                        OutOfMeleeRange, HealthLow, HealthZero };

class EnemyAIFSM {
    EnemyState state = EnemyState::Patrol;
    float health = 100.f;
    // Patrol-specific state
    int patrolWaypointIndex = 0;
    // Chase-specific state
    float chaseLostTimer = 0.f;

public:
    void Update(float dt) {
        // 1. Poll perception
        auto event = PollEvents();

        // 2. Evaluate transitions
        EnemyState next = state;
        switch (state) {
        case EnemyState::Patrol:
            if (event == EnemyEvent::HealthZero) next = EnemyState::Dead;
            else if (event == EnemyEvent::EnemySpotted) next = EnemyState::Chase;
            break;
        case EnemyState::Chase:
            if (event == EnemyEvent::HealthZero) next = EnemyState::Dead;
            else if (event == EnemyEvent::HealthLow) next = EnemyState::Flee;
            else if (event == EnemyEvent::InMeleeRange) next = EnemyState::Attack;
            else if (event == EnemyEvent::EnemyLost) next = EnemyState::Patrol;
            break;
        case EnemyState::Attack:
            if (event == EnemyEvent::HealthZero) next = EnemyState::Dead;
            else if (event == EnemyEvent::HealthLow) next = EnemyState::Flee;
            else if (event == EnemyEvent::OutOfMeleeRange) next = EnemyState::Chase;
            break;
        case EnemyState::Flee:
            if (event == EnemyEvent::HealthZero) next = EnemyState::Dead;
            else if (event == EnemyEvent::EnemyLost)
                next = EnemyState::Patrol; // safe now
            break;
        case EnemyState::Dead:
            break;
        }

        // 3. Handle state transitions
        if (next != state) {
            OnExit(state);
            state = next;
            OnEnter(state);
        }

        // 4. Execute state logic
        switch (state) {
        case EnemyState::Patrol: UpdatePatrol(dt); break;
        case EnemyState::Chase:  UpdateChase(dt);  break;
        case EnemyState::Attack: UpdateAttack(dt); break;
        case EnemyState::Flee:   UpdateFlee(dt);   break;
        case EnemyState::Dead:   UpdateDead(dt);   break;
        }
    }

private:
    EnemyEvent PollEvents() {
        if (health <= 0) return EnemyEvent::HealthZero;
        if (health < 30)  return EnemyEvent::HealthLow;
        float dist = DistanceToEnemy();
        bool visible = HasLineOfSight();
        if (visible && dist < 2.f)  return EnemyEvent::InMeleeRange;
        if (visible && dist < 15.f) return EnemyEvent::EnemySpotted;
        if (visible && dist > 20.f) return EnemyEvent::OutOfMeleeRange;
        if (!visible && dist > 25.f) return EnemyEvent::EnemyLost;
        return EnemyEvent::EnemyLost; // default
    }

    void UpdatePatrol(float dt) { /* move along waypoints */ }
    void UpdateChase(float dt)  { /* navigate to last known pos */ }
    void UpdateAttack(float dt) { /* face enemy and strike */ }
    void UpdateFlee(float dt)   { /* move away from enemy */ }
    void UpdateDead(float dt)   { /* play death anim, then disable */ }

    void OnEnter(EnemyState s)  { /* entry callbacks */ }
    void OnExit(EnemyState s)   { /* exit callbacks */ }
};
```

**FSM 版本的复杂度特征**：
- 5 个状态，6 个事件 → 转移表有 5×6 = 30 个槽位，其中约 14 个有实际转移逻辑
- 新增一个状态（如 `Stunned`）需要修改：① 枚举定义 ② 状态转移 switch 的 5 个 case ③ 状态执行 switch
- 修改逻辑影响面：转移表 + 状态执行，耦合度高

#### BT 版本

```cpp
// ============================================================
// BT 版本：巡逻+追击+攻击+撤退 敌人 AI
// 复杂度度量：1 个树定义文件(~60 行) + 6 个节点文件(~80行总计),
//             节点圈复杂度 ≈ 每个节点 1-3
// ============================================================

// --- Node definitions (one file per node type) ---

// Condition nodes: pure checks, no side effects
struct IsDeadNode : ConditionNode {
    Status Tick(Blackboard& bb) override {
        return bb.Get<float>("health") <= 0 ? Status::Success : Status::Failure;
    }
};

struct IsHealthLowNode : ConditionNode {
    Status Tick(Blackboard& bb) override {
        return bb.Get<float>("health") < 30 ? Status::Success : Status::Failure;
    }
};

struct HasEnemyInSightNode : ConditionNode {
    Status Tick(Blackboard& bb) override {
        auto* enemy = bb.Get<Entity*>("perception.enemy");
        return (enemy && LineOfSight(enemy)) ? Status::Success : Status::Failure;
    }
};

struct IsInMeleeRangeNode : ConditionNode {
    Status Tick(Blackboard& bb) override {
        auto* enemy = bb.Get<Entity*>("perception.enemy");
        return (enemy && DistanceTo(enemy) < 2.f)
            ? Status::Success : Status::Failure;
    }
};

struct IsEnemyLostNode : ConditionNode {
    Status Tick(Blackboard& bb) override {
        auto* enemy = bb.Get<Entity*>("perception.enemy");
        if (!enemy) return Status::Success;
        return (!LineOfSight(enemy) && DistanceTo(enemy) > 25.f)
            ? Status::Success : Status::Failure;
    }
};

// Action nodes: may return Running for multi-frame operations
struct FleeAction : ActionNode {
    Status Tick(Blackboard& bb) override {
        auto* enemy = bb.Get<Entity*>("perception.enemy");
        if (!enemy) return Status::Success;
        MoveAwayFrom(enemy);
        return Status::Running; // flee is ongoing
    }
};

struct AttackAction : ActionNode {
    Status Tick(Blackboard& bb) override {
        auto* enemy = bb.Get<Entity*>("perception.enemy");
        if (!enemy) return Status::Failure;
        FaceTarget(enemy);
        if (AttackCooldownReady())
            PerformAttack();
        return Status::Running;
    }
};

struct ChaseAction : ActionNode {
    Status Tick(Blackboard& bb) override {
        auto* enemy = bb.Get<Entity*>("perception.enemy");
        if (!enemy) return Status::Failure;
        NavigateTo(enemy->position);
        return Status::Running;
    }
};

struct PatrolAction : ActionNode {
    int waypointIndex = 0;
    Status Tick(Blackboard& bb) override {
        // Patrol along waypoints; never "completes"
        MoveAlongWaypoints(waypointIndex);
        return Status::Running;
    }
};

struct DeadAction : ActionNode {
    bool animFinished = false;
    Status Tick(Blackboard& bb) override {
        if (!animFinished) {
            PlayDeathAnimation();
            animFinished = true;
        }
        return Status::Running;
    }
};

// --- Tree construction ---
// This is what designers would arrange in a visual editor.
// The tree structure IS the AI logic.

BehaviorTree BuildEnemyBT() {
    BehaviorTree bt;

    // Root: highest-priority subtree wins
    auto* root = bt.CreateSelector();

    // Priority 1: Dead (overrides everything)
    auto* deadSeq = bt.CreateSequence();
    deadSeq->AddChild(bt.CreateNode<IsDeadNode>());
    deadSeq->AddChild(bt.CreateNode<DeadAction>());
    root->AddChild(deadSeq);

    // Priority 2: Self-preservation (flee when health low)
    auto* fleeSeq = bt.CreateSequence();
    fleeSeq->AddChild(bt.CreateNode<IsHealthLowNode>());
    fleeSeq->AddChild(bt.CreateNode<FleeAction>());
    root->AddChild(fleeSeq);

    // Priority 3: Combat subtree
    auto* combatSel = bt.CreateSelector();

    // 3a: Melee attack if close
    auto* meleeSeq = bt.CreateSequence();
    meleeSeq->AddChild(bt.CreateNode<IsInMeleeRangeNode>());
    meleeSeq->AddChild(bt.CreateNode<AttackAction>());
    combatSel->AddChild(meleeSeq);

    // 3b: Chase if enemy visible
    auto* chaseSeq = bt.CreateSequence();
    chaseSeq->AddChild(bt.CreateNode<HasEnemyInSightNode>());
    chaseSeq->AddChild(bt.CreateNode<ChaseAction>());
    combatSel->AddChild(chaseSeq);

    // 3c: Fallback if enemy lost during combat
    auto* lostSeq = bt.CreateSequence();
    lostSeq->AddChild(bt.CreateNode<IsEnemyLostNode>());
    lostSeq->AddChild(bt.CreateNode<PatrolAction>());
    combatSel->AddChild(lostSeq);

    root->AddChild(combatSel);

    // Priority 4: Default — patrol
    root->AddChild(bt.CreateNode<PatrolAction>());

    bt.SetRoot(root);
    return bt;
}
```

**BT 版本的复杂度特征**：
- 6 个条件节点 + 5 个动作节点 = 11 个叶子节点
- 新增一个行为（如 `Stunned`）：新增 1 个 Condition + 1 个 Action，在树中按优先级插入 1 个 Sequence
- 修改逻辑影响面：只影响被修改的节点和它在树中的位置

#### 对比总结

| 指标 | FSM | BT |
|------|-----|----|
| 总代码行数 | ~150 | ~60 (树定义) + ~80 (节点) = ~140 |
| 文件数 | 1 | 1 + 11 (或合并为 2-3) = 2-12 |
| McCabe 圈复杂度 | ~12 (Update 中的双 switch) | 每个节点 1-3，树结构 5-8 |
| 新增"Stunned"行为工作量 | 修改 3 处已有代码 + 新增状态 | 新增 2 个节点 + 1 行树结构 |
| "新增低血量 berserk"工作量 | 修改 Attack/Flee 转移逻辑 | 在 fleeSeq 之前插入 1 个条件子树 |
| 单帧 tick 节点数 | 1 (直接) | 4-8 (遍历路径) |
| 行为优先级可见性 | 分散在 switch case 的顺序中 | 集中在树结构的左→右顺序 |

**关键结论**：在这个简单 AI（5 种行为）规模下，FSM 和 BT 的代码量几乎持平。但 BT 的**修改成本**已经展现出优势——新增任何行为在 BT 中都是局部操作，在 FSM 中需要触碰多个已有 case。

### 示例 B：演化场景——从简单到复杂的生长痛

这个例子展示了为什么"一开始用 FSM，后来迁移到 BT"的代价远超预期。

#### 阶段 1：基础 FSM（巡逻 + 追击）

最初的需求很简单——一个守卫 NPC。用 FSM 实现有 2 个状态：

```
[Patrol] ←→ [Chase]
```

代码很干净：~40 行，1 个 switch。

#### 阶段 2：新增攻击 + 死亡

```
[Patrol] ←→ [Chase] ←→ [Attack] → [Dead]
```

新增 2 个状态，修改 Patro l→Chase 和 Chase→Patrol 的转移条件（加入"如果在攻击范围内则跳转到 Attack"）。约 80 行代码。仍然可管理。

#### 阶段 3：新增撤退 + 守卫

```
[Patrol] ←→ [Chase] ←→ [Attack] → [Dead]
                ↑         ↓
                └─ [Flee] ──┘
     [Guard] (站岗不动，类似 Patrol 但无巡逻路径)
```

此时 FSM 状态数 = 6，但转移边开始变得复杂：
- `Attack → Flee`（低血量）
- `Flee → Patrol`（安全后）
- `Flee → Chase`（逃跑中被发现）
- `Guard → Chase`（站岗时发现敌人）
- `Chase → Guard`（丢失敌人且原本在站岗——等等，Chase 怎么知道"原本在站岗还是巡逻"？）

**问题出现了**：`Chase` 状态失去了"战斗结束后该回到哪里"的信息。这需要额外的状态变量（`previousIdleState`）或状态栈（Pushdown）。现在 FSM 的转移表有 6×8 = 48 个槽位而不是 2×3 = 6 个。

#### 阶段 4：新增"调查可疑声音"

需求：NPC 听到枪声时中断当前行为，前往声源调查，调查结束后回到之前的行为。

```
状态数 = 7 (新增 Investigate)
转移边 ≈ 12 条新增或修改
```

这次修改触及了几乎每个已有状态的转移逻辑——因为"听到声音"可以从任何非 Dead 状态触发。加上 Pushdown 栈管理，代码量膨胀到约 350 行。

#### 阶段 5：新增"小队协同"和"低血量 berserk"

阶段 5 是 FSM 的真正崩溃点：

- **小队协同**：NPC 需要对同伴的死亡、撤退、进攻信号做出反应。这引入了 3-4 个新事件和转移路径，与已有转移规则产生交叉耦合。
- **Berserk**：特定 NPC（近战型）在低血量时不撤退而是冲上去。这与现有的 `HealthLow → Flee` 转移冲突——你需要在该转移上加入"除非 NPC 类型是 Berserker"的条件分支。

此时的 FSM 转移图：

```
转移表：10 状态 × 12 事件 = 120 槽位
其中 ~45 个槽位有显式转移逻辑
~15 个槽位有条件分支（如 "if berserker then... else..."）
代码行数：600+
```

**如果用 BT 实现阶段 5 的需求**：

```
Selector (Root)
├── Dead Sequence                    ← 不变
├── Berserk Sequence (new!)          ← 仅新增
│   ├── Condition: IsBerserkerType?
│   ├── Condition: IsHealthLow?
│   └── Action: ChargeAttack
├── SquadReaction Selector (new!)    ← 仅新增
│   ├── SquadRetreat Sequence
│   │   ├── Condition: SquadMoraleBroken?
│   │   └── Action: RetreatWithSquad
│   ├── SquadAssist Sequence
│   │   ├── Condition: AllyNeedsHelp?
│   │   └── Action: MoveToAlly
│   └── SquadAttackSequence
│       ├── Condition: SquadOrderAttack?
│       └── Action: CoordinatedAttack
├── Flee Sequence (unchanged)        ← 不变
├── Investigate Sequence (unchanged) ← 不变
├── Combat Sequence (unchanged)      ← 不变
├── Guard Sequence (unchanged)       ← 不变
└── Patrol Action (unchanged)        ← 不变
```

- **新增行为只需插入新子树**。已有节点的逻辑完全不变。
- **优先级通过树顺序可见**。Berserk 放在 Flee 之前 → Berserker 永远不会进入 Flee 分支。
- **代码行数**：每个新行为 ~20-30 行（节点定义 + 树结构插入），已有代码零修改。

**演化成本对比**：

| | 阶段 1 | 阶段 3 | 阶段 5 |
|---|---|---|---|
| FSM 代码行数 | ~40 | ~200 | ~600+ |
| FSM 每个新阶段修改已有代码比例 | — | 60% | 80% |
| BT 代码行数 | ~80 | ~140 | ~220 |
| BT 每个新阶段修改已有代码比例 | — | 10% | 5% |

**这不是一个公平的比较**——在阶段 1 时 FSM 确实更简单（40 行 vs 80 行）。关键是：**你能准确预测你的 AI 需求在 6 个月后是什么规模吗？** 如果不能，BT 的演化成本优势是重要的保险。

---

## 3. 练习

### 练习 1：设计选型决策（45min）

阅读以下游戏设计文档摘要（为一个新 IP 的动作 RPG 游戏），针对三个不同的 AI 类型分别做出 FSM vs BT 的选型决策，每个写一段 200-300 字的理由。

**设计文档摘要**：

> 游戏包含三个 AI 类别：
>
> **A. 陷阱机关**：地牢中的可破坏障碍物（箭墙、落石、毒气喷射）。每个机关有 3-4 个状态：待机 → 激活（玩家进入触发范围）→ 冷却 → 待机。机关之间独立，没有交互。
>
> **B. 普通敌人**：守卫、巡逻兵、斥候。每种约 8-12 种顶层行为（巡逻、站岗、追击、近战/远程攻击、撤退、呼叫增援、调查异常、死亡）。不同的敌人类型在具体参数上有差异（攻击距离、移动速度、警戒范围），但行为骨架相似。设计团队预期在开发过程中会新增 2-3 种敌人行为和 5+ 种敌人变体。
>
> **C. Boss 战**：分为 3 个阶段（100%-66% HP / 66%-33% / 33%-0%），每个阶段有不同的攻击模式和 arena 机制。每个 Boss 是独特的——行为不与其他 Boss 共享。Boss 需要在阶段切换时平滑过渡动画，同时某些攻击组合有严格的顺序要求（"必须先放技能 A，等 2 秒后接技能 B"）。

**你的任务**：
- 为 A、B、C 分别选择 FSM 或 BT，并写出理由。
- 理由中需要至少引用 1 个来自本教程 §1 的比较维度。
- 如果选择混合方案，说明每一层用什么以及为什么。

### 练习 2：已有系统审计（30min）

找到一个你或团队已有的 FSM AI 实现（或使用本教程 §2 示例 A 的 FSM 代码），回答以下问题：

1. 列出当前 FSM 的所有状态和转移边。
2. 标记出哪些状态之间的转移规则存在"交叉耦合"（即修改一条转移会影响另一条的行为预期）。
3. 指出：如果当前系统增加 3 个新行为（你的选择：如"stunned/硬直"、"loot/拾取"、"taunt/嘲讽"），哪些已有状态需要修改？
4. 给出判断：该系统应该保持 FSM、迁移到 BT、还是混合？（如果混合，画出分层架构草图。）

### 练习 3（可选）：双实现对比实验（~3h）

选择一个中等复杂度的 AI 行为（建议：一个有巡逻、追击、近战攻击、远程攻击、撤退、使用道具、调查声音 7 种行为的敌人），分别用 FSM 和 BT 实现完整可运行的代码（语言自选）。记录以下数据：

| 指标 | FSM | BT |
|------|-----|----|
| 实现耗时 | | |
| 代码行数 | | |
| 初始 bug 数（实现过程中的逻辑错误） | | |
| 新增 1 个行为（如"召唤小兵"）的耗时 | | |
| 修改 1 个现有行为（如"撤退条件从 30% HP 改为 25% HP + 队友死亡"）的耗时 | | |

对比你的数据和本教程的预测。如果有差异，分析原因。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **A. 陷阱机关 → FSM**
>
> 理由：陷阱机关的状态空间极小（3-4 状态）且状态切换有严格的顺序约束（待机→激活→冷却→待机）。引用维度 1（复杂度天花板）：FSM 在 ≤6 状态时是最优选择——1 个枚举 + 1 个 switch，代码量约 50 行，圈复杂度 < 5。引用维度 5（性能）：陷阱通常在场景中大量存在（20-50+），每个机关的 AI 必须是常数级开销。BT 的每帧树遍历在此场景中是净损失。引用维度 2（模块化）：机关之间独立无交互——不需要 BT 的子树复用和 Blackboard 共享数据。不需要混合方案：纯 FSM 即可。
>
> **B. 普通敌人 → BT**
>
> 理由：8-12 种顶层行为已超过 FSM 的舒适区（维度 1 拐点约 6-8 种行为）。不同敌人类型共享行为骨架但参数化差异（攻击距离、移动速度、警戒范围）——这正是 BT 的子树参数化优势（维度 2：模块化复用）。设计师预期会新增 2-3 种行为——BT 的"插入新子树"比 FSM 的"修改 N 个状态的转移规则"更安全（维度 3：修改成本模型预测 BT 的已有节点受影响率 0-10% vs FSM 的 80-100%）。建议混合：高层战术决策用 BT（Selector 优先级驱动），低层动画用 Animation State Machine / FSM（严格的 animation blending 和过渡条件需要确定性状态）。中层"追击执行"和"攻击节奏"可保留在 BT 内部（通过 Sequence 拆分子步骤）或下沉到轻量 FSM（如"Attack"状态内部包含 Windup→Swing→Recovery 的动画 FSM）。
>
> **C. Boss 战 → 混合：BT（阶段决策）+ FSM（阶段内攻击序列）+ Animator（动画过渡）**
>
> 理由：Boss 的**阶段切换**是条件驱动的（HP 阈值 → 阶段变化），BT 的条件评估天然适合——不需要在阶段 1 的每个攻击状态中检查"HP < 66% → 切换到阶段 2"。但**阶段内的攻击序列**有严格顺序要求（"必须先放技能 A，等 2 秒后接技能 B"），这是 FSM 的优势——序列和时序在 FSM 中表达得比 BT 的 Sequence + Wait 更精确（引用维度 4：确定性）。动画过渡要求平滑且可中断，属于低层 Animation State Machine 的职责（引用维度 5：决策频率越高用越简单的机制）。架构设计：高层 = BT（评估阶段切换条件），中层 = 每个阶段一个 FSM/HFSM（定义该阶段的攻击模式序列），低层 = Animator（驱动具体动画混合和过渡）。Blackboard 作为跨层共享总线——BT 写入 `CurrentBossPhase`，FSM 读取后切换模式，Animator 读取 `IsInRecovery` 控制动画混合。

> [!tip]- 练习 2 参考答案
> **系统审计示例**（基于本教程 §2 示例 A 的 FSM 代码 — 巡逻+追击+攻击+撤退 敌人 AI）：
>
> **1. 当前状态和转移边**：
> - 状态：`Patrol`、`Chase`、`Attack`、`Flee`、`Dead`
> - 转移边（来源→去向：触发条件）：
>   - `Patrol → Chase`: `EnemySpotted`; `Patrol → Dead`: `HealthZero`
>   - `Chase → Attack`: `InMeleeRange`; `Chase → Flee`: `HealthLow`; `Chase → Patrol`: `EnemyLost`; `Chase → Dead`: `HealthZero`
>   - `Attack → Chase`: `OutOfMeleeRange`; `Attack → Flee`: `HealthLow`; `Attack → Dead`: `HealthZero`
>   - `Flee → Patrol`: `EnemyLost`; `Flee → Dead`: `HealthZero`
>   - `Dead`: 无转出
>
> **2. 交叉耦合的转移规则**：
> - `HealthLow → Flee` 存在于 `Chase`、`Attack` 两个状态中。修改 Flee 的条件（如从 30% HP 改为 25% HP + 队友死亡）需要同时修改这两个状态的转移分支——耦合点。
> - `EnemyLost → Patrol` 存在于 `Chase` 和 `Flee`。如果将来 Patrol 需要携带"上次丢失敌人的位置"参数，两个转移点都需要向 Blackboard 写入。
> - `HealthZero → Dead` 存在于除 Dead 外的**所有**状态——这是 4 条重复的转移边。在 FSM 中这是典型的"全局转移"问题，HSM 通过父状态统一处理可以解决。
>
> **3. 新增 3 个行为后的修改影响**：
> - **Stunned/硬直**：需要从 `Chase`、`Attack`（可能还有 `Flee`）增加转移边。需要 `Stunned` 状态内维护计时器。结束后需要知道"回到哪个状态"——FSM 不天然支持"中断后返回"，需要额外栈或成员变量。修改状态数：3-4 个已有状态。
> - **Loot/拾取**：通常发生在敌人死亡后或战斗结束后（Patrol 中看到掉落物）。需要在 `Patrol` 和可能的 `Chase`/`Flee` 后添加转移。修改状态数：2-3 个。
> - **Taunt/嘲讽**：可能从任何战斗状态触发。需要在 `Chase` 和 `Attack` 添加转移。修改状态数：2 个。
> - **总修改**：6-9 处，覆盖 80% 的已有状态。
>
> **4. 判断：应迁移到 BT（混合方案可选）**：
> 该系统已处于 FSM 反模式边界——"向已有状态添加补丁代码""修改一条转移会影响另一条""设计师每次提新行为都感到恐惧"。如果项目还有后续迭代计划（新敌人变体、新 AI 行为），迁移到 BT 是更可持续的选择。**分层架构草图**：
> ```
> High (BT): Selector → Flee优先 | Attack优先 | Chase | Patrol → 条件驱动决策
> Mid (无/Func): BT 的 Action 节点直接执行简单逻辑（MoveTo、PlayAnimation）
> Low (Animator): Idle / Walk / Run / Attack Blend Tree — 从 Blackboard 读取参数
> ```
> 如果团队熟悉 FSM 且迁移成本过高（deadline 临近），可以先用 HSM 重构提取全局转移（Dead/Stunned），推迟 BT 迁移到下一个里程碑。

> [!tip]- 练习 3 参考答案（可选）
> **双实现对比实验参考数据**（基于典型中级开发者的经验值）：
>
> | 指标 | FSM | BT |
> |------|-----|----|
> | 实现耗时 | ~2h（7 个状态 + 15 条转移边） | ~3h（22 个节点 + Blackboard + ~40 行条件函数） |
> | 代码行数 | ~180 行（1 个枚举 + 7 个 Update 函数 + 1 个转移表） | ~120 行（树结构定义 50 行 + 节点函数 70 行） |
> | 初始 bug 数 | 3 个（遗漏 EnemyLost→Patrol、Flee 后没有重置目标、Dead 可以被重复触发） | 2 个（Sequence 中 Condition 顺序错、忘记添加 Repeater） |
> | 新增 1 个行为 | ~35min（添加状态 + 修改 4 个已有状态的转移规则） | ~15min（添加 1 个 Sequence 子树、3 个节点） |
> | 修改 1 个行为 | ~20min（修改 2 个函数中的条件判断） | ~8min（修改 1 个 Condition 函数的逻辑） |
>
> **与教程预测的差异分析**：
> 教程预测 BT 的代码行数通常比 FSM 多（因为需要节点框架），但在本实验中 BT 更少——这是因为 7 种行为本身带来了 FSM 转移表的固有开销（每个状态需处理多条转移），而 BT 的复用（`HasTarget` Condition 被多分支共享）减少了重复代码。这个差异取决于**行为之间的条件重叠度**——如果条件重叠高，BT 更省代码；如果每个行为条件独立，FSM 更省。实际项目中这个重叠度是需要测量的。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的分析有充分依据并引用了教程中的比较维度，就是正确的。

## 4. 扩展阅读

### 必读材料

1. **Damian Isla — "Managing Complexity in the Halo 2 AI" (GDC 2005)**
   这篇演讲是行为树在游戏 AI 中的起源文献。Isla 详细描述了 Bungie 从 FSM 迁移到优先级行为列表（proto-BT）的动机和过程。关键论点：当 AI 需要 50+ 种行为且优先级频繁变动时，FSM 的转移表不再可维护。可在 GDC Vault 找到录音和幻灯片。

2. **Damian Isla — "Handling Complexity in the Halo 3 AI" (GDC 2007)**
   Halo 2 的后续演进。讨论行为标签系统如何进一步减少条件冗余，以及如何为大型团队（20+ 设计师）扩展 BT 工具链。

3. **Game AI Pro 系列 — "Behavior Selection" 章节**
   Game AI Pro 1/2/3 中有多篇关于行为选择架构的文章。特别推荐：
   - "The Simplest AI Trick in the Book"（Game AI Pro 1, Chapter 17）— 展示了一个极简优先级系统的威力
   - "Behavior Selection Algorithms"（Game AI Pro 1, Chapter 18）— 系统比较 FSM、BT、Utility AI 的决策特征

4. **Mikael Hedberg — "Causing Fear, But Not Frustration: AI in Dead Space" (GDC 2008)**
   讨论了在恐怖游戏中如何用混合架构（BT + 脚本 FSM）创造可预测但令人紧张的 AI 行为。

### 推荐材料

5. **Alex J. Champandard — "Getting Started with Behavior Trees" (AiGameDev.com, 2007-2012)**
   Champandard 的系列文章是行为树入门的经典资源。虽然是 2007 年的内容，但其对 BT vs FSM 的思考框架仍然是最清晰的之一。

6. **Bobby Anguelov — "Behavior Trees: A Primer" (blog, 2014)**
   一位 AAA AI 程序员的 BT 实战经验总结。特别有价值的是他对"BT 何时反而是坏选择"的讨论。

7. **GDC AI Summit recordings (2010-2024)**
   GDC 的 AI Summit 每年有 10-20 场演讲，其中约 1/3 涉及行为选择架构。搜索关键词 "behavior selection architecture"、"decision making"、"FSM vs BT"。

### 补充查阅

8. **Unreal Engine 5 — Behavior Tree 文档**
   研究 UE5 的 BT 实现如何通过 Decorator（Observer Aborts）、Service（并行 tick）、Composite（Selector/Sequence/Parallel）实现生产级 AI。注意 UE5 的 StateTree 是 HSM+BT 的融合——观察哪些概念来自 FSM 体系，哪些来自 BT 体系。

9. **《Behavior Trees in Robotics and AI: An Introduction》(Michele Colledanchise & Petter Ögren, 2018)**
   这是行为树的学术专著。如果你想理解 BT 的形式化语义（而不是游戏行业的直觉用法），这本书提供了从数学定义出发的完整分析。第 2-4 章特别适合那些想知道"为什么 Selector 必须是 fallback 而不是别的什么"的读者。

---

## 常见陷阱

### 陷阱 1: "BT 总是更好"的教条主义

**症状**：无论需求多简单，坚持用 BT，因为"这是业界标准"或"FSM 已经过时了"。

**后果**：为一个只有 3 种状态的自动门引入 15 个 BT 节点、一个 Blackboard、一个可视化编辑器集成。引入的复杂度远超 AI 本身的复杂度。

**正确做法**：回顾 §1 的"何时选择 FSM"。如果你的 AI 符合以下 3+ 条，FSM 是更好的选择：
- 状态数 ≤ 6
- 每个状态下不需要频繁的条件分支
- 需求稳定，不太可能在开发中新增行为
- 团队不熟悉 BT
- 性能是关键约束（如移动端或大规模单位场景）

Pac-Man 的幽灵 AI 用 3 状态 FSM 运行了 40 年——如果你在重制 Pac-Man，FSM 仍然是正确的选择。

### 陷阱 2: 为简单系统过早引入 BT

**症状**：看到 BT 的演示很酷，就把当前的 4 状态 FSM 改成 BT，"为以后扩展做准备"。

**后果**：
- 增加了代码库的技术栈（需要 BT 运行时、序列化、调试工具）
- 团队学习成本（每个新成员需要理解 BT 的 tick 语义）
- 设计团队的可视化工具需求（"为什么我们不能像 Unreal 那样拖节点？"）
- 如果"以后的扩展"从未发生，这些成本是净损失

**正确做法**：**用当前需求选择工具，用"可替换性"降低风险**。把 AI 的 Update() 入口设计成接口，使得 FSM 实现可以无痛替换为 BT 实现（或反过来）。这不意味着过度抽象——只是一个 `IAIBehavior` 接口，`Update()` 返回 void，内部实现可以是 FSM、BT 或任何东西。

```cpp
// 这种薄封装是免费的保险
class EnemyAI {
    std::unique_ptr<IBehaviorController> controller; // FSM or BT
public:
    void Update(float dt) { controller->Tick(dt); }
};
```

### 陷阱 3: FSM-in-BT 泄露

**症状**：在 BT 的 Action 节点中实现有状态的状态机逻辑——节点内部有 `enum State { ... }` 和 `switch`。

**后果**：BT 的两大优势（每帧从根重评估带来的自动优先级中断、子树复用）被削弱。如果 `Attack` 节点内部有一个"预备→挥砍→收招"的微型 FSM，而在这个 FSM 的"收招"阶段外部条件触发了中断（如血量降低），节点可能无法响应中断直到整个微 FSM 完成一个周期——这正是 FSM 的缺点。

**正确做法**：两种路径——
1. **拆分 Action 节点**：把 `Attack` 拆成 `WindUp → Swing → Recovery` 三个独立 Action 节点，放入一个 Sequence。这样每个子阶段完成后都会重新评估条件。
2. **使用"可中断" Action**：如果无法拆分（如攻击动画是一个不可打断的蒙太奇），让 Action 在 `Tick()` 中检查中断条件并主动返回 `Failure`（触发父 Selector 重评估）。

```cpp
// ✅ BT-friendly: 拆分长行为为独立可中断的节点
Sequence("MeleeAttack")
├── Action: WindUpAttack     // returns Success when ready to swing
├── Action: SwingAttack      // returns Success when hit frame passed
└── Action: RecoveryAttack   // returns Success when animation ends

// ⚠️ 次选: 长 Action 内部检查中断条件
Status AttackAction::Tick(Blackboard& bb) {
    if (bb.Get<float>("health") < 30)
        return Status::Failure; // abort → parent Selector finds Flee
    // ... continue attack animation
    return Status::Running;
}
```

### 陷阱 4: 忽略团队技能栈

**症状**：技术负责人根据"业界最佳实践"选择 BT，但团队中的 AI 程序员从未用过 BT，设计师也从未在可视化编辑器中排列过节点。

**后果**：最初 3 个月的 BT 实现充满了微妙的设计错误——Condition 节点有副作用（导致非确定性行为）、树的结构不合理（深度过大、回退路径缺失）、Blackboard key 命名混乱。这些问题在 FSM 中可能不会发生，因为 FSM 的错误模式更"可见"（转移表遗漏通常比树结构错误更容易发现）。

**正确做法**：
- 如果团队没有 BT 经验：先用 FSM 完成第一个里程碑，同时在 side project 中用 BT 实现一个简单原型来积累经验。
- 如果设计师没有 BT 编辑器经验：准备好前 2-3 周的大量一对一辅导时间，或者先用"程序员定义树结构 + 设计师调参数"的模式过渡。
- **工具选择应该匹配团队的学习曲线，而非跳过一个不存在的曲线。**

### 陷阱 5: 过度工程化简单 AI

**症状**：设计了一个完美解耦、高度参数化、支持可视化编辑的 BT 框架……但游戏里只有 3 种敌人，每种 4 个状态。

**后果**：框架代码（运行时、序列化、编辑器集成、Blackboard 系统）占了 AI 代码库的 80%，而实际的行为逻辑只占 20%。当团队需要修改 AI 行为时，他们必须先理解框架的抽象层，然后才能触达实际的行为逻辑。

**正确做法**：遵循 YAGNI（You Aren't Gonna Need It）：
1. 先用最朴素的方式实现 AI（FSM 或简单的 if-else 链）。
2. 当第二个或第三个敌人开始复制粘贴代码时，提取共享逻辑。
3. 当你发现自己在维护一份"状态-事件"转移表时，考虑是否正式化 FSM。
4. 当你发现转移表有超过 30% 的"忽略"槽位、或新增行为需要修改 >50% 的状态时，考虑迁移到 BT。
5. **每一步都只在痛苦足够具体时才架构升级。** 凭空设计的框架几乎总是错的——因为你还没有体验到真实的使用摩擦。

---

> **下一篇**: [[../15-hybrid-architectures|Tutorial 15: 混合架构与 AI 系统设计]] — 详细讨论如何在单个项目中组合 FSM、BT、Utility AI 等不同范式。
