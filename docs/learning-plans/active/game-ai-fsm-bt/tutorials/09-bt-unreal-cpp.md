---
title: "行为树在 Unreal Engine 中的实现 (C++)"
updated: 2026-06-05
---

# 行为树在 Unreal Engine 中的实现 (C++)

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 150min
> 前置知识: 06-bt-fundamentals, 07-bt-node-types

---

## 1. 概念讲解

### 为什么 Unreal 的 Behavior Tree 是一个完整框架（而不只是库）？

Tutorial 06 和 07 建立了行为树的理论基础——Composite、Decorator、Leaf、Service 的抽象契约。如果你在 Unity 中实现行为树，你需要自己写 Tick 循环、自己管理节点状态、自己处理事件驱动。但当你转向 Unreal Engine 的 UBehaviorTree 系统时，你会立刻注意到一个关键差异：

**UE 的 Behavior Tree 不是一个库——它是一个编辑器和运行时的完整框架。** 这意味着它有大段固定的架构约定、资产管线、和内存模型。你不能简单地"用一下 Behavior Tree"——你必须理解它如何嵌入 `AIController` → `BrainComponent` → `UBehaviorTreeComponent` 的完整调用链。

本节将解剖 UE Behavior Tree 系统的四层架构：

| 层次 | 核心类 | 职责 |
|------|--------|------|
| 资产层 | `UBehaviorTree`, `UBlackboardData` | 编辑器中创建的不可变资产（图结构、BB 键定义） |
| 节点层 | `UBTNode` → `UBTCompositeNode` / `UBTTaskNode` / `UBTDecorator` / `UBTService` | 行为图的节点类型系统 |
| 执行层 | `UBehaviorTreeComponent` | 资产实例化、Tick 驱动、节点内存管理、事件处理 |
| 宿主层 | `AAIController` → `UBrainComponent` | AI 控制器：行为树的宿主，提供感知/移动/Pawn 控制 |

理解这四个层次的分离，是正确使用 UE Behavior Tree 的前提。许多开发者遇到问题是因为混淆了资产（"这棵树长什么样"）和实例（"这棵树当前运行到哪了"）。

### 核心架构：从 AIController 到节点 Tick

```
AAIController::BeginPlay()
  └→ RunBehaviorTree(UBehaviorTree* BTAsset)
       └→ BrainComponent::StartTree(BTAsset)
            └→ UBehaviorTreeComponent::StartTree(BTAsset)
                 └→ 从资产实例化根节点
                      └→ 每帧 TickComponent():
                           └→ 从活动节点序列向下 Tick
                                ├→ Composite: 按顺序 Tick 子节点
                                ├→ Decorator: 在子节点之前/同时评估条件
                                ├→ Service: 在 Composite 作用域内后台 Tick
                                └→ Task: 执行具体行为，返回 InProgress/Succeeded/Failed
```

关键点：

1. **`UBehaviorTreeComponent` 是 `USceneComponent` 的直接子类**——不依赖 `UPrimitiveComponent`，没有物理开销。它通过 `TickComponent` 驱动树执行。
2. **`BrainComponent` 是中间层**，提供了 AI 逻辑的状态机（Start/Restart/Stop/Pause/Resume）。`UBehaviorTreeComponent` 是 `UBrainComponent` 的子类——它把 "BrainComponent 的状态机" 和 "Behavior Tree 的节点执行" 粘合在一起。
3. **一个 AIController 只跑一棵树**。如果需要切换行为树，调用 `RunBehaviorTree(NewAsset)` 即可——内部会清理旧实例、实例化新资产。
4. **Tick 是从根节点开始的自上而下搜索**：每帧从 `RootNode` 开始，遍历当前活动的 Composite 链条，直到找到活动 Leaf Task。不是整棵树都 Tick——只 Tick **活跃执行路径上的节点**。

### UBTNode 层次结构：四种节点类型的继承链

```
UObject
 └─ UBTNode (抽象基类)
      ├─ UBTCompositeNode (控制流)
      │    ├─ UBTComposite_Selector          // 依次尝试，成功即停
      │    ├─ UBTComposite_Sequence          // 依次执行，全部成功才成功
      │    └─ UBTComposite_SimpleParallel     // 主任务 + 后台子树的并行
      ├─ UBTTaskNode (叶子行为)
      │    ├─ UBTTask_MoveTo                 // 内置：移动
      │    ├─ UBTTask_RunBehavior            // 子行为树
      │    ├─ UBTTask_RunBehaviorDynamic     // 动态子行为树
      │    ├─ UBTTask_Wait                   // 等待 X 秒
      │    ├─ UBTTask_PlaySound              // 播放声音
      │    └─ UBTTask_BlueprintBase          // 蓝图可继承的 Task 基类
      ├─ UBTDecorator (条件守卫)
      │    ├─ UBTDecorator_Blackboard        // 检查 BB 键的值
      │    ├─ UBTDecorator_CompareBBEntries  // 比较两个 BB 键
      │    ├─ UBTDecorator_ConditionalLoop   // 循环：当条件为真
      │    ├─ UBTDecorator_Cooldown          // 冷却时间锁
      │    ├─ UBTDecorator_DoesPathExist     // 导航路径存在性
      │    ├─ UBTDecorator_ForceSuccess      // 强制分支成功
      │    ├─ UBTDecorator_KeepInCone        // 目标是否在锥形范围内
      │    ├─ UBTDecorator_Loop              // 循环 N 次
      │    ├─ UBTDecorator_ReachedMoveGoal   // 到达移动目标
      │    ├─ UBTDecorator_SetTagCooldown    // GameplayTag 冷却
      │    ├─ UBTDecorator_TagCooldown       // 检查 Tag 冷却状态
      │    ├─ UBTDecorator_TimeLimit         // 时间限制，超时强制失败
      │    └─ UBTDecorator_BlackboardBase    // BB 相关 Decorator 的基类
      └─ UBTService (后台持续运行)
           ├─ UBTService_DefaultFocus        // 自动设置 AI 视线聚焦
           ├─ UBTService_RunEQS              // 运行 EQS 查询
           └─ UBTService_BlueprintBase       // 蓝图可继承的 Service 基类
```

**每个节点类型有不同的生命周期契约**：

| 节点类型 | 生命周期阶段 | 关键虚函数 |
|----------|-------------|-----------|
| `UBTCompositeNode` | 进入 → Tick 子节点循环 → 子节点完成 → 退出 | `GetNextChildHandler`, `NotifyChildExecution` |
| `UBTTaskNode` | 激活 → 执行（可能是异步的）→ 完成 | `ExecuteTask`, `AbortTask`, `TickTask` |
| `UBTDecorator` | 在父节点激活时开始评估 → 持续评估（Observer 模式）→ 条件变化触发挥断 | `CalculateRawConditionValue`, `OnNodeActivation`, `OnNodeDeactivation` |
| `UBTService` | 在父 Composite 激活时开始 → 按间隔 Tick → 父 Composite 退出时停止 | `TickNode`, `OnSearchStart` |

### Blackboard 集成：数据与行为的分离

Tutorial 11 会深入 Blackboard 系统，但此处需要建立基本理解：

UE 的 Blackboard 实现了**行为与数据的分离**——这是行为树设计的关键原则。行为树节点不应该存储实体特定的数据（"当前目标是谁？"），这些数据应该存在 Blackboard 中。

```
UBlackboardData (资产，不可变)
 ├─ 定义 Key 的类型和名称
 │   ├─ BBKey_TargetActor    FBlackboardKeySelector (Object)
 │   ├─ BBKey_TargetLocation FBlackboardKeySelector (Vector)
 │   ├─ BBKey_IsAlerted      FBlackboardKeySelector (Bool)
 │   └─ BBKey_MoveSpeed      FBlackboardKeySelector (Float)
 │
UBlackboardComponent (实例，每个 AI 一个)
 ├─ 运行时存储每个 Key 的当前值
 └─ 值变更时触发 Observer 回调 → Behavior Tree 的 Event-Driven 机制
```

**FBlackboardKeySelector 的设计**：这是一个在编辑器中配置的元数据包装器。它在资产级别存储一个 Key 名称引用，在运行时通过 `GetSelectedBlackboardKey()` 转换为索引以高效查找。支持的类型包括：`Object`、`Class`、`Enum`、`Int`、`Float`、`Bool`、`Vector`、`Rotator`、`String`、`Name`。

关键 API：

```cpp
// 在 Task 中读取 BB 值
UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
AActor* Target = Cast<AActor>(BB->GetValueAsObject(TargetActorKey.SelectedKeyName));

// 在 Task 中写入 BB 值
BB->SetValueAsVector(TargetLocationKey.SelectedKeyName, NewLocation);
BB->SetValueAsBool(IsAlertedKey.SelectedKeyName, true);
```

### 编辑器资产工作流

UE Behavior Tree 的设计理念是"代码实现节点，编辑器组合行为"。标准工作流：

1. **定义 Blackboard 资产** (`.uasset`)：声明所有 Key 的名称和类型。这是 BT 和 AI Controller 之间的数据契约。
2. **编写 C++ 节点**：派生自 `UBTTaskNode`、`UBTDecorator`、`UBTService` 或 `UBTCompositeNode`，实现具体逻辑。
3. **创建 Behavior Tree 资产** (`.uasset`)：在 BT Editor 中将节点拖拽到图中，配置 Decorator/Service 的附件关系。
4. **在 AIController 中启动**：

```cpp
void AMyAIController::BeginPlay()
{
    Super::BeginPlay();
    RunBehaviorTree(BehaviorTreeAsset);  // UPROPERTY(EditDefaultsOnly) 配置
}
```

节点在编辑器中有三个重要的显示元素：
- **Node Name**：节点的显示名称（可通过覆写 `GetNodeName()` 自定义）
- **Static Description**：节点在编辑器中的静态描述（覆写 `GetStaticDescription()`），帮助设计师理解节点功能
- **Runtime Description**：运行时的动态描述——但在编辑器中不可见

### UBehaviorTreeComponent 内存模型

这是面试中高频出现的深度问题。UE Behavior Tree 的内存管理机制是它与大多数自研行为树系统的核心差异：

1. **节点实例化**：当你调用 `StartTree(Asset)` 时，`UBehaviorTreeComponent` 会遍历资产中的每一个节点，为每个节点分配**实例内存**。这意味着即使两个 AI 运行同一棵行为树，它们各自拥有独立的节点实例数据。

2. **`AllocateNodeMemory` 模式**：节点不应将运行时状态存储为 C++ 成员变量（因为节点对象本身从资产复制而来）。而是覆写 `GetNodeMemorySize()` + `InitializeMemory()` + `CleanupMemory()` 来管理每实例数据：

```cpp
// 自定义 Task 的每实例数据结构
struct FMyTaskMemory
{
    float ElapsedTime;
    int32 AttemptCount;
    AActor* CachedTarget;  // 弱引用还是原始指针？看下文
};

// 在 Task 类中
virtual uint16 GetInstanceMemorySize() const override
{
    return sizeof(FMyTaskMemory);
}

virtual void InitializeMemory(UBehaviorTreeComponent& OwnerComp,
    uint8* NodeMemory, EBTMemoryInit::Type InitType) const override
{
    // 只在首次初始化时设置
    if (InitType == EBTMemoryInit::Initialize)
    {
        FMyTaskMemory* MyMemory = reinterpret_cast<FMyTaskMemory*>(NodeMemory);
        new(MyMemory) FMyTaskMemory();  // placement new
    }
}
```

3. **子树实例化（Subtree Instancing）**：当 BT 中使用 `RunBehavior` Task 引用另一个 BT 资产时，子树的节点也会被完整实例化，纳入父 `UBehaviorTreeComponent` 的实例树中。这不是"引用"——是真正的"展开"。对内存的直接影响：包含深层子树的 BT 资产会消耗更多每实体内存。

4. **节点内存是连续分配的一大块**：`UBehaviorTreeComponent` 分配一块连续内存来存放所有节点的实例数据，通过节点在资产中的索引做偏移访问。这种设计对于缓存友好性极好，100+ 节点的树也只是一个 allocation。

### Event-Driven 机制：Observer Abort

Gameplay 中最影响 AI 响应速度的设计是 **Observer Abort**。

传统轮询模式：每个 Task 必须在自己的 `TickTask` 中检查"条件是否还满足"，不满足时返回 `Failed`。问题：Task 的实现者必须记住做这个检查，且检查频率受限。

Observer Abort 模式：Decorator 可以注册为特定 Blackboard Key 的观察者。当该 Key 的值发生变化时，`UBlackboardComponent` 立即通知 Decorator → Decorator 重新评估条件 → 如果条件不再满足，Decorator 触发所在分支的 abort。

```cpp
// 在 Decorator 构造中注册 Observer
UBTDecorator_HasAmmo::UBTDecorator_HasAmmo()
{
    bNotifyBecomeRelevant = true;   // 节点激活时通知
    bNotifyCeaseRelevant = true;    // 节点取消时通知
    FlowAbortMode = EBTFlowAbortMode::Self;  // 条件变化时 abort 自己
}
```

三种 FlowAbortMode：
- `None`：不触发 abort——轮询模式
- `Self`：当条件变为 false 时，abort 自身所在的分支（该 Decorator 及其兄弟节点）
- `LowerPriority`：当条件变为 true 时，abort 优先级更低的分支——用于"更高优先级行为抢断"场景（如"受到伤害 → 中断 Patrol 进入 Flee"）
- `Both`：同时启用 Self 和 LowerPriority

---

## 2. 代码示例

> 以下代码基于 UE 5.3+ API。所有示例都是完整可编译的 C++ 类，包含头文件和实现文件。

### 示例 A: 自定义 BTTask —— UBTTask_FindPlayerLocation

**目的**：使用 AI Perception 查找玩家，将结果位置写入 Blackboard。展示 ExecuteTask 的完整生命周期，包括异步完成和 abort 处理。

```cpp
// BTFindPlayerLocation.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Tasks/BTTask_BlackboardBase.h"
#include "BTFindPlayerLocation.generated.h"

/**
 * Task that uses AI Perception to locate the player and writes the position
 * to a Blackboard Vector key. If no player is sensed, the task fails after
 * a configurable timeout.
 */
UCLASS()
class UBTTask_FindPlayerLocation : public UBTTask_BlackboardBase
{
    GENERATED_BODY()

public:
    UBTTask_FindPlayerLocation();

    /** If no player is sensed within this time, the task fails. */
    UPROPERTY(EditAnywhere, Category = "Search",
        meta = (ClampMin = "0.1", ClampMax = "30.0"))
    float SearchTimeout = 5.0f;

    /** Radius around last known location to consider as "found". */
    UPROPERTY(EditAnywhere, Category = "Search",
        meta = (ClampMin = "0.0"))
    float AcceptanceRadius = 100.0f;

protected:
    virtual EBTNodeResult::Type ExecuteTask(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;
    virtual EBTNodeResult::Type AbortTask(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;
    virtual void TickTask(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;
    virtual uint16 GetInstanceMemorySize() const override;

    virtual FString GetStaticDescription() const override;
};

// Per-instance runtime data
struct FBTFindPlayerLocationMemory
{
    float TimeRemaining;
    uint8 bRequestedAbort : 1;
};
```

```cpp
// BTFindPlayerLocation.cpp
#include "BTFindPlayerLocation.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"
#include "Perception/AIPerceptionComponent.h"
#include "Perception/AISense_Sight.h"

UBTTask_FindPlayerLocation::UBTTask_FindPlayerLocation()
{
    NodeName = TEXT("Find Player Location");

    // Accept only Vector keys — designer can't accidentally select a Bool key
    BlackboardKey.AddVectorFilter(this, GET_MEMBER_NAME_CHECKED(
        UBTTask_FindPlayerLocation, BlackboardKey));
}

EBTNodeResult::Type UBTTask_FindPlayerLocation::ExecuteTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    FBTFindPlayerLocationMemory* MyMemory =
        reinterpret_cast<FBTFindPlayerLocationMemory*>(NodeMemory);
    MyMemory->TimeRemaining = SearchTimeout;
    MyMemory->bRequestedAbort = false;

    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController)
    {
        return EBTNodeResult::Failed;
    }

    // Check perception immediately — don't wait for a tick
    UAIPerceptionComponent* PerceptionComp =
        AIController->GetPerceptionComponent();
    if (!PerceptionComp)
    {
        return EBTNodeResult::Failed;
    }

    TArray<AActor*> PerceivedActors;
    PerceptionComp->GetCurrentlyPerceivedActors(
        UAISense_Sight::StaticClass(), PerceivedActors);

    for (AActor* Actor : PerceivedActors)
    {
        if (Actor && Actor->ActorHasTag(FName("Player")))
        {
            // Found immediately — write to BB and succeed
            OwnerComp.GetBlackboardComponent()->SetValueAsVector(
                BlackboardKey.SelectedKeyName, Actor->GetActorLocation());
            return EBTNodeResult::Succeeded;
        }
    }

    // No player perceived — go latent; TickTask will poll
    return EBTNodeResult::InProgress;
}

void UBTTask_FindPlayerLocation::TickTask(UBehaviorTreeComponent& OwnerComp,
    uint8* NodeMemory, float DeltaSeconds)
{
    FBTFindPlayerLocationMemory* MyMemory =
        reinterpret_cast<FBTFindPlayerLocationMemory*>(NodeMemory);

    MyMemory->TimeRemaining -= DeltaSeconds;
    if (MyMemory->TimeRemaining <= 0.0f)
    {
        // FailSafe: if we haven't gotten an abort notification but timeout expired,
        // use FinishLatentTask since the task became InProgress in ExecuteTask.
        FinishLatentTask(OwnerComp, EBTNodeResult::Failed);
        return;
    }

    // Poll perception every tick while latent
    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return;

    UAIPerceptionComponent* PerceptionComp =
        AIController->GetPerceptionComponent();
    if (!PerceptionComp) return;

    TArray<AActor*> PerceivedActors;
    PerceptionComp->GetCurrentlyPerceivedActors(
        UAISense_Sight::StaticClass(), PerceivedActors);

    for (AActor* Actor : PerceivedActors)
    {
        if (Actor && Actor->ActorHasTag(FName("Player")))
        {
            OwnerComp.GetBlackboardComponent()->SetValueAsVector(
                BlackboardKey.SelectedKeyName, Actor->GetActorLocation());
            FinishLatentTask(OwnerComp, EBTNodeResult::Succeeded);
            return;
        }
    }
}

EBTNodeResult::Type UBTTask_FindPlayerLocation::AbortTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    // Called when a higher-priority Decorator triggers an abort.
    // No FinishLatentTask needed here — the engine handles cleanup.
    FBTFindPlayerLocationMemory* MyMemory =
        reinterpret_cast<FBTFindPlayerLocationMemory*>(NodeMemory);
    MyMemory->bRequestedAbort = true;
    return EBTNodeResult::Aborted;
}

uint16 UBTTask_FindPlayerLocation::GetInstanceMemorySize() const
{
    return sizeof(FBTFindPlayerLocationMemory);
}

FString UBTTask_FindPlayerLocation::GetStaticDescription() const
{
    return FString::Printf(TEXT("%s: search for player via sight sense\n"
        "Timeout: %.1fs  AcceptRadius: %.0f"),
        *Super::GetStaticDescription(), SearchTimeout, AcceptanceRadius);
}
```

**关键要点**：
- 使用 `UBTTask_BlackboardBase` 而非 `UBTTaskNode`，自动获得 Blackboard Key Selector 配置
- 在构造函数中调用 `AddVectorFilter` 限制选中 Key 类型——编辑器层面防止配置错误
- `ExecuteTask` 可以返回 `InProgress` 以进入异步模式。此时必须通过 `FinishLatentTask` 收尾
- `AbortTask` 中**不要调用 `FinishLatentTask`**——引擎在 abort 自己时会做清理
- `GetInstanceMemorySize` 提供每实例内存大小，内存由 `UBehaviorTreeComponent` 连续分配

### 示例 B: 自定义 BTDecorator —— UBTDecorator_HasAmmo

**目的**：检查 AI 是否有弹药，支持 Observer Abort 在弹药变化时立即响应。

```cpp
// BTDecorator_HasAmmo.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/BTDecorator.h"
#include "BTDecorator_HasAmmo.generated.h"

/**
 * Decorator that checks whether the controlled AI has remaining ammo.
 * Registers as an Observer on the AmmoCount Blackboard key so that
 * ammo changes trigger immediate re-evaluation.
 */
UCLASS()
class UBTDecorator_HasAmmo : public UBTDecorator
{
    GENERATED_BODY()

public:
    UBTDecorator_HasAmmo();

    /** The Blackboard key storing the current ammo count. */
    UPROPERTY(EditAnywhere, Category = "Condition")
    FBlackboardKeySelector AmmoKey;

    /** Minimum ammo required for this decorator to pass. */
    UPROPERTY(EditAnywhere, Category = "Condition",
        meta = (ClampMin = "0"))
    int32 MinAmmo = 1;

protected:
    virtual bool CalculateRawConditionValue(
        UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const override;

    virtual void OnNodeActivation(FBehaviorTreeSearchData& SearchData) override;
    virtual void OnNodeDeactivation(
        FBehaviorTreeSearchData& SearchData, EBTNodeResult::Type NodeResult) override;

    virtual FString GetStaticDescription() const override;

#if WITH_EDITOR
    virtual FName GetNodeIconName() const override;
#endif

private:
    /** Called when the observed Blackboard key's value changes. */
    UFUNCTION()
    void OnBlackboardKeyChanged(const UBlackboardComponent& BlackboardComp,
        FBlackboard::FKey ChangedKeyID);

    void RegisterObserver(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory);
    void UnregisterObserver(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory);
};

struct FBTDecorator_HasAmmoMemory
{
    FDelegateHandle ObserverHandle;
};
```

```cpp
// BTDecorator_HasAmmo.cpp
#include "BTDecorator_HasAmmo.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"

UBTDecorator_HasAmmo::UBTDecorator_HasAmmo()
{
    NodeName = TEXT("Has Ammo");

    AmmoKey.AddIntFilter(this,
        GET_MEMBER_NAME_CHECKED(UBTDecorator_HasAmmo, AmmoKey));

    // === THIS IS THE KEY TO OBSERVER ABORT ===
    // Without bNotifyBecomeRelevant, OnNodeActivation is never called.
    bNotifyBecomeRelevant = true;
    bNotifyCeaseRelevant = true;

    // Self: when this decorator's condition becomes false, abort the
    // branch it's guarding (e.g., stop attacking when out of ammo).
    FlowAbortMode = EBTFlowAbortMode::Self;
}

bool UBTDecorator_HasAmmo::CalculateRawConditionValue(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
{
    const UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB || !AmmoKey.IsSet()) return false;

    const int32 CurrentAmmo = BB->GetValueAsInt(AmmoKey.SelectedKeyName);
    return CurrentAmmo >= MinAmmo;
}

void UBTDecorator_HasAmmo::OnNodeActivation(
    FBehaviorTreeSearchData& SearchData)
{
    Super::OnNodeActivation(SearchData);
    RegisterObserver(SearchData.OwnerComp,
        GetNodeMemory<uint8>(SearchData));
}

void UBTDecorator_HasAmmo::OnNodeDeactivation(
    FBehaviorTreeSearchData& SearchData, EBTNodeResult::Type NodeResult)
{
    UnregisterObserver(SearchData.OwnerComp,
        GetNodeMemory<uint8>(SearchData));
    Super::OnNodeDeactivation(SearchData, NodeResult);
}

void UBTDecorator_HasAmmo::RegisterObserver(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return;

    FBTDecorator_HasAmmoMemory* MyMemory =
        reinterpret_cast<FBTDecorator_HasAmmoMemory*>(NodeMemory);

    FOnBlackboardChangeNotification Delegate =
        FOnBlackboardChangeNotification::CreateUObject(
            this, &UBTDecorator_HasAmmo::OnBlackboardKeyChanged);

    MyMemory->ObserverHandle = BB->RegisterObserver(
        AmmoKey.GetSelectedKeyID(), this, Delegate);
}

void UBTDecorator_HasAmmo::UnregisterObserver(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return;

    FBTDecorator_HasAmmoMemory* MyMemory =
        reinterpret_cast<FBTDecorator_HasAmmoMemory*>(NodeMemory);

    BB->UnregisterObserver(AmmoKey.GetSelectedKeyID(),
        MyMemory->ObserverHandle);
}

// Returning EBlackboardNotificationResult::RemoveObserver causes the
// observer to be removed after the first notification. We want persistent
// observation, so return ContinueObserving.
EBlackboardNotificationResult UBTDecorator_HasAmmo::OnBlackboardKeyChanged(
    const UBlackboardComponent& BlackboardComp, FBlackboard::FKey ChangedKeyID)
{
    // The engine will call ConditionChanged on the BehaviorTreeComponent,
    // which triggers re-evaluation of this and surrounding decorators.
    // We return ContinueObserving so the observer persists.
    return EBlackboardNotificationResult::ContinueObserving;
}

FString UBTDecorator_HasAmmo::GetStaticDescription() const
{
    return FString::Printf(TEXT("%s >= %d"),
        *AmmoKey.SelectedKeyName.ToString(), MinAmmo);
}

#if WITH_EDITOR
FName UBTDecorator_HasAmmo::GetNodeIconName() const
{
    return FName("BTEditor.Graph.BTNode.Decorator.Conditional.Icon");
}
#endif
```

**关键要点**：
- `bNotifyBecomeRelevant` 是 Observer Abort 的开关——不设这个，`OnNodeActivation` 不会被调用
- `FlowAbortMode::Self` 表示"条件变 false 时 abort 所在分支"
- `RegisterObserver` 返回的 `FDelegateHandle` 必须保存以在 `OnNodeDeactivation` 中正确注销
- `OnBlackboardKeyChanged` 返回 `ContinueObserving` 保证持续监听
- **不要**在 `OnBlackboardKeyChanged` 回调中直接做重计算或调用 `FinishLatentTask`——只做标记。引擎的 `ConditionChanged` 会统一调度重新评估

### 示例 C: 自定义 BTService —— UBTService_UpdatePlayerDistance

**目的**：每 0.5 秒更新 Blackboard 中的距离 Key。展示 Service 的正确间隔配置和 `TickNode` 实现。

```cpp
// BTService_UpdatePlayerDistance.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/BTService.h"
#include "BTService_UpdatePlayerDistance.generated.h"

/**
 * Service that periodically calculates the distance from the AI to the player
 * and writes it to a Blackboard Float key. Runs at a configurable interval
 * while its parent Composite is active.
 */
UCLASS()
class UBTService_UpdatePlayerDistance : public UBTService
{
    GENERATED_BODY()

public:
    UBTService_UpdatePlayerDistance();

    /** Blackboard key for the player actor reference. */
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector PlayerActorKey;

    /** Blackboard key where the calculated distance is written. */
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector DistanceKey;

    /** If true, also write the squared distance for cheaper comparisons. */
    UPROPERTY(EditAnywhere, Category = "Blackboard")
    bool bWriteSquaredDistance = false;

    /** Blackboard key for squared distance (only used if bWriteSquaredDistance is true). */
    UPROPERTY(EditAnywhere, Category = "Blackboard",
        meta = (EditCondition = "bWriteSquaredDistance"))
    FBlackboardKeySelector SquaredDistanceKey;

protected:
    virtual void TickNode(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;

    virtual FString GetStaticDescription() const override;
};
```

```cpp
// BTService_UpdatePlayerDistance.cpp
#include "BTService_UpdatePlayerDistance.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"
#include "GameFramework/Actor.h"

UBTService_UpdatePlayerDistance::UBTService_UpdatePlayerDistance()
{
    NodeName = TEXT("Update Player Distance");

    // Service tick interval — 0.5s is a reasonable default for AI distance checks.
    // Lower values cost more CPU; higher values reduce responsiveness.
    Interval = 0.5f;
    RandomDeviation = 0.05f;  // slight stagger to avoid phasing with other AIs

    PlayerActorKey.AddObjectFilter(this,
        GET_MEMBER_NAME_CHECKED(UBTService_UpdatePlayerDistance, PlayerActorKey),
        AActor::StaticClass());

    DistanceKey.AddFloatFilter(this,
        GET_MEMBER_NAME_CHECKED(UBTService_UpdatePlayerDistance, DistanceKey));

    SquaredDistanceKey.AddFloatFilter(this,
        GET_MEMBER_NAME_CHECKED(UBTService_UpdatePlayerDistance, SquaredDistanceKey));
}

void UBTService_UpdatePlayerDistance::TickNode(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds)
{
    Super::TickNode(OwnerComp, NodeMemory, DeltaSeconds);

    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return;

    AActor* PlayerActor = Cast<AActor>(
        BB->GetValueAsObject(PlayerActorKey.SelectedKeyName));
    if (!PlayerActor) return;

    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return;

    APawn* ControlledPawn = AIController->GetPawn();
    if (!ControlledPawn) return;

    const FVector AILocation = ControlledPawn->GetActorLocation();
    const FVector PlayerLocation = PlayerActor->GetActorLocation();

    const float DistSq = FVector::DistSquared(AILocation, PlayerLocation);
    BB->SetValueAsFloat(DistanceKey.SelectedKeyName,
        FMath::Sqrt(DistSq));

    if (bWriteSquaredDistance)
    {
        BB->SetValueAsFloat(SquaredDistanceKey.SelectedKeyName, DistSq);
    }
}

FString UBTService_UpdatePlayerDistance::GetStaticDescription() const
{
    return FString::Printf(TEXT("Every %.2fs (±%.2fs): calc |%s → %s|"),
        Interval, RandomDeviation,
        *PlayerActorKey.SelectedKeyName.ToString(),
        *DistanceKey.SelectedKeyName.ToString());
}
```

**关键要点**：
- `Interval` 和 `RandomDeviation` 是 `UBTService` 的内置属性——不需要自己管理 Timer
- `RandomDeviation` 至关重要：如果 200 个 AI 同时 Tick Service，它们会在一帧内同时执行 `GetActorLocation` 和 `DistSquared`，造成 CPU 尖峰。随机偏差将这些计算分散到不同帧
- Service 的 `TickNode` 不返回执行结果（它是后台运行的，不影响树流控）
- Service 自动随父 Composite 的激活/取消而启动/停止——无需手动生命周期管理

### 示例 D: 自定义 BTComposite —— UBTComposite_RandomSelector

**目的**：从有效子节点中随机选择一个执行，而不是顺序尝试。展示 Composite 的 `GetNextChildHandler` 实现。

```cpp
// BTComposite_RandomSelector.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/BTCompositeNode.h"
#include "BTComposite_RandomSelector.generated.h"

/**
 * Composite that picks a random child from among those whose Decorators pass,
 * then executes only that child. If the child fails, the Composite fails
 * (does NOT try another child — this is "pick one", not "pick until one succeeds").
 */
UCLASS()
class UBTComposite_RandomSelector : public UBTCompositeNode
{
    GENERATED_BODY()

public:
    UBTComposite_RandomSelector();

protected:
    virtual int32 GetNextChildHandler(FBehaviorTreeSearchData& SearchData,
        int32 PrevChild, EBTNodeResult::Type LastResult) const override;

    virtual FString GetStaticDescription() const override;

#if WITH_EDITOR
    virtual bool CanAbortLowerPriority() const override;
    virtual bool CanAbortSelf() const override;
#endif
};
```

```cpp
// BTComposite_RandomSelector.cpp
#include "BTComposite_RandomSelector.h"

UBTComposite_RandomSelector::UBTComposite_RandomSelector()
{
    NodeName = TEXT("Random Selector");
    // Allow both Self and LowerPriority aborts so Decorators on children
    // (or on this Composite itself) can interrupt.
    bUseChildExecutionNotify = false;
}

int32 UBTComposite_RandomSelector::GetNextChildHandler(
    FBehaviorTreeSearchData& SearchData, int32 PrevChild,
    EBTNodeResult::Type LastResult) const
{
    // On first entry (PrevChild == BTSpecialChild::NotInitialized):
    // pick a random child whose decorators pass.
    if (PrevChild == BTSpecialChild::NotInitialized)
    {
        // Collect all children whose decorators currently pass
        TArray<int32> ValidChildren;
        const int32 NumChildren = GetChildrenNum();

        for (int32 i = 0; i < NumChildren; ++i)
        {
            // DoDecoratorCheck returns true if all decorators on this child pass
            if (DoDecoratorCheck(SearchData, i))
            {
                ValidChildren.Add(i);
            }
        }

        if (ValidChildren.Num() == 0)
        {
            return BTSpecialChild::ReturnToParent;
        }

        // Pick random valid child
        const int32 RandomIndex = FMath::RandRange(0, ValidChildren.Num() - 1);
        return ValidChildren[RandomIndex];
    }

    // After the chosen child finishes (regardless of Succeeded or Failed),
    // return to parent — we don't try another child.
    return BTSpecialChild::ReturnToParent;
}

FString UBTComposite_RandomSelector::GetStaticDescription() const
{
    return TEXT("Random Selector: picks one random child whose decorators pass");
}

#if WITH_EDITOR
bool UBTComposite_RandomSelector::CanAbortLowerPriority() const
{
    return true;
}

bool UBTComposite_RandomSelector::CanAbortSelf() const
{
    return true;
}
#endif
```

**关键要点**：
- `PrevChild == BTSpecialChild::NotInitialized` 标记第一次进入——类比 Iterator 的"还没开始"
- `BTSpecialChild::ReturnToParent` 通知父节点当前 Composite 执行完毕
- `DoDecoratorCheck(SearchData, ChildIndex)` 是 Composite 的关键 API——检查某个子节点的所有 Decorator 是否通过
- `CanAbortLowerPriority` / `CanAbortSelf` 在 `#if WITH_EDITOR` 中覆写，控制编辑器中 Abort 模式的可用选项

### 在编辑器中连接一切

创建完 C++ 类后，在编辑器中组装行为树的标准流程：

1. **创建 Blackboard 资产** (`Content/AI/BB_Enemy`): 添加 Key: `TargetActor` (Object), `TargetLocation` (Vector), `PlayerDistance` (Float), `AmmoCount` (Int), `IsAlerted` (Bool)
2. **创建 Behavior Tree 资产** (`Content/AI/BT_Enemy`): 将 Blackboard 资产关联到 BT
3. **组装节点图**：拖拽 `UBTComposite_RandomSelector` 到根节点 → 在子节点槽位上添加 `UBTTask_FindPlayerLocation` → 附加 `UBTDecorator_HasAmmo` 到相关分支 → 在 Composite 上附加 `UBTService_UpdatePlayerDistance`
4. **在 AIController 中注册**：

```cpp
UPROPERTY(EditDefaultsOnly, Category = "AI")
UBehaviorTree* BehaviorTreeAsset;

void AMyAIController::BeginPlay()
{
    Super::BeginPlay();
    if (BehaviorTreeAsset)
    {
        RunBehaviorTree(BehaviorTreeAsset);
    }
}
```

---

## 3. 练习

### 练习 1: 完整敌人 AI 行为树

**目标**：使用自定义 Task、Decorator、Service 搭建一个完整的六行为敌人 AI。

**行为流程**：`巡逻(Patrol) → 发现玩家(Detect) → 追击(Chase) → 攻击(Attack) → 丢失目标(LoseTarget) → 返回巡逻(Return)`

**要求**：

1. **创建 Blackboard Keys**（先定义契约）：`TargetActor` (Object), `TargetLocation` (Vector), `PlayerDistance` (Float), `AmmoCount` (Int), `IsAlerted` (Bool), `PatrolIndex` (Int), `HomeLocation` (Vector)

2. **实现自定义 BBTTask**：
   - `UBTTask_PatrolToNextWaypoint`：读取 `PatrolIndex`，将 AI 移动到数组中的下一个路径点，到达后递增索引并写入 BB。如果路径点数组为空或遍历完成，从头循环。
   - `UBTTask_ChaseTarget`：读 `TargetActor`，使用 `AIController->MoveToActor()` 向目标移动。每 0.3 秒更新目标位置（通过覆写 `TickTask`）。如果到达 `AcceptanceRadius` 内，返回 Succeeded。

3. **实现自定义 BTDecorator**：
   - `UBTDecorator_IsInRange`：比较 `PlayerDistance`（由 Service 更新）与配置的 `MinRange`/`MaxRange`。用于"攻击范围"和"追击范围"的判定。支持 Observer Abort。

4. **实现自定义 BTService**：
   - `UBTService_UpdateTargetData`：从 AI Perception 获取当前感知到的玩家，更新 `TargetActor` 和 `TargetLocation`。如果玩家丢失（不再感知到），设置 `IsAlerted = false`。

5. **在编辑器中组装**：
   - 顶层 Selector：`Detect → ChaseSequence → Patrol`
   - `Detect` 分支：`[Decorator: IsNotAlerted] → FindPlayerLocation → SetAlertedTrue`
   - `ChaseSequence` 嵌套 Selector：`Attack [Decorator: IsInRange(0, 300)] → Chase [Decorator: IsInRange(300, 2000)] → LoseTarget`
   - `Patrol` 序列：`PatrolToNextWaypoint → Wait(2s) → Loop`

6. **验证**：在模拟中逐步验证：AI 创建后是否开始巡逻？玩家进入感知范围是否切换到追击？追击到攻击距离是否开火？玩家跑出范围是否追击？跑出追击范围是否回到巡逻？

---

### 练习 2: Observer Abort 响应式 AI

**目标**：在练习 1 的基础上，添加 Observer Abort 让 AI **立即响应**环境变化，不等待当前 Task 执行完成。

**场景**：当前 AI 正在执行 `PatrolToNextWaypoint`（需要 5 秒到达路径点）。中途玩家进入感知范围——AI 应该**立即中断巡逻**进入追击，而不是走完 5 秒。

**要求**：

1. **在 `Detect` 分支的 Decorator 上设置 Observer Abort**：
   - `UBTDecorator_IsNotAlerted` 监听 `IsAlerted` Key，设置 `FlowAbortMode = LowerPriority`。当 `IsAlerted` 变为 true 时，中断低优先级分支（Patrol）。
   - `UBTDecorator_IsInRange` 监听 `PlayerDistance` Key，配置合适的 `FlowAbortMode`。当玩家进入攻击范围时，`Attack` 分支（Self Abort Chase）、当玩家跑出追击范围时，`Chase` 分支（Self Abort Chase 转而触发 LoseTarget）。

2. **验证 Observer Abort 的行为**：
   - 在 `AbortTask` 中添加 `UE_LOG`，确认被正确触发。
   - 测试 "巡逻中玩家出现 → 立即切换" 的延迟。Observer Abort 应该在同一帧内响应（因为 Blackboard 的 `OnValueChanged` 是同步触发的）。
   - 测试边界：玩家在 AI 的感知边界快速闪烁（进出进出），确认不会触发无限 abort 循环（引擎内部有冷却机制）。

3. **回答以下问题**：
   - 如果你把 `FlowAbortMode` 设为 `Both` 而不是 `Self` 或 `LowerPriority`，行为上会有什么差异？
   - Observer Abort 触发的 `AbortTask` 调用链是什么？从 `UBlackboardComponent::OnValueChanged` 开始，画出调用栈（函数名和顺序）。
   - 在什么场景下 Observer Abort 会导致行为树"抖动"（在 Patrol 和 Chase 之间快速来回切换），如何修复？

---

### 练习 3: 群组 AI 通过共享 Blackboard 协调（可选）

**目标**：实现多个 AI 通过共享 Blackboard 值进行协同，展示 Blackboard 的数据共享能力。

**场景**：三个 AI 守卫巡逻同一个区域。当一个守卫发现玩家后，通过共享 Blackboard 的 `TargetLocation` 通知其他守卫，实现群组响应。

**要求**：

1. **共享 Blackboard 策略**：创建一个 `ASharedBlackboardManager` Actor，它持有一个 `UBlackboardComponent`。每个 AI Controller 在 `BeginPlay` 中获取该 Manager 的 BB Component 引用，用于读取共享数据。
   - 注意：`UBlackboardComponent` 的 `SetValueAs*` 支持跨 AI 读取，但写入必须谨慎——谁有权限写？使用 `AuthorityOnly` 标记或只在 Server 端写入。

2. **自定义 Service: `UBTService_CheckGroupAlert`**：检查共享 BB 上的 `bGroupAlerted` Key。如果为 true 且自身 `IsAlerted` 为 false，进入"支援"行为分支。

3. **自定义 Task: `UBTTask_FlankTarget`**：读取 `TargetActor` 的当前位置，计算一个侧面位置（目标位置的左侧或右侧 45° 偏移 400 单位），使用 `AIController->MoveToLocation()` 移动。与 `UBTTask_ChaseTarget` 区分——不是直接冲向目标，而是绕侧。

4. **行为树结构**：顶层 Selector：
   - `GroupAlert [Decorator: IsGroupAlerted] → FlankTarget`
   - `SelfAlert [Decorator: IsAlerted] → Chase → Attack`
   - `Patrol`

5. **验证**：放置三个 AI 守卫和一个玩家。确认：
   - 玩家进入任何一个守卫的感知范围 → 该守卫追击 → 其他守卫通过共享 BB 感知到警报 → 支援。
   - 三个守卫从不同方向接近玩家（直追 + 两个侧翼）。
   - 玩家消灭所有守卫后，新生成的守卫恢复巡逻。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 以下是完整敌人 AI 行为树的核心 C++ 实现参考。注意：编辑器中的树结构组装描述见代码后的树形图。
>
> **Blackboard Keys（在 UBlackboardData 资产中定义）**：
> - `TargetActor` (Object)、`TargetLocation` (Vector)、`PlayerDistance` (Float)
> - `AmmoCount` (Int)、`IsAlerted` (Bool)、`PatrolIndex` (Int)、`HomeLocation` (Vector)
>
> **UBTTask_PatrolToNextWaypoint.h**：
> ```cpp
> #pragma once
> #include "BehaviorTree/Tasks/BTTask_BlackboardBase.h"
> #include "BTTask_PatrolToNextWaypoint.generated.h"
>
> UCLASS()
> class UBTTask_PatrolToNextWaypoint : public UBTTask_BlackboardBase
> {
>     GENERATED_BODY()
> public:
>     UBTTask_PatrolToNextWaypoint();
>     UPROPERTY(EditAnywhere, Category = "Patrol")
>     TArray<FVector> Waypoints; // 在编辑器中配置路径点
>     UPROPERTY(EditAnywhere, Category = "Patrol", meta = (ClampMin = "1.0"))
>     float AcceptanceRadius = 100.0f;
> protected:
>     virtual EBTNodeResult::Type ExecuteTask(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) override;
>     virtual void TickTask(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds) override;
>     virtual uint16 GetInstanceMemorySize() const override;
> };
> struct FPatrolMemory { float WaitTimer; bool bWaiting; };
> ```
>
> **UBTTask_PatrolToNextWaypoint.cpp**：
> ```cpp
> UBTTask_PatrolToNextWaypoint::UBTTask_PatrolToNextWaypoint()
> {
>     NodeName = TEXT("Patrol To Next Waypoint");
>     BlackboardKey.AddIntFilter(this, GET_MEMBER_NAME_CHECKED(UBTTask_PatrolToNextWaypoint, BlackboardKey));
> }
>
> EBTNodeResult::Type UBTTask_PatrolToNextWaypoint::ExecuteTask(
>     UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
> {
>     auto* BB = OwnerComp.GetBlackboardComponent();
>     int32 Index = BB->GetValueAsInt(BlackboardKey.SelectedKeyName);
>     if (Waypoints.Num() == 0) return EBTNodeResult::Failed;
>     // 循环路径点
>     Index = Index % Waypoints.Num();
>     BB->SetValueAsInt(BlackboardKey.SelectedKeyName, Index);
>     // 发起移动
>     AAIController* AI = OwnerComp.GetAIOwner();
>     AI->MoveToLocation(Waypoints[Index], AcceptanceRadius);
>     return EBTNodeResult::Succeeded; // MoveTo 是异步的，由 MoveTo Task 内部处理
>     // 注意：实际项目应使用 UAIBlueprintHelperLibrary::CreateMoveToProxyObject
>     // 或覆写 TickTask 等待到达
> }
>
> uint16 UBTTask_PatrolToNextWaypoint::GetInstanceMemorySize() const { return sizeof(FPatrolMemory); }
> ```
>
> **UBTTask_ChaseTarget** — 核心逻辑在 TickTask 中每 0.3s 更新目标位置：
> ```cpp
> void UBTTask_ChaseTarget::TickTask(UBehaviorTreeComponent& OwnerComp,
>     uint8* NodeMemory, float DeltaSeconds)
> {
>     auto* BB = OwnerComp.GetBlackboardComponent();
>     AActor* Target = Cast<AActor>(BB->GetValueAsObject(TargetActorKey.SelectedKeyName));
>     if (!Target) { FinishLatentTask(OwnerComp, EBTNodeResult::Failed); return; }
>     float Dist = FVector::Dist(OwnerComp.GetAIOwner()->GetPawn()->GetActorLocation(),
>                                Target->GetActorLocation());
>     BB->SetValueAsFloat(PlayerDistanceKey.SelectedKeyName, Dist);
>     if (Dist <= AcceptanceRadius) { FinishLatentTask(OwnerComp, EBTNodeResult::Succeeded); return; }
>     // 每 0.3s 更新一次移动目标
>     FChaseMemory* Mem = reinterpret_cast<FChaseMemory*>(NodeMemory);
>     Mem->UpdateTimer -= DeltaSeconds;
>     if (Mem->UpdateTimer <= 0.0f)
>     {
>         OwnerComp.GetAIOwner()->MoveToActor(Target, AcceptanceRadius * 0.8f);
>         Mem->UpdateTimer = 0.3f;
>     }
> }
> ```
>
> **UBTDecorator_IsInRange**：
> ```cpp
> bool UBTDecorator_IsInRange::CalculateRawConditionValue(
>     UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
> {
>     float Dist = OwnerComp.GetBlackboardComponent()->GetValueAsFloat(DistanceKey.SelectedKeyName);
>     return Dist >= MinRange && Dist <= MaxRange;
> }
> ```
>
> **UBTService_UpdateTargetData**：
> ```cpp
> void UBTService_UpdateTargetData::TickNode(UBehaviorTreeComponent& OwnerComp,
>     uint8* NodeMemory, float DeltaSeconds)
> {
>     auto* BB = OwnerComp.GetBlackboardComponent();
>     auto* PerceptionComp = OwnerComp.GetAIOwner()->GetPerceptionComponent();
>     TArray<AActor*> Perceived;
>     PerceptionComp->GetCurrentlyPerceivedActors(UAISense_Sight::StaticClass(), Perceived);
>     AActor* Player = nullptr;
>     for (AActor* A : Perceived) { if (A->ActorHasTag("Player")) { Player = A; break; } }
>     if (Player)
>     {
>         BB->SetValueAsObject(TargetActorKey.SelectedKeyName, Player);
>         BB->SetValueAsVector(TargetLocationKey.SelectedKeyName, Player->GetActorLocation());
>         BB->SetValueAsBool(IsAlertedKey.SelectedKeyName, true);
>     }
>     else { BB->SetValueAsBool(IsAlertedKey.SelectedKeyName, false); }
> }
> ```
>
> **编辑器中的树结构**（树形图）：
> ```
> Selector (Root)
> ├── Sequence "Detect"  [Decorator: IsNotAlerted(ObserverAbort=LowerPriority)]
> │   ├── Task: FindPlayerLocation (返回 TargetLocation)
> │   └── Task: SetAlertedTrue  (IsAlerted = true)
> ├── Selector "Combat" (在 IsAlerted=true 时可达)
> │   ├── Sequence "Attack"  [Decorator: IsInRange(0, 300, Self)]
> │   │   └── Task: AttackTarget
> │   ├── Sequence "Chase"   [Decorator: IsInRange(300, 2000, Self)]
> │   │   └── Task: ChaseTarget
> │   └── Sequence "LoseTarget"
> │       ├── Task: ClearAlerted  (IsAlerted = false)
> │       └── Task: ReturnToHome
> └── Sequence "Patrol"
>     ├── Task: PatrolToNextWaypoint
>     ├── Task: Wait(2s)
>     └── [Loop]
>
> [Service: UpdateTargetData @0.3s] 挂在 Selector(Root) 上
> ```
>
> **验证步骤**：六个验证场景逐一确认——AI 创建后应开始巡逻；玩家进入感知范围时 Service 更新 IsAlerted=true → Detected Decorator(LowerPriority) 触发 abort 中断 Patrol → 进入 Combat；距离 ≤300 进入 Attack；距离 >300 ≤2000 进入 Chase；距离 >2000 触发 LoseTarget → 返回 Home；Home 到达后 IsAlerted=false → Patrol 恢复。

> [!tip]- 练习 2 参考答案
> **1. Observer Abort 配置**：
>
> - **Detect 分支的 IsNotAlerted Decorator**：监听 `IsAlerted` Key，`FlowAbortMode = LowerPriority`。当 Service 写入 `IsAlerted = true` 时，条件从 false→true，触发 LowerPriority abort → 中断 Patrol 分支，Selector 重新从左评估，进入 Detect 分支。
> - **Attack 分支的 IsInRange Decorator**：监听 `PlayerDistance`，`FlowAbortMode = Self`。当距离 > 300 时条件从 true→false，Self abort 中断 Attack → Selector 重新评估 → fall through 到 Chase。
> - **Chase 分支的 IsInRange Decorator**：监听 `PlayerDistance`，`FlowAbortMode = Self`。当距离 > 2000 时 Self abort → fall through 到 LoseTarget。
>
> **2. 验证步骤代码**：
> ```cpp
> // 在 AbortTask 中添加日志
> EBTNodeResult::Type UBTTask_PatrolToNextWaypoint::AbortTask(
>     UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
> {
>     UE_LOG(LogBehaviorTree, Warning, TEXT("[%s] AbortTask called — interrupting patrol"),
>         *GetNodeName());
>     return EBTNodeResult::Aborted;
> }
> ```
> Observer Abort 响应延迟应为**同一帧**——`UBlackboardComponent::SetValueAsBool` 内部同步调用 `OnBlackboardKeyValueChange` 委托，该委托直接触发 `UBTDecorator::OnBlackboardKeyValueChange` → `ConditionalFlowAbort`。
>
> **3. 回答以下问题**：
>
> **Q: FlowAbortMode = Both vs Self 或 LowerPriority？**
> - `Self`：只在条件 true→false 时 abort 自己 + 右侧兄弟。场景："弹药用完→停止射击"。
> - `LowerPriority`：只在条件 false→true 时 abort 右侧低优先级分支。场景："看到敌人→抢断巡逻"。
> - `Both`：双向反应。当 `IsNotAlerted` 用 Both 时：① `IsAlerted` 从 false→true → LowerPriority abort，中断 Patrol；② `IsAlerted` 从 true→false → Self abort，中断正在进行的 Detect 分支。注意后者可能导致 AI 在"玩家刚离开视野一帧"就立即切回巡逻——如果你希望"丢失目标后保持追一下"，应该只用 LowerPriority，让 LoseTarget 分支来处理退出。
>
> **Q: Observer Abort 的调用链**：
> ```
> UBlackboardComponent::SetValueAsBool("IsAlerted", true)
>   → FBlackboard::SetValue(key, value)
>     → 遍历 key 的 Observer Delegates
>       → UBTDecorator_IsNotAlerted::OnBlackboardKeyValueChange(ChangedKey)
>         → ConditionalFlowAbort(FlowAbortMode)
>           → UBehaviorTreeComponent::RequestExecution(this, AbortLowerPriority)
>             → 下一帧或同一帧: ProcessExecutionRequest()
>               → 从 Root 开始 ApplySearchData(AbortLowerPriority)
>                 → 遍历树找到需要 abort 的分支
>                   → Composite::OnChildAborted()
>                     → 递归调用每个正在 Running 的子节点的 AbortTask()
>                       → Task::AbortTask() → 清理状态，返回 Aborted
> ```
> （UE 5.x 中 `RequestExecution` 可能在 `bRequestedFlowUpdate` 标志下同帧执行）
>
> **Q: Observer Abort 抖动的修复**：
> 当玩家在感知边界快速进出时（如 1999→2001→1999 米），`PlayerDistance` 在 2000 边界振荡，导致 Chase 和 LoseTarget 之间无限 abort。修复方案：
> 1. **迟滞（Hysteresis）**：追击触发距离 2000，退出距离 2500（200 单位缓冲区）。Decorator 内部检查"如果已经在追击中，使用更大的退出阈值"。
> 2. **最小稳定帧数**：条件必须连续满足 N 帧（如 5 帧 = ~83ms）才算切换，过滤瞬时波动。
> 3. **Cooldown Decorator**：在 Chase 分支前挂一个 `Cooldown(0.5s)` 装饰器，防止高频切换。
> 4. **引擎层面的 Abort 冷却**：UE 的 `UBehaviorTreeComponent` 内部已有一个 per-node 的 abort 去重机制——同一帧内同一节点不被 abort 两次。但跨帧抖动仍需上述方案。

> [!tip]- 练习 3 参考答案（可选）
> **1. 共享 Blackboard 策略 — ASharedBlackboardManager**：
> ```cpp
> // SharedBlackboardManager.h
> UCLASS()
> class ASharedBlackboardManager : public AActor
> {
>     GENERATED_BODY()
> public:
>     UPROPERTY(EditAnywhere)
>     UBlackboardData* SharedBBData; // 资产引用
>     UPROPERTY(VisibleAnywhere)
>     UBlackboardComponent* SharedBB;
>     void BeginPlay() override
>     {
>         SharedBB = NewObject<UBlackboardComponent>(this);
>         SharedBB->InitializeBlackboard(*SharedBBData);
>     }
> };
> // 每个 AI Controller 在 BeginPlay 中获取：
> // ASharedBlackboardManager* Mgr = ...; // 通过 GameMode 或 World 查找
> // SharedBBRef = Mgr->SharedBB;
> ```
> 写入权限：只有**第一个发现玩家的守卫**通过 `UBTTask_SetGroupAlerted` 写入共享 BB。其他守卫只读。在网络环境下，Server 端写入，Client 端不进行 BB 写入操作。
>
> **2. UBTService_CheckGroupAlert**：
> ```cpp
> void UBTService_CheckGroupAlert::TickNode(UBehaviorTreeComponent& OwnerComp,
>     uint8* NodeMemory, float DeltaSeconds)
> {
>     // 从 Manager 获取共享 BB 引用（通过 Blackboard Key 或 AIController 成员）
>     auto* MyBB = OwnerComp.GetBlackboardComponent();
>     auto* SharedBB = OwnerComp.GetAIOwner()->GetSharedBlackboard(); // 自定义
>     bool bGroupAlerted = SharedBB->GetValueAsBool("bGroupAlerted");
>     MyBB->SetValueAsBool("bShouldSupport", bGroupAlerted && !MyBB->GetValueAsBool("IsAlerted"));
> }
> ```
>
> **3. UBTTask_FlankTarget**：
> ```cpp
> EBTNodeResult::Type UBTTask_FlankTarget::ExecuteTask(UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
> {
>     auto* BB = OwnerComp.GetBlackboardComponent();
>     AActor* Target = Cast<AActor>(BB->GetValueAsObject("TargetActor"));
>     if (!Target) return EBTNodeResult::Failed;
>     FVector TargetPos = Target->GetActorLocation();
>     FVector AIPos = OwnerComp.GetAIOwner()->GetPawn()->GetActorLocation();
>     FVector DirToTarget = (TargetPos - AIPos).GetSafeNormal();
>     // 45° 偏移，400 单位距离
>     float Angle = (FlankSide == EFlankSide::Left ? 45.0f : -45.0f);
>     FVector FlankPos = TargetPos + DirToTarget.RotateAngleAxis(Angle, FVector::UpVector) * -400.0f;
>     OwnerComp.GetAIOwner()->MoveToLocation(FlankPos);
>     return EBTNodeResult::Succeeded;
> }
> ```
>
> **4. 行为树结构**：
> ```
> Selector (Root)
> ├── Sequence "GroupAlert"  [Decorator: IsGroupAlerted(LowerPriority)]
> │   └── Task: FlankTarget (随机左侧/右侧)
> ├── Selector "SelfAlert"   [Decorator: IsAlerted(LowerPriority)]
> │   ├── Task: ChaseTarget
> │   └── Task: AttackTarget
> └── Sequence "Patrol"
>     ├── Task: PatrolToNextWaypoint
>     └── [Loop]
> ```
>
> **5. 验证场景**：三个守卫 A/B/C。玩家靠近 A → A 的 Perception 触发 Service 写入共享 BB→ A 进入 SelfAlert 分支（追击）→ B/C 的 CheckGroupAlert Service 检测到 `bGroupAlerted=true` 且自身 `IsAlerted=false` → `bShouldSupport=true` → GroupAlert Decorator(LowerPriority) 触发 → B/C 中断 Patrol 进入 FlankTarget。结果：A 从正面追击，B 从左侧 45° 包抄，C 从右侧 45° 包抄。玩家被消灭后，Service 写入 `bGroupAlerted=false` → 所有守卫恢复正常巡逻。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

### 官方文档

| 资源 | 说明 |
|------|------|
| [Unreal Engine Behavior Tree Documentation](https://docs.unrealengine.com/5.3/en-US/behavior-tree-in-unreal-engine/) | Epic 官方 Behavior Tree 文档，含快速入门、节点参考和蓝图集成。**必读**。 |
| [AI Perception System](https://docs.unrealengine.com/5.3/en-US/ai-perception-in-unreal-engine/) | AI Perception 是 BT 的天然"事件源"。理解 Sight/Hearing/Damage 三种感知如何通过 `UAIPerceptionComponent::OnPerceptionUpdated` 委托驱动 BT 的条件评估。 |
| [Environment Query System (EQS)](https://docs.unrealengine.com/5.3/en-US/environment-query-system-in-unreal-engine/) | EQS 与 BT 通过 `UBTTask_RunEQS` 和 `UBTService_RunEQS` 集成。EQS 回答"哪里是最好的掩体？""哪里是最好的射击位置？"，BT 的 Task 使用 EQS 结果执行移动。 |
| [GameplayTasks Integration](https://docs.unrealengine.com/5.3/en-US/gameplay-tasks-in-unreal-engine/) | `UBTTaskNode` 内部基于 `UGameplayTask` 系统。理解 GameplayTasks 的优先级队列机制，可以解释为什么高优先级 BT 分支能中断低优先级分支。 |

### 社区与进阶资源

| 资源 | 说明 |
|------|------|
| [Tom Looman's AI Tutorial Series](https://www.tomlooman.com/) | 前 Epic 工程师的系列教程。覆盖从零搭建 BT + EQS + Perception 的完整 AI 系统，包含 C++ 源码。 |
| [Unreal Engine Source: BehaviorTreeComponent.cpp](https://github.com/EpicGames/UnrealEngine) | 阅读 `UBehaviorTreeComponent::TickComponent`、`ApplySearchData`、`ProcessExecutionRequest` 的源码。理解完整 Tick 循环如何管理节点激活/取消/Abort/重启。调试 BT 问题时的终极参考。 |
| [AIGameDev — AI Behavior Tree Debugging Techniques](https://www.aigamedev.com/) | 深入 BT 调试技巧：使用 `VisualLogger`、`GameplayDebugger` 的 `ShowDebug BehaviorTree` 命令、BT 节点状态可视化。 |
| [GDC 2005: Managing Complexity in the Halo 2 AI (Damian Isla)](https://www.gdcvault.com/) | Halo 2 从 HSM 演化到行为树的历史。虽然不涉及 UE 实现，但理解"为什么需要 Observer Abort"和"优先级中断"的设计哲学，对正确使用 UE BT 至关重要。 |

### 书籍

| 书名 | 章节 | 说明 |
|------|------|------|
| *Unreal Engine 5 Game Development with C++ Scripting* (Zhenyu George Li, 2023) | Chapter 10: AI Behaviors | UE5 BT 的完整实战，包含 C++ 节点编写 → 编辑器组装 → 调试的完整管线。 |
| *Elevating Game Experiences with Unreal Engine 5* (2nd ed.) | Chapter 8: AI and Behavior | 覆盖 BT + EQS + Perception 在商业项目中的集成架构。 |
| *Game AI Pro 1*, Chapter 23: *Behavior Trees for Next-Gen Game AI* (Alex J. Champandard) | 全文 | 行为树理论与工业实践的桥梁章节。理解 BT 的核心契约（Composite/Decorator/Leaf 的语义）如何映射到引擎实现。 |

---

## 常见陷阱

### 1. 忘记调用 FinishLatentTask

**症状**：`ExecuteTask` 返回 `InProgress` 后，行为树再也不会从这个 Task 继续——它"卡住"了。日志中没有错误，但 AI 永远停在"执行中"状态。

**根因**：Unreal 的行为树执行器在遇到 `InProgress` 返回时，会停止对该分支的进一步 Tick，等待 Task 通过 `FinishLatentTask` 异步完成。如果 Task 忘记调用 `FinishLatentTask`（或者它依赖的外部事件永远不会触发），分支永久悬挂。

**解法**：
- 每个返回 `InProgress` 的 Task 必须有至少一个**保证触发的 time-out 路径**调用 `FinishLatentTask`（参见示例 A 的 `TimeRemaining` 倒计时）
- 在 `TickTask` 中检查 `OwnerComp.IsValid()`——如果 Owner AI 被销毁而 Task 仍在等待，没有这个检查会崩溃
- 调试时使用 `ShowDebug BehaviorTree` 控制台命令——可以看到哪些节点卡在 `InProgress`

### 2. Blackboard Key Selector 类型不匹配

**症状**：`BB->GetValueAsObject(KeyName)` 返回 `nullptr`，但你在编辑器中确认 Key 的值不为空。

**根因**：`FBlackboardKeySelector` 在 C++ 构造时通过 `AddObjectFilter`（或 `AddIntFilter`、`AddFloatFilter` 等）声明了期望的类型。但在编辑器中配置时，设计师可能选了另一个类型的 Key（例如将 `Object` Key 配给了期望 `Vector` 的节点）。UE 的 BT Editor **不会**在编辑时报类型不匹配错误——它在运行时静默失败。

**解法**：
- 在构造函数中正确调用 `AddXxxFilter`，限制可选的 Key 类型（参见示例 A/B/C 的构造函数）
- 在 `ExecuteTask`/`CalculateRawConditionValue` 中，始终检查 `BlackboardKey.IsSet()`（确认 Key 已被配置）和 `BB->GetValueAsXxx()` 的返回值
- 使用 `FBlackboardKeySelector::ResolveSelectedKey` 系列方法做类型安全的读取

### 3. 节点实例内存泄漏

**症状**：运行数小时后，AI 的 Behavior Tree 行为逐渐变慢，内存持续增长。

**根因**：覆写了 `GetInstanceMemorySize` 但**没有覆写 `CleanupMemory`**。如果每实例内存中包含需要显式释放的资源（如 `TArray` 堆分配、弱引用表），`UBehaviorTreeComponent` 的默认清理只做 `free` 不会调用析构函数。

**解法**：

```cpp
virtual void CleanupMemory(UBehaviorTreeComponent& OwnerComp,
    uint8* NodeMemory, EBTMemoryClear::Type CleanupType) const override
{
    FMyTaskMemory* MyMemory = reinterpret_cast<FMyTaskMemory*>(NodeMemory);
    MyMemory->~FMyTaskMemory();  // explicit destructor for non-trivial members
}
```

如果内存结构中**只有 POD 类型**（如 `float`, `int32`, `bool`），不需要覆写 `CleanupMemory`——引擎的 `free` 足够。但只要包含 `TArray`、`TMap`、`FString`、`TWeakObjectPtr` 等非平凡类型，必须调用显式析构。

### 4. Observer Abort 导致无限重新评估循环

**症状**：AI 在两个状态之间疯狂抖动（例如 Patrol ↔ Chase 每秒切换几十次），CPU 飙升。

**根因**：Observer Abort 的触发链形成了循环：
- Decorator A 检测到条件变化 → abort 当前 Task T1 → 新分支启动 Task T2
- Task T2 的 `ExecuteTask` 修改了 Blackboard 值 → 触发 Decorator B 的 Observer → abort T2
- 回到 T1 → T1 的 `ExecuteTask` 又修改 Blackboard → 触发 Decorator A → 回到 T2 ……

**解法**：
- **避免在 `ExecuteTask` 中修改触发 Observer 的同一个 Key**。如果 `UBTDecorator_HasAmmo` 监听 `AmmoCount`，`UBTTask_Shoot` 不应该在 `ExecuteTask` 中立即扣弹药——延迟到 `TickTask` 或射击实际执行时
- **使用 Decorator 的 Cooldown**：在容易抖动的 Decorator 之前附加一个 `UBTDecorator_Cooldown`（内置节点，不需要自己写），强制最小间隔
- **引擎的 Abort 冷却**：UE 的 `UBehaviorTreeComponent` 内部有 `NextExecutionTime` 追踪机制，同一帧内不会对同一节点执行多次 abort。但这不能解决跨帧抖动
- **设计层面**：给条件添加滞回（hysteresis）——追击的触发距离和取消距离不同（例如 `<500` 开始追击，`>800` 才放弃），避免在边界附近来回切换

### 5. Service Tick 频率过高

**症状**：场景中有 50 个 AI，每个都有一个每 0.05s 执行一次的 Service，导致 CPU 持续 80%+。

**根因**：Service 的 `Interval` 设得太小。每次 Service Tick 都会执行 `GetActorLocation`、向量运算、BB 读写——这些操作在 50+ 个实体上累积起来很重。

**解法**：
- **默认 Interval 不低于 0.25s**。大多数游戏 AI 在 250ms 的决策延迟下表现完全正常
- **使用 `RandomDeviation`** 分散负载（见示例 C）——50 个 AI 的 Service 应该分散在 0.25-0.35s 之间执行，而非同一帧
- **区分"感知频率"和"决策频率"**：`UBTService_UpdateTargetData` 可以用 0.1s 的 AI Perception 回调（事件驱动，不主动 Tick），而 `UBTService_UpdatePlayerDistance` 只需 0.5s 一次
- **距离 LOD**：对距离玩家超过 3000 单位的 AI，将 Service Interval 提高到 2.0s 或直接暂停 BB 更新——它们不需要每帧知道玩家位置

---

> **下一步**: 完成本教程后，进入 Tutorial 10 [[10-bt-lua|行为树在 Lua 中的实现]]，了解如何在没有 UE 基础设施的情况下从零实现完整的行为树引擎。或者继续 Tutorial 11 [[11-blackboard-data-flow|Blackboard 系统与数据流]]，深入理解 UE Blackboard 的高性能实现和与 BT 的深度集成。
