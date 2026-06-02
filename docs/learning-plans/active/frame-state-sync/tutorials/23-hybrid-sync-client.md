# 混合同步客户端实现：双通道架构

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [21-状态同步服务端架构](21-state-sync-server.md), [12-帧同步进阶](12-lockstep-advanced.md)

---

## 1. 概念讲解

### 1.1 为什么需要混合同步客户端？

如果你已经学完了帧同步（1-12 节）和状态同步（13-21 节），你应该已经能独立实现两种独立的网络同步系统。但现实中，**没有哪款大型游戏只使用一种同步方式**。

以《合金弹头：觉醒》（2023，腾讯天美）为例：
- 玩家的**移动和射击**用帧同步——因为弹幕射击对操作反馈要求极高，延迟必须控制在 16-33ms 以内
- 怪物的**AI 行为**用状态同步——因为怪物数量多（几十个）、不需要逐帧精确，服务器周期性下发位置即可
- 玩家的**属性值**（等级、装备、Buff）用状态同步——这些是低频变更的 KV 数据，不需要帧同步的逐帧一致性开销

再看《守望先锋》：
- 玩家移动/射击 → 客户端预测 + 服务器和解（状态同步变体）
- 技能释放（如源氏 Shift 冲刺）→ **服务器立即下发状态更新**并附带权威修正
- 但某些**判定敏感的操作**（如法老之鹰的火箭弹预判轨迹）实际上有帧同步的味道——服务器在 60Hz Tick 上精确模拟弹道

混合架构的核心洞察：**不是所有实体都需要同一个同步策略。根据实体的实时性要求、修改频率、和可校验性来分通道。**

### 1.2 双通道架构全景

```
┌──────────────────────────────────────────────────────────────────────┐
│                         混合同步客户端                                  │
│                                                                      │
│  ┌───────────────────────────┐    ┌───────────────────────────────┐  │
│  │  Channel A: 帧同步通道      │    │  Channel B: 状态同步通道        │  │
│  │  ┌─────────┬────────────┐  │    │  ┌──────────┬──────────────┐  │  │
│  │  │ UDP     │ 30Hz 发送   │  │    │  │ RUDP/TCP │ 15Hz 收发    │  │  │
│  │  │ 最小 2B │ 最大 8B/帧  │  │    │  │ 100-500B │ 属性+事件    │  │  │
│  │  │ 无序列号 │ 帧号定位   │  │    │  │ 有序可靠  │ 可重传       │  │  │
│  │  └─────────┴────────────┘  │    │  └──────────┴──────────────┘  │  │
│  └───────────┬───────────────┘    └───────────┬───────────────────┘  │
│              │                                │                      │
│              │  帧指令 (输入)                    │  实体状态/事件        │
│              ▼                                ▼                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    HybridSyncManager                            │  │
│  │                  统一生命周期 + 帧号对齐                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │  │
│  │  │ Lockstep     │  │ StateSync    │  │ FrameNumberAlign     │  │  │
│  │  │ Channel      │  │ Channel      │  │ 帧号->服务器Tick映射   │  │  │
│  │  │ 管理         │  │ 管理         │  │                      │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │  │
│  └───────────────────────────┬────────────────────────────────────┘  │
│                              │                                       │
│              ┌───────────────┼───────────────┐                       │
│              ▼               ▼               ▼                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │LockstepEntity│  │ReplicatedEnt │  │ HybridEntity │               │
│  │ 帧同步驱动    │  │ 状态同步驱动  │  │ 混合驱动     │               │
│  │ (自己/队友)   │  │ (怪物/NPC)   │  │ (Boss)       │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      EntityRegistry                           │   │
│  │    统一的实体注册表: ID映射 + 类型标记 + 生命周期回调            │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**关键设计原则**：

1. **两个通道在物理上是独立的 Socket**。帧同步 Channel A 使用裸 UDP，不经过可靠层——因为它依赖帧号定位而非序列号。状态同步 Channel B 使用 RUDP（如 KCP/ENet）或 TCP，需要可靠有序传输。
2. **两个通道共享同一个逻辑时间基准**。帧号 N 对应服务器 Tick N，状态同步的数据包中携带 `ServerTick` 字段，客户端通过 `FrameNumberAlign` 将二者对齐。
3. **帧同步通道的帧等待不阻塞状态同步通道**。如果 Channel A 在等帧（缓冲不足），Channel B 继续处理状态更新——反之亦然。两个通道互不阻塞。
4. **服务器是最终权威**。当状态同步的数据和帧同步计算的结果冲突时，状态同步数据覆盖帧同步结果（服务器说了算）。

### 1.3 双通道的职责分工

| 维度 | Channel A (帧同步) | Channel B (状态同步) |
|:------|:-------------------|:---------------------|
| **传输协议** | UDP，不可靠 | RUDP (KCP/ENet) 或 TCP，可靠 |
| **发送频率** | 30-60Hz（每逻辑帧或每2帧） | 10-20Hz（周期性快照） |
| **单包大小** | 2-8 字节（几个 bit 的输入标记） | 100-500 字节（位置+属性+事件） |
| **丢包处理** | 冗余发送（UDP 自带） + 帧缓冲容忍 | 协议层重传（RUDP 保证） |
| **排序保证** | 不保证（通过帧号在应用层排序） | 协议层保证有序 |
| **典型内容** | 移动方向（2bit）、攻击标记（1bit）、技能ID（5bit） | 位置(x,y,z)、血量、Buff列表、AI行为ID |
| **驱动实体** | LockstepEntity（玩家控制的角色） | ReplicatedEntity（怪物/NPC/道具） |
| **延迟特征** | 帧缓冲延迟（3-5帧）+ 网络RTT/2 | 网络 RTT/2（无帧缓冲） + 插值延迟 |
| **反外挂** | 依赖哈希校验 + 操作回放检测 | 服务器权威天然防作弊 |

### 1.4 通道间的协调机制

混合架构中最棘手的不是单个通道的实现，而是**两个通道之间的协调**。以下是三个核心协调问题：

#### 问题 1：帧号对齐

帧同步使用"逻辑帧号"（从战斗开始计数 0, 1, 2, ...），状态同步使用"服务器时间戳"（毫秒）。这两个时间系统需要对齐。

```
服务器时间轴 ──────────────────────────────────────────────►
             0ms    100ms   200ms   300ms   400ms   500ms
             │       │       │       │       │       │
逻辑帧号:     F0      F3      F6      F9     F12     F15
                   (每 33ms 一帧 = 30Hz)

状态同步包:  [snap@t=0]      [snap@t=200]     [snap@t=400]
              ↓                ↓                ↓
客户端收到:   snap(t=0)       snap(t=200)     snap(t=400)
              │                │                │
映射到帧号:   F0               F6              F12
```

**对齐策略**：客户端在收到第一个帧同步包时记录 `baseTimestamp` 和 `baseFrame`，之后的映射公式：

```
serverFrameFromTimestamp(serverMs) = baseFrame + round((serverMs - baseTimestamp) / frameIntervalMs)
```

#### 问题 2：优先级仲裁

当状态同步的数据和帧同步计算的结果冲突时，谁优先？

```
场景：帧同步计算玩家 A 的位置是 (100, 0)
      状态同步下发的玩家 A 位置是 (98, 2) ← 服务器权威

仲裁规则：
┌─────────────────────────────────────────────────────────┐
│  IF 实体类型 == LockstepEntity AND 该局部玩家:             │
│      → 使用帧同步结果（本地预测优先）                       │
│  ELSE IF 状态同步数据比帧同步数据"更新"（ServerTick 更大）:  │
│      → 使用状态同步数据（服务器权威覆盖）                    │
│  ELSE:                                                   │
│      → 使用帧同步结果                                      │
└─────────────────────────────────────────────────────────┘
```

关键点：**本地玩家的操作反馈必须走帧同步预测路径**，否则输入延迟无法接受。但本地玩家的属性（血量、等级）仍服从服务器状态同步的覆盖——这是服务器权威的底线。

#### 问题 3：互不阻塞

帧同步通道的帧等待（缓冲不足时 hang 住）不能阻塞状态同步通道的数据处理。反之亦然。

```
HybridSyncManager.Update():
  ├─ ProcessChannelA()  // 帧同步：检查帧缓冲 → 推进逻辑帧 / 等待
  │   └─ 如果缓冲不足 → return（不阻塞 Channel B）
  ├─ ProcessChannelB()  // 状态同步：立即处理所有已到达的包
  │   └─ 解包 → 更新 EntityRegistry 中的 ReplicatedEntity
  └─ ResolveConflicts() // 冲突仲裁：决定每个实体的最终状态
```

### 1.5 实体分类与注册

混合同步客户端管理的实体分为三类：

```
                    ┌──────────────────────────┐
                    │       IEntity              │
                    │  + EntityId: uint         │
                    │  + EntityType: enum       │
                    │  + OnUpdate(frame): void  │
                    └──────────┬───────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ LockstepEntity  │  │ ReplicatedEntity│  │  HybridEntity   │
│                 │  │                 │  │                 │
│ 帧同步驱动       │  │ 状态同步驱动     │  │ 混合驱动         │
│ 每逻辑帧        │  │ 收到包时更新     │  │ 帧同步+状态覆盖  │
│ TickInput()     │  │ ApplyState()    │  │ TickInput()     │
│ 计算位置+碰撞   │  │ 直接设置位置    │  │  + 位置取值仲裁  │
│                 │  │ + 插值平滑      │  │                 │
│ 用于: 玩家角色  │  │ 用于: 怪物/NPC  │  │ 用于: Boss/关键 │
│ (自己+队友)     │  │ 道具/弹幕       │  │ 实体             │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**LockstepEntity**：位置和状态完全由帧同步逻辑引擎计算。输入来自 Channel A，确定性执行得出结果。典型例子：自己控制的角色、队友角色。

**ReplicatedEntity**：位置和状态完全由服务器通过 Channel B 下发。客户端不做任何物理/逻辑计算，只做插值平滑。典型例子：AI 怪物、掉落道具、弹幕子弹、环境物件。

**HybridEntity**：主体走帧同步，但特定属性（如 Boss 的当前阶段、血量的服务器权威值）由状态同步覆盖。这是最高级的实体类型，用于需要"帧同步的即时响应 + 服务器权威的反外挂"的双重保障场景。典型例子：Boss、PVP 中的对手、需要服务器校验的关键实体。

---

## 2. 代码示例

> **重要说明**：以下代码构建混合同步客户端的核心框架。HybridSyncManager 和 EntityRegistry 是新增代码；LockstepChannel 和 StateSyncChannel 展示如何复用第 08 节和第 18 节的代码。C++ 和 Lua 版本给出完整的通道管理实现。

### 2.1 HybridSyncManager.cs —— 混合管理器（~280行）

这是整个混合同步客户端的大脑。它管理两个通道的生命周期，维护帧号对齐，执行仲裁逻辑。

```csharp
// HybridSyncManager.cs
// 挂载在场景根节点上。依赖 LockstepChannel 和 StateSyncChannel。
// 职责：
//   1. 统一启动/停止两个通道
//   2. 帧号对齐 (逻辑帧 <-> 服务器 Tick)
//   3. 每帧调度两个通道的 Update
//   4. 冲突仲裁：决定 Lockstep 和 Replicated 实体的最终状态

using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 实体同步类型标记
/// </summary>
public enum EntitySyncType : byte
{
    Lockstep    = 0,  // 帧同步驱动：每逻辑帧 TickInput()
    Replicated  = 1,  // 状态同步驱动：收到包时 ApplyState()
    Hybrid      = 2,  // 混合驱动：帧同步执行 + 状态同步覆盖特定属性
}

/// <summary>
/// 混合管理器 — 双通道的中枢
/// </summary>
public class HybridSyncManager : MonoBehaviour
{
    [Header("通道组件")]
    [SerializeField] private LockstepChannel  _lockstepChannel;   // 复用第08节代码
    [SerializeField] private StateSyncChannel _stateSyncChannel;  // 复用第18节代码

    [Header("时间配置")]
    [SerializeField] private int _logicFrameRate = 30;   // 逻辑帧 Hz
    [SerializeField] private int _stateSyncRate  = 15;   // 状态同步 Hz

    [Header("调试")]
    [SerializeField] private bool _verboseLog = false;

    // ── 运行时状态 ──────────────────────────────────────
    private EntityRegistry      _entityRegistry;
    private bool                _isRunning;
    private int                 _currentLogicFrame;      // 当前逻辑帧号 (自战斗开始)
    private long                _baseServerTimestampMs;  // 第一个帧同步包的服务器时间戳
    private int                 _baseLogicFrame;         // 对应 baseTimestamp 的逻辑帧号
    private float               _logicFrameAccumulator;  // 逻辑帧累积时间
    private float               _stateSyncAccumulator;   // 状态同步发送累积时间

    // 状态同步的最新 '服务器权威快照' — 用于仲裁
    private Dictionary<uint, ReplicatedState> _latestServerStates;

    // 事件
    public event Action<int>     OnLogicFrameAdvanced;   // 逻辑帧推进时触发
    public event Action<uint, ReplicatedState> OnStateReceived; // 收到状态同步数据时触发

    // ── 公共属性 ────────────────────────────────────────
    public int           CurrentLogicFrame => _currentLogicFrame;
    public EntityRegistry Registry          => _entityRegistry;
    public bool          IsRunning          => _isRunning;

    // ── 常量 ────────────────────────────────────────────
    private float LogicFrameInterval => 1f / _logicFrameRate;
    private float StateSyncInterval => 1f / _stateSyncRate;

    // ============================================================
    //  生命周期
    // ============================================================

    private void Awake()
    {
        _entityRegistry     = new EntityRegistry();
        _latestServerStates = new Dictionary<uint, ReplicatedState>(256);
    }

    /// <summary>
    /// 启动混合同步。调用此方法后，两个通道同时开始工作。
    /// </summary>
    /// <param name="serverAddress">服务器地址</param>
    /// <param name="lockstepPort">帧同步 UDP 端口</param>
    /// <param name="stateSyncPort">状态同步 RUDP 端口</param>
    /// <param name="playerCount">预期玩家数量</param>
    public void StartSync(string serverAddress, int lockstepPort, int stateSyncPort, int playerCount)
    {
        if (_isRunning) return;

        // 1. 启动帧同步通道 (Channel A)
        _lockstepChannel.OnFrameDataReceived += OnLockstepFrameReceived;
        _lockstepChannel.Connect(serverAddress, lockstepPort, playerCount);

        // 2. 启动状态同步通道 (Channel B)
        _stateSyncChannel.OnStateDataReceived += OnStateSyncDataReceived;
        _stateSyncChannel.Connect(serverAddress, stateSyncPort);

        // 3. 初始化时间基准 — baseTimestamp 和 baseFrame 在收到第一个帧包时设置
        _baseServerTimestampMs = -1;
        _baseLogicFrame        = 0;
        _currentLogicFrame     = -1; // -1 表示尚未收到第一个帧包
        _logicFrameAccumulator = 0f;
        _stateSyncAccumulator  = 0f;

        _isRunning = true;
        Debug.Log($"[HybridSyncManager] 双通道已启动 — Lockstep:{lockstepPort} StateSync:{stateSyncPort}");
    }

    public void StopSync()
    {
        if (!_isRunning) return;

        _lockstepChannel.OnFrameDataReceived -= OnLockstepFrameReceived;
        _stateSyncChannel.OnStateDataReceived -= OnStateSyncDataReceived;
        _lockstepChannel.Disconnect();
        _stateSyncChannel.Disconnect();
        _isRunning = false;

        Debug.Log("[HybridSyncManager] 双通道已停止");
    }

    // ============================================================
    //  主循环 (由 Unity Update 驱动)
    // ============================================================

    private void Update()
    {
        if (!_isRunning) return;

        float dt = Time.deltaTime;

        // ── 步骤 1: 处理两个通道的网络接收 ──
        // 无论帧同步是否在等待，状态同步的数据都必须被接收和处理
        ProcessChannelBReceive();        // 状态同步接收 (不阻塞)
        ProcessChannelAReceive();        // 帧同步接收 (可能触发帧推进)

        // ── 步骤 2: 推进逻辑帧 (Channel A 驱动) ──
        _logicFrameAccumulator += dt;
        while (_logicFrameAccumulator >= LogicFrameInterval)
        {
            _logicFrameAccumulator -= LogicFrameInterval;
            AdvanceLogicFrame();
        }

        // ── 步骤 3: 发送状态同步数据 (Channel B, 周期发送) ──
        _stateSyncAccumulator += dt;
        if (_stateSyncAccumulator >= StateSyncInterval)
        {
            _stateSyncAccumulator -= StateSyncInterval;
            SendStateSyncData();
        }

        // ── 步骤 4: 仲裁冲突 ──
        ResolveConflicts();

        // ── 步骤 5: 表现层 — 对所有实体做插值/平滑 ──
        UpdateEntityPresentation(dt);
    }

    // ============================================================
    //  Channel A: 帧同步处理
    // ============================================================

    /// <summary>
    /// 接收帧同步数据。由 LockstepChannel 的接收线程回调。
    /// 注意：此回调可能在非主线程！我们通过队列化处理保证线程安全。
    /// </summary>
    private void OnLockstepFrameReceived(int frameNumber, byte[][] playerInputs, long serverTimestampMs)
    {
        // 队列化 — 在主线程的 ProcessChannelAReceive 中处理
        _lockstepChannel.EnqueueFrameData(frameNumber, playerInputs, serverTimestampMs);
    }

    private void ProcessChannelAReceive()
    {
        // 从 LockstepChannel 的帧缓冲中取出可用帧
        // 帧同步的"等待"逻辑在 LockstepChannel 内部完成：
        // 如果缓冲帧不足（< 预缓冲帧数），不推进
        int nextFrame = _currentLogicFrame + 1;

        while (_lockstepChannel.HasFrame(nextFrame))
        {
            var frameData = _lockstepChannel.DequeueFrame(nextFrame);

            // 首次收到帧包 → 建立时间基准
            if (_baseServerTimestampMs < 0)
            {
                _baseServerTimestampMs = frameData.serverTimestampMs;
                _baseLogicFrame        = nextFrame;
                _currentLogicFrame     = nextFrame - 1; // 接下来 AdvanceLogicFrame 会 +1
            }

            nextFrame++;
        }
    }

    /// <summary>
    /// 推进一个逻辑帧。这是帧同步的核心迭代。
    /// </summary>
    private void AdvanceLogicFrame()
    {
        _currentLogicFrame++;

        // 从缓冲中获取当前帧的所有玩家输入
        if (!_lockstepChannel.HasFrame(_currentLogicFrame))
        {
            // 缓冲不足 — 此帧跳过。帧同步会使用"空输入"填充
            // 生产代码中应记录 missedFrames 并在追帧时加速
            if (_verboseLog) Debug.LogWarning($"[HSM] Frame {_currentLogicFrame} not ready — skipping");
        }

        var frameInputs = _lockstepChannel.GetFrameInputs(_currentLogicFrame);

        // 对所有 Lockstep 和 Hybrid 实体执行逻辑帧更新
        foreach (var entity in _entityRegistry.GetLockstepEntities())
        {
            // 获取该玩家在此帧的输入
            byte[] input = frameInputs.TryGetValue(entity.OwnerPlayerId, out var inp) ? inp : null;
            entity.TickInput(_currentLogicFrame, input);
        }

        // Hybrid 实体也执行帧同步逻辑（先走帧同步，后续仲裁可能覆盖）
        foreach (var entity in _entityRegistry.GetHybridEntities())
        {
            byte[] input = frameInputs.TryGetValue(entity.OwnerPlayerId, out var inp) ? inp : null;
            entity.TickInput(_currentLogicFrame, input);
        }

        OnLogicFrameAdvanced?.Invoke(_currentLogicFrame);
    }

    // ============================================================
    //  Channel B: 状态同步处理
    // ============================================================

    /// <summary>
    /// 状态同步数据的回调。来自 StateSyncChannel。
    /// 注意：可能在非主线程调用——我们直接在这里做轻量的数据缓存。
    /// </summary>
    private void OnStateSyncDataReceived(ReplicatedState[] states)
    {
        // 线程安全：将数据存入并发队列，主线程在 ProcessChannelBReceive 中取出
        _stateSyncChannel.EnqueueStateData(states);
    }

    private void ProcessChannelBReceive()
    {
        // 处理所有已到达的状态同步数据 — 不等待、不阻塞
        while (_stateSyncChannel.TryDequeueState(out ReplicatedState state))
        {
            // 1. 更新最新的服务器权威快照 (用于后续仲裁)
            _latestServerStates[state.entityId] = state;

            // 2. 立即应用到 ReplicatedEntity
            if (_entityRegistry.TryGetReplicatedEntity(state.entityId, out var repEntity))
            {
                repEntity.ApplyState(state, _currentLogicFrame);
                OnStateReceived?.Invoke(state.entityId, state);
            }
            else
            {
                // 实体尚未注册 → 可能需要动态创建
                // 生产代码中在此触发 EntityFactory.CreateReplicated(state)
                if (_verboseLog) Debug.Log($"[HSM] Replicated state for unknown entity {state.entityId}");
            }
        }
    }

    private void SendStateSyncData()
    {
        // 状态同步客户端通常只发送"事件"（如射击、拾取），
        // 而非持续的位置更新。位置由帧同步控制或服务器权威下发。
        // 这里发送待处理的 RPC 队列
        _stateSyncChannel.FlushPendingRpcs();
    }

    // ============================================================
    //  冲突仲裁
    // ============================================================

    /// <summary>
    /// 仲裁：决定每个实体的最终状态。
    /// 规则：
    ///   LockstepEntity + 本地玩家 → 帧同步结果（本地预测）
    ///   其他实体 → 如果有更新的服务器状态，使用服务器权威数据
    /// </summary>
    private void ResolveConflicts()
    {
        // 只对 HybridEntity 执行仲裁
        foreach (var hybrid in _entityRegistry.GetHybridEntities())
        {
            if (_latestServerStates.TryGetValue(hybrid.EntityId, out var serverState))
            {
                // 计算服务器状态对应的"逻辑帧号"
                int serverFrame = TimestampToLogicFrame(serverState.serverTimestampMs);

                // 如果服务器状态比当前帧更新 → 覆盖
                if (serverFrame >= _currentLogicFrame)
                {
                    hybrid.ApplyServerOverride(serverState);
                }
                // 否则：帧同步结果优先（本地预测尚未被服务器确认/否定）
            }
        }
    }

    // ============================================================
    //  表现层更新
    // ============================================================

    /// <summary>
    /// 对所有实体执行渲染层的插值/平滑更新。
    /// LockstepEntity: 逻辑位置 → 插值到渲染位置
    /// ReplicatedEntity: 目标位置 → 插值到渲染位置
    /// </summary>
    private void UpdateEntityPresentation(float dt)
    {
        float alpha = _logicFrameAccumulator / LogicFrameInterval; // 插值因子

        foreach (var entity in _entityRegistry.GetAllActiveEntities())
        {
            entity.UpdatePresentation(dt, alpha);
        }
    }

    // ============================================================
    //  工具方法
    // ============================================================

    /// <summary>
    /// 将服务器时间戳转换为对应的逻辑帧号
    /// 公式: baseFrame + round((timestamp - baseTimestamp) / frameIntervalMs)
    /// </summary>
    public int TimestampToLogicFrame(long serverTimestampMs)
    {
        if (_baseServerTimestampMs < 0) return _currentLogicFrame; // 尚未初始化

        long deltaMs = serverTimestampMs - _baseServerTimestampMs;
        int  deltaFrames = (int)Math.Round((double)deltaMs / (1000.0 / _logicFrameRate));
        return _baseLogicFrame + deltaFrames;
    }

    /// <summary>
    /// 将逻辑帧号转换为服务器时间戳
    /// </summary>
    public long LogicFrameToTimestamp(int frameNumber)
    {
        if (_baseServerTimestampMs < 0) return 0;
        int deltaFrames = frameNumber - _baseLogicFrame;
        return _baseServerTimestampMs + (long)(deltaFrames * (1000.0 / _logicFrameRate));
    }

    private void OnDestroy()
    {
        StopSync();
    }
}
```

### 2.2 EntityRegistry.cs —— 实体注册表（~130行）

统一管理三类实体的注册、查找和生命周期。

```csharp
// EntityRegistry.cs
// 统一实体注册表。使用三个字典分别管理三类实体，
// 避免类型判断的开销，同时方便批量遍历。

using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 实体基接口 — 所有同步实体必须实现
/// </summary>
public interface ISyncEntity
{
    uint           EntityId       { get; }
    EntitySyncType SyncType       { get; }
    uint           OwnerPlayerId  { get; }
    bool           IsActive       { get; }
    void           UpdatePresentation(float dt, float interpolationAlpha);
}

/// <summary>
/// 帧同步驱动的实体
/// </summary>
public abstract class LockstepEntity : ISyncEntity
{
    public uint           EntityId      { get; protected set; }
    public EntitySyncType SyncType      => EntitySyncType.Lockstep;
    public uint           OwnerPlayerId { get; protected set; }
    public bool           IsActive      { get; set; } = true;

    /// <summary>每逻辑帧调用：输入 → 确定性状态变更</summary>
    public abstract void TickInput(int frameNumber, byte[] input);

    /// <summary>获取当前帧的位置（用于仲裁和表现层插值）</summary>
    public abstract Vector3 GetLogicPosition();

    public abstract void UpdatePresentation(float dt, float interpolationAlpha);
}

/// <summary>
/// 状态同步驱动的实体
/// </summary>
public abstract class ReplicatedEntity : ISyncEntity
{
    public uint           EntityId      { get; protected set; }
    public EntitySyncType SyncType      => EntitySyncType.Replicated;
    public uint           OwnerPlayerId => 0; // Replicated 实体无 Owner
    public bool           IsActive      { get; set; } = true;

    /// <summary>收到服务器状态快照时调用</summary>
    public abstract void ApplyState(ReplicatedState state, int currentLogicFrame);

    public abstract void UpdatePresentation(float dt, float interpolationAlpha);
}

/// <summary>
/// 混合驱动实体：帧同步计算 + 状态同步覆盖特定属性
/// </summary>
public abstract class HybridEntity : ISyncEntity
{
    public uint           EntityId      { get; protected set; }
    public EntitySyncType SyncType      => EntitySyncType.Hybrid;
    public uint           OwnerPlayerId { get; protected set; }
    public bool           IsActive      { get; set; } = true;

    /// <summary>每逻辑帧调用 — 帧同步路径</summary>
    public abstract void TickInput(int frameNumber, byte[] input);

    /// <summary>服务器权威覆盖 — 状态同步路径</summary>
    public abstract void ApplyServerOverride(ReplicatedState serverState);

    public abstract void UpdatePresentation(float dt, float interpolationAlpha);
}

/// <summary>
/// 状态同步的数据结构（从服务器下发）
/// </summary>
public struct ReplicatedState
{
    public uint   entityId;
    public long   serverTimestampMs;
    public Vector3 position;
    public Vector3 velocity;
    public int    health;
    public int    maxHealth;
    public byte   stateFlags;      // 位掩码: bit0=alive, bit1=stunned, ...
    public uint[] buffIds;         // 当前 Buff 列表
    // 可根据项目需要扩展
}

/// <summary>
/// 实体注册表 — O(1) 查找，按类型高效遍历
/// </summary>
public class EntityRegistry
{
    // 三个独立字典，避免类型混在一起
    private readonly Dictionary<uint, LockstepEntity>   _lockstepEntities   = new Dictionary<uint, LockstepEntity>(64);
    private readonly Dictionary<uint, ReplicatedEntity> _replicatedEntities = new Dictionary<uint, ReplicatedEntity>(256);
    private readonly Dictionary<uint, HybridEntity>     _hybridEntities     = new Dictionary<uint, HybridEntity>(32);

    // ── 注册 ──────────────────────────────────────────

    public void Register(LockstepEntity entity)
    {
        _lockstepEntities[entity.EntityId] = entity;
    }

    public void Register(ReplicatedEntity entity)
    {
        _replicatedEntities[entity.EntityId] = entity;
    }

    public void Register(HybridEntity entity)
    {
        _hybridEntities[entity.EntityId] = entity;
    }

    // ── 注销 ──────────────────────────────────────────

    public void Unregister(uint entityId, EntitySyncType type)
    {
        switch (type)
        {
            case EntitySyncType.Lockstep:   _lockstepEntities.Remove(entityId);   break;
            case EntitySyncType.Replicated: _replicatedEntities.Remove(entityId); break;
            case EntitySyncType.Hybrid:     _hybridEntities.Remove(entityId);     break;
        }
    }

    public bool TryGetReplicatedEntity(uint entityId, out ReplicatedEntity entity)
        => _replicatedEntities.TryGetValue(entityId, out entity);

    // ── 批量遍历 (foreach-friendly) ──────────────────

    public IEnumerable<LockstepEntity> GetLockstepEntities()
    {
        foreach (var kv in _lockstepEntities)
            if (kv.Value.IsActive) yield return kv.Value;
    }

    public IEnumerable<ReplicatedEntity> GetReplicatedEntities()
    {
        foreach (var kv in _replicatedEntities)
            if (kv.Value.IsActive) yield return kv.Value;
    }

    public IEnumerable<HybridEntity> GetHybridEntities()
    {
        foreach (var kv in _hybridEntities)
            if (kv.Value.IsActive) yield return kv.Value;
    }

    public IEnumerable<ISyncEntity> GetAllActiveEntities()
    {
        foreach (var kv in _lockstepEntities)
            if (kv.Value.IsActive) yield return kv.Value;
        foreach (var kv in _replicatedEntities)
            if (kv.Value.IsActive) yield return kv.Value;
        foreach (var kv in _hybridEntities)
            if (kv.Value.IsActive) yield return kv.Value;
    }

    // ── 查询 ──────────────────────────────────────────

    public int LockstepCount   => _lockstepEntities.Count;
    public int ReplicatedCount => _replicatedEntities.Count;
    public int HybridCount     => _hybridEntities.Count;

    public ISyncEntity GetEntity(uint entityId)
    {
        if (_lockstepEntities.TryGetValue(entityId, out var le))   return le;
        if (_replicatedEntities.TryGetValue(entityId, out var re)) return re;
        if (_hybridEntities.TryGetValue(entityId, out var he))     return he;
        return null;
    }

    public void Clear()
    {
        _lockstepEntities.Clear();
        _replicatedEntities.Clear();
        _hybridEntities.Clear();
    }
}
```

### 2.3 LockstepChannel.cs —— 帧同步通道适配层（~80行）

这是第 08 节 LockstepManager 的精简包装，暴露 HybridSyncManager 需要的接口。

```csharp
// LockstepChannel.cs
// 对第08节 LockstepManager 的适配层。
// 在混合同步架构中，帧同步通道被封装为此接口，
// 以便 HybridSyncManager 可以统一管理。
// 实际实现直接复用第08节的代码（LockstepManager, FrameBuffer 等）。

using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 帧同步通道 — 管理 UDP 连接 + 帧缓冲 + 帧推进
/// 这是第08节完整 LockstepManager 的精简适配器。
/// </summary>
public class LockstepChannel : MonoBehaviour
{
    [Header("帧同步参数")]
    [SerializeField] private int _frameRate       = 30;     // 帧率
    [SerializeField] private int _preBufferFrames = 4;      // 预缓冲帧数
    [SerializeField] private int _maxBufferFrames = 12;     // 最大缓冲

    // ── 核心组件（复用第08节代码） ──
    private UdpNetworkClient  _udpClient;       // UDP 客户端 (第02/07节)
    private FrameBuffer       _frameBuffer;     // 帧环形缓冲 (第07/08节)
    private int               _localPlayerId;   // 本地玩家 ID

    // ── 事件 ──
    public event Action<int, byte[][], long> OnFrameDataReceived;

    // 线程安全的接收队列
    private readonly Queue<FramePacket> _receivedQueue = new Queue<FramePacket>();
    private readonly object             _queueLock     = new object();

    private struct FramePacket
    {
        public int      frameNumber;
        public byte[][] playerInputs;
        public long     serverTimestampMs;
    }

    public void Connect(string serverAddress, int port, int playerCount)
    {
        _udpClient = new UdpNetworkClient();
        _frameBuffer = new FrameBuffer(_maxBufferFrames, playerCount);
        _udpClient.OnDataReceived += OnUdpDataArrived;
        _udpClient.Connect(serverAddress, port);
    }

    public void Disconnect()
    {
        _udpClient?.Disconnect();
    }

    /// <summary>
    /// 线程安全地将帧数据加入队列。
    /// 实际项目中，UDP 接收运行在独立线程上。
    /// </summary>
    public void EnqueueFrameData(int frameNumber, byte[][] inputs, long serverTimestampMs)
    {
        lock (_queueLock)
        {
            _receivedQueue.Enqueue(new FramePacket
            {
                frameNumber       = frameNumber,
                playerInputs      = inputs,
                serverTimestampMs = serverTimestampMs
            });
        }
    }

    /// <summary>检查指定帧是否在缓冲中</summary>
    public bool HasFrame(int frameNumber)
    {
        return _frameBuffer.Has(frameNumber);
    }

    /// <summary>从缓冲中取出帧数据</summary>
    public FramePacket DequeueFrame(int frameNumber)
    {
        return _frameBuffer.Get(frameNumber);
    }

    /// <summary>获取指定帧的所有玩家输入</summary>
    public Dictionary<uint, byte[]> GetFrameInputs(int frameNumber)
    {
        return _frameBuffer.GetInputs(frameNumber);
    }

    // UDP 数据到达回调（在独立线程中调用）— 生产代码中用 RxThread 处理
    private void OnUdpDataArrived(byte[] data)
    {
        // 解析帧包 → EnqueueFrameData
        // 具体协议格式参见第07节 "帧同步协议设计"
        var parsed = ParseLockstepPacket(data);
        EnqueueFrameData(parsed.frameNo, parsed.inputs, parsed.serverTimeMs);

        // 同时存入帧缓冲，供后续帧推进使用
        _frameBuffer.Insert(parsed.frameNo, parsed.inputs);
    }

    private (int frameNo, byte[][] inputs, long serverTimeMs) ParseLockstepPacket(byte[] data)
    {
        // 协议格式 (参见第07节):
        // [0..3]  FrameNumber (uint32, little-endian)
        // [4..11] ServerTimestampMs (int64, little-endian)
        // [12]    PlayerCount
        // [13..]  每个玩家的输入流
        int offset = 0;
        int frameNo   = BitConverter.ToInt32(data, offset); offset += 4;
        long serverTs = BitConverter.ToInt64(data, offset); offset += 8;
        int playerCnt = data[offset]; offset += 1;

        byte[][] inputs = new byte[playerCnt][];
        for (int i = 0; i < playerCnt; i++)
        {
            byte len = data[offset]; offset += 1;
            inputs[i] = new byte[len];
            Buffer.BlockCopy(data, offset, inputs[i], 0, len);
            offset += len;
        }

        return (frameNo, inputs, serverTs);
    }

    private void Update()
    {
        // 主线程：将接收队列中的数据入帧缓冲
        lock (_queueLock)
        {
            while (_receivedQueue.Count > 0)
            {
                var pkt = _receivedQueue.Dequeue();
                _frameBuffer.Insert(pkt.frameNumber, pkt.playerInputs);
                OnFrameDataReceived?.Invoke(pkt.frameNumber, pkt.playerInputs, pkt.serverTimestampMs);
            }
        }
    }
}
```

### 2.4 StateSyncChannel.cs —— 状态同步通道适配层（~70行）

对第 18 节状态同步客户端的精简封装。

```csharp
// StateSyncChannel.cs
// 对第18节 StateSyncClient 的适配层。
// 在混合同步架构中，状态同步通道提供可靠的状态数据收发。

using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 状态同步通道 — 管理 RUDP 连接 + 可靠收发 + RPC 队列
/// </summary>
public class StateSyncChannel : MonoBehaviour
{
    [Header("状态同步参数")]
    [SerializeField] private int _maxPacketSize = 512;

    // ── 核心组件 ──
    private ReliableUdpClient _rudpClient;        // RUDP 客户端 (如 KCP)
    private Queue<ReplicatedState[]> _stateQueue = new Queue<ReplicatedState[]>();
    private Queue<byte[]>            _rpcQueue   = new Queue<byte[]>(); // 待发送 RPC
    private readonly object          _queueLock  = new object();

    // ── 事件 ──
    public event Action<ReplicatedState[]> OnStateDataReceived;

    public void Connect(string serverAddress, int port)
    {
        _rudpClient = new ReliableUdpClient();
        _rudpClient.OnDataReceived += OnRudpDataArrived;
        _rudpClient.Connect(serverAddress, port);
    }

    public void Disconnect()
    {
        _rudpClient?.Disconnect();
    }

    /// <summary>线程安全入队</summary>
    public void EnqueueStateData(ReplicatedState[] states)
    {
        lock (_queueLock)
        {
            _stateQueue.Enqueue(states);
        }
    }

    /// <summary>尝试从队列中取出状态数据（非阻塞）</summary>
    public bool TryDequeueState(out ReplicatedState state)
    {
        // 简化的批量解包：上层每次取一个实体
        // 生产代码中需要更精细的迭代器
        lock (_queueLock)
        {
            if (_stateQueue.Count == 0)
            {
                state = default;
                return false;
            }

            // 从队首的数组中按序取出
            var batch = _stateQueue.Peek();
            // … 实际需要维护一个内部的 cursor 遍历 batch
            // 为简洁，这里假设 batch 被逐条处理（HybridSyncManager 每次取一条）
            state = batch[0]; // 示意
            _stateQueue.Dequeue();
            return true;
        }
    }

    /// <summary>将待发送的 RPC 发出</summary>
    public void FlushPendingRpcs()
    {
        lock (_queueLock)
        {
            while (_rpcQueue.Count > 0)
            {
                byte[] rpcData = _rpcQueue.Dequeue();
                _rudpClient.Send(rpcData);
            }
        }
    }

    /// <summary>添加一个 RPC 到发送队列</summary>
    public void SendRpc(byte[] rpcData)
    {
        lock (_queueLock)
        {
            _rpcQueue.Enqueue(rpcData);
        }
    }

    private void OnRudpDataArrived(byte[] data)
    {
        // 解析状态快照包
        var states = ParseStatePacket(data);
        EnqueueStateData(states);
        OnStateDataReceived?.Invoke(states);
    }

    private ReplicatedState[] ParseStatePacket(byte[] data)
    {
        // 协议格式:
        // [0]    实体数量 (1B)
        // [1..]  每个实体的序列化数据
        int offset = 0;
        int count  = data[offset]; offset += 1;
        var states = new ReplicatedState[count];

        for (int i = 0; i < count; i++)
        {
            states[i] = new ReplicatedState
            {
                entityId           = BitConverter.ToUInt32(data, offset), offset += 4,
                serverTimestampMs  = BitConverter.ToInt64(data, offset),  offset += 8,
                position           = new Vector3(
                    BitConverter.ToSingle(data, offset),
                    BitConverter.ToSingle(data, offset + 4),
                    BitConverter.ToSingle(data, offset + 8)
                ),
                offset += 12,
                health             = BitConverter.ToInt32(data, offset), offset += 4,
                maxHealth          = BitConverter.ToInt32(data, offset), offset += 4,
                stateFlags         = data[offset],                     offset += 1,
            };
            // buffIds... (省略)
        }

        return states;
    }
}
```

### 2.5 C++ 双通道管理（~180行）

在 Unreal 或自研引擎中，双通道管理的核心是**线程安全 + 零拷贝消息传递**。以下代码展示 C++ 生产级的实现骨架。

```cpp
// ============================================================
// HybridSyncManager.h
// C++ 混合同步管理器 — Unreal Engine / 自研引擎
// ============================================================

#pragma once

#include <cstdint>
#include <memory>
#include <atomic>
#include <unordered_map>
#include <vector>
#include <thread>
#include <mutex>

// ─── 前置声明 ──────────────────────────────────────────
class LockstepChannel;
class StateSyncChannel;
class EntityRegistry;

struct ReplicatedState {
    uint32_t entityId;
    int64_t  serverTimestampMs;
    float    posX, posY, posZ;
    float    velX, velY, velZ;
    int32_t  health;
    int32_t  maxHealth;
    uint8_t  stateFlags;
};

enum class EntitySyncType : uint8_t {
    Lockstep   = 0,
    Replicated = 1,
    Hybrid     = 2,
};

// ─── 混合同步管理器 ─────────────────────────────────────
class HybridSyncManager {
public:
    HybridSyncManager(int logicFrameRate, int stateSyncRate);
    ~HybridSyncManager();

    // 生命周期
    void StartSync(const char* serverAddr, uint16_t lockstepPort,
                   uint16_t stateSyncPort, int playerCount);
    void StopSync();

    // 主线程每帧调用
    void Tick(float deltaTime);

    // 帧号转换
    int  TimestampToLogicFrame(int64_t serverTimestampMs) const;
    int64_t LogicFrameToTimestamp(int frameNumber) const;

    // 访问器
    int             GetCurrentLogicFrame() const { return _currentLogicFrame.load(); }
    EntityRegistry* GetRegistry()               { return _entityRegistry.get(); }

private:
    // ── 内部方法 ──
    void ProcessChannelA();       // 帧同步接收 + 推进
    void ProcessChannelB();       // 状态同步接收 + 应用
    void AdvanceLogicFrame();     // 推进一个逻辑帧
    void ResolveConflicts();      // 仲裁
    void UpdatePresentation(float dt); // 表现层插值

    // ── 通道 ──
    std::unique_ptr<LockstepChannel>  _lockstepChannel;
    std::unique_ptr<StateSyncChannel> _stateSyncChannel;
    std::unique_ptr<EntityRegistry>   _entityRegistry;

    // ── 时间 ──
    int         _logicFrameRate;
    int         _stateSyncRate;
    float       _logicFrameInterval;    // 秒
    float       _stateSyncInterval;

    std::atomic<int>     _currentLogicFrame{0};
    std::atomic<int64_t> _baseServerTimestampMs{-1};
    std::atomic<int>     _baseLogicFrame{0};
    float                _logicFrameAccumulator{0.0f};
    float                _stateSyncAccumulator{0.0f};
    bool                 _isRunning{false};

    // ── 线程安全的接收缓冲 ──
    // Lockstep 通道 — SPSC 无锁队列
    struct FramePacket {
        int        frameNumber;
        int64_t    serverTimestampMs;
        // 输入数据所有权转移至此 (unique_ptr 移动语义)
        std::unique_ptr<uint8_t*[]> playerInputs; // [playerId] → input bytes
    };
    // 生产代码中使用 moodycamel::ReaderWriterQueue 或 boost::lockfree::spsc_queue
    // 这里用 mutex + deque 示意
    std::mutex              _frameQueueLock;
    std::vector<FramePacket> _frameQueue;

    // 状态同步通道 — 最新状态快照 (用于仲裁)
    std::mutex                                    _stateMapLock;
    std::unordered_map<uint32_t, ReplicatedState> _latestServerStates;
};

// ============================================================
// HybridSyncManager.cpp
// ============================================================

HybridSyncManager::HybridSyncManager(int logicFrameRate, int stateSyncRate)
    : _logicFrameRate(logicFrameRate)
    , _stateSyncRate(stateSyncRate)
    , _logicFrameInterval(1.0f / logicFrameRate)
    , _stateSyncInterval(1.0f / stateSyncRate)
    , _entityRegistry(std::make_unique<EntityRegistry>())
{
}

HybridSyncManager::~HybridSyncManager()
{
    StopSync();
}

void HybridSyncManager::StartSync(const char* serverAddr,
                                   uint16_t lockstepPort,
                                   uint16_t stateSyncPort,
                                   int playerCount)
{
    if (_isRunning) return;

    // 1. 创建并启动帧同步通道
    _lockstepChannel = std::make_unique<LockstepChannel>();
    _lockstepChannel->SetFrameCallback([this](int frameNo, uint8_t** inputs,
                                              int playerCnt, int64_t serverTs) {
        // 此回调在独立网络线程中
        std::lock_guard<std::mutex> lock(_frameQueueLock);
        auto pkt = FramePacket{frameNo, serverTs, nullptr};
        pkt.playerInputs = std::make_unique<uint8_t*[]>(playerCnt);
        for (int i = 0; i < playerCnt; ++i) {
            // 复制输入数据 (帧同步输入极小, 2-8B, 复制开销可忽略)
            // 生产代码可在此使用内存池避免分配
            size_t len = (inputs[i] != nullptr) ? 1 : 0; // 简化的输入大小
            pkt.playerInputs[i] = new uint8_t[len];
            if (inputs[i]) memcpy(pkt.playerInputs[i], inputs[i], len);
        }
        _frameQueue.push_back(std::move(pkt));
    });
    _lockstepChannel->Connect(serverAddr, lockstepPort);

    // 2. 创建并启动状态同步通道
    _stateSyncChannel = std::make_unique<StateSyncChannel>();
    _stateSyncChannel->SetDataCallback([this](const ReplicatedState* states, int count) {
        std::lock_guard<std::mutex> lock(_stateMapLock);
        for (int i = 0; i < count; ++i) {
            _latestServerStates[states[i].entityId] = states[i];
            // 立即应用给 ReplicatedEntity
            // (此处调用 Registry 更新，在主线程 Tick 中也做一次)
        }
    });
    _stateSyncChannel->Connect(serverAddr, stateSyncPort);

    _baseServerTimestampMs.store(-1);
    _isRunning = true;
}

void HybridSyncManager::StopSync()
{
    if (!_isRunning) return;
    _lockstepChannel->Disconnect();
    _stateSyncChannel->Disconnect();
    _isRunning = false;
}

// ============================================================
// 主循环 Tick — 每渲染帧调用
// ============================================================

void HybridSyncManager::Tick(float deltaTime)
{
    if (!_isRunning) return;

    // 步骤 1: 处理网络接收 (非阻塞)
    ProcessChannelB();
    ProcessChannelA();

    // 步骤 2: 逻辑帧推进
    _logicFrameAccumulator += deltaTime;
    while (_logicFrameAccumulator >= _logicFrameInterval) {
        _logicFrameAccumulator -= _logicFrameInterval;
        AdvanceLogicFrame();
    }

    // 步骤 3: 状态同步发送
    _stateSyncAccumulator += deltaTime;
    if (_stateSyncAccumulator >= _stateSyncInterval) {
        _stateSyncAccumulator -= _stateSyncInterval;
        _stateSyncChannel->FlushPendingRpcs();
    }

    // 步骤 4: 仲裁
    ResolveConflicts();

    // 步骤 5: 表现层更新
    UpdatePresentation(deltaTime);
}

void HybridSyncManager::ProcessChannelA()
{
    // 从接收队列中取出所有帧数据，入帧缓冲
    std::lock_guard<std::mutex> lock(_frameQueueLock);
    for (auto& pkt : _frameQueue) {
        _lockstepChannel->GetFrameBuffer().Insert(pkt.frameNumber, pkt.playerInputs.get());

        if (_baseServerTimestampMs.load() < 0) {
            _baseServerTimestampMs.store(pkt.serverTimestampMs);
            _baseLogicFrame.store(pkt.frameNumber);
            _currentLogicFrame.store(pkt.frameNumber - 1);
        }
    }
    _frameQueue.clear();
}

void HybridSyncManager::ProcessChannelB()
{
    // 状态同步数据已在网络线程回调中写入 _latestServerStates
    // 这里只需触发 ReplicatedEntity 的更新
    // 实际项目中: 状态同步通道维护一个接收队列，在此轮询消费
    _stateSyncChannel->ProcessReceivedData(_entityRegistry.get());
}

void HybridSyncManager::AdvanceLogicFrame()
{
    int frame = _currentLogicFrame.fetch_add(1) + 1;

    // 获取此帧的所有玩家输入
    auto inputs = _lockstepChannel->GetFrameBuffer().GetInputs(frame);

    // 更新 Lockstep 实体
    for (auto* entity : _entityRegistry->GetLockstepEntities()) {
        auto* input = inputs.count(entity->GetOwnerPlayerId())
                          ? &inputs.at(entity->GetOwnerPlayerId())
                          : nullptr;
        entity->TickInput(frame, input);
    }

    // 更新 Hybrid 实体
    for (auto* entity : _entityRegistry->GetHybridEntities()) {
        auto* input = inputs.count(entity->GetOwnerPlayerId())
                          ? &inputs.at(entity->GetOwnerPlayerId())
                          : nullptr;
        entity->TickInput(frame, input);
    }
}

void HybridSyncManager::ResolveConflicts()
{
    int currentFrame = _currentLogicFrame.load();
    std::lock_guard<std::mutex> lock(_stateMapLock);

    for (auto* hybrid : _entityRegistry->GetHybridEntities()) {
        auto it = _latestServerStates.find(hybrid->GetEntityId());
        if (it == _latestServerStates.end()) continue;

        int serverFrame = TimestampToLogicFrame(it->second.serverTimestampMs);
        if (serverFrame >= currentFrame) {
            hybrid->ApplyServerOverride(it->second);
        }
    }
}

void HybridSyncManager::UpdatePresentation(float deltaTime)
{
    float alpha = _logicFrameAccumulator / _logicFrameInterval;

    for (auto* entity : _entityRegistry->GetAllActiveEntities()) {
        entity->UpdatePresentation(deltaTime, alpha);
    }
}

int HybridSyncManager::TimestampToLogicFrame(int64_t serverTimestampMs) const
{
    int64_t baseTs = _baseServerTimestampMs.load();
    if (baseTs < 0) return _currentLogicFrame.load();

    int64_t deltaMs    = serverTimestampMs - baseTs;
    int     deltaFrames = static_cast<int>(
        std::round(static_cast<double>(deltaMs) / (1000.0 / _logicFrameRate))
    );
    return _baseLogicFrame.load() + deltaFrames;
}

int64_t HybridSyncManager::LogicFrameToTimestamp(int frameNumber) const
{
    int64_t baseTs = _baseServerTimestampMs.load();
    if (baseTs < 0) return 0;
    int deltaFrames = frameNumber - _baseLogicFrame.load();
    return baseTs + static_cast<int64_t>(deltaFrames * (1000.0 / _logicFrameRate));
}
```

### 2.6 Lua 混合管理器（~150行）

在 Lua-based 引擎中（如《王者荣耀》式的 C+Lua 架构），混合管理器承担类似的职责，但利用 Lua 的动态特性简化代码。

```lua
-- ============================================================
-- hybrid_sync_manager.lua — 混合同步管理器
-- 依赖:
--   lockstep_channel: 第10节的 LockstepMgr
--   state_sync_channel: 第20节的 ReplicationClient
--   entity_registry: entity_registry.lua
-- ============================================================

local HybridSyncManager = {}
HybridSyncManager.__index = HybridSyncManager

-- 构造函数
---@param logic_frame_rate number 逻辑帧率 (Hz)
---@param state_sync_rate number 状态同步频率 (Hz)
---@param lockstep_channel table 帧同步通道实例 (第10节)
---@param state_sync_channel table 状态同步通道实例 (第20节)
---@param entity_registry table 实体注册表实例
function HybridSyncManager.new(logic_frame_rate, state_sync_rate,
                                lockstep_channel, state_sync_channel,
                                entity_registry)
    local self = setmetatable({}, HybridSyncManager)

    self._logic_frame_rate   = logic_frame_rate
    self._state_sync_rate    = state_sync_rate
    self._logic_frame_interval = 1.0 / logic_frame_rate
    self._state_sync_interval  = 1.0 / state_sync_rate

    self._lockstep_channel   = lockstep_channel
    self._state_sync_channel = state_sync_channel
    self._entity_registry    = entity_registry

    -- 运行时状态
    self._current_logic_frame    = 0
    self._base_server_timestamp  = -1     -- 第一个帧包的时间戳
    self._base_logic_frame       = 0
    self._logic_frame_accum      = 0.0
    self._state_sync_accum       = 0.0
    self._is_running             = false

    -- 最新的服务器权威快照 { [entity_id] = ReplicatedState }
    self._latest_server_states = {}

    return self
end

-- 启动双通道
---@param server_addr string
---@param lockstep_port number
---@param state_sync_port number
---@param player_count number
function HybridSyncManager:start(server_addr, lockstep_port, state_sync_port, player_count)
    self._is_running = true

    -- 启动帧同步通道
    self._lockstep_channel:connect(server_addr, lockstep_port, player_count)
    self._lockstep_channel:set_frame_callback(function(frame_no, inputs, server_ts)
        self:_on_lockstep_received(frame_no, inputs, server_ts)
    end)

    -- 启动状态同步通道
    self._state_sync_channel:connect(server_addr, state_sync_port)
    self._state_sync_channel:set_data_callback(function(states)
        self:_on_state_received(states)
    end)

    self._base_server_timestamp = -1
    self._logic_frame_accum      = 0.0
    self._state_sync_accum       = 0.0
end

-- 停止
function HybridSyncManager:stop()
    if not self._is_running then return end
    self._lockstep_channel:disconnect()
    self._state_sync_channel:disconnect()
    self._is_running = false
end

-- ============================================================
-- 主循环 (每渲染帧由引擎调用)
-- ============================================================
---@param dt number 帧间隔（秒）
function HybridSyncManager:tick(dt)
    if not self._is_running then return end

    -- 1. 处理两个通道的接收
    self:_process_channel_b()   -- 状态同步优先（不阻塞）
    self:_process_channel_a()   -- 帧同步（可能入缓冲）

    -- 2. 推进逻辑帧
    self._logic_frame_accum = self._logic_frame_accum + dt
    while self._logic_frame_accum >= self._logic_frame_interval do
        self._logic_frame_accum = self._logic_frame_accum - self._logic_frame_interval
        self:_advance_logic_frame()
    end

    -- 3. 发送状态同步 RPC
    self._state_sync_accum = self._state_sync_accum + dt
    if self._state_sync_accum >= self._state_sync_interval then
        self._state_sync_accum = self._state_sync_accum - self._state_sync_interval
        self._state_sync_channel:flush_rpcs()
    end

    -- 4. 仲裁
    self:_resolve_conflicts()

    -- 5. 表现层插值
    local alpha = self._logic_frame_accum / self._logic_frame_interval
    self:_update_presentation(dt, alpha)
end

-- ============================================================
-- 内部方法
-- ============================================================

function HybridSyncManager:_on_lockstep_received(frame_no, inputs, server_ts)
    -- 帧同步输入到达回调（可能在引擎网络线程中触发）
    -- Lua 通常单线程执行，但 C 引擎的回调通过消息队列转为主线程处理

    if self._base_server_timestamp < 0 then
        self._base_server_timestamp = server_ts
        self._base_logic_frame      = frame_no
        self._current_logic_frame   = frame_no - 1
    end

    -- 帧数据已由 LockstepChannel 内部缓冲，这里只需记录基准
end

function HybridSyncManager:_on_state_received(states)
    -- 状态同步数据到达
    for _, state in ipairs(states) do
        self._latest_server_states[state.entity_id] = state

        -- 立即应用到 ReplicatedEntity
        local entity = self._entity_registry:get_replicated(state.entity_id)
        if entity then
            entity:apply_state(state, self._current_logic_frame)
        end
    end
end

function HybridSyncManager:_process_channel_a()
    -- 帧同步通道已在内部维护帧缓冲
    -- 这里只需检查是否有新帧可以推进
    -- 帧缓冲的"等待"逻辑在 LockstepChannel 内部处理
    self._lockstep_channel:process_received_queue()
end

function HybridSyncManager:_process_channel_b()
    -- 状态同步的接收在 _on_state_received 中立即处理
    -- 这里处理延迟处理的任务（如动态创建实体）
    self._state_sync_channel:process_pending_spawns(self._entity_registry)
end

function HybridSyncManager:_advance_logic_frame()
    self._current_logic_frame = self._current_logic_frame + 1
    local frame = self._current_logic_frame

    -- 获取当前帧的输入
    local inputs = self._lockstep_channel:get_frame_inputs(frame)

    -- 更新 Lockstep 实体
    for _, entity in ipairs(self._entity_registry:get_lockstep_entities()) do
        local input = inputs[entity.owner_player_id]
        entity:tick_input(frame, input)
    end

    -- 更新 Hybrid 实体
    for _, entity in ipairs(self._entity_registry:get_hybrid_entities()) do
        local input = inputs[entity.owner_player_id]
        entity:tick_input(frame, input)
    end
end

function HybridSyncManager:_resolve_conflicts()
    local current_frame = self._current_logic_frame

    for _, hybrid in ipairs(self._entity_registry:get_hybrid_entities()) do
        local server_state = self._latest_server_states[hybrid.entity_id]
        if server_state then
            local server_frame = self:timestamp_to_logic_frame(server_state.server_timestamp_ms)
            if server_frame >= current_frame then
                hybrid:apply_server_override(server_state)
            end
        end
    end
end

function HybridSyncManager:_update_presentation(dt, alpha)
    for _, entity in ipairs(self._entity_registry:get_all_active()) do
        entity:update_presentation(dt, alpha)
    end
end

-- ============================================================
-- 时间转换工具
-- ============================================================

--- 服务器时间戳 → 逻辑帧号
function HybridSyncManager:timestamp_to_logic_frame(server_timestamp_ms)
    if self._base_server_timestamp < 0 then
        return self._current_logic_frame
    end
    local delta_ms     = server_timestamp_ms - self._base_server_timestamp
    local delta_frames = math.floor(delta_ms / (1000.0 / self._logic_frame_rate) + 0.5)
    return self._base_logic_frame + delta_frames
end

--- 逻辑帧号 → 服务器时间戳
function HybridSyncManager:logic_frame_to_timestamp(frame_number)
    if self._base_server_timestamp < 0 then return 0 end
    local delta_frames = frame_number - self._base_logic_frame
    return self._base_server_timestamp + (delta_frames * (1000.0 / self._logic_frame_rate))
end

return HybridSyncManager
```

### 2.7 集成示例：启动与运行

以下展示如何在 Unity 中组装所有组件并启动混合同步客户端。

```csharp
// GameBootstrap.cs — 场景入口
// 挂载在场景根节点，负责组装 HybridSyncManager + 两个 Channel

using UnityEngine;

public class GameBootstrap : MonoBehaviour
{
    [Header("服务器配置")]
    [SerializeField] private string _serverAddress = "127.0.0.1";
    [SerializeField] private int    _lockstepPort  = 9000;
    [SerializeField] private int    _stateSyncPort = 9001;

    [Header("同步参数")]
    [SerializeField] private int _logicFrameRate = 30;
    [SerializeField] private int _stateSyncRate  = 15;
    [SerializeField] private int _playerCount    = 2;

    private HybridSyncManager _hybridManager;

    private void Awake()
    {
        // 创建并配置 HybridSyncManager
        // LockstepChannel 和 StateSyncChannel 作为子组件挂在同一 GameObject 上
        _hybridManager = gameObject.AddComponent<HybridSyncManager>();

        var lockstepChannel = gameObject.AddComponent<LockstepChannel>();
        var stateSyncChannel = gameObject.AddComponent<StateSyncChannel>();

        // 通过反射或 SerializeField 注入依赖 (此处用 SerializeField 示意)
        // 实际上 Awake 中可用 GetComponent 获取
    }

    private void Start()
    {
        _hybridManager.StartSync(_serverAddress, _lockstepPort, _stateSyncPort, _playerCount);
    }

    private void OnDestroy()
    {
        _hybridManager?.StopSync();
    }
}
```

---

## 3. 练习

### 练习 1: 基础 — 理解双通道数据流 (20min)

**目标**：追踪一个玩家输入从采集到生效的完整路径，画出数据流图。

**任务**：
1. 在纸上画出 Channel A 和 Channel B 的数据流图，标注每个环节的延迟来源。
2. 回答以下问题：
   - 本地玩家的"移动输入"经过了哪些步骤才反映到屏幕上？
   - 远程怪物的"位置更新"经过了哪些步骤？
   - 这两个路径的延迟分别是多少？（假设 RTT=50ms，帧缓冲=4帧@30Hz）
3. 修改 `HybridSyncManager.Update()`，添加 `Debug.Log` 输出每个步骤的耗时，在 Unity 中验证你的估算。

**验证标准**：
- 数据流图正确标注了帧缓冲延迟（4帧=133ms）、网络RTT（50ms）、逻辑帧间隔（33ms）
- 本地移动延迟 ≈ RTT/2 + 帧缓冲 ≈ 25 + 133 = 158ms
- 怪物位置更新延迟 ≈ RTT/2 + 插值缓冲 ≈ 25 + 50 = 75ms

---

### 练习 2: 进阶 — 实现帧号对齐的边界情况 (35min)

**目标**：处理帧号对齐中的两个常见边界情况：首次对齐和时钟漂移。

**任务**：
1. 在 `HybridSyncManager.TimestampToLogicFrame()` 中添加跨越整数边界的测试：
   ```csharp
   // 测试 1: 正常转换
   Assert(manager.TimestampToLogicFrame(0) == 0);      // baseFrame=0, baseTs=0
   Assert(manager.TimestampToLogicFrame(33) == 1);      // 30Hz, 33ms=1帧
   Assert(manager.TimestampToLogicFrame(100) == 3);     // 100ms ≈ 3帧
   
   // 测试 2: 负数时间戳 (帧同步包比基准时间早)
   Assert(manager.TimestampToLogicFrame(-50) == -2);    // 回退2帧 — 这是边界情况！
   
   // 测试 3: 非常大的时间戳 (长时间运行后的时钟漂移)
   Assert(manager.TimestampToLogicFrame(3600000) > 0);  // 1小时后仍有效
   ```
2. 处理"状态同步的数据时间戳超前于当前逻辑帧"的情况：修改 `ResolveConflicts()`，当 `serverFrame > _currentLogicFrame + MAX_PREDICTION_FRAMES` 时（如超前超过 10 帧），将数据暂存到 `_pendingServerStates` 队列中，等待逻辑帧追上来后再应用。
3. 在 `ProcessChannelB()` 中消费 `_pendingServerStates`：当逻辑帧推进到某个待定状态的帧号范围内时，取出并应用。

**验证标准**：
- 负数时间戳被优雅处理（不崩溃、不产生异常帧号）
- 超前状态数据被延迟应用而非丢弃
- 添加至少 3 个 Unity Test Runner 单元测试

---

### 练习 3: 挑战 — 实现完整的 HybridBoss 实体 (45min)

**目标**：实现一个混合驱动的 Boss 实体，展示 "帧同步计算位置 + 服务器覆盖血量/阶段" 的完整模式。

**任务**：
1. 创建 `HybridBoss.cs`，继承 `HybridEntity`：
   - `TickInput()`：根据帧同步输入计算 Boss 的移动和攻击行为（使用确定性的 AI 状态机）
   - `ApplyServerOverride()`：覆盖 `_serverAuthoritativeHealth` 和 `_serverAuthoritativePhase`
   - `UpdatePresentation()`：将逻辑位置插值到渲染位置，血量条显示服务器权威值
2. Boss 的 AI 状态机包含三个阶段，阶段切换逻辑如下：
   - Phase 1 (HP > 60%): 移动 + 普攻
   - Phase 2 (HP 30-60%): 加速 + 范围攻击
   - Phase 3 (HP < 30%): 狂暴模式
   - 阶段切换由服务器的 `ApplyServerOverride` 触发（服务器决定何时切换）
3. 在 `HybridSyncManager` 中注册这个 Boss，验证：
   - 帧同步驱动的 Boss 移动在本地无延迟（类似玩家操作反馈）
   - 服务器下发的血量覆盖正确地反映到 Boss 血条上
   - 阶段切换时，Boss 的 AI 状态被正确重置

**验证标准**：
- Boss 移动响应 < 2 帧（帧同步路径）
- 服务器血量覆盖在 100ms 内反映（状态同步 RTT 内）
- 阶段切换不出现"瞬移"或"AI 状态残留"
- 添加 Editor 测试：模拟 200ms 延迟下的 Boss 行为，确保无抖动

---

## 4. 扩展阅读

### 4.1 业界案例

- **[合金弹头：觉醒 — GDC 2024 分享](https://www.gdcvault.com/)**：腾讯天美工作室分享的混合同步架构，详细介绍了横版射击游戏中"帧同步控制玩家角色 + 状态同步管理怪物/Boss"的实现
- **[守望先锋 2 — Netcode Deep Dive (BlizzCon 2019)](https://www.youtube.com/watch?v=W3aieHjyNvw)**：虽然以状态同步为主，但其 "确定性 ECS 模拟 + 服务器回退" 实际上就是一种混合同步的变体
- **[Apex Legends — Multiplayer Netcode (Respawn)](https://www.ea.com/ea-studios/respawn)**：大逃杀中的混合方案：玩家移动用客户端预测（状态同步变体），子弹物理走服务器权威

### 4.2 开源参考

- **[KCP (kcp-dev/kcp)](https://github.com/skywind3000/kcp)**：状态同步通道 B 的可靠 UDP 传输层的优秀选择，已被多款国产手游使用
- **[ENet (lsalzman/enet)](https://github.com/lsalzman/enet)**：另一个成熟的 RUDP 库，《守望先锋》早期版本使用了类似的自定义 RUDP
- **[NetCode for GameObjects — 源码](https://github.com/Unity-Technologies/com.unity.netcode.gameobjects)**：可以学习其 NetworkVariable 和 RPC 的底层实现，了解状态同步在 Unity 中的序列化机制

### 4.3 进阶话题

- **ECS 混合同步**：将 EntityRegistry 替换为 ECS (Entities/Components/Systems)，每个 System 可以指定 "lockstep_system" 或 "replicated_system" 标记。DOTS + NetCode 的结合是这个方向的主线。
- **快照恢复与混合同步**：在第 12 节的快照校验基础上，将快照校验扩展到混合实体。状态同步的覆盖结果可以被帧同步的哈希校验检测到——如果服务器下发的血量与帧同步计算的预期不一致，意味着外挂修改了本地血量。
- **带宽优化**：双通道的带宽分配策略——帧同步通道占用 ~2-3KB/s（8B * 30Hz），状态同步通道占用 ~10-20KB/s（500B * 20Hz * 可变的实体数量）。生产环境中需要 AOI（Area of Interest）来裁剪状态同步的实体数量。

---

## 常见陷阱

### 陷阱 1: 忘记两个通道是独立的网络连接

```
错误：用一个 UDP Socket 同时发送帧同步和状态同步数据。
结果：帧同步的小包被状态同步的大包阻塞（Head-of-Line blocking），
      帧同步的延迟从 30ms 飙升到 150ms+。
```

**正确做法**：两个通道必须使用**两个独立的 Socket**（不同的端口）。帧同步的 UDP Socket 只发 2-8 字节的微小包，操作系统内核会优先调度它们。状态同步的 RUDP Socket 有自己的流控和重传，不会影响帧同步。

### 陷阱 2: 帧号对齐依赖于不稳定的基准

```csharp
// ❌ 错误：用客户端本地时间作为基准
_baseTimestamp = DateTime.UtcNow.Ticks; // 客户端时间不可靠！
_baseFrame     = firstReceivedFrame;

// 问题：客户端可能修改系统时钟，或者不同客户端的时钟偏差数秒
// 导致 TimestampToLogicFrame() 产生完全错误的映射
```

**正确做法**：基准时间戳必须来自**服务器的第一个帧同步包中的 serverTimestamp**。帧号对齐全程使用服务器时间。

```csharp
// ✅ 正确：用服务器时间作为唯一的时间基准
void OnFirstFrameReceived(int frameNo, long serverTimestampMs) {
    _baseServerTimestampMs = serverTimestampMs; // 服务器权威时间
    _baseLogicFrame        = frameNo;
}
```

### 陷阱 3: Hybrid 实体在仲裁时的"回弹"效应

```
场景：
  Frame 100: 帧同步计算出 Boss 位置 = (100, 0)
  Frame 101: 状态同步下发 Boss 位置 = (99.5, 0.2) → 服务器权威覆盖 → Boss 跳到 (99.5, 0.2)
  Frame 102: 帧同步再次计算出 Boss 位置 = (100.3, -0.1) → 又跳回来

  → 观感：Boss 在两个位置之间抖动（回弹）
```

**根因**：每次 ApplyServerOverride 后，帧同步逻辑又从"覆盖前的位置"继续计算，导致下一帧的位置与服务器位置不一致。

**解决方案**：`ApplyServerOverride()` 必须同时**回设帧同步逻辑的当前位置**：

```csharp
public override void ApplyServerOverride(ReplicatedState serverState)
{
    // 1. 覆盖服务器权威属性 (血量/阶段)
    _health = serverState.health;
    _phase  = (serverState.stateFlags & 0x06) >> 1;

    // 2. 关键：也重置帧同步的"本地位置"为服务器位置
    //    这样下一帧的 TickInput 从这个位置开始计算
    _logicPosition = serverState.position;

    // 3. 如果服务器位置和本地位置差异过大（> 阈值），做平滑过渡而非跳变
    float dist = Vector3.Distance(_renderPosition, serverState.position);
    if (dist > 2.0f)
    {
        _needSmoothCorrection = true;
        _correctionTarget     = serverState.position;
    }
}
```

### 陷阱 4: 状态同步通道在锁步等待时停止接收

```
❌ 错误的 Update 顺序：
void Update() {
    ProcessChannelA(); // 帧同步等待 200ms → 整个 Update 阻塞了 200ms
    ProcessChannelB(); // 状态同步数据在这 200ms 内堆积在 Socket 缓冲区
}

✅ 正确的 Update 顺序：
void Update() {
    ProcessChannelB(); // 先处理状态同步（不阻塞，立即返回）
    ProcessChannelA(); // 再处理帧同步（可能等待，但不影响 Channel B）
}
```

**本质**：帧同步的等待（帧缓冲不足时 hang 住）是 Channel A 的内部行为，不能让这种等待污染到 Channel B。如果 Channel B 使用 TCP，TCP 的接收缓冲区是有限的（默认 64KB-256KB），长时间不读取会导致缓冲区满 → 服务器触发流控 → 状态同步延迟恶化。

### 陷阱 5: 实体注销时机与网络回调的竞态

```
时间线：
  T=0: 服务器下发 "销毁实体 42" (状态同步包)
  T=1: 客户端收到包 → 调用 _entityRegistry.Unregister(42)
  T=2: 帧同步推进 Frame N → 遍历 LockstepEntities → 访问实体 42 → NullReferenceException
```

**根因**：实体在帧同步迭代循环中被注销，循环迭代器失效。

**解决方案**：使用延迟注销机制：

```csharp
private readonly List<uint> _pendingUnregister = new List<uint>();

// 在收到销毁通知时，不立即从 Registry 移除，而是标记
public void MarkForUnregister(uint entityId)
{
    _pendingUnregister.Add(entityId);
}

// 在每帧的末尾（所有循环遍历完成后）统一执行注销
private void FlushPendingUnregisters()
{
    foreach (var id in _pendingUnregister)
        _entityRegistry.Unregister(id, _entityRegistry.GetEntity(id).SyncType);
    _pendingUnregister.Clear();
}
```

### 陷阱 6: 混淆"帧同步的玩家输入"和"状态同步的 RPC"

```csharp
// ❌ 错误：把帧同步的"技能释放"也通过状态同步通道发送
[ServerRpc]
void CastSkillServerRpc(int skillId) {
    // 这个 RPC 通过 Channel B (RUDP)，延迟不可控
    // 与其他玩家不同步——他们的帧同步计算依赖这个输入！
}

// ✅ 正确：帧同步的输入通过 Channel A 发送
// 状态同步的 RPC 只用于"非确定性事件"
void CastSkill(int skillId) {
    _lockstepChannel.SendInput(EncodeSkillInput(skillId)); // 走帧同步
}

// 状态同步通道只用于：聊天消息、拾取确认、商店购买等
[ServerRpc]
void SendChatMessageServerRpc(string message) {
    // 这个走 Channel B 没问题——聊天不需要逐帧一致性
}
```

**判断标准**：如果某个操作需要"所有客户端在同一帧看到相同的结果"，它必须走帧同步通道。如果某个操作只需要"最终一致"且不需要确定性时序，它可以走状态同步通道。

### 陷阱 7: 在逻辑帧中访问状态同步的数据而不做帧号对齐

```csharp
// ❌ 错误：在 TickInput（逻辑帧）中直接读取 _latestServerStates
// 可能导致不同客户端在"同一逻辑帧"看到不同的服务器状态
public override void TickInput(int frameNumber, byte[] input)
{
    var serverHP = _manager.GetLatestServerState(entityId).health;
    // 客户端 A 在 Frame 100 读到的 serverHP 是 "Frame 98 的服务器状态"
    // 客户端 B 在 Frame 100 读到的 serverHP 是 "Frame 99 的服务器状态"
    // → 确定性被破坏！
}

// ✅ 正确：使用帧号对齐，只在特定帧读取对应帧的服务器状态
public override void TickInput(int frameNumber, byte[] input)
{
    // 读取"帧号 N 对应的服务器状态"，而非"最新的"
    var serverHP = _manager.GetServerStateAtFrame(entityId, frameNumber).health;
}
```

**核心原则**：混合同步的确定性边界在"帧同步逻辑"一侧。任何进入帧同步逻辑的数据，必须可以通过帧号唯一确定。这意味着状态同步的数据在喂给帧同步逻辑前，必须做"帧号快照化"（snapshot by frame number）。
