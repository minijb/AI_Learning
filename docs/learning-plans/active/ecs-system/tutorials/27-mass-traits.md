---
title: "Mass Traits 与实体模板"
updated: 2026-06-05
---

# Mass Traits 与实体模板

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 2.5h
> 前置知识: Mass Entity 与 Fragment、Mass Processors

---

## 1. 概念讲解

### 为什么需要这个？

当实体类型增多时，手动为每种实体组合 Fragment 并初始化数据变得难以维护。五个不同的 NPC 类型可能需要 20 种不同的 Fragment 组合——纯代码方式会演变成混乱的工厂函数。**Trait** 是 Mass 提供的"实体配方"系统——将 Fragment 的组合和初始化逻辑封装为可复用的、可在编辑器中可视化配置的模块。

### 核心思想

#### 1.1 Trait 的定位

```
MassEntityConfigAsset (DataAsset)
├── Trait A: "行人基础"  → 添加 Transform + Velocity Fragments
├── Trait B: "人群行为"  → 添加 Steering + Animation Fragments
├── Trait C: "LOD 管理"  → 添加 LOD 相关 Fragment 和 Tag
└── Trait D: "ZoneGraph 导航" → 添加路径跟随 Fragment

                        ↓ 编译为

FMassEntityTemplate  ← 运行时使用的"蓝图"（不可变）
    → 生成实体时按此模板分配 Fragment
```

**与 Processors 的协作流程：**

```
Trait (构建时)                 Processor (运行时)
   ↓                               ↑
定义实体有哪些 Fragment    ←→   查询有哪些 Fragment
   ↓                               ↑
初始化 Fragment 默认值     ←→   修改 Fragment 数据
```

#### 1.2 FMassEntityTemplate

`FMassEntityTemplate` 是编译后的不可变模板，记录了：

- Fragment 列表（每种 Fragment 的 `UScriptStruct`）
- 初始值（Builder 中设置的默认 Fragment 数据）
- SharedFragment 初始值
- 模板 ID（用于查找）

**重要：** 一旦 `Build()` 之后模板不可修改。修改 Trait 配置后需要重新构建模板。

#### 1.3 MassEntityConfigAsset 的可视化配置

在 Content Browser 中创建 `MassEntityConfigAsset` Data Asset 后，UE 编辑器会显示 Trait 列表。Trait 的 `UPROPERTY` 字段直接暴露在 Details 面板中，策划/设计师无需写代码即可调整实体行为参数。

#### 1.4 ZoneGraph 与 Mass 集成概览

ZoneGraph 是 UE5 为 Mass AI 提供的轻量级寻路系统：

- **ZoneGraphData**：编辑器生成的导航数据（替代传统 NavMesh）
- **ZoneGraph Lane**：预计算的车道/步道路径
- **FMassZoneGraphLaneLocationFragment**：实体的当前车道位置
- **FMassZoneGraphPathFragment**：实体的路径请求

Mass Trait 系统通过 `UMassZoneGraphNavigationTrait` 将 ZoneGraph 相关 Fragment 注入实体。

---

## 2. 代码示例

### 2.1 自定义 Trait——行人基础配置

```cpp
// MassPedestrianTrait.h
#pragma once

#include "MassEntityTraitBase.h"
#include "MassPedestrianTrait.generated.h"

USTRUCT()
struct FMassPedestrianMovementFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float WalkSpeed = 150.0f;

    UPROPERTY()
    float RunSpeed = 400.0f;

    UPROPERTY()
    float RotationSpeed = 360.0f;

    UPROPERTY()
    bool bIsRunning = false;
};

USTRUCT()
struct FMassPedestrianAppearanceFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float Height = 175.0f;

    UPROPERTY()
    float BodyTypeIndex = 0.0f; // 0-1: skinny→heavy

    UPROPERTY()
    FLinearColor ShirtColor = FLinearColor::White;

    UPROPERTY()
    FLinearColor PantsColor = FLinearColor::Blue;

    UPROPERTY()
    int32 HeadMeshIndex = 0;
};

USTRUCT()
struct FMassPedestrianTag : public FMassTag
{
    GENERATED_BODY()
};

UCLASS(meta = (DisplayName = "Pedestrian Trait"))
class UMassPedestrianTrait : public UMassEntityTraitBase
{
    GENERATED_BODY()

public:
    // 可在编辑器中调整的参数
    UPROPERTY(EditAnywhere, Category = "Movement")
    float DefaultWalkSpeed = 150.0f;

    UPROPERTY(EditAnywhere, Category = "Movement")
    float DefaultRunSpeed = 400.0f;

    UPROPERTY(EditAnywhere, Category = "Appearance")
    FLinearColor DefaultShirtColor = FLinearColor::White;

    UPROPERTY(EditAnywhere, Category = "Appearance")
    FLinearColor DefaultPantsColor = FLinearColor(0.1f, 0.2f, 0.5f);

    UPROPERTY(EditAnywhere, Category = "Appearance")
    float MinHeight = 160.0f;

    UPROPERTY(EditAnywhere, Category = "Appearance")
    float MaxHeight = 190.0f;

protected:
    // 核心方法：构建模板时调用，定义实体包含哪些 Fragment
    virtual void BuildTemplate(
        FMassEntityTemplateBuildContext& BuildContext,
        const UWorld& World) const override;
};
```

```cpp
// MassPedestrianTrait.cpp
#include "MassPedestrianTrait.h"
#include "MassEntityTemplateRegistry.h"
#include "MassCommonFragments.h"

void UMassPedestrianTrait::BuildTemplate(
    FMassEntityTemplateBuildContext& BuildContext,
    const UWorld& World) const
{
    // 1. 声明实体需要的 Fragment
    BuildContext.AddFragment<FTransformFragment>();              // 基础 Transform
    BuildContext.AddFragment<FMassPedestrianMovementFragment>(); // 自定义移动
    BuildContext.AddFragment<FMassPedestrianAppearanceFragment>();// 外观
    BuildContext.AddTag<FMassPedestrianTag>();                   // 标签标记

    // 2. 设置 Fragment 初始值
    BuildContext.GetFragmentMutable<FMassPedestrianMovementFragment>()
        .WalkSpeed = DefaultWalkSpeed;
    BuildContext.GetFragmentMutable<FMassPedestrianMovementFragment>()
        .RunSpeed = DefaultRunSpeed;
    BuildContext.GetFragmentMutable<FMassPedestrianMovementFragment>()
        .RotationSpeed = 360.0f;

    // 外观使用随机值——在运行时由 Spawner 随机
    BuildContext.GetFragmentMutable<FMassPedestrianAppearanceFragment>()
        .ShirtColor = DefaultShirtColor;
    BuildContext.GetFragmentMutable<FMassPedestrianAppearanceFragment>()
        .PantsColor = DefaultPantsColor;

    // 高度在 Spawner 中随机（Builder 只能设默认值）
    BuildContext.GetFragmentMutable<FMassPedestrianAppearanceFragment>()
        .Height = (MinHeight + MaxHeight) * 0.5f;
}
```

### 2.2 车辆 Trait——包含 SharedFragment

```cpp
// MassVehicleTrait.h
#pragma once

#include "MassEntityTraitBase.h"
#include "MassVehicleTrait.generated.h"

USTRUCT()
struct FMassVehicleMovementFragment : public FMassFragment
{
    GENERATED_BODY()

    UPROPERTY()
    float CurrentSpeed = 0.0f;

    UPROPERTY()
    float TargetSpeed = 0.0f;

    UPROPERTY()
    float Acceleration = 300.0f;

    UPROPERTY()
    float MaxSpeed = 800.0f;

    UPROPERTY()
    float SteeringAngle = 0.0f;

    UPROPERTY()
    float WheelBase = 280.0f; // 轴距 cm
};

// 共享配置——所有同类车辆共享
USTRUCT()
struct FMassVehicleSharedFragment : public FMassSharedFragment
{
    GENERATED_BODY()

    UPROPERTY()
    TSoftObjectPtr<UStaticMesh> VehicleMesh;

    UPROPERTY()
    float VehicleLength = 450.0f; // cm

    UPROPERTY()
    float VehicleWidth = 180.0f;  // cm

    UPROPERTY()
    float Mass_Kg = 1500.0f;

    UPROPERTY()
    int32 MaxPassengers = 4;

    UPROPERTY()
    FLinearColor PaintColor = FLinearColor::Red;
};

USTRUCT()
struct FMassVehicleTag : public FMassTag
{
    GENERATED_BODY()
};

UENUM()
enum class EVehicleType : uint8
{
    Sedan,
    SUV,
    Truck,
    Bus,
    Motorcycle
};

UCLASS(meta = (DisplayName = "Vehicle Trait"))
class UMassVehicleTrait : public UMassEntityTraitBase
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, Category = "Vehicle")
    EVehicleType VehicleType = EVehicleType::Sedan;

    UPROPERTY(EditAnywhere, Category = "Vehicle")
    TSoftObjectPtr<UStaticMesh> DefaultMesh;

    UPROPERTY(EditAnywhere, Category = "Vehicle")
    float DefaultMaxSpeed = 600.0f;

    UPROPERTY(EditAnywhere, Category = "Vehicle")
    FLinearColor DefaultPaintColor = FLinearColor::White;

protected:
    virtual void BuildTemplate(
        FMassEntityTemplateBuildContext& BuildContext,
        const UWorld& World) const override;
};
```

```cpp
// MassVehicleTrait.cpp
#include "MassVehicleTrait.h"
#include "MassEntityTemplateRegistry.h"
#include "MassCommonFragments.h"

void UMassVehicleTrait::BuildTemplate(
    FMassEntityTemplateBuildContext& BuildContext,
    const UWorld& World) const
{
    // 个体 Fragment
    BuildContext.AddFragment<FTransformFragment>();
    BuildContext.AddFragment<FMassVehicleMovementFragment>();
    BuildContext.AddTag<FMassVehicleTag>();

    // 根据车辆类型设置参数
    FMassVehicleMovementFragment& MoveFrag =
        BuildContext.GetFragmentMutable<FMassVehicleMovementFragment>();
    MoveFrag.MaxSpeed = DefaultMaxSpeed;

    switch (VehicleType)
    {
    case EVehicleType::Bus:
        MoveFrag.Acceleration = 150.0f;
        MoveFrag.WheelBase = 600.0f;
        break;
    case EVehicleType::Truck:
        MoveFrag.Acceleration = 200.0f;
        MoveFrag.WheelBase = 500.0f;
        break;
    case EVehicleType::Motorcycle:
        MoveFrag.Acceleration = 500.0f;
        MoveFrag.WheelBase = 140.0f;
        break;
    default:
        MoveFrag.Acceleration = 300.0f;
        MoveFrag.WheelBase = 280.0f;
        break;
    }

    // 共享 Fragment（所有此类型车辆共享的配置）
    FMassVehicleSharedFragment& SharedFrag =
        BuildContext.AddSharedFragment<FMassVehicleSharedFragment>();
    SharedFrag.VehicleMesh = DefaultMesh;
    SharedFrag.PaintColor = DefaultPaintColor;

    switch (VehicleType)
    {
    case EVehicleType::SUV:
        SharedFrag.VehicleLength = 480.0f;
        SharedFrag.VehicleWidth = 195.0f;
        SharedFrag.Mass_Kg = 2000.0f;
        break;
    case EVehicleType::Bus:
        SharedFrag.VehicleLength = 1200.0f;
        SharedFrag.VehicleWidth = 255.0f;
        SharedFrag.Mass_Kg = 12000.0f;
        SharedFrag.MaxPassengers = 50;
        break;
    case EVehicleType::Truck:
        SharedFrag.VehicleLength = 800.0f;
        SharedFrag.VehicleWidth = 250.0f;
        SharedFrag.Mass_Kg = 8000.0f;
        break;
    case EVehicleType::Motorcycle:
        SharedFrag.VehicleLength = 220.0f;
        SharedFrag.VehicleWidth = 80.0f;
        SharedFrag.Mass_Kg = 200.0f;
        SharedFrag.MaxPassengers = 1;
        break;
    default: // Sedan
        SharedFrag.VehicleLength = 450.0f;
        SharedFrag.VehicleWidth = 180.0f;
        SharedFrag.Mass_Kg = 1500.0f;
        break;
    }
}
```

### 2.3 复合 Trait——组合多个子 Trait

```cpp
// MassCitizenTrait.h
#pragma once

#include "MassEntityTraitBase.h"
#include "MassCitizenTrait.generated.h"

// 将行人移动 + 人群行为 + LOD 管理组合为一个"市民"Trait
UCLASS(meta = (DisplayName = "Citizen Composite Trait"))
class UMassCitizenTrait : public UMassEntityTraitBase
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, Category = "Movement")
    float WalkSpeed = 150.0f;

    UPROPERTY(EditAnywhere, Category = "Crowd")
    float SeparationWeight = 1.0f;

    UPROPERTY(EditAnywhere, Category = "Crowd")
    float AlignmentWeight = 0.5f;

    UPROPERTY(EditAnywhere, Category = "LOD")
    float LODSignificanceThreshold = 5000.0f;

protected:
    virtual void BuildTemplate(
        FMassEntityTemplateBuildContext& BuildContext,
        const UWorld& World) const override;
};
```

```cpp
// MassCitizenTrait.cpp
#include "MassCitizenTrait.h"
#include "MassPedestrianTrait.h"
#include "MassEntityTemplateRegistry.h"

void UMassCitizenTrait::BuildTemplate(
    FMassEntityTemplateBuildContext& BuildContext,
    const UWorld& World) const
{
    // 组合方式：直接在 BuildContext 中添加多个 Trait 的 Fragment
    // 方式 1：手动添加
    BuildContext.AddFragment<FTransformFragment>();
    BuildContext.AddFragment<FMassPedestrianMovementFragment>();
    BuildContext.AddFragment<FMassPedestrianAppearanceFragment>();
    BuildContext.AddTag<FMassPedestrianTag>();

    // 设置默认值
    auto& MoveFrag = BuildContext.GetFragmentMutable<
        FMassPedestrianMovementFragment>();
    MoveFrag.WalkSpeed = WalkSpeed;

    // 方式 2：委托给子 Trait（更模块化）
    // 假设我们有一个独立的 LOD Trait
    BuildContext.AddFragment<FMassEntityLODFragment>();
    BuildContext.AddFragment<FMassEntityLODSignificanceFragment>();
}
```

### 2.4 Spawner 使用 Trait 生成实体

```cpp
// MassCrowdSpawner.cpp
#include "MassEntitySubsystem.h"
#include "MassSpawner.h"
#include "MassPedestrianTrait.h"
#include "MassEntityTemplateRegistry.h"

void SpawnCrowdFromTrait(
    UWorld* World,
    TSubclassOf<UMassEntityTraitBase> TraitClass,
    int32 Count,
    const FVector& Origin)
{
    UMassEntitySubsystem* Subsystem =
        World->GetSubsystem<UMassEntitySubsystem>();
    FMassEntityManager& EM = Subsystem->GetMutableEntityManager();

    // 1. 从 Trait 构建模板
    FMassEntityTemplateBuildContext BuildContext;
    const UMassEntityTraitBase* TraitCDO =
        TraitClass->GetDefaultObject<UMassEntityTraitBase>();
    TraitCDO->BuildTemplate(BuildContext, *World);

    // 注册模板（或获取已注册的模板）
    FMassEntityTemplateID TemplateID = BuildContext.GetTemplateID();

    // 2. 批量生成实体
    TArray<FMassEntityHandle> Entities;
    FMassEntityTemplate* Template =
        EM.FindOrCreateEntityTemplate(TemplateID, BuildContext);
    Template->CreateEntities(Count, Entities);

    // 3. 随机初始化每个实体的变体数据
    for (int32 i = 0; i < Count; ++i)
    {
        FMassEntityHandle& Handle = Entities[i];

        // 随机位置（在原点周围散布）
        if (FTransformFragment* Transform =
            EM.GetFragmentDataPtr<FTransformFragment>(Handle))
        {
            Transform->SetTranslation(Origin + FVector(
                FMath::RandRange(-1000.0f, 1000.0f),
                FMath::RandRange(-1000.0f, 1000.0f),
                0.0f));
        }

        // 随机外观
        if (FMassPedestrianAppearanceFragment* Appearance =
            EM.GetFragmentDataPtr<FMassPedestrianAppearanceFragment>(Handle))
        {
            Appearance->ShirtColor = FLinearColor::MakeRandomColor();
            Appearance->PantsColor = FLinearColor::MakeRandomColor();
            Appearance->Height =
                FMath::RandRange(155.0f, 195.0f);
            Appearance->HeadMeshIndex = FMath::RandRange(0, 5);
        }
    }

    UE_LOG(LogTemp, Log,
        TEXT("Spawned %d entities from Trait %s"),
        Count, *TraitClass->GetName());
}
```

### 2.5 蓝图配置流程

```
1. Content Browser → 右键 → Miscellaneous → Data Asset → MassEntityConfigAsset
2. 命名为 "DA_CrowdPedestrian"
3. 双击打开 → 在 "Traits" 数组中添加:
   - Pedestrian Trait (自定义的 UMassPedestrianTrait)
   - ZoneGraph Navigation Trait (UE 内置)
   - Crowd Member Trait (UE 内置 MassCrowd)
   - LOD Collector Trait (UE 内置)
4. 展开每个 Trait，在 Details 面板中调整参数
5. 保存
6. 将 "DA_CrowdPedestrian" 赋值给场景中的 MassSpawner Actor
7. 运行时 MassSpawner 读取配置并生成实体
```

---

## 3. 练习

### 练习 1: 基础练习 —— 自定义 NPC Trait

创建 `UMassNPCTrait`，包含：
- `FMassNPCStatsFragment`（`Health`、`Mana`、`Level`）
- `FMassNPCDialogueFragment`（`TArray<FString> DialogueLines`、`bool bCanTalk`）
- `FMassNPCVendorTag`（标记为商人）

在 BuildTemplate 中正确添加所有 Fragment 和 Tag，设置默认值。

### 练习 2: 进阶练习 —— 创建 MassEntityConfigAsset 并生成实体

1. 在编辑器中创建三个不同的 `MassEntityConfigAsset`：
   - `DA_Warrior`（高生命、近战配置）
   - `DA_Archer`（低生命、远程配置）
   - `DA_Healer`（中生命、治疗配置）
2. 为每个创建对应的 Trait（参考 2.1 的模式）
3. 在 C++ 中编写 `USquadSpawner`，读取三个 Config 各生成 10 个实体，排列为三角阵型。

### 练习 3: 挑战练习 —— ZoneGraph Trait 集成

创建 `UMassZoneGraphPatrolTrait`：
- 添加 `FMassZoneGraphLaneLocationFragment`（当前车道位置）
- 添加 `FMassZoneGraphPathFragment`（巡逻路径）
- 添加 `FMassZoneGraphShortPathFragment`（避障短路径）
- 编写 `UPatrolPathProcessor`：读取 ZoneGraph 提供的路径点，驱动实体沿车道巡逻移动
- 在 ZoneGraph 编辑器中绘制闭合巡逻路线，验证实体沿路线循环移动

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **UMassNPCTrait：包含 Stats、Dialogue、VendorTag 的完整 NPC 模板**：
>
> ```cpp
> // === MassNPCTrait.h ===
> #pragma once
> #include "MassEntityTraitBase.h"
> #include "MassNPCTrait.generated.h"
>
> // NPC 属性 Fragment
> USTRUCT()
> struct FMassNPCStatsFragment : public FMassFragment
> {
>     GENERATED_BODY()
>
>     UPROPERTY()
>     float Health = 100.0f;
>
>     UPROPERTY()
>     float MaxHealth = 100.0f;
>
>     UPROPERTY()
>     float Mana = 50.0f;
>
>     UPROPERTY()
>     float MaxMana = 50.0f;
>
>     UPROPERTY()
>     int32 Level = 1;
> };
>
> // 对话 Fragment——每位 NPC 独有（内容可能不同）
> USTRUCT()
> struct FMassNPCDialogueFragment : public FMassFragment
> {
>     GENERATED_BODY()
>
>     UPROPERTY()
>     TArray<FString> DialogueLines;
>
>     UPROPERTY()
>     bool bCanTalk = true;
> };
>
> // 商人标记——零数据 Tag
> USTRUCT()
> struct FMassNPCVendorTag : public FMassTag
> {
>     GENERATED_BODY()
> };
>
> // 通用 NPC 标记
> USTRUCT()
> struct FMassNPCTag : public FMassTag
> {
>     GENERATED_BODY()
> };
>
> // === UMassNPCTrait ===
> UCLASS(meta = (DisplayName = "NPC Trait"))
> class UMassNPCTrait : public UMassEntityTraitBase
> {
>     GENERATED_BODY()
>
> public:
>     // 编辑器可调参数
>     UPROPERTY(EditAnywhere, Category = "Stats")
>     float DefaultHealth = 100.0f;
>
>     UPROPERTY(EditAnywhere, Category = "Stats")
>     float DefaultMana = 50.0f;
>
>     UPROPERTY(EditAnywhere, Category = "Stats")
>     int32 DefaultLevel = 1;
>
>     UPROPERTY(EditAnywhere, Category = "Dialogue")
>     TArray<FString> DefaultDialogueLines;
>
>     UPROPERTY(EditAnywhere, Category = "Role")
>     bool bIsVendor = false;  // 是否为商人
>
> protected:
>     virtual void BuildTemplate(
>         FMassEntityTemplateBuildContext& BuildContext,
>         const UWorld& World) const override;
> };
>
> // === MassNPCTrait.cpp ===
> #include "MassNPCTrait.h"
> #include "MassEntityTemplateRegistry.h"
> #include "MassCommonFragments.h"
>
> void UMassNPCTrait::BuildTemplate(
>     FMassEntityTemplateBuildContext& BuildContext,
>     const UWorld& World) const
> {
>     // 1. 声明实体需要的 Fragment
>     BuildContext.AddFragment<FTransformFragment>();           // 基础 Transform
>     BuildContext.AddFragment<FMassNPCStatsFragment>();        // 属性
>     BuildContext.AddFragment<FMassNPCDialogueFragment>();     // 对话数据
>     BuildContext.AddTag<FMassNPCTag>();                       // NPC 通用标记
>
>     // 2. 设置属性默认值
>     BuildContext.GetFragmentMutable<FMassNPCStatsFragment>()
>         .Health = DefaultHealth;
>     BuildContext.GetFragmentMutable<FMassNPCStatsFragment>()
>         .MaxHealth = DefaultHealth;
>     BuildContext.GetFragmentMutable<FMassNPCStatsFragment>()
>         .Mana = DefaultMana;
>     BuildContext.GetFragmentMutable<FMassNPCStatsFragment>()
>         .MaxMana = DefaultMana;
>     BuildContext.GetFragmentMutable<FMassNPCStatsFragment>()
>         .Level = DefaultLevel;
>
>     // 3. 设置对话默认值
>     FMassNPCDialogueFragment& Dialogue =
>         BuildContext.GetFragmentMutable<FMassNPCDialogueFragment>();
>     Dialogue.DialogueLines = DefaultDialogueLines;
>     Dialogue.bCanTalk = true;
>
>     // 4. 条件性添加商人 Tag
>     if (bIsVendor)
>     {
>         BuildContext.AddTag<FMassNPCVendorTag>();
>     }
> }
> ```
> **关键点**：
> - `bIsVendor` 控制在模板构建时是否添加 `FMassNPCVendorTag`——非商人 NPC 不会携带此 Tag，Processor 可通过查询是否包含该 Tag 来区分处理逻辑。
> - `FMassNPCDialogueFragment` 包含 `TArray<FString>`——UE 反射系统支持 TArray 序列化，但注意此类动态数组不适合高频遍历场景（应作为初始化数据在生成时设置一次）。
> - `BuildContext.AddTag` 添加的标记在运行时通过位掩码快速过滤，零运行时开销。

> [!tip]- 练习 2 参考答案
> **三个 MassEntityConfigAsset + USquadSpawner 三角阵型生成**：
>
> ```cpp
> // === 首先创建三个 Trait 类 ===
>
> // 1. UWarriorTrait
> UCLASS(meta = (DisplayName = "Warrior Trait"))
> class UWarriorTrait : public UMassEntityTraitBase
> {
>     GENERATED_BODY()
> public:
>     UPROPERTY(EditAnywhere) float Health = 150.0f;
>     UPROPERTY(EditAnywhere) float AttackPower = 25.0f;
>     UPROPERTY(EditAnywhere) float Speed = 180.0f;
>
> protected:
>     virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext,
>         const UWorld& World) const override
>     {
>         BuildContext.AddFragment<FTransformFragment>();
>         BuildContext.AddFragment<FMassCharacterStatsFragment>();
>         BuildContext.AddTag<FMassWarriorTag>();
>
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .Health = Health;
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .MaxHealth = Health;
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .AttackPower = AttackPower;
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .Speed = Speed;
>     }
> };
>
> // 2. UArcherTrait（低生命、高攻击范围）
> UCLASS(meta = (DisplayName = "Archer Trait"))
> class UArcherTrait : public UMassEntityTraitBase
> {
>     GENERATED_BODY()
> public:
>     UPROPERTY(EditAnywhere) float Health = 80.0f;
>     UPROPERTY(EditAnywhere) float AttackPower = 35.0f;
>     UPROPERTY(EditAnywhere) float AttackRange = 800.0f;
>
> protected:
>     virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext,
>         const UWorld& World) const override
>     {
>         BuildContext.AddFragment<FTransformFragment>();
>         BuildContext.AddFragment<FMassCharacterStatsFragment>();
>         BuildContext.AddTag<FMassArcherTag>();
>
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .Health = Health;
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .MaxHealth = Health;
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .AttackPower = AttackPower;
>     }
> };
>
> // 3. UHealerTrait（中等生命、治疗能力）
> UCLASS(meta = (DisplayName = "Healer Trait"))
> class UHealerTrait : public UMassEntityTraitBase
> {
>     GENERATED_BODY()
> public:
>     UPROPERTY(EditAnywhere) float Health = 100.0f;
>     UPROPERTY(EditAnywhere) float HealAmount = 15.0f;
>     UPROPERTY(EditAnywhere) float HealRadius = 500.0f;
>
> protected:
>     virtual void BuildTemplate(FMassEntityTemplateBuildContext& BuildContext,
>         const UWorld& World) const override
>     {
>         BuildContext.AddFragment<FTransformFragment>();
>         BuildContext.AddFragment<FMassCharacterStatsFragment>();
>         BuildContext.AddTag<FMassHealerTag>();
>
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .Health = Health;
>         BuildContext.GetFragmentMutable<FMassCharacterStatsFragment>()
>             .MaxHealth = Health;
>     }
> };
>
> // === 编辑器配置流程 ===
> // 1. 编译上述 Trait C++ 代码
> // 2. 在 Content Browser → Miscellaneous → Data Asset → MassEntityConfigAsset
> // 3. 创建 DA_Warrior, DA_Archer, DA_Healer 三个资产
> // 4. 分别添加对应的 Trait 到每个 ConfigAsset 的 Traits 列表
> // 5. 在 Details 面板调整参数
>
> // === USquadSpawner: C++ 侧读取 Config 生成实体 ===
> UCLASS()
> class USquadSpawner : public UObject
> {
>     GENERATED_BODY()
> public:
>     UPROPERTY(EditAnywhere)
>     UMassEntityConfigAsset* WarriorConfig;
>
>     UPROPERTY(EditAnywhere)
>     UMassEntityConfigAsset* ArcherConfig;
>
>     UPROPERTY(EditAnywhere)
>     UMassEntityConfigAsset* HealerConfig;
>
>     UPROPERTY(EditAnywhere)
>     int32 SquadSize = 10;
>
>     // 三角阵型的三个顶点偏移（相对中心）
>     UPROPERTY(EditAnywhere)
>     FVector WarriorOffset = FVector(0.0f, 200.0f, 0.0f);   // 前排中央
>
>     UPROPERTY(EditAnywhere)
>     FVector ArcherOffset = FVector(-300.0f, -150.0f, 0.0f); // 后排左
>
>     UPROPERTY(EditAnywhere)
>     FVector HealerOffset = FVector(300.0f, -150.0f, 0.0f);  // 后排右
>
>     void SpawnSquad(FMassEntityManager& EntityManager, FVector CenterLocation)
>     {
>         check(WarriorConfig && ArcherConfig && HealerConfig);
>
>         // 获取或构建模板
>         const FMassEntityTemplate* WarriorTemplate =
>             WarriorConfig->GetOrCreateEntityTemplate(*World);
>         const FMassEntityTemplate* ArcherTemplate =
>             ArcherConfig->GetOrCreateEntityTemplate(*World);
>         const FMassEntityTemplate* HealerTemplate =
>             HealerConfig->GetOrCreateEntityTemplate(*World);
>
>         // 批量生成 Warriors（前排）
>         TArray<FMassEntityHandle> Warriors;
>         EntityManager.BatchCreateEntities(
>             WarriorTemplate->GetArchetype(), SquadSize, Warriors);
>         PlaceEntitiesInFormation(EntityManager, Warriors,
>             CenterLocation + WarriorOffset, FVector(100.0f, 0.0f, 0.0f));
>
>         // 批量生成 Archers（后排左）
>         TArray<FMassEntityHandle> Archers;
>         EntityManager.BatchCreateEntities(
>             ArcherTemplate->GetArchetype(), SquadSize, Archers);
>         PlaceEntitiesInFormation(EntityManager, Archers,
>             CenterLocation + ArcherOffset, FVector(50.0f, -120.0f, 0.0f));
>
>         // 批量生成 Healers（后排右）
>         TArray<FMassEntityHandle> Healers;
>         EntityManager.BatchCreateEntities(
>             HealerTemplate->GetArchetype(), SquadSize, Healers);
>         PlaceEntitiesInFormation(EntityManager, Healers,
>             CenterLocation + HealerOffset, FVector(-50.0f, -120.0f, 0.0f));
>
>         UE_LOG(LogTemp, Log,
>             TEXT("Squad spawned: %d Warriors + %d Archers + %d Healers"),
>             Warriors.Num(), Archers.Num(), Healers.Num());
>     }
>
> private:
>     // 将实体按行排列（三角阵型内部微调）
>     void PlaceEntitiesInFormation(FMassEntityManager& EntityManager,
>         const TArray<FMassEntityHandle>& Entities,
>         FVector Center, FVector PerEntityOffset)
>     {
>         for (int32 i = 0; i < Entities.Num(); ++i)
>         {
>             FVector Loc = Center + PerEntityOffset * i;
>             FMassTransformFragment& Transform =
>                 EntityManager.GetFragmentDataChecked<FMassTransformFragment>(Entities[i]);
>             Transform.Location = Loc;
>         }
>     }
> };
> ```
> **关键点**：
> - `MassEntityConfigAsset` 是 Data Asset——它封装了 Trait 组合，通过 `GetOrCreateEntityTemplate()` 获得运行时模板。
> - 三角阵型通过三个 Offset 定义顶点，每个顶点的实体在各自方向上微偏移排列。
> - 使用 `BatchCreateEntities(Archetype, Count, OutArray)` 批量创建，一次调用生成所有同类型实体。

> [!tip]- 练习 3 参考答案
> **UMassZoneGraphPatrolTrait + UPatrolPathProcessor**：
>
> ```cpp
> // === UMassZoneGraphPatrolTrait.h ===
> #pragma once
> #include "MassEntityTraitBase.h"
> #include "MassZoneGraphPatrolTrait.generated.h"
>
> // 巡逻配置 Fragment
> USTRUCT()
> struct FMassPatrolConfigFragment : public FMassFragment
> {
>     GENERATED_BODY()
>
>     UPROPERTY()
>     float PatrolSpeed = 250.0f;
>
>     UPROPERTY()
>     float WaitTimeAtWaypoint = 1.0f;  // 在路径点停留时间
>
>     UPROPERTY()
>     float CurrentWaitTime = 0.0f;
>
>     UPROPERTY()
>     bool bIsWaiting = false;
> };
>
> UCLASS(meta = (DisplayName = "ZoneGraph Patrol Trait"))
> class UMassZoneGraphPatrolTrait : public UMassEntityTraitBase
> {
>     GENERATED_BODY()
>
> public:
>     UPROPERTY(EditAnywhere, Category = "Patrol")
>     float DefaultPatrolSpeed = 250.0f;
>
>     UPROPERTY(EditAnywhere, Category = "Patrol")
>     float WaitTime = 1.0f;
>
>     // ZoneGraph 车道过滤
>     UPROPERTY(EditAnywhere, Category = "ZoneGraph")
>     FZoneGraphTagFilter LaneFilter;
>
> protected:
>     virtual void BuildTemplate(
>         FMassEntityTemplateBuildContext& BuildContext,
>         const UWorld& World) const override;
> };
>
> // === UMassZoneGraphPatrolTrait.cpp ===
> #include "MassZoneGraphPatrolTrait.h"
> #include "MassEntityTemplateRegistry.h"
> #include "ZoneGraphSubsystem.h"
>
> void UMassZoneGraphPatrolTrait::BuildTemplate(
>     FMassEntityTemplateBuildContext& BuildContext,
>     const UWorld& World) const
> {
>     // 添加 ZoneGraph 相关 Fragment（由 Mass AI 模块提供）
>     BuildContext.AddFragment<FMassZoneGraphLaneLocationFragment>();
>     BuildContext.AddFragment<FMassZoneGraphPathFragment>();
>     BuildContext.AddFragment<FMassZoneGraphShortPathFragment>();
>
>     // 添加巡逻自定义数据
>     BuildContext.AddFragment<FMassPatrolConfigFragment>();
>     BuildContext.AddFragment<FTransformFragment>();
>
>     // 设置默认值
>     BuildContext.GetFragmentMutable<FMassPatrolConfigFragment>()
>         .PatrolSpeed = DefaultPatrolSpeed;
>     BuildContext.GetFragmentMutable<FMassPatrolConfigFragment>()
>         .WaitTimeAtWaypoint = WaitTime;
>
>     // 添加 Tag 标记为巡逻实体
>     BuildContext.AddTag<FMassPedestrianTag>();
> }
>
> // === UPatrolPathProcessor ===
> UCLASS()
> class UPatrolPathProcessor : public UMassProcessor
> {
>     GENERATED_BODY()
> public:
>     UPatrolPathProcessor();
>
> protected:
>     virtual void ConfigureQueries() override;
>     virtual void Execute(FMassEntityManager& EntityManager,
>                          FMassExecutionContext& Context) override;
> private:
>     FMassEntityQuery PatrolQuery;
> };
>
> UPatrolPathProcessor::UPatrolPathProcessor()
> {
>     bAutoRegisterWithProcessingPhases = true;
>     ExecutionOrder.ExecuteInGroup = UE::Mass::ProcessorGroupNames::Movement;
>     ExecutionFlags = (int32)(EProcessorExecutionFlags::All);
> }
>
> void UPatrolPathProcessor::ConfigureQueries()
> {
>     // 需要 ZoneGraph 位置、路径和巡逻配置
>     PatrolQuery.AddRequirement<FMassZoneGraphLaneLocationFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PatrolQuery.AddRequirement<FMassZoneGraphPathFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PatrolQuery.AddRequirement<FMassZoneGraphShortPathFragment>(
>         EMassFragmentAccess::ReadOnly);
>     PatrolQuery.AddRequirement<FMassPatrolConfigFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PatrolQuery.AddRequirement<FTransformFragment>(
>         EMassFragmentAccess::ReadWrite);
>     PatrolQuery.RegisterWithProcessor(*this);
> }
>
> void UPatrolPathProcessor::Execute(
>     FMassEntityManager& EntityManager, FMassExecutionContext& Context)
> {
>     const float DeltaTime = Context.GetDeltaTimeSeconds();
>
>     PatrolQuery.ForEachEntityChunk(EntityManager, Context,
>         [DeltaTime](FMassExecutionContext& Context)
>         {
>             TArrayView<FMassZoneGraphLaneLocationFragment> LaneLocations =
>                 Context.GetMutableFragmentView<FMassZoneGraphLaneLocationFragment>();
>             TArrayView<FMassZoneGraphPathFragment> Paths =
>                 Context.GetMutableFragmentView<FMassZoneGraphPathFragment>();
>             TArrayView<FMassPatrolConfigFragment> PatrolConfigs =
>                 Context.GetMutableFragmentView<FMassPatrolConfigFragment>();
>             TArrayView<FTransformFragment> Transforms =
>                 Context.GetMutableFragmentView<FTransformFragment>();
>
>             for (int32 i = 0; i < Context.GetNumEntities(); ++i)
>             {
>                 FMassPatrolConfigFragment& Config = PatrolConfigs[i];
>
>                 // 如果在等待阶段，倒计时
>                 if (Config.bIsWaiting)
>                 {
>                     Config.CurrentWaitTime -= DeltaTime;
>                     if (Config.CurrentWaitTime <= 0.0f)
>                     {
>                         Config.bIsWaiting = false;
>                         // 请求移动到下一个路径点
>                         // Paths[i].AdvanceToNextWaypoint();
>                     }
>                     continue; // 等待中不移动
>                 }
>
>                 // 沿车道移动：从 LaneLocation 获取当前位置沿车道方向
>                 // ZoneGraph 的 LaneLocation 包含 DistanceAlongLane 信息
>                 // 这里展示核心逻辑（实际依赖 ZoneGraph API）
>                 float DistanceAlongLane = LaneLocations[i].DistanceAlongLane;
>                 DistanceAlongLane += Config.PatrolSpeed * DeltaTime;
>
>                 // 如果到达车道终点或路径点，触发等待
>                 // if (DistanceAlongLane >= LaneLocations[i].LaneLength)
>                 // {
>                 //     Config.bIsWaiting = true;
>                 //     Config.CurrentWaitTime = Config.WaitTimeAtWaypoint;
>                 //     DistanceAlongLane = LaneLocations[i].LaneLength;
>                 // }
>
>                 // 更新车道位置
>                 LaneLocations[i].DistanceAlongLane = DistanceAlongLane;
>
>                 // ZoneGraph 系统会根据 LaneLocation 自动更新实体 Transform
>                 // （在 MassZoneGraphNavigationProcessor 中处理）
>             }
>         });
> }
> ```
> **关键点**：
> - ZoneGraph 集成依赖 `FMassZoneGraphLaneLocationFragment`（当前车道位置）、`FMassZoneGraphPathFragment`（路径规划）和 `FMassZoneGraphShortPathFragment`（动态避障短路径）三个 Fragment。
> - 巡逻逻辑由 `FMassPatrolConfigFragment` 携带配置（速度、等待时间），Processor 驱动实体沿车道移动。
> - 实际项目中 ZoneGraph 的数据（车道结构、路径点）由 `UZoneGraphSubsystem` 管理。Processor 通过 `DistanceAlongLane` 参数控制实体在车道上的位置，UE 的 `MassZoneGraphNavigationProcessor` 会将车道位置同步回 `FTransformFragment`。
> - 编辑器中用 ZoneGraph 编辑器绘制闭合路线，Trait 通过 `FZoneGraphTagFilter` 筛选特定类型的车道。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassEntityTraitBase.h` — Trait 基类 API
- **UE 源码**: `Engine/Plugins/Runtime/MassEntity/Source/MassEntity/Public/MassEntityTemplate.h` — 理解模板编译过程
- **MassGameplay**: `Plugins/Runtime/MassGameplay/Source/MassGameplay/Public/MassSpawner.h` — Spawner 如何读取 ConfigAsset 并批量生成实体
- **ZoneGraph 文档**: 搜索 "Unreal Engine ZoneGraph" 了解车道编辑器和导航数据生成
- **City Sample**: 查看 `DA_Crowd` / `DA_Traffic` 等 MassEntityConfigAsset 的实际配置

---

## 常见陷阱

1. **Trait 只影响模板构建** — BuildTemplate 在实体生成**之前**调用一次。运行时的随机化应在 Spawner 或专门的 `InitializationProcessor` 中完成。

2. **模板不可变** — 一旦 `Build()` 后，模板中的 Fragment 列表和默认值固定。修改 Trait 参数后需要重新构建（通常由编辑器自动处理）。

3. **SharedFragment 的生命周期** — BuildContext 中添加的 SharedFragment 实例由模板持有引用。销毁所有使用该模板的实体后，SharedFragment 自动释放。

4. **Trait 的 UPROPERTY 不是运行时变量** — 编辑器中可见的参数值在 BuildTemplate 时使用。运行时修改 Trait CDO 的 UPROPERTY 不会自动影响已生成的实体。

5. **父 Trait 与子 Trait 的继承** — 如果 Trait A 包含 Trait B 的 Fragment，而 Trait B 又被单独添加到 ConfigAsset 中，可能导致重复添加同一 Fragment。Mass 会检测并跳过重复。
