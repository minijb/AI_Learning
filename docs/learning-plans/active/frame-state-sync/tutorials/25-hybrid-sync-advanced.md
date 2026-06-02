# 混合同步进阶：ECS、快照恢复、多局并行

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [24-混合同步服务端实现](24-hybrid-sync-server.md)

---

## 1. 概念讲解

### 1.1 为什么需要进阶话题？

学完前 24 节，你已经可以搭建一个混合同步服务端：双通道架构、Room 管理、DS 主循环。但"能跑"离"工业级"之间还有三道坎：

- **性能坎**：10 个玩家 × 60Hz 逻辑帧 × 数千实体 → 每帧只有 16.7ms。OOP 的虚函数调用、内存碎片、Cache Miss 会吃掉你一半的帧预算。
- **可靠性坎**：DS 进程崩溃了怎么办？玩家断线重连需要回到哪一帧？快照存多大、多久存一次？
- **规模化坎**：一台物理机要跑 50 场战斗。进程管理、负载均衡、内存上限——每一样做不好都会导致雪崩。

这三道坎对应的就是本教程的四个主题：

```
┌──────────────────────────────────────────────────────────────────────┐
│                       混合同步进阶体系                                  │
├─────────────────┬──────────────────┬──────────────────┬──────────────┤
│   ECS 架构       │   快照恢复        │   多局并行        │   性能剖析    │
│   (性能基础)     │   (可靠性基础)     │   (规模化基础)     │   (可观测性)  │
├─────────────────┼──────────────────┼──────────────────┼──────────────┤
│ • Archetype 布局 │ • 定期全量快照     │ • 单进程多 Room   │ • Profiler   │
│ • System 调度    │ • 增量快照        │ • 进程池 fork     │ • GC 避免    │
│ • 网络序列化集成  │ • 崩溃恢复流程     │ • 负载均衡        │ • Cache 优化 │
│ • Unity DOTS     │ • LZ4/Zstd 压缩   │ • 资源隔离        │ • 热点分析   │
└─────────────────┴──────────────────┴──────────────────┴──────────────┘
```

---

## 2. ECS (Entity Component System) 与网络同步

### 2.1 为什么守望先锋用 ECS？

守望先锋的服务器架构为人熟知：**单进程单战斗，ECS 驱动，60Hz Tick**。这不是偶然选择。

在传统的 GameObject-Component 模型（Unity 默认、UE Actor-Component）中：

```
传统 OOP 内存布局 (以 Unity GameObject 为例):

  GameObject[0]  →  Transform  Health  Skill  AI  Renderer  ...
  GameObject[1]  →  Transform  Health  Skill  AI  Renderer  ...
  GameObject[2]  →  Transform  Health  ...           Renderer  ...
  ...
  // 每个对象是一块分配，Component 是另一块分配
  // 遍历所有 Health：指针跳转 N 次 → Cache Miss × N
```

**Cache Miss 的代价**：L1 Cache 访问 ~1ns，主存访问 ~100ns。一次 Cache Miss 等于浪费 99ns，60Hz 下你有 16.7ms 的帧预算，如果每帧有 10,000 次 Cache Miss，光等内存就耗掉 1ms——这是纯浪费。

ECS 解决这个问题的核心手段是 **Archetype（原型）**：

```
ECS Archetype 内存布局:

  Archetype<Transform, Health, Skill>:
  ┌─────────────────────────────────────────────────────────┐
  │ Transform[0] Transform[1] Transform[2] ... Transform[N] │ ← 一块连续内存
  │ Health[0]    Health[1]    Health[2]    ... Health[N]    │ ← 一块连续内存
  │ Skill[0]     Skill[1]     Skill[2]     ... Skill[N]     │ ← 一块连续内存
  └─────────────────────────────────────────────────────────┘

  // 遍历所有 Health：一块连续内存 → 预取友好 → Cache Line 全部命中
  // System<Health> 只访问这一列 → 不加载无关数据污染 Cache
```

**为什么这对网络同步很重要？**

1. **快照序列化快**：遍历一个 Archetype 的所有 Transform，是一块连续内存的直接 `memcpy`，无需指针追踪。
2. **增量检测快**：同一个 Component 列连续存放，当前帧和上一帧做 `memcmp` 即可找出脏数据，无需逐个对象遍历。
3. **确定性执行**：System 按固定顺序调度（`SystemGroup`），执行顺序可预测、可重现——帧同步确定性的天然基础。

### 2.2 ECS 核心概念深度

#### Entity

```
Entity = 一个 32-bit 或 64-bit 的整数 ID。仅此而已。
```

Entity 不是对象。它不持有任何数据，不包含任何方法。它只是一个"钥匙"，用来查找它在哪些 Archetype 中。

```cpp
// C++ 中 Entity 的典型定义
using Entity = uint32_t;  // 低 24 bit: index, 高 8 bit: generation (防止悬空引用)

constexpr Entity kInvalidEntity = 0xFFFFFFFF;
```

#### Component

```
Component = 纯数据 struct。无方法、无虚函数、无继承。
```

这是 ECS 与 OOP 最根本的区别。在 OOP 中，`HealthComponent` 可能有 `TakeDamage()`、`Heal()`、`OnDeath` 事件。在 ECS 中：

```cpp
// ECS Component: 纯数据，POD (Plain Old Data)
struct Transform {
    float x, y, z;
    float rotation;  // 或四元数
};

struct Health {
    int current;
    int max;
};

struct Velocity {
    float vx, vy, vz;
};

// 行为在 System 中，数据在 Component 中 —— 完全分离
```

> **面试金句**："ECS 是 Data-Oriented Design (DOD) 的实践。把数据和行为分离，让数据对 CPU Cache 友好，让行为批量执行。"

#### Archetype

```
Archetype = 一组 Component 类型的唯一组合。
```

每个 Entity 的 Component 组合唯一对应一个 Archetype。当 Entity 添加或移除 Component 时，它在 Archetype 之间"移动"。

```
Archetype A: [Transform, Health]           → 静态物体（塔、基地）
Archetype B: [Transform, Health, Velocity] → 可移动角色（英雄、小兵）
Archetype C: [Transform, Velocity]         → 纯运动物体（子弹）
Archetype D: [Transform, Health, Skill]    → 有技能的静止单位
```

**关键性能特征**：每个 Archetype 内的内存是列式存储的。遍历所有 `[Transform, Health, Velocity]` 实体时，只访问这三个列，不碰其他 Archetype 的数据。

#### System

```
System = 对拥有特定 Component 组合的所有 Entity 执行的操作。
```

```cpp
// System 的声明式特征：声明它需要哪些 Component
struct MovementSystem {
    // 声明：我需要所有同时有 Transform 和 Velocity 的 Entity
    // 查询返回一个"视图"——直接访问 Archetype 列的迭代器
    
    void Execute(float deltaTime) {
        // 批量操作：一次遍历所有匹配的实体
        for (auto [transform, velocity] : world.Query<Transform, Velocity>()) {
            transform.x += velocity.vx * deltaTime;
            transform.y += velocity.vy * deltaTime;
            transform.z += velocity.vz * deltaTime;
        }
        // 编译器可以向量化这段循环 (SIMD)
    }
};
```

### 2.3 System 调度：SystemGroup 与确定性执行顺序

在帧同步架构中，所有 System 的执行顺序必须**跨客户端完全一致**。ECS 通过 SystemGroup 来实现：

```
SystemGroup 执行管线 (每逻辑帧):

  ┌──────────────────────────────────────────────────────────┐
  │  SimulationSystemGroup                                   │
  │                                                          │
  │  ┌─────────────────────────────────────────────────┐     │
  │  │  PreSimulationGroup                              │     │
  │  │  1. InputSystem          // 注入玩家输入          │     │
  │  │  2. SpawnSystem          // 生成实体请求处理      │     │
  │  └─────────────────────────────────────────────────┘     │
  │                                                          │
  │  ┌─────────────────────────────────────────────────┐     │
  │  │  SimulationGroup                                 │     │
  │  │  3. MovementSystem       // 位置更新              │     │
  │  │  4. PhysicsSystem        // 碰撞/物理             │     │
  │  │  5. SkillSystem          // 技能冷却/释放         │     │
  │  │  6. DamageSystem         // 伤害计算              │     │
  │  │  7. AISystem             // AI 行为树             │     │
  │  └─────────────────────────────────────────────────┘     │
  │                                                          │
  │  ┌─────────────────────────────────────────────────┐     │
  │  │  PostSimulationGroup                             │     │
  │  │  8. DeathSystem          // 死亡判定/清理         │     │
  │  │  9. SnapshotSystem       // 生成快照              │     │
  │  │ 10. ReplicationSystem    // 标记脏 Component     │     │
  │  └─────────────────────────────────────────────────┘     │
  └──────────────────────────────────────────────────────────┘
```

**关键约束**：

1. **Group 内 System 顺序固定**：`MovementSystem` 总是在 `PhysicsSystem` 之前。这个顺序在代码中以声明式方式注册，不依赖任何动态条件。

2. **Group 之间有序**：`PreSimulationGroup` → `SimulationGroup` → `PostSimulationGroup`。不能有跨 Group 的隐式依赖。

3. **System 之间通过 Component 通信**：`MovementSystem` 写入 `Transform`，`PhysicsSystem` 读取 `Transform`。ECS 框架可以通过分析 Component 的读写依赖自动推导 System 的调度顺序（如 Unity DOTS 的 `UpdateBefore`/`UpdateAfter` 属性）。

```csharp
// Unity DOTS 中声明 System 执行顺序
[UpdateInGroup(typeof(SimulationSystemGroup))]
[UpdateBefore(typeof(PhysicsSystem))]      // 保证在物理之前执行
public partial struct MovementSystem : ISystem
{
    public void OnUpdate(ref SystemState state)
    {
        float dt = SystemAPI.Time.DeltaTime;
        foreach (var (transform, velocity) in 
            SystemAPI.Query<RefRW<LocalTransform>, RefRO<Velocity>>())
        {
            transform.ValueRW.Position += velocity.ValueRO.Value * dt;
        }
    }
}
```

### 2.4 ECS 与帧同步：Archetype 状态的快速序列化

帧同步要求能够对游戏状态做快照（用于 Hash 校验或断线重连）。ECS 的列式存储使这个操作极其高效：

```
传统 OOP 快照序列化:
  for each GameObject:
    writer.Write(obj.transform.position)   // 指针跳转 1
    writer.Write(obj.health.current)       // 指针跳转 2
    writer.Write(obj.velocity)             // 指针跳转 3
    ...
  // N 个对象 × M 个 Component × 指针跳转 = N×M 次 Cache Miss

ECS 快照序列化:
  for each Archetype:
    memcpy(transformColumn, writer)        // 一次连续拷贝整个列
    memcpy(healthColumn, writer)           // 同上
    memcpy(velocityColumn, writer)         // 同上
  // Archetype 数 × Component 列数 = 极少的 memcpy 调用
```

**为什么这对混合同步重要**：在混合同步服务端（教程 24），第 3 步"生成状态快照"是每帧都执行的操作。ECS 让这一步从"遍历所有对象"变成"拷贝几个连续内存块"。

### 2.5 ECS 与状态同步：Component 级别的增量检测

状态同步的核心是"只发送变化了的数据"。在 ECS 中，增量检测可以精确到 Component 列级别：

```
增量检测策略:

  方法 1: 帧间 memcmp
  ┌────────────────────────────────────┐
  │ 上一帧 Transform 列 (4096 bytes)    │
  │ 当前帧 Transform 列 (4096 bytes)    │
  │          ↓ memcmp                   │
  │ 变化的 byte 范围: [128, 160]        │
  │ → 只有 Entity #8 (偏移128/16=8) 移动了 │
  └────────────────────────────────────┘

  方法 2: 写入标记 (Dirty Flag)
  ┌────────────────────────────────────┐
  │ 每个 Component 列配一个 DirtyBits   │
  │ Health 列: [0,0,0,1,0,0,...]       │
  │              ↑ Entity #3 血量变了   │
  └────────────────────────────────────┘
```

**方法 1** 利用 SIMD 指令（SSE/AVX `_mm_cmpeq_epi8`），一次比较 16/32 字节。对 4096 字节的列，只需 256 次 SIMD 比较。

**方法 2** 在 System 写入 Component 时打标记，序列化时只读脏行——适合实体数多但修改率低的场景。

### 2.6 Unity DOTS (ECS 1.0) 网络同步方案

Unity 的 DOTS (Data-Oriented Technology Stack) 包含 ECS 1.0，是目前 Unity 官方推荐的服务器架构。以下是其在网络同步中的实践：

```
Unity DOTS 网络同步架构:

  ┌──────────────────────────────────────────────────────┐
  │                   Netcode for Entities                │
  │  ┌─────────────────┐  ┌─────────────────────────────┐ │
  │  │ Ghost Replication │  │ Networked Components       │ │
  │  │ (实体复制系统)     │  │ 标记哪些 Component 需要同步 │ │
  │  └────────┬────────┘  └──────────────┬──────────────┘ │
  │           │                          │                 │
  │  ┌────────▼──────────────────────────▼──────────────┐ │
  │  │              Ghost Serialization                  │ │
  │  │  • 预测实体 (Predicted): 客户端预测+服务器和解     │ │
  │  │  • 插值实体 (Interpolated): 客户端插值服务器状态   │ │
  │  │  • 仅服务器实体: 客户端不模拟，仅渲染              │ │
  │  └──────────────────────────────────────────────────┘ │
  └──────────────────────────────────────────────────────┘
```

**关键设计**：

```csharp
// Unity Netcode for Entities: 标记需要同步的 Component
[GhostComponent]  // 标记此 Component 参与网络同步
public struct Health : IComponentData
{
    [GhostField]  // 标记此字段参与序列化
    public int Current;
    [GhostField]
    public int Max;
}

[GhostComponent(PrefabType = GhostPrefabType.Predicted)]  // 客户端预测实体
public struct PlayerInput : IComponentData
{
    public float2 MoveDirection;
    public bool Fire;
}

// 服务器端：发送 Ghost Snapshot
// Netcode for Entities 自动：
// 1. 每 N 帧对所有 GhostComponent 做增量序列化
// 2. 只发变化的字段（基于 GhostField 的 change mask）
// 3. 客户端收到后反序列化到对应 Entity
```

**Unity DOTS 适合什么**：
- 服务器端逻辑（DS/Headless）：ECS 的性能优势在服务器上最大化
- 大量实体（数千+）：ECS 的批量处理优势明显
- 帧同步 + 混合同步：确定性 System 调度天然契合

**不适合什么**：
- 小型项目（<100 实体）：ECS 的学习成本和代码复杂度超过收益
- 重度使用 GameObject 的项目：DOTS 与 GameObject 互操作成本高

### 2.7 Unreal Mass Entity 网络考量

UE5 引入了 **Mass Entity**，用于大规模实体模拟（如城市中的数万行人/车辆）。其核心设计思想与 ECS 高度相似：

```
Mass Entity 架构:

  ┌───────────────────────────────────────────────┐
  │              Mass Entity System                │
  │                                               │
  │  FMassEntityManager                            │
  │  ├─ Archetype 管理 (类似 ECS)                   │
  │  ├─ Chunk 内存布局 (16KB 一块)                  │
  │  └─ Fragment = Component                       │
  │                                               │
  │  FMassProcessor (类似 System)                  │
  │  ├─ 按 Archetype 批量处理                       │
  │  └─ Execute(FMassEntityManager&, FMassExecutionContext&) │
  │                                               │
  │  网络同步考量:                                  │
  │  ├─ 当前 Mass 主要面向客户端表现层               │
  │  ├─ 服务器网络同步仍需 Iris Replication         │
  │  └─ 大规模 Entity 的带宽 → 需 LOD + 视野裁剪     │
  └───────────────────────────────────────────────┘
```

**Mass vs ECS 网络同步建议**：

| 引擎 | 小规模（<100） | 中规模（100-1000） | 大规模（1000+） |
|------|---------------|-------------------|----------------|
| Unity | GameObject + NGO | ECS + Netcode for Entities | ECS + 自定义 |
| Unreal | Actor + Iris | Actor + Iris + LOD | Mass (表现) + Iris (关键实体) |

> **面试要点**：被问"你如何看待 UE5 Mass Entity 在网络同步中的应用"时，回答"Mass 当前定位是客户端表现层的大规模模拟，权威状态同步仍依赖 Iris Replication 处理关键实体。Mass 可以通过 Archetype 批量序列化来优化下行带宽，但增量检测和视野裁剪是更大的瓶颈。"

---

## 3. 快照恢复 (Snapshot Recovery)

### 3.1 为什么需要快照恢复？

教程 24 中我们设计了 DS 主循环——每帧收集输入、执行逻辑、广播。但一个关键问题没有解决：

> **如果 DS 进程崩溃了，或者玩家断线 5 分钟后重连，如何恢复？**

两个典型场景：

**场景 1：DS 崩溃恢复**。服务器跑到第 10000 帧时 crash 了（OOM、段错误、逻辑 bug）。DSA 检测到后拉起新进程，新进程从哪一帧开始？如果从头跑（帧 0），10 分钟的对局要重算 10 分钟——而且这期间的输入序列可能已经丢失。

**场景 2：玩家断线重连**。玩家在第 5000 帧掉线，3 分钟后（第 7000 帧）重连。他的客户端状态停留在第 5000 帧。如果从第 5000 帧重新模拟 2000 帧，需要 2000 × 33ms = 66 秒——这在体验上不可接受。他需要的是"从第 7000 帧的完整状态直接开始"。

两个场景的解决方案都是同一个：**定期保存完整状态快照**。

### 3.2 定期快照 (Periodic Full Snapshot)

```
时间轴:
 Frame: 0 ----- 300 ----- 600 ----- 900 ----- 1200 ----- 1500 ----- ...
                │         │         │         │          │
             Snapshot   Snapshot  Snapshot  Snapshot   Snapshot
              #1         #2        #3        #4         #5
              (全量)     (全量)    (全量)    (全量)     (全量)
```

**核心参数**：快照间隔 N。

| N 值 | 恢复时间（最坏） | 存储开销 | 适用 |
|------|-----------------|---------|------|
| 30 (1秒) | 重算 30 帧 | 高（每1秒一个全量快照） | 电竞/高可靠性 |
| 300 (10秒) | 重算 300 帧 | 中 | 通用推荐 |
| 900 (30秒) | 重算 900 帧 | 低 | 休闲/移动端 |

**快照存储策略**：

```
环形缓冲区: 只保留最近 K 个快照

 Snapshot Ring (K=5):
 ┌────┬────┬────┬────┬────┐
 │ S1 │ S2 │ S3 │ S4 │ S5 │ ← 写满后覆盖最早的
 └────┴────┴────┴────┴────┘
   ↑                    ↑
 oldest              latest

 崩溃恢复: 从 latest 快照 + 之后的所有输入重放 → 恢复到崩溃帧
 重连: 从 latest 快照直接下发 → 客户端替换当前状态
```

为什么用环形缓冲区而非无限保存？

- **内存**：一个全量快照可能 10-100MB（取决于实体数和 Component 数），无限保存 → 1 小时对局 = 30GB。
- **实际价值**：超出一定时间窗口（如最后 2 分钟）的快照，重放成本已接近从头跑，快照失去意义。

### 3.3 增量快照 (Delta Snapshot)

全量快照的存储开销大。增量快照只保存两次全量快照之间的**差异**：

```
Frame:  0 ---- 100 ---- 200 ---- 300 ---- 400 ---- 500
         │      │        │        │        │        │
       Full   Delta   Delta    Full    Delta    Delta
       S0     ΔS1     ΔS2      S3      ΔS4      ΔS5

恢复流程（目标帧=450）:
  1. 找到最近的全量快照 S3 (frame 300)
  2. 从磁盘加载 S3
  3. 按序应用 ΔS4, ΔS5 → 得到 frame 500 的状态
  4. 如果目标帧在 ΔS5 之后：继续重放输入
```

**增量快照的两种实现**：

#### 方法 A：Component 级别的 Copy-on-Write Diff

```
全量快照 S_n 存储:
  Archetype_A:
    Transform 列: [T0, T1, T2, ..., T99]  (100 个实体)
    Health 列:    [H0, H1, H2, ..., H99]

增量快照 ΔS_{n+1} 只存储变化的行:
  Transform 列变化: { entityIdx=3: T3_new, entityIdx=42: T42_new }
  Health 列变化:    { entityIdx=7: H7_new }
```

#### 方法 B：基于 Archetype Chunk 的差分

```
Archetype Chunk 大小固定 (如 16KB)。
比较两个快照间每个 Chunk 的 Hash → Hash 相同则跳过 → Hash 不同则存整个 Chunk。

优点: 比逐行 diff 快 (只需 Hash 比较)
缺点: 粒度较粗 (一个字段变则整个 Chunk 存)
```

### 3.4 崩溃恢复流程

```
┌──────────────────────────────────────────────────────────────────────┐
│                        崩溃恢复完整流程                                  │
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │ DS 崩溃   │───►│ DSA 检测  │───►│ 分配新DS  │───►│ 加载快照  │        │
│  │ Frame=N   │    │ 心跳超时  │    │ 选择节点  │    │ 从磁盘    │        │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘        │
│                                                       │              │
│                                                       ▼              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │ 恢复完成  │◄───│ 追上进度  │◄───│ 重放输入  │◄───│ 找到最近  │        │
│  │ 正常运行  │    │ 达到N帧  │    │ 逐帧执行  │    │ 快照帧M   │        │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘        │
│                                                                      │
│  快照来源选择:                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  1. 本地磁盘 (DS 同机)         → 最快，但同机崩溃不可用        │   │
│  │  2. 共享存储 (NFS/分布式FS)    → 可靠，有网络 IO 开销          │   │
│  │  3. 对等 DS (P2P 备份)        → 守望先锋方案：每场战斗 2 个 DS  │   │
│  │     主 DS 处理逻辑，影子 DS (Shadow Server) 仅接收输入+保存快照 │   │
│  │     主 DS 崩溃 → 影子 DS 立即接管                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**守望先锋的影子服务器方案**：

```
┌─────────────────┐         ┌─────────────────┐
│   主 DS (Active) │  输入流  │  影子 DS (Shadow) │
│                 │────────►│                 │
│  • 执行逻辑      │         │  • 只接收输入     │
│  • 广播状态      │         │  • 保存快照       │
│  • 响应客户端    │         │  • 不响应客户端    │
│                 │         │  • 不执行逻辑      │
└────────┬────────┘         └────────┬────────┘
         │ 崩溃                       │
         ▼                            ▼
   DSA 检测到主 DS 心跳丢失 ──► 影子 DS 提升为主 DS
   (切换时间: <100ms)
```

> 这个方案的成本是 2x 的服务器资源，但换来的是零数据丢失的故障转移。电竞级比赛必须用。

### 3.5 快照序列化：二进制格式与压缩

#### 二进制格式设计

快照的序列化格式直接影响恢复速度。推荐自行设计紧凑的二进制格式而非使用 Protobuf/JSON：

```
快照文件二进制格式:

┌──────────────────────────────────────────────┐
│ Header (64 bytes)                             │
│  ├─ magic:     uint32   (0x534E4150 "SNAP")   │
│  ├─ version:   uint16   (格式版本号)           │
│  ├─ frameNo:   uint32   (帧号)                │
│  ├─ timestamp: uint64   (unix ms)              │
│  ├─ entityCount: uint32 (实体总数)              │
│  ├─ archetypeCount: uint16 (Archetype 种类数)  │
│  ├─ compressed: uint8   (0=无, 1=LZ4, 2=Zstd) │
│  └─ reserved:  byte[37]                       │
├──────────────────────────────────────────────┤
│ Archetype Table (变长)                        │
│  for each Archetype:                          │
│  ├─ archetypeHash: uint64 (Component 组合哈希) │
│  ├─ entityCount: uint32                       │
│  ├─ componentCount: uint8                     │
│  └─ for each Component:                       │
│      ├─ componentTypeHash: uint32             │
│      ├─ dataOffset: uint32 (在数据区中的偏移)   │
│      └─ dataSize: uint32                      │
├──────────────────────────────────────────────┤
│ Data Section (变长)                           │
│  for each Component Column:                   │
│  └─ raw bytes of the entire column            │
│     (所有实体的此 Component 数据连续存放)       │
└──────────────────────────────────────────────┘
```

**关键设计决策**：

1. **列式存储**：所有实体的同一 Component 连续存放 → 加载时直接 `memcpy` 到 Archetype 列。
2. **Component 哈希而非字符串名**：`uint32` 比 `"Transform"` (9 bytes) 更紧凑，且哈希在构建时预计算。
3. **压缩在 Section 级别**：可以对 Data Section 整体压缩，Header 和 Table 不压缩（需要先解析 Table 才知道数据如何解压）。

#### 压缩算法选择

| 算法 | 压缩比 | 压缩速度 | 解压速度 | 适用 |
|------|--------|---------|---------|------|
| LZ4 | 2-3x | ~500 MB/s | ~2000 MB/s | 实时快照（每帧/每秒） |
| Zstd (level 1) | 3-5x | ~350 MB/s | ~1000 MB/s | 定期快照（每 10 秒） |
| Zstd (level 19) | 5-8x | ~5 MB/s | ~1000 MB/s | 离线存储（录像存档） |

**推荐策略**：运行时用 LZ4（速度快），存档时用 Zstd level 19（体积小）。

```
具体流程:
  1. 序列化快照到内存 buffer (不压缩)
  2. 用 LZ4 压缩 buffer → 写入环形缓冲区 (内存)
  3. 每 5 分钟: 取最新快照，用 Zstd level 19 压缩 → 写入磁盘 (持久化)
  4. 崩溃恢复: 优先从内存环形缓冲区恢复 (其他 DS 的内存/共享内存)
     如果不可用: 从磁盘 Zstd 快照恢复 (丢失最多 5 分钟进度)
```

---

## 4. 多局并行 (Multi-Room)

### 4.1 三种多局并行方案

教程 24 中我们介绍了两种模式：单进程多战斗和单进程单战斗。这里深入各自的实现细节。

#### 方案 A：场景叠加 + PhysicsWorld 隔离（合金弹头方案）

```
单进程内 N 个 Room 并行:

┌───────────────────────────────────────────────────────┐
│                     DS 进程                            │
│                                                       │
│  ┌─────────────────┐  ┌─────────────────┐             │
│  │   Room #1        │  │   Room #2        │  ...        │
│  │  ┌─────────────┐ │  │  ┌─────────────┐ │             │
│  │  │ PxScene A   │ │  │  │ PxScene B   │ │             │
│  │  │ (独立物理)   │ │  │  │ (独立物理)   │ │             │
│  │  └─────────────┘ │  │  └─────────────┘ │             │
│  │  ┌─────────────┐ │  │  ┌─────────────┐ │             │
│  │  │ EntityMgr A │ │  │  │ EntityMgr B │ │             │
│  │  │ (独立实体)   │ │  │  │ (独立实体)   │ │             │
│  │  └─────────────┘ │  │  └─────────────┘ │             │
│  │  ┌─────────────┐ │  │  ┌─────────────┐ │             │
│  │  │ Network A   │ │  │  │ Network B   │ │             │
│  │  │ (独立Socket) │ │  │  │ (独立Socket) │ │             │
│  │  └─────────────┘ │  │  └─────────────┘ │             │
│  └─────────────────┘  └─────────────────┘             │
│                                                       │
│  共享: 线程池 / 内存分配器 / 日志 / 定时器               │
└───────────────────────────────────────────────────────┘
```

**PhysicsWorld 隔离的关键代码**：

```csharp
// PhysX 中每个 Room 使用独立的 PxScene
public class RoomPhysicsWorld
{
    private PxScene _scene;  // 每个 Room 独立的物理场景
    
    public void Initialize()
    {
        var sceneDesc = new PxSceneDesc(Physics.TolerancesScale);
        sceneDesc.gravity = new PxVec3(0, -9.81f, 0);
        sceneDesc.cpuDispatcher = PxDefaultCpuDispatcherCreate(1); // 每个 Room 1 个线程
        
        _scene = Physics.CreateScene(sceneDesc);
    }
    
    public void Simulate(float deltaTime)
    {
        _scene.simulate(deltaTime);
        _scene.fetchResults(true);
    }
    
    public void Dispose()
    {
        _scene.release();  // 释放该 Room 的物理资源
    }
}
```

**隔离要点**：
- 每个 Room 的 `PxScene` 完全独立，碰撞只发生在 Room 内部的实体之间
- 物理线程数按 Room 数量分配：50 个 Room × 1 线程 = 50 线程，这在 32 核机器上可能过载 → 使用共享的 `PxDefaultCpuDispatcher` 按 Room 优先级调度
- 如果使用 Bullet Physics：每个 Room 独立 `btDiscreteDynamicsWorld`，更简单（Bullet 不强制绑定线程模型）

#### 方案 B：单进程单战斗（守望先锋方案）

```
每场战斗一个独立进程:

  DS Process Pool (预热的进程池):
  ┌──────────────────────────────────────────────┐
  │  Pool Manager                                │
  │                                              │
  │  Idle Pool (Ready to use):                   │
  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
  │  │ Proc1│ │ Proc2│ │ Proc3│ │ Proc4│  ...    │
  │  │ 空闲  │ │ 空闲  │ │ 空闲  │ │ 空闲  │       │
  │  └──────┘ └──────┘ └──────┘ └──────┘       │
  │                                              │
  │  Active Pool (Fighting):                     │
  │  ┌──────┐ ┌──────┐ ┌──────┐                │
  │  │ Proc5│ │ Proc6│ │ Proc7│  ...            │
  │  │ Room1│ │ Room2│ │ Room3│                 │
  │  └──────┘ └──────┘ └──────┘                │
  └──────────────────────────────────────────────┘
```

**进程池 (Process Pool) 的实现**：

```csharp
// C# 进程池管理器
public class DSProcessPool
{
    // 配置
    private readonly int _poolSize;             // 预热进程数
    private readonly string _dsExecutablePath;   // DS 可执行文件路径
    private readonly int _maxRoomsPerProcess;    // 本例中 = 1 (单进程单战斗)
    
    // 进程池
    private readonly Queue<DSProcess> _idlePool = new();
    private readonly Dictionary<uint, DSProcess> _activePool = new();
    
    // 预热：启动池中所有进程
    public async Task WarmupAsync()
    {
        for (int i = 0; i < _poolSize; i++)
        {
            var proc = await LaunchProcessAsync();
            await proc.WaitForReady();  // 等待 DS 进程完成初始化
            _idlePool.Enqueue(proc);
        }
    }
    
    // 分配一个空闲进程给新 Room
    public async Task<DSProcess> AllocateAsync(uint roomId)
    {
        DSProcess proc;
        
        if (_idlePool.Count > 0)
            proc = _idlePool.Dequeue();  // 从池中取
        else
            proc = await LaunchProcessAsync();  // 池空，动态启动
        
        await proc.AssignRoom(roomId);  // 通知 DS 进程创建 Room
        _activePool[roomId] = proc;
        
        // 确保池中至少保留 _poolSize 个备用进程
        _ = ReplenishPoolAsync();
        
        return proc;
    }
    
    // Room 结束，回收进程
    public void Release(uint roomId)
    {
        if (_activePool.TryGetValue(roomId, out var proc))
        {
            proc.Reset();  // 重置 DS 状态（清理内存、关闭 Socket）
            _idlePool.Enqueue(proc);
            _activePool.Remove(roomId);
        }
    }
    
    // 后台补充池
    private async Task ReplenishPoolAsync()
    {
        while (_idlePool.Count < _poolSize)
        {
            var proc = await LaunchProcessAsync();
            _idlePool.Enqueue(proc);
        }
    }
}
```

**进程预热 (Warmup) 的重要性**：

启动一个 DS 进程的代价：
- 加载引擎库：Unreal 引擎加载 ~2-5 秒，Unity IL2CPP ~1-3 秒
- 分配内存：预分配网络缓冲、对象池
- JIT/Warmup：.NET JIT 需要预热几个方法调用

如果不预热，匹配完成后用户要等 3-10 秒才能进战斗——这在手游/端游中不可接受。

**Linux fork 优化**：

在 Linux 上，可以用 `fork()` 来加速进程创建：

```
1. 父进程 (模板 DS):
   - 加载完所有资源（引擎、地图、通用实体模板）
   - 初始化网络栈（监听端口）
   - 此时 fork() 出子进程

2. 子进程 (实际战斗 DS):
   - 继承父进程的全部内存（Copy-on-Write，实际不复制）
   - 关闭继承的监听 Socket，创建自己的
   - 分配 Room 专用资源，开始战斗

优点: fork() 耗时 ~1ms，远快于重新加载引擎 (3-10s)
局限: Windows 不支持 fork()（Windows 上用进程池预热替代）
```

> 面试时如果有人问"Windows 上怎么实现类似 fork 的快速启动"，回答"Windows 上可以用进程池预热 + `CreateProcess` + 预加载的 DLL 共享（DLL 代码段在进程间共享物理页），但无法做到 Linux fork 的 COW 零拷贝效果。"

#### 方案 C：混合模式（多 Room 进程 + 进程池）

```
实际生产环境往往是混合的:

  物理机 (32核, 64GB):
  ┌─────────────────────────────────────────────────────────┐
  │  DS Process #1 (多Room, 4核, 8GB)                        │
  │  ├─ Room 1-10: 2v2 对战 (轻量)                          │
  │  └─ Room 11-15: PvE 副本 (轻量)                         │
  │                                                         │
  │  DS Process #2 (单Room, 8核, 16GB)                      │
  │  └─ Room 20: 5v5 排位 (重量级)                          │
  │                                                         │
  │  DS Process #3 (多Room, 2核, 4GB)                       │
  │  └─ Room 30-60: 休闲模式 (极轻量)                       │
  │                                                         │
  │  Idle Pool: Process #4-6 (预热待命)                     │
  └─────────────────────────────────────────────────────────┘
```

**选择逻辑**：

| 战斗类型 | 预期负载 | 分配策略 |
|---------|---------|---------|
| 2v2 休闲 | 低 CPU/内存 | 分配到共享进程（多 Room）|
| 5v5 排位 | 高 CPU/内存 | 分配到独占进程（单 Room）|
| 竞标赛 | 最高优先级 | 独占进程 + 影子 DS |

### 4.2 负载均衡

```
负载均衡决策:

┌──────────────────────────────────────────────────────────┐
│                      DSA (Agent)                          │
│                                                          │
│  收到开房请求 (roomType=5v5_ranked)                       │
│    │                                                     │
│    ├─ 1. 查询所有 DS 实例的负载指标                        │
│    │     DS#1: CPU 85%, Mem 90%, Room 3/10    ← 太满     │
│    │     DS#2: CPU 45%, Mem 60%, Room 1/5     ← 可选     │
│    │     DS#3: CPU 30%, Mem 40%, Room 2/10    ← 最优     │
│    │                                                     │
│    ├─ 2. 计算"容纳能力"                                  │
│    │     capacity = min(                                  │
│    │       (100 - cpu%) / cpuPerRoom,                     │
│    │       (100 - mem%) / memPerRoom,                     │
│    │       maxRooms - currentRooms                        │
│    │     )                                                │
│    │                                                     │
│    └─ 3. 选择 capacity 最大且匹配 roomType 的 DS          │
│         → 通知 DS#3 创建 Room                            │
└──────────────────────────────────────────────────────────┘
```

**负载指标采集**：

```csharp
public struct DSLoadMetrics
{
    public float CpuUsage;        // CPU 使用率 (0-100%)
    public float MemoryUsage;     // 内存使用率 (0-100%)
    public int   ActiveRooms;     // 活跃 Room 数
    public int   MaxRooms;        // 最大 Room 数
    public float NetworkInBps;    // 入站带宽 (bytes/s)
    public float NetworkOutBps;   // 出站带宽 (bytes/s)
    public int   TicksPerSecond;  // 实际逻辑帧率（低于配置值 = 过载）
    public long  Timestamp;       // 采集时间
    
    // 核心健康指标：实际 tick 频率是否低于配置
    public bool IsOverloaded(int configTickRate) 
        => TicksPerSecond < configTickRate * 0.9f;
}
```

**负载采集频率**：DS 每 5 秒上报一次心跳 + 负载指标给 DSA。DSA 维护每台 DS 的负载滑动窗口（最近 1 分钟）。

**过载处理**：
1. `TicksPerSecond` 低于配置的 90% → 标记为"过载"
2. 停止向过载 DS 分配新 Room
3. 如果持续过载超过 2 分钟 → 考虑将部分轻量 Room 迁移到其他 DS（需支持 Room 迁移的快照机制）

---

## 5. 性能剖析

### 5.1 热点分析：Unity Profiler / UE Insights

混合同步服务端的性能瓶颈通常按优先级排序：

```
高优先级 (每帧都执行，最容易成为瓶颈):
  1. 网络 IO (收包/发包、序列化/反序列化)  ← 最常成为瓶颈
  2. 物理模拟 (碰撞检测、约束解算)
  3. 快照生成 (内存拷贝/压缩)

中优先级:
  4. AI/行为树 (NPC 决策)
  5. 技能/伤害系统
  6. 输入处理

低优先级:
  7. 日志/监控上报
  8. 统计/结算
```

**Unity Profiler 关键指标**：

```csharp
// 在关键路径上添加 Profiler Marker
public class HybridDSTickSystem
{
    public void Tick(int frameNumber)
    {
        UnityEngine.Profiling.Profiler.BeginSample("DS.Tick.Total");
        
        UnityEngine.Profiling.Profiler.BeginSample("DS.Tick.NetworkRecv");
        CollectInputs(frameNumber);
        UnityEngine.Profiling.Profiler.EndSample();
        
        UnityEngine.Profiling.Profiler.BeginSample("DS.Tick.Physics");
        Physics.Simulate(Time.fixedDeltaTime);
        UnityEngine.Profiling.Profiler.EndSample();
        
        UnityEngine.Profiling.Profiler.BeginSample("DS.Tick.Systems");
        _world.Update();
        UnityEngine.Profiling.Profiler.EndSample();
        
        UnityEngine.Profiling.Profiler.BeginSample("DS.Tick.Snapshot");
        GenerateSnapshot(frameNumber);
        UnityEngine.Profiling.Profiler.EndSample();
        
        UnityEngine.Profiling.Profiler.BeginSample("DS.Tick.NetworkSend");
        BroadcastState();
        UnityEngine.Profiling.Profiler.EndSample();
        
        UnityEngine.Profiling.Profiler.EndSample();
    }
}
```

**UE Insights 等效用法**：

```cpp
// Unreal Engine: TRACE_CPUPROFILER_EVENT_SCOPE
void UHybridDSWorldSubsystem::Tick(float DeltaTime)
{
    TRACE_CPUPROFILER_EVENT_SCOPE(DS_Tick_Total);
    
    {
        TRACE_CPUPROFILER_EVENT_SCOPE(DS_Tick_NetworkRecv);
        CollectInputs(CurrentFrame);
    }
    
    {
        TRACE_CPUPROFILER_EVENT_SCOPE(DS_Tick_Physics);
        GetPhysicsScene()->Tick(DeltaTime);
    }
    
    // ...
}
```

**分析流程**：

1. 录制 5-10 分钟的典型对局（Profiler 文件）
2. 按时间排序：找出 `Total` 中占比最大的子项
3. 深入子项：是否有不必要的分配？是否有单帧内的重复计算？
4. 比较不同 Room 数下的性能曲线：找到系统的极限容量

### 5.2 内存管理：避免 GC 抖动

这是 C# DS 最容易踩的坑。服务端对局可能持续 30 分钟+，GC 触发一次 Gen2 回收可能暂停 50-200ms——在 60Hz 的逻辑帧中，这等于丢 3-12 帧。

**核心原则**：**帧循环的 hot path 上零分配**。

```csharp
// ❌ 错误：每帧分配
void ProcessDamage(Entity target, int damage)
{
    var eventData = new DamageEvent { target = target, value = damage };
    //                              ↑ 每帧 new → GC 压力
    _eventQueue.Add(eventData);
}

// ✅ 正确：使用对象池
void ProcessDamage(Entity target, int damage)
{
    var eventData = _damageEventPool.Rent();
    eventData.target = target;
    eventData.value = damage;
    _eventQueue.Add(eventData);
}
// 处理完成后 Return 到池中
```

**ECS 的内存优势**：

ECS 中，Component 数据存储在预分配的 Chunk（通常 16KB）中，不会逐实体分配。New Entity 时从 Chunk 的空位中分配，Destroy Entity 时将空位标记为空闲——整个过程不涉及 GC。

```cpp
// ECS Chunk 内存管理 (概念代码)
struct ArchetypeChunk {
    static constexpr int kChunkSize = 16 * 1024; // 16KB
    static constexpr int kMaxEntities = kChunkSize / sizeof(ComponentSet);
    
    byte data[kChunkSize];        // 所有 Component 数据
    uint32_t entityIds[kMaxEntities];  // Entity ID
    int count;                    // 当前实体数
    int freeListHead;             // 空闲位链表头
    
    // 添加实体: 从 freeList 取一个位置，写入 Component 数据
    // 移除实体: 加到 freeList，标记对应 Component 为默认值
    // 整个过程零 new/delete，零 GC
};
```

**其他 GC 避免技巧**：

1. **`List<T>`/`Dictionary<K,V>` 预分配容量**：`new List<Entity>(1024)` 而非默认的 `new List<Entity>()`
2. **使用 `ArrayPool<byte>` 管理网络缓冲区**：`byte[] buffer = ArrayPool<byte>.Shared.Rent(4096)`
3. **避免 LINQ/闭包**：`Where().Select()` 创建迭代器和闭包，在 hot path 上手工 `for` 循环
4. **避免字符串拼接**：日志用 `StringBuilder` 池化，或结构化日志（只写数值，不拼接字符串）
5. **`struct` 替代 `class`**：值类型在栈上分配或在 Chunk 内嵌，零 GC。但要小心装箱（传 `object` 参数时 `struct` 会被装箱）

### 5.3 CPU Cache 优化：数据局部性

这是高级优化，通常只在性能不足时才做。但面试中经常考察。

```
CPU Cache 层级 (典型):
  L1: 32KB,  延迟 ~1ns,  每核私有
  L2: 256KB, 延迟 ~4ns,  每核私有
  L3: 8MB,   延迟 ~12ns, 所有核共享
  RAM: 64GB, 延迟 ~100ns

Cache Line: 64 字节 (一次从 RAM 读 64 字节)
```

**对网络同步代码的影响**：

```csharp
// ❌ 差的数据布局: AoSoA (Array of Structs of Arrays) 混合过大
struct Entity {  // 一个大 struct，可能有 200+ 字节
    public int id;
    public float posX, posY, posZ;
    public float velX, velY, velZ;
    public int hp, maxHp, mp, maxMp;
    public int skillCooldown0, skillCooldown1, skillCooldown2, skillCooldown3;
    public int buffCount;
    public fixed int buffIds[8];
    // ... 200+ bytes total
}
Entity[] entities = new Entity[1000];

// 遍历所有 Entity 更新位置:
for (int i = 0; i < 1000; i++)
    entities[i].posX += entities[i].velX * dt;
// 问题: 每个 Entity 在 Cache Line 中只用到 24/200 = 12% 的数据
//       剩下的 88% 被白白加载进 Cache，污染了宝贵的 L1/L2
```

```csharp
// ✅ 好的数据布局: SoA (Structure of Arrays)
struct PositionComponent {
    public float x, y, z;  // 12 bytes
}
struct VelocityComponent {
    public float x, y, z;  // 12 bytes
}

// 列式存储: 两个独立数组
PositionComponent[] positions = new PositionComponent[1000];
VelocityComponent[] velocities = new VelocityComponent[1000];

// 遍历更新位置:
for (int i = 0; i < 1000; i++)
{
    positions[i].x += velocities[i].x * dt;
    positions[i].y += velocities[i].y * dt;
    positions[i].z += velocities[i].z * dt;
}
// 优势: 每 64 字节 Cache Line 容纳 5.3 个位置+速度 → 命中率高
```

**ECS 天然做到了这一点**。这也是为什么大型 DS 倾向于 ECS 架构。

---

## 6. 代码示例

### 6.1 C# ECS 快照系统 (MemorySnapshot)

```csharp
// MemorySnapshot.cs
// 基于 ECS 的全量/增量快照系统
// 依赖: Unity.Collections, Unity.Entities (或自建简单 ECS)

using System;
using Unity.Collections;
using Unity.Collections.LowLevel.Unsafe;
using System.IO;
using System.IO.Compression;  // DeflateStream
using System.Runtime.InteropServices;

/// <summary>
/// 快照类型标记
/// </summary>
public enum SnapshotType : byte
{
    Full = 0,   // 全量快照
    Delta = 1,  // 增量快照 (基于上一全量快照的差异)
}

/// <summary>
/// 快照文件头部 (64 bytes, 按 8 字节对齐)
/// </summary>
[StructLayout(LayoutKind.Sequential, Pack = 1)]
public struct SnapshotHeader
{
    public uint Magic;          // 0x534E4150 = "SNAP"
    public ushort Version;      // 格式版本
    public SnapshotType Type;
    public uint FrameNumber;    // 帧号
    public ulong TimestampMs;   // Unix 毫秒时间戳
    public uint TotalEntities;  // 实体总数
    public ushort ArchetypeCount; // Archetype 种类数
    public byte Compression;    // 0=None, 1=Deflate
    public byte Reserved0;
    public uint Reserved1;
    public uint Reserved2;
    public uint Reserved3;
    public uint Reserved4;
    public uint Reserved5;
    // 总共 64 bytes (验证: 4+2+1+1+4+8+4+2+1+1+4+4+4+4+4=48, 补齐到64)
    // 实际编译后可能需 Marshal.SizeOf 确认
}

/// <summary>
/// 一个 Archetype 的元数据
/// </summary>
public struct ArchetypeMeta
{
    public ulong ArchetypeHash;     // Component 组合的哈希
    public uint EntityCount;        // 该 Archetype 中实体数
    public ushort ComponentCount;
    // 紧随: ComponentMeta[ComponentCount]
}

/// <summary>
/// 单个 Component 列的元数据
/// </summary>
public struct ComponentMeta
{
    public uint TypeHash;   // Component 类型哈希
    public uint DataOffset; // 在数据区中的偏移
    public uint DataSize;   // 该列的总字节数
}

/// <summary>
/// ECS 快照管理器 — 负责保存和加载世界状态快照
/// </summary>
public class MemorySnapshotManager : IDisposable
{
    // ── 配置 ─────────────────────────────────
    private const uint SNAPSHOT_MAGIC = 0x534E4150;
    private const ushort SNAPSHOT_VERSION = 1;
    private const int FULL_SNAPSHOT_INTERVAL = 300;  // 每 300 帧 (10秒@30Hz) 一个全量快照
    private const int SNAPSHOT_RING_SIZE = 10;       // 环形缓冲区大小
    
    // ── 运行时状态 ───────────────────────────
    private readonly SnapshotData[] _ringBuffer = new SnapshotData[SNAPSHOT_RING_SIZE];
    private int _ringWriteIndex = 0;
    private SnapshotData _lastFullSnapshot; // 最近的全量快照 (用于生成增量)
    private uint _lastFullSnapshotFrame;
    
    /// <summary>
    /// 一个快照在内存中的表示
    /// </summary>
    private class SnapshotData
    {
        public SnapshotHeader Header;
        public byte[] RawData;      // 序列化后的二进制数据 (可能已压缩)
        public bool IsFull;         // 是全量还是增量
        public uint BaseFrame;      // 增量快照的基准帧 (全量快照的 BaseFrame = 自身帧号)
        
        public long DataSize => RawData?.Length ?? 0;
    }
    
    // ── 公共 API ─────────────────────────────
    
    /// <summary>
    /// 生成并保存一个快照。如果到了全量快照间隔，生成全量；否则生成增量。
    /// </summary>
    /// <param name="world">ECS 世界</param>
    /// <param name="frameNumber">当前帧号</param>
    public void SaveSnapshot(SimpleECSWorld world, uint frameNumber)
    {
        bool isFull = (frameNumber % FULL_SNAPSHOT_INTERVAL == 0);
        
        var snapshot = new SnapshotData
        {
            Header = new SnapshotHeader
            {
                Magic = SNAPSHOT_MAGIC,
                Version = SNAPSHOT_VERSION,
                Type = isFull ? SnapshotType.Full : SnapshotType.Delta,
                FrameNumber = frameNumber,
                TimestampMs = (ulong)DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            },
            IsFull = isFull,
        };
        
        if (isFull)
        {
            snapshot.RawData = SerializeFullSnapshot(world, ref snapshot.Header);
            _lastFullSnapshot = snapshot;
            _lastFullSnapshotFrame = frameNumber;
        }
        else
        {
            // 增量快照基于最近的全量快照
            if (_lastFullSnapshot == null)
            {
                // 还没有全量快照，降级为全量
                snapshot.RawData = SerializeFullSnapshot(world, ref snapshot.Header);
                snapshot.IsFull = true;
                _lastFullSnapshot = snapshot;
                _lastFullSnapshotFrame = frameNumber;
            }
            else
            {
                snapshot.BaseFrame = _lastFullSnapshotFrame;
                snapshot.RawData = SerializeDeltaSnapshot(world, _lastFullSnapshot, ref snapshot.Header);
            }
        }
        
        // 写入环形缓冲区
        _ringBuffer[_ringWriteIndex % SNAPSHOT_RING_SIZE] = snapshot;
        _ringWriteIndex++;
    }
    
    /// <summary>
    /// 查找并加载最近的快照 (包括增量链的展开)
    /// </summary>
    /// <param name="targetFrame">目标帧号 (0 表示最新)</param>
    /// <returns>快照的原始字节数据，可直接反序列化为世界状态</returns>
    public byte[] LoadNearestSnapshot(uint targetFrame = 0)
    {
        // 从环形缓冲区找最近的快照
        SnapshotData best = null;
        int bestIndex = -1;
        
        for (int i = 0; i < Math.Min(_ringWriteIndex, SNAPSHOT_RING_SIZE); i++)
        {
            var s = _ringBuffer[i];
            if (s == null) continue;
            
            // targetFrame=0 表示要最新的
            if (targetFrame == 0)
            {
                if (best == null || s.Header.FrameNumber > best.Header.FrameNumber)
                {
                    best = s;
                    bestIndex = i;
                }
            }
            else
            {
                // 找 ≤ targetFrame 的最大帧号快照
                if (s.Header.FrameNumber <= targetFrame)
                {
                    if (best == null || s.Header.FrameNumber > best.Header.FrameNumber)
                    {
                        best = s;
                        bestIndex = i;
                    }
                }
            }
        }
        
        if (best == null)
            return null;
        
        // 如果是增量快照，需要展开
        if (best.Header.Type == SnapshotType.Delta)
        {
            // 1. 找到基准的全量快照
            var baseSnapshot = FindFullSnapshot(best.BaseFrame);
            if (baseSnapshot == null)
                return best.RawData;  // 降级：单独返回增量数据，由调用者处理
            
            // 2. 从基准快照开始，收集到目标快照的所有增量
            var deltaChain = CollectDeltaChain(baseSnapshot.Header.FrameNumber, best.Header.FrameNumber);
            
            // 3. 展开链：基准 + Δ1 + Δ2 + ... + ΔN → 完整状态
            return ApplyDeltaChain(baseSnapshot.RawData, deltaChain);
        }
        
        return best.RawData;
    }
    
    // ── 序列化实现 ─────────────────────────
    
    /// <summary>
    /// 序列化完整的 ECS 世界为二进制快照
    /// </summary>
    private byte[] SerializeFullSnapshot(SimpleECSWorld world, ref SnapshotHeader header)
    {
        using var ms = new MemoryStream(1024 * 1024); // 1MB 初始容量
        using var writer = new BinaryWriter(ms);
        
        // 跳过 Header 位置 (稍后回填)
        writer.Seek(64, SeekOrigin.Begin);
        
        // 1. 收集所有 Archetype
        var archetypes = world.GetAllArchetypes();
        header.ArchetypeCount = (ushort)archetypes.Length;
        
        // 2. 写入 Archetype Table
        long tableStart = ms.Position;
        long dataSectionOffset = tableStart + archetypes.Length * (8 + 4 + 2); // 预估
        
        // 先预留 Table 空间
        writer.Seek((int)dataSectionOffset, SeekOrigin.Begin);
        
        var componentMetasList = new System.Collections.Generic.List<ComponentMeta[]>();
        
        foreach (var archetype in archetypes)
        {
            var componentTypes = archetype.GetComponentTypes();
            var metas = new ComponentMeta[componentTypes.Length];
            
            for (int c = 0; c < componentTypes.Length; c++)
            {
                var compType = componentTypes[c];
                var columnData = archetype.GetComponentColumnRaw(compType);
                
                metas[c] = new ComponentMeta
                {
                    TypeHash = compType.TypeHash,
                    DataOffset = (uint)ms.Position,
                    DataSize = (uint)columnData.Length,
                };
                
                // 直接写入列数据 (已经是连续的 byte[])
                writer.Write(columnData);
            }
            
            componentMetasList.Add(metas);
        }
        
        long dataEnd = ms.Position;
        
        // 3. 回填 Archetype Table
        writer.Seek((int)tableStart, SeekOrigin.Begin);
        for (int a = 0; a < archetypes.Length; a++)
        {
            var archetype = archetypes[a];
            var metas = componentMetasList[a];
            
            writer.Write(archetype.Hash);
            writer.Write((uint)archetype.EntityCount);
            writer.Write((ushort)metas.Length);
            
            foreach (var meta in metas)
            {
                writer.Write(meta.TypeHash);
                writer.Write(meta.DataOffset);
                writer.Write(meta.DataSize);
            }
        }
        
        // 4. 回填 Header
        header.TotalEntities = archetypes.Sum(a => a.EntityCount);
        ms.Seek(0, SeekOrigin.Begin);
        WriteHeader(writer, header);
        
        // 5. 获取完整 buffer
        byte[] rawData = new byte[dataEnd];
        ms.Seek(0, SeekOrigin.Begin);
        ms.Read(rawData, 0, (int)dataEnd);
        
        return CompressIfNeeded(rawData, ref header);
    }
    
    /// <summary>
    /// 序列化增量快照: 比较当前世界与基准快照的差异
    /// </summary>
    private byte[] SerializeDeltaSnapshot(SimpleECSWorld world, SnapshotData baseSnapshot, ref SnapshotHeader header)
    {
        // 增量快照格式:
        // [Header 64B] [ArchetypeCount: ushort] [for each changed archetype-chunk: chunkIndex|changedByteRange|newData]
        //
        // 简化实现: 对每个 Archetype 的每列做 memcmp
        // 只存储变化的字节范围 + 新数据
        
        using var ms = new MemoryStream(256 * 1024);
        using var writer = new BinaryWriter(ms);
        
        writer.Seek(64, SeekOrigin.Begin);
        
        var archetypes = world.GetAllArchetypes();
        ushort changedArchetypeCount = 0;
        
        // 先写一个占位的 changedArchetypeCount (稍后回填)
        long countPos = ms.Position;
        writer.Write((ushort)0);
        
        // 需要解析基准快照以进行比较 (简化: 这里假设 benchmark 已解析)
        // 实际实现中会维护一个 byte[][] 的上一帧数据用于快速 memcmp
        var prevData = ParseSnapshotData(baseSnapshot);
        
        for (int a = 0; a < archetypes.Length; a++)
        {
            var archetype = archetypes[a];
            var componentTypes = archetype.GetComponentTypes();
            
            for (int c = 0; c < componentTypes.Length; c++)
            {
                var compType = componentTypes[c];
                var currentData = archetype.GetComponentColumnRaw(compType);
                
                // 从 prevData 获取对应的上一帧数据
                byte[] previousData = prevData?.GetColumn(a, compType.TypeHash);
                
                if (previousData == null || currentData.Length != previousData.Length)
                {
                    // 新增的列或长度变化 → 全量写
                    writer.Write((uint)a);                    // archetypeIndex
                    writer.Write(compType.TypeHash);         // componentHash
                    writer.Write(0);                         // offset = 0 (全量)
                    writer.Write(currentData.Length);        // length
                    writer.Write(currentData);
                    changedArchetypeCount++;
                    continue;
                }
                
                // 快速比较：找变化的字节范围
                var diffResult = FindDiffRange(currentData, previousData);
                if (diffResult.hasDiff)
                {
                    writer.Write((uint)a);
                    writer.Write(compType.TypeHash);
                    writer.Write(diffResult.offset);
                    writer.Write(diffResult.length);
                    writer.Write(currentData, diffResult.offset, diffResult.length);
                    changedArchetypeCount++;
                }
            }
        }
        
        // 回填 changedArchetypeCount
        long endPos = ms.Position;
        ms.Seek(countPos, SeekOrigin.Begin);
        writer.Write(changedArchetypeCount);
        
        // 回填 Header
        ms.Seek(0, SeekOrigin.Begin);
        WriteHeader(writer, header);
        
        byte[] rawData = new byte[endPos];
        ms.Seek(0, SeekOrigin.Begin);
        ms.Read(rawData, 0, (int)endPos);
        
        return CompressIfNeeded(rawData, ref header);
    }
    
    // ── 辅助方法 ───────────────────────────
    
    /// <summary>
    /// 快速查找两个字节数组的差异范围
    /// 使用向量化比较 (实际项目中应该用 SIMD)
    /// </summary>
    private (bool hasDiff, int offset, int length) FindDiffRange(byte[] current, byte[] previous)
    {
        int firstDiff = -1;
        int lastDiff = -1;
        
        // 向量化友好的逐字节扫描
        for (int i = 0; i < current.Length; i++)
        {
            if (current[i] != previous[i])
            {
                if (firstDiff == -1) firstDiff = i;
                lastDiff = i;
            }
        }
        
        if (firstDiff == -1)
            return (false, 0, 0);
        
        return (true, firstDiff, lastDiff - firstDiff + 1);
    }
    
    private byte[] CompressIfNeeded(byte[] data, ref SnapshotHeader header)
    {
        // LZ4 优先 (速度快)。这里用 DeflateStream 演示，生产环境建议 LZ4
        if (data.Length < 1024)
        {
            header.Compression = 0; // 太小不压缩
            return data;
        }
        
        using var ms = new MemoryStream();
        using (var deflate = new DeflateStream(ms, CompressionLevel.Fastest, leaveOpen: true))
        {
            deflate.Write(data, 0, data.Length);
        }
        
        byte[] compressed = ms.ToArray();
        if (compressed.Length < data.Length * 0.9f) // 至少省 10% 才用压缩
        {
            header.Compression = 1;
            return compressed;
        }
        
        header.Compression = 0;
        return data;
    }
    
    private void WriteHeader(BinaryWriter writer, SnapshotHeader header)
    {
        writer.Write(header.Magic);
        writer.Write(header.Version);
        writer.Write((byte)header.Type);
        writer.Write(header.FrameNumber);
        writer.Write(header.TimestampMs);
        writer.Write(header.TotalEntities);
        writer.Write(header.ArchetypeCount);
        writer.Write(header.Compression);
        // 补齐到 64 bytes
        byte[] padding = new byte[64 - 23]; // 23 = 已写入的字节数
        writer.Write(padding);
    }
    
    // ── 占位方法 (依赖具体 ECS 实现) ──────
    
    private SnapshotData FindFullSnapshot(uint baseFrame)
    {
        for (int i = 0; i < Math.Min(_ringWriteIndex, SNAPSHOT_RING_SIZE); i++)
        {
            var s = _ringBuffer[i];
            if (s != null && s.IsFull && s.Header.FrameNumber == baseFrame)
                return s;
        }
        return null;
    }
    
    private byte[][] CollectDeltaChain(uint baseFrame, uint targetFrame)
    {
        var chain = new System.Collections.Generic.List<byte[]>();
        for (int i = 0; i < Math.Min(_ringWriteIndex, SNAPSHOT_RING_SIZE); i++)
        {
            var s = _ringBuffer[i];
            if (s != null && !s.IsFull && s.BaseFrame == baseFrame 
                && s.Header.FrameNumber <= targetFrame)
            {
                chain.Add(s.RawData);
            }
        }
        chain.Sort((a, b) => BitConverter.ToUInt32(a, 6).CompareTo(BitConverter.ToUInt32(b, 6)));
        return chain.ToArray();
    }
    
    private byte[] ApplyDeltaChain(byte[] baseData, byte[][] deltaChain)
    {
        // 简化: 复制基准数据，按序应用每个 delta
        byte[] result = new byte[baseData.Length];
        Array.Copy(baseData, result, baseData.Length);
        
        foreach (var delta in deltaChain)
        {
            ApplyDelta(result, delta);
        }
        
        return result;
    }
    
    private void ApplyDelta(byte[] baseData, byte[] delta)
    {
        // 解析 delta 包并应用到 baseData
        // (实现省略，依赖具体的序列化格式)
    }
    
    private ParsedSnapshotData ParseSnapshotData(SnapshotData snapshot)
    {
        // 解析快照为可查询的列数据
        return null; // 简化
    }
    
    private class ParsedSnapshotData
    {
        public byte[] GetColumn(int archetypeIndex, uint componentHash) => null;
    }
    
    public void Dispose()
    {
    }
}

// ─────────────────────────────────────────────────
//  简化版 ECS World 接口 (展示快照系统如何集成) ──
// ─────────────────────────────────────────────────

/// <summary>
/// 简化版 ECS 世界，用于演示快照 API
/// 生产环境应使用 Unity.Entities.World
/// </summary>
public class SimpleECSWorld
{
    public ArchetypeInfo[] GetAllArchetypes()
    {
        // 返回所有 Archetype 的 meta + 列数据访问器
        return Array.Empty<ArchetypeInfo>();
    }
}

public class ArchetypeInfo
{
    public ulong Hash;
    public uint EntityCount;
    
    public ComponentTypeInfo[] GetComponentTypes() => Array.Empty<ComponentTypeInfo>();
    public byte[] GetComponentColumnRaw(ComponentTypeInfo type) => Array.Empty<byte>();
}

public class ComponentTypeInfo
{
    public uint TypeHash;
    public Type ManagedType;
}
```

### 6.2 C++ ECS World + System + 网络同步集成

```cpp
// ECSWorld.h
// 轻量级 ECS 框架 + 网络同步集成 (C++17)
// 适用于 Dedicated Server

#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <memory>
#include <functional>
#include <cstring>
#include <algorithm>
#include <span>

// ============================================================
// 基础类型定义
// ============================================================

using Entity = uint32_t;
constexpr Entity kInvalidEntity = 0xFFFFFFFF;

// Component 类型 ID (编译期生成)
using ComponentTypeId = uint32_t;

template<typename T>
ComponentTypeId GetComponentTypeId() {
    // 生产环境应用编译期哈希 (如 FNV-1a constexpr)
    // 这里用简化的静态计数器保证唯一性
    static const ComponentTypeId id = []{
        static ComponentTypeId counter = 0;
        return ++counter;
    }();
    return id;
}

// ============================================================
// Archetype: Component 组合的唯一标识
// ============================================================

struct ArchetypeId {
    uint64_t hash;  // Component 组合的哈希值
    uint32_t componentCount;
    ComponentTypeId componentIds[16]; // 支持最多 16 个 Component
    
    bool operator==(const ArchetypeId& other) const {
        if (hash != other.hash || componentCount != other.componentCount) return false;
        return std::memcmp(componentIds, other.componentIds, 
                          componentCount * sizeof(ComponentTypeId)) == 0;
    }
};

// ============================================================
// Chunk: 固定大小的内存块 (16KB) 存储一个 Archetype 的所有实体数据
// ============================================================

class ArchetypeChunk {
public:
    static constexpr size_t kChunkSize = 16 * 1024;  // 16KB
    static constexpr size_t kMaxEntities = 64;        // 取决于 Entity 大小
    
private:
    uint8_t m_data[kChunkSize];
    Entity m_entityIds[kMaxEntities];
    uint32_t m_count = 0;
    uint32_t m_freeList[kMaxEntities];
    uint32_t m_freeCount = 0;
    
    // 每个 Component 在 Chunk 内的偏移和大小
    struct ComponentLayout {
        ComponentTypeId typeId;
        uint32_t offset;   // 在 m_data 中的偏移
        uint32_t stride;   // 每个实体的字节数
    };
    std::vector<ComponentLayout> m_layout;
    
public:
    ArchetypeChunk(const std::vector<ComponentLayout>& layout) : m_layout(layout) {
        // 初始化 freeList: 所有位置都空闲
        for (uint32_t i = 0; i < kMaxEntities; i++)
            m_freeList[i] = i;
        m_freeCount = kMaxEntities;
    }
    
    // 添加实体: 返回 entity 在 Chunk 内的索引
    uint32_t AddEntity(Entity e) {
        if (m_freeCount == 0 || m_count >= kMaxEntities)
            return UINT32_MAX;
        
        uint32_t slot = m_freeList[--m_freeCount];
        m_entityIds[slot] = e;
        m_count++;
        return slot;
    }
    
    // 移除实体
    void RemoveEntity(uint32_t slotIndex) {
        m_freeList[m_freeCount++] = slotIndex;
        m_entityIds[slotIndex] = kInvalidEntity;
        m_count--;
    }
    
    // 获取某个 Component 列的原始指针
    template<typename T>
    T* GetComponentColumn(ComponentTypeId typeId) {
        for (const auto& layout : m_layout) {
            if (layout.typeId == typeId) {
                return reinterpret_cast<T*>(m_data + layout.offset);
            }
        }
        return nullptr;
    }
    
    // 获取完整的列数据 (用于序列化)
    std::span<const uint8_t> GetColumnRaw(ComponentTypeId typeId) const {
        for (const auto& layout : m_layout) {
            if (layout.typeId == typeId) {
                return std::span<const uint8_t>(
                    m_data + layout.offset, layout.stride * m_count);
            }
        }
        return {};
    }
    
    uint32_t GetCount() const { return m_count; }
    Entity GetEntityId(uint32_t idx) const { return m_entityIds[idx]; }
    
    // 复制整个 Chunk 数据 (用于快照)
    void CopyTo(ArchetypeChunk& dest) const {
        std::memcpy(dest.m_data, m_data, kChunkSize);
        std::memcpy(dest.m_entityIds, m_entityIds, sizeof(m_entityIds));
        dest.m_count = m_count;
        dest.m_freeCount = m_freeCount;
        std::memcpy(dest.m_freeList, m_freeList, sizeof(m_freeList));
    }
};

// ============================================================
// System 基类
// ============================================================

class SystemBase {
public:
    virtual ~SystemBase() = default;
    
    // 返回此 System 需要的 Component 组合
    virtual std::vector<ComponentTypeId> GetRequiredComponents() const = 0;
    
    // 每逻辑帧执行
    virtual void OnUpdate(float deltaTime, class ECSWorld& world) = 0;
    
    // System 名称 (用于调试和调度排序)
    virtual const char* GetName() const = 0;
    
    // SystemGroup 中的优先级 (越小越先执行)
    virtual int GetPriority() const { return 0; }
};

// ============================================================
// ECS World: 管理所有 Entity、Archetype、Chunk 和 System
// ============================================================

class ECSWorld {
public:
    // ── 实体管理 ─────────────────────────
    
    Entity CreateEntity() {
        Entity e = m_nextEntityId++;
        m_entityAlive[e] = true;
        return e;
    }
    
    void DestroyEntity(Entity e) {
        // 从它所在的 Archetype-Chunk 中移除
        auto it = m_entityLocation.find(e);
        if (it != m_entityLocation.end()) {
            auto [archetypeHash, chunkIdx, slotIdx] = it->second;
            auto& chunks = m_archetypeChunks[archetypeHash];
            if (chunkIdx < chunks.size()) {
                chunks[chunkIdx]->RemoveEntity(slotIdx);
            }
            m_entityLocation.erase(it);
        }
        m_entityAlive[e] = false;
    }
    
    bool IsAlive(Entity e) const {
        auto it = m_entityAlive.find(e);
        return it != m_entityAlive.end() && it->second;
    }
    
    // ── Component 操作 ───────────────────
    
    template<typename T>
    void AddComponent(Entity e, const T& value) {
        // 1. 计算新的 ArchetypeId
        // 2. 如果 Entity 已有 Archetype，从中移除
        // 3. 在新的 Archetype-Chunk 中分配位置
        // (简化实现省略详细逻辑)
        ComponentTypeId typeId = GetComponentTypeId<T>();
        m_componentStorage[typeId][e] = value;
    }
    
    template<typename T>
    T* GetComponent(Entity e) {
        ComponentTypeId typeId = GetComponentTypeId<T>();
        auto& map = m_componentStorage[typeId];
        auto it = map.find(e);
        return (it != map.end()) ? &it->second : nullptr;
    }
    
    // ── System 管理 ──────────────────────
    
    void RegisterSystem(std::unique_ptr<SystemBase> system) {
        m_systems.push_back(std::move(system));
    }
    
    // 按优先级排序 Systems (确保确定性执行顺序)
    void SortSystems() {
        std::sort(m_systems.begin(), m_systems.end(),
            [](const auto& a, const auto& b) {
                return a->GetPriority() < b->GetPriority();
            });
    }
    
    // 执行所有 System (每逻辑帧调用)
    void Update(float deltaTime) {
        for (auto& sys : m_systems) {
            sys->OnUpdate(deltaTime, *this);
        }
    }
    
    // ── 快照支持 ─────────────────────────
    
    std::vector<ArchetypeChunk*> GetAllChunks() {
        std::vector<ArchetypeChunk*> result;
        for (auto& [hash, chunks] : m_archetypeChunks) {
            for (auto& chunk : chunks) {
                result.push_back(chunk.get());
            }
        }
        return result;
    }
    
    uint32_t GetTotalEntityCount() const {
        uint32_t count = 0;
        for (const auto& [hash, chunks] : m_archetypeChunks)
            for (const auto& chunk : chunks)
                count += chunk->GetCount();
        return count;
    }
    
    // ── 增量检测: 获取自上次快照后变化的 Entity ──
    
    std::vector<Entity> GetDirtyEntities() {
        std::vector<Entity> dirty;
        for (auto& [e, isDirty] : m_dirtyFlags) {
            if (isDirty) {
                dirty.push_back(e);
                isDirty = false; // 清除标记
            }
        }
        return dirty;
    }
    
    template<typename T>
    void MarkDirty(Entity e) {
        m_dirtyFlags[e] = true;
    }
    
private:
    Entity m_nextEntityId = 1;
    std::unordered_map<Entity, bool> m_entityAlive;
    std::unordered_map<Entity, bool> m_dirtyFlags;
    
    // 简化的 Component 存储 (生产环境用 Archetype Chunk)
    // 格式: componentTypeId → (entityId → raw bytes)
    struct ComponentStorage {
        std::unordered_map<ComponentTypeId, 
            std::unordered_map<Entity, std::vector<uint8_t>>> storage;
        
        template<typename T>
        std::unordered_map<Entity, T>& GetOrCreate() {
            // 简化: 用 reinterpret_cast 不安全，生产环境用 type-erased storage
            static std::unordered_map<Entity, T> dummy;
            return dummy;
        }
    };
    
    // 生产环境的 Archetype-Chunk 存储
    std::unordered_map<uint64_t, std::vector<std::unique_ptr<ArchetypeChunk>>> m_archetypeChunks;
    std::unordered_map<Entity, std::tuple<uint64_t, uint32_t, uint32_t>> m_entityLocation;
    
    // 简化的 Component 存储
    std::unordered_map<ComponentTypeId, std::unordered_map<Entity, std::any>> m_componentStorage;
    
    // Systems
    std::vector<std::unique_ptr<SystemBase>> m_systems;
};

// ============================================================
// 具体 System 示例: 移动系统 (帧同步 + 状态同步混合)
// ============================================================

struct TransformComponent {
    float x = 0, y = 0, z = 0;
};

struct VelocityComponent {
    float vx = 0, vy = 0, vz = 0;
};

struct ReplicatedComponent {
    bool isReplicated = false;  // true = 走状态同步下发
    uint32_t lastReplicatedFrame = 0;
};

struct PlayerInput {
    float moveX = 0, moveY = 0;
    bool fire = false;
    uint8_t skillId = 0;
};

// 移动 System: 对所有 [Transform, Velocity] 实体更新位置
class MovementSystem : public SystemBase {
public:
    std::vector<ComponentTypeId> GetRequiredComponents() const override {
        return { GetComponentTypeId<TransformComponent>(),
                 GetComponentTypeId<VelocityComponent>() };
    }
    
    const char* GetName() const override { return "MovementSystem"; }
    int GetPriority() const override { return 10; }  // 在输入之后、物理之前
    
    void OnUpdate(float deltaTime, ECSWorld& world) override {
        // ECS 查询: 遍历所有同时有 Transform 和 Velocity 的实体
        // 在生产环境中，这应该是 Archetype 级别的列遍历
        // 这里用简化的 Component 访问
        
        // 实际 ECS 查询伪代码:
        // for (auto chunk : world.GetChunksForArchetype<Transform, Velocity>())
        //     ProcessChunk(chunk, deltaTime);
        
        // 简化: 遍历所有实体检查 Component
        for (Entity e = 1; e < 10000; e++) { // 简化范围
            if (!world.IsAlive(e)) continue;
            
            auto* transform = world.GetComponent<TransformComponent>(e);
            auto* velocity = world.GetComponent<VelocityComponent>(e);
            
            if (transform && velocity) {
                // 确定性定点数运算 (生产环境用定点数替代 float)
                transform->x += velocity->vx * deltaTime;
                transform->y += velocity->vy * deltaTime;
                transform->z += velocity->vz * deltaTime;
                
                // 标记为脏 (用于增量状态同步)
                world.MarkDirty<TransformComponent>(e);
            }
        }
    }
};

// ============================================================
// 网络同步 System: 增量序列化 + 广播
// ============================================================

struct NetworkConnection {
    uint32_t clientId;
    int socketFd;
    // ... socket 管理
};

class NetworkSyncSystem : public SystemBase {
private:
    std::vector<NetworkConnection> m_connections;
    uint32_t m_currentFrame = 0;
    
    // 上一帧的快照数据 (用于增量检测)
    std::vector<uint8_t> m_lastFrameSnapshot;
    
public:
    std::vector<ComponentTypeId> GetRequiredComponents() const override {
        return { GetComponentTypeId<ReplicatedComponent>() };
    }
    
    const char* GetName() const override { return "NetworkSyncSystem"; }
    int GetPriority() const override { return 90; }  // 最后执行
    
    void OnUpdate(float deltaTime, ECSWorld& world) override {
        m_currentFrame++;
        
        // 第一步: 收集脏 Entity
        auto dirtyEntities = world.GetDirtyEntities();
        
        // 第二步: 为每个脏实体序列化 Replicated Components
        std::vector<uint8_t> frameData;
        SerializeDirtyEntities(world, dirtyEntities, frameData);
        
        // 第三步: 生成快照 (用于断线重连)
        if (m_currentFrame % 300 == 0) {
            SaveFullSnapshot(world);
        }
        
        // 第四步: 广播状态更新到所有连接
        for (auto& conn : m_connections) {
            SendFrameData(conn, m_currentFrame, frameData);
        }
    }
    
private:
    void SerializeDirtyEntities(ECSWorld& world, 
                                const std::vector<Entity>& dirty,
                                std::vector<uint8_t>& out) {
        // 简单二进制格式: [entityCount:u16] [for each: entityId:u32 componentMask:u32 data...]
        uint16_t count = static_cast<uint16_t>(dirty.size());
        out.insert(out.end(), reinterpret_cast<uint8_t*>(&count), 
                   reinterpret_cast<uint8_t*>(&count) + 2);
        
        for (Entity e : dirty) {
            // 写入 Entity ID
            out.insert(out.end(), reinterpret_cast<const uint8_t*>(&e),
                       reinterpret_cast<const uint8_t*>(&e) + 4);
            
            // 写入所有 Replicated Component 的数据
            uint32_t mask = 0;
            size_t maskOffset = out.size();
            out.resize(out.size() + 4); // 预留 mask 位置
            
            // Transform
            if (auto* t = world.GetComponent<TransformComponent>(e)) {
                mask |= 1 << 0;
                out.insert(out.end(), reinterpret_cast<uint8_t*>(t),
                           reinterpret_cast<uint8_t*>(t) + sizeof(TransformComponent));
            }
            
            // 更多 Component 的序列化...
            
            // 回填 mask
            std::memcpy(out.data() + maskOffset, &mask, 4);
        }
    }
    
    void SaveFullSnapshot(ECSWorld& world) {
        // 序列化所有 Archetype 的完整列数据
        // (调用 MemorySnapshotManager 或等效逻辑)
    }
    
    void SendFrameData(const NetworkConnection& conn, 
                       uint32_t frameNumber, 
                       const std::vector<uint8_t>& data) {
        // 通过 UDP/RUDP Socket 发送帧数据
        // 包格式: [frameNumber:u32] [dataSize:u16] [data...]
        (void)conn; (void)frameNumber; (void)data;
    }
};

// ============================================================
// DS 主循环: 集成 ECS World + System + 网络
// ============================================================

class DedicatedServer {
private:
    ECSWorld m_world;
    uint32_t m_frameNumber = 0;
    static constexpr float kFixedDeltaTime = 1.0f / 30.0f; // 30Hz
    
public:
    void Initialize() {
        // 注册 System (按优先级从小到大执行)
        m_world.RegisterSystem(std::make_unique<MovementSystem>());
        m_world.RegisterSystem(std::make_unique<NetworkSyncSystem>());
        // ... 更多 System
        
        m_world.SortSystems();
    }
    
    void RunFrame() {
        // 固定时间步
        m_world.Update(kFixedDeltaTime);
        m_frameNumber++;
    }
    
    void Run() {
        using Clock = std::chrono::steady_clock;
        auto nextFrameTime = Clock::now();
        
        while (true) {
            RunFrame();
            
            // 追赶机制: 如果执行超时，下一帧立即开始
            nextFrameTime += std::chrono::microseconds(
                static_cast<int64_t>(kFixedDeltaTime * 1'000'000));
            
            auto now = Clock::now();
            if (now < nextFrameTime) {
                std::this_thread::sleep_until(nextFrameTime);
            } else {
                // 超时了！立即追赶，不 sleep
                nextFrameTime = now;
            }
        }
    }
};
```

### 6.3 C# RoomPool 多局管理器

```csharp
// RoomPool.cs
// 单进程多战斗的 Room 池管理器
// 负责 Room 的分配、回收、崩溃隔离和负载上报

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

/// <summary>
/// Room 配置
/// </summary>
public class RoomConfig
{
    public uint RoomId;
    public RoomType Type;               // 战斗类型
    public int MaxPlayers;
    public string MapName;
    public Dictionary<uint, PlayerInfo> Players;
}

public enum RoomType
{
    PvE_Casual = 0,     // 休闲 PvE (最少资源)
    PvP_2v2 = 1,        // 2v2 对战
    PvP_5v5 = 2,        // 5v5 排位
    Tournament = 3,     // 锦标赛 (最高优先级)
}

public struct PlayerInfo
{
    public uint PlayerId;
    public string Name;
    public string Token; // 鉴权 token
}

// ────────────────────────────────────────────────
// Room 状态机
// ────────────────────────────────────────────────

public enum RoomState
{
    Idle,       // 等待玩家加入
    Loading,    // 加载资源
    Fighting,   // 战斗中
    Settle,     // 结算
    Destroying, // 正在销毁
    Crashed,    // 异常崩溃
}

// ────────────────────────────────────────────────
// 单个 Room 实例
// ────────────────────────────────────────────────

public class GameRoom : IDisposable
{
    public uint RoomId { get; }
    public RoomType Type { get; }
    public RoomState State { get; private set; } = RoomState.Idle;
    public DateTime CreatedAt { get; } = DateTime.UtcNow;
    
    // 核心子系统 (每个 Room 独立)
    private SimpleECSWorld _ecsWorld;
    private RoomPhysicsWorld _physicsWorld;
    private FrameSyncChannel _frameChannel;
    private StateSyncChannel _stateChannel;
    private MemorySnapshotManager _snapshotManager;
    
    // 玩家管理
    private readonly Dictionary<uint, PlayerSlot> _players = new();
    
    // 帧驱动
    private uint _frameNumber;
    private float _logicAccumulator;
    private const float LOGIC_DT = 1f / 30f; // 30Hz 逻辑帧
    
    // 超时管理
    private readonly Stopwatch _fightingTimer = new();
    private static readonly TimeSpan MaxFightingTime = TimeSpan.FromMinutes(30);
    private static readonly TimeSpan MaxIdleTime = TimeSpan.FromMinutes(5);
    
    // 统计
    public uint TotalFrames { get; private set; }
    public long TotalBytesSent { get; private set; }
    public long TotalBytesReceived { get; private set; }
    
    public GameRoom(uint roomId, RoomConfig config)
    {
        RoomId = roomId;
        Type = config.Type;
        
        foreach (var kvp in config.Players)
            _players[kvp.Key] = new PlayerSlot { Info = kvp.Value };
    }
    
    /// <summary>
    /// 初始化 Room: 创建 ECS World、物理世界、网络通道
    /// </summary>
    public void Initialize()
    {
        State = RoomState.Loading;
        
        // 1. ECS World
        _ecsWorld = new SimpleECSWorld();
        // 注册 System... (省略)
        
        // 2. 物理世界 (每个 Room 独立 PxScene)
        _physicsWorld = new RoomPhysicsWorld();
        _physicsWorld.Initialize();
        
        // 3. 网络通道
        _frameChannel = new FrameSyncChannel(RoomId);
        _stateChannel = new StateSyncChannel(RoomId);
        
        // 4. 快照管理
        _snapshotManager = new MemorySnapshotManager();
        
        _frameNumber = 0;
        _logicAccumulator = 0f;
        
        State = RoomState.Fighting;
        _fightingTimer.Restart();
    }
    
    /// <summary>
    /// 每逻辑帧 Tick (由 RoomPool 调用，已包裹 try-catch)
    /// </summary>
    public void Tick(float renderDeltaTime)
    {
        if (State != RoomState.Fighting) return;
        
        // 逻辑帧频率控制 (追赶机制)
        _logicAccumulator += renderDeltaTime;
        bool hasLogicalFrame = false;
        
        while (_logicAccumulator >= LOGIC_DT)
        {
            _logicAccumulator -= LOGIC_DT;
            
            // 1. 收集输入
            _frameChannel.CollectInputs(_frameNumber);
            
            // 2. 执行逻辑
            _ecsWorld.Update(LOGIC_DT);          // ECS System 管线
            _physicsWorld.Simulate(LOGIC_DT);    // 物理模拟
            
            // 3. 快照
            _snapshotManager.SaveSnapshot(_ecsWorld, _frameNumber);
            
            // 4. 广播
            _frameChannel.BroadcastFrame(_frameNumber);
            _stateChannel.BroadcastDirtyEntities(_ecsWorld.GetDirtyEntities());
            
            _frameNumber++;
            TotalFrames++;
            hasLogicalFrame = true;
            
            // 达到单个 Render 帧的逻辑帧上限 (防止无限追赶)
            if (_frameNumber - (_frameNumber - (uint)(_logicAccumulator / LOGIC_DT)) > 5)
                break;
        }
        
        if (!hasLogicalFrame) return;
        
        // 超时检查
        if (_fightingTimer.Elapsed > MaxFightingTime)
        {
            ForceSettle("timeout");
        }
    }
    
    /// <summary>
    /// 添加玩家
    /// </summary>
    public void AddPlayer(uint playerId, PlayerInfo info)
    {
        if (!_players.ContainsKey(playerId))
            _players[playerId] = new PlayerSlot { Info = info };
    }
    
    /// <summary>
    /// 玩家断线处理
    /// </summary>
    public void OnPlayerDisconnect(uint playerId)
    {
        if (_players.TryGetValue(playerId, out var slot))
        {
            slot.IsConnected = false;
            slot.DisconnectTime = DateTime.UtcNow;
        }
        
        // 检查是否所有玩家都断线
        if (_players.Values.All(p => !p.IsConnected))
        {
            // 所有玩家断线 60 秒后自动结算
            Task.Delay(TimeSpan.FromSeconds(60)).ContinueWith(_ =>
            {
                if (_players.Values.All(p => !p.IsConnected))
                    ForceSettle("all_disconnected");
            });
        }
    }
    
    /// <summary>
    /// 玩家重连: 下发最新快照
    /// </summary>
    public byte[] GetReconnectSnapshot(uint playerId)
    {
        var snapshotData = _snapshotManager.LoadNearestSnapshot();
        // 标记该玩家已重连
        if (_players.TryGetValue(playerId, out var slot))
            slot.IsConnected = true;
        
        return snapshotData;
    }
    
    /// <summary>
    /// 强制结算 (超时/维护/异常)
    /// </summary>
    public void ForceSettle(string reason)
    {
        State = RoomState.Settle;
        Console.WriteLine($"[Room {RoomId}] Settling: {reason}");
        // 保存录像、通知客户端...
        // 然后转入 Destroying
        State = RoomState.Destroying;
    }
    
    /// <summary>
    /// 异常关闭 (try-catch 捕获后调用)
    /// </summary>
    public void EmergencyShutdown(Exception ex)
    {
        State = RoomState.Crashed;
        Console.Error.WriteLine($"[Room {RoomId}] CRASHED: {ex}");
        
        // 通知所有客户端 "战斗异常终止"
        foreach (var slot in _players.Values)
        {
            TryNotifyPlayerCrash(slot);
        }
    }
    
    private void TryNotifyPlayerCrash(PlayerSlot slot)
    {
        // 发送 "房间崩溃" 通知到客户端
    }
    
    public void Dispose()
    {
        _physicsWorld?.Dispose();
        _frameChannel?.Dispose();
        _stateChannel?.Dispose();
        _snapshotManager?.Dispose();
    }
}

internal class PlayerSlot
{
    public PlayerInfo Info;
    public bool IsConnected = true;
    public DateTime DisconnectTime;
}

// ────────────────────────────────────────────────
// 占位类型 (实际实现见教程 24)
// ────────────────────────────────────────────────

internal class RoomPhysicsWorld
{
    public void Initialize() { }
    public void Simulate(float dt) { }
    public void Dispose() { }
}

internal class FrameSyncChannel
{
    public FrameSyncChannel(uint roomId) { }
    public void CollectInputs(uint frame) { }
    public void BroadcastFrame(uint frame) { }
    public void Dispose() { }
}

internal class StateSyncChannel
{
    public StateSyncChannel(uint roomId) { }
    public void BroadcastDirtyEntities(System.Collections.Generic.List<Entity> _) { }
    public void Dispose() { }
}

// ────────────────────────────────────────────────
// RoomPool: 管理所有 Room 的生命周期
// ────────────────────────────────────────────────

public class RoomPool : IDisposable
{
    // ── 配置 ─────────────────────────────────
    private readonly int _maxRooms;
    private readonly int _maxRoomsPerType;  // 每种类型的最大 Room 数
    private readonly float _tickInterval;    // 主循环间隔
    
    // ── Room 存储 ────────────────────────────
    private readonly Dictionary<uint, GameRoom> _activeRooms = new();
    private readonly List<uint> _pendingDestroy = new();
    private readonly object _lock = new();
    
    // ── 类型配额管理 ─────────────────────────
    private readonly Dictionary<RoomType, int> _typeRoomCount = new();
    
    // ── 负载指标 ─────────────────────────────
    private float _cpuUsage;
    private float _memoryUsageMB;
    
    // ── 事件 ─────────────────────────────────
    public event Action<uint, string> OnRoomCrashed;
    public event Action<uint> OnRoomDestroyed;
    
    // 负载指标 (供 DSA 查询)
    public (float cpu, float memory, int activeRooms) GetLoadMetrics()
    {
        lock (_lock)
            return (_cpuUsage, _memoryUsageMB, _activeRooms.Count);
    }
    
    // 实际 Tick 频率 (用于过载检测)
    public int TicksPerSecond { get; private set; }
    private int _tickCounter;
    private float _tpsTimer;
    
    public RoomPool(int maxRooms = 50, float tickInterval = 0.033f)
    {
        _maxRooms = maxRooms;
        _tickInterval = tickInterval;
        
        foreach (RoomType type in Enum.GetValues<RoomType>())
            _typeRoomCount[type] = 0;
    }
    
    // ============================================================
    // Room 生命周期管理
    // ============================================================
    
    /// <summary>
    /// 创建新 Room。返回 null 表示容量已满。
    /// </summary>
    public GameRoom CreateRoom(RoomConfig config)
    {
        lock (_lock)
        {
            if (_activeRooms.Count >= _maxRooms)
                return null;
            
            var room = new GameRoom(config.RoomId, config);
            _activeRooms[config.RoomId] = room;
            _typeRoomCount[config.Type] = _typeRoomCount.GetValueOrDefault(config.Type) + 1;
            
            // 异步初始化 (避免阻塞主循环)
            Task.Run(() => room.Initialize());
            
            Console.WriteLine($"[RoomPool] Created Room {config.RoomId} (Total: {_activeRooms.Count}/{_maxRooms})");
            return room;
        }
    }
    
    /// <summary>
    /// 获取 Room (用于网络层将包路由到正确的 Room)
    /// </summary>
    public GameRoom GetRoom(uint roomId)
    {
        lock (_lock)
        {
            _activeRooms.TryGetValue(roomId, out var room);
            return room;
        }
    }
    
    /// <summary>
    /// 标记 Room 待销毁 (异步清理，避免阻塞)
    /// </summary>
    public void DestroyRoom(uint roomId)
    {
        lock (_lock)
        {
            if (_activeRooms.ContainsKey(roomId))
                _pendingDestroy.Add(roomId);
        }
    }
    
    /// <summary>
    /// 获取指定类型的当前 Room 数
    /// </summary>
    public int GetRoomCount(RoomType type)
    {
        lock (_lock)
        {
            return _typeRoomCount.GetValueOrDefault(type);
        }
    }
    
    // ============================================================
    // 主驱动循环
    // ============================================================
    
    private CancellationTokenSource _cts;
    
    /// <summary>
    /// 启动 RoomPool 主循环 (通常在独立线程)
    /// </summary>
    public void Start()
    {
        _cts = new CancellationTokenSource();
        Task.Run(() => MainLoop(_cts.Token));
    }
    
    public void Stop()
    {
        _cts?.Cancel();
    }
    
    private async Task MainLoop(CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        double nextTickTime = sw.Elapsed.TotalSeconds;
        
        while (!ct.IsCancellationRequested)
        {
            double now = sw.Elapsed.TotalSeconds;
            
            // 固定时间步
            if (now >= nextTickTime)
            {
                TickAllRooms((float)(now - (nextTickTime - _tickInterval)));
                nextTickTime += _tickInterval;
                
                _tickCounter++;
                _tpsTimer += (float)(now - (nextTickTime - _tickInterval));
                if (_tpsTimer >= 1.0f)
                {
                    TicksPerSecond = _tickCounter;
                    _tickCounter = 0;
                    _tpsTimer -= 1.0f;
                }
            }
            
            // 清理待销毁 Room
            ProcessPendingDestroy();
            
            // 更新负载指标
            UpdateLoadMetrics();
            
            // 避免忙等
            double sleepTime = nextTickTime - sw.Elapsed.TotalSeconds;
            if (sleepTime > 0)
                await Task.Delay(TimeSpan.FromSeconds(Math.Min(sleepTime, 0.1)), ct);
        }
    }
    
    /// <summary>
    /// Tick 所有活跃 Room (核心: 崩溃隔离)
    /// </summary>
    private void TickAllRooms(float deltaTime)
    {
        List<GameRoom> rooms;
        lock (_lock)
        {
            rooms = _activeRooms.Values.ToList();
        }
        
        foreach (var room in rooms)
        {
            try
            {
                if (room.State == RoomState.Fighting)
                    room.Tick(deltaTime);
            }
            catch (Exception ex)
            {
                // ★ 崩溃隔离 ★
                // 一个 Room 崩溃不影响其他 Room
                Console.Error.WriteLine($"[RoomPool] Room {room.RoomId} crashed during Tick: {ex}");
                
                room.EmergencyShutdown(ex);
                OnRoomCrashed?.Invoke(room.RoomId, ex.Message);
                
                // 调度销毁
                DestroyRoom(room.RoomId);
            }
        }
    }
    
    /// <summary>
    /// 销毁待清理的 Room
    /// </summary>
    private void ProcessPendingDestroy()
    {
        List<uint> toDestroy;
        lock (_lock)
        {
            toDestroy = _pendingDestroy.ToList();
            _pendingDestroy.Clear();
        }
        
        foreach (var roomId in toDestroy)
        {
            GameRoom room;
            lock (_lock)
            {
                if (!_activeRooms.TryGetValue(roomId, out room))
                    continue;
                _activeRooms.Remove(roomId);
                _typeRoomCount[room.Type] = Math.Max(0, _typeRoomCount.GetValueOrDefault(room.Type) - 1);
            }
            
            try
            {
                room.Dispose();
                OnRoomDestroyed?.Invoke(roomId);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[RoomPool] Error disposing Room {roomId}: {ex}");
            }
            
            Console.WriteLine($"[RoomPool] Destroyed Room {roomId} (Total: {_activeRooms.Count}/{_maxRooms})");
        }
    }
    
    /// <summary>
    /// 更新负载指标 (CPU/内存)
    /// </summary>
    private void UpdateLoadMetrics()
    {
        // CPU 使用率: 通过 Process 获取
        using var process = Process.GetCurrentProcess();
        _cpuUsage = (float)(process.TotalProcessorTime.TotalMilliseconds / 
                   (Environment.ProcessorCount * (DateTime.UtcNow - process.StartTime.ToUniversalTime()).TotalMilliseconds)) * 100f;
        _memoryUsageMB = process.WorkingSet64 / (1024f * 1024f);
    }
    
    public void Dispose()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        
        lock (_lock)
        {
            foreach (var room in _activeRooms.Values)
            {
                try { room.Dispose(); } catch { }
            }
            _activeRooms.Clear();
        }
    }
}
```

---

## 7. 练习

### 练习 1：实现 ECS 快照的增量 Diff（基础）

**目标**：在 `MemorySnapshotManager` 的基础上，补全 `FindDiffRange` 方法的 SIMD 加速版本。

**要求**：
1. 使用 `System.Numerics.Vector<byte>` 实现向量化比较
2. 对 4096 字节的列，比较 SIMD 版本和朴素逐字节扫描版本的速度
3. 输出加速比

**提示**：
```csharp
// 向量化比较框架
var va = new Vector<byte>(current, offset);
var vb = new Vector<byte>(previous, offset);
var eq = Vector.Equals(va, vb);  // 返回每个元素是否相等
// eq 中值为 0 的 lane 就是差异位置
```

**预期结果**：SIMD 版本比逐字节扫描快 4-8 倍（取决于 CPU 的 SIMD 宽度）。

### 练习 2：设计带优先级的 Room 调度器（进阶）

**目标**：在高负载时，不同优先级（赛事 > 排位 > 休闲）的 Room 应获得不同的 CPU 时间片。

**要求**：
1. 修改 `RoomPool.TickAllRooms()`，使高优先级 Room 获得更多 Tick 次数
2. 设计优先级权重: Tournament=3x, PvP_5v5=2x, PvP_2v2=1x, PvE_Casual=1x
3. 当系统过载（TicksPerSecond < 配置值）时，PvE_Casual 的 Room 降频（每 2-3 次主循环只 Tick 一次）
4. 确保在任何降频策略下，帧号仍然单调递增且帧间隔一致

**提示**：
```csharp
// 权重调度框架
private int _roundRobinCounter = 0;

void TickAllRoomsWeighted(float deltaTime)
{
    _roundRobinCounter++;
    
    foreach (var room in rooms)
    {
        int weight = GetPriorityWeight(room.Type);
        bool shouldTick = (_roundRobinCounter % weight) == 0;
        
        if (shouldTick)
            room.Tick(deltaTime);
    }
}
```

### 练习 3：从零实现进程池 + fork 快速拉起（挑战）

**目标**：设计一个 Linux 上基于 `fork()` 的快速 DS 进程池。

**要求**：
1. 父进程预加载引擎资源，`fork()` 出子进程作为 DS 实例
2. 父子进程通过 Unix Domain Socket 通信（分配 Room、回收 Room、心跳）
3. 子进程崩溃时，父进程检测并 fork 新进程替补
4. 用 C++ 或 C 实现，写出关键代码约 200 行

**提示**：
```cpp
// fork 框架
int main() {
    // 父进程: 加载引擎资源
    LoadEngineResources();  // 加载地图、实体模板、物理世界配置
    
    // 预热进程池
    std::vector<pid_t> pool;
    for (int i = 0; i < POOL_SIZE; i++) {
        pid_t pid = fork();
        if (pid == 0) {
            // 子进程: 进入 DS 主循环
            ChildMain(i);  // i = 子进程编号
            _exit(0);
        }
        pool.push_back(pid);
    }
    
    // 父进程: 监听分配请求，管理子进程
    ParentMain(pool);
}
```

---

## 8. 扩展阅读

| 资源 | 内容 |
|------|------|
| Unity DOTS 文档 — [`entities.unity.com`](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/index.html) | ECS 1.0 官方文档，Archetype、Chunk、System 详细说明 |
| Unreal Mass Entity — [`docs.unrealengine.com`](https://docs.unrealengine.com/5.0/en-US/overview-of-mass-entity-in-unreal-engine/) | UE5 Mass Entity 概述 |
| Mike Acton — "Data-Oriented Design and C++" (CppCon 2014) | DOD 经典演讲，ECS 背后的设计哲学 |
| Overwatch Gameplay Architecture (GDC 2017) | 守望先锋 ECS 架构，网络同步细节 |
| LZ4 压缩算法 — [`lz4.github.io/lz4`](https://lz4.github.io/lz4/) | 最快的压缩算法之一，适合实时快照 |
| Zstd — [`facebook.github.io/zstd`](https://facebook.github.io/zstd/) | 高压缩比，适合存档快照 |
| PhysX SDK — `PxScene` 隔离文档 | 多个 `PxScene` 实例在同一进程中如何隔离 |
| Linux `fork()` — `man 2 fork` | COW、文件描述符继承、信号处理 |

---

## 9. 常见陷阱

### 陷阱 1：ECS 不等于性能银弹

**问题**：以为只要用了 ECS，性能就自动好了。

**实际**：ECS 的缓存友好性只有在**列遍历**时才体现。如果你仍然按 Entity 逐个遍历（遍历一个 Entity 的所有 Component，再到下一个 Entity），那你只是把 OOP 的虚函数开销变成了手动索引——缓存行为没有改善。

**正确做法**：确保每个 System 只遍历它需要的 Component 列。`MovementSystem` 只碰 `Transform` 和 `Velocity`，不碰 `Health`、`Skill` 等无关列。

```cpp
// ❌ 按 Entity 遍历 → Cache 行为等同于 OOP
for (auto e : entities) {
    auto* t = world.Get<Transform>(e);   // 访问 Transform 列
    auto* v = world.Get<Velocity>(e);    // 访问 Velocity 列
    auto* h = world.Get<Health>(e);      // 也加载了 Health 列，污染 Cache
    t->x += v->vx * dt;
}

// ✅ 按列遍历 → 真正的 DOD
auto transforms = world.GetColumn<Transform>();
auto velocities = world.GetColumn<Velocity>();
for (size_t i = 0; i < count; i++) {
    transforms[i].x += velocities[i].vx * dt;
    // Health 列完全不碰，不污染 Cache
}
```

### 陷阱 2：快照频率过高导致 I/O 成为瓶颈

**问题**：每帧都做全量快照并写入磁盘。

**实际**：磁盘 I/O 延迟（即使是 SSD）是 10-100μs 级别。在 30Hz 逻辑帧（每帧 33ms）中，每帧写一次磁盘看似可行，但当 Room 数增加到 50 个时，50 × 一次磁盘写入 = I/O 争抢 → 部分 Room 的帧超时。

**正确做法**：
1. 快照先写入内存环形缓冲区（延迟 ~100ns）
2. 异步后台线程定期（每 5 秒或每 60 秒）将内存中的快照持久化到磁盘
3. 崩溃恢复优先从内存恢复（通过共享内存或 P2P DS 内存交换）
4. 只有内存中的快照全部丢失时才从磁盘恢复

### 陷阱 3：多 Room 共享状态导致 "Room 间串扰"

**问题**：两个 Room 的物理模拟出现奇怪的交互——一个 Room 的子弹"穿过"了另一个 Room 的地形。

**实际**：这通常是因为 `PxScene` 或其他全局状态没有正确隔离。检查：
1. 每个 Room 是否使用了独立的 `PxScene` 实例
2. 碰撞过滤回调（`PxSimulationFilterShader`）是否按 Room 做了隔离
3. 全局单例（如 `Physics.TolerancesScale`、`Time.time`）是否被多 Room 共享导致非确定性

**C# 中常见的串扰源**：
- `static` 字段——所有 Room 共享
- `[RuntimeInitializeOnLoadMethod]` —— 全局初始化
- Singleton MonoBehaviours —— 全局唯一实例

**正确做法**：每个 Room 持有所有状态的引用，零 `static` 可变字段。

### 陷阱 4：fork() 后的文件描述符泄漏

**问题**：`fork()` 后，子进程继承了父进程的所有文件描述符（Socket、文件句柄）。如果父进程打开了 100 个 TCP 连接，子进程也继承这 100 个 fd——导致端口占用、地址冲突。

**正确做法**：
```cpp
// fork() 后立即关闭不需要的 fd
pid_t pid = fork();
if (pid == 0) {
    // 子进程
    // 关闭从父进程继承的所有不相关 fd
    for (int fd = 3; fd < getdtablesize(); fd++) {
        if (fd != child_listen_socket && fd != parent_ipc_socket)
            close(fd);
    }
    ChildMain();
    _exit(0);
}
```

### 陷阱 5：GC 在服务端的杀伤力远大于客户端

**问题**：服务端对局持续 30 分钟，GC Gen2 触发时暂停 100ms+ → 6 帧延迟 → 玩家集体卡顿。

**实际**：客户端的一次 GC 暂停 50ms 只影响一个玩家（而且可以被渲染平滑掩盖）。服务端的一次 GC 暂停影响该进程内的所有 Room（50 个 Room × 10 玩家 = 500 人同时卡顿）。

**正确做法**：
1. 服务端 hot path 零分配（对象池 + `ArrayPool` + `struct`）
2. 开启 `GC.SuppressFinalize` + `GCSettings.LatencyMode = GCLatencyMode.SustainedLowLatency`
3. 监控 GC 触发频率：如果 > 1 次/分钟，立即排查分配热点
4. 必要时使用 `GC.TryStartNoGCRegion` 在帧循环内锁定 GC

---

> **学习检查清单**：
> - [ ] 能解释 ECS 的 Archetype 为什么对网络同步的序列化和增量检测友好
> - [ ] 能写出 ECS World 的 System 注册和调度框架
> - [ ] 能实现快照的二进制格式设计，区分全量/增量快照
> - [ ] 能实现崩溃恢复流程：检测 → 加载快照 → 重放输入 → 恢复运行
> - [ ] 能设计多 Room 并行的进程模型，含崩溃隔离和负载均衡
> - [ ] 能在 Unity Profiler / UE Insights 中定位网络同步的性能瓶颈
> - [ ] 能列出至少 3 种避免 GC 抖动的具体措施
> - [ ] 能解释 fork() 在 DS 进程池中的作用和注意事项
