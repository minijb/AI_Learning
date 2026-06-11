---
title: "UE 内存管理与 GC"
updated: 2026-06-05
---

# UE 内存管理与 GC
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50 分钟
> 前置知识: 34-ue-low-level.md、C++ 内存管理基础
---
## 1. 概念讲解

### 为什么需要这个？

UE 的内存管理是一个双层系统：底层是自定义的物理内存分配器（FMalloc），上层是 UObject 垃圾回收（GC）。如果你不理解这两层如何协作，你会在项目中面对两类致命问题：

1. **GC 卡顿**：GC 在运行时不定期触发（默认每 61.1 秒或内存超过阈值），如果 GC 扫描了大量对象，它会导致 50-200ms 的卡顿——这在 60fps 游戏中就是 3-12 帧的停顿。
2. **内存泄漏**：UObject 的引用计数看似自动管理，但循环引用、强引用未清理、异步加载未释放都会导致内存持续增长，直到 OOM 崩溃。

一个典型的 UE5 项目在加载一个关卡后可能占用 2-4 GB 内存。如果你不理解内存分配的底层机制和 GC 的触发策略，你的游戏在主机和低配 PC 上就会崩溃或被系统杀死。

### 核心思想

#### FMalloc 层 — 物理内存分配器

UE 的 `FMalloc` 是可替换的物理内存分配器。默认使用 `FMallocBinned2`：

- **FMallocBinned2**（默认）：将分配请求按大小分桶（bins），每桶维护独立的空闲链表。比系统 `malloc` 快得多，且减少碎片。
- **FMallocAnsi**：直接包装系统 `malloc/free`，主要用于调试对比。
- **FMallocStomp**：在每个分配周围添加保护页，用于检测越界访问——性能极差，仅在 Debug 时使用。
- **FMallocMimalloc**：使用微软的 mimalloc，在某些 Load/Free 交替负载下表现更好。

**FMallocBinned2 的分桶策略**：
```
Size ≤ 16KB: 每个桶 16 字节递增，共 1024 个桶
           桶分配在固定大小的 Pool 中（64KB per pool）
Size > 16KB: 直接向 OS 请求（mmap/VirtualAlloc）
           释放后立即返回给 OS
```

**关键 API**：
```cpp
// 不要直接 new/delete UObject — 使用 NewObject<T>()
// 对于非 UObject 的 C++ 对象，可以使用：
void* Ptr = FMemory::Malloc(Size, Alignment);
FMemory::Free(Ptr);
// 或者直接用 UE 容器（TArray、TMap）

// 此 UObject 不会被 GC 追踪
// 该对象没有引用计数，纯粹由你手动管理生命周期
```

但这不意味着你应该到处用手动 `Malloc/Free`——UE 的 `TArray`、`TMap`、`TSharedPtr` 等容器已经封装了分配器。

#### UObject GC 层 — Mark-and-Sweep with Clusters

所有继承自 `UObject` 的对象都被 GC 追踪。GC 使用**标记-清除**算法：

**第一阶段 — 标记 (Mark)**：
从根集（Root Set）开始，递归遍历所有可达的 UObject。根集包括：
- `UGameInstance`
- `UGameViewportClient`
- `UWorld`
- 显式调用 `AddToRoot()` 的任何 UObject
- 加载的 Package (`UPackage`)
- 静态/全局 `UObject*` 指针（通过 `TObjectPtr` 声明）

**第二阶段 — 清除 (Sweep)**：
所有未被标记的 UObject 被判定为不可达，调用 `ConditionalBeginDestroy()` → `BeginDestroy()` → `FinishDestroy()` 路径销毁。

**Clusters（集群）**：UE5 将不包含外部引用的子对象图合并为一个 Cluster。如果整个 Cluster 都不可达，GC 可以在一次操作中释放整个 Cluster，而不需要逐个遍历其中的对象。这在大型场景（蓝图 Actor 包含数百个 Component）中显著减少了 GC 时间。

#### GC 的触发条件

1. **时间触发**：默认每 61.1 秒（可配置）
2. **内存阈值**：`MaxObjectsNotConsideredByGC` 或 `SizeOfPermanentObjectPool` 超出
3. **关卡切换**：`UEngine::LoadMap()` 调用前后
4. **手动触发**：`GEngine->ForceGarbageCollection(true)`

#### 避免 GC 卡顿的策略

| 策略 | 说明 |
|------|------|
| **对象池** | 预创建对象并重复使用，避免频繁创建/销毁和 GC 扫描 |
| **减少根集引用** | 避免不必要的 `AddToRoot()` |
| **USTRUCT 替代 UObject** | 纯数据不需要 GC 时，用 `USTRUCT` 代替 `UObject` |
| **TWeakObjectPtr** | 指回 UObject 但不阻止 GC 销毁它 |
| **GC 集群** | 优化对象图的拓扑结构，让子对象形成孤立 Cluster |
| **分帧 GC** | 将 GC 工作分摊到多帧（Time-Based GC） |

#### LLM — Low Level Memory Tracker

LLM 是 UE 内置的低层级内存追踪器，按"标签"分类所有内存分配：

```cpp
LLM_SCOPE(ELLMTag::Animation);  // 从此行到作用域结束，所有分配归类到 Animation
```

**开启方式**：
- 命令行：`-LLM`
- 运行时：`stat LLM` 和 `stat LLMFULL`

#### Memory Insights

Unreal Insights 的 Memory 视图提供了完整的内存时间线，包括：
- 每帧的分配/释放事件
- 按 Tag 分组的内存使用量
- GC 事件的时间点
- 内存峰值和泄漏分析

---
## 2. 代码示例

### 示例 A：LLM 作用域标签

```cpp
// LLMScopeExample.cpp
#include "CoreMinimal.h"
#include "HAL/LowLevelMemTracker.h"
#include "Engine/Engine.h"

// 定义自定义 LLM Tag（在项目 .h 中声明一次）
// 这些 Tag 在 LLM 报告中显示你的子系统内存使用
LLM_DEFINE_TAG(MyGameWeapons, TEXT("MyGame/Weapons"), TEXT("Game"), GET_STATFNAME(STAT_MyGameWeaponsLLM));
LLM_DEFINE_TAG(MyGameAbilities, TEXT("MyGame/Abilities"), TEXT("Game"), GET_STATFNAME(STAT_MyGameAbilitiesLLM));

class FWeaponCache
{
    TArray<uint8> CachedData;

    void RefreshCache()
    {
        // 从此行开始，所有内存分配都归类到 MyGameWeapons
        LLM_SCOPE(MyGameWeapons);

        CachedData.SetNum(1024 * 1024 * 5); // 5 MB

        for (int32 i = 0; i < CachedData.Num(); ++i)
        {
            CachedData[i] = static_cast<uint8>(i % 256);
        }

        UE_LOG(LogTemp, Log, TEXT("[LLM] Weapon cache allocated %d bytes under MyGameWeapons tag"),
            CachedData.Num());
    }
    // LLM_SCOPE 在作用域结束时自动恢复上一个 Tag
};

class FAbilitySystem
{
    TMap<FName, TArray<FVector>> AbilityPathData;

    void PrecomputePaths()
    {
        LLM_SCOPE(MyGameAbilities);

        for (const FName& AbilityName : { TEXT("Dash"), TEXT("Leap"), TEXT("Teleport") })
        {
            TArray<FVector>& Path = AbilityPathData.Add(AbilityName);
            Path.SetNum(1000);
            for (int32 i = 0; i < Path.Num(); ++i)
            {
                Path[i] = FVector(
                    FMath::FRandRange(-5000, 5000),
                    FMath::FRandRange(-5000, 5000),
                    FMath::FRandRange(0, 1000)
                );
            }
        }
    }
};

void RunLLMExample()
{
    FWeaponCache Weapons;
    Weapons.RefreshCache();

    FAbilitySystem Abilities;
    Abilities.PrecomputePaths();

    UE_LOG(LogTemp, Log, TEXT("LLM example complete — check 'stat LLMFULL' in console"));
}
// 运行方式：以 -LLM 参数启动编辑器/游戏，然后在控制台输入：
// stat LLMFULL
// 你会在报告中看到 MyGame/Weapons 和 MyGame/Abilities 标签
```

### 示例 B：UObject 对象池

```cpp
// ObjectPoolExample.cpp
#include "CoreMinimal.h"
#include "UObject/ObjectPool.h"
#include "GameFramework/Actor.h"

// Step 1: 定义一个可池化的 Actor
UCLASS()
class AMyPooledProjectile : public AActor
{
    GENERATED_BODY()

public:
    UPROPERTY()
    float Speed = 1500.0f;

    UPROPERTY()
    float Damage = 25.0f;

    UPROPERTY()
    float Lifetime = 2.0f;

    UFUNCTION()
    void Initialize(float InSpeed, float InDamage)
    {
        Speed = InSpeed;
        Damage = InDamage;
        SetActorHiddenInGame(false);
        SetActorTickEnabled(true);
        SetLifeSpan(Lifetime); // UE 内置的生命周期管理
    }

    UFUNCTION()
    void ReturnToPool()
    {
        SetActorHiddenInGame(true);
        SetActorTickEnabled(false);
        SetActorLocation(FVector::ZeroVector);
        // 停止所有计时器/特效
        SetLifeSpan(0.0f); // 重置自动销毁
    }

    virtual void Tick(float DeltaTime) override
    {
        Super::Tick(DeltaTime);
        FVector NewLocation = GetActorLocation() + GetActorForwardVector() * Speed * DeltaTime;
        SetActorLocation(NewLocation);
    }
};

// Step 2: 对象池管理器
class FProjectilePool
{
    TArray<AMyPooledProjectile*> AvailableProjectiles;

public:
    ~FProjectilePool()
    {
        // 销毁所有池化对象
        for (AMyPooledProjectile* Proj : AvailableProjectiles)
        {
            if (IsValid(Proj))
            {
                Proj->Destroy();
            }
        }
        AvailableProjectiles.Empty();
    }

    void Prewarm(UWorld* World, int32 PoolSize, TSubclassOf<AMyPooledProjectile> ProjectileClass)
    {
        if (!World || !ProjectileClass.Get()) return;

        for (int32 i = 0; i < PoolSize; ++i)
        {
            FActorSpawnParameters SpawnParams;
            SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

            AMyPooledProjectile* Proj = World->SpawnActor<AMyPooledProjectile>(
                ProjectileClass,
                FVector::ZeroVector,
                FRotator::ZeroRotator,
                SpawnParams
            );

            if (Proj)
            {
                Proj->ReturnToPool();
                AvailableProjectiles.Add(Proj);
            }
        }

        UE_LOG(LogTemp, Log, TEXT("[Pool] Prewarmed %d projectiles (out of %d requested)"),
            AvailableProjectiles.Num(), PoolSize);
    }

    AMyPooledProjectile* Acquire(UWorld* World, const FVector& Location, const FRotator& Rotation,
        float Speed, float Damage, TSubclassOf<AMyPooledProjectile> ProjectileClass)
    {
        AMyPooledProjectile* Proj = nullptr;

        if (AvailableProjectiles.Num() > 0)
        {
            Proj = AvailableProjectiles.Pop();
        }
        else
        {
            // 池子空了，创建新的
            if (!World || !ProjectileClass.Get()) return nullptr;

            FActorSpawnParameters SpawnParams;
            SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

            Proj = World->SpawnActor<AMyPooledProjectile>(ProjectileClass, Location, Rotation, SpawnParams);
            UE_LOG(LogTemp, Warning, TEXT("[Pool] Pool exhausted — spawned extra projectile"));
        }

        if (Proj)
        {
            Proj->SetActorLocation(Location);
            Proj->SetActorRotation(Rotation);
            Proj->Initialize(Speed, Damage);
        }

        return Proj;
    }

    void Release(AMyPooledProjectile* Proj)
    {
        if (!IsValid(Proj)) return;

        Proj->ReturnToPool();
        AvailableProjectiles.Add(Proj);
    }

    int32 GetAvailableCount() const { return AvailableProjectiles.Num(); }
};

// 使用示例
void SimulateCombat(UWorld* World)
{
    static FProjectilePool Pool;
    static bool bInitialized = false;

    if (!bInitialized)
    {
        TSubclassOf<AMyPooledProjectile> ProjectileBP =
            LoadClass<AMyPooledProjectile>(nullptr, TEXT("/Game/Blueprints/BP_Projectile.BP_Projectile_C"));
        Pool.Prewarm(World, 50, ProjectileBP);
        bInitialized = true;
    }

    // 模拟发射 500 发子弹
    for (int32 i = 0; i < 500; ++i)
    {
        AMyPooledProjectile* Proj = Pool.Acquire(
            World,
            FVector(FMath::FRandRange(-500, 500), FMath::FRandRange(-500, 500), 100.0f),
            FRotator(FMath::FRandRange(-30, 30), FMath::FRandRange(0, 360), 0),
            1500.0f + FMath::FRandRange(-200, 200),
            25.0f
        );
        // Proj 会在 LifeSpan 到期后通过 SetLifeSpan 自动销毁
        // 改进版本可以使用 FTimerHandle 在超时后调用 Pool.Release(Proj)
    }

    UE_LOG(LogTemp, Log, TEXT("[Pool] 500 projectiles spawned, available: %d"), Pool.GetAvailableCount());
}
```

### 示例 C：memreport 分析与内存对比

```cpp
// MemoryReportAnalysis.cpp
#include "CoreMinimal.h"
#include "Engine/Engine.h"
#include "UObject/UObjectIterator.h"
#include "UObject/Package.h"

void AnalyzeMemoryByClass()
{
    // 按 UClass 分组统计 UObject 数量和内存使用
    TMap<FName, int32> ObjectCountByClass;
    TMap<FName, SIZE_T> MemoryByClass;

    for (TObjectIterator<UObject> It; It; ++It)
    {
        UObject* Obj = *It;
        if (!Obj) continue;

        UClass* Class = Obj->GetClass();
        if (!Class) continue;

        FName ClassName = Class->GetFName();
        ObjectCountByClass.FindOrAdd(ClassName)++;
        MemoryByClass.FindOrAdd(ClassName) += static_cast<SIZE_T>(Obj->GetResourceSizeBytes(EResourceSizeMode::Exclusive));
    }

    // 按内存使用排序并输出 Top 20
    MemoryByClass.ValueSort([](SIZE_T A, SIZE_T B) { return A > B; });

    UE_LOG(LogTemp, Log, TEXT("=== Memory Usage by Class (Top 20) ==="));
    int32 Rank = 0;
    for (const auto& Pair : MemoryByClass)
    {
        if (Rank >= 20) break;
        Rank++;

        float SizeMB = Pair.Value / (1024.0f * 1024.0f);
        int32 Count = ObjectCountByClass.FindRef(Pair.Key);
        UE_LOG(LogTemp, Log, TEXT("  %2d. %-40s | %6d objects | %8.2f MB"),
            Rank, *Pair.Key.ToString(), Count, SizeMB);
    }
}

// 在控制台调用后的分析方法：
// > memreport -full
// 会生成 YourProject/Saved/Profiling/MemReports/ 下的 .memreport 文件
// 包含：
//   - 按 Class 的内存分布
//   - 按 Package 的内存分布
//   - FMalloc 分配器统计
//   - LLM 标签统计（如果已启用 -LLM）

// CSV 格式的 memreport 可以用 Python 分析：
/*
import csv

def parse_memreport(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    in_classes = False
    class_data = []
    for line in lines:
        if 'Obj List: Class' in line:
            in_classes = True
            continue
        if in_classes and line.strip() == '':
            in_classes = False
            continue
        if in_classes:
            parts = line.strip().split()
            if len(parts) >= 3:
                # Format: ClassName  Count  SizeKB
                class_data.append({
                    'class': parts[0],
                    'count': int(parts[1]),
                    'size_kb': float(parts[2])
                })

    # Sort by size
    class_data.sort(key=lambda x: x['size_kb'], reverse=True)
    for entry in class_data[:10]:
        print(f"{entry['class']:40s} {entry['count']:6d} obj  {entry['size_kb']/1024:8.2f} MB")

# Usage: parse_memreport('Saved/Profiling/MemReports/memreport.txt')
*/
```

### 示例 D：TWeakObjectPtr 防止 GC 循环

```cpp
// WeakPointerExample.cpp
#include "CoreMinimal.h"
#include "UObject/WeakObjectPtr.h"

UCLASS()
class UGameCharacter : public UObject
{
    GENERATED_BODY()
public:
    UPROPERTY()
    FString Name;

    // 危险：强引用会导致循环引用 — GC 无法释放
    // UPROPERTY()
    // UGameCharacter* BestFriend;

    // 安全：弱引用不阻止 GC 销毁对象
    TWeakObjectPtr<UGameCharacter> BestFriend;

    void SetBestFriend(UGameCharacter* NewFriend)
    {
        BestFriend = NewFriend;
    }

    void TalkToBestFriend()
    {
        // 使用前检查对象是否仍然有效
        if (BestFriend.IsValid())
        {
            UE_LOG(LogTemp, Log, TEXT("%s says hi to %s"), *Name, *BestFriend->Name);
        }
        else
        {
            UE_LOG(LogTemp, Log, TEXT("%s's friend is gone..."), *Name);
        }
    }
};

// 验证弱引用行为
void TestWeakPointer()
{
    UGameCharacter* Alice = NewObject<UGameCharacter>();
    Alice->Name = TEXT("Alice");

    UGameCharacter* Bob = NewObject<UGameCharacter>();
    Bob->Name = TEXT("Bob");

    Alice->SetBestFriend(Bob);

    // Bob 仍然有效
    Alice->TalkToBestFriend(); // "Alice says hi to Bob"

    // 手动销毁 Bob
    Bob->ConditionalBeginDestroy();
    Bob = nullptr;

    // GC 后
    CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS);

    Alice->TalkToBestFriend(); // "Alice's friend is gone..."
}
```

---
## 3. 练习

### 练习 1: 内存报告分析

1. 打开一个包含至少一个完整关卡的 UE5 项目
2. 在控制台中执行 `memreport -full`
3. 找到生成的 `.memreport` 文件（`Saved/Profiling/MemReports/`）
4. 识别出：
   - 占用内存最多的前 5 个 Class
   - 占用内存最多的前 3 个 Package
   - Total Physical 内存和 Total Virtual 内存的差值（这是碎片化的指示）
5. 如果发现意外的大内存消耗（比如某个你不需要的子系统占用了 500MB+），记录下并尝试找到原因

### 练习 2: 实现并测量对象池

1. 基于示例 B，为你的项目中最频繁创建/销毁的 Actor 类型实现对象池
2. 使用 `stat startfile` 和 `stat stopfile` 或 Unreal Insights 录制 60 秒的游戏过程：
   - 先使用原始 `SpawnActor/Destroy` 模式
   - 再使用对象池模式
3. 对比两次录制的：总内存分配次数、GC 触发次数、平均帧时间
4. 计算对象池减少的内存抖动百分比

### 练习 3: LLM 标签和内存归类（可选）

1. 为你的项目中的 3 个主要子系统（如武器、AI、UI）添加自定义 LLM Tag
2. 以 `-LLM` 参数启动游戏
3. 在控制台运行 `stat LLMFULL`，截图你的标签出现在报告中
4. 模拟内存压力场景（大量生成 Actor 后销毁），观察你的标签内存曲线的变化
5. 检查是否有内存泄漏：重复压力场景 10 次，看你的标签内存是否持续增长


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **步骤 4 解析 — memreport 解读要点：**
>
> 1. **占用内存最多的前 5 个 Class**：在 `.memreport` 文件的 `Class` 段中按 `Size` 降序查找。典型排名（以 Lyra Starter 为例）：
>    - `StaticMesh` — 关卡中的所有静态网格体
>    - `Texture2D` — 所有 2D 纹理（若包含 GPU 内存，通常占第一）
>    - `SkeletalMesh` — 骨骼网格体及其 LOD
>    - `AnimSequence` — 动画数据（曲线压缩后通常在几 MB）
>    - `Material` / `MaterialInstance` — 材质实例及其 Shader 缓存
>
> 2. **占用内存最多的前 3 个 Package**：在 `Package` 段中按 `Size` 排序。典型排名：
>    - `/Game/Maps/YourLevel` — 关卡本身引用的所有资产
>    - `/Engine/...` — 引擎共享资源（渲染资源、默认材质等）
>    - `/Game/Characters/...` — 角色相关资产（骨骼、动画、纹理）
>
> 3. **Total Physical vs Total Virtual 差值**：Physical = OS 从物理 RAM 分配的量，Virtual = 进程保留的虚拟地址空间（含未提交的）。差值 > 2GB 说明内存碎片化严重——大量小块分配导致虚拟空间膨胀，但物理内存尚未爆满。碎片化会导致分配速度下降（FMalloc 需要更长时间找到合适的空闲块）。
>
> 4. **意外大消耗排查**：
>    - 如果发现 `MediaTexture` 或 `MediaPlayer` 占用 500MB+ → 检查是否有未关闭的视频播放器
>    - 如果发现某个用户目录（如 `/Game/OldAssets`）占用了大量内存 → 考虑清理未使用的资产
>    - 使用 `obj refs name=XXX` 命令追踪具体对象的引用链

> [!tip]- 练习 2 参考答案
> **实现步骤与关键代码补充：**
>
> ```cpp
> // 基于示例 B 的 FProjectilePool，补充测量代码
> // 在游戏 GameMode 或测试 Actor 中添加：
>
> UCLASS()
> class AObjectPoolBenchmark : public AActor
> {
>     GENERATED_BODY()
>
> public:
>     UPROPERTY(EditAnywhere)
>     int32 SpawnCount = 1000;
>
>     UPROPERTY(EditAnywhere)
>     int32 PoolSize = 200;
>
>     UPROPERTY(EditAnywhere)
>     TSubclassOf<AMyPooledProjectile> ProjectileClass;
>
>     // 模式 1: 原始 SpawnActor/Destroy 模式
>     UFUNCTION(BlueprintCallable)
>     void RunSpawnDestroyTest()
>     {
>         TArray<AMyPooledProjectile*> Projectiles;
>         for (int32 i = 0; i < SpawnCount; ++i)
>         {
>             AMyPooledProjectile* Proj = GetWorld()->SpawnActor<AMyPooledProjectile>(
>                 ProjectileClass, FVector::ZeroVector, FRotator::ZeroRotator);
>             Projectiles.Add(Proj);
>         }
>         // 销毁全部 → GC 压力
>         for (AMyPooledProjectile* Proj : Projectiles)
>         {
>             Proj->Destroy();
>         }
>     }
>
>     // 模式 2: 对象池模式
>     UFUNCTION(BlueprintCallable)
>     void RunPoolTest()
>     {
>         FProjectilePool Pool;
>         Pool.Prewarm(GetWorld(), PoolSize, ProjectileClass);
>
>         TArray<AMyPooledProjectile*> Active;
>         for (int32 i = 0; i < SpawnCount; ++i)
>         {
>             Active.Add(Pool.Acquire(GetWorld(), FVector::ZeroVector,
>                 FRotator::ZeroRotator, 1500.0f, 25.0f, ProjectileClass));
>         }
>         // 归还池子
>         for (AMyPooledProjectile* Proj : Active)
>         {
>             Proj->ReturnToPool();
>         }
>     }
> };
> ```
>
> **预期对比数据**（1000 个 Actor 场景）：
>
> | 指标 | Spawn/Destroy | 对象池 | 改善 |
> |------|--------------|--------|------|
> | 内存分配次数 | ~3000-5000 | ~PoolSize（首次） | 95%+ |
> | GC 触发次数（60s） | 2-4 次 | 0-1 次 | 75%+ |
> | 平均帧时间 | +3-8ms spikes | 稳定 <1ms | 大幅减少抖动 |
> | 内存抖动百分比 | 基准 | 减少 80-95% | — |
>
> **关键测量命令**：
> ```bash
> # 录制 Insights
> stat startfile
> # … 运行场景 60 秒 …
> stat stopfile
> # 在 Insights Memory 视图中对比:
> # 1. Alloc/Free 事件计数
> # 2. GC Mark/Sweep 时间戳
> # 3. 每帧分配内存曲线（GC spikes 对比）
> ```

> [!tip]- 练习 3 参考答案（可选）
> **LLM 标签实现步骤：**
>
> ```cpp
> // 1. 在项目头文件中声明三个 LLM Tag
> // MyGameLLMTags.h
> #pragma once
> #include "HAL/LowLevelMemTracker.h"
>
> LLM_DEFINE_TAG(MyGameWeapons,  TEXT("MyGame/Weapons"),  TEXT("Game"), GET_STATFNAME(STAT_MyGameWeaponsLLM));
> LLM_DEFINE_TAG(MyGameAI,       TEXT("MyGame/AI"),       TEXT("Game"), GET_STATFNAME(STAT_MyGameAILLM));
> LLM_DEFINE_TAG(MyGameUI,       TEXT("MyGame/UI"),       TEXT("Game"), GET_STATFNAME(STAT_MyGameUILLM));
>
> // 2. 在各子系统中添加作用域标签
> void AWeapon::Fire()
> {
>     LLM_SCOPE(MyGameWeapons);
>     // 子弹/弹壳/粒子，所有内存分配归类到 Weapons
> }
>
> void UAIController::ProcessDecision()
> {
>     LLM_SCOPE(MyGameAI);
>     // 行为树/黑板/寻路缓存
> }
>
> void UMyHUD::UpdateHealthBar()
> {
>     LLM_SCOPE(MyGameUI);
>     // UI Widget 的动态纹理/材质分配
> }
> ```
>
> **内存泄漏检测方法**：
> 1. 以 `-LLM -LLMCSV` 启动游戏，10 次重复"生成-销毁"压力循环
> 2. 打开 `Saved/Profiling/LLM/*.csv`，筛选 `MyGame/Weapons` 列
> 3. 绘制曲线：X=时间，Y=内存占用
> 4. **泄漏判定**：如果 10 个循环后内存占用持续上升 → 泄漏。如果每次循环后回落到基准线 → 无泄漏
> 5. 额外检查：`stat LLMFULL` → 查看 `MyGame/Weapons` 的 `Current` vs `Peak`——如果 Current 稳定在 Peak 附近说明分配后未释放

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---
## 4. 扩展阅读

- **UE5 官方文档 — Garbage Collection**: https://docs.unrealengine.com/5.3/en-US/garbage-collection-in-unreal-engine/
- **UE5 官方文档 — Low Level Memory Tracker**: https://docs.unrealengine.com/5.3/en-US/low-level-memory-tracker-in-unreal-engine/
- **UE5 源码**: `Engine/Source/Runtime/Core/Public/HAL/MallocBinned2.h` — FMallocBinned2 实现
- **UE5 源码**: `Engine/Source/Runtime/CoreUObject/Private/UObject/GarbageCollection.cpp` — GC 主循环
- **Ben Zeigler (Epic) 的 GC 演讲**: "Object Lifetime and Garbage Collection Best Practices" (Unreal Fest 2023)
- **Memory Insights 文档**: Unreal Insights 中 Memory 视图的使用指南

---
## 常见陷阱

1. **UGameInstance 的子对象泄露**：`UGameInstance` 是整个游戏生命周期的根对象。如果你在 `UGameInstance` 中持有强引用（`UPROPERTY()`），这些子对象会在整个游戏运行期间存活，即使是关卡切换也不会释放。用 `TWeakObjectPtr` 或者确保在关卡切换时清理。

2. **Object Pool 中的引用**：池化对象在被 "返回池子" 后，**必须清理所有外部引用**。如果池中的 `AEnemy` 仍然被 `APlayerController::CurrentTarget` 引用，GC 不会释放它，你会得到"池子里的对象仍然存活但状态未重置"的诡异 Bug。

3. **`GetResourceSizeBytes()` 不是实际物理内存**：这个函数返回的是"你认为你占用了多少"，而不是操作系统报告的物理内存。Tooltip 内存、渲染资源（纹理/网格的 GPU 内存）通常不会被这个函数报告。

4. **CollectGarbage 的性能禁忌**：在 Tick 中调用 `CollectGarbage()` 会毁了你的帧率。`ForceGarbageCollection(true)` 中的 `true` 参数意味着"完全清理"，这可能需要数百毫秒。只在关卡切换、过场动画、加载屏幕时才手动触发 GC。

5. **LLM 未启用时的 LLM_SCOPE**：如果游戏没有以 `-LLM` 启动，`LLM_SCOPE` 是无操作——不会影响性能，但也不会记录任何数据。确认启动参数包含 `-LLM` 后再进行分析。`-LLMCSV` 会额外输出 CSV 文件用于离线分析。
