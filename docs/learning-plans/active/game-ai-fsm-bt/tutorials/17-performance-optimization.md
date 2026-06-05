---
title: "游戏 AI 性能优化实战"
updated: 2026-06-05
---

# 游戏 AI 性能优化实战

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 01-15（所有已完成的 FSM + BT + GOAP 教程）

---

## 1. 概念讲解

### 为什么性能优化是系统设计问题而非编码问题？

大多数程序员对"性能优化"的直觉是：找到最慢的函数，用更高效的算法重写。这在 AI 系统中是**不充分的**——实际上可能是**错误的起点**。

游戏 AI 的性能约束来自帧预算的铁律。60fps 意味着每一帧只有 16.67ms。这 16.67ms 必须在渲染（GPU 命令提交 + 等待）、物理、动画、脚本逻辑和 AI 之间分配。AI 系统通常被分配 **2-5ms**——这不是 "AI 团队和渲染团队商量后决定" 的数字，而是 **"如果 AI 超过这个时间，帧率就会下降，玩家会投诉"** 的物理约束。

理解这一点后，"性能优化"的含义从"让代码跑得更快"变为 **"在固定的 CPU 预算内，为尽可能多的 agent 提供尽可能高质量的决策"**。这是一个多维度的权衡工程，而不仅仅是算法竞赛。

**关键公式**：

```
AI 帧预算 (ms)  = 16.67 × (1 - GPU_bound_ratio) × AI_share
总 agent 数      = AI 帧预算 / per_agent_cost
```

如果一个 per-agent BT 评估花费 0.05ms，在 3ms 预算内最多支持 60 个 agent。如果需要支持 500 个 agent，要么将 per-agent cost 降到 0.006ms（12 倍），要么通过降低 tick 频率等手段让平均 per-agent cost 缩减到等效的 0.006ms。

**性能分析的第一步永远是测量**。Unity 中使用 `Profiler.BeginSample("AI_Total")` / `Profiler.EndSample()` 包裹整个 AI 更新循环；UE 中使用 `TRACE_CPUPROFILER_EVENT_SCOPE` 或 UE Insights。没有 measurement baseline 的 "优化" 只是猜测——你必须知道当前各子系统的精确耗时分布：

| 子系统 | 典型占比 | 优化重点 |
|:-------|:---------|:---------|
| 行为树/FSM Tick | 30-50% | 降低 tick 频率、子树缓存、条件预检 |
| 感知系统 (Perception) | 20-40% | 空间哈希、距离平方比较、视锥预剔除 |
| 寻路 (Pathfinding) | 10-25% | 路径复用、异步寻路、简化导航网格 |
| Blackboard 读写 | 5-10% | 整数 Key 索引、struct 替代 class |
| 其他（动画查询、物理查询） | 5-15% | 降低查询频率、缓存结果 |

### Tick 管理：不是所有 AI 都需要每帧思考

这是 AI 性能优化的**最大杠杆**——它不改变 per-agent 的评估成本，而是减少需要评估的 agent-帧数。

#### 可变 Tick 频率（Variable Tick Rate）

核心思路：根据 AI 与玩家的距离或重要性，分配不同的 tick 频率。

| 距离层级 | Tick 频率 | 帧间隔 | 等效 per-agent cost (假设全频 0.05ms) |
|:---------|:----------|:-------|:--------------------------------------|
| 近距离 (< 20m) | 每帧 | 1 | 0.05ms |
| 中距离 (20-60m) | 每 3 帧 | 3 | 0.017ms |
| 远距离 (60-150m) | 每 10 帧 | 10 | 0.005ms |
| 极远 (> 150m) | 每 30 帧 | 30 | 0.0017ms |

**注意**：频率降低引入响应延迟。30 帧的 tick 间隔在 60fps 下意味着 0.5 秒的决策延迟——敌方 NPC 在被玩家发现后可能需要 0.5 秒才"反应"过来。补偿策略：**事件唤醒**。当关键事件（受到伤害、感知到玩家）发生时，立即将该 agent 提升为最高 tick 频率并重置计数器。

#### Time-Slicing（时间分片）

可变 tick 频率的进阶：将 AI 更新任务均匀散布到多个帧上，确保每一帧的 AI 负载稳定。

```
帧 0: agent[0..99]   tick
帧 1: agent[100..199] tick
帧 2: agent[200..299] tick
...
帧 9: agent[900..999] tick
帧10: agent[0..99]   tick  ← 每个 agent 每 10 帧更新一次
```

实现要点：维护一个全局的 `_nextAgentIndex` 游标，每帧更新 `batchSize` 个 agent 后推进游标。这保证每帧的 AI 负载是常数，而非周期性尖峰。

**Time-slicing 与可变 tick 频率的区别**：time-slicing 解决的是"同一帧内 agent 数量过多"的问题——所有 agent 使用相同 tick 频率，但分批执行。可变 tick 频率解决的是"远距离 agent 不需要高频更新"的问题。两者可以组合：按距离对 agent 分组，每组内部使用 time-slicing。

#### 优先级调度（Priority-Based Scheduling）

不是所有 AI 同等重要。Boss 的决策质量远比背景中巡逻的守卫重要。优先级调度将 CPU 预算向高优先级 agent 倾斜：

1. **关键路径 agent**（Boss、精英怪、玩家附近 10m 内）：每帧 tick，使用完整 AI 系统
2. **战术 agent**（玩家 10-40m）：每 2-5 帧 tick，使用完整 AI 但降低感知更新频率
3. **背景 agent**（40m 以外）：每 10-30 帧 tick，使用简化 AI
4. **休眠 agent**（不可见且远离玩家）：仅在事件唤醒时恢复

### 数据结构：内存访问模式决定性能

CPU 性能的天花板早已不是主频，而是**缓存未命中（cache miss）** 的代价。一次 L3 cache miss 约 40-100 个时钟周期，一次主内存访问约 200+ 个时钟周期。在 4GHz CPU 上，这意味着一次内存访问可能耗费 50ns——足以执行 50-100 条简单指令。

#### GC 压力管理（C#/Unity 特定）

在 C# 中，GC 是 AI 系统最大的隐蔽性能杀手。行为树每帧 tick 可能产生大量的临时对象——每次 `Dictionary` 的枚举器装箱、每次字符串拼接、每次 lambda 捕获都可能导致 heap 分配。GC 触发时的 **stop-the-world** 暂停可达 1-5ms，对于 60fps 游戏来说意味着 6-30 帧的卡顿。

**零分配策略**：
- Tick 热路径中 **禁止** `new`、`string.Format`、`$` 字符串插值、装箱
- 预分配所有可变容器（`List<T>`、`Stack<T>`），通过 `.Clear()` 重用
- 使用 `struct` 替代 `class` 用于高频创建的小对象（Blackboard 条目、节点状态）
- 对象池化：所有可复用的节点实例、命令对象、查询结果

#### AoS vs SoA（Array of Structures vs Structure of Arrays）

考虑 1000 个 AI agent 的 `Health` 数据：

**AoS（传统面向对象方式）**：
```csharp
class AIAgent {
    public float Health;      // offset 0
    public Vector3 Position;  // offset 4
    public float Speed;       // offset 20
    public int State;         // offset 24
    // ... 更多字段
}
AIAgent[] agents = new AIAgent[1000];
```

遍历所有 agent 的 Health 时，CPU 加载整个 64-byte cache line，却只用了 4 bytes（Health）。其余 60 bytes 被浪费——这就是 cache 污染。

**SoA（数据导向方式）**：
```csharp
struct AIAgentData {
    public NativeArray<float> Health;     // contiguous block
    public NativeArray<Vector3> Positions;
    public NativeArray<float> Speeds;
    public NativeArray<int> States;
}
```

遍历 Health 时，每个 cache line（64 bytes）包含 16 个连续的 `float` 值。缓存利用率从 AoS 的 ~6% 提升到 SoA 的 ~100%。在 1000+ agent 的循环中，这可以带来 3-10x 的性能差异。

**规则**：需要全量遍历的属性用 SoA；需要按 agent 随机访问的属性用 AoS（单个 agent 的多个属性在同一个 cache line 中）。

#### 空间哈希（Spatial Hashing）

AI 最常见的操作之一是"找到附近的所有其他 AI / 玩家 / 物体"。每帧 O(N²) 的距离比较是不可接受的。空间哈希将世界划分为统一大小的网格单元，agent 根据位置注册到网格中：

```
网格大小 = max(感知范围, 交互范围)  // 保证任何查询只需检查相邻的 3×3 个格子
```

查询"我周围 20m 内的所有敌人"从 O(N²) 降为 O(K)，其中 K 是 9 个相邻格子中的 agent 数。对于均匀分布的场景，K ≈ 9 × 平均密度 × 格子面积。

实现要点：
- 使用 `NativeParallelMultiHashMap<int, int>`（Unity Collections）或 `TMultiMap`（UE5）——键是格子坐标的哈希值，值是 agent 索引
- 每帧在 AI tick 之前重建哈希表（或增量更新）
- 网格坐标计算：`cellX = floor(position.x / cellSize)`, `cellY = floor(position.y / cellSize)`，哈希：`cellX * large_prime + cellY`

### 行为树特定优化

行为树的性能模型是：**每帧成本 = 树遍历深度 × 每节点评估成本 × 条件重评估次数**。优化瞄准这三个乘数。

#### 子树缓存（Sub-Tree Caching）

行为树每帧从根重新评估。如果某个子树在上次评估中返回了特定结果，且影响它决策的外部条件没有改变，则可以跳过该子树的重新评估。

```
[Selector]
  ├─ [Cooldown: 2s] HasEnemy → Combat Subtree   ← 2 秒内不需要重新评估 "HasEnemy"
  ├─ [Cooldown: 3s] HealthLow → Flee Subtree
  └─ Patrol Subtree
```

Cooldown Decorator 是最简单有效的子树缓存形式。进阶方案：在子树根节点处维护一个"脏标记"——当子树依赖的 Blackboard Key 发生变化时标记为脏，下一帧才重新评估。非脏的子树直接返回缓存的上次结果。

**关键约束**：缓存只对 **Selector 的已失败分支** 和 **Sequence 的已成功分支** 安全——这些分支的结果不会因为"不重新评估"而改变树的最终输出。对 Running 分支的缓存需要更谨慎的脏标记机制。

#### 条件预检（Conditional Pre-Check）

在完整评估一个子树之前，先快速检查该子树的最顶层条件：

```
[Selector]
  ├─ [PreCheck: Distance < 50m] → [Sequence]
  │    ├─ [Distance < 5m] → MeleeAttack
  │    └─ [Distance < 20m] → RangedAttack
  ├─ [PreCheck: HasSuspiciousSound] → Investigate
  └─ Patrol
```

`PreCheck` 是一个轻量级条件，在父 Selector 决定是否进入该分支之前执行。如果 PreCheck 失败，整个子树被跳过而无需评估内部节点。PreCheck 应使用**远小于完整条件成本**的运算——如距离平方与阈值的比较（避免 `sqrt`）、简单的布尔标志检查。

实现上，PreCheck 可以内嵌到 Selector 的 tick 逻辑中：在遍历每个子节点之前，先检查该子节点的 PreCheck。

#### 事件驱动评估（Event-Driven Evaluation）

标准行为树是 **pull-based**（每帧从根拉取状态）。事件驱动是 **push-based**（仅当外部事件改变时推送更新）：

1. AI 处于 Patrol 行为的 Running 状态时，不需要每帧重新检查"是否有敌人"——只有在 Perception 系统检测到新目标时才需要
2. 通过 Observer Abort 机制（UE Behavior Tree 原生支持）：BT 注册"观察"Blackboard 的特定 Key，当 Key 值变化时自动触发条件重评估

**UE Observer Aborts 实现**：
```cpp
// On a Decorator node in UE Behavior Tree:
// Notify Observer = On Value Change
// Observer Aborts = Lower Priority (or Self, or Both)
```

当被观察的 Blackboard Key 变化时，BT 自动中断当前执行的节点并重新评估。这意味着静默状态下（没有 Blackboard 变化），行为树完全不消耗 CPU——无需每帧遍历。

### FSM 特定优化

FSM 的 per-agent 成本远低于 BT（常数级 vs 遍历级），但在大规模场景下仍有关键优化点。

#### 转移表数组化

基于 `switch` 的转移评估每帧执行 O(S) 次条件检查（S = 状态数）。对于频繁切换的状态机（如动画状态机），将转移表表示为二维数组：

```cpp
// Transition table: [currentState][event] → nextState
using TransitionKey = std::pair<StateId, EventId>;
std::unordered_map<TransitionKey, StateId> _transitions; // 查找 O(1)

// Even faster: dense array when state/event counts are small
StateId _table[MAX_STATES][MAX_EVENTS]; // O(1) with zero hash overhead
```

#### 避免热路径上的虚函数

C++ 中，FSM 的 `IState::Update()` 如果声明为 `virtual`，每个 agent 每帧都需要经过 vtable 间接调用。对于 1000+ agent 的场景，仅 vtable lookup 就可能造成显著的指令缓存压力。

**替代方案**：
- 使用函数指针数组：`using UpdateFn = void(*)(Agent&, float dt); UpdateFn _updates[MAX_STATES];`
- 使用模板 + `std::variant`：`using State = std::variant<Patrol, Chase, Attack, Flee>; std::visit([](auto& s){ s.Update(dt); }, _state);`
- 在已知状态分布不均匀时，将最频繁的状态放在 `switch` 的第一个 `case` ——编译器通常将其优化为跳转表

### 多线程 AI

单线程 AI 模型在 agent 数量突破数百后遇到硬上限。多线程化是突破这个上限的路径——但引入的复杂度需要严格的设计约束。

#### 并行化模型

**Agent 级并行**（最安全、最常用）：
- 每个 agent 的 AI 是完全独立的——不同 agent 之间只通过 Blackboard 共享只读数据
- 将 N 个 agent 均匀分配到 M 个 worker thread
- Unity: `IJobParallelFor` + `NativeArray<AgentData>`
- UE: `ParallelFor` + `TArray<FAIUpdateTask>`

**行为树级并行**（进阶）：
- 同一棵 BT 的不同子树并行评估。仅对 Parallel 节点下的独立子树安全
- 需要原子操作保护共享 Blackboard 的写访问
- 实际收益有限——大多数 BT 的瓶颈在叶子节点（感知查询、路径计算），而非树本身的遍历

#### 锁无关 Blackboard（Lock-Free Blackboard）

多线程 AI 的最大挑战是 Blackboard 的读写冲突。agent A 读取 `TargetPosition` 的同时 agent B 在写入。锁会消除并行的收益，但完全不加锁会导致数据腐化。

**写时复制（Copy-on-Write）Blackboard**：
- 每个 agent 持有 Blackboard 的本地副本
- AI 系统在每帧开始时从全局 Blackboard 同步只读数据到各 agent 的本地副本
- Agent 写入自己的本地副本，帧末尾合并回全局 Blackboard（仅写入变化的值）
- 合并阶段使用原子 CAS 或细粒度锁

**双层 Blackboard 架构**：
```
全局层 (Read-heavy, 每帧更新)     → 感官输入、世界状态
本地层 (per-agent, 可自由读写)    → agent 内部状态、决策中间值
```

Agent 只能写本地层，只能读全局层（或本地层）。全局层的写入由 AI 系统在同步阶段执行。这从根本上消除了数据竞争。

#### Unity Jobs + Burst 编译

对于 500+ agent 的场景，将 AI 逻辑移入 Burst 编译的 Job 是突破单线程限制的最有效手段：

```csharp
[BurstCompile]
struct AIUpdateJob : IJobParallelFor
{
    [ReadOnly] public NativeArray<PerceptionData> Perceptions;
    public NativeArray<AgentState> States;
    public NativeArray<BlackboardEntry> Blackboard;

    public void Execute(int index)
    {
        // Burst-compiled AI logic — no managed allocations, no virtual calls
        ref var state = ref States.ElementAt(index);
        var perception = Perceptions[index];
        // ... FSM transition or BT node evaluation
    }
}
```

Burst 的限制：不能使用 class、虚函数、托管对象、`string`、异常。这意味着你的 AI 数据结构必须全部重新设计为 unmanaged struct + NativeContainer。这不是"加个 `[BurstCompile]` 就完事"——它要求整个 AI 数据流从 OOP 转为 DOD。

### 内存预算

每个 AI agent 的内存占用直接影响可支持的 agent 总数。在移动平台或低端硬件上，内存约束可能比 CPU 约束更早到达。

#### Per-Agent 内存预算

| 数据类型 | 典型大小 | 1000 agents |
|:---------|:---------|:------------|
| Agent 状态（位置、朝向、速度） | 64B | 64KB |
| Blackboard 数据（10 个 Key） | 160B | 160KB |
| BT 运行时状态（节点路径、计时器） | 128B | 128KB |
| 行为树节点实例（每 agent 克隆） | 1-4KB | 1-4MB |
| 动画/物理状态 | 256B | 256KB |
| **总计** | **~2-5KB/agent** | **~2-5MB** |

**压缩策略**：
1. **Blackboard 值压缩**：使用 `FixedString64Bytes`（Unity）或 `FName`（UE）存储 Key；布尔值打包为位字段；使用 `half` 精度浮点存储不需要高精度的值（情绪值、计时器比例）
2. **共享不可变数据**：行为树结构、曲线数据、配置参数在所有 agent 之间共享单例实例——只有 per-agent 运行时状态需要独立副本
3. **节点实例的懒分配**：不为 agent 预分配整棵树的所有节点实例，而是只在节点首次被 tick（进入 Running 状态）时才分配——大多数 agent 在任何给定帧只接触树中的少数节点

---

## 2. 代码示例

### 示例 A：Unity AI LOD 管理器 + Burst 距离排序

完整的三级 LOD 系统：Full（完整 BT）、Simplified（简化 FSM）、Disabled（休眠）。使用 Burst 编译的 Job 计算所有 agent 到玩家的距离并排序，避免在主线程上做 O(N) 的 `Vector3.Distance`。

```csharp
using Unity.Burst;
using Unity.Collections;
using Unity.Jobs;
using UnityEngine;
using UnityEngine.Profiling;

// ── LOD Level Definition ──
public enum AILODLevel : byte
{
    Full = 0,       // Complete BT, every frame tick
    Simplified = 1, // Lightweight FSM, every 10 frames
    Disabled = 2    // No AI update, event-wake only
}

// ── Per-agent data stored SoA for Burst compatibility ──
public struct AgentLODData
{
    public Vector3 Position;
    public float SqrDistanceToPlayer;
    public AILODLevel CurrentLOD;
    public AILODLevel TargetLOD;
    public int TickCounter;
    public byte LODTransitionCooldown; // frames before another LOD change allowed
}

// ── LOD Configuration ──
[System.Serializable]
public struct LODConfig
{
    public float FullRadius;       // < this → Full
    public float SimplifiedRadius; // < this → Simplified, else Disabled
    public int SimplifiedTickInterval;  // tick every N frames for Simplified
    public int LODHysteresis;      // extra margin to prevent oscillation (meters)
    public int TransitionCooldownFrames; // min frames between LOD changes
}

// ── Burst-compiled Job: compute distances + assign LOD levels ──
[BurstCompile]
public struct AILODUpdateJob : IJobParallelFor
{
    [ReadOnly] public Vector3 PlayerPosition;
    [ReadOnly] public LODConfig Config;
    public NativeArray<AgentLODData> Agents;

    public void Execute(int index)
    {
        var agent = Agents[index];
        Vector3 delta = agent.Position - PlayerPosition;
        float sqrDist = delta.x * delta.x + delta.y * delta.y + delta.z * delta.z;
        agent.SqrDistanceToPlayer = sqrDist;

        float hysteresisSqr = Config.LODHysteresis * Config.LODHysteresis;

        // LOD assignment with hysteresis to prevent oscillation
        AILODLevel newLOD;
        float fullSqr = Config.FullRadius * Config.FullRadius;
        float simpleSqr = Config.SimplifiedRadius * Config.SimplifiedRadius;

        if (sqrDist < fullSqr - hysteresisSqr)
            newLOD = AILODLevel.Full;
        else if (sqrDist < simpleSqr - hysteresisSqr)
            newLOD = AILODLevel.Simplified;
        else if (sqrDist < simpleSqr + hysteresisSqr
                 && agent.CurrentLOD == AILODLevel.Simplified)
            newLOD = AILODLevel.Simplified; // hysteresis: don't demote yet
        else
            newLOD = AILODLevel.Disabled;

        // Apply transition cooldown
        if (newLOD != agent.CurrentLOD)
        {
            if (agent.LODTransitionCooldown == 0)
            {
                agent.TargetLOD = newLOD;
                agent.LODTransitionCooldown = (byte)Config.TransitionCooldownFrames;
            }
        }
        else if (agent.LODTransitionCooldown > 0)
        {
            agent.LODTransitionCooldown--;
        }

        Agents[index] = agent;
    }
}

// ── Main LOD Manager (MonoBehaviour) ──
public class AILODManager : MonoBehaviour
{
    [Header("LOD Config")]
    [SerializeField] private LODConfig _config = new LODConfig
    {
        FullRadius = 30f,
        SimplifiedRadius = 80f,
        SimplifiedTickInterval = 10,
        LODHysteresis = 5f,
        TransitionCooldownFrames = 30
    };

    [Header("References")]
    [SerializeField] private Transform _player;

    private NativeArray<AgentLODData> _agents;
    private IAIController[] _controllers; // Full = BT, Simplified = FSM
    private int _agentCount;
    private int _currentBatchStart; // for time-slicing LOD updates

    public void Initialize(IAIController[] controllers)
    {
        _controllers = controllers;
        _agentCount = controllers.Length;
        _agents = new NativeArray<AgentLODData>(
            _agentCount, Allocator.Persistent);

        for (int i = 0; i < _agentCount; i++)
        {
            _agents[i] = new AgentLODData
            {
                Position = controllers[i].GetPosition(),
                CurrentLOD = AILODLevel.Full,
                TargetLOD = AILODLevel.Full
            };
        }
    }

    void Update()
    {
        Profiler.BeginSample("AI_LOD_Update");

        // Update agent positions from controllers
        for (int i = 0; i < _agentCount; i++)
        {
            var agent = _agents[i];
            agent.Position = _controllers[i].GetPosition();
            _agents[i] = agent;
        }

        // Schedule Burst job
        var job = new AILODUpdateJob
        {
            PlayerPosition = _player.position,
            Config = _config,
            Agents = _agents
        };
        JobHandle handle = job.Schedule(_agentCount, 64);
        handle.Complete();

        // Apply LOD transitions and tick AI
        int fullCount = 0, simplifiedCount = 0, disabledCount = 0;
        for (int i = 0; i < _agentCount; i++)
        {
            var agent = _agents[i];
            if (agent.TargetLOD != agent.CurrentLOD)
            {
                OnLODChanged(i, agent.CurrentLOD, agent.TargetLOD);
                agent.CurrentLOD = agent.TargetLOD;
                _agents[i] = agent;
            }

            switch (agent.CurrentLOD)
            {
                case AILODLevel.Full:
                    _controllers[i].TickAI(); // BT, every frame
                    fullCount++;
                    break;
                case AILODLevel.Simplified:
                    agent.TickCounter++;
                    if (agent.TickCounter >= _config.SimplifiedTickInterval)
                    {
                        _controllers[i].TickAISimplified(); // FSM
                        agent.TickCounter = 0;
                    }
                    _agents[i] = agent;
                    simplifiedCount++;
                    break;
                case AILODLevel.Disabled:
                    disabledCount++;
                    break;
            }
        }

        Profiler.EndSample();

        // Debug visualization
        if (Time.frameCount % 60 == 0)
            Debug.Log($"AI LOD: Full={fullCount} Simplified={simplifiedCount} Disabled={disabledCount}");
    }

    private void OnLODChanged(int agentIndex, AILODLevel from, AILODLevel to)
    {
        if (to == AILODLevel.Full)
            _controllers[agentIndex].OnLODActivate();  // restore BT state
        else if (from == AILODLevel.Full)
            _controllers[agentIndex].OnLODDeactivate(); // snapshot BT state to BB
    }

    void OnDestroy()
    {
        if (_agents.IsCreated) _agents.Dispose();
    }
}
```

**关键设计决策**：
1. `NativeArray<AgentLODData>` 使用 SoA 布局——所有 agent 的 LOD 数据在连续内存中，Burst Job 的缓存利用率最大化
2. **Hysteresis**（迟滞）：LOD 切换边界增加 5m 的缓冲区，防止 agent 在边界上来回振荡导致 "LOD 抖动"
3. **Transition Cooldown**：两次 LOD 切换之间至少间隔 30 帧，进一步抑制抖动
4. 距离计算使用 `sqrDist`（无 `sqrt`）——性能敏感场景中，平方距离与阈值的平方比较等价且快 3-5x

### 示例 B：Unity 对象池 + struct Blackboard（零 GC）

这是为大规模 AI 场景设计的完整 BT 节点池化系统，配合基于 `struct` 的 Blackboard，确保 Tick 热路径零堆分配。

```csharp
using System;
using System.Collections.Generic;
using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;

// ── Compact Blackboard Key: integer index instead of string ──
public struct BBKey : IEquatable<BBKey>
{
    public readonly int Index;
    public BBKey(int index) => Index = index;

    public bool Equals(BBKey other) => Index == other.Index;
    public override int GetHashCode() => Index;
    public override bool Equals(object obj) => obj is BBKey k && Equals(k);
}

// ── Struct-based Blackboard value entry ──
public enum BBValueType : byte
{
    None, Float, Int, Bool, Vector3, EntityRef
}

public struct BBValue
{
    public BBValueType Type;
    // Union-style storage — only one field is valid based on Type
    public float FloatVal;
    public int IntVal;
    public bool BoolVal;
    public float V3X, V3Y, V3Z;
}

// ── GC-free Blackboard using NativeList ──
public struct BlackboardData : IDisposable
{
    private NativeList<BBValue> _values;
    private NativeList<FixedString32Bytes> _keyNames; // debug only, stripped in ship

    public void Initialize(int capacity)
    {
        _values = new NativeList<BBValue>(capacity, Allocator.Persistent);
        _keyNames = new NativeList<FixedString32Bytes>(capacity, Allocator.Persistent);
    }

    public BBKey RegisterKey(FixedString32Bytes name)
    {
        int index = _values.Length;
        _values.Add(new BBValue { Type = BBValueType.None });
        _keyNames.Add(name);
        return new BBKey(index);
    }

    public float GetFloat(BBKey key)
    {
        var v = _values[key.Index];
        return v.Type == BBValueType.Float ? v.FloatVal : 0f;
    }

    public void SetFloat(BBKey key, float value)
    {
        var v = _values[key.Index];
        v.Type = BBValueType.Float;
        v.FloatVal = value;
        _values[key.Index] = v;
    }

    public int GetInt(BBKey key)
    {
        var v = _values[key.Index];
        return v.Type == BBValueType.Int ? v.IntVal : 0;
    }

    public void SetInt(BBKey key, int value)
    {
        var v = _values[key.Index];
        v.Type = BBValueType.Int;
        v.IntVal = value;
        _values[key.Index] = v;
    }

    public Vector3 GetVector3(BBKey key)
    {
        var v = _values[key.Index];
        return v.Type == BBValueType.Vector3
            ? new Vector3(v.V3X, v.V3Y, v.V3Z)
            : Vector3.zero;
    }

    public void SetVector3(BBKey key, Vector3 value)
    {
        var v = _values[key.Index];
        v.Type = BBValueType.Vector3;
        v.V3X = value.x; v.V3Y = value.y; v.V3Z = value.z;
        _values[key.Index] = v;
    }

    public void Clear()
    {
        for (int i = 0; i < _values.Length; i++)
        {
            var v = _values[i];
            v.Type = BBValueType.None;
            _values[i] = v;
        }
    }

    public void Dispose()
    {
        if (_values.IsCreated) _values.Dispose();
        if (_keyNames.IsCreated) _keyNames.Dispose();
    }
}

// ── BT Node pooling system ──
public enum BTResult : byte { Success, Failure, Running }

public abstract class PooledBTNode
{
    // Per-instance runtime state — must be Reset() before pool reuse
    internal int _currentChildIndex;
    internal bool _isActive;

    public abstract BTResult Tick(BlackboardData bb);
    public virtual void Reset() { _currentChildIndex = 0; _isActive = false; }
}

public sealed class PooledSelector : PooledBTNode
{
    public PooledBTNode[] Children; // set once at construction, not per-agent

    public override BTResult Tick(BlackboardData bb)
    {
        while (_currentChildIndex < Children.Length)
        {
            var result = Children[_currentChildIndex].Tick(bb);
            if (result != BTResult.Failure) return result;
            _currentChildIndex++;
        }
        return BTResult.Failure;
    }

    public override void Reset()
    {
        base.Reset();
        for (int i = 0; i < Children.Length; i++)
            Children[i].Reset();
    }
}

public sealed class PooledSequence : PooledBTNode
{
    public PooledBTNode[] Children;

    public override BTResult Tick(BlackboardData bb)
    {
        while (_currentChildIndex < Children.Length)
        {
            var result = Children[_currentChildIndex].Tick(bb);
            if (result != BTResult.Success) return result;
            _currentChildIndex++;
        }
        return BTResult.Success;
    }

    public override void Reset()
    {
        base.Reset();
        for (int i = 0; i < Children.Length; i++)
            Children[i].Reset();
    }
}

// ── Per-type object pool ──
public class BTNodePool<T> where T : PooledBTNode, new()
{
    private readonly Stack<T> _free = new Stack<T>(64);

    public T Rent()
    {
        return _free.Count > 0 ? _free.Pop() : new T();
    }

    public void Return(T node)
    {
        node.Reset();
        _free.Push(node);
    }
}

// ── Central pool manager ──
public class BTPoolManager
{
    private readonly Dictionary<Type, object> _pools = new Dictionary<Type, object>();

    public BTNodePool<T> GetPool<T>() where T : PooledBTNode, new()
    {
        var type = typeof(T);
        if (!_pools.TryGetValue(type, out var pool))
        {
            pool = new BTNodePool<T>();
            _pools[type] = pool;
        }
        return (BTNodePool<T>)pool;
    }

    public T Rent<T>() where T : PooledBTNode, new()
        => GetPool<T>().Rent();

    public void Return<T>(T node) where T : PooledBTNode, new()
        => GetPool<T>().Return(node);
}

// ── Usage: per-agent BT runner with pooled nodes ──
public class PooledBTRunner
{
    private PooledBTNode _root;
    private BlackboardData _bb;
    private BTPoolManager _poolManager;
    private List<PooledBTNode> _allocatedNodes; // track for return on deactivate

    // Pre-defined keys (registered once at startup, cached here)
    public BBKey KeyTargetPos;
    public BBKey KeyHealth;
    public BBKey KeyHasEnemy;

    public void Initialize(BTPoolManager poolManager)
    {
        _poolManager = poolManager;
        _allocatedNodes = new List<PooledBTNode>(32);
        _bb.Initialize(32);
        KeyTargetPos = _bb.RegisterKey("TargetPos");
        KeyHealth = _bb.RegisterKey("Health");
        KeyHasEnemy = _bb.RegisterKey("HasEnemy");

        // Build tree from pool
        BuildTree();
    }

    private void BuildTree()
    {
        var root = _poolManager.Rent<PooledSelector>();
        _allocatedNodes.Add(root);

        var combatSeq = _poolManager.Rent<PooledSequence>();
        _allocatedNodes.Add(combatSeq);
        // ... add condition and action nodes as leaves

        root.Children = new PooledBTNode[] { combatSeq /* , patrol, etc. */ };
        _root = root;
    }

    public void Tick()
    {
        _root.Tick(_bb);
    }

    public void Deactivate()
    {
        // Return all allocated nodes to pools
        foreach (var node in _allocatedNodes)
        {
            node.Reset();
            // Return to correct typed pool based on runtime type
            var poolProp = typeof(BTPoolManager)
                .GetMethod("Return")
                ?.MakeGenericMethod(node.GetType());
            poolProp?.Invoke(_poolManager, new object[] { node });
        }
        _allocatedNodes.Clear();
    }

    public void Dispose()
    {
        Deactivate();
        _bb.Dispose();
    }
}
```

**零 GC 保证**：
1. Blackboard 使用 `NativeList<BBValue>`（unmanaged struct），无堆分配
2. Key 是 `BBKey`（int 包装），无字符串哈希
3. 节点池使用预分配的 `Stack<T>`，`Rent()` 和 `Return()` 均无分配
4. Tick 路径中没有 `new`、字符串操作或装箱
5. `BBValue` 使用 union-style 存储——`Type` 字段 + 内联值，无 `object` 装箱

### 示例 C：UE5 — MassEntity + TaskGraph 并行 AI 评估

UE5 的 MassEntity 框架专为大规模实体设计。以下展示如何将 AI 决策集成到 MassEntity 处理器中，利用 TaskGraph 并行评估数百个 agent。

```cpp
// ── Mass AI Fragment: per-agent AI state ──
USTRUCT()
struct FMassAIFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    EMassAIState CurrentState = EMassAIState::Idle;

    UPROPERTY()
    float StateTimer = 0.0f;

    UPROPERTY()
    float Health = 100.0f;

    UPROPERTY()
    FVector LastKnownEnemyLocation = FVector::ZeroVector;

    UPROPERTY()
    int32 TickCounter = 0;

    UPROPERTY()
    uint8 LODLevel = 0; // 0=Full, 1=Simplified, 2=Disabled

    // Cached event state — set by perception processor
    UPROPERTY()
    bool bHasEnemyInSight = false;

    UPROPERTY()
    bool bReceivedDamage = false;
};

// ── Perception Fragment ──
USTRUCT()
struct FMassPerceptionFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    FVector ClosestEnemyPosition = FVector::ZeroVector;

    UPROPERTY()
    float ClosestEnemyDistanceSq = FLT_MAX;

    UPROPERTY()
    bool bHasEnemyInSight = false;
};

// ── Shared immutable AI config (one instance for all agents) ──
USTRUCT()
struct FMassAIConfigShared : public FMassSharedFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float AttackRange = 200.0f;

    UPROPERTY()
    float ChaseRange = 1500.0f;

    UPROPERTY()
    float FleeHealthThreshold = 30.0f;

    UPROPERTY()
    int32 FullLODTickInterval = 1;        // every frame

    UPROPERTY()
    int32 SimplifiedLODTickInterval = 10; // every 10 frames

    UPROPERTY()
    int32 FullLODRadius = 3000;           // cm

    UPROPERTY()
    int32 SimplifiedLODRadius = 8000;     // cm
};

// ── Event-Driven Behavior Tree with Observer Aborts ──
// This processor only ticks AI when relevant perception events occur,
// using MassEntity's Tag-based event signaling.

USTRUCT()
struct FMassAIEventTag : public FMassTag {};      // signals "needs AI tick"

USTRUCT()
struct FMassAIDamageEventTag : public FMassTag {}; // signals "took damage"

// ── Perception Processor (runs every frame, writes events) ──
UCLASS()
class UMassAIPerceptionProcessor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UMassAIPerceptionProcessor()
    {
        ExecutionOrder.ExecuteAfter.Add(UMassLODProcessorBase::StaticClass()->GetFName());
        ExecutionFlags = (int32)EProcessorExecutionFlags::All;
    }

protected:
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override
    {
        // Query all AI entities with perception + transform
        EntityManager.ForEachEntity<FMassPerceptionFragment,
                                     FTransformFragment,
                                     FMassAIFragment>(
            Context,
            [](FMassPerceptionFragment& Perception,
               FTransformFragment& Transform,
               FMassAIFragment& AI)
            {
                // Run perception: check for enemies in sight
                // (Simplified — real implementation queries spatial hash)
                Perception.bHasEnemyInSight = false;

                // When perception state changes, signal the AI event tag
                if (Perception.bHasEnemyInSight != AI.bHasEnemyInSight)
                {
                    AI.bHasEnemyInSight = Perception.bHasEnemyInSight;
                    // Signal that this entity needs an AI evaluation
                    // MassEntity: add lightweight tag to trigger event-driven tick
                }
            });
    }
};

// ── AI Decision Processor: runs in parallel via TaskGraph ──
UCLASS()
class UMassAIDecisionProcessor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UMassAIDecisionProcessor()
    {
        // Only process entities tagged for AI update (event-driven)
        // + periodic tick for LOD-based scheduling
        ExecutionOrder.ExecuteAfter.Add(UMassAIPerceptionProcessor::StaticClass()->GetFName());
        ExecutionFlags = (int32)EProcessorExecutionFlags::All;
    }

protected:
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override
    {
        TRACE_CPUPROFILER_EVENT_SCOPE(UMassAIDecisionProcessor::Execute);

        // MassEntity automatically parallelizes ForEachEntity across
        // TaskGraph workers when chunk count exceeds threshold
        EntityManager.ForEachEntity<FMassAIFragment,
                                     FMassPerceptionFragment,
                                     FTransformFragment>(
            Context,
            [this](FMassAIFragment& AI,
                   FMassPerceptionFragment& Perception,
                   FTransformFragment& Transform)
            {
                // LOD-gated tick
                int32 tickInterval = (AI.LODLevel == 0)
                    ? 1 : Config->SimplifiedLODTickInterval;

                AI.TickCounter++;
                if (AI.TickCounter < tickInterval) return;
                AI.TickCounter = 0;

                // Event-driven logic: only re-evaluate on state change
                // (In a full BT, this is the Observer Abort trigger)
                if (AI.bReceivedDamage)
                {
                    AI.CurrentState = EMassAIState::Fleeing;
                    AI.bReceivedDamage = false;
                    return;
                }

                // ── Decision logic (simplified BT-equivalent) ──
                switch (AI.CurrentState)
                {
                case EMassAIState::Idle:
                case EMassAIState::Patrolling:
                    if (Perception.bHasEnemyInSight)
                    {
                        float distSq = Perception.ClosestEnemyDistanceSq;
                        float attackSq = Config->AttackRange * Config->AttackRange;
                        float chaseSq = Config->ChaseRange * Config->ChaseRange;

                        if (distSq <= attackSq)
                            AI.CurrentState = EMassAIState::Attacking;
                        else if (distSq <= chaseSq)
                            AI.CurrentState = EMassAIState::Chasing;
                    }
                    break;

                case EMassAIState::Chasing:
                    if (!Perception.bHasEnemyInSight)
                    {
                        AI.StateTimer += tickInterval * 0.016f; // approx dt
                        if (AI.StateTimer > 3.0f) // lost sight for 3s
                        {
                            AI.CurrentState = EMassAIState::Investigating;
                            AI.LastKnownEnemyLocation =
                                Perception.ClosestEnemyPosition;
                            AI.StateTimer = 0.0f;
                        }
                    }
                    else
                    {
                        AI.StateTimer = 0.0f;
                    }
                    break;

                case EMassAIState::Attacking:
                    if (AI.Health < Config->FleeHealthThreshold)
                    {
                        AI.CurrentState = EMassAIState::Fleeing;
                        break;
                    }
                    if (!Perception.bHasEnemyInSight)
                    {
                        AI.CurrentState = EMassAIState::Chasing;
                    }
                    break;

                case EMassAIState::Fleeing:
                    AI.StateTimer += tickInterval * 0.016f;
                    if (AI.StateTimer > 5.0f) // flee for 5s then return
                    {
                        AI.CurrentState = EMassAIState::Patrolling;
                        AI.StateTimer = 0.0f;
                    }
                    break;

                default:
                    break;
                }
            });
    }

private:
    // Shared config — read-only, no lock needed
    TSharedPtr<FMassAIConfigShared> Config;
};

// ── Damage Signal Processor: injects event tags ──
UCLASS()
class UMassAIDamageSignalProcessor : public UMassObserverProcessor
{
    GENERATED_BODY()

public:
    UMassAIDamageSignalProcessor()
    {
        // Observe entities when FMassAIFragment is added/changed
        ObservedType = FMassAIFragment::StaticStruct();
        Operation = EMassObservedOperation::Add;
    }

protected:
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override
    {
        // Mark entities that need immediate AI re-evaluation
        EntityManager.ForEachEntity<FMassAIFragment>(
            Context,
            [](FMassAIFragment& AI)
            {
                // Force immediate re-evaluation
                AI.TickCounter = INT32_MAX;
            });
    }
};
```

**关键设计要点**：
1. **MassEntity 自动并行化**：`ForEachEntity` 在 entity chunk 数量超过阈值时自动分配到 TaskGraph 的多个 worker 上
2. **事件驱动 Tick**：`FMassAIEventTag` 标签用于标记需要 AI 重评估的实体，避免每帧扫描全部 agent
3. **Observer Aborts 的架构等价物**：`bReceivedDamage` 标志作为 Blackboard 观察的等效——外部系统（如伤害处理器）设置此标志，AI 决策处理器在下一次 tick 时立即响应
4. **LOD gating 内嵌在 processor 中**：`TickCounter` + `tickInterval` 实现可变频率，不依赖外部调度
5. **Shared Fragment**：`FMassAIConfigShared` 在所有 agent 之间共享，零冗余内存

---

## 3. 练习

### 练习 1：Profile 500 AI 场景 + 瓶颈分析

**目标**：在场景中放置 500 个运行你自研 BT 框架的 AI agent，使用 Profiler 定位 Top 3 性能瓶颈并提出优化方案。

**步骤**：
1. 创建一个测试场景，生成 500 个 AI agent，均匀分布在 200m×200m 的区域内
2. 每个 agent 运行一个中等复杂度的行为树（至少 15 个节点：包含巡逻、追击、攻击、撤退行为）
3. 使用 `Profiler.BeginSample/EndSample`（Unity）或 `TRACE_CPUPROFILER_EVENT_SCOPE`（UE）在以下位置插入 marker：
   - 整个 AI 更新循环的总耗时
   - BT tick 耗时
   - 感知查询耗时
   - Blackboard 读写耗时
4. 在 Profiler 中运行 30 秒，导出性能数据
5. 回答以下问题：
   - Top 3 耗时子系统是什么？各占 AI 总预算的百分之几？
   - 每个 agent 的平均 tick 时间是多少？是否有 outlier（某些 agent 显著慢于其他）？
   - GC 分配情况如何？Tick 路径中有哪些分配来源？
6. 为 Top 1 瓶颈提出至少两种优化方案，估计优化后的性能提升

**验收标准**：
- 清楚识别了 Top 3 瓶颈，每个瓶颈有精确的 ms 数值
- 对 Top 1 瓶颈提出了至少两种不同的优化策略，并量化预期收益

### 练习 2：实现 Time-Sliced AI 更新系统

**目标**：实现一个将 1000 个 AI agent 均匀分布到 10 帧的 time-slicing 调度器。

**步骤**：
1. 设计 `AIScheduler` 类，管理 agent 的 tick 调度：
   - 维护 agent 列表和每帧处理数量 `batchSize = ceil(agentCount / sliceFrameCount)`
   - 每帧从当前游标位置开始，tick `batchSize` 个 agent
   - 游标推进，到达列表末尾时回绕到开头
2. 支持**动态 agent 加入/移除**（agent 死亡/生成时）而不破坏时间分布
3. 支持**紧急唤醒**：agent 收到伤害或检测到玩家时，立即加入当前帧的 tick 队列
4. 实现一个简单的 Profiler 叠加层，显示每帧实际 tick 的 agent 数量和 AI 总耗时
5. 比较 time-slicing 前后的帧时间稳定性（标准差）

**验收标准**：
- 1000 个 agent 在 10 帧内均匀分布，每帧 tick agent 数在 95-105 之间
- agent 生成/销毁不会导致某一帧的 agent 数出现 > 20% 的尖峰
- 紧急唤醒的 agent 在事件发生的同一帧被 tick
- 帧时间标准差相比无 time-slicing 时降低至少 60%

### 练习 3（可选）：Unity Jobs/Burst 并行 BT 评估

**目标**：将你的行为树评估逻辑从主线程 `MonoBehaviour.Update()` 迁移到 Burst 编译的 `IJobParallelFor`。

**前置条件**：已完成 Tutorial 08 中的类基行为树实现。

**步骤**：
1. 将 per-agent 的 AI 数据重构为 unmanaged struct（`AgentAIData`），使用 `NativeArray<AgentAIData>` 存储
2. 将行为树的关键条件评估逻辑（距离检查、血量比较、状态机转移）实现为纯函数，标记 `[BurstCompile]`
3. 实现 `AIEvaluateJob : IJobParallelFor`，在 `Execute(int index)` 中完成单个 agent 的一帧决策
4. 在主线程的 `Update()` 中调度 Job：`new AIEvaluateJob { ... }.Schedule(agentCount, 64).Complete();`
5. 对比单线程版本和 Job 版本在 100、500、1000 个 agent 时的 CPU 耗时
6. 记录 Burst 编译的限制：哪些代码无法在 Burst 中运行？你是如何处理这些限制的？

**验收标准**：
- 1000 个 agent 的 AI 评估在 3ms 内完成（含 Job 调度开销）
- 性能相比单线程版本提升至少 3x
- 无托管内存分配在 Job 的 Execute 路径中

---

## 4. 扩展阅读

- **Unity DOTS AI Patterns** — [DOTS Best Practices Guide](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/)，特别关注 `IJobEntity`、`Aspect` 和 `EntityCommandBuffer` 在 AI 系统中的应用模式
- **UE5 MassEntity Framework** — [MassEntity Overview](https://docs.unrealengine.com/5.3/en-US/mass-entity-in-unreal-engine/), [Mass AI](https://docs.unrealengine.com/5.3/en-US/mass-ai-in-unreal-engine/) — 城市人群、野生动物的批量 AI 处理的官方架构文档
- **Data-Oriented Design (Richard Fabian)** — 免费在线书籍 [dataorienteddesign.com](https://www.dataorienteddesign.com/dodbook/)，第 3 章 "Existential Processing" 和第 5 章 "Component-Based Design" 直接适用于 AI 数据布局
- **GDC Performance Talks**:
  - *"AI and Performance: Case Studies from The Last of Us Part II"* (Naughty Dog, GDC 2021) — 大规模 AI 系统的 profiling 方法论，包含 BT、感知、寻路的集成性能分析
  - *"Building a Better Centaur: AI for Horizon Forbidden West"* (Guerrilla, GDC 2023) — LOD 系统、屏幕外 AI 优化、行为保真度与性能的平衡策略
  - *"Agents of Mayhem: Scalable AI Design"* (Volition, GDC 2016) — 开放世界中数百个 AI agent 的架构设计，包含 Job System 的实际性能数据
- **Game AI Pro 3** — 第 7 章 "Architecture Tricks: Managing AI in Large Game Worlds" 和第 23 章 "Building the AI for Halo Wars 2's Blitz Mode" — 生产环境中的大规模 AI 架构战例
- **C++ Cache Optimization** — [What Every Programmer Should Know About Memory (Ulrich Drepper)](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf) — 虽然不是 AI 专用，但 Section 3 (CPU Caches) 和 Section 6 (Multi-Threaded Optimizations) 是理解 SoA vs AoS 的基础

---

## 常见陷阱

### 1. 未经 Profiling 的过早优化

**症状**：花了 3 天实现对象池和 struct Blackboard，优化后帧率毫无变化。

**根因**：没有测量就假设瓶颈在哪里。真正的瓶颈可能是 NavMesh 路径查询每帧触发（每次 0.5ms），而你优化的 BT 节点遍历只占总预算的 5%。

**解法**：永远先 profile，后优化。使用 80/20 法则——优化占比最高的 20% 代码路径。写优化代码之前，问自己："这个函数的 `Profiler.BeginSample` 显示它占总帧时间的百分之几？" 如果答案是 "不知道"，那就先去测量。

### 2. LOD Pop-in 过于明显

**症状**：摄像机向远处移动时，AI 在可见范围内突然从"流畅战斗"切换为"僵硬站立"。玩家可以清楚地看到切换边界。

**根因**：LOD 切换是瞬间的，且低 LOD 级别的行为表现与高 LOD 差异过大。AI 从 LOD 0（完整 BT 战斗）降到 LOD 1（简化 FSM 仅巡逻）时，动画和行为同时跳变。

**解法**：
- LOD 切换范围必须大于渲染 LOD 范围——AI LOD 降级应该发生在 AI 模型被渲染裁剪之前
- 在 LOD 切换时使用过渡状态：LOD 0 → LOD 1 时，先在 Blackboard 中保存即将执行的行为标签，LOD 1 的简化 FSM 启动时优先过渡到该行为
- 为 LOD 切换添加视觉缓冲：降级前的最后一个非战斗行为完成后才切换，而非立即中断

### 3. Time-Slicing 导致的"思考延迟"

**症状**：使用 time-slicing 后，10 帧更新一次的 agent 对角色的攻击反应慢了 166ms（10 帧 / 60fps）。在快速近战中，这个延迟让 AI 显得"迟钝"。

**根因**：Time-slicing 均匀分配 CPU 预算，但不等同于均匀分配**响应时间**。紧急事件（攻击、受伤、目标消失）需要即时响应，但 scheduler 不知道哪些 agent 正在经历紧急事件。

**解法**：
- 紧急事件必须绕过 scheduler：在事件发生时立即将该 agent 提升到当前帧的 tick 队列
- 使用 **双级 tick 频率**：所有 agent 每帧执行"快速检查"（< 0.001ms），包括伤害标记、目标状态变化——只有完整决策逻辑受 time-slicing 控制
- 为近距离/高频交互的 agent 禁用 time-slicing——只有中远距离 agent 使用分片调度

### 4. 池化泄漏：忘记 Reset 状态

**症状**：AI agent 在对象池中重用后，偶尔表现出前一个 agent 的行为——一个刚刷新的敌人直接进入"撤退"状态，或者持有不存在的目标引用。

**根因**：`Return()` 方法没有完全清除节点/agent 的运行时状态。`_currentChildIndex`、`_stateTimer`、`_targetEntity` 等字段保留了上一次使用的值。

**解法**：
- 每个 `PooledBTNode` 的 `Reset()` 方法必须是**幂等的**——调用两次与调用一次效果相同
- 实现单元测试验证池化正确性：`Rent → Tick(3 frames) → Return → Rent → 断言(_currentChildIndex == 0 && _stateTimer == 0)`
- 在 Debug Build 中，池归还时将敏感字段（指针、Entity ID）填充为哨兵值（如 `0xDEAD`），使"使用已归还对象"的 bug 更容易复现

### 5. 多线程 Blackboard 数据腐化

**症状**：在启用并行 AI 评估后，某些 agent 偶尔读取到半更新的 Blackboard 数据——目标位置是新的（帧 N），但目标类型标签是旧的（帧 N-1）。AI 做出基于不一致数据的决策。

**根因**：Blackboard 的多个 Key 被不同线程同时写入，读线程可能看到部分更新的状态。没有原子性保证跨 Key 的一致性。

**解法**：
- **版本号机制**：全局 Blackboard 维护一个递增的 `uint _version`。AI 系统在同步阶段开始前递增版本号，写入 Key 时附上版本号。Agent 读取时比较版本号——不一致的读取被丢弃并重试
- **双缓冲 Blackboard**：维护两个 Blackboard 副本（`_front` 和 `_back`）。当前帧所有 agent 读取 `_front`（只读），所有写入进入 `_back`。帧结束时 atomic swap `_front ↔ _back`
- **限制并行写入源**：只有 AI 系统的同步阶段可以写入全局 Blackboard——agent 本身的 `Execute()` 只写入本地 Blackboard。这从根本上消除了并发写冲突

---

> **下一步**: 恭喜完成本系列全部 17 个教程。性能优化是 AI 工程师的"最后一道工序"——在行为正确的前提下，确保系统可以在目标硬件上支撑设计中的 agent 规模。建议在面试准备中使用本教程中的练习 1 和练习 2 作为实际动手项目——面试官对"你自己 profile 过并优化过"的系统比"你说你了解性能优化"的叙述更有兴趣。
