---
title: "Jobs + Burst 详解"
updated: 2026-06-05
---

# Jobs + Burst 详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 3.5 小时
> 前置知识: System 编写（教程 18）、C# 多线程基础、内存布局知识

---

## 1. 概念讲解

### 为什么需要 Jobs + Burst？

即使在 ECS 架构下，如果所有逻辑都在主线程顺序执行，性能上限仍然是单核频率。真正让 DOTS 性能飞跃的，是**并行 Job 调度**和**Burst 编译器的原生代码生成**。

```
单线程 (MonoBehaviour):      ████████████████████ (100 个对象更新)
Job 并行 (6 核, Burst):       ████  ████  ████
                              ████  ████  ████  → 理论上 6x 加速
                                             实际可达 15-50x
```

### Jobs System 的工作原理

Jobs System 是 Unity 的多线程任务调度器：

1. **Job 定义**: 继承 `IJobEntity`（或 `IJob`、`IJobParallelFor`）的结构体
2. **数据声明**: 所有需要的数据通过 struct 字段传入
3. **调度**: 调用 `Schedule()` 或 `ScheduleParallel()` 将 Job 放入队列
4. **执行**: Worker Threads 从队列取 Job 执行
5. **依赖**: 通过 `JobHandle` 链条保证顺序

**线程安全规则**:
- 每个 Job 独立处理不同的 Entity/Index
- 写入操作由 Job System 保证不冲突
- 使用 `NativeContainer`（非托管容器）而非 `List<T>`

### Burst 编译器的工作原理

Burst 是一个基于 LLVM 的 AOT 编译器：

```
C# (HPC# 子集)
    │
    ▼  IL2CPP 转 .NET IL
托管 IL 代码
    │
    ▼  Burst 编译器 (LLVM)
原生机器码 (x64/ARM64)
    │
    ▼  LLVM 优化 Pass
- 循环展开
- 函数内联
- 死代码消除
- SIMD 自动向量化 (SSE/AVX/NEON)
    │
    ▼
高度优化的原生代码
```

### Burst 的限制

Burst 只能编译 "HPC#"（High-Performance C#）子集，不能包含：

- ❌ 托管对象（`class`、`string`、`object`、`delegate`）
- ❌ 异常（`try-catch`、`throw`）
- ❌ `System.IO`、`System.Net` 等 .NET 类库
- ❌ 虚方法调用（除非 `sealed`）
- ❌ `foreach` 遍历非 Burst 兼容集合
- ✅ 支持 `math`、`NativeArray`、`struct`、`fixed` 数组、指针（`unsafe`）

### 核心思想

**"为缓存而写"**: 将数据组织成连续内存块，让 CPU 预取器可以高效工作。Burst 自动利用 SIMD 指令同时计算多个数据。

**"零开销抽象"**: `IJobEntity` 的 `Execute()` 方法看起来像普通 foreach，但实际上被编译为高度优化的 SIMD 循环。

---

## 2. 代码示例

### 2.1 IJobEntity 基础写法

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Jobs;
using Unity.Mathematics;
using Unity.Transforms;
using Unity.Collections;

// === 组件定义 ===
public struct Velocity : IComponentData
{
    public float3 Value;
}

public struct GravityAffected : IComponentData
{
    public float GravityScale;
}

// === IJobEntity 示例：重力 + 移动 ===
[BurstCompile]
public partial struct PhysicsMovementJob : IJobEntity
{
    // 外部传入的参数
    public float DeltaTime;
    public float3 Gravity;

    void Execute(
        ref LocalTransform transform,
        ref Velocity velocity,
        in GravityAffected gravity)
    {
        // 应用重力加速度
        velocity.Value += Gravity * gravity.GravityScale * DeltaTime;

        // 更新位置
        transform.Position += velocity.Value * DeltaTime;
    }
}

// === 调度 System ===
[BurstCompile]
public partial struct PhysicsSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        state.RequireForUpdate<Velocity>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        var job = new PhysicsMovementJob
        {
            DeltaTime = SystemAPI.Time.DeltaTime,
            Gravity = new float3(0f, -9.81f, 0f)
        };

        // ScheduleParallel: 自动多线程并行
        state.Dependency = job.ScheduleParallel(state.Dependency);
    }
}
```

### 2.2 NativeContainer 的线程安全使用

```csharp
using Unity.Burst;
using Unity.Collections;
using Unity.Entities;
using Unity.Jobs;
using Unity.Mathematics;

[BurstCompile]
public partial struct TargetTrackingJob : IJobEntity
{
    [ReadOnly] public NativeArray<float3> TargetPositions; // 只读：多线程安全
    [ReadOnly] public NativeArray<float> DetectionRadii;

    // 只读的 ComponentLookup（类似字典，O(1) 查找）
    [ReadOnly] public ComponentLookup<LocalTransform> TransformLookup;

    void Execute(
        ref LocalTransform transform,
        ref Velocity velocity,
        in Entity entity)
    {
        for (int i = 0; i < TargetPositions.Length; i++)
        {
            float dist = math.distance(transform.Position, TargetPositions[i]);
            if (dist < DetectionRadii[i])
            {
                float3 direction = math.normalize(TargetPositions[i] - transform.Position);
                velocity.Value = direction * 5f;
                break;
            }
        }
    }
}
```

### 2.3 NativeList / NativeHashMap 的高级用法

```csharp
using Unity.Burst;
using Unity.Collections;
using Unity.Entities;
using Unity.Jobs;
using Unity.Mathematics;

// 使用 NativeHashMap 查找
[BurstCompile]
public partial struct DamageLookupJob : IJobEntity
{
    [ReadOnly] public NativeHashMap<FixedString32Bytes, float> DamageMultiplierMap;

    void Execute(ref Health health, in DamageType damageType)
    {
        // 根据伤害类型查找倍率
        if (DamageMultiplierMap.TryGetValue(damageType.Name, out float multiplier))
        {
            health.Current -= 10f * multiplier;
        }
    }
}

public struct DamageType : IComponentData
{
    public FixedString32Bytes Name; // Burst 兼容的字符串
}

// 使用 NativeList 收集结果
[BurstCompile]
public partial struct CollectDeadEntitiesJob : IJobEntity
{
    public NativeList<Entity>.ParallelWriter DeadList; // 并行的 Writer

    void Execute(in Health health, in Entity entity)
    {
        if (health.Current <= 0f)
        {
            DeadList.AddNoResize(entity); // 注意：需要预分配容量
        }
    }
}

// 调度示例
[BurstCompile]
public partial struct CollectAndDestroySystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 预分配 NativeList（这个操作不能 Burst，在 Schedule 之前做）
        var deadList = new NativeList<Entity>(1024, Allocator.TempJob);

        var collectJob = new CollectDeadEntitiesJob
        {
            DeadList = deadList.AsParallelWriter()
        };

        JobHandle collectHandle = collectJob.ScheduleParallel(state.Dependency);

        // 必须在 Job 完成后才能读取 NativeList
        collectHandle.Complete();

        var ecb = new EntityCommandBuffer(Allocator.Temp);
        for (int i = 0; i < deadList.Length; i++)
        {
            ecb.DestroyEntity(deadList[i]);
        }
        ecb.Playback(state.EntityManager);
        ecb.Dispose();

        deadList.Dispose();
    }
}
```

### 2.4 EntityCommandBuffer.ParallelWriter 多线程写入

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Jobs;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;

// 子弹碰撞检测和处理
[BurstCompile]
public partial struct BulletCollisionJob : IJobEntity
{
    public float DeltaTime;
    public EntityCommandBuffer.ParallelWriter Ecb; // 并行 ECB
    [ReadOnly] public ComponentLookup<Health> HealthLookup;

    // EntityIndexInChunk 用于生成唯一的 sortKey
    void Execute(
        [ChunkIndexInQuery] int sortKey,          // 自动注入的排序键
        ref LocalTransform transform,
        ref Bullet bullet,
        in Entity entity)
    {
        bullet.RemainingLifetime -= DeltaTime;

        // 过期销毁
        if (bullet.RemainingLifetime <= 0f)
        {
            Ecb.DestroyEntity(sortKey, entity);
            return;
        }

        // 移动子弹
        float3 forward = math.forward(transform.Rotation);
        transform.Position += forward * bullet.Speed * DeltaTime;

        // 碰撞检测（简化版：Y < 0 视为命中地面）
        if (transform.Position.y < 0f)
        {
            // 生成命中特效
            Entity hitEffect = Ecb.Instantiate(sortKey, bullet.HitEffectPrefab);
            Ecb.SetComponent(sortKey, hitEffect, LocalTransform.FromPosition(transform.Position));

            // 销毁子弹
            Ecb.DestroyEntity(sortKey, entity);
        }
    }
}

// 调度 System
[BurstCompile]
public partial struct BulletSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        var job = new BulletCollisionJob
        {
            DeltaTime = SystemAPI.Time.DeltaTime,
            Ecb = ecb.AsParallelWriter(),
            HealthLookup = SystemAPI.GetComponentLookup<Health>(true)
        };

        state.Dependency = job.ScheduleParallel(state.Dependency);
    }
}
```

### 2.5 性能基准对比

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Jobs;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;
using UnityEngine;
using Unity.Profiling;

public struct BenchmarkEntity : IComponentData
{
    public float Value;
}

// === 无 Burst 版本（仅作对比） ===
public partial struct NoBurstMovementSystem : ISystem
{
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;
        foreach (var (transform, data) in
                 SystemAPI.Query<RefRW<LocalTransform>, RefRW<BenchmarkEntity>>())
        {
            data.ValueRW = math.sin(data.ValueRO + deltaTime);
            transform.ValueRW.Position.y = data.ValueRO;
        }
    }
}

// === Burst 版本 ===
[BurstCompile]
public partial struct BurstMovementSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        new BurstMoveJob { DeltaTime = SystemAPI.Time.DeltaTime }
            .ScheduleParallel();
    }
}

[BurstCompile]
public partial struct BurstMoveJob : IJobEntity
{
    public float DeltaTime;

    void Execute(ref LocalTransform transform, ref BenchmarkEntity data)
    {
        data.Value = math.sin(data.Value + DeltaTime);
        transform.Position.y = data.Value;
    }
}

// 预期性能对比（10000 个实体）:
// ┌─────────────────────────┬──────────┬───────────┐
// │ 版本                    │ 单帧耗时  │ FPS       │
// ├─────────────────────────┼──────────┼───────────┤
// │ No Burst (foreach)      │ ~25ms    │ ~40       │
// │ Burst Only (无 Job)     │ ~8ms     │ ~125      │
// │ Burst + Job (Schedule)  │ ~3ms     │ ~333      │
// │ Burst + JobParallel     │ ~0.8ms   │ 60+ (稳定)│
// └─────────────────────────┴──────────┴───────────┘
```

### 2.6 综合示例 — 大规模敌人生成与并行更新

```csharp
// === 完整的并行敌人系统 ===
using Unity.Burst;
using Unity.Entities;
using Unity.Jobs;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;

// 组件
public struct EnemyComponent : IComponentData
{
    public float Health;
    public float3 TargetPosition;
    public float AggroRange;
}

// === 1. 敌人生成 (使用 ECB 并行) ===
[BurstCompile]
public partial struct EnemySpawnJob : IJobEntity
{
    public EntityCommandBuffer.ParallelWriter Ecb;
    public Random Random;
    public NativeArray<Entity> EnemyPrefabs; // 多种敌人 Prefab

    void Execute([ChunkIndexInQuery] int sortKey, in SpawnPoint spawnPoint)
    {
        int typeIndex = Random.NextInt(0, EnemyPrefabs.Length);
        Entity enemy = Ecb.Instantiate(sortKey, EnemyPrefabs[typeIndex]);

        // 随机位置偏移
        float3 offset = Random.NextFloat3(new float3(-2, 0, -2), new float3(2, 0, 2));
        Ecb.SetComponent(sortKey, enemy, LocalTransform.FromPosition(spawnPoint.Position + offset));

        Ecb.AddComponent(sortKey, enemy, new EnemyComponent
        {
            Health = 100f,
            TargetPosition = float3.zero,
            AggroRange = 15f
        });
    }
}

// === 2. 敌人 AI (并行处理) ===
[BurstCompile]
public partial struct EnemyAIJob : IJobEntity
{
    public float DeltaTime;
    public float3 PlayerPosition;

    [NativeDisableParallelForRestriction]
    public NativeArray<int> EnemyCount; // 共享计数器

    void Execute(
        ref LocalTransform transform,
        ref EnemyComponent enemy,
        ref Velocity velocity,
        [EntityIndexInChunk] int entityIndex)
    {
        float distToPlayer = math.distance(transform.Position, PlayerPosition);

        // 原子计数器（简化演示，实际使用 Interlocked）
        // NativeArray 不支持原子操作，此处展示多线程思路
        // 实际应在单线程完成计数

        if (distToPlayer < enemy.AggroRange)
        {
            // 追击玩家
            float3 direction = math.normalize(PlayerPosition - transform.Position);
            velocity.Value = direction * 5f;
            transform.Rotation = quaternion.LookRotationSafe(direction, math.up());
        }
        else
        {
            // 随机巡逻（简化：减速）
            velocity.Value = math.lerp(velocity.Value, float3.zero, DeltaTime);
        }

        transform.Position += velocity.Value * DeltaTime;
    }
}

// === 3. 综合调度 System ===
[BurstCompile]
public partial struct EnemyManagerSystem : ISystem
{
    private Random _random;

    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        _random = new Random(12345);
        state.RequireForUpdate<SpawnPoint>();
        state.RequireForUpdate<EnemyComponent>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        float deltaTime = SystemAPI.Time.DeltaTime;

        // 找到玩家位置
        float3 playerPos = float3.zero;
        foreach (var transform in SystemAPI.Query<RefRO<LocalTransform>>().WithAll<PlayerTag>())
        {
            playerPos = transform.ValueRO.Position;
            break;
        }

        _random.NextInt(); // 推进随机数生成器

        // 并行 AI 更新
        var aiJob = new EnemyAIJob
        {
            DeltaTime = deltaTime,
            PlayerPosition = playerPos,
            EnemyCount = new NativeArray<int>(1, Allocator.TempJob)
        };

        state.Dependency = aiJob.ScheduleParallel(state.Dependency);

        // 注意：如果需要读回 EnemyCount，必须在 Job 完成后访问
        state.Dependency.Complete();
        // int totalEnemies = aiJob.EnemyCount[0]; ← 使用前确保 Complete
        aiJob.EnemyCount.Dispose();
    }
}
```

**运行方式:** 将所有代码放入 Scripts 文件夹。创建敌人生成点 GameObjects（挂载 SpawnPoint Authoring）。在 SubScene 中放入敌人 Prefab。运行观察 1000+ 敌人的并行 AI 行为。

**预期效果:**
- 多核 CPU 利用率显著提升（可用 Profiler 验证）
- 1000 个敌人同时运行 AI 仍保持 60+ FPS
- Burst 编译自动生成 SIMD 优化的原生代码
- ECB.ParallelWriter 在多个线程安全地创建/销毁 Entity

---

## 3. 练习

### 练习 1: 基础练习 — 并行的简单移动

创建 10000 个 Entity，每个有随机初始位置和速度。编写 `IJobEntity` 让它们沿速度方向移动。使用 Burst + ScheduleParallel。测量 FPS。

### 练习 2: 进阶练习 — 并行的碰撞检测

使用 `NativeMultiHashMap<int, Entity>` 实现空间哈希（Spatial Hashing）：
1. 第一个 Job：将所有实体按网格坐标写入 HashMap
2. 第二个 Job：查询邻近网格中的实体，检测距离是否 < 阈值

### 练习 3: 挑战练习（可选） — 完整的 Boids 集群模拟

实现经典的 Boids（鸟群）算法：
1. 分离（Separation）：远离邻近个体
2. 对齐（Alignment）：朝向邻近个体的平均方向
3. 凝聚（Cohesion）：移向邻近个体的平均位置

要求：
- 全部使用 IJobEntity 或 IJobParallelFor
- 使用 NativeArray 存储中间计算结果
- 使用 Burst 编译
- 目标：1000 个体 60 FPS


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```csharp
> using Unity.Burst;
> using Unity.Entities;
> using Unity.Jobs;
> using Unity.Mathematics;
> using Unity.Transforms;
>
> // === 组件定义 ===
> public struct RandomVelocity : IComponentData
> {
>     public float3 Value;
> }
>
> // === IJobEntity 定义 ===
> [BurstCompile]
> public partial struct SimpleMoveJob : IJobEntity
> {
>     public float DeltaTime;
>
>     void Execute(ref LocalTransform transform, in RandomVelocity velocity)
>     {
>         transform.Position += velocity.Value * DeltaTime;
>     }
> }
>
> // === 初始化和调度 System ===
> [BurstCompile]
> public partial struct SimpleMovementSystem : ISystem
> {
>     [BurstCompile]
>     public void OnCreate(ref SystemState state)
>     {
>         state.RequireForUpdate<RandomVelocity>();
>     }
>
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         var job = new SimpleMoveJob
>         {
>             DeltaTime = SystemAPI.Time.DeltaTime
>         };
>         state.Dependency = job.ScheduleParallel(state.Dependency);
>     }
> }
>
> // === 批量创建 10000 个 Entity（在 OnCreate 或 Baking 中） ===
> // 使用 EntityManager 批量创建：
> // var archetype = state.EntityManager.CreateArchetype(
> //     typeof(LocalTransform), typeof(RandomVelocity));
> // using var entities = new NativeArray<Entity>(10000, Allocator.Temp);
> // state.EntityManager.CreateEntity(archetype, entities);
> // 然后用一个 Job 设置随机值：
>
> [BurstCompile]
> public partial struct InitVelocityJob : IJobEntity
> {
>     public Unity.Mathematics.Random Random;
>
>     void Execute(ref LocalTransform transform, ref RandomVelocity velocity)
>     {
>         velocity.Value = Random.NextFloat3Direction() * Random.NextFloat(1f, 5f);
>         transform.Position = Random.NextFloat3(new float3(-50f), new float3(50f));
>     }
> }
> ```
>
> **性能测量方式：**
> - 使用 Unity Profiler（Window → Analysis → Profiler）查看 `SimpleMoveJob` 的耗时
> - 或用 `ProfilerMarker` 包裹调度代码：
>   ```csharp
>   static readonly ProfilerMarker s_MoveMarker = new("SimpleMoveJob");
>   s_MoveMarker.Begin();
>   state.Dependency = job.ScheduleParallel(state.Dependency);
>   s_MoveMarker.End();
>   ```
> - 预期：10000 实体在 Burst + ScheduleParallel 下 < 1ms（取决于 CPU 核心数）

> [!tip]- 练习 2 参考答案
> ```csharp
> using Unity.Burst;
> using Unity.Collections;
> using Unity.Entities;
> using Unity.Jobs;
> using Unity.Mathematics;
> using Unity.Transforms;
>
> public struct CollisionCandidate : IComponentData
> {
>     public float Radius;
> }
>
> // === 空间哈希碰撞检测 ===
> [BurstCompile]
> public partial struct CollisionDetectionSystem : ISystem
> {
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         float cellSize = 2f; // 网格单元大小（应 >= 最大碰撞半径）
>
>         // 步骤 1：构建空间哈希表（将实体按网格坐标分组）
>         var spatialMap = new NativeMultiHashMap<int, Entity>(4096, Allocator.TempJob);
>
>         var buildJob = new BuildSpatialMapJob
>         {
>             CellSize = cellSize,
>             SpatialMap = spatialMap.AsParallelWriter()
>         };
>         JobHandle buildHandle = buildJob.ScheduleParallel(state.Dependency);
>
>         // 步骤 2：查询邻近网格进行碰撞检测
>         var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
>         var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);
>
>         var queryJob = new SpatialQueryJob
>         {
>             CellSize = cellSize,
>             SpatialMap = spatialMap,
>             CollisionThreshold = 1.5f,
>             Ecb = ecb.AsParallelWriter()
>         };
>
>         // queryJob 依赖 buildJob（必须等哈希表构建完成）
>         state.Dependency = queryJob.ScheduleParallel(buildHandle);
>
>         spatialMap.Dispose(state.Dependency);
>     }
> }
>
> // === Job 1：构建空间哈希 ===
> [BurstCompile]
> public partial struct BuildSpatialMapJob : IJobEntity
> {
>     public float CellSize;
>     public NativeMultiHashMap<int, Entity>.ParallelWriter SpatialMap;
>
>     void Execute(in LocalTransform transform, in Entity entity)
>     {
>         // 计算网格坐标并编码为单个 int（哈希键）
>         int cellX = (int)math.floor(transform.Position.x / CellSize);
>         int cellZ = (int)math.floor(transform.Position.z / CellSize);
>         int hashKey = cellX * 73856093 ^ cellZ * 19349663; // 简单哈希
>         SpatialMap.Add(hashKey, entity);
>     }
> }
>
> // === Job 2：查询邻近网格 ===
> [BurstCompile]
> [WithAll(typeof(CollisionCandidate))] // 只对可碰撞的实体做查询
> public partial struct SpatialQueryJob : IJobEntity
> {
>     public float CellSize;
>     [ReadOnly] public NativeMultiHashMap<int, Entity> SpatialMap;
>     public float CollisionThreshold;
>     public EntityCommandBuffer.ParallelWriter Ecb;
>
>     void Execute(
>         [ChunkIndexInQuery] int sortKey,
>         in LocalTransform transform,
>         in Entity entity)
>     {
>         int cellX = (int)math.floor(transform.Position.x / CellSize);
>         int cellZ = (int)math.floor(transform.Position.z / CellSize);
>
>         // 遍历 3x3 邻域网格
>         for (int dx = -1; dx <= 1; dx++)
>         {
>             for (int dz = -1; dz <= 1; dz++)
>             {
>                 int hashKey = (cellX + dx) * 73856093 ^ (cellZ + dz) * 19349663;
>
>                 if (SpatialMap.TryGetFirstValue(hashKey, out Entity other, out var iterator))
>                 {
>                     do
>                     {
>                         // 跳过自身
>                         if (other == entity) continue;
>
>                         // 这里需要 other 的位置信息（通过 ComponentLookup 获取）
>                         // 简化示意：假设已获取 otherPos
>                         float3 otherPos = float3.zero; // 实际：TransformLookup[other].Position
>                         float dist = math.distance(transform.Position, otherPos);
>
>                         if (dist < CollisionThreshold)
>                         {
>                             // 碰撞响应（例：标记碰撞）
>                             Ecb.AddComponent<CollisionTag>(sortKey, entity);
>                         }
>                     }
>                     while (SpatialMap.TryGetNextValue(out other, ref iterator));
>                 }
>             }
>         }
>     }
> }
>
> public struct CollisionTag : IComponentData { }
> ```
>
> **设计要点：**
> - `NativeMultiHashMap` 支持多线程并行写入（`AsParallelWriter()`）和读取
> - 哈希键 = 网格坐标编码，相邻网格的实体通过哈希键查找
> - 3×3 邻域查询保证覆盖所有可能的碰撞对（只要 CellSize >= 碰撞阈值）
> - `TryGetFirstValue` / `TryGetNextValue` 迭代同一哈希桶内的所有实体
> - 为避免重复检测，可在查询时只检查 `entity.Index > other.Index` 的配对

> [!tip]- 练习 3 参考答案（可选）
> ```csharp
> using Unity.Burst;
> using Unity.Collections;
> using Unity.Entities;
> using Unity.Jobs;
> using Unity.Mathematics;
> using Unity.Transforms;
>
> // === Boid 参数 ===
> public struct BoidParams : IComponentData
> {
>     public float SeparationWeight;
>     public float AlignmentWeight;
>     public float CohesionWeight;
>     public float MaxSpeed;
>     public float NeighborRadius;
>     public float SeparationRadius;
> }
>
> // Step 1: 收集所有 Boid 的位置和速度到 NativeArray
> [BurstCompile]
> public partial struct CollectBoidDataJob : IJobEntity
> {
>     public NativeArray<float3> Positions;
>     public NativeArray<float3> Velocities;
>
>     void Execute(
>         [EntityIndexInChunk] int sortKey,
>         in LocalTransform transform,
>         in Velocity velocity)
>     {
>         Positions[sortKey] = transform.Position;
>         Velocities[sortKey] = velocity.Value;
>     }
> }
>
> // Step 2: Boids 算法核心
> [BurstCompile]
> public partial struct BoidUpdateJob : IJobEntity
> {
>     [ReadOnly] public NativeArray<float3> Positions;
>     [ReadOnly] public NativeArray<float3> Velocities;
>     public float DeltaTime;
>     public BoidParams Params;
>
>     void Execute(
>         ref LocalTransform transform,
>         ref Velocity velocity,
>         in Entity entity)
>     {
>         float3 separation = float3.zero;
>         float3 alignment = float3.zero;
>         float3 cohesion = float3.zero;
>         int neighborCount = 0;
>
>         int boidIndex = entity.Index; // 简化：假设 Index 对应数组索引
>
>         for (int i = 0; i < Positions.Length; i++)
>         {
>             if (i == boidIndex) continue;
>
>             float3 offset = Positions[i] - transform.Position;
>             float dist = math.length(offset);
>
>             if (dist < Params.NeighborRadius && dist > 0.0001f)
>             {
>                 float3 toNeighbor = offset / dist;
>
>                 // 1. 分离：远离邻近个体（距离越近排斥力越大）
>                 if (dist < Params.SeparationRadius)
>                 {
>                     separation -= toNeighbor * (1f - dist / Params.SeparationRadius);
>                 }
>
>                 // 2. 对齐：朝向邻近个体的平均方向
>                 alignment += Velocities[i];
>
>                 // 3. 凝聚：移向邻近个体的平均位置
>                 cohesion += Positions[i];
>
>                 neighborCount++;
>             }
>         }
>
>         if (neighborCount > 0)
>         {
>             alignment = alignment / neighborCount;
>             cohesion = (cohesion / neighborCount - transform.Position);
>         }
>
>         // 合成所有力
>         float3 steering = separation * Params.SeparationWeight
>                         + math.normalizesafe(alignment) * Params.AlignmentWeight
>                         + math.normalizesafe(cohesion) * Params.CohesionWeight;
>
>         // 更新速度（限制最大速度）
>         velocity.Value += steering * DeltaTime;
>         float speed = math.length(velocity.Value);
>         if (speed > Params.MaxSpeed)
>         {
>             velocity.Value = math.normalize(velocity.Value) * Params.MaxSpeed;
>         }
>
>         // 更新位置和朝向
>         transform.Position += velocity.Value * DeltaTime;
>         if (math.lengthsq(velocity.Value) > 0.0001f)
>         {
>             transform.Rotation = quaternion.LookRotationSafe(
>                 math.normalize(velocity.Value), math.up());
>         }
>     }
> }
>
> // === 调度 System ===
> [BurstCompile]
> public partial struct BoidSystem : ISystem
> {
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         // 获取查询
>         var query = SystemAPI.QueryBuilder()
>             .WithAll<LocalTransform, Velocity, BoidTag>()
>             .Build();
>
>         int boidCount = query.CalculateEntityCount();
>         if (boidCount == 0) return;
>
>         // 分配中间数组
>         var positions = new NativeArray<float3>(boidCount, Allocator.TempJob);
>         var velocities = new NativeArray<float3>(boidCount, Allocator.TempJob);
>
>         // 获取 Boid 参数（假设只有一个单例参数 Entity）
>         BoidParams params = default;
>         foreach (var p in SystemAPI.Query<RefRO<BoidParams>>())
>         {
>             params = p.ValueRO;
>             break;
>         }
>
>         float deltaTime = SystemAPI.Time.DeltaTime;
>
>         // Step 1: 收集数据
>         var collectJob = new CollectBoidDataJob
>         {
>             Positions = positions,
>             Velocities = velocities
>         };
>         JobHandle collectHandle = collectJob.ScheduleParallel(state.Dependency);
>
>         // Step 2: 更新 Boid（依赖 collectHandle）
>         var updateJob = new BoidUpdateJob
>         {
>             Positions = positions,
>             Velocities = velocities,
>             DeltaTime = deltaTime,
>             Params = params
>         };
>         state.Dependency = updateJob.ScheduleParallel(collectHandle);
>
>         // 清理中间数组（在 Job 完成后）
>         positions.Dispose(state.Dependency);
>         velocities.Dispose(state.Dependency);
>     }
> }
>
> public struct BoidTag : IComponentData { }
> ```
>
> **优化要点：**
> - O(n²) 遍历在 1000 个体时仍是可行的（每帧约 1M 次 `math.distance` 调用）
> - 超过 1000 个体推荐使用空间哈希（练习 2）替代全对全比较
> - 参数建议：`SeparationWeight=1.5, AlignmentWeight=1.0, CohesionWeight=1.0, MaxSpeed=5, NeighborRadius=3, SeparationRadius=1.5`
> - 边界处理：可在更新后 clamp 位置到有限空间，或在边界处反转速度
---

## 4. 扩展阅读

- [Unity Jobs System 文档](https://docs.unity3d.com/Manual/JobSystem.html)
- [Burst Compiler 文档](https://docs.unity3d.com/Packages/com.unity.burst@1.8/manual/index.html)
- [Burst 最佳实践](https://docs.unity3d.com/Packages/com.unity.burst@1.8/manual/docs/OptimizationGuidelines.html)
- [NativeContainer Safety System](https://docs.unity3d.com/Manual/JobSystemNativeContainer.html)
- [LLVM 优化 Pass 文档](https://llvm.org/docs/Passes.html)

---

## 常见陷阱

1. **忘记 `[BurstCompile]`**: ISystem 和 IJobEntity 都必须标记 `[BurstCompile]`。遗漏会导致静默回退到托管代码（慢 10-50x）。

2. **在 Job 中使用托管类型**: `string`、`class`、`List<T>` 等会导致 Burst 编译失败。使用 `FixedString32Bytes`、`NativeList<T>`、`struct`。

3. **NativeContainer 生命周期**: 使用 `Allocator.TempJob` 必须在 4 帧内释放；使用 `Allocator.Persistent` 必须在 OnDestroy 中手动释放。忘记 Dispose 会内存泄漏。

4. **ParallelWriter 的 sortKey**: ECB.ParallelWriter 的每个操作都需要一个 sortKey（int）。通常使用 `[ChunkIndexInQuery]` 或 `entity.Index` 作为 sortKey。sortKey 保证同一 Chunk 内的操作顺序正确。

5. **读取未 Complete 的依赖**: 在 Job 的 `Schedule()` 返回的 `JobHandle` 被 `Complete()` 之前，Job 写入的数据不可读取。如果 System 需要在 Job 后读取 NativeContainer 中的数据，必须先 `state.Dependency.Complete()`。

6. **Job 中的 `foreach` 不是 Burst 兼容的**: 虽然 ISystem.OnUpdate 中的 `SystemAPI.Query` foreach 可以被 Burst 编译，但 IJobEntity.Execute 中不能使用 foreach 遍历 NativeArray——使用 `for` 循环代替。

7. **SIMD 不是万能的**: Burst 自动向量化适用于连续的简单运算。对分支密集的代码或复杂数据结构操作，SIMD 收益有限。使用 Profiler 验证优化效果。
