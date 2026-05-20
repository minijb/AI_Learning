# 渲染管线基础：从顶点到像素

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 01-数学基础：线性代数与几何

---

## 1. 概念讲解

### 1.1 为什么需要渲染管线？

在计算机屏幕上显示一个 3D 场景，本质上是将三维世界中的几何数据转换成二维像素颜色的过程。这个过程极其复杂——涉及坐标变换、裁剪、光栅化、着色、深度判断、混合等数十个步骤。如果没有一个标准化的流程，每个开发者都需要从零实现这些步骤，不仅效率低下，而且不同硬件厂商的实现方式也会千差万别。

**渲染管线（Rendering Pipeline）** 就是这一整套从 3D 场景描述到 2D 像素输出的标准化流程。它定义了数据如何在 GPU 上流动、经过哪些处理阶段、每个阶段做什么。理解渲染管线是成为游戏引擎开发者的基石，因为引擎的核心工作之一就是高效地驱动这条管线。

现代 GPU 被设计为高度并行地执行渲染管线中的特定阶段，每秒可以处理数十亿个顶点和像素。这种并行性是 GPU 与 CPU 最本质的区别，也是实时渲染得以实现的关键。

### 1.2 实时渲染管线的完整流程

现代实时渲染管线通常分为四个主要阶段：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        实时渲染管线全景图                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  应用阶段    │ →  │  几何阶段    │ →  │  光栅化阶段  │ →  │  像素处理阶段 │  │
│  │ Application │    │  Geometry   │    │  Rasterizer │    │ Pixel Stage │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│        │                  │                  │                  │           │
│        ▼                  ▼                  ▼                  ▼           │
│   CPU 主导            GPU 顶点处理         GPU 图元处理        GPU 像素处理   │
│   场景管理            顶点着色器           三角形设置          片段着色器     │
│   剔除优化            图元装配             扫描转换            深度/模板测试   │
│   提交绘制命令         裁剪                属性插值            混合输出        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

下面详细拆解每个阶段。

---

#### 阶段一：应用阶段（Application Stage）

**执行者：CPU**

应用阶段完全在 CPU 上运行，是渲染管线的起点。这个阶段的主要任务包括：

1. **场景管理**：维护场景中所有对象的位置、旋转、缩放信息，构建场景图（Scene Graph）或空间加速结构（如 BVH、八叉树）。

2. **视锥体剔除（Frustum Culling）**：判断哪些物体在摄像机的视野范围内。完全在视野外的物体可以直接跳过，不提交给 GPU 处理。这是最重要的 CPU 端优化之一。

3. **遮挡剔除（Occlusion Culling）**：判断哪些物体被其他物体完全遮挡。被遮挡的物体即使在校锥体内也不需要渲染。

4. **LOD 选择**：根据物体距离摄像机的远近，选择合适细节层次（Level of Detail）的模型。

5. **准备渲染状态**：设置着色器程序、纹理、混合模式等渲染状态。

6. **提交绘制命令**：通过图形 API（OpenGL、Vulkan、DirectX 12）将绘制命令（Draw Call）提交给 GPU。

```
应用阶段流程：

场景数据准备
    │
    ├── 更新变换矩阵（Model Matrix）
    │       每个物体的位置、旋转、缩放 → 4x4 模型矩阵
    │
    ├── 视锥体剔除
    │       物体包围盒 vs 6 个裁剪平面 → 完全在外则剔除
    │
    ├── 遮挡剔除（可选，通常用 GPU 查询）
    │       前一帧深度缓冲 → 判断当前物体是否被遮挡
    │
    ├── LOD 选择
    │       距离摄像机远近 → 选择高/中/低模
    │
    └── 排序与批处理
            按材质/着色器排序 → 减少状态切换
            合并相同材质的物体 → 减少 Draw Call

    │
    ▼

提交绘制命令到 GPU
    │
    ├── glDrawArrays / glDrawElements (OpenGL)
    ├── vkCmdDraw / vkCmdDrawIndexed (Vulkan)
    └── DrawIndexedInstanced (DirectX 12)
```

**关键概念：Draw Call**

Draw Call 是 CPU 通知 GPU 开始渲染一批几何体的命令。每次 Draw Call 都有固定的 CPU 开销（设置渲染状态、验证参数等），因此减少 Draw Call 数量是性能优化的重要方向。现代引擎通过合批（Batching）、实例化渲染（Instancing）、GPU Driven Rendering 等技术来降低 Draw Call。

---

#### 阶段二：几何阶段（Geometry Stage）

**执行者：GPU**

几何阶段负责将顶点数据从模型空间转换到裁剪空间，并组装成图元（Primitive）。这是 GPU 并行处理的第一个阶段。

```
几何阶段详细流程：

顶点数据输入（Vertex Buffer）
    │
    ├── 顶点属性：位置 (x,y,z)、法线 (nx,ny,nz)、颜色 (r,g,b)、纹理坐标 (u,v)
    ├── 索引数据（可选）：定义顶点如何连接成三角形
    └── 实例数据（可选）：每个实例的变换矩阵、颜色等
    │
    ▼

顶点着色器（Vertex Shader）—— 可编程
    │
    ├── 输入：单个顶点的所有属性
    ├── 处理：
    │       1. 坐标变换：Model → World → View → Clip（MVP 矩阵）
    │       2. 法线变换：用逆转置矩阵变换法线到世界/观察空间
    │       3. 光照计算（可选，如 Gouraud 着色）
    │       4. 顶点动画（骨骼动画、顶点变形）
    │       5. 纹理坐标变换
    └── 输出：裁剪空间位置 (gl_Position / SV_Position) + 自定义 varyings
    │
    ▼

图元装配（Primitive Assembly）
    │
    ├── 根据绘制模式将顶点连接成图元：
    │       GL_POINTS：点
    │       GL_LINES / GL_LINE_STRIP / GL_LINE_LOOP：线
    │       GL_TRIANGLES / GL_TRIANGLE_STRIP / GL_TRIANGLE_FAN：三角形
    └── 输出：完整的图元（如三角形的三个顶点）
    │
    ▼

裁剪（Clipping）
    │
    ├── 目的：去除完全在视锥体外的图元，分割部分在内的图元
    ├── Sutherland-Hodgman 算法或 Liang-Barsky 算法
    ├── 在裁剪空间进行（w 分量还未除）
    └── 输出：裁剪后的图元，顶点数可能增加（如三角形被裁剪成四边形 → 分割为两个三角形）
    │
    ▼

透视除法（Perspective Division）
    │
    ├── 将裁剪空间坐标 (x, y, z, w) 转换为 NDC（归一化设备坐标）
    ├── x_ndc = x_clip / w, y_ndc = y_clip / w, z_ndc = z_clip / w
    └── NDC 范围：OpenGL [-1, 1]，DirectX [-1, 1]（x,y）/ [0, 1]（z）
    │
    ▼

视口变换（Viewport Transform）
    │
    ├── 将 NDC 映射到屏幕像素坐标
    ├── x_screen = (x_ndc + 1) * 0.5 * viewport_width + viewport_x
    ├── y_screen = (y_ndc + 1) * 0.5 * viewport_height + viewport_y
    └── z 值映射到深度缓冲范围 [0, 1] 或 [-1, 1]
```

**顶点着色器详解**

顶点着色器是 GPU 上执行的第一个可编程阶段。它的核心职责是坐标变换，但也承担了许多其他任务。

顶点着色器的执行模型是 **SIMD（单指令多数据）**：同一个着色器程序被同时执行在成千上万个顶点上，每个顶点独立处理，顶点之间不能共享数据（除非使用 uniform 缓冲区或纹理）。

```glsl
// 典型顶点着色器（GLSL）
#version 330 core

layout(location = 0) in vec3 aPos;      // 顶点位置
layout(location = 1) in vec3 aNormal;   // 顶点法线
layout(location = 2) in vec2 aTexCoord; // 纹理坐标
layout(location = 3) in vec3 aColor;    // 顶点颜色

uniform mat4 model;      // 模型矩阵
uniform mat4 view;       // 观察矩阵
uniform mat4 projection; // 投影矩阵
uniform mat3 normalMatrix; // 法线矩阵（model 的逆转置的上 3x3）

out vec3 vWorldPos;      // 世界空间位置（传给片段着色器）
out vec3 vNormal;        // 世界空间法线
out vec2 vTexCoord;      // 纹理坐标
out vec3 vColor;         // 顶点颜色

void main() {
    // 1. 计算世界空间位置
    vec4 worldPos = model * vec4(aPos, 1.0);
    vWorldPos = worldPos.xyz;

    // 2. 变换法线到世界空间
    vNormal = normalize(normalMatrix * aNormal);

    // 3. 传递纹理坐标和颜色
    vTexCoord = aTexCoord;
    vColor = aColor;

    // 4. 核心：MVP 变换到裁剪空间
    gl_Position = projection * view * worldPos;
}
```

---

#### 阶段三：光栅化阶段（Rasterization Stage）

**执行者：GPU 固定功能单元**

光栅化是将几何图元（通常是三角形）转换为像素片段（Fragment）的过程。这是从连续的几何世界到离散的像素世界的关键转换。

```
光栅化阶段详细流程：

三角形设置（Triangle Setup）
    │
    ├── 输入：屏幕空间的三个顶点坐标 (x, y, z)
    ├── 计算三角形边界框（bounding box）
    ├── 计算边方程（edge equations）用于判断像素是否在三角形内
    └── 准备插值参数
    │
    ▼

扫描转换（Scan Conversion）
    │
    ├── 遍历三角形边界框内的每个像素中心点
    ├── 使用重心坐标（Barycentric Coordinates）判断点是否在三角形内
    │
    │   对于三角形顶点 A, B, C 和像素点 P：
    │   P = αA + βB + γC，其中 α + β + γ = 1，α,β,γ ≥ 0
    │   若满足条件，则 P 在三角形内部
    │
    ├── 同时计算深度值（z 插值）
    └── 输出：一组片段（Fragment），每个片段对应一个可能被覆盖的像素
    │
    ▼

属性插值（Attribute Interpolation）
    │
    ├── 对每个片段，插值顶点属性：
    │       颜色：fragColor = α * colorA + β * colorB + γ * colorC
    │       纹理坐标：同理
    │       法线：同理（注意需要归一化）
    │       世界位置：同理
    │
    ├── 深度值插值（透视校正插值）
    │       简单线性插值在透视投影下是错误的！
    │       正确做法：对 1/z 进行线性插值，然后取倒数
    │       属性插值公式：attr = (α*attrA/zA + β*attrB/zB + γ*attrC/zC) / (α/zA + β/zB + γ/zC)
    │
    └── 输出：带有插值属性的片段
```

**为什么需要透视校正插值？**

在透视投影下，深度不是线性变化的。屏幕空间中的等距点在视图空间中并不等距。如果直接对属性做线性插值，纹理会出现扭曲（affine texture mapping 的问题）。

正确的透视校正插值基于一个关键观察：在投影平面上，1/z 是线性变化的。因此：

1. 先计算每个顶点的 1/z
2. 在屏幕空间对 1/z 和 attr/z 做线性插值
3. 最后用插值后的 attr/z 除以插值后的 1/z 得到正确的属性值

现代 GPU 在硬件中自动完成透视校正插值，开发者通常不需要手动处理。但理解这个原理对于调试纹理扭曲等问题至关重要。

**透视校正插值公式：**

```
a_correct = lerp(a0/w0, a1/w1) / lerp(1/w0, 1/w1)
```

其中 `lerp` 表示屏幕空间的双线性插值。所有现代 GPU 在硬件层面自动执行透视校正插值，开发者通常无需手动处理，但理解这一原理对调试 UV 扭曲等问题至关重要。

**光栅化的边缘函数法**

GPU 使用边缘函数法（Edge Function Method）判断像素是否在三角形内。对于由顶点 v0, v1, v2 定义的三角形，边缘函数定义为：

```
E_ij(p) = (v_j - v_i) x (p - v_i)
```

当且仅当 `E_01(p) >= 0`、`E_12(p) >= 0`、`E_20(p) >= 0`（对逆时针三角形）时，点 p 位于三角形内部。GPU 利用这种函数的线性特性，通过增量计算高效地遍历三角形覆盖的像素块。

**顶点缓冲布局与缓存效率**

顶点数据在 GPU 显存中的布局直接影响缓存效率。引擎应采用**交错布局（Interleaved Layout）**，即单个顶点所有属性连续存储，而非平面布局（Planar Layout，每种属性分别存储）。交错布局能更好地利用顶点缓存的局部性原理，因为相邻顶点的所有属性在内存中相邻，一次缓存行读取即可获得多个属性。

---

#### 阶段四：像素处理阶段（Pixel/Fragment Stage）

**执行者：GPU**

像素处理阶段对每个片段（Fragment）进行着色，并决定最终是否写入帧缓冲以及如何写入。这是视觉效果最丰富的阶段。

```
像素处理阶段详细流程：

片段着色器（Fragment Shader）—— 可编程
    │
    ├── 输入：插值后的顶点属性（位置、法线、颜色、纹理坐标等）
    ├── 处理：
    │       1. 纹理采样（Texture Sampling）
    │       2. 光照计算（Phong、Blinn-Phong、PBR 等）
    │       3. 法线贴图（Normal Mapping）
    │       4. 环境贴图（Environment Mapping）
    │       5. 各种特效计算
    └── 输出：颜色 (RGBA) + 深度（可选修改）
    │
    ▼

逐片段测试（Per-Fragment Tests）—— 固定功能
    │
    ├── 裁剪测试（Scissor Test）
    │       片段是否在指定的矩形区域内？否 → 丢弃
    │
    ├── 模板测试（Stencil Test）
    │       片段的模板值与模板缓冲中的值比较
    │       通过/失败可配置不同操作（保持、替换、递增等）
    │       用途：镜面反射区域标记、轮廓描边、阴影体积
    │
    ├── 深度测试（Depth Test）
    │       片段深度 vs 深度缓冲中的值
    │       比较函数：LESS、LEQUAL、GREATER、EQUAL 等
    │       用途：解决可见性问题（哪个物体在前面）
    │       注意：深度测试通常在片段着色器之后，但 Early-Z 优化可以提前
    │
    └── 所有测试通过后，片段进入混合阶段
    │
    ▼

混合（Blending）—— 可配置
    │
    ├── 将片段颜色与帧缓冲中已有颜色混合
    ├── 混合方程：FinalColor = SrcFactor * SrcColor op DstFactor * DstColor
    ├── 常用模式：
    │       不透明：关闭混合，直接覆盖
    │       半透明：SrcAlpha / OneMinusSrcAlpha
    │       加法混合：One / One（用于发光效果）
    │       乘法混合：DstColor / Zero（用于暗化）
    └── 输出：最终像素颜色
    │
    ▼

写入帧缓冲（Framebuffer Write）
    │
    ├── 颜色缓冲（Color Buffer）：存储 RGBA 颜色
    ├── 深度缓冲（Depth Buffer）：存储每个像素的深度值
    ├── 模板缓冲（Stencil Buffer）：存储模板值（通常 8 位）
    └── 这些缓冲合称为帧缓冲（Framebuffer）
```

**片段着色器详解**

片段着色器决定了每个像素最终的颜色。它是 GPU 上最灵活、最常用的可编程阶段。

```glsl
// 典型片段着色器（GLSL）—— 带 Blinn-Phong 光照
#version 330 core

in vec3 vWorldPos;
in vec3 vNormal;
in vec2 vTexCoord;
in vec3 vColor;

uniform vec3 uCameraPos;
uniform vec3 uLightPos;
uniform vec3 uLightColor;
uniform float uLightIntensity;
uniform sampler2D uTexture;
uniform bool uUseTexture;

out vec4 FragColor;

void main() {
    // 1. 基础颜色
    vec3 baseColor = uUseTexture ? texture(uTexture, vTexCoord).rgb : vColor;

    // 2. 法线归一化（插值后可能不再单位长度）
    vec3 N = normalize(vNormal);

    // 3. 光照方向
    vec3 L = normalize(uLightPos - vWorldPos);

    // 4. 观察方向
    vec3 V = normalize(uCameraPos - vWorldPos);

    // 5. 半角向量（Blinn-Phong）
    vec3 H = normalize(L + V);

    // 6. 漫反射
    float NdotL = max(dot(N, L), 0.0);
    vec3 diffuse = baseColor * uLightColor * NdotL * uLightIntensity;

    // 7. 镜面反射
    float NdotH = max(dot(N, H), 0.0);
    float specularPower = 32.0;
    vec3 specular = vec3(1.0) * uLightColor * pow(NdotH, specularPower) * uLightIntensity;

    // 8. 环境光
    vec3 ambient = baseColor * 0.1;

    // 9. 最终颜色
    vec3 finalColor = ambient + diffuse + specular;

    // 10. Gamma 校正（线性空间 → sRGB）
    finalColor = pow(finalColor, vec3(1.0 / 2.2));

    FragColor = vec4(finalColor, 1.0);
}
```

---

### 1.3 坐标空间变换详解（Model-View-Projection）

理解坐标空间变换是掌握渲染管线的关键。一个顶点从模型文件到屏幕，要经过多次坐标空间转换。

```
坐标空间变换链：

模型空间（Model/Local Space）
    │    对象的本地坐标系，原点在模型中心/脚底
    │    顶点数据在模型文件中存储的原始坐标
    │
    │    变换：Model Matrix（模型矩阵）
    │    包含：平移、旋转、缩放
    │    由引擎根据物体 Transform 组件构建
    ▼

世界空间（World Space）
    │    场景的全局坐标系，所有物体共享
    │    用于：物理模拟、碰撞检测、光照计算
    │
    │    变换：View Matrix（观察矩阵）
    │    将世界原点平移到摄像机位置，旋转使摄像机朝向 -Z
    │    等价于摄像机世界变换的逆矩阵
    ▼

观察空间（View/Camera/Eye Space）
    │    以摄像机为原点的坐标系
    │    +X 向右，+Y 向上，-Z 向前（OpenGL 右手系）
    │    用于：观察空间中的光照计算
    │
    │    变换：Projection Matrix（投影矩阵）
    │    正交或透视投影
    ▼

裁剪空间（Clip Space）
    │    经过投影变换后的 4D 齐次坐标 (x, y, z, w)
    │    视锥体被变换为单位立方体
    │    用于：裁剪判断（-w ≤ x,y,z ≤ w）
    │
    │    变换：Perspective Division（透视除法）
    ▼

NDC（Normalized Device Coordinates）
    │    3D 归一化坐标 (x/w, y/w, z/w)
    │    范围：OpenGL [-1, 1]³，DirectX [-1,1]xy / [0,1]z
    │
    │    变换：Viewport Transform（视口变换）
    ▼

屏幕空间（Screen Space）
    │    2D 像素坐标 (x, y) + 深度 z
    │    x ∈ [0, viewport_width]
    │    y ∈ [0, viewport_height]
    │    z ∈ [0, 1]（深度缓冲值）
    ▼

窗口像素（Window Pixel）
```

**模型矩阵（Model Matrix）**

模型矩阵将顶点从模型空间变换到世界空间。它通常由三个基本变换矩阵相乘得到：

```
Model = Translation * Rotation * Scale

// 缩放矩阵
Scale(sx, sy, sz) =
┌ sx  0   0   0 ┐
│ 0   sy  0   0 │
│ 0   0   sz  0 │
└ 0   0   0   1 ┘

// 绕 Y 轴旋转 θ 弧度
RotationY(θ) =
┌ cosθ   0   sinθ   0 ┐
│ 0      1   0      0 │
│ -sinθ  0   cosθ   0 │
└ 0      0   0      1 ┘

// 平移矩阵
Translation(tx, ty, tz) =
┌ 1   0   0   tx ┐
│ 0   1   0   ty │
│ 0   0   1   tz │
└ 0   0   0   1  ┘
```

注意：变换顺序很重要。通常先缩放、再旋转、最后平移（S-R-T）。在矩阵乘法中，这表示为 `M = T * R * S`，因为向量是右乘的：`v_world = M * v_local = T * R * S * v_local`。

**观察矩阵（View Matrix）**

观察矩阵将世界空间变换到观察空间（以摄像机为原点）。它本质上是摄像机世界变换的逆。

给定摄像机的：
- 位置 `eye`（世界空间）
- 观察方向 `center`（世界空间中看向的点）
- 上方向 `up`（世界空间中的上向量）

```
// 构建观察矩阵（LookAt）
forward = normalize(center - eye)    // 摄像机朝向（观察空间 -Z）
right = normalize(cross(forward, up)) // 观察空间 +X
up' = cross(right, forward)           // 观察空间 +Y

View =
┌ right.x   right.y   right.z   -dot(right, eye)   ┐
│ up'.x     up'.y     up'.z     -dot(up', eye)     │
│ -forward.x -forward.y -forward.z dot(forward, eye)│
└ 0         0         0         1                  ┘
```

**投影矩阵（Projection Matrix）**

投影矩阵有两种主要类型：正交投影和透视投影。

*透视投影矩阵（Perspective Projection）*

模拟人眼的透视效果——近大远小。由以下参数定义：
- `fov`：垂直视野角度（弧度）
- `aspect`：宽高比（width / height）
- `near`：近裁剪平面距离
- `far`：远裁剪平面距离

```
// OpenGL 风格透视投影矩阵
// 注意：near 和 far 必须为正数

tanHalfFov = tan(fov / 2)

P =
┌ 1/(aspect*tanHalfFov)   0              0                    0     ┐
│ 0                       1/tanHalfFov   0                    0     │
│ 0                       0              -(far+near)/(far-near)  -2*far*near/(far-near) │
│ 0                       0              -1                   0     ┘

// 变换后：gl_Position = P * vec4(viewPos, 1.0)
// 结果：x,y ∈ [-w, w], z ∈ [-w, w]（裁剪空间）
// 透视除法后：z_ndc ∈ [-1, 1]
// 注意：OpenGL 的 z_ndc 是 [-1, 1]，DirectX 是 [0, 1]
```

透视投影矩阵有一个重要的性质：它将 Z 值非线性地映射到深度缓冲。这意味着近处的深度精度高，远处的深度精度低。这被称为 **深度精度问题（Z-fighting）**，当 near 值设置得太小或 far/near 比值太大时，远处的物体会出现闪烁。

*正交投影矩阵（Orthographic Projection）*

没有透视变形，平行线保持平行。常用于 2D 游戏、UI 渲染、工程制图。

```
// 正交投影矩阵
// 由六个裁剪面定义：left, right, bottom, top, near, far

P =
┌ 2/(right-left)      0                0              -(right+left)/(right-left) ┐
│ 0                   2/(top-bottom)   0              -(top+bottom)/(top-bottom) │
│ 0                   0                -2/(far-near)  -(far+near)/(far-near)     │
└ 0                   0                0              1                          ┘
```

**法线矩阵（Normal Matrix）**

法线不能直接用模型矩阵变换！当模型矩阵包含非均匀缩放时，直接使用模型矩阵变换法线会导致法线不再垂直于表面。

正确的法线矩阵是模型矩阵的**逆转置矩阵（Inverse-Transpose）**的上 3x3 部分：

```
NormalMatrix = transpose(inverse(modelMatrix))

// 在着色器中：
// 如果模型矩阵只包含旋转和均匀缩放，可以用 model 矩阵的上 3x3
// 如果有非均匀缩放，必须用 normalMatrix
```

为什么？因为法线需要保持与切线平面垂直。设切线向量为 T，法线为 N，则 N·T = 0。变换后，我们需要 N'·T' = 0。如果 M 是模型矩阵，T' = M * T，那么 N' 应该满足 (N')^T * (M * T) = 0。这意味着 N' = (M^{-1})^T * N。

---

### 1.4 帧缓冲与双缓冲

**帧缓冲（Framebuffer）**

帧缓冲是 GPU 内存中的一块区域，存储了最终渲染结果。一个完整的帧缓冲包含：

- **颜色附件（Color Attachment）**：存储每个像素的颜色（RGBA），可以有多个（MRT - Multiple Render Targets）
- **深度附件（Depth Attachment）**：存储每个像素的深度值（通常 24 位或 32 位浮点）
- **模板附件（Stencil Attachment）**：存储每个像素的模板值（通常 8 位）

```
帧缓冲结构：

┌─────────────────────────────────────────┐
│           帧缓冲（Framebuffer）           │
├─────────────────────────────────────────┤
│  颜色缓冲 0（RGBA8/RGBA16F/RGBA32F）      │
│  ┌─────┬─────┬─────┬─────┐             │
│  │ R   │ G   │ B   │ A   │  per pixel   │
│  └─────┴─────┴─────┴─────┘             │
├─────────────────────────────────────────┤
│  深度缓冲（D24S8 / D32F）                │
│  ┌─────────────┬────────┐               │
│  │ 深度值(24bit)│ 模板(8bit)│ per pixel  │
│  └─────────────┴────────┘               │
├─────────────────────────────────────────┤
│  颜色缓冲 1~N（MRT 时）                  │
└─────────────────────────────────────────┘
```

**双缓冲（Double Buffering）**

显示器以固定刷新率（如 60Hz、144Hz）从帧缓冲读取像素数据。如果 GPU 正在写入的帧缓冲被显示器读取，会出现画面撕裂（Tearing）——上半部分是旧帧，下半部分是新帧。

双缓冲通过使用两个帧缓冲解决此问题：

```
双缓冲机制：

帧 N 渲染中              帧 N+1 渲染中
┌──────────┐            ┌──────────┐
│  后缓冲   │ ← GPU 写入  │  后缓冲   │ ← GPU 写入
│ (Back)   │            │ (Back)   │
├──────────┤            ├──────────┤
│  前缓冲   │ → 显示器读取 │  前缓冲   │ → 显示器读取
│ (Front)  │            │ (Front)  │
└──────────┘            └──────────┘

垂直同步（VSync）时交换：
- 等待显示器刷新信号（VBLANK）
- 交换前后缓冲指针（只需交换地址，不复制数据）
- 旧的前缓冲变为新的后缓冲，继续渲染下一帧
```

现代 GPU 还支持 **三重缓冲（Triple Buffering）**：使用三个缓冲，允许 GPU 在显示器读取前一帧的同时，提前开始渲染后一帧，减少等待 VSync 的空闲时间。

---

### 1.5 GPU 的并行执行模型

GPU 与 CPU 在架构上有本质区别。理解 GPU 的并行模型对于编写高效着色器和优化渲染性能至关重要。

**CPU vs GPU 架构对比**

```
CPU 架构（少量强大核心）：
┌─────────────────────────────────────────────────────────┐
│  Core 0              Core 1              Core 2  Core 3  │
│  ┌─────┐            ┌─────┐            ┌─────┐ ┌─────┐  │
│  │ ALU │            │ ALU │            │ ALU │ │ ALU │  │
│  │ ALU │            │ ALU │            │ ALU │ │ ALU │  │
│  │ FPU │            │ FPU │            │ FPU │ │ FPU │  │
│  │Cache│            │Cache│            │Cache│ │Cache│  │
│  │64KB │            │64KB │            │64KB │ │64KB │  │
│  └─────┘            └─────┘            └─────┘ └─────┘  │
│  复杂控制逻辑：分支预测、乱序执行、大容量缓存                │
│  优化目标：最小化单个线程的延迟                             │
└─────────────────────────────────────────────────────────┘

GPU 架构（大量简单核心）：
┌─────────────────────────────────────────────────────────┐
│  SM / CU 0          SM / CU 1          ...  SM / CU N   │
│  ┌─────────┐        ┌─────────┐              ┌────────┐ │
│  │Core Core│        │Core Core│              │Core ...│ │
│  │Core Core│        │Core Core│              │       │ │
│  │Core Core│        │Core Core│              │       │ │
│  │Core Core│        │Core Core│              │       │ │
│  │Core Core│        │Core Core│              │       │ │
│  │Core Core│        │Core Core│              │       │ │
│  │Core Core│        │Core Core│              │       │ │
│  │Core Core│        │Core Core│              │       │ │
│  │ 共享    │        │ 共享    │              │ 共享   │ │
│  │ 内存    │        │ 内存    │              │ 内存   │ │
│  └─────────┘        └─────────┘              └────────┘ │
│  每个 SM 有 64~128 个核心，数千个并发线程                  │
│  优化目标：最大化吞吐量（单位时间处理的数据量）              │
└─────────────────────────────────────────────────────────┘
```

**SIMT 执行模型（Single Instruction Multiple Threads）**

NVIDIA GPU 使用 SIMT 模型，AMD 使用类似的概念（Wavefront）。核心思想是：

- 一组线程（NVIDIA 叫 Warp，32 个线程；AMD 叫 Wavefront，64 个线程）**同时执行相同的指令**
- 每个线程有自己的寄存器状态和独立的数据
- 如果线程发生分支（if/else），Warp 需要**串行执行**两个分支路径，屏蔽不满足条件的线程

```
SIMT 执行示例：

Warp 中的 32 个线程同时执行：

if (x > 0) {
    // 路径 A
    result = sqrt(x);
} else {
    // 路径 B
    result = 0;
}

执行过程：
┌──────────────────────────────────────────────────────┐
│ 时钟周期 1-10：                                       │
│   线程 0-15（x > 0）：执行 sqrt(x)，线程 16-31 空闲    │
│                                                      │
│ 时钟周期 11-12：                                      │
│   线程 16-31（x ≤ 0）：执行 result = 0，线程 0-15 空闲 │
│                                                      │
│ 总时间 = 路径 A 时间 + 路径 B 时间                    │
│ （分支发散导致性能下降！）                              │
└──────────────────────────────────────────────────────┘
```

**关键启示**：
1. 避免着色器中的分支发散——尽量让相邻像素走相同代码路径
2. 纹理采样是延迟操作——Warp 中所有线程请求纹理后，GPU 会切换到其他 Warp 执行，隐藏内存延迟
3. 寄存器压力——使用过多寄存器会减少可同时驻留的 Warp 数量，降低延迟隐藏能力

**顶点处理并行**

顶点着色器以顶点为单位并行执行。每个顶点独立处理，数千个顶点同时被不同的 GPU 核心处理。顶点之间没有通信（除非使用特殊的着色器扩展）。

**片段处理并行**

片段着色器以像素/片段为单位并行执行。但有一个重要限制：**同一个图元的相邻片段可能被分配到不同的 Warp**，而来自不同图元的片段可能交错执行。GPU 使用 **Early-Z** 优化在片段着色器之前进行深度测试，避免为被遮挡的像素执行片段着色器。

---

### 1.6 OpenGL / Vulkan / DirectX 12 管线对比

现代图形 API 都实现了相同的底层渲染管线概念，但在抽象层次、控制粒度和使用复杂度上有显著差异。

```
┌─────────────────┬─────────────────┬─────────────────┐
│    OpenGL       │    Vulkan       │  DirectX 12     │
├─────────────────┼─────────────────┼─────────────────┤
│ 1992 年首次发布  │ 2016 年发布      │ 2015 年发布      │
│ 跨平台           │ 跨平台           │ Windows/Xbox    │
│ 高级抽象         │ 底层显式控制      │ 底层显式控制      │
├─────────────────┼─────────────────┼─────────────────┤
│ 驱动管理状态     │ 应用管理状态      │ 应用管理状态      │
│ 隐式资源管理     │ 显式资源管理      │ 显式资源管理      │
│ 全局状态机       │ 无全局状态       │ 无全局状态       │
├─────────────────┼─────────────────┼─────────────────┤
│ 单线程友好       │ 多线程设计       │ 多线程设计       │
│ 驱动开销大       │ 驱动开销极小     │ 驱动开销极小     │
│ CPU 瓶颈明显     │ CPU 扩展性好     │ CPU 扩展性好     │
├─────────────────┼─────────────────┼─────────────────┤
│ 易学易用         │ 学习曲线陡峭     │ 学习曲线陡峭     │
│ 适合入门/原型    │ 适合高性能引擎   │ 适合高性能引擎   │
│ 代码量少         │ 代码量 5-10 倍   │ 代码量 5-10 倍   │
└─────────────────┴─────────────────┴─────────────────┘
```

**OpenGL 管线概览**

```
OpenGL 渲染管线状态：

// 1. 创建和绑定着色器程序
GLuint shaderProgram = createShaderProgram(vertexSource, fragmentSource);
glUseProgram(shaderProgram);

// 2. 设置顶点数据
GLuint VAO, VBO, EBO;
glGenVertexArrays(1, &VAO);
glBindVertexArray(VAO);
glGenBuffers(1, &VBO);
glBindBuffer(GL_ARRAY_BUFFER, VBO);
glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);

// 3. 配置顶点属性指针
glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 8 * sizeof(float), (void*)0);
glEnableVertexAttribArray(0);

// 4. 设置 Uniform（MVP 矩阵等）
glUniformMatrix4fv(modelLoc, 1, GL_FALSE, glm::value_ptr(model));

// 5. 绘制调用
glDrawElements(GL_TRIANGLES, 36, GL_UNSIGNED_INT, 0);
```

**Vulkan 管线概览**

Vulkan 要求显式指定几乎所有管线状态，预先创建管线状态对象（PSO）：

```
Vulkan 渲染管线创建流程：

1. 创建 VkInstance（应用与 Vulkan 驱动连接）
2. 选择物理设备（GPU）
3. 创建逻辑设备和队列（图形队列、呈现队列）
4. 创建交换链（Swap Chain）和图像视图
5. 创建渲染通道（Render Pass）
6. 创建帧缓冲（Framebuffer）
7. 创建管线布局（Pipeline Layout）和描述符集布局
8. 创建图形管线（Graphics Pipeline）：
   - 顶点输入状态（Vertex Input State）
   - 输入装配状态（Input Assembly State）
   - 视口和裁剪状态（Viewport & Scissor State）
   - 光栅化状态（Rasterization State）
   - 多重采样状态（Multisample State）
   - 深度/模板状态（Depth Stencil State）
   - 颜色混合状态（Color Blend State）
   - 动态状态（Dynamic State）
   - 着色器阶段（Shader Stages）
   - 管线布局（Pipeline Layout）
   - 渲染通道（Render Pass）
9. 创建命令池和命令缓冲
10. 记录命令缓冲：
    - vkCmdBeginRenderPass
    - vkCmdBindPipeline
    - vkCmdBindVertexBuffers
    - vkCmdBindIndexBuffer
    - vkCmdBindDescriptorSets
    - vkCmdDrawIndexed
    - vkCmdEndRenderPass
11. 提交命令缓冲到队列
```

**DirectX 12 管线概览**

DirectX 12 与 Vulkan 概念非常相似，都是底层 API：

```
DirectX 12 渲染管线创建流程：

1. 创建 DXGI 工厂和交换链
2. 创建 D3D12 设备和命令队列
3. 创建描述符堆（RTV、DSV、CBV/SRV/UAV）
4. 创建命令分配器和命令列表
5. 创建根签名（Root Signature）—— 类似 Vulkan 的 Pipeline Layout
6. 编译着色器（HLSL → DXIL）
7. 创建图形管线状态对象（PSO）：
   - D3D12_GRAPHICS_PIPELINE_STATE_DESC
   - Input Layout
   - VS, PS, etc.
   - Rasterizer State
   - Blend State
   - Depth Stencil State
   - Render Target Formats
   - Sample Desc
8. 创建资源（顶点缓冲、索引缓冲、常量缓冲、纹理）
9. 记录命令列表：
   - OMSetRenderTargets
   - SetGraphicsRootSignature
   - SetPipelineState
   - IASetVertexBuffers
   - IASetIndexBuffer
   - DrawIndexedInstanced
10. 关闭命令列表并提交执行
```

**API 选择建议**

| 场景 | 推荐 API |
|------|----------|
| 学习图形学原理、快速原型 | OpenGL |
| 跨平台商业引擎（Windows/Linux/Android） | Vulkan |
| 仅 Windows/Xbox 平台 | DirectX 12 |
| 移动平台（iOS） | Metal |
| Web 平台 | WebGL / WebGPU |

---

### 1.7 现代 GPU 架构与渲染管线发展

现代 GPU 架构在经典渲染管线的基础上进行了大量扩展和优化。

**可编程管线的扩展**

传统管线只有顶点和片段着色器是可编程的。现代 GPU 增加了多个可编程阶段：

```
现代可编程管线阶段（OpenGL 4.x / Vulkan / DX12）：

┌─────────────────────────────────────────────────────────────┐
│  可选可编程阶段                                               │
├─────────────────────────────────────────────────────────────┤
│  细分着色器（Tessellation Shader）                            │
│    ├── 细分控制着色器（TCS / Hull Shader）                    │
│    │      决定每个图元细分成多少份                            │
│    └── 细分评估着色器（TES / Domain Shader）                  │
│           计算细分后顶点的位置                                │
│    用途：动态 LOD、曲面细分、置换贴图                          │
├─────────────────────────────────────────────────────────────┤
│  几何着色器（Geometry Shader）                                │
│    输入：一个图元（点/线/三角形）                             │
│    输出：零个或多个图元                                       │
│    用途：公告板（Billboard）、粒子系统、阴影体积、线框渲染       │
│    注意：性能开销大，现代用法逐渐被计算着色器替代               │
├─────────────────────────────────────────────────────────────┤
│  计算着色器（Compute Shader）                                 │
│    完全独立的通用计算管线                                      │
│    用途：粒子模拟、后处理、剔除、光照计算、物理模拟             │
│    特点：可读写任意缓冲，支持原子操作、共享内存、工作组同步      │
├─────────────────────────────────────────────────────────────┤
│  网格着色器（Mesh Shader）—— NVIDIA Turing+ / DX12 Ultimate   │
│    替代传统的顶点/细分/几何着色器管线                          │
│    特点：以线程组为单位处理网格，支持 GPU 驱动渲染              │
│    用途：大规模几何处理、集群剔除、Nanite 风格虚拟几何          │
└─────────────────────────────────────────────────────────────┘
```

**GPU Driven Rendering**

现代引擎（如 Unreal Engine 5 的 Nanite）越来越多地使用 GPU 来驱动渲染流程，减少 CPU 端的瓶颈：

```
传统渲染 vs GPU Driven Rendering：

传统（CPU 主导）：
CPU: 遍历场景 → 视锥体剔除 → 提交 Draw Call → GPU 渲染
     ↑_________________________________________↓
     每帧数千次往返，CPU 成为瓶颈

GPU Driven：
CPU: 提交整个场景数据（一次或几次 Draw Call）
GPU: 实例化渲染 → GPU 端剔除（视锥体/遮挡/LOD）→ 生成绘制命令 → 渲染
     ↑________________________________________________________↓
     大量工作转移到 GPU，CPU 几乎零开销
```

**实时光线追踪（Ray Tracing）**

NVIDIA RTX（Turing 架构及以后）、AMD RDNA2、Intel Arc 都支持硬件加速光线追踪：

- **光线生成着色器（Ray Generation Shader）**：发射光线
- **相交着色器（Intersection Shader）**：自定义图元相交测试
- **任意命中着色器（Any-Hit Shader）**：透明材质处理
- **最近命中着色器（Closest-Hit Shader）**：光线命中后的着色
- **未命中着色器（Miss Shader）**：光线未命中任何物体（天空盒等）

光线追踪管线与传统光栅化管线可以混合使用（混合渲染），这是当前实时渲染的主流方向。

**延迟渲染（Deferred Rendering）**

传统前向渲染（Forward Rendering）在每个片段着色器中计算光照，光源数量增加时性能急剧下降。延迟渲染将几何信息和光照计算分离：

```
延迟渲染管线：

Pass 1: 几何通道（G-Buffer Pass）
    ├── 渲染所有不透明几何体到多个渲染目标
    ├── G-Buffer 通常包含：
    │   - 世界空间位置（或深度重建）
    │   - 世界空间法线
    │   - 基础颜色（Albedo）
    │   - 材质属性（粗糙度、金属度、AO）
    └── 不计算光照！

Pass 2: 光照通道（Lighting Pass）
    ├── 渲染全屏四边形或光源几何体
    ├── 从 G-Buffer 采样几何信息
```

**G-Buffer 布局设计**

G-Buffer 的布局设计是延迟渲染的关键决策。设计目标是在信息完整性和带宽之间取得平衡——每个额外的 G-Buffer 纹理都意味着几何 Pass 的带宽增加。

| G-Buffer 布局方案 | 包含数据 | 纹理数量 | 带宽 | 适用场景 |
|:-------------------|:---------|:---------|:-----|:---------|
| 紧凑布局 | Albedo(RGB8)+Roughness, Normal(RG16f)+Metallic, Depth(R32f) | 3 | 较低 | 基础 PBR |
| 标准布局 | Albedo(RGBA8), Normal(RGBA16f), Depth(R32f), Material(RGBA8) | 4 | 中等 | 标准 PBR |
| 扩展布局 | + Emissive, + AO, + Subsurface, + Material ID | 6-8 | 较高 | 复杂材质 |
| 简化布局 | Albedo+Normal(合并在 RGBA16f), Depth | 2 | 低 | 移动端、性能敏感 |

紧凑布局将 Roughness 打包到 Albedo 的 Alpha 通道，将 Metallic 打包到 Normal 的 Alpha 通道或 Blue 通道（Normal 可以重建 Z 分量，只需存储 XY），在保持功能完整的同时减少纹理数量。深度纹理（Depth）可以从 Depth Pre-Pass 复用，或者直接从深度缓冲复制。MRT（Multiple Render Targets）技术允许几何 Pass 同时输出到多个纹理。

**Forward+ / Clustered 渲染**

为了结合前向渲染的灵活性和延迟渲染的光照效率，业界发展了 **Forward+（Tile-based Forward Rendering）** 和 **Clustered Rendering** 方案。

Forward+ 的工作流程是：首先执行一个深度预 Pass（Depth Pre-Pass），仅写入深度缓冲，禁用颜色输出。然后基于深度缓冲，将屏幕划分为 N x N（通常为 8x8 或 16x16）的 Tile，对每个 Tile 根据深度范围确定哪些光源可能影响该 Tile 内的像素。最后在前向渲染的片元着色器中，只遍历与该像素所在 Tile 关联的光源进行光照计算。

Clustered Rendering 进一步将视锥体在深度方向上划分为对数分布的 Cluster（簇），形成一个 3D 的 Tile-Cluster 网格。这种划分更符合透视投影的特性——远处物体在屏幕上的面积小但深度范围大，近处则相反。每个 Cluster 维护一个可能影响它的光源列表，片元着色器根据像素位置确定所属 Cluster，只遍历相关光源。

| 方案 | 核心思想 | 光源复杂度 | 透明物体 | MSAA | 材质灵活性 | 额外开销 |
|:-----|:---------|:-----------|:---------|:-----|:-----------|:---------|
| Forward | 逐物体逐光源 | O(M * K) | 原生支持 | 支持 | 完全灵活 | 无 |
| Deferred | G-Buffer + 逐像素光源 | O(Pixel + N) | 需额外 Pass | 不支持 | 受限 | G-Buffer 带宽 |
| Forward+ | Tile 光源剔除 + Forward | O(M * K_tile) | 原生支持 | 支持 | 完全灵活 | 光源剔除 Pass |
| Clustered | 3D Cluster 光源剔除 | O(M * K_cluster) | 原生支持 | 支持 | 完全灵活 | 光源剔除 Pass |

Clustered Rendering 已成为现代引擎（如 Unity HDRP、Unreal Engine 4+、Frostbite）的默认渲染方案，它在保持前向渲染优势的同时，通过高效的光源剔除实现了对大量光源的支持。

延迟渲染的核心优势是光照复杂度从 O(M * K) 降低到 O(N_pixels + N_lights)——每个光源只影响其光照范围内的像素。对于大量光源的场景，这是数量级的性能提升。通过模板测试或 Light Volume 几何体，可以精确限制每个光源的受影响像素范围。

延迟渲染的主要限制是：不支持透明物体（没有深度信息来排序和混合），需要额外的前向渲染 Pass 处理透明物体；G-Buffer 带宽高，对填充率敏感；不支持 MSAA（G-Buffer 的多重采样开销极大）；材质多样性受限（所有物体使用统一的 G-Buffer 布局）。

---

## 2. 代码示例

以下是一个完整的 OpenGL 示例程序，渲染一个带 MVP 变换的彩色立方体。程序包含完整的顶点/片段着色器、摄像机控制、以及旋转动画。

```cpp
// =============================================================================
// 02-rendering-pipeline-demo.cpp
// 渲染管线基础：带 MVP 变换的彩色旋转立方体
// 依赖：GLFW3, GLAD, GLM
// =============================================================================

#include <glad/glad.h>
#include <GLFW/glfw3.h>
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>

#include <iostream>
#include <cmath>

// =============================================================================
// 着色器源码
// =============================================================================

const char* vertexShaderSource = R"(
#version 330 core

layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec3 aColor;

uniform mat4 uModel;
uniform mat4 uView;
uniform mat4 uProjection;
uniform mat3 uNormalMatrix;

out vec3 vWorldPos;
out vec3 vNormal;
out vec3 vColor;

void main() {
    vec4 worldPos = uModel * vec4(aPos, 1.0);
    vWorldPos = worldPos.xyz;
    vNormal = normalize(uNormalMatrix * aNormal);
    vColor = aColor;
    gl_Position = uProjection * uView * worldPos;
}
)";

const char* fragmentShaderSource = R"(
#version 330 core

in vec3 vWorldPos;
in vec3 vNormal;
in vec3 vColor;

uniform vec3 uCameraPos;
uniform vec3 uLightPos;
uniform vec3 uLightColor;
uniform float uAmbient;

out vec4 FragColor;

void main() {
    // 法线归一化
    vec3 N = normalize(vNormal);

    // 光照方向
    vec3 L = normalize(uLightPos - vWorldPos);

    // 观察方向
    vec3 V = normalize(uCameraPos - vWorldPos);

    // 半角向量（Blinn-Phong）
    vec3 H = normalize(L + V);

    // 漫反射
    float NdotL = max(dot(N, L), 0.0);
    vec3 diffuse = vColor * uLightColor * NdotL;

    // 镜面反射
    float NdotH = max(dot(N, H), 0.0);
    float specularPower = 64.0;
    vec3 specular = vec3(0.3) * uLightColor * pow(NdotH, specularPower);

    // 环境光
    vec3 ambient = vColor * uAmbient;

    // 最终颜色（线性空间）
    vec3 linearColor = ambient + diffuse + specular;

    // Gamma 校正（线性 → sRGB）
    vec3 finalColor = pow(linearColor, vec3(1.0 / 2.2));

    FragColor = vec4(finalColor, 1.0);
}
)";

// =============================================================================
// 全局状态
// =============================================================================

int screenWidth = 1280;
int screenHeight = 720;

// 摄像机参数
glm::vec3 cameraPos(3.0f, 3.0f, 5.0f);
glm::vec3 cameraTarget(0.0f, 0.0f, 0.0f);
glm::vec3 cameraUp(0.0f, 1.0f, 0.0f);

// 鼠标控制
bool firstMouse = true;
float lastX = screenWidth / 2.0f;
float lastY = screenHeight / 2.0f;
float yaw = -120.0f;
float pitch = -30.0f;
float fov = 45.0f;

// =============================================================================
// 工具函数
// =============================================================================

// 编译单个着色器
GLuint compileShader(GLenum type, const char* source) {
    GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &source, nullptr);
    glCompileShader(shader);

    GLint success;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
    if (!success) {
        char infoLog[512];
        glGetShaderInfoLog(shader, 512, nullptr, infoLog);
        std::cerr << "Shader compilation failed:\n" << infoLog << std::endl;
        return 0;
    }
    return shader;
}

// 链接着色器程序
GLuint createShaderProgram(const char* vsSource, const char* fsSource) {
    GLuint vs = compileShader(GL_VERTEX_SHADER, vsSource);
    GLuint fs = compileShader(GL_FRAGMENT_SHADER, fsSource);

    GLuint program = glCreateProgram();
    glAttachShader(program, vs);
    glAttachShader(program, fs);
    glLinkProgram(program);

    GLint success;
    glGetProgramiv(program, GL_LINK_STATUS, &success);
    if (!success) {
        char infoLog[512];
        glGetProgramInfoLog(program, 512, nullptr, infoLog);
        std::cerr << "Program linking failed:\n" << infoLog << std::endl;
        return 0;
    }

    glDeleteShader(vs);
    glDeleteShader(fs);
    return program;
}

// 更新摄像机方向
void updateCameraDirection() {
    glm::vec3 direction;
    direction.x = cos(glm::radians(yaw)) * cos(glm::radians(pitch));
    direction.y = sin(glm::radians(pitch));
    direction.z = sin(glm::radians(yaw)) * cos(glm::radians(pitch));
    cameraTarget = cameraPos + glm::normalize(direction);
}

// =============================================================================
// 回调函数
// =============================================================================

void framebufferSizeCallback(GLFWwindow* window, int width, int height) {
    screenWidth = width;
    screenHeight = height;
    glViewport(0, 0, width, height);
}

void mouseCallback(GLFWwindow* window, double xpos, double ypos) {
    if (firstMouse) {
        lastX = (float)xpos;
        lastY = (float)ypos;
        firstMouse = false;
    }

    float xoffset = (float)xpos - lastX;
    float yoffset = lastY - (float)ypos; // 反转 Y 轴
    lastX = (float)xpos;
    lastY = (float)ypos;

    float sensitivity = 0.1f;
    xoffset *= sensitivity;
    yoffset *= sensitivity;

    yaw += xoffset;
    pitch += yoffset;

    // 限制俯仰角
    if (pitch > 89.0f) pitch = 89.0f;
    if (pitch < -89.0f) pitch = -89.0f;

    updateCameraDirection();
}

void scrollCallback(GLFWwindow* window, double xoffset, double yoffset) {
    fov -= (float)yoffset;
    if (fov < 1.0f) fov = 1.0f;
    if (fov > 90.0f) fov = 90.0f;
}

// =============================================================================
// 主函数
// =============================================================================

int main() {
    // ---- 初始化 GLFW ----
    if (!glfwInit()) {
        std::cerr << "Failed to initialize GLFW" << std::endl;
        return -1;
    }

    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);

    GLFWwindow* window = glfwCreateWindow(screenWidth, screenHeight,
                                          "02 Rendering Pipeline - Colored Cube",
                                          nullptr, nullptr);
    if (!window) {
        std::cerr << "Failed to create GLFW window" << std::endl;
        glfwTerminate();
        return -1;
    }

    glfwMakeContextCurrent(window);
    glfwSetFramebufferSizeCallback(window, framebufferSizeCallback);
    glfwSetCursorPosCallback(window, mouseCallback);
    glfwSetScrollCallback(window, scrollCallback);
    glfwSetInputMode(window, GLFW_CURSOR, GLFW_CURSOR_DISABLED);

    // ---- 初始化 GLAD ----
    if (!gladLoadGLLoader((GLADloadproc)glfwGetProcAddress)) {
        std::cerr << "Failed to initialize GLAD" << std::endl;
        return -1;
    }

    // 启用深度测试
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LESS);

    // ---- 创建立方体顶点数据 ----
    // 每个顶点：位置(3) + 法线(3) + 颜色(3)
    // 立方体 6 个面 × 每个面 2 个三角形 × 每个三角形 3 个顶点 = 36 个顶点
    float vertices[] = {
        // 背面 (z = -0.5, 法线指向 -Z)
        // 三角形 1
        -0.5f, -0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.8f, 0.2f, 0.2f, // 红
         0.5f, -0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.8f, 0.2f, 0.2f,
         0.5f,  0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.8f, 0.2f, 0.2f,
        // 三角形 2
         0.5f,  0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.8f, 0.2f, 0.2f,
        -0.5f,  0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.8f, 0.2f, 0.2f,
        -0.5f, -0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.8f, 0.2f, 0.2f,

        // 正面 (z = 0.5, 法线指向 +Z)
        -0.5f, -0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.2f, 0.8f, 0.2f, // 绿
         0.5f, -0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.2f, 0.8f, 0.2f,
         0.5f,  0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.2f, 0.8f, 0.2f,
         0.5f,  0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.2f, 0.8f, 0.2f,
        -0.5f,  0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.2f, 0.8f, 0.2f,
        -0.5f, -0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.2f, 0.8f, 0.2f,

        // 左面 (x = -0.5, 法线指向 -X)
        -0.5f,  0.5f,  0.5f, -1.0f,  0.0f,  0.0f,  0.2f, 0.2f, 0.8f, // 蓝
        -0.5f,  0.5f, -0.5f, -1.0f,  0.0f,  0.0f,  0.2f, 0.2f, 0.8f,
        -0.5f, -0.5f, -0.5f, -1.0f,  0.0f,  0.0f,  0.2f, 0.2f, 0.8f,
        -0.5f, -0.5f, -0.5f, -1.0f,  0.0f,  0.0f,  0.2f, 0.2f, 0.8f,
        -0.5f, -0.5f,  0.5f, -1.0f,  0.0f,  0.0f,  0.2f, 0.2f, 0.8f,
        -0.5f,  0.5f,  0.5f, -1.0f,  0.0f,  0.0f,  0.2f, 0.2f, 0.8f,

        // 右面 (x = 0.5, 法线指向 +X)
         0.5f,  0.5f,  0.5f,  1.0f,  0.0f,  0.0f,  0.8f, 0.8f, 0.2f, // 黄
         0.5f,  0.5f, -0.5f,  1.0f,  0.0f,  0.0f,  0.8f, 0.8f, 0.2f,
         0.5f, -0.5f, -0.5f,  1.0f,  0.0f,  0.0f,  0.8f, 0.8f, 0.2f,
         0.5f, -0.5f, -0.5f,  1.0f,  0.0f,  0.0f,  0.8f, 0.8f, 0.2f,
         0.5f, -0.5f,  0.5f,  1.0f,  0.0f,  0.0f,  0.8f, 0.8f, 0.2f,
         0.5f,  0.5f,  0.5f,  1.0f,  0.0f,  0.0f,  0.8f, 0.8f, 0.2f,

        // 底面 (y = -0.5, 法线指向 -Y)
        -0.5f, -0.5f, -0.5f,  0.0f, -1.0f,  0.0f,  0.8f, 0.2f, 0.8f, // 紫
         0.5f, -0.5f, -0.5f,  0.0f, -1.0f,  0.0f,  0.8f, 0.2f, 0.8f,
         0.5f, -0.5f,  0.5f,  0.0f, -1.0f,  0.0f,  0.8f, 0.2f, 0.8f,
         0.5f, -0.5f,  0.5f,  0.0f, -1.0f,  0.0f,  0.8f, 0.2f, 0.8f,
        -0.5f, -0.5f,  0.5f,  0.0f, -1.0f,  0.0f,  0.8f, 0.2f, 0.8f,
        -0.5f, -0.5f, -0.5f,  0.0f, -1.0f,  0.0f,  0.8f, 0.2f, 0.8f,

        // 顶面 (y = 0.5, 法线指向 +Y)
        -0.5f,  0.5f, -0.5f,  0.0f,  1.0f,  0.0f,  0.2f, 0.8f, 0.8f, // 青
         0.5f,  0.5f, -0.5f,  0.0f,  1.0f,  0.0f,  0.2f, 0.8f, 0.8f,
         0.5f,  0.5f,  0.5f,  0.0f,  1.0f,  0.0f,  0.2f, 0.8f, 0.8f,
         0.5f,  0.5f,  0.5f,  0.0f,  1.0f,  0.0f,  0.2f, 0.8f, 0.8f,
        -0.5f,  0.5f,  0.5f,  0.0f,  1.0f,  0.0f,  0.2f, 0.8f, 0.8f,
        -0.5f,  0.5f, -0.5f,  0.0f,  1.0f,  0.0f,  0.2f, 0.8f, 0.8f,
    };

    // ---- 创建 VAO/VBO ----
    GLuint VAO, VBO;
    glGenVertexArrays(1, &VAO);
    glGenBuffers(1, &VBO);

    glBindVertexArray(VAO);

    glBindBuffer(GL_ARRAY_BUFFER, VBO);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);

    // 位置属性 (location = 0)
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 9 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);

    // 法线属性 (location = 1)
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 9 * sizeof(float),
                          (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);

    // 颜色属性 (location = 2)
    glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 9 * sizeof(float),
                          (void*)(6 * sizeof(float)));
    glEnableVertexAttribArray(2);

    glBindVertexArray(0);

    // ---- 创建着色器程序 ----
    GLuint shaderProgram = createShaderProgram(vertexShaderSource, fragmentShaderSource);
    if (!shaderProgram) {
        return -1;
    }

    // 获取 Uniform 位置
    GLint uModelLoc = glGetUniformLocation(shaderProgram, "uModel");
    GLint uViewLoc = glGetUniformLocation(shaderProgram, "uView");
    GLint uProjectionLoc = glGetUniformLocation(shaderProgram, "uProjection");
    GLint uNormalMatrixLoc = glGetUniformLocation(shaderProgram, "uNormalMatrix");
    GLint uCameraPosLoc = glGetUniformLocation(shaderProgram, "uCameraPos");
    GLint uLightPosLoc = glGetUniformLocation(shaderProgram, "uLightPos");
    GLint uLightColorLoc = glGetUniformLocation(shaderProgram, "uLightColor");
    GLint uAmbientLoc = glGetUniformLocation(shaderProgram, "uAmbient");

    // ---- 渲染循环 ----
    while (!glfwWindowShouldClose(window)) {
        // 计算时间
        float time = (float)glfwGetTime();

        // 处理输入
        if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS) {
            glfwSetWindowShouldClose(window, true);
        }

        // 清屏
        glClearColor(0.1f, 0.1f, 0.15f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        // 使用着色器
        glUseProgram(shaderProgram);

        // ---- 构建 MVP 矩阵 ----

        // 1. 模型矩阵：旋转 + 缩放
        glm::mat4 model = glm::mat4(1.0f);
        model = glm::rotate(model, time * 0.5f, glm::vec3(0.0f, 1.0f, 0.0f)); // Y轴旋转
        model = glm::rotate(model, time * 0.3f, glm::vec3(1.0f, 0.0f, 0.0f)); // X轴旋转
        model = glm::scale(model, glm::vec3(1.5f, 1.5f, 1.5f));

        // 2. 观察矩阵
        glm::mat4 view = glm::lookAt(cameraPos, cameraTarget, cameraUp);

        // 3. 投影矩阵
        glm::mat4 projection = glm::perspective(
            glm::radians(fov),
            (float)screenWidth / (float)screenHeight,
            0.1f, 100.0f
        );

        // 4. 法线矩阵（model 的逆转置的上 3x3）
        glm::mat3 normalMatrix = glm::transpose(glm::inverse(glm::mat3(model)));

        // ---- 设置 Uniform ----
        glUniformMatrix4fv(uModelLoc, 1, GL_FALSE, glm::value_ptr(model));
        glUniformMatrix4fv(uViewLoc, 1, GL_FALSE, glm::value_ptr(view));
        glUniformMatrix4fv(uProjectionLoc, 1, GL_FALSE, glm::value_ptr(projection));
        glUniformMatrix3fv(uNormalMatrixLoc, 1, GL_FALSE, glm::value_ptr(normalMatrix));

        glUniform3f(uCameraPosLoc, cameraPos.x, cameraPos.y, cameraPos.z);
        glUniform3f(uLightPosLoc, 5.0f, 5.0f, 5.0f);  // 光源位置
        glUniform3f(uLightColorLoc, 1.0f, 1.0f, 1.0f); // 白光
        glUniform1f(uAmbientLoc, 0.15f);               // 环境光强度

        // ---- 绘制立方体 ----
        glBindVertexArray(VAO);
        glDrawArrays(GL_TRIANGLES, 0, 36);

        // 交换缓冲并轮询事件
        glfwSwapBuffers(window);
        glfwPollEvents();
    }

    // ---- 清理 ----
    glDeleteVertexArrays(1, &VAO);
    glDeleteBuffers(1, &VBO);
    glDeleteProgram(shaderProgram);

    glfwTerminate();
    return 0;
}
```

**运行方式:**

1. **安装依赖**：
   - GLFW3：`vcpkg install glfw3` 或从源码编译
   - GLAD：从 https://glad.dav1d.de/ 生成 OpenGL 3.3 Core 加载器
   - GLM：`vcpkg install glm` 或头文件-only

2. **编译（CMake 示例）**：
   ```cmake
   cmake_minimum_required(VERSION 3.10)
   project(RenderingPipelineDemo)
   set(CMAKE_CXX_STANDARD 14)

   find_package(glfw3 REQUIRED)
   find_package(glm REQUIRED)

   add_executable(demo 02-rendering-pipeline-demo.cpp glad.c)
   target_link_libraries(demo glfw)
   target_include_directories(demo PRIVATE ${CMAKE_SOURCE_DIR}/include)
   ```

3. **运行**：
   ```bash
   ./demo
   ```

**预期输出:**

- 一个 1280x720 的窗口，标题为 "02 Rendering Pipeline - Colored Cube"
- 窗口中央显示一个彩色立方体，六个面分别为：红、绿、蓝、黄、紫、青
- 立方体自动绕 X 轴和 Y 轴缓慢旋转
- 每个面有 Blinn-Phong 光照效果（漫反射 + 镜面高光）
- 鼠标移动控制摄像机视角（类似 FPS 游戏）
- 鼠标滚轮缩放视野
- 按 ESC 退出

---

## 3. 练习

### 练习 1：实现索引缓冲绘制（预计 1h）

当前示例使用 36 个独立顶点绘制立方体（每个面 6 个顶点 × 6 个面），存在大量顶点重复。立方体实际只有 8 个唯一顶点。

**任务**：
1. 提取 8 个唯一顶点位置
2. 创建索引缓冲（EBO/IBO），定义 12 个三角形（36 个索引）
3. 修改顶点数据布局，使用索引绘制 `glDrawElements` 替代 `glDrawArrays`
4. 注意：使用索引绘制时，每个顶点只能有一个法线和一个颜色。如果想让不同面有不同颜色，需要使用**面法线**或**顶点拆分**策略

**提示**：
- 一种方案是为每个面创建独立的顶点（共 24 个顶点，每个顶点只属于一个面）
- 使用 `glDrawElements(GL_TRIANGLES, 36, GL_UNSIGNED_INT, 0)`

### 练习 2：添加多个立方体与实例化渲染（预计 2h）

**任务**：
1. 在场景中渲染 100 个立方体，排列成 10×10 的网格
2. 每个立方体有不同的位置和旋转
3. 使用**实例化渲染（Instancing）**优化：一次 Draw Call 绘制所有立方体
4. 在顶点着色器中使用 `gl_InstanceID` 或实例化顶点属性来获取每个实例的变换

**提示**：
```cpp
// 创建实例数据缓冲
glm::mat4 instanceMatrices[100];
// ... 填充每个实例的 model 矩阵 ...

GLuint instanceVBO;
glGenBuffers(1, &instanceVBO);
glBindBuffer(GL_ARRAY_BUFFER, instanceVBO);
glBufferData(GL_ARRAY_BUFFER, sizeof(instanceMatrices), instanceMatrices, GL_STATIC_DRAW);

// 将 mat4 作为 4 个 vec4 顶点属性
for (int i = 0; i < 4; i++) {
    glEnableVertexAttribArray(3 + i);
    glVertexAttribPointer(3 + i, 4, GL_FLOAT, GL_FALSE, sizeof(glm::mat4),
                          (void*)(i * sizeof(glm::vec4)));
    glVertexAttribDivisor(3 + i, 1); // 每个实例更新一次
}

// 绘制
glDrawArraysInstanced(GL_TRIANGLES, 0, 36, 100);
```

### 练习 3（可选）：实现简单的延迟渲染管线（预计 4h）

**任务**：
1. 创建 G-Buffer：使用帧缓冲对象（FBO）和多个颜色附件
   - 附件 0：世界空间位置（RGBA16F）
   - 附件 1：世界空间法线（RGBA16F）
   - 附件 2：基础颜色 + 粗糙度（RGBA8）
2. 第一遍渲染：将立方体的几何信息写入 G-Buffer
3. 第二遍渲染：渲染全屏四边形，从 G-Buffer 采样并计算光照
4. 添加多个点光源，观察性能差异

**提示**：
- 使用 `glBindFramebuffer(GL_FRAMEBUFFER, gBufferFBO)` 绑定自定义帧缓冲
- 使用 `glDrawBuffers` 指定多个渲染目标
- 第二遍的片段着色器使用 `uniform sampler2D` 采样 G-Buffer
- 注意 G-Buffer 的精度选择，位置信息需要浮点纹理

---

## 4. 扩展阅读

### 经典书籍

1. **《Real-Time Rendering, 4th Edition》** — Tomas Akenine-Möller 等
   - 实时渲染领域的圣经，第 1-5 章详细讲解渲染管线和 GPU 架构
   - 必读，虽然厚重但值得逐章研读

2. **《OpenGL SuperBible, 7th Edition》** — Graham Sellers 等
   - OpenGL 编程的权威参考，涵盖从基础到高级特性
   - 适合作为 OpenGL API 的手册

3. **《Learning Modern 3D Graphics Programming》** — Jason L. McKesson
   - 免费在线书籍（https://paroj.github.io/gltut/）
   - 从零开始讲解现代 OpenGL 和图形学原理

4. **《Vulkan Programming Guide》** — Graham Sellers, John Kessenich
   - Vulkan API 的官方指南，适合想深入底层 API 的读者

### 在线资源

1. **LearnOpenGL**（https://learnopengl.com/ / https://learnopengl-cn.github.io/）
   - 最友好的现代 OpenGL 教程，中文翻译质量高
   - 强烈推荐按章节顺序学习

2. **Scratchapixel**（https://www.scratchapixel.com/）
   - 计算机图形学基础教程，数学推导详细
   - 光栅化、光线追踪、着色等主题都有覆盖

3. **GPU Gems 系列**（NVIDIA 官方）
   - GPU Gems 1/2/3 和 GPU Pro 系列
   - 大量高级渲染技术的实现细节

4. **Fabian Giesen 的博客**（https://fgiesen.wordpress.com/）
   - 图形程序员的技术博客，光栅化、压缩、优化等主题
   - "A trip through the Graphics Pipeline 2011" 系列必读

### 论文与报告

1. **"A Trip Through the Graphics Pipeline 2011"** — Fabian Giesen
   - 详细解释现代 GPU 的内部工作原理
   - 从 API 调用到像素输出的完整旅程

2. **"GPU Architecture: From Graphics to Compute"** — various
   - 理解 GPU 从图形专用到通用计算的演变

3. **"The Rendering Equation"** — James T. Kajiya (1986)
   - 渲染方程的原始论文，理解光照的数学基础

---

## 常见陷阱

### 陷阱 1：矩阵乘法顺序错误

```cpp
// 错误：顺序颠倒
gl_Position = model * view * projection * vec4(pos, 1.0);
// 正确：从右到左应用变换
gl_Position = projection * view * model * vec4(pos, 1.0);
```

**原因**：矩阵乘法是右结合的。`P * V * M * v` 表示先应用 M，再 V，再 P。如果顺序写反，结果完全错误。

### 陷阱 2：法线变换错误

```cpp
// 错误：直接用 model 矩阵变换法线
vec3 worldNormal = (model * vec4(normal, 0.0)).xyz;

// 正确：使用逆转置矩阵
vec3 worldNormal = normalize((inverse(transpose(model)) * vec4(normal, 0.0)).xyz);

// 或如果 model 只包含旋转和均匀缩放：
vec3 worldNormal = normalize((mat3(model) * normal));
```

**原因**：非均匀缩放会改变法线与表面的垂直关系。逆转置矩阵保持法线的正交性。

### 陷阱 3：深度缓冲精度问题（Z-fighting）

```cpp
// 错误：near 太小，far/near 比值太大
glm::perspective(glm::radians(45.0f), aspect, 0.001f, 10000.0f);

// 正确：根据场景调整 near/far
glm::perspective(glm::radians(45.0f), aspect, 0.1f, 100.0f);
```

**原因**：透视投影对 Z 值的映射是非线性的。near 越小，远端的深度精度越差。当两个表面深度值非常接近时，GPU 无法区分前后关系，导致闪烁。

**解决方案**：
- 尽可能增大 near 平面距离
- 使用对数深度缓冲（Logarithmic Depth Buffer）
- 使用反向 Z（Reverse Z，将深度映射从 [0,1] 反转为 [1,0]，配合 GL_GREATER）

### 陷阱 4：Gamma 校正混淆

```cpp
// 错误：在线性空间计算后直接输出
FragColor = vec4(ambient + diffuse + specular, 1.0);

// 正确：计算在线性空间，输出前 Gamma 校正
vec3 linearColor = ambient + diffuse + specular;
vec3 finalColor = pow(linearColor, vec3(1.0 / 2.2));
FragColor = vec4(finalColor, 1.0);
```

**原因**：纹理图片通常存储在 sRGB 空间（Gamma ≈ 2.2），而光照计算必须在线性空间进行。如果不对纹理做反 Gamma 校正就参与光照计算，结果会过亮。输出到屏幕前需要重新 Gamma 校正。

**正确做法**：
1. 采样 sRGB 纹理时，OpenGL 可以自动转换：`glTexImage2D(..., GL_SRGB8_ALPHA8, ...)`
2. 或者手动在着色器中 `pow(textureColor, vec3(2.2))`
3. 最终输出前 `pow(finalColor, vec3(1.0/2.2))`
4. 或者使用帧缓冲的 sRGB 自动转换：`glEnable(GL_FRAMEBUFFER_SRGB)`

### 陷阱 5：背面剔除与顶点绕序

```cpp
// 启用背面剔除
glEnable(GL_CULL_FACE);
glCullFace(GL_BACK);
glFrontFace(GL_CCW); // 或 GL_CW
```

**原因**：如果顶点绕序（winding order）与设置不匹配，所有面都会被剔除，导致物体"消失"。

**检查方法**：先关闭剔除 `glDisable(GL_CULL_FACE)`，确认物体可见，然后检查顶点定义顺序。从三角形正面看，顶点应该是逆时针（CCW）或顺时针（CW）排列。

### 陷阱 6：Uniform 变量名不匹配

```cpp
// C++ 代码
glUniformMatrix4fv(glGetUniformLocation(program, "model"), ...);

// 着色器代码
uniform mat4 uModel; // 名称不匹配！
```

**原因**：`glGetUniformLocation` 找不到名称时会返回 -1，后续 `glUniform*` 调用 silently 失败，不会报错。

**建议**：始终检查 Uniform 位置是否为 -1，或使用一致的命名约定（如 `uModel`、`uView` 等前缀）。

### 陷阱 7：视口变换遗漏

```cpp
// 错误：窗口大小改变后不更新视口
// 正确：在窗口大小改变回调中更新
glViewport(0, 0, newWidth, newHeight);
```

**原因**：OpenGL 的视口定义了 NDC 到屏幕像素的映射。如果不随窗口大小更新，渲染结果会被拉伸或只显示在部分区域。

### 陷阱 8：忘记清除深度缓冲

```cpp
// 错误：只清除颜色缓冲
glClear(GL_COLOR_BUFFER_BIT);

// 正确：同时清除颜色和深度缓冲
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
```

**原因**：如果不清除深度缓冲，上一帧的深度值会影响当前帧的渲染，导致新帧的物体被错误地判定为被遮挡。

### 陷阱 9：VSync 与帧率

```cpp
// 控制 VSync
glfwSwapInterval(1); // 开启 VSync，帧率锁定显示器刷新率
glfwSwapInterval(0); // 关闭 VSync，尽可能快渲染
```

**注意**：开启 VSync 时，如果渲染时间超过一帧（如 16.67ms@60Hz），帧率会直接掉到 30fps（等待两帧）。这是交换间隔的整数倍限制。对于需要精确帧率控制的游戏，需要更复杂的帧率管理策略。
