---
title: "游戏循环与网络Tick集成"
updated: 2026-06-05
---

# 游戏循环与网络Tick集成

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 45min
> 前置知识: 03-序列化与通信协议设计

---

## 1. 概念讲解

### 为什么需要游戏循环与网络Tick集成？

所有多人游戏都面临同一个根本矛盾：**游戏逻辑是离散的（按帧/步进执行），网络是异步的（包到达时间不可预测），但玩家期望的是连续的、低延迟的体验**。如果游戏循环和网络发送/接收的频率不协调，会出现三类典型问题：

| 问题 | 表现 | 根因 |
|------|------|------|
| **逻辑帧抖动** | 角色移动忽快忽慢，技能释放时机漂移 | 逻辑更新频率随渲染帧率波动 |
| **带宽浪费/拥堵** | 网络包堆积或空转 | 发送频率与逻辑帧脱钩 |
| **物理不一致** | 客户端和服务器碰撞结果不同 | PhysX/Chaos 的浮点计算 + 不同步长 |

**例子**：假设服务器以 30Hz 运行逻辑，客户端以 60fps 渲染，但网络每秒只发 20 个包。如果三者的节奏不协调，客户端的画面、服务端的判定、网络包的收发就会像"三个不同速度的齿轮"——卡死是时间问题。

### 核心思想

```
┌─────────────────────────────────────────────────────────────────┐
│                        游戏主循环                               │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  输入采集 │ → │  逻辑更新 │ → │  物理模拟 │ → │  渲染呈现 │  │
│  │ (Input)  │    │ (Logic)  │    │(Physics) │    │ (Render)  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │               │               │               │        │
│       ▼               ▼               ▼               ▼        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              网络Tick层（独立调度）                       │  │
│  │  · Send Tick:  每 N 个逻辑帧发送一次状态快照              │  │
│  │  · Recv Tick:  每 M 毫秒检查一次接收缓冲区                │  │
│  │  · Cmd Tick:   玩家指令采样频率（可与逻辑帧解耦）          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

核心要解决的问题只有三个：

1. **频率匹配**：逻辑帧、渲染帧、网络发送、网络接收——四个频率各自是什么关系？
2. **时间基准**：分布式环境下，每个端对"当前帧"的理解如何对齐？
3. **缓冲策略**：输入指令和网络包各自需要多大的缓冲区？何时消费？

---

### 1.1 游戏主循环基础：逻辑帧 vs 渲染帧

#### FixedUpdate vs Update（Unity 视角）

Unity 的主循环分两个通道：

```
Unity Engine Loop (简化)
│
├─ Time.fixedDeltaTime (默认 0.02s = 50Hz)
│   └─ FixedUpdate()    ← 物理/逻辑更新，固定步长
│       └─ 内部: Physics.Simulate(fixedDeltaTime)
│       └─ 可能一帧内调用 0 次、1 次或多次
│
├─ Time.deltaTime (可变，取决于帧率)
│   └─ Update()          ← 输入采集、渲染前逻辑
│   └─ LateUpdate()      ← 相机跟随、渲染后调整
│
└─ 渲染管线
```

**关键特性**：`FixedUpdate` 在一帧内可以执行 0 次、1 次或多次。当渲染帧率高于物理帧率时，某些帧不会执行 `FixedUpdate`；当渲染帧率低于物理帧率时，一帧内会执行多次 `FixedUpdate` 来"追赶"物理时间。

#### 逻辑帧 vs 渲染帧

```
时间线:  0ms        16ms       33ms       50ms       66ms
         │          │          │          │          │
渲染帧:  [Frame 0]  [Frame 1]  [Frame 2]  [Frame 3]  [Frame 4]
         │     │    │     │    │          │     │    │
Fixed:   [Tick0][Tick1]       [Tick2]    [Tick3][Tick4]
         (0ms) (16ms)         (33ms)     (50ms) (66ms)
```

- **渲染帧**：由 GPU vsync 或应用层帧率控制决定，间隔可变
- **逻辑帧/物理帧**：固定步长（如 16.67ms 对应 60Hz，33.33ms 对应 30Hz）
- **分离的好处**：即使画面掉帧到 15fps，物理逻辑仍以 50Hz 稳定推进，碰撞和运动不会出错

#### 为什么逻辑帧必须是固定步长？

```csharp
// 错误做法：逻辑用可变 deltaTime
void Update() {
    float dt = Time.deltaTime;
    player.position += velocity * dt; // 每帧 dt 都不同
}
// 问题：浮点运算 (a*dt1 + a*dt2) ≠ a*(dt1+dt2)，尤其在长时间运行后累积误差
// 问题：碰撞检测对步长敏感——步长太大可能"穿过"薄墙（tunneling）
```

```csharp
// 正确做法：固定步长的逻辑帧
void FixedUpdate() {
    float dt = Time.fixedDeltaTime; // 始终 0.02s
    player.position += velocity * dt; // 确定性高
}
```

### 1.2 网络Tick的概念

网络游戏中有三个独立的"频率"概念：

| 术语 | 含义 | 典型值 | 控制方 |
|------|------|--------|--------|
| **Tick Rate** | 服务器逻辑更新频率 | 30/60/128 Hz | 服务器 |
| **Send Rate** | 服务器向客户端发包频率 | 20/30/60 Hz | 服务器 |
| **Command Rate** | 客户端发送指令频率 | 等于客户端帧率或定频 | 客户端 |

> **注意**：不同引擎/游戏对术语的使用可能不同。CS:GO 的 `tickrate` 128 指服务器逻辑+发包频率；Overwatch 的 tick rate 是 60Hz 但客户端发送指令频率是 60Hz。**面试中要能区分这三个概念，并说明你在讨论哪一个。**

#### Tick Rate 与 Send Rate 的关系

```
Tick Rate = 60Hz (每 16.67ms)
Send Rate = 20Hz (每 50ms)

时间线:
Tick:   T0    T1    T2    T3    T4    T5    T6
        │     │     │     │     │     │     │
Send:   S0──────────S1──────────S2──────────S3
        │            │            │            │
发送内容: [T0状态]   [T2,T3合并]  [T5状态]     [T7状态]
                           ↑
                  Send Rate < Tick Rate 时，需要合并/采样
```

- **Tick Rate = Send Rate**：每帧逻辑结果即时发送（状态同步常见）
- **Tick Rate > Send Rate**：多个逻辑帧的结果按策略采样发送（节省带宽）
- **Tick Rate < Send Rate**：无意义，逻辑还没算完就发包只是浪费

#### Command Rate

客户端发送指令（按键、鼠标移动）的频率：

- **按帧率发送**：每渲染帧都发送指令 → 60fps = 60 cmd/s，流畅但带宽高
- **固定频率发送**：每 33ms 发送一次（30Hz）→ 降低上行带宽，但指令精度下降
- **变化触发发送**：有按键变化时才发送 → 省带宽但可能导致"最后一条指令"丢失

### 1.3 常见Tick模型

#### 模型一：固定Tick（Fixed Timestep）

```
┌──────────────────────────────────────────┐
│  逻辑帧: 固定步长 (如 16.67ms = 60Hz)    │
│  渲染帧: 可变步长                        │
│  网络: 通常与逻辑帧对齐                  │
│                                          │
│  代表: 帧同步(Lockstep)游戏              │
│  例子: 王者荣耀(逻辑帧 66ms=15Hz)        │
│        Dota 2(逻辑帧 33ms=30Hz)          │
└──────────────────────────────────────────┘
```

帧同步中，逻辑帧是最核心的时钟：
- 所有客户端以**相同帧号**推进逻辑
- 服务器控制全局帧号（或使用乐观帧锁定）
- 每个逻辑帧开始前，必须收集齐该帧所有玩家的操作指令

```csharp
// Unity 帧同步逻辑帧实现
public class LockstepTicker : MonoBehaviour
{
    [SerializeField] private int _targetTickRate = 30;
    private float _tickInterval;     // 33.33ms @ 30Hz
    private float _accumulator;
    private uint _currentTick;

    void Awake()
    {
        _tickInterval = 1.0f / _targetTickRate;
        // 禁用 Unity 默认的 FixedUpdate 物理步进
        // 帧同步不使用 PhysX，使用自己的确定性物理
        Physics.autoSimulation = false;
    }

    void Update()
    {
        _accumulator += Time.deltaTime;

        // 追赶逻辑帧：即使渲染掉帧，逻辑帧也按固定步长推进
        while (_accumulator >= _tickInterval)
        {
            _accumulator -= _tickInterval;
            ExecuteLogicTick(_currentTick++);
        }

        // 渲染插值：用剩余的 _accumulator 在两个逻辑帧之间插值
        float alpha = _accumulator / _tickInterval;
        InterpolateRenderState(alpha);
    }

    void ExecuteLogicTick(uint tick)
    {
        // 1. 检查该帧所有玩家的指令是否已到达
        if (!HasAllCommandsForTick(tick))
        {
            // 帧同步关键：指令不齐 → 等待（产生"卡帧"）
            return;
        }

        // 2. 执行确定性逻辑
        GameLogic.Update(_tickInterval); // 所有客户端运行相同代码

        // 3. 如果本客户端有未发送指令，发送给服务器
        FlushPendingCommands(tick);
    }
}
```

#### 模型二：可变Tick（Variable Timestep）

```
┌──────────────────────────────────────────┐
│  逻辑帧 = 渲染帧（步长可变）              │
│  物理按子步长细分                        │
│                                          │
│  代表: 单机游戏、部分轻量联机             │
│  风险: 逻辑非确定性，不适合竞技类联机     │
└──────────────────────────────────────────┘
```

```csharp
// 可变Tick示例（不推荐用于竞技联机）
void Update()
{
    float dt = Time.deltaTime; // 可变步长
    ProcessInput(dt);
    UpdateGameLogic(dt);       // 每帧步长不同！
    SendNetworkState();
}
// 问题：dt 不同导致计算结果的浮点误差不同
// 两台电脑上同样的输入字符串，结果可能因为帧率不同而不同
```

#### 模型三：独立网络Tick（Decoupled Tick）

```
┌──────────────────────────────────────────┐
│  逻辑帧: 固定 60Hz                       │
│  渲染帧: 可变 (vsync)                    │
│  发送帧: 固定 30Hz（不等于逻辑帧）        │
│  接收帧: 事件驱动（或按固定间隔 poll）    │
│                                          │
│  代表: Overwatch（状态同步）             │
│        逻辑60Hz + 发60Hz + 收事件驱动    │
│        但发送≠逻辑：发送的是状态快照     │
└──────────────────────────────────────────┘
```

```csharp
// 独立网络Tick：逻辑、渲染、网络三者解耦
public class DecoupledTickManager : MonoBehaviour
{
    [SerializeField] private int _logicTickRate  = 60;
    [SerializeField] private int _networkSendRate = 30;
    [SerializeField] private int _networkRecvRate = 30;

    private float _logicAccumulator;
    private float _sendAccumulator;
    private float _recvAccumulator;
    private float _logicDt, _sendDt, _recvDt;

    void Awake()
    {
        _logicDt = 1.0f / _logicTickRate;
        _sendDt  = 1.0f / _networkSendRate;
        _recvDt  = 1.0f / _networkRecvRate;
    }

    void Update()
    {
        float frameDt = Time.deltaTime;
        _logicAccumulator += frameDt;
        _sendAccumulator  += frameDt;
        _recvAccumulator  += frameDt;

        // 逻辑帧：固定步长，可能一帧执行多次
        while (_logicAccumulator >= _logicDt)
        {
            _logicAccumulator -= _logicDt;
            ExecuteLogicStep(_logicDt);
        }

        // 网络发送：固定频率，状态快照
        while (_sendAccumulator >= _sendDt)
        {
            _sendAccumulator -= _sendDt;
            SendStateSnapshot();
        }

        // 网络接收：按固定间隔消费接收缓冲区
        while (_recvAccumulator >= _recvDt)
        {
            _recvAccumulator -= _recvDt;
            ProcessReceivedPackets();
        }

        // 渲染：用剩余时间插值
        Render(_logicAccumulator / _logicDt);
    }
}
```

### 1.4 帧同步的Tick模型

帧同步（Lockstep）的Tick模型有严格的帧号概念：

```
                    服务器（帧号权威源）
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
 Client A        Client B        Client C
    │               │               │
    │ 发送帧N指令   │ 发送帧N指令   │ 发送帧N指令
    │ ───────────→  │ ───────────→  │ ───────────→
    │               │               │
    │    服务器收集齐所有指令，广播帧N指令包             │
    │ ←─────────── │ ←─────────── │ ←───────────
    │               │               │
    ▼               ▼               ▼
 执行帧N逻辑     执行帧N逻辑     执行帧N逻辑
 （结果完全相同）（结果完全相同）（结果完全相同）
```

核心特征：

- **帧号是全局唯一的时钟**
- 帧N必须等到所有玩家的帧N指令到齐才能执行
- 如果某玩家的指令未到 → **全体等待**（这是帧同步"卡"的根源）
- 服务器的帧号推进有两种策略：
  - **严格帧锁定**：等齐所有人才推进
  - **乐观帧锁定**：不等齐，先推进，超时补帧

```csharp
// 服务器端帧同步Tick控制
public class LockstepServerTick
{
    private uint _serverFrame = 0;
    private float _frameInterval = 0.033f; // 30Hz
    private float _timer;
    private Dictionary<uint, Dictionary<int, byte[]>> _frameCommands
        = new(); // frameNo -> (playerId -> cmd)
    private int _playerCount;
    private uint _maxAheadFrames = 3; // 客户端最多领先服务器3帧

    void Update(float dt)
    {
        _timer += dt;
        if (_timer < _frameInterval) return;
        _timer -= _frameInterval;

        // 检查当前帧是否所有玩家指令到齐
        if (_frameCommands.TryGetValue(_serverFrame, out var cmds)
            && cmds.Count == _playerCount)
        {
            // 所有指令到齐，打包广播
            BroadcastFrameCommands(_serverFrame, cmds);
            _frameCommands.Remove(_serverFrame);
        }
        else
        {
            // 超时策略：缺失玩家判为"无操作"
            // 帧同步中这是灾难性的——缺失玩家的客户端
            // 和服务器/其他客户端的结果将不同
            LogWarning($"Frame {_serverFrame} missing commands");
            // 实际做法：填充空操作
            FillEmptyCommands(_serverFrame);
        }

        _serverFrame++;
    }

    // 接收客户端指令，携带客户端帧号
    public void OnClientCommand(int playerId, uint clientFrame, byte[] cmd)
    {
        // 帧号映射：客户端帧号 → 服务器帧号
        uint serverFrame = MapClientToServerFrame(playerId, clientFrame);

        // 拒绝超前的帧（防作弊：不能让客户端预发未来帧的指令）
        if (serverFrame > _serverFrame + _maxAheadFrames)
        {
            LogWarning($"Player {playerId} sent too far ahead frame");
            return;
        }

        if (!_frameCommands.ContainsKey(serverFrame))
            _frameCommands[serverFrame] = new Dictionary<int, byte[]>();
        _frameCommands[serverFrame][playerId] = cmd;
    }
}
```

```csharp
// 客户端端帧同步Tick控制
public class LockstepClientTick
{
    private uint _localFrame = 0;
    private float _frameInterval;
    private float _accumulator;
    private Queue<uint> _readyFrames = new(); // 已收到服务器回包的帧号
    private Dictionary<uint, FrameData> _pendingFrames = new(); // 待执行的帧
    private uint _maxBufferedFrames = 5; // 客户端最多缓冲5帧（控制延迟）

    void Update()
    {
        _accumulator += Time.deltaTime;
        while (_accumulator >= _frameInterval)
        {
            _accumulator -= _frameInterval;

            // 1. 采集本玩家当前帧的输入
            var input = CaptureInput();
            SendInputToServer(_localFrame, input);

            // 2. 推进本地帧号
            _localFrame++;

            // 3. 消费已准备好的帧（指令已从服务器返回）
            while (_readyFrames.Count > 0)
            {
                uint readyFrame = _readyFrames.Dequeue();
                ExecuteFrame(readyFrame);
            }
        }
    }
}
```

### 1.5 状态同步的Tick模型

状态同步（State Sync）中，服务器是**唯一权威**：

```
服务器 (权威)
│  逻辑Tick: 30Hz 固定
│  物理Tick: 30Hz 固定（与逻辑同频或独立）
│  发送Tick: 30Hz（每逻辑帧发或下采样）
│
│          state snapshot (30Hz)
│  ───────────────────────────────→  客户端
│                                     │
│          player commands (按输入频) │
│  ←───────────────────────────────  │
│                                     │  本地预测Tick: 60Hz
│                                     │  插值Tick: 按渲染帧
│                                     │  和解Tick: 收到服务器状态时
```

```csharp
// 状态同步服务器Tick
public class StateSyncServerTick
{
    private float _tickInterval;  // e.g., 1/30 = 33.33ms
    private float _accumulator;
    private uint _serverTick;

    // 指令缓冲区：按Tick存储每个玩家的输入
    private Dictionary<uint, Dictionary<int, PlayerCommand>> _commandBuffer = new();

    void Update(float dt)
    {
        _accumulator += dt;
        while (_accumulator >= _tickInterval)
        {
            _accumulator -= _tickInterval;

            // 1. 消费该Tick收到的所有玩家指令
            ProcessCommands(_serverTick);

            // 2. 执行权威逻辑（移动、技能判定、伤害计算）
            RunAuthorityLogic(_tickInterval);

            // 3. 执行物理模拟（碰撞、弹道）
            RunPhysics(_tickInterval);

            // 4. 生成当前帧状态快照（只含变化的实体）
            var snapshot = BuildStateSnapshot(_serverTick);

            // 5. 发送给所有客户端（可能不是每Tick都发）
            BroadcastSnapshot(snapshot);

            _serverTick++;
        }
    }
}
```

### 1.6 时间同步（Clock Synchronization）

分布式系统中，没有全局时钟。客户端和服务器的时间必然不同步。时间同步的核心问题是：**客户端需要知道"服务器当前在第几帧"**。

#### 基础方法：往返时间（RTT）估算

```
Client                            Server
  │                                 │
  │──── T1 ────→                    │
  │                                 │ T2 = 服务器收到时的时间
  │                    ←──── T3 ────│
  │ T4 = 客户端收到回复             │
  │                                 │
  RTT = (T4 - T1) - (T3 - T2)     ≈ 网络往返时间
  ServerTime ≈ T2                  (服务器处理时刻)
  Offset    ≈ T2 - (T1 + RTT/2)   (时钟偏移)
```

#### NTP 简化版实现

```csharp
// 网络时间同步器（客户端侧）
public class NetworkTimeSync
{
    private const int MAX_SAMPLES = 8;
    private Queue<(float rtt, float offset)> _samples = new();
    private float _clockOffset = 0f; // 本地时间与服务器时间的偏移
    private float _roundTripTime = 0f;
    private float _syncInterval = 5f; // 每5秒重新同步
    private float _syncTimer;

    // 发送时间同步请求
    public void SendTimeRequest()
    {
        var msg = new TimeSyncRequest { ClientSendTime = Time.time };
        NetworkManager.Send(msg);
    }

    // 收到服务器回复
    public void OnTimeSyncResponse(float clientSendTime, float serverReceiveTime,
                                    float serverSendTime)
    {
        float clientReceiveTime = Time.time;
        float rtt = (clientReceiveTime - clientSendTime)
                    - (serverSendTime - serverReceiveTime);
        // 估计服务器在中间时刻的时间
        float estimatedServerTime = serverReceiveTime + (serverSendTime - serverReceiveTime) / 2f;
        float offset = estimatedServerTime - (clientSendTime + rtt / 2f);

        // 采样收集
        _samples.Enqueue((rtt, offset));
        if (_samples.Count > MAX_SAMPLES)
            _samples.Dequeue();

        // 异常值剔除：丢弃 RTT 超过 2 倍中位数的样本
        RecalculateOffset();
    }

    void RecalculateOffset()
    {
        var samples = _samples.ToArray();
        if (samples.Length == 0) return;

        // 按 RTT 排序，取 RTT 最小的 N/2 个样本
        // 原理：RTT 最小的样本，网络条件最稳定，offset 最准
        Array.Sort(samples, (a, b) => a.rtt.CompareTo(b.rtt));
        int goodCount = Math.Max(1, samples.Length / 2);
        float sumOffset = 0;
        for (int i = 0; i < goodCount; i++)
            sumOffset += samples[i].offset;

        _clockOffset = sumOffset / goodCount;
        _roundTripTime = samples[0].rtt; // 最小 RTT
    }

    // 获取当前服务器时间
    public float GetServerTime() => Time.time + _clockOffset;

    // 获取当前RTT（用于延迟补偿等）
    public float GetRTT() => _roundTripTime;

    void Update()
    {
        _syncTimer += Time.deltaTime;
        if (_syncTimer >= _syncInterval)
        {
            _syncTimer -= _syncInterval;
            SendTimeRequest();
        }
    }
}
```

#### 常见误区

- **单次采样就确定 offset**：网络抖动下，单次采样的误差可能达到 RTT 的量级
- **用平均值而非最小值**：offset 的准确性受网络波动影响。应取 RTT **最小**的样本——此时网络最"干净"，offset 最接近真实值
- **同步频率过高**：每帧都发 NTP 包 → 浪费带宽。5~10 秒一次即可
- **忽略服务器处理时间**：`serverSendTime - serverReceiveTime` 必须从 RTT 中扣除

### 1.7 Tick与物理引擎集成

#### Unity PhysX 集成

Unity 的物理引擎 PhysX 以 `Time.fixedDeltaTime` 为步长运行。在网络游戏中，需要做额外控制：

```csharp
// Unity 物理与网络Tick集成
public class NetworkedPhysicsTick : MonoBehaviour
{
    [SerializeField] private int _physicsTickRate = 30; // 与服务器Tick对齐
    [SerializeField] private float _maxCatchupTicks = 4; // 一帧最多追赶4个物理帧

    void Awake()
    {
        // 设置 Unity 物理步长，与服务器Tick对齐
        Time.fixedDeltaTime = 1.0f / _physicsTickRate;
        // 注意：修改 fixedDeltaTime 也会影响 FixedUpdate 的调用频率

        // 禁用自动物理模拟，改为手动控制
        Physics.autoSimulation = false;
    }

    void Update()
    {
        // 累积时间
        _physicsAccumulator += Time.deltaTime;

        // 手动驱动物理，限制追赶次数防止螺旋死亡(Death Spiral)
        int ticksExecuted = 0;
        while (_physicsAccumulator >= Time.fixedDeltaTime
               && ticksExecuted < _maxCatchupTicks)
        {
            _physicsAccumulator -= Time.fixedDeltaTime;

            // 在物理步进前，应用网络收到的权威位置修正
            ApplyServerCorrections();

            // 手动推进物理模拟
            Physics.Simulate(Time.fixedDeltaTime);

            // 物理后的逻辑处理
            PostPhysicsStep();

            ticksExecuted++;
        }

        // 如果还有剩余累积时间（渲染帧率太低），丢弃
        if (_physicsAccumulator >= Time.fixedDeltaTime)
        {
            _physicsAccumulator = 0f; // 防止螺旋
        }
    }
}
```

> **Death Spiral（螺旋死亡）**：当物理计算太慢，一帧内完不成所需的 FixedUpdate 次数时，累积时间越来越大 → 一帧内需要追赶的 FixedUpdate 越来越多 → 计算更慢 → 恶性循环。`_maxCatchupTicks` 是一个安全阀。

#### Unreal Chaos 集成

UE5 的 Chaos 物理系统也支持固定步长：

```cpp
// UE Chaos 物理Tick与网络集成
void UChaosNetworkComponent::TickComponent(
    float DeltaTime,
    ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

    // Chaos 物理通常独立于 GameThread 在专用线程运行
    // 但网络相关的物理修正需要在 GameThread 上应用

    if (TickType == LEVELTICK_All)
    {
        // 1. 处理收到的服务器物理修正
        ApplyServerPhysicsCorrections(DeltaTime);

        // 2. 本地物理预测（使用 Chaos 的异步 Tick）
        // 物理在 PhysicsThread 上以固定步长运行，不需要手动子步

        // 3. 物理结果"回读"需要在 GameThread 上进行
        ReadbackPhysicsResults();
    }
}

// UE 的 FTickFunction 层级结构
// - UWorld::Tick() 是总入口
//   - TG_PrePhysics:   FTickFunction 预物理阶段
//   - TG_DuringPhysics: 物理模拟（异步，不阻塞 GameThread）
//   - TG_PostPhysics:  物理结果后处理
//   - TG_LastDemotable: 可降级到下一帧的阶段

// 网络驱动 Tick：继承 FTickFunction 精确控制
USTRUCT()
struct FNetworkTickFunction : public FTickFunction
{
    GENERATED_BODY()

    // 设置Tick组：在网络驱动之前
    virtual void RegisterTickFunctions(class ULevel* Level) override
    {
        // TickGroup = TG_PrePhysics（在所有物理之前运行网络逻辑）
    }

    virtual void ExecuteTick(
        float DeltaTime,
        ELevelTick TickType,
        ENamedThreads::Type CurrentThread,
        const FGraphEventRef& MyCompletionGraphEvent) override
    {
        // 网络包接收 + 处理
        ProcessIncomingPackets(DeltaTime);

        // 生成外发包
        GenerateOutgoingPackets(DeltaTime);
    }
};
```

#### 物理引擎与网络的冲突处理

物理引擎（PhysX/Chaos）默认假设"本地环境是权威的"——这在联网游戏中是错的：

```csharp
// 冲突解决：当本地物理预测与服务器权威状态不一致时
public class PhysicsConflictResolver
{
    // 服务器发来的权威位置
    public void OnServerCorrection(int entityId, Vector3 serverPos,
                                    Quaternion serverRot, Vector3 serverVel)
    {
        var entity = GetEntity(entityId);
        float positionError = Vector3.Distance(entity.transform.position, serverPos);

        if (positionError > _correctionThreshold)
        {
            // 大误差 → 硬切（Teleport）
            entity.transform.position = serverPos;
            entity.transform.rotation = serverRot;
            entity.Rigidbody.velocity = serverVel;
        }
        else if (positionError > _smoothThreshold)
        {
            // 小误差 → 平滑修正
            StartCoroutine(SmoothCorrect(entity, serverPos, serverVel));
        }
        // 极小误差 → 忽略（避免频繁微调导致的抖动）
    }
}
```

### 1.8 前端的Buffer管理

#### 输入队列（Input Queue）

客户端采集的输入不能直接发给服务器——需要缓冲以匹配网络Tick：

```
玩家输入事件（异步、连续）
  │
  ▼
┌─────────────────────────────────┐
│         输入采集层              │
│  Unity:  Input.GetKey()        │
│  UE:     EnhancedInputAction   │
│  Lua:    Input.GetKeyDown()    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│       输入编码层                │
│  将原始按键 → 命令包            │
│  {tick:1234, cmd:0x03, data:..} │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│        输入缓冲区               │
│  ┌───┬───┬───┬───┬───┐         │
│  │F1 │F2 │F3 │F4 │F5 │  ...    │
│  └───┴───┴───┴───┴───┘         │
│  环形队列，按帧号索引           │
└────────────┬────────────────────┘
             │ 发包时机到来
             ▼
┌─────────────────────────────────┐
│         网络发送层              │
│  取缓冲区中的 N 帧指令，打包    │
│  冗余发送（帧同步常用）         │
└─────────────────────────────────┘
```

```csharp
// 环形输入缓冲区（帧同步客户端核心组件）
public class InputBuffer
{
    private struct InputEntry
    {
        public uint FrameNumber;
        public byte[] CommandData;
        public bool HasCommand;
    }

    private InputEntry[] _buffer;
    private uint _bufferStartFrame; // 缓冲区起始帧号
    private const int BUFFER_SIZE = 64; // 缓冲64帧 ≈ 2秒 @ 30Hz

    public InputBuffer()
    {
        _buffer = new InputEntry[BUFFER_SIZE];
    }

    // 写入一帧的输入
    public void WriteInput(uint frameNumber, byte[] command)
    {
        // 帧号超出缓冲区范围 → 扩容或拒绝
        if (frameNumber < _bufferStartFrame)
            return; // 已过期

        if (frameNumber >= _bufferStartFrame + BUFFER_SIZE)
            ExpandBuffer(frameNumber);

        int index = (int)(frameNumber % BUFFER_SIZE);
        _buffer[index].FrameNumber = frameNumber;
        _buffer[index].CommandData = command;
        _buffer[index].HasCommand = true;
    }

    // 读取一帧的输入（用于执行逻辑帧）
    public bool TryReadInput(uint frameNumber, out byte[] command)
    {
        command = null;
        if (frameNumber < _bufferStartFrame
            || frameNumber >= _bufferStartFrame + BUFFER_SIZE)
            return false;

        int index = (int)(frameNumber % BUFFER_SIZE);
        if (_buffer[index].HasCommand && _buffer[index].FrameNumber == frameNumber)
        {
            command = _buffer[index].CommandData;
            return true;
        }
        return false; // 指令未到达或帧号不匹配
    }

    // 清理已消费的帧
    public void AdvanceStartFrame(uint newStartFrame)
    {
        while (_bufferStartFrame < newStartFrame)
        {
            int index = (int)(_bufferStartFrame % BUFFER_SIZE);
            _buffer[index].HasCommand = false;
            _bufferStartFrame++;
        }
    }
}
```

#### 命令缓冲区（Command Buffer）

与输入队列不同，命令缓冲区关注的是**网络发送侧**的批处理：

```csharp
// 发送端命令缓冲区：收集多条指令，合并为一个包发送
public class CommandSendBuffer
{
    private MemoryStream _stream = new();
    private BinaryWriter _writer;
    private int _commandCount;
    private const int MAX_COMMANDS_PER_PACKET = 10;
    private const int MAX_PACKET_SIZE = 1200; // 略小于 MTU 1500

    public CommandSendBuffer()
    {
        _writer = new BinaryWriter(_stream);
    }

    public bool TryAddCommand(uint frameNumber, byte cmdType, byte[] data)
    {
        // 单条指令的预估大小 = 4(frame) + 1(type) + 2(len) + data
        int estimatedSize = 4 + 1 + 2 + (data?.Length ?? 0);

        if (_stream.Length + estimatedSize > MAX_PACKET_SIZE
            || _commandCount >= MAX_COMMANDS_PER_PACKET)
            return false; // 包已满，需要先发送

        // 写入帧号（相对当前包的基准帧号，用varint节省空间）
        _writer.Write7BitEncodedInt((int)frameNumber);
        _writer.Write(cmdType);
        if (data != null)
        {
            _writer.Write((ushort)data.Length);
            _writer.Write(data);
        }
        else
        {
            _writer.Write((ushort)0);
        }
        _commandCount++;
        return true;
    }

    public byte[] Flush()
    {
        if (_commandCount == 0) return null;

        byte[] packet = _stream.ToArray();
        _stream.SetLength(0);
        _stream.Position = 0;
        _commandCount = 0;
        return packet;
    }
}
```

#### 接收端环形缓冲区

```csharp
// 接收端缓冲区：缓冲收到的网络包，按帧号排序消费
public class ReceiveBuffer
{
    private SortedDictionary<uint, byte[]> _packets = new();
    private uint _nextExpectedFrame;

    // 插入一个收到的包
    public void InsertPacket(uint frameNumber, byte[] data)
    {
        // 拒绝过期包
        if (frameNumber < _nextExpectedFrame) return;

        _packets[frameNumber] = data;
    }

    // 尝试连续消费（按序取出，无空隙）
    public bool TryConsume(out uint frameNumber, out byte[] data)
    {
        frameNumber = 0;
        data = null;

        if (_packets.Count == 0) return false;

        var first = _packets.First();
        if (first.Key != _nextExpectedFrame) return false; // 有空隙，等待

        frameNumber = first.Key;
        data = first.Value;
        _packets.Remove(first.Key);
        _nextExpectedFrame = frameNumber + 1;
        return true;
    }
}
```

---

## 2. 代码示例

### 2.1 Unity: FixedUpdate 网络层集成框架

完整示例：一个固定步长的网络Tick系统，支持逻辑帧、渲染插值和网络同步。

```csharp
// NetworkTickManager.cs — Unity 网络Tick管理器
using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 核心Tick管理器：协调逻辑Tick、渲染帧和网络收发。
/// 适用场景：帧同步或状态同步客户端。
/// </summary>
public class NetworkTickManager : MonoBehaviour
{
    [Header("Tick Configuration")]
    [SerializeField] private int _logicTickRate = 30;   // 逻辑帧频率
    [SerializeField] private int _networkSendRate = 20;  // 网络发送频率
    [SerializeField] private int _maxCatchupTicks = 5;   // 一帧最多追赶的逻辑帧数

    [Header("Time Sync")]
    [SerializeField] private float _timeSyncInterval = 5f; // 时间同步间隔

    // 私有状态
    private float _logicDt;          // 逻辑帧步长
    private float _networkSendDt;    // 网络发送步长
    private float _accumulator;
    private float _sendAccumulator;
    private float _timeSyncTimer;
    private uint _localTick;

    // 网络时间偏移
    private float _serverTimeOffset;
    private float _estimatedRtt;

    // 输入缓冲区
    private InputBuffer _inputBuffer = new InputBuffer();
    // 接收缓冲区
    private ReceiveBuffer _receiveBuffer = new ReceiveBuffer();

    void Awake()
    {
        _logicDt = 1.0f / _logicTickRate;
        _networkSendDt = 1.0f / _networkSendRate;

        // 禁用自动物理，改为手动控制
        Physics.autoSimulation = false;

        // 固定时间步长设为与逻辑Tick相同（或整数倍）
        Time.fixedDeltaTime = _logicDt;
    }

    void Update()
    {
        float dt = Time.deltaTime;
        _accumulator += dt;
        _sendAccumulator += dt;
        _timeSyncTimer += dt;

        // === 逻辑Tick（固定步长，追赶模式）===
        int ticksExecuted = 0;
        while (_accumulator >= _logicDt && ticksExecuted < _maxCatchupTicks)
        {
            _accumulator -= _logicDt;
            ExecuteLogicTick(_localTick);
            _localTick++;
            ticksExecuted++;
        }

        if (_accumulator >= _logicDt)
        {
            // 追赶不完 → 丢弃累积时间，防止螺旋
            _accumulator = 0f;
            Debug.LogWarning("[TickManager] Frame catchup limit reached — discarding accumulated time");
        }

        // === 网络发送Tick（独立频率）===
        while (_sendAccumulator >= _networkSendDt)
        {
            _sendAccumulator -= _networkSendDt;
            FlushOutgoingCommands();
        }

        // === 渲染插值 ===
        float renderAlpha = _accumulator / _logicDt;
        InterpolateForRendering(renderAlpha);

        // === 时间同步 ===
        if (_timeSyncTimer >= _timeSyncInterval)
        {
            _timeSyncTimer -= _timeSyncInterval;
            SendTimeSyncRequest();
        }
    }

    // === 逻辑Tick执行 ===
    void ExecuteLogicTick(uint tickNumber)
    {
        // 1. 采集本帧输入
        byte[] input = CaptureLocalInput(tickNumber);
        _inputBuffer.WriteInput(tickNumber, input);

        // 2. 处理从服务器收到的包（按序消费）
        while (_receiveBuffer.TryConsume(out uint frameNo, out byte[] data))
        {
            ProcessServerPacket(frameNo, data);
        }

        // 3. 执行本地预测逻辑（状态同步）
        // 或执行确定性逻辑（帧同步）
        RunLocalGameLogic(_logicDt);
    }

    // === 本地输入采集 ===
    byte[] CaptureLocalInput(uint tickNumber)
    {
        // 编码为简单的位标志
        byte flags = 0;
        if (Input.GetKey(KeyCode.W))      flags |= 0x01; // 前进
        if (Input.GetKey(KeyCode.S))      flags |= 0x02; // 后退
        if (Input.GetKey(KeyCode.A))      flags |= 0x04; // 左移
        if (Input.GetKey(KeyCode.D))      flags |= 0x08; // 右移
        if (Input.GetKey(KeyCode.Space))  flags |= 0x10; // 跳跃
        if (Input.GetMouseButton(0))      flags |= 0x20; // 攻击

        // 返回编码后的字节
        // 实际项目中会用 BitWriter 或 protobuf
        return new byte[] { flags };
    }

    // === 网络命令发送（含冗余）===
    void FlushOutgoingCommands()
    {
        var sendBuffer = new CommandSendBuffer();

        // 取最近3帧的输入做冗余发送（帧同步常用策略）
        // 冗余策略：每帧包含最近N帧的指令
        // 丢包时，可以通过后续包的冗余数据补回
        uint startFrame = _localTick > 3 ? _localTick - 3 : 0;
        for (uint f = startFrame; f < _localTick; f++)
        {
            if (_inputBuffer.TryReadInput(f, out byte[] cmd))
            {
                if (!sendBuffer.TryAddCommand(f, 0x01 /*INPUT*/, cmd))
                    break;
            }
        }

        byte[] packet = sendBuffer.Flush();
        if (packet != null)
        {
            // 实际发送（UDP socket）
            NetworkTransport.Send(packet);
        }
    }

    // === 渲染插值 ===
    void InterpolateForRendering(float alpha)
    {
        // alpha ∈ [0, 1)：当前渲染时间在两个逻辑帧之间的位置
        // 用于平滑角色位置、动画等
        // 例如：renderPos = Lerp(prevLogicPos, nextLogicPos, alpha)
    }

    // === 时间同步 ===
    void SendTimeSyncRequest()
    {
        var request = new TimeSyncRequest
        {
            ClientSendTimestamp = Time.realtimeSinceStartup
        };
        NetworkTransport.Send(SerializeTimeSyncRequest(request));
    }

    public void OnTimeSyncResponse(TimeSyncResponse response)
    {
        float clientRecvTime = Time.realtimeSinceStartup;
        // 计算 RTT（扣除服务器处理时间）
        float rtt = (clientRecvTime - response.ClientSendTimestamp)
                    - (response.ServerRecvTimestamp - response.ServerSendTimestamp);

        // 简单指数平滑更新 offset（生产环境应使用采样+中位数滤波）
        float estimatedServerTime = response.ServerSendTimestamp;
        float newOffset = estimatedServerTime - (clientRecvTime - rtt / 2f);

        _serverTimeOffset = Mathf.Lerp(_serverTimeOffset, newOffset, 0.1f);
        _estimatedRtt = Mathf.Lerp(_estimatedRtt, rtt, 0.2f);
    }

    public float GetServerTime() => Time.realtimeSinceStartup + _serverTimeOffset;
    public float GetEstimatedRtt() => _estimatedRtt;
    public uint GetCurrentTick() => _localTick;

    // === 辅助方法（简化）===
    void ProcessServerPacket(uint frameNo, byte[] data) { /* 解析并应用服务器状态 */ }
    void RunLocalGameLogic(float dt) { /* 具体游戏逻辑 */ }
    void RunLocalPhysics(float dt) { Physics.Simulate(dt); }

    // === 数据结构 ===
    [Serializable]
    struct TimeSyncRequest
    {
        public float ClientSendTimestamp;
    }

    [Serializable]
    struct TimeSyncResponse
    {
        public float ClientSendTimestamp;
        public float ServerRecvTimestamp;
        public float ServerSendTimestamp;
    }
}
```

**设置说明**：
1. 将脚本挂载到场景中的空 GameObject（如 `NetworkManager`）
2. `_logicTickRate` 设为与服务器一致的频率
3. 网络发送频率可与逻辑Tick不同，节省上行带宽
4. 确保 `NetworkTransport` 替换为实际使用的传输层

### 2.2 Unreal: FTickFunction / UNetDriver Tick Flow

```cpp
// NetworkTickSubsystem.h
// UE 网络Tick子系统 — 管理独立的逻辑/网络Tick周期

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "NetworkTickSubsystem.generated.h"

// 逻辑Tick函数：在GameThread上以固定速率运行
USTRUCT()
struct FLogicTickFunction : public FTickFunction
{
    GENERATED_BODY()

    float LogicTickRate = 30.0f;  // 30Hz
    float AccumulatedTime = 0.0f;
    int32 MaxCatchupTicks = 5;

    virtual void ExecuteTick(
        float DeltaTime,
        ELevelTick TickType,
        ENamedThreads::Type CurrentThread,
        const FGraphEventRef& MyCompletionGraphEvent) override;

    // 返回固定步长
    float GetLogicDeltaTime() const { return 1.0f / LogicTickRate; }

    // TickFunction 的接口要求
    virtual FString DiagnosticMessage() override
    {
        return FString::Printf(TEXT("FLogicTickFunction[%gHz]"), LogicTickRate);
    }

    virtual FName DiagnosticContext(bool bDetailed) override
    {
        return FName(TEXT("LogicTick"));
    }
};

// 网络发送Tick函数
USTRUCT()
struct FNetworkSendTickFunction : public FTickFunction
{
    GENERATED_BODY()

    float SendRate = 20.0f;
    float AccumulatedTime = 0.0f;

    virtual void ExecuteTick(
        float DeltaTime,
        ELevelTick TickType,
        ENamedThreads::Type CurrentThread,
        const FGraphEventRef& MyCompletionGraphEvent) override;

    virtual FString DiagnosticMessage() override
    {
        return FString::Printf(TEXT("FNetworkSendTick[%gHz]"), SendRate);
    }
    virtual FName DiagnosticContext(bool bDetailed) override
    {
        return FName(TEXT("NetworkSend"));
    }
};

// Tick管理子系统
UCLASS()
class UNetworkTickSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    // FTickableGameObject 接口
    virtual void Tick(float DeltaTime) override;
    virtual TStatId GetStatId() const override
    {
        RETURN_QUICK_DECLARE_CYCLE_STAT(UNetworkTickSubsystem, STATGROUP_Tickables);
    }
    virtual bool IsTickable() const { return bIsActive; }

    // 时间同步
    void SendTimeSyncRequest();
    void OnTimeSyncResponse(float ClientSendTime, float ServerRecvTime,
                             float ServerSendTime);
    float GetEstimatedServerTime() const;
    float GetEstimatedRTT() const { return SmoothedRTT; }

    // Tick控制
    uint32 GetCurrentLogicTick() const { return CurrentTick; }
    float GetTickAlpha() const { return Accumulator / (1.0f / LogicTickRate); }

private:
    FLogicTickFunction LogicTick;
    FNetworkSendTickFunction NetworkSendTick;

    float LogicTickRate = 30.0f;
    float NetworkSendRate = 20.0f;
    float Accumulator = 0.0f;
    uint32 CurrentTick = 0;
    int32 MaxCatchupTicks = 5;
    bool bIsActive = true;

    // 时间同步
    float ServerTimeOffset = 0.0f;
    float SmoothedRTT = 0.0f;
    float TimeSyncTimer = 0.0f;
    float TimeSyncInterval = 5.0f;

    // 缓冲
    TMap<uint32, TArray<uint8>> InputBuffer;
    TMap<uint32, TArray<uint8>> ReceiveBuffer;
    uint32 ExpectedReceiveFrame = 0;

    void ExecuteLogicTick(uint32 TickNumber);
    void FlushOutgoingCommands();
    TArray<uint8> CaptureLocalInput(uint32 TickNumber);
};

// === 实现文件 NetworkTickSubsystem.cpp ===

#include "NetworkTickSubsystem.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

void UNetworkTickSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    // 在Tick系统中注册我们的Tick函数
    LogicTick.TickGroup = TG_PrePhysics;  // 在物理之前运行逻辑
    LogicTick.bCanEverTick = true;
    LogicTick.bStartWithTickEnabled = true;

    NetworkSendTick.TickGroup = TG_DuringPhysics; // 与物理并行
    NetworkSendTick.bCanEverTick = true;
    NetworkSendTick.bStartWithTickEnabled = true;

    // 实际注册到 Level 的 Tick 系统
    if (UWorld* World = GetWorld())
    {
        LogicTick.RegisterTickFunction(World->PersistentLevel);
        NetworkSendTick.RegisterTickFunction(World->PersistentLevel);
    }
}

void UNetworkTickSubsystem::Tick(float DeltaTime)
{
    // === 逻辑Tick（固定步长追赶）===
    Accumulator += DeltaTime;
    int32 TicksExecuted = 0;
    float LogicDt = 1.0f / LogicTickRate;

    while (Accumulator >= LogicDt && TicksExecuted < MaxCatchupTicks)
    {
        Accumulator -= LogicDt;
        ExecuteLogicTick(CurrentTick);
        CurrentTick++;
        TicksExecuted++;
    }

    if (Accumulator >= LogicDt)
    {
        Accumulator = 0.0f; // 防止螺旋
    }

    // === 网络发送 ===
    // 由 FNetworkSendTickFunction::ExecuteTick 独立驱动

    // === 时间同步 ===
    TimeSyncTimer += DeltaTime;
    if (TimeSyncTimer >= TimeSyncInterval)
    {
        TimeSyncTimer -= TimeSyncInterval;
        SendTimeSyncRequest();
    }
}

void UNetworkTickSubsystem::ExecuteLogicTick(uint32 TickNumber)
{
    // 1. 采集输入
    TArray<uint8> Input = CaptureLocalInput(TickNumber);
    InputBuffer.Add(TickNumber, Input);

    // 2. 处理收到的包
    // (在状态同步中，这里应用服务器发来的权威状态)
    while (ReceiveBuffer.Contains(ExpectedReceiveFrame))
    {
        const TArray<uint8>& Data = ReceiveBuffer[ExpectedReceiveFrame];
        // ProcessServerPacket(ExpectedReceiveFrame, Data);
        ReceiveBuffer.Remove(ExpectedReceiveFrame);
        ExpectedReceiveFrame++;
    }

    // 3. 本地逻辑更新
    // RunLocalGameLogic(LogicDt);
}

TArray<uint8> UNetworkTickSubsystem::CaptureLocalInput(uint32 TickNumber)
{
    TArray<uint8> Cmd;
    // 编码玩家输入
    Cmd.Add(0); // Placeholder — 实际编码输入标志位

    // 示例：获取本地 PlayerController 的输入
    if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
    {
        // 读取 EnhancedInput 或传统 Axis/Action 值
        // 编码到字节数组
    }

    return Cmd;
}

void UNetworkTickSubsystem::FlushOutgoingCommands()
{
    // 将缓冲区中的指令打包发送
    // 帧同步常用的冗余策略：每包包含最近 3 帧的指令
    const uint32 RedundancyFrames = 3;
    TArray<uint8> Packet;

    for (uint32 F = CurrentTick > RedundancyFrames ? CurrentTick - RedundancyFrames : 0;
         F < CurrentTick; ++F)
    {
        if (TArray<uint8>* Cmd = InputBuffer.Find(F))
        {
            // 序列化到 Packet
            // FMemoryWriter + FBitWriter 用于 bit-level 序列化
        }
    }

    // SendPacket(Packet);
}

void UNetworkTickSubsystem::SendTimeSyncRequest()
{
    // 发送时间同步请求到服务器
    // float ClientSendTime = FPlatformTime::Seconds();
    // 构造请求包并通过 UNetDriver 或自定义 Socket 发送
}

void UNetworkTickSubsystem::OnTimeSyncResponse(
    float ClientSendTime, float ServerRecvTime, float ServerSendTime)
{
    float ClientRecvTime = FPlatformTime::Seconds();
    float RTT = (ClientRecvTime - ClientSendTime)
              - (ServerSendTime - ServerRecvTime);

    // 指数平滑
    SmoothedRTT = FMath::Lerp(SmoothedRTT, RTT, 0.2f);

    float EstimatedServerTime = ServerSendTime;
    float NewOffset = EstimatedServerTime - (ClientRecvTime - RTT / 2.0f);
    ServerTimeOffset = FMath::Lerp(ServerTimeOffset, NewOffset, 0.1f);
}

float UNetworkTickSubsystem::GetEstimatedServerTime() const
{
    return FPlatformTime::Seconds() + ServerTimeOffset;
}

// UE Tick系统中 UNetDriver 的 Tick 流程（分析用）
// UE 的网络Tick内建于 UNetDriver::TickDispatch / TickFlush
//
// UWorld::Tick()
//   ├─ UNetDriver::TickDispatch(DeltaTime)
//   │    └─ 接收并分发网络包到各个 UChannel / UActorChannel
//   │    └─ 更新 Actor Replication（处理收到的属性复制）
//   │
//   ├─ [Gameplay Ticks: PrePhysics, DuringPhysics, PostPhysics]
//   │    └─ AActor::Tick(), UActorComponent::TickComponent()
//   │    └─ 物理模拟
//   │
//   └─ UNetDriver::TickFlush(DeltaTime)
//        └─ 将脏属性写入发送缓冲区
//        └─ 通过 UDP Socket 发送
//
// 在 Iris (UE5) 中，流程改进为:
//   NetUpdateFrequency 控制 Actor 的复制频率
//   Iris 内部有自己的优先级调度和带宽管理
```

### 2.3 Lua: 游戏主循环实现（Timer-Driven）

```lua
-- =============================================================================
-- TickManager.lua — 纯Lua游戏主循环 + 网络Tick集成
-- 适用场景：基于 Skynet/Custom C Engine 的帧同步或状态同步客户端/服务器
-- =============================================================================

---@class TickManager
---@field private _logicTickRate   number   逻辑帧频率 (Hz)
---@field private _sendTickRate    number   网络发送频率 (Hz)
---@field private _maxCatchup      number   一帧最多追赶次数
---@field private _accumulator     number   时间累积器
---@field private _sendAccumulator number   发送累积器
---@field private _currentTick     integer  当前逻辑帧号
---@field private _running         boolean  是否在运行
---@field private _inputBuffer     table    输入缓冲区 {[frameNo] = cmdData}
---@field private _recvBuffer      table    接收缓冲区（按帧号排序）
---@field private _recvList        table    接收帧号列表（有序）
---@field private _clockOffset     number   服务器时钟偏移
---@field private _estimatedRtt    number   估计的往返延迟
local TickManager = {}

-- 构造函数
---@param logicTickRate number 逻辑帧频率
---@param sendTickRate  number 网络发送频率
---@return TickManager
function TickManager.new(logicTickRate, sendTickRate)
    logicTickRate = logicTickRate or 30
    sendTickRate  = sendTickRate or 20

    local self = {
        _logicTickRate   = logicTickRate,
        _sendTickRate    = sendTickRate,
        _logicDt         = 1.0 / logicTickRate,
        _sendDt          = 1.0 / sendTickRate,
        _maxCatchup      = 5,
        _accumulator     = 0.0,
        _sendAccumulator = 0.0,
        _currentTick     = 0,
        _running         = false,
        _inputBuffer     = {},
        _recvBuffer      = {},
        _recvList        = {},   -- 保持有序以便按序消费
        _clockOffset     = 0.0,
        _estimatedRtt    = 0.0,
        _timeSyncTimer   = 0.0,
        _timeSyncInterval = 5.0, -- 每5秒同步一次时间
    }
    setmetatable(self, { __index = TickManager })
    return self
end

-- =============================================================================
-- 主循环：每帧调用一次（由引擎的 Update 回调驱动）
-- @param dt number 距上一帧的时间（秒）
-- =============================================================================
function TickManager:onUpdate(dt)
    if not self._running then return end

    -- === 时间同步（定期发送 NTP 请求）===
    self._timeSyncTimer = self._timeSyncTimer + dt
    if self._timeSyncTimer >= self._timeSyncInterval then
        self._timeSyncTimer = self._timeSyncTimer - self._timeSyncInterval
        self:_sendTimeSyncRequest()
    end

    -- === 逻辑Tick（固定步长，追赶模式）===
    self._accumulator = self._accumulator + dt
    local ticksExecuted = 0
    while self._accumulator >= self._logicDt and ticksExecuted < self._maxCatchup do
        self._accumulator = self._accumulator - self._logicDt
        self:_executeLogicTick(self._currentTick)
        self._currentTick = self._currentTick + 1
        ticksExecuted = ticksExecuted + 1
    end

    -- 超过追赶上限 → 丢弃剩余时间防止螺旋
    if self._accumulator >= self._logicDt then
        self._accumulator = 0.0
    end

    -- === 网络发送Tick（独立频率）===
    self._sendAccumulator = self._sendAccumulator + dt
    while self._sendAccumulator >= self._sendDt do
        self._sendAccumulator = self._sendAccumulator - self._sendDt
        self:_flushOutgoingCommands()
    end

    -- === 渲染插值：计算 alpha ===
    local alpha = self._accumulator / self._logicDt
    -- alpha 用于在两个逻辑帧状态之间插值渲染
    self:_interpolateForRender(alpha)
end

-- =============================================================================
-- 启动主循环
-- =============================================================================
function TickManager:start()
    self._running = true
    self._accumulator = 0.0
    self._sendAccumulator = 0.0
    self._currentTick = 0
    print("[TickManager] Started at logic=" .. self._logicTickRate
          .. "Hz send=" .. self._sendTickRate .. "Hz")
end

-- 停止主循环
function TickManager:stop()
    self._running = false
    print("[TickManager] Stopped at tick=" .. self._currentTick)
end

-- =============================================================================
-- 单次逻辑帧执行
-- @param tickNumber integer 帧号
-- =============================================================================
function TickManager:_executeLogicTick(tickNumber)
    -- 1. 采集本地输入
    local cmd = self:_captureLocalInput(tickNumber)
    if cmd then
        self._inputBuffer[tickNumber] = cmd
    end

    -- 2. 按序消费收到的网络包
    while #self._recvList > 0 and self._recvList[1] <= tickNumber do
        local frameNo = table.remove(self._recvList, 1)
        local data = self._recvBuffer[frameNo]
        self._recvBuffer[frameNo] = nil
        if data then
            self:_processServerPacket(frameNo, data)
        end
    end

    -- 3. 执行本地游戏逻辑（确定性逻辑 或 客户端预测）
    self:_runLocalGameLogic(self._logicDt)

    -- 4. 清理旧输入（防止内存无限增长）
    if tickNumber > 60 then
        self._inputBuffer[tickNumber - 60] = nil
    end
end

-- =============================================================================
-- 采集本地输入 → 编码为紧凑字节
-- @param tickNumber integer
-- @return table|nil 编码后的输入数据
-- =============================================================================
function TickManager:_captureLocalInput(tickNumber)
    -- 实际项目中应调用引擎输入 API（如 Unity 的 Input.GetKey）
    -- 这里用伪代码展示逻辑
    local flags = 0
    -- if Input.GetKey("W")      then flags = flags | 0x01 end  -- 前进
    -- if Input.GetKey("S")      then flags = flags | 0x02 end  -- 后退
    -- if Input.GetKey("A")      then flags = flags | 0x04 end  -- 左移
    -- if Input.GetKey("D")      then flags = flags | 0x08 end  -- 右移
    -- if Input.GetKey("Space")  then flags = flags | 0x10 end  -- 跳跃
    -- if Input.GetMouseButton(0)then flags = flags | 0x20 end  -- 攻击

    -- 如果 flags 为 0 且上一帧也没有输入，可以跳过发送（省带宽）
    -- 但帧同步中需要发送"空输入"以避免卡帧
    return { flags = flags, tick = tickNumber }
end

-- =============================================================================
-- 输出命令刷新：将缓冲区中的指令打包发送
-- 帧同步常用冗余策略：每包包含最近 3 帧的指令
-- =============================================================================
function TickManager:_flushOutgoingCommands()
    local packet = {}
    local cmdCount = 0
    local MAX_CMDS = 10
    local MAX_SIZE = 1200

    -- 冗余发送最近 3 帧（帧同步常用防丢包策略）
    local startFrame = math.max(0, self._currentTick - 3)
    for frameNo = startFrame, self._currentTick - 1 do
        local cmd = self._inputBuffer[frameNo]
        if cmd ~= nil then
            -- 编码一条指令的预估大小
            -- 实际应使用 protobuf 或自定义 varint 编码
            table.insert(packet, cmd)
            cmdCount = cmdCount + 1
            if cmdCount >= MAX_CMDS then break end
        end
    end

    if cmdCount > 0 then
        -- 序列化并发送
        -- local bytes = protobuf.encode("InputPacket", { commands = packet })
        -- NetworkTransport.send(bytes)
    end
end

-- =============================================================================
-- 收到网络包 → 插入接收缓冲区
-- @param frameNo integer 服务器指定的帧号
-- @param data    table   反序列化后的包数据
-- =============================================================================
function TickManager:onReceivePacket(frameNo, data)
    -- 拒绝过期包
    if frameNo < self._currentTick then
        return
    end

    -- 插入缓冲区
    self._recvBuffer[frameNo] = data

    -- 维护有序列表（用于按序消费）
    local inserted = false
    for i, fn in ipairs(self._recvList) do
        if fn > frameNo then
            table.insert(self._recvList, i, frameNo)
            inserted = true
            break
        elseif fn == frameNo then
            inserted = true -- 避免重复插入
            break
        end
    end
    if not inserted then
        table.insert(self._recvList, frameNo)
    end
end

-- =============================================================================
-- 时间同步：发送请求
-- =============================================================================
function TickManager:_sendTimeSyncRequest()
    -- local requestTime = os.clock()  -- 高精度时间
    -- local msg = { type = "time_sync", client_time = requestTime }
    -- NetworkTransport.send(protobuf.encode("TimeSync", msg))
end

-- 时间同步：处理回复
---@param clientSendTime  number 客户端发送时的时间戳
---@param serverRecvTime  number 服务端收到请求的时间戳
---@param serverSendTime  number 服务端发送回复的时间戳
function TickManager:onTimeSyncResponse(clientSendTime, serverRecvTime, serverSendTime)
    local clientRecvTime = os.clock()

    -- 计算 RTT（扣除服务器处理时间）
    local rtt = (clientRecvTime - clientSendTime)
              - (serverSendTime - serverRecvTime)

    -- 估计服务器时间
    local estimatedServerTime = serverSendTime
    local newOffset = estimatedServerTime - (clientRecvTime - rtt / 2.0)

    -- 指数平滑
    self._clockOffset  = self._clockOffset * 0.9 + newOffset * 0.1
    self._estimatedRtt = self._estimatedRtt * 0.8 + rtt * 0.2
end

-- 获取估计的服务器时间
---@return number
function TickManager:getServerTime()
    return os.clock() + self._clockOffset
end

-- =============================================================================
-- 回调占位（项目应替换为实际逻辑）
-- =============================================================================
function TickManager:_processServerPacket(frameNo, data)
    -- 实现：应用服务器权威状态 / 执行服务端帧指令
end

function TickManager:_runLocalGameLogic(dt)
    -- 实现：确定性逻辑更新 / 客户端预测
end

function TickManager:_interpolateForRender(alpha)
    -- 实现：在两个逻辑帧状态间插值
end

-- =============================================================================
-- 对外接口
-- =============================================================================
return TickManager
```

**使用示例**：

```lua
-- main.lua — 在引擎 Update 回调中使用 TickManager
local TickManager = require("TickManager")

-- 创建：逻辑 30Hz，网络发送 20Hz
local tickMgr = TickManager.new(30, 20)
tickMgr:start()

-- 伪代码：引擎每渲染帧调用
function onEngineUpdate(deltaTime)
    tickMgr:onUpdate(deltaTime)
end

-- 伪代码：网络层收到包时调用
function onNetworkPacketReceived(frameNo, data)
    tickMgr:onReceivePacket(frameNo, data)
end

-- 伪代码：时间同步回复到达
function onTimeSyncResponse(reqTime, srvRecvTime, srvSendTime)
    tickMgr:onTimeSyncResponse(reqTime, srvRecvTime, srvSendTime)
end
```

---

## 3. 练习

### 练习 1: 基础 — 实现固定步长逻辑帧（15min）

**目标**：用你熟悉的语言（C#/C++/Lua）实现一个简单的固定步长游戏循环，支持追赶机制和渲染插值。

**要求**：
1. 逻辑帧固定 30Hz（33.33ms 步长）
2. 渲染帧随引擎（模拟 60fps，即 ~16.67ms 一帧）
3. 每帧最多追赶 4 个逻辑帧
4. 计算并输出每帧的 `alpha` 值（用于渲染插值）
5. 模拟一帧掉帧场景：第 10 帧的 dt = 80ms（正常 16ms），观察追赶行为

**验收标准**：
- 累计逻辑时间与渲染时间误差不超过 ±1 个逻辑帧步长
- 掉帧场景下能输出正确的追赶次数（4 次）并输出 warning
- alpha 值始终在 [0, 1) 范围内

**伪代码框架**：

```
accumulator = 0
MAX_CATCHUP = 4
LOGIC_DT = 1/30

每渲染帧(dt):
    accumulator += dt
    ticks = 0
    while accumulator >= LOGIC_DT and ticks < MAX_CATCHUP:
        accumulator -= LOGIC_DT
        executeLogicTick()
        ticks += 1
    if accumulator >= LOGIC_DT:
        accumulator = 0  # 丢弃，防螺旋
        print("WARNING: frame catchup limit reached")
    alpha = accumulator / LOGIC_DT
    render(alpha)
```

### 练习 2: 进阶 — Ring Buffer 输入队列（20min）

**目标**：实现一个环形缓冲区（Ring Buffer），用于管理帧同步中的输入指令存储。

**要求**：
1. 缓冲区容量 64 帧
2. 支持 `WriteInput(frameNo, data)` — O(1) 写入
3. 支持 `TryReadInput(frameNo) → data|null` — O(1) 读取
4. 支持 `AdvanceStart(frameNo)` — 清理已消费帧
5. 帧号超出容量时拒绝写入（不扩展/扩容）
6. 帧号回绕（wraparound）正确处理（uint32 溢出）

**验收标准**：

| 测试用例 | 输入 | 期望输出 |
|----------|------|----------|
| 正常写入读取 | Write(5, "A"), Read(5) | "A" |
| 读取未写入帧 | Read(10) | null |
| 清理后读取 | Write(5, "A"), AdvanceStart(6), Read(5) | null |
| 容量边界 | Write(0..63), Write(64) | 64 被拒绝（超出容量） |
| 帧号回绕 | Write(0xFFFFFFFF, "X"), Write(0, "Y"), Read(0xFFFFFFFF) | null（已被覆盖） |

**提示**：环形缓冲区用 `frameNo % BUFFER_SIZE` 索引。需要 `_bufferStart` 指针追踪有效范围。

### 练习 3: 挑战 — 手动时间同步采样与滤波（25min）

**目标**：实现一个鲁棒的网络时间同步器，能处理网络抖动。

**要求**：
1. 模拟网络环境：生成随机 RTT（均值 50ms，标准差 20ms 的正态分布）
2. 每 5 秒发送一次时间同步请求
3. 收集 8 个最新采样
4. 实现两种滤波策略并对比：
   - **策略 A**：取所有采样 offset 的算术平均值
   - **策略 B**：按 RTT 升序排列，取 RTT 最小的一半采样的 offset 平均值
5. 以"真实 offset = 100ms"为基准，对比两种策略的误差

**模拟框架**：

```python
import random
import math

TRUE_OFFSET = 100.0  # 真实时钟偏移 (ms)
MEAN_RTT = 50.0      # 平均 RTT (ms)
STD_RTT = 20.0       # RTT 标准差 (ms)

def simulate_one_sample():
    """模拟一次时间同步采样"""
    rtt = max(1, random.gauss(MEAN_RTT, STD_RTT))
    # 偏移的误差主要来源于 RTT/2 的估计
    noise = random.gauss(0, rtt / 4)  # 模拟非对称延迟噪声
    observed_offset = TRUE_OFFSET + noise
    return rtt, observed_offset

# 收集 8 个样本并对比两种策略
samples = [simulate_one_sample() for _ in range(8)]

# 策略 A: 算术平均
avg_offset = sum(o for _, o in samples) / len(samples)

# 策略 B: 取 RTT 最小的一半样本
sorted_samples = sorted(samples, key=lambda x: x[0])
half = max(1, len(sorted_samples) // 2)
best_offset = sum(o for _, o in sorted_samples[:half]) / half

print(f"真实偏移: {TRUE_OFFSET}ms")
print(f"策略A (平均): {avg_offset:.2f}ms, 误差: {abs(avg_offset - TRUE_OFFSET):.2f}ms")
print(f"策略B (最小RTT): {best_offset:.2f}ms, 误差: {abs(best_offset - TRUE_OFFSET):.2f}ms")
```

**验收标准**：
- 策略 B 的误差在 80% 的情况下小于或等于策略 A
- 能解释为什么策略 B 更好（RTT 越小 → 网络越对称 → offset 估算越准）

---

## 4. 扩展阅读

| 资源 | 描述 |
|------|------|
| [Gaffer On Games: Fix Your Timestep!](https://gafferongames.com/post/fix_your_timestep/) | 游戏循环定步长经典文章，帧同步和状态同步的循环基础 |
| [Gabriel Gambetta: Client-Server Game Architecture](https://www.gabrielgambetta.com/client-server-game-architecture.html) | 状态同步的客户端-服务器架构，含 Tick 策略 |
| [Overwatch GDC: Gameplay Architecture and Netcode](https://www.gdcvault.com/play/1024001/) | Overwatch 如何实现 60Hz Tick + 客户端预测 + 回滚 |
| [Riot: Peeking into VALORANT's Netcode](https://technology.riotgames.com/news/peeking-valorants-netcode) | VALORANT 128-tick 服务器 + 客户端预测的时间同步细节 |
| [Valve: Source Multiplayer Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) | Source 引擎的 Tick 系统 + lag compensation |
| [NTP RFC 5905](https://datatracker.ietf.org/doc/html/rfc5905) | NTP 协议标准，时间同步的理论基础 |
| [腾讯: 帧同步游戏开发基础指南](https://developer.cloud.tencent.com/article/1050868) | 帧同步 Tick 机制的中文详解 |
| [GAMES104: 网络游戏的架构基础 (B站)](https://www.bilibili.com/video/BV1La411o7kG) | 游戏引擎课程中的网络章节，含 Tick 设计 |

---

## 常见陷阱

### 1. FixedUpdate 与游戏逻辑混用

```csharp
// 错误：在 FixedUpdate 中既做物理又做网络逻辑
void FixedUpdate() {
    ProcessNetworkPackets(); // ❌ FixedUpdate 可能一帧执行多次
    UpdateGameLogic();       //    网络包被重复处理
}
// 修正：网络逻辑放 Update，物理逻辑放 FixedUpdate
void Update() {
    ProcessNetworkPackets(); // ✅ 每渲染帧只处理一次
}
void FixedUpdate() {
    Physics.Simulate(Time.fixedDeltaTime); // ✅ 只在物理Tick执行
}
```

### 2. 未限速的追赶导致 Death Spiral

当渲染帧率低于逻辑帧率时（如渲染 10fps，逻辑 60Hz），一帧需要追赶 6 个逻辑帧。如果每个逻辑帧的计算量本身就重，追赶会导致单帧耗时更长 → 渲染帧率更低 → 需要追赶更多帧 → 恶性循环。

**解决方案**：设置 `maxCatchupTicks` 上限（如 4-5），超出则丢弃累积时间。

### 3. 用 `Time.deltaTime` 驱动网络 Tick

```csharp
// 错误：网络Tick用可变 deltaTime
void Update() {
    SendNetworkUpdate(Time.deltaTime); // ❌ dt 变化导致发包频率不稳定
}
// 修正：用固定累积器
void Update() {
    _sendAccumulator += Time.deltaTime;
    while (_sendAccumulator >= _fixedSendInterval) {
        _sendAccumulator -= _fixedSendInterval;
        SendNetworkUpdate();
    }
}
```

### 4. 时间同步只采样一次就信任

网络抖动可能使单次采样的误差高达 50ms+。必须在数秒内收集多个采样，做滤波后再使用。正确的做法是：**取 RTT 最小的 N 个样本的 offset 中位数/均值**。

### 5. 服务器时间偏移直接跳变

```csharp
// 错误：直接赋值
_serverTimeOffset = newOffset; // ❌ 突然跳变导致画面瞬移/卡顿

// 修正：平滑过渡
_serverTimeOffset = Mathf.Lerp(_serverTimeOffset, newOffset, 0.1f);
// 或使用更保守的策略：只有新采样 RTT < 当前最小RTT 时才更新
```

### 6. 输入缓冲区无限增长

如果不清理已消费的输入，内存会持续增长——尤其是高 Tick 率（128Hz）下，每秒产生 128 条记录。

```csharp
// 每帧清理过期输入
_inputBuffer.RemoveWhere(kvp => kvp.Key < _currentTick - 300); // 保留最近 300 帧
```

### 7. 忽略物理引擎的自动模拟

如果你在 Unity 中手动调用 `Physics.Simulate()`，必须设置 `Physics.autoSimulation = false`。否则 Unity 会自动在 FixedUpdate 期间模拟物理，导致"双倍物理"——每帧物理跑两次。

### 8. 网络包处理顺序错误

UDP 天然无序。直接 `foreach` 遍历收到的包而不按帧号排序，会导致"先收到帧 5 的状态，后收到帧 3 的状态"——帧 3 的旧状态覆盖了帧 5 的新状态。

```csharp
// 错误
foreach (var packet in receivedPackets) {
    ApplyState(packet); // ❌ 不保证顺序！
}
// 修正
var sortedPackets = receivedPackets.OrderBy(p => p.FrameNumber);
foreach (var packet in sortedPackets) {
    if (packet.FrameNumber >= _lastAppliedFrame) {
        ApplyState(packet);
        _lastAppliedFrame = packet.FrameNumber;
    }
}
```
