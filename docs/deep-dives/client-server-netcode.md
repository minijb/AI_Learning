---
title: "快节奏多人游戏网络架构 深度剖析"
updated: 2026-06-05
---

# 快节奏多人游戏网络架构 深度剖析

> 基于 Gabriel Gambetta 系列文章深化
> 深度等级: 第 5-6 层（实现原理 + 性能分析）
> 关联学习计划: 无（独立深度探索）
> 分析日期: 2026-06-05
> 关键词: client-side prediction, server reconciliation, entity interpolation, dead reckoning, lag compensation, authoritative server, netcode

---

## 原教程摘要

Gabriel Gambetta 的四篇文章构建了一套完整的快节奏多人游戏网络架构：

1. **权威服务器模型** — 客户端只发送输入，服务器是游戏世界的唯一权威
2. **客户端预测 + 服务器协调** — 客户端立即模拟输入效果，通过序列号与服务器状态对齐
3. **实体插值** — 其他玩家的位置使用过去两个快照插值，显示"延迟 100ms 的过去"
4. **延迟补偿** — 服务器回退时间到射击者视角的瞬间来判断命中

核心结论：**玩家看到自己在"现在"，看到其他实体在"过去"，服务器通过时间回退来裁决空间敏感的交互。**

---

## 第 1 层: 直觉理解——为什么这一切是必要的

### 核心矛盾

多人游戏的网络问题本质上是**物理学矛盾**：

> 光速有限 → 信号传播需要时间 → 信息永远是过时的

当你（在东京）按下右箭头键时，服务器（在纽约）需要约 50ms 才能收到这条指令。服务器处理后，结果再花 50ms 传回给你。你看到角色移动的那一刻，距离你按键已经过去了 100ms。

100ms 听起来不多，但在一个 60fps 的射击游戏中，100ms = 6 帧。对于职业玩家，20ms 的延迟就能感知到差异。直接"发送-等待-渲染"的朴素实现根本不可行。

### 一个类比：快递公司和本地仓库

想象你经营一个全国连锁超市：

- **朴素方案**：顾客下单 → 订单送到总部 → 总部发货 → 顾客收货。每次购物等 3 天。
- **客户端预测**：每个分店建一个"预测仓库"。顾客下单时，分店**立刻**从预测仓库取货给顾客（假设总部会批准），同时把订单发往总部。总部批复后，分店对比批复结果和预测结果：如果不一致，从顾客那里把错误的货换回来。
- **实体插值**：分店 A 不知道分店 B 的实时库存，只能看到总部每 100ms 发来的库存快照。为了平滑展示 B 的商品变动，分店 A 把 B 的库存快照延迟 100ms 播放。
- **延迟补偿**：当一个顾客拿着商品 A 去结账，系统需要判断"这个商品在顾客拿起它的那一刻是否真的在货架上"。总部把时钟拨回到顾客伸手的瞬间来裁决。

---

## 第 2 层: 使用场景——何时需要这些技术

### 决策矩阵

| 游戏类型 | 客户端预测 | 实体插值 | 延迟补偿 | 为什么 |
|----------|-----------|---------|---------|--------|
| FPS (CS/Valorant) | 必须 | 必须 | 必须 | 毫秒级反应，射击判定需要高精度 |
| MOBA (LOL/Dota2) | 必须 | 可选 | 不需要 | 技能有弹道/前摇，略有延迟可接受 |
| 赛车 (Forza) | 必须 | — | — | 航位推算足够，无空间敏感交互 |
| RTS (星际争霸) | — | — | — | Lockstep 确定性同步更适合 |
| 格斗 (街霸) | — | — | — | Rollback netcode (GGPO) 更适合 |
| MMO (WOW) | 可选 | 必须 | 不需要 | 高延迟可接受，但需要看到其他玩家平滑移动 |
| 回合制 | — | — | — | 朴素客户端-服务器即可 |

### 技术选型决策树

```
需要低延迟的实时操作？ ─── 否 ──→ 朴素客户端-服务器 / Lockstep
    │
    是
    │
    ↓
玩家能瞬间改变方向和速度？ ─── 否 ──→ 客户端预测 + 航位推算
    │                                          （赛车、飞行模拟）
    是
    │
    ↓
需要精确的空间交互判定？ ─── 是 ──→ 客户端预测 + 实体插值 + 延迟补偿
    │                                      （FPS、TPS）
    否
    │
    ↓
客户端预测 + 实体插值
（MOBA、MMO 动作）
```

---

## 第 3 层: 算法与实现

### 3.1 客户端预测 + 服务器协调

#### 数据结构

```
客户端维护:
  input_buffer: Queue<Input>      // 未确认的输入，每条带序列号
  last_acked_seq: uint32          // 服务器最后确认的序列号
  predicted_state: GameState      // 本地预测的游戏状态

服务器维护（每个客户端）:
  last_processed_seq: uint32      // 该客户端最后处理的输入序列号
```

#### 客户端流程

```python
def on_local_input(input):
    input.sequence = next_sequence()
    input_buffer.append(input)
    send_to_server(input)
    apply_to_state(predicted_state, input)  # 立即预测

def on_server_update(server_state, acked_seq):
    # 1. 重置为服务器权威状态
    predicted_state = server_state

    # 2. 丢弃已确认的输入
    input_buffer = [i for i in input_buffer if i.sequence > acked_seq]

    # 3. 重新应用未确认的输入
    for input in input_buffer:
        apply_to_state(predicted_state, input)

    # 4. 可选：对位置做视觉平滑（避免跳变）
    smooth_correction(old_position, predicted_state.position)
```

**核心公式**：

```
predicted_state = server_state + Σ apply(unacked_inputs)
```

#### 服务器流程

```python
def on_client_input(client_id, input):
    client_input_queues[client_id].append(input)
    # 不立即处理，等待定时更新循环

def server_tick():
    for client_id, queue in client_input_queues.items():
        for input in queue:
            apply_to_state(world_state, input)
            last_processed_seq[client_id] = input.sequence
        queue.clear()

    # 广播世界快照
    for client_id in all_clients:
        snapshot = extract_relevant_state(world_state, client_id)
        snapshot.last_acked_seq = last_processed_seq[client_id]
        send_to_client(client_id, snapshot)
```

#### 关键细节：预测失败时的视觉修正

当服务器状态和预测状态不一致时，不能直接把角色跳回服务器位置——这会产生"橡皮筋"效果。常见平滑策略：

```python
def smooth_correction(current_pos, corrected_pos):
    error = corrected_pos - current_pos

    if error.length() < SNAP_THRESHOLD:    # 误差很小（如 < 0.5m）
        # 直接修正，肉眼不可见
        return corrected_pos
    elif error.length() < SMOOTH_THRESHOLD:  # 中等误差（< 2m）
        # 逐帧 lerp 过去
        return current_pos + error * SMOOTH_FACTOR  # factor ~= 0.3
    else:                                     # 大误差（> 2m）
        # 可能是传送/重生，直接跳
        return corrected_pos
```

---

### 3.2 实体插值

#### 数据结构

```
客户端维护（每个远程实体）:
  snapshot_buffer: Deque<(timestamp, Position)>  # 最多存 2-3 个快照
  render_timestamp: float   # 当前渲染的时间点 = now - INTERP_DELAY
```

#### 核心算法

```python
INTERP_DELAY = 100  # ms，通常是服务器 tick_rate 的 2 倍

def on_snapshot_received(entity_id, position, server_timestamp):
    buffer = entity_buffers[entity_id]
    buffer.append((server_timestamp, position))

    # 只保留最新的 3 个快照
    if len(buffer) > 3:
        buffer.pop(0)

def render_entity(entity_id, now):
    buffer = entity_buffers[entity_id]
    render_time = now - INTERP_DELAY

    # 找到包围 render_time 的两个快照
    for i in range(len(buffer) - 1):
        if buffer[i].timestamp <= render_time <= buffer[i+1].timestamp:
            t0, p0 = buffer[i]
            t1, p1 = buffer[i+1]

            # 线性插值
            alpha = (render_time - t0) / (t1 - t0)
            return lerp(p0, p1, alpha)

    # 外推：render_time 超出了最新快照（网络卡顿）
    if buffer:
        # 用最新的已知位置，等待新数据
        return buffer[-1].position
```

#### 为什么延迟是必须的

```
时间线（客户端视角）:

服务器 tick:    T=0         T=100       T=200       T=300
                │           │           │           │
快照到达:       Snapshot(0) Snapshot(1) Snapshot(2) Snapshot(3)
                ↓ 100ms     ↓ 100ms     ↓ 100ms
客户端收到:     t=50        t=150       t=250       t=350

如果直接渲染最新快照，在 t=150 到 t=250 之间，角色会"卡住"100ms，
然后突然跳到新位置。

使用 INTERP_DELAY=100ms:
  t=150 时，render_time = 50，插值在 Snapshot(0) 和 (1) 之间 → 平滑
  t=250 时，render_time = 150，插值在 Snapshot(1) 和 (2) 之间 → 平滑
```

---

### 3.3 航位推算（Dead Reckoning）

#### 适用条件

航位推算只在**状态变化连续且可预测**时有效。可预测性的度量是**状态二阶导数有界**：

```
position(t+dt) ≈ position(t) + velocity(t) * dt + 0.5 * acceleration(t) * dt²
```

如果 `acceleration` 的突变率（jerk）被物理限制约束（如赛车转弯半径、最大加速度），预测就是可靠的。

#### 算法

```python
def on_server_update(entity_id, position, velocity, acceleration, timestamp):
    entity = entities[entity_id]
    entity.authoritative_position = position
    entity.velocity = velocity
    entity.acceleration = acceleration
    entity.last_update_time = timestamp
    entity.predicted_position = position  # 重置预测

def simulate_entity(entity, now):
    dt = now - entity.last_update_time
    # 恒定加速度模型
    entity.predicted_position = (
        entity.authoritative_position
        + entity.velocity * dt
        + 0.5 * entity.acceleration * dt * dt
    )
```

#### 误差特性

| 运动模式 | 预测误差 | 原因 |
|---------|---------|------|
| 匀速直线 | ≈ 0 | 恒定加速度模型精确匹配 |
| 匀加速/减速 | 极小 | 模型直接覆盖 |
| 转弯（恒定半径） | 小 | 向心加速度恒定 |
| 急转弯 | 中 | 加速度矢量变化，需要更高级模型 |
| 碰撞 | 极大 | 瞬时的速度/方向突变，无法预测 |

---

### 3.4 延迟补偿（Lag Compensation）

#### 核心思想

> 服务器回退世界状态到射击者按下扳机那一瞬间，以射击者的视角做命中判定。

#### 算法

```python
MAX_COMPENSATION_MS = 200  # 最多回退 200ms
SNAPSHOT_HISTORY_SIZE = int(MAX_COMPENSATION_MS / TICK_DURATION)  # 如 200/50 = 4

class Server:
    def __init__(self):
        # 环形缓冲：存储最近 N 帧的完整世界快照
        self.snapshot_history = RingBuffer(SNAPSHOT_HISTORY_SIZE)

    def server_tick(self):
        # 正常更新世界
        self.apply_all_inputs()
        # 保存快照
        self.snapshot_history.push(self.world_state.clone())

    def on_shot(self, shooter_id, shot_timestamp, aim_origin, aim_direction):
        # 1. 计算需要回退多长时间
        current_server_time = self.get_server_time()
        # shot_timestamp 是客户端时间，需要转换为服务器时间
        latency = self.client_latency[shooter_id]
        server_shot_time = current_server_time - latency

        # 2. 限制回退范围（防止作弊者伪造极大延迟）
        lag = current_server_time - server_shot_time
        if lag > MAX_COMPENSATION_MS:
            lag = MAX_COMPENSATION_MS
        if lag < 0:
            lag = 0

        # 3. 找到对应时刻的快照
        target_time = current_server_time - lag
        snapshot = self.snapshot_history.get_at_time(target_time)

        # 4. 在该快照中进行射线检测
        hit_entity = snapshot.raycast(aim_origin, aim_direction)

        # 5. 在当前世界状态中应用伤害
        if hit_entity and hit_entity.is_enemy_of(shooter_id):
            # 验证目标是否在射击者视野内（防止穿过墙壁的作弊）
            # 注意：只检查目标当时的遮挡，不检查射击者
            if not snapshot.is_occluded(shooter_id, hit_entity.id):
                self.world_state.apply_damage(hit_entity.id, damage)
```

#### 时间线详解

```
                    客户端 A                    服务器                    客户端 B
                    ────────                    ──────                    ────────
  t=0           A 看到 B 在位置 P0
  t=50          A 瞄准 P0 开枪                 收到 A 的射击事件            B 移动到位置 P1
                (shot_timestamp=0,             shot_timestamp=0
                 aim=P0)
  t=100                                       处理射击：                  收到服务器更新
                                              回退世界到 t=0              B 被击中（在 P1 位置！）
                                              发现 B 在 P0
                                              命中判定：命中！
                                              在当前世界（t=100）
                                              对 B 造成伤害

  B 的体验：已经移动到 P1 躲到墙后，但还是受伤害了。
  为什么会"穿墙被打"？请看第 7 层的权衡分析。
```

---

## 第 4 层: 行为契约

### 4.1 客户端预测 + 协调

| | 条件 |
|---|---|
| **前置条件** | 游戏世界是确定性的；输入可以被序列化为固定格式；所有输入带唯一单调递增序列号 |
| **后置条件** | 服务器确认后，客户端状态 == 服务器状态；未确认的输入保留在 buffer 中 |
| **不变量** | `predicted_state == server_state + Σ(unacked_inputs)`；`acked_seq` 单调不减 |

#### 边界情况

| 情况 | 行为 |
|------|------|
| 服务器从未收到输入 #5（UDP 丢包） | 客户端持续重发 #5（通过冗余编码）；客户端看到 #6 被 ack 时推断 #5 也丢失了，停止重发 |
| 客户端在收到 ack 前发出 100 个输入 | Buffer 被丢弃——服务器一次 tick 处理所有排队输入，返回最新 seq |
| 服务器 tick 速率低于客户端输入速率 | 多个输入在同一次 tick 中处理；客户端一次 reconciliation 重放多个输入 |
| 玩家死亡（客户端预测死亡但服务器说没死） | 客户端只做视觉效果（血花、数字），真正扣血/死亡等服务器确认 |
| 网络断开 | 客户端继续预测（本地假运行），重连后全量同步；或切换到"等待重连"状态 |

### 4.2 实体插值

| | 条件 |
|---|---|
| **前置条件** | 快照 buffer 至少有 2 个快照；`render_time` 在两个快照时间戳之间 |
| **后置条件** | 渲染位置是历史真实位置的线性近似 |
| **不变量** | `render_time = now - INTERP_DELAY`；快照时间戳单调递增 |

#### 边界情况

| 情况 | 行为 |
|------|------|
| 快照到达乱序（UDP） | 按时间戳排序插入 buffer；丢弃过时快照 |
| 快照丢包 | Buffer 中出现时间间隙；插值时用前后快照外推（或跳到新位置） |
| 玩家停止移动 | 同一位置出现多次；插值结果恒定 → 角色自然静止 |
| 新玩家出现（join-in-progress） | 第一个快照到达时 buffer 只有一个点；先显示该位置，第二个快照到达后才开始插值 |
| 网络抖动导致快照间隔不均 | 使用基于时间戳的插值（而非假设固定间隔）来抵消抖动 |

### 4.3 延迟补偿

| | 条件 |
|---|---|
| **前置条件** | 服务器维护了至少 `MAX_COMPENSATION_MS` 的历史快照；客户端发送射击事件时带精确时间戳和瞄准信息 |
| **后置条件** | 命中判定在快照时刻完成，伤害在当前时刻应用 |
| **不变量** | `补偿延迟 ≤ MAX_COMPENSATION_MS`；历史快照不会被未来事件修改 |

#### 边界情况

| 情况 | 行为 |
|------|------|
| 补偿延迟为负（客户端时钟快于服务器） | `lag = max(0, lag)`——不做回退 |
| 补偿延迟 > MAX_COMPENSATION_MS | 截断为 MAX_COMPENSATION_MS——高延迟玩家处于劣势 |
| 射击后目标被其他人杀死 | 仍然造成伤害（射击时刻目标是活着的）；两个玩家可能同时杀死对方 |
| 射击者在射击瞬间被杀死 | 取决于游戏设计——通常服务器拒绝已死角色的射击 |
| 快照历史不足（启动阶段） | 不做补偿，使用当前状态判定 |

---

## 第 5 层: 实现原理——底层细节

### 5.1 为什么序列号机制能工作

序列号不仅用于"哪个输入已确认"，它们还使得**客户端可以重建任意时刻的状态**。

```
客户端维护的输入历史:
  seq=1: move_right   (已 ack: server confirmed at x=11)
  seq=2: move_right   (未 ack)
  seq=3: jump         (未 ack)

服务器返回: state={x=12, y=0}, acked_seq=2

客户端重构:
  base_state = server_state        # x=12, y=0（包含 seq=1 和 seq=2 的效果）
  apply(base_state, input[3])      # 重放 seq=3: jump
  # 结果: x=12, y=5（正确！）
```

**关键洞察**：客户端不需要知道服务器具体处理了哪些输入——服务器处理的输入效果已经体现在返回的游戏状态中。客户端只需要把**服务器没处理**的输入重新应用上去。

### 5.2 输入冗余与可靠性

UDP 是不可靠的。关键输入（如射击）不能依赖单次发送：

```python
# 输入冗余策略
class InputPacket:
    sequence: uint32
    current_input: Input       # 当前输入
    # 冗余：附带最近 3 个输入，以防服务器漏掉了
    redundant_inputs: list[Input]  # [seq-3, seq-2, seq-1]

# 服务器侧
def on_input_packet(packet):
    for input in [packet.current_input] + packet.redundant_inputs:
        if input.sequence > last_processed_seq[client_id]:
            apply_input(input)
            last_processed_seq[client_id] = input.sequence
```

Source Engine 使用 `CUserCmd` 结构，每个数据包携带当前命令 + 最近几条历史命令。

### 5.3 插值的数学

实体插值本质上是**移动平均滤波**。它在频域上是一个低通滤波器，平滑了由于低频更新造成的阶梯状位置变化。

```
时间轴上：
  服务器采样点:  •       •       •       •       •       (50ms 间隔，即 20Hz tick)
                  \     / \     / \     / \     /
  客户端插值:      •---•---•---•---•---•---•---•---•---•   (平滑连续)
```

线性插值的截断误差：
```
error_max = (Δt)² * |max_acceleration| / 8
```
对于 100ms 间隔和 10m/s² 的最大加速度：`error_max = 0.1² * 10 / 8 = 0.0125m = 1.25cm`，视觉上不可见。

### 5.4 延迟补偿的数学

延迟补偿等价于在服务器上执行一次**时间平移**：

```
世界状态 W(t) 在时间 t 的快照
射击事件 e = (t_shot, origin, direction) 到达服务器的时间是 t_arrival

正常处理: hit_test(W(t_arrival), origin, direction)  # 基于"现在"判定 → 打不中
延迟补偿: hit_test(W(t_shot), origin, direction)      # 基于"射击时"判定 → 打中了
```

但有个微妙之处：**被射击者在 t_shot 时的位置**取决于被射击者在 t_shot 时的输入，而这些输入服务器早就收到了。服务器的快照 `W(t_shot)` 是**事后构建的**，但它包含的**所有玩家的输入都是在 t_shot 之前发出的**——所以它是"过去那个时刻应该有的正确状态"。

唯一的信息不对称是：射击者在 t_shot 到 t_arrival 之间发送的其他输入。但这些不影响命中判定——它们发生在射击之后。

---

## 第 6 层: 性能特征

### 6.1 带宽

| 数据 | 典型大小 | 频率 | 单客户端带宽 |
|------|---------|------|-------------|
| 客户端上行：输入 | 2-8 bytes/input | 60Hz (每个输入) | ~0.5 KB/s |
| 客户端上行：带冗余的输入 | 10-30 bytes/packet | 60Hz | ~1.8 KB/s |
| 服务器下行：世界快照 | 视实体数量而定 | 20-60Hz | 5-30 KB/s |

**带宽优化策略**：

- **增量编码**：只发送变化的数据（如"实体 #42: pos += (0.1, 0, -0.05)"）。位置用 `int16` 而非 `float32`。
- **兴趣管理（Area of Interest）**：服务器只发送玩家视野内的实体
- **Delta 压缩**：相对于上一个确认快照的差异
- **优先级更新**：近处实体高频更新，远处实体低频更新

### 6.2 服务器 CPU

| 操作 | 复杂度 | 每 tick 每客户端开销 |
|------|--------|---------------------|
| 排队输入 | O(1) per input | 可忽略 |
| 应用输入（移动、物理） | O(1) per input | ~10μs |
| 快照生成 | O(entities) per client | ~5μs per entity |
| 延迟补偿·快照存储 | O(entities) per tick | ~0.5μs per entity（memcpy） |
| 延迟补偿·命中检测 | O(entities) per shot | ~50μs（射线检测） |

**快照存储的内存开销**：

```
每快照 per_entity: position(12B) + rotation(16B) + velocity(12B) ≈ 40B
假设 32 个实体，200ms 历史，20Hz tick = 4 个快照
总内存：32 × 40B × 4 = 5.12KB

即使 64 个玩家 × 64 个实体 = 4096 实体：4096 × 40B × 4 = 640KB
```

快照存储的内存成本极低，主要开销是**每个 tick 克隆世界状态**（memcpy）。

### 6.3 客户端 CPU

| 操作 | 复杂度 | 每帧开销 |
|------|--------|---------|
| 预测本地输入 | O(1) | 可忽略 |
| 协调（reapply unacked inputs） | O(buffer_size) | ~1μs per input |
| 实体插值 | O(entities) | ~1μs per entity |

### 6.4 延迟的组成

```
总延迟 = 客户端帧时间/2 + 网络 RTT/2 + 服务器 tick/2 + 插值延迟

典型 FPS 场景（60Hz 客户端, 50ms RTT, 64Hz tick, 2 tick 插值延迟）:
  = 8.3ms + 25ms + 7.8ms + 31.25ms
  = 72.35ms
```

**各技术对延迟的影响**：

| 技术 | 延迟影响 |
|------|---------|
| 客户端预测（本地玩家） | 消除输入延迟，本地操作 ≈ 单机体验 |
| 实体插值（其他玩家） | 增加 INTERP_DELAY（通常 2×tick 间隔）的延迟 |
| 延迟补偿（射击判定） | 无额外延迟——服务器回退时间模拟射击者视角 |

---

## 第 7 层: 设计权衡、对比方案与演进

### 7.1 对比方案

#### Lockstep (确定性 P2P)

```
每个客户端模拟整个游戏世界。
所有客户端等待所有人的输入到达后，一起步进一帧。
```

| | Lockstep | 客户端-服务器 + 预测 |
|---|---|---|
| **延迟** | 最慢玩家的延迟决定所有人的体验 | 每个玩家独立的输入响应 |
| **作弊防护** | 弱——每个客户端都能看到完整游戏状态（地图 hack） | 强——服务器控制信息分发 |
| **断线处理** | 必须暂停等待 | 可以继续（服务器保留状态） |
| **带宽** | 极低（只发输入） | 中等（需要发世界快照） |
| **适用** | RTS（星际争霸、帝国时代） | FPS、MOBA、MMO |

#### Rollback Netcode (GGPO, 格斗游戏)

```
客户端预测 + 如果预测错误，回滚到错误帧重新模拟。
没有"服务器权威"——两个客户端对等，各自预测。
```

| | Rollback (GGPO) | 客户端-服务器 + 预测 |
|---|---|---|
| **权威性** | 无中心权威，双方各自回滚 | 服务器是唯一权威 |
| **回滚频率** | 可能频繁回滚（延迟高时） | 只做协调（reconciliation），不真正回滚 |
| **最大延迟** | 通常限 200-300ms | 可更高，只是体验下降 |
| **适用** | 1v1 格斗游戏 | 多人在线游戏 |

#### Snapshot Interpolation vs State Interpolation

Gambetta 描述的是 **state interpolation**（服务器发位置，客户端插值）。另一种是 **snapshot interpolation**（服务器发整个世界的快照，客户端在快照之间插值）。

| | State Interpolation | Snapshot Interpolation |
|---|---|---|
| **带宽** | 低（只发变化） | 高（每帧发完整状态） |
| **实现复杂度** | 高（需要增量编码、可靠传输） | 低（简单的快照序列） |
| **一致性** | 可能因丢包造成状态漂移 | 强（每个快照是完整的） |
| **代表** | Source Engine, 大部分商业引擎 | Overwatch |

Overwatch 使用 snapshot interpolation——每帧发送完整快照，客户端在两个快照间插值。带宽更高但实现简单且一致性强。

### 7.2 延迟补偿的争议："穿墙被打"

```
场景：
  玩家 B 在 t=0 时站在空旷处。
  t=50ms：B 移动到墙后。
  t=80ms：A 开枪（A 的屏幕上 B 还在空旷处）。
  t=130ms：服务器判定命中。B 在墙后被"打死"。

B 的体验：我已经躲好了，怎么还被打中？
A 的体验：我明明瞄得很准。
```

**问题的根源**：延迟补偿优先选择了**射击者的视角**。这被称为"favor the shooter"原则。

**替代方案**：

| 策略 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| Favor the shooter | 以射击者视角判定（当前方案） | 射击手感好 | 被射击者可能"穿墙死" |
| Favor the target | 以被射击者视角判定 | 躲藏有意义 | 必须"预判"射击，手感极差 |
| No compensation | 以服务器当前状态判定 | 公平 | 必须瞄准"未来位置"，体验差 |
| Pure server-side | 服务器在收到射击事件后处理，不做回退 | 简单 | 高 ping 玩家处于劣势 |
| Hybrid（部分游戏使用） | 子弹有飞行时间或弹道 | 更物理真实 | 增加复杂度 |

大多数 FPS 选择 **favor the shooter**，因为"我打中了但没判定"比"我躲好了但死了"更让玩家沮丧。Valve 的 Source Engine 和 Blizzard 的 Overwatch 都采用此策略。

### 7.3 演进历史

| 时代 | 游戏 | 网络模型 | 创新 |
|------|------|---------|------|
| 1993 | Doom | P2P Lockstep | 基础多人同步 |
| 1996 | Quake | 客户端-服务器 + 预测 | 引入客户端预测（QuakeWorld） |
| 1998 | Quake II | UDP + 增量更新 | 放弃 TCP，使用自定义 UDP 协议 |
| 1999 | Half-Life (GoldSrc) | 客户端-服务器 + 预测 | Source Engine 前身，完善的预测系统 |
| 2004 | Half-Life 2 (Source) | 客户端-服务器 + 预测 + 插值 + 延迟补偿 | **首次完整实现这四种技术的商业引擎** |
| 2007 | TF2 / CS:S | 同上 | 大范围验证，延迟补偿成为 FPS 标配 |
| 2016 | Overwatch | Snapshot interpolation + favor the shooter | 简化架构：快照插值替代状态插值 |
| 2020 | Valorant | 128-tick 服务器 + 激进的延迟补偿 | 高 tick rate + 高度优化的网络栈 |

**Source Engine 的关键贡献**：Valve 是第一家将这四种技术（预测、协调、插值、延迟补偿）系统化地实现并广泛部署的团队。他们的 [Source Multiplayer Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) 文档至今仍是游戏网络编程的必读材料。

### 7.4 常见陷阱

#### 陷阱 1：预测和物理的冲突

客户端预测通常使用**简化的物理模型**（如恒定速度移动），而服务器使用**完整物理引擎**。当两者结果不一致时，协调会产生视觉跳变。

**缓解**：客户端使用与服务器相同的物理代码（共享库/确定性物理）；或增加容错阈值。

#### 陷阱 2：插值延迟过大

`INTERP_DELAY` 设置过大（如 200ms），玩家看到其他角色的位置严重过时，导致"我明明看到他在那里但打不中"。

**建议**：`INTERP_DELAY = 2 × server_tick_duration`。20Hz tick → 100ms 延迟；60Hz tick → 33ms 延迟。

#### 陷阱 3：时钟同步

客户端和服务器时钟不同步会导致延迟补偿计算错误。NTP 级的同步通常足够，但在高精度要求下需要更精确的方案（如基于 RTT 的时钟偏移估计）。

```python
# 简单时钟偏移估计
def estimate_clock_offset():
    t0 = client_time()
    send_ping()
    server_time = wait_for_pong()
    t1 = client_time()
    rtt = t1 - t0
    # 假设上下行对称
    estimated_server_time_at_t1 = server_time + rtt / 2
    clock_offset = estimated_server_time_at_t1 - t1
    return clock_offset
```

#### 陷阱 4：快照历史的内存

服务器每 tick 需要克隆完整世界状态。对于大型开放世界，这可能很昂贵。

**优化**：只克隆可能被延迟补偿查询的实体（玩家、载具、投射物）。静态物体（地形、建筑）在历史快照间不变，可以共享引用。

#### 陷阱 5：作弊向量

客户端预测将部分模拟权交给了客户端，引入了作弊途径：

| 作弊类型 | 如何利用预测 | 缓解 |
|---------|-------------|------|
| Speedhack | 客户端预测快速移动，服务器可能来不及验证 | 服务器验证最大速度、加速度 |
| Aimbot | 客户端可以精确知道所有实体位置（用于渲染预测） | 服务器端反作弊检测异常瞄准模式 |
| Wallhack | 客户端需要知道附近实体来预测它们 | 兴趣管理：只发视野范围内的实体 |
| Lag switch | 故意延迟输入，让延迟补偿过度回退 | 限制 MAX_COMPENSATION_MS |
| 回溯作弊 | 伪造旧的射击时间戳 | 服务器验证时间戳合理性 |

---

## 进阶阅读

- [Source Multiplayer Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) — Valve 官方文档，完整描述 GoldSrc/Source 引擎网络栈
- [Latency Compensating Methods in Client/Server In-game Protocol Design and Optimization](https://developer.valvesoftware.com/wiki/Latency_Compensating_Methods_in_Client/Server_In-game_Protocol_Design_and_Optimization) — Yahn Bernier 的经典论文，延迟补偿的原始设计文档
- [What Every Programmer Needs to Know About Game Networking](https://gafferongames.com/post/what_every_programmer_needs_to_know_about_game_networking/) — Glenn Fiedler 的网络编程入门
- [Gaffer On Games: Networked Physics](https://gafferongames.com/post/networked_physics_2004/) — 确定性物理在网络游戏中的实践
- [Overwatch Gameplay Architecture and Netcode](https://www.youtube.com/watch?v=W3aieHjyNvw) — GDC 演讲，Overwatch 的网络架构
- [GGPO](https://www.ggpo.net/) — 回滚网络代码的开创性实现

---

*深化完成于 2026-06-05。基于 Gabriel Gambetta 的四篇系列文章，扩展到七层深度分析。*
