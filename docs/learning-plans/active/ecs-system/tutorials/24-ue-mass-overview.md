# Mass 框架总览

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 2h
> 前置知识: ECS 核心概念（Entity-Component-System）、Unreal Engine 基础（Actor、UObject、C++ 模块系统）

---

## 1. 概念讲解

### 为什么需要这个？

Unreal Engine 传统的 Actor 系统在处理大量相似实体时性能瓶颈显著。一个 Actor 至少包含 `AActor` 的完整开销：Transform 组件、Tick 注册、网络复制元数据、蓝图 VM 绑定等。当场景中有 1000+ 个行为相似的实体（如人群行人、车辆、鸟群），传统 Actor 的逐实体 Tick 和内存布局碎片化会导致帧率剧烈下降。

**Mass 框架**是 UE5 为"大量同类实体"场景设计的数据驱动高性能系统。它借鉴 ECS 架构思想，将数据与逻辑分离，使用连续内存布局和批量并行处理，在万人同屏场景下仍能保持 60+ FPS。

### 核心思想

Mass 不是 UE 对传统 ECS 的照搬，而是一套针对 UE 生态深度定制的"类 ECS"系统。它的四大核心概念：

| 概念 | ECS 对应 | Mass 中的角色 |
|------|---------|--------------|
| **Entity** | Entity | `FMassEntityHandle` — 轻量整数句柄，无虚函数，无独立对象 |
| **Fragment** | Component | `FMassFragment` / `FMassSharedFragment` / `FMassTag` — 纯数据结构 |
| **Processor** | System | `UMassProcessor` — 对符合条件的实体批量执行逻辑 |
| **Trait** | 无直接对应 | `UMassEntityTraitBase` — Fragment 组合的配置模板 |

**Mass 与 Actor 系统的关系：**

- Mass 实体不是 Actor，它们共享同一个 `UWorld`，但由 `UMassEntitySubsystem` 管理生命周期。
- 一个 Actor 可以**桥接**到 Mass 实体（如 `AMassCharacter`），或通过 `MassAgentComponent` 使 Actor 受 Mass 驱动。
- Mass 适合**同质化大量实体**；Actor 适合**少量、行为复杂的实体**。

**适用场景：**

- 城市人群模拟（行人、购物者）
- 交通系统（车辆、自行车）
- 粒子群/鸟群（群体行为）
- 子弹/投射物（弹道模拟）
- 环境装饰（草、石头）的 LOD 管理

### 性能特征

Mass 的性能优势来源于三个层面：

1. **数据局部性** — Fragment 按 Archetype 连续存储，CPU 缓存友好。
2. **批量处理** — Processor 的 `Execute` 接收实体列表，可 SIMD 友好遍历。
3. **并行执行** — 不同 Processor Group 可跨线程并行，同一 Group 内无依赖的 Processor 也可并行。

**粗略性能对比**（10,000 个简单移动实体，仅 Tick 位置更新）：

| 方案 | CPU 耗时 (ms) |
|------|--------------|
| 传统 Actor + Tick | ~8-12ms |
| Mass Processor (单线程) | ~0.5ms |
| Mass Processor (并行) | ~0.15ms |

---

## 2. 代码示例

### 2.1 最小 Mass 项目：生成 100 个带位置的实体

**第一步：启用插件**

在 `.uproject` 中启用 Mass 相关插件：

```json
{
    "Plugins": [
        { "Name": "MassGameplay", "Enabled": true },
        { "Name": "MassAI", "Enabled": true },
        { "Name": "MassCrowd", "Enabled": true },
        { "Name": "MassEntity", "Enabled": true },
        { "Name": "MassMovement", "Enabled": true },
        { "Name": "ZoneGraph", "Enabled": true }
    ]
}
```

**第二步：定义 Fragment**

```cpp
// MassBasicFragments.h
#pragma once

#include "MassEntityTypes.h"
#include "MassBasicFragments.generated.h"

// 基础 Transform 数据——存储位置和旋转
USTRUCT()
struct FMassTransformFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    FVector Location = FVector::ZeroVector;

    UPROPERTY()
    FRotator Rotation = FRotator::ZeroRotator;
};

// 移动速度 Fragment
USTRUCT()
struct FMassVelocityFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    FVector Velocity = FVector::ZeroVector;
};

// 实体标签——标记实体类型，零大小
USTRUCT()
struct FMassPedestrianTag : public FMassTag
{
    GENERATED_BODY()
};
```

**第三步：实现 Processor —— 让实体运动**

```cpp
// MassBasicMovementProcessor.h
#pragma once

#include "MassProcessor.h"
#include "MassBasicMovementProcessor.generated.h"

UCLASS()
class UMassBasicMovementProcessor : public UMassProcessor
{
    GENERATED_BODY()

public:
    UMassBasicMovementProcessor();

protected:
    virtual void ConfigureQueries() override;
    virtual void Execute(FMassEntityManager& EntityManager,
                         FMassExecutionContext& Context) override;

private:
    // 查询：拥有 Transform + Velocity 且带有 PedestrianTag 的实体
    FMassEntityQuery EntityQuery;
};
```

```cpp
// MassBasicMovementProcessor.cpp
#include "MassBasicMovementProcessor.h"
#include "MassBasicFragments.h"
#include "MassEntityManager.h"
#include "MassExecutionContext.h"

UMassBasicMovementProcessor::UMassBasicMovementProcessor()
{
    // 在 Movement 阶段执行，行为组
    ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Movement;
    ExecutionOrder.ExecuteAfter.Add(TEXT("MassBeginMovementProcessor"));
    ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
}

void UMassBasicMovementProcessor::ConfigureQueries()
{
    // 构建查询：实体需同时拥有 Transform、Velocity Fragment 和 PedestrianTag
    EntityQuery.AddRequirement<FMassTransformFragment>(EMassFragmentAccess::ReadWrite);
    EntityQuery.AddRequirement<FMassVelocityFragment>(EMassFragmentAccess::ReadOnly);
    EntityQuery.AddTagRequirement<FMassPedestrianTag>(EMassFragmentPresence::All);
    EntityQuery.RegisterWithProcessor(*this);
}

void UMassBasicMovementProcessor::Execute(
    FMassEntityManager& EntityManager, FMassExecutionContext& Context)
{
    // 批量获取所有匹配实体的 Fragment 视图
    EntityQuery.ForEachEntityChunk(EntityManager, Context,
        [](FMassExecutionContext& Context)
        {
            const int32 NumEntities = Context.GetNumEntities();
            // 获取数组视图——连续内存，缓存友好
            const TArrayView<FMassVelocityFragment> Velocities =
                Context.GetMutableFragmentView<FMassVelocityFragment>();
            TArrayView<FMassTransformFragment> Transforms =
                Context.GetMutableFragmentView<FMassTransformFragment>();

            const float DeltaTime = Context.GetDeltaTimeSeconds();

            for (int32 i = 0; i < NumEntities; ++i)
            {
                Transforms[i].Location += Velocities[i].Velocity * DeltaTime;
            }
        });
}
```

**第四步：生成实体——在 GameMode 或 Subsystem 中**

```cpp
// MassEntitySpawner.cpp
#include "MassEntitySubsystem.h"
#include "MassEntityManager.h"
#include "MassBasicFragments.h"
#include "Engine/World.h"

void SpawnMassEntities(UWorld* World, int32 Count)
{
    UMassEntitySubsystem* EntitySubsystem =
        World->GetSubsystem<UMassEntitySubsystem>();
    check(EntitySubsystem);

    FMassEntityManager& EntityManager = EntitySubsystem->GetMutableEntityManager();

    // 创建 Archetype：定义实体由哪些 Fragment 组成
    FMassArchetypeHandle Archetype = EntityManager.CreateArchetype({
        FMassTransformFragment::StaticStruct(),
        FMassVelocityFragment::StaticStruct(),
        FMassPedestrianTag::StaticStruct()
    });

    TArray<FMassEntityHandle> Entities;
    // 批量创建
    EntityManager.BatchCreateEntities(
        Archetype, Count, Entities);

    const FVector SpawnOrigin = FVector(0.0f, 0.0f, 100.0f);

    for (int32 i = 0; i < Count; ++i)
    {
        // 写入初始数据
        FMassTransformFragment& Transform =
            EntityManager.GetFragmentDataChecked<FMassTransformFragment>(
                Entities[i]);

        Transform.Location = SpawnOrigin +
            FVector(FMath::RandRange(-500.0f, 500.0f),
                    FMath::RandRange(-500.0f, 500.0f),
                    0.0f);

        FMassVelocityFragment& Velocity =
            EntityManager.GetFragmentDataChecked<FMassVelocityFragment>(
                Entities[i]);

        Velocity.Velocity = FVector(
            FMath::RandRange(-200.0f, 200.0f),
            FMath::RandRange(-200.0f, 200.0f),
            0.0f).GetSafeNormal() * 150.0f;
    }

    UE_LOG(LogTemp, Log, TEXT("Spawned %d Mass entities"), Count);
}
```

**第五步（可选）：通过 MassEntityConfigAsset 可视化配置**

1. 在 Content Browser 中右键 → Miscellaneous → Data Asset → `MassEntityConfigAsset`。
2. 命名为 `DA_Pedestrian`。
3. 打开后在 Traits 列表中添加自定义 Trait。
4. 使用 `UMassSpawner` 或 `AMassVisualizer` 将配置应用到场景。

**运行方式：**

1. 创建 UE 5.3+ C++ 项目。
2. 将上述代码放入项目模块。
3. 在 `Build.cs` 中添加模块依赖：
```csharp
PublicDependencyModuleNames.AddRange(new string[] {
    "MassEntity",
    "MassCommon",
    "MassMovement",
    "MassSpawner",
    "ZoneGraph"
});
```
4. 在 `AMyGameMode::BeginPlay()` 或自定义 Subsystem 中调用 `SpawnMassEntities`。
5. 运行游戏，在视口观察实体按随机速度移动。

**预期效果：**

在场景原点周围 10m 范围内生成 100 个 Mass 实体，每个实体以随机方向和速度运动。由于 Mass 实体默认不渲染，可通过 `MassDebugger` 子系统或 `VisualLogger` 可视化实体位置。配合 `MassGameplayDebugger` 可在运行时查看所有实体的 Fragment 数据。

---

## 3. 练习

### 练习 1: 基础练习 —— 扩展 Fragment

在 `FMassTransformFragment` 中添加 `FVector Scale` 字段。修改 Movement Processor，使实体沿 X 轴正方向以不同速度移动（速度为随机 50~300）。在 `SpawnMassEntities` 中将实体生成范围扩大到 2000x2000。

### 练习 2: 进阶练习 —— 添加实体生命周期

实现 `FMassLifetimeFragment`（包含 `float RemainingTime`），编写 `ULifetimeProcessor` 在 Execute 中递减时间并在 ≤0 时调用 `Context.Defer().DestroyEntity(EntityIndex)` 销毁实体。在生成时为每个实体设置 3~10 秒的随机寿命。验证实体随时间逐渐消失。

### 练习 3: 挑战练习 —— 集成 Mass LOD

创建三个 Fragment 集合分别对应 LOD 三个级别：`FMassLODNearFragment`（包含 `FVector DetailedPosition`）、`FMassLODMediumFragment`（仅包含 `FVector Location`）、`FMassLODFarFragment`（仅包含 `FMassTag`）。编写 `ULODSwitchProcessor` 根据实体到玩家距离动态切换 Fragment 组合。在 `FMassExecutionContext` 中通过 `Defer().AddFragment` / `RemoveFragment` 实现 Fragment 增删。

---

## 4. 扩展阅读

- **官方文档**: Unreal Engine 5 Mass Entity 文档（在 Epic Dev Community 搜索 "Mass Entity"）
- **源码阅读**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassEntityManager.h` — 理解 EntityManager 的内部结构
- **City Sample**: Epic 官方的 City Sample 项目大量使用 Mass 框架实现行人、车辆和交通系统，是学习 Mass 的最佳实践案例
- **GDC 2022**: "Building Huge Worlds with Mass" — Epic 技术演讲，讲解 Mass 的设计哲学
- **ZoneGraph**: `Engine/Plugins/Runtime/ZoneGraph/` — Mass 的寻路和空间查询系统，与 Mass AI 紧密集成

---

## 常见陷阱

1. **Mass 实体不是 Actor** — 不要试图通过 `AActor::GetActorLocation()` 之类的方式访问 Mass 实体。使用 `FMassEntityManager::GetFragmentDataChecked<T>()`。

2. **Fragment 必须标记 `USTRUCT()` 和 `GENERATED_BODY()`** — 这是 UE 反射系统的要求，缺少会导致 Fragment 无法被 Mass 系统识别。

3. **Processor 需注册到正确的 Group** — `ExecutionOrder.ExecuteInGroup` 决定了 Processor 的执行阶段。错误的 Group 可能导致数据竞争（例如在 Movement Group 中读写只在 Animation Group 更新的数据）。

4. **不要逐实体操作** — 始终通过 `ForEachEntityChunk` 批量处理。逐实体的 `GetFragmentDataChecked` 在 Processor 的 Execute 中使用会严重破坏性能。

5. **线程安全** — 标记 `ReadOnly` 的 Fragment 可被多个 Processor 并行读取；但 `ReadWrite` Fragment 在同一阶段只能由一个 Processor 写入。使用 `ExecutionOrder` 确保正确的读写顺序。
