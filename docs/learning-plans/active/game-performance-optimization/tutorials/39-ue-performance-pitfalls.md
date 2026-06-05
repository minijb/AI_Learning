---
title: "UE 常见性能陷阱"
updated: 2026-06-05
---

# UE 常见性能陷阱
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50 分钟
> 前置知识: 34-ue-low-level.md、35-ue-rendering.md、36-ue-threading.md
---
## 1. 概念讲解

### 为什么需要这个？

UE 的性能陷阱有两种：一种是"API 用错了会慢"，另一种是"API 本身就有问题，但你不走到那一步不会发现"。绝大多数开发者掉进陷阱的方式不是无知，而是**默认行为**——UE 为了让入门简单，很多默认值都是"能用但不够快"。等你项目已经做了几个月才发现某个默认设置是帧率杀手，重构成本就很高了。

本章从八个常见方向系统性地梳理这些陷阱：从最臭名昭著的 Tick 滥用，到蓝图与 C++ 的边界，到碰撞、动画、关卡流送的隐性开销。读完这一章，你应该能够在 Code Review 中一眼识别出"这段代码跑 100 个实例就会掉帧"的模式。

### 核心思想

#### 1. Tick 滥用 — 头号帧率杀手

**问题的本质**：UE 中几乎所有 Actor 和 Component 默认都启用 Tick (`PrimaryActorTick.bCanEverTick = true`)。一个场景中有 5000 个 Actor，即使 4990 个的 Tick 函数是空的，引擎仍然需要每帧遍历它们——函数调用的分发开销本身就很大。

**最常见的 Tick 滥用模式**：

```
❌ 在 Tick 中做重复查询：
   Tick → GetAllActorsOfClass() → 每帧遍历所有 Actor
   Tick → FindComponentByClass() → 每帧查找 Component
   Tick → 读取磁盘/网络 → 每帧 I/O

❌ 在 Tick 中做不需要逐帧更新的计算：
   Tick → 重新生成路径 → 路径只在你移动后才需要更新
   Tick → 检查 "玩家是否在 10 米内" → 而这个条件每 0.5 秒检查一次就够了

❌ 不可见的 Actor 仍然 Tick：
   远处的敌人、被遮挡的粒子、已死亡的尸体——都在 Tick
```

**解决方案**：
- 用 `SetActorTickEnabled(false)` 明确关闭不需要的 Tick
- 用 `Timer`（`FTimerHandle`）替代 Tick 中做周期性工作
- 用 `UFUNCTION()` 的 `BlueprintNativeEvent` 实现按需更新
- 在 Actor 离开玩家视野时关闭 Tick（`WasRecentlyRendered` 检查）

#### 2. Blueprint vs C++ — 10x-100x 的性能差距

蓝图虚拟机 (Blueprint VM) 的每条节点大概比等效的 C++ 代码慢 10-100 倍。这不是蓝图"写得不好"，而是字节码解释执行和 C++ 编译优化之间的固有差距。

**蓝图特别慢的场景**：
- 数学运算密集（大量 Vector/Quat 运算）
- 循环遍历数组（每次迭代都有 VM 开销）
- 字符串操作和格式化
- 在 Tick 中调用复杂蓝图函数

**蓝图 nativization**（蓝图本地化）可以将蓝图转译为 C++ 源码再编译，但局限性很大：
- 只支持特定节点类型
- 不能 nativize 动态委托
- 某些蓝图宏不兼容
- 在 UE5 中已不推荐使用（Epic 官方已标记为 Deprecated）

**最优方案**：热路径用 C++，配置和事件流用蓝图。具体来说：
- 在 C++ 中实现 `BlueprintCallable` 函数处理重计算
- 蓝图中只做事件绑定和流程编排
- 考虑使用 `UFUNCTION(BlueprintPure=false)` 标记有副作用的函数（防止蓝图在 Tick 中反复调用）

#### 3. Construction Script 滥用

**Construction Script 的杀手级特征**：它不仅在放置 Actor 时执行，还在地图中每次移动 Actor、每次修改属性、以及编辑器启动时执行。一个 Construction Script 如果有：
- `SpawnActor`（每次移动都生成新 Actor！）
- `LoadObject`（每次移动都读磁盘）
- 复杂的循环计算

那么你的编辑器就会卡顿——即使在运行时没问题。

**规则**：Construction Script 只应设置视觉相关的初始值，不应有任何副作用。

#### 4. Cast 节点在蓝图热路径中

蓝图中的 `Cast To` 节点不是免费的——它涉及类型查找和指针转换。在 Tick 中每帧对一个数组中的每个 Actor 做 Cast，成本很快就上来了。

**替代方案**：
- 使用 `Interface`（蓝图接口）替代 Cast——Interface 调用不需要做类型转换
- 缓存 Cast 结果（`GetComponentByClass` 的结果存为成员变量）
- 使用 `IsA()` 检查替代 Cast 再取值（如果只是防御性检查）

#### 5. 碰撞复杂度过高

碰撞检测分为两个阶段：**Broad Phase**（粗检测，用空间哈希或 Sweep-and-Prune）和 **Narrow Phase**（精确检测，用 GJK/EPA 算法）。

Narrow Phase 的成本取决于碰撞体的几何复杂度：
- **Simple Collision**：Box、Sphere、Capsule、Convex Hull（快，常数时间）
- **Complex Collision**（Use Complex Collision as Simple）：逐三角形检测（慢，正比于三角形数量）

**常见错误**：在角色胶囊体上启用复杂碰撞，导致每次与地形碰撞都做逐三角形测试。

#### 6. Animation Blueprint 开销

Animation Blueprint 的性能消耗有两个来源：
- **Event Graph**：逐帧执行的动画事件逻辑（类似于 Actor 的 Event Tick）——如果在这里做复杂计算，成本很高。
- **Anim Graph**：混合树、状态机——这些是 C++ 本地化的，相对高效。

**关键优化**：
- 对距离远的角色使用 **Animation Budget Allocator** 插件（强制远处角色以更低频率更新动画）
- 启用 **Parallel Animation Evaluation**（`a.ParallelAnimEvaluation 1`）
- 将复杂动画计算移到 Anim Graph（C++ 原生），而非 Event Graph（Blueprint VM）

#### 7. 关卡流送卡顿

World Composition / World Partition 的关卡流送可能在 GameThread 上触发同步加载（`LoadPackage` 阻塞），导致 50-200ms 的卡顿。

**缓解策略**：
- 使用 `FStreamableManager::RequestAsyncLoad` 预加载即将需要的资产
- 设置合理的流送距离和预算
- 在加载屏幕中隐藏卡顿，或用过场动画覆盖

#### 8. 对象池化

频繁 `SpawnActor` / `Destroy` 不仅触发内存分配，还强制 GC 标记整个对象图。如第 37 章所述，对象池是解决这个问题的标准模式。

---
## 2. 代码示例

### 示例 A：Tick 优化 — 坏 vs 好

```cpp
// TickPitfall_Bad.cpp — 经典的 Tick 滥用
UCLASS()
class ABadEnemyManager : public AActor
{
    GENERATED_BODY()
public:
    ABadEnemyManager()
    {
        PrimaryActorTick.bCanEverTick = true;
    }

    virtual void Tick(float DeltaTime) override
    {
        Super::Tick(DeltaTime);

        // ❌ 每帧遍历所有 Actor！
        TArray<AActor*> AllEnemies;
        UGameplayStatics::GetAllActorsOfClass(GetWorld(), AEnemyCharacter::StaticClass(), AllEnemies);

        for (AActor* Enemy : AllEnemies)
        {
            // ❌ 每帧检查距离
            float Dist = FVector::Dist(GetActorLocation(), Enemy->GetActorLocation());
            if (Dist < 1000.0f)
            {
                // ❌ 每帧 Cast
                if (AEnemyCharacter* EnemyChar = Cast<AEnemyCharacter>(Enemy))
                {
                    EnemyChar->ActivateNearPlayer();
                }
            }
        }
    }
};
```

```cpp
// TickPitfall_Good.cpp — 优化后的版本
UCLASS()
class AGoodEnemyManager : public AActor
{
    GENERATED_BODY()

private:
    // ✅ 缓存敌人列表，只在加入/离开时更新
    UPROPERTY()
    TArray<TWeakObjectPtr<AEnemyCharacter>> TrackedEnemies;

    FTimerHandle DistanceCheckTimer;
    static constexpr float DistanceCheckInterval = 0.5f; // 每 0.5 秒检查一次

public:
    AGoodEnemyManager()
    {
        PrimaryActorTick.bCanEverTick = false; // ✅ 完全关闭 Tick
    }

    virtual void BeginPlay() override
    {
        Super::BeginPlay();
        // ✅ 用 Timer 替代 Tick 做周期性检查
        GetWorldTimerManager().SetTimer(DistanceCheckTimer, this,
            &AGoodEnemyManager::CheckEnemyDistances,
            DistanceCheckInterval, true);
    }

    UFUNCTION()
    void RegisterEnemy(AEnemyCharacter* Enemy)
    {
        if (!Enemy) return;
        // 避免重复注册
        if (!TrackedEnemies.ContainsByPredicate(
            [Enemy](const TWeakObjectPtr<AEnemyCharacter>& E) { return E.Get() == Enemy; }))
        {
            TrackedEnemies.Add(Enemy);
        }
    }

    UFUNCTION()
    void UnregisterEnemy(AEnemyCharacter* Enemy)
    {
        TrackedEnemies.RemoveAll(
            [Enemy](const TWeakObjectPtr<AEnemyCharacter>& E) { return E.Get() == Enemy; });
    }

private:
    void CheckEnemyDistances()
    {
        const FVector MyLocation = GetActorLocation();

        for (int32 i = TrackedEnemies.Num() - 1; i >= 0; --i)
        {
            AEnemyCharacter* Enemy = TrackedEnemies[i].Get();
            if (!Enemy)
            {
                TrackedEnemies.RemoveAt(i); // 自动清理已销毁的对象
                continue;
            }

            float DistSq = FVector::DistSquared(MyLocation, Enemy->GetActorLocation());
            if (DistSq < FMath::Square(1000.0f))
            {
                Enemy->ActivateNearPlayer();
            }
            else
            {
                Enemy->DeactivateFromPlayer();
            }
        }
    }
};
```

**性能对比**（场景中有 500 个 Enemy）：
```
stat unit 输出:

Bad 版本: Game Thread = 24.3 ms  (GetAllActorsOfClass 每帧 500 个 Actor = ~18ms)
Good 版本: Game Thread = 0.8 ms  (Timer 每 0.5 秒一次, 500 个 Actor = ~2ms, 分摊到每帧 ~0.13ms)
```

### 示例 B：Blueprint 重计算 → C++ BlueprintCallable

```cpp
// BlueprintPitfall_HeavyMath.cpp
// 问题：蓝图中的大量 Vector/Matrix 运算慢 10-100x
// 解决：将热路径计算移到 C++，标记为 BlueprintCallable

UCLASS()
class UMathOperations : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    // ❌ 这段逻辑在蓝图中实现会非常慢：
    //    对 1000 个变换做骨骼矩阵计算
    //
    // ✅ 在 C++ 中实现，蓝图只需调用这个函数

    /** 批量计算骨骼世界变换（蒙皮前的预处理） */
    UFUNCTION(BlueprintCallable, Category = "Animation|Optimization",
        meta = (DisplayName = "Compute Bone World Transforms (Fast)"))
    static void ComputeBoneWorldTransforms(
        const TArray<FTransform>& BoneLocalTransforms,
        const TArray<int32>& BoneParentIndices,
        TArray<FTransform>& OutWorldTransforms)
    {
        const int32 BoneCount = BoneLocalTransforms.Num();
        OutWorldTransforms.SetNum(BoneCount);

        for (int32 i = 0; i < BoneCount; ++i)
        {
            const int32 ParentIdx = BoneParentIndices[i];
            if (ParentIdx < 0)
            {
                OutWorldTransforms[i] = BoneLocalTransforms[i]; // Root bone
            }
            else
            {
                // ✅ C++ 中的 FTransform 乘法是 SIMD 优化的
                OutWorldTransforms[i] = BoneLocalTransforms[i] * OutWorldTransforms[ParentIdx];
            }
        }
    }

    /** 批量计算点到光源的距离（排序前预处理） */
    UFUNCTION(BlueprintCallable, Category = "Rendering|Optimization",
        meta = (DisplayName = "Compute Point Light Distances (Fast)"))
    static void ComputePointLightDistances(
        const TArray<FVector>& PointPositions,
        const FVector& LightPosition,
        TArray<float>& OutDistancesSq)
    {
        const int32 Count = PointPositions.Num();
        OutDistancesSq.SetNum(Count);

        for (int32 i = 0; i < Count; ++i)
        {
            // ✅ FVector::DistSquared 是 SIMD 优化的（SSE/NEON）
            OutDistancesSq[i] = FVector::DistSquared(PointPositions[i], LightPosition);
        }
    }

    /** 高开销的几何查询 — 蓝图不应该在 Tick 中调用 */
    UFUNCTION(BlueprintCallable, Category = "AI|Optimization",
        meta = (DisplayName = "Batch Line Trace (Fast)"))
    static int32 BatchLineTrace(
        UWorld* World,
        const TArray<FVector>& StartPoints,
        const FVector& EndPoint,
        TArray<bool>& OutHitResults)
    {
        if (!World) return 0;

        const int32 Count = StartPoints.Num();
        OutHitResults.SetNum(Count);

        int32 HitCount = 0;
        FCollisionQueryParams QueryParams;
        QueryParams.bTraceComplex = false; // ✅ 使用 Simple Collision

        for (int32 i = 0; i < Count; ++i)
        {
            FHitResult Hit;
            bool bHit = World->LineTraceSingleByChannel(
                Hit, StartPoints[i], EndPoint, ECC_Visibility, QueryParams);
            OutHitResults[i] = bHit;
            if (bHit) HitCount++;
        }

        return HitCount;
    }
};

// 蓝图使用方式:
// 1. 在 Event Graph 中拖入 "Compute Bone World Transforms (Fast)" 节点
// 2. 传入 BoneLocalTransforms 和 BoneParentIndices 数组
// 3. 得到 OutWorldTransforms —— 比纯蓝图实现快 10-50 倍
```

### 示例 C：碰撞优化

```cpp
// CollisionOptimization.cpp
#include "Components/StaticMeshComponent.h"
#include "PhysicsEngine/BodySetup.h"

// 运行时分析碰撞设置
void AnalyzeCollisionSettings(AActor* TargetActor)
{
    if (!TargetActor) return;

    TArray<UStaticMeshComponent*> MeshComponents;
    TargetActor->GetComponents<UStaticMeshComponent>(MeshComponents);

    int32 SimpleCount = 0;
    int32 ComplexCount = 0;
    int32 TotalTriangles_Complex = 0;

    for (UStaticMeshComponent* Mesh : MeshComponents)
    {
        if (!Mesh || !Mesh->GetStaticMesh()) continue;

        UBodySetup* BodySetup = Mesh->GetBodySetup();
        if (!BodySetup) continue;

        // 检查碰撞复杂度设置
        ECollisionTraceFlag TraceFlag = BodySetup->CollisionTraceFlag;

        switch (TraceFlag)
        {
        case CTF_UseSimpleAsComplex:
            SimpleCount++;
            UE_LOG(LogTemp, Log, TEXT("  [OK] %s: Simple collision only"),
                *Mesh->GetName());
            break;

        case CTF_UseComplexAsSimple:
            ComplexCount++;
            {
                // 获取复杂碰撞的三角形数量
                if (Mesh->GetStaticMesh()->GetRenderData())
                {
                    for (const FStaticMeshLODResources& LOD :
                        Mesh->GetStaticMesh()->GetRenderData()->LODResources)
                    {
                        TotalTriangles_Complex += LOD.GetNumTriangles();
                    }
                }
                UE_LOG(LogTemp, Warning, TEXT("  [WARN] %s: Complex collision! Triangles: %d"),
                    *Mesh->GetName(),
                    TotalTriangles_Complex);
            }
            break;

        case CTF_UseDefault:
            // 取决于 Convex Decomposition 设置
            UE_LOG(LogTemp, Log, TEXT("  [Info] %s: Default (Simple unless Complex specified)"),
                *Mesh->GetName());
            break;
        }
    }

    UE_LOG(LogTemp, Log, TEXT("=== Collision Analysis for %s ==="), *TargetActor->GetName());
    UE_LOG(LogTemp, Log, TEXT("  Simple Collision:  %d meshes"), SimpleCount);
    UE_LOG(LogTemp, Log, TEXT("  Complex Collision: %d meshes (%d total triangles)"),
        ComplexCount, TotalTriangles_Complex);

    if (ComplexCount > 0)
    {
        UE_LOG(LogTemp, Warning,
            TEXT("Recommendation: Convert complex collision meshes to simple convex/capsule/sphere shapes"));
    }
}

// 运行时调整碰撞 Channel
void OptimizeCollisionChannels(UPrimitiveComponent* Component, bool bIsImportant)
{
    if (!Component) return;

    if (bIsImportant)
    {
        // 重要对象：响应所有碰撞
        Component->SetCollisionResponseToAllChannels(ECR_Block);
    }
    else
    {
        // 不重要对象（如装饰物）：只响应关键 Channel
        Component->SetCollisionResponseToAllChannels(ECR_Ignore);
        Component->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
        Component->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
        // 其他 Channel（如 Visibility, Camera, Pawn）全部 Ignore
    }
}

// 在游戏中切换碰撞预设
void SetLowQualityCollisionForDistantActors(UWorld* World, float CullDistance)
{
    APlayerController* PC = World->GetFirstPlayerController();
    if (!PC) return;

    FVector PlayerLocation = PC->GetPawn() ? PC->GetPawn()->GetActorLocation() : FVector::ZeroVector;

    for (TActorIterator<AActor> It(World); It; ++It)
    {
        AActor* Actor = *It;
        float DistSq = FVector::DistSquared(Actor->GetActorLocation(), PlayerLocation);

        if (DistSq > FMath::Square(CullDistance))
        {
            // 远处对象：禁用碰撞
            Actor->SetActorEnableCollision(false);
        }
        else
        {
            Actor->SetActorEnableCollision(true);
        }
    }
}
```

### 示例 D：Animation Blueprint 性能优化

```cpp
// AnimationOptimization.cpp
#include "Animation/AnimInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"

// Animation Budget Allocator — UE5 内置的动画 LOD 系统
// 启用方式（在项目设置中或通过代码）：

void EnableAnimationBudgetAllocator(UWorld* World)
{
    // Animation Budget Allocator 在 UE 5.1+ 中以插件形式提供
    // Plugins → Animation → Animation Budget Allocator (启用)
    // 然后通过 CVar 配置：
    //
    // a.Budget.Enabled 1                          — 启用系统
    // a.Budget.BudgetMs 2.0                       — 每帧动画预算（毫秒）
    // a.Budget.MinQuality 0                       — 最低动画质量（0=最低）
    // a.Budget.MaxTickRate 10                      — 最远角色的最大 Tick 频率（Hz）
    // a.Budget.WorkFactor 1.0                      — 中距角色的质量系数
    //
    // 系统自动为：
    //   近处角色 → 全频率、高质量动画
    //   中距角色 → 降低的更新频率
    //   远处角色 → 可能以 3-5 Hz 更新，最低质量动画
}

// 在 C++ 中控制动画更新频率
UCLASS()
class UMyAnimInstance : public UAnimInstance
{
    GENERATED_BODY()

public:
    virtual void NativeUpdateAnimation(float DeltaSeconds) override
    {
        Super::NativeUpdateAnimation(DeltaSeconds);

        // ✅ 距离衰减更新逻辑
        AActor* Owner = GetOwningActor();
        if (!Owner) return;

        APlayerController* PC = Owner->GetWorld()->GetFirstPlayerController();
        if (!PC || !PC->GetPawn()) return;

        float DistToPlayer = FVector::Dist(Owner->GetActorLocation(), PC->GetPawn()->GetActorLocation());

        // 根据距离决定更新频率
        if (DistToPlayer > 5000.0f)
        {
            // 超过 50 米的角色：每 3 帧更新一次
            static int32 FrameSkip = 0;
            FrameSkip = (FrameSkip + 1) % 3;
            if (FrameSkip != 0) return;
        }

        // 正常更新动画数据
        UpdateSpeed();
        UpdateDirection();
        UpdateAimOffset();
    }

private:
    void UpdateSpeed()
    {
        AActor* Owner = GetOwningActor();
        if (Owner)
        {
            Speed = Owner->GetVelocity().Size();
        }
    }

    void UpdateDirection()
    {
        AActor* Owner = GetOwningActor();
        if (Owner)
        {
            FVector Vel = Owner->GetVelocity();
            Direction = Vel.IsNearlyZero() ? 0.0f :
                FMath::RadiansToDegrees(FMath::Atan2(Vel.Y, Vel.X));
        }
    }

    void UpdateAimOffset()
    {
        // 仅在角色可见时更新瞄准偏移
        AActor* Owner = GetOwningActor();
        if (Owner && Owner->WasRecentlyRendered(0.1f))
        {
            // 执行昂贵的骨骼变换计算
            AimPitch = FMath::Clamp(GetOwningComponent()->GetComponentRotation().Pitch, -90.0f, 90.0f);
            AimYaw = GetOwningComponent()->GetComponentRotation().Yaw;
        }
    }

    UPROPERTY(BlueprintReadOnly, Category = "Animation")
    float Speed = 0.0f;

    UPROPERTY(BlueprintReadOnly, Category = "Animation")
    float Direction = 0.0f;

    UPROPERTY(BlueprintReadOnly, Category = "Animation")
    float AimPitch = 0.0f;

    UPROPERTY(BlueprintReadOnly, Category = "Animation")
    float AimYaw = 0.0f;
};
```

---
## 3. 练习

### 练习 1: Tick 审计

1. 打开你的项目，在编辑器中运行 `stat game`
2. 找到 Tick 耗时最高的 5 个类
3. 对每个类检查：
   - 它真的需要每帧执行吗？是否可以换成 Timer？
   - 如果必须 Tick，它是否在不可见时做了无用功？
   - Tick 中是否包含 `GetAllActorsOfClass`、`FindComponentByClass`、或 Cast？
4. 选择一个最严重的类进行优化（参考示例 A）
5. 用 `stat unit` 测量优化前后的 GameThread 时间差

### 练习 2: 蓝图到 C++ 迁移

1. 在你的项目中找一个蓝图中包含循环/数学运算的节点（如 ForEachLoop + 大量 Vector 运算）
2. 在 C++ 中实现等效逻辑的 `BlueprintCallable` 函数（参考示例 B）
3. 替换蓝图逻辑为调用 C++ 函数
4. 使用 Unreal Insights 录制迁移前后的性能对比：
   - 迁移前：蓝图 Tick 耗时
   - 迁移后：C++ 函数调用耗时
5. 计算加速比并回答：你的具体场景中 C++ 比蓝图快了多少倍？是否符合 10-100x 的预期范围？如果不符，为什么？

### 练习 3: 碰撞审计与优化（可选）

1. 使用示例 C 中的 `AnalyzeCollisionSettings` 函数审计你的关卡中所有 `StaticMeshComponent`
2. 对标记为 `[WARN]` 的组件：
   - 在 Static Mesh Editor 中为它们生成 Simple Collision（Convex Decomposition）
   - 或者手动放置 Box/Sphere/Capsule 碰撞体
3. 用 `stat physics` 测量修改前后的物理耗时
4. 实验：在 `Collision` → `Preset` 中测试 `NoCollision` vs `BlockAll` 的性能差异（在 500 个实例的场景中）
5. 记录你的发现：减少复杂碰撞体后，物理 Tick 时间降低了多少？

---
## 4. 扩展阅读

- **UE5 官方文档 — Actor Tick**: https://docs.unrealengine.com/5.3/en-US/actor-ticking-in-unreal-engine/
- **UE5 官方文档 — Blueprint Performance**: https://docs.unrealengine.com/5.3/en-US/blueprint-best-practices-in-unreal-engine/
- **UE5 官方文档 — Animation Budget Allocator**: https://docs.unrealengine.com/5.3/en-US/animation-budget-allocator-in-unreal-engine/
- **UE5 官方文档 — Collision**: https://docs.unrealengine.com/5.3/en-US/collision-in-unreal-engine/
- **"Blueprint Nativization: Why It's Deprecated and What to Do Instead"** — Epic Developer Community
- **UE5 源码**: `Engine/Source/Runtime/Engine/Private/Actor.cpp` — 查看 Actor::Tick 的完整实现

---
## 常见陷阱

1. **`bCanEverTick = true` 的传染性**：很多开发者不知道 `bCanEverTick` 不仅影响 Actor 本身，还影响附着的 Component。如果你创建的 Actor 不需要 Tick，在构造函数中明确设置 `PrimaryActorTick.bCanEverTick = false`——不要依赖默认行为。

2. **蓝图 Cast 的结果没有缓存**：蓝图 Cast 的结果每次都是一个新节点求值。如果你在 Tick 中对同一个对象反复 Cast，每次都需要类型查找。解决方案：第一次 Cast 后，将结果存入变量，后续使用变量。

3. **Construction Script 中的 `SpawnActor`**：这是最常见的编辑器卡顿原因。如果在 Construction Script 中 Spawn，每次在编辑器中移动该 Actor 都会生成一个新实例——而且旧实例不会被自动清理。在 BeginPlay 中创建运行时对象，Construction Script 只处理可视化设置。

4. **`GetAllActorsOfClass` 在 Tick 中**：它的成本是 O(N)，其中 N = 世界中所有 Actor 的数量。在 Tick 中调用相当于每帧遍历整个 Actor 列表。替代方案：自己维护数组（Actor 注册/注销模式）或使用 `TArray<AActor*>` 的 `Overlap` 查询。

5. **Animation Blueprint Event Graph 的隐藏成本**：很多动画师在 Event Graph 中做 AI 决策——这是最糟糕的组合：Blueprint VM + 每帧执行 + 每个 AI 角色独立执行。AI 决策应该放在 C++ 或行为树中，Animation Blueprint 只应做动画混合。

6. **Collision Preset 的默认 `BlockAll`**：很多蓝图 Actor 的根组件默认是 `BlockAll`——即使它们只是视觉效果。如果你有 2000 个装饰性 Actor 都响应所有碰撞通道，物理系统需要每帧对所有可能的碰撞对做粗检测。将非交互对象的碰撞预设改为 `NoCollision` 或 `OverlapAllDynamic`（如果需要触发 Overlap 事件而非物理响应）。
