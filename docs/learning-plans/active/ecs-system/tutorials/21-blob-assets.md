---
title: "Blob Assets 与共享组件"
updated: 2026-06-05
---

# Blob Assets 与共享组件

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 2.5 小时
> 前置知识: Baking（教程 19）、IComponentData 详解（教程 17）、内存布局知识

---

## 1. 概念讲解

### 为什么需要 Blob Assets？

在游戏中，大量实体共享相同的数据——例如所有同类型敌人有相同的属性表、所有同种武器有相同的伤害曲线。如果每个实体都存一份完整的数据，内存浪费严重。

传统的解决方案是"共享引用"（如 ScriptableObject），但在 ECS 中，数据必须是非托管的（Burst 兼容），且需要支持多线程读取。

**Blob Assets** 就是 ECS 对这个问题的答案：一个不可变的、引用计数的、Burst 兼容的共享数据容器。

### Blob Assets vs SharedComponent

| 特性 | BlobAssetReference<T> | ISharedComponentData |
|------|----------------------|---------------------|
| 数据存储 | 独立的内存块（非 Chunk） | Chunk 内（与实体一起） |
| 共享方式 | 多个实体持有同一个引用 | 相同值的实体放入同一 Chunk |
| 可变性 | 创建后不可变 | 值可以改变（但会触发 Chunk 迁移） |
| 大小 | 可以非常大（MB 级） | 受 Chunk 限制（建议 < 1KB） |
| Burst 兼容 | ✅ | ⚠️ 有限支持 |
| 访问速度 | 一次指针跳转 | Chunk 内直接访问 |
| 主要用途 | 大型配置表、技能数据、路径网格 | 小型共享属性（如材质 ID、队伍 ID） |

### 核心思想

**BlobAsset**: "写一次，读多次，绝不修改" — 创建代价较高，但读取零开销。适合静态配置数据。

**SharedComponent**: "相同值的实体分到一组" — 值变化时实体会迁移 Chunk，适合动态分组。

**选择原则**:
- 数据 > 1KB 且不可变 → BlobAsset
- 数据 < 1KB 且可能需要变 → SharedComponent
- 数据 < 1KB 且完全不变 → 两者皆可，BlobAsset 更高效

---

## 2. 代码示例

### 2.1 BlobAssetReference<T> 基础

```csharp
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;

// === Blob 数据定义 ===
public struct EnemyConfigBlob
{
    public float MaxHealth;
    public float MoveSpeed;
    public float AttackDamage;
    public float AttackRange;
    public float DetectionRadius;
    public float3 EyeOffset; // 视觉起点偏移

    // 支持字符串
    public BlobString Name; // 单个字符串
    public BlobArray<FixedString32Bytes> AbilityNames; // 技能名数组

    // 嵌套结构
    public BlobArray<DropItem> DropTable;
}

public struct DropItem
{
    public FixedString32Bytes ItemId;
    public float DropChance;
    public int MinCount;
    public int MaxCount;
}

// === 引用 BlobAsset 的组件 ===
public struct EnemyConfig : IComponentData
{
    public BlobAssetReference<EnemyConfigBlob> Config;
}
```

### 2.2 BlobBuilder 构造 BlobAsset

```csharp
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;

public static class EnemyConfigFactory
{
    // 在 Baking 阶段或 System.OnCreate 中调用
    public static BlobAssetReference<EnemyConfigBlob> CreateEnemyConfig(
        float maxHealth, float moveSpeed, float attackDamage,
        float attackRange, float detectionRadius,
        string name, string[] abilityNames,
        (string id, float chance, int min, int max)[] dropTable)
    {
        // 1. 创建 BlobBuilder
        using var builder = new BlobBuilder(Allocator.Temp);

        // 2. 分配根结构
        ref var root = ref builder.ConstructRoot<EnemyConfigBlob>();

        // 3. 填充简单字段
        root.MaxHealth = maxHealth;
        root.MoveSpeed = moveSpeed;
        root.AttackDamage = attackDamage;
        root.AttackRange = attackRange;
        root.DetectionRadius = detectionRadius;
        root.EyeOffset = new float3(0, 1.6f, 0);

        // 4. 分配 BlobString
        builder.AllocateString(ref root.Name, name);

        // 5. 分配 BlobArray（技能名）
        var abilities = builder.Allocate(ref root.AbilityNames, abilityNames.Length);
        for (int i = 0; i < abilityNames.Length; i++)
        {
            abilities[i] = abilityNames[i];
        }

        // 6. 分配嵌套 BlobArray（掉落表）
        var drops = builder.Allocate(ref root.DropTable, dropTable.Length);
        for (int i = 0; i < dropTable.Length; i++)
        {
            drops[i] = new DropItem
            {
                ItemId = dropTable[i].id,
                DropChance = dropTable[i].chance,
                MinCount = dropTable[i].min,
                MaxCount = dropTable[i].max
            };
        }

        // 7. 创建不可变引用
        return builder.CreateBlobAssetReference<EnemyConfigBlob>(Allocator.Persistent);
    }
}
```

### 2.3 System 中使用 BlobAsset

```csharp
using Unity.Burst;
using Unity.Entities;
using Unity.Mathematics;
using Unity.Transforms;

// === 敌人 AI System ===
[BurstCompile]
public partial struct EnemyAISystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;

        // 找到玩家位置
        float3 playerPos = float3.zero;
        foreach (var transform in SystemAPI.Query<RefRO<LocalTransform>>()
                     .WithAll<PlayerTag>())
        {
            playerPos = transform.ValueRO.Position;
            break;
        }

        new EnemyAIJob
        {
            DeltaTime = deltaTime,
            PlayerPosition = playerPos
        }.ScheduleParallel();
    }
}

[BurstCompile]
public partial struct EnemyAIJob : IJobEntity
{
    public float DeltaTime;
    public float3 PlayerPosition;

    void Execute(
        ref LocalTransform transform,
        ref Velocity velocity,
        in EnemyConfig config,           // 只读引用
        ref Health health,
        ref EnemyState state)
    {
        // 通过 .Config.Value 访问 Blob 数据
        ref var cfg = ref config.Config.Value;

        float distToPlayer = math.distance(transform.Position, PlayerPosition);

        switch (state.CurrentState)
        {
            case EnemyStateType.Idle:
                if (distToPlayer < cfg.DetectionRadius)
                {
                    state.CurrentState = EnemyStateType.Chase;
                }
                break;

            case EnemyStateType.Chase:
                float3 direction = math.normalize(PlayerPosition - transform.Position);
                velocity.Value = direction * cfg.MoveSpeed;
                transform.Rotation = quaternion.LookRotationSafe(direction, math.up());

                if (distToPlayer < cfg.AttackRange)
                {
                    state.CurrentState = EnemyStateType.Attack;
                    state.AttackCooldown = 0f;
                }
                break;

            case EnemyStateType.Attack:
                velocity.Value = float3.zero; // 停止移动
                state.AttackCooldown -= DeltaTime;

                if (distToPlayer > cfg.AttackRange)
                {
                    state.CurrentState = EnemyStateType.Chase;
                }
                else if (state.AttackCooldown <= 0f)
                {
                    // 造成伤害（通过 ECB 实现）
                    state.AttackCooldown = 1.5f;
                }
                break;
        }

        // 死亡检查
        if (health.Current <= 0f)
        {
            state.CurrentState = EnemyStateType.Dead;
        }
    }
}

// === 敌人状态 ===
public struct EnemyState : IComponentData
{
    public EnemyStateType CurrentState;
    public float AttackCooldown;
}

public enum EnemyStateType : byte
{
    Idle,
    Chase,
    Attack,
    Dead
}
```

### 2.4 ISharedComponentData — 共享组件

```csharp
using Unity.Entities;
using Unity.Mathematics;

// 使用 SharedComponent 按队伍分组
public struct TeamData : ISharedComponentData
{
    public int TeamId;
}

// 游戏设置（也适用 SharedComponent）
public struct DifficultySetting : ISharedComponentData
{
    public float DamageMultiplier;
    public float HealthMultiplier;
    public float SpawnRateMultiplier;
}

// === 使用 SharedComponent 的 System ===
[BurstCompile]
public partial struct TeamBasedSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 遍历 TeamData 时，Query 自动按 TeamId 分组
        // 每个唯一的 TeamId 值对应一个 Chunk
        foreach (var (team, entity) in
                 SystemAPI.Query<RefRO<TeamData>>().WithEntityAccess())
        {
            int teamId = team.ValueRO.TeamId;
            // 同一 Chunk 内的所有实体 teamId 相同
        }
    }
}

// === 运行时切换队伍的 System ===
public partial struct TeamSwitchSystem : ISystem
{
    public void OnUpdate(ref SystemState state)
    {
        var ecb = new EntityCommandBuffer(Allocator.Temp);

        foreach (var (health, entity) in
                 SystemAPI.Query<RefRO<Health>>()
                     .WithEntityAccess()
                     .WithNone<DeadTag>())
        {
            if (health.ValueRO.Current < health.ValueRO.Max * 0.3f)
            {
                // 血量低于 30%，切换到溃逃队伍
                ecb.SetSharedComponent(entity, new TeamData { TeamId = -1 }); // -1 = 溃逃队
            }
        }

        ecb.Playback(state.EntityManager);
        ecb.Dispose();
    }
}
```

### 2.5 BlobAsset 序列化与存储

```csharp
using Unity.Entities;
using Unity.Collections;
using System;
using System.IO;

// === 序列化 BlobAsset 到文件 ===
public static class BlobAssetSerializer
{
    // 保存 BlobAsset 到文件
    public static unsafe void SaveToFile<T>(
        BlobAssetReference<T> blob,
        string filePath) where T : unmanaged
    {
        // 获取 BlobAsset 的原始数据指针和大小
        void* dataPtr = blob.GetUnsafePtr();
        int dataSize = blob.Value.GetHashCode(); // 注意：这不是正确的大小

        // 正确做法：需要使用 unsafe 获取 BlobAsset 的内存大小
        // 简化示例
        byte[] bytes = new byte[sizeof(T)];
        fixed (byte* dest = bytes)
        {
            UnsafeUtility.MemCpy(dest, dataPtr, sizeof(T));
        }
        File.WriteAllBytes(filePath, bytes);
    }

    // 加载 BlobAsset 从文件
    public static unsafe BlobAssetReference<T> LoadFromFile<T>(
        string filePath) where T : unmanaged
    {
        byte[] bytes = File.ReadAllBytes(filePath);

        // 创建 BlobAsset
        using var builder = new BlobBuilder(Allocator.Temp);
        ref var root = ref builder.ConstructRoot<T>();

        fixed (byte* src = bytes)
        {
            UnsafeUtility.MemCpy(UnsafeUtility.AddressOf(ref root), src, bytes.Length);
        }

        return builder.CreateBlobAssetReference<T>(Allocator.Persistent);
    }
}

// === BakingSystem 中管理 BlobAsset 单例 ===
[WorldSystemFilter(WorldSystemFilterFlags.BakingSystem)]
public partial struct ConfigBakingSystem : ISystem
{
    public void OnUpdate(ref SystemState state)
    {
        // 存储所有已创建的 BlobAsset，防止内存泄漏
        var blobAssets = new NativeList<BlobAssetReference<EnemyConfigBlob>>(Allocator.Temp);

        foreach (var (configData, entity) in
                 SystemAPI.Query<RefRO<EnemyConfigData>>()
                     .WithAll<EnemyConfigTag>()
                     .WithEntityAccess())
        {
            var blobRef = EnemyConfigFactory.CreateEnemyConfig(
                configData.ValueRO.MaxHealth,
                configData.ValueRO.MoveSpeed,
                configData.ValueRO.AttackDamage,
                configData.ValueRO.AttackRange,
                configData.ValueRO.DetectionRadius,
                "Enemy",
                new[] { "Slash", "ShieldBash" },
                new (string, float, int, int)[] { ("Gold", 0.5f, 10, 50) }
            );

            blobAssets.Add(blobRef);

            var ecb = new EntityCommandBuffer(Allocator.Temp);
            ecb.RemoveComponent<EnemyConfigTag>(entity);
            ecb.RemoveComponent<EnemyConfigData>(entity);
            ecb.AddComponent(entity, new EnemyConfig { Config = blobRef });
            ecb.Playback(state.EntityManager);
            ecb.Dispose();
        }

        // BlobAsset 引用计数由 component 持有后自动管理
        // 当所有 EnemyConfig 组件被移除时，BlobAsset 自动释放
        blobAssets.Dispose();
    }
}
```

### 2.6 性能对比示例

```csharp
// 场景：10000 个敌人，每个持有配置表

// 方案 A：每个 Entity 存储完整配置（错误示范）
public struct BadEnemyConfig : IComponentData
{
    public float MaxHealth;
    public float MoveSpeed;
    public float AttackDamage;
    // ... 假设共 200 字节
}
// 内存：10000 × 200B = 2MB（每个实体独立复制）

// 方案 B：BlobAssetReference（推荐）
// 内存：10000 × 8B（引用）+ 1 × 200B（实际数据）≈ 78KB

// 方案 C：ISharedComponentData
// 内存：按 Chunk 去重，每个 Chunk 存一份。假设 100 个 Chunk：
//      100 × 200B = 20KB
// 但每次 Chunk 迁移有开销

// 方案 D：组合使用
// 小型共享属性用 SharedComponent（队伍 ID、难度等级）
// 大型配置表用 BlobAsset（技能表、掉落表）
```

**运行方式:** 在 Baking 阶段通过 `BakingSystem` 创建 BlobAsset 并存入组件引用。在 System 中通过 `config.Config.Value` 读取 Blob 数据。所有持有相同 BlobAsset 的 Entity 共享同一块内存。

**预期效果:**
- 10000 个敌人共享一个 BlobAsset 配置：内存节省 > 95%
- BlobAsset 读取速度接近直接访问 struct 字段（一次间接引用）
- SharedComponent 自动将相同值的实体分到同一 Chunk，减少 Chunk 碎片
- BlobAsset 创建后无法修改，天然线程安全——可以无锁并发读取

---

## 3. 练习

### 练习 1: 基础练习 — 创建武器配置 BlobAsset

实现：
- `WeaponConfigBlob` 包含 `Damage`、`Range`、`FireRate`、`ProjectileSpeed`
- `WeaponConfigBakingSystem` 读取 Scene 中的武器数据，生成 BlobAsset
- WeaponSystem 中使用 BlobAsset 读取武器参数

### 练习 2: 进阶练习 — 多层级 BlobArray

实现一个技能树 BlobAsset：
```
SkillTreeBlob
├── Name (BlobString)
├── Skills (BlobArray<SkillNode>)
│   ├── SkillNode
│   │   ├── SkillId (FixedString32)
│   │   ├── UnlockCost (int)
│   │   └── Children (BlobArray<int>)  // 子技能索引
```
练习构造和遍历该数据。

### 练习 3: 挑战练习（可选） — 空间分区 BlobAsset

使用 BlobAsset 存储预计算的 2D 空间网格：
```
SpatialGridBlob
├── GridSizeX, GridSizeY (int)
├── CellSize (float)
└── Cells (BlobArray<GridCell>)
    └── NeighborIndices (BlobArray<int>)
```
在 Job 中使用该 BlobAsset 进行快速邻近查询（替代运行时构建哈希表）。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```csharp
> using Unity.Entities;
> using Unity.Collections;
> using Unity.Mathematics;
> using UnityEngine;
>
> // === BlobAsset 数据结构 ===
> public struct WeaponConfigBlob
> {
>     public float Damage;
>     public float Range;
>     public float FireRate;
>     public float ProjectileSpeed;
> }
>
> // === 引用组件 ===
> public struct WeaponConfig : IComponentData
> {
>     public BlobAssetReference<WeaponConfigBlob> Config;
> }
>
> // === 中间数据组件（Baking 期间） ===
> public struct WeaponConfigTag : IComponentData { }
>
> public struct WeaponConfigData : IComponentData
> {
>     public float Damage;
>     public float Range;
>     public float FireRate;
>     public float ProjectileSpeed;
> }
>
> // === Authoring ===
> public class WeaponConfigAuthoring : MonoBehaviour
> {
>     public float Damage = 25f;
>     public float Range = 50f;
>     public float FireRate = 0.2f;
>     public float ProjectileSpeed = 100f;
>
>     class Baker : Baker<WeaponConfigAuthoring>
>     {
>         public override void Bake(WeaponConfigAuthoring authoring)
>         {
>             var entity = GetEntity(TransformUsageFlags.None);
>
>             // 标记需要后处理
>             AddComponent<WeaponConfigTag>(entity);
>             AddComponent(entity, new WeaponConfigData
>             {
>                 Damage = authoring.Damage,
>                 Range = authoring.Range,
>                 FireRate = authoring.FireRate,
>                 ProjectileSpeed = authoring.ProjectileSpeed
>             });
>         }
>     }
> }
>
> // === BakingSystem：生成 BlobAsset ===
> [WorldSystemFilter(WorldSystemFilterFlags.BakingSystem)]
> public partial struct WeaponConfigBakingSystem : ISystem
> {
>     public void OnUpdate(ref SystemState state)
>     {
>         var ecb = new EntityCommandBuffer(Allocator.Temp);
>
>         foreach (var (configData, entity) in
>                  SystemAPI.Query<RefRO<WeaponConfigData>>()
>                      .WithAll<WeaponConfigTag>()
>                      .WithEntityAccess())
>         {
>             // 创建 BlobAsset
>             using var blobBuilder = new BlobBuilder(Allocator.Temp);
>             ref var root = ref blobBuilder.ConstructRoot<WeaponConfigBlob>();
>
>             root.Damage = configData.ValueRO.Damage;
>             root.Range = configData.ValueRO.Range;
>             root.FireRate = configData.ValueRO.FireRate;
>             root.ProjectileSpeed = configData.ValueRO.ProjectileSpeed;
>
>             var blobRef = blobBuilder.CreateBlobAssetReference<WeaponConfigBlob>(Allocator.Persistent);
>
>             // 替换中间数据为引用组件
>             ecb.RemoveComponent<WeaponConfigTag>(entity);
>             ecb.RemoveComponent<WeaponConfigData>(entity);
>             ecb.AddComponent(entity, new WeaponConfig { Config = blobRef });
>         }
>
>         ecb.Playback(state.EntityManager);
>         ecb.Dispose();
>     }
> }
>
> // === 运行时 WeaponSystem 使用 BlobAsset ===
> [BurstCompile]
> public partial struct WeaponSystem : ISystem
> {
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         float deltaTime = SystemAPI.Time.DeltaTime;
>
>         foreach (var (weapon, config, cooldown) in
>                  SystemAPI.Query<RefRW<Weapon>, RefRO<WeaponConfig>, RefRW<WeaponCooldown>>())
>         {
>             // 通过 .Config.Value 访问 Blob 中的只读数据
>             ref var cfg = ref config.ValueRO.Config.Value;
>
>             cooldown.ValueRW.Remaining -= deltaTime;
>             if (cooldown.ValueRO.Remaining <= 0f)
>             {
>                 // 开火：使用 Blob 中的参数
>                 cooldown.ValueRW.Remaining = cfg.FireRate;
>                 // 发射逻辑使用 cfg.Damage, cfg.Range, cfg.ProjectileSpeed...
>             }
>         }
>     }
> }
>
> public struct WeaponCooldown : IComponentData
> {
>     public float Remaining;
> }
> ```
>
> **设计要点：**
> - Authoring 在 Inspector 中可编辑 → Baker 转成中间数据 → BakingSystem 后处理生成 BlobAsset
> - BakingSystem 使用 `[WorldSystemFilter(WorldSystemFilterFlags.BakingSystem)]` 只在 Baking 时运行
> - 运行时通过 `config.ValueRO.Config.Value` 访问（两次解引用：组件引用 → BlobAssetReference → Blob 数据）
> - BlobAsset 不可变 → 天然线程安全，可在多个 Job 中并发读取

> [!tip]- 练习 2 参考答案
> ```csharp
> using Unity.Entities;
> using Unity.Collections;
> using Unity.Mathematics;
>
> // === BlobAsset 数据结构（多层嵌套） ===
> public struct SkillTreeBlob
> {
>     public BlobString Name;
>     public BlobArray<SkillNode> Skills;
> }
>
> public struct SkillNode
> {
>     public FixedString32Bytes SkillId;
>     public int UnlockCost;
>     public BlobArray<int> Children; // 子技能在 Skills 数组中的索引
> }
>
> // === 工厂方法构造技能树 ===
> public static class SkillTreeFactory
> {
>     public static BlobAssetReference<SkillTreeBlob> CreateWarriorTree()
>     {
>         using var builder = new BlobBuilder(Allocator.Temp);
>         ref var root = ref builder.ConstructRoot<SkillTreeBlob>();
>
>         builder.AllocateString(ref root.Name, "Warrior");
>
>         // 分配技能数组
>         var skills = builder.Allocate(ref root.Skills, 5);
>
>         // Skill 0: 重击（根技能，解锁 Skill 1 和 Skill 2）
>         skills[0] = new SkillNode
>         {
>             SkillId = "HeavyStrike",
>             UnlockCost = 0
>         };
>         var children0 = builder.Allocate(ref skills[0].Children, 2);
>         children0[0] = 1; // → 旋风斩
>         children0[1] = 2; // → 盾击
>
>         // Skill 1: 旋风斩（子技能，解锁 Skill 3）
>         skills[1] = new SkillNode
>         {
>             SkillId = "Whirlwind",
>             UnlockCost = 3
>         };
>         var children1 = builder.Allocate(ref skills[1].Children, 1);
>         children1[0] = 3; // → 剑刃风暴
>
>         // Skill 2: 盾击（子技能，解锁 Skill 4）
>         skills[2] = new SkillNode
>         {
>             SkillId = "ShieldBash",
>             UnlockCost = 2
>         };
>         var children2 = builder.Allocate(ref skills[2].Children, 1);
>         children2[0] = 4; // → 神圣壁垒
>
>         // Skill 3: 剑刃风暴（叶子节点）
>         skills[3] = new SkillNode
>         {
>             SkillId = "BladeStorm",
>             UnlockCost = 5
>         };
>         var children3 = builder.Allocate(ref skills[3].Children, 0); // 无子节点
>
>         // Skill 4: 神圣壁垒（叶子节点）
>         skills[4] = new SkillNode
>         {
>             SkillId = "HolyBulwark",
>             UnlockCost = 4
>         };
>         var children4 = builder.Allocate(ref skills[4].Children, 0);
>
>         return builder.CreateBlobAssetReference<SkillTreeBlob>(Allocator.Persistent);
>     }
> }
>
> // === 遍历技能树（BFS 示例） ===
> [BurstCompile]
> public partial struct SkillTreeTraversalSystem : ISystem
> {
>     [BurstCompile]
>     public void OnUpdate(ref SystemState state)
>     {
>         foreach (var tree in SystemAPI.Query<RefRO<SkillTreeBlobRef>>())
>         {
>             ref var blob = ref tree.ValueRO.Data.Value;
>             ref var skills = ref blob.Skills;
>
>             // 使用 NativeQueue 做 BFS 遍历
>             var queue = new NativeQueue<int>(Allocator.Temp);
>             queue.Enqueue(0); // 从根技能开始
>
>             while (queue.TryDequeue(out int skillIndex))
>             {
>                 ref var node = ref skills[skillIndex];
>
>                 // 打印技能信息
>                 // Debug.Log($"Skill: {node.SkillId}, Cost: {node.UnlockCost}");
>
>                 // 将子节点入队
>                 ref var children = ref node.Children;
>                 for (int i = 0; i < children.Length; i++)
>                 {
>                     queue.Enqueue(children[i]);
>                 }
>             }
>
>             queue.Dispose();
>         }
>     }
> }
>
> public struct SkillTreeBlobRef : IComponentData
> {
>     public BlobAssetReference<SkillTreeBlob> Data;
> }
> ```
>
> **多层 BlobArray 要点：**
> - `BlobArray<int>` 存储的是**索引**而非引用（BlobAsset 不支持嵌套引用）
> - 每个 `Children` 数组必须单独调用 `builder.Allocate()` 分配
> - 遍历时用索引回查 `Skills` 数组获取实际节点
> - BFS/DFS 需要辅助数据结构（`NativeQueue`/`NativeList`）——不能用递归（Burst 限制）

> [!tip]- 练习 3 参考答案（可选）
> ```csharp
> using Unity.Entities;
> using Unity.Collections;
> using Unity.Mathematics;
>
> // === 空间网格 BlobAsset 结构 ===
> public struct SpatialGridBlob
> {
>     public int GridSizeX;
>     public int GridSizeY;
>     public float CellSize;
>     public BlobArray<GridCell> Cells;
> }
>
> public struct GridCell
> {
>     public int CellIndex;
>     public int2 GridCoord;
>     public BlobArray<int> NeighborIndices; // 相邻 Cell 的索引（包含自身）
> }
>
> // === 工厂方法：预计算网格邻接关系 ===
> public static class SpatialGridFactory
> {
>     public static BlobAssetReference<SpatialGridBlob> Create(
>         int gridSizeX, int gridSizeY, float cellSize)
>     {
>         using var builder = new BlobBuilder(Allocator.Temp);
>         ref var root = ref builder.ConstructRoot<SpatialGridBlob>();
>
>         root.GridSizeX = gridSizeX;
>         root.GridSizeY = gridSizeY;
>         root.CellSize = cellSize;
>
>         int totalCells = gridSizeX * gridSizeY;
>         var cells = builder.Allocate(ref root.Cells, totalCells);
>
>         // 预计算每个 Cell 的邻居
>         var tempNeighbors = new NativeList<int>(9, Allocator.Temp);
>
>         for (int y = 0; y < gridSizeY; y++)
>         {
>             for (int x = 0; x < gridSizeX; x++)
>             {
>                 int cellIdx = y * gridSizeX + x;
>                 cells[cellIdx].GridCoord = new int2(x, y);
>
>                 tempNeighbors.Clear();
>
>                 // 3×3 邻域（包含自身）
>                 for (int dy = -1; dy <= 1; dy++)
>                 {
>                     for (int dx = -1; dx <= 1; dx++)
>                     {
>                         int nx = x + dx;
>                         int ny = y + dy;
>                         if (nx >= 0 && nx < gridSizeX && ny >= 0 && ny < gridSizeY)
>                         {
>                             tempNeighbors.Add(ny * gridSizeX + nx);
>                         }
>                     }
>                 }
>
>                 // 分配邻居数组
>                 var neighbors = builder.Allocate(ref cells[cellIdx].NeighborIndices,
>                     tempNeighbors.Length);
>                 for (int i = 0; i < tempNeighbors.Length; i++)
>                 {
>                     neighbors[i] = tempNeighbors[i];
>                 }
>             }
>         }
>
>         tempNeighbors.Dispose();
>         return builder.CreateBlobAssetReference<SpatialGridBlob>(Allocator.Persistent);
>     }
> }
>
> // === Job 中使用预计算网格进行邻近查询 ===
> [BurstCompile]
> public partial struct SpatialQueryWithBlobJob : IJobEntity
> {
>     public BlobAssetReference<SpatialGridBlob> Grid;
>     [ReadOnly] public NativeMultiHashMap<int, Entity> SpatialMap;
>
>     void Execute(
>         in LocalTransform transform,
>         in Entity entity,
>         in QueryRadius radius)
>     {
>         ref var grid = ref Grid.Value;
>
>         // 计算当前 Cell 索引
>         int cx = (int)math.floor(transform.Position.x / grid.CellSize);
>         int cy = (int)math.floor(transform.Position.z / grid.CellSize); // 2D 示例
>         cx = math.clamp(cx, 0, grid.GridSizeX - 1);
>         cy = math.clamp(cy, 0, grid.GridSizeY - 1);
>         int cellIdx = cy * grid.GridSizeX + cx;
>
>         // 遍历当前 Cell 及其预计算邻居
>         ref var neighbors = ref grid.Cells[cellIdx].NeighborIndices;
>         for (int ni = 0; ni < neighbors.Length; ni++)
>         {
>             int neighborIdx = neighbors[ni];
>
>             if (SpatialMap.TryGetFirstValue(neighborIdx, out Entity other, out var iter))
>             {
>                 do
>                 {
>                     if (other == entity) continue;
>                     // 精确距离检测
>                     // float dist = math.distance(transform.Position, otherPos);
>                     // if (dist < radius.Value) { /* 碰撞响应 */ }
>                 }
>                 while (SpatialMap.TryGetNextValue(out other, ref iter));
>             }
>         }
>     }
> }
>
> public struct QueryRadius : IComponentData
> {
>     public float Value;
> }
> ```
>
> **BlobAsset 空间网格的优势：**
> - 邻接关系在 Baking 时**预计算一次**，运行时直接查表（零 CPU 开销）
> - 不需要运行时构建哈希表键（节省 `cellX * prime ^ cellZ * prime` 计算）
> - `BlobArray<int>` 存储邻居索引使遍历极快（连续内存、缓存友好）
> - 适用于固定大小的地图网格（如 RTS 地图、寻路网格）
> - 边界 Cell 的邻居数 < 9（自动处理地图边界）
---

## 4. 扩展阅读

- [Blob Assets 官方文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/blob-assets.html)
- [ISharedComponentData 文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/components-shared.html)
- [BlobBuilder API](https://docs.unity3d.com/Packages/com.unity.entities@1.0/api/Unity.Entities.BlobBuilder.html)
- [数据导向设计原则](https://www.dataorienteddesign.com/dodbook/)

---

## 常见陷阱

1. **修改 BlobAsset 数据**: BlobAsset 创建后不可修改。任何对 `ref var cfg = ref config.Config.Value` 后字段赋值的行为都是 **未定义行为**（可能静默损坏数据或崩溃）。需要修改用普通 IComponentData。

2. **BlobAsset 生命周期**: BlobAsset 使用引用计数。当所有持有该引用的组件被销毁后，BlobAsset 自动释放。不要在组件外部手动 Dispose BlobAssetReference（除非你用 `Allocator.Persistent` 自己管理）。

3. **BlobString vs BlobArray<char>**: BlobString 有固定最大长度（基于分配大小）。创建时用 `builder.AllocateString(ref root.Name, "text")`。读取时可以直接用 `root.Name.ToString()`。

4. **SharedComponent 的大小限制**: 建议 < 1KB。大型共享数据使用 BlobAsset + IComponentData 组合。过大的 SharedComponent 会导致 Chunk 利用率低。

5. **Chunk 迁移**: 修改 SharedComponent 的值会导致实体从当前 Chunk 迁移到新 Chunk（因为相同 SharedComponent 值的实体必须在同一 Chunk）。频繁修改 SharedComponent 会产生大量迁移开销。

6. **BlobAsset 中的引用**: BlobAsset 不能包含对其他 BlobAsset 的引用（`BlobAssetReference<T>` 不能作为 Blob 结构体字段）。使用 ID 索引代替引用。

7. **Burst 兼容性**: `BlobArray<T>` 和 `BlobString` 中的 T 必须是 unmanaged 类型。对于字符串，使用 `FixedString32Bytes` 或 `FixedString64Bytes`。
