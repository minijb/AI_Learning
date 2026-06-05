---
title: "网络协议深度：UDP vs TCP 与可靠UDP层"
updated: 2026-06-05
---

# 网络协议深度：UDP vs TCP 与可靠UDP层

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [[01-game-network-architecture|01 - 游戏网络架构总览]]

---

## 1. 概念讲解

### 为什么需要这个？

如果你只用 TCP 做游戏网络通信，你的游戏在公网表现会很糟糕。这不是 TCP 设计得不好——恰恰相反，TCP 在它擅长的场景（可靠、有序的字节流传输）中近乎完美。问题在于：**实时游戏不需要 TCP 的所有保证，却要为它的代价买单**。

一个帧同步游戏每帧（约 33ms @30fps 或 16ms @60fps）就要发送一次玩家输入，上一帧的输入如果丢了，**不需要重传**——下一帧马上就到了。但 TCP 会死死卡住，不把丢失的那帧重传成功，后续所有数据都到不了应用层。这就是**队头阻塞**（Head-of-Line Blocking, HOL Blocking）。

反过来，裸 UDP 又快又轻，但丢包、乱序、重复——什么保证都没有。所以我们需要**在 UDP 之上构建我们需要的可靠性**——不多不少，刚好够用。

本节是后续所有同步架构的通信基石。无论是 Lockstep 的帧指令传输、状态同步的快照下发、还是混合同步的双通道设计，底层协议的选择和封装都是第一道工程决策。

### TCP 为什么不适合实时游戏

#### 1. 队头阻塞 (Head-of-Line Blocking)

TCP 保证**有序交付**。发送方按顺序发 1, 2, 3, 4, 5，接收方必须按 1, 2, 3, 4, 5 的顺序收到。如果包 2 丢了，包 3, 4, 5 已经到了内核缓冲区，但操作系统不会把它们交给应用程序——它在等包 2 的重传。

```
发送方: [1] [2] [3] [4] [5]  →  网络丢包 2
接收方 TCP 缓冲区: [1] [---等待2---] [3] [4] [5]
应用层能读到的:   [1]         ← 3,4,5 被"堵"住了
```

重传超时（RTO）通常是 200ms 起步，在丢包严重的移动网络下，这意味着你的游戏可能突然卡住 200ms+，然后一次性收到大量积压数据——玩家体验就是"飘移"或"瞬移"。

对于帧同步来说，第 100 帧的输入和第 101 帧的输入是**互相独立的**——收到 101 帧完全可以先执行，100 帧可以丢弃或用默认值填充。TCP 强行要求有序，反而帮了倒忙。

#### 2. 拥塞控制 (Congestion Control)

TCP 的拥塞控制算法（CUBIC、BBR 等）假设"丢包 = 网络拥塞"，一旦检测到丢包就大幅削减发送窗口。这对文件下载是合理的——避免把网络压垮。但对实时游戏：

- 游戏的数据包通常很小（几十到几百字节），远低于带宽上限
- 丢包更可能来自 Wi-Fi 干扰、移动信号切换，而非真正的拥塞
- TCP 的"慢启动"和"拥塞避免"导致发送速率锯齿状波动，而游戏需要**稳定的发送节奏**

更致命的是，TCP 的拥塞窗口缩减和重传超时是**内核层面**的行为，应用程序无法绕过。即使你知道"这个包不重要，别重传了"，TCP 不给你这个选项。

#### 3. 连接状态的代价

TCP 是面向连接的：三次握手建立连接，四次挥手断开。在移动网络下，频繁的 IP 切换（Wi-Fi ↔ 4G/5G）会导致连接断开，必须重新握手。而 UDP 无连接，切换网络后直接继续发包即可——只要应用层做了会话迁移。

此外，每个 TCP 连接在操作系统内核中都维护着发送/接收缓冲区、拥塞状态、定时器等数据结构，大量并发连接时内存开销不容忽视。一个 MMO 服务端可能同时维持数万连接，全用 TCP 时内核资源压力大。

#### 补充：TCP 也不是一无是处

某些场景下 TCP 仍然是正确选择：

- **登录/大厅/匹配服务**：需要可靠传输，延迟不敏感，用 HTTP/HTTPS（基于 TCP）完全合适
- **回合制游戏**：延迟容忍度高，可靠性要求高
- **WebSocket 信令**：用于建立 WebRTC 连接的信令通道

核心原则：**实时战斗走 UDP，非实时交互走 TCP/HTTP**。

### UDP 的优势和代价

#### 优势

| 特性     | UDP                       | TCP      |
| ------ | ------------------------- | -------- |
| 连接建立   | 无，直接发包                    | 三次握手     |
| 传输保证   | 无（尽力而为）                   | 可靠、有序    |
| 队头阻塞   | 不存在                       | 存在       |
| 拥塞控制   | 无（应用层自行实现）                | 内核强制     |
| 头部开销   | 8 字节                      | 20-60 字节 |
| 包边界    | 保留（每个 send = 一个 datagram） | 流式，无边界   |
| NAT 穿透 | 相对容易（打洞）                  | 困难       |
| 广播/多播  | 支持                        | 不支持      |

**包边界保留**这一点很重要：UDP 是面向数据报的，一次 `sendto()` 对应一次 `recvfrom()`，不会出现 TCP 的"粘包"问题。这在游戏协议设计中非常便利——每个数据报就是一个逻辑帧，不需要额外的分帧逻辑。

#### 代价

UDP 什么都不保证，所以以下问题全需要应用层自己解决：

1. **丢包**：数据报可能在任意节点被丢弃。需要 ACK + 重传机制
2. **乱序**：后发的包可能先到。需要序列号排序
3. **重复**：数据报可能被重复投递（如重传超时判定过短）。需要去重
4. **分片**：超过 MTU（通常 1500 字节减去 IP/UDP 头）的包会在 IP 层分片，任何一片丢失则整个数据报作废。需要应用层控制包大小或自行分片重组

**好消息是**：你不必对每个包都保证可靠性。这正是可靠 UDP 层的核心设计哲学——**选择性可靠**：对重要数据（关键状态、RPC 调用）保证可靠有序，对高频实时数据（位置更新、帧输入）容忍丢失。

### 可靠UDP层设计

> 可靠 UDP 的本质是：**在 UDP 之上实现一个裁剪版的传输层**，只包含游戏需要的特性。

#### 核心机制

##### 1. 序列号 (Sequence Number)

每个发出的数据报携带一个单调递增的序列号（通常用 `uint16` 或 `uint32`）：

```
发送方: seq=1001 [input: ←→A]  →  网络
        seq=1002 [input: →B  ]  →  网络
        seq=1003 [input: ↑C  ]  →  网络  (丢包)
        seq=1004 [input: ←D  ]  →  网络
```

接收方根据序列号判断：
- `seq > lastReceived`：新包，处理
- `seq <= lastReceived`：重复包，丢弃
- `seq > lastReceived + 1`：有丢包，记录缺失的序列号

**序列号回绕**：如果使用 `uint16`（0-65535），在高速率下可能回绕。解决方法：
- 使用足够大的序列号空间（`uint32` 在 60fps 下可跑 2.7 年才回绕）
- 或实现回绕感知的比较（RFC 1982 序列号算术）

```csharp
// C# 序列号回绕安全比较
public static bool IsSequenceGreater(uint s1, uint s2)
{
    // 如果差值在 uint.MaxValue/2 范围内，s1 > s2
    return (s1 > s2) && (s1 - s2 <= uint.MaxValue / 2)
        || (s1 < s2) && (s2 - s1 > uint.MaxValue / 2);
}
```

##### 2. ACK 机制

ACK（Acknowledgement）是可靠传输的核心：接收方收到数据后发送确认。

**三种 ACK 形式**：

| 形式 | 含义 | 适用场景 |
|------|------|---------|
| 单独 ACK 包 | 只包含确认信息，无业务数据 | 接收方没有数据要发送时 |
| Piggyback ACK | 确认信息附在反向数据包中 | 双向通信时，节省带宽 |
| NACK (Negative ACK) | 告知发送方"缺失了哪些包" | 接收方能立即发现丢包时 |

**ACK 的数据结构**（Bitfield 方式，高效确认一组包）：

```
字段:
- ack (uint32):     确认的最高序列号（此号及之前的所有包都已收到）
- ack_bitfield (uint32): 在 ack 之前的 32 个包的接收位图

示例:
ack = 1005, ack_bitfield = 0b...1011
→ 确认: 1005(收到), 1004(收到), 1003(丢失), 1002(收到), 1001(收到)
```

Bitfield 的优势：一个 4 字节 + 4 字节的 ACK 可以确认 33 个包的状态，带宽效率极高。

##### 3. 重传策略

**超时重传 (Timeout Retransmission)**：

最简单的策略：发送方为每个发出的包启动定时器，超时未收到 ACK 则重传。

```csharp
// 超时重传的核心逻辑
float rtt = CalculateSmoothedRTT(); // 平滑 RTT
retransmitTimeout = rtt * 2 + 50;   // 简单公式：2倍RTT + 安全余量
```

RTT（Round-Trip Time）的计算使用**指数加权移动平均**（EWMA）：

```
SRTT = (1 - α) × SRTT + α × latestRTT    // α 通常取 0.125
RTTVAR = (1 - β) × RTTVAR + β × |SRTT - latestRTT|   // β 通常取 0.25
RTO = SRTT + max(G, 4 × RTTVAR)          // G 是时钟粒度
```

**快速重传 (Fast Retransmit)**：

不等待超时，当收到连续 3 个 ACK 都缺失同一个包时，立即重传。这可以大幅减少重传延迟——从 200ms+ 的 RTO 降到 1 个 RTT。

```
场景:
发送方发出: 1001, 1002, 1003, 1004, 1005 (1002 丢失)
接收方收到 1001 → ACK 1001
接收方收到 1003 → ACK 1001 (期待 1002, ack_bitfield 显示 1003 到了)
接收方收到 1004 → ACK 1001 (期待 1002)
接收方收到 1005 → ACK 1001 (期待 1002)
                        ↑ 连续 3 个 ACK 都缺失 1002
发送方收到第 3 个重复 ACK → 立即重传 1002，不等待超时
```

**冗余发包 (Redundancy)**：

对于帧同步这种场景，可以在每个包中附带前 N 帧的输入数据，即使当前帧丢了，接收方也能从后续帧中恢复：

```
帧 5 的数据: [帧5输入 | 帧4输入 | 帧3输入]
帧 6 的数据: [帧6输入 | 帧5输入 | 帧4输入]
```

帧 5 丢包 → 帧 6 到达时即可补全帧 4 和帧 5 的输入。这在微观层面等同于"FEC（前向纠错）"。

##### 4. 信道/通道设计

将不同类型的消息分配到不同信道，每个信道有独立的可靠性策略：

| 信道 | 可靠性 | 有序 | 用途 |
|------|--------|------|------|
| 信道 0 | 可靠 | 有序 | RPC 调用、关键状态变更、聊天 |
| 信道 1 | 可靠 | 无序 | 实体生成/销毁、重要事件（去重即可） |
| 信道 2 | 不可靠 | 无序 | 位置/旋转快照、帧输入、高频状态 |
| 信道 3 | 不可靠 | 有序 | 连续动画状态（丢失无妨，但顺序不能乱） |

多信道设计让你在同一 UDP 连接上混合可靠和不可靠流量——这正是 TCP 做不到的。

### 主流可靠UDP方案对比

业界已有多个成熟的可靠 UDP 库，大多数游戏不需要从零实现。以下是核心方案对比：

#### KCP

**定位**：以 10%-20% 的额外带宽消耗为代价，换取比 TCP 低 30%-40% 的传输延迟。

**核心特点**：
- 纯算法库，不负责底层 Socket I/O——通过回调函数 `output()` 把数据交给使用者发送
- 选择性重传（只重传真正丢失的包，不像 TCP 重传丢失点之后所有包）
- 快速重传（不等超时）
- 可配置的流控模式：正常模式（同 TCP）和流模式（适合文件传输）
- 协议头部极小：24 字节

**适用场景**：
- 帧同步游戏的帧指令传输（KCP 在中国游戏行业广泛使用）
- 弱网优化（移动网络、跨国通信）
- 作为 skynet、ET 等框架的底层传输组件

**缺点**：
- 带宽消耗比 TCP 高 10%-20%
- 无内置连接管理（需自己实现握手/心跳）
- 无内置加密

#### ENet

**定位**：轻量级、可靠的 UDP 网络库，专为游戏设计。

**核心特点**：
- 完整功能库：连接管理、多信道、可靠/不可靠传输、分片重组、NAT 穿透辅助
- 单线程设计，适合集成到游戏主循环
- 信道设计内置（0-255 个信道，可配置可靠性/有序性）
- C 语言实现，跨平台（Windows/Linux/macOS/iOS/Android/游戏主机）

**适用场景**：
- 需要"开箱即用"的可靠 UDP 方案
- 中小型多人游戏
- 原型快速开发

**缺点**：
- 带宽效率不如 KCP 激进
- 无内置加密
- 社区活跃度近年下降

#### RakNet / SLikeNet

**定位**：功能全面的游戏网络中间件（原商业产品，现开源）。

**核心特点**：
- BitStream 序列化工具（类似 protobuf 但更轻量）
- 可靠的 UDP 层（有连接/无连接两种模式）
- 内置 NAT 穿透服务器
- 内置对象复制系统
- 内置语音聊天功能
- SLikeNet 是 RakNet 的活跃维护分支

**适用场景**：
- 需要全栈网络方案的项目
- 中小型团队（功能全面减少自研）

**缺点**：
- 体量较大，性能不如专项库
- C++ 代码风格较老

#### Google QUIC

**定位**：HTTP/3 的底层传输协议，为 Web 场景设计，但技术理念可借鉴。

**核心特点**：
- 基于 UDP，内置 TLS 1.3 加密
- 0-RTT 握手（重连时零延迟建连）
- 无 HOL 阻塞：不同 HTTP 请求（Stream）之间独立，单个 Stream 丢包不影响其他
- 连接迁移：切换网络 IP 后连接不中断（基于 Connection ID）
- 内置多路复用和流控

**适用场景**（对游戏而言）：
- 服务端之间的 RPC 通信
- Web 游戏的后端 API
- 参考其设计（多 Stream、连接迁移）自研游戏协议

**注意**：QUIC 面向的是 HTTP 流量模式，直接用于游戏协议需要大量定制。但它的设计思想（如用 Connection ID 解耦连接与 IP）值得学习。

#### Steam Datagram Relay (SDR)

**定位**：Valve 为 Dota 2、CS:GO/CS2 开发的游戏网络传输层。

**核心特点**：
- **中继网络**：通过 Valve 全球部署的中继服务器转发流量，隐藏客户端真实 IP（防 DDoS）并优化路由
- 基于 UDP，可选加密
- 智能路由选择（根据延迟和丢包率自动选择最优中继路径）
- 与 Steamworks SDK 集成
- CS2 使用了基于 SDR 的子 tick 系统

**适用场景**：
- 在 Steam 平台发行的游戏
- 需要防 DDoS 的竞技游戏

**技术启示**：SDR 证明了通过部署中继网络可以显著改善高延迟地区的游戏体验。

#### 方案选择决策树

```
需要极低延迟 + 可以接受更多带宽消耗？→ KCP
需开箱即用的完整网络库？              → ENet
需要全栈方案 + NAT穿透 + 语音？       → SLikeNet (RakNet)
服务端间 RPC + 加密 + 连接迁移？       → QUIC (自研灵感)
Steam 平台 + 防DDoS？                  → Steam Datagram Relay
有特殊需求且团队有能力自研？           → 基于以上思想，自研可靠UDP层
```

### 连接管理

虽然 UDP 本身无连接，但可靠 UDP 层需要模拟连接状态来管理会话生命周期。

#### 三次握手（类 TCP 但精简）

```
客户端                          服务端
  |                              |
  |----- ConnectReq (seq=X) ---->|   (1) 客户端发起连接
  |                              |
  |<-- ConnectResp (seq=Y, -----|   (2) 服务端确认 + 分配 Connection ID
  |     ack=X+1)                |
  |                              |
  |----- ConnectAck (ack=Y+1) ->|   (3) 客户端确认，连接建立
  |                              |
  |<==== 数据传输阶段 ==========>|
```

游戏场景下常做的简化：两步握手 + Cookie 防 DDoS：

```
客户端                          服务端
  |                              |
  |----- ConnectReq ----------->|   (1) 请求连接
  |<-- Challenge (cookie) ------|   (2) 服务端返回随机 cookie，不分配资源
  |----- ConnectReq + cookie -->|   (3) 客户端返回 cookie，服务端验证后分配连接
  |<-- Connected ---------------|   (4) 服务端确认建立
```

这种设计的优势是：服务端在步骤 3 之前不分配任何资源，防止 SYN Flood 攻击。

#### 心跳 (Heartbeat)

UDP 连接可能"静默断开"——对方进程崩溃或网络中断，但没有任何通知。

```csharp
// 服务端心跳检测
const float HeartbeatInterval = 5.0f;     // 每 5 秒发送心跳
const float ConnectionTimeout = 15.0f;    // 15 秒未收到任何包则断开

void UpdateHeartbeat(float deltaTime) {
    timeSinceLastSend += deltaTime;
    if (timeSinceLastSend >= HeartbeatInterval) {
        SendPacket(new HeartbeatPacket());
        timeSinceLastSend = 0;
    }

    timeSinceLastReceive += deltaTime;
    if (timeSinceLastReceive >= ConnectionTimeout) {
        Disconnect(DisconnectReason.Timeout);
    }
}
```

心跳的优化：
- 如果最近已经发了业务数据包，可以跳过心跳（"安静心跳"）
- 心跳包应该极小（1-2 字节 payload），甚至可以只是一个空包
- 对大量空闲连接（如大厅中的玩家），可以降低心跳频率

#### 超时断开与 RTO 退避

断开连接有两种方式：

1. **优雅断开**：发送 Disconnect 通知 → 等待 ACK → 释放资源
2. **超时断开**：连续 N 秒无数据 → 判定死连接 → 释放资源

对于重传超时，使用**指数退避**——如果同一包连续重传失败，每次 RTO 翻倍：

```csharp
int retransmitCount = 0;
float rto = estimatedRTT * 2;
while (!ackReceived) {
    await Wait(rto);
    SendPacket(packet);
    retransmitCount++;
    rto *= 2;  // 指数退避
    if (retransmitCount >= MaxRetransmits) {
        Disconnect(DisconnectReason.TooManyRetries);
        break;
    }
}
```

### 拥塞控制和流量控制

可靠 UDP 层需要自己的拥塞控制和流量控制——不能复刻 TCP 的算法，但可以借鉴思想。

#### 滑动窗口 (Sliding Window)

滑动窗口限制"在途中"（已发送但未确认）的数据量：

```
发送窗口 = 已发送未确认的包数量上限

发送方:
  [已确认] [发送中.....] [可发送........] [不可发送]
           |<-- 窗口 -->|

窗口大小动态调整：
- 无丢包时：增大窗口（例如每个 RTT 增加 MSS）
- 检测到丢包时：减半窗口（乘法减小，加法增加 AIMD）
```

接收方也有接收窗口，通过 ACK 告知发送方自己还有多少缓冲区：

```csharp
// 流量控制：接收方在 ACK 中携带接收窗口大小
struct AckPacket {
    uint sequenceAcked;
    uint ackBitfield;
    uint receiveWindow;  // "我还能收这么多字节，别发太快"
}
```

#### 针对游戏的流控策略

游戏的流量模式和文件传输完全不同：

1. **数据量预测**：游戏通常知道每帧/每秒会发多少数据（输入指令 ~数十字节，快照 ~数百字节），不太需要窗口探测
2. **带宽预分配**：可以预设最大发送速率（如 64KB/s），在此范围内不限制
3. **拥塞响应**：丢包时优先考虑冗余发包/快速重传，而非削减发送速率——因为游戏丢包通常不等于拥塞
4. **优先丢弃而非阻塞**：当检测到真实拥塞时，降低不可靠信道的发送速率（丢弃位置更新），保证可靠信道的 RPC 仍能送达

**KCP 的窗口设计值得参考**：

```
发送窗口大小 = min(拥塞窗口, 接收方通告窗口)
拥塞窗口初始 = 10 个包  (比 TCP 的 2-4 个包激进)
拥塞窗口增长 = 每个 RTT 增加 1 (同 TCP)
拥塞窗口缩减 = 丢包时减半, 或仅减 1/8 (比 TCP 温和)
```

### NAT 穿透基础

> 这是网络同步中最"硬核"的工程问题之一——两台位于不同 NAT 后的设备如何直连通信。

#### 为什么需要穿透

IPv4 地址早已枯竭，绝大多数玩家位于 NAT（Network Address Translation）后面。NAT 设备（通常是家用路由器）将内网私有 IP（192.168.x.x）映射到一个公网 IP。

问题：A 和 B 都在 NAT 后面，公网只知道 NAT 的 IP，不知道内部设备。A 无法直接向 B 的私有地址发包。

#### NAT 类型

| 类型 | 行为 | 穿透难度 |
|------|------|---------|
| 完全锥形 (Full Cone) | 任何外部主机可通过映射的公网 IP:Port 发来数据 | 容易 |
| 受限锥形 (Restricted Cone) | 只有本机向目标 IP 发过包，该 IP 才能回包 | 中等 |
| 端口受限锥形 (Port Restricted Cone) | 只有本机向目标 IP:Port 发过包，该 IP:Port 才能回包 | 中等 |
| 对称型 (Symmetric) | 每个目标 IP:Port 分配不同的映射端口 | 困难 |

对称型 NAT 最难穿透，因为端口映射会变，无法预测。

#### STUN (Session Traversal Utilities for NAT)

**原理**：

```
游戏客户端                    STUN 服务器                    对端
   |                            |                           |
   |-- 我是谁？ --------------->|                           |
   |<-- 你的公网地址是 1.2.3.4:5555 --|                     |
   |                                                       |
   |-- (通过信令服务器交换地址) --------------------------->|
   |<-- 对端的公网地址是 5.6.7.8:6666 -------------------|
   |                                                       |
   |==== 直接 UDP 通信 ====================================|
```

STUN 是一个简单的查询-响应协议：客户端向 STUN 服务器询问"我在公网上看起来是什么地址？"，然后通过信令服务器（可以是 HTTP/WebSocket）将这个地址告诉对端。双方知道对方的公网地址后，直接 UDP 打洞。

#### TURN (Traversal Using Relays around NAT)

当 STUN 打洞失败（如双方都是对称型 NAT），TURN 作为中继兜底：

```
客户端 A ←→ TURN 中继服务器 ←→ 客户端 B
```

TURN 服务器将 A 的数据转发给 B，反之亦然。代价是：
- 延迟增加（多一跳）
- 服务器带宽成本（所有数据都经过中继）
- 但保证了连通性

#### ICE (Interactive Connectivity Establishment)

ICE 不是单独一个协议，而是一个**协商框架**：收集所有可能的候选地址（本地地址、STUN 反射地址、TURN 中继地址），然后逐对测试连通性，选择最优路径。

```
候选地址优先级:
1. 直连 (host): 192.168.1.5               ← 同局域网最优先
2. STUN 反射 (srflx): 1.2.3.4:5555        ← NAT 后首选
3. TURN 中继 (relay): turn.example.com    ← 兜底
```

WebRTC 内置了完整的 ICE 实现，游戏也可以使用 WebRTC Data Channel（本质是 SCTP over DTLS over ICE over UDP）作为传输层。

#### 游戏中的 NAT 穿透实践

对于游戏开发者，有两个选择：

1. **使用现成的**：如 Steam Networking、WebRTC、或部署 STUN/TURN 服务
2. **自研简单版**：绝大多数场景下，UDP 打洞的原理很简单——双方同时向对方的公网 IP:Port 发包，"打"穿 NAT 的映射规则

```
打洞关键：双方同时发包
1. A 向 B 的公网地址发包 → 在 A 的 NAT 上创建映射
2. B 向 A 的公网地址发包 → 在 B 的 NAT 上创建映射
3. 两个方向都有映射后，数据可以双向流通

Tips:
- 对称型 NAT 需要端口预测或 TURN 兜底
- 移动网络（4G/5G）大多是对称型 NAT，TURN 是必要的
- 大约 8%-15% 的玩家对需要 TURN 中继
```

---

## 2. 代码示例

### 示例 1: Unity C# — 手写简单可靠UDP层

这是一个最小可运行的可靠 UDP 实现，演示序列号、ACK bitfield 和超时重传的核心逻辑。

```csharp
// ReliableUdpClient.cs
// 最小可靠UDP层实现 — 只做序列号+ACK+超时重传
// 可在 Unity 中直接使用，需要 .NET Standard 2.1+

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Threading;

/// <summary>
/// 可靠UDP数据包的头部结构
/// 总开销: 13 字节
/// </summary>
public struct PacketHeader
{
    public const int Size = 13;

    public byte ProtocolId;        // 协议标识 (区分我们的包和其他流量)
    public uint Sequence;          // 序列号 (每个发出的包严格递增)
    public uint Ack;               // 确认的最高序列号
    public uint AckBitfield;       // Ack 之前 32 个包的接收位图

    public byte[] Serialize()
    {
        byte[] buffer = new byte[Size];
        buffer[0] = ProtocolId;
        // 使用大端序写入，确保跨平台一致性
        BitConverter.GetBytes(Sequence).CopyTo(buffer, 1);     // 如果需要大端序，手动翻转
        BitConverter.GetBytes(Ack).CopyTo(buffer, 5);
        BitConverter.GetBytes(AckBitfield).CopyTo(buffer, 9);
        return buffer;
    }

    public static PacketHeader Deserialize(byte[] data, int offset = 0)
    {
        return new PacketHeader
        {
            ProtocolId = data[offset],
            Sequence = BitConverter.ToUInt32(data, offset + 1),
            Ack = BitConverter.ToUInt32(data, offset + 5),
            AckBitfield = BitConverter.ToUInt32(data, offset + 9)
        };
    }
}

/// <summary>
/// 未确认的数据包记录 — 存储在发送队列中等待ACK
/// </summary>
public class PendingPacket
{
    public uint Sequence;
    public byte[] Data;
    public float SendTime;         // 上次发送时间 (用于超时计算)
    public int RetransmitCount;    // 已重传次数

    public PendingPacket(uint seq, byte[] data, float sendTime)
    {
        Sequence = seq;
        Data = data;
        SendTime = sendTime;
        RetransmitCount = 0;
    }
}

/// <summary>
/// 可靠UDP层 — 管理连接、发送/接收、ACK、重传
/// </summary>
public class ReliableUdpClient
{
    private UdpClient _udpClient;
    private IPEndPoint _remoteEndPoint;

    // 序列号管理
    private uint _sendSequence = 0;     // 下一个要发送的序列号
    private uint _recvSequence = 0;     // 期望接收的下一个序列号

    // 接收缓冲区: 记录最近收到的 33 个包的状态，用于生成 ACK Bitfield
    // receivedHistory[0] = 最新收到的 seq 的状态
    // receivedHistory[i] = (_recvSequence - 1 - i) 号包的状态
    private bool[] _receivedHistory = new bool[33];

    // 发送队列: 等待 ACK 的包
    // Key: sequence number
    private Dictionary<uint, PendingPacket> _pendingPackets = new Dictionary<uint, PendingPacket>();

    // RTT 和重传配置
    private float _estimatedRTT = 0.1f;          // 初始 RTT 估计: 100ms
    private const float _rttAlpha = 0.125f;       // EWMA 平滑因子
    private const int _maxRetransmits = 10;       // 最大重传次数
    private float _timeSinceLastSend = 0f;

    // 心跳配置
    private const float _heartbeatInterval = 5.0f;
    private const float _connectionTimeout = 15.0f;
    private float _timeSinceLastReceive = 0f;

    // 接收方缓存: 暂存乱序到达的包
    // Key: sequence number, Value: payload data
    private SortedList<uint, byte[]> _outOfOrderBuffer = new SortedList<uint, byte[]>();
    private const int _maxOutOfOrderBuffer = 64;  // 最多缓存 64 个乱序包

    // 事件
    public event Action<byte[]> OnDataReceived;
    public event Action<string> OnDisconnected;
    public event Action OnConnected;
    public bool IsConnected { get; private set; }

    /// <summary>
    /// 连接到远程端点 (游戏场景通常用两步握手，这里简化为直接建立)
    /// </summary>
    public void Connect(string host, int port)
    {
        _udpClient = new UdpClient();
        _remoteEndPoint = new IPEndPoint(IPAddress.Parse(host), port);
        IsConnected = true;

        // 发送连接请求 (序列号从 0 开始)
        SendPacket(new byte[] { 0x01 }, reliable: true); // 0x01 = 连接请求

        // 启动接收线程 (Unity 中可用 async/await 或主线程 Update 轮询)
        _udpClient.BeginReceive(OnReceive, null);

        OnConnected?.Invoke();
    }

    /// <summary>
    /// 发送数据 (可选可靠/不可靠)
    /// reliable=true 时数据进入待确认队列，超时重传
    /// reliable=false 时直接发送，不保证送达
    /// </summary>
    public void Send(byte[] payload, bool reliable = true)
    {
        if (!IsConnected) return;
        // 构造完整包: 头部 + 业务数据
        byte[] packet = BuildPacket(payload);
        _udpClient.Send(packet, packet.Length, _remoteEndPoint);

        if (reliable)
        {
            // 记录到待确认队列
            _pendingPackets[_sendSequence - 1] = new PendingPacket(
                _sendSequence - 1, packet, UnityEngine.Time.time
            );
        }
    }

    /// <summary>
    /// 每帧调用 — 处理重传、心跳、超时检测
    /// Unity: 在 Update() 中调用
    /// </summary>
    public void Update(float deltaTime)
    {
        if (!IsConnected) return;

        // 1. 检查待确认包，超时则重传
        CheckRetransmissions(deltaTime);

        // 2. 心跳
        _timeSinceLastSend += deltaTime;
        _timeSinceLastReceive += deltaTime;

        if (_timeSinceLastSend >= _heartbeatInterval)
        {
            SendHeartbeat();
            _timeSinceLastSend = 0f;
        }

        if (_timeSinceLastReceive >= _connectionTimeout)
        {
            Disconnect("Connection timeout");
        }
    }

    /// <summary>
    /// 构建完整数据包: 头部 + payload
    /// </summary>
    private byte[] BuildPacket(byte[] payload)
    {
        uint currentAck = _recvSequence > 0 ? _recvSequence - 1 : 0;
        uint ackBitfield = CalculateAckBitfield();

        PacketHeader header = new PacketHeader
        {
            ProtocolId = 0xAB,          // 自定义协议标识
            Sequence = _sendSequence++,
            Ack = currentAck,
            AckBitfield = ackBitfield
        };

        byte[] headerBytes = header.Serialize();
        byte[] fullPacket = new byte[PacketHeader.Size + payload.Length];
        Buffer.BlockCopy(headerBytes, 0, fullPacket, 0, PacketHeader.Size);
        Buffer.BlockCopy(payload, 0, fullPacket, PacketHeader.Size, payload.Length);

        return fullPacket;
    }

    /// <summary>
    /// 根据接收历史计算 ACK Bitfield
    /// receivedHistory[0] = 刚收到的这个 seq 之前的 seq
    /// bit i = 1 表示 (latestReceived - 1 - i) 号包已收到
    /// </summary>
    private uint CalculateAckBitfield()
    {
        uint bitfield = 0;
        for (int i = 0; i < 32; i++)
        {
            if (_receivedHistory[i])
                bitfield |= (1u << i);
        }
        return bitfield;
    }

    /// <summary>
    /// 处理接收到的数据
    /// </summary>
    private void OnReceive(IAsyncResult ar)
    {
        try
        {
            IPEndPoint sender = new IPEndPoint(IPAddress.Any, 0);
            byte[] data = _udpClient.EndReceive(ar, ref sender);

            // 验证来源地址
            if (!sender.Equals(_remoteEndPoint)) return;

            // 解析头部
            PacketHeader header = PacketHeader.Deserialize(data, 0);
            if (header.ProtocolId != 0xAB) return; // 不是我们的包

            // 提取 payload
            int payloadLength = data.Length - PacketHeader.Size;
            byte[] payload = new byte[payloadLength];
            Buffer.BlockCopy(data, PacketHeader.Size, payload, 0, payloadLength);

            _timeSinceLastReceive = 0f;

            // 处理 ACK 信息: 确认对方收到了我们的哪些包
            ProcessAck(header.Ack, header.AckBitfield);

            // 处理对方发来的新数据
            ProcessIncomingData(header.Sequence, payload);

            // 继续接收下一个包
            _udpClient.BeginReceive(OnReceive, null);
        }
        catch (ObjectDisposedException)
        {
            // Socket 已关闭，正常退出
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError($"Receive error: {ex.Message}");
        }
    }

    /// <summary>
    /// 处理对方的 ACK 确认 — 从待确认队列中移除已确认的包
    /// </summary>
    private void ProcessAck(uint latestAck, uint ackBitfield)
    {
        // 计算新的 RTT 样本 (从最近被 ACK 的包中)
        if (_pendingPackets.ContainsKey(latestAck))
        {
            float rtt = UnityEngine.Time.time - _pendingPackets[latestAck].SendTime;
            if (rtt > 0)
            {
                // EWMA 平滑 RTT
                _estimatedRTT = (1 - _rttAlpha) * _estimatedRTT + _rttAlpha * rtt;
            }
        }

        // 移除已确认的包
        List<uint> toRemove = new List<uint>();
        foreach (var kvp in _pendingPackets)
        {
            uint seq = kvp.Key;

            // 检查 seq 是否被确认
            if (seq == latestAck || IsAckedByBitfield(seq, latestAck, ackBitfield))
            {
                toRemove.Add(seq);
            }
        }

        foreach (uint seq in toRemove)
        {
            _pendingPackets.Remove(seq);
        }
    }

    /// <summary>
    /// 判断序列号 seq 是否被 bitfield 确认
    /// seq 在 ack 之前 1-32 号范围内，且对应的 bit 为 1，则是已确认
    /// </summary>
    private bool IsAckedByBitfield(uint seq, uint latestAck, uint bitfield)
    {
        if (seq >= latestAck) return false; // seq 不能 >= latestAck

        uint diff = latestAck - seq;
        if (diff > 32) return false; // 超出 bitfield 范围

        // diff=1 → bit 0, diff=2 → bit 1, ..., diff=32 → bit 31
        return (bitfield & (1u << (int)(diff - 1))) != 0;
    }

    /// <summary>
    /// 处理新到达的数据 — 处理乱序和重复
    /// </summary>
    private void ProcessIncomingData(uint seq, byte[] payload)
    {
        // 更新接收历史 (为下一次 ACK 做准备)
        UpdateReceiveHistory(seq);

        // 重复包检测
        if (seq <= _recvSequence && _recvSequence > 0)
        {
            // 这是重复包 (我们已经收到了更新的包)
            // 仍然需要更新 ACK 信息，但不需要处理数据
            return;
        }

        // 乱序检测
        if (seq > _recvSequence)
        {
            // 有包丢失! 记录缺失的序列号
            for (uint missing = _recvSequence; missing < seq; missing++)
            {
                // 缺失的包会被后续的冗余数据或重传补上
            }

            // 缓存这个包
            _outOfOrderBuffer[seq] = payload;

            // 如果缓冲区过大，清理旧数据
            while (_outOfOrderBuffer.Count > _maxOutOfOrderBuffer)
            {
                _outOfOrderBuffer.RemoveAt(0);
            }

            // 尝试顺序交付缓冲区中的数据
            DeliverInOrder();
        }
    }

    /// <summary>
    /// 更新接收历史 — 将新收到的 seq 插入历史数组
    /// </summary>
    private void UpdateReceiveHistory(uint seq)
    {
        if (_recvSequence == 0)
        {
            // 第一个包
            _recvSequence = seq + 1;
            return;
        }

        if (seq >= _recvSequence)
        {
            // 收到了更新的包: 将之间的 seq 标记为未收到
            int shift = (int)(seq - _recvSequence);
            // 将现有历史向后移动 shift 位
            for (int i = 31; i >= shift; i--)
            {
                _receivedHistory[i] = _receivedHistory[i - shift];
            }
            for (int i = 0; i < shift && i < 33; i++)
            {
                _receivedHistory[i] = false; // 中间的包状态未知，标记为未收到
            }
            // 最新收到的 seq - 1 的包标记为已收到
            if (shift == 0)
                _receivedHistory[0] = true;

            _recvSequence = seq + 1;
        }
        else
        {
            // seq < _recvSequence: 这是之前丢失的包，现在补上了
            int offset = (int)(_recvSequence - 1 - seq);
            if (offset >= 0 && offset < 33)
            {
                _receivedHistory[offset] = true;
            }
        }
    }

    /// <summary>
    /// 按序交付缓冲区中的数据
    /// </summary>
    private void DeliverInOrder()
    {
        // 从最小序列号开始，检查是否可以顺序交付
        // _outOfOrderBuffer 是 SortedList，按 key 排序
        List<uint> delivered = new List<uint>();
        foreach (var kvp in _outOfOrderBuffer)
        {
            // 只有序列号连续的才能交付
            if (kvp.Key <= _recvSequence)
            {
                // 已是重复包 (在 UpdateReceiveHistory 中已处理)
                delivered.Add(kvp.Key);
                continue;
            }

            if (kvp.Key == _recvSequence)
            {
                // 正好是下一个期望的包!
                OnDataReceived?.Invoke(kvp.Value);
                _recvSequence = kvp.Key + 1;
                delivered.Add(kvp.Key);
            }
            else
            {
                // 还有缺口，停止交付
                break;
            }
        }

        foreach (uint seq in delivered)
        {
            _outOfOrderBuffer.Remove(seq);
        }
    }

    /// <summary>
    /// 检查超时未确认的包并重传
    /// </summary>
    private void CheckRetransmissions(float deltaTime)
    {
        float rto = _estimatedRTT * 2.0f + 0.05f; // RTO = 2×RTT + 50ms 安全余量
        List<uint> toRemove = new List<uint>();

        foreach (var kvp in _pendingPackets)
        {
            PendingPacket pending = kvp.Value;
            float elapsed = UnityEngine.Time.time - pending.SendTime;

            if (elapsed >= rto)
            {
                if (pending.RetransmitCount >= _maxRetransmits)
                {
                    // 重传次数耗尽，断开连接
                    toRemove.Add(kvp.Key);
                    Disconnect("Too many retransmissions");
                    return;
                }

                // 重传!
                _udpClient.Send(pending.Data, pending.Data.Length, _remoteEndPoint);
                pending.SendTime = UnityEngine.Time.time;
                pending.RetransmitCount++;

                UnityEngine.Debug.Log(
                    $"Retransmit seq={pending.Sequence}, " +
                    $"attempt={pending.RetransmitCount}, " +
                    $"RTO={rto * 1000:F0}ms"
                );
            }
        }

        foreach (uint seq in toRemove)
        {
            _pendingPackets.Remove(seq);
        }
    }

    /// <summary>
    /// 发送心跳包
    /// </summary>
    private void SendHeartbeat()
    {
        // 心跳包体可以只是一个字节 (0xFF = PING)
        Send(new byte[] { 0xFF }, reliable: false);
    }

    /// <summary>
    /// 断开连接
    /// </summary>
    public void Disconnect(string reason = "Manual disconnect")
    {
        if (!IsConnected) return;

        // 发送断开通知 (不可靠发送，丢了也无妨)
        Send(new byte[] { 0x02 }, reliable: false); // 0x02 = 断开

        IsConnected = false;
        _udpClient?.Close();
        _udpClient = null;

        _pendingPackets.Clear();
        _outOfOrderBuffer.Clear();

        OnDisconnected?.Invoke(reason);
    }

    /// <summary>
    /// 清理资源
    /// </summary>
    public void Dispose()
    {
        Disconnect("Disposed");
    }
}
```

**使用示例 (Unity MonoBehaviour)**：

```csharp
// GameNetworkManager.cs
// 挂载到 Unity GameObject 上
using UnityEngine;

public class GameNetworkManager : MonoBehaviour
{
    private ReliableUdpClient _client;

    void Start()
    {
        _client = new ReliableUdpClient();
        _client.OnDataReceived += HandleData;
        _client.OnConnected += () => Debug.Log("Connected!");
        _client.OnDisconnected += (reason) => Debug.Log($"Disconnected: {reason}");

        // 连接到游戏服务器
        _client.Connect("127.0.0.1", 7777);
    }

    void Update()
    {
        _client?.Update(Time.deltaTime);

        // 模拟帧同步: 每帧发送玩家输入
        if (_client != null && _client.IsConnected)
        {
            byte[] inputData = SerializePlayerInput();
            _client.Send(inputData, reliable: false); // 帧输入用不可靠模式
        }
    }

    void HandleData(byte[] data)
    {
        // 处理服务端发来的数据 (帧确认、状态快照等)
        Debug.Log($"Received {data.Length} bytes from server");
        DeserializeAndApply(data);
    }

    byte[] SerializePlayerInput()
    {
        // 将玩家按键状态序列化为字节 (示例: 4字节)
        byte[] data = new byte[4];
        data[0] = (byte)(Input.GetKey(KeyCode.W) ? 1 : 0);
        data[1] = (byte)(Input.GetKey(KeyCode.S) ? 1 : 0);
        data[2] = (byte)(Input.GetKey(KeyCode.A) ? 1 : 0);
        data[3] = (byte)(Input.GetKey(KeyCode.D) ? 1 : 0);
        return data;
    }

    void DeserializeAndApply(byte[] data)
    {
        // 反序列化服务端状态并应用到本地 GameObjects
        // (具体实现依赖游戏逻辑)
    }

    void OnDestroy()
    {
        _client?.Dispose();
    }
}
```

### 示例 2: C++ — ENet 集成示例

ENet 是开箱即用的可靠 UDP 库，内置连接管理、多信道、分片重组。

```cpp
// enet_example.cpp
// ENet 使用示例 — 游戏客户端/服务端的基础骨架
// 编译: g++ -o enet_example enet_example.cpp -lenet
// 或 Windows: cl enet_example.cpp enet.lib ws2_32.lib winmm.lib

#include <enet/enet.h>
#include <cstdio>
#include <cstring>
#include <vector>
#include <chrono>
#include <thread>

// ============================================================
// 服务端示例
// ============================================================
class GameServer {
public:
    GameServer(uint16_t port, int maxClients)
        : _server(nullptr), _maxClients(maxClients) {

        // 1. 初始化 ENet
        if (enet_initialize() != 0) {
            fprintf(stderr, "Failed to initialize ENet\n");
            exit(EXIT_FAILURE);
        }

        // 2. 创建 ENetHost (服务端)
        ENetAddress address;
        address.host = ENET_HOST_ANY;  // 监听所有网卡
        address.port = port;

        _server = enet_host_create(
            &address,        // 监听地址
            maxClients,      // 最大连接数
            2,               // 信道数量 (0: 可靠, 1: 不可靠)
            0,               // 入站带宽限制 (0 = 无限制)
            0                // 出站带宽限制 (0 = 无限制)
        );

        if (!_server) {
            fprintf(stderr, "Failed to create server host\n");
            exit(EXIT_FAILURE);
        }

        printf("[Server] Listening on port %d\n", port);
    }

    ~GameServer() {
        if (_server) {
            enet_host_destroy(_server);
        }
        enet_deinitialize();
    }

    /// <summary>
    /// 每帧调用 — 处理事件、发送游戏状态
    /// </summary>
    void Update() {
        ENetEvent event;

        // 3. 轮询事件 (超时 0 = 非阻塞)
        while (enet_host_service(_server, &event, 0) > 0) {
            switch (event.type) {
                case ENET_EVENT_TYPE_CONNECT:
                    HandleConnect(event);
                    break;

                case ENET_EVENT_TYPE_RECEIVE:
                    HandleReceive(event);
                    // !! 关键: 处理完必须释放包 !!
                    enet_packet_destroy(event.packet);
                    break;

                case ENET_EVENT_TYPE_DISCONNECT:
                    HandleDisconnect(event);
                    break;

                case ENET_EVENT_TYPE_NONE:
                    break;
            }
        }

        // 4. 发送游戏状态快照 (60fps)
        BroadcastGameState();
    }

private:
    void HandleConnect(const ENetEvent& event) {
        printf("[Server] Client connected from %x:%u\n",
               event.peer->address.host, event.peer->address.port);

        // 可以设置用户数据来关联游戏特定的客户端信息
        event.peer->data = nullptr; // 这里可以存储 PlayerState*
    }

    void HandleReceive(const ENetEvent& event) {
        // 5. 根据信道 ID 区分消息类型
        switch (event.channelID) {
            case 0: {
                // 信道 0: 可靠有序 — RPC 调用、聊天消息
                printf("[Server] Reliable msg from client: %.*s\n",
                       (int)event.packet->dataLength, event.packet->data);
                break;
            }
            case 1: {
                // 信道 1: 不可靠 — 玩家输入、位置更新
                // 解析玩家输入 (假设前 4 字节是 float 的 x, z 移动)
                if (event.packet->dataLength >= 8) {
                    float moveX, moveZ;
                    memcpy(&moveX, event.packet->data, 4);
                    memcpy(&moveZ, event.packet->data + 4, 4);
                    printf("[Server] Player input: moveX=%.2f moveZ=%.2f\n", moveX, moveZ);

                    // 应用输入到权威游戏状态
                    ApplyPlayerInput(event.peer, moveX, moveZ);
                }
                break;
            }
        }
    }

    void HandleDisconnect(const ENetEvent& event) {
        printf("[Server] Client disconnected\n");

        // 清理玩家状态
        if (event.peer->data) {
            // delete static_cast<PlayerState*>(event.peer->data);
            event.peer->data = nullptr;
        }
    }

    void BroadcastGameState() {
        // 构造状态快照数据包
        char buffer[256];
        int len = snprintf(buffer, sizeof(buffer),
            "STATE|tick=%llu|players=%zu",
            _currentTick, _players.size());

        // 6. 创建广播数据包
        ENetPacket* packet = enet_packet_create(
            buffer,
            len,
            ENET_PACKET_FLAG_UNRELIABLE_FRAGMENT  // 不可靠分片 (大包用)
        );

        // 广播到所有连接的客户端 (信道 0 = 可靠, 信道 1 = 不可靠)
        enet_host_broadcast(_server, 0, packet);
        // 注意: enet_host_broadcast 内部会自动复制 packet，
        // 不需要手动 destroy

        _currentTick++;
    }

    void ApplyPlayerInput(ENetPeer* peer, float moveX, float moveZ) {
        // 应用玩家输入到权威游戏逻辑
        // (这里省略具体实现)
    }

    ENetHost* _server;
    int _maxClients;
    uint64_t _currentTick = 0;
    std::vector<void*> _players; // 实际应该是 PlayerState 指针
};

// ============================================================
// 客户端示例
// ============================================================
class GameClient {
public:
    GameClient()
        : _client(nullptr), _peer(nullptr) {

        if (enet_initialize() != 0) {
            fprintf(stderr, "Failed to initialize ENet\n");
            exit(EXIT_FAILURE);
        }
    }

    ~GameClient() {
        Disconnect();
        enet_deinitialize();
    }

    /// <summary>
    /// 连接到服务器
    /// </summary>
    bool Connect(const char* host, uint16_t port) {
        // 创建客户端 Host (只连一个服务器，所以最大连接数 = 1)
        _client = enet_host_create(
            nullptr,         // 客户端不需要绑定地址
            1,               // 最大 1 个出站连接
            2,               // 2 个信道
            0, 0             // 带宽无限制
        );

        if (!_client) {
            fprintf(stderr, "Failed to create client host\n");
            return false;
        }

        // 解析服务器地址并连接
        ENetAddress address;
        enet_address_set_host(&address, host);
        address.port = port;

        _peer = enet_host_connect(_client, &address, 2, 0);
        if (!_peer) {
            fprintf(stderr, "No available peers\n");
            return false;
        }

        // 等待连接建立 (阻塞方式，生产环境应异步)
        ENetEvent event;
        if (enet_host_service(_client, &event, 5000) > 0 &&
            event.type == ENET_EVENT_TYPE_CONNECT) {
            printf("[Client] Connected to server\n");
            return true;
        }

        // 连接失败
        enet_peer_reset(_peer);
        return false;
    }

    /// <summary>
    /// 发送玩家输入 (不可靠信道)
    /// </summary>
    void SendPlayerInput(float moveX, float moveZ) {
        if (!_peer) return;

        // 构造输入数据
        char buffer[8];
        memcpy(buffer, &moveX, 4);
        memcpy(buffer + 4, &moveZ, 4);

        // 7. 创建并发送不可靠数据包
        ENetPacket* packet = enet_packet_create(
            buffer, 8,
            ENET_PACKET_FLAG_UNSEQUENCED  // 不可靠 + 无序
            // 如果需要不可靠但有序: 使用 ENET_PACKET_FLAG_UNRELIABLE_FRAGMENT 或不带 flag
        );

        enet_peer_send(_peer, 1, packet); // 信道 1 = 不可靠
    }

    /// <summary>
    /// 发送可靠 RPC 调用 (可靠信道)
    /// </summary>
    void SendRPC(const char* method, const char* args) {
        if (!_peer) return;

        char buffer[512];
        int len = snprintf(buffer, sizeof(buffer), "RPC|%s|%s", method, args);

        // 8. 可靠 + 有序 数据包 (默认标志)
        ENetPacket* packet = enet_packet_create(
            buffer, len,
            ENET_PACKET_FLAG_RELIABLE  // 保证送达 + 保证顺序
        );

        enet_peer_send(_peer, 0, packet); // 信道 0 = 可靠
    }

    /// <summary>
    /// 每帧处理网络事件
    /// </summary>
    void Update() {
        if (!_client) return;

        ENetEvent event;
        while (enet_host_service(_client, &event, 0) > 0) {
            switch (event.type) {
                case ENET_EVENT_TYPE_RECEIVE:
                    printf("[Client] Received %d bytes on channel %d: %.*s\n",
                           (int)event.packet->dataLength,
                           (int)event.channelID,
                           (int)event.packet->dataLength,
                           event.packet->data);
                    enet_packet_destroy(event.packet);
                    break;

                case ENET_EVENT_TYPE_DISCONNECT:
                    printf("[Client] Disconnected from server\n");
                    _peer = nullptr;
                    break;

                default:
                    break;
            }
        }
    }

    void Disconnect() {
        if (_peer) {
            enet_peer_disconnect(_peer, 0);

            // 等待断开确认 (非阻塞)
            ENetEvent event;
            while (enet_host_service(_client, &event, 3000) > 0) {
                if (event.type == ENET_EVENT_TYPE_DISCONNECT) {
                    printf("[Client] Disconnected gracefully\n");
                    break;
                }
            }

            enet_peer_reset(_peer);
            _peer = nullptr;
        }

        if (_client) {
            enet_host_destroy(_client);
            _client = nullptr;
        }
    }

private:
    ENetHost* _client;
    ENetPeer* _peer;
};

// ============================================================
// 主函数 — 演示服务端/客户端交互流程
// ============================================================
int main() {
    // 启动服务端
    GameServer server(7777, 32);

    // 启动客户端并连接
    GameClient client;
    if (!client.Connect("127.0.0.1", 7777)) {
        fprintf(stderr, "Client failed to connect\n");
        return 1;
    }

    // 模拟游戏循环 (60fps = ~16ms/tick)
    auto lastTime = std::chrono::steady_clock::now();
    const auto tickDuration = std::chrono::milliseconds(16);

    for (int frame = 0; frame < 600; frame++) { // 运行 600 帧 (~10秒)
        auto now = std::chrono::steady_clock::now();

        // 更新服务端 (处理消息 + 广播状态)
        server.Update();

        // 更新客户端 (处理消息)
        client.Update();

        // 模拟玩家输入
        client.SendPlayerInput(
            sinf(frame * 0.1f),   // X 轴正弦运动
            cosf(frame * 0.1f)    // Z 轴余弦运动
        );

        // 帧率控制
        auto elapsed = std::chrono::steady_clock::now() - now;
        if (elapsed < tickDuration) {
            std::this_thread::sleep_for(tickDuration - elapsed);
        }
    }

    printf("Demo complete\n");
    return 0;
}
```

**ENet 信道标志速查表**：

```cpp
// ENet 数据包可靠性标志
ENET_PACKET_FLAG_RELIABLE             // 可靠 + 有序 (默认)
ENET_PACKET_FLAG_UNSEQUENCED          // 不可靠 + 无序 (最新包覆盖旧包)
ENET_PACKET_FLAG_UNRELIABLE_FRAGMENT  // 不可靠 + 有序 (多余一个包到达时丢弃旧的)
// 不带任何 FLAG → 等同于 ENET_PACKET_FLAG_RELIABLE

// 创建信道时指定行为:
// enet_host_create(..., channelLimit=2, ...)
// 每个 Peer 创建后，信道默认是可靠有序。
// 要改变信道行为，需要修改 ENet 源码或使用 enet_peer_send 时的 flags。
```

### 示例 3: Lua — KCP 在 skynet 中的使用

KCP 是云风 (cloudwu) 开发的可靠传输协议，广泛用于中国游戏行业的帧同步项目中。skynet 框架内置了对 KCP 的支持。

```lua
-- kcp_agent.lua
-- skynet 中使用 KCP 的网络代理服务
-- 每个客户端连接对应一个 agent，负责该连接的 KCP 数据收发

local skynet = require "skynet"
local socket = require "skynet.socket"
local crypt = require "skynet.crypt"

-- KCP 模式常量 (定义在 skynet/lualib/skynet/socket.lua 中)
local KCP_RAW   = 0   -- 原始 KCP 模式 (不使用 skynet 内部流控)
local KCP_NORMAL = 1  -- 标准模式 (带流控)

local agent = {}
local CMD = {}

-- KCP 配置参数 (帧同步场景的推荐值)
local KCP_CONFIG = {
    nodelay = 1,       -- 启用 nodelay 模式
    interval = 10,     -- 内部更新间隔 (ms)，越小延迟越低但 CPU 消耗越大
    resend = 2,        -- 快速重传阈值 (收到多少个重复 ACK 就触发)
    nc = 1,            -- 是否关闭拥塞控制 (0=关闭, 1=开启)
    sndwnd = 128,      -- 发送窗口大小 (包数)
    rcvwnd = 128,      -- 接收窗口大小
    mtu = 512,         -- 最大传输单元 (字节)，帧同步小包场景可以用更小的值
}

function agent.start(client_fd, gate)
    -- 1. 将普通 TCP socket 升级为 KCP socket
    --    (KCP 仍然使用底层的 UDP socket，这里演示 skynet 的封装)
    socket.start(client_fd)

    -- 设置 KCP 参数
    socket.kcp(client_fd, KCP_CONFIG)

    -- 2. 握手阶段: 等待客户端的连接请求
    local handshake_ok = agent.handshake(client_fd)
    if not handshake_ok then
        socket.close(client_fd)
        return
    end

    skynet.info_func(function()
        return string.format("agent [%d] connected", client_fd)
    end)

    -- 3. 进入主循环: 收发帧数据
    agent.main_loop(client_fd)
end

--- 简单的挑战-响应握手
function agent.handshake(fd)
    -- 生成随机 challenge
    local challenge = crypt.randomkey()
    socket.write(fd, "CHALLENGE:" .. challenge)

    -- 等待客户端响应 (5 秒超时)
    local response = socket.read(fd, 5000)
    if not response then
        skynet.error("Handshake timeout")
        return false
    end

    -- 验证响应 (生产环境应使用 HMAC 或更严格的验证)
    local expected = "RESPONSE:" .. crypt.hexencode(crypt.sha256(challenge))
    if response ~= expected then
        skynet.error("Handshake failed: invalid response")
        skynet.error("expected:", expected)
        skynet.error("got:", response)
        return false
    end

    skynet.error("Handshake OK")
    return true
end

--- 帧同步主循环
function agent.main_loop(fd)
    local frame_index = 0          -- 当前帧序号
    local frame_buffer = {}        -- 帧数据缓冲区 (用于冗余发送)
    local BUFFER_SIZE = 3          -- 冗余帧数: 每帧附带前 3 帧的数据

    -- 客户端输入缓冲区 (处理乱序到达的帧指令)
    local input_pending = {}       -- [frame] = raw_data

    while true do
        -- 4. 接收帧指令 (等待时间: 一帧的时间 = 33ms @30fps)
        local raw_data = socket.read(fd, 33)
        if not raw_data then
            -- 超时: 没有收到客户端输入
            -- 在帧同步中，这说明客户端可能掉线或网络卡顿
            -- 可以使用"空输入"作为默认值继续推进帧
            raw_data = "\x00\x00\x00\x00"  -- 空输入 (4 字节全 0)
        end

        -- 5. 解析帧序号和输入数据
        -- 协议格式: [4字节帧序号][输入数据...]
        local client_frame = string.unpack(">I4", raw_data, 1)  -- 大端序 uint32
        local input_data = string.sub(raw_data, 5)

        -- 存储帧指令 (处理可能的乱序)
        input_pending[client_frame] = input_data

        -- 6. 收集当前帧需要执行的所有玩家输入
        local all_inputs = agent.collect_inputs(input_pending, frame_index)

        if all_inputs then
            -- 7. 执行帧逻辑 (调用战斗服务)
            local frame_result = agent.execute_frame(frame_index, all_inputs)

            -- 8. 将帧结果加入冗余缓冲区
            table.insert(frame_buffer, frame_result)
            if #frame_buffer > BUFFER_SIZE then
                table.remove(frame_buffer, 1)
            end

            -- 9. 发送帧确认给客户端 (附带冗余数据)
            agent.send_frame_ack(fd, frame_index, frame_buffer)

            frame_index = frame_index + 1
        end
    end
end

--- 收集某一帧的所有玩家输入
--- 在帧同步中，服务端需要收集所有玩家的帧指令后才能推进
function agent.collect_inputs(input_pending, target_frame)
    -- 简化版: 只有一个玩家，直接返回
    local input = input_pending[target_frame]
    if input then
        input_pending[target_frame] = nil  -- 清理
        return input
    end

    -- 如果还没有收到这一帧的输入，返回 nil 表示"等待"
    -- 在实际项目中，如果有多个玩家，需要等所有人的输入到齐
    return nil
end

--- 执行一帧的游戏逻辑
function agent.execute_frame(frame_idx, inputs)
    -- 调用战斗计算服务 (通常是另一个 skynet 服务)
    -- local result = skynet.call(".battle", "lua", "execute", frame_idx, inputs)

    -- 返回帧结果 (包含所有实体的状态变化)
    return string.format("FRAME:%d|DATA:%s", frame_idx, inputs)
end

--- 发送帧确认 + 冗余数据
function agent.send_frame_ack(fd, frame_idx, frame_buffer)
    -- 构建数据包: [ACK帧序号][冗余帧数量][冗余帧数据...]
    local packet = string.pack(">I4I2", frame_idx, #frame_buffer)

    for _, frame_data in ipairs(frame_buffer) do
        -- 每帧数据前加 2 字节长度前缀
        packet = packet .. string.pack(">I2", #frame_data) .. frame_data
    end

    socket.write(fd, packet)
end

--- 客户端发送帧指令的命令处理
function CMD.send_frame(frame_data)
    -- 这里可以暴露给外部服务调用
    -- (实际在 skynet 架构中，数据的收发通过 socket 消息处理)
end

-- 暴露命令接口
skynet.start(function()
    skynet.dispatch("lua", function(session, source, cmd, ...)
        local f = CMD[cmd]
        if f then
            skynet.ret(skynet.pack(f(...)))
        end
    end)
end)

return agent
```

**KCP 参数调优指南**（帧同步场景）：

```lua
-- 帧同步 (30fps) 推荐配置
local LOCKSTEP_KCP_CONFIG = {
    nodelay = 1,       -- 必须开启: 关闭 nagle，每帧立即发包
    interval = 10,     -- KCP 内部时钟 tick: 10ms
    resend = 2,        -- 快速重传: 2 个重复 ACK 就重传 (比 TCP 的 3 更低)
    nc = 0,            -- 关闭拥塞控制! 帧同步的流量稳定可控，不需要
    sndwnd = 32,       -- 小窗口: 帧同步每帧才发一个包，不需要大窗口
    rcvwnd = 128,      -- 接收窗口可以大一些，容忍突发
    mtu = 256,         -- 小 MTU: 帧同步数据包很小 (几十字节)，小 MTU 避免组装延迟
}

-- 状态同步 (60fps) 推荐配置
local STATE_SYNC_KCP_CONFIG = {
    nodelay = 1,
    interval = 5,      -- 5ms 粒度，匹配 60fps
    resend = 2,
    nc = 1,            -- 开启拥塞控制: 状态同步的数据量波动大
    sndwnd = 256,      -- 大窗口: 状态快照可能几百字节
    rcvwnd = 256,
    mtu = 512,
}
```

**KCP 的 `output` 回调模式**（在不使用 skynet 时的手动集成）：

```lua
-- kcp_raw_example.lua
-- 直接使用 KCP C 库的 Lua 绑定 (kcp.lua)
-- 演示如何在任意框架中集成 KCP

local kcp = require "kcp"

-- 创建 KCP 实例
-- conv: 会话 ID (用于区分同一 UDP socket 上的多个会话)
-- user: 用户数据指针 (可以传入 self/this)
local kcp_obj = kcp.create(conv_id, user_data)

-- 设置参数
kcp_obj:nodelay(1, 10, 2, 1)  -- nodelay, interval, resend, nc
kcp_obj:wndsize(128, 128)      -- sndwnd, rcvwnd
kcp_obj:setmtu(512)

-- KCP 的核心模式: 你需要提供一个 output 回调
-- KCP 调用 output 来"发送"数据，你负责把数据发给底层 UDP socket
function kcp_output(buf, size, user_data)
    -- user_data 里可以存 UDP socket 的 fd
    local udp_socket = user_data
    udp_socket:send(buf, size)
end
kcp_obj:setoutput(kcp_output)

-- 主循环: 周期性调用 update (通常 10ms 一次)
function on_timer()
    local current_ms = get_time_ms()
    kcp_obj:update(current_ms)
end

-- 收到 UDP 数据时，喂给 KCP
function on_udp_recv(data, size)
    kcp_obj:input(data, size)
end

-- 从 KCP 读取可靠数据
function recv_reliable()
    local size = kcp_obj:peeksize()  -- 先看看有多少数据可读
    if size > 0 then
        local data = kcp_obj:recv(size)
        -- data 就是可靠、有序的业务数据!
        process_game_message(data)
    end
end

-- 通过 KCP 发送可靠数据
function send_reliable(data)
    kcp_obj:send(data)
end
```

---

## 3. 练习

### 练习 1: 基础 — 实现 UDP Ping-Pong

**目标**：理解 UDP 的基本 Socket 操作和丢包/乱序现象。

**要求**：
1. 用你熟悉的语言（C#/C++/Python/Lua）写一个 UDP 服务端和客户端
2. 客户端每秒发送一个带序列号的 Ping，服务端收到后回复 Pong
3. 客户端打印每次 Ping-Pong 的 RTT (Round-Trip Time)
4. 运行至少 100 次，记录 RTT 的最小值、最大值、平均值、标准差
5. **关键测试**：在本地用工具模拟丢包（如 `clumsy` on Windows, `tc qdisc` on Linux），观察丢包率 5%、10%、20% 时的行为。记录：丢包时延迟如何变化？Ping-Pong 是否有卡顿感？

**验收标准**：
- 代码可以编译/运行
- 输出 RTT 统计信息
- 能说明在高丢包率下裸 UDP 的问题

### 练习 2: 进阶 — 给你的 Ping-Pong 加上 ACK 和重传

**目标**：理解可靠 UDP 层的 ACK 机制和超时重传。

**要求**：
1. 在练习 1 的基础上，给 Ping 消息加上"要求可靠"标志
2. 服务端收到可靠 Ping 后，必须发送 ACK 确认
3. 客户端维护一个"未确认消息队列"，为每条消息设置 200ms 超时
4. 超时未收到 ACK，自动重传（最多重传 5 次，之后放弃并打印错误）
5. 实现简单的 RTT 估算（EWMA 平滑），并根据估算的 RTT 动态调整超时时间
6. **关键测试**：在 20% 丢包率下，可靠 Ping-Pong 的成功率应该 > 95%（允许个别包重传 5 次后失败）

**验收标准**：
- 超时重传正常工作
- RTT 平滑估算能适应网络变化
- 20% 丢包率下成功率 > 95%

**提示**：
```
超时时间 = 2 × SRTT + 50ms  (安全余量)
SRTT = 0.875 × SRTT + 0.125 × 本次RTT  (α = 0.125)
```

### 练习 3: 挑战 — 实现简易滑动窗口流量控制

**目标**：理解发送方流控和接收方缓冲区管理。

**要求**：
1. 在练习 2 的基础上，限制"在途中"（未确认）的数据包数量（发送窗口）
2. 接收方维护一个固定大小的"接收缓冲区"（如 64 个包），在 ACK 中告知发送方剩余空间
3. 发送窗口 = min(拥塞窗口, 接收方通告窗口)。初始拥塞窗口 = 16 个包
4. 实现 AIMD 拥塞控制：每个 RTT 确认全部在途包后，窗口 +1；检测到丢包（超时重传），窗口减半
5. 设计一个发送方"压力测试"：以高于接收方处理速度的速率发包，验证流控是否生效
6. **关键测试**：接收方故意在处理消息时 sleep(100ms)，验证发送方是否被流控限速

**验收标准**：
- 发送方不会淹没接收方（缓冲区不溢出）
- 在网络变差时（丢包率增加），发送窗口自动缩小
- 在网络恢复后，发送窗口自动增长

---

## 4. 扩展阅读

- **Gaffer On Games: UDP vs TCP** — [https://gafferongames.com/post/udp_vs_tcp/](https://gafferongames.com/post/udp_vs_tcp/) — 游戏网络编程经典文章，深入解释为什么 UDP 是实时游戏的正确选择
- **KCP 源码剖析** — [https://github.com/skywind3000/kcp](https://github.com/skywind3000/kcp) — 只有约 1000 行 C 代码，强烈建议通读
- **ENet 官方文档** — [http://enet.bespin.org/](http://enet.bespin.org/) — 完整 API 参考和设计理念
- **QUIC 协议规范** — [RFC 9000](https://www.rfc-editor.org/rfc/rfc9000) — 了解 HTTP/3 底层的传输设计，其多 Stream 和连接迁移值得学习
- **RFC 1982: Serial Number Arithmetic** — [https://www.rfc-editor.org/rfc/rfc1982](https://www.rfc-editor.org/rfc/rfc1982) — 序列号回绕比较的标准做法
- **Beej's Guide to Network Programming** — [https://beej.us/guide/bgnet/](https://beej.us/guide/bgnet/) — 学习 Socket 编程的最佳入门读物
- **clumsy** — [https://jagt.github.io/clumsy/](https://jagt.github.io/clumsy/) — Windows 下的网络模拟工具，可模拟丢包、延迟、乱序
- **Steam Networking Sockets** — [https://github.com/ValveSoftware/GameNetworkingSockets](https://github.com/ValveSoftware/GameNetworkingSockets) — Valve 开源的游戏网络库，包含 SDR 实现
- **WebRTC for Gaming** — 了解 WebRTC DataChannel 如何基于 SCTP over DTLS over ICE over UDP 构建可靠和不可靠通道

---

## 常见陷阱

### 陷阱 1: 在可靠信道上发送高频实时数据

**问题**：将玩家位置更新（60fps）放在可靠有序信道上发送，一旦丢包，所有后续位置更新都被阻塞等待重传。

**表现**：玩家移动卡顿，然后突然瞬移（一次性收到积压的位置数据）。

**解决**：高频实时数据必须用不可靠信道。如果偶尔需要保证某些关键状态到达，可以在不可靠数据中附带最近的确认状态（类似帧同步的冗余机制）。

### 陷阱 2: 序列号回绕处理不当

**问题**：使用 `uint16` 作为序列号，65535 之后回绕到 0。如果简单地用 `>` 比较序列号，回绕后会判断错误。

```cpp
// 错误! 回绕后会出错
if (newSeq > lastSeq) { /* 处理新包 */ }

// 正确: 使用 RFC 1982 序列号比较
bool is_greater(uint16_t s1, uint16_t s2) {
    return ((s1 > s2) && (s1 - s2 <= 32768)) ||
           ((s1 < s2) && (s2 - s1  > 32768));
}
```

### 陷阱 3: 重传风暴

**问题**：超时时间设置过短（如 50ms），在网络轻微抖动时触发大量不必要的重传。这些重传又增加了网络负载，导致更多丢包和更多重传——形成恶性循环。

**解决**：
- RTO 至少设置为 2 × RTT，且最小不低于 100ms
- 使用 RTT 平滑估算，RTO = SRTT + 4 × RTTVAR
- 对不可靠信道上的数据，不要使用重传

### 陷阱 4: ACK 包风暴

**问题**：每收到一个数据包就发送一个 ACK，在高速率下 ACK 流量可能占据总流量的 30%-50%。

**解决**：
- 使用 Piggyback ACK：ACK 信息附在反向数据包中
- 延迟 ACK：等到有数据要发送或超过一定时间（如 10ms）后再发 ACK
- 使用累积 ACK（TCP 的方式）：一个 ACK 确认所有之前的包

### 陷阱 5: NAT 穿透的"双方同时发包"依赖

**问题**：假设双方同时发包就能打穿 NAT，但忽略了 TTL（生存时间）、防火墙规则、运营商级 NAT（CGNAT）等因素。移动网络（4G/5G）几乎总是对称型 NAT。

**解决**：
- 务必部署 TURN 服务器作为兜底
- 使用成熟的 ICE 库，而非自己实现穿透逻辑
- 做好 TURN 中继的成本估算和容量规划

### 陷阱 6: 忽略 RTT 的抖动 (Jitter)

**问题**：只在建立连接时测量一次 RTT，然后固定使用这个值。实际上 RTT 在游戏过程中会剧烈波动（Wi-Fi 干扰、移动信号切换），固定 RTO 会在高延迟时过早超时。

**解决**：持续测量 RTT，使用 EWMA 平滑，并根据 RTT 的变化幅度（RTTVAR）动态调整 RTO。

### 陷阱 7: KCP 的 `nc=0` 误用

**问题**：KCP 关闭拥塞控制（`nc=0`）后，即使在真实拥塞情况下也不会降速，导致大量数据积压在网络中间节点，最终被丢弃。

**解决**：
- 仅在**数据量稳定且可预测**的场景下关闭拥塞控制（如帧同步，每帧数据量几乎不变）
- 对于状态同步或可变数据量的场景，保持拥塞控制开启
- 关闭拥塞控制时，需要在上层自己做发送速率限制

### 陷阱 8: 在没有时序保证的情况下使用可靠无序信道

**问题**：设定了"可靠但无序"的信道用于发送 RPC，但不处理乱序。例如：先发 `Fire()` 再发 `StopFire()`，如果 `StopFire()` 先到，玩家会看到一个瞬间的枪火然后消失。

**解决**：
- RPC 调用通常需要有序保证
- 如果使用无序信道，每个 RPC 必须携带"因果关系"标识（如 Lamport 时钟或依赖的 RPC ID）
- 大多数情况下，RPC 使用可靠有序信道是最简单的选择
