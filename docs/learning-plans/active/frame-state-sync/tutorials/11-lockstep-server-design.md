# 帧同步服务端设计：帧对齐与乐观帧锁定

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [07-帧同步协议设计：帧指令、冗余发包、丢包处理](07-lockstep-protocol-design.md)

---

## 1. 概念讲解

### 1.1 帧同步服务端的核心职责

在 Server-Relayed Lockstep（服务器中转）模型中，服务端不是"玩游戏的机器"——服务端**不执行游戏逻辑**，它只是一个**高精度、低延迟的广播交换机**。

```
┌──────────────────────────────────────────────────────────────────┐
│                        帧同步服务端                                │
│                                                                   │
│  ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌───────────────┐   │
│  │ 输入收集 │   │ 帧对齐  │   │ 输入广播  │   │  断线/重连处理  │   │
│  │ Input   │──►│ Frame   │──►│ Broadcast│   │  Disconnect   │   │
│  │ Collector│   │ Aligner │   │          │   │  /Reconnect   │   │
│  └─────────┘   └─────────┘   └──────────┘   └───────────────┘   │
│        │              │              │                │           │
│        ▼              ▼              ▼                ▼           │
│  接收玩家输入     决定何时广播    组装帧包发送     玩家超时/重连    │
│  (UDP收包线程)   (定时器驱动)   (组播/单播)      帧追赶加速       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

服务端的四条核心职责：

**① 输入收集 (Input Collection)**
服务端通过 UDP socket 接收所有客户端的输入消息。每个消息携带 `{playerId, frameNumber, inputData}`。服务端不做逻辑判断，只管收集到内存缓冲区。

与状态同步的区别：状态同步服务器要跑物理引擎、AI、技能系统。帧同步服务器不需要任何游戏逻辑——它甚至不需要知道"攻击"是什么意思。

**② 帧对齐 (Frame Alignment)**
这是帧同步服务端存在的根本原因。服务端在每个逻辑帧周期（如 66ms）结束时，决定："此刻，第 N 帧要广播什么输入集合？"

两种对齐策略：
- **严格对齐 (Strict)**：等待所有玩家的输入到齐后才广播。公平，但任意一个慢玩家会让全体卡顿。
- **乐观对齐 (Optimistic)**：定时器一到就广播——已经收到的输入打包发出，未收到的填充空操作。流畅，但慢玩家吃亏。

**③ 输入广播 (Input Broadcast)**
服务端将当前帧的输入集合组装成帧包，广播给所有客户端。广播包的结构通常包含冗余历史帧，这是帧同步对抗丢包的核心手段（详见教程 07）。

**④ 断线/重连处理 (Disconnect & Reconnect)**
玩家掉线时：
- 短时掉线（< 5s）：服务端持续用空操作填充该玩家，不中断对局。
- 长时掉线（> 30s）：标记玩家离线，可选触发 AI 托管或终止对局。
- 重连：新客户端连接后，服务端将缓存的历史帧打包发送，客户端快进追赶（Frame Catchup）。

### 1.2 严格帧对齐 (Strict Frame Alignment)

严格对齐是帧同步服务端最"教科书"的实现方式。它的规则只有一条：

> 直到所有玩家的当前帧输入都到齐了，才广播这一帧。

```
时间轴（严格对齐，3 个玩家）:

Player A (低延迟):   输入到达 ▼              输入到达 ▼
                     ════════╗               ════════╗
                             ║                       ║
Player B (低延迟):   输入到达 ▼              输入到达 ▼
                     ════════╣               ════════╣
                             ║                       ║
Player C (高延迟):   .......输入到达...▼     .......输入到达...▼
                     ═══════════════╣       ═══════════════════╣
                                   ║                         ║
服务端广播:                       [广播帧N]                  [广播帧N+1]
                                   ▲                         ▲
                                   │                         │
                          所有人在等C，          所有人又在等C，
                          包括A和B！              游戏卡顿明显
```

**严格对齐的致命缺陷**：一个 200ms 延迟的玩家，会把全体玩家的帧间隔拖到 200ms。如果逻辑帧率目标是 15fps（66ms/帧），实际帧率会降到 5fps。

**但严格对齐有不可替代的优势**：绝对公平。每个玩家的每一帧操作都精确地在那一帧生效，不存在"你的这次攻击被我丢了"的问题。这在对公平性要求极高的场景（电竞比赛、格斗游戏）中是硬性要求。

**代表游戏**：星际争霸 2 的合作模式服务器、格斗游戏的匹配对战（GGPO 回滚网络之前的传统方案）。

### 1.3 乐观帧锁定 (Optimistic Lockstep)

乐观帧锁定的核心思想只有一句话：

> 服务器按固定频率广播帧。到时间了，有多少输入算多少。没到的——填充空操作。

```
时间轴（乐观锁定，3 个玩家，30fps 逻辑帧率）:

服务端定时器:         ║                       ║
              ┌───────╨───────┐       ┌───────╨───────┐
              │ 广播时刻到达！ │       │ 广播时刻到达！ │
              │ 立即打包广播   │       │ 立即打包广播   │
              └───────┬───────┘       └───────┬───────┘
                      ║                       ║
Player A (正常):  输入▼ 收到广播           输入▼ 收到广播
                      ║                       ║
Player B (正常):  输入▼ 收到广播           输入▼ 收到广播
                      ║                       ║
Player C (延迟):  输入还在路上...          输入还在路上...
                  ┌─用空操作填充─┐        ┌─用空操作填充─┐
                  │ C这帧操作丢失 │        │ C这帧操作丢失 │
                  └─────────────┘        └─────────────┘
                      ║                       ║
                  全体广播[帧N+空C]        全体广播[帧N+1+空C]
                  A和B流畅运行！          A和B流畅运行！
```

**乐观锁定的关键参数**：

| 参数 | 典型值 | 含义 |
|------|--------|------|
| 逻辑帧率 | 15 Hz (66ms) | 每秒执行多少个逻辑帧 |
| 发送间隔 (SendInterval) | 33ms (双倍速率) | 服务器实际发包的频率 |
| 帧缓冲区大小 (BufferFrames) | 4~6 帧 | 客户端提前发送未来N帧的输入 |
| 超时判定 | 2~3 个发送间隔 | 多长时间没收到输入视为超时 |
| 丢包容忍 | 连续 3 帧空操作后触发 | 降级策略触发线 |

**发送间隔为什么是 33ms 而非 66ms？**

王者荣耀的 15Hz 逻辑帧率，理论广播间隔是 66ms。但实际服务端以 33ms 间隔发送——**每个逻辑帧的输入包会发送两次**（上一次是冗余重复）。这不是浪费带宽，而是对抗丢包的核心策略：

```
帧N的完整输入集合:
  ↓
T=0ms:  服务器广播帧N (首次 ── 可能丢包)
T=33ms: 服务器广播帧N (冗余 ── 增加了UDP到达概率)
T=66ms: 服务器广播帧N+1 (首次)
T=99ms: 服务器广播帧N+1 (冗余)
```

客户端收到任何一次广播就能拿到帧 N 的数据。即使第一次广播丢了，33ms 后的冗余包大概率能到。这就是"双倍速率冗余广播"——同时也是帧同步 UDP 层设计的核心（详见教程 02 和 07）。

### 1.4 严格 vs 乐观：一张对比表

| 维度 | 严格帧对齐 | 乐观帧锁定 |
|------|-----------|-----------|
| **公平性** | ★★★★★ 每帧所有玩家操作精确生效 | ★★★☆☆ 高延迟玩家可能丢操作 |
| **流畅度** | ★★☆☆☆ 最慢玩家拖累所有人 | ★★★★★ 快玩家不受影响 |
| **延迟感受** | 以最差网络为准 | 各玩家感受各自网络 |
| **带宽** | 恰好每帧一个包 | 冗余广播，带宽×2（可接受） |
| **复杂度** | 低（等待+广播） | 中（定时器+超时+空操作+追赶） |
| **断线处理** | 需要主动中断等待 | 自动降级（空操作填充） |
| **适用场景** | 格斗游戏、局域网对战、小人数对战 | 移动 MOBA、大逃杀、弱网环境 |

> **面试要点**：面试官问"帧同步为什么有延迟？"，不要只回答"网络延迟"。要深入区分两种延迟——严格对齐的"等慢玩家延迟"和乐观锁定的"网络本身延迟"。前者的解法是乐观锁定，后者的解法是帧缓冲区 + 冗余广播。

### 1.5 帧缓冲区 (Frame Buffer)：输入与广播的时间差

乐观锁定中，客户端和服务端之间存在一个关键的时间缓冲：

```
客户端时间轴 ──────────────────────────────────────────────────────►

         [客户端渲染帧N-2] [渲染帧N-1] [渲染帧N] [渲染帧N+1]
                │              │            │          │
                │     收集操作阶段(Bucket)    │    操作发送▼
                │              │            │    ┌──────────────┐
                │              │            │    │ 发送Input{   │
                │              │            │    │  frame: N+3  │ ← 关键！发送的是
                │              │            │    │  data: ...   │   未来帧的输入
                │              │            │    └──────────────┘
                ▼              ▼            ▼
服务端时间轴 ──────────────────────────────────────────────────────►
                                                           │
                                    服务端收到Input{frame: N+3}
                                    存储在帧缓冲槽位[N+3]中
                                                           │
                                    等待...等待...等到 T=N+3 广播时刻
                                                           │
                                                           ▼
                                                    广播帧N+3（含此输入）
```

**为什么客户端要发送"未来帧"的输入？**

假设没有缓冲区，客户端在帧 N 时刻发送帧 N 的输入：
- 客户端 → 服务器：10~50ms 网络延迟
- 服务器处理 + 排队：5~10ms
- 服务器 → 客户端广播：10~50ms
- 总计 RTT：50~110ms

等到客户端收到"帧 N 的广播"时，已经过去了好几帧的时间。客户端无法即时执行——它在逻辑上已经是帧 N+2 或 N+3 了。

**解决方案：客户端"预发送"未来 4~6 帧的输入。**

```
客户端在渲染帧 N 时，发送 Input{frame: N+BUFFER_SIZE}。
服务器在 T=N+BUFFER_SIZE 时广播帧 N+BUFFER_SIZE，
此时该输入刚好在广播时刻前到达。
```

`BUFFER_SIZE` 的取值取决于网络 RTT：
- 局域网（RTT < 5ms）：BUFFER_SIZE = 1~2
- 4G/5G（RTT 30~80ms）：BUFFER_SIZE = 4~6
- 弱网（RTT > 150ms）：BUFFER_SIZE = 8~10（但体验已经不好了）

**缓冲区不是越大越好**：
- 太大 → 客户端的操作需要等很久才生效（操作延迟 = BUFFER_SIZE × 帧间隔）
- 太小 → 输入经常赶不上广播时刻 → 频繁填充空操作 → 操作丢失

王者荣耀 BUFFER_SIZE 通常为 4，对应约 264ms（4 × 66ms）的操作延迟。这个数字看起来高，但配合客户端的**预表现（Prediction）**——玩家按下攻击键时立刻播放攻击动画——玩家感知的延迟远小于此。

---

## 2. 代码示例

### 2.1 C#: FrameServer 完整实现

以下代码是一个生产级帧同步服务端的核心骨架。它使用 UDP Socket，支持乐观帧锁定、输入缓冲窗口、多客户端管理、冗余广播和帧追赶。

```csharp
// FrameServer.cs — 乐观帧锁定服务端完整实现
// 编译: dotnet new console; 替换 Program.cs 为本文件
// 依赖: 无外部依赖，仅 .NET 8.0+ 标准库

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;

namespace LockstepServer;

#region 数据结构定义

/// <summary>
/// 单个玩家的单帧输入。对应客户端发来的输入消息。
/// 字段顺序对齐网络包的序列化布局，避免任何填充字节。
/// </summary>
public struct PlayerInput
{
    public uint FrameNumber;   // 目标逻辑帧号（客户端预发送的未来帧）
    public byte PlayerId;      // 玩家 ID (1~MaxPlayers)
    public ushort InputFlags;  // 按键位掩码（bit0=移动, bit1=攻击, bit2=技能1...）
    public short AxisX;        // 摇杆X轴 (Q8.8 定点数, 范围[-32768,32767]→[-128.0,127.99])
    public short AxisY;        // 摇杆Y轴 (同上)

    public const int SerializedSize = 11; // 4+1+2+2+2 bytes

    /// <summary>
    /// 空输入：表示玩家在本帧没有任何操作。
    /// 帧同步要求空输入也是明确定义的，不能"未收到=未定义"。
    /// </summary>
    public static PlayerInput Empty(uint frame, byte playerId)
    {
        return new PlayerInput
        {
            FrameNumber = frame,
            PlayerId = playerId,
            InputFlags = 0,
            AxisX = 0,
            AxisY = 0
        };
    }

    /// <summary>
    /// 反序列化：从网络字节数组还原 PlayerInput。
    /// 网络字节序为大端，需转换为主机字节序。
    /// </summary>
    public static PlayerInput Deserialize(ReadOnlySpan<byte> data)
    {
        if (data.Length < SerializedSize)
            throw new ArgumentException($"数据过短: {data.Length} < {SerializedSize}");

        return new PlayerInput
        {
            // 帧同步协议通常使用大端序（与底层 C++ 服务端对齐）
            FrameNumber = (uint)IPAddress.NetworkToHostOrder(BitConverter.ToInt32(data[0..4])),
            PlayerId = data[4],
            InputFlags = (ushort)IPAddress.NetworkToHostOrder(BitConverter.ToInt16(data[5..7])),
            AxisX = IPAddress.NetworkToHostOrder(BitConverter.ToInt16(data[7..9])),
            AxisY = IPAddress.NetworkToHostOrder(BitConverter.ToInt16(data[9..11]))
        };
    }
}

/// <summary>
/// 一个逻辑帧的完整输入集合：包含所有玩家在该帧的输入。
/// 这是服务端广播给客户端的最小数据单元。
/// </summary>
public struct FramePackage
{
    public uint FrameNumber;
    public ushort PlayerCount;
    public PlayerInput[] Inputs; // 按 PlayerId 升序排列（保证确定性）

    /// <summary>
    /// 序列化为网络字节数组。
    /// 格式: [FrameNumber:4][PlayerCount:2][Inputs...]
    /// </summary>
    public byte[] Serialize()
    {
        int totalSize = 6 + Inputs.Length * PlayerInput.SerializedSize;
        byte[] buffer = new byte[totalSize];
        int offset = 0;

        // FrameNumber (大端)
        WriteUInt32BE(buffer, ref offset, FrameNumber);
        // PlayerCount (大端)
        WriteUInt16BE(buffer, ref offset, PlayerCount);

        foreach (var input in Inputs)
        {
            WriteUInt32BE(buffer, ref offset, input.FrameNumber);
            buffer[offset++] = input.PlayerId;
            WriteUInt16BE(buffer, ref offset, input.InputFlags);
            WriteInt16BE(buffer, ref offset, input.AxisX);
            WriteInt16BE(buffer, ref offset, input.AxisY);
        }

        return buffer;
    }

    // 大端写入辅助方法（避免分配临时数组）
    private static void WriteUInt32BE(byte[] buf, ref int offset, uint val)
    {
        buf[offset + 0] = (byte)(val >> 24);
        buf[offset + 1] = (byte)(val >> 16);
        buf[offset + 2] = (byte)(val >> 8);
        buf[offset + 3] = (byte)val;
        offset += 4;
    }

    private static void WriteUInt16BE(byte[] buf, ref int offset, ushort val)
    {
        buf[offset + 0] = (byte)(val >> 8);
        buf[offset + 1] = (byte)val;
        offset += 2;
    }

    private static void WriteInt16BE(byte[] buf, ref int offset, short val)
    {
        buf[offset + 0] = (byte)(val >> 8);
        buf[offset + 1] = (byte)val;
        offset += 2;
    }
}

#endregion

#region 多客户端管理

/// <summary>
/// 服务端维护的单个客户端状态。
/// </summary>
public class ClientState
{
    public byte PlayerId;
    public IPEndPoint EndPoint;
    public long LastInputTime;       // 最后一次收到输入的时间戳 (Stopwatch tick)
    public uint LastInputFrame;      // 最后一次收到的输入帧号
    public bool IsConnected;
    public int ConsecutiveEmptyFrames; // 连续空操作帧计数（用于超时判定）

    // 每客户端独立的输入缓冲窗口：sliding window [currentFrame, currentFrame + BUFFER_SIZE)
    // Key=帧号, Value=该帧的输入（可能为 null 表示还未收到）
    public readonly SortedDictionary<uint, PlayerInput?> InputBuffer = new();
}

#endregion

#region FrameServer 主类

/// <summary>
/// 帧同步服务端主类。负责 UDP 收发包、帧定时广播、客户端生命周期管理。
/// 设计要点：
/// 1. 收包和发包使用独立线程，避免相互阻塞
/// 2. 帧广播由高精度定时器驱动，不依赖系统时钟的绝对精度
/// 3. 所有共享状态通过锁保护，但锁粒度精细（每客户端独立锁）
/// </summary>
public class FrameServer : IDisposable
{
    // ── 配置参数 ──
    private readonly int _maxPlayers;           // 最大玩家数
    private readonly int _targetFps;            // 目标逻辑帧率 (如 15)
    private readonly int _sendIntervalMs;       // 发送间隔 ms (如 33ms 双倍速率)
    private readonly int _bufferFrames;         // 帧缓冲区大小 (客户端预发送N帧)
    private readonly int _maxHistoryFrames;     // 历史帧缓存数量 (用于重连追赶)
    private readonly int _disconnectTimeoutMs;  // 掉线判定超时 ms

    // ── 网络 ──
    private readonly UdpClient _udp;
    private readonly CancellationTokenSource _cts = new();
    private Task? _recvTask;
    private Task? _tickTask;

    // ── 帧状态 ──
    private uint _currentFrame;                 // 服务端当前逻辑帧号 (单调递增)
    private long _lastTickTime;                 // 上一次 Tick 的 Stopwatch 时间戳
    private readonly object _frameLock = new(); // 保护帧状态的锁

    // ── 客户端管理 ──
    // ConcurrentDictionary: 线程安全的玩家字典。收包线程写入，Tick 线程读取。
    private readonly ConcurrentDictionary<byte, ClientState> _clients = new();

    // ── 帧历史缓存 ──
    // 环形缓冲区：存储最近 maxHistoryFrames 帧的 FramePackage，用于断线重连追赶
    private readonly FramePackage?[] _frameHistory;
    private long _frameHistoryWriteIndex;

    // ── 性能计数 ──
    private long _totalFramesBroadcast;
    private long _totalInputsReceived;
    private long _totalEmptyFills;

    /// <param name="port">UDP 监听端口</param>
    /// <param name="maxPlayers">最大玩家数</param>
    /// <param name="targetFps">逻辑帧率</param>
    /// <param name="bufferFrames">帧缓冲区大小</param>
    public FrameServer(int port, int maxPlayers = 10, int targetFps = 15, int bufferFrames = 4)
    {
        _maxPlayers = maxPlayers;
        _targetFps = targetFps;
        _bufferFrames = bufferFrames;

        // 发送间隔 = 1000ms / (targetFps * 2)  双倍速率冗余广播
        _sendIntervalMs = 1000 / (targetFps * 2);

        // 历史帧缓存 = 30 秒的帧数 (用于重连追赶)
        _maxHistoryFrames = targetFps * 30;
        _frameHistory = new FramePackage?[_maxHistoryFrames];

        // 掉线超时 = 5 秒（大约 75 个帧周期 @ 15fps）
        _disconnectTimeoutMs = 5000;

        _udp = new UdpClient(port);
        // 增大 socket 缓冲区以减少丢包
        _udp.Client.SendBufferSize = 256 * 1024;
        _udp.Client.ReceiveBufferSize = 256 * 1024;

        Console.WriteLine($"[FrameServer] 启动: port={port}, fps={targetFps}, " +
                          $"sendInterval={_sendIntervalMs}ms, buffer={bufferFrames}帧");
    }

    /// <summary>
    /// 启动服务端：同时启动收包线程和 Tick 线程。
    /// </summary>
    public void Start()
    {
        _lastTickTime = Stopwatch.GetTimestamp();
        _recvTask = Task.Run(() => ReceiveLoop(_cts.Token));
        _tickTask = Task.Run(() => TickLoop(_cts.Token));
        Console.WriteLine("[FrameServer] 已启动，等待客户端连接...");
    }

    #endregion

    #region 收包循环

    /// <summary>
    /// 收包循环：在独立线程中运行，持续接收 UDP 包。
    /// 解析出来的 PlayerInput 存入对应客户端的输入缓冲区。
    /// </summary>
    private async Task ReceiveLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                // UdpClient.ReceiveAsync 在有数据到达时立即返回
                var result = await _udp.ReceiveAsync(ct);
                ProcessReceivedPacket(result.Buffer, result.RemoteEndPoint);
            }
            catch (OperationCanceledException)
            {
                break; // 正常关闭
            }
        }
    }

    /// <summary>
    /// 处理收到的 UDP 包。支持两种包类型：
    /// - 输入包 (第一个字节=0x01): PlayerInput
    /// - 连接请求 (第一个字节=0x02): 玩家加入
    /// </summary>
    private void ProcessReceivedPacket(byte[] data, IPEndPoint sender)
    {
        if (data.Length < 2) return;

        byte packetType = data[0];

        switch (packetType)
        {
            case 0x01: // 输入包
                ProcessInputPacket(data.AsSpan(1), sender);
                break;

            case 0x02: // 连接请求
                ProcessJoinRequest(sender);
                break;

            case 0x03: // 重连请求
                ProcessReconnectRequest(data.AsSpan(1), sender);
                break;

            default:
                Console.WriteLine($"[警告] 未知包类型 0x{packetType:X2} 来自 {sender}");
                break;
        }
    }

    /// <summary>
    /// 处理玩家输入包。将输入存入对应帧号的缓冲区槽位。
    ///
    /// 核心设计：每玩家独立的滑动输入窗口。
    /// 客户端预发送未来 BUFFER_SIZE 帧的输入，服务端将它们放入对应槽位。
    /// Tick 线程在广播时刻从这些槽位中取用。
    /// </summary>
    private void ProcessInputPacket(ReadOnlySpan<byte> data, IPEndPoint sender)
    {
        try
        {
            var input = PlayerInput.Deserialize(data);
            Interlocked.Increment(ref _totalInputsReceived);

            if (!_clients.TryGetValue(input.PlayerId, out var client))
            {
                // 未注册的客户端发来的输入——可能是延迟的旧连接包
                return;
            }

            // 更新客户端活跃时间（用于超时判定）
            client.LastInputTime = Stopwatch.GetTimestamp();
            client.LastInputFrame = Math.Max(client.LastInputFrame, input.FrameNumber);
            client.ConsecutiveEmptyFrames = 0; // 收到真实输入，重置空帧计数

            // 存入输入缓冲窗口
            lock (client.InputBuffer)
            {
                // 清理过期的旧帧输入（早于当前帧-1的已不需要）
                CleanExpiredInputs(client, _currentFrame);

                // 存入：如果客户端重复发送同一帧的输入（冗余发送），保留最新的
                client.InputBuffer[input.FrameNumber] = input;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[错误] 解析输入包失败: {ex.Message}");
        }
    }

    /// <summary>
    /// 清理客户端输入缓冲区中已过期的帧数据。
    /// 过期定义：帧号 < currentFrame（这些帧已经广播过，不再需要）。
    /// </summary>
    private static void CleanExpiredInputs(ClientState client, uint currentFrame)
    {
        var expired = new List<uint>();
        foreach (var kv in client.InputBuffer)
        {
            if (kv.Key < currentFrame)
                expired.Add(kv.Key);
        }
        foreach (var frame in expired)
            client.InputBuffer.Remove(frame);
    }

    #endregion

    #region 连接管理

    /// <summary>
    /// 分配新玩家 ID（简单的线性分配）。
    /// 生产环境应使用对象池管理 ID 复用。
    /// </summary>
    private byte? AllocatePlayerId()
    {
        for (byte i = 1; i <= _maxPlayers; i++)
        {
            if (!_clients.ContainsKey(i))
                return i;
        }
        return null; // 房间已满
    }

    private void ProcessJoinRequest(IPEndPoint sender)
    {
        if (_clients.Count >= _maxPlayers)
        {
            Console.WriteLine($"[连接] 拒绝 {sender}: 房间已满");
            // 发送拒绝包 (实际项目应回复明确的拒绝码)
            return;
        }

        // 检查是否已有相同 IPEndPoint 的客户端（防止重复连接）
        foreach (var kv in _clients)
        {
            if (kv.Value.EndPoint.Equals(sender))
            {
                Console.WriteLine($"[连接] 忽略 {sender}: 已连接的玩家 PlayerId={kv.Key}");
                return;
            }
        }

        var playerId = AllocatePlayerId();
        if (playerId == null) return;

        var client = new ClientState
        {
            PlayerId = playerId.Value,
            EndPoint = sender,
            LastInputTime = Stopwatch.GetTimestamp(),
            IsConnected = true
        };

        if (_clients.TryAdd(playerId.Value, client))
        {
            Console.WriteLine($"[连接] 玩家 {playerId} 加入, 来自 {sender}, " +
                              $"当前人数: {_clients.Count}/{_maxPlayers}");

            // 发送连接确认包：告知客户端其 PlayerId 和当前帧号
            SendConnectAck(client);
        }
    }

    /// <summary>
    /// 发送连接确认包。
    /// 格式: [0x02][PlayerId:1][CurrentFrame:4][MaxPlayers:1][TargetFps:1][BufferFrames:1]
    /// </summary>
    private async void SendConnectAck(ClientState client)
    {
        byte[] ack = new byte[9];
        ack[0] = 0x02; // 包类型
        ack[1] = client.PlayerId;
        uint currentFrame;
        lock (_frameLock) { currentFrame = _currentFrame; }
        // CurrentFrame (大端)
        ack[2] = (byte)(currentFrame >> 24);
        ack[3] = (byte)(currentFrame >> 16);
        ack[4] = (byte)(currentFrame >> 8);
        ack[5] = (byte)currentFrame;
        ack[6] = (byte)_maxPlayers;
        ack[7] = (byte)_targetFps;
        ack[8] = (byte)_bufferFrames;

        await _udp.SendAsync(ack, ack.Length, client.EndPoint);
    }

    #endregion

    #region Tick 循环（帧对齐 + 广播）

    /// <summary>
    /// Tick 循环：服务端的核心定时器。
    /// 按 sendIntervalMs 间隔触发，每个 Tick 执行一次帧组装 + 广播。
    ///
    /// 与 System.Timers.Timer 不同，这里使用手动 spin-wait 循环，
    /// 因为：
    /// 1. 需要精确控制帧号递增，不能有累积误差
    /// 2. GC 导致的 timer 延迟在帧同步场景下不可接受
    /// 3. 可以精确测量每次 Tick 的实际执行时间（用于性能监控）
    /// </summary>
    private async Task TickLoop(CancellationToken ct)
    {
        long tickFrequency = Stopwatch.Frequency;
        long tickIntervalTicks = tickFrequency * _sendIntervalMs / 1000;

        while (!ct.IsCancellationRequested)
        {
            long now = Stopwatch.GetTimestamp();
            long elapsed = now - _lastTickTime;

            if (elapsed >= tickIntervalTicks)
            {
                // 更新 lastTickTime 为"理论上应该触发的时间"，而非当前时间
                // 这样可以防止因某一次 Tick 执行慢而导致的帧率漂移
                _lastTickTime += tickIntervalTicks;

                // 如果已经落后很多（比如 GC 暂停后），做追赶处理
                if (_lastTickTime < now - tickIntervalTicks * 3)
                {
                    Console.WriteLine($"[警告] Tick 严重滞后，重置时钟");
                    _lastTickTime = now;
                }

                DoTick();
            }

            // 精确等待到下一个 Tick 时间（比 Thread.Sleep 更精确）
            long nextTickTime = _lastTickTime + tickIntervalTicks;
            long waitMs = (nextTickTime - Stopwatch.GetTimestamp()) * 1000 / tickFrequency;

            if (waitMs > 1)
            {
                // 等待大部分时间
                await Task.Delay((int)waitMs - 1, ct);
                // 剩余 1ms 用 spin-wait 精确对齐
                while (Stopwatch.GetTimestamp() < nextTickTime)
                {
                    Thread.SpinWait(10);
                }
            }
        }
    }

    /// <summary>
    /// 执行单次帧 Tick：收集输入 → 组装帧包 → 广播
    ///
    /// 关键决策点：乐观帧锁定的核心逻辑在这里——每个 Tick 产生一个新帧号，
    /// 但只有每两次 Tick 才对应一个新逻辑帧（因为双倍速率冗余广播）。
    /// </summary>
    private void DoTick()
    {
        // 每隔两次 Tick 推进一次逻辑帧号
        // Tick1 → 冗余广播上一帧 (frameNumber 不变)
        // Tick2 → 广播新帧 (frameNumber++)
        bool isNewFrame = false;
        uint broadcastFrame;
        lock (_frameLock)
        {
            // 简单策略：每两次 Tick 递增一次帧号
            // 实际实现可用一个计数器交替
            if ((_currentFrame + _totalFramesBroadcast) % 2 == 0)
            {
                _currentFrame++;
                isNewFrame = true;
            }
            broadcastFrame = _currentFrame;
        }

        // 组装帧包：收集所有玩家在 broadcastFrame 的输入
        var frameInputs = new PlayerInput[_maxPlayers];
        int playerIdx = 0;
        int emptyFillCount = 0;

        foreach (var kv in _clients)
        {
            var client = kv.Value;
            if (!client.IsConnected) continue;

            PlayerInput input;
            lock (client.InputBuffer)
            {
                if (client.InputBuffer.TryGetValue(broadcastFrame, out var storedInput) &&
                    storedInput.HasValue)
                {
                    input = storedInput.Value;
                    // 取用后移除，释放内存
                    client.InputBuffer.Remove(broadcastFrame);
                }
                else
                {
                    // 乐观锁定：输入未到，填充空操作
                    input = PlayerInput.Empty(broadcastFrame, client.PlayerId);
                    emptyFillCount++;
                    client.ConsecutiveEmptyFrames++;
                }
            }

            frameInputs[playerIdx++] = input;
        }

        // 按 PlayerId 排序输入（保证所有客户端收到相同的输入顺序）
        Array.Sort(frameInputs, 0, playerIdx,
            Comparer<PlayerInput>.Create((a, b) => a.PlayerId.CompareTo(b.PlayerId)));

        // 组装帧包
        var package = new FramePackage
        {
            FrameNumber = broadcastFrame,
            PlayerCount = (ushort)playerIdx,
            Inputs = frameInputs[0..playerIdx] // 截取实际玩家数
        };

        // 序列化并广播
        byte[] serialized = package.Serialize();
        BroadcastFrame(serialized, broadcastFrame);

        // 缓存历史帧（用于重连追赶）
        StoreFrameHistory(package);

        Interlocked.Increment(ref _totalFramesBroadcast);
        Interlocked.Add(ref _totalEmptyFills, emptyFillCount);

        // 周期性能输出（每 100 帧）
        if (broadcastFrame % 100 == 0)
        {
            PrintStats();
        }
    }

    #endregion

    #region 广播与重连

    /// <summary>
    /// 广播帧包到所有已连接的客户端。
    /// 使用 UDP 单播循环而非组播——移动网络环境下组播支持差。
    ///
    /// 性能注意：批量 send 比逐个 send 效率高，
    /// 但 UDP 无连接特性使得逐个 send 的延迟更可控。
    /// </summary>
    private void BroadcastFrame(byte[] data, uint frameNumber)
    {
        var disconnectedClients = new List<byte>();

        foreach (var kv in _clients)
        {
            var client = kv.Value;
            if (!client.IsConnected) continue;

            // 掉线检测
            long elapsedMs = (Stopwatch.GetTimestamp() - client.LastInputTime) * 1000 /
                             Stopwatch.Frequency;

            if (elapsedMs > _disconnectTimeoutMs)
            {
                Console.WriteLine($"[掉线] 玩家 {client.PlayerId} 超时 {elapsedMs}ms，" +
                                  $"连续空帧: {client.ConsecutiveEmptyFrames}");
                client.IsConnected = false;
                disconnectedClients.Add(client.PlayerId);
                continue;
            }

            // 如果客户端已标记为断线但还未被移除，跳过广播
            if (client.ConsecutiveEmptyFrames > _targetFps * 15) // 15 秒无输入
            {
                continue;
            }

            try
            {
                // 异步发送，不等待结果（UDP 无连接，发送即完成）
                _ = _udp.SendAsync(data, data.Length, client.EndPoint);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[发送失败] 玩家 {client.PlayerId}: {ex.Message}");
            }
        }

        // 清理长时间断线的客户端
        foreach (var pid in disconnectedClients)
        {
            _clients.TryRemove(pid, out _);
        }
    }

    /// <summary>
    /// 处理重连请求。客户端断线后重连，需要追赶历史帧。
    /// </summary>
    private async void ProcessReconnectRequest(ReadOnlySpan<byte> data, IPEndPoint sender)
    {
        if (data.Length < 1) return;
        byte playerId = data[0];

        if (!_clients.TryGetValue(playerId, out var client))
        {
            // 可能是新客户端（断线后重新连接时 EndPoint 可能变了）
            Console.WriteLine($"[重连] 玩家 {playerId} 请求重连，但不在活动列表中");
            return;
        }

        // 更新连接信息
        client.EndPoint = sender;
        client.IsConnected = true;
        client.ConsecutiveEmptyFrames = 0;
        client.LastInputTime = Stopwatch.GetTimestamp();

        Console.WriteLine($"[重连] 玩家 {playerId} 重连成功, 来自 {sender}");

        // 发送连接确认 + 当前帧号
        SendConnectAck(client);

        // 发送历史帧包（追赶帧）
        await SendCatchupFrames(client);
    }

    /// <summary>
    /// 发送追赶帧：将缓存的历史帧打包发送给重连客户端。
    ///
    /// 追赶策略：
    /// - 默认 3 倍速发送历史帧（每 11ms 发一帧 vs 正常 33ms）
    /// - 客户端收到后快速执行，追赶至当前帧
    /// - 追赶完成后切换到正常帧率
    /// </summary>
    private async Task SendCatchupFrames(ClientState client)
    {
        uint currentFrame;
        lock (_frameLock) { currentFrame = _currentFrame; }

        const int CATCHUP_INTERVAL_MS = 11; // 3 倍速
        int sent = 0;

        for (long i = 0; i < _maxHistoryFrames && sent < _maxHistoryFrames; i++)
        {
            // 从环形缓冲区读取历史帧
            long readIndex = (_frameHistoryWriteIndex - _maxHistoryFrames + i) % _maxHistoryFrames;
            if (readIndex < 0) readIndex += _maxHistoryFrames;

            var pkg = _frameHistory[readIndex];
            if (pkg == null) continue;

            // 只发送重连客户端尚未消费的帧
            if (pkg.Value.FrameNumber <= client.LastInputFrame) continue;
            if (pkg.Value.FrameNumber >= currentFrame) break;

            byte[] data = pkg.Value.Serialize();
            await _udp.SendAsync(data, data.Length, client.EndPoint);
            sent++;

            // 频率控制
            await Task.Delay(CATCHUP_INTERVAL_MS);
        }

        Console.WriteLine($"[重连] 追赶完成: 发送了 {sent} 帧给玩家 {client.PlayerId}");
    }

    #endregion

    #region 帧历史缓存

    /// <summary>
    /// 将已广播的帧包存入环形历史缓冲区。
    /// 环形缓冲区 = 固定大小数组 + 取模索引，O(1) 写入，无内存分配。
    /// </summary>
    private void StoreFrameHistory(FramePackage package)
    {
        long index = Interlocked.Increment(ref _frameHistoryWriteIndex) - 1;
        _frameHistory[index % _maxHistoryFrames] = package;
    }

    #endregion

    #region 性能统计

    private long _lastStatsTime;

    private void PrintStats()
    {
        long now = Stopwatch.GetTimestamp();
        if (_lastStatsTime == 0) { _lastStatsTime = now; return; }

        double elapsedSec = (double)(now - _lastStatsTime) / Stopwatch.Frequency;
        _lastStatsTime = now;

        Console.WriteLine(
            $"[统计] 帧:{_currentFrame} | " +
            $"客户端:{_clients.Count}/{_maxPlayers} | " +
            $"总广播:{_totalFramesBroadcast} | " +
            $"总输入:{_totalInputsReceived} | " +
            $"空填充率:{_totalEmptyFills * 100.0 / Math.Max(1, _totalFramesBroadcast * _clients.Count):F1}%"
        );
    }

    #endregion

    #region 服务端性能估算

    /// <summary>
    /// 计算当前对局的性能指标。
    /// 用于容量规划和监控告警。
    /// </summary>
    public (double cpuMsPerTick, long memoryBytes, int bandwidthBps) EstimatePerformance()
    {
        // CPU: 每 Tick 主要开销
        //   - 遍历客户端字典: O(P)
        //   - 输入收集(查缓冲): O(P * B) 其中 B=缓冲窗口大小
        //   - 序列化: O(P * S) 其中 S=输入大小
        //   - 广播: O(P) 次 sendto
        //
        // 对于 P=10, B=4, S=11 bytes:
        //   ~0.1ms per tick (现代 CPU)，非常轻量

        double cpuMsPerTick = _clients.Count * 0.01; // 经验估算值

        // 内存: 环形历史缓冲 + 客户端缓冲
        long memoryBytes = _maxHistoryFrames * (6 + _maxPlayers * PlayerInput.SerializedSize) +
                           _clients.Count * _bufferFrames * (sizeof(uint) + PlayerInput.SerializedSize + 16);

        // 带宽: 下行 = 广播包大小 × 发送频率 × 客户端数
        int pkgSize = 6 + _maxPlayers * PlayerInput.SerializedSize; // bytes
        int bandwidthBps = pkgSize * (_targetFps * 2) * _clients.Count;

        return (cpuMsPerTick, memoryBytes, bandwidthBps);
    }

    #endregion

    public void Dispose()
    {
        _cts.Cancel();
        _udp.Dispose();
        _cts.Dispose();
        Console.WriteLine("[FrameServer] 已关闭");
    }

    /// <summary>
    /// 入口：启动服务端并等待退出。
    /// </summary>
    public static void Main()
    {
        using var server = new FrameServer(port: 8888, maxPlayers: 10, targetFps: 15, bufferFrames: 4);
        server.Start();

        Console.WriteLine("按任意键退出...");
        Console.ReadKey();
    }
}
```

### 2.2 C++: FrameServer 实现

C++ 版本使用原生 socket API，适用于高性能服务端（Dota2、星际争霸 2 等）。重点展示：无锁输入缓冲区、内存池分配、精确帧定时。

```cpp
// FrameServer.h — C++ 帧同步服务端
#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <array>
#include <mutex>
#include <atomic>
#include <chrono>
#include <thread>
#include <string>

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
    using socklen_t = int;
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #include <fcntl.h>
    #define SOCKET int
    #define INVALID_SOCKET (-1)
    #define SOCKET_ERROR (-1)
#endif

// ============================================================
// 基本类型定义
// ============================================================

using frame_t = uint32_t;
using player_id_t = uint8_t;
using input_flags_t = uint16_t;
using fixed_axis_t = int16_t;  // Q8.8 定点数

// 帧同步专用时间戳（微秒精度）
using Timestamp = std::chrono::steady_clock::time_point;
inline int64_t elapsed_us(Timestamp start, Timestamp end) {
    return std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
}
inline int64_t elapsed_ms(Timestamp start, Timestamp end) {
    return std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
}

// ============================================================
// PlayerInput: 单玩家单帧输入 (11 bytes)
// ============================================================
#pragma pack(push, 1)
struct PlayerInput {
    frame_t frameNumber;       // 4 bytes, 大端
    player_id_t playerId;      // 1 byte
    input_flags_t inputFlags;  // 2 bytes, 大端
    fixed_axis_t axisX;        // 2 bytes, 大端
    fixed_axis_t axisY;        // 2 bytes, 大端

    static constexpr size_t SERIALIZED_SIZE = 11;

    static PlayerInput empty_input(frame_t frame, player_id_t pid) {
        return PlayerInput{frame, pid, 0, 0, 0};
    }

    // 大端反序列化（C++20 用 std::endian，此处手动实现以兼容 C++17）
    static PlayerInput deserialize(const uint8_t* data, size_t len);
};
#pragma pack(pop)

// ============================================================
// FramePackage: 单帧广播包
// ============================================================
struct FramePackage {
    frame_t frameNumber;
    uint16_t playerCount;
    std::vector<PlayerInput> inputs; // 按 PlayerId 排序

    // 序列化为大端字节流
    std::vector<uint8_t> serialize() const;
};

// ============================================================
// RingBuffer: 固定大小的环形缓冲区（模板实现）
// ============================================================
template<typename T, size_t Capacity>
class RingBuffer {
    std::array<T, Capacity> _data{};
    std::atomic<size_t> _writeIndex{0};

public:
    void push(const T& item) {
        size_t idx = _writeIndex.fetch_add(1, std::memory_order_relaxed);
        _data[idx % Capacity] = item;
    }

    // 读取从 (writeIndex - count) 到 (writeIndex) 的元素
    // 返回读取到的数量
    size_t read_last_n(T* out, size_t count) const {
        size_t writeIdx = _writeIndex.load(std::memory_order_acquire);
        size_t start = (writeIdx >= count) ? (writeIdx - count) : 0;
        size_t actual = writeIdx - start;
        if (actual > count) actual = count;

        for (size_t i = 0; i < actual; ++i) {
            out[i] = _data[(start + i) % Capacity];
        }
        return actual;
    }

    bool read_at(long logicalIndex, T& out) const {
        size_t writeIdx = _writeIndex.load(std::memory_order_acquire);
        if (logicalIndex < 0) return false;
        size_t start = (writeIdx >= Capacity) ? (writeIdx - Capacity) : 0;
        if (static_cast<size_t>(logicalIndex) < start) return false;
        if (static_cast<size_t>(logicalIndex) >= writeIdx) return false;
        out = _data[static_cast<size_t>(logicalIndex) % Capacity];
        return true;
    }

    // 返回已写入的元素总数（单调递增），作为逻辑索引
    size_t total_written() const {
        return _writeIndex.load(std::memory_order_acquire);
    }
};

// ============================================================
// ClientState: 服务端维护的单个客户端状态
// ============================================================
struct ClientState {
    player_id_t playerId;
    sockaddr_in address;             // UDP 地址
    bool connected;

    std::atomic<int64_t> lastInputTimeUs;  // 微秒时间戳（用于超时判定）
    std::atomic<frame_t> lastInputFrame;   // 最后收到的输入帧号
    std::atomic<int> consecutiveEmptyFrames; // 连续空帧计数

    // 输入缓冲窗口：提前接收的输入
    // 使用 array + 取模而非 map，O(1) 无锁访问
    static constexpr size_t BUFFER_SLOTS = 16; // 足够容纳 bufferFrames + 冗余
    PlayerInput inputBuffer[BUFFER_SLOTS];
    std::atomic<bool> inputValid[BUFFER_SLOTS];

    ClientState() : playerId(0), connected(false),
                    lastInputTimeUs(0), lastInputFrame(0),
                    consecutiveEmptyFrames(0) {
        memset(&address, 0, sizeof(address));
        for (size_t i = 0; i < BUFFER_SLOTS; ++i)
            inputValid[i].store(false, std::memory_order_relaxed);
    }

    // 存入输入（无锁写入）
    void store_input(const PlayerInput& input) {
        size_t slot = input.frameNumber % BUFFER_SLOTS;
        inputBuffer[slot] = input;
        inputValid[slot].store(true, std::memory_order_release);
    }

    // 取出输入。如果未到达，返回 false。
    bool fetch_input(frame_t frame, PlayerInput& out) {
        size_t slot = frame % BUFFER_SLOTS;
        if (!inputValid[slot].load(std::memory_order_acquire)) return false;
        // 验证帧号匹配（防止取模碰撞）
        if (inputBuffer[slot].frameNumber != frame) return false;
        out = inputBuffer[slot];
        inputValid[slot].store(false, std::memory_order_release);
        return true;
    }

    // 检查指定帧是否有输入（不取出）
    bool has_input(frame_t frame) const {
        size_t slot = frame % BUFFER_SLOTS;
        return inputValid[slot].load(std::memory_order_acquire) &&
               inputBuffer[slot].frameNumber == frame;
    }
};

// ============================================================
// FrameServer: 主类
// ============================================================
class FrameServer {
public:
    struct Config {
        int port = 8888;
        int maxPlayers = 10;
        int targetFps = 15;
        int bufferFrames = 4;
        int disconnectTimeoutMs = 5000;
    };

    explicit FrameServer(const Config& cfg);
    ~FrameServer();

    // 禁止拷贝和移动（socket 资源不可复制）
    FrameServer(const FrameServer&) = delete;
    FrameServer& operator=(const FrameServer&) = delete;

    void start();
    void stop();

    // 性能指标
    struct Stats {
        frame_t currentFrame;
        int activeClients;
        uint64_t totalFrames;
        uint64_t totalInputs;
        uint64_t totalEmptyFills;
        double emptyFillRate; // 0.0 ~ 1.0
        double tickTimeUsAvg; // 微秒
    };
    Stats get_stats() const;

private:
    Config _cfg;
    SOCKET _sock{INVALID_SOCKET};
    std::atomic<bool> _running{false};
    std::thread _recvThread;
    std::thread _tickThread;

    // 帧状态
    std::atomic<frame_t> _currentFrame{0};
    std::mutex _broadcastMutex;   // 用于帧号推进和广播的互斥

    // 客户端管理
    std::mutex _clientsMutex;
    std::unordered_map<player_id_t, ClientState> _clients;

    // 帧历史缓存（用于重连追赶）
    static constexpr size_t HISTORY_CAPACITY = 4096; // 约 4.5 分钟 @ 15fps
    RingBuffer<FramePackage, HISTORY_CAPACITY> _frameHistory;

    // 性能计数
    std::atomic<uint64_t> _totalFrames{0};
    std::atomic<uint64_t> _totalInputs{0};
    std::atomic<uint64_t> _totalEmptyFills{0};
    std::atomic<uint64_t> _totalTickTimeUs{0};

    void recv_loop();
    void tick_loop();
    void process_packet(const uint8_t* data, size_t len, const sockaddr_in& from);
    void process_input(const uint8_t* data, size_t len, const sockaddr_in& from);
    void process_join(const sockaddr_in& from);
    void process_reconnect(const uint8_t* data, size_t len, const sockaddr_in& from);
    void do_tick();
    void broadcast_frame(const FramePackage& pkg);
    void send_to(const uint8_t* data, size_t len, const sockaddr_in& addr);
    void send_connect_ack(const ClientState& client);
    void send_catchup_frames(const ClientState& client);
    player_id_t allocate_player_id();
    void check_timeouts();
};

// ============================================================
// 实现 (FrameServer.cpp)
// ============================================================

#ifdef FRAMESERVER_IMPLEMENTATION

// ---------- PlayerInput 反序列化 ----------

PlayerInput PlayerInput::deserialize(const uint8_t* data, size_t len) {
    if (len < SERIALIZED_SIZE) {
        throw std::runtime_error("PlayerInput deserialize: data too short");
    }

    PlayerInput input;
    // 大端 → 主机字节序
    input.frameNumber =
        (static_cast<uint32_t>(data[0]) << 24) |
        (static_cast<uint32_t>(data[1]) << 16) |
        (static_cast<uint32_t>(data[2]) << 8)  |
        static_cast<uint32_t>(data[3]);
    input.playerId   = data[4];
    input.inputFlags =
        (static_cast<uint16_t>(data[5]) << 8) |
        static_cast<uint16_t>(data[6]);
    input.axisX =
        (static_cast<int16_t>(static_cast<uint16_t>(data[7]) << 8) |
        static_cast<uint16_t>(data[8]));
    input.axisY =
        (static_cast<int16_t>(static_cast<uint16_t>(data[9]) << 8) |
        static_cast<uint16_t>(data[10]));

    return input;
}

// ---------- FramePackage 序列化 ----------

std::vector<uint8_t> FramePackage::serialize() const {
    size_t totalSize = 6 + inputs.size() * PlayerInput::SERIALIZED_SIZE;
    std::vector<uint8_t> buf(totalSize);
    size_t off = 0;

    // FrameNumber (大端)
    buf[off++] = static_cast<uint8_t>(frameNumber >> 24);
    buf[off++] = static_cast<uint8_t>(frameNumber >> 16);
    buf[off++] = static_cast<uint8_t>(frameNumber >> 8);
    buf[off++] = static_cast<uint8_t>(frameNumber);

    // PlayerCount (大端)
    buf[off++] = static_cast<uint8_t>(playerCount >> 8);
    buf[off++] = static_cast<uint8_t>(playerCount);

    for (const auto& input : inputs) {
        buf[off++] = static_cast<uint8_t>(input.frameNumber >> 24);
        buf[off++] = static_cast<uint8_t>(input.frameNumber >> 16);
        buf[off++] = static_cast<uint8_t>(input.frameNumber >> 8);
        buf[off++] = static_cast<uint8_t>(input.frameNumber);
        buf[off++] = input.playerId;
        buf[off++] = static_cast<uint8_t>(input.inputFlags >> 8);
        buf[off++] = static_cast<uint8_t>(input.inputFlags);
        buf[off++] = static_cast<uint8_t>(static_cast<uint16_t>(input.axisX) >> 8);
        buf[off++] = static_cast<uint8_t>(input.axisX);
        buf[off++] = static_cast<uint8_t>(static_cast<uint16_t>(input.axisY) >> 8);
        buf[off++] = static_cast<uint8_t>(input.axisY);
    }

    return buf;
}

// ---------- FrameServer 构造/析构 ----------

FrameServer::FrameServer(const Config& cfg) : _cfg(cfg) {}

FrameServer::~FrameServer() { stop(); }

void FrameServer::start() {
    // 初始化 socket
#ifdef _WIN32
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif

    _sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (_sock == INVALID_SOCKET)
        throw std::runtime_error("Failed to create socket");

    // 设置非阻塞
#ifdef _WIN32
    u_long mode = 1;
    ioctlsocket(_sock, FIONBIO, &mode);
#else
    fcntl(_sock, F_SETFL, O_NONBLOCK);
#endif

    // 增大缓冲区
    int bufSize = 256 * 1024;
    setsockopt(_sock, SOL_SOCKET, SO_RCVBUF, reinterpret_cast<char*>(&bufSize), sizeof(bufSize));
    setsockopt(_sock, SOL_SOCKET, SO_SNDBUF, reinterpret_cast<char*>(&bufSize), sizeof(bufSize));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(_cfg.port));
    addr.sin_addr.s_addr = INADDR_ANY;
    if (bind(_sock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == SOCKET_ERROR)
        throw std::runtime_error("Failed to bind socket");

    _running.store(true);

    printf("[FrameServer] 启动: port=%d, fps=%d, buffer=%d帧\n",
           _cfg.port, _cfg.targetFps, _cfg.bufferFrames);

    _recvThread = std::thread(&FrameServer::recv_loop, this);
    _tickThread = std::thread(&FrameServer::tick_loop, this);
}

void FrameServer::stop() {
    _running.store(false);
    if (_recvThread.joinable()) _recvThread.join();
    if (_tickThread.joinable()) _tickThread.join();
    if (_sock != INVALID_SOCKET) {
#ifdef _WIN32
        closesocket(_sock);
        WSACleanup();
#else
        close(_sock);
#endif
        _sock = INVALID_SOCKET;
    }
    printf("[FrameServer] 已关闭\n");
}

// ---------- 收包循环 ----------

void FrameServer::recv_loop() {
    uint8_t buffer[2048];
    sockaddr_in from;
    socklen_t fromLen = sizeof(from);

    while (_running.load(std::memory_order_acquire)) {
        // recvfrom 非阻塞：无数据时立即返回 -1 + EAGAIN
        int n = recvfrom(_sock, reinterpret_cast<char*>(buffer), sizeof(buffer),
                         0, reinterpret_cast<sockaddr*>(&from), &fromLen);
        if (n > 0) {
            process_packet(buffer, static_cast<size_t>(n), from);
        } else if (n == 0) {
            continue; // datagram of length 0 — ignore
        } else {
            // EAGAIN/EWOULDBLOCK: 没有数据，sleep 少量时间避免 CPU 空转
#ifdef _WIN32
            if (WSAGetLastError() == WSAEWOULDBLOCK) {
                std::this_thread::sleep_for(std::chrono::microseconds(100));
                continue;
            }
#else
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                std::this_thread::sleep_for(std::chrono::microseconds(100));
                continue;
            }
#endif
            // 其他 socket 错误
            break;
        }
    }
}

void FrameServer::process_packet(const uint8_t* data, size_t len,
                                  const sockaddr_in& from) {
    if (len < 2) return;

    switch (data[0]) {
        case 0x01: process_input(data + 1, len - 1, from); break;
        case 0x02: process_join(from); break;
        case 0x03: process_reconnect(data + 1, len - 1, from); break;
    }
}

void FrameServer::process_input(const uint8_t* data, size_t len,
                                 const sockaddr_in& from) {
    try {
        auto input = PlayerInput::deserialize(data, len);
        _totalInputs.fetch_add(1);

        std::lock_guard<std::mutex> lock(_clientsMutex);
        auto it = _clients.find(input.playerId);
        if (it == _clients.end()) return;

        auto& client = it->second;
        auto now = std::chrono::steady_clock::now();
        client.lastInputTimeUs.store(
            std::chrono::duration_cast<std::chrono::microseconds>(
                now.time_since_epoch()).count(),
            std::memory_order_release);
        client.lastInputFrame.store(input.frameNumber, std::memory_order_release);
        client.consecutiveEmptyFrames.store(0, std::memory_order_release);

        // 存入无锁输入缓冲区
        client.store_input(input);
    } catch (...) {
        fprintf(stderr, "[错误] 输入包解析失败\n");
    }
}

// ---------- 连接管理 ----------

player_id_t FrameServer::allocate_player_id() {
    for (player_id_t i = 1; i <= static_cast<player_id_t>(_cfg.maxPlayers); ++i) {
        if (_clients.find(i) == _clients.end())
            return i;
    }
    return 0; // 房间已满
}

void FrameServer::process_join(const sockaddr_in& from) {
    std::lock_guard<std::mutex> lock(_clientsMutex);

    if (static_cast<int>(_clients.size()) >= _cfg.maxPlayers) {
        printf("[连接] 拒绝: 房间已满\n");
        return;
    }

    // 检查重复连接
    for (const auto& kv : _clients) {
        if (memcmp(&kv.second.address, &from, sizeof(from)) == 0) {
            return; // 已经连接
        }
    }

    auto pid = allocate_player_id();
    if (pid == 0) return;

    ClientState client;
    client.playerId = pid;
    client.address = from;
    client.connected = true;
    auto now = std::chrono::steady_clock::now();
    client.lastInputTimeUs.store(
        std::chrono::duration_cast<std::chrono::microseconds>(
            now.time_since_epoch()).count(),
        std::memory_order_relaxed);

    _clients[pid] = std::move(client);

    printf("[连接] 玩家 %d 加入, 当前人数: %zu/%d\n",
           pid, _clients.size(), _cfg.maxPlayers);

    send_connect_ack(_clients[pid]);
}

void FrameServer::send_connect_ack(const ClientState& client) {
    uint8_t ack[9];
    ack[0] = 0x02;
    ack[1] = client.playerId;

    frame_t cf = _currentFrame.load(std::memory_order_acquire);
    ack[2] = static_cast<uint8_t>(cf >> 24);
    ack[3] = static_cast<uint8_t>(cf >> 16);
    ack[4] = static_cast<uint8_t>(cf >> 8);
    ack[5] = static_cast<uint8_t>(cf);
    ack[6] = static_cast<uint8_t>(_cfg.maxPlayers);
    ack[7] = static_cast<uint8_t>(_cfg.targetFps);
    ack[8] = static_cast<uint8_t>(_cfg.bufferFrames);

    send_to(ack, sizeof(ack), client.address);
}

void FrameServer::send_to(const uint8_t* data, size_t len, const sockaddr_in& addr) {
    sendto(_sock, reinterpret_cast<const char*>(data), static_cast<int>(len),
           0, reinterpret_cast<const sockaddr*>(&addr), sizeof(addr));
}

// ---------- Tick 循环与帧广播 ----------

void FrameServer::tick_loop() {
    using namespace std::chrono;
    int sendIntervalUs = 1000000 / (_cfg.targetFps * 2); // 双倍速率

    auto nextTick = steady_clock::now();

    while (_running.load(std::memory_order_acquire)) {
        auto now = steady_clock::now();

        if (now >= nextTick) {
            auto tickStart = steady_clock::now();

            do_tick();

            auto tickEnd = steady_clock::now();
            _totalTickTimeUs.fetch_add(
                duration_cast<microseconds>(tickEnd - tickStart).count());

            // 推进到下一个理论 Tick 时间（防止累积误差）
            nextTick += microseconds(sendIntervalUs);

            // 滞后检测
            if (steady_clock::now() > nextTick + microseconds(sendIntervalUs * 2)) {
                printf("[警告] Tick 滞后\n");
                nextTick = steady_clock::now();
            }
        }

        // 精确等待
        auto waitUntil = nextTick;
        while (steady_clock::now() < waitUntil) {
            std::this_thread::sleep_for(microseconds(100));
        }
    }
}

void FrameServer::do_tick() {
    std::lock_guard<std::mutex> lock(_broadcastMutex);

    // 帧号递增（每两次 Tick 递增一次 = 双倍速率冗余广播）
    static int tickCounter = 0;
    frame_t broadcastFrame = _currentFrame.load(std::memory_order_relaxed);
    if (tickCounter % 2 == 0) {
        broadcastFrame = _currentFrame.fetch_add(1);
    }
    tickCounter++;

    // 超时检查
    check_timeouts();

    // 收集所有玩家对该帧的输入
    std::vector<PlayerInput> frameInputs;
    frameInputs.reserve(_clients.size());
    int emptyFills = 0;

    {
        std::lock_guard<std::mutex> clLock(_clientsMutex);
        for (auto& kv : _clients) {
            auto& client = kv.second;
            if (!client.connected) continue;

            PlayerInput input;
            if (client.fetch_input(broadcastFrame, input)) {
                frameInputs.push_back(input);
            } else {
                // 乐观锁定：输入未到，填充空操作
                frameInputs.push_back(
                    PlayerInput::empty_input(broadcastFrame, client.playerId));
                emptyFills++;
                client.consecutiveEmptyFrames.fetch_add(1);
            }
        }
    }

    // 按 PlayerId 排序，确保确定性
    std::sort(frameInputs.begin(), frameInputs.end(),
              [](const PlayerInput& a, const PlayerInput& b) {
                  return a.playerId < b.playerId;
              });

    FramePackage pkg;
    pkg.frameNumber = broadcastFrame;
    pkg.playerCount = static_cast<uint16_t>(frameInputs.size());
    pkg.inputs = std::move(frameInputs);

    _totalFrames.fetch_add(1);
    _totalEmptyFills.fetch_add(emptyFills);

    broadcast_frame(pkg);
    _frameHistory.push(pkg);
}

void FrameServer::broadcast_frame(const FramePackage& pkg) {
    auto data = pkg.serialize();

    std::lock_guard<std::mutex> lock(_clientsMutex);
    for (auto& kv : _clients) {
        if (!kv.second.connected) continue;
        send_to(data.data(), data.size(), kv.second.address);
    }
}

// ---------- 超时检测 ----------

void FrameServer::check_timeouts() {
    auto now = std::chrono::steady_clock::now();
    auto nowUs = std::chrono::duration_cast<std::chrono::microseconds>(
        now.time_since_epoch()).count();
    int64_t timeoutUs = static_cast<int64_t>(_cfg.disconnectTimeoutMs) * 1000;

    std::lock_guard<std::mutex> lock(_clientsMutex);
    auto it = _clients.begin();
    while (it != _clients.end()) {
        auto lastTime = it->second.lastInputTimeUs.load(std::memory_order_acquire);
        if (lastTime > 0 && (nowUs - lastTime) > timeoutUs) {
            printf("[掉线] 玩家 %d 超时 %.1f 秒, 连续空帧: %d\n",
                   it->first,
                   (nowUs - lastTime) / 1e6,
                   it->second.consecutiveEmptyFrames.load());
            it->second.connected = false;

            // 长时间掉线则移除
            if (it->second.consecutiveEmptyFrames.load() > _cfg.targetFps * 30) {
                it = _clients.erase(it);
                continue;
            }
        }
        ++it;
    }
}

// ---------- 重连处理 ----------

void FrameServer::process_reconnect(const uint8_t* data, size_t len,
                                     const sockaddr_in& from) {
    if (len < 1) return;
    player_id_t pid = data[0];

    std::lock_guard<std::mutex> lock(_clientsMutex);
    auto it = _clients.find(pid);
    if (it == _clients.end()) {
        printf("[重连] 玩家 %d 不在活动列表中\n", pid);
        return;
    }

    auto& client = it->second;
    client.address = from;
    client.connected = true;
    client.consecutiveEmptyFrames.store(0);

    printf("[重连] 玩家 %d 重连成功\n", pid);
    send_connect_ack(client);
    send_catchup_frames(client);
}

void FrameServer::send_catchup_frames(const ClientState& client) {
    constexpr int CATCHUP_INTERVAL_MS = 11; // 3 倍速
    size_t totalWritten = _frameHistory.total_written();
    size_t start = (totalWritten > HISTORY_CAPACITY) ?
                   (totalWritten - HISTORY_CAPACITY) : 0;

    frame_t currentFrame = _currentFrame.load(std::memory_order_acquire);
    frame_t lastKnownFrame = client.lastInputFrame.load(std::memory_order_acquire);

    int sent = 0;
    for (size_t i = start; i < totalWritten; ++i) {
        FramePackage pkg;
        if (!_frameHistory.read_at(static_cast<long>(i), pkg)) continue;
        if (pkg.frameNumber <= lastKnownFrame) continue;
        if (pkg.frameNumber >= currentFrame) break;

        auto data = pkg.serialize();
        send_to(data.data(), data.size(), client.address);
        sent++;

        std::this_thread::sleep_for(std::chrono::milliseconds(CATCHUP_INTERVAL_MS));
    }

    printf("[重连] 追赶完成: 发送了 %d 帧给玩家 %d\n", sent, client.playerId);
}

// ---------- 统计 ----------

FrameServer::Stats FrameServer::get_stats() const {
    Stats s;
    s.currentFrame = _currentFrame.load();
    s.activeClients = 0;
    {
        std::lock_guard<std::mutex> lock(_clientsMutex);
        for (const auto& kv : _clients) {
            if (kv.second.connected) s.activeClients++;
        }
    }
    s.totalFrames = _totalFrames.load();
    s.totalInputs = _totalInputs.load();
    s.totalEmptyFills = _totalEmptyFills.load();

    uint64_t totalInputs = s.totalFrames * s.activeClients;
    s.emptyFillRate = totalInputs > 0 ?
        static_cast<double>(s.totalEmptyFills) / totalInputs : 0.0;

    uint64_t totalTicks = s.totalFrames > 0 ? s.totalFrames : 1;
    s.tickTimeUsAvg = static_cast<double>(_totalTickTimeUs.load()) / totalTicks;

    return s;
}

#endif // FRAMESERVER_IMPLEMENTATION
```

### 2.3 Lua (skynet): 帧同步服务

skynet 是云风开发的轻量级游戏服务器框架，广泛用于国内手游后台。以下展示如何在 skynet 中实现帧同步服务。

```lua
-- lockstep_svr.lua — 基于 skynet 的帧同步服务
-- 启动方式: skynet.newservice("lockstep_svr", roomId, maxPlayers, targetFps, bufferFrames)

local skynet = require "skynet"
local socket = require "skynet.socket"
local crypt = require "skynet.crypt" -- 可选: 用于随机种子生成

-- ============================================================
-- 配置常量
-- ============================================================
local MAX_PLAYERS       -- 最大玩家数
local LOGIC_FPS         -- 逻辑帧率 (如 15)
local SEND_INTERVAL_MS  -- 发送间隔(ms) = 1000 / (LOGIC_FPS * 2)
local BUFFER_FRAMES     -- 帧缓冲区大小
local DISCONNECT_TIMEOUT_MS = 5000 -- 掉线超时 (5秒)

-- ============================================================
-- 全局状态
-- ============================================================
local currentFrame = 0      -- 当前逻辑帧号
local clients = {}          -- { playerId => ClientState }
local frameHistory = {}     -- 帧历史缓存 (环形, 用于重连追赶)
local historyIndex = 1
local MAX_HISTORY = 1800    -- 最多缓存 1800 帧 (约 2 分钟 @ 15fps)
local udpSocket             -- 服务器的 UDP socket fd

-- 性能统计
local stats = {
    totalFrames = 0,
    totalInputs = 0,
    totalEmptyFills = 0,
}

-- ============================================================
-- 数据结构: ClientState
-- ============================================================
--[[
ClientState = {
    playerId     = number,    -- 玩家 ID
    addr         = string,    -- IP 地址
    port         = number,    -- 端口
    connected    = boolean,
    lastInputTime= number,    -- 最后收到输入的时间 (skynet.now())
    lastInputFrame = number,  -- 最后收到输入的帧号
    emptyFrames  = number,    -- 连续空帧计数
    inputBuffer  = table,     -- { [frameNumber] = PlayerInput }
}
]]

-- ============================================================
-- 数据结构: PlayerInput
-- ============================================================
--[[
PlayerInput = {
    frameNumber = number,  -- 4 bytes
    playerId    = number,  -- 1 byte
    inputFlags  = number,  -- 2 bytes (bit flags)
    axisX       = number,  -- 2 bytes (Q8.8 fixed point)
    axisY       = number,  -- 2 bytes (Q8.8 fixed point)
}

序列化格式 (大端, 11 bytes):
  [0-3] : uint32 frameNumber
  [4]   : uint8  playerId
  [5-6] : uint16 inputFlags
  [7-8] : int16  axisX
  [9-10]: int16  axisY
]]

-- 反序列化: 大端字节流 → PlayerInput table
local function deserialize_input(data)
    if #data < 11 then
        return nil, "data too short"
    end

    -- string.byte 返回 0-255, 手工组装大端整型
    local function read_u32(off)
        return (string.byte(data, off) << 24) |
               (string.byte(data, off + 1) << 16) |
               (string.byte(data, off + 2) << 8) |
               string.byte(data, off + 3)
    end

    local function read_u16(off)
        return (string.byte(data, off) << 8) |
               string.byte(data, off + 1)
    end

    local function read_s16(off)
        local val = read_u16(off)
        -- 符号扩展: 如果最高位为 1, 转负
        if val >= 0x8000 then
            val = val - 0x10000
        end
        return val
    end

    return {
        frameNumber = read_u32(1),
        playerId    = string.byte(data, 5),
        inputFlags  = read_u16(6),
        axisX       = read_s16(8),
        axisY       = read_s16(10),
    }
end

-- 序列化: PlayerInput table → 大端字节流
local function serialize_input(input)
    local function write_u32(n)
        return string.char((n >> 24) & 0xFF,
                           (n >> 16) & 0xFF,
                           (n >> 8) & 0xFF,
                           n & 0xFF)
    end
    local function write_u16(n)
        return string.char((n >> 8) & 0xFF, n & 0xFF)
    end
    local function write_s16(n)
        if n < 0 then n = n + 0x10000 end
        return write_u16(n)
    end

    return table.concat({
        write_u32(input.frameNumber),
        string.char(input.playerId),
        write_u16(input.inputFlags),
        write_s16(input.axisX),
        write_s16(input.axisY),
    })
end

-- 创建空输入
local function empty_input(frame, playerId)
    return {
        frameNumber = frame,
        playerId    = playerId,
        inputFlags  = 0,
        axisX       = 0,
        axisY       = 0,
    }
end

-- ============================================================
-- 帧包序列化: FramePackage → 大端字节流
-- ============================================================
-- 格式: [frameNumber:4][playerCount:2][inputs...]
local function serialize_frame_package(pkg)
    local parts = {}

    -- frameNumber (4 bytes)
    local fn = pkg.frameNumber
    parts[1] = string.char((fn >> 24) & 0xFF,
                           (fn >> 16) & 0xFF,
                           (fn >> 8) & 0xFF,
                           fn & 0xFF)
    -- playerCount (2 bytes)
    local pc = pkg.playerCount
    parts[2] = string.char((pc >> 8) & 0xFF, pc & 0xFF)

    -- inputs
    for i, input in ipairs(pkg.inputs) do
        parts[2 + i] = serialize_input(input)
    end

    return table.concat(parts)
end

-- ============================================================
-- 工具函数
-- ============================================================

-- 分配玩家 ID (简单线性分配)
local function allocate_player_id()
    for id = 1, MAX_PLAYERS do
        if not clients[id] then
            return id
        end
    end
    return nil
end

-- 发送 UDP 数据包
local function send_udp(data, addr, port)
    if not addr or not port then return end
    -- skynet socket 的 sendto: socket.send(fd, data, addr, port)
    -- 注意: skynet 内部使用整数 IP，需转换
    -- 简化处理: 此处假设 addr 已是 "x.x.x.x" 格式或从消息中获取
    socket.sendto(udpSocket, data, addr, port)
end

-- ============================================================
-- 连接管理
-- ============================================================

local function handle_join(addr, port)
    if not addr or not port then return end

    -- 检查房间是否已满
    local count = 0
    for _ in pairs(clients) do count = count + 1 end
    if count >= MAX_PLAYERS then
        skynet.error("[连接] 拒绝: 房间已满")
        return
    end

    -- 分配 ID
    local pid = allocate_player_id()
    if not pid then return end

    clients[pid] = {
        playerId = pid,
        addr = addr,
        port = port,
        connected = true,
        lastInputTime = skynet.now(),
        lastInputFrame = 0,
        emptyFrames = 0,
        inputBuffer = {},
    }

    skynet.error(string.format("[连接] 玩家 %d 加入 (%s:%d), 当前人数: %d/%d",
        pid, addr, port, count + 1, MAX_PLAYERS))

    -- 发送连接确认
    send_connect_ack(clients[pid])
end

-- 发送连接确认包
local function send_connect_ack(client)
    -- 格式: [0x02][playerId:1][currentFrame:4][maxPlayers:1][targetFps:1][bufferFrames:1]
    local fn = currentFrame
    local data = string.char(
        0x02,                              -- 包类型
        client.playerId,                   -- 玩家 ID
        (fn >> 24) & 0xFF,                -- frameNumber
        (fn >> 16) & 0xFF,
        (fn >> 8) & 0xFF,
        fn & 0xFF,
        MAX_PLAYERS,                       -- 最大玩家数
        LOGIC_FPS,                         -- 帧率
        BUFFER_FRAMES                      -- 帧缓冲区
    )
    send_udp(data, client.addr, client.port)
end

-- ============================================================
-- 输入处理
-- ============================================================

local function process_input(data, addr, port)
    local input, err = deserialize_input(data)
    if not input then
        skynet.error("[错误] 输入包解析失败: " .. (err or "unknown"))
        return
    end

    stats.totalInputs = stats.totalInputs + 1

    local client = clients[input.playerId]
    if not client then
        -- 未注册的玩家 —— 可能是重连
        return
    end

    -- 更新活跃状态
    client.lastInputTime = skynet.now()
    client.lastInputFrame = math.max(client.lastInputFrame, input.frameNumber)
    client.emptyFrames = 0

    -- 存入输入缓冲窗口
    -- 清理过期输入: 移除帧号 < currentFrame - 2 的数据
    local minFrame = currentFrame - 2
    for frm, _ in pairs(client.inputBuffer) do
        if frm < minFrame then
            client.inputBuffer[frm] = nil
        end
    end

    client.inputBuffer[input.frameNumber] = input
end

-- ============================================================
-- 帧 Tick 循环
-- ============================================================

-- 执行一次帧 Tick
local function do_tick()
    -- 帧号递增 (每两次 Tick 递增一次 = 双倍速率)
    -- 使用一个简单的计数器来决定是否递增
    -- 为了简化，这里使用 "每次 Tick 递增帧号，但广播速率由外部定时器控制"
    currentFrame = currentFrame + 1
    stats.totalFrames = stats.totalFrames + 1

    local frameNumber = currentFrame

    -- 组装帧包
    local frameInputs = {}
    local playerCount = 0
    local emptyFillCount = 0

    for pid, client in pairs(clients) do
        if client.connected then
            local input = client.inputBuffer[frameNumber]
            if input then
                frameInputs[#frameInputs + 1] = input
                client.inputBuffer[frameNumber] = nil -- 取用后释放
            else
                -- 乐观锁定: 填充空操作
                frameInputs[#frameInputs + 1] = empty_input(frameNumber, pid)
                emptyFillCount = emptyFillCount + 1
                client.emptyFrames = client.emptyFrames + 1
            end
            playerCount = playerCount + 1
        end
    end

    stats.totalEmptyFills = stats.totalEmptyFills + emptyFillCount

    -- 按 playerId 排序
    table.sort(frameInputs, function(a, b) return a.playerId < b.playerId end)

    -- 构建帧包
    local pkg = {
        frameNumber = frameNumber,
        playerCount = playerCount,
        inputs = frameInputs,
    }

    -- 序列化并广播
    local serializedData = serialize_frame_package(pkg)

    for pid, client in pairs(clients) do
        if client.connected then
            -- 掉线检测
            local elapsed = skynet.now() - client.lastInputTime
            if elapsed > DISconnect_TIMEOUT_MS then
                skynet.error(string.format("[掉线] 玩家 %d 超时 %dms, 连续空帧: %d",
                    pid, elapsed, client.emptyFrames))
                client.connected = false
            else
                send_udp(serializedData, client.addr, client.port)
            end
        end
    end

    -- 清理长时间断线的玩家
    for pid, client in pairs(clients) do
        if not client.connected and client.emptyFrames > LOGIC_FPS * 30 then
            clients[pid] = nil
            skynet.error(string.format("[清理] 移除断线玩家 %d", pid))
        end
    end

    -- 缓存帧历史
    historyIndex = (historyIndex % MAX_HISTORY) + 1
    frameHistory[historyIndex] = pkg

    -- 周期统计
    if frameNumber % 100 == 0 then
        local activeCount = 0
        for _, c in pairs(clients) do
            if c.connected then activeCount = activeCount + 1 end
        end
        local totalPossible = stats.totalFrames * math.max(1, activeCount)
        local emptyRate = totalPossible > 0 and
            (stats.totalEmptyFills / totalPossible * 100) or 0
        skynet.error(string.format(
            "[统计] 帧:%d 客户端:%d/%d 空填充率:%.1f%% 总广播:%d 总输入:%d",
            frameNumber, activeCount, MAX_PLAYERS,
            emptyRate, stats.totalFrames, stats.totalInputs))
    end
end

-- ============================================================
-- 重连处理
-- ============================================================

local function handle_reconnect(data, addr, port)
    if #data < 1 then return end
    local pid = string.byte(data, 1)

    local client = clients[pid]
    if not client then
        skynet.error(string.format("[重连] 玩家 %d 不在活动列表中", pid))
        return
    end

    -- 更新连接信息
    client.addr = addr
    client.port = port
    client.connected = true
    client.emptyFrames = 0
    client.lastInputTime = skynet.now()

    skynet.error(string.format("[重连] 玩家 %d 重连成功 (%s:%d)", pid, addr, port))

    -- 发送连接确认
    send_connect_ack(client)

    -- 发送历史帧追赶 (3倍速)
    local sent = 0
    local idx = (historyIndex - math.min(MAX_HISTORY, #frameHistory)) % MAX_HISTORY
    if idx <= 0 then idx = idx + MAX_HISTORY end

    for i = 1, MAX_HISTORY do
        local pkg = frameHistory[idx]
        if pkg then
            if pkg.frameNumber <= client.lastInputFrame then
                -- 跳过已消费的帧
            elseif pkg.frameNumber >= currentFrame then
                break -- 已追赶到当前帧
            else
                local data = serialize_frame_package(pkg)
                send_udp(data, addr, port)
                sent = sent + 1
                skynet.sleep(11) -- 3倍速: 11ms 间隔 vs 正常 33ms
            end
        end
        idx = (idx % MAX_HISTORY) + 1
    end

    skynet.error(string.format("[重连] 追赶完成: 发送了 %d 帧给玩家 %d", sent, pid))
end

-- ============================================================
-- UDP 收包分发
-- ============================================================

local function handle_packet(data, addr, port)
    if #data < 2 then return end

    -- 在 skynet 中，addr 是从 socket.read 返回的字符串 IP
    local packetType = string.byte(data, 1)
    local payload = string.sub(data, 2)

    if packetType == 0x01 then
        process_input(payload, addr, port)
    elseif packetType == 0x02 then
        handle_join(addr, port)
    elseif packetType == 0x03 then
        handle_reconnect(payload, addr, port)
    else
        skynet.error(string.format("[警告] 未知包类型 0x%02X", packetType))
    end
end

-- ============================================================
-- UDP 收包循环
-- ============================================================

local function recv_loop()
    skynet.error("[收包] UDP 接收循环启动")

    while true do
        -- skynet socket.read 阻塞等待一个 UDP packet
        -- 返回: data (string), addr (string, "x.x.x.x")
        local data, addr = socket.read(udpSocket)
        if not data then
            skynet.error("[收包] socket 关闭，退出收包循环")
            break
        end

        -- 从 addr 中提取 IP 和 port
        -- skynet 中 addr 格式为 "x.x.x.x:port"
        local ip, port_str = string.match(addr, "^([%d%.]+):(%d+)$")
        if ip and port_str then
            local port = tonumber(port_str)
            handle_packet(data, ip, port)
        else
            skynet.error("[收包] 无法解析地址: " .. tostring(addr))
        end
    end
end

-- ============================================================
-- Tick 定时器循环
-- ============================================================

local function tick_loop()
    skynet.error(string.format("[Tick] 定时器启动, 间隔=%dms", SEND_INTERVAL_MS))

    while true do
        skynet.sleep(SEND_INTERVAL_MS) -- skynet.sleep 单位是 0.01 秒
        -- 注意：skynet.sleep(33) 在 SEND_INTERVAL_MS=33 时需要转换为厘秒
        -- 实际上 skynet 用 skynet.timeout() 或者直接用整数厘秒
        -- 为清晰起见，这里使用 1 厘秒 = 10ms 的单位
        -- 实际代码中: skynet.sleep(SEND_INTERVAL_MS / 10)
        -- 我们已经在循环条件中处理
        do_tick()
    end
end

-- ============================================================
-- 服务入口
-- ============================================================

local function init(roomId, maxPlayers, targetFps, bufferFrames)
    MAX_PLAYERS = maxPlayers or 10
    LOGIC_FPS = targetFps or 15
    BUFFER_FRAMES = bufferFrames or 4

    -- 发送间隔 = 双倍速率
    -- skynet.sleep 单位是 0.01 秒 (10ms)
    -- 例如 30fps×2 = 16.67ms → 约 2 tick
    SEND_INTERVAL_MS = math.floor(1000 / (LOGIC_FPS * 2))

    -- 打开 UDP socket
    -- 端口由网关分配或固定
    local port = 8888 + (roomId or 0)
    udpSocket = socket.udp(function(str, addr)
        -- 这个回调在 skynet 协程上下文中被调用
        -- 但我们使用独立的 recv_loop，所以这里不用
    end, "0.0.0.0", port)

    skynet.error(string.format(
        "[FrameServer] 初始化: roomId=%d, port=%d, fps=%d, sendInterval=%dms, buffer=%d帧",
        roomId or 0, port, LOGIC_FPS, SEND_INTERVAL_MS, BUFFER_FRAMES))

    -- 启动协程
    skynet.fork(recv_loop)
    skynet.fork(tick_loop)

    -- 服务主循环：处理消息 (skynet.call / skynet.send)
    skynet.dispatch("lua", function(session, source, cmd, ...)
        -- 可扩展的管理接口: 查询统计、踢人、关服等
        if cmd == "stats" then
            local activeCount = 0
            for _, c in pairs(clients) do
                if c.connected then activeCount = activeCount + 1 end
            end
            return {
                currentFrame = currentFrame,
                activeClients = activeCount,
                totalFrames = stats.totalFrames,
                totalInputs = stats.totalInputs,
                totalEmptyFills = stats.totalEmptyFills,
            }
        elseif cmd == "kick" then
            local pid = ...
            if clients[pid] then
                clients[pid].connected = false
                return true
            end
            return false
        elseif cmd == "shutdown" then
            socket.close(udpSocket)
            skynet.exit()
        end
    end)
end

-- skynet 启动入口
skynet.start(function()
    local roomId = tonumber(skynet.getenv("roomId")) or 0
    local maxPlayers = tonumber(skynet.getenv("maxPlayers")) or 10
    local targetFps = tonumber(skynet.getenv("targetFps")) or 15
    local bufferFrames = tonumber(skynet.getenv("bufferFrames")) or 4

    init(roomId, maxPlayers, targetFps, bufferFrames)
end)
```

---

## 3. 帧同步服务端架构深度剖析

### 3.1 服务端帧管理器 (FrameManager) 设计模式

FrameManager 是帧同步服务端的核心状态机。它的状态转换如下：

```
                  ┌─────────────────────────────────┐
                  │           FrameManager            │
                  │                                  │
    客户端输入 ──►│  ┌──────────┐    ┌───────────┐   │
  (UDP packet)   │  │ 输入缓冲  │    │ 帧历史缓存 │   │
                  │  │ (PerClient│───►│ (环形缓冲) │   │──► 重连追赶
                  │  │  滑动窗口)│    └───────────┘   │
                  │  └────┬─────┘                     │
                  │       │                           │
                  │       ▼                           │
   定时器触发 ──►│  ┌──────────┐                     │
  (每 SendInterval)│  │ 帧组装器 │                     │
                  │  │ (收集+   │                     │
                  │  │  排序+   │──► 广播 (UDP sendto) │
                  │  │  序列化) │                     │
                  │  └──────────┘                     │
                  └─────────────────────────────────┘
```

**FrameManager 的关键设计决策**：

1. **输入缓冲窗口大小**：`BUFFER_SIZE` 帧。每客户端维护 `[currentFrame, currentFrame + BUFFER_SIZE)` 的输入。客户端发送的未来帧号刚好落在这个窗口内。

2. **过期清理策略**：广播完成的帧（帧号 < currentFrame）立即从缓冲区清除。如果不清除，长时间运行后内存会无限增长。但要注意：如果客户端因为网络问题重发了旧帧，清理后这些输入会丢失——但这没关系，因为该帧已经广播过了。

3. **帧历史缓存的环形缓冲**：用于重连追赶。大小 = `历史秒数 × 逻辑帧率`。对于 30 秒缓存、15fps 帧率 = 450 帧。每帧约 116 bytes（10 玩家 × 11 bytes + 6 bytes 头），总计 ≈ 52KB。内存开销极小。

### 3.2 帧步调 (Frame Pacing) 的精确实现

"按照固定频率做某事"看似简单，实现起来有很多细节：

**方案一：Sleep-based（C# Task.Delay / C++ sleep_for）**
```
while running:
    do_tick()
    sleep(sendInterval)
```
问题：`do_tick()` 本身有执行时间（虽然很小，约 0.1~0.5ms），累积起来会导致实际帧率略低于目标。30 分钟后可能偏移数百毫秒。

**方案二：Timer-based with catch-up（基于绝对时间的定时器）**
```
nextTick = now()
while running:
    if now() >= nextTick:
        do_tick()
        nextTick += sendInterval  # 推到下一个理论时间
    else:
        sleep until nextTick
```
这是最精确的方案。即使某次 `do_tick()` 执行慢了，`nextTick` 仍然按理论时间递增，后续 Tick 会自动追赶回来。

**方案三：Spin-wait（忙等）**
```
nextTick = now()
while running:
    while now() < nextTick:
        ; // CPU 空转
    do_tick()
    nextTick += sendInterval
```
精度最高（微秒级），但浪费 CPU。只在需要极高精度时使用（如高频交易）。

**帧同步服务端推荐方案二**，这是前面 C# 和 C++ 代码中使用的方案。

### 3.3 输入缓冲窗口的滑动机制

每客户端独立的输入缓冲窗口是帧同步服务端最精妙的设计之一：

```
客户端 Player A 的输入缓冲窗口:
                                                Window
frame:  ... 100  101  102  103  104  105  106  107  108  109  110 ...
              │    │    │    │    │    │    │    │    │    │    │
              ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼
buffer:   [已广播] [  X  ] [  X  ] [  ✓  ] [  ✓  ] [  ✓  ] [  ✓  ] [  ✓  ] [ ?  ] [ ?  ] [ ?  ]
                               ▲                      ▲              ▲
                               │                      │              │
                         currentFrame=103      已收到的最远帧   客户端预发送的最远帧
                                               (提前量=4)     (客户端当前帧=106)
                                                             发送的是 106+BUF=110
```

窗口 `[currentFrame, currentFrame + BUFFER_SIZE)` 内的帧：
- **已填充 (✓)**：客户端已发送了该帧的输入
- **未填充 (? 或 X)**：客户端尚未发送，Tick 到此时填充空操作
- **已广播 [已广播]**：该帧已处理完毕，从缓冲区移除

### 3.4 断线重连帧追赶 (Frame Catchup)

断线重连是帧同步服务端最具挑战性的功能之一。核心流程：

```
客户端断线                 重连请求                  追赶完成
    │                        │                         │
    │──── 缺失帧 N ~ N+K ────│                         │
    │                        │                         │
    ▼                        ▼                         ▼
┌────────────────────────────────────────────────────────┐
│                    服务端追赶流程                        │
│                                                        │
│ 1. 接收重连请求，验证身份                                │
│ 2. 发送 ConnectAck (告知当前帧号、帧率、缓冲区大小)       │
│ 3. 从帧历史缓存中取出 [N, currentFrame) 的所有帧         │
│ 4. 以 3× 速率批量发送 (追赶间隔 = SendInterval / 3)      │
│ 5. 客户端收到后加速执行逻辑帧，追赶至当前帧              │
│ 6. 追赶完成 → 切换到正常帧率接收                         │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**追赶速度的选择**：
- 太快（如 10×）会把客户端 CPU 打满，导致手机发热/卡顿
- 太慢（如 1×）追不上当前帧，永远处于滞后状态
- 3× ~ 5× 是经验值：对 15fps 的逻辑帧率，3× 追赶 = 45fps 执行速度，现代手机轻松应对

**追赶期间的空操作处理**：重连客户端追赶期间，服务端继续正常广播新帧。追赶客户端需要同时处理"追赶帧"和"实时广播帧"。追赶客户端通常采用双缓冲：一个缓冲接收追赶帧批量，一个缓冲接收实时帧——追赶帧消费完毕后切换到实时帧模式。

### 3.5 服务端性能估算

**CPU 开销**（单局 10 人，15fps，双倍速率 = 30 Tick/s）：

| 操作 | 每 Tick 执行次数 | 每次耗时 | 总耗时/Tick |
|------|-----------------|---------|------------|
| 遍历客户端收集输入 | 10 次 | ~10 ns | ~100 ns |
| 输入排序 (10项) | 1 次 | ~50 ns | ~50 ns |
| 序列化帧包 | 1 次 | ~200 ns | ~200 ns |
| UDP sendto × 10 | 10 次 | ~5 μs/次 | ~50 μs |
| Socket 缓冲区管理 | — | ~10 μs | ~10 μs |
| **总计** | | | **~60 μs/Tick** |

30 Tick/s × 60 μs = 1.8 ms CPU 时间/秒。**CPU 占用约 0.18%**。帧同步服务端的 CPU 开销极低。

**内存开销**（单局 10 人）：

| 项目 | 大小 |
|------|------|
| 帧历史缓存 (30s, 450帧) | ~52 KB |
| 客户端输入缓冲 (10人 × 4帧 × 11字节) | ~440 B |
| Socket 缓冲区 | 256 KB × 2 (收/发) = 512 KB |
| 杂项 (客户端状态、字典…) | ~10 KB |
| **总计** | **~575 KB** |

单局内存不到 1MB。一台 4GB 内存的云服务器理论上可以承载数千局。

**带宽开销**（单局 10 人，15fps，双倍速率 = 30 包/s）：

每个广播包大小 = 6 (header) + 10 × 11 = 116 bytes。
UDP 头 + IP 头 = 28 bytes。
每个包实际占用 = 144 bytes。

下行带宽 = 144 bytes × 30 包/s × 10 人 = **43.2 KB/s** ≈ 345 Kbps。

上行带宽（每客户端）= 11 bytes × 15 帧/s + 28 bytes 头 = **~0.6 KB/s**。

即使在 2G 网络（~20 KB/s）下也毫无压力。这就是帧同步带宽优势的核心体现。

---

## 4. 王者荣耀服务端架构参考

### 4.1 整体拓扑

```
                        ┌────────────────────┐
                        │    网关层 (Gate)    │
                        │  - 连接管理          │
                        │  - 协议转换          │
                        │  - 负载均衡          │
                        └────────┬───────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
     ┌────────▼────────┐ ┌──────▼───────┐ ┌────────▼────────┐
     │   BattleServer  │ │ BattleServer │ │   BattleServer  │
     │   (帧同步对局)   │ │ (帧同步对局)  │ │   (帧同步对局)   │
     │                 │ │              │ │                 │
     │ • FrameManager  │ │ • FrameMgr   │ │ • FrameManager  │
     │ • 输入收集/广播  │ │ • 输入收集/广播│ │ • 输入收集/广播  │
     │ • 录像生成      │ │ • 录像生成    │ │ • 录像生成      │
     └────────┬────────┘ └──────┬───────┘ └────────┬────────┘
              │                  │                  │
     ┌────────▼──────────────────▼──────────────────▼────────┐
     │                    Redis / 共享内存                     │
     │  - 房间状态缓存                                         │
     │  - 玩家匹配信息                                         │
     └───────────────────────────────────────────────────────┘
```

**BattleServer** 是王者荣耀帧同步的核心服务。每个 BattleServer 进程同时承载多局对战（通常 100~500 局/进程），每局独立的 FrameManager 实例。

### 4.2 BattleServer 的关键设计

**① 单进程多房间**

一台物理机运行一个 BattleServer 进程，内部以协程/异步方式同时驱动数百个对局。每个对局 = 一个 `BattleRoom` 对象，拥有独立的 FrameManager、客户端列表、帧历史缓存。

王者荣耀使用 Linux epoll + 协程（或类似 Go 的 goroutine）实现高并发。UDP socket 被所有对局共享——收包时根据 `{roomId, playerId}` 分发到对应的 BattleRoom。

**② 帧同步 + 状态同步混合**

这是很多人不知道的一点：王者荣耀并非纯帧同步！对于某些场景，它混入了轻量状态同步：

- **帧同步负责**：英雄移动、普攻、技能释放——这些依赖确定的物理/逻辑计算
- **状态同步负责**：经济系统（金币获取）、装备购买、小兵生成——这些不直接影响战斗，但用状态同步更简单
- **混合同步**：防御塔血量——帧同步计算伤害，但防御塔被推倒的事件通过状态同步确认

这种混合设计避免了纯帧同步的一个陷阱：为"不太需要确定性的系统"支付确定性的复杂度。

**③ 录像与 Spectator**

BattleServer 在帧同步过程中，将每帧的 FramePackage 写入录像文件。录像文件格式：
```
[Header] 版本号、玩家列表、英雄选择、随机种子
[Frame 0] PlayerInput 集合
[Frame 1] PlayerInput 集合
...
[Frame N] PlayerInput 集合
```

一场 20 分钟的对局 @ 15fps = 18,000 帧。18,000 × 116 bytes ≈ 2.1 MB。这就是为什么王者荣耀的录像文件只有几 MB。

**④ 反外挂**

帧同步的反外挂主要依赖两点：
- **全知视角 (Omniscient Server)**：虽然服务器不执行逻辑，但它可以看到所有输入。如果玩家 X 在帧 N 的输入坐标是 (1000, 500)，但该玩家的英雄实际在 (200, 300)（上一个合法位置），服务器可以标记为可疑。
- **客户端校验**：客户端本地运行反外挂模块，检测内存修改（加速、全图等）。

---

## 5. 练习

### 练习 1: 基础 — 实现简化 FrameServer (45min)

创建一个只支持 2 个玩家、严格帧对齐的控制台 FrameServer：

1. **基本结构**：实现 UDP 收发包 + 帧号递增
2. **严格对齐**：两个玩家的输入都到齐后才广播。打印每次广播时的等待时间
3. **包格式**：使用简化的 4 字节帧号 + 4 字节玩家输入（可直接用 int）
4. **测试**：写一个简单的客户端模拟器，可配置延迟（`--delay-ms=N`），验证：
   - 延迟 0ms 时，帧间隔接近目标（如 66ms @ 15fps）
   - 延迟 100ms 时，帧间隔被拖慢到 ~100ms

扩展：将严格对齐改为乐观锁定（固定频率广播 + 空操作填充），对比两种模式下的帧率变化。

### 练习 2: 进阶 — 帧缓冲窗口调优 (60min)

基于练习 1 的乐观锁定 FrameServer，实现帧缓冲窗口：

1. **客户端预发送**：客户端在帧 N 时发送帧 N + BUFFER_SIZE 的输入
2. **服务端滑动窗口**：每客户端维护 `[currentFrame, currentFrame + BUFFER_SIZE)` 的输入缓冲
3. **实验**：
   - 固定延迟 50ms，测试 BUFFER_SIZE = 1, 2, 3, 4, 5, 6, 8
   - 记录每次实验的空操作填充率（一段时间内空操作占总 Tick 的比例）
   - 记录"输入到达但已过期"的比例（输入帧号 < 当前广播帧号）
   - 绘制 BUFFER_SIZE vs 空填充率的折线图
4. **分析**：为什么 BUFFER_SIZE 不能无限增大？找出最优值并解释。

### 练习 3: 挑战 — 断线重连与帧追赶 (90min)

实现完整的断线重连流程：

1. **服务端**：
   - 客户端模拟断线（停止发送输入 10 秒）
   - 服务端在 5 秒超时后将客户端标记为断线，持续用空操作填充
   - 客户端恢复连接后，发送重连请求（包含断线前最后一帧的帧号）
   - 服务端从帧历史缓存中取出追赶帧，以 3× 速度发送
   
2. **客户端**：
   - 实现追赶模式：收到追赶帧时，跳过渲染，纯粹执行逻辑帧（加速追赶）
   - 追赶完成后自动切换到正常模式
   - 验证追赶后的游戏状态与"从不掉线"的参考客户端一致（对比两者的英雄位置、血量）

3. **边界情况**：
   - 帧历史缓存满了怎么办？（环形覆写 → 最老的帧丢失 → 只能追赶到最早的可用帧）
   - 追赶过程中又收到新的实时帧怎么办？（双缓冲：一个队列消费追赶帧，一个消费实时帧）
   - 客户端断线 30 秒以上怎么办？（服务端移除玩家，AI 托管或判定失败）

---

## 6. 扩展阅读

### 必读文章
- **Gaffer On Games — Deterministic Lockstep**：帧同步理论的奠基性文章
  https://gafferongames.com/post/deterministic_lockstep/
- **Gaffer On Games — UDP vs TCP**：为什么游戏网络用 UDP 而不是 TCP
  https://gafferongames.com/post/udp_vs_tcp/

### 工业实践
- **腾讯云: 从王者荣耀聊聊游戏的帧同步**：王者荣耀帧同步方案的深度分析
  https://cloud.tencent.com/developer/article/2479003
- **腾讯游戏学院: 帧同步游戏开发基础指南**：含 BattleServer 架构设计
  https://developer.cloud.tencent.com/article/1050868
- **基于帧同步的游戏框架说明**：实际项目的帧同步架构分享（含 BattleServer 代码结构）
  https://cloud.tencent.com/developer/article/2147386

### 开源参考
- **UnityLockstep (GitHub: Kirito9910)**：Unity C# 完整帧同步框架（含服务端）
- **ET (GitHub: egametang/ET)**：Unity + C# 的 ECS 框架，内置帧同步 BattleServer
- **skynet (GitHub: cloudwu/skynet)**：云风开发的轻量级游戏服务器框架，广泛用于帧同步项目
- **NKGMobaBasedOnET**：基于 ET 框架的 MOBA 项目，含完整帧同步实现

### 相关教程
- 本计划第 07 节：**帧同步协议设计：帧指令、冗余发包、丢包处理**
- 本计划第 12 节：**帧同步进阶：快照校验、预测回滚与反外挂**
- 本计划第 28 节：**断线重连与中途加入**

---

## 常见陷阱

### 陷阱 1: 忘记帧号的单调性要求

**错误**：服务端重启或异常恢复后，帧号从 0 重新开始。

**为什么错**：客户端保留着旧帧号的状态。服务端重置帧号后，客户端发来的包带了大的帧号（如 15000），而服务端期望小的帧号（0），导致所有输入都被当作"超出窗口"而丢弃。

**正确做法**：帧号必须是全局单调递增的。服务端异常恢复时，要么从持久化的帧号继续，要么触发全体客户端重新同步。

### 陷阱 2: 广播时直接修改输入缓冲区

**错误**：
```csharp
// 广播时遍历客户端输入缓冲
foreach (var client in _clients) {
    var input = client.InputBuffer[frameNumber];
    client.InputBuffer.Remove(frameNumber);  // ← 在遍历中修改
    framePackage.Inputs[i++] = input;
}
```

**为什么错**：多线程环境下，收包线程可能同时在向同一个 `InputBuffer` 写入。在遍历中修改集合引发并发问题。即使单线程，修改正在遍历的字典也可能改变内部布局。

**正确做法**：使用 `TryGetValue` + 后置清理，或使用快照（snapshot）模式——先收集所有输入的快照，再批量清理。

### 陷阱 3: 服务端时钟漂移

**错误**：用 `DateTime.Now` 或 `std::chrono::system_clock::now()` 驱动 Tick 循环。

**为什么错**：系统时钟可以被 NTP 修正、用户手动调整、夏令时切换。如果在 Tick 循环运行时系统时钟被向后调整了 5 秒，`nextTick` 时间戳会突然"在未来很远"，导致 Tick 循环冻结 5 秒——整局玩家卡住。

**正确做法**：使用单调时钟（`Stopwatch` in C#, `std::chrono::steady_clock` in C++, `skynet.now()` in Lua）。单调时钟保证永远不会回退，不受系统时间调整影响。

### 陷阱 4: 空操作不等于不操作

**错误**：某玩家在帧 N 没有发输入包，服务端就不在广播包中为该玩家分配槽位。

**为什么错**：帧同步要求 $I_n$ 对所有客户端**完全一致**。如果包 A 中有 Player3 的输入而包 B 中没有，两个客户端按不同的输入执行逻辑 → desync。

**正确做法**：广播包中始终为所有玩家预留槽位。没有输入时填充显式的空操作（`InputFlags=0`）。

### 陷阱 5: 帧追赶时忘记处理随机种子

**错误**：断线重连追赶期间，客户端快速执行 N 帧逻辑，但随机数生成器在每个逻辑帧中按"总调用次数"推进。

**为什么错**：在线客户端的逻辑帧 N 中只调用了 1 次 `Random.Next()`（例如判断暴击），而追赶客户端因为某些代码路径不同调用了 2 次——PRNG 的状态岔开了。后续所有随机结果都不同 → desync。

**正确做法**：每个逻辑帧开始时，用 `hash(seed, frameNumber)` 重新播种 PRNG。这样无论追赶速度如何，每帧的随机序列都是确定且一致的。详见教程 06。

### 陷阱 6: 过度优化导致丢包

**错误**：为了降低 CPU，减少 UDP socket 的接收缓冲区大小。

**为什么错**：UDP 是无连接的。如果 socket 接收缓冲区太小，高流量时新到达的包会被内核丢弃——这发生在应用层代码看到之前。你甚至不知道它们丢了。

**正确做法**：Socket 接收缓冲区至少设为 256KB。现代操作系统允许到 MB 级。帧同步带宽很低（几十 KB/s），256KB 足够容纳 5~10 秒的突发流量。

### 陷阱 7: 忽略多网卡 / NAT 环境

**错误**：客户端连接时，服务端用 `recvfrom` 返回的源地址作为客户端的"永久地址"。

**为什么错**：移动网络环境下，客户端的 IP 地址可能在会话期间改变。用户从 WiFi 切换到 4G → IP 改变。重连时服务端仍向旧 IP 发送数据 → 客户端收不到。

**正确做法**：不依赖长期有效的 IP 地址。重连时客户端主动告知新的连接端点，服务端更新地址映射。
