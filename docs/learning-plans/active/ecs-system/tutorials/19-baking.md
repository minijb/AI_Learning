# Baking 与 Authoring

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 3 小时
> 前置知识: IComponentData 详解（教程 17）、System 编写（教程 18）、Unity Prefab/Scene 基础

---

## 1. 概念讲解

### 为什么需要 Baking？

在纯 ECS 世界中，Entity 没有 Inspector 面板，没有可视化编辑能力——它们只是数据和索引。但游戏开发需要可视化编辑和设计师友好的工作流。

**Baking** 是连接 GameObject 世界（编辑时）和 Entity 世界（运行时）的桥梁。它将 Scene/Prefab 中的 GameObject 和 MonoBehaviour 转换为 Entity 和 IComponentData。

### Baking 的工作流程

```
编辑时 (Editor)                     运行时 (Player)
┌─────────────────────┐           ┌─────────────────────┐
│  SubScene            │           │  World               │
│  ┌─────────────────┐ │  Baking   │  ┌─────────────────┐ │
│  │ GameObject       │ │ ═══════► │  │ Entity           │ │
│  │ ├─ Transform     │ │           │  │ ├─ LocalTransform│ │
│  │ ├─ MeshRenderer  │ │           │  │ ├─ RenderMesh    │ │
│  │ └─ MyAuthoring   │ │           │  │ └─ MyComponent   │ │
│  └─────────────────┘ │           │  └─────────────────┘ │
│                       │           │                       │
│  Prefab               │  Baking   │  Entity (模板)        │
│  ┌─────────────────┐ │ ═══════► │  ┌─────────────────┐ │
│  │ GameObject       │ │           │  │ 可以运行时实例化   │ │
│  │ └─ MyAuthoring   │ │           │  └─────────────────┘ │
│  └─────────────────┘ │           │                       │
└─────────────────────┘           └─────────────────────┘
```

### 核心概念

**Baker<T>** — 每个 Authoring MonoBehaviour 的内部类，负责将 GameObject 数据转换为 Entity 组件。在 Baking 阶段执行一次。

**BakingSystem** — 全局的后处理系统，在所有 Baker 执行完后运行。通常用于生成 BlobAsset、合并数据等跨 Entity 操作。

**SubScene** — 包含一组 GameObject 的"ECS 场景"。SubScene 中的 GameObject 在编辑时可见可编辑，在运行时被自动 Baking 为 Entity，原始 GameObject 不再存在。

**TransformUsageFlags** — 告诉 Baker 该 Entity 的 Transform 使用方式，决定生成哪些 Transform 组件（`LocalTransform`、`LocalToWorld`、`Parent` 等）。

### 核心思想

"Author once, run everywhere." — 你在 Inspector 中编辑的数据，自动转换为高性能的 ECS 表示。不需要手动创建 Entity、添加组件。

---

## 2. 代码示例

### 2.1 基础 Baking — 简单的武器组件

```csharp
using Unity.Entities;
using Unity.Mathematics;
using UnityEngine;

// === 组件定义 ===
public struct Weapon : IComponentData
{
    public float Damage;
    public float Range;
    public float FireRate;
    public float CooldownRemaining;
    public Entity ProjectilePrefab; // 子弹 Prefab 的 Entity 引用
}

public struct AmmoClip : IComponentData
{
    public int CurrentAmmo;
    public int MaxAmmo;
    public float ReloadTime;
}

// === Authoring ===
public class WeaponAuthoring : MonoBehaviour
{
    [Header("武器属性")]
    public float Damage = 25f;
    public float Range = 50f;
    public float FireRate = 0.2f;

    [Header("弹药")]
    public int MaxAmmo = 30;

    [Header("子弹 Prefab")]
    public GameObject ProjectilePrefab; // 必须也是 ECS Prefab（即在 SubScene 中或已 Baking 过）

    class Baker : Baker<WeaponAuthoring>
    {
        public override void Bake(WeaponAuthoring authoring)
        {
            // 获取 Entity（告诉 Baker 该 GameObject 使用动态 Transform）
            var entity = GetEntity(TransformUsageFlags.Dynamic);

            // 添加武器组件
            AddComponent(entity, new Weapon
            {
                Damage = authoring.Damage,
                Range = authoring.Range,
                FireRate = authoring.FireRate,
                CooldownRemaining = 0f,
                // 将 GameObject 引用转为 Entity 引用
                ProjectilePrefab = GetEntity(authoring.ProjectilePrefab, TransformUsageFlags.Dynamic)
            });

            // 添加弹药组件
            AddComponent(entity, new AmmoClip
            {
                CurrentAmmo = authoring.MaxAmmo,
                MaxAmmo = authoring.MaxAmmo,
                ReloadTime = 1.5f
            });
        }
    }
}
```

### 2.2 角色 Authoring — 组合多个组件

```csharp
using Unity.Entities;
using Unity.Mathematics;
using UnityEngine;

// === 角色相关组件 ===
public struct CharacterTag : IComponentData { }

public struct MovementInput : IComponentData
{
    public float2 Value;
}

public struct CharacterStats : IComponentData
{
    public float MaxHealth;
    public float CurrentHealth;
    public float Armor;
    public float MoveSpeed;
}

// === Authoring ===
public class CharacterAuthoring : MonoBehaviour
{
    [Header("基础属性")]
    public float MaxHealth = 100f;
    public float Armor = 10f;
    public float MoveSpeed = 5f;

    [Header("装备")]
    public GameObject DefaultWeaponPrefab;

    class Baker : Baker<CharacterAuthoring>
    {
        public override void Bake(CharacterAuthoring authoring)
        {
            var entity = GetEntity(TransformUsageFlags.Dynamic);

            // 添加标签
            AddComponent<CharacterTag>(entity);

            // 添加输入组件（初始化为零）
            AddComponent(entity, new MovementInput { Value = float2.zero });

            // 添加属性组件
            AddComponent(entity, new CharacterStats
            {
                MaxHealth = authoring.MaxHealth,
                CurrentHealth = authoring.MaxHealth,
                Armor = authoring.Armor,
                MoveSpeed = authoring.MoveSpeed
            });

            // 将默认武器作为子实体添加
            if (authoring.DefaultWeaponPrefab != null)
            {
                var weaponEntity = GetEntity(authoring.DefaultWeaponPrefab, TransformUsageFlags.Dynamic);

                // 添加 Parent 组件，让武器跟随角色
                AddComponent(entity, new Parent { Value = weaponEntity });
            }
        }
    }
}
```

### 2.3 BakingSystem — 后处理生成 BlobAsset

```csharp
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;
using UnityEngine;

// === BlobAsset 数据结构 ===
public struct EnemyConfigBlob
{
    public float Health;
    public float Speed;
    public float Damage;
    public float3 SpawnOffset;
    public BlobArray<FixedString32Bytes> BehaviorNames; // 行为树节点名数组
}

// === 组件（引用 BlobAsset）===
public struct EnemyConfigReference : IComponentData
{
    public BlobAssetReference<EnemyConfigBlob> Config;
}

// === Authoring ===
public class EnemyConfigAuthoring : MonoBehaviour
{
    public float Health = 50f;
    public float Speed = 3f;
    public float Damage = 15f;
    public Vector3 SpawnOffset = Vector3.up;
    public string[] Behaviors = { "Idle", "Patrol", "Chase", "Attack" };

    class Baker : Baker<EnemyConfigAuthoring>
    {
        public override void Bake(EnemyConfigAuthoring authoring)
        {
            var entity = GetEntity(TransformUsageFlags.None);

            // 注意：这里只添加一个标记，实际 BlobAsset 在 BakingSystem 中创建
            // (因为 BlobAsset 需要在 Baking 的最后阶段构建，此时所有数据已就绪)
            AddComponent<EnemyConfigTag>(entity);
            AddComponent(entity, new EnemyConfigData
            {
                Health = authoring.Health,
                Speed = authoring.Speed,
                Damage = authoring.Damage,
                SpawnOffset = authoring.SpawnOffset,
            });
        }
    }
}

// 中间数据组件（仅在 Baking 期间存在）
public struct EnemyConfigTag : IComponentData { }
public struct EnemyConfigData : IComponentData
{
    public float Health;
    public float Speed;
    public float Damage;
    public float3 SpawnOffset;
    // BlobString 在 Baking 数据中不方便传，这里简化
}

// === BakingSystem ===
[WorldSystemFilter(WorldSystemFilterFlags.BakingSystem)]
public partial struct EnemyConfigBakingSystem : ISystem
{
    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        var ecb = new EntityCommandBuffer(Allocator.Temp);

        foreach (var (configData, entity) in
                 SystemAPI.Query<RefRO<EnemyConfigData>>()
                     .WithAll<EnemyConfigTag>()
                     .WithEntityAccess())
        {
            // 创建 BlobAsset
            using var blobBuilder = new BlobBuilder(Allocator.Temp);
            ref var root = ref blobBuilder.ConstructRoot<EnemyConfigBlob>();

            root.Health = configData.ValueRO.Health;
            root.Speed = configData.ValueRO.Speed;
            root.Damage = configData.ValueRO.Damage;
            root.SpawnOffset = configData.ValueRO.SpawnOffset;

            // 分配 BehaviorNames 数组
            var behaviors = blobBuilder.Allocate(ref root.BehaviorNames, 4);
            behaviors[0] = "Idle";
            behaviors[1] = "Patrol";
            behaviors[2] = "Chase";
            behaviors[3] = "Attack";

            var blobRef = blobBuilder.CreateBlobAssetReference<EnemyConfigBlob>(Allocator.Persistent);

            // 替换组件：移除中间数据，添加引用组件
            ecb.RemoveComponent<EnemyConfigTag>(entity);
            ecb.RemoveComponent<EnemyConfigData>(entity);
            ecb.AddComponent(entity, new EnemyConfigReference { Config = blobRef });
        }

        ecb.Playback(state.EntityManager);
        ecb.Dispose();
    }
}
```

### 2.4 Prefab Baking — 运行时实例化

```csharp
using Unity.Entities;
using UnityEngine;

// 将一个 GameObject 标记为 ECS Prefab
public class BulletAuthoring : MonoBehaviour
{
    public float Speed = 20f;
    public float Lifetime = 3f;
    public GameObject HitEffectPrefab;

    class Baker : Baker<BulletAuthoring>
    {
        public override void Bake(BulletAuthoring authoring)
        {
            var entity = GetEntity(TransformUsageFlags.Dynamic);

            AddComponent(entity, new Bullet
            {
                Speed = authoring.Speed,
                RemainingLifetime = authoring.Lifetime
            });

            // 添加 Prefab 标签——使该 Entity 成为 Prefab
            // 这样运行时可以通过 ECB.Instantiate 来创建实例
            AddComponent<Prefab>(entity);
        }
    }
}

public struct Bullet : IComponentData
{
    public float Speed;
    public float RemainingLifetime;
}
```

### 2.5 综合示例 — 带武器的角色 Prefab Baking

```csharp
// === 1. 组件定义 ===
public struct FireInput : IComponentData
{
    public bool IsFiring;
}

// === 2. 角色 Prefab Authoring ===
public class PlayerPrefabAuthoring : MonoBehaviour
{
    [Header("角色属性")]
    public float MaxHealth = 100f;
    public float MoveSpeed = 5f;

    [Header("武器挂点")]
    public Transform WeaponSocket; // 武器生成的父节点

    [Header("初始武器")]
    public GameObject StartingWeaponPrefab;

    class Baker : Baker<PlayerPrefabAuthoring>
    {
        public override void Bake(PlayerPrefabAuthoring authoring)
        {
            // 角色本身
            var playerEntity = GetEntity(TransformUsageFlags.Dynamic);

            AddComponent<PlayerTag>(playerEntity);
            AddComponent<Prefab>(playerEntity); // 标记为 Prefab
            AddComponent(playerEntity, new CharacterStats
            {
                MaxHealth = authoring.MaxHealth,
                CurrentHealth = authoring.MaxHealth,
                Armor = 0f,
                MoveSpeed = authoring.MoveSpeed
            });
            AddComponent(playerEntity, new MovementInput { Value = float2.zero });
            AddComponent(playerEntity, new FireInput { IsFiring = false });

            // 武器作为子实体
            if (authoring.WeaponSocket != null && authoring.StartingWeaponPrefab != null)
            {
                var weaponEntity = GetEntity(authoring.StartingWeaponPrefab, TransformUsageFlags.Dynamic);
                // 注意：武器 Prefab 应该已经通过 Baking 生成了自己的 Entity
                // 这里只是记录引用
                AddComponent(playerEntity, new Child { Value = weaponEntity });
            }
        }
    }
}

// === 3. 运行时生成玩家的 System ===
[BurstCompile]
public partial struct PlayerSpawnSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        state.RequireForUpdate<PlayerPrefabData>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        // 读取场景中存放的 Prefab 引用
        foreach (var prefabData in SystemAPI.Query<RefRO<PlayerPrefabData>>())
        {
            var ecb = new EntityCommandBuffer(Allocator.Temp);

            // 实例化 Prefab
            var playerInstance = ecb.Instantiate(prefabData.ValueRO.PrefabEntity);

            // 设置初始位置
            ecb.SetComponent(playerInstance, LocalTransform.FromPosition(0, 1, 0));

            ecb.Playback(state.EntityManager);
            ecb.Dispose();

            // 只生成一次后退出
            break;
        }
    }
}

// 存放 Prefab 引用的单例组件（通常由一个 GameObject 的 Authoring 提供）
public struct PlayerPrefabData : IComponentData
{
    public Entity PrefabEntity;
}
```

**运行方式:** 在 Unity 中创建 SubScene。为每个 Authoring 脚本对应的 GameObject 挂载相应组件。将 Bullet Prefab 和角色 Prefab 也放入 SubScene。运行时，Baking 自动将所有数据转换为 Entity。

**预期效果:** 编辑时修改 Inspector 中的数值（如 Damage、MaxHealth），运行时自动反映到对应的 Entity 组件中。BakingSystem 在所有 Baker 之后执行，生成 BlobAsset 等共享数据。Prefab 通过 `AddComponent<Prefab>(entity)` 标记，运行时通过 `ECB.Instantiate` 创建实例。

---

## 3. 练习

### 练习 1: 基础练习 — 创建一个可配置的障碍物 Authoring

实现：
- `ObstacleAuthoring` MonoBehaviour，包含 `float Radius` 和 `float DamagePerSecond`
- Baker 将其转换为 `Obstacle` 和 `CircleCollider` 组件
- 注意正确使用 `TransformUsageFlags`

### 练习 2: 进阶练习 — BakingSystem 生成技能表 BlobAsset

实现：
- `SkillDataAuthoring` 包含技能数组（名称、伤害、冷却、图标名）
- Baker 只收集原始数据
- `SkillDataBakingSystem` 将数据合并生成 `BlobAssetReference<SkillTableBlob>`
- 将 BlobAsset 引用存入单例组件 `SkillTable`

### 练习 3: 挑战练习（可选） — 嵌套 Prefab 的角色装备系统

实现：
- 角色 Prefab 有一个 `WeaponSocket` Transform
- 武器 Prefab 独立 Baking
- 在 `PlayerSpawnSystem` 中同时实例化角色和武器，并设置 `Parent` 关系
- 提示：使用 `ECB.Instantiate` + `ECB.SetComponent` 设置 `Parent`

---

## 4. 扩展阅读

- [Baking 官方文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/baking.html)
- [BakingSystem 详解](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/baking-baking-system.html)
- [SubScene 使用指南](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/conversion-subscenes.html)
- [TransformUsageFlags 说明](https://docs.unity3d.com/Packages/com.unity.entities@1.0/api/Unity.Entities.TransformUsageFlags.html)

---

## 常见陷阱

1. **TransformUsageFlags 设置错误**: 
   - `None`: 不需要 Transform（纯数据 Entity）
   - `Dynamic`: 运行时会移动/旋转的实体
   - `Renderable`: 需要渲染的静态实体
   - 设置错误会导致缺少 `LocalTransform` 组件或渲染不可见。

2. **Baker 中的 GetEntity 调用次数**: 对同一个 GameObject 多次调用 `GetEntity()` 返回同一个 Entity。但要注意参数一致性。

3. **BakingSystem 不应修改 GameObject**: BakingSystem 运行在 Baking World 中，此时 GameObject 可能已被销毁。只应操作 Entity。

4. **BlobAsset 的生命周期**: 在 BakingSystem 中创建的 `BlobAssetReference` 必须是 `Allocator.Persistent`，因为要在运行时使用。BlobAsset 是不可变的共享数据，创建后无法修改。

5. **SubScene 中的引用**: 跨 SubScene 的 GameObject 引用在 Baking 时可能无法解析。将关联对象放在同一个 SubScene 内。

6. **不要混淆 Prefab 和普通 Entity**: 运行时实例化的模板必须添加 `Prefab` 标签组件。否则 ECS 会把它当作场景中的活动 Entity。
