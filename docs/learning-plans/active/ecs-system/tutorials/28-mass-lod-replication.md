---
title: "Mass LOD 与网络复制"
updated: 2026-06-05
---

# Mass LOD 与网络复制

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 3h
> 前置知识: Mass Processors、Mass Traits、UE 网络复制基础

---

## 1. 概念讲解

### 为什么需要这个？

万人同屏场景面临两个核心挑战：(1) 如何根据距离动态调整实体精度以节省 CPU/GPU；(2) 如何在多人游戏中同步成千上万个实体状态。Mass 的 LOD 系统和复制系统协同工作——LOD 决定计算粒度，复制决定网络带宽。

### 核心思想

#### 1.1 Mass LOD 系统——距离驱动的细节层次

Mass LOD 将实体分为三个（或更多）层级：

| LOD 级别 | 距离范围 | Fragment 特征 | 典型行为 |
|---------|---------|-------------|---------|
| **High (近)** | 0 ~ 50m | 完整 Fragment 集合 | 动画、碰撞、AI 决策、高精度渲染 |
| **Medium (中)** | 50m ~ 150m | 简化 Fragment | 简单位移动画、无碰撞、低模渲染 |
| **Low (远)** | 150m+ | 最小 Fragment + Tag | 仅位置更新、点渲染或剔除 |
| **Off** | 超出视野 | 无 Fragment（可休眠） | 不处理、不渲染 |

**核心 Processor:** `ULODSignificanceProcessor` 根据实体与所有 "Significance View"（通常是玩家摄像机）的距离，计算每个实体的 LOD 级别，然后通过 Fragment 增删触发实体在不同 Archetype 间迁移。

#### 1.2 LOD Collector——LOD 级别管理

```cpp
// Mass 内置概念（简化）
FMassEntityLODSignificanceRange
  High:   0.0f  - 5000.0f
  Medium: 5000.0f - 15000.0f
  Low:    15000.0f - 30000.0f
  Off:    30000.0f+
```

每个 LOD Collector 定义一组距离阈值。实体可以通过 `FMassEntityLODSignificanceFragment` 存储其当前 significance 值，系统根据 Collector 的阈值自动决定 LOD 级别。

#### 1.3 网络复制架构

Mass 的网络复制不同于 Actor 复制——它不是逐实体复制，而是通过 `MassClientBubbleInfo` 批量同步。

```
[Server]                            [Client]
Mass Entities                      Mass Entities (replicas)
    ↓                                   ↑
UMassReplicatorBase                     |
    ↓                                   |
FMassBubbleInfoClass                   |
    ↓                                   |
    ├── Serialize Entities ──────────→  |
    │   (chunked, compressed)           |
    │                                   |
    └── ← Receive Client Commands ─────┘
        (e.g., request entity detail)
```

**关键类：**

| 类 | 角色 |
|---|------|
| `UMassReplicatorBase` | 服务端：管理复制状态、序列化实体 |
| `FMassClientBubbleInfoBase` | 客户端：接收并应用复制数据 |
| `FMassNetworkIDFragment` | 每个实体的唯一网络 ID（跨服务端/客户端） |
| `FMassReplicationProcessor` | 服务端：收集需要复制的实体 |
| `FMassClientBubbleProcessor` | 客户端：应用接收到的复制数据 |

#### 1.4 复制粒度控制

- **LOD 感知复制** — 远距离实体低频复制（如每秒 1 次），近距离高频（如每秒 10 次）。
- **带宽管理** — `UMassReplicationSubsystem` 每帧分配复制带宽，优先复制 LOD 级别高的实体。
- **相关性过滤** — 服务端仅复制与客户端相关的实体（基于观察者位置的 LOD 过滤）。

---

## 2. 代码示例

### 2.1 LOD 级别定义与 Fragment

```cpp
// MassCrowdLODFragments.h
#pragma once

#include "MassEntityTypes.h"
#include "MassLODTypes.h"
#include "MassCrowdLODFragments.generated.h"

// LOD Collector Tag——标记实体参与哪个 LOD 系统
USTRUCT()
struct FMassCrowdLODCollectorTag : public FMassTag
{
    GENERATED_BODY()
};

// LOD Significance——存储计算出的重要性数值
USTRUCT()
struct FMassCrowdSignificanceFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float Significance = 0.0f; // 越小越重要（近距离=低值）

    UPROPERTY()
    EMassLOD PrevLOD = EMassLOD::Max;
};

// High LOD——近距离专用 Fragment
USTRUCT()
struct FMassCrowdHighLODFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    int32 AnimationStateIndex = 0;

    UPROPERTY()
    float AnimationBlendWeight = 0.0f;

    UPROPERTY()
    bool bIsColliding = true;

    UPROPERTY()
    FVector DetailedFootPosition = FVector::ZeroVector;
};

USTRUCT()
struct FMassCrowdHighLODTag : public FMassTag
{
    GENERATED_BODY()
};

// Medium LOD——中距离简化版
USTRUCT()
struct FMassCrowdMediumLODFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    int32 SimpleAnimationState = 0; // 仅 Idle/Walk/Run

    UPROPERTY()
    bool bUseImposter = false;
};

USTRUCT()
struct FMassCrowdMediumLODTag : public FMassTag
{
    GENERATED_BODY()
};

// Low LOD——远距离极简版
USTRUCT()
struct FMassCrowdLowLODTag : public FMassTag
{
    GENERATED_BODY()
};
```

### 2.2 LOD Significance Processor

```cpp
// CrowdLODSignificanceProcessor.h
#pragma once

#include "MassLODSignificanceProcessor.h"
#include "MassCrowdLODFragments.h"
#include "CrowdLODSignificanceProcessor.generated.h"

UCLASS()
class UCrowdLODSignificanceProcessor : public UMassLODSignificanceProcessor
{
    GENERATED_BODY()

public:
    UCrowdLODSignificanceProcessor();

    // 配置每个 LOD 级别所需的 Fragment 和 Tag
    UPROPERTY(EditAnywhere, Category = "LOD")
    TArray<FMassLODSignificanceRange> SignificanceRanges;

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;
};
```

```cpp
// CrowdLODSignificanceProcessor.cpp
#include "CrowdLODSignificanceProcessor.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassLODSubsystem.h"
#include "MassCommandBuffer.h"

UCrowdLODSignificanceProcessor::UCrowdLODSignificanceProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::LOD;
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);

    // 默认 LOD 距离阈值
    SignificanceRanges = {
        { 0.0f,    5000.0f },  // High LOD:   0-50m
        { 5000.0f, 15000.0f }, // Medium LOD: 50-150m
        { 15000.0f,30000.0f }  // Low LOD:    150-300m
        // >30000 = Off（不处理）
    };
}

void UCrowdLODSignificanceProcessor::ConfigureQueries()
{
    // 查询需要 LOD Collector Tag 和 Significance Fragment
    EntityQuery.AddTagRequirement<FMassCrowdLODCollectorTag>(
        EMassFragmentPresence::All);
    EntityQuery.AddRequirement<FMassCrowdSignificanceFragment>(
        EMassFragmentAccess::ReadWrite);
    EntityQuery.AddRequirement<FTransformFragment>(
        EMassFragmentAccess::ReadOnly);
    EntityQuery.RegisterWithProcessor(*this);
}

void UCrowdLODSignificanceProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    // 获取所有视图（玩家摄像机位置）
    TArray<FTransform> ViewTransforms;
    if (const UMassLODSubsystem* LODSubsystem =
        Context.GetSubsystem<UMassLODSubsystem>())
    {
        LODSubsystem->GetViewerTransforms(ViewTransforms);
    }

    EntityQuery.ForEachEntityChunk(EntityManager, Context,
        [this, &ViewTransforms](FMassExecutionContext& Context)
        {
            TArrayView<FMassCrowdSignificanceFragment> Significances =
                Context.GetMutableFragmentView<FMassCrowdSignificanceFragment>();
            const TArrayView<FTransformFragment> Transforms =
                Context.GetFragmentView<FTransformFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                const FVector EntityPos =
                    Transforms[i].GetTransform().GetLocation();

                // 计算离最近视点的距离
                float MinDistanceSq = FLT_MAX;
                for (const FTransform& View : ViewTransforms)
                {
                    const float DistSq = FVector::DistSquared(
                        EntityPos, View.GetLocation());
                    MinDistanceSq = FMath::Min(MinDistanceSq, DistSq);
                }

                float Distance = FMath::Sqrt(MinDistanceSq);

                // 根据距离映射 LOD 级别
                EMassLOD NewLOD = EMassLOD::Max; // 默认=Off
                for (int32 Level = 0; Level < SignificanceRanges.Num(); ++Level)
                {
                    if (Distance >= SignificanceRanges[Level].MinDistance &&
                        Distance < SignificanceRanges[Level].MaxDistance)
                    {
                        NewLOD = static_cast<EMassLOD>(Level);
                        break;
                    }
                }

                // 存储 Significance = 距离（越小越重要）
                Significances[i].Significance = Distance;

                // LOD 级别变化时，添加/移除相应的 Fragment
                if (NewLOD != Significances[i].PrevLOD)
                {
                    const FMassEntityHandle Entity = Context.GetEntity(i);

                    switch (Significances[i].PrevLOD)
                    {
                    case EMassLOD::High:
                        Context.Defer().RemoveFragment<
                            FMassCrowdHighLODFragment>(Entity);
                        Context.Defer().RemoveTag<
                            FMassCrowdHighLODTag>(Entity);
                        break;
                    case EMassLOD::Medium:
                        Context.Defer().RemoveFragment<
                            FMassCrowdMediumLODFragment>(Entity);
                        Context.Defer().RemoveTag<
                            FMassCrowdMediumLODTag>(Entity);
                        break;
                    case EMassLOD::Low:
                        Context.Defer().RemoveTag<
                            FMassCrowdLowLODTag>(Entity);
                        break;
                    default: break;
                    }

                    switch (NewLOD)
                    {
                    case EMassLOD::High:
                        Context.Defer().AddFragment<
                            FMassCrowdHighLODFragment>(Entity);
                        Context.Defer().AddTag<
                            FMassCrowdHighLODTag>(Entity);
                        break;
                    case EMassLOD::Medium:
                        Context.Defer().AddFragment<
                            FMassCrowdMediumLODFragment>(Entity);
                        Context.Defer().AddTag<
                            FMassCrowdMediumLODTag>(Entity);
                        break;
                    case EMassLOD::Low:
                        Context.Defer().AddTag<
                            FMassCrowdLowLODTag>(Entity);
                        break;
                    default: break;
                    }

                    Significances[i].PrevLOD = NewLOD;
                }
            }
        });
}
```

### 2.3 网络复制——Bubble Info

```cpp
// MassCrowdReplication.h
#pragma once

#include "MassReplicationTypes.h"
#include "MassClientBubbleHandler.h"
#include "MassCrowdReplication.generated.h"

// 复制数据 Fragment——标记哪些 Fragment 需要复制
USTRUCT()
struct FMassCrowdReplicationFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    FVector ReplicatedLocation = FVector::ZeroVector;

    UPROPERTY()
    FRotator ReplicatedRotation = FRotator::ZeroRotator;

    UPROPERTY()
    float ReplicatedSpeed = 0.0f;

    UPROPERTY()
    int32 ReplicatedAnimationState = 0;
};

// Bubble Info——定义客户端如何接收数据
USTRUCT()
struct FMassCrowdClientBubbleItem
{
    GENERATED_BODY()

    UPROPERTY()
    FVector Location = FVector::ZeroVector;

    UPROPERTY()
    FRotator Rotation = FRotator::ZeroRotator;

    UPROPERTY()
    float Speed = 0.0f;

    UPROPERTY()
    int32 AnimationState = 0;
};

// Bubble Info 封装器
USTRUCT()
struct FMassCrowdBubbleInfo : public FMassClientBubbleInfoBase
{
    GENERATED_BODY()

    UPROPERTY()
    TArray<FMassCrowdClientBubbleItem> Items;

    virtual void Serialize(FArchive& Ar) override
    {
        Super::Serialize(Ar);
        Ar << Items;
    }
};
```

```cpp
// MassCrowdReplicationProcessor.h
#pragma once

#include "MassReplicationProcessor.h"
#include "MassCrowdReplication.generated.h"

UCLASS()
class UCrowdReplicationProcessor : public UMassReplicationProcessor
{
    GENERATED_BODY()

public:
    UCrowdReplicationProcessor();

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;
};
```

```cpp
// MassCrowdReplicationProcessor.cpp
#include "MassCrowdReplicationProcessor.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassReplicationSubsystem.h"
#include "MassCrowdLODFragments.h"
#include "MassNetworkIDFragment.h"

UCrowdReplicationProcessor::UCrowdReplicationProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::Replication;
    ExecutionFlags = (int32)(EProcessorExecutionFlags::ServerOnly);
}

void UCrowdReplicationProcessor::ConfigureQueries()
{
    // 需要网络 ID（由复制系统分配）
    EntityQuery.AddRequirement<FMassNetworkIDFragment>(
        EMassFragmentAccess::ReadOnly);
    // 需要基础位置数据
    EntityQuery.AddRequirement<FTransformFragment>(
        EMassFragmentAccess::ReadOnly);
    // 需要复制目标数据
    EntityQuery.AddRequirement<FMassCrowdReplicationFragment>(
        EMassFragmentAccess::ReadWrite);
    // 需要 LOD 信息（用于控制复制频率）
    EntityQuery.AddRequirement<FMassCrowdSignificanceFragment>(
        EMassFragmentAccess::ReadOnly);

    EntityQuery.RegisterWithProcessor(*this);
}

void UCrowdReplicationProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    UMassReplicationSubsystem* ReplicationSubsystem =
        Context.GetSubsystem<UMassReplicationSubsystem>();
    if (!ReplicationSubsystem) return;

    // 每帧可用的复制带宽（可配置）
    const int32 MaxEntitiesPerFrame = 200;
    int32 NumProcessed = 0;

    EntityQuery.ForEachEntityChunk(EntityManager, Context,
        [&ReplicationSubsystem, &NumProcessed, MaxEntitiesPerFrame]
        (FMassExecutionContext& Context)
        {
            const TArrayView<FMassNetworkIDFragment> NetworkIDs =
                Context.GetFragmentView<FMassNetworkIDFragment>();
            const TArrayView<FTransformFragment> Transforms =
                Context.GetFragmentView<FTransformFragment>();
            TArrayView<FMassCrowdReplicationFragment> ReplicationData =
                Context.GetMutableFragmentView<FMassCrowdReplicationFragment>();
            const TArrayView<FMassCrowdSignificanceFragment> Significances =
                Context.GetFragmentView<FMassCrowdSignificanceFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                if (NumProcessed >= MaxEntitiesPerFrame)
                    return; // 带宽限制

                const FTransform& Transform = Transforms[i].GetTransform();
                const FVector& CurrentPos = Transform.GetLocation();
                const FRotator& CurrentRot = Transform.Rotator();

                FMassCrowdReplicationFragment& Replicated =
                    ReplicationData[i];

                // LOD 感知复制频率：
                // High LOD (近): 每帧复制（如果数据变化大）
                // Low LOD (远): 距离变化超过阈值才复制
                const float Dist = Significances[i].Significance;
                const float ReplicationThreshold =
                    (Dist < 5000.0f) ? 10.0f : 100.0f; // cm

                const bool bShouldReplicate =
                    FVector::Dist(Replicated.ReplicatedLocation, CurrentPos)
                    > ReplicationThreshold;

                if (bShouldReplicate)
                {
                    Replicated.ReplicatedLocation = CurrentPos;
                    Replicated.ReplicatedRotation = CurrentRot;

                    // 构建 Bubble Item 并发送
                    FMassCrowdClientBubbleItem Item;
                    Item.Location = CurrentPos;
                    Item.Rotation = CurrentRot;
                    // 假设有速度 Fragment
                    Item.Speed = 0.0f; // 从 Velocity Fragment 获取
                    Item.AnimationState = 0;

                    // 添加到 Bubble 并标记为待发送
                    ReplicationSubsystem->AddBubbleItem(
                        NetworkIDs[i].GetNetworkID(), Item);

                    ++NumProcessed;
                }
            }
        });
}
```

### 2.4 客户端 Bubble Processor

```cpp
// MassCrowdClientBubbleProcessor.h
#pragma once

#include "MassClientBubbleProcessor.h"
#include "MassCrowdReplication.generated.h"

UCLASS()
class UCrowdClientBubbleProcessor : public UMassClientBubbleProcessor
{
    GENERATED_BODY()

public:
    UCrowdClientBubbleProcessor();

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;
};
```

```cpp
// MassCrowdClientBubbleProcessor.cpp
#include "MassCrowdClientBubbleProcessor.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassClientBubbleHandler.h"
#include "MassNetworkIDFragment.h"
#include "MassCrowdLODFragments.h"

UCrowdClientBubbleProcessor::UCrowdClientBubbleProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::Replication;
    ExecutionFlags = (int32)(EProcessorExecutionFlags::ClientOnly);
}

void UCrowdClientBubbleProcessor::ConfigureQueries()
{
    EntityQuery.AddRequirement<FMassNetworkIDFragment>(
        EMassFragmentAccess::ReadOnly);
    EntityQuery.AddRequirement<FTransformFragment>(
        EMassFragmentAccess::ReadWrite);
    EntityQuery.AddRequirement<FMassCrowdReplicationFragment>(
        EMassFragmentAccess::ReadWrite);
    EntityQuery.RegisterWithProcessor(*this);
}

void UCrowdClientBubbleProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    // 获取客户端接收到的 Bubble 数据
    const FMassCrowdBubbleInfo* BubbleInfo =
        GetClientBubbleInfo<FMassCrowdBubbleInfo>();
    if (!BubbleInfo) return;

    EntityQuery.ForEachEntityChunk(EntityManager, Context,
        [BubbleInfo](FMassExecutionContext& Context)
        {
            const TArrayView<FMassNetworkIDFragment> NetworkIDs =
                Context.GetFragmentView<FMassNetworkIDFragment>();
            TArrayView<FTransformFragment> Transforms =
                Context.GetMutableFragmentView<FTransformFragment>();
            TArrayView<FMassCrowdReplicationFragment> ReplicationData =
                Context.GetMutableFragmentView<FMassCrowdReplicationFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                const int32 NetID = NetworkIDs[i].GetNetworkID();
                if (NetID < 0 || NetID >= BubbleInfo->Items.Num())
                    continue;

                const FMassCrowdClientBubbleItem& Item =
                    BubbleInfo->Items[NetID];

                // 应用复制数据（带插值平滑）
                FTransform& Transform = Transforms[i].GetMutableTransform();
                const FVector OldLocation = Transform.GetLocation();

                // 线性插值平滑（Alpha 基于 deltaTime 和目标距离）
                const float InterpSpeed = 10.0f;
                const FVector InterpolatedLocation = FMath::VInterpTo(
                    OldLocation, Item.Location,
                    Context.GetDeltaTimeSeconds(), InterpSpeed);

                Transform.SetLocation(InterpolatedLocation);
                Transform.SetRotation(Item.Rotation.Quaternion());

                // 更新复制数据 Fragment
                ReplicationData[i].ReplicatedLocation = Item.Location;
                ReplicationData[i].ReplicatedSpeed = Item.Speed;
                ReplicationData[i].ReplicatedAnimationState = Item.AnimationState;
            }
        });
}
```

### 2.5 完整集成——在 Spawner 中启用 LOD 和复制

```cpp
// CrowdSpawnerWithLODReplication.cpp
void SetupCrowdWithLODAndReplication(
    UWorld* World,
    int32 EntityCount,
    const FVector& Origin)
{
    UMassEntitySubsystem* Subsystem =
        World->GetSubsystem<UMassEntitySubsystem>();
    FMassEntityManager& EM = Subsystem->GetMutableEntityManager();

    // 1. 创建 Archetype——包含 LOD 和复制所需的 Fragment
    FMassArchetypeHandle Archetype = EM.CreateArchetype({
        // 基础
        FTransformFragment::StaticStruct(),
        FVector2D(0, 0), // placeholder for Velocity
        // LOD
        FMassCrowdLODCollectorTag::StaticStruct(),
        FMassCrowdSignificanceFragment::StaticStruct(),
        FMassCrowdHighLODFragment::StaticStruct(),
        FMassCrowdHighLODTag::StaticStruct(),
        FMassCrowdMediumLODFragment::StaticStruct(),
        FMassCrowdMediumLODTag::StaticStruct(),
        FMassCrowdLowLODTag::StaticStruct(),
        // 网络复制
        FMassNetworkIDFragment::StaticStruct(),
        FMassCrowdReplicationFragment::StaticStruct()
    });

    // 2. 批量生成
    TArray<FMassEntityHandle> Entities;
    EM.BatchCreateEntities(Archetype, EntityCount, Entities);

    // 3. 初始化
    for (int32 i = 0; i < EntityCount; ++i)
    {
        FTransformFragment& Transform =
            EM.GetFragmentDataChecked<FTransformFragment>(Entities[i]);
        Transform.SetTranslation(Origin + FVector(
            FMath::RandRange(-5000.0f, 5000.0f),
            FMath::RandRange(-5000.0f, 5000.0f),
            0.0f));

        // LOD 初始状态: 假设所有实体从远距离开始
        FMassCrowdSignificanceFragment& Sig =
            EM.GetFragmentDataChecked<FMassCrowdSignificanceFragment>(
                Entities[i]);
        Sig.Significance = 50000.0f; // 初始远超 High LOD 范围
        Sig.PrevLOD = EMassLOD::Max;  // 初始无 LOD
    }

    UE_LOG(LogTemp, Log,
        TEXT("Spawned %d entities with LOD + Replication support"),
        EntityCount);
}
```

---

## 3. 练习

### 练习 1: 基础练习 —— 实现三层 LOD Fragment 切换

创建 `UPedestrianLODProcessor`，基于到玩家的距离动态切换实体的 Fragment 集合。要求：
- ≤50m：添加 `FMassDetailedAnimationFragment`（包含动画骨骼混合树索引）
- 50-150m：添加 `FMassSimpleAnimationFragment`（仅包含移动动画状态）
- ≥150m：仅保留 `FTransformFragment`

在 Execute 中通过 `Context.Defer()` 添加/移除 Fragment。使用 `VisualLogger` 记录 LOD 切换事件。

### 练习 2: 进阶练习 —— LOD 感知的 Processor 性能分析

创建三个 Processor，分别只处理 High/Medium/Low LOD 的实体（通过 Tag 过滤）。使用 UE 的 `UE::Stats` 或 `SCOPE_CYCLE_COUNTER` 测量每个 Processor 的耗时。调整实体数量和 LOD 距离阈值，观察性能变化。目标：证明 10000 个实体中只有近处 200 个运行完整 AI 逻辑时，帧率仍能保持在 60 FPS。

### 练习 3: 挑战练习 —— 客户端预测 + 服务端权威

实现客户端预测模型：
1. 服务端运行完整的移动和避障 Processor
2. 客户端接收服务端的复制位置并应用
3. 客户端在收到新数据之前使用本地 `UPredictionProcessor` 继续驱动实体（使用最后一次复制的速度）
4. 当服务端数据到达时，客户端平滑校正（使用 `FMath::VInterpTo`）
5. 测试延迟 100ms 下的表现——实体是否平滑移动而无跳变

---

## 4. 扩展阅读

- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassLOD/Public/MassLODSignificanceProcessor.h` — 内置 LOD 处理器实现
- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassReplication/Public/MassReplicationProcessor.h` — 复制处理器基类
- **MassGameplay**: `Plugins/Runtime/MassGameplay/Source/MassLOD/` — LOD Collector 的具体实现
- **City Sample**: 查看项目的 Mass LOD 配置和复制设置
- **Network Profiling**: 使用 `stat net` 命令查看复制带宽使用情况，验证 LOD 感知复制有效降低带宽

---

## 常见陷阱

1. **LOD 切换开销** — Fragment 增删触发 Archetype 迁移（内存复制所有其他 Fragment 数据）。如果大量实体在同一帧切换 LOD（如玩家快速移动），可能导致卡顿。Mass 通过分批迁移缓解此问题，但设计时应避免 LOD 阈值过于密集。

2. **复制带宽超限** — 如果 MaxEntitiesPerFrame 过小，远距离实体更新延迟增大（几百毫秒才更新一次）。合理设置复制优先级——近距离实体优先。

3. **客户端 LOD 与服务端不一致** — 客户端和服务端可能对同一实体计算不同的 LOD 级别（视点位置不同）。确保 `FMassCrowdSignificanceFragment` 不在客户端修改——它应由服务端权威计算。

4. **NetworkID 泄漏** — `FMassNetworkIDFragment` 由 `UMassReplicationSubsystem` 管理。销毁实体时必须通知子系统释放 ID，否则 ID 池泄漏。

5. **LOD 与复制 Phase 的顺序** — LOD Processor 必须在 Replication Processor 之前执行，否则 Replication Processor 读取的是过时的 LOD 数据，导致错误的复制优先级决策。
