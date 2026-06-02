# 状态同步核心原理：权威服务器模型

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: 04 - 游戏循环与网络Tick集成

---

## 1. 概念讲解

### 1.1 为什么需要状态同步？

在帧同步（第5节）中，我们学习了这样一种哲学：**不要同步结果，同步原因**。每个客户端拿到相同的输入序列，独立运行相同的确定性逻辑，自然能得到相同的结果。

这套方案在 RTS 和 MOBA 中非常成功。但如果你要做的是下面这类游戏，它就会暴露出致命的短板：

- **FPS（第一人称射击）**：玩家需要在几百毫秒内瞄准敌人的头部。等你把输入发到服务器、等服务器广播、等所有客户端都跑完逻辑帧……敌人早就跑了。
- **MMO（大型多人在线）**：地图上有数千个玩家和 NPC。同步 2000 个单位的位置/血量/状态/装备信息？帧同步的"所有客户端执行所有逻辑"意味着每个客户端都要模拟整个世界——手机根本算不动。
- **大逃杀/生存**：物理模拟（子弹弹道、爆炸冲击波）、AI 行为树、随机掉落……这些逻辑天然不是确定性的。强行做成确定性需要付出天文数字的工程代价。

状态同步正是在这些场景下诞生的替代方案。它的核心哲学与帧同步恰好相反：

> **不要同步原因，同步结果。让服务器来承担"原因→结果"的计算。**

与其让所有客户端独立计算，不如让一台服务器算好一切，然后把最终状态广播给所有客户端。客户端不"思考"——它们只是"播放"服务器告诉它们的状态。

### 1.2 权威服务器 (Authoritative Server)

权威服务器是整个状态同步架构的基石。一句话定义：

> **服务器是游戏世界的唯一真相源（Source of Truth）。客户端的任何行为，必须经过服务器验证才能成为"事实"。**

让我们用一张图来理解这个关系：

```
                     ┌──────────────────────┐
                     │      权威服务器        │
                     │  (Source of Truth)    │
                     │                      │
                     │  ┌────────────────┐   │
                     │  │  游戏世界状态    │   │
                     │  │  - 玩家A位置     │   │
                     │  │  - 玩家B血量     │   │
                     │  │  - 子弹C轨迹     │   │
                     │  │  - NPC D行为     │   │
                     │  └────────────────┘   │
                     │          │             │
                     │    运行所有游戏逻辑     │
                     │    物理/技能/AI/判定   │
                     └──┬─────────────┬──────┘
                        │             │
              状态更新 ↓             ↓ 状态更新
                  ┌──────┐       ┌──────┐
                  │客户端A│       │客户端B│
                  │      │       │      │
                  │ "哑"  │       │ "哑"  │
                  │ 终端  │       │ 终端  │
                  └──┬───┘       └──┬───┘
                     │              │
              输入上传 ↑        输入上传 ↑
              (移动/射击)      (移动/射击)
```

**权威性的三层含义**：

1. **逻辑权威**：所有游戏逻辑（伤害计算、碰撞检测、技能效果、AI决策）在服务器上运行。客户端的计算结果不被信任。
2. **状态权威**：服务器维护的世界状态是唯一合法的。客户端的本地状态可以被服务器覆盖（这在第15节"服务端和解"中会详细展开）。
3. **仲裁权威**：当客户端A声称"我打中了客户端B"，客户端B声称"我没被打中"，只有服务器的判定才是最终裁定。

**关键洞察**：这与帧同步的"服务器中转"模型有根本不同。帧同步中，服务器只是**转发输入**（它不执行逻辑）；状态同步中，服务器是**执行逻辑**（它做一切计算）。

为什么必须是服务器？因为：

- **反外挂**：如果玩家的客户端声称"我瞬间移动到了地图对面"，没有服务器验证，外挂就有了无限空间。状态同步中，服务器只信任自己算出的位置。
- **统一视图**：2 个玩家看到的延迟不同（A 200ms，B 50ms），它们各自即时看到的"世界"不同。但服务器维护唯一的世界，消除了分歧。
- **水平扩展**：服务器可以拆分到多个进程/机器（第 21 节详述），状态同步的架构天然支持这一点。

### 1.3 客户端角色："哑终端" (Dumb Terminal)

在纯状态同步模型中，客户端被设计为 **"哑终端"**：

> 客户端不计算游戏逻辑，只负责三件事：**采集输入 → 发送给服务器 → 渲染服务器返回的状态**。

```
客户端渲染循环:
  ┌─────────────────────────────────────────────┐
  │  while (true) {                              │
  │    // 1. 采集玩家输入                          │
  │    Input input = ReadPlayerInput();           │
  │                                              │
  │    // 2. 发送给服务器（ServerRPC）              │
  │    SendToServer(input);                      │
  │                                              │
  │    // 3. 接收服务器下发的状态更新                │
  │    WorldState state = ReceiveFromServer();    │
  │                                              │
  │    // 4. 渲染                                │
  │    Render(state);                            │
  │  }                                           │
  └─────────────────────────────────────────────┘
```

注意第 3 步和第 4 步之间没有任何"计算"。客户端不需要做碰撞检测、伤害公式、AI 行为——这些都发生在服务器上。客户端只是把服务器告诉它的位置、旋转、动画状态画出来。

**"哑终端"的程度是一个光谱**。实际工程中很少是"完全哑"的——现代游戏通常会加入客户端预测（第 14 节）来掩盖网络延迟，但这只是"预测"而非"权威决策"。此外，纯客户端表现逻辑（粒子特效、UI动画、本地音效）不需要服务器参与，这些天然属于客户端。

**关键设计决策**：哪些逻辑放服务器，哪些放客户端？

| 逻辑类型 | 位置 | 原因 |
|---------|------|------|
| 伤害计算 | 服务器 | 反外挂核心 |
| 碰撞检测 | 服务器 | 防止穿墙/瞬移外挂 |
| AI 行为树 | 服务器 | NPC 行为必须统一 |
| 掉落/随机 | 服务器 | 防止刷装备 |
| 粒子特效 | 客户端 | 纯表现，不影响游戏 |
| UI 交互 | 客户端 | 本地体验 |
| 脚步声/枪声 | 客户端 | 即时反馈 |

### 1.4 属性复制 (Property Replication)

属性复制是状态同步中 **服务器→客户端** 单向数据流的核心机制。它的工作方式是：

> 服务器在每个网络 Tick 结束时，遍历所有"需要同步"的属性（Property），找出哪些属性发生了变化，然后将变化后的值打包发送给相关的客户端。

**一个典型的状态同步实体**（用概念性伪代码表示）：

```csharp
// 服务器上的"网络实体"定义
class PlayerEntity : NetworkEntity {
    // 标记为 [Replicated] 的属性会自动同步到客户端
    [Replicated] Vector3   Position;     // 每 Tick 都可能变化 → 高频同步
    [Replicated] Quaternion Rotation;    // 同上
    [Replicated] float     Health;       // 受伤/治疗时变化 → 按需同步
    [Replicated] int       Score;        // 得分变化 → 按需同步
    [Replicated] WeaponId  CurrentWeapon;// 切枪时变化 → 事件驱动同步

    // 不标记的属性：服务器私有，客户端不可见
    float moveSpeed;           // 服务器自己用于移动计算
    List<DamageRecord> history;// 伤害历史，仅供反外挂分析
}
```

**属性复制的三个关键设计点**：

#### ① 谁来决定"需要同步"？

服务器需要对每个属性维护一个 **脏标记 (Dirty Flag)**：

```
┌─────────────────────────────────┐
│ 每个 Tick:                       │
│   for each entity:               │
│     for each property:           │
│       if property.IsDirty():     │
│         add to sync packet       │
│         property.ClearDirty()    │
└─────────────────────────────────┘
```

不是所有属性都需要同步。区分**高频属性**（Position、Rotation——每 Tick 都可能变）和**低频属性**（Health、Score——只在事件发生时变）。高频属性可以用专门的快速通道；低频属性用"变化才同步"的策略。

#### ② 发给谁？

不是所有客户端都需要看到所有属性。这就是 **AOI (Area of Interest，兴趣区域)** 和 **相关性 (Relevancy)** 的概念：

- 你的位置 → 附近玩家需要看到
- 你的血量 → 队友需要看到（可能全队）；敌人不需要看到
- 你的装备 → 所有玩家可能需要看到（外观）；详细属性只有你自己能看到

这引出了**复制组 (Replication Group)** 的概念——将属性分组，不同组发给不同的客户端集合。Unreal Engine 的 `Replication Graph` 和 Unity NGO 的 `NetworkVisibility` 都是做这件事的。

#### ③ 同步频率和优先级

网络带宽有限，服务器必须决定**先同步谁、同步多频繁**：

```
优先级 = f(距离, 重要性, 变化幅度)
  - 离你最近的敌人 → 高优先级，高频率
  - 地图对面的队友 → 低优先级，低频率
  - 你自己的角色  → 最高优先级（本地预测 + 服务端确认）
```

**属性复制的完整流程（一帧内）**：

```
服务端 Tick 开始
    │
    ▼
执行所有实体的逻辑（移动、攻击、技能...）
    │
    ▼
收集脏属性 ── 遍历所有 [Replicated] 属性
    │
    ▼
确定目标客户端 ── AOI / 相关性 / 复制组
    │
    ▼
序列化 ── 将 (ObjectId, PropertyId, NewValue) 序列化成字节流
    │
    ▼
打包发送 ── 一个 UDP 包可能包含多个实体的多个属性更新
    │
    ▼
服务端 Tick 结束
```

客户端收到后：

```
客户端收到状态更新包
    │
    ▼
反序列化 ── 解析出 (ObjectId, PropertyId, NewValue)
    │
    ▼
应用状态 ── entity.Position = newPosition; entity.Health = newHealth;
    │
    ▼
触发回调 ── OnHealthChanged?.Invoke(old, new)（UI 更新等）
```

### 1.5 RPC (Remote Procedure Call)

RPC 是状态同步中**双向**通信的机制，补充了属性复制的单向性：

```
属性复制: 服务器 ──状态──► 客户端  （单向，连续）
RPC:      客户端 ──事件──► 服务器  （ServerRPC）
          服务器 ──事件──► 客户端  （ClientRPC）
```

#### ServerRPC（客户端 → 服务器）

客户端告诉服务器"玩家做了什么"。这是**输入上传**的标准方式：

```csharp
// 客户端代码：玩家按下射击键
void Update() {
    if (Input.GetKeyDown(KeyCode.Space)) {
        // 发送 ServerRPC：告诉服务器"我想射击"
        FireWeaponServerRpc(targetPosition, currentWeaponId);
    }
}

// 这个函数在服务器上执行（不是在客户端！）
[ServerRpc]
void FireWeaponServerRpc(Vector3 target, int weaponId) {
    // ① 验证合法性（防止外挂）
    if (!CanFire(weaponId)) return;           // 冷却中？弹药？
    if (Vector3.Distance(transform.position, target) > weaponRange) return; // 超射程？

    // ② 执行实际的游戏逻辑
    SpawnProjectile(transform.position, target, weaponId);
    ConsumeAmmo(weaponId);
    StartCooldown(weaponId);

    // ③ 如果命中，服务端直接处理（下一个 Tick 属性复制会通知其他客户端）
    if (HitSomething(target, out var victim)) {
        ApplyDamage(victim, CalculateDamage(weaponId, target));
    }
}
```

**ServerRPC 的执行上下文**：
- 调用方是客户端，但函数体在**服务器**上执行
- 服务器有完全的自由来"接受"或"拒绝"这个请求
- 参数由客户端提供，但服务器**必须验证**每一项参数——不可信任客户端传来的任何数据

#### ClientRPC（服务器 → 客户端）

服务器告诉客户端"发生了某件事"。通常是**一次性事件**，不适合用属性复制（因为不是持续性状态）：

```csharp
// 服务器代码：某个玩家使用了终极技能
void OnUltimateActivated(int playerId) {
    // 更新状态（属性复制会处理）
    player.UltimateReady = false;
    player.Energy = 0;

    // 发送 ClientRPC：告诉所有客户端"播放特效"
    PlayUltimateEffectClientRpc(playerId, ultimateEffectId);
}

// 这个函数在所有客户端（或特定客户端）上执行
[ClientRpc]
void PlayUltimateEffectClientRpc(int playerId, EffectId effectId) {
    // 每个客户端根据自己的位置播放特效和音效
    GameObject vfx = Instantiate(GetEffectPrefab(effectId));
    vfx.transform.position = GetPlayerPosition(playerId);
    AudioManager.PlayUltimateSound(effectId);
}
```

**属性复制 vs RPC 的选择指南**：

| 场景 | 用属性复制 | 用 ClientRPC |
|------|-----------|-------------|
| 玩家持续移动 | ✅ Position 每帧变化 | ❌ 帧帧发 RPC 浪费 |
| 一次性播放音效 | ❌ 用 "PlayedSound" 布尔属性？别扭 | ✅ 自然的事件语义 |
| 显示伤害飘字 | ❌ 每个伤害数字一个属性？不现实 | ✅ 轻量事件 |
| 对话/任务进度 | ✅ 持续性状态 | ❌ 除非是一次性通知 |
| 死亡/复活 | ✅ 状态切换（isDead: false→true） | ✅ 同时触发死亡动画 RPC |

**RPC 的可靠性语义**：

不同的 RPC 可能需要不同的交付保证：

```
即时 RPC（Unreliable）:  发送即忘，丢包不重传 → 适用于高频事件（移动、瞄准方向）
可靠 RPC（Reliable）:    保证到达，有序 → 适用于关键事件（射击、使用技能、交互）
```

Unity NGO 的默认 RPC 是可靠的。Unreal 支持 `Reliable` 和 `Unreliable` 两种标记。

### 1.6 网络对象标识 (NetworkId, Spawn/Despawn)

在状态同步系统中，服务器和客户端需要**用同一个 ID 引用同一个游戏对象**。这就是 NetworkId。

#### NetworkId 的生成与管理

```
服务器维护一个 NetworkId 分配器:
  ┌──────────────────────────────┐
  │  uint32 nextId = 1;          │
  │                              │
  │  NetworkId Allocate() {      │
  │    return nextId++;          │
  │  }                           │
  │                              │
  │  Dictionary<NetworkId,        │
  │             GameObject>       │
  │    spawnedObjects;           │
  └──────────────────────────────┘
```

关键设计：
- **NetworkId 由服务器分配**——客户端没有分配权，保证全局唯一
- **服务器和客户端维护同一个映射表**：`NetworkId → GameObject/Entity`
- **NetworkId 是持续增长的**（或在长运行会话中可回收），uint32 足够容纳数十万个对象

#### Spawn（生成）流程

```
客户端加入游戏
    │
    ▼
服务器遍历所有已存在的网络对象
    │
    ▼
对每个对象: 发送 Spawn 消息
    │  消息内容: {
    │    NetworkId: 5,
    │    PrefabId: "PlayerCharacter",
    │    OwnerClientId: 2,
    │    InitialProperties: { Position: (10,0,5), Health: 100, ... }
    │  }
    │
    ▼
客户端收到 Spawn 消息
    │
    ├─ Instantiate(PrefabId) → 创建本地 GameObject
    ├─ 绑定 NetworkId = 5 到这个对象
    ├─ 应用初始属性
    └─ 开始接收该对象的后续属性更新
```

**新对象生成时**（如玩家发射了一颗子弹）：

```
服务器:
  Projectile proj = Instantiate(bulletPrefab);
  proj.NetworkId = AllocateNetworkId(); // 分配 ID 103
  proj.Spawn(); // 通知所有相关客户端

客户端收到 Spawn(NetworkId=103, PrefabId="Bullet", Position=..., Velocity=...):
  创建子弹对象，绑定 ID 103
```

#### Despawn（销毁）流程

```
服务器决定销毁对象（子弹命中、敌人死亡、道具被拾取）
    │
    ▼
发送 Despawn(NetworkId=103) 给相关客户端
    │
    ▼
客户端:
  查找 NetworkId=103 的本地对象
  Destroy(gameObject)
  从映射表中移除
```

**Spawn/Despawn 的可靠性要求**：
- Spawn 和 Despawn 消息**必须可靠传输**——丢了一个 Spawn 消息，客户端就永远不知道这个对象的存在；丢了一个 Despawn，僵尸对象永远留在场景中
- 通常使用可靠有序通道（Reliable Ordered），保证 Spawn 先于该对象的任何属性更新到达

### 1.7 状态同步 vs 帧同步：核心对比

这是面试中的高频问题，值得深入理解。

#### 数据流对比

```
帧同步（Lockstep）:
  客户端A ──输入──► 服务器 ──广播所有输入──► 客户端A、B、C
                         │
                   （服务器不执行逻辑）
                         │
  客户端A、B、C ◄──── 各自独立执行逻辑 ────► 必须得到相同结果

状态同步（State Sync）:
  客户端A ──输入(ServerRPC)──► 服务器
  客户端B ──输入(ServerRPC)──► 服务器
                                 │
                          服务器执行所有逻辑
                          （唯一权威计算节点）
                                 │
  客户端A ◄── 状态复制 ──┤  ├── 状态复制 ──► 客户端B
  客户端C ◄── 状态复制 ──┘
```

#### 多维度对比表

| 维度 | 帧同步 | 状态同步 |
|------|--------|---------|
| **传输内容** | 玩家输入（~16 bytes/frame/player） | 游戏状态（position/rotation/health/... 数百~数千 bytes/frame） |
| **传输频率** | 高频（15-30Hz，每帧都发） | 低频到中频（5-30Hz，可变速/按需） |
| **带宽特征** | 极小（与玩家数成正比，与实体数无关） | 较大（与实体数和属性数成正比） |
| **计算位置** | 所有客户端+服务器（服务器仅转发） | 服务器唯一计算 |
| **一致性模型** | 强一致（逐比特相同，确定性逻辑） | 最终一致（服务器权威，客户端追随） |
| **延迟敏感性** | 极敏感（一个慢玩家拖累所有人） | 可容忍（客户端预测掩盖延迟） |
| **断线重连** | 复杂（需要从头执行所有丢失的逻辑帧） | 简单（服务器直接发送当前状态快照） |
| **录像回放** | 极简（录像 = 初始状态 + 输入序列，几十KB） | 较复杂（需记录状态快照或 replays） |
| **反外挂** | 困难（客户端执行逻辑，外挂可见所有数据） | 天然（服务器闭门计算，客户端只看到结果） |
| **服务器负载** | CPU 负载低（只做转发+校验） | CPU 负载高（执行所有游戏逻辑） |
| **最适游戏类型** | RTS、MOBA、回合制 | FPS、TPS、MMO、大逃杀 |
| **最适实体数量** | 数百~数千（客户端能模拟的极限） | 理论上无限（客户端只渲染附近） |
| **确定性要求** | **必须**确定性（定点数/确定物理） | 不需要（服务器说了算） |

#### 最核心的本质区别

用一句话概括：

- **帧同步**：传输**操作**，在所有端复现**过程**
- **状态同步**：传输**结果**，在所有端展示**快照**

这引出一个深刻的推论：**帧同步是"计算分布式"，状态同步是"计算集中式"**。帧同步把计算分摊到了每个客户端上（省服务器但要求确定性）；状态同步把计算集中到了服务器上（耗服务器但解放了客户端的确定性约束）。

### 1.8 状态同步的网络模型

#### ① Update Loop（更新循环）

状态同步的服务器以一个固定的**网络 Tick 率**运行：

```
时间轴（以 20Hz tick rate = 50ms 为例）:

Tick 0 (0ms)     Tick 1 (50ms)    Tick 2 (100ms)   Tick 3 (150ms)
    │                 │                 │                 │
    ├─ 处理积压输入     ├─ 处理积压输入     ├─ 处理积压输入     ├─ ...
    ├─ 执行游戏逻辑     ├─ 执行游戏逻辑     ├─ 执行游戏逻辑
    ├─ 收集脏属性       ├─ 收集脏属性       ├─ 收集脏属性
    └─ 发送状态更新     └─ 发送状态更新     └─ 发送状态更新
```

**一个 Tick 内部的伪代码**：

```cpp
// 服务器主循环
void ServerTick(float deltaTime) {
    // 阶段 1: 处理所有客户端发来的输入/命令
    for (auto& client : connectedClients) {
        while (client->HasPendingCommands()) {
            Command cmd = client->DequeueCommand();
            // 验证 + 执行
            if (ValidateCommand(cmd, client)) {
                ExecuteCommand(cmd, client);
            }
        }
    }

    // 阶段 2: 更新所有游戏系统
    physicsWorld.Step(deltaTime);      // 物理模拟
    aiManager.Update(deltaTime);       // AI 行为
    skillSystem.Update(deltaTime);     // 技能/冷却
    spawnerManager.Update(deltaTime);  // 生成/销毁

    // 阶段 3: 收集变更并发送状态更新
    for (auto& client : connectedClients) {
        UpdatePacket packet;
        ReplicationSystem.CollectDirtyProperties(
            client,      // 以该客户端视角
            packet,      // 输出到此包
            client->aoi  // 只看 AOI 范围内的实体
        );
        client->Send(packet);
    }
}
```

#### ② Snapshot（状态快照）

"快照"这个词在状态同步中有两个不同的使用场景：

**a) 增量快照 (Incremental Snapshot)**：每 Tick 只发送**变化了的属性**。这是最常用的模式。

```
Tick N 发送:    { Entity3.Position = (10,0,5), Entity7.Health = 80 }
Tick N+1 发送:  { Entity3.Position = (10.2,0,5.1), Entity12 rotation = (0,90,0) }
Tick N+2 发送:  { Entity3.Position = (10.4,0,5.2) }
                 ↑ Entity7.Health 没变 → 不发; Entity12 没变 → 不发
```

**b) 全量快照 (Full Snapshot)**：偶尔发送一个实体的**全部属性**。用于：
- 新客户端加入时的初始状态
- 增量丢包过多后的"关键帧"修复
- 断线重连时的状态恢复

```cpp
// 全量快照示例
struct FullSnapshot {
    uint32_t tickNumber;                  // 快照对应的 Tick 号
    std::vector<EntityState> entities;    // 所有实体的完整状态

    struct EntityState {
        NetworkId id;
        Vector3 position;
        Quaternion rotation;
        Vector3 velocity;
        float health;
        uint32_t animState;
        // ... 所有属性
    };
};
```

快照的典型用法：服务器每 N 个 Tick 生成一次全量快照缓存。客户端用最新的全量快照建立基线，然后随后的增量更新在此基础上叠加。

#### ③ Delta Compression（增量压缩）

增量压缩是状态同步节省带宽的核心技术：

> 不发送"现在的值是多少"，而是发送"值从上一个确认点变化了多少"。

```
基本属性复制:  每次发送完整值
  Tick N:   Position = Vector3(100.5, 0, 50.2)    → 12 bytes (3 × float)
  Tick N+1: Position = Vector3(100.6, 0, 50.3)    → 12 bytes

增量压缩:      发送相对于"基线"的差异
  基线:    Position = Vector3(100.5, 0, 50.2)
  Tick N+1: Delta = Vector3(+0.1, 0, +0.1)        → 可压缩到 2-4 bytes（用半精度或整数编码）
```

增量压缩要生效，需要解决两个问题：

**a) 基线管理**：服务器需要知道"客户端当前认为的值是什么"。这通过确认（Acknowledge）机制实现——客户端收到状态更新后告诉服务器"我收到了 Tick N"，服务器就知道 Tick N 的状态已确认，可以作为后续增量更新的基线。

**b) 漂移修正**：如果客户端丢包了，它收到的增量是基于一个"服务器以为客户端有但实际上没有"的基线。积累一定量后需要**回退到全量快照**重建基线。

```
场景:
  服务器: Tick 100 基线 → Tick 101 增量(+0.1) → Tick 102 增量(+0.1)
  客户端: 收到 Tick 100 ✓，Tick 101 ✗（丢包），Tick 102 ✓（增量 +0.1）

  结果: 客户端位置 = 基线 + 0.1 = 100.6
        服务器位置 = 基线 + 0.1 + 0.1 = 100.7  ← 漂移了 0.1！

  修复: 服务器检测到连续 N 个包未被确认 → 发送全量快照重建基线
```

**量化 (Quantization)** 是增量压缩的好搭档。不是发送 float（4 bytes），而是将值映射到整数范围：

```
float position_x: 范围 [-1000, 1000]，精度要求 1cm
→ 映射到整数范围 [0, 200000]（2000m / 0.01m = 200000 个离散值）
→ 用 uint18 编码（实际上可以用变长整数/VarInt 实现）
→ 传输从 4 bytes 降到 ~2-3 bytes
```

Quake 3、Source Engine、Overwatch 都大量使用增量压缩 + 量化。Source Engine 的网络层使用了非常激进的压缩策略——delta 编码 + Huffman 编码 + 位级打包。

### 1.9 状态同步的适用场景

#### FPS（第一人称射击）— 状态同步的天然主场

- **CS:GO / CS2**：服务器 Tick 64-128Hz，客户端预测 + 服务端回退(Lag Compensation)。带宽下行 ~20-50 KB/s per player。
- **Valorant**：128 tick 服务器，激进的延迟补偿。Riot 专门写了[技术博客](https://technology.riotgames.com/news/peeking-valorants-netcode)。
- **Call of Duty / Battlefield**：使用 Dedicated Server (DS) 架构，每个比赛由一台专用服务器承载。

FPS 为什么选状态同步：
- 精确命中判定必须在服务器上做（反外挂）
- 客户端只需渲染附近 16-32 个玩家，不需要模拟整个地图
- 高延迟客户端可以用预测来掩护（见第 14、15、17 节）

#### TPS（第三人称射击）— 与 FPS 共享同一架构

- **Fortnite**：使用 Unreal Engine 的 Replication 系统（带 Iris 升级），100 人大逃杀场景
- **Gears of War**：UE 经典的状态同步 + Dedicated Server

TPS 的特殊挑战：第三人称视角可见范围更大（能看见墙角后面？能看见身后？），AOI 管理更复杂。

#### MMO（大型多人在线）— 分区分服的状态同步

- **World of Warcraft**：经典的分区 (Shard/Realm) + 动态分线 (Phasing) 架构。每个 Zone 一个 Game Server，Zone 间切换时做状态迁移。同屏 100+ 玩家时使用激进的优先级和 LOD 策略。
- **Final Fantasy XIV**：类似的分区架构，副本使用独立 Instance 服务器。

MMO 的带宽压力来自同屏人数。100 个玩家在暴风城拍卖行门口 → 如果每个玩家 20 properties × 100 players = 2000 个属性需要同步。优化手段：AOI（只同步附近玩家）、重要性排序（重要玩家高频，路人低频）、属性LOD（远处玩家只同步位置，不同步手指动画状态）。

#### 休闲竞技（Overwatch、Apex Legends 等）

- **守望先锋**：混合架构——主体使用状态同步（服务器权威的射击/技能），但加入了"预测回滚"（类似帧同步的回滚概念）用于处理高延迟场景。这也是本计划第四阶段"状态帧同步"的来源。
- **Apex Legends**：Source Engine 的继承，状态同步 + 服务器权威物理。

---

## 2. 代码示例

### 2.1 Unity C# — NGO 权威服务器示例

下面的例子使用 Unity Netcode for GameObjects (NGO) 实现一个简化版的权威服务器 FPS 场景。包含：NetworkVariable（属性复制）、ServerRPC（输入上传）、ClientRPC（特效广播）。

**场景设置**：
- 一个 `Player` prefab，挂载 `NetworkObject` + 下面的脚本
- 一个 `Bullet` prefab，作为 `NetworkObject` 动态 Spawn/Despawn
- 使用 Unity NGO 的默认传输（Unity Transport）

```csharp
// ============================================================
// PlayerController.cs — 挂载在玩家 Prefab 上
// ============================================================
using UnityEngine;
using Unity.Netcode;

public class PlayerController : NetworkBehaviour
{
    // === NetworkVariable（属性复制：服务器 → 客户端） ===

    // NetworkVariable 的值由服务器写入，自动同步到所有客户端
    // 客户端上的修改会被忽略（除非有写入权限设置）
    public NetworkVariable<Vector3> NetworkPosition = new NetworkVariable<Vector3>(
        Vector3.zero,
        NetworkVariableReadPermission.Everyone,  // 所有人都能读
        NetworkVariableWritePermission.Server    // 只有服务器能写
    );

    public NetworkVariable<float> NetworkHealth = new NetworkVariable<float>(
        100f,
        NetworkVariableReadPermission.Everyone,
        NetworkVariableWritePermission.Server
    );

    public NetworkVariable<int> NetworkScore = new NetworkVariable<int>(
        0,
        NetworkVariableReadPermission.Everyone,
        NetworkVariableWritePermission.Server
    );

    // === 本地状态（客户端私有，不同步） ===
    private float moveSpeed = 5f;
    private float lastFireTime = 0f;
    private float fireCooldown = 0.5f;

    // === 初始化 ===
    public override void OnNetworkSpawn()
    {
        // 注册属性变化回调 — 当服务器更新 NetworkPosition 时触发
        NetworkPosition.OnValueChanged += OnPositionChanged;
        NetworkHealth.OnValueChanged += OnHealthChanged;
        NetworkScore.OnValueChanged += OnScoreChanged;

        // 如果这是本地玩家，锁定鼠标和设置相机
        if (IsOwner)
        {
            Cursor.lockState = CursorLockMode.Locked;
            Camera.main.transform.SetParent(transform);
            Camera.main.transform.localPosition = new Vector3(0, 1.7f, 0); // 眼睛高度
        }
    }

    public override void OnNetworkDespawn()
    {
        NetworkPosition.OnValueChanged -= OnPositionChanged;
        NetworkHealth.OnValueChanged -= OnHealthChanged;
        NetworkScore.OnValueChanged -= OnScoreChanged;
    }

    // === 客户端回调：当服务器推送了新状态 ===
    private void OnPositionChanged(Vector3 oldPos, Vector3 newPos)
    {
        // 直接应用服务器告知的位置
        // （第 14 节会改进为"插值平滑"，避免瞬移感）
        transform.position = newPos;
    }

    private void OnHealthChanged(float oldHp, float newHp)
    {
        Debug.Log($"Health changed: {oldHp} → {newHp}");
        // 更新 UI / 播放受伤动画 / 检测死亡
        if (newHp <= 0 && IsOwner)
        {
            Debug.Log("You died!");
        }
    }

    private void OnScoreChanged(int oldScore, int newScore)
    {
        Debug.Log($"Score: {newScore}");
        // 更新 HUD 上的击杀数
    }

    // === 客户端更新循环 ===
    void Update()
    {
        // 只有本地玩家（Owner）才处理输入
        if (!IsOwner) return;

        // 采集移动输入
        Vector3 input = new Vector3(
            Input.GetAxis("Horizontal"), 0, Input.GetAxis("Vertical")
        );

        // 发送移动 ServerRPC（输入上传到服务器）
        if (input.magnitude > 0.01f)
        {
            Vector3 moveDir = transform.TransformDirection(input.normalized);
            SendMoveInputServerRpc(moveDir, Time.deltaTime);
        }

        // 采集射击输入
        if (Input.GetButtonDown("Fire1"))
        {
            // 简单冷却检查（本地检查防止滥发，服务器再做一次）
            if (Time.time - lastFireTime >= fireCooldown)
            {
                lastFireTime = Time.time;

                // 从屏幕中心做射线，确定射击方向
                Ray ray = Camera.main.ScreenPointToRay(new Vector3(Screen.width / 2, Screen.height / 2, 0));
                SendFireServerRpc(ray.origin, ray.direction);
            }
        }
    }

    // ============================================================
    // ServerRPC（客户端 → 服务器）：输入上传
    // ============================================================

    // 移动输入：客户端每帧调用，告诉服务器"我想往这个方向移动"
    [ServerRpc]
    void SendMoveInputServerRpc(Vector3 direction, float deltaTime)
    {
        // ⚠️ 关键：服务器必须验证！
        // 不要直接使用客户端发来的 deltaTime（可能被篡改）
        // 使用服务器的 deltaTime
        float serverDeltaTime = NetworkManager.Singleton.LocalTime.TimeAsFloat;

        // 计算新位置（服务器上的权威位置计算）
        Vector3 newPosition = transform.position + direction * moveSpeed * serverDeltaTime;

        // 服务器端的简单碰撞检测（防止客户端的穿墙外挂）
        if (IsValidPosition(newPosition))
        {
            transform.position = newPosition;
            // 更新 NetworkVariable → 自动同步到所有客户端
            NetworkPosition.Value = newPosition;
        }
        // 如果位置非法（比如客户端说穿墙了），忽略这次移动
        // 客户端会在收到同步的状态后被修正
    }

    // 射击输入：客户端调用，告诉服务器"我开枪了"
    [ServerRpc]
    void SendFireServerRpc(Vector3 origin, Vector3 direction)
    {
        // ⚠️ 服务器端验证
        // 1. 检查冷却（防止客户端修改冷却时间）
        if (Time.timeAsDouble - lastFireTime < fireCooldown) return;
        lastFireTime = Time.timeAsDouble;

        // 2. 验证射击方向是否合理（防止自瞄，简化版只做射线检查）
        //    真正生产环境会检查：方向是否超出 FOV、是否跳变等

        // 3. 服务器执行射线检测（权威命中判定）
        RaycastHit hit;
        if (Physics.Raycast(origin, direction, out hit, 100f))
        {
            // 检查击中的是不是其他玩家
            var targetPlayer = hit.collider.GetComponent<PlayerController>();
            if (targetPlayer != null && targetPlayer != this)
            {
                // 服务器计算伤害并直接修改目标 NetworkVariable
                float damage = 25f;
                float newHealth = Mathf.Max(0, targetPlayer.NetworkHealth.Value - damage);
                targetPlayer.NetworkHealth.Value = newHealth;

                // 击杀判定
                if (newHealth <= 0)
                {
                    NetworkScore.Value++; // 击杀者加分
                }

                // 通知所有客户端播放"命中"特效（ClientRPC）
                PlayHitEffectClientRpc(hit.point, hit.normal);
            }
            else
            {
                // 打到了墙壁/地面 → 播放弹孔特效
                PlayHitEffectClientRpc(hit.point, hit.normal);
            }
        }

        // 生成子弹的视觉表现（声音/枪口火焰等）
        // 这是纯表现，用 ClientRPC 告诉所有客户端
        PlayMuzzleFlashClientRpc();
    }

    // ============================================================
    // ClientRPC（服务器 → 客户端）：事件/特效广播
    // ============================================================

    [ClientRpc]
    void PlayHitEffectClientRpc(Vector3 hitPoint, Vector3 hitNormal)
    {
        // 在每个客户端上播放命中特效（火花、弹孔等）
        // 注意：这个函数在 ALL 客户端上执行，不只是开枪者
        GameObject impact = Instantiate(hitEffectPrefab, hitPoint,
            Quaternion.LookRotation(hitNormal));
        Destroy(impact, 2f); // 2 秒后销毁特效
    }

    [ClientRpc]
    void PlayMuzzleFlashClientRpc()
    {
        // 播放枪口火焰 + 枪声
        // 每个客户端都知道"哪个玩家开了枪"
        muzzleFlashEffect.Play();
        audioSource.PlayOneShot(fireSound);
    }

    // === 辅助方法 ===
    [SerializeField] private GameObject hitEffectPrefab;
    [SerializeField] private ParticleSystem muzzleFlashEffect;
    [SerializeField] private AudioSource audioSource;
    [SerializeField] private AudioClip fireSound;

    // 简单的服务器端位置验证（第 21 节会详细讨论 NavMesh/碰撞验证）
    bool IsValidPosition(Vector3 pos)
    {
        // 简化版：检查是否在地图范围内
        return pos.x > -50 && pos.x < 50 && pos.z > -50 && pos.z < 50;
    }
}
```

**关键设计点注解**：

1. `NetworkVariable` 的 `WritePermission.Server` 保证了只有服务器能修改值。客户端即使直接修改 `NetworkPosition.Value`，这个修改也不会被发送到服务器或其他客户端。
2. `ServerRpc` 的函数体运行在服务器上。客户端调用它 = 向服务器发送一条消息。参数由客户端提供，服务器的函数体**必须验证参数**。
3. `ClientRpc` 由服务器调用，在所有（连接的）客户端上执行。用于传播不需要持久存储的"事件"——特效、音效、UI 提示等。
4. 射线检测 (`Physics.Raycast`) 在服务器上执行，使得命中判定是权威的。客户端本地可能也有射线（用于视觉反馈），但只有服务器结果决定是否造成伤害。

### 2.2 C++ — 自定义状态同步消息循环

下面的代码展示一个**无外部引擎、无网络库**的 C++ 状态同步骨架。它不依赖 Unity/Unreal/任何框架，只使用标准库和 POSIX sockets，帮助你理解状态同步引擎的底层运作。

代码结构：`NetworkServer` + `NetworkClient` + `ReplicationSystem`（收集脏属性、序列化、发送）。

```cpp
// ============================================================
// state_sync_core.h — 核心类型定义
// ============================================================
#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <functional>
#include <cstring>
#include <chrono>

// --- 基础类型 ---
using NetworkId = uint32_t;
using TickNumber = uint64_t;
using ClientId = uint8_t;

constexpr NetworkId INVALID_NETWORK_ID = 0;
constexpr float TICK_DURATION = 1.0f / 20.0f;  // 20Hz = 50ms per tick

// --- 3D 向量 ---
struct Vector3 {
    float x = 0, y = 0, z = 0;
    Vector3 operator+(const Vector3& o) const { return {x+o.x, y+o.y, z+o.z}; }
    Vector3 operator-(const Vector3& o) const { return {x-o.x, y-o.y, z-o.z}; }
    Vector3 operator*(float s) const { return {x*s, y*s, z*s}; }
    float length() const { return std::sqrt(x*x + y*y + z*z); }
};

// --- 网络属性类型枚举 ---
enum class PropertyType : uint8_t {
    POSITION = 0,    // Vector3
    ROTATION = 1,    // Quaternion（简化为 Vector3 euler）
    HEALTH = 2,      // float
    SCORE = 3,       // int32_t
    WEAPON_ID = 4,   // uint8_t
    IS_DEAD = 5,     // bool
};

// --- 属性值（带类型标记的 union） ---
struct PropertyValue {
    PropertyType type;
    union {
        Vector3 vec3_val;
        float   float_val;
        int32_t int32_val;
        uint8_t uint8_val;
        bool    bool_val;
    };

    // 构造函数
    static PropertyValue FromVector3(Vector3 v)  { PropertyValue pv; pv.type = PropertyType::POSITION; pv.vec3_val = v; return pv; }
    static PropertyValue FromFloat(float f)       { PropertyValue pv; pv.type = PropertyType::HEALTH; pv.float_val = f; return pv; }
    static PropertyValue FromInt32(int32_t i)     { PropertyValue pv; pv.type = PropertyType::SCORE; pv.int32_val = i; return pv; }
    static PropertyValue FromUInt8(uint8_t u)     { PropertyValue pv; pv.type = PropertyType::WEAPON_ID; pv.uint8_val = u; return pv; }
    static PropertyValue FromBool(bool b)         { PropertyValue pv; pv.type = PropertyType::IS_DEAD; pv.bool_val = b; return pv; }

    // 简易序列化大小
    size_t serializedSize() const {
        switch (type) {
            case PropertyType::POSITION: return sizeof(float) * 3;
            case PropertyType::ROTATION: return sizeof(float) * 3;
            case PropertyType::HEALTH:   return sizeof(float);
            case PropertyType::SCORE:    return sizeof(int32_t);
            case PropertyType::WEAPON_ID:return sizeof(uint8_t);
            case PropertyType::IS_DEAD:  return sizeof(bool);
        }
        return 0;
    }
};

// --- 网络实体基类 ---
struct NetworkEntity {
    NetworkId networkId = INVALID_NETWORK_ID;
    ClientId ownerClientId = 0;
    bool isDirty = false;  // 本 Tick 是否有属性变化

    // 属性存储（属性类型 → 当前值）
    std::unordered_map<PropertyType, PropertyValue> properties;

    // 脏属性跟踪（本 Tick 哪些属性变了）
    std::vector<PropertyType> dirtyProperties;

    void setProperty(PropertyValue val) {
        auto& old = properties[val.type];
        // 简单比较（真实系统会做更精确的比较）
        if (memcmp(&old, &val, sizeof(PropertyValue)) != 0) {
            old = val;
            dirtyProperties.push_back(val.type);
            isDirty = true;
        }
    }

    void clearDirty() {
        dirtyProperties.clear();
        isDirty = false;
    }
};

// --- 命令（ServerRPC 的底层表示） ---
enum class CommandType : uint8_t {
    MOVE = 0,
    FIRE = 1,
    USE_ITEM = 2,
};

struct Command {
    ClientId clientId;
    CommandType type;
    TickNumber tickReceived;
    // 命令参数（不同命令携带不同参数）
    union {
        struct { Vector3 direction; float deltaTime; } move;
        struct { Vector3 origin; Vector3 direction; } fire;
        uint32_t itemId;
    };
};

// --- 状态更新包（服务器 → 客户端） ---
// 包含一个 Tick 内所有实体的属性变更
struct StateUpdatePacket {
    TickNumber tickNumber;
    std::vector<std::pair<NetworkId, PropertyValue>> updates; // (entityId, newValue)
    std::vector<NetworkId> spawnedEntities;   // 新实体列表
    std::vector<NetworkId> despawnedEntities; // 销毁实体列表
};

// --- 全量快照 ---
struct FullSnapshot {
    TickNumber tickNumber;
    std::vector<NetworkEntity> entities; // 所有实体的完整状态
};
```

```cpp
// ============================================================
// state_sync_core.cpp — 服务器主循环实现
// ============================================================
#include "state_sync_core.h"
#include <iostream>
#include <queue>
#include <algorithm>

// ======================================================
// ReplicationSystem：负责收集脏属性、生成更新包
// ======================================================
class ReplicationSystem {
public:
    // 注册一个需要复制的实体
    void registerEntity(NetworkEntity* entity) {
        entities_[entity->networkId] = entity;
    }

    void unregisterEntity(NetworkId id) {
        entities_.erase(id);
    }

    // 为本 Tick 收集所有实体的脏属性，生成更新包
    // `clientId` 用于 AOI 过滤（简化版省略）
    StateUpdatePacket collectDirtyProperties(TickNumber tick, ClientId /*clientId*/) {
        StateUpdatePacket packet;
        packet.tickNumber = tick;

        for (auto& [id, entity] : entities_) {
            if (!entity->isDirty) continue;

            // 将每个脏属性加入更新包
            for (auto propType : entity->dirtyProperties) {
                packet.updates.push_back({id, entity->properties[propType]});
            }

            entity->clearDirty(); // 清除脏标记
        }

        return packet;
    }

private:
    std::unordered_map<NetworkId, NetworkEntity*> entities_;
};

// ======================================================
// NetworkServer：权威服务器主类
// ======================================================
class NetworkServer {
public:
    NetworkServer() : nextNetworkId_(1), tickNumber_(0) {}

    // ===== 初始化 =====
    void initialize() {
        std::cout << "[Server] Initializing authoritative server at 20Hz" << std::endl;
        // 真实系统：绑定 UDP socket、启动监听
    }

    // ===== 主循环 =====
    void run() {
        using clock = std::chrono::steady_clock;
        auto nextTick = clock::now();

        while (running_) {
            // 等待直到下一次 Tick 时间
            std::this_thread::sleep_until(nextTick);
            nextTick += std::chrono::duration<float>(TICK_DURATION);

            tick();
        }
    }

    void tick() {
        tickNumber_++;

        // === 阶段 1: 处理积压的客户端命令 ===
        processPendingCommands();

        // === 阶段 2: 执行游戏逻辑 ===
        executeGameLogic();

        // === 阶段 3: 收集脏属性、生成快照、发送更新 ===
        for (auto& client : clients_) {
            StateUpdatePacket packet = replication_.collectDirtyProperties(
                tickNumber_, client.clientId
            );

            // 同时也发送 Spawn/Despawn 通知
            // （简化版：假定由外部系统填充）

            sendUpdateToClient(client.clientId, packet);
        }

        // === 阶段 4: 周期性全量快照（每 100 Tick 一次，即每 5 秒） ===
        if (tickNumber_ % 100 == 0) {
            generateFullSnapshot();
        }
    }

    // ===== 客户端管理 =====
    struct ConnectedClient {
        ClientId clientId;
        std::queue<Command> pendingCommands;
        NetworkEntity* playerEntity = nullptr;
    };

    void onClientConnect(ClientId clientId) {
        ConnectedClient client;
        client.clientId = clientId;
        clients_.push_back(client);
        std::cout << "[Server] Client " << (int)clientId << " connected" << std::endl;

        // 为新客户端创建玩家实体
        NetworkEntity* playerEntity = createEntity();
        playerEntity->ownerClientId = clientId;
        playerEntity->setProperty(PropertyValue::FromVector3({0, 0, 0}));
        playerEntity->setProperty(PropertyValue::FromFloat(100.0f));       // Health
        playerEntity->setProperty(PropertyValue::FromInt32(0));            // Score
        playerEntity->setProperty(PropertyValue::FromBool(false));         // IsDead

        clients_.back().playerEntity = playerEntity;

        // 发送全量快照给新客户端（下一 Tick 的更新循环中处理）
    }

    // ===== 接收客户端命令（由网络层调用） =====
    void receiveCommand(ClientId fromClient, Command cmd) {
        // 标记命令的接收时间
        cmd.tickReceived = tickNumber_;

        // 放入客户端的命令队列
        for (auto& client : clients_) {
            if (client.clientId == fromClient) {
                client.pendingCommands.push(cmd);
                break;
            }
        }
    }

private:
    // ---- 阶段 1: 处理命令 ----
    void processPendingCommands() {
        for (auto& client : clients_) {
            while (!client.pendingCommands.empty()) {
                Command cmd = client.pendingCommands.front();
                client.pendingCommands.pop();

                // ⚠️ 验证命令合法性
                if (!validateCommand(cmd, client)) {
                    std::cout << "[Server] Rejected invalid command from client "
                              << (int)client.clientId << std::endl;
                    continue; // 静默拒绝
                }

                // 执行命令
                executeCommand(cmd, client);
            }
        }
    }

    bool validateCommand(const Command& cmd, const ConnectedClient& client) {
        NetworkEntity* entity = client.playerEntity;
        if (!entity) return false;

        // 验证示例：移动命令的方向向量不应超过长度 1（可能被篡改）
        if (cmd.type == CommandType::MOVE) {
            if (cmd.move.direction.length() > 1.01f) return false; // 容差 0.01
        }

        // 验证示例：射击频率检查（防止连发外挂）
        if (cmd.type == CommandType::FIRE) {
            // 简化：检查距离上次射击是否超过冷却
            auto now = std::chrono::steady_clock::now();
            // （真实系统需要追踪每个客户端的最后射击时间）
        }

        return true;
    }

    void executeCommand(const Command& cmd, ConnectedClient& client) {
        NetworkEntity* entity = client.playerEntity;

        switch (cmd.type) {
            case CommandType::MOVE: {
                const float speed = 5.0f;
                // 使用服务器的 TICK_DURATION 而非客户端传来的 deltaTime
                Vector3 movement = cmd.move.direction * speed * TICK_DURATION;
                Vector3 oldPos = entity->properties[PropertyType::POSITION].vec3_val;
                Vector3 newPos = oldPos + movement;

                // 服务器端碰撞/边界检查
                if (isValidPosition(newPos)) {
                    entity->setProperty(PropertyValue::FromVector3(newPos));
                }
                // 如果位置非法（穿墙），忽略移动（客户端会被状态同步修正）
                break;
            }

            case CommandType::FIRE: {
                // 服务器做射线检测判定命中
                float maxRange = 100.0f;
                Vector3 origin = cmd.fire.origin;
                Vector3 direction = cmd.fire.direction;

                // 简化版命中检测：检查是否与任何其他实体相交
                NetworkEntity* hitTarget = performRaycast(origin, direction, maxRange, entity);
                if (hitTarget) {
                    float currentHp = hitTarget->properties[PropertyType::HEALTH].float_val;
                    float newHp = std::max(0.0f, currentHp - 25.0f);
                    hitTarget->setProperty(PropertyValue::FromFloat(newHp));

                    if (newHp <= 0) {
                        hitTarget->setProperty(PropertyValue::FromBool(true)); // IsDead = true

                        // 击杀者加分
                        int score = entity->properties[PropertyType::SCORE].int32_val;
                        entity->setProperty(PropertyValue::FromInt32(score + 1));

                        std::cout << "[Server] Client " << (int)client.clientId
                                  << " killed entity " << hitTarget->networkId << std::endl;
                    }
                }
                break;
            }

            default:
                break;
        }
    }

    // ---- 阶段 2: 游戏逻辑 ----
    void executeGameLogic() {
        // 服务器上运行的其他游戏逻辑:
        // - AI 行为树更新
        // - 技能冷却推进
        // - 延迟生效的技能（投掷物飞行、激光延时）
        // - 定时事件（刷怪、毒圈收缩）
        // - 物理模拟（如果使用服务器端物理引擎）

        // 简化示例：所有 alive 实体的简单 AI 行为
        for (auto& [id, entity] : entities_) {
            if (entity->properties[PropertyType::IS_DEAD].bool_val) continue;
            // AI 逻辑...
        }
    }

    // ---- 阶段 3 & 4: 状态同步发送 ----
    void sendUpdateToClient(ClientId clientId, const StateUpdatePacket& packet) {
        // 序列化 packet 为字节流，通过 UDP socket 发送
        // 真实实现会在下一节深入
        std::cout << "[Server] Sending " << packet.updates.size()
                  << " property updates to client " << (int)clientId
                  << " (tick " << packet.tickNumber << ")" << std::endl;
    }

    void generateFullSnapshot() {
        // 收集所有实体的完整状态
        FullSnapshot snapshot;
        snapshot.tickNumber = tickNumber_;
        for (auto& [id, entity] : entities_) {
            snapshot.entities.push_back(*entity);
        }

        // 缓存快照用于断线重连
        cachedSnapshots_.push_back(snapshot);
        if (cachedSnapshots_.size() > 10) {
            cachedSnapshots_.erase(cachedSnapshots_.begin()); // 只保留最近 10 个
        }
    }

    // ---- 实体管理 ----
    NetworkEntity* createEntity() {
        NetworkEntity* entity = new NetworkEntity();
        entity->networkId = nextNetworkId_++;
        entities_[entity->networkId] = entity;
        replication_.registerEntity(entity);
        std::cout << "[Server] Entity spawned: id=" << entity->networkId << std::endl;
        return entity;
    }

    void destroyEntity(NetworkId id) {
        auto it = entities_.find(id);
        if (it != entities_.end()) {
            replication_.unregisterEntity(id);
            delete it->second;
            entities_.erase(it);
            std::cout << "[Server] Entity despawned: id=" << id << std::endl;
        }
    }

    // ---- 辅助 ----
    bool isValidPosition(const Vector3& pos) {
        // 简化：地图范围检查
        return pos.x > -100 && pos.x < 100 && pos.z > -100 && pos.z < 100;
    }

    NetworkEntity* performRaycast(Vector3 origin, Vector3 dir, float maxRange,
                                   NetworkEntity* exclude) {
        // 简化版碰撞检测：遍历所有实体，检查射线是否穿过它们
        // 真实系统会使用物理引擎的射线检测
        for (auto& [id, entity] : entities_) {
            if (entity == exclude) continue;
            if (entity->properties[PropertyType::IS_DEAD].bool_val) continue;

            Vector3 targetPos = entity->properties[PropertyType::POSITION].vec3_val;
            Vector3 toTarget = targetPos - origin;
            float distance = toTarget.length();

            if (distance > maxRange) continue;

            // 检查是否在射线方向上（点积）
            // 简化：距离 < 0.5 视为命中
            Vector3 dirNorm = dir;
            float projection = (toTarget.x * dirNorm.x + toTarget.y * dirNorm.y + toTarget.z * dirNorm.z);
            if (projection > 0 && projection < maxRange) {
                Vector3 closest = origin + dirNorm * projection;
                if ((closest - targetPos).length() < 0.5f) {
                    return entity;
                }
            }
        }
        return nullptr;
    }

    // ---- 成员变量 ----
    bool running_ = true;
    NetworkId nextNetworkId_;
    TickNumber tickNumber_;
    std::vector<ConnectedClient> clients_;
    ReplicationSystem replication_;
    std::unordered_map<NetworkId, NetworkEntity*> entities_;
    std::vector<FullSnapshot> cachedSnapshots_;
};
```

```cpp
// ============================================================
// main.cpp — 启动服务器（演示入口）
// ============================================================
#include "state_sync_core.cpp"

int main() {
    NetworkServer server;
    server.initialize();

    // 模拟：两个客户端连接
    server.onClientConnect(1);
    server.onClientConnect(2);

    // 模拟：客户端 1 发送移动命令
    Command moveCmd;
    moveCmd.clientId = 1;
    moveCmd.type = CommandType::MOVE;
    moveCmd.move.direction = {0, 0, 1}; // 向前
    moveCmd.move.deltaTime = 0.05f;     // 客户端发送的值（服务器会用自己的值替代）
    server.receiveCommand(1, moveCmd);

    // 模拟：客户端 1 发送射击命令
    Command fireCmd;
    fireCmd.clientId = 1;
    fireCmd.type = CommandType::FIRE;
    fireCmd.fire.origin = {0, 0, 0};
    fireCmd.fire.direction = {0, 0, 1};
    server.receiveCommand(1, fireCmd);

    // 运行 5 个 Tick
    for (int i = 0; i < 5; i++) {
        std::cout << "\n=== Tick " << i << " ===" << std::endl;
        server.tick();
    }

    std::cout << "\nServer simulation complete." << std::endl;
    return 0;
}
```

**代码要点注解**：

1. **`processPendingCommands` → `validateCommand` → `executeCommand`** 是服务器处理客户端输入的黄金流程。任何跳过验证的路径都是外挂的入口。
2. **`TICK_DURATION`** 替代了客户端传来的 `deltaTime`。如果信任客户端的 deltaTime（比如客户端说 "0.0001秒"，然后闪电般移动），服务器就会被欺骗。
3. **`ReplicationSystem::collectDirtyProperties`** 将"哪些属性需要同步"的决策封装在一个独立的系统中。这为后续的 AOI、优先级排序、增量压缩提供干净的扩展点。
4. **属性存储使用 `PropertyType → PropertyValue` 的 map**。真实系统会使用更高效的存储（连续数组 + 位掩码标记脏），但 map 清晰地展示了数据关系。
5. **`cachedSnapshots_`** 保留最近的快照，用于断线重连。这在第 28 节会深入展开。

### 2.3 Lua — 状态同步消息处理器

Lua 在游戏服务器端的应用非常广泛（Skynet、ET框架、SLG服务器等）。下面的代码展示一个基于 Lua 的状态同步消息处理层——它不依赖任何特定网络框架，只用纯 Lua 实现消息分发、属性复制和命令处理。

```lua
-- ============================================================
-- state_sync.lua — Lua 状态同步消息处理核心
-- ============================================================
-- 假设底层有一个 C 绑定网络层，通过回调驱动
-- 设计风格：事件驱动 + 消息分发

-- ======================================================
-- 1. 基础定义
-- ======================================================

local StateSync = {}

-- 属性类型枚举
StateSync.PropertyType = {
    POSITION    = 1,
    ROTATION    = 2,
    HEALTH      = 3,
    SCORE       = 4,
    WEAPON_ID   = 5,
    IS_DEAD     = 6,
    ANIM_STATE  = 7,
}

-- 命令类型枚举
StateSync.CommandType = {
    MOVE       = 1,
    FIRE       = 2,
    USE_SKILL  = 3,
    PICK_ITEM  = 4,
}

-- ======================================================
-- 2. 网络实体类
-- ======================================================

local NetworkEntity = {}
NetworkEntity.__index = NetworkEntity

function NetworkEntity:new(id, owner_id)
    local obj = {
        network_id = id,
        owner_id = owner_id or 0,

        -- 属性存储: property_type → value
        properties = {},

        -- 脏标记追踪（按 Tick 清理）
        _dirty = {},        -- { [property_type] = true }
        _has_changes = false,

        -- 命令队列（服务器端）
        _command_queue = {},
    }
    setmetatable(obj, self)
    return obj
end

-- 设置属性（服务器端调用，自动标记脏）
function NetworkEntity:set_property(prop_type, value)
    local old = self.properties[prop_type]
    -- 简单比较（Vector3 类需要重写 __eq）
    if old ~= value then
        self.properties[prop_type] = value
        self._dirty[prop_type] = true
        self._has_changes = true
    end
end

-- 获取属性
function NetworkEntity:get_property(prop_type)
    return self.properties[prop_type]
end

-- 清除脏标记（Tick 结束时调用）
function NetworkEntity:clear_dirty()
    self._dirty = {}
    self._has_changes = false
end

-- 获取所有脏属性类型
function NetworkEntity:get_dirty_properties()
    local props = {}
    for prop_type, _ in pairs(self._dirty) do
        table.insert(props, prop_type)
    end
    return props
end

-- 序列化为全量状态（用于新客户端 / 断线重连）
function NetworkEntity:serialize_full()
    return {
        network_id = self.network_id,
        owner_id = self.owner_id,
        properties = self.properties, -- 浅拷贝（真实系统需要深拷贝）
    }
end

-- ======================================================
-- 3. 服务器端核心
-- ======================================================

local ServerCore = {}
ServerCore.__index = ServerCore

function ServerCore:new()
    local srv = {
        tick_number = 0,
        tick_rate = 20,             -- Hz
        tick_duration = 1.0 / 20,   -- seconds

        entities = {},              -- network_id → NetworkEntity
        clients = {},               -- client_id → { entity, command_queue, ... }
        next_network_id = 1,

        -- 命令处理器注册表 (CommandType → handler function)
        command_handlers = {},

        -- 实体工厂注册表 (prefab_name → constructor function)
        entity_factories = {},

        -- 状态更新回调（由网络层注册）
        on_send_state_update = nil, -- function(client_id, packet)
        on_send_full_snapshot = nil,-- function(client_id, snapshot)
    }
    setmetatable(srv, self)

    -- 注册默认命令处理器
    srv:register_command_handler(StateSync.CommandType.MOVE, srv._handle_move)
    srv:register_command_handler(StateSync.CommandType.FIRE, srv._handle_fire)

    return srv
end

-- ===== 主 Tick =====
function ServerCore:tick()
    self.tick_number = self.tick_number + 1

    -- 阶段 1: 处理所有客户端的积压命令
    for client_id, client_data in pairs(self.clients) do
        self:_process_commands(client_id, client_data)
    end

    -- 阶段 2: 执行服务器端游戏逻辑
    self:_execute_game_logic()

    -- 阶段 3: 收集脏属性、发送状态更新
    for client_id, client_data in pairs(self.clients) do
        local packet = self:_collect_dirty_properties(client_id)
        if self.on_send_state_update and #packet.updates > 0 then
            self.on_send_state_update(client_id, packet)
        end
    end

    -- 阶段 4: 清理脏标记
    for _, entity in pairs(self.entities) do
        entity:clear_dirty()
    end

    -- 阶段 5: 周期性全量快照
    if self.tick_number % 100 == 0 then
        self:_generate_full_snapshot()
    end
end

-- ===== 客户端管理 =====
function ServerCore:on_client_connect(client_id)
    -- 创建客户端数据
    local player_entity = self:spawn_entity("Player", client_id)
    self.clients[client_id] = {
        entity = player_entity,
        command_queue = {},
    }

    -- 发送全量世界状态给新客户端
    local snapshot = self:_build_full_snapshot()
    if self.on_send_full_snapshot then
        self.on_send_full_snapshot(client_id, snapshot)
    end

    print(string.format("[Server] Client %d connected, entity=%d",
          client_id, player_entity.network_id))
end

function ServerCore:on_client_disconnect(client_id)
    local client_data = self.clients[client_id]
    if client_data and client_data.entity then
        self:despawn_entity(client_data.entity.network_id)
    end
    self.clients[client_id] = nil
    print(string.format("[Server] Client %d disconnected", client_id))
end

-- ===== 命令接收 =====
function ServerCore:receive_command(client_id, cmd_type, params)
    -- 放入命令队列
    local client_data = self.clients[client_id]
    if not client_data then return end

    table.insert(client_data.command_queue, {
        type = cmd_type,
        params = params,
        received_tick = self.tick_number,
    })
end

-- ===== 实体管理 =====
function ServerCore:spawn_entity(entity_type, owner_id, initial_props)
    local id = self.next_network_id
    self.next_network_id = id + 1

    local entity = NetworkEntity:new(id, owner_id)
    self.entities[id] = entity

    -- 应用初始属性
    if initial_props then
        for prop_type, value in pairs(initial_props) do
            entity:set_property(prop_type, value)
        end
    end

    print(string.format("[Server] Spawned entity %d (type=%s)", id, entity_type))
    return entity
end

function ServerCore:despawn_entity(network_id)
    local entity = self.entities[network_id]
    if not entity then return end

    self.entities[network_id] = nil
    -- 通知所有客户端销毁（在下次状态更新包中携带 despawn 信息）
    print(string.format("[Server] Despawned entity %d", network_id))
end

-- ===== 命令处理器注册 =====
function ServerCore:register_command_handler(cmd_type, handler)
    self.command_handlers[cmd_type] = handler
end

-- ======================================================
-- 内部方法
-- ======================================================

-- 处理所有积压命令
function ServerCore:_process_commands(client_id, client_data)
    local entity = client_data.entity

    for _, cmd in ipairs(client_data.command_queue) do
        local handler = self.command_handlers[cmd.type]
        if handler then
            -- ⚠️ 验证在前，执行在后
            if self:_validate_command(client_id, entity, cmd) then
                handler(self, client_id, entity, cmd.params)
            else
                print(string.format("[Server] Rejected cmd type=%d from client %d",
                      cmd.type, client_id))
            end
        end
    end

    -- 清空队列
    client_data.command_queue = {}
end

-- 命令验证
function ServerCore:_validate_command(client_id, entity, cmd)
    if not entity then return false end

    -- 死亡状态不能操作
    if entity:get_property(StateSync.PropertyType.IS_DEAD) then
        return false
    end

    -- 按命令类型做参数范围检查
    if cmd.type == StateSync.CommandType.MOVE then
        local dir_x = cmd.params.dx or 0
        local dir_z = cmd.params.dz or 0
        -- 方向向量长度 <= 1（防止外挂加速）
        if math.sqrt(dir_x * dir_x + dir_z * dir_z) > 1.01 then
            return false
        end

    elseif cmd.type == StateSync.CommandType.FIRE then
        -- 射击冷却检查
        local last_fire = entity._last_fire_time or 0
        if self.tick_number - last_fire < 10 then -- 10 ticks = 0.5s @20Hz
            return false
        end
    end

    return true
end

-- 执行服务器端游戏逻辑
function ServerCore:_execute_game_logic()
    -- 在这里运行：
    -- - AI 行为树
    -- - 技能系统
    -- - 定时事件（毒圈、刷怪）
    -- - Buff/Debuff 持续时间
    -- 每个系统通过 entity:set_property() 修改属性，自动标记脏

    -- 示例：AI 巡逻
    for _, entity in pairs(self.entities) do
        if entity.owner_id == 0 and not entity:get_property(StateSync.PropertyType.IS_DEAD) then
            -- AI entity — 简单巡逻逻辑
            -- (真实系统会调用完整的行为树)
        end
    end
end

-- 收集脏属性（AOI 简化版 — 发送所有实体的所有变更）
function ServerCore:_collect_dirty_properties(client_id)
    local packet = {
        tick_number = self.tick_number,
        updates = {},      -- { {network_id, prop_type, value}, ... }
        spawns = {},       -- 本 Tick 新 Spawn 的 entity（需在别处管理）
        despawns = {},     -- 本 Tick Despawn 的 entity
    }

    for network_id, entity in pairs(self.entities) do
        if entity._has_changes then
            for _, prop_type in ipairs(entity:get_dirty_properties()) do
                table.insert(packet.updates, {
                    network_id = network_id,
                    prop_type = prop_type,
                    value = entity:get_property(prop_type),
                })
            end
        end
    end

    return packet
end

-- 构建全量世界快照
function ServerCore:_build_full_snapshot()
    local snapshot = {
        tick_number = self.tick_number,
        entities = {},
    }
    for _, entity in pairs(self.entities) do
        table.insert(snapshot.entities, entity:serialize_full())
    end
    return snapshot
end

function ServerCore:_generate_full_snapshot()
    -- 缓存快照，限制数量
    local snapshot = self:_build_full_snapshot()
    table.insert(self._cached_snapshots or {}, snapshot)
    if #(self._cached_snapshots or {}) > 10 then
        table.remove(self._cached_snapshots, 1)
    end
end

-- ======================================================
-- 命令处理器实现
-- ======================================================

function ServerCore:_handle_move(client_id, entity, params)
    -- 服务器端移动计算
    local dx = params.dx or 0
    local dz = params.dz or 0
    local speed = 5.0
    local dt = self.tick_duration  -- ⚠️ 使用服务器的 tick_duration!

    local pos = entity:get_property(StateSync.PropertyType.POSITION) or {x=0,y=0,z=0}

    -- 计算新位置
    local new_x = pos.x + dx * speed * dt
    local new_z = pos.z + dz * speed * dt

    -- 服务器端边界检查
    if self:_is_valid_position(new_x, new_z) then
        entity:set_property(StateSync.PropertyType.POSITION, {
            x = new_x, y = pos.y, z = new_z
        })
    end
end

function ServerCore:_handle_fire(client_id, entity, params)
    -- 服务器端射击处理
    entity._last_fire_time = self.tick_number

    local origin_x = params.ox or 0
    local origin_y = params.oy or 0
    local origin_z = params.oz or 0
    local dir_x = params.dx or 0
    local dir_y = params.dy or 0
    local dir_z = params.dz or 1

    -- 服务器做射线检测（简化版 — 遍历所有实体检查命中）
    local hit_entity = self:_raycast_hit(origin_x, origin_y, origin_z,
                                           dir_x, dir_y, dir_z, 100, entity)

    if hit_entity then
        -- 扣血
        local cur_hp = hit_entity:get_property(StateSync.PropertyType.HEALTH) or 100
        local new_hp = math.max(0, cur_hp - 25)
        hit_entity:set_property(StateSync.PropertyType.HEALTH, new_hp)

        -- 击杀判定
        if new_hp <= 0 then
            hit_entity:set_property(StateSync.PropertyType.IS_DEAD, true)

            -- 击杀者加分
            local score = entity:get_property(StateSync.PropertyType.SCORE) or 0
            entity:set_property(StateSync.PropertyType.SCORE, score + 1)
        end
    end
end

-- ======================================================
-- 辅助方法
-- ======================================================

function ServerCore:_is_valid_position(x, z)
    -- 地图边界检查
    return x > -100 and x < 100 and z > -100 and z < 100
end

function ServerCore:_raycast_hit(ox, oy, oz, dx, dy, dz, max_range, exclude_entity)
    -- 简化射线检测：遍历所有实体
    for _, entity in pairs(self.entities) do
        if entity == exclude_entity then goto continue end
        if entity:get_property(StateSync.PropertyType.IS_DEAD) then goto continue end

        local pos = entity:get_property(StateSync.PropertyType.POSITION)
        if not pos then goto continue end

        -- 简化：距离 ≤ 0.5 视为命中（真实系统用物理引擎）
        local to_x = pos.x - ox
        local to_z = pos.z - oz
        local dist = math.sqrt(to_x * to_x + to_z * to_z)

        if dist <= max_range then
            -- 检查方向（前向点积）
            local dot_product = to_x * dx + to_z * dz
            if dot_product > 0 then
                -- 检查垂直距离
                local proj_x = ox + dx * dot_product / (dx*dx + dz*dz)
                local proj_z = oz + dz * dot_product / (dx*dx + dz*dz)
                local perp_dist = math.sqrt((pos.x - proj_x)^2 + (pos.z - proj_z)^2)
                if perp_dist < 0.5 then
                    return entity
                end
            end
        end

        ::continue::
    end
    return nil
end

-- ======================================================
-- 4. 客户端消息处理器
-- ======================================================

local ClientHandler = {}
ClientHandler.__index = ClientHandler

function ClientHandler:new()
    local cl = {
        entities = {},  -- network_id → local_entity_data
        pending_state_updates = {},
    }
    setmetatable(cl, self)
    return cl
end

-- 处理服务器发来的状态更新包
function ClientHandler:on_state_update(packet)
    for _, update in ipairs(packet.updates) do
        local net_id = update.network_id
        local prop_type = update.prop_type
        local value = update.value

        -- 查找本地实体
        local local_entity = self.entities[net_id]
        if not local_entity then
            -- 可能是还未收到 Spawn 消息？（乱序到达）
            -- 先缓存更新，等 Spawn 消息到达后再应用
            table.insert(self.pending_state_updates, update)
            goto continue
        end

        -- 应用服务器发来的状态
        self:_apply_property(local_entity, prop_type, value)

        ::continue::
    end
end

-- 处理全量快照（新客户端加入 / 断线重连）
function ClientHandler:on_full_snapshot(snapshot)
    -- 清除旧状态，建立新的世界视图
    self.entities = {}

    for _, entity_data in ipairs(snapshot.entities) do
        local local_entity = {
            network_id = entity_data.network_id,
            owner_id = entity_data.owner_id,
            properties = entity_data.properties,
            game_object = nil, -- 由渲染层绑定
        }
        self.entities[entity_data.network_id] = local_entity

        -- 通知渲染层创建/更新 GameObject
        self:_on_entity_created(local_entity)
    end

    -- 应用之前缓存的状态更新（如果它们在快照 tick 之后）
    self:_apply_pending_updates(snapshot.tick_number)
end

-- 应用单个属性到本地实体
function ClientHandler:_apply_property(local_entity, prop_type, value)
    local_entity.properties[prop_type] = value

    -- 回调给渲染层
    if prop_type == StateSync.PropertyType.POSITION then
        -- local_entity.game_object.transform.position = value
    elseif prop_type == StateSync.PropertyType.HEALTH then
        -- UI: 更新血条
        -- if local_entity.is_local_player then UpdateHealthBar(value) end
    end
end

function ClientHandler:_apply_pending_updates(snapshot_tick)
    local applied = {}
    for i, update in ipairs(self.pending_state_updates) do
        -- 只应用快照之后 Tick 的更新
        -- （简化版: 全部应用）
        local local_entity = self.entities[update.network_id]
        if local_entity then
            self:_apply_property(local_entity, update.prop_type, update.value)
            applied[i] = true
        end
    end

    -- 清理已应用的
    local remaining = {}
    for i, update in ipairs(self.pending_state_updates) do
        if not applied[i] then
            table.insert(remaining, update)
        end
    end
    self.pending_state_updates = remaining
end

function ClientHandler:_on_entity_created(local_entity)
    -- 通知渲染层创建对应的 GameObject/Sprite
    -- game_object = Instantiate(prefab)
    -- local_entity.game_object = game_object
    print(string.format("[Client] Entity %d created", local_entity.network_id))
end

-- ======================================================
-- 5. 注册导出
-- ======================================================

StateSync.ServerCore = ServerCore
StateSync.NetworkEntity = NetworkEntity
StateSync.ClientHandler = ClientHandler

return StateSync
```

```lua
-- ============================================================
-- example_usage.lua — 使用示例
-- ============================================================

local StateSync = require("state_sync")

-- 创建服务器
local server = StateSync.ServerCore:new()

-- 注册网络发送回调（由具体的网络框架实现）
server.on_send_state_update = function(client_id, packet)
    -- 序列化并发送
    -- network_layer:send_to_client(client_id, serialize(packet))
    print(string.format("→ Client %d: %d property updates (tick %d)",
          client_id, #packet.updates, packet.tick_number))
end

server.on_send_full_snapshot = function(client_id, snapshot)
    print(string.format("→ Client %d: full snapshot with %d entities (tick %d)",
          client_id, #snapshot.entities, snapshot.tick_number))
end

-- 模拟两个客户端连接
server:on_client_connect(1)
server:on_client_connect(2)

-- 模拟客户端 1 发送移动命令
server:receive_command(1, StateSync.CommandType.MOVE,
    { dx = 0, dz = 1 })  -- 向前移动

-- 模拟客户端 1 发送射击命令
server:receive_command(1, StateSync.CommandType.FIRE,
    { ox = 0, oy = 0, oz = 0, dx = 0, dy = 0, dz = 1 })

-- 恶意外挂尝试：发送超速移动方向
server:receive_command(1, StateSync.CommandType.MOVE,
    { dx = 100, dz = 100 })  -- 方向长度 = 141，远超 1.0，会被拒绝

-- 运行 10 个服务器 Tick
for i = 1, 10 do
    print(string.format("\n--- Server Tick %d ---", i))
    server:tick()
end
```

**Lua 版本设计要点**：

1. **`ServerCore` 的 Tick 循环**定义了清晰的阶段顺序：处理命令 → 执行逻辑 → 收集脏属性 → 发送 → 清理。这个顺序是状态同步服务器的基础契约。
2. **命令验证 `_validate_command`** 是 Lua 服务器的安全边界。注意方向向量检查（`> 1.01` 拒绝）、死亡状态检查、冷却检查。这些检查在**服务器端而非客户端**，是反外挂的第一道防线。
3. **`ClientHandler`** 用 `pending_state_updates` 处理消息乱序到达的情况——状态更新可能在 Spawn 消息之前到达（UDP 原生乱序），需要缓存并延迟应用。
4. **全量快照**提供了一种干净的状态重置方式——当客户端的世界状态与服务器偏差过大时，全量快照是最简单的修复手段。

---

## 3. 练习

### 练习 1: 基础 — 补全 ServerRPC 验证链（30min）

基于 2.1 节的 Unity NGO 示例，在 `PlayerController` 中添加一个 `SendUseItemServerRpc` 命令（使用道具），并实现完整的服务器端验证链。

**要求**：
1. 添加 `SendUseItemServerRpc(int itemId)` — 客户端按数字键 1/2/3 发送对应的道具 ID
2. 服务器端验证以下条件（缺一不可）：
   - 道具 ID 是否合法（1-3 范围内）
   - 玩家背包中是否确实拥有该道具（维护一个 `List<int> inventory` 在服务器端）
   - 道具是否处于冷却中（每个道具独立冷却，用 `Dictionary<int, float> itemCooldowns` 追踪）
   - 玩家是否存活（`NetworkHealth.Value > 0`）
3. 验证通过后：移除道具、应用效果（扣冷却）、通过 ClientRPC 播放使用特效
4. 验证失败时：静默拒绝，不通知客户端（防止外挂探测）

**提示**：
- 背包数据不应该用 `NetworkVariable` 暴露给客户端（防止全图外挂），只在服务器端维护
- 冷却检查用 `Time.timeAsDouble`（服务器时间），不用客户端传来的值

### 练习 2: 进阶 — 实现增量压缩模拟（45min）

用任意语言（建议 C++ 或 Python）实现一个简单的增量压缩 (Delta Compression) 模拟器。不需要网络传输，只需要在内存中模拟"服务器生成更新 → 客户端接收/丢包 → 漂移修复"的完整流程。

**要求**：
1. 定义 5 个实体，每个实体有 Position (Vector3) 和 Health (float) 两个属性
2. 服务器每 Tick 更新实体位置（匀速移动），有时更新血量（随机事件）
3. 实现三种模式对比：
   - **全量模式**：每 Tick 发送所有实体的所有属性
   - **脏属性模式**：每 Tick 只发送变化的属性
   - **增量压缩模式**：发送相对于基线的增量（delta），基线由客户端 Ack 确认
4. 模拟 10% 丢包率（随机丢弃一些 Tick 的更新）
5. 对比三种模式的累计传输字节数（模拟 100 个 Tick）
6. 增量模式下：当连续 3 个 Tick 未被 Ack 时，服务器回退到全量快照

**期望输出**：
```
Mode             | Total Bytes | Avg/Tick | Drift Errors
Full             | 120,000     | 1,200    | 0
Dirty Only       | 24,500      | 245      | 0
Delta (10% loss) | 15,200      | 152      | 2 (recovered)
```

**提示**：
- 基线管理：客户端每次收到更新后发送 Ack(tickNumber) 给服务器
- 漂移检测：客户端维护 `expectedTick`；收到包的 tick 与 expectedTick 不连续时记录 drift
- 修复：服务器检测到连续未 Ack 的 Tick 数 ≥ 3 时，发送全量快照

### 练习 3: 挑战 — 实现简单的 AOI（兴趣区域）系统（60min）

基于 Lua 版本的 `ServerCore`（2.3 节），扩展实现一个基本的 **AOI (Area of Interest)** 系统——客户端只收到 "附近" 实体的状态更新，而不是全图所有实体。

**要求**：
1. 将地图划分为网格（如 10×10 = 100 个格子，每个格子 20m×20m）
2. 每个客户端有一个 "AOI 范围"（默认为当前格子 + 周围 8 个相邻格子，即 3×3 九宫格）
3. `_collect_dirty_properties` 修改为：只收集 AOI 范围内的实体的脏属性
4. 当实体跨越格子边界时，处理 **AOI 进入/离开**：
   - 进入新格子的实体 → 发送完整的 Spawn 消息（含所有属性）
   - 离开旧格子的实体 → 发送 Despawn 消息
5. 实现 **AOI 过渡缓冲区**：在格子边缘加 2m 缓冲区，避免实体在格子边界来回跳跃时频繁 Spawn/Despawn
6. 测试：创建 100 个实体均匀分布在地图上，验证每个客户端只收到局部更新

**关键设计决策**（在代码注释中说明）：
- 为什么用 3×3 九宫格而不是圆形 AOI？
- 格子大小如何选择（太大 vs 太小）？
- AOI 切换时是否可能短暂看到 "闪现"？如何缓解？

---

## 扩展阅读

- **Source Multiplayer Networking** — Valve Developer Wiki: 深入理解 Source Engine（CS:GO/TF2）的属性复制和增量压缩实现细节。必读。
- **Unreal Engine Network Replication Flow** — Epic 官方文档: 理解 UE 的 `Replication Graph`、`NetPriority`、`NetUpdateFrequency` 如何协同工作。
- **Gaffer On Games: Networked Physics** — Glenn Fiedler: 状态同步 + 物理模拟的经典文章。
- **Overwatch Gameplay Architecture and Netcode (GDC)** — 详解守望先锋如何在高延迟下保持射击公平性。
- **TRIBES 2 Network Model** — 最早提出"客户端作为哑终端"思路之一的经典技术文章。
- **Introducing Iris (Unreal Engine 5)** — Epic 的下一代 Replication 系统，通过自动化的过滤和优先级排程改进状态同步性能。

---

## 常见陷阱

### 陷阱 1: 信任客户端传来的"辅助数据"

**错误模式**：
```csharp
[ServerRpc]
void MoveServerRpc(Vector3 direction, float clientDeltaTime) {
    // ❌ 直接使用客户端传来的 deltaTime！
    transform.position += direction * speed * clientDeltaTime;
}
```

**为什么错**：客户端可以发任意的 `clientDeltaTime`——比如外挂说 "我这一帧过了 0.0001 秒"，于是 speed × 0.0001 几乎不产生位移？不，外挂会说 "我这一帧过了 10 秒"，于是角色瞬移 speed × 10 的距离。外挂可以把 `clientDeltaTime` 设为负数实现倒退，设为 0 实现静止。

**正确做法**：服务器永远使用自己的计时系统（`NetworkManager.LocalTime`、`Time.timeAsDouble`、服务器的 Tick duration），客户端的时间参数仅作参考，**绝不影响服务器逻辑决策**。

```csharp
// ✓ 服务器用自己的 deltaTime
transform.position += direction * speed * Time.fixedDeltaTime;
```

### 陷阱 2: NetworkVariable 的写权限混淆

**错误理解**：以为客户端也能修改 `NetworkVariable` 的值并生效。

```csharp
// 客户端代码
NetworkHealth.Value = 50; // ❌ 不会同步到服务器！
```

**真相**：`WritePermission.Server` 的 `NetworkVariable`，客户端的写入是**本地假象**——其他客户端看不到，服务器也收不到。你的本地 UI 可能显示了 50 血量，但下一秒服务器就会覆盖回来。

**正确模式**：
```csharp
// 客户端：发送 RPC 请求服务器修改
RequestHealServerRpc(20);

// 服务器
[ServerRpc]
void RequestHealServerRpc(float amount) {
    if (CanHeal()) {
        NetworkHealth.Value += amount; // 服务器写入 → 自动同步
    }
}
```

### 陷阱 3: 高延迟下的"状态跳变"

**问题**：客户端直接设置 `transform.position = networkPosition`（如 2.1 节 OnPositionChanged 中的做法），在 200ms 延迟下会看到明显的瞬移/抖动。

**为什么会发生**：服务器以 20Hz 推送位置。客户端每 50ms 收到一次新位置。如果网络延迟不稳定（50ms → 200ms → 80ms），位置更新的间隔就不均匀——有时两帧之间角色跳了一大段。

**缓解策略**（第 16 节深入）：
- **插值 (Interpolation)**：客户端"故意落后"服务器 100ms，在这段缓冲时间内平滑插值过去的位置 → 当前位置。
- **外推 (Extrapolation/Dead Reckoning)**：在还没收到新位置时，根据速度/加速度预测继续移动。
- 不要在 `OnValueChanged` 中直接 `transform.position = newPos`。使用 `Vector3.Lerp` 或 `Vector3.SmoothDamp`。

### 陷阱 4: 忘记服务器也要跑"完整世界"的代价

**误解**：帧同步的服务器很轻量（只转发），状态同步的服务器也很轻量。完全错误。

**真相**：状态同步的服务器需要运行**所有游戏逻辑**。对于 64 人大逃杀：
- 64 个玩家的移动/状态
- 数百个投掷物的物理模拟
- AI NPC 的行为树（如果存在）
- 碰撞检测
- 伤害计算
- 技能系统

一个 64 人的 CS:GO 服务器大概需要 1-2 个 CPU 核心。100 人的 Battlefield 服务器需要更多。如果你用单线程处理所有逻辑，很容易卡在 CPU 瓶颈上。

**缓解策略**：
- 使用 ECS (Entity Component System) 架构：Unity DOTS / Unreal Mass
- 使用多线程/多进程拆分游戏世界（第 21 节）
- 警惕 Tick 中的 O(n²) 操作（如每个实体检查所有其他实体）
- 优先使用空间哈希/网格分区加速 AOI 和碰撞

### 陷阱 5: Spawn 消息丢失导致"幽灵引用"

**场景**：服务器 Spawn 了一个新子弹（NetworkId=42），并立即发送 Spawn(42) + Position(42, x, y, z) 两个包。UDP 丢包导致客户端的 Spawn(42) 丢了，但 Position(42, ...) 收到了。

**症状**：客户端收到对 NetworkId=42 的属性更新，但本地没有 id=42 的对象 → 无法应用 → 属性更新被丢弃 → 这个实体在客户端上"隐形"了。

**解决方案**：
- Spawn 消息用可靠通道发送（保证到达）
- 属性更新包中包含 "此 Tick 新 Spawn 的实体列表"，客户端检测到未识别的 NetworkId 时主动请求 Spawn 重发
- 服务器定期对一个实体重新发送 Spawn 信息（如每 30 tick 一次），作为兜底

### 陷阱 6: 属性复制的"过同步"(Over-replication)

**症状**：一个 RPG 服务器运行正常，但 30 人副本中每个玩家的下行带宽飙到 500KB/s。

**原因**：所有属性对所有客户端同步。你背包里的 50 件装备、你的任务进度、你的技能熟练度——这些属性对站在你旁边的队友毫无意义，但它们仍然在同步。

**检查清单**：
- 哪些属性**只有 Owner** 需要？（背包、任务日志）→ 用 `OwnerClientId` 过滤
- 哪些属性**只有队友**需要？（血量、Buff 状态）→ 用团队 ID 过滤
- 哪些属性**所有人都需要**？（位置、外观、动画）→ 保持
- 远处的实体是否需要所有属性？（位置 vs 手指动画）→ 属性 LOD
