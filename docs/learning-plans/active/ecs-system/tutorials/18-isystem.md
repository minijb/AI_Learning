---
title: "System 编写详解"
updated: 2026-06-05
---

# System 编写详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 3 小时
> 前置知识: IComponentData 详解（教程 17）、C# 泛型/特性

---

## 1. 概念讲解

### 为什么需要 System？

System 是 ECS 中的"处理器"——它只负责逻辑，不持有任何持久化状态（状态通过 `SystemState` 和组件存储）。一个 System 回答三个问题：

1. **查什么** — 通过 EntityQuery 或 SystemAPI.Query 筛选一组 Entity
2. **做什么** — 对筛选到的 Entity 执行变换逻辑
3. **何时做** — 由 SystemGroup 更新顺序决定

### SystemBase vs ISystem

| 特性 | SystemBase（旧式） | ISystem（新式，推荐） |
|------|-------------------|----------------------|
| 类型 | `partial class`（托管） | `partial struct`（非托管） |
| Burst 支持 | ❌ 不支持 | ✅ 支持 |
| 内存分配 | 托管堆（GC） | 无 GC |
| `Entities.ForEach` | ✅ 可用 | ❌ 不可用 |
| `SystemAPI.Query` | ✅ 可用 | ✅ 可用 |
| `IJobEntity` | ✅ 可用 | ✅ 可用 |
| `OnCreate/OnUpdate/OnDestroy` | 无 `ref` 参数 | `ref SystemState state` |
| 适用场景 | 需访问托管对象 | **所有新代码** |

**结论：所有新代码都应使用 ISystem。SystemBase 仅为兼容旧代码保留。**

### SystemState 的生命周期

```
World 创建
  └── System 实例化 → OnCreate(ref SystemState state)
         │
         ▼
    每帧: OnUpdate(ref SystemState state)
         │
         ▼
  World 销毁 → OnDestroy(ref SystemState state)
```

- **OnCreate**: 注册 `RequireForUpdate<T>()`，预构建 EntityQuery，分配持久化资源。
- **OnUpdate**: 主逻辑。读取输入、处理实体、写入输出。
- **OnDestroy**: 释放 NativeContainer、清理资源。

### 核心思想

**SystemAPI.Query** — 最简单直接的查询方式，在 `OnUpdate` 中用 `foreach` 遍历。适合简单场景。

**IJobEntity** — 将查询逻辑提取到独立的 Job 结构体中，自动并行化。适合批量处理。

**EntityQuery** — 手动构建查询，支持 `[WithAll]`、`[WithNone]`、`[WithChangeFilter]`。适合复杂筛选和 Job 调度。

**SystemGroup** — 组织 System 的层级容器，控制执行顺序。

---

## 2. 代码示例

### 2.1 SystemAPI.Query（最简单的查询方式）

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Mathematics;
using Unity.Transforms;

[BurstCompile]
public partial struct SimpleMovementSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        // 如果没有实体拥有 MoveSpeed 组件，此 System 不会运行
        state.RequireForUpdate<MoveSpeed>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;

        // foreach 遍历所有符合条件的 Entity
        foreach (var (transform, speed) in
                 SystemAPI.Query<RefRW<LocalTransform>, RefRO<MoveSpeed>>())
        {
            float3 forward = math.forward(transform.ValueRO.Rotation);
            transform.ValueRW.Position += forward * speed.ValueRO.MetersPerSecond * deltaTime;
        }
    }

    [BurstCompile]
    public void OnDestroy(ref SystemState state) { }
}
```

### 2.2 IJobEntity（并行批处理）

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Jobs;
using Unity.Mathematics;
using Unity.Transforms;

// Job 定义
[BurstCompile]
public partial struct MoveForwardJob : IJobEntity
{
    public float DeltaTime; // 从外部传入

    // Execute 方法参数 = 查询条件
    void Execute(ref LocalTransform transform, in MoveSpeed speed)
    {
        float3 forward = math.forward(transform.Rotation);
        transform.Position += forward * speed.MetersPerSecond * DeltaTime;
    }
}

// 调度 Job 的 System
[BurstCompile]
public partial struct MovementJobSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        state.RequireForUpdate<MoveSpeed>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 创建并调度 Job
        var job = new MoveForwardJob
        {
            DeltaTime = SystemAPI.Time.DeltaTime
        };

        // ScheduleParallel 自动将工作分配到所有可用核心
        JobHandle handle = job.ScheduleParallel(state.Dependency);
        state.Dependency = handle; // 链式依赖
    }

    [BurstCompile]
    public void OnDestroy(ref SystemState state) { }
}
```

### 2.3 [WithAll]、[WithNone]、[WithChangeFilter]

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Transforms;

// 标签定义
public struct PlayerTag : IComponentData { }
public struct EnemyTag : IComponentData { }
public struct DeadTag : IComponentData { }

[BurstCompile]
public partial struct EnemyMovementJob : IJobEntity
{
    public float DeltaTime;
    public float3 PlayerPosition;

    // [WithAll] — 必须拥有该组件
    // [WithNone] — 必须没有该组件
    // [WithChangeFilter] — 仅在指定组件的值发生变化时才处理
    [WithAll(typeof(EnemyTag))]
    [WithNone(typeof(DeadTag))]
    void Execute(
        ref LocalTransform transform,
        in MoveSpeed speed,
        [ChunkIndexInQuery] int chunkIndex,
        [EntityIndexInChunk] int entityIndex)
    {
        float3 direction = math.normalize(PlayerPosition - transform.Position);
        transform.Position += direction * speed.MetersPerSecond * DeltaTime;
        transform.Rotation = quaternion.LookRotationSafe(direction, math.up());
    }
}

[BurstCompile]
public partial struct EnemySystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 找到玩家位置
        float3 playerPos = float3.zero;
        foreach (var transform in SystemAPI.Query<RefRO<LocalTransform>>()
                     .WithAll<PlayerTag>())
        {
            playerPos = transform.ValueRO.Position;
            break;
        }

        var job = new EnemyMovementJob
        {
            DeltaTime = SystemAPI.Time.DeltaTime,
            PlayerPosition = playerPos
        };

        state.Dependency = job.ScheduleParallel(state.Dependency);
    }
}
```

### 2.4 WithChangeFilter — 仅处理变化的实体

```csharp
using Unity.Burst;
using Unity.Entities;

public struct DirtyFlag : IComponentData { }

[BurstCompile]
public partial struct ChangeDetectionJob : IJobEntity
{
    // localToWorld 变化时才处理
    // 使用 ChangeFilter 版本需要在参数列表中引用该组件
    void Execute(in LocalToWorld localToWorld, [ChangedFilter] in Health health)
    {
        // 只有在 health 值发生变化时才进入这里
        // 这很高效——跳过大量未变化的实体
    }
}

// 或者使用 EntityQuery 的版本：
[BurstCompile]
public partial struct ChangeFilterSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 手动构建 EntityQuery 并使用 ChangeFilter
        var query = SystemAPI.QueryBuilder()
            .WithAll<Health, LocalTransform>()
            .WithChangeFilter<Health>() // 仅 Health 变化时才匹配
            .Build();

        // 计算匹配的 Chunk 数量
        int chunkCount = query.CalculateChunkCount();

        // 如无匹配则跳过
        if (chunkCount == 0) return;

        // 手动遍历 Chunk...
    }
}
```

### 2.5 EntityQuery 的手动构建

适合需要精细控制查询的场景：

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Collections;

[BurstCompile]
public partial struct ManualQuerySystem : ISystem
{
    private EntityQuery _enemyQuery;
    private EntityQuery _deadEnemyQuery;

    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        // 方式一：通过 SystemAPI 构建
        _enemyQuery = SystemAPI.QueryBuilder()
            .WithAll<EnemyTag, Health, LocalTransform>()
            .WithNone<DeadTag>()
            .Build();

        // 方式二：通过 EntityQueryBuilder（更底层）
        _deadEnemyQuery = new EntityQueryBuilder(Allocator.Persistent)
            .WithAll<EnemyTag, DeadTag>()
            .Build(ref state);

        // 注册 RequireForUpdate：查询为空则 System 不执行
        state.RequireForUpdate(_enemyQuery);
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 获取匹配的 Entity 数量
        int aliveCount = _enemyQuery.CalculateEntityCount();
        int deadCount = _deadEnemyQuery.CalculateEntityCount();

        // 可以获取所有匹配的 Entity 数组
        var enemies = _enemyQuery.ToEntityArray(Allocator.Temp);
        // ... 处理
        enemies.Dispose();

        // 可以获取组件数组
        var healthArray = _enemyQuery.ToComponentDataArray<Health>(Allocator.Temp);
        // ... 批量处理
        healthArray.Dispose();
    }

    [BurstCompile]
    public void OnDestroy(ref SystemState state)
    {
        // Persistent 的查询需要在 OnDestroy 中手动释放
        // 注意：通过 SystemAPI.QueryBuilder().Build() 创建的查询是自动管理的
        // 但 _deadEnemyQuery 使用了 new EntityQueryBuilder(Allocator.Persistent)，需要手动 Dispose
        _deadEnemyQuery.Dispose();
    }
}
```

### 2.6 SystemGroup 和更新顺序

```csharp
using Unity.Entities;

// 定义自定义 SystemGroup
[UpdateInGroup(typeof(SimulationSystemGroup))]
public partial class CombatSystemGroup : ComponentSystemGroup { }

// 在 Group 内排序 System
[UpdateInGroup(typeof(CombatSystemGroup))]
[UpdateBefore(typeof(DamageSystem))]   // 在 DamageSystem 之前执行
public partial struct HitDetectionSystem : ISystem { /* ... */ }

[UpdateInGroup(typeof(CombatSystemGroup))]
[UpdateAfter(typeof(HitDetectionSystem))] // 在 HitDetectionSystem 之后执行
public partial struct DamageSystem : ISystem { /* ... */ }

[UpdateInGroup(typeof(CombatSystemGroup))]
[UpdateAfter(typeof(DamageSystem))]
public partial struct DeathSystem : ISystem { /* ... */ }

// 默认的顶级 SystemGroup 层级：
// InitializationSystemGroup
//   └── BeginSimulationEntityCommandBufferSystem
// SimulationSystemGroup ← 大部分游戏逻辑放这里
//   ├── 你的自定义 Group
//   └── EndSimulationEntityCommandBufferSystem
// PresentationSystemGroup ← 渲染相关
```

### 2.7 综合示例 — 完整战斗系统

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;

// === 1. 组件定义 ===
public struct Damage : IComponentData
{
    public float Value;
}

public struct DamageCooldown : IComponentData
{
    public float Remaining;
}

// === 2. 伤害施加 System ===
[BurstCompile]
[UpdateInGroup(typeof(SimulationSystemGroup))]
public partial struct DealDamageSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        state.RequireForUpdate<Damage>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        foreach (var (health, damage, cooldown, entity) in
                 SystemAPI.Query<RefRW<Health>, RefRO<Damage>, RefRW<DamageCooldown>>()
                     .WithEntityAccess())
        {
            if (cooldown.ValueRO.Remaining > 0f)
            {
                cooldown.ValueRW.Remaining -= deltaTime;
                continue;
            }

            // 扣血
            health.ValueRW.Current -= damage.ValueRO.Value;

            // 重置冷却
            cooldown.ValueRW.Remaining = 0.5f;

            // 如果死亡
            if (health.ValueRO.Current <= 0f)
            {
                ecb.AddComponent<DeadTag>(entity);
                ecb.RemoveComponent<Health>(entity);
            }
        }
    }
}

// === 3. 死亡清理 System ===
[BurstCompile]
[UpdateInGroup(typeof(SimulationSystemGroup))]
[UpdateAfter(typeof(DealDamageSystem))]
public partial struct DeathCleanupSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        foreach (var entity in SystemAPI.QueryBuilder()
                     .WithAll<DeadTag, LocalTransform>()
                     .WithNone<DestroyTimer>()
                     .Build()
                     .ToEntityArray(Allocator.Temp))
        {
            // 添加延迟销毁计时器
            ecb.AddComponent(entity, new DestroyTimer { Remaining = 3f });
        }
    }
}

// 销毁计时器组件
public struct DestroyTimer : IComponentData
{
    public float Remaining;
}

// === 4. 定时销毁 System ===
[BurstCompile]
[UpdateInGroup(typeof(SimulationSystemGroup))]
[UpdateAfter(typeof(DeathCleanupSystem))]
public partial struct TimedDestroySystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        foreach (var (timer, entity) in
                 SystemAPI.Query<RefRW<DestroyTimer>>().WithEntityAccess())
        {
            timer.ValueRW.Remaining -= deltaTime;
            if (timer.ValueRO.Remaining <= 0f)
            {
                ecb.DestroyEntity(entity);
            }
        }
    }
}
```

**运行方式:** 将所有代码放入 Scripts 文件夹。创建包含 `Health`、`Damage`、`DamageCooldown` 组件的 Entity。运行后观察战斗循环：受伤 → 死亡 → 延迟销毁。

**预期效果:** System 按照声明的依赖顺序（`UpdateBefore`/`UpdateAfter`）依次执行。IJobEntity 自动并行处理大量实体。EntityQuery 精确筛选需要的实体。ChangeFilter 跳过未变化的数据。

---

## 3. 练习

### 练习 1: 基础练习 — 将 foreach 改写为 IJobEntity

将教程 16 中的 `RotationSystem`（使用 `SystemAPI.Query` foreach）改写为使用 `IJobEntity` 的版本。对比两种写法的区别。

### 练习 2: 进阶练习 — 分层更新系统

创建以下 SystemGroup 结构：
```
SimulationSystemGroup
  └── GameLogicGroup
       ├── InputSystem (读取输入 → 设置 MoveDirection 组件)
       ├── MovementSystem (根据 MoveDirection 移动实体)
       └── BoundarySystem (限制实体在 [-10, 10] 范围内)
```
确保三个 System 严格按顺序执行。

### 练习 3: 挑战练习（可选） — EntityQuery 的性能分析

使用 `SystemAPI.GetSingleton<EntityQuery>()` 获取内置查询，打印以下信息：
- 匹配的 Entity 数量
- 匹配的 Chunk 数量
- 每个 Chunk 中的 Entity 数量（Chunk 利用率）

---

## 4. 扩展阅读

- [ISystem 文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-isystem.html)
- [SystemAPI.Query 文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-systemapi-query.html)
- [IJobEntity 文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-ijobentity.html)
- [System Update Order](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-update-order.html)

---

## 常见陷阱

1. **忘记传 `ref SystemState`**: ISystem 的 OnCreate/OnUpdate/OnDestroy 必须接收 `ref SystemState state`，这是非托管 struct 访问 ECS 世界的唯一方式。

2. **RequireForUpdate 用法错误**: `RequireForUpdate<T>()` 检查的是是否有**至少一个**实体拥有组件 T。如果你还需要排除某个组件，使用 `RequireForUpdate` 的 EntityQuery 重载。

3. **Job 依赖链断裂**: 调度多个 Job 时，必须将上一个 Job 的 `JobHandle` 传给下一个 Job 的 `ScheduleParallel(state.Dependency)`，否则可能数据竞争。使用 `state.Dependency = JobHandle.CombineDependencies(...)` 合并多个依赖。

4. **SystemAPI.Query 不能跨帧保持引用**: `SystemAPI.Query` 返回的是临时引用，不能保存到字段中。需要持久化查询时使用 `EntityQuery`。

5. **struct ISystem 不能有托管字段**: ISystem 是 `partial struct`，所有字段必须是 blittable 类型。不能有 `List<T>`、`string` 等托管对象。需要托管资源时使用 `SystemBase` 或通过 `SystemState` 的 `EntityStorageInfoLookup` 等间接访问。

6. **Wrong SystemGroup**: 如果不指定 `[UpdateInGroup]`，System 默认放入 `SimulationSystemGroup`。渲染相关 System 应放入 `PresentationSystemGroup`。
