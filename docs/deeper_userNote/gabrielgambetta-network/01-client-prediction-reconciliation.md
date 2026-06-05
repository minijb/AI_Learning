---
title: "客户端预测与服务器协调"
updated: 2026-06-05
---

# 客户端预测与服务器协调

> 基于笔记: gabrielgambetta-network.md
> 所属教程: 快节奏多人游戏网络架构 — 从 Gambetta 系列到工业实践
> 章: 1/5

---

## 直觉理解：快递仓库模型

想象你是一个全国连锁超市的运营者。每个城市都有分店，总部在北京。

**朴素方案**（没有预测）：顾客下单 → 订单发到北京总部 → 总部审批 → 货物从北京发出 → 顾客收货。每次购物等 3 天。

**客户端预测方案**：每个分店建一个"预测仓库"。分店经理知道 99% 的订单总部都会批准。于是：

1. 顾客下单时，分店**立刻**从预测仓库取货交给顾客——这是预测
2. 订单同时发送到总部
3. 总部审批后，把"权威库存状态"发回分店
4. 分店对比权威状态和自己的预测：如果不一致（比如总部说"这个货已经卖完了"），分店从顾客那里把错误的货换回来——这是协调（reconciliation）

这就是客户端预测 + 服务器协调的精髓：**用本地的即时响应掩盖网络延迟，然后用服务器的权威状态纠正预测错误**。

---

## 笔记问题 `#1：x=12` 还是 x=11？

笔记中描述了这样一个场景（来自 Gambetta 原文）：

> 当 250ms 的时候客户端预测的状态是 x=12，但是服务器却说新的状态是 x=11……角色向右移动了两格，停留 50 毫秒，向左跳跃一格，停留 100 毫秒，然后向右跳跃一格。

### 为什么会出现这个矛盾？

让我们用时间线来拆解——**这是理解整个协调机制的关键**。

```
时间轴（客户端视角）：

t=0     玩家按下右箭头（发送请求 #1）
        客户端预测位置：x=11 ✓（立即显示）

t=50    服务器收到请求 #1
t=100   服务器 tick：处理请求 #1 → x=11（权威状态）
        服务器广播快照（包含 x=11, last_processed=#1）
        → 快照在网络上传输需要 150ms

t=150   玩家再次按下右箭头（发送请求 #2）
        客户端预测位置：x=12

t=250   客户端收到服务器的快照：「x=11, last_processed=#1」
        客户端把角色跳回 x=11 ← 这就是笔记中描述的"来回跳"！
        …然后客户端重放未确认的请求 #2 → x=12
```

**问题的根源**：服务器发来的状态只包含了请求 #1 的效果，但客户端已经执行了请求 #2。如果不做协调，客户端直接用 x=11 覆盖 x=12，就产生了视觉上的回退。

**解决方案的本质**：客户端保留"哪些请求服务器还没处理"的记录。收到服务器状态后，只丢弃已处理的请求，把未处理的请求重新应用上去。这样，客户端状态始终等于：

```
predicted_state = server_authoritative_state + sum(unprocessed_inputs)
```

这就是笔记中描述的核心逻辑——但笔记只讲了"是什么"，下面我们展开**怎么实现**。

---

## 算法与实现

### 数据结构

```python
from dataclasses import dataclass, field
from collections import deque
from typing import Deque

@dataclass
class PlayerInput:
    """客户端发送给服务器的输入单元"""
    sequence: int       # 单调递增的序列号——整个机制的核心
    move_x: float = 0.0 # 水平移动输入（-1.0 到 +1.0）
    move_y: float = 0.0 # 垂直移动输入
    jump: bool = False  # 是否按下跳跃
    fire: bool = False  # 是否开火
    timestamp: float = 0.0  # 客户端时间戳（用于延迟补偿，见第 3 章）


@dataclass
class ServerSnapshot:
    """服务器发送给客户端的世界快照"""
    tick: int           # 服务器 tick 序号
    player_x: float     # 本地玩家的权威 x 坐标
    player_y: float     # 本地玩家的权威 y 坐标
    player_vx: float    # 本地玩家的权威 x 速度
    player_vy: float    # 本地玩家的权威 y 速度
    acked_input: int    # 服务器确认的最后一个输入序列号——关键字段！
    entity_positions: dict = field(default_factory=dict)  # 其他实体位置


@dataclass
class ClientState:
    """客户端维护的本地状态"""
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    sequence: int = 0       # 下一个输入将使用的序列号
    input_buffer: Deque[PlayerInput] = field(default_factory=deque)
    # input_buffer 只存储服务器尚未确认的输入
```

### V1: 朴素实现——不做协调（有 bug）

先看一下**不协调**会发生什么——这就是笔记中描述的问题：

```python
# 错误版本：直接把服务器状态覆盖到本地
def on_server_update_wrong(client: ClientState, snap: ServerSnapshot):
    client.x = snap.player_x
    client.y = snap.player_y
    # 问题：input_buffer 中的输入效果全部丢失
    # 结果：玩家看到角色"跳回"，然后在下一次本地输入时才"跳回"预测位置
```

### V2: 正确的协调实现

```python
# 移动速度常量
PLAYER_SPEED = 200.0  # 单位/秒


def apply_input(state: ClientState, inp: PlayerInput):
    """将单个输入应用到游戏状态上——这是"确定性模拟"的核心"""
    # 归一化对角线移动，防止斜向移动速度比正交快 √2 倍
    import math
    mag = math.sqrt(inp.move_x ** 2 + inp.move_y ** 2)
    if mag > 1.0:
        inp.move_x /= mag
        inp.move_y /= mag

    dt = 1.0 / 60.0  # 假设 60Hz 输入速率
    state.x += inp.move_x * PLAYER_SPEED * dt
    state.y += inp.move_y * PLAYER_SPEED * dt
    # 注意：这里用简化的运动学模型。生产环境中，客户端和服务器
    # 应使用完全相同的物理代码（通常编译为共享库），确保确定性


def on_local_input(client: ClientState, move_x: float, move_y: float,
                   jump: bool, fire: bool, current_time: float):
    """步骤 1：玩家按下按键 — 立即预测 + 发送给服务器"""
    client.sequence += 1
    inp = PlayerInput(
        sequence=client.sequence,
        move_x=move_x, move_y=move_y,
        jump=jump, fire=fire,
        timestamp=current_time,
    )
    # 关键：保存到未确认 buffer，用于后续协调
    client.input_buffer.append(inp)
    # 立即应用预测 — 消除输入延迟
    apply_input(client, inp)
    # 发送给服务器（由网络层处理，此处省略 send_to_server(inp)）


def on_server_update(client: ClientState, snap: ServerSnapshot):
    """步骤 2：收到服务器权威快照 — 协调预测状态"""
    # 2a. 丢弃服务器已确认的输入
    #     服务器说"我处理到了序列号 N"，意味着 ≤N 的输入都已被处理
    while client.input_buffer and client.input_buffer[0].sequence <= snap.acked_input:
        client.input_buffer.popleft()

    # 2b. 重置为服务器权威状态
    #     这是"服务器是权威"的体现——相信服务器的状态
    client.x = snap.player_x
    client.y = snap.player_y
    client.vx = snap.player_vx
    client.vy = snap.player_vy

    # 2c. 重新应用服务器尚未处理的输入
    #     公式: predicted_state = server_state + Σ(unacked_inputs)
    for inp in client.input_buffer:
        apply_input(client, inp)

    # 结果：如果预测正确，重放后的位置与预测位置一致
    #       如果预测错误（比如撞到了在服务器上才存在的障碍物），
    #       重放后的位置是正确的新预测值
```

### 用笔记中的例子验证

```
假设: 每次按右键移动 1 个单位

客户端：
  t=0:   按右键 → seq=1, x=1, input_buffer=[#1], 发送 #1
  t=150: 按右键 → seq=2, x=2, input_buffer=[#1, #2], 发送 #2
  t=250: 收到快照(acked=1, x=1)
          → 丢弃 #1（已 ack）     input_buffer=[#2]
          → 重置 x=1（服务器权威）
          → 重放 #2: x=1+1=2     ← 正确！
  t=350: 收到快照(acked=2, x=2)
          → 丢弃 #2（已 ack）     input_buffer=[]
          → 重置 x=2
          → 没有未确认输入，结束  ← 完美收敛
```

---

## 实践考量

### 视觉平滑：处理"橡皮筋"效果

当预测和服务器状态不一致时，直接把角色跳到权威位置会产生"橡皮筋"效果。实际做法是用**视觉平滑**：

```python
SNAP_THRESHOLD = 0.5    # 小于此距离，直接修正（不可见）
SMOOTH_THRESHOLD = 2.0  # 小于此距离，逐帧 Lerp
SMOOTH_FACTOR = 0.3     # 每帧修正 30% 的误差

def smooth_correction(current_pos: tuple, corrected_pos: tuple) -> tuple:
    """平滑地将渲染位置收敛到权威位置"""
    import math
    dx = corrected_pos[0] - current_pos[0]
    dy = corrected_pos[1] - current_pos[1]
    error = math.sqrt(dx * dx + dy * dy)

    if error < SNAP_THRESHOLD:
        # 误差太小，肉眼不可见，直接修正
        return corrected_pos
    elif error < SMOOTH_THRESHOLD:
        # 中等误差：逐帧 lerp，让修正看起来自然
        return (
            current_pos[0] + dx * SMOOTH_FACTOR,
            current_pos[1] + dy * SMOOTH_FACTOR,
        )
    else:
        # 大误差：可能是传送、重生，直接跳过去
        return corrected_pos
```

### 输入冗余：UDP 不是可靠的

UDP 会丢包。如果服务器的 `acked_input` 跳过了某些序列号，客户端需要知道如何处理：

```python
# 客户端发送每个包时，附带最近 3 个输入用于冗余
class InputPacket:
    current: PlayerInput          # 当前输入
    redundant: list[PlayerInput]  # 最近 3 个输入（seq-3, seq-2, seq-1）
    # 目的：即使某个包丢失，后续包中的冗余输入也能让服务器补齐
```

Source Engine 的数据包结构 `CUserCmd` 就采用了这种冗余策略：每个网络包携带当前命令 + 前几条历史命令，确保服务器不会因单次丢包而永久丢失某个输入。[基于内部知识]

### 预测失败的场景

笔记中提到：

> 即使世界是完全的决定性的，没有任何客户端作弊，客户端预测的状态和服务器发送的状态在 reconciliation 后仍然可能不匹配……当多个玩家同时连接到服务器时，很容易遇到这种情况。

具体来说，以下场景会导致预测与权威状态不一致：

| 失败场景 | 原因 | 协调后的结果 |
|---------|------|------------|
| 被另一个玩家推开 | 客户端不知道其他玩家的碰撞 | 角色跳回，重新计算位置 |
| 撞到可破坏物体 | 物体是否被破坏由服务器决定 | 可能"穿过"本应挡路的物体，然后被拉回 |
| 被减速/眩晕 debuff | 技能施放由服务器权威判定 | 移动速度突变，需要平滑处理 |
| 拾取物品 | 物品可能已被其他玩家拾取 | 客户端预测"捡到了"，服务器说"没有" |
| 死亡 | 伤害由服务器权威判定 | 客户端预测"活着"，服务器说"死了"——不能简单跳转，需要死亡动画过渡 |

### 生产环境中的特殊处理

笔记中提到了一个重要的边界情况：

> 由于游戏状态的复杂性，它并不总是容易逆转，你可能想要避免杀死一个角色，即使它在客户端的游戏状态中生命值已经低于零。

这意味着：**客户端只做视觉效果预测，不做游戏逻辑预测**。

```python
def on_local_input_with_guard(client, move_x, move_y, jump, fire, current_time):
    """生产级输入处理：区分视觉效果和游戏逻辑"""
    client.sequence += 1
    inp = PlayerInput(
        sequence=client.sequence,
        move_x=move_x, move_y=move_y, jump=jump, fire=fire,
        timestamp=current_time,
    )
    client.input_buffer.append(inp)
    send_to_server(inp)

    # 预测移动：低风险，99% 正确
    apply_movement(client, inp)

    # 预测伤害：高风险！只在客户端做视觉效果（血花、数字）
    if inp.fire:
        # 不扣血，只显示枪口火焰和弹道特效
        client.render_effects.muzzle_flash = True
        # 客户端不减少任何实体的 HP——等服务器确认
```

---

## 关联主题

- **实体插值**（第 2 章）：协调解决的是"自己"的预测问题；对于其他玩家，需要不同的技术——实体插值
- **延迟补偿**（第 3 章）：协调确保本地玩家的位置正确；但射击判定（"我打中他了吗？"）需要时间回退——延迟补偿
- **固定时间步长**：客户端和服务器使用固定步长（如 60Hz）是确定性的前提。详见 [[../../deep-dives/fixed-timestep|固定时间步长深度分析]]
- **底层网络协议的完整分析**：详见 [[../../deep-dives/client-server-netcode|快节奏多人游戏网络架构深度剖析]]，第 5-6 层覆盖了传输层细节、时钟同步、带宽建模和内存布局
