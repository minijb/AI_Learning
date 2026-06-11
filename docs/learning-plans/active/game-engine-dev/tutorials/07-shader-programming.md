---
title: "着色器编程：GLSL/HLSL 与 GPU 计算"
updated: 2026-06-05
---

# 着色器编程：GLSL/HLSL 与 GPU 计算

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 06-渲染管线基础：从顶点到像素

---

## 1. 概念讲解

### 1.1 为什么需要着色器？

在固定功能管线时代，图形 API（如早期 OpenGL 1.x）提供了一套预定义的渲染流程：顶点变换、光照计算、纹理映射、雾效等，开发者只能通过有限的 API 参数进行微调。这种模式虽然简单易用，但严重限制了渲染效果的多样性。

着色器（Shader）的引入彻底改变了这一局面。着色器是一段运行在 GPU 上的小程序，它允许开发者直接控制渲染管线的各个阶段。从 OpenGL 2.0 / Direct3D 9 开始，可编程管线成为标准，现代图形渲染的几乎所有视觉效果——从逼真的光照模型到复杂的后处理特效——都依赖于着色器程序。

**着色器带来的核心能力：**

- **完全控制顶点处理**：自定义顶点变形、骨骼动画、GPU 粒子系统
- **完全控制像素着色**：PBR 材质、法线贴图、环境光遮蔽、延迟渲染
- **通用 GPU 计算**：物理模拟、AI 寻路、图像处理、机器学习推理
- **高度并行执行**：利用 GPU 的成百上千个核心同时处理大量数据

### 1.2 核心思想：数据并行与 SIMD 执行模型

GPU 的设计哲学与 CPU 截然不同。CPU 追求单线程执行速度和复杂控制流（分支预测、乱序执行、大缓存），而 GPU 追求**数据级并行**——对大量数据执行相同的操作。

#### SIMD / SIMT 执行模型

GPU 采用 **SIMD（Single Instruction, Multiple Data）** 或更准确地说是 **SIMT（Single Instruction, Multiple Threads）** 架构。简单来说：

- 成百上千个"线程"同时执行**同一段**着色器代码
- 每个线程处理不同的数据（不同的顶点、不同的像素）
- 所有线程共享同一条指令流，但拥有独立的寄存器状态

#### Warp / Wavefront：GPU 调度的基本单元

NVIDIA GPU 将 32 个线程组织为一个 **Warp**，AMD GPU 将 64 个线程组织为一个 **Wavefront**。这是 GPU 调度和执行的最小单元：

- Warp 内所有线程**同步执行**相同的指令
- 如果 Warp 内线程发生分支（如 `if` 语句条件不同），GPU 必须**串行执行**各分支路径，屏蔽不满足条件的线程——这称为**分支发散（Branch Divergence）**
- 分支发散是 GPU 性能的头号杀手之一

```
// 示例：分支发散
if (vertex.position.x > 0.0) {
    // Warp 中 x>0 的线程执行这里
    color = red;
} else {
    // Warp 中 x<=0 的线程执行这里
    color = blue;
}
// 整个 Warp 需要执行两条路径，各自屏蔽一半线程
```

**优化原则**：尽量减少 Warp 内的分支发散。对于均匀数据（如材质属性相同的面片），分支代价很小；对于高度变化的数据（如随机分布的顶点），分支代价巨大。

#### 内存访问模式

GPU 内存带宽高但延迟也高。为了隐藏延迟，GPU 采用大量线程同时执行，当一个 Warp 等待内存时，调度器切换到另一个就绪的 Warp。

**关键优化**：确保 Warp 内线程的内存访问是**连续的**（Coalesced）。如果 Warp 中 32 个线程访问连续的内存地址，GPU 可以合并为一次内存事务；如果访问随机分散的地址，则需要 32 次独立内存访问。

### 1.3 顶点着色器（Vertex Shader）详解

顶点着色器是渲染管线的第一个可编程阶段，每个输入顶点都会触发一次顶点着色器执行。

#### 输入：Attribute（顶点属性）

顶点属性是从 CPU 通过 VAO/VBO 传递到 GPU 的逐顶点数据。常见的属性包括：

| 属性 | 类型 | 含义 |
|------|------|------|
| `position` | `vec3` | 顶点位置（模型空间或局部空间） |
| `normal` | `vec3` | 顶点法线（用于光照计算） |
| `texCoord` | `vec2` | 纹理坐标（UV） |
| `color` | `vec4` | 顶点颜色 |
| `tangent` | `vec4` | 切线向量（用于法线贴图） |
| `boneIndices` | `ivec4` | 骨骼索引（骨骼动画） |
| `boneWeights` | `vec4` | 骨骼权重（骨骼动画） |

在 GLSL 中，顶点属性通过 `layout(location = N) in` 声明：

```glsl
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;
```

`location` 编号与 C++ 端 `glVertexAttribPointer` 的索引对应。

#### 输出：Varying / Interpolator

顶点着色器的输出会被光栅化器插值后传递给片段着色器。在 GLSL 中，这些变量称为 `out`：

```glsl
out vec3 vWorldPos;
out vec3 vNormal;
out vec2 vTexCoord;
```

**重要**：顶点着色器**必须**输出 `gl_Position`（裁剪空间位置），这是光栅化器的唯一强制输入。

#### Uniform：全局常量数据

Uniform 是从 CPU 传递到 GPU 的**逐绘制调用**数据，对所有顶点/片段都相同。典型 uniform 包括：

- 变换矩阵（模型矩阵、视图矩阵、投影矩阵）
- 光源参数（位置、颜色、方向）
- 材质参数（颜色、光泽度、纹理采样器）
- 时间、屏幕尺寸等全局状态

```glsl
uniform mat4 uModelMatrix;
uniform mat4 uViewMatrix;
uniform mat4 uProjectionMatrix;
uniform vec3 uLightPos;
```

#### 顶点着色器的典型任务

1. **坐标变换**：将顶点从模型空间 → 世界空间 → 观察空间 → 裁剪空间
2. **法线变换**：将法线向量变换到正确的空间（注意非均匀缩放时需要逆转置矩阵）
3. **逐顶点光照**（如果采用 Gouraud 着色）：在顶点级别计算光照颜色，插值到片段
4. **顶点变形**：骨骼动画、形变、波浪效果、GPU 粒子
5. **纹理坐标变换**：UV 滚动、投影纹理

### 1.4 片段着色器（Fragment Shader / Pixel Shader）详解

片段着色器（OpenGL 术语）或称像素着色器（DirectX 术语）在光栅化之后执行，每个光栅化生成的片段（潜在像素）都会触发一次执行。

#### 输入：插值后的顶点输出

```glsl
in vec3 vWorldPos;
in vec3 vNormal;
in vec2 vTexCoord;
```

这些值是光栅化器对三角形三个顶点的对应输出进行**重心坐标插值**后的结果。

**注意**：对于法线等向量属性，直接插值后再归一化，与先归一化再插值的结果不同。通常需要在片段着色器中重新归一化：

```glsl
vec3 normal = normalize(vNormal);
```

#### 输出：颜色与深度

片段着色器的主要输出是颜色：

```glsl
out vec4 fragColor;
```

也可以输出到多个渲染目标（MRT，Multiple Render Targets）：

```glsl
layout(location = 0) out vec4 gAlbedo;
layout(location = 1) out vec4 gNormal;
layout(location = 2) out vec4 gDepth;
```

#### 纹理采样

纹理采样是片段着色器的核心操作之一：

```glsl
uniform sampler2D uDiffuseMap;
uniform sampler2D uNormalMap;

vec4 diffuseColor = texture(uDiffuseMap, vTexCoord);
vec4 normalSample = texture(uNormalMap, vTexCoord);
```

**纹理采样器类型：**

| GLSL 类型 | 用途 |
|-----------|------|
| `sampler2D` | 2D 纹理 |
| `sampler3D` | 3D 体积纹理 |
| `samplerCube` | 立方体贴图（天空盒、环境反射） |
| `sampler2DArray` | 2D 纹理数组 |
| `sampler2DShadow` | 阴影贴图深度比较 |

**纹理过滤模式**（在 C++ 端设置）：

- `GL_NEAREST` / `GL_LINEAR`：最近邻 / 双线性过滤
- `GL_LINEAR_MIPMAP_LINEAR`：三线性过滤（最佳质量）
- 各向异性过滤：`GL_TEXTURE_MAX_ANISOTROPY_EXT`

#### 片段着色器的典型任务

1. **纹理采样与颜色混合**：漫反射贴图、法线贴图、高光贴图
2. **光照计算**：Lambert 漫反射、Blinn-Phong 高光、PBR BRDF
3. **雾效**：基于距离的线性/指数雾
4. **透明度与混合**：Alpha 测试、Alpha 混合、顺序无关透明（OIT）
5. **后处理效果**：色调映射、Gamma 校正、边缘检测

### 1.5 几何着色器（Geometry Shader）简介

几何着色器位于顶点着色器和光栅化器之间，可以**创建或销毁**几何图元。

**特点：**

- 输入：一个完整的图元（点、线、三角形）
- 输出：零个或多个图元
- 可以修改顶点属性

**典型应用：**

- **公告板（Billboard）渲染**：将点扩展为始终面向相机的四边形
- **线框渲染**：将三角形扩展为三条线
- **阴影体积（Shadow Volume）**：生成阴影几何体
- **点精灵（Point Sprite）**：粒子系统
- **几何体细分预览**：将三角形细分为更多三角形

**性能注意**：几何着色器在 GPU 上效率较低，因为它打破了 SIMD 执行模型的假设（输出量不确定导致线程分歧）。现代 GPU 上，许多几何着色器的功能可以通过**计算着色器**或**顶点着色器 + 间接绘制**更高效地实现。

### 1.5a 细分着色器（Tessellation Shader）简介

细分着色器是现代 GPU 的可选可编程阶段，由**外壳着色器（Hull Shader / TCS）**、**细分器（Tessellator）**和**域着色器（Domain Shader / TES）**组成。它允许根据视图距离或屏幕空间占有率动态增加几何细节。

**工作流程：**

1. **Hull Shader（TCS）**：决定每个 Patch（通常为四边形或三角形）细分成多少份
2. **Tessellator**：固定功能单元，根据 Hull Shader 的输出执行实际的细分
3. **Domain Shader（TES）**：计算细分后每个新顶点的位置（通常在参数化曲面上）

**典型应用：**

- **动态 LOD**：地形渲染中，远处地块使用低细分级别，近处高细分级别
- **曲面细分**：将低模通过置换贴图细分为高模
- **连续过渡**：实现 LOD 的平滑过渡，避免跳变

DirectX 11 引入的硬件曲面细分是地形和角色渲染的重要工具。例如，地形渲染中，近处地块使用 64x64 细分，远处使用 2x2 细分，实现细节随距离的连续变化。

### 1.6 计算着色器（Compute Shader）简介

计算着色器是独立的着色器阶段，不隶属于图形管线。它直接对 GPU 的计算资源进行编程，用于**通用 GPU 计算（GPGPU）**。

#### 执行模型

计算着色器以**工作组（Work Group）**为单位执行：

- 每个工作组包含三维排列的**本地调用（Local Invocation）**
- 多个工作组组成**全局调用空间（Global Invocation Space）**
- 工作组内可以通过 `shared` 内存进行高速数据共享

```glsl
layout(local_size_x = 256, local_size_y = 1, local_size_z = 1) in;

void main() {
    uint idx = gl_GlobalInvocationID.x;
    // 处理第 idx 个元素
}
```

#### 典型应用

| 应用场景 | 说明 |
|----------|------|
| 粒子系统 | 物理模拟、碰撞检测、生命周期管理 |
| 后处理 | 模糊、Bloom、SSAO、色调映射 |
| 图像处理 | 卷积、边缘检测、图像压缩 |
| 物理模拟 | 流体、布料、刚体 |
| AI 计算 | 神经网络推理、寻路、行为树 |
| 剔除与 LOD | 视锥剔除、遮挡剔除、细节层次选择 |

### 1.7 GLSL 与 HLSL 语法对比

GLSL（OpenGL Shading Language）和 HLSL（High-Level Shading Language，DirectX）是两大主流着色器语言，概念相通但语法不同。

#### 基本语法对比

| 概念 | GLSL | HLSL |
|------|------|------|
| 文件扩展名 | `.vert`, `.frag`, `.geom`, `.comp` | `.hlsl`, `.vs`, `.ps`, `.cs` |
| 入口函数 | `main()` | 任意名称，通过编译选项指定 |
| 顶点位置输出 | `gl_Position` | `SV_Position` 语义 |
| 颜色输出 | `out vec4 fragColor` | `float4 : SV_Target` |
| 深度输出 | `gl_FragDepth` | `float : SV_Depth` |
| 输入变量 | `in` | 函数参数 + 语义 |
| 输出变量 | `out` | 返回值结构体 + 语义 |

#### 数据类型对比

| GLSL | HLSL | 说明 |
|------|------|------|
| `vec2/3/4` | `float2/3/4` | 浮点向量 |
| `ivec2/3/4` | `int2/3/4` | 整数向量 |
| `uvec2/3/4` | `uint2/3/4` | 无符号整数向量 |
| `bvec2/3/4` | `bool2/3/4` | 布尔向量 |
| `mat2/3/4` | `float2x2/3x3/4x4` | 矩阵（注意行列顺序） |
| `mat3x4` | `float3x4` | 非方阵 |
| `sampler2D` | `Texture2D` + `SamplerState` | 2D 纹理（HLSL 分离纹理和采样器） |
| `samplerCube` | `TextureCube` | 立方体贴图 |

#### 矩阵乘法

```glsl
// GLSL: 列主序，* 运算符即矩阵乘法
vec4 clipPos = projection * view * model * vec4(position, 1.0);
// 等价于: P * V * M * v
```

```hlsl
// HLSL: 行主序（默认），mul 函数
float4 clipPos = mul(float4(position, 1.0), model);
clipPos = mul(clipPos, view);
clipPos = mul(clipPos, projection);
// 或者: mul(v, M * V * P)
```

**注意**：HLSL 默认行主序，GLSL 默认列主序。C++ 端传递矩阵时需要确保内存布局一致，或者在着色器中显式指定。

#### Uniform / Constant Buffer

```glsl
// GLSL: Uniform Block (UBO)
layout(std140, binding = 0) uniform TransformBlock {
    mat4 model;
    mat4 view;
    mat4 projection;
} ubo;
```

```hlsl
// HLSL: Constant Buffer (cbuffer)
cbuffer TransformBuffer : register(b0) {
    float4x4 model;
    float4x4 view;
    float4x4 projection;
};
```

#### 纹理采样

```glsl
// GLSL
uniform sampler2D uTexture;
vec4 color = texture(uTexture, uv);
// 或: textureLod(uTexture, uv, lod)
```

```hlsl
// HLSL
Texture2D gTexture : register(t0);
SamplerState gSampler : register(s0);
float4 color = gTexture.Sample(gSampler, uv);
// 或: gTexture.SampleLevel(gSampler, uv, lod)
```

#### 语义系统（Semantics）

HLSL 使用语义（Semantics）将着色器变量与管线阶段连接起来：

```hlsl
struct VSInput {
    float3 position : POSITION;
    float3 normal   : NORMAL;
    float2 texCoord : TEXCOORD0;
};

struct VSOutput {
    float4 position : SV_Position;
    float3 worldPos : TEXCOORD0;
    float3 normal   : TEXCOORD1;
    float2 texCoord : TEXCOORD2;
};
```

GLSL 使用 `in`/`out` 变量名匹配或 `layout(location = N)` 显式指定。

### 1.8 Uniform Buffer Object (UBO) 与 Shader Storage Buffer Object (SSBO)

#### UBO：Uniform Buffer Object

UBO 允许将多个 uniform 变量组织到一个缓冲区对象中，多个着色器程序可以共享同一个 UBO。

**优势：**

- 减少 uniform 设置的开销（一次性绑定整个缓冲区）
- 多个着色器共享相同的数据（如场景级变换矩阵）
- 数据量较大时性能更好

**内存布局（std140）：**

`std140` 是 OpenGL 定义的显式内存布局规则，确保 C++ 端和 GLSL 端的内存布局一致：

| 类型 | 对齐要求 | 大小 |
|------|----------|------|
| `float`, `int`, `uint`, `bool` | 4 字节 | 4 字节 |
| `vec2`, `ivec2` | 8 字节 | 8 字节 |
| `vec3`, `vec4`, `ivec3`, `ivec4` | 16 字节 | 16 字节（vec3 也占 16 字节！） |
| `mat4` | 16 字节 | 64 字节（4 个 vec4） |
| `mat3` | 16 字节 | 48 字节（3 个 vec4） |

**vec3 的陷阱**：`vec3` 在 `std140` 中占用 16 字节（不是 12 字节），后面会填充 4 字节。这经常导致 C++ 端结构体对齐错误。

```cpp
// C++ 端: 使用 alignas 确保对齐
struct alignas(16) TransformBlock {
    glm::mat4 model;
    glm::mat4 view;
    glm::mat4 projection;
};
// 总大小: 3 * 64 = 192 字节
```

```glsl
// GLSL 端
layout(std140, binding = 0) uniform TransformBlock {
    mat4 model;
    mat4 view;
    mat4 projection;
};
```

#### SSBO：Shader Storage Buffer Object

SSBO 是 OpenGL 4.3+ 引入的，比 UBO 更灵活：

| 特性 | UBO | SSBO |
|------|-----|------|
| 最大大小 | 通常 64KB | 通常 128MB+（GPU 内存大小） |
| 着色器可写 | 否（只读） | 是（读写） |
| 内存布局 | std140 / std430 | std430（更紧凑） |
| 原子操作 | 否 | 是 |
| 动态索引 | 有限 | 完全支持 |

SSBO 允许着色器写入数据，这在计算着色器中特别有用：

```glsl
layout(std430, binding = 1) buffer ParticleBuffer {
    vec4 positions[];  // 可变长度数组！
} particles;

void main() {
    uint idx = gl_GlobalInvocationID.x;
    particles.positions[idx] += vec4(velocity, 0.0);
}
```

### 1.9 着色器编译、链接与错误检查

OpenGL 着色器的编译和链接是一个多步骤过程，每一步都可能出错，必须添加错误检查。

**编译流程：**

1. 创建着色器对象：`glCreateShader`
2. 设置源码：`glShaderSource`
3. 编译：`glCompileShader`
4. 检查编译状态：`glGetShaderiv(GL_COMPILE_STATUS)`
5. 创建程序对象：`glCreateProgram`
6. 附加着色器：`glAttachShader`
7. 链接：`glLinkProgram`
8. 检查链接状态：`glGetProgramiv(GL_LINK_STATUS)`
9. 使用程序：`glUseProgram`

**常见错误：**

- **编译错误**：语法错误、类型不匹配、未定义变量、版本不匹配
- **链接错误**：输入/输出变量不匹配、uniform 未使用被优化掉、缺少 main 函数
- **运行时错误**：uniform 位置未找到、纹理单元未绑定、缓冲区未绑定

### 1.10 多个着色器程序的管理与切换

现代渲染引擎通常需要多个着色器程序：

- 基础着色（带/不带纹理）
- 法线贴图着色
- 骨骼动画着色
- 阴影贴图生成
- 延迟渲染 G-Buffer 填充
- 各种后处理效果

**管理策略：**

1. **Shader 类**：封装单个着色器程序的编译、链接、uniform 设置
2. **Shader Cache**：按材质/效果类型缓存着色器程序，避免重复编译
3. **Shader Variant**：通过宏定义（`#define`）生成同一着色器的多个变体
4. **Uniform Buffer**：将 per-frame / per-scene 数据放入 UBO，减少 uniform 切换

**切换开销**：`glUseProgram` 有一定开销，应尽量减少切换次数。现代引擎通常按着色器排序渲染队列，而不是按材质或距离。

### 1.11 从 CPU 传递数据到 GPU 的方式

| 方式 | API | 适用场景 | 性能特点 |
|------|-----|----------|----------|
| `glUniform*` | 单个 uniform | 少量频繁变化的数据 | 每个 uniform 一次 API 调用 |
| UBO | `glBindBufferBase` | 每帧/每对象的数据块 | 一次绑定，多个 uniform |
| SSBO | `glBindBufferBase` | 大量数据、着色器可写 | 大容量，支持原子操作 |
| VBO/VAO | `glBindVertexArray` | 顶点数据 | 初始化上传，每帧绑定 |
| 纹理 | `glBindTexture` | 图像数据、查找表 | GPU 缓存友好 |
| Shader Storage Image | `glBindImageTexture` | 随机读写图像 | 计算着色器专用 |
| Push Constants | `vkCmdPushConstants` | 每绘制调用的小数据 | Vulkan 特性，极低延迟 |

### 1.12 GPU 着色器执行模型深入

#### Warp / Wavefront 调度

现代 GPU 采用**单指令多线程（SIMT）**架构。以 NVIDIA 为例：

- **Warp**：32 个线程为一组，共享程序计数器
- **Warp Scheduler**：每个 SM（Streaming Multiprocessor）有多个 Warp Scheduler
- **零开销线程切换**：当一个 Warp 等待内存时，立即切换到另一个就绪 Warp

** occupancy（占用率）**：活跃 Warp 数 / 最大 Warp 数。高占用率可以更好地隐藏内存延迟。

影响占用率的因素：

- 寄存器使用量（每个线程用的寄存器越多，同时运行的 Warp 越少）
- 共享内存使用量
- 线程块大小

#### 分支发散（Branch Divergence）

当 Warp 内线程执行条件分支时：

```glsl
if (condition) {
    // 路径 A
} else {
    // 路径 B
}
```

GPU 必须**串行执行**两条路径：

1. 执行路径 A，路径 B 的线程被屏蔽（不写入结果）
2. 执行路径 B，路径 A 的线程被屏蔽

**优化策略：**

- 将条件一致的数据放在同一 Warp 中（如按材质排序）
- 使用 `step()`、`mix()` 等无分支函数替代简单条件
- 避免在热点代码中使用复杂分支

```glsl
// 有分支
if (x > 0.0) {
    color = red;
} else {
    color = blue;
}

// 无分支版本
color = mix(blue, red, step(0.0, x));
```

#### 内存层次结构

| 内存类型 | 速度 | 容量 | 生命周期 | 作用域 |
|----------|------|------|----------|--------|
| 寄存器 | 最快 | ~256KB/SM | 线程 | 单个线程 |
| 共享内存（L1） | 很快 | ~64KB/SM | 线程块 | 同一线程块 |
| L2 缓存 | 快 | ~4MB | 全局 | 所有线程 |
| 全局内存 | 慢 | GB 级 | 全局 | 所有线程 |
| 常量/纹理缓存 | 快（只读） | 64KB | 全局 | 所有线程（只读） |

### 1.13 计算着色器在 GPGPU 中的应用

计算着色器打开了通用 GPU 计算的大门。以下是游戏引擎中的典型应用：

#### GPU 粒子系统

传统粒子系统在 CPU 上更新位置、速度，然后上传到 GPU 渲染。使用计算着色器：

- 粒子数据存储在 SSBO 中
- 计算着色器每帧更新所有粒子的物理状态
- 零 CPU-GPU 数据传输（如果不需要 CPU 读取）

#### 后处理效果链

- 输入纹理 → 计算着色器（Bloom 提取）→ 中间纹理
- 中间纹理 → 计算着色器（高斯模糊）→ 模糊纹理
- 原图 + 模糊纹理 → 计算着色器（合并）→ 最终输出

#### 视锥剔除与遮挡剔除

- 将场景中所有物体的包围盒放入 SSBO
- 计算着色器并行测试每个包围盒是否在视锥内
- 输出可见物体列表，供后续渲染使用

#### 神经网络推理

- 将模型权重存储为纹理或缓冲区
- 使用计算着色器执行矩阵乘法
- 适用于轻量级 AI（如 NPC 行为决策、图像超分辨率）

---

## 2. 代码示例

以下是一个完整的 C++ OpenGL 程序，配合 GLSL 着色器，渲染一个带纹理映射和基本 Blinn-Phong 光照的立方体。

### 2.1 完整 C++ 程序

```cpp
// main.cpp
// 编译: g++ -std=c++17 main.cpp -o shader_demo -lglfw -lGLEW -lGL -lm

#include <GL/glew.h>
#include <GLFW/glfw3.h>
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <cmath>

#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"  // 需要 stb_image.h 头文件

// ---------------------------------------------------------------------------
// 工具函数：读取文件
// ---------------------------------------------------------------------------
std::string readFile(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        std::cerr << "Failed to open file: " << path << std::endl;
        return "";
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

// ---------------------------------------------------------------------------
// 工具函数：编译着色器并检查错误
// ---------------------------------------------------------------------------
GLuint compileShader(GLenum type, const std::string& source) {
    GLuint shader = glCreateShader(type);
    const char* src = source.c_str();
    glShaderSource(shader, 1, &src, nullptr);
    glCompileShader(shader);

    // 检查编译状态
    GLint success;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
    if (!success) {
        char infoLog[512];
        glGetShaderInfoLog(shader, 512, nullptr, infoLog);
        std::cerr << "Shader compilation failed:\n" << infoLog << std::endl;
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

// ---------------------------------------------------------------------------
// 工具函数：链接着色器程序并检查错误
// ---------------------------------------------------------------------------
GLuint createShaderProgram(const std::string& vertSource,
                           const std::string& fragSource) {
    GLuint vertShader = compileShader(GL_VERTEX_SHADER, vertSource);
    GLuint fragShader = compileShader(GL_FRAGMENT_SHADER, fragSource);
    if (vertShader == 0 || fragShader == 0) return 0;

    GLuint program = glCreateProgram();
    glAttachShader(program, vertShader);
    glAttachShader(program, fragShader);
    glLinkProgram(program);

    // 检查链接状态
    GLint success;
    glGetProgramiv(program, GL_LINK_STATUS, &success);
    if (!success) {
        char infoLog[512];
        glGetProgramInfoLog(program, 512, nullptr, infoLog);
        std::cerr << "Program linking failed:\n" << infoLog << std::endl;
        glDeleteProgram(program);
        program = 0;
    }

    // 链接完成后着色器对象可以删除（程序内部保留副本）
    glDeleteShader(vertShader);
    glDeleteShader(fragShader);

    return program;
}

// ---------------------------------------------------------------------------
// 工具函数：加载纹理
// ---------------------------------------------------------------------------
GLuint loadTexture(const std::string& path) {
    int width, height, channels;
    unsigned char* data = stbi_load(path.c_str(), &width, &height, &channels, 0);
    if (!data) {
        std::cerr << "Failed to load texture: " << path << std::endl;
        return 0;
    }

    GLuint texture;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);

    // 设置纹理参数
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

    // 上传纹理数据
    GLenum format = (channels == 4) ? GL_RGBA : GL_RGB;
    glTexImage2D(GL_TEXTURE_2D, 0, format, width, height, 0, format, GL_UNSIGNED_BYTE, data);
    glGenerateMipmap(GL_TEXTURE_2D);

    stbi_image_free(data);
    glBindTexture(GL_TEXTURE_2D, 0);
    return texture;
}

// ---------------------------------------------------------------------------
// 立方体顶点数据
// 每个顶点: position(3) + normal(3) + texCoord(2) = 8 floats
// ---------------------------------------------------------------------------
float cubeVertices[] = {
    // 背面 (z = -0.5)
    -0.5f, -0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.0f, 0.0f,
     0.5f, -0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  1.0f, 0.0f,
     0.5f,  0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  1.0f, 1.0f,
     0.5f,  0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  1.0f, 1.0f,
    -0.5f,  0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.0f, 1.0f,
    -0.5f, -0.5f, -0.5f,  0.0f,  0.0f, -1.0f,  0.0f, 0.0f,

    // 正面 (z = 0.5)
    -0.5f, -0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.0f, 0.0f,
     0.5f, -0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  1.0f, 0.0f,
     0.5f,  0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  1.0f, 1.0f,
     0.5f,  0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  1.0f, 1.0f,
    -0.5f,  0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.0f, 1.0f,
    -0.5f, -0.5f,  0.5f,  0.0f,  0.0f,  1.0f,  0.0f, 0.0f,

    // 左面 (x = -0.5)
    -0.5f,  0.5f,  0.5f, -1.0f,  0.0f,  0.0f,  1.0f, 0.0f,
    -0.5f,  0.5f, -0.5f, -1.0f,  0.0f,  0.0f,  1.0f, 1.0f,
    -0.5f, -0.5f, -0.5f, -1.0f,  0.0f,  0.0f,  0.0f, 1.0f,
    -0.5f, -0.5f, -0.5f, -1.0f,  0.0f,  0.0f,  0.0f, 1.0f,
    -0.5f, -0.5f,  0.5f, -1.0f,  0.0f,  0.0f,  0.0f, 0.0f,
    -0.5f,  0.5f,  0.5f, -1.0f,  0.0f,  0.0f,  1.0f, 0.0f,

    // 右面 (x = 0.5)
     0.5f,  0.5f,  0.5f,  1.0f,  0.0f,  0.0f,  1.0f, 0.0f,
     0.5f,  0.5f, -0.5f,  1.0f,  0.0f,  0.0f,  1.0f, 1.0f,
     0.5f, -0.5f, -0.5f,  1.0f,  0.0f,  0.0f,  0.0f, 1.0f,
     0.5f, -0.5f, -0.5f,  1.0f,  0.0f,  0.0f,  0.0f, 1.0f,
     0.5f, -0.5f,  0.5f,  1.0f,  0.0f,  0.0f,  0.0f, 0.0f,
     0.5f,  0.5f,  0.5f,  1.0f,  0.0f,  0.0f,  1.0f, 0.0f,

    // 底面 (y = -0.5)
    -0.5f, -0.5f, -0.5f,  0.0f, -1.0f,  0.0f,  0.0f, 1.0f,
     0.5f, -0.5f, -0.5f,  0.0f, -1.0f,  0.0f,  1.0f, 1.0f,
     0.5f, -0.5f,  0.5f,  0.0f, -1.0f,  0.0f,  1.0f, 0.0f,
     0.5f, -0.5f,  0.5f,  0.0f, -1.0f,  0.0f,  1.0f, 0.0f,
    -0.5f, -0.5f,  0.5f,  0.0f, -1.0f,  0.0f,  0.0f, 0.0f,
    -0.5f, -0.5f, -0.5f,  0.0f, -1.0f,  0.0f,  0.0f, 1.0f,

    // 顶面 (y = 0.5)
    -0.5f,  0.5f, -0.5f,  0.0f,  1.0f,  0.0f,  0.0f, 1.0f,
     0.5f,  0.5f, -0.5f,  0.0f,  1.0f,  0.0f,  1.0f, 1.0f,
     0.5f,  0.5f,  0.5f,  0.0f,  1.0f,  0.0f,  1.0f, 0.0f,
     0.5f,  0.5f,  0.5f,  0.0f,  1.0f,  0.0f,  1.0f, 0.0f,
    -0.5f,  0.5f,  0.5f,  0.0f,  1.0f,  0.0f,  0.0f, 0.0f,
    -0.5f,  0.5f, -0.5f,  0.0f,  1.0f,  0.0f,  0.0f, 1.0f,
};

// ---------------------------------------------------------------------------
// 顶点着色器源码
// ---------------------------------------------------------------------------
const char* vertexShaderSource = R"(
#version 330 core

// 顶点属性输入
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;

// 输出到片段着色器
out vec3 vWorldPos;
out vec3 vNormal;
out vec2 vTexCoord;

// UBO: 变换矩阵
layout(std140, binding = 0) uniform TransformBlock {
    mat4 model;
    mat4 view;
    mat4 projection;
} ubo;

void main() {
    // 计算世界空间位置
    vec4 worldPos = ubo.model * vec4(aPosition, 1.0);
    vWorldPos = worldPos.xyz;

    // 法线变换：使用逆转置矩阵处理非均匀缩放
    // 注意：这里为简化使用 model 矩阵，实际应使用 mat3(transpose(inverse(ubo.model)))
    vNormal = mat3(ubo.model) * aNormal;

    // 传递纹理坐标
    vTexCoord = aTexCoord;

    // 最终裁剪空间位置
    gl_Position = ubo.projection * ubo.view * worldPos;
}
)";

// ---------------------------------------------------------------------------
// 片段着色器源码
// ---------------------------------------------------------------------------
const char* fragmentShaderSource = R"(
#version 330 core

// 从顶点着色器输入
in vec3 vWorldPos;
in vec3 vNormal;
in vec2 vTexCoord;

// 输出颜色
out vec4 fragColor;

// 材质参数
uniform sampler2D uDiffuseMap;
uniform vec3 uCameraPos;

// 光源参数（使用 uniform，非 UBO，演示两种方式）
struct PointLight {
    vec3 position;
    vec3 color;
    float intensity;
};

uniform PointLight uLight;

// 材质属性
uniform float uShininess;
uniform vec3 uAmbientColor;

void main() {
    // 归一化法线（插值后长度可能不为1）
    vec3 normal = normalize(vNormal);

    // 从相机到片段的方向
    vec3 viewDir = normalize(uCameraPos - vWorldPos);

    // 从光源到片段的方向
    vec3 lightDir = normalize(uLight.position - vWorldPos);

    // 半程向量（Blinn-Phong）
    vec3 halfDir = normalize(lightDir + viewDir);

    // 采样漫反射纹理
    vec4 texColor = texture(uDiffuseMap, vTexCoord);

    // 环境光
    vec3 ambient = uAmbientColor * texColor.rgb;

    // 漫反射 (Lambert)
    float NdotL = max(dot(normal, lightDir), 0.0);
    vec3 diffuse = uLight.color * NdotL * texColor.rgb * uLight.intensity;

    // 高光 (Blinn-Phong)
    float NdotH = max(dot(normal, halfDir), 0.0);
    float specular = pow(NdotH, uShininess) * uLight.intensity;
    vec3 specularColor = uLight.color * specular;

    // 合并
    vec3 result = ambient + diffuse + specularColor;

    // Gamma 校正 (近似，使用 pow 2.2)
    result = pow(result, vec3(1.0 / 2.2));

    fragColor = vec4(result, texColor.a);
}
)";

// ---------------------------------------------------------------------------
// 主函数
// ---------------------------------------------------------------------------
int main() {
    // 初始化 GLFW
    if (!glfwInit()) {
        std::cerr << "Failed to initialize GLFW" << std::endl;
        return -1;
    }

    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);

    GLFWwindow* window = glfwCreateWindow(800, 600, "Shader Programming Demo", nullptr, nullptr);
    if (!window) {
        std::cerr << "Failed to create window" << std::endl;
        glfwTerminate();
        return -1;
    }
    glfwMakeContextCurrent(window);

    // 初始化 GLEW
    if (glewInit() != GLEW_OK) {
        std::cerr << "Failed to initialize GLEW" << std::endl;
        return -1;
    }

    // 启用深度测试
    glEnable(GL_DEPTH_TEST);

    // 编译链接着色器程序
    GLuint shaderProgram = createShaderProgram(vertexShaderSource, fragmentShaderSource);
    if (shaderProgram == 0) return -1;

    // 创建 VAO, VBO
    GLuint VAO, VBO;
    glGenVertexArrays(1, &VAO);
    glGenBuffers(1, &VBO);

    glBindVertexArray(VAO);

    glBindBuffer(GL_ARRAY_BUFFER, VBO);
    glBufferData(GL_ARRAY_BUFFER, sizeof(cubeVertices), cubeVertices, GL_STATIC_DRAW);

    // 位置属性 (location = 0)
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 8 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);

    // 法线属性 (location = 1)
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 8 * sizeof(float), (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);

    // 纹理坐标属性 (location = 2)
    glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, 8 * sizeof(float), (void*)(6 * sizeof(float)));
    glEnableVertexAttribArray(2);

    glBindVertexArray(0);

    // 创建 UBO
    GLuint ubo;
    glGenBuffers(1, &ubo);
    glBindBuffer(GL_UNIFORM_BUFFER, ubo);
    // 分配空间: 3 个 mat4 = 3 * 64 = 192 字节
    glBufferData(GL_UNIFORM_BUFFER, 192, nullptr, GL_STATIC_DRAW);

    // 绑定 UBO 到绑定点 0
    GLuint uboIndex = glGetUniformBlockIndex(shaderProgram, "TransformBlock");
    if (uboIndex != GL_INVALID_INDEX) {
        glUniformBlockBinding(shaderProgram, uboIndex, 0);
    }
    glBindBufferBase(GL_UNIFORM_BUFFER, 0, ubo);

    // 加载纹理（如果没有纹理文件，程序会使用默认白色）
    GLuint diffuseTexture = 0;
    // 尝试加载纹理，如果不存在则创建一个简单的棋盘格纹理
    {
        // 创建 64x64 棋盘格纹理
        const int texSize = 64;
        unsigned char checkerboard[texSize * texSize * 3];
        for (int y = 0; y < texSize; y++) {
            for (int x = 0; x < texSize; x++) {
                int check = ((x / 8) + (y / 8)) % 2;
                unsigned char c = check ? 200 : 80;
                checkerboard[(y * texSize + x) * 3 + 0] = c;
                checkerboard[(y * texSize + x) * 3 + 1] = c;
                checkerboard[(y * texSize + x) * 3 + 2] = c;
            }
        }
        glGenTextures(1, &diffuseTexture);
        glBindTexture(GL_TEXTURE_2D, diffuseTexture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, texSize, texSize, 0, GL_RGB, GL_UNSIGNED_BYTE, checkerboard);
        glGenerateMipmap(GL_TEXTURE_2D);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glBindTexture(GL_TEXTURE_2D, 0);
    }

    // 获取 uniform 位置
    glUseProgram(shaderProgram);
    GLint uDiffuseMapLoc    = glGetUniformLocation(shaderProgram, "uDiffuseMap");
    GLint uCameraPosLoc     = glGetUniformLocation(shaderProgram, "uCameraPos");
    GLint uLightPosLoc      = glGetUniformLocation(shaderProgram, "uLight.position");
    GLint uLightColorLoc    = glGetUniformLocation(shaderProgram, "uLight.color");
    GLint uLightIntensityLoc= glGetUniformLocation(shaderProgram, "uLight.intensity");
    GLint uShininessLoc     = glGetUniformLocation(shaderProgram, "uShininess");
    GLint uAmbientColorLoc  = glGetUniformLocation(shaderProgram, "uAmbientColor");

    // 设置光源参数（不变的部分）
    glUniform3f(uLightPosLoc, 2.0f, 3.0f, 2.0f);
    glUniform3f(uLightColorLoc, 1.0f, 0.95f, 0.8f);
    glUniform1f(uLightIntensityLoc, 1.0f);
    glUniform1f(uShininessLoc, 32.0f);
    glUniform3f(uAmbientColorLoc, 0.1f, 0.1f, 0.15f);

    // 相机参数
    glm::vec3 cameraPos(3.0f, 3.0f, 3.0f);
    glm::vec3 cameraTarget(0.0f, 0.0f, 0.0f);
    glm::vec3 cameraUp(0.0f, 1.0f, 0.0f);

    // 主循环
    while (!glfwWindowShouldClose(window)) {
        // 计算时间
        float time = (float)glfwGetTime();

        // 清屏
        glClearColor(0.1f, 0.1f, 0.15f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        // 使用着色器程序
        glUseProgram(shaderProgram);

        // 更新 UBO 数据
        glm::mat4 model = glm::mat4(1.0f);
        model = glm::rotate(model, time * 0.5f, glm::vec3(0.0f, 1.0f, 0.0f));
        model = glm::rotate(model, time * 0.3f, glm::vec3(1.0f, 0.0f, 0.0f));

        glm::mat4 view = glm::lookAt(cameraPos, cameraTarget, cameraUp);
        glm::mat4 projection = glm::perspective(
            glm::radians(45.0f),
            800.0f / 600.0f,
            0.1f,
            100.0f
        );

        glBindBuffer(GL_UNIFORM_BUFFER, ubo);
        glBufferSubData(GL_UNIFORM_BUFFER, 0, sizeof(glm::mat4), glm::value_ptr(model));
        glBufferSubData(GL_UNIFORM_BUFFER, 64, sizeof(glm::mat4), glm::value_ptr(view));
        glBufferSubData(GL_UNIFORM_BUFFER, 128, sizeof(glm::mat4), glm::value_ptr(projection));

        // 设置相机位置 uniform
        glUniform3f(uCameraPosLoc, cameraPos.x, cameraPos.y, cameraPos.z);

        // 绑定纹理到纹理单元 0
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, diffuseTexture);
        glUniform1i(uDiffuseMapLoc, 0);

        // 绘制立方体
        glBindVertexArray(VAO);
        glDrawArrays(GL_TRIANGLES, 0, 36);

        // 交换缓冲区
        glfwSwapBuffers(window);
        glfwPollEvents();
    }

    // 清理
    glDeleteVertexArrays(1, &VAO);
    glDeleteBuffers(1, &VBO);
    glDeleteBuffers(1, &ubo);
    glDeleteTextures(1, &diffuseTexture);
    glDeleteProgram(shaderProgram);

    glfwTerminate();
    return 0;
}
```

### 2.2 运行方式

**依赖：**

- OpenGL 3.3+ 支持
- GLFW3
- GLEW
- GLM（OpenGL Mathematics）
- stb_image.h（单头文件图像加载库）

**Linux/Ubuntu 编译：**

```bash
# 安装依赖
sudo apt-get install libglfw3-dev libglew-dev libglm-dev

# 下载 stb_image.h 到同一目录
wget https://raw.githubusercontent.com/nothings/stb/master/stb_image.h

# 编译
g++ -std=c++17 main.cpp -o shader_demo -lglfw -lGLEW -lGL -lm

# 运行
./shader_demo
```

**Windows (MinGW) 编译：**

```bash
g++ -std=c++17 main.cpp -o shader_demo.exe -lglfw3 -lglew32 -lopengl32
```

**macOS 编译：**

```bash
g++ -std=c++17 main.cpp -o shader_demo -lglfw -lglew -framework OpenGL
```

### 2.3 预期输出

程序运行后显示一个 800x600 的窗口，包含：

- 一个缓慢旋转的立方体
- 立方体表面有棋盘格纹理
- 基本 Blinn-Phong 光照效果（漫反射 + 高光 + 环境光）
- 光源位于场景右上方，发出暖白色光
- 背景为深蓝色

---

## 3. 练习

### 练习 1：添加第二个立方体（难度：低）

修改程序，在场景中渲染两个立方体：

- 第一个立方体在原点，缓慢旋转（已有）
- 第二个立方体位于 `(2.0, 0.0, 0.0)`，以不同速度反向旋转

**提示**：需要为第二个立方体使用不同的模型矩阵，但视图和投影矩阵可以共享同一个 UBO。考虑如何高效地更新 UBO 数据。

**思考**：如果场景中有 1000 个立方体，每次都更新 UBO 并调用 `glDrawArrays` 是否高效？查阅 **Instanced Rendering（实例化渲染）** 了解更高效的方案。

### 练习 2：实现法线贴图（Normal Mapping）（难度：中）

在片段着色器中添加法线贴图支持：

1. 添加切线（Tangent）和副切线（Bitangent）顶点属性
2. 在顶点着色器中构建 TBN（Tangent-Bitangent-Normal）矩阵
3. 从法线贴图采样切线空间法线
4. 使用 TBN 矩阵将法线转换到世界空间
5. 使用转换后的法线进行光照计算

**法线贴图生成**：可以使用工具如 [Awesome Bump](https://github.com/agmmnn/awesome-bump) 或在线生成器从灰度高度图生成法线贴图。

**关键代码片段（片段着色器）：**

```glsl
// TBN 矩阵从顶点着色器传入
in mat3 vTBN;

uniform sampler2D uNormalMap;

void main() {
    // 采样切线空间法线
    vec3 normalTS = texture(uNormalMap, vTexCoord).rgb;
    // 从 [0,1] 映射到 [-1,1]
    normalTS = normalTS * 2.0 - 1.0;
    // 转换到世界空间
    vec3 normalWS = normalize(vTBN * normalTS);
    // ... 使用 normalWS 进行光照计算
}
```

### 练习 3（可选）：计算着色器粒子系统（难度：高）

使用计算着色器实现一个简单的 GPU 粒子系统：

1. 创建一个 SSBO 存储粒子数据（位置、速度、生命周期）
2. 编写计算着色器，每帧更新粒子状态：
   - 应用重力
   - 更新位置
   - 减少生命周期
   - 生命周期结束后重置粒子
3. 使用 `glDrawArrays(GL_POINTS, ...)` 渲染粒子
4. 在顶点着色器中，将粒子位置扩展为公告板四边形

**进阶**：不使用几何着色器，而是在顶点着色器中使用**顶点拉取（Vertex Pulling）**技术，每个粒子由 6 个顶点组成，从 SSBO 读取位置并计算公告板顶点。

**计算着色器框架：**

```glsl
#version 430 core

struct Particle {
    vec4 position;  // xyz = position, w = size
    vec4 velocity;  // xyz = velocity, w = lifetime
};

layout(std430, binding = 0) buffer ParticleBuffer {
    Particle particles[];
};

layout(local_size_x = 256, local_size_y = 1, local_size_z = 1) in;

uniform float uDeltaTime;
uniform float uTotalTime;

void main() {
    uint idx = gl_GlobalInvocationID.x;
    if (idx >= particles.length()) return;

    Particle p = particles[idx];

    // 更新生命周期
    p.velocity.w -= uDeltaTime;

    if (p.velocity.w <= 0.0) {
        // 重置粒子
        p.position.xyz = vec3(0.0);
        p.velocity.xyz = vec3(
            sin(uTotalTime + idx) * 2.0,
            5.0 + fract(idx * 0.1) * 3.0,
            cos(uTotalTime + idx) * 2.0
        );
        p.velocity.w = 2.0 + fract(idx * 0.37) * 3.0;
    } else {
        // 应用重力
        p.velocity.y -= 9.8 * uDeltaTime;
        // 更新位置
        p.position.xyz += p.velocity.xyz * uDeltaTime;
    }

    particles[idx] = p;
}
```

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // 添加第二个立方体：使用不同的 model 矩阵 + 共享 UBO
> // 思路：创建两个 model 矩阵，每帧分别更新 UBO 后各发一次 DrawCall
>
> // 渲染循环中：
> while (!glfwWindowShouldClose(window)) {
>     float currentTime = glfwGetTime();
>     glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
>     glUseProgram(shaderProgram);
>
>     // ---- 更新共享的 View 和 Projection（一次性写入 UBO） ----
>     glm::mat4 view = camera.GetViewMatrix();
>     glm::mat4 projection = glm::perspective(glm::radians(45.0f), 800.0f/600.0f, 0.1f, 100.0f);
>
>     // ---- 立方体 1：原点，缓慢旋转 ----
>     {
>         glm::mat4 model1 = glm::mat4(1.0f);
>         model1 = glm::rotate(model1, currentTime * 0.5f, glm::vec3(0.5f, 1.0f, 0.0f));
>         // 更新整个 UBO（model + view + projection）
>         glBindBuffer(GL_UNIFORM_BUFFER, uboMatrices);
>         glBufferSubData(GL_UNIFORM_BUFFER, 0, sizeof(glm::mat4), glm::value_ptr(model1));
>         glBufferSubData(GL_UNIFORM_BUFFER, sizeof(glm::mat4), sizeof(glm::mat4), glm::value_ptr(view));
>         glBufferSubData(GL_UNIFORM_BUFFER, 2 * sizeof(glm::mat4), sizeof(glm::mat4), glm::value_ptr(projection));
>         glBindVertexArray(VAO);
>         glDrawArrays(GL_TRIANGLES, 0, 36);
>     }
>
>     // ---- 立方体 2：offset (2.0, 0, 0)，反向旋转 ----
>     {
>         glm::mat4 model2 = glm::mat4(1.0f);
>         model2 = glm::translate(model2, glm::vec3(2.0f, 0.0f, 0.0f));
>         model2 = glm::rotate(model2, currentTime * (-0.8f), glm::vec3(0.0f, 0.0f, 1.0f));
>         glBindBuffer(GL_UNIFORM_BUFFER, uboMatrices);
>         glBufferSubData(GL_UNIFORM_BUFFER, 0, sizeof(glm::mat4), glm::value_ptr(model2));
>         // view 和 projection 不变，无需重新上传（如果 UBO 绑定未变）
>         glBindVertexArray(VAO);
>         glDrawArrays(GL_TRIANGLES, 0, 36);
>     }
>
>     glfwSwapBuffers(window);
>     glfwPollEvents();
> }
> ```
>
> **思考题答案：** 对于 1000 个立方体，每次更新 UBO + 单独 `glDrawArrays` 是不可行的——1000 次 UBO 更新意味着 1000 次 CPU-GPU 同步，1000 次 Draw Call 意味着 1000 次驱动开销。解决方案是**实例化渲染（Instanced Rendering）**：将所有 1000 个 model 矩阵放入一个 SSBO 或实例化顶点缓冲，使用 `glDrawArraysInstanced` 一次提交所有实例。顶点着色器通过 `gl_InstanceID` 索引读取对应矩阵。另一个方向是 **GPU-Driven Rendering**：将绘制命令也放在 GPU buffer 中（`glMultiDrawElementsIndirect`），完全消除 CPU 端的逐物体循环。

> [!tip]- 练习 2 参考答案
> ```cpp
> // 法线贴图（Normal Mapping）—— 在片段着色器中用切线空间法线替代插值法线
>
> // ==== 顶点数据扩展：每个顶点增加切线 tangent (vec3) 和副切线 bitangent (vec3) ====
> // 为立方体的每个面计算 TBN 基向量
> // 前面（z=0.5）：Normal=(0,0,1), Tangent=(1,0,0), Bitangent=(0,1,0)
>
> // ==== 顶点着色器：计算 TBN 矩阵并传递到片段着色器 ====
> const char* vertexShaderWithTBN = R"(
> #version 330 core
> layout(location = 0) in vec3 aPosition;
> layout(location = 1) in vec3 aNormal;
> layout(location = 2) in vec2 aTexCoord;
> layout(location = 3) in vec3 aTangent;      // ★ 新增切线
> layout(location = 4) in vec3 aBitangent;    // ★ 新增副切线
>
> layout(std140, binding = 0) uniform TransformBlock {
>     mat4 model;
>     mat4 view;
>     mat4 projection;
> } ubo;
>
> out vec3 vWorldPos;
> out vec2 vTexCoord;
> out mat3 vTBN;  // ★ TBN 矩阵（切线空间 → 世界空间）
>
> void main() {
>     vec4 worldPos = ubo.model * vec4(aPosition, 1.0);
>     vWorldPos = worldPos.xyz;
>     vTexCoord = aTexCoord;
>
>     // 将 TBN 向量变换到世界空间
>     vec3 T = normalize(mat3(ubo.model) * aTangent);
>     vec3 B = normalize(mat3(ubo.model) * aBitangent);
>     vec3 N = normalize(mat3(ubo.model) * aNormal);
>
>     // 可选：Gram-Schmidt 正交化确保 TBN 正交（处理非均匀缩放）
>     T = normalize(T - dot(T, N) * N);
>     B = cross(N, T);  // 重新计算 B 确保正交
>
>     vTBN = mat3(T, B, N);
>     gl_Position = ubo.projection * ubo.view * worldPos;
> }
> )";
>
> // ==== 片段着色器：采样法线贴图，转换到世界空间后计算光照 ====
> const char* fragmentShaderWithNormalMap = R"(
> #version 330 core
> in vec3 vWorldPos;
> in vec2 vTexCoord;
> in mat3 vTBN;
>
> out vec4 fragColor;
>
> uniform sampler2D uDiffuseMap;
> uniform sampler2D uNormalMap;   // ★ 法线贴图
> uniform vec3 uCameraPos;
> uniform vec3 uLightPos;
> uniform vec3 uLightColor;
> uniform float uShininess;
>
> void main() {
>     // 1. 采样切线空间法线
>     vec3 normalTS = texture(uNormalMap, vTexCoord).rgb;
>     // 2. 从 [0,1] 映射到 [-1,1]
>     normalTS = normalize(normalTS * 2.0 - 1.0);
>     // 3. 通过 TBN 矩阵转换到世界空间
>     vec3 N = normalize(vTBN * normalTS);
>
>     // 4. 标准 Blinn-Phong 光照（使用世界空间法线 N）
>     vec3 L = normalize(uLightPos - vWorldPos);
>     vec3 V = normalize(uCameraPos - vWorldPos);
>     vec3 H = normalize(L + V);
>
>     float NdotL = max(dot(N, L), 0.0);
>     float NdotH = max(dot(N, H), 0.0);
>     float specular = pow(NdotH, uShininess);
>
>     vec3 albedo = texture(uDiffuseMap, vTexCoord).rgb;
>     vec3 ambient = albedo * 0.1;
>     vec3 diffuse = albedo * uLightColor * NdotL;
>     vec3 spec = vec3(0.5) * specular * NdotL;  // 仅在光照区域产生高光
>
>     vec3 result = ambient + diffuse + spec;
>     fragColor = vec4(result, 1.0);
> }
> )";
> ```
>
> **TBN 正交化的重要性：** 顶点着色器中的 Gram-Schmidt 过程确保 TBN 矩阵是正交的——这在模型有非均匀缩放（如 scale=(2,1,1)）时尤为关键。直接使用模型矩阵变换的 TBN 向量可能不再正交，导致法线方向错误和光照异常。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // GPU 粒子系统：计算着色器更新 + 顶点着色器公告板渲染
>
> // ==== 1. 粒子数据结构（GPU buffer） ====
> struct Particle {
>     glm::vec4 position;  // xyz = world pos, w = size
>     glm::vec4 velocity;  // xyz = velocity, w = lifetime remaining
>     glm::vec4 color;     // rgb = color, a = alpha
> };
>
> // ==== 2. 创建 SSBO ====
> GLuint particleSSBO;
> glGenBuffers(1, &particleSSBO);
> glBindBuffer(GL_SHADER_STORAGE_BUFFER, particleSSBO);
> glBufferData(GL_SHADER_STORAGE_BUFFER, MAX_PARTICLES * sizeof(Particle),
>              nullptr, GL_DYNAMIC_DRAW);
> glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, particleSSBO);
>
> // ==== 3. 计算着色器（更新粒子状态） ====
> const char* computeShaderSrc = R"(
> #version 430 core
> layout(local_size_x = 256) in;
>
> struct Particle {
>     vec4 position;
>     vec4 velocity;
>     vec4 color;
> };
>
> layout(std430, binding = 0) buffer ParticleBuffer {
>     Particle particles[];
> };
>
> uniform float uDeltaTime;
> uniform float uTotalTime;
>
> void main() {
>     uint idx = gl_GlobalInvocationID.x;
>     if (idx >= particles.length()) return;
>
>     Particle p = particles[idx];
>     p.velocity.w -= uDeltaTime;  // lifetime -= dt
>
>     if (p.velocity.w <= 0.0) {
>         // 重置粒子——从发射器位置重新生成
>         float offset = float(idx) * 1.618034f; // 黄金比例散开
>         p.position = vec4(sin(uTotalTime * 2.0 + offset) * 1.5, 0.0,
>                            cos(uTotalTime * 1.7 + offset) * 1.5, 1.0);
>         p.velocity = vec4(
>             (sin(offset * 7.0) * 0.3),       // vx: 随机水平
>             3.0 + sin(offset * 13.0) * 1.5,  // vy: 向上
>             (cos(offset * 7.0) * 0.3),       // vz
>             2.0 + sin(offset * 5.0) * 1.5    // lifetime: 2-3.5 秒
>         );
>         p.color = vec4(
>             0.5 + 0.5 * sin(offset * 3.0),
>             0.5 + 0.5 * sin(offset * 7.0 + 2.0),
>             0.5 + 0.5 * sin(offset * 11.0 + 4.0),
>             1.0
>         );
>     } else {
>         // 应用重力 + 更新位置
>         p.velocity.y -= 9.8 * uDeltaTime;
>         p.position.xyz += p.velocity.xyz * uDeltaTime;
>         // 生命周期衰减时透明度降低
>         p.color.a = smoothstep(0.0, 1.0, p.velocity.w / 2.5);
>         p.position.w = 0.05 + 0.03 * (p.velocity.w / 3.5); // 粒子大小随生命周期
>     }
>
>     particles[idx] = p;
> }
> )";
>
> // ==== 4. 每帧调度 ====
> // 在渲染循环中：
> //   glUseProgram(computeProgram);
> //   glUniform1f(glGetUniformLocation(computeProgram, "uDeltaTime"), deltaTime);
> //   glDispatchCompute((MAX_PARTICLES + 255) / 256, 1, 1);
> //   glMemoryBarrier(GL_VERTEX_ATTRIB_ARRAY_BARRIER_BIT); // ★ 确保 SSBO 写入对 VS 可见
> //
> //   glUseProgram(renderProgram);
> //   glBindVertexArray(particleVAO);  // 空 VAO，顶点从 SSBO 拉取
> //   glDrawArrays(GL_POINTS, 0, MAX_PARTICLES);
> //
> // 顶点着色器中从 SSBO 读取位置并生成公告板四边形：
> //   layout(std430, binding = 0) buffer ParticleBuffer { Particle particles[]; };
> //   // 使用 gl_VertexID / 6 获取粒子索引，用 gl_VertexID % 6 决定公告板的哪个角
> ```
>
> **关键设计决策：** GPU 粒子系统将全部模拟计算放在 GPU 上执行——`glDispatchCompute` 更新 SSBO，然后 `glDrawArrays` 直接读取 SSBO 渲染，**零 CPU-GPU 数据拷贝**。这与传统 CPU 粒子系统（CPU 更新 → `glBufferSubData` 上传 → GPU 渲染）相比，消除了一帧中最昂贵的瓶颈。计算着色器的 `local_size_x = 256` 对应 AMD GCN 的 4 个 wavefront（64 threads each），或 NVIDIA 的 8 个 warp（32 threads each）。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

### 官方文档

- [OpenGL 4.6 Core Profile Specification](https://www.khronos.org/registry/OpenGL/specs/gl/glspec46.core.pdf) — GLSL 语法和内置变量的权威参考
- [GLSL Reference Card](https://www.khronos.org/files/opengl45-quick-reference-card.pdf) — 快速查阅卡
- [HLSL Reference](https://docs.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-reference) — Microsoft HLSL 文档

### 书籍

- **《Real-Time Rendering, 4th Edition》** — Tomas Akenine-Moller 等 — 实时渲染的权威参考书，第 3 章详细讲解 GPU 架构
- **《OpenGL SuperBible, 7th Edition》** — Graham Sellers 等 — OpenGL 编程 comprehensive 指南
- **《Physically Based Rendering, 3rd Edition》** — Matt Pharr 等 — 离线渲染，但着色器数学同样适用

### 在线资源

- [LearnOpenGL - Shaders](https://learnopengl.com/Getting-started/Shaders) — 交互式 OpenGL 教程
- [The Book of Shaders](https://thebookofshaders.com/) — 专注于片段着色器的视觉教程
- [ShaderToy](https://www.shadertoy.com/) — 在线片段着色器编写和分享平台
- [GPU Gems 系列](https://developer.nvidia.com/gpugems/gpugems/part-i-natural-effects) — NVIDIA 的经典 GPU 编程技巧集

### 性能优化参考

- [NVIDIA GPU Programming Guide](https://developer.nvidia.com/gpugems/gpugems2/part-iii-high-quality-rendering/chapter-28-graphics-pipeline-performance) — GPU Gems 2 第 28 章
- [AMD GPUOpen](https://gpuopen.com/) — AMD 的开源 GPU 工具和优化指南
- [RenderDoc](https://renderdoc.org/) — 开源图形调试器，分析着色器性能和资源使用

### 相关章节

- 第 02 章：渲染管线基础 — 理解着色器在管线中的位置
- 第 04 章：纹理与采样 — 深入了解纹理过滤、mipmap、各向异性过滤
- 第 05 章：光照与阴影 — Phong/Blinn-Phong、PBR、阴影贴图
- 第 08 章：GPU 架构与优化 — 更深入的 GPU 微架构和性能分析

---

## 常见陷阱

### 陷阱 1：GLSL 版本不匹配

不同 OpenGL 版本对应不同的 GLSL 版本。如果 `#version` 声明与 OpenGL 上下文版本不匹配，可能导致编译错误或使用未定义行为。

| OpenGL 版本 | GLSL 版本 |
|-------------|-----------|
| 2.0 | 110 |
| 3.0 | 130 |
| 3.3 | 330 |
| 4.0 | 400 |
| 4.3 | 430 |
| 4.6 | 460 |

**建议**：始终显式声明 `#version`，并使用与 OpenGL 上下文匹配的版本。

### 陷阱 2：`std140` 布局中的 `vec3` 对齐

`vec3` 在 `std140` 中占用 16 字节，不是 12 字节。这经常导致 C++ 端结构体大小与 GLSL uniform block 不匹配。

```cpp
// 错误！大小为 12 + 4 + 12 = 28 字节
struct BadLayout {
    glm::vec3 position;  // 实际占用 16 字节
    float padding;       // 这里会被 GLSL 忽略
    glm::vec3 color;     // 实际占用 16 字节
};

// 正确！使用 vec4 或显式对齐
struct GoodLayout {
    glm::vec4 position;  // 16 字节
    glm::vec4 color;     // 16 字节
};
// 或者使用 alignas(16)
struct AlsoGood {
    alignas(16) glm::vec3 position;
    alignas(16) glm::vec3 color;
};
```

### 陷阱 3：法线变换忽略非均匀缩放

当模型矩阵包含非均匀缩放（如 `scale(1.0, 2.0, 1.0)`）时，直接使用 `mat3(model) * normal` 会导致法线不再垂直于表面。

**正确做法**：使用逆转置矩阵：

```glsl
mat3 normalMatrix = transpose(inverse(mat3(model)));
vec3 worldNormal = normalize(normalMatrix * aNormal);
```

**注意**：`inverse()` 在着色器中计算较昂贵。对于静态物体，应在 CPU 端计算并作为 uniform 传入。

### 陷阱 4：纹理单元与采样器绑定混淆

`glUniform1i(samplerLocation, N)` 中的 `N` 是**纹理单元索引**，不是纹理对象 ID。

```cpp
// 正确
glActiveTexture(GL_TEXTURE0);
glBindTexture(GL_TEXTURE_2D, textureID);
glUniform1i(glGetUniformLocation(program, "uTexture"), 0);  // 绑定到纹理单元 0

// 错误
// glUniform1i(glGetUniformLocation(program, "uTexture"), textureID);  // 这是错的！
```

### 陷阱 5：忘记 `glUseProgram` 就设置 uniform

`glUniform*` 调用作用于**当前绑定的着色器程序**。如果忘记先调用 `glUseProgram`，uniform 设置会失败或设置到错误的程序上。

```cpp
// 正确
glUseProgram(program);
glUniform3f(lightPosLoc, 1.0f, 2.0f, 3.0f);

// 错误
// glUniform3f(lightPosLoc, 1.0f, 2.0f, 3.0f);  // program 可能未绑定！
```

### 陷阱 6：未使用的 uniform 被编译器优化掉

如果着色器中声明了 uniform 但没有实际使用，编译器会将其优化掉。此时 `glGetUniformLocation` 返回 `-1`，这不是错误，但可能导致后续的 `glUniform*` 调用实际上没有作用。

**建议**：始终检查 uniform 位置是否为 `-1`，并在调试时留意。

### 陷阱 7：分支发散导致性能骤降

在片段着色器中使用动态分支（如基于纹理值的条件）可能导致严重的 warp 发散。

```glsl
// 性能较差：每个像素可能走不同分支
if (texture(uMask, uv).r > 0.5) {
    expensiveLighting();
} else {
    cheapLighting();
}

// 优化方案 1：使用 step/mix 消除分支
float mask = step(0.5, texture(uMask, uv).r);
vec3 color = mix(cheapLighting(), expensiveLighting(), mask);

// 优化方案 2：按材质分 draw call，确保同 warp 内分支一致
```

### 陷阱 8：计算着色器工作组大小设置不当

工作组大小（`local_size_x/y/z`）影响 GPU 占用率和性能。

- 太小（如 8）：无法充分利用 GPU 并行性
- 太大（如 1024）：每个工作组占用过多寄存器和共享内存，降低同时执行的工作组数
- **最佳实践**：使用 64、128 或 256 的倍数，与 GPU warp/wavefront 大小对齐（NVIDIA: 32, AMD: 64）

### 陷阱 9：忽略 Gamma 校正

直接在着色器中线性空间颜色输出到屏幕，会导致颜色看起来"发灰"或"不正确"。

**正确流程**：

1. 纹理（如漫反射贴图）通常在 sRGB 空间存储 — 使用 `GL_SRGB8` / `GL_SRGB8_ALPHA8` 格式让 OpenGL 自动转换到线性空间
2. 在线性空间中进行所有光照计算
3. 最终输出前进行 Gamma 校正：`pow(color, 1.0/2.2)` 或使用更精确的 sRGB 转换函数

```glsl
// 最终输出前的 Gamma 校正
vec3 linearToSRGB(vec3 linear) {
    return pow(linear, vec3(1.0 / 2.2));
    // 更精确的版本：
    // return mix(linear * 12.92, pow(linear, vec3(1.0/2.4)) * 1.055 - 0.055,
    //            step(vec3(0.0031308), linear));
}
```
