---
title: "延迟补偿 (Lag Compensation & Server-Side Rewind)"
updated: 2026-06-05
---

# 延迟补偿 (Lag Compensation & Server-Side Rewind)

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [[15-server-reconciliation|15-服务端和解 (Server Reconciliation)]]

---

## 1. 概念讲解

### 1.1 为什么需要延迟补偿？——延迟的不公平性

想象一个典型的 FPS 场景：

```
时刻 T0:  玩家A（低延迟 30ms）站在掩体后。
时刻 T1:  玩家B（高延迟 150ms）在B的屏幕上看到A从掩体后跑出来。
时刻 T2:  B开枪射击——在B的屏幕上，子弹命中了A的身体。
时刻 T3:  射击消息在网络上传输 150ms 到达服务器。
时刻 T4:  服务器收到射击消息。此时服务器上的"权威世界"中，
          A在 T0+150ms 时已经跑回了掩体后面。
时刻 T5:  服务器判定：A在掩体后，B的子弹打在掩体上 → 未命中。
```

**B 在他的屏幕上明明白白看到子弹打在 A 身上，服务器却说没打中。**

这就是网络延迟造成的**不公平性**：不是谁枪法好谁赢，而是**谁的延迟低谁赢**。低延迟玩家天然拥有"信息优势"——他们看到的世界更接近服务器权威世界。高延迟玩家看到的是过去的世界，射击"过去的目标"在服务器看来等于射击"当前位置的掩体"。

在没有延迟补偿的 FPS 中，高延迟玩家必须**提前量射击 (leading)**——瞄准敌人**将要到达的位置**而非屏幕上的当前位置。这违反了 FPS 的基本直觉："瞄准即命中"。

**延迟补偿的目标**：

> 让每个玩家可以瞄准屏幕上看到的目标，而不是需要预判网络延迟的提前量。

具体来说：服务器的命中判定不是以**收到消息时**的世界状态来做，而是以**射击者看到的世界状态**来做。

### 1.2 核心思想：服务端回退 (Server-Side Rewind)

延迟补偿的核心技术叫 **Server-Side Rewind**（也称 Backwards Reconciliation / Lag Compensation）。它的核心思想极其简洁：

> **服务器将世界状态回退到"射击者在扣扳机那一刻看到的世界"，再做命中判定。**

```
射击者（Player B, RTT=300ms）的时间线:

B 的屏幕上:    [看到A在掩体外]      ← B扣下扳机
              ↑
              | 网络传输: 150ms
              ↓
服务器时间线:  [A已经跑回掩体后]    [收到B的射击消息]
              |                    |
              服务器上的"当前"世界    ↓
                              回退到B看到的世界
                              ↓
                              在历史世界中做射线检测
                              ↓
                              命中！→ 扣除A的生命值
```

关键步骤：

1. **记录历史状态**：服务器在每个 tick 保存所有玩家的位置快照到环形缓冲区
2. **接收射击消息**：消息携带 `{射击者ID, 目标时间戳, 射击方向/射线}`
3. **计算回退时间**：`回退时间 = 服务器当前时间 - 射击者的RTT/2`（即射击者在扣扳机时看到的世界时间）
4. **执行回退命中**：将目标玩家（被射击者）的位置恢复到"回退时间"对应的历史位置，然后做射线检测
5. **恢复**：检测完成后，将目标玩家位置恢复到当前状态，继续模拟

### 1.3 关键概念：Lag Compensation 不是 Prediction

这里有一个常见的概念混淆需要澄清：

| 概念 | 谁做的 | 目标 | 方向 |
|------|--------|------|------|
| **客户端预测 (Client-Side Prediction)** | 客户端 | 让本地玩家操作即时响应 | 向前推测（本地玩家→未来） |
| **服务端和解 (Server Reconciliation)** | 服务器+客户端 | 纠正客户端预测的误差 | 向后纠正（服务器矫正客户端） |
| **实体插值 (Entity Interpolation)** | 客户端 | 让远程玩家运动平滑 | 在历史中插值（远程玩家→过去） |
| **延迟补偿 (Lag Compensation)** | 服务器 | 让射击判定公平 | 向后回退（服务器回到过去） |

延迟补偿只涉及**服务器端的命中判定**。它不改变客户端看到的东西，不改变玩家移动的流畅性，也不涉及预测。它**只在服务器判定"这次射击中没中"的那一刻**发挥作用。

### 1.4 数学描述

设：
- $T_{now}$：服务器当前时间
- $T_{shot}$：射击者在本地扣扳机的时间（客户端时间戳）
- $RTT_B$：射击者 B 的往返延迟
- $S(t)$：世界在时间 t 的状态
- $P_A(t)$：玩家 A 在时间 t 的位置

**无延迟补偿的判定**：
$$\text{Hit} = \text{Raycast}(S(T_{now}), \text{射线参数})$$

**有延迟补偿的判定**：
$$\text{Hit} = \text{Raycast}(S(T_{rewind}), \text{射线参数})$$

其中：
$$T_{rewind} = T_{now} - \frac{RTT_B}{2}$$

$T_{rewind}$ 的物理含义：射击者在**扣扳机那一刻**，他的屏幕上看到的世界对应服务器时间轴上的哪个时间点。

推导：
- 服务器状态广播到客户端需要约 $RTT/2$ 时间
- 所以客户端屏幕上显示的世界，是约 $RTT/2$ 之前的服务器世界
- 因此射击者在时刻 $T_{now}$ 看到的世界 ≈ 服务器在 $T_{now} - RTT/2$ 时的世界

这就是为什么射击消息不需要携带"目标时间戳"——服务器可以用当前时间减去 RTT/2 来计算。

但在实际工程中，**消息通常携带客户端时间戳**，因为：
1. RTT 可能有抖动（RTT/2 只是估计值）
2. 客户端可能因为帧率不稳定，渲染的世界延迟不等于 RTT/2
3. 携带精确的时间戳可以消除估计误差

### 1.5 回退流程图

```
                    ┌──────────────────────────────────────────────┐
                    │              每 Tick 执行的流程                 │
                    └──────────────────────────────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    │  1. 保存当前帧快照到 History Buffer        │
                    │     Snapshot{ tick, positions[], ... }    │
                    └─────────────────────┬─────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    │  2. 处理所有待处理的射击消息               │
                    │     for each shot in pendingShots:        │
                    └─────────────────────┬─────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    │  3. 对每个射击：                           │
                    │     a) 计算 T_rewind                      │
                    │     b) 从 History Buffer 取出目标玩家      │
                    │        在 T_rewind 时刻的位置              │
                    │     c) 将目标玩家临时移动到历史位置        │
                    │     d) 执行射线检测                        │
                    │     e) 如果命中 → 应用伤害                 │
                    │     f) 恢复目标玩家到当前真实位置          │
                    └─────────────────────┬─────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    │  4. 继续运行物理/游戏逻辑（当前真实状态）  │
                    └─────────────────────┬─────────────────────┘
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    │  5. 清理过期的历史快照                     │
                    │     (超过 MaxHistoryTime 的条目)           │
                    └──────────────────────────────────────────┘
```

---

## 2. 代码示例

### 2.1 C#: 服务端回退命中判定 — 完整实现

以下代码是一个生产级 FPS 服务器的延迟补偿核心模块。包含环形历史缓冲区、命中判定回退、伤害处理和时间戳管理。

```csharp
// LagCompensationSystem.cs — 服务端回退命中判定完整实现
// 适用于 Unity Netcode / 自定义 C# 服务器
// 依赖: UnityEngine (Vector3, Physics), System.Collections.Generic

using System;
using System.Collections.Generic;
using UnityEngine;

namespace ServerLagCompensation
{
    #region 数据结构

    /// <summary>
    /// 单个 tick 的快照：记录所有玩家在该 tick 的位置和旋转。
    /// 这是回退命中判定的数据来源。
    /// </summary>
    public struct PlayerPoseSnapshot
    {
        public uint Tick;               // 服务器 tick 号
        public int PlayerId;            // 玩家 ID
        public Vector3 Position;        // 世界坐标位置
        public Quaternion Rotation;     // 旋转
        public Vector3 Velocity;        // 速度（用于插值）
        public bool IsValid;            // 此快照是否有效（玩家可能不在线/未生成）
    }

    /// <summary>
    /// 客户端发送的射击消息。
    /// 从网络反序列化后进入服务器的射击处理队列。
    /// </summary>
    public struct ShotMessage
    {
        public int ShooterId;           // 谁开的枪
        public uint ClientTick;         // 射击时客户端的本地 tick（用于回退计算）
        public Vector3 ShootOrigin;     // 射线起点（世界坐标）
        public Vector3 ShootDirection;  // 射线方向（单位向量）
        public float MaxRange;          // 最大射程
        public int WeaponId;            // 武器类型（用于伤害计算）
        public uint ServerTickReceived; // 服务器在哪个 tick 收到此消息（由收包线程填充）
    }

    /// <summary>
    /// 命中判定结果。
    /// </summary>
    public struct HitResult
    {
        public bool Hit;                // 是否命中
        public int VictimId;            // 被击中玩家 ID（-1 表示未命中玩家）
        public Vector3 HitPoint;        // 命中点世界坐标
        public Vector3 HitNormal;       // 命中面法线
        public float Distance;          // 射线起点到命中点的距离
    }

    #endregion

    #region 环形历史缓冲区

    /// <summary>
    /// 环形缓冲区：存储每个玩家最近 N 个 tick 的位置快照。
    /// 使用二维数组 [playerIndex, tickIndex] 而非 Dictionary 避免 GC 分配。
    /// </summary>
    public class HistoryBuffer
    {
        private readonly int _maxPlayers;
        private readonly uint _bufferSize;          // 每个玩家保存多少 tick 的历史
        private readonly PlayerPoseSnapshot[,] _buffer; // [playerSlot, tickIndex]
        private readonly uint[] _headTick;          // 每个玩家最新写入的 tick 号
        private readonly object _lock = new object();

        /// <param name="maxPlayers">最大玩家数</param>
        /// <param name="historyTicks">保存历史长度（tick数）。如 tickrate=60, 保存1秒 → 60</param>
        public HistoryBuffer(int maxPlayers, uint historyTicks)
        {
            _maxPlayers = maxPlayers;
            _bufferSize = historyTicks;
            _buffer = new PlayerPoseSnapshot[maxPlayers, historyTicks];
            _headTick = new uint[maxPlayers];

            // 初始化为无效快照
            for (int p = 0; p < maxPlayers; p++)
            {
                _headTick[p] = 0;
                for (int t = 0; t < historyTicks; t++)
                    _buffer[p, t].IsValid = false;
            }
        }

        /// <summary>
        /// 每 tick 调用一次：保存所有在线玩家的当前位置快照。
        /// 必须在物理模拟完成后、处理射击消息前调用。
        /// </summary>
        public void RecordSnapshot(uint serverTick, IReadOnlyList<PlayerState> players)
        {
            lock (_lock)
            {
                for (int i = 0; i < players.Count && i < _maxPlayers; i++)
                {
                    var player = players[i];
                    if (player == null || !player.IsSpawned) continue;

                    int slot = player.PlayerId;
                    uint index = serverTick % _bufferSize;

                    _buffer[slot, index] = new PlayerPoseSnapshot
                    {
                        Tick = serverTick,
                        PlayerId = player.PlayerId,
                        Position = player.Position,
                        Rotation = player.Rotation,
                        Velocity = player.Velocity,
                        IsValid = true
                    };
                    _headTick[slot] = serverTick;
                }
            }
        }

        /// <summary>
        /// 获取指定玩家在目标 tick 的插值位置。
        /// 如果精确 tick 没有快照，在最近的两个快照之间线性插值。
        /// </summary>
        /// <returns>插值后的位置快照。如果目标 tick 超出历史范围返回 invalid。</returns>
        public PlayerPoseSnapshot GetInterpolatedPose(int playerId, uint targetTick)
        {
            lock (_lock)
            {
                if (playerId < 0 || playerId >= _maxPlayers)
                    return default;

                uint headTick = _headTick[playerId];
                if (headTick == 0) return default;

                // 目标 tick 超出历史范围：太老或太新
                if (targetTick > headTick) return default;
                if (targetTick + _bufferSize < headTick) return default;

                // 先尝试精确匹配
                uint exactIndex = targetTick % _bufferSize;
                var exact = _buffer[playerId, exactIndex];
                if (exact.IsValid && exact.Tick == targetTick)
                    return exact;

                // 线性插值：找最近的前后两个快照
                uint beforeTick = targetTick;
                uint afterTick = targetTick;

                PlayerPoseSnapshot before = default, after = default;
                bool foundBefore = false, foundAfter = false;

                // 向后搜索（更老的 tick）
                for (uint t = targetTick; t + _bufferSize > headTick && t > 0; t--)
                {
                    uint idx = t % _bufferSize;
                    var snap = _buffer[playerId, idx];
                    if (snap.IsValid && snap.Tick <= targetTick)
                    {
                        before = snap;
                        beforeTick = t;
                        foundBefore = true;
                        break;
                    }
                }

                // 向前搜索（更新的 tick）
                for (uint t = targetTick + 1; t <= headTick; t++)
                {
                    uint idx = t % _bufferSize;
                    var snap = _buffer[playerId, idx];
                    if (snap.IsValid && snap.Tick >= targetTick)
                    {
                        after = snap;
                        afterTick = t;
                        foundAfter = true;
                        break;
                    }
                }

                if (!foundBefore && !foundAfter) return default;
                if (!foundAfter) return before;   // 只有更老的快照
                if (!foundBefore) return after;   // 只有更新的快照
                if (beforeTick == afterTick) return before;

                // 线性插值
                float t_ratio = (float)(targetTick - beforeTick) / (afterTick - beforeTick);
                return new PlayerPoseSnapshot
                {
                    Tick = targetTick,
                    PlayerId = playerId,
                    Position = Vector3.Lerp(before.Position, after.Position, t_ratio),
                    Rotation = Quaternion.Slerp(before.Rotation, after.Rotation, t_ratio),
                    Velocity = Vector3.Lerp(before.Velocity, after.Velocity, t_ratio),
                    IsValid = true
                };
            }
        }

        /// <summary>
        /// 临时存储：在一次回退检测中暂存目标玩家的原始位置，
        /// 检测完成后恢复。用于回退→检测→恢复的流程。
        /// </summary>
        private readonly Dictionary<int, (Vector3 pos, Quaternion rot)> _restoreData = new();

        /// <summary>
        /// 将目标玩家临时移动到历史位置（为射线检测做准备）。
        /// 返回 true 表示移动成功，false 表示历史数据不可用。
        /// </summary>
        public bool RewindPlayer(PlayerState player, uint targetTick)
        {
            var snapshot = GetInterpolatedPose(player.PlayerId, targetTick);
            if (!snapshot.IsValid) return false;

            // 保存当前位置用于恢复
            _restoreData[player.PlayerId] = (player.Position, player.Rotation);

            // 临时移动到历史位置
            player.Position = snapshot.Position;
            player.Rotation = snapshot.Rotation;
            return true;
        }

        /// <summary>
        /// 恢复玩家到回退前的位置。
        /// </summary>
        public void RestorePlayer(PlayerState player)
        {
            if (_restoreData.TryGetValue(player.PlayerId, out var original))
            {
                player.Position = original.pos;
                player.Rotation = original.rot;
                _restoreData.Remove(player.PlayerId);
            }
        }
    }

    #endregion

    #region 回退命中判定系统

    /// <summary>
    /// 延迟补偿的主系统：接收射击消息，执行回退命中判定，产生伤害事件。
    /// </summary>
    public class LagCompensationSystem
    {
        private readonly HistoryBuffer _history;
        private readonly List<PlayerState> _players;
        private readonly Queue<ShotMessage> _pendingShots = new();
        private readonly uint _tickRate;          // 服务器 tick 频率（如 60）
        private readonly float _maxLagCompensationMs; // 最大补偿延迟（ms），超出则拒绝

        // 调试/统计
        public int ShotsProcessed { get; private set; }
        public int ShotsHit { get; private set; }
        public int ShotsRewindFailed { get; private set; }

        /// <param name="maxPlayers">最大玩家数</param>
        /// <param name="tickRate">服务器 tickrate（Hz）</param>
        /// <param name="historySeconds">保存历史快照的秒数</param>
        /// <param name="maxLagMs">最大补偿延迟（ms）。超过此延迟的射击不做补偿，直接拒绝</param>
        public LagCompensationSystem(int maxPlayers, uint tickRate,
                                     float historySeconds = 1.0f, float maxLagMs = 500.0f)
        {
            _tickRate = tickRate;
            _maxLagCompensationMs = maxLagMs;

            uint historyTicks = (uint)(tickRate * historySeconds);
            _history = new HistoryBuffer(maxPlayers, historyTicks);
            _players = new List<PlayerState>(maxPlayers);
        }

        /// <summary>
        /// 注册玩家到系统（通常在玩家 spawn 时调用）。
        /// </summary>
        public void RegisterPlayer(PlayerState player)
        {
            if (!_players.Exists(p => p.PlayerId == player.PlayerId))
                _players.Add(player);
        }

        /// <summary>
        /// 每 tick 调用：保存快照 → 处理射击 → 运行物理。
        /// 调用顺序至关重要！
        /// </summary>
        public void OnServerTick(uint currentTick)
        {
            // Step 1: 先运行物理模拟，更新所有玩家到当前位置
            RunPhysics(currentTick);

            // Step 2: 保存更新后的位置快照（供未来回退使用）
            _history.RecordSnapshot(currentTick, _players);

            // Step 3: 处理所有待处理的射击消息
            ProcessPendingShots(currentTick);
        }

        /// <summary>
        /// 接收客户端射击消息（由网络层调用）。
        /// </summary>
        public void EnqueueShot(ShotMessage shot)
        {
            _pendingShots.Enqueue(shot);
        }

        /// <summary>
        /// 处理所有待处理的射击消息。
        /// 每个射击都会触发一次回退→射线检测→恢复的完整流程。
        /// </summary>
        private void ProcessPendingShots(uint currentTick)
        {
            while (_pendingShots.Count > 0)
            {
                var shot = _pendingShots.Dequeue();
                var result = ProcessSingleShot(shot, currentTick);

                ShotsProcessed++;

                if (result.Hit)
                {
                    ShotsHit++;
                    ApplyDamage(shot, result);
                }

                // 通知射击者和被击中者
                SendShotResult(shot, result, currentTick);
            }
        }

        /// <summary>
        /// 处理单个射击消息：核心回退逻辑。
        /// </summary>
        private HitResult ProcessSingleShot(ShotMessage shot, uint currentTick)
        {
            // ──── 1. 计算回退时间 ────
            // 射击消息携带了客户端 tick（ClientTick）。
            // 我们需要计算这个 ClientTick 对应服务器时间轴上的哪个 tick。
            //
            // 简化方案：假设客户端和服务器的 tick 频率相同，且射击消息的传输
            // 延迟约为 (currentTick - ClientTick) 个 tick。回退时间为 ClientTick。
            //
            // 更精确的方案：服务器维护每个玩家的"客户端时钟偏移"（通过 NTP 类似的机制）。
            // 这里使用简化方案——直接使用 ClientTick 作为回退目标。
            uint rewindTick = shot.ClientTick;

            // 安全检查：回退不能超过最大补偿时间
            uint tickAge = currentTick - rewindTick;
            float ageMs = (float)tickAge / _tickRate * 1000.0f;
            if (ageMs > _maxLagCompensationMs)
            {
                // 超过最大补偿窗口，拒绝这次射击（可能的作弊或极端网络情况）
                ShotsRewindFailed++;
                return new HitResult { Hit = false, VictimId = -1 };
            }

            // ──── 2. 找到射击者（验证射击者存在且合法） ────
            var shooter = _players.Find(p => p.PlayerId == shot.ShooterId);
            if (shooter == null || !shooter.IsSpawned)
                return new HitResult { Hit = false, VictimId = -1 };

            // ──── 3. 回退所有潜在目标玩家到历史位置 ────
            // 注意：只需回退"可能被射线穿过的玩家"，优化时可以先用 AABB 粗筛。
            // 生产环境应使用空间哈希或 BVH 加速结构。
            var rewoundPlayers = new List<PlayerState>();

            foreach (var player in _players)
            {
                if (player.PlayerId == shot.ShooterId) continue; // 不检测射击者自己
                if (!player.IsSpawned) continue;

                // 简单距离过滤：先做球体检测（快速剔除远处玩家）
                float approxDist = Vector3.Distance(shot.ShootOrigin, player.Position);
                if (approxDist > shot.MaxRange * 1.5f) continue;

                // 执行回退
                if (_history.RewindPlayer(player, rewindTick))
                {
                    rewoundPlayers.Add(player);
                }
            }

            // ──── 4. 执行射线检测 ────
            // 此时被回退玩家的位置已经恢复到射击者看到的历史位置。
            // 使用 Unity Physics.Raycast 进行精确碰撞检测。
            //
            // 关键：必须更新物理场景使移动后的碰撞体生效。
            // 在 Unity 中，直接修改 Transform.position 不会自动更新 Rigidbody/Collider。
            // 生产代码需要使用 Physics.SyncTransforms() 或 Rigidbody.position。
            //
            // 简化演示：假设我们使用自定义的碰撞检测而非 Unity Physics。
            var bestHit = new HitResult { Hit = false, VictimId = -1, Distance = float.MaxValue };

            foreach (var victim in rewoundPlayers)
            {
                // 执行针对每个玩家的碰撞检测（使用玩家碰撞体）
                // 这里简化为胶囊体射线检测
                if (RaycastAgainstPlayer(shot.ShootOrigin, shot.ShootDirection,
                                         shot.MaxRange, victim, out var hitInfo))
                {
                    if (hitInfo.Distance < bestHit.Distance)
                    {
                        bestHit = hitInfo;
                    }
                }
            }

            // ──── 5. 恢复所有被回退的玩家 ────
            foreach (var player in rewoundPlayers)
            {
                _history.RestorePlayer(player);
            }

            // ──── 6. 如果命中了玩家，还要检查是否有墙体遮挡 ────
            // 在回退后的世界中，射线先碰到墙体还是先碰到玩家？
            // 需要做完整的世界几何体射线检测（包括静态几何体）。
            //
            // 完整实现：先用 RaycastAll 获取所有碰撞，按距离排序。
            // 如果第一个碰撞是静态几何体 → 未命中玩家。
            // 如果第一个碰撞是玩家碰撞体 → 命中。
            //
            // 注意：世界几何体（墙壁、掩体）不需要回退——它们是静态的。
            // 只有玩家需要回退。

            return bestHit;
        }

        /// <summary>
        /// 对单个玩家执行射线 vs 胶囊体碰撞检测。
        /// 简化实现；生产环境应使用 Unity Physics.Raycast + CapsuleCollider。
        /// </summary>
        private bool RaycastAgainstPlayer(Vector3 origin, Vector3 direction, float maxRange,
                                          PlayerState victim, out HitResult result)
        {
            result = new HitResult { Hit = false, VictimId = -1 };

            // 简化：使用 SphereCast 近似玩家的碰撞体积
            // 实际玩家的碰撞体通常是胶囊体（CapsuleCollider），高约1.8m，半径约0.3m
            float playerRadius = 0.3f;
            float playerHeight = 1.8f;

            Vector3 playerCenter = victim.Position + Vector3.up * (playerHeight * 0.5f);

            // 点到射线的最近距离
            Vector3 playerToOrigin = origin - playerCenter;
            float projectionLength = Vector3.Dot(playerToOrigin, direction);

            // 玩家在射线后方
            if (projectionLength < 0 && playerToOrigin.magnitude > playerRadius)
                return false;

            // 最近点
            Vector3 closestPoint = origin + direction * Mathf.Max(0, projectionLength);
            float closestDist = Vector3.Distance(closestPoint, playerCenter);

            if (closestDist <= playerRadius && projectionLength <= maxRange)
            {
                result.Hit = true;
                result.VictimId = victim.PlayerId;
                result.HitPoint = closestPoint;
                result.Distance = projectionLength;
                result.HitNormal = (closestPoint - playerCenter).normalized;
                return true;
            }

            return false;
        }

        private void RunPhysics(uint currentTick)
        {
            // 在实际服务器中，这里运行物理模拟更新所有玩家位置。
            // 此处省略具体实现，假设 _players 中的 Position 已被更新。
        }

        private void ApplyDamage(ShotMessage shot, HitResult result)
        {
            // 根据武器类型计算伤害
            float damage = CalculateDamage(shot.WeaponId, result.Distance, result.HitPoint);
            var victim = _players.Find(p => p.PlayerId == result.VictimId);
            if (victim != null)
            {
                victim.Health -= damage;
            }
        }

        private float CalculateDamage(int weaponId, float distance, Vector3 hitPoint)
        {
            // 简化：固定伤害。实际应包含距离衰减、部位倍率（爆头/身体/四肢）。
            return 25.0f;
        }

        private void SendShotResult(ShotMessage shot, HitResult result, uint currentTick)
        {
            // 发送命中/未命中结果给相关客户端（射击者和被击中者）。
            // 被击中者收到通知后可播放受击动画。
        }
    }

    #endregion

    #region 玩家状态（供演示用）

    /// <summary>
    /// 服务器端的玩家状态。只包含命中判定需要的最少字段。
    /// </summary>
    public class PlayerState
    {
        public int PlayerId;
        public Vector3 Position;
        public Quaternion Rotation;
        public Vector3 Velocity;
        public float Health = 100f;
        public bool IsSpawned = true;

        // 碰撞检测用的碰撞体引用（在 Unity 中为 CapsuleCollider）
        // public CapsuleCollider Collider;
    }

    #endregion

    #region 使用示例

    /// <summary>
    /// 服务器主循环中的集成方式：
    ///
    /// var lagComp = new LagCompensationSystem(maxPlayers: 16, tickRate: 60);
    /// lagComp.RegisterPlayer(playerA);
    /// lagComp.RegisterPlayer(playerB);
    ///
    /// // 每 tick:
    /// void FixedUpdate() {
    ///     uint tick = GetCurrentServerTick();
    ///     lagComp.OnServerTick(tick);
    /// }
    ///
    /// // 网络收包线程:
    /// void OnShotReceived(ShotMessage msg) {
    ///     msg.ServerTickReceived = GetCurrentServerTick();
    ///     lagComp.EnqueueShot(msg);
    /// }
    /// </summary>

    #endregion
}
```

### 2.2 C++: HistoryBuffer + RewindSystem — 高性能实现

以下代码展示 C++ 服务端中延迟补偿的数据结构和核心算法，注重缓存友好和零分配。

```cpp
// lag_compensation.hpp — C++ 服务端的延迟补偿系统
// 适用于 Unreal Engine Dedicated Server 或自定义 C++ 游戏服务器
// 编译: C++17 或更高

#pragma once

#include <vector>
#include <array>
#include <deque>
#include <cstdint>
#include <cmath>
#include <algorithm>
#include <optional>

// ============================================================================
// 基础数学类型（独立于引擎，方便跨平台测试）
// ============================================================================

struct Vec3 {
    float x, y, z;

    Vec3() : x(0), y(0), z(0) {}
    Vec3(float x, float y, float z) : x(x), y(y), z(z) {}

    Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
    Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }

    float Dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
    float Length() const { return std::sqrt(x * x + y * y + z * z); }
    Vec3 Normalized() const {
        float len = Length();
        return len > 0.0001f ? *this * (1.0f / len) : Vec3{0, 0, 0};
    }
    float Distance(const Vec3& o) const { return (*this - o).Length(); }
};

struct Quat {
    float x, y, z, w;
    Quat() : x(0), y(0), z(0), w(1) {}
};

// ============================================================================
// 快照数据
// ============================================================================

struct PlayerSnapshot {
    uint32_t tick = 0;           // 服务器 tick 号
    Vec3     position;           // 世界坐标
    Vec3     velocity;           // 速度（用于插值和外推）
    Quat     rotation;
    float    capsuleHalfHeight = 0.9f;
    float    capsuleRadius = 0.3f;
    bool     valid = false;      // 此槽位是否有有效数据
};

// ============================================================================
// 射击消息
// ============================================================================

struct ShotMessage {
    int      shooter_id;
    uint32_t client_tick;        // 客户端扣扳机时的本地 tick
    Vec3     shoot_origin;
    Vec3     shoot_direction;     // 单位向量
    float    max_range;
    int      weapon_id;
};

// ============================================================================
// 命中结果
// ============================================================================

struct HitResult {
    bool  hit = false;
    int   victim_id = -1;
    Vec3  hit_point;
    Vec3  hit_normal;
    float distance = 0.0f;
};

// ============================================================================
// 环形历史缓冲区（缓存友好版本）
// ============================================================================
// 设计要点：
// - 使用固定大小的预分配数组，避免运行时堆分配
// - 每个玩家有一整块连续的快照数组（cache line 友好）
// - 使用取模运算定位槽位：index = tick % capacity
// - 快照的时间跨度 = capacity / tickrate 秒

class HistoryBuffer {
public:
    /// @param max_players   最大玩家数
    /// @param capacity      每个玩家保存的快照数量（如 tickrate=60, 存1秒 → 60）
    HistoryBuffer(int max_players, uint32_t capacity)
        : m_capacity(capacity)
        , m_maxPlayers(max_players)
    {
        // 预分配所有内存：二维数组展平为一维
        // [player0_snap0, player0_snap1, ..., player1_snap0, player1_snap1, ...]
        m_buffer.resize(max_players * capacity);
        m_heads.resize(max_players, 0);
    }

    /// 记录当前 tick 的所有玩家快照。
    /// 在每帧物理模拟完成后、处理射击前调用。
    void RecordSnapshot(uint32_t tick,
                        const Vec3* positions,
                        const Vec3* velocities,
                        const Quat* rotations,
                        int playerCount)
    {
        for (int i = 0; i < playerCount && i < m_maxPlayers; ++i) {
            uint32_t idx = tick % m_capacity;
            auto& snap = m_buffer[i * m_capacity + idx];
            snap.tick     = tick;
            snap.position = positions[i];
            snap.velocity = velocities[i];
            snap.rotation = rotations[i];
            snap.valid    = true;
            m_heads[i]    = tick;
        }
    }

    /// 获取插值后的快照。
    /// 如果目标 tick 没有精确匹配的快照，在前后两个快照间线性插值。
    std::optional<PlayerSnapshot> GetInterpolated(int playerId, uint32_t targetTick) const
    {
        if (playerId < 0 || playerId >= m_maxPlayers)
            return std::nullopt;

        uint32_t headTick = m_heads[playerId];
        if (headTick == 0)
            return std::nullopt;

        // 检查目标是否在历史窗口内
        uint32_t tickAge = headTick - targetTick;
        if (tickAge > m_capacity || targetTick > headTick)
            return std::nullopt;

        // 尝试精确匹配
        size_t baseOffset = playerId * m_capacity;
        uint32_t exactIdx = targetTick % m_capacity;
        const auto& exact = m_buffer[baseOffset + exactIdx];
        if (exact.valid && exact.tick == targetTick)
            return exact;

        // 搜索前后最近的快照
        const PlayerSnapshot* before = nullptr;
        const PlayerSnapshot* after  = nullptr;
        uint32_t beforeTick = 0, afterTick = 0;

        // 向后搜索
        for (uint32_t t = targetTick; t + m_capacity > headTick && t > 0; --t) {
            const auto& snap = m_buffer[baseOffset + (t % m_capacity)];
            if (snap.valid && snap.tick <= targetTick) {
                before = &snap;
                beforeTick = t;
                break;
            }
        }

        // 向前搜索
        for (uint32_t t = targetTick + 1; t <= headTick; ++t) {
            const auto& snap = m_buffer[baseOffset + (t % m_capacity)];
            if (snap.valid && snap.tick >= targetTick) {
                after = &snap;
                afterTick = t;
                break;
            }
        }

        if (!before && !after) return std::nullopt;
        if (!after)  return *before;
        if (!before) return *after;
        if (beforeTick == afterTick) return *before;

        // 线性插值
        float t = float(targetTick - beforeTick) / float(afterTick - beforeTick);
        PlayerSnapshot result;
        result.tick     = targetTick;
        result.position = before->position + (after->position - before->position) * t;
        result.velocity = before->velocity + (after->velocity - before->velocity) * t;
        result.capsuleHalfHeight = before->capsuleHalfHeight;
        result.capsuleRadius     = before->capsuleRadius;
        result.valid    = true;

        // 旋转：简化版线性插值（生产代码应使用 Slerp）
        result.rotation.x = before->rotation.x + (after->rotation.x - before->rotation.x) * t;
        result.rotation.y = before->rotation.y + (after->rotation.y - before->rotation.y) * t;
        result.rotation.z = before->rotation.z + (after->rotation.z - before->rotation.z) * t;
        result.rotation.w = before->rotation.w + (after->rotation.w - before->rotation.w) * t;

        return result;
    }

    uint32_t GetHeadTick(int playerId) const {
        return (playerId >= 0 && playerId < m_maxPlayers) ? m_heads[playerId] : 0;
    }

private:
    uint32_t m_capacity;
    int      m_maxPlayers;
    std::vector<PlayerSnapshot> m_buffer; // 展平的一维数组
    std::vector<uint32_t>       m_heads;  // 每个玩家最新 tick
};

// ============================================================================
// 回退系统：执行服务端回退命中判定
// ============================================================================

class RewindSystem {
public:
    RewindSystem(int maxPlayers, uint32_t tickRate,
                 float historySeconds = 1.0f, float maxLagMs = 500.0f)
        : m_history(maxPlayers, uint32_t(tickRate * historySeconds))
        , m_tickRate(tickRate)
        , m_maxLagCompensationMs(maxLagMs)
        , m_maxPlayers(maxPlayers)
    {
        m_playerPositions.resize(maxPlayers, Vec3{});
        m_playerVelocities.resize(maxPlayers, Vec3{});
        m_playerRotations.resize(maxPlayers, Quat{});
    }

    /// 每 tick 调用：记录快照 + 处理射击。
    void OnTick(uint32_t currentTick) {
        // 1. 记录当前世界状态快照
        m_history.RecordSnapshot(currentTick,
                                  m_playerPositions.data(),
                                  m_playerVelocities.data(),
                                  m_playerRotations.data(),
                                  m_maxPlayers);
        // 2. 处理待处理的射击
        ProcessShots(currentTick);
    }

    /// 网络层收到射击消息时调用。
    void EnqueueShot(const ShotMessage& shot) {
        m_pendingShots.push_back(shot);
    }

    /// 设置玩家在当前 tick 的位置（由物理模拟更新）。
    void SetPlayerState(int playerId, const Vec3& pos, const Vec3& vel, const Quat& rot) {
        if (playerId >= 0 && playerId < m_maxPlayers) {
            m_playerPositions[playerId] = pos;
            m_playerVelocities[playerId] = vel;
            m_playerRotations[playerId] = rot;
        }
    }

private:
    HistoryBuffer          m_history;
    uint32_t               m_tickRate;
    float                  m_maxLagCompensationMs;
    int                    m_maxPlayers;

    std::vector<Vec3>      m_playerPositions;  // 当前真实位置
    std::vector<Vec3>      m_playerVelocities;
    std::vector<Quat>      m_playerRotations;

    std::deque<ShotMessage> m_pendingShots;

    /// 处理所有待处理的射击。
    void ProcessShots(uint32_t currentTick) {
        while (!m_pendingShots.empty()) {
            ShotMessage shot = m_pendingShots.front();
            m_pendingShots.pop_front();

            HitResult result = ProcessShot(shot, currentTick);
            if (result.hit) {
                ApplyDamage(shot, result);
            }
            // 将结果发送给客户端...
        }
    }

    /// 处理单个射击：核心回退逻辑。
    HitResult ProcessShot(const ShotMessage& shot, uint32_t currentTick) {
        // 1. 计算回退 tick
        uint32_t rewindTick = shot.client_tick;

        // 2. 安全检查：回退窗口
        uint32_t tickAge = currentTick - rewindTick;
        float ageMs = float(tickAge) / float(m_tickRate) * 1000.0f;
        if (ageMs > m_maxLagCompensationMs) {
            return HitResult{}; // 超出补偿窗口，拒绝
        }

        // 3. 对每个潜在目标执行回退→检测→恢复
        HitResult bestHit;
        bestHit.distance = std::numeric_limits<float>::max();

        for (int victimId = 0; victimId < m_maxPlayers; ++victimId) {
            if (victimId == shot.shooter_id) continue;

            // 回退目标玩家
            auto snapshot = m_history.GetInterpolated(victimId, rewindTick);
            if (!snapshot.has_value()) continue;

            // 快速剔除：距离检查
            float approxDist = shot.shoot_origin.Distance(snapshot->position);
            if (approxDist > shot.max_range * 1.5f) continue;

            // 保存原始位置
            Vec3 originalPos = m_playerPositions[victimId];
            Quat originalRot = m_playerRotations[victimId];

            // 临时设置历史位置
            m_playerPositions[victimId] = snapshot->position;
            m_playerRotations[victimId] = snapshot->rotation;

            // 射线 vs 胶囊体检测
            float hitDist;
            if (RayCapsuleIntersect(shot.shoot_origin, shot.shoot_direction,
                                     snapshot->position, snapshot->capsuleHalfHeight,
                                     snapshot->capsuleRadius, shot.max_range, hitDist))
            {
                if (hitDist < bestHit.distance) {
                    bestHit.hit       = true;
                    bestHit.victim_id = victimId;
                    bestHit.distance  = hitDist;
                    bestHit.hit_point = shot.shoot_origin + shot.shoot_direction * hitDist;
                    bestHit.hit_normal = (bestHit.hit_point - snapshot->position).Normalized();
                }
            }

            // 恢复原始位置
            m_playerPositions[victimId] = originalPos;
            m_playerRotations[victimId] = originalRot;
        }

        return bestHit;
    }

    /// 射线 vs 胶囊体相交检测（简化版）。
    /// 胶囊体轴线从 base 到 base + (0, halfHeight*2, 0)。
    /// 详见 "Real-Time Collision Detection" 第5.3.2节。
    static bool RayCapsuleIntersect(const Vec3& rayOrigin, const Vec3& rayDir,
                                     const Vec3& capsuleCenter, float halfHeight,
                                     float radius, float maxRange, float& outDist)
    {
        // 胶囊体底端和顶端
        Vec3 base = capsuleCenter - Vec3{0, halfHeight, 0};
        Vec3 tip  = capsuleCenter + Vec3{0, halfHeight, 0};
        Vec3 axis = tip - base; // (0, 2*halfHeight, 0)
        float axisLen = axis.Length();

        // 简化为：射线 vs 沿轴线扫过的球体（capsule = 线段扫过的球体）
        // 步骤：找到射线上离胶囊体轴线最近的点
        Vec3  ba  = axis * (1.0f / axisLen); // 轴线单位向量
        Vec3  oc  = rayOrigin - base;

        float rayDotAxis = rayDir.Dot(ba);
        float ocDotAxis  = oc.Dot(ba);

        float a = 1.0f - rayDotAxis * rayDotAxis;
        float b = oc.Dot(rayDir) - ocDotAxis * rayDotAxis;
        float c = oc.Dot(oc) - ocDotAxis * ocDotAxis - radius * radius;
        float h = b * b - a * c;

        if (h < 0.0f) return false; // 射线未命中无限圆柱体

        h = std::sqrt(h);
        float t = (-b - h) / a;

        // 检查是否命中圆柱体的有限部分（在轴线两端之间）
        float y = ocDotAxis + t * rayDotAxis;

        if (y < 0.0f) {
            // 射线先击中底端球体
            Vec3 sphereCenter = base;
            Vec3 oc2 = rayOrigin - sphereCenter;
            float b2 = oc2.Dot(rayDir);
            float c2 = oc2.Dot(oc2) - radius * radius;
            float h2 = b2 * b2 - c2;
            if (h2 < 0.0f) return false;
            t = -b2 - std::sqrt(h2);
        }
        else if (y > axisLen) {
            // 射线先击中顶端球体
            Vec3 sphereCenter = tip;
            Vec3 oc2 = rayOrigin - sphereCenter;
            float b2 = oc2.Dot(rayDir);
            float c2 = oc2.Dot(oc2) - radius * radius;
            float h2 = b2 * b2 - c2;
            if (h2 < 0.0f) return false;
            t = -b2 - std::sqrt(h2);
        }

        if (t < 0.0f || t > maxRange) return false;

        outDist = t;
        return true;
    }

    void ApplyDamage(const ShotMessage& shot, const HitResult& result) {
        // 伤害处理：根据武器、命中部位计算伤害
        // 生产代码需要包含：爆头倍率、距离衰减、护甲减伤等
    }
};
```

### 2.3 Lua: 简易回退实现 — 轻量级服务端

以下 Lua 实现适合嵌入 C/C++ 游戏服务器（如 skynet 框架），展示延迟补偿的核心逻辑。

```lua
-- lag_compensation.lua — Lua 服务端延迟补偿实现
-- 适用: skynet / 自定义 C-Lua 混合服务器
-- 依赖: 3D 数学库（向量运算需自行实现或绑定 C 库）

local LagCompensation = {}
LagCompensation.__index = LagCompensation

-- ============================================================================
-- 构造函数
-- ============================================================================

function LagCompensation.new(max_players, tickrate, history_seconds, max_lag_ms)
    local self = setmetatable({}, LagCompensation)
    self.max_players = max_players
    self.tickrate = tickrate or 60
    self.max_lag_ms = max_lag_ms or 500
    self.history_ticks = math.floor(tickrate * (history_seconds or 1.0))

    -- 每个玩家的历史快照：[playerId+1] = { {tick=N, pos={x,y,z}, vel={x,y,z}, ...}, ... }
    self.history = {}
    for i = 1, max_players do
        self.history[i] = {}  -- 使用数组 + table.remove 实现 FIFO（简单但非最优）
    end

    -- 待处理的射击队列
    self.pending_shots = {}

    -- 玩家当前真实位置
    self.positions = {}
    self.velocities = {}

    return self
end

-- ============================================================================
-- 每 tick 调用：保存快照 + 处理射击
-- ============================================================================

function LagCompensation:OnTick(current_tick)
    -- 1. 保存当前所有玩家位置快照
    self:_RecordSnapshot(current_tick)

    -- 2. 处理待处理射击
    self:_ProcessShots(current_tick)

    -- 3. 清理过期快照
    self:_CleanupHistory(current_tick)
end

-- 设置玩家位置（由物理模拟调用）
function LagCompensation:SetPlayerState(player_id, pos_x, pos_y, pos_z, vel_x, vel_y, vel_z)
    local idx = player_id + 1
    self.positions[idx] = {x = pos_x, y = pos_y, z = pos_z}
    self.velocities[idx] = {x = vel_x, y = vel_y, z = vel_z}
end

-- 接收客户端射击消息
function LagCompensation:EnqueueShot(msg)
    -- msg: { shooter_id, client_tick, origin={x,y,z}, dir={x,y,z}, max_range, weapon_id }
    table.insert(self.pending_shots, msg)
end

-- ============================================================================
-- 内部方法
-- ============================================================================

function LagCompensation:_RecordSnapshot(tick)
    for i = 1, self.max_players do
        local pos = self.positions[i]
        if pos then
            local snap = {
                tick      = tick,
                pos_x     = pos.x,
                pos_y     = pos.y,
                pos_z     = pos.z,
                vel_x     = (self.velocities[i] or {}).x or 0,
                vel_y     = (self.velocities[i] or {}).y or 0,
                vel_z     = (self.velocities[i] or {}).z or 0,
            }
            table.insert(self.history[i], snap)

            -- 限制历史长度
            while #self.history[i] > self.history_ticks do
                table.remove(self.history[i], 1)
            end
        end
    end
end

function LagCompensation:_ProcessShots(current_tick)
    local processed = 0
    for _, shot in ipairs(self.pending_shots) do
        -- 射击可能已经被之前处理的某个射击"消费"了（玩家死亡等情况）
        local result = self:_ProcessSingleShot(shot, current_tick)
        if result.hit then
            self:_ApplyDamage(shot, result)
        end
        processed = processed + 1
    end
    -- 清空队列
    for i = 1, processed do
        table.remove(self.pending_shots, 1)
    end
end

function LagCompensation:_ProcessSingleShot(shot, current_tick)
    -- 1. 回退 tick
    local rewind_tick = shot.client_tick

    -- 2. 安全检查：补偿窗口
    local tick_age = current_tick - rewind_tick
    local age_ms = (tick_age / self.tickrate) * 1000
    if age_ms > self.max_lag_ms then
        return { hit = false, victim_id = -1 }
    end

    -- 3. 遍历潜在目标
    local best_hit = { hit = false, victim_id = -1, distance = math.huge }

    for player_id = 0, self.max_players - 1 do
        if player_id ~= shot.shooter_id then
            local snap = self:_GetSnapshotAt(player_id, rewind_tick)
            if snap then
                -- 快速距离剔除
                local dx = shot.origin.x - snap.pos_x
                local dy = shot.origin.y - snap.pos_y
                local dz = shot.origin.z - snap.pos_z
                local dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                if dist <= shot.max_range * 1.5 then
                    -- 执行回退后的碰撞检测
                    local hit_info = self:_RayVsPlayer(
                        shot.origin, shot.dir, shot.max_range,
                        snap.pos_x, snap.pos_y, snap.pos_z
                    )
                    if hit_info and hit_info.distance < best_hit.distance then
                        best_hit = {
                            hit       = true,
                            victim_id = player_id,
                            distance  = hit_info.distance,
                            hit_point = hit_info.point,
                            hit_normal = hit_info.normal,
                        }
                    end
                end
            end
        end
    end

    return best_hit
end

-- 获取玩家在目标 tick 的插值快照
function LagCompensation:_GetSnapshotAt(player_id, target_tick)
    local hist = self.history[player_id + 1]
    if not hist or #hist == 0 then
        return nil
    end

    -- 检查目标是否在范围内
    local oldest = hist[1].tick
    local newest = hist[#hist].tick
    if target_tick < oldest or target_tick > newest then
        return nil
    end

    -- 二分搜索找最近快照
    local lo, hi = 1, #hist
    while lo < hi do
        local mid = math.floor((lo + hi) / 2)
        if hist[mid].tick < target_tick then
            lo = mid + 1
        else
            hi = mid
        end
    end

    -- 精确匹配
    if hist[lo].tick == target_tick then
        local s = hist[lo]
        return { pos_x = s.pos_x, pos_y = s.pos_y, pos_z = s.pos_z }
    end

    -- 线性插值（lo 是第一个 ≥ target_tick 的快照）
    local after = hist[lo]
    local before = hist[lo - 1]
    if not before then
        return { pos_x = after.pos_x, pos_y = after.pos_y, pos_z = after.pos_z }
    end

    local t = (target_tick - before.tick) / (after.tick - before.tick)
    return {
        pos_x = before.pos_x + (after.pos_x - before.pos_x) * t,
        pos_y = before.pos_y + (after.pos_y - before.pos_y) * t,
        pos_z = before.pos_z + (after.pos_z - before.pos_z) * t,
    }
end

-- 射线 vs 球体碰撞（简化版玩家碰撞检测）
-- 玩家的简化碰撞体：半径 0.35m 的球体（中心在 position + (0, 0.9, 0)）
function LagCompensation:_RayVsPlayer(origin, dir, max_range, px, py, pz)
    -- 玩家球心（胶囊体中心）
    local cx, cy, cz = px, py + 0.9, pz
    local radius = 0.35

    -- 射线方程: P = origin + t * dir, t ≥ 0
    -- 球体方程: |P - C|² = r²
    -- 代入得: |origin + t*dir - C|² = r²
    local oc_x = origin.x - cx
    local oc_y = origin.y - cy
    local oc_z = origin.z - cz

    local a = dir.x*dir.x + dir.y*dir.y + dir.z*dir.z  -- 应为 1.0（dir 是单位向量）
    local b = 2.0 * (oc_x*dir.x + oc_y*dir.y + oc_z*dir.z)
    local c = oc_x*oc_x + oc_y*oc_y + oc_z*oc_z - radius*radius

    local discriminant = b*b - 4*a*c
    if discriminant < 0 then
        return nil -- 无交点
    end

    -- 求最近的交点（较小的 t）
    local t = (-b - math.sqrt(discriminant)) / (2*a)
    if t < 0 then
        -- 射线起点在球体内部，尝试另一个交点
        t = (-b + math.sqrt(discriminant)) / (2*a)
        if t < 0 then
            return nil
        end
    end

    if t > max_range then
        return nil
    end

    -- 命中点
    local hit_x = origin.x + dir.x * t
    local hit_y = origin.y + dir.y * t
    local hit_z = origin.z + dir.z * t

    -- 法线（从球心指向命中点）
    local nx = hit_x - cx
    local ny = hit_y - cy
    local nz = hit_z - cz
    local nlen = math.sqrt(nx*nx + ny*ny + nz*nz)
    if nlen > 0.0001 then
        nx, ny, nz = nx/nlen, ny/nlen, nz/nlen
    end

    return {
        distance = t,
        point    = { x = hit_x, y = hit_y, z = hit_z },
        normal   = { x = nx, y = ny, z = nz },
    }
end

function LagCompensation:_ApplyDamage(shot, result)
    local victim_id = result.victim_id
    -- 计算伤害并应用到玩家
    -- 实际代码会调用玩家的:TakeDamage(damage, shot.weapon_id, result.hit_point)
end

function LagCompensation:_CleanupHistory(current_tick)
    local cutoff = current_tick - self.history_ticks
    for i = 1, self.max_players do
        local hist = self.history[i]
        while #hist > 0 and hist[1].tick < cutoff do
            table.remove(hist, 1)
        end
    end
end

-- ============================================================================
-- 使用示例
-- ============================================================================

--[[
    local lc = LagCompensation.new(16, 60, 1.0, 500)

    -- 服务器主循环:
    function server_tick(tick)
        -- 先运行物理（更新 lc.positions）
        lc:OnTick(tick)
    end

    -- 网络层收到射击消息:
    function on_shot_received(msg)
        lc:EnqueueShot(msg)
    end
]]

return LagCompensation
```

---

## 3. 真实引擎的延迟补偿实现

### 3.1 Source Engine / CS:GO 的延迟补偿

Source Engine（CS:GO 使用的引擎）是延迟补偿的**教科书级实现**。Valve 在 2001 年 Counter-Strike 1.6 时期首次引入，后经 CS:S、CS:GO 不断打磨。

#### 核心机制

CS:GO 的延迟补偿包含三个关键设计：

**① 历史位置缓存**

```
sv_maxunlag = 1.0  (秒) — 默认 1 秒，可在 0.2~1.0 之间调整

服务器在每个 tick (64/128Hz) 记录所有玩家的精确位置到历史缓冲区。
缓冲区的覆盖范围 = tickrate × sv_maxunlag。
64 tick × 1.0 秒 = 64 个历史快照。

历史缓存 = 环形数组，每个玩家每 tick 一个槽位。
```

**② 射击处理流程**

```
1. 客户端发送射击事件: CUserCmd { tick_count, viewangles, buttons, ... }
   - tick_count: 客户端在哪个 tick 扣的扳机
   - viewangles: 射击时的视角方向（确定射线方向）

2. 服务器收到消息:
   a) 计算回退时间: target_tick = cmd.tick_count
   b) 验证回退窗口: current_tick - target_tick < sv_maxunlag * tickrate
   c) 遍历所有玩家:
      - 保存该玩家的当前位置（m_vecOrigin, m_angRotation）
      - 恢复到 target_tick 时刻的位置
   d) 从射击者的视角方向发射射线
   e) 如果射线命中某个玩家的碰撞体 → 记录命中
   f) 恢复所有玩家的位置

3. 伤害处理:
   - 根据命中部位（头/胸/腹/四肢）计算伤害倍率
   - 应用护甲减伤
   - 发送命中事件给客户端
```

**③ `sv_showimpacts` 调试**

CS:GO 提供了 `sv_showimpacts` 命令，在服务器上可视化命中判定：

- `sv_showimpacts 1`: 显示**服务器端**的命中点（蓝色）
- `sv_showimpacts 2`: 显示**客户端**的命中点（红色）

当蓝色和红色在同一位置时，延迟补偿工作正常。如果红色在玩家身上但蓝色在掩体上 → 延迟补偿失败或超出窗口。

#### CS:GO 的特殊处理

**爆头与延迟的平衡**：CS:GO 中爆头伤害极高（AWP 一枪秒杀）。高延迟玩家如果获得完整的延迟补偿，可能会产生"我在掩体后但还是被爆头了"的挫败感。Valve 的对策：

- `sv_maxunlag` 默认 1.0s（较长的补偿窗口，对高延迟玩家友好）
- 但同时配合**客户端预测**让掩体后的移动即时显示
- 被击中玩家看到"自己被爆头"时，已经是在他拉出掩体后的一瞬间——这种"被 peek 者优势"（Peeker's Advantage）是延迟补偿无法完全消除的

#### 面试要点

> **Q: CS:GO 如何防止高延迟玩家滥用延迟补偿进行"时光倒流射击"？**
>
> A: 三个方面：
> 1. `sv_maxunlag` 限制补偿窗口（默认 1 秒），超过的射击消息直接拒绝
> 2. 补偿只影响命中判定，不影响伤害计算——伤害仍然基于服务器当前世界状态（如护甲值）
> 3. 客户端射击频率受武器射速限制（`NextPrimaryAttack`），无法通过延迟制造"超频射击"

### 3.2 Valorant 的延迟补偿

Riot Games 的 Valorant 在 CS:GO 的基础上做了几项重要改进，以应对现代 FPS 对公平性的极致要求。

#### ① 128-tick 高频服务器

Valorant 所有服务器固定运行在 **128 tick**（每 7.8125ms 一个 tick）。这直接带来两个优势：

- **更精确的历史位置**：快照间隔从 15.6ms（64 tick）降到 7.8ms，历史插值误差减半
- **更小的回退窗口**：在相同的 `sv_maxunlag`（1 秒）内，Valorant 有 128 个快照，CS:GO 只有 64 个

#### ② 客户端-服务器时钟同步

Valorant 使用**精确的时钟同步**来消除 RTT 估计误差：

```
客户端发送每条消息时附带:
  - client_tick: 客户端本地 tick（由服务器校正过的时钟）
  - server_tick_echo: 客户端最后一次收到的服务器 tick（用于计算单向延迟）

服务器维护每个客户端的:
  - clock_offset: 客户端时钟 vs 服务器时钟的差值
  - smoothed_rtt: 指数平滑的 RTT 值（EWMA, α=0.1）

回退时间 = server_tick - smoothed_rtt/2 + clock_offset
而不是简单地使用 client_tick
```

#### ③ 动态缓冲补偿（Adaptive Buffering）

Valorant 不像 CS:GO 那样固定 1 秒补偿窗口，而是根据每个玩家的网络情况**动态调整**：

```
if rtt < 30ms:   max_rewind = 200ms  (低延迟，紧窗口)
if rtt 30-60ms:  max_rewind = 400ms
if rtt 60-100ms: max_rewind = 600ms
if rtt > 100ms:  max_rewind = 800ms (上限)
```

这确保低延迟玩家不会因为宽松的补偿窗口而被"过度补偿"，同时给予高延迟玩家合理补偿。

#### ④ 反作弊与延迟补偿的结合 (Vanguard)

Valorant 的反作弊系统 Vanguard 也会监控延迟补偿相关的异常行为：

- **回溯作弊 (Backtracking)**：外挂利用延迟补偿机制，故意使用旧的客户端 tick 来射击"过去的敌人"。Vanguard 检测异常的 tick 时差模式。
- **延迟伪造**：外挂报告虚假的高 RTT 来获取更长的补偿窗口。服务端通过第三方测量（服务器记录的收发包时间差）来交叉验证客户端报告的 RTT。

### 3.3 Unity Netcode for Entities 的 Server Rewind

Unity 的 Netcode for Entities（ECS Netcode）内置了对 Ghost（网络实体）的服务端回退支持，称为 **Server Rollback**。

#### 核心 API

```csharp
// 在 System 中启用回退命中判定
[WorldSystemFilter(WorldSystemFilterFlags.ServerSimulation)]
public partial struct HitScanSystem : ISystem
{
    public void OnUpdate(ref SystemState state)
    {
        // 1. 获取 CommandTarget 组件（玩家输入的视口方向）
        // 2. 获取 PhysicsWorld（包含所有碰撞体）
        // 3. 创建回退后的查询
        foreach (var (commandData, entity) in
                 SystemAPI.Query<RefRO<CommandData>>().WithAll<Simulate>().WithEntityAccess())
        {
            // 获取此命令对应的插值延迟（服务器到客户端的往返）
            var interpolationDelay = SystemAPI.GetComponent<CommandDataInterpolationDelay>(entity);

            // 获取回退后的 PhysicsWorld 快照
            // Unity ECS 的 Physics 系统支持通过 interpolationDelay 查询历史碰撞状态
            var physicsWorld = SystemAPI.GetSingleton<PhysicsWorldSingleton>();
            var collisionWorld = physicsWorld.CollisionWorld;

            // 使用 interpolationDelay 作为回退量进行射线检测
            // Netcode for Entities 内部已完成 Ghost 实体的位置回退
            var rayInput = new RaycastInput
            {
                Start = commandData.ValueRO.shootOrigin,
                End   = commandData.ValueRO.shootOrigin +
                        commandData.ValueRO.shootDirection * maxRange,
                Filter = CollisionFilter.Default
            };

            if (collisionWorld.CastRay(rayInput, out var hit))
            {
                // 命中处理
                // hit.Entity 是命中的 Ghost 实体
                // 此时碰撞体位置已经自动回退了 interpolationDelay 个 tick
            }
        }
    }
}
```

#### 与手写回退的区别

| 维度 | 手写回退 | Unity Netcode for Entities |
|------|---------|---------------------------|
| 历史快照 | 自己管理环形缓冲区 | ECS Ghost 系统自动保存历史 |
| 回退触发 | 手动计算回退 tick | `CommandDataInterpolationDelay` 自动提供 |
| 碰撞检测 | 手动执行射线检测 | 使用 PhysicsWorld 的快照查询 |
| 位置插值 | 自己写线性/曲线插值 | Ghost 的 `SmoothingAction` 处理 |
| 复杂度 | 高（200+ 行代码） | 低（框架封装） |
| 灵活性 | 完全自定义 | 受框架设计约束 |

---

## 4. 延迟补偿的边界情况

### 4.1 被击中的玩家也在移动

这是延迟补偿最常见的复杂场景：

```
场景：
T0:  玩家A在位置X，向掩体后移动（速度 5m/s）
T1:  玩家B从远处射击A。B的RTT=200ms，B的屏幕上A在位置X附近
T2:  射击消息到达服务器。回退到 T_revind = T2 - 100ms
     此时A的真实位置已经移动了 100ms × 5m/s = 0.5m（可能已经在掩体后）

回退判定：
  - 将A移回 T_rewind 时的位置（约在X附近）
  - 射线检测 → 命中A的历史位置
  - 伤害生效 → A被击中

问题："我在掩体后怎么还被打中了？？"
```

**解决方案**：

**方案 A：全量回退（CS:GO 做法）** — 接受这种"不公平"。

CS:GO 的设计哲学是"射击者的屏幕优先"。如果你在射击者的屏幕上被瞄准了，你就该被击中——即使你实际上已经跑到了掩体后面。这是一种刻意的设计选择，理由：
- 射击者的体验 > 被射击者的体验（射击需要主动技巧，被射击是被动的）
- 如果取消这种补偿，高延迟玩家将完全无法命中移动目标

**方案 B：限制回退距离（Valorant 做法）** — 设定最大回退距离。

```csharp
// 如果玩家在回退窗口内移动了超过阈值，拒绝这次射击
float rewindDistance = Vector3.Distance(currentPosition, rewindPosition);
if (rewindDistance > MAX_REWIND_DISTANCE) // 如 0.5m
{
    // 拒绝：玩家移动太快，回退会产生不公平的"掩体后命中"
    return new HitResult { Hit = false };
}
```

**方案 C：受害者视角验证（Overwatch 曾使用）** — 双重判定。

既从射击者视角判定，也从受害者视角判定。只有两个视角都认为"合理"时，伤害才生效。

### 4.2 多个射击者不同延迟

```
玩家A (RTT=30ms) 和 玩家B (RTT=200ms) 同时射击 玩家C。

服务器处理顺序：
  1. 先收到A的消息（因延迟低）→ 回退到 T-15ms → 命中C → C的HP从100降到75
  2. 后收到B的消息（因延迟高）→ 回退到 T-100ms → 也命中C → C的HP从75降到50

问题：B的回退时间比A早85ms。在B回退的世界中，C还没有被A击中。
      但服务器对A的伤害已经生效了。顺序变成了：
      实际物理时间: A先命中C → B后命中C
      回退视角:     B的子弹在A之前就"到达"了C
```

这在游戏性上通常**不是问题**——因为：
1. 两次射击都"合理地"命中了射击者屏幕上的目标
2. 延迟补偿的本意就是让每个射击者以自己的视角判定
3. 最终结果 C 受到两次伤害是合理的（两发子弹确实都"命中"了）

但在极端情况下（如 C 本应被 A 的射击推离原位从而躲开 B 的射击），需要引入 **射击因果链**——后续射击的回退判定需要考虑先前已处理的射击结果（如位置改变、死亡等）。

### 4.3 掩体边缘的判定

这是延迟补偿**最常见的玩家投诉来源**。

```
场景：
  玩家A在掩体边缘反复 peek（快速探出、缩回）
  玩家B（高延迟）瞄准掩体边缘

  T0:  A探出掩体 → B的屏幕显示A在掩体外 → B开枪
  T1:  A缩回掩体
  T2:  服务器收到B的射击 → 回退到T0 → A在掩体外 → 命中！

  但A从自己的视角看：已经缩回掩体了，却被"穿墙"打死。
```

**解决方案**：

**① 客户端预测 + 延迟补偿的协同**

A 的客户端上，peek 缩回是**即时响应**的（客户端预测自己的移动）。所以 A 在屏幕上看到自己缩回掩体后，即使被服务器回退判定为在掩体外被击中，A 收到"你被命中"的消息也会比实际缩回晚约 RTT/2。这段时间差在 A 看来是："我已经躲好了，但延迟让我被穿墙了"。

Valorant 对此的缓解是**低延迟优先匹配**——尽量让同一对局的玩家延迟接近。

**② 限制 peek 速度**

一些游戏在掩体附近降低移动加速度（"黏滞掩体"效果），减少"peek→缩回"的速度差，缩小回退判定偏差。

**③ 预测误差的硬截断**

```csharp
// 如果回退位置与当前位置差距过大（玩家正在快速移动/peek），
// 对回退位置做"钳制"——不能退回超过某一半速移动距离
float maxAllowedRewindDist = (currentTick - rewindTick) * MAX_SPEED * 0.5f;
Vector3 clampedRewindPos = Vector3.MoveTowards(currentPos, rewindPos, maxAllowedRewindDist);
```

---

## 5. 练习

### 练习 1: 基础 — 实现简易服务端回退 (45min)

基于上述 C# 代码骨架，完成以下任务：

1. **实现 HistoryBuffer 的单元测试**：
   - 写入 120 个 tick 的快照（模拟 2 秒 @ 60 tick）
   - 验证 `GetInterpolatedPose` 在精确匹配、插值匹配、超出范围时的行为
   - 验证环形覆写：第 121 个快照正确覆盖第 1 个

2. **实现 ProcessSingleShot 的完整版本**：
   - 添加世界静态几何体的射线检测（墙壁遮挡判定）
   - 如果射线先碰到墙壁再碰到玩家 → 未命中
   - 验证：射击者→墙壁→目标玩家 时判定为未命中

3. **测试不同延迟下的命中率**：
   - 场景：目标玩家以固定速度直线移动，射击者瞄准目标位置
   - 模拟 RTT=0ms, 50ms, 100ms, 200ms, 500ms
   - 对比"有延迟补偿"和"无延迟补偿"的命中率

### 练习 2: 进阶 — 多射击者并发回退 (60min)

1. **实现并发射击的确定性处理**：
   - 3 个射击者同时射击同一个目标，延迟各不相同
   - 确保无论射击消息的到达顺序如何，最终伤害结果一致（同一 tick 内的射击按 shooter_id 排序处理）
   - 验证：重新排序消息不影响最终所有玩家的 HP

2. **实现"先杀后死"规则**：
   - 如果射击者 A 在 tick N 杀死了目标 C
   - 射击者 B 在同一 tick 也射击了 C（但 B 的回退时间更早）
   - 规则：如果 C 在被 A 击杀后立即死亡，B 的射击不应再对 C 造成伤害（因为 C 已经死了）
   - 实现这个规则并测试

3. **分析回退窗口大小的权衡**：
   - 固定所有玩家的 RTT=150ms，改变 `maxLagCompensationMs`（100, 200, 300, 500, 1000）
   - 记录每次的命中率、误判率（"掩体后命中"次数）
   - 写一段 200 字的分析：`sv_maxunlag` 取什么值最优？为什么？

### 练习 3: 挑战 — 完整的 FPS 命中小型 Demo (90min)

从头实现一个极简的 FPS 命中判定服务器（使用 Unity 或纯 C# 控制台）：

1. **服务器**（60 tick）：
   - 2 个玩家在 3D 空间中移动（简单的匀速直线 + 方向键）
   - 每个 tick 保存位置快照
   - 接收射击消息，执行回退命中判定
   - 打印每次射击的判定结果

2. **客户端模拟器**（独立进程，通过 UDP 通信）：
   - 2 个模拟客户端，各配置不同的延迟（--delay=30, --delay=150）
   - 每个客户端在本地屏幕上渲染简单场景（可以用 Debug.DrawRay 或 ASCII 渲染）
   - 扣扳机时发送射击消息（附带 clientTick）
   - 收到命中结果后打印

3. **验证实验**：
   - **实验 A**：目标以 3m/s 横向移动，距离 30m，射击者瞄准目标当前屏幕位置
     - RTT=0ms 时，命中率 ≈ 100%
     - RTT=150ms 时，**无延迟补偿**命中率 ≈ 0%（子弹打到目标身后的空气）
     - RTT=150ms 时，**有延迟补偿**命中率 ≈ 95%+
   
   - **实验 B**：目标在掩体后反复 peek（探出 0.5s → 缩回 0.5s）
     - 高延迟射击者（RTT=200ms）在目标缩回瞬间射击
     - 观察服务器端判定结果——是否出现了"掩体后命中"
     - 如果出现，你能通过什么机制减少这种情况？

4. **性能分析**：
   - 测量每 tick 的处理时间（回退 + 射线检测）
   - 测量历史缓冲区的内存占用
   - 如果玩家数从 2 增加到 16，内存和 CPU 的增长如何？

---

## 6. 扩展阅读

### 必读文章（英文）

- **Valve Developer Wiki — Lag Compensation**
  https://developer.valvesoftware.com/wiki/Lag_compensation
  — Source Engine 延迟补偿的官方文档，CS:GO 实现的基础

- **Gaffer On Games — Networked Physics**
  https://gafferongames.com/post/networked_physics/
  — Glen Fiedler 关于网络物理的经典系列，含延迟补偿的数学推导

- **Riot Games Tech Blog — Valorant's 128-Tick Servers**
  https://technology.riotgames.com/
  — Riot 关于 Valorant 网络架构的技术文章

- **Unreal Engine — Lag Compensation in ShooterGame**
  — Unreal Engine 示例项目 ShooterGame 包含了完整的延迟补偿实现（C++ 源码）

### 必读文章（中文）

- **腾讯游戏学院: FPS 游戏中的延迟补偿技术研究**
  深入分析 CS:GO 的延迟补偿策略及对游戏性的影响

- **知乎: Valorant 的 Netcode 为什么"感觉"比 CSGO 好？**
  讨论 128 tick、时钟同步、动态缓冲对体感的影响

### 相关教程

- 本计划第 13 节：**状态同步核心原理：权威服务器模型** — 延迟补偿依赖于权威服务器架构
- 本计划第 14 节：**客户端预测** — 延迟补偿的前置概念，理解客户端和服务端的时间差异
- 本计划第 15 节：**服务端和解** — 延迟补偿 + 服务端和解的协同工作
- 本计划第 16 节：**实体插值** — 与延迟补偿正交但互补的渲染技术

### 开源参考

- **Unity Netcode for Entities (GitHub: Unity-Technologies/EntityComponentSystemSamples)**
  内含 Netcode Samples 项目，展示 Server Rollback 的完整用法

- **Source SDK (GitHub: ValveSoftware/source-sdk-2013)**
  CS:GO 引擎的源代码，`lagcompensation.cpp` 是延迟补偿的核心实现

- **Overwatch Netcode Analysis (YouTube: Battle(non)sense)**
  详细的守望先锋网络架构分析，含延迟补偿的可视化对比

---

## 常见陷阱

### 陷阱 1: 回退后忘记更新物理场景

**错误**：直接修改 `Transform.position` 后立即调用 `Physics.Raycast`。

**为什么错**：在 Unity 中，修改 `Transform.position` 不会自动更新 `Collider` 的包围盒和相关物理加速结构。射线检测使用的是旧的碰撞体位置。

**正确做法**：
```csharp
// Unity 中必须调用此方法同步 Transform 和 PhysX 碰撞体
Physics.SyncTransforms();

// 或者直接使用 Rigidbody.position（这会同步更新碰撞体）
rigidbody.position = rewindPos;
```
在 Unreal Engine 中，使用 `UPrimitiveComponent::SetWorldLocation()` 会自动更新物理表示。

### 陷阱 2: 回退所有玩家而不仅仅是潜在目标

**错误**：对每个射击，回退所有在线玩家的位置。

**为什么错**：如果场景中有 64 个玩家，每个 tick 处理 20 个射击，你每 tick 要回退/恢复 1280 个玩家位置——CPU 开销极大且完全无意义（大多数玩家根本不在射线上）。

**正确做法**：
1. 先做空间粗筛：网格哈希 / 八叉树 / k-d tree
2. 只回退射线穿过的空间分区内的玩家
3. 对距离明显超出射程的玩家直接跳过

### 陷阱 3: RTT/2 假设不成立

**错误**：直接使用 `rewindTick = currentTick - avgRTT/2`。

**为什么错**：RTT 的两段（上行+下行）在网络拥塞时可能不对称。移动网络的上行延迟通常远大于下行延迟（用户下载快、上传慢）。RTT/2 假设对称网络，在 4G/WiFi 下常有 30~50% 误差。

**正确做法**：
- 让客户端在射击消息中携带**客户端本地时间戳**（已经过服务器时钟校正）
- 服务器使用 `clientTick` 作为回退目标，而非用 RTT/2 估算
- 实现双向时钟同步（NTP-lite）：服务器定期发送 `{serverTick, clientTick}` 响应，客户端维护 `clock_offset`

### 陷阱 4: 静态几何体在回退中不被考虑

**错误**：只回退了玩家位置，但用"当前"的世界几何体做射线检测。

**为什么错**：虽然大多数情况下世界几何体是静态的（不随时间变化），但有例外：
- 可破坏的掩体 / 门
- 动态升降平台
- 移动的车辆 / 载具

如果场景包含动态几何体，它也需要参与回退。

**正确做法**：将动态几何体视为"特殊的玩家"，同样记录历史位置，回退时一并处理。

### 陷阱 5: 补偿窗口过大导致的"时光倒流射击"

**错误**：`sv_maxunlag` 设置过大（如 5 秒）。

**为什么错**：
- 高延迟玩家可以瞄准 5 秒前敌人暴露的位置，此时敌人早已移动到完全不同的地方
- 被击中者体验极差："我在安全区域待了很久怎么突然死了？"
- 外挂可以滥用此机制：故意报告极大的 clientTick 来实现"回溯射击"

**正确做法**：
- 补偿窗口不超过 ~1 秒（`sv_maxunlag = 1.0`）
- 对超过窗口的射击直接拒绝（而非降级为无补偿判定）
- 限制 clientTick 的偏移范围——如果报告的 clientTick 比 serverTick 老太多，标记为可疑

### 陷阱 6: 忘记处理玩家死亡/重生的边界

**错误**：在回退过程中，目标玩家的历史位置跨越了其死亡/重生时刻。

**场景**：
```
T0: 玩家A在位置X被杀（HP=0）
T1-T5: A处于死亡状态（不可射击）
T6: A在重生点重生
T7: 高延迟玩家B的射击到达，B的 clientTick = T2

问题：T2 时 A 已经死了，A 的碰撞体应该被禁用。
     但历史缓冲区中 T2 的快照可能显示 A 仍在位置X（未被清理）。
     回退判定可能"复活"已死亡的玩家来挡子弹。
```

**正确做法**：
- 历史快照中存储 `IsAlive` 状态
- 回退时检查碰撞体是否有效（IsAlive && IsSpawned）
- 死亡玩家的历史快照应标记为"不可碰撞"或直接被跳过

### 陷阱 7: 延迟补偿与命中验证的顺序错误

**错误**：先执行无补偿的判定，如果未命中才尝试有补偿的判定。

**为什么错**：这导致双倍的 CPU 开销（两次射线检测），且逻辑复杂度增加——如果第一次"未命中但穿过了玩家历史位置附近的区域"，第二次命中后会产生不一致。

**正确做法**：
- 延迟补偿是默认开启的，所有射击都走回退→检测→恢复流程
- 不存在"先无补偿、后有补偿"的 fallback 路径
- 唯一的 fallback 是补偿窗口超限时直接拒绝
