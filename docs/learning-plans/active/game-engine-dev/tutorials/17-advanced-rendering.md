# 高级渲染技术：PBR、光线追踪与 GPU Driven Rendering

> **所属计划**: [游戏引擎开发工程师](../plan.md)
> **预计耗时**: 10 小时
> **前置知识**: [06-渲染管线基础](06-rendering-pipeline.md), [07-着色器编程](07-shader-programming.md), [09-光照与材质系统](09-lighting-and-materials.md)

---

## 概述

在掌握了渲染管线基础、着色器编程和光照系统之后，本章将深入现代游戏引擎中使用的高级渲染技术。这些技术是实现高品质视觉效果的核心——从完整的 PBR 材质系统到后处理管线，从屏幕空间效果到光线追踪，每一项都是当代 3A 游戏引擎渲染系统的关键组成部分。

---

## 1. PBR 渲染管线完整实现

基于物理的渲染（Physically Based Rendering, PBR）是现代游戏引擎的标准光照模型。与 Phong/Blinn-Phong 等经验模型不同，PBR 基于微表面模型和能量守恒原理，使用物理可解释的参数来描述材质属性。

### Metallic-Roughness 工作流

游戏引擎中最常用的 PBR 参数化方案是 Metallic-Roughness 工作流：

| 材质 | Metallic | Roughness | Albedo | 说明 |
|:-----|:---------|:----------|:-------|:-----|
| 木材 | 0.0 | 0.3-0.8 | 棕色 | 非金属，漫反射材质 |
| 塑料 | 0.0 | 0.1-0.3 | 彩色 | 非金属，较光滑 |
| 铁 | 1.0 | 0.2-0.6 | 浅灰色 | 金属，F0 由 Albedo 决定 |
| 金 | 1.0 | 0.1-0.3 | 金黄色 | 金属，有色 F0 |
| 水/玻璃 | 0.0 | 0.0-0.1 | 白色 | 非金属，极低粗糙度 |

**Metallic（金属度）** 控制材质是金属还是非金属。当 Metallic = 1.0 时，漫反射分量为零；当 Metallic = 0.0 时，F0 = 0.04（典型非金属反射率）。

**Roughness（粗糙度）** 控制表面光滑程度。Roughness 直接输入法线分布函数的 alpha 参数：$\alpha = \text{Roughness}^2$。

### Cook-Torrance BRDF

$$f_r = k_d \cdot f_{lambert} + k_s \cdot f_{cook-torrance}$$

镜面反射项：

$$f_{cook-torrance} = \frac{D(\mathbf{h}) \cdot F(\mathbf{v}, \mathbf{h}) \cdot G(\mathbf{l}, \mathbf{v}, \mathbf{h})}{4(\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})}$$

**法线分布函数 D（GGX）**：

$$D_{GGX}(\mathbf{h}) = \frac{\alpha^2}{\pi((\mathbf{n} \cdot \mathbf{h})^2(\alpha^2 - 1) + 1)^2}$$

**几何遮蔽函数 G（Schlick-GGX）**：

$$G_{GGX}(\mathbf{l}, \mathbf{v}, \mathbf{h}) = G_1(\mathbf{l}) \cdot G_1(\mathbf{v})$$

$$G_1(\mathbf{v}) = \frac{\mathbf{n} \cdot \mathbf{v}}{(\mathbf{n} \cdot \mathbf{v})(1 - k) + k}$$

其中 $k = \frac{(\alpha + 1)^2}{8}$（直接光照）或 $k = \frac{\alpha^2}{2}$（IBL）。

**菲涅尔方程 F（Schlick 近似）**：

$$F_{Schlick}(\cos\theta, F_0) = F_0 + (1 - F_0)(1 - \cos\theta)^5$$

### IBL 环境光照

Image-Based Lighting 使用环境贴图模拟来自四面八方的间接光照。

**漫反射 IBL**：预计算辐照度贴图（Irradiance Map），离线对环境贴图进行卷积。

**镜面反射 IBL**：使用 Split Sum Approximation 分解为两部分——Prefiltered Map（按粗糙度模糊的环境贴图）和 BRDF LUT（预计算的菲涅尔积分）。

```glsl
// BRDF LUT 生成着色器（简化版）
vec2 Hammersley(uint i, uint N) {
    uint bits = (i << 16u) | (i >> 16u);
    bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);
    bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);
    bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);
    bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);
    float rdi = float(bits) * 2.3283064365386963e-10;
    return vec2(float(i) / float(N), rdi);
}

vec3 ImportanceSampleGGX(vec2 Xi, vec3 N, float roughness) {
    float a = roughness * roughness;
    float phi = 2.0 * PI * Xi.x;
    float cosTheta = sqrt((1.0 - Xi.y) / (1.0 + (a*a - 1.0) * Xi.y));
    float sinTheta = sqrt(1.0 - cosTheta * cosTheta);
    vec3 H = vec3(cos(phi)*sinTheta, sin(phi)*sinTheta, cosTheta);
    vec3 up = abs(N.z) < 0.999 ? vec3(0,0,1) : vec3(1,0,0);
    vec3 tangent = normalize(cross(up, N));
    vec3 bitangent = cross(N, tangent);
    return normalize(tangent * H.x + bitangent * H.y + N * H.z);
}
```

---

## 2. 屏幕空间效果

### 屏幕空间环境光遮蔽（SSAO）

SSAO 在屏幕空间近似环境光遮蔽效果，避免了离线烘焙的开销。

**实现原理**：对于每个像素，在其周围半球上采样若干点，将这些采样点变换到屏幕空间，采样对应位置的深度值。如果采样点深度比当前像素更近，则认为该方向被遮挡。

```glsl
void main() {
    float depth = texture(uDepthMap, vTexCoord).r;
    vec3 fragPos = reconstructViewPosition(vTexCoord, depth);
    vec3 normal = normalize(texture(uNormalMap, vTexCoord).rgb);

    // 随机旋转采样核
    vec3 randomVec = vec3(
        fract(sin(dot(vTexCoord, vec2(12.9898, 78.233))) * 43758.5453),
        fract(sin(dot(vTexCoord, vec2(93.9898, 67.345))) * 24634.6345),
        0.0
    );

    vec3 tangent = normalize(randomVec - normal * dot(randomVec, normal));
    vec3 bitangent = cross(normal, tangent);
    mat3 TBN = mat3(tangent, bitangent, normal);

    float occlusion = 0.0;
    for (int i = 0; i < params.sampleCount; i++) {
        vec3 samplePos = fragPos + TBN * params.samples[i].xyz * params.radius;
        vec4 offset = params.projection * vec4(samplePos, 1.0);
        offset.xyz = offset.xyz / offset.w * 0.5 + 0.5;

        float sampleDepth = texture(uDepthMap, offset.xy).r;
        vec3 sampleViewPos = reconstructViewPosition(offset.xy, sampleDepth);
        float rangeCheck = smoothstep(0.0, 1.0,
            params.radius / abs(fragPos.z - sampleViewPos.z));
        occlusion += (sampleViewPos.z >= samplePos.z + params.bias ? 1.0 : 0.0)
                    * rangeCheck;
    }

    occlusion = 1.0 - (occlusion / float(params.sampleCount));
    FragColor = pow(occlusion, params.intensity);
}
```

**关键要点**：随机旋转采样核消除条带 artifact；范围检查（Range Check）避免远处深度错误计入；Bias 参数防止表面自遮蔽。

更现代的 **GTAO**（Ground Truth Ambient Occlusion）提供了更精确的遮蔽计算，考虑了地平线角度和多次反弹。GTAO 基于射线追踪的地面 truth 进行近似，考虑了法线方向、视角方向和环境光的颜色分布，是当前最高质量的屏幕空间 AO 方案。相比 SSAO，GTAO 能更准确地模拟光线在凹角处的遮蔽行为，且结果更接近离线渲染的质量。

### 屏幕空间反射（SSR）

SSR 在屏幕空间追踪反射射线，仅反射屏幕上可见的内容：

1. 计算反射射线：$\mathbf{R} = \text{reflect}(-\mathbf{V}, \mathbf{N})$
2. 将射线从视图空间变换到屏幕空间
3. 沿屏幕空间的射线方向进行步进或二分查找
4. 当射线深度与场景深度相交时，采样对应的屏幕颜色作为反射颜色

SSR 的主要限制是无法反射屏幕外的物体和背面，通常配合反射探针和 Planar Reflection 使用。

### 屏幕空间次表面散射（SSSSS）

SSSSS 模拟光线在半透明材质（皮肤、蜡、玉石等）内部的散射效果。核心是基于屏幕空间的高斯模糊——根据材质的散射距离配置文件，对漫反射光照缓冲进行可分离的高斯模糊。

---

## 3. 后处理管线

### 泛光（Bloom）

Bloom 模拟相机镜头观察极高亮度区域时的光晕效果：

1. **亮度提取**：从 HDR 图像中提取超过阈值的亮色区域
2. **下采样与模糊**：对亮色区域多次下采样，每次使用高斯模糊
3. **上采样与叠加**：将模糊后的各级亮度图上采样累加，叠加到原图

高斯模糊的可分离性是关键优化——二维 $N \times N$ 高斯模糊需要 $N^2$ 次采样，分离为水平和垂直两次一维模糊只需 $2N$ 次。

现代引擎中更高效的 Bloom 方案采用双向下采样+上采样（Dual Filtering）或 Kawase Blur，在保持视觉质量的同时减少采样次数。Dual Filtering 利用双线性采样在单次采样中获取 2x2 像素块的平均值，大幅减少下采样 Pass 的数量。Kawase Blur 则通过多次小核模糊叠加来近似大核高斯模糊，每次 Pass 只需 4-9 次采样，总采样数远低于传统高斯模糊。

### 色调映射（Tone Mapping）

色调映射将 HDR 的宽动态范围压缩到显示设备的有限范围内。经典的 Reinhard 色调映射公式为：

```glsl
vec3 Reinhard(vec3 color) {
    return color / (color + vec3(1.0));
}
```

这个公式将 `[0, infinity)` 映射到 `[0, 1)`，但暗部对比度损失较大，高亮区域容易被过度压缩，导致画面发灰。

**ACES Filmic Tone Mapping**（Academy Color Encoding System）是当前业界标准，由电影艺术与科学学院开发，在影视和游戏行业广泛应用。ACES 在暗部保持更好的对比度，在高光部分提供更自然的"肩膀"压缩：

```glsl
vec3 ACESFitted(vec3 color) {
    const mat3 ACES_INPUT_MAT = mat3(
        0.59719, 0.35458, 0.04823,
        0.07600, 0.90834, 0.01566,
        0.02840, 0.13383, 0.83777
    );
    const mat3 ACES_OUTPUT_MAT = mat3(
        1.60475, -0.53108, -0.07367,
        -0.10208,  1.10813, -0.00605,
        -0.00327, -0.07276,  1.07602
    );
    color = ACES_INPUT_MAT * color;
    vec3 a = color * (color + 0.0245786) - 0.000090537;
    vec3 b = color * (0.983729 * color + 0.4329510) + 0.238081;
    color = a / b;
    color = ACES_OUTPUT_MAT * color;
    return clamp(color, 0.0, 1.0);
}
```

### 色彩分级（Color Grading / LUT）

使用 3D LUT（Look-Up Texture）实现色彩分级。离线使用 DaVinci Resolve 等工具调色，烘焙为 3D LUT 纹理。运行时只需一次 LUT 采样：

```glsl
vec3 applyColorGrading(vec3 color, sampler2D lutTexture, float lutSize) {
    color = clamp(color, 0.0, 1.0);
    float blueIndex = color.b * (lutSize - 1.0);
    float blueIndexFract = fract(blueIndex);
    float halfTexel = 0.5 / lutSize;
    float scale = (lutSize - 1.0) / lutSize;
    vec2 lutUV = (color.rg * scale + halfTexel);
    float sliceSize = 1.0 / lutSize;
    float sliceOffset = floor(blueIndex) * sliceSize;
    lutUV.x += sliceOffset;
    vec3 lutColor1 = texture(lutTexture, lutUV).rgb;
    lutUV.x += sliceSize;
    vec3 lutColor2 = texture(lutTexture, lutUV).rgb;
    return mix(lutColor1, lutColor2, blueIndexFract);
}
```

### 时间性抗锯齿（TAA）

TAA（Temporal Anti-Aliasing）是现代 3A 游戏中最主流的抗锯齿方案，通常作为后处理管线的一部分实现。它利用了时序维度的信息：每帧对投影矩阵施加一个子像素偏移（Jitter），使得相邻帧采样的是略微不同的子像素位置；然后通过帧间混合（通常使用指数移动平均）累积历史颜色：

```glsl
// TAA 混合
vec3 currentColor = texture(currentFrame, uv).rgb;
vec2 historyUV = uv + motionVector;  // 重投影到历史帧
vec3 historyColor = texture(historyFrame, historyUV).rgb;

// 邻域裁剪：将历史颜色限制在当前像素 3x3 邻域的颜色包围盒内
vec3 neighborMin = vec3(1.0), neighborMax = vec3(0.0);
for(int x = -1; x <= 1; x++) {
    for(int y = -1; y <= 1; y++) {
        vec3 c = texture(currentFrame, uv + vec2(x,y) * texelSize).rgb;
        neighborMin = min(neighborMin, c);
        neighborMax = max(neighborMax, c);
    }
}
historyColor = clamp(historyColor, neighborMin, neighborMax);

// 基于运动向量长度调整混合因子
float blendFactor = mix(0.1, 0.9, length(motionVector) * 100.0);
vec3 finalColor = mix(historyColor, currentColor, blendFactor);
```

TAA 的核心优势在于：对于静态画面，N 帧的累积等效于 N 倍超采样的效果；对于动态画面，有效采样率仍然高于单帧。

TAA 的实现需要解决几个关键技术问题：

1. **重投影（Reprojection）**：需要根据场景运动和相机运动，将历史帧的像素坐标变换到当前帧坐标，以找到对应的累积位置。这需要每帧生成运动向量（Motion Vector，即场景在屏幕空间的速度场）。

2. **鬼影（Ghosting）**：当遮挡关系发生变化（如物体移动揭露新背景）时，累积的历史颜色可能来自被遮挡的物体，导致拖影。解决方案包括深度测试、邻域裁剪（Neighborhood Clipping）——将历史颜色限制在当前像素 3x3 邻域的颜色包围盒内，以及基于运动向量长度调整混合因子。

3. **子像素抖动（Jitter）**：每帧对投影矩阵施加一个子像素偏移，常用的抖动模式包括 Halton 序列或低差异序列，确保在多个帧内均匀覆盖子像素空间。

TAA 与超分辨率技术（DLSS、FSR 2.0、XeSS）结合使用已成为现代游戏的标准做法。这些技术本质上是在 TAA 的基础上增加了上采样步骤，以较低的内部渲染分辨率达到接近原生分辨率的视觉效果。

---

## 4. 实时光线追踪

### 加速结构（BLAS / TLAS）

| 加速结构 | 全称 | 构建内容 | 更新频率 |
|:---------|:-----|:---------|:---------|
| BLAS | Bottom-Level AS | 单个物体的三角形网格 | 低（物体变形时） |
| TLAS | Top-Level AS | 场景中所有物体的实例 | 每帧（物体移动时） |

BLAS 在场景加载时构建，每个静态 Mesh 构建一次。TLAS 每帧重建，包含场景中所有需要光线追踪的物体实例。

### 光线追踪管线着色器

光线追踪管线包含五种新的着色器阶段：

- **Ray Generation Shader**：程序入口，每个像素执行一次，发射初始光线
- **Intersection Shader**：自定义几何相交测试
- **Any-Hit Shader**：光线与三角形相交时调用，可用于 Alpha Test
- **Closest-Hit Shader**：找到最近交点后调用，计算反射/折射/阴影颜色
- **Miss Shader**：光线未与任何物体相交时调用

### 混合渲染管线

在实时光线追踪游戏中，通常采用混合渲染：

| 效果 | 光栅化方案 | 光线追踪方案 | 性能开销 |
|:-----|:-----------|:-------------|:---------|
| 阴影 | Shadow Map / CSM | RT Shadow | 中等 |
| 反射 | SSR + 反射探针 | RT Reflection | 高 |
| 全局光照 | Lightmap / VXGI | RTGI | 极高 |
| 环境光遮蔽 | SSAO / GTAO | RTAO | 中等 |

UE5 的 Lumen 技术使用软件光线追踪（在计算着色器中遍历 Signed Distance Field）作为硬件光线追踪的替代，在保持较高质量的同时降低对 RTX 硬件的依赖。

---

## 5. GPU Driven Rendering

### 间接绘制（Indirect Draw）

Indirect Draw 允许 GPU 直接生成绘制调用的参数，无需 CPU 参与：

```cpp
// 1. 创建间接绘制缓冲（GPU 可写）
VkBufferCreateInfo bufferInfo{};
bufferInfo.size = MAX_DRAW_COMMANDS * sizeof(VkDrawIndexedIndirectCommand);
bufferInfo.usage = VK_BUFFER_USAGE_INDIRECT_BUFFER_BIT |
                   VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
vkCreateBuffer(device, &bufferInfo, nullptr, &indirectDrawBuffer);

// 2. 计算着色器写入间接绘制命令
layout(local_size_x = 256) in;
struct DrawCommand {
    uint indexCount; uint instanceCount;
    uint firstIndex; int vertexOffset; uint firstInstance;
};
layout(set = 0, binding = 1) buffer OutDrawCommands {
    DrawCommand commands[];
} outDraws;
layout(set = 0, binding = 2) buffer DrawCount { uint count; } drawCount;

void main() {
    uint idx = gl_GlobalInvocationID.x;
    if (idx >= inBounds.visibleIndices.length()) return;
    uint meshIndex = inBounds.visibleIndices[idx];
    DrawCommand cmd;
    cmd.indexCount = meshParams.indexCounts[meshIndex];
    cmd.instanceCount = 1;
    cmd.firstIndex = meshParams.firstIndices[meshIndex];
    cmd.vertexOffset = meshParams.vertexOffsets[meshIndex];
    cmd.firstInstance = meshIndex;
    uint slot = atomicAdd(drawCount.count, 1);
    outDraws.commands[slot] = cmd;
}

// 3. CPU 端执行间接绘制
vkCmdDrawIndexedIndirectCount(cmd,
    indirectBuffer, 0, countBuffer, 0,
    MAX_DRAW_COMMANDS, sizeof(VkDrawIndexedIndirectCommand));
```

### 计算着色器视锥剔除

整个剔除流程在 GPU 上完成：
1. **视锥剔除**：根据相机视锥体剔除不可见物体
2. **遮挡剔除**：使用上一帧的深度缓冲判断物体是否被遮挡
3. **LOD 选择**：根据屏幕空间大小选择合适的 LOD 层级
4. **绘制命令生成**：将可见的 LOD 组合成间接绘制命令

### Mesh Shader 管线

Mesh Shader（Vulkan 1.3 / DirectX 12 Ultimate）是 GPU Driven Rendering 的终极形态，完全替代传统顶点着色器-曲面细分-几何着色器管线。

核心单位是 **Meshlet**——一组最多 64-256 个顶点的小三角形簇。Task Shader 在 Mesh Shader 之前执行，用于高级剔除和 LOD 选择。

| 特性 | 传统管线 | Mesh Shader |
|:-----|:---------|:------------|
| CPU Draw Calls | 每 Mesh 一次 | 每 Mesh Group 一次 |
| 顶点获取 | 固定功能 | 可编程 |
| LOD | CPU 决策 | GPU 决策 |
| 剔除 | CPU 或 Compute | Task Shader 内置 |

---

## 6. 虚拟纹理技术

虚拟纹理（Virtual Texturing）解决大规模场景中纹理内存不足的问题。核心思想类似于操作系统的虚拟内存——只有当前可见的纹理区域才加载到显存中。

### 虚拟纹理原理

纹理空间划分为固定大小的**瓦片（Tile / Page）**，通常为 128x128 或 256x256 像素。渲染时，片元着色器将 UV 坐标和 Mipmap 层级转换为虚拟纹理坐标，通过**页表（Page Table）**查找对应的物理纹理中的瓦片位置。

### GPU Feedback 机制

Feedback Pass 以较低分辨率执行，将每个像素需要的虚拟页 ID 输出到一张纹理中。CPU 读取这张纹理，收集需要加载的瓦片列表，然后异步加载缺失的瓦片。

### 纹理流送策略

| 策略 | 原理 | 优点 | 缺点 |
|:-----|:-----|:-----|:-----|
| 静态预加载 | 关卡加载时加载所有纹理 | 无运行时卡顿 | 内存占用大 |
| 按需加载 | Feedback 驱动，缺页时加载 | 内存效率高 | 可能出现 pop-in |
| 预测性加载 | 根据相机运动预加载前方纹理 | 减少 pop-in | 预测错误时浪费带宽 |
| 渐进加载 | 先加载低 Mipmap，逐步提升 | 快速显示 | 远处可能暂时模糊 |

现代引擎通常采用混合策略——预测性加载 + 优先级队列 + 渐进加载。例如，Unreal Engine 的 Texture Streaming 系统根据视野和相机运动方向预测即将需要的纹理，按优先级排序加载，并在纹理完全加载前使用低 Mipmap 层级的数据作为占位。

| 技术 | 典型用途 | 页大小 | 物理纹理大小 | 关键挑战 |
|:-----|:---------|:-------|:-------------|:---------|
| 传统虚拟纹理 | 大型地形纹理 | 128x128 | 4096x4096 | Pop-in、磁盘带宽 |
| 稀疏纹理（Sparse/Partially Resident） | 硬件支持 | 64x64 | 由 GPU 管理 | API 兼容性 |
| 运行时虚拟纹理（RVT） | 地形混合、贴花 | 256x256 | 动态分配 | 缓存一致性 |
| 纳米虚拟纹理（Nanite VSM） | UE5 虚拟阴影 | 128x128 | 动态分配 | 阴影质量与性能平衡 |

UE 的 Virtual Texture 系统支持 Runtime Virtual Texture（RVT）和 Sparse Volume Texture。

---

## 总结

本章涵盖了现代游戏引擎渲染系统的核心技术：

1. **PBR 完整实现**：掌握 Cook-Torrance BRDF 的 D/F/G 三要素和 IBL 的 Split Sum Approximation，是构建现代材质系统的基础
2. **屏幕空间效果**：SSAO/GTAO 提供高效的环境遮蔽，SSR 实现屏幕内反射，SSSSS 模拟次表面散射
3. **后处理管线**：Bloom、ACES 色调映射和 LUT 色彩分级构成了完整的图像调校流程
4. **实时光线追踪**：理解 BLAS/TLAS 加速结构和混合渲染管线，能在支持硬件上实现精确的光照效果
5. **GPU Driven Rendering**：通过 Indirect Draw 和 Mesh Shader 将渲染决策从 CPU 转移到 GPU，是海量几何渲染的关键
6. **虚拟纹理**：通过页表和 Feedback 机制实现纹理的按需流送，是开放世界游戏的标配技术

---

## 延伸阅读

- **《Physically Based Rendering, 3rd Edition》** — Matt Pharr 等 — PBR 理论和实践权威
- **《Real-Time Rendering, 4th Edition》** — Tomas Akenine-Moller 等 — 实时渲染圣经
- **GDC 2017: FrameGraph** — Yuriy O'Donnell — 现代渲染架构
- **Karls' Blog: Epic Games** — 关于 Split Sum Approximation 的原始论文
