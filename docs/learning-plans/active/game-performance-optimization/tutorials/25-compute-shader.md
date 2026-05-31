# Compute Shader 优化
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: GPU 架构简析 (23)、GPU 带宽优化 (24)

---

## 1. 概念讲解

### 为什么需要这个？

Compute Shader 是 GPU 编程中最高自由度的工具。它跳出了图形管线的限制，让你直接调度成千上万的线程去处理任意数据。现代游戏引擎中 Compute Shader 无处不在：

- **粒子模拟**（数万粒子每帧更新 → GPU 胜过 CPU）
- **后处理**（Bloom、深度雾、SSAO → 比 Pixel Shader 更灵活**
- **Culling**（GPU-driven rendering 的核心 — 在 GPU 上做视锥体/遮挡剔除）
- **GPU Skinning**（骨骼动画计算移到 GPU）
- **Clustered/Forward+ 光照**（光源分配和 tile 列表构建）
- **地形和海洋模拟**（FFT 水波、高度场侵蚀）

但 Compute Shader 的自由度也带来了优化挑战。同样一个并行归约，写的方式不同性能差 10 倍以上。本节覆盖 Compute Shader 中的核心优化模式。

### 核心思想

#### Dispatch 模型

```
                      Grid (3D)
                  ┌─────────────────┐
                  │ ┌──┐ ┌──┐ ┌──┐ │
                  │ │TG│ │TG│ │TG│ │  每个方块 = 一个 Thread Group
                  │ └──┘ └──┘ └──┘ │  每组 64-1024 个线程
                  │ ┌──┐ ┌──┐ ┌──┐ │  所有组内线程共享 LDS/Shared Memory
                  │ │TG│ │TG│ │TG│ │
                  │ └──┘ └──┘ └──┘ │
                  └─────────────────┘
                  总线程数 = grid_dim × TG_dim
```

关键属性：
- **Thread Group 内的线程**：可以访问同一块 shared memory，可以通过 `barrier` 同步
- **不同 Thread Group 之间**：完全独立，不能同步，不能直接通信
- **Dispatch 是异步的**：`Dispatch()` 只是把任务放入 Compute Queue。需要 fence 或资源的 UAV barrier 才能与后续操作同步

#### Occupancy 与 Thread Group 大小的选择

回忆第 23 节的结论：warp/wavefront 大小决定 TG 大小的下限。**TG 大小必须是 warp 大小的整数倍**，否则会有部分 warp 中线程闲置。

实际选择 TG 大小时考虑：

| TG 大小 | 优势 | 劣势 |
|--------|------|------|
| 32 (1 warp) | 最灵活 | Occupancy 受限，shared memory 利用率最低 |
| 64 (2 warps) | AMD 单 wave64 友好 | NVIDIA 上 2 个 warp — 隐藏延迟能力弱 |
| 128 (4 warps) | 平衡点 | — |
| 256 (8 warps) | 高 occupancy，好的延迟隐藏 | 寄存器压力大可能降 occupancy |
| 512+ | 最大化 occupancy | 寄存器 / shared memory 通常成为瓶颈 |

**经验法则**：
- NVIDIA: 128 或 256，避免 32（浪费 SM 调度能力）
- AMD: 64 或 128（wave64 模式），256 也是好的
- Mali (16-wide): 64 或 128（16 的倍数）
- 综合跨平台: **128 或 256**

#### Shared Memory 优化

**与 L1 Cache 的差异**：
Shared memory 由程序员显式管理，比依赖 L1 Cache 更可预测。L1 Cache 会被其他 SM 操作、纹理采样、常量数据竞争，而 Shared Memory 完全在你掌控中。

**Bank Conflict 模式与解决**（已在 23 节展示过）：

```hlsl
// 问题: stride 访问引发 bank conflict
float val = sharedData[tid * stride];  // tid=0,1,2,... stride>1

// 解决: padding 打破对 bank 的映射
groupshared float sharedData[256 + 8];  // +padding 改变 bank mapping
```

**使用 Shared Memory 作为用户管理的缓存**：

```hlsl
// 场景: 多次从全局内存读取同一数据
// 不用 shared memory: 每次读都可能 miss L1
float total = 0;
for (int i = 0; i < 100; i++) {
    total += globalData[baseIdx + i];  // 100 次全局读
}

// 用 shared memory: 一次性批量加载，后续从 shared memory 读
groupshared float tile[128];
// 线程 i 负责加载 tile[i]
tile[threadIdx.x] = globalData[baseIdx + threadIdx.x];
GroupMemoryBarrierWithGroupSync();
total = 0;
for (int i = 0; i < 100; i++) {
    total += tile[i];  // 100 次 shared memory 读 (~20 cycles vs ~400)
}
```

#### Coalesced 内存访问

**Struct-of-Arrays (SoA) vs Array-of-Structs (AoS)**：

```cpp
// AoS — 灾难性的 GPU 访问
struct Particle {
    float3 position;
    float3 velocity;
    float lifetime;
    float4 color;
};
// sizeof(Particle) = 56 bytes
// 当 warp 的 32 个线程都读 position 时:
// 线程 0 读 offset 0, 线程 1 读 offset 56, 线程 2 读 offset 112...
// 每个线程触发不同的 cache line → 32 次独立读 → ~32× 带宽浪费

// SoA — 高性能 GPU 访问
struct ParticleBuffer {
    float3 positions[N];
    float3 velocities[N];
    float  lifetimes[N];
    float4 colors[N];
};
// 当 warp 的 32 个线程都读 position:
// 线程 0-31 读连续的 32 个 float3 → 1-2 个 cache line → 完全合并
```

在 HLSL 中，SoA 布局通过多个 `StructuredBuffer` 或 `ByteAddressBuffer` 实现：

```hlsl
StructuredBuffer<float3> g_Positions : register(t0);
StructuredBuffer<float3> g_Velocities : register(t1);
// 线程 i 访问: pos = g_Positions[i]; vel = g_Velocities[i];
// 合并访问，完美。
```

#### Scatter vs Gather

- **Gather**（读连续 → 写连续）：每个线程从分散的源地址读，写入自己的连续目标地址。读操作合并性由源数据布局决定。
- **Scatter**（读连续 → 写分散）：每个线程从连续地址读，写入分散的目标地址。**写操作几乎不可能合并**，因为每个线程写的目标地址不同。

**Gather 总是优于 Scatter**。在可能的情况下，把 scatter 转换为 gather（加一个中间 pass）：

```hlsl
// Bad: Scatter（每个 particle 写到 grid cell 的任意位置）
uint cellIndex = ComputeCell(particlePositions[threadIdx]);
cellParticleLists[cellIndex][cellCounts[cellIndex]++] = threadIdx;

// Better: 先 sort/count，再 gather
// Pass 1: 计算每个 cell 的 particle 数 (atomic 写 grid)
// Pass 2: Prefix sum 得到各 cell 的偏移
// Pass 3: 每个 particle 计算自己的 cell，根据 prefix sum 确定写位置
//         但同一个 cell 内的多个 particle 写连续地址 → 写也是合并的
```

#### Atomic 操作的代价

Atomic 操作（`InterlockedAdd`、`InterlockedMax` 等）在 GPU 上有特殊代价：

- **无竞争时**：atomic 对同一个 L2 cache line → 约 50-100 周期
- **大量竞争时**：32 个线程同时 atomic 同一地址 → 串行化，~32× 单个 atomic 的延迟
- **跨 SM 竞争更糟**：不同 SM 的线程竞争同一地址 → 通过 L2 或 VRAM 仲裁

优化策略：
- **减少 atomic 次数**：用 shared memory 做 local atomic，最后汇总
- **分散 atomic 目标**：每个 TG 有自己的计数器数组
- **考虑使用 `InterlockedAdd` 的返回值减少后续访问**

```hlsl
// Bad: 所有线程竞争同一个 counter
uint globalIdx;
InterlockedAdd(g_Counter, 1, globalIdx);  // 全局竞争

// Good: 每 TG 独立的 counter
groupshared uint localCounter;
// 初始化一次
if (threadIdx.x == 0) localCounter = 0;
GroupMemoryBarrierWithGroupSync();
// TG 内 atomic
uint localIdx;
InterlockedAdd(localCounter, 1, localIdx);  // 仅 TG 内竞争
// 最后由 TG 内最后一个线程提交
GroupMemoryBarrierWithGroupSync();
if (threadIdx.x == 0) {
    InterlockedAdd(g_Counter, localCounter, localIdx);  // 每 TG 一次
}
```

#### 常见使用场景的模式总结

| 场景 | 推荐模式 | 关键优化点 |
|------|---------|-----------|
| 粒子模拟 | SoA 布局，per-particle 线程 | 合并读取 position/velocity |
| 并行归约 | Shared memory + tree reduction | Bank conflict 避免，最后 warp 优化 |
| 矩阵转置 | Tiled shared memory | Coalesced 读 + coalesced 写 |
| Histogram | Local histogram per TG | Shared memory atomic + 最后合并 |
| Prefix Sum | Work-efficient scan (Blelloch) | 多 pass，每个 pass 翻倍 stride |
| GPU Culling | Indirect draw args + atomic | 每个物体一个线程，compact 输出 |
| FFT | Cooley-Tukey in shared memory | 避免 bank conflict 的 twiddle 访问 |
| Clustered Light | Per-tile light assignment | SoA light data, shared memory for tile |

---

## 2. 代码示例

### 示例 A: Naive vs Coalesced 矩阵转置 (HLSL)

```hlsl
// matrix_transpose.hlsl
// 基于 NVIDIA GPU Gems 的优化转置实现

// 全局常量
cbuffer Constants : register(b0) {
    uint matrixDim;     // 方阵维度
};

// === 版本 1: Naive — Scatter 写，性能灾难 ===
// 读是合并的，写是完全分散的（stride=N）
StructuredBuffer<float> g_Input  : register(t0);
RWStructuredBuffer<float> g_Output : register(u0);

[numthreads(16, 16, 1)]
void TransposeNaive(uint3 dtid : SV_DispatchThreadID) {
    uint row = dtid.y;
    uint col = dtid.x;
    if (row >= matrixDim || col >= matrixDim) return;

    float val = g_Input[row * matrixDim + col];
    // 写: col * N + row → 不同线程写分散地址 → 每次写触发独立 transaction
    g_Output[col * matrixDim + row] = val;
}

// === 版本 2: Tiled — 使用 shared memory 同时合并读和写 ===
groupshared float g_Tile[16][16 + 1];  // +1 是 padding，防止 bank conflict!

[numthreads(16, 16, 1)]
void TransposeTiled(uint3 dtid : SV_DispatchThreadID, uint3 gtid : SV_GroupThreadID) {
    uint row = dtid.y;
    uint col = dtid.x;

    // Step 1: 合并读 → shared memory
    if (row < matrixDim && col < matrixDim) {
        g_Tile[gtid.y][gtid.x] = g_Input[row * matrixDim + col];
    }
    GroupMemoryBarrierWithGroupSync();

    // Step 2: 从 shared memory 读转置位置 → 合并写
    // 线程 (x,y) 现在处理目标位置 (y,x) → 即 (gtid.x, gtid.y) 的新位置
    uint outRow = dtid.y;
    uint outCol = dtid.x;
    // 实际上这里需要把 tile 的 (x,y) 映射到全局的转置位置
    // 全局: 线程负责 outRow = blockCol*16 + gtid.x, outCol = blockRow*16 + gtid.y
    uint blockRow = gtid.y;  // dtid.y / 16 → shared memory 中是 block-local
    // 更清晰的重写:
    // 目标: 转置矩阵中的 (col, row) → 即 (dtid.x, dtid.y)
    // shared memory 中 tile[gtid.y][gtid.x] 存储的是 input[row][col]
    // 读取 tile[gtid.x][gtid.y] 就得到了 input[col][row] → 正好是转置!
    float val = g_Tile[gtid.x][gtid.y];

    // 写入转置后的全局位置
    if (outRow < matrixDim && outCol < matrixDim) {
        g_Output[outRow * matrixDim + outCol] = val;
    }
}
```

### 示例 B: 并行归约 (Parallel Reduction) 的优化演进

```hlsl
// reduction.hlsl — 并行求和：从 naive 到优化的 4 个版本

cbuffer Constants : register(b0) {
    uint dataCount;
};

// 全局 buffer
StructuredBuffer<float> g_Input   : register(t0);
RWStructuredBuffer<float> g_Output : register(u0);

#define THREADS 256

// === 版本 1: Naive InterlockedAdd — 所有线程竞争同一个地址 ===
// 性能: 极差 (所有 atomic 串行化)
[numthreads(THREADS, 1, 1)]
void ReductionNaive(uint3 dtid : SV_DispatchThreadID) {
    uint idx = dtid.x;
    if (idx < dataCount) {
        InterlockedAdd(g_Output[0], asuint(g_Input[idx]));  // 全局竞争!
    }
}
// 注意: InterlockedAdd 不支持 float，实际需要 CAS 循环或 int 版本


// === 版本 2: Shared Memory 归约 — 无 bank conflict ===
// 每 TG 独立归约，最后汇总
groupshared float g_SharedSum[THREADS];

[numthreads(THREADS, 1, 1)]
void ReductionShared(uint3 dtid : SV_DispatchThreadID,
                     uint3 gtid : SV_GroupThreadID) {
    uint idx = dtid.x;

    // Step 1: 加载到 shared memory
    g_SharedSum[gtid.x] = (idx < dataCount) ? g_Input[idx] : 0.0;
    GroupMemoryBarrierWithGroupSync();

    // Step 2: Tree reduction
    // Stride 从 1 开始翻倍: 1, 2, 4, 8, ...
    for (uint stride = 1; stride < THREADS; stride *= 2) {
        // 线程 0,2,4,... 参与第一轮; 线程 0,4,8,... 参与第二轮...
        // 但这样有 bank conflict! stride=1 → 相邻线程访问相邻 bank → OK
        // stride=2 → 线程 0→bank0, 线程 2→bank2 → 还是 OK
        // 关键是: 同一 warp 内线程的 stride 不是 1 时会有冲突
        uint index = 2 * stride * gtid.x;
        if (index + stride < THREADS) {
            g_SharedSum[index] += g_SharedSum[index + stride];
        }
        GroupMemoryBarrierWithGroupSync();
    }

    // Step 3: 线程 0 写入全局
    if (gtid.x == 0) {
        // 使用 atomic 加到全局结果（每 TG 一次，而非每线程）
        uint prev;
        InterlockedAdd(g_Output[0], asuint(g_SharedSum[0]), prev);
    }
}


// === 版本 3: 无 bank conflict 的归约（Sequential Addressing） ===
// 翻倍 stride 改为 sequential: 后半加到前半
groupshared float g_SharedV3[THREADS];

[numthreads(THREADS, 1, 1)]
void ReductionNoBankConflict(uint3 dtid : SV_DispatchThreadID,
                             uint3 gtid : SV_GroupThreadID) {
    uint idx = dtid.x;
    g_SharedV3[gtid.x] = (idx < dataCount) ? g_Input[idx] : 0.0;
    GroupMemoryBarrierWithGroupSync();

    // Sequential addressing: 每次迭代，活跃线程数减半
    // 线程 0..127 读 0..127 和 128..255 → 所有访问连续 → 无 bank conflict
    for (uint s = THREADS / 2; s > 0; s >>= 1) {
        if (gtid.x < s) {
            g_SharedV3[gtid.x] += g_SharedV3[gtid.x + s];
        }
        GroupMemoryBarrierWithGroupSync();
    }

    if (gtid.x == 0) {
        // 直接写（如果每个 TG 结果写不同位置）
        g_Output[dtid.y * 1024 + dtid.z] = g_SharedV3[0];
    }
}


// === 版本 4: 完全展开的最后 warp（避免不必要的 barrier） ===
// 当活跃线程 ≤ 32 时，同一 warp 内不需要显式 barrier
[numthreads(THREADS, 1, 1)]
void ReductionWarpOptimized(uint3 dtid : SV_DispatchThreadID,
                            uint3 gtid : SV_GroupThreadID) {
    uint idx = dtid.x;
    g_SharedV3[gtid.x] = (idx < dataCount) ? g_Input[idx] : 0.0;
    GroupMemoryBarrierWithGroupSync();

    // Phase 1: 跨 warp 归约（需要 barrier）
    for (uint s = THREADS / 2; s > 32; s >>= 1) {
        if (gtid.x < s) {
            g_SharedV3[gtid.x] += g_SharedV3[gtid.x + s];
        }
        GroupMemoryBarrierWithGroupSync();
    }

    // Phase 2: 最后的 warp（32 线程）不需要 barrier
    // 因为同一 warp 内线程是 lock-step 执行的
    if (gtid.x < 32) {
        // 手动展开最后 5 轮
        float v = g_SharedV3[gtid.x];
        v += g_SharedV3[gtid.x + 32];
        v += g_SharedV3[gtid.x + 16];
        v += g_SharedV3[gtid.x + 8];
        v += g_SharedV3[gtid.x + 4];
        v += g_SharedV3[gtid.x + 2];
        v += g_SharedV3[gtid.x + 1];
        g_SharedV3[gtid.x] = v;
    }

    if (gtid.x == 0) {
        g_Output[dtid.y * 1024 + dtid.z] = g_SharedV3[0];
    }
}
```

### 示例 C: 粒子模拟 — SoA + Shared Memory (HLSL + C++)

```hlsl
// particle_sim.hlsl
// 基于 SoA 的粒子邻域搜索 + 力计算

cbuffer ParticleConstants : register(b0) {
    uint  particleCount;
    uint  gridDim;           // 均匀网格的维度
    float cellSize;
    float dt;
    float3 gravity;
    float  damping;
    float  particleRadius;
    float  restDensity;
    float  pressureConstant;
};

// SoA 布局
StructuredBuffer<float3> g_Positions  : register(t0);  // N × float3
StructuredBuffer<float3> g_Velocities : register(t1);  // N × float3
RWStructuredBuffer<float3> g_NewPositions  : register(u0);
RWStructuredBuffer<float3> g_NewVelocities : register(u1);

// Grid 辅助数据结构
RWStructuredBuffer<uint> g_GridCellStart : register(u2);  // gridDim^3
RWStructuredBuffer<uint> g_GridCellEnd   : register(u3);  // gridDim^3
RWStructuredBuffer<uint> g_GridParticles  : register(u4); // N (排序后)

[numthreads(256, 1, 1)]
void SimulateParticles(uint3 dtid : SV_DispatchThreadID) {
    uint pid = dtid.x;
    if (pid >= particleCount) return;

    // 合并读取（SoA → 32 线程连读 32 个 Vec3 → 完美合并）
    float3 pos = g_Positions[pid];
    float3 vel = g_Velocities[pid];

    // 确定粒子所在 grid cell
    int3 cell = int3(pos / cellSize);
    cell = clamp(cell, int3(0, 0, 0), int3(gridDim - 1, gridDim - 1, gridDim - 1));
    uint cellIdx = cell.x + cell.y * gridDim + cell.z * gridDim * gridDim;

    // 检查 27 个相邻 cell
    float3 force = gravity;
    int neighborCount = 0;

    for (int dz = -1; dz <= 1; dz++) {
        for (int dy = -1; dy <= 1; dy++) {
            for (int dx = -1; dx <= 1; dx++) {
                int3 nc = cell + int3(dx, dy, dz);
                if (any(nc < 0) || any(nc >= gridDim)) continue;

                uint nCellIdx = nc.x + nc.y * gridDim + nc.z * gridDim * gridDim;
                uint start = g_GridCellStart[nCellIdx];
                uint end = g_GridCellEnd[nCellIdx];

                // 遍历相邻 cell 内的所有粒子
                for (uint j = start; j < end; j++) {
                    uint otherPid = g_GridParticles[j];
                    if (otherPid == pid) continue;

                    float3 otherPos = g_Positions[otherPid];  // 随机访问!
                    float3 diff = pos - otherPos;
                    float dist2 = dot(diff, diff);
                    float radius2 = particleRadius * particleRadius;

                    if (dist2 < radius2 && dist2 > 0.0001) {
                        // SPH-like 压力
                        float dist = sqrt(dist2);
                        float q = dist / particleRadius;
                        // 简化的压力核函数
                        float pressure = pressureConstant * (1.0 - q) * (1.0 - q);
                        force += normalize(diff) * pressure;
                        neighborCount++;
                    }
                }
            }
        }
    }

    // Euler 积分
    float3 newVel = vel + force * dt;
    newVel *= damping;
    float3 newPos = pos + newVel * dt;

    g_NewVelocities[pid] = newVel;
    g_NewPositions[pid] = newPos;
}
```

```cpp
// particle_sim_host.cpp — C++ host 端调度代码
// 编译: 需要 D3D12/Vulkan 框架

#include <vector>
#include <DirectXMath.h>
using namespace DirectX;

struct ParticleSystem {
    // SoA buffers
    std::vector<XMFLOAT3> positions;
    std::vector<XMFLOAT3> velocities;
    std::vector<XMFLOAT3> newPositions;
    std::vector<XMFLOAT3> newVelocities;

    // Grid
    std::vector<uint32_t> gridCellStart;
    std::vector<uint32_t> gridCellEnd;
    std::vector<uint32_t> gridParticles;

    uint32_t particleCount;
    uint32_t gridDim;

    void initialize(uint32_t count, float worldSize) {
        particleCount = count;
        gridDim = uint32_t(worldSize / cellSize) + 1;

        positions.resize(count);
        velocities.resize(count);
        newPositions.resize(count);
        newVelocities.resize(count);

        gridCellStart.resize(gridDim * gridDim * gridDim);
        gridCellEnd.resize(gridDim * gridDim * gridDim);
        gridParticles.resize(count);

        // 初始化粒子位置，散布在球体内
        for (uint32_t i = 0; i < count; i++) {
            // 球形分布
            float theta = float(rand()) / RAND_MAX * 2.0f * XM_PI;
            float phi = acos(2.0f * float(rand()) / RAND_MAX - 1.0f);
            float r = pow(float(rand()) / RAND_MAX, 1.0f / 3.0f) * worldSize * 0.4f;
            positions[i] = XMFLOAT3(
                r * sin(phi) * cos(theta),
                r * sin(phi) * sin(theta),
                r * cos(phi)
            );
            velocities[i] = XMFLOAT3(0, 0, 0);
        }
    }

    // GPU Buffer 管理（省略细节）
    // createBuffers(), uploadToGPU(), downloadFromGPU()

    void simulateFrame(float dt) {
        // Step 1: Build grid (将粒子分配到 grid cell)
        // 通过 sorting 或 atomic 构建 cell-particle 映射
        buildGrid();

        // Step 2: Dispatch compute shader
        // 256 线程 per group, 足以覆盖典型粒子数
        uint32_t groups = (particleCount + 255) / 256;
        // pCommandList->SetComputeRootSignature(...)
        // pCommandList->SetPipelineState(computePSO)
        // pCommandList->Dispatch(groups, 1, 1)

        // Step 3: UAV barrier (确保粒子更新完成)
        // pCommandList->ResourceBarrier(...)

        // Step 4: Swap buffers (双缓冲)
        std::swap(positions, newPositions);
        std::swap(velocities, newVelocities);
    }

    void buildGrid() {
        // 简化: 用 CPU 端排序演示
        // 实际 GPU 实现: 用 atomic 计数 + prefix sum
        std::fill(gridCellStart.begin(), gridCellStart.end(), 0);
        std::fill(gridCellEnd.begin(), gridCellEnd.end(), 0);

        // 计数每个 cell 的粒子数
        for (uint32_t i = 0; i < particleCount; i++) {
            XMFLOAT3 pos = positions[i];
            int cx = int(pos.x / cellSize);
            int cy = int(pos.y / cellSize);
            int cz = int(pos.z / cellSize);
            cx = std::clamp(cx, 0, int(gridDim) - 1);
            cy = std::clamp(cy, 0, int(gridDim) - 1);
            cz = std::clamp(cz, 0, int(gridDim) - 1);
            uint32_t cellIdx = cx + cy * gridDim + cz * gridDim * gridDim;
            gridCellEnd[cellIdx]++;
        }

        // Prefix sum → gridCellStart
        uint32_t sum = 0;
        for (uint32_t i = 0; i < gridDim * gridDim * gridDim; i++) {
            gridCellStart[i] = sum;
            sum += gridCellEnd[i];
            gridCellEnd[i] = sum;  // 现在 end 是 exclusive end
        }

        // 填入粒子
        std::vector<uint32_t> offsets = gridCellStart;
        for (uint32_t i = 0; i < particleCount; i++) {
            XMFLOAT3 pos = positions[i];
            int cx = int(pos.x / cellSize);
            int cy = int(pos.y / cellSize);
            int cz = int(pos.z / cellSize);
            cx = std::clamp(cx, 0, int(gridDim) - 1);
            cy = std::clamp(cy, 0, int(gridDim) - 1);
            cz = std::clamp(cz, 0, int(gridDim) - 1);
            uint32_t cellIdx = cx + cy * gridDim + cz * gridDim * gridDim;
            gridParticles[offsets[cellIdx]++] = i;
        }
    }

    static constexpr float cellSize = 1.0f;
};
```

---

## 3. 练习

### 练习 1: 归约性能对比 [基础]

实现并测量 4 个归约版本的性能：
1. 用上面提供的 4 个版本（Naive atomic、Shared Memory naive、Sequential addressing、Warp-optimized）
2. 对不同数据量（256, 1024, 4096, 16384, 65536, 262144 元素）测试
3. 用 RenderDoc/NSight 或 D3D12 Timestamp Query 测量 GPU 耗时
4. 画图对比：X 轴 = 数据量，Y 轴 = 微秒
5. 解释：为什么小数据量时 warp-optimized 优势不明显，大数据量时明显？

### 练习 2: 设计一个 GPU Frustum Culling [进阶]

设计一个 Compute Shader 来做视锥体剔除：

1. **输入**：N 个物体的 BoundingSphere（world-space center + radius）
2. **输出**：
   - `visibleIndices[]`：可见物体的 index 列表（compact）
   - `visibleCount`：可见物体总数
   - `indirectDrawArgs`：`DrawIndexedInstanced` 的 `SV_DispatchIndirect` 参数

3. **约束**：
   - 每个物体一个线程 → 判断其 sphere 与 6 个 frustum plane 的关系
   - 可见物体写入 compact 列表（不能有空隙）
   - `indirectDrawArgs` 供后续 `DrawIndexedInstancedIndirect` 使用

4. 写出完整的 HLSL 代码和 C++ dispatch 代码
5. 分析：`InterlockedAdd` 在这里是否是瓶颈？如果是，如何优化？

### 练习 3: Matrix Multiply（Tiled + Shared Memory）[挑战]

实现 GPU 上的矩阵乘法，使用 tiled shared memory 优化：

1. 实现 3 个版本：
   - Naive: 每个线程直接读全局内存
   - Shared Memory: 每个 tile 加载到 shared memory
   - 多 tile 累积: 多个 tile 加载和累积（正确版本**）
2. 对 1024×1024 矩阵测试性能
3. 用 NSight Compute 查看 `l1tex__throughput` 和 `smem__throughput` 对比
4. 计算实际达到的 TFLOPS 与理论峰值的比例
5. 解释为什么 naive 版本只能达到理论峰值的 5-15%，而 tiled 版本可以达到 60-80%

---

## 4. 扩展阅读

- [NVIDIA: CUDA C++ Best Practices Guide — Shared Memory](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#shared-memory) — Bank conflict 详解
- [AMD: RDNA Performance Guide — Compute Shaders](https://gpuopen.com/learn/rdna-performance-guide/) — Wavefront 和 occupancy
- [Microsoft: DirectX Compute Shader Overview](https://learn.microsoft.com/en-us/windows/win32/direct3d11/direct3d-11-advanced-stages-compute-shader) — DX11/12 compute 基础
- *GPU Gems 3* — Chapter 39: Parallel Prefix Sum (Scan) with CUDA — 经典并行 scan 实现
- [NVIDIA: Parallel Reduction](https://developer.download.nvidia.com/assets/cuda/files/reduction.pdf) — Mark Harris 的归约优化全系列
- [Optimizing Parallel Reduction in CUDA](https://developer.download.nvidia.com/compute/cuda/1.1-Beta/x86_website/projects/reduction/doc/reduction.pdf) — 每一步优化的详细解释
- [Vulkan Compute Shader Best Practices](https://developer.nvidia.com/blog/vulkan-dos-and-donts/) — Vulkan compute 注意事项
- [Intel: Compute Architecture Guide](https://www.intel.com/content/www/us/en/developer/articles/guide/xe-hpg-compute-architecture.html) — Intel Arc 的 compute 特性
- [GDC 2017: GPU-Driven Rendering with Compute Shaders](https://www.gdcvault.com/) — Ubisoft 的 compute culling 实践

---

## 常见陷阱

1. **TG 大小不是 wavefront 的倍数**：`numthreads(100, 1, 1)` 在 32-wide 的 GPU 上产生 3 个部分填充的 warp（32 + 32 + 32, 但最后一个只有 4 个活跃线程 + 28 个闲置）。不仅浪费执行槽，还浪费寄存器和 shared memory。始终用 64, 128, 256, 512。

2. **在 shared memory 中忘记 barrier**：写入 shared memory 后没有 `GroupMemoryBarrierWithGroupSync()` 就读取 → 同一个 warp 内可能读到旧值（warp 内没有数据竞争，但跨 warp 有）。规则：任何写入 shared memory 后如果其他线程需要读，必须 barrier。

3. **`GroupMemoryBarrierWithGroupSync` 在分支内**：如果 barrier 不在所有线程执行的路径上，会死锁。编译器通常会拒绝，但如果通过间接方式绕过就不会。barrier 必须在无条件执行路径上。

4. **Atomic 天真主义**：初次使用 compute shader 的人常把 atomic 当成万能工具（"我就 atomic 加到全局 counter 上不就好了"）。一个全局 counter 被 10000 个线程竞争 = 灾难。设计时要问：能否减少 atomic 次数？能否 local atomic + 最后合并？

5. **大 shared memory 分配降 occupancy**：每个 thread group 申请 48KB shared memory，SM 有 100KB → 最多 2 个 TG per SM。如果每个 TG 只有 64 线程，occupancy = 2×2/48 = 8% → 几乎无法隐藏延迟。**Shared memory 大小和 thread group 数量需要一起考虑**。

6. **CPU 端过量 Dispatch**：在循环中每帧 dispatch 100 个小型 compute shader → 每次 dispatch 都有 driver overhead（~5-20 µs per dispatch）。尽量合并为更大的 dispatch，或使用 indirect dispatch。
