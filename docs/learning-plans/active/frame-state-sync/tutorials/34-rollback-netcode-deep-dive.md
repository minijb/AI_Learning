---
title: "预测回滚网络深度剖析"
updated: 2026-06-05
---

# 预测回滚网络深度剖析

> 预计耗时: 75min | 前置: [[12-lockstep-advanced|12-帧同步进阶]]

---

## 1. 概念回顾与算法详解

### 1.1 快速回顾

教程 12 第 3 节已详细讲解了 GGPO 预测回滚的基础原理与简化实现：核心思想是用 CPU 换延迟——不等远程输入到达，先用预测输入执行并渲染，预测错误时回滚重算。本节不再重复那些基础，而是从**精确的帧级时间线**和**数学模型**入手，深入那些教程 12 未覆盖的生产级细节。

> **重温教程 12**：如果你对 `RollbackManager` 的 `SaveFrame`/`LoadFrame`/`CheckRollback` 三个核心循环还不熟悉，请先复习教程 12 的 3.4~3.5 节。

### 1.2 帧级时间线：从执行到回滚的完整序列

以下是一个精确的每帧分解，覆盖**保存→采样→预测→执行→渲染→收包→检测→回滚→重算→重新渲染**的完整链路。

```
时间轴 (每一列 = 一帧, 60fps = 16.67ms/帧)
FrameDelay = 2 帧 (人为缓冲)

═══════════════════════════════════════════════════════════════════════════
Frame:     N-5    N-4    N-3    N-2    N-1     N     N+1    N+2    N+3
═══════════════════════════════════════════════════════════════════════════
本地输入:  ←─── 本地玩家在每个帧都采样自己的输入 ───→
远程输入:  [真实] [真实] [真实] [真实] [???] [???] [???] [???] [???]
           └─── 已到达 ──→└── 尚未到达 (需预测!) ──→
═══════════════════════════════════════════════════════════════════════════

Frame N 时刻发生了什么：

┌─────────────────────────────────────────────────────────────────┐
│ 1. SaveState(N)        将游戏完整状态拷贝到 Slot[N % BUF_SIZE] │
│ 2. SampleLocalInput()  读取本地键盘/手柄                        │
│ 3. PredictRemoteInput() 远程输入尚未到达 → 预测为"无操作"或     │
│                           "上一帧方向保持"                       │
│ 4. Simulate(N)         输入 = (本地真实 + 远程预测)              │
│ 5. Render(N - 2)       渲染 2 帧前的状态 (FrameDelay=2)         │
│                          玩家看到的是 N-2 帧的画面               │
└─────────────────────────────────────────────────────────────────┘

Frame N+1 时刻发生了什么：

┌─────────────────────────────────────────────────────────────────┐
│ 1. SaveState(N+1)      保存当前状态                             │
│ 2. 收包！远程玩家 Frame N-3 的输入到达 (延迟 = 3帧)            │
│ 3. CheckRollback(N-3):                                          │
│    - 从 Slot[N-3] 读取当时保存的 remoteInput_used               │
│    - 对比：real != predicted → MISMATCH!                        │
│ 4. Rollback(N-3):                                               │
│    a. LoadSnapshot(N-3)  ← 恢复 Slot[N-3] 的完整游戏状态       │
│    b. 用正确的远程输入重新执行 Frame N-3                       │
│    c. 用远程 N-2 输入执行 Frame N-2 (此时也可能到达)            │
│    d. 用远程 N-1 输入执行 Frame N-1                            │
│    e. 用远程 N   输入执行 Frame N   (也可能仍需预测)           │
│    f. 重新执行 Frame N+1                                        │
│ 5. 渲染回滚后的当前帧 (N-1, 因为 FrameDelay=2)                  │
│    注意：玩家可能看到画面"回跳"，这是回滚的视觉代价            │
└─────────────────────────────────────────────────────────────────┘
```

关键观察：**Frame N+1 时收到了 3 帧前 (N-3) 的远程输入**。这说明网络单向延迟约为 3 帧 (≈50ms)。在 FrameDelay=2 的情况下，至少 1 帧需要回滚。

### 1.3 数学模型

回滚系统的核心可量化为以下公式：

```
RenderedFrame  = CurrentTick - FrameDelay
InputsUsed[N]  = (local_input[N], remote_input[N-RTTover2])
                 其中 RTTover2 ≈ 网络单向延迟 (帧数)

RollbackDepth  = CurrentTick - LastConfirmedTick
                 = max(0, RTTover2 - FrameDelay)

如果 RollbackDepth > 0:
    需要从 LastConfirmedTick+1 帧回滚到 CurrentTick
    总回滚量 = RollbackDepth 帧

ResimulationBudget = 16.67ms (per render frame)
TimePerSimFrame = ResimulationBudget / max(1, RollbackDepth)
```

**例子**：60fps 格斗游戏，RTT=100ms，FrameDelay=2
- RTTover2 ≈ 3.33 帧 (100ms/2/16.67ms)，取整为 3 帧
- `RollbackDepth = max(0, 3 - 2) = 1` 帧
- 每帧预算 = 16.67ms / 1 = 16.67ms —— 充裕

**反例**：RTT=300ms，FrameDelay=2
- RTTover2 ≈ 9 帧
- `RollbackDepth = max(0, 9 - 2) = 7` 帧
- 每帧预算 = 16.67ms / 7 ≈ 2.38ms —— 非常紧张！

这直接引出了第 3 节的**死亡螺旋问题**。

---

## 2. 输入衰减 (Input Decay / Input Fading)

> 本节内容**不出现在任何现有教程中**。它是 Rocket League 团队在 GDC 演讲中首次公开的生产级技术。

### 2.1 问题：全强度预测的视觉灾难

考虑以下场景：P1（你）正在向前跑，P2（对手）正在向你冲过来。在某一帧，P2 突然急转弯向右。你的客户端还不知道这个转弯——它还在预测 P2 继续向前冲。

```
预测路径 (全强度 100% × 7帧):
  P1 ──────────────────→
       ↑
       │  P2 预测位置 (直冲)
       │  × ← 远程实际位置 (右转)
       │     (差距 = 7帧 × 全速)
       │
       └── 回滚发生时：P2 从画面左侧"瞬移"到右侧
          视觉上极度 jarring (撕裂感)
```

回滚发生时，如果预测输入的幅度等同于真实输入，位置误差能达到 7 帧 × 移动速度。在格斗游戏中，这可能意味着角色凭空"瞬移"半个屏幕。

### 2.2 解决方案：输入强度随时间衰减

**核心洞察**：比起预测"玩家会做什么"，更安全的假设是"玩家**越来越可能什么都不做**"。因为：
- 预测错误时，**欠预测（undershoot）**→ 角色回弹少 → 人眼几乎察觉不到
- 预测正确时，**过预测（overshoot）**→ 角色跳跃幅度大 → 非常刺眼

输入衰减的策略：

```
预测帧编号:   1     2     3     4    5+
输入强度:    100%  66%   33%   10%   0%
```

这意味着：远程输入只在前 3 帧有显著影响，之后快速衰减到零。结合 GGPO 默认的"假设无操作"策略，衰减后的预测值本质上是：**从当前已知状态向"无操作"状态的平滑过渡**。

### 2.3 视觉效果对比

```
无衰减 (全强度预测 100% × 5帧):
  真实路径:  ───┐
                └── (右转)
  预测路径:  ────────→ (直走)
  回滚时:   角色从右侧"弹回"到下方拐角处 ← 非常明显!

有衰减 (100%→66%→33%→10%→0%):
  真实路径:  ───┐
                └── (右转)
  预测路径:  ───╲ (逐渐减速)
                  ╲
  回滚时:   角色轻微滑动到正确位置 ← 几乎察觉不到!
```

Rocket League 使用此技术的场景：车辆在空中的旋转预测。高速旋转时，如果预测错误，衰减使得车辆"慢慢停下旋转"而不是"疯狂旋转后突然静止"——前者看起来像空气阻力，后者看起来像网络故障。

> **参考**：Jared Cone, _Rocket League's Physics Rollback_, GDC 2018.

### 2.4 完整实现

```csharp
using System;
using System.Runtime.CompilerServices;

/// <summary>
/// 带衰减的远程输入预测器。
/// 
/// 核心算法：
/// - 收到最后一次真实输入后，创建一个衰减曲线
/// - 第 1 帧：100% 真实输入值
/// - 第 2~3 帧：线性衰减到 0%
/// - 第 4+ 帧：归零（等效于 GGPO 的"假设无操作"）
/// 
/// 这样做的物理直觉：玩家不做新操作时，"上一个操作的效果"
/// 随着时间的推移自然衰减。这模拟了操作的"持续时间限制"。
/// </summary>
public class InputDecayPredictor
{
    /// <summary>衰减窗口：超过此帧数后输入归零</summary>
    const int DECAY_WINDOW = 4;

    /// <summary>衰减曲线：第 i 帧的保留系数</summary>
    static readonly float[] DecayTable = { 1.0f, 0.66f, 0.33f, 0.10f, 0.0f };

    /// <summary>最后一次收到的真实远程输入</summary>
    PlayerInput lastRealInput;

    /// <summary>收到最后一次真实输入的帧号</summary>
    int lastRealInputFrame;

    /// <summary>衰减模式开关</summary>
    bool decayEnabled;

    public InputDecayPredictor(bool enableDecay = true)
    {
        decayEnabled = enableDecay;
        lastRealInput = PlayerInput.Empty;
        lastRealInputFrame = -999;
    }

    /// <summary>
    /// 当收到一个远程真实输入时调用。
    /// 这会重置衰减曲线——远程输入从此刻起重新开始衰减。
    /// </summary>
    public void OnRemoteInputReceived(int frame, PlayerInput input)
    {
        lastRealInput = input;
        lastRealInputFrame = frame;
    }

    /// <summary>
    /// 为当前帧预测远程输入。
    /// 
    /// 如果上一次真实输入是 N 帧前收到的：
    /// - N=0 (本帧刚收到): 返回真实输入
    /// - N=1: 返回真实输入的 66%
    /// - N=2: 返回真实输入的 33%
    /// - N=3: 返回真实输入的 10%
    /// - N≥4: 返回空输入 (无操作)
    /// </summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public PlayerInput Predict(int currentFrame)
    {
        if (!decayEnabled)
        {
            // 无衰减模式：永远返回最后一次真实输入
            // 这是简单的"方向保持"预测（比"无操作"稍好）
            return lastRealInput;
        }

        int framesSinceLastReal = currentFrame - lastRealInputFrame;

        if (framesSinceLastReal <= 0)
            return lastRealInput;  // 本帧有真实输入

        if (framesSinceLastReal >= DecayTable.Length)
            return PlayerInput.Empty;  // 完全衰减

        float factor = DecayTable[framesSinceLastReal];
        return PlayerInput.Lerp(PlayerInput.Empty, lastRealInput, factor);
    }

    /// <summary>重置预测器状态（对局结束/重连时调用）</summary>
    public void Reset()
    {
        lastRealInput = PlayerInput.Empty;
        lastRealInputFrame = -999;
    }
}

/// <summary>
/// 玩家输入的简洁表示（16-bit 足够存储格斗游戏所有按键）。
/// 保持与教程 12 的 FrameInput 兼容。
/// </summary>
public struct PlayerInput : IEquatable<PlayerInput>
{
    public ushort packed;

    // 位域布局 (示例):
    // [15-12] 方向: 0000=无, 0001=上, 0010=下, 0100=左, 1000=右
    // [11-8]  按钮组: 0001=拳, 0010=脚, 0100=特殊, 1000=防御
    // [7-0]   预留

    public static PlayerInput Empty => new PlayerInput { packed = 0 };

    public bool IsEmpty => packed == 0;

    /// <summary>
    /// 在两个输入之间线性插值。
    /// 注意：对离散按键输入，Lerp 可能产生非整数值。
    /// 这里采用"分量级缩放"：每个方向分量乘以 factor 后四舍五入。
    /// </summary>
    public static PlayerInput Lerp(PlayerInput a, PlayerInput b, float t)
    {
        if (t >= 1.0f) return b;
        if (t <= 0.0f) return a;

        // 分别提取方向 X 和 Y（简化：假设高 4 位编码方向）
        // 真实实现需要按具体按键布局逐分量处理
        int dirA = (a.packed >> 12) & 0xF;
        int dirB = (b.packed >> 12) & 0xF;

        // 插值方向分量 (将方向转换为 -1/0/1 向量后插值)
        float ax = ((dirA >> 2) & 1) - ((dirA >> 3) & 1);  // 左=-1, 右=+1
        float ay = ((dirA >> 0) & 1) - ((dirA >> 1) & 1);  // 下=-1, 上=+1
        float bx = ((dirB >> 2) & 1) - ((dirB >> 3) & 1);
        float by = ((dirB >> 0) & 1) - ((dirB >> 1) & 1);

        float rx = ax + (bx - ax) * t;
        float ry = ay + (by - ay) * t;

        // 离散化回方向位
        uint newDir = 0;
        if (rx > 0.3f) newDir |= 0b1000;  // 右
        if (rx < -0.3f) newDir |= 0b0100; // 左
        if (ry < -0.3f) newDir |= 0b0010; // 下
        if (ry > 0.3f) newDir |= 0b0001;  // 上

        // 按钮部分：不插值，t<0.5 时用 a 的按钮，否则归零
        ushort buttons = t < 0.5f ? (ushort)(a.packed & 0x0FFF) : (ushort)0;

        return new PlayerInput { packed = (ushort)((newDir << 12) | buttons) };
    }

    public bool Equals(PlayerInput other) => packed == other.packed;
    public override bool Equals(object obj) => obj is PlayerInput pi && Equals(pi);
    public override int GetHashCode() => packed;
    public static bool operator ==(PlayerInput a, PlayerInput b) => a.packed == b.packed;
    public static bool operator !=(PlayerInput a, PlayerInput b) => a.packed != b.packed;
}
```

### 2.5 衰减策略对比

| 策略 | 误预测位置误差 | 视觉质量 | CPU 开销 | 适合场景 |
|------|--------------|---------|---------|---------|
| 无衰减（全强度预测） | 大 (N帧 × 全速) | 差——可见瞬移 | 最低 | RTT<20ms 的局域网 |
| 常数衰减（线性→0） | 中 (N帧 × 平均50%) | 中等 | 低 | 通用推荐 |
| 非线性衰减 (加速曲线) | 小 | 好 | 低 | 高动态游戏 (Rocket League) |
| 无操作预测 (衰减到0=1帧) | 极小 | 最好 (但延迟感强) | 最低 | 格斗/回合制 |

**Rocket League 的特别之处**：RL 使用了非线性衰减——因为车辆在空中旋转有惯性，物理引擎让旋转自然衰减与输入衰减叠加后效果更好。Jared Cone 将其描述为"假装对手在逐渐松开摇杆，而不是突然松开"。

---

## 3. 性能预算与"死亡螺旋" (Performance Budget & Spiral of Death)

> 这是回滚网络系统中**最危险也最容易被忽视**的问题。它不发生在开发环境（局域网 0ms 延迟），但一上线就炸。

### 3.1 做数学：你的游戏能承受多少回滚帧？

回滚系统的性能约束来自一个硬性现实：**每个渲染帧的预算是固定的 16.67ms（60fps）**。如果这一帧内发生了回滚，需要在此预算内重算若干帧。

```
设：
  TickRate   = 60 fps (每帧 16.67ms)
  RTT        = 300ms (真实网络条件)
  FrameDelay = 3 帧 (输入缓冲)

RTT 的单向帧数 = 300ms / 16.67ms = 18 帧
(双向 300ms = 单向 150ms ≈ 9帧; 但回滚需要覆盖的是lastConfirmed→current，
实际需要处理的帧数取决于对端输入到达的延迟。)

更精确的计算：
  单向延迟 = RTT/2 = 150ms ≈ 9 帧
  RollbackFrames = max(0, 单向延迟帧数 - FrameDelay)
                 = max(0, 9 - 3) = 6 帧

每渲染帧预算 = 16.67ms
每仿帧可用时间 = 16.67ms / 6 ≈ 2.78ms

如果单帧仿真耗时 > 2.78ms → 爆预算 → 死亡螺旋
```

### 3.2 死亡螺旋的精确机制

```
第 N 帧:  回滚 6 帧，仿真耗时 18ms > 16.67ms
          → 第 N 帧晚了 1.33ms 完成

第 N+1 帧: 需要回滚 6 帧 (因为收包仍在累积) + 没做完的上一帧
          → 实际需要回滚 7 帧
          → 仿真耗时 21ms > 16.67ms
          → 晚了 4.33ms

第 N+2 帧: 需要回滚 8 帧 → 24ms → 晚了 7.33ms
          ...
          → 几秒内系统完全崩坏，帧率跌到个位数
```

这就是**死亡螺旋**：单帧超时的惩罚会累积到下一帧，使下一帧也超时，形成正反馈循环。一旦进入螺旋，唯一的出路是丢弃帧（引发更大的视觉问题）或断开连接。

### 3.3 性能预算计算器

```csharp
using System;
using System.Diagnostics;

/// <summary>
/// 回滚性能预算监控器。
/// 
/// 在每个渲染帧开始时调用 BeginFrame，结束时调用 EndFrame。
/// 它会：
/// 1. 追踪最近 N 帧的仿真时间分布
/// 2. 在接近死亡螺旋阈值时发出警告
/// 3. 在预算超支时触发保护机制
/// </summary>
public class PerformanceBudgetCalculator
{
    // --- 配置 ---
    const int TARGET_FPS = 60;
    const float FRAME_BUDGET_MS = 1000f / TARGET_FPS;  // 16.67ms

    /// <summary>单帧仿真时间的"安全上限"占预算的比例</summary>
    const float SAFETY_MARGIN = 0.70f;  // 70% 用于仿真，30% 留给渲染/系统

    /// <summary>超过此回滚深度时触发警告</summary>
    const int WARN_ROLLBACK_DEPTH = 5;

    /// <summary>超过此回滚深度时强制限制</summary>
    int maxRollbackFrames = 8;  // 可动态调整

    // --- 状态 ---
    Stopwatch frameTimer = Stopwatch.StartNew();
    int currentRollbackDepth;

    // 滑动窗口统计 (最近 60 帧)
    const int WINDOW_SIZE = 60;
    float[] simTimes = new float[WINDOW_SIZE];  // 每帧的仿真耗时 (ms)
    int windowIndex;
    int windowCount;

    // 死亡螺旋检测
    int consecutiveOverBudgetFrames;
    bool spiralDetected;
    float peakSimTimeMs;

    /// <summary>当前帧安全仿真预算 (ms)</summary>
    public float SafeSimBudgetMs => FRAME_BUDGET_MS * SAFETY_MARGIN;

    /// <summary>当前回滚深度需要多少预算</summary>
    public float RequiredBudgetMs =>
        GetAverageSimTimePerFrame() * currentRollbackDepth;

    /// <summary>是否处于死亡螺旋</summary>
    public bool InDeathSpiral => spiralDetected;

    public void BeginFrame(int rollbackDepth)
    {
        currentRollbackDepth = rollbackDepth;
        frameTimer.Restart();
    }

    /// <summary>
    /// 记录本帧仿真实际耗时。
    /// </summary>
    public void RecordSimTime(float simTimeMs)
    {
        simTimes[windowIndex] = simTimeMs;
        windowIndex = (windowIndex + 1) % WINDOW_SIZE;
        if (windowCount < WINDOW_SIZE) windowCount++;

        if (simTimeMs > peakSimTimeMs)
            peakSimTimeMs = simTimeMs;
    }

    /// <summary>
    /// 帧结束时调用。检查预算状况，必要时触发保护。
    /// 返回 true 表示帧按时完成，false 表示超时。
    /// </summary>
    public bool EndFrame()
    {
        frameTimer.Stop();
        float frameTotalMs = (float)frameTimer.Elapsed.TotalMilliseconds;

        // --- 检查 1：本帧是否超预算？ ---
        if (frameTotalMs > FRAME_BUDGET_MS)
        {
            consecutiveOverBudgetFrames++;
        }
        else
        {
            consecutiveOverBudgetFrames = 0;
        }

        // --- 检查 2：连续超预算 > 3 帧 → 死亡螺旋 ---
        if (consecutiveOverBudgetFrames > 3 && !spiralDetected)
        {
            spiralDetected = true;
            LogSpiralWarning();
            TriggerProtection();
        }
        else if (consecutiveOverBudgetFrames == 0 && spiralDetected)
        {
            spiralDetected = false;
        }

        // --- 检查 3：预测性预警 ---
        float avgSimTime = GetAverageSimTimePerFrame();
        float predictedBudget = avgSimTime * currentRollbackDepth;

        if (predictedBudget > SafeSimBudgetMs && !spiralDetected)
        {
            Console.WriteLine(
                $"[BUDGET WARN] Predicted sim={predictedBudget:F1}ms > " +
                $"safe={SafeSimBudgetMs:F1}ms. Depth={currentRollbackDepth}. " +
                $"Consider increasing FrameDelay or reducing max rollback.");
        }

        return frameTotalMs <= FRAME_BUDGET_MS;
    }

    float GetAverageSimTimePerFrame()
    {
        if (windowCount == 0) return 0;
        float sum = 0;
        for (int i = 0; i < windowCount; i++)
            sum += simTimes[i];
        return sum / windowCount;
    }

    void LogSpiralWarning()
    {
        Console.Error.WriteLine(
            $"\n╔══════════════════════════════════════════════════════════╗\n" +
            $"║  DEATH SPIRAL DETECTED!                                 ║\n" +
            $"║  Consecutive over-budget frames: {consecutiveOverBudgetFrames}                    ║\n" +
            $"║  Average sim time per frame: {GetAverageSimTimePerFrame():F2}ms                    ║\n" +
            $"║  Current rollback depth: {currentRollbackDepth}                              ║\n" +
            $"║  Peak single-frame sim time: {peakSimTimeMs:F2}ms                     ║\n" +
            $"║  ACTIONS TAKEN: reducing max rollback, increasing delay     ║\n" +
            $"╚══════════════════════════════════════════════════════════════╝");
    }

    void TriggerProtection()
    {
        // 保护措施 1：降低最大回滚帧数
        int oldMax = maxRollbackFrames;
        maxRollbackFrames = Math.Max(2, maxRollbackFrames - 2);

        // 保护措施 2：增加有效帧延迟（丢弃无法处理的帧）
        // 实际项目中会通知 RollbackManager 调整策略

        Console.WriteLine(
            $"[PROTECT] MaxRollbackFrames: {oldMax} → {maxRollbackFrames}");
    }

    /// <summary>
    /// 获取报告：当前预算使用情况。
    /// </summary>
    public BudgetReport GetReport()
    {
        return new BudgetReport
        {
            avgSimTimeMs = GetAverageSimTimePerFrame(),
            currentDepth = currentRollbackDepth,
            predictedTotalMs = GetAverageSimTimePerFrame() * currentRollbackDepth,
            budgetMs = FRAME_BUDGET_MS,
            safeBudgetMs = SafeSimBudgetMs,
            consecutiveOverBudget = consecutiveOverBudgetFrames,
            inSpiral = spiralDetected,
            peakSimTimeMs = peakSimTimeMs,
            maxRollbackFrames = maxRollbackFrames,
        };
    }
}

public struct BudgetReport
{
    public float avgSimTimeMs;
    public int currentDepth;
    public float predictedTotalMs;
    public float budgetMs;
    public float safeBudgetMs;
    public int consecutiveOverBudget;
    public bool inSpiral;
    public float peakSimTimeMs;
    public int maxRollbackFrames;

    public override string ToString() =>
        $"Sim: {avgSimTimeMs:F2}ms/frame × {currentDepth} depth = " +
        $"{predictedTotalMs:F1}ms / {budgetMs:F1}ms budget " +
        (inSpiral ? "[SPIRAL!]" : (predictedTotalMs > safeBudgetMs ? "[WARN]" : "[OK]"));
}
```

### 3.4 解决方案决策树

```
遇到性能预算问题？
│
├─ 方案 A: 降低逻辑 Tick Rate
│   └─ 60fps → 30fps：预算翻倍 (33ms/帧)
│      代价：手感变"肉"，画面可能需插值
│      适合：回合制、策略、卡牌游戏
│
├─ 方案 B: 限制最大回滚帧数
│   └─ maxRollbackFrames = 4
│      超出后：丢弃超时帧，用服务器权威状态覆盖
│      代价：偶尔"瞬移"但避免帧率崩溃
│      适合：动作游戏、MOBA
│
├─ 方案 C: 增加 FrameDelay
│   └─ FrameDelay 2→4：减少 2 帧回滚需求
│      代价：+33ms 输入延迟
│      适合：对输入延迟不太敏感的游戏
│
├─ 方案 D: ECS 性能优化
│   └─ 使用 DOD/ECS 架构，每帧仿真 < 1ms
│      让回滚 8 帧只需要 8ms，远低于 16ms 预算
│      适合：追求极致性能的 3A 项目
│
├─ 方案 E: 跳过渲染（仅仿真）
│   └─ 回滚期间：只跑逻辑不渲染
│      最后一帧才渲染，减少 GPU 压力
│      代价：实现复杂度高 (需要逻辑/渲染分离)
│      适合：渲染重的游戏
│
└─ 方案 F: 混合架构
    └─ 本地玩家：即时反馈 (预测执行)
       远程玩家：插值显示 (不预测，稍有延迟)
       代价：远程对手看起来有轻微延迟
       适合：>2 人对战 (无法为每人做回滚)
```

### 3.5 Tick Rate vs Max Rollback 速查表

| Tick Rate | 帧预算 | RTT=50ms 回滚帧 | RTT=100ms | RTT=200ms | RTT=300ms |
|-----------|--------|-----------------|-----------|-----------|-----------|
| 30 fps | 33.3ms | 0~1 帧 / 33ms | 1~2 帧 / 16ms | 3~4 帧 / 8ms | 5~6 帧 / 6ms |
| 60 fps | 16.7ms | 1~2 帧 / 8ms | 3~4 帧 / 4ms | 6~7 帧 / 2.4ms | 9~10 帧 / 1.7ms |
| 120 fps | 8.3ms | 2~3 帧 / 3ms | 6~7 帧 / 1.2ms | 12~13 帧 / 0.6ms | ⚠ 不可行 |

> 灰色背景 = 安全，黄色 = 紧张，红色 = 死亡螺旋风险高。
> 假设 FrameDelay=2，单帧仿真 1ms。

---

## 4. 状态保存策略优化

教程 12 的 `RollbackBuffer` 使用 `memcpy` 全量保存——这在状态较小时可行，但当游戏状态增长到数十 KB 以上时，每帧 memcpy 的巨大开销会成为瓶颈。本节详细介绍 5 种生产级优化策略。

### 4.1 策略一：连续内存布局 (Contiguous Memory Layout)

**思想**：将所有可变游戏状态放在一个连续的、固定布局的 `struct` 中。一次 `memcpy` 即可保存和恢复。

```cpp
// contiguous_save_state.h
#pragma once
#include <cstring>
#include <cstdint>
#include <new>

/// <summary>
/// 连续内存的游戏状态模板。
/// 
/// 核心约束：
/// 1. T 必须是 trivially copyable (no virtual, no pointers to heap)
/// 2. 所有动态数据必须内联在此 struct 内 (固定大小数组)
/// 3. sizeof(T) 决定每帧快照的内存开销
/// 
/// 优点：单次 memcpy，极快 (通常 < 1μs for < 16KB)
/// 缺点：状态大小固定，不支持动态实体数量
/// </summary>
template<typename T>
class ContiguousGameState
{
    static_assert(std::is_trivially_copyable_v<T>,
        "T must be trivially copyable for memcpy save/restore");

public:
    struct Slot {
        T      state;
        uint32_t frame;
        uint32_t checksum;  // 可选哈希
        bool    valid;
    };

    ContiguousGameState(size_t maxFrames)
        : m_capacity(maxFrames), m_head(0), m_count(0)
    {
        // 一次分配所有槽位，保证连续性和 cache locality
        m_slots = new Slot[maxFrames];
    }

    ~ContiguousGameState()
    {
        delete[] m_slots;
    }

    // 禁止拷贝 — 回滚系统只应有一个实例
    ContiguousGameState(const ContiguousGameState&) = delete;
    ContiguousGameState& operator=(const ContiguousGameState&) = delete;

    /// <summary>保存当前状态到指定帧号</summary>
    void Save(uint32_t frame, const T& state)
    {
        size_t idx = frame % m_capacity;

        // 单次 memcpy — 这是 contiguous layout 的核心优势
        std::memcpy(&m_slots[idx].state, &state, sizeof(T));
        m_slots[idx].frame = frame;
        m_slots[idx].valid = true;

        if (m_count < m_capacity) m_count++;
    }

    /// <summary>恢复到指定帧的状态</summary>
    /// <returns>true 表示快照存在且恢复成功</returns>
    bool Restore(uint32_t frame, T& outState) const
    {
        size_t idx = frame % m_capacity;
        if (!m_slots[idx].valid || m_slots[idx].frame != frame)
            return false;

        std::memcpy(&outState, &m_slots[idx].state, sizeof(T));
        return true;
    }

    /// <summary>标记槽位为无效（回滚超出范围时清理）</summary>
    void Invalidate(uint32_t frame)
    {
        size_t idx = frame % m_capacity;
        m_slots[idx].valid = false;
    }

    size_t Capacity() const { return m_capacity; }
    size_t Count() const { return m_count; }

private:
    Slot*  m_slots;
    size_t m_capacity;
    size_t m_head;
    size_t m_count;
};

/// <summary>
/// 使用示例：定义你的游戏状态为一个平凡可拷贝 struct。
/// 
/// 关键：此 struct 必须是固定大小的。实体数量等动态数据
/// 必须通过固定大小数组实现 (如 PlayerState players[4])。
/// </summary>
struct FightGameState {
    // 玩家状态 (固定 2 人)
    struct Player {
        int32_t  pos_x, pos_y;     // 定点数 raw value
        int32_t  vel_x, vel_y;
        int32_t  hp;
        uint8_t  facing;           // 0=右, 1=左
        uint8_t  state;            // 状态机当前状态
        uint8_t  state_timer;      // 状态已持续帧数
        uint8_t  combo_count;
        uint16_t input_history;    // 最近 4 帧输入 (每帧 4bit)
    };
    Player players[2];

    // 投射物 (固定最大 16 个)
    struct Projectile {
        int32_t pos_x, pos_y;
        int32_t vel_x, vel_y;
        uint8_t owner;      // 0=P1, 1=P2
        uint8_t active;     // 0=未激活, 1=活跃
        uint8_t type;
    };
    Projectile projectiles[16];

    // 全局状态
    uint32_t frame_number;
    uint32_t rng_state;        // 必须在状态内！
    int32_t  round_timer;      // 剩余帧数
    uint8_t  round_phase;      // 0=开场, 1=对战, 2=结束
    uint8_t  padding[3];       // 对齐

    // 确保 sizeof 是确定的
    static_assert(sizeof(FightGameState) < 4096,
        "State too large for per-frame snapshot");
};

// 使用
// ContiguousGameState<FightGameState> saveStates(256);
// saveStates.Save(frame, currentState);
// saveStates.Restore(rollbackFrame, currentState);
```

### 4.2 策略二：增量快照 (Delta Snapshots)

并非每帧每个字段都会变化。增量快照只保存**变化了的字段**。

```csharp
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

/// <summary>
/// 增量快照系统。
/// 
/// 做法：
/// - 每 10 帧保存一个完整快照 (Keyframe)
/// - 帧之间的帧只保存相对于上一帧的 delta
/// - 回滚时从最近的 keyframe 开始，依次应用 delta
/// 
/// 内存节省取决于"帧间变化率"。格斗游戏中，大部分帧只有
/// 1~2 个玩家在移动，投射物也相对静止——变化率通常 < 20%。
/// </summary>
public class DeltaSnapshotManager
{
    const int KEYFRAME_INTERVAL = 10;  // 每 10 帧一个全量快照

    struct Keyframe
    {
        public uint frame;
        public byte[] fullState;  // 全量序列化
    }

    struct Delta
    {
        public uint frame;
        public List<FieldChange> changes;
    }

    struct FieldChange
    {
        public ushort offset;    // 在状态字节数组中的偏移
        public ushort length;    // 变化的字节数
        public byte[] newValue;  // 新值
    }

    Keyframe[] keyframes;
    Delta[] deltas;
    int keyframeCount, deltaCount;
    int maxFrames;

    // 最近一次序列化的"上一帧"状态（用于计算 delta）
    byte[] lastSerializedState;

    public DeltaSnapshotManager(int maxHistory = 256)
    {
        maxFrames = maxHistory;
        keyframes = new Keyframe[maxHistory / KEYFRAME_INTERVAL + 1];
        deltas = new Delta[maxHistory];
    }

    /// <summary>
    /// 保存帧状态。自动决定保存全量还是 delta。
    /// </summary>
    public void Save(uint frame, byte[] stateBytes)
    {
        if (frame % KEYFRAME_INTERVAL == 0)
        {
            // 保存 keyframe
            keyframes[keyframeCount++] = new Keyframe
            {
                frame = frame,
                fullState = (byte[])stateBytes.Clone()
            };
        }
        else
        {
            // 计算并保存 delta
            var changes = ComputeDelta(lastSerializedState, stateBytes);
            deltas[deltaCount++] = new Delta
            {
                frame = frame,
                changes = changes
            };
        }

        // 更新"上一帧"引用（浅拷贝足够——下一帧会重新计算 delta）
        lastSerializedState = stateBytes;
    }

    /// <summary>
    /// 计算两个状态数组之间的差异。
    /// 返回变化区域的列表。
    /// </summary>
    List<FieldChange> ComputeDelta(byte[] oldState, byte[] newState)
    {
        if (oldState == null || oldState.Length != newState.Length)
            return CaptureFull(newState);  // 首个保存或大小不同

        var changes = new List<FieldChange>();
        int i = 0;

        while (i < oldState.Length)
        {
            // 找到第一个变化的字节
            if (oldState[i] == newState[i])
            {
                i++;
                continue;
            }

            // 标记变化区间的起点
            int start = i;
            // 找到连续变化区间的终点
            while (i < oldState.Length && oldState[i] != newState[i])
                i++;

            int length = i - start;
            var newVal = new byte[length];
            Array.Copy(newState, start, newVal, 0, length);

            changes.Add(new FieldChange
            {
                offset = (ushort)start,
                length = (ushort)length,
                newValue = newVal
            });
        }

        return changes;
    }

    List<FieldChange> CaptureFull(byte[] state)
    {
        return new List<FieldChange>
        {
            new FieldChange
            {
                offset = 0,
                length = (ushort)state.Length,
                newValue = (byte[])state.Clone()
            }
        };
    }

    /// <summary>
    /// 恢复到目标帧的状态。
    /// 从最近的 keyframe 开始，依次应用 delta。
    /// </summary>
    public byte[] Restore(uint targetFrame)
    {
        // 找到 ≤ targetFrame 的最近 keyframe
        Keyframe kf = default;
        bool found = false;
        for (int i = keyframeCount - 1; i >= 0; i--)
        {
            if (keyframes[i].frame <= targetFrame)
            {
                kf = keyframes[i];
                found = true;
                break;
            }
        }
        if (!found) throw new InvalidOperationException("No keyframe found");

        // 从 keyframe 的完整状态开始
        byte[] state = (byte[])kf.fullState.Clone();

        // 依次应用 delta 直到目标帧
        for (uint f = kf.frame + 1; f <= targetFrame; f++)
        {
            for (int d = 0; d < deltaCount; d++)
            {
                if (deltas[d].frame == f)
                {
                    ApplyDelta(state, deltas[d].changes);
                    break;
                }
            }
        }

        return state;
    }

    void ApplyDelta(byte[] state, List<FieldChange> changes)
    {
        foreach (var change in changes)
        {
            Array.Copy(change.newValue, 0, state, change.offset, change.length);
        }
    }
}
```

### 4.3 策略三：懒保存 / Copy-on-Write (Lazy Save)

**思想**：不是每帧都保存，而是在**回滚真正发生时**才进行深拷贝。在此之前只记录"哪些帧可能需要回滚"。

```cpp
// lazy_save_state.h
#pragma once
#include <cstring>
#include <vector>

/// <summary>
/// Copy-on-Write 懒保存策略。
/// 
/// 正常流程 (无回滚):
///   Save(N)  → 只递增引用计数，不拷贝数据
/// 
/// 回滚发生时:
///   Rollback(N) → 触发深拷贝，从共享池复制状态
/// 
/// 适用场景: 回滚概率低 (< 5%) 的游戏。
/// 优点: 正常帧几乎零开销
/// 缺点: 回滚帧的第一次访问有拷贝延迟
/// </summary>
template<typename T>
class LazySaveStateManager
{
    static_assert(std::is_trivially_copyable_v<T>);

    struct VersionedState {
        T        state;
        uint32_t frame;
        int      ref_count;  // 引用计数
    };

    std::vector<VersionedState> m_pool;
    T* m_current;  // 当前活跃状态指针 (在共享池中)

public:
    LazySaveStateManager()
    {
        m_pool.emplace_back();
        m_current = &m_pool.back().state;
        m_pool.back().ref_count = 1;
    }

    /// <summary>
    /// 正常帧的"保存"——几乎零开销。
    /// 只增加引用计数，标记此版本与当前帧关联。
    /// </summary>
    void Save(uint32_t frame)
    {
        // 当前状态由 m_current 指向。
        // 暂不拷贝——只是记录 frame 与此版本关联。
        // (简化实现：用 frame 索引到槽位)
        //
        // 真正的懒 save 维护一个 frame→versioned_state* 的映射。
        // 这里的关键是 save 操作本身不触发拷贝。
        (void)frame;  // 实际实现中会维护映射
    }

    /// <summary>
    /// 在修改状态之前调用。
    /// 如果当前版本的引用计数 > 1 (意味着已有 save 引用它)，
    /// 则执行 Copy-on-Write：复制一份新的版本。
    /// </summary>
    void OnBeforeModify()
    {
        auto& current_version = m_pool.back();

        if (current_version.ref_count > 1)
        {
            // COW: 创建新版本
            m_pool.emplace_back();
            auto& new_version = m_pool.back();
            std::memcpy(&new_version.state, &current_version.state, sizeof(T));
            new_version.ref_count = 1;
            m_current = &new_version.state;
        }
    }

    T* Current() { return m_current; }
    const T* Current() const { return m_current; }

    /// <summary>
    /// 回滚到指定帧的状态。
    /// 查找该帧对应的版本并返回。
    /// </summary>
    const T* GetStateForFrame(uint32_t frame) const
    {
        // 实际实现：二分查找 frame→version 映射
        (void)frame;
        return m_current;  // 占位
    }
};
```

### 4.4 策略四：环形缓冲区压缩 (Ring Buffer Compression)

旧帧不需要保留精度——它们只是为了"万一需要回滚"。对超过一定时间的帧进行**运行时压缩**（Run-Length Encoding）：

```csharp
/// <summary>
/// 简单的运行长度编码 (RLE) 压缩器。
/// 适合游戏状态中常见的"大片零"模式（未激活的实体槽位、
/// 不变的状态字段等）。
/// </summary>
public static class RLECompressor
{
    /// <summary>
    /// 压缩字节数组。输出格式:
    ///   [control_byte] [data...]
    ///   control_byte > 0: 后跟 control_byte 个不重复字节
    ///   control_byte < 0: 后跟 1 个字节，重复 -control_byte 次
    ///   control_byte = 0: 结束
    /// </summary>
    public static byte[] Compress(byte[] input)
    {
        var output = new List<byte>(input.Length);
        int i = 0;

        while (i < input.Length)
        {
            // 查找连续相同字节的 run
            int runStart = i;
            while (i < input.Length - 1 && input[i] == input[i + 1] && (i - runStart) < 127)
                i++;

            int runLength = i - runStart + 1;

            if (runLength >= 3)
            {
                // 有意义的 run (≥3 才值得压缩)
                output.Add((byte)(-(runLength - 1)));  // 负数表示 run
                output.Add(input[runStart]);
                i++;
            }
            else
            {
                // 查找不重复字节序列
                int literalStart = runStart;
                while (i < input.Length)
                {
                    if (i < input.Length - 1 && input[i] == input[i + 1])
                        break;  // 遇到 run，停止
                    if (i - literalStart >= 127)
                        break;  // 达到最大长度
                    i++;
                }
                int literalLength = i - literalStart;
                output.Add((byte)(literalLength - 1));
                for (int j = 0; j < literalLength; j++)
                    output.Add(input[literalStart + j]);
            }
        }

        output.Add(0);  // 结束标记
        return output.ToArray();
    }

    /// <summary>解压 RLE 数据</summary>
    public static byte[] Decompress(byte[] input)
    {
        var output = new List<byte>(input.Length * 2);
        int i = 0;

        while (i < input.Length)
        {
            sbyte control = (sbyte)input[i++];
            if (control == 0) break;

            if (control < 0)
            {
                // Run: 重复字节
                int count = -control + 1;
                byte val = input[i++];
                for (int j = 0; j < count; j++)
                    output.Add(val);
            }
            else
            {
                // Literal: 不重复字节
                int count = control + 1;
                for (int j = 0; j < count; j++)
                    output.Add(input[i++]);
            }
        }

        return output.ToArray();
    }
}
```

### 4.5 策略五：混合策略 (Hybrid)

```
全量快照 (每 10 帧)
    │
    ├─ 帧 0:  Full Snapshot [2KB]
    ├─ 帧 1:  Delta [200B]     ← 变化字段
    ├─ 帧 2:  Delta [150B]
    ├─ ...
    ├─ 帧 9:  Delta [180B]
    ├─ 帧 10: Full Snapshot [2KB]  ← 新的 keyframe
    ├─ 帧 11: Delta (RLE 压缩) [80B]  ← 旧帧可以压缩
    └─ ...

总计 10 帧开销:
  纯全量: 10 × 2KB = 20KB
  纯 delta: 2KB + 9 × 170B ≈ 3.5KB
  混合 (delta + RLE): 2KB + 9 × 90B ≈ 2.8KB
  节省: ~86%
```

### 4.6 性能对比总表

以下数据基于格斗游戏场景 (2 玩家，~2KB 状态大小)：

| 策略 | 每帧保存时间 | 恢复一帧时间 | 每帧内存 | 10帧总内存 | 实现复杂度 |
|------|------------|------------|---------|-----------|-----------|
| 全量 memcpy (T12) | 0.5μs | 0.5μs | 2KB | 20KB | 极低 |
| 连续内存布局 | 0.3μs | 0.3μs | 2KB | 20KB | 低 |
| 增量 Delta | 15μs | 50μs (累积) | ~200B/帧 | 3.5KB | 中 |
| 懒保存 (COW) | 0.05μs | 0.5μs+ | 2KB (回滚时) | 2KB | 中 |
| 环形缓冲 RLE | 0.5μs+30μs | 0.5μs+40μs | ~800B/帧 | 8KB | 中高 |
| 混合 (Keyframe+Delta+RLE) | 0.5μs~30μs | 0.5μs~90μs | 200~800B | 2.8KB | 高 |

> **选择指南**：状态 < 4KB → 全量 memcpy 最快最简单。状态 4~32KB → 使用连续内存布局 + 增量 delta。状态 > 32KB → 必须用混合策略。懒保存适合回滚率 < 5% 的场景。

---

## 5. 现代 Rollback 库对比

### 5.1 总览

| 库 | 语言 | 许可证 | 生态 | 适用引擎 | 特点 |
|----|------|--------|------|---------|------|
| **GGPO** | C/C++ | MIT | 格斗游戏标杆 | 任何 (C FFI) | 原始实现，Battle-tested，文档全，但集成复杂 |
| **GGRS** | Rust | MIT | Rust 游戏 | Bevy/Macroquad | 类型安全，P2P+Spectator，活跃维护 |
| **backroll-rs** | Rust | MIT | Rust 生态 | 任何 Rust 引擎 | 纯 Safe Rust，无 unsafe |
| **Corrade/netcode-rollback** | C# | MIT | Unity | Unity | Unity-native，DarkRift 网络 |
| **SnapNet** | C++ | 商业 | AAA 项目 | UE/Unity | 全栈方案，含中继服务器、匹配 |
| **GGPO-UE** | C++ | MIT | UE | UE5 | 社区维护的 UE 封装 |

### 5.2 选型决策指南

```
你的项目是...
│
├─ Unity 格斗游戏 (1v1 P2P)
│   → Corrade/netcode-rollback
│     理由: Unity 原生集成，DarkRift 低延迟传输，
│           社区支持好，中文文档丰富
│
├─ Unity 非格斗游戏 (>2 人)
│   → 不建议纯 P2P rollback
│     考虑：服务端权威 + 客户端预测 + 插值混合架构
│
├─ UE5 格斗游戏
│   → ⚠ 无完美即插即用方案
│     选择 A: 自建 (基于本教程的 C++ 模板)
│     选择 B: GGPO C SDK + UE C++ FFI 封装
│     选择 C: SnapNet (商业，省心但昂贵)
│     详见第 6 节
│
├─ Rust 动作/格斗游戏 (Bevy/Macroquad)
│   → GGRS (首选) 或 backroll-rs
│     理由: 类型安全，Rust 生态无缝，文档出色
│
├─ AAA 商用 (多平台、>100 万预算)
│   → SnapNet
│     理由: 中继服务器、匹配、回放、反作弊一整套
│
└─ 学习/研究/原型
    → GGPO (C SDK) — 理解原始设计
      GGRS (Rust) — 理解现代 API 设计
      本教程代码 — 理解核心机制
```

### 5.3 GGRS 集成示例

```rust
// GGRS 集成示例：基于 Bevy 引擎的 1v1 格斗游戏
// 依赖: ggrs = "0.10", bevy = "0.14"

use ggrs::{GGRSRequest, GGRSEvent, PlayerHandle, SessionBuilder};
use std::net::SocketAddr;

// ---- 定义游戏输入 ----
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct GameInput {
    // 占 1 字节 —— GGRS 要求输入可哈希且紧凑
    data: u8,
}

impl GameInput {
    fn up(&self)    -> bool { self.data & 0b0001 != 0 }
    fn down(&self)  -> bool { self.data & 0b0010 != 0 }
    fn left(&self)  -> bool { self.data & 0b0100 != 0 }
    fn right(&self) -> bool { self.data & 0b1000 != 0 }
    fn punch(&self) -> bool { self.data & 0b0001_0000 != 0 }
    fn kick(&self)  -> bool { self.data & 0b0010_0000 != 0 }
}

// ---- 实现 GGRS 所需的 Config 特征 ----
#[derive(Debug)]
struct FighterConfig;
impl ggrs::Config for FighterConfig {
    type Input = GameInput;
    type State = FightState;          // 游戏状态 (需实现 Clone + PartialEq)
    type Address = SocketAddr;

    // 回滚时的输入延迟 (帧)
    fn input_delay(&self) -> usize { 2 }
}

// ---- 游戏状态 ----
#[derive(Clone, PartialEq)]
struct FightState {
    p1_x: f32, p1_y: f32, p1_hp: u32,
    p2_x: f32, p2_y: f32, p2_hp: u32,
    frame: u32,
}

// GGRS 要求: advance_frame(state, inputs)
// 会被 GGRS 在正常执行、回滚重算时自动调用
fn advance_frame(state: &mut FightState, inputs: &[(GameInput, GameInput)]) {
    // inputs[0].0 = 本地玩家输入, inputs[0].1 = 远程玩家输入
    let (local, remote) = &inputs[0];
    // ... 执行游戏逻辑 ...
    state.frame += 1;
}

// ---- 初始化 GGRS 会话 ----
fn start_ggrs_session(local_port: u16, remote_addr: SocketAddr) {
    let local_handle = PlayerHandle(0);
    let remote_handle = PlayerHandle(1);

    let mut sess = SessionBuilder::<FighterConfig>::new()
        .with_num_players(2)
        .with_input_delay(2)
        .add_player(ggrs::PlayerType::Local, local_handle, local_port)
        .expect("add local player")
        .add_player(ggrs::PlayerType::Remote(remote_addr), remote_handle, 0)
        .expect("add remote player")
        .start_synctest_session()  // 开发阶段用 SyncTest
        .expect("start session");

    // 主循环
    loop {
        // 1. 采样本地输入 (来自手柄/键盘)
        let local_input = sample_local_input();
        sess.add_local_input(local_handle, local_input);

        // 2. 推进帧 → GGRS 内部处理 rollback
        let requests = sess.advance_frame().expect("advance");

        // 3. 处理 GGRS 请求 (发送/接收网络包)
        for req in requests {
            match req {
                GGRSRequest::SendPacket(msg) => {
                    // 发送给远程玩家
                    send_to(remote_addr, &msg);
                }
            }
        }

        // 4. 处理 GGRS 事件 (通知)
        for evt in sess.events() {
            match evt {
                GGRSEvent::Synchronizing { .. } => {
                    println!("Syncing...");
                }
                GGRSEvent::Synchronized { .. } => {
                    println!("Synchronized!");
                }
                GGRSEvent::Disconnected { .. } => {
                    println!("Opponent disconnected");
                    return;
                }
                GGRSEvent::NetworkInterrupted { .. } => {
                    println!("Network interrupted");
                }
                _ => {}
            }
        }

        // 5. 获取当前游戏状态并渲染
        let state = sess.current_state();
        render(state);
    }
}
```

### 5.4 各库深度对比

#### GGPO (C/C++ SDK)

- **优势**：最成熟的实现，经 15+ 商业游戏验证。`ggponet.h` API 清晰。
- **劣势**：C API 与现代引擎集成成本高。同步测试模式需要引擎支持 "Save/Load" 两个回调。无内建 P2P 传输——你需要自己搞定 UDP 传输。
- **典型集成成本**：2~4 周 (有经验者) 到 2~3 月 (新手)。

#### GGRS (Rust)

- **优势**：内存安全，Session API 简洁。Spectator 支持开箱即用。SyncTest 模式是无侵入的——GGRS 持有状态的 Copy，自定重算。
- **劣势**：Rust 生态限制——无法用于 Unity/UE。
- **注意**：作者在 2024 年声明后减少维护，需关注 fork 状态。

#### backroll-rs (Rust)

- **优势**：纯 Safe Rust (`#![forbid(unsafe_code)]`)。API 更接近 GGPO 原始设计（`save_state`/`load_state` 回调）。
- **劣势**：功能比 GGRS 少，社区更小。仍然需要自己处理传输层。
- **适用**：想彻底理解回滚实现细节时阅读其源码，或对安全性有极致要求的项目。

#### SnapNet (商业)

- **优势**：一站式——中继服务器、匹配、回放、反作弊、跨平台。AAA 项目（如 MultiVersus）使用。
- **劣势**：闭源付费，价格不透明。锁定 SnapNet 生态。
- **适用**：预算充足，不想自建网络基础设施的团队。

---

## 6. UE5 中的真实回滚

> **关键纠正**：UE 引擎自带的 `CharacterMovementComponent` (CMC) 回滚机制**不是 GGPO 式预测回滚**。这个混淆是 UE 网络面试中最常见的错误之一。

### 6.1 UE CMC Rollback vs True GGPO Rollback

| 维度 | UE CMC Rollback | True GGPO Rollback |
|------|----------------|-------------------|
| **目的** | 服务端验证移动合法性 | 隐藏网络延迟，给本地玩家即时反馈 |
| **谁跑逻辑** | 客户端先跑，服务端后验证 | 所有客户端各自跑，全权预测 |
| **回滚触发** | 服务端发现客户端移动不合法 | 远程真实输入与预测不一致 |
| **重算范围** | 只重算移动 (CMC 相关) | 重算**全部**游戏逻辑 |
| **延迟隐藏** | 不隐藏 (客户端始终落后服务端) | 隐藏 (本地输入立即响应) |
| **确定性要求** | 低 (只验证最终位置) | 极高 (逐位确定性) |
| **实现成本** | 低 (引擎内建) | 高 (完全自建) |
| **适用游戏类型** | FPS/TPS (移动为主) | 格斗/动作 (帧精确) |

一句话总结：**CMC 回滚验证"你移动得对不对"；GGPO 回滚隐藏"网络延迟的存在"。**

### 6.2 在 UE5 中实现真正的 GGPO 回滚

要在 UE5 中实现 GGPO 式回滚，必须绕开 UE 的网络复制系统和 CMC，完全自己管理 tick 和状态。

核心挑战：

1. **固定仿真帧率**：UE 的 `Tick` 频率不固定（帧率变化）。必须覆写 tick 流程，确保逻辑 tick 严格按固定频率执行。
2. **物理确定性**：`ChaosPhysics` 不是确定性的——浮点数、多线程物理求解、碰撞检测的任意顺序。必须用定点数物理或固定种子 + 单线程确定模式。
3. **网络层自建**：不能依赖 `UNetDriver` 或 `Iris`——需要自己处理 UDP 输入包的接收和分发。
4. **渲染/逻辑分离**：渲染帧率可以和逻辑 tick 率不同。

### 6.3 URollbackSubsystem 骨架

```cpp
// RollbackSubsystem.h
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "RollbackSubsystem.generated.h"

/// <summary>
/// UE5 GGPO 式回滚子系统。
/// 
/// 使用 UGameInstanceSubsystem 因为它的生命周期跨越整个游戏实例，
/// 不随关卡切换销毁——回滚状态需要在整个对局期间保持。
/// 
/// 关键设计决策：
/// - 逻辑 tick 独立于渲染 tick (使用 FTickableGameObject)
/// - 所有游戏状态存储为固定大小的平凡可拷贝 struct
/// - 网络层使用 FUdpSocketBuilder (绕过 UE 复制系统)
/// </summary>
UCLASS()
class URollbackSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
    GENERATED_BODY()

public:
    // --- USubsystem ---
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    // --- FTickableGameObject ---
    virtual void Tick(float DeltaTime) override;
    virtual TStatId GetStatId() const override;
    virtual bool IsTickable() const override { return bIsActive; }
    // 关键：逻辑 tick 在渲染之前运行！
    virtual bool IsTickableWhenPaused() const override { return false; }

    // --- 公开API (供游戏逻辑层调用) ---
    void SaveState(int32 Frame);
    void RestoreState(int32 Frame);
    void AddLocalInput(int32 Frame, uint16 Input);
    void OnRemoteInputReceived(int32 Frame, uint16 Input);

private:
    // --- 回滚核心参数 ---
    static constexpr int32 MAX_ROLLBACK_FRAMES = 8;
    static constexpr int32 FRAME_DELAY = 2;
    static constexpr int32 STATE_BUFFER_SIZE = 256;

    // --- 游戏状态 — 必须是固定大小、平凡可拷贝 ---
    struct FGameState
    {
        // 玩家 1 & 2 — 内联固定数组，无动态分配
        FVector2D PlayerPositions[2];  // 注意：FVector2D 用 double，
        FVector2D PlayerVelocities[2]; // 如果需确定性，替换为定点数
        int32     PlayerHP[2];
        uint8     PlayerStates[2];     // 状态机
        uint8     PlayerFacing[2];
        uint32    RNGState;
        int32     FrameNumber;

        // 投射物 (固定上限)
        static constexpr int32 MAX_PROJECTILES = 32;
        FVector2D  ProjectilePositions[MAX_PROJECTILES];
        FVector2D  ProjectileVelocities[MAX_PROJECTILES];
        uint8      ProjectileActive[MAX_PROJECTILES];
        int32      ProjectileCount;
    };
    static_assert(sizeof(FGameState) < 16384,
        "GameState exceeds 16KB — consider delta snapshots");

    // --- 输入缓冲区 ---
    struct FFrameInput
    {
        uint16 LocalInput;     // 本地玩家输入
        uint16 RemoteInput;    // 远程玩家输入 (0=尚未到达, 视为需预测)
        bool    bRemoteIsReal; // 远程输入是否为真实值 (非预测)?
    };

    // --- 状态快照槽位 ---
    struct FStateSlot
    {
        FGameState State;
        int32      Frame;
        bool       bValid;
    };

    // --- 内部缓冲区 ---
    FStateSlot StateBuffer[STATE_BUFFER_SIZE];
    FFrameInput InputBuffer[STATE_BUFFER_SIZE];
    int32 CurrentFrame = 0;

    // --- 网络 ---
    class FSocket* UdpSocket = nullptr;

    // --- 状态 ---
    FGameState CurrentState;
    bool bIsActive = false;
    int32 LastConfirmedRemoteFrame = -1;

    // --- 内部方法 ---
    void SimulateFrame(int32 Frame, uint16 LocalInput, uint16 RemoteInput);
    void CheckForRollback(int32 Frame, uint16 RealRemoteInput);
    void PerformRollback(int32 FromFrame);
    void SendLocalInput(int32 Frame, uint16 Input);
    void ReceiveRemoteInputs();

    // --- 帧定时器 (固定 60fps 逻辑) ---
    float AccumulatedTime = 0.0f;
    static constexpr float FIXED_DT = 1.0f / 60.0f;
};

// RollbackSubsystem.cpp
#include "RollbackSubsystem.h"
#include "HAL/PlatformMemory.h"
#include "Sockets.h"
#include "SocketSubsystem.h"

void URollbackSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    // 初始化状态缓冲区
    FMemory::Memzero(StateBuffer, sizeof(StateBuffer));
    FMemory::Memzero(InputBuffer, sizeof(InputBuffer));
    FMemory::Memzero(&CurrentState, sizeof(CurrentState));

    // 创建 UDP Socket
    UdpSocket = FUdpSocketBuilder(TEXT("RollbackSocket"))
        .AsNonBlocking()
        .AsReusable()
        .BoundToPort(7778)
        .Build();

    bIsActive = true;
    UE_LOG(LogTemp, Log, TEXT("[Rollback] Subsystem initialized. Fixed DT=%.4fms"), FIXED_DT * 1000.0f);
}

void URollbackSubsystem::Deinitialize()
{
    bIsActive = false;
    if (UdpSocket)
    {
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(UdpSocket);
        UdpSocket = nullptr;
    }
    Super::Deinitialize();
}

void URollbackSubsystem::Tick(float DeltaTime)
{
    // 固定频率逻辑 tick
    AccumulatedTime += DeltaTime;

    while (AccumulatedTime >= FIXED_DT && bIsActive)
    {
        AccumulatedTime -= FIXED_DT;
        int32 Frame = CurrentFrame++;

        // 1. 采样本地输入
        uint16 LocalInput = 0;  // TODO: 从 PlayerController 获取
        AddLocalInput(Frame, LocalInput);

        // 2. 接收远程输入 (非阻塞)
        ReceiveRemoteInputs();

        // 3. 获取本帧输入组合
        FFrameInput& Input = InputBuffer[Frame % STATE_BUFFER_SIZE];
        uint16 RemoteInput = Input.bRemoteIsReal ? Input.RemoteInput : 0;

        // 4. 预测远程输入 (如果尚未到达)
        if (!Input.bRemoteIsReal)
        {
            // 使用第 2 节的输入衰减预测
            // (此处简化：直接假设无操作)
            RemoteInput = 0;
        }

        // 5. 执行仿真
        SimulateFrame(Frame, LocalInput, RemoteInput);

        // 6. 保存状态快照 (用于可能回滚)
        SaveState(Frame);

        // 7. 发送本地输入
        SendLocalInput(Frame, LocalInput);
    }
}

void URollbackSubsystem::SaveState(int32 Frame)
{
    int32 SlotIdx = Frame % STATE_BUFFER_SIZE;
    FStateSlot& Slot = StateBuffer[SlotIdx];
    // 单次 memcpy — 完整的游戏状态
    FMemory::Memcpy(&Slot.State, &CurrentState, sizeof(FGameState));
    Slot.Frame = Frame;
    Slot.bValid = true;
}

void URollbackSubsystem::RestoreState(int32 Frame)
{
    int32 SlotIdx = Frame % STATE_BUFFER_SIZE;
    FStateSlot& Slot = StateBuffer[SlotIdx];
    if (!Slot.bValid || Slot.Frame != Frame)
    {
        UE_LOG(LogTemp, Error, TEXT("[Rollback] Invalid restore: frame %d"), Frame);
        return;
    }
    FMemory::Memcpy(&CurrentState, &Slot.State, sizeof(FGameState));
}

void URollbackSubsystem::AddLocalInput(int32 Frame, uint16 Input)
{
    InputBuffer[Frame % STATE_BUFFER_SIZE].LocalInput = Input;
    InputBuffer[Frame % STATE_BUFFER_SIZE].bRemoteIsReal = false;
}

void URollbackSubsystem::OnRemoteInputReceived(int32 Frame, uint16 Input)
{
    // 检查是否需要回滚
    FFrameInput& Existing = InputBuffer[Frame % STATE_BUFFER_SIZE];
    if (Existing.bRemoteIsReal && Existing.RemoteInput != Input)
    {
        // 预测错误！需要从此帧回滚
        UE_LOG(LogTemp, Warning, TEXT("[Rollback] Mispredict at frame %d! Expected=%d, Got=%d"),
            Frame, Existing.RemoteInput, Input);
        PerformRollback(Frame);
    }

    Existing.RemoteInput = Input;
    Existing.bRemoteIsReal = true;
    LastConfirmedRemoteFrame = FMath::Max(LastConfirmedRemoteFrame, Frame);
}

void URollbackSubsystem::SimulateFrame(int32 Frame, uint16 LocalInput, uint16 RemoteInput)
{
    CurrentState.FrameNumber = Frame;
    // TODO: 在此处实现游戏逻辑
    // 使用 LocalInput 和 RemoteInput 更新 CurrentState
}

void URollbackSubsystem::PerformRollback(int32 FromFrame)
{
    int32 RollbackFrames = CurrentFrame - FromFrame;
    UE_LOG(LogTemp, Warning, TEXT("[Rollback] Rolling back %d frames (from %d to %d)"),
        RollbackFrames, FromFrame, CurrentFrame - 1);

    if (RollbackFrames > MAX_ROLLBACK_FRAMES)
    {
        UE_LOG(LogTemp, Error, TEXT("[Rollback] Rollback depth %d exceeds max %d!"),
            RollbackFrames, MAX_ROLLBACK_FRAMES);
        // 回退到完整状态重置
        return;
    }

    // 加载 FromFrame 的快照
    RestoreState(FromFrame);

    // 重算从 FromFrame 到 CurrentFrame-1 的所有帧
    for (int32 f = FromFrame; f < CurrentFrame; f++)
    {
        FFrameInput& Input = InputBuffer[f % STATE_BUFFER_SIZE];
        uint16 remote = Input.bRemoteIsReal ? Input.RemoteInput : 0;
        SimulateFrame(f, Input.LocalInput, remote);
        SaveState(f);  // 更新快照为正确的值
    }
}

TStatId URollbackSubsystem::GetStatId() const
{
    RETURN_QUICK_DECLARE_CYCLE_STAT(URollbackSubsystem, STATGROUP_Tickables);
}

void URollbackSubsystem::SendLocalInput(int32 Frame, uint16 Input)
{
    // TODO: 通过 UDP socket 发送本地输入
    // 格式: [frame:4B][input:2B]
}

void URollbackSubsystem::ReceiveRemoteInputs()
{
    // TODO: 从 UDP socket 非阻塞读取远程输入包
    // 收到后调用 OnRemoteInputReceived(frame, input)
}
```

### 6.4 UE5 物理确定性的现实

这是 UE5 GGPO 回滚的**最棘手问题**。ChaosPhysics 设计时没有考虑位级确定性。如果你需要物理碰撞的确定性：

- **方案 1**：不用 ChaosPhysics。对格斗游戏而言，碰撞检测只需简单的 AABB 判定——自己写一个确定性的碰撞检测器 (500 行以内)。
- **方案 2**：用 ChaosPhysics 的确定模式。但这要求：单线程、固定子步、无异步、所有碰撞体的添加/移除顺序确定。实际可行但约束极多。
- **方案 3**：只对"不需要物理"的状态做回滚。位置、HP 等由你自己的逻辑管理——物理引擎只用于视觉特效。这是最务实的方案（也是许多商业游戏的选择）。

---

## 7. 动画启动帧设计 (Anticipation Frames for Rollback)

### 7.1 问题：回滚与动画的冲突

回滚后重新渲染时，游戏逻辑状态是正确的，但**动画状态可能不匹配**。

```
场景：P2 在帧 N 执行了"重拳"。
     客户端在帧 N+4 才收到此输入。
     回滚到 N，重新执行 N~N+4 → P2 的动画会直接从
     "待机"跳到"重拳第 4 帧"。

视觉效果：
  帧 N+2 渲染: P2 待机 ← 预测错误前的渲染
  帧 N+4 渲染: P2 重拳第 4 帧 ← 回滚后重新渲染
  玩家看到：对手突然"变招"——从待机瞬间变成出拳半程
```

这比预测位置错误更刺眼，因为动画是玩家关注的核心。

### 7.2 解决方案：动作启动帧 (Anticipation / Startup Frames)

这是格斗游戏中一个**古老的设计模式**，早在回滚网络出现之前就存在——但它恰好**完美适配了回滚网络的需求**。

```
传统格斗游戏的动作帧划分：
┌─────────┬──────────┬───────────┐
│  Startup │  Active   │ Recovery  │
│  (启动帧) │ (判定帧)  │ (收招帧)  │
├─────────┼──────────┼───────────┤
│ 3 帧     │ 3 帧      │ 3 帧      │
│ 出招动作  │ 攻击判定   │ 收回动作   │
│ 无攻击判定 │ 可命中对手 │ 有硬直    │
└─────────┴──────────┴───────────┘

回滚感知的关键设计：
  远程玩家 → 启动帧可以跳过！因为远程玩家实际早已按下按钮
  本地玩家 → 启动帧正常播放，保证手感流畅
```

关键洞察：当远程对手的动作因为回滚而"延迟到达"时，**跳过启动帧直接进入攻击判定帧**。对于观看者（本地玩家）而言，对手"起手很快"——这在格斗游戏中完全合理——高手本来就起手快。这比"对手瞬间中拳"好一万倍。

### 7.3 实现

```csharp
using System;
using System.Collections.Generic;

/// <summary>
/// 回滚感知的动画状态机。
/// 
/// 关键设计：
/// - 每个动作有 startup/active/recovery 三段
/// - 回滚时，根据"动作实际已经执行了多少帧"跳过 startup
/// - 本地玩家的 startup 永远完整播放 (不跳过)
/// </summary>
public class RollbackAwareAnimationController
{
    public struct AnimationAction
    {
        public string name;
        public int startupFrames;   // 启动帧数 (无攻击判定)
        public int activeFrames;    // 判定帧数 (有攻击判定)
        public int recoveryFrames;  // 收招帧数
        public int totalFrames => startupFrames + activeFrames + recoveryFrames;
    }

    // 动作库
    Dictionary<int, AnimationAction> actions = new();

    // 当前动画状态
    int currentActionId;         // 当前动作 ID
    int currentFrameInAction;    // 当前在动作中的第几帧 (0-indexed)
    int actionStartedOnFrame;    // 动作开始的逻辑帧号

    // 回滚跳过模式
    bool isLocalPlayer;  // 本地玩家不跳帧

    public RollbackAwareAnimationController(bool isLocal)
    {
        isLocalPlayer = isLocal;

        // 注册动作 (示例)
        actions[0] = new AnimationAction { name = "Idle",   startupFrames = 0, activeFrames = 0, recoveryFrames = 0 };
        actions[1] = new AnimationAction { name = "Jab",    startupFrames = 2, activeFrames = 2, recoveryFrames = 3 };
        actions[2] = new AnimationAction { name = "Heavy",  startupFrames = 5, activeFrames = 3, recoveryFrames = 6 };
        actions[3] = new AnimationAction { name = "Special",startupFrames = 8, activeFrames = 4, recoveryFrames = 10 };
    }

    /// <summary>
    /// 开始一个新动作。
    /// </summary>
    public void StartAction(int actionId, int currentLogicFrame)
    {
        currentActionId = actionId;
        currentFrameInAction = 0;
        actionStartedOnFrame = currentLogicFrame;
    }

    /// <summary>
    /// 回滚发生时，快进动画到正确的帧。
    /// 
    /// 这是因为动作实际已经执行了 `elapsedFrames` 帧——
    /// 我们不需要从头播放 startup，可以直接跳到当前应该
    /// 在的位置。对于远程玩家，startup 可以跳过。
    /// </summary>
    public void FastForwardOnRollback(int actionId, int actionStartedFrame, int currentLogicFrame)
    {
        int elapsed = currentLogicFrame - actionStartedFrame;
        var action = actions[actionId];

        if (isLocalPlayer)
        {
            // 本地玩家：不跳过 startup，但快进到正确帧
            // （本地玩家的输入是即时的，理论上不需要处理，但
            //  如果发生了某种回滚，至少保持一致）
            currentActionId = actionId;
            actionStartedOnFrame = actionStartedFrame;
            currentFrameInAction = Math.Min(elapsed, action.totalFrames - 1);

            if (elapsed >= action.totalFrames)
            {
                // 动作已完成，回到 Idle
                currentActionId = 0;
                currentFrameInAction = 0;
            }
        }
        else
        {
            // 远程玩家：可以跳过 startup
            if (elapsed <= action.startupFrames)
            {
                // 仍在 startup 阶段 → 直接跳到 startup 末尾
                currentActionId = actionId;
                currentFrameInAction = elapsed;
                // 正常播放完剩余的 startup
            }
            else
            {
                // 已经过了 startup → 从 active 或 recovery 阶段开始
                int pastStartup = elapsed - action.startupFrames;
                currentActionId = actionId;
                actionStartedOnFrame = actionStartedFrame;

                if (pastStartup < action.activeFrames + action.recoveryFrames)
                {
                    // 在 active 或 recovery 中
                    currentFrameInAction = action.startupFrames + pastStartup;
                }
                else
                {
                    // 已完成 → 回到 Idle
                    currentActionId = 0;
                    currentFrameInAction = 0;
                }
            }
        }
    }

    /// <summary>
    /// 每帧更新 (正常流程，非回滚)。
    /// </summary>
    public void Update(int currentLogicFrame)
    {
        currentFrameInAction++;
        var action = actions[currentActionId];

        if (currentFrameInAction >= action.totalFrames)
        {
            // 动作结束 → 回到 Idle
            currentActionId = 0;
            currentFrameInAction = 0;
            actionStartedOnFrame = currentLogicFrame;
        }
    }

    /// <summary>
    /// 获取当前应播放的动画帧索引 (用于渲染)。
    /// </summary>
    public (string actionName, int frameIndex, bool hasHitbox) GetCurrentRenderState()
    {
        var action = actions[currentActionId];
        bool hasHitbox = currentFrameInAction >= action.startupFrames
                      && currentFrameInAction < action.startupFrames + action.activeFrames;

        return (action.name, currentFrameInAction, hasHitbox);
    }
}
```

### 7.4 动作帧状态机图

```
                ┌──────────────────────────────────────────┐
                │           按键输入 (Punch)                │
                │  ┌─────────────────────────────────────┐ │
                │  │                                     ▼ ▼
┌──────┐  按键  ┌──────────┐  startup结束  ┌──────────┐  active结束  ┌───────────┐  recovery结束  ┌──────┐
│ Idle │──────→│ Startup  │──────────────→│  Active  │─────────────→│ Recovery  │───────────────→│ Idle │
│      │       │ (0~N帧)  │               │ (判定帧)  │              │ (收招帧)   │                │      │
└──────┘       └──────────┘               └──────────┘              └───────────┘                └──────┘
                      │                         │                          │
                      │ (远程玩家回滚时)          │                          │
                      │ 跳过这些帧               │                          │
                      └─────────────────────────┴──────────────────────────┘
                                    远程玩家实际看到的起始帧
```

### 7.5 更复杂的技巧：Hitstop 与回滚

Hitstop（击中停顿）是格斗游戏的另一个经典设计——攻击命中时，双方画面暂停 2~10 帧。

**与回滚的交互**：
- 回滚重算时，如果发现之前渲染的帧有 Hitstop，而重新计算后没有（或反之），画面会出现"卡顿"感
- **解决方案**：Hitstop 被视为逻辑状态的一部分（保存在快照中），回滚后会正确重放

```csharp
// 在 GameState 中包含 hitstop
public struct GameState {
    // ...
    public int hitstopRemaining;  // 剩余停顿帧数
    // 保存/恢复时一并处理
}
```

---

## 8. P2P vs 服务端回滚架构

### 8.1 P2P 回滚 (GGPO 默认模型)

```
┌─────────────────────────────────────────────────────────────┐
│                     P2P Rollback 架构                        │
│                                                              │
│   ┌──────────┐                          ┌──────────┐        │
│   │ Client A │ ←── UDP (直接连接) ──→  │ Client B │        │
│   │          │                          │          │        │
│   │ 跑全量逻辑 │                          │ 跑全量逻辑 │        │
│   │ 预测 B 输入│                          │ 预测 A 输入│        │
│   │ 保存状态   │                          │ 保存状态   │        │
│   │ 发送输入   │                          │ 发送输入   │        │
│   └──────────┘                          └──────────┘        │
│                                                              │
│   优点: 最低延迟 (无中间节点), 简单                           │
│   缺点: 无权威方 (纠纷无法仲裁), 最多 2 人                    │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 服务端回滚 (Mortal Kombat / NRS 模型)

```
┌─────────────────────────────────────────────────────────────┐
│                    Server-Based Rollback                     │
│                                                              │
│   ┌──────────┐         ┌──────────────┐        ┌──────────┐ │
│   │ Client A │ ←──UDP→ │   Server     │←─UDP─→ │ Client B │ │
│   │          │         │              │        │          │ │
│   │ 发输入给   │         │ 收集所有输入   │        │ 发输入给   │ │
│   │ 服务器     │         │ 按时序广播     │        │ 服务器     │ │
│   │          │         │ 防作弊验证     │        │          │ │
│   │ 接收广播   │         │ (跑逻辑验证)  │        │ 接收广播   │ │
│   │ 预测执行   │         └──────────────┘        │ 预测执行   │ │
│   └──────────┘                                   └──────────┘ │
│                                                              │
│   优点: 有权威方 (防作弊), 可 >2 人                            │
│   缺点: +半程 RTT 延迟 (客户端→服务器)                          │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 混合架构 (推荐)

```
┌─────────────────────────────────────────────────────────────┐
│                    Hybrid Rollback                           │
│                                                              │
│   ┌──────────┐         ┌──────────────┐        ┌──────────┐ │
│   │ Client A │ ←──UDP→ │   Server     │←─UDP─→ │ Client B │ │
│   │          │  (输入)  │              │ (广播) │          │ │
│   │          │         │              │        │          │ │
│   │ 本地预测   │         │ • 转发所有输入  │        │ 本地预测   │ │
│   │ P2P 回滚   │←─P2P──→│ • 周期性验证    │←─P2P──→│ P2P 回滚   │ │
│   │ (对 B)    │  (低延迟)│ • 反作弊审计    │ (低延迟)│ (对 A)    │ │
│   └──────────┘         └──────────────┘        └──────────┘ │
│                                                              │
│   客户端之间: P2P 回滚 (低延迟)                                │
│   客户端↔服务器: 输入中继 + 周期性 Hash 验证 (防作弊)          │
└─────────────────────────────────────────────────────────────┘
```

### 8.4 架构选择速查

| 需求 | 推荐架构 | 理由 |
|------|---------|------|
| 1v1 格斗，好友对战 | P2P | 最低延迟，不需要反作弊 |
| 1v1 格斗，匹配竞技 | 服务端回滚 | 防作弊 + 公平性 |
| 2~4 人合作动作 | 混合 | P2P 回滚 (低延迟) + 服务器验证 |
| >4 人对战 | 不建议纯回滚 | 回滚深度太大，改用插值/预测混合 |

---

## 9. 练习

### 练习 1：基础 — 实现输入衰减并对比视觉效果 (30min)

**目标**：理解输入衰减对回滚视觉质量的影响。

**步骤**：
1. 使用教程 12 练习 2 的简化格斗游戏框架（或你自己的回滚实现），在其中集成第 2 节的 `InputDecayPredictor`。
2. 在 100ms 模拟网络延迟下，录制一段 10 秒的对战（双方频繁移动/攻击）。
3. 分别在以下三种模式下运行同一段输入序列：
   - 模式 A：无衰减（全强度预测）
   - 模式 B：线性衰减（100%→66%→33%→0%）
   - 模式 C：无操作预测（GGPO 原始默认）
4. 对比三种模式的视觉质量：
   - 统计回滚发生时，角色位置误差（像素）
   - 主观评分（1-5）——画面"撕裂感"程度
5. **提交**：三种模式的误差对比表格 + 一段截图说明。

### 练习 2：进阶 — 性能分析 (45min)

**目标**：测量你的游戏能承受多少回滚帧。

**步骤**：
1. 集成第 3 节的 `PerformanceBudgetCalculator`。
2. 在不同回滚深度下（1/2/4/6/8/10 帧），测量以下指标：
   - 单帧仿真的平均耗时 (`avgSimTimeMs`)
   - 总预算 (`avgSimTimeMs × depth`)
   - 帧率是否下降
3. 找到你的游戏的"回滚上限"——超过此深度后帧率跌到 50fps 以下。
4. 如果上限 < 6 帧，尝试优化仿真代码（减少分配、使用结构体、避免虚函数）。
5. **提交**：性能报告表格 + 优化前后的对比。

### 练习 3：挑战 — 实现服务端回滚架构 (90min)

**目标**：将 P2P 回滚改造为服务端回滚架构。

**步骤**：
1. 实现一个简单的 UDP 服务器，它：
   - 接收两个客户端的输入包 (每帧)
   - 按帧号排序后，广播给两个客户端
   - 周期性接收客户端的 Hash 报告
2. 修改客户端：
   - 不再直接 P2P 发送输入——发送给服务器
   - 从服务器接收广播输入（而不是直接从对手）
   - 使用接收到的输入（可能有 30~50ms 额外延迟）进行回滚预测
3. 测量并对比：
   - P2P 模式的总延迟 (输入→对端看到)
   - 服务端模式的总延迟
4. **提交**：延迟对比图 + 架构图。

---

## 10. 常见陷阱

### 陷阱 1：忘记保存 RNG 状态

回滚重算时，如果 RNG 状态没有被保存/恢复，会产生不同的随机数——导致重算结果与原始执行不同。**这是最常见的回滚 Desync 原因。**

```csharp
// ❌ 错误：RNG 是全局单例，回滚时不会重置
int damage = Random.Range(10, 20);

// ✅ 正确：RNG 状态在 GameState 中，随快照一起保存/恢复
[Serializable]
public struct GameState {
    public uint rngState;  // 必须在快照内!
}
int damage = DeterministicRandom.Range(10, 20, ref state.rngState);
```

### 陷阱 2：未处理音频效果

回滚重算时，如果游戏逻辑触发了音频播放（如 `AudioSource.Play()`），回滚期间可能会导致：
- 相同的音效被播放两次（首算 + 重算）
- 音效在回滚后被错误地"取消"

**解决方案**：使用逻辑/表现的分离模式——逻辑层只记录"发生了音效事件"，渲染层在确认帧不会再被回滚后才真正播放。

```csharp
// 逻辑层：只记录事件
state.pendingAudioEvents.Add(new AudioEvent { type = SoundType.Hit, frame = currentFrame });

// 渲染层：只播放"已确认"的帧的音效
void PlayConfirmedAudio(int confirmedFrame) {
    var events = state.GetAudioEventsUpTo(confirmedFrame);
    foreach (var e in events) {
        if (!e.played) {
            AudioManager.Play(e.type);
            e.played = true;
        }
    }
}
```

### 陷阱 3：粒子系统 / VFX 状态丢失

粒子系统维护着大量 GPU 端状态——发射器位置、生命周期、随机种子。这些**不应**（也通常无法）保存在游戏状态快照中。

**正确做法**：将粒子系统完全视为"渲染层"的职责。回滚期间，渲染层应该：
1. 停止所有正在播放的粒子
2. 根据回滚后的逻辑状态重新触发粒子（如受击火花、技能特效）
3. 接受"粒子可能重放"——这比粒子消失好

### 陷阱 4：未初始化的内存

`memcpy` 保存整个 struct 时，struct 中的 **padding bytes** 可能包含随机值。如果这些 padding 在游戏逻辑中被误用（如 `memcmp` 比较两个状态），会导致不确定行为。

```cpp
// ❌ 危险：padding 可能包含随机值
struct GameState {
    int32_t hp;       // 4 bytes
    uint8_t flags;    // 1 byte
    // [3 bytes padding — 随机值!]
    int32_t x;        // 4 bytes
};

// ✅ 安全：显式填充
struct GameState {
    int32_t hp;
    uint8_t flags;
    uint8_t _padding[3] = {0, 0, 0};  // 显式控制 padding
    int32_t x;
};
```

### 陷阱 5：时间步长不匹配

固定时间步长 (Fixed Timestep) 是回滚的前提条件。如果某次仿真使用 `deltaTime=16.0ms` 而回滚后使用 `deltaTime=17.0ms`，位置会产生微小偏差，累积后导致 Desync。

**解决方案**：始终使用**完全相同的固定 dt**，存储在状态中。

```csharp
// 回滚系统必须使用恒定 deltaTime
const float FIXED_DT = 1f / 60f;  // 16.666ms，永远不变

// ❌ 错误
state.Update(Time.deltaTime);  // 变长!

// ✅ 正确
state.Update(FIXED_DT);  // 永远不变
```

### 陷阱 6：动画状态漂移

回滚时，动画系统可能处于一个"与逻辑状态不一致"的中间状态。第 7 节已经详细讨论了解决方案（启动帧设计 + 快进机制），但要特别注意一个常见 bug：

```csharp
// ❌ 错误：Animator 是外部状态，回滚时不会被重置
animator.SetTrigger("Punch");  // 回滚重算时可能触发两次

// ✅ 正确：动画状态由逻辑层驱动，每帧设为绝对状态
animator.Play("Punch", layer: 0, normalizedTime: actionFrame / totalFrames);
```

### 陷阱 7：性能死亡螺旋

已在第 3 节详细讨论。核心要点：**始终监控回滚深度，设置硬性上限**。不相信"我们的仿真很快，不会超时"——网络条件千变万化，200ms RTT 在移动网络上是常态。

```csharp
// 每帧检查
if (rollbackDepth > MAX_ROLLBACK_FRAMES) {
    // 拒绝回滚，用服务器权威状态重置
    ResetToServerState();
    return;
}
```

### 陷阱 8：认为回滚只适合格斗游戏

教程 12 的陷阱 6 已讨论过此问题。补充一个工程视角：**回滚是一种延迟隐藏技术，可以裁剪应用到任何需要低频度远端输入的场景**。例如：
- FPS：只对"被击中"的视觉反馈做微回滚（< 2 帧）
- MOBA：对自己释放的技能做预测执行，对敌方技能用插值
- RTS：对"单位攻击指令"做预测，对"建造/升级"使用锁步确认

关键在于识别**哪些事件对延迟敏感**，而后只对这些事件使用回滚——而不是对整个游戏做全量 GGPO。

---

## 11. 扩展阅读

### 必读演讲
- **Jared Cone, _Rocket League's Physics Rollback_, GDC 2018** — 输入衰减技术的来源，详细讲解了 RL 如何在高动态物理游戏中实现回滚
- **Michael Stallone, _8 Frames in 16ms: Rollback Networking in Mortal Kombat and Injustice 2_, GDC 2019** — 服务端回滚的实战经验，NetherRealm 如何从 P2P 迁移到服务端模型
- **Tony Cannon, _GGPO: The Community Effects of Rollback_, GDC 2018** — GGPO 对格斗游戏社区的影响

### 论文
- **J. Greer, _Deterministic Simulation for Networked Games_** — 确定性仿真的理论基础
- **S. Fiedler, _Input Prediction in Peer-to-Peer Fighting Games_** — 输入预测策略的量化分析

### 开源参考
- **GGPO SDK**: https://github.com/pond3r/ggpo
- **GGRS**: https://github.com/gschup/ggrs
- **backroll-rs**: https://github.com/HouraiTeahouse/backroll-rs
- **Corrade/netcode-rollback**: https://github.com/Corrade/netcode-rollback

### 深度文章
- **Fight the Latency!**: https://ki.infil.net/w02-netcode.html — 格斗游戏网络代码的终极指南
- **Why GGPO is harder in UE5**: https://forums.unrealengine.com/ — UE 社区的讨论帖，解释 UE 引擎设计对回滚网络的不友好之处

---

> **本章总结**：回滚网络不是"实现一个 `memcpy` + `Save/Load` 就能收工"的技术。生产级回滚需要处理输入衰减（视觉质量）、性能预算（防止死亡螺旋）、状态优化（内存与速度的平衡）、动画修复（动作帧设计）、架构选择（P2P vs 服务端）以及一系列隐蔽的确定性陷阱。掌握这些后，你的回滚系统才能从"玩具级"进入"可上线级"。
