---
title: "完整 UE Mass 项目：万人同屏 AI 人群模拟"
updated: 2026-06-05
---

# 完整 UE Mass 项目：万人同屏 AI 人群模拟

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 8h
> 前置知识: 全部前五篇 Mass 教程（总览→Entity/Fragment→Processors→Traits→LOD/Replication）

---

## 1. 概念讲解

### 为什么需要这个？

前五篇教程覆盖了 Mass 框架的各个独立模块。本教程将所有模块整合为一个完整的可运行项目——万人同屏 AI 人群模拟。你将看到 Fragment 定义、Trait 配置、Processor 协作、ZoneGraph 导航、LOD 管理、性能分析如何在一个项目中协同工作。

### 核心思想

#### 1.1 项目架构

```
┌─────────────────────────────────────────────────────────┐
│                    Mass Crowd Project                    │
├─────────────────────────────────────────────────────────┤
│  构建时（编辑器中）                                       │
│  ┌──────────────────┐  ┌──────────────────────────────┐ │
│  │ MassEntityConfig  │  │ ZoneGraph Data (导航数据)     │ │
│  │ Asset x3          │  │ - Sidewalk lanes (步道)      │ │
│  │ - Pedestrian      │  │ - Crosswalk lanes (斑马线)   │ │
│  │ - Vehicle         │  │ - Road lanes (车道)          │ │
│  │ - Cyclist         │  └──────────────────────────────┘ │
│  └──────────────────┘                                     │
├─────────────────────────────────────────────────────────┤
│  运行时（C++ Processors）                                 │
│  ┌────────────────────────────────────────────────────┐ │
│  │ LOD Phase                                          │ │
│  │  └─ ULODSignificanceProcessor                      │ │
│  │     └─ UCrowdLODFragmentSwitcher                    │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Navigation Phase                                   │ │
│  │  └─ UZoneGraphPathFollowProcessor                  │ │
│  │     └─ UObstacleAvoidanceProcessor                  │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Behavior Phase (可并行)                             │ │
│  │  ├─ UCrowdSeparationProcessor (分离)                │ │
│  │  ├─ UCrowdAlignmentProcessor (对齐)                 │ │
│  │  └─ UCrowdCohesionProcessor  (聚拢)                 │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Movement Phase                                      │ │
│  │  └─ UCrowdMovementProcessor                        │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Animation Phase                                     │ │
│  │  └─ UCrowdAnimationProcessor                       │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Rendering Phase                                     │ │
│  │  └─ UCrowdRenderingProcessor (ISM 合批)             │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Replication Phase (服务端)                           │ │
│  │  └─ UCrowdReplicationProcessor                      │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### 1.2 性能目标

| 实体数量 | 目标 FPS | 关键策略 |
|---------|---------|---------|
| 1,000   | 120+    | 全部 High LOD |
| 5,000   | 90+     | 50% Medium, 30% Low |
| 10,000  | 60+     | 20% High, 40% Medium, 40% Low |
| 20,000  | 30+     | LOD + ISM 合批 + 休眠远距离 |

---

## 2. 完整项目代码

### 2.1 项目设置

**启用插件** （`.uproject` 文件）：

```json
{
    "Plugins": [
        { "Name": "MassEntity", "Enabled": true },
        { "Name": "MassGameplay", "Enabled": true },
        { "Name": "MassAI", "Enabled": true },
        { "Name": "MassCrowd", "Enabled": true },
        { "Name": "MassMovement", "Enabled": true },
        { "Name": "MassNavigation", "Enabled": true },
        { "Name": "MassLOD", "Enabled": true },
        { "Name": "MassReplication", "Enabled": true },
        { "Name": "MassRepresentation", "Enabled": true },
        { "Name": "ZoneGraph", "Enabled": true },
        { "Name": "ZoneGraphAnnotations", "Enabled": true }
    ]
}
```

**Build.cs 模块依赖**：

```csharp
// MassCrowdProject.Build.cs
PublicDependencyModuleNames.AddRange(new string[] {
    "Core", "CoreUObject", "Engine",
    "MassEntity",
    "MassCommon",
    "MassMovement",
    "MassNavigation",
    "MassAI",
    "MassCrowd",
    "MassLOD",
    "MassReplication",
    "MassRepresentation",
    "MassSpawner",
    "MassSignals",
    "ZoneGraph",
    "ZoneGraphAnnotations",
    "StructUtils",
    "GameplayTags"
});
```

### 2.2 实体设计——行人 Fragment 集合

```cpp
// CrowdProjectFragments.h
#pragma once

#include "MassEntityTypes.h"
#include "ZoneGraphTypes.h"
#include "MassMovementFragments.h"
#include "MassNavigationFragments.h"
#include "MassRepresentationFragments.h"
#include "MassLODFragments.h"
#include "CrowdProjectFragments.generated.h"

// ===== 核心数据 Fragment =====

// 人群移动参数
USTRUCT()
struct FCrowdMovementFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float DesiredSpeed = 150.0f;    // 期望移动速度 cm/s

    UPROPERTY()
    float CurrentSpeed = 0.0f;      // 当前实际速度

    UPROPERTY()
    float MaxSpeed = 200.0f;        // 最大速度

    UPROPERTY()
    float Acceleration = 400.0f;    // 加速度 cm/s²

    UPROPERTY()
    float RotationSpeed = 360.0f;   // 旋转速度 度/s
};

// 人群行为参数（Steering）
USTRUCT()
struct FCrowdBehaviorFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    FVector SteeringForce = FVector::ZeroVector;

    UPROPERTY()
    float SeparationWeight = 1.5f;  // 分离权重

    UPROPERTY()
    float AlignmentWeight = 1.0f;   // 对齐权重

    UPROPERTY()
    float CohesionWeight = 0.8f;    // 聚拢权重

    UPROPERTY()
    float AvoidanceRadius = 150.0f; // 个人空间半径

    UPROPERTY()
    float NeighborQueryRadius = 500.0f;
};

// 动画状态
USTRUCT()
struct FCrowdAnimationFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    int32 CurrentAnimState = 0;     // 0=Idle, 1=Walk, 2=Run

    UPROPERTY()
    float StateBlendWeight = 1.0f;

    UPROPERTY()
    float PlayRate = 1.0f;

    UPROPERTY()
    float CycleOffset = 0.0f;       // 动画循环偏移（避免同步）
};

// LOD 数据
USTRUCT()
struct FCrowdLODFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float DistanceToViewer = 0.0f;

    UPROPERTY()
    int32 CurrentLODLevel = 0;      // 0=High, 1=Medium, 2=Low, 3=Off

    UPROPERTY()
    int32 PreviousLODLevel = 3;

    UPROPERTY()
    float TimeSinceLastLODChange = 0.0f; // 防抖动计时器
};

// ===== 共享 Fragment =====

// 人群全局配置——所有行人共享
USTRUCT()
struct FCrowdGlobalSharedFragment : public FMassSharedFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float GlobalTimeScale = 1.0f;

    UPROPERTY()
    float MaxCrowdDensity = 4.0f;   // 每平方米最多实体数

    UPROPERTY()
    bool bEnableCollisionAvoidance = true;
};

// 渲染配置——同类实体共享
USTRUCT()
struct FCrowdRenderingSharedFragment : public FMassSharedFragment
{
    GENERATED_BODY()

    UPROPERTY()
    TSoftObjectPtr<UStaticMesh> HighLODMesh;

    UPROPERTY()
    TSoftObjectPtr<UStaticMesh> MediumLODMesh;

    UPROPERTY()
    TSoftObjectPtr<UMaterialInterface> Material;

    UPROPERTY()
    FVector MeshScale = FVector(1.0f);

    UPROPERTY()
    int32 ISMInstanceGroupIndex = 0; // ISM 实例分组
};

// ===== Tags =====

USTRUCT() struct FCrowdPedestrianTag : public FMassTag { GENERATED_BODY() };
USTRUCT() struct FCrowdHighLODTag : public FMassTag { GENERATED_BODY() };
USTRUCT() struct FCrowdMediumLODTag : public FMassTag { GENERATED_BODY() };
USTRUCT() struct FCrowdLowLODTag : public FMassTag { GENERATED_BODY() };
USTRUCT() struct FCrowdNavigationActiveTag : public FMassTag { GENERATED_BODY() };
```

### 2.3 Processor 设计——Movement Processor

```cpp
// CrowdMovementProcessor.h & .cpp
// CrowdMovementProcessor.h
#pragma once

#include "MassProcessor.h"
#include "CrowdMovementProcessor.generated.h"

UCLASS()
class UCrowdMovementProcessor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UCrowdMovementProcessor();

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;

private:
    FMassEntityQuery MovementQuery;
};
```

```cpp
// CrowdMovementProcessor.cpp
#include "CrowdMovementProcessor.h"
#include "CrowdProjectFragments.h"
#include "MassCommonFragments.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassMovementFragments.h"

UCrowdMovementProcessor::UCrowdMovementProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::Movement;
    ExecutionOrder.ExecuteAfter.Add(
        TEXT("MassBeginMovementProcessor"));
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UCrowdMovementProcessor::ConfigureQueries()
{
    MovementQuery.AddRequirement<FTransformFragment>(
        EMassFragmentAccess::ReadWrite);
    MovementQuery.AddRequirement<FCrowdMovementFragment>(
        EMassFragmentAccess::ReadWrite);
    MovementQuery.AddRequirement<FCrowdBehaviorFragment>(
        EMassFragmentAccess::ReadOnly);
    MovementQuery.AddRequirement<FCrowdAnimationFragment>(
        EMassFragmentAccess::ReadWrite);
    MovementQuery.AddTagRequirement<FCrowdPedestrianTag>(
        EMassFragmentPresence::All);
    MovementQuery.RegisterWithProcessor(*this);
}

void UCrowdMovementProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    MovementQuery.ForEachEntityChunk(EntityManager, Context,
        [](FMassExecutionContext& Context)
        {
            const int32 NumEntities = Context.GetNumEntities();
            const float DeltaTime = Context.GetDeltaTimeSeconds();

            TArrayView<FTransformFragment> Transforms =
                Context.GetMutableFragmentView<FTransformFragment>();
            TArrayView<FCrowdMovementFragment> Movements =
                Context.GetMutableFragmentView<FCrowdMovementFragment>();
            const TArrayView<FCrowdBehaviorFragment> Behaviors =
                Context.GetFragmentView<FCrowdBehaviorFragment>();
            TArrayView<FCrowdAnimationFragment> Animations =
                Context.GetMutableFragmentView<FCrowdAnimationFragment>();

            for (int32 i = 0; i < NumEntities; ++i)
            {
                FCrowdMovementFragment& Move = Movements[i];
                const FCrowdBehaviorFragment& Behavior = Behaviors[i];

                // 1. 应用 Steering 力计算目标速度
                FVector TargetVelocity = FVector::ZeroVector;

                if (!Behavior.SteeringForce.IsNearlyZero())
                {
                    TargetVelocity = Behavior.SteeringForce.GetSafeNormal()
                                     * Move.DesiredSpeed;
                }

                // 2. 平滑加速到目标速度
                FVector CurrentVelocity =
                    Transforms[i].GetTransform().GetRotation().Vector()
                    * Move.CurrentSpeed;

                if (!TargetVelocity.IsNearlyZero())
                {
                    CurrentVelocity = FMath::VInterpTo(
                        CurrentVelocity,
                        TargetVelocity,
                        DeltaTime,
                        Move.Acceleration / FMath::Max(Move.CurrentSpeed, 1.0f));
                }
                else
                {
                    // 无 Steering 时减速到 0
                    CurrentVelocity = FMath::VInterpTo(
                        CurrentVelocity,
                        FVector::ZeroVector,
                        DeltaTime,
                        2.0f);
                }

                Move.CurrentSpeed = CurrentVelocity.Size();
                if (Move.CurrentSpeed > Move.MaxSpeed)
                {
                    CurrentVelocity =
                        CurrentVelocity.GetSafeNormal() * Move.MaxSpeed;
                    Move.CurrentSpeed = Move.MaxSpeed;
                }

                // 3. 更新位置
                FTransform& Transform = Transforms[i].GetMutableTransform();
                Transform.AddToTranslation(CurrentVelocity * DeltaTime);

                // 4. 更新朝向（面向速度方向）
                if (Move.CurrentSpeed > 10.0f)
                {
                    const FRotator TargetRotation = CurrentVelocity.Rotation();
                    const FRotator CurrentRotation = Transform.Rotator();
                    const FRotator NewRotation = FMath::RInterpTo(
                        CurrentRotation, TargetRotation,
                        DeltaTime, Move.RotationSpeed);
                    Transform.SetRotation(NewRotation.Quaternion());
                }

                // 5. 更新动画状态
                FCrowdAnimationFragment& Anim = Animations[i];
                if (Move.CurrentSpeed < 5.0f)
                {
                    Anim.CurrentAnimState = 0; // Idle
                    Anim.PlayRate = 1.0f;
                }
                else if (Move.CurrentSpeed < Move.MaxSpeed * 0.6f)
                {
                    Anim.CurrentAnimState = 1; // Walk
                    Anim.PlayRate = Move.CurrentSpeed / 150.0f;
                }
                else
                {
                    Anim.CurrentAnimState = 2; // Run
                    Anim.PlayRate = Move.CurrentSpeed / 300.0f;
                }
            }
        });
}
```

### 2.4 人群行为 Processor——Boids 三规则

```cpp
// CrowdBehaviorProcessor.h
#pragma once

#include "MassProcessor.h"
#include "CrowdBehaviorProcessor.generated.h"

UCLASS()
class UCrowdBehaviorProcessor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UCrowdBehaviorProcessor();

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;

private:
    FMassEntityQuery BehaviorQuery;

    // Boids 参数
    UPROPERTY(EditAnywhere, Category = "Boids")
    float SeparationRadius = 200.0f;

    UPROPERTY(EditAnywhere, Category = "Boids")
    float AlignmentRadius = 500.0f;

    UPROPERTY(EditAnywhere, Category = "Boids")
    float CohesionRadius = 800.0f;
};
```

```cpp
// CrowdBehaviorProcessor.cpp
#include "CrowdBehaviorProcessor.h"
#include "CrowdProjectFragments.h"
#include "MassCommonFragments.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"

UCrowdBehaviorProcessor::UCrowdBehaviorProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::Behavior;
    ExecutionOrder.ExecuteAfter.Add(
        UCrowdLODProcessor::StaticClass()->GetFName());
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UCrowdBehaviorProcessor::ConfigureQueries()
{
    BehaviorQuery.AddRequirement<FTransformFragment>(
        EMassFragmentAccess::ReadOnly);
    BehaviorQuery.AddRequirement<FCrowdMovementFragment>(
        EMassFragmentAccess::ReadOnly);
    BehaviorQuery.AddRequirement<FCrowdBehaviorFragment>(
        EMassFragmentAccess::ReadWrite);
    BehaviorQuery.AddTagRequirement<FCrowdHighLODTag>(
        EMassFragmentPresence::All);
    BehaviorQuery.RegisterWithProcessor(*this);
}

void UCrowdBehaviorProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    // 第一遍: 收集所有 High LOD 实体的位置和速度
    struct FEntitySnapshot
    {
        FVector Position;
        FVector Velocity;
        FMassEntityHandle Handle;
    };

    TArray<FEntitySnapshot> Snapshots;
    Snapshots.Reserve(2048);

    BehaviorQuery.ForEachEntityChunk(EntityManager, Context,
        [&Snapshots](FMassExecutionContext& Context)
        {
            const TArrayView<FTransformFragment> Transforms =
                Context.GetFragmentView<FTransformFragment>();
            const TArrayView<FCrowdMovementFragment> Movements =
                Context.GetFragmentView<FCrowdMovementFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                const FTransform& T = Transforms[i].GetTransform();
                Snapshots.Add({
                    T.GetLocation(),
                    T.GetRotation().Vector() * Movements[i].CurrentSpeed,
                    Context.GetEntity(i)
                });
            }
        });

    // 第二遍: 计算 Boids Steering
    BehaviorQuery.ForEachEntityChunk(EntityManager, Context,
        [this, &Snapshots](FMassExecutionContext& Context)
        {
            const TArrayView<FTransformFragment> Transforms =
                Context.GetFragmentView<FTransformFragment>();
            TArrayView<FCrowdBehaviorFragment> Behaviors =
                Context.GetMutableFragmentView<FCrowdBehaviorFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                const FVector& MyPos =
                    Transforms[i].GetTransform().GetLocation();
                FCrowdBehaviorFragment& Behavior = Behaviors[i];

                FVector SeparationForce = FVector::ZeroVector;
                FVector AlignmentForce = FVector::ZeroVector;
                FVector CohesionForce = FVector::ZeroVector;
                FVector CohesionCenter = FVector::ZeroVector;
                int32 SepCount = 0, AliCount = 0, CohCount = 0;

                for (const FEntitySnapshot& Other : Snapshots)
                {
                    if (Other.Handle == Context.GetEntity(i))
                        continue;

                    const FVector ToOther = Other.Position - MyPos;
                    const float Distance = ToOther.Size();

                    // 分离：近距离推开
                    if (Distance < SeparationRadius && Distance > 0.1f)
                    {
                        const float Strength = 1.0f - (Distance / SeparationRadius);
                        SeparationForce -=
                            ToOther.GetSafeNormal() * Strength;
                        ++SepCount;
                    }

                    // 对齐：匹配邻居速度方向
                    if (Distance < AlignmentRadius)
                    {
                        AlignmentForce += Other.Velocity;
                        ++AliCount;
                    }

                    // 聚拢：向邻居中心移动
                    if (Distance < CohesionRadius)
                    {
                        CohesionCenter += Other.Position;
                        ++CohCount;
                    }
                }

                // 归一化并加权
                if (SepCount > 0) SeparationForce /= (float)SepCount;
                if (AliCount > 0) AlignmentForce /= (float)AliCount;
                if (CohCount > 0)
                {
                    CohesionCenter /= (float)CohCount;
                    CohesionForce = (CohesionCenter - MyPos).GetSafeNormal();
                }

                Behavior.SteeringForce =
                    SeparationForce  * Behavior.SeparationWeight +
                    AlignmentForce   * Behavior.AlignmentWeight +
                    CohesionForce    * Behavior.CohesionWeight;
            }
        });
}
```

### 2.5 LOD Processor——动态 Fragment 切换

```cpp
// CrowdLODProcessor.h
#pragma once

#include "MassProcessor.h"
#include "CrowdLODProcessor.generated.h"

UCLASS()
class UCrowdLODProcessor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UCrowdLODProcessor();

    UPROPERTY(EditAnywhere, Category = "LOD")
    float HighLODDistance = 5000.0f; // 50m

    UPROPERTY(EditAnywhere, Category = "LOD")
    float MediumLODDistance = 15000.0f; // 150m

    UPROPERTY(EditAnywhere, Category = "LOD")
    float LowLODDistance = 30000.0f; // 300m

    UPROPERTY(EditAnywhere, Category = "LOD")
    float LODChangeHysteresis = 500.0f; // 5m 防抖动

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;

private:
    FMassEntityQuery LODQuery;
};
```

```cpp
// CrowdLODProcessor.cpp
#include "CrowdLODProcessor.h"
#include "CrowdProjectFragments.h"
#include "MassCommonFragments.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassCommandBuffer.h"
#include "GameFramework/PlayerController.h"

UCrowdLODProcessor::UCrowdLODProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::LOD;
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UCrowdLODProcessor::ConfigureQueries()
{
    LODQuery.AddRequirement<FTransformFragment>(
        EMassFragmentAccess::ReadOnly);
    LODQuery.AddRequirement<FCrowdLODFragment>(
        EMassFragmentAccess::ReadWrite);
    LODQuery.AddTagRequirement<FCrowdPedestrianTag>(
        EMassFragmentPresence::All);
    LODQuery.RegisterWithProcessor(*this);
}

void UCrowdLODProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    // 获取所有玩家视点
    TArray<FVector> ViewerLocations;
    if (UWorld* World = Context.GetWorld())
    {
        for (FConstPlayerControllerIterator It =
             World->GetPlayerControllerIterator(); It; ++It)
        {
            if (APlayerController* PC = It->Get())
            {
                FVector Loc;
                FRotator Rot;
                PC->GetPlayerViewPoint(Loc, Rot);
                ViewerLocations.Add(Loc);
            }
        }
    }

    const float DeltaTime = Context.GetDeltaTimeSeconds();
    const float Hysteresis = LODChangeHysteresis;

    LODQuery.ForEachEntityChunk(EntityManager, Context,
        [this, &ViewerLocations, DeltaTime, Hysteresis]
        (FMassExecutionContext& Context)
        {
            const TArrayView<FTransformFragment> Transforms =
                Context.GetFragmentView<FTransformFragment>();
            TArrayView<FCrowdLODFragment> LODFrags =
                Context.GetMutableFragmentView<FCrowdLODFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                const FVector EntityPos =
                    Transforms[i].GetTransform().GetLocation();

                // 计算离最近视点的距离
                float MinDistSq = FLT_MAX;
                for (const FVector& ViewLoc : ViewerLocations)
                {
                    MinDistSq = FMath::Min(MinDistSq,
                        FVector::DistSquared(EntityPos, ViewLoc));
                }

                const float Distance = FMath::Sqrt(MinDistSq);
                FCrowdLODFragment& LODFrag = LODFrags[i];

                // 防抖动：只有距离跨过足够大的阈值且停留足够久才切换
                LODFrag.TimeSinceLastLODChange += DeltaTime;
                int32 NewLODLevel = 3; // Off

                if (Distance < HighLODDistance + Hysteresis)
                    NewLODLevel = 0; // High
                else if (Distance < MediumLODDistance + Hysteresis)
                    NewLODLevel = 1; // Medium
                else if (Distance < LowLODDistance + Hysteresis)
                    NewLODLevel = 2; // Low

                // 反向防抖动
                if (NewLODLevel > LODFrag.CurrentLODLevel)
                {
                    const float CheckDist = (NewLODLevel == 1)
                        ? HighLODDistance - Hysteresis
                        : (NewLODLevel == 2)
                        ? MediumLODDistance - Hysteresis
                        : LowLODDistance - Hysteresis;

                    if (Distance < CheckDist)
                        NewLODLevel = LODFrag.CurrentLODLevel;
                }

                // 执行切换（最少停留 0.5 秒）
                if (NewLODLevel != LODFrag.CurrentLODLevel &&
                    LODFrag.TimeSinceLastLODChange > 0.5f)
                {
                    const FMassEntityHandle Entity = Context.GetEntity(i);

                    // 移除旧 LOD Tag
                    switch (LODFrag.CurrentLODLevel)
                    {
                    case 0: Context.Defer().RemoveTag<FCrowdHighLODTag>(Entity); break;
                    case 1: Context.Defer().RemoveTag<FCrowdMediumLODTag>(Entity); break;
                    case 2: Context.Defer().RemoveTag<FCrowdLowLODTag>(Entity); break;
                    default: break;
                    }

                    // 添加新 LOD Tag
                    switch (NewLODLevel)
                    {
                    case 0: Context.Defer().AddTag<FCrowdHighLODTag>(Entity); break;
                    case 1: Context.Defer().AddTag<FCrowdMediumLODTag>(Entity); break;
                    case 2: Context.Defer().AddTag<FCrowdLowLODTag>(Entity); break;
                    default: break;
                    }

                    LODFrag.PreviousLODLevel = LODFrag.CurrentLODLevel;
                    LODFrag.CurrentLODLevel = NewLODLevel;
                    LODFrag.TimeSinceLastLODChange = 0.0f;
                }

                LODFrag.DistanceToViewer = Distance;
            }
        });
}
```

### 2.6 生成器——从 ZoneGraph 生成实体

```cpp
// CrowdSpawnerSubsystem.h
#pragma once

#include "Subsystems/WorldSubsystem.h"
#include "MassEntityHandle.h"
#include "CrowdSpawnerSubsystem.generated.h"

UCLASS()
class UCrowdSpawnerSubsystem : public UWorldSubsystem
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable)
    void SpawnCrowd(int32 Count, const FVector& RegionCenter, float RegionRadius);

    UFUNCTION(BlueprintCallable)
    int32 GetActiveEntityCount() const;

private:
    UPROPERTY()
    TArray<FMassEntityHandle> SpawnedEntities;
};
```

```cpp
// CrowdSpawnerSubsystem.cpp
#include "CrowdSpawnerSubsystem.h"
#include "CrowdProjectFragments.h"
#include "MassCommonFragments.h"
#include "MassEntitySubsystem.h"
#include "MassEntityManager.h"
#include "Engine/World.h"

void UCrowdSpawnerSubsystem::SpawnCrowd(
    int32 Count, const FVector& RegionCenter, float RegionRadius)
{
    UMassEntitySubsystem* EntitySubsystem =
        GetWorld()->GetSubsystem<UMassEntitySubsystem>();
    check(EntitySubsystem);

    FMassEntityManager& EM = EntitySubsystem->GetMutableEntityManager();

    // 创建基础 Archetype（High LOD 初始状态）
    FMassArchetypeHandle Archetype = EM.CreateArchetype({
        FTransformFragment::StaticStruct(),
        FCrowdMovementFragment::StaticStruct(),
        FCrowdBehaviorFragment::StaticStruct(),
        FCrowdAnimationFragment::StaticStruct(),
        FCrowdLODFragment::StaticStruct(),
        FCrowdPedestrianTag::StaticStruct(),
        FCrowdHighLODTag::StaticStruct() // 初始为 High LOD
    });

    // 批量创建
    TArray<FMassEntityHandle> NewEntities;
    EM.BatchCreateEntities(Archetype, Count, NewEntities);

    for (int32 i = 0; i < Count; ++i)
    {
        const FMassEntityHandle& Handle = NewEntities[i];

        // 随机位置
        const FVector SpawnPos = RegionCenter + FVector(
            FMath::FRandRange(-RegionRadius, RegionRadius),
            FMath::FRandRange(-RegionRadius, RegionRadius),
            0.0f);

        FTransformFragment& TransformFrag =
            EM.GetFragmentDataChecked<FTransformFragment>(Handle);
        TransformFrag.SetTranslation(SpawnPos);

        const FRotator RandomRot(0.0f, FMath::FRandRange(0.0f, 360.0f), 0.0f);
        TransformFrag.SetRotation(RandomRot.Quaternion());

        // 随机移动参数——增加人群多样性
        FCrowdMovementFragment& MoveFrag =
            EM.GetFragmentDataChecked<FCrowdMovementFragment>(Handle);
        MoveFrag.DesiredSpeed = FMath::FRandRange(80.0f, 200.0f);
        MoveFrag.MaxSpeed = MoveFrag.DesiredSpeed * 1.3f;
        MoveFrag.Acceleration = FMath::FRandRange(200.0f, 600.0f);

        // 随机行为参数
        FCrowdBehaviorFragment& BehaviorFrag =
            EM.GetFragmentDataChecked<FCrowdBehaviorFragment>(Handle);
        BehaviorFrag.SeparationWeight = FMath::FRandRange(1.0f, 2.0f);
        BehaviorFrag.AlignmentWeight = FMath::FRandRange(0.5f, 1.5f);
        BehaviorFrag.CohesionWeight = FMath::FRandRange(0.3f, 1.2f);
        BehaviorFrag.AvoidanceRadius = FMath::FRandRange(100.0f, 200.0f);

        // 随机动画偏移——避免所有实体动画同步
        FCrowdAnimationFragment& AnimFrag =
            EM.GetFragmentDataChecked<FCrowdAnimationFragment>(Handle);
        AnimFrag.CycleOffset = FMath::FRandRange(0.0f, 1.0f);
        AnimFrag.CurrentAnimState = 0; // 初始 Idle

        // LOD 初始状态
        FCrowdLODFragment& LODFrag =
            EM.GetFragmentDataChecked<FCrowdLODFragment>(Handle);
        LODFrag.CurrentLODLevel = 0; // High
        LODFrag.PreviousLODLevel = 0;
        LODFrag.TimeSinceLastLODChange = 1.0f;
    }

    SpawnedEntities.Append(NewEntities);

    UE_LOG(LogTemp, Log, TEXT(
        "CrowdSpawner: Spawned %d entities (Total: %d) in %.0fm radius around %s"),
        Count,
        SpawnedEntities.Num(),
        RegionRadius / 100.0f,
        *RegionCenter.ToString());
}

int32 UCrowdSpawnerSubsystem::GetActiveEntityCount() const
{
    return SpawnedEntities.Num();
}
```

### 2.7 蓝图配置步骤

```
1. 创建 MassEntityConfigAsset:
   Content/Config/DA_CrowdPedestrian

   在 Traits 数组中添加:
   - "Crowd Movement Trait" (自定义)
     参数:
       DefaultDesiredSpeed = 150.0
       DefaultMaxSpeed = 200.0
   
   - "Crowd Behavior Trait" (自定义)
     参数:
       SeparationWeight = 1.5
       AlignmentWeight = 1.0
       CohesionWeight = 0.8
   
   - "Crowd LOD Trait" (自定义)
     参数:
       HighLODDistance = 5000.0
       MediumLODDistance = 15000.0
       LowLODDistance = 30000.0
   
   - "Mass Representation Trait" (UE 内置)
     参数:
       StaticMesh = SM_Character_Base
       Material = M_Crowd_Instanced

2. 创建 ZoneGraph:
   - 打开 ZoneGraph 编辑器 (Window → ZoneGraph)
   - 绘制步道路径网络
   - 生成 ZoneGraphData
   - 设置 ZoneShape 的 Tags: "Sidewalk", "Crosswalk"

3. 创建 GameMode:
   - 新建 Blueprint: BP_CrowdGameMode (继承 AGameModeBase)
   - 在 BeginPlay 中调用 "Get CrowdSpawnerSubsystem → SpawnCrowd"
   - 设置参数: Count=5000, Center=(0,0,0), Radius=10000

4. 场景设置:
   - 将 BP_CrowdGameMode 设为关卡 GameMode
   - 放置 AMassVisualizer 或 MassDebugger 可视化实体
   - 按 ` (反引号) 打开控制台, 输入:
     - mass.debug.DrawEntityFragments 1  (显示 Fragment 数据)
     - mass.debug.DrawLOD 1             (显示 LOD 级别颜色)
     - stat mass                         (查看 Mass 性能统计)

5. 运行:
   - PIE (Play In Editor)
   - 控制台输入: CrowdSpawnerSubsystem.SpawnCrowd 10000
   - 观察人群自然流动
   - stat unit 查看帧率
```

### 2.8 性能分析

在项目中添加性能统计代码：

```cpp
// CrowdPerformanceMonitor.h
#pragma once

#include "MassProcessor.h"
#include "CrowdPerformanceMonitor.generated.h"

UCLASS()
class UCrowdPerformanceMonitor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UCrowdPerformanceMonitor();

protected:
    virtual void ConfigureQueries() override {}
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;
};
```

```cpp
// CrowdPerformanceMonitor.cpp
#include "CrowdPerformanceMonitor.h"
#include "MassEntitySubsystem.h"
#include "Engine/World.h"

UCrowdPerformanceMonitor::UCrowdPerformanceMonitor()
{
    bAutoRegisterWithProcessingPhases = true;
    // 在所有 Phase 之后执行（仅统计）
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::SyncWorldToMass;
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UCrowdPerformanceMonitor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    static float AccumTime = 0.0f;
    static int32 FrameCount = 0;

    AccumTime += Context.GetDeltaTimeSeconds();
    ++FrameCount;

    // 每秒输出一次统计
    if (AccumTime >= 1.0f)
    {
        const int32 TotalEntities = EntityManager.DebugGetEntityCount();
        const float AvgFrameTime = (AccumTime / FrameCount) * 1000.0f;
        const float AvgFPS = FrameCount / AccumTime;

        UE_LOG(LogTemp, Display, TEXT(
            "=== Mass Crowd Performance (1s avg) ==="));
        UE_LOG(LogTemp, Display, TEXT(
            "  Total Entities: %d"), TotalEntities);
        UE_LOG(LogTemp, Display, TEXT(
            "  Avg Frame Time: %.2f ms"), AvgFrameTime);
        UE_LOG(LogTemp, Display, TEXT(
            "  Avg FPS: %.1f"), AvgFPS);
        UE_LOG(LogTemp, Display, TEXT(
            "  Entities/ms: %.1f"), TotalEntities / AvgFrameTime);

        // 按 LOD 级别统计实体数
        // （需要通过 Archetype 查询——此处为简化版本）
        UE_LOG(LogTemp, Display, TEXT(
            "  Approx CPU cost per entity: %.3f ms"),
            AvgFrameTime / FMath::Max(TotalEntities, 1));
        UE_LOG(LogTemp, Display, TEXT(
            "========================================"));

        AccumTime = 0.0f;
        FrameCount = 0;
    }
}
```

**预期性能数据**（RTX 3070 Ti + Ryzen 7 6800H）：

| 实体数 | High LOD | Medium LOD | Low LOD | 帧时间 | FPS |
|-------|---------|-----------|---------|-------|-----|
| 1,000 | 1,000 | 0 | 0 | 5.2ms | 192 |
| 5,000 | 800 | 2,200 | 2,000 | 8.1ms | 123 |
| 10,000 | 500 | 4,500 | 5,000 | 12.3ms | 81 |
| 20,000 | 200 | 6,000 | 13,800 | 22.7ms | 44 |

---

## 3. 练习

### 练习 1: 基础练习 —— 集成 ZoneGraph 导航

为人群实体添加 `FMassZoneGraphLaneLocationFragment` 和 `FMassZoneGraphPathFragment`。创建 `UZoneGraphMovementProcessor`，读取路径点并驱动实体沿 ZoneGraph 步道移动。在 ZoneGraph 编辑器中绘制闭合路径。验证实体沿路径行走而非随机漫游。

### 练习 2: 进阶练习 —— 红绿灯与交通系统

创建 `UTrafficLightProcessor`：
1. 定义 `FTrafficLightFragment`（`int32 CurrentPhase` — 0=Green/1=Yellow/2=Red, `float PhaseTime`）
2. 在 Processor 中读取 `FMassZoneGraphLaneLocationFragment`，检查实体前方是否有 Crosswalk
3. 如果有 Crosswalk 且当前相位为 Red，将 `FCrowdMovementFragment::DesiredSpeed` 设置为 0
4. 实现完整的红灯停、绿灯行逻辑

### 练习 3: 挑战练习 —— 完整的 Day/Night 人群密度系统

创建 `UCrowdDensityManager`：
1. 在游戏时间 8:00-9:00（早高峰）和 17:00-18:00（晚高峰），将人群密度提高到 `MaxCrowdDensity = 8.0`
2. 在 2:00-5:00（凌晨），将密度降低到 1.0
3. 通过 Spawner 动态生成/销毁实体来调整密度
4. 使用 `FMassEntitySpawnDataGenerator` 按密度生成实体到 ZoneGraph 入口
5. 在 HUD 显示当前时间和活跃实体数
6. 验证密度变化流畅无卡顿（在 5 分钟内从凌晨过渡到早高峰）

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // ZoneGraphMovementProcessor.h
> #pragma once
> #include "MassProcessor.h"
> #include "ZoneGraphMovementProcessor.generated.h"
>
> UCLASS()
> class UZoneGraphMovementProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UZoneGraphMovementProcessor()
>     {
>         bAutoRegisterWithProcessingPhases = true;
>         ExecutionOrder.ExecuteInGroup =
>             UE::Mass::ProcessorGroupNames::Movement;
>         ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
>     }
>
>     // 期望移动速度
>     UPROPERTY(EditAnywhere, Category = "Movement")
>     float WalkingSpeed = 150.0f;  // cm/s
>
>     // 到达路径点判距阈值
>     UPROPERTY(EditAnywhere, Category = "Movement")
>     float ArrivalTolerance = 100.0f;  // cm
>
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void Execute(FMassEntityManager& EntityManager,
>                          FMassExecutionContext& Context) override;
> private:
>     FMassEntityQuery PathFollowQuery;
> };
> ```
>
> ```cpp
> // ZoneGraphMovementProcessor.cpp
> #include "ZoneGraphMovementProcessor.h"
> #include "CrowdProjectFragments.h"
> #include "MassCommonFragments.h"
> #include "MassMovementFragments.h"
> #include "ZoneGraphSubsystem.h"
> #include "MassNavigationFragments.h"
> #include "MassEntityManager.h"
> #include "MassExecutionContext.h"
>
> void UZoneGraphMovementProcessor::ConfigureQueries()
> {
>     // 需要 ZoneGraph 路径 Fragment + Transform + 移动参数
>     PathFollowQuery.AddRequirement<FMassZoneGraphPathFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PathFollowQuery.AddRequirement<FMassZoneGraphLaneLocationFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PathFollowQuery.AddRequirement<FTransformFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PathFollowQuery.AddRequirement<FCrowdMovementFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PathFollowQuery.AddTagRequirement<FCrowdNavigationActiveTag>(
>         EMassFragmentPresence::All);
>     PathFollowQuery.RegisterWithProcessor(*this);
> }
>
> void UZoneGraphMovementProcessor::Execute(
>     FMassEntityManager& Mgr, FMassExecutionContext& Ctx)
> {
>     const UZoneGraphSubsystem* ZoneGraph =
>         Ctx.GetSubsystem<UZoneGraphSubsystem>();
>     if (!ZoneGraph) return;
>
>     const float DeltaTime = Ctx.GetDeltaTimeSeconds();
>
>     PathFollowQuery.ForEachEntityChunk(Mgr, Ctx,
>         [this, ZoneGraph, DeltaTime](FMassExecutionContext& Chunk)
>         {
>             auto Paths = Chunk.GetMutableFragmentView<
>                 FMassZoneGraphPathFragment>();
>             auto Lanes = Chunk.GetMutableFragmentView<
>                 FMassZoneGraphLaneLocationFragment>();
>             auto Transforms = Chunk.GetMutableFragmentView<
>                 FTransformFragment>();
>             auto Movements = Chunk.GetMutableFragmentView<
>                 FCrowdMovementFragment>();
>
>             for (int32 i = 0; i < Chunk.GetNumEntities(); ++i)
>             {
>                 auto& Path = Paths[i];
>                 auto& Lane = Lanes[i];
>                 FTransform& T = Transforms[i].GetMutableTransform();
>                 auto& Move = Movements[i];
>                 const FVector CurrentPos = T.GetLocation();
>
>                 // 1. 如果没有路径或已到达终点，请求新路径
>                 if (Path.PathPoints.IsEmpty() ||
>                     Path.CurrentPointIndex >= Path.PathPoints.Num())
>                 {
>                     // 已到达终点——在实际项目中从路径请求系统获取下一路径
>                     continue;
>                 }
>
>                 // 2. 获取当前目标点
>                 const FVector TargetPoint =
>                     Path.PathPoints[Path.CurrentPointIndex];
>
>                 // 3. 检查是否到达当前目标点
>                 const float DistToTarget =
>                     FVector::Dist(CurrentPos, TargetPoint);
>
>                 if (DistToTarget <= ArrivalTolerance)
>                 {
>                     // 到达当前点，前进到下一个路径点
>                     Path.CurrentPointIndex++;
>                     // 已到达终点则不继续移动
>                     if (Path.CurrentPointIndex >= Path.PathPoints.Num())
>                         continue;
>                 }
>
>                 // 4. 计算朝目标点的移动方向
>                 const FVector CurrentTarget =
>                     Path.PathPoints[Path.CurrentPointIndex];
>                 const FVector MoveDirection =
>                     (CurrentTarget - CurrentPos).GetSafeNormal();
>
>                 // 5. 沿 ZoneGraph 车道移动——结合 Lane 位置进行平滑
>                 // 实际项目中用 ZoneGraphSubsystem 查询车道切线
>                 const FVector NewPos = CurrentPos +
>                     MoveDirection * WalkingSpeed * DeltaTime;
>                 T.SetLocation(NewPos);
>
>                 // 6. 更新朝向（面对移动方向）
>                 if (!MoveDirection.IsNearlyZero())
>                 {
>                     const FRotator NewRotation =
>                         MoveDirection.Rotation();
>                     T.SetRotation(FQuat::Slerp(
>                         T.GetRotation(),
>                         NewRotation.Quaternion(),
>                         FMath::Min(1.0f,
>                             Move.RotationSpeed * DeltaTime / 90.0f)));
>                 }
>
>                 // 7. 更新车道位置
>                 ZoneGraph->FindNearestLane(NewPos, Lane);
>
>                 // 8. 更新当前速度
>                 Move.CurrentSpeed = WalkingSpeed;
>             }
>         });
> }
> ```
>
> **Trait 配置——在 Spawner 中为实体添加 ZoneGraph Fragment：**
>
> ```cpp
> // CrowdZoneGraphTrait.h
> UCLASS()
> class UCrowdZoneGraphTrait : public UMassEntityTraitBase
> {
>     GENERATED_BODY()
> public:
>     virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext,
>                                const UWorld& World) const override
>     {
>         // 添加 ZoneGraph 路径 Fragment（为空，后续由路径请求系统填充）
>         BuildContext.AddFragment<FMassZoneGraphPathFragment>();
>         BuildContext.AddFragment<FMassZoneGraphLaneLocationFragment>();
>
>         // 标记为导航激活实体
>         BuildContext.AddTag<FCrowdNavigationActiveTag>();
>     }
> };
> ```
>
> **验证步骤**：在 ZoneGraph 编辑器中绘制闭合步道回路 → 在 Spawner 的 `MassEntityConfig` 中添加 `UCrowdZoneGraphTrait` → 运行游戏 → 观察行人是否沿步道行走而非随机漂移。

> [!tip]- 练习 2 参考答案
> ```cpp
> // TrafficLightFragments.h
> #pragma once
> #include "MassEntityTypes.h"
> #include "TrafficLightFragments.generated.h"
>
> // 红绿灯状态 Fragment（挂载在 TrafficLight 实体上）
> USTRUCT()
> struct FTrafficLightFragment : public FMassFragment
> {
>     GENERATED_BODY()
>
>     // 0=Green, 1=Yellow, 2=Red
>     UPROPERTY() int32 CurrentPhase = 0;
>
>     // 当前相位已经过的时间（秒）
>     UPROPERTY() float PhaseTime = 0.0f;
>
>     // 各相位持续时间（秒）
>     UPROPERTY() float GreenDuration = 30.0f;
>     UPROPERTY() float YellowDuration = 3.0f;
>     UPROPERTY() float RedDuration = 30.0f;
>
>     // 红绿灯影响范围（cm）
>     UPROPERTY() float InfluenceRadius = 3000.0f;
> };
> ```
>
> ```cpp
> // TrafficLightProcessor.h
> #pragma once
> #include "MassProcessor.h"
> #include "TrafficLightProcessor.generated.h"
>
> UCLASS()
> class UTrafficLightProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UTrafficLightProcessor()
>     {
>         bAutoRegisterWithProcessingPhases = true;
>         // 在导航 Processor 之后、移动 Processor 之前执行
>         ExecutionOrder.ExecuteInGroup =
>             UE::Mass::ProcessorGroupNames::Behavior;
>         ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
>     }
>
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void Execute(FMassEntityManager& EntityManager,
>                          FMassExecutionContext& Context) override;
>
> private:
>     FMassEntityQuery TrafficLightQuery;   // 更新红绿灯相位
>     FMassEntityQuery CrowdQuery;          // 应用红绿灯到行人
> };
> ```
>
> ```cpp
> // TrafficLightProcessor.cpp (核心实现)
> void UTrafficLightProcessor::ConfigureQueries()
> {
>     // 查询 1：所有红绿灯实体
>     TrafficLightQuery.AddRequirement<FTrafficLightFragment>(
>         EMassFragmentAccess::ReadWrite);
>     TrafficLightQuery.AddRequirement<FTransformFragment>(
>         EMassFragmentAccess::ReadOnly);
>     TrafficLightQuery.RegisterWithProcessor(*this);
>
>     // 查询 2：所有有导航数据的行人实体
>     CrowdQuery.AddRequirement<FTransformFragment>(
>         EMassFragmentAccess::ReadOnly);
>     CrowdQuery.AddRequirement<FCrowdMovementFragment>(
>         EMassFragmentAccess::ReadWrite);
>     CrowdQuery.AddRequirement<FMassZoneGraphLaneLocationFragment>(
>         EMassFragmentAccess::ReadOnly);
>     CrowdQuery.AddTagRequirement<FCrowdPedestrianTag>(
>         EMassFragmentPresence::All);
>     CrowdQuery.RegisterWithProcessor(*this);
> }
>
> void UTrafficLightProcessor::Execute(
>     FMassEntityManager& Mgr, FMassExecutionContext& Ctx)
> {
>     const float DeltaTime = Ctx.GetDeltaTimeSeconds();
>
>     // ── 第一遍：更新所有红绿灯的相位 ──
>     TArray<FTransform> LightTransforms;
>     TArray<FTrafficLightFragment> LightStates;
>
>     TrafficLightQuery.ForEachEntityChunk(Mgr, Ctx,
>         [DeltaTime, &LightTransforms, &LightStates]
>         (FMassExecutionContext& Chunk)
>         {
>             auto Lights = Chunk.GetMutableFragmentView<
>                 FTrafficLightFragment>();
>             const auto Transforms =
>                 Chunk.GetFragmentView<FTransformFragment>();
>
>             for (int32 i = 0; i < Chunk.GetNumEntities(); ++i)
>             {
>                 auto& L = Lights[i];
>                 L.PhaseTime += DeltaTime;
>
>                 // 相位切换逻辑
>                 switch (L.CurrentPhase)
>                 {
>                 case 0: // Green → Yellow
>                     if (L.PhaseTime >= L.GreenDuration)
>                     {
>                         L.CurrentPhase = 1; L.PhaseTime = 0.0f;
>                     }
>                     break;
>                 case 1: // Yellow → Red
>                     if (L.PhaseTime >= L.YellowDuration)
>                     {
>                         L.CurrentPhase = 2; L.PhaseTime = 0.0f;
>                     }
>                     break;
>                 case 2: // Red → Green
>                     if (L.PhaseTime >= L.RedDuration)
>                     {
>                         L.CurrentPhase = 0; L.PhaseTime = 0.0f;
>                     }
>                     break;
>                 }
>
>                 // 收集红绿灯状态供第二遍使用
>                 LightTransforms.Add(
>                     Transforms[i].GetTransform());
>                 LightStates.Add(L);
>             }
>         });
>
>     if (LightStates.IsEmpty()) return;
>
>     // ── 第二遍：将红绿灯状态应用到行人 ──
>     CrowdQuery.ForEachEntityChunk(Mgr, Ctx,
>         [&LightTransforms, &LightStates]
>         (FMassExecutionContext& Chunk)
>         {
>             const auto Transforms =
>                 Chunk.GetFragmentView<FTransformFragment>();
>             const auto Lanes = Chunk.GetFragmentView<
>                 FMassZoneGraphLaneLocationFragment>();
>             auto Movements = Chunk.GetMutableFragmentView<
>                 FCrowdMovementFragment>();
>
>             for (int32 i = 0; i < Chunk.GetNumEntities(); ++i)
>             {
>                 const FVector PedPos =
>                     Transforms[i].GetTransform().GetLocation();
>                 auto& Move = Movements[i];
>
>                 // 恢复默认速度（假设上一帧可能被减速）
>                 Move.DesiredSpeed = Move.MaxSpeed;
>
>                 // 检查每个红绿灯
>                 for (int32 j = 0; j < LightStates.Num(); ++j)
>                 {
>                     const auto& L = LightStates[j];
>                     const FVector LightPos =
>                         LightTransforms[j].GetLocation();
>
>                     const float Dist = FVector::Dist(
>                         PedPos, LightPos);
>
>                     // 在红绿灯影响范围内
>                     if (Dist <= L.InfluenceRadius)
>                     {
>                         // 检查行人是否在 Crosswalk 车道上
>                         // （实际项目中通过 Lane 的 Tags 判断）
>                         const FZoneGraphTag CrosswalkTag =
>                             ZoneGraphTag::Crosswalk;
>                         const bool bIsOnCrosswalk =
>                             Lanes[i].Tags.Contains(CrosswalkTag);
>
>                         if (bIsOnCrosswalk)
>                         {
>                             switch (L.CurrentPhase)
>                             {
>                             case 0: // Green——正常通行
>                                 break; // 保持 DesiredSpeed
>                             case 1: // Yellow——减速
>                                 Move.DesiredSpeed =
>                                     FMath::Max(0.0f,
>                                         Move.MaxSpeed * 0.3f);
>                                 break;
>                             case 2: // Red——停止
>                                 Move.DesiredSpeed = 0.0f;
>                                 break;
>                             }
>                         }
>                     }
>                 }
>             }
>         });
> }
> ```
>
> **关键设计决策：**
> - 红绿灯影响只作用于斑马线上的行人（通过 `ZoneGraphTag::Crosswalk` 判断），不阻碍旁边车道的行人
> - `DesiredSpeed = 0` 而非直接改 `CurrentSpeed`——让 Movement Processor 通过加速度平滑减速，避免瞬时停止
> - Yellow 相位减速到 30% 而非立即停止，模拟"加速通过黄灯"的现实行为

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // CrowdDensityManager.h
> #pragma once
> #include "CoreMinimal.h"
> #include "GameFramework/Actor.h"
> #include "CrowdDensityManager.generated.h"
>
> UCLASS()
> class UCrowdDensityManager : public UObject
> {
>     GENERATED_BODY()
> public:
>     // 一天中的时间（0-24 小时，浮点数）
>     float GetCurrentTimeOfDay() const { return CurrentTime; }
>
>     // 根据当前时间计算目标人群密度
>     float CalculateTargetDensity() const;
>
>     // 更新当前密度（线性插值到目标值，防止突变）
>     void UpdateDensity(float DeltaTime, FCrowdGlobalSharedFragment& Config);
>
>     // 设置当前游戏时间（由外部时间系统调用）
>     void SetTimeOfDay(float Hour) { CurrentTime = Hour; }
>
> private:
>     float CurrentTime = 12.0f;   // 默认中午 12:00
>     float CurrentDensity = 4.0f; // 当前实际密度
>     float TargetDensity = 4.0f;  // 目标密度
> };
> ```
>
> ```cpp
> // CrowdDensityManager.cpp
> #include "CrowdDensityManager.h"
> #include "CrowdProjectFragments.h"
> #include "MassSpawner.h"
>
> float UCrowdDensityManager::CalculateTargetDensity() const
> {
>     const float Hour = CurrentTime;
>
>     // 凌晨 2:00 - 5:00：最低密度
>     if (Hour >= 2.0f && Hour < 5.0f)
>         return 1.0f;
>
>     // 早高峰 8:00 - 9:00：最高密度
>     if (Hour >= 8.0f && Hour < 9.0f)
>         return 8.0f;
>
>     // 晚高峰 17:00 - 18:00：最高密度
>     if (Hour >= 17.0f && Hour < 18.0f)
>         return 8.0f;
>
>     // 过渡时段：线性插值
>     // 5:00→8:00：密度从 1.0 渐变到 8.0
>     if (Hour >= 5.0f && Hour < 8.0f)
>     {
>         const float T = (Hour - 5.0f) / 3.0f;
>         return FMath::Lerp(1.0f, 8.0f, T);
>     }
>
>     // 9:00→17:00：白天中等密度
>     if (Hour >= 9.0f && Hour < 17.0f)
>     {
>         const float T = (Hour - 9.0f) / 8.0f;
>         return FMath::Lerp(8.0f, 5.0f, T);
>     }
>
>     // 18:00→2:00(+1天)：夜晚逐渐降低
>     if (Hour >= 18.0f)
>     {
>         const float T = (Hour - 18.0f) / 8.0f;
>         return FMath::Lerp(5.0f, 1.0f, FMath::Min(T, 1.0f));
>     }
>
>     // 0:00→2:00：继续降至最低
>     return FMath::Lerp(2.0f, 1.0f, Hour / 2.0f);
> }
>
> void UCrowdDensityManager::UpdateDensity(
>     float DeltaTime, FCrowdGlobalSharedFragment& Config)
> {
>     TargetDensity = CalculateTargetDensity();
>
>     // 缓慢过渡到目标密度——5 分钟内从凌晨过渡到早高峰
>     // 32 个单位变化在 300 秒内 = 约 0.1 单位/秒的过渡速度
>     constexpr float DensityChangeSpeed = 0.1f; // 密度单位/秒
>     CurrentDensity = FMath::FInterpConstantTo(
>         CurrentDensity, TargetDensity,
>         DeltaTime, DensityChangeSpeed);
>
>     Config.MaxCrowdDensity = CurrentDensity;
> }
>
> // ── DensityTimeProcessor（Mass Processor）──
> UCLASS()
> class UDensityTimeProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UDensityTimeProcessor()
>     {
>         bAutoRegisterWithProcessingPhases = true;
>         ExecutionOrder.ExecuteInGroup =
>             UE::Mass::ProcessorGroupNames::PrePhysics;
>         ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
>     }
>
>     // 时间流逝速度（1.0 = 实时，3600.0 = 1小时/秒）
>     UPROPERTY(EditAnywhere, Category = "Time")
>     float TimeScale = 600.0f; // 10分钟 = 1秒，方便测试日/夜循环
>
> protected:
>     virtual void ConfigureQueries() override
>     {
>         // 读取并修改全局 Shared Fragment（密度配置）
>         EntityQuery.AddRequirement<FCrowdGlobalSharedFragment>(
>             EMassFragmentAccess::ReadWrite);
>         EntityQuery.RegisterWithProcessor(*this);
>     }
>
>     virtual void Execute(FMassEntityManager& Mgr,
>                          FMassExecutionContext& Ctx) override
>     {
>         const float DeltaTime = Ctx.GetDeltaTimeSeconds();
>
>         EntityQuery.ForEachEntityChunk(Mgr, Ctx,
>             [this, DeltaTime](FMassExecutionContext& Chunk)
>             {
>                 auto Configs = Chunk.GetMutableFragmentView<
>                     FCrowdGlobalSharedFragment>();
>
>                 if (Configs.Num() > 0)
>                 {
>                     auto& Config = Configs[0];
>                     TimeOfDay += DeltaTime * TimeScale;
>                     if (TimeOfDay >= 24.0f) TimeOfDay -= 24.0f;
>
>                     DensityManager.SetTimeOfDay(TimeOfDay);
>                     DensityManager.UpdateDensity(DeltaTime, Config);
>
>                     // HUD 输出（实际项目用 ScreenDebugMessage 或 UMG）
>                     if (GEngine)
>                     {
>                         GEngine->AddOnScreenDebugMessage(
>                             -1, 0.0f, FColor::Cyan,
>                             FString::Printf(
>                                 TEXT("Time: %02d:%02d | "
>                                      "Density: %.1f | "
>                                      "Active: %d"),
>                                 (int32)TimeOfDay,
>                                 (int32)((TimeOfDay -
>                                     (int32)TimeOfDay) * 60),
>                                 DensityManager
>                                     .CalculateTargetDensity(),
>                                 Mgr.GetNumEntities()));
>                     }
>                 }
>             });
>     }
>
> private:
>     UCrowdDensityManager DensityManager;
>     float TimeOfDay = 8.0f; // 从早上 8:00 开始
> };
> ```
>
> **Spawner 集成关键点：**
>
> ```cpp
> // 在 Spawner 的 Tick 中根据密度动态调整实体数
> void ACrowdSpawner::Tick(float DeltaTime)
> {
>     Super::Tick(DeltaTime);
>
>     const float TargetDensity =
>         DensityManager.CalculateTargetDensity();
>     const int32 TargetCount =
>         FMath::CeilToInt(TargetDensity * SpawnAreaSize);
>     const int32 CurrentCount =
>         EntityManager->GetNumEntities();
>
>     if (CurrentCount < TargetCount)
>     {
>         // 生成差额实体到 ZoneGraph 入口
>         for (int32 i = 0;
>              i < TargetCount - CurrentCount && i < MaxSpawnPerFrame;
>              ++i)
>         {
>             SpawnAtRandomZoneGraphEntry();
>         }
>     }
>     else if (CurrentCount > TargetCount)
>     {
>         // 销毁超出实体（优先选择离玩家最远的 Low LOD 实体）
>         TrimEntities(CurrentCount - TargetCount);
>     }
> }
> ```
>
> **防卡顿策略：**
> - `MaxSpawnPerFrame` 限制每帧最大生成数（如 20 个），避免帧率尖刺
> - 销毁优先选择 Low LOD 实体——它们在远距离，销毁瞬间不可见
> - `FInterpConstantTo` 而非 `FMath::Lerp`——确保过渡速度恒定，不受帧率影响

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **City Sample 项目**: Epic Games Launcher → 学习 → City Sample。这是学习 Mass 框架的最佳实践项目，包含完整的行人、车辆和交通系统
- **GDC 2023**: "Massive Scale AI and Crowds in UE5" — Epic 技术演讲
- **UE 源码必读文件列表**:
  - `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassEntityManager.h`
  - `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassProcessor.h`
  - `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassExecutionContext.h`
  - `Engine/Plugins/Runtime/MassGameplay/Source/MassSpawner/Public/MassSpawner.h`
  - `Engine/Plugins/Runtime/ZoneGraph/Source/ZoneGraph/Public/ZoneGraphSubsystem.h`
- **性能优化**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassProcessingPhaseManager.h` — 理解 Phase 调度和并行化

---

## 常见陷阱

1. **ZoneGraph 数据未生成** — 在编辑器中绘制 ZoneShape 后，必须显式点击 "Generate ZoneGraph" 才会生成导航数据。忘记这步会导致所有实体呆立原地。

2. **Processor 执行顺序错误** — LOD Processor 必须在 Behavior Processor 之前执行，否则 Behavior Processor 可能处理的是上一帧的 LOD 级别。使用 `ExecutionOrder.ExecuteBefore/After` 显式声明依赖。

3. **ISM 实例未创建** — Mass Representation 使用 Instanced Static Mesh (ISM) 合批渲染。如果 `FMassRepresentationFragment` 未配置或 ISM Actor 不存在，实体虽在运行但不可见。

4. **Trait 重复添加同一 Fragment** — 如果两个 Trait 都添加了 `FTransformFragment`，Mass 会检测并跳过重复。但如果有任何自定义逻辑依赖"Fragment 只被添加一次"，可能产生意外行为。

5. **O(N²) 行为 Processor 在大规模下的爆炸** — `UCrowdBehaviorProcessor` 使用全局 O(N²) 邻居搜索。对于 10,000+ 实体，必须改用空间哈希网格或 ZoneGraph 按车道分组来降低复杂度。City Sample 中通过 `FMassZoneGraphLaneLocationFragment` 按车道限制邻居搜索范围，将复杂度降至近似 O(N)。
