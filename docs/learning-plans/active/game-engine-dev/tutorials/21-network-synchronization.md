---
title: "网络同步基础"
updated: 2026-06-05
---

# 网络同步基础

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 无

---

## 1. 概念讲解

### 1.1 为什么需要网络同步？

现代游戏早已不是单机体验。从《英雄联盟》的 5v5 对战到《原神》的开放世界联机，从《CS2》的竞技对抗到《艾尔登法环》的入侵机制——网络同步是所有多人游戏体验的基础。

然而，网络通信天然不完美：

- **延迟（Latency）**：数据从一端传到另一端需要时间。北京到洛杉矶的物理距离就决定了最低延迟约 130ms（光速限制）。
- **抖动（Jitter）**：延迟不是恒定的。同一时刻发送的两个包可能相差几十毫秒到达。
- **丢包（Packet Loss）**：网络拥塞时，路由器会直接丢弃数据包，丢包率从 0.1% 到 10% 不等。
- **乱序（Out-of-Order）**：包可能走不同路径到达，导致后发的包先到。

游戏网络同步的核心挑战是：**在不可靠的网络之上，构建一个所有玩家都觉得"公平、流畅、一致"的虚拟世界。**

### 1.2 网络传输层：TCP vs UDP

游戏网络通常建立在两种传输协议之上，理解它们的差异是设计同步方案的前提。

| 特性 | TCP | UDP |
|------|-----|-----|
| 连接 | 面向连接 | 无连接 |
| 可靠性 | 可靠传输，自动重传 | 不可靠，可能丢包 |
| 顺序保证 | 保证按序到达 | 不保证顺序 |
| 拥塞控制 | 有（降低发送速率） | 无 |
| 头部开销 | 20 字节 | 8 字节 |
| 延迟特性 | 可能因重传产生突发延迟 | 延迟稳定，但可能丢包 |

**为什么大多数游戏选择 UDP？**

1. **实时性优先**：对于 60FPS 的游戏，每 16.6ms 就要发送一帧数据。TCP 的重传机制会让旧数据阻塞新数据——等一个丢了的包重传， newer 的状态已经过时了。
2. **头部开销小**：UDP 头部仅 8 字节，适合高频小数据包场景。
3. **自定义可靠性**：游戏可以决定哪些数据需要可靠传输（如武器切换），哪些不需要（如每帧的位置更新）。TCP 的"全有或全无"可靠性过于粗暴。

**例外：回合制游戏、MMO 的聊天系统、文件传输等可以使用 TCP。**

### 1.3 网络基础度量

**RTT（Round-Trip Time，往返时间）**

从发送数据到收到对方确认的时间。测量方式：客户端发送一个带时间戳的包，服务器立即回传，客户端计算差值。

```
RTT = T_receive - T_send
```

**单向延迟（One-Way Delay）**

理论上等于 RTT / 2，但实际上上下行延迟可能不对称。精确测量需要两端时钟同步（如 NTP）。

**抖动（Jitter）**

连续数据包到达时间间隔的变化量。数学定义为：

```
Jitter = |D(i, i-1) - D(i-1, i-2)|
```

其中 D(i, i-1) 是第 i 个包和第 i-1 个包的到达时间差。

**带宽与带宽延迟积（BDP）**

```
BDP = 带宽 × RTT
```

表示网络"管道"中同时能容纳多少数据。游戏同步设计需要考虑 BDP，避免发送速率超过网络容量。

### 1.4 游戏网络架构

#### 客户端-服务器架构（Client-Server, C/S）

```
    Client A
       ↑↓
    ┌──────┐
    │Server│ ← 中央权威
    └──────┘
       ↑↓
    Client B
```

**特点：**
- 服务器是游戏世界的"唯一真相源"（Single Source of Truth）
- 客户端只发送输入，服务器计算全部游戏逻辑
- 服务器将世界状态广播给所有客户端

**优点：**
- 天然防作弊（客户端无法篡改游戏状态）
- 逻辑集中，易于维护
- NAT 穿透简单（只需服务器有公网 IP）

**缺点：**
- 服务器成本高
- 延迟敏感：玩家的每个操作都要等服务器确认
- 服务器是单点瓶颈

**代表游戏：** CS2、Valorant、英雄联盟、魔兽世界

#### 点对点架构（Peer-to-Peer, P2P）

```
    Client A ←────→ Client B
       ↑↓    ↘   ↗
       └──────→ Client C
```

**特点：**
- 没有中央服务器，每个客户端直接与其他客户端通信
- 通常有一个"主机"（Host）负责协调
- 所有客户端都模拟游戏世界

**优点：**
- 无需专用服务器，成本低
- 对于格斗游戏等低延迟场景，P2P 的延迟等于单向延迟而非 RTT

**缺点：**
- 严重作弊风险（每个客户端都可以修改本地状态）
- 主机优势（Host Advantage）：主机玩家的输入无需网络传输
- NAT 穿透复杂
- 同步逻辑复杂（所有节点必须达成一致）

**代表游戏：** 街霸 6（使用回滚网代码）、部分格斗游戏

#### 权威服务器（Authoritative Server）

这是 C/S 架构的强化版，也是现代竞技游戏的标准做法：

```
Client: "我按了 W，请求向前移动"
         ↓
Server: [验证输入合法性] → [计算新位置] → [广播给所有客户端]
         ↓
Client: [收到服务器确认的位置，更新显示]
```

**核心原则：**
- 服务器拥有绝对权威，客户端只是"观众"
- 客户端可以预测和插值，但服务器状态才是真实的
- 任何客户端的计算结果都只是"猜测"

**为什么必须权威？**

想象一个非权威服务器的设计：客户端直接报告"我在 (100, 200)"，服务器照单全收。作弊者可以瞬间传送到任何位置、穿墙、无限血量。权威服务器要求客户端只发送"我按了 W"，由服务器决定"你移动到了哪里"。

### 1.5 状态同步 vs 帧同步

多人游戏的网络同步架构主要分为两种范式：

| 特性 | 状态同步（State Synchronization） | 帧同步（Lockstep / Deterministic Simulation） |
|------|----------------------------------|---------------------------------------------|
| 同步对象 | 游戏状态（位置、速度、生命值等） | 玩家输入（按键、鼠标移动） |
| 网络流量 | 较高（每帧发送状态数据） | 较低（每帧只发送输入） |
| 延迟处理 | 预测+插值 | 等所有玩家输入到达后才推进 |
| 确定性要求 | 不需要 | 严格需要（浮点数计算必须完全一致） |
| 回放/观战 | 需要额外录制 | 天然支持（只需记录输入） |
| 掉线处理 | 较容易（状态快照恢复） | 较难（需要重放或等待） |
| 作弊防护 | 较好（服务器验证） | 较差（客户端可伪造输入） |
| 代表游戏 | CS2, Overwatch, Fortnite | 星际争霸, 街霸, 王者荣耀 |

**状态同步**是现代 FPS 和 MOBA 游戏的主流选择。其核心思想是服务器作为权威（Authoritative）状态源，持续向客户端广播游戏状态。客户端在本地进行预测和插值，以掩盖网络延迟。

**帧同步**在 RTS 游戏和格斗游戏中更为常见。其核心思想是所有客户端运行完全相同的确定性模拟，只同步玩家的输入。由于模拟是确定性的，相同的输入必然产生相同的状态。帧同步对**跨平台确定性**有极高要求——不同 CPU（x86 vs ARM）、不同编译器优化级别可能导致浮点运算结果的微小差异，这些差异会随时间放大导致状态分叉（Desync）。

### 1.6 状态同步方案

#### 快照同步（Snapshot Interpolation）

**核心思想：** 服务器以固定频率（如 20Hz，即每 50ms）广播完整的世界状态快照。客户端接收这些快照，在它们之间进行插值，呈现平滑的运动。

```
时间轴：
Server: [快照@t0]      [快照@t1]      [快照@t2]      [快照@t3]
           ↓              ↓              ↓              ↓
Client: [渲染] ← 在 t0 和 t1 之间插值 → [渲染]
```

**关键参数：插值延迟（Interpolation Delay）**

客户端不能渲染"最新"的快照，因为下一个快照可能还没到（网络抖动）。通常客户端会缓冲 2-3 个快照，以固定延迟（如 100ms）渲染。

```cpp
// 客户端渲染时刻
// 当前时间: t_now
// 渲染目标: t_now - interp_delay (如 t_now - 100ms)
// 找到包围该时刻的两个快照，进行线性插值
```

**优点：**
- 实现简单
- 对丢包鲁棒（丢了一个快照，还有前后两个可以插值）
- 新玩家加入时只需接收最新快照即可

**缺点：**
- 带宽消耗大（每 tick 发送所有实体状态）
- 玩家看到的是"过去"的状态（有插值延迟）
- 不适合高频更新（如 60Hz）

**代表引擎：** Source Engine（CS2、TF2）、Unity 的 Mirror 快照同步模式

#### 增量同步 / Delta Compression

**核心思想：** 不发送完整快照，只发送与上一个确认状态相比的"变化量"。

```
Tick 100: 发送完整快照（基准帧）
Tick 101: 只发送改变了位置的实体
Tick 102: 只发送改变了血量的实体
...
Tick 110: 如果客户端请求重传，重新发送完整快照
```

**实现要点：**

1. **基准帧管理**：服务器记录每个客户端最后确认收到的帧号（ACK）。
2. **差分计算**：只序列化自基准帧以来发生变化的字段。
3. **回退机制**：如果客户端报告丢包（NACK），发送完整快照作为恢复。

```cpp
// 伪代码
struct DeltaSnapshot {
    uint32_t baseline_tick;  // 基准帧号
    uint32_t delta_tick;     // 当前帧号
    std::vector<EntityDelta> deltas;
};

struct EntityDelta {
    uint16_t entity_id;
    uint32_t changed_fields_mask;  // 位掩码，标记哪些字段变了
    std::vector<uint8_t> changed_data;
};
```

**优点：**
- 大幅节省带宽（通常减少 80-95%）
- 适合大规模世界（如 100 个玩家同屏）

**缺点：**
- 实现复杂
- 依赖可靠的基础帧（需要 ACK/NACK 机制）
- 新玩家加入需要完整快照

**优化：仅发送可见实体**

结合视锥剔除（Frustum Culling）和距离剔除，只序列化客户端"能看到"的实体。这是 MMO 和 Battle Royale 游戏的必备优化。

### 1.6 客户端预测（Client-side Prediction）

快照同步有一个致命问题：**玩家按下 W 后，要等 RTT/2（到服务器）+ RTT/2（回客户端）= RTT 的时间才能看到自己的角色移动。**

在 100ms 延迟下，这会让游戏感觉"粘滞"、"不跟手"。

**客户端预测**解决了这个问题：

```
Client: 检测到"按 W"
         ↓
Client: [立即在本地模拟移动] ← 不等服务器！
         ↓
Client: 发送"按 W"给服务器
         ↓
Server: [权威计算移动] → [发送确认]
         ↓
Client: [收到服务器状态]
         ↓
Client: [比较预测 vs 服务器结果]
         ├── 一致 → 无事发生（最常见）
         └── 不一致 → 回滚并重新模拟（Reconciliation）
```

**关键洞察：** 玩家的输入（按键、鼠标移动）在本地是 100% 确定的。客户端可以立即用和服务器完全相同的物理/移动代码来预测结果。如果服务器也收到了相同的输入，预测就是正确的。

**预测什么？**

- **玩家自己的角色**：必须预测。玩家对自己的输入最敏感。
- **可交互环境**：如门、按钮——预测它们的状态变化。
- **不预测其他玩家**：其他玩家的输入你并不知道，无法预测。

### 1.7 服务器回滚（Server Reconciliation）

预测不可能永远正确。当服务器状态与预测不一致时，需要**回滚（Reconciliation）**。

**什么导致预测错误？**

1. **服务器拒绝了输入**：如移动到了碰撞体中、技能在 CD 中
2. **其他玩家的影响**：如被击退、被冰冻
3. **随机因素**：如服务器判定这次攻击暴击了，改变了你的位置

**回滚算法：**

```cpp
// 客户端维护一个输入历史队列
std::deque<PlayerInput> input_history;

// 收到服务器确认 @tick 100
void OnServerState(ServerState state, uint32_t server_tick) {
    // 1. 找到对应 tick 的预测状态
    PredictedState predicted = GetPredictedState(server_tick);

    // 2. 比较
    if (predicted != state) {
        // 3. 回滚到服务器状态
        current_state = state;

        // 4. 重放所有后续输入
        for (auto& input : input_history) {
            if (input.tick > server_tick) {
                current_state = Simulate(input, current_state);
            }
        }
    }

    // 5. 丢弃已确认的输入
    while (!input_history.empty() && input_history.front().tick <= server_tick) {
        input_history.pop_front();
    }
}
```

**视觉平滑化：**

直接回滚可能导致角色"瞬移"。更好的做法是：
- 如果误差很小（< 10cm），缓慢插值修正
- 如果误差很大（被击退、传送），直接瞬移（玩家理解这是特殊事件）

### 1.8 插值（Interpolation）与外推（Extrapolation）

这两个技术用于处理**其他玩家/实体**的显示——你不能预测它们，但可以让它们的运动看起来平滑。

#### 插值（Interpolation）

**原理：** 使用两个已知的过去状态，在中间渲染平滑过渡。

```cpp
// 客户端缓冲了服务器快照
// 快照 @t=100ms: pos = (0, 0)
// 快照 @t=150ms: pos = (10, 0)
// 当前渲染时间: t=125ms (延迟 25ms 渲染)

float alpha = (125.0f - 100.0f) / (150.0f - 100.0f);  // = 0.5
Vector3 rendered_pos = Lerp(pos_100, pos_150, alpha);  // = (5, 0)
```

**要求：** 至少有两个快照才能插值。因此需要缓冲时间（通常 50-100ms）。

**优点：** 完全平滑，不会猜测错误
**缺点：** 总是延迟显示（你看到的是 100ms 前的敌人）

**自适应插值延迟**

固定插值延迟（如 100ms）在网络状况变化时可能不够灵活。网络抖动大时，100ms 缓冲可能不够，导致插值"饿死"（没有两个快照可插值）；网络稳定时，100ms 又 unnecessarily 增加延迟。

更好的做法是**动态调整插值延迟**：

```cpp
float CalculateInterpDelay() {
    // 基于抖动统计动态调整
    float jitter = CalculateJitter();  // 测量最近 N 个包的到达时间方差
    // 至少 50ms，根据抖动增加，通常取 2-3 倍抖动 + 基础缓冲
    return std::max(50.0f, jitter * 2.5f + 30.0f);
}
```

一些引擎采用更复杂的自适应算法，根据测量的网络抖动动态调整插值延迟，在平滑性和延迟之间取得最佳平衡。

#### 外推（Extrapolation）

**原理：** 基于已知的速度/加速度，预测实体未来的位置。

```cpp
// 最后已知状态 @t=100ms: pos=(0,0), vel=(10,0)
// 当前时间: t=120ms (晚了 20ms，下一个快照还没到)

float dt = 0.020f;
Vector3 extrapolated_pos = last_pos + last_vel * dt;  // = (0.2, 0)
```

**优点：** 延迟更低
**缺点：** 如果实体改变了方向（如急停、转向），外推会完全错误

**何时使用外推？**

- 快照未及时到达（网络抖动）
- 高速移动的实体（如赛车、火箭）
- 结合插值：优先插值，无数据时才外推

### 1.9 延迟补偿（Lag Compensation）

这是一个让玩家觉得"公平"的关键技术，尤其在射击游戏中。

**问题场景：**

```
玩家 A（延迟 50ms）瞄准玩家 B 的头部，开枪
         ↓
服务器收到射击请求（50ms 后）
         ↓
服务器检查：玩家 B 现在在哪里？
         ↓
问题：玩家 B 已经移动了！服务器看到 B 不在准星上 → 判定未命中
         ↓
玩家 A 的屏幕上明明打中了，但服务器说没打中 → 极度挫败感
```

**延迟补偿的解决方案：**

服务器在判定命中时，**将其他玩家回滚到射击者看到他们的时间点**。

```cpp
void ProcessShot(Player shooter, Ray shot_ray, uint32_t client_timestamp) {
    // 1. 计算射击发生时的服务器 tick
    // client_timestamp 是射击者在本地按下射击键的时间
    // 减去射击者的 RTT/2，得到对应的服务器时间
    uint32_t target_tick = ServerTickAtClientTime(client_timestamp);

    // 2. 保存当前所有玩家状态
    auto saved_states = SaveAllPlayerStates();

    // 3. 将所有其他玩家回滚到 target_tick 的状态
    for (auto& player : all_players) {
        if (player.id != shooter.id) {
            player.state = GetHistoricalState(player.id, target_tick);
        }
    }

    // 4. 在回滚后的世界中进行射线检测
    HitResult hit = Raycast(shot_ray);

    // 5. 恢复所有玩家状态
    RestoreAllPlayerStates(saved_states);

    // 6. 应用伤害（在恢复后的世界中）
    if (hit.valid) {
        ApplyDamage(hit.player, shooter.weapon.damage);
    }
}
```

**关键权衡：**

- **被射击者的体验**：被射击者可能觉得自己已经躲到掩体后了，但还是被打中（因为射击者看到的是"过去"的他）。
- **射击者的体验**：准星对准就能命中，感觉公平。
- **行业标准：** 优先保证射击者的体验（因为主动射击是玩家控制的行为，被射击是被动承受的）。

**代表游戏：** CS2、Valorant、Overwatch 都使用延迟补偿。

### 1.10 实体插值（Entity Interpolation）

这是插值技术在 Source Engine 中的具体实现名称，本质上与 1.8 节的插值相同，但有一些工程细节值得了解。

**Source Engine 的实现：**

```cpp
// 客户端维护两个快照缓冲区
Snapshot snapshot0;  // 较旧的快照
Snapshot snapshot1;  // 较新的快照

// 渲染时，根据当前时间在这两个快照之间插值
float interp_fraction = (render_time - snapshot0.timestamp)
                        / (snapshot1.timestamp - snapshot0.timestamp);

// 插值所有实体位置
for (Entity* ent : entities) {
    ent->render_pos = Lerp(
        snapshot0.GetEntityPos(ent->id),
        snapshot1.GetEntityPos(ent->id),
        interp_fraction
    );
}
```

**cl_interp 与 cl_interp_ratio：**

Source Engine 允许玩家通过控制台调整插值参数：

- `cl_interp`：手动设置插值延迟（秒）
- `cl_interp_ratio`：插值延迟 = `cl_interp_ratio / cl_updaterate`
- `cl_updaterate`：期望的服务器更新频率

竞技玩家通常将插值调到最低（如 15-30ms），牺牲一定的平滑性换取更低的延迟。

### 1.11 网络序列化与状态压缩

游戏状态通过网络发送，序列化和压缩直接影响带宽和性能。

#### 基本序列化

```cpp
class NetworkBuffer {
public:
    void WriteUInt8(uint8_t v)  { /* ... */ }
    void WriteUInt16(uint16_t v) { /* ... */ }
    void WriteUInt32(uint32_t v) { /* ... */ }
    void WriteFloat(float v) { /* ... */ }
    void WriteVector3(const Vector3& v) {
        WriteFloat(v.x);
        WriteFloat(v.y);
        WriteFloat(v.z);
    }
    // ...
};
```

#### 量化（Quantization）

浮点数占 4 字节，但很多值不需要完整精度：

```cpp
// 血量：0-100，只需 1 字节
void WriteHealth(uint8_t health) {
    WriteUInt8(health);  // 而不是 WriteFloat
}

// 角度：0-360度，量化为 16 位无符号整数（精度 0.005 度）
void WriteAngle(float degrees) {
    uint16_t quantized = static_cast<uint16_t>(
        (degrees / 360.0f) * 65535.0f
    );
    WriteUInt16(quantized);
}

// 位置：如果世界范围有限，可以用更少位数
// 例如世界范围 -512 到 +512，精度 0.01，需要 log2(102400) ≈ 17 位
void WritePosition(float pos, float min, float max, int bits) {
    float range = max - min;
    uint32_t max_val = (1u << bits) - 1;
    uint32_t quantized = static_cast<uint32_t>(((pos - min) / range) * max_val);
    WriteBits(quantized, bits);
}
```

#### 位域压缩（Bit Packing）

将多个小值打包到字节中：

```cpp
// 布尔标志：8 个布尔值打包到 1 字节
uint8_t flags = (is_jumping << 0) | (is_crouching << 1) | (is_firing << 2);
WriteUInt8(flags);

// 枚举值：如果只有 5 种武器，只需 3 位
void WriteWeaponType(WeaponType type) {
    WriteBits(static_cast<uint32_t>(type), 3);  // 0-7
}
```

#### 增量编码与预测编码

```cpp
// 位置通常变化很小，发送差值而非绝对值
void WriteDeltaPosition(const Vector3& current, const Vector3& baseline) {
    Vector3 delta = current - baseline;
    // delta 的范围通常比绝对位置小得多，可以用更少位数
    WriteQuantizedFloat(delta.x, -10.0f, 10.0f, 16);
    WriteQuantizedFloat(delta.y, -10.0f, 10.0f, 16);
    WriteQuantizedFloat(delta.z, -10.0f, 10.0f, 16);
}
```

#### 字典压缩与字符串表

字符串（如玩家名字、资源路径）通过字符串表压缩：

```cpp
// 服务器维护一个字符串表，给每个字符串分配索引
// 只发送索引（2 字节）而非完整字符串
std::unordered_map<std::string, uint16_t> string_table;

void WriteStringRef(const std::string& str) {
    auto it = string_table.find(str);
    if (it != string_table.end()) {
        WriteUInt16(it->second);  // 2 字节
    } else {
        WriteUInt16(0xFFFF);       // 标记：新字符串
        WriteString(str);          // 完整字符串（仅第一次）
    }
}
```

### 1.12 各同步方案权衡总结

| 技术 | 延迟感受 | 带宽消耗 | 实现复杂度 | 作弊防护 | 适用场景 |
|------|---------|---------|-----------|---------|---------|
| 快照同步 | 高（插值延迟） | 高 | 低 | 强 | 小规模对战、入门实现 |
| 增量同步 | 高 | 低 | 高 | 强 | 大规模 MMO、Battle Royale |
| 客户端预测 | 低（自己的输入） | 中 | 中 | 强 | FPS、动作游戏 |
| 延迟补偿 | 低（射击判定） | 低 | 中 | 强 | 射击游戏 |
| P2P 回滚 | 极低 | 低 | 极高 | 弱 | 格斗游戏 |

**Overwatch 的混合方案：**

- 玩家自己角色：客户端预测 + 服务器回滚
- 其他玩家：快照插值（Entity Interpolation）
- 射击判定：延迟补偿
- 技能/命中：权威服务器 + 延迟补偿

**Rocket League 的特殊处理：**

- 物理模拟是确定性的（Deterministic），使用固定时间步长
- 所有客户端和服务器运行完全相同的物理代码
- 只需同步输入（油门、转向、跳跃），而非位置
- 客户端预测几乎 100% 准确，回滚极少发生

---

## 2. 代码示例

### 2.1 UDP 客户端/服务器基础通信

以下代码演示了一个完整的跨平台 UDP 客户端-服务器通信框架，使用 BSD Socket API。

**`udp_socket.h`** — 跨平台 UDP Socket 封装：

```cpp
#pragma once

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
    typedef int socklen_t;
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #include <fcntl.h>
    #include <errno.h>
    typedef int SOCKET;
    #define INVALID_SOCKET (-1)
    #define SOCKET_ERROR (-1)
    #define closesocket close
#endif

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <iostream>

// 初始化/清理网络库
struct NetworkInit {
    NetworkInit() {
#ifdef _WIN32
        WSADATA wsaData;
        WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif
    }
    ~NetworkInit() {
#ifdef _WIN32
        WSACleanup();
#endif
    }
};

struct NetworkAddress {
    sockaddr_in addr;

    NetworkAddress() { memset(&addr, 0, sizeof(addr)); }

    NetworkAddress(const std::string& ip, uint16_t port) {
        memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        inet_pton(AF_INET, ip.c_str(), &addr.sin_addr);
    }

    std::string ToString() const {
        char buf[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &addr.sin_addr, buf, sizeof(buf));
        return std::string(buf) + ":" + std::to_string(ntohs(addr.sin_port));
    }
};

class UDPSocket {
public:
    UDPSocket() : socket_(INVALID_SOCKET) {}

    ~UDPSocket() { Close(); }

    // 创建 UDP Socket
    bool Create() {
        socket_ = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (socket_ == INVALID_SOCKET) {
            std::cerr << "Failed to create socket\n";
            return false;
        }
        return true;
    }

    // 绑定到本地端口（服务器用）
    bool Bind(uint16_t port) {
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        addr.sin_addr.s_addr = INADDR_ANY;

        if (bind(socket_, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
            std::cerr << "Failed to bind to port " << port << "\n";
            return false;
        }
        return true;
    }

    // 设置为非阻塞模式
    bool SetNonBlocking() {
#ifdef _WIN32
        u_long mode = 1;
        return ioctlsocket(socket_, FIONBIO, &mode) == 0;
#else
        int flags = fcntl(socket_, F_GETFL, 0);
        return fcntl(socket_, F_SETFL, flags | O_NONBLOCK) != -1;
#endif
    }

    // 发送数据
    int SendTo(const void* data, size_t len, const NetworkAddress& dest) {
        return sendto(socket_, (const char*)data, (int)len, 0,
                      (sockaddr*)&dest.addr, sizeof(dest.addr));
    }

    // 接收数据
    int RecvFrom(void* buffer, size_t max_len, NetworkAddress& from) {
        socklen_t from_len = sizeof(from.addr);
        int result = recvfrom(socket_, (char*)buffer, (int)max_len, 0,
                              (sockaddr*)&from.addr, &from_len);
        return result;
    }

    void Close() {
        if (socket_ != INVALID_SOCKET) {
            closesocket(socket_);
            socket_ = INVALID_SOCKET;
        }
    }

private:
    SOCKET socket_;
};
```

**`udp_server.cpp`** — UDP Echo 服务器：

```cpp
#include "udp_socket.h"
#include <chrono>
#include <thread>

int main() {
    NetworkInit net_init;

    UDPSocket server;
    if (!server.Create()) return 1;
    if (!server.Bind(7777)) return 1;
    if (!server.SetNonBlocking()) return 1;

    std::cout << "[Server] Listening on port 7777...\n";

    char buffer[1024];
    auto last_print = std::chrono::steady_clock::now();
    int packet_count = 0;

    while (true) {
        NetworkAddress client_addr;
        int received = server.RecvFrom(buffer, sizeof(buffer), client_addr);

        if (received > 0) {
            // 收到数据，回传（Echo）
            std::cout << "[Server] Received " << received
                      << " bytes from " << client_addr.ToString()
                      << ": " << std::string(buffer, received) << "\n";

            server.SendTo(buffer, received, client_addr);
            packet_count++;
        }

        // 每秒打印统计
        auto now = std::chrono::steady_clock::now();
        if (std::chrono::duration_cast<std::chrono::seconds>(now - last_print).count() >= 1) {
            if (packet_count > 0) {
                std::cout << "[Server] Processed " << packet_count << " packets in last second\n";
                packet_count = 0;
            }
            last_print = now;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    return 0;
}
```

**`udp_client.cpp`** — UDP 客户端（带 RTT 测量）：

```cpp
#include "udp_socket.h"
#include <chrono>
#include <thread>

// 简单的协议头
struct PacketHeader {
    uint32_t sequence;      // 序列号
    uint32_t timestamp_ms;  // 发送时间戳（客户端本地）
};

int main() {
    NetworkInit net_init;

    UDPSocket client;
    if (!client.Create()) return 1;
    if (!client.SetNonBlocking()) return 1;

    NetworkAddress server_addr("127.0.0.1", 7777);

    std::cout << "[Client] Connecting to " << server_addr.ToString() << "\n";

    uint32_t sequence = 0;
    char recv_buffer[1024];

    // RTT 统计
    float rtt_sum = 0.0f;
    int rtt_count = 0;

    while (true) {
        // 发送心跳包
        PacketHeader header;
        header.sequence = sequence++;
        header.timestamp_ms = static_cast<uint32_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now().time_since_epoch()
            ).count()
        );

        const char* payload = "Hello Server!";
        char send_buffer[256];
        memcpy(send_buffer, &header, sizeof(header));
        memcpy(send_buffer + sizeof(header), payload, strlen(payload));

        client.SendTo(send_buffer, sizeof(header) + strlen(payload), server_addr);

        // 等待响应（轮询）
        auto send_time = std::chrono::steady_clock::now();
        bool received = false;

        while (!received) {
            NetworkAddress from;
            int len = client.RecvFrom(recv_buffer, sizeof(recv_buffer), from);

            if (len > 0) {
                auto recv_time = std::chrono::steady_clock::now();
                float rtt = std::chrono::duration<float, std::milli>(recv_time - send_time).count();

                PacketHeader* resp_header = (PacketHeader*)recv_buffer;
                std::cout << "[Client] Received echo for seq=" << resp_header->sequence
                          << ", RTT=" << rtt << "ms\n";

                rtt_sum += rtt;
                rtt_count++;
                received = true;
            }

            // 超时检查
            auto elapsed = std::chrono::steady_clock::now() - send_time;
            if (elapsed > std::chrono::milliseconds(1000)) {
                std::cout << "[Client] Timeout waiting for response!\n";
                break;
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }

        // 打印平均 RTT
        if (rtt_count > 0 && rtt_count % 10 == 0) {
            std::cout << "[Client] Average RTT over last 10 packets: "
                      << (rtt_sum / rtt_count) << "ms\n";
            rtt_sum = 0;
            rtt_count = 0;
        }

        // 每秒发送一次
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    return 0;
}
```

**运行方式：**

```bash
# 编译（Linux/macOS）
g++ -std=c++17 udp_server.cpp -o udp_server
g++ -std=c++17 udp_client.cpp -o udp_client

# 编译（Windows MSVC）
cl /std:c++17 /EHsc udp_server.cpp
cl /std:c++17 /EHsc udp_client.cpp

# 运行（先启动服务器，再启动客户端）
./udp_server
# 另一个终端
./udp_client
```

**预期输出：**

```
[Server] Listening on port 7777...
[Server] Received 31 bytes from 127.0.0.1:54321: Hello Server!
[Server] Processed 1 packets in last second
...

[Client] Connecting to 127.0.0.1:7777
[Client] Received echo for seq=0, RTT=0.5ms
[Client] Received echo for seq=1, RTT=0.3ms
...
[Client] Average RTT over last 10 packets: 0.4ms
```

### 2.2 快照同步实现

以下代码演示了一个简化的快照同步系统，包含服务器广播和客户端插值。

```cpp
#include "udp_socket.h"
#include <vector>
#include <deque>
#include <map>
#include <cmath>
#include <algorithm>

// ============================================================================
// 共享数据结构
// ============================================================================

static constexpr uint32_t PROTOCOL_ID = 0x47454E54;  // "GENT"
static constexpr float SERVER_TICK_RATE = 20.0f;      // 20 Hz
static constexpr float SERVER_TICK_DT = 1.0f / SERVER_TICK_RATE;
static constexpr float INTERP_DELAY_MS = 100.0f;      // 100ms 插值延迟

struct Vector3 {
    float x, y, z;
    Vector3(float x=0, float y=0, float z=0) : x(x), y(y), z(z) {}
    Vector3 operator+(const Vector3& o) const { return Vector3(x+o.x, y+o.y, z+o.z); }
    Vector3 operator*(float s) const { return Vector3(x*s, y*s, z*s); }
};

inline Vector3 Lerp(const Vector3& a, const Vector3& b, float t) {
    return a + (b - a) * t;
}

// 实体状态
struct EntityState {
    uint32_t entity_id;
    Vector3 position;
    Vector3 velocity;
    float health;
    uint32_t timestamp_ms;
};

// 世界快照
struct WorldSnapshot {
    uint32_t tick;
    uint32_t timestamp_ms;
    std::vector<EntityState> entities;
};

// 网络消息类型
enum class MsgType : uint8_t {
    CLIENT_INPUT = 1,    // 客户端 → 服务器：输入
    SERVER_SNAPSHOT = 2, // 服务器 → 客户端：快照
    CLIENT_ACK = 3       // 客户端 → 服务器：确认收到
};

// ============================================================================
// 序列化辅助
// ============================================================================

class BitWriter {
    std::vector<uint8_t> data;
    uint32_t bit_pos = 0;
public:
    void WriteBits(uint32_t value, int bits) {
        for (int i = 0; i < bits; i++) {
            int byte_idx = bit_pos / 8;
            int bit_idx = bit_pos % 8;
            if (byte_idx >= data.size()) data.push_back(0);
            if (value & (1u << i)) {
                data[byte_idx] |= (1u << bit_idx);
            }
            bit_pos++;
        }
    }
    void WriteUInt8(uint8_t v) { WriteBits(v, 8); }
    void WriteUInt16(uint16_t v) { WriteBits(v, 16); }
    void WriteUInt32(uint32_t v) { WriteBits(v, 32); }
    void WriteFloat(float v) {
        uint32_t bits;
        static_assert(sizeof(bits) == sizeof(v), "Size mismatch");
        memcpy(&bits, &v, sizeof(v));
        WriteBits(bits, 32);
    }
    void WriteVector3(const Vector3& v) {
        WriteFloat(v.x);
        WriteFloat(v.y);
        WriteFloat(v.z);
    }
    const std::vector<uint8_t>& GetData() const { return data; }
    size_t GetBitCount() const { return bit_pos; }
};

class BitReader {
    const uint8_t* data;
    size_t total_bits;
    uint32_t bit_pos = 0;
public:
    BitReader(const uint8_t* d, size_t bytes) : data(d), total_bits(bytes * 8) {}
    uint32_t ReadBits(int bits) {
        uint32_t result = 0;
        for (int i = 0; i < bits; i++) {
            if (bit_pos >= total_bits) return 0;
            int byte_idx = bit_pos / 8;
            int bit_idx = bit_pos % 8;
            if (data[byte_idx] & (1u << bit_idx)) {
                result |= (1u << i);
            }
            bit_pos++;
        }
        return result;
    }
    uint8_t ReadUInt8() { return ReadBits(8); }
    uint16_t ReadUInt16() { return ReadBits(16); }
    uint32_t ReadUInt32() { return ReadBits(32); }
    float ReadFloat() {
        uint32_t bits = ReadBits(32);
        float v;
        memcpy(&v, &bits, sizeof(v));
        return v;
    }
    Vector3 ReadVector3() {
        return Vector3(ReadFloat(), ReadFloat(), ReadFloat());
    }
};

// ============================================================================
// 服务器实现
// ============================================================================

struct ClientConnection {
    NetworkAddress addr;
    uint32_t last_ack_tick = 0;
    float last_input_forward = 0;
    float last_input_right = 0;
    uint32_t player_entity_id;
};

class SnapshotServer {
    UDPSocket socket_;
    std::map<uint64_t, ClientConnection> clients_;  // 用 addr hash 做 key
    std::vector<EntityState> entities_;
    uint32_t current_tick_ = 0;
    uint32_t next_entity_id_ = 1;

    static uint64_t AddrHash(const NetworkAddress& addr) {
        return (uint64_t)addr.addr.sin_addr.s_addr << 32 | addr.addr.sin_port;
    }

public:
    bool Start(uint16_t port) {
        if (!socket_.Create()) return false;
        if (!socket_.Bind(port)) return false;
        if (!socket_.SetNonBlocking()) return false;

        // 创建一些测试实体
        for (int i = 0; i < 5; i++) {
            EntityState e;
            e.entity_id = next_entity_id_++;
            e.position = Vector3((float)i * 5.0f, 0, 0);
            e.velocity = Vector3(1.0f + i * 0.5f, 0, 0);
            e.health = 100.0f;
            entities_.push_back(e);
        }

        return true;
    }

    void ProcessInput(const NetworkAddress& from, const std::vector<uint8_t>& data) {
        uint64_t hash = AddrHash(from);
        auto it = clients_.find(hash);

        // 新客户端
        if (it == clients_.end()) {
            ClientConnection client;
            client.addr = from;
            client.player_entity_id = next_entity_id_++;

            // 为新玩家创建实体
            EntityState player;
            player.entity_id = client.player_entity_id;
            player.position = Vector3(0, 0, 0);
            player.velocity = Vector3(0, 0, 0);
            player.health = 100.0f;
            entities_.push_back(player);

            clients_[hash] = client;
            std::cout << "[Server] New client connected: " << from.ToString()
                      << " (entity " << client.player_entity_id << ")\n";
            return;
        }

        // 解析输入
        if (data.size() >= 3) {
            it->second.last_input_forward = (int8_t)data[1] / 127.0f;
            it->second.last_input_right = (int8_t)data[2] / 127.0f;
        }
    }

    void Update(float dt) {
        // 模拟实体移动
        for (auto& e : entities_) {
            // 简单的圆周运动 + 线性移动
            float time = current_tick_ * SERVER_TICK_DT;
            e.position.x += e.velocity.x * dt;
            e.position.z += std::sin(time + e.entity_id) * dt * 2.0f;

            // 边界环绕
            if (e.position.x > 50.0f) e.position.x -= 100.0f;
            if (e.position.x < -50.0f) e.position.x += 100.0f;
        }

        // 应用玩家输入
        for (auto& [hash, client] : clients_) {
            for (auto& e : entities_) {
                if (e.entity_id == client.player_entity_id) {
                    e.position.x += client.last_input_right * 10.0f * dt;
                    e.position.z += client.last_input_forward * 10.0f * dt;
                }
            }
        }

        current_tick_++;
    }

    void BroadcastSnapshot() {
        // 构建快照
        BitWriter writer;
        writer.WriteUInt8((uint8_t)MsgType::SERVER_SNAPSHOT);
        writer.WriteUInt32(current_tick_);
        writer.WriteUInt8((uint8_t)entities_.size());

        for (const auto& e : entities_) {
            writer.WriteUInt32(e.entity_id);
            writer.WriteVector3(e.position);
            writer.WriteFloat(e.health);
        }

        // 广播给所有客户端
        for (const auto& [hash, client] : clients_) {
            socket_.SendTo(writer.GetData().data(), writer.GetData().size(), client.addr);
        }
    }

    void Poll() {
        char buffer[2048];
        NetworkAddress from;

        while (true) {
            int len = socket_.RecvFrom(buffer, sizeof(buffer), from);
            if (len <= 0) break;

            if (len < 1) continue;
            MsgType type = (MsgType)buffer[0];

            switch (type) {
                case MsgType::CLIENT_INPUT:
                    ProcessInput(from, std::vector<uint8_t>((uint8_t*)buffer, (uint8_t*)buffer + len));
                    break;
                case MsgType::CLIENT_ACK:
                    // 处理 ACK
                    break;
                default:
                    break;
            }
        }
    }

    void Run() {
        auto last_tick = std::chrono::steady_clock::now();

        while (true) {
            Poll();

            auto now = std::chrono::steady_clock::now();
            float elapsed = std::chrono::duration<float>(now - last_tick).count();

            if (elapsed >= SERVER_TICK_DT) {
                Update(SERVER_TICK_DT);
                BroadcastSnapshot();
                last_tick = now;
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
};

// ============================================================================
// 客户端实现（带插值）
// ============================================================================

class SnapshotClient {
    UDPSocket socket_;
    NetworkAddress server_addr_;
    std::deque<WorldSnapshot> snapshot_buffer_;
    std::map<uint32_t, EntityState> interpolated_entities_;
    uint32_t latest_tick_ = 0;

public:
    bool Connect(const std::string& server_ip, uint16_t server_port) {
        if (!socket_.Create()) return false;
        if (!socket_.SetNonBlocking()) return false;

        server_addr_ = NetworkAddress(server_ip, server_port);

        // 发送初始输入包注册
        uint8_t init_packet[3] = {(uint8_t)MsgType::CLIENT_INPUT, 0, 0};
        socket_.SendTo(init_packet, 3, server_addr_);

        return true;
    }

    void SendInput(float forward, float right) {
        uint8_t packet[3];
        packet[0] = (uint8_t)MsgType::CLIENT_INPUT;
        packet[1] = (uint8_t)(forward * 127.0f);
        packet[2] = (uint8_t)(right * 127.0f);
        socket_.SendTo(packet, 3, server_addr_);
    }

    void ReceiveSnapshots() {
        char buffer[2048];
        NetworkAddress from;

        while (true) {
            int len = socket_.RecvFrom(buffer, sizeof(buffer), from);
            if (len <= 0) break;

            if (len < 6 || (MsgType)buffer[0] != MsgType::SERVER_SNAPSHOT)
                continue;

            BitReader reader((uint8_t*)buffer + 1, len - 1);
            WorldSnapshot snap;
            snap.tick = reader.ReadUInt32();
            snap.timestamp_ms = static_cast<uint32_t>(
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()
                ).count()
            );

            uint8_t entity_count = reader.ReadUInt8();
            for (int i = 0; i < entity_count; i++) {
                EntityState e;
                e.entity_id = reader.ReadUInt32();
                e.position = reader.ReadVector3();
                e.health = reader.ReadFloat();
                snap.entities.push_back(e);
            }

            // 只保留更新的快照
            if (snap.tick > latest_tick_) {
                latest_tick_ = snap.tick;
                snapshot_buffer_.push_back(snap);

                // 限制缓冲区大小
                while (snapshot_buffer_.size() > 32) {
                    snapshot_buffer_.pop_front();
                }
            }
        }
    }

    void Interpolate() {
        if (snapshot_buffer_.size() < 2) {
            // 快照不够，无法插值
            return;
        }

        // 计算渲染目标时间 = 当前时间 - 插值延迟
        auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()
        ).count();

        uint32_t render_target_time = static_cast<uint32_t>(now_ms - INTERP_DELAY_MS);

        // 找到包围 render_target_time 的两个快照
        const WorldSnapshot* snap_a = nullptr;
        const WorldSnapshot* snap_b = nullptr;

        for (size_t i = 0; i < snapshot_buffer_.size() - 1; i++) {
            if (snapshot_buffer_[i].timestamp_ms <= render_target_time &&
                snapshot_buffer_[i + 1].timestamp_ms >= render_target_time) {
                snap_a = &snapshot_buffer_[i];
                snap_b = &snapshot_buffer_[i + 1];
                break;
            }
        }

        if (!snap_a || !snap_b) {
            // 目标时间超出范围，使用最新的可用快照
            snap_b = &snapshot_buffer_.back();
            for (size_t i = snapshot_buffer_.size() - 1; i > 0; i--) {
                if (snapshot_buffer_[i - 1].timestamp_ms < snap_b->timestamp_ms) {
                    snap_a = &snapshot_buffer_[i - 1];
                    break;
                }
            }
            if (!snap_a) return;
        }

        // 计算插值系数
        float dt_total = static_cast<float>(snap_b->timestamp_ms - snap_a->timestamp_ms);
        float dt_current = static_cast<float>(render_target_time - snap_a->timestamp_ms);
        float t = (dt_total > 0.0f) ? dt_current / dt_total : 0.0f;
        t = std::clamp(t, 0.0f, 1.0f);

        // 构建实体查找表
        std::map<uint32_t, const EntityState*> entities_a, entities_b;
        for (const auto& e : snap_a->entities) entities_a[e.entity_id] = &e;
        for (const auto& e : snap_b->entities) entities_b[e.entity_id] = &e;

        // 插值所有实体
        interpolated_entities_.clear();
        for (const auto& [id, e_a] : entities_a) {
            auto it_b = entities_b.find(id);
            if (it_b != entities_b.end()) {
                EntityState interp;
                interp.entity_id = id;
                interp.position = Lerp(e_a->position, it_b->second->position, t);
                interp.health = e_a->health + (it_b->second->health - e_a->health) * t;
                interpolated_entities_[id] = interp;
            } else {
                // 实体在 B 中不存在，使用 A 的值
                interpolated_entities_[id] = *e_a;
            }
        }
    }

    void Render() {
        // 简化的"渲染"——打印实体位置
        static auto last_print = std::chrono::steady_clock::now();
        auto now = std::chrono::steady_clock::now();

        if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_print).count() >= 500) {
            std::cout << "[Client] Interpolated state (" << interpolated_entities_.size() << " entities):\n";
            for (const auto& [id, e] : interpolated_entities_) {
                std::cout << "  Entity " << id << ": pos=("
                          << e.position.x << ", " << e.position.y << ", " << e.position.z
                          << "), health=" << e.health << "\n";
            }
            std::cout << "  Buffer size: " << snapshot_buffer_.size() << " snapshots\n";
            last_print = now;
        }
    }

    void Run() {
        auto last_input_time = std::chrono::steady_clock::now();

        while (true) {
            ReceiveSnapshots();
            Interpolate();
            Render();

            // 定期发送输入（模拟玩家按 W）
            auto now = std::chrono::steady_clock::now();
            if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_input_time).count() >= 50) {
                SendInput(0.0f, 0.0f);  // 静止
                last_input_time = now;
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
};

// ============================================================================
// 主函数
// ============================================================================

int main(int argc, char** argv) {
    NetworkInit net_init;

    if (argc > 1 && std::string(argv[1]) == "server") {
        SnapshotServer server;
        if (server.Start(7777)) {
            std::cout << "Snapshot Server started on port 7777\n";
            server.Run();
        }
    } else {
        SnapshotClient client;
        if (client.Connect("127.0.0.1", 7777)) {
            std::cout << "Snapshot Client connecting to 127.0.0.1:7777\n";
            client.Run();
        }
    }

    return 0;
}
```

**运行方式：**

```bash
# 编译
g++ -std=c++17 snapshot_sync.cpp -o snapshot_sync

# 启动服务器
./snapshot_sync server

# 启动多个客户端（不同终端）
./snapshot_sync client
./snapshot_sync client
```

**预期输出：**

```
[Server] Listening on port 7777...
[Server] New client connected: 127.0.0.1:54321 (entity 6)
[Server] New client connected: 127.0.0.1:54322 (entity 7)

[Client] Interpolated state (6 entities):
  Entity 1: pos=(12.34, 0, 2.15), health=100
  Entity 2: pos=(17.89, 0, -1.23), health=100
  ...
  Entity 6: pos=(0, 0, 0), health=100
  Buffer size: 3 snapshots
```

### 2.3 客户端预测 + 回滚框架

以下代码展示了一个完整的客户端预测和服务器回滚系统，适用于 FPS/动作游戏。

```cpp
#include "udp_socket.h"
#include <deque>
#include <map>
#include <cmath>

// ============================================================================
// 共享定义
// ============================================================================

static constexpr float TICK_RATE = 60.0f;
static constexpr float TICK_DT = 1.0f / TICK_RATE;
static constexpr float PLAYER_SPEED = 10.0f;

struct Vector2 {
    float x, y;
    Vector2(float x=0, float y=0) : x(x), y(y) {}
    Vector2 operator+(const Vector2& o) const { return Vector2(x+o.x, y+o.y); }
    Vector2 operator*(float s) const { return Vector2(x*s, y*s); }
    bool operator==(const Vector2& o) const { return x==o.x && y==o.y; }
    bool operator!=(const Vector2& o) const { return !(*this == o); }
};

struct PlayerInput {
    uint32_t tick;
    Vector2 move_dir;   // 归一化移动方向
    bool jump;
};

struct PlayerState {
    uint32_t entity_id;
    Vector2 position;
    Vector2 velocity;
    bool on_ground;
};

// ============================================================================
// 物理模拟（客户端和服务器共享完全相同的代码）
// ============================================================================

class PhysicsSimulator {
public:
    static PlayerState Simulate(const PlayerState& state,
                                 const PlayerInput& input,
                                 float dt) {
        PlayerState next = state;

        // 水平移动
        next.position.x += input.move_dir.x * PLAYER_SPEED * dt;
        next.position.y += input.move_dir.y * PLAYER_SPEED * dt;

        // 简单的跳跃
        if (input.jump && state.on_ground) {
            next.velocity.y = 8.0f;
            next.on_ground = false;
        }

        // 重力
        if (!next.on_ground) {
            next.velocity.y -= 20.0f * dt;
            next.position.y += next.velocity.y * dt;

            // 地面碰撞
            if (next.position.y <= 0.0f) {
                next.position.y = 0.0f;
                next.velocity.y = 0.0f;
                next.on_ground = true;
            }
        }

        // 世界边界
        next.position.x = std::clamp(next.position.x, -50.0f, 50.0f);

        return next;
    }
};

// ============================================================================
// 权威服务器
// ============================================================================

struct ServerPlayer {
    NetworkAddress addr;
    uint32_t entity_id;
    PlayerState state;
    std::deque<PlayerInput> pending_inputs;
    uint32_t last_processed_input_tick = 0;
};

class PredictiveServer {
    UDPSocket socket_;
    std::map<uint64_t, ServerPlayer> players_;
    uint32_t current_tick_ = 0;
    uint32_t next_entity_id_ = 1;

    static uint64_t AddrHash(const NetworkAddress& addr) {
        return (uint64_t)addr.addr.sin_addr.s_addr << 32 | addr.addr.sin_port;
    }

public:
    bool Start(uint16_t port) {
        if (!socket_.Create()) return false;
        if (!socket_.Bind(port)) return false;
        if (!socket_.SetNonBlocking()) return false;
        return true;
    }

    void ProcessPacket(const NetworkAddress& from, const uint8_t* data, int len) {
        if (len < 13) return;

        uint64_t hash = AddrHash(from);
        auto it = players_.find(hash);

        // 新玩家连接
        if (it == players_.end()) {
            ServerPlayer player;
            player.addr = from;
            player.entity_id = next_entity_id_++;
            player.state = {player.entity_id, Vector2(0, 0), Vector2(0, 0), true};
            players_[hash] = player;
            std::cout << "[Server] Player " << player.entity_id << " connected from "
                      << from.ToString() << "\n";
            it = players_.find(hash);
        }

        // 解析输入: [tick:4][move_x:4][move_y:4][jump:1]
        uint32_t input_tick;
        memcpy(&input_tick, data, 4);
        float move_x, move_y;
        memcpy(&move_x, data + 4, 4);
        memcpy(&move_y, data + 8, 4);
        bool jump = data[12] != 0;

        PlayerInput input{input_tick, Vector2(move_x, move_y), jump};

        // 存储输入（按 tick 排序插入）
        auto& inputs = it->second.pending_inputs;
        auto insert_pos = inputs.begin();
        while (insert_pos != inputs.end() && insert_pos->tick < input.tick) {
            ++insert_pos;
        }
        if (insert_pos == inputs.end() || insert_pos->tick != input.tick) {
            inputs.insert(insert_pos, input);
        }

        // 限制队列大小
        while (inputs.size() > 120) {  // 2 秒 @ 60Hz
            inputs.pop_front();
        }
    }

    void Update() {
        current_tick_++;

        // 处理每个玩家的输入
        for (auto& [hash, player] : players_) {
            // 找到当前 tick 的输入
            PlayerInput current_input{current_tick_, Vector2(0, 0), false};

            for (const auto& input : player.pending_inputs) {
                if (input.tick == current_tick_) {
                    current_input = input;
                    break;
                }
            }

            // 权威模拟
            player.state = PhysicsSimulator::Simulate(player.state, current_input, TICK_DT);
            player.last_processed_input_tick = current_tick_;

            // 清理已处理的旧输入
            while (!player.pending_inputs.empty() &&
                   player.pending_inputs.front().tick <= current_tick_) {
                player.pending_inputs.pop_front();
            }
        }
    }

    void BroadcastState() {
        // 格式: [state_count:1][(entity_id:4, pos_x:4, pos_y:4, vel_x:4, vel_y:4, ground:1) * count]
        uint8_t buffer[1024];
        buffer[0] = (uint8_t)players_.size();
        size_t offset = 1;

        for (const auto& [hash, player] : players_) {
            if (offset + 21 > sizeof(buffer)) break;

            memcpy(buffer + offset, &player.entity_id, 4); offset += 4;
            memcpy(buffer + offset, &player.state.position.x, 4); offset += 4;
            memcpy(buffer + offset, &player.state.position.y, 4); offset += 4;
            memcpy(buffer + offset, &player.state.velocity.x, 4); offset += 4;
            memcpy(buffer + offset, &player.state.velocity.y, 4); offset += 4;
            buffer[offset] = player.state.on_ground ? 1 : 0; offset += 1;
        }

        // 广播给所有玩家，附带最后处理的输入 tick
        for (const auto& [hash, player] : players_) {
            uint8_t send_buffer[1024];
            // 添加头部: [last_processed_tick:4]
            memcpy(send_buffer, &player.last_processed_input_tick, 4);
            memcpy(send_buffer + 4, buffer, offset);
            socket_.SendTo(send_buffer, 4 + offset, player.addr);
        }
    }

    void Poll() {
        char buffer[1024];
        NetworkAddress from;

        while (true) {
            int len = socket_.RecvFrom(buffer, sizeof(buffer), from);
            if (len <= 0) break;
            ProcessPacket(from, (uint8_t*)buffer, len);
        }
    }

    void Run() {
        auto last_tick = std::chrono::steady_clock::now();

        while (true) {
            Poll();

            auto now = std::chrono::steady_clock::now();
            float elapsed = std::chrono::duration<float>(now - last_tick).count();

            if (elapsed >= TICK_DT) {
                Update();
                BroadcastState();
                last_tick = now;
            }

            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }
    }
};

// ============================================================================
// 预测客户端
// ============================================================================

class PredictiveClient {
    UDPSocket socket_;
    NetworkAddress server_addr_;
    uint32_t local_tick_ = 0;
    uint32_t entity_id_ = 0;

    // 预测状态
    PlayerState predicted_state_;
    PlayerState last_server_state_;

    // 输入历史（用于回滚重放）
    std::deque<PlayerInput> input_history_;

    // 渲染状态（用于平滑错误修正）
    Vector2 render_position_;
    bool has_server_state_ = false;

public:
    bool Connect(const std::string& server_ip, uint16_t port) {
        if (!socket_.Create()) return false;
        if (!socket_.SetNonBlocking()) return false;
        server_addr_ = NetworkAddress(server_ip, port);

        // 发送空输入包注册
        SendInput(Vector2(0, 0), false);
        return true;
    }

    void SendInput(const Vector2& move_dir, bool jump) {
        uint8_t packet[13];
        memcpy(packet, &local_tick_, 4);
        memcpy(packet + 4, &move_dir.x, 4);
        memcpy(packet + 8, &move_dir.y, 4);
        packet[12] = jump ? 1 : 0;
        socket_.SendTo(packet, 13, server_addr_);
    }

    void ReceiveServerState() {
        char buffer[1024];
        NetworkAddress from;

        while (true) {
            int len = socket_.RecvFrom(buffer, sizeof(buffer), from);
            if (len <= 0) break;
            if (len < 5) continue;

            uint32_t last_processed_tick;
            memcpy(&last_processed_tick, buffer, 4);

            uint8_t player_count = buffer[4];
            size_t offset = 5;

            for (int i = 0; i < player_count && offset + 21 <= (size_t)len; i++) {
                uint32_t id;
                float px, py, vx, vy;
                bool ground;

                memcpy(&id, buffer + offset, 4); offset += 4;
                memcpy(&px, buffer + offset, 4); offset += 4;
                memcpy(&py, buffer + offset, 4); offset += 4;
                memcpy(&vx, buffer + offset, 4); offset += 4;
                memcpy(&vy, buffer + offset, 4); offset += 4;
                ground = buffer[offset] != 0; offset += 1;

                if (entity_id_ == 0) {
                    entity_id_ = id;  // 首次收到自己的 entity_id
                    predicted_state_ = {id, Vector2(px, py), Vector2(vx, vy), ground};
                    render_position_ = Vector2(px, py);
                    last_server_state_ = predicted_state_;
                    has_server_state_ = true;
                    std::cout << "[Client] Assigned entity_id=" << id << "\n";
                }

                if (id == entity_id_) {
                    last_server_state_ = {id, Vector2(px, py), Vector2(vx, vy), ground};
                    Reconcile(last_processed_tick);
                }
            }
        }
    }

    void Reconcile(uint32_t server_last_processed_tick) {
        if (!has_server_state_) return;

        // 找到服务器最后处理的输入对应的预测状态
        // 实际上我们需要回滚到服务器状态，然后重放所有之后的输入

        // 1. 丢弃已确认的输入
        while (!input_history_.empty() &&
               input_history_.front().tick <= server_last_processed_tick) {
            input_history_.pop_front();
        }

        // 2. 从服务器状态开始重放
        PlayerState reconciled = last_server_state_;

        for (const auto& input : input_history_) {
            reconciled = PhysicsSimulator::Simulate(reconciled, input, TICK_DT);
        }

        // 3. 检查差异
        float pos_diff = std::sqrt(
            std::pow(predicted_state_.position.x - reconciled.position.x, 2) +
            std::pow(predicted_state_.position.y - reconciled.position.y, 2)
        );

        if (pos_diff > 0.01f) {
            // 预测错误！回滚到服务器状态并重放
            std::cout << "[Client] Prediction error @tick " << local_tick_
                      << ": diff=" << pos_diff << "m\n";

            predicted_state_ = reconciled;

            // 对于小误差，平滑插值而非直接跳转
            if (pos_diff < 1.0f) {
                // 让渲染位置逐渐追上预测位置
                render_position_ = reconciled.position;
            } else {
                // 大误差直接瞬移（被击退、传送等）
                render_position_ = reconciled.position;
            }
        }
    }

    void Update(const Vector2& input_dir, bool jump) {
        local_tick_++;

        // 记录输入
        PlayerInput input{local_tick_, input_dir, jump};
        input_history_.push_back(input);

        // 限制历史长度
        while (input_history_.size() > 120) {
            input_history_.pop_front();
        }

        // 本地预测
        predicted_state_ = PhysicsSimulator::Simulate(predicted_state_, input, TICK_DT);

        // 发送输入到服务器
        SendInput(input_dir, jump);

        // 平滑渲染位置向预测位置靠拢
        Vector2 diff(predicted_state_.position.x - render_position_.x,
                     predicted_state_.position.y - render_position_.y);
        render_position_.x += diff.x * 0.3f;
        render_position_.y += diff.y * 0.3f;
    }

    void Render() {
        static auto last_print = std::chrono::steady_clock::now();
        auto now = std::chrono::steady_clock::now();

        if (std::chrono::duration_cast<std::chrono::milliseconds>(now - last_print).count() >= 200) {
            std::cout << "[Client] Render pos=(" << render_position_.x << ", " << render_position_.y
                      << ") Predicted pos=(" << predicted_state_.position.x << ", "
                      << predicted_state_.position.y << ") Tick=" << local_tick_ << "\n";
            last_print = now;
        }
    }

    void Run() {
        auto last_tick = std::chrono::steady_clock::now();
        float accumulator = 0.0f;

        // 模拟输入：左右移动
        float move_timer = 0.0f;

        while (true) {
            ReceiveServerState();

            auto now = std::chrono::steady_clock::now();
            float frame_time = std::chrono::duration<float>(now - last_tick).count();
            last_tick = now;
            accumulator += frame_time;

            // 固定时间步长更新
            while (accumulator >= TICK_DT) {
                // 生成测试输入
                move_timer += TICK_DT;
                float move_x = std::sin(move_timer * 2.0f);  // 左右摆动
                Update(Vector2(move_x, 0.0f), false);
                accumulator -= TICK_DT;
            }

            Render();
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }
    }
};

// ============================================================================
// 主函数
// ============================================================================

int main(int argc, char** argv) {
    NetworkInit net_init;

    if (argc > 1 && std::string(argv[1]) == "server") {
        PredictiveServer server;
        if (server.Start(7777)) {
            std::cout << "Predictive Server started on port 7777\n";
            server.Run();
        }
    } else {
        PredictiveClient client;
        if (client.Connect("127.0.0.1", 7777)) {
            std::cout << "Predictive Client connecting...\n";
            client.Run();
        }
    }

    return 0;
}
```

**运行方式：**

```bash
# 编译
g++ -std=c++17 prediction_reconciliation.cpp -o prediction_reconciliation

# 启动服务器
./prediction_reconciliation server

# 启动客户端
./prediction_reconciliation client
```

**预期输出：**

```
[Server] Predictive Server started on port 7777
[Server] Player 1 connected from 127.0.0.1:54321

[Client] Predictive Client connecting...
[Client] Assigned entity_id=1
[Client] Render pos=(0.15, 0) Predicted pos=(0.17, 0) Tick=1
[Client] Render pos=(0.31, 0) Predicted pos=(0.33, 0) Tick=2
...
[Client] Prediction error @tick 45: diff=0.05m
[Client] Render pos=(12.5, 0) Predicted pos=(12.5, 0) Tick=60
```

**关键观察：**

1. 客户端的 `Render pos` 和 `Predicted pos` 通常几乎一致——这是预测正确的正常情况。
2. 当网络抖动导致服务器状态与预测不一致时，会出现 `Prediction error` 日志，客户端回滚并重放。
3. 小误差（< 1m）通过平滑插值修正，大误差直接瞬移。

---

## 3. 练习

### 练习 1：实现 RTT 平滑估计

在 UDP 客户端示例中，RTT 测量值会有抖动。实现一个**指数加权移动平均（EWMA）**来平滑 RTT 估计：

```cpp
float smoothed_rtt = 0.0f;
float rtt_variance = 0.0f;
static constexpr float ALPHA = 0.125f;  // RTT 平滑系数
static constexpr float BETA = 0.25f;    // 方差平滑系数

// 每次测量到新 RTT：
float diff = measured_rtt - smoothed_rtt;
smoothed_rtt += ALPHA * diff;
rtt_variance += BETA * (std::abs(diff) - rtt_variance);

// 超时重传时间 = smoothed_rtt + 4 * rtt_variance
float rto = smoothed_rtt + 4.0f * rtt_variance;
```

**要求：**
- 修改 UDP 客户端，实现上述 RTT 平滑算法
- 打印平滑后的 RTT 和计算出的 RTO
- 模拟网络抖动（在本地加入随机延迟），观察平滑效果

### 练习 2：实现增量快照同步

在快照同步示例的基础上，实现**增量同步（Delta Compression）**：

**要求：**
1. 服务器记录每个客户端最后确认的快照 tick（通过 ACK 包）
2. 发送快照时，只包含自基准 tick 以来发生变化的实体字段
3. 使用位掩码标记哪些字段发生了变化：
   ```cpp
   struct EntityDelta {
       uint32_t entity_id;
       uint16_t changed_mask;  // bit 0=position, bit 1=velocity, bit 2=health
       // 只序列化 changed_mask 标记的字段
   };
   ```
4. 实现客户端的 ACK 机制（每收到一个快照，发送确认）
5. 统计并打印带宽节省比例：
   ```
   Full snapshot size: 256 bytes
   Delta snapshot size: 45 bytes
   Savings: 82.4%
   ```

### 练习 3（可选）：实现简单的延迟补偿命中判定

扩展预测客户端/服务器示例，添加射击机制：

**要求：**
1. 客户端发送射击请求时，附带当前的本地 tick
2. 服务器收到射击请求后：
   - 计算射击发生时的服务器 tick（考虑网络延迟）
   - 将所有其他玩家的位置回滚到该 tick 的历史状态
   - 进行射线检测判定命中
   - 恢复当前状态
3. 服务器维护一个**历史状态环缓冲区**（如最近 2 秒，120 tick @ 60Hz）
4. 添加一个静止的"靶子"实体，测试以下场景：
   - 客户端 A 在 tick 100 射击靶子
   - 由于延迟，服务器在 tick 105 收到请求
   - 服务器回滚到 tick 100 的状态进行判定
   - 判定结果与客户端预期一致

**提示：** 历史状态缓冲区可以这样实现：

```cpp
static constexpr int HISTORY_SIZE = 128;  // 约 2 秒 @ 60Hz
std::array<WorldState, HISTORY_SIZE> state_history_;

WorldState& GetHistoricalState(uint32_t tick) {
    return state_history_[tick % HISTORY_SIZE];
}
```

---

## 3.5 参考答案

> [!tip]- 练习 1：RTT 平滑估计 (EWMA)
>
> 基于 `udp_client.cpp` 添加 EWMA RTT 平滑和网络抖动模拟。
>
> ```cpp
> // ============================================================
> // udp_client_ewma.cpp — 带 EWMA RTT 平滑 + 抖动模拟的客户端
> // ============================================================
> #include "udp_socket.h"
> #include <chrono>
> #include <thread>
> #include <random>
> #include <cmath>
>
> struct PacketHeader {
>     uint32_t sequence;
>     uint32_t timestamp_ms;
> };
>
> // ——— EWMA RTT 估计器 ———
> class RttEstimator {
> public:
>     static constexpr float ALPHA = 0.125f;   // RTT 平滑系数
>     static constexpr float BETA  = 0.25f;    // 方差平滑系数
>     static constexpr float K     = 4.0f;     // RTO 倍数
>     static constexpr float MIN_RTO_MS = 50.0f;
>     static constexpr float MAX_RTO_MS = 3000.0f;
>
>     void AddSample(float measured_rtt_ms) {
>         if (first_sample_) {
>             // 首次测量直接初始化，避免从 0 开始
>             smoothed_rtt_ = measured_rtt_ms;
>             rtt_variance_ = measured_rtt_ms * 0.5f;
>             first_sample_ = false;
>         } else {
>             float diff = measured_rtt_ms - smoothed_rtt_;
>             smoothed_rtt_ += ALPHA * diff;
>             // 使用 fabsf(diff) 而非 diff 的平方，计算成本更低
>             rtt_variance_ += BETA * (std::fabs(diff) - rtt_variance_);
>         }
>         rto_ = std::clamp(smoothed_rtt_ + K * rtt_variance_, MIN_RTO_MS, MAX_RTO_MS);
>     }
>
>     float SmoothedRtt() const { return smoothed_rtt_; }
>     float RttVariance() const { return rtt_variance_; }
>     float Rto()          const { return rto_; }
>
> private:
>     float smoothed_rtt_ = 0.0f;
>     float rtt_variance_ = 0.0f;
>     float rto_          = MIN_RTO_MS;
>     bool  first_sample_ = true;
> };
>
> // ——— 网络抖动模拟器 ———
> class JitterSimulator {
> public:
>     JitterSimulator(float base_delay_ms, float jitter_range_ms)
>         : base_delay_(base_delay_ms)
>         , jitter_range_(jitter_range_ms)
>         , rng_(std::random_device{}())
>         , dist_(0.0f, 1.0f) {}
>
>     // 返回模拟抖动后的延迟，范围 [base - range/2, base + range/2]
>     float ApplyJitter(float original_rtt_ms) {
>         float jitter = (dist_(rng_) - 0.5f) * jitter_range_;
>         return original_rtt_ms + jitter;
>     }
>
>     // 模拟丢包，概率 0..1
>     bool ShouldDrop(float drop_probability = 0.05f) {
>         return dist_(rng_) < drop_probability;
>     }
>
> private:
>     float base_delay_;
>     float jitter_range_;
>     std::mt19937 rng_;
>     std::uniform_real_distribution<float> dist_;
> };
>
> int main() {
>     NetworkInit net_init;
>
>     UDPSocket client;
>     if (!client.Create()) return 1;
>     if (!client.SetNonBlocking()) return 1;
>
>     NetworkAddress server_addr("127.0.0.1", 7777);
>     std::cout << "[Client] Connecting to " << server_addr.ToString() << "\n";
>
>     uint32_t sequence = 0;
>     char recv_buffer[1024];
>
>     RttEstimator rtt_estimator;
>     // 模拟 20ms 基础延迟 + ±10ms 抖动
>     JitterSimulator jitter(20.0f, 10.0f);
>
>     // 滑动窗口统计原始 RTT（用于对比平滑效果）
>     static constexpr int WINDOW = 10;
>     float raw_rtt_window[WINDOW] = {};
>     int window_idx = 0;
>
>     while (true) {
>         // 构造心跳包
>         PacketHeader header;
>         header.sequence = sequence++;
>         header.timestamp_ms = static_cast<uint32_t>(
>             std::chrono::duration_cast<std::chrono::milliseconds>(
>                 std::chrono::steady_clock::now().time_since_epoch()
>             ).count()
>         );
>
>         const char* payload = "Hello Server!";
>         char send_buffer[256];
>         memcpy(send_buffer, &header, sizeof(header));
>         memcpy(send_buffer + sizeof(header), payload, strlen(payload));
>
>         client.SendTo(send_buffer, sizeof(header) + strlen(payload), server_addr);
>
>         // 等待响应
>         auto send_time = std::chrono::steady_clock::now();
>         bool received = false;
>
>         while (!received) {
>             NetworkAddress from;
>             int len = client.RecvFrom(recv_buffer, sizeof(recv_buffer), from);
>
>             if (len > 0) {
>                 auto recv_time = std::chrono::steady_clock::now();
>                 float raw_rtt = std::chrono::duration<float, std::milli>(
>                     recv_time - send_time).count();
>
>                 // 应用抖动模拟
>                 float jittered_rtt = jitter.ApplyJitter(raw_rtt);
>                 rtt_estimator.AddSample(jittered_rtt);
>
>                 // 记录原始 RTT 用于对比
>                 raw_rtt_window[window_idx % WINDOW] = jittered_rtt;
>                 window_idx++;
>
>                 PacketHeader* resp = (PacketHeader*)recv_buffer;
>                 std::cout << "[Client] seq=" << resp->sequence
>                           << " | raw_rtt=" << jittered_rtt << "ms"
>                           << " | smoothed=" << rtt_estimator.SmoothedRtt() << "ms"
>                           << " | var=" << rtt_estimator.RttVariance() << "ms"
>                           << " | RTO=" << rtt_estimator.Rto() << "ms\n";
>
>                 received = true;
>             }
>
>             auto elapsed = std::chrono::steady_clock::now() - send_time;
>             if (elapsed > std::chrono::milliseconds(1500)) {
>                 std::cout << "[Client] Timeout for seq=" << header.sequence << "\n";
>                 break;
>             }
>
>             std::this_thread::sleep_for(std::chrono::milliseconds(1));
>         }
>
>         // 每 WINDOW 次打印对比统计
>         if (window_idx > 0 && window_idx % WINDOW == 0) {
>             float raw_avg = 0.0f;
>             for (int i = 0; i < WINDOW; i++) raw_avg += raw_rtt_window[i];
>             raw_avg /= WINDOW;
>             std::cout << "--- Window avg: raw=" << raw_avg
>                       << "ms, smoothed=" << rtt_estimator.SmoothedRtt()
>                       << "ms, RTO=" << rtt_estimator.Rto() << "ms ---\n";
>         }
>
>         std::this_thread::sleep_for(std::chrono::seconds(1));
>     }
>     return 0;
> }
> ```
>
> **关键说明：**
>
> - 首次测量用实际 RTT 初始化 `smoothed_rtt_`，避免从 0 开始的冷启动偏差
> - `fabsf(diff)` 替代平方，节省浮点运算——游戏网络层需要极低开销
> - `RTO` 被钳制在 `[50ms, 3000ms]`，防止极端值导致超时过长或过短
> - `JitterSimulator` 可调 base_delay / jitter_range 观察不同网络条件下的平滑效果

> [!tip]- 练习 2：增量快照同步 (Delta Compression)
>
> 在 `SnapshotServer` 基础上添加客户端 ACK、基准帧管理、位掩码差分序列化、带宽统计。
>
> ```cpp
> // ============================================================
> // delta_snapshot.h — 增量快照同步核心数据结构
> // ============================================================
> #pragma once
> #include <cstdint>
> #include <vector>
> #include <cstring>
>
> // 实体字段位掩码定义
> enum class EntityField : uint16_t {
>     POSITION   = 1 << 0,   // 位置 (12 bytes: 3×float)
>     VELOCITY   = 1 << 1,   // 速度 (12 bytes)
>     HEALTH     = 1 << 2,   // 生命值 (4 bytes)
>     ROTATION   = 1 << 3,   // 朝向 (4 bytes: 1×float yaw)
>     TIMESTAMP  = 1 << 4,   // 时间戳 (4 bytes)
>     ALL        = 0xFFFF,
> };
>
> inline uint16_t operator|(EntityField a, EntityField b) {
>     return static_cast<uint16_t>(a) | static_cast<uint16_t>(b);
> }
>
> inline bool HasField(uint16_t mask, EntityField f) {
>     return (mask & static_cast<uint16_t>(f)) != 0;
> }
>
> // 字段字节数（用于带宽统计）
> static constexpr int FIELD_SIZE_POSITION  = 12;
> static constexpr int FIELD_SIZE_VELOCITY  = 12;
> static constexpr int FIELD_SIZE_HEALTH    = 4;
> static constexpr int FIELD_SIZE_ROTATION  = 4;
> static constexpr int FIELD_SIZE_TIMESTAMP = 4;
> static constexpr int FULL_SNAPSHOT_PER_ENTITY =
>     FIELD_SIZE_POSITION + FIELD_SIZE_VELOCITY + FIELD_SIZE_HEALTH
>     + FIELD_SIZE_ROTATION + FIELD_SIZE_TIMESTAMP;  // = 36 bytes/entity
>
> // 单个实体的增量
> struct EntityDelta {
>     uint32_t entity_id;
>     uint16_t changed_mask;
>     // 只包含变化字段的数据（按掩码顺序序列化）
>     std::vector<uint8_t> data;
> };
>
> // 增量快照包
> struct DeltaSnapshot {
>     uint32_t baseline_tick;    // 基准帧号（客户端确认过的）
>     uint32_t delta_tick;       // 当前帧号
>     std::vector<EntityDelta> deltas;
> };
>
> // ============================================================
> // 服务器端：记录基准帧、计算差分、统计带宽
> // ============================================================
> #include "udp_socket.h"
> #include <map>
> #include <unordered_map>
> #include <deque>
> #include <chrono>
>
> // 服务器端保存的完整实体状态（用于差分对比）
> struct ServerEntityState {
>     uint32_t entity_id;
>     float pos_x, pos_y, pos_z;
>     float vel_x, vel_y, vel_z;
>     float health;
>     float rotation_yaw;
>     uint32_t timestamp_ms;
> };
>
> // 每个客户端连接的基准帧快照
> struct ClientBaseline {
>     uint32_t acked_tick = 0;
>     std::unordered_map<uint32_t, ServerEntityState> entities; // 客户端"看到的"最后一帧
> };
>
> class DeltaSnapshotServer {
> public:
>     static constexpr float TICK_RATE = 20.0f;
>     static constexpr float TICK_DT   = 1.0f / TICK_RATE;
>
>     // —— 带宽统计 ——
>     struct BandwidthStats {
>         uint64_t full_snapshot_bytes   = 0;  // 累计完整快照字节
>         uint64_t delta_snapshot_bytes  = 0;  // 累计增量快照字节
>         uint64_t total_packets         = 0;
>
>         void RecordDelta(size_t bytes) {
>             delta_snapshot_bytes += bytes;
>             full_snapshot_bytes += simulated_full_bytes_; // 假设同一帧发完整快照
>             total_packets++;
>         }
>
>         void SetSimulatedFullBytes(size_t bytes) { simulated_full_bytes_ = bytes; }
>
>         float SavingsPercent() const {
>             if (full_snapshot_bytes == 0) return 0.0f;
>             return (1.0f - (float)delta_snapshot_bytes / (float)full_snapshot_bytes) * 100.0f;
>         }
>
>         void Print() const {
>             std::cout << "Full snapshot (simulated): " << full_snapshot_bytes << " bytes\n";
>             std::cout << "Delta snapshot (actual):  " << delta_snapshot_bytes << " bytes\n";
>             std::cout << "Savings: " << SavingsPercent() << "%\n";
>         }
>
>     private:
>         size_t simulated_full_bytes_ = 0;
>     };
>
>     // ——— 核心方法 ———
>
>     // 序列化完整快照（基准帧）
>     static void SerializeFullSnapshot(const std::vector<ServerEntityState>& entities,
>                                        std::vector<uint8_t>& out) {
>         out.clear();
>         for (const auto& e : entities) {
>             AppendU32(out, e.entity_id);
>             AppendFloat(out, e.pos_x);
>             AppendFloat(out, e.pos_y);
>             AppendFloat(out, e.pos_z);
>             AppendFloat(out, e.vel_x);
>             AppendFloat(out, e.vel_y);
>             AppendFloat(out, e.vel_z);
>             AppendFloat(out, e.health);
>             AppendFloat(out, e.rotation_yaw);
>             AppendU32(out, e.timestamp_ms);
>         }
>     }
>
>     // 对指定客户端计算增量快照
>     static DeltaSnapshot ComputeDelta(
>         const std::vector<ServerEntityState>& current,
>         ClientBaseline& baseline,
>         uint32_t delta_tick)
>     {
>         DeltaSnapshot snap;
>         snap.baseline_tick = baseline.acked_tick;
>         snap.delta_tick = delta_tick;
>
>         for (const auto& cur : current) {
>             EntityDelta delta;
>             delta.entity_id = cur.entity_id;
>             delta.changed_mask = 0;
>
>             auto it = baseline.entities.find(cur.entity_id);
>
>             if (it == baseline.entities.end()) {
>                 // 新实体：发送全部字段
>                 delta.changed_mask = static_cast<uint16_t>(EntityField::ALL);
>                 SerializeEntityFields(cur, delta.changed_mask, delta.data);
>             } else {
>                 const auto& prev = it->second;
>                 // 逐字段比较，只标记变化的
>                 if (prev.pos_x != cur.pos_x || prev.pos_y != cur.pos_y || prev.pos_z != cur.pos_z)
>                     delta.changed_mask |= EntityField::POSITION;
>                 if (prev.vel_x != cur.vel_x || prev.vel_y != cur.vel_y || prev.vel_z != cur.vel_z)
>                     delta.changed_mask |= EntityField::VELOCITY;
>                 if (prev.health != cur.health)
>                     delta.changed_mask |= EntityField::HEALTH;
>                 if (prev.rotation_yaw != cur.rotation_yaw)
>                     delta.changed_mask |= EntityField::ROTATION;
>                 if (prev.timestamp_ms != cur.timestamp_ms)
>                     delta.changed_mask |= EntityField::TIMESTAMP;
>
>                 if (delta.changed_mask != 0) {
>                     SerializeEntityFields(cur, delta.changed_mask, delta.data);
>                 }
>             }
>
>             if (delta.changed_mask != 0) {
>                 snap.deltas.push_back(delta);
>             }
>
>             // 更新基线
>             baseline.entities[cur.entity_id] = cur;
>         }
>
>         // 清理基准中已不存在的实体（已销毁）
>         for (auto it = baseline.entities.begin(); it != baseline.entities.end(); ) {
>             bool found = false;
>             for (const auto& cur : current) {
>                 if (cur.entity_id == it->first) { found = true; break; }
>             }
>             if (!found) {
>                 it = baseline.entities.erase(it);
>             } else {
>                 ++it;
>             }
>         }
>
>         baseline.acked_tick = delta_tick;
>         return snap;
>     }
>
>     // 序列化增量快照为网络字节流
>     static void SerializeDeltaSnapshot(const DeltaSnapshot& snap, std::vector<uint8_t>& out) {
>         out.clear();
>         AppendU32(out, snap.baseline_tick);
>         AppendU32(out, snap.delta_tick);
>         AppendU16(out, static_cast<uint16_t>(snap.deltas.size()));
>
>         for (const auto& delta : snap.deltas) {
>             AppendU32(out, delta.entity_id);
>             AppendU16(out, delta.changed_mask);
>             // 变化的字段数据直接追加
>             out.insert(out.end(), delta.data.begin(), delta.data.end());
>         }
>     }
>
>     // 客户端反序列化
>     static void DeserializeDeltaSnapshot(const uint8_t* data, size_t len,
>                                           DeltaSnapshot& snap) {
>         size_t off = 0;
>         snap.baseline_tick = ReadU32(data, off); off += 4;
>         snap.delta_tick    = ReadU32(data, off); off += 4;
>         uint16_t count     = ReadU16(data, off); off += 2;
>
>         snap.deltas.resize(count);
>         for (auto& delta : snap.deltas) {
>             delta.entity_id    = ReadU32(data, off); off += 4;
>             delta.changed_mask = ReadU16(data, off); off += 2;
>
>             // 根据掩码计算数据长度
>             int field_bytes = 0;
>             if (HasField(delta.changed_mask, EntityField::POSITION))  field_bytes += FIELD_SIZE_POSITION;
>             if (HasField(delta.changed_mask, EntityField::VELOCITY))  field_bytes += FIELD_SIZE_VELOCITY;
>             if (HasField(delta.changed_mask, EntityField::HEALTH))    field_bytes += FIELD_SIZE_HEALTH;
>             if (HasField(delta.changed_mask, EntityField::ROTATION))  field_bytes += FIELD_SIZE_ROTATION;
>             if (HasField(delta.changed_mask, EntityField::TIMESTAMP)) field_bytes += FIELD_SIZE_TIMESTAMP;
>
>             delta.data.assign(data + off, data + off + field_bytes);
>             off += field_bytes;
>         }
>     }
>
> private:
>     // ——— 辅助序列化/反序列化 ———
>     static void AppendU32(std::vector<uint8_t>& v, uint32_t val) {
>         v.push_back(val & 0xFF);
>         v.push_back((val >> 8) & 0xFF);
>         v.push_back((val >> 16) & 0xFF);
>         v.push_back((val >> 24) & 0xFF);
>     }
>     static void AppendU16(std::vector<uint8_t>& v, uint16_t val) {
>         v.push_back(val & 0xFF);
>         v.push_back((val >> 8) & 0xFF);
>     }
>     static void AppendFloat(std::vector<uint8_t>& v, float val) {
>         uint32_t bits;
>         memcpy(&bits, &val, 4);
>         AppendU32(v, bits);
>     }
>     static uint32_t ReadU32(const uint8_t* data, size_t off) {
>         return data[off] | (data[off+1] << 8) | (data[off+2] << 16) | (data[off+3] << 24);
>     }
>     static uint16_t ReadU16(const uint8_t* data, size_t off) {
>         return data[off] | (data[off+1] << 8);
>     }
>
>     // 按掩码顺序序列化实体字段
>     static void SerializeEntityFields(const ServerEntityState& e, uint16_t mask,
>                                        std::vector<uint8_t>& out) {
>         if (HasField(mask, EntityField::POSITION)) {
>             AppendFloat(out, e.pos_x);
>             AppendFloat(out, e.pos_y);
>             AppendFloat(out, e.pos_z);
>         }
>         if (HasField(mask, EntityField::VELOCITY)) {
>             AppendFloat(out, e.vel_x);
>             AppendFloat(out, e.vel_y);
>             AppendFloat(out, e.vel_z);
>         }
>         if (HasField(mask, EntityField::HEALTH))
>             AppendFloat(out, e.health);
>         if (HasField(mask, EntityField::ROTATION))
>             AppendFloat(out, e.rotation_yaw);
>         if (HasField(mask, EntityField::TIMESTAMP))
>             AppendU32(out, e.timestamp_ms);
>     }
> };
>
> // ============================================================
> // 客户端 ACK 机制集成示例
> // ============================================================
> // 在 SnapshotClient::ReceiveSnapshots() 中，每收到一个快照即发送 ACK：
> //
> // void SendAck(uint32_t received_tick) {
> //     uint8_t packet[7];
> //     packet[0] = (uint8_t)MsgType::CLIENT_ACK;
> //     memcpy(packet + 1, &received_tick, 4);
> //     packet[5] = 0; packet[6] = 0; // 填充
> //     socket_.SendTo(packet, 7, server_addr_);
> // }
> //
> // 服务器端处理 ACK：
> // case MsgType::CLIENT_ACK:
> //     uint32_t acked_tick;
> //     memcpy(&acked_tick, buffer + 1, 4);
> //     baseline.acked_tick = acked_tick;  // 更新该客户端的基准帧
> //     break;
>
> // ============================================================
> // 带宽统计演示
> // ============================================================
> // int main() {
> //     NetworkInit net_init;
> //     DeltaSnapshotServer::BandwidthStats stats;
> //
> //     // 模拟 5 帧：设置完整快照大小
> //     int entity_count = 5;
> //     size_t full_bytes_per_tick = entity_count * FULL_SNAPSHOT_PER_ENTITY; // 180 bytes
> //     stats.SetSimulatedFullBytes(full_bytes_per_tick);
> //
> //     // 模拟增量发送（实际 serialized delta 大小取决于变化量）
> //     // 假设只有 1 个实体的位置变了：delta = header + entity_id + mask + 12 bytes pos
> //     size_t delta_bytes_per_tick = 4 + 4 + 2 + 4 + 2 + 12; // ~28 bytes
> //
> //     for (int i = 0; i < 5; i++) {
> //         stats.RecordDelta(delta_bytes_per_tick);
> //     }
> //     stats.Print();
> //     // 输出: Full snapshot (simulated): 900 bytes
> //     //       Delta snapshot (actual):  140 bytes
> //     //       Savings: 84.4%
> // }
> ```
>
> **关键说明：**
>
> - `changed_mask` 用位掩码标记变化字段，发送端只序列化 `mask` 为 1 的字段，接收端按相同顺序还原
> - 新增实体会设置 `ALL` 掩码，发送完整状态；消失的实体会从 baseline 中移除
> - `serialize`/`deserialize` 必须严格对称——字段顺序和类型一致，否则解码错位
> - 真正的生产环境会使用 `BitWriter`/`BitReader`（教程 2.2 已有），这里用字节流是为了可读性
> - 带宽节省率取决于实体变化率：大量静止实体时可达 90%+；全员移动时也有 ~50%（减少了 `entity_id` 之外的不变字段）

> [!tip]- 练习 3（可选）：延迟补偿命中判定
>
> 扩展 `PredictiveServer`，添加射击请求处理、历史状态环缓冲区、服务器端回滚射线检测。
>
> ```cpp
> // ============================================================
> // lag_compensation.h — 延迟补偿命中判定
> // ============================================================
> #pragma once
> #include <array>
> #include <vector>
> #include <cmath>
> #include <cstring>
> #include <algorithm>
>
> static constexpr int HISTORY_SIZE = 128;   // ~2 秒 @ 60Hz
> static constexpr float MAX_LAG_COMP_MS = 200.0f; // 最大回滚时间
> static constexpr int MAX_LAG_COMP_TICKS =
>     static_cast<int>(MAX_LAG_COMP_MS / (1000.0f / 60.0f)); // ≈12 ticks
>
> struct Vec3 {
>     float x, y, z;
>     Vec3(float x=0, float y=0, float z=0) : x(x), y(y), z(z) {}
>     Vec3 operator+(const Vec3& o) const { return {x+o.x, y+o.y, z+o.z}; }
>     Vec3 operator-(const Vec3& o) const { return {x-o.x, y-o.y, z-o.z}; }
>     Vec3 operator*(float s) const { return {x*s, y*s, z*s}; }
>     float Dot(const Vec3& o) const { return x*o.x + y*o.y + z*o.z; }
>     float LengthSq() const { return Dot(*this); }
>     float Length() const { return std::sqrt(LengthSq()); }
>     Vec3 Normalized() const {
>         float len = Length();
>         return len > 0.0001f ? (*this * (1.0f / len)) : Vec3{};
>     }
> };
>
> // 世界状态快照（存入历史缓冲区）
> struct WorldState {
>     uint32_t tick;
>     // 所有非 shooter 实体的位置 + 碰撞体半径
>     struct EntityRecord {
>         uint32_t entity_id;
>         Vec3 position;
>         float hit_radius;  // 碰撞球半径
>     };
>     std::vector<EntityRecord> entities;
> };
>
> // 客户端射击请求
> struct FireRequest {
>     uint32_t client_tick;     // 客户端射击时的本地 tick
>     uint32_t shooter_entity_id;
>     Vec3 shoot_origin;
>     Vec3 shoot_direction;     // 单位向量
>     float max_distance;
> };
>
> // 射击结果
> struct HitResult {
>     bool hit;
>     uint32_t hit_entity_id;
>     Vec3 hit_point;
>     uint32_t hit_tick;  // 实际判定用的历史 tick
> };
>
> // ============================================================
> // 服务器端：历史状态环缓冲区 + 回滚判定
> // ============================================================
> class LagCompensationServer {
> public:
>     // ——— 历史状态管理 ———
>
>     void RecordWorldState(uint32_t tick, const std::vector<WorldState::EntityRecord>& entities) {
>         WorldState& state = state_history_[tick % HISTORY_SIZE];
>         state.tick = tick;
>         state.entities = entities;
>     }
>
>     const WorldState* GetHistoricalState(uint32_t tick) const {
>         const WorldState& state = state_history_[tick % HISTORY_SIZE];
>         if (state.tick != tick) return nullptr; // 已被覆盖或未写入
>         return &state;
>     }
>
>     // ——— 射线球体检测 ———
>     // 射线: origin + t * direction, t ∈ [0, max_dist]
>     // 球体: center, radius
>     // 返回 t >= 0 或 -1 表示未击中
>     static float RaySphereIntersect(const Vec3& origin, const Vec3& dir,
>                                      const Vec3& center, float radius) {
>         Vec3 oc = origin - center;
>         float a = dir.Dot(dir);          // 应为 1.0（单位向量）
>         float b = 2.0f * oc.Dot(dir);
>         float c = oc.Dot(oc) - radius * radius;
>         float discriminant = b * b - 4.0f * a * c;
>
>         if (discriminant < 0.0f) return -1.0f;
>
>         float sqrt_d = std::sqrt(discriminant);
>         float t1 = (-b - sqrt_d) / (2.0f * a);
>         float t2 = (-b + sqrt_d) / (2.0f * a);
>
>         // 返回最近的正面交点
>         if (t1 >= 0.0f) return t1;
>         if (t2 >= 0.0f) return t2;
>         return -1.0f;
>     }
>
>     // ——— 带延迟补偿的命中判定 ———
>
>     HitResult ProcessFireRequest(const FireRequest& req, uint32_t server_receive_tick) {
>         HitResult result{};
>         result.hit = false;
>         result.hit_entity_id = 0;
>         result.hit_tick = req.client_tick;
>
>         // 1. 计算客户端请求的 tick 是否在可回滚范围内
>         int tick_delta = static_cast<int>(server_receive_tick) - static_cast<int>(req.client_tick);
>         if (tick_delta < 0 || tick_delta > MAX_LAG_COMP_TICKS) {
>             // 超出回滚时间窗口：要么太旧（被覆盖），要么是未来 tick（作弊/时钟不同步）
>             // 退化处理：使用当前 tick 判定
>             result.hit_tick = server_receive_tick;
>             return DoHitTest(req, server_receive_tick);
>         }
>
>         // 2. 获取历史状态
>         const WorldState* hist = GetHistoricalState(req.client_tick);
>         if (!hist) {
>             // 状态已被覆盖，无法回滚——使用当前状态判定
>             // 这会导致客户端看到"明明瞄准了却没打中"的情况
>             result.hit_tick = server_receive_tick;
>             return DoHitTest(req, server_receive_tick);
>         }
>
>         // 3. 在历史状态下执行射线检测（排除 shooter 自身）
>         return DoHitTestAgainst(req, *hist);
>     }
>
> private:
>     HitResult DoHitTestAgainst(const FireRequest& req, const WorldState& hist) {
>         HitResult result{};
>         result.hit = false;
>         result.hit_tick = hist.tick;
>
>         float closest_t = req.max_distance;
>         Vec3 dir_norm = req.shoot_direction.Normalized();
>
>         for (const auto& ent : hist.entities) {
>             if (ent.entity_id == req.shooter_entity_id) continue; // 排除自身
>
>             float t = RaySphereIntersect(req.shoot_origin, dir_norm,
>                                           ent.position, ent.hit_radius);
>             if (t >= 0.0f && t < closest_t) {
>                 closest_t = t;
>                 result.hit = true;
>                 result.hit_entity_id = ent.entity_id;
>                 result.hit_point = req.shoot_origin + dir_norm * t;
>             }
>         }
>         return result;
>     }
>
>     // 无回滚的简单判定（当前 tick）
>     HitResult DoHitTest(const FireRequest& req, uint32_t current_tick) {
>         const WorldState* cur = GetHistoricalState(current_tick);
>         if (!cur) return {};
>         return DoHitTestAgainst(req, *cur);
>     }
>
>     std::array<WorldState, HISTORY_SIZE> state_history_;
> };
>
> // ============================================================
> // 集成到 PredictiveServer 的示例
> // ============================================================
> //
> // 在 PredictiveServer 中添加：
> //   LagCompensationServer lag_comp_;
> //
> // 每帧 Update() 后记录历史：
> //   void RecordHistory() {
> //       std::vector<WorldState::EntityRecord> records;
> //       for (const auto& [hash, player] : players_) {
> //           records.push_back({
> //               player.entity_id,
> //               Vec3{player.state.position.x, 0, player.state.position.y},
> //               0.5f  // 碰撞半径
> //           });
> //       }
> //       // 添加"靶子"实体
> //       records.push_back({TARGET_ENTITY_ID, Vec3{10.0f, 0, 5.0f}, 1.0f});
> //       lag_comp_.RecordWorldState(current_tick_, records);
> //   }
> //
> // 收到射击请求时处理:
> //   case MsgType::FIRE_REQUEST:
> //       FireRequest req;
> //       memcpy(&req, buffer + 1, sizeof(req));  // 见下方结构
> //       HitResult hit = lag_comp_.ProcessFireRequest(req, current_tick_);
> //       // 广播结果给所有客户端
> //       break;
>
> // ============================================================
> // 客户端发送射击请求
> // ============================================================
> //
> // void SendFireRequest(const Vec3& origin, const Vec3& dir) {
> //     uint8_t packet[1 + sizeof(FireRequest)];
> //     packet[0] = (uint8_t)MsgType::FIRE_REQUEST;
> //
> //     FireRequest req;
> //     req.client_tick = local_tick_;          // 客户端当前 tick
> //     req.shooter_entity_id = entity_id_;
> //     req.shoot_origin = origin;
> //     req.shoot_direction = dir;
> //     req.max_distance = 100.0f;
> //
> //     memcpy(packet + 1, &req, sizeof(req));
> //     socket_.SendTo(packet, 1 + sizeof(req), server_addr_);
> // }
>
> // ============================================================
> // 集成测试：静态靶子命中判定
> // ============================================================
> //
> // 场景：
> //   - 靶子 entity_id=999，位置 (10, 0, 5)，碰撞半径 1.0
> //   - 客户端 A 在 tick=100 时射击 origin=(0,0,0) dir=(0.89, 0, 0.45)
> //   - 由于 80ms 网络延迟，服务器在 tick=105 收到请求
> //   - 服务器回滚到 tick=100 的历史状态
> //   - 判定结果：命中靶子，hit_point≈(10, 0, 5)
> //
> // 预期日志：
> //   [Client] Fire! tick=100 origin=(0,0,0) dir=(0.89,0,0.45)
> //   [Server] Recv fire from entity=1 client_tick=100 (server_tick=105)
> //   [Server] Lag comp: rewound 5 ticks (100→105), hit entity 999!
> //   [Client] Hit confirmed! entity=999 point=(10.0,0,5.0)
> ```
>
> **关键说明：**
>
> - `tick % HISTORY_SIZE` 是典型的环缓冲区索引方式；通过存储 `tick` 字段验证是否被覆盖
> - `MAX_LAG_COMP_MS = 200ms` 限制了最大回滚时间：超出窗口的射击直接使用当前状态判定（防止滥用）
> - 射线-球体检测用解析几何公式，避免了需要在历史缓冲区中存储完整碰撞几何体
> - 实际游戏中还需要处理：弹道扩散（随机种子存储在请求中）、穿墙检测（需要碰撞网格回滚）、延迟补偿作弊（故意延迟发送以利用回滚机制）
> - 这里使用 `Vec3` 替代教程中的 `Vector3`/`Vector2` 以支持 3D 射击场景
## 4. 扩展阅读

### 经典论文与文章

1. **"1500 Archers on a 28.8: Network Programming in Age of Empires and Beyond"**
   - Mark Terrano, Paul Bettner (Ensemble Studios)
   - 介绍了 AoE 的 P2P 同步架构和 200ms 回合制同步
   - [Gamasutra 原文](https://www.gamasutra.com/view/feature/131503/1500_archers_on_a_288_network_.php)

2. **"Source Multiplayer Networking"**
   - Valve Developer Community
   - 详细讲解 Source 引擎的快照插值、客户端预测、延迟补偿
   - [Valve Wiki](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking)

3. **"Latency Compensating Methods in Client/Server In-game Protocol Design and Optimization"**
   - Yahn W. Bernier (Valve)
   - CS 延迟补偿的权威论文
   - [GDC 2001](https://developer.valvesoftware.com/wiki/Latency_Compensating_Methods_in_Client/Server_In-game_Protocol_Design_and_Optimization)

4. **"It IS Rocket Science!"**
   - Jared Cone (Psyonix)
   - Rocket League 的网络架构：确定性物理 + 输入同步
   - [GDC 2018](https://www.youtube.com/watch?v=ueEmSn9Oad4)

5. **"Overwatch Gameplay Architecture and Netcode"**
   - Timothy Ford (Blizzard)
   - Overwatch 的 ECS 架构和网络同步设计
   - [GDC 2017](https://www.youtube.com/watch?v=W3aieHjyNvw)

6. **"8 Frames in 16ms: Rollback Networking in Mortal Kombat and Injustice 2"**
   - Michael Stallone (NetherRealm Studios)
   - 格斗游戏的回滚网代码
   - [GDC 2018](https://www.youtube.com/watch?v=7jb0FOcImFI)

### 开源实现参考

1. **ENet** — 可靠的 UDP 网络库
   - 提供 UDP 之上的有序、可靠、无序通道
   - 被 Source Engine、Minecraft 等使用
   - [GitHub: lsalzman/enet](http://github.com/lsalzman/enet)

2. **yojimbo** — Glenn Fiedler 的游戏网络库
   - 专为竞技游戏设计
   - 内置客户端-服务器架构、快照同步、连接管理
   - [GitHub: networkprotocol/yojimbo](https://github.com/networkprotocol/yojimbo)

3. **GameNetworkingSockets** — Valve 开源
   - Steam 网络 API 的开源版本
   - 提供 UDP 之上的可靠消息、P2P NAT 穿透
   - [GitHub: ValveSoftware/GameNetworkingSockets](https://github.com/ValveSoftware/GameNetworkingSockets)

4. **GGPO** — 格斗游戏回滚网代码
   - 开源的回滚网络框架
   - 被街霸、骷髅女孩等使用
   - [GitHub: pond3r/ggpo](https://github.com/pond3r/ggpo)

### 书籍

1. **《Multiplayer Game Programming: Architecting Networked Games》**
   - Josh Glazer, Sanjay Madhav
   - 最全面的游戏网络编程教材

2. **《Game Engine Architecture》第 3 版**
   - Jason Gregory
   - 第 11 章 "Networking" 涵盖多人游戏网络基础

---

## 常见陷阱

### 陷阱 1：在客户端信任任何来自客户端的数据

```cpp
// 错误：客户端直接报告位置
void OnClientMessage(PlayerPos pos) {
    player.position = pos;  // 作弊者可以随意传送！
}

// 正确：客户端只报告输入
void OnClientMessage(PlayerInput input) {
    player.state = ServerSimulate(input, player.state);  // 权威计算
}
```

**规则：** 永远假设客户端是恶意的。服务器必须验证所有输入的合法性。

### 陷阱 2：使用浮点数进行跨平台确定性模拟

```cpp
// 危险：不同 CPU/编译器的浮点结果可能不同
float result = std::sin(angle);  // x86 vs ARM 可能有微小差异
```

**后果：** P2P 或确定性回滚架构中，微小的浮点差异会随时间放大，导致不同客户端的世界状态分叉（Desync）。

**解决方案：**
- 使用定点数（Fixed Point）代替浮点数
- 使用确定性数学库（如 [libfixmath](https://github.com/PetteriAimonen/libfixmath)）
- 确保所有平台使用相同的编译器设置（如禁用浮点优化）

### 陷阱 3：忽略时钟同步

```cpp
// 错误：直接使用本地时间戳
uint32_t client_time = GetLocalTime();  // 客户端可以修改系统时间！

// 正确：使用服务器分配的 tick 号
uint32_t server_tick = GetServerTick();  // 服务器是权威时间源
```

**规则：** 游戏逻辑时间以服务器 tick 为准。客户端本地时间仅用于渲染和插值。

### 陷阱 4：预测与插值混用

```cpp
// 错误：对同一实体同时进行预测和插值
void Update() {
    PredictLocalPlayer();   // 预测本地玩家
    InterpolateAllPlayers(); // 插值所有玩家（包括自己！）
}
```

**后果：** 本地玩家会感觉"输入延迟"，因为插值在预测之上又加了一层延迟。

**正确做法：**
- 本地玩家角色：使用预测（立即响应输入）
- 其他玩家/实体：使用插值（平滑显示）
- 两者严格区分，不要混用

### 陷阱 5：快照缓冲区溢出或欠载

```cpp
// 错误：固定插值延迟，不考虑网络状况
static constexpr float INTERP_DELAY = 100.0f;  // 固定 100ms
```

**问题：** 网络抖动大时，100ms 缓冲可能不够，导致插值"饿死"（没有两个快照可插值）；网络稳定时，100ms 又 unnecessarily 增加延迟。

**解决方案：** 动态调整插值延迟：

```cpp
float CalculateInterpDelay() {
    // 基于抖动统计动态调整
    float jitter = CalculateJitter();
    return std::max(50.0f, jitter * 2.0f + 30.0f);  // 至少 50ms，根据抖动增加
}
```

### 陷阱 6：忘记处理乱序包

```cpp
// 错误：总是用最新收到的快照
void OnSnapshot(Snapshot snap) {
    latest_snapshot = snap;  // 如果 snap 是旧的，会覆盖更新的快照！
}

// 正确：按 tick 号管理快照
void OnSnapshot(Snapshot snap) {
    if (snap.tick > latest_tick_) {
        snapshot_buffer_.push_back(snap);
        // ... 保持有序
    }
    // 丢弃旧 tick 的快照
}
```

### 陷阱 7：在渲染线程中直接修改物理状态

```cpp
// 错误：插值结果直接作为物理状态
void Render() {
    player.position = InterpolatePosition();  // 插值是"视觉"位置！
    PhysicsUpdate();  // 用插值位置做物理计算 → 错误
}

// 正确：分离逻辑位置和渲染位置
struct Player {
    Vector3 logic_position;   // 物理/逻辑使用的真实位置
    Vector3 render_position;  // 插值后的显示位置（仅渲染）
};
```

### 陷阱 8：带宽估算不足

```cpp
// 危险：未压缩的快照
struct FullSnapshot {
    EntityState entities[100];  // 100 个实体
};
// 每个实体：id(4) + pos(12) + rot(16) + vel(12) + health(4) = 48 bytes
// 总大小：4800 bytes/tick @ 20Hz = 768,000 bytes/sec ≈ 6.1 Mbps
```

**优化后的估算：**

```cpp
// 优化后：
// - 只发送可见实体（平均 20 个）
// - 增量同步（平均变化 30%）
// - 量化压缩（位置从 12 bytes → 6 bytes）
// 总大小：~20 * 48 * 0.3 * 0.5 ≈ 144 bytes/tick @ 20Hz = 23,040 bytes/sec ≈ 184 kbps
```

**规则：** 设计同步方案时，先做带宽预算。目标玩家的上行通常只有 1-2 Mbps，要预留余量。
