---
title: "Shader 优化基础 — ALU、采样、精度、变体"
updated: 2026-06-05
---

# Shader 优化基础 — ALU、采样、精度、变体
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: 05-Draw Call 优化 (了解渲染管线和 Shader 基本概念)

---

## 1. 概念讲解

### 为什么需要这个？

在现代游戏中，一个像素可能被 Shader 执行数百条指令。1080p 分辨率下每帧有 200 万像素，如果平均 Overdraw 是 2.5x，就是 500 万次 Pixel Shader 调用。每条多余的指令乘以 500 万，就是实实在在的 GPU 时间。

一个真实案例：《使命召唤》的技术分享中提到，他们将一个角色 Shader 从 180 条 ALU 指令优化到 85 条，单帧 GPU 时间从 2.1ms 降到 1.0ms——在 60fps 游戏中释放了 1.1ms，等于多了 6.6% 的帧预算。

**Shader 优化的本质是在不损害视觉质量的前提下，减少 GPU 每个像素/顶点的计算量。**

### 核心思想

#### 1. GPU 指令成本层级

GPU 不同操作的成本差别巨大。以下是现代 GPU（AMD RDNA3 / NVIDIA Ada Lovelace）的大致成本排序（以单精度 FMA 为基准 = 1x）：

| 操作 | 相对成本 | 说明 |
|------|----------|------|
| FMA (fused multiply-add) | 1.0x | `a*b + c`，现代 GPU 的基础单元 |
| ADD/SUB | ~0.5x | 可与 MUL 配对 |
| MUL | ~0.5x | 同上 |
| RCP (reciprocal) | 4-8x | `1/x`，使用查找表+牛顿迭代 |
| RSQRT (inverse sqrt) | 4-8x | `1/sqrt(x)`，同上 |
| SIN/COS | 8-16x | 使用泰勒级数或查找表 |
| POW/EXP/LOG | 10-20x | 超越函数，避免在 Pixel Shader 中使用 |
| Texture Sample | 10-50x | 取决于缓存命中、过滤模式 |
| Branch (taken) | ？ | 取决于 divergence；warp/wave 内部分支代价高 |
| Discard/clip | 高 | 禁用 Early-Z 优化 |

关键认知：**一次 Texture Sample 的代价远大于几十条 ALU 指令**。所以用 ALU 计算代替纹理查找往往是正确的优化方向。

#### 2. ALU 优化

**MAD 合并**：现代 GPU 中 `a*b + c` 是一条指令，不是两条。所以：
```hlsl
// 不优化（两条指令：MUL + ADD）
float result = a * b;
result = result + c;

// 优化（一条 FMA 指令）
float result = mad(a, b, c);  // 或直接 a * b + c，编译器通常会优化
```

**避免分支（Branch Divergence）**：GPU 以 warp（NVIDIA，32 线程）或 wavefront（AMD，64 线程）为单位执行。如果 warp 内部分线程走 if，部分走 else，两种路径都要执行，只是结果被 mask 掉。

```hlsl
// 坏：动态分支
if (someDynamicCondition) {
    result = ExpensiveCalcA();  // 整个 warp 都要执行这个
} else {
    result = ExpensiveCalcB();  // 整个 warp 也都要执行这个
}

// 好：用数学代替分支
float t = step(0, someDynamicCondition); // 0 或 1
result = lerp(CheapCalcA(), CheapCalcB(), t);

// 更好：让分支条件在 warp 内一致
// uniform bool 的分支是零开销的
```

**避免 discard/clip**：`discard` 和 `clip()` 禁用 Early-Z（GPU 无法在 PS 执行前判断像素是否可见），导致 Hidden Surface Removal 失效。替代方案：使用 alpha-to-coverage 或依赖深度测试。

**标量化**：将向量计算中不需要的分量去掉：
```hlsl
// 坏：计算完整的 float4
float4 color = texture.Sample(sampler, uv);  // 采样 4 个通道
float alpha = color.a; // 只要 alpha

// 好：如果只需要单通道，使用单通道纹理（R8 格式）
float alpha = texAlpha.Sample(sampler, uv).r;  // 只采样 1 通道
```

#### 3. 纹理采样优化

**Independent vs Dependent 纹理读取**：
- Independent read：UV 直接从顶点属性插值而来，GPU 可以预取（prefetch）
- Dependent read：UV 通过 Shader 计算得出（如法线贴图扰动后的 UV），无法预取

```hlsl
// Independent read — GPU 可以预取，延迟低
float3 baseColor = texBase.Sample(sampler, input.uv).rgb;

// Dependent read — 必须等法线贴图采样完成才能计算 UV
float3 N = texNormal.Sample(sampler, input.uv).xyz;
float2 perturbedUV = input.uv + N.xy * parallaxStrength;
float3 baseColor = texBase.Sample(sampler, perturbedUV).rgb; // 依赖前一步
// ↑ 两次采样串行，延迟翻倍
```

**LOD 控制**：手动控制 Mip Level 可以减少采样延迟：
```hlsl
// 显式指定 LOD — GPU 不需要计算导数
float3 color = tex.SampleLevel(sampler, uv, 3.0).rgb; // 直接用 Mip Level 3

// SampleGrad — 手动提供导数，在 Compute Shader 中常用
float3 color = tex.SampleGrad(sampler, uv, ddx, ddy).rgb;
```

**各向异性过滤（Anisotropic Filtering）**：默认的三线性过滤在斜视表面时模糊。各向异性过滤（2x–16x）以极小成本提升质量，现代 GPU 几乎零开销。但要注意：AF x16 意味着最多采样 128 个纹素（vs 三线性的 8 个），在带宽受限的移动端需要审慎使用。

#### 4. 精度优化

| 精度类型 | 位宽 | 范围 | 精度 | 适用场景 |
|----------|------|------|------|----------|
| float (fp32) | 32 | ±3.4×10^38 | ~7 位十进制 | 世界坐标、深度值 |
| half (fp16) | 16 | ±65504 | ~3 位十进制 | 颜色、法线（归一化后）、UV |
| min16float | ≥16 | 至少 fp16 | 至少 fp16 | 移动端优化，驱动可能用 fp16 |
| fixed (fp10) | 10 | -2 到 2 | ~0.002 | 颜色分量 |

在移动端（Mali, Adreno, Apple GPU），fp16 运算吞吐量通常是 fp32 的 2 倍。在桌面端（NVIDIA/AMD），fp16 吞吐量与 fp32 相同（但寄存器压力减半）。

```hlsl
// 精度提示
half3 color = tex.Sample(sampler, uv).rgb;  // 用 half
half NdotL = saturate(dot((half3)normal, (half3)lightDir)); // 显式转换
float depth = input.position.z;  // 深度必须用 float
```

注意：`half` 在 HLSL 中是最低精度提示，驱动可能仍用 fp32。使用 `min16float` 可以获得更确定的优化效果（需要 Shader Model 6.2+）。

#### 5. Shader 变体爆炸

Shader 变体（Variant）是指同一个 .shader 文件由于不同的编译宏组合产生的不同版本。

**变体数计算**：
```
变体数 = 2^(#pragma multi_compile 宏数量) × ∏(每个 shader_feature 枚举数)
```

一个典型案例：
```hlsl
#pragma multi_compile _ NORMAL_MAP          // 2 种
#pragma multi_compile _ METALLIC_MAP        // 2 种
#pragma multi_compile _ EMISSION_MAP        // 2 种
#pragma multi_compile _ LIGHTMAP_ON         // 2 种
#pragma multi_compile _ SHADOWS_ON          // 2 种
#pragma multi_compile _ FOG_LINEAR FOG_EXP  // 3 种
// 总变体数: 2×2×2×2×2×3 = 96
```

如果有 10 个这样的 Shader，就是 960 个变体需要编译。编译时间从秒级变成分钟级。

**减少变体策略**：
1. **合并宏**：`NORMAL_MAP` 和 `HEIGHT_MAP` 总是同时出现 → 合并为一个 `DETAIL_MAP`
2. **用 Shader Feature 代替 Multi Compile**：`shader_feature` 只编译实际使用的变体，`multi_compile` 预编译所有组合
3. **运行时选择**：把不常用的分支移到 `if` 中（Uniform 分支零开销）
4. **Shader 拆分**：把功能差异大的部分拆成独立 Shader
5. **预编译剔除**：Unity 的 `IPreprocessShaders` 接口，UE 的 Shader Permutation Reduction

**Shader Stripping**：编译后删除未使用的变体。Unity 通过 `ShaderVariantCollection` 预热需要的变体，其余不打包。UE 通过 `.ini` 配置和 `ShouldCompilePermutation` 过滤。

---

## 2. 代码示例

### 示例 1：分支 vs 无分支（HLSL）

```hlsl
// shader_opt_comparison.hlsl — 同一功能的 4 种实现
// 在 Unity/UE 中创建一个 Unlit Shader，替换 frag 函数体测试

// ====== 场景：根据阈值混合两种颜色 ======
float threshold = 0.5;
float3 colorA = float3(1, 0, 0);  // 红色
float3 colorB = float3(0, 0, 1);  // 蓝色

// ❌ 实现 1：动态分支（最差，会导致 divergence）
float3 Branch_Dynamic(float value) {
    if (value > threshold)
        return colorA;
    else
        return colorB;
}
// 编译结果（AMD RDNA ISA，大致）：
//   v_cmp_gt_f32  s[0:1], v0, 0.5   // 比较
//   s_and_saveexec_b64 s[2:3], s[0:1] // 保存执行掩码
//   ... colorA 路径 ...
//   s_andn2_saveexec_b64 s[2:3], s[0:1] // 取反掩码
//   ... colorB 路径 ...

// ✅ 实现 2：lerp（好，无分支）
float3 Branch_Lerp(float value) {
    float t = step(threshold, value); // 0.0 或 1.0
    return lerp(colorB, colorA, t);
}
// 编译结果：
//   v_cmp_ge_f32  vcc, v0, 0.5      // 比较 → 布尔
//   v_cndmask_b32 v1, colorB, colorA, vcc // 条件选择
//   总共 ~3 条指令，无分支

// ✅ 实现 3：直接数学（最好，但可读性差）
float3 Branch_Math(float value) {
    // 利用 sign 和 saturate
    float t = saturate(sign(value - threshold));
    return colorB + (colorA - colorB) * t;
}
// 与 lerp 编译结果几乎相同

// ====== 场景 2：避免 discard ======
// ❌ discard 禁用 Early-Z
float4 AlphaTest_Discard(float alpha) {
    if (alpha < 0.5) discard;  // 整个管线的 Early-Z 被禁用
    return float4(1, 1, 1, alpha);
}

// ✅ alpha-to-coverage（需要 MSAA）
// 在 Shader 中输出 alpha，硬件自动做 coverage
float4 AlphaTest_Coverage(float alpha) {
    // 配合管线状态：AlphaToCoverageEnable = true
    return float4(1, 1, 1, alpha); // 硬件处理丢弃逻辑
}

// ====== 场景 3：降低精度 ======
// ❌ 全精度（移动端昂贵）
float3 NormalMapping(float3 tangentNormal) {
    float3 N = tangentNormal * 2.0 - 1.0;  // fp32
    N = normalize(N);                        // rsqrt 在 fp32
    return N;
}

// ✅ 半精度（移动端友好）
half3 NormalMapping_Half(half3 tangentNormal) {
    half3 N = tangentNormal * 2.0 - 1.0;    // fp16
    N = normalize(N);                        // rsqrt 在 fp16（快 2x）
    return N;
}
```

### 示例 2：C++ 分析工具 — 模拟 Shader 变体计数

```cpp
// shader_variant_count.cpp — 计算 Shader 变体数和编译时间估算
// 编译: g++ -std=c++17 shader_variant_count.cpp -o variant_count && ./variant_count

#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <iomanip>

struct ShaderDefine {
    std::string name;
    int optionCount;  // 选项数（multi_compile 是 2，枚举可以更多）

    ShaderDefine(const std::string& n, int c) : name(n), optionCount(c) {}
};

struct ShaderInfo {
    std::string name;
    std::vector<ShaderDefine> defines;
    float avgCompileTimeMs;  // 单变体编译时间（ms）
};

// 计算变体数
int CountVariants(const std::vector<ShaderDefine>& defines) {
    int total = 1;
    for (auto& d : defines) {
        total *= d.optionCount;
    }
    return total;
}

int main() {
    std::cout << "========== Shader 变体爆炸分析 ==========\n\n";

    // 定义一个典型的标准 PBR Shader
    ShaderInfo standardPBR;
    standardPBR.name = "Standard PBR Shader";
    standardPBR.avgCompileTimeMs = 50.0f; // 每个变体平均 50ms 编译时间
    standardPBR.defines = {
        {"_NORMALMAP", 2},       // ON/OFF
        {"_METALLICGLOSSMAP", 2},
        {"_EMISSION", 2},
        {"_OCCLUSION", 2},
        {"_DETAIL_MULX2", 2},
        {"_SPECULARHIGHLIGHTS_OFF", 2},
        {"_GLOSSYREFLECTIONS_OFF", 2},
        {"_PARALLAXMAP", 2},
        {"_SPECCOOKIE", 2},
        {"DIRECTIONAL", 2},
        {"SHADOWS_SCREEN", 2},
        {"LIGHTMAP_ON", 2},
        {"FOG_LINEAR FOG_EXP FOG_EXP2", 4},
        {"INSTANCING_ON", 2},
    };

    int variants = CountVariants(standardPBR.defines);
    float compileTime = variants * standardPBR.avgCompileTimeMs / 1000.0f;
    float storageMB = variants * 12.0f / 1024.0f;  // 假设每个变体 12KB

    std::cout << "Shader: " << standardPBR.name << "\n";
    std::cout << "  宏定义数: " << standardPBR.defines.size() << "\n";
    for (auto& d : standardPBR.defines) {
        std::cout << "    " << std::setw(30) << std::left << d.name
                  << " → " << d.optionCount << " 选项\n";
    }
    std::cout << "\n  总变体数: " << variants << "\n";
    std::cout << "  预估编译时间: " << compileTime << " 秒 ("
              << (compileTime / 60.0f) << " 分钟)\n";
    std::cout << "  预估 Shader 库大小: " << storageMB << " MB\n";

    // 优化后：合并和移除不必要的宏
    std::cout << "\n========== 优化措施 ==========\n\n";

    ShaderInfo optimizedPBR;
    optimizedPBR.name = "Optimized PBR Shader";
    optimizedPBR.avgCompileTimeMs = 50.0f;
    optimizedPBR.defines = {
        // 合并 _METALLICGLOSSMAP + _SPECULARHIGHLIGHTS_OFF + _GLOSSYREFLECTIONS_OFF
        // → 一个枚举 MACRO_SURFACE_TYPE
        {"SURFACE_TYPE (合并 8 种情况)", 3},

        // _NORMALMAP + _PARALLAXMAP → DETAIL_MAP
        {"DETAIL_MAP_LEVEL", 3},

        // 合并 LIGHTMAP + DIRECTIONAL + SHADOWS → LIGHTING_MODE
        {"LIGHTING_MODE", 3},

        // _EMISSION + _OCCLUSION 按需 — 用 shader_feature 代替 multi_compile（不预编译）
        // _SPECCOOKIE 移除 — 很少用的功能，单独 Shader

        // FOG 合并
        {"FOG_MODE", 3},

        // 保留 INSTANCING_ON
        {"INSTANCING_ON", 2},

        // _DETAIL_MULX2 用 uniform branch 代替
    };

    int optimizedVariants = CountVariants(optimizedPBR.defines);
    float optCompileTime = optimizedVariants * optimizedPBR.avgCompileTimeMs / 1000.0f;
    float optStorageMB = optimizedVariants * 12.0f / 1024.0f;

    std::cout << "Shader: " << optimizedPBR.name << "\n";
    std::cout << "  宏定义数: " << optimizedPBR.defines.size() << "\n";
    std::cout << "  总变体数: " << optimizedVariants << "\n";
    std::cout << "  预估编译时间: " << optCompileTime << " 秒\n";
    std::cout << "  预估 Shader 库大小: " << optStorageMB << " MB\n\n";

    std::cout << "========================================\n";
    std::cout << "变体减少: " << variants << " → " << optimizedVariants
              << " (减少 " << (100.0f * (variants - optimizedVariants) / variants)
              << "%)\n";
    std::cout << "编译时间减少: " << compileTime << "s → " << optCompileTime
              << "s (节省 " << (compileTime - optCompileTime) << "s)\n";
    std::cout << "========================================\n\n";

    // 实际建议
    std::cout << "========== Shader 优化检查清单 ==========\n";
    std::cout << "□ 1. 搜索项目中的 '#pragma multi_compile':\n";
    std::cout << "     每个 'multi_compile' 都是 2^n 的乘数\n";
    std::cout << "□ 2. 用 'shader_feature' 替代 'multi_compile':\n";
    std::cout << "     只编译 Material 实际引用的变体\n";
    std::cout << "□ 3. 合并相关宏为枚举:\n";
    std::cout << "     #pragma multi_compile _ A B C D → 1 个 4-选项宏\n";
    std::cout << "□ 4. 拆分大 Shader:\n";
    std::cout << "     把罕见功能（视差、cookie）移到独立 Shader\n";
    std::cout << "□ 5. 用 Uniform Branch 代替部分宏:\n";
    std::cout << "     [if (uniform_bool)] 在 GPU 上零开销（无 divergence）\n";
    std::cout << "□ 6. 运行时统计实际使用的变体:\n";
    std::cout << "     Unity: ShaderVariantCollection\n";
    std::cout << "     UE:    r.ShaderDevelopmentMode 1\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: 手算变体数

某个 Unity URP Lit Shader 有以下宏定义：
```
#pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
#pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
#pragma multi_compile_fragment _ _SHADOWS_SOFT
#pragma multi_compile _ LIGHTMAP_ON
#pragma multi_compile _ FOG_LINEAR FOG_EXP FOG_EXP2
```

计算总变体数。如果将 `_MAIN_LIGHT_SHADOWS*` 合并为一个枚举（4 选项），总数变为多少？

### 练习 2: 分析你自己的 Shader

拿一个你项目中实际使用的 Shader：
1. 统计所有 `#pragma multi_compile` 和 `#pragma shader_feature`
2. 计算理论最大变体数
3. 找出 3 个可以合并或移除的宏
4. 估算优化后的变体数

### 练习 3: 实现精度对比测试（挑战）

在一个支持 fp16 的平台上（移动设备或 Vulkan/DX12 桌面），创建一个 Compute Shader：
- 用 fp32 做 1000000 次 `normalize()` 计算
- 用 fp16 做同样的计算
- 用 GPU timestamp query 测量两次的时间差
- 对比结果精度损失

---

## 4. 扩展阅读

- **NVIDIA GPU 架构白皮书** — https://developer.nvidia.com/gpu-architecture：各代架构的指令吞吐量表
- **AMD RDNA3 ISA 手册** — https://gpuopen.com/learn/rdna3-isa/：底层指令集参考，了解哪些操作是真正的单指令
- **EA Frostbite — Shader Permutation Reduction** — GDC 2017：工业级 Shader 变体管理案例
- **ARM Mali GPU 优化指南** — https://developer.arm.com/documentation/101897/latest/：移动端 Shader 优化的权威参考，包含 fp16 数据
- **Unity Shader Variant 文档** — https://docs.unity3d.com/Manual/shader-variants.html

---

## 常见陷阱

- **把乘法拆开写不合并**：`a*b; c = a+d;` 不如写成一组。现代编译器会重排，但在移动端 GLSL 上不一定。显式用 `mad()` 更安全。
- **在 Pixel Shader 中用 `pow()`**：`pow(x, 2.0)` 比 `x*x` 慢 10 倍以上。`pow(x, 2.2)` 用于 Gamma 是必要的，但简单的平方或立方直接用乘法。
- **在分支内采样纹理**：纹理采样延迟很高（几百个周期），分支掩盖不了。尽量提前采样，再在分支内用采样结果做计算。
- **全项目用 fp32**：在移动端这意味着浪费 50% 的 ALU 吞吐量。颜色、法线（归一化后）、UV 用 half/mediump 足够了。
- **忘记 Shader 也有 Cache**：合理组织纹理读取顺序，让相邻像素访问相邻纹理地址（空间局部性），可以大幅提高 Texture Cache 命中率。
- **Shader 变体默认全编译**：Unity 项目首次导入时可能编译上万个变体，编译时间以小时计。配置 `ShaderVariantCollection` 只编译实际需要的变体。
