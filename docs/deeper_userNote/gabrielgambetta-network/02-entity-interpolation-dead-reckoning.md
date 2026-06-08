---
title: "实体插值与航位推算"
updated: 2026-06-08
---

# 实体插值与航位推算

> 基于笔记: gabrielgambetta-network.md
> 所属教程: 快节奏多人游戏网络架构 — 从 Gambetta 系列到工业实践
> 章: 2/5

---

## 直觉理解：看直播 vs 看回放

你在看一场足球比赛的直播。解说员说"梅西进球了！"——但信号从球场传到你家电视有 5 秒延迟。你看的是**5 秒前的梅西**。

现在假设你**自己在球场上踢球**。你不需要等电视信号才知道自己在哪——你直接**感知**自己的位置。

这就是客户端-服务器架构中"自己"和"其他玩家"的区别：

- **自己**：客户端预测 → 即时响应 → 看到的是"现在"
- **其他玩家**：服务器发来快照 → 有网络延迟 → 只能看到"过去"

笔记中 Gambetta 的核心结论：

> 玩家看到**自己**在当前时刻，看到**其他实体**在过去。

问题来了：既然其他玩家的位置数据每 100ms 才到达一次，怎么让他们的移动看起来**平滑**而不是每 100ms 跳一次？

答案取决于游戏类型：**航位推算**（可预测的运动）和**实体插值**（不可预测的运动）。

---

## 笔记问题 `#2：什么时候用航位推算，什么时候用插值？`

笔记中给出了两个截然不同的场景：

> **赛车游戏**：一辆速度非常快的车相当可预测……它在任何时刻的位置高度依赖于其之前的位置、速度和方向。
>
> **3D 射击游戏**：玩家通常以极高速度奔跑、停止和拐角，这使得航位推算基本上毫无用处。

核心判断标准是**状态的可预测性**——一个形式化的定义：

```
position(t+dt) ≈ position(t) + velocity(t)·dt + ½·acceleration(t)·dt²
```

如果在 `dt`（通常 50-100ms）内，加速度矢量的变化量（jerk）被物理限制约束，航位推算有效。如果玩家可以**瞬间**改变方向或速度（如 FPS 中的急停、转向），航位推算的预测误差会大到你无法接受。

---

## 算法与实现

### 航位推算（Dead Reckoning）

适用于赛车、飞行模拟等**物理约束强**的游戏。

```python
@dataclass
class DeadReckonedEntity:
    """使用航位推算的远程实体"""
    entity_id: int
    # 服务器最后发来的权威数据
    auth_x: float = 0.0
    auth_y: float = 0.0
    auth_vx: float = 0.0
    auth_vy: float = 0.0
    auth_ax: float = 0.0  # 加速度 —— 对于赛车，这受引擎/刹车/转弯半径约束
    auth_ay: float = 0.0
    last_update_time: float = 0.0  # 服务器时间戳


def on_entity_update(entity: DeadReckonedEntity, x: float, y: float,
                     vx: float, vy: float, ax: float, ay: float,
                     server_time: float):
    """收到服务器权威更新 — 重置预测基准"""
    entity.auth_x = x
    entity.auth_y = y
    entity.auth_vx = vx
    entity.auth_vy = vy
    entity.auth_ax = ax
    entity.auth_ay = ay
    entity.last_update_time = server_time


def extrapolate_position(entity: DeadReckonedEntity, now: float) -> tuple:
    """使用恒定加速度模型外推当前位置"""
    dt = now - entity.last_update_time
    # 匀加速运动公式: s = s₀ + v₀·t + ½·a·t²
    pred_x = entity.auth_x + entity.auth_vx * dt + 0.5 * entity.auth_ax * dt * dt
    pred_y = entity.auth_y + entity.auth_vy * dt + 0.5 * entity.auth_ay * dt * dt
    return (pred_x, pred_y)
```

**为什么用加速度而不只是速度？**笔记中说"假设汽车的方向和加速度在那 100 毫秒内保持不变"——恒定加速度模型比恒定速度模型多捕获了"玩家在加速/减速/转弯"的信息，预测精度显著更高。对于赛车游戏，这是正确的模型；对于 FPS，连恒定速度模型都经常失效。

**预测误差的来源**：

| 运动模式 | 预测误差 | 原因 |
|---------|---------|------|
| 匀速直线 | ≈ 0 | 恒定加速度模型退化到精确匹配 |
| 匀加速/减速 | 极小 | 模型直接覆盖 |
| 恒定半径转弯 | 小 | 向心加速度在短时间窗口内近似恒定 |
| 急转弯（jerk 大） | 中 | 加速度矢量突变，100ms 内可偏移数十厘米 |
| 碰撞 | 极大 | 速度瞬间反转——模型完全失效 |

当服务器更新到达时，如果权威位置和预测位置差距过大（碰撞），角色会"跳"到正确位置。这可以接受——碰撞本身就是一种视觉不连续事件，跳跃是自然的。

---

### 实体插值（Entity Interpolation）

适用于 FPS、MOBA 等**状态变化不可预测**的游戏。核心思想是**故意把其他玩家显示在"过去"**，用两个已知快照之间的区域做平滑插值。

```
时间线（客户端视角，假设 100ms 插值延迟）：

真实世界时间:  t=0       t=100     t=200     t=300
              │         │         │         │
服务器 tick:   tick#0    tick#1    tick#2    tick#3
              │         │         │         │
快照到达:      Sn(0)     Sn(1)     Sn(2)     Sn(3)
              ↓ +50ms   ↓ +50ms   ↓ +50ms   ↓+50ms
客户端收到:   t=50      t=150     t=250     t=350

无插值（直接渲染最新快照）:
  t=50~149:  显示 Sn(0) ─── 100ms 静止 ───
  t=150:     跳到 Sn(1) ─── 100ms 静止 ───
  t=250:     跳到 Sn(2) ─────────────────
  → 角色看起来像"幻灯片放映"，完全不可接受

有插值（render_time = now - 100ms）:
  t=150:     render_time=50,  插值在 Sn(0) 和 Sn(1) 之间 → 平滑
  t=250:     render_time=150, 插值在 Sn(1) 和 Sn(2) 之间 → 平滑
  t=350:     render_time=250, 插值在 Sn(2) 和 Sn(3) 之间 → 平滑
  → 角色每帧都在移动，视觉流畅
```

#### 逐帧推演：插值延迟的精确运作

上面时间线容易让人产生一个疑问：*客户端的时钟明明在往前走，为什么减去 100ms 之后，render_time 恰好能落在两个已收到的快照之间？*

答案藏在**快照到达的节奏**里。我们用具体的帧来走一遍。

情景设定：
- 服务器 tick rate = 10Hz → 每 **100ms** 产生一个快照
- 网络单程延迟 = **50ms**（往返 100ms）
- 插值延迟 = **100ms**（恰好等于一个 tick 间隔）
- 客户端以 **60FPS** 渲染，每帧约 16.7ms

```
服务器时间    tick#0   tick#1   tick#2   tick#3   tick#4
              t=0      t=100    t=200    t=300    t=400
                │        │        │        │        │
客户端收到    t=50     t=150    t=250    t=350    t=450
                ▼        ▼        ▼        ▼        ▼

客户端帧 (t)      render_time = t - 100   可用快照           行为
───────────────────────────────────────────────────────────────────
t = 50~99         -50 ~ -1                [Sn(0)]            快照不足，静止在 Sn(0)
t = 100            0                       [Sn(0), Sn(1)]     插值 Sn(0)↔Sn(1) @ α=0
t = 116            16                      [Sn(0), Sn(1)]     插值 Sn(0)↔Sn(1) @ α=0.16
t = 133            33                      [Sn(0), Sn(1)]     插值 Sn(0)↔Sn(1) @ α=0.33
t = 150            50                      [Sn(0), Sn(1)]     插值 Sn(0)↔Sn(1) @ α=0.50
...（帧持续推进，α 从 0→1）...
t = 233            133                     [Sn(0), Sn(1)]     α=1.33 ❌ >1，超出范围
t = 233~266       133~166                 [Sn(1), Sn(2)]     插值 Sn(1)↔Sn(2)（刚收到 Sn(2)）
...───────────────────────────────────────────────────────────────
t = 350            250                     [Sn(2), Sn(3)]     平滑过渡到下一区间
```

关键观察：

1. **render_time 永远在追赶快照，而不是快照追赶当前时间**
   - 当前时间 t = 150 时，render_time = 50，恰好等于 tick#0 的时间戳。
   - 此时 tick#0 快照已在 t=50 到达，tick#1 快照已在 t=150 到达——**两个快照都已就位**。
   - 如果你没有插值延迟（render_time = t = 150），你会试图渲染 tick#1.5 的位置——那在 tick#1 和 tick#2 之间，但 tick#2 还没收到，只能外推或静止。

2. **100ms 的插值延迟恰好等于快照间隔**
   - 这意味着：当你开始插值区间 [Sn(n), Sn(n+1)] 时，Sn(n+1) 刚好已经到达。
   - 更一般地：只要 **interp_delay ≥ server_tick_interval**，渲染就永远有至少两个快照可用。
   - 如果 interp_delay < tick_interval（比如延迟 50ms 但 tick 间隔 100ms），在 tick 刚切换后的几帧里可能出现 render_time 超出最新快照的情况，导致卡顿。

3. **alpha 的物理意义**
```
                tick#0 (t=0)                         tick#1 (t=100)
                │                                         │
                ◆─────────────────────────────────────────◆
                                       ▲
                                       ╰──── render_time = 50
                                       α = (50 - 0) / 100 = 0.5
```
   - `alpha = 0` → 你看到的是 tick#0 的精确位置（刚收到 tick#1 的最早时刻）
   - `alpha = 1` → 你看到的是 tick#1 的精确位置（下一快照来之前的最后一刻）
   - 在两者之间，角色以**线性速度**从旧位置移向新位置——这个速度由服务器快照决定，不是客户端猜测的。

#### 一个更直觉的比喻：浇花的水管

想象服务器是一根水管，每 100ms 喷出一截蓝色的水（快照）。水管到你家的距离是 50ms。

- **无插值延迟**：你站在水管口旁边，手指伸出去接水。水是喷射的，你能接到一截，然后空 100ms，再接一截。运动是跳跃的。
- **有插值延迟**：你往后退 100ms 的距离，手里拿了一个**杯子（两个快照之间的区间）**。现在你看到水管里的水是一段**连续的流**——因为上一个蓝色水段还没完全流走，下一个就到了。杯子总是满的。

后退的这 100ms 就是 `INTERP_DELAY`。它让你看到的不是"最新的一滴水"，而是"已经流到杯子里的那段水流"。

#### 延迟与 tick rate 的数学关系

形式上，保证"永远有两个快照可用"的最小延迟是：
```
INTERP_DELAY_min = server_tick_interval + jitter_buffer
```
其中 `jitter_buffer` 抵消网络抖动（通常 1-2 个额外 tick）。

| 服务器 tick rate | tick 间隔 | 最小插值延迟 | 工业实践（含抖动缓冲） |
|-----------------|-----------|------------|---------------------|
| 20 Hz (Source)  | 50 ms     | 50 ms      | 100 ms (cl_interp 0.1) |
| 64 Hz (CS2/MM)  | 15.6 ms   | 15.6 ms    | ~31 ms (2×)           |
| 128 Hz (竞技)   | 7.8 ms    | 7.8 ms     | ~16 ms (2×)           |

 tick rate 越高，你可以把插值延迟压得越低，其他玩家看起来越"实时"——但代价是服务器 CPU 和网络带宽。
#### 实现

```python
from collections import deque
from typing import Deque

INTERP_DELAY = 0.100  # 100ms —— 通常是 2× 服务器 tick 间隔
MAX_SNAPSHOTS = 3     # 只保留最近 3 个快照，减少内存


@dataclass
class InterpolatedEntity:
    """使用插值的远程实体"""
    entity_id: int
    snapshots: Deque[tuple] = field(default_factory=deque)
    # 每个快照: (server_tick, x, y)


def on_entity_snapshot(entity: InterpolatedEntity, tick: int,
                       x: float, y: float):
    """收到新的权威快照"""
    entity.snapshots.append((tick, x, y))
    # 限制 buffer 大小：只保留最近 N 个快照
    while len(entity.snapshots) > MAX_SNAPSHOTS:
        entity.snapshots.popleft()


def interpolate_position(entity: InterpolatedEntity,
                         now: float, tick_duration: float) -> tuple:
    """
    渲染该实体在当前帧的位置。
    now: 当前真实时间
    tick_duration: 每个服务器 tick 的时长（秒）
    """
    render_time = now - INTERP_DELAY

    snapshots = entity.snapshots
    if len(snapshots) < 2:
        # 快照不足，无法插值——显示最新已知位置
        if snapshots:
            return (snapshots[-1][1], snapshots[-1][2])
        return (0.0, 0.0)

    # 找到包围 render_time 的两个快照
    for i in range(len(snapshots) - 1):
        t0 = snapshots[i][0] * tick_duration   # tick 转秒
        t1 = snapshots[i + 1][0] * tick_duration

        if t0 <= render_time <= t1:
            # 计算插值因子
            alpha = (render_time - t0) / (t1 - t0)
            # 线性插值
            x = snapshots[i][1] + alpha * (snapshots[i + 1][1] - snapshots[i][1])
            y = snapshots[i][2] + alpha * (snapshots[i + 1][2] - snapshots[i][2])
            return (x, y)

    # render_time 超出了最新快照的范围（网络卡顿）
    # 回退：使用最新已知位置
    return (snapshots[-1][1], snapshots[-1][2])
```

#### 为什么插值延迟是必须的？

如果不加延迟（`render_time = now`），在大多数帧中，`now` 会超出最新快照的时间戳，导致只能外推——而外推在不可预测的场景下就是不准确的跳跃。插值延迟确保我们**永远在已知数据之间做插值，永远不做外推**。

这引入了一个微秒的权衡：

| | 插值延迟小 (50ms) | 插值延迟大 (200ms) |
|---|---|---|
| 视觉平滑度 | 可能偶尔卡顿（快照没到） | 非常平滑 |
| 信息新鲜度 | 更接近真实位置 | 严重过时 |
| 适用场景 | 低延迟环境（LAN、低 ping） | 高延迟环境（跨国对战） |

Valve 的 Source Engine 默认使用 **100ms** 插值延迟（`cl_interp = 0.1`），这是基于 20Hz tick rate（50ms 间隔）的 2 倍设定。现代游戏使用更高 tick rate（64-128Hz），插值延迟可以相应减小。[基于内部知识]

---

## 实践考量

### 插值 vs 外推：决策流程

```
服务器更新到达 → 快照 buffer 中有 ≥2 个快照？
    │
    是 → render_time = now - INTERP_DELAY
    │     若 render_time 在两个快照之间 → 插值（平滑）
    │     若 render_time > 最新快照 → 网络问题，用最新位置（静止等待）
    │
    否 → 只有 1 个快照 → 显示该位置（等第二个快照）
```

### 乱序到达与丢包

UDP 的特性使得快照可能乱序到达或丢失：

```python
def on_entity_snapshot_robust(entity: InterpolatedEntity, tick: int,
                               x: float, y: float):
    """增强版：处理乱序和丢包"""
    snapshots = entity.snapshots

    if snapshots and tick <= snapshots[-1][0]:
        # 乱序或重复的快照：忽略（已过时）
        return

    # 正常插入
    snapshots.append((tick, x, y))
    while len(snapshots) > MAX_SNAPSHOTS:
        snapshots.popleft()
```

如果快照丢失（tick 序列出现间隙），插值算法自动在现存快照之间工作，间隙不影响插值质量——只是插值的时间窗口变大了。

### 笔记中的额外优化

笔记提到：

> 你可以让服务器在每个更新中发送更详细的位置数据——例如，玩家跟随的一系列直线段，或者每 10 毫秒采样一次的位置。

这指的是**过采样插值**（oversampled interpolation）。服务器不只发送 tick 时刻的位置，还发送中间时刻的采样点。这允许客户端使用 Catmull-Rom 曲线或更高阶插值来产生更平滑的运动路径。代价是带宽增加——但可以对增量位置进行高效编码来抵消。[推测]

### 为什么 100ms 延迟"通常不会被注意到"？

笔记中说：

> 即使是快节奏的游戏，看到其他实体有 100 毫秒的延迟通常也不会被注意到。

这有三个原因：

1. **人类视觉对平滑度的敏感度高于精确位置**——每秒 60 帧的平滑运动比精确的实时位置更重要
2. **玩家注意力集中在自己的准星上**，对其他角色的观察是外围的
3. **100ms 在游戏时间尺度上很短**——一次典型的射击反应时间是 200-300ms，100ms 的对手延迟远小于这个阈值

唯一的例外是笔记中提到的**空间敏感的交互**（射击判定）——这将在下一章用延迟补偿来解决。

---

## 关联主题

- **客户端预测**（第 1 章）：预测 + 插值 + 航位推算三者的分工：预测处理"自己"，插值/航位推算处理"他人"
- **延迟补偿**（第 3 章）：插值让其他玩家看起来在"过去"——延迟补偿让"射击过去的玩家"仍然能命中
- **更深层的网络协议分析**：详见 [[../../deep-dives/client-server-netcode|快节奏多人游戏网络架构深度剖析]]，第 3.2-3.3 节覆盖了插值与航位推算的底层数学和性能分析
