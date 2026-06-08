---
title: "延迟补偿"
updated: 2026-06-05
---

# 延迟补偿

> 基于笔记: gabrielgambetta-network.md
> 所属教程: 快节奏多人游戏网络架构 — 从 Gambetta 系列到工业实践
> 章: 3/5

---

## 直觉理解：时间机器

想象你和朋友在玩激光枪对战。朋友站在空旷处，你瞄准他的头扣动扳机。但问题是——光从你这里照到他那里需要时间。你瞄准的是**0.3 微秒前的他**（光速从 100 米外到达）。0.3 微秒之内他不可能移动，所以这无所谓。

现在把光速降低到每秒 340 米（音速）。你瞄准 100 米外的朋友，声音传过去要 300 毫秒。你瞄准的是**300 毫秒前的他**——300 毫秒足够他走到墙后面了。你开枪，他看到你开枪（音速，300ms 后），但你瞄准的地方已经没人了。

这就是在线 FPS 中延迟的问题。笔记中 Gambetta 的描述：

> 你瞄准的是敌人头部 100 毫秒前的位置——而不是你开枪时的位置！某种程度上，这就像在一个光速非常非常慢的宇宙中游戏。

**延迟补偿就是给服务器一台"时间机器"**：当服务器收到你的射击事件时，它把世界状态回退到你扣扳机的那一瞬间，以你当时的视角做命中判定。

---

## 笔记问题 `#3`：服务器怎么知道"我当时看到了什么"？

笔记描述了延迟补偿的运作方式，但没有解释**数学上怎么做到**。关键步骤：

1. 客户端射击时，发送 `(timestamp, aim_origin, aim_direction)` 给服务器
2. 服务器收到后，**不**在"当前"世界状态上做射线检测
3. 服务器回退到 `timestamp` 对应的那一帧快照，在那个时刻的世界状态上做射线检测
4. 如果命中，在当前世界状态中应用伤害

### 服务器怎么回退时间？

服务器每 tick 都把世界状态存入环形缓冲区：

```
环形快照缓冲 (假设 128 tick，每 tick 16ms = 2 秒历史):

  [tick#0] [tick#1] [tick#2] ... [tick#127]
     ↑                            ↑
   最旧                         最新
   
  写入指针 → 每次 tick 前进一格，覆盖最旧的快照
```

当需要回退到某个 tick 时，直接从缓冲区读取那个快照。

### 但客户端的时间戳是客户端时钟——和服务器时钟不同步！

笔记没有讨论这个问题，但它是生产环境中的关键难点。

```
客户端:  t=1000ms  射击！
服务器:  t=1050ms  收到射击事件。
         如果直接用客户端的 1000ms，但服务器此刻是 1050ms——
         回退 50ms 是正确的。但如果客户端时钟比服务器快 200ms 呢？
         回退 250ms，回退到一个没有对应快照的 tick。
```

解决方案：**RTT 时钟偏移估计**。

```python
def estimate_clock_offset(client):
    """估计客户端与服务器之间的时钟偏移"""
    t0 = client_local_time()
    send_ping_to_server()
    # 服务器在 pong 中附带它的时钟值 server_time
    server_time_on_arrival = wait_for_pong()
    t1 = client_local_time()

    rtt = t1 - t0
    # 假设上行和下行延迟对称（各占 RTT/2）
    # 服务器收到 ping 的时间 ≈ t0 + RTT/2
    # 当时服务器时钟 = server_time_on_arrival
    estimated_server_time_now = server_time_on_arrival + rtt / 2
    clock_offset = estimated_server_time_now - t1
    return clock_offset
```

客户端使用这个偏移量，把射击时间戳转换为服务器时钟：

```python
client_shot_time = 1000  # 客户端时钟
server_shot_time = client_shot_time + clock_offset  # 转换为服务器时钟
```

---

## 算法与实现

### 数据结构

```python
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
import math


@dataclass
class EntitySnapshot:
    """单个实体在某个 tick 的状态快照"""
    entity_id: int
    x: float; y: float; z: float
    hitbox_radius: float  # 简化为球形碰撞体
    is_alive: bool = True


@dataclass
class WorldSnapshot:
    """服务器在某个 tick 的完整世界快照"""
    tick: int
    entities: dict = field(default_factory=dict)  # entity_id → EntitySnapshot


@dataclass
class ShotEvent:
    """客户端发来的射击事件"""
    shooter_id: int
    shot_timestamp: float       # 客户端时钟
    aim_origin: tuple           # 射线起点 (x, y, z)
    aim_direction: tuple        # 射线方向（已归一化）
    weapon_damage: float = 25.0

# 服务器端全局状态
SNAPSHOT_HISTORY_SIZE = 128  # 环形缓冲大小
MAX_COMPENSATION_MS = 0.200  # 最多回退 200ms——超过的延迟玩家自己承担
```

### V1: 朴素射线检测（不补偿）

```python
def process_shot_naive(world: dict, shot: ShotEvent) -> Optional[int]:
    """错误做法：在当前世界状态中做射线检测"""
    # 问题：其他玩家在射击后的 100ms 内可能已经移动了
    # 结果：必须瞄准"未来位置"才能命中——高 ping 玩家处于劣势
    best_hit = None
    best_dist = float('inf')

    for entity_id, entity in world.items():
        if entity_id == shot.shooter_id:
            continue
        dist = ray_sphere_intersect(
            shot.aim_origin, shot.aim_direction,
            (entity.x, entity.y, entity.z), entity.hitbox_radius
        )
        if dist is not None and dist < best_dist:
            best_dist = dist
            best_hit = entity_id

    return best_hit
```

### V2: 延迟补偿——回退到射击时刻

```python
class LagCompensatedServer:
    def __init__(self, tick_duration: float = 0.016):
        self.tick_duration = tick_duration  # 每 tick 秒数（16ms → ~62.5Hz）
        self.snapshot_history: deque[WorldSnapshot] = deque(maxlen=SNAPSHOT_HISTORY_SIZE)
        self.current_tick: int = 0
        self.world: dict = {}           # 当前权威世界状态
        self.client_latencies: dict = {}  # client_id → 预估 RTT/2 (秒)
        self.world_state = {}            # entity_id → 当前状态

    def server_tick(self):
        """每个 tick：更新世界 → 保存快照"""
        # 处理所有未处理的输入（省略细节）
        self.current_tick += 1

        # 保存快照
        snap = WorldSnapshot(tick=self.current_tick)
        for eid, e in self.world_state.items():
            snap.entities[eid] = EntitySnapshot(
                entity_id=eid,
                x=e.x, y=e.y, z=e.z,
                hitbox_radius=e.hitbox_radius,
                is_alive=e.is_alive,
            )
        self.snapshot_history.append(snap)

    def process_shot_compensated(self, shot: ShotEvent,
                                  server_receive_time: float) -> Optional[int]:
        """
        延迟补偿版的射击处理。
        server_receive_time: 服务器收到射击事件的真实时间（秒）
        """
        latency = self.client_latencies.get(shot.shooter_id, 0.0)

        # 1. 将客户端时间戳转换为服务器时间
        #    客户端在 shot_timestamp 时刻射击
        #    经过 latency 秒后到达服务器
        #    所以服务器收到时是 server_receive_time
        #    射击发生时服务器时间 ≈ server_receive_time - latency
        server_shot_time = server_receive_time - latency

        # 2. 计算需要回退的 tick 数
        lag_seconds = server_receive_time - server_shot_time
        # 限制在 MAX_COMPENSATION_MS 以内——防止作弊者利用极大延迟
        if lag_seconds > MAX_COMPENSATION_MS:
            lag_seconds = MAX_COMPENSATION_MS
        if lag_seconds < 0:
            # 客户端时钟比服务器快（罕见但可能）——不回退
            lag_seconds = 0.0

        ticks_back = int(lag_seconds / self.tick_duration)
        target_tick = self.current_tick - ticks_back

        # 3. 找到目标 tick 对应的快照
        target_snapshot = self._find_snapshot(target_tick)
        if target_snapshot is None:
            # 快照历史不足（刚启动或 buffer 太小）
            # 回退到当前世界状态
            target_snapshot = self._build_current_snapshot()

        # 4. 在目标快照中做射线检测
        best_hit = None
        best_dist = float('inf')

        for entity_id, entity_snap in target_snapshot.entities.items():
            if entity_id == shot.shooter_id:
                continue
            if not entity_snap.is_alive:
                # 即使在这帧快照中目标已死，仍然考虑——
                # 也许两个玩家同时杀死了对方（trade kill）
                continue

            dist = ray_sphere_intersect(
                shot.aim_origin, shot.aim_direction,
                (entity_snap.x, entity_snap.y, entity_snap.z),
                entity_snap.hitbox_radius,
            )
            if dist is not None and dist < best_dist:
                best_dist = dist
                best_hit = entity_id

        # 5. 如果命中，在当前世界状态中应用伤害
        if best_hit is not None and best_hit in self.world_state:
            target = self.world_state[best_hit]
            if target.is_alive:
                target.health -= shot.weapon_damage
                if target.health <= 0:
                    target.is_alive = False
                return best_hit

        return None

    def _find_snapshot(self, target_tick: int) -> Optional[WorldSnapshot]:
        """在环形缓冲中查找最接近 target_tick 的快照"""
        best = None
        best_diff = float('inf')
        for snap in self.snapshot_history:
            diff = abs(snap.tick - target_tick)
            if diff < best_diff:
                best_diff = diff
                best = snap
        return best

    def _build_current_snapshot(self) -> WorldSnapshot:
        """从当前世界状态构建快照（回退方案）"""
        snap = WorldSnapshot(tick=self.current_tick)
        for eid, e in self.world_state.items():
            snap.entities[eid] = EntitySnapshot(
                entity_id=eid,
                x=e.x, y=e.y, z=e.z,
                hitbox_radius=e.hitbox_radius,
                is_alive=e.is_alive,
            )
        return snap


def ray_sphere_intersect(origin: tuple, direction: tuple,
                         sphere_center: tuple, radius: float) -> Optional[float]:
    """射线与球体的交点距离。返回 None 表示不相交。"""
    # 简化版：只检测最近交点
    ox, oy, oz = origin
    dx, dy, dz = direction
    cx, cy, cz = sphere_center

    # 射线参数方程: P = O + t*D
    # 球体方程: |P - C|² = r²
    # 代入得二次方程: |D|²·t² + 2·D·(O-C)·t + |O-C|² - r² = 0
    ocx, ocy, ocz = ox - cx, oy - cy, oz - cz
    a = dx*dx + dy*dy + dz*dz  # 方向已归一化 → a = 1
    b = 2 * (dx*ocx + dy*ocy + dz*ocz)
    c = ocx*ocx + ocy*ocy + ocz*ocz - radius*radius

    discriminant = b*b - 4*a*c
    if discriminant < 0:
        return None  # 不相交

    t = (-b - math.sqrt(discriminant)) / (2*a)
    if t < 0:
        # 交点在射线后方
        t = (-b + math.sqrt(discriminant)) / (2*a)
        if t < 0:
            return None
    return t
```

### 时间线详解：穿墙被打是怎么发生的

```
                    客户端 A                    服务器                    客户端 B
                    ────────                    ──────                    ────────
  server_tick=0   A 看到 B 在 x=10（空旷处）
  
  server_tick=1   A 瞄准 x=10 开枪              收到 A 的射击事件            B 移动到 x=15（墙后）
                  shot_timestamp=1000ms         server_receive=1050ms
                  aim_origin=A_pos              latency=50ms
                  aim_direction=→B              回退到 tick≈3 (1000ms时刻)
                                                在快照 `#3` 中检测：B 在 x=10 ✓
                                                判定命中！
                                                在当前世界 (tick≈6) 中对 B
                                                造成 25 点伤害
                                                
  server_tick=6                               广播更新                     收到更新
                                                                           B: "我在墙后，怎么死了？"

  B 的体验：我已经躲到墙后了，但还是被打中了。这是"favor the shooter"的代价。
```

---

## 实践考量

### "Favor the Shooter" 原则及其争议

延迟补偿本质上是一个**哲学选择**：在空间敏感的交互中，优先保障谁的游戏体验？

| 策略                    | 描述                | 射击者体验         | 被射击者体验    | 采用游戏                    |
| --------------------- | ----------------- | ------------- | --------- | ----------------------- |
| **Favor the shooter** | 以射击者视角的过去状态判定     | "我打中了！"       | "我在墙后被杀？" | CS, Valorant, Overwatch |
| **Favor the target**  | 以被射击者视角的当前状态判定    | "我瞄得很准但没判定？"  | "躲墙后就是安全" | 极少使用                    |
| **纯服务器判决**            | 以服务器当前状态判定        | 高 ping 玩家必须预瞄 | 公平        | 社区服务器 mod               |
| **弹道模拟**              | 子弹有飞行时间，碰撞在"交会时刻" | 更真实但更复杂       | 更真实       | Battlefield 系列          |

大多数 FPS 选择 favor the shooter。原因：**"我打中了但没判定"比"我躲好了但死了"更让玩家沮丧**——前者感觉像作弊，后者可以解释为"网络延迟"。[基于内部知识]

### 安全性：防止延迟补偿滥用

延迟补偿为作弊者打开了一个窗口：

```python
# 作弊防护检查
def validate_shot_event(shot: ShotEvent, shooter_id: int,
                         max_latency: float = 0.200):
    """服务器端验证射击事件的合理性"""
    # 1. 限制最大回退时间
    #    如果客户端声称的延迟 > MAX_COMPENSATION_MS，
    #    截断为 MAX_COMPENSATION_MS——高延迟玩家处于劣势
    #    （防止"lag switch"：故意制造延迟来获得不公平的回退判定）
    pass  # 在 process_shot_compensated 中已处理

    # 2. 验证射击者是否还活着
    #    如果射击者在当前 tick 已死亡，拒绝射击
    #    （防止死亡后"幽灵射击"）
    pass

    # 3. 验证时间戳不会来自未来
    #    如果 shot_timestamp > server_current_time + tolerance
    #    （客户端时钟不可能快于服务器太多）
    pass
```

笔记中 Gambetta 的结论很诚实：

> 如果敌人原本处于开放位置，躲到墙后面，然后在几秒钟后，当他们以为安全时被击中呢？嗯，这种情况确实可能发生。这就是你要付出的代价。

### 性能考量：快照存储

延迟补偿的内存开销取决于实体数量和快照历史长度：

```
每快照 per entity ≈ position(12B) + rotation(16B) + hitbox(16B) = 44B
假设: 10 个玩家 × 44B × 128 快照 = 56KB（环形缓冲）
加上投射物: 50 个 × 20B × 128 = 128KB
总计: < 200KB —— 完全可以接受

主要开销不是内存，而是每 tick 的快照克隆（memcpy）
```

详见 [[../../deep-dives/client-server-netcode|快节奏多人游戏网络架构深度剖析]] 第 6 层的完整性能分析。

### 延迟补偿 vs 客户端预测：不要混淆

| | 客户端预测 | 延迟补偿 |
|---|---|---|
| **谁执行** | 客户端 | 服务器 |
| **目的** | 消除自己的输入延迟 | 让空间敏感的交互公平 |
| **操作** | 本地立即模拟输入效果 | 回退世界状态到过去的时刻 |
| **时间方向** | 向前看（预测未来） | 向后看（回到过去） |
| **影响范围** | 只影响本地玩家 | 影响所有玩家的交互判定 |

---

## 关联主题

- **客户端预测**（第 1 章）：预测让本地操作即时响应；延迟补偿让远程交互基于"当时的状态"公平判定
- **实体插值**（第 2 章）：插值让其他玩家平滑显示在"过去"；延迟补偿让"射击过去的玩家"能够命中——两者协同工作
- **Valve 的完整设计文档**：笔记末尾的额外阅读链接中，Yahn Bernier 的 [Latency Compensating Methods](https://developer.valvesoftware.com/wiki/Latency_Compensating_Methods_in_Client/Server_In-game_Protocol_Design_and_Optimization) 是延迟补偿的原始设计文档
- **更深层的协议分析**：详见 [[../../deep-dives/client-server-netcode|快节奏多人游戏网络架构深度剖析]] 第 3.4 节和第 7 层
