---
title: "断线重连与中途加入"
updated: 2026-06-05
---

# 断线重连与中途加入

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [[12-lockstep-advanced|12-帧同步进阶]], [[17-lag-compensation|17-延迟补偿]]

---

## 1. 概念讲解

### 1.1 为什么需要断线重连与中途加入？

在网络游戏的五个核心服务质量指标中，"连接稳定性"往往是玩家感知最强烈的：

| 场景 | 玩家体验 | 无重连系统的后果 |
|------|---------|----------------|
| WiFi 切换（4G ↔ WiFi） | 2~5 秒断线 | 直接被踢出对局，扣分 |
| 电梯/隧道/地库 | 5~30 秒断线 | 对局终止，全队 4v5 |
| 接电话/切后台 | 10~120 秒断线 | 被判定逃跑，信誉分降 |
| 中途加入（好友邀请） | 对局已进行 5 分钟 | 看不到就开始，无法加入 |
| 服务器重启/迁移 | 全局断线 3~8 秒 | 所有玩家对局丢失 |

**核心矛盾**：游戏是实时/准实时的，网络是不可靠的。断线重连的本质是**在不可靠的网络上维护一个可靠的会话状态**。

> **面试要点**：面试官问"你们的游戏怎么处理断线？"，不要只回答"有个重连按钮"。要从分级策略说起——瞬时抖动（冗余指令填充）、短时断线（帧追赶加速）、长时断线（完整状态恢复），不同时长不同策略。

### 1.2 断线重连的核心挑战全景图

```
┌──────────────────────────────────────────────────────────────────────┐
│                       断线重连三大核心挑战                              │
├──────────────────┬───────────────────┬───────────────────────────────┤
│   状态恢复        │    帧追赶          │    RTT 波动                    │
│   (State Recov)  │   (Frame Catchup)  │   (RTT Jitter)                │
├──────────────────┼───────────────────┼───────────────────────────────┤
│ • 恢复哪些状态？  │ • 追赶多少帧？     │ • 重连后立即面对高 RTT         │
│ • 状态的时间戳？  │ • 追赶速度上限？   │ • 追赶时 RTT 不降反升          │
│ • 增量 vs 全量？  │ • 追赶期交互策略？ │ • 如何区分断线还是高延迟？      │
│ • Spawn/Despawn? │ • 逻辑 vs 渲染追赶？│ • 断线检测阈值如何设定？       │
└──────────────────┴───────────────────┴───────────────────────────────┘
```

### 1.3 分级处理策略总述

断线不是"0 或 1"的状态，而是持续时长决定处理策略：

```
断线时长        名称          RTT 表现          处理策略
─────────────────────────────────────────────────────────────────
< 500ms         微抖动       偶尔丢 1-2 个包     无需处理,UDP冗余包覆盖
500ms~2s        瞬时断线     连续丢包+心跳超时    冗余指令填充+空操作
2s~10s          短时断线     长间隙+缓冲区堆积    快照恢复+帧追赶加速
10s~60s         长时断线     连接断开+TCP重连      全量状态同步/完整重连
> 60s           超长断线     可能永久离线          踢出对局+AI托管
```

**核心设计原则——"断线容忍窗口"**：
- 每个游戏有自己的"容忍窗口"（通常 5~15 秒）
- 窗口内：服务端保持玩家状态，用空操作填充，等待重连
- 窗口外：服务端判定玩家永久离线，释放资源，通知其他玩家
- 重连请求到达时：如果窗口期内 → 快速恢复；窗口期外 → 拒绝/投票

---

## 2. 帧同步的断线重连

### 2.1 快照恢复法 (Snapshot Recovery)

帧同步的独特优势：**游戏状态是对输入序列的确定性推演**。因此重连的核心思路是：

> 断线玩家不需要完整的状态数据——只需要"某一帧的完整状态快照" + "从那一帧之后的所有输入序列"。

```
帧同步重连流程图:

客户端断线                   服务端
    │                          │
    │   心跳超时检测到断线       │
    │                          │ 标记玩家为"断线中"
    │                          │ 开始用空操作填充此玩家的帧位
    │                          │ 持续缓存已广播的帧包到环形缓冲区
    │                          │
    │◄──网络恢复,TCP重连────────│
    │                          │
    │ 发送重连请求               │
    │ {playerId, lastAckFrame} │
    │─────────────────────────►│
    │                          │ 1. 从环形缓冲区查找 lastAckFrame
    │                          │    之后的快照 S_k
    │                          │ 2. 发送: 快照S_k + 帧包[K+1..N]
    │◄─────────────────────────│
    │                          │
    │ 1. 加载快照S_k作为起点     │
    │ 2. 从K+1帧开始逐帧重放    │
    │ 3. 加速模拟(4x~8x)        │
    │ 4. 追到当前帧N→正常播放    │
```

**快照数据结构**：

快照不是简单的"所有实体的位置"——帧同步的快照必须包含游戏的全部**逻辑状态**。遗漏任何一个非渲染字段都会导致后续追帧偏离确定性。

```csharp
// 快照的最小必要字段集合
public class GameSnapshot
{
    public uint FrameNumber;
    // 所有逻辑实体的完整状态（排序确保确定性）
    public EntityState[] Entities;
    // 随机数生成器状态（关键！漏掉这个 = 后续所有随机事件偏离）
    public ulong[] RngStates;
    // 全局计时器/冷却状态
    public uint GameTimeMs;
    public int[] TeamScores;
    // 技能系统全局状态
    public uint[] GlobalCooldowns;
    // 注意：不包含渲染状态（动画帧、粒子、UI等）
}
```

**为什么随机数生成器状态必须保存？**

帧同步的确定性依赖输入确定性和随机数确定性的双重保证。如果断线恢复时 RNG 状态未被保存，重连者从快照帧之后生成的"随机"数值会与在线玩家不一致，导致蝴蝶效应式的 desync。

典型场景：第 500 帧被暴击判定为真（RNG 消耗了一次随机数），第 505 帧玩家断线。追帧到 550 帧时又遇到暴击判定——如果 RNG 状态不正确，这里的暴击结果会与在线玩家不同。

### 2.2 帧追赶 (Frame Catchup)

帧追赶是重连中最耗时的阶段。核心问题：**追赶速度的上限在哪里？**

```
假设: 逻辑帧率 15fps（66ms/帧），断线 5 秒，丢失 75 帧
     正常速度追赶: 75 × 66ms = 5 秒  ← 等到追完，其他玩家又推进了 5 秒
     4x 加速追赶: 75 × 66ms/4 = 1.25 秒 ← 可接受
     8x 加速追赶: 75 × 66ms/8 = 0.62 秒 ← 很快，但...
```

**追赶速度的硬上限**：CPU 单帧能塞入多少逻辑帧。

在移动端（如王者荣耀），一轮逻辑更新（66ms 内有 1 帧逻辑+渲染）时，CPU 预算约 16ms 给逻辑。如果用 1ms 跑一帧逻辑，理论最大追赶倍数是 66x。但实际情况：

- 移动端发热：超过 8x 持续追赶会触发温控降频
- 网络缓冲：追赶期间收到的"直播帧"需要缓存，内存压力增大
- 渲染分离：追赶时**不需要渲染**——跳过所有图形管线

**追帧的优化策略——"只追逻辑，不追渲染"**：

```csharp
// 追赶模式下的帧循环
while (chasingFrame < serverLatestFrame)
{
    // 执行逻辑帧（核心耗时）
    ExecuteOneLogicFrame(inputs[chasingFrame]);
    chasingFrame++;

    // 跳过渲染：不更新 Transform、不提交 Draw Call、不播放特效
    // 只在追赶结束后的第一帧做一次"状态快照→渲染同步"

    // 每 10 个逻辑帧检查一次是否追到最新
    if (chasingFrame % 10 == 0 && chasingFrame >= serverLatestFrame)
        break;
}
// 追赶完成：将逻辑状态一次性同步到渲染层
SyncLogicToRender();
```

### 2.3 王者荣耀重连方案

王者荣耀是帧同步重连的经典案例。其完整方案可概括为：

```
┌─────────────────────────────────────────────────────────────┐
│                  王者荣耀断线重连架构                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  服务端                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  帧包环形缓冲区 (最近 600 帧 ≈ 40 秒)                  │   │
│  │  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐  │   │
│  │  │帧100│帧101│ ... │帧300│ ... │帧699│ ... │帧699│  │   │
│  │  └─────┴─────┴─────┴─────┴──▲──┴─────┴─────┴─────┘  │   │
│  │                             │                        │   │
│  │                    当前广播帧 = 500                   │   │
│  │                    重连请求说 lastAck = 300          │   │
│  │                    需要发送: 300到500的200个帧包      │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  客户端                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. 接收帧包 [300..500] 共 200 帧                     │   │
│  │  2. 这些帧包中已经包含所有玩家的输入（被打包好了）     │   │
│  │  3. 从帧 300 的快照开始，逐帧执行逻辑                  │   │
│  │  4. 加速追赶: 逻辑 8x 速度，跳过渲染                   │   │
│  │  5. 追赶期间: 将玩家操作缓存，但不发送                 │   │
│  │  6. 追到帧 500: 开始正常游戏，立即发送缓存的操作     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**为什么王者荣耀不需要单独的快照？**

王者的帧包设计已经内置了"状态的快照功能"：每个帧包携带的是"所有玩家在这一帧的输入"。由于游戏是确定性的，给你所有输入就等于给了你恢复完整状态的能力（只要从一个确定起点开始）。唯一需要额外保存的是 RNG 状态——王者荣耀的做法是每 150 帧（约 10 秒）做一次 RNG 快照并随帧包附带。

**但这里有一个微妙之处**：如果断线发生在第 1 帧和第 300 帧之间，服务端需要传输 300 个帧包。每个帧包约 50~100 字节，300 帧 ≈ 15~30KB——这完全可以接受。但如果对局已进行 15 分钟（约 13500 帧），不可能全量重传。这就是为什么服务端的帧包环形缓冲区只保留约 40 秒（600 帧）——**重连只支持最近 40 秒内的断线**。

### 2.4 追赶期间的玩家操作

追赶期间，玩家并非"什么都做不了"。核心策略有两种：

**策略 A：完全忽略（王者荣耀采用）**

```
追赶期间（假设 1.5 秒）:
  - 玩家的屏幕显示"重连中..." + 进度条
  - 所有触屏事件被吞掉，不产生任何输入
  - 追完后，玩家的第一帧操作从当前帧开始
  - 优点: 简单、不会导致逻辑混乱
  - 缺点: 玩家在追赶期间"失去控制" 1.5 秒
```

**策略 B：缓存后发送**

```
追赶期间（假设 1.5 秒）:
  - 玩家可以操作（但看不到结果，因为在追赶中）
  - 操作被缓存在 InputBuffer 中
  - 追完后，将缓存的输入一次性发送给服务器
  - 服务器将这些输入填入"未来帧"的空操作槽位
  - 优点: 追赶期间玩家不感到"失控"
  - 缺点: 延迟了实际生效时间，可能产生"操作不跟手"的感觉
```

**实际工程中的选择**：因为追帧通常只需要 0.5~2 秒，且追帧期间画面是冻结/黑屏的（玩家看不到游戏世界，操作也是盲操作），所以多数产品选择策略 A（完全忽略）。但策略 B 在"追赶时间较长（>3s）且屏幕显示追赶进度条不黑屏"的场景下有优势。

---

## 3. 状态同步的断线重连

### 3.1 全量状态同步 (Full State Sync)

状态同步中，服务端是权威状态持有者。重连的核心思路完全不同：

> 服务端将当前世界的所有实体状态一次性打包发送给重连客户端。客户端收到后直接"跳"到最新状态，不需要模拟任何帧。

```
全量状态同步流程:

客户端发送重连请求
      │
      ▼
服务端处理:
  1. 冻结玩家在世界的输入（短暂暂停此玩家的模拟）
  2. 遍历所有相关实体，序列化状态
  3. 打包: {Entities[], GameTime, Scores, ...}
  4. 发送全量快照包（可能达到数十KB）
      │
      ▼
客户端接收:
  1. 清空本地所有实体状态
  2. 反序列化 → 创建/更新实体
  3. 同步渲染层
  4. 开始接收增量更新
```

**全量快照的数据结构**：

```cpp
// 状态同步重连: 全量世界快照
struct WorldSnapshot {
    uint32_t serverTick;          // 快照对应的服务器 tick
    float    gameTime;            // 游戏时间（秒）

    // 所有活跃实体的完整状态
    struct EntityEntry {
        uint32_t entityId;
        uint32_t prefabId;        // 实体类型（用于客户端创建GameObject）
        uint8_t  ownerPlayerId;   // 所属玩家（用于权限判定）

        // 变换
        float posX, posY, posZ;
        float rotX, rotY, rotZ, rotW;  // 四元数

        // 物理
        float velX, velY, velZ;
        float angVelX, angVelY, angVelZ;

        // 游戏状态（可变长度）
        uint16_t stateBytesLen;
        uint8_t  stateBytes[];    // 协议缓冲区: HP, buffs, cooldowns...

        // 注意: 不包括只在客户端存在的渲染状态
        // （动画播放进度、粒子系统等——这些可以丢失，客户端重新播放）
    };
    uint16_t entityCount;
    EntityEntry entities[];

    // 全局状态
    int32_t teamScores[2];
    float   matchTimeRemaining;
    // ... 其他全局状态
};
```

**全量同步的优缺点**：

| 优点 | 缺点 |
|------|------|
| 实现简单，不依赖历史数据 | 带宽消耗大，一包可达 50~200KB |
| 不依赖帧同步的确定性假设 | 大包可能分片，增加延迟 |
| 客户端逻辑简单（清空→重建） | 创建/销毁实体时可能产生 GC 抖动 |
| 适用于任意时长的断线 | 实体多的游戏（MMO）不可行——需要增量 |

### 3.2 增量重连 (Delta Reconnect)

对于实体数量极大的游戏（MMO、大逃杀），全量同步的带宽不可接受。增量重连的核心思想：

> 服务端记录断线玩家"最后一次确认收到的时间点"。重连时，只发送从那个时间点之后发生的变化。

```
增量重连的数据包:

DeltaReconnectPacket {
    uint32_t lastAckedTick; // 客户端上次确认的服务器 tick

    // 需要创建的实体（断线期间新刷新的）
    EntityEntry[] spawnedEntities;

    // 需要更新的实体（断线期间状态变化的）
    EntityDelta[] updatedEntities;

    // 需要销毁的实体（断线期间被杀掉/消失的）
    uint32_t[] despawnedEntityIds;

    // 全局状态增量
    int32_t scoreDelta;
    // ...
}
```

**增量重连的实现前提**：服务端需要维护每个玩家最近确认的 tick 号，以及每个 tick 的"世界变化日志"（Change Log）。

```cpp
// 服务端的变化日志系统
class WorldChangeLog {
    struct TickChanges {
        uint32_t tick;
        std::vector<uint32_t> spawnedIds;
        std::vector<uint32_t> despawnedIds;
        std::vector<std::pair<uint32_t, EntityDelta>> entityDeltas;
    };

    // 环形缓冲区: 保留最近 N 秒的变化记录
    static constexpr size_t BUFFER_SIZE = 600; // 10秒 @ 60 tick/s
    TickChanges buffer_[BUFFER_SIZE];
    size_t head_ = 0;

public:
    void RecordSpawn(uint32_t tick, uint32_t entityId) {
        buffer_[tick % BUFFER_SIZE].spawnedIds.push_back(entityId);
    }

    void RecordDespawn(uint32_t tick, uint32_t entityId) {
        buffer_[tick % BUFFER_SIZE].despawnedIds.push_back(entityId);
    }

    void RecordDelta(uint32_t tick, uint32_t entityId, const EntityDelta& delta) {
        buffer_[tick % BUFFER_SIZE].entityDeltas.emplace_back(entityId, delta);
    }

    // 重连时: 从lastAckedTick到currentTick的所有变化合并
    ReconnectData CompileReconnectData(uint32_t lastAckedTick, uint32_t currentTick) {
        // ...合并所有 tick 的变化，去重（同一实体的多个 delta 合并为最新值）
    }
};
```

### 3.3 Spawn/Despawn 事件补发

这是增量重连中**最容易被忽视但最容易出 Bug** 的部分。

**问题场景**：
```
Tick 100: 玩家断线
Tick 150: 服务器刷新了一波小兵 (entityId=2001~2006, spawn)
Tick 180: 小兵 2003 被击杀 (despawn)
Tick 200: 玩家重连

增量同步时，如果只发送"当前存在的实体"列表:
  - 客户端永远不知道 2003 曾经存在过
  - 计分板上的击杀数可能少 1
  - 如果有任务系统依赖"你击杀过小兵"，任务进度会错
```

**Spawn/Despawn 补发协议**：

```cpp
// 断线期间的所有 Spawn/Despawn 事件（按时间排序）
struct SpawnDespawnLog {
    uint32_t tick;
    enum EventType : uint8_t { SPAWN = 0, DESPAWN = 1, TRANSFER = 2 };
    EventType eventType;
    uint32_t entityId;
    uint32_t prefabId;      // 仅 SPAWN 需要
    uint32_t killerId;      // 仅 DESPAWN 需要
    uint32_t newOwnerId;    // 仅 TRANSFER（实体所有权转移）需要
};

// 重连时补发
ReconnectPacket {
    WorldSnapshot fullSnapshot;           // 当前所有活跃实体
    SpawnDespawnLog[] missedEvents;      // 断线期间错过的事件
};
```

> **面试要点**：问 "状态同步的断线重连和帧同步有什么本质区别？" —— 帧同步重连靠的是"输入回放 + 确定性"，状态同步重连靠的是"服务端权威状态的直接下发"。前者带宽小（只传输入序列）但需要客户端跑逻辑追赶，后者带宽大但客户端可以瞬间恢复。

---

## 4. 中途加入 (Late Join)

### 4.1 帧同步的中途加入

帧同步的中途加入比断线重连多一个挑战：**加入者从未拥有过任何游戏状态**。

```
标准流程:
  1. 新客户端连接到服务器
  2. 服务器发送: 当前帧快照 S_current + 帧包缓冲区 [0..current]
  3. 客户端从帧 0 开始追帧（4x~8x 加速），直到追到 current
  4. 开始正常游戏

优化流程（如果对局已进行很久）:
  1. 服务器每 300 帧创建一个"中途加入快照"（包含完整状态+RNG状态）
  2. 新客户端请求最近的中途加入快照 S_k
  3. 从帧 K 开始追帧到 current（而非从帧 0）
  4. 大幅减少追帧时间
```

**中途加入快照的生成时机**：不是每个帧都做（太耗内存），而是固定的 snapshot interval（如每 300 帧 ≈ 20 秒）。这意味中途加入者最多需要追 300 帧（约 1~3 秒 @ 8x 速度）。

### 4.2 状态同步的中途加入

状态同步的中途加入相对简单：

```
流程:
  1. 新客户端连接 → 请求加入
  2. 服务器: 发送全量世界快照
  3. 客户端: 创建所有实体 → 同步渲染层
  4. 开始接收增量更新
```

但需要注意以下边界情况：

**动态对象池问题**：

服务端的实体使用对象池管理。如果客户端按"当前活跃实体列表"创建实体，而某些实体在服务器上是从对象池中复用的（entityId 不变但 prefabId 变了），客户端可能创建出错误的实体类型。

```
解决方案:
  - 全量快照中始终携带 prefabId（而不依赖 entityId 映射历史）
  - 客户端收到快照后: 销毁所有本地实体 → 按快照重建（而非"增量更新"）
```

**技能冷却与 Buff 状态**：

断线/中途加入期间，技能冷却仍在计时。加入者需要知道每个技能的剩余冷却时间：

```cpp
// 快照中的技能状态
struct AbilityState {
    uint8_t  abilitySlot;        // Q/W/E/R 等
    float    cooldownRemaining;  // 剩余冷却时间（秒）
    uint8_t  charges;            // 充能技能剩余层数
    bool     isOnCooldown;
};
```

### 4.3 注意事项总结

| 关注点 | 问题 | 解决方案 |
|--------|------|---------|
| 动态对象池 | entityId 可能复用 | 快照携带 prefabId |
| 技能冷却 | 冷却在断线期已走完 | 快照携带 cooldownRemaining |
| Buff/Debuff | 断线期 Buff 持续减少 | 快照携带所有活跃 Buff 的剩余时间 |
| 计时器 | 全局/关卡计时器仍在走 | 快照携带当前 gameTime |
| 计分板 | 断线期分数可能变化 | 全量/增量更新 scores |
| RNG 状态 | 帧同步的 RNG 必须保存 | 快照中包含 RNG state |
| 玩家输入 | 断线期输入=空操作 | 服务端已用空操作填充 |
| AI 托管 | 断线期角色由 AI 控制 | 重连后平滑移交回玩家 |

---

## 5. 网络抖动处理

### 5.1 断线时间的分级阈值

断线检测不是一个简单的"收不到包→断线"的二元判断。工程上需要分级：

```
检测层级:
  Level 0: 单包丢失 (Single Packet Loss)        → UDP冗余包覆盖，无感知
  Level 1: 瞬时抖动 (< 500ms)                    → 心跳仍可能通，不触发任何处理
  Level 2: 瞬时断线 (500ms ~ 2s)                → 触发冗余指令填充
  Level 3: 短时断线 (2s ~ 10s)                  → 触发帧追赶/增量恢复
  Level 4: 长时断线 (10s ~ 60s)                 → 触发完整重连流程
  Level 5: 超长断线 (> 60s)                     → 踢出对局 / AI 托管
```

### 5.2 瞬时断线 (< 2s): 冗余指令填充

瞬时断线的最轻量处理：服务端用该玩家"上一帧的输入"或"空操作"填充缺失的帧位，对局继续进行。

```
帧同步服务端的处理:

玩家A 的输入到达情况:
  帧 100: ✓ (正常)
  帧 101: ✗ (丢包/网络抖动)
  帧 102: ✗ (连续丢包)
  帧 103: ✓ (恢复)

服务端广播:
  广播帧100: [A的帧100输入, B的帧100输入, C的帧100输入]  ← 正常
  广播帧101: [A的空操作,    B的帧101输入, C的帧101输入]  ← A被填充空操作
  广播帧102: [A的空操作,    B的帧102输入, C的帧102输入]  ← A继续空操作
  广播帧103: [A的帧103输入, B的帧103输入, C的帧103输入]  ← 恢复
```

**非对称影响**：断线玩家的角色在断线期间"原地不动"。对于 MOBA 游戏，这可能意味着被击杀——这是可接受的惩罚（短暂的不可靠连接不应被过度补偿）。

### 5.3 短时断线 (2~10s): 帧追赶

短时断线需要帧追赶。追赶期间的关键参数：

```
追赶参数:
  - 追赶倍率: 4x ~ 8x (取决于设备性能)
  - 最大追赶帧数: 600 帧 (约 40 秒 @ 15fps)
  - 追赶超时: 10 秒 (如果 10 秒内追不完，放弃并踢出)
  - 追赶期间画面: 显示进度条 / "重新连接中..."
  - 追赶完成后: 立即发送玩家当前操作
```

**追帧的"追赶悖论"**：你在追的时候，其他在线玩家还在继续玩。如果你用 4x 速度追 200 帧，耗时约 3.3 秒。在这 3.3 秒里，其他玩家又推进了约 50 帧。所以实际需要追 200+50=250 帧。追加的 50 帧需要约 0.8 秒，期间又推进了约 12 帧……这是一个收敛的等比数列：

$$T_{catchup} = \frac{T_{missing}}{speedup - 1}$$

其中 $T_{missing}$ 是缺失的帧时长，$speedup$ 是加速倍率。当 speedup=8 时，追 5 秒缺失的帧只需约 0.71 秒。

### 5.4 长时间断线 (> 10s): 完整重连或踢出

超过 10 秒的断线，帧追赶的性价比急剧下降（需要追太多帧，追赶时间长）。此时有两种选择：

- **允许重连**：走完整重连流程（全量快照+赶帧）——适用于休闲游戏
- **踢出对局**：释放资源，AI 托管角色——适用于竞技游戏

**竞技游戏的特殊考量**：长时间断线的玩家回来后即使追上了，也可能因为"挂机"期间的损失（被杀、丢塔）而失去竞技意义。此时触发投降投票或自动认输比"硬追"对体验更好。

> **工程经验**：设置一个 `MAX_CATCHUP_FRAMES = 600`（约 40 秒）。超过此值的追赶直接拒绝并踢出——因为此时内存中的帧包环形缓冲区可能也不完整了。

---

## 6. 客户端断线检测

### 6.1 心跳超时

心跳是检测连接存活的最基本手段：

```cpp
// 客户端心跳逻辑
class HeartbeatMonitor {
    uint32_t lastServerTime_ = 0;      // 最后一次收到服务器时间戳
    uint32_t heartbeatInterval_ = 500; // 心跳间隔 500ms
    uint32_t timeoutThreshold_ = 3000; // 超时阈值 3s（6个心跳周期）
    bool     isDisconnected_ = false;

public:
    // 每收到任意服务器消息时调用
    void OnPacketReceived(uint32_t serverTime) {
        lastServerTime_ = serverTime;
        if (isDisconnected_) {
            isDisconnected_ = false;
            OnReconnected(); // 触发重连流程
        }
    }

    // 每帧调用（或定时器）
    void Update(uint32_t currentTime) {
        if (currentTime - lastServerTime_ > timeoutThreshold_) {
            if (!isDisconnected_) {
                isDisconnected_ = true;
                OnDisconnected(); // 触发断线处理
            }
        }
    }
};
```

### 6.2 连续丢包计数

心跳超时是被动检测，连续丢包计数是主动检测——两者互补：

```cpp
// 丢包计数器
class PacketLossMonitor {
    uint32_t lastSequence_ = 0;        // 上次收到的序列号
    uint32_t consecutiveLosses_ = 0;   // 连续丢包计数
    uint32_t lossThreshold_ = 10;      // 连续丢 10 个包 = 断线判定

public:
    void OnPacketReceived(uint32_t seq) {
        if (lastSequence_ != 0) {
            uint32_t expected = lastSequence_ + 1;
            if (seq > expected) {
                consecutiveLosses_ += (seq - expected);
                // 注意: 累积计算而非用 =，处理乱序到达的情况
            } else {
                consecutiveLosses_ = 0; // 恢复正常
            }
        }
        lastSequence_ = seq;

        if (consecutiveLosses_ >= lossThreshold_) {
            OnConnectionUnstable(); // 触发不稳定告警
        }
    }
};
```

**心跳 vs 丢包计数对比**：

| 检测方式 | 检测延迟 | 误判风险 | 适用场景 |
|----------|---------|---------|---------|
| 心跳超时 | 3~5 秒 | 低（服务端静默也会触发） | 检测真正的 TCP 断连 / 长时间无数据 |
| 连续丢包 | 0.5~1 秒 | 中（突发丢包后恢复会被误判） | 检测 UDP 链路恶化 |
| 组合方案 | 先丢包告警 + 后心跳确认 | 低 | **推荐** |

**推荐组合方案**：
1. 丢包计数达到阈值（如连续 10 个包）→ 触发"黄色告警"：开始用空操作填充
2. 心跳超时（3 秒无任何包）→ 触发"红色告警"：确认断线，启动重连状态机
3. 黄色期间恢复正常 → 撤销告警，无需重连

---

## 7. 代码示例

### 7.1 C#: 帧同步重连系统完整实现

```csharp
// FrameSyncReconnect.cs — 帧同步重连系统完整实现
// 适用: Unity / .NET 8.0+ 独立服务器
// 依赖: 无外部依赖，使用标准库

using System;
using System.Collections.Generic;
using System.Threading;

namespace FrameSyncReconnect;

#region 数据结构

/// <summary>
/// 游戏世界的完整逻辑快照。
/// 包含从某个确定帧开始重放所需的所有状态。
/// </summary>
public class GameSnapshot
{
    public uint FrameNumber { get; set; }

    // 所有逻辑实体的状态（按 entityId 排序，确保确定性）
    public EntityState[] Entities { get; set; } = Array.Empty<EntityState>();

    // 随机数生成器状态 —— 遗漏此项将导致确定性崩溃
    public ulong[] RngStates { get; set; } = Array.Empty<ulong>();

    // 全局游戏状态
    public uint GameTimeMs { get; set; }
    public int[] TeamScores { get; set; } = new int[2];
    public uint[] GlobalCooldowns { get; set; } = Array.Empty<uint>();

    /// <summary>
    /// 深拷贝快照。重连管理器持有此快照直到客户端确认收到。
    /// </summary>
    public GameSnapshot DeepClone()
    {
        return new GameSnapshot
        {
            FrameNumber = FrameNumber,
            Entities = (EntityState[])Entities.Clone(),
            RngStates = (ulong[])RngStates.Clone(),
            GameTimeMs = GameTimeMs,
            TeamScores = (int[])TeamScores.Clone(),
            GlobalCooldowns = (uint[])GlobalCooldowns.Clone()
        };
    }
}

/// <summary>
/// 单个逻辑实体的状态。
/// 只包含逻辑相关字段，不包含渲染/动画状态。
/// </summary>
public struct EntityState
{
    public uint EntityId;
    public ushort PrefabId;       // 实体类型标识
    public int OwnerPlayerId;     // 所有玩家（-1 = 中立）
    public long PosX;             // 定点数 Q32.32
    public long PosY;
    public long PosZ;
    public int Hp;
    public int MaxHp;
    public uint StateFlags;       // (bit0=alive, bit1=stunned, bit2=invincible...)
    public uint[] BuffIds;        // 当前活跃Buff列表
    public float[] BuffRemaining; // 每个Buff的剩余时间
}

/// <summary>
/// 一个逻辑帧的输入集合（所有玩家在本帧的操作）。
/// 帧同步重连的核心数据单位。
/// </summary>
public class FrameInput
{
    public uint FrameNumber { get; init; }
    public PlayerInput[] Inputs { get; init; } = Array.Empty<PlayerInput>();
}

public struct PlayerInput
{
    public int PlayerId;
    public ushort InputFlags;  // 按键位掩码
    public short AxisX;        // 摇杆 X
    public short AxisY;        // 摇杆 Y
    public uint Checksum;      // 输入校验和（防篡改）

    /// <summary>空操作：玩家本帧未产生任何输入</summary>
    public static PlayerInput Empty(int playerId) => new()
    {
        PlayerId = playerId,
        InputFlags = 0,
        AxisX = 0,
        AxisY = 0,
        Checksum = 0
    };
}

#endregion

#region 服务端: 帧包环形缓冲区 + 快照管理器

/// <summary>
/// 服务端的帧包环形缓冲区。
/// 保存最近 N 帧的完整输入集合，供断线重连使用。
/// </summary>
public class FrameBuffer
{
    private readonly FrameInput[] _buffer;
    private readonly int _capacity;
    private uint _headFrame; // 最新写入的帧号

    public FrameBuffer(int capacityFrames)
    {
        _capacity = capacityFrames;
        _buffer = new FrameInput[capacityFrames];
        _headFrame = 0;
    }

    /// <summary>写入一帧的输入集合</summary>
    public void Write(uint frameNumber, PlayerInput[] inputs)
    {
        int index = (int)(frameNumber % (uint)_capacity);
        _buffer[index] = new FrameInput
        {
            FrameNumber = frameNumber,
            Inputs = (PlayerInput[])inputs.Clone()
        };
        _headFrame = frameNumber;
    }

    /// <summary>读取指定帧的输入集合，如果超出缓冲区范围返回 null</summary>
    public FrameInput? Read(uint frameNumber)
    {
        if (frameNumber > _headFrame) return null;
        // 检查是否在缓冲区范围内
        if (_headFrame - frameNumber >= (uint)_capacity) return null;

        int index = (int)(frameNumber % (uint)_capacity);
        var frame = _buffer[index];
        if (frame == null || frame.FrameNumber != frameNumber) return null;
        return frame;
    }

    /// <summary>获取从 startFrame 到 endFrame（含）的所有帧输入</summary>
    public List<FrameInput> GetFramesRange(uint startFrame, uint endFrame)
    {
        var result = new List<FrameInput>();
        for (uint f = startFrame; f <= endFrame; f++)
        {
            var fi = Read(f);
            if (fi != null)
                result.Add(fi);
        }
        return result;
    }

    /// <summary>最新的帧号</summary>
    public uint HeadFrame => _headFrame;
}

/// <summary>
/// 服务端的快照管理器。
/// 每隔 SNAPSHOT_INTERVAL 帧创建一次完整世界快照（用于重连起点）。
/// </summary>
public class SnapshotManager
{
    private const int SNAPSHOT_INTERVAL = 300; // 每 300 帧（约 20 秒）一个快照
    private readonly Dictionary<uint, GameSnapshot> _snapshots = new();
    private readonly object _lock = new();

    /// <summary>保存快照。调用方负责传入当前完整状态。</summary>
    public void SaveSnapshot(uint frameNumber, GameSnapshot snapshot)
    {
        if (frameNumber % SNAPSHOT_INTERVAL != 0) return;

        lock (_lock)
        {
            snapshot.FrameNumber = frameNumber;
            _snapshots[frameNumber] = snapshot.DeepClone();

            // 清理过期快照（保留最近 5 个）
            if (_snapshots.Count > 5)
            {
                uint oldest = uint.MaxValue;
                foreach (var key in _snapshots.Keys)
                    if (key < oldest) oldest = key;
                _snapshots.Remove(oldest);
            }
        }
    }

    /// <summary>获取 <= targetFrame 的最近一个快照</summary>
    public GameSnapshot? GetNearestSnapshot(uint targetFrame)
    {
        lock (_lock)
        {
            uint nearest = 0;
            GameSnapshot? result = null;
            foreach (var (frame, snap) in _snapshots)
            {
                if (frame <= targetFrame && frame > nearest)
                {
                    nearest = frame;
                    result = snap;
                }
            }
            return result;
        }
    }
}

/// <summary>
/// 服务端重连协调器。
/// 处理客户端的重连请求，返回 [快照 + 追赶帧包]。
/// </summary>
public class ServerReconnectCoordinator
{
    private readonly FrameBuffer _frameBuffer;
    private readonly SnapshotManager _snapshotManager;
    private readonly Dictionary<int, PlayerConnectionState> _playerStates = new();

    // 玩家重连容忍窗口（毫秒）
    private const uint RECONNECT_WINDOW_MS = 15000;
    // 超过此帧数的追赶直接拒绝
    private const uint MAX_CATCHUP_FRAMES = 600;

    public ServerReconnectCoordinator(FrameBuffer frameBuffer, SnapshotManager snapshotManager)
    {
        _frameBuffer = frameBuffer;
        _snapshotManager = snapshotManager;
    }

    /// <summary>构建重连响应数据包</summary>
    public ReconnectResponse BuildReconnectResponse(int playerId, uint lastAckedFrame)
    {
        uint currentFrame = _frameBuffer.HeadFrame;
        uint framesBehind = currentFrame - lastAckedFrame;

        // 检查是否允许重连
        if (!_playerStates.TryGetValue(playerId, out var state))
        {
            return new ReconnectResponse { Accepted = false, Reason = "Player not found" };
        }

        // 计算断线时长
        uint disconnectDurationMs = (currentFrame - state.DisconnectFrame) * 66; // 假设 66ms/帧
        if (disconnectDurationMs > RECONNECT_WINDOW_MS)
        {
            return new ReconnectResponse { Accepted = false, Reason = "Reconnect window expired" };
        }

        // 如果追赶帧数太多，拒绝
        if (framesBehind > MAX_CATCHUP_FRAMES)
        {
            return new ReconnectResponse { Accepted = false, Reason = "Too many frames to catch up" };
        }

        // 找到最近的有效快照作为起点
        var snapshot = _snapshotManager.GetNearestSnapshot(lastAckedFrame);
        uint catchupStartFrame = snapshot?.FrameNumber ?? 0;

        // 获取从快照帧到当前帧的所有输入
        var framesToCatchup = _frameBuffer.GetFramesRange(catchupStartFrame + 1, currentFrame);

        return new ReconnectResponse
        {
            Accepted = true,
            Snapshot = snapshot?.DeepClone(),
            CatchupFrames = framesToCatchup,
            CurrentServerFrame = currentFrame
        };
    }

    public void MarkPlayerDisconnected(int playerId, uint disconnectFrame)
    {
        _playerStates[playerId] = new PlayerConnectionState
        {
            IsConnected = false,
            DisconnectFrame = disconnectFrame
        };
    }

    private class PlayerConnectionState
    {
        public bool IsConnected;
        public uint DisconnectFrame;
    }
}

/// <summary>服务端返回的重连响应</summary>
public class ReconnectResponse
{
    public bool Accepted;
    public string Reason = "";
    public GameSnapshot? Snapshot;
    public List<FrameInput> CatchupFrames = new();
    public uint CurrentServerFrame;
}

#endregion

#region 客户端: 帧追赶引擎

/// <summary>
/// 客户端帧追赶引擎。
/// 在收到重连数据后，以加速模式执行逻辑帧直到追平服务器。
/// </summary>
public class ClientCatchupEngine
{
    // 追赶倍率（几个逻辑帧对应一次 Update 调用）
    private const int CATCHUP_SPEED_MULTIPLIER = 8;
    // 每追赶多少帧报告一次进度
    private const int PROGRESS_REPORT_INTERVAL = 50;

    private readonly Action<FrameInput> _executeLogicFrame;
    private uint _currentFrame = 0;
    private uint _targetFrame = 0;
    private List<FrameInput>? _pendingFrames;

    /// <param name="executeLogicFrame">执行一帧逻辑的回调（由游戏逻辑层注入）</param>
    public ClientCatchupEngine(Action<FrameInput> executeLogicFrame)
    {
        _executeLogicFrame = executeLogicFrame;
    }

    /// <summary>当前是否在追赶中</summary>
    public bool IsCatchingUp => _pendingFrames != null && _currentFrame < _targetFrame;

    /// <summary>追赶进度 (0.0 ~ 1.0)</summary>
    public float CatchupProgress => _targetFrame > 0
        ? Math.Min(1.0f, (float)(_currentFrame - (_targetFrame - (uint)(_pendingFrames?.Count ?? 0))) / (float)(_pendingFrames?.Count ?? 1))
        : 1.0f;

    /// <summary>
    /// 开始追赶。
    /// snapshotState: 从快照重建的本地状态（已就绪）。
    /// catchupFrames: 需要追赶的帧输入列表。
    /// targetFrame: 服务器的当前帧号。
    /// </summary>
    public void BeginCatchup(GameSnapshot snapshot, List<FrameInput> catchupFrames, uint targetFrame)
    {
        // 快照帧之后的第一帧开始追
        _currentFrame = snapshot.FrameNumber + 1;
        _targetFrame = targetFrame;
        _pendingFrames = catchupFrames;

        Console.WriteLine($"[Catchup] Starting from frame {_currentFrame}, " +
                          $"target {_targetFrame}, {catchupFrames.Count} frames to process");
    }

    /// <summary>
    /// 每帧调用（在 Unity Update 中）。
    /// 追赶期间返回 true，追赶完成返回 false。
    /// </summary>
    public bool UpdateCatchup()
    {
        if (!IsCatchingUp) return false;

        // 每次 Update 执行 CATCHUP_SPEED_MULTIPLIER 帧的逻辑
        for (int i = 0; i < CATCHUP_SPEED_MULTIPLIER && _currentFrame <= _targetFrame; i++)
        {
            // 从 pendingFrames 中找到对应的帧输入
            var frameInput = FindFrameInput(_currentFrame);
            if (frameInput != null)
            {
                // 执行逻辑帧（不渲染！）
                _executeLogicFrame(frameInput);
            }
            _currentFrame++;
        }

        // 报告进度
        if ((_currentFrame - _targetFrame + (uint)(_pendingFrames?.Count ?? 0)) % PROGRESS_REPORT_INTERVAL == 0)
        {
            Console.WriteLine($"[Catchup] Progress: {CatchupProgress * 100:F1}% " +
                              $"(frame {_currentFrame}/{_targetFrame})");
        }

        return IsCatchingUp;
    }

    private FrameInput? FindFrameInput(uint frameNumber)
    {
        // 线性搜索（追赶帧通常 < 600，性能可接受）
        if (_pendingFrames == null) return null;
        foreach (var fi in _pendingFrames)
        {
            if (fi.FrameNumber == frameNumber) return fi;
        }
        return null; // 该帧无数据（极罕见，通常意味着丢包导致帧包不完整）
    }
}

#endregion

#region 客户端: 断线检测器

/// <summary>
/// 客户端断线检测器：心跳超时 + 连续丢包的双重检测。
/// </summary>
public class DisconnectDetector
{
    private long _lastReceiveTimeTicks;
    private uint _lastSequence;
    private int _consecutiveLossCount;
    private bool _isDisconnected;
    private bool _isWarning; // 黄色告警

    private const long HEARTBEAT_TIMEOUT_TICKS = 3 * TimeSpan.TicksPerSecond; // 3秒心跳超时
    private const int LOSS_WARNING_THRESHOLD = 8;   // 连续丢8个包 → 黄色告警
    private const int LOSS_CRITICAL_THRESHOLD = 20;  // 连续丢20个包 → 确认断线

    public event Action? OnWarning;      // 黄色告警
    public event Action? OnDisconnected; // 红色告警（确认断线）
    public event Action? OnReconnected;  // 恢复连接
    public bool IsDisconnected => _isDisconnected;
    public bool IsWarning => _isWarning;

    public DisconnectDetector()
    {
        _lastReceiveTimeTicks = DateTime.UtcNow.Ticks;
    }

    /// <summary>收到任意包时调用</summary>
    public void OnPacketReceived(uint sequence)
    {
        _lastReceiveTimeTicks = DateTime.UtcNow.Ticks;

        // 丢包检测：检查序列号连续性
        if (_lastSequence != 0)
        {
            uint expected = _lastSequence + 1;
            if (sequence > expected)
            {
                _consecutiveLossCount += (int)(sequence - expected);
            }
            else
            {
                _consecutiveLossCount = 0;
            }
        }
        _lastSequence = sequence;

        // 恢复检测
        if (_isDisconnected)
        {
            _isDisconnected = false;
            _isWarning = false;
            _consecutiveLossCount = 0;
            OnReconnected?.Invoke();
        }
        else if (_isWarning)
        {
            _isWarning = false;
            _consecutiveLossCount = 0;
        }
    }

    /// <summary>每帧或定时器调用</summary>
    public void Update()
    {
        long nowTicks = DateTime.UtcNow.Ticks;
        long elapsedTicks = nowTicks - _lastReceiveTimeTicks;

        // 红色告警：心跳超时
        if (elapsedTicks > HEARTBEAT_TIMEOUT_TICKS)
        {
            if (!_isDisconnected)
            {
                _isDisconnected = true;
                _isWarning = true;
                OnDisconnected?.Invoke();
            }
            return;
        }

        // 黄色告警：连续丢包
        if (_consecutiveLossCount >= LOSS_CRITICAL_THRESHOLD)
        {
            if (!_isDisconnected)
            {
                _isDisconnected = true;
                OnDisconnected?.Invoke();
            }
        }
        else if (_consecutiveLossCount >= LOSS_WARNING_THRESHOLD && !_isWarning)
        {
            _isWarning = true;
            OnWarning?.Invoke();
        }
    }
}

#endregion
```

### 7.2 C++: 快照恢复 + 追赶系统

```cpp
// ReconnectSystem.hpp — 快照恢复与赶帧系统
// 适用: Unreal Engine / 独立 C++ 游戏服务器
// 编译: C++20, 依赖: <vector>, <unordered_map>, <deque>, <chrono>, <optional>

#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <deque>
#include <chrono>
#include <optional>
#include <mutex>
#include <string>
#include <algorithm>

namespace ReconnectSystem {

// ============================================================
// 数据结构定义
// ============================================================

/// 定点数类型（Q32.32），确保跨平台确定性
using Fixed64 = int64_t;

/// 单个实体快照
struct EntitySnapshot {
    uint32_t entityId;
    uint16_t prefabId;
    int32_t  ownerPlayerId;

    // 变换（定点数）
    Fixed64 posX, posY, posZ;
    int32_t rotX, rotY, rotZ, rotW; // 四元数（Q16.16）

    // 游戏状态
    int32_t hp;
    int32_t maxHp;
    uint32_t stateFlags;  // bit flags: alive, stunned, etc.

    // 活跃 Buff 列表
    std::vector<uint32_t> buffIds;
    std::vector<float> buffRemaining;
};

/// 完整游戏世界快照
struct WorldSnapshot {
    uint32_t frameNumber;     // 快照对应的服务器帧号
    uint32_t gameTimeMs;      // 游戏时间（毫秒）
    int32_t  teamScores[2];

    // 所有活跃实体
    std::vector<EntitySnapshot> entities;

    // RNG 状态（帧同步关键！）
    // 假设游戏使用 N 个独立的 RNG 实例（战斗 RNG、掉落 RNG、AI RNG...）
    std::vector<uint64_t> rngStates;

    // 全局冷却时间（技能系统）
    std::vector<float> globalCooldowns;
};

/// 单个玩家的单帧输入
struct PlayerInput {
    int32_t  playerId;
    uint16_t inputFlags;  // 按键位掩码
    int16_t  axisX;       // 摇杆 X (-32768 ~ 32767)
    int16_t  axisY;       // 摇杆 Y
    uint32_t checksum;

    static PlayerInput Empty(int32_t playerId) {
        return { playerId, 0, 0, 0, 0 };
    }
};

/// 一个逻辑帧的输入集合
struct FrameInputPack {
    uint32_t frameNumber;
    std::vector<PlayerInput> inputs; // 按 playerId 排序
};

// ============================================================
// 服务端: 环形帧缓冲区
// ============================================================

class FrameRingBuffer {
public:
    explicit FrameRingBuffer(size_t capacityFrames)
        : capacity_(capacityFrames)
    {
        buffer_.resize(capacity_);
    }

    /// 写入一帧的输入
    void Write(uint32_t frameNumber, std::vector<PlayerInput> inputs) {
        size_t index = frameNumber % capacity_;
        buffer_[index] = FrameInputPack{ frameNumber, std::move(inputs) };
        headFrame_ = frameNumber;
    }

    /// 读取指定帧（如果超出缓冲区范围返回 nullopt）
    std::optional<FrameInputPack> Read(uint32_t frameNumber) const {
        if (frameNumber > headFrame_) return std::nullopt;
        if (headFrame_ - frameNumber >= capacity_) return std::nullopt;

        size_t index = frameNumber % capacity_;
        const auto& pack = buffer_[index];
        if (pack.frameNumber != frameNumber) return std::nullopt;
        return pack;
    }

    /// 获取帧范围 [start, end] 的所有输入
    std::vector<FrameInputPack> GetRange(uint32_t startFrame, uint32_t endFrame) const {
        std::vector<FrameInputPack> result;
        for (uint32_t f = startFrame; f <= endFrame; ++f) {
            auto pack = Read(f);
            if (pack.has_value()) {
                result.push_back(std::move(*pack));
            }
        }
        return result;
    }

    uint32_t HeadFrame() const { return headFrame_; }

private:
    size_t capacity_;
    uint32_t headFrame_ = 0;
    std::vector<std::optional<FrameInputPack>> buffer_;
};

// ============================================================
// 服务端: 快照管理
// ============================================================

class SnapshotManager {
public:
    static constexpr uint32_t SNAPSHOT_INTERVAL = 300; // 每300帧
    static constexpr size_t MAX_SNAPSHOTS = 5;

    /// 保存快照（只在 SNAPSHOT_INTERVAL 的整数倍帧调用）
    void SaveSnapshot(uint32_t frameNumber, WorldSnapshot snapshot) {
        if (frameNumber % SNAPSHOT_INTERVAL != 0) return;

        std::lock_guard<std::mutex> lock(mutex_);
        snapshot.frameNumber = frameNumber;
        snapshots_[frameNumber] = std::move(snapshot);

        // 清理旧快照
        while (snapshots_.size() > MAX_SNAPSHOTS) {
            auto oldest = snapshots_.begin()->first;
            snapshots_.erase(oldest);
        }
    }

    /// 获取 <= targetFrame 的最近快照
    std::optional<WorldSnapshot> GetNearestSnapshot(uint32_t targetFrame) const {
        std::lock_guard<std::mutex> lock(mutex_);

        uint32_t nearest = 0;
        const WorldSnapshot* result = nullptr;

        for (const auto& [frame, snap] : snapshots_) {
            if (frame <= targetFrame && frame > nearest) {
                nearest = frame;
                result = &snap;
            }
        }

        if (result) {
            return *result; // 拷贝返回
        }
        return std::nullopt;
    }

private:
    mutable std::mutex mutex_;
    std::unordered_map<uint32_t, WorldSnapshot> snapshots_;
};

// ============================================================
// 服务端: 玩家连接状态跟踪
// ============================================================

struct PlayerConnectionState {
    bool isConnected = true;
    uint32_t disconnectFrame = 0;
    uint32_t lastAckedFrame = 0;

    // 断线期间的空操作填充计数
    uint32_t emptyInputFrameCount = 0;

    // 重连窗口（帧数）：15 秒 × 15fps = 225 帧
    static constexpr uint32_t RECONNECT_WINDOW_FRAMES = 225;
    // 超过此帧数直接踢出
    static constexpr uint32_t MAX_CATCHUP_FRAMES = 600;

    bool CanReconnect(uint32_t currentFrame) const {
        return (currentFrame - disconnectFrame) <= RECONNECT_WINDOW_FRAMES;
    }
};

// ============================================================
// 服务端: 重连协调器
// ============================================================

struct ReconnectResponse {
    bool accepted = false;
    std::string reason;

    // 成功时填充
    WorldSnapshot snapshot;
    std::vector<FrameInputPack> catchupFrames;
    uint32_t currentServerFrame = 0;
};

class ServerReconnectCoordinator {
public:
    ServerReconnectCoordinator(FrameRingBuffer& frameBuffer,
                                SnapshotManager& snapshotManager)
        : frameBuffer_(frameBuffer)
        , snapshotManager_(snapshotManager)
    {}

    /// 构建重连响应
    ReconnectResponse BuildResponse(int32_t playerId) {
        auto it = playerStates_.find(playerId);
        if (it == playerStates_.end()) {
            return { false, "Player not found" };
        }

        auto& state = it->second;
        uint32_t currentFrame = frameBuffer_.HeadFrame();

        if (!state.CanReconnect(currentFrame)) {
            return { false, "Reconnect window expired" };
        }

        uint32_t framesBehind = currentFrame - state.lastAckedFrame;
        if (framesBehind > PlayerConnectionState::MAX_CATCHUP_FRAMES) {
            return { false, "Too many frames to catch up" };
        }

        // 获取最近快照
        auto snapshotOpt = snapshotManager_.GetNearestSnapshot(state.lastAckedFrame);
        uint32_t catchupStart = snapshotOpt.has_value()
            ? snapshotOpt->frameNumber + 1
            : 0;

        auto catchupFrames = frameBuffer_.GetRange(catchupStart, currentFrame);

        ReconnectResponse response;
        response.accepted = true;
        response.currentServerFrame = currentFrame;
        response.catchupFrames = std::move(catchupFrames);

        if (snapshotOpt.has_value()) {
            response.snapshot = std::move(*snapshotOpt);
        }

        return response;
    }

    /// 标记玩家断线
    void MarkDisconnected(int32_t playerId, uint32_t disconnectFrame) {
        auto& state = playerStates_[playerId];
        state.isConnected = false;
        state.disconnectFrame = disconnectFrame;
    }

    /// 标记玩家已重连
    void MarkReconnected(int32_t playerId) {
        auto it = playerStates_.find(playerId);
        if (it != playerStates_.end()) {
            it->second.isConnected = true;
            it->second.emptyInputFrameCount = 0;
        }
    }

    /// 更新玩家确认帧号
    void UpdateAckedFrame(int32_t playerId, uint32_t ackedFrame) {
        playerStates_[playerId].lastAckedFrame = ackedFrame;
    }

    /// 为断线玩家生成空操作填充
    PlayerInput GetEmptyInputForPlayer(int32_t playerId) {
        auto it = playerStates_.find(playerId);
        if (it != playerStates_.end()) {
            it->second.emptyInputFrameCount++;
        }
        return PlayerInput::Empty(playerId);
    }

private:
    FrameRingBuffer& frameBuffer_;
    SnapshotManager& snapshotManager_;
    std::unordered_map<int32_t, PlayerConnectionState> playerStates_;
};

// ============================================================
// 客户端: 赶帧引擎
// ============================================================

class ClientCatchupEngine {
public:
    using LogicFrameCallback = std::function<void(const FrameInputPack&)>;
    using ProgressCallback = std::function<void(float progress)>;

    /// speedMultiplier: 每次 Update 执行多少逻辑帧
    explicit ClientCatchupEngine(size_t speedMultiplier = 8)
        : speedMultiplier_(speedMultiplier)
    {}

    /// 设置逻辑帧执行回调（由游戏层注入）
    void SetLogicFrameCallback(LogicFrameCallback cb) {
        logicFrameCallback_ = std::move(cb);
    }

    /// 设置进度报告回调
    void SetProgressCallback(ProgressCallback cb) {
        progressCallback_ = std::move(cb);
    }

    /// 开始追赶
    void BeginCatchup(
        const WorldSnapshot& snapshot,
        std::vector<FrameInputPack> catchupFrames,
        uint32_t targetFrame
    ) {
        currentFrame_ = snapshot.frameNumber + 1;
        targetFrame_ = targetFrame;
        catchupFrames_ = std::move(catchupFrames);

        // 构建帧查找索引（用有序 vector 而非 map，内存更紧凑且缓存友好）
        frameIndex_.clear();
        frameIndex_.reserve(catchupFrames_.size());
        for (size_t i = 0; i < catchupFrames_.size(); ++i) {
            frameIndex_.emplace_back(catchupFrames_[i].frameNumber, i);
        }
        // 按帧号排序（通常已有序，但防御性排序）
        std::sort(frameIndex_.begin(), frameIndex_.end());

        isCatchingUp_ = true;
        totalFrames_ = static_cast<float>(catchupFrames_.size());
    }

    /// 每次 Update 调用，返回 true 表示仍在追赶
    bool UpdateCatchup() {
        if (!isCatchingUp_) return false;

        uint32_t framesProcessedThisUpdate = 0;

        for (size_t i = 0;
             i < speedMultiplier_ && currentFrame_ <= targetFrame_;
             ++i)
        {
            // 二分查找当前帧的输入
            auto it = std::lower_bound(
                frameIndex_.begin(), frameIndex_.end(),
                currentFrame_,
                [](const auto& entry, uint32_t f) { return entry.first < f; }
            );

            if (it != frameIndex_.end() && it->first == currentFrame_) {
                const auto& pack = catchupFrames_[it->second];
                if (logicFrameCallback_) {
                    logicFrameCallback_(pack);
                }
            }
            // else: 该帧无数据（极罕见，通常表示帧包不完整）

            currentFrame_++;
            framesProcessedThisUpdate++;
        }

        // 进度报告
        if (progressCallback_ && framesProcessedThisUpdate > 0) {
            float progress = totalFrames_ > 0
                ? std::min(1.0f, static_cast<float>(framesProcessedThisUpdate) / totalFrames_)
                : 1.0f;
            progressCallback_(progress);
        }

        if (currentFrame_ > targetFrame_) {
            isCatchingUp_ = false;
            catchupFrames_.clear();
            frameIndex_.clear();
            return false;
        }

        return true;
    }

    bool IsCatchingUp() const { return isCatchingUp_; }
    float CatchupProgress() const {
        if (!isCatchingUp_ || totalFrames_ <= 0) return 1.0f;
        return std::min(1.0f, static_cast<float>(
            catchupFrames_.size() - frameIndex_.size()) / totalFrames_);
    }

private:
    size_t speedMultiplier_;
    bool isCatchingUp_ = false;
    uint32_t currentFrame_ = 0;
    uint32_t targetFrame_ = 0;
    float totalFrames_ = 0.0f;

    std::vector<FrameInputPack> catchupFrames_;
    // (frameNumber, index into catchupFrames_) 的有序索引
    std::vector<std::pair<uint32_t, size_t>> frameIndex_;

    LogicFrameCallback logicFrameCallback_;
    ProgressCallback progressCallback_;
};

// ============================================================
// 客户端: 断线检测器
// ============================================================

class DisconnectDetector {
public:
    using Callback = std::function<void()>;

    /// heartbeatTimeoutMs: 心跳超时阈值（毫秒）
    /// lossWarningThreshold: 连续丢包警告阈值
    /// lossCriticalThreshold: 连续丢包确认断线阈值
    DisconnectDetector(
        uint32_t heartbeatTimeoutMs = 3000,
        int lossWarningThreshold = 8,
        int lossCriticalThreshold = 20
    )
        : heartbeatTimeoutMs_(heartbeatTimeoutMs)
        , lossWarningThreshold_(lossWarningThreshold)
        , lossCriticalThreshold_(lossCriticalThreshold)
    {
        lastReceiveTime_ = std::chrono::steady_clock::now();
    }

    /// 收到任意包时调用
    void OnPacketReceived(uint32_t sequence) {
        lastReceiveTime_ = std::chrono::steady_clock::now();

        // 丢包检测
        if (lastSequence_ != 0) {
            uint32_t expected = lastSequence_ + 1;
            if (sequence > expected) {
                consecutiveLosses_ += static_cast<int>(sequence - expected);
            } else {
                consecutiveLosses_ = 0;
            }
        }
        lastSequence_ = sequence;

        // 如果之前是断线状态，通知恢复
        if (isDisconnected_) {
            isDisconnected_ = false;
            isWarning_ = false;
            consecutiveLosses_ = 0;
            if (onReconnected_) onReconnected_();
        } else if (isWarning_) {
            isWarning_ = false;
            consecutiveLosses_ = 0;
        }
    }

    /// 定时器调用（每 100ms 即可）
    void Update() {
        auto now = std::chrono::steady_clock::now();
        auto elapsedMs = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - lastReceiveTime_).count();

        // 红色告警：心跳超时
        if (elapsedMs > heartbeatTimeoutMs_) {
            if (!isDisconnected_) {
                isDisconnected_ = true;
                isWarning_ = true;
                if (onDisconnected_) onDisconnected_();
            }
            return;
        }

        // 丢包检测
        if (consecutiveLosses_ >= lossCriticalThreshold_) {
            if (!isDisconnected_) {
                isDisconnected_ = true;
                if (onDisconnected_) onDisconnected_();
            }
        } else if (consecutiveLosses_ >= lossWarningThreshold_ && !isWarning_) {
            isWarning_ = true;
            if (onWarning_) onWarning_();
        }
    }

    bool IsDisconnected() const { return isDisconnected_; }
    int ConsecutiveLosses() const { return consecutiveLosses_; }

    // 回调注册
    void SetOnWarning(Callback cb) { onWarning_ = std::move(cb); }
    void SetOnDisconnected(Callback cb) { onDisconnected_ = std::move(cb); }
    void SetOnReconnected(Callback cb) { onReconnected_ = std::move(cb); }

private:
    uint32_t heartbeatTimeoutMs_;
    int lossWarningThreshold_;
    int lossCriticalThreshold_;

    std::chrono::steady_clock::time_point lastReceiveTime_;
    uint32_t lastSequence_ = 0;
    int consecutiveLosses_ = 0;
    bool isDisconnected_ = false;
    bool isWarning_ = false;

    Callback onWarning_;
    Callback onDisconnected_;
    Callback onReconnected_;
};

} // namespace ReconnectSystem
```

### 7.3 Lua: 重连管理器（与 C# 引擎绑定）

```lua
-- ReconnectManager.lua — 客户端重连管理器
-- 适用: 帧同步/状态同步 Lua 客户端（XLua / SLua / ToLua 等）
-- 依赖: 底层 C# 网络层已提供 SendToServer / 事件回调

local ReconnectManager = {}
ReconnectManager.__index = ReconnectManager

-- ============================================================
-- 配置常量
-- ============================================================

local CONFIG = {
    -- 心跳超时 (ms)
    HEARTBEAT_TIMEOUT_MS = 3000,

    -- 连续丢包告警阈值
    LOSS_WARNING_THRESHOLD = 8,
    LOSS_CRITICAL_THRESHOLD = 20,

    -- 追赶倍率（每次 Update 执行多少帧逻辑）
    CATCHUP_SPEED = 8,

    -- 追赶进度报告间隔（帧）
    PROGRESS_REPORT_INTERVAL = 50,

    -- 重连尝试次数上限
    MAX_RECONNECT_ATTEMPTS = 3,

    -- 重连尝试间隔 (ms)
    RECONNECT_RETRY_INTERVAL_MS = 2000,

    -- 最大追赶帧数（超过则拒绝重连）
    MAX_CATCHUP_FRAMES = 600,
}

-- ============================================================
-- 状态枚举
-- ============================================================

local ConnectionState = {
    CONNECTED    = 1,  -- 正常连接
    WARNING      = 2,  -- 黄色告警（丢包增多）
    DISCONNECTED = 3,  -- 已断线
    RECONNECTING = 4,  -- 正在重连
    CATCHING_UP  = 5,  -- 正在追帧
}

-- ============================================================
-- 构造函数
-- ============================================================

function ReconnectManager.new(networkLayer, gameLogic)
    local self = setmetatable({}, ReconnectManager)

    -- 外部依赖注入
    self.network = networkLayer  -- 网络层接口（C# 绑定）
    self.gameLogic = gameLogic   -- 游戏逻辑层接口（C# 绑定）

    -- 状态
    self.state = ConnectionState.CONNECTED
    self.lastReceiveTime = os.clock() * 1000  -- 毫秒
    self.lastSequence = 0
    self.consecutiveLosses = 0
    self.reconnectAttempts = 0
    self.nextReconnectTime = 0

    -- 追赶状态
    self.isCatchingUp = false
    self.catchupFrames = nil       -- { [frameNum] = FrameInputPack }
    self.currentFrame = 0
    self.targetFrame = 0

    -- 事件回调（UI 层注册）
    self.onStateChanged = nil      -- function(newState, oldState)
    self.onCatchupProgress = nil   -- function(progress: 0.0~1.0)

    return self
end

-- ============================================================
-- 网络事件处理
-- ============================================================

--- 收到任意服务器消息时调用
function ReconnectManager:OnPacketReceived(sequence)
    self.lastReceiveTime = os.clock() * 1000

    -- 丢包检测
    if self.lastSequence > 0 then
        local expected = self.lastSequence + 1
        if sequence > expected then
            self.consecutiveLosses = self.consecutiveLosses + (sequence - expected)
        else
            self.consecutiveLosses = 0
        end
    end
    self.lastSequence = sequence

    -- 恢复检测
    if self.state == ConnectionState.DISCONNECTED
        or self.state == ConnectionState.RECONNECTING then
        self:_TransitionTo(ConnectionState.CONNECTED)
        self.reconnectAttempts = 0
        self.consecutiveLosses = 0
        print("[Reconnect] Connection restored!")
    elseif self.state == ConnectionState.WARNING then
        self:_TransitionTo(ConnectionState.CONNECTED)
        self.consecutiveLosses = 0
        print("[Reconnect] Network recovered from warning state")
    end
end

--- 收到服务器重连响应时调用（由网络层回调）
function ReconnectManager:OnReconnectResponse(response)
    if not response.accepted then
        print(string.format("[Reconnect] Server rejected: %s", response.reason))
        -- 尝试再次重连
        self.reconnectAttempts = self.reconnectAttempts + 1
        if self.reconnectAttempts < CONFIG.MAX_RECONNECT_ATTEMPTS then
            self.nextReconnectTime = os.clock() * 1000 + CONFIG.RECONNECT_RETRY_INTERVAL_MS
            self:_TransitionTo(ConnectionState.DISCONNECTED) -- 回到等待状态
        else
            -- 重连失败，踢回大厅
            print("[Reconnect] Max retries exceeded, returning to lobby")
            self:_OnReconnectFailed()
        end
        return
    end

    print(string.format(
        "[Reconnect] Server accepted! Need to catch up %d frames",
        #(response.catchupFrames or {})
    ))

    -- 开始追赶
    self:_TransitionTo(ConnectionState.CATCHING_UP)
    self:_BeginCatchup(response)
end

-- ============================================================
-- 定时更新（每帧调用）
-- ============================================================

function ReconnectManager:Update()
    local nowMs = os.clock() * 1000

    -- 追赶状态下的更新
    if self.state == ConnectionState.CATCHING_UP then
        self:_UpdateCatchup()
        return
    end

    -- 重连状态下等待重试
    if self.state == ConnectionState.DISCONNECTED then
        if self.reconnectAttempts > 0
            and nowMs >= self.nextReconnectTime
            and self.reconnectAttempts < CONFIG.MAX_RECONNECT_ATTEMPTS then
            self:_SendReconnectRequest()
        end
        return
    end

    -- 连接状态下的健康检查
    local elapsedMs = nowMs - self.lastReceiveTime

    -- 红色告警：心跳超时
    if elapsedMs > CONFIG.HEARTBEAT_TIMEOUT_MS then
        if self.state ~= ConnectionState.DISCONNECTED
            and self.state ~= ConnectionState.RECONNECTING then
            self:_OnDisconnected()
        end
        return
    end

    -- 黄色告警：连续丢包
    if self.consecutiveLosses >= CONFIG.LOSS_CRITICAL_THRESHOLD then
        if self.state ~= ConnectionState.DISCONNECTED then
            self:_OnDisconnected()
        end
    elseif self.consecutiveLosses >= CONFIG.LOSS_WARNING_THRESHOLD
        and self.state == ConnectionState.CONNECTED then
        self:_TransitionTo(ConnectionState.WARNING)
        print(string.format(
            "[Reconnect] Network unstable: %d consecutive losses",
            self.consecutiveLosses
        ))
    end
end

-- ============================================================
-- 内部方法：状态转换
-- ============================================================

function ReconnectManager:_TransitionTo(newState)
    if self.state == newState then return end
    local oldState = self.state
    self.state = newState
    print(string.format("[Reconnect] State: %d → %d", oldState, newState))

    if self.onStateChanged then
        self.onStateChanged(newState, oldState)
    end
end

-- ============================================================
-- 内部方法：断线处理
-- ============================================================

function ReconnectManager:_OnDisconnected()
    self:_TransitionTo(ConnectionState.DISCONNECTED)
    self.reconnectAttempts = 0

    -- 立即发送第一次重连请求
    self:_SendReconnectRequest()
end

function ReconnectManager:_SendReconnectRequest()
    self:_TransitionTo(ConnectionState.RECONNECTING)

    -- 发送重连请求（告知服务器最后确认的帧号）
    local lastAckedFrame = self.gameLogic:GetLastAckedFrame()
    self.network:SendReconnectRequest(lastAckedFrame)

    print(string.format(
        "[Reconnect] Sending reconnect request (attempt %d, lastAck=%d)",
        self.reconnectAttempts + 1, lastAckedFrame
    ))
end

function ReconnectManager:_OnReconnectFailed()
    -- 通知 UI 层
    if self.onReconnectFailed then
        self.onReconnectFailed()
    end
    -- 返回大厅或重新登录
    self.gameLogic:ReturnToLobby()
end

-- ============================================================
-- 内部方法：帧追赶
-- ============================================================

function ReconnectManager:_BeginCatchup(response)
    -- 从快照重建游戏状态
    if response.snapshot then
        self.gameLogic:LoadSnapshot(response.snapshot)
    end

    -- 构建帧查找表（用 table 做 O(1) 查找）
    self.catchupFrames = {}
    if response.catchupFrames then
        for _, framePack in ipairs(response.catchupFrames) do
            self.catchupFrames[framePack.frameNumber] = framePack
        end
    end

    -- 计算起始帧
    local startFrame = 0
    if response.snapshot then
        startFrame = response.snapshot.frameNumber + 1
    end

    self.currentFrame = startFrame
    self.targetFrame = response.currentServerFrame
    self.isCatchingUp = true

    local totalFrames = self.targetFrame - startFrame + 1
    print(string.format(
        "[Reconnect] Catchup started: frames %d→%d (%d total, %dx speed)",
        startFrame, self.targetFrame, totalFrames, CONFIG.CATCHUP_SPEED
    ))
end

function ReconnectManager:_UpdateCatchup()
    if not self.isCatchingUp then return end

    local framesProcessed = 0

    for i = 1, CONFIG.CATCHUP_SPEED do
        if self.currentFrame > self.targetFrame then break end

        -- 查找本帧的输入
        local frameInput = self.catchupFrames[self.currentFrame]
        if frameInput then
            -- 执行逻辑帧（不渲染！由游戏逻辑层接管）
            self.gameLogic:ExecuteLogicFrame(frameInput)
        end

        self.currentFrame = self.currentFrame + 1
        framesProcessed = framesProcessed + 1
    end

    -- 进度回调
    if framesProcessed > 0 and self.onCatchupProgress then
        local startFrame = self.targetFrame - self:_TotalPendingFrames()
        local totalFrames = self.targetFrame - startFrame + 1
        local progress = totalFrames > 0
            and math.min(1.0, (self.currentFrame - startFrame) / totalFrames)
            or 1.0
        self.onCatchupProgress(progress)
    end

    -- 追赶完成
    if self.currentFrame > self.targetFrame then
        self:_OnCatchupComplete()
    end
end

function ReconnectManager:_TotalPendingFrames()
    local count = 0
    if self.catchupFrames then
        for _ in pairs(self.catchupFrames) do count = count + 1 end
    end
    return count
end

function ReconnectManager:_OnCatchupComplete()
    self.isCatchingUp = false
    self.catchupFrames = nil

    -- 同步逻辑状态到渲染层
    self.gameLogic:SyncLogicToRender()

    self:_TransitionTo(ConnectionState.CONNECTED)
    print("[Reconnect] Catchup complete! Resuming normal gameplay.")

    -- 通知 UI 层追赶完成
    if self.onCatchupComplete then
        self.onCatchupComplete()
    end
end

-- ============================================================
-- 公开接口
-- ============================================================

--- 注册状态变化回调
function ReconnectManager:RegisterCallbacks(callbacks)
    if callbacks.onStateChanged then
        self.onStateChanged = callbacks.onStateChanged
    end
    if callbacks.onCatchupProgress then
        self.onCatchupProgress = callbacks.onCatchupProgress
    end
    if callbacks.onCatchupComplete then
        self.onCatchupComplete = callbacks.onCatchupComplete
    end
    if callbacks.onReconnectFailed then
        self.onReconnectFailed = callbacks.onReconnectFailed
    end
end

--- 获取当前状态字符串（调试用）
function ReconnectManager:GetStateName()
    local names = {
        [ConnectionState.CONNECTED]    = "CONNECTED",
        [ConnectionState.WARNING]      = "WARNING",
        [ConnectionState.DISCONNECTED] = "DISCONNECTED",
        [ConnectionState.RECONNECTING] = "RECONNECTING",
        [ConnectionState.CATCHING_UP]  = "CATCHING_UP",
    }
    return names[self.state] or "UNKNOWN"
end

--- 获取追赶进度 (0.0~1.0)，不在追赶返回 1.0
function ReconnectManager:GetCatchupProgress()
    if not self.isCatchingUp or self.targetFrame == 0 then return 1.0 end
    local startFrame = self.targetFrame - self:_TotalPendingFrames()
    local totalFrames = self.targetFrame - startFrame + 1
    if totalFrames <= 0 then return 1.0 end
    return math.min(1.0, (self.currentFrame - startFrame) / totalFrames)
end

--- 主动发送 ping（心跳辅助）
function ReconnectManager:SendPing()
    self.network:SendPing(os.clock() * 1000)
end

return ReconnectManager
```

---

## 8. 练习

### 练习 1: 基础 — 实现丢包检测与心跳超时 (25min)

**目标**：实现一个客户端断线检测模块，正确区分丢包告警和确认断线。

**要求**：
1. 维护一个 `PacketLossMonitor` 类，支持序列号连续性检查
2. 维护一个 `HeartbeatMonitor` 类，支持基于最后收包时间的超时检测
3. 组合两者：丢包达到阈值 → 黄色告警，心跳超时 → 红色告警（确认断线）
4. 当"黄色告警"期间恢复 → 撤销告警，不触发重连
5. 当"红色告警"后恢复 → 触发 `OnReconnected` 事件

**测试场景**：
- 模拟连续 5 个包丢失 → 不应触发告警（阈值=8）
- 模拟连续 12 个包丢失 → 应触发黄色告警
- 黄色告警后收到 1 个包 → 应撤销告警
- 3 秒无数据 → 触发断线事件
- 断线后收到数据 → 触发重连事件

### 练习 2: 进阶 — 帧追赶速度的自适应调整 (35min)

**目标**：实现自适应的帧追赶速度，根据设备性能动态调整追赶倍率。

**要求**：
1. 实现 `AdaptiveCatchupSpeed` 策略：
   - 初始追赶倍率 = 4x
   - 每 50 个追赶帧测量一次单帧逻辑耗时（`logicFrameDuration`）
   - 如果 `logicFrameDuration < 2ms` → 倍率 +2（上限 16x）
   - 如果 `logicFrameDuration > 10ms` → 倍率 -2（下限 2x）
   - 如果设备温度传感器显示高温 → 强制降至 2x
2. 使用指数移动平均 (EMA) 平滑 `logicFrameDuration` 的测量值
3. 实现追赶期间的帧预算控制：
   - 每帧总预算 = 16ms（60fps）
   - 逻辑帧消耗 ≤ 12ms（留 4ms 给系统和渲染必要的 UI）
   - 如果超过预算 → 自动降速

**提示**：
```csharp
// EMA 平滑
float smoothedDuration = alpha * measuredDuration + (1 - alpha) * smoothedDuration;
// alpha = 0.1 ~ 0.3，越小平滑越强
```

### 练习 3: 挑战 — 设计增量重连的消息合并算法 (45min)

**目标**：设计并实现一个增量重连系统，将断线期间的多个 tick 的变化合并为最小化的增量包。

**背景**：服务器以 60 tick/s 运行，每个 tick 记录世界变化日志。玩家断线 5 秒后重连，断线期间有 300 个 tick 的变化记录。直接发送 300 个变化列表是浪费——同一个实体在 300 个 tick 中被修改了 200 次，但客户端只需要最终状态。此外，实体可能在断线期间被创建然后被销毁（净效果为零，无需发送）。

**要求**：
1. 设计一个 `DeltaCompressor`，输入是 300 个 tick 的变化记录，输出压缩后的增量包
2. 压缩规则：
   - 同一 entityId 的多个修改 → 合并为最终状态（丢弃中间状态）
   - 先 SPAWN 后 DESPAWN 的实体 → 从增量包中移除（净效果为零）
   - 先 DESPAWN 后 SPAWN 的实体 → 视为新实体（全量信息）
   - EntityA 被 EntityB 引用（如 Buff 施加者）→ 保留 EntityA 的完整信息
3. 压缩后包大小控制：如果压缩后超过 64KB，则放弃增量方案，改用全量快照
4. 复杂度要求：O(N + M log M)，其中 N 是变化记录数，M 是去重后涉及的实体数

---

## 9. 常见陷阱

### 陷阱 1: 追赶期间的"双写"问题

**现象**：追赶完成后，客户端开始正常游戏。但服务器发来的"直播帧"中有些帧客户端在追赶时已经执行过了。

**根因**：追赶结束时，客户端追到了 `targetFrame`。但 UDP 网络上可能仍有在途的帧包（地址是旧 IP？不，同一连接）。如果服务器的帧包不携带去重信息，客户端可能重复执行同一帧。

**解决方案**：
```csharp
// 客户端维护已执行帧的位图（滑动窗口）
private readonly HashSet<uint> executedFrames = new();
private uint executedFramesWindowStart = 0;

void OnFrameReceived(FrameInput frame) {
    if (frame.FrameNumber < executedFramesWindowStart) return; // 太旧
    if (executedFrames.Contains(frame.FrameNumber)) return;     // 已执行
    ExecuteFrame(frame);
    executedFrames.Add(frame.FrameNumber);
    // 滑动窗口：清理旧帧
    while (executedFrames.Contains(executedFramesWindowStart)) {
        executedFrames.Remove(executedFramesWindowStart);
        executedFramesWindowStart++;
    }
}
```

### 陷阱 2: 追赶期间收到新帧包的并发问题

**现象**：客户端正在以 8x 速度追赶帧 300~500，同时服务器的 UDP 数据流不断发来帧 501、502……如果追赶逻辑和收包逻辑在不同线程，可能出现竞态。

**根因**：追赶引擎在修改游戏状态，收包线程也在"试图"修改游戏状态。

**解决方案**：
```csharp
// 追赶期间：将新收到的帧包缓存到 pendingNewFrames 队列
// 追赶完成时：处理 pendingNewFrames（此时通常只有少量帧）
private readonly Queue<FrameInput> pendingNewFrames = new();

void OnFrameReceived(FrameInput frame) {
    if (isCatchingUp) {
        pendingNewFrames.Enqueue(frame);
        return;  // 不立即执行
    }
    ExecuteFrame(frame);
}

void OnCatchupComplete() {
    while (pendingNewFrames.TryDequeue(out var frame)) {
        ExecuteFrame(frame);
    }
    isCatchingUp = false;
}
```

### 陷阱 3: 快照包含渲染状态导致非确定性

**现象**：从快照恢复后，所有客户端 Hash 校验不一致——但只在重连后出现。

**根因**：快照的序列化/反序列化过程中，包含了渲染相关的非确定性数据（动画播放进度、粒子系统随机种子、LOD 状态等）。这些数据在不同硬件上可能不同，导致 Hash 分歧。

**解决方案**：快照序列化函数中**严格只序列化逻辑状态字段**。使用一个明确的"逻辑状态标记"——给结构体的每个字段标记 `[LogicState]` 或 `[RenderOnly]`，序列化时只取 `[LogicState]` 部分。这比手工"记得哪些字段不能写"更可靠。

### 陷阱 4: RNG 状态的序列化字节序问题

**现象**：断线重连后，所有随机事件偏离——暴击不出、掉落不同、AI 行为改变。

**根因**：RNG 状态是一个 `uint64_t[]` 数组。如果序列化时使用了主机字节序（而非网络字节序），不同平台（x86 小端 vs ARM 大端）的客户端会解析出不同的 RNG 种子。

**解决方案**：始终使用显式的字节序转换（`htonl`/`ntohl` 或 .NET 的 `IPAddress.HostToNetworkOrder`）来序列化 RNG 状态。在序列化层的文档中明确标注"所有多字节整型使用网络字节序（大端）"。

### 陷阱 5: 断线检测阈值配置不当

**现象**：
- 阈值太小（如 500ms 超时）→ WIFI 瞬时波动频繁触发重连，体验差
- 阈值太大（如 10s 超时）→ 真正断线后 10s 才检测到，玩家已经死了

**推荐配置**：

| 游戏类型 | 心跳超时 | 丢包告警 | 丢包断线 | 原因 |
|---------|---------|---------|---------|------|
| MOBA | 3s | 8 个连续丢包 | 20 个 | 操作密集，断线后需要快速检测 |
| FPS/TPS | 2s | 5 个 | 15 个 | 实时性要求最高 |
| MMO | 5s | 15 个 | 40 个 | 可以接受较长检测延迟 |
| 卡牌/回合制 | 10s | 不限 | 心跳超时 | 不需要丢包检测，心跳即可 |

### 陷阱 6: 追赶完成时的渲染同步"跳变"

**现象**：追赶完成瞬间，屏幕上的所有实体"跳"到新位置——角色瞬移、子弹消失、特效闪烁。

**根因**：追赶期间渲染层被冻结（或显示追赶进度条）。追赶完成后的第一帧，渲染层从上一帧的"旧状态"直接跳到"最新逻辑状态"，中间没有插值过渡。

**解决方案**：追赶完成后，不立即同步到渲染层。而是：
1. 标记渲染层为"脏"（所有实体需要重新插值）
2. 在接下来的 3~5 个渲染帧中做平滑过渡（Lerp 从旧位置到新位置）
3. 过渡期间允许轻微的"拉扯感"，但避免瞬移

---

## 10. 扩展阅读

### 必读文章
- **GDC 2017: 'It IS Rocket Science!' — Rocket League 的网络架构**：Jared Cone 详述了 Rocket League 的断线重连和物理状态恢复方案。核心概念：物理模拟状态必须包含刚体速度和角速度（不仅是位置），否则追赶后物体的运动轨迹会偏离。
- **Valve Developer Wiki — Source Multiplayer Networking**：https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking — 包含 Source 引擎的完整重连和 Full Update 机制。
- **Unity Netcode for GameObjects (NGO) — NetworkVariable & Scene Management**：官方文档中关于场景同步和断线重连的实现模式。

### 推荐深入了解
- **Overwatch GDC 2017 — Gameplay Architecture and Netcode**：Tim Ford 和 Phil Orwig 分享的 Overwatch 重连方案。特别关注"快速重连（Fast Reconnect）"——重连时优先恢复玩家自己的英雄，其他英雄按优先级延迟加载。
- **Rainbow Six Siege — Replication Graph and Late Join**：育碧的复制图技术在大型场景中的断线重连优化——只同步玩家可见范围内的实体，而非全量世界。
- **王者荣耀网络同步方案**（中文技术博客系列）：腾讯互娱公开的帧同步重连和赶帧方案细节。

### 开源参考
- **Unreal Engine — Iris Replication System**：UE5 的 Iris 复制系统源码（`Engine/Source/Runtime/Experimental/Iris/`）包含状态增量同步和重连的完整实现。
- **RiptideNetworking**：开源 C# 网络库，包含简单的断线重连示例代码。

---

> **学习建议**：断线重连是网络同步的"最后一公里"。它不像帧同步协议或状态同步那样有清晰的教科书方案——每种游戏类型的实现都不同。建议先理解本章的分级策略（瞬时→短时→长时），然后在实际项目中根据游戏的具体需求（竞技性 vs 休闲性、帧率、实体数量）调整参数。关键参数只有三个：心跳超时阈值、最大追赶帧数、追赶倍率。调好这三个参数，断线重连体验就成功了 80%。
