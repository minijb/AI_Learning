---
title: "纹理优化 — 压缩、图集、流式加载"
updated: 2026-06-05
---

# 纹理优化 — 压缩、图集、流式加载
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: 07-LOD 系统 (了解 Mipmap 概念和纹理在渲染管线中的角色)

---

## 1. 概念讲解

### 为什么需要这个？

纹理占游戏显存的 60%–80%。一个 4K PBR 材质包含 BaseColor、Normal、Roughness、Metallic、AO 五张贴图，以 RGBA8 未压缩格式存储：

```
4K 纹理 = 4096 × 4096 × 4 bytes = 67,108,864 bytes = 64 MB（单张）
一个材质 5 张 = 320 MB
```

8GB 显存的显卡，只够放 25 个这样的材质——实际游戏可能有数千个。这就是纹理优化存在的根本原因。

更重要的是，纹理带宽是 GPU 的主要功耗来源。一个 1080p 帧从显存读取的纹理数据可以达到 200–500MB。降低纹理带宽 = 更低的功耗 + 更高的帧率 + 更少发热。

### 核心思想

#### 1. 纹理内存计算

**基本公式**：
```
纹理大小(字节) = 宽度 × 高度 × 每像素字节数 × (1 + 1/4 + 1/16 + ...)
               ≈ 宽度 × 高度 × 每像素字节数 × 1.33  （含 Mipmap）
```

在 GPU 硬件中，纹理还存在对齐开销（tiling/linear layout），实际占用可能略高于理论值。

**常见格式与单像素字节数**：

| 格式 | bpp | 4K 单张(含Mip) | 压缩比 | 质量 | 用途 |
|------|-----|---------------|--------|------|------|
| RGBA8 (未压缩) | 32 | 85.3 MB | 1:1 | 无损 | 编辑器/原型 |
| BC1 (DXT1) | 4 | 10.7 MB | 8:1 | RGB，1-bit Alpha | 漫反射贴图 |
| BC3 (DXT5) | 8 | 21.3 MB | 4:1 | RGBA，平滑 Alpha | 法线+粗糙度打包/贴花 |
| BC5 (3Dc) | 8 | 21.3 MB | 4:1 | 双通道高质量 | 法线贴图（RG 通道） |
| BC6H | 8 | 21.3 MB | 4:1 | HDR | 天空球/HDR 环境贴图 |
| BC7 | 8 | 21.3 MB | 4:1 | RGBA 高质量 | 通用高质量 |
| ASTC 4×4 | 8 | 21.3 MB | 4:1 | RGBA 通用 | 移动端 |
| ASTC 6×6 | 3.56 | 9.5 MB | ~9:1 | 适中 | 移动端 diffuse |
| ASTC 8×8 | 2 | 5.3 MB | 16:1 | 有损 | 移动端远处物体 |
| ETC2 RGB | 4 | 10.7 MB | 8:1 | RGB | GLES 移动端 fallback |

**PC 端黄金组合**：BC7（高质量 RGBA）+ BC5（法线贴图）+ BC6H（HDR）
**移动端黄金组合**：ASTC 4×4（重要贴图）+ ASTC 6×6（一般贴图）+ ASTC 8×8（UI 背景）

#### 2. 压缩格式深度解析

**BC1（DXT1）**：4×4 块，每块 64 位 = 4bpp。
- 存两个 16 位 RGB 565 端点色 + 2 位/像素插值索引
- 适合：没有 Alpha 或只需要 1-bit Alpha 的漫反射贴图
- 不适合：法线贴图（会产生明显色带）

**BC3（DXT5）**：4×4 块，每块 128 位 = 8bpp。
- RGB 部分 = BC1，Alpha 部分 = 独立的 8 位端点 + 3 位/像素索引
- 适合：有渐变 Alpha 的贴图、贴花、粒子

**BC5（ATI2/3Dc）**：4×4 块，每块 128 位 = 8bpp。
- 两个独立通道（R 和 G），每个 = DXT5 的 Alpha 部分
- 完美适合法线贴图（法线的 X 和 Y 分量）
- Z 分量在 Shader 中重建：`z = sqrt(1 - x² - y²)`

**BC7**：4×4 块，每块 128 位 = 8bpp。
- 比 BC3 好得多的 RGB 质量，支持 8 种编码模式
- 适合：高质量漫反射/高光贴图，PC 和主机

**ASTC**：可变块大小（4×4 到 12×12），每块 128 位。
- bpp = 128 / (blockWidth × blockHeight)
- 支持 1-4 通道、LDR/HDR、sRGB
- 几乎所有现代移动 GPU 都支持

**Crunch 压缩**：对 DXT 做进一步的 LZMA 类压缩，用于减少**安装包**大小（不影响显存）。Unity 中使用，典型压缩率 2.5:1。

#### 3. 纹理图集（Texture Atlas）

将多张小纹理合并到一张大纹理中。

**收益**：
- 减少纹理切换（Bind Texture 是相对昂贵的操作）
- 减少 Draw Call（同一图集的物体可以合批）
- 更好的纹理缓存局部性

**代价**：
- 可能浪费空间（各子纹理之间的间距、形状不匹配）
- Over-fetching：当采样到子纹理边缘时，GPU 会读取相邻像素（在 Mipmap 低层尤其严重）
- 更新单个纹理时需要重建整个图集

**常见图集方案**：
- UI Sprite Atlas（Unity Sprite Atlas, UE Paper2D Sprite Sheet）
- 粒子纹理 Flipbook（多帧动画合并）
- Megascans 的 UDIM 工作流

**UV Padding（UV 扩展）**：在图集中，每个子纹理周围留 2-4 像素的边距，填充边缘色，防止 Mipmap 低层出现颜色渗漏。

#### 4. Mipmap 生成与 Streaming

**Mipmap 内存**：Mipmap 链是原始纹理的 1/3 额外内存。公式：
```
Mip 总大小 = 原始大小 × (1 + 1/4 + 1/16 + 1/64 + ...) = 原始大小 × 4/3
```

**Mipmap 裁剪**：远处的物体不需要最高精度 Mip Level。设置 `MaxMipLevel` 或 `MipBias` 可以减少已加载到显存的 Mip 层数：
```
// Unity
texture.mipMapBias = 2.0f;  // 跳过前 2 级，从 Level 2 开始
texture.maxMipLevel = 5;    // 最多加载到 Level 5

// UE — 在 Texture 属性中设置 LOD Bias 和 Num Cinematic Mip Levels
```

**虚拟纹理（Virtual Texturing）**：
- 核心思想：像虚拟内存一样，只加载当前需要的纹理 Tile
- GPU 上有一张低分辨率的"页表"（Page Table），指示每个 Tile 的物理位置
- UE5 的 Virtual Texture 系统和 id Software 的 MegaTexture 都是这种方案
- 优势：场景可以用极高的纹理分辨率（16K+），只占少量物理显存

**Partial Residency Textures**（部分驻留纹理）：
- DX12/Vulkan 特性：纹理可以只有部分 Mip Level 加载到显存
- GPU 访问未加载的 Mip Level 时返回零或触发回调

**UE Texture Streaming Pool**：UE 维护一个纹理流式加载池（默认 1000MB），根据物体距离动态调整加载到显存的 Mip Level。`r.Streaming.PoolSize` 控制池大小。

**Unity Mipmap Streaming**：Unity 2018.3+ 支持自动 Mipmap Streaming，在 Quality Settings 中启用。

#### 5. 分辨率管理

**最佳实践**：
| 纹理用途 | 建议最大分辨率 | 格式 | 说明 |
|----------|---------------|------|------|
| 角色主角贴图 | 2048×2048 | BC7/BC5 | 近距离观察 |
| 配角/NPC | 1024×1024 | BC7/BC5 | 平时距离远 |
| 场景道具 | 512-1024 | BC7 | 根据大小分级 |
| 远景建筑 | 256-512 | BC1 | 永远不会靠近 |
| UI 图标 | 按需 | ASTC/BC7 | 需要清晰时不过度压缩 |
| 天空球 | 2048×1024 | BC6H | HDR 格式 |

**平台覆盖**：Unity 中可为不同平台设置不同最大分辨率（Android 512，PC 2048），UE 中使用 LOD Bias 按平台调整。

---

## 2. 代码示例

### 示例 1：纹理内存计算器（Python）

```python
# texture_memory_calc.py — 精确计算纹理显存占用
# 运行: python texture_memory_calc.py

import math

# ===== 纹理格式定义 =====
# (名称, 每像素位数(bpp), 块宽度, 块高度, 每块字节数)
TEXTURE_FORMATS = {
    # PC 桌面格式
    "RGBA8":       ("RGBA8 Uncompressed",  32, 1, 1, 4),
    "RGBA16F":     ("RGBA16F (HDR)",       64, 1, 1, 8),
    "BC1":         ("BC1 / DXT1",           4, 4, 4, 8),
    "BC3":         ("BC3 / DXT5",           8, 4, 4, 16),
    "BC4":         ("BC4 (Single Channel)", 4, 4, 4, 8),
    "BC5":         ("BC5 / 3Dc (Normal)",   8, 4, 4, 16),
    "BC6H":        ("BC6H (HDR)",           8, 4, 4, 16),
    "BC7":         ("BC7 (High Quality)",   8, 4, 4, 16),
    # 移动端格式
    "ASTC_4x4":    ("ASTC 4×4",             8, 4, 4, 16),
    "ASTC_6x6":    ("ASTC 6×6",            3.56, 6, 6, 16),
    "ASTC_8x8":    ("ASTC 8×8",             2, 8, 8, 16),
    "ASTC_10x10":  ("ASTC 10×10",           1.28, 10, 10, 16),
    "ETC2_RGB":    ("ETC2 RGB",             4, 4, 4, 8),
}


def calc_texture_size(width, height, fmt_key, mip_levels=None):
    """计算纹理显存占用"""
    fmt_name, bpp, bw, bh, block_bytes = TEXTURE_FORMATS[fmt_key]

    # 对齐到块边界
    blocks_x = math.ceil(width / bw)
    blocks_y = math.ceil(height / bh)
    aligned_w = blocks_x * bw
    aligned_h = blocks_y * bh

    if mip_levels is None:
        # 默认：完整的 Mip 链
        mip_levels = math.floor(math.log2(max(width, height))) + 1

    total_bytes = 0
    current_w, current_h = width, height

    for level in range(mip_levels):
        bx = math.ceil(current_w / bw)
        by = math.ceil(current_h / bh)
        level_bytes = bx * by * block_bytes
        total_bytes += level_bytes

        # 下一级 Mip 尺寸减半
        current_w = max(1, current_w // 2)
        current_h = max(1, current_h // 2)

    # 精确 bpp（含对齐）
    base_bytes = math.ceil(width / bw) * math.ceil(height / bh) * block_bytes
    effective_bpp = base_bytes * 8 / (width * height)

    return total_bytes, base_bytes, effective_bpp


def format_size(bytes_val):
    """格式化字节为可读字符串"""
    if bytes_val >= 1024 * 1024 * 1024:
        return f"{bytes_val / (1024**3):.2f} GB"
    elif bytes_val >= 1024 * 1024:
        return f"{bytes_val / (1024**2):.2f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.2f} KB"
    else:
        return f"{bytes_val} B"


def main():
    print("=" * 72)
    print("纹理显存占用量计算器")
    print("=" * 72)

    # 测试各种分辨率
    test_resolutions = [
        (256,  256,  "UI 小图标"),
        (512,  512,  "小道具/UI 面板"),
        (1024, 1024, "标准贴图/角色"),
        (2048, 2048, "主角/高精度"),
        (4096, 4096, "4K 高精度/地形"),
    ]

    test_formats = ["RGBA8", "BC1", "BC3", "BC7", "ASTC_6x6"]

    print(f"\n{'分辨率':<20}", end="")
    for fmt in test_formats:
        print(f"{TEXTURE_FORMATS[fmt][0]:<20}", end="")
    print()

    print("-" * 72)

    for w, h, desc in test_resolutions:
        print(f"{w}×{h} ({desc}):", end="")
        # 实际列宽计算
        col = 0
        for fmt in test_formats:
            total, _, _ = calc_texture_size(w, h, fmt)
            print(f"  {format_size(total):>15}", end="")
        print()

    print("\n" + "=" * 72)
    print("PBR 材质集显存估算")
    print("=" * 72)

    # 一个典型的 PBR 材质：
    # BaseColor(BC7) + Normal(BC5) + ORM(BC7) + Emissive(BC7)
    pbr_maps = [
        ("BaseColor",   2048, 2048, "BC7"),
        ("Normal",      2048, 2048, "BC5"),
        ("ORM (Occlusion+Roughness+Metallic)", 2048, 2048, "BC7"),
        ("Emissive",    1024, 1024, "BC7"),  # 发光贴图通常可以小一些
    ]

    total_pbr = 0
    print(f"\n{'贴图':<35} {'分辨率':>12} {'格式':>22} {'大小':>12}")
    print("-" * 85)

    for name, w, h, fmt in pbr_maps:
        total, base, _ = calc_texture_size(w, h, fmt)
        total_pbr += total
        print(f"{name:<35} {w}×{h:>4}     {TEXTURE_FORMATS[fmt][0]:>22} {format_size(total):>12}")

    print("-" * 85)
    print(f"{'单个材质合计':<35} {'':>12} {'':>22} {format_size(total_pbr):>12}")

    # 场景中有 200 个这样的材质
    print(f"\n场景中 200 个材质: {format_size(total_pbr * 200)} 显存")
    print("使用 ASTC 6×6 替代: ", end="")
    astc_total = 0
    for name, w, h, _ in pbr_maps:
        t, _, _ = calc_texture_size(w, h, "ASTC_6x6")
        astc_total += t
    print(f"{format_size(astc_total * 200)}")

    print("\n" + "=" * 72)
    print("优化建议")
    print("=" * 72)
    print("1. 从不使用 RGBA8 用于最终发布 — 总是选择压缩格式")
    print("2. 法线贴图用 BC5（PC）或 ASTC（移动），不是 BC3")
    print("3. 粗糙度+金属度+AO 打包到单张 BC7 的 RGB 通道")
    print("4. 不需要 Alpha 的贴图用 BC1（8:1 压缩比）而不是 BC3")
    print("5. 大场景用 Texture Streaming 只加载需要的 Mip Level")
    print("6. 定期审核纹理分辨率 — 很多 4K 贴图实际不需要 4K")


if __name__ == "__main__":
    main()
```

### 示例 2：虚拟纹理页表查找（C++ 概念）

```cpp
// virtual_texture_page_table.cpp — 虚拟纹理页表查找的概念实现
// 编译: g++ -std=c++17 virtual_texture_page_table.cpp -o vt_demo && ./vt_demo

#include <iostream>
#include <vector>
#include <cstdint>
#include <cmath>
#include <iomanip>

// ====== 虚拟纹理页表 ======
// 概念：将巨大的虚拟纹理空间（如 65536×65536）映射到有限的物理页（如 4096×4096）
// GPU 访问纹理时先查页表 → 找到物理页 → 采样物理纹理

constexpr int PAGE_SIZE    = 128;   // 每页 128×128 纹素
constexpr int VIRTUAL_DIM  = 65536; // 虚拟纹理 64K×64K
constexpr int PAGES_X      = VIRTUAL_DIM / PAGE_SIZE; // 512 页/维
constexpr int PAGES_Y      = VIRTUAL_DIM / PAGE_SIZE;
constexpr int PHYSICAL_DIM = 4096;  // 物理纹理池 4K×4K
constexpr int PHYS_PAGES_X = PHYSICAL_DIM / PAGE_SIZE; // 32 页/维
constexpr int PHYS_PAGES_Y = PHYSICAL_DIM / PAGE_SIZE;
constexpr int MAX_PHYS_PAGES = PHYS_PAGES_X * PHYS_PAGES_Y; // 总物理页数: 1024

// 页表条目
struct PageTableEntry {
    bool    resident;       // 该页是否已加载到物理纹理
    int16_t physPageX;      // 物理页 X 索引
    int16_t physPageY;      // 物理页 Y 索引
    int16_t mipLevel;       // 正在使用的 Mip Level
};

// 物理页状态
struct PhysicalPage {
    bool    allocated;
    int     virtualPageX;   // 对应的虚拟页 X
    int     virtualPageY;   // 对应的虚拟页 Y
    int     mipLevel;
    int64_t lastAccessFrame;
};

class VirtualTextureSystem {
private:
    // 页表：每个 Mip Level 一张
    std::vector<std::vector<PageTableEntry>> pageTable;

    // 物理页池
    std::vector<PhysicalPage> physPages;

    // 统计
    int64_t currentFrame = 0;
    int64_t pageHits = 0;
    int64_t pageMisses = 0;
    int     numMipLevels;

public:
    VirtualTextureSystem() {
        // 计算 Mip 级别数
        numMipLevels = (int)std::log2(VIRTUAL_DIM) + 1;

        // 初始化页表
        pageTable.resize(numMipLevels);
        for (int mip = 0; mip < numMipLevels; ++mip) {
            int dim = VIRTUAL_DIM >> mip;
            if (dim < PAGE_SIZE) break;
            int pagesX = dim / PAGE_SIZE;
            int pagesY = dim / PAGE_SIZE;

            pageTable[mip].resize(pagesX * pagesY);
            for (auto& entry : pageTable[mip]) {
                entry.resident = false;
                entry.physPageX = -1;
                entry.physPageY = -1;
                entry.mipLevel = mip;
            }
        }

        // 初始化物理页池
        physPages.resize(MAX_PHYS_PAGES);
        for (auto& p : physPages) {
            p.allocated = false;
        }
    }

    // GPU 采样时的页表查找（模拟）
    // 输入：虚拟 UV + 导数（用于选择 Mip Level）
    // 输出：物理 UV + 是否命中
    struct SampleResult {
        bool  hit;           // 页是否在物理纹理中
        float physU, physV;  // 转换后的物理 UV
        int   mipLevel;      // 使用的 Mip Level
    };

    SampleResult Sample(float virtualU, float virtualV, float dUVdx, float dUVdy) {
        // 计算 Mip Level（基于导数）
        float maxDeriv = std::max(
            std::max(std::abs(dUVdx), std::abs(dUVdy)),
            std::max(std::abs(dUVdx), std::abs(dUVdy))  // dUVdx 和 dUVdy 各两分量
        );
        // 重新计算：用完整的 2D 导数
        float dudx = dUVdx, dvdx = dUVdy;  // 简化，实际应该是 vec2
        float dudy = dUVdx, dvdy = dUVdy;  // 同上
        float maxGrad = std::max(
            std::sqrt(dudx*dudx + dvdx*dvdx),
            std::sqrt(dudy*dudy + dvdy*dvdy)
        );

        // 选择 Mip Level
        int mipLevel = (int)std::floor(std::log2(
            maxGrad * VIRTUAL_DIM + 0.5f
        ));
        mipLevel = std::max(0, std::min(mipLevel, numMipLevels - 1));

        int vDim = VIRTUAL_DIM >> mipLevel;
        int pagesX = vDim / PAGE_SIZE;

        // 计算虚拟页坐标
        float texelU = virtualU * vDim;
        float texelV = virtualV * vDim;
        int pageX = (int)(texelU / PAGE_SIZE);
        int pageY = (int)(texelV / PAGE_SIZE);

        // Safety clamp
        pageX = std::max(0, std::min(pageX, pagesX - 1));
        pageY = std::max(0, std::min(pageY, vDim / PAGE_SIZE - 1));

        int pageIndex = pageY * pagesX + pageX;
        auto& entry = pageTable[mipLevel][pageIndex];

        SampleResult result;
        result.mipLevel = mipLevel;

        if (entry.resident) {
            // 页命中：计算物理 UV
            float localU = texelU / PAGE_SIZE - pageX;  // 页内 UV (0-1)
            float localV = texelV / PAGE_SIZE - pageY;

            // 映射到物理页位置
            result.physU = (entry.physPageX + localU) / PHYS_PAGES_X;
            result.physV = (entry.physPageY + localV) / PHYS_PAGES_Y;
            result.hit = true;

            pageHits++;
            physPages[entry.physPageY * PHYS_PAGES_X + entry.physPageX]
                .lastAccessFrame = currentFrame;
        } else {
            // 页缺失：触发加载请求
            result.hit = false;
            pageMisses++;
            RequestPageLoad(pageX, pageY, mipLevel);
        }

        return result;
    }

    void RequestPageLoad(int vpx, int vpy, int mip) {
        // 找一个空闲物理页
        int freePage = -1;
        for (int i = 0; i < MAX_PHYS_PAGES; ++i) {
            if (!physPages[i].allocated) {
                freePage = i;
                break;
            }
        }

        // 如果没有空闲页，驱逐最久未使用的页（LRU）
        if (freePage < 0) {
            int64_t oldest = INT64_MAX;
            for (int i = 0; i < MAX_PHYS_PAGES; ++i) {
                if (physPages[i].lastAccessFrame < oldest) {
                    oldest = physPages[i].lastAccessFrame;
                    freePage = i;
                }
            }
            // 驱逐旧页：更新页表
            auto& oldEntry = pageTable[physPages[freePage].mipLevel]
                [physPages[freePage].virtualPageY * (VIRTUAL_DIM / PAGE_SIZE)
                 + physPages[freePage].virtualPageX];
            oldEntry.resident = false;
        }

        // 分配物理页
        physPages[freePage].allocated = true;
        physPages[freePage].virtualPageX = vpx;
        physPages[freePage].virtualPageY = vpy;
        physPages[freePage].mipLevel = mip;
        physPages[freePage].lastAccessFrame = currentFrame;

        // 更新页表
        int vDim = VIRTUAL_DIM >> mip;
        int pagesX = vDim / PAGE_SIZE;
        auto& entry = pageTable[mip][vpy * pagesX + vpx];
        entry.resident = true;
        entry.physPageX = (int16_t)(freePage % PHYS_PAGES_X);
        entry.physPageY = (int16_t)(freePage / PHYS_PAGES_X);
        entry.mipLevel = (int16_t)mip;
    }

    void AdvanceFrame() { currentFrame++; }

    void PrintStats() const {
        int64_t total = pageHits + pageMisses;
        std::cout << "========== 虚拟纹理统计 ==========\n";
        std::cout << "虚拟纹理大小: " << VIRTUAL_DIM << "×" << VIRTUAL_DIM << "\n";
        std::cout << "物理页池: " << PHYSICAL_DIM << "×" << PHYSICAL_DIM
                  << " (" << MAX_PHYS_PAGES << " 页，每页 " << PAGE_SIZE << "×" << PAGE_SIZE << ")\n";
        std::cout << "总采样次数: " << total << "\n";
        if (total > 0) {
            std::cout << "页命中: " << pageHits << " (" 
                      << std::fixed << std::setprecision(1)
                      << (100.0 * pageHits / total) << "%)\n";
            std::cout << "页缺失: " << pageMisses << " ("
                      << (100.0 * pageMisses / total) << "%)\n";
        }

        int usedPages = 0;
        for (auto& p : physPages) {
            if (p.allocated) usedPages++;
        }
        std::cout << "已用物理页: " << usedPages << "/" << MAX_PHYS_PAGES
                  << " (" << (100.0 * usedPages / MAX_PHYS_PAGES) << "%)\n";
    }
};

int main() {
    VirtualTextureSystem vt;

    std::cout << "========== 虚拟纹理页表查找演示 ==========\n\n";

    // 模拟 GPU 采样：大量针对附近区域的请求
    std::cout << "模拟 1000 次纹理采样...\n";
    for (int i = 0; i < 200; ++i) {
        // 主要区域 (0.2–0.4 UV)
        vt.Sample(0.25f + (i % 5) * 0.02f, 0.3f + (i % 3) * 0.03f, 0.001f, 0.001f);
        vt.AdvanceFrame();
    }
    for (int i = 0; i < 600; ++i) {
        // 扩展区域 (0.3–0.6 UV)
        vt.Sample(0.4f + (i % 10) * 0.02f, 0.35f + (i % 8) * 0.03f, 0.002f, 0.002f);
        vt.AdvanceFrame();
    }
    for (int i = 0; i < 200; ++i) {
        // 远处跳跃（缺页多）
        vt.Sample(0.8f + (i % 3) * 0.05f, 0.1f + (i % 4) * 0.05f, 0.0005f, 0.0005f);
        vt.AdvanceFrame();
    }

    vt.PrintStats();

    std::cout << "\n========== 纹理压缩格式速查 ==========\n";
    std::cout << "PC 平台:\n";
    std::cout << "  Diffuse (RGB):     BC1 (4bpp, 8:1)\n";
    std::cout << "  Diffuse (RGBA):    BC7 (8bpp, 4:1)\n";
    std::cout << "  Normal Map:        BC5 (8bpp, 4:1) — 两个通道\n";
    std::cout << "  HDR/Skybox:        BC6H (8bpp, 4:1)\n";
    std::cout << "移动平台:\n";
    std::cout << "  重要纹理:          ASTC 4×4 (8bpp)\n";
    std::cout << "  一般纹理:          ASTC 6×6 (3.56bpp)\n";
    std::cout << "  远处/UI背景:       ASTC 8×8 (2bpp)\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: 计算纹理预算

一个开放世界游戏，目标 8GB 显存。假设：
- 渲染目标（G-Buffer + 深度 + 后处理）占用 800MB
- Mesh 数据占用 1.2GB
- 其他（CB、Shader、RT）占用 0.5GB
- 剩余全是纹理

如果平均每个材质 4 张贴图（BC7 2K），最多能有多少个不同材质？如果改用 ASTC 6×6 呢？

### 练习 2: 分析你项目的纹理

在 Unity 编辑器中：
1. 打开 Project 窗口，按 Size 排序纹理
2. 找出最大的 10 个纹理，记录分辨率和格式
3. 逐一判断：是否真的需要这么大的分辨率？
4. 估算将它们降级可节省的显存

### 练习 3: 实现简易纹理图集打包器（挑战）

用 Python 实现一个简单的 Bin Packing 算法（First Fit Decreasing Height）：
- 输入：N 张不同大小的纹理（width, height 列表）
- 输出：图集的尺寸和每张子纹理的 UV 坐标
- 约束：图集边长必须是 2 的幂
- 额外：为每个子纹理生成 2 像素的 UV Padding

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **纹理预算计算：**
>
> ```
> 总显存:                    8.0 GB  = 8192 MB
> 渲染目标 (G-Buffer + 深度等):  -800 MB
> Mesh 数据:                  -1200 MB
> 其他 (CB/Shader/RT):         -500 MB
> ─────────────────────────────────────────
> 纹理可用预算:               5692 MB
> ```
>
> **方案 A：BC7 2K 纹理：**
> ```
> 单张 2K BC7 纹理 (含 Mipmap): 2048×2048/16 blocks × 16 bytes/block × 4/3
>                             = 262,144 × 16 × 1.333
>                             = 5,592,405 bytes ≈ 5.33 MB
>
> 每个材质 4 张贴图:          ≈ 21.33 MB
> 最多材质数:                 5692 / 21.33 ≈ 267 个材质
> ```
>
> **方案 B：ASTC 6×6 2K 纹理：**
> ```
> 单张 2K ASTC 6×6 纹理 (含 Mipmap): 2048×2048/36 blocks × 16 bytes/block × 4/3
>                                   = 116,508 × 16 × 1.333
>                                   = 2,484,061 bytes ≈ 2.37 MB
>
> 每个材质 4 张贴图:          ≈ 9.48 MB
> 最多材质数:                 5692 / 9.48 ≈ 600 个材质
> ```
>
> | 格式 | 单张 2K 大小 | 4 张/材质 | 最多材质数 |
> |------|------------|----------|-----------|
> | BC7 | 5.33 MB | 21.33 MB | ~267 |
> | ASTC 6×6 | 2.37 MB | 9.48 MB | ~600 |
>
> **结论**：使用 ASTC 6×6 可支持的材质数量是 BC7 的 2.25 倍。但注意：ASTC 在 PC 上需要 DX11+ 或 Vulkan 支持。

> [!tip]- 练习 2 参考答案
> **Unity 中分析纹理的操作步骤：**
>
> 1. **打开 Project 窗口，按大小排序**：
>    - Project 窗口 → 右上角菜单 → "One Column Layout" 或使用 `Editor.dll` 扩展
>    - 更直接的方法：Window → Analysis → **Asset Manager** (Unity 2022+) 或使用 **Build Report**
>    - 或者写 Editor 脚本：
>      ```csharp
>      // 在 Unity Editor 中运行
>      var textures = AssetDatabase.FindAssets("t:Texture2D")
>          .Select(guid => AssetDatabase.GUIDToAssetPath(guid))
>          .Select(path => AssetImporter.GetAtPath(path) as TextureImporter)
>          .Where(imp => imp != null);
>      foreach (var t in textures.OrderByDescending(t => {
>          var info = new FileInfo(t.assetPath);
>          return info.Exists ? info.Length : 0;
>      }).Take(10)) {
>          var info = new FileInfo(t.assetPath);
>          Debug.Log($"{t.name}: {info.Length / 1024 / 1024}MB, "
>                  + $"MaxSize={t.maxTextureSize}, Format={t.textureFormat}");
>      }
>      ```
>
> 2. **逐一判断**（对最大的 10 个纹理）：
>    ```
>    纹理名              分辨率       格式     大小      建议
>    ────────────────────────────────────────────────────────────
>    Skybox_HDRI         4096×2048    RGBA Half  32 MB   可降为 2048×1024 (8MB)
>    Terrain_Diffuse     4096×4096    BC7       21 MB    地形可拆分多 Tile
>    Character_Body      4096×4096    BC7       21 MB    主角保持，NPC 降为 2K
>    UI_Background       4096×4096    RGBA32    64 MB    无脑用 4K 浪费！降为 1024
>    Props_Atlas         4096×4096    BC7       21 MB    合理 - 图集合批
>    Foliage_Atlas       4096×4096    BC7       21 MB    合理
>    Building_Facade     4096×4096    BC7       21 MB    远景建筑 2K 足够
>    Ground_Mud          2048×2048    BC7       5.3 MB   可接受
>    Particle_Sheet      2048×2048    BC7       5.3 MB   可接受
>    Logo_Splash         2048×2048    RGBA32   16 MB    用 BC7 代替 RGBA32!
>    ────────────────────────────────────────────────────────────
>    节省显存估算:          ~100 MB
>    ```
>
> 3. **常见"无脑 4K"的浪费场景**：
>    - UI 背景图：屏幕上的 UI 通常只有 1920×1080 或更小，4K 完全浪费
>    - 小型道具：玩家永远不会靠近到能看到 4K 细节的距离
>    - 天空盒：2048×1024 已经足够（是环绕的，每个方向只占部分）
>    - UI 按钮/图标：256×256 或 512×512 即可

> [!tip]- 练习 3 参考答案（可选）
> ```python
> # bin_packing_atlas.py — First Fit Decreasing Height 纹理打包
> # 运行: python bin_packing_atlas.py
>
> from dataclasses import dataclass
> from typing import List, Tuple
> import math
>
> @dataclass
> class TextureRect:
>     name: str
>     width: int
>     height: int
>     x: int = 0   # 图集中的位置 (填充)
>     y: int = 0
>     u0: float = 0.0
>     v0: float = 0.0
>     u1: float = 0.0
>     v1: float = 0.0
>     padding: int = 2
>
> @dataclass
> class AtlasResult:
>     atlas_width: int
>     atlas_height: int
>     rects: List[TextureRect]
>     occupancy: float  # 空间利用率
>
> def next_power_of_two(n: int) -> int:
>     """返回 ≥ n 的最小 2 的幂"""
>     p = 1
>     while p < n:
>         p *= 2
>     return p
>
> def pack_textures(
>     textures: List[Tuple[str, int, int]],
>     padding: int = 2,
>     max_size: int = 4096
> ) -> AtlasResult:
>     """
>     First Fit Decreasing Height 算法：
>     1. 按高度降序排列纹理
>     2. 每个纹理放在第一个能容纳它的"货架"上
>     3. 货架满后开启新货架
>     """
>     # 创建对象并加 padding
>     rects = []
>     for name, w, h in textures:
>         r = TextureRect(name=name, width=w + 2*padding, height=h + 2*padding, padding=padding)
>         rects.append(r)
>
>     # 按高度降序排列 (FFDH)
>     rects.sort(key=lambda r: r.height, reverse=True)
>
>     # 简易货架算法
>     class Shelf:
>         def __init__(self, y, height, max_w):
>             self.y = y
>             self.height = height
>             self.remaining_x = 0
>             self.max_width = max_w
>
>         def try_place(self, w):
>             if self.remaining_x + w <= self.max_width:
>                 x = self.remaining_x
>                 self.remaining_x += w
>                 return x, self.y
>             return None
>
>     shelves: List[Shelf] = []
>     total_h = 0
>     max_w_used = 0
>
>     for rect in rects:
>         placed = False
>         # 尝试放入现有货架
>         for shelf in shelves:
>             result = shelf.try_place(rect.width)
>             if result is not None:
>                 rect.x, rect.y = result
>                 placed = True
>                 max_w_used = max(max_w_used, rect.x + rect.width)
>                 break
>
>         if not placed:
>             # 新建货架
>             new_shelf = Shelf(total_h, rect.height, max_size)
>             rect.x, rect.y = new_shelf.try_place(rect.width)
>             total_h += rect.height
>             shelves.append(new_shelf)
>             max_w_used = max(max_w_used, rect.width)
>
>     # 取 2 的幂作为图集尺寸
>     atlas_w = next_power_of_two(max_w_used)
>     atlas_h = next_power_of_two(total_h)
>
>     # 计算 UV 坐标
>     for rect in rects:
>         pad = rect.padding
>         rect.u0 = (rect.x + pad + 0.5) / atlas_w
>         rect.v0 = (rect.y + pad + 0.5) / atlas_h
>         rect.u1 = (rect.x + rect.width - pad - 0.5) / atlas_w
>         rect.v1 = (rect.y + rect.height - pad - 0.5) / atlas_h
>
>     # 计算空间利用率
>     used_area = sum(r.width * r.height for r in rects)
>     occupancy = used_area / (atlas_w * atlas_h) * 100
>
>     return AtlasResult(atlas_w, atlas_h, rects, occupancy)
>
>
> # ====== 测试 ======
> if __name__ == "__main__":
>     # 各种尺寸的纹理
>     textures = [
>         ("rock_diffuse",    512, 512),
>         ("grass_diffuse",   256, 256),
>         ("wood_planks",     512, 256),
>         ("metal_panel",     256, 512),
>         ("dirt_ground",    1024, 1024),
>         ("brick_wall",      512, 512),
>         ("stone_tile",      256, 256),
>         ("roof_shingle",    512, 256),
>         ("glass_window",    128, 256),
>         ("door_wood",       256, 512),
>         ("fence_iron",      256, 128),
>         ("ivy_vine",        512, 128),
>         ("crate_wood",      512, 512),
>         ("barrel_metal",    256, 256),
>     ]
>
>     result = pack_textures(textures, padding=2)
>
>     print(f"图集尺寸: {result.atlas_width}×{result.atlas_height}")
>     print(f"空间利用率: {result.occupancy:.1f}%\n")
>     print(f"{'纹理名':<20} {'原始尺寸':<12} {'图集位置':<12} {'UV 坐标'}")
>     print("-" * 70)
>     for r in result.rects:
>         print(f"{r.name:<20} {r.width-4}×{r.height-4:<6} "
>               f"({r.x},{r.y}:{r.width}×{r.height}) "
>               f"({r.u0:.4f},{r.v0:.4f})-({r.u1:.4f},{r.v1:.4f})")
>
>     print(f"\n注意: 每个纹理周围有 2px padding 防止 Mipmap 渗漏")
> ```
>
> **设计要点：**
> - FFDH（First Fit Decreasing Height）：按高度降序排列，放入第一个能容纳的货架
> - 图集尺寸取 2 的幂（GPU 要求）
> - 每个纹理周围 2px padding 防止 Mipmap 低层颜色渗漏
> - UV 坐标加半像素偏移避免边缘采样问题

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **NVIDIA Texture Compression Guide** — https://developer.nvidia.com/astc-texture-compression-for-game-assets：ASTC 和 BCn 的详细对比
- **ARM ASTC Evaluation Guide** — https://developer.arm.com/documentation/102162/latest/：如何评估不同 ASTC 块大小的质量
- **Bin Packing Algorithms** — http://panthema.net/2013/1125-Rectangle-Bin-Packing-FFDH/：图集打包的算法实现
- **UE Virtual Texturing** — https://docs.unrealengine.com/5.0/en-US/virtual-texturing-in-unreal-engine/：UE5 虚拟纹理系统
- **GPUOpen Texture Tool** — https://github.com/GPUOpen-Tools/Compressonator：AMD 的纹理压缩和对比工具

---

## 常见陷阱

- **用法线贴图用 BC1 压缩**：BC1 只有 4bpp，颜色端点 565 导致法线方向出现明显的 16 级量化台阶。正确姿势是用 BC5（双通道 8 位精度）。
- **图集没有 UV Padding**：导致 Mipmap 低层出现颜色渗漏，子纹理边缘出现相邻纹理的颜色。必须在每个子纹理周围留至少 2 像素边距。
- **所有纹理都无脑用 4K**：UI 的一个按钮背景用 4K 纹理纯属浪费。根据实际屏幕占比选择分辨率。
- **忽略 Mipmap 内存**：认为 4K BC7 = 21.3MB，忘了 Mipmap 链还有约 7MB。显存计算要带 Mip 链。
- **移动端用 DXT 格式**：DXT/BCn 在大多数移动 GPU 上不支持。移动端应该用 ASTC（首选）或 ETC2（fallback）。
- **Texture Streaming 池太小导致纹理永远模糊**：默认 1000MB 对现代游戏不够。根据目标设备显存调整（UE: `r.Streaming.PoolSize`）。
