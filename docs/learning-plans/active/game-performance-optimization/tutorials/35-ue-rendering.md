---
title: "UE 渲染优化 — Nanite/Lumen/VSM"
updated: 2026-06-05
---

# UE 渲染优化 — Nanite/Lumen/VSM
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50 分钟
> 前置知识: 34-ue-low-level.md、UE 基础渲染管线概念
---
## 1. 概念讲解

### 为什么需要这个？

UE5 引入了三个颠覆性的渲染系统——Nanite、Lumen 和 Virtual Shadow Maps。它们各自以"硬件换质量"为设计哲学，让小型团队也能做出电影级画面。但代价是：如果不理解其内部工作机制，你会在不知情的情况下消耗大量 GPU 毫秒，而根本不知道为什么帧率从 120 掉到了 45。

这三个系统不是"开关"这么简单。它们有大量的性能梯度和硬件分级，你在项目初期就需要做出正确的架构决策——比如，你的场景中有多少薄面/镂空材质？目标硬件是否支持 Hardware Ray Tracing？VSM 的 Page Table 是否在 VRAM 受限时成为瓶颈？这些都是在 Project Settings 里点几下就能影响全项目的事，但修复一个错误的决策可能需要数周的重构。

### 核心思想

#### Nanite — 虚拟化几何体

Nanite 的核心是**GPU 驱动的 Cluster 渲染**。传统渲染管线中，CPU 需要逐个物体地进行 Draw Call 和 LOD 选择；Nanite 把整个场景的静态网格体预处理成大小均匀的小块（Cluster，每个约 128 三角形），然后让 GPU 自己决定每一帧、每一个像素需要哪个 Cluster 的哪个 LOD 级别。

关键技术栈：
- **Cluster 化预处理**：静态网格在构建时将三角形分组为 Cluster，每个 Cluster 附带一个简化的边界体积和 LOD 层级。
- **层次化 Z-Buffer (HZB) 剔除**：GPU 用上一帧的深度缓冲构建 mipmap，然后从粗到细地剔除不可见的 Cluster。
- **屏幕空间误差驱动 LOD**：根据 Cluster 投影到屏幕上的像素大小，自动选择 LOD 级别——这正是"虚拟化几何体"的含义：你只需要关心最终像素，不需要手工做 LOD。

**Nanite 的性能开销**：
| 因素 | 影响 |
|------|------|
| 薄面/细长几何体（铁丝网、栅栏）| Cluster 剔除效率降低，大量小 Cluster 消耗 GPU |
| Masked Material（镂空材质）| → 必须做逐像素的可见性测试，不能用 HZB 剔除 |
| World Position Offset（WPO）| Disables Nanite 对该材质的优化，回退到传统管线 |
| 曲面细分/置换 | Nanite 不支持——这是设计取舍 |

#### Lumen — 实时全局光照

Lumen 提供两种追踪模式：

1. **Hardware Ray Tracing (HWRT)**：利用 RT 核心，追踪场景中的 Signed Distance Field 代理或实际三角形。质量更高，但需要 RT 硬件（RTX 20 系+、RDNA 2+）。
2. **Software Ray Tracing (SWRT)**：使用 Mesh Distance Field 进行追踪，在任何支持 DX11 的 GPU 上运行。成本更高、精度更低，但覆盖面广。

**Surface Cache** 是 Lumen 的关键设计：它把场景表面的光照信息缓存在低分辨率纹理中，然后对这些缓存做光线追踪，而不是对全分辨率几何体。这大大减少了追踪成本，但引入了缓存失效和延迟的问题（比如快速移动的光源会有拖影）。

**性能梯度**（从高到低）:
```
Epic → High → Medium → Low → 关闭
```

- **Epic**: HWRT, 高质量反射, 全分辨率 Surface Cache
- **High**: 默认，SWRT/HWRT 可选，适合主机/高配 PC
- **Medium**: 降低 Surface Cache 分辨率和追踪距离，适合中端 PC
- **Low**: 大幅降低追踪参数，更适合移动端/低配

#### Virtual Shadow Maps (VSM)

传统 Cascaded Shadow Maps (CSM) 将多个固定分辨率的 Shadow Map 层叠在摄像机周围（通常 3-4 级，每级 2048²），但存在内存浪费（远处也需要全分辨率）和级联切换时的走样。

VSM 的核心思想：**一个 Shadow Texel 对应一个屏幕像素**。它使用类似虚拟纹理的 Page Table 系统，只在需要的地方分配高分辨率阴影页面。这意味着：
- 近处阴影：1:1 像素比，极高清晰度
- 远处阴影：自动降低分辨率，不浪费内存
- 大量小光源产生的阴影每个只需 Pages 包含可见区域

**VSM 的代价**：
- Page Table 本身占用 VRAM（默认 16K × 16K 的 Page Table）
- 每个需要阴影的光源独立分配 Page Pool
- 大量光源时，Page Pool 碎片化可能导致性能退化

#### Runtime Virtual Texture (RVT)

RVT 与 VSM 共享类似的分页机制：将场景材质属性（BaseColor、Normal、Roughness 等）烘焙到分页虚拟纹理中。这对于大型地形特别有用——你不需要每帧对所有地形 Layer 做完整材质求值，而是增量地更新虚拟纹理。

### 性能分析命令

- `stat gpu` — 最常用的 GPU 耗时分解：列出每个渲染 Pass 的 GPU 毫秒数
- `stat scenerendering` — 场景渲染的 CPU 侧耗时（Draw Call、Culling、Mesh Draw Commands）
- `stat nanite` — Nanite 专有统计：Cluster 数量、剔除效率、HZB 使用
- `stat lumen` — Lumen 统计：Surface Cache 更新、追踪数量
- `stat shadowrendering` — 阴影相关统计
- `ProfileGPU` — 打开 GPU Visualizer 面板（Ctrl+Shift+,）
- `r.Nanite.ShowStats 1` — 屏幕叠加显示 Nanite 统计

---
## 2. 代码示例

### 示例 A：UE 渲染性能分析宏

```cpp
// RenderingProfiler.h
#pragma once

#include "CoreMinimal.h"
#include "RenderingThread.h"

// GPU 作用域统计 — 在 stat gpu 中可见
DECLARE_GPU_STAT_NAMED(MyCustomRenderPass, TEXT("MyCustomRenderPass"));

// 渲染事件标记 — 在 RenderDoc/GPU Visualizer 中可见
DECLARE_DRAW_EVENT(MyCustomEvent, FColor::Green);

// 使用示例：在渲染代码中包裹你的自定义 Pass
void RenderMyCustomPass(FRHICommandListImmediate& RHICmdList)
{
    SCOPED_GPU_STAT(RHICmdList, MyCustomRenderPass);
    SCOPED_DRAW_EVENT(RHICmdList, MyCustomEvent);

    // ... 你的渲染代码 ...
}

// CPU 侧统计 — 在 stat scenerendering 中可见
DECLARE_CYCLE_STAT(TEXT("MyCustomCpuWork"), STAT_MyCustomCpuWork, STATGROUP_SceneRendering);

void DoHeavyCpuWork()
{
    SCOPE_CYCLE_COUNTER(STAT_MyCustomCpuWork);
    // ... CPU 密集型工作 ...
}
```

**编译与使用**：
1. 将上述代码放在你的 `.h` 文件中，在 `.cpp` 中使用
2. 运行游戏，打开控制台输入 `stat gpu`，你会在列表中看到 `MyCustomRenderPass`
3. 输入 `stat scenerendering`，你会看到 `MyCustomCpuWork` 的耗时
4. 按 Ctrl+Shift+, 打开 GPU Visualizer，在下拉菜单中找到你的 Event

### 示例 B：性能开关脚本（Console Variables 批量操作）

创建一个 `.txt` 文件保存为 `YourProject/Config/PerfPresets.txt`，然后在控制台用 `exec PerfPresets.txt` 执行：

```
; ========================================
; 预设 A：Ultra Quality（默认 UE5 质量）
; ========================================
r.Nanite 1
r.Lumen.DiffuseIndirect.Allow 1
r.Lumen.Reflections.Allow 1
r.Shadow.Virtual.Enable 1
r.Lumen.HardwareRayTracing 1
r.Lumen.ScreenProbeGather.RadianceCache.ProbeResolution 32
r.Shadow.Virtual.ResolutionLodBiasDirectional -1.5

; ========================================
; 预设 B：Balanced（中配 PC，60fps 目标）
; ========================================
; 取消注释以下行来使用:
; r.Nanite 1
; r.Lumen.DiffuseIndirect.Allow 1
; r.Lumen.Reflections.Allow 1
; r.Shadow.Virtual.Enable 1
; r.Lumen.HardwareRayTracing 0        ; 切换到软件追踪
; r.Lumen.ScreenProbeGather.RadianceCache.ProbeResolution 16  ; 减半 Probe 分辨率
; r.Shadow.Virtual.ResolutionLodBiasDirectional 0  ; 降低 VSM 分辨率

; ========================================
; 预设 C：Performance（低配/Steam Deck，高帧率）
; ========================================
; r.Nanite 0                          ; 关闭 Nanite，回退到传统 LOD
; r.Lumen.DiffuseIndirect.Allow 0     ; 关闭 Lumen GI，使用 Lightmaps
; r.Lumen.Reflections.Allow 0         ; 关闭 Lumen 反射
; r.Shadow.Virtual.Enable 0           ; 使用传统 CSM
; r.Shadow.CSM.MaxCascades 2          ; 减少 CSM 级联
; r.Streaming.PoolSize 2000           ; 降低纹理流送池（MB）
; r.VT.Enable 0                       ; 关闭虚拟纹理
```

### 示例 C：运行时性能开销测量

```cpp
// PerfMeasurement.cpp
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"
#include "HAL/PlatformTime.h"

// 测量 CVar 切换对帧时间的影响
void MeasureCvarImpact(const FString& CvarName, int32 NewValue)
{
    UWorld* World = GEngine->GameViewport->GetWorld();
    if (!World) return;

    // 基准测量 — 当前帧时间
    float BaselineMs = 0.0f;
    {
        double StartTime = FPlatformTime::Seconds();
        // 等待几帧稳定
        for (int32 i = 0; i < 10; ++i)
        {
            World->GetGameViewport()->Draw();
        }
        double EndTime = FPlatformTime::Seconds();
        BaselineMs = static_cast<float>((EndTime - StartTime) * 1000.0 / 10.0);
    }

    UE_LOG(LogTemp, Log, TEXT("Baseline frame time: %.2f ms"), BaselineMs);

    // 应用新的 CVar 值
    IConsoleVariable* CVar = IConsoleManager::Get().FindConsoleVariable(*CvarName);
    if (!CVar)
    {
        UE_LOG(LogTemp, Warning, TEXT("CVar %s not found"), *CvarName);
        return;
    }
    CVar->Set(NewValue);

    // 测量新设置下的帧时间
    float NewMs = 0.0f;
    {
        double StartTime = FPlatformTime::Seconds();
        for (int32 i = 0; i < 10; ++i)
        {
            World->GetGameViewport()->Draw();
        }
        double EndTime = FPlatformTime::Seconds();
        NewMs = static_cast<float>((EndTime - StartTime) * 1000.0 / 10.0);
    }

    UE_LOG(LogTemp, Log, TEXT("%s = %d -> Frame time: %.2f ms (delta: %+.2f ms, %+.1f%%)"),
        *CvarName, NewValue, NewMs,
        NewMs - BaselineMs,
        ((NewMs / BaselineMs) - 1.0f) * 100.0f);

    // 恢复原值
    CVar->Set(CVar->GetInt());
}

// 在蓝图或控制台中调用：
// MeasureCvarImpact(TEXT("r.Nanite"), 0)
// 输出: Nanite 关闭后帧时间变化
```

### 示例 D：可扩展性设置读取

```cpp
#include "Scalability.h"
#include "Engine/GameUserSettings.h"

void PrintScalabilitySettings()
{
    // 读取当前可扩展性等级
    Scalability::FQualityLevels Levels = Scalability::GetQualityLevels();

    UE_LOG(LogTemp, Log, TEXT("=== Scalability Settings ==="));
    UE_LOG(LogTemp, Log, TEXT("ResolutionQuality:   %.2f"), Levels.ResolutionQuality);
    UE_LOG(LogTemp, Log, TEXT("ViewDistanceQuality: %d"),   Levels.ViewDistanceQuality);    // 0=Low, 3=Epic
    UE_LOG(LogTemp, Log, TEXT("AntiAliasingQuality: %d"),   Levels.AntiAliasingQuality);
    UE_LOG(LogTemp, Log, TEXT("ShadowQuality:       %d"),   Levels.ShadowQuality);
    UE_LOG(LogTemp, Log, TEXT("GlobalIlluminationQuality: %d"), Levels.GlobalIlluminationQuality);
    UE_LOG(LogTemp, Log, TEXT("ReflectionQuality:   %d"),   Levels.ReflectionQuality);
    UE_LOG(LogTemp, Log, TEXT("PostProcessQuality:  %d"),   Levels.PostProcessQuality);
    UE_LOG(LogTemp, Log, TEXT("TextureQuality:      %d"),   Levels.TextureQuality);
    UE_LOG(LogTemp, Log, TEXT("EffectsQuality:      %d"),   Levels.EffectsQuality);
    UE_LOG(LogTemp, Log, TEXT("FoliageQuality:      %d"),   Levels.FoliageQuality);
    UE_LOG(LogTemp, Log, TEXT("ShadingQuality:      %d"),   Levels.ShadingQuality);

    // 设置特定等级
    // Scalability::SetQualityLevels(Levels); // 同步设置全部
    // Scalability::FQualityLevels NewLevels = Levels;
    // NewLevels.ShadowQuality = 1; // Medium
    // Scalability::SetQualityLevels(NewLevels);
}
```

---
## 3. 练习

### 练习 1: 渲染开销分解

1. 创建一个新 UE5 项目，放入至少 5 种不同类型的静态网格体（包括镂空材质、半透明材质、WPO 动画材质）
2. 启用 Nanite 对所有支持的网格体
3. 运行 `stat gpu`，记录每个 Pass 的耗时
4. 依次切换以下 CVar 并重新测量：
   - `r.Nanite 0` — 观察 Nanite 被关闭后的 BasePass/ShadowDepths 耗时变化
   - `r.Lumen.DiffuseIndirect.Allow 0` — 观察 Lumen 被关闭后的 DiffuseIndirectAndAO 变化
   - `r.Shadow.Virtual.Enable 0` — 切换到传统 CSM，观察阴影 Pass 变化
5. 回答：你的场景中，哪个系统的开销最大？为什么？

### 练习 2: 可扩展性预设

1. 基于示例 B 中的 Console Variables 脚本，为你自己的项目创建三个性能预设文件（Low/Medium/High）
2. 在三个不同场景中测试每个预设：
   - 密集室内场景（大量静态网格）
   - 开放世界场景（大量地形+植被）
   - 带有多个动态光源的场景
3. 使用 `stat unit` 记录每个场景+预设组合的 Frame/Game/Draw/GPU 时间
4. 制作一个表格，标识哪些 CVar 设置对哪种场景类型影响最大

### 练习 3: 自定义 GPU 统计（可选）

1. 在你的项目中创建一个自定义 Render Pass（使用 `SCOPED_GPU_STAT` 和 `SCOPED_DRAW_EVENT`）
2. 编译并确认它在 `stat gpu` 和 GPU Visualizer 中可见
3. 尝试用 `SCOPED_GPU_STAT` 包裹现有 UE 渲染代码路径（如 Post Process 的自定义部分）
4. 使用 RenderDoc 捕获一帧，确认你的 Event 出现在正确的时机


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **渲染开销分解 — 排查思路与典型结果**
> 
> **测试场景搭建要点**：
> - 镂空材质：铁栅栏/树叶（Masked Material，禁用 HZB 剔除，需逐像素可见性测试）
> - 半透明材质：玻璃/水面（Translucent，额外排序 + 独立 Pass 开销）
> - WPO 动画材质：旗帜飘动/水面波动（World Position Offset 禁用 Nanite 优化）
> 
> **stat gpu 典型输出解读**：
> 
> | Pass | Nanite ON | Nanite OFF | 分析 |
> |------|-----------|------------|------|
> | Nanite VisBuffer | 1.2ms | — | Nanite 可见性 Buffer 构建 |
> | Nanite BasePass | 2.8ms | — | Nanite 材质求值（薄面物体占比大时偏高） |
> | BasePass (non-Nanite) | 0.3ms | 4.5ms | 传统物体 → Nanite 关闭后暴增 |
> | ShadowDepths | 1.5ms | 3.2ms | 关闭 VSM 后切换到 CSM，Draw Call 增加 |
> | Lumen (DiffuseIndirect) | 2.1ms | 2.1ms | Lumen 独立于 Nanite（依赖 Surface Cache） |
> | Lumen (Reflections) | 0.8ms | 0.8ms | 同上 |
> | Post Process | 0.9ms | 0.9ms | 后处理不受 Nanite/VSM 影响 |
> | **Total** | **9.6ms** | **11.5ms** | Nanite 节省 ~2ms（取决于场景复杂度） |
> 
> **为什么 Nanite 关闭后 BasePass 暴增？**
> - Nanite 将大量小三角形合并为 Cluster，减少 Draw Call
> - 关闭后每个静态网格体产生独立 Draw Call（CPU 提交 + GPU 状态切换）
> - 场景中 5 种静态网格 × 每个的材质变体 → 大量 SetPass Call
> 
> **哪个系统开销最大？**
> - 答案取决于场景：
>   - **室内密集场景**：Lumen GI → 大量光线追踪 Surface Cache 更新（2-3ms）
>   - **大量植被的开放世界**：Nanite BasePass → 薄面几何体（树叶）Cluster 剔除效率低（3-5ms）
>   - **多动态光源场景**：VSM ShadowDepths → 每个光源独立 Shadow Page Pool（2-4ms）
> - **通用结论**：Lumen 是最大的单系统开销（常占帧预算 20-30%），其次是 Nanite/VSM

> [!tip]- 练习 2 参考答案
> **可扩展性预设 — 三种场景的测试矩阵**
> 
> **三个预设文件**（保存为 `.txt` 放入 Config 目录）：
> 
> **Preset_Ultra.txt** (Epic 等效):
> ```
> r.Nanite 1
> r.Lumen.DiffuseIndirect.Allow 1
> r.Lumen.Reflections.Allow 1
> r.Shadow.Virtual.Enable 1
> r.Lumen.HardwareRayTracing 1
> r.Lumen.ScreenProbeGather.RadianceCache.ProbeResolution 32
> r.Shadow.Virtual.ResolutionLodBiasDirectional -1.5
> r.Streaming.PoolSize 4000
> ```
> 
> **Preset_High.txt** (主机/高配 PC):
> ```
> r.Nanite 1
> r.Lumen.DiffuseIndirect.Allow 1
> r.Lumen.Reflections.Allow 1
> r.Shadow.Virtual.Enable 1
> r.Lumen.HardwareRayTracing 1
> r.Lumen.ScreenProbeGather.RadianceCache.ProbeResolution 24
> r.Shadow.Virtual.ResolutionLodBiasDirectional -1.0
> r.Streaming.PoolSize 3000
> ```
> 
> **Preset_Medium.txt** (中配 PC):
> ```
> r.Nanite 1
> r.Lumen.DiffuseIndirect.Allow 1
> r.Lumen.Reflections.Allow 1
> r.Shadow.Virtual.Enable 1
> r.Lumen.HardwareRayTracing 0
> r.Lumen.ScreenProbeGather.RadianceCache.ProbeResolution 16
> r.Shadow.Virtual.ResolutionLodBiasDirectional 0.0
> r.Streaming.PoolSize 2000
> ```
> 
> **Preset_Low.txt** (低配/Steam Deck):
> ```
> r.Nanite 0
> r.Lumen.DiffuseIndirect.Allow 0
> r.Lumen.Reflections.Allow 0
> r.Shadow.Virtual.Enable 0
> r.Shadow.CSM.MaxCascades 2
> r.Shadow.CSM.ShadowDistance 3000
> r.Streaming.PoolSize 1500
> r.VT.Enable 0
> ```
> 
> **测试矩阵**（使用 `stat unit`）：
> 
> | 场景 | 预设 | Frame (ms) | GPU (ms) | 主要瓶颈 |
> |------|------|-----------|----------|----------|
> | 密集室内 | Ultra | 14.2 | 13.8 | Lumen GI (3.2ms) |
> | 密集室内 | High | 11.5 | 11.2 | Lumen GI (2.1ms) |
> | 密集室内 | Medium | 8.3 | 8.0 | Nanite BasePass (2.5ms) |
> | 密集室内 | Low | 5.1 | 4.8 | 传统 BasePass (1.8ms) |
> | 开放世界 | Ultra | 18.5 | 18.1 | Nanite VisBuffer (4.5ms) |
> | 开放世界 | High | 14.8 | 14.5 | Nanite VisBuffer (3.2ms) |
> | 开放世界 | Medium | 10.2 | 9.8 | Nanite BasePass (2.8ms) |
> | 开放世界 | Low | 7.8 | 7.5 | CSM Shadow (1.5ms) |
> | 多动态光 | Ultra | 22.1 | 21.5 | VSM PageTable (5.1ms) |
> | 多动态光 | High | 16.5 | 16.1 | VSM PageTable (3.5ms) |
> | 多动态光 | Medium | 10.8 | 10.3 | VSM PageTable (2.1ms) |
> | 多动态光 | Low | 6.2 | 5.8 | CSM+静态烘焙 (0.8ms) |
> 
> **CVar 影响分析**：
> 
> | CVar | 密集室内 | 开放世界 | 多动态光 | 备注 |
> |------|---------|----------|---------|------|
> | `r.Nanite 0` | ++中 | **+++最大** | +小 | 开放世界中几何复杂度最高 |
> | `r.Lumen.* 0` | **+++最大** | ++中 | +小 | 室内 GI 贡献大 |
> | `r.Shadow.Virtual.Enable 0` | +小 | +小 | **+++最大** | 光源越多 VSM 收益越大 |
> | `r.Streaming.PoolSize` | +小 | ++中 | +小 | 纹理流送池主要影响开放世界大纹理 |
> 
> **结论**：没有一刀切的优化——根据场景特征选择对应的性能开关。开放世界优先调 Nanite/LOD，室内优先调 Lumen，多光源场景优先调 VSM/Shadow。

> [!tip]- 练习 3 参考答案（可选）
> **自定义 GPU 统计 — 完整示例**
> 
> ```cpp
> // MyCustomRenderPass.h
> #pragma once
> #include "CoreMinimal.h"
> #include "RenderingThread.h"
> 
> // 声明 GPU Stat（在 stat gpu 中可见）
> DECLARE_GPU_STAT_NAMED(MyCustomBloomPass, TEXT("My Custom Bloom"));
> DECLARE_GPU_STAT_NAMED(MyCustomToneMapPass, TEXT("My Custom ToneMap"));
> 
> // 声明 Draw Event（在 GPU Visualizer 中有色块标记）
> DECLARE_DRAW_EVENT(MyBloomEvent, FColor::Yellow);
> DECLARE_DRAW_EVENT(MyToneMapEvent, FColor::Cyan);
> ```
> 
> ```cpp
> // MyCustomRenderPass.cpp
> #include "MyCustomRenderPass.h"
> #include "PostProcess/PostProcessing.h"
> 
> // 自定义后处理 Pass 示例
> void RenderMyCustomPostProcess(
>     FRDGBuilder& GraphBuilder,
>     const FSceneView& View,
>     FRDGTextureRef SceneColor)
> {
>     // 添加 GPU Stat scope
>     RDG_GPU_STAT_SCOPE(GraphBuilder, MyCustomBloomPass);
> 
>     // 添加 Draw Event scope
>     RDG_EVENT_SCOPE(GraphBuilder, "My Custom Bloom Pass");
> 
>     // 创建临时 RT（Render Graph 自动管理生命周期）
>     FRDGTextureDesc BloomDesc = SceneColor->Desc;
>     BloomDesc.Reset();
>     BloomDesc.Extent = FIntPoint(
>         SceneColor->Desc.Extent.X / 4,
>         SceneColor->Desc.Extent.Y / 4);
>     BloomDesc.Format = PF_FloatRGBA;
>     FRDGTextureRef BloomTexture = GraphBuilder.CreateTexture(
>         BloomDesc, TEXT("MyBloomRT"));
> 
>     // Downsample Pass
>     AddDownsamplePass(GraphBuilder, View, SceneColor, BloomTexture);
> 
>     // Blur Pass (horizontal + vertical)
>     FRDGTextureRef BlurredTexture = GraphBuilder.CreateTexture(
>         BloomDesc, TEXT("MyBloomBlurred"));
>     AddGaussianBlurPass(GraphBuilder, View, BloomTexture, BlurredTexture);
> 
>     // Composite Pass
>     {
>         RDG_GPU_STAT_SCOPE(GraphBuilder, MyCustomToneMapPass);
>         RDG_EVENT_SCOPE(GraphBuilder, "My Custom ToneMap");
>         AddCompositePass(GraphBuilder, View, SceneColor, BlurredTexture);
>     }
> }
> ```
> 
> **验证步骤**：
> 1. 编译项目，确保没有编译错误
> 2. 运行游戏 → 打开控制台 → 输入 `stat gpu`
> 3. 在 GPU stat 列表中找到 `My Custom Bloom` 和 `My Custom ToneMap`
> 4. 按 Ctrl+Shift+, → 打开 GPU Visualizer → 在下拉菜单中勾选你的 Event
> 5. 黄色块 = Bloom，青色块 = ToneMap，确认它们的顺序和时机正确
> 6. 用 RenderDoc 捕获一帧 → 在 Event Browser 中搜索 `My Custom` → 确认你的 Event 出现在预期位置（后处理阶段）
> 
> **RenderDoc 验证细节**：
> - 打开捕获 → Event Browser → 按名称搜索
> - 确认你的 Event 在 `PostProcessing` group 中
> - 确认 Event 时间戳与 `stat gpu` 中显示的耗时一致
> - 检查是否有意外的资源 barrier 产生额外开销

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---
## 4. 扩展阅读

- **UE5 官方文档 — Nanite**: https://docs.unrealengine.com/5.3/en-US/nanite-virtualized-geometry-in-unreal-engine/
- **UE5 官方文档 — Lumen**: https://docs.unrealengine.com/5.3/en-US/lumen-global-illumination-and-reflections-in-unreal-engine/
- **UE5 官方文档 — Virtual Shadow Maps**: https://docs.unrealengine.com/5.3/en-US/virtual-shadow-maps-in-unreal-engine/
- **Brian Karis (Epic) 的 Nanite SIGGRAPH 2021 演讲**: "Nanite: A Deep Dive" — 理解 Cluster 渲染和 GPU 剔除的经典资料
- **Krzysztof Narkowicz (Epic) 的 Lumen 技术博客系列**: 深入 Surface Cache 和 Radiance Cache 的实现细节
- **UE5 Virtual Texturing 文档**: Runtime Virtual Texture 的工作原理和材质设置

---
## 常见陷阱

1. **盲目禁用 Nanite**：禁用 Nanite 会将所有几何体回退到传统 LOD 管线。如果你的网格没有手工设置 LOD，它们会以 LOD 0（全分辨率）渲染所有距离，导致 Draw Call 爆炸和 GPU 浪费。禁用 Nanite 不是"回退到传统性能"，而是"回退到你没有优化的传统管线"。

2. **Lumen Surface Cache 的暖机时间**：Lumen 的 Surface Cache 需要数帧才能收敛。如果你在运行时切换 Lumen 相关 CVar 后立即测量 FPS，会得到严重误导的数据。至少等待 30-60 帧后再记录数据。

3. **VSM 与大量光源**：每个产生阴影的光源都独立分配一个 VSM Page Pool。如果你有 50 个投射阴影的 Point Light，VSM 的 VRAM 开销会比 CSM 大得多。在大量小光源场景中，考虑使用非虚拟阴影贴图或限制阴影投射距离。

4. **Nanite 不支持所有材质特性**：WPO、Pixel Depth Offset、Tessellation（已废弃）都会禁用 Nanite 优化。检查你的材质图，确保只在必要时使用这些节点。

5. **`stat gpu` 与 `stat unit` 的区别**：`stat gpu` 显示 GPU 本身的耗时（实际渲染时间），`stat unit` 包含 CPU 等待 GPU 的时间。如果你的 `stat unit` 显示 GPU 时间远大于 Frame 时间，说明存在 CPU-GPU 同步点（资源锁、读回操作）。
