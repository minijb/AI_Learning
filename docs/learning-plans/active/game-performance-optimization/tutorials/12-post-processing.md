# 后处理优化 — 全屏特效的代价与降级
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: 11-光照优化 (了解渲染管线后期阶段), 08-Shader 优化 (了解 Pixel Shader 成本)

---

## 1. 概念讲解

### 为什么需要这个？

后处理是现代游戏画面"电影感"的来源——Bloom 让灯光发光，Tonemapping 让 HDR 正确映射到屏幕，DOF 模拟相机景深，Motion Blur 增加速度感。但每一个全屏 Pass 都意味着：**屏幕上的每一个像素都要被重新处理一次**。

1080p 下，一个全屏 Pass = 200 万次 Pixel Shader 调用。如果叠加 6 个后处理效果 + 4 个降采样 Pass，总共 10 × 200 万 = 2000 万次调用。如果每个后处理 PS 平均 30 条 ALU 指令 + 8 次纹理采样 = ~200 GPU 周期，总开销 = 2000 万 × 200 = 40 亿周期 ≈ **1.5ms–2.5ms**（1.5GHz GPU）。

在 60fps 预算（16.67ms）下，后处理可能占用 10%–15% 的帧时间。这还不算带宽——每个全屏 Pass 都要读写帧缓冲（1080p RGBA16F = 16.6MB per read/write）。

### 核心思想

#### 1. 后处理效果成本排名

从最便宜到最昂贵（1080p，单个全屏 Pass）：

| 效果 | 相对成本 | ALU | 纹理采样 | 说明 |
|------|----------|-----|----------|------|
| Tone Mapping | 1× | ~5 | 0-1 | 简单的颜色映射曲线 |
| Color Grading (LUT) | 1.5× | ~5 | 1 (3D LUT) | 查表操作 |
| Vignette | 1× | ~3 | 0 | 纯计算 |
| Film Grain | 2× | ~8 | 1-2 | 噪声采样+混合 |
| **Bloom (降采样链)** | **3-8×** | 5-15/pass | 4-9/pass | 多个降采样+上采样+合成 Pass |
| **Depth of Field** | **5-15×** | 20-40 | 8-15 | 多 Pass、散景计算、CoC 计算 |
| **Motion Blur** | **4-10×** | 15-25 | 3-5 | 需要速度缓冲、多采样 |
| **SSAO** | **8-20×** | 30-50 | 8-16 | 多方向深度采样、模糊 Pass |
| **SSR** | **10-30×** | 40-80 | 10-30 | 屏幕空间光线追踪、多步 Marching |

成本 = （分辨率 × PS 复杂度）+（带宽 × 读写次数）

#### 2. 降采样策略

核心思想：**模糊类的效果不需要在全分辨率下计算**。

**Bloom 降采样链**：
```
原始 (1920×1080)  ← 提取亮部
    ↓ 降采样 (双线性)
960×540            ← 模糊 Pass 1
    ↓ 降采样
480×270            ← 模糊 Pass 2
    ↓ 降采样
240×135            ← 模糊 Pass 3
    ↓ 降采样
120×68             ← 模糊 Pass 4
    ↓ 上采样 + 合成
1920×1080          ← 最终合成
```

降采样链的总像素处理量：
```
1920×1080 (提取) = 2,073,600
960×540   = 518,400
480×270   = 129,600
240×135   = 32,400
120×68    = 8,160
上采样 ×4 = 518,400 + 129,600 + 32,400 + 8,160 = 688,560
合成      = 2,073,600
────────────────────────────
总计      ≈ 5,526,720 像素
```

vs 全分辨率 5 Pass = 2,073,600 × 5 = 10,368,000 像素。降采样节省 ~47% 的像素处理量。

**DOF 降采样**：半分辨率 DOF 是最常见的优化。在 960×540 计算 CoC（Circle of Confusion）+ 散景模糊，然后上采样合成。视觉效果几乎无损，性能提升 ~3×。

**Motion Blur 降采样**：在 1/2 或 1/4 分辨率做速度缓冲采样和模糊，因为 Motion Blur 本身就是模糊效果，分辨率降低不可见。

#### 3. Compute Shader vs Pixel Shader

对于后处理，Compute Shader 通常优于 Pixel Shader：

| 方面 | Pixel Shader | Compute Shader |
|------|-------------|----------------|
| 调度 | 隐式（GPU 决定线程组） | 显式（手动指定 thread group） |
| LDS/Group Shared Memory | 不可用 | 可用（速度 10-100× vs 全局显存） |
| 相邻像素共享数据 | 需要重新采样 | 可以预加载到 LDS |
| UAV（无序访问） | 有限支持 | 完全支持 |
| 与光栅化管线集成 | 自然 | 需要手动 compute→graphics 同步 |
| 对于简单 Pass | 更简单 | 与 PS 持平 |

Compute Shader 的最大优势是 **LDS（Local Data Share）/Group Shared Memory**。例如 9×9 的模糊 kernel：Pixel Shader 中每个像素需要 81 次纹理采样（每采样一次 = 一次全局显存访问 ≈ 200-500 周期）。Compute Shader 中可以将 16×16+8（边界）= 24×24 的像素块一次性加载到 LDS（~100 周期/线程），然后 16×16 个线程各做 81 次 LDS 读取（~10 周期/次），总延迟降低 3-5×。

#### 4. 时间性技术（Temporal）

**Temporal Anti-Aliasing（TAA）**：利用前一帧的渲染结果来增强当前帧的抗锯齿。

成本：
- TAA resolve Pass：中等（需要 5-9 次纹理采样 + 历史缓冲读取）
- 但可以大幅减少其他 Pass 的分辨率要求（启用 TAA 后，SSAO/SSR 可以在更低分辨率下运行而不出现明显噪点）

**Temporal Upscaling（DLSS/FSR/TSR）**：
- 以更低内部分辨率渲染（如 1080p → 4K 输出）
- G-Buffer 和光照计算都在低分辨率
- 后处理可以和上采样融合在一起
- **这是现代游戏性能优化的最强大杠杆**：DLSS/FSR Quality 模式（67% 分辨率）通常节省 30-40% GPU 时间

#### 5. 引擎实现对比

**Unity URP Post Processing**：
- URP 的后处理直接集成在渲染管线中
- `Volume` 组件挂载 `Volume Profile`
- 在 URP Asset 中可配置每个效果是否启用
- `renderScale` 控制内部分辨率滑块（0.5–2.0）

**Unity HDRP Post Processing**：
- 更丰富：Exposure、Tonemapping（ACES/Neutral/Custom）、Color Adjustments
- 内置 Bloom、DOF（物理相机模型）、Motion Blur
- `Dynamic Resolution` 功能可自动调整内部分辨率

**UE Post Process Volume**：
- `Post Process Volume` 可放置在场景中，影响进入范围的相机
- `Post Process Settings` 包含所有可调参数
- UE 内置 Scalability System：Low/Medium/High/Epic/Cinematic 档位，自动开关/降级后处理效果

**UE Console Variables（关键后处理）**：
```
r.BloomQuality      0-5    // Bloom 质量
r.DOF.Quality       0-4    // 景深质量
r.MotionBlurQuality 0-4    // 运动模糊质量
r.AmbientOcclusionLevels 0-4  // SSAO 采样数
r.SSR.Quality       0-4    // SSR 质量
r.Tonemapper.Quality 0-5   // Tonemapping 质量
r.PostProcessAllowBlendModes 0/1 // Blendable 后处理材质
```

#### 6. 可扩展性设计

游戏应该在画质设置中提供后处理的分级控制：
```
Low:    Tone Mapping + Color Grading only
Medium: + Bloom (1/4 res, 4 downsamples)
High:   + SSAO (1/2 res), + Motion Blur (1/2 res)
Ultra:  + DOF (full res), + SSR (1/2 res), + full quality all
```

---

## 2. 代码示例

### 示例 1：Bloom 降采样链（GLSL/HLSL）

```hlsl
// bloom_downsample.hlsl — Bloom 降采样链的完整实现
// 包含: 亮部提取 → 降采样(多次) → 上采样(多次) → 合成

// ====== Pass 1: 提取亮部 (Extract Bright) ======
// 在全分辨率下执行
Texture2D    g_SceneColor;
SamplerState g_SamplerClamp;

float4 ExtractBrightPS(float2 uv : TEXCOORD0) : SV_Target {
    float3 color = g_SceneColor.SampleLevel(g_SamplerClamp, uv, 0).rgb;

    // 亮度阈值提取（只保留超过 threshold 的亮部）
    float brightness = dot(color, float3(0.2126, 0.7152, 0.0722)); // 感知亮度
    float3 brightColor = color * smoothstep(g_BloomThreshold, g_BloomThreshold + g_BloomSoftKnee, brightness);

    return float4(brightColor, 1.0);
    // 指令数: ~6 ALU + 1 纹理采样 ≈ 极轻
}

// ====== Pass 2-N: 降采样 (Downsample) ======
// 每次将分辨率减半，同时做 2×2 盒式滤波
Texture2D    g_BloomInput;  // 上一级的结果
float2       g_TexelSize;   // 当前级输入纹理的纹素大小

float4 DownsamplePS(float2 uv : TEXCOORD0) : SV_Target {
    // 4 点采样 (双线性采样器会自动做 2×2 平均)
    // 偏移到四个纹素的中心
    float2 texelSize = g_TexelSize;

    float3 color = float3(0, 0, 0);
    // 3×3 tent filter — 比纯 2×2 盒式滤波效果更好，避免闪烁
    // 权重: 中心 1/4, 四边 1/8, 四角 1/16
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2(-1, -1) * texelSize, 0).rgb * (1.0/16.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2( 0, -1) * texelSize, 0).rgb * (1.0/8.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2( 1, -1) * texelSize, 0).rgb * (1.0/16.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2(-1,  0) * texelSize, 0).rgb * (1.0/8.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2( 0,  0) * texelSize, 0).rgb * (1.0/4.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2( 1,  0) * texelSize, 0).rgb * (1.0/8.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2(-1,  1) * texelSize, 0).rgb * (1.0/16.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2( 0,  1) * texelSize, 0).rgb * (1.0/8.0);
    color += g_BloomInput.SampleLevel(g_SamplerClamp, uv + float2( 1,  1) * texelSize, 0).rgb * (1.0/16.0);

    return float4(color, 1.0);
    // 指令数: 9 次纹理采样 + 9 次乘法 + 9 次加法
}

// ====== Pass: 上采样 (Upsample) ======
// 将低分辨率 Bloom 放大并与高分辨率混合
// 注意：上采样是反向进行的 (从最低分辨率开始，逐级上采样)
Texture2D    g_CurrentBloom;  // 当前级的 Bloom（低分辨率）
Texture2D    g_PreviousBloom; // 上一级的 Bloom（高分辨率，可能已合成过）
float2       g_UpsampleTexelSize;

float4 UpsamplePS(float2 uv : TEXCOORD0) : SV_Target {
    // 从低分辨率的 g_CurrentBloom 上采样
    // 使用 3×3 tent filter 做上采样
    float2 texelSize = g_UpsampleTexelSize;

    float3 color = float3(0, 0, 0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2(-1, -1) * texelSize, 0).rgb * (1.0/16.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2( 0, -1) * texelSize, 0).rgb * (1.0/8.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2( 1, -1) * texelSize, 0).rgb * (1.0/16.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2(-1,  0) * texelSize, 0).rgb * (1.0/8.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2( 0,  0) * texelSize, 0).rgb * (1.0/4.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2( 1,  0) * texelSize, 0).rgb * (1.0/8.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2(-1,  1) * texelSize, 0).rgb * (1.0/16.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2( 0,  1) * texelSize, 0).rgb * (1.0/8.0);
    color += g_CurrentBloom.SampleLevel(g_SamplerClamp, uv + float2( 1,  1) * texelSize, 0).rgb * (1.0/16.0);

    return float4(color, 1.0);
}

// ====== Pass: 最终合成 (Composite) ======
// 将 Bloom 叠加回场景颜色
Texture2D    g_SceneColorFinal;
Texture2D    g_FinalBloom;

float4 CompositePS(float2 uv : TEXCOORD0) : SV_Target {
    float3 sceneColor = g_SceneColorFinal.SampleLevel(g_SamplerClamp, uv, 0).rgb;
    float3 bloom = g_FinalBloom.SampleLevel(g_SamplerClamp, uv, 0).rgb;

    // 简单加法混合（真实物理中 Bloom 应该 HDR 散射）
    float3 result = sceneColor + bloom * g_BloomIntensity;

    return float4(result, 1.0);
}

// ====== 可选：Compute Shader 版本（更高效） ======
// 使用共享内存+LDS 优化的降采样

#ifndef COMPUTE_BLOOM
#define COMPUTE_BLOOM
groupshared float3 g_Cache[16 + 4][16 + 4]; // 20×20 = 带边界的缓存

[numthreads(16, 16, 1)]
void DownsampleCS(uint3 dtid : SV_DispatchThreadID, uint3 gtid : SV_GroupThreadID) {
    // Step 1: 加载到共享内存（含 2 像素边界用于 3×3 filter）
    // 每个线程加载自己的像素 + 边界像素
    int2 baseCoord = dtid.xy * 2 - 1; // 降采样到一半分辨率

    // 加载核心 16×16 像素
    // ... (加载逻辑)

    GroupMemoryBarrierWithGroupSync();

    // Step 2: 从共享内存读取并过滤
    float3 color = float3(0, 0, 0);
    // 3×3 tent filter 从 LDS 读取（比全局纹理采样快 10-50×）
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            float weight = (2 - abs(x)) * (2 - abs(y)) / 16.0;
            color += g_Cache[gtid.y + 2 + y][gtid.x + 2 + x] * weight;
        }
    }

    // Step 3: 写入输出纹理
    g_OutputBloom[dtid.xy] = float4(color, 1.0);
}
#endif
```

### 示例 2：后处理成本分析器（C++）

```cpp
// postprocess_cost.cpp — 后处理开销计算和优化对比
// 编译: g++ -std=c++17 postprocess_cost.cpp -o pp_cost && ./pp_cost

#include <iostream>
#include <vector>
#include <string>
#include <iomanip>
#include <cmath>

struct PostEffect {
    std::string name;
    int downscale;       // 降采样因子: 1=全分辨率, 2=1/2, 4=1/4
    float aluPerPixel;   // 每个像素的 ALU 指令数
    int texSamples;      // 每个像素的纹理采样次数
    float costWeight;    // 相对成本权重
    bool enabled;
};

struct PostPipeline {
    std::string name;
    int resolutionW, resolutionH;
    std::vector<PostEffect> effects;
};

struct PipelineCost {
    float totalPixelOps;     // 总像素处理量（百万）
    float totalBandwidthMB;  // 总带宽（MB）
    float estimatedGPUMs;    // 预估 GPU 时间（ms）
};

PipelineCost AnalyzePipeline(const PostPipeline& pipe) {
    PipelineCost cost = {};
    int fullResPixels = pipe.resolutionW * pipe.resolutionH;

    for (auto& fx : pipe.effects) {
        if (!fx.enabled) continue;

        int effectiveW = pipe.resolutionW / fx.downscale;
        int effectiveH = pipe.resolutionH / fx.downscale;
        int pixels = effectiveW * effectiveH;

        // 像素操作 = 实际像素 × 单位成本
        float pixelOps = pixels * (fx.aluPerPixel + fx.texSamples * 10.0f);
        cost.totalPixelOps += pixelOps;

        // 带宽估算：假设每像素 RGBA16F (8 bytes) 读写
        // 读: 纹理采样, 写: Render Target
        float readBytes = fx.texSamples * 8.0f;
        float writeBytes = 8.0f; // 输出到 RT
        cost.totalBandwidthMB += pixels * (readBytes + writeBytes) / (1024.0f * 1024.0f);
    }

    // GPU 时间估算
    // ALU: ~1.5 GHz GPU, 每个像素 ops / 1.5G ops = 时间
    float gpuFreqGHz = 1.5f;
    cost.estimatedGPUMs = cost.totalPixelOps / (gpuFreqGHz * 1000.0f);

    // 加上带宽延迟 (~200 GB/s bandwidth)
    float bandwidthTime = cost.totalBandwidthMB / 200000.0f * 1000.0f;
    cost.estimatedGPUMs += bandwidthTime;

    return cost;
}

void PrintPipeline(const PostPipeline& pipe, const PipelineCost& cost) {
    std::cout << "Pipeline: " << pipe.name << "\n";
    std::cout << "分辨率: " << pipe.resolutionW << "×" << pipe.resolutionH << "\n\n";

    std::cout << std::setw(25) << std::left << "效果"
              << std::setw(10) << "降采样"
              << std::setw(8)  << "状态"
              << std::setw(8)  << "ALU/p"
              << std::setw(8)  << "采样"
              << "\n";
    std::cout << std::string(60, '-') << "\n";

    int totalPixels = pipe.resolutionW * pipe.resolutionH;
    for (auto& fx : pipe.effects) {
        int effectiveW = pipe.resolutionW / fx.downscale;
        int effectiveH = pipe.resolutionH / fx.downscale;
        float megaPixels = effectiveW * effectiveH / 1000000.0f;

        std::cout << std::setw(25) << std::left << fx.name
                  << std::setw(10) << ("1/" + std::to_string(fx.downscale))
                  << std::setw(8)  << (fx.enabled ? "ON" : "OFF")
                  << std::setw(8)  << fx.aluPerPixel
                  << std::setw(8)  << fx.texSamples
                  << "  [" << std::fixed << std::setprecision(2)
                  << megaPixels << "MP]"
                  << "\n";
    }

    std::cout << std::string(60, '-') << "\n";
    std::cout << "总像素操作: " << std::fixed << std::setprecision(1)
              << (cost.totalPixelOps / 1000000.0) << "M ops\n";
    std::cout << "总带宽: " << cost.totalBandwidthMB << " MB\n";
    std::cout << "预估 GPU 时间: " << std::setprecision(2)
              << cost.estimatedGPUMs << " ms\n\n";
}

int main() {
    std::cout << "========== 后处理成本对比 ==========\n\n";

    // 场景 A：超高画质，全分辨率
    PostPipeline ultra;
    ultra.name = "Ultra — 全分辨率 + 全效果";
    ultra.resolutionW = 1920;
    ultra.resolutionH = 1080;
    ultra.effects = {
        {"Tone Mapping + LUT",       1,  5,   1,  1.0f, true},
        {"Bloom — 亮部提取",         1,  6,   1,  1.0f, true},
        {"Bloom — 降采样 #1",        2,  9,   9,  1.0f, true},
        {"Bloom — 降采样 #2",        4,  9,   9,  1.0f, true},
        {"Bloom — 降采样 #3",        8,  9,   9,  1.0f, true},
        {"Bloom — 降采样 #4",       16,  9,   9,  1.0f, true},
        {"Bloom — 上采样 ×4",        1,  9,   9,  4.0f, true},  // 4 次合成（简化为 1 个条目×4 权重）
        {"Bloom — 合成",             1,  3,   2,  1.0f, true},
        {"DOF — CoC 计算",           1,  15,  3,  1.0f, true},
        {"DOF — 近景模糊",           1,  20,  8,  1.0f, true},
        {"DOF — 远景模糊",           1,  20,  8,  1.0f, true},
        {"DOF — 合成",               1,  8,   3,  1.0f, true},
        {"Motion Blur",              1,  15,  5,  1.0f, true},
        {"SSAO",                     1,  35,  12, 1.0f, true},
        {"SSR",                      1,  50,  20, 1.0f, true},
        {"Film Grain + Vignette",    1,  8,   2,  1.0f, true},
    };

    auto costUltra = AnalyzePipeline(ultra);
    PrintPipeline(ultra, costUltra);

    // 场景 B：优化后，降采样 + 可选效果
    PostPipeline optimized;
    optimized.name = "Optimized — 降采样 + 按优先级";
    optimized.resolutionW = 1920;
    optimized.resolutionH = 1080;
    optimized.effects = {
        {"Tone Mapping + LUT",       1,  5,   1,  1.0f, true},
        {"Bloom — 亮部提取",         1,  6,   1,  1.0f, true},
        {"Bloom — 降采样 #1",        2,  9,   9,  1.0f, true},
        {"Bloom — 降采样 #2",        4,  9,   9,  1.0f, true},
        {"Bloom — 降采样 #3",        8,  9,   9,  1.0f, true},
        // 移除降采样 #4（120×68 太小，贡献不大）
        {"Bloom — 上采样 ×3",        1,  9,   9,  3.0f, true},  // 3 次合成
        {"Bloom — 合成",             1,  3,   2,  1.0f, true},
        {"DOF — CoC 计算 (1/2)",     2,  15,  3,  1.0f, true},  // 半分辨率！
        {"DOF — 近景模糊 (1/2)",     2,  20,  8,  1.0f, true},
        {"DOF — 远景模糊 (1/2)",     2,  20,  8,  1.0f, true},
        {"DOF — 合成",               1,  8,   3,  1.0f, true},
        {"Motion Blur (1/4)",        4,  15,  5,  1.0f, true},  // 1/4 分辨率！
        {"SSAO (1/2)",               2,  35,  12, 1.0f, true},  // 半分辨率
        // SSR 关闭 — 最贵效果，降级时最先关
        {"SSR",                      1,  50,  20, 1.0f, false},
        {"Film Grain + Vignette",    1,  8,   2,  1.0f, true},
    };

    auto costOpt = AnalyzePipeline(optimized);
    PrintPipeline(optimized, costOpt);

    // 对比结果
    std::cout << "========== 优化效果 ==========\n";
    float pixelReduction = (1.0f - costOpt.totalPixelOps / costUltra.totalPixelOps) * 100.0f;
    float bandwidthReduction = (1.0f - costOpt.totalBandwidthMB / costUltra.totalBandwidthMB) * 100.0f;
    float timeReduction = (1.0f - costOpt.estimatedGPUMs / costUltra.estimatedGPUMs) * 100.0f;

    std::cout << "像素操作减少:   " << std::setprecision(1) << pixelReduction << "%\n";
    std::cout << "带宽减少:       " << bandwidthReduction << "%\n";
    std::cout << "预估 GPU 时间减少: " << timeReduction << "%\n";
    std::cout << "节省 GPU 时间:  " << (costUltra.estimatedGPUMs - costOpt.estimatedGPUMs) << " ms\n\n";

    std::cout << "========== 后处理降级策略 ==========\n\n";
    std::cout << "画质档位建议:\n\n";
    std::cout << "Low (集成显卡/移动端):\n";
    std::cout << "  ✓ Tone Mapping + Color Grading\n";
    std::cout << "  ✓ Bloom (1/4 res, 3 级降采样)\n";
    std::cout << "  ✗ DOF, Motion Blur, SSAO, SSR\n\n";

    std::cout << "Medium (中端 GPU):\n";
    std::cout << "  ✓ Tone Mapping + Color Grading\n";
    std::cout << "  ✓ Bloom (1/2 res, 4 级降采样)\n";
    std::cout << "  ✓ SSAO (1/2 res)\n";
    std::cout << "  ✗ DOF, SSR\n\n";

    std::cout << "High (高端 GPU):\n";
    std::cout << "  ✓ 全效果（Bloom, SSAO, DOF 1/2 res, Motion Blur 1/2 res）\n";
    std::cout << "  ✓ SSR (1/2 res)\n\n";

    std::cout << "Ultra (发烧级):\n";
    std::cout << "  ✓ 所有效果全分辨率\n";
    std::cout << "  ✓ Ray Tracing 替代 SSR\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: 在你的项目中测量后处理成本

在 Unity 或 UE 中：
1. 创建一个测试场景，放置一些几何体和光源
2. 用 Profiler 记录一帧的 GPU 时间
3. 逐一禁用后处理效果，测量每种效果的实际 GPU 成本
4. 列出成本排名，与本文的排名表对比

### 练习 2: 实现 Bloom 降采样链

用你熟悉的渲染框架（Unity Shader Graph / Unreal Material / 原生代码）实现一个简化的 Bloom：
1. 提取亮部 Pass（全分辨率）
2. 3 级降采样链（1/2 → 1/4 → 1/8）
3. 3 级上采样合成
4. 对比全分辨率 Bloom vs 降采样 Bloom 的帧率差异

### 练习 3: 设计画质档位（挑战）

为你的游戏设计 4 档后处理画质设置：
1. Low / Medium / High / Ultra — 列出每档开启的效果和分辨率
2. 对每档进行性能基准测试
3. 确保 Low 和 Ultra 的 GPU 时间差 < 5ms（60fps 预算的 30%）
4. 使用 Console Variables / Quality Settings 实现运行时切换

---

## 4. 扩展阅读

- **Next-Gen Post Processing in Call of Duty (GDC 2015)** — Activision 的后处理管线分享，大量降采样技术
- **UE Post Process Materials** — https://docs.unrealengine.com/5.0/en-US/post-process-materials-in-unreal-engine/：UE 后处理材质系统
- **Unity URP Post Processing** — https://docs.unity3d.com/Packages/com.unity.render-pipelines.universal@latest/manual/integration-with-post-processing.html
- **Kawase Bloom** — 一种高效的 Bloom 算法，使用多 Pass 且极轻量
- **GPU Zen 2 — Advanced Rendering Techniques** — 包含 Compute Shader 后处理的最佳实践章节

---

## 常见陷阱

- **每帧重建 Render Target**：为每个后处理 Pass 动态创建 RT 然后在帧末销毁，导致大量内存分配。正确做法：提前分配并复用 RT 池。
- **降采样用 Point Sampling**：降采样时用 Point（最近邻）采样会导致明显的锯齿和闪烁。始终用双线性或更好的 filter。
- **Bloom 阈值设太低**：`threshold=0` 意味着整个场景都参与 Bloom → 画面过曝 + 浪费大量降采样 Pass 处理暗部像素。典型阈值: 1.0-1.5（HDR 值）。
- **后处理 Pass 不必要地多**：Color Grading + Tone Mapping + White Balance + Contrast 可以合并为一个 Pass。每加一个 Pass = 全屏像素再处理一次。
- **SSAO 采样数太高**：默认 16-32 个方向采样已经足够。有人设为 64 或 128，但视觉差异极小，成本翻倍。
- **忘记移动端 Bloom**：移动 GPU（尤其 TBDR）在做全屏多次 Pass 时效率很低。考虑使用预计算的 Lens Flare 贴图 + 简单的高斯模糊（单一方向 2 Pass）代替完整 Bloom 降采样链。
