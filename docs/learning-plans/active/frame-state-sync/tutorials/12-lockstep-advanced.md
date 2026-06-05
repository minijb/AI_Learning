---
title: "帧同步进阶：快照校验、预测回滚与反外挂"
updated: 2026-06-05
---

# 帧同步进阶：快照校验、预测回滚与反外挂

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 90-120min
> 前置知识: [[11-lockstep-server-design|11-帧同步服务端设计：帧对齐与乐观帧锁定]]

---

## 1. 概念讲解

### 1.1 为什么需要进阶话题？

学完前 11 节，你已经可以搭建一个基础的帧同步对战系统：客户端发送输入 → 服务器汇集广播 → 所有客户端按帧执行。但"能跑"离"能上线"之间还隔着一条巨大的鸿沟。

这些是上线后迟早会撞到的真实问题：

- **"A 说自己打死了 B，B 说自己逃掉了"**——Desync 要不要检测？怎么检测？检测到之后能做什么？
- **"格斗游戏输入延迟 6 帧根本没法玩"**——能不能既给快玩家即时反馈，又保持一致性？
- **"有人开了全图挂把所有敌人位置都显示出来了"**——帧同步本地有全量状态，反外挂怎么搞？
- **"一场 30 分钟的对局，录像文件只占 200KB"**——帧同步特有的 Replay 魔术是怎么做的？
- **"线上 desync 了，本地复现不了"**——怎么调试一个不确定复现的同步 bug？

这 5 个问题对应本教程的 5 个章节。每一项都是面试高频题。

### 1.2 核心思想地图

```
┌──────────────────────────────────────────────────────────────────────┐
│                      帧同步进阶体系                                   │
├───────────────┬──────────────────┬─────────────────┬─────────────────┤
│   快照校验     │    预测回滚       │    反外挂        │   录像 & 调试    │
│   (防 Desync) │   (降输入延迟)    │   (防作弊)       │   (可观测性)     │
├───────────────┼──────────────────┼─────────────────┼─────────────────┤
│ • 全量 Hash   │ • GGPO 原理      │ • 全图挂         │ • 指令序列录像   │
│ • 增量校验    │ • 输入预测       │ • 自瞄/数值修改   │ • 帧日志         │
│ • Desync 检测 │ • 误预测回滚     │ • 服务端重跑比对  │ • Diff 工具      │
│ • 回放诊断    │ • SyncTest 验证  │ • 代码混淆       │ • 回放定位       │
│               │ • 帧延迟调优     │                  │                 │
│               │ • 确定性陷阱     │                  │                 │
└───────────────┴──────────────────┴─────────────────┴─────────────────┘
```

---

## 2. 快照校验 (Snapshot Verification)

### 2.1 问题的根源

帧同步的致命弱点：**服务器不跑逻辑，无法天然验证客户端是否正确**。

在状态同步中，服务器是权威——客户端说什么服务器可以不听。但在帧同步中，服务器只是"哑转发"，不执行游戏逻辑。这意味着：如果两个客户端产生了不同的游戏状态，**没有人能判断谁对谁错**。

更糟的是，这两个客户端都"相信自己是对的"。它们在各自的"平行宇宙"里继续运行，直到某一刻彻底无法交互——第 1000 帧时，客户端 A 认为英雄在 (500, 200) 放技能打中了敌人，客户端 B 认为英雄在 (300, 400)，AI 兵在完全不同位置……两个世界已经面目全非。

这就是 **Desync（不同步）**。

### 2.2 快照 Hash 的基本原理

快照校验的核心思想：**不验证整个状态，只验证状态的"指纹"**。

每一帧结束后，客户端计算当前游戏状态 S_n 的一个 Hash（校验和），上报给服务器。服务器比对所有客户端的 Hash：

```
客户端A: S_n → Hash_A = 0x8B2C_F1A3
客户端B: S_n → Hash_B = 0x8B2C_F1A3  ← 一致
客户端C: S_n → Hash_C = 0x67D0_3E91  ← 不一致！Desync！
```

Hash 一致 → 逻辑结果一致（极高的概率保证）。Hash 不一致 → Desync 发生。

### 2.3 Hash 算法选择

#### CRC32

```csharp
// 优点：极快（硬件加速），4 字节输出
// 缺点：碰撞概率高（32-bit 只有 43 亿种可能）
// 适用：低安全要求场景，每帧都比对时可用
uint crc = Crc32.Compute(stateBytes);
```

**CRC32 vs MD5 对比**：

| 算法 | 输出长度 | 速度 | 碰撞概率（1000万帧） | 适用 |
|------|---------|------|---------------------|------|
| CRC32 | 4 bytes | ~10 GB/s | ~0.001% | 高频校验（每帧） |
| MD5 | 16 bytes | ~0.5 GB/s | 可忽略 | 阶段性校验（每30帧） |
| SHA-256 | 32 bytes | ~0.2 GB/s | 可忽略 | 反外挂/审计 |

**推荐策略——分层校验**：

```
每帧：    CRC32  (计算快，用于快速发现)
每10帧：  MD5    (碰撞低，用于确认)
每300帧： SHA-256 (防篡改，用于审计留底)
```

#### MD5 实现示例

```csharp
using System.Security.Cryptography;
using System.Text;

public static class SnapshotHash
{
    // 计算游戏状态的 MD5
    public static string ComputeMD5(GameState state)
    {
        using var md5 = MD5.Create();
        byte[] data = SerializeStateForHash(state);
        byte[] hash = md5.ComputeHash(data);
        return BitConverter.ToString(hash).Replace("-", "");
    }

    // 只序列化逻辑相关字段（确定的字节序！）
    static byte[] SerializeStateForHash(GameState state)
    {
        using var ms = new MemoryStream();
        using var writer = new BinaryWriter(ms);

        // 关键：按确定的顺序写入，避免遍历容器的非确定性
        // 先收集所有 EntityID 排序
        var sortedIds = state.Entities.Keys.OrderBy(id => id);

        foreach (var id in sortedIds)
        {
            var entity = state.Entities[id];
            writer.Write(id);                    // EntityID
            writer.Write(entity.PosX.RawValue);  // 定点数原始值
            writer.Write(entity.PosY.RawValue);
            writer.Write(entity.HP);
            writer.Write(entity.Facing);         // 朝向（整数值）
            // 注意：不写渲染相关字段（动画帧、插值状态等）
        }

        return ms.ToArray();
    }
}
```

**关键细节——序列化顺序的确定性**：

Hash 计算的结果取决于两个因素：
1. 游戏状态的实际值
2. 值被序列化时的**顺序**

很多 desync 不是逻辑真的不一致，而是 **Hash 计算时遍历容器的顺序不一致**。这比逻辑 desync 更隐蔽——游戏实际上是一致的，但 Hash 不同，导致误报。

防范措施已在教程 06 详细讨论，核心原则是：**在计算 Hash 前，显式排序所有实体的遍历顺序**。

### 2.4 全量校验 vs 增量校验

#### 全量校验（Full State Hash）

每帧对所有实体状态计算 Hash：

```csharp
// 优点：完整覆盖，不会漏检
// 缺点：计算量大，尤其实体数多时
public class FullStateVerifier
{
    public bool Verify(GameState stateA, GameState stateB, uint frameNumber)
    {
        string hashA = SnapshotHash.ComputeMD5(stateA);
        string hashB = SnapshotHash.ComputeMD5(stateB);

        if (hashA != hashB)
        {
            LogDesync(frameNumber, hashA, hashB);
            return false;
        }
        return true;
    }
}
```

在王者荣耀中，一局 10 人对战可能涉及上万个实体（防御塔、小兵、野怪、子弹、技能特效逻辑实体……）。全量 Hash 每帧都做的话，计算量不可忽视。

#### 增量校验（Incremental Verification）

只校验"关键状态"的变化量：

```csharp
public struct IncrementalCheckpoint
{
    public uint frameNumber;
    public int player0HP;
    public int player1HP;
    public long player0X, player0Y;
    public long player1X, player1Y;
    public int livingEntityCount;
    // 只包含"改变即影响游戏结果"的字段
}

public class IncrementalVerifier
{
    // 每 N 帧（如每 10 帧）计算一个增量快照
    const int CHECKPOINT_INTERVAL = 10;

    Dictionary<uint, IncrementalCheckpoint> checkpoints = new();

    public void RecordCheckpoint(uint frame, GameState state)
    {
        if (frame % CHECKPOINT_INTERVAL == 0)
        {
            checkpoints[frame] = new IncrementalCheckpoint
            {
                frameNumber = frame,
                player0HP = state.GetPlayer(0).HP,
                player1HP = state.GetPlayer(1).HP,
                player0X = state.GetPlayer(0).PosX.RawValue,
                player0Y = state.GetPlayer(0).PosY.RawValue,
                player1X = state.GetPlayer(1).PosX.RawValue,
                player1Y = state.GetPlayer(1).PosY.RawValue,
                livingEntityCount = state.GetLivingEntityCount(),
            };
        }
    }

    public bool CompareCheckpoint(uint frame, IncrementalCheckpoint other)
    {
        if (!checkpoints.TryGetValue(frame, out var mine))
            return true; // 没有记录就算了

        return mine.player0HP == other.player0HP
            && mine.player1HP == other.player1HP
            && mine.player0X == other.player0X
            && mine.player0Y == other.player0Y
            && mine.player1X == other.player1X
            && mine.player1Y == other.player1Y
            && mine.livingEntityCount == other.livingEntityCount;
    }
}
```

**策略选择指南**：

| 策略 | 覆盖范围 | CPU 开销 | 网络开销 | 推荐场景 |
|------|---------|---------|---------|---------|
| 全量 CRC32 每帧 | 完整 | 中 | ~4B/帧 | 实体数 <500 |
| 全量 MD5 每30帧 | 完整 | 低 | ~16B/30帧 | 通用推荐 |
| 增量关键字段每帧 | 有限 | 很低 | 极小 | 移动端、大型对局 |
| 混合：CRC32 每帧 + MD5 每50帧 | 完整 | 中低 | 很小 | 生产环境首选 |

### 2.5 Desync 检测与诊断流程

当 Hash 不一致时，需要快速定位问题：

```
检测到 Desync
    │
    ├─ 1. 立即记录当前帧号 + 双方的 Hash 值
    │
    ├─ 2. 双方各自保存"快照 + 输入历史"到本地文件
    │     (快照 = 最近一次验证通过的完整状态)
    │     (输入历史 = 从快照帧到 desync 帧的所有输入)
    │
    ├─ 3. 服务器尝试"重放诊断"
    │     从最近一次一致帧开始，用服务器记录的输入序列
    │     逐步重放到 desync 帧，观察哪一帧出现了分歧
    │
    └─ 4. 标记该帧为 desync 帧，通知客户端回滚或踢出
```

```csharp
public class DesyncDetector
{
    // 保存最近一次验证通过的完整快照
    GameState lastGoodSnapshot;
    uint lastGoodFrame;

    // 循环缓冲区：保存最近 N 帧的输入
    const int INPUT_HISTORY_SIZE = 600; // 10秒 @ 60fps
    Queue<FrameInput[]> inputHistory = new(INPUT_HISTORY_SIZE);

    public void OnFrameComplete(uint frame, GameState state, string localHash)
    {
        // 存储输入历史
        inputHistory.Enqueue(state.LastFrameInputs);
        while (inputHistory.Count > INPUT_HISTORY_SIZE)
            inputHistory.Dequeue();

        // 每 30 帧发送 Hash 给服务器校验
        if (frame % 30 == 0)
        {
            string hash = SnapshotHash.ComputeMD5(state);
            SendToServer(new HashReport { frame = frame, hash = hash });

            // 更新快照（用于 Desync 后的回滚重放）
            lastGoodSnapshot = state.DeepClone();
            lastGoodFrame = frame;
        }
    }

    // 服务器通知 Desync
    public void OnDesyncDetected(uint desyncFrame)
    {
        Debug.LogError($"[DESYNC] Frame {desyncFrame}! Last good: {lastGoodFrame}");

        // 保存诊断数据到本地文件
        SaveDiagnosticData(desyncFrame);

        // 尝试从 lastGoodFrame 回滚
        RollbackToFrame(lastGoodFrame, desyncFrame);
    }

    void SaveDiagnosticData(uint desyncFrame)
    {
        var report = new DesyncReport
        {
            desyncFrame = desyncFrame,
            lastGoodFrame = lastGoodFrame,
            snapshot = lastGoodSnapshot,
            inputs = inputHistory.ToArray(),
            timestamp = DateTime.UtcNow,
        };
        string json = JsonUtility.ToJson(report);
        string path = $"desync_report_{desyncFrame}_{DateTime.UtcNow.Ticks}.json";
        File.WriteAllText(path, json);
    }

    void RollbackToFrame(uint fromFrame, uint toFrame)
    {
        // 从 lastGoodSnapshot 开始，重新执行 fromFrame 到 toFrame 的逻辑
        var state = lastGoodSnapshot.DeepClone();
        for (uint f = fromFrame + 1; f <= toFrame; f++)
        {
            state.ExecuteFrame(f, /* 使用服务器下发的输入 */);
        }
        // 现在 state 应该是"正确"的状态
    }
}
```

---

## 3. 预测回滚 (Predictive Rollback)

### 3.1 问题的根源——帧同步的输入延迟

标准帧同步的输入延迟模型：

```
玩家按下按钮
    │
    ▼
客户端缓存输入 [延迟 0]
    │
    ▼
发送给服务器 ────[网络延迟 30ms]───→ 服务器收集
                                        │
                                        ▼
                                  广播给所有客户端
                                        │
                              ──[网络延迟 30ms]──
                              │
                              ▼
                        所有客户端执行
                              │
                              ▼
                         画面显示结果
                              │
                 总延迟: 0 + 30 + 30 = 60ms  (最优情况)
                 如果网络抖动: 可能 100~200ms
```

对于 MOBA/RTS，60~100ms 的输入延迟在可接受范围内——操作频率低，玩家难以感知。

但对于 **格斗游戏**（Street Fighter、Guilty Gear），60ms 延迟已经严重影响体验——输入时机精确到 1~2 帧（16~33ms），延迟导致"按了但没出招"。

### 3.2 GGPO / Rollback Netcode 原理

GGPO（Good Game Peace Out）是由 Tony Cannon 发明的网络同步方案，专门解决 P2P 格斗游戏的延迟问题。其核心思想在 2019 年被 Cannon 兄弟以 MIT 协议开源。

**核心理念——用 CPU 换延迟**：

```
传统 Lockstep:
  等所有人的输入 → 执行 → 显示  (延迟 = 最慢玩家 RTT)

GGPO:
  不等！用预测的输入先执行 → 显示 (延迟 = 0)
  等网络输入到达 → 对比预测 → 如果预测错了 → 回滚重算
```

**工作流程（以两玩家 P2P 为例）**：

```
时间轴: ──[Frame N-2]──[Frame N-1]──[Frame N]──[Frame N+1]──→

1. 本地玩家按了"轻拳" → 立即作为 Frame N 的输入
2. 远程玩家的 Frame N 输入还在路上（网络延迟）
3. GGPO 不等待！假设远程玩家"无操作"，先用本地真实输入 + 远程预测输入执行 Frame N
4. 显示 Frame N 的画面（玩家看到即时反馈）
5. 3 帧后，远程玩家的 Frame N 真实输入到达
6. 对比：远程玩家实际按了"重拳"，不是"无操作"
7. 回滚！从 Frame N 开始重新计算，带上正确的远程输入
8. 一直快进算到当前帧
```

**关键约束**：
1. **每次逻辑帧的执行开销必须极低**——因为要快速"追赶"回当前帧
2. **回滚必须不可见**——重算期间不能渲染中间帧，只能"闪现"最终结果
3. **游戏状态的可快照性**——必须在任意帧保存和恢复完整状态

### 3.3 适用场景分析

| 游戏类型 | 是否适用 GGPO | 原因 |
|---------|-------------|------|
| 格斗游戏（1v1，P2P） | **最佳** | 玩家少，回滚概率低，状态简单 |
| 动作游戏（2~4人 PvE） | **适用** | 状态可能复杂，但玩家数少 |
| MOBA（10人） | **不适用** | 玩家太多 → 每人都在预测其他人 → 误预测概率极高 → 一直在回滚 |
| RTS（1000+ 单位） | **不适用** | 状态量巨大，快照/恢复成本不可接受 |
| FPS（高 tickrate） | **不适用** | 状态同步 + 延迟补偿更合适 |

**现实中的 GGPO 应用**：
- Street Fighter V (Rollback + GGPO)
- Guilty Gear Strive
- Skullgirls（首个商用 GGPO 游戏）
- Killer Instinct (2013)（Xbox One）
- Mortal Kombat 11

### 3.4 C# GGPO 风格回滚框架（简化版）

```csharp
using System;
using System.Collections.Generic;

/// <summary>
/// GGPO 风格的预测回滚管理器（简化版，适用于 1v1 P2P）
/// 
/// 核心数据结构：
/// - inputBuffer: 环缓冲区，存储每帧的输入（含本地 + 远程）
/// - stateBuffer: 环缓冲区，存储每帧的游戏状态快照
/// - 帧号基于同步时钟递增
/// </summary>
public class RollbackManager
{
    const int MAX_ROLLBACK_FRAMES = 8;  // 最多回滚 8 帧（格斗游戏典型值）
    const int FRAME_DELAY = 2;          // 人为增加 2 帧延迟作为网络缓冲

    // 环缓冲区：帧号 → 输入
    FrameInput[] inputBuffer = new FrameInput[256];
    // 环缓冲区：帧号 → 游戏状态快照（Deep Clone）
    byte[][] stateBuffer = new byte[256][];
    // 当前"已确认"的帧号（远程输入全部到达的最远帧）
    uint confirmedFrame;

    // 事件：帧推进
    public delegate void AdvanceFrameCallback(FrameInput input);
    public AdvanceFrameCallback OnAdvanceFrame;

    // 事件：需要从网络获取远程输入
    public delegate void RequestRemoteInputCallback(uint frame);
    public RequestRemoteInputCallback OnRequestRemoteInput;

    /// <summary>
    /// 设置本地玩家本帧的输入
    /// 调用时机：每一帧开始前，由输入系统调用
    /// </summary>
    public void SetLocalInput(uint frame, PlayerInput input)
    {
        ref var frameInput = ref inputBuffer[frame % 256];
        frameInput.frame = frame;
        frameInput.localInput = input;
        frameInput.localReady = true;
    }

    /// <summary>
    /// 接收远程玩家的输入（由网络线程回调）
    /// </summary>
    public void ReceiveRemoteInput(uint frame, PlayerInput remoteInput)
    {
        ref var frameInput = ref inputBuffer[frame % 256];
        frameInput.frame = frame;
        frameInput.remoteInput = remoteInput;
        frameInput.remoteReady = true;

        // 更新已确认帧：远程输入到达的最老的一帧中缺少的远程输入记录
        UpdateConfirmedFrame();
    }

    /// <summary>
    /// 推进到指定帧。这是主循环每帧调用的核心方法。
    /// 返回 true 表示成功推进。
    /// </summary>
    public bool AdvanceFrame(uint targetFrame)
    {
        // 获取当前"显示"帧（上一帧）
        uint currentFrame = targetFrame - 1;
        ref var currentInput = ref inputBuffer[currentFrame % 256];

        // 情况1：远程输入已到达 + 本地输入就绪 → 正常推进
        // 情况2：远程输入未到达 → 预测推进（假设远程"无操作"）
        // 情况3：本地输入未到达 → 等待（本地输入由我们控制，理论上不会缺）

        // 构建实际执行的输入
        FrameInput execInput = new FrameInput
        {
            frame = currentFrame,
            localInput = currentInput.localReady
                ? currentInput.localInput
                : PlayerInput.Empty,  // 安全回退
            remoteInput = currentInput.remoteReady
                ? currentInput.remoteInput
                : PredictRemoteInput(currentFrame),  // 预测！
            isPredicted = !currentInput.remoteReady,
        };

        // 保存快照（用于可能的下一次回滚）
        SaveSnapshot(currentFrame);

        // 执行逻辑帧
        OnAdvanceFrame?.Invoke(execInput);

        return true;
    }

    /// <summary>
    /// 检查是否需要回滚
    /// 调用时机：收到远程输入后
    /// </summary>
    void CheckRollback(uint frame, FrameInput oldInput)
    {
        // 如果到达的远程输入与预测的一致 → 无需回滚
        if (oldInput.isPredicted && oldInput.remoteInput.Equals(PlayerInput.Empty))
        {
            // 幸运：预测对了（假设无操作很常见）
            return;
        }

        // 预测错误！需要从该帧回滚
        Debug.LogWarning($"[Rollback] Misprediction at frame {frame}! Rolling back...");

        Rollback(frame);
    }

    /// <summary>
    /// 回滚到指定帧，用正确的输入重新推进到当前帧
    /// </summary>
    void Rollback(uint fromFrame)
    {
        uint currentFrame = GetCurrentFrame();

        // 1. 恢复 fromFrame 的快照
        RestoreSnapshot(fromFrame);

        // 2. 从 fromFrame 到 currentFrame，用正确的输入重新执行
        for (uint f = fromFrame; f <= currentFrame; f++)
        {
            ref var input = ref inputBuffer[f % 256];

            FrameInput execInput = new FrameInput
            {
                frame = f,
                localInput = input.localReady ? input.localInput : PlayerInput.Empty,
                // 此时远程输入已经到达（因为回滚的触发条件就是远程输入到达）
                remoteInput = input.remoteReady ? input.remoteInput : PredictRemoteInput(f),
                isPredicted = !input.remoteReady,
            };

            // 重新执行逻辑帧
            OnAdvanceFrame?.Invoke(execInput);

            // 更新快照（回滚后的新状态）
            SaveSnapshot(f);
        }
    }

    /// <summary>
    /// 预测远程玩家的输入
    /// 最简单的策略：假设"无操作"
    /// </summary>
    PlayerInput PredictRemoteInput(uint frame)
    {
        // 高级策略：可以基于前几帧的输入趋势预测（如方向保持、连招继续）
        // 但最简单和最常见的策略是"假设无操作"
        return PlayerInput.Empty;
    }

    /// <summary>
    /// 保存游戏状态快照（Deep Clone）
    /// 实际项目中需要由游戏逻辑层提供序列化接口
    /// </summary>
    void SaveSnapshot(uint frame)
    {
        // 这里需要游戏层调用 SetSnapshot 注入状态
        // stateBuffer[frame % 256] = SerializeGameState();
    }

    void RestoreSnapshot(uint frame)
    {
        // 恢复游戏状态
        // DeserializeGameState(stateBuffer[frame % 256]);
    }

    void UpdateConfirmedFrame()
    {
        // 从 confirmedFrame 开始向后扫描，找到连续"远程已到"的最远帧
        uint f = confirmedFrame;
        while (true)
        {
            ref var input = ref inputBuffer[f % 256];
            if (!input.remoteReady) break;
            f++;
        }
        confirmedFrame = f - 1;
    }

    uint GetCurrentFrame()
    {
        // 由游戏主循环管理
        return 0;
    }
}

// 帧输入结构
public struct FrameInput
{
    public uint frame;
    public PlayerInput localInput;
    public PlayerInput remoteInput;
    public bool localReady;
    public bool remoteReady;
    public bool isPredicted;   // 本帧的远程输入是预测的
}

// 玩家单帧输入
public struct PlayerInput : IEquatable<PlayerInput>
{
    public uint buttons;  // 位掩码: bit0=轻拳, bit1=中拳, bit2=重拳, bit3=轻脚, ...
    public sbyte xAxis;   // 方向: -1(左), 0(中), 1(右)
    public sbyte yAxis;   // 方向: -1(下), 0(中), 1(上)

    public static PlayerInput Empty => new PlayerInput();

    public bool Equals(PlayerInput other)
    {
        return buttons == other.buttons
            && xAxis == other.xAxis
            && yAxis == other.yAxis;
    }
}
```

**关键设计决策解释**：

1. **`MAX_ROLLBACK_FRAMES = 8`**：P2P 格斗游戏的网络延迟通常在 0~100ms。60fps 下 8 帧 = 133ms，足够覆盖绝大多数延迟。更大的值意味着回滚时重算帧数更多（CPU 压力更大）且视觉"跳变"更明显。

2. **`FRAME_DELAY = 2`**：人为延迟 2 帧。这意味着"我按下按钮后 2 帧才传达给对方"，代价是 33ms 额外延迟，收益是大幅减少回滚——给网络传输留出 33ms 缓冲窗口。

3. **预测策略 = 假设无操作**：这是 GGPO 默认策略，因为 PvP 格斗中 70%+ 的帧玩家确实"没有新操作"（保持方向/防御/等待）。更高级的策略可以"假设方向保持"来进一步提升预测准确率。

### 3.5 C++ 回滚缓冲区

C++ 版本的实现更贴近底层，利用内存池和裸指针消除 GC 压力：

```cpp
#include <cstdint>
#include <cstring>
#include <cassert>
#include <new>

/// <summary>
/// C++ 回滚状态缓冲区 —— 每帧的快照以原始字节形式存储
/// 使用预分配内存池，避免帧同步路径中的动态分配
/// </summary>
template<size_t MaxFrames = 256, size_t StateSize = 4096>
class RollbackBuffer
{
public:
    RollbackBuffer() : m_head(0), m_count(0)
    {
        // 预分配内存池：MaxFrames 个快照槽位
        // 每个槽位 = StateSize 字节（具体大小由游戏状态决定）
        m_pool = static_cast<uint8_t*>(
            ::operator new(MaxFrames * StateSize, std::align_val_t(64))
        );
        std::memset(m_pool, 0, MaxFrames * StateSize);
    }

    ~RollbackBuffer()
    {
        ::operator delete(m_pool, std::align_val_t(64));
    }

    // 禁止拷贝
    RollbackBuffer(const RollbackBuffer&) = delete;
    RollbackBuffer& operator=(const RollbackBuffer&) = delete;

    /// <summary>
    /// 保存帧号 frame 的游戏状态快照
    /// </summary>
    void Save(uint32_t frame, const void* stateData)
    {
        assert(frame < m_head + MaxFrames);
        size_t idx = frame % MaxFrames;

        // 直接 memcpy 到预分配槽位
        std::memcpy(Slot(idx), stateData, StateSize);

        // 记录该槽位的帧号
        m_frames[idx] = frame;

        // 更新计数
        if (frame >= m_head + m_count)
        {
            m_count = std::min(frame - m_head + 1, MaxFrames);
        }
    }

    /// <summary>
    /// 恢复到帧号 frame 的状态快照
    /// 返回 true 表示恢复成功
    /// </summary>
    bool Restore(uint32_t frame, void* outStateData)
    {
        size_t idx = frame % MaxFrames;

        // 验证槽位的帧号匹配
        if (m_frames[idx] != frame)
        {
            // 快照不存在（可能已经滚出缓冲区）
            return false;
        }

        std::memcpy(outStateData, Slot(idx), StateSize);
        return true;
    }

    /// <summary>
    /// 将指定范围内的帧重新执行（回滚追赶用）
    /// 调用者提供帧执行函数 f(frame, input)
    /// inputProvider(frame) 返回该帧的输入数据
    /// </summary>
    template<typename ExecFunc, typename InputProvider>
    void Rollforward(
        uint32_t fromFrame,
        uint32_t toFrame,
        ExecFunc&& execFunc,        // void(uint32_t frame, const InputData& input)
        InputProvider&& getInput    // InputData(uint32_t frame)
    )
    {
        // 先从快照恢复起始状态
        if (!Restore(fromFrame, m_tempState))
        {
            // 起始帧的快照不存在，无法回滚
            return;
        }

        // 逐帧重新执行
        for (uint32_t f = fromFrame + 1; f <= toFrame; ++f)
        {
            auto input = getInput(f);
            execFunc(f, input, m_tempState);  // 用 m_tempState 承载状态

            // 重新保存快照（可能被后续回滚再次使用）
            Save(f, m_tempState);
        }
    }

private:
    uint8_t* Slot(size_t idx) { return m_pool + idx * StateSize; }

    uint8_t* m_pool;           // 预分配池
    uint32_t m_frames[MaxFrames]; // 每槽位对应的帧号
    uint32_t m_head;            // 缓冲区最早帧号
    uint32_t m_count;           // 当前有效槽位数
    uint8_t  m_tempState[StateSize]; // 回滚执行时的临时状态
};
```

**使用示例——格斗游戏主循环**：

```cpp
// 游戏逻辑帧执行函数
void ExecuteFrame(uint32_t frame, const FrameInput& input, void* stateData)
{
    auto* state = static_cast<FightGameState*>(stateData);
    // 两个玩家的输入
    state->ProcessInput(0, input.p1);  // P1 是本地玩家，输入总是已知
    state->ProcessInput(1, input.p2);  // P2 是远程玩家，输入可能被预测
    state->AdvancePhysics();
    state->CheckHits();
}

// 主循环
void MainLoop()
{
    RollbackBuffer<256, sizeof(FightGameState)> rbuf;
    FightGameState currentState;

    uint32_t frame = 0;
    while (gameRunning)
    {
        // 1. 保存当前帧快照（回滚保险）
        rbuf.Save(frame, &currentState);

        // 2. 获取本地输入
        PlayerInput myInput = ReadLocalInput();

        // 3. 获取远程输入（可能已到达，也可能需要预测）
        PlayerInput remoteInput;
        bool remoteReady = TryGetRemoteInput(frame, &remoteInput);
        if (!remoteReady)
        {
            remoteInput = PredictRemote();  // 预测：空操作
        }

        // 4. 执行逻辑帧
        FrameInput frameInput{frame, myInput, remoteInput, remoteReady};
        ExecuteFrame(frame, frameInput, &currentState);

        // 5. 如果本帧远程输入是预测的且之后真实输入到达 ≠ 预测值
        if (!remoteReady && HasRemoteInputArrived(frame))
        {
            PlayerInput actualRemote = GetRemoteInput(frame);
            if (!actualRemote.Equals(remoteInput))
            {
                // 回滚！
                rbuf.Rollforward(frame, currentFrame,
                    ExecuteFrame,
                    [](uint32_t f) { return GetInputForFrame(f); }
                );
            }
        }

        // 6. 渲染（如果有回滚，渲染器只显示最终状态）
        Render(currentState);

        frame++;
    }
}
```

### 3.6 预测回滚的工程挑战

| 挑战 | 描述 | 缓解方案 |
|------|------|---------|
| **状态序列化开销** | 每帧 Deep Copy 4096 字节 × 60fps = 240KB/s 写入 | 使用 memcpy + 预分配池（C++ 方案） |
| **视觉跳变** | 回滚后面向错误方向打了空气 | 回滚帧数 ≤ 3 帧时视觉上几乎不可见；超过 5 帧需"平滑修正" |
| **音频不一致** | 回滚前播放了"击中音效"，回滚后没击中 | 音频延迟播放（与 FRAME_DELAY 对齐） |
| **确定性要求** | 回滚重算必须逐位一致，否则二次 desync | 与帧同步的确定性要求相同（定点数 + 确定性容器） |
| **不可逆操作** | 粒子特效已产生 / UI 已更新 | 将"视觉层"和"逻辑层"分离——回滚只影响逻辑层 |

---


### 3.7 GGPO SyncTest — 确定性自动验证

#### 为什么需要 SyncTest？

预测回滚有一个致命的前提条件：**游戏的逻辑执行必须是完全确定性的**。前文中我们反复强调定点数、确定性容器、禁止浮点数——但这些规则是"人肉保证"的，只要有一个程序员在某处写了 `float` 或用 `DateTime.Now` 做随机种子，回滚重算就会产生不同的结果，导致二次 desync。

传统的确定性验证方法是：在联机对战中通过 Hash 校验发现 desync。但这种方式有严重缺陷：

- **滞后性**：Desync 可能是 1000 帧前埋下的 bug，但 hash 只在每 N 帧比一次
- **不可复现**：线上出现 desync，本地连不上对方的网络环境，没法复现
- **无法 CI**：你不可能在 CI pipeline 里启动两名玩家联机对战

GGPO 给出的解决方案是 **SyncTest**——一种**单机、自动化、零网络依赖**的确定性验证模式。

#### SyncTest 核心原理

SyncTest 的核心思想非常简单：**在每一帧执行后，故意回滚 1 帧然后重新执行，比较两次执行的结果是否完全一致**。

```
正常流程 (帧 N-1 → 帧 N):
  SaveState(N-1) → AdvanceFrame(N) → SaveState(N)

SyncTest 验证流程:
  SaveState(N-1)
  → AdvanceFrame(N) → state_after_first_run
  → LoadState(N-1)
  → AdvanceFrame(N) → state_after_second_run
  → 比较 state_after_first_run == state_after_second_run ?
     ├─ 相同 → 通过！这一帧是确定性的
     └─ 不同 → 断言失败！存在非确定性 bug
```

**关键洞察**：如果游戏是确定性的，那么从同一个起点状态 S_{n-1} 出发，用同样的输入 I_n 执行一帧，得到的结果 S_n 应该是**完全相同的**——不管你是第一次执行还是第 100 次执行。如果在同一个进程中连续执行两次得到不同结果，那游戏逻辑中必然存在非确定性因素。

SyncTest 等于在每一帧做一次"微回滚"——只回滚 1 帧。因为只回滚 1 帧，不需要像正常回滚那样回滚几十帧，开销极小（只需要保存上一帧的状态，以及本帧的输入）。

#### SyncTest 的 CI 威力

SyncTest 的最大价值不在调试，而在 CI：

```bash
# CI 脚本示例 —— 每次提交自动运行
./game --synctest --frames=10000 --seed=42
# 如果有非确定性 bug，进程会 assert 崩溃 → CI 报红
```

与传统的"联机 hash 校验"相比：

| 特性 | 联机 Hash 校验 | SyncTest |
|------|---------------|----------|
| 运行方式 | 需要至少两名玩家的网络环境 | 单进程即可 |
| 检测时机 | 每 N 帧比对一次 | **每帧**都验证 |
| 错误定位 | 只能知道"某帧 hash 不同"，无法定位具体代码行 | assert 失败 → 直接停在 bug 代码行 |
| CI 支持 | 需要搭建网络环境 | 一行命令即可 |
| 覆盖范围 | 只检测"不同玩家结果不同" | 检测"同一玩家连续两次结果不同" |

#### SyncTest 的局限性

SyncTest 不是万能药。它检测的是**连续两次执行结果不同**，但以下场景它检测不到：

- **确定性但错误的计算**：比如某个公式在两边都算错了，但错得一样——SyncTest 认为"一致 = 通过"
- **输入顺序相关的确定性差异**：比如先处理 P1 输入再处理 P2 输入 vs 反过来——如果代码里处理顺序是固定的，SyncTest 也会通过

这两类问题仍然需要 Hash 校验来兜底。SyncTest + Hash 校验 = 双重保险。

#### C# SyncTest 实现

```csharp
/// <summary>
/// GGPO SyncTest —— 确定性自动验证器
///
/// 用法：
///   1. 在 CI 或开发调试时启动 SyncTest 模式（而非正常联机模式）
///   2. 每帧调用 VerifyFrame() —— 如果发现非确定性，会抛异常
///
/// 原理：每帧执行完后，回滚 1 帧重新执行，比较两次结果
/// </summary>
public class SyncTestVerifier
{
    // 上一帧的完整状态快照（用于回滚）
    byte[] lastFrameSnapshot;
    uint lastFrameNumber;
    bool hasLastFrame = false;

    // 本帧的输入（用于回滚重放）
    FrameInput lastInput;

    // 状态大小（固定值，由游戏状态决定）
    readonly int stateSize;

    // Hash 函数：用 CRC32 即可，SyncTest 只做快速比对
    // 不作安全性用途，CRC32 够用

    public SyncTestVerifier(int stateSize)
    {
        this.stateSize = stateSize;
        this.lastFrameSnapshot = new byte[stateSize];
    }

    /// <summary>
    /// 验证当前帧的确定性。
    /// 调用时机：在 AdvanceFrame() 执行完毕后。
    ///
    /// 首次调用（帧 0）只会保存快照，不验证。
    /// 从第 2 帧开始，每帧都执行 "回滚 1 帧 → 重算 → 比较"。
    /// </summary>
    /// <param name="currentFrame">当前帧号</param>
    /// <param name="currentState">当前帧执行完后的游戏状态</param>
    /// <param name="currentInput">驱动本帧执行的输入</param>
    /// <exception cref="SyncTestException">状态不一致时抛出</exception>
    public void VerifyFrame(uint currentFrame, IGameState currentState,
                            FrameInput currentInput)
    {
        if (!hasLastFrame)
        {
            // 第一帧：只保存快照，无法验证（没有"上一帧"可以回滚）
            SaveSnapshot(currentState);
            lastFrameNumber = currentFrame;
            lastInput = currentInput;
            hasLastFrame = true;
            return;
        }

        // === 步骤 1: 计算"第一次执行"的结果 Hash ===
        uint firstRunHash = currentState.ComputeLogicHash();

        // === 步骤 2: 回滚到上一帧状态 ===
        currentState.LoadFromSnapshot(lastFrameSnapshot);

        // === 步骤 3: 用相同的输入重新执行本帧 ===
        // 注意：这里的输入是"上一帧调用时保存的输入"，
        // 因为我们要重算的是 currentFrame-1 → currentFrame 这一帧
        currentState.AdvanceFrame(lastFrameNumber + 1, lastInput);

        // === 步骤 4: 计算"第二次执行"的结果 Hash ===
        uint secondRunHash = currentState.ComputeLogicHash();

        // === 步骤 5: 比较 ===
        if (firstRunHash != secondRunHash)
        {
            // 非确定性 bug 被捕获！
            string msg = string.Format(
                "[SyncTest FAIL] Frame {0}: first=0x{1:X8}, second=0x{2:X8}",
                currentFrame, firstRunHash, secondRunHash);

            // 在开发模式下，直接抛出异常停在 bug 发生处
            // CI 中进程 crash → 构建失败，完美
            throw new SyncTestException(msg);
        }

        // === 步骤 6: 保存本帧快照，供下一帧回滚使用 ===
        SaveSnapshot(currentState);
        lastFrameNumber = currentFrame;
        lastInput = currentInput;
    }

    void SaveSnapshot(IGameState state)
    {
        // 将游戏状态序列化到预分配的缓冲区
        // 这里可以用 memcpy（如果状态是值类型 POD），
        // 或者用序列化方法（如果状态包含引用类型）
        state.SerializeTo(lastFrameSnapshot);
    }
}

/// <summary>
/// SyncTest 模式下的主循环
/// </summary>
public class SyncTestRunner
{
    SyncTestVerifier verifier;
    GameState state;

    public SyncTestRunner()
    {
        verifier = new SyncTestVerifier(GameState.StateSize);
        state = new GameState();
    }

    /// <summary>
    /// 运行 N 帧 SyncTest
    /// </summary>
    /// <param name="frames">运行帧数</param>
    /// <param name="inputProvider">
    /// 输入提供者——在 SyncTest 模式下通常是
    /// 自动生成的 AI 输入或录制好的输入序列。
    /// 输入必须是完全确定的。
    /// </param>
    public void Run(int maxFrames, Func<uint, FrameInput> inputProvider)
    {
        try
        {
            for (uint f = 0; f < maxFrames; f++)
            {
                FrameInput input = inputProvider(f);
                state.AdvanceFrame(f, input);
                verifier.VerifyFrame(f, state, input);
            }

            Console.WriteLine(
                $"[SyncTest PASS] All {maxFrames} frames deterministic.");
        }
        catch (SyncTestException ex)
        {
            Console.Error.WriteLine(ex.Message);
            // 在 CI 中，让进程以非零退出码终止
            Environment.Exit(1);
        }
    }
}
```

#### SyncTest 捕获的真实 Bug 示例

以下是一个**真实会被 SyncTest 捕获的典型非确定性 bug**：

```csharp
// === 错误代码：使用系统时间做游戏逻辑 ===
public class DamageCalculator
{
    public static int CalculateCriticalDamage(int baseDamage)
    {
        // ❌ 错误：DateTime.Now.Millisecond 是系统时间，
        // 不是确定性的！第一次调用是 42ms，回滚后重算时
        // 可能已经是 43ms 了 → 不同的随机结果
        int timeMs = DateTime.Now.Millisecond;
        bool isCritical = (timeMs % 100 < 20); // 20% 暴击率

        return isCritical ? baseDamage * 2 : baseDamage;
    }
}

// === 正确代码：使用确定性随机数生成器 ===
public class DamageCalculatorFixed
{
    // ✅ 正确：使用帧同步的确定性 PRNG
    // Random 的种子在游戏开始时由服务器统一下发
    // 所有客户端用相同的种子 → 相同的随机序列
    public static int CalculateCriticalDamage(
        int baseDamage, ref DeterministicRandom rng)
    {
        // 每次调用 rng.Next() 都会推进 rng 的内部状态
        // 但这个过程是完全确定性的
        int roll = rng.Next(0, 100);
        bool isCritical = (roll < 20);
        return isCritical ? baseDamage * 2 : baseDamage;
    }
}
```

在这个例子中，SyncTest 的执行过程是：

1. 帧 100 执行 `CalculateCriticalDamage(100)`：
   - `DateTime.Now.Millisecond` = 42 → `42 % 100 < 20` = true → 暴击！伤害 200
2. 回滚到帧 99，重新执行帧 100：
   - `DateTime.Now.Millisecond` = 43（已经过了 1ms）→ `43 % 100 < 20` = true → 还是暴击？不，这次 43 ≥ 20 → 无暴击！伤害 100
3. 两次结果 Hash 不同 → **SyncTest 断言失败**，精确地停在 bug 所在帧。

这就比线上 desync 后花几天时间排查有效得多——bug 引入的**当下**就被发现了。

#### 在 CI 中集成 SyncTest

```yaml
# GitHub Actions 示例
name: Determinism Check
on: [push, pull_request]
jobs:
  synctest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: dotnet build GameCore/GameCore.csproj
      - name: Run SyncTest (10,000 frames)
        run: dotnet run --project GameCore --synctest --frames=10000 --seed=0
      - name: Run SyncTest with different seed
        run: dotnet run --project GameCore --synctest --frames=10000 --seed=12345
```

**最佳实践**：在 CI 中跑 SyncTest 时，建议用**多个不同的随机种子**各跑一遍。有的非确定性 bug 只在特定 PRNG 序列下触发（例如某个 `rand() % N` 只在特定值上出问题），多 seed 可以增加覆盖面。

---

### 3.8 Frame Delay vs Speculative Execution — 延迟与回滚的博弈

#### 问题的本质

在预测回滚系统中，一帧的执行需要"所有玩家的输入"才能保证绝对正确。但网络传输需要时间——远程玩家的输入不可能在本地帧执行的那一刻"恰好"到达。

这引出了一个根本性的权衡：

- **如果等远程输入到达再执行**：玩家感受 0 回滚，但输入延迟 = 网络 RTT/2（可能高达 100ms+）
- **如果不等就直接执行（预测）**：即时响应，但远程输入到来后可能需要回滚

GGPO 给出的方案是**折中**：等一小段时间（Frame Delay），但不等全部——等不到的帧靠预测 + 回滚兜底。

#### Frame Delay（帧延迟）

**定义**：故意将本地输入延迟 N 帧再发送，让本地玩家和远程玩家的输入在"同一时间点"到达对方。

```
无 Frame Delay：
  Frame 0: 本地按下"前"→ 立即发送，本帧执行
           远程输入还没到 → 预测（空操作）
  Frame 1: 本地按下"拳"→ 立即发送，本帧执行
           远程的 Frame 0 输入到达 → 发现预测错了 → 回滚！

Frame Delay = 2：
  Frame 0: 本地按下"前"→ 存入发送队列，不立即发送
  Frame 2: "前"输入被发送（延迟了 2 帧）
           此时远程的 Frame 2 输入也已到达
           → 不需要预测，不需要回滚！
```

**Frame Delay 的本质**：用本地玩家的输入延迟，换取远程输入的"准时到达"。增加的输入延迟 = FrameDelay × (1/fps)。例如 FrameDelay=2, 60fps → ~33ms 额外延迟。

#### Speculative Execution（推测执行）

**定义**：不等远程输入，直接用预测值执行当前帧。如果后来发现预测错误，回滚重算。

预测策略（详见 3.3 节）：
- 空操作预测："对手什么都没做"
- 惯性预测："对手延续上一帧的操作"
- AI 预测："用行为树预测对手下一步操作"

#### 两者的关系：GGPO 的核心公式

```
RollbackFrames = max(0, TransmissionDelay - FrameDelay)

其中：
  TransmissionDelay = 远程输入到达所需帧数
    = (网络 RTT/2 + 处理时间) × fps
  FrameDelay = 故意引入的本地输入延迟帧数
```

**直观理解**：
- 如果 FrameDelay ≥ TransmissionDelay → 远程输入总是准时到达 → RollbackFrames = 0（完美！但输入有延迟）
- 如果 FrameDelay < TransmissionDelay → 远程输入可能在执行时尚未到达 → RollbackFrames > 0（可能需要回滚）

**例子**：60fps 格斗游戏，RTT=50ms

```
TransmissionDelay = (25ms + 5ms处理) × 60fps ≈ 2 帧

FrameDelay = 0:
  RollbackFrames = 2 - 0 = 2 帧 → 最多回滚 2 帧，输入延迟 0 → 极致响应，偶有回滚

FrameDelay = 1:
  RollbackFrames = 2 - 1 = 1 帧 → 最多回滚 1 帧，输入延迟 16.7ms → 折中

FrameDelay = 2:
  RollbackFrames = 2 - 2 = 0 帧 → 永不回滚，输入延迟 33ms → 稳定，但手感偏"肉"
```

#### 按游戏类型推荐 FrameDelay

| 游戏类型 | 推荐 FrameDelay | 理由 |
|---------|----------------|------|
| **格斗游戏** | 1–2 帧 | 玩家对输入延迟极其敏感。1 帧延迟（16.7ms @ 60fps）是职业选手能感知的极限。RTT < 30ms 时可设为 1 帧。 |
| **FPS（帧同步模式）** | 1–3 帧 | 射击需要即时反馈，但比格斗的帧精度要求稍低。配合客户端预测（本地立即播放枪口火焰）来掩盖延迟。 |
| **RTS** | 3–5 帧 | 指令延迟（点击到单位响应）50–83ms 在 RTS 中是可接受的。更高的 FrameDelay 意味着更少的回滚和更稳定的体验。 |
| **MOBA** | 2–4 帧 | 王者荣耀实测使用约 3 帧 FrameDelay。移动端 RTT 波动大，需要留足缓冲。 |
| **回合制/棋牌** | 5–8 帧 | 无实时操作压力。高 FrameDelay = 网络容错能力强。 |

#### 自适应帧延迟 (Adaptive Frame Delay)

固定 FrameDelay 的问题：网络质量是动态的。在 Wi-Fi 环境下，RTT 可能从 30ms 跳到 200ms。

**自适应方案**：根据实时测量的 RTT 动态调整 FrameDelay。

```csharp
/// <summary>
/// 自适应帧延迟调节器
///
/// 核心逻辑：
/// - 维护 RTT 的指数加权移动平均 (EWMA)
/// - 当 RTT 升高 → 增加 FrameDelay（减少回滚风险）
/// - 当 RTT 降低 → 减少 FrameDelay（改善手感）
/// - 变化必须平滑，不能跳变（否则玩家会感到"操作时滞忽大忽小"）
/// </summary>
public class AdaptiveFrameDelay
{
    // EWMA 平滑因子（0-1，越小越平滑但响应越慢）
    const float EWMA_ALPHA = 0.2f;

    // 当前实测 RTT（秒）
    float smoothedRTT;

    // 当前帧延迟（帧数）
    int currentFrameDelay;

    // 帧延迟范围
    readonly int minFrameDelay;
    readonly int maxFrameDelay;

    // 游戏帧率
    readonly float fps;

    public AdaptiveFrameDelay(int minDelay, int maxDelay, float fps = 60f)
    {
        this.minFrameDelay = minDelay;
        this.maxFrameDelay = maxDelay;
        this.fps = fps;
        this.smoothedRTT = 0.05f; // 初始假设 RTT=50ms
        this.currentFrameDelay = (minDelay + maxDelay) / 2; // 初始取中值
    }

    /// <summary>
    /// 每次收到远程输入时调用，更新 RTT 估计
    /// </summary>
    /// <param name="measuredRTT">本次测量到的 RTT（秒）</param>
    public void OnRTTMeasured(float measuredRTT)
    {
        // 指数加权移动平均：平滑 RTT 的短时抖动
        smoothedRTT = EWMA_ALPHA * measuredRTT
                     + (1f - EWMA_ALPHA) * smoothedRTT;

        RecomputeFrameDelay();
    }

    void RecomputeFrameDelay()
    {
        // 将 RTT 转换为帧数（含处理缓冲）
        // 半程 RTT + 帧处理时间 ≈ 需要的等待帧数
        float halfRTTFrames = (smoothedRTT / 2f) * fps;
        float processingBuffer = 1f; // 1 帧处理缓冲
        int idealDelay = Mathf.CeilToInt(halfRTTFrames + processingBuffer);

        // 平滑调整：每次最多改变 1 帧，避免跳变
        if (idealDelay > currentFrameDelay)
            currentFrameDelay = Math.Min(currentFrameDelay + 1, maxFrameDelay);
        else if (idealDelay < currentFrameDelay)
            currentFrameDelay = Math.Max(currentFrameDelay - 1, minFrameDelay);

        // 确保在合法范围内
        currentFrameDelay = Math.Clamp(currentFrameDelay, minFrameDelay, maxFrameDelay);
    }

    public int GetFrameDelay() => currentFrameDelay;
}
```

**自适应策略的最佳实践**：

- **只增不减要谨慎**：如果网络变好，应该降低 FrameDelay。但改变必须平滑——每次 ±1 帧，每 30 帧最多调整一次。
- **上线前锁定下限**：格斗游戏 FrameDelay 不应低于 1 帧，即使 RTT 极低。1 帧是帧同步固有的"发送 → 广播 → 接收"最低延迟。
- **突发事件降级**：检测到连续 3 次回滚帧数 > 阈值时，立即将 FrameDelay +2 作为应急措施，防止"回滚风暴"。

---

### 3.9 确定性陷阱深度剖析

预测回滚对确定性的要求是**绝对的、逐位的**——前文我们反复强调定点数和确定性容器，但实际工程中还有很多更隐蔽的陷阱。以下 5 个陷阱来自 GGPO 官方文档和实际项目的血泪经验。

#### 陷阱 1：系统时间 (Wall Clock Time)

**症状**：游戏逻辑中使用了 `DateTime.Now`、`Time.time`、`clock()` 等系统时间 API。

**为什么破坏确定性**：系统时间是外部输入，帧同步系统无法控制。第一次执行时系统时间是 T，回滚重算时系统时间是 T+Δt——即使 Δt 只有 1ms，也足以导致某些逻辑（如暴击判定、伤害计算）产生不同结果。

```csharp
// ❌ 错误：使用系统时间作为随机种子或逻辑判断
public class BuffManager
{
    public void UpdateBuffs(float deltaTime)
    {
        // 问题 1: deltaTime 来自 Unity 的 Time.deltaTime
        // 在不同帧率/不同硬件上值可能不同
        buff.RemainingDuration -= deltaTime;

        // 问题 2: 用系统时间做周期性效果触发
        if (DateTime.Now.Second % 3 == 0)
        {
            ApplyPeriodicEffect();
        }
    }
}

// ✅ 正确：所有时间概念来源于帧号
public class BuffManagerFixed
{
    public void UpdateBuffs(uint currentFrame)
    {
        // 帧号是确定性的——所有客户端在帧 100 执行相同的逻辑
        // fixedDeltaTime 是编译时确定的常量：1/60 = 0.01666...
        const float FIXED_DELTA = 1f / 60f;

        buff.RemainingDuration -= FIXED_DELTA;

        // 周期性效果用帧号判断（帧 180 → 3 秒 @60fps）
        if (currentFrame % 180 == 0)
        {
            ApplyPeriodicEffect();
        }
    }
}
```

**C++ 版本**：

```cpp
// ❌ 错误：std::chrono 也是系统时间
auto now = std::chrono::steady_clock::now();
auto seed = now.time_since_epoch().count();
std::mt19937 rng(seed);  // 不同客户端 seed 不同 → desync
// ✅ 正确：帧号驱动
// 在帧同步启动时，服务器下发统一的随机种子
// 例如：seed = hash(gameSessionID + serverTimestamp) 由服务器统一下发
uint32_t deterministicSeed = sessionData.randomSeed;
std::mt19937 rng(deterministicSeed);
```

#### 陷阱 2：Static 变量 / 全局状态

**症状**：C/C++ 中的 `static` 局部变量、全局变量、单例模式中的状态。

**为什么破坏确定性**：Static 变量的生命周期是整个进程——回滚时你复制了游戏状态的 struct，但 static 变量还留在原地，保持着"错误"的值。下次执行函数时读到的还是旧值。

```cpp
// ❌ 错误：函数内的 static 变量
int GetNextProjectileID()
{
    static int nextID = 0;  // 致命！这个变量不在 GameState 里
    return nextID++;        // 回滚后 nextID 不会回滚
}

// 执行过程：
// 帧 50: GetNextProjectileID() → 返回 100，nextID 变成 101
//        → 新建子弹 ID=100
// 回滚到帧 49，重算帧 50:
//        GetNextProjectileID() → 返回 101（不是 100！）← 已经不同了！

// ✅ 正确：将状态放入 GameState
struct GameState
{
    int nextProjectileID = 0;  // 保存在 state 中，回滚时会一起恢复
};

int GetNextProjectileID(GameState& state)
{
    return state.nextProjectileID++;  // 确定性的——回滚后回到正确的值
}
```

**C# 版本——注意 `static` 的隐患**：

```csharp
// ❌ 错误：静态字段
public class EntityFactory
{
    private static int _nextEntityID = 0;  // 不属于任何 GameState 实例

    public static int AllocateID()
    {
        return _nextEntityID++;  // 回滚无法恢复
    }
}

// ✅ 正确：实例字段，随 GameState 一起保存/恢复
public class EntityFactory
{
    private int _nextEntityID;  // 实例字段

    public EntityFactory(int startID = 0)
    {
        _nextEntityID = startID;
    }

    public int AllocateID()
    {
        return _nextEntityID++;
    }

    // 序列化支持：保存/恢复时包含此字段
    public void Serialize(BinaryWriter w) => w.Write(_nextEntityID);
    public void Deserialize(BinaryReader r) => _nextEntityID = r.ReadInt32();
}
```

#### 陷阱 3：悬垂引用 / 悬垂指针

**症状**：游戏状态中保存了指向其他对象的指针或引用。

**为什么破坏确定性**：回滚时，保存的状态快照被恢复到内存中。但指针指向的地址是**新的**——旧的对象可能已经被移动/释放了。如果逻辑依赖指针比较（`if (target == lastTarget)`），回滚后地址不同，逻辑分支不同。

```cpp
// ❌ 错误：使用裸指针
struct GameState
{
    Entity* playerTarget;  // 保存了指向 Enemy 实体的指针
    //                    // 回滚后 Enemy 可能位于不同的内存地址
};

// ✅ 正确：使用 EntityID（索引）代替指针
struct GameState
{
    EntityID playerTarget;  // EntityID 是整数类型
    //                      // 回滚后通过 ID 查找实体
    //                      // 如果实体已被销毁 → EntityID 为 INVALID
};

// 使用示例
void ProcessAttack(GameState& state)
{
    Entity* target = FindEntityByID(state.playerTarget);
    if (target != nullptr && target->IsAlive())
    {
        target->TakeDamage(10);
    }
}
```

**C# 版本**：

```csharp
// ❌ 错误：引用类型直接作为状态的一部分
public struct BadGameState
{
    public Enemy targetEnemy;  // 引用类型！回滚后引用可能失效
}

// ✅ 正确：用 ID 代理
public struct GoodGameState
{
    public int targetEnemyID;  // 值类型，可直接 memcpy
    public bool HasTarget => targetEnemyID != -1;
}
```

#### 陷阱 4：未初始化内存

**症状**：结构体/对象的某些字段从未被显式初始化，读取时可能得到任意值。

**为什么破坏确定性**：未初始化内存的内容是不确定的——在 Debug 模式下可能被编译器初始化为 0xCC，在 Release 模式下可能是上次那块内存的残留值。不同客户端、不同运行环境、甚至同一进程的两次运行——都可能读到不同的值。

```cpp
// ❌ 错误：未初始化的内存
struct PlayerInput
{
    uint16_t buttons;       // 哪些按键被按下
    int16_t stickX;        // 摇杆 X 轴
    int16_t stickY;        // 摇杆 Y 轴
    uint8_t padding[3];    // ❌ 未初始化！如果被序列化到 hash 中 → 不确定
};

// 某次运行：padding = { 0x00, 0x12, 0xFF }
// 另一次运行：padding = { 0xCC, 0xCC, 0xCC }
// → hash 不同 → "desync"！
// 注意：即使 padding 不在"游戏逻辑"中使用，
// 只要它被包含在 hash 计算的序列化中，就会触发误报

// ✅ 正确：零初始化所有字段
struct PlayerInputFixed
{
    uint16_t buttons = 0;
    int16_t stickX = 0;
    int16_t stickY = 0;
    uint8_t padding[3] = {0};  // 显式零初始化

    // 或者在 SaveState 时只序列化有效字段，不包含 padding：
    void Serialize(BinaryWriter& w) const
    {
        w.Write(buttons);
        w.Write(stickX);
        w.Write(stickY);
        // padding 不写入！
    }
};

// ✅ 最佳实践：GameState 在创建时用 memset 清零
GameState* CreateGameState()
{
    auto* state = static_cast<GameState*>(
        ::operator new(sizeof(GameState), std::align_val_t(64))
    );
    std::memset(state, 0, sizeof(GameState));  // 全零初始化
    return state;
}
```

**C# 版本**：

```csharp
// C# 中，值类型 (struct) 的字段会自动初始化为默认值（0/null）
// 但要注意：数组、List 等集合类型的元素可能是默认值

// ❌ 易错：Hash 计算时包含了未显式设置的字段
public struct EntityState
{
    public int hp;
    public int maxHp;
    public int unusedField;  // 始终为 0，但在序列化时被写入 hash → 浪费/潜在风险
}

// ✅ 正确：只序列化逻辑字段，明确排除 padding/unused
public struct EntityStateFixed
{
    public int hp;
    public int maxHp;

    public void WriteHash(BinaryWriter w)
    {
        w.Write(hp);
        w.Write(maxHp);
        // unusedField 不参与 hash
    }
}
```

#### 陷阱 5：外部库的内部状态

**症状**：游戏逻辑依赖了第三方库（物理引擎、寻路库、音频引擎），这些库内部维护了无法被 GGPO Save/Load 机制覆盖的状态。

**为什么破坏确定性**：回滚时你只能保存/恢复自己的 `GameState` struct。物理引擎内部的碰撞体 BVH 树、音频引擎的 DSP 缓冲区、寻路库的 NavMesh 缓存——这些都不在你的 `GameState` 里。回滚后它们保持着"错误"的中间状态。

```cpp
// ❌ 错误：物理引擎的状态无法被 Save/Load
struct GameState
{
    // 这是我自己的状态，可以保存/恢复
    int playerHP;
    Vec3 playerPosition;

    // ❌ physicsWorld 的碰撞检测内部状态不在我的控制范围内
    // 回滚无法恢复它的 broadphase 缓存、接触点列表等
    b2World* physicsWorld;
};

// ✅ 正确方案 A：将物理引擎的确定性版本作为纯逻辑层
// 使用定点数物理引擎（如自定义实现的简单物理），
// 或确认物理引擎本身是确定性的且支持状态保存。

// ✅ 正确方案 B（更实用）：分离逻辑状态与引擎状态
// 不在回滚帧中调用物理引擎；用逻辑层自己维护简化的物理状态
struct GameStateFixed
{
    int playerHP;
    Fixed64 playerX, playerY;    // 定点数位置
    Fixed64 velocityX, velocityY; // 定点数速度
    // ... 所有物理相关数据都直接用定点数存储
    // 不必依赖外部物理引擎
};

// 引擎层（渲染/物理表现）可以并行运行，
// 但从逻辑层读取状态，不反向写入

// ✅ 正确方案 C：为保存/恢复设计确定性重置
class PhysicsWrapper
{
    b2World* world;

    // 每次回滚后，完全重建物理世界
    void ResetFromGameState(const GameState& state)
    {
        delete world;
        world = new b2World(b2Vec2(0, -10));

        // 从 GameState 重新创建所有物理体
        for (auto& entity : state.entities)
        {
            b2BodyDef def;
            def.position.Set(entity.posX.ToFloat(), entity.posY.ToFloat());
            // 注意：这依赖于浮点数转换的确定性
            // 一般不推荐对核心逻辑这样做
            world->CreateBody(&def);
        }
    }
};
```

**总体建议**：回滚涉及的核心逻辑层（输入处理、碰撞判定、伤害计算、AI 决策）应**完全避免**依赖外部有状态库。如果必须使用（如寻路），确保：

1. 该库的接口是"纯函数式"的——给定相同输入，总是返回相同输出
2. 或每次回滚后能够将该库的内部状态完全重置（通常意味着重建所有对象）

#### 确定性检查清单

将以上陷阱汇总为一张工程检查清单：

| # | 检查项 | 工具/方法 |
|---|-------|----------|
| 1 | 无 `DateTime.Now` / `clock()` / `Time.time` 等系统时间调用 | grep |
| 2 | 无 `static` 局部变量在逻辑函数中持有可变状态 | clang-tidy `cert-dcl59-cpp` |
| 3 | 无裸指针保存在 `GameState` 中（全部用 ID/索引） | code review |
| 4 | 所有序列化到 hash 的 struct 零初始化或显式排除 padding | valgrind `--track-origins=yes` |
| 5 | 核心逻辑不依赖第三方有状态库的内部状态 | 架构审查 |
| 6 | 所有浮点数替换为定点数（或确认 `-ffloat-store` 等编译器行为）| grep `float` / `double` |
| 7 | 容器遍历顺序确定（`OrderBy` 排序后再遍历） | code review |
| 8 | CI 中启用 SyncTest（多种 seed 各跑 10000 帧）| CI pipeline |


## 4. 帧同步反外挂

### 4.1 帧同步的独特外挂风险

帧同步的反外挂问题与其他网络架构有本质区别：**客户端拥有全量游戏状态**。

在状态同步中，服务器可以不发送"视野外敌人"的数据——你看不到的东西，外挂也看不到。但在帧同步中，所有客户端独立计算整个游戏世界——每个客户端的**内存里已经有了所有实体的位置、血量、冷却时间**。你只是选择不渲染它们。

这使得帧同步面对的外挂类型与状态同步完全不同：

| 外挂类型 | 帧同步易发性 | 说明 |
|---------|------------|------|
| **全图挂 (MapHack)** | **极高** | 数据已在内存中，只需读取并渲染 |
| **数值修改** | **高** | 修改内存中的 HP/攻击力等数值，导致本地 eval 与服务器不同 |
| **自瞄 / 自动走位** | **中** | AI 读取内存做决策，难度对帧同步和状态同步类似 |
| **DDoS / 掉线挂** | 低 | 与网络拓扑有关，与同步模型无关 |
| **加速外挂** | **高** | 加速 Tick 频率或用不同时间步长执行逻辑 |

### 4.2 全图挂（MapHack）——帧同步的阿喀琉斯之踵

**原理**：帧同步客户端计算全量状态，意味着敌方英雄的位置、野怪血量、技能冷却等信息在客户端内存中是完整且实时的。外挂只需 Hook `GameState` 的内存地址，读取数据，然后在画面中叠加渲染。

```
正常客户端：
  游戏状态内存 ──[裁剪]──→ 只渲染视野内对象

外挂客户端：
  游戏状态内存 ──[直接读取]──→ 渲染所有对象
```

**为什么帧同步的 MapHack 比状态同步更难防？**

状态同步中，服务器可以不发视野外数据——消除了问题。帧同步中，客户端需要所有数据来计算世界——无法消除问题，只能检测和威慑。

**检测方法**：

1. **行为分析**：玩家总是"碰巧"知道敌人在草丛里。统计"非视野内技能命中率"、"非视野路径精确度"等指标。
2. **客户端完整性校验**：验证代码段是否被修改（完整性 Hash）。
3. **内存扫描**：反作弊客户端（如 TenProtect）扫描是否有已知外挂的内存特征。

**缓解方法**：

1. **视野裁剪不应仅靠渲染层**：即使逻辑层有全量状态，渲染层在绘制前应做二次裁剪检查——虽然不能防止数据被读，但增加了外挂"找出有用数据"的难度。
2. **数据混淆（Obfuscation）**：将敌方英雄位置存储在 XOR 加密的内存区域，只在逻辑层使用时解密。
3. **服务端重跑比对**：定期让服务端重跑 N 帧逻辑，对比"客户端声称的结果"——这是最有效的方法（见 4.3）。

### 4.3 数值修改——修改 HP/攻击力

**攻击者手法**：

```cpp
// 外挂伪代码：注入 DLL 后 Hook 游戏逻辑
void __cdecl HookDamageCalculation(Unit* attacker, Unit* defender)
{
    // 原始逻辑
    int rawDamage = CalculateRawDamage(attacker, defender);
    // 外挂注入：将伤害乘以 10
    int hackedDamage = rawDamage * 10;
    ApplyDamage(defender, hackedDamage);
}
```

由于帧同步的分散计算特性，这种修改只影响**攻击者本地的计算结果**。攻击者会看到"我秒杀了敌人"，但服务器和其他客户端仍然正常运行（使用未被修改的逻辑）。这本质上也是一种 Desync。

**检测方法——服务端重跑逻辑比对**：

```
1. 服务器缓存最近 N 帧的输入（只存输入，极小）
2. 每 M 秒（如 5 秒），服务器随机选取 1 个客户端
3. 要求该客户端上报其当前游戏状态的 Hash（或关键字段）
4. 服务器用缓存的输入序列重跑逻辑，计算"正确"状态
5. 比对 Hash
6. 如果差异超过阈值 → 标记为可疑
```

```csharp
// 服务端重跑校验
public class ServerSideLogicVerifier
{
    // 服务端维护一个轻量逻辑引擎
    // 不需要完整渲染，只需要逻辑计算能力
    ServerGameLogic logicEngine;

    // 输入环形缓冲区
    Dictionary<uint, FrameInput[]> inputHistory = new();

    // 随机抽查
    public async Task RandomAudit(uint targetFrame)
    {
        // 1. 请求客户端上报 targetFrame 的状态 Hash
        var clientHash = await RequestClientHash(targetFrame);

        // 2. 服务端重跑
        string serverHash = RecomputeHash(targetFrame);

        // 3. 比对
        if (clientHash != serverHash)
        {
            LogSecurityAlert($"Player {suspectId}: hash mismatch at frame {targetFrame}");
            LogSecurityAlert($"  Client: {clientHash}, Server: {serverHash}");
            // 标记为可疑，进入人工审核
        }
    }

    string RecomputeHash(uint targetFrame)
    {
        // 从最近一次已知正确的状态开始快进
        // （服务器可维护一个"基线状态"）
        logicEngine.LoadBaseline();
        for (uint f = baselineFrame + 1; f <= targetFrame; f++)
        {
            if (inputHistory.TryGetValue(f, out var inputs))
            {
                logicEngine.ExecuteFrame(f, inputs);
            }
        }
        return logicEngine.ComputeStateHash();
    }
}
```

**为什么服务端重跑比对是银弹？**

因为帧同步中，F 是确定性的——给定输入和初始状态，结果唯一。服务器重跑的结果就是"绝对正确答案"。任何声称与服务器结果一致的客户端，要么诚实，要么外挂还能完美模拟服务端逻辑——后者要求外挂不仅 Hack 逻辑，还要在"被抽查时"提交正确结果。这大幅提升了外挂开发成本。

### 4.4 自瞄 / 自动走位

这类外挂通过 AI 读取游戏内存中的敌人位置，自动做出最优决策（瞄准、走位）。帧同步中检测难度与状态同步类似。

**检测方法**：

1. **输入模式分析**：真人的输入有"抖动"——鼠标移动的轨迹不是完美直线，操作频率有波动。AI 的输入则异常"干净"。
2. **反应时间分析**：人类对视觉刺激的反应时间 ≥ 150ms。如果敌人一进视野（<50ms）就开始精确瞄准 → 机器。
3. **决策一致性**：AI 在面对相同局面时会做出完全相同的决策（给相同输入）。真人有随机性。

### 4.5 预防手段

#### 代码混淆 (Obfuscation)

```csharp
// 原始代码
public class HealthComponent
{
    public int CurrentHP;
}

// 混淆后（示例，真实混淆远更复杂）
public class aB3xK
{
    private int _x7F;  // 不再是 "CurrentHP"

    // XOR 加密存储
    private int _xorKey = 0x7A3F_5C12;

    public int GetValue()
    {
        return _x7F ^ _xorKey;
    }

    public void SetValue(int v)
    {
        _x7F = v ^ _xorKey;
    }
}
```

生产环境使用专业混淆工具（如 .NET 的 ConfuserEx、C++ 的 OLLVM/Obfuscator-LLVM），不是手工混淆。

#### 反调试 (Anti-Debug)

```cpp
// Windows 反调试示例
#include <Windows.h>

bool IsDebuggerPresent_Custom()
{
    // 检查 PEB (Process Environment Block) 的 BeingDebugged 标志
    // 不是调用 IsDebuggerPresent()，而是直接读 PEB
    // 因为调用 API 本身可以被 Hook
    BOOL beingDebugged = FALSE;
    __asm {
        mov eax, fs:[0x30]     // PEB 地址
        movzx eax, byte ptr [eax + 2]  // BeingDebugged
        mov beingDebugged, eax
    }
    return beingDebugged;

    // 更隐蔽的检查：NtQueryInformationProcess(ProcessDebugPort, ...)
    // 或 CheckRemoteDebuggerPresent()
}
```

#### 客户端签名

定期对客户端代码段做 Hash，与服务器记录的"已知正确 Hash"比对。任何注入的 DLL 或修改的代码都会改变 Hash。

---

## 5. 帧同步录像 (Replay)

### 5.1 为什么帧同步录像极小？

回顾帧同步的数学基础：

$$S_n = F(F(...F(F(S_0, I_0), I_1), ...), I_{n-1})$$

录像文件 = $S_0$ + $[I_0, I_1, I_2, ..., I_{N-1}]$

不需要存任何一帧的游戏状态，只需要：
- **初始状态 $S_0$**（几十到几百字节：地图种子、英雄选择、初始位置）
- **所有帧的输入序列**（每帧每玩家 ~10 bytes × 玩家数 × 帧数）

**实际数字对比**：

| 项目 | 帧同步录像 | 状态同步录像（近似） |
|------|-----------|-------------------|
| 30 分钟 MOBA | **~200 KB** | ~50 MB（需存关键帧+状态） |
| 10 分钟格斗 | **~50 KB** | ~5 MB |
| 1 小时 RTS | **~500 KB** | ~200 MB |

帧同步录像的体积与**游戏复杂度完全无关**！100 单位还是一万单位，录像一样大——因为只存输入。

### 5.2 录像文件格式设计

```
文件结构：
┌─────────────────────────────────┐
│ Header (128 bytes)              │
│   magic: 0x524C_5059 ("REPLAY")│
│   version: 2                    │
│   gameMode: 1 (MOBA)            │
│   playerCount: 10               │
│   logicFPS: 15                  │
│   totalFrames: 16200 (30min)    │
│   mapSeed: 0x7A3F_5C12         │
│   checksum: CRC32 of body      │
├─────────────────────────────────┤
│ Initial State (variable)        │
│   playerHeroes[]: [heroId, skinId, ...]  │
│   mapData: compressed           │
├─────────────────────────────────┤
│ Frame Inputs (variable)         │
│   ├─ Frame 0: [P0 input, P1 input, ...]│
│   ├─ Frame 1: [P0 input, ...]  │
│   ├─ Frame 2: ...              │
│   └─ Frame N: ...              │
└─────────────────────────────────┘
```

```csharp
using System.IO;
using System.IO.Compression;

public class ReplayWriter
{
    BinaryWriter writer;
    GZipStream compressedStream;  // 输入序列高度可压缩（大量空操作帧）

    public void WriteHeader(ReplayHeader header)
    {
        writer.Write(0x524C5F50);       // magic "RP_P"
        writer.Write((ushort)2);        // version
        writer.Write((byte)header.playerCount);
        writer.Write((byte)header.logicFPS);
        writer.Write(header.totalFrames);
        writer.Write(header.mapSeed);
    }

    public void WriteFrameInputs(FrameInput[] inputs)
    {
        // 每帧：1 byte 帧类型 + N × 输入数据
        // 帧类型: 0=正常帧, 1=关键帧(可跳跃), 2=元数据帧
        writer.Write((byte)0);  // 正常帧

        foreach (var input in inputs)
        {
            WritePlayerInput(input);
        }
    }

    void WritePlayerInput(FrameInput input)
    {
        // 位掩码紧凑编码
        // 2 bytes: 操作标志 + 参数
        // 如果玩家无操作 → 1 bit 就够了
        writer.Write(input.buttons);     // 2 bytes: 操作位掩码
        if (input.HasPosition())
        {
            writer.Write(input.targetX); // 4 bytes: target X (fixed-point raw)
            writer.Write(input.targetY); // 4 bytes: target Y
        }
    }
}

public struct ReplayHeader
{
    public byte playerCount;
    public byte logicFPS;
    public uint totalFrames;
    public uint mapSeed;
}
```

### 5.3 录像回放实现

```csharp
public class ReplayPlayer
{
    GameState state;
    Queue<FrameInput[]> inputQueue;
    uint currentFrame;

    public void Load(string replayPath)
    {
        // 1. 读取 Header
        // 2. 初始化 GameState 到 S_0
        // 3. 将所有帧输入加载到 inputQueue
    }

    // 每渲染帧调用一次（渲染帧率 60fps ≠ 逻辑帧率 15fps）
    public void Update(float deltaTime)
    {
        accumulator += deltaTime;
        float logicDt = 1.0f / logicFPS;  // 66.67ms @ 15fps

        // 追赶逻辑帧
        while (accumulator >= logicDt && inputQueue.Count > 0)
        {
            var inputs = inputQueue.Dequeue();
            state.ExecuteFrame(currentFrame, inputs);
            currentFrame++;
            accumulator -= logicDt;
        }

        // 用剩余时间做插值渲染
        float alpha = accumulator / logicDt;
        RenderInterpolated(state, alpha);
    }
}
```

---

## 6. 帧同步调试

### 6.1 帧日志 (Frame Log)

帧同步最困难的调试场景：**线上 desync 了，本地怎么都复现不了**。

帧日志是解决方案——记录每一帧的决策点：

```csharp
public class FrameLogger
{
    const int LOG_BUFFER_FRAMES = 120;  // 最近 2 秒的日志（@60fps）
    Queue<string>[] playerLogs;         // 每玩家一个日志队列

    // 在游戏逻辑的关键决策点调用
    public void LogDecision(uint frame, int playerId, string eventType, string detail)
    {
        // 只记录"决策点"——即可能产生分歧的地方：
        // - 碰撞检测结果
        // - 伤害计算
        // - 随机数生成
        // - AI 决策
        // - 技能命中判定

        int idx = frame % LOG_BUFFER_FRAMES;
        playerLogs[playerId].Enqueue(
            $"[F{frame}] {eventType}: {detail}"
        );
    }

    // Desync 发生时，将日志 Dump 到文件
    public void DumpLogs(uint desyncFrame, string path)
    {
        using var writer = new StreamWriter(path);
        uint startFrame = desyncFrame > LOG_BUFFER_FRAMES
            ? desyncFrame - LOG_BUFFER_FRAMES : 0;

        writer.WriteLine($"=== Desync Report ===");
        writer.WriteLine($"Desync Frame: {desyncFrame}");
        writer.WriteLine($"Log Range: [{startFrame}, {desyncFrame}]");

        for (uint f = startFrame; f <= desyncFrame; f++)
        {
            int idx = f % LOG_BUFFER_FRAMES;
            foreach (var logEntry in playerLogs[playerId])
            {
                if (logEntry.StartsWith($"[F{f}]"))
                    writer.WriteLine(logEntry);
            }
        }
    }
}
```

### 6.2 状态 Diff 工具

当两个客户端产生 desync 时，最直观的诊断是：**直接对比两个 GameState，找出第一个不一致的字段**。

```csharp
public class StateDiffer
{
    public struct DiffEntry
    {
        public string fieldPath;  // 如 "Entity[42].PosX"
        public string valueA;
        public string valueB;
    }

    public List<DiffEntry> Diff(GameState stateA, GameState stateB)
    {
        var diffs = new List<DiffEntry>();

        // 收集所有实体的 ID 并集
        var allIds = new HashSet<uint>(stateA.Entities.Keys);
        allIds.UnionWith(stateB.Entities.Keys);

        foreach (var id in allIds.OrderBy(x => x))
        {
            bool inA = stateA.Entities.TryGetValue(id, out var entA);
            bool inB = stateB.Entities.TryGetValue(id, out var entB);

            if (inA != inB)
            {
                diffs.Add(new DiffEntry
                {
                    fieldPath = $"Entity[{id}].Exists",
                    valueA = inA.ToString(),
                    valueB = inB.ToString(),
                });
                continue;
            }

            // 逐个字段比较
            if (entA.PosX != entB.PosX)
                diffs.Add(new DiffEntry {
                    fieldPath = $"Entity[{id}].PosX",
                    valueA = entA.PosX.ToString(),
                    valueB = entB.PosX.ToString(),
                });

            if (entA.PosY != entB.PosY)
                diffs.Add(new DiffEntry {
                    fieldPath = $"Entity[{id}].PosY",
                    valueA = entA.PosY.ToString(),
                    valueB = entB.PosY.ToString(),
                });

            if (entA.HP != entB.HP)
                diffs.Add(new DiffEntry {
                    fieldPath = $"Entity[{id}].HP",
                    valueA = entA.HP.ToString(),
                    valueB = entB.HP.ToString(),
                });

            // ... 其他字段
        }

        return diffs;
    }
}
```

### 6.3 逐帧回放定位

最可靠的方法——二分法定位 desync 帧：

```
1. 记录输入序列（从 Frame 0 到 Desync Frame）
2. 服务端用输入序列重放
   状态 S_server = F(S_0, I_0, I_1, ..., I_N)
3. 客户端送来的状态 S_client = 客户端计算的结果
4. 对比 S_server 和 S_client 的 Hash
5. 如果第 N 帧的 Hash 不同：
   - 二分法：检查第 N/2 帧的 Hash
   - 如果 N/2 帧相同 → desync 发生在 (N/2, N] 区间
   - 如果 N/2 帧不同 → desync 发生在 [0, N/2] 区间
   - 递归缩小范围，直到定位到精确帧
```

```csharp
public class BisectDesyncFinder
{
    // 输入序列（从帧0到desyncFrame，服务端记录的）
    FrameInput[][] inputSequence;
    GameState initialState;

    // 二分法定位 desync 发生的精确帧
    public uint FindDesyncFrame(uint knownBadFrame, Func<uint, string> getClientHash)
    {
        // 前置条件：已知 Frame 0 是好的，Frame knownBadFrame 是坏的
        uint good = 0;
        uint bad = knownBadFrame;

        while (bad - good > 1)
        {
            uint mid = (good + bad) / 2;

            // 服务端重跑到 mid 帧
            string serverHash = ComputeServerHash(mid);

            // 获取客户端在 mid 帧的 Hash（从已记录的 Hash 序列）
            string clientHash = getClientHash(mid);

            if (serverHash == clientHash)
                good = mid;  // mid 帧一致，desync 在后面
            else
                bad = mid;   // mid 帧不一致，desync 在前面或就在此帧
        }

        // bad 现在是第一个不一致的帧
        Debug.Log($"Desync first detected at frame {bad}");
        Debug.Log($"Last good frame: {good}");

        // 检查 good 和 bad 之间的逻辑差异
        DumpFrameDiff(good, bad);

        return bad;
    }

    string ComputeServerHash(uint frame)
    {
        var state = initialState.DeepClone();
        for (uint f = 0; f <= frame; f++)
        {
            state.ExecuteFrame(f, inputSequence[f]);
        }
        return SnapshotHash.ComputeMD5(state);
    }

    void DumpFrameDiff(uint goodFrame, uint badFrame)
    {
        // 详细对比 good 和 bad 之间所有变量的变化
        // 帮助定位是哪个逻辑分支出了非确定性问题
    }
}
```

---

## 7. 扩展阅读

### 必读文章
- **GGPO 官网与论文**：https://www.ggpo.net/ — Tony Cannon 的完整 GGPO 介绍和白皮书
- **GDC 2019: 8 Frames in 16ms — Rollback Networking in Mortal Kombat and Injustice 2**：NetherRealm 工作室的实战分享，回滚网络在商业格斗游戏中的应用
  https://www.gdcvault.com/play/1026410/
- **GDC 2018: It's GGPO! — The Community Effects of Rollback**：GGPO 对格斗游戏社区的影响分析
- **Fight the Latency! — 关于 Rollback 的深入技术博客**：
  https://ki.infil.net/w02-netcode.html

### 中文深度文章
- **帧同步反外挂方案（腾讯云）**：帧同步项目的安全架构实战
- **王者荣耀的反外挂体系**：腾讯游戏安全中心公开分享

### 开源参考
- **GGPO 开源 SDK**：https://github.com/pond3r/ggpo — 官方开源实现
- **Unity Rollback Network Sample**：Unity 官方网络同步示例中的回滚实现
- **FightCore**：开源格斗游戏引擎，含完整 Rollback 实现

---

## 8. 练习

### 练习 1: 基础 — 实现 Hash 校验系统（30min）

基于教程 05 的帧同步模拟器（或自建一个简化游戏逻辑），实现快照校验：

1. **创建两个 GameState 实例**，初始状态相同
2. **手动模拟 Desync**：在某个特定帧，给 State B 的某个实体 HP 加 1（模拟非确定性 Bug）
3. **实现 Hash 计算**：每帧结束后计算 GameState 的 CRC32 或简单 XOR Hash
4. **实现 Desync 检测**：两个 GameState 的 Hash 在每帧比较，第一次出现不一致时立即报警并报告帧号
5. **验证**：确认你的检测器能在"HP+1 过的第一帧"就发现不同

要求：Hash 计算必须使用确定的实体遍历顺序（按 EntityID 排序后迭代）。

### 练习 2: 进阶 — 实现简易 GGPO 回滚（60min）

用 C#/Unity 或 C++ 实现一个 **1v1 本地模拟**的 GGPO 回滚系统：

1. **构建简化的格斗游戏逻辑**：
   - 两个角色，各有 HP、位置（一维即可：x 坐标）
   - 输入：左移(-1)、右移(+1)、攻击(A)、防御(D)
   - 碰撞判定：如果攻击帧时两角色距离 < 阈值 → 命中，扣血

2. **实现回滚缓冲区**（Ring Buffer 存储每帧的状态快照）：
   - `SaveSnapshot(frame, state)` — 保存快照
   - `RestoreSnapshot(frame) → state` — 恢复快照
   - 使用 Deep Clone（C# 的序列化克隆或 C++ 的 memcpy）

3. **模拟预测 + 回滚流程**：
   - 本地玩家输入总是"真实"的
   - 远程玩家输入：每帧以 80% 概率"已到达"，20% 概率"预测为空操作"
   - 当预测错误的输入到达时，触发回滚

4. **测量指标**：
   - 总帧数 vs 回滚次数
   - 平均回滚帧数（每次回滚需要重算多少帧）
   - 预测准确率（预测"空操作"猜对的概率）

要求：回滚后的画面不能出现抖动——只渲染最终结果。

### 练习 3: 挑战 — 服务端重跑反外挂验证（90min）

设计并实现一个服务端反外挂验证系统（可用 Python 或 C# 实现服务端部分）：

1. **客户端部分**（C#）：
   - 运行一个简单的 MOBA 简化逻辑（2v2，每帧执行移动/攻击/技能）
   - 逻辑使用定点数（教程 06 的 FixedMath 库）
   - 每 100 帧上报一次状态 Hash（MD5）

2. **服务端部分**（Python/C#）：
   - 缓存所有帧的输入序列
   - 维护一个"影子逻辑引擎"——相同的游戏逻辑代码，执行同样的帧输入
   - 每 100 帧，将服务端重算的 Hash 与客户端上报的 Hash 对比

3. **外挂模拟**：
   - 在客户端注入一个"作弊模块"：每 50 帧随机给某个友方英雄的 HP + 5
   - 作弊模块不应影响输入序列（输入仍然是正常的）

4. **验证**：
   - 服务端应在作弊发生后的 100 帧内检测到 Hash 不一致
   - 打印检测报告：不一致的帧号、客户端 Hash、服务端 Hash

5. **进阶**：
   - 不依赖 Hash，让服务端重新计算所有实体状态，逐字段对比，定位到"哪个实体的哪个字段"被篡改
   - 模拟作弊者"只在 Hash 不检测时才作弊"——通过预测 Hash 检测时机来躲避检测。服务端如何改进？

---

## 常见陷阱

### 陷阱 1: Hash 计算时包含了渲染层数据

**错误**：在 Hash 计算中包含了动画帧进度、粒子系统状态、UI 状态（如血条渲染值）等渲染层数据。

**为什么错**：渲染层数据在不同客户端上天然不同（帧率、GPU 驱动、插值算法），把渲染数据纳入 Hash 必然导致误报 Desync。

**正确做法**：Hash 只覆盖**逻辑层状态**——位置（定点数）、HP（整数）、技能冷却（整数帧数）等。渲染层数据（动画帧、插值 alpha、特效状态）不应参与 Hash 计算。

### 陷阱 2: 回滚帧数设得太大

**错误**：`MAX_ROLLBACK_FRAMES = 30`，认为"缓冲越大越好"。

**为什么错**：回滚缓冲越大：
1. 快照存储开销越大（每帧 Deep Copy 整个 GameState）
2. 回滚时重算帧数越多（CPU 尖刺）
3. 视觉跳变越明显（从 30 帧前的状态突然跳到当前帧）
4. 内存占用（30 × GameState 大小可能接近 MB 级别）

**正确做法**：回滚缓冲大小 = 预期最大网络延迟 + 安全余量。对于 P2P 格斗游戏（RTT 通常 < 50ms），FRAME_DELAY = 2 + MAX_ROLLBACK = 8 是合理的。宁可出现一次"等网络"的卡顿，也不要 30 帧的大规模回滚。

### 陷阱 3: 把录像文件存成了视频格式

**错误**：用录屏软件录游戏的 mp4 作为"录像"。

**为什么错**：失去了帧同步录像的所有优势：
- 文件体积与游戏分辨率成正比（1080p 30fps → 每分钟约 100MB）
- 无法"切换视角"观看
- 无法快进/倒退到任意帧
- 无法作为诊断工具（不能重放逻辑）

**正确做法**：录像 = 初始状态 + 输入序列。这是帧同步的天然优势。

### 陷阱 4: 只做客户端校验，不做服务端校验

**错误**：反外挂方案全靠客户端的 TenProtect/反调试/混淆，没有服务端校验。

**为什么错**：客户端的任何防御都可以被绕过——反调试可以被反-反调试，混淆可以被去混淆，完整性 Hash 可以被伪造。唯一不可欺骗的是"服务端重跑逻辑结果"——因为服务器运行在外挂无法访问的环境中。

**正确做法**：客户端安全措施是"门锁"（增加成本），服务端重跑校验是"摄像头 + 报警"（最终防线）。两者必须结合。

### 陷阱 5: 调试 Desync 时只看 Hash 不看日志

**错误**：检测到 Hash 不一致，知道 desync 了，但没有记录"为什么 desync"的诊断信息，开始猜。

**为什么错**：只靠 Hash 无法知道**哪个逻辑步骤**出了问题。你需要知道：
- 哪一帧开始不一致
- 哪个实体的哪个字段第一个出现了分歧
- 那一帧的输入是什么
- 那一帧调了哪些函数、产生了哪些随机数

**正确做法**：帧日志（Frame Log） + 状态 Diff + 二分定位（Bisect）是定位 Desync 的标准工具链。在开发阶段多花一点时间建设调试基础设施，在线上问题排查时会省下百倍时间。

### 陷阱 6: 认为 GGPO 只适合格斗游戏

**错误**：听到"回滚网络"就联想到复杂的 GGPO 实现，认为自己的非格斗游戏用不上。

**为什么错**：回滚的思想可以部分引入帧同步架构，不一定要完整的 GGPO。例如：
- 在 5v5 MOBA 中，客户端可以先用自己的输入预测执行（不等服务器），等服务器输入到达后，如果一致则无需回滚——因为自己的输入总是对的。这本质上是一种"半回滚"（只需在收到别人输入时做轻量一致性检查）。
- 在动作游戏中，可以用"快照 + 局部回滚"降低特定技能的感知延迟。

**正确做法**：理解回滚作为**延迟隐藏技术**的本质，然后按需裁剪到自己的场景。不要因为 GGPO 的全套实现复杂就放弃回滚思想。
