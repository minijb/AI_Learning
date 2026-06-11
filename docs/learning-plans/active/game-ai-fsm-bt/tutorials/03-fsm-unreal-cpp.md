---
title: "FSM 在 Unreal Engine 中的实现 (C++)"
updated: 2026-06-05
---

# FSM 在 Unreal Engine 中的实现 (C++)

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 01-fsm-core-concepts

---

## 1. 概念讲解

### 为什么需要这个？

Tutorial 01 建立了 FSM 的理论基础——状态、转移、事件、动作。但把理论搬到 Unreal Engine 里时，你会立刻撞上几个实际问题：

- UE 的对象模型（`UObject`、`AActor`、`UActorComponent`）有严格的生命周期和 GC 规则。你的状态对象不能是裸 `new`/`delete` 的普通 C++ 类——GC 会来回收它，或者你忘了回收导致泄漏。
- UE 的反射系统（`UCLASS`/`UPROPERTY`/`UFUNCTION`）为数据驱动和编辑器暴露提供了强大能力。一个纯 C++ `enum class` + `switch` 的 FSM 虽然能跑，但放弃了 UE 最大的优势：让设计师在编辑器中配置行为。
- UE 自带 StateTree、GameplayAbilitySystem (GAS) 等框架，它们与 FSM 有重叠也有互补。你需要在合适的场景选择合适的工具，而不是每次都从零撸一个 FSM。

本节覆盖四种在 UE 中实现 FSM 的主流模式，按复杂度递增：

| 模式 | 适用场景 | 复杂度 | 数据驱动 |
|------|---------|--------|---------|
| UEnum + switch | 简单敌人 AI（≤5 个状态） | 低 | 否 |
| UObject 状态模式 | 复杂 AI，需要状态私有数据 | 中 | 否 |
| DataTable 驱动 | 设计师需要配置转移规则 | 中高 | 是 |
| StateTree | UE5 官方推荐的行为状态系统 | 中 | 原生支持 |

### 核心思想

#### 模式 A: UEnum + switch —— 最简 FSM

这与 Tutorial 01 的 switch 模式本质相同，但利用了 `UENUM` 反射：

```cpp
UENUM(BlueprintType)
enum class EEnemyState : uint8
{
    Idle,
    Patrol,
    Chase,
    Attack,
    Dead
};
```

`UENUM` 带来的好处：可以在蓝图中访问、可以在编辑器 Details 面板中显示当前状态、可以用 `StaticEnum<EEnemyState>()->GetDisplayNameTextByValue()` 打印可读的状态名。

这种模式的核心思想是：**Actor/Component 自己就是状态机宿主**。当前状态作为 `UPROPERTY` 成员变量存储，`Tick()` 中执行 switch 分发，无需额外的状态对象。

优点：零额外分配、性能最优、理解成本最低。
缺点：所有状态逻辑挤在一个类里，状态数量增长后难以维护；设计师无法在编辑器里配置转移规则。

#### 模式 B: UObject 状态模式 —— 面向对象 FSM

将每个状态建模为一个 `UObject` 子类：

```cpp
UCLASS(Abstract, Blueprintable)
class UAIState : public UObject
{
    GENERATED_BODY()
public:
    // Called when entering this state
    virtual void OnEnter(AActor* Owner) {}
    // Called every frame while this state is active
    virtual void OnTick(AActor* Owner, float DeltaTime) {}
    // Called when leaving this state
    virtual void OnExit(AActor* Owner) {}
    // Evaluate transitions; returns the next state or nullptr to stay
    virtual UAIState* EvaluateTransition(AActor* Owner) { return nullptr; }
};
```

状态机组件（`UActorComponent`）持有当前状态对象的引用，每个 `Tick` 委托给它。转移通过状态对象的 `EvaluateTransition()` 返回目标状态来完成。

**关键设计决策：UObject vs 纯 C++ 的权衡**

`UAIState` 继承自 `UObject`（而非普通 C++ 类）有明确意图：

1. **GC 集成**：`UPROPERTY()` 引用会被 UE 的垃圾回收器追踪。如果你把状态对象存为裸指针，GC 不知道你持有它，可能在某个时刻回收掉，导致悬垂指针。
2. **蓝图可继承**：`Blueprintable` 让设计师可以创建蓝图子类覆盖行为，而不需要改 C++ 代码。
3. **反射**：可以在编辑器中将状态对象暴露为可配置的资产。

代价是：`UObject` 不能独立存在——必须作为另一个 `UObject` 的 `UPROPERTY` 子对象或被 `AddToRoot()` 保护。每个状态对象至少需要 56 字节（`UObject` 基类的大小），加上虚函数表指针。对于 100+ 个敌人的场景，如果每个敌人持有自己的状态对象，会有明显的 GC 遍历开销。

**单例状态 vs 实例状态**

这是状态模式在 UE 中实践时最常见的分歧：

- **共享/单例模式**：每种状态只有一个全局实例，所有敌人共享。状态对象不能存储实体特定的数据（如"当前追击目标"），这些数据放在 `AActor` 或 Blackboard 上。优点：内存极省，GC 压力为零。
- **实例模式**：每个敌人拥有自己的状态对象实例，状态可以存储私有数据。优点：状态逻辑更自包含。缺点：大量敌人时 GC 遍历开销不可忽略。

对于游戏 AI，**共享状态模式**通常是正确选择。把数据（Blackboard）和行为（State）分离，状态类只定义行为逻辑，数据从 Actor 或 Blackboard 读取。

#### 模式 C: DataTable 驱动 FSM

将转移规则从代码移到数据资源中：

```cpp
USTRUCT(BlueprintType)
struct FStateTransitionRow : public FTableRowBase
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    FGameplayTag FromState;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    FGameplayTag ToState;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    FGameplayTag TriggerEvent;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float Priority = 0.0f;
};
```

运行时加载 `UDataTable` 资产，根据当前状态和触发事件查询转移规则。

优点：设计师可以在不碰 C++ 的情况下调整 AI 行为。新增一个状态只修改一行数据，不需要改代码。同一个 AI 逻辑可以用不同的 DataTable 产生不同性格的敌人（激进型、保守型）。

代价：转移查询需要每帧遍历 DataTable（或建立索引缓存），有查找开销。配置错误（如拼错 GameplayTag）在编译期无法发现，运行时才能暴露。

#### UE5 StateTree 简介

UE5 引入的 StateTree 是 Epic 官方对"游戏 AI 需要什么状态系统"的答案。它不是传统 FSM，而是一种**层级状态机 + 数据绑定**系统：

- 状态有树状嵌套结构（父状态可以包含子状态）
- 转移条件使用 `Evaluator` 节点，支持参数化的 `Condition`
- 数据通过 `Instance Data` 绑定，类似于 DataAsset + Blackboard 的混合

StateTree 的设计哲学是：**状态是资产**（`.uasset`），在编辑器中可视化编辑，运行时无 GC 压力（它不是 `UObject` 树）。

何时用 StateTree 而非手动 FSM：
- 状态超过 8 个且转移规则频繁变动。
- 团队有设计师参与 AI 调优。
- 需要 UE5 的 Mass AI 系统集成（StateTree 是 Mass AI 的官方行为框架）。

何时继续用手动 FSM：
- 简单 AI（≤5 个状态）。
- 需要极致性能且状态逻辑不频繁变动。
- 需要在多个 UE 版本间保持兼容（StateTree 在 5.0-5.4 间有 API 变动）。

#### FSM 与 GameplayAbilitySystem 的关系

GAS 和 FSM 解决不同层次的问题：

| 层次 | FSM | GAS |
|------|-----|-----|
| 行为决策 | "我该做什么？"（巡逻→追击→攻击） | "我能做什么？"（哪些技能可用） |
| 状态粒度 | 粗粒度——行为模式 | 细粒度——能力激活/冷却/消耗 |
| 典型角色 | 敌人 AI 顶层行为 | 角色战斗技能系统 |

它们经常组合使用：**FSM 决策"是否"进入战斗状态，GAS 管理"如何"施放技能**。例如：

```cpp
void UCombatState::OnEnter(AActor* Owner)
{
    // FSM 层: 进入战斗状态
    // GAS 层: 激活战斗技能组
    UAbilitySystemComponent* ASC = Owner->FindComponentByClass<UAbilitySystemComponent>();
    if (ASC)
    {
        ASC->GiveAbility(FGameplayAbilitySpec(UCombatAbility::StaticClass()));
    }
}

void UCombatState::OnTick(AActor* Owner, float DeltaTime)
{
    // GAS 自动处理冷却、消耗、动画——FSM 不需要关心这些细节
    // FSM 只负责通过 EvaluateTransition 决定何时退出战斗
}
```

#### 委托驱动的转移系统

UE 的 `DECLARE_DYNAMIC_MULTICAST_DELEGATE` 非常适合实现事件驱动的 FSM 转移。替代每帧轮询条件的方式：

```cpp
// 定义事件
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnPlayerDetected);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnDamageReceived, float, Damage);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnHealthDepleted);

// 在状态机组件中绑定
void UFSMComponent::BeginPlay()
{
    Super::BeginPlay();
    // 绑定事件 → 状态转移
    OnPlayerDetected.AddDynamic(this, &UFSMComponent::TransitionToChase);
    OnHealthDepleted.AddDynamic(this, &UFSMComponent::TransitionToDead);
}
```

委托模式的优势：事件驱动而非每帧轮询——如果 PlayerDetected 没有触发，`EvaluateTransition` 根本不需要执行，节省 CPU 周期。

#### TMap 转移表

对于纯数据驱动的 FSM，`TMap` 可以作为内存中的转移索引：

```cpp
// Key: (FromState, Event) pair; Value: target state + guard function
struct FTransitionKey
{
    FGameplayTag FromState;
    FGameplayTag Event;
    
    friend bool operator==(const FTransitionKey& A, const FTransitionKey& B)
    {
        return A.FromState == B.FromState && A.Event == B.Event;
    }
    
    friend uint32 GetTypeHash(const FTransitionKey& Key)
    {
        return HashCombine(GetTypeHash(Key.FromState), GetTypeHash(Key.Event));
    }
};

TMap<FTransitionKey, FTransitionRule> TransitionTable;
```

这比 DataTable 的逐行扫描快 O(1) vs O(n)，但需要在 DataTable 加载时构建索引。对于超过 20 条转移规则的情况，务必建立索引缓存。

---

## 2. 代码示例

> **说明**：以下代码是完整的 Unreal Engine C++ 示例。为了清晰，省略了部分 UE 宏（如 `GENERATED_BODY`）的重复展示。所有类名和函数遵循 UE 命名规范。假设你已有一个第三人称 C++ 项目模板。

### 示例 A: UEnum + switch FSM on ACharacter

这是最直接的模式：一个 `ACharacter` 子类持有状态枚举，在 `Tick` 中 switch 分发。

```cpp
// ============================================================
// EnemyAICharacter.h
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "EnemyAICharacter.generated.h"

UENUM(BlueprintType)
enum class EEnemyState : uint8
{
    Idle        UMETA(DisplayName = "待机"),
    Patrol      UMETA(DisplayName = "巡逻"),
    Chase       UMETA(DisplayName = "追击"),
    Attack      UMETA(DisplayName = "攻击"),
    Dead        UMETA(DisplayName = "死亡")
};

UCLASS()
class MYPROJECT_API AEnemyAICharacter : public ACharacter
{
    GENERATED_BODY()

public:
    AEnemyAICharacter();

    virtual void Tick(float DeltaTime) override;

protected:
    virtual void BeginPlay() override;

    // ---- FSM Core ----
    void EvaluateTransitions();
    void ExecuteState(float DeltaTime);
    void SetState(EEnemyState NewState);

    // ---- State Behaviors ----
    void EnterState(EEnemyState State);
    void ExitState(EEnemyState State);
    void TickIdle(float DeltaTime);
    void TickPatrol(float DeltaTime);
    void TickChase(float DeltaTime);
    void TickAttack(float DeltaTime);
    void TickDead(float DeltaTime);

    // ---- Perception ----
    bool CanSeePlayer() const;
    bool IsPlayerInAttackRange() const;
    bool IsPlayerInDetectRange() const;

    // ---- Current State ----
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "FSM")
    EEnemyState CurrentState;

    // ---- Configuration ----
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float DetectRange = 1500.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float AttackRange = 200.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float PatrolSpeed = 200.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float ChaseSpeed = 500.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float AttackCooldown = 1.0f;

    // ---- Runtime Data ----
    UPROPERTY()
    TArray<FVector> PatrolPoints;

    int32 CurrentPatrolIndex = 0;
    float CooldownTimer = 0.0f;
    float Health = 100.0f;
};

// ============================================================
// EnemyAICharacter.cpp
// ============================================================

#include "EnemyAICharacter.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "AIController.h"

AEnemyAICharacter::AEnemyAICharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    CurrentState = EEnemyState::Idle;
}

void AEnemyAICharacter::BeginPlay()
{
    Super::BeginPlay();

    // Populate patrol points from children actors tagged as "PatrolPoint"
    TArray<AActor*> FoundPoints;
    UGameplayStatics::GetAllActorsWithTag(GetWorld(), FName("PatrolPoint"), FoundPoints);
    for (AActor* Point : FoundPoints)
    {
        PatrolPoints.Add(Point->GetActorLocation());
    }

    // Enter initial state
    SetState(EEnemyState::Patrol);
}

void AEnemyAICharacter::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

    // Phase 1: Evaluate transitions first so the correct state runs this frame
    EvaluateTransitions();

    // Phase 2: Execute current state behavior
    ExecuteState(DeltaTime);
}

void AEnemyAICharacter::EvaluateTransitions()
{
    // Dead is an absorbing state — no transitions out
    if (CurrentState == EEnemyState::Dead) return;

    if (Health <= 0.0f)
    {
        SetState(EEnemyState::Dead);
        return;
    }

    // Transitions in priority order
    switch (CurrentState)
    {
    case EEnemyState::Idle:
        if (IsPlayerInDetectRange() && CanSeePlayer())
        {
            SetState(EEnemyState::Chase);
        }
        break;

    case EEnemyState::Patrol:
        if (IsPlayerInAttackRange() && CanSeePlayer())
        {
            SetState(EEnemyState::Attack);
        }
        else if (IsPlayerInDetectRange() && CanSeePlayer())
        {
            SetState(EEnemyState::Chase);
        }
        break;

    case EEnemyState::Chase:
        if (IsPlayerInAttackRange() && CanSeePlayer())
        {
            SetState(EEnemyState::Attack);
        }
        else if (!IsPlayerInDetectRange() || !CanSeePlayer())
        {
            SetState(EEnemyState::Patrol);
        }
        break;

    case EEnemyState::Attack:
        if (!IsPlayerInAttackRange() && IsPlayerInDetectRange() && CanSeePlayer())
        {
            SetState(EEnemyState::Chase);
        }
        else if (!IsPlayerInDetectRange() || !CanSeePlayer())
        {
            SetState(EEnemyState::Patrol);
        }
        break;

    default: break;
    }
}

void AEnemyAICharacter::ExecuteState(float DeltaTime)
{
    switch (CurrentState)
    {
    case EEnemyState::Idle:   TickIdle(DeltaTime);   break;
    case EEnemyState::Patrol: TickPatrol(DeltaTime); break;
    case EEnemyState::Chase:  TickChase(DeltaTime);  break;
    case EEnemyState::Attack: TickAttack(DeltaTime); break;
    case EEnemyState::Dead:   TickDead(DeltaTime);   break;
    }
}

void AEnemyAICharacter::SetState(EEnemyState NewState)
{
    if (NewState == CurrentState) return;

    ExitState(CurrentState);
    CurrentState = NewState;
    EnterState(CurrentState);

    UE_LOG(LogTemp, Log, TEXT("[%s] State: %s"),
        *GetName(),
        *StaticEnum<EEnemyState>()->GetDisplayNameTextByValue(static_cast<int64>(CurrentState)).ToString());
}

void AEnemyAICharacter::EnterState(EEnemyState State)
{
    switch (State)
    {
    case EEnemyState::Patrol:
        GetCharacterMovement()->MaxWalkSpeed = PatrolSpeed;
        break;
    case EEnemyState::Chase:
        GetCharacterMovement()->MaxWalkSpeed = ChaseSpeed;
        break;
    case EEnemyState::Attack:
        GetCharacterMovement()->MaxWalkSpeed = 0.0f;
        CooldownTimer = 0.0f;
        break;
    case EEnemyState::Dead:
        GetCharacterMovement()->DisableMovement();
        GetMesh()->SetSimulatePhysics(true); // ragdoll
        SetLifeSpan(5.0f); // auto-destroy after 5 seconds
        break;
    default: break;
    }
}

void AEnemyAICharacter::ExitState(EEnemyState State)
{
    // Cleanup when leaving a state — cancel timers, reset data, etc.
    switch (State)
    {
    case EEnemyState::Attack:
        CooldownTimer = 0.0f;
        break;
    default: break;
    }
}

void AEnemyAICharacter::TickIdle(float DeltaTime)
{
    // Idle: do nothing, wait for perception trigger
}

void AEnemyAICharacter::TickPatrol(float DeltaTime)
{
    if (PatrolPoints.Num() == 0) return;

    AAIController* AI = Cast<AAIController>(GetController());
    if (!AI) return;

    FVector Target = PatrolPoints[CurrentPatrolIndex];
    float DistSq = FVector::DistSquared(GetActorLocation(), Target);

    if (DistSq < 10000.0f) // 100cm tolerance
    {
        CurrentPatrolIndex = (CurrentPatrolIndex + 1) % PatrolPoints.Num();
    }

    AI->MoveToLocation(PatrolPoints[CurrentPatrolIndex]);
}

void AEnemyAICharacter::TickChase(float DeltaTime)
{
    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(GetWorld(), 0);
    if (!Player) return;

    AAIController* AI = Cast<AAIController>(GetController());
    if (!AI) return;

    AI->MoveToActor(Player);
}

void AEnemyAICharacter::TickAttack(float DeltaTime)
{
    CooldownTimer -= DeltaTime;
    if (CooldownTimer > 0.0f) return;

    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(GetWorld(), 0);
    if (!Player) return;

    // Face the player
    FVector Dir = (Player->GetActorLocation() - GetActorLocation()).GetSafeNormal();
    SetActorRotation(Dir.Rotation());

    // Apply damage (simplified — use ApplyDamage() in production)
    Player->TakeDamage(20.0f, FDamageEvent(), nullptr, this);

    CooldownTimer = AttackCooldown;
}

void AEnemyAICharacter::TickDead(float DeltaTime)
{
    // Ragdoll does its own thing — nothing to tick
}

bool AEnemyAICharacter::CanSeePlayer() const
{
    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(GetWorld(), 0);
    if (!Player) return false;

    FHitResult Hit;
    FVector Start = GetActorLocation();
    FVector End = Player->GetActorLocation();
    FCollisionQueryParams Params;
    Params.AddIgnoredActor(this);

    return !GetWorld()->LineTraceSingleByChannel(Hit, Start, End,
        ECC_Visibility, Params);
}

bool AEnemyAICharacter::IsPlayerInAttackRange() const
{
    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(GetWorld(), 0);
    if (!Player) return false;
    return FVector::Dist(GetActorLocation(), Player->GetActorLocation()) <= AttackRange;
}

bool AEnemyAICharacter::IsPlayerInDetectRange() const
{
    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(GetWorld(), 0);
    if (!Player) return false;
    return FVector::Dist(GetActorLocation(), Player->GetActorLocation()) <= DetectRange;
}
```

**设计要点**：
- `SetState` 统一处理 Enter/Exit 回调，保证不会漏掉状态清理。
- `EvaluateTransitions` 在 `ExecuteState` 之前调用，保证同一帧感知事件能立刻切换状态。
- 所有配置参数（速度、范围、冷却）都是 `UPROPERTY(EditAnywhere)`，可在编辑器中调整。

---

### 示例 B: UObject 状态模式

状态作为独立 `UObject` 子类，由 `UActorComponent` 管理。

```cpp
// ============================================================
// AIState.h — base state class
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "AIState.generated.h"

UCLASS(Abstract, Blueprintable, BlueprintType, EditInlineNew, DefaultToInstanced)
class MYPROJECT_API UAIState : public UObject
{
    GENERATED_BODY()

public:
    /** Called when this state becomes active. */
    UFUNCTION(BlueprintNativeEvent, Category = "AI State")
    void OnEnter(AActor* Owner);
    virtual void OnEnter_Implementation(AActor* Owner) {}

    /** Called every frame while this state is active. */
    UFUNCTION(BlueprintNativeEvent, Category = "AI State")
    void OnTick(AActor* Owner, float DeltaTime);
    virtual void OnTick_Implementation(AActor* Owner, float DeltaTime) {}

    /** Called when this state is no longer active. */
    UFUNCTION(BlueprintNativeEvent, Category = "AI State")
    void OnExit(AActor* Owner);
    virtual void OnExit_Implementation(AActor* Owner) {}

    /**
     * Evaluates transition conditions.
     * @return The next state to transition to, or nullptr to remain in this state.
     */
    UFUNCTION(BlueprintNativeEvent, Category = "AI State")
    UAIState* EvaluateTransition(AActor* Owner);
    virtual UAIState* EvaluateTransition_Implementation(AActor* Owner) { return nullptr; }

    /** Friendly name for debug display. */
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "AI State")
    FName StateName;
};

// ============================================================
// AIStateMachineComponent.h — state machine host
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "AIStateMachineComponent.generated.h"

class UAIState;

UCLASS(ClassGroup=(AI), meta=(BlueprintSpawnableComponent))
class MYPROJECT_API UAIStateMachineComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UAIStateMachineComponent();

    virtual void TickComponent(float DeltaTime, ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction) override;

    /** Transition to a new state, calling Exit on old and Enter on new. */
    UFUNCTION(BlueprintCallable, Category = "AI State Machine")
    void TransitionTo(UAIState* NewState);

    /** Returns the current state (may be null before initialization). */
    UFUNCTION(BlueprintPure, Category = "AI State Machine")
    UAIState* GetCurrentState() const { return CurrentState; }

    /** Initialize with a starting state. Call during BeginPlay. */
    UFUNCTION(BlueprintCallable, Category = "AI State Machine")
    void StartStateMachine(UAIState* InitialState);

protected:
    virtual void BeginPlay() override;

    UPROPERTY()
    UAIState* CurrentState;
};

// ============================================================
// AIStateMachineComponent.cpp
// ============================================================

#include "AIStateMachineComponent.h"
#include "AIState.h"

UAIStateMachineComponent::UAIStateMachineComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

void UAIStateMachineComponent::BeginPlay()
{
    Super::BeginPlay();
}

void UAIStateMachineComponent::StartStateMachine(UAIState* InitialState)
{
    if (!InitialState) return;
    // Don't call TransitionTo here — it would call Exit on null CurrentState
    CurrentState = InitialState;
    CurrentState->OnEnter(GetOwner());
}

void UAIStateMachineComponent::TickComponent(float DeltaTime, ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

    if (!CurrentState) return;

    // Tick current state
    CurrentState->OnTick(GetOwner(), DeltaTime);

    // Evaluate transitions
    UAIState* NextState = CurrentState->EvaluateTransition(GetOwner());
    if (NextState && NextState != CurrentState)
    {
        TransitionTo(NextState);
    }
}

void UAIStateMachineComponent::TransitionTo(UAIState* NewState)
{
    if (!NewState || NewState == CurrentState) return;

    if (CurrentState)
    {
        CurrentState->OnExit(GetOwner());
    }

    UE_LOG(LogTemp, Log, TEXT("[%s] FSM: %s → %s"),
        *GetOwner()->GetName(),
        CurrentState ? *CurrentState->StateName.ToString() : TEXT("None"),
        *NewState->StateName.ToString());

    UAIState* OldState = CurrentState;
    CurrentState = NewState;
    CurrentState->OnEnter(GetOwner());
}

// ============================================================
// States_Concrete.h — concrete state examples
// ============================================================

#pragma once

#include "AIState.h"
#include "Engine/DataTable.h"
#include "States_Concrete.generated.h"

/**
 * Patrol state: follows a set of waypoints.
 * Transitions to ChaseState when player detected.
 */
UCLASS()
class MYPROJECT_API UPatrolState : public UAIState
{
    GENERATED_BODY()

public:
    UPatrolState() { StateName = TEXT("Patrol"); }

    virtual void OnEnter_Implementation(AActor* Owner) override;
    virtual void OnTick_Implementation(AActor* Owner, float DeltaTime) override;
    virtual void OnExit_Implementation(AActor* Owner) override;
    virtual UAIState* EvaluateTransition_Implementation(AActor* Owner) override;

    /** Speed to use while patrolling. */
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Patrol")
    float PatrolSpeed = 300.0f;

    /** State to transition to when player is detected. */
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Patrol")
    TSubclassOf<UAIState> ChaseStateClass;

private:
    int32 CurrentWaypoint = 0;
};

/**
 * Chase state: pursues the player.
 * Uses FTimerHandle for a "lost sight" timeout.
 * Transitions to AttackState when in range, back to PatrolState on timeout.
 */
UCLASS()
class MYPROJECT_API UChaseState : public UAIState
{
    GENERATED_BODY()

public:
    UChaseState() { StateName = TEXT("Chase"); }

    virtual void OnEnter_Implementation(AActor* Owner) override;
    virtual void OnTick_Implementation(AActor* Owner, float DeltaTime) override;
    virtual void OnExit_Implementation(AActor* Owner) override;
    virtual UAIState* EvaluateTransition_Implementation(AActor* Owner) override;

    /** How long the enemy will chase without seeing the player before giving up. */
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Chase")
    float ChaseTimeout = 5.0f;

    /** Speed during chase. */
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Chase")
    float ChaseSpeed = 600.0f;

    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Chase")
    TSubclassOf<UAIState> AttackStateClass;

    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Chase")
    TSubclassOf<UAIState> PatrolStateClass;

private:
    FTimerHandle LostSightTimerHandle;
    AActor* OwnerActor = nullptr;

    UFUNCTION()
    void OnLostSightTimeout();
};

// ============================================================
// States_Concrete.cpp — partial implementation
// ============================================================

#include "States_Concrete.h"
#include "AIController.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"

// ---- Patrol State ----

void UPatrolState::OnEnter_Implementation(AActor* Owner)
{
    ACharacter* Character = Cast<ACharacter>(Owner);
    if (Character)
    {
        Character->GetCharacterMovement()->MaxWalkSpeed = PatrolSpeed;
    }
}

void UPatrolState::OnTick_Implementation(AActor* Owner, float DeltaTime)
{
    // Waypoint following logic — simplified for brevity
    AAIController* AI = Cast<AAIController>(
        Cast<APawn>(Owner) ? Cast<APawn>(Owner)->GetController() : nullptr);
    if (!AI || !AI->GetMoveStatus().IsValid())
    {
        // Pick a random destination
        FVector Origin = Owner->GetActorLocation();
        FVector RandomDest = Origin + FVector(
            FMath::RandRange(-1000.0f, 1000.0f),
            FMath::RandRange(-1000.0f, 1000.0f),
            0.0f);
        AI->MoveToLocation(RandomDest);
    }
}

void UPatrolState::OnExit_Implementation(AActor* Owner)
{
    AAIController* AI = Cast<AAIController>(
        Cast<APawn>(Owner) ? Cast<APawn>(Owner)->GetController() : nullptr);
    if (AI) AI->StopMovement();
}

UAIState* UPatrolState::EvaluateTransition_Implementation(AActor* Owner)
{
    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(Owner->GetWorld(), 0);
    if (!Player) return nullptr;

    float Dist = FVector::Dist(Owner->GetActorLocation(), Player->GetActorLocation());
    if (Dist <= 1500.0f)
    {
        // Transition to chase — instantiate the state class
        if (ChaseStateClass)
        {
            return NewObject<UAIState>(Owner, ChaseStateClass);
        }
    }
    return nullptr;
}

// ---- Chase State ----

void UChaseState::OnEnter_Implementation(AActor* Owner)
{
    OwnerActor = Owner;
    ACharacter* Character = Cast<ACharacter>(Owner);
    if (Character)
    {
        Character->GetCharacterMovement()->MaxWalkSpeed = ChaseSpeed;
    }

    // Start a timer: if we don't see the player for ChaseTimeout seconds, give up
    Owner->GetWorldTimerManager().SetTimer(LostSightTimerHandle,
        this, &UChaseState::OnLostSightTimeout, ChaseTimeout, false);
}

void UChaseState::OnTick_Implementation(AActor* Owner, float DeltaTime)
{
    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(Owner->GetWorld(), 0);
    if (!Player) return;

    AAIController* AI = Cast<AAIController>(
        Cast<APawn>(Owner)->GetController());
    if (AI) AI->MoveToActor(Player);

    // Check line of sight; if player is visible, reset the timeout
    FHitResult Hit;
    FVector Start = Owner->GetActorLocation();
    FVector End = Player->GetActorLocation();
    FCollisionQueryParams Params;
    Params.AddIgnoredActor(Owner);

    if (!Owner->GetWorld()->LineTraceSingleByChannel(Hit, Start, End,
        ECC_Visibility, Params))
    {
        // Player is visible — refresh the timer
        Owner->GetWorldTimerManager().SetTimer(LostSightTimerHandle,
            this, &UChaseState::OnLostSightTimeout, ChaseTimeout, false);
    }
}

void UChaseState::OnExit_Implementation(AActor* Owner)
{
    Owner->GetWorldTimerManager().ClearTimer(LostSightTimerHandle);
}

UAIState* UChaseState::EvaluateTransition_Implementation(AActor* Owner)
{
    // Transitions are driven by timer (timeout → patrol) or by reaching attack range
    // The timer callback calls TransitionTo directly
    return nullptr; // transition evaluation is timer/event-driven in this example
}

void UChaseState::OnLostSightTimeout()
{
    // Timer fired — we lost the player. Transition back to patrol.
    UActorComponent* Comp = OwnerActor->FindComponentByClass<UAIStateMachineComponent>();
    if (Comp && PatrolStateClass)
    {
        UAIState* PatrolState = NewObject<UAIState>(OwnerActor, PatrolStateClass);
        Cast<UAIStateMachineComponent>(Comp)->TransitionTo(PatrolState);
    }
}
```

**设计要点**：
- `UAIState` 使用 `EditInlineNew` + `DefaultToInstanced` 说明符，允许在蓝图编辑器中内联创建和配置状态资产。
- `TSubclassOf<UAIState>` 用于配置转移目标，这样状态可以引用其他状态的类而不创建循环依赖。
- `FTimerHandle` 管理"追击超时"——这是委托驱动转移的一个实例：超时事件触发状态切换，而非每帧轮询。
- 状态对象用 `NewObject<UAIState>(Outer, Class)` 动态创建，Outer 设置为 Actor 以确保 GC 不会过早回收它们。生产级代码应使用共享单例模式避免频繁分配。

---

### 示例 C: DataTable 驱动 FSM

将转移规则配置为数据资产，运行时不依赖硬编码的 switch。

```cpp
// ============================================================
// FSMDataTable.h — struct and loader
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataTable.h"
#include "GameplayTagContainer.h"
#include "FSMDataTable.generated.h"

/**
 * A single row in the transition table.
 * Each row defines: "When in State A, on Event E, go to State B."
 *
 * Priority resolves conflicts when multiple rows match.
 */
USTRUCT(BlueprintType)
struct FFSMTransitionRow : public FTableRowBase
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    FGameplayTag FromState;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    FGameplayTag TriggerEvent;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    FGameplayTag ToState;

    /** Higher = evaluated first. Resolves ambiguity. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    int32 Priority = 0;

    /** Optional guard: only transition if health is below this value (1.0 = 100%). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float HealthThreshold = 1.0f;

    /** Optional guard: transition only if distance to player ≤ this (0 = disabled). */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM")
    float MaxDistance = 0.0f;
};

/**
 * Runtime lookup index for O(1) transition queries.
 */

USTRUCT()
struct FFSMTransitionIndex
{
    GENERATED_BODY()

    /** Per-state list of transition rows that apply to that state, pre-sorted by priority. */
    UPROPERTY()
    TMap<FGameplayTag, TArray<FFSMTransitionRow>> RowsByFromState;
};

/**
 * Loads a DataTable asset and builds a transition index for fast querying.
 */
UCLASS()
class MYPROJECT_API UFSMTransitionTable : public UObject
{
    GENERATED_BODY()

public:
    /** Load and index a DataTable asset. Call once during BeginPlay. */
    UFUNCTION(BlueprintCallable, Category = "FSM DataTable")
    void LoadTable(UDataTable* DataTable);

    /**
     * Query the transition table.
     * @param CurrentState  The state the entity is currently in.
     * @param Event         The event that just occurred.
     * @param HealthRatio   Current health ratio (0-1) for guard evaluation.
     * @param PlayerDistance Distance to player for guard evaluation.
     * @return The target state tag, or FGameplayTag::EmptyTag if no match.
     */
    FGameplayTag QueryTransition(FGameplayTag CurrentState, FGameplayTag Event,
        float HealthRatio = 1.0f, float PlayerDistance = 0.0f) const;

private:
    FFSMTransitionIndex TransitionIndex;
};

// ============================================================
// FSMDataTable.cpp
// ============================================================

#include "FSMDataTable.h"
#include "Engine/DataTable.h"

void UFSMTransitionTable::LoadTable(UDataTable* DataTable)
{
    if (!DataTable) return;

    TransitionIndex.RowsByFromState.Empty();

    static const FString ContextStr(TEXT("FSMTransitionTable::LoadTable"));
    TArray<FFSMTransitionRow*> AllRows;
    DataTable->GetAllRows<FFSMTransitionRow>(ContextStr, AllRows);

    for (FFSMTransitionRow* Row : AllRows)
    {
        if (Row && Row->FromState.IsValid())
        {
            TransitionIndex.RowsByFromState.FindOrAdd(Row->FromState).Add(*Row);
        }
    }

    // Sort each state's list by priority (descending)
    for (auto& Pair : TransitionIndex.RowsByFromState)
    {
        Pair.Value.Sort([](const FFSMTransitionRow& A, const FFSMTransitionRow& B) {
            return A.Priority > B.Priority;
        });
    }

    UE_LOG(LogTemp, Log, TEXT("[FSMTransitionTable] Loaded %d states, %d total transitions."),
        TransitionIndex.RowsByFromState.Num(), AllRows.Num());
}

FGameplayTag UFSMTransitionTable::QueryTransition(
    FGameplayTag CurrentState, FGameplayTag Event,
    float HealthRatio, float PlayerDistance) const
{
    const TArray<FFSMTransitionRow>* Rows = TransitionIndex.RowsByFromState.Find(CurrentState);
    if (!Rows) return FGameplayTag::EmptyTag;

    // Rows are already sorted by priority — first match wins
    for (const FFSMTransitionRow& Row : *Rows)
    {
        if (Row.TriggerEvent != Event) continue;

        // Evaluate optional guards
        if (HealthRatio > Row.HealthThreshold) continue;
        if (Row.MaxDistance > 0.0f && PlayerDistance > Row.MaxDistance) continue;

        return Row.ToState;
    }

    return FGameplayTag::EmptyTag;
}

// ============================================================
// DataDrivenFSMComponent.h — usage example
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GameplayTagContainer.h"
#include "FSMDataTable.h"
#include "DataDrivenFSMComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnStateChanged, FGameplayTag, OldState,
    FGameplayTag, NewState);

UCLASS()
class MYPROJECT_API UDataDrivenFSMComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UDataDrivenFSMComponent();

    virtual void TickComponent(float DeltaTime, ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction) override;

    /** The transition table asset configured in-editor. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "FSM DataTable")
    UDataTable* TransitionTableAsset;

    /** Initial state tag. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FSM DataTable")
    FGameplayTag InitialState;

    /** Trigger an event on the FSM. If a matching transition exists, state changes. */
    UFUNCTION(BlueprintCallable, Category = "FSM DataTable")
    void SendEvent(FGameplayTag Event);

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "FSM DataTable")
    FGameplayTag CurrentState;

    UPROPERTY(BlueprintAssignable, Category = "FSM DataTable")
    FOnStateChanged OnStateChanged;

protected:
    virtual void BeginPlay() override;

private:
    UPROPERTY()
    UFSMTransitionTable* TransitionTable;

    void SetState(FGameplayTag NewState);
    float GetHealthRatio() const;
    float GetPlayerDistance() const;
};

// ============================================================
// DataDrivenFSMComponent.cpp
// ============================================================

#include "DataDrivenFSMComponent.h"
#include "GameFramework/Character.h"
#include "Kismet/GameplayStatics.h"

UDataDrivenFSMComponent::UDataDrivenFSMComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
}

void UDataDrivenFSMComponent::BeginPlay()
{
    Super::BeginPlay();

    if (TransitionTableAsset)
    {
        TransitionTable = NewObject<UFSMTransitionTable>(this);
        TransitionTable->LoadTable(TransitionTableAsset);
    }

    SetState(InitialState);
}

void UDataDrivenFSMComponent::TickComponent(float DeltaTime, ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

    // Periodic evaluation for distance/health guards
    if (!TransitionTable || !CurrentState.IsValid()) return;

    FGameplayTag QueryEvent = FGameplayTag::RequestGameplayTag(TEXT("Event.Tick"));
    FGameplayTag NextState = TransitionTable->QueryTransition(
        CurrentState, QueryEvent, GetHealthRatio(), GetPlayerDistance());

    if (NextState.IsValid())
    {
        SetState(NextState);
    }
}

void UDataDrivenFSMComponent::SendEvent(FGameplayTag Event)
{
    if (!TransitionTable || !CurrentState.IsValid()) return;

    FGameplayTag NextState = TransitionTable->QueryTransition(
        CurrentState, Event, GetHealthRatio(), GetPlayerDistance());

    if (NextState.IsValid())
    {
        SetState(NextState);
    }
}

void UDataDrivenFSMComponent::SetState(FGameplayTag NewState)
{
    if (NewState == CurrentState) return;

    FGameplayTag OldState = CurrentState;
    CurrentState = NewState;

    UE_LOG(LogTemp, Log, TEXT("[%s] FSM State: %s → %s"),
        *GetOwner()->GetName(), *OldState.ToString(), *NewState.ToString());

    OnStateChanged.Broadcast(OldState, NewState);
}

float UDataDrivenFSMComponent::GetHealthRatio() const
{
    // In production, read from a HealthComponent or AttributeSet
    return 1.0f;
}

float UDataDrivenFSMComponent::GetPlayerDistance() const
{
    ACharacter* Player = UGameplayStatics::GetPlayerCharacter(GetWorld(), 0);
    if (!Player) return FLT_MAX;
    return FVector::Dist(GetOwner()->GetActorLocation(), Player->GetActorLocation());
}
```

**DataTable 资产结构示例**（在编辑器中配置为 CSV 或手填行）：

| RowName | FromState | TriggerEvent | ToState | Priority | HealthThreshold | MaxDistance |
|---------|-----------|-------------|---------|----------|-----------------|-------------|
| PatrolToChase | `State.Patrol` | `Event.PlayerDetected` | `State.Chase` | 10 | 1.0 | 1500 |
| ChaseToAttack | `State.Chase` | `Event.PlayerInRange` | `State.Attack` | 10 | 1.0 | 200 |
| ChaseToPatrol | `State.Chase` | `Event.PlayerLost` | `State.Patrol` | 5 | 1.0 | 0 |
| AttackToChase | `State.Attack` | `Event.PlayerOutOfRange` | `State.Chase` | 10 | 1.0 | 0 |
| AnyToDead | `State.Patrol` | `Event.HealthZero` | `State.Dead` | 100 | 0.0 | 0 |
| AnyToDead | `State.Chase` | `Event.HealthZero` | `State.Dead` | 100 | 0.0 | 0 |
| AnyToDead | `State.Attack` | `Event.HealthZero` | `State.Dead` | 100 | 0.0 | 0 |

注意 `HealthZero` 事件需要一行对应每个可能的源状态（除非你实现通配符匹配）。优先级 100 保证死亡转移在所有其他转移之前被评估。

---

## 3. 练习

### 练习 1: 炮塔 AI FSM (UActorComponent)

**目标**：实现一个炮塔的五态 FSM，作为 `UActorComponent` 挂在 `AActor` 上。

**状态定义**：

| 状态 | 说明 |
|------|------|
| `Idle` | 炮塔缓慢旋转（360° 扫描动画），等待目标 |
| `Searching` | 检测到可疑但未锁定；快速转向最后已知方向 |
| `LockedOn` | 锁定目标，持续跟踪瞄准 |
| `Firing` | 锁定状态下以固定射速开火 |
| `Overheated` | 热量槽满；停止射击，冷却一段时间后回到 Idle |

**转移规则**：

| 从 | 事件 | 到 | 条件 |
|----|------|----|------|
| Idle | TargetInRange | Searching | 距离 ≤ DetectionRadius |
| Searching | TargetLost | Idle | 超过 SearchTimeout 未锁定 |
| Searching | TargetLocked | LockedOn | 在 LockRadius 内且有视线 |
| LockedOn | TargetLost | Searching | 丢失目标 |
| LockedOn | TargetInFiringRange | Firing | 距离 ≤ FireRange 且有视线 |
| Firing | TargetOutOfRange | LockedOn | 距离 > FireRange |
| Firing | OverheatTriggered | Overheated | 连续射击 HeatPerShot × N ≥ MaxHeat |
| Overheated | CooldownComplete | Idle | 等待 CooldownDuration 秒 |
| (任意) | HealthZero | — | 禁用组件 |

**要求**：

1. 使用 `UENUM` 定义 `ETurretState`。使用 `switch` + `TickComponent` 实现（参考示例 A 但作为 Component）。
2. 状态逻辑：
   - `Idle`: `FRotator` 平滑插值旋转（`FMath::RInterpTo`）。
   - `Searching`: 用 `FTimerHandle` 计时；超时后回到 Idle。
   - `LockedOn`: 每帧 `FindLookAtRotation` 计算朝向目标的旋转。
   - `Firing`: 用 `FTimerHandle` 管理射速（`SetTimer` 循环 + `FireShot()` 函数）。每次射击增加热量值。`FireShot` 内做 `LineTrace`，命中时调用 `UGameplayStatics::ApplyDamage`。
   - `Overheated`: 计时冷却，计时结束时转换回 Idle。
3. 将热量 (`CurrentHeat`)、最大热量 (`MaxHeat`)、冷却速率 (`CooldownDuration`) 暴露为 `EditAnywhere`。
4. 在 `BeginPlay` 中调用 `SetState(ETurretState::Idle)`。用统一的 `SetState` 函数处理 Enter/Exit。
5. 确保 `Overheated` 和 `Dead` 态势不会因新的事件而错误转移。
6. 写至少 3 个 `UE_LOG` 调用在不同的 Enter 回调中，标记状态切换。

---

### 练习 2: DataTable 配置化

**目标**：将练习 1 的炮塔 FSM 转移规则从 `switch` 改为 `UDataTable` 驱动。

**要求**：

1. 定义 `FTurretTransitionRow : public FTableRowBase`，字段包括：`FromState` (FName)、`TriggerEvent` (FName)、`ToState` (FName)、`Priority` (int32)。
2. 创建 `UTurretTransitionTable : public UObject`，构造函数接收 `UDataTable*` 并建立 `TMap<FName, TArray<FTurretTransitionRow>>` 索引。
3. 修改 `UTurretFSMComponent::EvaluateTransitions()`，使用 `UTurretTransitionTable::Query(FName CurrentState, FName Event)` 进行 O(1) 查找。
4. 在编辑器中创建一个 `UTurretDataTable` 资产（DataTable 行结构选 `FTurretTransitionRow`），填入全部 9 条转移规则。导出为 CSV 文件，粘贴 CSV 内容到答案中。
5. 回答：与 `switch` 版本相比，DataTable 版本在以下方面的差异：
   - 新增"维修中"状态时的改动流程。
   - 设计师独立调试转移逻辑的能力。
   - 性能差异（100 个炮塔同时运行）。

---

### 练习 3: UE5 StateTree 炮塔（可选）

**目标**：了解 UE5 的 StateTree 系统，体会其与手动 FSM 的差异。

**要求**：

1. 在 UE5 中创建 StateTree 资产，实现与练习 1 相同的五态炮塔逻辑。
2. 比较 StateTree 的 `Evaluator` / `Condition` / `Task` 与你手写的 Enter/Exit/Tick/EvaluateTransition 的对应关系。
3. 回答：StateTree 的 `Instance Data` 机制如何替代 UObject 状态模式中的状态私有成员变量？
4. 回答：在以下场景中，你会选择 StateTree 还是手动 FSM？给出理由。
   - 场景 A: Boss AI（20+ 状态，阶段切换，需要设计师频繁迭代）
   - 场景 B: 批量小兵 AI（200 个实体，5 个状态，行为固定不变）
   - 场景 C: 过场动画序列管理器（时间线驱动，无复杂条件）


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **UTurretFSMComponent 完整实现：**
>
> ```cpp
> // TurretFSMComponent.h
> #pragma once
> #include "CoreMinimal.h"
> #include "Components/ActorComponent.h"
> #include "TurretFSMComponent.generated.h"
>
> UENUM(BlueprintType)
> enum class ETurretState : uint8
> {
>     Idle        UMETA(DisplayName = "待机"),
>     Searching   UMETA(DisplayName = "搜索"),
>     LockedOn    UMETA(DisplayName = "锁定"),
>     Firing      UMETA(DisplayName = "射击"),
>     Overheated  UMETA(DisplayName = "过热"),
>     Dead        UMETA(DisplayName = "已摧毁")
> };
>
> UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
> class MYPROJECT_API UTurretFSMComponent : public UActorComponent
> {
>     GENERATED_BODY()
> public:
>     UTurretFSMComponent();
>     virtual void TickComponent(float DeltaTime, ELevelTick TickType,
>         FActorComponentTickFunction* ThisTickFunction) override;
>
> protected:
>     virtual void BeginPlay() override;
>
>     // FSM Core
>     void EvaluateTransitions();
>     void ExecuteState(float DeltaTime);
>     void SetState(ETurretState NewState);
>
>     // State Behaviors
>     void EnterState(ETurretState State);
>     void ExitState(ETurretState State);
>     void TickIdle(float DeltaTime);
>     void TickSearching(float DeltaTime);
>     void TickLockedOn(float DeltaTime);
>     void TickFiring(float DeltaTime);
>     void TickOverheated(float DeltaTime);
>
>     // Combat
>     void FireShot();
>
>     // State
>     UPROPERTY(VisibleAnywhere, Category = "FSM")
>     ETurretState CurrentState = ETurretState::Idle;
>
>     // Config
>     UPROPERTY(EditAnywhere, Category = "FSM|Perception")
>     float DetectionRadius = 2000.0f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Perception")
>     float LockRadius = 1000.0f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Combat")
>     float FireRange = 800.0f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Combat")
>     float FireRate = 0.3f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Combat")
>     float DamagePerShot = 10.0f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Heat")
>     float MaxHeat = 100.0f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Heat")
>     float HeatPerShot = 8.0f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Heat")
>     float CooldownDuration = 3.0f;
>     UPROPERTY(EditAnywhere, Category = "FSM|Search")
>     float SearchTimeout = 4.0f;
>
>     // Runtime
>     float CurrentHeat = 0.0f;
>     float CooldownTimer = 0.0f;
>     float SearchTimer = 0.0f;
>     FTimerHandle FireTimerHandle;
>     FRotator IdleTargetRotation;
> };
> ```
>
> ```cpp
> // TurretFSMComponent.cpp (key methods)
> void UTurretFSMComponent::BeginPlay()
> {
>     Super::BeginPlay();
>     IdleTargetRotation = GetOwner()->GetActorRotation();
>     SetState(ETurretState::Idle);
> }
>
> void UTurretFSMComponent::TickComponent(float DeltaTime, ELevelTick, FActorComponentTickFunction*)
> {
>     EvaluateTransitions();
>     ExecuteState(DeltaTime);
> }
>
> void UTurretFSMComponent::SetState(ETurretState NewState)
> {
>     if (NewState == CurrentState) return;
>     ExitState(CurrentState);
>     CurrentState = NewState;
>     EnterState(CurrentState);
> }
>
> void UTurretFSMComponent::EnterState(ETurretState State)
> {
>     switch (State)
>     {
>     case ETurretState::Idle:
>         UE_LOG(LogTemp, Log, TEXT("[Turret] Entering Idle — scanning rotation"));
>         break;
>     case ETurretState::Searching:
>         UE_LOG(LogTemp, Log, TEXT("[Turret] Entering Searching — acquired suspicious contact"));
>         SearchTimer = 0.0f;
>         break;
>     case ETurretState::LockedOn:
>         UE_LOG(LogTemp, Log, TEXT("[Turret] Entering LockedOn — target acquired!"));
>         break;
>     case ETurretState::Firing:
>         GetWorld()->GetTimerManager().SetTimer(FireTimerHandle, this,
>             &UTurretFSMComponent::FireShot, FireRate, true);
>         break;
>     case ETurretState::Overheated:
>         UE_LOG(LogTemp, Warning, TEXT("[Turret] Overheated! Cooling down..."));
>         CooldownTimer = 0.0f;
>         GetWorld()->GetTimerManager().ClearTimer(FireTimerHandle);
>         break;
>     case ETurretState::Dead:
>         SetActive(false); // Disable component
>         break;
>     }
> }
>
> void UTurretFSMComponent::TickIdle(float DeltaTime)
> {
>     // Smooth 360-degree scanning rotation
>     IdleTargetRotation.Yaw += 30.0f * DeltaTime;
>     FRotator Current = GetOwner()->GetActorRotation();
>     FRotator Target = IdleTargetRotation;
>     GetOwner()->SetActorRotation(FMath::RInterpTo(Current, Target, DeltaTime, 2.0f));
> }
>
> void UTurretFSMComponent::TickSearching(float DeltaTime)
> {
>     // Rapid turn towards last known direction
>     SearchTimer += DeltaTime;
>     if (SearchTimer >= SearchTimeout)
>     {
>         SetState(ETurretState::Idle);
>         return;
>     }
>     // Rotate toward last known target location...
> }
>
> void UTurretFSMComponent::TickLockedOn(float DeltaTime)
> {
>     AActor* Target = GetTarget();
>     if (!Target) return;
>     FRotator LookAt = UKismetMathLibrary::FindLookAtRotation(
>         GetOwner()->GetActorLocation(), Target->GetActorLocation());
>     GetOwner()->SetActorRotation(FMath::RInterpTo(
>         GetOwner()->GetActorRotation(), LookAt, DeltaTime, 8.0f));
> }
>
> void UTurretFSMComponent::TickFiring(float DeltaTime)
> {
>     TickLockedOn(DeltaTime); // Keep tracking while firing
> }
>
> void UTurretFSMComponent::TickOverheated(float DeltaTime)
> {
>     CooldownTimer += DeltaTime;
>     CurrentHeat = FMath::FInterpTo(CurrentHeat, 0.0f, DeltaTime, 1.0f);
>     if (CooldownTimer >= CooldownDuration)
>     {
>         CurrentHeat = 0.0f;
>         SetState(ETurretState::Idle);
>     }
> }
>
> void UTurretFSMComponent::FireShot()
> {
>     FVector Start = GetOwner()->GetActorLocation();
>     FVector End = Start + GetOwner()->GetActorForwardVector() * FireRange;
>     FHitResult Hit;
>     FCollisionQueryParams Params;
>     Params.AddIgnoredActor(GetOwner());
>
>     if (GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
>     {
>         if (AActor* HitActor = Hit.GetActor())
>         {
>             UGameplayStatics::ApplyDamage(HitActor, DamagePerShot,
>                 GetOwner()->GetInstigatorController(), GetOwner(), UDamageType::StaticClass());
>         }
>     }
>
>     CurrentHeat += HeatPerShot;
>     if (CurrentHeat >= MaxHeat)
>     {
>         SetState(ETurretState::Overheated);
>     }
> }
> ```

> [!tip]- 练习 2 参考答案
> **FTurretTransitionRow 结构体：**
>
> ```cpp
> USTRUCT(BlueprintType)
> struct FTurretTransitionRow : public FTableRowBase
> {
>     GENERATED_BODY()
>
>     UPROPERTY(EditAnywhere, BlueprintReadWrite)
>     FName FromState;
>     UPROPERTY(EditAnywhere, BlueprintReadWrite)
>     FName TriggerEvent;
>     UPROPERTY(EditAnywhere, BlueprintReadWrite)
>     FName ToState;
>     UPROPERTY(EditAnywhere, BlueprintReadWrite)
>     int32 Priority = 0;
> };
> ```
>
> **UTurretTransitionTable 查询类：**
>
> ```cpp
> UCLASS()
> class UTurretTransitionTable : public UObject
> {
>     GENERATED_BODY()
>     TMap<FName, TArray<FTurretTransitionRow>> Index;
> public:
>     void BuildFromDataTable(UDataTable* DataTable)
>     {
>         Index.Empty();
>         static const FString ContextStr(TEXT("TurretFSM"));
>         TArray<FTurretTransitionRow*> Rows;
>         DataTable->GetAllRows(ContextStr, Rows);
>         for (auto* Row : Rows)
>         {
>             Index.FindOrAdd(Row->FromState).Add(*Row);
>         }
>     }
>     const FTurretTransitionRow* Query(FName FromState, FName Event) const
>     {
>         const TArray<FTurretTransitionRow>* Candidates = Index.Find(FromState);
>         if (!Candidates) return nullptr;
>         for (const auto& Row : *Candidates)
>         {
>             if (Row.TriggerEvent == Event) return &Row;
>         }
>         return nullptr;
>     }
> };
> ```
>
> **CSV 内容（9 条转移规则）：**
>
> ```csv
> FromState,TriggerEvent,ToState,Priority
> Idle,TargetInRange,Searching,0
> Searching,TargetLost,Idle,0
> Searching,TargetLocked,LockedOn,0
> LockedOn,TargetLost,Searching,0
> LockedOn,TargetInFiringRange,Firing,0
> Firing,TargetOutOfRange,LockedOn,0
> Firing,OverheatTriggered,Overheated,0
> Overheated,CooldownComplete,Idle,0
> Searching,HealthZero,Dead,10
> Idle,HealthZero,Dead,10
> LockedOn,HealthZero,Dead,10
> Firing,HealthZero,Dead,10
> ```
>
> **switch vs DataTable 差异分析：**
>
> | 维度 | switch 版本 | DataTable 版本 |
> |------|------------|----------------|
> | 新增"维修中"状态改动流程 | 修改 5 个 switch case + 新增 Enter/Exit/Tick 函数 + 在 EvaluateTransitions 的各 case 中添加新条件的处理 = 改动分散在 4-5 处 | 在 CSV 中新增 "Repairing" 状态的行（定义哪些事件进入/离开该状态）+ 在组件中添加 Enter/Exit/Tick 函数 = 逻辑与转移分离 |
> | 设计师独立调试 | 需要程序员介入，通过断点或 UE_LOG 查看分支 | 可在 DataTable 编辑器中直接查看/修改转移规则，无需重新编译 |
> | 性能（100 炮塔） | 最优：switch 是编译期跳转表，O(1) | 每次查询 TMap O(1)，但多了哈希查找开销；100 个炮塔共享同一份 DataTable 时只需一次建索引 |

> [!tip]- 练习 3 参考答案（可选）
> **StateTree 与手动 FSM 的对应关系：**
>
> | StateTree 概念 | 手动 FSM 对应 | 说明 |
> |:---|:---|:---|
> | State | EEnemyState 枚举值 + Enter/Exit/Tick | StateTree 的状态是树节点，可以有子状态 |
> | Evaluator | 嵌入在 Tick 中的条件检查（轮询） | Evaluator 持续运行，返回布尔值驱动转移 |
> | Condition（在 Transition 上） | EvaluateTransitions() 中的 if 判断 | 决定是否触发转移 |
> | Task | 状态 Update 中的具体行为函数 | Action 节点，可跨多帧执行（返回 Running） |
> | Instance Data | 状态对象的私有成员变量（如 CurrentHeat） | 绑定到状态实例，每个 agent 独立 |
>
> **场景选型决策：**
>
> - **场景 A (Boss AI, 20+ 状态)**：选择 **StateTree**。状态数量多 + 需要设计师频繁迭代 + 有层次结构需求（阶段 → 子行为）。StateTree 的资产化编辑和数据绑定让设计师可以独立调优 Boss 行为，无需每次修改等程序员改 C++。
> - **场景 B (批量小兵 AI, 200 实体, 5 状态)**：选择 **手动 FSM (UEnum + switch / UObject 状态模式)**。状态少且固定，性能敏感（200 个实体），不需要可视化编辑。StateTree 的每帧 Evaluator 评估在 200 个实体上开销不可忽略，而手写 switch 是编译期优化的跳转表。
> - **场景 C (过场动画序列管理器)**：选择 **手动 FSM 或 Level Sequence**。过场动画是时间线驱动的线性序列，没有复杂条件分支，FSM 的 switch 或 UE 原生的 Level Sequence Director 更合适。StateTree 的条件驱动在这里是杀鸡用牛刀——大多数"转移"只是"当前动画播放完毕"，不需要动态条件评估。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

### 官方文档

| 资源 | 说明 |
|------|------|
| [Unreal Engine StateTree Documentation](https://docs.unrealengine.com/5.3/en-US/state-tree-in-unreal-engine/) | Epic 官方 StateTree 文档，含快速入门和完整 API 参考。StateTree 是 UE5 中对传统手动 FSM 的官方替代方案。 |
| [Gameplay Ability System (GAS) Documentation](https://docs.unrealengine.com/5.3/en-US/gameplay-ability-system-for-unreal-engine/) | 理解 GAS 后，才能判断何时用 FSM、何时用 GAS 管理角色行为。推荐先读 GameplayTags、GameplayAbilities、AbilityTasks 三个子章节。 |
| [AI Perception System](https://docs.unrealengine.com/5.3/en-US/ai-perception-in-unreal-engine/) | AI Perception 是 UE 的感知框架（视觉、听觉、伤害事件），与 FSM 是天然的"事件源 + 决策层"组合。 |
| [Mass AI](https://docs.unrealengine.com/5.3/en-US/mass-ai-in-unreal-engine/) | UE5 的大规模 AI 框架。Mass AI 原生使用 StateTree 作为行为系统。如果你的游戏有 100+ AI 实体，应该了解 Mass 而非手写 `AActor` + FSM。 |

### 社区资源

| 资源 | 说明 |
|------|------|
| [Tom Looman's GAS & AI Tutorial Series](https://www.tomlooman.com/) | 前 Epic 工程师的 UE AI 教程系列，覆盖 Perception、Behavior Tree、EQS 与 FSM 的组合使用。 |
| [UE4/5 AI Programming: Introduction](https://dev.epicgames.com/community/learning/tutorials/eO2P/unreal-engine-ai-programming-introduction) | Epic 社区教程，从零搭建 AI Controller + FSM 的蓝图版本——理解蓝图 FSM 可以帮助你设计 C++ 版的接口。 |
| [Unreal Slackers Discord #ai channel](https://unrealslackers.org/) | UE AI 开发者社区，遇到具体问题时最有用的求助渠道。 |

### 书籍章节

| 书名 | 章节 | 说明 |
|------|------|------|
| *Unreal Engine 5 Game Development with C++ Scripting* (Zhenyu George Li, 2023) | Chapter 10: AI Behaviors | 覆盖 Behavior Tree 和 State Tree 两种范式，包含 C++ 与蓝图的混合编程模式。 |
| *Elevating Game Experiences with Unreal Engine 5* (multiple authors, 2nd ed.) | Chapter 8: AI and Behavior | 涵盖 GAS + FSM 在商业项目中的实际架构。 |

---

## 常见陷阱

### 1. UObject 状态对象的 GC 陷阱

**症状**：`UAIState` 对象在运行时被 GC 回收，`CurrentState` 变成悬垂指针，访问时崩溃。

**根因**：`UObject` 实例只要有 `UPROPERTY()` 强引用就不会被 GC。但如果你把状态对象创建为局部变量或存在裸指针里，GC 看不到这个引用。

**解法**：

```cpp
// ✅ 正确：CurrentState 是 UPROPERTY，被 GC 追踪
UPROPERTY()
UAIState* CurrentState;

// ❌ 错误：裸指针——GC 不知道你持有它
UAIState* CurrentState; // may become dangling!
```

对于共享/单例状态对象，在 `UAIStateMachineComponent` 中用 `UPROPERTY() TMap<FName, UAIState*> StateCache` 持有所有状态的引用，保证它们在组件的生命周期内不被回收。

### 2. Tick 开销——每帧 switch 的隐藏成本

**症状**：场景中有 200 个敌人，每个 `TickComponent` 里有 `switch` + `LineTrace`，帧率降到 30fps 以下。

**根因**：每帧对所有敌人做感知检测（射线检测尤其是性能杀手）+ switch 分支预测失效的开销。即使敌人在 `Idle` 或 `Dead` 状态，`EvaluateTransitions` 仍然在运行。

**解法**（按影响从大到小）：

1. **禁用休眠实体的 Tick**：`Dead` 状态调用 `SetComponentTickEnabled(false)`。远离玩家的实体通过 `UActorComponent::SetComponentTickInterval()` 降低 Tick 频率。
2. **事件驱动替代轮询**：用 AI Perception 的 `OnPerceptionUpdated` 委托 + `SendEvent` 替代每帧 `CanSeePlayer()` 检查。感知系统内部有空间哈希优化，比你手写的 `LineTrace` 高效得多。
3. **使用 UE5 Mass AI**：如果实体数量超过 100，考虑 Mass Entity 系统——它用 ECS 模式批量处理，消除逐实体虚函数调用开销。
4. **降低感知检测频率**：不必每帧检测。用 `FTimerHandle` 每 0.2-0.5 秒检查一次，大多数游戏 AI 行为在 100-200ms 的延迟下是察觉不到的。

### 3. DataTable 行命名冲突

**症状**：新加的转移规则不生效，也没有错误提示。

**根因**：DataTable 要求每行的 `RowName`（`FName` 类型）**全局唯一**。如果你复制了一行但忘记改 RowName，新行会静默覆盖旧行（或反过来）。

**解法**：

- 使用一致的命名约定：`FromState_Event_ToState`（如 `Patrol_PlayerDetected_Chase`）。`FName` 不分大小写，所以 `patrol_playerDetected_Chase` 和 `Patrol_PlayerDetected_Chase` 被视为同一行。
- 在运行时加载完成后，`ensure(DataTable->GetTableData().RowMap.Num() == expectedRowCount)` 验证行数。
- 导出 CSV 后用文本对比工具验证，而不是在编辑器的行列表里肉眼看。

### 4. BeginPlay 初始化顺序

**症状**：`AEnemyAICharacter::BeginPlay()` 中调用了 `FindComponentByClass<UFSMComponent>()`，但组件尚未注册，返回 `nullptr`。

**根因**：`AActor::BeginPlay()` 和 `UActorComponent::BeginPlay()` 的执行顺序是：先 Actor、后 Component，但 Component 之间没有保证的顺序。如果你的 FSM Component 依赖另一个 Component（如 HealthComponent），不能假设它在 `BeginPlay` 中已经可用。

**解法**：

- 将 FSM 的初始化逻辑放在 `TickComponent` 的第一帧（用 `bInitialized` 标志位延迟初始化）——但这增加了分支。
- 更好的方案：在 FSM Component 的 `BeginPlay` 中，用 `GetOwner()->FindComponentByClass<T>()` 获取依赖组件，如果为 null，`ensureMsgf` 断言并优雅降级（不崩溃，但记录错误）。
- 最鲁棒方案：创建一个 `AIController` 子类，在其 `OnPossess` 中统一初始化 AI 的各个组件——此时所有 Component 都已注册完毕。

### 5. 状态逻辑中直接操作 Actor 属性

**症状**：`UChaseState::OnEnter` 直接修改 `ACharacter->GetCharacterMovement()->MaxWalkSpeed = 600.0f`。后来你把这个状态接到一个非 Character 类型的 Actor 上，崩溃。

**根因**：状态对象对宿主类型做了隐式假设。`AActor* Owner` 可以是任何 Actor 子类。

**解法**：

- 在 `OnEnter` 中 `Cast<T>` 并对 `nullptr` 做早期返回，绝不做裸假设。
- 更好的设计：不要直接操作 Actor 的移动组件。让状态通过**能力/接口**（如 `UCharacterMovementInterface`）与宿主通信，这样任何实现了该接口的 Actor 都可以使用这个状态。

```cpp
// ✅ 通过接口解耦
void UChaseState::OnEnter_Implementation(AActor* Owner)
{
    if (IMovementInterface* Movement = Cast<IMovementInterface>(Owner))
    {
        Movement->SetSpeed(ChaseSpeed);
    }
}
```
