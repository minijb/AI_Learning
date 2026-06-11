---
title: "GPU 带宽优化 — 纹理压缩与 Tiling"
updated: 2026-06-05
---

# GPU 带宽优化 — 纹理压缩与 Tiling
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50min
> 前置知识: GPU 架构简析 (23)

---

## 1. 概念讲解

### 为什么需要这个？

你的游戏在 4K 下一帧需要渲染多少数据？粗略算一笔账：

```
G-Buffer (6 targets × 32-bit) × 3840 × 2160 = 6 × 4 × 8.3M = 199 MB/frame
Shadow map (2048² × 32-bit × 4 cascades) = 64 MB
Textures sampled (~20 textures × 1024² × 4 bytes, mipmapped ≈ 1.33×) = 107 MB
Depth buffer (32-bit) = 33 MB
Total per frame ≈ 400 MB (仅 GPU 访问，不含 CPU)

60fps: 400 MB × 60 = 24 GB/s
```

这还是在 **没有 overdraw** 的情况下。实际场景中 overdraw 因子（同一像素被绘制次数）通常在 1.5-3.0 之间，引入半透明则可能更高。所以 4K 60fps 的实际带宽需求轻松超过 50 GB/s。

你的 RTX 3070 Ti 有 608 GB/s 带宽——看起来绰绰有余。但：
- 移动端 Mali GPU 只有 51.2 GB/s（LPDDR5 6400 MT/s × 64-bit）
- 主机共享内存（PS5 448 GB/s，但 CPU 也要吃）
- 你的带宽不只是渲染在用：Compute Shader、物理、后处理、光线追踪都在抢

带宽瓶颈是现代游戏性能的最常见瓶颈之一，也是最容易被忽视的。

### 核心思想

#### 带宽数字的真实含义

| GPU | 带宽 | 类型 | 位宽 | 备注 |
|-----|------|------|------|------|
| RTX 4090 | 1008 GB/s | GDDR6X | 384-bit | 当前桌面天花板 |
| RTX 3070 Ti | 608 GB/s | GDDR6X | 256-bit | — |
| RTX 4060 | 272 GB/s | GDDR6 | 128-bit | 注意! 比 3060 Ti 还低 |
| RX 7900 XTX | 960 GB/s | GDDR6 | 384-bit | — |
| Steam Deck | 88 GB/s | LPDDR5 | 128-bit | CPU+GPU 共享 |
| iPhone 15 Pro (A17) | 51.2 GB/s | LPDDR5 | 64-bit | CPU+GPU+ANE 共享 |
| Mali G710 (旗舰) | ~64 GB/s | LPDDR5 | 64-bit | 典型共享配置 |

**关键顿悟**：RTX 4060（272 GB/s）跑 4K 游戏时，即使核心算力够，带宽也很可能是瓶颈。这就是为什么中端卡在 4K 下表现断崖式下降——不是算力问题，是带宽问题。

#### 带宽公式

```
GPU Bandwidth Usage (bytes/frame) =
    Σ (Resource_Size × Access_Count × Compression_Ratio)

其中:
- Resource_Size = Resolution_X × Resolution_Y × Bytes_Per_Pixel
- Access_Count = 写入次数 + 读取次数（含 overdraw 因子）
- Compression_Ratio = 1.0 (未压缩) ～ 0.25 (BC7 高质量) ～ 0.125 (BC1)
```

对于渲染目标：
```
RT Bandwidth = Width × Height × BPP × (1 write + N read for sampling)
              × Overdraw_Factor
              × (1 - DCC_Efficiency)
```

#### 纹理压缩格式

现代 GPU 的纹理压缩是在 **硬件中解码** 的——数据在 VRAM 中以压缩格式存储，Shader 采样时硬件即时解压，对 Shader 透明。这带来三重收益：
1. VRAM 占用减少（8GB 显存能放更多纹理）
2. 带宽减少（从 VRAM 读取的数据量降低）
3. Cache 命中率提升（更多纹理可以留在 L2 中）

**桌面格式（BCn 系列，即 DXTC/S3TC）：**

| 格式 | 压缩比 | 每像素 | Alpha | 适合 |
|------|--------|--------|-------|------|
| BC1 (DXT1) | 8:1 | 4 bpp | 1-bit | 不透明 diffuse，无 alpha |
| BC3 (DXT5) | 4:1 | 8 bpp | 8-bit | 带 alpha 的 diffuse（法线贴图也可用） |
| BC4 | 4:1 | 4 bpp | — | 单通道灰度（高度图、roughness） |
| BC5 | 2:1 | 8 bpp | — | 双通道（法线贴图标准选择：仅存 RG，重建 B） |
| BC6H | 4:1 | 8 bpp | — | HDR (FP16) 纹理，如 HDR 天空盒 |
| BC7 | 4:1 | 8 bpp | 8-bit | 高质量 RGBA，比 BC3 好很多 |

BC7 是现代游戏 diffuse/specular 的最佳选择：8 bpp 下质量显著优于 BC3，且支持 alpha。

**BC5 的法线贴图存储技巧**：
```hlsl
// 压缩时: 只存法线的 X 和 Y 分量到 BC5 的两个通道
// 解压时在 Shader 中重建 Z:
float3 normal;
normal.xy = normalTex.Sample(sampler, uv).rg * 2.0 - 1.0;  // BC5 解码 [0,1] → [-1,1]
normal.z = sqrt(saturate(1.0 - dot(normal.xy, normal.xy)));  // 重建 Z
```

**移动格式（ASTC）：**

ASTC (Adaptive Scalable Texture Compression) 是移动端的统一格式。它支持从 4×4 到 12×12 的 block 大小（对应 8.0 bpp 到 0.89 bpp），且同时支持 LDR/HDR 和 2D/3D 纹理。

| Block 大小 | bpp | 典型用途 |
|-----------|-----|---------|
| 4×4 | 8.00 | 高质量带 alpha (类似 BC7) |
| 5×5 | 5.12 | 高质量 diffuse |
| 6×6 | 3.56 | 标准 diffuse（推荐） |
| 8×8 | 2.00 | 低精度 diffuse，AO 贴图 |
| 5×4 | 6.40 | 法线贴图 |
| 6×5 | 4.27 | roughness/metallic 贴图 |

ASTC 的核心优势是 **灵活性**：你可以为每张贴图选择不同的压缩率。法线可以 5×5，AO 可以 8×8，diffuse 可以 6×6 或 4×4。

**Apple GPU 的独特路径**：Metal 3 支持 ASTC HDR，且配合 Apple 芯片的专用纹理压缩硬件，性能极佳。

**Adreno GPU (Snapdragon)** 同时支持 ASTC 和 Adreno 专有的 **UBWC (Universal Bandwidth Compression)**，后者是硬件透明的无损压缩，对渲染目标和纹理都有效。

#### Mipmapping 与带宽

Mipmap 不仅仅是为了消除远处纹理的锯齿。在带宽层面，mipmapping 的收益被广泛低估：

```
无 mipmap: 远距离采样 → 相邻像素访问纹理中相距很远的纹素
         → Cache miss 频繁 → 每次采样都触发 VRAM 读取
         → 带宽消耗 = 采样次数 × 单次 cache line 大小（通常 64-128 bytes）

有 mipmap: 远距离采样 → 使用高层 mip（小分辨率）
         → 相邻像素访问紧凑的纹素 → Cache 命中率高
         → 且读取的数据量本身就少得多
```

具体数字：一个 1024² 的纹理完整 mip chain 只比原始纹理多 ~33% 的存储。但这 33% 的投入带来的带宽节省可达 50% 以上（在大量远距离采样场景）。

**启用 mipmapping 的正确方式**：
- 对场景中的所有纹理（除了 UI 和精确纹理如 LUT）启用 mipmapping
- 移动端：使用 Vulkan 的 `VK_SAMPLER_MIPMAP_MODE_LINEAR` 确保 trilinear/anisotropic 正常工作
- 使用 mip bias 或 Clamp LOD 避免过度模糊

#### DCC / Memory Compression

现代 GPU 在写入渲染目标时使用 **无损压缩**：

- **AMD DCC (Delta Color Compression)**：RDNA 系列。将 tile 内颜色值编码为与参考值的 delta，通常 2:1-4:1 压缩率。对 smooth 渐变效果极好，对噪声纹理效果差。
- **NVIDIA Memory Compression**：Maxwell+ 架构。类似原理，无公开细节。典型压缩率 1.5:1-3:1。
- **Intel Arc (Xe-HPG)**：有自己的无损压缩管线，目标 ~2:1。
- **Apple GPU**：Lossless Render Target Compression — Metal 自动启用，透明。

压缩不仅减少 VRAM 占用，更重要的是减少 **带宽**：压缩后的数据从 VRAM 读取/写入时传输量减少，解压/压缩由 GPU 硬件完成，几乎无延迟。

**优化启示**：
- Clear 渲染目标（而非 Load 上一帧内容）可以提高压缩效率——DCC 在 cleared surface 上压缩率最高
- 避免在 RT 之间不必要地拷贝（如 `Resolve`）
- MSAA 的 `Resolve` 操作禁用 DCC，在移动端尤其昂贵

#### Tile-Based Rendering 的带宽优势

回顾 IMR vs TBR 的带宽消耗：

```
IMR (桌面):
  Overdraw = 2.5×, 1920×1080, 32 bpp RT, 3 targets
  每帧写入 = 1920×1080×4×3×2.5 = 62.2 MB
  实际上 GPU 读写都以 cache line 粒度进行 (通常 64B)
  加上 Blend 读+写、Depth 读写、纹理读取...
  真实带宽 ≈ 200-500 MB/frame

TBR (移动):
  - Binning pass: 写 vertex data → VRAM (~5-20 MB)
  - 每个 tile (16×16 或 32×32) 在片上处理
  - Tile 完成后一次写入 VRAM
  - 无 Blend 带宽开销（在片上完成）
  - Depth/Stencil 在片上完成
  带宽 ≈ 50-100 MB/frame (取决于 tile 数和 RT 数)
```

这是 2-5× 的带宽节省。对带宽紧张的移动 GPU 来说是生死攸关的。

**但 TBR 有陷阱**：
- **Load 操作昂贵**：Metal 中 `LoadAction.Load` 会强制从 VRAM 读取前一帧内容到 tile memory。能用 `DontCare`/`Clear` 就用。
- **Store 操作昂贵**：不需要保留的 RT 用 `StoreAction.DontCare`，避免写回 VRAM。
- **MRT 吃 tile memory**：Mali G710 每 core tile memory 约 32KB，Apple GPU 约 128KB。一个 32×32 tile 的 128-bit (4×32) RT = 4KB，3 个 MR target = 12KB + depth/stencil 4KB = 16KB。还在范围内，但更大的 tile 或更多 MRT 会溢出。
- **Tile 间依赖**：在同一 pass 内读 neighbor pixel 可能触发 tile reload。

---

## 2. 代码示例

### 示例 A: 带宽受限操作的模拟与测量 (HLSL Compute)

```hlsl
// bandwidth_bench.hlsl
// 编译: dxc.exe -T cs_6_0 -E main bandwidth_bench.hlsl -Fh bandwidth_bench.h
// 测量读写不同 stride 下的有效带宽

struct Constants {
    uint dataSize;      // 数据大小 (floats)
    uint stride;        // 访问步长
    uint iterations;    // 重复次数
};
ConstantBuffer<Constants> g_Constants : register(b0);
RWStructuredBuffer<float> g_Data : register(u0);
RWStructuredBuffer<uint> g_Result : register(u1);  // [0]=cycles estimate

// 纳秒级 GPU 计时器 (通过 atomic 模拟)
// 实际使用中应搭配 Query Timestamp
groupshared uint g_StartCounter;
groupshared uint g_EndCounter;

// 完全合并的访问 (stride=1)
// 每个线程处理连续元素
[numthreads(256, 1, 1)]
void coalesced_read(uint3 dtid : SV_DispatchThreadID) {
    uint idx = dtid.x;
    if (idx >= g_Constants.dataSize) return;

    float sum = 0.0;
    // 合并读: 线程 i 读 data[i]，连续线程访问连续地址
    for (uint i = 0; i < g_Constants.iterations; i++) {
        uint offset = (idx + i * 256) % g_Constants.dataSize;
        sum += g_Data[offset];
    }
    g_Data[idx] = sum;  // 防止优化掉
}

// 大步长访问 (stride=32)
// 模拟非合并访问
[numthreads(256, 1, 1)]
void strided_read(uint3 dtid : SV_DispatchThreadID) {
    uint idx = dtid.x;
    if (idx >= g_Constants.dataSize) return;

    float sum = 0.0;
    for (uint i = 0; i < g_Constants.iterations; i++) {
        // 步长 32: 一个 warp 的 32 个线程访问跨 cache line 的分散地址
        uint offset = (idx * g_Constants.stride + i) % g_Constants.dataSize;
        sum += g_Data[offset];
    }
    g_Data[idx] = sum;
}

// 随机访问 — 最差情况
[numthreads(256, 1, 1)]
void random_read(uint3 dtid : SV_DispatchThreadID) {
    uint idx = dtid.x;
    if (idx >= g_Constants.dataSize) return;

    // Wang 哈希 — 确定性伪随机
    uint hash = idx;
    float sum = 0.0;
    for (uint i = 0; i < g_Constants.iterations; i++) {
        hash = hash * 1664525u + 1013904223u;
        uint offset = hash % g_Constants.dataSize;
        sum += g_Data[offset];
    }
    g_Data[idx] = sum;
}

// 带宽计算器 (CPU 端)
```

```cpp
// bandwidth_bench.cpp
// 编译: cl /EHsc /O2 bandwidth_bench.cpp /link d3d12.lib dxgi.lib
// 需要 D3D12 环境

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <wrl/client.h>
#include <chrono>
#include <cstdio>
#include <vector>

using Microsoft::WRL::ComPtr;

// 简化版 D3D12 初始化（实际项目使用 D3D12 模板或框架）
// ... (省略冗长的设备创建代码，展示核心测量逻辑)

struct BandwidthResult {
    double gbps;
    double ms;
    size_t bytes_accessed;
};

// 在时间戳之间计算带宽的便捷方法
BandwidthResult calc_bandwidth(
    uint64_t start_tick, uint64_t end_tick,
    uint64_t gpu_freq_hz,      // GPU 时间戳频率 (Hz)
    size_t total_bytes         // 总共读写的字节数
) {
    BandwidthResult r;
    double seconds = double(end_tick - start_tick) / double(gpu_freq_hz);
    r.ms = seconds * 1000.0;
    r.bytes_accessed = total_bytes;
    r.gbps = double(total_bytes) / seconds / 1e9;
    return r;
}

void print_bandwidth_analysis() {
    // 典型场景带宽估算
    struct Scene {
        const char* name;
        int width, height, fps;
        int rt_count;
        int rt_bpp;
        int texture_count;
        int texture_res;
        int texture_bpp;
        float overdraw;
        bool has_shadow_maps;
    };

    Scene scenes[] = {
        {"1080p Medium (PC)", 1920, 1080, 60, 4, 32,
         20, 1024, 8, 2.0f, true},
        {"1440p High (PC)",   2560, 1440, 60, 5, 32,
         25, 2048, 8, 2.5f, true},
        {"4K Ultra (PC)",    3840, 2160, 60, 6, 32,
         30, 2048, 8, 3.0f, true},
        {"720p Mobile (Mali)",1280, 720,  30, 3, 32,
         10, 512,  5, 1.5f, false},  // ASTC 6×6 ≈ 5 bpp
        {"1080p Mobile (Apple)", 1920, 1080, 60, 4, 32,
         15, 1024, 5, 1.8f, false},
    };

    printf("=== 场景带宽估算 ===\n");
    printf("%-25s %8s %8s %8s\n", "场景", "RT", "纹理", "总计");
    printf("%-25s %8s %8s %8s\n", "", "(GB/s)", "(GB/s)", "(GB/s)");

    for (auto& s : scenes) {
        double rt_bytes = (double)s.width * s.height * (s.rt_bpp / 8.0)
                        * s.rt_count * s.overdraw * s.fps;
        // 纹理采样: mipmap 因子 ~1.33
        double tex_bytes = (double)s.texture_res * s.texture_res
                         * (s.texture_bpp / 8.0) * 1.33
                         * s.texture_count * s.fps;
        // Shadow maps
        double shadow_bytes = 0;
        if (s.has_shadow_maps) {
            shadow_bytes = 2048.0 * 2048.0 * 4.0 * 4.0 * s.fps;  // 4 cascades × 32-bit
        }

        double rt_gbps = rt_bytes / 1e9;
        double tex_gbps = tex_bytes / 1e9;
        double shadow_gbps = shadow_bytes / 1e9;
        double total = rt_gbps + tex_gbps + shadow_gbps;

        printf("%-25s %7.1f  %7.1f  %7.1f\n", s.name, rt_gbps, tex_gbps, total);
    }

    printf("\n=== GPU 带宽余量分析 ===\n");
    struct GPU {
        const char* name;
        double bw_gbps;
    };
    GPU gpus[] = {
        {"RTX 4090", 1008},
        {"RTX 3070 Ti", 608},
        {"RTX 4060", 272},
        {"Steam Deck", 88},
        {"Mali G710", 64},
        {"iPhone 15 Pro", 51.2},
    };

    for (auto& s : scenes) {
        double rt_bytes = (double)s.width * s.height * (s.rt_bpp / 8.0)
                        * s.rt_count * s.overdraw * s.fps;
        double tex_bytes = (double)s.texture_res * s.texture_res
                         * (s.texture_bpp / 8.0) * 1.33 * s.texture_count * s.fps;
        double shadow_bytes = s.has_shadow_maps ?
            2048.0 * 2048.0 * 4.0 * 4.0 * s.fps : 0;
        double total = (rt_bytes + tex_bytes + shadow_bytes) / 1e9;

        printf("\n%s (%.0f GB/s):\n", s.name, total);
        for (auto& g : gpus) {
            double pct = total / g.bw_gbps * 100;
            const char* status = pct < 50 ? "OK" :
                                 pct < 75 ? "WARN" : "CRITICAL";
            printf("  %-20s: %5.1f%% %s\n", g.name, pct, status);
        }
    }
}

int main() {
    print_bandwidth_analysis();
    return 0;
}
```

### 示例 B: 纹理压缩选用决策工具 (Python)

```python
#!/usr/bin/env python3
"""
texture_budget_calc.py — 纹理预算与带宽估算

估算给定纹理预算和压缩格式下的 VRAM 占用和带宽消耗。
用于在项目早期做出纹理压缩格式的决策。
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class CompressionFormat:
    name: str
    bpp: float          # bits per pixel
    supports_alpha: bool
    supports_hdr: bool
    quality_rank: int   # 1=best, subjective
    platform: str       # "desktop", "mobile", "universal"


FORMATS = [
    # Desktop BCn
    CompressionFormat("BC1 (DXT1)", 4.0, False, False, 4, "desktop"),
    CompressionFormat("BC3 (DXT5)", 8.0, True,  False, 3, "desktop"),
    CompressionFormat("BC4",        4.0, False, False, 3, "desktop"),  # single channel
    CompressionFormat("BC5",        8.0, False, False, 2, "desktop"),  # 2 channels
    CompressionFormat("BC6H",       8.0, False, True,  2, "desktop"),
    CompressionFormat("BC7",        8.0, True,  False, 1, "desktop"),
    # Mobile ASTC
    CompressionFormat("ASTC 4×4",   8.00, True, True, 1, "mobile"),
    CompressionFormat("ASTC 5×5",   5.12, True, True, 2, "mobile"),
    CompressionFormat("ASTC 6×6",   3.56, True, True, 3, "mobile"),
    CompressionFormat("ASTC 8×8",   2.00, True, True, 4, "mobile"),
    CompressionFormat("ASTC 5×4",   6.40, True, True, 2, "mobile"),  # 法线
    # Universal (uncompressed)
    CompressionFormat("R8G8B8A8",  32.0, True,  False, 0, "universal"),
    CompressionFormat("R16G16B16A16_FLOAT", 64.0, True, True, 0, "universal"),
]


@dataclass
class TextureCategory:
    name: str
    count: int
    resolution: int       # 正方形，边长
    format_name: str
    mipmapped: bool = True
    is_cubemap: bool = False
    is_array: bool = False
    array_size: int = 1


def texture_size_mb(cat: TextureCategory, fmt: CompressionFormat) -> float:
    """计算单张纹理（含 mip chain）的 VRAM 占用 (MB)"""
    pixels = cat.resolution * cat.resolution
    if cat.is_cubemap:
        pixels *= 6
    if cat.is_array:
        pixels *= cat.array_size

    if cat.mipmapped:
        pixels = int(pixels * 1.333)  # mip chain 约 +33%

    bytes_total = (pixels * fmt.bpp) / 8.0
    return bytes_total / (1024 * 1024)


def bandwidth_estimate(
    categories: List[TextureCategory],
    format_map: dict,
    fps: int = 60,
    avg_samples_per_pixel: int = 1
) -> dict:
    """估算每帧的纹理带宽消耗"""
    total_bytes = 0.0
    breakdown = []

    for cat in categories:
        fmt = format_map.get(cat.format_name, FORMATS[-2])  # default RGBA8
        size_per_texture = texture_size_mb(cat, fmt) * 1024 * 1024
        # 假设每帧全部采样一次（粗糙估计）
        bytes_per_frame = size_per_texture * cat.count * avg_samples_per_pixel
        total_bytes += bytes_per_frame
        breakdown.append((cat.name, cat.count, cat.resolution,
                         fmt.name, fmt.bpp, bytes_per_frame / 1e6))

    gbps = total_bytes * fps / 1e9

    return {
        "total_per_frame_mb": total_bytes / 1e6,
        "total_bandwidth_gbps": gbps,
        "breakdown": breakdown,
    }


def print_report(title: str, cats: List[TextureCategory],
                 format_map: dict, fps: int = 60):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(f"{'Category':<20} {'Cnt':>4} {'Res':>6} {'Format':<20} "
          f"{'bpp':>5} {'MB/frame':>10}")
    print("-" * 60)

    result = bandwidth_estimate(cats, format_map, fps)
    for name, cnt, res, fmt_name, bpp, mb in result["breakdown"]:
        print(f"{name:<20} {cnt:>4} {res:>6} {fmt_name:<20} "
              f"{bpp:>4.1f} {mb:>9.2f}")

    print("-" * 60)
    print(f"  每帧纹理带宽: {result['total_per_frame_mb']:.1f} MB")
    print(f"  @{fps}fps 总带宽: {result['total_bandwidth_gbps']:.1f} GB/s")
    print()


if __name__ == "__main__":
    # 场景: PC 3A 游戏 (2K 分辨率)
    pc_format_map = {
        "base_color": FORMATS[5],    # BC7
        "normal":     FORMATS[3],    # BC5
        "orm":        FORMATS[0],    # BC1 (打包 roughness+metallic+AO)
        "emissive":   FORMATS[0],    # BC1
        "skybox":     FORMATS[4],    # BC6H (HDR)
    }

    pc_categories = [
        TextureCategory("Base Color",  300, 2048, "base_color"),
        TextureCategory("Normal",      300, 2048, "normal"),
        TextureCategory("ORM",         300, 2048, "orm"),
        TextureCategory("Emissive",     50, 1024, "emissive"),
        TextureCategory("Skybox",       10, 2048, "skybox", is_cubemap=True),
        TextureCategory("UI",           20, 1024, "base_color", mipmapped=False),
    ]

    print_report("PC 3A 游戏 (BCn 压缩)", pc_categories, pc_format_map)

    # 场景: 移动游戏 (1080p)
    mobile_format_map = {
        "diffuse_astc":  FORMATS[8],   # ASTC 6×6
        "normal_astc":   FORMATS[10],  # ASTC 5×4
        "ao_astc":       FORMATS[9],   # ASTC 8×8
        "ui_astc":       FORMATS[7],   # ASTC 4×4
    }

    mobile_categories = [
        TextureCategory("Diffuse",  100, 1024, "diffuse_astc"),
        TextureCategory("Normal",   100, 1024, "normal_astc"),
        TextureCategory("AO",        50, 512,  "ao_astc"),
        TextureCategory("UI",        15, 512,  "ui_astc", mipmapped=False),
    ]

    print_report("移动游戏 (ASTC 压缩, 30fps)", mobile_categories,
                 mobile_format_map, fps=30)

    # 对比：如果不压缩
    uncompressed_map = {
        "base_color": FORMATS[-2],  # RGBA8
        "normal":     FORMATS[-2],
        "orm":        FORMATS[-2],
        "emissive":   FORMATS[-2],
        "skybox":     FORMATS[-2],
        "diffuse_astc": FORMATS[-2],
        "normal_astc":  FORMATS[-2],
        "ao_astc":      FORMATS[-2],
        "ui_astc":      FORMATS[-2],
    }

    print_report("PC 场景 — 未压缩 (RGBA8, 用于对比)", pc_categories,
                 uncompressed_map)
    print_report("移动场景 — 未压缩 (RGBA8, 用于对比)", mobile_categories,
                 uncompressed_map, fps=30)

    # 关键发现
    bc_pc = bandwidth_estimate(pc_categories, pc_format_map)
    raw_pc = bandwidth_estimate(pc_categories, uncompressed_map)

    print(f"\n=== 关键对比 ===")
    print(f"PC: BCn压缩 vs 未压缩 = {bc_pc['total_bandwidth_gbps']:.1f} "
          f"vs {raw_pc['total_bandwidth_gbps']:.1f} GB/s "
          f"(节省 {100*(1-bc_pc['total_bandwidth_gbps']/raw_pc['total_bandwidth_gbps']):.0f}%)")

    bc_mob = bandwidth_estimate(mobile_categories, mobile_format_map, fps=30)
    raw_mob = bandwidth_estimate(mobile_categories, uncompressed_map, fps=30)
    print(f"移动: ASTC vs 未压缩 = {bc_mob['total_bandwidth_gbps']:.1f} "
          f"vs {raw_mob['total_bandwidth_gbps']:.1f} GB/s "
          f"(节省 {100*(1-bc_mob['total_bandwidth_gbps']/raw_mob['total_bandwidth_gbps']):.0f}%)")
```

---

## 3. 练习

### 练习 1: 纹理预算审计 [基础]

选一个你正在开发或有源码的游戏项目（或公开的 Demo），做一次纹理预算审计：

1. 列出所有纹理，记录：名称、分辨率、格式（压缩/未压缩）、mipmap（有/无）
2. 用 `texture_budget_calc.py` 估算当前 VRAM 占用和带宽消耗
3. 找出前 5 个带宽消耗最大的纹理
4. 对每个大纹理提出降带宽方案（换压缩格式、降分辨率、拆分通道等）
5. 估算方案实施后的带宽节省量

### 练习 2: 移动端 Tiling 决策树 [进阶]

你要在 Mali G710 和 Apple A17 上实现一个 deferred renderer：
- G-Buffer: 3 targets (Albedo RGBA8, Normal RG8, PBR RGBA8) + Depth32
- 后处理: Bloom (2 pass), ToneMapping, TAA
- 屏幕分辨率: 1080p

分析以下问题：
1. G-Buffer 总共占用多少 tile memory per core？每个 tile 假设 32×32。是否在 tile memory 限制内？
2. 从 G-Buffer 到 Lighting pass 的 Load 操作如何避免？（提示：subpass / `VK_ATTACHMENT_LOAD_OP_DONT_CARE`）
3. Bloom 的多次全屏 pass 在 TBR 上有什么特殊代价？如何优化？
4. TAA 需要前一帧的 color buffer——在 TBR 上这个 Load 是否昂贵？能优化吗？

### 练习 3: 带宽剖面实测 [挑战]（可选）

如果你有 RenderDoc 或 NSight Graphics 可用：

1. 捕获一个场景帧
2. 导出所有 draw call 的带宽统计（NSight: "GPU Trace" → "Memory" 视图；RenderDoc: "Statistics" 窗口）
3. 找出带宽消耗最大的 3 个 event
4. 对每个 event：
   - 是什么操作（Draw、Copy、Clear 等）
   - 读写了哪些 resource
   - 总带宽是多少
5. 提出具体的优化方案并估算收益
6. 如果可能，实施一个优化并重新测量

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **纹理预算审计实操框架：**
>
> 使用 `texture_budget_calc.py`（教程中的工具）生成报告。典型发现示例：
>
> ```
> === Texture Budget Audit ===
> Total VRAM (estimated): 5120 MB (5 GB)
>
> Texture                     Resolution   Format     MiP?   VRAM      Bandwidth/frame
> ─────────────────────────────────────────────────────────────────────────────────
> character_diffuse_01        2048×2048    RGBA8      Yes    21.3 MB   42.6 MB  ← #1
> terrain_splatmap            4096×4096    RGBA8      Yes    85.3 MB   170.7 MB  ← #2 BIGGEST
> skybox_hdr                  2048×2048    BC6H       Yes    10.7 MB   21.3 MB
> particle_atlas              1024×1024    RGBA8      No      5.3 MB    10.7 MB  ← #3 (no mip!)
> ui_main_atlas               2048×2048    RGBA8      No     21.3 MB   21.3 MB
> normal_detail_01            1024×1024    BC5        Yes     5.3 MB    10.7 MB
> roughness_metal_01          512×512      BC4        Yes     1.3 MB    2.7 MB   ← optimal
> ─────────────────────────────────────────────────────────────────────────────────
> ```
>
> **Top 5 大纹理的降带宽方案：**
>
> | 纹理 | 当前 | 方案 | 节省 | 理由 |
> |------|------|------|------|------|
> | `terrain_splatmap` (4096² RGBA8) | 85 MB | → 2048² BC7 | **节省 ~74 MB** | Splatmap 不需要 4K 精度；BC7 4:1 压缩率 |
> | `character_diffuse_01` (2048² RGBA8) | 21 MB | → BC7 | **节省 ~16 MB** | 角色纹理最受益于 BC7 高质量压缩 |
> | `particle_atlas` (1024² RGBA8, no mip) | 5.3 MB | → BC3 + mip | **节省 ~3 MB + 降低采样带宽 50%** | mip 解决远处粒子采样时的带宽浪费 |
> | `ui_main_atlas` (2048² RGBA8) | 21 MB | → BC7 或保持 RGBA8 | **0-16 MB** | UI 纹理需要像素级精度——评估 BC7 的视觉差异 |
> | `skybox_hdr` (2048² BC6H) | 11 MB | 已最优 | — | BC6H 是 HDR 纹理的最佳选择 |
>
> **估算总带宽节省**：从 ~277 MB/frame → ~180 MB/frame（**节省 35%**）

> [!tip]- 练习 2 参考答案
> **移动端 TBR Deferred Renderer 分析：**
>
> **1. G-Buffer tile memory 占用：**
> ```
> Mali G710 tile memory per core: 典型 ~32KB (Valhall 架构)
> Apple A17 tile memory per core: ~128KB (Apple GPU)
>
> G-Buffer layout (per pixel, 32-bit = 4 bytes per channel):
>   - Albedo:   RGBA8  = 4 bytes
>   - Normal:    RG8    = 2 bytes
>   - PBR:       RGBA8  = 4 bytes
>   - Depth:     32-bit  = 4 bytes
>   Total per pixel: 14 bytes
>
> 32×32 tile = 1024 pixels × 14 bytes = 14.3 KB per tile
> ```
>
> - **Mali G710**: 14.3 KB < 32KB ✓ 在 tile memory 限制内，但接近（~45% 占用）。额外 bandwidth compression 可降低到 8-10KB。
> - **Apple A17**: 14.3 KB << 128KB ✓ 非常充裕。
> - **如果增加到 4 个 RT**（如添加 Velocity buffer RG16F = 4 bytes），则 ~18.3 KB/tile → Mali 上仍可接受，但已无多余空间做 blend 操作。
>
> **2. G-Buffer → Lighting pass 的 Load 优化：**
> ```cpp
> // Vulkan: 使用 subpass 避免 VRAM round-trip
> // Subpass 0: G-Buffer fill (3 color attachments + depth)
> // Subpass 1: Lighting (read G-Buffer as input attachments, write to final color)
>
> VkAttachmentDescription colorAttachments[4] = {
>     { /* Albedo  */ .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
>                     .storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE },
>     { /* Normal  */ .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
>                     .storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE },
>     { /* PBR     */ .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
>                     .storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE },
>     { /* Final   */ .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
>                     .storeOp = VK_ATTACHMENT_STORE_OP_STORE },
> };
> // G-Buffer attachments 在 subpass 之间保留在 tile memory 中
> // Lighting subpass 通过 input attachment 读取 → tile memory 内传输，零 VRAM 带宽！
> ```
> - **Metal**: 使用 `StoreAction.dontCare` 让 G-Buffer 不写回 VRAM。Lighting pass 用 `[[color(0)]]` 在 tile memory 中消费 G-Buffer。
> - **关键优化**：G-Buffer 只在 tile memory 中生存，永不 touch VRAM。只有 final color buffer 最终 Store。
>
> **3. Bloom 在 TBR 上的代价和优化：**
> - **代价**：每个 fullscreen pass 都是 tile write-back to VRAM + next pass tile load from VRAM。两次 Bloom pass = 2× write + 2× read = ~66 MB 带宽（1080p × 4 bytes × 2 × 2）。
> - **优化 1**：降采样到 540p 做 Bloom → 带宽降为 1/4。
> - **优化 2**：合并 Bloom + ToneMapping + TAA 到一个 pass（tile 内计算 → 一次 write-back）。
> - **Metal 最优解**：使用 Tile Shaders — Bloom blur 在 tile memory 中完成，不写回 VRAM。
>
> **4. TAA 对前一帧 Color Buffer 的 Load：**
> - TAA 需要 `historyColor = Load(frame_N_minus_1)`。
> - 在 TBR 上，上一个 frame 的 color buffer 在 VRAM 中 → Load 必须从 VRAM 读取。这在 TBR 上是昂贵的。
> - **优化**：如果 TAA + ToneMap 在同一 pass 合并，history 读取是一次性的，后续计算在 tile memory 中完成。
> - **进一步优化**：使用 `VK_ATTACHMENT_LOAD_OP_LOAD` 或 Metal 的 `LoadAction.load` 仅在必要时。如果可以用上一帧的 depth 做 reprojection 来减少 sample 点，可降低带宽。

> [!tip]- 练习 3 参考答案（可选）
> **带宽剖面实测步骤（NVIDIA NSight Graphics）：**
>
> 1. **捕获帧**：`Quick Launch` → 运行游戏 → `F11` 捕获帧
> 2. **GPU Trace 视图**：展开帧 → 找到 `Memory` 标签页
> 3. **识别 Top-3 带宽消耗者**：
>
> 典型结果示例（虚构但 realistic）：
>
> | Event | Operation | Resources | Read BW | Write BW | Total |
> |-------|-----------|-----------|---------|----------|-------|
> | #145 Shadows | Draw (1024×4 cascade) | Depth RT (R32) | 12 MB | 48 MB | **60 MB** |
> | #278 Opaque | Draw (Forward pass) | 8× texture samples | 85 MB | 32 MB | **117 MB** ← #1 |
> | #389 Bloom V | Compute (540p blur) | 540p RT R11G11B10 | 48 MB | 24 MB | **72 MB** |
>
> **优化方案：**
> - **Event #278 (Opaque)** — 最大带宽消耗：
>   - 8 个纹理中 3 个是 RGBA8 → 换 BC7/BC5（节省 ~60 MB 读带宽）。
>   - BaseColor + Normal + PBR → 已在 BC7/BC5 阶段后，预估节省 40%。
> - **Event #145 (Shadows)**：
>   - 4× cascade shadow maps → 考虑用 PSSM 优化，减少到 2 cascade + 更紧缩的 frustum fit，带宽减半。
>   - 使用 D32_SFLOAT 替代 R32_UINT（硬件 depth compression 友好）。
> - **Event #389 (Bloom)**：
>   - 降采样到 1/4 分辨率（270p）→ 带宽降为 1/4。
>   - 合并 Bloom + ToneMap 到一个 pass → 减少一次 full-screen write。
>
> **总估算节省**：~140 MB/frame → ~80 MB/frame（**节省 43%**）

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- [GPUOpen: Texture Compression](https://gpuopen.com/learn/using-modern-texture-compression/) — BCn/ASTC 最佳实践
- [ARM: ASTC Texture Compression Guide](https://developer.arm.com/documentation/102162/latest/) — ASTC 权威文档
- [NVIDIA: Texture Tools Exporter](https://developer.nvidia.com/texture-tools-exporter) — BC7 高质量压缩工具
- [Intel: ISPC Texture Compressor](https://www.intel.com/content/www/us/en/developer/articles/technical/ispc-texture-compressor.html) — BCn 快速压缩
- [Radeon GPU Profiler — Bandwidth Analysis](https://gpuopen.com/rgp/) — AMD 带宽实测
- [NVIDIA NSight Graphics — Memory Statistics](https://developer.nvidia.com/nsight-graphics) — NVIDIA 带宽实测
- [Metal Best Practices — Texture Loading](https://developer.apple.com/documentation/metal/texture_loading) — Apple GPU 纹理优化
- [Rich Geldreich: "Crunch" Texture Compression Library](https://github.com/BinomialLLC/crunch) — 高级纹理压缩（支持 BC1-7 和 ETC）
- [Real-Time Rendering 4th — Chapter 6: Texturing](https://www.realtimerendering.com/)
- GDC 2018: "Optimizing for Tile-Based Rendering" (ARM) — TBR 深入分析

---

## 常见陷阱

1. **纹理格式"能用就行"**：很多团队在项目初期用 RGBA8 或 PNG 导入，到后期才考虑压缩。此时所有美术资产已经定稿，换格式可能引入 visual regression。从 Day 1 就用正确的压缩格式。

2. **移动端用 BC 格式**：BC1-7 是桌面 GPU 格式。Mali/Adreno 不支持硬件 BC 解压（除非驱动软件模拟，极慢）。移动端必须用 ASTC 或 ETC2。检查你的引擎 Texture Importer 设置。

3. **不启用 mipmapping**：很多 UI 纹理和 2D sprite 默认不生成 mipmap——但如果这些纹理被缩小渲染（如远距离的 UI 元素），会产生严重带宽浪费和锯齿。除非确定纹理只在 1:1 尺寸下使用，否则始终启用 mipmap。

4. **法线贴图用 BC3/DXT5**：BC3 对法线的质量远不如 BC5。BC5 用 2 个通道（RG）存 XY，比 BC3 的压缩 artifact 少得多。且 BC5 和 BC3 都是 8 bpp，VRAM 开销一样。

5. **DCC/压缩对 Clear 的依赖**：如果你 Load 渲染目标而不是 Clear，DCC metadata 需要处理 delta 编码的重置，压缩效率可能大幅下降。对全屏 pass（如天空盒），Clear 比 Load 快很多。

6. **在 TBR GPU 上叠加多个全屏后处理 pass**：每个 pass 都意味着 tile 写回 VRAM。与其 5 个独立的 pass，不如尽量合并到一个 pass 中（如 Bloom + ToneMap + ColorGrade 在一个 pixel shader 中完成）。Metal 的 Tile Shaders 和 Vulkan 的 subpass 是这里的最优解。
