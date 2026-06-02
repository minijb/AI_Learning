# 观战系统：实时/延迟观战与 OB 视角

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 45min
> 前置知识: [26-录像与战斗回放系统](26-replay-systems.md)

---

## 1. 概念讲解

### 1.1 为什么需要观战系统？

观战系统不是"锦上添花"的功能。在竞技游戏的生态中，它支撑着三个核心场景：

| 场景 | 需求 | 观战模式 | 代表产品 |
|------|------|---------|---------|
| **电竞赛事直播** | 低延迟、多机位、导演切换 | 实时观战 + OB | 英雄联盟/王者荣耀赛事 |
| **玩家社交** | 好友在对战中，我想看 | 延迟观战 | 王者荣耀好友观战 |
| **学习复盘** | 高手第一视角学习操作 | 录像观战 | Dota2 观战系统、Starcraft2 Replay |

从技术角度看，观战系统的本质是：

> **将一个战斗的数据流"镜像"给非参战方，并允许该方自由选择观察视角。**

这听起来简单，但涉及：数据流复制、延迟控制、加入时机、视角切换、反作弊——每一点都有技术深度。

### 1.2 观战模式分类

```
观战模式
├── 实时观战 (Live Spectating)
│   └── 观战者与玩家同帧看到内容
│   └── 风险：观战者可向参战玩家泄露信息（"对面打野在红区！"）
│   └── 适用：局域网赛事、有物理隔离的电竞场景
│
├── 延迟观战 (Delayed Spectating)
│   └── 观战者看到的是 N 秒前的比赛
│   └── 王者荣耀：3 分钟延迟
│   └── Dota2：2 分钟延迟
│   └── 核心价值：消除观战作弊的信息价值
│
└── 录像观战 (Replay Spectating)
    └── 比赛已结束，播放录像文件
    └── 可暂停、快进、慢放
    └── 详见 26-录像与战斗回放系统
```

**延迟观战是生产环境的主流选择**。为什么需要延迟？看这个例子：

```
实时观战的作弊场景（MOBA）：
  观战者A 是玩家B的朋友，观战玩家B的比赛
  观战者A 在观战视角看到敌方打野正在蹲草丛
  观战者A 通过语音告诉玩家B："别去上路！草里有人！"
  
  结果：玩家B获得了不应有的信息优势。
```

加入 **N 秒延迟** 后：观战者看到的是 N 秒前的情况，"草里有人"这条信息在 N 秒前有效，但对当前时刻已无参考价值。

### 1.3 核心思想地图

```
                    ┌──────────────────────────────────────────────┐
                    │              观战系统架构                      │
                    ├──────────────────────────────────────────────┤
                    │                                              │
                    │  ┌──────────┐     ┌──────────┐               │
                    │  │ 战斗服务器 │     │ 观战服务器 │   ◄─ 独立进程 │
                    │  │ (DS/Room) │────►│(Spectator │               │
                    │  │          │镜像 │  Server)  │               │
                    │  └──────────┘     └─────┬─────┘               │
                    │                         │                     │
                    │              ┌──────────┼──────────┐          │
                    │              ▼          ▼          ▼          │
                    │         ┌──────┐  ┌──────┐  ┌──────┐         │
                    │         │观战者1│  │观战者2│  │观战者N│         │
                    │         └──────┘  └──────┘  └──────┘         │
                    │                                              │
                    │  观战客户端功能：                              │
                    │  ┌─────────┐ ┌──────────┐ ┌───────────────┐  │
                    │  │上帝视角  │ │玩家跟随   │ │数据面板(HUD)  │  │
                    │  │自由镜头 │ │锁定视角   │ │经济/装备/等级 │  │
                    │  └─────────┘ └──────────┘ └───────────────┘  │
                    └──────────────────────────────────────────────┘
```

---

## 2. 帧同步观战

### 2.1 帧同步观战的加入原理

帧同步的核心是"相同的初始状态 + 相同的输入序列 → 相同的最终状态"。观战者要加入到一场正在进行的战斗中，需要两样东西：

1. **当前帧号** — 战斗进行到了第几帧
2. **该帧的完整状态快照** — 作为观战者的初始状态

```
观战者加入流程（帧同步）:

  观战客户端                        观战服务器                      战斗服务器
      │                                │                              │
      │ ① 请求观战 Room#42             │                              │
      │──────────────────────────────►│                              │
      │                                │ ② 查询 Room#42 当前帧号      │
      │                                │─────────────────────────────►│
      │                                │     currentFrame = 15000     │
      │                                │◄─────────────────────────────│
      │                                │                              │
      │                                │ ③ 请求帧 #15000 的完整快照    │
      │                                │─────────────────────────────►│
      │                                │     snapshot[15000] (序列化)  │
      │                                │◄─────────────────────────────│
      │                                │                              │
      │ ④ 下发：frameNo=15000         │                              │
      │    + snapshot + 元数据        │                              │
      │◄──────────────────────────────│                              │
      │                                │                              │
      │ ⑤ 客户端恢复状态              │                              │
      │    world.LoadSnapshot(snapshot)│                              │
      │    currentFrame = 15000       │                              │
      │                                │                              │
      │ ⑥ 从帧 #15001 开始接收输入    │                              │
      │◄═══ 持续的帧输入流 ═══════════│◄═══ 战斗服务器帧输入 ═══════│
      │                                │                              │
      │ ⑦ 每帧执行：                  │                              │
      │    world.Tick(inputs[frame])   │                              │
      │    render()                   │                              │
```

**关键点**：观战者不需要所有历史帧的输入，只需要**一个快照 + 从该帧之后的输入流**。这是帧同步最大的优势之一——观战者加入的成本极低。

### 2.2 延迟观战的实现

帧同步的延迟观战实现非常优雅：**只需要在输入流的"窗口"上做偏移**。

```
正常玩家看到的数据流（帧同步）:

  时间轴 →  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┐
  帧号      │14995│14996│14997│14998│14999│15000│15001│ ...
            └─────┴─────┴─────┴─────┴─────┴─────┴─────┘
                            ▲
                    当前服务器最新帧
                    正常玩家在此帧执行


观战者看到的数据流（延迟 300 帧 = 5秒 @ 60fps）:

  时间轴 →  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┐
  帧号      │14700│14701│14702│14703│14704│14705│14706│ ...
            └─────┴─────┴─────┴─────┴─────┴─────┴─────┘
              ▲
       观战者当前帧 = 服务器最新帧 - 延迟帧数
       spectatorFrame = serverFrame - DELAY_FRAMES
```

**实现方式**：观战服务器维护一个输入环形缓冲区：

```
┌─────────────────────────────────────────────────────────────────┐
│              观战服务器输入环形缓冲区                              │
│                                                                  │
│  buffer size = 延迟帧数 + 缓冲余量                                │
│  例如：300 帧延迟 + 60 帧缓冲 = 360 帧容量                        │
│                                                                  │
│  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐     │
│  │...│F= │F= │F= │F= │F= │F= │F= │F= │F= │F= │F= │F= │...│     │
│  │   │N  │N+1│N+2│N+3│N+4│N+5│N+6│N+7│N+8│N+9│N+ │N+ │   │     │
│  │   │   │   │   │   │   │   │   │   │   │   │ 10│ 11│   │     │
│  └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘     │
│    ▲                           ▲                   ▲             │
│    │                           │                   │             │
│  最旧                        观战者                 最新          │
│  (可能已丢弃)              读取位置               写入位置        │
│                                                                  │
│  readPos = (writePos - DELAY_FRAMES + bufferSize) % bufferSize   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 多视角切换

帧同步的"第一视角"观战——能看到某个玩家的局部视野（战争迷雾）——需要特殊处理：

```
帧同步的视野数据存储:

  每帧的游戏状态中包含每个玩家的"可见集合"：
  
  GameState {
      entities: Entity[],
      playerVisibility: {
          0: Set<EntityId>,  // 玩家0可见的实体集合
          1: Set<EntityId>,  // 玩家1可见的实体集合
      }
  }
  
  观战者切换到"玩家0视角"时：
  - 只渲染 playerVisibility[0] 中的实体
  - 镜头锁定玩家0的位置
  - 可以看到玩家0的 UI（技能冷却、装备等）
```

**视野切换的核心代码逻辑**：

```csharp
// 帧同步观战客户端的视角管理
public class SpectatorViewManager
{
    // -1 表示上帝视角（全图可见），0~9 表示跟随对应玩家
    public int FollowTarget { get; private set; } = -1;
    
    // 当前渲染使用的可见集合
    public HashSet<uint> VisibleEntities { get; private set; }
    
    // 切换视角
    public void SwitchToGodView()
    {
        FollowTarget = -1;
        VisibleEntities = null; // null = 显示全部
        Camera.mode = CameraMode.Free;
    }
    
    public void SwitchToPlayer(int playerIdx, GameState state)
    {
        FollowTarget = playerIdx;
        // 使用该玩家的战争迷雾数据
        VisibleEntities = state.PlayerVisibility[playerIdx];
        Camera.mode = CameraMode.LockedToEntity;
        Camera.target = state.Players[playerIdx].EntityId;
    }
    
    // 每帧过滤渲染实体
    public List<Entity> GetRenderableEntities(GameState state)
    {
        if (VisibleEntities == null)
            return state.AllEntities; // 上帝视角：全部可见
        
        return state.AllEntities
            .Where(e => VisibleEntities.Contains(e.Id))
            .ToList();
    }
}
```

---

## 3. 状态同步观战

### 3.1 状态同步观战的加入

状态同步的观战者加入比帧同步简单——但也更"重"：

```
观战者加入流程（状态同步）:

  观战客户端                        观战服务器
      │                                │
      │ ① 请求观战 Battle#42          │
      │──────────────────────────────►│
      │                                │
      │ ② 服务器构造全量状态快照       │
      │   - 所有玩家的位置/血量/状态   │
      │   - 所有可见实体的属性        │
      │   - 游戏时间、比分等元数据    │
      │◄──────────────────────────────│
      │                                │
      │ ③ 客户端用快照初始化世界       │
      │   foreach entity in snapshot:  │
      │       SpawnEntity(entity)      │
      │                                │
      │ ④ 开始接收增量状态更新         │
      │◄═══ 持续的属性更新流 ══════════│
      │   - 位置更新 (PositionUpdate)  │
      │   - 血量更新 (HPUpdate)       │
      │   - 事件 (SkillCast, Death...) │
      │                                │
      │ ⑤ 客户端持续 Apply 更新       │
      │   + 本地插值/预测渲染          │
```

**与帧同步的关键区别**：

| 维度 | 帧同步观战 | 状态同步观战 |
|------|-----------|-------------|
| **加入成本** | 快照+从该帧开始的输入流 | 全量状态快照+增量更新流 |
| **客户端负载** | 需运行完整游戏逻辑 | 只需Apply状态+渲染 |
| **延迟实现** | 输入流窗口偏移 | 状态流时间戳偏移 |
| **视角切换** | 切换渲染过滤+可见集合 | 切换相机目标+本地过滤 |
| **带宽** | 很低（只有输入） | 中等（状态更新） |

### 3.2 状态流的延迟机制

状态同步的延迟观战通过**时间戳过滤**实现：

```csharp
// 观战服务器：维护最近的状态更新环形缓冲区
public class StateSyncSpectatorServer
{
    // 每个实体最近的状态更新历史
    // entityId → (timestamp, state) 的环形缓冲区
    Dictionary<uint, RingBuffer<StateEntry>> _entityStates;
    
    const int DELAY_SECONDS = 180; // 王者荣耀：3分钟延迟
    const int HISTORY_SECONDS = 200; // 保留200秒历史
    
    // 获取观战者应该看到的状态（N秒前）
    public WorldSnapshot GetSpectatorSnapshot(uint battleId)
    {
        var cutoffTime = DateTime.UtcNow.AddSeconds(-DELAY_SECONDS);
        
        var snapshot = new WorldSnapshot();
        foreach (var (entityId, history) in _entityStates)
        {
            // 从环形缓冲区中找到最接近 cutoffTime 的状态
            var state = history.FindClosest(cutoffTime);
            if (state != null)
                snapshot.Entities[entityId] = state;
        }
        return snapshot;
    }
    
    // 持续推送给观战者的状态更新流
    public async IAsyncEnumerable<StateUpdate> StreamUpdates(
        uint battleId, DateTime fromTime)
    {
        // fromTime = 当前时间 - 延迟秒数
        var spectatorTime = DateTime.UtcNow.AddSeconds(-DELAY_SECONDS);
        
        while (true)
        {
            // 获取 spectatorTime 之后的所有更新
            var updates = GetUpdatesSince(battleId, spectatorTime);
            
            foreach (var update in updates)
                yield return update;
            
            spectatorTime = DateTime.UtcNow.AddSeconds(-DELAY_SECONDS);
            await Task.Delay(50); // 20Hz 推送频率
        }
    }
}
```

### 3.3 视角切换（状态同步）

状态同步的视角切换全部在客户端本地完成——因为客户端已经拥有全量状态：

```csharp
// 状态同步观战客户端：视角管理
public class StateSyncSpectatorCamera
{
    int _followTarget = -1; // -1=自由, 0~N=跟随玩家
    
    public void SwitchFollow(int playerIdx)
    {
        _followTarget = playerIdx;
        
        if (playerIdx >= 0)
        {
            // 锁定相机到目标玩家实体
            var entityId = _world.GetPlayerEntityId(playerIdx);
            _camera.LockTo(entityId);
            _camera.SetMode(CameraMode.ThirdPerson);
        }
        else
        {
            _camera.SetMode(CameraMode.FreeFly);
        }
    }
    
    // 每帧更新：如果锁定玩家，平滑跟随
    public void Update(float dt)
    {
        if (_followTarget < 0) return;
        
        var target = _world.GetEntity(_world.GetPlayerEntityId(_followTarget));
        if (target == null) return;
        
        // 平滑跟随（带有阻尼的插值）
        var targetPos = target.Position + _cameraOffset;
        _camera.Position = Vector3.Lerp(
            _camera.Position, targetPos, _followSmoothness * dt);
    }
}
```

---

## 4. 代码示例

### 4.1 C# — 帧同步观战客户端 (~150行)

```csharp
// SpectatorClient.cs — 帧同步观战客户端完整实现
// 依赖: 已有的帧同步客户端框架 (FrameSyncClient, GameWorld, SnapshotSerializer)

using System;
using System.Collections.Generic;
using UnityEngine;

namespace BattleSpectator
{
    /// <summary>
    /// 观战模式枚举
    /// </summary>
    public enum SpectateMode
    {
        Live,       // 实时观战（赛事用）
        Delayed,    // 延迟观战（好友观战用）
        Replay      // 录像观战
    }

    /// <summary>
    /// 帧同步观战客户端。
    /// 复用战斗客户端的 GameWorld 执行逻辑帧，但不发送任何输入。
    /// </summary>
    public class SpectatorClient : MonoBehaviour
    {
        [Header("配置")]
        [SerializeField] int _delayFrames = 9000;  // 默认定时延迟 150秒 @ 60fps
        [SerializeField] float _logicFrameInterval = 1f / 60f;

        [Header("运行时状态")]
        [SerializeField] uint _currentFrame;
        [SerializeField] SpectateMode _mode;
        [SerializeField] int _followPlayerIdx = -1; // -1=上帝视角

        // === 核心组件 ===
        GameWorld _world;              // 游戏逻辑世界（复用战斗客户端的世界）
        SpectatorNetwork _network;     // 观战专用网络层
        HashSet<uint> _visibleFilter;  // 当前视角的可见实体集合

        // === 输入流水线 ===
        // 从观战服务器收到的输入帧队列（帧号 → 该帧所有玩家的输入）
        Dictionary<uint, PlayerInput[]> _pendingInputs = new();
        float _logicTimer;

        // === 初始化 ===

        /// <summary>
        /// 连接到观战服务器，加入指定战斗。
        /// </summary>
        /// <param name="serverAddr">观战服务器地址</param>
        /// <param name="battleId">要观战的战斗ID</param>
        /// <param name="mode">观战模式</param>
        public void Connect(string serverAddr, uint battleId, SpectateMode mode)
        {
            _mode = mode;
            _network = new SpectatorNetwork();
            _world = new GameWorld(); // 创建独立的游戏世界实例

            // 注册网络事件
            _network.OnJoinResponse += OnJoinResponse;
            _network.OnFrameInput += OnFrameInput;
            _network.OnBattleEnd += OnBattleEnd;

            // 发送加入请求
            _network.Connect(serverAddr, () =>
            {
                _network.SendJoinRequest(battleId, mode);
            });
        }

        // === 网络回调 ===

        /// <summary>
        /// 收到加入响应：包含初始快照 + 起始帧号
        /// </summary>
        void OnJoinResponse(JoinResponse resp)
        {
            Debug.Log($"[Spectator] Joined battle. Start frame: {resp.StartFrame}, " +
                      $"Player count: {resp.PlayerCount}");

            // 1. 用快照恢复游戏世界状态
            _world.LoadSnapshot(resp.SnapshotData);
            _currentFrame = resp.StartFrame;

            // 2. 根据延迟模式调整实际起始帧
            if (_mode == SpectateMode.Delayed)
            {
                // 延迟观战：实际起始帧 = 当前最新帧 - 延迟帧数
                // 观战服务器已经帮我们做了这个偏移，所以这里不需要额外处理
            }

            // 3. 开始驱动逻辑帧
            _logicTimer = 0f;
            enabled = true;
        }

        /// <summary>
        /// 收到一帧的输入数据。
        /// 观战服务器按帧号推送，可能一包包含多帧。
        /// </summary>
        void OnFrameInput(FrameInputPacket packet)
        {
            // 将收到的输入存入待处理队列
            for (int i = 0; i < packet.FrameCount; i++)
            {
                uint frameNo = packet.StartFrame + (uint)i;
                _pendingInputs[frameNo] = packet.Inputs[i];
            }

            // 清理过旧的帧（已经执行过的）
            CleanOldFrames();
        }

        void OnBattleEnd(BattleEndInfo info)
        {
            Debug.Log($"[Spectator] Battle ended. Winner: team {info.WinnerTeam}");
            enabled = false;
        }

        // === 主循环 ===

        void Update()
        {
            if (_world == null || !enabled) return;

            // 累积逻辑时间
            _logicTimer += Time.deltaTime;

            // 以固定步长执行逻辑帧（追赶机制）
            while (_logicTimer >= _logicFrameInterval)
            {
                _logicTimer -= _logicFrameInterval;
                TickLogicFrame();
            }

            // 渲染帧：根据当前视角渲染世界
            RenderWorld();
        }

        /// <summary>
        /// 执行一个逻辑帧。
        /// 帧同步观战的核心：找到当前帧的输入 → 喂给 GameWorld → 执行。
        /// </summary>
        void TickLogicFrame()
        {
            uint targetFrame = _currentFrame + 1;

            // 检查该帧的输入是否已到达
            if (!_pendingInputs.TryGetValue(targetFrame, out var inputs))
            {
                // 输入未到达 → 等待（不跳过，保证确定性）
                // 实际项目中可增加"缓冲帧"配置来容忍网络抖动
                return;
            }

            // 喂入输入，执行一帧游戏逻辑
            // 观战者不产生输入，inputs 来自参战玩家
            _world.SetInputs(targetFrame, inputs);
            _world.Tick(_logicFrameInterval);

            _currentFrame = targetFrame;

            // 执行后清理已处理的帧（保留最近若干帧用于回放）
            _pendingInputs.Remove(targetFrame);
        }

        void CleanOldFrames()
        {
            // 保留最近 120 帧（2秒缓冲），删除更旧的
            uint cutoff = _currentFrame > 120 ? _currentFrame - 120 : 0;
            var toRemove = new List<uint>();
            foreach (var frameNo in _pendingInputs.Keys)
            {
                if (frameNo < cutoff) toRemove.Add(frameNo);
            }
            foreach (var f in toRemove) _pendingInputs.Remove(f);
        }

        // === 渲染 ===

        void RenderWorld()
        {
            // 根据当前视角决定渲染哪些实体
            if (_followPlayerIdx < 0)
            {
                // 上帝视角：渲染全部实体
                _world.RenderAll();
            }
            else
            {
                // 玩家视角：只渲染该玩家可见的实体
                var visibleSet = _world.GetPlayerVisibility(_followPlayerIdx);
                _world.RenderFiltered(visibleSet);
            }
        }

        // === 视角切换 ===

        /// <summary>
        /// 切换到上帝视角（自由镜头）
        /// </summary>
        public void SwitchToGodView()
        {
            _followPlayerIdx = -1;
            _visibleFilter = null;
            CameraController.SetFreeMode();
            Debug.Log("[Spectator] Switched to God View");
        }

        /// <summary>
        /// 切换到指定玩家的第一视角
        /// </summary>
        /// <param name="playerIdx">玩家索引 (0~N-1)</param>
        public void SwitchToPlayerView(int playerIdx)
        {
            if (playerIdx < 0 || playerIdx >= _world.PlayerCount)
            {
                Debug.LogWarning($"[Spectator] Invalid player index: {playerIdx}");
                return;
            }

            _followPlayerIdx = playerIdx;
            _visibleFilter = _world.GetPlayerVisibility(playerIdx);
            
            var playerEntity = _world.GetPlayerEntity(playerIdx);
            CameraController.LockToEntity(playerEntity);
            
            Debug.Log($"[Spectator] Switched to Player {playerIdx} view");
        }

        /// <summary>
        /// 循环切换视角（UI 按钮绑定）
        /// </summary>
        public void CycleView()
        {
            _followPlayerIdx++;
            if (_followPlayerIdx >= _world.PlayerCount)
                SwitchToGodView();
            else
                SwitchToPlayerView(_followPlayerIdx);
        }
    }

    // ================================================================
    // 网络层（简化实现）
    // ================================================================

    /// <summary>
    /// 观战专用网络层。
    /// 与战斗客户端使用不同的连接，避免影响战斗通信。
    /// </summary>
    public class SpectatorNetwork
    {
        UdpClient _udp;
        string _serverAddr;
        int _serverPort;

        public event Action<JoinResponse> OnJoinResponse;
        public event Action<FrameInputPacket> OnFrameInput;
        public event Action<BattleEndInfo> OnBattleEnd;

        public void Connect(string addr, Action onConnected)
        {
            _serverAddr = addr;
            _serverPort = 9000; // 观战专用端口
            _udp = new UdpClient();
            _udp.Connect(_serverAddr, _serverPort);
            
            // 开始异步接收
            BeginReceive();
            onConnected?.Invoke();
        }

        public void SendJoinRequest(uint battleId, SpectateMode mode)
        {
            var writer = new BinaryWriter(new MemoryStream());
            writer.Write((byte)MessageType.SpectatorJoin);  // 消息类型
            writer.Write(battleId);
            writer.Write((byte)mode);
            
            var data = ((MemoryStream)writer.BaseStream).ToArray();
            _udp.Send(data, data.Length);
        }

        async void BeginReceive()
        {
            while (_udp != null)
            {
                try
                {
                    var result = await _udp.ReceiveAsync();
                    ProcessPacket(result.Buffer);
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SpectatorNetwork] Receive error: {ex.Message}");
                }
            }
        }

        void ProcessPacket(byte[] data)
        {
            var reader = new BinaryReader(new MemoryStream(data));
            var msgType = (MessageType)reader.ReadByte();

            switch (msgType)
            {
                case MessageType.SpectatorJoinAck:
                    OnJoinResponse?.Invoke(JoinResponse.Deserialize(reader));
                    break;
                case MessageType.FrameInputBatch:
                    OnFrameInput?.Invoke(FrameInputPacket.Deserialize(reader));
                    break;
                case MessageType.BattleEnd:
                    OnBattleEnd?.Invoke(BattleEndInfo.Deserialize(reader));
                    break;
            }
        }
    }

    // === 数据结构 ===

    public enum MessageType : byte
    {
        SpectatorJoin = 100,
        SpectatorJoinAck = 101,
        FrameInputBatch = 102,
        BattleEnd = 103,
    }

    public struct JoinResponse
    {
        public uint BattleId;
        public uint StartFrame;       // 观战起始帧号
        public int PlayerCount;
        public byte[] SnapshotData;   // 序列化的游戏状态快照

        public static JoinResponse Deserialize(BinaryReader r)
        {
            return new JoinResponse
            {
                BattleId = r.ReadUInt32(),
                StartFrame = r.ReadUInt32(),
                PlayerCount = r.ReadByte(),
                SnapshotData = r.ReadBytes(r.ReadInt32()),
            };
        }
    }

    public struct FrameInputPacket
    {
        public uint StartFrame;
        public int FrameCount;
        public PlayerInput[][] Inputs;  // Inputs[frameIndex][playerIdx]

        public static FrameInputPacket Deserialize(BinaryReader r)
        {
            var pkt = new FrameInputPacket
            {
                StartFrame = r.ReadUInt32(),
                FrameCount = r.ReadByte(),
            };
            int playerCount = r.ReadByte();
            pkt.Inputs = new PlayerInput[pkt.FrameCount][];
            
            for (int f = 0; f < pkt.FrameCount; f++)
            {
                pkt.Inputs[f] = new PlayerInput[playerCount];
                for (int p = 0; p < playerCount; p++)
                {
                    pkt.Inputs[f][p] = PlayerInput.Deserialize(r);
                }
            }
            return pkt;
        }
    }

    public struct BattleEndInfo
    {
        public uint BattleId;
        public int WinnerTeam;
        public uint DurationFrames;
        public uint EndReason; // 0=正常结束, 1=投降, 2=超时

        public static BattleEndInfo Deserialize(BinaryReader r)
        {
            return new BattleEndInfo
            {
                BattleId = r.ReadUInt32(),
                WinnerTeam = r.ReadByte(),
                DurationFrames = r.ReadUInt32(),
                EndReason = r.ReadByte(),
            };
        }
    }

    // PlayerInput 定义已在教程 05/07 中，此处省略
    public struct PlayerInput
    {
        public uint FrameNo;
        public byte PlayerIdx;
        public ushort InputFlags;   // 位掩码：移动/攻击/技能...
        public short MoveX, MoveY;  // 移动方向（定点数原始值）

        public static PlayerInput Deserialize(BinaryReader r)
        {
            return new PlayerInput
            {
                FrameNo = r.ReadUInt32(),
                PlayerIdx = r.ReadByte(),
                InputFlags = r.ReadUInt16(),
                MoveX = r.ReadInt16(),
                MoveY = r.ReadInt16(),
            };
        }
    }
}
```

### 4.2 C++ — 观战代理服务器

```cpp
// SpectatorProxyServer.hpp — 观战代理服务器
// 职责：从战斗服务器接收数据流 → 缓存 + 延迟 → 广播给观战客户端
// 设计：每个 BattleRoom 一个 SpectatorProxy 实例

#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <deque>
#include <memory>
#include <mutex>
#include <chrono>
#include <thread>
#include <functional>

// ================================================================
// 数据定义
// ================================================================

struct PlayerInput {
    uint32_t frame_no;
    uint8_t  player_idx;
    uint16_t input_flags;
    int16_t  move_x, move_y;
};

struct FrameInputBatch {
    uint32_t start_frame;                  // 起始帧号
    std::vector<std::vector<PlayerInput>> inputs; // inputs[frame_offset][player_idx]
};

struct GameSnapshot {
    uint32_t frame_no;
    uint32_t battle_id;
    std::vector<uint8_t> serialized_data;  // 序列化的全量状态
};

struct SpectatorSession {
    uint32_t session_id;
    uint32_t battle_id;
    uint32_t spectator_ip;
    uint16_t spectator_port;
    uint32_t delay_seconds;    // 观战延迟（秒）
    uint32_t join_frame;       // 加入时的帧号
    bool     active;
};

// ================================================================
// 帧输入环形缓冲区
// ================================================================

template<typename T>
class RingBuffer {
public:
    explicit RingBuffer(size_t capacity)
        : _buffer(capacity), _capacity(capacity), _write_pos(0), _count(0) {}

    void push(const T& item) {
        _buffer[_write_pos] = item;
        _write_pos = (_write_pos + 1) % _capacity;
        if (_count < _capacity) _count++;
    }

    // 读取从 write_pos 往前数 offset 个位置的元素
    // offset=0 → 最新，offset=1 → 上一帧
    const T* get_offset(size_t offset) const {
        if (offset >= _count) return nullptr;
        size_t idx = (_write_pos + _capacity - 1 - offset) % _capacity;
        return &_buffer[idx];
    }

    size_t count() const { return _count; }
    size_t capacity() const { return _capacity; }

private:
    std::vector<T> _buffer;
    size_t _capacity;
    size_t _write_pos;
    size_t _count;
};

// ================================================================
// 观战代理服务器
// ================================================================

class SpectatorProxyServer {
public:
    // 延迟帧数计算（假设 60 逻辑帧/秒）
    static constexpr uint32_t FRAMES_PER_SECOND = 60;
    static constexpr size_t   INPUT_RING_SIZE = 60 * 300;  // 300秒容量

    SpectatorProxyServer(uint16_t listen_port)
        : _listen_port(listen_port)
        , _input_ring(INPUT_RING_SIZE)
        , _current_frame(0)
        , _running(false)
    {}

    ~SpectatorProxyServer() { shutdown(); }

    // === 生命周期 ===

    void start() {
        _running = true;
        _receive_thread = std::thread(&SpectatorProxyServer::receiveLoop, this);
        _broadcast_thread = std::thread(&SpectatorProxyServer::broadcastLoop, this);
    }

    void shutdown() {
        _running = false;
        if (_receive_thread.joinable()) _receive_thread.join();
        if (_broadcast_thread.joinable()) _broadcast_thread.join();
    }

    // === 战斗服务器 → 观战服务器的数据注入 ===

    /**
     * 战斗服务器每帧调用：推送一帧的输入数据。
     * 线程安全（由互斥锁保护）。
     */
    void pushFrameInput(const FrameInputBatch& batch) {
        std::lock_guard<std::mutex> lock(_mutex);
        
        for (size_t i = 0; i < batch.inputs.size(); i++) {
            _input_ring.push(batch.inputs[i]);
        }
        
        _current_frame = batch.start_frame + static_cast<uint32_t>(batch.inputs.size()) - 1;
    }

    /**
     * 战斗服务器定期调用：推送快照（用于新观战者加入）。
     */
    void pushSnapshot(const GameSnapshot& snapshot) {
        std::lock_guard<std::mutex> lock(_mutex);
        _latest_snapshot = snapshot;
    }

    // === 观战者管理 ===

    /**
     * 新观战者请求加入。
     * 返回：起始帧号 + 快照数据
     */
    GameSnapshot acceptSpectator(const SpectatorSession& session) {
        std::lock_guard<std::mutex> lock(_mutex);
        
        auto s = std::make_shared<SpectatorSession>(session);
        s->active = true;
        
        // 根据延迟计算观战者应该从哪一帧开始
        uint32_t delay_frames = session.delay_seconds * FRAMES_PER_SECOND;
        uint32_t start_frame = (_current_frame > delay_frames) 
                               ? (_current_frame - delay_frames) 
                               : 0;
        s->join_frame = start_frame;
        
        _sessions[session.session_id] = s;
        
        // 返回该帧的快照（如果快照帧不精确匹配，取最近的一个）
        // 生产代码中应维护快照环形缓冲区以支持精确查找
        GameSnapshot result = _latest_snapshot;
        result.frame_no = start_frame;
        return result;
    }

    void removeSpectator(uint32_t session_id) {
        std::lock_guard<std::mutex> lock(_mutex);
        _sessions.erase(session_id);
    }

    // === 内部线程 ===

private:
    void receiveLoop() {
        // 实际项目中：从 UDP socket 接收战斗服务器的数据
        // 此处为简化示例，数据通过 pushFrameInput/pushSnapshot 注入
        while (_running) {
            std::this_thread::sleep_for(std::chrono::milliseconds(16)); // ~60Hz
            // recvfrom + deserialize + pushFrameInput
        }
    }

    /**
     * 广播线程：每帧给所有观战者发送延迟后的输入
     */
    void broadcastLoop() {
        while (_running) {
            std::this_thread::sleep_for(std::chrono::milliseconds(16));
            
            std::lock_guard<std::mutex> lock(_mutex);
            
            for (auto& [id, session] : _sessions) {
                if (!session->active) continue;
                
                // 计算该观战者应该接收的帧号范围
                uint32_t delay_frames = session->delay_seconds * FRAMES_PER_SECOND;
                uint32_t target_frame = (_current_frame > delay_frames) 
                                        ? (_current_frame - delay_frames) 
                                        : 0;
                
                // 从上次发送的帧到目标帧，逐帧发送
                uint32_t send_start = session->join_frame;
                
                // 构建帧输入包并发送
                sendFrameRange(session, send_start, target_frame);
                
                // 更新已发送帧号
                session->join_frame = target_frame + 1;
            }
        }
    }

    /**
     * 给指定观战者发送 [from_frame, to_frame] 范围的帧输入。
     * 通过环形缓冲区按偏移反查历史输入。
     */
    void sendFrameRange(const std::shared_ptr<SpectatorSession>& session,
                        uint32_t from_frame, uint32_t to_frame)
    {
        if (from_frame > to_frame) return;
        
        uint32_t frame_count = to_frame - from_frame + 1;
        
        // 限制单次发送的帧数（避免网络突发）
        const uint32_t MAX_FRAMES_PER_PACKET = 10;
        for (uint32_t offset = 0; offset < frame_count; offset += MAX_FRAMES_PER_PACKET)
        {
            uint32_t batch_start = from_frame + offset;
            uint32_t batch_end = std::min(batch_start + MAX_FRAMES_PER_PACKET - 1, to_frame);
            uint32_t batch_count = batch_end - batch_start + 1;
            
            // 从环形缓冲区提取数据
            // offset_from_tail: 当前帧到目标帧的距离
            uint32_t frames_behind = _current_frame - batch_start;
            
            std::vector<std::vector<PlayerInput>> batch_inputs;
            batch_inputs.reserve(batch_count);
            
            for (uint32_t i = 0; i < batch_count; i++)
            {
                uint32_t lookup_offset = frames_behind - i;
                const auto* inputs = _input_ring.get_offset(lookup_offset);
                if (inputs)
                    batch_inputs.push_back(*inputs);
            }
            
            // 序列化并发送
            auto serialized = serializeFrameBatch(batch_start, batch_inputs);
            sendToSpectator(session, serialized);
        }
    }

    std::vector<uint8_t> serializeFrameBatch(
        uint32_t start_frame,
        const std::vector<std::vector<PlayerInput>>& batch)
    {
        // 简化序列化：实际项目应使用 Protobuf/FlatBuffers
        std::vector<uint8_t> out;
        out.reserve(1024);
        
        // Header
        auto push_u32 = [&](uint32_t v) {
            out.push_back(v & 0xFF);
            out.push_back((v >> 8) & 0xFF);
            out.push_back((v >> 16) & 0xFF);
            out.push_back((v >> 24) & 0xFF);
        };
        
        // Message type: FrameInputBatch = 102
        out.push_back(102);
        
        // Start frame
        push_u32(start_frame);
        
        // Frame count
        out.push_back(static_cast<uint8_t>(batch.size()));
        
        // Player count (from first frame)
        out.push_back(batch.empty() ? 0 : static_cast<uint8_t>(batch[0].size()));
        
        // Per-frame inputs
        for (const auto& frame_inputs : batch) {
            for (const auto& input : frame_inputs) {
                push_u32(input.frame_no);
                out.push_back(input.player_idx);
                out.push_back(input.input_flags & 0xFF);
                out.push_back((input.input_flags >> 8) & 0xFF);
                out.push_back(input.move_x & 0xFF);
                out.push_back((input.move_x >> 8) & 0xFF);
                out.push_back(input.move_y & 0xFF);
                out.push_back((input.move_y >> 8) & 0xFF);
            }
        }
        
        return out;
    }

    void sendToSpectator(const std::shared_ptr<SpectatorSession>& session,
                         const std::vector<uint8_t>& data)
    {
        // 实际项目：sendto(socket, data, session->spectator_ip, session->spectator_port)
        (void)session;
        (void)data;
    }

    // === 成员变量 ===

    uint16_t _listen_port;
    RingBuffer<std::vector<PlayerInput>> _input_ring;
    uint32_t _current_frame;
    GameSnapshot _latest_snapshot;
    
    std::unordered_map<uint32_t, std::shared_ptr<SpectatorSession>> _sessions;
    
    std::mutex _mutex;
    std::thread _receive_thread;
    std::thread _broadcast_thread;
    std::atomic<bool> _running;
};
```

### 4.3 Lua — 观战管理器

```lua
-- SpectatorManager.lua — 观战管理器（游戏客户端 Lua 层）
-- 职责：管理观战模式切换、OB 视角、HUD 数据面板

local SpectatorManager = {}
SpectatorManager.__index = SpectatorManager

-- ================================================================
-- 视角模式定义
-- ================================================================

local ViewMode = {
    GOD         = 0,  -- 上帝视角（自由镜头）
    FOLLOW      = 1,  -- 跟随玩家（第三人称锁定）
    FIRST_PERSON = 2, -- 第一人称（玩家视野 + 战争迷雾）
    DIRECTOR    = 3,  -- 导演模式（AI 自动选择最佳镜头）
}

-- ================================================================
-- 构造函数
-- ================================================================

function SpectatorManager.new(game_world, camera_controller, hud)
    local self = setmetatable({}, SpectatorManager)
    
    self._world = game_world
    self._camera = camera_controller
    self._hud = hud
    
    -- 当前状态
    self._view_mode = ViewMode.GOD
    self._follow_target = -1       -- 跟随的玩家索引，-1=无
    self._camera_distance = 15.0   -- 上帝视角距离
    self._camera_pitch = 45.0      -- 俯仰角（度）
    self._camera_yaw = 0.0         -- 偏航角
    
    -- 导演模式数据
    self._director_timer = 0
    self._director_interval = 8.0  -- 每8秒切换一次焦点
    self._director_focus_stack = {} -- 重要事件优先级队列
    
    -- 数据面板缓存
    self._panel_visible = true
    self._last_panel_update = 0
    self._panel_update_interval = 0.5  -- 每0.5秒刷新一次面板
    
    -- 输入绑定
    self:_bind_input()
    
    return self
end

-- ================================================================
-- 输入绑定（快捷键）
-- ================================================================

function SpectatorManager:_bind_input()
    -- 视角切换快捷键
    Input:BindKey(KeyCode.F1, function() self:switch_to_god_view() end)
    Input:BindKey(KeyCode.F2, function() self:cycle_player_view() end)
    Input:BindKey(KeyCode.F3, function() self:toggle_director_mode() end)
    Input:BindKey(KeyCode.Tab, function() self:toggle_panel() end)
    
    -- 数字键切换跟随目标
    for i = 0, 9 do
        Input:BindKey(KeyCode.Alpha0 + i, function()
            if self._world:get_player_count() > i then
                self:switch_to_player_view(i)
            end
        end)
    end
    
    -- 鼠标滚轮调整距离
    Input:BindAxis("Mouse ScrollWheel", function(delta)
        self._camera_distance = math.clamp(
            self._camera_distance - delta * 2.0,
            5.0,   -- 最近
            50.0   -- 最远
        )
    end)
    
    -- 右键拖拽旋转（上帝视角）
    Input:BindDrag(MouseButton.Right, function(dx, dy)
        if self._view_mode == ViewMode.GOD then
            self._camera_yaw = self._camera_yaw + dx * 0.3
            self._camera_pitch = math.clamp(
                self._camera_pitch - dy * 0.3,
                10.0,  -- 最低俯角
                80.0   -- 最高俯角
            )
        end
    end)
end

-- ================================================================
-- 视角切换
-- ================================================================

function SpectatorManager:switch_to_god_view()
    self._view_mode = ViewMode.GOD
    self._follow_target = -1
    self._camera:set_mode(CameraMode.FreeFly)
    print("[Spectator] Switched to God View")
end

function SpectatorManager:switch_to_player_view(player_idx)
    local player_count = self._world:get_player_count()
    if player_idx < 0 or player_idx >= player_count then
        print(string.format("[Spectator] Invalid player index: %d (max: %d)",
              player_idx, player_count - 1))
        return
    end
    
    self._view_mode = ViewMode.FOLLOW
    self._follow_target = player_idx
    
    local entity = self._world:get_player_entity(player_idx)
    if entity then
        self._camera:lock_to_entity(entity.id)
        self._camera:set_mode(CameraMode.ThirdPerson)
    end
    
    -- 更新 HUD 为当前玩家数据
    self:_refresh_hud_for_player(player_idx)
    
    print(string.format("[Spectator] Following Player %d", player_idx))
end

function SpectatorManager:cycle_player_view()
    local player_count = self._world:get_player_count()
    if player_count == 0 then return end
    
    self._follow_target = (self._follow_target + 1) % (player_count + 1)
    
    if self._follow_target >= player_count then
        self:switch_to_god_view()
    else
        self:switch_to_player_view(self._follow_target)
    end
end

-- ================================================================
-- 导演模式（AI 控制最佳镜头）
-- ================================================================

function SpectatorManager:toggle_director_mode()
    if self._view_mode == ViewMode.DIRECTOR then
        self:switch_to_god_view()
    else
        self._view_mode = ViewMode.DIRECTOR
        self._director_timer = 0
        print("[Spectator] Director Mode ON")
    end
end

-- 导演模式的核心：自动选择"最值得看的"目标
function SpectatorManager:_director_update(dt)
    self._director_timer = self._director_timer + dt
    
    -- 检查是否有紧急事件需要切换
    local urgent = self:_get_urgent_event()
    if urgent then
        self:_focus_on_event(urgent)
        self._director_timer = 0
        return
    end
    
    -- 定时切换焦点
    if self._director_timer >= self._director_interval then
        self._director_timer = 0
        local next_target = self:_select_director_target()
        if next_target then
            self:_smooth_transition_to(next_target)
        end
    end
end

-- 获取紧急事件（击杀、团战、推塔等）
function SpectatorManager:_get_urgent_event()
    local events = self._world:get_recent_events(3.0) -- 最近3秒的事件
    
    -- 优先级排序：多杀 > 单杀 > 团战 > 推塔 > 拿龙
    local priority_order = {
        ["MultiKill"]   = 100,
        ["FirstBlood"]  = 90,
        ["Kill"]        = 80,
        ["TeamFight"]   = 70,
        ["TowerDestroy"] = 60,
        ["BossKill"]    = 50,
    }
    
    local best_event = nil
    local best_priority = 0
    
    for _, event in ipairs(events) do
        local priority = priority_order[event.type] or 0
        if priority > best_priority then
            best_priority = priority
            best_event = event
        end
    end
    
    return best_event
end

-- 聚焦到一个事件位置
function SpectatorManager:_focus_on_event(event)
    self._camera:move_to(event.position, 1.5) -- 1.5秒平滑移动到事件位置
    self._camera:set_zoom(12.0)               -- 拉近镜头
end

-- 选择导演模式的下一个焦点目标
function SpectatorManager:_select_director_target()
    local players = self._world:get_all_players()
    if #players == 0 then return nil end
    
    -- 评分系统：综合多个维度给玩家打分
    local best_player = nil
    local best_score = -math.huge
    
    for _, player in ipairs(players) do
        local score = 0
        
        -- 经济领先程度
        local avg_gold = self._world:get_average_gold()
        if avg_gold > 0 then
            score = score + (player.gold / avg_gold) * 10
        end
        
        -- KDA
        score = score + (player.kills * 5 + player.assists * 2 - player.deaths * 3)
        
        -- 近期战斗热度（附近敌人数量）
        local nearby_enemies = self._world:count_nearby_enemies(player.entity_id, 20.0)
        score = score + nearby_enemies * 8
        
        -- 血量危险度（低血量反而更有看头）
        if player.hp_percent < 0.3 then
            score = score + 15
        end
        
        -- 避免重复看同一个人
        if player.idx == self._follow_target then
            score = score - 20
        end
        
        if score > best_score then
            best_score = score
            best_player = player
        end
    end
    
    return best_player
end

-- 平滑过渡到新目标
function SpectatorManager:_smooth_transition_to(player)
    self._follow_target = player.idx
    local entity = self._world:get_entity(player.entity_id)
    if entity then
        self._camera:move_to(entity.position, 2.0) -- 2秒平滑过渡
    end
    self:_refresh_hud_for_player(player.idx)
end

-- ================================================================
-- HUD 数据面板
-- ================================================================

function SpectatorManager:toggle_panel()
    self._panel_visible = not self._panel_visible
    self._hud:set_visible(self._panel_visible)
end

-- 刷新 HUD 面板（显示经济、装备、等级等）
function SpectatorManager:_refresh_hud_for_player(player_idx)
    local player = self._world:get_player(player_idx)
    if not player then return end
    
    self._hud:show_player_detail({
        name       = player.name,
        level      = player.level,
        hp         = player.hp,
        max_hp     = player.max_hp,
        mp         = player.mp,
        max_mp     = player.max_mp,
        gold       = player.gold,
        kills      = player.kills,
        deaths     = player.deaths,
        assists    = player.assists,
        items      = player.items,       -- {item_id, ...}
        skills_cd  = player.skill_cooldowns, -- {remaining_seconds, ...}
    })
end

-- 定期更新全局数据面板（所有玩家的概览）
function SpectatorManager:_update_overview_panel()
    local now = os.clock()
    if now - self._last_panel_update < self._panel_update_interval then
        return
    end
    self._last_panel_update = now
    
    if not self._panel_visible then return end
    
    local players = self._world:get_all_players()
    local panel_data = {}
    
    for _, p in ipairs(players) do
        table.insert(panel_data, {
            name    = p.name,
            level   = p.level,
            hp_pct  = p.hp / math.max(p.max_hp, 1),
            gold    = p.gold,
            kda     = string.format("%d/%d/%d", p.kills, p.deaths, p.assists),
            is_dead = p.hp <= 0,
        })
    end
    
    self._hud:show_overview(panel_data)
    
    -- 对局信息
    self._hud:show_match_info({
        game_time = self._world:get_game_time(),
        score     = string.format("%d - %d",
                     self._world:get_team_score(0),
                     self._world:get_team_score(1)),
    })
end

-- ================================================================
-- 每帧更新
-- ================================================================

function SpectatorManager:update(dt)
    if not self._world then return end
    
    -- 导演模式：自动选择镜头
    if self._view_mode == ViewMode.DIRECTOR then
        self:_director_update(dt)
    end
    
    -- 跟随模式：平滑跟随目标
    if self._view_mode == ViewMode.FOLLOW and self._follow_target >= 0 then
        local entity = self._world:get_player_entity(self._follow_target)
        if entity then
            -- 相机平滑跟随（带阻尼的插值）
            local target_pos = entity.position + Vector3(0, 5, -8)
            self._camera:lerp_to(target_pos, 8.0 * dt)
        end
    end
    
    -- 上帝视角：自由移动 + 旋转
    if self._view_mode == ViewMode.GOD then
        self:_update_god_camera()
    end
    
    -- 数据面板更新
    self:_update_overview_panel()
end

-- 上帝视角的相机控制
function SpectatorManager:_update_god_camera()
    -- WASD 移动
    local move_dir = Vector3.zero
    
    if Input:GetKey(KeyCode.W) then move_dir.z = move_dir.z + 1 end
    if Input:GetKey(KeyCode.S) then move_dir.z = move_dir.z - 1 end
    if Input:GetKey(KeyCode.A) then move_dir.x = move_dir.x - 1 end
    if Input:GetKey(KeyCode.D) then move_dir.x = move_dir.x + 1 end
    
    if move_dir:magnitude() > 0 then
        move_dir = move_dir:normalized()
        -- 移动方向根据相机朝向旋转
        local yaw_rad = math.rad(self._camera_yaw)
        local forward = Vector3(math.sin(yaw_rad), 0, math.cos(yaw_rad))
        local right = Vector3(math.cos(yaw_rad), 0, -math.sin(yaw_rad))
        
        local world_move = forward * move_dir.z + right * move_dir.x
        local speed = 20.0 * (Input:GetKey(KeyCode.LeftShift) and 2.0 or 1.0)
        self._camera:move(world_move * speed * Time.deltaTime)
    end
    
    -- 构建相机位置（球坐标 → 笛卡尔坐标）
    local pitch_rad = math.rad(self._camera_pitch)
    local yaw_rad = math.rad(self._camera_yaw)
    
    local offset = Vector3(
        math.cos(pitch_rad) * math.sin(yaw_rad),
        math.sin(pitch_rad),
        math.cos(pitch_rad) * math.cos(yaw_rad)
    ) * self._camera_distance
    
    -- 如果聚焦于某个位置（双击地面），移动到该位置
    if self._focus_point then
        self._camera:look_at(self._focus_point)
        self._camera:set_position(self._focus_point + offset)
    else
        -- 自由模式：相机看向地图中心或鼠标指向的地面位置
        local ground_target = self:_get_ground_target()
        self._camera:look_at(ground_target)
        self._camera:set_position(ground_target + offset)
    end
end

function SpectatorManager:_get_ground_target()
    -- 从相机位置沿视线方向做射线检测，找到与地面的交点
    -- 简化实现：返回当前相机前方的固定距离点
    return self._camera:get_position() + self._camera:get_forward() * 30.0
end

-- ================================================================
-- 公开接口
-- ================================================================

function SpectatorManager:get_current_view_mode()
    return self._view_mode
end

function SpectatorManager:get_follow_target()
    return self._follow_target
end

function SpectatorManager:on_battle_end(winner_team)
    print(string.format("[Spectator] Battle ended. Winner: Team %d", winner_team))
    -- 显示结算画面
    self._hud:show_battle_result(winner_team)
end

return SpectatorManager
```

---

## 5. OB (Observer) 系统设计

### 5.1 OB 系统架构

OB 系统是观战功能的"高级版"，专为电竞赛事设计：

```
┌─────────────────────────────────────────────────────────────────┐
│                        OB 系统架构                               │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    OB 客户端（Unity/UE 专用客户端）         │  │
│  │                                                             │  │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  │  │
│  │  │ 镜头控制  │  │ 导演面板   │  │ HUD 系统 │  │ 慢放控制  │  │  │
│  │  │          │  │           │  │          │  │          │  │  │
│  │  │·上帝视角 │  │·事件列表   │  │·双方对比 │  │·0.25x    │  │  │
│  │  │·玩家跟随 │  │·一键切镜头 │  │·经济曲线 │  │·0.5x     │  │  │
│  │  │·画中画   │  │·预设运镜   │  │·装备面板 │  │·1x       │  │  │
│  │  │·自由运镜 │  │·焦点预测   │  │·技能CD   │  │·2x       │  │  │
│  │  │·热力图   │  │           │  │          │  │          │  │  │
│  │  └──────────┘  └───────────┘  └──────────┘  └──────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────┐  ┌─────────────────────────────┐  │
│  │    实时数据注入           │  │    推流输出                   │  │
│  │    ·比赛数据API           │  │    ·RTMP/NDI 推流             │  │
│  │    ·事件推送              │  │    ·多机位画面合成            │  │
│  └──────────────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 上帝视角 (God View) 设计

上帝视角允许 OB 操作员自由移动镜头，核心特性：

```
上帝视角的关键参数：

  相机模式:    正交投影 (Orthographic) 或 透视投影 (Perspective)
  俯仰范围:    15° ~ 85° (防止完全水平/垂直的 disorienting 镜头)
  高度范围:    5m ~ 50m (地图视野缩放)
  移动速度:    基础 20m/s，Shift 加速至 40m/s
  旋转速度:    30°/s (右键拖拽)
  边界限制:    相机不可移出地图边界（防止黑边）
```

```csharp
// OB 上帝视角相机控制
public class OBGodCamera : MonoBehaviour
{
    [Header("配置")]
    [SerializeField] float _moveSpeed = 20f;
    [SerializeField] float _fastSpeed = 40f;
    [SerializeField] float _rotateSpeed = 30f;
    [SerializeField] float _zoomSpeed = 5f;
    [SerializeField] float _minHeight = 5f;
    [SerializeField] float _maxHeight = 50f;
    [SerializeField] float _minPitch = 15f;
    [SerializeField] float _maxPitch = 85f;
    
    [Header("边界")]
    [SerializeField] Bounds _mapBounds = new(Vector3.zero, new Vector3(200, 0, 200));
    
    Vector3 _targetPosition;
    float _targetYaw;
    float _targetPitch = 60f;
    float _targetZoom = 20f;
    
    Vector3 _dragStartMouse;
    Vector3 _dragStartCamera;
    bool _isDragging;
    
    void Update()
    {
        HandleMovement();
        HandleRotation();
        HandleZoom();
        ApplyTransform();
    }
    
    void HandleMovement()
    {
        Vector3 move = Vector3.zero;
        
        if (Input.GetKey(KeyCode.W)) move += Vector3.forward;
        if (Input.GetKey(KeyCode.S)) move += Vector3.back;
        if (Input.GetKey(KeyCode.A)) move += Vector3.left;
        if (Input.GetKey(KeyCode.D)) move += Vector3.right;
        
        if (move.magnitude > 0)
        {
            float speed = Input.GetKey(KeyCode.LeftShift) ? _fastSpeed : _moveSpeed;
            // 移动方向投影到水平面
            Vector3 flatMove = Quaternion.Euler(0, _targetYaw, 0) * move.normalized;
            _targetPosition += flatMove * speed * Time.deltaTime;
        }
        
        // 中键拖拽平移
        if (Input.GetMouseButtonDown(2))
        {
            _isDragging = true;
            _dragStartMouse = Input.mousePosition;
            _dragStartCamera = _targetPosition;
        }
        if (Input.GetMouseButtonUp(2)) _isDragging = false;
        
        if (_isDragging)
        {
            Vector3 delta = Input.mousePosition - _dragStartMouse;
            // 屏幕空间偏移 → 世界空间偏移（考虑当前高度）
            float scale = _targetZoom / Screen.height * 2f;
            _targetPosition = _dragStartCamera 
                + new Vector3(-delta.x, 0, -delta.y) * scale;
        }
        
        // 钳制在地图边界内
        _targetPosition.x = Mathf.Clamp(_targetPosition.x, 
            _mapBounds.min.x, _mapBounds.max.x);
        _targetPosition.z = Mathf.Clamp(_targetPosition.z, 
            _mapBounds.min.z, _mapBounds.max.z);
    }
    
    void HandleRotation()
    {
        if (Input.GetMouseButton(1)) // 右键旋转
        {
            _targetYaw += Input.GetAxis("Mouse X") * _rotateSpeed;
            _targetPitch -= Input.GetAxis("Mouse Y") * _rotateSpeed;
            _targetPitch = Mathf.Clamp(_targetPitch, _minPitch, _maxPitch);
        }
    }
    
    void HandleZoom()
    {
        _targetZoom -= Input.GetAxis("Mouse ScrollWheel") * _zoomSpeed;
        _targetZoom = Mathf.Clamp(_targetZoom, _minHeight, _maxHeight);
    }
    
    void ApplyTransform()
    {
        // 球坐标 → 世界坐标
        float pitchRad = _targetPitch * Mathf.Deg2Rad;
        float yawRad = _targetYaw * Mathf.Deg2Rad;
        
        Vector3 offset = new Vector3(
            Mathf.Cos(pitchRad) * Mathf.Sin(yawRad),
            Mathf.Sin(pitchRad),
            Mathf.Cos(pitchRad) * Mathf.Cos(yawRad)
        ) * _targetZoom;
        
        transform.position = _targetPosition + offset;
        transform.LookAt(_targetPosition);
    }
}
```

### 5.3 导演模式 (Director Mode)

导演模式的核心是**决策算法**——在任意时刻决定"应该把镜头给谁"：

```csharp
// OB 导演模式：AI 驱动的镜头决策系统
public class OBDirectorSystem
{
    // 镜头关注点（候选目标）
    struct FocusCandidate
    {
        public int playerIdx;
        public Vector3 position;
        public float score;
        public string reason;  // 为什么选中（用于日志/调试）
    }
    
    // 事件驱动的强制切换（优先级最高）
    Dictionary<string, float> _eventPriorities = new()
    {
        { "Pentakill",   100f },
        { "QuadraKill",   90f },
        { "TripleKill",   80f },
        { "DoubleKill",   70f },
        { "FirstBlood",   85f },
        { "Kill",         60f },
        { "BaronSteal",   95f },
        { "TowerDestroy", 50f },
        { "TeamFight5v5", 75f },
        { "TeamFight3v3", 55f },
    };
    
    float _switchCooldown = 0f;
    const float MIN_SWITCH_INTERVAL = 4.0f; // 最短切换间隔（避免镜头抖动）
    
    int _currentFocus = -1;
    GameWorld _world;
    
    /// <summary>
    /// 每帧调用：返回当前应该聚焦的玩家索引。
    /// 返回 -1 表示保持当前镜头不变。
    /// </summary>
    public int GetDirectorFocus(float dt)
    {
        _switchCooldown -= dt;
        
        // 1. 检查是否有紧急事件需要强制切换
        var urgentEvent = GetHighestPriorityEvent();
        if (urgentEvent != null)
        {
            if (urgentEvent.involvedPlayerIdx != _currentFocus 
                || _switchCooldown <= 0)
            {
                _currentFocus = urgentEvent.involvedPlayerIdx;
                _switchCooldown = MIN_SWITCH_INTERVAL;
                Debug.Log($"[Director] Event-driven switch: {urgentEvent.type} → Player {_currentFocus}");
                return _currentFocus;
            }
            return -1; // 已经在看这个玩家，不切换
        }
        
        // 2. 没有紧急事件时，用启发式算法选择"最有趣的"玩家
        if (_switchCooldown <= 0)
        {
            var candidates = ScoreAllPlayers();
            candidates.Sort((a, b) => b.score.CompareTo(a.score));
            
            if (candidates.Count > 0 && candidates[0].playerIdx != _currentFocus)
            {
                _currentFocus = candidates[0].playerIdx;
                _switchCooldown = MIN_SWITCH_INTERVAL;
                Debug.Log($"[Director] Heuristic switch: {candidates[0].reason} → Player {_currentFocus}");
                return _currentFocus;
            }
        }
        
        return -1;
    }
    
    /// <summary>
    /// 评分所有玩家：综合考虑多个维度
    /// </summary>
    List<FocusCandidate> ScoreAllPlayers()
    {
        var candidates = new List<FocusCandidate>();
        
        for (int i = 0; i < _world.PlayerCount; i++)
        {
            var player = _world.GetPlayer(i);
            float score = 0f;
            string reason = "";
            
            // 因子1：经济领先/落后程度（有故事性）
            float goldScore = Mathf.Abs(player.Gold - _world.AverageGold) 
                              / Mathf.Max(_world.AverageGold, 1) * 20f;
            score += goldScore;
            
            // 因子2：附近敌人数量（可能在打架）
            int nearby = _world.CountNearbyEnemies(i, 30f);
            float combatScore = nearby * 15f;
            score += combatScore;
            if (combatScore > 30f) reason = "团战中心";
            
            // 因子3：血量百分比（越低越刺激）
            float hpScore = (1f - player.HpPercent) * 25f;
            score += hpScore;
            if (player.HpPercent < 0.2f) reason = "极限血量";
            
            // 因子4：技能释放频率（操作密集度）
            float apmScore = player.RecentAPM / 200f * 10f;
            score += apmScore;
            
            // 因子5：连胜/连杀状态
            float streakScore = player.KillStreak * 10f;
            score += streakScore;
            if (player.KillStreak >= 5) reason = "连杀中";
            
            // 因子6：距离上次被观察的时间（避免重复看同一个人）
            // ... 实现略
            
            candidates.Add(new FocusCandidate
            {
                playerIdx = i,
                position = player.Position,
                score = score,
                reason = reason
            });
        }
        
        return candidates;
    }
    
    UrgentEvent GetHighestPriorityEvent()
    {
        // 查询最近3秒内的游戏事件
        // ... 实现略
        return null;
    }
}
```

### 5.4 数据面板 (HUD) 设计

OB 系统的数据面板是赛事转播的核心元素：

```
┌─────────────────────────────────────────────────────────────────┐
│  蓝方                       25:43                       红方    │
│  ═══════                                              ═══════   │
│  击杀: 12                                           击杀: 8    │
│  经济: 45.2K                                         经济: 38.1K│
│  ────────────────────────────────────────────────────────────  │
│                                                                 │
│  ┌──────────┐                                    ┌──────────┐  │
│  │ Player1  │ Lv.15  ├── 经济曲线 ──┤  Lv.14 │ Player6  │  │
│  │ ═══════ │  HP ████████░░          ████░░  HP │ ═══════ │  │
│  │ 12/3/8  │  MP ████░░░░░░          ████░░  MP │ 8/5/10  │  │
│  │ 装备槽:  │                                    │ 装备槽:  │  │
│  │ [⚔][🛡][👢]│                                  │ [⚔][⚔][👢]│  │
│  │ [💍][📿]  │                                  │ [💍][🛡]  │  │
│  └──────────┘                                    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 观战服务器架构

### 6.1 为什么需要独立的观战服务器？

核心原因三个：

1. **隔离影响**：观战者的网络波动（重连、慢速客户端）不应影响战斗服务器的帧同步时序
2. **独立扩容**：热门比赛的观战人数可能是参战人数的 1000 倍，需要独立水平扩展
3. **安全隔离**：观战服务器暴露在公网（观众来自世界各地），战斗服务器可在内网

```
                    ┌─────────────────────────┐
                    │      战斗服务器集群       │
                    │  (内网，低延迟，安全)      │
                    │                          │
                    │  DS#1  DS#2  DS#3  ...  │
                    └─────┬──────┬──────┬──────┘
                          │      │      │
                    镜像数据流  │      │
                          ▼      ▼      ▼
                    ┌─────────────────────────┐
                    │      观战服务器集群       │
                    │  (公网，可水平扩展)       │
                    │                          │
                    │  Spec#1  Spec#2  ...    │
                    └─────┬──────┬────────────┘
                          │      │
                    ┌─────┴──────┴─────┐
                    │    观众/OB客户端   │
                    └───────────────────┘
```

### 6.2 镜像数据流

观战服务器通过**镜像复制**从战斗服务器获取数据：

```csharp
// 战斗服务器侧：将每帧数据推送到观战服务器
public class BattleToSpectatorMirror
{
    List<string> _spectatorServerAddrs;
    UdpClient _mirrorClient;
    
    /// <summary>
    /// 每逻辑帧调用一次。
    /// 将本帧的输入和状态快照推送给所有观战服务器。
    /// </summary>
    public void MirrorFrame(uint frameNo, PlayerInput[] inputs, 
                           GameState snapshot)
    {
        // 构造镜像数据包
        var packet = new MirrorPacket
        {
            battleId = _battleId,
            frameNo = frameNo,
            inputs = inputs,
            // 状态快照不每帧都发——每 30 帧发一次完整快照
            // 其余帧只发增量（脏字段）
            snapshot = (frameNo % 30 == 0) ? snapshot : null,
            dirtyEntities = (frameNo % 30 != 0) 
                ? snapshot.GetDirtyEntities() : null,
        };
        
        byte[] data = Serialize(packet);
        
        // 发送给所有观战服务器（UDP 广播或逐个发送）
        foreach (var addr in _spectatorServerAddrs)
        {
            _mirrorClient.Send(data, data.Length, addr, 9100);
        }
    }
}
```

### 6.3 观战服务器的水平扩展

当一场热门比赛有百万观战者时，单台观战服务器不够。需要**级联架构**：

```
                      战斗服务器 (唯一的)
                           │
                    镜像数据 (1份)
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        观战边缘节点1  观战边缘节点2  观战边缘节点3
        (亚洲)         (欧洲)         (北美)
              │            │            │
         ┌────┼────┐  ┌────┼────┐  ┌────┼────┐
         ▼    ▼    ▼  ▼    ▼    ▼  ▼    ▼    ▼
        观众  观众  观众 ...
```

**边缘节点内部**使用**扇出（Fan-out）** 模式：

```cpp
// 观战边缘节点：接收一份镜像数据 → 扇出给 N 个观战者
class SpectatorEdgeNode {
    // 来自战斗服务器的单路输入
    // 扇出给 up to 10,000 个观战者
    
    void onMirrorData(const MirrorPacket& pkt) {
        // 不需要每帧都给每个观战者单独发——使用组播/广播
        // 或者将观战者分组，每组共享一个发送缓冲区
        
        for (auto& group : _spectatorGroups) {
            // 组内所有观战者共享相同的延迟配置
            auto delayed = applyDelay(pkt, group.delaySeconds);
            group.multicast(delayed);
        }
    }
};
```

---

## 7. 练习

### 练习 1: 基础 — 实现简单的延迟观战客户端 (30min)

**目标**：在已有帧同步客户端框架上，实现一个基础的延迟观战功能。

**要求**：
1. 实现 `SpectatorClient` 类，包含：
   - `JoinBattle(battleId, delayFrames)` — 加入观战
   - `OnFrameInput(frameNo, inputs)` — 接收帧输入
   - 以固定步长消费 `_pendingInputs` 队列执行逻辑帧
2. 延迟实现：观战者永远落后服务器 `delayFrames` 帧
3. 测试：用本地双进程模拟——战斗进程产生输入 → 观战进程接收并执行，验证状态一致性

**提示**：复用教程 08 的 `GameWorld` 和 `FrameSyncClient` 基础代码。

**验收标准**：
- 观战客户端能正确连接到战斗服务器
- 观战者看到的状态与战斗者 delayFrames 帧前的状态一致
- 断线重连后能恢复（重新请求快照+后续帧）

---

### 练习 2: 进阶 — 实现多视角切换与战争迷雾过滤 (45min)

**目标**：在观战客户端中实现视角切换，包括上帝视角和玩家第一视角（含战争迷雾）。

**要求**：
1. 实现 `SpectatorViewManager`，支持以下视角模式：
   - 上帝视角 (God View)：全图可见，WASD 移动 + 右键旋转视角
   - 玩家跟随 (Follow)：相机锁定目标玩家，平滑跟随
   - 第一人称 (First Person)：显示目标玩家的战争迷雾，只看该玩家可见的实体
2. 视角切换快捷键：F1=上帝视角, F2=循环切换玩家
3. 实现简单的战争迷雾过滤：`_world.GetPlayerVisibility(playerIdx)` 返回可见实体集合

**验收标准**：
- 三种视角模式可以正确切换
- 上帝视角可以看到所有实体
- 第一人称视角下，不可见实体被隐藏/半透明显示
- 相机平滑跟随无抖动

---

### 练习 3: 挑战 — 设计一个可扩展的导演模式系统 (60min)

**目标**：设计并实现一个导演模式系统，能根据游戏事件自动选择最佳镜头。

**要求**：
1. **事件优先级系统**：
   - 定义事件类型（击杀、团战、推塔等）和优先级
   - 事件发生时自动切换镜头到事件位置
   - 支持事件冷却（同一类事件 8 秒内不重复切换）
2. **玩家评分系统**：
   - 综合经济、KDA、血量、附近敌人数量等因子
   - 定期重新评分，选择最高分玩家作为镜头焦点
3. **运镜系统**：
   - 镜头切换使用平滑过渡（贝塞尔曲线或 S 曲线缓动）
   - 支持预设运镜路径（如团战前的环绕镜头）
4. **可配置性**：
   - 优先级、评分权重通过配置文件（JSON）控制
   - 支持运行时调整参数

**验收标准**：
- 导演模式能自动跟随团战、击杀等高优先级事件
- 无事件时自动选择"最有趣"的玩家
- 镜头切换平滑，无突兀跳转
- 配置文件可调整行为

---

## 8. 常见陷阱

### 陷阱 1: 观战者影响战斗服务器性能

**症状**：观战人数增加后，战斗服务器的帧率下降。

**根因**：在战斗服务器进程中直接处理观战者连接——观战者的网络 IO 和序列化开销拖慢了战斗主循环。

**解决**：
- **必须将观战服务器与战斗服务器分离**（独立进程/独立机器）
- 战斗服务器只做一次数据镜像推送（给观战服务器），不做 1→N 扇出
- 观战服务器的扇出开销独立承担

### 陷阱 2: 快照帧号不匹配导致加入时状态错误

**症状**：新观战者加入后，看到的游戏状态与实际不符（英雄在错误位置、血量不对等）。

**根因**：观战者请求加入时获取的快照帧号是 `N`，但随后收到的输入帧从 `N+5` 开始，丢失了 `N+1` 到 `N+4` 的输入。

**解决**：
```
// 正确的做法：确保快照帧号和输入流无缝衔接
JoinResponse response = spectatorServer.AcceptJoin(battleId);

// 1. 快照帧号 = 起始帧号
uint snapshotFrame = response.SnapshotFrameNo;  // 例如 15000

// 2. 第一帧输入必须从 snapshotFrame + 1 开始
uint nextInputFrame = snapshotFrame + 1;

// 3. 服务端保证：从 snapshotFrame 帧之后的所有输入都不会丢失
//    （输入环形缓冲区容量 ≥ 延迟窗口 + 安全余量）
```

### 陷阱 3: 延迟观战的"延迟"用帧数度量而非时间

**症状**：在不同帧率的对局中，同样的延迟配置给用户的体验不同（60fps 下 3 分钟延迟 vs 15fps 下 3 分钟延迟）。

**根因**：用帧数定义延迟（如 `delayFrames = 10800`），但游戏逻辑帧率可能变化。

**解决**：
- **延迟应该用秒数定义，转换为帧数时使用当前对局的实际逻辑帧率**
- 示例：`delayFrames = delaySeconds * actualFrameRate`
- 对于支持可变帧率的混合同步，格外注意——延迟窗口的帧数不是常数

### 陷阱 4: 观战者在战争迷雾视角下看到不应看到的信息

**症状**：切换到玩家第一视角时，观战者仍然能看到敌方隐身的英雄。

**根因**：战争迷雾过滤只检查了"实体是否在可见集合中"，但没有检查"实体是否应该可见"（隐身状态、草丛状态等）。

**解决**：
```csharp
// 完善的可见性检查要包含多层过滤
public bool IsEntityVisibleToSpectator(Entity entity, int followPlayer)
{
    // 第一层：该玩家是否拥有该实体的视野
    if (!_world.PlayerVisibility[followPlayer].Contains(entity.Id))
        return false;
    
    // 第二层：实体自身的可见性状态
    if (entity.HasState(EntityState.Invisible))  // 隐身
        return false;
    if (entity.HasState(EntityState.InBush)      // 在草丛且无真眼
        && !_world.HasTrueSight(followPlayer, entity.Position))
        return false;
    
    // 第三层：特殊技能效果（如诡术妖姬分身）
    if (entity.IsIllusion && !_world.CanSeeIllusions(followPlayer))
        return false;
    
    return true;
}
```

### 陷阱 5: 导演模式镜头频繁切换造成观感不适

**症状**：导演模式镜头每 1-2 秒就切换一次，观看体验极差。

**根因**：评分系统对微小变化过于敏感——两个玩家评分接近时，微小的事件就会导致镜头来回跳。

**解决**：
1. **切换冷却**：强制最短切换间隔（如 4 秒）
2. **滞后阈值 (Hysteresis)**：新目标分数必须比当前目标高 15% 以上才切换
3. **预测性保持**：如果检测到团战即将发生（多名玩家接近），保持当前镜头不变
4. **平滑过渡时间**：镜头切换使用至少 1.5 秒的缓动

---

## 9. 扩展阅读

- **Dota2 Spectator System** — Source 引擎的观战系统设计：Steam 平台最成熟的观战架构之一，支持实时观战、延迟观战、教练模式
- **League of Legends Spectator** — Riot 的观战架构白皮书：解释了他们的 3 分钟延迟策略和数据中心间同步方案
- **Overwatch League Observer Client** — 专为电竞赛事设计的 OB 客户端，包含画中画、热力图、3D 回放等高级功能
- **GGPO Rollback Networking** — 虽然不是观战系统，但其"输入预测+回滚"的思路可应用于观战者的快进/快退（通过跳帧+重新模拟实现）
- **Unity Cinemachine** — Unity 的虚拟相机系统，其 `CinemachineVirtualCamera` 和 `CinemachineClearShot` 可直接用于构建 OB 系统的相机管理
- **NDI (Network Device Interface)** — 视频流传输协议，可用于 OB 客户端向转播车/推流服务器输出视频信号
