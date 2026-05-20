# 渲染引擎架构：多线程渲染、Render Graph 与可见性裁剪

> **所属计划**: [游戏引擎开发工程师](../plan.md)
> **预计耗时**: 8 小时
> **前置知识**: [06-渲染管线基础](06-rendering-pipeline.md), [07-着色器编程](07-shader-programming.md), [16-多线程与并发](16-multithreading-and-jobs.md)

---

## 概述

前面的章节聚焦于单线程环境下的渲染管线实现。然而，现代商业引擎的渲染架构必须充分利用多核 CPU 和异步 GPU 的特性，以在复杂场景下维持稳定帧率。本章从多线程渲染架构入手，逐步深入 Render Graph、Shader 系统、跨平台抽象和可见性裁剪等核心主题。

---

## 1. 多线程渲染架构

现代游戏引擎的渲染架构普遍采用**游戏线程（Game Thread, GT）**与**渲染线程（Render Thread, RT）**分离的设计。

### 游戏线程与渲染线程的分离原理

两个线程以**双缓冲**或**三缓冲**的方式协作。游戏线程负责第 N 帧的逻辑更新，同时渲染线程负责将第 N-1 帧已准备好的渲染命令提交给 GPU。

$$T_{frame} = \max(T_{game}, T_{render})$$

在理想情况下，总帧时间取两者中的较大值，而非两者之和。

**GT/RT/GPU 流水线时序：**

```
时间轴 ->

第 N-1 帧:  [GT: 逻辑更新 N-1] -> [RT: 生成命令 N-1] -> [GPU: 执行绘制 N-1]
第 N 帧:                              [GT: 逻辑更新 N]   -> [RT: 生成命令 N]   -> [GPU: 执行绘制 N]
第 N+1 帧:                                                 [GT: 逻辑更新 N+1] -> [RT: 生成命令 N+1] -> ...
```

游戏线程在第 N 帧进行逻辑更新的同时，GPU 正在执行第 N-1 帧的绘制命令（假设渲染线程延迟一帧）。这种流水线结构是现代引擎实现高帧率的核心基础。

### 渲染场景描述（Render Scene Description）

游戏线程与渲染线程之间传递的是**渲染场景描述**，而非直接传递渲染命令。这份数据结构包含：

- **可见物体列表**：裁剪后的 Mesh 实例、世界变换、材质引用、LOD 级别
- **光源数据**：位置、方向、颜色、强度、阴影参数
- **相机参数**：视图矩阵、投影矩阵、近远裁剪面、FOV
- **后处理设置**：曝光、色调映射、Bloom、SSAO 等参数
- **渲染特性开关**：阴影、反射、体积光等

渲染场景描述通常存储在**环形缓冲区（Ring Buffer）**中，以避免每帧分配内存。游戏线程写入第 N 帧的数据，渲染线程读取第 N-1 帧的数据，两者通过原子操作同步读写指针。环形缓冲区的大小通常为三帧（对应 Triple Buffering），确保游戏线程始终有空间写入而不会被渲染线程阻塞。

---

## 2. RHI（Render Hardware Interface）抽象层

RHI 是渲染架构中的关键抽象层，屏蔽了底层图形 API（DirectX 12、Vulkan、Metal 等）的差异。

### RHI 核心设计原则

1. **最小抽象**：只抽象 GPU 资源创建、状态设置和命令提交，不抽象渲染算法
2. **显式资源管理**：采用显式的创建/销毁模式，上层代码负责生命周期
3. **命令列表模型**：提供 Command List 接口，渲染线程将命令录制到列表中批量提交
4. **同步原语**：提供 Fence、Semaphore 等同步原语

### 关键设计决策

**显式资源屏障（Explicit Resource Barrier）**：在 DX12 和 Vulkan 中，资源在同一帧内可能处于不同状态——例如一张纹理可能先作为渲染目标写入，然后作为着色器资源读取。RHI 层通过 `ResourceBarrier` 接口暴露这种状态转换，上层代码（如 Render Graph）负责在正确的位置插入屏障。这种显式控制虽然增加了代码复杂度，但允许引擎精确控制 GPU 的同步点，消除不必要的等待。

**DrawIndexedIndirect**：这是 GPU-Driven 渲染的核心 API，它允许 GPU 直接从缓冲区读取绘制参数（索引数、实例数等），而无需 CPU 介入。在实现遮挡剔除、GPU 粒子系统等高级特性时，这个接口至关重要。

**命令列表复用**：现代图形 API 允许命令列表在提交后被重置（`Reset`）并复用其底层内存分配，这避免了每帧创建和销毁命令列表的开销。渲染线程可以维护一个**命令列表池（Command List Pool）**，从池中取出空闲列表录制命令，提交后归还池中重置。

### RHI 核心接口

```cpp
namespace rhi {

enum class ERHIBackend : uint8_t {
    Vulkan, DirectX12, Metal, OpenGL
};

enum class EFormat : uint8_t {
    R8G8B8A8_UNORM, B8G8R8A8_UNORM,
    R32G32B32A32_FLOAT, R16G16B16A16_FLOAT,
    D32_FLOAT, D24_UNORM_S8_UINT,
    R11G11B10_FLOAT
};

struct TextureDesc {
    uint32_t width = 1, height = 1, depth = 1;
    uint32_t mipLevels = 1, arraySize = 1;
    EFormat format = EFormat::R8G8B8A8_UNORM;
    uint32_t sampleCount = 1;
    uint32_t usageFlags = 0;
    std::string debugName;
};

struct BufferDesc {
    uint32_t sizeInBytes = 0, strideInBytes = 0;
    uint32_t usageFlags = 0;
    std::string debugName;
};

struct RenderPassAttachment {
    IRHITexture* texture = nullptr;
    uint8_t loadOp = 0, storeOp = 0;
    float clearColor[4] = {0};
};

struct RenderPassDesc {
    std::vector<RenderPassAttachment> colorAttachments;
    RenderPassAttachment depthStencilAttachment;
};

// RHI 设备接口
class IRHIDevice {
public:
    virtual ~IRHIDevice() = default;
    virtual std::unique_ptr<IRHITexture> CreateTexture(const TextureDesc& desc) = 0;
    virtual std::unique_ptr<IRHIBuffer> CreateBuffer(const BufferDesc& desc) = 0;
    virtual std::unique_ptr<IRHIPipelineState> CreateGraphicsPipelineState(
        const GraphicsPipelineDesc& desc) = 0;
    virtual std::unique_ptr<IRHIFence> CreateFence() = 0;
    virtual std::unique_ptr<IRHICommandList> CreateCommandList() = 0;
    virtual void WaitIdle() = 0;
};

// 命令列表接口
class IRHICommandList {
public:
    virtual ~IRHICommandList() = default;
    virtual void Begin() = 0;
    virtual void End() = 0;
    virtual void Reset() = 0;
    virtual void BeginRenderPass(const RenderPassDesc& desc) = 0;
    virtual void EndRenderPass() = 0;
    virtual void SetPipelineState(IRHIPipelineState* pipeline) = 0;
    virtual void SetViewport(const Viewport& viewport) = 0;
    virtual void SetScissorRect(const ScissorRect& scissor) = 0;
    virtual void SetVertexBuffer(uint32_t slot, IRHIBuffer* buffer, uint32_t offset) = 0;
    virtual void SetIndexBuffer(IRHIBuffer* buffer, uint32_t offset, bool b32Bit) = 0;
    virtual void DrawIndexed(uint32_t indexCount, uint32_t instanceCount,
                             uint32_t firstIndex, int32_t vertexOffset,
                             uint32_t firstInstance) = 0;
    virtual void DrawIndexedIndirect(IRHIBuffer* argsBuffer, uint32_t argsOffset) = 0;
    virtual void ResourceBarrier(IRHIResource* resource,
                                  uint32_t beforeState, uint32_t afterState) = 0;
    virtual void Dispatch(uint32_t groupX, uint32_t groupY, uint32_t groupZ) = 0;
};

// Fence - CPU/GPU 同步
class IRHIFence {
public:
    virtual ~IRHIFence() = default;
    virtual void SignalFromGPU(IRHICommandList* cmdList, uint64_t value) = 0;
    virtual void WaitOnGPU(IRHICommandList* cmdList, uint64_t value) = 0;
    virtual void WaitOnCPU(uint64_t value) = 0;
};

std::unique_ptr<IRHIDevice> CreateRHIDevice(ERHIBackend backend, void* platformWindow);

} // namespace rhi
```

### 多线程命令录制

在大型场景中，渲染命令数量可能非常庞大。现代引擎采用**多线程命令录制**：

- 渲染线程作为主线程，生成渲染场景描述和确定管线结构
- 将每个 Render Pass 的录制任务分发到工作线程池并行执行
- 每个工作线程录制自己的命令列表
- 渲染线程合并命令列表并提交给 GPU

---

## 3. 渲染图/帧图（Render Graph）

Render Graph 是现代游戏引擎渲染架构中的革命性设计，最早由 Yuriy O'Donnell 在 GDC 2017 系统提出。它将渲染管线从命令式转变为声明式。

### 核心思想

Render Graph 将一帧渲染过程抽象为**有向无环图（DAG）**：

- **节点（Node）**：代表 Render Pass，包含执行回调
- **边（Edge）**：代表资源依赖关系
- **资源（Resource）**：纹理、缓冲区等，由 Render Graph 管理生命周期

执行分两个阶段：
1. **构建阶段**：声明性注册所有 Pass 和资源依赖
2. **编译与执行阶段**：分析 DAG，执行依赖排序、资源分配、屏障插入

### 工程优势

- **自动资源管理**：中间资源自动分配和回收。引擎可以根据实际需求决定这些纹理的格式、尺寸，甚至可以将生命周期不重叠的资源复用到同一块 GPU 内存中（内存别名，Memory Aliasing），这可以显著减少中间渲染资源的总内存占用（30-50% 节省）。
- **自动屏障插入**：根据 Pass 间读写关系自动计算并插入必要的资源屏障（Resource Barrier），避免了手动管理屏障的繁琐和易错。
- **渲染管线可视化**：由于整个渲染管线以图的形式显式描述，引擎可以轻松生成渲染管线的可视化表示（如 RenderDoc 的截图），极大地方便了调试和优化。
- **跨平台优化**：在移动端 Tiled GPU 上合并多个小 Pass，以减少 Tile 内存的往返传输。

### Render Graph 实现核心

```cpp
namespace rendergraph {

enum class ERGAccess : uint8_t { None, Read, Write, ReadWrite };

template<typename T>
class RGHandle {
    uint32_t m_id = 0xFFFFFFFF;
public:
    explicit RGHandle(uint32_t id) : m_id(id) {}
    bool IsValid() const { return m_id != 0xFFFFFFFF; }
    uint32_t GetID() const { return m_id; }
};

using RGTextureHandle = RGHandle<class RGTexture>;

struct RGTextureDesc {
    uint32_t width = 1, height = 1, mipLevels = 1;
    uint32_t format = 0, usageFlags = 0;
    std::string debugName;
};

class RenderPassBuilder {
public:
    void Read(RGTextureHandle handle, ERGAccess access = ERGAccess::Read);
    void Write(RGTextureHandle handle, ERGAccess access = ERGAccess::Write);
    void SetRenderTarget(uint32_t slot, RGTextureHandle handle);
    void SetDepthStencil(RGTextureHandle handle);
};

class RGPass {
public:
    using SetupFunc = std::function<void(RenderPassBuilder&)>;
    using ExecuteFunc = std::function<void(rhi::IRHICommandList*)>;

    RGPass(const std::string& name, SetupFunc setup, ExecuteFunc execute);
    void Setup(RenderPassBuilder& builder);
    void Execute(rhi::IRHICommandList* cmdList);
};

class RenderGraph {
public:
    RGTextureHandle CreateTexture(const RGTextureDesc& desc);
    RGTextureHandle ImportTexture(const std::string& name, rhi::IRHITexture* external);

    void AddPass(const std::string& name,
                 RGPass::SetupFunc setup,
                 RGPass::ExecuteFunc execute);

    void Compile();  // 分析依赖、分配资源、计算执行顺序
    void Execute(rhi::IRHIDevice* device);

private:
    void BuildDependencyGraph();
    bool TopologicalSort();
    void AllocateResources();
    void InsertResourceBarriers();

    std::vector<std::unique_ptr<RGPass>> m_passes;
    std::vector<RGTextureDesc> m_textureDescriptions;
    std::vector<RGPass*> m_executionOrder;
};

} // namespace rendergraph
```

### 延迟渲染管线示例

```cpp
void RenderDeferredFrame(RenderGraph& graph, const SceneView& view) {
    // 声明中间资源
    auto gbufferBaseColor = graph.CreateTexture({view.width, view.height, 1, 0, 0, "GBuffer_BaseColor"});
    auto gbufferNormal = graph.CreateTexture({view.width, view.height, 1, R16G16B16A16_FLOAT, 0, "GBuffer_Normal"});
    auto sceneDepth = graph.CreateTexture({view.width, view.height, 1, D32_FLOAT, 0, "SceneDepth"});
    auto lightingBuffer = graph.CreateTexture({view.width, view.height, 1, R16G16B16A16_FLOAT, 0, "Lighting"});

    // GBuffer Pass
    graph.AddPass("GBuffer",
        [&](RenderPassBuilder& builder) {
            builder.SetRenderTarget(0, gbufferBaseColor);
            builder.SetRenderTarget(1, gbufferNormal);
            builder.SetDepthStencil(sceneDepth);
        },
        [&](rhi::IRHICommandList* cmd) {
            // 绑定 GBuffer 管线，绘制不透明物体
        });

    // SSAO Pass
    auto aoTexture = graph.CreateTexture({view.width, view.height, 1, R8_UNORM, 0, "SSAO"});
    graph.AddPass("SSAO",
        [&](RenderPassBuilder& builder) {
            builder.Read(sceneDepth);
            builder.Read(gbufferNormal);
            builder.Write(aoTexture);
        },
        [&](rhi::IRHICommandList* cmd) {
            // 执行 SSAO 计算着色器
        });

    // 延迟光照 Pass
    graph.AddPass("DeferredLighting",
        [&](RenderPassBuilder& builder) {
            builder.Read(gbufferBaseColor);
            builder.Read(gbufferNormal);
            builder.Read(sceneDepth);
            builder.Read(aoTexture);
            builder.Write(lightingBuffer);
        },
        [&](rhi::IRHICommandList* cmd) {
            // 对每个光源执行延迟光照
        });

    // 后处理 Pass
    auto backBuffer = graph.ImportTexture("BackBuffer", GetSwapChainBackBuffer());
    graph.AddPass("Tonemap",
        [&](RenderPassBuilder& builder) {
            builder.Read(lightingBuffer);
            builder.Write(backBuffer);
        },
        [&](rhi::IRHICommandList* cmd) {
            // 色调映射 + Gamma 校正
        });
}
```

---

## 4. Shader 系统

### Shader 变体（Variant）管理

同一套 Shader 源码需要生成大量变体来适应不同渲染需求：

- 是否使用法线贴图 / 高光贴图
- 是否启用 Alpha Clip / 骨骼动画
- 光照模型选择（Blinn-Phong / GGX）
- 渲染路径（前向 / 延迟）
- 阴影类型（主光源 / 级联 / 点光源）

这些选项的组合可能产生数百甚至数千个 Shader 变体。直接手写每个变体不现实，因此引擎通常采用**条件编译 + 自动变体生成**的方案——在 Shader 源码中使用 `#if` / `#ifdef` 根据编译器宏选择代码路径，编译时根据材质设置自动确定需要哪些变体。

**控制变体爆炸的策略**：

1. **变体剥离（Variant Stripping）**：打包时剔除未使用的变体。例如，如果游戏从不在移动平台上使用某个复杂 Shader，则该平台的对应变体可以被移除。
2. **按需编译（On-demand Compilation）**：只在实际需要某个变体时才编译它，而不是预先编译所有可能组合。这避免了启动时的长时间编译等待。
3. **变体缓存**：将编译好的变体缓存到磁盘，下次启动时直接加载，避免重复编译。缓存键通常由 Shader 源码哈希 + 变体宏组合确定。

### Shader 热重载（Hot Reload）

实现流程：
1. **文件监控**：后台线程监控 Shader 源码文件的修改时间戳
2. **变更检测**：检测到修改时标记对应 Shader 为"脏"
3. **异步编译**：工作线程上重新编译受影响变体
4. **运行时替换**：更新材质引用的 Shader 对象

关键机制：材质持有 Shader 引用句柄而非直接指针，编译完成后更新句柄背后的对象。

### Shader 节点编辑器

节点编辑器核心是一个**节点图到 Shader 源码的编译器**：

1. **节点定义系统**：每个节点对应一个 Shader 函数或操作
2. **图验证器**：检查类型匹配、循环依赖
3. **代码生成器**：从数据流图到命令式代码的转换（拓扑排序遍历）
4. **预览系统**：简化渲染场景实时预览

---

## 5. 跨平台渲染抽象

### 平台特定优化策略

| 平台类型 | 代表硬件/API | GPU 架构特点 | 优化策略 |
|---------|------------|------------|---------|
| 桌面独显 | NVIDIA RTX / AMD Radeon (DX12/Vulkan) | 大带宽显存、大量计算单元、Tile-based 光追核心 | 最大化并行度、充分利用异步计算队列、DLSS/FSR 升频 |
| 游戏主机 | PS5 (RDNA2) / Xbox Series X (DX12) | 统一内存架构(UMA)、硬件加速光线追踪、高速 SSD | 减少 CPU-GPU 数据传输、利用硬件特性（如 PS5 的 Geometry Engine）|
| 移动 GPU | Apple M系列 / Qualcomm Adreno / ARM Mali (Metal/Vulkan) | Tiled Deferred 渲染架构、带宽敏感、计算资源有限 | 减少 Render Pass 数量、避免 TBDR 架构中的"全屏三角形"陷阱、ASTC/ETC 压缩 |
| 集成 GPU | Intel Iris Xe | 共享系统内存、计算单元较少 | 降低分辨率、简化着色器、优先保证带宽效率 |

### 各平台优化详解

**桌面独立 GPU**：优化的重点是最大化 GPU 的并行计算能力。这包括利用异步计算队列（Async Compute）并行执行图形和计算工作负载（例如，在光栅化 GBuffer 的同时，使用计算着色器执行 SSAO 或 Bloom），以及通过使用 DLSS（NVIDIA）或 FSR（AMD）等升频技术来降低渲染分辨率。

**游戏主机**：统一内存架构（UMA）意味着 CPU 和 GPU 共享同一块物理内存，不存在 PCIe 传输瓶颈。这为引擎架构带来了新的可能性——例如，GPU 可以直接访问由 CPU 生成的数据结构（如 GPU-Driven 渲染中的间接绘制缓冲区），而无需显式的上传操作。此外，主机的硬件特性通常是公开且有文档的，引擎可以利用这些特性实现桌面平台无法达到的优化（如 PS5 的 Primitive Shader 和 Mesh Shader 等几何处理流水线）。

**移动 GPU**：绝大多数移动 GPU 采用 **Tiled Deferred Rendering（TBDR）** 架构（如 PowerVR 的 Tile-Based Deferred Rendering、ARM Mali 的 Tile-Based Rendering）。在这种架构下，GPU 将屏幕划分为小块（Tile），对每个 Tile 依次执行几何处理、光栅化和像素着色。Pass 之间的全屏读写操作会导致 Tile 内存与主内存之间的数据传输（称为"Resolve"操作），这在移动平台上是非常消耗带宽的。

针对移动平台的优化策略：

1. **Render Pass 合并**：将多个小的 Render Pass 合并为一个大的 Pass，避免中间结果的 Resolve 操作。例如，将基础颜色、法线和材质的渲染合并到同一个 GBuffer Pass 中。
2. **避免 Shader 中的分支**：移动 GPU 的线程调度器对动态分支（dynamic branch）的处理效率通常低于桌面 GPU。尽量使用静态分支（编译时确定的 `#ifdef`）或将分支转换为 lerp/mix 操作。
3. **使用 ASTC/ETC 纹理压缩**：移动平台的显存带宽有限，使用硬件支持的压缩纹理格式（ASTC 是目前的最佳选择）可以显著减少带宽占用。
4. **MSAA 解析优化**：在 TBDR 架构上，MSAA 的解析可以在 Tile 内存中完成，不产生额外的带宽开销，这使得 MSAA 在移动平台上的成本远低于桌面平台。

### 图形 API 切换策略

在 RHI 层实现图形 API 的切换能力，需要仔细设计抽象层次。过于底层的抽象会失去平台优化的空间，过于高层的抽象则可能导致某些平台特性无法使用。

现代引擎通常采用**分层策略**：核心渲染算法（如延迟渲染、后处理效果）使用统一的 RHI 接口编写，而平台特定的优化通过**平台后端（Platform Backend）**的特化实现来完成。例如，Unreal Engine 的 RHI 层在 `FRHICommandList` 上提供统一的接口，但每个平台（D3D12RHI、VulkanRHI、MetalRHI）有自己的实现，可以在不修改上层代码的情况下注入平台特定的优化。

---

## 6. 可见性裁剪系统

可见性裁剪是渲染引擎中最重要的性能优化系统之一，目标是以最小开销确定哪些物体对当前相机可见。

### 视锥裁剪（Frustum Culling）

AABB 与视锥的相交测试使用**分离轴定理**的特例。

**快速拒绝测试**：

$$r = e_x |N_x| + e_y |N_y| + e_z |N_z|$$

$$s = N \cdot C + d$$

- $s + r < 0$：AABB 完全在平面负侧（外部）
- $s - r > 0$：AABB 完全在平面正侧（内部）
- 否则：相交

### 遮挡裁剪（Occlusion Culling）

| 方法 | 原理 | 优点 | 缺点 |
|:-----|:-----|:-----|:-----|
| 硬件遮挡查询 | GPU 查询包围盒是否通过深度测试 | 精确 | GPU-CPU 同步延迟 |
| 软件光栅化 | CPU 维护低分辨率深度缓冲 | 无同步延迟 | 增加 CPU 开销 |
| 层次 Z 缓冲（Hi-Z） | 层级化深度缓冲区逐级测试 | 结合两者优点 | 实现复杂 |

### 层次裁剪结构（BVH）

**包围体层次结构（BVH）** 是一棵二叉树，每个内部节点存储包围其子节点的包围盒。

```cpp
struct AABB {
    float minX, minY, minZ, maxX, maxY, maxZ;

    float SurfaceArea() const {
        float dx = maxX - minX, dy = maxY - minY, dz = maxZ - minZ;
        return 2.0f * (dx * dy + dy * dz + dz * dx);
    }

    // 与平面相交测试：-1=外部, 0=相交, 1=内部
    int ClassifyAgainstPlane(const float plane[4]) const {
        float cx = (minX + maxX) * 0.5f;
        float cy = (minY + maxY) * 0.5f;
        float cz = (minZ + maxZ) * 0.5f;
        float ex = (maxX - minX) * 0.5f;
        float ey = (maxY - minY) * 0.5f;
        float ez = (maxZ - minZ) * 0.5f;

        float r = ex * std::abs(plane[0]) + ey * std::abs(plane[1]) + ez * std::abs(plane[2]);
        float s = plane[0]*cx + plane[1]*cy + plane[2]*cz + plane[3];

        if (s + r < 0.0f) return -1;
        if (s - r > 0.0f) return 1;
        return 0;
    }
};

struct BVHNode {
    AABB bounds;
    uint32_t leftChild = 0xFFFFFFFF;
    uint32_t rightChild = 0xFFFFFFFF;
    uint32_t objectStart = 0, objectCount = 0;
    bool IsLeaf() const { return leftChild == 0xFFFFFFFF; }
};

class BVH {
public:
    void Build(std::vector<BVHObject>&& objects);
    void FrustumCull(const float frustumPlanes[6][4],
                     std::vector<uint32_t>& outVisibleObjects) const;

private:
    uint32_t BuildRecursive(uint32_t start, uint32_t end);
    void FrustumCullNode(uint32_t nodeIdx, const float frustumPlanes[6][4],
                         std::vector<uint32_t>& outVisibleObjects) const;

    std::vector<BVHNode> m_nodes;
    std::vector<BVHObject> m_objects;
    uint32_t m_rootNode = 0xFFFFFFFF;
    static constexpr uint32_t kMaxLeafObjects = 8;
};
```

**SAH 分割策略**：选择使左右子树包围盒表面积之和最小的分割轴和位置。

对于大型开放世界场景，采用**多层次裁剪策略**：顶层四叉树管理地形块，中层 BVH 管理静态物体，底层对动态物体使用 AABB 列表。现代光线追踪 API（DXR、Vulkan Ray Tracing）进一步采用 **TLAS/BLAS 双层结构**——BLAS 是每个 Mesh 的静态加速结构，TLAS 是每帧重建的实例层，动态物体只需更新实例变换而不必重建整个加速结构。

---

## 总结

本章深入探讨了现代渲染引擎的架构设计：

1. **多线程渲染**：GT/RT 分离通过双缓冲隐藏延迟，RHI 抽象层提供跨平台统一的资源管理和命令提交接口
2. **Render Graph**：声明式渲染管线组织方式，自动管理资源生命周期和同步屏障，是现代引擎渲染系统的核心架构模式
3. **Shader 系统**：变体管理、热重载和节点编辑器构成了工业级 Shader 管线的基础
4. **跨平台抽象**：针对不同 GPU 架构（桌面独显、主机、移动端）采用差异化的优化策略
5. **可见性裁剪**：视锥裁剪 + 遮挡裁剪 + BVH 层次结构的多层裁剪策略，是维持大规模场景渲染效率的关键

掌握这些架构知识，你就具备了设计和实现一个现代多线程渲染引擎的能力。

### 与高级渲染技术的衔接

渲染引擎架构是高级渲染技术的载体。本章讨论的 Render Graph、RHI 抽象和多线程架构，为以下高级技术提供了运行基础：

- **PBR 渲染管线**（参见 PBR 材质系统教程）：通过 Render Graph 组织 GBuffer Pass、光照 Pass 和后处理 Pass
- **屏幕空间效果**（SSAO、SSR）：作为独立的 Render Graph Pass，读取深度/法线缓冲，输出效果纹理
- **后处理管线**（Bloom、色调映射、色彩分级）：由 Render Graph 自动管理中间纹理和依赖顺序
- **实时光线追踪**（DXR/Vulkan RT）：RHI 层暴露加速结构（BLAS/TLAS）和光线追踪管线接口
- **GPU-Driven Rendering**：通过 RHI 的 `DrawIndexedIndirect` 接口和计算着色器实现 GPU 端的剔除和 LOD 选择
- **虚拟纹理**：RHI 层提供稀疏纹理（Sparse Texture）和内存映射接口，上层实现页表管理和纹理流送

理解架构与具体渲染技术之间的关系，有助于在实际开发中做出正确的设计决策——例如，何时使用 Render Graph 的自动资源管理，何时需要手动控制资源生命周期以获得最大性能。

---

## 延伸阅读

- **GDC 2017: FrameGraph** — Yuriy O'Donnell — 现代渲染架构的里程碑演讲
- **《Real-Time Rendering, 4th Edition》** — 第 20 章：渲染系统架构
- **Unreal Engine Documentation**: Render Dependency Graph (RDG)
- **《Game Engine Architecture, 3rd Edition》** — Jason Gregory — 渲染系统章节
- **GDC 2021: "Software Occlusion Culling in Unreal Engine 5"** — UE5 的层次 Z 缓冲遮挡裁剪实现
- **NVIDIA DXR Tutorial** — 实时光线追踪入门（https://developer.nvidia.com/rtx/raytracing/dxr/tutorial）
