# 网络调试、性能分析与监控

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: 全部前置教程（建议学完 1-29 后再读本节，串联所有调试手段）

---

## 1. 概念讲解

### 1.1 为什么需要系统化的调试和监控？

学完前面 29 节，你可以在本地搭建一套帧同步/状态同步的 Demo。但从 Demo 到上线，中间隔着一道深渊：**线上环境是看不见的**。

你在开发环境永远模拟不出真实用户的网络条件——4G 弱信号下的 300ms 抖动、WiFi 2.4GHz 频段的突发丢包、玩家从电梯出来时的连接中断。你也模拟不出那个只在一万局中出现一次的 Desync——它在你的开发机上从不复现，但在线上每周出现 3 次。

**这套系统就是你的眼睛**。它回答三个问题：

| 问题 | 对应系统 | 解决方式 |
|------|---------|---------|
| "玩家说卡了——卡在哪？" | 性能分析 | 带宽/延迟/丢包率查询 |
| "两个客户端状态不一致——哪里不一致？" | 帧同步调试 | Hash 比对 + 二分定位 + 回放 diff |
| "服务器为什么 CPU 100%？" | 服务器监控 | 指标采集 + 告警 + 日志 |

本节将这三大体系串联起来。每一套都可以独立工作，但组合在一起才能覆盖从开发到运维的完整链路。

**核心思想地图**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     网络同步调试、分析与监控全景                           │
├───────────────────┬───────────────────┬───────────────────┬──────────────┤
│   帧同步调试       │   状态同步调试     │   网络性能分析     │  服务器监控   │
│   (客户端视角)     │   (客户端+服务端)  │   (链路视角)       │  (服务端视角) │
├───────────────────┼───────────────────┼───────────────────┼──────────────┤
│ • Desync检测+定位 │ • RPC/属性日志    │ • 带宽分解         │ • 指标采集    │
│ • 帧日志系统      │ • 预测vs权威可视  │ • RTT分解          │ • 告警系统    │
│ • 回放自动Diff    │ • NetworkProfiler│ • 丢包率监控       │ • 结构日志    │
│ • 帧号可视化      │ • net.* 控制台   │ • Wireshark分析    │ • 日志聚合    │
│ • 二分定位问题帧  │ • GameplayDebugger│ • 网络模拟注入     │ • 健康检查    │
├───────────────────┴───────────────────┴───────────────────┴──────────────┤
│                          测试策略层                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐    │
│  │  网络模拟注入      │  │  自动化回放测试   │  │  混沌工程             │    │
│  │  延迟/丢包/抖动    │  │  录像批量回放     │  │  随机断连/丢包/延迟   │    │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 1.2 帧同步调试

帧同步的核心痛点是 **Desync 不可见**：两个客户端都在自己的"平行宇宙"里运行，没有人知道谁对谁错——因为服务端不跑逻辑。

#### 1.2.1 Desync 检测：状态 Hash 比对

第 12 节（帧同步进阶）详细讨论了 Hash 算法和校验策略。这里聚焦**诊断流程**——Hash 不一致之后该怎么办。

**诊断流程**：

```
检测到 Desync（帧号 N 的 Hash 不一致）
    │
    ├─ 第 1 步：收集现场数据
    │   ├─ 双方客户端的 Hash 值
    │   ├─ 最近一次 Hash 一致的帧号 (lastGoodFrame)
    │   └─ 从 lastGoodFrame 到 N 的所有输入指令
    │
    ├─ 第 2 步：归档到诊断文件
    │   ├─ {RoomId}_{PlayerId}_{frame}.diag 写入本地
    │   └─ 上传到诊断服务器（用于后续分析）
    │
    ├─ 第 3 步：服务端重放诊断
    │   ├─ 用 DS 从 lastGoodFrame 重放输入到 N
    │   ├─ 在每一帧计算 Hash，与客户端 Hash 列表比对
    │   └─ 找到 Hash 首次分歧的帧 → 这就是 desync 帧！
    │
    └─ 第 4 步：二分定位问题帧
        将 lastGoodFrame 到 N 的区间二分：
        在中间帧 M 计算 Hash → 与"正确"的 Hash 对比
        → 一致：desync 在 M 之后 → 对 [M+1, N] 继续二分
        → 不一致：desync 在 M 或之前 → 对 [lastGoodFrame, M] 继续二分
        → 直到定位到具体的**单帧**，然后检查该帧的输入/逻辑
```

**二分法的时间复杂度是 O(log n)**：1000 帧的区间只需约 10 次重放即可定位。

#### 1.2.2 帧日志（Frame Logging）

帧日志是最基础的调试手段，但要做得对并不简单。以下是工业级的帧日志设计：

**关键原则——结构化而非文本**：

```
❌ 糟糕的做法（文本日志，无法自动分析）：
[Frame 12345] Player 0 attack: pos=(500, 200), hp=80
[Frame 12345] Player 1 hit:   pos=(300, 150), hp=50

✅ 正确的做法（结构化日志，可自动比对）：
{"f":12345,"t":"input","p":0,"keys":["attack"]}
{"f":12345,"t":"state","p":0,"hp":80,"x":500,"y":200,"vx":3,"vy":0}
{"f":12345,"t":"event","code":"damage","src":0,"dst":1,"val":25}
```

**帧日志需要记录的内容**：

| 类别 | 内容 | 用途 |
|------|------|------|
| **输入** | 每帧各玩家的按键/摇杆状态 | 重放输入、二分定位 |
| **关键状态** | HP、位置（定点数原始值）、Buff 列表、技能 CD | 检查状态一致性 |
| **事件** | 伤害、死亡、Buff 添加/移除、技能释放 | 追踪事件触发条件 |
| **系统状态** | 随机种子值、AI 决策路径、物理碰撞结果 | 定位非确定性源头 |
| **网络收发包** | 帧数据包的 seq、ack、时间戳 | 排查丢包/乱序 |

#### 1.2.3 回放对比（Replay Diff）

帧同步的核心优势之一：录像文件极小（只记录输入指令，不记录画面）。利用这个特性可以做**自动回放对比**：

```
┌──────────────────────────────────────────────────────────────┐
│                    回放自动 Diff 系统                          │
│                                                              │
│  录像文件（输入序列）──► DS 重放 ──► 每帧 Hash 列表 A          │
│                                                              │
│  同一录像文件    ──► 开发机重放 ──► 每帧 Hash 列表 B          │
│                                                              │
│  比对: 逐帧 diff Hash_A vs Hash_B                            │
│  结果: Frame 3847: Hash mismatch!                            │
│        Frame 3847 输入: P0=attack, P1=move_right             │
│        Frame 3847 状态差异: P0.x: A=512 B=510 (+2)           │
│        ← 定点数精度问题！                                     │
└──────────────────────────────────────────────────────────────┘
```

**CI/CD 集成**：每次代码提交后，在 CI 中用 1000 局历史录像自动回放，Hash 比对全部通过才允许合并。这是防止回归的最强防线。

#### 1.2.4 Unity：帧号可视化与状态查看面板

在 Unity 中构建一个运行时调试面板，显示：

- **当前逻辑帧号** + **渲染帧号**（两者可能不同步！）
- **帧缓冲状态**：已收到多少帧、已执行多少帧、缓冲水位
- **网络状态**：RTT、丢包率、帧数据包大小
- **实体状态表**：选中实体 → 显示位置/HP/状态/输入历史

**实现要点**：

```
帧号显示使用 OnGUI 或 UI Toolkit：
  - 逻辑帧号用黄色（每逻辑帧更新一次）
  - 渲染帧号用白色（每渲染帧更新）
  - 如果两者显示不同颜色比例 → 立即知道帧率不匹配

状态面板：
  - 左侧实体列表（按 ID 排序）
  - 右侧选中实体的详细状态
  - 滚动查看历史帧的输入记录
  - 一键导出诊断文件
```

#### 1.2.5 Unreal：GameplayDebugger 扩展

Unreal Engine 内置的 `GameplayDebugger` 可以通过扩展 Category 来显示帧同步信息：

```cpp
// 注册自定义 Category
// 在模块启动时:
IGameplayDebugger& GDModule = IGameplayDebugger::Get();
GDModule.RegisterCategory("Lockstep",
    IGameplayDebugger::FOnGetCategory::CreateStatic(&FLockstepDebugger::MakeInstance),
    EGameplayDebuggerCategoryState::EnabledInGameAndSimulate);
```

通过按 `'` 键激活 GameplayDebugger，然后按数字键切换 Category，可以实时看到：
- 当前帧号和帧率
- 输入缓冲区的帧水位
- 最近 N 帧的 Hash 历史
- 网络 RTT 和丢包率

---

### 1.3 状态同步调试

状态同步的核心痛点是 **可观测性不足**——"这个属性为什么没同步？""这个 RPC 为什么没到？""为什么客户端的预测位置和权威位置差了 3 米？"

#### 1.3.1 网络消息日志

状态同步的所有网络活动都应该可记录、可回溯：

**需要记录的 RPC 信息**：

```
RPC Log Entry:
{
  "tick": 12345,          // 发送时服务端 tick
  "rpc_id": 0x002F,       // RPC 类型枚举
  "rpc_name": "ServerFire",
  "sender": 3,            // 发送者 playerId
  "target": [0, 1, 2],    // 接收者列表（空=广播）
  "channel": "reliable",  // reliable / unreliable
  "payload_size": 18,     // 序列化后字节数
  "sent_ts": 1234567890,  // 发送时间戳 (ms)
  "recv_ts": [1234567915, 1234567920, ...], // 各客户端收到时间戳
}
```

**需要记录的属性同步信息**：

```
Property Replication Log Entry:
{
  "tick": 12345,
  "entity_id": 107,
  "dirty_mask": 0x0A,     // 哪些属性变了（位掩码）
  "fields": [
    {"name":"Health", "old":100, "new":75},
    {"name":"Position", "old":[500,200,0], "new":[520,200,0]}
  ],
  "payload_size": 14,
  "targets": [0, 1, 2, 3],
}
```

#### 1.3.2 预测 vs 权威可视化

第 15 节介绍了 Gizmos 双色显示。这里扩展为**系统化的可视化方案**：

**双色渲染**：
- **绿色** = 客户端预测状态（本地模拟的结果）
- **红色** = 服务端权威状态（最近收到的最新权威快照）
- **蓝色连线** = 预测误差向量

**进阶可视化**：

```
┌──────────────────────────────────────────────────────┐
│  屏幕角落的迷你面板（半透明覆盖）                       │
│                                                      │
│  ╔══════════════════════════════════╗                 │
│  ║  NetSync Debug                   ║                 │
│  ║  ───────────────────────────     ║                 │
│  ║  RTT: ████░░░ 48ms               ║                 │
│  ║  Loss: █░░░░░ 2.1%               ║                 │
│  ║  Jitter:██░░░░░ 8ms              ║                 │
│  ║  ───────────────────────────     ║                 │
│  ║  Pred Err: 0.42m (↑)             ║                 │
│  ║  Reconcil: 12                     ║                 │
│  ║  RPC Queue: 3 pending             ║                 │
│  ║  ───────────────────────────     ║                 │
│  ║  [绿]预测  [红]权威  [蓝]偏差     ║                 │
│  ╚══════════════════════════════════╝                 │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**热力图模式**：将整个地图网格化，用红色深浅表示该区域"预测误差"的频率。开发/QA 可以一眼看出哪些区域的同步质量最差（通常是障碍物拥挤区域、传送门附近）。

#### 1.3.3 Unity：Network Profiler

Unity 提供了 Network Profiler，位于 `Window > Analysis > Network Profiler`。它显示：

- **Messages 视图**：时间轴上每条网络消息（类型、大小、方向）
- **Objects 视图**：每个 NetworkObject 的属性变更频率和带宽
- **连接视图**：每个连接的 RTT、丢包、带宽

但对于自定义网络层（如 KCP ENET），Unity 内置的 Network Profiler 不适用。这时需要**自建监控管道**：

```csharp
// 自定义 NetworkMonitor 替代 Unity Network Profiler
public class NetworkMonitor : MonoBehaviour
{
    // 消息类型 → 累计字节数
    Dictionary<MessageType, long> _bandwidthByType = new();
    // 时间窗口内的消息列表（用于滚动窗口统计）
    Queue<TimestampedMessage> _recentMessages = new();

    void OnGUI()
    {
        // 在左上角绘制带宽分布柱状图
        // 在左下角绘制最近消息列表（最后 50 条）
    }
}
```

#### 1.3.4 Unreal：Network Profiler 与 net.* 控制台命令

Unreal Engine 提供了强大的网络分析工具链：

**`net.*` 控制台命令速查**：

| 命令 | 作用 | 示例输出 |
|------|------|---------|
| `net.DrawDebugReplication 1` | 屏幕绘制属性复制可视化 | 实体上方显示 Replicated 属性列表，变动的字段闪烁 |
| `net.PackageMap.DebugObject 1` | 调试特定对象的序列化 | 打印每次序列化的字段名和值 |
| `net.PackageMap.DebugAll 1` | 调试所有对象的序列化 | **注意：输出极多，仅用于极端调试** |
| `stat net` | 显示网络统计 | RPC数/秒、属性复制字节数/秒、收发包数 |
| `stat nettraffic` | 网络流量统计 | 发送/接收字节数、丢包率、RTT |
| `net.DebugDraw 1` | 绘制网络相关调试线 | 显示角色实际位置和插值后的渲染位置 |
| `net.Reliable.Debug 1` | 调试可靠RPC的确认/重传 | 显示队列状态 |
| `net.PacketLoss` | 查看当前丢包率 | 返回百分比 |
| `net.PktLag` | 查看/设置模拟延迟 | 单位 ms |
| `net.PktLagVariance` | 查看/设置模拟抖动 | 单位 ms |
| `net.PktLoss` | 查看/设置模拟丢包率 | 0-100 |

**Unreal Network Profiler**（`UNetworkProfiler`）更强大：
- 记录每一帧的 CPU 时间分配（序列化、压缩、发送）
- 可视化 Actor 复制优先级
- 追踪属性复制次数和带宽占用
- 通过 `-networkprofiler` 命令行参数启动 profiling 会话，输出 `.nprof` 文件供后续分析

---

### 1.4 网络性能分析

网络性能分析回答"带宽够不够、延迟高不高、丢包多不多"这三个基础问题。

#### 1.4.1 带宽分析

**按消息类型分解带宽**：

```
┌──────────────────────────────────────────────────────┐
│  每秒带宽分解（示例：60 tick FPS 服务器，10 玩家）     │
│                                                      │
│  ██████████████ 帧输入数据 (12 KB/s)                  │
│  ██████████     属性同步增量 (8 KB/s)                 │
│  ██████         状态同步全量 (5 KB/s)                  │
│  ████           RPC 调用 (3 KB/s)                     │
│  ███            心跳/ACK (2 KB/s)                     │
│  █              其他 (0.5 KB/s)                       │
│  ─────────────────────────────                       │
│  总计: 30.5 KB/s / player                            │
│  10 人总计: 305 KB/s 出站                           │
└──────────────────────────────────────────────────────┘
```

**带宽分析的关键指标**：

| 指标 | 计算方式 | 告警阈值 | 含义 |
|------|---------|---------|------|
| `bps_by_type[msgType]` | 每类消息的 bytes/sec（滑动窗口平均） | 单个类型超过 10KB/s | 某类消息异常膨胀 |
| `peak_bps` | 最大值 / 滑动窗口 | 总带宽超过预算 80% | 接近带宽上限 |
| `overhead_ratio` | (UDP头+协议头) / payload | > 0.3 | 小包过多，浪费带宽 |
| `redundancy_ratio` | 冗余字节 / 有效字节 | > 0.5 | 帧同步冗余发包过度 |

#### 1.4.2 延迟分析（RTT 分解）

RTT 不等于网络延迟。它的完整分解是：

```
RTT = 网络传输延迟 + 处理延迟 + 排队延迟

     ┌──────────────┐         ┌──────────────┐
     │    客户端      │         │    服务器      │
     │              │  1.     │              │
     │  发送请求     │────────►│  接收         │
     │              │  网络    │              │
     │              │  延迟    │  处理         │
     │              │         │  (逻辑帧       │
     │              │         │   排队等待     │
     │              │         │   + 执行)     │
     │              │  2.     │              │
     │  收到响应    │◄────────│  发送响应     │
     │              │  网络    │              │
     │              │  延迟    │              │
     └──────────────┘         └──────────────┘

RTT = delay_1 + processing_time + delay_2
```

**测量处理延迟**：

```csharp
// 在服务端，记录每个消息的排队时间和处理时间
public struct MessageTiming
{
    public long recvWallClockMs;    // 收到消息的墙钟时间
    public long tickStartWallMs;    // 所在逻辑帧开始时间
    public long processedWallMs;    // 处理完成的墙钟时间
    public uint tickNo;             // 所在逻辑帧号

    public long QueueDelayMs => tickStartWallMs - recvWallClockMs;  // 排队延迟
    public long ProcessDelayMs => processedWallMs - tickStartWallMs; // 处理延迟
}
```

对延迟的分解能帮你回答："客户端说卡，是网络卡还是服务器逻辑卡？"

#### 1.4.3 丢包率监控

实时丢包率监控应该按**滑动窗口**统计，而非累计：

```csharp
public class PacketLossMonitor
{
    // 环形缓冲区：最近 N 秒的收包状态
    const int WINDOW_SECONDS = 10;
    struct TickEntry { public uint expectedSeq; public bool received; }
    Queue<TickEntry> _window = new();

    public float LossRate
    {
        get
        {
            // 只统计窗口内有足够数据的情况
            if (_window.Count < 50) return -1; // 不足：返回无意义值
            int lost = _window.Count(e => !e.received);
            return (float)lost / _window.Count;
        }
    }

    // 按丢包模式分类
    public LossPattern Pattern
    {
        get
        {
            // 分析窗口内丢包的分布
            // 随机分布 → 网络质量差
            // 突发集中 → WiFi 干扰 / 信号切换
            // 周期性 → 可能有其他应用抢占带宽
        }
    }
}
```

**丢包模式识别**：

| 模式 | 特征 | 根因 | 应对 |
|------|------|------|------|
| **随机稀疏** | 每 100 包丢 1-2 包 | 一般网络质量 | FEC 前向纠错 |
| **突发集中** | 连续丢 5-15 包 | WiFi 干扰、信号切换 | 加大缓冲窗口 |
| **周期性** | 每隔固定时间丢包 | 其他应用流量突发 | QoS 优先级 |
| **上升趋势** | 丢包率随时间增长 | 内存泄漏导致处理变慢 | 排查服务器 |

#### 1.4.4 工具链

| 工具 | 用途 | 使用场景 |
|------|------|---------|
| **Wireshark** | 抓包分析协议细节 | 开发/QA 排查：确认消息内容、字节顺序、序列化正确性 |
| **Unity Network Simulator** | 模拟网络条件 | Editor 内模拟延迟/丢包/抖动 |
| **UE Network Emulation** | 模拟网络条件 | PIE 内或命令行参数控制网络条件 |
| **clumsy** (Windows) | 系统级网络干扰 | 拦截所有流量注入延迟/丢包 |
| **tc + netem** (Linux) | 内核级网络模拟 | 服务器端模拟（如限制出站带宽） |
| **Grafana + Prometheus** | 时序指标可视化 | 线上监控仪表板 |
| **ELK / Loki** | 日志聚合搜索 | 线上问题回溯 |

---

### 1.5 服务器监控

服务器监控的目标：**在玩家投诉之前发现问题**。

#### 1.5.1 关键指标

| 指标 | 采集方式 | 告警阈值参考 | 说明 |
|------|---------|-------------|------|
| **帧耗时 (FrameTime)** | 每逻辑帧记录 `delta = now - lastFrameStart` | 连续 5 帧 > 目标帧时间的 120% | 服务器过载的最直接指标 |
| **CPU 使用率** | OS 指标（`/proc/stat` 或 `GetProcessTimes`） | > 80% 持续 60s | 整体负载 |
| **内存使用** | OS 指标 / 进程 RSS | > 物理内存 85% 或 1 小时内增长 > 200MB | OOM 预警 |
| **活跃房间数** | 服务端 RoomManager 计数 | 距离上限 < 10 | 扩容预警 |
| **活跃玩家数** | 服务端连接计数 | 距离上限 < 100 | 扩容预警 |
| **断线率** | 异常断开连接数 / 总连接数 | > 5%/min | 网络问题或 crash |
| **逻辑帧掉帧率** | 实际执行帧数 / 理论应执行帧数 | < 95% | 严重过载 |
| **GC 耗时** (C# 服务端) | `GC.GetTotalPauseDuration()` | > 10ms/帧 持续 30s | GC 压力过大 |

#### 1.5.2 告警系统设计

告警系统遵循"发现 → 分级 → 通知 → 自动处理"的流水线：

```
指标采集 (每 5s) ──► 规则评估 ──► 告警触发
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                  P0 严重         P1 警告         P2 信息
                (立即电话)      (5min内响应)     (记录即可)
                    │               │               │
                    ▼               ▼               ▼
              自动处理:         发送到:          写入日志
              - 踢出最卡玩家   - 企业微信/Discord  - ELK
              - 迁移房间        - PagerDuty        - 指标系统
              - 限流新连接
```

**告警规则示例**：

```yaml
# 告警规则配置（概念示例）
alerts:
  - name: high_frame_time
    condition: frame_time_ms > 20  # 目标 16.6ms，超过 20ms 预警
    duration: 30s                  # 持续 30s 才触发（防止瞬时抖动）
    severity: P1
    message: "DS {host}:{pid} 帧耗时 {value}ms，持续 {duration}s"

  - name: abnormal_disconnect_rate
    condition: disconnect_rate > 0.05  # 5% 异常断线
    duration: 60s
    severity: P0
    auto_action: migrate_rooms

  - name: memory_leak_suspected
    condition: memory_growth_rate > 100MB/hour  # 每小时增长超 100MB
    duration: 3600s  # 1 小时
    severity: P1
    message: "DS {host}:{pid} 疑似内存泄漏，1h 增长 {value}MB"
```

#### 1.5.3 结构化日志系统

日志是可观测性的基石。设计要点：

**必带字段**：

```json
{
  "ts": "2026-06-02T10:30:45.123Z",  // ISO 8601 时间戳
  "host": "ds-shanghai-03",          // 机器标识
  "pid": 12345,                       // 进程 ID
  "room_id": "room_b3f2_170842",     // 房间 ID（用于关联）
  "frame": 38472,                     // 逻辑帧号
  "level": "INFO",                    // 日志级别
  "module": "FrameServer",            // 模块名
  "msg": "Broadcast frame completed", // 人类可读
  "duration_ms": 2.3,                 // 操作耗时
  "player_count": 8,                  // 上下文数据
  "payload_bytes": 426
}
```

**关键设计决策——FrameNo + RoomID 作为关联键**：

当你在 ELK 中搜索 `room_id:"room_b3f2_170842" AND frame:38472` 时，你能看到：
- 这一帧服务端收到了哪些输入
- 这一帧执行了什么逻辑
- 这一帧发送了哪些数据给客户端
- 每个步骤花了多少时间

这就是**全链路追踪**在游戏服务器中的等价实现。

---

### 1.6 测试策略

#### 1.6.1 网络模拟注入

在开发环境中模拟各种网络条件，是防止"在我机器上没问题"的核心手段。

**延迟模型**：

```
真实网络不是均匀延迟，而是：

延迟 = 基础延迟 + 抖动(jitter) + 突发延迟(burst)

基础延迟: 光纤/路由器的固定开销，如 30ms
抖动:     ±10ms 范围内的随机波动（WiFi 尤其明显）
突发延迟: 每 30 秒可能有一次 200ms 的 spike（如 4G 信号切换）
```

**丢包模型**：
- **随机丢包**：`random() < loss_rate` 丢弃
- **突发丢包**：一旦开始丢包，连续丢弃 2-8 个包（模拟 WiFi 干扰）
- **Gilbert-Elliott 模型**：两个状态的马尔可夫链——"好状态"低丢包率，"坏状态"高丢包率，模拟真实链路的突发性

**带宽限制**：
- 出站带宽上限（模拟 3G/4G 上行限制）
- 入站带宽上限

#### 1.6.2 自动化回放测试

**CI 中的回放测试流水线**：

```
┌─────────────────────────────────────────────────────┐
│              自动化回放测试流程                        │
│                                                     │
│  ① 收集线上录像（或手动录制的测试录像）                │
│     ↓                                               │
│  ② 存储到录像仓库（按版本/地图/模式分类）              │
│     ↓                                               │
│  ③ CI 每次提交触发：                                 │
│     ├─ 用新版本代码编译 DS                           │
│     ├─ 对每局录像执行重放                             │
│     ├─ 逐帧 Hash 与基准 Hash 比对                    │
│     ├─ 全部通过 → 允许合并                            │
│     └─ 任何失败 → 阻止合并 + 报告差异帧               │
│     ↓                                               │
│  ④ 定期（如每周）全量回归：用全部录像库（数千局）重放   │
└─────────────────────────────────────────────────────┘
```

**关键指标**：
- 回放通过率：`passed_replays / total_replays`
- 首次 Desync 帧分布：大部分 desync 发生在哪段时间（开局？中期？）
- 新增 Desync：本次提交是否引入了新的 Desync

#### 1.6.3 混沌工程

在生产环境或预发布环境中**主动注入故障**，验证系统的容错能力：

| 混沌实验 | 注入方式 | 预期行为 | 观测指标 |
|---------|---------|---------|---------|
| **随机断开玩家连接** | 服务端主动关闭某玩家 socket | 其他玩家继续正常游戏；断线玩家可通过重连恢复 | 重连成功率、其他玩家延迟是否增加 |
| **服务端进程崩溃** | `kill -9` 随机 DS 进程 | DSA 检测到崩溃 → 迁移房间到其他 DS → 玩家重连 | 迁移耗时、玩家体验评分 |
| **网络分区** | iptables 阻断部分连接 | 分区内的玩家继续游戏；恢复后自动合并 | 合并后数据一致性 |
| **带宽拥塞** | tc 限制出站带宽至 100KB/s | 自动降级（降低 tickrate / 减少属性同步频率） | 降级触发时间、恢复时间 |
| **高延迟尖刺** | tc 注入周期性 500ms 延迟 | 帧同步客户端利用缓冲区吸收；状态同步客户端预测覆盖 | 缓冲消耗率、预测误差峰值 |
| **大规模丢包** | tc 30% 随机丢包 | FEC/重传恢复消息；丢包率过高时优雅降级 | 消息恢复率、客户端体验 |

**混沌工程的黄金法则**：先在预发布环境跑，再上生产。生产混沌实验必须在玩家低峰期进行，且有快速回滚能力。

---

## 2. 代码示例

### 2.1 C#：Desync 检测调试工具（Unity，~180 行）

```csharp
// ============================================
// DesyncDebugger.cs — 帧同步 Desync 检测与诊断工具
// ============================================
// 用途：
//   1. 每帧计算游戏状态 Hash 并上报
//   2. 服务端比对各客户端 Hash → 发现不一致时触发诊断
//   3. 客户端保存诊断数据（快照 + 输入历史）
//   4. 支持二分法定位问题帧（服务端重放用）
// 依赖：UnityEngine, System.Security.Cryptography, System.IO
// ============================================

using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

namespace LockstepDebug
{
    #region 数据结构

    /// <summary>
    /// 哈希报告：客户端每 N 帧上报给服务端的状态指纹。
    /// </summary>
    [Serializable]
    public struct HashReport
    {
        public uint frameNumber;        // 逻辑帧号
        public string hashValue;        // Hash 值（16 进制字符串）
        public int playerCount;         // 当前玩家数
        public int entityCount;         // 当前实体数
    }

    /// <summary>
    /// 帧日志条目：记录每帧的关键信息，用于 desync 后回溯。
    /// 使用 struct 而非 class 减少 GC 分配——帧日志是热点路径。
    /// </summary>
    [Serializable]
    public struct FrameLogEntry
    {
        public uint frame;
        public long timestampMs;        // 墙钟时间戳
        public byte[] inputData;        // 本帧所有玩家的输入（序列化后）
        public string stateHash;        // 本帧状态 Hash
    }

    /// <summary>
    /// 诊断数据文件：desync 发生时保存到磁盘。
    /// 包含完整快照和输入历史，可直接交给开发人员复现。
    /// </summary>
    [Serializable]
    public class DiagnosticDump
    {
        public string roomId;
        public int playerId;
        public uint desyncFrame;
        public uint lastGoodFrame;
        public string desyncHash;               // desync 帧的 Hash
        public string expectedHash;             // 服务端期望的 Hash
        public byte[] snapshotData;             // 最近一次一致帧的完整状态快照
        public List<FrameLogEntry> inputHistory; // 从 lastGoodFrame 到 desyncFrame 的输入历史
        public string gameVersion;              // 用于确认版本一致性
        public string platformInfo;             // OS / 设备信息
    }

    #endregion

    #region Hash 计算器

    /// <summary>
    /// 游戏状态 Hash 计算器。
    /// 核心要求：序列化顺序必须是确定性的（遍历前先排序）。
    /// </summary>
    public static class StateHasher
    {
        /// <summary>
        /// 计算游戏状态的 MD5 Hash。
        /// 只序列化逻辑相关字段（定点数原始值、HP、状态位），
        /// 跳过渲染专用字段（动画帧、插值 alpha、粒子状态）。
        /// </summary>
        public static string ComputeHash(GameState state)
        {
            using var md5 = MD5.Create();
            using var ms = new MemoryStream(4096); // 预估大小，减少扩容
            using var writer = new BinaryWriter(ms, Encoding.UTF8);

            // 步骤 1：按实体 ID 升序写入，保证遍历顺序确定性
            var sortedIds = new List<uint>(state.entities.Keys);
            sortedIds.Sort(); // 关键！不排序的话 Dictionary 遍历顺序不确定 → Hash 不同却非 desync

            // 步骤 2：逐实体写入逻辑状态字段
            writer.Write((uint)sortedIds.Count); // 实体总数（用于检测实体数量不一致）
            foreach (var id in sortedIds)
            {
                var e = state.entities[id];
                writer.Write(id);
                writer.Write(e.posX.RawValue);   // 定点数原始值（long）
                writer.Write(e.posY.RawValue);
                writer.Write(e.posZ.RawValue);
                writer.Write(e.hp);
                writer.Write(e.stateFlags);       // 状态位掩码
                writer.Write(e.facing);            // 朝向（0-255 整数）
                // 注意：不写入 velocity（可由位置差分推导，且可能与浮点相关）
                // 注意：不写入 animationFrame（渲染专用）
            }

            // 步骤 3：写入全局状态
            writer.Write(state.randomSeed);       // 当前随机种子
            writer.Write(state.frameNumber);      // 帧号（冗余校验）

            writer.Flush();
            byte[] hashBytes = md5.ComputeHash(ms.ToArray());
            return BitConverter.ToString(hashBytes).Replace("-", "");
        }
    }

    #endregion

    #region Desync 检测器（客户端侧）

    /// <summary>
    /// DesyncDetector 挂载在每个客户端上。
    /// 每 N 帧计算 Hash 并上报服务端，同时维护快照和输入历史。
    /// </summary>
    public class DesyncDetector : MonoBehaviour
    {
        [Header("配置")]
        [SerializeField] int _hashInterval = 30;        // 每 30 帧上报一次 Hash
        [SerializeField] int _inputHistorySize = 600;   // 保存最近 600 帧输入（10 秒 @60fps）
        [SerializeField] int _checkpointInterval = 300; // 每 300 帧保存完整快照

        // 运行时状态
        private uint _lastGoodFrame;                     // 最近一次验证通过的帧号
        private byte[] _lastGoodSnapshot;                // 该帧的完整快照
        private Queue<FrameLogEntry> _inputHistory;       // 环形输入历史
        private string _roomId;
        private int _playerId;

        // 统计
        public int DesyncCount { get; private set; }
        public float LastHashComputeMs { get; private set; }

        void Awake()
        {
            _inputHistory = new Queue<FrameLogEntry>(_inputHistorySize);
        }

        /// <summary>
        /// 每逻辑帧结束后调用。
        /// </summary>
        /// <param name="frame">当前逻辑帧号</param>
        /// <param name="state">完整游戏状态</param>
        /// <param name="serializedInputs">本帧所有玩家的输入（已序列化）</param>
        public void OnFrameComplete(uint frame, GameState state, byte[] serializedInputs)
        {
            // ---- 记录帧日志 ----
            var entry = new FrameLogEntry
            {
                frame = frame,
                timestampMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                inputData = serializedInputs,
                stateHash = null // 等 Hash 计算完再填充
            };

            _inputHistory.Enqueue(entry);
            while (_inputHistory.Count > _inputHistorySize)
                _inputHistory.Dequeue(); // 环形淘汰

            // ---- 每 N 帧计算并上报 Hash ----
            if (frame % (uint)_hashInterval == 0 && frame > 0)
            {
                var sw = System.Diagnostics.Stopwatch.StartNew();
                string hash = StateHasher.ComputeHash(state);
                LastHashComputeMs = sw.ElapsedMilliseconds;

                // 更新日志条目中的 Hash
                var arr = _inputHistory.ToArray();
                for (int i = arr.Length - 1; i >= 0; i--)
                {
                    if (arr[i].frame == frame)
                    {
                        arr[i].stateHash = hash;
                        break;
                    }
                }

                // 上报到服务端
                SendHashReport(frame, hash, state);

                // 保存快照（用于 desync 后的回滚起点）
                if (frame % (uint)_checkpointInterval == 0)
                {
                    _lastGoodFrame = frame;
                    _lastGoodSnapshot = SerializeFullSnapshot(state);
                }
            }
        }

        private void SendHashReport(uint frame, string hash, GameState state)
        {
            var report = new HashReport
            {
                frameNumber = frame,
                hashValue = hash,
                playerCount = state.playerCount,
                entityCount = state.entities.Count
            };
            // 实际发送到服务端...（此处省略网络层代码）
            NetworkSender.SendHashReport(report);
        }

        /// <summary>
        /// 服务端通知：检测到 Desync（你的 Hash 和其他人不一致）。
        /// </summary>
        public void OnDesyncDetected(uint desyncFrame, string expectedHash)
        {
            DesyncCount++;
            string localHash = "";
            foreach (var e in _inputHistory)
                if (e.frame == desyncFrame) { localHash = e.stateHash; break; }

            Debug.LogError($"[DESYNC] 帧 {desyncFrame} 不一致！本地={localHash}, 期望={expectedHash}, " +
                           $"lastGood={_lastGoodFrame}");

            // ---- 保存诊断文件 ----
            SaveDiagnosticDump(desyncFrame, expectedHash);
        }

        /// <summary>
        /// 将诊断数据序列化到本地文件。
        /// 文件路径: {persistentDataPath}/diagnostics/{roomId}_{playerId}_f{frame}.diag
        /// </summary>
        private void SaveDiagnosticDump(uint desyncFrame, string expectedHash)
        {
            var dump = new DiagnosticDump
            {
                roomId = _roomId,
                playerId = _playerId,
                desyncFrame = desyncFrame,
                lastGoodFrame = _lastGoodFrame,
                desyncHash = "", // 从 inputHistory 中取
                expectedHash = expectedHash,
                snapshotData = _lastGoodSnapshot,
                inputHistory = new List<FrameLogEntry>(_inputHistory),
                gameVersion = Application.version,
                platformInfo = $"{SystemInfo.operatingSystem} | {SystemInfo.deviceModel}"
            };

            // 填 desyncHash
            foreach (var e in _inputHistory)
                if (e.frame == desyncFrame) { dump.desyncHash = e.stateHash; break; }

            // 序列化为 JSON（可读性好，方便跨平台分析）
            string json = JsonUtility.ToJson(dump, true);
            string dir = Path.Combine(Application.persistentDataPath, "diagnostics");
            Directory.CreateDirectory(dir);
            string path = Path.Combine(dir, $"{_roomId}_{_playerId}_f{desyncFrame}.diag");
            File.WriteAllText(path, json);

            Debug.Log($"[DESYNC] 诊断文件已保存: {path} ({json.Length / 1024}KB)");
        }

        /// <summary>
        /// 序列化完整游戏状态到字节数组（用于快照）。
        /// </summary>
        private byte[] SerializeFullSnapshot(GameState state)
        {
            // 实际实现参考第 03 节（序列化协议）和第 12 节（快照校验）
            // 这里用 JSON 简化演示
            return Encoding.UTF8.GetBytes(JsonUtility.ToJson(state));
        }

        // ---- 编辑器可视化 ----
        void OnGUI()
        {
            if (!Debug.isDebugBuild) return;
            GUILayout.BeginArea(new Rect(10, 250, 300, 150));
            GUILayout.Label($"帧同步调试 | Desync 次数: {DesyncCount}");
            GUILayout.Label($"最近一次 Hash 计算: {LastHashComputeMs:F2}ms");
            GUILayout.Label($"输入历史缓冲: {_inputHistory.Count}/{_inputHistorySize}");
            GUILayout.Label($"最近一致帧: {_lastGoodFrame}");
            if (GUILayout.Button("手动导出诊断"))
                SaveDiagnosticDump(0, "manual");
            GUILayout.EndArea();
        }
    }

    #endregion

    #region 二分定位器（服务端重放用）

    /// <summary>
    /// DesyncBinarySearcher 在服务端使用。
    /// 当检测到 Desync 后，使用二分法定位问题帧。
    /// </summary>
    public static class DesyncBinarySearcher
    {
        /// <summary>
        /// 二分查找 Desync 起始帧。
        /// </summary>
        /// <param name="inputHistory">从 lastGoodFrame 到 desyncFrame 的输入序列</param>
        /// <param name="lastGoodFrame">已知一致的帧号</param>
        /// <param name="desyncFrame">已知不一致的帧号</param>
        /// <param name="referenceHashes">参考 Hash 列表（通常来自"正确"的客户端）</param>
        /// <param name="replayFunc">重放函数：(fromFrame, toFrame, inputs) → 每帧 Hash 的字典</param>
        /// <returns>首次出现 Hash 不一致的帧号</returns>
        public static uint FindDesyncFrame(
            List<FrameLogEntry> inputHistory,
            uint lastGoodFrame,
            uint desyncFrame,
            Dictionary<uint, string> referenceHashes,
            Func<uint, uint, List<FrameLogEntry>, Dictionary<uint, string>> replayFunc)
        {
            uint left = lastGoodFrame + 1;
            uint right = desyncFrame;
            uint result = desyncFrame; // 默认值

            int iterations = 0;
            const int MAX_ITERATIONS = 20; // 安全上限

            while (left <= right && iterations < MAX_ITERATIONS)
            {
                iterations++;
                uint mid = (left + right) / 2;

                // 重放 [lastGoodFrame, mid] 区间，获取每帧的 Hash
                var hashes = replayFunc(lastGoodFrame, mid, inputHistory);

                // 检查 mid 帧的 Hash 是否与参考一致
                if (hashes.TryGetValue(mid, out string midHash) &&
                    referenceHashes.TryGetValue(mid, out string refHash) &&
                    midHash == refHash)
                {
                    // mid 帧一致 → desync 在 mid 之后
                    left = mid + 1;
                }
                else
                {
                    // mid 帧不一致 → desync 在 mid 或之前
                    result = mid;
                    right = mid - 1;
                }
            }

            return result;
        }
    }

    #endregion
}
```

---

### 2.2 C#：网络模拟器（延迟 + 丢包注入）（Unity，~130 行）

```csharp
// ============================================
// NetworkSimulator.cs — 网络条件模拟器
// ============================================
// 用途：
//   1. 在开发/测试环境中模拟各种网络条件
//   2. 支持延迟、抖动、丢包（随机/突发）、带宽限制
//   3. 可实时调整参数（通过 Unity Inspector 或代码）
//   4. 基于 Gilbert-Elliott 模型的真实丢包模式
// 集成方式：在你的网络层 send/recv 之前插入此模拟器
// ============================================

using System;
using System.Collections.Generic;
using UnityEngine;
using Random = System.Random;

namespace NetworkSimulation
{
    /// <summary>
    /// 网络条件配置（可在 Inspector 中调整）。
    /// </summary>
    [Serializable]
    public struct NetworkCondition
    {
        [Header("延迟 (ms)")]
        [Tooltip("基础延迟（双向总延迟的一半，即单向延迟）")]
        [Range(0, 1000)] public int baseLatencyMs;

        [Tooltip("抖动范围（±值），实际延迟 = base ± Random.Range(0, jitter)")]
        [Range(0, 500)] public int jitterMs;

        [Header("丢包")]
        [Tooltip("随机丢包率 (0.0 ~ 1.0)")]
        [Range(0f, 1f)] public float lossRate;

        [Tooltip("突发丢包：一旦丢包，额外连续丢弃的最大数量")]
        [Range(0, 20)] public int burstLossMax;

        [Tooltip("突发丢包的概率（每次随机丢包时，有 burstProbability 的几率触发突发）")]
        [Range(0f, 1f)] public float burstProbability;

        [Header("带宽限制")]
        [Tooltip("出站带宽上限 (KB/s)，0 表示不限")]
        [Range(0, 10000)] public int outboundBandwidthKBps;

        [Tooltip("入站带宽上限 (KB/s)，0 表示不限")]
        [Range(0, 10000)] public int inboundBandwidthKBps;

        // 预设
        public static NetworkCondition Good => new()
        {
            baseLatencyMs = 20, jitterMs = 5, lossRate = 0f, burstLossMax = 0,
            burstProbability = 0f, outboundBandwidthKBps = 0, inboundBandwidthKBps = 0
        };

        public static NetworkCondition Average => new()
        {
            baseLatencyMs = 50, jitterMs = 20, lossRate = 0.02f, burstLossMax = 3,
            burstProbability = 0.1f, outboundBandwidthKBps = 1000, inboundBandwidthKBps = 2000
        };

        public static NetworkCondition Poor => new()
        {
            baseLatencyMs = 150, jitterMs = 80, lossRate = 0.08f, burstLossMax = 8,
            burstProbability = 0.4f, outboundBandwidthKBps = 200, inboundBandwidthKBps = 500
        };

        public static NetworkCondition Terrible => new()
        {
            baseLatencyMs = 300, jitterMs = 200, lossRate = 0.15f, burstLossMax = 15,
            burstProbability = 0.7f, outboundBandwidthKBps = 50, inboundBandwidthKBps = 100
        };
    }

    /// <summary>
    /// 模拟数据包：在发送队列中排队。
    /// </summary>
    struct SimulatedPacket
    {
        public byte[] data;
        public long deliverAtMs;        // 计划送达的墙钟时间 (ms)
        public int destinationPlayerId; // 目标玩家（-1 表示广播）
    }

    /// <summary>
    /// NetworkSimulator 是一个中间层，放在实际网络层之上。
    ///
    /// 使用方式：
    ///   var simulator = new NetworkSimulator();
    ///   simulator.SetCondition(NetworkCondition.Average);
    ///
    ///   发送：simulator.Send(data, playerId); // 不会立即发送，会排队
    ///   每帧：simulator.Update();             // 处理到期的包并实际发送
    ///
    /// 设计要点：
    ///   - 延迟通过"计划送达时间"实现，而非 sleep。不阻塞主线程。
    ///   - 丢包在发送时立即决定（因为决定后就可以丢弃，不需要排队）。
    ///   - 突发丢包通过计数器追踪：进入突发模式 → 连续丢弃 burstLossMax 个包。
    /// </summary>
    public class NetworkSimulator
    {
        // 配置
        private NetworkCondition _condition;
        private Random _random = new Random();

        // 丢包状态机
        private bool _inBurstMode;          // 是否处于突发丢包模式
        private int _burstRemaining;         // 剩余突发丢包数

        // 带宽控制（滑动窗口）
        private Queue<long> _recentOutboundBytes = new();  // 最近 1 秒内发送的字节数
        private Queue<long> _recentInboundBytes = new();

        // 延迟队列（按 deliverAtMs 排序的待发送包）
        private List<SimulatedPacket> _outboundQueue = new();
        private List<SimulatedPacket> _inboundQueue = new();

        // 统计
        public long TotalPacketsSent { get; private set; }
        public long TotalPacketsDropped { get; private set; }
        public long TotalPacketsDelayed { get; private set; }
        public float CurrentLossRate => TotalPacketsSent > 0
            ? (float)TotalPacketsDropped / TotalPacketsSent : 0f;

        // 外部注入的实际网络发送回调
        private Action<byte[], int> _actualSendCallback;

        public NetworkSimulator(Action<byte[], int> actualSendCallback)
        {
            _actualSendCallback = actualSendCallback;
        }

        public void SetCondition(NetworkCondition condition)
        {
            _condition = condition;
            _inBurstMode = false;
            _burstRemaining = 0;
        }

        /// <summary>
        /// 发送数据包（模拟器入口）。
        /// </summary>
        /// <param name="data">要发送的数据</param>
        /// <param name="playerId">目标玩家 ID，-1 表示广播</param>
        public void Send(byte[] data, int playerId)
        {
            TotalPacketsSent++;

            // ---- 步骤 1：丢包判定 ----
            if (ShouldDrop())
            {
                TotalPacketsDropped++;
                return;
            }

            // ---- 步骤 2：带宽限制判定 ----
            if (!HasBandwidthAvailable(data.Length, isOutbound: true))
            {
                // 超出带宽上限 → 丢弃（或可改为排队，取决于策略）
                TotalPacketsDropped++;
                return;
            }

            // ---- 步骤 3：计算延迟并加入队列 ----
            long nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            int latencyMs = _condition.baseLatencyMs +
                            _random.Next(-_condition.jitterMs, _condition.jitterMs + 1);
            if (latencyMs < 0) latencyMs = 0;

            _outboundQueue.Add(new SimulatedPacket
            {
                data = data,
                deliverAtMs = nowMs + latencyMs,
                destinationPlayerId = playerId
            });
        }

        /// <summary>
        /// 每帧调用：处理到期包的实际发送。
        /// </summary>
        public void Update()
        {
            long nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

            // 处理出站队列
            for (int i = _outboundQueue.Count - 1; i >= 0; i--)
            {
                if (_outboundQueue[i].deliverAtMs <= nowMs)
                {
                    var pkt = _outboundQueue[i];
                    _actualSendCallback(pkt.data, pkt.destinationPlayerId);
                    _outboundQueue.RemoveAt(i);
                }
            }

            // 清理带宽窗口（淘汰 1 秒前的记录）
            long cutoff = nowMs - 1000;
            while (_recentOutboundBytes.Count > 0 && _recentOutboundBytes.Peek() < cutoff)
                _recentOutboundBytes.Dequeue();
        }

        /// <summary>
        /// 丢包判定（支持随机 + 突发模式）。
        /// </summary>
        private bool ShouldDrop()
        {
            if (_condition.lossRate <= 0f) return false;

            // 突发模式：继续丢弃
            if (_inBurstMode && _burstRemaining > 0)
            {
                _burstRemaining--;
                if (_burstRemaining == 0) _inBurstMode = false;
                return true;
            }

            // 随机丢包判定
            if (_random.NextDouble() < _condition.lossRate)
            {
                // 是否触发突发？
                if (_random.NextDouble() < _condition.burstProbability && _condition.burstLossMax > 0)
                {
                    _inBurstMode = true;
                    _burstRemaining = _random.Next(1, _condition.burstLossMax + 1) - 1; // -1 因为当前包算一个
                }
                return true;
            }

            return false;
        }

        /// <summary>
        /// 带宽检查（滑动窗口限流）。
        /// </summary>
        private bool HasBandwidthAvailable(int dataLength, bool isOutbound)
        {
            int limitKBps = isOutbound ? _condition.outboundBandwidthKBps : _condition.inboundBandwidthKBps;
            if (limitKBps <= 0) return true; // 不限

            var queue = isOutbound ? _recentOutboundBytes : _recentInboundBytes;
            long nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

            // 清理 1 秒前的记录
            long cutoff = nowMs - 1000;
            while (queue.Count > 0 && queue.Peek() < cutoff)
                queue.Dequeue();

            // 计算当前窗口的累计字节数
            long totalBytes = 0;
            foreach (var ts in queue) totalBytes += ts; // 这里简化：我们存的是 timestamp 和 size 的对

            // 注意：上面代码简化了，实际应该存 (timestamp, size) 对。
            // 这里的简化版本只用于概念说明。
            // 生产实现见下文"改进版带宽控制"。

            return true; // 简化
        }

        // ---- 预设快捷方法 ----
        public void SimulateGood() => SetCondition(NetworkCondition.Good);
        public void SimulateAverage() => SetCondition(NetworkCondition.Average);
        public void SimulatePoor() => SetCondition(NetworkCondition.Poor);
        public void SimulateTerrible() => SetCondition(NetworkCondition.Terrible);
    }

    /// <summary>
    /// Unity MonoBehaviour 包装器，提供 Inspector 面板。
    /// 挂在场景中的空 GameObject 上即可使用。
    /// </summary>
    public class NetworkSimulatorUI : MonoBehaviour
    {
        public NetworkCondition currentCondition = NetworkCondition.Average;
        [SerializeField] private bool _autoApplyToNetworkManager = true;

        private NetworkSimulator _simulator;

        void Start()
        {
            // 创建模拟器并注入实际网络层
            _simulator = new NetworkSimulator((data, playerId) =>
            {
                // 调用真实的网络发送函数
                // NetworkManager.Instance.SendRaw(data, playerId);
            });
            _simulator.SetCondition(currentCondition);
        }

        void Update()
        {
            _simulator?.Update();
        }

        void OnGUI()
        {
            if (_simulator == null) return;
            GUILayout.BeginArea(new Rect(10, 10, 280, 180));
            GUILayout.Label("=== 网络模拟器 ===");
            GUILayout.Label($"发送: {_simulator.TotalPacketsSent} | 丢弃: {_simulator.TotalPacketsDropped}");
            GUILayout.Label($"丢包率: {_simulator.CurrentLossRate:P2}");
            GUILayout.Label($"延迟: {currentCondition.baseLatencyMs}ms ± {currentCondition.jitterMs}ms");

            GUILayout.BeginHorizontal();
            if (GUILayout.Button("优")) _simulator.SimulateGood();
            if (GUILayout.Button("中")) _simulator.SimulateAverage();
            if (GUILayout.Button("差")) _simulator.SimulatePoor();
            if (GUILayout.Button("极差")) _simulator.SimulateTerrible();
            GUILayout.EndHorizontal();
            GUILayout.EndArea();
        }
    }
}
```

---

### 2.3 C++：帧日志系统（~120 行）

```cpp
// ============================================
// frame_logger.h — 高性能帧日志系统 (C++ 服务端)
// ============================================
// 用途：
//   1. 以最小开销记录每逻辑帧的关键事件
//   2. 环形内存缓冲区 → 异步写入磁盘（不阻塞逻辑帧）
//   3. 结构化输出：JSON Lines 格式（每行一条 JSON，方便 ELK 采集）
//   4. 支持按房间号/帧号过滤查询
//
// 设计要点：
//   - 使用无锁环形缓冲区（SPSC: 单生产者单消费者）
//   - 生产者（逻辑线程）只写内存，消费者（IO 线程）异步写磁盘
//   - 帧号 + 房间号作为每条日志的必带字段
//   - 零分配热路径：预分配 buffer，snprintf 直接写入
// ============================================

#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <atomic>
#include <thread>
#include <vector>
#include <string>
#include <chrono>

namespace FrameLogger {

// ============================================
// 配置常量
// ============================================
constexpr size_t BUFFER_SIZE     = 8 * 1024 * 1024; // 8MB 环形缓冲区
constexpr size_t MAX_ENTRY_SIZE  = 512;              // 单条日志最大字节
constexpr size_t MAX_ENTRIES     = BUFFER_SIZE / MAX_ENTRY_SIZE; // ~16384 条
constexpr int    FLUSH_INTERVAL_MS = 1000;           // 每秒 flush 一次

// ============================================
// 日志条目（固定大小，避免动态分配）
// ============================================
struct alignas(64) LogEntry {  // 64 字节对齐避免 false sharing
    uint64_t timestamp_ms;        // 墙钟时间戳 (ms)
    uint32_t frame_no;            // 逻辑帧号
    uint32_t room_id_hash;        // 房间 ID 的 hash（节省空间）
    uint16_t data_len;            // 实际数据长度
    uint8_t  level;               // 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR
    uint8_t  reserved;
    char     data[MAX_ENTRY_SIZE - 24]; // 剩余的用于日志内容
};
static_assert(sizeof(LogEntry) == MAX_ENTRY_SIZE, "LogEntry size mismatch");

// ============================================
// 无锁环形缓冲区 (SPSC)
// ============================================
class RingBuffer {
public:
    RingBuffer()
        : _write_pos(0), _read_pos(0)
    {
        _entries.resize(MAX_ENTRIES);
    }

    // 生产者：写入一条日志。环形满时覆盖最老的条目（不会阻塞）。
    // 返回 true 表示写入成功。
    bool push(const LogEntry& entry) {
        size_t write = _write_pos.load(std::memory_order_relaxed);
        size_t next = (write + 1) % MAX_ENTRIES;

        // 如果写指针追上读指针 → 缓冲区满，覆盖最老条目
        if (next == _read_pos.load(std::memory_order_acquire)) {
            // 推进读指针一位（丢弃最老条目）
            _read_pos.store((_read_pos.load() + 1) % MAX_ENTRIES,
                           std::memory_order_release);
        }

        _entries[write] = entry;
        _write_pos.store(next, std::memory_order_release);
        return true;
    }

    // 消费者：读取一条日志。缓冲区空时返回 false。
    bool pop(LogEntry& out) {
        size_t read = _read_pos.load(std::memory_order_relaxed);
        if (read == _write_pos.load(std::memory_order_acquire)) {
            return false; // 缓冲区空
        }

        out = _entries[read];
        _read_pos.store((read + 1) % MAX_ENTRIES, std::memory_order_release);
        return true;
    }

    size_t available() const {
        size_t w = _write_pos.load(std::memory_order_acquire);
        size_t r = _read_pos.load(std::memory_order_acquire);
        if (w >= r) return w - r;
        return MAX_ENTRIES - r + w;
    }

private:
    std::vector<LogEntry> _entries;
    std::atomic<size_t>   _write_pos;
    std::atomic<size_t>   _read_pos;
};

// ============================================
// 帧日志器
// ============================================
class Logger {
public:
    Logger(const std::string& log_dir,
           const std::string& process_name,
           uint32_t           room_id)
        : _room_id(room_id)
        , _room_id_hash(std::hash<std::string>{}(
              std::to_string(room_id) + "_" + process_name))
        , _running(false)
    {
        // 构造日志文件路径: {log_dir}/{process_name}_room{id}_{date}.log
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        char date_buf[32];
        std::strftime(date_buf, sizeof(date_buf), "%Y%m%d_%H%M%S",
                      std::localtime(&time_t));

        _filepath = log_dir + "/" + process_name + "_room"
                  + std::to_string(room_id) + "_" + date_buf + ".log";

        // 打开文件（追加模式）
        _file = fopen(_filepath.c_str(), "ab");
    }

    ~Logger() {
        stop();
        if (_file) fclose(_file);
    }

    // ---- 热路径 API（线程安全，可在逻辑帧中调用） ----

    /// 写入一条结构化日志。
    /// @param frame  逻辑帧号
    /// @param level  日志级别
    /// @param format printf 风格格式串 + 参数
    template<typename... Args>
    void log(uint32_t frame, uint8_t level, const char* format, Args... args) {
        LogEntry entry{};
        entry.timestamp_ms = now_ms();
        entry.frame_no     = frame;
        entry.room_id_hash = _room_id_hash;
        entry.level        = level;

        // 使用 snprintf 直接写入 entry.data（零堆分配）
        int written = snprintf(entry.data, sizeof(entry.data),
                               format, args...);
        entry.data_len = static_cast<uint16_t>(
            written > 0 ? std::min(written, (int)sizeof(entry.data) - 1) : 0);

        _buffer.push(entry);
    }

    // 便捷方法
    void debug(uint32_t frame, const char* fmt, auto... args)  { log(frame, 0, fmt, args...); }
    void info(uint32_t frame, const char* fmt, auto... args)   { log(frame, 1, fmt, args...); }
    void warn(uint32_t frame, const char* fmt, auto... args)   { log(frame, 2, fmt, args...); }
    void error(uint32_t frame, const char* fmt, auto... args)  { log(frame, 3, fmt, args...); }

    // ---- 生命周期管理 ----

    /// 启动异步 IO 线程
    void start() {
        _running = true;
        _io_thread = std::thread(&Logger::io_loop, this);
    }

    /// 停止 IO 线程并 flush 剩余日志
    void stop() {
        _running = false;
        if (_io_thread.joinable()) {
            _io_thread.join();
        }
        flush_all();
    }

private:
    // ---- 异步 IO 线程 ----

    void io_loop() {
        auto last_flush = std::chrono::steady_clock::now();
        LogEntry entry;

        while (_running) {
            // 批量消费缓冲区
            int count = 0;
            while (_buffer.pop(entry) && count < 256) {
                write_entry(entry);
                count++;
            }

            // 定期 flush
            auto now = std::chrono::steady_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                now - last_flush).count();
            if (elapsed >= FLUSH_INTERVAL_MS) {
                fflush(_file);
                last_flush = now;
            }

            // 如果缓冲区为空，短暂休眠（减少 CPU 空转）
            if (count == 0) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        }
    }

    // 清空所有剩余日志
    void flush_all() {
        LogEntry entry;
        while (_buffer.pop(entry)) {
            write_entry(entry);
        }
        if (_file) fflush(_file);
    }

    // ---- 格式化输出 ----

    void write_entry(const LogEntry& entry) {
        if (!_file) return;

        // 输出 JSON Lines 格式：
        // {"ts":1234567890,"f":12345,"rid":"abc","l":"INFO","msg":"..."}
        static const char* level_names[] = {"DEBUG","INFO","WARN","ERROR"};

        // 转义 data 中的特殊字符（简化实现：只处理双引号和反斜杠）
        char escaped[sizeof(entry.data) * 2];
        const char* src = entry.data;
        char* dst = escaped;
        size_t len = entry.data_len;
        for (size_t i = 0; i < len && src[i]; i++) {
            switch (src[i]) {
                case '"':  *dst++ = '\\'; *dst++ = '"';  break;
                case '\\': *dst++ = '\\'; *dst++ = '\\'; break;
                case '\n': *dst++ = '\\'; *dst++ = 'n';  break;
                case '\r': *dst++ = '\\'; *dst++ = 'r';  break;
                case '\t': *dst++ = '\\'; *dst++ = 't';  break;
                default:   *dst++ = src[i]; break;
            }
        }
        *dst = '\0';

        fprintf(_file,
            "{\"ts\":%llu,\"f\":%u,\"rid\":\"%08x\",\"l\":\"%s\",\"msg\":\"%s\"}\n",
            (unsigned long long)entry.timestamp_ms,
            entry.frame_no,
            entry.room_id_hash,
            level_names[entry.level & 3],
            escaped);
    }

    // ---- 时间工具 ----

    static uint64_t now_ms() {
        auto now = std::chrono::system_clock::now();
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()).count();
    }

    // ---- 成员变量 ----

    uint32_t   _room_id;
    uint32_t   _room_id_hash;
    std::string _filepath;
    FILE*      _file;
    RingBuffer _buffer;
    std::thread _io_thread;
    std::atomic<bool> _running;
};

} // namespace FrameLogger

// ============================================
// 使用示例
// ============================================
//
// // 在 DS 初始化时：
// FrameLogger::Logger logger("./logs", "ds_shanghai_03", roomId);
// logger.start();
//
// // 在逻辑帧中（热点路径，无锁无分配）：
// void GameWorld::Tick(uint32_t frame, const Input* inputs) {
//     logger.info(frame, "Tick start, players=%d", playerCount);
//     // ... 执行游戏逻辑 ...
//     logger.info(frame, "Tick end, entities=%d, duration_us=%lld",
//                 entityCount, tickDurationUs);
// }
//
// // DS 关闭时：
// logger.stop();
// ============================================
```

---

### 2.4 Lua：调试面板（~100 行）

```lua
-- ============================================
-- debug_panel.lua — 运行时调试面板（Lua 层）
-- ============================================
-- 用途：
--   1. 在游戏屏幕上叠加半透明调试信息
--   2. 显示帧号、网络状态、实体信息、Desync 历史
--   3. 支持热键切换显示/隐藏、切换信息页
--   4. 纯 Lua 实现，不依赖特定引擎 UI 系统
--   （需要 C 层提供 debug_draw_text 和 debug_draw_rect 绑定）
-- ============================================

local DebugPanel = {}
DebugPanel.__index = DebugPanel

-- ─── 配置 ──────────────────────────────────────
local CONFIG = {
    visible = true,               -- 默认显示
    position = { x = 10, y = 10 }, -- 面板左上角 (像素)
    line_height = 18,              -- 每行高度
    max_lines = 30,                -- 最大显示行数
    font_size = 14,
    bg_alpha = 0.6,               -- 背景透明度
    fg_color = {1, 1, 1, 1},     -- 前景色 (RGBA)
    highlight_color = {1, 1, 0, 1}, -- 高亮色 (黄色)
    error_color = {1, 0, 0, 1},    -- 错误色 (红色)
    page = 1,                      -- 当前信息页
    max_pages = 3,                 -- 总页数
}

-- ─── 构造函数 ──────────────────────────────────

--- 创建调试面板
--- @param net_stats_func function 获取网络统计的函数 f() → {rtt, loss, jitter, sent, recv}
--- @param frame_info_func function 获取帧信息的函数 f() → {logical_frame, render_frame, buffer_size}
--- @param entity_stats_func function 获取实体统计的函数 f() → {count, selected_entity_info}
function DebugPanel.new(net_stats_func, frame_info_func, entity_stats_func)
    local self = setmetatable({}, DebugPanel)
    self._net_stats_fn = net_stats_func
    self._frame_info_fn = frame_info_func
    self._entity_stats_fn = entity_stats_func
    self._desync_history = {}    -- { {frame=N, localHash=..., remoteHash=...}, ... }
    self._last_rpc_logs = {}     -- 最近 RPC 记录（环形）
    self._rpc_log_capacity = 20
    self._shown = CONFIG.visible
    return self
end

-- ─── 公共 API ──────────────────────────────────

--- 记录一次 Desync 事件
function DebugPanel:record_desync(frame, local_hash, remote_hash)
    table.insert(self._desync_history, {
        frame = frame,
        local_hash = local_hash,
        remote_hash = remote_hash,
        time = os.time(),
    })
    -- 只保留最近 50 条
    if #self._desync_history > 50 then
        table.remove(self._desync_history, 1)
    end
end

--- 记录一次 RPC 调用
function DebugPanel:record_rpc(rpc_name, sender, target, size_bytes)
    table.insert(self._last_rpc_logs, {
        name = rpc_name,
        sender = sender,
        target = target,
        size = size_bytes,
        time = os.clock(),
    })
    if #self._last_rpc_logs > self._rpc_log_capacity then
        table.remove(self._last_rpc_logs, 1)
    end
end

--- 切换显示/隐藏（通常绑定到 F1 键）
function DebugPanel:toggle()
    self._shown = not self._shown
end

--- 切换信息页（通常绑定到 F2 键）
function DebugPanel:next_page()
    CONFIG.page = (CONFIG.page % CONFIG.max_pages) + 1
end

--- 每渲染帧调用：绘制调试面板
--- 由 C 层的渲染回调调用，或直接由 Lua update loop 调用
function DebugPanel:render()
    if not self._shown then return end

    local x, y = CONFIG.position.x, CONFIG.position.y
    local line_h = CONFIG.line_height
    local lines = {}

    -- ─── 标题 ──────────────────────────────────
    lines[#lines + 1] = {
        text = string.format("=== 调试面板 (第 %d/%d 页) [F1:隐藏 F2:换页] ===",
                            CONFIG.page, CONFIG.max_pages),
        color = CONFIG.fg_color,
    }

    if CONFIG.page == 1 then
        -- ─── 第 1 页：网络状态 ──────────────────
        self:_add_network_page(lines)
    elseif CONFIG.page == 2 then
        -- ─── 第 2 页：帧同步状态 ────────────────
        self:_add_lockstep_page(lines)
    elseif CONFIG.page == 3 then
        -- ─── 第 3 页：RPC 日志 ──────────────────
        self:_add_rpc_page(lines)
    end

    -- ─── 绘制背景 ──────────────────────────────
    local panel_width = 380
    local panel_height = #lines * line_h + 10
    engine.debug_draw_rect(x - 5, y - 5, panel_width, panel_height,
                           {0, 0, 0, CONFIG.bg_alpha})

    -- ─── 绘制文字 ──────────────────────────────
    for i, line_info in ipairs(lines) do
        local line_y = y + (i - 1) * line_h
        engine.debug_draw_text(x, line_y, line_info.text,
                               line_info.color or CONFIG.fg_color,
                               CONFIG.font_size)
    end
end

-- ─── 私有方法：各页面内容 ─────────────────────

function DebugPanel:_add_network_page(lines)
    local stats = self._net_stats_fn and self._net_stats_fn() or {}

    -- RTT 显示（带颜色指示）
    local rtt = stats.rtt or 0
    local rtt_color = CONFIG.fg_color
    if rtt > 200 then rtt_color = CONFIG.error_color
    elseif rtt > 100 then rtt_color = CONFIG.highlight_color end

    local rtt_bar = self:_make_bar(rtt, 500, 20)
    lines[#lines + 1] = {
        text = string.format("RTT: %s %dms", rtt_bar, rtt),
        color = rtt_color,
    }

    -- 丢包率
    local loss = stats.loss_rate or 0
    local loss_color = loss > 0.1 and CONFIG.error_color or
                       (loss > 0.03 and CONFIG.highlight_color or CONFIG.fg_color)
    lines[#lines + 1] = {
        text = string.format("丢包率: %.1f%%", loss * 100),
        color = loss_color,
    }

    -- 抖动
    local jitter = stats.jitter or 0
    lines[#lines + 1] = {
        text = string.format("抖动: %dms", jitter),
    }

    -- 带宽
    lines[#lines + 1] = {
        text = string.format("发送: %d KB/s | 接收: %d KB/s",
                            (stats.sent_bps or 0) / 1024,
                            (stats.recv_bps or 0) / 1024),
    }

    -- 收发包统计
    lines[#lines + 1] = {
        text = string.format("收包: %d | 发包: %d | 重传: %d",
                            stats.packets_recv or 0,
                            stats.packets_sent or 0,
                            stats.packets_retransmit or 0),
    }
end

function DebugPanel:_add_lockstep_page(lines)
    local frame_info = self._frame_info_fn and self._frame_info_fn() or {}
    local entity_info = self._entity_stats_fn and self._entity_stats_fn() or {}

    -- 帧号（逻辑 vs 渲染）
    local logical = frame_info.logical_frame or 0
    local render = frame_info.render_frame or 0
    lines[#lines + 1] = {
        text = string.format("逻辑帧: %d | 渲染帧: %d | 差值: %d",
                            logical, render, math.abs(logical - render)),
        color = math.abs(logical - render) > 3 and CONFIG.highlight_color
                or CONFIG.fg_color,
    }

    -- 帧缓冲状态
    local buffer_size = frame_info.buffer_size or 0
    local buffer_capacity = frame_info.buffer_capacity or 64
    local buffer_pct = buffer_size / buffer_capacity
    local buffer_bar = self:_make_bar(buffer_size, buffer_capacity, 15)
    local buffer_color = buffer_pct < 0.2 and CONFIG.error_color or
                         (buffer_pct > 0.8 and CONFIG.highlight_color or CONFIG.fg_color)
    lines[#lines + 1] = {
        text = string.format("帧缓冲: %s %d/%d", buffer_bar, buffer_size, buffer_capacity),
        color = buffer_color,
    }

    -- 实体统计
    lines[#lines + 1] = {
        text = string.format("实体: %d 个", entity_info.count or 0),
    }

    -- Desync 历史（最近 3 次）
    lines[#lines + 1] = { text = "--- Desync 历史 (最近3次) ---" }
    local start = math.max(1, #self._desync_history - 2)
    if #self._desync_history == 0 then
        lines[#lines + 1] = { text = "  (无)", color = {0.5, 0.5, 0.5, 1} }
    else
        for i = start, #self._desync_history do
            local d = self._desync_history[i]
            lines[#lines + 1] = {
                text = string.format("  帧 %d: 本地=%s... 远程=%s...",
                                    d.frame,
                                    string.sub(d.local_hash, 1, 8),
                                    string.sub(d.remote_hash, 1, 8)),
                color = CONFIG.error_color,
            }
        end
    end
end

function DebugPanel:_add_rpc_page(lines)
    lines[#lines + 1] = { text = string.format("--- RPC 日志 (最近 %d 条) ---",
                                               #self._last_rpc_logs) }
    if #self._last_rpc_logs == 0 then
        lines[#lines + 1] = { text = "  (无 RPC 记录)" }
        return
    end

    -- 从新到旧显示
    for i = #self._last_rpc_logs, 1, -1 do
        local rpc = self._last_rpc_logs[i]
        local age = os.clock() - rpc.time
        local age_color = age > 5 and {0.5, 0.5, 0.5, 1} or CONFIG.fg_color
        lines[#lines + 1] = {
            text = string.format("  [%.1fs前] %s: P%d→P%d (%dB)",
                                age, rpc.name, rpc.sender, rpc.target, rpc.size),
            color = age_color,
        }
    end
end

-- ─── 工具函数 ─────────────────────────────────

--- 生成 ASCII 进度条
--- @param value number 当前值
--- @param max_val number 最大值
--- @param width number 进度条字符宽度
function DebugPanel:_make_bar(value, max_val, width)
    if max_val == 0 then return string.rep("-", width) end
    local ratio = math.min(1.0, value / max_val)
    local filled = math.floor(ratio * width)
    return "[" .. string.rep("#", filled) .. string.rep("-", width - filled) .. "]"
end

-- ─── 返回模块 ──────────────────────────────────
return DebugPanel
```

---

## 3. 练习

### 练习 1：构建 Desync 检测闭环 [基础]

**目标**：在本地搭建一个完整的 Desync 检测 → 日志记录 → 可视化流程。

**要求**：

1. 基于第 08 节的锁步客户端 Demo（或第 12 节的快照校验 Demo），扩展以下功能：
   - 每 30 逻辑帧计算状态 Hash（使用 MD5）
   - 在本地模拟"假 Desync"：在某个随机帧故意修改一个实体的位置（模拟浮点误差），观察 Hash 是否会检测到
2. 当 Hash 不一致时：
   - 在屏幕上显示红色警告："[DESYNC] 帧 {N} 不一致！"
   - 将诊断数据（快照 + 输入历史）写入本地 JSON 文件
3. 使用 Lua 调试面板显示：
   - 当前帧号和最近一次 Hash 值
   - Desync 历史（最近 5 次）
4. 验证：故意注入 Desync → 观察检测结果 → 检查生成的诊断文件是否完整

**提示**：
- Hash 计算时务必按实体 ID 排序，否则遍历顺序不一致导致假阳性
- 使用 `System.Security.Cryptography.MD5`（C#）或 `require("md5")`（Lua 需要第三方库）
- 诊断文件用 JSON 格式（`JsonUtility.ToJson` / `JsonConvert.SerializeObject`），方便后续 Python 批量分析

---

### 练习 2：网络条件对比测试 [进阶]

**目标**：量化不同网络条件对同步质量的影响。

**要求**：

1. 使用第 2.2 节的 NetworkSimulator，或 UE 的 `net.PktLag` / `net.PktLoss` 命令，搭建一个可控的测试环境
2. 选择一个已有的同步 Demo（帧同步或状态同步均可），构建以下测试矩阵：

| 场景 | 延迟 | 抖动 | 丢包率 | 描述 |
|------|------|------|--------|------|
| A 理想 | 10ms | 2ms | 0% | LAN 环境 |
| B 好 | 30ms | 10ms | 1% | 优质 WiFi |
| C 中 | 80ms | 30ms | 3% | 4G 移动网络 |
| D 差 | 200ms | 80ms | 8% | 弱信号 |
| E 极差 | 400ms | 150ms | 15% | 电梯/地铁 |

3. 对每个场景运行 60 秒，自动记录以下指标：
   - 帧同步：缓冲消耗率（buffer drain rate）、Desync 次数
   - 状态同步：预测误差平均值/峰值、和解次数、RPC 延迟
4. 将结果导出为 CSV，用表格或图表对比
5. 分析：项目的目标网络条件是什么？当前实现在目标条件下表现如何？最差条件下可接受吗？

**提示**：
- 使用 `Time.realtimeSinceStartup` 或 `std::chrono` 做精确计时
- 如果要自动化，写一个 `TestRunner` 脚本：切换网络条件 → 运行 60s → 记录指标 → 切换下一个条件
- 在 UE 中，可以用 `NetEmulation.DefaultProfile.json` 定义网络模拟配置文件

---

### 练习 3：混沌工程——故障注入与恢复验证 [挑战]

**目标**：构建故障注入框架，验证同步系统的容错能力。

**要求**：

1. 实现一个 `ChaosMonkey` 类，支持以下故障注入：
   - **随机断连**：每 30 秒有 10% 概率断开一个随机客户端，5 秒后自动重连
   - **延迟尖刺**：每 60 秒有 20% 概率注入一次 500ms 延迟尖刺，持续 2 秒
   - **丢包爆发**：每 90 秒有 15% 概率注入 30% 丢包率，持续 3 秒
   - **服务端限速**：每 120 秒有 10% 概率将服务端出站带宽限制到 50KB/s，持续 5 秒
2. 在故障注入期间和之后，监控以下恢复指标：
   - 重连时间（从断连到恢复到正常游戏状态）
   - 帧缓冲恢复时间（缓冲从危险水位恢复到安全水位）
   - 预测误差峰值和恢复时间
3. 运行 10 分钟的混沌测试，记录所有指标，输出恢复成功率
4. 分析最弱的环节：
   - 哪种故障恢复最慢？
   - 哪些故障组合会导致不可恢复的状态？
5. （可选）将 ChaosMonkey 集成到 CI 中：每次提交后运行 5 分钟混沌测试，全部恢复才算通过

**提示**：
- 故障注入应在独立线程中运行，不阻塞游戏主循环
- 使用 `Coroutine` 或 `async/await` 管理故障的持续时间和恢复
- 记录每条故障事件的开始/结束时间戳，与监控指标做时间对齐
- 如果发现系统无法从某种故障中恢复，首先检查：重连逻辑是否正确重建了状态、缓冲区是否正确处理了过期数据

---

## 4. 扩展阅读

- **Valve: Source Multiplayer Networking**：[https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) — 包含 `cl_showpos`、`net_graph` 等调试工具的设计思想，业界调试工具的鼻祖
- **Overwatch Network Debugging (GDC 2017)**：[https://www.youtube.com/watch?v=W3aieHjyNvw](https://www.youtube.com/watch?v=W3aieHjyNvw) — 暴雪展示的"优先队列重传"可视化和调试面板，包含实际网络流量的回放分析
- **Unreal Engine Network Profiler Documentation**：[https://docs.unrealengine.com/en-US/TestingAndOptimization/PerformanceAndProfiling/NetworkProfiler/](https://docs.unrealengine.com/en-US/TestingAndOptimization/PerformanceAndProfiling/NetworkProfiler/) — UE 官方网络分析器文档
- **Gaffer On Games: Networked Physics**：[https://gafferongames.com/post/networked_physics_2004/](https://gafferongames.com/post/networked_physics_2004/) — 包含 RTT 分解和丢包模式分析
- **clumsy - Windows Network Simulator**：[https://github.com/jagt/clumsy](https://github.com/jagt/clumsy) — 开源 Windows 网络模拟工具，比 Unity/UE 内置模拟器更真实（系统级拦截）
- **tc-netem Linux Traffic Control**：[https://wiki.linuxfoundation.org/networking/netem](https://wiki.linuxfoundation.org/networking/netem) — Linux 内核级网络模拟，用于服务端测试
- **Wireshark Lua Dissector**：[https://wiki.wireshark.org/Lua/Dissectors](https://wiki.wireshark.org/Lua/Dissectors) — 可以自己写一个 Wireshark 协议解析器，用 Lua 脚本解析自定义协议，极大提升抓包分析效率
- **Prometheus + Grafana**：[https://prometheus.io/docs/](https://prometheus.io/docs/) — 服务端指标监控的事实标准
- **Netflix Chaos Monkey**：[https://github.com/Netflix/chaosmonkey](https://github.com/Netflix/chaosmonkey) — 混沌工程的开山之作，游戏服务器的混沌工程可以从中借鉴思路
- **Riot Games: League of Legends Determinism Testing**：[https://technology.riotgames.com/news/determinism-league-legends-fixing-divergences](https://technology.riotgames.com/news/determinism-league-legends-fixing-divergences) — Riot 如何检测和修复帧同步 desync 的实战经验

---

## 常见陷阱

### 陷阱 1：printf 调试代替结构化日志

**症状**：用 `Debug.Log` / `printf` / `print()` 到处打印，线上问题来了之后在几十 GB 的日志中 `grep` 关键字——关键字可能不匹配、日志格式不一致、时间戳格式混乱。

**正确做法**：从第一天就用结构化日志（JSON Lines）。每条日志带 `frame`、`room_id`、`timestamp`、`level`、`module` 六个必带字段。日志可以通过 `jq` 或 ELK 做结构化查询，而不是靠 `grep` 猜关键字。

### 陷阱 2：Hash 计算包含非确定性数据

**症状 A**：Hash 包含当前系统时间 → 每次计算结果不同，即使游戏状态完全一致。
**症状 B**：Hash 遍历容器时顺序不确定（如 Lua 的 `pairs()`、C# 的 `Dictionary` 无序遍历） → 同一状态的 Hash 有时相同有时不同。
**症状 C**：Hash 包含渲染相关数据（动画帧、插值 alpha） → 不同帧率/硬件产生不同 Hash，但逻辑完全一致。

**正确做法**：Hash 计算只包含**逻辑状态**数据，且必须按确定的顺序（如实体 ID 升序）序列化。C++ 用 `std::map`（有序），C# 用 `SortedDictionary` 或先 `.Keys.OrderBy()`。

### 陷阱 3：调试面板导致性能问题

**症状**：`OnGUI()` 中做了大量字符串拼接、字典遍历、反射查询 → 每帧 GC Alloc 数 MB → 帧率暴跌。

**正确做法**：
- 调试面板的字符串每 0.5 秒更新一次（而非每渲染帧），用 `Time.frameCount % 30 == 0` 控制
- 预分配 `StringBuilder`，复用
- 在 Release 构建中完全移除 `OnGUI` 调用（用 `#if UNITY_EDITOR || DEVELOPMENT_BUILD`）
- 热路径的指标采集使用无分配的计数器（如 `Interlocked.Increment`）

### 陷阱 4：在逻辑帧中直接写磁盘

**症状**：Desync 发生时在 `FixedUpdate` 中执行 `File.WriteAllText` → 磁盘 IO 耗时 50ms → 逻辑帧超时 → 连锁反应导致更多帧超时。

**正确做法**：诊断数据的写入必须在**独立线程**或**下一帧的时间片**中执行。逻辑帧只负责把数据拷贝到一个缓冲区（内存操作，< 0.1ms），后台线程负责写入磁盘。C++ 示例中的 `RingBuffer + io_thread` 就是这个模式。

### 陷阱 5：告警阈值拍脑袋，不做基线

**症状**：上线第一天设了"帧耗时 > 16.6ms 告警" → 每天收到 5000 条告警 → 所有人麻木 → 真正的故障被淹没。

**正确做法**：
- 先用一周时间采集**基线数据**（正常情况下的指标分布）
- 告警阈值设置为基线的 **P99 值 × 2** 或 **平均值 + 3σ**
- 告警必须带 `duration`（持续时间），过滤瞬时抖动
- 告警分级：P0（立即响应）、P1（5 分钟内）、P2（仅记录）
- 定期回顾告警质量：误报率、漏报率

### 陷阱 6：网络模拟只在"好条件"下测试

**症状**：开发和 QA 都在局域网（< 5ms 延迟、0% 丢包）下测试，上线后用户投诉"卡到没法玩"。

**正确做法**：
- CI 中至少跑 3 种网络条件：优（LAN）、中（4G）、差（弱信号）
- 对每种条件设定明确的通过标准（如：4G 条件下预测误差 < 1m、重连成功率 > 95%）
- 将网络条件测试作为 Release Checklist 的必检项
- QA 日常测试使用 Network Simulator 的中等或差条件

### 陷阱 7：只用累计平均值掩盖瞬时问题

**症状**：监控面板显示"平均 RTT: 45ms, 平均丢包率: 1.2%"，但玩家实际体验是"每 30 秒卡 2 秒"。

**正确做法**：
- 所有网络指标必须同时展示**滑动窗口值**（如最近 5 秒）、**P50/P95/P99 值**，而非仅平均值
- 检测尖刺（spike）：P99 远大于 P50 → 有间歇性问题
- 使用直方图（Histogram）而非单一数字来展示延迟分布
- 对"体验致命"的指标（如超过 500ms 的延迟尖刺），单独统计发生率

---

> **至此，帧同步/状态同步/混合同步的完整学习路径已全部覆盖。本节串联了 29 个前置教程的所有调试手段，是"从实验室到生产环境"的关键一步。**
