---
title: "Actor 概念、UE Actor 复制与 skynet Actor 模型 — 深度剖析"
updated: 2026-06-05
---

# Actor 概念、UE Actor 复制与 skynet Actor 模型 — 深度剖析

> 深度等级: 第 6 层（源码分析）
> 关联学习计划: 帧同步、状态同步与状态帧同步
> 分析日期: 2026-06-03

---

## 导读：三个"Actor"，一个灵魂

你可能已经注意到：Unreal Engine 里有 `AActor`，skynet 文档里也反复提到 "Actor 模型"，
而计算机科学中 Actor Model 又是一个有 50 年历史的并发计算理论。它们之间是什么关系？

**核心结论**：

- **CS Actor Model**（1973, Carl Hewitt）是一种并发计算范式——"一切皆 Actor，Actor 之间只通过消息通信，不共享内存"。
- **skynet 的 Actor 模型** 是 Actor Model 的一个实践实现——每个 Lua 服务是一个 Actor，消息队列 + 协程驱动。
- **UE 的 AActor-Replication** 则**不是** Actor Model 的实现——`AActor` 这个名字只是巧合。
  UE 的复制系统是一个 **CS 架构下的属性增量同步机制**：服务器遍历所有标记为 `bReplicates` 的 AActor，
  对比前后 Shadow State，把变化值序列化发给客户端，仅此而已。

本文分三部分：
- **Part A**：Actor Model 的计算机科学定义、核心原理、与游戏服务器的天然契合
- **Part B**：UE Actor 复制的完整流程——从 `ServerReplicateActors` 到 `UActorChannel::ReplicateActor` 到底层 bitstream
- **Part C**：skynet 的 Actor 实现——C 层消息队列调度 + Lua 层协程驱动的完整链路

---

## Part A：Actor Model — 并发计算的一种哲学

### 第 1 层：直觉理解

想象一个**邮件系统**：

- 每个人有一个信箱地址。
- 你只能通过**写信**与别人通信——你不能直接进入别人的房间翻他的抽屉。
- 收到信后，你可以：回信、给第三方写信、或者创建一个新的通信者。
- 你**永远不共享**你的笔记（状态）给别人——别人想知道你的状态？写信来问。

这就是 Actor Model 的直觉：**计算单元之间没有共享内存，只有消息传递**。

这个类比的关键约束：
- 通信是**异步**的——你寄出信后继续做自己的事，不等对方拆信。
- 不保证**到达顺序**——A 寄出两封信，B 可能先收到后一封。
- 地址是**一等公民**——你可以把别人的地址写在信里发给第三方（从而动态建立通信拓扑）。

### 第 2 层：使用场景

**Actor Model 最适合的场景**：

| 场景                | 为什么适合                        |
| ----------------- | ---------------------------- |
| 游戏服务器（skynet）     | 每个"服务"（登录、匹配、战斗逻辑）天然隔离，消息驱动  |
| 分布式系统（Erlang/OTP） | 物理机器间本身就不共享内存，消息传递是唯一选项      |
| 高并发 Web 后端（Akka）  | 百万级连接 → 每连接一个 Actor，内存开销极小   |
| IoT / 嵌入式         | 设备间天然异步、不可靠通信                |
| 微服务编排（Orleans）    | 每个"虚拟 Actor"对应一个业务实体，自动激活/钝化 |

**不适合 Actor Model 的场景**：

| 场景 | 为什么不适合 |
|------|------------|
| 高性能计算（HPC） | 需要共享内存 + SIMD 优化，消息传递开销太大 |
| 游戏引擎渲染管线 | 渲染是紧密耦合的数据流，Actor 的异步消息不适合 |
| 数据库事务 | 需要 ACID，Actor 模型不直接提供事务语义 |
| 低延迟实时系统 | 消息调度的延迟不确定性不可接受（微秒级） |

#### 决策流程图

```
你的系统是否需要处理大量并发实体？
  ├── 否 → 传统多线程/进程模型即可
  └── 是 → 这些实体之间是否需要频繁通信？
            ├── 否 → 每个实体独立，Actor 模型是好的隔离方案
            └── 是 → 通信模式是请求-响应还是流式数据？
                      ├── 请求-响应 → Actor 模型（如 skynet.call）
                      └── 流式数据 → 考虑 CSP（Go channel）或数据流模型
```

### 第 3 层：基本语义—三条铁律

Actor Model 由 Carl Hewitt 于 1973 年提出，核心只有三条规则：

```text
规则 1: 一个 Actor 收到消息时，可以：
         (a) 发送有限条消息给其他 Actor
         (b) 创建有限个新的 Actor
         (c) 指定处理下一条消息时的行为（成为另一个"自己"）

规则 2: Actor 之间通信只通过异步消息传递。
         没有共享内存、没有锁、没有全局变量。

规则 3: 消息传递不保证顺序。
         如果 A 向 B 发送 M1 然后 M2，B 可能先收到 M2。
         如果需要顺序保证，引入一个 Queue Actor 做缓冲。
```

这三条规则推导出所有 Actor 系统的关键性质：
- **隔离性**：一个 Actor 崩溃不影响其他 Actor（Erlang 的 "let it crash" 哲学即源于此）
- **位置透明性**：Actor 可以在同一进程、同一机器、或跨网络——地址解析是运行时的事
- **无锁并发**：因为不共享状态，不需要 mutex/semaphore/lock

### 第 4 层：行为契约

**每个 Actor 的形式化定义**（Agha, 1985）：

```text
Actor = (Address, Mailbox, Behavior, State)

Address  : 全局唯一的不可变标识符（类似"邮箱地址"）
Mailbox  : 消息的 FIFO 队列（实现层面，理论模型不保证 FIFO）
Behavior : 函数: (Message, State) → (Actions, NewBehavior, NewState)
State    : 该 Actor 的私有状态，外部不可见
```

**消息发送的契约**：

```text
前置条件: sender 持有 recipient 的 Address
后置条件: 消息最终被投递到 recipient 的 Mailbox（"最终" = 无时间上限）
不变量:   发送操作无副作用于 sender 的状态
异常:     无——Actor Model 中发送消息永远不会失败
           （实现层面：如果目标 Actor 不存在，消息被静默丢弃或路由到死信队列）
```

**关键语义——"无限制非确定性"（Unbounded Nondeterminism）**：

这是 Actor Model 区别于 CSP（Communicating Sequential Processes）等模型的核心特征。
简单说：一个 Actor 可以在有限步骤内做出**无限多种可能的选择**——例如，
一个网络服务器 Actor 可以在任意时间点收到来自任意客户端的消息，无法预先确定下一步收到什么。

实际含义：**Actor 系统天然适合处理不可预测的并发输入**（这正是游戏服务器的特征）。

### 第 5 层：实现原理—消息调度模型

所有 Actor 框架的核心是一个 **Work-Stealing 消息调度器**：

```text
┌─────────────────────────────────────────────────────┐
│                    Scheduler                         │
│  ┌──────────────────────────────────────────────┐   │
│  │          Global Run Queue                     │   │
│  │  [Actor3]→[Actor1]→[Actor7]→[Actor2]→...      │   │
│  └──────────────┬───────────────────────────────┘   │
│                 │  Worker Threads 从队列取 Actor     │
│     ┌───────────┼───────────┬───────────┐           │
│     ▼           ▼           ▼           ▼           │
│  Worker1    Worker2    Worker3    Worker4            │
│     │           │           │           │           │
│     ▼           ▼           ▼           ▼           │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐           │
│  │Actor │  │Actor │  │Actor │  │Actor │  ...       │
│  │Mailbox│ │Mailbox│ │Mailbox│ │Mailbox│           │
│  └──────┘  └──────┘  └──────┘  └──────┘           │
└─────────────────────────────────────────────────────┘
```

**调度伪代码**：

```python
def scheduler_loop():
    while not should_exit:
        actor = global_run_queue.pop()
        if actor is None:
            sleep_until_woken()  # 没有活跃 Actor，worker 休眠
            continue

        message = actor.mailbox.pop()
        if message is None:
            continue  # mailbox 已空，该 Actor 不再是"活跃"状态

        # 执行 Actor 的消息处理
        new_messages = actor.behavior.process(message)

        # 将产生的消息路由到目标 Actor 的 mailbox
        for (target_addr, msg) in new_messages:
            target = addr_table.lookup(target_addr)
            target.mailbox.push(msg)
            if not target.is_active:
                target.is_active = True
                global_run_queue.push(target)

        # 如果 mailbox 还有消息，重新放回运行队列
        if not actor.mailbox.is_empty():
            global_run_queue.push(actor)
        else:
            actor.is_active = False
```

**关键设计点**：

1. **一个 Actor 一次只处理一条消息**（单线程语义）——所以 Actor 内部不需要锁。
2. **多个 Worker 线程并发调度不同 Actor**——这是并发的来源。
3. **消息是"fire and forget"**——发送方不等待接收方处理。
4. **地址表（Address Table）** 是全局的——但 Actor 内部状态完全隔离。

### 第 6 层：四套主流实现的架构对比

| 框架 | 语言 | Actor 粒度 | 调度模型 | 消息语义 | 典型用途 |
|------|------|----------|---------|---------|---------|
| **Erlang/OTP** | Erlang | 进程（~300 字节） | 抢占式调度（reduction count） | 异步，可选择性同步（gen_server:call） | 电信、WhatsApp、RabbitMQ |
| **Akka** | Scala/Java | 对象（~400 字节） | 线程池 + Dispatcher | 异步 tell / 同步 ask（Future） | 金融交易、实时分析 |
| **Orleans** | C# | 虚拟 Actor（自动激活/钝化） | 单线程 Turn-Based | 异步 RPC 风格 | 游戏后端（Halo）、IoT |
| **skynet** | C + Lua | 服务（~几KB） | 多 Worker 线程 + 全局队列 | 异步 send / 同步 call（协程挂起） | 中国手游服务器 |

**为什么游戏服务器偏爱 Actor 模型？**

游戏服务器天然是 Actor 模型的完美匹配：

```text
游戏业务实体        →  Actor
──────────────────────────────────
一个玩家连接        →  一个 Actor（管理连接状态、心跳、消息转发）
一个战斗房间        →  一个 Actor（管理对局逻辑、帧同步）
一个匹配队列        →  一个 Actor（管理匹配算法、超时）
一个公会            →  一个 Actor（管理公会数据和广播）

通信模式：
  玩家登录          →  LoginActor.send(消息) → AuthActor.receive(消息)
  匹配成功          →  MatchActor.call(消息) → RoomActor.receive(消息)
  伤害计算          →  BattleActor.call(消息) → 等待返回
```

---

## Part B：UE Actor 复制 — 一种属性增量同步机制

> **关键区分**：UE 的 `AActor` + Replication 系统**不是** Actor Model 的实现。
> 它是 C/S 架构下的**有状态属性同步**：服务器维护权威状态，客户端接收增量更新。
> 之所以叫 "Actor"，是因为 UE 的游戏对象基类就叫 `AActor`，这是 Epic 的命名选择，与 CS Actor Model 无关。

### 第 1 层：直觉理解

**类比：GPS 导航更新**

你和朋友开车去同一个目的地。你们手机上都有地图 App（= 客户端），但只有你的手机有实时路况数据（= 服务器）。

- 你的手机 **不把整张地图** 发给朋友。太贵了（带宽）。
- 你的手机 **也不每秒发一次全量位置**。太浪费了。
- 你的手机只发 **变化了的部分**："前方 500 米拥堵"、"建议绕行路口 C"。
- 朋友的手机收到后更新显示，**但朋友不能自己改路况数据**——你才是权威。

UE 的 Actor Replication 就是这样：
- 服务器拥有 **AActor 的权威状态**（位置、血量、动画）。
- 每帧遍历需要同步的 Actor，对比**上次已发送的值**（Shadow State）和当前值。
- 只发送**变化的属性**。
- 客户端收到后更新本地副本，**但客户端不能篡改权威值**。

### 第 2 层：使用场景

**什么时候用 UE Replication？**

- ✅ 标准的 C/S 或 DS 架构游戏：FPS、TPS、MMO
- ✅ 有明确权威服务器的场景（服务器防作弊）
- ✅ 需要同步的属性数量可控（几十个属性/Actor，而非几千个）
- ✅ 不需要帧级确定性（不需要所有客户端帧帧一致）

**什么时候不该用？**

- ❌ 帧同步 (Lockstep) 游戏——需要的是确定性指令转发，不是属性增量
- ❌ 纯 P2P 游戏——Replication 系统设计上依赖服务器权威
- ❌ 物量极大的场景（如数千个实体同时同步）——每 Actor 一个 Channel 的开销太高
- ❌ 对延迟极度敏感的格斗游戏——Replication 叠加客户端预测后延迟仍在 30-80ms 范围

### 第 3 层：API 层—关键类和属性

#### 核心类层次

```text
UNetDriver (抽象基类 — 网络引擎)
  ├── UIpNetDriver (生产环境，UDP 实现)
  │     └── 持有 TArray<UNetConnection*> 管理所有客户端连接
  └── UDemoNetDriver (录像回放)

UNetConnection (一个客户端连接)
  ├── 持有 TArray<UChannel*> (所有打开的通道)
  ├── 管理可靠/不可靠数据包 (SendBunch / ReceivedPacket)
  └── 管理连接状态 (USOCK_Open / USOCK_Pending / USOCK_Closed)

UChannel (抽象通道基类)
  ├── UControlChannel (控制通道 — 连接握手、NMT_Hello)
  ├── UVoiceChannel (语音通道)
  └── UActorChannel ★ (Actor 属性复制通道)
        ├── AActor* Actor          (关联的 Actor)
        ├── FObjectReplicator      (Actor 自身的属性复制器)
        ├── TMap<UObject*, FObjectReplicator> ReplicationMap (子对象复制器)
        └── 方法: ReplicateActor() (核心复制入口)
```

#### 关键 Actor 属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `bReplicates` | `bool` | 设为 `true` 后，该 Actor 参与网络复制 |
| `bOnlyRelevantToOwner` | `bool` | `true` = 只复制给拥有者（如第一人称武器） |
| `NetUpdateFrequency` | `float` | 每秒最大复制次数（如 `100.0` = 最多 100Hz） |
| `NetPriority` | `float` | 优先级（带宽紧张时高优先级 Actor 优先发送） |
| `NetDormancy` | `ENetDormancy` | 休眠状态：`DORM_Awake` / `DORM_DormantAll` / `DORM_Initial` |
| `RemoteRole` | `ENetRole` | 客户端上的角色：`ROLE_SimulatedProxy` / `ROLE_AutonomousProxy` |

#### 属性复制宏

```cpp
// 在 AActor 子类中声明需要复制的属性
UPROPERTY(Replicated)
float Health;

// 在 GetLifetimeReplicatedProps 中注册
void AMyActor::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AMyActor, Health);                    // 无条件复制
    DOREPLIFETIME_CONDITION(AMyActor, Ammo, COND_OwnerOnly); // 仅复制给拥有者
}
```

#### RPC 函数标记

```cpp
UFUNCTION(Server, Reliable)        void ServerFire();       // 客户端→服务器
UFUNCTION(Client, Reliable)        void ClientShowDamage(); // 服务器→特定客户端
UFUNCTION(NetMulticast, Unreliable) void MulticastExplosion(); // 服务器→所有客户端
```

### 第 4 层：行为契约

#### 属性复制契约

```text
前置条件:
  - Actor.bReplicates == true
  - Actor 已被服务器创建并注册到 NetDriver
  - 客户端已加载 Actor 所在的 Level
  - Actor 对目标连接是"Relevant"的 (IsNetRelevantFor 返回 true)
  - Channel 未饱和（带宽未满）

后置条件:
  - 客户端收到包含变化属性的 FInBunch
  - 客户端调用对应的 RepNotify 回调 (OnRep_*)
  - 客户端的 Shadow State 更新为与服务器一致

不变量:
  - 服务器永远拥有权威状态 (ROLE_Authority)
  - 客户端永远不能修改权威属性（修改会被服务器覆盖）
  - 属性复制是单向的：Server → Client

异常/降级:
  - Channel 饱和：低优先级 Actor 本次跳过，下次 Tick 重试
  - Actor 变为 Dormant：停止复制，直到再次 Awake
  - Actor 不再 Relevant：Channel 关闭（5 秒宽限期）
  - 客户端未加载 Level：Channel 暂缓，等 Level 加载后打开
```

#### RPC 可靠性契约

```text
Reliable RPC:
  - 保证送达且按序执行
  - 如果丢包，底层自动重传（类似 TCP 的 ACK/NACK 机制）
  - 代价：延迟增加（需要等待确认）

Unreliable RPC:
  - 不保证送达，丢包不重传
  - 适用于高频、幂等、可丢失的数据（如位置更新）
  - 代价：可能丢失
```

### 第 5 层：实现原理—复制流程全貌

以下流程基于 UE 5.5 官方文档和源码 (NetDriver.h/ActorChannel.h)。

#### 总览：五个关键阶段

```text
阶段 1: 收集候选 Actor       ServerReplicateActors() 开始
阶段 2: 按连接筛选+排序       ForEach Connection
阶段 3: 相关性检查           IsNetRelevantFor / Channel 管理
阶段 4: 属性序列化            UActorChannel::ReplicateActor / FObjectReplicator
阶段 5: 数据包发送            NetDriver::TickFlush → Socket Write
```

#### 阶段 1：收集候选 Actor（伪代码）

```python
def ServerReplicateActors(net_driver):
    considered_actors = []

    for actor in world.all_actors:
        # 跳过不参与复制的 Actor
        if not actor.bReplicates:
            continue

        # 跳过初始休眠的 Actor
        if actor.net_dormancy == DORM_Initial:
            continue

        # 检查更新频率：距上次复制是否达到最小间隔
        time_since_last_update = now - actor.last_update_time
        min_interval = 1.0 / actor.net_update_frequency
        if time_since_last_update < min_interval:
            continue

        # 如果只复制给 Owner
        if actor.b_only_relevant_to_owner:
            owner_connection = actor.owner.connection
            if actor.is_relevancy_owner_for(owner_connection.viewer):
                owner_connection.owned_relevant_list.append(actor)
            continue  # 进入 Owner 专有列表，不放通用列表

        # 调用 PreReplication — 允许蓝图/C++ 做最后过滤
        actor.pre_replication()

        considered_actors.append(actor)

    return considered_actors
```

#### 阶段 2：按连接筛选

```python
def process_per_connection(net_driver, considered_actors):
    for connection in net_driver.client_connections:
        relevant_actors = []

        for actor in considered_actors:
            # 休眠检查
            if actor.net_dormancy == DORM_DormantAll:
                continue

            # 如果还没有 Channel
            if not connection.has_channel_for(actor):
                # 检查客户端是否已加载此 Actor 所在的 Level
                if not connection.is_level_loaded(actor.level):
                    continue
                # 相关性检查
                if not actor.is_net_relevant_for(connection):
                    continue

            relevant_actors.append(actor)

        # 追加 Owner 专有列表
        relevant_actors.extend(connection.owned_relevant_list)

        # 按优先级排序（降序）
        relevant_actors.sort(key=lambda a: a.net_priority, reverse=True)

        # 进入阶段 3
        replicate_per_connection(connection, relevant_actors)
```

#### 阶段 3：Channel 管理和最终复制

```python
def replicate_per_connection(connection, sorted_actors):
    for actor in sorted_actors:
        # 检查 Level 是否仍加载
        if not connection.is_level_loaded(actor.level):
            connection.close_channel_for(actor)
            continue

        # 每 1 秒重新检查相关性
        if time_since_last_relevancy_check(actor) >= 1.0:
            if not actor.is_net_relevant_for(connection):
                # 5 秒宽限期后关闭 Channel
                if actor.irrelevant_time >= 5.0:
                    connection.close_channel_for(actor)
                continue

        # 如果连接已饱和（带宽满）
        if connection.is_saturated:
            # 低优先级 Actor 推迟到下一帧
            if actor.relevant_time < 1.0:
                actor.force_update_next_tick = True
            continue

        # ★ 最终调用 — 执行实际的属性复制
        channel = connection.get_or_create_channel(actor)
        channel.replicate_actor()
```

#### 阶段 4：UActorChannel::ReplicateActor — 属性序列化核心

这是整个复制系统最关键的函数。位于 `Engine/ActorChannel.h` 和 `DataReplication.h`。

```python
def replicate_actor(channel, actor):
    bunch = FOutBunch()  # 输出数据包

    # step 1: 首次复制 — 发送 Spawn 信息
    if channel.is_first_update:
        bunch.write(actor.class)
        bunch.write(actor.initial_location)
        bunch.write(actor.initial_rotation)
        bunch.write(actor.net_guid)
        for component in actor.replicated_components:
            bunch.write(component.net_guid)

    # step 2: 角色降级
    # 如果客户端不拥有此 Actor 但它被标为 AutonomousProxy（BUG情况）
    # 强制降为 SimulatedProxy
    if not connection.owns(actor) and actor.remote_role == ROLE_AutonomousProxy:
        actor.remote_role = ROLE_SimulatedProxy

    # step 3: 复制 Actor 自身的变化属性
    actor_replicator = channel.actor_replicator  # FObjectReplicator
    actor_replicator.replicate_properties(bunch)
    # FObjectReplicator 内部：
    #   for each property in actor.replicated_properties:
    #       current_value = property.get(actor)
    #       if current_value != shadow_state[property]:
    #           FNetBitWriter.write(property.index)
    #           FNetBitWriter.write(current_value)
    #           shadow_state[property] = current_value

    # step 4: 复制每个 Component 的变化属性
    for component in actor.replicated_components:
        comp_replicator = channel.replication_map[component]
        comp_replicator.replicate_properties(bunch)

    # step 5: 标记已删除的 Component
    for deleted_comp in actor.deleted_components:
        bunch.write(DELETE_COMMAND)
        bunch.write(deleted_comp.net_guid)

    # step 6: 发送数据包
    connection.send_bunch(bunch)
```

#### DataReplication.h 中的 FObjectReplicator 核心逻辑

`FObjectReplicator` 是 UE 属性复制的实际执行者（UE 后期重构将复制逻辑从 UActorChannel 迁移到此处）。

```python
class FObjectReplicator:
    object              # UObject* — 被复制的对象（Actor 或 Component）
    connection          # UNetConnection* — 目标连接
    rep_layout          # FRepLayout — 复制属性布局（编译期生成的偏移表）
    shadow_state        # byte[] — 上次发送的属性值快照
    changed_properties  # set<int> — 本帧变化的属性索引

    def replicate_properties(self, bunch):
        # 对比当前值和 Shadow State
        for rep_index in range(self.rep_layout.num_properties):
            property_offset = self.rep_layout.offsets[rep_index]
            current_value = self.read_property(property_offset)
            shadow_value = self.shadow_state[rep_index]

            if current_value == shadow_value:
                continue  # 未变化，跳过

            # 标记为变化
            self.changed_properties.add(rep_index)
            self.shadow_state[rep_index] = current_value

        # 序列化变化属性到 bitstream
        writer = FNetBitWriter()
        writer.write_bits(len(self.changed_properties))  # 变化数量
        for rep_index in self.changed_properties:
            writer.write_bits(rep_index)                  # 属性索引
            writer.write_bits(self.get_property(rep_index))  # 属性值

        bunch.append(writer)
        self.changed_properties.clear()
```

**Delta Compression（增量压缩）的实现**：

UE 不只是"每次发变化值"，它还做了 bit-level 优化：
- 如果一个 `float` 的整数部分没变只变了小数部分，只发小数部分。
- 如果一个 `FVector` 只有 X 变了，只发 X 的 delta。
- 如果是 `bool` 属性，只需 1 bit。
- 属性值序列化使用变长整数编码（Variant Int）。

### 第 6 层：源码引用

以下是 UE 5 复制系统的关键源码位置：

| 文件 | 关键内容 | 版本 |
|------|---------|------|
| `Engine/Source/Runtime/Engine/Classes/Engine/NetDriver.h` | `UNetDriver::ServerReplicateActors()` 声明 + TickFlush | UE 5.5+ |
| `Engine/Source/Runtime/Engine/Private/NetDriver.cpp` | `ServerReplicateActors` 完整实现 | UE 5.5+ |
| `Engine/Source/Runtime/Engine/Classes/Engine/ActorChannel.h` | `UActorChannel` 类定义 + `ReplicateActor()` 声明 | UE 5.7 |
| `Engine/Source/Runtime/Engine/Private/ActorChannel.cpp` | `UActorChannel::ReplicateActor()` 完整实现 | UE 5.5+ |
| `Engine/Source/Runtime/Engine/Public/Net/DataReplication.h` | `FObjectReplicator` 声明 — 实际属性对比和序列化 | UE 5.5+ |
| `Engine/Source/Runtime/Engine/Private/DataReplication.cpp` | `FObjectReplicator::ReplicateProperties()` 实现 | UE 5.5+ |
| `Engine/Source/Runtime/Engine/Classes/Engine/EngineTypes.h` | `ENetRole`, `ENetDormancy` 枚举定义 | UE 5.5+ |

#### 参考官方文档的直接引用

来自 Epic 官方文档 "Detailed Actor Replication Flow"（UE 5.7，2025）：

> The majority of actor replication happens inside the `UNetDriver::ServerReplicateActors` function.
> This is where the server first gathers all actors it has determined to be relevant for each client,
> then sends any properties that have changed since the last time each connected client was updated.
> The `UActorChannel::ReplicateActor` function then handles the details of actor replication to a specific channel.

来自 `UActorChannel` API 文档的结构描述：

```text
An ActorChannel bunch looks like this:

+-------------------+---------------------------------------------------+
|     SpawnInfo     | (Spawn Info) Initial bunch only                  |
|  -Actor Class     | -Created by ActorChannel                         |
|  -Spawn Loc/Rot   |                                                   |
|  NetGUID assigns  |                                                   |
|  -Actor NetGUID   |                                                   |
|  -Component NetGUIDs |                                               |
+-------------------+---------------------------------------------------+
|                   |                                                   |
+-------------------+---------------------------------------------------+
| NetGUID ObjRef    | (Content chunks) x number of replicating objects |
|                   |  -Each chunk created by its own FObjectReplicator|
+-------------------+---------------------------------------------------+
|                   |                                                   |
|     Properties... |                                                   |
|                   |                                                   |
|        RPCs...    |                                                   |
+-------------------+---------------------------------------------------+
```

#### UE5 Iris 系统（下一代复制框架）

UE 5.x 开始引入 **Iris** (`Engine/Source/Runtime/Experimental/Iris/`)，重构了复制架构：

- 旧模型：`UActorChannel` 中心化 — 每个 Actor 对应一个 Channel
- 新模型 (Iris)：`ReplicationBridge` + `ReplicationSystem` — 去中心化，数据驱动
  - `UReplicationBridge`：替代 ActorChannel 的角色，负责将 Actor 状态桥接到复制系统
  - `UReplicationSystem`：调度中心，管理所有连接的复制优先级和带宽分配
  - `FNetRefHandle`：替代 FNetworkGUID，更高效的引用句柄

Iris 在 UE 5.5+ 中已默认启用，但 API 层（`UPROPERTY(Replicated)`）对上层完全透明。

---

## Part C：skynet 的 Actor 模型实现

> **skynet** 是云风 (cloudwu) 开发的轻量级游戏服务器框架，GitHub 14k+ stars。
> 它是 **真正的 Actor Model 实现**：每个 Lua 服务 (.lua 文件) 是一个 Actor，
> 拥有独立的 Lua VM 状态（通过 multi-state Lua 实现）、独立的消息队列、
> 通过 `skynet.send`（异步）和 `skynet.call`（同步等待）通信。

### 第 1 层：直觉理解

**类比：公司组织架构**

```
公司（skynet 进程）
  ├── 前台（网关 Actor）—— 接待访客（客户端连接）
  ├── HR 部门（登录 Actor）—— 验证身份
  ├── 会议室 A（战斗房 Actor #1）—— 正在开会的团队
  ├── 会议室 B（战斗房 Actor #2）—— 另一个团队
  └── 调度中心（Worker 线程池）—— 确保每个部门都有人在处理事务
```

- 每个部门（Actor）有自己的办公室（独立 Lua 状态），不能随意进入别人的办公室翻文件。
- 部门间通信靠**内部邮件**（`skynet.send`——异步）或**派人过去等回复**（`skynet.call`——协程挂起，等待响应）。
- 每个部门一次只处理一件事（协程驱动，单线程语义），但多个部门可以同时工作（多 Worker 线程）。
- 一个部门如果处理太慢，不会阻塞其他部门——邮件堆在信箱里排队。

### 第 2 层：使用场景

**skynet 特别适合**：

| 场景 | 为什么 |
|------|--------|
| 手游服务器（中国游戏行业广泛使用） | Actor 隔离 + 协程 = 开发心智负担低 |
| 网关服务器 | 高并发连接 → 每个连接一个协程处理 |
| 匹配服务器 | 逻辑简单但需要处理大量异步操作 |
| 聊天/社交服务器 | 广播消息天然适合 Actor 模型 |
| 小型到中型 MMO 逻辑服务器 | 服务间通信开销极低（同进程） |

**skynet 不太适合**：

| 场景 | 为什么 |
|------|--------|
| 高计算密度（如物理模拟） | Lua 性能上限 + 单 Actor 单线程 |
| 需要强类型安全的系统 | Lua 是动态类型 |
| 超大团队（100+ 服务类型） | skynet 的工具链和调试相对原始 |
| 需要跨语言互操作 | skynet 强绑定 C + Lua |

### 第 3 层：API 层—核心原语

#### skynet 服务的生命周期

```lua
-- myservice.lua — 一个 skynet Actor
local skynet = require "skynet"

-- 1. 启动入口（必须）
skynet.start(function()
    -- 注册消息处理函数
    skynet.dispatch("lua", function(session, source, cmd, ...)
        if cmd == "ping" then
            skynet.ret(skynet.pack("pong"))
        end
    end)

    -- 注册其他 Actor 可以调用的函数
    -- ...
end)
```

#### 核心 API 表格

| API | 签名 | 语义 |
|-----|------|------|
| `skynet.start(fn)` | 启动 Actor，fn 是该 Actor 的主协程函数 |
| `skynet.send(addr, type, ...)` | 异步发送消息到目标 Actor |
| `skynet.call(addr, type, ...)` | 同步调用：发送 → 挂起当前协程 → 收到响应后恢复 |
| `skynet.ret(...)` | 返回响应给 caller（在 dispatch 回调中使用） |
| `skynet.fork(fn, ...)` | 在当前 Actor 内启动新协程（不阻塞当前协程） |
| `skynet.timeout(ti, fn)` | 延迟 ti（单位 0.01s）后回调 fn |
| `skynet.newservice(name, ...)` | 创建新的 Actor（启动新的 Lua 服务） |
| `skynet.dispatch(type, fn)` | 注册消息处理器 |
| `skynet.wait(co)` | 挂起当前协程，等待被唤醒 |
| `skynet.wakeup(co)` | 唤醒指定协程 |
| `skynet.exit()` | 退出当前 Actor |

**消息类型常量**（定义在 skynet.h，导出到 Lua）：

```lua
skynet.PTYPE_TEXT = 0       -- 文本消息
skynet.PTYPE_RESPONSE = 1   -- 响应消息（call 的返回）
skynet.PTYPE_LUA = 10       -- Lua 消息（最常用）
skynet.PTYPE_SOCKET = 6     -- Socket 数据
skynet.PTYPE_ERROR = 7      -- 错误消息
skynet.PTYPE_SYSTEM = 4     -- 系统消息
```

#### 地址系统

skynet 的 Actor 地址是一个 **32 位无符号整数**（handle），编码了 harbor（节点 ID）和本地 ID：

```text
32-bit Handle:
  [ 8 bits harbor ] [ 24 bits local id ]

  同一进程内: harbor = 0
  跨进程:     harbor > 0 (通过 harbor 服务转发消息)
```

### 第 4 层：行为契约

#### 消息传递契约

```text
skynet.send(addr, type, ...):
  前置条件: addr 是一个有效的 Actor handle
  后置条件: 消息被放入目标 Actor 的 message_queue
  语义:     异步、非阻塞、不保证送达顺序
  失败处理: 如果目标 Actor 已退出，消息被投递到 PTYPE_ERROR

skynet.call(addr, type, ...):
  前置条件: addr 是一个有效的 Actor handle
  后置条件: 当前协程挂起，等待目标 Actor 调用 skynet.ret 返回
  语义:     同步（通过协程挂起/恢复实现，不阻塞 OS 线程）
  异常:     超时未收到响应 → 协程恢复但返回值 = false
```

#### Actor 隔离契约

```text
不变量:
  - 每个 Actor 拥有独立的 Lua state (lua_State*)
  - Actor 之间不能直接访问对方的 Lua 全局变量
  - 同一 Actor 的多个协程共享同一个 Lua state（所以协程间需要小心共享变量）
  - 不同 Actor 的协程运行在不同 Worker 线程上（天然并发安全）

线程安全:
  - Actor 内部不需要锁——同一时刻只有一个协程在执行
  - 全局消息队列 (global_mq) 有 spinlock 保护
  - 每个 Actor 的私有消息队列有 spinlock 保护
```

### 第 5 层：实现原理—完整调度链路

#### 架构总览

```text
┌──────────────────────────────────────────────────────────┐
│                    skynet 进程                             │
│                                                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                   │
│  │ Timer   │  │ Socket  │  │ Monitor │  ← 专用线程       │
│  │ Thread  │  │ Thread  │  │ Thread  │                    │
│  └────┬────┘  └────┬────┘  └────┬────┘                   │
│       │            │            │                          │
│       └────────────┼────────────┘                          │
│                    │ wakeup signal                         │
│                    ▼                                        │
│  ┌─────────────────────────────────────┐                  │
│  │         Global Message Queue         │                  │
│  │  (spinlock-protected linked list)    │                  │
│  │  [ServiceA Queue]→[ServiceB Queue]→...│                │
│  └──────────┬──────────────────────────┘                  │
│             │ Worker Threads pop queues                    │
│     ┌───────┼───────┬───────┬───────┐                     │
│     ▼       ▼       ▼       ▼       ▼                      │
│  Worker0  Worker1  Worker2  Worker3  ... (N threads)      │
│     │       │       │       │                              │
│     │  pop message from queue                              │
│     │  dispatch to Lua callback                            │
│     │  if coroutine yields → save state                   │
│     │  send new messages → push to target queues          │
│     │  if queue empty → return NULL, worker sleeps        │
│     ▼                                                      │
│  ┌──────────────────────────────────────┐                 │
│  │     Service Instances (Actors)        │                 │
│  │  ┌────────┐ ┌────────┐ ┌────────┐    │                 │
│  │  │Gate.lua│ │Auth.lua│ │Room.lua│... │                 │
│  │  │lua_State│ │lua_State│ │lua_State│  │                 │
│  │  │  + mq  │ │  + mq  │ │  + mq  │    │                 │
│  │  └────────┘ └────────┘ └────────┘    │                 │
│  └──────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────┘
```

#### Worker 线程的主循环（简化自 skynet_start.c:thread_worker）

```python
def thread_worker(worker_id, weight):
    monitor = monitors[worker_id]
    last_queue = None

    while not should_quit:
        # 核心调度函数 — 从全局队列取队列，取消息，分发
        last_queue = skynet_context_message_dispatch(
            monitor, last_queue, weight
        )

        if last_queue is None:
            # 没有可用的消息队列 → Worker 休眠
            pthread_mutex_lock(&global_mutex)
            sleep_count += 1
            # 等待被 timer/socket/monitor 线程唤醒
            pthread_cond_wait(&global_cond, &global_mutex)
            sleep_count -= 1
            pthread_mutex_unlock(&global_mutex)
```

#### 消息分发的核心函数（简化自 skynet_server.c）

```python
def skynet_context_message_dispatch(monitor, current_queue, weight):
    # 1. 从全局队列取出下一个有消息的 Actor 队列
    if current_queue is None:
        current_queue = skynet_globalmq_pop()
        if current_queue is None:
            return None  # 全局队列空 → worker 休眠

    # 2. 获取 Actor 的 context
    handle = current_queue.handle
    ctx = skynet_handle_grab(handle)
    if ctx is None:
        # Actor 已退出，释放队列，取下一个
        skynet_mq_release(current_queue, drop_message)
        return skynet_globalmq_pop()

    # 3. 权重调度 — 同一队列处理多条消息
    #    weight < 0: 处理 1 条（用于 timer 事件）
    #    weight = 0: 处理队列中所有消息
    #    weight > 0: 处理 weight 条
    n = 1 if weight < 0 else (weight if weight > 0 else MAX_INT)

    for i in range(n):
        if skynet_mq_pop(current_queue, message) != 0:
            # 队列空了
            skynet_context_release(ctx)
            return skynet_globalmq_pop()

        # 4. ★ 分发消息到 Actor 的回调函数
        dispatch_message(ctx, message)

        # 5. 监控检查 — 检测死循环
        skynet_monitor_trigger(monitor, message.source, handle)

    # 6. 权重耗尽但队列还有消息
    if skynet_mq_length(current_queue) > 0:
        skynet_globalmq_push(current_queue)  # 放回全局队列尾部

    skynet_context_release(ctx)
    return current_queue
```

#### dispatch_message — 消息路由到 Lua

```python
def dispatch_message(ctx, msg):
    # 从消息中解析类型和大小
    msg_type = msg.sz >> MESSAGE_TYPE_SHIFT
    msg_size = msg.sz & MESSAGE_TYPE_MASK

    # ★ 调用 Actor 注册的回调函数
    # 这个 cb 是 skynet.lua 层面注册的 _cb_dispatch
    reserve_msg = ctx.cb(
        ctx, ctx.cb_ud,
        msg_type,      # 消息类型 (PTYPE_LUA = 10, etc.)
        msg.session,   # 会话 ID (用于 call/response 配对)
        msg.source,    # 发送者地址
        msg.data,      # 消息数据
        msg_size       # 数据大小
    )

    if not reserve_msg:
        skynet_free(msg.data)  # 释放消息内存
```

#### Lua 层：消息接收 → dispatch → 协程调度

在 `lualib/skynet.lua` 中（skynet 仓库 master 分支）：

```lua
-- 这是 C 层调用的 Lua 回调
-- 当消息到达时被 dispatch_message 调用
local function raw_dispatch_message(prototype, msg, sz, session, source)
    -- 1. 查找消息类型的协议处理器
    local p = proto[prototype]
    if not p then return end

    -- 2. 如果是 RESPONSE 类型，唤醒等待该 session 的协程
    if prototype == skynet.PTYPE_RESPONSE then
        local co = session_id_coroutine[session]
        if co == "BREAK" then return end
        if co == nil then return end

        -- session 关联清理
        session_id_coroutine[session] = nil
        session_coroutine_id[co] = nil
        session_coroutine_address[co] = nil

        -- ★ 恢复挂起的协程，传入返回值
        return suspend(co, coroutine_resume(co, true, msg, sz, session))
    end

    -- 3. 解包消息
    local tag = session_coroutine_tracetag[running_thread]
    local co_trace = tag and c.trace(tag, "REQUEST", 4)

    local f = p.dispatch
    if f then
        -- 4. ★ fork 新协程执行消息处理
        local co = coroutine_create(function()
            p.dispatch(session, source, p.unpack(msg, sz))
        end)
        suspend(co, coroutine_resume(co))
    else
        -- 无 dispatch → 直接处理
        local co = coroutine_create(function()
            p.unpack(msg, sz)
        end)
        suspend(co, coroutine_resume(co))
    end
end
```

#### skynet.call 的同步等待实现

```lua
function skynet.call(addr, typename, ...)
    local p = proto[typename]
    local session = c.send(addr, p.id, nil, p.pack(...))  -- C 层发送

    if session == nil then
        error("call failed: invalid address")
    end

    -- ★ 挂起当前协程，等待响应
    -- yield "CALL" 让调度器知道这是 call 等待
    -- 当收到 PTYPE_RESPONSE 且 session 匹配时，协程被恢复
    return yield_call(session)
end

local function yield_call(session)
    watching_session[session] = true
    session_id_coroutine[session] = running_thread

    -- ★ 核心：yield 挂起当前协程
    -- 控制权返回给 skynet 调度器
    -- 当收到 RESPONSE 时，raw_dispatch_message 里 resume 此协程
    local succ, msg, sz = coroutine_yield("CALL", session)

    watching_session[session] = nil
    if not succ then
        error("call failed")
    end

    return p.unpack(msg, sz)
end
```

#### 消息队列实现（简化自 skynet_mq.c）

```python
# 全局队列 — 单链表，spinlock 保护
class GlobalQueue:
    head: MessageQueue  # 队首
    tail: MessageQueue  # 队尾
    lock: SpinLock

    def push(queue):
        with lock:
            if tail:
                tail.next = queue
                tail = queue
            else:
                head = tail = queue

    def pop():
        with lock:
            mq = head
            if mq:
                head = mq.next
                if not head:
                    tail = None
                mq.next = None
            return mq

# 每个 Actor 的私有消息队列 — 环形缓冲区 + spinlock
class MessageQueue:
    handle: uint32
    queue: Message[]     # 环形缓冲区
    cap: int             # 容量（初始 64，按需翻倍）
    head: int            # 读指针
    tail: int            # 写指针
    in_global: int       # 是否已在全局队列中
    lock: SpinLock

    def push(msg):
        with lock:
            queue[tail] = msg
            tail = (tail + 1) % cap
            if head == tail:
                expand_queue()     # 队列满 → 扩容为 2x
            if in_global == 0:
                in_global = 1
                global_queue.push(self)  # 加入全局调度

    def pop(msg):
        with lock:
            if head == tail:
                in_global = 0
                return 1        # 队列空
            msg = queue[head]
            head = (head + 1) % cap
            return 0            # 成功
```

### 第 6 层：源码引用

| 文件 | 关键内容 | 版本 |
|------|---------|------|
| `skynet-src/skynet_server.c` | `skynet_context` 结构体、`skynet_context_new()`、`dispatch_message()`、`skynet_context_message_dispatch()` | master (d60c98b) |
| `skynet-src/skynet_start.c` | `thread_worker()` 主循环、`thread_timer()`、`thread_socket()`、`start()` | master |
| `skynet-src/skynet_mq.c` | `message_queue` 环形缓冲区、`global_queue` 单链表、`skynet_mq_push/pop` | master |
| `lualib/skynet.lua` | Actor 的 Lua 层实现：`skynet.send/call/fork/wait/timeout`、session 管理、协程调度 | master |
| `skynet-src/skynet_module.c` | C 模块加载器（dlopen） | master |
| `skynet-src/skynet_handle.c` | Handle 注册表（地址→context 映射） | master |
| `skynet-src/skynet_harbor.c` | 跨节点消息路由（harbor 服务） | master |

#### 关键数据结构引用

`skynet_context` (skynet_server.c:40-60):

```c
struct skynet_context {
    void * instance;              // Lua state (lua_State*)
    struct skynet_module * mod;   // 模块指针
    void * cb_ud;                 // 回调用户数据
    skynet_cb cb;                 // 消息回调函数
    struct message_queue *queue;  // ★ 消息队列
    uint32_t handle;              // ★ Actor 地址
    int session_id;               // 会话 ID 计数器
    ATOM_INT ref;                 // 引用计数
    bool init;                    // 是否已初始化
    bool endless;                 // 是否无限循环
    bool profile;                 // 性能剖析开关
};
```

`message_queue` (skynet_mq.c:14-26):

```c
struct message_queue {
    struct spinlock lock;
    uint32_t handle;
    int cap;                      // 环形缓冲区容量
    int head;                     // 读指针
    int tail;                     // 写指针
    int release;                  // 释放标记
    int in_global;                // 是否在全局队列中
    int overload;                 // 过载计数
    int overload_threshold;       // 过载阈值（默认 1024）
    struct skynet_message *queue; // 环形缓冲区
    struct message_queue *next;   // 全局队列链表指针
};
```

---

## 第 7 层：对比与边界

### UE Replication vs skynet Actor Model vs CS Actor Model

| 维度 | CS Actor Model (理论) | skynet Actor (实现) | UE Actor Replication |
|------|----------------------|--------------------|--------------------|
| **通信方式** | 纯异步消息 | `send`(异步) + `call`(同步/协程) | 属性推送 (Server→Client) + RPC |
| **状态所有权** | 每个 Actor 拥有自己状态 | 每个 Lua 服务拥有自己的全局变量表 | 服务器独有权威，客户端是缓存 |
| **并发模型** | 天然并发，消息驱动 | 多 Worker 线程 + 单 Actor 单协程 | 单线程 Tick（主循环），网络 IO 在 NetDriver |
| **隔离性** | 完全隔离，消息唯一通信手段 | Lua state 隔离，同 Actor 协程共享 | 无隔离 — 所有 Actor 在同一内存空间 |
| **创建语义** | 任意 Actor 可创建新 Actor | `skynet.newservice()` | 服务器创建，通过 Channel 告知客户端 |
| **失败处理** | 独立失败，可监督 | 独立失败，父服务可选监控 | 服务器为单一故障域 |
| **用途** | 通用并发模型 | 游戏服务器后端 | 游戏客户端-服务器状态同步 |
| **可扩展性** | 理论无上限 | 单进程 ~数千 Actor（实测） | 单 DS ~数百同步 Actor |

### 性能特征

| 指标 | skynet | UE Replication |
|------|--------|---------------|
| 消息延迟（同进程） | ~微秒级（共享内存） | N/A（网络 RTT） |
| Actor 创建开销 | ~毫秒（启动 Lua state） | ~微秒（构造 C++ 对象） |
| 单 Actor 内存占用 | ~几 KB + Lua state 开销 | ~几百字节（AActor 对象） |
| 带宽效率 | 只发送消息数据 | 增量压缩 + bit-level 优化 |
| 最大并发 Actor | ~10000+（受内存限制） | ~1000（受单线程 Tick 限制） |

### 设计取舍

**skynet 的选择**：

1. **单进程多服务**（而非多进程）：通信走共享内存所以极快，代价是无法利用多机横向扩展（需要用 harbor 跨进程通信来弥补）。
2. **协程而非线程**：开发者心智负担低（没有 race condition），代价是 CPU 密集型计算会阻塞同一 Actor 的其他消息。
3. **Lua 而非 C++**：开发快、热更新友好，代价是性能上限和类型安全。

**UE Replication 的选择**：

1. **属性推送而非消息**：开发者只需标记属性，框架自动处理同步——开发效率极高。代价是灵活性差：不能自定义"哪些属性在什么条件下发给谁"到精细级别（虽然有 CONDITIONS 宏，但远不如手写网络包灵活）。
2. **增量而非全量**：节省大量带宽，代价是实现复杂度高（Shadow State 管理、RepLayout 代码生成）。
3. **UDP + 可靠性层**：低延迟但需要自己实现 ACK/NACK——在 UChannel 层面做了大量工程工作来保证可靠消息的送达。

---

## 常见面试题

### Q1: UE 的 `bReplicates` 和 `Replicated` 标记有什么区别？

**答**：`bReplicates = true` 是 Actor 级别的开关——告诉 NetDriver "这个 Actor 参与网络复制"。
`UPROPERTY(Replicated)` 是属性级别的标记——告诉反射系统"这个属性在 Actor 参与复制时，需要对比变化并序列化"。
前者是前提，后者是内容。`bReplicates = false` 的 Actor 即使有 Replicated 属性也不会被同步。

### Q2: skynet 中 `skynet.send` 和 `skynet.call` 的底层区别是什么？

**答**：两者都调用 C 层的 `skynet_context_push` 将消息放入目标 Actor 的消息队列。
区别在于：
- `send`：发完就返回，不挂起协程。
- `call`：发送时会分配一个 `session_id`，然后 `coroutine_yield` 挂起当前协程。
  当目标 Actor 调用 `skynet.ret()` 时，C 层构造一个 `PTYPE_RESPONSE` 消息发回调用方。
  Lua 层收到 `PTYPE_RESPONSE` 后，根据 `session_id` 找到挂起的协程并 `coroutine_resume`。

### Q3: 为什么 UE 的 Replication 不适合帧同步游戏？

**答**：帧同步 (Lockstep) 的核心要求是：**所有客户端以相同的顺序执行相同的指令，产生完全相同的结果**。
UE Replication 完全不保证这一点——它推送的是属性变更结果，不是"导致这个结果的指令"。
而且 Replication 是有损的——可能跳过中间值（只发最终值），这在帧同步中意味着不同客户端走到了不同的游戏状态。

### Q4: skynet 的单 Actor 内如果有一个协程做了死循环，会影响其他协程吗？

**答**：会影响。skynet 是**协作式多任务**——协程必须主动 yield 才能让出执行权。
如果一个协程进入死循环且不 yield，该 Actor 的所有其他协程永久无法执行。
这是协程模型的核心权衡：实现简单（无抢占），但需要开发者自律。
skynet 的 Monitor 线程会检测这种情况并报告 "Maybe an endless loop" 警告。

### Q5: Actor Model 和 CSP (Communicating Sequential Processes) 的核心区别是什么？

**答**：

| 维度 | Actor Model | CSP (Go channel) |
|------|------------|-------------------|
| 通信对象 | 有地址的 Actor | 匿名 Channel |
| 消息传递 | 异步（发送即忘） | 同步（发送方阻塞直到接收方就绪，除非 buffered channel） |
| 创建语义 | 动态创建 Actor | 固定拓扑（goroutine + channel，但可以用 channel 传 channel） |
| 不确定性 | 无限制非确定性 | 有限非确定性 |
| 典型实现 | Erlang, Akka, skynet | Go, Clojure core.async, Rust tokio::mpsc |

最根本的区别：Actor 通过**命名实体**通信，CSP 通过**匿名通道**通信。这导致 Actor 天然适合表示"业务实体"（玩家、房间、公会），而 CSP 更适合表示"数据流管道"。

---

## 延伸主题

学完这个后可以探索的相关主题：

1. **GGPO 回滚网络**：格斗游戏的 P2P 帧同步，输入预测 + 状态回滚 — 一种介于 Lockstep 和 State Sync 之间的方案
2. **Erlang OTP 的 Supervisor 树**：Actor 模型的"失败容错"模式 — "let it crash"
3. **Orleans Virtual Actor**：Actor 自动激活/钝化，物理位置完全透明 — 游戏服务器的新方向
4. **UE Iris 系统源码导读**：UE 5.5+ 的下一代复制框架 — 从 Channel 模型到 ReplicationSystem 的架构演进
5. **Deterministic Lockstep 的实现细节**：浮点数确定性、随机数种子的同步、Checksum 校验 — 与 Replication 完全不同的世界
6. **QUIC 协议在游戏网络中的应用**：Google 的新传输协议，0-RTT 握手 + 多路复用 — 解决 UDP 可靠性问题的现代答案
