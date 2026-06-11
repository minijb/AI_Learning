---
title: "UE 线程模型与 Task System"
updated: 2026-06-05
---

# UE 线程模型与 Task System
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 55 分钟
> 前置知识: 34-ue-low-level.md、C++ 多线程基础
---
## 1. 概念讲解

### 为什么需要这个？

UE 不是单线程引擎。从 UE3 开始，渲染就运行在独立线程上；到了 UE5，引擎内部有 10+ 个命名线程同时工作。如果你不理解这个线程模型，你写的代码可能会：在 GameThread 外访问 UObject 导致随机崩溃、在 RenderThread 上做阻塞操作导致 GPU 饥饿、用错了并行 API 导致性能反而变差。

更重要的是，UE 的 Task System 是你对抗 CPU 瓶颈的主要武器。一个 `ParallelFor` 可能让你的蒙皮计算从 8ms 降到 1ms，一个正确的 Task Chain 可以让你异步加载资产的同时不阻塞主循环。但前提是——你必须理解每个线程的角色和线程安全规则。

### 核心思想

#### 命名线程及其角色

| 线程 | 角色 | 你可以做什么 | 绝对不能做什么 |
|------|------|-------------|---------------|
| **GameThread** | 游戏逻辑、蓝图、UObject 生命周期 | 所有 UObject 操作、GameMode、PlayerController | —（但不要阻塞它超过 33ms） |
| **RenderThread** | 渲染命令提交、FRenderResource 管理 | 创建/更新 FRenderResource、提交 RHI 命令 | 访问 UObject、创建/销毁 Actor |
| **RHIThread** | 将渲染命令翻译为 GPU 驱动调用 | —（由引擎管理） | 任何直接操作 |
| **AsyncLoadingThread** | 异步加载资产 | 用 FStreamableManager 触发加载 | 直接访问未加载完成的 UObject |
| **TaskGraph Workers** | 执行 TaskGraph 中的任务（数量 = 逻辑核心数 - 1） | 通过 AsyncTask/ParallelFor 调度 | UObject 访问（除非你在 GameThread 上同步等待） |
| **AudioThread** | 音频处理和混合 | —（引擎管理） | — |

**核心线程安全规则**：
1. **UObject 必须在 GameThread 上访问**（包括读/写属性、调用函数）。唯一的例外是：你在 GameThread 上用 `FGraphEvent` 等待 Task 完成后，可以在 GameThread 上安全读取 Task 写入的数据。
2. **FRenderResource 必须在 RenderThread 或 RHIThread 上操作**。用 `ENQUEUE_RENDER_COMMAND` 将代码调度到 RenderThread。
3. **任何线程都可以通过 `AsyncTask` 和 `ParallelFor` 提交工作**，但这些工作不应该访问 UObject。

#### TaskGraph System

UE 的 Task System 基于 `FTaskGraphInterface`，是所有并行任务的基础：

```
                  ┌─────────────────────┐
                  │    FTaskGraphInterface   │
                  └──────────┬──────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  Named Thread │  │  Worker 0    │  │  Worker N    │
    │  (GameThread) │  │  ...         │  │  ...         │
    └──────────────┘  └──────────────┘  └──────────────┘
```

**三种核心 API**：

1. **`AsyncTask`**：提交一个函数到 TaskGraph，立即返回，不阻塞调用者。
2. **`ParallelFor`**：将范围 `[0, N)` 分割成多个 Chunk，分散到多个 Worker 上并行执行。
3. **`FGraphEvent`**：可组合的依赖链——Task B 必须等 Task A 完成才能开始。

#### 关键数据结构

- **`FGraphEventRef`**：一个 Task 的句柄，可用于等待完成（`Wait()`）或作为后续 Task 的前置依赖。
- **`FGraphEventArray`**：多个 `FGraphEventRef` 的集合，用于表示"等这些全部完成后再开始"。
- **`FTaskGraphInterface::Get().WaitUntilTasksComplete()`**：在 GameThread 上等待 Task 完成。这种等待是**非自旋的**——它会让 GameThread 去执行其他已就绪的 Task，而不是白白空转。

#### ParallelFor 的工作原理

```cpp
// 语法
ParallelFor(NumElements, [&](int32 Index) {
    // 处理第 Index 个元素
    VertexColors[Index] = ComputeColor(Index);
});

// 高开销元素：手动分块
ParallelFor(NumElements, [&](int32 Index) {
    for (int32 Vert = Index * ChunkSize; Vert < (Index + 1) * ChunkSize; ++Vert) {
        // 每个 Chunk 的工作量大，减少调度开销
    }
}, false); // bForceSingleThread = false
```

**调度开销权衡**：如果你的单个迭代只需要几十个 CPU 周期，`ParallelFor` 的分发开销会超过收益。经验法则：每个 Chunk 至少需要 1000 个时钟周期才值得并行化。

#### 线程命名

在 Unreal Insights 和调试器中，UE 的命名线程显示为：
- `GameThread`
- `RenderThread`
- `RHIThread`
- `TaskGraphThreadNP 0`, `TaskGraphThreadNP 1`, ...

自定义线程（使用 `FRunnableThread::Create`）会以你指定的名称显示。

---
## 2. 代码示例

### 示例 A：ParallelFor — 顶点处理

```cpp
// ParallelVertexProcessing.cpp
#include "CoreMinimal.h"
#include "Async/ParallelFor.h"
#include "Rendering/PositionVertexBuffer.h"
#include "HAL/PlatformTime.h"

// 场景：你有一个包含 100 万个顶点的网格，需要对所有顶点做变换/颜色计算
struct FVertexData
{
    FVector3f Position;
    FVector3f Normal;
    FLinearColor Color;
};

void ProcessVerticesSerial(TArray<FVertexData>& Vertices)
{
    for (FVertexData& Vert : Vertices)
    {
        // 模拟复杂的逐顶点计算（如皮肤蒙皮、顶点变形）
        Vert.Position = Vert.Position * 2.0f + Vert.Normal;
        Vert.Color = FLinearColor(
            FMath::Abs(Vert.Position.X),
            FMath::Abs(Vert.Position.Y),
            FMath::Abs(Vert.Position.Z),
            1.0f
        );
        Vert.Normal = Vert.Normal.GetSafeNormal();
    }
}

void ProcessVerticesParallel(TArray<FVertexData>& Vertices)
{
    // ParallelFor 自动将 [0, Vertices.Num()) 分块并分发到 Worker 线程
    ParallelFor(Vertices.Num(), [&Vertices](int32 Index)
    {
        FVertexData& Vert = Vertices[Index];
        Vert.Position = Vert.Position * 2.0f + Vert.Normal;
        Vert.Color = FLinearColor(
            FMath::Abs(Vert.Position.X),
            FMath::Abs(Vert.Position.Y),
            FMath::Abs(Vert.Position.Z),
            1.0f
        );
        Vert.Normal = Vert.Normal.GetSafeNormal();
    });
}

void BenchmarkVertexProcessing()
{
    constexpr int32 VertexCount = 1'000'000;
    TArray<FVertexData> VerticesA, VerticesB;
    VerticesA.SetNum(VertexCount);
    VerticesB.SetNum(VertexCount);

    // 初始化随机顶点
    for (int32 i = 0; i < VertexCount; ++i)
    {
        FVector3f RandomPos(FMath::FRandRange(-100, 100), FMath::FRandRange(-100, 100), FMath::FRandRange(-100, 100));
        FVector3f RandomNormal(FMath::FRandRange(-1, 1), FMath::FRandRange(-1, 1), FMath::FRandRange(-1, 1));
        RandomNormal.Normalize();
        VerticesA[i] = { RandomPos, RandomNormal, FLinearColor::White };
        VerticesB[i] = { RandomPos, RandomNormal, FLinearColor::White };
    }

    // 串行测量
    {
        double StartTime = FPlatformTime::Seconds();
        ProcessVerticesSerial(VerticesA);
        double EndTime = FPlatformTime::Seconds();
        UE_LOG(LogTemp, Log, TEXT("Serial: %.2f ms"), (EndTime - StartTime) * 1000.0);
    }

    // 并行测量
    {
        double StartTime = FPlatformTime::Seconds();
        ProcessVerticesParallel(VerticesB);
        double EndTime = FPlatformTime::Seconds();
        UE_LOG(LogTemp, Log, TEXT("ParallelFor: %.2f ms"), (EndTime - StartTime) * 1000.0);
    }
}
// 预期输出（在 8 核 CPU 上）：
// Serial: ~45 ms
// ParallelFor: ~8 ms  (约 5.6x 加速比，受内存带宽限制）
```

### 示例 B：AsyncTask 与完成回调

```cpp
// AsyncTaskExample.cpp
#include "CoreMinimal.h"
#include "Async/Async.h"
#include "Engine/Engine.h"

// 场景：需要从磁盘加载大量 XML/JSON 配置，在后台线程解析，完成后通知 GameThread

struct FConfigData
{
    TMap<FString, float> WeaponDamageTable;
    TArray<FString> LevelNames;
    int32 VersionNumber = 0;
};

// 注意：此函数运行在 TaskGraph Worker 上，不能访问 UObject
FConfigData ParseConfigFileWorker(const FString& FilePath)
{
    FConfigData Result;
    // 模拟文件读取和解析
    FPlatformProcess::Sleep(0.05f);

    Result.WeaponDamageTable.Add(TEXT("Pistol"), 25.0f);
    Result.WeaponDamageTable.Add(TEXT("Rifle"), 45.0f);
    Result.WeaponDamageTable.Add(TEXT("Shotgun"), 80.0f);
    Result.LevelNames = { TEXT("Level_01"), TEXT("Level_02"), TEXT("Level_Boss") };
    Result.VersionNumber = 3;

    UE_LOG(LogTemp, Log, TEXT("[Worker Thread] ConfigData parsed, version=%d"), Result.VersionNumber);
    return Result;
}

void LoadConfigAsync()
{
    const FString ConfigPath = FPaths::ProjectConfigDir() / TEXT("WeaponData.xml");

    // 方法 1: AsyncTask + 回调
    AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask, [ConfigPath]()
    {
        // 在后台线程执行耗时工作
        FConfigData Data = ParseConfigFileWorker(ConfigPath);

        // 将结果传递回 GameThread
        AsyncTask(ENamedThreads::GameThread, [Data = MoveTemp(Data)]()
        {
            // 现在安全地在 GameThread 上使用数据
            FString WeaponStr;
            for (const auto& Pair : Data.WeaponDamageTable)
            {
                WeaponStr += FString::Printf(TEXT("%s=%.1f, "), *Pair.Key, Pair.Value);
            }
            UE_LOG(LogTemp, Log, TEXT("[GameThread] Config loaded: %s (version %d)"),
                *WeaponStr, Data.VersionNumber);

            // 在这里可以安全地更新 UObject：
            // MyGameInstance->ApplyWeaponConfig(Data);
        });
    });
}

// 方法 2: 使用 Async 高级包装
void LoadConfigAsync_V2()
{
    const FString ConfigPath = FPaths::ProjectConfigDir() / TEXT("WeaponData.xml");

    auto Future = Async(EAsyncExecution::ThreadPool, [ConfigPath]() -> FConfigData
    {
        return ParseConfigFileWorker(ConfigPath);
    });

    // Future 可以通过 .Get() 阻塞等待（不推荐在 GameThread 上这样做）
    // 更好的方式是在 Tick 中轮询 .IsReady()，或使用以下模式：
    // 注意：.Get() 在 GameThread 上是非自旋的——它会执行其他就绪任务
    // FConfigData Result = Future.Get();
}
```

### 示例 C：FGraphEvent 任务依赖链

```cpp
// TaskChainExample.cpp
#include "CoreMinimal.h"
#include "Async/TaskGraphInterfaces.h"

// 场景：游戏启动时需要顺序执行三个步骤，但每个步骤内部可以并行化
// Step A: 解析多个配置文件 (可并行)
// Step B: 在 A 完成后，编译 Shader 变体 (必须在 A 之后)
// Step C: 在 B 完成后，预热粒子系统 (必须在 B 之后)

struct FGameBootData
{
    TArray<FString> ConfigFiles;
    TArray<FString> ShaderVariants;
    TArray<FString> ParticleSystems;
};

void ExecuteStartupTaskChain(const FGameBootData& BootData)
{
    // Step A: 并行解析所有配置文件
    FGraphEventArray ParseTasks;
    for (const FString& ConfigFile : BootData.ConfigFiles)
    {
        FGraphEventRef Task = FFunctionGraphTask::CreateAndDispatchWhenReady(
            [ConfigFile]()
            {
                UE_LOG(LogTemp, Log, TEXT("[Parse] Reading %s..."), *ConfigFile);
                FPlatformProcess::Sleep(0.01f); // 模拟 I/O
            },
            TStatId(),
            nullptr, // 无前置依赖
            ENamedThreads::AnyThread
        );
        ParseTasks.Add(Task);
    }

    // Step B: 等 A 的所有任务完成后，在任意线程执行 Shader 编译
    FGraphEventArray CompileTasks;
    for (const FString& ShaderVariant : BootData.ShaderVariants)
    {
        FGraphEventRef Task = FFunctionGraphTask::CreateAndDispatchWhenReady(
            [ShaderVariant]()
            {
                UE_LOG(LogTemp, Log, TEXT("[Compile] Compiling %s..."), *ShaderVariant);
                FPlatformProcess::Sleep(0.02f); // 模拟编译
            },
            TStatId(),
            &ParseTasks, // 前置依赖：等 A 全部完成
            ENamedThreads::AnyThread
        );
        CompileTasks.Add(Task);
    }

    // Step C: 等 B 全部完成后，在 GameThread 执行最终初始化
    FFunctionGraphTask::CreateAndDispatchWhenReady(
        [&BootData]()
        {
            UE_LOG(LogTemp, Log, TEXT("[GameThread] All startup tasks complete!"));
            UE_LOG(LogTemp, Log, TEXT("  Loaded %d config files"), BootData.ConfigFiles.Num());
            UE_LOG(LogTemp, Log, TEXT("  Compiled %d shader variants"), BootData.ShaderVariants.Num());
            // 现在可以安全地操作 UObject
        },
        TStatId(),
        &CompileTasks, // 前置依赖：等 B 全部完成
        ENamedThreads::GameThread // 强制在 GameThread 执行
    );
}

void TestTaskChain()
{
    FGameBootData Data;
    Data.ConfigFiles = { TEXT("Engine.ini"), TEXT("Game.ini"), TEXT("Input.ini"), TEXT("Scalability.ini") };
    Data.ShaderVariants = { TEXT("Variant_Base"), TEXT("Variant_Shadow"), TEXT("Variant_Reflection") };
    Data.ParticleSystems = { TEXT("PS_Fire"), TEXT("PS_Smoke") };

    ExecuteStartupTaskChain(Data);

    UE_LOG(LogTemp, Log, TEXT("Task chain submitted — main thread continues immediately"));
    // 此时 Step A 正在并行执行，主线程可以继续做其他初始化工作
}

// 输出预期：
// Task chain submitted — main thread continues immediately
// [Parse] Reading Engine.ini...
// [Parse] Reading Game.ini...
// ... (并行执行)
// [Compile] Compiling Variant_Base...   ← 等所有 Parse 完成后
// ...
// [GameThread] All startup tasks complete!
```

### 示例 D：ENQUEUE_RENDER_COMMAND

```cpp
// RenderThreadExample.cpp
#include "RenderingThread.h"
#include "RHIResources.h"

// 自定义渲染资源 — 必须继承 FRenderResource
class FMyCustomTextureResource : public FRenderResource
{
public:
    FTexture2DRHIRef TextureRHI;

    virtual void InitRHI() override
    {
        // 此方法在 RenderThread 上调用
        FRHICommandListImmediate& RHICmdList = FRHICommandListExecutor::GetImmediateCommandList();

        const int32 Width = 256;
        const int32 Height = 256;
        const int32 NumMips = 1;

        FRHITextureCreateDesc Desc = FRHITextureCreateDesc::Create2D(TEXT("MyCustomTexture"))
            .SetExtent(Width, Height)
            .SetFormat(PF_R8G8B8A8)
            .SetNumMips(NumMips)
            .SetFlags(ETextureCreateFlags::ShaderResource);

        TextureRHI = RHICreateTexture(Desc);
        UE_LOG(LogTemp, Log, TEXT("[RenderThread] Custom texture created: %dx%d"), Width, Height);
    }

    virtual void ReleaseRHI() override
    {
        TextureRHI.SafeRelease();
    }
};

// 在 GameThread 上调用，将工作分派到 RenderThread
void UpdateTextureData(FMyCustomTextureResource& Resource, const TArray<FColor>& PixelData)
{
    // MUST 拷贝数据！Lambda 在 RenderThread 上执行，必须捕获值
    // 如果捕获引用，GameThread 可能在 RenderThread 使用前就销毁数据
    TArray<FColor> PixelDataCopy = PixelData;

    ENQUEUE_RENDER_COMMAND(UpdateMyTexture)(
        [&Resource, PixelDataCopy = MoveTemp(PixelDataCopy)](FRHICommandListImmediate& RHICmdList)
        {
            // 此 Lambda 在 RenderThread 上执行
            if (!Resource.TextureRHI.IsValid()) return;

            FUpdateTextureRegion2D Region(0, 0, 0, 0, 256, 256);
            RHICmdList.UpdateTexture2D(
                Resource.TextureRHI,
                0, // MipIndex
                Region,
                256 * sizeof(FColor), // SourcePitch
                (const uint8*)PixelDataCopy.GetData()
            );
            UE_LOG(LogTemp, Log, TEXT("[RenderThread] Texture data updated"));
        });
    // 此函数立即返回——GameThread 不会被阻塞
}
```

---
## 3. 练习

### 练习 1: ParallelFor 基准测试

1. 复制示例 A 中的 `BenchmarkVertexProcessing` 函数
2. 修改它以测试不同的顶点数量（10K、100K、1M、10M）
3. 在每个规模下，对比串行和并行的时间，计算加速比
4. 额外实验：将 `ParallelFor` 的第三个参数 `bForceSingleThread` 设为 `true`，比较其开销
5. 回答：在你的 CPU 上，哪个规模下并行才有收益？为什么？

### 练习 2: 任务依赖链

1. 写三个函数：`ReadFromDisk()`（模拟 I/O, Sleep 50ms）、`DecompressData()`（模拟解压, Sleep 20ms）、`ProcessFinalData()`（在 GameThread 打印结果）
2. 用 `FGraphEvent` 构建依赖链：Read → Decompress → Process
3. 另外创建第二条链：`CalculateHash()`（并行于 Read）→ 等 Read 和 CalculateHash 都完成后才执行 Decompress
4. 验证执行顺序：通过日志时间戳确认依赖关系正确

### 练习 3: 自定义命名线程（可选）

1. 重载 `FRunnable`，创建一个每 100ms 打印一次日志的自定义线程
2. 在 `FRunnable::Init()` 中使用 `FPlatformProcess::SetThreadName(TEXT("MyWorker"))` 设置线程名
3. 在 Unreal Insights 或 Windows Performance Analyzer 中确认你的自定义线程名称出现
4. 实现线程安全的终止机制（使用 `FEvent` 或 `TAtomic<bool>`）


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **ParallelFor 基准测试 — 实验结果与加速比分析**
> 
> **测试代码**：
> ```cpp
> #include "CoreMinimal.h"
> #include "Async/ParallelFor.h"
> #include "HAL/PlatformTime.h"
> 
> void BenchmarkParallelFor()
> {
>     TArray<int32> Sizes = { 10'000, 100'000, 1'000'000, 10'000'000 };
> 
>     for (int32 N : Sizes)
>     {
>         TArray<FVector3f> DataA, DataB;
>         DataA.SetNum(N); DataB.SetNum(N);
>         // 初始化随机数据
>         for (int32 i = 0; i < N; i++)
>         {
>             FVector3f V(FMath::FRand(), FMath::FRand(), FMath::FRand());
>             DataA[i] = V; DataB[i] = V;
>         }
> 
>         // 串行版本
>         double SerialStart = FPlatformTime::Seconds();
>         for (int32 i = 0; i < N; i++)
>         {
>             DataA[i] = DataA[i] * 2.0f + FVector3f(1, 2, 3);
>             DataA[i].Normalize();
>         }
>         double SerialTime = (FPlatformTime::Seconds() - SerialStart) * 1000.0;
> 
>         // 并行版本
>         double ParallelStart = FPlatformTime::Seconds();
>         ParallelFor(N, [&DataB](int32 i)
>         {
>             DataB[i] = DataB[i] * 2.0f + FVector3f(1, 2, 3);
>             DataB[i].Normalize();
>         });
>         double ParallelTime = (FPlatformTime::Seconds() - ParallelStart) * 1000.0;
> 
>         // 单线程并行（bForceSingleThread=true）
>         double SingleThreadParallelStart = FPlatformTime::Seconds();
>         ParallelFor(N, [&DataB](int32 i)
>         {
>             DataB[i] = DataB[i] * 2.0f + FVector3f(1, 2, 3);
>             DataB[i].Normalize();
>         }, true); // bForceSingleThread = true
>         double SingleThreadParallelTime =
>             (FPlatformTime::Seconds() - SingleThreadParallelStart) * 1000.0;
> 
>         double Speedup = SerialTime / ParallelTime;
>         double Overhead = SingleThreadParallelTime - SerialTime;
> 
>         UE_LOG(LogTemp, Log,
>             TEXT("N=%d | Serial: %.3fms | Parallel: %.3fms | "
>                  "SingleThreadParallel: %.3fms | Speedup: %.1fx | Overhead: +%.3fms"),
>             N, SerialTime, ParallelTime, SingleThreadParallelTime,
>             Speedup, Overhead);
>     }
> }
> ```
> 
> **典型结果**（8 核 CPU 参考值）：
> 
> | N | Serial | Parallel | Speedup | SingleThread Overhead |
> |---|--------|----------|---------|----------------------|
> | 10K | 0.15ms | 0.12ms | 1.25x | +0.03ms |
> | 100K | 1.5ms | 0.35ms | 4.3x | +0.05ms |
> | 1M | 15ms | 2.5ms | 6.0x | +0.08ms |
> | 10M | 150ms | 22ms | 6.8x | +0.15ms |
> 
> **分析**：
> - **10K 时无收益（1.25x）**：并行调度开销（~0.03ms）与 4 个 Worker Thread 的唤醒开销接近计算本身。每次迭代只需几十 ns，不值得并行。
> - **100K 时收益明显（4.3x）**：计算时间远大于调度开销，8 核中 ~5-6 核有效工作（其他被系统线程占用）
> - **1M+ 趋于平缓（6-7x）**：内存带宽成为瓶颈（所有核同时读写 TArray，CPU cache 冲突），接近 Amdahl 定律的理论上限
> - **SingleThreadParallel overhead**：每次 `ParallelFor` 的框架开销（lambda 包装、边界检查）约 0.03~0.15ms，对小 N 影响相对大
> 
> **你的 CPU 上的收益阈值**：
> - 计算每个 N 元素的 `(serial_time - parallel_time) / (N / num_cores)`
> - 经验法则：单个迭代 > 1000 CPU 周期（~0.25μs @ 4GHz）才值得并行
> - 即：`serial_time / N > 0.25μs` → 并行有收益

> [!tip]- 练习 2 参考答案
> **任务依赖链 — FGraphEvent 的实现**
> 
> ```cpp
> #include "CoreMinimal.h"
> #include "Async/TaskGraphInterfaces.h"
> #include "HAL/PlatformTime.h"
> 
> void ExecuteStartupTaskChain()
> {
>     // ===== Task 1A: ReadFromDisk（模拟 I/O） =====
>     FGraphEventRef ReadTask = FFunctionGraphTask::CreateAndDispatchWhenReady(
>         []()
>         {
>             UE_LOG(LogTemp, Log, TEXT("[%.3f] ReadFromDisk START"),
>                 FPlatformTime::Seconds());
>             FPlatformProcess::Sleep(0.05f); // 模拟 50ms I/O
>             UE_LOG(LogTemp, Log, TEXT("[%.3f] ReadFromDisk DONE"),
>                 FPlatformTime::Seconds());
>         },
>         TStatId(),
>         nullptr, // 无前置依赖
>         ENamedThreads::AnyThread
>     );
> 
>     // ===== Task 1B: CalculateHash（并行于 ReadFromDisk） =====
>     FGraphEventRef HashTask = FFunctionGraphTask::CreateAndDispatchWhenReady(
>         []()
>         {
>             UE_LOG(LogTemp, Log, TEXT("[%.3f] CalculateHash START"),
>                 FPlatformTime::Seconds());
>             FPlatformProcess::Sleep(0.02f); // 模拟 20ms 哈希计算
>             UE_LOG(LogTemp, Log, TEXT("[%.3f] CalculateHash DONE"),
>                 FPlatformTime::Seconds());
>         },
>         TStatId(),
>         nullptr, // 无前置依赖（与 Read 并行）
>         ENamedThreads::AnyThread
>     );
> 
>     // ===== Task 2: DecompressData（等 Read + Hash 都完成） =====
>     FGraphEventArray Prerequisites;
>     Prerequisites.Add(ReadTask);
>     Prerequisites.Add(HashTask);
> 
>     FGraphEventRef DecompressTask = FFunctionGraphTask::CreateAndDispatchWhenReady(
>         []()
>         {
>             UE_LOG(LogTemp, Log, TEXT("[%.3f] DecompressData START"),
>                 FPlatformTime::Seconds());
>             FPlatformProcess::Sleep(0.02f); // 模拟 20ms 解压
>             UE_LOG(LogTemp, Log, TEXT("[%.3f] DecompressData DONE"),
>                 FPlatformTime::Seconds());
>         },
>         TStatId(),
>         &Prerequisites, // ★ 等 Read + Hash 都完成
>         ENamedThreads::AnyThread
>     );
> 
>     // ===== Task 3: ProcessFinalData（在 GameThread 执行） =====
>     FGraphEventRef ProcessTask = FFunctionGraphTask::CreateAndDispatchWhenReady(
>         []()
>         {
>             UE_LOG(LogTemp, Log, TEXT("[%.3f] ProcessFinalData on GameThread: ALL DONE!"),
>                 FPlatformTime::Seconds());
>         },
>         TStatId(),
>         DecompressTask, // ★ 等 Decompress 完成
>         ENamedThreads::GameThread // ★ 必须在 GameThread 执行
>     );
> 
>     // 等待整个链完成（在 GameThread 上非自旋等待）
>     FTaskGraphInterface::Get().WaitUntilTasksComplete(
>         { ProcessTask }, ENamedThreads::GameThread);
> }
> ```
> 
> **执行时间线验证**（日志输出示例）：
> ```
> [0.000] ReadFromDisk START
> [0.001] CalculateHash START      ← 与 Read 并行！
> [0.021] CalculateHash DONE
> [0.050] ReadFromDisk DONE
> [0.051] DecompressData START     ← 等 Read + Hash 都完成
> [0.071] DecompressData DONE
> [0.071] ProcessFinalData on GameThread: ALL DONE!
> ```
> 
> **关键点**：
> - ReadFromDisk (50ms) 和 CalculateHash (20ms) 同时开始 → wall-clock = max(50, 20) = 50ms
> - 串行版本 = 50 + 20 + 20 = 90ms → 并行节省 40ms (44%)
> - `WaitUntilTasksComplete` 在 GameThread 上是非自旋的——会执行其他就绪 Task，不会浪费 CPU
> - 依赖链通过 `FGraphEventArray` 精确控制——`DecompressTask` 的前提是 `ReadTask && HashTask` 都完成

> [!tip]- 练习 3 参考答案（可选）
> **自定义命名线程 — FRunnable 实现**
> 
> ```cpp
> // MyWorkerThread.h
> #pragma once
> #include "CoreMinimal.h"
> #include "HAL/Runnable.h"
> #include "HAL/RunnableThread.h"
> #include "HAL/Event.h"
> 
> class FMyWorkerThread : public FRunnable
> {
> public:
>     FMyWorkerThread();
>     virtual ~FMyWorkerThread();
> 
>     // FRunnable 接口
>     virtual bool Init() override;
>     virtual uint32 Run() override;
>     virtual void Stop() override;
>     virtual void Exit() override;
> 
>     // 外部控制接口
>     void RequestStop();
>     bool IsRunning() const { return bRunning; }
> 
> private:
>     FRunnableThread* Thread = nullptr;
>     FEvent* StopEvent = nullptr;
>     TAtomic<bool> bRunning{ false };
>     TAtomic<bool> bStopRequested{ false };
> };
> 
> // MyWorkerThread.cpp
> FMyWorkerThread::FMyWorkerThread()
> {
>     // 使用 FEvent 进行线程安全的终止信号
>     StopEvent = FPlatformProcess::GetSynchEventFromPool(false);
> 
>     // 创建线程（自动调用 Init → Run → Exit）
>     Thread = FRunnableThread::Create(
>         this,
>         TEXT("MyWorker"), // ★ 线程名（在 Unreal Insights / 调试器中可见）
>         0,                // 栈大小（0 = 默认）
>         TPri_Normal       // 优先级
>     );
> }
> 
> FMyWorkerThread::~FMyWorkerThread()
> {
>     RequestStop();
>     if (Thread)
>     {
>         Thread->WaitForCompletion(); // 等待线程结束
>         delete Thread;
>         Thread = nullptr;
>     }
>     if (StopEvent)
>     {
>         FPlatformProcess::ReturnSynchEventToPool(StopEvent);
>         StopEvent = nullptr;
>     }
> }
> 
> bool FMyWorkerThread::Init()
> {
>     // ★ 设置线程名（在 Windows / Unreal Insights 中可见）
>     FPlatformProcess::SetThreadName(TEXT("MyWorker"));
> 
>     bRunning = true;
>     UE_LOG(LogTemp, Log, TEXT("[MyWorker] Thread initialized (ID: %d)"),
>         FPlatformTLS::GetCurrentThreadId());
>     return true;
> }
> 
> uint32 FMyWorkerThread::Run()
> {
>     while (!bStopRequested)
>     {
>         UE_LOG(LogTemp, Log, TEXT("[MyWorker] Working... (time: %.1f)"),
>             FPlatformTime::Seconds());
> 
>         // 每 100ms 检查一次终止信号（非忙等）
>         StopEvent->Wait(100); // 等待 100ms 或被 signal
>     }
>     return 0;
> }
> 
> void FMyWorkerThread::Stop()
> {
>     bStopRequested = true;
>     if (StopEvent) StopEvent->Trigger(); // 唤醒 Wait
> }
> 
> void FMyWorkerThread::Exit()
> {
>     bRunning = false;
>     UE_LOG(LogTemp, Log, TEXT("[MyWorker] Thread exiting"));
> }
> 
> void FMyWorkerThread::RequestStop()
> {
>     bStopRequested = true;
>     if (StopEvent) StopEvent->Trigger();
> }
> 
> // === 使用示例 ===
> void TestMyWorker()
> {
>     FMyWorkerThread Worker;
> 
>     UE_LOG(LogTemp, Log, TEXT("[Main] Worker started, waiting 3 seconds..."));
>     FPlatformProcess::Sleep(3.0f);
> 
>     Worker.RequestStop();
>     UE_LOG(LogTemp, Log, TEXT("[Main] Stop requested"));
> }
> ```
> 
> **验证方法**：
> 1. 编译后运行 → 在 Unreal Insights 中查看 Trace
> 2. 找到名为 `MyWorker` 的线程
> 3. 确认每隔 100ms 有一次日志输出
> 4. 确认主线程 RequestStop 后，Worker 线程在 100ms 内退出（Wait 被 Trigger 提前唤醒）
> 5. 在 Windows Performance Analyzer (WPA) 中同样可见 `MyWorker` 线程名
> 
> **线程安全终止的设计要点**：
> - `TAtomic<bool>` 保证 `bStopRequested` 的跨线程可见性（无需 mutex）
> - `FEvent::Wait(100)` 在有超时的等待，避免忙等浪费 CPU
> - `FEvent::Trigger()` 在 RequestStop 中唤醒等待的线程，使其快速响应终止
> - 析构函数中使用 `WaitForCompletion()` 确保线程完全退出后才释放资源

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---
## 4. 扩展阅读

- **UE5 官方文档 — Task System**: https://docs.unrealengine.com/5.3/en-US/tasks-systems-in-unreal-engine/
- **UE5 源码**: `Engine/Source/Runtime/Core/Public/Async/TaskGraphInterfaces.h` — TaskGraph 的完整接口
- **UE5 源码**: `Engine/Source/Runtime/Core/Public/Async/ParallelFor.h` — ParallelFor 实现细节
- **Krzysztof Narkowicz — "Parallelizing the Naughty Dog Engine"**: 了解 AAA 引擎中的任务系统设计，尽管不是 UE，但模式非常相似
- **Unreal Engine 线程命名约定**: Engine/Source/Runtime/Core/Private/HAL/ThreadingBase.cpp

---
## 常见陷阱

1. **在 Task 中访问 UObject**：这是最常见的崩溃原因。UObject 的引用计数和 GC 只能在 GameThread 上安全操作。如果你需要在后台线程访问数据，确保数据是纯 C++ 类型（`TArray<int32>`、`FVector` 等），或使用 `TWeakObjectPtr` + `IsValid()` 检查，并在 GameThread 上锁定。

2. **忘记拷贝捕获的数据**：`ENQUEUE_RENDER_COMMAND` 和 `AsyncTask` 的 Lambda 可能在调用者已经销毁栈帧后才执行。你必须**拷贝**所有需要的数据，而不是捕获引用。UE 的 `MoveTemp` 可以帮助避免不必要的拷贝。

3. **在 GameThread 上 `FGraphEvent::Wait()`**：这是安全的（非自旋，会执行其他就绪任务），但如果你等待的任务依赖一个同样在 GameThread 上执行的任务，就会发生死锁。永远不要在 GameThread 上等待一个需要 GameThread 才能完成的任务。

4. **ParallelFor 的粒度太细**：如果每个迭代只需要几十个 CPU 周期，`ParallelFor` 的任务分发和 Cache Line 冲突的开销会超过并行收益。对于简单循环（如数组初始化），先用串行版本，只有在 Profiler 显示是热点时才考虑并行化。

5. **ENQUEUE_RENDER_COMMAND 的引用捕获**：`ENQUEUE_RENDER_COMMAND` 会在未来某个时间点在 RenderThread 上执行。如果你捕获了局部变量的引用，函数返回后局部变量被销毁，RenderThread 访问的就是悬空引用。永远拷贝，或者确保资源继承自 `FRenderResource`（它的生命周期由渲染线程管理）。
