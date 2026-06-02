# AAA 案例研究: 游戏 AI 工业实践

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 01-16 (所有前置教程)

---

## 1. 概念讲解

### 为什么需要案例研究？

经过 Tutorial 01-16，你已经掌握了 FSM、HSM、BT、Utility AI、GOAP、HTN 的全部理论、实现和选型框架。但理论有一个盲区：**它告诉你工具怎么用，却不告诉你为什么某个团队选择了这个工具而不是那个，他们在哪些地方踩了坑，以及哪些决定是技术驱动的而哪些纯粹是组织约束。**

案例研究填补这个盲区。下面七个案例每一条都来自 GDC 演讲、Game AI Pro 文章和开发者访谈——不是推测，是当事人公开讲述的决策过程。理解这些决策背后的约束和权衡，是你在面试中能把"我了解 BT"提升到"我能解释为什么 Halo 2 放弃 FSM 转向 BT"的关键。

### 案例 1: Halo 2/3 (Bungie) — 行为树的起源

#### 背景

2001 年 Halo: Combat Evolved 发售时，Bungie 的敌人 AI 使用的是一个相对传统的 FSM 架构。精英（Elite）有约 15-20 个状态，豺狼（Jackal）和咕噜人（Grunt）更少。这个系统在单兵种、简单战斗场景下完全够用。

Halo 2（2004）的需求变了：双持武器、可驾驶载具、队友 AI、动态难度缩放、多兵种协同战术。FSM 开始断裂。

#### 为什么 FSM 不够用了？

Damian Isla 在 GDC 2005 的演讲 *"Managing Complexity in the Halo 2 AI"* 中总结了三个致命问题：

1. **状态组合爆炸**。一个精英在 Halo 2 中可能需要：战斗/非战斗 × 健康/护盾破裂 × 持枪/持剑/空手 × 有掩体/无掩体 × 有队友/独行。平面 FSM 需要 O(2^N) 个状态来表示这些组合。HSM 能压缩，但转移边仍然跨越多层。

2. **行为抢占的复杂性**。在 Halo 1 中，精英的行为优先级是硬编码的：战斗 > 搜索 > 空闲。Halo 2 需要动态优先级——有时候撤退比战斗更重要，有时候投掷手雷优先于射击，且这种优先级关系取决于战术上下文（是否有队友掩护、是否在载具附近）。

3. **设计迭代速度**。Bungie 的 AI 设计团队包含非程序员。在 FSM 中，设计师添加一个新行为需要程序员修改多个状态的转移规则。Isla 说："设计团队需要能够在没有工程师参与的情况下独立添加、调整、删除行为。"

#### 解决方案："优先级行为列表"（即后来的行为树）

Isla 设计的系统不是教科书行为树（这个术语当时还未定型），而是一个"从根开始每帧重新评估的优先级行为列表"：

- 行为节点是自包含的决策模块，每个节点检查自己的前置条件，条件为真时执行，执行中返回 Running。
- 节点按优先级从左到右排列。每帧从最高优先级节点开始评估，找到第一个条件满足的节点就开始执行。
- 核心洞察：**系统不记忆"上次在哪个状态"。每帧重新问"现在最重要的事是什么？"**

这个设计解决了所有三个问题：
- 组合爆炸消失了——每个行为维度是一个独立节点，不产生笛卡尔积。
- 优先级由节点顺序直接表达，拖拽节点就改变优先级。
- 设计师可以独立新增行为——只需要写一个新节点的条件/动作逻辑并插入合适位置。

#### 小队协调系统

Halo 2 的另一个突破是**小队 AI（Squad AI）**。在 Halo 1 中，每个敌人独立行动。Halo 2 引入了一个分层协调系统：

```
Encounter Director（遭遇战导演）
  ├── Squad Leader（小队长）
  │     ├── Role: Suppressor（压制者） — 持续开火压制玩家
  │     ├── Role: Flanker（侧翼）     — 绕路包抄
  │     └── Role: Grenadier（掷弹兵） — 投掷手雷逼迫玩家移动
  └── Individual BT（个体行为树）
```

工作流程：
1. Encounter Director 评估战场态势（玩家位置、掩体分布、小队伤亡）。
2. Squad Leader 根据态势分配角色——确保任何时候至少有一个压制者和一个侧翼者。
3. 每个角色的行为树独立运行，但通过 Blackboard 共享信息（如"侧翼者已就位，压制者可以推进"）。

Isla 后来在演讲中提到，这个系统的关键设计决策是**角色分配与角色执行分离**——Squad Leader 只负责分配角色，不负责角色如何完成角色。这样新增一个角色类型（如"自爆兵"）不需要修改 Squad Leader 的逻辑。

#### 性能考量 — Xbox 360

Halo 3（2007）在 Xbox 360 上运行。核心约束：
- 主频 3.2 GHz PowerPC，三核六线程，但 AI 通常只分到 0.5-1 个核心。
- 同时活跃的 AI 实体约 20-40 个。
- 每帧 AI 预算约 3-5ms。

Bungie 的优化策略：
- **条件缓存**。同一个条件（如"玩家在视野内吗？"）可能被多个行为节点检查。系统缓存条件结果，一个感知帧内只计算一次。
- **行为标签（Behavior Tags）**。给每个行为节点打标签（如 `combat`、`movement`、`investigation`），避免互斥行为同时激活——如果 `combat` 标签的行为已在 Running，跳过其他 `combat` 标签节点。
- **LOD 系统**。远处的敌人降低评估频率（每秒 2 次而非每帧 30 次），只保留关键行为（移动、受击反应）全频率。

#### 启示

Halo 2 的案例不是因为 Bungie"发明了行为树"而重要——是因为它展示了**架构选择是被需求压力逼出来的**。如果 Halo 2 的 AI 需求和 Halo 1 一样，Bungie 永远不会从 FSM 迁移。当你做技术选型时，先问：我的需求复杂度到拐点了吗？

---

### 案例 2: Killzone 2/3 (Guerrilla Games) — HTN 的工业应用

#### 背景

Guerrilla Games 的 Killzone 系列是 PS3 独占的 FPS。Killzone 2（2009）和 Killzone 3（2011）使用了一种与当时行业主流（BT）不同的 AI 架构：分层状态机（HSM）驱动的**层次任务网络（HTN）规划**。

#### 为什么 HTN 而非 BT？

Guerrilla 的 AI 程序员在 GDC 演讲中解释了他们的推理：

1. **战场需要"计划感"**。Killzone 的战斗场景强调阵地推进——敌人需要在掩体间移动、相互掩护、逐步推进。BT 的每帧重评估模型可能导致行为碎片化——敌人可能在"射击"和"移动"之间频繁切换，看起来不像一个有意图的士兵。HTN 的"先规划一个完整序列再执行"模型更匹配这种"有意图"的行为风格。

2. **设计师作者体验**。HTN 的"计划库"（Plan Library）——一组预定义的"如何完成目标"的配方——对设计师来说比 BT 更直观。设计师思考的是"ISA 士兵要压制玩家，他会怎么做？找掩体 → 探头 → 点射 → 撤回 → 换掩体"。这个序列可以作为一个完整计划录入。

3. **可预测性 vs 灵活性**。HTN 提供了比 GOAP 更可预测的行为（因为计划是预定义的），同时比 BT 更结构化的序列执行。对于 Killzone 这种高度脚本化的战役关卡，可预测性非常重要——设计师需要精确控制敌人何时推进、何时撤退。

#### HTN 架构细节

```
HSM 顶层（个体 AI 状态机）:
  Idle
  ├── Combat
  │     ├── HTN Planner  ← 在 Combat 状态下激活
  │     │     ├── Goal: SuppressPlayer
  │     │     │     └── Plan: FindCover → PeekOut → BurstFire → Withdraw
  │     │     ├── Goal: AdvancePosition
  │     │     │     └── Plan: FindNextCover → Overwatch(teammate) → MoveToCover
  │     │     └── Goal: Retreat
  │     │           └── Plan: SmokeGrenade → MoveToSafeZone
  │     └── FSM（计划执行中）
  └── Dead
```

关键设计点：
- **HSM 作顶层**。HSM 管理大粒度的行为模式切换（Idle → Combat → Dead），HTN 在 Combat 状态内部处理战术决策。
- **计划库（Plan Library）**。设计师通过数据文件定义"如何达成一个目标"的计划模板。每个计划是一系列有序步骤，步骤可以是原子动作或子目标（递归展开）。
- **重规划（Re-planning）**。当计划中的某个步骤失败（如"移动到掩体 A"时 A 被炸毁），HTN 规划器尝试替代分解。如果当前目标的所有计划都失败，回退到上一级目标重新选择。

#### 性能 — PS3

PS3 的 Cell 处理器以难以编程著称（1 个 PPE + 6 个可用 SPE）。Guerrilla 的 AI 运行在 PPE 上，预算是每帧 2-3ms（与渲染、物理共享）。

优化措施：
- **计划缓存**。一旦 HTN 规划出一个计划，在执行期间不重新规划（除非步骤失败）。这与 GOAP 的"每帧或每次状态变化都重规划"形成对比——HTN 节省了大量规划开销。
- **计划库限制深度**。递归展开最多 3 层，防止规划爆炸。

#### 事后反思

Guerrilla 在 2011 年 GDC 上坦率地承认了 HSM+HTN 架构的局限性：

> "当你需要一种新行为时，你必须在层次中找到正确的位置，然后检查它是否与兄弟状态的转移规则冲突。"

这正是行为树解决的问题。如果重新开始，Guerrilla 表示可能会考虑 BT 作为顶层架构，但在内部的战术序列仍然使用 HTN 式的计划执行。

#### 启示

Killzone 的案例展示了**一支团队如何根据游戏的特定需求（阵地战、需要"计划感"、关卡脚本化程度高）选择了一个非主流的方案并让它工作**。它也提醒我们：事后看来更"现代"的解决方案（BT）不一定在当时的具体约束下更优。

---

### 案例 3: F.E.A.R. (Monolith) — GOAP 的先驱

#### 背景

2005 年的 F.E.A.R.（First Encounter Assault Recon）被广泛认为是 AI 史上的里程碑。玩家普遍感知敌人"很聪明"——他们会动态寻找掩体、包抄、相互掩护、撤退重组。这种"智能感"来自 Jeff Orkin 设计的 **GOAP（Goal-Oriented Action Planning）** 系统。

#### GOAP 核心架构

GOAP 的核心理念：**不给 AI 预设行为序列，让 AI 自己规划如何达成目标。**

```
F.E.A.R. 的 AI 架构:

感知系统 → World State（世界状态）
                ↓
          Goal Selector（目标选择器）
                ↓
          A* Planner（A* 规划器）← Action Set（动作库）
                ↓
          Plan（动作序列）→ 执行 → 感知 → 重规划
```

#### 为什么 GOAP 创造了"智能感"？

传统 FSM 或 BT 的 AI 行为是设计者预定义的："如果玩家在掩体后，投掷手雷。"玩家很快学会了敌人的行为模式并加以利用。

F.E.A.R. 的 GOAP 系统不同：

1. **动态目标选择**。每个 AI 每几秒重新评估"我现在最应该做什么"。目标包括 `KillPlayer`（消灭玩家）、`StayAlive`（保命）、`FlankPlayer`（包抄）。目标选择的依据是 World State——自身的血量、弹药、位置，以及玩家和队友的状态。

2. **规划产生 emergent 行为**。AI 不"知道"如何包抄——它只知道有一组可用动作（`MoveTo`、`FireAt`、`Reload`、`ThrowGrenade`、`TakeCover`），A* 规划器根据当前 World State 寻找从现有状态到达 Goal 的动作序列。结果：
   - 一个 AI 发现正面对枪打不中，自动寻找侧翼掩体路线。
   - 队友被压制时，另一个 AI 投掷手雷逼迫玩家离开掩体。
   - 血量低且弹药不足时，AI 选择撤退而非送死。

3. **玩家无法预测**。因为规划基于动态 World State，同一个敌人在不同局势下做出不同选择。玩家不能简单地"等他探头就爆头"——有时候他探头，有时候他绕路。

#### 技术细节：A* 规划器

GOAP 把动作规划建模为图搜索：

- **节点** = World State（所有相关变量的快照：位置、血量、弹药、玩家位置等）
- **边** = Action（一个动作有前置条件 Precondition 和效果 Effect）
- **启发式函数** = 当前 World State 到目标 World State 的估计距离
- **A*** = 从起始状态搜索到目标状态的动作序列

一个具体例子：

```
Goal: KillPlayer
当前 World State: { hasWeapon: true, playerVisible: false, playerAt: (10,20) }

Action Set:
  Reload:     pre: { ammoLow: true }       → effect: { ammoLow: false }
  MoveTo(x):  pre: {}                       → effect: { position: x }
  FireAt:     pre: { hasWeapon: true, playerVisible: true } → effect: { playerAlive: false }

规划结果: [MoveTo(10,20), FireAt]
```

#### 规划的成本

GOAP 的 A* 规划在敌人数量增多时可能成为性能瓶颈。F.E.A.R. 使用的优化：

- **World State 精简**。只包含约 15-20 个布尔/枚举变量，而非完整的游戏状态。这些变量经过精心挑选，是"对决策有影响的"最小集合。
- **规划频率控制**。不是每帧重规划。每个 AI 在以下时机重规划：当前计划执行完毕、计划中的步骤失败、World State 发生重大变化（如被击中）。
- **规划深度限制**。A* 搜索深度上限通常为 5-8 步，避免搜索爆炸。配合一个合理的启发式函数，大多数规划在 0.1-0.5ms 内完成（每个 AI）。
- **同时活跃的 AI 数量**。F.E.A.R. 的关卡设计保证同时与玩家交战的敌人不超过 5-8 个——这不是技术限制，而是设计哲学（小规模高强度枪战）。更多的敌人是关卡后期的增援，在前一批被消灭后才激活。

#### 调优挑战

Orkin 在后来的访谈中坦言了 GOAP 的主要挑战：

1. **"聪明"不等于"好玩"**。太聪明的 AI 会让玩家沮丧——如果敌人总是完美包抄，玩家会觉得不公平。F.E.A.R. 的解决方案是给 AI 注入"不完美的感知"——他们偶尔忽略玩家位置、选择次优掩体、在包抄路径上故意暴露自己。

2. **行为可解释性**。当一个 AI 做出了意料之外的行为——比如没有按预期投掷手雷——开发者很难确定这是规划器的"合理"输出还是 bug。调试 GOAP 需要可视化规划过程和 World State 快照。

3. **动作库的完备性**。如果可用动作不足以从当前 World State 到达目标，规划器返回失败，AI 进入 fallback 行为。确保动作库"覆盖"所有可能的状态组合是一项持续的工作。

#### 启示

F.E.A.R. 的 GOAP 系统展示了**规划如何创造 emergent 行为**——不需要手动设计"包抄"行为，系统通过组合基本动作自然产生包抄。但代价是：规划和调试的复杂性、性能约束、以及"太聪明反而不好玩"的设计挑战。

---

### 案例 4: The Sims (Maxis) — 效用 AI 的极致应用

#### 背景

The Sims 系列面临一个独特的 AI 挑战：模拟数百个市民的日常生活，每个市民有 8 种需求（饥饿、精力、社交、娱乐、卫生、膀胱、环境、舒适），数千种可能的交互（吃饭、睡觉、聊天、看电视、洗澡、上厕所……），市民的行为需要看起来"合理且有个性"。

这不是"选哪个目标"的问题——所有需求同时竞争，且优先级随需求数值动态变化。FSM 不可能（"吃饭"和"上厕所"是平级的还是有严格顺序？），BT 不合适（行为之间不是简单的优先级关系，而是多因素权衡）。

#### 解决方案：效用 AI（Utility AI）

Maxis 使用的效用系统——后来由 Dave Mark 形式化为 **IAUS（Infinite Axis Utility System）**——的核心是**评分制决策**：

1. **需求生成分数**。每个需求（如饥饿）根据当前数值生成一个"需求紧迫度"分数。饥饿值越低，分数越高。
2. **交互也有分数**。每个可用的交互（如"从冰箱取食物吃"）根据以下因素计算一个总分数：
   - 该交互满足什么需求？（吃饭满足饥饿）
   - 满足的效率如何？（一顿饭恢复多少饥饿值？）
   - 距离多远？（需要走到冰箱，距离影响分数）
   - 当前情绪/性格修正？（一个"美食家"市民对高质量食物的评分更高）
3. **选择最高分的交互**。系统不需要知道"现在该吃饭还是该睡觉"——它只需要为所有可用交互打分，选最高分。

#### 数学本质

效用 AI 的决策函数可以写为：

```
Score(action) = Σ w_i × Curve_i(input_i)
```

其中：
- `input_i` 是第 i 个考虑因素（如当前饥饿值、到达冰箱的距离）
- `Curve_i` 是一个响应曲线（Response Curve），将输入映射到 0-1 的"合意度"
- `w_i` 是该因素的权重

**响应曲线是效用 AI 最强大的设计工具。** 它不是简单的"饥饿 < 30 就去吃饭"，而是一条连续曲线——饥饿值 80 时吃饭的欲望是 0.1，饥饿值 20 时是 0.9。这种连续性创造了平滑、可信的行为过渡。

#### 性格系统

Sims 的每个市民有不同的性格特征（如"懒惰"、"美食家"、"社交达人"、"洁癖"）。效用 AI 中，性格通过**修改权重和曲线**来表达：

- 懒惰市民："运动"和"清洁"交互的基础分数被下调。
- 美食家市民：高质量食物的评分曲线更陡。
- 社交达人：社交交互的分数被持续上调，甚至在其他需求中等时也会优先社交。

这种设计的美妙之处：**不需要为每种性格组合写独立的行为逻辑**。同一个评分框架 + 不同的曲线/权重参数就能产生截然不同的行为模式。

#### 调优挑战

Score 系统的一个经典问题是**权重地狱（Weight Hell）**：面对数百种交互，调整权重使行为"看起来合理"是一场噩梦。Dave Mark 的方法论：

1. **先定义"正确"行为的案例**。一个健康的、中性的市民在典型条件下应该优先做什么？把案例调对。
2. **用响应曲线而非权重做微调**。响应曲线是可视化的——你画一条曲线就定义了"饥饿值与吃饭欲望的关系"——比调整一个抽象的数字直观得多。
3. **自动化测试**。Maxis 为 The Sims 3/4 建立了批量模拟测试：以 100 倍速度运行 10 个市民 48 模拟小时，统计每个交互的频率，检查是否有市民饿死、尿裤子、或从不社交。

#### 启示

The Sims 的案例展示了**当行为选择需要同时考虑多个竞争的、连续的维度时，效用 AI 是最自然的选择**。FSM 和 BT 本质上是离散的、优先级驱动的——它们不擅长处理"A 的紧迫度是 0.7，B 的紧迫度是 0.65，同时 C 因为距离太远被降权到 0.4"这种决策。

---

### 案例 5: The Last of Us / Uncharted (Naughty Dog) — 混合分层架构

#### 背景

Naughty Dog 以"电影化叙事"著称——他们的游戏在开放战斗和高度脚本化的关卡片段之间无缝切换。这对 AI 系统提出了独特挑战：如何让 AI 在自由战斗中表现智能，同时又能在脚本化场景中精确执行导演意图？

#### 分层架构

Naughty Dog 使用了一个三层架构（来源：GDC 演讲和 Game AI Pro 文章）：

```
第 3 层: 脚本层（Script Layer）
  - 关卡特定逻辑
  - 触发器和 setpiece 事件
  - 导演控制（"现在让敌人撤退到下一个房间"）

第 2 层: 战术层（Tactical Layer / Behavior Tree）
  - 战斗决策：攻击/掩体/侧翼/撤退
  - 感知系统输出驱动
  - 可复用的 BT 节点库

第 1 层: 执行层（Execution Layer / Animation FSM）
  - 动画状态机
  - 寻路和移动
  - 物理交互
```

#### "脚本跃迁"模式

Naughty Dog 的 Jonathan Stein 描述了一个反复出现的模式——**脚本跃迁（Script Escalation）**：

1. 关卡设计师先用脚本（Script Layer）实现一个新的 AI 行为原型——比如在船甲板摇晃时 AI 需要抓住栏杆稳住。
2. 如果这个行为在测试中被认为对全局 NPC 都有用，工程师将其"提升"为可复用的 BT 节点。
3. BT 节点在后续关卡中可通过 Blackboard 参数化（如"抓握时间 = 2.0s"，"摇晃阈值 = 0.5"）。

这种模式让 Naughty Dog 可以**快速原型而不承诺长期架构**。如果脚本行为只在特定关卡出现一次，它就留在 Script Layer，不会污染可复用代码。

#### 同伴 AI 问题（Buddy AI Problem）

The Last of Us 中的一个核心挑战是同伴 AI——Ellie（或其他同伴）需要：
- 在战斗中不被敌人发现（虽然敌人实际上"看不见"她来避免挫败感）
- 在玩家需要时提供帮助（递弹药、呼叫敌人位置）
- 在剧情关键时刻出现在特定位置
- **不能挡路、不能推玩家、不能看起来愚蠢**

Naughty Dog 的解决方案：
- **双层感知**。同伴有一个"逻辑感知"（追踪敌人位置、掩体位置、玩家意图）和一个"视觉感知"（仅用于反馈给玩家——如 Ellie 看向敌人方向）。
- **情境意识系统**。同伴的 BT 节点可以读取"剧情紧张度"——在紧张场景中优先隐蔽，在放松场景中优先互动。
- **玩家意图预测**。系统追踪玩家的输入历史和移动方向，预测玩家"想做什么"，同伴据此调整——如果玩家反复尝试进入某个建筑，同伴会移动到门口等待而不是挡路。

#### 启示

Naughty Dog 的案例展示了**AI 架构服务于游戏的整体设计目标**——不是追求"最聪明的 AI"，而是追求"在正确的时间做正确的事的 AI"。分层架构让不同团队（关卡设计、AI 工程、动画）各自使用适合自己需求的工具，同时保持系统整体的连贯。

---

### 案例 6: Alien: Isolation (Creative Assembly) — 导演 AI + 行为树

#### 背景

Alien: Isolation（2014）的核心挑战是：一款恐怖游戏只有一个主要敌人（异形），这个敌人需要持续 15-20 小时制造恐怖感，不能重复，不能"被看穿"。如果玩家学会了异形的行为模式，恐怖感就消失了。

Creative Assembly 的解决方案是一个两层 AI 系统，它被公认为游戏 AI 设计的杰作。

#### 双层架构

```
┌─────────────────────────────────────┐
│         Director AI（导演 AI）       │
│  - 追踪玩家位置（始终知道）           │
│  - 管理"紧张度"计                     │
│  - 决策：异形应该追击、搜索还是撤退？  │
│  - 向异形下达"宏观指令"               │
└──────────────┬──────────────────────┘
               │ 宏观指令（"去搜索区域 B"）
               ▼
┌─────────────────────────────────────┐
│      Alien Behavior Tree（异形 BT）  │
│  - 执行导演的宏观指令                 │
│  - 感知系统：视觉、听觉（有限）        │
│  - 搜索行为：检查柜子、通风管道        │
│  - 追击行为：追逐、攻击               │
│  - **不知道玩家确切位置**（除非看到）  │
└─────────────────────────────────────┘
```

#### 导演 AI 的核心：紧张度曲线

导演 AI 的核心是一个**紧张度（Tension Meter）**变量，它根据以下输入动态变化：

| 输入 | 效果 |
|------|------|
| 玩家静止不动 | 紧张度缓慢下降 |
| 玩家移动/跑动 | 紧张度上升 |
| 玩家直视异形 | 紧张度大幅上升 |
| 异形距离玩家 | 距离越近，紧张度贡献越大 |
| 玩家使用了火焰喷射器 | 紧张度暂时下降（玩家有主动权） |
| 时间流逝 | 紧张度自然衰减 |

导演根据紧张度和一个内部状态机决定异形的行为模式：

```
Director 状态机:
  │
  ├── Stalk（潜行）: 紧张度低-中
  │     └── 指令：在玩家附近区域巡逻搜索，但不直接靠近
  │
  ├── Hunt（狩猎）: 紧张度中-高
  │     └── 指令：主动搜索玩家最后已知位置，检查藏身处
  │
  ├── Attack（攻击）: 紧张度高 + 异形发现玩家
  │     └── 指令：追击并攻击
  │
  └── Retreat（撤退）: 攻击后或剧情需要
        └── 指令：爬回通风管道，暂时消失
```

#### 为什么两层分离？

关键的架构决策是**导演始终知道玩家位置，但异形不知道**：

- **导演**有"上帝视角"——它知道玩家在哪里。这确保了恐怖节奏的精确控制。导演不会让异形长时间找不到玩家（→无聊），也不会让异形一直在玩家身边（→持续高压导致麻木）。
- **异形 BT** 只有有限感知——视觉锥体、听觉范围。它必须"真的"找到玩家才能攻击。这确保了玩家的隐身和躲藏游戏有意义——如果异形也一直知道玩家位置，那躲柜子就是自欺欺人。

这种"不公平但感觉公平"的设计是 Alien: Isolation 恐怖感的核心。

#### 实际效果

一个典型的恐怖循环（约 2-5 分钟）：

1. **平静期**：异形在通风管中，导演让它去别的区域。玩家探索、推进目标。
2. **建立期**：紧张度上升。导演让异形从附近通风口出现，进入 Stalk 模式。玩家听到异形的脚步声和通风管声音。
3. **高潮期**：异形进入 Hunt 模式，在玩家所在区域搜索。玩家躲进柜子。异形靠近柜子，闻了闻，然后走开（导演知道玩家在柜子里，但异形不知道——它只是在执行"彻底搜索"指令）。
4. **释放期**：导演判断紧张度已足够高且持续了一段时间，指令异形 Retreat。异形回到通风管。玩家长出一口气。

整个过程中，导演在精确控制节奏，而异形在诚实地执行"搜索但不知道你在哪"的行为。

#### 启示

Alien: Isolation 的导演 AI 是**"公平 vs 有趣"权衡的教科书案例**。导演"作弊"了——它知道玩家在哪——但这种作弊是为了创造更好的体验。关键设计原则：**分开"知道真相的系统"和"执行行为的系统"**，让作弊只发生在导演层，而执行层保持诚实。

---

### 案例 7: DOOM (2016) / DOOM Eternal (id Software) — 战斗 AI 的设计哲学

#### 背景

DOOM（2016）的 AI 设计与前面所有案例都不同。id Software 的目标不是"让 AI 看起来聪明"，而是**"让 AI 成为战斗系统的乐趣引擎"**。

id Software 称之为 **"Push-Forward Combat"（推进式战斗）**——AI 被设计成**主动向玩家推进**，逼迫玩家移动、切换武器、在战斗中流动，而不是鼓励玩家躲掩体对射。

#### 核心设计原则

DOOM 的战斗 AI 遵循三个原则，它们与传统"聪明 AI"的设计目标截然相反：

**原则 1：AI 不是"智能对手"，而是"战斗资源"**。

每个恶魔是一个"移动的战斗谜题"：
- Imps（小鬼）：低血量远程单位，逼迫玩家移动。爬墙能力意味着没有安全的角落。
- Hell Knights（地狱骑士）：大型近战单位，逼迫玩家后退和跳跃。它们的冲刺攻击有一个可预测的前摇。
- Mancubi（肥球）：大型远程单位，区域压制火力。玩家需要优先击杀或绕后。
- Cacodemons（大嘴怪）：飞行单位，战斗手雷吞入后可处决。

每种恶魔考验玩家的不同技能——移动、瞄准、资源管理（弹药/护甲/生命）。AI 的"智能"不在于策略，而在于**在正确的时间施加正确的压力**。

**原则 2：AI 行为必须可读**。

DOOM 中每个敌人的攻击都有清晰的前摇动画——玩家可以学习、预测和反制。这不是 AI "蠢"，是故意设计的。id Software 的 Hugo Martin 说："如果玩家死了，他们应该说'我知道为什么我死了，我下次会做得更好'，而不是'这 AI 作弊了'。"

**原则 3：AI 推动玩家进入"战斗之舞"**。

DOOM 的核心循环——"Glory Kill 处决 → 获得生命 → 电锯 → 获得弹药 → 火焰喷射器 → 获得护甲"——是由 AI 的行为驱动的。AI 不断推进迫使玩家移动，玩家移动中不断击杀 → 处决 → 补充资源。AI 越有侵略性，玩家移动越多，循环越流畅。

#### 实现：FSM + 优先级覆盖

与外界猜测的复杂 BT 系统不同，id Software 使用了相对简单的架构：

```
每个恶魔:
  └── 战斗角色 FSM (Combat Role FSM)
        ├── Idle / Spawn
        ├── Engage（与玩家交战）
        │     ├── 攻击选择：基于距离、角度、场上情况
        │     ├── 移动选择：靠近玩家、保持距离、侧移
        │     └── 受击反应：硬直、击退
        │
        ├── Glory Kill Ready（可被处决）
        │     └── 闪烁高亮，等待玩家处决
        │
        └── Dead
```

"优先级覆盖"系统处理特殊情况：
- 如果玩家使用了 BFG，所有非 Boss 恶魔立刻切换到"躲避"行为。
- 如果多个同类恶魔同时在场，系统限制同时攻击的数量（通常 2-3 个），防止玩家被"子弹海绵"淹没。
- 如果玩家长时间不移动（可能卡住了或 AFK），AI 的攻击频率自动降低。

#### 性能 — 大量单位

DOOM 的一个技术挑战是同时管理 20-30 个活跃 AI。id Software 的方法：
- **"攻击队列"系统**。全局管理哪些 AI 可以在当前帧攻击，限制每帧的攻击者数量。
- **降频 LOD**。远的恶魔降低行为更新频率，只处理移动和基础动画。
- **单一动画更新**。恶魔的 AI Tick 频率与动画更新频率解耦——AI 决策可以 5fps，但动画渲染始终 60fps。

#### 启示

DOOM 的案例提醒我们一个最容易被忽视的问题：**AI 的目的是让游戏更好玩，不是让 AI "更聪明"**。在你的面试中，如果你能说出"有时候我们应该刻意限制 AI 的能力来创造更好的玩家体验"，你会比只谈技术方案的候选人高出至少一个层级。

---

### 案例总结：模式与反模式

将这些案例放在一起，可以提炼出几个跨项目模式：

| 维度 | 共同模式 |
|------|---------|
| **分层** | 所有 7 个项目都使用多层 AI 架构。没有一个是单一范式解决所有问题的 |
| **分离关注点** | 决策 vs 执行、宏观 vs 微观、知道真相 vs 模拟感知——这些分离反复出现 |
| **调试优先** | 每个团队都在第一版 AI 框架中内置了可视化或日志，即使它"只是一个开发工具" |
| **约束意识** | 硬件约束（PS3 SPU、Xbox 360 核心数）、设计约束（"不能比玩家聪明"）、组织约束（设计师独立工作）都深刻地塑造了架构 |
| **迭代路径** | 从简单开始（FSM/脚本），在验证需求后升级到更复杂的系统。没有团队从第一天就"选对"了架构 |

---

## 2. 代码示例

### 示例 A: Halo 风格的小队协调系统

以下实现展示了一个简化版的 Halo 风格小队 AI——通过 Behavior Tree 进行角色分配和协调。代码使用伪代码（C++ 风格），聚焦结构而非具体平台细节。

```cpp
// ============================================================
// 示例 A: Halo 风格的小队协调系统
// 演示: Squad Leader BT 分配 Roles + 每个 Role 的独立 BT
// ============================================================

#include <vector>
#include <string>
#include <functional>
#include <unordered_map>

// ---- 基础 BT 节点类型（简化版） ----
enum class BTStatus { Success, Failure, Running };

struct BTNode {
    virtual ~BTNode() = default;
    virtual BTStatus Tick(float dt) = 0;
};

// ---- Blackboard（小队共享数据） ----
struct SquadBlackboard {
    // 小队共享感知
    Vector3 playerLastKnownPos;
    float   playerThreatLevel = 0.0f;   // 0-1, 基于玩家火力输出
    int     squadAliveCount    = 0;
    int     squadTotalCount    = 0;

    // 角色分配追踪
    std::string suppressorID  = "";  // 谁在压制？
    std::string flankerID     = "";  // 谁在侧翼？
    std::string grenadierID   = "";  // 谁在投雷？

    // 协调信号
    bool flankerInPosition    = false;
    bool grenadeThrown        = false;
    float timeSinceLastGrenade = 999.0f;
};

// ---- 角色枚举 ----
enum class SquadRole {
    Unassigned,
    Suppressor,   // 持续火力压制，吸引玩家注意
    Flanker,      // 绕路包抄
    Grenadier     // 投掷手雷逼迫玩家换位
};

// ---- 个体 AI 组件 ----
struct AIAgent {
    std::string id;
    Vector3     position;
    float       health;
    float       ammo;
    SquadRole   assignedRole = SquadRole::Unassigned;

    // 能力标签（不同兵种有不同能力）
    bool canSuppress  = false;
    bool canFlank     = false;
    bool canThrowGrenade = false;

    BTNode* behaviorTree = nullptr;  // 指向角色对应的 BT
};

// ============================================================
// Squad Leader 的 BT（角色分配）
// ============================================================

class SquadLeaderBT : public BTNode {
    SquadBlackboard* bb;
    std::vector<AIAgent*>* squad;
    float roleReassignTimer = 0.0f;

public:
    SquadLeaderBT(SquadBlackboard* blackboard, std::vector<AIAgent*>* s)
        : bb(blackboard), squad(s) {}

    BTStatus Tick(float dt) override {
        // 更新共享感知
        UpdateBlackboard(dt);

        // 定期重新分配角色（每 3 秒或角色阵亡时）
        roleReassignTimer -= dt;
        if (roleReassignTimer <= 0.0f || IsRoleKilled()) {
            AssignRoles();
            roleReassignTimer = 3.0f;
        }

        // Squad Leader 始终 Running —— 它是持续服务，不会 "完成"
        return BTStatus::Running;
    }

private:
    void UpdateBlackboard(float dt) {
        bb->squadAliveCount = 0;
        for (auto* agent : *squad) {
            if (agent->health > 0) bb->squadAliveCount++;
        }
        bb->squadTotalCount = (int)squad->size();

        // 威胁评估（简化）：基于玩家造成的伤害速率
        // 实际项目中可能从战斗统计系统读取
        bb->playerThreatLevel = EstimatePlayerThreat();

        // 更新协调信号
        for (auto* agent : *squad) {
            if (agent->assignedRole == SquadRole::Flanker
                && IsNearFlankingPosition(agent)) {
                bb->flankerInPosition = true;
            }
        }
    }

    // 核心：角色分配算法
    void AssignRoles() {
        // 重置所有角色
        for (auto* agent : *squad) {
            if (agent->health > 0) {
                agent->assignedRole = SquadRole::Unassigned;
            }
        }
        bb->suppressorID = "";
        bb->flankerID    = "";
        bb->grenadierID  = "";

        // 优先级分配: Suppressor > Flanker > Grenadier
        // "最擅长"的分配策略 —— 能力匹配优先

        // Step 1: 找最适合压制的（高血量、有压制能力）
        AIAgent* bestSuppressor = FindBestForRole(SquadRole::Suppressor);
        if (bestSuppressor) {
            bestSuppressor->assignedRole = SquadRole::Suppressor;
            bb->suppressorID = bestSuppressor->id;
        }

        // Step 2: 找最适合侧翼的（速度快、有侧翼能力、不是压制者）
        AIAgent* bestFlanker = FindBestForRole(SquadRole::Flanker);
        if (bestFlanker) {
            bestFlanker->assignedRole = SquadRole::Flanker;
            bb->flankerID = bestFlanker->id;
        }

        // Step 3: 找最适合投雷的（有手雷、不是前两个角色）
        AIAgent* bestGrenadier = FindBestForRole(SquadRole::Grenadier);
        if (bestGrenadier) {
            bestGrenadier->assignedRole = SquadRole::Grenadier;
            bb->grenadierID = bestGrenadier->id;
        }

        // Step 4: 未分配的成员默认跟随 Suppressor 的行为
        for (auto* agent : *squad) {
            if (agent->health > 0
                && agent->assignedRole == SquadRole::Unassigned) {
                // 分配一个"辅助压制"角色 —— 本质上复制 Suppressor BT
                agent->assignedRole = SquadRole::Suppressor;
            }
        }
    }

    AIAgent* FindBestForRole(SquadRole role) {
        AIAgent* best = nullptr;
        float bestScore = -1.0f;

        for (auto* agent : *squad) {
            if (agent->health <= 0) continue;
            if (agent->assignedRole != SquadRole::Unassigned) continue;

            float score = ScoreAgentForRole(agent, role);
            if (score > bestScore) {
                bestScore = score;
                best = agent;
            }
        }
        return best;
    }

    float ScoreAgentForRole(AIAgent* agent, SquadRole role) {
        // 评分函数：综合考虑能力匹配 + 当前状态
        float score = 0.0f;

        switch (role) {
        case SquadRole::Suppressor:
            // 压制者需要：高血量（能承受反击）、充足弹药
            score += agent->canSuppress ? 100.0f : 0.0f;
            score += agent->health * 0.5f;
            score += agent->ammo * 0.3f;
            break;

        case SquadRole::Flanker:
            // 侧翼者需要：速度快、血量尚可、有侧翼能力
            score += agent->canFlank ? 100.0f : 0.0f;
            score += (agent->health > 50.0f) ? 50.0f : 0.0f;
            // 距离玩家不要太近（否则会被发现）也不要太远（否则要跑太久）
            float distToPlayer = Distance(agent->position,
                                          bb->playerLastKnownPos);
            score += (distToPlayer > 15.0f && distToPlayer < 50.0f) ? 30.0f : 0.0f;
            break;

        case SquadRole::Grenadier:
            // 掷弹兵需要：有手雷、在投掷范围内、不是压制者
            score += agent->canThrowGrenade ? 100.0f : 0.0f;
            float dist = Distance(agent->position, bb->playerLastKnownPos);
            score += (dist > 10.0f && dist < 30.0f) ? 40.0f : 0.0f;
            break;

        default: break;
        }
        return score;
    }

    bool IsRoleKilled() {
        // 检查已分配角色的 agent 是否阵亡
        for (auto* agent : *squad) {
            if (agent->health <= 0
                && agent->assignedRole != SquadRole::Unassigned) {
                return true;
            }
        }
        return false;
    }

    float EstimatePlayerThreat() { /* 省略实现 */ return 0.5f; }
    bool IsNearFlankingPosition(AIAgent* a) { /* 省略实现 */ return false; }
    float Distance(Vector3 a, Vector3 b) { return (a - b).Length(); }
};

// ============================================================
// 个体角色 BT: Suppressor（压制者）
// ============================================================

class SuppressorBT : public BTNode {
    AIAgent* owner;
    SquadBlackboard* bb;
    float burstTimer = 0.0f;
    int   burstCount = 0;

public:
    SuppressorBT(AIAgent* agent, SquadBlackboard* blackboard)
        : owner(agent), bb(blackboard) {}

    BTStatus Tick(float dt) override {
        // 死亡检查
        if (owner->health <= 0) return BTStatus::Failure;

        // 行为逻辑（Selector 风格，但这里简化为顺序检查）:

        // 1. 如果不在掩体中 → 先找掩体
        if (!IsInCover()) {
            MoveToNearestCover(dt);
            return BTStatus::Running;
        }

        // 2. 如果侧翼者还没就位 → 持续开火吸引注意力
        if (!bb->flankerInPosition) {
            SuppressingFire(dt);
            return BTStatus::Running;
        }

        // 3. 侧翼者就位 + 手雷爆炸后 → 推进
        if (bb->flankerInPosition && bb->grenadeThrown) {
            AdvanceToNextCover(dt);
            bb->grenadeThrown = false;
            return BTStatus::Running;
        }

        // 4. 默认：保持压制
        SuppressingFire(dt);
        return BTStatus::Running;
    }

private:
    void SuppressingFire(float dt) {
        burstTimer -= dt;
        if (burstTimer <= 0.0f) {
            // 短点射而非连射 —— 节省弹药，持续施压
            FireBurst(3);  // 3 发点射
            burstTimer = 0.5f;  // 每 0.5 秒一个点射
            burstCount++;
        }

        // 偶尔小幅度移动（左右摇头），避免被玩家狙击
        if (burstCount % 4 == 0) {
            StrafeRandom(dt);
        }
    }

    void MoveToNearestCover(float dt)    { /* 省略寻路逻辑 */ }
    void AdvanceToNextCover(float dt)    { /* 省略推进逻辑 */ }
    void FireBurst(int rounds)           { /* 省略射击逻辑 */ }
    void StrafeRandom(float dt)          { /* 省略移动逻辑 */ }
    bool IsInCover()                     { return false; }
};

// ============================================================
// 个体角色 BT: Flanker（侧翼者）
// ============================================================

class FlankerBT : public BTNode {
    AIAgent* owner;
    SquadBlackboard* bb;
    std::vector<Vector3> flankPath;
    int currentWaypoint = 0;

public:
    FlankerBT(AIAgent* agent, SquadBlackboard* blackboard)
        : owner(agent), bb(blackboard) {}

    BTStatus Tick(float dt) override {
        if (owner->health <= 0) return BTStatus::Failure;

        // 1. 计算侧翼路径（只计算一次）
        if (flankPath.empty()) {
            flankPath = ComputeFlankRoute(
                owner->position,
                bb->playerLastKnownPos,
                30.0f  // 侧翼偏移距离
            );
        }

        // 2. 沿路径移动
        if (currentWaypoint < (int)flankPath.size()) {
            Vector3 target = flankPath[currentWaypoint];
            MoveToward(target, dt);

            if (Distance(owner->position, target) < 1.0f) {
                currentWaypoint++;
            }
            return BTStatus::Running;
        }

        // 3. 到达侧翼位置 → 通知 Squad Leader
        bb->flankerInPosition = true;

        // 4. 从侧翼攻击
        AttackFromFlank(dt);
        return BTStatus::Running;
    }

private:
    // A* 寻路 + 侧向偏移 —— 绕开主战场
    std::vector<Vector3> ComputeFlankRoute(
        Vector3 from, Vector3 target, float flankOffset
    ) {
        // 实际实现：使用导航网格，计算避开玩家视线的路径
        // 这里返回简化的直线路径
        std::vector<Vector3> path;
        Vector3 flankTarget = target + Vector3::Right * flankOffset;
        path.push_back(from);
        path.push_back(flankTarget);
        return path;
    }

    void MoveToward(Vector3 target, float dt)   { /* 省略 */ }
    void AttackFromFlank(float dt)              { /* 省略 */ }
    float Distance(Vector3 a, Vector3 b)        { return 0.0f; }
};

// ============================================================
// 个体角色 BT: Grenadier（掷弹兵）
// ============================================================

class GrenadierBT : public BTNode {
    AIAgent* owner;
    SquadBlackboard* bb;
    float grenadeCooldown = 0.0f;

public:
    GrenadierBT(AIAgent* agent, SquadBlackboard* blackboard)
        : owner(agent), bb(blackboard) {}

    BTStatus Tick(float dt) override {
        if (owner->health <= 0) return BTStatus::Failure;
        if (!owner->canThrowGrenade) return BTStatus::Failure;

        grenadeCooldown -= dt;

        // 1. 如果在掩体中且冷却完毕 → 投掷手雷
        if (IsInCover() && grenadeCooldown <= 0.0f) {
            // 瞄准玩家当前位置或掩体后方
            Vector3 aimTarget = PredictPlayerPosition();

            if (Distance(owner->position, aimTarget) < 25.0f) {
                ThrowGrenade(aimTarget);
                bb->grenadeThrown = true;
                bb->timeSinceLastGrenade = 0.0f;
                grenadeCooldown = 8.0f;  // 8 秒冷却
            }
        }

        // 2. 冷却中 → 用枪械参与战斗
        if (grenadeCooldown > 0.0f) {
            FireAtPlayer(dt);
        }

        return BTStatus::Running;
    }

private:
    bool IsInCover() { return false; }
    Vector3 PredictPlayerPosition() { return {}; }
    void ThrowGrenade(Vector3 target) { /* 省略 */ }
    void FireAtPlayer(float dt) { /* 省略 */ }
    float Distance(Vector3 a, Vector3 b) { return 0.0f; }
};
```

**关键设计点解读**：

1. **Squad Leader 是持续服务**（始终返回 Running）——它不是一次性决策，而是持续监控和调整角色分配。
2. **角色分配与角色执行完全分离**。Squad Leader 只负责"谁是 Flanker"，FlankerBT 负责"怎么 Flank"。新增角色不需要修改 Squad Leader 的 BT 结构。
3. **通过 Blackboard 共享协调信号**（`flankerInPosition`、`grenadeThrown`）而非直接在 Agent 之间发送消息——降低耦合。
4. **评分制角色分配**而非硬编码规则——你可以轻松添加新的评分因子（如"距离玩家最近者优先成为压制者"）而不破坏已有逻辑。

---

### 示例 B: 简化的导演 AI 系统（Alien: Isolation 风格）

```cpp
// ============================================================
// 示例 B: 简化导演 AI 系统（Alien: Isolation 风格）
// 演示: 紧张度系统 + 宏观状态机 + 指令下发到 BT
// ============================================================

#include <cmath>
#include <algorithm>

// ---- 导演的宏观指令 ----
enum class DirectorCommand {
    PatrolArea,     // 在指定区域闲逛
    SearchArea,     // 彻底搜索指定区域
    HuntPlayer,     // 主动寻找并攻击玩家
    RetreatToVents, // 撤退回通风管道
    Idle            // 什么都不做
};

// ---- 导演内部状态机 ----
enum class DirectorState {
    Building,     // 建立紧张感：异形在附近但保持距离
    Sustaining,   // 维持紧张：异形在搜索，玩家躲藏
    Climax,       // 高潮：异形在追击
    Releasing     // 释放：异形撤退，玩家喘息
};

// ---- 导演 AI ----
class DirectorAI {
private:
    // ---- 输入 ----
    Vector3 playerPosition;
    Vector3 alienPosition;
    float   playerSpeed        = 0.0f;   // 平均移动速度
    float   playerLookAngle    = 0.0f;   // 玩家视线方向（用来检测"直视异形"）
    float   timeSinceLastSighting = 999.0f;  // 玩家上次看到异形的时间
    float   timeSinceLastAttack   = 999.0f;  // 异形上次攻击的时间
    bool    playerInHidingSpot  = false;     // 玩家是否在柜子/床底
    bool    playerHasFlamethrower = false;   // 玩家是否有火焰喷射器

    // ---- 状态 ----
    float tension          = 0.0f;   // 0.0 - 1.0 紧张度
    float desiredTension   = 0.7f;   // 目标紧张度范围: [0.5, 0.85]
    DirectorState state    = DirectorState::Building;
    DirectorCommand currentCommand = DirectorCommand::PatrolArea;

    // ---- 计时器 ----
    float stateTimer       = 0.0f;   // 当前状态已持续时间
    float phaseTimer       = 0.0f;   // 当前阶段计时

    // ---- 调优参数 ----
    static constexpr float TENSION_DECAY_RATE   = 0.02f;  // 每秒衰减
    static constexpr float MIN_STATE_DURATION    = 15.0f;  // 每个状态最少持续时间
    static constexpr float MAX_CLIMAX_DURATION   = 30.0f;  // 高潮最多持续 30 秒
    static constexpr float MIN_RELEASE_DURATION  = 20.0f;  // 释放至少 20 秒

public:
    // ---- 每帧由游戏循环调用 ----
    DirectorCommand Update(float dt,
                           Vector3 playerPos, Vector3 alienPos,
                           float playerVel, float lookAngle,
                           bool inHiding, bool hasFlame) {
        // 更新输入
        playerPosition      = playerPos;
        alienPosition       = alienPos;
        playerSpeed         = playerVel;
        playerLookAngle     = lookAngle;
        playerInHidingSpot  = inHiding;
        playerHasFlamethrower = hasFlame;

        // 更新计时器
        stateTimer      += dt;
        phaseTimer      += dt;
        timeSinceLastSighting += dt;
        timeSinceLastAttack   += dt;

        // Step 1: 更新紧张度
        UpdateTension(dt);

        // Step 2: 更新导演状态机
        UpdateState(dt);

        // Step 3: 根据状态发出指令
        currentCommand = DecideCommand();

        return currentCommand;
    }

    // ---- 外部回调：异形通知导演 ----
    void OnAlienSpottedPlayer()  { timeSinceLastSighting = 0.0f; }
    void OnAlienAttackedPlayer() { timeSinceLastAttack   = 0.0f; }
    void OnPlayerUsedFlamethrower() { tension *= 0.4f; }  // 玩家获得主动权

    // ---- 查询接口（供调试/可视化） ----
    float  GetTension()     const { return tension; }
    DirectorState GetState() const { return state; }

private:
    // ==========================================
    // 紧张度更新
    // ==========================================
    void UpdateTension(float dt) {
        float tensionDelta = 0.0f;

        // 因素 1: 玩家移动速度
        //   - 静止/慢走: 紧张度下降
        //   - 跑动: 紧张度上升（异形会听到脚步声）
        if (playerSpeed > 5.0f) {
            tensionDelta += 0.15f * dt;  // 跑动
        } else if (playerSpeed < 1.0f) {
            tensionDelta -= 0.05f * dt;  // 静止
        }

        // 因素 2: 距离衰减
        //   - 异形越近，紧张度越高
        float dist = Distance(playerPosition, alienPosition);
        if (dist < 10.0f) {
            tensionDelta += 0.2f * dt;   // 异形非常近
        } else if (dist < 30.0f) {
            tensionDelta += 0.08f * dt;  // 异形在附近
        } else {
            tensionDelta -= 0.03f * dt;  // 异形很远
        }

        // 因素 3: 玩家直视异形
        //   - 恐怖作品的核心：看到怪物 = 恐惧峰值
        Vector3 directionToAlien = (alienPosition - playerPosition).Normalized();
        Vector3 playerLookDir    = AngleToDirection(playerLookAngle);
        float dot = DotProduct(playerLookDir, directionToAlien);

        if (dot > 0.85f && dist < 15.0f) {
            // 玩家正在直视近处的异形——恐惧峰值
            tensionDelta += 0.3f * dt;
        }

        // 因素 4: 上次"接触"的时间衰减
        if (timeSinceLastSighting > 30.0f) {
            tensionDelta -= 0.04f * dt;  // 太久没看到异形，紧张感消退
        }

        // 因素 5: 玩家在藏身处
        if (playerInHidingSpot) {
            // 在藏身处时，如果异形在附近 → 紧张（屏住呼吸的恐惧）
            // 如果异形很远 → 放松
            if (dist < 5.0f) {
                tensionDelta += 0.25f * dt;
            } else {
                tensionDelta -= 0.06f * dt;
            }
        }

        // 因素 6: 自然衰减
        tensionDelta -= TENSION_DECAY_RATE * dt;

        // 因素 7: 玩家有火焰喷射器时，紧张度上升更慢
        if (playerHasFlamethrower) {
            tensionDelta *= 0.6f;
        }

        // 应用变化并钳制
        tension = std::clamp(tension + tensionDelta, 0.0f, 1.0f);
    }

    // ==========================================
    // 导演状态机
    // ==========================================
    void UpdateState(float dt) {
        switch (state) {

        case DirectorState::Building:
            // 状态目标：让紧张度逐步上升到 0.5-0.7 之间
            // 转移条件：紧张度到达目标区间后进入 Sustaining
            if (tension >= 0.5f && stateTimer > MIN_STATE_DURATION) {
                TransitionTo(DirectorState::Sustaining);
            }
            break;

        case DirectorState::Sustaining:
            // 状态目标：维持紧张度在 0.5-0.85 之间
            // 转移条件 1: 紧张度过高且持续了一段时间 → Climax
            if (tension >= 0.85f && stateTimer > 20.0f) {
                TransitionTo(DirectorState::Climax);
            }
            // 转移条件 2: 紧张度太低且无法回升 → 退回 Building
            else if (tension < 0.3f && stateTimer > 30.0f) {
                TransitionTo(DirectorState::Building);
            }
            break;

        case DirectorState::Climax:
            // 状态目标：保持高压，但不超过持续时间上限
            if (stateTimer > MAX_CLIMAX_DURATION
                || timeSinceLastAttack > 15.0f) {
                // 要么持续时间太长了，要么异形一直没找到玩家
                TransitionTo(DirectorState::Releasing);
            }
            break;

        case DirectorState::Releasing:
            // 状态目标：让玩家喘息，紧张度降到 0.3 以下
            if (tension < 0.3f && stateTimer > MIN_RELEASE_DURATION) {
                TransitionTo(DirectorState::Building);
            }
            break;
        }
    }

    void TransitionTo(DirectorState newState) {
        state = newState;
        stateTimer = 0.0f;
    }

    // ==========================================
    // 指令决策
    // ==========================================
    DirectorCommand DecideCommand() {
        switch (state) {

        case DirectorState::Building:
            // 建立期：异形在玩家附近区域闲逛但不要太近
            // 偶尔搜索一下（制造紧张），但大部分时间在巡逻
            if (tension < 0.35f) {
                // 紧张度不够 → 让异形搜索玩家附近的区域
                return DirectorCommand::SearchArea;
            } else {
                // 紧张度适中 → 巡逻保持存在感
                return DirectorCommand::PatrolArea;
            }

        case DirectorState::Sustaining:
            // 维持期：让异形在"搜索玩家所在区域"和"短暂撤退"之间切换
            // 这个 ping-pong 创造"我以为它走了但其实没有"的恐怖感
            if (phaseTimer > 45.0f) {
                phaseTimer = 0.0f;
            }

            if (phaseTimer < 30.0f) {
                return DirectorCommand::SearchArea;
            } else {
                // 短暂撤退（15 秒），然后再次出现——制造"假安全"时刻
                return DirectorCommand::RetreatToVents;
            }

        case DirectorState::Climax:
            // 高潮期：异形全力搜索和追击
            if (timeSinceLastSighting < 5.0f) {
                // 最近看到过玩家 → 追击
                return DirectorCommand::HuntPlayer;
            } else {
                // 丢失目标 → 但还是搜索（不放松）
                return DirectorCommand::SearchArea;
            }

        case DirectorState::Releasing:
            // 释放期：异形撤退，给玩家探索空间
            return DirectorCommand::RetreatToVents;

        default:
            return DirectorCommand::PatrolArea;
        }
    }

    // ---- 工具函数（省略实现） ----
    float  Distance(Vector3 a, Vector3 b)       { return 0.0f; }
    float  DotProduct(Vector3 a, Vector3 b)     { return 0.0f; }
    Vector3 AngleToDirection(float angle)       { return {}; }
};
```

**关键设计点解读**：

1. **紧张度是一个连续值**，使行为过渡平滑而非跳跃。玩家不会感觉到"现在进入紧张阶段"——他只会发现异形越来越近。
2. **状态机控制节奏**，但每个状态内的具体指令仍有变体（通过 `phaseTimer` 做 ping-pong）。纯粹的循环会让玩家识破模式。
3. **导演"作弊"但不被察觉**。导演知道玩家位置用于计算紧张度和选择指令区域，但异形 BT 仍然需要通过自己的感知系统找到玩家。作弊发生在玩家看不到的层面。
4. **外部回调**（`OnAlienSpottedPlayer` 等）让异形 BT 可以向导演报告事件，形成反馈循环。这不是单向控制——导演和异形双向对话。

---

## 3. 练习

### 练习 1: 案例架构总结（面试准备用）

**目标**：选择一个案例（建议选择与你目标岗位最相关的），撰写一份 1 页的架构总结，适合在系统设计面试中使用。

**格式要求**：
- 游戏名称、AI 架构类型、核心挑战（3 行内）
- 架构图（用 ASCII art 或简洁的文字描述层次关系）
- 为什么选择这个架构？（2-3 个具体原因，引用硬件/设计/组织约束）
- 1 个关键权衡（他们牺牲了什么来获得什么？）
- 如果今天重做，你会建议什么改变？（基于当前技术环境）

**提示**：
- 如果你目标是 FPS 游戏岗位 → Halo 2 或 DOOM
- 如果你目标是开放世界/RPG → The Sims 或 The Last of Us
- 如果你目标是 AI 系统工程岗位 → F.E.A.R. 或 Killzone

---

### 练习 2: 设计你自己的导演 AI

**目标**：为一个恐怖游戏设计导演 AI 系统。不要写代码——先设计架构。

**要求**：

1. **定义输入**。导演 AI 需要接收什么信息？（至少 6 种输入）为每个输入说明"为什么这个信息对恐怖节奏至关重要"。

2. **定义输出**。导演 AI 控制什么？（至少 3 种可以控制的游戏元素）不是所有输出都是"控制敌人"——考虑环境（灯光、音效、门）、资源投放（弹药、药品）、和叙事触发器。

3. **定义紧张度曲线**。一张简单的手绘描述：X 轴是游戏时间，Y 轴是紧张度。标注出高点（Boss 战、追逐段落）和低点（安全室、剧情段落）。说明为什么这个节奏合理。

4. **防止"恐怖免疫"**。玩家在玩了 10 小时后会对恐怖脱敏。你的导演系统如何应对这一点？（至少提出两种策略）

---

### 练习 3（可选）: 实现简单小队协调

**目标**：基于示例 A 的设计，用你选择的语言实现一个简化的小队协调系统。

**要求**：
1. 实现至少 3 种角色（Suppressor、Flanker、Grenadier）。
2. 包含一个基本的角色分配算法——即使只是随机分配或基于距离分配。
3. 用 Unity/Unreal/纯代码控制 3 个 AI 在地图上对玩家执行协同攻击。
4. 如果可能，添加可视化——用颜色或标记显示每个 AI 的当前角色。

**评估标准**（自评）：
- 角色分配是否合理？（不会三个 AI 全选同一个角色）
- 角色切换是否平滑？（角色阵亡或战场变化后能否重新分配？）
- 玩家的感受如何？（觉得 AI 在配合还是各自为战？）

---

## 4. 扩展阅读

### GDC 演讲（核心 — 必看）

这些是本文案例的直接来源，大部分可在 GDC Vault（https://www.gdcvault.com/）找到：

| 演讲 | 讲者 | 年份 | 关联案例 |
|------|------|------|---------|
| *Managing Complexity in the Halo 2 AI* | Damian Isla (Bungie) | GDC 2005 | Halo 2 BT 起源 |
| *Building a Better Battle: AI in Halo 3* | Damian Isla | GDC 2008 | Halo 3 行为标签系统 |
| *Three States and a Plan: The AI of F.E.A.R.* | Jeff Orkin (Monolith) | GDC 2006 | F.E.A.R. GOAP |
| *Goal-Oriented Action Planning: Ten Years of AI Programming* | Jeff Orkin | GDC 2015 | GOAP 十年回顾 |
| *The AI of Killzone 2 & 3* | Guerrilla Games | GDC 2011 | Killzone HTN |
| *Creating the Alien AI in Alien: Isolation* | Creative Assembly | GDC 2015 | 导演 AI + BT |
| *Embracing Push Forward Combat in DOOM* | id Software | GDC 2017 | DOOM 战斗 AI |
| *AI for 'Middle-earth: Shadow of Mordor' — The Nemesis System* | Monolith | GDC 2015 | Utility AI 应用 |
| *Modeling Player Knowledge for AI* | David "Rez" Graham | GDC 2012 | AI 感知系统设计 |

### Game AI Pro 系列

Game AI Pro（1/2/3/360）是游戏 AI 领域的工业论文集，每篇文章由 AAA 开发者撰写。以下是与案例研究最相关的文章：

| 文章 | 作者 | 位置 | 内容 |
|------|------|------|------|
| *Behavior Selection Algorithms: An Overview* | Michael Dawe | GAP3, Ch 4 | FSM/BT/Utility/GOAP 全景对比 |
| *The Simplest AI Trick in the Book* | Various | GAP1, Ch 11 | FSM 量产模式 |
| *Modular AI* | Kevin Dill | GAP2, Ch 13 | 模块化 AI 架构 |
| *Architecture Tricks: Managing Behaviors in Time, Space, and Depth* | Steve Rabin | GAP1, Ch 3 | 多层 AI 架构设计 |
| *An Introduction to Utility Theory* | David "Rez" Graham | GAP1, Ch 17 | 效用理论入门 |
| *GOAP: Ten Years Later* | Jeff Orkin | GAP3, Ch 7 | GOAP 十年实践总结 |
| *Building an AI Director* | Brian Schwab | GAP3, Ch 25 | 导演 AI 设计方法 |

### 书籍

| 书名 | 作者 | 相关章节 | 说明 |
|------|------|---------|------|
| *Programming Game AI by Example* | Mat Buckland (2005) | Ch 2 (FSM), Ch 9 (Goal-Driven Agent) | 游戏 AI 经典教材。Ch 9 的 Goal-Driven Agent 是 GOAP 的前身概念 |
| *Artificial Intelligence for Games* (2nd ed.) | Ian Millington (2009) | Ch 5 (Decision Making), Ch 9 (Action Execution) | 偏理论，但对 HTN 和 GOAP 有严格的算法描述 |
| *Behavioral Mathematics for Game AI* | Dave Mark (2012) | 全书 | 效用 AI 的数学基础。Dave Mark 是 IAUS 的创造者 |
| *Game Engine Architecture* (3rd ed.) | Jason Gregory (2019) | Section 15 (AI) | Naughty Dog 引擎架构师的视角，讨论商业引擎中的 AI 系统设计 |

### 在线资源

- **AI and Games (YouTube)**：[youtube.com/@AIandGames](https://www.youtube.com/@AIandGames) — Tommy Thompson 的频道，深度分析商业游戏的 AI 设计。推荐视频：*"The AI of Alien: Isolation"*、*"The AI of DOOM (2016)"*、*"How F.E.A.R.'s AI Works"*。
- **Game AI Pro 官网**：[gameaipro.com](https://www.gameaipro.com/) — Game AI Pro 1 免费在线阅读；第 2/3 卷部分免费。
- **GDC Vault**：[gdcvault.com](https://www.gdcvault.com/) — 大部分 GDC AI 演讲的录像（部分需要会员）。

---

## 常见陷阱

### 1. 过度研究而不实现

**症状**：你阅读了所有 7 个案例，看了所有 GDC 演讲，但一行代码都没写。你可以在面试中引用 Isla 和 Orkin 的观点，但如果面试官让你在白板上设计一个 AI 系统，你发现你只知道"他们做了什么"而不知道"怎么做的"。

**解法**：每读完一个案例，挑一个核心概念实现一个最小原型。读完 Halo 案例 → 实现一个 3 角色的 Squad Leader + 2 个体 BT。读完 Alien: Isolation 案例 → 实现一个带紧张度变量的导演状态机（50 行 Python 就够了）。读完 F.E.A.R. 案例 → 实现一个带有 5 个动作和 3 个目标的微型 GOAP 规划器。

### 2. 盲目套用 AAA 模式到独立游戏

**症状**：你在做一个 3 人团队的 2D 独立游戏，但你设计了 Halo 级别的多层 AI 架构——Squad Leader、BT、Blackboard、行为标签、LOD 系统——然后发现游戏还有 3 个月要发售而你还在写 AI 框架。

**根因**：AAA 方案的复杂性是为 AAA 的约束准备的——20-40 人的团队、非程序员设计师需要独立迭代、硬件性能严格受限、行为数量 50+。独立游戏的约束完全不同——人员少、迭代快、行为数少、性能瓶颈在渲染而非 AI。

**解法**：读案例时，区分"这个决策是因为什么约束？"如果约束不匹配你的项目，决策就不适用于你。Halo 2 转向 BT 是因为行为数超过 FSM 拐点——你的独立游戏有超过 15 种行为吗？如果没有，FSM 可能更适合你。

### 3. 混淆"为什么"——误读决策驱动因素

**症状**：你告诉别人"Guerrilla 用 HTN 是因为它比 BT 好"，或者"id Software 用 FSM 而不是 BT 说明 BT 过时了"。

**根因**：每个架构选择是多个约束的产物——硬件、团队结构、设计目标、已有技术债务、时间线。没有一个"正确"的架构。

**正确理解**：
- Killzone 用 HTN 是因为**阵地战需要"计划感"** + PS3 硬件限制不能跑每帧重规划 → 预定义计划库更合适。
- DOOM 用 FSM 是因为**AI 不需要"聪明"**——它需要可预测、可读、服务于战斗循环。BT 的复杂度是不必要的。
- F.E.A.R. 用 GOAP 是因为**Monolith 愿意投入 R&D 成本**来换取 emergent 行为——这个选择在大多数项目的时间线约束下是不可行的。

在你的面试中，展示这种理解——"我知道为什么他们做了那个选择，以及如果约束不同我会做什么不同的选择"——比背诵案例事实有价值得多。

### 4. 忽视设计师的工作流

**症状**：你设计了一个技术上优雅的 AI 系统，但设计师无法独立使用它。每一个行为调整都需要你来改代码。项目进度被你的带宽瓶颈拖住。

**根因**：几乎所有 AAA 案例中，架构选择的一个关键驱动因素是"设计师能不能独立工作"。Halo 2 的 BT 成功很大程度上因为设计师可以在可视化编辑器中调整行为优先级。如果你在构建自己的 AI 系统时没有考虑设计师的工作流——即使是"未来可能有的设计师"——你的系统在团队扩展到 5 人以上时就会开始产生摩擦。

**解法**：至少提供一种数据驱动的方式来配置 AI 行为——JSON/YAML 文件定义行为参数、优先级、条件阈值。不需要可视化编辑器，但不要让每次调参都变成一次编译。

### 5. 用案例为自己的偏见辩护

**症状**：你偏好 BT，所以你在每个案例中寻找"证明 BT 更好"的证据。你忽略了 Killzone 用 HTN 成功了 3 代游戏，你也忽略了 DOOM 刻意不使用 BT 但仍然是 AI 设计的典范。

**根因**：确认偏误。案例研究的目的是拓展你的工具箱和判断力，不是为你已有的观点寻找弹药。

**自检**：尝试为**你不喜欢的**架构辩护。如果你认为 GOAP 太复杂不实用，尝试写下 F.E.A.R. 用 GOAP 成功的三个具体原因。如果你认为 FSM 已经过时，尝试写下 DOOM 团队为什么选择 FSM 而且这个选择是对的。如果你做不到这一点，你就还没有真正理解这些案例。

---

> **下一篇：** [19-interview-prep.md](19-interview-prep.md) — 面试准备与系统设计（综合所有本计划知识点，模拟真实面试场景）
