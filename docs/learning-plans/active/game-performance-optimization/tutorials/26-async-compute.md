---
title: "Async Compute 与现代 GPU 并行"
updated: 2026-06-05
---

# Async Compute 与现代 GPU 并行
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: Compute Shader 优化 (25)

---

## 1. 概念讲解

### 为什么需要这个？

打开 GPU Profiler 观察一帧，常见的问题是：Graphics Queue 满负荷工作，Compute Queue 完全空闲（反之亦然）。或者更糟——某些 pass 之间有空隙，GPU 在等某个 barrier 解除的同时什么也不做。

现代 GPU 拥有多个硬件队列，可以同时执行不同类型的操作。浪费这些队列等于浪费 20-40% 的 GPU 时间。

**Async Compute** 就是利用这些并行队列，让 Compute 和 Graphics 同时执行。doom (2016) 是最早大规模使用 async compute 的商业游戏之一，从中获得了 15-25% 的 GPU 性能提升。如今，async compute 是主机和 PC 高端游戏的标配。

### 核心思想

#### GPU 的硬件队列

现代 GPU 的命令处理器（Command Processor）支持多个独立的执行队列：

| 队列类型 | 用途 | 典型 GPU 队列数 |
|---------|------|---------------|
| Graphics | 渲染命令 (Draw, Dispatch, Copy) | 1 个主队列 |
| Compute | 计算命令 (Dispatch) | 1-3 个 (AMD 通常 2-3) |
| Copy/DMA | 数据传输 (Copy, Upload) | 1-2 个 |

各架构的队列能力：

| GPU | Graphics | Compute | Copy | 备注 |
|-----|----------|---------|------|------|
| AMD GCN | 1 | 2-8 ACE (Async Compute Engine) | 2 DMA | ACE 就是 AMD async compute 的硬件基础 |
| AMD RDNA/RDNA2 | 1 | 2 ACE (各 4 队列) | 2 DMA | ACE 简化但调度更高效 |
| AMD RDNA3 | 1 | 2 ACE | 2 DMA | 类似 RDNA2 |
| NVIDIA Pascal (GTX 10) | 1 | 1 (有限异步) | 1-2 | Pascal 的 async compute 是软件模拟的，有限并行度 |
| NVIDIA Turing (RTX 20) | 1 | 1 (真正异步) | 1-2 | 硬件支持 compute + graphics 真正并行 |
| NVIDIA Ampere (RTX 30) | 1 | 1 | 1-2 | 单 compute queue，但可以与 graphics 并发执行 |
| NVIDIA Ada (RTX 40) | 1 | 1 | 1-2 | 同 Ampere |
| Intel Arc (Xe-HPG) | 1 | 1 (compute engine) | 1-2 | Compute engine 可与 render slice 并行 |
| Apple GPU (M1/M2) | 1 | 1 | 1 | Metal 中通过 `MTLCommandBuffer` 的并发控制 |
| Mali (Valhall+) | 1 | 1 | — | 有限 async compute 能力 |
| PS5 (RDNA2 定制) | 1 | 2 | 2 | 主机上 async compute 是标准优化手段 |
| Xbox Series X (RDNA2) | 1 | 2 | 2 | 同 PS5 |

**关键洞察**：AMD GPU（包括主机）有多 ACE，天生对 async compute 友好。NVIDIA Pascal 时代 async compute 是软模拟的，收益有限；从 Turing 开始硬件真正支持。

#### 并行窗口：在哪把 Compute 插入 Graphics

一帧内的并行机会：

```
Graphics Queue:  ┌─ZPrepass─┬─ShadowMaps─┬─G-Buffer─┬─Lighting─┬─PostFX─┐
                 │          │            │          │          │        │
Compute Queue:   │ IDLE     │ Culling ▲  │ IDLE     │ SSAO ▲   │ Bloom ▲│
                 │          │ (并行!)    │          │ (并行!)  │ (并行!)│

时间节省：      ┌─────────────────────────────────────────────────┐
                │  Compute 插入 Graphics 的间隙 → 总帧时间缩短   │
                └─────────────────────────────────────────────────┘
```

典型并行窗口：

1. **Shadow pass 期间**：Shadow map 渲染只需要 depth → 图形管线只占 ALU + 光栅化。计算管线可以利用空闲的 ALU 做 GPU culling、particle update。

2. **G-Buffer pass 期间**：G-Buffer 渲染主要绑定在 ROP（光栅输出）和带宽上。Compute queue 可以做 SSAO、light culling —— 这些是 ALU 密集的。

3. **Lighting pass 期间**：如果 lighting 是 compute shader 实现的（tiled/clustered），那它们本来就在 compute queue 上。此时 graphics queue 可以做 post-processing 的前半部分。反过来也行。

4. **Post-processing 期间**：如果 post-FX 在 graphics queue，compute queue 可以做下一帧的 culling。

#### Fences 和 Barriers：同步的艺术

多队列并行带来同步问题：如果 Compute Queue 正在写一个 buffer，Graphics Queue 同时去读它 → 未定义行为。

DX12/Vulkan 提供了精确的同步原语：

**Vulkan 术语**：
- **Pipeline Barrier**（管线屏障）：在单个队列内保证顺序
- **Semaphore**（信号量）：跨队列同步（queue A 完成 → queue B 开始）
- **Fence**（围栏）：GPU → CPU 同步
- **Event**：细粒度同步

**DX12 术语**：
- **Resource Barrier**（资源屏障）：在单个队列内进行状态转换
- **Fence**（围栏）：跨队列同步 + GPU→CPU 同步
- 没有独立的 semaphore 概念（合并到 fence 中）

#### 资源状态转换与 Hazard

与 Async Compute 相关的常见资源状态：

```
COMMON → COMPUTE_SHADER_RESOURCE       // Compute 读
COMMON → UNORDERED_ACCESS               // Compute 写
COMMON → RENDER_TARGET                  // Graphics 写
COMMON → PIXEL_SHADER_RESOURCE         // Graphics 读

转换规则（伪代码）:
如果 Compute 写入 UAV → Graphics 读取 SRV:
  1. Compute queue: Dispatch
  2. Compute queue: UAV → COMMON barrier
  3. Fence signal from compute, wait on graphics
  4. Graphics queue: COMMON → SRV barrier
  5. Graphics queue: Draw (读取)

如果 Graphics 写入 RT → Compute 读取:
  1. Graphics queue: Draw
  2. Graphics queue: RT → COMMON barrier
  3. Fence signal from graphics, wait on compute
  4. Compute queue: COMMON → SRV barrier
  5. Compute queue: Dispatch
```

**常见的 Hazard 类型**：

- **RAW (Read-After-Write)**：Queue A 写入 → Queue B 读取。需要 barrier + fence。
- **WAR (Write-After-Read)**：Queue A 读取 → Queue B 写入。同样需要同步。
- **WAW (Write-After-Write)**：两个队列同时写入同一资源 → **绝对禁止**。

#### Doom (2016) 案例

id Software 在 Doom 中对 async compute 的使用是教科书级别的：

```
Graphics Queue:   DepthPrepass → ShadowMaps → GBuffer → StencilReflect → ForwardPass → PostFX
Compute Queue:    IDLE         → IDLE       → IDLE    → GPU Particles  → SSAO      → Bloom
                                                                   ↕ 并发
```

关键设计：
- SSAO 和 Bloom 被移到 compute queue，与 ForwardPass 的 graphics queue 并行
- GPU particles 在 compute queue 更新，利用 shadow pass 的间隙
- 在主机上额外利用 async compute 做 GPU culling

**收益**：Doom 通过 async compute 节省了约 2-3ms（在 60fps = 16.67ms 的预算中约 12-18%）。

#### UE5 的 Async Compute 支持

Unreal Engine 5 内置了 async compute 框架：
- `ERDGPassFlags::AsyncCompute` 标记一个 RDG pass 在 compute queue 上执行
- 自动插入必要的 barriers 和 fences
- 主要用在：SSGI、反射追踪、体积雾的后处理阶段

项目设置中启用：
```ini
; DefaultEngine.ini
[/Script/Engine.RendererSettings]
r.AsyncCompute=1
```

#### 帧流水线 (Frame Pipelining)

超越单帧内并行：将相邻帧重叠，形成流水线：

```
Frame N Graphics:  ┌─Shadow─┬─GBuffer─┬─Lighting─┬─PostFX─┐
Frame N Compute:   │ Cull▲  │ SSAO    │          │        │
Frame N+1 Graphics:│        │ Cull▲   │ Shadow   │ GBuffer│ ...
Frame N+1 Compute: │        │         │ SSAO     │        │
```

这需要多缓冲（triple/double buffer）避免数据竞争。典型实现：
- Current frame 的 graphics 操作
- Next frame 的 culling/simulation 在 compute queue
- 双缓冲所有中间结果（`g_CulledObjects[frameIdx]`）

#### 测量实际节省

最简单的验证方法：用 GPU Timestamp Query 测量单个 queue 的总耗时 vs 两个 queue 并行的 wall-clock 耗时。

```cpp
// DX12 测量代码框架
ComPtr<ID3D12QueryHeap> timestampHeap;
// ... 创建 query heap，2 个 timestamp per query

// 在 graphics queue 开头和结尾插入 timestamp
graphicsCmdList->EndQuery(timestampHeap, D3D12_QUERY_TYPE_TIMESTAMP, 0);  // G_START
// ... 所有 graphics 命令 ...
graphicsCmdList->EndQuery(timestampHeap, D3D12_QUERY_TYPE_TIMESTAMP, 1);  // G_END

// 在 compute queue 开头和结尾插入 timestamp
computeCmdList->EndQuery(timestampHeap, D3D12_QUERY_TYPE_TIMESTAMP, 2);  // C_START
// ... 所有 compute 命令 ...
computeCmdList->EndQuery(timestampHeap, D3D12_QUERY_TYPE_TIMESTAMP, 3);  // C_END

// 同步分析:
uint64_t gpuFreq;
cmdQueue->GetTimestampFrequency(&gpuFreq);

uint64_t serialTime = (G_END - G_START) + (C_END - C_START);  // 串行总时间
uint64_t parallelTime = max(G_END, C_END) - min(G_START, C_START);  // 并行 wall-clock

double saving = 1.0 - double(parallelTime) / double(serialTime);
printf("Async compute saving: %.1f%%\n", saving * 100);
```

---

## 2. 代码示例

### 示例 A: DX12 双队列设置 (Graphics + Compute)

```cpp
// async_compute_dx12.cpp
// 最小双队列设置的 DX12 代码框架
// 编译: cl /EHsc /std:c++17 async_compute_dx12.cpp /link d3d12.lib dxgi.lib

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <wrl/client.h>
#include <cstdio>
#include <cassert>

using Microsoft::WRL::ComPtr;

// === 错误检查辅助 ===
inline void checkHR(HRESULT hr, const char* msg) {
    if (FAILED(hr)) { printf("ERROR: %s (0x%08X)\n", msg, hr); __debugbreak(); }
}

// === 双队列管理器 ===
struct AsyncComputeContext {
    // D3D12 核心对象
    ComPtr<ID3D12Device5>          device;       // 需要 device5 支持 enhanced barriers
    ComPtr<ID3D12CommandQueue>     graphicsQueue;
    ComPtr<ID3D12CommandQueue>     computeQueue;
    ComPtr<ID3D12CommandAllocator> graphicsAllocator;
    ComPtr<ID3D12CommandAllocator> computeAllocator;
    ComPtr<ID3D12GraphicsCommandList> graphicsCmdList;
    ComPtr<ID3D12GraphicsCommandList> computeCmdList;

    // Fences
    ComPtr<ID3D12Fence> graphicsFence;
    ComPtr<ID3D12Fence> computeFence;
    UINT64 graphicsFenceValue = 0;
    UINT64 computeFenceValue = 0;
    HANDLE fenceEvent;

    void Initialize(ID3D12Device* inDevice) {
        device = inDevice;

        // 创建 Graphics Queue (DIRECT type)
        D3D12_COMMAND_QUEUE_DESC gfxDesc = {};
        gfxDesc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
        gfxDesc.Priority = D3D12_COMMAND_QUEUE_PRIORITY_HIGH;
        gfxDesc.Flags = D3D12_COMMAND_QUEUE_FLAG_NONE;
        checkHR(device->CreateCommandQueue(&gfxDesc,
                 IID_PPV_ARGS(&graphicsQueue)), "Create Graphics Queue");

        // 创建 Compute Queue (COMPUTE type)
        D3D12_COMMAND_QUEUE_DESC cmpDesc = {};
        cmpDesc.Type = D3D12_COMMAND_LIST_TYPE_COMPUTE;
        cmpDesc.Priority = D3D12_COMMAND_QUEUE_PRIORITY_NORMAL;
        cmpDesc.Flags = D3D12_COMMAND_QUEUE_FLAG_NONE;
        checkHR(device->CreateCommandQueue(&cmpDesc,
                 IID_PPV_ARGS(&computeQueue)), "Create Compute Queue");

        // Graphics command list
        checkHR(device->CreateCommandAllocator(
            D3D12_COMMAND_LIST_TYPE_DIRECT,
            IID_PPV_ARGS(&graphicsAllocator)), "Create Graphics Allocator");
        checkHR(device->CreateCommandList(
            0, D3D12_COMMAND_LIST_TYPE_DIRECT,
            graphicsAllocator.Get(), nullptr,
            IID_PPV_ARGS(&graphicsCmdList)), "Create Graphics CmdList");
        graphicsCmdList->Close();

        // Compute command list
        checkHR(device->CreateCommandAllocator(
            D3D12_COMMAND_LIST_TYPE_COMPUTE,
            IID_PPV_ARGS(&computeAllocator)), "Create Compute Allocator");
        checkHR(device->CreateCommandList(
            0, D3D12_COMMAND_LIST_TYPE_COMPUTE,
            computeAllocator.Get(), nullptr,
            IID_PPV_ARGS(&computeCmdList)), "Create Compute CmdList");
        computeCmdList->Close();

        // Fences
        checkHR(device->CreateFence(0, D3D12_FENCE_FLAG_NONE,
                 IID_PPV_ARGS(&graphicsFence)), "Create Graphics Fence");
        checkHR(device->CreateFence(0, D3D12_FENCE_FLAG_NONE,
                 IID_PPV_ARGS(&computeFence)), "Create Compute Fence");
        fenceEvent = CreateEvent(nullptr, FALSE, FALSE, nullptr);
    }

    // 提交 graphics 命令并返回 fence value
    UINT64 SubmitGraphics() {
        graphicsCmdList->Close();
        ID3D12CommandList* lists[] = { graphicsCmdList.Get() };
        graphicsQueue->ExecuteCommandLists(1, lists);
        graphicsQueue->Signal(graphicsFence.Get(), ++graphicsFenceValue);
        return graphicsFenceValue;
    }

    // 提交 compute 命令并返回 fence value
    UINT64 SubmitCompute() {
        computeCmdList->Close();
        ID3D12CommandList* lists[] = { computeCmdList.Get() };
        computeQueue->ExecuteCommandLists(1, lists);
        computeQueue->Signal(computeFence.Get(), ++computeFenceValue);
        return computeFenceValue;
    }

    // 等待 graphics queue 完成到指定 point
    void WaitForGraphics(UINT64 fenceValue) {
        if (graphicsFence->GetCompletedValue() < fenceValue) {
            graphicsFence->SetEventOnCompletion(fenceValue, fenceEvent);
            WaitForSingleObject(fenceEvent, INFINITE);
        }
    }

    // 等待 compute queue 完成到指定 point
    void WaitForCompute(UINT64 fenceValue) {
        if (computeFence->GetCompletedValue() < fenceValue) {
            computeFence->SetEventOnCompletion(fenceValue, fenceEvent);
            WaitForSingleObject(fenceEvent, INFINITE);
        }
    }

    // Graphics queue 等待 compute queue (Compute → Graphics 依赖)
    void GraphicsWaitForCompute(UINT64 computeFenceVal) {
        graphicsQueue->Wait(computeFence.Get(), computeFenceVal);
    }

    // Compute queue 等待 graphics queue (Graphics → Compute 依赖)
    void ComputeWaitForGraphics(UINT64 graphicsFenceVal) {
        computeQueue->Wait(graphicsFence.Get(), graphicsFenceVal);
    }

    void ResetGraphics() {
        graphicsAllocator->Reset();
        graphicsCmdList->Reset(graphicsAllocator.Get(), nullptr);
    }

    void ResetCompute() {
        computeAllocator->Reset();
        computeCmdList->Reset(computeAllocator.Get(), nullptr);
    }

    void Shutdown() {
        if (fenceEvent) CloseHandle(fenceEvent);
    }
};
```

### 示例 B: Overlapping Post-FX Compute with Shadow Pass

```cpp
// frame_overlap_demo.cpp
// 演示: 在 graphics queue 渲染 shadow map 的同时，
//       compute queue 处理上一帧的后处理效果

struct ResourceHandles {
    // Shadow pass 资源
    ComPtr<ID3D12Resource> shadowDepth;    // DSV (graphics 写)
    // 后处理资源
    ComPtr<ID3D12Resource> sceneColorPrev; // SRV (compute 读), 上一帧的 color
    ComPtr<ID3D12Resource> bloomOutput;    // UAV (compute 写)
    ComPtr<ID3D12Resource> ssaoOutput;     // UAV (compute 写)
    // 这些资源的 D3D12 描述符...
};

void RenderFrameOverlapped(AsyncComputeContext& ctx, ResourceHandles& res) {
    // ===============================================
    // Phase 1: 同时开始
    // ===============================================

    // Graphics Queue: Shadow Map Rendering
    ctx.ResetGraphics();
    {
        // Transition depth buffer
        D3D12_RESOURCE_BARRIER barrier = {};
        barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        barrier.Transition.pResource = res.shadowDepth.Get();
        barrier.Transition.StateBefore = D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
        barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_DEPTH_WRITE;
        barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        ctx.graphicsCmdList->ResourceBarrier(1, &barrier);

        // 设置 depth-only 渲染
        ctx.graphicsCmdList->OMSetRenderTargets(0, nullptr, FALSE, &dsvHandle);
        ctx.graphicsCmdList->ClearDepthStencilView(dsvHandle,
            D3D12_CLEAR_FLAG_DEPTH, 1.0f, 0, 0, nullptr);

        // 渲染 shadow casters
        ctx.graphicsCmdList->SetPipelineState(shadowPSO);
        ctx.graphicsCmdList->SetGraphicsRootSignature(shadowRootSig);
        for (auto& mesh : shadowCasters) {
            ctx.graphicsCmdList->DrawIndexedInstanced(
                mesh.indexCount, 1, mesh.startIndex, 0, 0);
        }
    }
    UINT64 shadowFence = ctx.SubmitGraphics();

    // Compute Queue: 同时开始后处理（使用上一帧的 color buffer）
    ctx.ResetCompute();
    {
        // SSAO (读上一帧 depth, 写 ssaoOutput)
        ctx.computeCmdList->SetPipelineState(ssaoPSO);
        ctx.computeCmdList->SetComputeRootSignature(computeRootSig);
        // 设置 SRV (上一帧 depth) 和 UAV (ssaoOutput)
        ctx.computeCmdList->SetComputeRootDescriptorTable(0, prevDepthSRV);
        ctx.computeCmdList->SetComputeRootDescriptorTable(1, ssaoOutputUAV);
        ctx.computeCmdList->Dispatch(
            (width + 15) / 16, (height + 15) / 16, 1);

        // UAV barrier (保证 SSAO 写完再被 Bloom 读)
        D3D12_RESOURCE_BARRIER uavBarrier = {};
        uavBarrier.Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
        uavBarrier.UAV.pResource = res.ssaoOutput.Get();
        ctx.computeCmdList->ResourceBarrier(1, &uavBarrier);

        // Bloom
        ctx.computeCmdList->SetPipelineState(bloomPSO);
        ctx.computeCmdList->Dispatch(
            (width + 15) / 16, (height + 15) / 16, 1);
    }
    UINT64 postFxFence = ctx.SubmitCompute();

    // ===============================================
    // Phase 2: Synchronize
    // Shadow must complete before graphics can use shadow map for lighting
    // PostFX must complete before presentation
    // ===============================================

    // Wait for both queues to finish
    ctx.WaitForGraphics(shadowFence);
    ctx.WaitForCompute(postFxFence);

    // Now safe to proceed to lighting pass (uses shadow map + postFX results)

    printf("Frame completed: Shadow queue=%llu, PostFX queue=%llu\n",
           shadowFence, postFxFence);
}
```

### 示例 C: GPU Timestamp 测量 Async Compute 收益

```cpp
// measure_async_gain.cpp
// 使用 D3D12 Query Timestamp 测量 async compute 的实际节省

void MeasureAsyncComputeGain(
    AsyncComputeContext& ctx,
    ComPtr<ID3D12QueryHeap> timestampHeap,
    ComPtr<ID3D12Resource> readbackBuffer,
    uint64_t gpuFrequency)
{
    const UINT TS_G_START = 0;
    const UINT TS_G_END   = 1;
    const UINT TS_C_START = 2;
    const UINT TS_C_END   = 3;

    // === 测试: 串行模式 (所有工作在 graphics queue) ===
    ctx.ResetGraphics();
    ctx.graphicsCmdList->EndQuery(timestampHeap,
        D3D12_QUERY_TYPE_TIMESTAMP, TS_G_START);

    // Shadow pass (graphics)
    // ... render shadows ...

    // SSAO (graphics queue, 串行)
    // ... 用 graphics queue 做 SSAO ...

    ctx.graphicsCmdList->EndQuery(timestampHeap,
        D3D12_QUERY_TYPE_TIMESTAMP, TS_G_END);

    ctx.graphicsCmdList->ResolveQueryData(timestampHeap,
        D3D12_QUERY_TYPE_TIMESTAMP,
        TS_G_START, 4, readbackBuffer.Get(), TS_G_START * sizeof(uint64_t));

    UINT64 serialFence = ctx.SubmitGraphics();
    ctx.WaitForGraphics(serialFence);

    // 读取串行时间
    uint64_t* data;
    D3D12_RANGE range = { 0, 4 * sizeof(uint64_t) };
    readbackBuffer->Map(0, &range, (void**)&data);
    uint64_t serialGpuTime = data[TS_G_END] - data[TS_G_START];
    readbackBuffer->Unmap(0, nullptr);

    printf("Serial mode (all on graphics queue): %.2f ms\n",
           double(serialGpuTime) / double(gpuFrequency) * 1000.0);

    // === 测试: 并行模式 (graphics + compute) ===
    // Graphics queue: shadow pass + timestamp
    ctx.ResetGraphics();
    ctx.graphicsCmdList->EndQuery(timestampHeap,
        D3D12_QUERY_TYPE_TIMESTAMP, TS_G_START);
    // ... render shadows ...
    ctx.graphicsCmdList->EndQuery(timestampHeap,
        D3D12_QUERY_TYPE_TIMESTAMP, TS_G_END);

    // Compute queue: SSAO + timestamp (与 shadow pass 并行)
    ctx.ResetCompute();
    ctx.computeCmdList->EndQuery(timestampHeap,
        D3D12_QUERY_TYPE_TIMESTAMP, TS_C_START);
    // ... compute SSAO ...
    ctx.computeCmdList->EndQuery(timestampHeap,
        D3D12_QUERY_TYPE_TIMESTAMP, TS_C_END);

    // Resolve timestamps (要在两个 queue 都完成之后)
    UINT64 gFence = ctx.SubmitGraphics();
    UINT64 cFence = ctx.SubmitCompute();
    ctx.WaitForGraphics(gFence);
    ctx.WaitForCompute(cFence);

    // 现在可以安全 resolve（或者用单独的 resolve）
    // 简化: 直接用 graphics queue resolve copy
    {
        ctx.ResetGraphics();
        ctx.graphicsCmdList->ResolveQueryData(timestampHeap,
            D3D12_QUERY_TYPE_TIMESTAMP,
            TS_G_START, 4, readbackBuffer.Get(), 0);
        UINT64 resolveFence = ctx.SubmitGraphics();
        ctx.WaitForGraphics(resolveFence);
    }

    readbackBuffer->Map(0, &range, (void**)&data);
    uint64_t gStart = data[0];
    uint64_t gEnd   = data[1];
    uint64_t cStart = data[2];
    uint64_t cEnd   = data[3];
    readbackBuffer->Unmap(0, nullptr);

    // 串行时间 = graphics 总时间 + compute 总时间
    uint64_t serialTotal = (gEnd - gStart) + (cEnd - cStart);

    // 并行 wall-clock = max(end) - min(start)
    uint64_t parallelWall = max(gEnd, cEnd) - min(gStart, cStart);

    double serialMs = double(serialTotal) / double(gpuFrequency) * 1000.0;
    double parallelMs = double(parallelWall) / double(gpuFrequency) * 1000.0;
    double saving = 1.0 - parallelMs / (double(gEnd - gStart)
                    / double(gpuFrequency) * 1000.0);  // 相对于纯 graphics 时间

    printf("\n=== Async Compute Benchmark Results ===\n");
    printf("Graphics queue time:       %.3f ms\n",
           double(gEnd - gStart) / double(gpuFrequency) * 1000.0);
    printf("Compute queue time:        %.3f ms\n",
           double(cEnd - cStart) / double(gpuFrequency) * 1000.0);
    printf("Serial equivalent:         %.3f ms\n", serialMs);
    printf("Parallel wall-clock:       %.3f ms\n", parallelMs);
    printf("Actual time saving:        %.1f%%\n", saving * 100.0);
    printf("vs serial:                 %.1f%%\n",
           (1.0 - parallelMs / serialMs) * 100.0);

    // 预期输出 (示例):
    // Graphics queue time:       4.200 ms     (shadow pass on graphics)
    // Compute queue time:        2.800 ms     (SSAO on compute — 与 shadow 并行)
    // Serial equivalent:         7.000 ms     (4.2 + 2.8, 如果串行)
    // Parallel wall-clock:       4.500 ms     (重叠执行)
    // Actual time saving:        25.7%         vs 纯 graphics 时间
    // vs serial:                 35.7%         vs 串行等效
}
```

---

## 3. 练习

### 练习 1: 识别并行机会 [基础]

选一个你熟悉的现代游戏或 demo（或一帧的 GPU 捕获），画出它的主要 pass 序列：

1. 列出每个 pass：名称、执行队列（当前在哪儿）、耗时、依赖关系
2. 识别哪些 pass 可以移到 compute queue
3. 画出并行化后的调度图（Gantt chart）
4. 计算理论节省时间

示例格式：
```
Pass              Queue     耗时    依赖
Z-Prepass         Graphics  1.2ms   -
Shadow Maps       Graphics  2.5ms   -
GPU Culling       Graphics  0.8ms   -
G-Buffer          Graphics  3.1ms   Culling
SSAO              Graphics  1.8ms   G-Buffer
Lighting          Graphics  2.2ms   Shadow+GBuffer+SSAO
Bloom             Graphics  1.0ms   Lighting
ToneMap           Graphics  0.4ms   Bloom

识别:
- GPU Culling 可移到 Compute，与 Z-Prepass+Shadow 并行
- SSAO 可移到 Compute，与 G-Buffer (graphics) 并行
- Bloom 可移到 Compute，与 Lighting (graphics) 并行

理论节省: min(1.2+2.5, 0.8) + min(3.1, 1.8) + min(2.2, 1.0) = 0.8+1.8+1.0 = 3.6ms
原始帧时间: 13.0ms → 优化后: 9.4ms (节省 27.7%)
```

### 练习 2: 实现 Compute Particle + Graphics 并行 [进阶]

构建一个 demo，其中 compute queue 更新粒子系统与 graphics queue 的 shadow pass 并行：

1. **Compute Queue**：
   - Dispatch particle update (256 线程/组)
   - 写入 particle buffer（position + velocity）
   - Signal fence

2. **Graphics Queue**：
   - 渲染 shadow maps（不依赖粒子）
   - Wait for particle compute fence
   - 渲染粒子（使用 compute 更新的 buffer）

3. 用 GPU timestamp 测量：
   - 串行版本耗时（先 update particle，再 render shadow → particles）
   - 并行版本耗时（particle update 与 shadow render 重叠）
   - 计算实际节省

4. 注意：particle update 写入的 buffer 在被 graphics 读取之前必须有 UAV barrier + fence

### 练习 3: 跨帧流水线 [挑战]

实现一个跨帧的 async compute 流水线：

**Frame N**:
- Graphics: Shadow → G-Buffer → Lighting → Post-FX final
- Compute: SSAO (与 G-Buffer 并行) → Bloom (与 Lighting 并行)

**同时在 Compute Queue 上启动 Frame N+1 的工作**:
- Compute: GPU Culling for Frame N+1（读 Frame N 的 depth）

设计双缓冲策略使得 Frame N+1 的 culling 不读取 Frame N 正在写入的 depth。画出完整的时间线、barrier 和 fence 序列。实现代码框架。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **识别并行机会 — 对示例 Pass 序列的完整分析**
> 
> **原始序列**（题中给出的示例）：
> 
> | Pass | Queue | 耗时 | 依赖 |
> |------|-------|------|------|
> | Z-Prepass | Graphics | 1.2ms | — |
> | Shadow Maps | Graphics | 2.5ms | — |
> | GPU Culling | Graphics | 0.8ms | — |
> | G-Buffer | Graphics | 3.1ms | Culling |
> | SSAO | Graphics | 1.8ms | G-Buffer |
> | Lighting | Graphics | 2.2ms | Shadow+GBuffer+SSAO |
> | Bloom | Graphics | 1.0ms | Lighting |
> | ToneMap | Graphics | 0.4ms | Bloom |
> 
> **并行化方案分析**：
> 
> 1. **GPU Culling → Compute Queue**（与 Z-Prepass + Shadow 并行）
>    - 依赖：无（Culling 只依赖上一帧的 depth buffer 和物体数据）
>    - 并行窗口大小：max(1.2+2.5, 0.8) = 3.7ms，节省 0.8ms
> 
> 2. **SSAO → Compute Queue**（与 G-Buffer Graphics 并行）
>    - 依赖：需要 G-Buffer 完成后的 depth/normal（需 fence 同步）
>    - 但 SSAO 本身可以用前序帧的 depth 近似（TAA 友好），或用本帧 G-Buffer 完成后立即开始
>    - 严格依赖方案：SSAO 必须等 G-Buffer 完成 → 无法并行
>    - 宽松方案（TAA reprojection）：SSAO 读上一帧 depth，与当前 G-Buffer 并行 → 节省 1.8ms
> 
> 3. **Bloom → Compute Queue**（与 Lighting Graphics 并行）
>    - 依赖：Bloom 需要 Lighting 的输出（HDR color buffer）
>    - Bloom 的 downsample 阶段可以提前（从上一帧 HDR 做），但 upsample+composite 必须等 Lighting
>    - 实际可行方案：Bloom downsample 与 Lighting 并行 → 节省约 0.6ms
> 
> **Gantt Chart（优化后）**：
> ```
> Graphics: |████ ZPrepass ████|████ ShadowMaps ████|████ G-Buffer ████|████ Lighting ████|██ TMap ██|
>           | 1.2ms            | 2.5ms              | 3.1ms            | 2.2ms            | 0.4ms |
> Compute:  |██ GPU Culling ██|                    |████ SSAO ████|████ Bloom ████|              |
>           | 0.8ms           |                    | 1.8ms        | 1.0ms         |              |
> ```
> 
> **理论节省**：min(3.7, 0.8) + min(3.1, 1.8) + min(2.2, 1.0) = 0.8 + 1.8 + 1.0 = **3.6ms**
> **原始总时间**：13.0ms → **优化后**：9.4ms（节省 27.7%）
> 
> **注意事项**：
> - 需要双缓冲 SSAO 的输入（上一帧 depth + 当前帧 depth）
> - Barrier 开销约 0.02~0.05ms per synchronization point
> - 实际节省约 3.3~3.5ms（减去 barrier overhead）
> - 此优化对 AMD GPU（多 ACE）收益更大，NVIDIA Turing+ 也有 8-15% 收益

> [!tip]- 练习 2 参考答案
> **Compute Particle + Graphics 并行 — 代码框架**
> 
> ```cpp
> // DX12 双队列粒子更新与 Shadow Map 并行
> 
> void RenderFrameWithAsyncCompute() {
>     // ===== 准备工作 =====
>     ResetCommandAllocators();
> 
>     // ===== Compute Queue: 粒子更新 =====
>     {
>         computeCmdList->SetPipelineState(particleUpdatePSO);
>         computeCmdList->SetComputeRootSignature(particleRootSig);
> 
>         // 设置粒子 buffer (UAV)
>         computeCmdList->SetComputeRootUnorderedAccessView(0, particleBufferGPUVA);
>         computeCmdList->SetComputeRoot32BitConstant(1, particleCount, 0);
>         computeCmdList->SetComputeRoot32BitConstant(1, deltaTimeAsUint, 1);
> 
>         UINT numGroups = (particleCount + 255) / 256;
>         computeCmdList->Dispatch(numGroups, 1, 1);
> 
>         // UAV barrier: 确保粒子更新完成后才能被 Graphics 读取
>         D3D12_RESOURCE_BARRIER uavToSRV = {};
>         uavToSRV.Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
>         uavToSRV.Flags = D3D12_RESOURCE_BARRIER_FLAG_NONE;
>         uavToSRV.UAV.pResource = particleBuffer;
>         computeCmdList->ResourceBarrier(1, &uavToSRV);
> 
>         computeCmdList->Close();
>         ID3D12CommandList* computeLists[] = { computeCmdList };
>         computeQueue->ExecuteCommandLists(1, computeLists);
> 
>         // Signal fence: compute → graphics
>         computeFenceValue++;
>         computeQueue->Signal(computeFence, computeFenceValue);
>     }
> 
>     // ===== Graphics Queue: Shadow Maps（与 Compute 并行） =====
>     {
>         graphicsCmdList->SetPipelineState(shadowPSO);
>         graphicsCmdList->OMSetRenderTargets(0, nullptr, FALSE,
>             &shadowDSV.cpuHandle);
> 
>         // 渲染 Shadow Maps（不依赖粒子数据）
>         for (auto& shadowCaster : shadowCasters) {
>             graphicsCmdList->IASetVertexBuffers(…);
>             graphicsCmdList->DrawIndexedInstanced(…);
>         }
> 
>         // ===== 等待 Compute 完成 =====
>         // Graphics queue 等待 compute fence
>         graphicsQueue->Wait(computeFence, computeFenceValue);
> 
>         // 现在粒子 buffer 可以被安全读取
>         // 状态转换: UAV → SRV (在 Graphics 端读取)
>         D3D12_RESOURCE_BARRIER particleToSRV = {};
>         particleToSRV.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
>         particleToSRV.Transition.pResource = particleBuffer;
>         particleToSRV.Transition.StateBefore = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
>         particleToSRV.Transition.StateAfter = D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
>         graphicsCmdList->ResourceBarrier(1, &particleToSRV);
> 
>         // ===== 渲染粒子（使用 Compute 更新的 buffer） =====
>         graphicsCmdList->SetPipelineState(particleRenderPSO);
>         graphicsCmdList->SetGraphicsRootShaderResourceView(0,
>             particleBufferGPUVA); // 作为 SRV 读取
>         graphicsCmdList->DrawInstanced(…);
> 
>         graphicsCmdList->Close();
>         ID3D12CommandList* gfxLists[] = { graphicsCmdList };
>         graphicsQueue->ExecuteCommandLists(1, gfxLists);
>     }
> 
>     // ===== GPU Timestamp 测量 =====
>     // 串行版本: 先 particle update → 再 shadow → 再 particle render = total_serial
>     // 并行版本: particle update || shadow → particle render = total_parallel
>     // saving = (total_serial - total_parallel) / total_serial × 100%
> }
> ```
> 
> **关键同步点**：
> 1. Compute queue 写完 particle buffer → UAV barrier → Signal fence
> 2. Graphics queue 渲染完 shadow → Wait(compute fence) → 转换 particle buffer 为 SRV → 读粒子数据
> 3. 这样就保证了 RAW (Read-After-Write) 的正确性

> [!tip]- 练习 3 参考答案
> **跨帧流水线 — 双缓冲设计与 Barrier/Fence 序列**
> 
> **时间线设计**（双缓冲 depth buffer: `DepthBuf[0]` 和 `DepthBuf[1]`）：
> 
> ```
> Frame N (使用 DepthBuf[0]):
> ═══════════════════════════════════════════════════════════
> Graphics: | Shadow[0] | G-Buffer[0] | Lighting | PostFX → Present
> Compute:             |  SSAO(N)   | Bloom(N)|
>                       (读 DepthBuf[0])
> 
> Compute (提前): | GPU Culling for N+1 |
>                  (读 DepthBuf[0], 因为 N+1 还没开始)
> ═══════════════════════════════════════════════════════════
> 
> Frame N+1 (使用 DepthBuf[1]):
> ═══════════════════════════════════════════════════════════
> Graphics: | Shadow[1] | G-Buffer[1] | Lighting | PostFX → Present
> Compute:             |  SSAO(N+1)  | Bloom(N+1)|
>                       (读 DepthBuf[1])
> 
> Compute (提前): | GPU Culling for N+2 |
>                  (读 DepthBuf[1])
> ═══════════════════════════════════════════════════════════
> ```
> 
> **双缓冲策略**：
> - Frame N 写入 `DepthBuf[N%2]`（G-Buffer 的 depth RT）
> - Frame N+1 写入 `DepthBuf[(N+1)%2]`——**不同的 buffer！**
> - Frame N 的 GPU Culling（为 N+1 准备）读取 `DepthBuf[N%2]`
> - 关键：**读的是上一帧的 depth，写的是当前帧不同的 buffer** → 天然的 WAR 避免
> 
> **Barrier 和 Fence 序列（DX12 伪代码）**：
> ```
> // ===== Frame N =====
> // Compute Queue
> Dispatch(GPUCulling_FrameN);           // 读 DepthBuf[N%2] as SRV
> Barrier(UAV→COMMON, g_CulledObjects[N%2]); // culling 结果就绪
> ComputeFence.Value = ++computeFenceValue;
> ComputeQueue.Signal(ComputeFence, computeFenceValue);
> 
> // Graphics Queue
> RenderShadow(DepthBuf[N%2]);           // 写 DepthBuf[N%2] as DSV
> GraphicsQueue.Wait(ComputeFence, computeFenceValue); // 等 culling 完成
> Barrier(COMMON→SRV, g_CulledObjects[N%2]);
> DrawIndexedInstancedIndirect(..., g_CulledObjects[N%2]);
> RenderGBuffer(DepthBuf[N%2]);
> 
> // ===== Frame N+1 =====
> // Compute Queue (culling 读 N 的 depth，写 N+1 的 culling buffer)
> Dispatch(GPUCulling_FrameN1);          // 读 DepthBuf[N%2] as SRV
> Barrier(UAV→COMMON, g_CulledObjects[(N+1)%2]);
> ...
> 
> // Graphics Queue (渲染到 N+1 的 depth)
> RenderShadow(DepthBuf[(N+1)%2]);       // 写 DepthBuf[(N+1)%2] — 不同 buffer!
> GraphicsQueue.Wait(ComputeFence, ...);
> DrawIndexedInstancedIndirect(..., g_CulledObjects[(N+1)%2]);
> ```
> 
> **资源列表（每帧独立）**：
> 
> | 资源 | Frame N | Frame N+1 | 用途 |
> |------|---------|-----------|------|
> | DepthBuffer | Buf[0] | Buf[1] | G-Buffer depth (DSV → SRV for culling) |
> | CulledObjects | Arr[0] | Arr[1] | Culling 输出 (UAV → SRV for DrawIndirect) |
> | IndirectArgs | Args[0] | Args[1] | DrawIndexedInstancedIndirect 参数 |
> | SSGI/SSAO buffer | Buf[0] | Buf[1] | Compute 输出供 Lighting 读取 |
> 
> **跨帧流水线的额外收益**：除了 per-frame async compute，culling 为下一帧提前完成 → culling latency 从 wait-for-previous-frame 变为 zero（GPU Culling 在上一帧的 compute overlap 中完成，本帧 graphics 直接使用）。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [GDC 2016: "Rendering 'DOOM' — Async Compute Deep Dive"](https://www.gdcvault.com/) — id Software 的 Tiago Sousa, 经典 async compute 演讲
- [Microsoft: "Multi-Engine Synchronization in DX12"](https://learn.microsoft.com/en-us/windows/win32/direct3d12/user-mode-heap-synchronization) — DX12 多队列同步
- [Vulkan: "Queue Family and Synchronization"](https://docs.vulkan.org/spec/latest/chapters/synchronization.html) — 跨队列同步规范
- [AMD: "Async Compute for RDNA"](https://gpuopen.com/learn/async-compute-for-rdna/) — AMD 官方指南
- [NVIDIA: "Advanced API Performance — Async Compute"](https://developer.nvidia.com/blog/advanced-api-performance-async-compute-and-copy/) — NVIDIA 视角
- [Digital Foundry: "Async Compute on Consoles"](https://www.eurogamer.net/digitalfoundry) — 主机 async compute 实战分析
- [3DMark Time Spy: Async Compute Benchmark](https://benchmarks.ul.com/) — 量化 async compute 收益
- [UE5: RDG Async Compute](https://docs.unrealengine.com/5.0/en-US/render-dependency-graph-in-unreal-engine/) — UE5 的 async compute 框架
- [GDC 2019: "Async Compute in Frostbite"](https://www.gdcvault.com/) — DICE 的 Frostbite 引擎中的 async compute
- [Intel: "Arc GPU Async Compute Considerations"](https://www.intel.com/content/www/us/en/developer/articles/guide/arc-gpu-developer-guide.html)

---

## 常见陷阱

1. **"在 NVIDIA 上不需要 async compute"**：是的，NVIDIA 只有一个 compute queue。但 Turing+ 的 compute queue 确实可以和 graphics queue 并发执行（不同 SM 或同一 SM 的未占用 slot）。收益通常比 AMD 小但不为零——shadow pass 期间做 SSAO 在 RTX 30 系列上实测有 8-12% 节省。

2. **过度使用 barrier**：每个资源 barrier 都有代价（~0.5-3 µs per barrier）。如果在 compute 和 graphics 之间每帧插入 20 个 barrier，总 overhead 可能吃掉一半的 async compute 收益。合理分组（batch barriers）并减少不必要的状态转换。

3. **忽略 queue priority**：DX12 的 `D3D12_COMMAND_QUEUE_PRIORITY_HIGH` 会影响 GPU 调度。两个队列都设为 `HIGH` 可能导致命令处理器频繁切换，引入 overhead。通常 graphics queue 用 `HIGH`、compute queue 用 `NORMAL` 是正确的。

4. **Compute queue 任务太轻**：如果 compute dispatch 只要 0.1ms，而 barrier + fence 设置要 0.02ms → overhead 20%，不划算。Compute queue 上的任务应该足够重（≥0.5ms）才值得单独开队列。

5. **Fence 信号后立即读**：Fence 保证的是"之前的操作提交完毕"，但不是"GPU 执行完毕"。如果你在 `Signal` 后立即从 CPU 读 GPU 写入的 buffer，需要 `GetCompletedValue()` 等待 fence。CPU-GPU 同步使用 fence，GPU-GPU 同步使用 `Wait`（在命令队列中插入）。

6. **在 Mali 移动 GPU 上使用 async compute**：Mali 虽然支持 compute queue，但并发执行能力有限。加上 tile-based 渲染的特性，compute + graphics 的并行机会比桌面 GPU 少得多。移动端优先优化单队列内的执行（如利用 subpass 减少 tile reload），而不是盲目追求 async compute。

7. **Copy Queue 的滥用**：DMA/Copy queue 可以做数据传输与 rendering 并行。但如果 copy 触发 GPU cache 刷新（因为 CPU 刚写入的数据需要 GPU 读取），可能破坏所有正在执行的 graphics/compute 的 cache 状态。异步上传纹理和 buffer 需要 `D3D12_HEAP_TYPE_UPLOAD` + 显式 barrier。
