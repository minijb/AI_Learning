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
