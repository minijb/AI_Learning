---
title: "GPU 架构简析 — 并行模型与调度"
updated: 2026-06-05
---

# GPU 架构简析 — 并行模型与调度
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: Draw Call 优化 (05)

---

## 1. 概念讲解

### 为什么需要这个？

你在 Unity/UE 里写了 Shader，调了参数，画面出来了。但当你面对 GPU 性能瓶颈时——帧时间 33ms 里 GPU 占了 25ms——你需要的不仅是"降低 Shader 复杂度"这种泛泛建议。你需要知道 GPU 内部到底发生了什么：

- 为什么一个 `if` 分支可能让性能腰斩，而另一个却几乎无影响？
- 为什么 256 个线程比 64 个线程快？2560 个呢？
- 为什么寄存器多用了一个，整个 Shader 的 occupancy 就掉了一半？
- 为什么同样的算法，在 Mali GPU 上和 NVIDIA 上的瓶颈完全不同？

这些问题答案都在 GPU 的并行执行模型中。本节给你一个足够精确的心智模型，让你在面对 GPU 性能数据时能做出正确的优化决策。

### 核心思想

#### CPU vs GPU: 延迟优化 vs 吞吐优化

CPU 的目标是 **最小化单个任务的完成时间（延迟）**。为此它投资了大量硅片面积在分支预测、乱序执行、大容量私有 Cache 上。一个 i9-13900K 有 24 个核心，每个核心可以在 5.8GHz 频率下处理 2 个超线程。

GPU 的目标是 **最大化单位时间完成的工作量（吞吐）**。它把同样的硅片预算用来堆成千上万个更简单的计算单元。一个 RTX 3070 Ti (GA104) 拥有 6144 个 CUDA Core，同时保持 48 个 SM（Streaming Multiprocessor）处于活跃状态。

核心差异：

| 特性 | CPU (13900K) | GPU (RTX 3070 Ti) |
|------|-------------|-------------------|
| 核数 | 24 | 6144 CUDA Cores (48 SM × 128) |
| 频率 | 5.8 GHz | ~1.77 GHz |
| Cache (L1) | 每核 80KB | 每 SM 128KB |
| Cache (L2) | 36MB 共享 | 4MB 共享 |
| 线程数 | 32 硬件线程 | ~200K+ 同时驻留 |
| 设计目标 | 低延迟 | 高吞吐 |
| 晶体管分配 | 分支预测/乱序/大Cache | 海量 ALU |

**吞吐优化的代价**：GPU 单个线程比 CPU 线程慢得多——时钟低，没有分支预测，没有乱序执行。但 GPU 通过同时运行数万个线程来弥补。关键是 **隐藏延迟**：当一个 warp 等待内存时，SM 立刻切换到另一个 warp，ALU 从不闲着。

#### SIMT 执行模型: Warp/Wavefront

GPU 以 **warp**（NVIDIA 术语）或 **wavefront**（AMD 术语）为单位调度线程：

- **NVIDIA**: 一个 warp = 32 个线程。所有线程在同一周期内执行同一条指令。
- **AMD RDNA**: 一个 wavefront = 32 或 64 个线程（wave32/wave64 模式）。
- **Intel Arc (Xe-HPG)**: 一个 SIMD lane = 8 个线程，一个 EU = 8 lanes = 64 线程。
- **Apple GPU (Metal)**: 一个 SIMD group ≈ 32 个线程（threadgroup 内）。
- **ARM Mali (Valhall/G-series)**: 一个 warp = 16 个线程，4-wide SIMD。

执行规则：**同一 warp 内的所有线程在同一时钟周期执行同一条指令**（SIMT — Single Instruction Multiple Thread）。每个线程有自己的寄存器文件和程序计数器副本，所以可以走不同的分支——但所有分支会被串行化执行。

```
// 假设一个 warp 的 32 个线程遇到这个分支：
if (threadIdx.x < 16) {
    result[threadIdx.x] = A[threadIdx.x] * 2;  // 路径 A
} else {
    result[threadIdx.x] = B[threadIdx.x] + 3;  // 路径 B
}

// GPU 执行流程：
// 1. 所有 32 线程评估条件
// 2. 线程 0-15 走路径 A；线程 16-31 被屏蔽（masked off），闲置等待
// 3. 线程 16-31 走路径 B；线程 0-15 被屏蔽，闲置等待
// 4. 所有线程重新汇聚（reconverge）继续执行
// 实际执行时间 ≈ A 时间 + B 时间
```

这就是 **warp divergence**：当 warp 内线程走不同分支时，两个分支都要执行，有效吞吐减半甚至更差。

**reconvergence** 在现代 GPU 上比早期更智能。NVIDIA Volta+ 使用 Independent Thread Scheduling，每个线程有自己的栈，允许子 warp 级别的灵活调度。但代价是寄存器更多，且需要显式 `__syncwarp()` 屏障。

#### Occupancy: 用更多 Warp 隐藏延迟

GPU 的核心策略是用大量 warp 互相覆盖彼此的延迟。想象一个流水线：当 Warp A 触发一次全局内存读取（~200-800 周期延迟），SM 立刻切换到 Warp B。B 做一会儿计算又触发了内存读取，SM 切到 Warp C... 等 C 的内存请求也在等待时，A 的数据已经回来了。

**occupancy** 衡量 SM 上同时活跃的 warp 数量相对于理论最大值的比例：

```
occupancy = active_warps / max_warps_per_SM
```

例如 NVIDIA GA104 (RTX 3070 Ti)：每 SM 最多 48 个 warp（1536 线程），每 SM 最多 4 个 warp scheduler。

高 occupancy 意味着更多 warp 可用于隐藏延迟——但 **不是 occupancy 越高越好**。原因是：

#### Register Pressure: 寄存器的隐形成本

每个 SM 有固定数量的寄存器。GA104 每 SM 有 65536 个 32-bit 寄存器。

如果 Shader 用了 64 个寄存器（VGPR），每个 warp 需要 32 × 64 = 2048 个寄存器。SM 最多容纳 65536 / 2048 = 32 个 warp。occupancy = 32/48 = 66.7%。

如果 Shader 用了 128 个寄存器，每个 warp 需要 4096 个寄存器。SM 最多容纳 16 个 warp。occupancy = 16/48 = 33.3%。

**寄存器用量直接决定了 occupancy 的上限。** 更多的局部变量、更复杂的表达式、更大的循环展开都增加寄存器压力。当寄存器不足时，编译器会 **spill**——把寄存器内容写入 VRAM（L1 缓存），需要时再读回。这比全局内存快但比寄存器慢 10-100 倍，且吃掉宝贵的 L1 带宽。

**优化启示**：有时牺牲 occupancy 换取更少的指令（用寄存器存中间结果）是正确的；有时为提升 occupancy 而减少寄存器用量（减少循环展开、避免大数组在寄存器中）是正确选择。需要用 Profiler（NSight/RGP）实测。

#### 共享内存同样限制 Occupancy

Shared memory（NVIDIA 术语）/ LDS（AMD 术语）也按 SM 分配。GA104 每 SM 最多 100KB shared memory，可配置为不同大小。如果一个 thread block 请求 48KB shared memory，SM 能容纳的 block 数就受限于 shared memory 而非寄存器或线程数。

#### GPU 内存层次结构

```
                   大小          延迟(周期)      访问范围
寄存器 (VGPR)      256KB/SM      ~0             单线程
共享内存/LDS       100KB/SM      ~20-30         同一 thread block
L1 Cache           128KB/SM      ~30-50         同一 SM
L2 Cache           4MB (GA104)  ~200-300        全 GPU (所有 SM)
全局内存/VRAM      8GB (GDDR6)  ~400-800        全 GPU + CPU (映射)
```

关键特点：

- **寄存器**：最快但最稀缺。每个线程私有。编译器自动管理。
- **共享内存/LDS**：由程序员显式管理（比 L1 快，且不会受 CPU 端操作污染）。用于 thread block 内部通信（如并行归约、矩阵转置）。
- **L1 Cache**：硬件自动管理。NVIDIA SM 上的 L1 和 Shared Memory 共享同一块物理 SRAM（可配置比例，通常 48KB/52KB 或 64KB/36KB）。
- **L2 Cache**：所有 SM 共享。对纹理采样有很大加速效果，因为纹理访问通常有良好的空间局部性。
- **全局内存**：GDDR6/GDDR6X 带宽高（RTX 3070 Ti: 608 GB/s）但延迟也很高。合并访问（coalesced access）至关重要——同一 warp 访问连续地址可以合并为单次 burst。

**Mobile GPU (Mali/Adreno) 的特殊之处**：它们使用统一内存架构（CPU 和 GPU 共享物理内存），这减少了数据拷贝但带宽更紧张（LPDDR5 通常 50-100 GB/s vs 桌面 GPU 的 500+ GB/s）。Mali GPU 的 L2 Cache 通常 256KB-2MB 不等。

#### IMR vs TBR: 两种渲染架构

**IMR (Immediate Mode Rendering)** — 桌面 GPU 标准（NVIDIA, AMD, Intel 桌面）：

1. 顶点着色器处理顶点
2. 光栅化为像素
3. 像素着色器读取纹理、写入帧缓冲 → **直接写入 VRAM**
4. 每帧可能有大量读-改-写（Blend），带宽开销巨大

**TBR (Tile-Based Rendering)** — 移动 GPU 标准（Mali, Adreno, Apple GPU）：

1. 整个屏幕被划分为 8×8 或 32×32 像素的 tile
2. 顶点着色器先处理所有几何体 → 生成每个 tile 的 primitive list（binning pass）
3. 逐 tile 光栅化 → 所有像素处理在 **on-chip tile memory**（极快 SRAM）中完成
4. 处理完成后一次性将 tile 写回 VRAM → 大幅减少外部带宽

TBR 的优势：
- 帧缓冲在片上完成，节省了大量 Blend 带宽
- 移动 GPU 带宽有限（LPDDR5 51.2 GB/s vs GDDR6 608 GB/s），TBR 是救命技术
- 代价：额外的 binning pass，且有 tile 间依赖

**Apple GPU (Metal)** 更进一步——使用 Programmable Blend 和 Tile Shaders，允许在 tile memory 中做计算管线，不经过 VRAM。

**为什么知道这个很重要？**
- TBR 上频繁在帧缓冲间切换（Load/Store actions）比 IMR 贵得多。Metal 和 Vulkan 中要小心使用 `DONT_CARE`/`CLEAR` 而非 `LOAD`。
- TBR 上全屏后处理 pass 会丢失 tile memory 优势（因需要切换渲染目标），应尽量合并。
- IMR 上几何体过多会影响 Broadwell/前端，TBR 上几何体过多会影响 binning pass。

#### 架构知识到优化决策的映射

| 知识 | 优化决策 |
|------|---------|
| Warp 大小 = 32/64 | thread group 大小应为 warp 的整数倍，避免部分 warp |
| Warp divergence 代价 | 尽量让分支条件在 warp 内一致（如 `threadIdx.x < 16`） |
| 寄存器限制 occupancy | 用 NSight/RGP 检查 VGPR 用量，必要时减少局部变量 |
| Shared memory 限制 occupancy | 大 shared memory 分配时检查对 occupancy 的影响 |
| L2 仅 4MB | 同一帧中的渲染目标和纹理不要超过 L2 容量 |
| TBR tile memory | 移动端优先用 subpass/input attachment 减少 load/store |
| 统一内存 (移动) | 尽量避免 CPU↔GPU 数据拷贝，它们不是真正的"零拷贝" |

---

## 2. 代码示例

### 示例 A: Warp Divergence 代价演示 (CUDA)

```cuda
// divergence_demo.cu
// 编译: nvcc -o divergence_demo divergence_demo.cu
// 运行: ./divergence_demo

#include <cuda_runtime.h>
#include <stdio.h>
#include <chrono>

// 场景 1: 分支在 warp 内发散 (相邻线程走不同路径)
// 线程 0,2,4,... → 路径 A; 线程 1,3,5,... → 路径 B
// 每个 warp 内两个分支都会执行
__global__ void divergent_kernel(float* data, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) {
        float val = data[idx];
        if (idx % 2 == 0) {
            // 路径 A: 重计算
            for (int i = 0; i < 500; i++) {
                val = val * 1.0001f + 0.0001f;
            }
        } else {
            // 路径 B: 不同计算
            for (int i = 0; i < 500; i++) {
                val = val / 1.0001f - 0.0001f;
            }
        }
        data[idx] = val;
    }
}

// 场景 2: 分支在 warp 内一致 (前半 warp 走 A, 后半走 B)
// 线程 0-15 → 路径 A; 线程 16-31 → 路径 B
// 每个 warp 内两个分支也都执行，但只有一次分支转换
__global__ void coalesced_branch_kernel(float* data, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) {
        float val = data[idx];
        // 分支条件基于 threadIdx.x 而非全局 idx
        // 在 warp 内: 线程 0-15 走 A, 16-31 走 B
        if ((idx & 31) < 16) {
            for (int i = 0; i < 500; i++) {
                val = val * 1.0001f + 0.0001f;
            }
        } else {
            for (int i = 0; i < 500; i++) {
                val = val / 1.0001f - 0.0001f;
            }
        }
        data[idx] = val;
    }
}

// 场景 3: 无分支
__global__ void no_branch_kernel(float* data, int n) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < n) {
        float val = data[idx];
        for (int i = 0; i < 1000; i++) {
            val = val * 1.0001f + 0.0001f;
        }
        data[idx] = val;
    }
}

int main() {
    const int N = 1 << 20;  // 1M floats
    float* d_data;
    cudaMalloc(&d_data, N * sizeof(float));

    // 初始化
    float* h_data = (float*)malloc(N * sizeof(float));
    for (int i = 0; i < N; i++) h_data[i] = 1.0f;
    cudaMemcpy(d_data, h_data, N * sizeof(float), cudaMemcpyHostToDevice);

    cudaEvent_t start, stop;
    cudaEventCreate(&start);
    cudaEventCreate(&stop);

    int blockSize = 256;
    int gridSize = (N + blockSize - 1) / blockSize;

    // 预热
    divergent_kernel<<<gridSize, blockSize>>>(d_data, N);
    cudaDeviceSynchronize();

    // 测试 1: Divergent
    cudaEventRecord(start);
    divergent_kernel<<<gridSize, blockSize>>>(d_data, N);
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);
    float ms_divergent;
    cudaEventElapsedTime(&ms_divergent, start, stop);

    // 测试 2: Coalesced Branch
    cudaEventRecord(start);
    coalesced_branch_kernel<<<gridSize, blockSize>>>(d_data, N);
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);
    float ms_coalesced;
    cudaEventElapsedTime(&ms_coalesced, start, stop);

    // 测试 3: No Branch
    cudaEventRecord(start);
    no_branch_kernel<<<gridSize, blockSize>>>(d_data, N);
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);
    float ms_nobranch;
    cudaEventElapsedTime(&ms_nobranch, start, stop);

    printf("=== Warp Divergence Benchmark ===\n");
    printf("Divergent branch (stride=1):    %.3f ms\n", ms_divergent);
    printf("Coalesced branch (half-warp):   %.3f ms\n", ms_coalesced);
    printf("No branch:                     %.3f ms\n", ms_nobranch);
    printf("Divergent overhead:            %.1f%%\n",
           (ms_divergent / ms_nobranch - 1.0f) * 100);
    printf("Coalesced overhead:            %.1f%%\n",
           (ms_coalesced / ms_nobranch - 1.0f) * 100);

    cudaFree(d_data);
    free(h_data);
    cudaEventDestroy(start);
    cudaEventDestroy(stop);
    return 0;
}

// 预期输出（RTX 3070 Ti 示例）:
// Divergent branch:  ~0.52 ms
// Coalesced branch: ~0.31 ms
// No branch:        ~0.28 ms
// 解释: 发散分支两个路径都要执行，~2x 开销
// coalesced 版本中 half-warp 同时活跃/失活，实际只有一个分支转换，
// 但 GPU 聪明地只在 warp 内存在不同路径时才发散
```

### 示例 B: Shared Memory Bank Conflicts (CUDA)

```cuda
// bank_conflict_demo.cu
// 编译: nvcc -o bank_conflict_demo bank_conflict_demo.cu
// Shared memory 被分为 32 个 bank（每 bank 4 bytes）。
// 同一 warp 内的多个线程访问同一 bank 的不同地址 → bank conflict

#include <cuda_runtime.h>
#include <stdio.h>

const int N = 1024;
const int BLOCK = 256;

// 无 bank conflict: 线程 i 访问 bank[i]，所有 32 线程访问不同 bank
__global__ void no_conflict(float* out, const float* in) {
    __shared__ float smem[BLOCK];
    int tid = threadIdx.x;
    smem[tid] = in[blockIdx.x * BLOCK + tid];
    __syncthreads();
    out[blockIdx.x * BLOCK + tid] = smem[tid];  // stride=1
}

// 2-way bank conflict: 线程 i 和 i+16 访问同一 bank
__global__ void conflict_2way(float* out, const float* in) {
    __shared__ float smem[BLOCK];
    int tid = threadIdx.x;
    smem[tid] = in[blockIdx.x * BLOCK + tid];
    __syncthreads();
    // 每个 bank 的 4 bytes 存一个 float; BLOCK=256 → 256 floats
    // stride=2 时: 线程 0→bank[0], 线程 1→bank[2], ...
    // 但 256 floats / 32 banks = 8 floats/bank
    // 线程 0→bank0@offset0, 线程 16→bank0@offset16*2/4=8? — 手动计算
    // 更简单: stride=2 → 偶数线程访问偶数 index，奇数线程访问奇数 index
    // 线程 0(bank0) 和线程 16(bank16→(16*2)%32=bank0) 冲突
    out[blockIdx.x * BLOCK + tid] = smem[tid * 2 % BLOCK];
}

// 32-way bank conflict: 所有线程访问同一 bank
__global__ void conflict_32way(float* out, const float* in) {
    __shared__ float smem[BLOCK];
    int tid = threadIdx.x;
    smem[tid] = in[blockIdx.x * BLOCK + tid];
    __syncthreads();
    // 所有线程访问 bank 0 的不同地址
    out[blockIdx.x * BLOCK + tid] = smem[(tid % 2) * 16];
}

// 解法: 添加 padding
__global__ void conflict_fixed(float* out, const float* in) {
    // BLOCK + 1 的 padding 改变了 mapping → 每行开始不在同一 bank
    __shared__ float smem[BLOCK + 1];  // padding!
    int tid = threadIdx.x;
    smem[tid] = in[blockIdx.x * BLOCK + tid];
    __syncthreads();
    out[blockIdx.x * BLOCK + tid] = smem[tid * 2 % BLOCK];
}

int main() {
    const int blocks = 256;
    float *d_in, *d_out;
    cudaMalloc(&d_in, N * blocks * sizeof(float));
    cudaMalloc(&d_out, N * blocks * sizeof(float));

    float* h_in = (float*)malloc(N * blocks * sizeof(float));
    for (int i = 0; i < N * blocks; i++) h_in[i] = (float)i;
    cudaMemcpy(d_in, h_in, N * blocks * sizeof(float), cudaMemcpyHostToDevice);

    cudaEvent_t start, stop;
    cudaEventCreate(&start); cudaEventCreate(&stop);

    // 预热
    no_conflict<<<blocks, BLOCK>>>(d_out, d_in);
    cudaDeviceSynchronize();

    float times[4];
    const char* names[] = {"No conflict", "2-way conflict",
                           "32-way conflict", "Fixed (padding)"};
    void (*kernels[])(float*, const float*) = {
        no_conflict, conflict_2way, conflict_32way, conflict_fixed
    };

    for (int k = 0; k < 4; k++) {
        cudaEventRecord(start);
        kernels[k]<<<blocks, BLOCK>>>(d_out, d_in);
        cudaEventRecord(stop);
        cudaEventSynchronize(stop);
        cudaEventElapsedTime(&times[k], start, stop);
    }

    printf("=== Shared Memory Bank Conflict Demo ===\n");
    for (int k = 0; k < 4; k++)
        printf("%-20s: %.3f ms\n", names[k], times[k]);
    printf("32-way penalty vs no-conflict: %.1fx\n",
           times[2] / times[0]);

    cudaFree(d_in); cudaFree(d_out);
    free(h_in);
    cudaEventDestroy(start); cudaEventDestroy(stop);
    return 0;
}

// 预期输出:
// No conflict:          ~0.08 ms
// 2-way conflict:       ~0.15 ms  (~2x)
// 32-way conflict:      ~0.95 ms  (~12x — 32x 但不是等比例，因为有广播机制)
// Fixed (padding):      ~0.09 ms  (基本恢复)
```

### 示例 C: Occupancy 计算器

```python
#!/usr/bin/env python3
"""
occupancy_calc.py — GPU Occupancy 计算器

使用真实 GPU 规格（NVIDIA GA104 = RTX 3070 Ti, AMD RDNA 2, Apple M2）计算
给定寄存器/共享内存使用下的 occupancy。
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class SMConfig:
    """单个 SM 的硬件限制"""
    name: str
    max_warps_per_sm: int       # 最大 warp/wave 数
    max_blocks_per_sm: int      # 最大 thread block 数
    max_threads_per_sm: int     # 最大线程数
    regs_per_sm: int            # 32-bit 寄存器总数
    shared_mem_per_sm: int      # 共享内存 (bytes)
    warp_size: int              # 每 warp 线程数
    max_regs_per_thread: int    # 每线程最大寄存器


# 真实 GPU 数据
GPUS = {
    "RTX 3070 Ti (GA104)": SMConfig(
        name="GA104",
        max_warps_per_sm=48,           # 1536 threads / 32
        max_blocks_per_sm=16,
        max_threads_per_sm=1536,
        regs_per_sm=65536,
        shared_mem_per_sm=102400,      # 100 KB (可配置，此为上限)
        warp_size=32,
        max_regs_per_thread=255,
    ),
    "RTX 4090 (AD102)": SMConfig(
        name="AD102",
        max_warps_per_sm=48,
        max_blocks_per_sm=24,
        max_threads_per_sm=1536,
        regs_per_sm=65536,
        shared_mem_per_sm=102400,
        warp_size=32,
        max_regs_per_thread=255,
    ),
    "RX 6800 XT (RDNA 2)": SMConfig(
        name="RDNA2 WGP",
        max_warps_per_sm=32,           # wavefronts (wave32 mode)
        max_blocks_per_sm=8,
        max_threads_per_sm=1024,        # 32 wavefronts × 32
        regs_per_sm=65536,
        shared_mem_per_sm=131072,       # 128 KB LDS
        warp_size=32,
        max_regs_per_thread=256,
    ),
    "Apple M2 Pro (Metal 3)": SMConfig(
        name="Apple GPU",
        max_warps_per_sm=32,            # 1024 threads / 32
        max_blocks_per_sm=8,
        max_threads_per_sm=1024,
        regs_per_sm=65536,              # 估计值
        shared_mem_per_sm=65536,        # 64 KB threadgroup memory
        warp_size=32,
        max_regs_per_thread=256,
    ),
    "Mali G710 (Valhall)": SMConfig(
        name="Mali-G710",
        max_warps_per_sm=16,            # 每 core 256 threads
        max_blocks_per_sm=8,
        max_threads_per_sm=256,
        regs_per_sm=65536,              # 估计
        shared_mem_per_sm=65536,
        warp_size=16,                   # Mali 用 16
        max_regs_per_thread=128,
    ),
}


def calc_occupancy(
    config: SMConfig,
    threads_per_block: int,
    regs_per_thread: int,
    shared_mem_per_block: int,
) -> dict:
    """计算给定配置下的 occupancy"""

    warps_per_block = (threads_per_block + config.warp_size - 1) // config.warp_size

    # 限制 1: 线程数
    blocks_by_threads = config.max_threads_per_sm // threads_per_block     \n
        if threads_per_block > 0 else 0

    # 限制 2: block 数
    blocks_by_sm_limit = config.max_blocks_per_sm

    # 限制 3: 寄存器
    regs_per_warp = regs_per_thread * config.warp_size
    # 对齐: warp 分配单元按 warp 对齐
    reg_alloc_granularity = 256  # NVIDIA 以 256 寄存器为分配粒度
    regs_per_block_rounded = (
        (regs_per_warp * warps_per_block + reg_alloc_granularity - 1)
        // reg_alloc_granularity
    ) * reg_alloc_granularity
    blocks_by_regs = config.regs_per_sm // regs_per_block_rounded \
        if regs_per_block_rounded > 0 else 0

    # 限制 4: 共享内存
    blocks_by_smem = config.shared_mem_per_sm // shared_mem_per_block \
        if shared_mem_per_block > 0 else blocks_by_threads

    # 实际 blocks
    active_blocks = min(
        blocks_by_threads,
        blocks_by_sm_limit,
        blocks_by_regs,
        blocks_by_smem,
    )
    active_warps = active_blocks * warps_per_block
    occupancy_pct = (active_warps / config.max_warps_per_sm) * 100

    return {
        "active_blocks": active_blocks,
        "active_warps": active_warps,
        "active_threads": active_blocks * threads_per_block,
        "occupancy_pct": occupancy_pct,
        "limiting_factor": (
            "threads" if blocks_by_threads <= min(blocks_by_sm_limit, blocks_by_regs, blocks_by_smem)
            else "sm_limit" if blocks_by_sm_limit <= min(blocks_by_threads, blocks_by_regs, blocks_by_smem)
            else "registers" if blocks_by_regs <= min(blocks_by_threads, blocks_by_sm_limit, blocks_by_smem)
            else "shared_memory"
        ),
        "regs_per_block_rounded": regs_per_block_rounded,
        "regs_used_pct": (regs_per_block_rounded * active_blocks / config.regs_per_sm) * 100,
        "smem_used_pct": (shared_mem_per_block * active_blocks / config.shared_mem_per_sm) * 100,
    }


def print_analysis(config: SMConfig, threads: int, regs: int, smem: int):
    result = calc_occupancy(config, threads, regs, smem)
    print(f"  块大小={threads:4d}  寄存器/线程={regs:3d}  共享内存/块={smem:5d} B")
    print(f"  → {result['active_warps']:2d} warps / {config.max_warps_per_sm} max  "
          f"({result['occupancy_pct']:.1f}% occupancy)")
    print(f"  → 活跃块: {result['active_blocks']}  活跃线程: {result['active_threads']}")
    print(f"  → 限制因素: {result['limiting_factor']}")
    if result['regs_per_block_rounded'] > 0:
        print(f"  → 寄存器: {result['regs_per_block_rounded']} / 块 "
              f"({result['regs_used_pct']:.0f}% SM 使用)")
    print(f"  → 共享内存: {result['smem_used_pct']:.0f}% SM 使用")
    print()


if __name__ == "__main__":
    gpu = GPUS["RTX 3070 Ti (GA104)"]
    print(f"=== Occupancy 分析: {gpu.name} ===\n")
    print(f"每 SM: {gpu.max_warps_per_sm} warps, "
          f"{gpu.regs_per_sm} 寄存器, {gpu.shared_mem_per_sm//1024} KB shared mem\n")

    # 场景 1: 轻量 Shader (32 regs, 0 shared mem)
    print("场景 1: 轻量 Shader (32 寄存器, 0B shared mem)")
    for threads in [64, 128, 256, 512, 1024]:
        print_analysis(gpu, threads, 32, 0)

    # 场景 2: 中等 Shader (64 regs, 4KB shared)
    print("场景 2: 中等 Shader (64 寄存器, 4KB shared mem)")
    for threads in [64, 128, 256, 512]:
        print_analysis(gpu, threads, 64, 4096)

    # 场景 3: 重 Shader (128 regs, 16KB shared) — register pressure!
    print("场景 3: 重 Shader (128 寄存器, 16KB shared mem) — register pressure!")
    for threads in [64, 128, 256]:
        print_analysis(gpu, threads, 128, 16384)

    # 场景 4: 比较不同 GPU
    print("=== 跨 GPU 对比 (128 threads, 64 regs, 8KB shared) ===")
    for name, cfg in GPUS.items():
        r = calc_occupancy(cfg, 128, 64, 8192)
        print(f"  {name:30s}: {r['occupancy_pct']:5.1f}% ({r['active_warps']} warps)")

# 预期输出（RTX 3070 Ti 关键观察）:
# 场景 1: 32 regs + 1024 threads → 100% occupancy (48 warps)
# 场景 3: 128 regs + 256 threads → 33.3% occupancy (16 warps) ← 被寄存器限制!
# 这就是为什么编译器报告 "register pressure" 时值得关注
```

---

## 3. 练习

### 练习 1: Occupancy 参数扫描 [基础]

用上面的 `occupancy_calc.py`，在你的目标 GPU（或你拥有的 GPU 最近的型号）上进行参数扫描：

1. 固定 `shared_mem_per_block = 0`，遍历 `regs_per_thread` 从 16 到 256，步长 16
   - 找出 occupancy 首次降到 50% 以下的寄存器数
2. 固定 `regs_per_thread = 48`，遍历 `shared_mem_per_block` 从 0 到 100KB，步长 2KB
   - 找出 occupancy 首次降到 50% 以下的 shared memory 大小
3. 写一段总结：你的 Shader 如果要保持 ≥ 50% occupancy，寄存器预算和 shared memory 预算各是多少？

### 练习 2: 分支重排 [进阶]

给定以下 Shader 代码（HLSL）：

```hlsl
// 原始: 分支条件取决于动态的 per-pixel 数据
float4 PSMain(PSInput input) : SV_Target {
    float4 color = g_BaseColor;
    float depth = g_DepthTex.Sample(g_Sampler, input.uv).r;

    if (depth > 0.999) {          // sky pixels — 少数情况
        color = g_SkyColor;
    } else if (depth < 0.1) {     // near pixels — 少数情况
        color = applyFog(color, depth);
    } else {                      // 绝大多数像素
        color = applyLighting(color, input.normal, input.worldPos);
        color = applyShadow(color, depth);
    }
    return color;
}
```

1. 分析这个分支在 GPU 上对 warp divergence 的影响：sky pixel 和 near pixel 穿插在实体像素中间时会发生什么？
2. 不改变语义，重写这个 Shader 以减少 divergence。提示：考虑是否可以用分支 + 提前返回，或重排分支顺序，或使用 `clip()`/`discard`？
3. 在 RenderDoc/NSight 中对比两种实现的 GPU 耗时。
4. 进一步：能否用 Early-Z/stencil 把 sky 和 near 像素在单独的 pass 中剔除？

### 练习 3: 手算 Occupancy [挑战]

已知 AMD RDNA 2 一个 WGP (Workgroup Processor) 的规格：
- 65536 个 VGPR（32-bit 寄存器）
- 最大 32 个 wavefront（wave32 模式）
- 64KB LDS（共享内存）
- 最大 8 个 workgroup 同时驻留
- 波前分配粒度：VGPR 按 256 对齐

一个 workgroup 配置为 `[numthreads(256, 1, 1)]`，Shader 使用 84 个 VGPR 和 12KB LDS。

1. **手工计算**这个 workgroup 配置下的 occupancy（wavefront 数），写出每一步：
   - wavefront 数 = ?
   - VGPR 分配量（含对齐）= ?
   - 从 VGPR 角度看能放几个 workgroup？
   - 从 LDS 角度看能放几个 workgroup？
   - 从最大 workgroup 数看能放几个？
   - 最终 occupancy = ?
2. 用 Python calculator 验证你的计算。
3. 如果将 `numthreads` 改为 `(64, 1, 1)`，保持 84 VGPR 和 12KB LDS，occupancy 如何变化？为什么？

---

## 4. 扩展阅读

- [NVIDIA CUDA C++ Programming Guide — SM Architecture](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#hardware-implementation) — 官方 SM 架构描述
- [AMD RDNA 2 Instruction Set Architecture Reference](https://www.amd.com/en/support/tech-docs/rdna-2-instruction-set-architecture-reference-guide) — Wavefront 模式和调度细节
- [GPUOpen: RDNA Performance Guide — Occupancy](https://gpuopen.com/learn/rdna-performance-guide/) — AMD 官方 occupancy 优化建议
- [Apple Metal Shading Language Specification — Threadgroup Execution](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf) — SIMD-group 和 tile shaders
- [ARM Mali GPU Architecture](https://developer.arm.com/documentation/102468/latest/) — Valhall/G-series 架构详解
- [Imagination PowerVR Tile-Based Rendering](https://docs.imgtec.com/) — TBR 深入文档
- [NVIDIA NSight Compute Kernel Profiling Guide](https://docs.nvidia.com/nsight-compute/) — occupancy 和 register pressure 分析
- *CUDA by Example* (Sanders & Kandrot) — Warp 和 shared memory 章节

---

## 常见陷阱

1. **盲目追求 100% occupancy**：occupancy 只是"潜在隐藏延迟的能力"，不是目标本身。64 VGPR 的 50% occupancy Shader 可能比 32 VGPR 的 100% occupancy Shader 更快——因为前者需要更少指令（中间结果在寄存器中）。**用 Profiler 实测，不要猜**。

2. **忽略波前大小差异**：NVIDIA warp = 32，Mali warp = 16，AMD 可切换 32/64。`numthreads(32, 1, 1)` 在 Mali 上是 2 个 warp，但在 NVIDIA 上只有 1 个。跨平台时 thread group 大小应取各平台波前大小的最小公倍数。

3. **Shared memory padding 过度**：避免 bank conflicts 的 padding 方案如果不对，可能引入新冲突。NVIDIA 在 Kepler 后有 broadcast 机制（同一 warp 的多个线程读同一地址时直接广播），所以有时"32-way conflict"实际只执行一次读。

4. **在 TBR 上像在 IMR 上一样使用 MRT**：多渲染目标（MRT）在 TBR 上消耗 tile memory——每增加一个 32-bit 目标就多吃掉 tile memory。Mali GPU 典型 tile memory 是 16-32KB per core，超过就溢出到 VRAM，batching 优势丧失。

5. **寄存器 spill 的隐蔽性**：编译器 spill 寄存器到 VRAM 的行为不会有任何警告（除非你用 `--ptxas-options=-v` 查看 CUDA 编译输出，或 HLSL 的 `/Fc` 查看汇编）。Spill 让 L1 带宽紧张，且比直接优化寄存器用量慢得多。**始终查看编译器生成的汇编/PTX**。
