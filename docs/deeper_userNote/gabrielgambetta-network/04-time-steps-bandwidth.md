---
title: "时间步、快照设计与带宽优化"
updated: 2026-06-05
---

# 时间步、快照设计与带宽优化

> 基于笔记: gabrielgambetta-network.md
> 所属教程: 快节奏多人游戏网络架构 — 从 Gambetta 系列到工业实践
> 章: 4/5

---

## 直觉理解：工厂流水线的节拍

前面三章讲的是"怎么处理延迟"，这一章讲的是"怎么管理数据流"。

想象工厂流水线：传送带每 100 毫秒移动一个工位。每个工位上的工人在这 100 毫秒内完成自己的工作，然后把半成品推给下一个人。

**时间步（time step）**就是传送带的节奏。笔记中说：

> 更好的方法是接收客户端输入时将其排队，不做任何处理。游戏世界以较低频率定期更新，例如每秒 10 次。每次更新之间的延迟，即本例中的 100 毫秒，称为时间步。

为什么服务器不以"收到输入就立即处理"的方式工作？原因有二：

1. **计算效率**：批量处理输入比逐个处理更高效（缓存友好、减少锁竞争）
2. **可预测性**：固定步长使得物理模拟结果确定——同样的输入在同样的时间步长下总是产生同样的结果

---

## 时间步设计

### 服务器 tick rate 的选择

笔记提到的 10Hz（100ms 步长）是现代游戏的低端；实际数字取决于游戏类型：

| 游戏类型 | 典型 tick rate | 步长 | 原因 |
|---------|---------------|------|------|
| MMO（WOW） | 10-20 Hz | 50-100ms | 大量玩家，状态变化缓慢 |
| MOBA（LOL） | 30 Hz | 33ms | 需要精确技能判定 |
| FPS（CS:GO） | 64-128 Hz | 8-16ms | 毫秒级射击判定 |
| 格斗（街霸） | 60 Hz | 16ms | P2P rollback，需要高帧率 |
| RTS（星际） | 8-16 Hz（lockstep） | 62-125ms | 所有客户端同步步进 |

**核心权衡**：更高的 tick rate = 更好的响应性和插值质量，但需要更多带宽和 CPU。

### 客户端与服务器的步长可以不同

```python
SERVER_TICK_RATE = 20      # 服务器每秒 20 tick（50ms 步长）
CLIENT_INPUT_RATE = 60     # 客户端每秒采样 60 次输入
SNAPSHOT_RATE = 20         # 每秒发送 20 个世界快照

# 客户端：高频采样输入
# 服务器：批量处理——一个 tick 内处理排队的多个输入
# 快照频率可以 ≤ tick rate（降低带宽而不降低模拟精度）
```

笔记中提到：

> 所有未处理的客户端输入都会被应用（可能以小于时间步的时间增量进行，以使物理效果更可预测）

这意味着服务器在一个 tick 内处理多个客户端输入时，会按时间顺序以**子步长**（sub-step）逐一应用，而不是把它们全部压缩到一次步进中。这保持了物理模拟的精度。

### 实现：服务器 tick 循环

```python
class ServerTickLoop:
    def __init__(self, tick_rate: float = 20.0):
        self.tick_duration = 1.0 / tick_rate  # 秒
        self.sub_step_count = 4  # 每次 tick 细分为 4 个子步
        self.sub_step_dt = self.tick_duration / self.sub_step_count
        self.input_queues: dict[int, list] = {}  # client_id → 排队输入

    def queue_input(self, client_id: int, inp):
        """接收客户端输入，先排队，不立即处理"""
        if client_id not in self.input_queues:
            self.input_queues[client_id] = []
        self.input_queues[client_id].append(inp)

    def tick(self):
        """一次完整的 tick：处理所有排队输入 → 更新世界 → 广播快照"""
        for client_id, queue in self.input_queues.items():
            for inp in queue:
                # 以子步长应用，保持物理精度
                for _ in range(self.sub_step_count):
                    apply_input_to_world(inp, self.sub_step_dt)
            queue.clear()

        # 物理模拟也使用子步长
        for _ in range(self.sub_step_count):
            simulate_physics(self.sub_step_dt)

        # 生成并广播快照
        snapshot = build_snapshot()
        for client_id in self.connected_clients:
            send_snapshot(client_id, snapshot)
```

子步长的数学原理：数值积分（如 Euler、Verlet）的误差与步长的平方成正比。将 50ms 拆分为 4 × 12.5ms 的子步，误差降低 16 倍。详见 [[../../deep-dives/fixed-timestep|固定时间步长深度分析]]。

---

## 快照设计

### 谁应该收到什么？

笔记描述的快照是**全量广播**——所有客户端收到相同的数据。实际中，这浪费了大量带宽。两个关键优化：

#### 兴趣管理（Area of Interest）

```python
def build_snapshot_for_client(client_id: int, world_state: dict) -> dict:
    """只为客户端构建其视野内的实体快照"""
    viewer = world_state[client_id]
    visible_entities = {}

    for eid, entity in world_state.items():
        if eid == client_id:
            continue  # 自己的状态单独处理（在第 1 章中覆盖）
        # 只发送视野范围内的实体
        distance = math.sqrt(
            (entity.x - viewer.x) ** 2 + (entity.y - viewer.y) ** 2
        )
        if distance <= VIEW_DISTANCE:
            # 根据距离调整更新优先级
            if distance < NEAR_DISTANCE:
                priority = 'high'   # 全精度，高频更新
            elif distance < MID_DISTANCE:
                priority = 'medium' # 降低精度
            else:
                priority = 'low'    # 最低精度，最低频率
            visible_entities[eid] = {
                'x': quantize(entity.x, priority),
                'y': quantize(entity.y, priority),
                'z': quantize(entity.z, priority),
                'priority': priority,
            }
    return visible_entities
```

这直接防止了一种常见作弊：**wallhack**（透視）。如果服务器不发送墙后敌人的位置，客户端就无从渲染它们。

#### Delta 压缩（增量编码）

大多数游戏状态在 tick 之间变化很小。发送增量而非全量：

```python
def encode_delta(prev_snapshot: dict, current_state: dict,
                 last_acked_tick: int) -> bytes:
    """
    相对于客户端上次确认的快照，只编码变化的部分。
    
    关键洞察：不需要存储每个 tick 的全量快照用于 delta——
    只需要客户端告知它上次成功收到了哪个 tick 的快照，
    服务器相对于那个 tick 编码当前的差异。
    """
    delta = {}
    for eid, current in current_state.items():
        prev = prev_snapshot.get(eid)

        if prev is None:
            # 新出现的实体，发送全量
            delta[eid] = {'full': serialize_entity(current)}
        else:
            # 已有实体，只发送变化
            changes = {}
            if abs(current['x'] - prev['x']) > EPSILON:
                changes['dx'] = current['x'] - prev['x']
            if abs(current['y'] - prev['y']) > EPSILON:
                changes['dy'] = current['y'] - prev['y']
            if current['is_alive'] != prev['is_alive']:
                changes['alive'] = current['is_alive']
            if changes:
                delta[eid] = changes

    # 标记已消失的实体
    for eid in prev_snapshot:
        if eid not in current_state:
            delta[eid] = {'removed': True}

    return serialize_delta(delta)
```

#### 量化：告别 float32

网络传输中，每字节都很珍贵。将浮点数量化为整数可以节省 50%+ 的带宽：

```python
def quantize_position(value: float, min_val: float, max_val: float,
                      bits: int) -> int:
    """将浮点位置量化为 N 位整数"""
    # 例如：地图 1024m × 1024m，用 16 位量化
    # 精度 = 1024 / 2^16 = 1.56cm —— 对位置来说完全够用
    # 16 bits vs 32 bits (float) → 节省 50% 带宽
    range_val = max_val - min_val
    max_int = (1 << bits) - 1
    normalized = (value - min_val) / range_val
    return int(normalized * max_int)


def dequantize_position(encoded: int, min_val: float, max_val: float,
                        bits: int) -> float:
    """将量化的整数还原为浮点数"""
    range_val = max_val - min_val
    max_int = (1 << bits) - 1
    return min_val + (encoded / max_int) * range_val
```

Quake 3 是最早大量使用量化技术的游戏之一。它将玩家位置量化为 13 位整数（每轴），角度量化为 8 位，使得整个玩家状态在不到 10 个字节内就能传输。[基于内部知识]

---

## 带宽预算

### 典型数据流

```
客户端上行（发送给服务器）:
  输入包（带冗余）: ~12 bytes × 60Hz = 720 bytes/s
  + 偶尔的聊天/命令: 忽略不计
  总计: < 1 KB/s

服务器下行（发送给客户端）:
  无优化全量快照: 10 entities × 40 bytes × 20Hz = 8 KB/s
  增量编码优化:   10 entities × ~8 bytes × 20Hz = 1.6 KB/s
  兴趣管理优化:   3 entities × ~8 bytes × 20Hz = 0.48 KB/s
  （玩家通常只关注周围少数实体）

  64 玩家服务器总下行:
    64 × 1.6 KB/s = ~100 KB/s（增量编码，无兴趣管理）
    64 × 0.48 KB/s = ~30 KB/s（增量 + 兴趣管理）
```

### 实际数据参考

| 游戏 | 上行带宽 | 下行带宽 | tick rate | 说明 |
|------|---------|---------|-----------|------|
| CS:GO | ~5-10 KB/s | ~20-40 KB/s | 64 | 竞争模式 |
| Valorant | ~5 KB/s | ~15-30 KB/s | 128 | 高度优化的网络栈 |
| Overwatch | ~3 KB/s | ~16 KB/s（推测） | 63 | 快照插值架构 |
| Fortnite | ~3-8 KB/s | ~15-30 KB/s | 30 | 100 名玩家 BR |
| WOW | ~1 KB/s | ~3-10 KB/s | 10-20 | 大量玩家，低更新频率 |

[基于内部知识，具体数字可能因更新而异]

---

## UDP vs TCP：传输层选择

笔记没有讨论传输层，但这是一个基础性的设计决策。

### 为什么游戏不用 TCP？

TCP 的两个特性对实时游戏是致命的：

1. **队头阻塞（Head-of-Line Blocking）**：如果数据包 `#5` 丢失，TCP 会停止投递 `#6`、`#7`、`#8`，直到 `#5` 被重传并确认。在游戏中，`#6`（当前位置）比 `#5`（100ms 前的位置）更有价值——宁愿丢旧的也不要卡新的。

2. **拥塞控制**：TCP 检测到丢包后会大幅降低发送速率，然后缓慢恢复。这会导致游戏世界快照的传输速率剧烈波动。

### 游戏通常使用自定义 UDP 协议

```python
# 简化版游戏 UDP 数据包结构
class GamePacket:
    sequence: int           # 包序列号（用于检测丢包和乱序）
    ack: int                # 上次收到的对端包序列号（用于 RTT 估计）
    ack_bitfield: int       # 位图：最近 32 个包中哪些已收到
    payload_type: int       # 0=输入, 1=快照, 2=连接管理
    payload: bytes          # 实际数据

# 可靠性由应用层选择性实现：
# - 输入 → 冗余发送（每个包附带前几个输入）
# - 快照 → 不可靠，丢了就等下一个（插值会处理间隙）
# - 关键事件（拾取物品、伤害确认）→ 应用层 ACK + 重传
```

这种"可靠消息在不可靠信道上"的设计模式被称为 **RUDP（Reliable UDP）** 或自定义可靠性层。Valve 的 Source Engine、Epic 的 Unreal Engine、Unity Transport 都使用类似的设计。[基于内部知识]

---

## 关联主题

- **客户端预测**（第 1 章）：预测消除了服务器 tick rate 对本地响应性的影响——无论服务器是 20Hz 还是 128Hz，本地操作都是即时的
- **实体插值**（第 2 章）：插值延迟通常设为 2× tick 间隔——更高的 tick rate 意味着可以降低插值延迟
- **延迟补偿**（第 3 章）：历史快照的长度由 `MAX_COMPENSATION_MS` 和 tick rate 共同决定——更高的 tick rate 需要更多的快照存储
- **固定时间步长**：独立游戏引擎中时间步实现的完整指南：详见 [[../../deep-dives/fixed-timestep|固定时间步长深度分析]]
- **带宽与性能的完整数据**：详见 [[../../deep-dives/client-server-netcode|快节奏多人游戏网络架构深度剖析]] 第 6 层
