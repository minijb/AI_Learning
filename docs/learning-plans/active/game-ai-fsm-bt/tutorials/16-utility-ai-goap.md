# Utility AI / GOAP / HTN 及其他 AI 范式

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 90min
> 前置知识: 14-fsm-vs-bt

---

## 1. 概念讲解

### 为什么需要超越 FSM 和 BT？

Tutorial 14 建立了一个基础认知：FSM 适合确定性顺序场景（≤8 种行为），BT 适合条件驱动的复杂行为（8-50 种行为）。但这两者在某些游戏类型中都会暴露结构性短板：

- **Sims-like 模拟游戏**：一个 NPC 有 8 种需求（饥饿、社交、娱乐、清洁……），每种需求以不同速率衰减，可选动作 50+ 种。BT 和 FSM 需要**为每个可能的上下文编写条件**——组合数爆炸。The Sims 团队给出的答案是 **Utility AI**。
- **战术射击游戏**：敌人需要动态规划"移动到掩体→投掷手雷→从侧翼开火"的序列，且环境变化导致同一目标每次的最优路径不同。BT 的树结构是**设计时固定**的，规划"两步之后做什么"需要 GOAP。
- **开放世界 RPG**：NPC 的日常行为（吃饭、工作、回家、社交）有内在的层次性——"工作"包含若干子任务，子任务又分解为原子动作。这些层次结构在 BT 中表现为过深的树嵌套，而 **HTN** 的逐层展开提供了更自然的表达。

三种范式各有其理论根源：Utility AI 来自决策理论（期望效用最大化），GOAP 来自自动规划（STRIPS），HTN 来自程序化知识表示。下面逐一深入。

### Utility AI：分数制行为选择

#### 核心思想

Utility AI 不维护状态转移、不执行树遍历。它在每一帧（或每隔 N 帧）做一件事：**对所有可能的动作计算效用分数，选择最高分执行。**

```
foreach action in available_actions:
    score = action.Evaluate(context)  // 0.0 ~ 1.0
select action with highest score
if selected_action != current_action:
    interrupt current, start selected
```

这个简单循环背后是三个关键设计决策：

1. **Curve（响应曲线）**：不是简单的 `if (hunger > 80) return 1.0`，而是一个从输入值到效用分数的**连续函数**。常用形式包括线性、Logistic（S 形）、分段多项式。例如：饥饿值从 0 到 100 映射为"吃饭"的效用——饥饿 0-20 时效用接近 0（不饿就不吃），饥饿 60-80 时斜率最陡（快速上升的进食倾向），饥饿 90-100 时效用接近 1（几乎一定要吃）。

2. **Multiplicative vs Weighted Sum scoring**：最简单的 Utility AI 使用加权和（Σ(wᵢ × scoreᵢ)）。**IAUS（Infinite Axis Utility System）** 则使用乘法组合：`final = 1.0 - Π(1 - AxisScoreᵢ)`。乘法组合的关键特性：最差的轴（接近 0）会把总分拉向 0，即使其他所有轴都很高。这更符合"致命因素"的直觉——NPC 即使社交需求极高（0.9），如果血量只有 5%（评分 0.05），就不会去参加派对。

3. **Reason-to-score 映射**：不是动作评估自己的条件，而是**独立的 Scorer 评估每个"理由"**。一个 `EatFood` 动作有多个 Reason（饥饿、食物美味度、社交用餐），每个 Reason 由独立的曲线/函数评估。动作的最终分数是这些 Reason 的组合。新 Reason 的添加不需要修改任何动作代码——只需要注册新的 Scorer。

#### The Sims 的做法

The Sims 3/4 的 AI 系统（被称为 "The Autonomy System"）是 Utility AI 最广为人知的工业化应用：

- 每个 Sim 有 ~8 种 Motive（Hunger, Energy, Social, Fun, Hygiene, Bladder, Environment, Comfort），每种以独立速率衰减。
- 环境中所有可交互对象向 Sim 广播"我能满足的需求"和"满足量"（例如：冰箱 → Hunger +40, Fun +5）。
- Sim 对所有可达交互计算效用：`Utility = Σ(Curve(MotiveLevel) × MotiveWeight × ObjectSatisfaction)`。
- 动作选择不是帧级：Sim 每 2-5 秒重新评估一次，避免行为抖动。

**关键设计洞察**：The Sims 中不需要显式的"状态"或"行为树"。角色行为从效用计算中**涌现**——饥饿的 Sim 自然靠近厨房，疲惫的 Sim 自然靠近床，既饿又疲惫的 Sim 在面对"边吃边看电视"的选项时，综合效用可能高于单纯吃饭或单纯睡觉。

#### 与 BT 的对比

| 维度 | Behavior Tree | Utility AI |
|------|--------------|------------|
| 行为选择机制 | 固定优先级顺序 + 条件门控 | 连续效用分数 + 最高分胜出 |
| 设计师心智模型 | "如果 A 比 B 更重要，把 A 放左" | "饥饿程度多高时才值得中断社交去吃饭？" |
| 新行为添加成本 | 在 Selector 中插入新子树 | 注册新 Action + 配置 Reason/Curve |
| 可预测性 | 高——按照树结构逐级 fall-through | 低——多个因素浮动互作用导致难以精确预测 |
| 调试难度 | 中——路径追踪 + 条件标注 | 高——需要看到所有候选动作的分数才能理解"为什么选了 A" |
| 适合场景 | 战术战斗 AI、确定性强场景 | NPC 日常、模拟游戏、多因素决策 |

Utility AI 的核心优势是**scale in design space, not code space**：从 5 个动作扩展到 50 个动作，代码复杂度基本不变（每个动作独立评分），而 BT 需要重新排布树结构和优先级。代价是**调试和调参**——设计师需要微调响应曲线的形状来避免行为振荡。

#### Dave Mark 的 IAUS

IAUS（Infinite Axis Utility System）由 Dave Mark 系统化提出并推广。其核心区别于简单 Utility 的地方：

- **Agent-relative input**：每个 Axis 代表一个"关注维度"（threat level, social need, proximity to goal）。Axis 不直接比较，而是各自独立地通过 response curve 映射到 reason score。
- **Canonical curve shapes**：IAUS 定义了四种标准曲线：线性递增、线性递减、钟形（peak at middle）、反钟形（valley at middle），每种由 3-4 个控制点参数化。
- **No global weights**：在 IAUS 中，权重隐含在曲线的 Y 轴范围内。一个曲线的最大值是 0.3 而另一个是 0.9，这意味着前者在任何输入下都不会产生超过 0.3 的贡献。这迫使设计师在每个动作的上下文中独立考虑每个轴的相对重要性，而非全局设定一个通用权重。

### GOAP：目标导向行动规划

#### F.E.A.R. 的 AI 问题

2005 年，Monolith Productions 在 F.E.A.R. 中面临的敌人 AI 需求是：需要表现出**看起来智能**的战术行为（利用掩体、侧翼包抄、投掷手雷、压制火力），但传统的 FSM/BT 在"动态产生行为序列"上存在先天限制。

Jeff Orkin 的解决方案是 **GOAP（Goal-Oriented Action Planning）**——一个受 STRIPS 规划器启发的架构：

1. AI 拥有一个**世界状态**（World State）：`{ HasWeapon=true, AtHealth=100, PlayerVisible=true, PlayerDistance=15 }`
2. AI 拥有一组**目标**（Goals）：`KillPlayer(priority=10)`, `Survive(priority=8)`, `Patrol(priority=3)`，每个目标有一个期望的世界状态。
3. AI 拥有一组**动作**（Actions）：每个动作有前置条件（Preconditions）和效果（Effects）。
4. 当目标激活时，**A\* 规划器**在世界状态空间中搜索，找到从当前状态到达目标状态的动作序列。

#### 核心组件

**World State**：一个键值对映射（通常用 `Dictionary<string, object>` 或位掩码）。是规划器的输入和动作效果的目标。

**GoapAction** 的定义：
- `Preconditions: Dictionary<string, bool>` — 执行此动作前必须满足的世界状态
- `Effects: Dictionary<string, bool>` — 执行此动作后世界状态如何改变
- `Cost: float` — 执行此动作的代价（用于 A\* 的 g(n)）
- `Perform(): IEnumerator` — 实际执行逻辑

**A\* 规划器**：状态节点是 WorldState，边是 GoapAction。启发式函数 h(n) = 当前状态与目标状态之间的差异度量（汉明距离或加权差异）。

#### 示例：KillPlayer 目标

```
Goal: KillPlayer
World State: {playerAlive=true, hasWeapon=true, nearPlayer=false, behindCover=false}

Available Actions:
- MoveToPlayer: {pre: {}, eff: {nearPlayer=true}, cost: 1}
- AttackPlayer: {pre: {nearPlayer=true, hasWeapon=true}, eff: {playerAlive=false}, cost: 1}
- PickupWeapon: {pre: {hasWeapon=false}, eff: {hasWeapon=true}, cost: 2}
- TakeCover: {pre: {}, eff: {behindCover=true}, cost: 1}

A* finds: [MoveToPlayer, AttackPlayer]  cost = 2
```

如果角色手中没有武器：`[PickupWeapon, MoveToPlayer, AttackPlayer]` cost = 4

如果加入掩体优先策略：`[TakeCover, PickupWeapon, MoveToPlayer, AttackPlayer]`——但如果 `TakeCover` 不直接影响 `nearPlayer` 或 `hasWeapon`，规划器需要评估前置条件链中的每一步。

#### 优势与代价

**优势**：
- **动作的可组合性**：新增一个 `ThrowGrenade` 动作（前置：有手雷、敌人在视线内；效果：造成伤害），不需要修改任何已有动作——规划器自动找到包含新动作的序列。
- **涌现行为**：设计师不需要预想"当敌人血量低且有手雷且玩家在掩体后时做什么"——规划器自动将 `LowHealth → TakeCover` + `HasGrenade → ThrowGrenade` 组合起来。
- **世界状态的解耦性**：动作之间只通过 WorldState 通信，无直接依赖。

**代价**：
- **规划器性能**：A\* 的节点扩展数 = `actions^depth`。50 个动作 × 深度 5 = 潜在搜索空间极大。F.E.A.R. 通过限制规划深度（3-5 步）和每帧单次规划来控制开销。
- **不可预测性**：同一个目标可能产生多个有效计划，哪个被选中取决于 A\* 的成本函数——这本身就是一个调参游戏。
- **难以注入"风格"**：设计一个"激进型"和"保守型"敌人，在 BT 中是调整树结构优先级；在 GOAP 中需要调整动作成本——间接且难以验证。

### HTN：分层任务网络

#### 与 GOAP 的本质区别

GOAP 和 HTN 都解决"从目标到动作序列"的问题，但方向相反：

- **GOAP**：从目标**反向搜索**——目标驱动，在世界状态空间中找路径。自动产生计划，但不可预测。
- **HTN**：从目标**正向展开**——设计师编写"复合任务"作为模板，运行时逐层分解为原子动作。可预测，但需要预先编写所有组合。

HTN 中的两个核心概念：

- **Compound Task（复合任务）**：不是原子执行单元，而是一个"待展开的任务名"。运行时，规划器在 Task Library 中查找该任务名对应的分解方法（Method）。
- **Method（分解方法）**：一个"将复合任务替换为子任务序列"的规则。可以包含条件（该方法在什么世界状态下适用）和子任务列表。

#### Killzone 的做法

Guerrilla Games 在 Killzone 2/3 中使用 HTN 驱动敌人 AI：

- 顶层复合任务：`FightPlayer`, `PatrolArea`, `Retreat`
- `FightPlayer` 分解为：`[SelectWeapon, MoveToPosition, EngageTarget, AssessThreat]`
- `EngageTarget` 再分解为：`[FindCover, SuppressFire, AdvanceCover, Attack]`
- 分解过程中的世界状态检查确保选择的 Method 与当前上下文匹配（例如：敌人距离 < 5m → 选择近战 Method 而非射击 Method）

HTN 的关键特性：**规划失败是可接受的**。在 GOAP 中，规划器无法找到计划意味着 AI 卡住；在 HTN 中，如果某个 Method 的条件不满足，系统尝试下一个 Method，如果全部失败，父任务报告失败，上层可以选择其他父任务。

#### HTN vs GOAP 对比

| 维度 | GOAP | HTN |
|------|------|-----|
| 搜索方向 | 反向（目标 → 当前状态） | 正向（复合任务 → 原子动作） |
| 计划来源 | 自动搜索产生 | 设计师编写模板 |
| 可预测性 | 低——计划是搜索涌现的 | 高——计划结构在设计时就确定了 |
| 新动作添加 | 只需注册 Action | 除注册 Action 外还需定义 Method |
| 规划成本 | O(actions^depth) | O(methods × max_decomposition_depth)，通常更低 |
| 适用场景 | 动作间组合爆炸的高变化环境 | 行为结构清晰、需要精确控制的场景 |

#### Horizon Zero Dawn 的做法

Guerrilla 在后 Killzone 时代转向了更成熟的 HTN 实现（用于 Horizon Zero Dawn 和 Horizon Forbidden West）。他们公开了以下经验：

- 并非所有行为都用 HTN——机器行为中最底层的运动控制使用小型 FSM（因为需要帧级确定性和低延迟）。
- HTN 主要负责"战术决策"层：扫描 → 选择攻击模式 → 执行攻击序列 → 评估结果 → 调整战术。
- Method 的编写由 AI 设计师完成，使用内部可视化工具。Method 的条件门控允许一个复合任务有 3-8 种不同的分解方式，根据世界状态择一。

### 五范式对比表

以下对比帮你快速定位各范式的设计空间：

| 维度 | FSM | BT | Utility AI | GOAP | HTN |
|------|-----|----|-----------|------|-----|
| **行为选择机制** | 状态转移 | 优先级遍历 | 效用评分 | A\* 规划 | 模板展开 |
| **可预测性** | 极高 | 高 | 低 | 低 | 高 |
| **每帧性能** | 最优（常数） | 优（O(深度)） | 次优（O(动作数)） | 较差（O(动作数^深度)） | 优（O(方法展开)） |
| **设计师友好度** | 状态量少时好 | 可视化后好 | 需要数学直觉 | 较差 | 可视化后好 |
| **涌现行为** | 否 | 有限 | 是（效用交互） | 是（规划组合） | 否 |
| **最适规模** | ≤15 状态 | 10-100 行为 | 20-100 动作 | 10-60 动作 | 20-80 复合任务 |
| **核心优势** | 简单确定性 | 模块化+复用 | 多因素平滑决策 | 动作自由组合 | 可控规划 |
| **核心弱点** | 组合爆炸 | 需要设计树结构 | 调参困难 | 规划成本+不可预测 | 需要预写所有组合 |

### 何时使用哪种范式

**Utility AI 最佳场景**：
- **模拟/生活类游戏**（The Sims 风格）：多维需求同时变化，动作选择需要平滑过渡而非硬切换。
- **RPG NPC 日常行为**：NPC 的行为选择由 6+ 个因素同时驱动（时间、天气、关系值、任务状态、健康、性格），BT 的树结构在这些因素交互面前会迅速膨胀。
- **开放世界生态系统**：动物的捕食/迁徙/休息行为由饥饿、威胁、繁殖需求共同决定——这些都是连续值而非二值条件。

**GOAP 最佳场景**：
- **战术射击**（F.E.A.R. 风格）：敌人拥有 20-50 种动作且环境高度可变，需要动态规划 3-5 步的序列。
- **潜行游戏**：NPC 的行为（巡逻→调查→警戒→追捕）变化由少量世界状态驱动，但每帧的"最优序列"可能因玩家位置而完全不同。
- **满足以下条件时请避免 GOAP**：
  - 团队没有专用的 AI 程序员来调试规划器
  - 需求要求 AI 行为高度可预测（QA 团队需要精确知道 AI 在每种情况下做什么）
  - 动作数量超过 60 且规划深度超过 6——A\* 的搜索空间将变得难以管理

**HTN 最佳场景**：
- **需要可控规划的 AAA 游戏**：当"涌现行为"是风险而非优势时——HTN 的模板展开提供了 GOAP 的"动作序列"能力，同时保留了可预测性。
- **关卡特化 AI**：不同的关卡可能需要同一类型 AI 的不同行为模式。HTN 允许设计师为每个关卡编写独立的 Method 集合。
- **有清晰行为层次的大型项目**：NPC 的战斗行为天然分层（战术 → 攻击模式 → 武器技能 → 动作），HTN 的逐层展开匹配这种领域结构。

**关键决策总结**：
- 玩家的**马**需要 AI？→ FSM（行为少，顺序性强）
- 敌人的**守卫**（巡逻→发现→追击）→ BT（中断频繁，条件驱动）
- 敌人的**战术小队**（掩体→手雷→侧翼）→ GOAP 或 HTN（需要动态规划序列）
- 城镇中的**NPC 居民**（吃饭、工作、回家、社交）→ Utility AI（多因素平滑决策）
- 你的团队**没有 AI 程序员**但需要做战术 AI？→ BT（UE5 原生支持，工业成熟）

---

## 2. 代码示例

### 示例 A：C# Utility AI —— NPC 日常行为

下面实现一个完整的 Utility AI 系统，包含可配置的响应曲线和基于 Reason 的评分架构。场景：NPC 的日常行为选择（吃饭、睡觉、工作、社交）。

```csharp
// ============================================================
// UtilityResponseCurve.cs — 响应曲线：将连续输入映射到效用分数
// ============================================================
public class UtilityResponseCurve
{
    // Four canonical curve shapes
    public enum Shape { Linear, Logistic, Bell, InverseBell }

    private readonly Shape _shape;
    private readonly float _midpoint;   // Input where slope is steepest
    private readonly float _steepness;  // Affects curve sharpness
    private readonly float _minOutput;
    private readonly float _maxOutput;

    public UtilityResponseCurve(Shape shape, float midpoint, float steepness,
                                float minOutput = 0f, float maxOutput = 1f)
    {
        _shape = shape;
        _midpoint = midpoint;
        _steepness = steepness;
        _minOutput = minOutput;
        _maxOutput = maxOutput;
    }

    public float Evaluate(float input)
    {
        float normalized = input; // input is already 0..1 in this example
        float raw;

        switch (_shape)
        {
            case Shape.Linear:
                raw = normalized;
                break;
            case Shape.Logistic:
                // Standard logistic: 1 / (1 + e^(-k*(x - x0)))
                raw = 1f / (1f + MathF.Exp(-_steepness * (normalized - _midpoint)));
                break;
            case Shape.Bell:
                // Gaussian-like: exp(-((x - midpoint)^2) / (2 * sigma^2))
                float sigma = 1f / _steepness;
                float diff = normalized - _midpoint;
                raw = MathF.Exp(-(diff * diff) / (2f * sigma * sigma));
                break;
            case Shape.InverseBell:
                // 1 - Bell
                float sigmaInv = 1f / _steepness;
                float diffInv = normalized - _midpoint;
                raw = 1f - MathF.Exp(-(diffInv * diffInv) / (2f * sigmaInv * sigmaInv));
                break;
            default:
                raw = normalized;
                break;
        }
        return _minOutput + raw * (_maxOutput - _minOutput);
    }
}
```

```csharp
// ============================================================
// UtilityReason.cs — 每个 Reason 对应一个评分维度
// ============================================================
public class UtilityReason
{
    public string Name { get; }
    private readonly UtilityResponseCurve _curve;
    private readonly Func<float> _inputSampler; // Reads the current input value
    private readonly float _weight;

    public UtilityReason(string name, UtilityResponseCurve curve,
                         Func<float> inputSampler, float weight = 1f)
    {
        Name = name;
        _curve = curve;
        _inputSampler = inputSampler;
        _weight = weight;
    }

    public float Evaluate()
    {
        float input = _inputSampler();
        float raw = _curve.Evaluate(input);
        return raw * _weight;
    }
}
```

```csharp
// ============================================================
// UtilityAction.cs — 一个可选行为
// ============================================================
public abstract class UtilityAction
{
    public string Name { get; }
    protected readonly List<UtilityReason> Reasons = new();

    protected UtilityAction(string name) => Name = name;

    public void AddReason(UtilityReason reason) => Reasons.Add(reason);

    // IAUS-style multiplicative combination
    public float EvaluateScore()
    {
        if (Reasons.Count == 0) return 0f;

        float product = 1f;
        foreach (var reason in Reasons)
        {
            float score = reason.Evaluate();
            product *= (1f - Math.Clamp(score, 0f, 1f));
        }
        return 1f - product; // IAUS formula: 1 - Π(1 - score_i)
    }

    public abstract void Execute(float deltaTime);
}
```

```csharp
// ============================================================
// UtilityAIController.cs — 每帧/每N帧评估所有动作
// ============================================================
public class UtilityAIController
{
    private readonly List<UtilityAction> _actions = new();
    private UtilityAction _currentAction;
    private float _evaluationCooldown;
    private readonly float _evaluationInterval = 0.5f; // Re-evaluate every 0.5s

    public void AddAction(UtilityAction action) => _actions.Add(action);

    public void Update(float deltaTime)
    {
        _evaluationCooldown -= deltaTime;

        if (_evaluationCooldown <= 0f)
        {
            EvaluateAndSelect();
            _evaluationCooldown = _evaluationInterval;
        }

        _currentAction?.Execute(deltaTime);
    }

    private void EvaluateAndSelect()
    {
        UtilityAction bestAction = null;
        float bestScore = float.MinValue;

        foreach (var action in _actions)
        {
            float score = action.EvaluateScore();
            if (score > bestScore)
            {
                bestScore = score;
                bestAction = action;
            }
        }

        if (bestAction != _currentAction)
        {
            _currentAction = bestAction;
        }
    }
}
```

```csharp
// ============================================================
// 使用示例：NPC 日常行为配置
// ============================================================

// --- Context: NPC with needs that decay over time ---
public class NPCContext
{
    public float Hunger;      // 0=full, 100=starving
    public float Energy;      // 0=exhausted, 100=energetic
    public float SocialNeed;  // 0=content, 100=lonely
    public float Wealth;      // 0=broke, 100=rich

    public NPCContext() { Hunger = 80f; Energy = 20f; SocialNeed = 50f; Wealth = 30f; }
}

// --- Building the AI ---
var npc = new NPCContext();
var controller = new UtilityAIController();

// EatFood action — driven by hunger (high hunger → high utility)
var eatFood = new UtilityAction("EatFood");
eatFood.AddReason(new UtilityReason(
    "Hunger",
    new UtilityResponseCurve(UtilityResponseCurve.Shape.Logistic, 0.5f, 8f),
    inputSampler: () => npc.Hunger / 100f,
    weight: 1f
));

// Sleep action — driven by low energy (inverse of energy → when tired)
var sleep = new UtilityAction("Sleep");
sleep.AddReason(new UtilityReason(
    "Fatigue",
    new UtilityResponseCurve(UtilityResponseCurve.Shape.Logistic, 0.5f, 8f),
    inputSampler: () => 1f - (npc.Energy / 100f), // Low energy = high fatigue
    weight: 1.2f // Sleep slightly more important than eating
));

// Socialize action — driven by social need
var socialize = new UtilityAction("Socialize");
socialize.AddReason(new UtilityReason(
    "Loneliness",
    new UtilityResponseCurve(UtilityResponseCurve.Shape.Linear, 0.5f, 1f),
    inputSampler: () => npc.SocialNeed / 100f,
    weight: 0.8f
));

// Work action — driven by wealth need AND sufficient energy
var work = new UtilityAction("Work");
work.AddReason(new UtilityReason(
    "WealthNeed",
    new UtilityResponseCurve(UtilityResponseCurve.Shape.Logistic, 0.7f, 6f),
    inputSampler: () => 1f - (npc.Wealth / 100f), // Poor → work more
    weight: 0.6f
));
work.AddReason(new UtilityReason(
    "CanWork",
    new UtilityResponseCurve(UtilityResponseCurve.Shape.Linear, 0.3f, 1f),
    inputSampler: () => npc.Energy / 100f, // Only work when not exhausted
    weight: 1f
));

controller.AddAction(eatFood);
controller.AddAction(sleep);
controller.AddAction(socialize);
controller.AddAction(work);
```

**关键设计点**：

- `CanWork` Reason 使用线性曲线检查能量水平——当能量极低时这个轴的分数接近 0，IAUS 的乘法组合会把 `Work` 的总分拉低到接近 0，即使 NPC 很穷。
- `evaluationInterval` 设为 0.5 秒避免帧级评估的行为振荡——这也是 Utility AI 在帧间平滑的关键参数。
- 每个动作的 Reaseon 独立——新动作（如 `WatchTV`: 娱乐需求 + 能量充足）只需注册新的 Reason，不触及已有代码。

### 示例 B：C# 简化 GOAP 规划器 —— 敌人 KillPlayer

```csharp
// ============================================================
// WorldState.cs — 键值对世界状态
// ============================================================
public class WorldState
{
    private readonly Dictionary<string, bool> _state = new();

    public WorldState Clone()
    {
        var clone = new WorldState();
        foreach (var kv in _state)
            clone._state[kv.Key] = kv.Value;
        return clone;
    }

    public bool Get(string key) =>
        _state.TryGetValue(key, out bool v) && v;

    public void Set(string key, bool value) => _state[key] = value;

    // Heuristic: count of mismatched keys vs goal
    public int DistanceTo(WorldState goal)
    {
        int diff = 0;
        foreach (var kv in goal._state)
        {
            bool current = Get(kv.Key);
            if (current != kv.Value) diff++;
        }
        return diff;
    }

    public bool Satisfies(Dictionary<string, bool> conditions)
    {
        foreach (var kv in conditions)
            if (Get(kv.Key) != kv.Value) return false;
        return true;
    }

    public void ApplyEffects(Dictionary<string, bool> effects)
    {
        foreach (var kv in effects)
            _state[kv.Key] = kv.Value;
    }
}
```

```csharp
// ============================================================
// GoapAction.cs — 带前置条件和效果的原子动作
// ============================================================
public abstract class GoapAction
{
    public string Name { get; }
    public float Cost { get; }
    public Dictionary<string, bool> Preconditions { get; } = new();
    public Dictionary<string, bool> Effects { get; } = new();

    protected GoapAction(string name, float cost = 1f)
    {
        Name = name;
        Cost = cost;
    }

    public bool IsViable(WorldState worldState) =>
        worldState.Satisfies(Preconditions);

    public WorldState Simulate(WorldState input)
    {
        var result = input.Clone();
        result.ApplyEffects(Effects);
        return result;
    }

    public abstract IEnumerator Perform(WorldState worldState);
}
```

```csharp
// ============================================================
// GoapPlanner.cs — A* 规划器
// ============================================================
public class GoapPlanner
{
    public Queue<GoapAction> Plan(WorldState current, WorldState goal,
                                   List<GoapAction> allActions, int maxDepth = 10)
    {
        // Priority queue by f(n) = g(n) + h(n)
        var openSet = new SortedSet<PlanNode>(new PlanNodeComparer());
        var closedSet = new HashSet<string>(); // state hash as string key

        var startNode = new PlanNode(current, null, null, 0f, current.DistanceTo(goal));
        openSet.Add(startNode);

        while (openSet.Count > 0)
        {
            var node = openSet.Min;
            openSet.Remove(node);

            // Check if goal satisfied
            if (node.State.Satisfies(goal._StateDict()))
            {
                return BuildPlan(node);
            }

            string stateKey = node.State._StateHash();
            if (closedSet.Contains(stateKey)) continue;
            closedSet.Add(stateKey);

            if (node.Depth >= maxDepth) continue;

            // Expand: try each action
            foreach (var action in allActions)
            {
                if (!action.IsViable(node.State)) continue;

                var newState = action.Simulate(node.State);
                float g = node.G + action.Cost;
                float h = newState.DistanceTo(goal);
                var child = new PlanNode(newState, node, action, g, h);
                child.Depth = node.Depth + 1;
                openSet.Add(child);
            }
        }

        return null; // No valid plan found
    }

    private Queue<GoapAction> BuildPlan(PlanNode leaf)
    {
        var plan = new Stack<GoapAction>();
        var current = leaf;
        while (current.Action != null)
        {
            plan.Push(current.Action);
            current = current.Parent;
        }
        return new Queue<GoapAction>(plan);
    }

    private class PlanNode
    {
        public WorldState State;
        public PlanNode Parent;
        public GoapAction Action;
        public float G;       // Cost so far
        public float H;       // Heuristic
        public float F => G + H;
        public int Depth;

        public PlanNode(WorldState state, PlanNode parent,
                        GoapAction action, float g, float h)
        {
            State = state; Parent = parent; Action = action; G = g; H = h;
        }
    }

    private class PlanNodeComparer : IComparer<PlanNode>
    {
        public int Compare(PlanNode a, PlanNode b)
        {
            int cmp = a.F.CompareTo(b.F);
            if (cmp != 0) return cmp;
            // Tie-breaker: prefer lower depth (shorter plans)
            return a.Depth.CompareTo(b.Depth);
        }
    }
}
```

```csharp
// ============================================================
// GoapAgent.cs — AI agent using the planner
// ============================================================
public class GoapAgent
{
    private readonly GoapPlanner _planner = new();
    private readonly List<GoapAction> _actions = new();
    private Queue<GoapAction> _currentPlan;
    private GoapAction _currentAction;
    private WorldState _worldState;

    public GoapAgent(WorldState initialState)
    {
        _worldState = initialState;
    }

    public void AddAction(GoapAction action) => _actions.Add(action);

    public void Update(float deltaTime)
    {
        if (_currentPlan == null || _currentPlan.Count == 0)
        {
            // No plan — replan
            var goal = SelectGoal();
            if (goal != null)
            {
                _currentPlan = _planner.Plan(_worldState, goal, _actions, maxDepth: 5);
            }
        }

        if (_currentPlan != null && _currentPlan.Count > 0)
        {
            _currentAction = _currentPlan.Peek();
            _currentAction.Perform(_worldState);
            // In real code, Perform returns a coroutine; on completion,
            // apply effects and dequeue:
            _worldState.ApplyEffects(_currentAction.Effects);
            _currentPlan.Dequeue();
        }
    }

    private WorldState SelectGoal()
    {
        // For this example, always return KillPlayer goal
        var goal = new WorldState();
        goal.Set("playerAlive", false);
        return goal;
    }
}
```

```csharp
// ============================================================
// 具体动作实现
// ============================================================

// PickupWeapon: {pre: {}, eff: {hasWeapon=true}}
public class PickupWeaponAction : GoapAction
{
    public PickupWeaponAction() : base("PickupWeapon", cost: 2f)
    {
        // Preconditions: none (can always try to find a weapon)
        Effects["hasWeapon"] = true;
    }

    public override IEnumerator Perform(WorldState ws)
    {
        yield return new WaitForSeconds(0.5f);
        ws.Set("hasWeapon", true);
    }
}

// MoveToPlayer: {pre: {}, eff: {nearPlayer=true}}
public class MoveToPlayerAction : GoapAction
{
    public MoveToPlayerAction() : base("MoveToPlayer", cost: 1f)
    {
        Effects["nearPlayer"] = true;
    }

    public override IEnumerator Perform(WorldState ws)
    {
        yield return new WaitForSeconds(1.0f);
        ws.Set("nearPlayer", true);
    }
}

// AttackPlayer: {pre: {nearPlayer, hasWeapon}, eff: {playerAlive=false}}
public class AttackPlayerAction : GoapAction
{
    public AttackPlayerAction() : base("AttackPlayer", cost: 1f)
    {
        Preconditions["nearPlayer"] = true;
        Preconditions["hasWeapon"] = true;
        Effects["playerAlive"] = false;
    }

    public override IEnumerator Perform(WorldState ws)
    {
        yield return new WaitForSeconds(0.3f);
        ws.Set("playerAlive", false);
    }
}

// TakeCover: {pre: {}, eff: {behindCover=true}}
public class TakeCoverAction : GoapAction
{
    public TakeCoverAction() : base("TakeCover", cost: 1f)
    {
        Effects["behindCover"] = true;
    }

    public override IEnumerator Perform(WorldState ws)
    {
        yield return new WaitForSeconds(0.8f);
        ws.Set("behindCover", true);
    }
}
```

**关键设计点**：

- `WorldState.DistanceTo()` 用作 A\* 的启发式：统计与目标状态不匹配的键数。这个启发式是**可接受的**（admissible）——因为每个动作最多改变有限数量的状态键，实际代价不会低于差异键数。
- `maxDepth = 5` 限制搜索深度——对于 50 个动作的场景，深度 5 意味着最多 `50^5` 个节点，但实际分支因子远小于 50 因为前置条件过滤了大量不可行动作。
- 动作的 `Perform()` 返回 `IEnumerator`——这与 Unity 协程模型匹配，允许动作跨多帧执行。在实际实现中，Agent 需要在动作完成后才出队并应用效果。

---

## 3. 练习

### 练习 1：扩展 Utility AI 并分析调参挑战

在示例 A 的 NPC 日常行为基础上：

1. 添加 3 个新动作：`WatchTV`（娱乐需求 + 能量 > 20%）、`GoShopping`（财富足够 + 社交需求中低）、`Exercise`（能量过高 + 健康需求）。
2. 为每个新动作创建对应的 `UtilityReason` 和响应曲线。
3. 设计一个场景让 NPC 在 `WatchTV` 和 `Socialize` 之间频率振荡（两种行为的效用分值在边界处交替领先），然后通过调整曲线参数（steepness，midpoint）来消除振荡。

**思考问题**：Utility AI 的调参为什么比 BT 更难？IAUS 的乘法组合在什么情况下会导致几乎所有动作的分数都被拉低（即 NPC 什么都不想做）？如何防止这种情况？

### 练习 2：扩展 GOAP 并追踪规划路径

在示例 B 的 KillPlayer 规划器基础上：

1. 添加 `HealAction`（前置：`health < 50`，效果：`health = 100`，cost = 2）和 `ThrowGrenadeAction`（前置：`hasGrenade ∧ nearPlayer ∧ behindCover`，效果：`playerAlive = false`，cost = 3）。
2. 用纸笔（或代码添加日志）追踪规划器在以下场景下的搜索路径：
   - 敌人武器就绪，已近玩家 → 规划结果？
   - 敌人无武器，血量 < 30 → 规划器会加入 Heal 还是直接捡武器？
   - 敌人有手雷在掩体后 → 路径长度和成本的变化？
3. 确认：为什么 `AttackPlayer` 的 cost = 1 而 `ThrowGrenade` 的 cost = 3？这种成本差异如何影响规划器在两种攻击方式间的选择？

**思考问题**：如果加入 20 个更多样的动作（使用医疗包、呼叫支援、设置陷阱、使用烟雾弹……），A\* 规划的搜索空间会如何增长？你可以用什么策略（启发式改进、规划结果缓存、增量重规划）来控制开销？

### 练习 3（可选）：同一场景 × 三种范式

设计一个简单的 AI 场景：**敌人守卫**——需要巡逻，发现玩家时追击/攻击，血量低时找掩体/撤退。

1. 用 **BT** 实现伪代码（树结构图 + 关键节点逻辑，参考 Tutorial 14 示例）。
2. 用 **GOAP** 定义目标、世界状态和动作集合，列出规划器可能产生的所有有效计划。
3. 对比两种方案在以下维度：**编写/配置难度**、**新增"投掷烟雾弹后从侧翼攻击"行为的修改量**、**调试时理解"为什么 AI 现在做了 X"的难度**。

**无标准答案**——这个练习的价值在于你形成自己的判断，并在面试中能够论证它。

---

## 4. 扩展阅读

- **GOAP 原始论文**：Jeff Orkin, *"Applying Goal-Oriented Action Planning to Games"* (2003) — 首次系统描述 F.E.A.R. 中的 GOAP 架构，包含规划器细节和与 FSM 的对比。PDF 可在 GDC Vault 或 Jeff Orkin 个人主页找到。
- **Three States and a Plan: The A.I. of F.E.A.R.**：Jeff Orkin, GDC 2006 — 更侧重于 F.E.A.R. 中 GOAP 的生产级实现，包括规划器的性能优化和与动画系统的集成。
- **Dave Mark's IAUS GDC Talks**：
  - GDC 2010: *"Architecting a Utility-Based AI System"* — IAUS 的系统设计
  - GDC 2012: *"Improving AI Decision Modeling Through Utility Theory"* — 响应曲线的数学基础
  - GDC 2015: *"Building a Better Centaur: AI Beyond the Horizon"* — Utility AI 与 BT 的混合架构
- **Killzone AI**：
  - Mikko Mononen, GDC 2009: *"The AI of Killzone 2"* — HSM/HTN 混合架构详解
  - Arjen Beij, GDC 2012: *"Creating the AI for Killzone 3's Multiplayer Bots"* — 多人 Bot AI 的 HTN 实践
- **Game AI Pro 系列**（CRC Press，全部免费 PDF 在 gameaipro.com）：
  - *Game AI Pro 1*, Chapter 8: "Exploring the HTN Planner" (Troy Humphreys) — HTN 规划器的完整 C++ 实现
  - *Game AI Pro 1*, Chapter 30: "An Introduction to Utility Theory" (Dave Mark & Kevin Dill) — IAUS 的形式化定义
  - *Game AI Pro 2*, Chapter 25: "Beyond Behavior: Evolving Agent Architectures" — GOAP、Utility、HTN 的演化关系
  - *Game AI Pro 3*, Chapter 8: "The Simplest AI Trick in the Book" (Bobby Anguelov) — 分层 Utility + BT
- **Horizon Zero Dawn**：Arjen Beij, GDC 2017: *"Decima AI: From Killzone to Horizon Zero Dawn"* — Guerrilla 如何从 Killzone 的 HTN 演化到 Horizon 的开放世界 AI 架构。
- **STRIPS 规划器**：Richard Fikes & Nils Nilsson, *"STRIPS: A New Approach to the Application of Theorem Proving to Problem Solving"* (1971) — GOAP 的理论前身，理解 STRIPS 就能理解为什么 GOAP 使用 `{preconditions, effects}` 的动作模型。

---

## 常见陷阱

### GOAP 规划器成本爆炸

**症状**：AI 在动作多（>40）时出现明显的帧时间尖刺，规划器响应延迟导致 AI 行为"慢半拍"。

**根因**：A\* 的搜索空间是 `actions^depth`，虽然前置条件过滤掉大量不可行动作，但在"弱前提"动作（`pre: {}`，如 `MoveToPlayer`、`TakeCover`）面前，分支因子仍然很大。

**补救措施**：
1. **Capped planning**：硬限制深度（如 maxDepth=5）和每帧最大扩展节点数（如 200）。
2. **Plan caching**：相同世界状态 → 复用上次规划结果。对大量 NPC 共享相同行为的场景有效（如 RTS 的小兵）。
3. **Hierarchical planning**：先规划"任务层"（进攻/防守/撤退），再在任务内规划具体动作——将搜索空间从 50^5 降为 10^2 + 5^3。
4. **Staggered evaluation**：不同 NPC 在不同帧规划，而非所有 NPC 同帧规划。

### Utility AI 动作振荡（Flip-Flopping）

**症状**：NPC 在两种行为之间以高频率来回切换（吃饭→社交→吃饭→社交……每 0.5 秒切换一次）。

**根因**：两个动作每次评估时的效用分数仅相差 0.01-0.03，世界状态的微小变化（某需求衰减了 0.1）导致最高分交替。

**补救措施**：
1. **Hysteresis（滞后）**：新动作的分数必须超过当前动作分数 + 阈值（如 0.1）才能切换。这是控制理论的标准方法。
2. **Cooldown**：动作切换后锁定最短执行时间（如 3 秒），在此期间不重新评估。
3. **Running score bonus**：给当前正在执行的动作一个固定的"惯性加分"（如 +0.05），让切换需要显著性差异。
4. **Commitment system**：评估频率低于动作执行时间（如每 2 秒评估一次，动作最短执行 5 秒）。

### HTN 计划展开爆炸

**症状**：HTN 的复合任务在分解过程中产生过多的递推深度（Method A 分解出 Compound Task B，B 分解出 Compound Task C……），导致每帧遍历的 Method 数过多。

**根因**：Method 编写时缺乏"基例"（直接分解为原子任务的分支），所有 Method 都至少分解出一个复合子任务——形成无限递推路径。

**补救措施**：
1. **每个复合任务至少有一个原子 Method**——这是 HTN 正确性的必要条件。
2. **Max decomposition depth**：硬上限（如 6 层），超限则报告规划失败。
3. **Pre-check 条件**：Method 的条件应该在开始分解前就排除不可行的路径，而非分解后再发现条件不满足。

### 期待 GOAP 取代设计师

**反模式**：团队引入 GOAP 时的隐含假设是"只要定义好动作和目标，AI 就会自动产生有趣的行为"。

**现实**：涌现行为只有在动作集合**经过了充分的设计**时才产生。一个糟糕的 GOAP 配置（动作前置条件太宽、成本函数粗糙、世界状态键不足）产生的行为不是"涌现的战术"，而是"看起来像 bug 的随机行为"。

**正确的心态**：GOAP 解决的是**动作组合的排列空间**问题——你不用手动编写"掩体→手雷→侧翼"这个序列，但你需要确保三个动作各自的前置条件、效果和成本使得**在合理的上下文中，这三个动作组成一个可行的计划**。GOAP 不是魔法——它是自动化的动作编排工具，而编排质量取决于你输入的数据质量。

### 过度依赖涌现行为

**适用于所有三种范式**：Utility AI、GOAP 和 HTN 都可能产生"在没有显式编写的情况下，AI 表现出了设计意图之外的行为"——这是刀的两面。

一方面，这正是选择这些范式的理由——比 BT/FSM 更丰富的行为多样性。另一方面，**玩家会注意到模式**：如果 Utility NPC 总是在饥饿 61% 时中断社交去吃饭（因为曲线在 60% 处斜率最陡），这就成了可被玩家预测的"机械节奏"，而玩家对"机械的涌现"的宽容度远低于"设计的确定性"。

**防护措施**：
- 在所有分数计算中加入少量噪声（±5%），打破输入→行为的一一对应。
- 为关键行为保留"设计过的确定性覆盖"——无论效用分数如何，某些硬约束（如 Boss 的阶段转换）应该用 FSM/BT 控制。
- 提供运行时可视化：展示所有动作的当前分数、响应曲线和世界状态——这不仅用于调试，也用于设计师理解"涌现"是从哪里来的。
