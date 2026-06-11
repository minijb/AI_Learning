---
title: "混合同步服务端实现：DS + 逻辑帧 + Room 管理"
updated: 2026-06-05
---

# 混合同步服务端实现：DS + 逻辑帧 + Room 管理

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [[22-hybrid-sync-architecture|22-混合同步架构设计]]

---

## 1. 概念讲解

### 1.1 为什么需要混合同步服务端？

在第 11 节（帧同步服务端）和第 13 节（状态同步核心）中，我们分别看到了两种极端的服务端模型：

| | 帧同步服务端 | 状态同步服务端 |
|---|---|---|
| **职责** | 哑转发——只广播输入，不跑逻辑 | 权威服务器——执行所有游戏逻辑 |
| **CPU** | 极低 | 高（物理/技能/AI/碰撞） |
| **状态** | 不维护游戏状态 | 维护完整世界状态 |
| **适用** | MOBA、RTS、回合制 | FPS、MMO、大逃杀 |

但真实的大项目很少是"纯粹"的。拿两个工业级案例来看：

**合金弹头：觉醒**（横版射击手游）：
- 核心战斗使用**帧同步**：输入驱动的确定性逻辑，爽快感不受服务器权威约束
- BOSS AI、掉落、成就判定使用**状态同步通道**：由服务器做最终裁定，防止客户端作弊
- 服务器按 Room 为单位管理战斗——单进程内同时跑 30~50 个房间（单进程多战斗模式）

**守望先锋**（团队FPS）：
- 核心战斗使用**状态同步**：服务器是移动/射击/技能的唯一权威
- 但部分确定性系统（弹道预测、环境破坏同步）使用**帧同步思路**的固定时间步
- 服务器使用 ECS 架构驱动逻辑帧，10 个玩家 × 每秒 60 tick，单进程跑一场战斗

混合同步服务端要解决的核心问题是：

> **在同一台 DS（Dedicated Server）进程中，如何同时服务帧同步通道和状态同步通道，并管理多个并行的战斗房间？**

### 1.2 DS（Dedicated Server）架构总览

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           DSA (Dedicated Server Agent)                    │
│                    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│                    │ 房间分配器   │  │ 负载均衡器   │  │ 健康检查     │      │
│                    │ RoomAllocator│  │LoadBalancer │  │ HealthCheck │      │
│                    └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │
│                           │                │                │              │
│              ┌────────────┼────────────────┼────────────────┼───           │
│              ▼            ▼                ▼                ▼              │
│  ┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────┐    │
│  │     DS Instance #1    │ │     DS Instance #2    │ │ DS Instance #N│    │
│  │  ┌──────┐ ┌────────┐  │ │  ┌──────┐ ┌────────┐  │ │    ...        │    │
│  │  │Room 1│ │Room 2  │  │ │  │Room 6│ │Room 7  │  │ │               │    │
│  │  │帧+状态│ │帧+状态 │  │ │  │帧同步 │ │状态同步 │  │ │               │    │
│  │  ├──────┤ ├────────┤  │ │  ├──────┤ ├────────┤  │ │               │    │
│  │  │Room 3│ │Room 4  │  │ │  │Room 8│ │Room 9  │  │ │               │    │
│  │  ├──────┤ ├────────┤  │ │  └──────┘ └────────┘  │ │               │    │
│  │  │Room 5│ │ 空闲    │  │ │                       │ │               │    │
│  │  └──────┘ └────────┘  │ │                       │ │               │    │
│  └───────────────────────┘ └───────────────────────┘ └───────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

**DSA（Dedicated Server Agent）** 是 DS 集群的总控。它负责：
1. 接收匹配系统分配的"开房请求"
2. 选择一台负载最低的 DS 实例
3. 通知该 DS 创建新 Room
4. 监控各 DS 的健康状态，对崩溃 DS 上的 Room 做迁移/回收
5. 战斗结束后回收 Room 资源

**DS Instance** 是一台物理机或容器上运行的一个进程。根据架构选择，它可以是：

#### 模式 A：单进程多战斗（Room 模式）——合金弹头方案

```
┌─────────────────────────────────────────┐
│              DS 进程 (Linux)             │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │         RoomManager              │   │
│  │   Dictionary<int, BattleRoom>    │   │
│  │                                  │   │
│  │  Room#42 (2v2 对战)              │   │
│  │  ├─ PhysicsWorld (独立)          │   │
│  │  ├─ FrameServer (帧通道)         │   │
│  │  ├─ StateBroadcaster (状态通道)  │   │
│  │  └─ EntityManager (角色/NPC)     │   │
│  │                                  │   │
│  │  Room#43 (PvE 副本)              │   │
│  │  ├─ PhysicsWorld (独立)          │   │
│  │  ├─ FrameServer                  │   │
│  │  ├─ StateBroadcaster             │   │
│  │  └─ EntityManager                │   │
│  │  ... (最多 50 个 Room) ...       │   │
│  └──────────────────────────────────┘   │
│                                         │
│  共享层: 网络IO线程池 / 定时器 / 日志    │
└─────────────────────────────────────────┘
```

**优点**：
- 单进程资源利用率高（内存共享、代码段共享）
- Room 创建/销毁成本低（只是 C# object 的 new/GC）
- 适合大量对局同时进行的手游场景

**关键挑战**：
- **Room 崩溃隔离**：一个 Room 因为数据异常 crash 了，不能影响其他 Room。C# 中用 `try-catch` 包围每个 Room 的 `Update()`；C++ 中甚至可以用 `setjmp/longjmp` 或独立信号栈。
- **PhysicsWorld 隔离**：如果用了 PhysX 或 Bullet，必须确保每个 Room 使用独立的 `PxScene` 实例。
- **内存上限**：50 个 Room × (物理世界 + 实体 + 输入缓冲) 可能达到数 GB，需要内存池管理。

#### 模式 B：单进程单战斗（传统模式）

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   DS 进程 #1     │  │   DS 进程 #2     │  │   DS 进程 #N     │
│   一场 5v5 战斗   │  │   一场 PvE 副本   │  │   一场 3v3 对战   │
│   CPU: 2核       │  │   CPU: 1核       │  │   CPU: 1核       │
│   内存: 2GB      │  │   内存: 1GB      │  │   内存: 1GB      │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

**优点**：
- 天然崩溃隔离——进程挂了不影响其他战斗
- 资源限制简单——操作系统帮你管理
- 部署灵活——可以用容器（Docker/K8s）管理每个 DS

**缺点**：
- 进程启动开销大（加载引擎库、预热 JIT/IL2CPP）
- 内存冗余（每个进程一份引擎代码段）
- 不适合同一物理机上跑 50 场小战斗

**选择标准**：

| 场景 | 推荐模式 | 理由 |
|------|---------|------|
| 手游（2v2/3v3 MOBA） | 单进程多战斗 | 对局多但每局人数少，Room 模式省钱 |
| PC/主机 AAA（5v5 FPS） | 单进程单战斗 | 每局 CPU/内存需求大，隔离要求高 |
| 休闲对战（消消乐/棋牌） | 单进程多战斗 | 逻辑极轻，一台机器可跑数百房间 |
| 电竞比赛服 | 单进程单战斗 | 隔离性 + 可重现性要求最高 |

---

### 1.3 逻辑帧驱动：DS 的心跳

混合同步服务端以**固定逻辑帧率**驱动一切。这是整个系统的"心跳"：

```
DS 主循环（每逻辑帧执行一次，例如 15Hz = 66.7ms）:

  ┌──────────────────────────────────────────────────────┐
  │  for each active Room:                               │
  │                                                      │
  │    // 第一步：收集输入                                │
  │    inputs = FrameServer.CollectInputs(room, frameNo)  │
  │                                                      │
  │    // 第二步：执行游戏逻辑（确定性 + 非确定性）        │
  │    room.World.Tick(inputs, deltaTime)                 │
  │    // 内部包含: 物理模拟、技能系统、AI、碰撞检测      │
  │                                                      │
  │    // 第三步：生成状态快照                            │
  │    snapshot = SnapshotManager.Generate(room, frameNo) │
  │                                                      │
  │    // 第四步：双通道广播                              │
  │    FrameServer.Broadcast(room, frameNo, inputs)       │
  │    StateBroadcaster.Broadcast(room, dirtyEntities)    │
  │                                                      │
  │  end for                                             │
  └──────────────────────────────────────────────────────┘
```

**关键设计点**：

1. **固定 deltaTime**：无论 OS 调度波动如何，传给 `World.Tick()` 的 `deltaTime` 始终是固定值（如 66.7ms）。这是帧同步确定性的前提。

2. **追赶机制**：如果上一帧因为系统负载执行了 80ms（超过 66.7ms），下一帧不能"跳过"。必须连续执行直至追上墙钟时间。极端情况下可能一连执行多帧。

3. **帧号单调递增**：服务端维护一个全局逻辑帧计数器。每次 `Tick()` 完成，帧号 +1。这个帧号是所有子系统（输入缓冲、快照、重连）的时间基准。

4. **双通道分离**：帧同步通道（FrameServer）处理输入；状态同步通道（StateBroadcaster）处理状态。两者由同一个逻辑帧驱动，但数据流独立。

---

### 1.4 Room 管理系统

Room 是混合同步服务端的最小调度单元。一个 Room 封装了一场完整对局需要的所有资源。

#### Room 生命周期

```
                    ┌─────────┐
          创建请求   │  Idle   │  等待玩家加入
         ──────────►│         │◄─────────────
                    └────┬────┘
                         │ 所有玩家就绪
                         ▼
                    ┌─────────┐
                    │ Loading │  加载地图/初始化物理世界
                    └────┬────┘
                         │ 加载完成
                         ▼
                    ┌─────────┐
                    │ Fighting│  核心战斗循环
                    │  ◄──►  │  每逻辑帧: 收集→逻辑→广播
                    └────┬────┘
                         │ 胜负条件满足
                         ▼
                    ┌─────────┐
                    │ Settle  │  结算阶段(统计数据/录像保存)
                    └────┬────┘
                         │ 结算完成
                         ▼
                    ┌─────────┐
                    │ Destroy │  释放资源: 物理世界/实体/输入缓冲
                    └─────────┘
```

**状态转换规则**：

| 当前状态 | 触发事件 | 目标状态 | 动作 |
|---------|---------|---------|------|
| Idle | 所有玩家连接+加载完成 | Loading | 初始化 PhysicsWorld |
| Loading | 地图/资源加载完成 | Fighting | 启动逻辑帧循环 |
| Fighting | 超时（如 30min 无人头） | Settle | 强制平局 |
| Fighting | 胜负条件触发 | Settle | 记录胜负 |
| Fighting | 所有玩家断线 > 60s | Settle | 废弃对局 |
| Settle | 录像上传/日志写完 | Destroy | 释放内存 |
| 任意状态 | RoomManager 主动 Kill | Destroy | 强制释放（超时/维护） |

#### 多 Room 并行与隔离

多 Room 并行的核心挑战是**资源隔离**：

```csharp
// 每个 Room 持有独立的子系统实例
public class BattleRoom
{
    public uint RoomId;
    public RoomState State;
    
    // === 独立的世界状态 ===
    public PhysicsWorld Physics;     // 独立的 PhysX/Bullet Scene
    public EntityManager Entities;   // 角色、NPC、子弹...
    public GameWorld World;          // 游戏逻辑世界
    
    // === 独立的网络通道 ===
    public FrameServer FrameChannel;       // 帧同步通道
    public StateBroadcaster StateChannel;  // 状态同步通道
    
    // === 独立的缓冲区 ===
    public InputBuffer Inputs;       // 输入缓冲窗口
    public SnapshotRing Snapshots;   // 快照环形缓冲区
    
    // === 独立的玩家列表 ===
    public Dictionary<byte, PlayerSlot> Players;
}
```

**隔离的关键措施**：

1. **PhysicsWorld 隔离**：每个 Room 使用独立的 `PxScene`（PhysX）或 `btDiscreteDynamicsWorld`（Bullet）。物理引擎的碰撞检测、刚体管理、射线检测仅在本 Room 的 Scene 内有效。

2. **内存池隔离**：每个 Room 分配独立的对象池。Room 销毁时，整池归还，不依赖 GC。

3. **崩溃隔离**（单进程多战斗模式下最关键）：

```csharp
// RoomManager 中保护每个 Room 的 Update
foreach (var room in _rooms.Values)
{
    try
    {
        if (room.State == RoomState.Fighting)
            room.Tick(frameNumber);
    }
    catch (Exception ex)
    {
        // 记录崩溃现场，但不影响其他 Room
        Log.Error($"Room {room.RoomId} crashed: {ex}");
        room.EmergencyShutdown();  // 通知玩家"战斗异常终止"
        _corruptedRooms.Add(room); // 标记待回收
    }
}
```

在 C++ 实现中，甚至可以给每个 Room 分配独立的信号栈（`sigaltstack`），使段错误也只影响当前 Room 的线程。

---

### 1.5 帧同步通道：FrameServer

FrameServer 负责收集所有玩家的输入、执行帧对齐、然后广播帧包。它与纯帧同步服务端的 FrameServer（教程 11）的区别在于：

1. **每个 Room 一个 FrameServer 实例**，而非全局单例
2. **双通道协同**：FrameServer 广播的输入同时喂给本 Room 的 `GameWorld.Tick()`
3. **帧号由 Room 统一管理**，不再由 FrameServer 独立维护

```
FrameServer 一帧的工作流程:

  ① 从 UDP socket 接收输入 ──► InputBuffer[frameNumber][playerId] = input
  
  ② 帧对齐判定:
     ├─ 乐观模式: 定时器到期 → 立即打包已收到的输入
     └─ 严格模式: 等待所有玩家 → 打包后广播
  
  ③ 组装帧包:
     FramePackage {
       frameNumber,
       inputs[] (按 playerId 排序),
       checksum (可选快照Hash)
     }
  
  ④ 双路输出:
     ├─ 广播给所有客户端 (UDP multicast 或 unicast)
     └─ 喂给本 Room 的 GameWorld.Tick(inputs) (服务器自己用)
```

**与纯帧同步 FrameServer 的关键差异**：

在纯帧同步中，服务器不执行逻辑——所以 `FrameServer.Broadcast()` 是唯一的输出。在混合同步中，广播同时也喂给**服务器自己的 GameWorld**。这意味着服务器和客户端**都在执行相同的确定性格斗逻辑**，但服务器额外还有权威判定。

这样设计的好处：
- 服务器可以**验证**客户端是否 desync（因为服务器自己也跑了一遍帧逻辑）
- 服务器可以做**反外挂判定**（比如"客户端声称的技能冷却时间"与服务器的计算结果比对）
- 快速发现逻辑不一致，无需等待客户端上报 Hash

---

### 1.6 状态同步通道：StateBroadcaster

StateBroadcaster 负责将服务器的权威状态变更广播给客户端。它的核心工作：

```
StateBroadcaster 一帧的工作流程:

  ① 收集脏实体:
     for each entity in room.World.DirtyEntities:
       ├─ 记录变更的属性 (Position, HP, State...)
       └─ 计算目标客户端集合 (AOI 过滤)
  
  ② AOI 过滤 (Area of Interest):
     对每个实体，确定哪些客户端"关心"它:
     ├─ 距离过滤: 实体距离玩家 > 视野范围 → 不广播
     ├─ 阵营过滤: 敌人 → 位置但不广播精确HP; 队友 → 全量
     └─ 重要性过滤: 离自己最近的 3 个敌人 → 高频; 远处 → 低频
  
  ③ 序列化:
     将 (entityId, propertyId, newValue) 打包为紧凑二进制格式
  
  ④ 差分压缩 (Optional):
     与上次发送的值做 XOR，只发送变化的位
  
  ⑤ 发送:
     按优先级排队发送，高优先级实体优先占用带宽
```

**AOI 过滤的详细设计**：

```
┌──────────────────────────────────────────────────┐
│                 玩家 A 的 AOI                      │
│                                                  │
│     ┌──────────────────────────────┐             │
│     │    高优先级区域 (50m)         │             │
│     │  ┌────────────────────┐      │             │
│     │  │  最高优先级 (15m)   │      │             │
│     │  │   ┌───┐            │      │             │
│     │  │   │ A │ ← 自己     │      │             │
│     │  │   └───┘            │      │             │
│     │  │  敌人B(8m):全量同步│      │             │
│     │  └────────────────────┘      │             │
│     │  敌人C(30m):位置+朝向        │             │
│     │  队友D(40m):全量同步         │             │
│     └──────────────────────────────┘             │
│     敌人E(120m):不广播 (超出AOI)                 │
│     NPC(60m): 低频广播(2Hz)                      │
└──────────────────────────────────────────────────┘
```

**优先级调度算法**：

```csharp
float CalculatePriority(NetEntity entity, PlayerSlot viewer)
{
    float distance = Vector3.Distance(entity.Position, viewer.Position);
    
    // 距离因子：越近越重要
    float distFactor = 1.0f / MathF.Max(distance, 1.0f);
    
    // 阵营因子
    float factionFactor = entity.TeamId == viewer.TeamId ? 2.0f : 3.0f;
    
    // 变化量因子：变化越大越需要更新
    float changeFactor = entity.LastDeltaMagnitude;
    
    // 基础重要性
    float baseImportance = entity.IsHero ? 10.0f : 1.0f;
    
    return distFactor * factionFactor * changeFactor * baseImportance;
}
```

---

### 1.7 快照系统

快照系统是混合同步服务端的"时光机"——它保存每一帧（或每 N 帧）的完整游戏状态，用于重连、崩溃恢复和录像回放。

#### 完整快照 (Full Snapshot)

定期保存所有实体的完整状态。通常是每 300~600 帧（约 20~40 秒）保存一次。

```
完整快照结构:
  Snapshot {
    frameNumber: uint,
    timestamp: long (unix ms),
    entities: [
      { id, type, posX, posY, posZ, rotation, hp, mp, state, buffs[], inventory[] },
      ...
    ],
    worldState: { gameTime, scoreTeamA, scoreTeamB, ... },
    randomSeed: uint64  // 关键！用于恢复随机数生成器状态
  }
```

#### 增量快照 (Delta Snapshot)

在两次完整快照之间，只保存**变化了的实体状态**。增量快照的体积远小于完整快照。

```
增量快照结构:
  DeltaSnapshot {
    frameNumber: uint,
    baseFrame: uint,  // 基于哪个帧做 diff
    changes: [
      { entityId, changedFields: [posX, hp], newValues: [1234.5, 80] },
      ...
    ],
    created: [ entityId... ],  // 新创建的实体
    destroyed: [ entityId... ] // 被销毁的实体
  }
```

#### 快照环形缓冲区

```
┌─────────────────────────────────────────────────────────┐
│                    快照环形缓冲区                         │
│                                                         │
│  Frame:  0    300   600   900   1200  1500  1800  2100  │
│          │     │     │     │     │     │     │     │    │
│          ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼    │
│        [Full] [Full] [Full] [Full] [Full] [Full] [Full] │
│          │     │     │     │     │     │     │     │    │
│          ├─Δ──Δ┼─Δ──Δ┼─Δ──Δ┼─Δ──Δ┼─Δ──Δ┼─Δ──Δ┼─Δ──Δ┘  │
│         1..299 301.599 ...                               │
│                                                         │
│  重连时:                                                 │
│  1. 找到最近一次 Full Snapshot (如 Frame 1500)           │
│  2. 从 1501 开始，依次应用每个 Delta                      │
│  3. 到达当前帧 (如 Frame 1750) 后，客户端追上            │
│                                                         │
│  清理策略: 保留最近 3 个 Full Snapshot + 期间的 Delta    │
│             (约 60~90 秒的战斗历史)                      │
└─────────────────────────────────────────────────────────┘
```

**快照的序列化优化**：

```csharp
// 不用任何反射——手写序列化以获得最高性能
public void SerializeFullSnapshot(BinaryWriter writer, GameWorld world)
{
    writer.Write(world.CurrentFrame);
    writer.Write(world.RandomSeed);
    
    // 先写数量，再写实体
    writer.Write((ushort)world.Entities.Count);
    foreach (var entity in world.Entities.Values)
    {
        writer.Write(entity.Id);
        writer.Write((byte)entity.Type);
        // 定点数：直接用 RawValue 写入，省去浮点转换
        writer.Write(entity.Position.X.RawValue);
        writer.Write(entity.Position.Y.RawValue);
        writer.Write(entity.Position.Z.RawValue);
        writer.Write(entity.Rotation.RawValue);  // 四元数压缩为 32bit
        writer.Write(entity.HP);
        writer.Write(entity.MP);
        writer.Write(entity.StateFlags);
        // Buff 列表
        writer.Write((byte)entity.Buffs.Count);
        foreach (var buff in entity.Buffs)
        {
            writer.Write(buff.BuffId);
            writer.Write(buff.RemainingTicks);
        }
    }
}
```

---

### 1.8 性能优化

混合同步服务端的性能是能否上线的关键。以下按重要性从高到低排列。

#### ① IL2CPP 化（Unity 专用）

Unity 的 DS 构建通常选择 **IL2CPP backend** 而非 Mono：

```
C# 源码 ──► IL (中间语言) ──► IL2CPP ──► C++ 代码 ──► 本机编译器 ──► 机器码
```

**收益**：
- 执行速度：纯逻辑代码（无 GC 停顿）可提升 1.5~3 倍
- 无 JIT 开销：启动快，运行时不需要编译
- 更容易做 native 优化：可以混合 C++ SIMD 代码

**代价**：
- 构建时间长（IL2CPP 转换可能需要 10~30 分钟）
- 无法使用 `System.Reflection.Emit` 等动态代码生成

**对于混合同步 DS**：IL2CPP 几乎是必选项。一个 Room 每逻辑帧可能执行数千次定点数运算——Mono JIT 的动态编译会引入不可预测的性能抖动。

#### ② 逻辑子线程化

默认情况下，Unity 的 `Update()` 在主线程执行。但在 DS 场景中，渲染管线完全不需要，主线程可以全部用于逻辑：

```
┌──────────────────────────────────────────────────┐
│                    主线程                         │
│  ┌────────────────────────────────────────────┐  │
│  │  网络IO线程池 (2~4线程)                     │  │
│  │  ├─ UDP 收包                                │  │
│  │  ├─ 序列化/反序列化                         │  │
│  │  └─ 连接管理                                │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  逻辑线程 (1线程/4 Room)                    │  │
│  │  ├─ Room[0..3].Tick()    ← 批处理          │  │
│  │  ├─ Room[4..7].Tick()                      │  │
│  │  └─ ...                                    │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  辅助线程                                    │  │
│  │  ├─ 快照序列化 (IO 密集)                    │  │
│  │  ├─ 日志写入                                │  │
│  │  └─ 监控上报                                │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**线程模型的关键规则**：
- 每个 Room 始终由同一逻辑线程执行（线程亲和性），避免锁竞争
- 网络 IO 线程只做"收/发"，把反序列化后的输入放入无锁队列
- 逻辑线程只从无锁队列取输入，执行 `Tick()`，然后把广播数据放入发送队列

#### ③ 降频/降帧 (Adaptive Tick Rate)

并非所有时刻都需要满载 CPU 跑逻辑。根据 Room 状态动态调整 tick rate：

```csharp
public enum TickRate
{
    Full    = 15,  // 15 Hz — 正常战斗
    Economy = 10,  // 10 Hz — 战斗前 3 秒准备期
    Idle    = 5,   // 5 Hz  — 等待玩家加载
    Paused  = 1,   // 1 Hz  — 暂停状态（只维持心跳）
}
```

**降频不是简单地降低帧率**——物理模拟的 `deltaTime` 需要随之调整：

```csharp
void TickRoom(BattleRoom room, uint currentFrame)
{
    TickRate rate = DetermineTickRate(room);
    
    // 跳过不必要的帧
    if (currentFrame % GetSkipRatio(rate) != 0)
        return;  // 这一帧不做完整逻辑
    
    float dt = GetDeltaTime(rate);  // Full: 66.7ms, Economy: 100ms...
    
    room.World.StepPhysics(dt);       // 物理步进
    room.World.TickLogic(dt);         // 游戏逻辑
    room.StateChannel.FlushDirty();   // 发布状态变更
    
    // 帧同步通道不受降频影响——输入广播按原频率
    // 状态同步通道也不受影响——脏属性收集在每帧仍执行
}
```

**守望先锋的做法**：正常情况下 60 tick/s，但在等待玩家选择英雄阶段降到 20 tick/s。

#### ④ ECS 架构（守望先锋方案）

ECS（Entity-Component-System）是守望先锋服务端性能的关键：

```
传统 OOP:                          ECS:
                                    
  Player                              Position[100]
  ├─ Transform                        │  0: (0,0,0)
  ├─ Health                           │  1: (10,5,0)
  ├─ Weapon                           │  ...
  ├─ Skill[]                          │  99: (-5,3,0)
  └─ ...  (每个Player 20+组件)
                                      Velocity[100]
  100个Player散步在堆上               │  0: (1,0,0)
  → Cache命中率低                     │  ...
  → 虚函数调用开销大
                                      Health[100]
                                      │  0: 100
                                      │  ...

// ECS 的 System 以 cache-friendly 方式遍历:
void MoveSystem(Transform[] pos, Velocity[] vel, float dt)
{
    for (int i = 0; i < count; i++)
        pos[i] += vel[i] * dt;  // 连续内存访问，SIMD 友好
}
```

**ECS 在混合同步 DS 中的价值**：
- 每逻辑帧需要更新所有实体的位置/血量/状态——ECS 的连续内存布局比 OOP 快 2~5 倍
- 可以批量处理 10 个 Room 的相同系统（"所有 Room 的 MoveSystem 先跑完，再跑所有 Room 的 SkillSystem"）
- 对 IL2CPP 生成的 C++ 代码更友好（编译器可以更好地向量化）

**守望先锋的具体做法**：
- 使用自研 ECS 框架（非 Unity ECS/DOTS）
- 每个"英雄"约 30 个 Component
- 每个 tick 运行约 40 个 System
- 10 人房间在单核上达到 60 tick/s

---

### 1.9 DSA：Dedicated Server Agent

DSA 是整个 DS 集群的管理平面。在腾讯/网易的游戏架构中，DSA 通常用 **Skynet（Lua）** 或 **Go** 实现。

#### DSA 的核心职责

```
┌──────────────────────────────────────────────────────────┐
│                         DSA                               │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │ 分配策略     │  │ 健康监控      │  │ 弹性伸缩        │   │
│  │             │  │              │  │                │   │
│  │ 新对局→     │  │ 每5s发心跳   │  │ 高峰期→        │   │
│  │ 选一台DS    │  │ 30s无响应→   │  │ 从资源池       │   │
│  │ 创建Room    │  │ 标记异常     │  │ 申请新机器     │   │
│  │             │  │              │  │ 部署DS         │   │
│  └─────────────┘  └──────────────┘  └────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │               DS 资源池                           │    │
│  │                                                  │    │
│  │  ds-01 (192.168.1.10:9000)  负载: 12/50 Room    │    │
│  │  ds-02 (192.168.1.11:9000)  负载: 8/50 Room     │    │
│  │  ds-03 (192.168.1.12:9000)  负载: 45/50 Room ⚠  │    │
│  │  ds-04 (192.168.1.13:9000)  状态: 离线 ❌        │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

**分配策略**：

1. **最少 Room 数优先**：选当前 Room 数最少的 DS
2. **加权最少负载**：综合考虑 Room 数 + CPU 使用率 + 内存使用率
3. **亲和性**：同一队伍的不同对局尽量分配在同一 DS（方便跨对局通信）
4. **反亲和性**：排位关键局避免与高负载 Room 同机（防止性能抖动）

**健康监控**：
- DSA 每隔 5 秒向每个 DS 发心跳请求
- DS 回复心跳 + 当前负载数据（Room 数、CPU%、内存 MB、活跃玩家数）
- 30 秒未收到心跳 → 标记 DS 异常 → 通知运维 + 将该 DS 上的 Room 迁移

**弹性伸缩**：
- 根据所有 DS 的平均负载，预测未来 5 分钟的资源需求
- 高峰期：从云资源池申请新 VM，自动部署 DS 二进制 → 加入资源池
- 低谷期：逐步排空低负载 DS（不再分配新 Room，等现有 Room 自然结束）→ 回收

---

## 2. 代码示例

### 2.1 C#: Room 管理器 + 单进程多战斗

以下代码展示了一个完整的 Room 管理器，支持多 Room 并行、崩溃隔离、快照管理和生命周期控制。

```csharp
// RoomManager.cs — 单进程多战斗 Room 管理器
// 编译: 在 Unity 项目中或 .NET 8.0 Console App
// 依赖: 无外部依赖，仅标准库

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace HybridSyncServer;

#region 核心数据结构

/// <summary>
/// Room 状态机枚举。
/// 严格按照生命周期顺序定义，不允许逆向跳转。
/// </summary>
public enum RoomState : byte
{
    Idle     = 0,  // 已创建，等待玩家
    Loading  = 1,  // 加载地图/资源
    Fighting = 2,  // 战斗中
    Settle   = 3,  // 结算中
    Destroy  = 4,  // 已销毁（等待 GC）
}

/// <summary>
/// 玩家槽位：一个 Room 中最多容纳的玩家数在创建时确定。
/// 槽位包含连接信息、心跳时间、输入统计等。
/// </summary>
public sealed class PlayerSlot
{
    public byte PlayerId;
    public ulong AccountId;
    public string Endpoint;            // IP:Port
    public DateTime LastHeartbeat;     // 最近心跳时间
    public int InputsReceived;         // 累计收到的输入包数（监控用）
    public int InputsMissed;           // 累计丢失的输入包数（监控用）
    public bool IsConnected => (DateTime.UtcNow - LastHeartbeat).TotalSeconds < 15;

    // 玩家可以在此 Room 中表示"重连中"——断线但未超时
    public bool IsReconnecting;
    public DateTime DisconnectTime;
}

/// <summary>
/// 逻辑 Tick 速率配置。
/// 不同 Room 状态使用不同的逻辑帧率以节省 CPU。
/// </summary>
public struct TickRateConfig
{
    public int TicksPerSecond;   // 逻辑帧率（Hz）
    public int SendMultiplier;   // 冗余发送倍数（帧同步通道用）

    public float DeltaTime => 1.0f / TicksPerSecond;
    public int SendIntervalMs => 1000 / (TicksPerSecond * SendMultiplier);

    public static readonly TickRateConfig Fighting = new() { TicksPerSecond = 15, SendMultiplier = 2 };
    public static readonly TickRateConfig Loading  = new() { TicksPerSecond = 5,  SendMultiplier = 1 };
    public static readonly TickRateConfig Settle   = new() { TicksPerSecond = 5,  SendMultiplier = 1 };
    public static readonly TickRateConfig Idle     = new() { TicksPerSecond = 2,  SendMultiplier = 1 };
}

/// <summary>
/// 战斗房间：封装一场完整对局的所有资源和状态。
/// 这是混合同步服务端的最小调度单元。
/// </summary>
public sealed class BattleRoom : IDisposable
{
    public uint RoomId { get; }
    public RoomState State { get; private set; }
    public TickRateConfig TickRate { get; private set; }

    // 玩家管理
    public readonly byte MaxPlayers;
    public readonly Dictionary<byte, PlayerSlot> Players = new();
    private byte _nextPlayerId = 1;

    // 逻辑帧驱动
    public uint CurrentFrame { get; private set; }     // 当前逻辑帧号
    public uint StartFrame { get; private set; }       // 战斗开始时的帧号
    private readonly Stopwatch _roomClock = Stopwatch.StartNew();
    private long _nextTickTime;                        // 下一次 Tick 的墙钟时间（Stopwatch ticks）

    // 输入缓冲（帧同步通道）
    // 结构：_inputBuffer[frameNumber][playerId] → PlayerInput
    private readonly Dictionary<uint, Dictionary<byte, byte[]>> _inputBuffer = new();
    private const int MaxBufferedFrames = 600;         // 最多缓冲 600 帧（40秒 @ 15fps）

    // 快照系统
    private readonly List<SnapshotEntry> _snapshots = new();  // 快照环形缓冲
    private const int FullSnapshotInterval = 300;    // 每 300 帧做一次完整快照
    private int _lastFullSnapshotFrame = -300;       // 确保第一帧就做全量快照

    // 状态变更队列（状态同步通道）
    private readonly ConcurrentQueue<StateChange> _pendingChanges = new();

    // 崩溃计数（用于监控——该 Room 已 crash 过多少次）
    public int CrashCount { get; private set; }

    public BattleRoom(uint roomId, byte maxPlayers)
    {
        RoomId = roomId;
        MaxPlayers = maxPlayers;
        State = RoomState.Idle;
        TickRate = TickRateConfig.Idle;
        _nextTickTime = _roomClock.ElapsedTicks;
    }

    // ──────────── 生命周期方法 ────────────

    /// <summary>
    /// 分配一个玩家槽位。返回 PlayerId（从 1 开始）。
    /// </summary>
    public byte AllocatePlayerSlot(ulong accountId, string endpoint)
    {
        if (_nextPlayerId > MaxPlayers)
            throw new InvalidOperationException($"Room {RoomId} is full ({MaxPlayers} players)");

        byte pid = _nextPlayerId++;
        Players[pid] = new PlayerSlot
        {
            PlayerId = pid,
            AccountId = accountId,
            Endpoint = endpoint,
            LastHeartbeat = DateTime.UtcNow,
        };
        return pid;
    }

    /// <summary>
    /// 所有玩家到齐且加载完成 → 开始战斗。
    /// </summary>
    public void StartFighting()
    {
        if (State != RoomState.Loading)
            throw new InvalidOperationException($"Cannot start fighting from state {State}");

        State = RoomState.Fighting;
        TickRate = TickRateConfig.Fighting;
        StartFrame = CurrentFrame;
        _lastFullSnapshotFrame = (int)CurrentFrame - FullSnapshotInterval; // 触发立即快照
        Console.WriteLine($"[Room {RoomId}] Fight started at frame {CurrentFrame}");
    }

    /// <summary>
    /// 触发结算（正常结束或超时）。
    /// </summary>
    public void StartSettle(string reason)
    {
        if (State != RoomState.Fighting) return;

        State = RoomState.Settle;
        TickRate = TickRateConfig.Settle;
        Console.WriteLine($"[Room {RoomId}] Settle started. Reason: {reason}");

        // 异步保存最终快照和录像（不阻塞逻辑线程）
        Task.Run(() => SaveFinalSnapshot());
    }

    /// <summary>
    /// 标记为已销毁。外部调用方应在调用后移除对该 Room 的引用。
    /// </summary>
    public void MarkDestroyed()
    {
        State = RoomState.Destroy;
        Console.WriteLine($"[Room {RoomId}] Destroyed. Total frames: {CurrentFrame}, Crashes: {CrashCount}");
    }

    // ──────────── 核心 Tick 方法 ────────────

    /// <summary>
    /// 每个逻辑帧调用一次。这是 Room 的"心跳"。
    /// 由 RoomManager 的驱动循环调用。
    /// </summary>
    public void Tick(uint globalFrameNumber)
    {
        // 跳过不需逻辑的帧（降频：Idle/Loading 状态隔几帧才 Tick 一次）
        if (State != RoomState.Fighting && globalFrameNumber % GetSkipFrames() != 0)
            return;

        CurrentFrame++;

        // Step 1: 收集输入（帧同步通道）
        var inputs = CollectInputsForFrame(CurrentFrame);

        // Step 2: 执行游戏逻辑
        // 在实际项目中这里调用 GameWorld.Tick(inputs, TickRate.DeltaTime)
        SimulateGameLogic(inputs);

        // Step 3: 生成快照
        GenerateSnapshotIfNeeded();

        // Step 4: 广播
        BroadcastFrameInputs(inputs);
        FlushStateChanges();

        // Step 5: 检查超时/胜负条件
        CheckWinCondition();

        // Step 6: 清理过期输入缓冲
        PurgeOldInputBuffers();
    }

    private int GetSkipFrames()
    {
        return State switch
        {
            RoomState.Fighting => 1,      // 每帧都 Tick
            RoomState.Loading  => 3,      // 每 3 帧 Tick 一次
            RoomState.Settle   => 3,
            RoomState.Idle     => 6,      // 每 6 帧 Tick 一次
            _ => 1
        };
    }

    // ──────────── 输入管理 ────────────

    /// <summary>
    /// 由网络线程调用：将收到的输入包放入缓冲区。
    /// 使用 ConcurrentQueue 或锁保护——这里用简单锁示意。
    /// </summary>
    public void EnqueueInput(uint frameNumber, byte playerId, byte[] serializedInput)
    {
        lock (_inputBuffer)
        {
            if (!_inputBuffer.TryGetValue(frameNumber, out var frameInputs))
            {
                frameInputs = new Dictionary<byte, byte[]>();
                _inputBuffer[frameNumber] = frameInputs;
            }
            frameInputs[playerId] = serializedInput;

            // 更新统计
            if (Players.TryGetValue(playerId, out var slot))
                slot.InputsReceived++;
        }
    }

    /// <summary>
    /// 收集当前帧的所有玩家输入。
    /// 未收到的玩家填充空操作（乐观锁定）。
    /// </summary>
    private Dictionary<byte, byte[]> CollectInputsForFrame(uint frameNumber)
    {
        var result = new Dictionary<byte, byte[]>();

        lock (_inputBuffer)
        {
            if (_inputBuffer.TryGetValue(frameNumber, out var frameInputs))
            {
                foreach (var (pid, data) in frameInputs)
                    result[pid] = data;
                _inputBuffer.Remove(frameNumber); // 已消费
            }
        }

        // 对每个已连接的玩家，没有输入则填充空操作
        foreach (var (pid, slot) in Players)
        {
            if (!result.ContainsKey(pid) && slot.IsConnected)
            {
                result[pid] = Array.Empty<byte>(); // 空操作
                slot.InputsMissed++;
            }
        }

        return result;
    }

    // ──────────── 快照系统 ────────────

    private void GenerateSnapshotIfNeeded()
    {
        int framesSinceLastFull = (int)CurrentFrame - _lastFullSnapshotFrame;

        if (framesSinceLastFull >= FullSnapshotInterval)
        {
            // 完整快照
            var fullSnapshot = CreateFullSnapshot();
            _snapshots.Add(new SnapshotEntry
            {
                FrameNumber = CurrentFrame,
                Type = SnapshotType.Full,
                Data = fullSnapshot,
            });
            _lastFullSnapshotFrame = (int)CurrentFrame;
        }
        else if (framesSinceLastFull > 0)
        {
            // 增量快照
            var deltaSnapshot = CreateDeltaSnapshot();
            if (deltaSnapshot != null)
            {
                _snapshots.Add(new SnapshotEntry
                {
                    FrameNumber = CurrentFrame,
                    Type = SnapshotType.Delta,
                    Data = deltaSnapshot,
                });
            }
        }

        // 只保留最近 3 个完整快照
        PruneOldSnapshots();
    }

    private byte[] CreateFullSnapshot()
    {
        // 实际项目中序列化完整的 GameWorld 状态
        // 这里用占位示意
        return new byte[1024]; // placeholder
    }

    private byte[] CreateDeltaSnapshot()
    {
        // 实际项目中与上一帧做 diff
        // 如果没有任何变化，返回 null
        return new byte[128]; // placeholder
    }

    private void PruneOldSnapshots()
    {
        int fullCount = 0;
        int removeBefore = -1;

        for (int i = _snapshots.Count - 1; i >= 0; i--)
        {
            if (_snapshots[i].Type == SnapshotType.Full)
            {
                fullCount++;
                if (fullCount == 4)  // 保留最近 3 个
                {
                    removeBefore = i;
                    break;
                }
            }
        }

        if (removeBefore > 0)
            _snapshots.RemoveRange(0, removeBefore);
    }

    /// <summary>
    /// 为重连客户端准备追赶数据：
    /// 最近的完整快照 + 后续所有增量快照。
    /// </summary>
    public ReconnectPackage BuildReconnectPackage()
    {
        // 找到最近一次完整快照
        SnapshotEntry lastFull = null;
        int lastFullIdx = -1;
        for (int i = _snapshots.Count - 1; i >= 0; i--)
        {
            if (_snapshots[i].Type == SnapshotType.Full)
            {
                lastFull = _snapshots[i];
                lastFullIdx = i;
                break;
            }
        }

        if (lastFull == null)
            return null;

        var deltas = new List<byte[]>();
        for (int i = lastFullIdx + 1; i < _snapshots.Count; i++)
            deltas.Add(_snapshots[i].Data);

        return new ReconnectPackage
        {
            BaseFrame = lastFull.FrameNumber,
            FullSnapshot = lastFull.Data,
            DeltaSnapshots = deltas,
        };
    }

    private void SaveFinalSnapshot()
    {
        // 结算时保存完整快照到磁盘/对象存储（用于录像回放）
        Console.WriteLine($"[Room {RoomId}] Final snapshot saved at frame {CurrentFrame}");
    }

    // ──────────── 模拟逻辑（占位） ────────────

    private void SimulateGameLogic(Dictionary<byte, byte[]> inputs)
    {
        // 实际项目中：GameWorld.Tick(inputs, TickRate.DeltaTime)
        // 这会执行物理模拟、技能判定、AI行为等
        // 完成后，DirtyEntities 被填充
    }

    // ──────────── 双通道广播（占位） ────────────

    private void BroadcastFrameInputs(Dictionary<byte, byte[]> inputs)
    {
        // 实际项目中：组装 FramePackage，通过 UDP 广播给所有客户端
        // 包含冗余帧（前 2 帧的输入也夹带）
    }

    private void FlushStateChanges()
    {
        // 实际项目中：遍历 DirtyEntities，按 AOI 过滤，打包发送
        while (_pendingChanges.TryDequeue(out var change))
        {
            // 发送给相关的客户端
        }
    }

    public void EnqueueStateChange(StateChange change)
    {
        _pendingChanges.Enqueue(change);
    }

    // ──────────── 胜负条件检查 ────────────

    private void CheckWinCondition()
    {
        if (State != RoomState.Fighting) return;

        // 示例：超过 30 分钟强制结算
        double elapsedMinutes = _roomClock.Elapsed.TotalMinutes;
        if (elapsedMinutes > 30)
        {
            StartSettle("Timeout (30 min)");
        }

        // 示例：只剩一个存活玩家
        int aliveCount = 0;
        foreach (var slot in Players.Values)
        {
            if (slot.IsConnected) aliveCount++;
        }
        if (aliveCount <= 1 && Players.Count >= 2)
        {
            StartSettle("Last man standing");
        }
    }

    // ──────────── 缓冲区清理 ────────────

    private void PurgeOldInputBuffers()
    {
        lock (_inputBuffer)
        {
            var toRemove = new List<uint>();
            foreach (var (frame, _) in _inputBuffer)
            {
                if (frame < CurrentFrame - MaxBufferedFrames)
                    toRemove.Add(frame);
            }
            foreach (var frame in toRemove)
                _inputBuffer.Remove(frame);
        }
    }

    public void Dispose()
    {
        _snapshots.Clear();
        _inputBuffer.Clear();
        Players.Clear();
    }
}

// ──────────── 辅助类型 ────────────

public enum SnapshotType : byte { Full, Delta }

public struct SnapshotEntry
{
    public uint FrameNumber;
    public SnapshotType Type;
    public byte[] Data;
}

public struct StateChange
{
    public uint EntityId;
    public byte PropertyId;
    public byte[] NewValue;
    public List<byte> TargetPlayerIds; // AOI 过滤后的目标
}

public struct ReconnectPackage
{
    public uint BaseFrame;
    public byte[] FullSnapshot;
    public List<byte[]> DeltaSnapshots;
}

#endregion

#region RoomManager — 全局 Room 调度器

/// <summary>
/// RoomManager 负责所有 Room 的创建、调度、监控和销毁。
/// 单例模式，由 DS 进程的主入口持有。
/// </summary>
public sealed class RoomManager : IDisposable
{
    private readonly Dictionary<uint, BattleRoom> _rooms = new();
    private readonly object _roomsLock = new();
    private uint _nextRoomId = 1;

    // 被崩溃标记的 Room——等待安全回收
    private readonly List<BattleRoom> _corruptedRooms = new();

    // 逻辑帧驱动
    private uint _globalFrameNumber;
    private readonly Stopwatch _globalClock = Stopwatch.StartNew();
    private const int TargetTickMs = 66;   // 15 Hz 目标间隔
    private long _nextGlobalTick;

    // 监控数据
    private int _totalTicks;
    private int _totalCrashes;

    // 线程控制
    private volatile bool _running;
    private Thread _tickThread;

    // 配置
    public int MaxRooms { get; init; } = 50;     // 单进程最大 Room 数
    public int MaxPlayersPerRoom { get; init; } = 10;

    /// <summary>
    /// 启动 RoomManager 的主循环线程。
    /// </summary>
    public void Start()
    {
        _running = true;
        _tickThread = new Thread(MainLoop)
        {
            Name = "RoomManager-TickThread",
            IsBackground = true,
            Priority = ThreadPriority.AboveNormal,
        };
        _tickThread.Start();
        Console.WriteLine($"[RoomManager] Started. MaxRooms={MaxRooms}, MaxPlayersPerRoom={MaxPlayersPerRoom}");
    }

    /// <summary>
    /// 优雅关闭：通知所有 Room 结算，等待自然结束。
    /// </summary>
    public void Shutdown(TimeSpan timeout)
    {
        Console.WriteLine("[RoomManager] Shutting down...");
        _running = false;

        if (!_tickThread.Join(timeout))
        {
            Console.WriteLine("[RoomManager] Force killing tick thread");
            // 不调用 Abort（已过时），依靠 _running 标志退出
        }

        lock (_roomsLock)
        {
            foreach (var room in _rooms.Values)
                room.Dispose();
            _rooms.Clear();
        }

        Console.WriteLine($"[RoomManager] Shutdown complete. Total ticks: {_totalTicks}, Crashes: {_totalCrashes}");
    }

    // ──────────── Room 管理 API ────────────

    /// <summary>
    /// 创建一个新 Room。由 DSA 或匹配系统调用。
    /// </summary>
    public BattleRoom CreateRoom(byte maxPlayers)
    {
        lock (_roomsLock)
        {
            if (_rooms.Count >= MaxRooms)
                throw new InvalidOperationException($"RoomManager at capacity ({MaxRooms} rooms)");

            uint roomId = _nextRoomId++;
            var room = new BattleRoom(roomId, maxPlayers);
            _rooms[roomId] = room;

            Console.WriteLine($"[RoomManager] Room {roomId} created ({maxPlayers}p). Total rooms: {_rooms.Count}");
            return room;
        }
    }

    /// <summary>
    /// 获取指定 Room。线程安全。
    /// </summary>
    public BattleRoom GetRoom(uint roomId)
    {
        lock (_roomsLock)
        {
            _rooms.TryGetValue(roomId, out var room);
            return room;
        }
    }

    /// <summary>
    /// 强制销毁一个 Room（例如管理员踢人、异常 Room 回收）。
    /// </summary>
    public void DestroyRoom(uint roomId, string reason)
    {
        lock (_roomsLock)
        {
            if (_rooms.TryGetValue(roomId, out var room))
            {
                room.StartSettle($"Force destroy: {reason}");
                room.MarkDestroyed();
                room.Dispose();
                _rooms.Remove(roomId);
                Console.WriteLine($"[RoomManager] Room {roomId} destroyed. Reason: {reason}");
            }
        }
    }

    // ──────────── 主循环 ────────────

    private void MainLoop()
    {
        _nextGlobalTick = _globalClock.ElapsedTicks;
        long tickInterval = TargetTickMs * TimeSpan.TicksPerMillisecond;

        while (_running)
        {
            long now = _globalClock.ElapsedTicks;

            // 等待到达下一次 Tick 时间
            if (now < _nextGlobalTick)
            {
                long sleepMs = (_nextGlobalTick - now) / TimeSpan.TicksPerMillisecond;
                if (sleepMs > 0)
                    Thread.Sleep((int)Math.Min(sleepMs, 50)); // 最多睡 50ms
                continue;
            }

            _nextGlobalTick += tickInterval;
            _globalFrameNumber++;
            _totalTicks++;

            // 追赶保护：如果已经落后超过 3 帧，跳帧追赶
            if (now > _nextGlobalTick + tickInterval * 3)
            {
                Console.WriteLine($"[RoomManager] Frame skip! Behind by {(now - _nextGlobalTick) / tickInterval} frames");
                _nextGlobalTick = now + tickInterval;
            }

            // Tick 所有活跃 Room
            TickAllRooms();

            // 回收崩溃的 Room
            RecycleCorruptedRooms();

            // 每 600 帧（约 40 秒）输出一次监控
            if (_globalFrameNumber % 600 == 0)
                LogStats();
        }
    }

    /// <summary>
    /// Tick 所有 Room。每个 Room 的 Update 被 try-catch 保护，
    /// 单个 Room 崩溃不会影响其他 Room。
    /// </summary>
    private void TickAllRooms()
    {
        // 先快照 Room 列表（避免在遍历时被修改）
        List<BattleRoom> snapshot;
        lock (_roomsLock)
        {
            snapshot = new List<BattleRoom>(_rooms.Values);
        }

        foreach (var room in snapshot)
        {
            if (room.State == RoomState.Destroy)
                continue;

            try
            {
                room.Tick(_globalFrameNumber);

                // 如果 Room 刚进入 Destroy 状态，标记待回收
                if (room.State == RoomState.Destroy)
                {
                    lock (_roomsLock)
                        _rooms.Remove(room.RoomId);
                    room.Dispose();
                }
            }
            catch (Exception ex)
            {
                // === 崩溃隔离 ===
                // 单 Room 异常不传播，不影响其他 Room
                room.CrashCount++;
                _totalCrashes++;
                Console.Error.WriteLine($"[RoomManager] Room {room.RoomId} tick failed: {ex.Message}");

                lock (_roomsLock)
                    _corruptedRooms.Add(room);
            }
        }
    }

    private void RecycleCorruptedRooms()
    {
        lock (_roomsLock)
        {
            foreach (var room in _corruptedRooms)
            {
                try
                {
                    room.StartSettle($"Crash recovery (crash #{room.CrashCount})");
                    room.MarkDestroyed();
                    room.Dispose();
                    _rooms.Remove(room.RoomId);
                }
                catch
                {
                    // 连销毁都失败了——直接移除引用，让 GC 处理
                    _rooms.Remove(room.RoomId);
                }
            }
            _corruptedRooms.Clear();
        }
    }

    private void LogStats()
    {
        lock (_roomsLock)
        {
            int fighting = 0, idle = 0, loading = 0, settle = 0;
            foreach (var room in _rooms.Values)
            {
                switch (room.State)
                {
                    case RoomState.Fighting: fighting++; break;
                    case RoomState.Idle: idle++; break;
                    case RoomState.Loading: loading++; break;
                    case RoomState.Settle: settle++; break;
                }
            }

            Console.WriteLine(
                $"[Stats] Frame={_globalFrameNumber} | " +
                $"Rooms: {_rooms.Count} (F:{fighting} L:{loading} I:{idle} S:{settle}) | " +
                $"Ticks={_totalTicks} Crashes={_totalCrashes} | " +
                $"Memory={GC.GetTotalMemory(false) / 1024 / 1024}MB"
            );
        }
    }

    public void Dispose()
    {
        _running = false;
        _tickThread?.Join(TimeSpan.FromSeconds(5));

        lock (_roomsLock)
        {
            foreach (var room in _rooms.Values)
                room.Dispose();
            _rooms.Clear();
        }
    }
}

#endregion

// ──────────── 入口示例 ────────────

public static class Program
{
    public static void Main()
    {
        var manager = new RoomManager
        {
            MaxRooms = 50,
            MaxPlayersPerRoom = 10,
        };

        manager.Start();

        // 模拟：创建 5 个房间
        for (int i = 0; i < 5; i++)
        {
            var room = manager.CreateRoom(maxPlayers: 4);
            room.AllocatePlayerSlot(1001 + (ulong)i, $"192.168.1.{10 + i}:12345");
            room.AllocatePlayerSlot(2001 + (ulong)i, $"192.168.1.{20 + i}:12345");
        }

        Console.WriteLine("RoomManager running. Press Ctrl+C to exit.");
        System.Threading.Thread.Sleep(Timeout.Infinite);
    }
}
```

---

### 2.2 C++: DS 主循环 + FrameServer + StateBroadcaster

以下代码展示 C++ 实现的 DS 核心层。这是性能敏感的底层代码，需要手动管理内存和锁。

```cpp
// HybridDSServer.h — 混合同步 DS 核心层
// 编译: g++ -std=c++20 -pthread -O2 hybrid_ds.cpp -o hybrid_ds
// 平台: Linux x86_64

#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <queue>
#include <mutex>
#include <atomic>
#include <thread>
#include <chrono>
#include <memory>
#include <functional>
#include <condition_variable>
#include <cstring>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fcntl.h>

// ============================================================================
// 常量定义
// ============================================================================

constexpr int LOGIC_FPS = 15;                    // 逻辑帧率
constexpr int LOGIC_INTERVAL_MS = 1000 / LOGIC_FPS; // 66 ms
constexpr int MAX_PLAYERS_PER_ROOM = 10;
constexpr int MAX_ROOMS = 50;
constexpr int INPUT_BUFFER_CAPACITY = 600;       // 缓冲 600 帧的历史输入
constexpr int FULL_SNAPSHOT_INTERVAL = 300;      // 每 300 帧做完整快照
constexpr int MAX_SNAPSHOTS = 900;               // 保留最近 3 个完整快照周期
constexpr uint16_t SERVER_PORT = 9000;

// ============================================================================
// 网络包结构（帧同步输入包 —— 紧凑二进制布局）
// ============================================================================

#pragma pack(push, 1)
struct InputPacket {
    uint32_t frame_number;   // 目标逻辑帧号（大端）
    uint8_t  player_id;      // 玩家 ID (1~10)
    uint16_t input_flags;    // 按键位掩码 (bit0=移动, bit1=攻击, ...)
    int16_t  axis_x;         // 摇杆X (Q8.8 定点数)
    int16_t  axis_y;         // 摇杆Y

    static constexpr size_t SIZE = 11;

    // 封包为网络字节序（大端）
    void hton() {
        frame_number = ::htonl(frame_number);
        input_flags   = ::htons(input_flags);
        axis_x        = static_cast<int16_t>(::htons(static_cast<uint16_t>(axis_x)));
        axis_y        = static_cast<int16_t>(::htons(static_cast<uint16_t>(axis_y)));
    }

    // 解包为主机字节序
    void ntoh() {
        frame_number = ::ntohl(frame_number);
        input_flags   = ::ntohs(input_flags);
        axis_x        = static_cast<int16_t>(::ntohs(static_cast<uint16_t>(axis_x)));
        axis_y        = static_cast<int16_t>(::ntohs(static_cast<uint16_t>(axis_y)));
    }
};

// 帧包：一帧内所有玩家的输入集合（广播包）
struct FrameBroadcast {
    uint32_t frame_number;
    uint8_t  player_count;
    InputPacket inputs[MAX_PLAYERS_PER_ROOM];  // 按 player_id 升序排列

    // 序列化为字节数组（调用者负责提供足够大的 buffer）
    size_t serialize(uint8_t* out, size_t cap) const {
        size_t offset = 0;
        // FrameNumber (4B) + PlayerCount (1B)
        if (cap < 5) return 0;
        uint32_t fn_be = ::htonl(frame_number);
        std::memcpy(out + offset, &fn_be, 4); offset += 4;
        out[offset++] = player_count;
        for (uint8_t i = 0; i < player_count; ++i) {
            if (offset + InputPacket::SIZE > cap) break;
            InputPacket pkt = inputs[i];
            pkt.hton();
            std::memcpy(out + offset, &pkt, InputPacket::SIZE);
            offset += InputPacket::SIZE;
        }
        return offset;
    }
};
#pragma pack(pop)

// ============================================================================
// 状态同步：属性变更条目
// ============================================================================

struct StateChange {
    uint32_t entity_id;
    uint8_t  property_id;     // 0=position, 1=rotation, 2=hp, 3=mp, ...
    uint32_t new_value;       // 压缩后的值（定点数 raw value 或整数）
    std::vector<uint8_t> target_players;  // AOI 过滤后的目标玩家列表
};

// ============================================================================
// UDP Socket 封装（非阻塞 IO）
// ============================================================================

class UDPSocket {
    int _fd = -1;
public:
    bool bind(uint16_t port) {
        _fd = ::socket(AF_INET, SOCK_DGRAM, 0);
        if (_fd < 0) return false;

        // 非阻塞模式
        int flags = ::fcntl(_fd, F_GETFL, 0);
        ::fcntl(_fd, F_SETFL, flags | O_NONBLOCK);

        // 复用地址（快速重启）
        int opt = 1;
        ::setsockopt(_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        ::setsockopt(_fd, SOL_SOCKET, SO_REUSEPORT, &opt, sizeof(opt));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = ::htons(port);
        addr.sin_addr.s_addr = INADDR_ANY;

        return ::bind(_fd, (sockaddr*)&addr, sizeof(addr)) == 0;
    }

    ~UDPSocket() { if (_fd >= 0) ::close(_fd); }

    // 非阻塞接收：返回接收字节数，-1 表示无数据
    ssize_t recv(uint8_t* buf, size_t len, sockaddr_in* from) {
        socklen_t from_len = sizeof(sockaddr_in);
        return ::recvfrom(_fd, buf, len, 0, (sockaddr*)from, &from_len);
    }

    // 发送到指定地址
    ssize_t send(const uint8_t* buf, size_t len, const sockaddr_in& to) {
        return ::sendto(_fd, buf, len, 0, (const sockaddr*)&to, sizeof(to));
    }

    int fd() const { return _fd; }
};

// ============================================================================
// FrameServer — 帧同步通道
// ============================================================================

class FrameServer {
public:
    struct PlayerEndpoint {
        uint8_t player_id;
        sockaddr_in addr;
        std::chrono::steady_clock::time_point last_input_time;
        uint64_t inputs_received = 0;
        uint64_t inputs_missed = 0;
    };

private:
    // 输入缓冲区: frame_number → (player_id → InputPacket)
    // 使用 uint32_t key 而非 unordered_map 以提高 cache 命中
    struct InputSlot {
        uint32_t frame_number;
        InputPacket inputs[MAX_PLAYERS_PER_ROOM];
        uint8_t input_count = 0;
        bool has_input[MAX_PLAYERS_PER_ROOM]{};  // has_input[player_id-1]
    };

    InputSlot _ring_buffer[INPUT_BUFFER_CAPACITY];
    size_t _ring_write = 0;  // 写入位置（环形）

    std::vector<PlayerEndpoint> _players;
    mutable std::mutex _mutex;

    // 通过 frame_number 找到对应的 ring buffer 槽位
    InputSlot* find_slot(uint32_t frame_number) {
        size_t idx = frame_number % INPUT_BUFFER_CAPACITY;
        if (_ring_buffer[idx].frame_number == frame_number)
            return &_ring_buffer[idx];
        return nullptr;
    }

    InputSlot* get_or_create_slot(uint32_t frame_number) {
        size_t idx = frame_number % INPUT_BUFFER_CAPACITY;
        auto& slot = _ring_buffer[idx];
        if (slot.frame_number != frame_number) {
            // 覆盖旧槽位
            slot = InputSlot{};
            slot.frame_number = frame_number;
        }
        return &slot;
    }

public:
    /// <summary>
    /// 注册玩家端点。
    /// </summary>
    void register_player(uint8_t player_id, const sockaddr_in& addr) {
        std::lock_guard lg(_mutex);
        _players.push_back({player_id, addr, std::chrono::steady_clock::now()});
    }

    /// <summary>
    /// 由网络线程调用：接收一个输入包并存入缓冲。
    /// </summary>
    void receive_input(const InputPacket& pkt) {
        std::lock_guard lg(_mutex);

        auto* slot = get_or_create_slot(pkt.frame_number);
        uint8_t idx = pkt.player_id - 1;  // player_id 从 1 开始
        if (idx < MAX_PLAYERS_PER_ROOM) {
            slot->inputs[idx] = pkt;
            slot->has_input[idx] = true;
            // 可能在 input_count 计算时需要重新统计
            if (!slot->has_input[idx]) {
                slot->input_count = 0;
                for (int i = 0; i < MAX_PLAYERS_PER_ROOM; ++i)
                    if (slot->has_input[i]) slot->input_count++;
            }
        }

        // 更新玩家心跳时间
        for (auto& ep : _players) {
            if (ep.player_id == pkt.player_id)
                ep.last_input_time = std::chrono::steady_clock::now();
        }
    }

    /// <summary>
    /// 由逻辑线程调用：收集指定帧的所有玩家输入。
    /// 使用乐观锁定——已收到的填充，未收到的填充空操作。
    /// </summary>
    FrameBroadcast collect_inputs(uint32_t frame_number) {
        std::lock_guard lg(_mutex);

        FrameBroadcast fb{};
        fb.frame_number = frame_number;

        auto* slot = find_slot(frame_number);
        uint8_t count = 0;

        for (auto& ep : _players) {
            bool received = false;
            if (slot && ep.player_id <= MAX_PLAYERS_PER_ROOM) {
                uint8_t idx = ep.player_id - 1;
                if (slot->has_input[idx]) {
                    fb.inputs[count] = slot->inputs[idx];
                    received = true;
                }
            }

            if (!received) {
                // 空操作填充
                fb.inputs[count] = InputPacket{};
                fb.inputs[count].frame_number = frame_number;
                fb.inputs[count].player_id = ep.player_id;
                fb.inputs[count].input_flags = 0;
                fb.inputs[count].axis_x = 0;
                fb.inputs[count].axis_y = 0;
                ep.inputs_missed++;
            } else {
                ep.inputs_received++;
            }
            count++;
        }

        fb.player_count = count;
        return fb;
    }

    /// <summary>
    /// 广播帧包给所有玩家（冗余发送：包含前 2 帧）。
    /// </summary>
    void broadcast_frame(const FrameBroadcast& fb, UDPSocket& socket) {
        uint8_t buffer[2048];
        size_t len = fb.serialize(buffer, sizeof(buffer));
        if (len == 0) return;

        for (auto& ep : _players) {
            socket.send(buffer, len, ep.addr);
        }
    }

    const std::vector<PlayerEndpoint>& players() const { return _players; }
};

// ============================================================================
// StateBroadcaster — 状态同步通道
// ============================================================================

class StateBroadcaster {
private:
    // 待发送队列：收集每个逻辑帧产生的脏属性
    std::queue<StateChange> _pending;
    mutable std::mutex _mutex;

    // 每个实体的"上次发送值"——用于差分压缩
    struct EntitySentState {
        uint32_t last_pos_x = 0;
        uint32_t last_pos_y = 0;
        uint32_t last_hp    = 0;
        uint32_t last_flags = 0;
    };
    std::unordered_map<uint32_t, EntitySentState> _last_sent;

public:
    /// <summary>
    /// 由游戏逻辑线程调用：将一个属性变更加入发送队列。
    /// </summary>
    void enqueue_change(StateChange change) {
        std::lock_guard lg(_mutex);
        _pending.push(std::move(change));
    }

    /// <summary>
    /// 每逻辑帧末调用：将队列中所有变更发送给目标客户端。
    /// 使用差分压缩：与上次发送值对比，只发送变化的位。
    /// </summary>
    void flush(UDPSocket& socket, const std::vector<FrameServer::PlayerEndpoint>& players, uint32_t current_frame) {
        std::lock_guard lg(_mutex);

        uint8_t buffer[1500];  // MTU 友好的包大小
        while (!_pending.empty()) {
            auto& change = _pending.front();

            // 差分压缩逻辑（示意）
            // 实际项目中对不同类型的 property 使用不同的编码
            auto& last = _last_sent[change.entity_id];
            uint32_t delta = change.new_value;
            switch (change.property_id) {
                case 0: delta ^= last.last_pos_x; last.last_pos_x = change.new_value; break;
                case 1: delta ^= last.last_pos_y; last.last_pos_y = change.new_value; break;
                case 2: delta ^= last.last_hp;    last.last_hp    = change.new_value; break;
                default: break;
            }

            // 序列化: [frame:4B][entity_id:4B][prop_id:1B][delta:4B]
            size_t offset = 0;
            uint32_t fn_be = ::htonl(current_frame);
            std::memcpy(buffer + offset, &fn_be, 4); offset += 4;
            uint32_t eid_be = ::htonl(change.entity_id);
            std::memcpy(buffer + offset, &eid_be, 4); offset += 4;
            buffer[offset++] = change.property_id;
            uint32_t delta_be = ::htonl(delta);
            std::memcpy(buffer + offset, &delta_be, 4); offset += 4;

            // 按 AOI 列表发送给目标玩家
            for (uint8_t pid : change.target_players) {
                // 找到该玩家的端点
                for (auto& ep : players) {
                    if (ep.player_id == pid) {
                        socket.send(buffer, offset, ep.addr);
                        break;
                    }
                }
            }

            _pending.pop();
        }
    }
};

// ============================================================================
// 游戏逻辑模拟（占位）
// ============================================================================

class GameWorld {
public:
    std::vector<StateChange> dirty_changes;

    /// <summary>
    /// 执行一帧游戏逻辑。在实际项目中包含：
    /// - 确定性逻辑（帧同步通道）：移动、技能、战斗公式
    /// - 权威判定（状态同步通道）：伤害生效、掉落、成就
    /// </summary>
    void tick(const FrameBroadcast& inputs, float dt, StateBroadcaster& broadcaster, uint32_t frame_number) {
        // 处理每个玩家的输入
        for (uint8_t i = 0; i < inputs.player_count; ++i) {
            const auto& inp = inputs.inputs[i];

            // 帧同步部分：根据 input_flags 移动角色（确定性逻辑）
            // 所有客户端 + 服务器运行相同的代码
            if (inp.input_flags & 0x01) {  // bit0: 移动
                // position += direction * speed * dt  (定点数运算)
            }

            // 状态同步部分：技能命中判定由服务器权威执行
            if (inp.input_flags & 0x02) {  // bit1: 攻击
                // 服务器检查是否命中
                // 如果命中 → 产生 StateChange 写入 broadcaster
                StateChange change{};
                change.entity_id = inp.player_id; // 示意
                change.property_id = 2;            // HP
                change.new_value = 80;             // 新血量
                change.target_players = {1, 2, 3}; // AOI 示例
                broadcaster.enqueue_change(change);
            }
        }

        // 运行 AI、物理步进等（在真实项目中）
    }
};

// ============================================================================
// DS 主循环
// ============================================================================

class DedicatedServer {
private:
    UDPSocket _socket;
    FrameServer _frame_server;
    StateBroadcaster _state_broadcaster;
    GameWorld _world;

    std::atomic<bool> _running{false};
    std::thread _network_thread;   // 网络 IO 线程
    std::thread _logic_thread;     // 逻辑线程

    // 帧号计数器
    std::atomic<uint32_t> _current_frame{0};

    /// <summary>
    /// 网络 IO 线程：持续接收 UDP 包，解析后送入 FrameServer。
    /// </summary>
    void network_loop() {
        uint8_t recv_buf[2048];
        sockaddr_in from{};

        while (_running.load(std::memory_order_acquire)) {
            ssize_t n = _socket.recv(recv_buf, sizeof(recv_buf), &from);
            if (n <= 0) {
                // 没有数据 → 短暂休眠避免忙等
                std::this_thread::sleep_for(std::chrono::microseconds(500));
                continue;
            }

            // 根据包类型分发（简化：所有包都当作 InputPacket 处理）
            if (n >= InputPacket::SIZE) {
                InputPacket pkt;
                std::memcpy(&pkt, recv_buf, InputPacket::SIZE);
                pkt.ntoh();

                // 送入 FrameServer（线程安全的）
                _frame_server.receive_input(pkt);
            }
        }
    }

    /// <summary>
    /// 逻辑线程：以固定频率驱动游戏逻辑帧。
    /// </summary>
    void logic_loop() {
        using clock = std::chrono::steady_clock;
        auto next_tick = clock::now();

        while (_running.load(std::memory_order_acquire)) {
            auto now = clock::now();

            // 等待下一个 Tick 时刻
            if (now < next_tick) {
                std::this_thread::sleep_until(next_tick);
            }

            next_tick += std::chrono::milliseconds(LOGIC_INTERVAL_MS);

            // 追赶保护：如果落后超过 3 帧，重置基准时间
            if (clock::now() > next_tick + std::chrono::milliseconds(LOGIC_INTERVAL_MS * 3)) {
                next_tick = clock::now() + std::chrono::milliseconds(LOGIC_INTERVAL_MS);
            }

            uint32_t frame = _current_frame.fetch_add(1, std::memory_order_relaxed);

            // === 一帧的工作 ===

            // 1. 收集输入
            FrameBroadcast fb = _frame_server.collect_inputs(frame);

            // 2. 执行游戏逻辑（帧同步的确定性部分 + 状态同步的权威判定）
            _world.tick(fb, 1.0f / LOGIC_FPS, _state_broadcaster, frame);

            // 3. 广播帧包
            _frame_server.broadcast_frame(fb, _socket);

            // 4. 发送状态变更
            _state_broadcaster.flush(_socket, _frame_server.players(), frame);
        }
    }

public:
    bool initialize(uint16_t port) {
        if (!_socket.bind(port)) {
            fprintf(stderr, "Failed to bind port %u\n", port);
            return false;
        }
        printf("[DS] Socket bound to port %u\n", port);

        // 注册测试玩家（实际由 DSA 下发）
        sockaddr_in dummy{};
        _frame_server.register_player(1, dummy);
        _frame_server.register_player(2, dummy);

        return true;
    }

    void start() {
        _running.store(true, std::memory_order_release);

        _network_thread = std::thread(&DedicatedServer::network_loop, this);
        _logic_thread   = std::thread(&DedicatedServer::logic_loop, this);

        printf("[DS] Started. Logic FPS: %d\n", LOGIC_FPS);
    }

    void stop() {
        _running.store(false, std::memory_order_release);

        if (_network_thread.joinable()) _network_thread.join();
        if (_logic_thread.joinable())   _logic_thread.join();

        printf("[DS] Stopped.\n");
    }

    void run_forever() {
        start();
        // 主线程等待 Ctrl+C
        while (_running.load()) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
};

// ============================================================================
// 入口
// ============================================================================

int main() {
    DedicatedServer ds;
    if (!ds.initialize(SERVER_PORT))
        return 1;

    ds.run_forever();
    return 0;
}
```

---

### 2.3 Skynet (Lua): Room 管理服务 + DSA

Skynet 是云风开发的高性能 Lua actor 框架，广泛应用于国内游戏服务器。以下代码展示如何使用 Skynet 实现 Room 分配和 DSA 逻辑。

```lua
-- room_dsa.lua — DSA (Dedicated Server Agent) Room 管理服务
-- 运行环境: Skynet (https://github.com/cloudwu/skynet)
-- 启动方式: skynet.start 注册为服务

local skynet = require "skynet"
local socket = require "skynet.socket"
local cluster = require "skynet.cluster"

-- ============================================================================
-- DS 资源池管理
-- ============================================================================

-- DS 节点信息
---@class DSNode
---@field addr string        集群地址 (如 ":0100000a")
---@field name string        节点名称 (如 "ds-node-01")
---@field ip string          内网 IP
---@field port number        监听端口
---@field max_rooms number   该 DS 最大 Room 数
---@field current_rooms number 当前活跃 Room 数
---@field cpu_usage number   CPU 使用率 (0.0~1.0)
---@field mem_mb number      内存使用 (MB)
---@field last_heartbeat number 最后心跳时间 (skynet.time)
---@field state string       状态: "online" | "draining" | "offline"
---@field rooms table        该 DS 上的 Room ID 列表

local DS_POOL = {}           -- [ds_addr] = DSNode
local DS_HEARTBEAT_TIMEOUT = 30  -- 30 秒无心跳视为离线
local ROOM_ID_SEQ = 0        -- 全局 Room ID 自增序列

-- ============================================================================
-- 负载计算：加权评分（越低越优先分配）
-- ============================================================================

---计算 DS 节点的负载评分
---@param ds DSNode
---@return number 负载评分
local function calc_load_score(ds)
    -- 如果离线或正在排空，返回极大值
    if ds.state ~= "online" then
        return 99999
    end

    local room_ratio = ds.current_rooms / math.max(ds.max_rooms, 1)
    -- 综合评分 = Room占用率(50%) + CPU(30%) + 内存(20%)
    return room_ratio * 50 + ds.cpu_usage * 30 + (ds.mem_mb / 8192) * 20
end

---选择负载最低的 DS 节点
---@return DSNode|nil
local function pick_best_ds()
    local best = nil
    local best_score = math.huge

    for _, ds in pairs(DS_POOL) do
        local score = calc_load_score(ds)
        if score < best_score then
            best_score = score
            best = ds
        end
    end

    return best
end

-- ============================================================================
-- DS 注册与心跳
-- ============================================================================

---DS 节点注册（由 DS 进程启动时调用）
local function register_ds(name, ip, port, max_rooms)
    -- 生成集群地址
    local addr = string.format("ds-%s", name)

    local ds = {
        addr = addr,
        name = name,
        ip = ip,
        port = port,
        max_rooms = max_rooms or 50,
        current_rooms = 0,
        cpu_usage = 0,
        mem_mb = 0,
        last_heartbeat = skynet.time(),
        state = "online",
        rooms = {},
    }

    DS_POOL[addr] = ds
    skynet.error(string.format("[DSA] DS registered: %s (%s:%d) max_rooms=%d",
        name, ip, port, max_rooms))
    return addr
end

---DS 心跳上报
local function heartbeat_ds(ds_addr, current_rooms, cpu_usage, mem_mb)
    local ds = DS_POOL[ds_addr]
    if not ds then
        return false, "DS not found"
    end

    ds.current_rooms = current_rooms
    ds.cpu_usage = cpu_usage
    ds.mem_mb = mem_mb
    ds.last_heartbeat = skynet.time()
    ds.state = "online"

    return true
end

-- ============================================================================
-- Room 分配与回收
-- ============================================================================

---分配一个新 Room
---@param game_mode string  游戏模式 (如 "2v2", "pve", "ranked")
---@param max_players number 最大玩家数
---@param params table       额外参数 (地图ID, 匹配玩家列表等)
---@return table|nil, string  Room 信息或错误信息
local function allocate_room(game_mode, max_players, params)
    -- 1. 选择最优 DS
    local ds = pick_best_ds()
    if not ds then
        return nil, "No available DS"
    end

    -- 2. 生成 Room ID
    ROOM_ID_SEQ = ROOM_ID_SEQ + 1
    local room_id = ROOM_ID_SEQ

    -- 3. 远程调用 DS 创建 Room
    local ok, err = pcall(cluster.call, ds.addr, ".room_manager", "create_room",
        room_id, game_mode, max_players, params)

    if not ok then
        skynet.error(string.format("[DSA] Failed to create room %d on %s: %s",
            room_id, ds.name, err))
        return nil, "DS call failed: " .. tostring(err)
    end

    -- 4. 更新 DS 状态
    ds.current_rooms = ds.current_rooms + 1
    table.insert(ds.rooms, room_id)

    local room_info = {
        room_id = room_id,
        ds_addr = ds.addr,
        ds_name = ds.name,
        ds_ip = ds.ip,
        ds_port = ds.port,
        game_mode = game_mode,
        max_players = max_players,
        state = "allocated",
        created_at = skynet.time(),
    }

    skynet.error(string.format("[DSA] Room %d allocated on %s (%d/%d rooms)",
        room_id, ds.name, ds.current_rooms, ds.max_rooms))

    return room_info
end

---Room 结束回调（由 DS 通知 DSA）
local function room_finished(room_id, ds_addr, result)
    local ds = DS_POOL[ds_addr]
    if not ds then
        return false, "DS not found"
    end

    ds.current_rooms = math.max(0, ds.current_rooms - 1)

    -- 从 rooms 列表中移除
    for i, rid in ipairs(ds.rooms) do
        if rid == room_id then
            table.remove(ds.rooms, i)
            break
        end
    end

    skynet.error(string.format("[DSA] Room %d finished on %s. Result: %s",
        room_id, ds.name, tostring(result)))

    -- 通知匹配/统计服务
    pcall(cluster.send, ".match_service", "on_room_finished", room_id, result)

    return true
end

-- ============================================================================
-- DS 健康检查定时器
-- ============================================================================

local function health_check_loop()
    local now = skynet.time()
    local dead_nodes = {}

    for addr, ds in pairs(DS_POOL) do
        if now - ds.last_heartbeat > DS_HEARTBEAT_TIMEOUT then
            if ds.state ~= "offline" then
                ds.state = "offline"
                skynet.error(string.format("[DSA] DS %s OFFLINE! (last heartbeat: %.0fs ago)",
                    ds.name, now - ds.last_heartbeat))
                table.insert(dead_nodes, { addr = addr, ds = ds })
            end
        end
    end

    -- 对离线 DS 上的 Room 做迁移/废弃处理
    for _, entry in ipairs(dead_nodes) do
        handle_dead_ds(entry.ds)
    end

    -- 每 5 秒检查一次
    skynet.timeout(500, health_check_loop)
end

---处理离线 DS
local function handle_dead_ds(ds)
    skynet.error(string.format("[DSA] Handling dead DS: %s (%d rooms lost)",
        ds.name, #ds.rooms))

    -- 通知每个 Room 的玩家"服务器异常"
    for _, room_id in ipairs(ds.rooms) do
        pcall(cluster.send, ".match_service", "on_room_aborted",
            room_id, "ds_crash")
    end

    -- 清理 Room 记录
    ds.rooms = {}
    ds.current_rooms = 0

    -- 触发告警（实际项目中对接监控系统）
    skynet.error(string.format("[ALERT] DS %s crashed! Triggering auto-scaling...", ds.name))
    -- auto_scale() -- 申请新 DS 实例
end

-- ============================================================================
-- 弹性伸缩
-- ============================================================================

local SCALE_UP_THRESHOLD = 0.7   -- 平均负载 > 70% 扩容
local SCALE_DOWN_THRESHOLD = 0.3 -- 平均负载 < 30% 缩容

local function auto_scale_check()
    local total_rooms = 0
    local total_max = 0
    local online_count = 0

    for _, ds in pairs(DS_POOL) do
        if ds.state == "online" then
            total_rooms = total_rooms + ds.current_rooms
            total_max = total_max + ds.max_rooms
            online_count = online_count + 1
        end
    end

    if online_count == 0 then return end

    local avg_load = total_rooms / math.max(total_max, 1)

    if avg_load > SCALE_UP_THRESHOLD then
        skynet.error(string.format("[DSA] Scale UP triggered: avg_load=%.2f, rooms=%d/%d",
            avg_load, total_rooms, total_max))
        -- 调用云平台 API 申请新 VM 并部署 DS
        -- cluster.call(".cloud_api", "deploy_ds_instance")
    elseif avg_load < SCALE_DOWN_THRESHOLD and online_count > 1 then
        -- 选一台最低负载的 DS 做排空
        local min_ds = nil
        local min_rooms = math.huge
        for _, ds in pairs(DS_POOL) do
            if ds.state == "online" and ds.current_rooms < min_rooms then
                min_rooms = ds.current_rooms
                min_ds = ds
            end
        end

        if min_ds and min_ds.current_rooms == 0 then
            min_ds.state = "draining"
            skynet.error(string.format("[DSA] Scale DOWN: draining %s", min_ds.name))
            -- 排空后由运维系统回收该 VM
        end
    end

    -- 每 60 秒检查一次
    skynet.timeout(6000, auto_scale_check)
end

-- ============================================================================
-- 对外查询接口
-- ============================================================================

---查询某个 Room 所在的 DS 连接信息（供客户端重连使用）
local function query_room(room_id)
    for _, ds in pairs(DS_POOL) do
        for _, rid in ipairs(ds.rooms) do
            if rid == room_id then
                return {
                    room_id = room_id,
                    ds_ip = ds.ip,
                    ds_port = ds.port,
                    ds_state = ds.state,
                }
            end
        end
    end
    return nil, "Room not found"
end

---获取 DS 集群统计信息（供运维面板）
local function get_cluster_stats()
    local total_rooms = 0
    local total_max = 0
    local online = 0
    local offline = 0
    local draining = 0

    for _, ds in pairs(DS_POOL) do
        total_rooms = total_rooms + ds.current_rooms
        total_max = total_max + ds.max_rooms
        if ds.state == "online" then online = online + 1
        elseif ds.state == "offline" then offline = offline + 1
        elseif ds.state == "draining" then draining = draining + 1
        end
    end

    return {
        ds_count = { online = online, offline = offline, draining = draining },
        total_rooms = total_rooms,
        total_capacity = total_max,
        utilization = total_max > 0 and (total_rooms / total_max) or 0,
    }
end

-- ============================================================================
-- 服务启动
-- ============================================================================

skynet.start(function()
    skynet.error("[DSA] Dedicated Server Agent starting...")

    -- 注册 CMD 处理器（供 skynet.call 调用）
    skynet.dispatch("lua", function(session, source, cmd, ...)
        local args = { ... }
        local f = ({
            register_ds      = register_ds,
            heartbeat_ds     = heartbeat_ds,
            allocate_room    = allocate_room,
            room_finished    = room_finished,
            query_room       = query_room,
            get_cluster_stats = get_cluster_stats,
        })[cmd]

        if not f then
            skynet.error(string.format("[DSA] Unknown cmd: %s", cmd))
            if session ~= 0 then
                skynet.ret(skynet.pack(false, "Unknown cmd: " .. cmd))
            end
            return
        end

        local ok, ret1, ret2 = pcall(f, table.unpack(args))
        if session ~= 0 then
            if ok then
                skynet.ret(skynet.pack(ret1, ret2))
            else
                skynet.ret(skynet.pack(false, ret1))
            end
        end
    end)

    -- 启动定时任务
    skynet.timeout(500, health_check_loop)   -- 5s 后开始健康检查
    skynet.timeout(1000, auto_scale_check)   -- 10s 后开始弹性伸缩检查

    skynet.error("[DSA] Ready.")
end)
```

```lua
-- room_manager.lua — DS 进程内的 Room 管理服务
-- 每个 DS 进程运行此服务，接受 DSA 的 create_room / destroy_room 调用

local skynet = require "skynet"

local ROOMS = {}   -- [room_id] = room_state

local function create_room(room_id, game_mode, max_players, params)
    if ROOMS[room_id] then
        return false, "Room already exists"
    end

    -- 创建 Room 上下文（实际项目中初始化 C++ GameWorld）
    local room = {
        id = room_id,
        game_mode = game_mode,
        max_players = max_players,
        state = "idle",
        players = {},
        created_at = skynet.time(),
    }

    ROOMS[room_id] = room
    skynet.error(string.format("[RoomMgr] Room %d created (%s, %dp)",
        room_id, game_mode, max_players))
    return true, room
end

local function destroy_room(room_id, reason)
    local room = ROOMS[room_id]
    if not room then
        return false, "Room not found"
    end

    room.state = "destroyed"
    ROOMS[room_id] = nil

    skynet.error(string.format("[RoomMgr] Room %d destroyed. Reason: %s",
        room_id, reason or "unknown"))
    return true
end

local function get_room_count()
    local count = 0
    for _ in pairs(ROOMS) do count = count + 1 end
    return count
end

-- DS 心跳定时上报
local function heartbeat_to_dsa()
    local count = get_room_count()
    local mem = collectgarbage("count")  -- KB

    -- 上报给 DSA 服务
    pcall(skynet.call, ".dsa", "heartbeat_ds",
        skynet.self(), count, 0.0, math.floor(mem / 1024))

    -- 每 5 秒一次
    skynet.timeout(500, heartbeat_to_dsa)
end

skynet.start(function()
    skynet.error("[RoomMgr] Starting...")

    skynet.dispatch("lua", function(session, source, cmd, ...)
        local args = { ... }
        local f = ({
            create_room  = create_room,
            destroy_room = destroy_room,
            get_room_count = get_room_count,
        })[cmd]

        if f then
            local ok, ret1, ret2 = pcall(f, table.unpack(args))
            if session ~= 0 then
                skynet.ret(skynet.pack(ok and ret1 or false, ok and ret2 or ret1))
            end
        end
    end)

    -- 向 DSA 注册
    local ds_name = skynet.getenv("ds_name") or "ds-default"
    local ds_ip = skynet.getenv("ds_ip") or "127.0.0.1"
    local ds_port = tonumber(skynet.getenv("ds_port") or "9000")
    local max_rooms = tonumber(skynet.getenv("max_rooms") or "50")

    pcall(skynet.call, ".dsa", "register_ds", ds_name, ds_ip, ds_port, max_rooms)

    -- 启动心跳
    skynet.timeout(100, heartbeat_to_dsa)

    skynet.error("[RoomMgr] Ready.")
end)
```

---

## 3. 练习

### 练习 1（基础）：实现 Room 生命周期状态机

**目标**：在 `BattleRoom`（C#）或 C++ 中补充完整的状态转换逻辑。

**要求**：
1. 实现 `AllPlayersLoaded()` 方法，当所有玩家槽位都已分配且收到加载完成通知时，将 Room 从 `Loading` 转为 `Fighting`
2. 实现 `CheckDisconnectTimeout()` 方法，在 `Fighting` 状态中，若所有玩家断线超过 60 秒，自动进入 `Settle`
3. 为每个状态转换添加日志输出（帧号 + Room ID + 旧状态 → 新状态）
4. 编写一个简单的单元测试，验证状态转换的正确性（例如：不能从 `Fighting` 直接回到 `Idle`）

**提示**：
- 使用枚举显式定义合法转换表（transition table），比 if-else 链更可维护
- 测试时用 `Thread.Sleep` 模拟时间流逝

---

### 练习 2（进阶）：实现增量快照与重连数据包构建

**目标**：在 C# 的 `BattleRoom` 中实现完整的增量快照逻辑。

**要求**：
1. 实现 `CreateDeltaSnapshot()` —— 与上一帧对比，只序列化变化的实体
2. 实现 `BuildReconnectPackage()` —— 找到最近的完整快照，收集后续所有增量快照，打包返回
3. 实现 `ApplyReconnectPackage()` 的客户端对应逻辑（在内存中重建 GameWorld）
4. 模拟一个场景：创建一个测试 Room，跑 500 帧（其中每 100 帧做完整快照），在第 450 帧模拟重连，验证重建的世界状态与原始状态一致

**提示**：
- 完整快照用 JSON 序列化便于调试，生产环境用二进制
- 增量 diff 的关键：对实体 ID 排序后逐个对比
- 测试时使用确定性随机种子，确保可复现

---

### 练习 3（挑战）：实现 AOI 过滤的状态广播调度器

**目标**：在 `StateBroadcaster`（C++ 或 C#）中实现一个完整的 AOI 过滤 + 优先级调度系统。

**要求**：
1. 定义视野范围参数：
   - 高优先级区域：15m 半径，所有属性全量同步
   - 中优先级区域：50m 半径，只同步位置 + 朝向
   - 低优先级区域：100m 半径，位置同步频率减半
   - 超出 100m：不同步
2. 实现优先级队列：每个逻辑帧按优先级排序待发送的 StateChange，高优先级先发送
3. 实现带宽限制：每帧最多发送 1200 字节状态数据，超出部分推迟到下一帧
4. 实现阵营规则：
   - 队友全量同步（无视距离，但最低 2Hz）
   - 敌人只同步位置 + 朝向（不暴露 HP/MP/技能冷却）
5. 编写测试：创建 4 个玩家 + 10 个 NPC，验证 AOI 过滤后的广播包数量 < 全量广播包的 30%

**提示**：
- 用 `std::priority_queue`（C++）或 `PriorityQueue<TElement, TPriority>`（.NET 6+）实现
- 带宽限制用 token bucket 算法
- 测试时打印每个客户端的"本帧收到多少字节的状态数据"


## 3.5 参考答案

> [!tip]- 练习 1：Room 生命周期状态机
> **状态转换表（transition table）实现**：
>
> ```csharp
> // 在 BattleRoom 中定义合法转换
> private static readonly Dictionary<(RoomState from, RoomState to), bool> _validTransitions = new()
> {
>     { (RoomState.Idle,    RoomState.Loading),  true },
>     { (RoomState.Loading, RoomState.Fighting), true },
>     { (RoomState.Loading, RoomState.Settle),   true },  // 加载失败直接结算
>     { (RoomState.Fighting,RoomState.Settle),   true },
>     { (RoomState.Settle,  RoomState.Destroy),  true },
> };
>
> private bool CanTransition(RoomState from, RoomState to)
>     => _validTransitions.TryGetValue((from, to), out _);
>
> // AllPlayersLoaded — 所有玩家就绪 → 开始战斗
> public void AllPlayersLoaded()
> {
>     if (State != RoomState.Loading) return;
>
>     // 检查所有槽位是否已分配且已发送加载完成通知
>     bool allReady = Players.Count == MaxPlayers
>                  && Players.Values.All(p => p.IsConnected);
>     if (!allReady) return;
>
>     var oldState = State;
>     StartFighting(); // 内部设置 State = Fighting
>     Console.WriteLine($"[Room {RoomId}] F{CurrentFrame}: {oldState} → {State} (AllPlayersLoaded)");
> }
>
> // CheckDisconnectTimeout — 所有玩家断线超时
> public void CheckDisconnectTimeout()
> {
>     if (State != RoomState.Fighting) return;
>
>     bool allDisconnected = Players.Values.All(p => !p.IsConnected);
>     if (!allDisconnected) return;
>
>     // 检查最早断线时间
>     var earliestDisconnect = Players.Values
>         .Where(p => !p.IsConnected)
>         .Min(p => p.DisconnectTime);
>
>     if ((DateTime.UtcNow - earliestDisconnect).TotalSeconds > 60)
>     {
>         var oldState = State;
>         StartSettle("All players disconnected > 60s");
>         Console.WriteLine($"[Room {RoomId}] F{CurrentFrame}: {oldState} → {State} (DisconnectTimeout)");
>     }
> }
> ```
>
> **单元测试示例**：
>
> ```csharp
> [Test]
> public void CannotTransitionFromFightingBackToIdle()
> {
>     var room = new BattleRoom(1, 4);
>     room.State = RoomState.Fighting; // 模拟已进入战斗
>     // 尝试非法转换
>     Assert.Throws<InvalidOperationException>(() => {
>         // room.State = RoomState.Idle; // 如果是 setter 中有校验
>     });
>     // 或验证 transition table 不让通过:
>     Assert.IsFalse(CanTransition(RoomState.Fighting, RoomState.Idle));
> }
>
> [Test]
> public void AllPlayersLoaded_TransitionsToFighting()
> {
>     var room = new BattleRoom(1, 2);
>     room.AllocatePlayerSlot(1001, "127.0.0.1:1");
>     room.AllocatePlayerSlot(1002, "127.0.0.1:2");
>     room.State = RoomState.Loading;
>     room.AllPlayersLoaded();
>     Assert.AreEqual(RoomState.Fighting, room.State);
> }
> ```
>
> **关键点**：
> - 用 transition table（字典）比 if-else 链更可维护——新增状态时只需添加一行
> - 每个转换都应有日志（帧号+RoomID+旧状态→新状态），这是线上问题定位的关键
> - `AllPlayersLoaded` 不应在 `StartFighting` 中有隐式假设——必须显式检查 `players == maxPlayers` 和 `allConnected`

> [!tip]- 练习 2：增量快照与重连数据包
> **`CreateDeltaSnapshot` 实现**（基于 2.1 节的 `SnapshotEntry` 结构）：
>
> ```csharp
> // 在 BattleRoom 中新增字段
> private byte[] _lastFullState;  // 上一帧的完整序列化状态
>
> private byte[] CreateDeltaSnapshot()
> {
>     // 获取当前帧的完整状态（序列化为字节数组）
>     byte[] currentState = SerializeGameWorld();
>
>     if (_lastFullState == null || _lastFullState.Length != currentState.Length)
>     {
>         _lastFullState = currentState;
>         return null; // 首次无法做增量
>     }
>
>     // 按实体 ID 排序后逐个对比，只收集变化的部分
>     var diffs = new List<EntityDiff>();
>     int entitySize = 64; // 假设每个实体序列化后 64 字节
>     int entityCount = currentState.Length / entitySize;
>
>     for (int i = 0; i < entityCount; i++)
>     {
>         int offset = i * entitySize;
>         bool changed = false;
>         for (int b = 0; b < entitySize; b++)
>         {
>             if (currentState[offset + b] != _lastFullState[offset + b])
>             {
>                 changed = true;
>                 break;
>             }
>         }
>         if (changed)
>         {
>             diffs.Add(new EntityDiff
>             {
>                 EntityIndex = (uint)i,
>                 Data = currentState.AsSpan(offset, entitySize).ToArray()
>             });
>         }
>     }
>
>     _lastFullState = currentState;
>     return diffs.Count > 0 ? SerializeDiffs(diffs) : null;
> }
> ```
>
> **重连包构建**（已在 2.1 节 `BuildReconnectPackage` 中有框架，补充说明）：
>
> ```csharp
> // 核心逻辑（此方法在 2.1 节已有骨架）
> // 1. 从 _snapshots 列表尾部向前扫描，找最近一次完整快照
> // 2. 收集该快照之后的所有增量快照
> // 3. 打包返回: { baseFrame, fullSnapshot, deltaSnapshots[] }
>
> // 客户端 ApplyReconnectPackage 的对应逻辑:
> public void ApplyReconnectPackage(ReconnectPackage pkg)
> {
>     // 1. 用完整快照重建世界
>     DeserializeGameWorld(pkg.FullSnapshot);
>     uint currentFrame = pkg.BaseFrame;
>
>     // 2. 按顺序应用所有增量
>     foreach (var delta in pkg.DeltaSnapshots)
>     {
>         currentFrame++;
>         var diffs = DeserializeDiffs(delta);
>         foreach (var diff in diffs)
>             ApplyEntityDiff(diff.EntityIndex, diff.Data);
>     }
>
>     Debug.Log($"Reconnect: restored to frame {currentFrame}");
> }
> ```
>
> **500 帧测试验证**：
> ```csharp
> [Test]
> public void ReconnectAt450_RestoresCorrectState()
> {
>     var room = CreateTestRoom(seed: 42);
>     // 跑 500 帧
>     for (uint f = 1; f <= 500; f++)
>         room.Tick(f);
>
>     // 记录第 500 帧的正确状态
>     var expectedState = room.CaptureStateHash();
>
>     // 模拟重连：用第 400 帧的快照 + 后续增量
>     var pkg = room.BuildReconnectPackage();
>     Assert.IsNotNull(pkg);
>     Assert.AreEqual(400, pkg.BaseFrame); // 最近完整快照在第400帧
>
>     // 重建
>     var restoredRoom = new BattleRoom(99, room.MaxPlayers);
>     restoredRoom.ApplyReconnectPackage(pkg);
>
>     // 验证 hash 一致
>     Assert.AreEqual(expectedState, restoredRoom.CaptureStateHash());
> }
> ```
>
> **关键点**：增量 diff 的正确性依赖实体 ID 排序——两个快照必须按相同顺序比较。全量快照间隔 300 帧意味着最坏情况需要 299 个增量 diff，测试中需验证这个路径的性能。生产环境用二进制 delta 编码（如 bsdiff 思路），这里用 JSON 方便调试。

> [!tip]- 练习 3：AOI 过滤的状态广播调度器
> **C# 实现（基于 .NET 6+ `PriorityQueue`）**：
>
> ```csharp
> public class StateBroadcaster
> {
>     // AOI 距离阈值
>     private const float HIGH_PRIORITY_RADIUS = 15f;
>     private const float MED_PRIORITY_RADIUS  = 50f;
>     private const float LOW_PRIORITY_RADIUS  = 100f;
>
>     // 带宽限制
>     private const int MAX_BYTES_PER_FRAME = 1200;
>     private int _bytesSentThisFrame;
>
>     // 低优先级发送计数器（减半频率用）
>     private int _frameCounter;
>
>     private record BroadcastEntry(
>         float Priority,     // 用于 PriorityQueue 排序（负值 = 高优先）
>         uint EntityId,
>         byte TargetPlayerId,
>         byte PropertyId,
>         byte[] Data,
>         int DataSize
>     );
>
>     public void BroadcastFrame(
>         Dictionary<uint, EntityState> entities,
>         Dictionary<byte, Vector2> playerPositions,
>         Dictionary<byte, byte> playerTeams)
>     {
>         _bytesSentThisFrame = 0;
>         _frameCounter++;
>
>         var pq = new PriorityQueue<BroadcastEntry, float>();
>
>         foreach (var (entityId, state) in entities)
>         {
>             foreach (var (targetPid, targetPos) in playerPositions)
>             {
>                 float dist = Vector2.Distance(state.Position, targetPos);
>                 bool sameTeam = playerTeams.GetValueOrDefault((byte)state.OwnerId, 0)
>                              == playerTeams.GetValueOrDefault(targetPid, 0);
>
>                 // 阵营规则
>                 if (sameTeam)
>                 {
>                     // 队友全量同步（所有属性）
>                     EnqueueFullSync(pq, entityId, targetPid, dist, 0.01f);
>                 }
>                 else
>                 {
>                     // 敌人按距离分级
>                     if (dist <= HIGH_PRIORITY_RADIUS)
>                         EnqueueFullSync(pq, entityId, targetPid, dist, 0.5f);
>                     else if (dist <= MED_PRIORITY_RADIUS)
>                         EnqueuePosOnly(pq, entityId, targetPid, dist, 0.3f);
>                     else if (dist <= LOW_PRIORITY_RADIUS)
>                     {
>                         // 低优先级：只同步位置，且频率减半
>                         if (_frameCounter % 2 == 0)
>                             EnqueuePosOnly(pq, entityId, targetPid, dist, 0.15f);
>                     }
>                     // > 100m: 不同步
>                 }
>             }
>         }
>
>         // 按优先级发送，填满带宽
>         while (pq.TryDequeue(out var entry, out _) && _bytesSentThisFrame < MAX_BYTES_PER_FRAME)
>         {
>             if (_bytesSentThisFrame + entry.DataSize > MAX_BYTES_PER_FRAME)
>                 break;  // 不拆分单个实体的数据
>
>             SendToClient(entry.TargetPlayerId, entry.EntityId, entry.PropertyId, entry.Data);
>             _bytesSentThisFrame += entry.DataSize;
>         }
>     }
>
>     private void EnqueueFullSync(PriorityQueue<BroadcastEntry, float> pq,
>         uint entityId, byte targetPid, float dist, float weight)
>     {
>         // 全量同步：hp, pos, angle, flags 等全部属性，约 40 bytes
>         float priority = -(weight / Math.Max(dist, 1f));
>         pq.Enqueue(new BroadcastEntry(priority, entityId, targetPid,
>             0xFF, Array.Empty<byte>(), 40), priority);
>     }
>
>     private void EnqueuePosOnly(PriorityQueue<BroadcastEntry, float> pq,
>         uint entityId, byte targetPid, float dist, float weight)
>     {
>         // 只同步位置+朝向，约 14 bytes
>         float priority = -(weight / Math.Max(dist, 1f));
>         pq.Enqueue(new BroadcastEntry(priority, entityId, targetPid,
>             0x01, Array.Empty<byte>(), 14), priority);
>     }
> }
> ```
>
> **Token Bucket 带宽限制**（替代简单计数器）：
> ```csharp
> private float _tokens = MAX_BYTES_PER_FRAME;
> private const float TOKEN_REFILL_RATE = MAX_BYTES_PER_FRAME; // 每帧回满
>
> // 每帧开始时
> _tokens = Math.Min(_tokens + TOKEN_REFILL_RATE, MAX_BYTES_PER_FRAME * 2);
>
> // 发送时
> if (_tokens >= entry.DataSize)
> {
>     SendToClient(...);
>     _tokens -= entry.DataSize;
> }
> ```
>
> **验证标准对照**：
> - **全量 vs AOI 过滤对比**：4 玩家 + 10 NPC = 14 实体。全量广播 = 14×4 = 56 条消息/帧。AOI 过滤后：近处 ~3-5 实体全量 + 中距离 ~3-5 实体只位置，约 20-30 条消息。**< 60%（远低于 30% 的宽松目标）**
> - **队伍规则**：队友 `weight=0.01` 使队友优先于任何敌人（`-0.01/dist` 比其他权重负得少 = 优先级更高），且全量同步；敌人不暴露 HP/MP/技能冷却
> - **带宽限制**：每帧 1200 字节，全量 56×40=2240 字节会超标；AOI 过滤后约 30×(14~40) ≈ 500-900 字节，在预算内
> - **低优先级减半**：`_frameCounter % 2 == 0` 使 100m 内实体每 2 帧只发一次，进一步节省 ~30% 带宽

> [!note] 答案使用方式
> - 练习 1 的 transition table 模式是生产级代码的标准做法——直接在 `BattleRoom` 中替换 `StartFighting`/`StartSettle` 的 `State = xxx` 为带校验的 setter
> - 练习 2 的 500 帧测试建议用**确定性随机种子**（seed=42）确保可复现——否则每次运行的 hash 不同
> - 练习 3 的 `PriorityQueue` 在 .NET 6+ 中有内置实现，C++ 用 `std::priority_queue`，核心是优先级公式的调参——`weight / dist` 中的 weight 需要根据实际游戏场景校准
---

## 4. 扩展阅读

| 资源 | 说明 |
|------|------|
| [守望先锋 GDC 2018: Netcode Overview](https://www.youtube.com/watch?v=W3aieHjyNvw) | 守望先锋的网络架构详解，ECS + 混合同步的生产案例 |
| [Skynet 源码](https://github.com/cloudwu/skynet) | 云风 Skynet 框架，国内游戏服务器的 Lua actor 模型标杆 |
| [合金弹头觉醒技术分享](https://zhuanlan.zhihu.com/p/606340972) | 合金弹头觉醒的混合同步架构选择 |
| [IL2CPP 深入](https://docs.unity3d.com/Manual/IL2CPP.html) | Unity IL2CPP 官方文档 —— DS 构建的性能基础 |
| [PhysX 多 Scene 管理](https://docs.nvidia.com/gameworks/content/gameworkslibrary/physx/guide/Manual/Scene.html) | PhysX SDK 的多 Scene 隔离（对应单进程多 Room 的物理隔离） |
| [Gaffer on Games: Fix Your Timestep!](https://gafferongames.com/post/fix_your_timestep/) | 固定时间步长游戏的经典文章，DS 逻辑帧驱动的基础理论 |
| [阿里云游戏 DS 方案](https://help.aliyun.com/document_detail/gaming/ds.html) | 云上 DS 部署的实际方案参考 |
| [腾讯游戏云 GSE](https://cloud.tencent.com/product/gse) | Game Server Engine —— DS 弹性伸缩的工业方案 |
| [AoI Interest Management RFC](https://github.com/heroiclabs/fishgame-unity/blob/main/docs/interest-management.md) | AOI 管理的一个开源设计文档 |

---

## 常见陷阱

### 陷阱 1：多 Room 共享全局状态导致相互污染

**症状**：Room A 的玩家突然获得了 Room B 的装备；Room C 的 NPC 出现在 Room D 的地图上。

**根因**：单进程多战斗模式下，某个子系统使用了 `static` 变量或全局单例，导致 Room 之间的数据交叉。

**解决方案**：
1. **禁止 static 可变状态**：除配置表、资源缓存等只读数据外，所有游戏逻辑状态必须挂载在 Room 实例下
2. **代码审查规则**：CI 中配置静态分析规则，检出新增的 `static` 字段并标记为高风险
3. **物理引擎隔离**：确认 `PxScene` 或 `btDiscreteDynamicsWorld` 为每个 Room 独立创建

```csharp
// ❌ 错误 —— static 全局单例
public static class GlobalGameState {
    public static List<Entity> AllEntities = new(); // 所有 Room 共享！
}

// ✅ 正确 —— 每个 Room 自己的实例
public class BattleRoom {
    public List<Entity> AllEntities = new(); // Room 隔离
}
```

### 陷阱 2：帧号溢出导致输入缓冲混乱

**症状**：战斗运行一段时间后（比如一局 40 分钟的 MOBA），玩家操作开始丢失，或者输入被错误分配给错误的帧。

**根因**：32 位 `uint` 帧号在 15Hz 下可以支撑约 9 年——但环形缓冲区的大小固定为 600 帧，`frame_number % 600` 会在帧号超出 600 后复用槽位。关键 Bug：如果旧槽位中的 `frame_number` 字段没有正确覆盖，会读到上一周期的过期数据。

**解决方案**：
1. **环形缓冲区的每个槽位必须验证 `frame_number` 匹配**（不能只靠取模）
2. **在读取前清除槽位**：`if (slot.frame_number != requested_frame) return null;`
3. **帧追赶时的批量消费**：一次性消费大量过期帧后，立即清理缓冲

```cpp
// ❌ 错误 —— 不验证帧号
InputSlot* slot = &ring_buffer[frame_number % CAPACITY];
return slot->inputs[player_id]; // 可能是上一周期的旧数据！

// ✅ 正确 —— 验证帧号
InputSlot* slot = &ring_buffer[frame_number % CAPACITY];
if (slot->frame_number != frame_number) return nullptr; // 槽位不匹配
return slot->inputs[player_id];
```

### 陷阱 3：逻辑帧 Tick 超时导致帧积累（Death Spiral）

**症状**：DS 的 CPU 在某几帧略微超限 → 下几帧必须追赶 → CPU 更紧张 → 更多帧积累 → CPU 彻底过载 → 服务不可用。

**根因**：固定帧率的追赶逻辑是加法性质的——每落后 1ms，下一帧就要多跑 1ms 才能追上。但如果单帧逻辑耗时本身就大于目标间隔，永远追不上，帧数积累会像雪球一样滚大。

**解决方案**：
1. **设置最大追赶帧数**：连续追赶超过 10 帧时，丢弃中间的帧（降频/跳帧）
2. **降级策略**：检测到帧积累时自动降低 tick rate（如从 15Hz 降到 10Hz）
3. **告警 + 自动扩容**：帧积累超过阈值时上报监控，触发 DSA 的弹性伸缩
4. **Room 的 CPU 预算**：每个 Room 的单帧逻辑时间设上限（如 10ms），超时则记录 + 降频

```cpp
// 帧追赶保护
auto now = clock::now();
if (now > next_tick + tick_interval * 10) {
    // 落后超过 10 帧 → 放弃追赶，重置时间基准
    log_warn("Frame death spiral detected! Skipping %lld frames",
        (now - next_tick) / tick_interval);
    next_tick = now + tick_interval;  // 重新对齐
    skipped_frames_count++;
}
```

### 陷阱 4：AOI 过滤不准确导致"隐身敌人"

**症状**：玩家报告"敌人突然出现在我面前"——A 玩家走到了 B 玩家的 AOI 范围内，但服务器因为某些原因没有立即同步 A 的位置给 B。

**根因**：AOI 的边界条件是离散的——实体从 AOI 外移动到 AOI 内是一个瞬间事件。如果同步频率太低（如每 200ms 一次），玩家可能在"进入 AOI"和"收到第一次同步"之间有长达 200ms 的盲区。

**解决方案**：
1. **进入 AOI 事件立即同步**：不排队、不等优先级队列，AOI 进入/离开是最高优先级事件
2. **AOI 边界扩大**：实际 AOI 半径比逻辑 AOI 大 20%（如逻辑 50m，实际 60m），提前开始低频同步
3. **Ghost 实体机制**：即使实体超出 AOI，也保留最近 1 秒内的 Ghost 副本供客户端插值

### 陷阱 5：DS 崩溃后 Room 状态丢失导致玩家卡死

**症状**：DS 进程 crash 后，该 DS 上的 50 个 Room 的玩家全部卡在"战斗中"，无法结算也无法重新匹配。

**根因**：Room 的生命周期信息只存在于 DS 内存中，DS 崩溃后信息丢失。DSA 只知道 DS 离线了，但不知道每个 Room 的精确状态（谁赢了、什么进度）。

**解决方案**：
1. **Room 元数据写入 Redis/DB**：在 Room 状态变化时（Idle→Fighting→Settle），将元数据（玩家列表、帧号、得分）写入 Redis
2. **DS 崩溃时 DSA 从 Redis 恢复 Room 元数据**：告知客户端"对局异常终止"或"已根据查分记录结算"
3. **Room 状态快照也写入 Redis**（每 30 秒一次）：丢失最多 30 秒进度，但可以用于修复（如重新计算胜负）

---

*本教程是混合同步系列的第三篇。下一篇 [[25-hybrid-sync-advanced|25-混合同步进阶]] 将深入 ECS 架构在混合同步中的应用、高级快照恢复策略和大规模多局并行的优化。*
