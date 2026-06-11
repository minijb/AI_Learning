---
title: "EntityCommandBuffer 详解"
updated: 2026-06-05
---

# EntityCommandBuffer 详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 2.5 小时
> 前置知识: System 编写（教程 18）、Jobs + Burst（教程 20）、ECS 架构原理

---

## 1. 概念讲解

### 为什么需要 ECB？

在 ECS 中，"结构化更改"（Structural Changes）指创建/销毁 Entity、添加/移除组件等操作。这些操作会改变 Chunk 的内存布局，因此**不能在 Job 中直接执行**（Job 中多个线程可能同时修改 Chunk）。

ECB（EntityCommandBuffer）通过**延迟执行**解决这个问题：

```
Job 中记录操作    →    Job 完成后播放操作
(线程安全，只记录)     (主线程，安全执行结构更改)

┌──────────────┐      ┌─────────────────┐
│ Worker 0     │      │                 │
│  ecb.Create  │──────│                 │
│  ecb.Destroy │      │   ECB.Playback  │
├──────────────┤      │   (单线程执行    │
│ Worker 1     │      │    所有记录的    │
│  ecb.AddComp │──────│    操作)         │
│  ecb.SetComp │      │                 │
└──────────────┘      └─────────────────┘
```

### ECB 的播放时机

| 播放方式 | 描述 | 使用场景 |
|---------|------|---------|
| `EndSimulationEntityCommandBufferSystem` | 在 SimulationSystemGroup 结束时自动播放 | 最常见的延迟操作 |
| `BeginSimulationEntityCommandBufferSystem` | 在 SimulationSystemGroup 开始时播放 | 需要在所有 System 之前执行 |
| `EndInitializationEntityCommandBufferSystem` | 在 InitializationSystemGroup 结束时播放 | 初始化阶段 |
| `EndFixedStepSimulationEntityCommandBufferSystem` | 在固定时间步长组结束时播放 | 物理相关 |
| 手动 `ecb.Playback()` | 立即执行所有记录的操作 | 需要在特定时刻精确执行 |

### 核心思想

**"先想清楚要做什么，然后一起做。"** ECB 让你在 Job 中记录所有操作请求，然后在安全的时间点一起执行。这避免了 Job 中的竞态条件，同时保持了操作的原子性。

---

## 2. 代码示例

### 2.1 ECB 基础用法 — 创建和销毁

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;

public struct Lifetime : IComponentData
{
    public float Remaining;
}

// === 使用 ECB 进行延迟销毁 ===
[BurstCompile]
public partial struct LifetimeSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        state.RequireForUpdate<Lifetime>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;

        // 获取 ECB System 的单例
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();

        // 创建 ECB（单线程版本）
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        foreach (var (lifetime, entity) in
                 SystemAPI.Query<RefRW<Lifetime>>().WithEntityAccess())
        {
            lifetime.ValueRW.Remaining -= deltaTime;

            if (lifetime.ValueRO.Remaining <= 0f)
            {
                // 记录销毁操作——不会立即执行
                ecb.DestroyEntity(entity);
            }
        }
        // ECB 在 System 结束时自动 Playback
    }

    [BurstCompile]
    public void OnDestroy(ref SystemState state) { }
}
```

### 2.2 ECB 常用操作大全

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;

[BurstCompile]
public partial struct ECBDemoSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        // === 1. 创建实体 ===
        Entity newEntity = ecb.CreateEntity();

        // === 2. 添加组件 ===
        ecb.AddComponent(newEntity, new Health { Current = 100f, Max = 100f });
        ecb.AddComponent(newEntity, LocalTransform.FromPosition(0, 0, 0));
        ecb.AddComponent<PlayerTag>(newEntity);

        // === 3. 添加 Buffer ===
        var buffer = ecb.AddBuffer<Waypoint>(newEntity);
        buffer.Add(new Waypoint { Position = new float3(1, 0, 0) });
        buffer.Add(new Waypoint { Position = new float3(2, 0, 0) });

        // === 4. 设置组件值（覆盖已有值） ===
        ecb.SetComponent(newEntity, new MoveSpeed { MetersPerSecond = 5f });

        // === 5. 移除组件 ===
        ecb.RemoveComponent<Lifetime>(newEntity);

        // === 6. 实例化 Prefab ===
        Entity prefabInstance = ecb.Instantiate(somePrefabEntity);
        ecb.SetComponent(prefabInstance, LocalTransform.FromPosition(10, 0, 0));

        // === 7. 销毁实体 ===
        ecb.DestroyEntity(newEntity);

        // === 8. 禁用/启用 Enableable 组件 ===
        ecb.SetComponentEnabled<Invincible>(newEntity, true);  // 启用
        ecb.SetComponentEnabled<Invincible>(newEntity, false); // 禁用

        // === 9. 附加组件（如果不存在则添加；如果存在则不操作） ===
        ecb.AddComponentIfMissing<DeadTag>(newEntity);

        // === 10. 追加到 Buffer ===
        ecb.AppendToBuffer(newEntity, new Waypoint { Position = new float3(5, 0, 0) });

        // 注意：所有操作在 Playback 时按记录顺序执行。
        // 因此上面先 CreateEntity、添加组件、设置组件、最后 DestroyEntity 是合法的。
        // Playback 时会按顺序：创建 → 添加 → 设置 → 销毁。
    }
}
```

### 2.3 ECB.AsParallelWriter() 用于并行 Job

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Jobs;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;

// === 子弹生成器 ===
public struct BulletSpawner : IComponentData
{
    public Entity BulletPrefab;
    public float FireRate;
    public float Cooldown;
    public float BulletSpeed;
    public float BulletLifetime;
}

public struct Bullet : IComponentData
{
    public float Speed;
    public float RemainingLifetime;
}

// === 并行子弹发射 Job ===
[BurstCompile]
public partial struct BulletSpawnJob : IJobEntity
{
    public float DeltaTime;
    public EntityCommandBuffer.ParallelWriter Ecb;

    void Execute(
        [ChunkIndexInQuery] int sortKey,  // 并行写入的排序键
        ref BulletSpawner spawner,
        in LocalTransform transform)
    {
        spawner.Cooldown -= DeltaTime;

        if (spawner.Cooldown <= 0f)
        {
            spawner.Cooldown = spawner.FireRate;

            // 并行创建子弹实体
            Entity bullet = Ecb.Instantiate(sortKey, spawner.BulletPrefab);

            // 设置初始位置和旋转
            Ecb.SetComponent(sortKey, bullet, transform);

            // 添加子弹组件
            Ecb.AddComponent(sortKey, bullet, new Bullet
            {
                Speed = spawner.BulletSpeed,
                RemainingLifetime = spawner.BulletLifetime
            });

            // 添加速度组件
            Ecb.AddComponent(sortKey, bullet, new Velocity
            {
                Value = math.forward(transform.Rotation) * spawner.BulletSpeed
            });
        }
    }
}

// === 子弹移动和销毁 Job ===
[BurstCompile]
public partial struct BulletUpdateJob : IJobEntity
{
    public float DeltaTime;
    public EntityCommandBuffer.ParallelWriter Ecb;

    void Execute(
        [ChunkIndexInQuery] int sortKey,
        ref LocalTransform transform,
        ref Bullet bullet,
        ref Velocity velocity,
        in Entity entity)
    {
        // 更新位置
        transform.Position += velocity.Value * DeltaTime;

        // 生命周期
        bullet.RemainingLifetime -= DeltaTime;
        if (bullet.RemainingLifetime <= 0f)
        {
            Ecb.DestroyEntity(sortKey, entity);
        }
    }
}

// === 综合调度 System ===
[BurstCompile]
[UpdateInGroup(typeof(SimulationSystemGroup))]
public partial struct BulletManagerSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        state.RequireForUpdate<BulletSpawner>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        // 第一步：并行生成子弹
        var spawnJob = new BulletSpawnJob
        {
            DeltaTime = deltaTime,
            Ecb = ecb.AsParallelWriter()
        };
        state.Dependency = spawnJob.ScheduleParallel(state.Dependency);

        // 第二步：并行更新子弹（需要在 Spawn 之后）
        var updateJob = new BulletUpdateJob
        {
            DeltaTime = deltaTime,
            Ecb = ecb.AsParallelWriter()
        };
        state.Dependency = updateJob.ScheduleParallel(state.Dependency);
    }
}
```

### 2.4 ECB 与 SystemState 的交互

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Collections;

// === 使用 ECB 在 System 间传递消息 ===

// 伤害请求（一次性事件）
public struct DamageRequest : IComponentData
{
    public Entity Target;
    public float Amount;
    public Entity Source;
}

// === 系统 A：产生伤害请求 ===
[BurstCompile]
public partial struct AttackSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        foreach (var (weapon, transform) in
                 SystemAPI.Query<RefRO<Weapon>, RefRO<LocalTransform>>())
        {
            // 创建一个"请求实体"作为消息
            Entity requestEntity = ecb.CreateEntity();
            ecb.AddComponent(requestEntity, new DamageRequest
            {
                Target = Entity.Null, // 简化：实际应查找目标
                Amount = weapon.ValueRO.Damage,
                Source = transform.ValueRO.Position.Equals(new float3(0, 0, 0))
                    ? Entity.Null : Entity.Null
            });
        }
    }
}

// === 系统 B：处理伤害请求 ===
[BurstCompile]
[UpdateAfter(typeof(AttackSystem))]
public partial struct DamageResolutionSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        foreach (var (request, entity) in
                 SystemAPI.Query<RefRO<DamageRequest>>().WithEntityAccess())
        {
            if (SystemAPI.Exists(request.ValueRO.Target))
            {
                // 查找目标并扣血
                var health = SystemAPI.GetComponentRW<Health>(request.ValueRO.Target);
                health.ValueRW.Current -= request.ValueRO.Amount;

                // 播放受击效果（创建临时实体）
                Entity hitVfx = ecb.CreateEntity();
                ecb.AddComponent(hitVfx, new TemporaryEffect
                {
                    RemainingLifetime = 0.5f,
                    EffectType = EffectType.HitSpark
                });
            }

            // 销毁请求实体（一次性消息）
            ecb.DestroyEntity(entity);
        }
    }
}

public struct TemporaryEffect : IComponentData
{
    public float RemainingLifetime;
    public EffectType EffectType;
}

public enum EffectType : byte
{
    HitSpark,
    Explosion,
    MuzzleFlash
}

[BurstCompile]
public partial struct CleanupEffectsSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;
        var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
        var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);

        foreach (var (effect, entity) in
                 SystemAPI.Query<RefRW<TemporaryEffect>>().WithEntityAccess())
        {
            effect.ValueRW.RemainingLifetime -= deltaTime;
            if (effect.ValueRO.RemainingLifetime <= 0f)
            {
                ecb.DestroyEntity(entity);
            }
        }
    }
}
```

### 2.5 手动 Playback — 精确控制执行时机

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Transforms;

// 需要在 System A 完成后再执行 System B 的结构更改时，
// 使用手动 Playback 确保顺序

[BurstCompile]
public partial struct ManualPlaybackSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 步骤 1: 收集数据到一个 NativeList
        var spawnPositions = new NativeList<float3>(Allocator.TempJob);

        foreach (var transform in SystemAPI.Query<RefRO<LocalTransform>>().WithAll<SpawnPoint>())
        {
            spawnPositions.Add(transform.ValueRO.Position);
        }

        // 步骤 2: 使用 ECB 立即生成敌人（需要马上看到结果）
        var ecb = new EntityCommandBuffer(Allocator.TempJob);

        foreach (var pos in spawnPositions)
        {
            // ... 创建敌人逻辑
        }

        // 手动 Playback：立即执行所有记录的操作
        ecb.Playback(state.EntityManager);

        // 步骤 3: 后续逻辑可以直接查询刚创建的实体
        foreach (var health in SystemAPI.Query<RefRO<Health>>().WithAll<EnemyTag>())
        {
            // 可以访问到步骤 2 创建的实体
        }

        // 清理
        ecb.Dispose();
        spawnPositions.Dispose();
    }
}
```

**运行方式:** 将代码放入 Scripts 文件夹。创建 `BulletSpawner` Authoring 并挂载到 GameObject，设置 BulletPrefab（需要制作子弹 Prefab 并标记为 ECS Prefab）。运行后观察子弹的生成—飞行—销毁流程。

**预期效果:**
- ECB 记录的创建/销毁操作在当前帧的 System Group 结束时批量执行
- 并行 Job 中多个线程安全地通过 `AsParallelWriter()` 写入 ECB
- 子弹的整个生命周期（生成 → 移动 → 过期销毁）由 ECB 串联
- 一次性事件（DamageRequest）通过"创建→使用→销毁"的 ECB 模式传递

---

## 3. 练习

### 练习 1: 基础练习 — 延迟生成敌人波次

实现：
- `WaveSpawner` 组件：包含 `EnemyPrefab`、`SpawnCount`、`SpawnInterval`
- 使用 ECB 每隔 `SpawnInterval` 秒生成一个敌人，直到 `SpawnCount` 耗尽
- 使用计时器跟踪间隔

### 练习 2: 进阶练习 — 子弹的连锁反应

实现：
- 子弹命中敌人后，通过 ECB 创建 3 个小型子子弹，随机方向散射
- 子子弹不能再次分裂（使用 Tag 标记）
- 所有子弹有统一的 `Lifetime` 自动销毁

### 练习 3: 挑战练习（可选） — 事件队列系统

使用 ECB 实现一个通用的事件队列：
- 定义 `GameEvent` 组件（包含 `EventType` enum 和 `float3 Position`）
- 任何 System 可以通过 ECB 创建事件实体
- `EventDispatcherSystem` 处理不同类型的事件（如：播放特效、扣血、播放音效）
- 处理完后销毁事件实体
- 确保帧内产生的事件能在同一帧被处理


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```csharp
> using Unity.Burst;
> using Unity.Entities;
> using Unity.Collections;
> using Unity.Mathematics;
> using Unity.Transforms;
>
> // === WaveSpawner 组件 ===
> public struct WaveSpawner : IComponentData
> {
>     public Entity EnemyPrefab;
>     public int TotalSpawnCount;      // 总共要生成的敌人数
>     public int SpawnedSoFar;          // 已生成数量
>     public float SpawnInterval;       // 生成间隔（秒）
>     public float IntervalTimer;       // 间隔计时器
>     public float3 SpawnOrigin;        // 生成位置基准
>     public float SpawnRadius;         // 随机偏移半径
> }
>
> [BurstCompile]
> public partial struct WaveSpawnerSystem : ISystem
> {
>     [BurstCompile]
>     public void OnCreate(ref SystemState state)
>     {
>         state.RequireForUpdate<WaveSpawner>();
>     }
>
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         float deltaTime = SystemAPI.Time.DeltaTime;
>         var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
>         var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);
>
>         // 使用 Random 生成种子（这里用固定种子简化）
>         var random = new Unity.Mathematics.Random(12345);
>
>         foreach (var (spawner, entity) in
>                  SystemAPI.Query<RefRW<WaveSpawner>>().WithEntityAccess())
>         {
>             // 已生成完毕，跳过
>             if (spawner.ValueRO.SpawnedSoFar >= spawner.ValueRO.TotalSpawnCount)
>                 continue;
>
>             // 更新间隔计时器
>             spawner.ValueRW.IntervalTimer -= deltaTime;
>
>             if (spawner.ValueRO.IntervalTimer <= 0f)
>             {
>                 // 重置计时器
>                 spawner.ValueRW.IntervalTimer = spawner.ValueRO.SpawnInterval;
>
>                 // 生成一个敌人
>                 Entity enemy = ecb.Instantiate(spawner.ValueRO.EnemyPrefab);
>
>                 // 随机位置（在 SpawnOrigin 周围的圆内）
>                 float angle = random.NextFloat(0f, math.PI * 2f);
>                 float dist = random.NextFloat(0f, spawner.ValueRO.SpawnRadius);
>                 float3 offset = new float3(
>                     math.cos(angle) * dist,
>                     0f,
>                     math.sin(angle) * dist);
>
>                 ecb.SetComponent(enemy, new LocalTransform
>                 {
>                     Position = spawner.ValueRO.SpawnOrigin + offset,
>                     Rotation = quaternion.identity,
>                     Scale = 1f
>                 });
>
>                 // 设置敌人的初始属性
>                 ecb.SetComponent(enemy, new Health
>                 {
>                     Current = 100f,
>                     Max = 100f
>                 });
>
>                 // 记录已生成数量
>                 spawner.ValueRW.SpawnedSoFar++;
>
>                 // 达到总数后，可以选择销毁生成器或保留
>                 // if (spawner.ValueRO.SpawnedSoFar >= spawner.ValueRO.TotalSpawnCount)
>                 //     ecb.DestroyEntity(entity);
>             }
>         }
>     }
> }
> ```
>
> **设计要点：**
> - `IntervalTimer` 在 `RefRW` 中递减，Burst 兼容的浮点计时
> - ECB 延迟执行：`ecb.Instantiate` + `ecb.SetComponent` 记录操作，在 SimulationSystemGroup 结束时批量 Playback
> - `SpawnedSoFar` 跟踪进度，避免无限生成
> - 使用 `ecb.SetComponent` 而非 `ecb.AddComponent`，因为 Prefab 已包含该组件（Set 覆盖已有值）
> - 可通过不销毁 `WaveSpawner` Entity 实现多波次：重置 `SpawnedSoFar = 0` 和 `IntervalTimer`

> [!tip]- 练习 2 参考答案
> ```csharp
> using Unity.Burst;
> using Unity.Entities;
> using Unity.Jobs;
> using Unity.Collections;
> using Unity.Mathematics;
> using Unity.Transforms;
>
> // === 组件 ===
> public struct BulletLifetime : IComponentData
> {
>     public float Remaining;
> }
>
> public struct BulletSpeed : IComponentData
> {
>     public float Value;
> }
>
> // 子子弹标记（不可再次分裂）
> public struct SubBulletTag : IComponentData { }
>
> // === 子弹移动 + 碰撞 + 分裂 ===
> [BurstCompile]
> public partial struct BulletChainReactionJob : IJobEntity
> {
>     public float DeltaTime;
>     public EntityCommandBuffer.ParallelWriter Ecb;
>
>     void Execute(
>         [ChunkIndexInQuery] int sortKey,
>         ref LocalTransform transform,
>         ref BulletLifetime lifetime,
>         in BulletSpeed speed,
>         in Entity entity)
>     {
>         // 移动（沿前方）
>         float3 forward = math.forward(transform.Rotation);
>         transform.Position += forward * speed.Value * DeltaTime;
>
>         // 生命周期
>         lifetime.Remaining -= DeltaTime;
>
>         if (lifetime.Remaining <= 0f)
>         {
>             Ecb.DestroyEntity(sortKey, entity);
>             return;
>         }
>
>         // 简化碰撞：Y < 0 视为命中地面（实际应使用物理查询）
>         if (transform.Position.y < 0f)
>         {
>             // 非子子弹才分裂（使用 Entity 上的 SubBulletTag 判断）
>             // 注意：Job 中不能直接检查组件存在性，
>             // 需要在 System 调度层面用 [WithNone(typeof(SubBulletTag))] 分离
>
>             // 分裂逻辑在实际的 SplitJob 中处理（见下方）
>             Ecb.DestroyEntity(sortKey, entity);
>         }
>     }
> }
>
> // === 分裂 Job（只处理非子子弹） ===
> [BurstCompile]
> [WithNone(typeof(SubBulletTag))]
> public partial struct BulletSplitJob : IJobEntity
> {
>     public float DeltaTime;
>     public EntityCommandBuffer.ParallelWriter Ecb;
>     public Entity ChildBulletPrefab; // 子子弹 Prefab
>
>     void Execute(
>         [ChunkIndexInQuery] int sortKey,
>         ref LocalTransform transform,
>         ref BulletLifetime lifetime,
>         in Entity entity)
>     {
>         // 碰撞检测（与移动 Job 相同，这里简化为统一在命中后触发）
>         lifetime.Remaining -= DeltaTime;
>
>         if (lifetime.Remaining <= 0f)
>         {
>             Ecb.DestroyEntity(sortKey, entity);
>             return;
>         }
>
>         // 命中检测
>         if (transform.Position.y < 0f)
>         {
>             // 生成 3 个子子弹，随机方向散射
>             var random = Unity.Mathematics.Random.CreateFromIndex((uint)(sortKey + entity.Index));
>
>             for (int i = 0; i < 3; i++)
>             {
>                 Entity child = Ecb.Instantiate(sortKey, ChildBulletPrefab);
>
>                 // 随机散射方向（锥形 60° 范围内）
>                 float angleY = random.NextFloat(-math.PI / 6f, math.PI / 6f);  // ±30° 水平
>                 float angleX = random.NextFloat(-math.PI / 6f, math.PI / 6f);   // ±30° 垂直
>
>                 quaternion scatterRot = math.mul(
>                     transform.Rotation,
>                     math.mul(
>                         quaternion.RotateY(angleY),
>                         quaternion.RotateX(angleX)));
>
>                 Ecb.SetComponent(sortKey, child, new LocalTransform
>                 {
>                     Position = transform.Position,
>                     Rotation = scatterRot,
>                     Scale = 1f
>                 });
>
>                 // 标记为子子弹（不可再分裂）
>                 Ecb.AddComponent<SubBulletTag>(sortKey, child);
>
>                 // 设置子子弹属性（速度减半，生命周期更短）
>                 Ecb.SetComponent(sortKey, child, new BulletSpeed { Value = 5f });
>                 Ecb.SetComponent(sortKey, child, new BulletLifetime { Remaining = 1f });
>             }
>
>             // 销毁母子弹
>             Ecb.DestroyEntity(sortKey, entity);
>         }
>     }
> }
>
> // === 调度 System ===
> [BurstCompile]
> public partial struct BulletChainReactionSystem : ISystem
> {
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         float deltaTime = SystemAPI.Time.DeltaTime;
>         var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
>         var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);
>
>         // 获取子子弹 Prefab（假设有单例提供）
>         Entity childPrefab = Entity.Null;
>         foreach (var data in SystemAPI.Query<RefRO<ChildBulletPrefabData>>())
>         {
>             childPrefab = data.ValueRO.PrefabEntity;
>             break;
>         }
>
>         if (childPrefab == Entity.Null) return;
>
>         // 先分裂（母子弹命中后生成子子弹）
>         var splitJob = new BulletSplitJob
>         {
>             DeltaTime = deltaTime,
>             Ecb = ecb.AsParallelWriter(),
>             ChildBulletPrefab = childPrefab
>         };
>         state.Dependency = splitJob.ScheduleParallel(state.Dependency);
>
>         // 再移动所有子弹（包括母和子）
>         var moveJob = new BulletChainReactionJob
>         {
>             DeltaTime = deltaTime,
>             Ecb = ecb.AsParallelWriter()
>         };
>         state.Dependency = moveJob.ScheduleParallel(state.Dependency);
>     }
> }
>
> public struct ChildBulletPrefabData : IComponentData
> {
>     public Entity PrefabEntity;
> }
> ```
>
> **关键设计：**
> - `[WithNone(typeof(SubBulletTag))]` 确保两次调度分离：母子弹走 SplitJob，子子弹只走移动
> - `SubBulletTag` 是纯标记组件，阻止无限递归分裂
> - `Unity.Mathematics.Random.CreateFromIndex((uint)(sortKey + entity.Index))` 为每个线程/Entity 产生确定性随机
> - 散射方向使用 `quaternion` 乘法组合旋转，避免万向锁
> - 执行顺序：先 Split（生成子子弹）→ 后 Move（移动所有子弹），子子弹在同一帧内就能移动

> [!tip]- 练习 3 参考答案（可选）
> ```csharp
> using Unity.Burst;
> using Unity.Entities;
> using Unity.Collections;
> using Unity.Mathematics;
> using Unity.Transforms;
>
> // === 事件类型定义 ===
> public enum EventType : byte
> {
>     PlayVFX,       // 播放特效
>     DealDamage,    // 造成伤害
>     PlaySound,     // 播放音效
>     SpawnEntity,   // 生成实体
> }
>
> // === 通用事件组件 ===
> public struct GameEvent : IComponentData
> {
>     public EventType Type;
>     public float3 Position;
>     public float FloatParam;      // 通用参数：伤害值/持续时间等
>     public int IntParam;          // 通用参数：音效 ID/实体类型等
>     public Entity TargetEntity;   // 可选：关联的目标 Entity
> }
>
> // === 事件分发 System ===
> [BurstCompile]
> [UpdateInGroup(typeof(SimulationSystemGroup))]
> [UpdateAfter(typeof(EndSimulationEntityCommandBufferSystem))]
> public partial struct EventDispatcherSystem : ISystem
> {
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         float deltaTime = SystemAPI.Time.DeltaTime;
>         var ecbSingleton = SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>();
>         var ecb = ecbSingleton.CreateCommandBuffer(state.WorldUnmanaged);
>
>         foreach (var (gameEvent, entity) in
>                  SystemAPI.Query<RefRO<GameEvent>>().WithEntityAccess())
>         {
>             switch (gameEvent.ValueRO.Type)
>             {
>                 case EventType.PlayVFX:
>                     HandlePlayVFX(ecb, gameEvent.ValueRO, entity);
>                     break;
>
>                 case EventType.DealDamage:
>                     HandleDealDamage(ecb, gameEvent.ValueRO, entity, ref state);
>                     break;
>
>                 case EventType.PlaySound:
>                     HandlePlaySound(ecb, gameEvent.ValueRO, entity);
>                     break;
>
>                 case EventType.SpawnEntity:
>                     HandleSpawnEntity(ecb, gameEvent.ValueRO, entity);
>                     break;
>             }
>         }
>     }
>
>     private void HandlePlayVFX(
>         EntityCommandBuffer ecb, GameEvent evt, Entity eventEntity)
>     {
>         // 创建 VFX 实体（带生命周期）
>         Entity vfxEntity = ecb.CreateEntity();
>         ecb.AddComponent(vfxEntity, LocalTransform.FromPosition(evt.Position));
>         ecb.AddComponent(vfxEntity, new TemporaryEffect
>         {
>             RemainingLifetime = evt.FloatParam, // 持续时间
>             EffectType = (EffectType)evt.IntParam
>         });
>
>         // 销毁事件实体
>         ecb.DestroyEntity(eventEntity);
>     }
>
>     private void HandleDealDamage(
>         EntityCommandBuffer ecb, GameEvent evt, Entity eventEntity,
>         ref SystemState state)
>     {
>         // 对目标 Entity 造成伤害
>         if (evt.TargetEntity != Entity.Null &&
>             SystemAPI.Exists(evt.TargetEntity))
>         {
>             var health = SystemAPI.GetComponentRW<Health>(evt.TargetEntity);
>             health.ValueRW.Current -= evt.FloatParam;
>         }
>
>         ecb.DestroyEntity(eventEntity);
>     }
>
>     private void HandlePlaySound(
>         EntityCommandBuffer ecb, GameEvent evt, Entity eventEntity)
>     {
>         // 创建音效事件实体（供音效 System 处理）
>         Entity soundEvent = ecb.CreateEntity();
>         ecb.AddComponent(soundEvent, new SoundEventData
>         {
>             SoundId = evt.IntParam,
>             Position = evt.Position
>         });
>
>         // 销毁原始事件
>         ecb.DestroyEntity(eventEntity);
>     }
>
>     private void HandleSpawnEntity(
>         EntityCommandBuffer ecb, GameEvent evt, Entity eventEntity)
>     {
>         // IntParam 存储 Entity 模板 ID（需配合查找表使用）
>         // Entity spawned = ecb.Instantiate(prefabLookup[evt.IntParam]);
>         // ecb.SetComponent(spawned, LocalTransform.FromPosition(evt.Position));
>
>         ecb.DestroyEntity(eventEntity);
>     }
> }
>
> // 音效数据（供后续处理）
> public struct SoundEventData : IComponentData
> {
>     public int SoundId;
>     public float3 Position;
> }
> ```
>
> **同一帧内事件处理的关键：**
> - **调度顺序至关重要**：
>   ```
>   SimulationSystemGroup
>     ├── AttackSystem (产生 GameEvent 实体，写入 ECB)
>     ├── EndSimulationEntityCommandBufferSystem (Playback: 事件实体正式创建)
>     ├── EffectSystem (产生更多 GameEvent)
>     ├── EndSimulationEntityCommandBufferSystem (Playback: 第二批事件)
>     ├── EventDispatcherSystem ([UpdateAfter]: 处理上一帧+当前帧的所有事件)
>     └── 下一帧开始
>   ```
> - 实际上，到 `EventDispatcherSystem` 执行时，同一帧创建的事件实体已经存在
> - 如果需要在**同一帧内**处理事件（产生者 → 消费者），需要将 Dispatcher 放在 `[UpdateAfter(typeof(EndSimulationEntityCommandBufferSystem))]`
> - 或者使用**手动 Playback**：Producer 立即 Playback ECB，然后 Consumer 查询新 Entity
>
> **扩展设计：**
> - 可以使用 `DynamicBuffer<GameEvent>` 替代创建/销毁实体，减少内存分配
> - 单例 `EventQueue` Buffer 作为全局事件总线
> - 多个 Consumer System 订阅不同类型事件（EventType mask 过滤）
---

## 4. 扩展阅读

- [ECB 官方文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-entity-command-buffer.html)
- [ECB Playback System 列表](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-entity-command-buffer-playback.html)
- [Structural Changes 最佳实践](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/performance-structural-changes.html)

---

## 常见陷阱

1. **ECB 操作的顺序**: ECB 按记录顺序执行。例如，先 `AddComponent<A>` 再 `SetComponent<A>` 是有效的——Set 会找到刚添加的组件并设置它。但先 `DestroyEntity` 再对该 Entity 操作是无效的（实体已被销毁）。

2. **`AsParallelWriter()` 的 sortKey**: 必须确保同一 Entity 的操作使用相同的 sortKey。通常使用 `[ChunkIndexInQuery]` 作为 sortKey，这样同一 Chunk 内的操作保持顺序。如果同一个 Entity 在多个线程中被操作，sortKey 保证它们按顺序执行。

3. **一个 ECB 的 Playback 次数**: 每个 ECB 实例只能 Playback 一次。如果需要多次执行，创建多个 ECB 实例。

4. **ECB 和 System 执行顺序**: ECB 的记录在 System 执行时发生，Playback 在 System Group 结束时发生。如果你在 System A 中记录了一个操作，并期望 System B（在 A 之后执行）看到结果，使用**手动 Playback**（因为自动 Playback 在 Group 结束时才执行，晚于 System B）。

5. **ECB 中的 Entity 引用**: ECB 记录的 Entity 是"未来的 Entity"——在 Playback 之前它只是一个占位符。不要尝试在同一个 ECB Playback 前通过 `SystemAPI` 查询这些 Entity（它们还不存在）。

6. **`EntityCommandBufferSystem` 的单例模式**: 使用 `SystemAPI.GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>()` 获取 ECB System 单例。每个 Playback System 只有一个实例。

7. **ECB 和 Job 依赖**: ECB 的 `CreateCommandBuffer()` 返回的 ECB 与 `state.Dependency` 无关。如果你在 Job 中通过 `AsParallelWriter()` 写入 ECB，确保 Job 的依赖被正确管理——ECB System 的 Playback 会自动等待所有相关的 JobHandle。
