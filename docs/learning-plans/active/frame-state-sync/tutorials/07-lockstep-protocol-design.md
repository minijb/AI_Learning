---
title: "帧同步协议设计：帧指令、冗余发包、丢包处理"
updated: 2026-06-05
---

# 帧同步协议设计：帧指令、冗余发包、丢包处理

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [[06-deterministic-game-logic|06-确定性游戏逻辑：定点数与跨平台一致性]]

---

## 1. 概念讲解

### 为什么需要协议设计？

假设你已经在第5节理解了 Lockstep 的核心原理，在第6节解决了确定性问题。现在你面前摆着一个具体的工程问题：**"把玩家按的键从一台手机传到另一台手机"这件事，到底怎么用字节流表达？**

帧同步的网络上跑的不是"移动指令"、"攻击指令"这些人类可读的文本，而是一串紧凑的二进制字节。协议层设计的每一 bit 浪费都会在 10 人 × 15fps × 30 分钟的对局中被放大为 MB 级别的额外流量。

同时，UDP 是不可靠传输——包可能丢失、乱序、重复。帧同步协议必须自己处理这一切。本节将完整讲解从单个指令的编码到整帧包的冗余传输的全链路设计。

### 核心思想

帧同步协议设计的四个核心目标：

```
┌─────────────────────────────────────────────────────────────────┐
│                    帧同步协议设计目标                              │
├───────────────┬───────────────┬──────────────┬───────────────────┤
│   紧凑性       │   可靠性       │   实时性      │   可校验性         │
│ (Compactness) │ (Reliability) │ (Real-time)  │ (Verifiability)   │
├───────────────┴───────────────┴──────────────┴───────────────────┤
│  每一 bit 都有意义，每字节带宽都被精打细算                           │
└─────────────────────────────────────────────────────────────────┘
```

---

### 1.1 帧同步消息体系

帧同步网络通信中流转的消息分为三类：

```
┌──────────────────────────────────────────────────┐
│                  消息类型                          │
├──────────────┬────────────────┬──────────────────┤
│  输入指令     │  帧同步包       │  心跳             │
│  (Cmd)       │  (FramePacket) │  (Heartbeat)     │
├──────────────┼────────────────┼──────────────────┤
│ 客户端→服务器 │ 服务器→所有客户端│ 双向              │
│ 单个玩家操作  │ 整帧所有玩家输入│ 连接保活+RTT测量   │
│ 2~8 字节     │ 不定长          │ 4~8 字节          │
└──────────────┴────────────────┴──────────────────┘
```

#### 输入指令 (Input Command)

客户端每次采集到玩家操作后，将其编码为一个或多个指令，发送给服务器。一个指令通常包含：

```
┌──────┬──────────┬──────────────────┐
│Opcode│ PlayerId │  Parameters...   │
│ 1B   │  1B      │  0~6B (变长)     │
└──────┴──────────┴──────────────────┘
```

**关键设计决定：指令是立即发送还是攒 Bucket 后发送？**

- **立即发送**：玩家按下按键立刻发包。延迟最低，但包数量多、带宽大（每个指令都要独立头部）。
- **Bucket 发送**：在一个逻辑帧间隔（如 66ms）内收集所有操作，打包为一个指令列表发送。包数量少、头部开销均摊。这是**王者荣耀等 MOBA 的标准做法**。

#### 帧同步包 (Frame Packet)

服务器收集完本 Turn 所有玩家的指令后，组装成一个帧同步包广播给所有人：

```
┌──────────┬──────────┬────────────┬──────────┬──────────┐
│ FrameId  │ CmdCount │ Commands[] │ Checksum │ Padding  │
│ 4B       │ 1B       │ 变长       │ 4B       │ 0~3B     │
└──────────┴──────────┴────────────┴──────────┴──────────┘
```

**每个客户端拿到相同的 FramePacket，执行相同的逻辑 → 到达相同的状态。** 这是帧同步协议最核心的不变量。

#### 心跳 (Heartbeat)

轻量级的保活消息，同时用于 RTT 测量：

```
┌──────────┬──────────┬──────────┐
│  Type=0  │ ClientId │ Timestamp│
│  1B      │  1B      │  4B      │
└──────────┴──────────┴──────────┘
```

服务器收到后立即回射（echo）——客户端对比发送时间戳和当前时间，得到当前 RTT。心跳频率通常 1~5 秒一次。

---

### 1.2 指令格式设计

#### 操作码 (Opcode) 设计

指令的第一个字节承载操作码。实战中通常用高 4 位表示指令类别，低 4 位表示子类型：

```
Opcode 字节布局 (1 byte):
┌──────────┬──────────┐
│ 高4位     │ 低4位     │
│ 指令类别  │ 子类型    │
└──────────┴──────────┘

类别定义:
0x0_ — 移动类 (Move)
  0x00: 移动到点    (MoveToPoint)     参数: targetX(2B) targetY(2B)  = 5B total
  0x01: 方向移动    (MoveDirection)    参数: dirAngle(1B)              = 2B total
  0x02: 停止移动    (StopMove)         参数: 无                       = 1B total

0x1_ — 攻击类 (Attack)
  0x10: 普通攻击    (NormalAttack)     参数: targetId(2B)              = 3B total
  0x11: 技能释放    (CastSkill)        参数: skillId(1B) targetId(2B)  = 4B total
  0x12: 技能指向    (SkillDirection)   参数: skillId(1B) angle(2B)     = 4B total

0x2_ — 物品类 (Item)
  0x20: 使用物品    (UseItem)          参数: slotId(1B)                = 2B total
  0x21: 购买物品    (BuyItem)          参数: itemId(2B)                = 3B total

0x3_ — 系统类 (System)
  0x30: 投降        (Surrender)        参数: 无                       = 1B total
  0x31: 暂停        (Pause)            参数: 无                       = 1B total
  0x32: 聊天信号    (Ping)             参数: pingType(1B) x(2B) y(2B) = 6B total
```

**设计原则**：
1. **高频指令要短**：MoveDirection（方向移动）在 MOBA 中每秒可能触发数十次，缩到 2 字节。
2. **低频指令可以稍长**：投降指令 1 字节无所谓，一局最多触发一次。
3. **预留扩展空间**：0x4_~0xE_ 留给未来指令类型，0xF_ 做特殊用途（如标记为系统包而非指令）。

#### 位级压缩

对于高频指令，可以用位域将多个字段压入更少的字节：

```csharp
// 未压缩的移动指令: Opcode(1B) + PlayerId(1B) + Flags(1B) + X(2B) + Y(2B) = 7B
// 压缩后的移动指令: PackedMove(3B)

// PackedMove 3字节布局:
// Byte0: [Opcode:4bit][PlayerId:4bit]          — 操作码和玩家ID共享1字节
// Byte1: [DirX:4bit][DirY:4bit]                — 方向量化到16级(-8~+7)
// Byte2: [SkillFlag:1bit][Reserved:7bit]        — 技能标志+预留
//
// 总大小: 3字节 (vs 未压缩7字节) — 节省 57%
```

**方向量化**是帧同步中非常重要的压缩技巧。对于一个摇杆输入，不需要传输精确的角度——将 360° 量化到 16 个方向（每方向 22.5°），4 bit 足够：

```csharp
// 将浮点摇杆值 (-1.0 ~ +1.0) 量化到 4-bit 有符号整数 (-8 ~ +7)
static int QuantizeAxis(float value) {
    // value ∈ [-1.0, 1.0]
    // 映射到 [-8, 7]
    int q = (int)(value * 8.0f);
    return Math.Clamp(q, -8, 7); // 4-bit 有符号范围
}

static float DequantizeAxis(int q) {
    return q / 8.0f; // 还原为浮点(仅用于显示/调试,逻辑层用定点数)
}
```

#### 典型指令大小汇总

| 指令类型 | 大小 | 频率 (每玩家/秒) | 带宽 (bytes/s/玩家) |
|---------|------|-----------------|-------------------|
| 方向移动 (压缩) | 3B | ~10-15次 | 30-45 |
| 普通攻击 | 3B | ~1-2次 | 3-6 |
| 技能释放 | 4B | ~0.5次 | 2 |
| 停止移动 | 1B | ~2-3次 | 2-3 |
| 使用物品 | 2B | ~0.3次 | 0.6 |
| **合计** | | | **~40-55 bytes/s/玩家** |

10 人对战：每个玩家上行 ~50 bytes/s，服务器下行广播 ~500 bytes/s。这在任何网络条件下都毫无压力。

---

### 1.3 帧同步包结构

#### 完整包格式

帧同步包是服务器向所有客户端广播的核心数据结构：

```
Byte offset:
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├───────────────┬───────────────┬───────────────┬───────────────┤
│                            FrameId (uint32)                    │  0..3
├───────────────┬───────────────┬───────────────┬───────────────┤
│  CmdCount     │  SeqNumber    │           Reserved             │  4..7
│  (uint8)      │  (uint8)      │           (uint16)             │
├───────────────┴───────────────┴───────────────┴───────────────┤
│                     Commands[] (变长)                          │  8..
│  ┌──────────┬──────────┬──────────┬──────────────────────┐    │
│  │ PlayerId │ CmdLen   │ Opcode   │ Params...             │    │
│  │ (uint8)  │ (uint8)  │ (uint8)  │ (变长, 0~N bytes)     │    │
│  └──────────┴──────────┴──────────┴──────────────────────┘    │
│  ... (重复 CmdCount 次)                                        │
├───────────────────────────────┬───────────────────────────────┤
│                         CRC32 (uint32)                         │  N..N+3
├───────────────────────────────┴───────────────────────────────┤
│                    Padding (0~3 bytes, 4字节对齐)               │
└───────────────────────────────────────────────────────────────┘
```

#### 字段说明

| 字段 | 大小 | 说明 |
|------|------|------|
| FrameId | 4B | 逻辑帧号，从 0 开始单调递增。客户端用其检测丢帧。 |
| CmdCount | 1B | 本帧包含的指令数量（最多 255 条，即 25 玩家每人 10 条指令，绰绰有余） |
| SeqNumber | 1B | 包序列号（0-255循环），用于检测 UDP 乱序和丢包 |
| Reserved | 2B | 预留字段，可用于协议版本号、加密标志等 |
| Commands[] | 变长 | 指令列表。每条指令的 CmdLen 使得变长解析成为可能 |
| CRC32 | 4B | 整个包（FrameId 到最后一个指令字节）的 CRC32 校验值 |

#### 为什么需要 SeqNumber？

FrameId 是逻辑帧号（15Hz = 每 66ms 一个），而 UDP 包可能在 ms 级别乱序。SeqNumber 提供更细粒度的包排序能力——同一个 FrameId 如果冗余发送了 3 次，3 个 UDP 包有相同的 FrameId 但不同的 SeqNumber（且 CRC32 相同），接收方可以安全去重。

---

### 1.4 冗余发包机制

UDP 是不可靠的——在移动网络（4G/5G）下，丢包率通常在 0.5%~5%，WiFi 下可能更低但也可能因干扰突发升高。帧同步协议的核心应对策略是**冗余发包 (Redundant Sending)**。

#### 基本原理

```
时间线 (服务器):
         Frame N         Frame N+1       Frame N+2
            │                │               │
  ──────────┼────────────────┼───────────────┼──────────→
            │                │               │
  发送:    P(N)            P(N+1)          P(N+2)
          P(N)            P(N+1)          P(N+2)
          P(N)                            P(N+2)
            │                │               │
  冗余度=3  冗余度=2        冗余度=3
```

服务器对同一个 FramePacket 发送多次（通常 2~5 次）。每个拷贝是**完全相同的字节序列**（包括相同的 CRC32）。客户端收到任何一个拷贝即可推进逻辑帧；收到多个拷贝则根据 SeqNumber 去重丢弃。

#### 冗余度 vs 带宽的权衡

| 冗余度 | 丢包容忍率 | 带宽倍率 | 适用场景 |
|--------|-----------|---------|---------|
| 1 | 0% | 1× | 理想网络（局域网） |
| 2 | ~5% | 2× | WiFi 环境 |
| 3 | ~10% | 3× | 4G 移动网络 |
| 5 | ~20% | 5× | 极端弱网 |

发包间隔也很重要——如果冗余包之间间隔太短，一个网络突发丢包会吞掉所有拷贝。理想做法是**交错发送**：

```
不是:  P(N) P(N) P(N)  ← 三个拷贝连着发，一个突发丢包全丢
而是:  P(N) P(N-1) P(N) P(N-2) P(N)  ← 拷贝散布在不同时间点
```

**交错冗余示例**（冗余度 3，每逻辑帧发送窗口 66ms）：

```
t=0ms:    发送 P(N)#1 (Seq=0)
t=16ms:   发送 P(N)#2 (Seq=1)
t=33ms:   发送 P(N)#3 (Seq=2) + P(N-1)#3 (交错)
t=50ms:   发送 P(N-2)#3 (交错)
t=66ms:   下一帧开始...
```

交错策略使得单个突发丢包（通常持续 10~30ms）最多丢失 2 个相邻包，而不会丢失所有拷贝。

#### 冗余度自适应

固定冗余度要么浪费带宽（网络好时），要么保护不足（网络差时）。自适应算法根据丢包率动态调整：

```
冗余度自适应状态机:
                    ┌──────────┐
        丢包率<1%   │  R = 2   │  丢包率>5%
     ┌──────────────┤ (正常)   ├──────────────┐
     │              └──────────┘              │
     ▼                                        ▼
┌──────────┐                          ┌──────────┐
│  R = 1   │  丢包率>3%               │  R = 3   │  丢包率>10%
│ (低冗余) │◄─────────────────────────│ (高冗余) ├──────────────┐
└──────────┘                          └──────────┘              │
     ▲                                                          ▼
     │              ┌──────────┐                        ┌──────────┐
     └──────────────│  R = 5   │◄───────────────────────│  R = 5   │
        丢包率<7%   │ (极限)   │     丢包率>15%          │ (极限)   │
                    └──────────┘                        └──────────┘
```

**自适应算法核心逻辑**：

```cpp
// 每 2 秒评估一次丢包率，调整冗余度
void AdaptiveRedundancy::Update(float loss_rate) {
    // 使用 EWMA (指数加权移动平均) 平滑丢包率
    smoothed_loss_ = smoothed_loss_ * 0.7f + loss_rate * 0.3f;
    
    if (smoothed_loss_ < 0.01f) {
        redundancy_ = 1;  // 几乎不丢包 → 不冗余
    } else if (smoothed_loss_ < 0.03f) {
        redundancy_ = 2;  // 正常
    } else if (smoothed_loss_ < 0.08f) {
        redundancy_ = 3;  // 较差
    } else if (smoothed_loss_ < 0.15f) {
        redundancy_ = 5;  // 很差
    } else {
        redundancy_ = 5;  // 极限，不再增加（节省上行带宽）
        // 此时应该触发玩家"网络不佳"提示
    }
}
```

**关键要点**：
- 用 EWMA 而非瞬时丢包率——避免因单个丢包剧烈抖动
- 冗余度有上限（通常 5）——UDP 丢包是突发性的，发 100 次也可能被同一突发吞掉
- 升冗余快、降冗余慢（不对称迟滞）——宁可多浪费带宽，也比突然丢帧导致卡顿好

---

### 1.5 丢包处理策略

冗余发包不能 100% 解决丢包问题。当所有冗余拷贝都丢失时，需要更进一步的恢复策略。

#### 策略一：FEC（前向纠错）—— XOR 冗余包

基本思想：**不重传原始包，而是传输可推导的"校验包"。**

**XOR FEC 原理**（最简单的 FEC 变体）：

```
每 N 个数据包生成 1 个 XOR 冗余包:
  FEC_Packet = P(1) XOR P(2) XOR P(3) XOR ... XOR P(N)

如果丢失了 P(k)，可以用其余包 + FEC 包恢复:
  P(k) = P(1) XOR P(2) XOR ... XOR P(k-1) XOR P(k+1) XOR ... XOR P(N) XOR FEC_Packet
```

**帧同步中的 FEC 方案**：

```
Group 0: P(0) P(1) P(2) → XOR → FEC(0)
Group 1: P(3) P(4) P(5) → XOR → FEC(1)
...

发送顺序:
  P(0) P(1) P(2) FEC(0) P(3) P(4) P(5) FEC(1) ...
  
如果在一组中丢失了恰好 1 个数据包 → 可以从 FEC 恢复
如果丢失 ≥2 个 → FEC 无法恢复，需要重传
```

**参数选择**：
- N=3，冗余率 33%（4 个包中 1 个是 FEC）→ 可容忍每组丢 1 个
- N=5，冗余率 20%（6 个包中 1 个是 FEC）→ 可容忍每组丢 1 个，带宽开销更低
- N=2，冗余率 50%（3 个包中 1 个是 FEC）→ 每组可恢复，但带宽翻倍

帧同步中通常 N=3~5，与冗余发包叠加使用。**FEC 和冗余发包不是互斥的**——两者结合效果更好：

```
混合策略: 冗余度 R=2, FEC 组大小 N=3

时间轴:
  P0#1  P0#2  P1#1  P1#2  P2#1  P2#2  F0#1  F0#2  P3#1  ...
  └─── Frame0 ──┘└─── Frame1 ──┘└─── Frame2 ──┘└─FEC(0-2)─┘

每个包冗余 2 份 + 每 3 帧额外 XOR 冗余
→ 可以容忍: 每组最多丢 1 帧（通过 FEC 恢复）且单个包丢 1 份（通过冗余恢复）
```

#### 策略二：丢包重传（NACK）

**核心思想**：不是超时自动重传（TCP 模式），而是**接收方检测到丢帧后主动请求重传**。

```
正常流程:
  Server ──P(5)──► Client
  Server ──P(6)──► Client
  Server ──P(7)──► Client  ← 丢失
  Server ──P(8)──► Client  ← 收到! 发现 SeqNumber 从 6 跳到 8
  Client ──NACK(FrameId=7)──► Server  ← 请求重传
  Server ──P(7)[retransmit]──► Client  ← 重传特定帧
```

**FrameId 间隙检测**：

```cpp
// 客户端收到帧同步包时的处理
void OnFramePacketReceived(const FramePacket& packet) {
    uint32_t received_frame = packet.header.frame_id;
    
    // 情况 1: 正常顺序 → 直接处理
    if (received_frame == expected_frame_) {
        ProcessFrame(packet);
        expected_frame_++;
        
        // 处理缓冲区中已到达的后续帧
        while (buffered_frames_.count(expected_frame_)) {
            ProcessFrame(buffered_frames_[expected_frame_]);
            buffered_frames_.erase(expected_frame_);
            expected_frame_++;
        }
        return;
    }
    
    // 情况 2: 未来帧 → 有丢帧！发送 NACK
    if (received_frame > expected_frame_) {
        // 请求重传所有缺失的帧
        for (uint32_t fid = expected_frame_; fid < received_frame; fid++) {
            SendNack(fid);
        }
        // 缓存当前帧，等待缺失帧到达
        buffered_frames_[received_frame] = packet;
        return;
    }
    
    // 情况 3: 过去帧 → 冗余包/重传包，直接丢弃
    // (已经处理过了)
}
```

**NACK 的设计考量**：

1. **NACK 抑制**：同一个缺失帧只发一次 NACK（或限频，如每 50ms 最多一次），避免网络拥塞时 NACK 风暴。
2. **NACK 超时**：如果发出 NACK 后 200ms 仍未收到重传包，放弃该帧——用空指令填充继续前进，不能无限等待。
3. **批量 NACK**：将多个缺失帧合并到一个 NACK 包中（用位图表示），减少包数量。

```
批量 NACK 包格式:
┌──────────┬──────────┬──────────┬──────────────────┐
│  Type=2  │ BaseFid  │ Count    │ MissingBitmap    │
│  1B      │  4B      │  1B      │  (Count bits)    │
└──────────┴──────────┴──────────┴──────────────────┘

BaseFid = 100, Count = 8, Bitmap = 0b00100101
→ 缺失帧: 100, 102, 105
```

#### 策略三：空指令填充

当 FEC 恢复失败、重传也超时时，**不能无限等待**——需要用空指令（Empty Command）填充缺失帧，让游戏继续。

```cpp
// 超时处理：用空指令填充并继续
void OnFrameTimeout(uint32_t frame_id) {
    // 为每个玩家生成空输入
    FramePacket empty_packet;
    empty_packet.header.frame_id = frame_id;
    empty_packet.header.cmd_count = player_count_;
    
    for (int i = 0; i < player_count_; i++) {
        FrameCommand cmd;
        cmd.player_id = i;
        cmd.opcode = CMD_EMPTY;  // 空操作
        cmd.param_length = 0;
        empty_packet.commands.push_back(cmd);
    }
    
    // 用空指令推进游戏状态
    ProcessFrame(empty_packet);
    expected_frame_++;
    
    LogWarning("Frame %u timed out, filled with empty commands", frame_id);
}
```

**不同玩家丢帧时的处理差异**：

| 丢失的帧是… | 游戏体验影响 |
|------------|------------|
| 自己的输入帧 | 操作延迟感增强，角色短暂"不听使唤" |
| 其他玩家的输入帧 | 该玩家角色短暂"静止"（使用上一帧输入重复） |
| 服务器的广播帧 | 所有玩家画面短暂暂停（最糟糕的情况） |

**实践经验**：对已丢失帧，使用"上一帧的输入"比"空指令"更好——角色至少保持之前的行为惯性（继续移动/攻击），而不是突然停下来。这叫 **Input Repeat（输入重复）** 策略。

```
丢帧处理决策树:
                    ┌─ 收到包? ──Yes──► 正常处理
                    │
  期望收到 Frame N ─┤                   ┌─ FEC 可恢复? ──Yes──► XOR 恢复
                    │                   │
                    └─ 超时 ──► 丢帧! ──┤                   ┌─ 成功 ──► 正常处理
                                        │                   │
                                        └─ 发送 NACK ──────┤
                                                            │
                                          ┌─ 超时 200ms ───┤
                                          │                 └─ 失败 ──► 空指令/输入重复填充
                                          │
                                          └─ 收到重传 ──► 正常处理
```

---

### 1.6 粘包/拆包

UDP 虽然是"数据报"协议（每个 sendto 对应一个 recvfrom），但在帧同步的客户端接收层，我们通常从 UDP Socket 批量读取以提高效率。此外，如果底层使用 KCP/ENet 等可靠 UDP 库，它们内部会对小包进行合并（粘包）。因此**应用层拆包是必须的**。

#### 基于长度的帧切分

最经典的方案——TLV 风格的长度前缀：

```
UDP 流中的多个帧:
┌──────┬────────────┬──────┬──────────────┬──────┬─────────┐
│ Len1 │  Packet1   │ Len2 │   Packet2    │ Len3 │ Packet3 │
│ 2B   │  Len1 bytes│ 2B   │  Len2 bytes  │ 2B   │         │
└──────┴────────────┴──────┴──────────────┴──────┴─────────┘
```

每个包用 2 字节长度前缀标记，接收方按长度切分。

#### 环形缓冲区实现

接收方使用环形缓冲区（Ring Buffer）来高效处理粘包/拆包：

```cpp
// 环形缓冲区: 解决粘包/拆包的核心数据结构
class RingBuffer {
    static constexpr size_t CAPACITY = 65536; // 64KB
    uint8_t buffer_[CAPACITY];
    size_t read_pos_ = 0;   // 下次读取位置
    size_t write_pos_ = 0;  // 下次写入位置
    size_t available_ = 0;  // 可读字节数
    
public:
    // 从 Socket 读取数据追加到缓冲区
    size_t AppendFromSocket(int sockfd) {
        // 计算可写入的连续空间
        size_t tail_space = CAPACITY - write_pos_;
        size_t bytes_read;
        
        if (tail_space >= 2048) {
            // 尾部空间足够，直接读入
            bytes_read = recv(sockfd, buffer_ + write_pos_, tail_space, 0);
        } else {
            // 尾部空间不足，回绕到开头
            bytes_read = recv(sockfd, buffer_, CAPACITY - write_pos_, 0);
        }
        
        if (bytes_read > 0) {
            write_pos_ = (write_pos_ + bytes_read) % CAPACITY;
            available_ += bytes_read;
        }
        return bytes_read;
    }
    
    // 尝试提取一个完整帧
    bool TryExtractPacket(std::vector<uint8_t>& out) {
        if (available_ < 2) return false; // 连长度前缀都不够
        
        // 读取 2 字节长度（大端序）
        uint16_t pkt_len = ReadU16At(read_pos_);
        
        if (available_ < 2 + pkt_len) return false; // 包体不完整
        
        // 拷贝完整包
        out.resize(pkt_len);
        CopyFrom(read_pos_ + 2, out.data(), pkt_len);
        
        // 推进读指针
        size_t consumed = 2 + pkt_len;
        read_pos_ = (read_pos_ + consumed) % CAPACITY;
        available_ -= consumed;
        
        return true;
    }
    
private:
    uint16_t ReadU16At(size_t pos) {
        size_t p = pos % CAPACITY;
        return (buffer_[p] << 8) | buffer_[p + 1]; // 大端
    }
    
    void CopyFrom(size_t pos, uint8_t* dst, size_t len) {
        for (size_t i = 0; i < len; i++) {
            dst[i] = buffer_[(pos + i) % CAPACITY];
        }
    }
};
```

**环形缓冲区的优势**：
- 零拷贝读取（直接从 buffer 位置读取长度前缀做判断）
- 不需要在每次收包后 memmove 数据
- 天然支持流式处理——多个小包可能在一个 recv 中到达，半个大包可能跨两次 recv

---

### 1.7 校验机制

帧同步包在网络传输中可能损坏（bit flip）。UDP 虽然有 16-bit 校验和，但它是可选的（IPv4）且只覆盖 UDP 头部+数据。应用层校验是**必须的**。

#### CRC32

CRC32 是最常用的帧校验算法。它计算快（硬件加速或查表法）、碰撞概率低（2^-32）。

**CRC32 查表法实现**（标准 IEEE 802.3 多项式 0xEDB88320）：

```cpp
// CRC32 查找表 (预计算)
static uint32_t crc32_table[256];
static bool crc32_initialized = false;

static void InitCRC32Table() {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t crc = i;
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320 : 0);
        }
        crc32_table[i] = crc;
    }
    crc32_initialized = true;
}

uint32_t CRC32(const uint8_t* data, size_t len) {
    if (!crc32_initialized) InitCRC32Table();
    
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc = (crc >> 8) ^ crc32_table[(crc ^ data[i]) & 0xFF];
    }
    return crc ^ 0xFFFFFFFF;
}
```

**在帧同步中的应用**：

1. **发送方**：计算 FrameId 到最后一个指令字节的 CRC32，填入包尾。
2. **接收方**：收到包后重新计算 CRC32，与包尾的 CRC32 比较。不匹配 → 丢弃（等待冗余包或触发 NACK）。
3. **校验范围不包括 CRC32 字段自身和 Padding**——这是标准做法。

#### Adler32

Adler32 比 CRC32 更快（不需要查表），但碰撞概率更高。适合对性能极度敏感的场景（如每帧校验数百个小包）：

```cpp
uint32_t Adler32(const uint8_t* data, size_t len) {
    const uint32_t MOD_ADLER = 65521;
    uint32_t a = 1, b = 0;
    
    for (size_t i = 0; i < len; i++) {
        a = (a + data[i]) % MOD_ADLER;
        b = (b + a) % MOD_ADLER;
    }
    return (b << 16) | a;
}
```

**选择建议**：
- 帧同步包（较大，每帧 1~3 个包）→ **CRC32**，碰撞风险更低
- 心跳包/指令包（小包，高频）→ Adler32 可接受

#### 实践中的校验流程

```
发送方:
  1. 序列化 FramePacket 到字节数组
  2. 计算 bytes[0..N-1] 的 CRC32
  3. 将 CRC32 追加到数组末尾
  4. 添加 2 字节长度前缀
  5. 通过 UDP Socket 发送

接收方:
  1. 从环形缓冲区提取一个完整帧 (通过长度前缀)
  2. 提取最后 4 字节作为声称的 CRC32
  3. 对其余字节重新计算 CRC32
  4. 比较两个 CRC32:
     - 匹配 → 解包处理
     - 不匹配 → 丢弃，等待冗余/FEC/NACK
```

---

## 2. 代码示例

### 2.1 Unity C#：FramePacket 编解码完整实现

```csharp
// FramePacket.cs — Unity C# 帧同步协议层完整实现
// 使用方式: 将此文件放入 Unity 项目的 Scripts/Network/ 目录

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace LockstepProtocol
{
    #region 指令定义

    /// <summary>
    /// 操作码枚举 — 高4位=类别，低4位=子类型
    /// </summary>
    public enum CommandOpcode : byte
    {
        // 移动类 (0x0_)
        MoveToPoint    = 0x00,  // 移动到目标点: targetX(2B) targetY(2B)
        MoveDirection  = 0x01,  // 方向移动:     dirAngle(1B)
        StopMove       = 0x02,  // 停止移动:     无参数

        // 攻击类 (0x1_)
        NormalAttack   = 0x10,  // 普通攻击:     targetId(2B)
        CastSkill      = 0x11,  // 技能释放:     skillId(1B) targetId(2B)
        SkillDirection = 0x12,  // 技能指向:     skillId(1B) angle(2B)

        // 物品类 (0x2_)
        UseItem        = 0x20,  // 使用物品:     slotId(1B)
        BuyItem        = 0x21,  // 购买物品:     itemId(2B)

        // 系统类 (0x3_)
        Surrender      = 0x30,  // 投降:         无参数
        Pause          = 0x31,  // 暂停:         无参数
        Ping           = 0x32,  // 聊天信号:     pingType(1B) x(2B) y(2B)

        // 特殊
        Empty          = 0xF0,  // 空指令(丢帧填充用)
    }

    /// <summary>
    /// 单条帧指令
    /// </summary>
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    public struct FrameCommand
    {
        public byte PlayerId;       // 玩家ID (0~255)
        public CommandOpcode Opcode; // 操作码
        public byte ParamLength;     // 参数长度(字节数)
        public byte[] Parameters;    // 参数数据(变长)

        /// <summary>指令总字节数（含头部）</summary>
        public int TotalSize => 3 + ParamLength; // PlayerId(1) + Opcode(1) + ParamLength(1) + Params

        /// <summary>创建空指令</summary>
        public static FrameCommand CreateEmpty(byte playerId)
        {
            return new FrameCommand
            {
                PlayerId = playerId,
                Opcode = CommandOpcode.Empty,
                ParamLength = 0,
                Parameters = Array.Empty<byte>()
            };
        }

        /// <summary>创建方向移动指令（最常用、最紧凑）</summary>
        public static FrameCommand CreateMoveDir(byte playerId, sbyte dx, sbyte dy)
        {
            return new FrameCommand
            {
                PlayerId = playerId,
                Opcode = CommandOpcode.MoveDirection,
                ParamLength = 1,
                // 将 dx,dy 打包进 1 字节: 高4位=dx(-8~+7), 低4位=dy(-8~+7)
                Parameters = new byte[] { (byte)(((dx & 0x0F) << 4) | (dy & 0x0F)) }
            };
        }
    }

    #endregion

    #region 帧同步包

    /// <summary>
    /// 帧同步包头（固定 8 字节）
    /// </summary>
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    public struct FramePacketHeader
    {
        public uint FrameId;      // 逻辑帧号 (0, 1, 2, ...)
        public byte CmdCount;     // 本帧指令数量
        public byte SeqNumber;    // 包序列号 (0~255 循环)
        public ushort Reserved;   // 预留

        public const int SIZE = 8; // 固定头大小
    }

    /// <summary>
    /// 完整的帧同步包 — 含编解码逻辑
    /// </summary>
    public class FramePacket
    {
        public FramePacketHeader Header;
        public List<FrameCommand> Commands;
        public uint Checksum; // CRC32

        public FramePacket()
        {
            Commands = new List<FrameCommand>();
        }

        #region 序列化 (Encode)

        /// <summary>
        /// 将 FramePacket 编码为字节数组（含 CRC32）
        /// 返回: 完整的可发送字节数组
        /// </summary>
        public byte[] Encode()
        {
            // 第一步: 计算总大小
            int totalSize = FramePacketHeader.SIZE; // 头部 8 字节
            foreach (var cmd in Commands)
            {
                totalSize += cmd.TotalSize; // 每条指令: 3(头部) + ParamLength
            }
            int payloadSize = totalSize; // 不含 CRC32 的数据大小
            totalSize += 4; // CRC32 4 字节

            // 第二步: 分配缓冲区并写入
            byte[] buffer = new byte[totalSize];
            int offset = 0;

            // 写入 FrameId (Little-Endian)
            WriteUInt32LE(buffer, ref offset, Header.FrameId);
            // 写入 CmdCount
            buffer[offset++] = Header.CmdCount;
            // 写入 SeqNumber
            buffer[offset++] = Header.SeqNumber;
            // 写入 Reserved
            WriteUInt16LE(buffer, ref offset, Header.Reserved);

            // 写入指令列表
            foreach (var cmd in Commands)
            {
                buffer[offset++] = cmd.PlayerId;
                buffer[offset++] = (byte)cmd.Opcode;
                buffer[offset++] = cmd.ParamLength;
                if (cmd.ParamLength > 0)
                {
                    Buffer.BlockCopy(cmd.Parameters, 0, buffer, offset, cmd.ParamLength);
                    offset += cmd.ParamLength;
                }
            }

            // 第三步: 计算 CRC32（覆盖 Header + Commands 部分）
            Checksum = CRC32.Compute(buffer, 0, payloadSize);
            WriteUInt32LE(buffer, ref offset, Checksum);

            return buffer;
        }

        #endregion

        #region 反序列化 (Decode)

        /// <summary>
        /// 从字节数组解码 FramePacket。
        /// 返回 null 表示校验失败（数据损坏）。
        /// </summary>
        public static FramePacket Decode(byte[] buffer, int offset, int length)
        {
            if (length < FramePacketHeader.SIZE + 4) // 至少要有头部 + CRC32
                return null;

            int startOffset = offset;
            int payloadSize = length - 4; // 不含 CRC32 的数据大小

            // 第一步: 校验 CRC32
            uint claimedChecksum = ReadUInt32LE(buffer, offset + payloadSize);
            uint computedChecksum = CRC32.Compute(buffer, offset, payloadSize);
            if (claimedChecksum != computedChecksum)
                return null; // 数据损坏，丢弃

            // 第二步: 解析头部
            FramePacket packet = new FramePacket();
            packet.Checksum = claimedChecksum;

            packet.Header.FrameId   = ReadUInt32LE(buffer, ref offset);
            packet.Header.CmdCount  = buffer[offset++];
            packet.Header.SeqNumber = buffer[offset++];
            packet.Header.Reserved  = ReadUInt16LE(buffer, ref offset);

            // 第三步: 解析指令列表
            for (int i = 0; i < packet.Header.CmdCount; i++)
            {
                if (offset + 3 > startOffset + payloadSize)
                    return null; // 数据不完整

                FrameCommand cmd = new FrameCommand();
                cmd.PlayerId    = buffer[offset++];
                cmd.Opcode      = (CommandOpcode)buffer[offset++];
                cmd.ParamLength = buffer[offset++];

                if (cmd.ParamLength > 0)
                {
                    if (offset + cmd.ParamLength > startOffset + payloadSize)
                        return null; // 参数数据越界

                    cmd.Parameters = new byte[cmd.ParamLength];
                    Buffer.BlockCopy(buffer, offset, cmd.Parameters, 0, cmd.ParamLength);
                    offset += cmd.ParamLength;
                }
                else
                {
                    cmd.Parameters = Array.Empty<byte>();
                }

                packet.Commands.Add(cmd);
            }

            return packet;
        }

        #endregion

        #region 辅助: Little-Endian 读写

        private static void WriteUInt32LE(byte[] buf, ref int offset, uint val)
        {
            buf[offset++] = (byte)(val);
            buf[offset++] = (byte)(val >> 8);
            buf[offset++] = (byte)(val >> 16);
            buf[offset++] = (byte)(val >> 24);
        }

        private static void WriteUInt16LE(byte[] buf, ref int offset, ushort val)
        {
            buf[offset++] = (byte)(val);
            buf[offset++] = (byte)(val >> 8);
        }

        private static uint ReadUInt32LE(byte[] buf, ref int offset)
        {
            uint val = (uint)(buf[offset] | (buf[offset + 1] << 8) |
                              (buf[offset + 2] << 16) | (buf[offset + 3] << 24));
            offset += 4;
            return val;
        }

        private static uint ReadUInt32LE(byte[] buf, int offset)
        {
            return (uint)(buf[offset] | (buf[offset + 1] << 8) |
                          (buf[offset + 2] << 16) | (buf[offset + 3] << 24));
        }

        private static ushort ReadUInt16LE(byte[] buf, ref int offset)
        {
            ushort val = (ushort)(buf[offset] | (buf[offset + 1] << 8));
            offset += 2;
            return val;
        }

        #endregion
    }

    #endregion

    #region CRC32

    /// <summary>
    /// CRC32 查表法实现（IEEE 802.3 多项式）
    /// </summary>
    public static class CRC32
    {
        private static readonly uint[] Table = new uint[256];
        private static bool _initialized = false;

        private static void Initialize()
        {
            if (_initialized) return;
            for (uint i = 0; i < 256; i++)
            {
                uint crc = i;
                for (int j = 0; j < 8; j++)
                {
                    crc = (crc >> 1) ^ ((crc & 1) != 0 ? 0xEDB88320u : 0u);
                }
                Table[i] = crc;
            }
            _initialized = true;
        }

        public static uint Compute(byte[] data, int offset, int length)
        {
            Initialize();
            uint crc = 0xFFFFFFFF;
            for (int i = 0; i < length; i++)
            {
                crc = (crc >> 8) ^ Table[(crc ^ data[offset + i]) & 0xFF];
            }
            return crc ^ 0xFFFFFFFF;
        }
    }

    #endregion

    #region 丢包检测与 NACK

    /// <summary>
    /// 客户端帧接收管理器 — 处理丢帧检测与重传请求
    /// </summary>
    public class FrameReceiver
    {
        private uint _expectedFrameId = 0;
        private readonly Dictionary<uint, FramePacket> _bufferedFrames = new();
        private readonly HashSet<uint> _nackSentFrames = new(); // 已发送过 NACK 的帧(防重复)
        private readonly Queue<uint> _nackTimeoutQueue = new(); // NACK 超时队列

        /// <summary>收到帧包时调用</summary>
        public FrameProcessResult OnFrameReceived(FramePacket packet)
        {
            uint fid = packet.Header.FrameId;

            // 过去帧(冗余包/重传包) → 丢弃
            if (fid < _expectedFrameId)
            {
                _nackSentFrames.Remove(fid); // 清理 NACK 记录
                return FrameProcessResult.AlreadyProcessed;
            }

            // 未来帧 → 有丢帧!
            if (fid > _expectedFrameId)
            {
                // 缓存当前包
                _bufferedFrames[fid] = packet;

                // 发射 NACK
                for (uint missing = _expectedFrameId; missing < fid; missing++)
                {
                    if (!_nackSentFrames.Contains(missing))
                    {
                        _nackSentFrames.Add(missing);
                        return FrameProcessResult.NeedNack(missing);
                    }
                }

                return FrameProcessResult.Buffered;
            }

            // fid == _expectedFrameId → 正常
            _bufferedFrames[fid] = packet;

            // 处理当前帧及缓冲区中连续的后续帧
            var results = new List<FrameProcessResult>();
            while (_bufferedFrames.TryGetValue(_expectedFrameId, out var buffered))
            {
                results.Add(FrameProcessResult.Ready(buffered));
                _bufferedFrames.Remove(_expectedFrameId);
                _nackSentFrames.Remove(_expectedFrameId);
                _expectedFrameId++;
            }

            // 返回第一个结果（实际使用中应该逐个处理）
            return results.Count > 0 ? results[0] : FrameProcessResult.Buffered;
        }

        /// <summary>NACK 超时处理 — 每帧调用,对超时的缺失帧用空指令填充</summary>
        public FramePacket[] CheckNackTimeouts(float now, float nackTimeout = 0.2f)
        {
            // 简化实现：对 _expectedFrameId 之前仍标记为 NACK 的帧进行超时处理
            var timeouts = new List<FramePacket>();
            // 生产代码需要维护"每个 NACK 的发送时间"来精确判断超时
            return timeouts.ToArray();
        }
    }

    /// <summary>
    /// 帧处理结果
    /// </summary>
    public class FrameProcessResult
    {
        public enum Type { Ready, NeedNack, Buffered, AlreadyProcessed }

        public Type ResultType;
        public FramePacket Packet;        // Ready 时有值
        public uint MissingFrameId;       // NeedNack 时有值

        public static FrameProcessResult Ready(FramePacket p) =>
            new() { ResultType = Type.Ready, Packet = p };
        public static FrameProcessResult NeedNack(uint fid) =>
            new() { ResultType = Type.NeedNack, MissingFrameId = fid };
        public static readonly FrameProcessResult Buffered =
            new() { ResultType = Type.Buffered };
        public static readonly FrameProcessResult AlreadyProcessed =
            new() { ResultType = Type.AlreadyProcessed };
    }

    #endregion
}
```

---

### 2.2 C++：帧同步协议层实现

```cpp
// lockstep_protocol.h — C++ 帧同步协议层
// 目标平台: Windows/Linux/Android/iOS 跨平台
// 依赖: C++17, 无第三方库

#pragma once

#include <cstdint>
#include <vector>
#include <array>
#include <cstring>
#include <algorithm>
#include <stdexcept>

namespace lockstep {

// ============================================================
// 常量定义
// ============================================================
constexpr uint8_t  PROTOCOL_VERSION  = 1;
constexpr size_t   MAX_PLAYERS       = 32;
constexpr size_t   MAX_COMMANDS_PER_FRAME = 255;
constexpr size_t   MAX_PACKET_SIZE   = 1500;  // 不超过 MTU

// ============================================================
// 操作码
// ============================================================
enum class Opcode : uint8_t {
    // 移动类 (0x0_)
    MoveToPoint    = 0x00,
    MoveDirection  = 0x01,
    StopMove       = 0x02,
    // 攻击类 (0x1_)
    NormalAttack   = 0x10,
    CastSkill      = 0x11,
    SkillDirection = 0x12,
    // 物品类 (0x2_)
    UseItem        = 0x20,
    BuyItem        = 0x21,
    // 系统类 (0x3_)
    Surrender      = 0x30,
    Pause          = 0x31,
    Ping           = 0x32,
    // 特殊
    Empty          = 0xF0,
};

// ============================================================
// 单条指令 — 固定头部 + 变长参数
// ============================================================
struct alignas(1) FrameCommand {
    uint8_t  player_id;
    Opcode   opcode;
    uint8_t  param_length;  // 0~255
    uint8_t  params[255];   // 内联存储,避免小对象堆分配

    // 序列化到缓冲区,返回写入的字节数
    size_t serialize(uint8_t* dst) const {
        dst[0] = player_id;
        dst[1] = static_cast<uint8_t>(opcode);
        dst[2] = param_length;
        if (param_length > 0) {
            std::memcpy(dst + 3, params, param_length);
        }
        return 3 + param_length;
    }

    // 从缓冲区反序列化,返回读取的字节数; 0 表示失败
    size_t deserialize(const uint8_t* src, size_t max_len) {
        if (max_len < 3) return 0;
        player_id   = src[0];
        opcode      = static_cast<Opcode>(src[1]);
        param_length = src[2];
        if (max_len < 3 + param_length) return 0;
        if (param_length > 0) {
            std::memcpy(params, src + 3, param_length);
        }
        return 3 + param_length;
    }

    // 便捷工厂方法
    static FrameCommand make_move_dir(uint8_t pid, int8_t dx, int8_t dy) {
        FrameCommand cmd{};
        cmd.player_id = pid;
        cmd.opcode    = Opcode::MoveDirection;
        cmd.param_length = 1;
        cmd.params[0] = static_cast<uint8_t>(((dx & 0x0F) << 4) | (dy & 0x0F));
        return cmd;
    }

    static FrameCommand make_empty(uint8_t pid) {
        FrameCommand cmd{};
        cmd.player_id = pid;
        cmd.opcode    = Opcode::Empty;
        cmd.param_length = 0;
        return cmd;
    }
};
static_assert(sizeof(FrameCommand) >= 3, "FrameCommand too small");

// ============================================================
// 帧同步包头 (固定 8 字节)
// ============================================================
#pragma pack(push, 1)
struct FramePacketHeader {
    uint32_t frame_id;    // 逻辑帧号
    uint8_t  cmd_count;   // 指令数量
    uint8_t  seq_number;  // 包序号 (0~255 循环)
    uint16_t reserved;    // 预留

    static constexpr size_t SIZE = 8;
};
#pragma pack(pop)
static_assert(sizeof(FramePacketHeader) == 8, "Header must be 8 bytes");

// ============================================================
// 完整的帧同步包
// ============================================================
class FramePacket {
public:
    FramePacketHeader header{};
    std::vector<FrameCommand> commands;
    uint32_t checksum = 0;

    // ---- 序列化 ----
    // 将包编码到缓冲区,返回总字节数。buffer 必须 >= MAX_PACKET_SIZE
    size_t encode(uint8_t* buffer) const {
        size_t offset = 0;

        // 写入头部 (使用 memcpy 避免未对齐访问)
        write_u32_le(buffer + offset, header.frame_id);   offset += 4;
        buffer[offset++] = header.cmd_count;
        buffer[offset++] = header.seq_number;
        write_u16_le(buffer + offset, header.reserved);   offset += 2;

        // 写入指令
        for (const auto& cmd : commands) {
            offset += cmd.serialize(buffer + offset);
        }

        // 计算并写入 CRC32
        size_t payload_size = offset;
        uint32_t crc = crc32(buffer, payload_size);
        write_u32_le(buffer + offset, crc);
        offset += 4;

        return offset;
    }

    // ---- 反序列化 ----
    // 从缓冲区解码。返回 true 表示成功; false 表示 CRC 校验失败或数据格式错误
    bool decode(const uint8_t* buffer, size_t length) {
        if (length < FramePacketHeader::SIZE + 4) return false;

        size_t payload_size = length - 4;

        // CRC 校验
        uint32_t claimed = read_u32_le(buffer + payload_size);
        uint32_t computed = crc32(buffer, payload_size);
        if (claimed != computed) return false;
        checksum = claimed;

        // 解析头部
        size_t offset = 0;
        header.frame_id  = read_u32_le(buffer + offset); offset += 4;
        header.cmd_count = buffer[offset++];
        header.seq_number = buffer[offset++];
        header.reserved  = read_u16_le(buffer + offset); offset += 2;

        // 解析指令
        commands.clear();
        commands.reserve(header.cmd_count);

        for (uint8_t i = 0; i < header.cmd_count; ++i) {
            FrameCommand cmd{};
            size_t consumed = cmd.deserialize(buffer + offset, payload_size - offset);
            if (consumed == 0) return false; // 数据不完整
            commands.push_back(cmd);
            offset += consumed;
        }

        // 验证：解析后 offset 应等于 payload_size
        return offset == payload_size;
    }

    // ---- 创建空帧（丢帧填充用） ----
    static FramePacket make_empty_frame(uint32_t frame_id, uint8_t player_count) {
        FramePacket pkt;
        pkt.header.frame_id  = frame_id;
        pkt.header.cmd_count = player_count;
        pkt.header.seq_number = 0;
        pkt.commands.reserve(player_count);
        for (uint8_t i = 0; i < player_count; ++i) {
            pkt.commands.push_back(FrameCommand::make_empty(i));
        }
        return pkt;
    }

private:
    // ---- CRC32 查表法 ----
    static uint32_t crc32(const uint8_t* data, size_t len) {
        static uint32_t table[256];
        static bool initialized = false;
        if (!initialized) {
            for (uint32_t i = 0; i < 256; ++i) {
                uint32_t crc = i;
                for (int j = 0; j < 8; ++j)
                    crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320u : 0u);
                table[i] = crc;
            }
            initialized = true;
        }

        uint32_t crc = 0xFFFFFFFFu;
        for (size_t i = 0; i < len; ++i)
            crc = (crc >> 8) ^ table[(crc ^ data[i]) & 0xFF];
        return crc ^ 0xFFFFFFFFu;
    }

    // ---- Little-Endian 读写 ----
    static void write_u32_le(uint8_t* dst, uint32_t v) {
        dst[0] = v & 0xFF; dst[1] = (v >> 8) & 0xFF;
        dst[2] = (v >> 16) & 0xFF; dst[3] = (v >> 24) & 0xFF;
    }
    static void write_u16_le(uint8_t* dst, uint16_t v) {
        dst[0] = v & 0xFF; dst[1] = (v >> 8) & 0xFF;
    }
    static uint32_t read_u32_le(const uint8_t* src) {
        return src[0] | (src[1] << 8) | (src[2] << 16) | (src[3] << 24);
    }
    static uint16_t read_u16_le(const uint8_t* src) {
        return src[0] | (src[1] << 8);
    }
};

// ============================================================
// 环形缓冲区 — 粘包/拆包处理
// ============================================================
class RingBuffer {
public:
    static constexpr size_t CAPACITY = 65536;  // 64KB

    RingBuffer() : buf_(new uint8_t[CAPACITY]) {}
    ~RingBuffer() { delete[] buf_; }

    // 不可拷贝
    RingBuffer(const RingBuffer&) = delete;
    RingBuffer& operator=(const RingBuffer&) = delete;

    // 从 socket 读取数据追加到缓冲区
    // 返回读取的字节数; -1 表示错误
    int append_from_socket(int sockfd) {
        size_t tail_space = CAPACITY - write_pos_;
        size_t to_read = tail_space > 2048 ? tail_space : CAPACITY - write_pos_;
        if (to_read < 2048) to_read = 2048; // 至少读 2KB

        // 如果尾部空间不足，回绕到开头读取
        uint8_t* dest = buf_ + write_pos_;
        if (tail_space < to_read) {
            dest = buf_;
            to_read = (write_pos_ > 0) ? write_pos_ : CAPACITY;
        }

        ssize_t n = recv(sockfd, dest, to_read, 0);
        if (n > 0) {
            write_pos_ = (write_pos_ + n) % CAPACITY;
            available_ += n;
        }
        return static_cast<int>(n);
    }

    // 尝试提取一个完整帧到 out_buffer。返回提取的字节数; 0 表示数据不足
    size_t try_extract(uint8_t* out_buffer, size_t out_capacity) {
        if (available_ < 2) return 0;  // 长度前缀都不完整

        uint16_t pkt_len = read_u16_at(read_pos_);
        if (available_ < 2 + pkt_len) return 0;  // 包不完整

        if (out_capacity < pkt_len) return 0;  // 输出缓冲区不够大

        // 拷贝包体(跳过长度前缀)
        copy_from(read_pos_ + 2, out_buffer, pkt_len);

        size_t consumed = 2 + pkt_len;
        read_pos_ = (read_pos_ + consumed) % CAPACITY;
        available_ -= consumed;

        return pkt_len;
    }

    size_t available() const { return available_; }
    void clear() { read_pos_ = write_pos_ = available_ = 0; }

private:
    uint8_t* buf_;
    size_t read_pos_ = 0;
    size_t write_pos_ = 0;
    size_t available_ = 0;

    uint16_t read_u16_at(size_t pos) const {
        size_t p = pos % CAPACITY;
        return static_cast<uint16_t>(buf_[p] << 8) | buf_[p + 1];  // 大端
    }

    void copy_from(size_t pos, uint8_t* dst, size_t len) const {
        for (size_t i = 0; i < len; ++i) {
            dst[i] = buf_[(pos + i) % CAPACITY];
        }
    }
};

// ============================================================
// 帧接收管理器 — 丢包检测 + NACK + 超时处理
// ============================================================
class FrameReceiver {
public:
    explicit FrameReceiver(uint8_t player_count)
        : player_count_(player_count) {}

    // 收到帧包时调用。返回需要发送 NACK 的帧列表
    // 注意: process() 不自动触发超时逻辑,调用方需定期调用 check_timeouts()
    enum class Status {
        Ready,          // 帧已就绪,可执行
        Buffered,       // 已缓存,等待前序帧
        AlreadyProcessed,
    };

    struct Result {
        Status status;
        FramePacket* packet = nullptr;  // Ready 时有效
        std::vector<uint32_t> nack_list; // 需要 NACK 的帧列表
    };

    Result on_packet_received(const FramePacket& pkt) {
        Result result;
        uint32_t fid = pkt.header.frame_id;

        // 1. 过去帧 → 丢弃
        if (fid < expected_frame_) {
            nack_pending_.erase(fid);
            result.status = Status::AlreadyProcessed;
            return result;
        }

        // 2. 未来帧 → 有丢帧, 发送 NACK
        if (fid > expected_frame_) {
            buffer_[fid] = pkt;

            for (uint32_t m = expected_frame_; m < fid; ++m) {
                if (!nack_pending_.count(m)) {
                    nack_pending_[m] = now_ms_();
                    result.nack_list.push_back(m);
                }
            }
            result.status = Status::Buffered;
            return result;
        }

        // 3. 正常帧 (fid == expected_frame_)
        buffer_[fid] = pkt;
        nack_pending_.erase(fid);

        // 4. 取出所有连续的缓存帧
        auto it = buffer_.find(expected_frame_);
        if (it != buffer_.end()) {
            result.packet = &it->second;
            result.status = Status::Ready;
            buffer_.erase(it);
            nack_pending_.erase(expected_frame_);
            expected_frame_++;
        }

        return result;
    }

    // 处理连续的缓存帧(一次取尽可能多)
    std::vector<FramePacket*> flush_ready_frames() {
        std::vector<FramePacket*> ready;
        while (true) {
            auto it = buffer_.find(expected_frame_);
            if (it == buffer_.end()) break;
            ready.push_back(&it->second);
            nack_pending_.erase(expected_frame_);
            expected_frame_++;
        }
        return ready;
    }

    // 检查 NACK 超时,返回需要填充空指令的帧列表
    std::vector<uint32_t> check_timeouts(uint32_t now_ms, uint32_t timeout_ms = 200) {
        now_ms_ = now_ms;
        std::vector<uint32_t> timed_out;
        for (const auto& [fid, send_time] : nack_pending_) {
            if (now_ms - send_time > timeout_ms && fid < expected_frame_) {
                timed_out.push_back(fid);
            }
        }
        // 不立即删除——填充空指令后会推进 expected_frame_
        return timed_out;
    }

    // 强制推进(填充空指令后调用)
    void advance_to(uint32_t frame_id) {
        // 清理 <= frame_id 的所有待处理状态
        for (uint32_t f = expected_frame_; f <= frame_id; ++f) {
            buffer_.erase(f);
            nack_pending_.erase(f);
        }
        expected_frame_ = frame_id + 1;
    }

    uint32_t expected_frame() const { return expected_frame_; }
    uint8_t player_count() const { return player_count_; }

private:
    uint8_t player_count_;
    uint32_t expected_frame_ = 0;
    uint32_t now_ms_ = 0;
    std::unordered_map<uint32_t, FramePacket> buffer_;
    std::unordered_map<uint32_t, uint32_t> nack_pending_;  // fid → NACK发送时间(ms)
};

} // namespace lockstep
```

---

### 2.3 Lua：用 string.pack 实现帧包

```lua
-- lockstep_protocol.lua — Lua 帧同步协议层
-- 使用 Lua 5.3+ 的 string.pack / string.unpack
-- 适用场景: Lua 游戏客户端 (如基于 Love2D/Solar2D/Cocos2d-x Lua 的项目)

local FrameProtocol = {}

-- ============================================================
-- 操作码常量
-- ============================================================
FrameProtocol.Opcode = {
    MoveToPoint    = 0x00,
    MoveDirection  = 0x01,
    StopMove       = 0x02,
    NormalAttack   = 0x10,
    CastSkill      = 0x11,
    SkillDirection = 0x12,
    UseItem        = 0x20,
    BuyItem        = 0x21,
    Surrender      = 0x30,
    Pause          = 0x31,
    Ping           = 0x32,
    Empty          = 0xF0,
}

-- ============================================================
-- CRC32 查找表 (Lua 实现, 兼容 LuaJIT)
-- ============================================================
local crc32_table = {}
do
    for i = 0, 255 do
        local crc = i
        for _ = 1, 8 do
            if crc & 1 ~= 0 then
                crc = (crc >> 1) ~ 0xEDB88320
            else
                crc = crc >> 1
            end
        end
        crc32_table[i] = crc
    end
end

local function crc32(data)
    local crc = 0xFFFFFFFF
    for i = 1, #data do
        local byte = string.byte(data, i)
        local idx = (crc ~ byte) & 0xFF
        crc = (crc >> 8) ~ crc32_table[idx]
    end
    return crc ~ 0xFFFFFFFF
end

-- ============================================================
-- 单条指令的打包/解包
-- ============================================================
-- 指令格式: PlayerId(1B) Opcode(1B) ParamLength(1B) Params(变长)
-- string.pack 格式: "B B B c<ParamLength>"

function FrameProtocol.pack_command(cmd)
    -- cmd: { player_id, opcode, params = "..." 或 {} }
    local player_id = cmd.player_id or 0
    local opcode = cmd.opcode or FrameProtocol.Opcode.Empty
    local params = cmd.params or ""

    if type(params) == "table" then
        params = string.char(table.unpack(params))
    end

    -- 使用 "I1" = uint8, "B" = uint8
    local head = string.pack("<I1I1I1", player_id, opcode, #params)
    return head .. params
end

function FrameProtocol.unpack_command(data, offset)
    -- 返回: cmd, new_offset 或 nil, offset (解析失败)
    local len = #data
    if offset + 3 > len then
        return nil, offset
    end

    local player_id, opcode, param_len = string.unpack("<I1I1I1", data, offset)
    offset = offset + 3

    if offset + param_len > len then
        return nil, offset - 3  -- 数据不足,回退
    end

    local params = ""
    if param_len > 0 then
        params = data:sub(offset, offset + param_len - 1)
        offset = offset + param_len
    end

    return {
        player_id = player_id,
        opcode = opcode,
        params = params
    }, offset
end

-- ============================================================
-- 帧包打包
-- ============================================================
-- 帧包格式:
--   Header:  FrameId(I4) CmdCount(I1) SeqNum(I1) Reserved(I2)
--   Body:    Commands[]
--   Tail:    CRC32(I4)
-- string.pack 格式前缀: "<I4 I1 I1 I2" = 8 bytes

function FrameProtocol.pack_frame(frame)
    -- frame: { frame_id, seq_number, commands = {cmd1, cmd2, ...} }
    local cmd_count = #(frame.commands or {})

    -- 打包头部
    local header = string.pack("<I4I1I1I2",
        frame.frame_id or 0,
        cmd_count,
        frame.seq_number or 0,
        frame.reserved or 0
    )

    -- 打包指令
    local body_parts = { header }
    for _, cmd in ipairs(frame.commands or {}) do
        body_parts[#body_parts + 1] = FrameProtocol.pack_command(cmd)
    end

    local payload = table.concat(body_parts)

    -- 计算 CRC32 并追加
    local checksum = crc32(payload)
    local checksum_bytes = string.pack("<I4", checksum)

    return payload .. checksum_bytes
end

-- ============================================================
-- 帧包解包
-- ============================================================
-- 返回: frame_table 或 nil (CRC不匹配/格式错误)

function FrameProtocol.unpack_frame(data)
    local len = #data
    if len < 12 then  -- 头8B + CRC4B
        return nil, "packet too short"
    end

    local payload_len = len - 4

    -- 校验 CRC32
    local payload = data:sub(1, payload_len)
    local claimed_crc = string.unpack("<I4", data, payload_len + 1)
    local computed_crc = crc32(payload)

    if claimed_crc ~= computed_crc then
        return nil, "CRC mismatch"
    end

    -- 解析头部
    local frame_id, cmd_count, seq_number, reserved =
        string.unpack("<I4I1I1I2", payload)

    local offset = 9  -- 头部 8 字节后
    local commands = {}

    for _ = 1, cmd_count do
        local cmd, new_offset = FrameProtocol.unpack_command(payload, offset)
        if not cmd then
            return nil, "failed to unpack command at offset " .. offset
        end
        commands[#commands + 1] = cmd
        offset = new_offset
    end

    return {
        frame_id = frame_id,
        seq_number = seq_number,
        reserved = reserved,
        commands = commands,
        checksum = claimed_crc,
    }
end

-- ============================================================
-- 便捷构造方法
-- ============================================================

--- 创建方向移动指令 (压缩到 ~3 字节)
--- @param player_id number 玩家ID
--- @param dx number 方向X (-8 ~ +7)
--- @param dy number 方向Y (-8 ~ +7)
function FrameProtocol.make_move_dir(player_id, dx, dy)
    -- 将 dx, dy 量化到 4bit, 合并为 1 字节
    local qx = math.max(-8, math.min(7, math.floor(dx * 8 + 0.5)))
    local qy = math.max(-8, math.min(7, math.floor(dy * 8 + 0.5)))
    -- params: 1 字节 = high 4 bits (dx) + low 4 bits (dy)
    local packed = ((qx & 0x0F) << 4) | (qy & 0x0F)
    return {
        player_id = player_id,
        opcode = FrameProtocol.Opcode.MoveDirection,
        params = string.char(packed),
    }
end

--- 创建空指令 (丢帧填充)
function FrameProtocol.make_empty(player_id)
    return {
        player_id = player_id,
        opcode = FrameProtocol.Opcode.Empty,
        params = "",
    }
end

--- 创建空帧 (丢帧时的默认帧)
function FrameProtocol.make_empty_frame(frame_id, player_count)
    local cmds = {}
    for pid = 0, player_count - 1 do
        cmds[#cmds + 1] = FrameProtocol.make_empty(pid)
    end
    return {
        frame_id = frame_id,
        seq_number = 0,
        commands = cmds,
    }
end

-- ============================================================
-- 粘包/拆包: 环形缓冲区模拟 (Lua table 实现)
-- ============================================================
local RingBuffer = {}
RingBuffer.__index = RingBuffer

function RingBuffer.new(max_size)
    max_size = max_size or 65536
    return setmetatable({
        _buf = {},
        _read = 1,
        _write = 1,
        _available = 0,
        _max = max_size,
    }, RingBuffer)
end

function RingBuffer:append(data)
    local data_len = #data
    for i = 1, data_len do
        self._buf[self._write] = string.byte(data, i)
        self._write = self._write % self._max + 1
    end
    self._available = self._available + data_len
end

function RingBuffer:try_extract()
    if self._available < 2 then
        return nil  -- 长度前缀不足
    end

    -- 读取 2 字节长度 (大端)
    local hi = self:_byte_at(self._read)
    local lo = self:_byte_at(self._read + 1)
    local pkt_len = (hi << 8) | lo

    if self._available < 2 + pkt_len then
        return nil  -- 包体不完整
    end

    -- 读取包体
    local bytes = {}
    local pos = self._read + 2
    for i = 1, pkt_len do
        bytes[i] = self:_byte_at(pos + i - 1)
    end
    local pkt_data = string.char(table.unpack(bytes))

    -- 推进读指针
    self._read = self:_advance(self._read, 2 + pkt_len)
    self._available = self._available - 2 - pkt_len

    return pkt_data
end

function RingBuffer:_byte_at(pos)
    pos = ((pos - 1) % self._max) + 1
    return self._buf[pos] or 0
end

function RingBuffer:_advance(pos, delta)
    return (pos - 1 + delta) % self._max + 1
end

FrameProtocol.RingBuffer = RingBuffer

-- ============================================================
-- 自测 (可直接运行: lua lockstep_protocol.lua)
-- ============================================================
if arg and arg[0]:match("lockstep_protocol") then
    print("=== FrameProtocol 自测 ===\n")

    -- 测试 1: 单条指令打包/解包
    local cmd = FrameProtocol.make_move_dir(1, 5, -3)
    local packed_cmd = FrameProtocol.pack_command(cmd)
    print(string.format("Test 1 - MoveDir packed: %d bytes", #packed_cmd))

    local unpacked_cmd = FrameProtocol.unpack_command(packed_cmd, 1)
    assert(unpacked_cmd.player_id == 1)
    assert(unpacked_cmd.opcode == FrameProtocol.Opcode.MoveDirection)
    print("  unpack OK")

    -- 测试 2: 完整帧打包/解包
    local frame = {
        frame_id = 42,
        seq_number = 7,
        commands = {
            FrameProtocol.make_move_dir(0, 8, 0),
            FrameProtocol.make_move_dir(1, -4, 3),
            FrameProtocol.make_empty(2),
        }
    }
    local packed_frame = FrameProtocol.pack_frame(frame)
    print(string.format("Test 2 - Frame packed: %d bytes", #packed_frame))

    local unpacked_frame = FrameProtocol.unpack_frame(packed_frame)
    assert(unpacked_frame.frame_id == 42)
    assert(unpacked_frame.seq_number == 7)
    assert(#unpacked_frame.commands == 3)
    print("  unpack OK, commands:", #unpacked_frame.commands)

    -- 测试 3: CRC 校验检测数据损坏
    local corrupted = packed_frame:sub(1, #packed_frame - 1) .. string.char(0xFF)
    local result = FrameProtocol.unpack_frame(corrupted)
    assert(result == nil)
    print("Test 3 - CRC corruption detected: OK")

    -- 测试 4: 环形缓冲区
    local rb = RingBuffer.new(1024)
    local len_prefix = string.pack(">I2", #packed_frame)  -- 2字节大端长度前缀
    rb:append(len_prefix .. packed_frame)
    local extracted = rb:try_extract()
    assert(extracted == packed_frame)
    print("Test 4 - RingBuffer: OK")

    -- 测试 5: 粘包提取
    local frame2 = FrameProtocol.pack_frame({
        frame_id = 43, seq_number = 8,
        commands = { FrameProtocol.make_empty(0) }
    })
    local len_prefix2 = string.pack(">I2", #frame2)
    rb:append(len_prefix .. packed_frame .. len_prefix2 .. frame2)
    assert(rb:try_extract() == packed_frame)
    assert(rb:try_extract() == frame2)
    print("Test 5 - Multiple packets in buffer: OK")

    print("\n=== All tests passed ===")
end

return FrameProtocol
```

---

## 3. 练习

### 练习 1: 实现 XOR FEC 编解码器

**目标**：理解前向纠错的原理，实现一个简单的 XOR FEC 系统。

**要求**：
1. 实现 `XorFEC` 类，构造函数接受 `group_size`（每组数据包数量，如 3）。
2. 提供 `AddDataPacket(packet_bytes)` 方法，累积数据包。当累积满一组时，自动生成 FEC 包（所有数据包的逐字节 XOR）。
3. 提供 `Recover(available_packets, missing_index)` 方法——给定组内除一个外的所有包和缺失包的索引，恢复缺失数据。
4. 编写测试：模拟丢失组内第 k 个包，验证恢复后的数据与原始数据逐字节一致。

**提示**：
- XOR 操作要求所有包**等长**。如果不等长，需要先填充到统一长度（记录原始长度在 FEC 包中）。
- 返回值可以用 `(fec_packet, original_lengths)` 元组。

**参考实现思路**：
```python
class XorFEC:
    def __init__(self, group_size=3):
        self.group_size = group_size
        self.buffer = []  # (packet_bytes, original_length)

    def add_data_packet(self, data: bytes):
        self.buffer.append((data, len(data)))
        if len(self.buffer) == self.group_size:
            return self._generate_fec()
        return None

    def _generate_fec(self):
        max_len = max(len(d) for d, _ in self.buffer)
        fec = bytearray(max_len)
        for data, _ in self.buffer:
            padded = data + b'\x00' * (max_len - len(data))
            for i in range(max_len):
                fec[i] ^= padded[i]
        result = (bytes(fec), [orig_len for _, orig_len in self.buffer])
        self.buffer.clear()
        return result
```

---

### 练习 2: 实现自适应冗余度控制器

**目标**：实现基于丢包率动态调整冗余度的控制器。

**要求**：
1. 实现 `AdaptiveRedundancy` 类，包含：
   - `OnPacketSent(frame_id)` — 记录发送
   - `OnPacketAcked(frame_id)` — 记录收到确认（通过后续帧到达间接判断）
   - `Update(now_ms)` — 定期评估丢包率并调整冗余度
2. 使用 EWMA (指数加权移动平均) 平滑丢包率，衰减因子 α=0.3。
3. 冗余度范围 1~5，升降规则：
   - `loss_rate < 1%` → R=1
   - `1% ≤ loss_rate < 3%` → R=2
   - `3% ≤ loss_rate < 8%` → R=3
   - `8% ≤ loss_rate < 15%` → R=5
   - `loss_rate ≥ 15%` → R=5 并触发"网络极差"警告
4. **迟滞**：升冗余在丢包率跨过阈值后立即生效；降冗余需要在阈值以下**持续 5 秒**才生效（防止抖动）。

**提示**：
- 可以用滑动窗口（最近 100 个包）统计瞬时丢包率，然后用 EWMA 平滑。
- `OnPacketAcked` 不一定是显式 ACK——在帧同步中，收到 frame_id=N+3 的包就间接确认了 frame_id=N 的包已到达。

---

### 练习 3: 构建完整的帧同步协议栈

**目标**：综合运用本教程所有知识，构建一个完整的帧同步协议层。

**要求**：
以下面的接口构建 `LockstepProtocolStack`：

```
发送路径:  GameLogic → create_frame_command() → FramePacket.encode()
              → CRC32 → RedundantSender(×N) → UDP Socket

接收路径:  UDP Socket → RingBuffer → try_extract()
              → CRC32验证 → FramePacket.decode()
              → FrameReceiver(丢帧检测+NACK) → GameLogic.execute()
```

具体需要实现：
1. **命令缓冲**：收集游戏逻辑层产生的指令，按帧打包。
2. **冗余发送器**：将帧包复制 N 份，交错发送（相邻拷贝间隔 10~16ms）。
3. **NACK 处理**：接收方检测到 FrameId 间隙 → 发送 NACK → 发送方收到 NACK 后重传指定帧。
4. **超时兜底**：如果 NACK 发出 200ms 未收到重传 → 用上一帧输入填充，继续推进。
5. **集成测试**：模拟以下网络条件，验证协议栈能正确推进到 1000 帧：
   - 完美网络 (0% 丢包)
   - 2% 随机丢包
   - 10% 突发丢包（每 100 帧中有连续 5 帧丢失）

**输出要求**：选择你擅长的语言（C#/C++/Lua/Python），实现并附上能运行的测试代码。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> XOR FEC 编解码器完整实现（Python）：
>
> ```python
> class XorFEC:
>     def __init__(self, group_size=3):
>         self.group_size = group_size
>         self.buffer = []  # (packet_bytes, original_length)
>
>     def add_data_packet(self, data: bytes):
>         """添加一个数据包。组满时返回 (fec_packet, original_lengths)，否则返回 None。"""
>         self.buffer.append((data, len(data)))
>         if len(self.buffer) == self.group_size:
>             return self._generate_fec()
>         return None
>
>     def _generate_fec(self):
>         # 找到最大长度，短包尾部补零
>         max_len = max(len(d) for d, _ in self.buffer)
>         fec = bytearray(max_len)
>         for data, _ in self.buffer:
>             for i in range(len(data)):
>                 fec[i] ^= data[i]
>             # 超出 data 长度的部分 XOR 0，不影响 fec
>         result = (bytes(fec), [orig_len for _, orig_len in self.buffer])
>         self.buffer.clear()
>         return result
>
>     @staticmethod
>     def recover(available_packets: list[bytes],
>                 fec_packet: bytes,
>                 original_lengths: list[int],
>                 missing_index: int) -> bytes:
>         """从组内其他包 + FEC 包恢复缺失的数据包。
>         available_packets: 除缺失包外的所有数据包
>         missing_index: 缺失包在组内的索引 (0-based)
>         """
>         recovered = bytearray(fec_packet)
>         for pkt in available_packets:
>             for i in range(min(len(pkt), len(recovered))):
>                 recovered[i] ^= pkt[i]
>         # 截断到原始长度
>         return bytes(recovered[:original_lengths[missing_index]])
>
>
> # --- 测试 ---
> def test_xor_fec():
>     fec = XorFEC(group_size=3)
>
>     p0 = b"Hello"
>     p1 = b"World!"
>     p2 = b"FEC"
>
>     assert fec.add_data_packet(p0) is None
>     assert fec.add_data_packet(p1) is None
>     fec_result = fec.add_data_packet(p2)
>     assert fec_result is not None
>
>     fec_pkt, orig_lens = fec_result
>
>     # 模拟丢失 p1（索引 1）
>     recovered = XorFEC.recover([p0, p2], fec_pkt, orig_lens, missing_index=1)
>     assert recovered == p1, f"Recovery failed: {recovered} != {p1}"
>
>     # 模拟丢失 p0（索引 0）
>     recovered = XorFEC.recover([p1, p2], fec_pkt, orig_lens, missing_index=0)
>     assert recovered == p0
>
>     print("All XOR FEC tests passed!")
>
> test_xor_fec()
> ```
>
> **设计要点**：
> - **等长要求**：XOR 操作要求所有操作数等长。短包尾部补 0x00 后参与 XOR，恢复时按 `original_lengths` 截断
> - **恢复原理**：FEC = P0 ⊕ P1 ⊕ P2，恢复 P1 = FEC ⊕ P0 ⊕ P2（异或的自逆性）
> - **局限性**：只能容忍组内丢失 1 个包。丢失 ≥ 2 个包无法恢复。这正是教程中提到的"Reed-Solomon 可以恢复多个但延迟/计算量不适合帧同步"的原因
> - **帧同步适用性**：冗余度 2~3 时 XOR FEC group_size=5 可将带宽从 300%（冗余度 3）降到 120%（5 个包 + 1 个 FEC），但代价是必须等满一组才能生成/恢复 → 引入额外延迟

> [!tip]- 练习 2 参考答案
> 自适应冗余度控制器：
>
> ```python
> import time
> from collections import deque
>
> class AdaptiveRedundancy:
>     def __init__(self):
>         self.redundancy = 2          # 初始冗余度
>         self.smoothed_loss = 0.0     # EWMA 平滑后的丢包率
>         self.alpha = 0.3             # EWMA 衰减因子
>
>         # 滑动窗口：最近 100 个包的发送/确认状态
>         self.window = deque(maxlen=100)
>         self.pending = {}            # frame_id -> send_time（未确认的包）
>
>         # 降冗余迟滞：记录进入低丢包区间的起始时间
>         self.low_loss_since = None
>         self.HYSTERESIS_SEC = 5.0
>
>     def on_packet_sent(self, frame_id: int):
>         self.pending[frame_id] = time.time()
>
>     def on_packet_acked(self, frame_id: int):
>         """收到间接确认：收到 frame_id=N+3 → 确认 N 已到达"""
>         send_time = self.pending.pop(frame_id, None)
>         if send_time is not None:
>             self.window.append(1)  # 成功
>         # 跳过的帧号视为丢失
>         expired = [fid for fid in self.pending if fid < frame_id]
>         for fid in expired:
>             self.pending.pop(fid)
>             self.window.append(0)  # 丢失
>
>     def update(self):
>         """定期评估丢包率并调整冗余度"""
>         if len(self.window) < 10:
>             return  # 样本不足，不做调整
>
>         # 瞬时丢包率
>         instant_loss = 1.0 - sum(self.window) / len(self.window)
>         # EWMA 平滑
>         self.smoothed_loss = (1 - self.alpha) * self.smoothed_loss \
>                            + self.alpha * instant_loss
>
>         # 根据平滑丢包率决定目标冗余度
>         target = self._loss_to_redundancy(self.smoothed_loss)
>
>         now = time.time()
>         if target < self.redundancy:
>             # 降冗余需要迟滞
>             if self.low_loss_since is None:
>                 self.low_loss_since = now
>             elif now - self.low_loss_since >= self.HYSTERESIS_SEC:
>                 self.redundancy = target
>                 self.low_loss_since = None
>         else:
>             # 升冗余立即生效
>             self.redundancy = target
>             self.low_loss_since = None
>
>     def _loss_to_redundancy(self, loss: float) -> int:
>         if loss < 0.01:   return 1
>         if loss < 0.03:   return 2
>         if loss < 0.08:   return 3
>         if loss < 0.15:   return 5
>         print("WARNING: Network extremely poor!")
>         return 5
> ```
>
> **设计要点**：
> - **EWMA 平滑**：`α=0.3` 意味着新样本权重 30%，旧值权重 70%。比简单平均更抗抖动，但比纯滑动平均反应更快
> - **迟滞（Hysteresis）**：降冗余需要持续 5 秒低丢包——防止网络短时波动导致冗余度来回振荡，振荡会引入不必要的带宽开销
> - **间接确认**：帧同步中没有显式 ACK。收到 frame_id=N+3 的包即确认 N 已到达（发送方能推断出来，因为后续帧的到达说明网络通畅）
> - **滑动窗口**：`deque(maxlen=100)` 自动丢弃老样本——丢包率的统计窗口始终是最近的 100 个包
> - **初始值**：初始冗余度 2 是保守默认值，适合 WiFi/有线环境

> [!tip]- 练习 3 参考答案
> 完整帧同步协议栈的核心架构与关键代码片段：
>
> **整体数据流**：
>
> ```
> 发送: GameLogic → CommandBuffer.collect()
>      → FramePacket.build(frameId, commands)
>      → CRC32.compute(packet)
>      → RedundantSender.send(packet, redundancy=N)
>      → UDP socket
>
> 接收: UDP socket → RingBuffer.insert(seq, data)
>      → FrameReceiver.try_extract()
>      → CRC32.verify(packet) → 失败则丢弃
>      → FramePacket.parse(packet)
>      → NACK检测 (FrameId间隙) → 发送NACK
>      → GameLogic.execute(framePacket)
> ```
>
> **1. 命令缓冲器**：
>
> ```csharp
> public class CommandBuffer {
>     private List<GameCommand> _pending = new();
>
>     public void AddCommand(GameCommand cmd) => _pending.Add(cmd);
>
>     public List<GameCommand> Flush() {
>         var result = _pending;
>         _pending = new List<GameCommand>();
>         return result;
>     }
> }
> ```
>
> **2. 交错冗余发送器**：
>
> ```csharp
> public class RedundantSender {
>     private int _redundancy = 3;
>     private int _interleaveMs = 12;  // 相邻拷贝间隔
>     private Queue<(uint frameId, byte[] data, int copy)> _queue = new();
>
>     public void SendFrame(uint frameId, byte[] packet) {
>         for (int i = 0; i < _redundancy; i++)
>             _queue.Enqueue((frameId, packet, i));
>     }
>
>     public void Update(float nowMs) {
>         // 按交错间隔发送排队的拷贝
>         while (_queue.Count > 0 && ShouldSendNext(nowMs)) {
>             var (frameId, data, copy) = _queue.Dequeue();
>             byte seq = (byte)((frameId * (uint)_redundancy + (uint)copy) & 0xFF);
>             UdpSend(frameId, seq, data);
>             _lastSendMs = nowMs;
>         }
>     }
> }
> ```
>
> **3. NACK 处理与超时兜底**：
>
> ```csharp
> public class FrameReceiver {
>     private uint _nextExpected = 0;
>     private SortedDictionary<uint, byte[]> _buffer = new();
>     private Dictionary<uint, float> _nackSentAt = new();  // NACK 发送时间
>     private const float NACK_TIMEOUT_MS = 200f;
>
>     public bool TryConsume(out uint frameId, out byte[] data,
>                            float nowMs, Action<uint> sendNack) {
>         frameId = 0; data = null;
>
>         // 检查 NACK 超时
>         foreach (var kv in _nackSentAt.ToList()) {
>             if (nowMs - kv.Value > NACK_TIMEOUT_MS) {
>                 // 超时兜底：用上一帧的输入填坑
>                 if (_buffer.TryGetValue(kv.Key - 1, out var prevData)) {
>                     _buffer[kv.Key] = prevData;
>                 }
>                 _nackSentAt.Remove(kv.Key);
>             }
>         }
>
>         // 尝试按序消费
>         if (_buffer.TryGetValue(_nextExpected, out data)) {
>             frameId = _nextExpected;
>             _buffer.Remove(_nextExpected);
>             _nextExpected++;
>             return true;
>         }
>
>         // 有空隙 → 发送 NACK
>         if (!_nackSentAt.ContainsKey(_nextExpected)) {
>             sendNack(_nextExpected);
>             _nackSentAt[_nextExpected] = nowMs;
>         }
>         return false;
>     }
>
>     public void Insert(uint frameId, byte[] data) {
>         if (frameId < _nextExpected) return;  // 过期
>         _buffer[frameId] = data;
>         _nackSentAt.Remove(frameId);  // 收到了，取消 NACK
>     }
> }
> ```
>
> **4. 集成测试要点**：
>
> ```python
> # 模拟不同丢包场景的测试框架
> def simulate_network(protocol, total_frames, loss_rate, burst_size=0):
>     for frame in range(total_frames):
>         protocol.tick()
>         if burst_size > 0 and frame % 100 < burst_size:
>             continue  # 突发丢包
>         if random.random() < loss_rate:
>             continue  # 随机丢包
>         protocol.deliver_packet(frame)
>     assert protocol.current_frame >= total_frames, \
>         f"Stuck at frame {protocol.current_frame}"
> ```
>
> **关键设计决策**：
> - **NACK 而非 ACK**：在帧同步中，期望帧号间隙就是丢包信号——不需要专门的 ACK 包
> - **超时兜底用上一帧输入**：简单粗暴但在大多数情况下可行。玩家的输入在相邻帧之间通常不变（持续按住方向键），丢失一帧的输入不会导致灾难性后果
> - **SeqNumber 去重**：RedundantSender 为每个拷贝分配不同的 SeqNumber，接收方用 `SeqNumber` 判断是否已收到同一 FrameId 的其他拷贝
> - **CRC32 校验**：必须在 decode **之前**验证 CRC——如果 CRC 失败说明包损坏，不应该喂给逻辑层（可能引入非确定性）

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

1. **《Development and Deployment of Multiplayer Online Games》Vol. 1 & 2** — "Gambetta" 系列，包含 Locke 协议层的深入实现细节。
2. **Gaffer on Games — "Networked Physics"** — Glenn Fiedler 的经典博客系列，其中"Reliability and Flow Control"章节深入讲解了冗余与 FEC 的实践。
3. **[KCP: A Fast and Reliable ARQ Protocol](https://github.com/skywind3000/kcp)** — 国人开发的可靠 UDP 协议库，其 FEC 和流控设计直接启发了多款国产游戏的帧同步方案。
4. **RFC 5109 — RTP Payload Format for Generic Forward Error Correction** — IETF 的 FEC 标准，帧同步 FEC 可参考其组帧方式。
5. **《守望先锋》网络同步 GDC 演讲** — "Overwatch Gameplay Architecture and Netcode" (GDC 2017)，了解 AAA 游戏中帧同步与状态同步的混合实践。
6. **王者荣耀技术博客** — 腾讯官方关于帧同步协议、Bucket 机制和乐观帧锁定的技术分享（中文，腾讯云社区可搜索）。
7. **Reed-Solomon 编码** — 比 XOR FEC 更强大的纠错编码（可容忍组内丢失多个包），**不适合**帧同步（编码/解码计算量大、延迟高），但了解其存在有助于面试。

---

## 常见陷阱

### 陷阱 1: 忘记字节序

帧同步包可能跨平台传输（Windows 做服务器、Android/iOS 做客户端）。如果在序列化时不显式指定字节序，不同平台的默认字节序（Little-Endian vs Big-Endian）会导致 FrameId 解析为一堆乱码。

**解决方案**：协议中所有多字节整数**强制 Little-Endian**（x86/ARM 原生序），或**强制 Big-Endian**（网络字节序）。在 `string.pack` / `BitConverter` / 手动位移中统一使用一种序。**永远不要直接 memcpy 一个有 endianness 的 struct 到网络包。**

```csharp
// 错误做法! 禁止!
byte[] buf = new byte[4];
Buffer.BlockCopy(BitConverter.GetBytes(frameId), 0, buf, 0, 4); // BitConverter 使用本机字节序!

// 正确做法: 显式指定 Little-Endian
buf[0] = (byte)(frameId);
buf[1] = (byte)(frameId >> 8);
buf[2] = (byte)(frameId >> 16);
buf[3] = (byte)(frameId >> 24);
```

### 陷阱 2: CRC32 覆盖范围错误

**常见错误**：把 CRC32 字段自身也纳入 CRC32 计算范围。这会导致永远校验不通过（因为 CRC32 字段写入后改变了数据，计算出的 CRC 又不同）。

**正确做法**：计算 CRC32 时**只覆盖 Header + Commands**，CRC32 字段本身**在计算范围之外**。如果包格式中 CRC32 后有 Padding 或尾部数据，确保它们也不在 CRC 范围内。

### 陷阱 3: 冗余包的去重逻辑缺失

同一个帧包可能因为冗余发送被接收方收到多次。如果不去重，`OnFrameReceived(FrameId=42)` 被调用 3 次 → 游戏逻辑执行了 3 次 Frame 42 → 状态严重错乱。

**必须维护**：`_lastProcessedFrameId`。任何 `frameId <= _lastProcessedFrameId` 的包直接丢弃。

### 陷阱 4: NACK 风暴

当网络拥塞时，丢包率飙升。如果实现不当，NACK 会像 TCP 重传一样指数增长——**NACK 本身的包也会丢**，触发更多 NACK → 拥塞更严重 → 更多丢包 → 死循环。

**抑制手段**：
- 每个缺失帧最多发 3 次 NACK
- NACK 之间有最小间隔（如 50ms）
- 用批量 NACK（一个包请求多个缺失帧）
- 检测到连续丢帧超过 10 帧时 → 放弃 NACK，直接请求全量快照同步

### 陷阱 5: 环形缓冲区越界

环形缓冲区实现中最隐蔽的 bug：当 `write_pos == read_pos` 时，无法区分"缓冲区空"和"缓冲区满"。这是因为 `(write_pos + 1) % CAPACITY == read_pos` 已经用于"满"的判定。

**解决方案**：
- 使用独立的 `available_` 计数器（本教程示例的做法）
- 或牺牲一个字节的容量：`available = (write_pos - read_pos + CAPACITY) % CAPACITY`，`full = (write_pos + 1) % CAPACITY == read_pos`

### 陷阱 6: 指令参数长度字段的使用不当

变长指令的 `ParamLength` 字段如果被恶意构造（如声称 255 字节的参数但实际数据只有 10 字节），会导致越界读取。

**防护**：
- 在 `decode()` 中严格检查 `offset + param_length <= payload_size`
- 拒绝 `param_length > MAX_COMMAND_PARAM_SIZE`（如 32 字节）
- 对来自客户端的输入指令也需要同样的检查——协议层的输入必须视为不可信

### 陷阱 7: 帧号溢出

`FrameId` 使用 `uint32_t`（最大约 42.9 亿帧）。在 15Hz 逻辑帧率下，可运行约 `4294967295 / 15 / 3600 = 79536 小时`（约 9 年）——实际上够用。但如果用了 `uint16_t`（65535 帧 = 约 73 分钟 @15Hz），对局时间长的游戏就会溢出回绕。

**解决方案**：
- 使用 `uint32_t` 作为 FrameId
- 比较 FrameId 时使用**序列号回绕比较**（而非简单的 `<` 和 `>`）：

```cpp
// 处理 uint32_t 回绕的比较: 判断 a 是否在 b 的"前方"
bool is_frame_ahead(uint32_t a, uint32_t b) {
    return (int32_t)(a - b) > 0;
}
// 原理: 用有符号差值判断,只要间隔不超过 2^31-1 帧 (~4.1年@15Hz) 就正确
```

这个技巧同样适用于 `SeqNumber`（uint8_t，256 个值回绕），使用 `(int8_t)(a - b) > 0` 判断。
