---
title: "Mass Processors 详解"
updated: 2026-06-05
---

# Mass Processors 详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 3h
> 前置知识: Mass Entity 与 Fragment、ECS System 概念

---

## 1. 概念讲解

### 为什么需要这个？

Processor 是 Mass 的逻辑执行单元——等同于 ECS 中的 System。但与纯数据导向的 ECS 不同的是，Mass 的 Processor 深度集成了 UE 的游戏循环（World Tick）、线程调度和依赖管理。不理解 Processor 的执行模型就写不出正确的 Mass 逻辑，更无法处理并行执行中的数据竞争。

### 核心思想

#### 1.1 Processor 的定位

```
游戏帧
├── PrePhysics Phase
│   ├── ProcessorGroup A  [可并行]
│   │   ├── Processor 1
│   │   └── Processor 2
│   ├── ProcessorGroup B  [可并行]
│   │   └── Processor 3
│   └── ...
├── DuringPhysics Phase
│   └── ...
├── PostPhysics Phase
│   └── ...
└── 下一帧
```

每个 Processor 属于一个 Phase 和一个 Group，决定其**何时执行**和**与谁并行**。

#### 1.2 执行模型关键概念

| 概念 | 说明 |
|------|------|
| **ExecutionOrder** | `ExecuteInGroup`（哪个组）、`ExecuteBefore`/`ExecuteAfter`（组内排序） |
| **ExecutionFlags** | 控制 Processor 在客户端/服务端/编辑器等环境下的运行 |
| **EntityQuery** | 声明 Processor 需要哪些 Fragment，哪些是只读、哪些可写 |
| **Execute** | 每帧调用的核心方法，接收匹配的实体数据 |
| **Signal** | 事件驱动机制，替代轮询检查 |
| **FMassCommandBuffer** | 延迟修改实体（增删 Fragment、销毁实体），在 Execute 结束后统一提交 |

#### 1.3 查询构建——FMassEntityQuery

```cpp
// 声明所需 Fragment
query.AddRequirement<T>(EMassFragmentAccess::ReadOnly);  // 只读访问
query.AddRequirement<T>(EMassFragmentAccess::ReadWrite); // 读写访问

// 声明 Tag 要求
query.AddTagRequirement<T>(EMassFragmentPresence::All);  // 必须有
query.AddTagRequirement<T>(EMassFragmentPresence::Any);  // 至少一个
query.AddTagRequirement<T>(EMassFragmentPresence::None); // 必须没有

// 声明 SharedFragment 要求
query.AddSharedRequirement<T>(EMassFragmentAccess::ReadOnly);

// 可选 Fragment（实体可有可无）
query.AddRequirement<T>(EMassFragmentAccess::ReadOnly,
                        EMassFragmentPresence::Optional);
```

**关键约束：** 两个 Processor 如果都需要 `ReadWrite` 访问同一 Fragment，它们**不能**在同一 Group 内并行。系统通过查询声明自动检测冲突。

#### 1.4 并行与线程安全

- 同一 **Phase** 的不同 **Group** 可跨线程并行。
- 同一 **Group** 内，无 Fragment 冲突的 Processor 可并行。
- ReadOnly Fragment 允许多个 Processor 同时读取。
- ReadWrite Fragment 在并发模型中充当"写锁"。

#### 1.5 Signal Processor——事件驱动

传统 Processor 每帧轮询所有实体检查条件（如 "Health == 0"）。Signal Processor 改为**当事件发生时**才触发处理。

```cpp
// 发送信号
Context.Defer().AddFragment<FMassDeathSignal>(EntityIndex);

// Signal Processor 仅在实体拥有该信号时执行
// 执行后可自动移除信号 Fragment
```

---

## 2. 代码示例

### 2.1 基础 Processor：群体移动

```cpp
// CrowdMovementProcessor.h
#pragma once

#include "MassProcessor.h"
#include "MassEntityTypes.h"
#include "CrowdMovementProcessor.generated.h"

USTRUCT()
struct FCrowdTransformFragment : public FMassFragment
{
    GENERATED_BODY()
    FVector Location = FVector::ZeroVector;
    FRotator Rotation = FRotator::ZeroRotator;
};

USTRUCT()
struct FCrowdVelocityFragment : public FMassFragment
{
    GENERATED_BODY()
    FVector Velocity = FVector::ZeroVector;
    float MaxSpeed = 200.0f;
};

USTRUCT()
struct FCrowdSteeringFragment : public FMassFragment
{
    GENERATED_BODY()
    FVector SteeringForce = FVector::ZeroVector;
    float SteeringWeight = 1.0f;
};

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
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassCommandBuffer.h"

UCrowdMovementProcessor::UCrowdMovementProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::Movement;
    ExecutionOrder.ExecuteAfter.Add(TEXT("MassBeginMovementProcessor"));
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UCrowdMovementProcessor::ConfigureQueries()
{
    MovementQuery.AddRequirement<FCrowdTransformFragment>(
        EMassFragmentAccess::ReadWrite);
    MovementQuery.AddRequirement<FCrowdVelocityFragment>(
        EMassFragmentAccess::ReadWrite);
    MovementQuery.AddRequirement<FCrowdSteeringFragment>(
        EMassFragmentAccess::ReadWrite);
    MovementQuery.RegisterWithProcessor(*this);
}

void UCrowdMovementProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    MovementQuery.ForEachEntityChunk(EntityManager, Context,
        [this](FMassExecutionContext& Context)
        {
            const int32 NumEntities = Context.GetNumEntities();
            const float DeltaTime = Context.GetDeltaTimeSeconds();

            TArrayView<FCrowdTransformFragment> Transforms =
                Context.GetMutableFragmentView<FCrowdTransformFragment>();
            TArrayView<FCrowdVelocityFragment> Velocities =
                Context.GetMutableFragmentView<FCrowdVelocityFragment>();
            const TArrayView<FCrowdSteeringFragment> Steerings =
                Context.GetMutableFragmentView<FCrowdSteeringFragment>();

            for (int32 i = 0; i < NumEntities; ++i)
            {
                // 应用 Steering 力到速度
                FVector& Vel = Velocities[i].Velocity;
                const float MaxSpeed = Velocities[i].MaxSpeed;

                Vel += Steerings[i].SteeringForce *
                       Steerings[i].SteeringWeight * DeltaTime;

                // 限制最大速度
                const float Speed = Vel.Size();
                if (Speed > MaxSpeed)
                {
                    Vel = Vel.GetSafeNormal() * MaxSpeed;
                }

                // 应用速度到位置
                Transforms[i].Location += Vel * DeltaTime;

                // 根据速度更新朝向
                if (Speed > 1.0f)
                {
                    Transforms[i].Rotation =
                        Vel.Rotation();
                }

                // 重置 Steering 力（下一帧重新计算）
                Steerings[i].SteeringForce = FVector::ZeroVector;
            }
        });
}
```

### 2.2 避障 Processor

```cpp
// AvoidanceProcessor.h
#pragma once

#include "MassProcessor.h"
#include "AvoidanceProcessor.generated.h"

UCLASS()
class UAvoidanceProcessor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UAvoidanceProcessor();

    UPROPERTY(EditAnywhere, Category = "Avoidance")
    float AvoidanceRadius = 200.0f;

    UPROPERTY(EditAnywhere, Category = "Avoidance")
    float AvoidanceStrength = 500.0f;

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;

private:
    FMassEntityQuery AvoidanceQuery;

    // 空间哈希——用于快速邻居查找
    struct FEntityEntry
    {
        FVector Location;
        FVector Velocity;
        FMassEntityHandle Handle;
    };
};
```

```cpp
// AvoidanceProcessor.cpp
#include "AvoidanceProcessor.h"
#include "CrowdMovementProcessor.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"

UAvoidanceProcessor::UAvoidanceProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    // 在 Movement 之前执行，为 Movement Processor 准备好 Steering 数据
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::Movement;
    ExecutionOrder.ExecuteBefore.Add(
        UCrowdMovementProcessor::StaticClass()->GetFName());
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UAvoidanceProcessor::ConfigureQueries()
{
    AvoidanceQuery.AddRequirement<FCrowdTransformFragment>(
        EMassFragmentAccess::ReadOnly);
    AvoidanceQuery.AddRequirement<FCrowdVelocityFragment>(
        EMassFragmentAccess::ReadOnly);
    AvoidanceQuery.AddRequirement<FCrowdSteeringFragment>(
        EMassFragmentAccess::ReadWrite);
    AvoidanceQuery.RegisterWithProcessor(*this);
}

void UAvoidanceProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    // 第一遍：收集所有实体的位置和速度
    TArray<FEntityEntry> EntityEntries;
    EntityEntries.Reserve(Context.GetNumEntities());

    AvoidanceQuery.ForEachEntityChunk(EntityManager, Context,
        [&EntityEntries](FMassExecutionContext& Context)
        {
            const TArrayView<FCrowdTransformFragment> Transforms =
                Context.GetFragmentView<FCrowdTransformFragment>();
            const TArrayView<FCrowdVelocityFragment> Velocities =
                Context.GetFragmentView<FCrowdVelocityFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                EntityEntries.Add({
                    Transforms[i].Location,
                    Velocities[i].Velocity,
                    Context.GetEntity(i)
                });
            }
        });

    // 第二遍：为每个实体计算避障力
    AvoidanceQuery.ForEachEntityChunk(EntityManager, Context,
        [this, &EntityEntries](FMassExecutionContext& Context)
        {
            const TArrayView<FCrowdTransformFragment> Transforms =
                Context.GetFragmentView<FCrowdTransformFragment>();
            const TArrayView<FCrowdVelocityFragment> Velocities =
                Context.GetFragmentView<FCrowdVelocityFragment>();
            TArrayView<FCrowdSteeringFragment> Steerings =
                Context.GetMutableFragmentView<FCrowdSteeringFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                FVector AvoidanceForce = FVector::ZeroVector;
                int32 NeighborCount = 0;

                const FVector& MyPos = Transforms[i].Location;
                const FVector& MyVel = Velocities[i].Velocity;

                for (const FEntityEntry& Other : EntityEntries)
                {
                    if (Other.Handle == Context.GetEntity(i))
                        continue;

                    const FVector ToOther = Other.Location - MyPos;
                    const float Distance = ToOther.Size();

                    if (Distance < AvoidanceRadius && Distance > 0.01f)
                    {
                        // 越近推离力越大（反比于距离的平方）
                        const float Strength =
                            AvoidanceStrength / (Distance * Distance);
                        AvoidanceForce -= ToOther.GetSafeNormal() * Strength;
                        ++NeighborCount;
                    }
                }

                if (NeighborCount > 0)
                {
                    AvoidanceForce /= (float)NeighborCount;
                    Steerings[i].SteeringForce += AvoidanceForce;
                }
            }
        });
}
```

### 2.3 Signal Processor——事件驱动处理

```cpp
// DeathSignalProcessor.h
#pragma once

#include "MassSignalProcessorBase.h"
#include "DeathSignalProcessor.generated.h"

// 死亡信号 Fragment——仅作为事件标记存在
USTRUCT()
struct FMassDeathSignal : public FMassTag
{
    GENERATED_BODY()
};

// Signal Processor 继承自 UMassSignalProcessorBase
UCLASS()
class UDeathSignalProcessor : public UMassSignalProcessorBase<FMassDeathSignal>
{
    GENERATED_BODY()

public:
    UDeathSignalProcessor();

protected:
    virtual void ConfigureQueries() override;
    virtual void SignalEntities(FMassEntityManager& EntityManager,
                                FMassExecutionContext& Context,
                                FMassSignalNameLookup& SignalLookup) override;
};
```

```cpp
// DeathSignalProcessor.cpp
#include "DeathSignalProcessor.h"
#include "CrowdMovementProcessor.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"
#include "MassCommandBuffer.h"

UDeathSignalProcessor::UDeathSignalProcessor()
{
    bAutoRegisterWithProcessingPhases = true;
    ExecutionOrder.ExecuteInGroup =
        UE::Mass::ProcessorGroupNames::Behavior;
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UDeathSignalProcessor::ConfigureQueries()
{
    // Signal Processor 自动查询带有 FMassDeathSignal 的实体
    // 基类已处理信号查询
    EntityQuery.AddRequirement<FCrowdTransformFragment>(
        EMassFragmentAccess::ReadWrite);
    EntityQuery.AddRequirement<FCrowdVelocityFragment>(
        EMassFragmentAccess::ReadWrite);
    EntityQuery.RegisterWithProcessor(*this);
}

void UDeathSignalProcessor::SignalEntities(
    FMassEntityManager& EntityManager,
    FMassExecutionContext& Context,
    FMassSignalNameLookup& SignalLookup)
{
    EntityQuery.ForEachEntityChunk(EntityManager, Context,
        [&Context](FMassExecutionContext& Context)
        {
            TArrayView<FCrowdTransformFragment> Transforms =
                Context.GetMutableFragmentView<FCrowdTransformFragment>();
            TArrayView<FCrowdVelocityFragment> Velocities =
                Context.GetMutableFragmentView<FCrowdVelocityFragment>();

            for (int32 i = 0; i < Context.GetNumEntities(); ++i)
            {
                // 播放死亡效果（位置降低到地面以下，速度归零）
                Transforms[i].Location.Z -= 100.0f;
                Velocities[i].Velocity = FVector::ZeroVector;

                // 3 秒后销毁实体
                Context.Defer().DestroyEntity(Context.GetEntity(i));
            }
        });

    // Signal Fragment 在本次处理后自动从所有实体移除
    // 无需手动 RemoveFragment
}
```

### 2.4 完整示例：将 Processor 注册到 UE 系统

```cpp
// MyMassModule.cpp
#include "Modules/ModuleManager.h"
#include "MassEntitySubsystem.h"
#include "MassProcessorDependencySolver.h"

class FMyMassModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        // Processor 通过 UCLASS 自动注册
        // 只需确保模块被加载——UE 反射系统负责实例化和注册
        UE_LOG(LogTemp, Log, TEXT("MyMassModule started"));
    }

    virtual void ShutdownModule() override {}
};

IMPLEMENT_MODULE(FMyMassModule, MyMassModule);

// 在 Build.cs 中声明对 MassEntity 的依赖
// PublicDependencyModuleNames.Add("MassEntity");
```

**处理器依赖关系可视化：**

```
Movement Group 执行顺序:
1. UAvoidanceProcessor    (读取 Transform, Velocity; 写入 Steering)
   ↓ (ExecuteAfter 自动保证)
2. UCrowdMovementProcessor (读取 Steering; 写入 Transform, Velocity)

Behavior Group 执行顺序:
3. UDeathSignalProcessor   (事件驱动，仅在实体有 DeathSignal 时执行)
```

---

## 3. 练习

### 练习 1: 基础练习 —— 创建自定义 Processor

创建 `UFlockingProcessor`，实现群体聚拢行为：遍历每个实体，计算其与所有其他实体的平均位置，生成指向群体中心的 Steering 力。在 `ConfigureQueries` 中正确声明 Fragment 依赖，在 `Execute` 中使用 `ForEachEntityChunk` 处理。设置正确的 `ExecutionOrder`。

### 练习 2: 进阶练习 —— Processor 并行

创建两个 Processor：`UHealthRegenerationProcessor`（每秒恢复实体 `Health += 5 * DeltaTime`）和 `UDamageProcessor`（检测实体碰撞并扣血）。两者都读写 `FMassCharacterStatsFragment::Health`。**观察问题**：将它们放在同一 Group 会导致数据竞争。解决方案：
- 方案 A：放入不同 Group
- 方案 B：使用 `ExecutionOrder.ExecuteBefore/After` 序列化
选一种实现并验证。

### 练习 3: 挑战练习 —— 自定义 Signal 链

设计一个战斗事件链：
1. `UAttackProcessor`：当检测到攻击命中时发送 `FMassHitSignal`
2. `UHitReactionProcessor`（Signal Processor）：监听 `FMassHitSignal`，修改动画状态 Fragment 为 "hit reaction"，添加 `FMassHitStunTag`，同时发送 `FMassDamageSignal`
3. `UDamageProcessor`（Signal Processor）：监听 `FMassDamageSignal`，扣减 Health，如果 Health ≤ 0 则发送 `FMassDeathSignal`

实现完整的事件链，验证每个 Signal Processor 的处理逻辑正确执行。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **UFlockingProcessor：群体聚拢（Cohesion）行为**：
>
> ```cpp
> // === UFlockingProcessor.h ===
> UCLASS()
> class UFlockingProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UFlockingProcessor();
>
>     UPROPERTY(EditAnywhere, Category = "Flocking")
>     float CohesionWeight = 100.0f;   // 聚拢力强度
>
>     UPROPERTY(EditAnywhere, Category = "Flocking")
>     float MaxSteeringForce = 200.0f; // 最大 Steering 力
>
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void Execute(FMassEntityManager& EntityManager,
>                          FMassExecutionContext& Context) override;
> private:
>     FMassEntityQuery FlockingQuery;
> };
>
> // === UFlockingProcessor.cpp ===
> UFlockingProcessor::UFlockingProcessor()
> {
>     bAutoRegisterWithProcessingPhases = true;
>     // 在 Movement 之前执行，为 MovementProcessor 准备 Steering 数据
>     ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Movement;
>     ExecutionOrder.ExecuteBefore.Add(
>         UCrowdMovementProcessor::StaticClass()->GetFName());
>     ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
> }
>
> void UFlockingProcessor::ConfigureQueries()
> {
>     FlockingQuery.AddRequirement<FCrowdTransformFragment>(
>         EMassFragmentAccess::ReadOnly);   // 读取位置（只读）
>     FlockingQuery.AddRequirement<FCrowdVelocityFragment>(
>         EMassFragmentAccess::ReadOnly);   // 读取速度（只读）
>     FlockingQuery.AddRequirement<FCrowdSteeringFragment>(
>         EMassFragmentAccess::ReadWrite);  // 写入 Steering
>     FlockingQuery.RegisterWithProcessor(*this);
> }
>
> void UFlockingProcessor::Execute(
>     FMassEntityManager& EntityManager, FMassExecutionContext& Context)
> {
>     // 第一遍：收集所有实体的位置，计算群体平均位置
>     FVector AveragePosition = FVector::ZeroVector;
>     int32 TotalCount = 0;
>
>     FlockingQuery.ForEachEntityChunk(EntityManager, Context,
>         [&](FMassExecutionContext& Context)
>         {
>             const TArrayView<FCrowdTransformFragment> Transforms =
>                 Context.GetFragmentView<FCrowdTransformFragment>();
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 AveragePosition += Transforms[i].Location;
>                 ++TotalCount;
>             }
>         });
>
>     if (TotalCount == 0) return;
>     AveragePosition /= TotalCount; // 群体中心
>
>     // 第二遍：为每个实体计算指向中心的 Steering 力
>     FlockingQuery.ForEachEntityChunk(EntityManager, Context,
>         [&](FMassExecutionContext& Context)
>         {
>             const TArrayView<FCrowdTransformFragment> Transforms =
>                 Context.GetFragmentView<FCrowdTransformFragment>();
>             TArrayView<FCrowdSteeringFragment> Steerings =
>                 Context.GetMutableFragmentView<FCrowdSteeringFragment>();
>
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 // 指向群体中心的方向
>                 FVector DesiredDirection =
>                     (AveragePosition - Transforms[i].Location).GetSafeNormal();
>
>                 // 计算 Steering 力：目标速度 - 当前速度
>                 FVector SteeringForce = DesiredDirection * CohesionWeight;
>
>                 // 限制最大 Steering 力
>                 if (SteeringForce.Size() > MaxSteeringForce)
>                 {
>                     SteeringForce = SteeringForce.GetSafeNormal() * MaxSteeringForce;
>                 }
>
>                 Steerings[i].SteeringForce += SteeringForce;
>             }
>         });
> }
> ```
> **关键点**：
> - 两次遍历：第一次计算群体中心（O(N)），第二次计算 Steering 力（O(N)）——总 O(N) 而非 O(N²)。
> - Steering 力是**累加**到已有 `SteeringForce` 字段上的（`+=`），而不是覆盖——这样多个行为 Processor（分离、对齐、聚拢）可以叠加。
> - `ConfigureQueries` 中 `FCrowdTransformFragment` 声明为 `ReadOnly`，允许与其他读取同一 Fragment 的 Processor 并行。

> [!tip]- 练习 2 参考答案
> **UHealthRegenerationProcessor + UDamageProcessor：并行冲突与解决方案**：
>
> ```cpp
> // === UHealthRegenerationProcessor: 每秒恢复生命 ===
> UCLASS()
> class UHealthRegenerationProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UHealthRegenerationProcessor();
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void Execute(FMassEntityManager& EntityManager,
>                          FMassExecutionContext& Context) override;
> private:
>     FMassEntityQuery RegenerationQuery;
> };
>
> // 方案 A：放入不同 Group 避免冲突
> UHealthRegenerationProcessor::UHealthRegenerationProcessor()
> {
>     bAutoRegisterWithProcessingPhases = true;
>     // 放入单独 Group：Behavior Group → 与其他 Movement Group Processor
>     // 读写不同 Fragment 组合时可以并行
>     ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Behavior;
>     ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
> }
>
> void UHealthRegenerationProcessor::ConfigureQueries()
> {
>     RegenerationQuery.AddRequirement<FMassCharacterStatsFragment>(
>         EMassFragmentAccess::ReadWrite);
>     // 排除死去的实体
>     RegenerationQuery.AddTagRequirement<FMassDeadTag>(
>         EMassFragmentPresence::None);
>     RegenerationQuery.RegisterWithProcessor(*this);
> }
>
> void UHealthRegenerationProcessor::Execute(
>     FMassEntityManager& EntityManager, FMassExecutionContext& Context)
> {
>     RegenerationQuery.ForEachEntityChunk(EntityManager, Context,
>         [](FMassExecutionContext& Context)
>         {
>             const float DeltaTime = Context.GetDeltaTimeSeconds();
>             TArrayView<FMassCharacterStatsFragment> Stats =
>                 Context.GetMutableFragmentView<FMassCharacterStatsFragment>();
>
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 Stats[i].Health = FMath::Min(
>                     Stats[i].Health + 5.0f * DeltaTime,
>                     Stats[i].MaxHealth);
>             }
>         });
> }
>
> // === UDamageProcessor: 碰撞检测并扣血 ===
> UCLASS()
> class UDamageProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UDamageProcessor();
>
>     UPROPERTY(EditAnywhere)
>     float DamageAmount = 10.0f;
>
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void Execute(FMassEntityManager& EntityManager,
>                          FMassExecutionContext& Context) override;
> private:
>     FMassEntityQuery DamageQuery;
> };
>
> UDamageProcessor::UDamageProcessor()
> {
>     bAutoRegisterWithProcessingPhases = true;
>     // 方案 A：放入 Behavior Group（可在 Behavior 阶段与其他 Group 并行）
>     ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Behavior;
>
>     // 方案 B：若两个都在同一 Group，用 ExecuteBefore/After 序列化：
>     // ExecutionOrder.ExecuteAfter.Add(
>     //     UHealthRegenerationProcessor::StaticClass()->GetFName());
>
>     ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
> }
>
> void UDamageProcessor::ConfigureQueries()
> {
>     DamageQuery.AddRequirement<FMassCharacterStatsFragment>(
>         EMassFragmentAccess::ReadWrite);
>     DamageQuery.AddTagRequirement<FMassDeadTag>(
>         EMassFragmentPresence::None);
>     DamageQuery.RegisterWithProcessor(*this);
> }
>
> void UDamageProcessor::Execute(
>     FMassEntityManager& EntityManager, FMassExecutionContext& Context)
> {
>     DamageQuery.ForEachEntityChunk(EntityManager, Context,
>         [this](FMassExecutionContext& Context)
>         {
>             TArrayView<FMassCharacterStatsFragment> Stats =
>                 Context.GetMutableFragmentView<FMassCharacterStatsFragment>();
>
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 // 简化：直接扣血（实际应做碰撞检测）
>                 Stats[i].Health -= DamageAmount * Context.GetDeltaTimeSeconds();
>
>                 if (Stats[i].Health <= 0.0f)
>                 {
>                     Context.Defer().AddTag<FMassDeadTag>(Context.GetEntity(i));
>                 }
>             }
>         });
> }
> ```
> **并行冲突解释**：如果两个 Processor 放在同一 Group 且都声明 `ReadWrite` 对 `FMassCharacterStatsFragment`，Mass 的 Dependency Solver 会检测到冲突并**序列化它们**（实际上可能报错或自动排序）。方案 A（不同 Group）允许它们在不同线程上并行运行（只要它们在不同的 Group 中且不共享 ReadWrite Fragment）。方案 B（ExecuteAfter）是显式告诉框架"先执行 A 再执行 B"。
> **推荐方案 A**：将不同职责的 Processor 放入不同 Group，最大化并行度。

> [!tip]- 练习 3 参考答案
> **自定义 Signal 链：FMassHitSignal → FMassDamageSignal → FMassDeathSignal**：
>
> ```cpp
> // === 定义 Signal Fragment ===
> USTRUCT()
> struct FMassHitSignal : public FMassSignal { GENERATED_BODY() };
> USTRUCT()
> struct FMassDamageSignal : public FMassSignal { GENERATED_BODY() };
> USTRUCT()
> struct FMassDeathSignal : public FMassSignal { GENERATED_BODY() };
>
> // 战斗相关 Fragment
> USTRUCT()
> struct FMassCombatStateFragment : public FMassFragment
> {
>     GENERATED_BODY()
>     UPROPERTY() float AttackCooldown = 0.0f;
>     UPROPERTY() float HitReactionTime = 0.0f;
> };
>
> // === UAttackProcessor: 检测攻击命中，发送 HitSignal ===
> UCLASS()
> class UAttackProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UAttackProcessor();
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void Execute(FMassEntityManager& EntityManager,
>                          FMassExecutionContext& Context) override;
> private:
>     FMassEntityQuery AttackQuery;
> };
>
> UAttackProcessor::UAttackProcessor()
> {
>     bAutoRegisterWithProcessingPhases = true;
>     ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Behavior;
>     ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
> }
>
> void UAttackProcessor::ConfigureQueries()
> {
>     AttackQuery.AddRequirement<FMassCharacterStatsFragment>(EMassFragmentAccess::ReadOnly);
>     AttackQuery.AddTagRequirement<FMassDeadTag>(EMassFragmentPresence::None);
>     AttackQuery.RegisterWithProcessor(*this);
> }
>
> void UAttackProcessor::Execute(
>     FMassEntityManager& EntityManager, FMassExecutionContext& Context)
> {
>     AttackQuery.ForEachEntityChunk(EntityManager, Context,
>         [](FMassExecutionContext& Context)
>         {
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 // 简化：假设所有实体都在攻击范围内
>                 // 实际应做距离检测来确定是否命中
>                 bool bHit = FMath::RandBool(); // 示例：50% 概率命中
>                 if (bHit)
>                 {
>                     // 发送 HitSignal——通过 Defer() 添加 Signal Fragment
>                     Context.Defer().AddSignal<FMassHitSignal>(Context.GetEntity(i));
>                 }
>             }
>         });
> }
>
> // === UHitReactionProcessor: Signal Processor，监听 FMassHitSignal ===
> UCLASS()
> class UHitReactionProcessor : public UMassSignalProcessorBase<FMassHitSignal>
> {
>     GENERATED_BODY()
> public:
>     UHitReactionProcessor();
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void SignalEntities(FMassEntityManager& EntityManager,
>         FMassExecutionContext& Context,
>         FMassSignalContext& SignalContext) override;
> private:
>     FMassEntityQuery HitReactionQuery;
> };
>
> UHitReactionProcessor::UHitReactionProcessor()
> {
>     bAutoRegisterWithProcessingPhases = true;
>     ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Behavior;
>     ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
> }
>
> void UHitReactionProcessor::ConfigureQueries()
> {
>     HitReactionQuery.AddRequirement<FMassAnimationFragment>(
>         EMassFragmentAccess::ReadWrite);
>     HitReactionQuery.AddRequirement<FMassCombatStateFragment>(
>         EMassFragmentAccess::ReadWrite);
>     HitReactionQuery.RegisterWithProcessor(*this);
> }
>
> void UHitReactionProcessor::SignalEntities(FMassEntityManager& EntityManager,
>     FMassExecutionContext& Context,
>     FMassSignalContext& SignalContext)
> {
>     HitReactionQuery.ForEachEntityChunk(EntityManager, Context,
>         [](FMassExecutionContext& Context)
>         {
>             TArrayView<FMassAnimationFragment> Animations =
>                 Context.GetMutableFragmentView<FMassAnimationFragment>();
>             TArrayView<FMassCombatStateFragment> CombatStates =
>                 Context.GetMutableFragmentView<FMassCombatStateFragment>();
>
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 // 设置受击动画状态
>                 Animations[i].AnimationState = 5; // Hit Reaction
>                 CombatStates[i].HitReactionTime = 0.3f;
>
>                 // 添加眩晕 Tag
>                 Context.Defer().AddTag<FMassStunnedTag>(Context.GetEntity(i));
>
>                 // 发送 DamageSignal 到下一个 Processor
>                 Context.Defer().AddSignal<FMassDamageSignal>(Context.GetEntity(i));
>             }
>         });
> }
>
> // === UDamageProcessor (Signal): 监听 FMassDamageSignal，扣血 ===
> UCLASS()
> class UDamageResponseProcessor : public UMassSignalProcessorBase<FMassDamageSignal>
> {
>     GENERATED_BODY()
> public:
>     UDamageResponseProcessor();
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void SignalEntities(FMassEntityManager& EntityManager,
>         FMassExecutionContext& Context,
>         FMassSignalContext& SignalContext) override;
> private:
>     FMassEntityQuery DamageQuery;
> };
>
> void UDamageResponseProcessor::SignalEntities(FMassEntityManager& EntityManager,
>     FMassExecutionContext& Context,
>     FMassSignalContext& SignalContext)
> {
>     DamageQuery.ForEachEntityChunk(EntityManager, Context,
>         [](FMassExecutionContext& Context)
>         {
>             TArrayView<FMassCharacterStatsFragment> Stats =
>                 Context.GetMutableFragmentView<FMassCharacterStatsFragment>();
>
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 Stats[i].Health -= 20.0f; // 固定伤害
>
>                 if (Stats[i].Health <= 0.0f)
>                 {
>                     // 发送 DeathSignal
>                     Context.Defer().AddSignal<FMassDeathSignal>(Context.GetEntity(i));
>                 }
>             }
>         });
> }
> ```
> **事件链流程**：
> ```
> AttackProcessor               → 命中检测 → 发送 FMassHitSignal
> HitReactionProcessor (Signal) → 受击反应 → 设置动画、添加眩晕 → 发送 FMassDamageSignal
> DamageResponseProcessor (Signal) → 扣血    → 判断死亡 → 发送 FMassDeathSignal
> DeathProcessor (Signal)       → 死亡处理 → 添加 DeadTag、清理
> ```
> **关键点**：
> - Signal Fragment 在被处理**之后**由框架自动移除，不需要手动清理。
> - Signal 链中下一步的 Signal 必须通过 `Defer().AddSignal()` 添加——不能在当前 Execute 中即时触发。
> - Signal Processor 仅在实体**拥有**对应 Signal Fragment 时才会被调度，避免了轮询检查。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassProcessor.h` — `UMassProcessor` 完整 API
- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassExecutionContext.h` — 理解 `FMassExecutionContext` 和 `FMassCommandBuffer` 的延迟操作模型
- **MassGameplay**: `Plugins/Runtime/MassGameplay/Source/MassGameplay/Public/MassGameplayExternalTraits.h` — 查看 Processor 如何与外部 Actor 交互
- **Dependency Solver**: `MassEntity/Private/MassProcessorDependencySolver.cpp` — 理解 Mass 如何自动解析 Processor 之间的依赖和冲突

---

## 常见陷阱

1. **错误理解 Defer 操作** — `Context.Defer().DestroyEntity(Handle)` 不会立即销毁实体，而是等到当前 Processor 执行完毕后统一处理。在同一个 Execute 内，先标记销毁再读取 Fragment 不会报错但读到的是旧数据。

2. **双重遍历性能问题** — 避障 Processor 中每帧遍历所有实体两遍（O(N²)）。对于 1000+ 实体应使用空间哈希网格或 `FMassEntityQuery` 的子查询进行空间局部查找。City Sample 使用 `FMassZoneGraphLaneLocationFragment` 按车道组织实体避免全局 O(N²)。

3. **Signal 残留** — Signal Fragment 在 Processor 执行后被基类自动移除。如果在 Signal Processor 的 Execute 中手动加入新的 Signal Fragment（形成 Signal 链），只能通过 `Defer()` 添加，因为当前 Processor 的 Entity 列表已快照。

4. **ExecutionOrder 冲突** — 两个 Processor 互相声明 `ExecuteBefore` 会导致依赖死循环。Mass 的 Dependency Solver 会检测并报告错误。

5. **World Tick 阶段选择** — `ExecutionOrder.ExecuteInGroup` 必须与实际需要的游戏逻辑阶段匹配。例如依赖物理碰撞的 Processor 应放在 `DuringPhysics` 阶段而不是 `PrePhysics`。
