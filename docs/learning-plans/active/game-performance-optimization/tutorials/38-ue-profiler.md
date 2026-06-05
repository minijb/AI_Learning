---
title: "UE Profiler 工具链 — Insights, Stat, CSV"
updated: 2026-06-05
---

# UE Profiler 工具链 — Insights, Stat, CSV
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 55 分钟
> 前置知识: 35-ue-rendering.md、36-ue-threading.md
---
## 1. 概念讲解

### 为什么需要这个？

没有测量的优化是玄学。在你的游戏掉帧时，"感觉是 AI 太慢了" 和 "AI Tick 耗时 12.3ms，占 GameThread 的 63%" 是两种完全不同的处境。前一个会让你盲目重写 AI 系统却发现帧率毫无改善；后者会精确地告诉你——这里的代码需要优化。

UE 提供了一套从粗到细的 Profiler 工具链：
- **Stat Commands**：即时的聚合统计（"这一帧发生了什么"）
- **Unreal Insights**：全量的逐帧追踪（"过去 30 秒发生了什么"）
- **CSV Profiler**：自动化的性能回归检测（"版本 B 比版本 A 慢了多少"）
- **GPU Visualizer + RenderDoc**：GPU 管线的逐 Pass 分析

熟练使用这套工具链，意味着你从"猜优化"变成"测量-优化-验证"的科学流程。

### 核心思想

#### Stat Commands — 即时统计

Stat 命令分为两类：**Toggle**（开关式）和 **Single-Shot**（一次性）。

| 命令 | 类型 | 内容 |
|------|------|------|
| `stat fps` | Toggle | 仅 FPS 显示 HUD |
| `stat unit` | Toggle | Frame/Game/Draw/GPU 时间分解 |
| `stat game` | Toggle | GameThread 的 Tick 开销分解 |
| `stat gpu` | Toggle | GPU 各渲染 Pass 耗时 |
| `stat scenerendering` | Toggle | 场景渲染 CPU 侧统计 |
| `stat memory` | Toggle | 物理内存和虚拟内存统计 |
| `stat startfile` / `stat stopfile` | Single-Shot | 开始/停止 Unreal Insights 录制 |
| `stat namedevents` | Toggle | 启用/禁用命名事件（影响 Insights 粒度） |

**`stat unit` 解读**：
```
Frame: 16.67 ms  (60 FPS 的预算)
Game:   8.20 ms  ← GameThread 耗时（游戏逻辑 + 提交渲染命令）
Draw:   4.10 ms  ← RenderThread 耗时（场景剔除 + 准备 Draw Call）
GPU:   13.50 ms  ← GPU 渲染耗时（如果 > Frame，说明 GPU 是瓶颈）
```

**关键洞察**：
- 如果 `Game > Frame`：CPU 游戏逻辑是瓶颈
- 如果 `Draw > Frame`：渲染线程是瓶颈（太多 Draw Call 或复杂剔除）
- 如果 `GPU > Frame`：GPU 是瓶颈（Shader 太重、Overdraw 太多、几何体太多）
- 如果 `Frame ≈ GPU` 但 `Game + Draw` 很小：GPU 瓶颈且 CPU 空闲——可以考虑降低画质

#### Unreal Insights — 全量追踪

Insights 的工作原理：
1. **录制会话**：引擎将每帧的事件（Timing Events、Memory Alloc/Free、Asset Load 等）写入二进制 Trace 文件
2. **离线分析**：用 Unreal Insights 应用（`Engine/Binaries/Win64/UnrealInsights.exe`）打开 Trace 文件
3. **交互式探索**：时间轴缩放、线程视图、资产加载视图、内存视图

**录制方式**：

- 方式 1（控制台）：游戏中输入 `stat startfile` 开始录制，`stat stopfile` 停止
- 方式 2（命令行）：
  ```
  YourGame.exe -trace=cpu,frame,bookmark -tracefile=MyTrace.utrace
  ```
- 方式 3（编辑器）：Tools → Unreal Insights → Start Trace

**Trace Channels** 决定了记录哪些数据：
- `cpu`：CPU 计时事件（函数作用域）
- `gpu`：GPU 渲染事件
- `frame`：帧边界标记
- `memory`：内存分配/释放事件
- `loadtime`：资产加载事件
- `bookmark`：书签（自定义标记点）

#### CSV Profiler — 自动化回归检测

CSV Profiler 将性能数据输出为 CSV 文件，主要用于：
- **自动化基准测试**：每晚构建自动运行固定场景，比较性能变化
- **性能回归检测**：新提交后自动检测帧率下降
- **设备对比**：同一场景在多台设备上的性能表

**捕获命令**：
```
YourGame.exe -execcmds="stat startfile, stat fps" -csvCaptureFrames=3000
```

这会录制 3000 帧的 CSV 数据，然后在 `Saved/Profiling/` 下生成 CSV 文件。

#### GPU Visualizer (ProfileGPU)

按下 **Ctrl+Shift+,** 打开 GPU Visualizer 面板。它显示当前帧的所有渲染 Pass 的 GPU 耗时分解，类似于 `stat gpu` 但交互更丰富——你可以展开每个 Pass 查看其子 Pass 的耗时。

#### RenderDoc 集成

UE5 内置了 RenderDoc 插件（需要在 Plugins 中启用）。启用后，在控制台输入 `renderdoc.CaptureAllActivity 1`，然后按 F12 捕获一帧，自动在 RenderDoc 中打开——你可以查看每个 Draw Call、Shader、输入输出纹理。

---
## 2. 代码示例

### 示例 A：自定义 Trace Channel

```cpp
// CustomTraceChannels.h
#pragma once

#include "CoreMinimal.h"
#include "ProfilingDebugging/TraceAuxiliary.h"

// 定义自定义 Trace Channels — 在 Insights 中作为独立分类出现
// 声明（放在 .cpp 或模块 Startup 中）
UE_TRACE_CHANNEL_DEFINE(MyGameplayChannel);

// 或者使用已经定义的 Channel:
// UE_TRACE_CHANNEL_EXTERN(AnimationChannel, ENGINE_API);  // 使用引擎已有的

// 使用示例：
// UE_TRACE_LOG_SCOPED_TODO(MyGameplayChannel, MyGameplay_ProcessAI, 200)  // 需要先定义 Event Spec
```

```cpp
// CustomTraceEvents.cpp
#include "CustomTraceChannels.h"
#include "Trace/Trace.inl"

// Step 1: 注册自定义 Trace Event
// 这定义了在 Insights 中显示的 Event 名称和字段
UE_TRACE_EVENT_BEGIN(Cpu, MyGame_AIThink, NoSync)
    UE_TRACE_EVENT_FIELD(int32, AgentCount)
    UE_TRACE_EVENT_FIELD(float, ThinkDurationMs)
UE_TRACE_EVENT_END()

UE_TRACE_EVENT_BEGIN(Cpu, MyGame_PhysicsQuery, NoSync)
    UE_TRACE_EVENT_FIELD(int32, QueryCount)
    UE_TRACE_EVENT_FIELD(float, MaxQueryTimeMs)
UE_TRACE_EVENT_END()

// Step 2: 在游戏代码中使用
class AMyAIController : public AActor
{
public:
    void ProcessAIThink(const TArray<AActor*>& Agents)
    {
        double StartTime = FPlatformTime::Seconds();

        // 模拟 AI 思考
        for (AActor* Agent : Agents)
        {
            FPlatformProcess::Sleep(0.001f); // 1ms per agent
        }

        double DurationMs = (FPlatformTime::Seconds() - StartTime) * 1000.0;

        // 写入 Trace Event — 在 Insights 时间线上显示为独立的彩色块
        UE_TRACE_LOG(Cpu, MyGame_AIThink, MyGameplayChannel)
            << MyGame_AIThink.AgentCount(Agents.Num())
            << MyGame_AIThink.ThinkDurationMs(static_cast<float>(DurationMs));
    }
};

class UPhysicsProfiler : public UObject
{
public:
    void ProfilePhysicsQuery(const TArray<FVector>& QueryPoints)
    {
        double StartTime = FPlatformTime::Seconds();
        float MaxQueryTime = 0.0f;

        for (const FVector& Point : QueryPoints)
        {
            // 每个查询点一个射线检测
            double QueryStart = FPlatformTime::Seconds();
            FHitResult Hit;
            GetWorld()->LineTraceSingleByChannel(Hit, Point, Point + FVector::UpVector * 100.0f,
                ECC_Visibility);
            float QueryTime = static_cast<float>((FPlatformTime::Seconds() - QueryStart) * 1000.0);
            MaxQueryTime = FMath::Max(MaxQueryTime, QueryTime);
        }

        UE_TRACE_LOG(Cpu, MyGame_PhysicsQuery, MyGameplayChannel)
            << MyGame_PhysicsQuery.QueryCount(QueryPoints.Num())
            << MyGame_PhysicsQuery.MaxQueryTimeMs(MaxQueryTime);
    }
};
```

### 示例 B：自动化基准测试脚本

```cpp
// BenchmarkAutomation.h
#pragma once

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Engine/Engine.h"

// UE 自动化测试框架中的性能测试
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPerfBenchmark_EmptyScene,
    "Project.Benchmarks.EmptyScene",
    EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::PerfFilter)

bool FPerfBenchmark_EmptyScene::RunTest(const FString& Parameters)
{
    // 跑 300 帧，测量平均帧时间
    constexpr int32 WarmupFrames = 60;
    constexpr int32 TestFrames = 240;

    TArray<float> FrameTimes;
    FrameTimes.Reserve(TestFrames);

    for (int32 i = 0; i < WarmupFrames; ++i)
    {
        GEngine->GameViewport->GetWorld()->GetGameViewport()->Draw();
    }

    for (int32 i = 0; i < TestFrames; ++i)
    {
        double FrameStart = FPlatformTime::Seconds();
        GEngine->GameViewport->GetWorld()->GetGameViewport()->Draw();
        double FrameTime = (FPlatformTime::Seconds() - FrameStart) * 1000.0;
        FrameTimes.Add(static_cast<float>(FrameTime));
    }

    // 统计
    float TotalMs = 0.0f;
    float MaxMs = 0.0f;
    float MinMs = FLT_MAX;
    for (float T : FrameTimes)
    {
        TotalMs += T;
        MaxMs = FMath::Max(MaxMs, T);
        MinMs = FMath::Min(MinMs, T);
    }
    float AvgMs = TotalMs / FrameTimes.Num();

    // 分类帧时间
    int32 GoodFrames = 0;   // < 16.67ms (60fps)
    int32 BadFrames = 0;    // > 33.33ms (<30fps)
    for (float T : FrameTimes)
    {
        if (T < 16.67f) GoodFrames++;
        if (T > 33.33f) BadFrames++;
    }

    UE_LOG(LogTemp, Log, TEXT("=== Empty Scene Benchmark ==="));
    UE_LOG(LogTemp, Log, TEXT("  Avg: %.2f ms (%.1f FPS)"), AvgMs, 1000.0f / AvgMs);
    UE_LOG(LogTemp, Log, TEXT("  Min: %.2f ms, Max: %.2f ms"), MinMs, MaxMs);
    UE_LOG(LogTemp, Log, TEXT("  Frames >= 60fps: %d/%d (%.1f%%)"),
        GoodFrames, TestFrames, 100.0f * GoodFrames / TestFrames);
    UE_LOG(LogTemp, Log, TEXT("  Frames <  30fps: %d/%d (%.1f%%)"),
        BadFrames, TestFrames, 100.0f * BadFrames / TestFrames);

    // 性能门槛断言（可配置）
    constexpr float TargetAvgMs = 10.0f; // 100 FPS
    TestTrue(FString::Printf(TEXT("Average frame time %.2f ms <= %.2f ms target"), AvgMs, TargetAvgMs),
        AvgMs <= TargetAvgMs);

    return true;
}
```

### 示例 C：Python 性能回归检测脚本

```python
# regression_check.py — 分析 UE CSV Profiler 输出，检测性能回归
#
# 使用方式:
#   python regression_check.py baseline.csv current.csv --threshold 5.0
#   (检测 current 是否比 baseline 慢超过 5%)

import csv
import sys
import argparse
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class FrameData:
    frame_number: int
    game_thread_ms: float
    render_thread_ms: float
    gpu_ms: float
    frame_ms: float

def parse_csv(filepath: str) -> List[FrameData]:
    """解析 UE CSV Profiler 输出文件"""
    frames: List[FrameData] = []

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                frames.append(FrameData(
                    frame_number=int(row.get('Frame', 0)),
                    game_thread_ms=float(row.get('GameThreadTime', 0)),
                    render_thread_ms=float(row.get('RenderThreadTime', 0)),
                    gpu_ms=float(row.get('GPUTime', 0)),
                    frame_ms=float(row.get('FrameTime', 0)),
                ))
            except (ValueError, KeyError):
                continue

    return frames

def compute_statistics(frames: List[FrameData]) -> Dict[str, float]:
    """计算关键统计指标"""
    if not frames:
        return {}

    # 跳过前 60 帧暖机
    test_frames = frames[60:]

    frame_times = [f.frame_ms for f in test_frames]
    game_times  = [f.game_thread_ms for f in test_frames]
    gpu_times   = [f.gpu_ms for f in test_frames]

    frame_times.sort()
    n = len(frame_times)

    def percentile(sorted_data: List[float], p: float) -> float:
        idx = int(p / 100.0 * (len(sorted_data) - 1))
        return sorted_data[min(idx, len(sorted_data) - 1)]

    return {
        'avg_frame_ms': sum(frame_times) / n,
        'p50_frame_ms': percentile(frame_times, 50),
        'p99_frame_ms': percentile(frame_times, 99),
        'min_frame_ms': min(frame_times),
        'max_frame_ms': max(frame_times),
        'avg_game_ms': sum(game_times) / n,
        'avg_gpu_ms': sum(gpu_times) / n,
        'total_frames': n,
    }

def detect_regression(
    baseline_stats: Dict[str, float],
    current_stats: Dict[str, float],
    threshold_pct: float
) -> List[str]:
    """检测性能回归"""
    regressions: List[str] = []

    metrics = [
        ('avg_frame_ms', 'average frame time', True),  # True = 越大越差
        ('p99_frame_ms', 'P99 frame time', True),
        ('avg_game_ms', 'average game thread time', True),
        ('avg_gpu_ms', 'average GPU time', True),
    ]

    for key, label, higher_is_worse in metrics:
        if key not in baseline_stats or key not in current_stats:
            continue

        baseline_val = baseline_stats[key]
        current_val = current_stats[key]

        if baseline_val == 0:
            continue

        change_pct = (current_val - baseline_val) / baseline_val * 100.0

        if higher_is_worse and change_pct > threshold_pct:
            regressions.append(
                f"REGRESSION: {label}: {baseline_val:.2f} → {current_val:.2f} ms "
                f"(+{change_pct:.1f}%, threshold: {threshold_pct:.1f}%)"
            )
        elif not higher_is_worse and change_pct < -threshold_pct:
            regressions.append(
                f"REGRESSION: {label}: {baseline_val:.2f} → {current_val:.2f} ms "
                f"({change_pct:.1f}%, threshold: {threshold_pct:.1f}%)"
            )

    return regressions

def main():
    parser = argparse.ArgumentParser(description='UE CSV Profiler regression detection')
    parser.add_argument('baseline', help='Baseline CSV file path')
    parser.add_argument('current', help='Current CSV file path')
    parser.add_argument('--threshold', type=float, default=5.0,
                        help='Regression threshold in percent (default: 5.0)')
    args = parser.parse_args()

    print(f"Loading baseline: {args.baseline}")
    baseline_frames = parse_csv(args.baseline)
    baseline_stats = compute_statistics(baseline_frames)

    print(f"Loading current: {args.current}")
    current_frames = parse_csv(args.current)
    current_stats = compute_statistics(current_frames)

    print(f"\n=== Baseline (n={baseline_stats['total_frames']}) ===")
    print(f"  Avg Frame: {baseline_stats['avg_frame_ms']:.2f} ms")
    print(f"  P99 Frame: {baseline_stats['p99_frame_ms']:.2f} ms")

    print(f"\n=== Current  (n={current_stats['total_frames']}) ===")
    print(f"  Avg Frame: {current_stats['avg_frame_ms']:.2f} ms")
    print(f"  P99 Frame: {current_stats['p99_frame_ms']:.2f} ms")

    regressions = detect_regression(baseline_stats, current_stats, args.threshold)

    if regressions:
        print(f"\n*** REGRESSIONS DETECTED (threshold: {args.threshold}%) ***")
        for reg in regressions:
            print(f"  ❌ {reg}")
        sys.exit(1)
    else:
        print(f"\n✅ No regressions detected (threshold: {args.threshold}%)")
        sys.exit(0)

if __name__ == '__main__':
    main()

# 与 UE 配合使用的完整工作流:
#
# 1. 生成 Baseline（基准版本）:
#    YourGame.exe -execcmds="stat startfile" -csvCaptureFrames=3000 -benchmark
#
# 2. 生成 Current（当前版本）:
#    YourGame.exe -execcmds="stat startfile" -csvCaptureFrames=3000 -benchmark
#
# 3. 运行回归检测:
#    python regression_check.py \
#        Saved/Profiling/baseline.csv \
#        Saved/Profiling/current.csv \
#        --threshold 3.0
```

### 示例 D：GPU Visualizer 与 RenderDoc 捕获

```cpp
// GPUProfilingHelpers.cpp
#include "CoreMinimal.h"
#include "Engine/Engine.h"

// 通过代码触发 GPU 捕获
void CaptureGPUFrame()
{
    // 在下一帧触发 GPU Visualizer 捕获
    // 等同于按下 Ctrl+Shift+,
    GEngine->Exec(nullptr, TEXT("ProfileGPU"));

    // 如果启用了 RenderDoc 插件：
    // 在控制台中输入 renderdoc.CaptureAllActivity 1
    // 然后按 F12 捕获帧
}

// 在游戏特定点插入 GPU Profiler 书签
void InsertGPUMarker(const FString& MarkerName)
{
    // 在 GPU 时间线中插入命名标记 — 在 RenderDoc 和 GPU Visualizer 中都可见
    // 等价于 SCOPED_DRAW_EVENT 但更轻量（仅书签，无耗时统计）
    GEngine->Exec(nullptr, *FString::Printf(TEXT("ProfileGPU Bookmark %s"), *MarkerName));
}
```

---
## 3. 练习

### 练习 1: stat 命令实战

1. 打开你的 UE5 项目，进入一个有一定复杂度的关卡
2. 依次运行以下 stat 命令并解读每个：
   - `stat unit` — 哪个部分是瓶颈？（Game/Draw/GPU）
   - `stat game` — GameThread 上哪个 Tick 开销最大？
   - `stat gpu` — GPU 上哪个 Pass 开销最大？
   - `stat memory` — 物理内存和虚拟内存使用量是多少？
   - `stat startfile` → 运行 30 秒 → `stat stopfile`
3. 打开生成的 `.utrace` 文件（用 UnrealInsights.exe），在 Timing 视图中找到开销最大的函数，记录其名称和耗时

### 练习 2: 性能回归检测流水线

1. 设置你的项目以支持 `-execcmds` 和 `-csvCaptureFrames` 启动参数
2. 在当前版本上运行：
   ```
   YourGame.exe YourMap -execcmds="stat startfile" -csvCaptureFrames=2000 -game -windowed -ResX=1280 -ResY=720
   ```
3. 复制生成的 CSV 文件作为 baseline
4. 在场景中添加 100 个额外 Actor（引入性能回归）
5. 再次运行相同命令，获取 current CSV
6. 使用示例 C 中的 Python 脚本检测回归——确认它检测到了帧率下降
7. 移除额外 Actor，重新运行，确认脚本报告 "No regressions"

### 练习 3: 自定义 Trace Channel 集成（可选）

1. 基于示例 A，为你的项目创建 3 个自定义 Trace Event：
   - 你的核心游戏循环
   - 你的 AI 决策系统
   - 你的物理查询
2. 在关键代码路径中调用 `UE_TRACE_LOG`
3. 录制 Insights Trace 并用 UnrealInsights.exe 打开
4. 在 Timing 视图中过滤你的自定义 Channel——确认它们以你期望的颜色/名称出现
5. 实验：给不同的 AI Agent 分配不同的 `AgentCount` 和 `ThinkDurationMs`，在 Insights 中观察模式

---
## 4. 扩展阅读

- **UE5 官方文档 — Unreal Insights**: https://docs.unrealengine.com/5.3/en-US/unreal-insights-in-unreal-engine/
- **UE5 官方文档 — CSV Profiler**: https://docs.unrealengine.com/5.3/en-US/csv-profiler-in-unreal-engine/
- **UE5 源码**: `Engine/Source/Runtime/Core/Public/ProfilingDebugging/CsvProfiler.h`
- **UE5 源码**: `Engine/Source/Runtime/TraceLog/Public/Trace/Trace.h` — Trace Event 定义宏
- **RenderDoc 集成文档**: https://docs.unrealengine.com/5.3/en-US/renderdoc-integration-in-unreal-engine/
- **"Mastering Unreal Insights" (Unreal Fest 2024 演讲)** — 高级 Trace 使用技巧

---
## 常见陷阱

1. **Insights 录制影响性能**：Trace 录制本身有 CPU 开销（2-5%），尤其是启用 `memory` 和 `gpu` channel 时。在测量"绝对性能"时，录制数据本身会影响测量结果。对于相对比较（版本 A vs 版本 B），只要录制条件相同，偏差是可控的。

2. **`stat unit` 在 Shipping 构建中不可用**：`stat` 命令和 Unreal Insights 录制的可用性依赖构建配置。Development 和 Test 构建中完整可用，Shipping 构建中通常被剥离。不要试图在 Shipping 构建中分析性能——使用 Test 构建代替。

3. **CSV Profiler 列名不固定**：不同的 UE 版本和不同的构建配置可能输出不同的 CSV 列。你在 `regression_check.py` 中使用的列名需要在目标 UE 版本上验证。最简单的方法是先用 `-csvCaptureFrames=10` 抓一个短文件，查看实际的列头。

4. **RenderDoc 捕获大场景的 VRAM 开销**：RenderDoc 在捕获帧时需要存储所有中间渲染状态（可能数 GB）。如果你的 VRAM 已经紧张，捕获操作本身可能导致 OOM。在捕获前先降低分辨率（`r.SetRes 1280x720`），然后在 RenderDoc 中查看。

5. **`-execcmds` 的执行顺序**：`-execcmds` 中的命令在引擎完全初始化后执行，但它们是有顺序的。如果你需要先设置分辨率再开始录制，顺序很重要：
   ```
   -execcmds="r.SetRes 1280x720, stat startfile"
   ```
   而不是反过来。逗号分隔的命令串行执行。
