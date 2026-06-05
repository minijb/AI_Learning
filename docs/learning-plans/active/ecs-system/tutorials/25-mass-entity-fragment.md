---
title: "Mass Entity 与 Fragment 详解"
updated: 2026-06-05
---

# Mass Entity 与 Fragment 详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 2.5h
> 前置知识: Mass 框架总览、ECS 组件概念

---

## 1. 概念讲解

### 为什么需要这个？

在传统 ECS 中，Component 是挂载在 Entity 上的数据块。Mass 的 Fragment 继承了这一思想，但针对 UE 生态做了三层分化——**纯数据 Fragment**、**共享数据 Fragment**、**零开销 Tag**——分别解决不同场景下的内存和查找效率问题。理解这三种 Fragment 的区别，是写出高性能 Mass 代码的前提。

### 核心思想

#### 1.1 FMassEntityHandle — 轻量实体句柄

`FMassEntityHandle` 是 Mass 实体的唯一标识，本质上是一个包装了 32 位整数索引和 16 位序列号的轻量结构体：

```cpp
// MassEntityTypes.h (简化)
struct FMassEntityHandle
{
    int32 Index;    // 在 EntityManager 内部数组中的位置
    int32 SerialNumber; // 防止 ABA 问题（重用检测）

    bool IsSet() const { return Index != InvalidIndex; }
    bool operator==(const FMassEntityHandle& Other) const;
};
```

**关键特性：**
- 无虚函数，无指针，可直接按值传递
- 自身不是实体对象——只是指向 `FMassEntityManager` 内部数据的键
- 销毁后重用索引时，`SerialNumber` 递增，老句柄自动失效（类似 ABA 防护）

#### 1.2 Fragment 类型体系

Mass 将 ECS 的 Component 细化为三种 Fragment：

| Fragment 类型 | 基类 | 存储方式 | 典型用途 |
|--------------|------|---------|---------|
| **FMassFragment** | 按实体独立存储 | Archetype 内连续数组 | Transform、Velocity、Health |
| **FMassSharedFragment** | 多个实体共享同一实例 | 独立哈希表，引用计数 | 共享 Mesh、共享配置、材质 |
| **FMassTag** | 不存储数据，纯标记 | 位掩码（BitSet） | 类型标记、状态标记 |

#### 1.3 Fragments vs Components 的 UE 特化

与通用 ECS 的 Component 相比，Mass Fragment 有以下 UE 特有约束：

- 必须用 `USTRUCT()` 宏标记并包含 `GENERATED_BODY()`
- 支持 `UPROPERTY()` 实现反射、序列化和网络复制
- `FMassSharedFragment` 通过 `FMassSharedFragmentInitializer` 管理引用计数和生命周期
- 所有 Fragment 实例由 `FMassEntityManager` 统一分配和释放，不存在手动 `new`/`delete`

#### 1.4 Archetype 在 Mass 中的体现

Archetype 是 Mass 的核心存储抽象——**具有相同 Fragment 组合的实体归入同一个 Archetype**。

```
Archetype A: [Transform, Velocity, PedestrianTag] → 实体 1,2,3,...
Archetype B: [Transform, Velocity, VehicleTag, WheelCount] → 实体 100,101,...
```

每个 Archetype 内部，同一 Fragment 的所有实例存储在**连续数组中**：

```
Archetype A 内存布局:
[Transform[0], Transform[1], Transform[2], ...]  ← 连续内存
[Velocity[0], Velocity[1], Velocity[2], ...]      ← 连续内存
[ChunkFragment: PedestrianTag BitSet]              ← 位掩码
```

**Fragment 增删导致 Archetype 迁移**——当实体添加或移除 Fragment 时，Mass EntityManager 会将其从当前 Archetype 移动到目标 Archetype，同时复制所有共享的 Fragment 数据。

---

## 2. 代码示例

### 2.1 FMassFragment — 纯数据 Fragment

每个实体拥有独立副本。最常用的 Fragment 类型。

```cpp
// MassEntityFragments.h
#pragma once

#include "MassEntityTypes.h"
#include "MassEntityFragments.generated.h"

// === 纯数据 Fragment ===

// 角色属性数据
USTRUCT()
struct FMassCharacterStatsFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float Health = 100.0f;

    UPROPERTY()
    float MaxHealth = 100.0f;

    UPROPERTY()
    float Speed = 200.0f;

    UPROPERTY()
    float AttackPower = 15.0f;

    // 非 UPROPERTY 字段也可用，但不参与反射/复制
    float InternalCooldown = 0.0f;
};

// AI 感知数据
USTRUCT()
struct FMassPerceptionFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float ViewRadius = 1500.0f;

    UPROPERTY()
    float ViewAngleDegrees = 120.0f;

    UPROPERTY()
    TArray<FMassEntityHandle> PerceivedEnemies;

    UPROPERTY()
    TArray<FMassEntityHandle> PerceivedAllies;
};

// 动画状态数据
USTRUCT()
struct FMassAnimationFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    int32 AnimationState = 0; // 0=Idle, 1=Walk, 2=Run, 3=Attack

    UPROPERTY()
    float StateTime = 0.0f;

    UPROPERTY()
    float BlendWeight = 0.0f;
};
```

### 2.2 FMassSharedFragment — 共享数据

同一 Archetype 内的多个实体共享**同一份数据实例**。适用于所有实体都相同的配置。

```cpp
// MassSharedFragments.h
#pragma once

#include "MassEntityTypes.h"
#include "Engine/StaticMesh.h"
#include "MassSharedFragments.generated.h"

// 共享视觉配置——所有同一类型的实体引用同一份
USTRUCT()
struct FMassVisualizationSharedFragment : public FMassSharedFragment
{
    GENERATED_BODY()

    UPROPERTY()
    TObjectPtr<UStaticMesh> Mesh = nullptr;

    UPROPERTY()
    TObjectPtr<UMaterialInterface> MaterialOverride = nullptr;

    UPROPERTY()
    float MeshScale = 1.0f;

    UPROPERTY()
    bool bCastShadow = true;
};

// 共享行为配置
USTRUCT()
struct FMassBehaviorSharedFragment : public FMassSharedFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float WanderRadius = 500.0f;

    UPROPERTY()
    float SeparationDistance = 100.0f;

    UPROPERTY()
    float AlignmentWeight = 1.0f;

    UPROPERTY()
    float CohesionWeight = 1.0f;
};

// 使用示例：为实体设置 SharedFragment
void SetupSharedFragment(FMassEntityManager& EntityManager,
                         FMassEntityHandle Entity,
                         UStaticMesh* MeshAsset)
{
    // SharedFragment 通过 Initializer 设置
    FMassSharedFragmentInitializer Initializer;
    auto& SharedFrag = Initializer.GetMutableFragmentData<
        FMassVisualizationSharedFragment>();
    SharedFrag.Mesh = MeshAsset;
    SharedFrag.MeshScale = 1.5f;

    EntityManager.AddSharedFragmentDataToEntity(Entity, Initializer);
}
```

### 2.3 FMassTag — 零开销标签

Tag 不存储数据，仅通过**位掩码**标记实体属性。查找速度极快（位运算），内存占用近零。

```cpp
// MassEntityTags.h
#pragma once

#include "MassEntityTypes.h"
#include "MassEntityTags.generated.h"

// 角色类型标签
USTRUCT()
struct FMassWarriorTag : public FMassTag
{
    GENERATED_BODY()
};

USTRUCT()
struct FMassArcherTag : public FMassTag
{
    GENERATED_BODY()
};

USTRUCT()
struct FMassHealerTag : public FMassTag
{
    GENERATED_BODY()
};

// 状态标签
USTRUCT()
struct FMassDeadTag : public FMassTag
{
    GENERATED_BODY()
};

USTRUCT()
struct FMassStunnedTag : public FMassTag
{
    GENERATED_BODY()
};

USTRUCT()
struct FMassInCombatTag : public FMassTag
{
    GENERATED_BODY()
};
```

### 2.4 查询示例：Fragment 组合过滤

```cpp
// Processor 中的查询构建
void UCombatProcessor::ConfigureQueries()
{
    // 查询 1：需要读写 Health，读取 Stats，要求必须有 WarriorTag 或 ArcherTag
    // 且不能有 DeadTag
    CombatEntityQuery.AddRequirement<FMassCharacterStatsFragment>(
        EMassFragmentAccess::ReadWrite);
    CombatEntityQuery.AddRequirement<FMassPerceptionFragment>(
        EMassFragmentAccess::ReadOnly);

    // 任一标签匹配（OR 语义）
    CombatEntityQuery.AddTagRequirement<FMassWarriorTag>(
        EMassFragmentPresence::Any);
    CombatEntityQuery.AddTagRequirement<FMassArcherTag>(
        EMassFragmentPresence::Any);

    // 排除标签（None = 实体不能有该标签）
    CombatEntityQuery.AddTagRequirement<FMassDeadTag>(
        EMassFragmentPresence::None);

    CombatEntityQuery.RegisterWithProcessor(*this);

    // 查询 2：仅角色标签匹配的实体（用于初始化）
    InitializationQuery.AddRequirement<FMassCharacterStatsFragment>(
        EMassFragmentAccess::ReadWrite);
    InitializationQuery.AddTagRequirement<FMassWarriorTag>(
        EMassFragmentPresence::All);
    InitializationQuery.AddTagRequirement<FMassHealerTag>(
        EMassFragmentPresence::None);
    InitializationQuery.RegisterWithProcessor(*this);
}
```

### 2.5 完整示例：Archetype 创建与 Fragment 生命周期

```cpp
// FragmentLifecycleDemo.cpp
#include "MassEntityManager.h"
#include "MassEntitySubsystem.h"
#include "MassEntityFragments.h"
#include "MassEntityTags.h"

void DemonstrateFragmentLifecycle(UWorld* World)
{
    UMassEntitySubsystem* Subsystem =
        World->GetSubsystem<UMassEntitySubsystem>();
    FMassEntityManager& EM = Subsystem->GetMutableEntityManager();

    // 1. 创建 Archetype A：战士（Health + Perception + WarriorTag）
    FMassArchetypeHandle ArchetypeWarrior = EM.CreateArchetype({
        FMassCharacterStatsFragment::StaticStruct(),
        FMassPerceptionFragment::StaticStruct(),
        FMassWarriorTag::StaticStruct()
    });

    // 2. 创建 Archetype B：弓箭手（Health + Perception + ArcherTag）
    FMassArchetypeHandle ArchetypeArcher = EM.CreateArchetype({
        FMassCharacterStatsFragment::StaticStruct(),
        FMassPerceptionFragment::StaticStruct(),
        FMassArcherTag::StaticStruct()
    });

    // 3. 批量生成实体
    TArray<FMassEntityHandle> Warriors, Archers;
    EM.BatchCreateEntities(ArchetypeWarrior, 50, Warriors);
    EM.BatchCreateEntities(ArchetypeArcher, 30, Archers);

    // 4. 写入初始数据
    for (const FMassEntityHandle& H : Warriors)
    {
        EM.GetFragmentDataChecked<FMassCharacterStatsFragment>(H).Health = 150.0f;
        EM.GetFragmentDataChecked<FMassCharacterStatsFragment>(H).AttackPower = 25.0f;
    }
    for (const FMassEntityHandle& H : Archers)
    {
        EM.GetFragmentDataChecked<FMassCharacterStatsFragment>(H).Health = 80.0f;
        EM.GetFragmentDataChecked<FMassCharacterStatsFragment>(H).AttackPower = 35.0f;
        EM.GetFragmentDataChecked<FMassPerceptionFragment>(H).ViewRadius = 2500.0f;
    }

    // 5. 运行时 Fragment 增删——触发 Archetype 迁移
    // 给第一个战士添加 StunnedTag（迁移到新 Archetype）
    FMassArchetypeHandle TargetArchetype =
        EM.GetArchetypeForEntity(Warriors[0]).GetArchetypeHandle();
    // 注意：实际 API 通过 FMassCommandBuffer 的 Defer 添加 Fragment
    // EntityManager.AddFragmentDataToEntity(Warriors[0], FMassStunnedTag());

    // 6. 验证 Archetype 迁移
    const int32 NumWarriorArchetypeEntities =
        EM.GetNumEntities(ArchetypeWarrior);
    UE_LOG(LogTemp, Log,
        TEXT("Warrior Archetype entities: %d, Archer: %d"),
        NumWarriorArchetypeEntities,
        EM.GetNumEntities(ArchetypeArcher));
}
```

### 2.6 Fragment 内存布局深入

```cpp
// 演示 Mass 内部 Chunk 布局（概念代码）
struct FMassArchetypeChunk
{
    static constexpr int32 ChunkSize = 64; // 每个 Chunk 最多 64 个实体

    // 每个 Fragment 类型对应一段连续内存
    // Fragment A: [Entity0, Entity1, ..., Entity63]  // sizeof(FragmentA) * 64 字节
    // Fragment B: [Entity0, Entity1, ..., Entity63]  // sizeof(FragmentB) * 64 字节
    // Tag BitSet:  uint64 bitmask                     // 8 字节

    TArray<uint8> FragmentData; // 所有 Fragment 数据的扁平化存储
    uint64 TagBits;             // Tag 位掩码
};
```

**性能要点：**

- `ForEachEntityChunk` 遍历时，每个 Chunk 内的同类型 Fragment 在内存中是连续的，CPU 预取器能高效工作。
- `FMassTag` 的查询是 `(TagBits & RequiredMask) == RequiredMask` 的单次位运算。
- `FMassSharedFragment` 存储在单独哈希表中，查询时通过 Entity→SharedFragmentIndex 间接访问（多一次指针跳转，注意缓存未命中）。

---

## 3. 练习

### 练习 1: 基础练习 —— 定义完整的实体类型

定义一个 `FMassRangedEnemyFragment`（包含 `float AttackRange`、`float ProjectileSpeed`、`int32 AmmoCount`）和 `FMassMeleeEnemyFragment`（包含 `float MeleeRange`、`float ComboMultiplier`）。创建两个 Archetype 各生成 30 个实体。写一个调试 Processor 输出每种实体数量。

### 练习 2: 进阶练习 —— SharedFragment 共享配置

创建 `FMassTeamSharedFragment`（包含 `int32 TeamId`、`FLinearColor TeamColor`、`TArray<FMassEntityHandle> TeamMembers`）。将所有同队实体批量添加此 SharedFragment。编写 `UTeamBalanceProcessor`：遍历所有实体，对于 `FMassDeadTag` 标记的实体，将其所在队伍的 `FMassTeamSharedFragment` 的 `TeamMembers` 中移除该实体句柄。

提示：SharedFragment 通过 `FMassArchetypeSharedFragmentValues` 批量设置；多个实体共享的 SharedFragment 不会存储多份数据。

### 练习 3: 挑战练习 —— 自定义 Archetype 迁移系统

实现一个 `UFragmentMigrationProcessor`，每 5 秒检查一次所有实体的 `FMassCharacterStatsFragment::Health`。当 `Health == 0` 时：
1. 移除 `FMassPerceptionFragment` 和 `FMassCharacterStatsFragment`
2. 添加 `FMassDeadTag`
3. 记录迁移日志
验证迁移后实体数量变化：原 Archetype 减少、新 Archetype（仅有 DeadTag）增加。

---

## 4. 扩展阅读

- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassArchetypeTypes.h` — Archetype 创建和管理的完整 API
- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassEntityManager.h` — EntityManager 的 Fragment 增删改查接口
- **碎片化问题**: 搜索 "Mass Entity Archetype Defragmentation" 了解频繁 Fragment 增删导致的 Archetype 碎片化及 Mass 如何处理
- **City Sample**: `Plugins/CitySample/Source/CitySampleMassCrowd/` — 查看 Crowd 实体的 Fragment 定义

---

## 常见陷阱

1. **Tag 不能存数据** — `FMassTag` 的 `StaticStruct()` 返回的 `UScriptStruct` 大小为 0。不要在 Tag 中定义 `UPROPERTY()` 字段，它们不会被序列化。

2. **SharedFragment 引用计数** — 当所有引用某 `FMassSharedFragment` 实例的实体被销毁后，该实例自动释放。不要缓存指向 SharedFragment 的裸指针。

3. **Fragment 增删开销** — 每次 `AddFragment`/`RemoveFragment` 都触发 Archetype 迁移和内存复制（复制实体的所有其他 Fragment）。高频增删会显著影响性能，应合并到批量操作。

4. **Archetype 碎片化** — 频繁创建和销毁 Archetype 会导致 EntityManager 内部存储碎片化。复用 Archetype 句柄，并在设计阶段明确实体的 Fragment 组合。

5. **Fragment 大小影响遍历性能** — 单个 Fragment 的 `sizeof` 应尽可能小（< 256 字节），过大的 Fragment 会降低 CPU 缓存的利用率。
