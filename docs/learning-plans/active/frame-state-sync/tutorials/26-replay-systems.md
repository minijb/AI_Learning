# 录像与战斗回放系统

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [12-帧同步进阶](12-lockstep-advanced.md), [25-混合同步进阶](25-hybrid-sync-advanced.md)

---

## 1. 概念讲解

### 1.1 为什么需要录像系统？

假设你刚打完一局《王者荣耀》，被对面打野抓了 8 次。你想知道问题出在哪——是自己清线过于激进？还是对面视野做得太好？还是纯粹队友不支援？

你需要**回放**这局比赛的每一个瞬间。

录像系统在这里不是锦上添花的功能，而是游戏的基础设施。它支撑的场景至少包括：

- **玩家复盘**：死了看回放，分析为什么输
- **反外挂**：检测异常操作序列（0.1ms 内完成 5 个不可能连续的操作？）
- **Desync 诊断**：比对不同客户端的录像，定位不同步的确切帧
- **精彩集锦**：自动或手动生成击杀集锦、高光时刻
- **电竞赛事**：裁判复核争议判决（比如谁先动手、技能是否命中）
- **AI 训练数据**：从海量录像中提取人类玩家的决策序列，训练 AI

最关键的问题是：**录像文件要多大？**

一场 30 分钟、10 人对战的《王者荣耀》——如果逐帧录制视频，1080p@30fps 大约是 **3~5GB**。如果只存操作指令序列呢？大约 **100KB**。这是 **30000:1** 的压缩比。

这个魔术是怎么变的？答案在帧同步的核心原理里：**相同输入 → 相同输出**。录像只需要存储"输入"，回放时重新执行逻辑即可重建整个对局。

### 1.2 三种录像模式对比

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          录像系统三大模式                                   │
├───────────────┬──────────────────────┬──────────────────────┬─────────────┤
│   指令录像     │     快照录像           │     混合录像           │ 指令+关键帧  │
│ (帧同步录像)    │ (状态同步录像)         │                      │              │
├───────────────┼──────────────────────┼──────────────────────┼─────────────┤
│ 原理: 存输入序列│ 原理: 定期存状态快照    │ 原理: 指令 + 快照双存  │              │
│ 大小: 极小     │ 大小: 较大             │ 大小: 中等            │              │
│ 依赖: 确定性逻辑 │ 依赖: 无（可直接查看）  │ 依赖: 确定性 + 快照定位│              │
│ 快进: 需重算    │ 快进: 瞬间跳转          │ 快进: 跳转到最近快照   │              │
│ 代表: 王者/星际  │ 代表: 守望/CS:GO       │ 代表: 合金弹头觉醒     │              │
└───────────────┴──────────────────────┴──────────────────────┴─────────────┘
```

#### 1.2.1 帧同步录像（指令录像）

帧同步录像只存储**初始状态 + 每一帧的玩家输入**。原理在教程 12 已经铺垫过：

> 确定性保证：相同的初始状态 S₀ + 相同的输入序列 [I₁, I₂, …, Iₙ] + 相同的逻辑代码 → 相同的最终状态 Sₙ。

一场 30 分钟的 MOBA（15Hz 逻辑帧）：
- 总帧数：30 × 60 × 15 = 27,000 帧
- 每帧输入大小：10 个玩家 × 约 4 字节指令 = 40 字节/帧
- 总指令数据：27,000 × 40 ≈ 1.08 MB（未压缩）
- 实际大小：Deflate/LZ4 压缩后通常 **100~500KB**

这就是为什么《魔兽争霸 3》一场 40 分钟的史诗对战，Replay 文件只有几百 KB。

**优点**：
- 极小文件，适合分享和长期存储
- 回放时可以做任意视角
- 天然支持 Demolition（重播任意片段）

**缺点**：
- 快进必须重算中间所有帧（28,000 帧的快进需要重新执行 28,000 次逻辑循环）
- 游戏版本必须完全一致——版本更新后旧录像可能无法播放
- 依赖确定性，微小差异导致灾难性漂移

#### 1.2.2 状态同步录像（快照录像）

状态同步录像定期保存**完整的世界状态快照**。不依赖确定性，但文件更大。

```
帧:   0    100  200  300  400  500  600
      │     │    │    │    │    │    │
      S₀   S₁₀₀ S₂₀₀ S₃₀₀ S₄₀₀ S₅₀₀ S₆₀₀
      ↑     ↑    ↑    ↑    ↑    ↑    ↑
    完整快照 完整快照 ... (每100帧一个快照)
```

每 100 帧存一个快照，中间的状态通过**插值**还原。

**优点**：
- 不依赖确定性——哪个版本都能播
- 快进跳帧 O(1)：直接读取目标帧最近的快照
- 可选择性记录（只录关键实体）
- 适合无确定性保证的状态同步游戏

**缺点**：
- 文件大：每个快照包含所有实体的位置/血量/状态
- 录制开销高：每 N 帧做一次全量序列化
- 帧间状态是近似的（插值），不是精确重现

#### 1.2.3 混合录像（指令 + 关键帧快照）

混合方案结合两者优势：平时存指令序列，每隔 M 帧插入一个状态快照作为"锚点"。

```
帧:  0       1000    2000    3000    4000
     │   ←指令序列→  │  ←指令序列→  │  ...
     S₀(完整快照)   S₁₀₀₀(快照)  S₂₀₀₀(快照)
```

**快进**：跳转到最近的快照，从该处开始执行指令到目标帧。
**回退**：跳转到上一个快照，从该处开始执行指令到目标帧。

这是《合金弹头觉醒》和部分现代 MOBA 使用的方案。

### 1.3 录像的核心用途

#### 1.3.1 复盘分析

玩家最常见的需求。回放系统需要支持：

- **播放/暂停/停止**：基本控制
- **调速**：0.5x / 1x / 2x / 4x / 8x
- **跳转**：拖拽进度条到任意时间点
- **自由视角**：解锁摄像机，以任意角度观察战场
- **切换视角**：切换到任意玩家的第一人称视角
- **显示信息面板**：实时显示血量、技能 CD、经济等

#### 1.3.2 反外挂

录像分析是反外挂系统的重要数据源：

```
┌─────────────────────────────────────────────────────────────┐
│                    录像反外挂检测流程                          │
├─────────────────────────────────────────────────────────────┤
│  1. 收集嫌疑对局录像                                          │
│  2. 从录像提取操作序列：[点击坐标, 按键间隔, 技能释放序列...]    │
│  3. 规则引擎检测：                                            │
│     • 操作间隔 < 人类极限（<50ms 连续精准操作）→ 脚本嫌疑       │
│     • 技能命中率异常（非指向性技能 100% 命中 100 次）→ 自瞄嫌疑 │
│     • 视野外操作（攻击了理论上不可见的目标）→ 全图挂嫌疑         │
│     • APM 异常波动（平常 80APM，团战瞬间 800APM）→ 自动脚本    │
│  4. 可疑操作序列 → 人工复核 → 封禁决策                        │
└─────────────────────────────────────────────────────────────┘
```

#### 1.3.3 Desync 诊断

这是帧同步最头疼的问题——线上不同步了，但不知道哪一帧出的问题。

**诊断流程**：

```
客户端A录像 ──→ 逐帧比对状态Hash ──→ 找到 Hash 不一致的第一帧
客户端B录像 ──→                   │
                                  ↓
                          该帧的指令序列 + 状态差异
                                  │
                                  ↓
                          本地重放该帧 → Debug → 定位原因
```

关键工具：
- **逐帧状态 Hash 日志**（在教程 12 中讲过）：每帧记录一次 Hash，录像播放时快速定位 Desync 帧
- **Diff 工具**：将两个客户端的状态 dump 做 diff，看哪些实体的哪些字段不一致
- **录制的输入确定性回放**：在一个干净的客户端上回放争议对局，验证是否能重现

---

## 2. 帧同步录像实现

### 2.1 录像文件格式

一个典型的帧同步录像文件结构：

```
┌──────────────────────────────────────────────────────────────┐
│                        录像文件结构                            │
├───────────────┬──────────────────────────────────────────────┤
│  File Header  │  魔数、版本号、格式标志                         │
│  Match Header │  游戏模式、地图ID、时长、玩家信息                │
│  Seed Data    │  随机种子、初始状态序列化块                      │
│  Frame Data   │  帧号 + 指令列表（逐帧存储）                     │
│  Hash Log     │  可选的逐帧状态Hash（用于Desync诊断）             │
│  Trailer      │  校验和、文件结束标记                           │
└───────────────┴──────────────────────────────────────────────┘
```

**Header 详细结构**：

```
Byte Offset  Size  Field              Description
─────────────────────────────────────────────────────
0            4     Magic              0x524E5A47 ("GZNR" — "GameZeN Replay")
4            2     Version            格式版本号（如 0x0100）
6            2     Flags              Bit0: 是否压缩, Bit1: 是否有HashLog
8            4     Seed               Random seed（用于确定性随机）
12           4     LogicFPS           逻辑帧率（如15=66ms/turn）
16           4     TotalFrames        对局总帧数
20           4     PlayerCount        玩家数量
24           N     PlayerEntries      每个玩家的信息块
24+N         4     Checksum           Header CRC32
```

**Player Entry 结构**：

```
Byte Offset  Size  Field
───────────────────────────
0            4     PlayerID
4            1     TeamID
5            1     HeroID
6            N     PlayerName (null-terminated UTF-8)
6+N          4     SkinID
```

**Frame Data 格式**：

```
┌──────────────────────────────────────────────────────────┐
│ Frame 0: [FrameHeader] [CmdCount] [Cmd₀] [Cmd₁] ...      │
│ Frame 1: [FrameHeader] [CmdCount] [Cmd₀] [Cmd₁] ...      │
│ ...                                                      │
│ Frame N: [FrameHeader] [CmdCount] [Cmd₀] [Cmd₁] ...      │
└──────────────────────────────────────────────────────────┘

FrameHeader (4 bytes):
  - FrameNumber (uint16): 帧号
  - FrameFlags  (uint16): Bit0=关键帧（有快照）

Cmd (variable length):
  - PlayerID  (uint16): 谁发的指令
  - CmdType   (uint8):  指令类型
  - CmdLength (uint8):  指令数据长度
  - CmdData   (variable): 具体指令内容
```

### 2.2 录像写入

录像写入发生在每一帧执行之后。流程：

```
游戏主循环:
  for each Frame:
    1. 收集所有玩家输入 → Input[]
    2. 执行游戏逻辑（确定性）
    3. 写入帧数据到录像文件 ← 这里
    4. 渲染（非确定性，不影响录像）
```

关键设计决策：

**a) 实时写入 vs 内存缓冲后写入？**

实时写入（每次 Flush）更安全——崩溃不丢录像。但 IO 开销高。

**推荐**：内存双缓冲。累积 N 帧后批量写入。典型 N=60（约 4 秒@15Hz）。游戏结束时强制 Flush 剩余数据。

**b) 压缩策略**

帧同步录像不需要帧内压缩（指令本身就小）。但整体可以做块压缩：

```
原始: [Frame0][Frame1]...[Frame999]
压缩: 每 500 帧压缩为一个 LZ4 Block
     [Block0(LZ4)][Block1(LZ4)]...
```

LZ4 速度快（~500MB/s 压缩，~2GB/s 解压），对指令数据压缩比约 2~5x。

**c) 录像文件的生命周期**

```
对局开始 ──→ 创建录像文件 ──→ 每帧追加 ──→ 对局结束 ──→ 关闭文件
                                                      │
                                        ┌──────────────┘
                                        ├─→ 本地存储（用户回放）
                                        └─→ 上传服务器（反外挂分析/人工复核）
```

### 2.3 录像回放

回放的核心流程：

```
1. 加载录像文件 → 解析 Header
2. 初始化游戏引擎（加载地图、英雄数据）
3. 设置确定性环境：
   - Random.Seed = Header.Seed
   - 关闭所有非确定性输入（网络、系统时钟）
   - 关闭渲染（仅逻辑回放，用于服务器端分析）
4. For each Frame in FrameData:
   a. 读取帧号 + 指令列表
   b. 将指令注入逻辑引擎（模拟"收到网络输入"）
   c. 执行一帧逻辑
   d. 【可选】比对 HashLog 中的状态 Hash
   e. 【可选】渲染当前帧到屏幕
5. 录像结束
```

**为什么要关闭非确定性输入？**

回放时不能重新连接网络，不能读取真实系统时钟。所有外部输入必须来自录像文件：

```csharp
// 正常游戏流程
float deltaTime = Time.deltaTime;  // 系统时钟 → 非确定性！
int playerInput = Network.Receive(); // 网络数据 → 非确定性！

// 回放流程
float deltaTime = 1.0f / LogicFPS;  // 固定值 → 确定性
int playerInput = ReplayFile.ReadFrame(frameIndex); // 录像数据 → 确定性
```

**视角切换在回放中的实现**：

回放系统的一个杀手级功能是**自由视角**——玩家可以拖拽摄像机到任意位置，或切换到任意玩家的第一人称视角。

因为帧同步每个客户端拥有**全量游戏状态**（所有玩家的位置、血量都在内存里），切换到任意玩家视角只是改变 Camera 的追踪目标，不需要任何网络请求。

### 2.4 快进与快退

帧同步录像的跳转是一个性能难题。

#### 2.4.1 快进（Seek Forward）

**问题**：当前在帧 5000，用户拖进度条到帧 15000。需要"快进" 10000 帧。如果逐帧执行 10000 次，即使每帧只 1ms 也要等 10 秒。

**方案 1：跳帧执行 (Skip Rendering)**

快进时关闭渲染、物理碰撞检测优化、关闭 AI 寻路精度，只保留核心逻辑：

```csharp
void FastForward(int targetFrame) {
    // 关闭所有非必要系统
    bool savedRender = renderEnabled;
    bool savedPhysics = physicsEnabled;
    renderEnabled = false;
    physicsEnabled = false;

    // 加速执行（15Hz → 等效数千Hz）
    Stopwatch sw = Stopwatch.StartNew();
    while (currentFrame < targetFrame) {
        var cmds = replayFile.ReadFrame(currentFrame);
        logicEngine.ExecuteFrame(cmds);
        currentFrame++;
    }
    Debug.Log($"Fast-forward {targetFrame - startFrame} frames in {sw.ElapsedMilliseconds}ms");

    renderEnabled = savedRender;
    physicsEnabled = savedPhysics;
    // 渲染当前帧
    RenderFrame(currentFrame);
}
```

现代 CPU 可以在几百毫秒内执行数万帧逻辑。一场 30 分钟对局（27,000 帧）的快进到末尾通常不超过 1~2 秒。

**方案 2：关键帧快照（混合方案）**

每 N 帧存储一次完整状态快照。跳转到目标帧 T：

```
1. 找到 T 之前最近的关键帧快照（帧 K）
2. 加载快照状态
3. 从帧 K 执行到帧 T（只执行 T-K 帧，而非 T 帧）
```

关键帧间距的权衡：
- 间距小（如每 100 帧）：快照存储开销大，跳转快
- 间距大（如每 1000 帧）：快照存储开销小，跳转慢

典型值：500~1000 帧（约 30~60 秒 @15Hz）。

#### 2.4.2 快退（Seek Backward）

**问题**：帧同步无法"倒放"——逻辑引擎只能向前推进，不能反向执行。

**方案**：快退 = 回到 S₀ → 快进到目标帧。

```
用户从帧 15000 拖回帧 8000:
  1. Reset 引擎到 S₀
  2. 加载最近关键帧（帧 5000 的快照）
  3. 从帧 5000 快进到帧 8000（执行 3000 帧）
```

如果有关键帧机制，快退的成本 ≈ 快进 3000 帧的成本，而非 8000 帧。

#### 2.4.3 进度条的平滑拖动

用户拖动进度条时的 UX 挑战：每次拖动都触发一次"跳到目标帧"。如果逐帧执行，用户会感觉到明显卡顿。

**解决方案**：

```
用户拖动进度条:
  onDrag(targetFrame):
    1. 取消上次还在进行中的 Seek
    2. 渲染一帧占位画面（显示"跳转中..."或当前帧的缩略图）
    3. 异步执行快进到 targetFrame
    4. 到达后 → 恢复渲染
```

使用**防抖**：用户连续拖动时，只响应最后一次停止位置。

---

## 3. 状态同步录像

### 3.1 全量快照录像

状态同步游戏的服务端是权威数据源。录像最自然的方案是**在服务端记录状态快照**。

**基本流程**：

```
每个 Tick:
  1. 收集所有客户端输入
  2. 执行服务端权威逻辑
  3. 更新世界状态
  4. IF (currentTick % snapshotInterval == 0):
       序列化全量世界状态 → 写入录像文件
```

**全量快照的内容**（以 FPS 为例）：

```
Snapshot {
    tick: uint32,
    timestamp: float64,
    entities: [
        {
            id: uint32,
            type: uint8 (0=player, 1=npc, 2=projectile),
            position: vec3,
            rotation: vec3,
            velocity: vec3,
            health: float32,
            armor: float32,
            weapon_state: uint8,
            animation_state: uint16,
            ...
        },
        ...
    ],
    game_state: {
        round_time: float32,
        score_team_a: uint8,
        score_team_b: uint8,
        bomb_state: uint8, // CS:GO 的 C4 状态
        ...
    }
}
```

**开销估算**（CS:GO 风格的 5v5 FPS, 64Hz tick rate）：

- 每 Tick 约 20~50 个实体
- 每个实体约 64~128 字节序列化数据
- 全量快照 ≈ 20~50 × 128 ≈ 2.5~6.4 KB/快照
- 如果每 64 tick (1秒) 存一次快照，30 分钟 ≈ 1800 snapshots × 5KB ≈ 9MB/局
- LZ4 压缩后 ≈ 2~4MB/局

9MB 对一局 FPS 来说是合理的录像大小。但相比帧同步录像的 100KB，确实大了两个数量级。

### 3.2 增量快照录像

减少文件大小的核心思路：**不是每帧都存所有数据，只存变化的部分**。

```
Tick 0:    [全量快照: 所有实体状态]         ← 基线
Tick 1:    [增量: 实体#3 位置变化, 实体#7 血量变化]
Tick 2:    [增量: 实体#3 位置变化]
...
Tick N:    [全量快照: 所有实体状态]         ← 下一个基线（每 M Tick 一次）
```

**增量 Delta 编码**：

```cpp
struct EntityDelta {
    uint32_t entity_id;
    uint16_t changed_fields;  // bitmask: 哪些字段变了
    // 只序列化变化的字段
    // Bit 0: position → vec3 new_position
    // Bit 1: rotation → vec3 new_rotation
    // Bit 2: velocity → vec3 new_velocity
    // Bit 3: health   → float new_health
    // ...
};

struct TickDelta {
    uint32_t tick;
    uint8_t  delta_count;
    EntityDelta deltas[delta_count];
};
```

**bitmask 技巧**：用 uint16_t 的每一位表示一个字段是否变化。只序列化标记为 1 的字段。如果实体这一帧完全没变（如静止的 NPC），则不出现在增量中。

增量快照可以将录像大小减少 60~80%：从 ~9MB 降到 ~2~3MB。

### 3.3 回放时的插值处理

状态同步录像的一个独特挑战：**快照是不连续的离散点**，而玩家期望看到流畅的连续运动。

```
真实运动:  ════════════════════
快照:      ●       ●       ●       ●       ●
           |       |       |       |       |
         Tick0   TickN   Tick2N  Tick3N  Tick4N

回放时:
  在快照之间做插值 → 让运动看起来平滑
```

**插值策略**：

```cpp
// 找到目标时间点前后的两个快照
Snapshot snap_before = FindNearestSnapshot(time - lookback);
Snapshot snap_after  = FindNearestSnapshot(time + lookahead);

// 线性插值
float t = (target_time - snap_before.timestamp) /
          (snap_after.timestamp - snap_before.timestamp);

for each entity:
    entity.position = Lerp(snap_before.position, snap_after.position, t);
    entity.rotation = Slerp(snap_before.rotation, snap_after.rotation, t);
```

**注意事项**：
- 位置用线性插值 OK
- 旋转用球面线性插值（Slerp）避免万向节问题
- 血量等标量值也线性插值
- 死亡/复活是离散事件，不能插值——实体要么活着要么死了
- 子弹/弹道：最好在录像中单独记录轨迹，而不是依赖快照插值

---

## 4. 代码示例

### 4.1 C#：帧同步录像写入和回放

```csharp
// ============================================================
// ReplayFileWriter.cs — 帧同步录像写入模块 (Unity/C#)
// 使用场景：在 Lockstep 客户端或服务器上，每帧写入指令到录像文件
// ============================================================

using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression; // DeflateStream

/// <summary>
/// 录像文件格式常量
/// </summary>
public static class ReplayConstants
{
    public const uint MAGIC = 0x524E5A47;  // "GZNR"
    public const ushort VERSION = 0x0100;
    public const int FRAMES_PER_BLOCK = 500; // 每500帧压缩一个块
    public const int SNAPSHOT_INTERVAL = 600; // 每600帧(~40秒@15Hz)存一次关键帧快照
}

/// <summary>
/// 录像文件头
/// </summary>
public struct ReplayHeader
{
    public uint magic;
    public ushort version;
    public ushort flags;            // Bit0: compressed, Bit1: hasHashLog
    public uint randomSeed;
    public uint logicFPS;
    public uint totalFrames;        // 对局结束后回填
    public uint playerCount;
    public ReplayPlayerInfo[] players;
}

public struct ReplayPlayerInfo
{
    public uint playerId;
    public byte teamId;
    public byte heroId;
    public string playerName;       // UTF-8, max 64 bytes
    public uint skinId;
}

// ---- 以下是 4.1.1 ~ 4.1.3 三个完整模块 ----

/// <summary>
/// 帧同步录像写入器。
/// 负责创建录像文件、写入头部、逐帧追加指令、定期写入快照、压缩和关闭。
/// </summary>
public class ReplayFileWriter : IDisposable
{
    private FileStream _fileStream;
    private BinaryWriter _writer;
    private MemoryStream _frameBuffer;   // 帧数据缓冲区，攒够一个 Block 后压缩写入
    private BinaryWriter _frameBufferWriter;
    private int _framesInBuffer;
    private uint _currentFrame;
    private ReplayHeader _header;
    private bool _disposed;

    // 反外挂用的操作日志（可选的扩展字段）
    private List<string> _operationLog;

    /// <summary>
    /// 创建录像文件并写入头部。
    /// </summary>
    /// <param name="filePath">录像文件完整路径</param>
    /// <param name="header">录像头部信息</param>
    public ReplayFileWriter(string filePath, ReplayHeader header)
    {
        _header = header;
        // 文件已存在则覆盖（同一对局不会重复创建）
        _fileStream = new FileStream(filePath, FileMode.Create, FileAccess.Write, FileShare.Read);
        _writer = new BinaryWriter(_fileStream);
        _frameBuffer = new MemoryStream(65536); // 64KB 初始缓冲区
        _frameBufferWriter = new BinaryWriter(_frameBuffer);
        _framesInBuffer = 0;
        _currentFrame = 0;
        _operationLog = new List<string>();

        WriteHeader();
    }

    // ---------- 头部序列化 ----------

    private void WriteHeader()
    {
        // 魔数 + 版本 + 标志
        _writer.Write(_header.magic);
        _writer.Write(_header.version);
        _writer.Write(_header.flags);
        // 随机种子（回放时必须一致）
        _writer.Write(_header.randomSeed);
        // 逻辑帧率
        _writer.Write(_header.logicFPS);
        // 总帧数占位（对局结束后回填）
        _writer.Write((uint)0);
        // 玩家数量
        _writer.Write(_header.playerCount);

        // 写入每个玩家的信息
        foreach (var p in _header.players)
        {
            _writer.Write(p.playerId);
            _writer.Write(p.teamId);
            _writer.Write(p.heroId);
            // 玩家名：固定 64 字节 UTF-8（后补零）
            byte[] nameBytes = new byte[64];
            if (!string.IsNullOrEmpty(p.playerName))
            {
                byte[] src = System.Text.Encoding.UTF8.GetBytes(p.playerName);
                int len = Math.Min(src.Length, 63);
                Buffer.BlockCopy(src, 0, nameBytes, 0, len);
            }
            _writer.Write(nameBytes);
            _writer.Write(p.skinId);
        }

        // 预留帧数据区偏移量占位（后面回填）
        // 留 4 字节给"帧数据起始 offset"
        _writer.Write((uint)0); // placeholder: offset to frame data
    }

    // ---------- 帧数据追加 ----------

    /// <summary>
    /// 写入一帧的指令数据。
    /// 调用时机：每逻辑帧执行完毕后。
    /// </summary>
    /// <param name="frameNumber">帧号（从0自增）</param>
    /// <param name="commands">本帧所有玩家的指令列表</param>
    public void WriteFrame(uint frameNumber, ReplayCommand[] commands)
    {
        // 帧号 = 帧头
        _frameBufferWriter.Write((ushort)frameNumber);
        // flags: Bit0=isKeyframe
        ushort flags = (ushort)((frameNumber % ReplayConstants.SNAPSHOT_INTERVAL == 0) ? 1 : 0);
        _frameBufferWriter.Write(flags);

        // 指令数量
        _frameBufferWriter.Write((byte)commands.Length);

        // 逐指令写入
        foreach (var cmd in commands)
        {
            _frameBufferWriter.Write((ushort)cmd.playerId);
            _frameBufferWriter.Write((byte)cmd.cmdType);
            // 变长指令数据
            byte[] data = cmd.Serialize();
            _frameBufferWriter.Write((byte)data.Length);
            _frameBufferWriter.Write(data);
        }

        _framesInBuffer++;
        _currentFrame = frameNumber;

        // 缓冲区满 → 压缩并刷入文件
        if (_framesInBuffer >= ReplayConstants.FRAMES_PER_BLOCK)
        {
            FlushFrameBlock();
        }
    }

    /// <summary>
    /// 将缓冲区中的帧数据压缩后写入文件。
    /// CompressedBlock 格式: [4字节解压后大小][4字节压缩后大小][LZ4/Deflate 压缩数据]
    /// </summary>
    private void FlushFrameBlock()
    {
        if (_framesInBuffer == 0) return;

        _frameBufferWriter.Flush();
        byte[] rawData = _frameBuffer.ToArray();
        int rawLength = rawData.Length;

        // Deflate 压缩
        byte[] compressed;
        using (var ms = new MemoryStream())
        {
            using (var deflate = new DeflateStream(ms, CompressionLevel.Fastest, leaveOpen: true))
            {
                deflate.Write(rawData, 0, rawLength);
            }
            compressed = ms.ToArray();
        }

        // 写入压缩块头 + 数据
        _writer.Write(rawLength);
        _writer.Write(compressed.Length);
        _writer.Write(compressed);

        // 重置缓冲区
        _frameBuffer.SetLength(0);
        _frameBufferWriter.Seek(0, SeekOrigin.Begin);
        _framesInBuffer = 0;
    }

    // ---------- 关键帧快照 ----------

    /// <summary>
    /// 写入关键帧快照（混合录像功能）。
    /// 将当前游戏世界的完整状态序列化后存储。
    /// </summary>
    /// <param name="snapshot">游戏状态快照的字节数组（由游戏逻辑层序列化产生）</param>
    public void WriteKeyFrameSnapshot(byte[] snapshotData)
    {
        // 在帧数据中插入一个特殊标记
        _frameBufferWriter.Write((ushort)0xFFFF); // 特殊帧号表示"这是快照"
        _frameBufferWriter.Write((ushort)0x0001); // flags: 关键帧标记
        // 快照数据长度 + 数据
        _frameBufferWriter.Write(snapshotData.Length);
        _frameBufferWriter.Write(snapshotData);
    }

    // ---------- 关闭 & 回填 ----------

    /// <summary>
    /// 对局结束时调用：刷出剩余数据、回填总帧数、关闭文件。
    /// </summary>
    /// <param name="totalFrames">对局实际总帧数</param>
    public void Close(uint totalFrames)
    {
        if (_disposed) return;

        // 1. 刷出缓冲区中剩余的帧数据
        FlushFrameBlock();

        // 2. 回填 Header 中的总帧数
        // 总帧数字段在头部第 18 字节（magic:4 + version:2 + flags:2 + seed:4 + fps:4 = 16, totalFrames 在 offset 16）
        _fileStream.Seek(16, SeekOrigin.Begin);
        _writer.Write(totalFrames);

        // 3. 写入文件尾部的 CRC32 校验
        _fileStream.Seek(0, SeekOrigin.End);
        // 简单尾部标记: 4字节 "END\0"
        _writer.Write((uint)0x00444E45); // "END\0" 小端

        _writer.Flush();
        _fileStream.Flush(true); // 确保数据写入磁盘

        Dispose();
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _frameBufferWriter?.Dispose();
        _frameBuffer?.Dispose();
        _writer?.Dispose();
        _fileStream?.Dispose();
    }
}

// ---- 指令结构 ----

/// <summary>
/// 单条玩家指令。
/// 对应教程 7 中定义的帧同步指令格式。
/// </summary>
public struct ReplayCommand
{
    public uint playerId;
    public byte cmdType; // 0=move, 1=attack, 2=skill, 3=item...
    private byte[] _data;

    public ReplayCommand(uint playerId, byte cmdType, byte[] data)
    {
        this.playerId = playerId;
        this.cmdType = cmdType;
        this._data = data ?? Array.Empty<byte>();
    }

    public byte[] Serialize()
    {
        // 简单返回内部数据；实际项目可能包含更多字段
        return _data;
    }

    public static ReplayCommand Deserialize(uint playerId, byte cmdType, byte[] data)
    {
        return new ReplayCommand(playerId, cmdType, data);
    }
}

// ============================================================
// ReplayFileReader.cs — 帧同步录像回放模块
// ============================================================

/// <summary>
/// 帧同步录像读取器。
/// 负责解析录像文件、逐帧提取指令、支持跳转（Seek）到指定帧。
/// </summary>
public class ReplayFileReader : IDisposable
{
    private FileStream _fileStream;
    private BinaryReader _reader;
    private ReplayHeader _header;
    private long _frameDataOffset;      // 帧数据区在文件中的起始位置
    private uint _currentFrame;
    private bool _disposed;

    // 当前 Block 的解压缓存
    private byte[] _decompressedBlock;
    private int _decompressedOffset;    // 当前 Block 内读取位置
    private uint _nextFrameInBlock;     // 下一个 Block 的起始帧号
    private int[] _blockFrameCounts;    // 每个 Block 包含的帧数（用于 Seek）

    /// <summary>
    /// 公开的头部信息，回放系统需要读取种子、玩家信息等。
    /// </summary>
    public ReplayHeader Header => _header;

    /// <summary>
    /// 当前回放定位的帧号。
    /// </summary>
    public uint CurrentFrame => _currentFrame;

    /// <summary>
    /// 打开录像文件，解析头部。
    /// </summary>
    public ReplayFileReader(string filePath)
    {
        _fileStream = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.Read);
        _reader = new BinaryReader(_fileStream);
        _currentFrame = 0;
        ParseHeader();
    }

    // ---------- 头部解析 ----------

    private void ParseHeader()
    {
        _header = new ReplayHeader();

        // 验证魔数
        _header.magic = _reader.ReadUInt32();
        if (_header.magic != ReplayConstants.MAGIC)
        {
            throw new InvalidDataException(
                $"Invalid replay file: expected magic 0x{ReplayConstants.MAGIC:X8}, got 0x{_header.magic:X8}");
        }

        _header.version = _reader.ReadUInt16();
        if (_header.version > ReplayConstants.VERSION)
        {
            throw new InvalidDataException(
                $"Replay version {_header.version} is newer than supported version {ReplayConstants.VERSION}");
        }

        _header.flags = _reader.ReadUInt16();
        _header.randomSeed = _reader.ReadUInt32();
        _header.logicFPS = _reader.ReadUInt32();
        _header.totalFrames = _reader.ReadUInt32();
        _header.playerCount = _reader.ReadUInt32();

        // 解析玩家信息
        _header.players = new ReplayPlayerInfo[_header.playerCount];
        for (int i = 0; i < _header.playerCount; i++)
        {
            _header.players[i] = new ReplayPlayerInfo
            {
                playerId = _reader.ReadUInt32(),
                teamId = _reader.ReadByte(),
                heroId = _reader.ReadByte(),
                playerName = ReadFixedUTF8String(64),
                skinId = _reader.ReadUInt32()
            };
        }

        // 读取帧数据偏移量
        _frameDataOffset = _reader.BaseStream.Position;
    }

    private string ReadFixedUTF8String(int byteLength)
    {
        byte[] bytes = _reader.ReadBytes(byteLength);
        // 找到第一个 '\0' 的位置
        int nullIndex = Array.IndexOf(bytes, (byte)0);
        if (nullIndex >= 0)
            return System.Text.Encoding.UTF8.GetString(bytes, 0, nullIndex);
        return System.Text.Encoding.UTF8.GetString(bytes);
    }

    // ---------- 逐帧读取指令 ----------

    /// <summary>
    /// 读取当前帧的指令列表，并将读取指针推进到下一帧。
    /// 返回 null 表示录像已到末尾。
    /// </summary>
    public ReplayFrameData ReadNextFrame()
    {
        if (_currentFrame >= _header.totalFrames)
            return null;

        // 如果需要切换到下一个压缩块
        if (_decompressedBlock == null || _decompressedOffset >= _decompressedBlock.Length)
        {
            if (!LoadNextBlock())
                return null;
        }

        // 从解压缓存中读取一帧
        return ReadFrameFromBuffer();
    }

    /// <summary>
    /// 加载下一个压缩块到解压缓存中。
    /// </summary>
    private bool LoadNextBlock()
    {
        if (_reader.BaseStream.Position >= _reader.BaseStream.Length - 4)
            return false; // 到达文件尾（-4 是因为有 tail marker）

        // 读取压缩块头
        int rawLength = _reader.ReadInt32();
        int compressedLength = _reader.ReadInt32();
        byte[] compressed = _reader.ReadBytes(compressedLength);

        // Deflate 解压
        using (var compressedStream = new MemoryStream(compressed))
        using (var deflate = new DeflateStream(compressedStream, CompressionMode.Decompress))
        using (var decompressedStream = new MemoryStream())
        {
            deflate.CopyTo(decompressedStream);
            _decompressedBlock = decompressedStream.ToArray();
        }

        // 校验解压后长度
        if (_decompressedBlock.Length != rawLength)
        {
            throw new InvalidDataException(
                $"Block decompression size mismatch: expected {rawLength}, got {_decompressedBlock.Length}");
        }

        _decompressedOffset = 0;
        return true;
    }

    /// <summary>
    /// 从解压缓存中读取一帧的完整数据（帧头 + 指令列表）。
    /// </summary>
    private ReplayFrameData ReadFrameFromBuffer()
    {
        // 帧头: uint16 frameNumber, uint16 flags
        ushort frameNum = BitConverter.ToUInt16(_decompressedBlock, _decompressedOffset);
        _decompressedOffset += 2;
        ushort flags = BitConverter.ToUInt16(_decompressedBlock, _decompressedOffset);
        _decompressedOffset += 2;

        // 检查是否是关键帧标记
        if (frameNum == 0xFFFF) // 快照标记
        {
            int snapLen = BitConverter.ToInt32(_decompressedBlock, _decompressedOffset);
            _decompressedOffset += 4;
            byte[] snapData = new byte[snapLen];
            Buffer.BlockCopy(_decompressedBlock, _decompressedOffset, snapData, 0, snapLen);
            _decompressedOffset += snapLen;
            // 快照帧跳过（由上层处理），继续读下一帧
            return ReadFrameFromBuffer();
        }

        // 指令数量
        byte cmdCount = _decompressedBlock[_decompressedOffset];
        _decompressedOffset += 1;

        // 逐指令解析
        var commands = new ReplayCommand[cmdCount];
        for (int i = 0; i < cmdCount; i++)
        {
            uint pid = BitConverter.ToUInt16(_decompressedBlock, _decompressedOffset);
            _decompressedOffset += 2;
            byte cmdType = _decompressedBlock[_decompressedOffset];
            _decompressedOffset += 1;
            byte dataLen = _decompressedBlock[_decompressedOffset];
            _decompressedOffset += 1;
            byte[] data = new byte[dataLen];
            Buffer.BlockCopy(_decompressedBlock, _decompressedOffset, data, 0, dataLen);
            _decompressedOffset += dataLen;

            commands[i] = ReplayCommand.Deserialize(pid, cmdType, data);
        }

        var fd = new ReplayFrameData
        {
            frameNumber = frameNum,
            isKeyFrame = (flags & 1) != 0,
            commands = commands
        };
        _currentFrame = frameNum;
        return fd;
    }

    // ---------- Seek 支持 ----------

    /// <summary>
    /// 跳转到指定帧（如果需要加载快照并快进）。
    /// 简化实现：回到文件帧数据起始位置，逐块跳到目标帧所在 Block。
    /// 完整实现应使用关键帧快照索引加速。
    /// </summary>
    public void SeekTo(uint targetFrame)
    {
        if (targetFrame > _header.totalFrames)
            targetFrame = _header.totalFrames;

        // 最简单实现：Reset + 逐块跳过
        _reader.BaseStream.Seek(_frameDataOffset, SeekOrigin.Begin);
        _decompressedBlock = null;
        _decompressedOffset = 0;
        _currentFrame = 0;

        // 逐帧跳过（生产环境应使用快照索引加速，这里展示原理）
        while (_currentFrame < targetFrame)
        {
            var fd = ReadNextFrame();
            if (fd == null) break;
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _reader?.Dispose();
        _fileStream?.Dispose();
    }
}

/// <summary>
/// 回放时的一帧数据。
/// </summary>
public class ReplayFrameData
{
    public uint frameNumber;
    public bool isKeyFrame;
    public ReplayCommand[] commands;
}

// ============================================================
// ReplayPlayer.cs — 回放播放控制器
// ============================================================

/// <summary>
/// 回放播放控制器。
/// 管理播放状态、速度、视角切换。
/// </summary>
public class ReplayPlayer
{
    public enum PlayState { Stopped, Playing, Paused, Seeking }

    private ReplayFileReader _reader;
    private PlayState _state;
    private float _playSpeed;      // 1.0 = 正常速度, 2.0 = 2倍速
    private float _frameAccumulator; // 用于按逻辑帧率推进
    private bool _seekPending;
    private uint _seekTarget;
    private PlayState _preSeekState;

    public PlayState State => _state;
    public float PlaySpeed { get => _playSpeed; set => _playSpeed = Mathf.Max(0.1f, value); }

    public ReplayPlayer(ReplayFileReader reader)
    {
        _reader = reader;
        _state = PlayState.Stopped;
        _playSpeed = 1.0f;
        _frameAccumulator = 0f;
    }

    /// <summary>
    /// 开始播放（从头或从当前位置）。
    /// </summary>
    public void Play()
    {
        _state = PlayState.Playing;
    }

    /// <summary>
    /// 暂停。
    /// </summary>
    public void Pause()
    {
        _state = PlayState.Paused;
    }

    /// <summary>
    /// 停止并重置到开头。
    /// </summary>
    public void Stop()
    {
        _state = PlayState.Stopped;
        _reader.SeekTo(0);
    }

    /// <summary>
    /// 跳转到指定帧（异步）。会先进入 Seeking 状态。
    /// </summary>
    public void SeekTo(uint targetFrame)
    {
        _seekPending = true;
        _seekTarget = targetFrame;
        _preSeekState = _state;
        _state = PlayState.Seeking;
    }

    /// <summary>
    /// 每渲染帧调用。推进回放逻辑。
    /// </summary>
    public void Update(float deltaTime)
    {
        if (_state == PlayState.Seeking)
        {
            // 执行 Seek 操作
            _reader.SeekTo(_seekTarget);
            _seekPending = false;
            _state = _preSeekState;
            return;
        }

        if (_state != PlayState.Playing)
            return;

        // 按逻辑帧率累积时间
        float frameInterval = 1.0f / _reader.Header.logicFPS;
        _frameAccumulator += deltaTime * _playSpeed;

        // 一次 Update 可能执行多帧（高速快进时）
        while (_frameAccumulator >= frameInterval)
        {
            _frameAccumulator -= frameInterval;

            var fd = _reader.ReadNextFrame();
            if (fd == null)
            {
                _state = PlayState.Stopped;
                return;
            }

            // 注入指令到逻辑引擎
            LogicEngine.Instance.ExecuteFrame(fd.commands);
        }
    }
}

/// <summary>
/// 辅助类：Unity 的 Mathf 模拟（避免引入完整 UnityEngine 依赖）。
/// </summary>
public static class Mathf
{
    public static float Max(float a, float b) => a > b ? a : b;
}
```

### 4.2 C++：状态同步快照录像系统

```cpp
// ============================================================
// snapshot_replay.h — 状态同步快照录像系统 (C++17)
// 用于权威服务器端录制，支持全量快照和增量 Delta。
// ============================================================

#pragma once

#include <cstdint>
#include <vector>
#include <string>
#include <fstream>
#include <unordered_map>
#include <memory>
#include <cstring>
#include <algorithm>
#include <zlib.h>  // 用于压缩（或用 LZ4）

// -------------------------------------------------------
// 基础类型定义
// -------------------------------------------------------

struct Vec3 {
    float x, y, z;

    bool operator==(const Vec3& o) const {
        return x == o.x && y == o.y && z == o.z;
    }
    bool operator!=(const Vec3& o) const { return !(*this == o); }
};

// 实体状态：简化表示，实际项目包含 40+ 字段
struct EntityState {
    uint32_t id;
    uint8_t  type;       // 0=player, 1=npc, 2=projectile, 3=item
    Vec3     position;
    Vec3     rotation;
    Vec3     velocity;
    float    health;
    float    armor;
    uint8_t  weapon_state;
    uint16_t anim_state;
    uint8_t  life_state; // 0=alive, 1=dead, 2=respawning

    // ---- Delta 编码支持 ----
    // 计算与另一个状态的差异 bitmask
    uint16_t ComputeDeltaMask(const EntityState& prev) const {
        uint16_t mask = 0;
        if (position     != prev.position)     mask |= (1 << 0);
        if (rotation     != prev.rotation)     mask |= (1 << 1);
        if (velocity     != prev.velocity)     mask |= (1 << 2);
        if (health       != prev.health)       mask |= (1 << 3);
        if (armor        != prev.armor)        mask |= (1 << 4);
        if (weapon_state != prev.weapon_state) mask |= (1 << 5);
        if (anim_state   != prev.anim_state)   mask |= (1 << 6);
        if (life_state   != prev.life_state)   mask |= (1 << 7);
        return mask;
    }
};

// 游戏状态哈希（用于 Desync 诊断和快照校验）
using StateHash = uint64_t;

// -------------------------------------------------------
// 快照录像写入器
// -------------------------------------------------------

class SnapshotReplayWriter {
public:
    struct Config {
        uint32_t full_snapshot_interval = 300;  // 每 N tick 存一次全量快照
        uint32_t delta_interval         = 1;    // 每 N tick 存一次增量（1=每tick）
        bool     enable_compression     = true;
        uint32_t compression_level      = 1;    // zlib: 1=fastest, 9=best
    };

    explicit SnapshotReplayWriter(const std::string& filepath, const Config& cfg = {})
        : _config(cfg)
    {
        _file.open(filepath, std::ios::binary | std::ios::trunc);
        if (!_file.is_open()) {
            throw std::runtime_error("Failed to open replay file: " + filepath);
        }
        WriteFileHeader();
    }

    ~SnapshotReplayWriter() {
        Close();
    }

    // ---- 录制接口 ----

    /// 写入一个全量快照。调用时机：对局开始 或 每 N tick。
    void WriteFullSnapshot(
        uint32_t tick,
        const std::vector<EntityState>& entities,
        StateHash hash = 0)
    {
        WriteTickHeader(tick, SnapshotType::Full);

        // 实体数量
        uint32_t count = static_cast<uint32_t>(entities.size());
        _file.write(reinterpret_cast<const char*>(&count), sizeof(count));

        // 每个实体的完整状态
        for (const auto& e : entities) {
            WriteEntityFull(e);
        }

        // 可选的状态 Hash
        _file.write(reinterpret_cast<const char*>(&hash), sizeof(hash));

        // 更新"上一个全量快照"的实体引用（用于 Delta 计算）
        _lastFullEntities = entities;

        _tickCount++;
    }

    /// 写入增量快照。只有变化的字段才序列化。
    void WriteDeltaSnapshot(
        uint32_t tick,
        const std::vector<EntityState>& current_entities)
    {
        WriteTickHeader(tick, SnapshotType::Delta);

        // 与上一帧做 Diff，找出变化的实体
        std::vector<EntityState> deltas;
        for (const auto& cur : current_entities) {
            // 找到上一帧中同 ID 的实体
            auto it = std::find_if(_lastFullEntities.begin(), _lastFullEntities.end(),
                [&](const EntityState& e) { return e.id == cur.id; });
            if (it == _lastFullEntities.end()) {
                // 新实体 → 写入全量（标记 mask = 0xFFFF 表示新增）
                EntityState full = cur;
                // 使用 mask 0xFFFF 表示这是新实体
                deltas.push_back(full);
            } else {
                uint16_t mask = cur.ComputeDeltaMask(*it);
                if (mask != 0) {
                    EntityState delta = cur;
                    // mask 存储在 life_state 位置（脏用，实际项目用独立字段）
                    deltas.push_back(delta);
                    // 需要在这里记录 mask。实际做法：每个 delta entity 前先写 mask。
                    // 简化实现中，我们在序列化时处理。
                }
            }
        }

        // 写入 Delta 数量
        uint32_t count = static_cast<uint32_t>(deltas.size());
        _file.write(reinterpret_cast<const char*>(&count), sizeof(count));

        for (const auto& e : deltas) {
            // 找到上一帧的同 ID 实体
            auto prev = std::find_if(_lastFullEntities.begin(), _lastFullEntities.end(),
                [&](const EntityState& s) { return s.id == e.id; });
            uint16_t mask;
            if (prev == _lastFullEntities.end()) {
                mask = 0xFFFF; // 新实体：所有字段都写
            } else {
                mask = e.ComputeDeltaMask(*prev);
            }

            WriteEntityDelta(e, mask);
        }

        // 更新缓存
        for (const auto& cur : current_entities) {
            auto it = std::find_if(_lastFullEntities.begin(), _lastFullEntities.end(),
                [&](const EntityState& s) { return s.id == cur.id; });
            if (it != _lastFullEntities.end()) {
                *it = cur;
            } else {
                _lastFullEntities.push_back(cur);
            }
        }

        _tickCount++;
    }

    /// 自动选择全量或增量（上层无需关心细节）。
    void WriteTick(
        uint32_t tick,
        const std::vector<EntityState>& entities,
        StateHash hash = 0)
    {
        if (tick % _config.full_snapshot_interval == 0) {
            WriteFullSnapshot(tick, entities, hash);
        } else {
            WriteDeltaSnapshot(tick, entities);
        }
    }

    /// 关闭录像文件，写入尾部标记。
    void Close() {
        if (_closed) return;
        _closed = true;

        // 写入尾部
        WriteU32(0x524F4645); // "EORF" — End Of Replay File
        _file.flush();
        _file.close();
    }

private:
    // 快照类型
    enum class SnapshotType : uint8_t {
        Full  = 0,
        Delta = 1
    };

    void WriteFileHeader() {
        // 魔数 "SNRP" (Snapshot RePlay)
        WriteU32(0x50524E53); // "SNRP" little-endian
        WriteU32(_config.full_snapshot_interval);
        WriteU32(_config.delta_interval);
        WriteU8(_config.enable_compression ? 1 : 0);
    }

    void WriteTickHeader(uint32_t tick, SnapshotType type) {
        WriteU32(tick);
        WriteU8(static_cast<uint8_t>(type));
    }

    // ---- 序列化辅助 ----

    void WriteU32(uint32_t v) {
        _file.write(reinterpret_cast<const char*>(&v), sizeof(v));
    }
    void WriteU16(uint16_t v) {
        _file.write(reinterpret_cast<const char*>(&v), sizeof(v));
    }
    void WriteU8(uint8_t v) {
        _file.write(reinterpret_cast<const char*>(&v), sizeof(v));
    }
    void WriteF32(float v) {
        _file.write(reinterpret_cast<const char*>(&v), sizeof(v));
    }

    void WriteEntityFull(const EntityState& e) {
        WriteU32(e.id);
        WriteU8(e.type);
        WriteF32(e.position.x); WriteF32(e.position.y); WriteF32(e.position.z);
        WriteF32(e.rotation.x); WriteF32(e.rotation.y); WriteF32(e.rotation.z);
        WriteF32(e.velocity.x); WriteF32(e.velocity.y); WriteF32(e.velocity.z);
        WriteF32(e.health);
        WriteF32(e.armor);
        WriteU8(e.weapon_state);
        WriteU16(e.anim_state);
        WriteU8(e.life_state);
    }

    void WriteEntityDelta(const EntityState& e, uint16_t mask) {
        // 先写 mask，再按位写对应字段
        WriteU32(e.id);
        WriteU16(mask);

        if (mask & (1 << 0)) {
            WriteF32(e.position.x); WriteF32(e.position.y); WriteF32(e.position.z);
        }
        if (mask & (1 << 1)) {
            WriteF32(e.rotation.x); WriteF32(e.rotation.y); WriteF32(e.rotation.z);
        }
        if (mask & (1 << 2)) {
            WriteF32(e.velocity.x); WriteF32(e.velocity.y); WriteF32(e.velocity.z);
        }
        if (mask & (1 << 3)) { WriteF32(e.health); }
        if (mask & (1 << 4)) { WriteF32(e.armor); }
        if (mask & (1 << 5)) { WriteU8(e.weapon_state); }
        if (mask & (1 << 6)) { WriteU16(e.anim_state); }
        if (mask & (1 << 7)) { WriteU8(e.life_state); }
    }

    // ---- 状态 ----
    Config _config;
    std::ofstream _file;
    uint32_t _tickCount = 0;
    std::vector<EntityState> _lastFullEntities;  // 用于 Delta 计算
    bool _closed = false;
};

// -------------------------------------------------------
// 快照录像读取器
// -------------------------------------------------------

class SnapshotReplayReader {
public:
    explicit SnapshotReplayReader(const std::string& filepath) {
        _file.open(filepath, std::ios::binary);
        if (!_file.is_open()) {
            throw std::runtime_error("Failed to open replay file: " + filepath);
        }
        ParseHeader();
    }

    ~SnapshotReplayReader() {
        if (_file.is_open()) _file.close();
    }

    /// 逐 Tick 读取。返回 true 表示成功读取一个 Tick 的数据。
    /// snapshot_type 输出：0=Full, 1=Delta
    bool ReadNextTick(
        uint32_t& out_tick,
        uint8_t& out_type,
        std::vector<EntityState>& out_entities,
        StateHash& out_hash)
    {
        // 检查是否到文件末尾
        if (_file.peek() == EOF) return false;

        // 检查尾部标记
        uint32_t peek = 0;
        auto pos = _file.tellg();
        _file.read(reinterpret_cast<char*>(&peek), sizeof(peek));
        if (peek == 0x524F4645) { // "EORF" — 文件结束
            return false;
        }
        _file.seekg(pos); // 回退

        // 读取 Tick Header
        out_tick = ReadU32();
        out_type = ReadU8();

        uint32_t count = ReadU32();
        out_entities.resize(count);

        if (out_type == 0) { // Full snapshot
            for (uint32_t i = 0; i < count; ++i) {
                out_entities[i] = ReadEntityFull();
            }
            out_hash = ReadU64();
            // 更新缓存
            _cachedEntities = out_entities;
        } else { // Delta snapshot
            for (uint32_t i = 0; i < count; ++i) {
                uint32_t id = ReadU32();
                uint16_t mask = ReadU16();
                EntityState e = ReadEntityDelta(id, mask);
                // 合并到缓存中
                auto it = std::find_if(_cachedEntities.begin(), _cachedEntities.end(),
                    [&](const EntityState& s) { return s.id == id; });
                if (it != _cachedEntities.end()) {
                    MergeDelta(*it, e, mask);
                } else {
                    _cachedEntities.push_back(e);
                }
            }
            out_entities = _cachedEntities;
            out_hash = 0;
        }

        return true;
    }

private:
    EntityState ReadEntityFull() {
        EntityState e;
        e.id           = ReadU32();
        e.type         = ReadU8();
        e.position.x   = ReadF32(); e.position.y = ReadF32(); e.position.z = ReadF32();
        e.rotation.x   = ReadF32(); e.rotation.y = ReadF32(); e.rotation.z = ReadF32();
        e.velocity.x   = ReadF32(); e.velocity.y = ReadF32(); e.velocity.z = ReadF32();
        e.health       = ReadF32();
        e.armor        = ReadF32();
        e.weapon_state = ReadU8();
        e.anim_state   = ReadU16();
        e.life_state   = ReadU8();
        return e;
    }

    EntityState ReadEntityDelta(uint32_t id, uint16_t mask) {
        EntityState e{};
        e.id = id;
        if (mask & (1 << 0)) {
            e.position.x = ReadF32(); e.position.y = ReadF32(); e.position.z = ReadF32();
        }
        if (mask & (1 << 1)) {
            e.rotation.x = ReadF32(); e.rotation.y = ReadF32(); e.rotation.z = ReadF32();
        }
        if (mask & (1 << 2)) {
            e.velocity.x = ReadF32(); e.velocity.y = ReadF32(); e.velocity.z = ReadF32();
        }
        if (mask & (1 << 3)) { e.health = ReadF32(); }
        if (mask & (1 << 4)) { e.armor  = ReadF32(); }
        if (mask & (1 << 5)) { e.weapon_state = ReadU8(); }
        if (mask & (1 << 6)) { e.anim_state   = ReadU16(); }
        if (mask & (1 << 7)) { e.life_state   = ReadU8(); }
        return e;
    }

    void MergeDelta(EntityState& target, const EntityState& delta, uint16_t mask) {
        if (mask & (1 << 0)) target.position = delta.position;
        if (mask & (1 << 1)) target.rotation = delta.rotation;
        if (mask & (1 << 2)) target.velocity = delta.velocity;
        if (mask & (1 << 3)) target.health = delta.health;
        if (mask & (1 << 4)) target.armor = delta.armor;
        if (mask & (1 << 5)) target.weapon_state = delta.weapon_state;
        if (mask & (1 << 6)) target.anim_state = delta.anim_state;
        if (mask & (1 << 7)) target.life_state = delta.life_state;
    }

    void ParseHeader() {
        uint32_t magic = ReadU32();
        if (magic != 0x50524E53) { // "SNRP"
            throw std::runtime_error("Not a valid snapshot replay file");
        }
        _fullSnapshotInterval = ReadU32();
        _deltaInterval = ReadU32();
        _compressed = (ReadU8() != 0);
    }

    // ---- 底层读取 ----
    uint32_t ReadU32() {
        uint32_t v; _file.read(reinterpret_cast<char*>(&v), sizeof(v)); return v;
    }
    uint16_t ReadU16() {
        uint16_t v; _file.read(reinterpret_cast<char*>(&v), sizeof(v)); return v;
    }
    uint8_t ReadU8() {
        uint8_t v; _file.read(reinterpret_cast<char*>(&v), sizeof(v)); return v;
    }
    float ReadF32() {
        float v; _file.read(reinterpret_cast<char*>(&v), sizeof(v)); return v;
    }
    uint64_t ReadU64() {
        uint64_t v; _file.read(reinterpret_cast<char*>(&v), sizeof(v)); return v;
    }

    // ---- 状态 ----
    std::ifstream _file;
    uint32_t _fullSnapshotInterval = 300;
    uint32_t _deltaInterval = 1;
    bool _compressed = false;
    std::vector<EntityState> _cachedEntities;
};

// ============================================================
// 使用示例（在服务器 Tick 循环中集成）
// ============================================================
//
//   SnapshotReplayWriter writer("match_12345.srp");
//
//   while (match_running) {
//       entities = RunServerTick(tick, inputs);
//       writer.WriteTick(tick, entities);
//       tick++;
//   }
//
//   writer.Close();
//
// 回放时:
//   SnapshotReplayReader reader("match_12345.srp");
//   uint32_t tick;
//   uint8_t type;
//   std::vector<EntityState> entities;
//   uint64_t hash;
//   while (reader.ReadNextTick(tick, type, entities, hash)) {
//       RenderFrame(entities);  // 渲染/播放
//   }
```

### 4.3 Lua：录像管理器

```lua
-- ============================================================
-- replay_manager.lua — 录像管理器 (Lua 5.3+)
-- 用于帧同步游戏的客户端/服务器侧录像生命周期管理。
-- 包括：创建、保存、加载、列表管理、自动清理。
-- ============================================================

local ReplayManager = {}
ReplayManager.__index = ReplayManager

-- 录像文件魔数：'GZNR' = GameZeN Replay
local MAGIC = 0x524E5A47
local CURRENT_VERSION = 0x0100
local HEADER_SIZE = 128  -- 固定的头部字节数

-- ============================================================
-- 元数据提取（不解析完整录像，只读头部）
-- ============================================================

--- 从录像文件中提取元数据（快速预览，不加载完整内容）
--- @param filepath string 录像文件路径
--- @return table|nil 元数据表，失败返回 nil
--- @return string|nil 错误信息
function ReplayManager.extract_metadata(filepath)
    local f, err = io.open(filepath, "rb")
    if not f then
        return nil, "Failed to open: " .. (err or "unknown")
    end

    -- 读取原始字节的辅助函数
    local function read_u32()
        local b = f:read(4)
        if not b or #b < 4 then return nil end
        -- Little-endian 反序列化
        return string.unpack("<I4", b)
    end

    local function read_u16()
        local b = f:read(2)
        if not b or #b < 2 then return nil end
        return string.unpack("<I2", b)
    end

    local function read_bytes(n)
        return f:read(n)
    end

    -- 验证魔数
    local magic = read_u32()
    if not magic or magic ~= MAGIC then
        f:close()
        return nil, "Invalid replay file: bad magic"
    end

    local version = read_u16()
    local flags = read_u16()
    local seed = read_u32()
    local logic_fps = read_u32()
    local total_frames = read_u32()
    local player_count = read_u32()

    local players = {}
    for i = 1, player_count do
        local pid = read_u32()
        local team = f:read(1):byte()
        local hero = f:read(1):byte()
        -- 玩家名：最多 64 字节 UTF-8
        local name_bytes = read_bytes(64)
        -- 找到 '\0' 截断
        local null_pos = name_bytes:find("\0")
        local name = null_pos and name_bytes:sub(1, null_pos - 1) or name_bytes
        local skin = read_u32()

        players[i] = {
            player_id = pid,
            team_id = team,
            hero_id = hero,
            name = name,
            skin_id = skin,
        }
    end

    f:close()

    -- 估算时长（秒）
    local duration_sec = logic_fps > 0 and (total_frames / logic_fps) or 0

    return {
        magic = magic,
        version = version,
        flags = flags,
        seed = seed,
        logic_fps = logic_fps,
        total_frames = total_frames,
        player_count = player_count,
        players = players,
        duration_sec = duration_sec,
        filepath = filepath,
    }
end

-- ============================================================
-- 录像文件头序列化（用于创建录像时）
-- ============================================================

--- 将录像头部序列化为字节串
--- @param header table 头部信息表
--- @return string 128字节的头部数据
function ReplayManager.serialize_header(header)
    -- 使用 table.concat 构建字节串比直接拼接更高效
    local parts = {}

    parts[#parts + 1] = string.pack("<I4", MAGIC)
    parts[#parts + 1] = string.pack("<I2", header.version or CURRENT_VERSION)
    parts[#parts + 1] = string.pack("<I2", header.flags or 0)
    parts[#parts + 1] = string.pack("<I4", header.seed or 0)
    parts[#parts + 1] = string.pack("<I4", header.logic_fps or 15)
    parts[#parts + 1] = string.pack("<I4", 0) -- total_frames 占位
    parts[#parts + 1] = string.pack("<I4", #(header.players or {}))

    -- 序列化玩家信息
    for _, p in ipairs(header.players or {}) do
        parts[#parts + 1] = string.pack("<I4", p.player_id or 0)
        parts[#parts + 1] = string.char(p.team_id or 0)
        parts[#parts + 1] = string.char(p.hero_id or 0)
        -- 玩家名：固定 64 字节
        local name_bytes = (p.name or ""):sub(1, 63)
        name_bytes = name_bytes .. string.rep("\0", 64 - #name_bytes)
        parts[#parts + 1] = name_bytes
        parts[#parts + 1] = string.pack("<I4", p.skin_id or 0)
    end

    local header_str = table.concat(parts)
    -- 补齐到 HEADER_SIZE
    if #header_str < HEADER_SIZE then
        header_str = header_str .. string.rep("\0", HEADER_SIZE - #header_str)
    end
    return header_str
end

-- ============================================================
-- 录像文件实例（代表一个正在写入或读取的录像会话）
-- ============================================================

--- 创建新的录像写入会话
--- @param filepath string 输出文件路径
--- @param header table 头部信息
--- @return table|nil 录像写入句柄
--- @return string|nil 错误信息
function ReplayManager.create_replay(filepath, header)
    local f, err = io.open(filepath, "wb")
    if not f then
        return nil, "Failed to create: " .. (err or "unknown")
    end

    -- 写入头部
    local header_bytes = ReplayManager.serialize_header(header)
    f:write(header_bytes)
    f:flush()

    local replay = {
        _file = f,
        _filepath = filepath,
        _header = header,
        _current_frame = 0,
        _frame_buffer = {},   -- 帧数据缓冲（攒够后批量写入）
        _buffer_count = 0,
        _max_buffer_size = 60, -- 每 60 帧写入一次
        _closed = false,
    }
    setmetatable(replay, ReplayManager)
    return replay
end

--- 写入一帧的指令数据
--- @param commands table 指令列表，每项 {player_id=, cmd_type=, data=string}
function ReplayManager:write_frame(commands)
    if self._closed then
        error("Replay already closed")
    end

    -- 构建帧数据字节串
    -- 格式: [frame_number:u16][flags:u16][cmd_count:u8][cmd₀][cmd₁]...
    local parts = {}

    -- 帧号（u16, 小端）
    parts[#parts + 1] = string.pack("<I2", self._current_frame)

    -- 标志位（u16, 小端）：Bit 0 = 是否关键帧
    local flags = (self._current_frame % 600 == 0) and 1 or 0
    parts[#parts + 1] = string.pack("<I2", flags)

    -- 指令数量（u8）
    local cmd_count = #(commands or {})
    parts[#parts + 1] = string.char(cmd_count)

    -- 逐指令序列化
    for _, cmd in ipairs(commands or {}) do
        parts[#parts + 1] = string.pack("<I2", cmd.player_id or 0)
        parts[#parts + 1] = string.char(cmd.cmd_type or 0)
        local data = cmd.data or ""
        parts[#parts + 1] = string.char(#data) -- 数据长度
        parts[#parts + 1] = data
    end

    self._frame_buffer[#self._frame_buffer + 1] = table.concat(parts)
    self._buffer_count = self._buffer_count + 1
    self._current_frame = self._current_frame + 1

    -- 缓冲区满 → 批量写入
    if self._buffer_count >= self._max_buffer_size then
        self:flush()
    end
end

--- 刷新缓冲区到文件
function ReplayManager:flush()
    if self._buffer_count == 0 then return end

    local data = table.concat(self._frame_buffer)
    self._file:write(data)
    self._file:flush()

    -- 清空缓冲区
    self._frame_buffer = {}
    self._buffer_count = 0
end

--- 关闭录像文件，回填总帧数
--- @param total_frames number|nil 总帧数（nil 时使用当前计数）
function ReplayManager:close(total_frames)
    if self._closed then return end
    self._closed = true

    self:flush()

    local tf = total_frames or self._current_frame

    -- 回填头部中的 total_frames 字段（offset 16: magic:4 + version:2 + flags:2 + seed:4 + fps:4）
    self._file:seek("set", 16)
    self._file:write(string.pack("<I4", tf))

    self._file:close()
    self._file = nil

    return self._filepath
end

-- ============================================================
-- 录像列表管理
-- ============================================================

--- 扫描目录获取所有录像文件的元数据
--- @param directory string 录像文件所在目录
--- @param max_count number|nil 最多返回数量（nil=全部）
--- @return table 元数据数组，按文件修改时间降序排列（最新的在前）
function ReplayManager.list_replays(directory, max_count)
    local replays = {}

    -- 遍历目录下所有 .gznr 文件
    local lfs = require("lfs") -- LuaFileSystem
    for file in lfs.dir(directory) do
        if file:match("%.gznr$") then
            local filepath = directory .. "/" .. file
            local meta, err = ReplayManager.extract_metadata(filepath)
            if meta then
                -- 附加文件系统信息
                local attr = lfs.attributes(filepath)
                meta.file_size = attr and attr.size or 0
                meta.modified = attr and attr.modification or 0
                meta.filename = file
                replays[#replays + 1] = meta
            end
        end
    end

    -- 按修改时间降序
    table.sort(replays, function(a, b)
        return (a.modified or 0) > (b.modified or 0)
    end)

    -- 截断
    if max_count and #replays > max_count then
        local truncated = {}
        for i = 1, max_count do
            truncated[i] = replays[i]
        end
        return truncated
    end

    return replays
end

--- 自动清理旧录像（保留最近 N 个）
--- @param directory string 录像目录
--- @param keep_count number 保留数量
--- @return number 删除的文件数量
function ReplayManager.cleanup_old_replays(directory, keep_count)
    local replays = ReplayManager.list_replays(directory)
    local deleted = 0

    -- 超过 keep_count 的部分删除
    for i = keep_count + 1, #replays do
        local ok, err = os.remove(replays[i].filepath)
        if ok then
            deleted = deleted + 1
        else
            -- 静默忽略删除失败（可能被其他进程占用）
        end
    end

    return deleted
end

--- 获取录像总存储大小
--- @param directory string 录像目录
--- @return number 总大小（字节）
function ReplayManager.get_total_size(directory)
    local total = 0
    local replays = ReplayManager.list_replays(directory)
    for _, r in ipairs(replays) do
        total = total + (r.file_size or 0)
    end
    return total
end

-- ============================================================
-- 回放加载器
-- ============================================================

--- 打开现有录像文件准备回放
--- @param filepath string 录像文件路径
--- @return table|nil 回放句柄
--- @return string|nil 错误信息
function ReplayManager.open_replay(filepath)
    local meta, err = ReplayManager.extract_metadata(filepath)
    if not meta then
        return nil, err
    end

    local f, ferr = io.open(filepath, "rb")
    if not f then
        return nil, "Failed to open: " .. (ferr or "unknown")
    end

    -- 跳过头部 (HEADER_SIZE 字节)
    -- 实际上不同玩家数量的录像头部大小不同，需要精确跳过
    -- 简化实现：用实际头部数据偏移 = 24 + player_count * 74 (64name+2*4+1+1)
    local header_data_size = 24 + meta.player_count * 74
    f:seek("set", header_data_size)

    local replay = {
        _file = f,
        _filepath = filepath,
        _meta = meta,
        _current_frame = 0,
        _closed = false,
    }
    setmetatable(replay, ReplayManager)
    return replay
end

--- 从回放文件中读取下一帧的指令
--- @return table|nil 帧数据 {frame_number=, flags=, commands=}
function ReplayManager:read_frame()
    if self._closed then return nil end

    local f = self._file
    -- 读取帧头
    local header = f:read(4)
    if not header or #header < 4 then return nil end

    local frame_num = string.unpack("<I2", header:sub(1, 2))
    local flags = string.unpack("<I2", header:sub(3, 4))

    -- 检查是否快照标记
    if frame_num == 0xFFFF then
        -- 跳过快照数据：读长度
        local snap_len_bytes = f:read(4)
        if not snap_len_bytes or #snap_len_bytes < 4 then return nil end
        local snap_len = string.unpack("<I4", snap_len_bytes)
        f:read(snap_len) -- 跳过快照数据
        return self:read_frame() -- 递归读下一帧
    end

    -- 读取指令数量
    local cmd_count_byte = f:read(1)
    if not cmd_count_byte then return nil end
    local cmd_count = cmd_count_byte:byte()

    -- 读取指令
    local commands = {}
    for i = 1, cmd_count do
        local cmd_header = f:read(4) -- pid:2 + type:1 + len:1
        if not cmd_header or #cmd_header < 4 then break end

        local pid = string.unpack("<I2", cmd_header:sub(1, 2))
        local cmd_type = cmd_header:sub(3, 3):byte()
        local data_len = cmd_header:sub(4, 4):byte()

        local data = ""
        if data_len > 0 then
            data = f:read(data_len) or ""
        end

        commands[i] = {
            player_id = pid,
            cmd_type = cmd_type,
            data = data,
        }
    end

    self._current_frame = frame_num
    return {
        frame_number = frame_num,
        flags = flags,
        commands = commands,
    }
end

--- 关闭回放文件
function ReplayManager:close_replay()
    if self._closed then return end
    self._closed = true
    if self._file then
        self._file:close()
        self._file = nil
    end
end

-- ============================================================
-- 使用示例
-- ============================================================
--
-- -- 创建录像
-- local writer, err = ReplayManager.create_replay("replays/match_001.gznr", {
--     version = 0x0100,
--     seed = 12345,
--     logic_fps = 15,
--     players = {
--         { player_id = 1, team_id = 0, hero_id = 105, name = "PlayerA", skin_id = 0 },
--         { player_id = 2, team_id = 1, hero_id = 201, name = "PlayerB", skin_id = 1 },
--     }
-- })
--
-- -- 每帧写入指令
-- for frame = 0, 27000 do
--     local cmds = collect_player_inputs(frame) -- 从网络层收集输入
--     writer:write_frame(cmds)
-- end
-- writer:close()
--
-- -- 列出所有录像
-- local replays = ReplayManager.list_replays("replays/")
-- for i, r in ipairs(replays) do
--     print(string.format("[%d] %s | %d frames | %.1f min",
--         i, r.filename, r.total_frames, r.duration_sec / 60))
-- end
--
-- -- 回放
-- local reader, err = ReplayManager.open_replay("replays/match_001.gznr")
-- while true do
--     local fd = reader:read_frame()
--     if not fd then break end
--     logic_engine:execute_frame(fd.commands)
-- end
-- reader:close_replay()

return ReplayManager
```

---

## 5. 业界录像系统分析

### 5.1 王者荣耀：纯指令录像

**技术栈**：帧同步 + 指令录像 + 服务端存储

王者荣耀的录像系统是帧同步录像的教科书级实现：

```
客户端（每帧）:
  1. 收集本地玩家输入
  2. 发送输入到服务器
  3. 收到服务器广播的所有玩家输入
  4. 执行逻辑
  5. 将输入追加到本地录像文件 ← 同一份数据！

服务器：
  - 仅做转发（不跑逻辑）
  - 可选：保存录像用于反外挂分析
```

**核心设计决策**：

| 决策 | 选择 | 原因 |
|------|------|------|
| 录像存储位置 | 客户端本地 + 服务端可选上传 | 最终由客户端生成，无需服务端跑逻辑 |
| 文件大小 | ~100KB（30分钟） | 指令序列天然极小 |
| 视角支持 | 完整自由视角 + 任意玩家切换 | 全量状态在客户端内存 |
| 版本兼容 | 严格版本锁定，跨版本不可播 | 需要完全相同的逻辑代码 |
| 分享 | 通过社交平台或直接传文件 | <1MB，分享零成本 |

**王者荣耀观战系统的工作流**：

```
玩家A 对局 → 本地生成录像 → 上传到王者服务器
                                  │
                    ┌─────────────┘
                    ↓
            观战者客户端下载录像 → 本地回放（延迟观战）
            或
            实时观战：服务器直接转发每帧指令给观战者
```

王者荣耀的"王者时刻"（高光集锦）也是基于录像数据分析自动生成的——系统分析录像中的击杀事件、多杀、关键团战，自动裁剪生成短视频。

### 5.2 守望先锋：状态同步 + 关键帧录像

守望先锋（Overwatch）使用状态同步架构（权威服务器），录像系统与之对应地使用**定期状态快照**。

**核心机制**：

```
服务端 Tick (64Hz):
  ┌─ 收集输入
  ├─ 权威逻辑（命中判定、技能、伤害）
  ├─ 更新所有实体状态
  ├─ IF (tick % 16 == 0):  ← 每 16 tick (~250ms) 存快照
  │   序列化全量实体状态 → 录像缓冲
  └─ 广播状态给客户端
```

**"全场最佳"（Play of the Game）的生成**：

守望先锋的 POTG 系统在服务端运行，分析录像数据：
1. 每局结束后遍历录像中的"事件点"（击杀、大招使用、多重击杀）
2. 对每个事件点打分：击杀价值 + 技能使用质量 + 时间窗口内的连续表现
3. 选取得分最高的一段（约 12 秒），渲染生成 POTG 回放
4. 将 POTG 发送给所有客户端

**精彩回放（Highlight）系统**：OW2 允许玩家在"生涯概况"中查看历史对局的完整回放。这些回放文件存储在服务端，玩家可以随时下载观看。

### 5.3 英雄联盟：混合录像方案

英雄联盟的录像系统介于两种纯方案之间。

**架构**：

```
对局开始时:
  服务器保存初始状态快照 S₀
  客户端也在本地录制（但以服务端录像为准）

每 Tick (30Hz):
  服务器记录：
    - 所有玩家的输入指令（类似帧同步）
    - 关键事件日志（击杀、推塔、大龙/小龙）

回放时:
  1. 加载 S₀
  2. 使用确定性逻辑逐帧执行指令
  3. 关键事件用于快速跳转定位
```

LoL 的 Replay 文件（`.rofl` 格式）实际上是一个经过加密/压缩的指令流，回放时必须使用**同一版本的游戏客户端**。这也是为什么 LoL 版本更新后旧录像经常无法播放——逻辑代码变了，确定性不成立。

LoL 在 2018 年引入了"回放高光时刻"功能（类似 OW 的 POTG），在本地分析录像，自动标记击杀和团战时刻。

### 5.4 三款游戏对比总结

| 维度 | 王者荣耀 | 守望先锋 | 英雄联盟 |
|------|---------|---------|---------|
| 同步架构 | 帧同步 | 状态同步 | 帧同步 |
| 录像类型 | 纯指令 | 周期性状态快照 | 指令 + 事件日志 |
| 典型大小(30min) | ~100KB | ~5-10MB | ~5-15MB |
| 快进性能 | 需重算（慢） | 瞬间跳转 | 需重算但有事件锚点 |
| 自由视角 | 是（天然） | 受限于快照精度 | 是（天然） |
| 服务端录制 | 可选 | 强制 | 强制 |
| 跨版本回放 | 否 | 是 | 否 |
| 精彩集锦 | 自动生成（客户端） | 服务端 POTG | 客户端高光标记 |

---

## 6. 练习

### 练习 1：基础 —— 实现一个简单的帧同步录像 Writer

**目标**：实现一个命令行 C# 程序，模拟帧同步对局的录像写入过程。

**要求**：
1. 定义录像头部结构（魔数、版本、随机种子、玩家信息）
2. 模拟 500 帧的逻辑循环（15Hz = 约 33 秒对局），每帧随机生成 2~5 条玩家指令
3. 将每条指令和帧数据写入二进制文件
4. 对局结束时写入尾部标记
5. 输出录像文件大小

**期望输出**：
```
Replay file: test_replay.gznr
Frames written: 500
Total commands: 1742
File size: 23,456 bytes
```

**提示**：
- 使用 `BinaryWriter` 进行序列化
- 指令可以简化为 `{ playerId: uint16, cmdType: uint8, param1: float, param2: float }`
- 不需要实现压缩（进阶再加）

### 练习 2：进阶 —— 实现录像回放器 + 快进功能

**目标**：基于练习 1 写入的录像文件，实现完整回放器，支持播放/暂停/快进。

**要求**：
1. 解析录像文件头部，提取随机种子和玩家信息
2. 逐帧读取指令并模拟"执行"（打印到控制台即可，不需要真正的游戏逻辑）
3. 实现 `SeekTo(frame)` 方法：跳转到指定帧
4. 实现 `FastForward(frames)` 方法：跳过 N 帧不打印，只计时性能
5. 比较正常播放和跳帧执行的性能差异

**期望输出**：
```
Loading replay: test_replay.gznr (500 frames, 33.3s, 4 players)
Playing at 1x speed...
[Frame 0] P1:move P2:attack P3:skill P4:move
[Frame 1] P1:move P2:move
...
FastForward(300 frames):  executed in 2.3ms (130,434 fps equivalent)
Now at frame 350
```

### 练习 3：挑战 —— Desync 诊断工具

**目标**：实现一个简单的 Desync 诊断工具，比对两份"相同对局"的不同客户端录像。

**场景**：帧同步对局中，客户端 A 和客户端 B 都录制了录像。但客户端 A 声称"第 842 帧我杀了 B"，B 声称"第 842 帧我没死"。请编写工具找出真正产生分歧的帧。

**要求**：
1. 加载两份录像文件
2. 逐帧比对它们的状态 Hash（模拟：每帧计算一个 `hash = seed ^ frameNum ^ cmdCount`）
3. 找到第一帧 Hash 不一致的位置
4. 输出不一致的帧号及两侧 Hash 值
5. 输出"分歧前最后一帧"的指令内容

**输入**：两份由练习 1 生成的录像文件，其中一份在第 400 帧人为插入一条不同的指令。

**期望输出**：
```
Loading replay_a.gznr... 500 frames
Loading replay_b.gznr... 500 frames
Comparing frame-by-frame...
  Frame 399: OK (hash_a=0xABCD1234, hash_b=0xABCD1234)
  Frame 400: DESYNC DETECTED!
    Replay A: hash=0xDEAD0001, 5 commands
      P1:move(100,200) P2:attack(P1) P3:skill(1,300,400)
    Replay B: hash=0xBEEF0002, 5 commands
      P1:move(100,200) P2:attack(P3) P3:skill(1,300,400)
                  ↑ 攻击目标不同！
Last synced frame: 399
  Commands: P1:move(95,190) P2:idle
```

**进阶**：实现一个简单的"状态 Diff"——假设每个实体有 `{id, pos_x, pos_y, hp}` 四个字段，比对第 400 帧两个录像中各实体的状态差异。

---

## 7. 扩展阅读

- **GGPO Rollback Networking**：[GGPO.net](https://www.ggpo.net/) — 格斗游戏网络库。其中的"预测回滚"机制与录像的"快照 + 回滚"思路同源。
- **星际争霸 2 Replay 格式分析**：[sc2replay.net](https://sc2replay.net/) — 社区对 SC2 录像（`.SC2Replay`）格式的逆向分析。
- **Dota 2 Replay Parser**：[Clarity](https://github.com/skadistats/clarity) — Java 库，解析 Dota 2 的 `.dem` 录像文件。Dota 2 使用 Source 2 引擎，录像包含完整的实体更新流。
- **CS:GO Demo 分析**：CS:GO 使用 Source 引擎的 Demo 系统。`.dem` 文件实际上是完整的网络包记录（Packet Capture），回放时作为"网络包"重新喂给客户端。
- **UE5 Iris Replay System**：UE5 的 Iris 复制系统内置了 Replay 支持——它利用与网络复制相同的序列化路径，将服务器状态快照写入文件。
- **王者荣耀录像逆向**：社区对 `.wzryrec` 格式的逆向分析可以帮助理解实际帧同步录像的实现细节。

---

## 常见陷阱

1. **浮点数不一致导致的录像 Divergence**
   即使录像录入了相同的指令序列，如果回放环境的浮点运算模式不同（如 x87 vs SSE、不同编译器优化级别），累积误差可能在数千帧后导致完全不同的游戏状态。解决方案：录像中存储定点数状态的关键帧快照，回放时以此为锚点纠正漂移。

2. **录像文件版本不匹配**
   游戏更新后，逻辑代码变了，旧录像无法回放。这是帧同步录像最大的工程痛点。缓解策略：a) 保留所有历史版本的游戏逻辑 DLL，回放时动态加载对应版本（类似 Wine 的多版本兼容方案）；b) 使用混合录像方案，关键帧快照确保跨版本可读（牺牲部分精确性）。

3. **压缩与随机访问的矛盾**
   录像文件压缩得越好，随机访问（拖进度条）越慢。不能既压缩到极致又随时跳转到任意帧。解决方案：分块压缩（每 500 帧一个独立压缩块），跳转时只需解压目标块。

4. **内存中的全量回放**
   帧同步回放需要在内存中保持全量游戏状态。一场 MOBA 可能涉及数百个实体、数千个技能效果。确保回放时的内存预算与正常对局相同，不要在回放时开启不必要的系统（如完整 AI、网络模块）。

5. **录制时忘记保存随机种子**
   录像回放需要精确的随机种子。如果在录制时遗漏了种子，回放时使用默认种子（或随机种子），RNG 序列将完全不同——第一帧扔骰子不一样，后面全部不一样。解决方案：在对局初始化时，服务器生成种子并下发给所有客户端，录像头部必须包含此种子。

6. **服务器 Tick Rate 与录像帧率不匹配**
   状态同步录像的快照间隔如果与服务器 Tick Rate 同步不好（如 60Hz Tick 但每 50 Tick 拍一次快照），回放时会出现明显的"步进"感。建议快照间隔等于 Tick Rate 的整数倍（如每 64 Tick = 约 1 秒 @64Hz）。

7. **录像文件损坏后的恢复**
   帧同步录像如果在中间某处损坏（如写入时崩溃），从损坏点之后的所有帧都无法读取。解决方案：a) 定期在文件中插入"同步标记"（Sync Marker），扫描受损文件时可以跳到最近标记恢复；b) 双缓冲写入 + OSync 确保写入完整性。
