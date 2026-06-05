---
title: "光照与材质系统"
updated: 2026-06-05
---

# 光照与材质系统

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 06-渲染管线基础, 07-着色器编程

---

## 目录

- [1. 概念讲解](#1-概念讲解)
  - [1.1 为什么需要光照系统？](#11-为什么需要光照系统)
  - [1.2 局部光照模型：Phong / Blinn-Phong](#12-局部光照模型phong--blinn-phong)
  - [1.3 光源类型](#13-光源类型)
  - [1.4 衰减与阴影基础](#14-衰减与阴影基础)
  - [1.5 纹理映射技术](#15-纹理映射技术)
  - [1.6 颜色科学与色彩空间](#16-颜色科学与色彩空间)
  - [1.7 抗锯齿技术](#17-抗锯齿技术)
  - [1.8 PBR：基于物理的渲染](#18-pbr基于物理的渲染)
  - [1.9 法线贴图与视差贴图](#19-法线贴图与视差贴图)
  - [1.10 材质系统架构设计](#110-材质系统架构设计)
  - [1.11 Gamma 校正与 HDR](#111-gamma-校正与-hdr)
  - [1.12 延迟渲染简介](#112-延迟渲染简介)
- [2. 代码示例](#2-代码示例)
- [3. 练习](#3-练习)
- [4. 扩展阅读](#4-扩展阅读)
- [常见陷阱](#常见陷阱)

---

## 1. 概念讲解

### 1.1 为什么需要光照系统？

在现实世界中，我们能看到物体是因为光线从光源发出，照射到物体表面后反射进入眼睛。没有光照，世界将是一片漆黑。游戏引擎中的光照系统正是模拟这一物理过程的计算框架。

早期的 3D 游戏（如 1993 年的《Doom》）使用预计算的光照贴图（Lightmap），光照信息在关卡设计阶段就烘焙到纹理中，运行时无法动态改变。这种方式虽然性能开销极低，但无法支持动态光源、移动物体和实时阴影。

现代游戏引擎需要支持：
- **动态光源**：手电筒、爆炸闪光、日夜循环
- **动态物体**：角色在场景中移动时的光照变化
- **实时阴影**：物体遮挡产生的动态阴影
- **全局光照**：光线在场景中的多次反弹（间接光照）

本章聚焦于**局部光照模型**——即只考虑光源直接照射到物体表面的光照计算。这是所有现代渲染管线的基石。

### 1.2 局部光照模型：Phong / Blinn-Phong

局部光照模型将表面的反射光分解为三个分量：

```
L = L_ambient + L_diffuse + L_specular
```

#### Ambient（环境光）

环境光模拟的是场景中经过多次随机反射后到达物体的间接光照。在局部光照模型中，这是一个简化的近似——假设环境光从所有方向均匀地照射到物体表面。

```
L_ambient = k_a * I_a
```

其中 `k_a` 是材质的环境光反射系数，`I_a` 是环境光强度。

#### Diffuse（漫反射）

漫反射模拟的是光线进入物体表面内部后，向各个方向均匀散射的现象。粗糙的表面（如混凝土、未上漆的木头）主要产生漫反射。

根据**Lambert 余弦定律**，漫反射光的强度与入射光线和表面法线的夹角余弦成正比：

```
L_diffuse = k_d * I * max(n · l, 0)
```

其中：
- `k_d`：材质的漫反射系数（即表面颜色/反照率）
- `I`：光源强度
- `n`：表面单位法向量
- `l`：指向光源的单位方向向量
- `max(n · l, 0)`：确保背面不受光照

#### Specular（高光反射）

高光反射模拟的是光线在光滑表面上的镜面反射。抛光金属、光滑塑料、水面等会产生明显的高光。

**Phong 模型**（1975 年由 Bui Tuong Phong 提出）使用反射向量 `r` 和观察向量 `v` 的夹角来计算高光：

```
r = reflect(-l, n) = 2(n · l)n - l
L_specular = k_s * I * max(r · v, 0)^shininess
```

其中 `shininess` 控制高光的锐利程度——值越大，高光越集中、越锐利。

**Blinn-Phong 模型**（1977 年由 Jim Blinn 提出）是对 Phong 的优化，使用**半角向量** `h` 代替反射向量：

```
h = (l + v) / ||l + v||
L_specular = k_s * I * max(n · h, 0)^shininess
```

Blinn-Phong 的优势：
1. 当光源和观察者在同一侧时，半角向量 `h` 比反射向量 `r` 计算更稳定
2. 在某些角度下，Blinn-Phong 的高光分布更符合物理直觉
3. 在 GLSL 中，`h` 的计算比 `reflect()` 更直接

> **现代引擎的选择**：虽然 Phong 和 Blinn-Phong 都是经验模型，但 Blinn-Phong 在现代 GPU 上性能略优，且是 OpenGL 固定功能管线的默认选择。不过，PBR 管线已完全取代了这两种模型。

### 1.3 光源类型

#### 方向光（Directional Light）

模拟无限远处的光源，如太阳。所有光线平行，没有位置概念，只有方向。

```
l = -normalize(light.direction)  // 指向光源的方向
```

特点：
- 无衰减（光线强度不随距离变化）
- 适合作为场景的主光源
- 阴影使用正交投影的 shadow map

#### 点光源（Point Light）

模拟从空间中某一点向所有方向均匀发射光线的光源，如灯泡、火把。

```
d = light.position - fragment_position
l = normalize(d)
distance = length(d)
```

特点：
- 有位置，无方向（向所有方向发射）
- 有衰减（光线强度随距离平方衰减）
- 阴影需要使用立方体贴图（Cube Map Shadow）

#### 聚光灯（Spot Light）

模拟有方向限制的光源，如手电筒、舞台灯。光线从一个点发出，限制在一个圆锥范围内。

```
d = light.position - fragment_position
l = normalize(d)
spotFactor = dot(-l, normalize(light.direction))
if spotFactor < cos(light.cutoff):
    intensity = 0
else:
    // 可选：平滑边缘
    intensity = smoothstep(cos(outerCutoff), cos(innerCutoff), spotFactor)
```

特点：
- 有位置、有方向、有角度范围
- 有衰减
- 可以配置内锥角和外锥角实现边缘柔化

#### 面光源（Area Light）

模拟有一定面积的光源，如窗户、荧光灯管、柔光箱。面光源产生的阴影有"软阴影"效果（阴影边缘渐变模糊）。

实时渲染中精确计算面光源极其昂贵。常用近似方法：
- **代表性点方法**：将面光源近似为多个点光源
- **LTC（Linearly Transformed Cosines）**：Unity 和 Unreal 使用的实时面光源技术
- **烘焙/预计算**：对静态面光源使用光照贴图

### 1.4 衰减与阴影基础

#### 衰减（Attenuation）

真实世界中，光强度随距离平方衰减（平方反比定律）：

```
I_attenuated = I / d^2
```

但在计算机图形中，纯平方衰减在近距离会趋向无穷大，在远距离衰减过快。因此使用修正的衰减函数：

```
att = 1.0 / (constant + linear * d + quadratic * d^2)
```

其中 `constant`、`linear`、`quadratic` 是可调参数。典型值：

| 范围 | Constant | Linear | Quadratic |
|------|----------|--------|-----------|
| 7    | 1.0      | 0.7    | 1.8       |
| 13   | 1.0      | 0.35   | 0.44      |
| 20   | 1.0      | 0.22   | 0.20      |
| 50   | 1.0      | 0.09   | 0.032     |
| 100  | 1.0      | 0.045  | 0.0075    |

> Unreal Engine 使用 `inverse square falloff` 配合 `light radius` 来实现物理正确的衰减，同时避免数值问题。

#### 阴影基础（Shadow Mapping）

Shadow Mapping 是最常用的实时阴影技术，由 Lance Williams 于 1978 年提出。核心思想是：从光源视角渲染场景深度，然后在正常渲染时比较当前片元的深度与光源视角下的深度。

**步骤：**

1. **Shadow Pass**：从光源视角渲染场景，将深度值写入深度贴图（Shadow Map / Depth Map）
2. **Render Pass**：在正常渲染时，将片元位置变换到光源的裁剪空间，采样 shadow map 比较深度

**关键问题与解决方案：**

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| Shadow Acne（阴影痤疮） | 深度比较时的精度问题 | 添加 bias（深度偏移） |
| Peter-Panning（阴影悬浮） | Bias 过大导致阴影与物体分离 | 使用 slope-scale bias 或 normal bias |
| 锯齿/硬边缘 | Shadow map 分辨率有限 | PCF（Percentage Closer Filtering）、CSM（Cascaded Shadow Maps） |
| 超出 shadow map 范围 | 片元在光源视锥外 | 设置 border color 为 1.0（无阴影） |

**PCF（Percentage Closer Filtering）**：

不是直接比较深度后返回 0 或 1，而是对 shadow map 进行多次采样，计算处于阴影中的比例：

```glsl
float shadow = 0.0;
vec2 texelSize = 1.0 / textureSize(shadowMap, 0);
for(int x = -1; x <= 1; ++x) {
    for(int y = -1; y <= 1; ++y) {
        float pcfDepth = texture(shadowMap, projCoords.xy + vec2(x, y) * texelSize).r;
        shadow += currentDepth - bias > pcfDepth ? 1.0 : 0.0;
    }
}
shadow /= 9.0;
```

#### 级联阴影贴图（CSM）

CSM（Cascaded Shadow Maps）解决大场景中 Shadow Map 分辨率不足的问题。它将相机视锥体沿深度方向划分为多个级联（Cascade），每个级联使用独立的 Shadow Map：

| 级联 | 覆盖范围 | Shadow Map 分辨率 | 每像素精度 |
|:-----|:---------|:-------------------|:-----------|
| Cascade 0 | 近处 (0.1-5m) | 2048x2048 | 约 2.4mm/texel |
| Cascade 1 | 中近处 (5-20m) | 2048x2048 | 约 7.3mm/texel |
| Cascade 2 | 中远处 (20-80m) | 1024x1024 | 约 58mm/texel |
| Cascade 3 | 远处 (80-500m) | 1024x1024 | 约 390mm/texel |

每个级联的 Shadow Map 只覆盖对应视锥体子集，因此近处物体获得高分辨率阴影，远处物体使用低分辨率。级联之间的过渡需要混合处理以避免硬切。级联的分割通常使用对数或指数分割方案，使各级的 texel 密度尽量均匀。

CSM 是现代引擎中方向光阴影的标准方案。

#### 软阴影（PCSS）

真实世界的阴影没有硬边缘——半影区（Penumbra）的存在使阴影从完全阴影过渡到完全光照。PCF（Percentage Closer Filtering）通过采样 Shadow Map 的邻域并平均比较结果来模拟软阴影，但产生固定宽度的软阴影，不能模拟光源大小导致的半影变化。

PCSS（Percentage Closer Soft Shadows）改进了 PCF，根据遮挡物与受影面的距离动态调整滤波核大小：

```
w_penumbra = (d_receiver - d_blocker) * w_light / d_blocker
```

其中 `d_blocker` 是遮挡物到光源的平均距离（通过 Shadow Map 采样估算），`d_receiver` 是受影面到光源的距离，`w_light` 是光源大小。这产生了物理上更可信的软阴影——靠近物体的阴影锐利，远离物体的阴影模糊。

#### VSM / EVSM

VSM（Variance Shadow Maps）是 Shadow Map 的预过滤方案。它不存储原始深度，而是存储深度值 z 和深度平方 z^2。通过切比雪夫不等式（Chebyshev's Inequality），可以计算阴影概率的上界：

```
P(z_fragment >= z) <= sigma^2 / (sigma^2 + (mu - z_fragment)^2)
```

其中 `mu = E[z]` 是期望深度，`sigma^2 = E[z^2] - E[z]^2` 是方差。由于 VSM 可以预先对 Shadow Map 进行高斯模糊，软阴影的计算只需要单次纹理采样，性能极佳。但 VSM 存在 Light Bleeding（漏光）问题——当多个遮挡物在深度方向上重叠时，方差计算导致非零的阴影概率。

EVSM（Exponential Variance Shadow Maps）通过指数 warp 减少 Light Bleeding：

```
z_warped = e^(c * z), z_warped^2 = e^(2c * z)
```

其中 c 是控制参数。EVSM 在保持 VSM 预过滤优势的同时，大幅减少了 Light Bleeding，是目前高质量的软阴影方案之一。

---

### 1.5 纹理映射技术

纹理映射（Texture Mapping）是将二维图像数据映射到三维几何表面的过程。它是增加表面视觉复杂度而不增加几何复杂度的核心技术。

#### UV 展开原理

UV 坐标是三维表面在二维纹理空间中的参数化表示。每个顶点关联一个二维坐标 `(u, v) ∈ [0, 1]^2`，光栅化阶段通过透视校正插值在三角形内部生成连续的 UV 坐标，用于从纹理图像中采样颜色。

UV 展开的质量直接影响纹理的拉伸和接缝可见性。对于复杂模型，通常需要专业美术使用 Maya、Blender、RizomUV 等工具进行手动或半自动 UV 展开。引擎开发中，程序化生成的几何（如地形、Impostor）需要算法自动生成 UV——例如球面投影、圆柱投影或基于参数化曲面的展开。

#### 纹理过滤

纹理过滤（Texture Filtering）解决当屏幕像素与纹理像素（Texel）的比例不为 1:1 时的采样问题。主要有以下几种过滤模式：

| 过滤模式 | 原理 | 质量 | 性能开销 | 适用场景 |
|:---------|:-----|:-----|:---------|:---------|
| 最近邻（Nearest） | 取最近 Texel 的颜色 | 最低，出现马赛克 | 极低 | 像素风格游戏、Debug |
| 双线性（Bilinear） | 在 2x2 Texel 邻域内线性插值 | 中等，轻微模糊 | 低 | 2D 游戏、简单 3D 场景 |
| 三线性（Trilinear） | Bilinear + Mipmap 层级间插值 | 较好，减少 Mipmap 跳变 | 中 | 一般 3D 场景 |
| 各向异性（Anisotropic） | 沿像素投影方向采样多个 Texel | 最高，斜视角清晰 | 较高（2x-16x） | 地形、地面纹理 |

各向异性过滤（Anisotropic Filtering, AF）解决了当表面法线接近垂直于观察方向时（如远处的地面），屏幕像素在纹理空间中投影为长而窄的椭圆的问题。标准双线性/三线性过滤假设纹理空间中的采样区域是正方形，而 AF 允许沿投影方向采样更多 Texel。AF 的质量由采样率表示（2x、4x、8x、16x），数字越大沿长轴采样越多。现代 GPU 在 16x AF 下的性能损失通常小于 10%，因此建议在高画质设置中默认启用。

#### Mipmap 生成原理与 LOD 选择

Mipmap 是一组预先计算的纹理图像金字塔，每一层分辨率是上一层的 `1/2 x 1/2`。Mipmap 的生成不仅是简单的下采样——使用盒式滤波器（Box Filter）会导致混叠（Aliasing），正确的做法是对每一层执行高质量的下采样滤波。

Mipmap 层级（LOD, Level of Detail）的选择基于屏幕像素在纹理空间中的覆盖范围。纹理坐标对屏幕坐标的偏导数 `du/dx`、`du/dy`、`dv/dx`、`dv/dy`（由 GPU 硬件计算）决定了纹理空间中的采样面积：

```
lambda = log2(max(sqrt((du/dx)^2 + (dv/dx)^2), sqrt((du/dy)^2 + (dv/dy)^2)) * w)
```

其中 `lambda` 是 Mipmap LOD 层级，`w` 是纹理宽度。GPU 根据 `lambda` 选择对应的 Mipmap 层级进行采样。启用三线性过滤时，还会对相邻两个层级进行插值。

#### 纹理环绕模式

当 UV 坐标超出 `[0, 1]` 范围时，环绕模式（Wrap Mode）定义了如何确定采样值：

- **Repeat（重复）**：小数部分取模，纹理平铺
- **Clamp（钳制）**：超出范围的部分取边界值，避免接缝
- **Mirror（镜像）**：纹理交替翻转平铺，减少平铺重复感
- **Border Color（边界颜色）**：超出范围的部分返回指定颜色

Repeat 模式是最常用的——它允许用一张小纹理覆盖大面积表面，但要求纹理设计为无缝平铺（Tileable）。Clamp 模式用于 UI 元素和不应平铺的纹理。Mirror 模式在某些特定场景（如水面反射）中使用。

---

### 1.6 颜色科学与色彩空间

图形学中"颜色"的处理比直觉复杂得多。从物理光照的线性叠加到显示设备的非线性响应，颜色科学贯穿渲染管线的始终。忽略这些细节会导致混合错误、光照不自然等视觉问题。

#### RGB 颜色模型与加色原理

RGB（Red, Green, Blue）模型基于三原色加色原理：通过不同比例的红、绿、蓝光叠加来产生各种颜色。在物理层面，颜色是光谱功率分布（Spectral Power Distribution, SPD）——不同波长光的强度分布。RGB 模型是对无限维 SPD 的三维近似，其基础是 CIE 1931 标准观察者色匹配函数。

计算机中的 RGB 值通常用归一化的浮点数 `[0, 1]` 或 8 位无符号整数 `[0, 255]` 表示。对于物理正确的光照计算，必须使用浮点表示——光照能量的线性叠加很容易超出 `[0, 1]` 范围。这也是 HDR（High Dynamic Range）渲染的基础。

#### 线性工作流与 Gamma 校正

显示设备（CRT、LCD、OLED）对输入信号的响应是非线性的。这个非线性响应大致符合幂函数关系，指数称为 Gamma（`gamma ≈ 2.2`）。如果直接将线性光照计算结果输出到显示器，暗部会显得过于明亮，整体画面发灰。

正确的颜色管线要求：所有光照计算（纹理混合、光照叠加、混合）在线性空间进行；最终结果输出到显示器前进行 Gamma 校正（Gamma Correction），即应用 `1/gamma` 的幂变换：

```
V_encoded = V_linear^(1/gamma)
V_linear = V_encoded^gamma
```

常见错误是直接在 Gamma 编码的颜色上进行光照计算。例如，将两张纹理相乘时，如果纹理存储的是 Gamma 编码值，乘法操作实际上执行的是：

```
(A^gamma * B^gamma) = (A * B)^gamma != (A * B)^(1/gamma)
```

结果不是正确的线性响应。正确的流程是：先将纹理从 sRGB 空间解码到线性空间，执行所有光照计算，最后对输出进行 Gamma 编码。

| 纹理类型 | 存储空间 | 是否需要 sRGB 解码 | 原因 |
|:---------|:---------|:-------------------|:-----|
| Albedo / Diffuse | sRGB | 是 | 表示反射率，物理量在线性空间 |
| Normal Map | 线性 | 否 | 法线向量本身就是线性量 |
| Roughness/Metallic | 线性 | 否 | PBR 参数是物理线性量 |
| Ambient Occlusion | 线性 | 否 | 遮蔽值是线性比例 |
| HDR Environment Map | 线性（浮点） | 否 | 存储线性辐射度 |
| Light Map | 线性（通常 HDR） | 否 | 预计算的光照结果是线性的 |
| UI / 照片纹理 | sRGB | 视用途而定 | 直接显示时需要保持 sRGB |

上述表格列出了常见纹理的存储空间选择。引擎的纹理导入管线应根据纹理用途自动设置正确的颜色空间——Albedo 纹理需要从 sRGB 解码，而 Roughness 和 Normal 纹理直接使用线性值。现代 Graphics API 提供了 sRGB 纹理格式（如 `GL_SRGB8_ALPHA8`、`VK_FORMAT_R8G8B8A8_SRGB`），硬件在采样时自动执行 sRGB 到线性的转换，简化了着色器代码。

#### sRGB 色域与宽色域

sRGB 是 1996 年由 HP 和 Microsoft 定义的标准色彩空间，定义了红、绿、蓝三原色的色度坐标和白点。其色域（Gamut）——即可表示的颜色范围——覆盖了人类视觉可见颜色的一部分。大多数显示器设计为覆盖 sRGB 色域。

高端显示器支持更宽的色域，如 DCI-P3（色域比 sRGB 大约 25%，尤其在红色和绿色区域）和 Rec.2020（超高清电视标准，色域极大）。现代引擎和操作系统（macOS、Windows 11、iOS、Android）开始支持广色域渲染，核心挑战是：引擎渲染管线的工作色域必须至少与目标显示色域一样宽，且需要正确的色域转换矩阵来将渲染结果映射到不同显示设备的色域。

#### HDR 与色调映射

HDR（High Dynamic Range）渲染允许光照计算的中间结果超出显示设备的 `[0, 1]` 亮度范围。物理世界的亮度动态范围极广：室内阴影约为 `1 cd/m^2`，阳光下的雪可达 `100000 cd/m^2`。HDR 渲染管线通过浮点帧缓冲（FP16 或 R11G11B10）保留这种高动态范围。

但显示器的亮度范围有限（SDR 显示器约 `100 cd/m^2`），因此需要色调映射（Tone Mapping）将 HDR 值压缩到显示范围。色调映射不仅是简单的截断或缩放——良好的色调映射应保留局部对比度，避免"过曝"或"欠曝"。经典的 Reinhard 色调映射公式为：

```
L_mapped = L_hdr / (1 + L_hdr)
```

这个公式将 `[0, infinity)` 映射到 `[0, 1)`，但暗部对比度损失较大。ACES（Academy Color Encoding System）色调映射曲线是当前业界标准，它在暗部保持对比度，在高光部分提供柔和的"肩膀"压缩，比 Reinhard 产生更自然的视觉效果。

---

### 1.7 抗锯齿技术

锯齿（Aliasing）是数字图像中由采样率不足引起的一种 artifacts——几何边缘呈现阶梯状，高频细节产生摩尔纹。抗锯齿（Anti-Aliasing, AA）技术的本质是提高有效采样率或通过后处理减少锯齿可见性。

#### 锯齿成因分析

锯齿的根源是采样定理（Nyquist-Shannon Sampling Theorem）：要从离散采样中完全重建连续信号，采样频率必须至少是信号最高频率的两倍。在渲染中，图像边缘（几何轮廓、纹理边界）对应信号中的高频分量，而像素网格的采样率往往不足以捕获这些高频信息，导致频谱混叠（Spectral Aliasing）——高频信号"伪装"成低频信号，表现为锯齿和闪烁。

#### SSAA 与 MSAA

| 技术 | 原理 | 质量 | 性能开销 | 内存开销 | 主要限制 | 适用场景 |
|:-----|:-----|:-----|:---------|:---------|:---------|:---------|
| SSAA | 整个场景以更高分辨率渲染，然后下采样 | 最高，全面抗锯齿 | 极高（4x = 4倍像素） | 极高 | 片元着色器全量执行 | 静态截图、极高画质预设 |
| MSAA | 仅在光栅化阶段多采样，片元着色器每像素执行一次 | 高，几何边缘平滑 | 中等（4x ≈ 1.5-2倍） | 较高 | 延迟渲染管线不兼容 | 前向渲染、传统 3D 游戏 |
| FXAA | 后处理边缘检测与模糊 | 低-中等，可能模糊纹理 | 极低 | 无额外 | 不能处理亚像素细节 | 性能敏感场景、手游 |
| SMAA | 改进的边缘检测，模式识别 | 中等，优于 FXAA | 低 | 无额外 | 仍可能误判边缘 | 平衡质量与性能的选择 |
| TAA | 利用时间累积，子像素抖动采样 | 很高，接近 MSAA 4x | 中等 | 需要历史缓冲 | 运动场景产生鬼影 | 现代 3A 游戏标配 |
| DLSS/FSR/XeSS | AI/时序上采样，内建抗锯齿 | 极高 | 较低（运行在网络） | 需要运动向量等 | 需要特定硬件支持 | 新一代游戏标准 |

**SSAA（Super Sample Anti-Aliasing，超采样抗锯齿）** 是最朴素的抗锯齿方法：将场景渲染到 N 倍分辨率的缓冲中，然后通过下采样滤波得到最终图像。例如 4x SSAA 渲染到 `2x` 宽、`2x` 高的分辨率。SSAA 提供了最佳的图像质量——几何边缘、着色器高频、纹理细节都能得到平滑。但其代价是片元着色器执行次数与分辨率成正比，4x SSAA 意味着片元着色器执行 4 倍，这对现代复杂片元着色器是不可接受的。

**MSAA（Multi-Sample Anti-Aliasing，多重采样抗锯齿）** 是对 SSAA 的关键优化。它认识到大多数锯齿出现在三角形边缘（coverage 变化处），而三角形内部的着色通常是低频的。因此 MSAA 在光栅化阶段对每个像素执行多个采样点（Coverage Sample），判断每个采样点被哪些三角形覆盖；但片元着色器只在三角形内部执行一次，执行结果被复制到该三角形覆盖的所有采样点。只有在三角形边缘（即一个像素被多个三角形覆盖时），才需要执行多次片元着色器。这种优化使得 4x MSAA 的性能开销通常在 1.5-2 倍之间，远低于 4x SSAA。

MSAA 的局限性在于：首先，它与延迟渲染管线天然不兼容——延迟渲染的 G-Buffer 生成阶段没有几何信息来执行多重采样；其次，MSAA 不能解决着色器内部的锯齿（如高光闪烁、Alpha Test 边缘）。这些限制推动了后处理抗锯齿和时间性抗锯齿的发展。

#### 后处理抗锯齿

**FXAA（Fast Approximate Anti-Aliasing）** 是纯后处理抗锯齿，不需要任何额外的几何或颜色缓冲。它通过对屏幕图像进行亮度边缘检测，找到高对比度边缘并进行局部模糊来减少锯齿。FXAA 的优点是性能开销极低（通常小于 1ms）、无额外内存需求、与任何渲染管线兼容。缺点是容易对非边缘区域（如纹理细节）产生不必要的模糊，且对子像素级别的锯齿无效。

**SMAA（Subpixel Morphological Anti-Aliasing）** 改进了 FXAA 的边缘检测算法，通过模式识别（Pattern Recognition）更精确地定位边缘，并使用局部对比度自适应的混合策略，减少了纹理模糊。SMAA 提供了接近 MSAA 的视觉质量，同时保持了后处理抗锯齿的兼容性和低内存开销。

#### 时间性抗锯齿（TAA）

TAA（Temporal Anti-Aliasing）是现代 3A 游戏中最主流的抗锯齿方案。它利用了时序维度的信息：每帧对投影矩阵施加一个子像素偏移（Jitter），使得相邻帧采样的是略微不同的子像素位置；然后通过帧间混合（通常使用指数移动平均）累积历史颜色：

```
C_current = alpha * C_new + (1 - alpha) * C_history
```

其中 `alpha` 通常取 `0.1` 左右，意味着历史颜色占主导，当前帧贡献较小。TAA 的核心优势在于：对于静态画面，N 帧的累积等效于 N 倍超采样的效果；对于动态画面，有效采样率仍然高于单帧。

TAA 的实现需要解决几个关键技术问题：首先是**重投影（Reprojection）**——需要根据场景运动和相机运动，将历史帧的像素坐标变换到当前帧坐标，以找到对应的累积位置。这需要每帧生成运动向量（Motion Vector，即场景在屏幕空间的速度场）。其次是**鬼影（Ghosting）**问题——当遮挡关系发生变化（如物体移动揭露新背景）时，累积的历史颜色可能来自被遮挡的物体，导致拖影。解决方案包括深度测试、邻域裁剪（Neighborhood Clipping）——将历史颜色限制在当前像素 3x3 邻域的颜色包围盒内，以及基于运动向量长度调整混合因子。

TAA 与超分辨率技术（DLSS、FSR 2.0、XeSS）结合使用已成为现代游戏的标准做法。这些技术本质上是在 TAA 的基础上增加了上采样步骤，以较低的内部渲染分辨率达到接近原生分辨率的视觉效果。

---

### 1.8 PBR：基于物理的渲染

PBR（Physically Based Rendering）是现代游戏引擎的标准光照模型。与 Phong/Blinn-Phong 等经验模型不同，PBR 基于物理光学原理，参数具有明确的物理意义，在不同光照条件下表现一致。

#### 核心物理原理

**渲染方程（The Rendering Equation）**：

```
L_o(p, ω_o) = L_e(p, ω_o) + ∫_Ω f_r(p, ω_i, ω_o) L_i(p, ω_i) (n · ω_i) dω_i
```

其中：
- `L_o(p, ω_o)`：从点 `p` 沿方向 `ω_o` 出射的辐射度
- `L_e(p, ω_o)`：点 `p` 自身发射的辐射度
- `f_r(p, ω_i, ω_o)`：**BRDF**（双向反射分布函数）
- `L_i(p, ω_i)`：从方向 `ω_i` 入射的辐射度
- `(n · ω_i)`：Lambert 余弦项
- `∫_Ω ... dω_i`：对半球面所有入射方向积分

#### 微表面模型（Microfacet Model）

微表面模型假设物体表面由无数微小的、理想镜面反射的平面（微表面）组成。从远处看，这些微表面的统计分布决定了表面的宏观反射特性。

**Cook-Torrance BRDF**：

```
f_r = k_d * f_lambert + k_s * f_cook-torrance

f_lambert = c / π

f_cook-torrance = D(h) * F(v, h) * G(l, v, h) / (4 * (n · l) * (n · v))
```

#### BRDF 基础与反射方程

BRDF（Bidirectional Reflectance Distribution Function，双向反射分布函数）是描述表面反射的通用数学框架。它定义了从入射方向 `ω_i` 到出射方向 `ω_o` 的光线反射比例：

```
f_r(ω_i, ω_o) = dL_o(ω_o) / (L_i(ω_i) * cos(theta_i) * dω_i)
```

BRDF 必须满足两个基本约束：**互换性（Reciprocity）** `f_r(ω_i, ω_o) = f_r(ω_o, ω_i)` 和 **能量守恒** `∫_Ω f_r(ω_i, ω_o) * cos(theta_o) * dω_o <= 1`。

基于 BRDF 的反射方程描述了表面某点在所有入射光照下的总出射辐射度：

```
L_o(p, ω_o) = ∫_Ω f_r(p, ω_i, ω_o) * L_i(p, ω_i) * cos(theta_i) * dω_i
```

这个积分方程是渲染的核心——所有光照计算本质上都是在求解或近似这个积分。实时渲染中的挑战在于，精确求解这个积分需要对半球上所有入射方向进行采样，计算量巨大。各种光照模型的本质就是对这一积分的不同近似策略。

其中三个核心函数：

##### D - 法线分布函数（Normal Distribution Function, NDF）

描述微表面法线的统计分布。表面越粗糙，微表面法线偏离宏观法线的程度越大。

**Trowbridge-Reitz GGX**（现代引擎标准选择）：

```
D_GGX(h) = α^2 / (π * ((n · h)^2 * (α^2 - 1) + 1)^2)
```

其中 `α = roughness^2`（Disney 的重新参数化，使 roughness 更线性）。

> Unreal Engine 4+ 和 Unity 的 HDRP 都使用 GGX 作为默认 NDF。

##### F - Fresnel 效应（菲涅尔效应）

描述反射率随观察角度变化的效应。当视线与表面法线夹角越大（掠射角），反射越强。

**Schlick 近似**（1994）：

```
F_Schlick(F0, cosθ) = F0 + (1 - F0) * (1 - cosθ)^5
```

其中：
- `F0`：垂直入射时的反射率（基础反射率）
- `cosθ = max(n · v, 0)` 或 `max(h · v, 0)`

对于电介质（非金属），`F0` 通常很小（0.02-0.05）。对于金属，`F0` 就是金属的颜色。

> Schlick 近似与精确的 Fresnel 方程相比，误差在可接受范围内，但计算成本大幅降低。

##### G - 几何遮蔽函数（Geometry Function）

描述微表面之间的自遮挡效应。粗糙表面有更多的微表面相互遮挡，减少了实际反射的光线。

**Smith GGX 几何函数**：

```
G(l, v, h) = G_sub(n · l) * G_sub(n · v)

G_sub(cosθ) = 2 * cosθ / (cosθ + sqrt(α^2 + (1 - α^2) * cosθ^2))
```

#### 能量守恒

PBR 的一个关键原则是能量守恒：出射光的总能量不能超过入射光的能量。

在 Cook-Torrance BRDF 中，这通过以下方式保证：

```
k_s = F  // 镜面反射比例由 Fresnel 决定
k_d = (1 - k_s) * (1 - metallic)  // 漫反射比例
```

注意：
- `metallic = 1` 时，`k_d = 0`，纯镜面反射（金属）
- `metallic = 0` 时，`k_d = 1 - k_s`，漫反射主导（非金属）

#### PBR 材质参数

现代 PBR 工作流使用以下参数：

| 参数 | 含义 | 范围 | 说明 |
|------|------|------|------|
| Albedo（Base Color） | 基础颜色 | RGB [0,1] | 非金属的漫反射颜色，金属的反射率 |
| Metallic | 金属度 | [0,1] | 0=非金属，1=金属 |
| Roughness | 粗糙度 | [0,1] | 0=完美镜面，1=完全粗糙 |
| AO（Ambient Occlusion） | 环境光遮蔽 | [0,1] | 模拟局部遮挡的间接光衰减 |
| Normal | 法线 | 切线空间向量 | 表面微观几何细节 |

> **Metal/Roughness 工作流** vs **Specular/Glossiness 工作流**：
> - Metal/Roughness 更直观，不易出错，是行业主流（Unreal、Unity、Godot 默认）
> - Specular/Glossiness 给艺术家更多控制，但容易创建物理不正确的材质

#### IBL 环境光照

Image-Based Lighting（IBL）使用环境贴图（Environment Map）模拟来自四面八方的间接光照。IBL 解决了反射方程中环境光照积分的实时计算问题——直接求解半球积分太慢，因此需要预计算。

IBL 分为漫反射和镜面反射两个分量：

**漫反射 IBL** 预计算辐照度贴图（Irradiance Map），对环境贴图在每个法线方向上的漫反射光照进行卷积：

```
diffuse(n) = (1/π) * ∫_Ω L_i(l) * (n · l) * dω_l
```

这个卷积可以在离线阶段完成，将结果存储为立方体贴图（Cubemap）。运行时只需根据法线方向采样即可。

**镜面反射 IBL** 更为复杂，因为镜面反射依赖于粗糙度（越粗糙的表面对环境反射越模糊）。Split Sum Approximation（由 Karis 在 2013 年提出）将镜面积分分解为两部分：

```
∫_Ω L_i(l) * f_r(l, v) * (n · l) * dω_l ≈ Prefiltered Map * BRDF LUT
```

- **Prefiltered Map**：在离线阶段使用重要性采样（Importance Sampling）生成——根据 GGX 分布的 PDF 采样环境贴图的不同方向，对不同的粗糙度层级存储不同程度的模糊结果。粗糙度从 0 到 1 映射到 Mipmap 的不同层级。
- **BRDF LUT**：是一个二维查找表（Look-Up Texture），输入为 `(n · v, Roughness)`，输出为 `(Scale, Bias)`，用于快速计算菲涅尔项的积分效果。

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

**PBR 材质参数表（含真实材质参考）**

| 材质 | Metallic | Roughness | Albedo | 说明 |
|:-----|:---------|:----------|:-------|:-----|
| 木材 | 0.0 | 0.3-0.8 | 棕色 | 非金属，漫反射材质 |
| 石头 | 0.0 | 0.6-1.0 | 灰色 | 非金属，高粗糙度 |
| 塑料 | 0.0 | 0.1-0.3 | 彩色 | 非金属，较光滑 |
| 铁 | 1.0 | 0.2-0.6 | 浅灰色 | 金属，F0 由 Albedo 决定 |
| 金 | 1.0 | 0.1-0.3 | 金黄色 | 金属，有色 F0 |
| 铜 | 1.0 | 0.1-0.4 | 橙红色 | 金属，有色 F0 |
| 水/玻璃 | 0.0 | 0.0-0.1 | 白色/无色 | 非金属，极低粗糙度 |
| 生锈金属 | 1.0 | 0.5-1.0 | 红褐色 | 金属，高粗糙度 |

### 1.9 法线贴图与视差贴图

#### 法线贴图（Normal Mapping）

法线贴图是一种用纹理存储表面法线方向的技术，可以在不增加几何复杂度的前提下，呈现丰富的表面细节（如凹凸、划痕、砖缝等）。

**切线空间（Tangent Space）**：

法线贴图通常存储在切线空间中——以每个顶点自身的表面为参考坐标系：
- **T（Tangent）**：沿 U 纹理坐标方向
- **B（Bitangent/Binormal）**：沿 V 纹理坐标方向
- **N（Normal）**：表面法线方向

这三个向量构成 TBN 矩阵，用于将切线空间的法线变换到世界空间：

```
N_world = TBN * N_tangent
        = T * N_tangent.x + B * N_tangent.y + N * N_tangent.z
```

切线空间法线贴图的优势：
1. **可复用**：同一法线贴图可用于不同朝向的表面
2. **可动画**：角色动画时法线细节跟随变形
3. **可压缩**：切线空间法线主要朝 Z+ 方向，适合压缩

法线贴图纹理通常存储为：
```
N_tangent = normalize(texture(normalMap, uv).rgb * 2.0 - 1.0)
```
（将 [0,1] 范围映射到 [-1,1]）

#### 视差贴图（Parallax Mapping）

法线贴图只改变光照计算中的法线方向，不改变实际几何。当观察角度较倾斜时，这种"欺骗"会暴露——表面看起来是平的。

视差贴图通过根据视角偏移纹理坐标来模拟表面的实际凹凸，解决了这个问题。

**Steep Parallax Mapping**（陡峭视差贴图）：

将视线向量分层，逐层采样高度图，找到视线与表面的实际交点：

```
layerDepth = 1.0 / numLayers
currentLayerDepth = 0.0
currentTexCoords = uv
viewDir = normalize(tangentViewPos - tangentFragPos)

deltaTexCoords = (viewDir.xy / viewDir.z) * heightScale / numLayers

while currentLayerDepth < currentDepth:
    currentTexCoords -= deltaTexCoords
    currentDepth = texture(heightMap, currentTexCoords).r
    currentLayerDepth += layerDepth
```

**Parallax Occlusion Mapping (POM)**：

在 Steep Parallax Mapping 基础上，对最后两个采样点进行线性插值，获得更精确的结果：

```
// 找到交点前后的两个层
afterDepth  = currentDepth - currentLayerDepth
beforeDepth = texture(heightMap, currentTexCoords + deltaTexCoords).r
              - currentLayerDepth + layerDepth

weight = afterDepth / (afterDepth - beforeDepth)
finalTexCoords = currentTexCoords + deltaTexCoords * weight
```

### 1.10 材质系统架构设计

现代游戏引擎的材质系统需要支持：
- 多种着色模型（Unlit、Lit、Hair、Skin、Cloth 等）
- 参数化材质实例（继承基础材质，覆盖参数）
- 材质图层（Layer blending，如泥土+草地+岩石混合）
- 运行时切换和动态参数更新

#### 典型的材质系统架构

```
Material Asset
├── Shader Graph / Material Definition
│   ├── 着色模型选择
│   ├── 输入参数定义（标量、向量、纹理）
│   └── 节点图 / 代码
├── Material Instance
│   ├── 父材质引用
│   └── 参数覆盖
└── Runtime Material
    ├── GPU Shader Program
    ├── Uniform Buffer / 常量缓存
    └── Texture Bindings
```

**Unreal Engine 的材质系统**：
- `UMaterial`：材质定义，包含完整的节点图
- `UMaterialInstance`：材质实例，可覆盖参数但不能修改图结构
- `UMaterialInstanceDynamic`：动态材质实例，运行时创建和修改
- 材质编译时根据节点图生成 HLSL 代码，再编译为着色器

**Unity 的材质系统**：
- `Material` 资产引用 `Shader`
- Shader 使用 ShaderLab + HLSL/CG 编写
- Shader Graph 提供可视化编辑
- SRP（Scriptable Render Pipeline）允许自定义渲染管线

**自研引擎的设计建议**：

```cpp
// 材质定义（资产）
struct MaterialDefinition {
    std::string name;
    ShaderProgramHandle shader;
    std::vector<MaterialParameter> parameters;
    std::vector<TextureBinding> textures;
    BlendMode blendMode;
    CullMode cullMode;
    DepthTestMode depthTest;
};

// 运行时材质实例
class MaterialInstance {
public:
    void SetFloat(const std::string& name, float value);
    void SetVector3(const std::string& name, const Vec3& value);
    void SetTexture(const std::string& name, TextureHandle texture);
    void Bind(CommandBuffer& cmd);  // 绑定到 GPU

private:
    MaterialDefinition* m_definition;
    std::unordered_map<std::string, MaterialParameterValue> m_overrides;
    UniformBufferHandle m_uniformBuffer;
};

// 材质系统
class MaterialSystem {
public:
    MaterialInstance* CreateInstance(MaterialDefinition* def);
    void CompileMaterial(MaterialDefinition* def);  // 生成着色器
    void UpdateGlobalUniforms(const SceneLighting& lighting);
};
```

### 1.11 Gamma 校正与 HDR

#### Gamma 校正

显示器的响应曲线是非线性的——输入电压与输出亮度呈幂函数关系：

```
L_display = L_linear^gamma
```

其中 `gamma ≈ 2.2`。

这意味着：
- 如果不进行 Gamma 校正，线性计算的颜色值直接输出到显示器会偏暗
- 纹理通常存储在 sRGB 空间（已应用 gamma 2.2），采样时需要转换到线性空间
- 最终输出前需要将线性颜色转换回 sRGB 空间

**正确的工作流**：

```
纹理采样 → sRGB to Linear → 光照计算（线性空间） → Tone Mapping → Linear to sRGB → 输出
```

在 OpenGL 中：
```cpp
// 创建纹理时标记为 sRGB
glTexImage2D(GL_TEXTURE_2D, 0, GL_SRGB8_ALPHA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, data);

// 或者在 shader 中手动转换
vec3 linearColor = pow(texture(albedoMap, uv).rgb, vec3(2.2));

// 输出前转换回 sRGB
vec3 srgbColor = pow(linearColor, vec3(1.0 / 2.2));
```

> **常见错误**：在线性空间进行光照计算但忘记 Gamma 校正，导致画面过暗；或者对已经是线性的数据（如法线贴图、粗糙度贴图）进行 Gamma 校正，导致错误。

#### HDR（High Dynamic Range）

现实世界的光照强度范围极大：
- 月光：约 0.001-0.003 lux
- 室内照明：约 100-500 lux
- 晴天室外：约 10,000-100,000 lux
- 直视太阳：约 1,000,000,000 lux

传统的 LDR（Low Dynamic Range）渲染使用 [0, 1] 范围存储颜色，无法表示这种巨大的动态范围。HDR 渲染使用浮点格式（如 RGBA16F、RGBA32F）存储中间结果，保留完整的亮度信息。

**Tone Mapping（色调映射）**：

将 HDR 的宽动态范围映射到显示器可显示的 [0, 1] 范围。

**Reinhard Tone Mapping**：

```
L_mapped = L_hdr / (1 + L_hdr)
```

简单但会过度压缩高亮区域，导致画面发灰。

**ACES Filmic Tone Mapping**（行业标准）：

Unreal Engine 4 引入后成为事实标准，更好地保留高亮细节和色彩饱和度：

```
// 简化版 ACES
float3 ACESFilm(float3 x) {
    float a = 2.51f;
    float b = 0.03f;
    float c = 2.43f;
    float d = 0.59f;
    float e = 0.14f;
    return saturate((x * (a * x + b)) / (x * (c * x + d) + e));
}
```

**Exposure（曝光）**：

Tone Mapping 前需要确定场景的"正确"曝光。常用方法：
- 手动曝光：艺术家设置固定曝光值
- 自动曝光（Eye Adaptation）：根据场景平均亮度动态调整

```
L_exposed = L_hdr * exposure

// 自动曝光：基于平均亮度的几何均值
exposure = keyValue / avgLuminance
```

### 1.12 延迟渲染简介

#### 前向渲染（Forward Rendering）的问题

传统的前向渲染对每个物体遍历所有光源进行着色：

```cpp
for each object:
    for each light affecting object:
        shade(object, light)
```

问题：
- 每个片元的光照计算复杂度 = O(numLights)
- 大量光源时性能急剧下降（overdraw 严重）
- 复杂的光照计算被重复执行，即使最终会被深度测试剔除

#### 延迟渲染（Deferred Rendering）

延迟渲染将几何信息和着色计算分离：

**G-Buffer Pass**：
将几何信息（位置、法线、颜色、材质参数）渲染到多个纹理：

```
G-Buffer Layout（典型）：
- RT0: RGB = Albedo, A = AO
- RT1: RGB = Normal (world space), A = unused
- RT2: R = Metallic, G = Roughness, B = Specular, A = Subsurface
- RT3: RGB = Emissive, A = unused
- Depth: 场景深度
```

**Lighting Pass**：
对每个光源，只计算光照贡献并累加到最终图像：

```cpp
for each light:
    for each pixel affected by light:
        // 从 G-Buffer 读取材质数据
        material = readGBuffer(pixel)
        // 计算光照
        color += shade(material, light)
```

优势：
- 光照复杂度与场景几何复杂度解耦
- 每个片元只着色一次（假设无 overdraw）
- 天然支持大量光源

劣势：
- 高带宽（G-Buffer 读写）
- 不支持透明物体（需要单独的前向渲染 pass）
- 抗锯齿更复杂（MSAA 不直接适用）
- 难以支持复杂材质模型（每个材质需要统一的 G-Buffer 布局）

#### 现代变体

**Tile-Based Deferred Rendering (TBDR)**：
将屏幕划分为 tiles（如 16x16），先计算每个 tile 受哪些光源影响，只对这些光源进行着色。这是移动 GPU（PowerVR、Mali）和现代桌面 GPU 的标准做法。

**Clustered Deferred Rendering**：
在 TBDR 基础上，将视锥体在深度方向上也划分为 clusters（3D 网格），进一步减少每个片元需要考虑的光源数量。

> Unreal Engine 4 默认使用 Deferred Rendering，UE5 的 Lumen 全局光照系统也基于延迟渲染管线。Unity 的 URP 支持前向和延迟两种模式，HDRP 默认延迟。

---

## 2. 代码示例

本节提供一个完整的 OpenGL + GLSL 示例，实现：
- Blinn-Phong 光照（方向光 + 点光源）
- 法线贴图
- Gamma 校正
- 多光源支持（可扩展）

### 2.1 C++ 主程序

```cpp
// main.cpp
// 编译: g++ -std=c++17 main.cpp -o lighting_demo -lglfw -lGL -lGLEW -lm

#include <glad/glad.h>
#include <GLFW/glfw3.h>
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>
#include <iostream>
#include <vector>
#include <cmath>

// ------------------------------------------------------------------
// Shader 类（简化版）
// ------------------------------------------------------------------
class Shader {
public:
    unsigned int ID;

    Shader(const char* vertexSource, const char* fragmentSource) {
        unsigned int vertex = glCreateShader(GL_VERTEX_SHADER);
        glShaderSource(vertex, 1, &vertexSource, nullptr);
        glCompileShader(vertex);
        checkCompileErrors(vertex, "VERTEX");

        unsigned int fragment = glCreateShader(GL_FRAGMENT_SHADER);
        glShaderSource(fragment, 1, &fragmentSource, nullptr);
        glCompileShader(fragment);
        checkCompileErrors(fragment, "FRAGMENT");

        ID = glCreateProgram();
        glAttachShader(ID, vertex);
        glAttachShader(ID, fragment);
        glLinkProgram(ID);
        checkCompileErrors(ID, "PROGRAM");

        glDeleteShader(vertex);
        glDeleteShader(fragment);
    }

    void use() { glUseProgram(ID); }
    void setBool(const std::string& name, bool value) const {
        glUniform1i(glGetUniformLocation(ID, name.c_str()), (int)value);
    }
    void setInt(const std::string& name, int value) const {
        glUniform1i(glGetUniformLocation(ID, name.c_str()), value);
    }
    void setFloat(const std::string& name, float value) const {
        glUniform1f(glGetUniformLocation(ID, name.c_str()), value);
    }
    void setVec3(const std::string& name, const glm::vec3& value) const {
        glUniform3fv(glGetUniformLocation(ID, name.c_str()), 1, &value[0]);
    }
    void setVec3(const std::string& name, float x, float y, float z) const {
        glUniform3f(glGetUniformLocation(ID, name.c_str()), x, y, z);
    }
    void setMat4(const std::string& name, const glm::mat4& mat) const {
        glUniformMatrix4fv(glGetUniformLocation(ID, name.c_str()), 1, GL_FALSE, &mat[0][0]);
    }

private:
    void checkCompileErrors(unsigned int shader, const std::string& type) {
        int success;
        char infoLog[1024];
        if (type != "PROGRAM") {
            glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
            if (!success) {
                glGetShaderInfoLog(shader, 1024, nullptr, infoLog);
                std::cerr << "Shader Compile Error (" << type << "): " << infoLog << std::endl;
            }
        } else {
            glGetProgramiv(shader, GL_LINK_STATUS, &success);
            if (!success) {
                glGetProgramInfoLog(shader, 1024, nullptr, infoLog);
                std::cerr << "Program Link Error: " << infoLog << std::endl;
            }
        }
    }
};

// ------------------------------------------------------------------
// 顶点数据：一个带切线/副切线的立方体
// ------------------------------------------------------------------
struct Vertex {
    glm::vec3 position;
    glm::vec3 normal;
    glm::vec2 texCoord;
    glm::vec3 tangent;
    glm::vec3 bitangent;
};

std::vector<Vertex> buildCube() {
    std::vector<Vertex> vertices;

    // 前面 (z = 1)
    glm::vec3 n = glm::vec3(0, 0, 1);
    glm::vec3 t = glm::vec3(1, 0, 0);
    glm::vec3 b = glm::vec3(0, 1, 0);
    vertices.push_back({{-0.5f, -0.5f,  0.5f}, n, {0.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f, -0.5f,  0.5f}, n, {1.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f,  0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f,  0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f,  0.5f}, n, {0.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f, -0.5f,  0.5f}, n, {0.0f, 0.0f}, t, b});

    // 后面 (z = -1)
    n = glm::vec3(0, 0, -1);
    t = glm::vec3(-1, 0, 0);
    b = glm::vec3(0, 1, 0);
    vertices.push_back({{ 0.5f, -0.5f, -0.5f}, n, {0.0f, 0.0f}, t, b});
    vertices.push_back({{-0.5f, -0.5f, -0.5f}, n, {1.0f, 0.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f, -0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f, -0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f, -0.5f}, n, {0.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f, -0.5f, -0.5f}, n, {0.0f, 0.0f}, t, b});

    // 左面 (x = -1)
    n = glm::vec3(-1, 0, 0);
    t = glm::vec3(0, 0, 1);
    b = glm::vec3(0, 1, 0);
    vertices.push_back({{-0.5f, -0.5f, -0.5f}, n, {0.0f, 0.0f}, t, b});
    vertices.push_back({{-0.5f, -0.5f,  0.5f}, n, {1.0f, 0.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f,  0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f,  0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f, -0.5f}, n, {0.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f, -0.5f, -0.5f}, n, {0.0f, 0.0f}, t, b});

    // 右面 (x = 1)
    n = glm::vec3(1, 0, 0);
    t = glm::vec3(0, 0, -1);
    b = glm::vec3(0, 1, 0);
    vertices.push_back({{ 0.5f, -0.5f,  0.5f}, n, {0.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f, -0.5f, -0.5f}, n, {1.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f, -0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f, -0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f,  0.5f}, n, {0.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f, -0.5f,  0.5f}, n, {0.0f, 0.0f}, t, b});

    // 上面 (y = 1)
    n = glm::vec3(0, 1, 0);
    t = glm::vec3(1, 0, 0);
    b = glm::vec3(0, 0, -1);
    vertices.push_back({{-0.5f,  0.5f,  0.5f}, n, {0.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f,  0.5f}, n, {1.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f, -0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f,  0.5f, -0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f, -0.5f}, n, {0.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f,  0.5f,  0.5f}, n, {0.0f, 0.0f}, t, b});

    // 下面 (y = -1)
    n = glm::vec3(0, -1, 0);
    t = glm::vec3(1, 0, 0);
    b = glm::vec3(0, 0, 1);
    vertices.push_back({{-0.5f, -0.5f, -0.5f}, n, {0.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f, -0.5f, -0.5f}, n, {1.0f, 0.0f}, t, b});
    vertices.push_back({{ 0.5f, -0.5f,  0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{ 0.5f, -0.5f,  0.5f}, n, {1.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f, -0.5f,  0.5f}, n, {0.0f, 1.0f}, t, b});
    vertices.push_back({{-0.5f, -0.5f, -0.5f}, n, {0.0f, 0.0f}, t, b});

    return vertices;
}

// ------------------------------------------------------------------
// 生成程序化纹理
// ------------------------------------------------------------------
unsigned int createProceduralTexture(int width, int height, bool isNormalMap = false) {
    unsigned int texture;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);

    std::vector<unsigned char> data(width * height * 4);

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            int idx = (y * width + x) * 4;
            if (isNormalMap) {
                // 简单的砖块法线贴图
                bool brick = ((x / 32) % 2 == 0) ^ ((y / 16) % 2 == 0);
                float nx = brick ? 0.5f + 0.3f * sin(x * 0.5f) : 0.5f;
                float ny = brick ? 0.5f + 0.3f * cos(y * 0.5f) : 0.5f;
                float nz = 0.8f;
                glm::vec3 n = glm::normalize(glm::vec3(nx - 0.5f, ny - 0.5f, nz));
                data[idx + 0] = static_cast<unsigned char>((n.x * 0.5f + 0.5f) * 255);
                data[idx + 1] = static_cast<unsigned char>((n.y * 0.5f + 0.5f) * 255);
                data[idx + 2] = static_cast<unsigned char>((n.z * 0.5f + 0.5f) * 255);
                data[idx + 3] = 255;
            } else {
                // 砖块颜色贴图
                bool brick = ((x / 32) % 2 == 0) ^ ((y / 16) % 2 == 0);
                if (brick) {
                    data[idx + 0] = 140; data[idx + 1] = 60;  data[idx + 2] = 40;  // 红褐色
                } else {
                    data[idx + 0] = 180; data[idx + 1] = 90;  data[idx + 2] = 60;  // 浅红褐色
                }
                data[idx + 3] = 255;
            }
        }
    }

    glTexImage2D(GL_TEXTURE_2D, 0, isNormalMap ? GL_RGBA8 : GL_SRGB8_ALPHA8,
                 width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, data.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glGenerateMipmap(GL_TEXTURE_2D);

    return texture;
}

// ------------------------------------------------------------------
// 全局变量
// ------------------------------------------------------------------
const unsigned int SCR_WIDTH = 1280;
const unsigned int SCR_HEIGHT = 720;

glm::vec3 cameraPos = glm::vec3(0.0f, 1.0f, 3.0f);
glm::vec3 cameraFront = glm::vec3(0.0f, 0.0f, -1.0f);
glm::vec3 cameraUp = glm::vec3(0.0f, 1.0f, 0.0f);

float yaw = -90.0f;
float pitch = 0.0f;
float lastX = SCR_WIDTH / 2.0f;
float lastY = SCR_HEIGHT / 2.0f;
bool firstMouse = true;

void framebuffer_size_callback(GLFWwindow* window, int width, int height) {
    glViewport(0, 0, width, height);
}

void mouse_callback(GLFWwindow* window, double xpos, double ypos) {
    if (firstMouse) {
        lastX = xpos;
        lastY = ypos;
        firstMouse = false;
    }
    float xoffset = xpos - lastX;
    float yoffset = lastY - ypos;
    lastX = xpos;
    lastY = ypos;

    float sensitivity = 0.1f;
    xoffset *= sensitivity;
    yoffset *= sensitivity;

    yaw += xoffset;
    pitch += yoffset;
    if (pitch > 89.0f) pitch = 89.0f;
    if (pitch < -89.0f) pitch = -89.0f;

    glm::vec3 front;
    front.x = cos(glm::radians(yaw)) * cos(glm::radians(pitch));
    front.y = sin(glm::radians(pitch));
    front.z = sin(glm::radians(yaw)) * cos(glm::radians(pitch));
    cameraFront = glm::normalize(front);
}

void processInput(GLFWwindow* window) {
    float speed = 2.5f;
    if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS)
        glfwSetWindowShouldClose(window, true);
    if (glfwGetKey(window, GLFW_KEY_W) == GLFW_PRESS)
        cameraPos += speed * cameraFront;
    if (glfwGetKey(window, GLFW_KEY_S) == GLFW_PRESS)
        cameraPos -= speed * cameraFront;
    if (glfwGetKey(window, GLFW_KEY_A) == GLFW_PRESS)
        cameraPos -= glm::normalize(glm::cross(cameraFront, cameraUp)) * speed;
    if (glfwGetKey(window, GLFW_KEY_D) == GLFW_PRESS)
        cameraPos += glm::normalize(glm::cross(cameraFront, cameraUp)) * speed;
}

// ------------------------------------------------------------------
// 顶点着色器
// ------------------------------------------------------------------
const char* vertexShaderSource = R"(
#version 330 core
layout (location = 0) in vec3 aPos;
layout (location = 1) in vec3 aNormal;
layout (location = 2) in vec2 aTexCoord;
layout (location = 3) in vec3 aTangent;
layout (location = 4) in vec3 aBitangent;

out VS_OUT {
    vec3 FragPos;
    vec2 TexCoord;
    vec3 TangentLightDir;
    vec3 TangentViewPos;
    vec3 TangentFragPos;
} vs_out;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;
uniform vec3 lightDir;      // 方向光方向（世界空间）
uniform vec3 viewPos;       // 相机位置（世界空间）

void main() {
    vs_out.FragPos = vec3(model * vec4(aPos, 1.0));
    vs_out.TexCoord = aTexCoord;

    // 构建 TBN 矩阵（世界空间 → 切线空间）
    mat3 normalMatrix = transpose(inverse(mat3(model)));
    vec3 T = normalize(normalMatrix * aTangent);
    vec3 N = normalize(normalMatrix * aNormal);
    T = normalize(T - dot(T, N) * N);  // Gram-Schmidt 正交化
    vec3 B = cross(N, T);
    mat3 TBN = transpose(mat3(T, B, N));  // 转置 = 逆矩阵（正交矩阵）

    // 将光照相关向量转换到切线空间
    vs_out.TangentLightDir = TBN * normalize(-lightDir);
    vs_out.TangentViewPos  = TBN * viewPos;
    vs_out.TangentFragPos  = TBN * vs_out.FragPos;

    gl_Position = projection * view * model * vec4(aPos, 1.0);
}
)";

// ------------------------------------------------------------------
// 片段着色器
// ------------------------------------------------------------------
const char* fragmentShaderSource = R"(
#version 330 core
out vec4 FragColor;

in VS_OUT {
    vec3 FragPos;
    vec2 TexCoord;
    vec3 TangentLightDir;
    vec3 TangentViewPos;
    vec3 TangentFragPos;
} fs_in;

// 材质参数
uniform sampler2D diffuseMap;
uniform sampler2D normalMap;
uniform vec3  materialAmbient;
uniform vec3  materialDiffuse;
uniform vec3  materialSpecular;
uniform float materialShininess;

// 方向光
uniform vec3  dirLightColor;
uniform float dirLightIntensity;

// 点光源（最多 4 个）
struct PointLight {
    vec3 position;
    vec3 color;
    float intensity;
    float constant;
    float linear;
    float quadratic;
};
uniform PointLight pointLights[4];
uniform int numPointLights;

// 开关
uniform bool useNormalMap;
uniform bool useGammaCorrection;

// 常量
const float GAMMA = 2.2;
const float INV_GAMMA = 1.0 / GAMMA;

// ------------------------------------------------------------------
// 从法线贴图获取法线（切线空间）
// ------------------------------------------------------------------
vec3 getNormalFromMap() {
    vec3 tangentNormal = texture(normalMap, fs_in.TexCoord).rgb * 2.0 - 1.0;
    return normalize(tangentNormal);
}

// ------------------------------------------------------------------
// Blinn-Phong 光照计算
// ------------------------------------------------------------------
vec3 blinnPhong(vec3 lightDir, vec3 viewDir, vec3 normal,
                vec3 lightColor, float lightIntensity,
                vec3 albedo) {
    vec3 L = normalize(lightDir);
    vec3 V = normalize(viewDir);
    vec3 N = normalize(normal);
    vec3 H = normalize(L + V);  // 半角向量

    // Ambient
    vec3 ambient = materialAmbient * lightColor * 0.1;

    // Diffuse
    float NdotL = max(dot(N, L), 0.0);
    vec3 diffuse = materialDiffuse * albedo * lightColor * NdotL;

    // Specular (Blinn-Phong)
    float NdotH = max(dot(N, H), 0.0);
    vec3 specular = materialSpecular * lightColor * pow(NdotH, materialShininess);

    return (ambient + diffuse + specular) * lightIntensity;
}

// ------------------------------------------------------------------
// 点光源衰减
// ------------------------------------------------------------------
float calcAttenuation(float distance, float constant, float linear, float quadratic) {
    return 1.0 / (constant + linear * distance + quadratic * distance * distance);
}

// ------------------------------------------------------------------
// sRGB / Linear 转换
// ------------------------------------------------------------------
vec3 srgbToLinear(vec3 srgb) {
    return pow(srgb, vec3(GAMMA));
}

vec3 linearToSrgb(vec3 linear) {
    return pow(linear, vec3(INV_GAMMA));
}

void main() {
    // 采样漫反射贴图
    vec3 albedo = texture(diffuseMap, fs_in.TexCoord).rgb;
    if (useGammaCorrection) {
        albedo = srgbToLinear(albedo);
    }

    // 获取法线
    vec3 normal;
    if (useNormalMap) {
        normal = getNormalFromMap();
    } else {
        normal = vec3(0.0, 0.0, 1.0);  // 切线空间的默认法线
    }

    vec3 viewDir = fs_in.TangentViewPos - fs_in.TangentFragPos;
    vec3 result = vec3(0.0);

    // ---- 方向光 ----
    result += blinnPhong(
        fs_in.TangentLightDir,
        viewDir,
        normal,
        dirLightColor,
        dirLightIntensity,
        albedo
    );

    // ---- 点光源 ----
    for (int i = 0; i < numPointLights; ++i) {
        // 将点光源位置转换到切线空间
        // 注意：这里简化处理，实际应在 VS 中传入切线空间的光源位置
        // 为简化代码，我们在世界空间计算点光源
        vec3 worldLightPos = pointLights[i].position;
        vec3 worldFragPos = fs_in.FragPos;
        vec3 worldNormal = normalize(vec3(0.0)); // 占位，实际应传入世界空间法线

        // 简化的世界空间点光源计算
        vec3 L = worldLightPos - worldFragPos;
        float dist = length(L);
        L = normalize(L);

        vec3 worldViewDir = normalize(viewPos - worldFragPos);
        vec3 worldNormalFallback = normalize(cross(dFdx(worldFragPos), dFdy(worldFragPos)));

        vec3 H = normalize(L + worldViewDir);
        float NdotL = max(dot(worldNormalFallback, L), 0.0);
        float NdotH = max(dot(worldNormalFallback, H), 0.0);

        vec3 ambient = materialAmbient * pointLights[i].color * 0.1;
        vec3 diffuse = materialDiffuse * albedo * pointLights[i].color * NdotL;
        vec3 specular = materialSpecular * pointLights[i].color * pow(NdotH, materialShininess);

        float atten = calcAttenuation(dist, pointLights[i].constant,
                                       pointLights[i].linear,
                                       pointLights[i].quadratic);

        result += (ambient + diffuse + specular) * pointLights[i].intensity * atten;
    }

    // Gamma 校正输出
    if (useGammaCorrection) {
        result = linearToSrgb(result);
    }

    // HDR 截断（简单版本）
    result = result / (result + vec3(1.0));

    FragColor = vec4(result, 1.0);
}
)";

// ------------------------------------------------------------------
// Main
// ------------------------------------------------------------------
int main() {
    glfwInit();
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);

    GLFWwindow* window = glfwCreateWindow(SCR_WIDTH, SCR_HEIGHT,
                                          "Lighting & Materials Demo", nullptr, nullptr);
    if (!window) {
        std::cerr << "Failed to create GLFW window" << std::endl;
        glfwTerminate();
        return -1;
    }
    glfwMakeContextCurrent(window);
    glfwSetFramebufferSizeCallback(window, framebuffer_size_callback);
    glfwSetCursorPosCallback(window, mouse_callback);
    glfwSetInputMode(window, GLFW_CURSOR, GLFW_CURSOR_DISABLED);

    if (!gladLoadGLLoader((GLADloadproc)glfwGetProcAddress)) {
        std::cerr << "Failed to initialize GLAD" << std::endl;
        return -1;
    }

    glEnable(GL_DEPTH_TEST);

    // 创建着色器
    Shader shader(vertexShaderSource, fragmentShaderSource);

    // 创建 VAO/VBO
    std::vector<Vertex> vertices = buildCube();
    unsigned int VAO, VBO;
    glGenVertexArrays(1, &VAO);
    glGenBuffers(1, &VBO);

    glBindVertexArray(VAO);
    glBindBuffer(GL_ARRAY_BUFFER, VBO);
    glBufferData(GL_ARRAY_BUFFER, vertices.size() * sizeof(Vertex), vertices.data(), GL_STATIC_DRAW);

    // Position
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)0);
    // Normal
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, normal));
    // TexCoord
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, texCoord));
    // Tangent
    glEnableVertexAttribArray(3);
    glVertexAttribPointer(3, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, tangent));
    // Bitangent
    glEnableVertexAttribArray(4);
    glVertexAttribPointer(4, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, bitangent));

    // 创建纹理
    unsigned int diffuseMap = createProceduralTexture(512, 512, false);
    unsigned int normalMap = createProceduralTexture(512, 512, true);

    shader.use();
    shader.setInt("diffuseMap", 0);
    shader.setInt("normalMap", 1);

    // 材质参数
    shader.setVec3("materialAmbient",  0.1f, 0.1f, 0.1f);
    shader.setVec3("materialDiffuse",  1.0f, 1.0f, 1.0f);
    shader.setVec3("materialSpecular", 0.5f, 0.5f, 0.5f);
    shader.setFloat("materialShininess", 32.0f);

    // 方向光
    shader.setVec3("lightDir", -0.2f, -1.0f, -0.3f);
    shader.setVec3("dirLightColor", 1.0f, 0.95f, 0.8f);
    shader.setFloat("dirLightIntensity", 1.0f);

    // 点光源
    shader.setInt("numPointLights", 2);
    // 点光源 0：红色，左侧
    shader.setVec3("pointLights[0].position", -2.0f, 1.0f, 0.0f);
    shader.setVec3("pointLights[0].color", 1.0f, 0.3f, 0.3f);
    shader.setFloat("pointLights[0].intensity", 2.0f);
    shader.setFloat("pointLights[0].constant", 1.0f);
    shader.setFloat("pointLights[0].linear", 0.09f);
    shader.setFloat("pointLights[0].quadratic", 0.032f);
    // 点光源 1：蓝色，右侧
    shader.setVec3("pointLights[1].position", 2.0f, 1.0f, 0.0f);
    shader.setVec3("pointLights[1].color", 0.3f, 0.3f, 1.0f);
    shader.setFloat("pointLights[1].intensity", 2.0f);
    shader.setFloat("pointLights[1].constant", 1.0f);
    shader.setFloat("pointLights[1].linear", 0.09f);
    shader.setFloat("pointLights[1].quadratic", 0.032f);

    // 开关
    shader.setBool("useNormalMap", true);
    shader.setBool("useGammaCorrection", true);

    // 渲染循环
    while (!glfwWindowShouldClose(window)) {
        processInput(window);

        glClearColor(0.05f, 0.05f, 0.08f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        shader.use();

        // 更新相机 uniform
        shader.setVec3("viewPos", cameraPos);

        // 变换矩阵
        glm::mat4 model = glm::mat4(1.0f);
        model = glm::rotate(model, (float)glfwGetTime() * 0.5f, glm::vec3(0.0f, 1.0f, 0.0f));
        shader.setMat4("model", model);

        glm::mat4 view = glm::lookAt(cameraPos, cameraPos + cameraFront, cameraUp);
        shader.setMat4("view", view);

        glm::mat4 projection = glm::perspective(glm::radians(45.0f),
                                                (float)SCR_WIDTH / SCR_HEIGHT,
                                                0.1f, 100.0f);
        shader.setMat4("projection", projection);

        // 绑定纹理
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, diffuseMap);
        glActiveTexture(GL_TEXTURE1);
        glBindTexture(GL_TEXTURE_2D, normalMap);

        // 绘制
        glBindVertexArray(VAO);
        glDrawArrays(GL_TRIANGLES, 0, 36);

        // 绘制第二个立方体（地面）
        model = glm::mat4(1.0f);
        model = glm::translate(model, glm::vec3(0.0f, -1.5f, 0.0f));
        model = glm::scale(model, glm::vec3(5.0f, 0.2f, 5.0f));
        shader.setMat4("model", model);
        shader.setBool("useNormalMap", false);  // 地面不用法线贴图
        glDrawArrays(GL_TRIANGLES, 0, 36);
        shader.setBool("useNormalMap", true);

        glfwSwapBuffers(window);
        glfwPollEvents();
    }

    glDeleteVertexArrays(1, &VAO);
    glDeleteBuffers(1, &VBO);
    glfwTerminate();
    return 0;
}
```

### 2.2 PBR 片段着色器（进阶）

以下是一个完整的 PBR 片段着色器实现，可与上面的 C++ 框架配合使用：

```glsl
#version 330 core
out vec4 FragColor;

in vec3 WorldPos;
in vec3 Normal;
in vec2 TexCoord;

uniform vec3 camPos;

// PBR 材质纹理
uniform sampler2D albedoMap;
uniform sampler2D normalMap;
uniform sampler2D metallicMap;
uniform sampler2D roughnessMap;
uniform sampler2D aoMap;

// 光源
uniform vec3 lightPositions[4];
uniform vec3 lightColors[4];

const float PI = 3.14159265359;

// ------------------------------------------------------------------
// 从法线贴图获取世界空间法线
// ------------------------------------------------------------------
vec3 getNormalFromMap() {
    vec3 tangentNormal = texture(normalMap, TexCoord).xyz * 2.0 - 1.0;

    vec3 Q1  = dFdx(WorldPos);
    vec3 Q2  = dFdy(WorldPos);
    vec2 st1 = dFdx(TexCoord);
    vec2 st2 = dFdy(TexCoord);

    vec3 N   = normalize(Normal);
    vec3 T   = normalize(Q1 * st2.t - Q2 * st1.t);
    vec3 B   = -normalize(cross(N, T));
    mat3 TBN = mat3(T, B, N);

    return normalize(TBN * tangentNormal);
}

// ------------------------------------------------------------------
// Fresnel - Schlick 近似
// ------------------------------------------------------------------
vec3 fresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

// ------------------------------------------------------------------
// Normal Distribution Function - GGX (Trowbridge-Reitz)
// ------------------------------------------------------------------
float distributionGGX(vec3 N, vec3 H, float roughness) {
    float a      = roughness * roughness;
    float a2     = a * a;
    float NdotH  = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;

    float num   = a2;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom       = PI * denom * denom;

    return num / denom;
}

// ------------------------------------------------------------------
// Geometry Function - Smith's method with GGX
// ------------------------------------------------------------------
float geometrySchlickGGX(float NdotV, float roughness) {
    float r = (roughness + 1.0);
    float k = (r * r) / 8.0;

    float num   = NdotV;
    float denom = NdotV * (1.0 - k) + k;

    return num / denom;
}

float geometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    float ggx2  = geometrySchlickGGX(NdotV, roughness);
    float ggx1  = geometrySchlickGGX(NdotL, roughness);

    return ggx1 * ggx2;
}

// ------------------------------------------------------------------
// 主函数
// ------------------------------------------------------------------
void main() {
    vec3 albedo     = pow(texture(albedoMap, TexCoord).rgb, vec3(2.2));
    float metallic  = texture(metallicMap, TexCoord).r;
    float roughness = texture(roughnessMap, TexCoord).r;
    float ao        = texture(aoMap, TexCoord).r;

    vec3 N = getNormalFromMap();
    vec3 V = normalize(camPos - WorldPos);

    // F0: 非金属固定为 0.04，金属使用 albedo
    vec3 F0 = vec3(0.04);
    F0 = mix(F0, albedo, metallic);

    // 反射率方程
    vec3 Lo = vec3(0.0);
    for (int i = 0; i < 4; ++i) {
        vec3 L = normalize(lightPositions[i] - WorldPos);
        vec3 H = normalize(V + L);
        float distance    = length(lightPositions[i] - WorldPos);
        float attenuation = 1.0 / (distance * distance);
        vec3 radiance     = lightColors[i] * attenuation;

        // Cook-Torrance BRDF
        float NDF = distributionGGX(N, H, roughness);
        float G   = geometrySmith(N, V, L, roughness);
        vec3  F   = fresnelSchlick(max(dot(H, V), 0.0), F0);

        vec3 kS = F;
        vec3 kD = vec3(1.0) - kS;
        kD *= 1.0 - metallic;

        vec3 numerator    = NDF * G * F;
        float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
        vec3 specular     = numerator / denominator;

        float NdotL = max(dot(N, L), 0.0);
        Lo += (kD * albedo / PI + specular) * radiance * NdotL;
    }

    // 环境光（简化处理，实际应使用 IBL）
    vec3 ambient = vec3(0.03) * albedo * ao;
    vec3 color   = ambient + Lo;

    // HDR tone mapping
    color = color / (color + vec3(1.0));
    // Gamma correction
    color = pow(color, vec3(1.0 / 2.2));

    FragColor = vec4(color, 1.0);
}
```

**运行方式:**

1. 确保安装了 GLFW、GLAD 和 GLM
2. 编译：`g++ -std=c++17 main.cpp -o lighting_demo -lglfw -lGL -lGLEW -lm`
3. 运行：`./lighting_demo`
4. 使用 WASD 移动，鼠标控制视角

**预期输出:**

- 一个旋转的立方体，表面有砖块纹理
- 方向光产生主要照明（暖白色）
- 两个点光源（红色和蓝色）产生彩色照明和衰减
- 法线贴图使砖块表面有凹凸感
- 地面平面使用基础 Blinn-Phong（无法线贴图）
- 整体画面经过 Gamma 校正，色调自然

---

## 3. 练习

### 练习 1：实现聚光灯

在上面的代码基础上，添加聚光灯支持。

**要求：**
- 定义 `SpotLight` 结构体，包含位置、方向、切角、外切角、颜色、强度
- 在片段着色器中实现聚光灯计算，包括边缘柔化（`smoothstep`）
- 在场景中放置一个跟随相机的聚光灯，模拟手电筒效果

**提示：**
```glsl
float theta = dot(lightDir, normalize(-L));
float epsilon = innerCutoff - outerCutoff;
float intensity = clamp((theta - outerCutoff) / epsilon, 0.0, 1.0);
```

### 练习 2：实现 PCF 软阴影

为方向光添加 Shadow Mapping 和 PCF 滤波。

**要求：**
- 添加 Shadow Pass：从方向光视角渲染场景深度到 FBO
- 在主渲染中比较当前片元深度与 shadow map 深度
- 实现 3x3 PCF 滤波，产生软阴影边缘
- 处理 Shadow Acne（添加 bias）和 Peter-Panning（使用 normal bias 或 slope-scale bias）

**验证方式：** 将立方体放在地面和光源之间，观察地面上的阴影。阴影边缘应该有轻微的模糊，而不是锯齿状硬边。

### 练习 3（可选）：完整的 PBR 材质查看器

将 PBR 片段着色器集成到主程序中，创建一个可交互的 PBR 材质查看器。

**要求：**
- 加载真实的 PBR 纹理集（可从 [Poly Haven](https://polyhaven.com/) 免费下载）
- 实现材质参数实时调节（粗糙度、金属度滑块）
- 添加多个可切换的光源配置
- 实现简单的 IBL（Image-Based Lighting）：
  - 使用环境贴图（cubemap）作为间接光照
  - 对漫反射部分，使用 irradiance map（环境贴图卷积）
  - 对镜面反射部分，使用预过滤环境贴图 + BRDF LUT

**参考资源：**
- LearnOpenGL 的 PBR 章节：https://learnopengl.com/PBR/Theory
- Poly Haven 免费 PBR 材质：https://polyhaven.com/

---

## 4. 扩展阅读

### 经典论文

1. **Phong, B.T.** (1975). "Illumination for Computer Generated Pictures." *Communications of the ACM.*
   - Phong 光照模型的原始论文

2. **Blinn, J.F.** (1977). "Models of Light Reflection for Computer Synthesized Pictures." *SIGGRAPH.*
   - Blinn-Phong 模型的原始论文

3. **Cook, R.L. & Torrance, K.E.** (1982). "A Reflectance Model for Computer Graphics." *SIGGRAPH.*
   - Cook-Torrance BRDF 的奠基论文

4. **Schlick, C.** (1994). "An Inexpensive BRDF Model for Physically-based Rendering." *Computer Graphics Forum.*
   - Schlick Fresnel 近似

5. **Walter, B. et al.** (2007). "Microfacet Models for Refraction through Rough Surfaces." *EGSR.*
   - GGX 分布函数的深入分析

6. **Burley, B.** (2012). "Physically-based Shading at Disney." *SIGGRAPH Course Notes.*
   - Disney 的 Principled BRDF，现代 PBR 的工业标准

### 现代引擎实现

7. **Karis, B.** (2013). "Real Shading in Unreal Engine 4." *SIGGRAPH Course Notes.*
   - Unreal Engine 4 PBR 实现的权威参考
   - 包含 GGX、Schlick Fresnel、Smith 几何函数的完整推导
   - IBL 实现细节（split-sum approximation）

8. **Hoffman, N.** (2013). "Background: Physics and Math of Shading." *SIGGRAPH Course Notes.*
   - PBR 的物理和数学基础，非常清晰的讲解

9. **Lagarde, S. & de Rousiers, C.** (2014). "Moving Frostbite to PBR." *SIGGRAPH Course Notes.*
   - EA Frostbite 引擎（Battlefield 系列）的 PBR 迁移经验

### 在线资源

10. **LearnOpenGL - Lighting & PBR**
    - https://learnopengl.com/Lighting/Colors
    - https://learnopengl.com/PBR/Theory
    - 最友好的 OpenGL 光照教程，包含完整代码

11. **The Book of Shaders - Lighting**
    - https://thebookofshaders.com/13/
    - 交互式着色器教程

12. **Filament PBR 文档**
    - https://google.github.io/filament/Filament.html
    - Google 的移动端 PBR 引擎，文档极其详尽

13. **Knarkowicz, K.** (2016). "ACES Filmic Tone Mapping Curve."
    - 各种 Tone Mapping 函数的对比分析

---

## 常见陷阱

### 陷阱 1：Gamma 校正混乱

**问题**：在线性空间计算光照但输出到 sRGB 显示器时未做 Gamma 校正，导致画面过暗；或者对已经是线性的数据（法线、粗糙度、金属度）进行了 Gamma 校正。

**解决**：
- 颜色贴图（albedo/diffuse）通常存储在 sRGB 空间，采样后转线性：`pow(color, 2.2)`
- 数据贴图（normal、roughness、metallic、AO）存储在线性空间，不要 Gamma 校正
- 最终输出前转回 sRGB：`pow(color, 1.0/2.2)`
- 使用 OpenGL 的 `GL_SRGB8_ALPHA8` 纹理格式可自动处理转换

### 陷阱 2：法线贴图未归一化

**问题**：从法线贴图采样后未重新归一化，或者 TBN 矩阵中的向量未正交化，导致法线方向错误，光照计算异常。

**解决**：
- 采样后始终 `normalize()`：
  ```glsl
  vec3 normal = normalize(texture(normalMap, uv).rgb * 2.0 - 1.0);
  ```
- 在顶点着色器中对 TBN 向量做 Gram-Schmidt 正交化：
  ```glsl
  T = normalize(T - dot(T, N) * N);
  B = cross(N, T);
  ```

### 陷阱 3：忽略能量守恒

**问题**：在 PBR 中，`k_d + k_s > 1`，导致出射光能量超过入射光，画面过亮且物理不正确。

**解决**：
```glsl
vec3 kS = F;
vec3 kD = vec3(1.0) - kS;
kD *= 1.0 - metallic;  // 金属没有漫反射
// kD + kS <= 1 自动满足
```

### 陷阱 4：Shadow Acne 和 Peter-Panning

**问题**：Shadow map 精度有限，导致自阴影瑕疵（Shadow Acne）或阴影与物体分离（Peter-Panning）。

**解决**：
- 使用 slope-scale bias：`bias = max(0.05 * (1.0 - dot(normal, lightDir)), 0.005)`
- 或使用 normal bias：沿法线方向轻微偏移片元位置
- 对 cascaded shadow maps 使用不同的 bias 值

### 陷阱 5：PBR 参数范围错误

**问题**：roughness 或 metallic 超出 [0,1] 范围，或者 albedo 的亮度超出合理范围（非金属 > 0.03-0.24 sRGB）。

**解决**：
- 在着色器中用 `clamp()` 限制参数范围
- 在材质编辑器中限制输入范围
- 参考 Disney 的 PBR 参数指南：
  - 非金属的 albedo 亮度范围：0.03（煤）到 0.94（雪）
  - 金属的 albedo 就是反射颜色（如金：RGB(1.0, 0.78, 0.34)）

### 陷阱 6：切线空间计算错误

**问题**：TBN 矩阵构建错误，导致法线贴图应用后表面朝向错误。

**解决**：
- 确保 tangent 和 bitangent 的方向与 UV 坐标系一致
- 注意 UV 翻转（OpenGL 的 V 坐标与 DirectX 相反）
- 使用 `dFdx`/`dFdy` 在片段着色器中动态计算 TBN 时，确保模型有正确的 UV 展开

### 陷阱 7：HDR 值未做 Tone Mapping

**问题**：HDR 渲染后直接将高亮度值截断到 [0,1]，导致高光区域完全变白，失去细节。

**解决**：
- 始终使用 Tone Mapping 将 HDR 范围映射到 LDR
- ACES Filmic 是目前最推荐的选择
- 配合自动曝光或手动曝光控制整体亮度

### 陷阱 8：多光源性能问题

**问题**：前向渲染中每个片元遍历所有光源，光源数量增加时性能急剧下降。

**解决**：
- 使用 tile-based 或 clustered 渲染
- 限制影响每个物体的光源数量（如 Unity 的 "Important" 设置）
- 对远处/微弱的光源使用烘焙光照
- 考虑切换到延迟渲染管线
