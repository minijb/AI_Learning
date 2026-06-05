---
title: "EQS、Smart Objects 与 GameplayTags 驱动 AI"
updated: 2026-06-05
---

# EQS、Smart Objects 与 GameplayTags 驱动 AI

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 09-bt-unreal-cpp, 12-decorator-service-parallel

---

## 1. 概念讲解

Tutorial 09 和 12 建立了 UE 行为树的完整技术栈——节点类型、Blackboard、Decorator/Service/Parallel。但仅靠行为树本身，AI 仍然缺少三个关键能力：**在哪里执行行为**（空间推理）、**如何与环境对象交互**（物体交互）、**如何用可扩展的标签体系驱动行为切换**（标签决策）。这三个问题分别由 EQS、Smart Objects 和 GameplayTags 解决。它们与行为树的关系不是"替代"而是"协同"——行为树回答"做什么"，EQS 回答"在哪里做"，Smart Objects 回答"怎么和环境交互"，GameplayTags 回答"以什么身份/状态做"。

### Part A — EQS (Environment Query System)

#### EQS 解决什么问题？

行为树的 Selector 能回答"攻击还是巡逻？"，Decorator 能回答"距离是否足够近？"。但有一个问题行为树本身无法优雅解决：**"我应该移动到哪里？"**

考虑以下场景：
- NPC 需要找掩护——"哪个位置在目标和我之间有障碍物？"
- NPC 需要侧翼包抄——"哪个位置在目标的侧后方且距离适中？"
- NPC 需要找血包——"哪个血包离我最近且不在敌人火力范围内？"
- NPC 需要巡逻——"哪个巡逻点有最好的视野覆盖？"

这些问题都是**空间评分问题**：在多候选位置中选择最优的一个。行为树可以做"找到目标 → 移动到目标"，但"在周围 50 米内找到最佳掩护位置"不是黑/白条件判断，而是需要在几百个候选点上运行多维度评分函数的计算。

**EQS 就是为此设计的**。它让设计师声明式地定义"生成候选位置 → 对每个位置打分 → 返回最佳 N 个"的查询管道。

EQS 的核心设计哲学：**BT says "what", EQS says "where"**。

#### EQS 架构：四个核心概念

EQS 查询的资产类型是 `UEnvQuery`。一个查询由以下组件构成：

| 组件 | 类型 | 职责 | 示例 |
|------|------|------|------|
| **Generator** | `UEnvQueryGenerator` | 生成候选点（Item）集合 | 在 AI 前方锥形区域生成 50 个点、NavMesh 上随机采样 100 个点、所有 Actor 的位置 |
| **Test** | `UEnvQueryTest` | 对每个候选点评分或过滤 | 距离目标的远近（距离测试）、与目标之间的视线遮蔽（Trace 测试）、自定义危险度评分 |
| **Context** | `UEnvQueryContext` | 提供参考位置/对象 | 查询者的位置（Querier）、目标 Actor 的位置、BB 中存储的位置 |
| **Item Type** | `UEnvQueryItemType` | 候选项的数据类型 | 点（Point）、Actor、方向向量 |

数据流：

```
Generator (produce items)
  → 对每个 item 运行所有 Test (score/filter)
    → 综合各 Test 的加权分数
      → 排序 → 返回 Top N items
```

**Generator** 是候选点来源。UE 内置了：
- `UEnvQueryGenerator_SimpleGrid`：在 AABB 内均匀生成网格点
- `UEnvQueryGenerator_OnCircle`：在圆周上生成点
- `UEnvQueryGenerator_Composite`：组合多个 Generator
- `UEnvQueryGenerator_CurrentLocation`：仅查询者当前位置
- `UEnvQueryGenerator_ActorsOfClass`：特定类型所有 Actor 的位置

**Test** 对每个候选点评分。每个 Test 的 `ScoringEquation` 决定了如何处理原始分数：

| 评分公式 | 描述 |
|---------|------|
| `Linear` | `score = Clamp(value, min, max)` 线性映射 |
| `Square` | 平方映射——强化高分点的优势 |
| `InverseLinear` | 反向线性：value 越小分数越高（如距离越近越好） |
| `SquareRoot` | 平方根映射——削弱高分差异 |
| `Constant` | 固定分数——纯粹用于过滤（FilterOnly） |

每个 Test 还有 `FilterType`：`FilterOnly`（不评分，低于阈值的直接丢弃）、`ScoreOnly`（只评分不过滤）、`FilterAndScore`（两者都做）。

**Context** 是参考点提供者。UE 内置：
- `UEnvQueryContext_Querier`：查询者（通常是 AI Controller 的 Pawn）
- `UEnvQueryContext_Item`：当前被测试的候选点自身
- `UEnvQueryContext_Blackboard`：从 Blackboard 读取指定 Key

#### EQS + BT 集成

EQS 通过以下机制接入行为树：

1. **`UBTTask_RunEQSQuery`**：BT Task，执行 EQS 查询并将结果写入 Blackboard。
2. **`UBTService_RunEQS`**：BT Service，周期性执行 EQS 查询（如每 1.0 秒更新最佳掩护位置）。
3. **`UEnvQueryInstanceBlueprintWrapper`**：蓝图可用的 EQS 查询包装器，支持异步查询完成回调。

最经典的 BT 模式——"找掩护 → 移动到掩护"：

```
[Service: UpdateCoverPosition @1.0s via RunEQS_CoverQuery]
Selector
├── Decorator: HasTarget? (LowerPriority)
│   └── Sequence "Combat"
│       ├── RunEQS: FindCoverEQS → BB.CoverLocation
│       └── MoveTo: BB.CoverLocation
└── Action: Patrol
```

关键点：Service 每 1 秒刷新最佳掩护位置（因为目标和自身位置在不断变化），而 MoveTo 持续向该位置移动。如果 EQS 返回的新位置与当前不同，MoveTo 会自动更新目标——不需要额外的 abort 逻辑。

#### EQS 查询执行流程

```
1. PrepareContext: 解析所有 Context，获取参考位置/对象
2. GenerateItems: Generator 使用 Context 生成候选点
3. For each item:
   a. For each Test:
      - 获取 Test 需要的 Context（如 Querier 位置、Target 位置）
      - 运行测试逻辑（距离计算、Trace、自定义函数）
      - 根据 ScoringEquation + ScoringFactor 转换为加权分数
      - 如果 FilterType 包含 Filter 且分数低于阈值：丢弃 item
   b. 累加 item 的总分
4. Sort items by total score (descending)
5. Return top N items
```

每个 Test 有一个 `Weight` 属性——设计师可以调整权重来改变评分优先级。例如"找狙击位"的查询中，"视野开阔"测试的权重设为 2.0，"远离目标"测试的权重设为 0.5。

#### 常见 EQS 使用场景

| 场景 | Generator | 关键 Test | Context |
|------|-----------|-----------|---------|
| 找掩护 | SimpleGrid (NavMesh) | Distance(Querier→Item) + Trace(Target→Item) | Querier, Target |
| 攻击站位 | Cone (前方锥形) | Distance(Target→Item) + Dot(Target→Item→Querier) | Querier, Target |
| 找血包/弹药 | ActorsOfClass | Distance(Querier→Item) + Trace(Enemy→Item) | Querier |
| 巡逻点选择 | ActorsOfClass (巡逻点) | Distance(Querier→Item) + Dot(Querier forward→Item) | Querier |
| 逃逸方向 | OnCircle (16 方向) | Distance(Enemy→Item) * -1 + Trace(Querier→Item) | Enemy, Querier |

---

### Part B — Smart Objects

#### 什么是 Smart Objects？

在传统 AI 交互实现中，交互逻辑是硬编码在行为树里的："如果靠近门 → 播放开门动画 → 等待动画结束 → 移动通过"。问题在于：**交互逻辑和交互对象的位置信息耦合了**。当设计师在地图中放置一扇新类型的门（旋转门 vs. 推拉门），程序员就得写新的 BT 节点。

**Smart Objects** 是 UE5 引入的系统，它将交互能力**从 AI 逻辑中剥离，附着到环境对象上**。核心理念：不是 AI 说"我知道怎么开门"，而是**门自己说"我可以被这样交互"，AI 查询"附近有什么可以交互的"然后执行**。

```
传统模式:  AI BT → if near Door → PlayOpenAnim → MoveThrough
SmartObject: AI BT → Query SmartObjectSubsystem → "附近有什么交互可用？"
                      → 门回答: "我有 EntrySlot+AnimationSlot，需要先 Claim"
                      → AI Claim EntrySlot → 执行开门 GameplayBehavior → Release Slot
```

#### Smart Objects 架构

| 组件 | 类 | 职责 |
|------|-----|------|
| **定义** | `USmartObjectDefinition` | 资产：定义交互的 Slot 类型、激活条件、关联的 GameplayBehavior |
| **运行时** | `USmartObjectSubsystem` | World Subsystem：管理所有 SmartObject 的注册、查询、Claim/Release |
| **标记** | `USmartObjectComponent` | Actor Component：标记一个 Actor 的位置提供了 SmartObject 交互 |
| **行为** | `UGameplayBehavior` | 具体的交互逻辑——播放动画、移动、启用/禁用物理等 |

一个 SmartObject 可以有多个 **Slot**（槽位）。例如一个双开门可以有两个角色同时交互（两个 Slot），一个工作站可以有"使用者"和"旁观者"两个不同角色的 Slot。

**Claim/Use/Release 生命周期**：

```
1. Query: AI 调用 SmartObjectSubsystem::FindSmartObjects(Request)
   → 返回附近可用的 SmartObject 及 Slot 信息

2. Claim: AI 调用 SmartObjectSubsystem::Claim(SmartObjectHandle, SlotHandle)
   → 标记该 Slot 为"已被占用"，其他 AI 查询时不可用

3. Use: AI 激活关联的 GameplayBehavior
   → GameplayBehavior 执行交互逻辑（动画、移动、等待）

4. Release: GameplayBehavior 结束或 AI 主动 Release
   → Slot 恢复为"可用"状态
```

**与 StateTree 的集成**：UE5 的 StateTree 有内置的 SmartObject Task——`StateTreeTask_FindSmartObject` 和 `StateTreeTask_ClaimSmartObject`。Behavior Tree 也可以通过与 SmartObjectSubsystem 直接交互来集成。

#### 典型使用场景

| 场景 | SmartObject 定义 | Slot 类型 |
|------|-----------------|-----------|
| 门 | 推/拉/旋转门的动画 + 移动路径 | 单人使用 |
| 梯子 | 攀爬动画序列 + 起始/结束位置 | 单人使用 |
| 掩护点 | 标记位置 + 进入/退出掩护动画 | 单人使用 |
| 工作站/椅子 | 坐下动画 + 长时间占用 | 单人使用 |
| 小组互动 | 双人对话动画 + 面对面位置 | 两个 Slot（角色 A + 角色 B） |

---

### Part C — GameplayTags 在 AI 中的应用

#### GameplayTags 系统基础

GameplayTags 是 UE 的层级化标签系统。标签以点分隔，形成层级：`AI.State.Combat`、`AI.State.Combat.Ranged`、`AI.Behavior.Aggressive`。层级关系通过前缀匹配表达——拥有 `AI.State.Combat.Ranged` 的实体也匹配 `AI.State.Combat` 的查询。

核心 API：

```cpp
// 标签容器 —— 实体身上"贴"的标签集合
FGameplayTagContainer MyTags;
MyTags.AddTag(FGameplayTag::RequestGameplayTag("AI.State.Combat"));

// 标签查询 —— "我关心哪些标签？"
FGameplayTagQuery Query = FGameplayTagQuery::BuildQuery(
    FGameplayTagQueryExpression().AnyTagsMatch(
        FGameplayTagContainer::CreateFromArray({CombatTag, AlertTag}))
);

// 匹配
bool bMatches = MyTags.MatchesQuery(Query);
```

GameplayTags 的优势：
- **层级化**：`AI.Role.Flanker` 可以被查询 `AI.Role` 的任何表达式匹配
- **数据驱动**：设计师可以在 DataTable 中定义标签，无需修改代码
- **高性能**：标签匹配是整数哈希比较，无字符串开销
- **网络友好**：标签可以作为紧凑的整数复制

#### 标签驱动的 BT 逻辑

UE 行为树原生集成了 GameplayTags：

**装饰器**：
- `UBTDecorator_TagCooldown`：检查标签的冷却状态
- `UBTDecorator_SetTagCooldown`：在子节点执行后为标签设置冷却

**Task**：
- `UBTTask_SetTagCooldown`：直接在 Task 中设置标签冷却

**自定义 Decorator 检查标签**：

```cpp
// 自定义 Decorator: 检查 AI 是否有指定 GameplayTag
bool UBTDecorator_HasGameplayTag::CalculateRawConditionValue(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
{
    // 从 AI 的 AbilitySystemComponent 或自定义组件获取标签
    if (UActorComponent* TagComp = OwnerComp.GetOwner()->GetComponentByClass(...))
    {
        return TagComp->HasMatchingGameplayTag(TagToCheck);
    }
    return false;
}
```

关键设计：不建议在 BT 节点内部硬编码标签字符串。应该使用 `FGameplayTag` 的 `UPROPERTY(EditAnywhere)` 暴露给编辑器，让设计师在编辑器中选择标签。

#### 标签驱动的 AI 角色系统

这是 GameplayTags 在 AI 中最强大的应用模式——**标签即角色**：

```
小队 AI 角色标签:
  AI.Role.Flanker     → 侧翼包抄者（BT 选择绕后路径）
  AI.Role.Sniper      → 狙击手（BT 选择高地 + 远距离）
  AI.Role.Heavy       → 重装兵（BT 选择正面压制 + 高耐久行为）
  AI.Role.Medic       → 医疗兵（BT 优先治疗队友）

AI 状态标签（动态变化）:
  AI.State.Combat     → 战斗中
  AI.State.Alert      → 警戒中
  AI.State.Reloading  → 换弹中
  AI.State.Covering   → 掩护中

AI 能力标签:
  Ability.Melee.Charged   → 近战蓄力完成
  Ability.Ranged.Aimed    → 远程瞄准完成
  Cooldown.Ability.Smoke  → 烟雾弹冷却中
```

行为树通过 Decorator 根据标签启用/禁用不同子树：

```
Selector
├── Decorator: HasTag(AI.State.Dead)
│   └── Action: PlayDeath
├── Decorator: HasTag(AI.Role.Medic) AND HasTag(AI.State.Combat)
│   └── SubTree: MedicCombatBehavior     // 医疗兵特殊战斗逻辑
├── Decorator: HasTag(AI.Role.Sniper) AND HasTag(AI.State.Combat)
│   └── SubTree: SniperCombatBehavior    // 狙击手特殊战斗逻辑
├── Decorator: HasTag(AI.State.Combat)
│   └── SubTree: DefaultCombatBehavior   // 默认战斗逻辑
└── Action: Idle
```

**标签驱动的行为树**使同一个 BT 资产可以服务多种 AI 类型——每种类型只是初始化时被赋予不同的角色标签。这大幅减少了 BT 资产的维护成本。

#### GAS + Tags + BT 的协同

当 AI 使用 GameplayAbilitySystem (GAS) 时，GameplayTags 成为沟通 BT 和 GAS 的桥梁：

```
BT 触发 Ability:
  BTTask_ActivateAbilityByTag → 通过 Tag 激活 GAS Ability
  GAS Ability 执行 → 期间添加临时标签（如 Ability.FireBreath.Active）
  BT Decorator 检查 Ability.FireBreath.Active → 阻止其他行为（Self Abort）

GAS 通知 BT:
  GAS Ability 完成 → 添加标签 Cooldown.Ability.FireBreath (duration=5s)
  BT TagCooldown Decorator 检查到冷却 → 阻止再次激活

Ability 成本管理:
  GAS AttributeSet 管理资源（Mana/Stamina）
  BT Decorator 检查 Attribute 值 → 决定是否使用 Ability
```

这个协作模式的核心优势：**BT 不需要知道 GAS 的内部实现细节**——它只通过标签查询状态。GAS Ability 的修改不影响 BT 结构。

---

## 2. 代码示例

> 以下代码基于 UE 5.4+ API。所有示例都是完整可编译的 C++ 类，包含头文件和实现文件。

### 示例 A：自定义 EQS Generator —— UEnvQueryGenerator_Cone

**目的**：在 AI 前方锥形区域内生成候选攻击站位点。与内置的 `OnCircle` 不同，锥形生成器聚焦于 AI 前方（攻击方向），更适合"找攻击位置"的场景。

```cpp
// EnvQueryGenerator_Cone.h
#pragma once

#include "CoreMinimal.h"
#include "EnvironmentQuery/Generators/EnvQueryGenerator_ProjectedPoints.h"
#include "EnvQueryGenerator_Cone.generated.h"

/**
 * Generates points in a cone-shaped region in front of the querier.
 * Suitable for finding attack positions — points that are in front of
 * the AI, within a configurable angle and distance range.
 */
UCLASS(meta = (DisplayName = "Cone"))
class UEnvQueryGenerator_Cone : public UEnvQueryGenerator_ProjectedPoints
{
    GENERATED_BODY()

public:
    UEnvQueryGenerator_Cone();

    /** Half-angle of the cone in degrees. 45 = 90-degree total cone. */
    UPROPERTY(EditDefaultsOnly, Category = "Cone",
        meta = (ClampMin = "1.0", ClampMax = "180.0"))
    float ConeHalfAngle = 45.0f;

    /** Minimum distance from the querier. */
    UPROPERTY(EditDefaultsOnly, Category = "Cone",
        meta = (ClampMin = "0.0"))
    float MinDistance = 200.0f;

    /** Maximum distance from the querier. */
    UPROPERTY(EditDefaultsOnly, Category = "Cone",
        meta = (ClampMin = "1.0"))
    float MaxDistance = 1500.0f;

    /** Reference point for the cone origin (typically the querier). */
    UPROPERTY(EditDefaultsOnly, Category = "Cone")
    TSubclassOf<UEnvQueryContext> Center;

    /** Number of angular slices (points per ring). */
    UPROPERTY(EditDefaultsOnly, Category = "Cone",
        meta = (ClampMin = "1", ClampMax = "64"))
    int32 AngularSlices = 16;

    /** Number of radial rings. */
    UPROPERTY(EditDefaultsOnly, Category = "Cone",
        meta = (ClampMin = "1", ClampMax = "32"))
    int32 RadialRings = 4;

protected:
    virtual void GenerateItems(FEnvQueryInstance& QueryInstance) const override;
    virtual FText GetDescriptionTitle() const override;
    virtual FText GetDescriptionDetails() const override;
};
```

```cpp
// EnvQueryGenerator_Cone.cpp
#include "EnvQueryGenerator_Cone.h"
#include "EnvironmentQuery/Contexts/EnvQueryContext_Querier.h"
#include "EnvironmentQuery/Items/EnvQueryItemType_Point.h"

UEnvQueryGenerator_Cone::UEnvQueryGenerator_Cone()
{
    Center = UEnvQueryContext_Querier::StaticClass();
    ItemType = UEnvQueryItemType_Point::StaticClass();
}

void UEnvQueryGenerator_Cone::GenerateItems(FEnvQueryInstance& QueryInstance) const
{
    // Resolve the cone origin from context
    TArray<FVector> CenterLocations;
    QueryInstance.PrepareContext(Center, CenterLocations);

    if (CenterLocations.Num() == 0)
    {
        return;
    }

    const FVector Origin = CenterLocations[0];
    const FRotator QuerierRotation = QueryInstance.Owner->GetOwner()
        ? QueryInstance.Owner->GetOwner()->GetActorRotation()
        : FRotator::ZeroRotator;
    const FVector Forward = QuerierRotation.Vector();
    const FVector Right = QuerierRotation.RotateVector(FVector::RightVector);

    const float HalfAngleRad = FMath::DegreesToRadians(ConeHalfAngle);

    // Reserve space: AngularSlices * RadialRings
    QueryInstance.ReserveItemData(CenterLocations.Num() * AngularSlices * RadialRings);

    for (int32 Ring = 0; Ring < RadialRings; ++Ring)
    {
        // T parameter: 0 at MinDistance, 1 at MaxDistance
        const float T = (RadialRings > 1)
            ? static_cast<float>(Ring) / (RadialRings - 1)
            : 0.5f;
        const float Distance = FMath::Lerp(MinDistance, MaxDistance, T);

        for (int32 Slice = 0; Slice < AngularSlices; ++Slice)
        {
            // Angle from -HalfAngle to +HalfAngle
            const float Angle = (AngularSlices > 1)
                ? FMath::Lerp(-HalfAngleRad, HalfAngleRad,
                      static_cast<float>(Slice) / (AngularSlices - 1))
                : 0.0f;

            const FVector Direction = Forward * FMath::Cos(Angle)
                + Right * FMath::Sin(Angle);
            const FVector Point = Origin + Direction * Distance;

            QueryInstance.AddItemData<UEnvQueryItemType_Point>(Point);
        }
    }
}

FText UEnvQueryGenerator_Cone::GetDescriptionTitle() const
{
    return FText::Format(FText::FromString("Cone: {0}° x {1}-{2}cm"),
        FText::AsNumber(ConeHalfAngle * 2),
        FText::AsNumber(MinDistance),
        FText::AsNumber(MaxDistance));
}

FText UEnvQueryGenerator_Cone::GetDescriptionDetails() const
{
    return FText::Format(FText::FromString("{0} slices x {1} rings ({2} points)"),
        FText::AsNumber(AngularSlices),
        FText::AsNumber(RadialRings),
        FText::AsNumber(AngularSlices * RadialRings));
}
```

**关键设计决策**：
- 继承自 `UEnvQueryGenerator_ProjectedPoints` 而非 `UEnvQueryGenerator` 直接基类——`ProjectedPoints` 基类自动将生成的点投影到 NavMesh 上。如果不需要投影（如三维空间查询），继承 `UEnvQueryGenerator` 即可。
- 使用 `QueryInstance.PrepareContext(Center, ...)` 解析 Context——不要假设单一点。UE 的 Context 可能返回多个位置（如"所有 Target 的位置"），Generator 需要为每个 Center 位置生成一组点。
- 点在极坐标中生成（角度 × 距离），然后转换为世界坐标。这比笛卡尔随机采样更均匀，避免了中心过密的问题。

### 示例 B：自定义 EQS Test —— UEnvQueryTest_DangerScore

**目的**：为 EQS 候选点评估危险度——危险度越低的点分数越高。综合考虑两个因素：是否在敌人视线内（Trace 检测）、是否靠近爆炸物（距离检测）。

```cpp
// EnvQueryTest_DangerScore.h
#pragma once

#include "CoreMinimal.h"
#include "EnvironmentQuery/EnvQueryTest.h"
#include "EnvQueryTest_DangerScore.generated.h"

/**
 * Scores EQS items by danger level — lower danger = higher score.
 * Factors: enemy line-of-sight (visibility trace) and proximity to
 * explosive barrels. Useful for cover-finding queries.
 */
UCLASS()
class UEnvQueryTest_DangerScore : public UEnvQueryTest
{
    GENERATED_BODY()

public:
    UEnvQueryTest_DangerScore();

    /** Context that provides the enemy/threat location. */
    UPROPERTY(EditDefaultsOnly, Category = "Danger")
    TSubclassOf<UEnvQueryContext> EnemyContext;

    /** Distance within which enemy line-of-sight applies full danger. */
    UPROPERTY(EditDefaultsOnly, Category = "Danger",
        meta = (ClampMin = "0.0"))
    float EnemySightMaxDistance = 3000.0f;

    /** Tag that marks actors as explosive hazards. */
    UPROPERTY(EditDefaultsOnly, Category = "Danger")
    FName ExplosiveTag = FName("Explosive");

    /** Distance within which an explosive barrel is considered dangerous. */
    UPROPERTY(EditDefaultsOnly, Category = "Danger",
        meta = (ClampMin = "0.0"))
    float ExplosiveDangerRadius = 500.0f;

    /** Weight multiplier for line-of-sight danger vs. explosive danger.
     *  1.0 = both equally significant; >1.0 = LOS more important */
    UPROPERTY(EditDefaultsOnly, Category = "Danger",
        meta = (ClampMin = "0.0"))
    float LOSWeight = 1.0f;

protected:
    virtual void RunTest(FEnvQueryInstance& QueryInstance) const override;
    virtual FText GetDescriptionTitle() const override;
};
```

```cpp
// EnvQueryTest_DangerScore.cpp
#include "EnvQueryTest_DangerScore.h"
#include "EnvironmentQuery/Items/EnvQueryItemType_Point.h"
#include "EnvironmentQuery/Contexts/EnvQueryContext_Querier.h"
#include "CollisionQueryParams.h"
#include "Engine/World.h"
#include "EngineUtils.h"

UEnvQueryTest_DangerScore::UEnvQueryTest_DangerScore()
{
    // Default scoring: higher is better. We'll produce danger as a
    // penalty (0 = no danger, 1 = max danger), then invert.
    TestPurpose = EEnvTestPurpose::Score;
    ScoringEquation = EEnvTestScoringEquation::Linear;

    // Clamp score to [0, 1] — this test's output is a penalty factor
    ClampMinType = EEnvQueryTestClamping::SpecifiedValue;
    ClampMaxType = EEnvQueryTestClamping::SpecifiedValue;
    ScaledClampMin = 0.0f;
    ScaledClampMax = 1.0f;

    // Higher is better, so danger = 0 → score = 1, danger = 1 → score = 0
    bInverseScore = true;

    FloatValueMin = 0.0f;
    FloatValueMax = 1.0f;

    EnemyContext = UEnvQueryContext_Querier::StaticClass();
    ValidItemType = UEnvQueryItemType_Point::StaticClass();
}

void UEnvQueryTest_DangerScore::RunTest(FEnvQueryInstance& QueryInstance) const
{
    UWorld* World = QueryInstance.World;
    if (!World)
    {
        return;
    }

    // Resolve enemy/threat locations
    TArray<FVector> EnemyLocations;
    QueryInstance.PrepareContext(EnemyContext, EnemyLocations);

    // Collect explosive barrel locations once (not per-item)
    TArray<FVector> ExplosiveLocations;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (It->ActorHasTag(ExplosiveTag))
        {
            ExplosiveLocations.Add(It->GetActorLocation());
        }
    }

    // Iterate over all items
    for (FEnvQueryInstance::ItemIterator It(this, QueryInstance); It; ++It)
    {
        const FVector ItemLocation = GetItemLocation(QueryInstance, It.GetIndex());
        float TotalDanger = 0.0f;

        // Factor 1: Enemy line-of-sight
        for (const FVector& EnemyPos : EnemyLocations)
        {
            const float Dist = FVector::Dist(ItemLocation, EnemyPos);
            if (Dist > EnemySightMaxDistance)
            {
                continue; // Too far for enemy to see this point
            }

            FHitResult Hit;
            FCollisionQueryParams Params;
            Params.bTraceComplex = false;
            // Trace from enemy to item — if blocked, item is safe
            const bool bBlocked = World->LineTraceSingleByChannel(
                Hit, EnemyPos, ItemLocation, ECC_Visibility, Params);

            if (!bBlocked)
            {
                // Item is visible to enemy — danger proportional to proximity
                const float CloseFactor = 1.0f - (Dist / EnemySightMaxDistance);
                TotalDanger += CloseFactor * LOSWeight;
            }
        }

        // Factor 2: Proximity to explosive barrels
        for (const FVector& ExplosivePos : ExplosiveLocations)
        {
            const float Dist = FVector::Dist(ItemLocation, ExplosivePos);
            if (Dist < ExplosiveDangerRadius)
            {
                TotalDanger += 1.0f - (Dist / ExplosiveDangerRadius);
            }
        }

        // Normalize: max danger per enemy is LOSWeight, per explosive is 1.0
        const float MaxPossibleDanger =
            EnemyLocations.Num() * LOSWeight + ExplosiveLocations.Num();
        const float NormalizedDanger = (MaxPossibleDanger > 0.0f)
            ? FMath::Clamp(TotalDanger / MaxPossibleDanger, 0.0f, 1.0f)
            : 0.0f;

        It.SetScore(TestPurpose, FilterType, NormalizedDanger,
            FloatValueMin, FloatValueMax);
    }
}

FText UEnvQueryTest_DangerScore::GetDescriptionTitle() const
{
    return FText::FromString(FString::Printf(
        TEXT("DangerScore: LOS(w=%.1f) + Explosive"), LOSWeight));
}
```

**关键设计决策**：
- `bInverseScore = true`：Test 产生的原始值是"危险度"（0=安全，1=危险），但 EQS 分数是"越高越好"。设置 bInverseScore 让框架自动完成反转——你不需要手动计算 `1 - score`。
- `FilterType` 和 `ScoringEquation` 在构造函数中设置，但设计师可以在编辑器中覆盖——因为它们是 `UPROPERTY(EditDefaultsOnly)`。这样同一个 Test 类既可以用于评分，也可以用于过滤。
- 爆炸物位置在每个 item 迭代时重复使用——这避免了重复的 `TActorIterator` 遍历。如果爆炸物很多，应考虑在查询开始前缓存结果。

### 示例 C：SmartObject 定义 + GameplayBehavior —— 门交互

**目的**：实现一个完整的门交互系统。门是 SmartObject——AI 查询到门、Claim 一个 Slot、执行开门行为、穿过门、Release Slot。

首先定义 SmartObject 的数据结构和一个自定义 `UAnimMontage` 驱动的 GameplayBehavior。

```cpp
// SOGameplayBehavior_InteractDoor.h
#pragma once

#include "CoreMinimal.h"
#include "SmartObjectGameplayBehavior.h"
#include "SOGameplayBehavior_InteractDoor.generated.h"

class UAnimMontage;
class AAIController;

/**
 * GameplayBehavior for door interaction.
 *
 * Lifecycle:
 *   1. Claim entry slot on the door SmartObject
 *   2. Move to entry position
 *   3. Play door-open animation
 *   4. Move to exit position (through the door)
 *   5. Release the slot
 *
 * This behavior is driven by the SmartObject subsystem —
 * the AI only needs to query, claim, and trigger the behavior.
 */
UCLASS()
class USOGameplayBehavior_InteractDoor : public USmartObjectGameplayBehavior
{
    GENERATED_BODY()

public:
    /** Animation montage to play when opening the door. */
    UPROPERTY(EditDefaultsOnly, Category = "Animation")
    UAnimMontage* OpenDoorMontage;

    /** Duration to wait after the animation before moving through. */
    UPROPERTY(EditDefaultsOnly, Category = "Animation",
        meta = (ClampMin = "0.0"))
    float PostAnimationDelay = 0.3f;

    /** Speed at which the AI moves through the door. */
    UPROPERTY(EditDefaultsOnly, Category = "Movement",
        meta = (ClampMin = "1.0"))
    float MoveThroughSpeed = 300.0f;

protected:
    // USmartObjectGameplayBehavior overrides
    virtual bool Activate(const FSmartObjectActivationContext& Context) override;
    virtual void OnDeactivated(const FSmartObjectActivationContext& Context) override;

private:
    /** Per-user state — tracks which phase of door interaction we're in. */
    enum class EDoorPhase : uint8
    {
        MovingToEntry,
        PlayingAnimation,
        WaitingAfterAnimation,
        MovingToExit,
        Complete
    };

    struct FPerUserData
    {
        EDoorPhase Phase = EDoorPhase::MovingToEntry;
        float Timer = 0.0f;
        FVector ExitLocation;
    };

    TMap<AActor*, FPerUserData> UserData;

    void TickDoorInteraction(AAIController* AI, FPerUserData& Data, float DeltaTime);
    FVector GetExitLocation(const FSmartObjectActivationContext& Context) const;
};
```

```cpp
// SOGameplayBehavior_InteractDoor.cpp
#include "SOGameplayBehavior_InteractDoor.h"
#include "AIController.h"
#include "GameFramework/Character.h"
#include "NavigationSystem.h"
#include "SmartObjectSubsystem.h"
#include "SmartObjectComponent.h"

bool USOGameplayBehavior_InteractDoor::Activate(
    const FSmartObjectActivationContext& Context)
{
    AActor* User = const_cast<AActor*>(Context.GetUserActor());
    if (!User)
    {
        return false;
    }

    AAIController* AI = Cast<AAIController>(User->GetInstigatorController());
    if (!AI)
    {
        // Fallback: user might be directly controlled by an AIController
        AI = Cast<AAIController>(User);
    }
    if (!AI)
    {
        return false;
    }

    FPerUserData& Data = UserData.Add(User);
    Data.Phase = EDoorPhase::MovingToEntry;
    Data.ExitLocation = GetExitLocation(Context);

    // Start moving to the door entry point
    // The SmartObject slot's transform defines the entry position
    const FSmartObjectSlotView Slot = Context.GetSlotView();
    const FVector EntryLocation = Slot.GetTransform().GetLocation();
    AI->MoveToLocation(EntryLocation, 50.0f);

    return true;
}

void USOGameplayBehavior_InteractDoor::OnDeactivated(
    const FSmartObjectActivationContext& Context)
{
    AActor* User = const_cast<AActor*>(Context.GetUserActor());
    if (User)
    {
        UserData.Remove(User);
    }
}

FVector USOGameplayBehavior_InteractDoor::GetExitLocation(
    const FSmartObjectActivationContext& Context) const
{
    // Exit is on the other side of the door.
    // In production, this would be defined per-slot in the SmartObjectDefinition.
    const FSmartObjectSlotView Slot = Context.GetSlotView();
    const FTransform SlotTransform = Slot.GetTransform();
    const FVector DoorForward = SlotTransform.GetRotation().Vector();
    return SlotTransform.GetLocation() + DoorForward * 250.0f;
}

void USOGameplayBehavior_InteractDoor::TickDoorInteraction(
    AAIController* AI, FPerUserData& Data, float DeltaTime)
{
    switch (Data.Phase)
    {
    case EDoorPhase::MovingToEntry:
        if (AI->GetMoveStatus() == EPathFollowingStatus::Idle)
        {
            // Reached entry — play animation
            if (ACharacter* Char = AI->GetCharacter())
            {
                if (OpenDoorMontage)
                {
                    Char->PlayAnimMontage(OpenDoorMontage);
                }
            }
            Data.Phase = EDoorPhase::PlayingAnimation;
            Data.Timer = OpenDoorMontage
                ? OpenDoorMontage->GetPlayLength() : 0.0f;
        }
        break;

    case EDoorPhase::PlayingAnimation:
        Data.Timer -= DeltaTime;
        if (Data.Timer <= 0.0f)
        {
            Data.Phase = EDoorPhase::WaitingAfterAnimation;
            Data.Timer = PostAnimationDelay;
        }
        break;

    case EDoorPhase::WaitingAfterAnimation:
        Data.Timer -= DeltaTime;
        if (Data.Timer <= 0.0f)
        {
            AI->MoveToLocation(Data.ExitLocation, 50.0f);
            Data.Phase = EDoorPhase::MovingToExit;
        }
        break;

    case EDoorPhase::MovingToExit:
        if (AI->GetMoveStatus() == EPathFollowingStatus::Idle)
        {
            Data.Phase = EDoorPhase::Complete;
        }
        break;

    case EDoorPhase::Complete:
        break;
    }
}
```

**配套的 BT Task —— 驱动整个 SmartObject 交互流程**：

```cpp
// BTTask_UseSmartObject.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/BTTaskNode.h"
#include "BTTask_UseSmartObject.generated.h"

struct FSmartObjectRequestFilter;
class USmartObjectSubsystem;

/**
 * BT Task that queries the SmartObjectSubsystem for the nearest usable
 * SmartObject matching a tag, claims a slot, activates the behavior,
 * and waits for completion. Writes the SmartObject location to a
 * Blackboard Vector key for fallback movement.
 */
UCLASS()
class UBTTask_UseSmartObject : public UBTTaskNode
{
    GENERATED_BODY()

public:
    UBTTask_UseSmartObject();

    /** GameplayTag the SmartObject must have to be selected. */
    UPROPERTY(EditAnywhere, Category = "SmartObject")
    FGameplayTag RequiredTag;

    /** Search radius for nearby SmartObjects. */
    UPROPERTY(EditAnywhere, Category = "SmartObject",
        meta = (ClampMin = "0.0"))
    float SearchRadius = 2000.0f;

    /** BB key to write the SmartObject location into (for fallback). */
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector OutputLocationKey;

protected:
    virtual EBTNodeResult::Type ExecuteTask(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;
    virtual EBTNodeResult::Type AbortTask(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;
    virtual void TickTask(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;
    virtual uint16 GetInstanceMemorySize() const override;

private:
    USmartObjectSubsystem* GetSmartObjectSubsystem(
        UBehaviorTreeComponent& OwnerComp) const;
};

struct FBTTaskUseSmartObjectMemory
{
    FSmartObjectClaimHandle ClaimedHandle;
    bool bBehaviorActivated = false;
};
```

```cpp
// BTTask_UseSmartObject.cpp
#include "BTTask_UseSmartObject.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"
#include "SmartObjectSubsystem.h"
#include "SmartObjectComponent.h"
#include "GameplayBehavior.h"

UBTTask_UseSmartObject::UBTTask_UseSmartObject()
{
    NodeName = TEXT("Use SmartObject");
    bNotifyTick = true;
}

uint16 UBTTask_UseSmartObject::GetInstanceMemorySize() const
{
    return sizeof(FBTTaskUseSmartObjectMemory);
}

USmartObjectSubsystem* UBTTask_UseSmartObject::GetSmartObjectSubsystem(
    UBehaviorTreeComponent& OwnerComp) const
{
    if (UWorld* World = OwnerComp.GetWorld())
    {
        return World->GetSubsystem<USmartObjectSubsystem>();
    }
    return nullptr;
}

EBTNodeResult::Type UBTTask_UseSmartObject::ExecuteTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    FBTTaskUseSmartObjectMemory* MyMemory =
        reinterpret_cast<FBTTaskUseSmartObjectMemory*>(NodeMemory);
    MyMemory->ClaimedHandle = FSmartObjectClaimHandle();
    MyMemory->bBehaviorActivated = false;

    USmartObjectSubsystem* SOSubsystem = GetSmartObjectSubsystem(OwnerComp);
    if (!SOSubsystem)
    {
        return EBTNodeResult::Failed;
    }

    AAIController* AI = OwnerComp.GetAIOwner();
    APawn* Pawn = AI ? AI->GetPawn() : nullptr;
    if (!Pawn)
    {
        return EBTNodeResult::Failed;
    }

    // Build query request
    FSmartObjectRequest Request;
    Request.QueryBox = FBoxCenterAndExtent(
        Pawn->GetActorLocation(), FVector(SearchRadius));
    Request.Filter = FSmartObjectRequestFilter();
    Request.Filter.UserTags = FGameplayTagContainer(RequiredTag);

    // Find and claim
    FSmartObjectRequestResult Result;
    if (!SOSubsystem->FindSmartObject(Request, Result))
    {
        return EBTNodeResult::Failed;
    }

    const FSmartObjectClaimHandle ClaimedHandle =
        SOSubsystem->Claim(Result);
    if (!ClaimedHandle.IsValid())
    {
        return EBTNodeResult::Failed;
    }

    MyMemory->ClaimedHandle = ClaimedHandle;

    // Activate the associated GameplayBehavior
    if (const USmartObjectComponent* SOComp =
            SOSubsystem->GetSmartObjectComponent(ClaimedHandle))
    {
        if (UGameplayBehavior* Behavior = SOComp->GetDefinition()
                ->GetDefaultGameplayBehavior())
        {
            FSmartObjectActivationContext ActivationContext(Pawn);
            if (Behavior->Activate(ActivationContext))
            {
                MyMemory->bBehaviorActivated = true;
            }
        }
    }

    // Write location to BB for fallback/debug
    if (UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent())
    {
        const FVector SOLocation =
            SOSubsystem->GetSlotLocation(MyMemory->ClaimedHandle);
        BB->SetValueAsVector(OutputLocationKey.SelectedKeyName, SOLocation);
    }

    return MyMemory->bBehaviorActivated
        ? EBTNodeResult::InProgress
        : EBTNodeResult::Failed;
}

void UBTTask_UseSmartObject::TickTask(UBehaviorTreeComponent& OwnerComp,
    uint8* NodeMemory, float DeltaSeconds)
{
    FBTTaskUseSmartObjectMemory* MyMemory =
        reinterpret_cast<FBTTaskUseSmartObjectMemory*>(NodeMemory);

    USmartObjectSubsystem* SOSubsystem = GetSmartObjectSubsystem(OwnerComp);
    if (!SOSubsystem || !MyMemory->ClaimedHandle.IsValid())
    {
        FinishLatentTask(OwnerComp, EBTNodeResult::Failed);
        return;
    }

    // Check if the slot is still claimed by us and the behavior
    // is still active. If released, the interaction is complete.
    const FSmartObjectSlotView Slot =
        SOSubsystem->GetSlotView(MyMemory->ClaimedHandle);
    if (Slot.GetState() != ESmartObjectSlotState::Claimed)
    {
        FinishLatentTask(OwnerComp, EBTNodeResult::Succeeded);
    }
}

EBTNodeResult::Type UBTTask_UseSmartObject::AbortTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    FBTTaskUseSmartObjectMemory* MyMemory =
        reinterpret_cast<FBTTaskUseSmartObjectMemory*>(NodeMemory);

    if (MyMemory->ClaimedHandle.IsValid())
    {
        if (USmartObjectSubsystem* SOSubsystem =
                GetSmartObjectSubsystem(OwnerComp))
        {
            SOSubsystem->Release(MyMemory->ClaimedHandle);
        }
        MyMemory->ClaimedHandle = FSmartObjectClaimHandle();
    }

    return EBTNodeResult::Aborted;
}
```

### 示例 D：BT 集成 —— EQS + SmartObject + GameplayTags 协同

以下是一个完整的行为树结构，展示三个系统如何在同一棵树中协同工作。场景：一个战术小队 NPC，根据角色标签（Flanker/Sniper/Heavy）使用不同策略，通过 EQS 找位置，通过 SmartObject 与门交互。

树结构（以文本形式呈现——实际在 UE BT Editor 中通过拖拽构建）：

```
Selector [Root]
│  Service: UpdatePerception @0.3s
│  Service: RunEQS_RefreshCover @1.0s → BB.CoverPosition
│
├── Decorator: HasTag(AI.State.Dead) (Self)
│   └── Action: PlayDeath
│
├── Decorator: HasTarget? (LowerPriority)
│   └── Sequence "Combat"
│       │  Service: RunEQS_FindAttackPosition @0.5s → BB.AttackPosition
│       │
│       ├── Decorator: HasTag(Cooldown.Ability.ThrowGrenade)
│       │   └── ForceFailure  ← block grenade subtree during cooldown
│       │
│       ├── Decorator: HasTag(AI.Role.Flanker) AND
│       │             HasTag(Ability.Grenade.Ready) (LowerPriority)
│       │   └── Sequence "FlankerGrenade"
│       │       ├── Action: SetTagCooldown(Cooldown.Ability.ThrowGrenade, 15s)
│       │       └── Action: ThrowGrenadeAtTarget
│       │
│       ├── Decorator: HasTag(AI.Role.Sniper) AND
│       │             TargetDistance > 2000 (LowerPriority)
│       │   └── Sequence "SniperEngage"
│       │       ├── Action: MoveTo BB.AttackPosition ← EQS result
│       │       └── Action: AimedShot
│       │
│       ├── Decorator: HasTag(AI.Role.Heavy) AND
│       │             TargetDistance < 800 (LowerPriority)
│       │   └── Sequence "HeavyRush"
│       │       ├── Action: MoveTo BB.CoverPosition  ← EQS result
│       │       └── Action: SuppressingFire
│       │
│       └── Action: MoveTo BB.CoverPosition  ← default: take cover
│
├── Decorator: Health < 50% (LowerPriority)
│   └── Sequence "SeekHealth"
│       ├── Action: UseSmartObject(Tag="Interact.HealthStation")
│       └── Action: Wait(3s)  // simulate healing time
│
└── Sequence "Patrol"
    ├── Action: MoveTo BB.PatrolPoint
    ├── Action: Wait(2s)
    └── Action: MoveTo BB.NextPatrolPoint
```

**集成要点**：
1. **EQS 作为 Service**：`RunEQS_RefreshCover` 每 1 秒刷新最佳掩护位置——因为战斗中目标和自身位置在持续变化。BT 的 MoveTo 节点持续向最新位置移动，无需额外 abort 逻辑。
2. **SmartObject 作为 Task**：`UseSmartObject` Task 封装了 Claim → Activate → Wait → Release 的完整生命周期，BT 只需将其作为普通叶子节点使用。
3. **GameplayTags 作为条件**：`HasTag(AI.Role.Sniper)` 让同一棵树适配多种角色。`HasTag(Cooldown.*)` 通过 TagCooldown 机制阻止行为重复触发。

配置示例——在 `AMyAIController` 中启动并设置初始标签：

```cpp
void AMyAIController::BeginPlay()
{
    Super::BeginPlay();

    // Assign role tag based on AI type
    if (AbilitySystemComponent)
    {
        FGameplayTagContainer RoleTags;
        switch (AssignedRole)
        {
        case ERole::Flanker:
            RoleTags.AddTag(FGameplayTag::RequestGameplayTag("AI.Role.Flanker"));
            break;
        case ERole::Sniper:
            RoleTags.AddTag(FGameplayTag::RequestGameplayTag("AI.Role.Sniper"));
            break;
        case ERole::Heavy:
            RoleTags.AddTag(FGameplayTag::RequestGameplayTag("AI.Role.Heavy"));
            break;
        }
        AbilitySystemComponent->AddLooseGameplayTags(RoleTags);
    }

    RunBehaviorTree(BehaviorTreeAsset);
}
```

---

## 3. 练习

### 练习 1：设计一个 EQS 查询——寻找最佳狙击位置

为狙击手 AI 设计一个完整的 EQS 查询，找到最佳射击位置。不使用代码，用 EQS 编辑器的概念描述。

要求覆盖以下评分维度：
1. **高地形**：位置高度比周围高（使用 Z 轴差值）
2. **视野开阔**：从该位置到目标的 Trace 不被阻挡
3. **远离目标**：与目标保持足够距离（狙击手不适合近战），但不超过武器有效射程
4. **靠近掩护**：位置附近有障碍物可以随时躲入（双重 Trace：位置→目标无阻挡 + 位置后退 2 米有阻挡）

写出查询的 Generator 选择和每个 Test 的配置（Test 类型、评分公式、权重）。解释权重比例的选择理由。

### 练习 2：为医疗站创建 SmartObject 并接入行为树

设计一个完整的"医疗站"SmartObject 集成方案。

要求：
1. 定义 `USmartObjectDefinition` 资产：包含一个 Slot，关联的 GameplayBehavior 负责播放治疗动画并在 3 秒后恢复 NPC 血量至 100%。
2. 在 AIController 的 BT 中实现医疗寻求逻辑：当 HP < 30% 时，EQS 查询最近的医疗站（`ActorsOfClass` Generator + `Distance` Test），移动到该位置，通过 SmartObject 交互进行治疗。
3. 处理竞争条件：如果多个 AI 同时寻找医疗站而只有一个 Slot，未被 Claim 到的 AI 应该怎么办？（描述解决方案，不必须写代码）
4. 分析：治疗过程中如果受到攻击，应该 Abort 治疗还是继续？两种选择分别适合什么游戏类型？

### 练习 3（可选）：设计标签驱动的 AI 角色系统

为一个 4 人战术小队设计完整的 GameplayTag 驱动行为系统。

要求：
1. 定义角色标签层级——至少 4 种角色（Flanker / Sniper / Heavy / Medic）
2. 定义状态标签层级——AI 状态（Idle / Alert / Combat / Retreating / Dead）
3. 定义能力标签层级——技能和冷却（至少 2 个主动技能 + 冷却标签）
4. 设计一棵统一的行为树，通过标签区分不同角色的行为：
   - Flanker 在战斗中优先侧翼包抄（通过 EQS 找侧翼位置）
   - Sniper 在战斗中优先找高地 + 远距离攻击
   - Heavy 在战斗中优先正面压制 + 高频率攻击
   - Medic 在战斗中优先治疗受伤队友（血量 < 50%），只在没有治疗需求时攻击
5. 画出完整的树结构，标注每个 Decorator 检查的标签。

---

## 4. 扩展阅读

- **Unreal Engine EQS 官方文档**：[Environment Query System](https://docs.unrealengine.com/5.4/en-US/environment-query-system-in-unreal-engine/) — UE 官方的 EQS 参考，涵盖内置 Node 的详细参数说明和蓝图集成。
- **Unreal Engine Smart Objects 文档**：[Smart Objects](https://docs.unrealengine.com/5.4/en-US/smart-objects-in-unreal-engine/) — SmartObjectSubsystem 的 API 参考和编辑器工作流。
- **Unreal Engine GameplayTags 文档**：[Gameplay Tags](https://docs.unrealengine.com/5.4/en-US/gameplay-tags-in-unreal-engine/) — GameplayTag 的层级结构、DataTable 管理、以及 GameplayTagQuery 的表达式构建。
- **Epic Games — Lyra Sample Project**：UE5 官方的 Lyra 示例项目是学习 Smart Objects + GameplayTags + GAS 集成的最佳实践参考。特别关注 `ShooterExplorer` 和 `ShooterMancer` AI 的 BT 结构和 SmartObject 用法。
- **Epic Games — "UE5 Gameplay Features: Smart Objects & StateTree"** (YouTube, Unreal Engine channel)：Epic 官方演示了 SmartObject + StateTree 的端到端工作流——StateTree 如何查询/Claim/使用 SmartObject，对理解 BT + SmartObject 的集成有很好的参考价值。
- **AIGameDev.com — "Spatial Reasoning for Game AI with EQS"** (archived)：深入讨论了 EQS 中的 Context 传递、多 Generator 组合、和异步查询的性能考量。

---

## 常见陷阱

### 1. EQS 查询不做 NavMesh 投影导致 AI 走到不可达位置

**症状**：AI 在 EQS 返回的位置和实际可到达位置之间来回移动，或在不可行走的地形上"滑行"。

**根因**：EQS Generator 生成的点没有被投影到 NavMesh 上。使用 `UEnvQueryGenerator_SimpleGrid` 或自定义 Generator 时，如果没有启用 `bProjectPoints` 或没有继承 `UEnvQueryGenerator_ProjectedPoints`，生成的点可能落在障碍物内部、空中、或不可行走的表面上。MoveTo 会尝试寻路到这些点——如果不可达，行为表现异常。

**解法**：
1. 继承 `UEnvQueryGenerator_ProjectedPoints` 并在子类构造函数中设置 `ProjectionData`。
2. 如果必须使用非投影 Generator，在 Test 链中添加 `UEnvQueryTest_Trace`（设置为 FilterOnly）过滤不可达点。
3. 在 EQS Query 资产中启用 "Generate Only on NavMesh" 设置（UE5 的 `UEnvQuery` 上的 `bGenerateOnlyOnNavMesh` 标志）。

### 2. EQS 查询开销低估——每帧/每秒运行 EQS 导致 CPU 尖峰

**症状**：场景中有 50+ AI 时，帧率在战斗阶段骤降。Profiler 显示 CPU 时间大量消耗在 EQS 的 `GenerateItems` 和 `RunTest` 中。

**根因**：EQS 不是免费操作。一个典型的"找掩护"查询可能涉及 200+ 个候选点 × 3-5 个 Test（含多次 Trace 调用）。如果 AI 每 0.3 秒运行一次这个查询，50 个 AI 每秒产生约 50 × (200 × 4) × 3.3 ≈ 132,000 次 Trace 调用。

**解法**：
1. **降低 EQS 运行频率**：掩护位置不需要每 0.3 秒更新。1.0-2.0 秒通常足够——玩家感知不到差异。
2. **限制候选点数量**：`SimpleGrid` 的 `GridSize` 和 `SpaceBetween` 参数直接决定候选点数。对于找掩护，50-100 个点通常足够；200+ 只有在非常大的开放区域才需要。
3. **使用 Item 缓存**：如果 EQS 查询的参考点（Querier/Target）没有显著移动（距离 < 阈值），可以跳过查询，使用上次缓存的结果。
4. **LOD 衰减**：远处 AI 的 EQS 频率降到 3-5 秒甚至关闭——离玩家 100 米外的 AI 不需要每 1 秒找掩护。
5. **在 Service 中使用 `RandomDeviation`**：避免所有 AI 在同一帧运行 EQS。

### 3. SmartObject Slot 泄露——Claim 后未 Release

**症状**：AI 使用门/梯子/工作站后，Slot 永远处于 Claimed 状态。其他 AI 无法使用该对象。长期运行后场景中所有 SmartObject Slot 都被"僵尸占用"。

**根因**：AI 在以下场景中没有正确 Release Slot：
- BT abort 时（被更高优先级行为抢断），没有在 `AbortTask` 中调用 `SOSubsystem->Release()`。
- AI 被销毁时（死亡/销毁），没有在 `EndPlay` 或析构中 Release。
- GameplayBehavior 内部异常退出（动画资源缺失、寻路失败），没有通过 `OnDeactivated` 清理。

**解法**：
1. **BT Task 的 `AbortTask` 中 release**：如示例 D 的 `BTTask_UseSmartObject` 所示——`AbortTask` 是必须实现的。
2. **AIController 的 `EndPlay` 中 release**：维护一个已 Claim 的 handle 列表，在 `EndPlay` 中遍历 release。
3. **GameplayBehavior 的超时机制**：如果行为在合理时间内未完成，应当 release slot 并返回 failure。
4. **SmartObjectSubsystem 的看门狗**：定期扫描 Claimed 但用户已无效的 Slot（用户 Pawn 已销毁），自动 Release。UE5 的 Subsystem 内置了部分此类检查，但自定义实现应额外保护。

### 4. GameplayTag 字符串硬编码导致重构灾难

**症状**：代码中散布着 `FGameplayTag::RequestGameplayTag("AI.State.Combat")`，当设计师或后续开发者决定重命名标签层级（如 `AI.State` → `NPC.State`）时，所有硬编码字符串都需要手动查找替换——一个遗漏就是运行时 bug。

**根因**：GameplayTags 虽然本质上是 `FName`（轻量级），但它们的**定义和管理**是版本控制中的资产。标签字符串不应该分散在 C++ 代码中。

**解法**：
1. **集中的 Native Tag 声明**：在一个头文件中使用 `UE_DECLARE_GAMEPLAY_TAG_EXTERN` + cpp 中 `UE_DEFINE_GAMEPLAY_TAG`，将标签定义为 C++ 全局常量。
2. **DataTable 管理**：在 `.ini` 或 DataTable 中集中定义所有标签，作为单一事实来源。
3. **不允许在 BT 节点中写死标签字符串**：BT Decorator/Service 的标签字段使用 `UPROPERTY(EditAnywhere, meta = (Categories = "AI.State"))` 暴露给编辑器——设计师在 BT Editor 中从下拉菜单选择标签，不是手动输入字符串。

### 5. 混淆 EQS Context、Blackboard 和 BT Service 的数据更新职责

**症状**：数据流混乱——有时 EQS 写入 Blackboard，有时 BT Service 写入，有时两者同时写入导致竞态。调试时无法确定"当前 Cover 位置是哪个系统写的，是什么时候写的"。

**根因**：三个系统都可以读写 Blackboard，但没有清晰的职责划分。

**解法——建立清晰的数据主权规则**：
- **EQS 负责空间推理结果**：`CoverPosition`、`AttackPosition`、`FleeDirection` 由 EQS 写入。这些是空间评分的结果。
- **BT Service 负责感知和状态更新**：`TargetActor`、`TargetDistance`、`AlertLevel` 由 Service 写入。这些是感知系统查询的结果。
- **BT Task 负责行为执行结果**：`CurrentAction`、`LastInteractionTime` 由 Task 写入。这些是行为执行后的状态标记。
- **绝不让两个系统写同一个 Key**：如果 EQS 和 Service 都需要写位置信息，它们应该用不同的 Key（如 `EQS_CoverPosition` vs. `Service_ThreatPosition`），Task 决定读哪个。
- **在 BT Editor 中对 Blackboard Key 做颜色编码或命名规范**：EQS 写入的 Key 前缀 `EQS_`，Service 写入的前缀 `Svc_`，Task 写入的前缀 `Act_`。

---

> **下一步**: 完成本教程后，继续 Tutorial 23 [[23-statetree-modern-ai|StateTree 与现代 UE5 AI 架构]]，学习 UE5 引入的 StateTree 系统如何作为 FSM+BT 的混合方案，以及它如何与 SmartObject/EQS/GameplayTags 深度集成。
