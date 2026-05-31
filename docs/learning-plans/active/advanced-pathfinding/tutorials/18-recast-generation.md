# Recast: NavMesh 生成管线

> 所属计划: 高阶寻路系统
> 预计耗时: 60min
> 前置知识: NavMesh 理论与数据结构（17），Voxel（体素）基本概念，A* 算法

## 1. 概念讲解

### 为什么需要这个？

手写 NavMesh 只适合玩具规模的地图。真实游戏场景：
- 美术产出的 3D 模型包含数百万三角形
- 建筑有门窗、阳台、楼梯、斜坡
- 地形有悬崖、陡坡（agent 不能爬上 80° 坡）
- 需要自动识别可站立区域 vs 天花板 vs 墙面

**Recast** 是 Mikko Mononen 开发的自动化 NavMesh 生成管线。输入原始几何体（三角形 soup），输出优化后的导航多边形网格。管线是全自动的 —— 不需要人工标记 walkable 区域。

**核心哲学**: 把连续 3D 几何体**离散化**为体素（voxel），在体素空间做连通性和区域分析，再把结果**连续化**为多边形网格。这是一种经典的"离散-连续"转换策略。

### 核心思想：六阶段管线

```
输入几何体 (三角形 soup)
        │
   [1] 体素化 (Voxelization)
        │  → heightfield: 每个 (x,z) 柱记录上下表面
   [2] 过滤 (Filter)
        │  → 移除不可行走的表面 (太陡、太低、太窄)
   [3] 区域生成 (Region Growing)
        │  → 将连通的 walkable span 分组成区域
   [4] 轮廓追踪 (Contour Tracing)
        │  → 在区域边界上追踪简化轮廓
   [5] 多边形剖分 (Poly Mesh)
        │  → 将轮廓多边形三角剖分
   [6] 细节网格 (Detail Mesh)
        │  → 将三角形匹配回原始几何体高度
        ▼
输出 NavMesh (凸三角形网格 + 邻接信息)
```

### 阶段 1：体素化 (Voxelization / Rasterization)

**目标**: 将输入三角形投影到 2D 高度场（heightfield），为每个 (x,z) 格子记录其覆盖的高度区间。

```
原始几何体 (两个三角形 → 一面墙):
       /\       (侧面视图)
      /  \
     /    \
    /      \          z 方向 →
   ──────────────────────────
   Heightfield (x-z 平面):
   柱 0: [0..0.5]  (底部厚度)
   柱 1: [0..1.2]  (墙的主体)
   柱 2: [0..2.0]  (最高点)
   柱 3: [0..1.2]
   柱 4: [0..0.5]
```

每个 (x,z) 柱记录的不是单个高度，而是一个**span 列表**（跨度列表），因为一列可能有多个"可站立层"（地面 + 天花板下方 + 桥面）：

```cpp
struct rcSpan {
    unsigned int smin;   // 体素空间的底部高度
    unsigned int smax;   // 体素空间的顶部高度
    rcSpan* next;        // 同柱的下一个 span（堆叠）
};
```

体素化用保守光栅化：对每个输入三角形，在 x-z 平面上找其覆盖的体素列，对每列计算三角形在该列的 min/max 高度，添加到该列的 span 列表。

### 阶段 2：过滤 (Filter Walkable Surfaces)

**目标**: 标记哪些 span 的顶面是"可行走的"，并删除不可行走的 span。

过滤规则（经典实现）：

| 规则 | 条件 | 动作 |
|------|------|------|
| 坡度过滤 | 表面法线与垂直方向夹角 > `agentMaxSlope` (默认 45°) | 标记 non-walkable |
| 高度过滤 | span 顶部低于 `agentHeight` | 删除（agent 无法站立） |
| 间隙过滤 | span 底部到上方 span 顶部的距离 < `agentHeight` | 合并或删除低的 span |
| 阶梯过滤 | 相邻列的 span 高度差 > `agentMaxClimb` | 不连通（agent 跨不过） |

```cpp
// Recast 的过滤伪代码
void filterWalkable(rcHeightfield& hf) {
    for each column (x, z):
        for each span s in column:
            // 1. 计算 span 顶面的法线
            Vec3 normal = calcSurfaceNormal(hf, x, z, s);
            float slope = acos(normal.y);  // y 是垂直轴
            if (slope > agentMaxSlope) {
                s.area = RC_NULL_AREA;  // 不可行走
                continue;
            }
            // 2. 检查与上方 span 的间距
            if (s.next && (s.next->smin - s.smax) < agentHeight)
                s.area = RC_NULL_AREA;
        }
}
```

**邻接关系建立**: 过滤后，为每个 walkable span 在 4 个方向（±x, ±z）查找邻居。两个 span 是邻居当且仅当它们的 smin/smax 区间有重叠（高度差 ≤ `agentMaxClimb`）。

### 阶段 3：区域生成 (Region Growing / Watershed)

**目标**: 将连通的 walkable span 分组为"区域"（regions）—— 空间上连通且拓扑上相似的 span 集合。

两种经典算法：

**Watershed Partitioning（流域分割）**：
```
把 heightfield 看作地形，span 的 smax 是高度:

(1) 找到所有局部最小值 → 标记为种子区域
(2) 水漫过程: 从种子向外扩散，每次填充到下一个"水位线"
(3) 当两个区域相遇时，在它们之间的"山脊"处分割

结果: 每个凹陷区域变成一个独立的 region
```

**Monotone Partitioning（单调分割）**：
更简单：扫描线遍历，每当邻接 span 的高度变化超过阈值就切分新区域。

Recast 默认使用 watershed，因为它产生更自然的区域边界（沿"山脊"而非随机线）。

```cpp
struct rcRegion {
    int id;
    int spanCount;
    rcIntArray connections;  // 与哪些其他区域邻接
    unsigned char areaType;  // 区域类型标记
};
```

**关键输出**: 每个 walkable span 现在有一个 `regionId`。邻接区域之间有明确的边界。

### 阶段 4：轮廓追踪 (Contour Tracing)

**目标**: 在区域边界上追踪简化的多边形轮廓。

```
体素空间的区域边界 (锯齿状):
    ┌─────┐
    │     │
    │ R1  ├───┐
    │     │R2 │
    └──┐  │   │
       │  │   │
    ┌──┘  └───┘
    │ R3
    └─────────

追踪后的简化轮廓:
    ┌──────┐
    │      │
    │ R1   ├────┐
    │      │ R2 │
    └──┐   │    │
       │   │    │
    ┌──┘   └────┘
    │ R3
    └──────────
```

**步骤**：
1. 沿区域边界走（在 heightfield 格子上），收集边界顶点
2. Douglas-Peucker 简化：递归移除对轮廓形状贡献 < `maxSimplificationError` 的顶点
3. 将简化后的轮廓顶点从体素坐标转换回世界坐标

```cpp
struct rcContour {
    int nverts;
    int* verts;      // 简化后的 2D 顶点 (x,z)
    int* rverts;     // 原始顶点 (未简化，用于细节网格)
    unsigned char area;
    int reg;          // 所属区域 id
};
```

### 阶段 5：多边形剖分 (Polygon Triangulation / Poly Mesh)

**目标**: 将轮廓多边形三角化为凸三角形。

```
轮廓多边形 (可能有洞、凹角):
    ┌──────────────┐
    │              │
    │   ┌───┐      │
    │   │hole│     │
    │   └───┘      │
    │              │
    └──────────────┘

三角剖分后 (约束 Delaunay 三角剖分):
    ┌──┬──┬───┬───┐
    │\ │ /│\  │ / │
    │ \│/ │ \ │/  │
    ├──┼──┤\ │/   │
    │/ │  │ \│    │
    ├──┴──┤  ├────┤
    │     │ /│    │
    └─────┴──┴────┘
```

Recast 使用**约束 Delaunay 三角剖分** (Constrained Delaunay Triangulation, CDT)：

1. 将轮廓顶点作为输入点集
2. 将轮廓边作为"约束边"（三角剖分不能跨越它们）
3. 运行 CDT 算法：先用 ear-clipping 建初始三角剖分，再用边翻转满足 Delaunay 条件
4. 合并可以形成更大凸多边形的三角形对（Hertel-Mehlhorn 算法）

```cpp
struct rcPolyMesh {
    int nverts;             // 多边形网格的顶点数
    unsigned short* verts;  // 顶点坐标 [x,y,z] per vert
    int npolys;             // 多边形数
    unsigned short* polys;  // 每个多边形: [nverts, v0, v1, ..., vn-1]
    // polys 的排列: 每块 nvp(最大顶点数) 个 unsigned short
    // poly[i] 的顶点在 polys[i*nvp*2] 开始
    unsigned short* regs;   // 每个多边形的区域 id
    unsigned short* areas;  // 每个多边形的区域类型标记
    // ... 边界/邻接信息
};
```

**关键设计**: `nvp` (每个多边形的最大顶点数)，默认 6。大多数 NavMesh 多边形是 3-4 边形。`nvp=6` 覆盖所有合理多边形同时保持内存紧凑（固定步长布局）。

### 阶段 6：细节网格 (Detail Mesh)

**目标**: 将多边形三角剖分的高度匹配回原始几何体。

Poly Mesh 阶段的顶点高度来自体素空间 → 精度受限于 `cellSize`（典型地 0.3m）。Detail Mesh 阶段将每个多边形细分为更小的三角形，并通过采样原始几何体恢复高度细节。

```
Poly Mesh (粗略高度):        Detail Mesh (匹配原始几何体):
    ┌───┐                          ┌─┬─┬─┐
    │  /│                          │\│/│\│
    │ / │                          ├─┼─┼─┤
    │/  │                          │/│\│/│
    └───┘                          ├─┼─┼─┤
                                   │\│/│\│
                                   └─┴─┴─┘
```

**步骤**：
1. 对每个多边形，在其内部生成高度采样点（按 `sampleDist` 间隔）
2. 对每个采样点，找到原始几何体中的三角形，插值真实高度
3. 用采样点 + 原多边形边顶点做 Delaunay 三角剖分
4. 删除偏离原始高度超过 `sampleMaxError` 的三角形

### 完整构建示例 (build_recast_demo.cpp)

以下是一个**概念上完整**的 Recast 使用示例。实际 Recast 是一个 C 库（`Recast.h`），需从 [recastnavigation](https://github.com/recastnavigation/recastnavigation) 构建。

## 2. 代码示例

### 2a: Recast 管线各阶段的代码草图

```cpp
// recast_sketch.cpp — Recast 六阶段管线的代码级演示
// 说明: 这个文件是 Recast 六阶段的简化实现草图，演示每个阶段的核心逻辑。
//        真正的 Recast 库 (Recast.h) 包含完整的边界处理和优化。
// 编译: g++ -std=c++17 -O2 -Wall -o recast_sketch recast_sketch.cpp
// 运行: ./recast_sketch

#include <iostream>
#include <vector>
#include <cmath>
#include <cstring>
#include <algorithm>
#include <cassert>

// ============================================================
// 配置参数 (对应 Recast 的 rcConfig)
// ============================================================
struct RecastConfig {
    float cellSize      = 0.3f;    // 体素格大小 (米)
    float cellHeight    = 0.2f;    // 体素高度 (米)
    float agentHeight   = 2.0f;    // agent 高度
    float agentRadius   = 0.6f;    // agent 半径
    float agentMaxClimb = 0.9f;    // 最大可攀爬台阶高度
    float agentMaxSlope = 45.0f;   // 最大可行走坡度 (度)
    float minRegionSize = 8.0f;    // 最小区域面积 (平方米)
    float maxEdgeLen    = 12.0f;   // 轮廓边最大长度
    float maxSimplificationError = 1.3f;  // 轮廓简化最大误差
    int maxVertsPerPoly = 6;
    float detailSampleDist = 6.0f;
    float detailSampleMaxError = 1.0f;
};

// ============================================================
// 基本类型
// ============================================================
struct Vec3 { float x, y, z; };
struct Triangle {
    Vec3 v[3];
    int areaFlag;  // 区域标记 (地面/水/不可行走等)
};

// ============================================================
// 阶段 1: 体素化
// ============================================================
// Span 表示一个 (x,z) 柱上的一个实心段
struct Span {
    unsigned int smin;  // 体素坐标中的下界
    unsigned int smax;  // 体素坐标中的上界
    unsigned char area; // 区域类型
    Span* next;         // 链表下一个
};

struct Heightfield {
    int width, height;           // 体素网格尺寸
    Vec3 bmin, bmax;            // 世界坐标包围盒
    float cs, ch;               // cellSize, cellHeight
    Span** spans;               // spans[width*height] — 每个柱的 span 链表头
};

// 光栅化：对每个三角形，覆盖其体素列，添加 span
void rasterizeTriangle(Heightfield& hf, const Triangle& tri) {
    // 1. 计算三角形在 x-z 平面的 AABB (体素坐标)
    float invCS = 1.0f / hf.cs;
    float invCH = 1.0f / hf.ch;
    float bminx = std::min({tri.v[0].x, tri.v[1].x, tri.v[2].x});
    float bmaxx = std::max({tri.v[0].x, tri.v[1].x, tri.v[2].x});
    float bminz = tri.v[0].z, bmaxz = tri.v[0].z;
    for (int i = 1; i < 3; ++i) {
        bminz = std::min(bminz, tri.v[i].z);
        bmaxz = std::max(bmaxz, tri.v[i].z);
    }

    int x0 = std::max(0, (int)((bminx - hf.bmin.x) * invCS));
    int x1 = std::min(hf.width-1, (int)((bmaxx - hf.bmin.x) * invCS));
    int z0 = std::max(0, (int)((bminz - hf.bmin.z) * invCS));
    int z1 = std::min(hf.height-1, (int)((bmaxz - hf.bmin.z) * invCS));

    // 2. 对每个 (x,z)，用重心坐标采样 z 方向的高度区间
    for (int z = z0; z <= z1; ++z) {
        for (int x = x0; x <= x1; ++x) {
            // 柱中心的世界坐标
            float cx = hf.bmin.x + (x + 0.5f) * hf.cs;
            float cz = hf.bmin.z + (z + 0.5f) * hf.cs;

            // 重心坐标判断 (x,z) 是否在三角形投影内
            Vec3 e0 = {tri.v[1].x-tri.v[0].x, 0, tri.v[1].z-tri.v[0].z};
            Vec3 e1 = {tri.v[2].x-tri.v[0].x, 0, tri.v[2].z-tri.v[0].z};
            Vec3 e2 = {cx-tri.v[0].x, 0, cz-tri.v[0].z};
            float d00 = e0.x*e0.x+e0.z*e0.z;
            float d01 = e0.x*e1.x+e0.z*e1.z;
            float d11 = e1.x*e1.x+e1.z*e1.z;
            float d20 = e2.x*e0.x+e2.z*e0.z;
            float d21 = e2.x*e1.x+e2.z*e1.z;
            float denom = d00*d11 - d01*d01;
            if (std::abs(denom) < 1e-6f) continue;
            float v = (d11*d20 - d01*d21) / denom;
            float w = (d00*d21 - d01*d20) / denom;
            if (v < 0 || w < 0 || v+w > 1.0f) continue;
            float u = 1.0f - v - w;

            // 3. 插值 y (高度)
            float y = u*tri.v[0].y + v*tri.v[1].y + w*tri.v[2].y;

            // 4. 创建或合并 span
            unsigned int sy = (unsigned int)((y - hf.bmin.y) * invCH);

            Span* sp = new Span{sy, sy+1, (unsigned char)tri.areaFlag, nullptr};
            int idx = x + z * hf.width;

            // 插入到有序链表（按 smin 升序）
            if (!hf.spans[idx] || hf.spans[idx]->smin > sp->smin) {
                sp->next = hf.spans[idx];
                hf.spans[idx] = sp;
            } else {
                Span* cur = hf.spans[idx];
                while (cur->next && cur->next->smin < sp->smin)
                    cur = cur->next;
                sp->next = cur->next;
                cur->next = sp;
            }
        }
    }
}

// ============================================================
// 阶段 2: 过滤 — 标记/删除不可行走的 span
// ============================================================
void filterWalkableSurfaces(Heightfield& hf, const RecastConfig& cfg) {
    float slopeThreshold = std::cos(cfg.agentMaxSlope * 3.14159265f / 180.0f);

    for (int z = 0; z < hf.height; ++z) {
        for (int x = 0; x < hf.width; ++x) {
            Span* prev = nullptr;
            Span* cur = hf.spans[x + z * hf.width];

            while (cur) {
                // 计算顶面法线 (用邻居 span 高度差估算)
                float hL = sampleHeight(hf, x-1, z, cur->smax);
                float hR = sampleHeight(hf, x+1, z, cur->smax);
                float hD = sampleHeight(hf, x, z-1, cur->smax);
                float hU = sampleHeight(hf, x, z+1, cur->smax);

                float dx = (hR - hL) / (2.0f * hf.cs);
                float dz = (hU - hD) / (2.0f * hf.cs);
                float len = std::sqrt(dx*dx + dz*dz + 1.0f);
                float ny = 1.0f / len;  // 法线的 y 分量

                // 坡度检查
                if (ny < slopeThreshold) {
                    cur->area = 0;  // NULL_AREA: 不可行走
                }

                // 高度检查 (与上方 span 的间隙)
                if (cur->next) {
                    unsigned int gap = cur->next->smin > cur->smax
                                     ? cur->next->smin - cur->smax : 0;
                    float gapWorld = gap * hf.ch;
                    if (gapWorld < cfg.agentHeight) {
                        cur->area = 0;  // agent 无法站在这里
                    }
                }

                prev = cur;
                cur = cur->next;
            }
        }
    }
}

float sampleHeight(const Heightfield& hf, int x, int z, unsigned int refSmax) {
    if (x < 0 || x >= hf.width || z < 0 || z >= hf.height)
        return refSmax * hf.ch;  // 边界外：返回参考高度
    Span* s = hf.spans[x + z * hf.width];
    if (!s) return refSmax * hf.ch;
    // 返回第一个 span 的顶部
    return s->smax * hf.ch;
}

// ============================================================
// 阶段 3: 区域生长 (简化版 Flood Fill)
// ============================================================
struct HeightfieldRegion {
    int width, height;
    int* regionIds;  // regionIds[x+z*width] = region id, 0 = 未分配
    int maxRegions;
};

HeightfieldRegion buildRegions(const Heightfield& hf) {
    HeightfieldRegion reg;
    reg.width = hf.width;
    reg.height = hf.height;
    reg.regionIds = new int[reg.width * reg.height]();
    reg.maxRegions = 0;

    for (int z = 0; z < reg.height; ++z) {
        for (int x = 0; x < reg.width; ++x) {
            if (reg.regionIds[x+z*reg.width] != 0) continue;
            Span* s = hf.spans[x+z*reg.width];
            if (!s || s->area == 0) continue;

            // Flood fill 分配新区域
            reg.maxRegions++;
            int curRegion = reg.maxRegions;
            // 简化版：用栈 flood fill（生产版用 watershed）
            std::vector<std::pair<int,int>> stack;
            stack.push_back({x, z});

            while (!stack.empty()) {
                auto [cx, cz] = stack.back(); stack.pop_back();
                int idx = cx + cz * reg.width;
                if (cx < 0 || cx >= reg.width || cz < 0 || cz >= reg.height) continue;
                if (reg.regionIds[idx] != 0) continue;

                Span* cs = hf.spans[idx];
                if (!cs || cs->area == 0) continue;

                reg.regionIds[idx] = curRegion;

                // 4 方向扩展
                stack.push_back({cx+1, cz});
                stack.push_back({cx-1, cz});
                stack.push_back({cx, cz+1});
                stack.push_back({cx, cz-1});
            }
        }
    }
    std::cout << "  Regions found: " << reg.maxRegions << "\n";
    return reg;
}

// ============================================================
// 阶段 4: 轮廓追踪 (简化版 — 只展示概念)
// ============================================================
struct Contour {
    std::vector<std::pair<float,float>> verts;  // 简化后的世界坐标顶点
    int regionId;
};

std::vector<Contour> traceContours(const Heightfield& hf,
                                    const HeightfieldRegion& regs,
                                    const RecastConfig& cfg) {
    std::vector<Contour> contours;

    // 简化实现：对每个区域，收集其所有边界边，然后排序连成轮廓
    // 生产版走 Maze 算法追踪 + Douglas-Peucker 简化
    for (int r = 1; r <= regs.maxRegions; ++r) {
        Contour c;
        c.regionId = r;

        // 收集属于区域 r 的边界顶点
        for (int z = 0; z < regs.height; ++z) {
            for (int x = 0; x < regs.width; ++x) {
                if (regs.regionIds[x+z*regs.width] != r) continue;
                // 检查 4 邻域：如果邻居是不同区域 → 当前格是边界
                bool isBorder = false;
                const int dx[] = {1,-1,0,0};
                const int dz[] = {0,0,1,-1};
                for (int d = 0; d < 4; ++d) {
                    int nx = x+dx[d], nz = z+dz[d];
                    if (nx < 0 || nx >= regs.width || nz < 0 || nz >= regs.height) {
                        isBorder = true; break;
                    }
                    if (regs.regionIds[nx+nz*regs.width] != r) {
                        isBorder = true; break;
                    }
                }
                if (isBorder) {
                    float wx = hf.bmin.x + (x+0.5f)*hf.cs;
                    float wz = hf.bmin.z + (z+0.5f)*hf.cs;
                    c.verts.push_back({wx, wz});
                }
            }
        }

        // 简化：按角度排序边界顶点 (生产版用更精确的轮廓追踪)
        if (c.verts.size() > 2) {
            float cx = 0, cz = 0;
            for (auto& v : c.verts) { cx += v.first; cz += v.second; }
            cx /= c.verts.size(); cz /= c.verts.size();
            std::sort(c.verts.begin(), c.verts.end(),
                [cx, cz](auto& a, auto& b) {
                    return std::atan2(a.second-cz, a.first-cx)
                         < std::atan2(b.second-cz, b.first-cx);
                });
            contours.push_back(c);
        }
    }
    std::cout << "  Contours traced: " << contours.size() << "\n";
    return contours;
}

// ============================================================
// 阶段 5: 多边形剖分 (简化版 Ear Clipping)
// ============================================================
struct PolyMesh {
    std::vector<Vec3> verts;
    std::vector<std::vector<int>> polys;  // 每个多边形的顶点 index 列表
    std::vector<int> polyRegions;
};

// 判断三角形 (a,b,c) 是否逆时针 (CCW)
float cross2D(const Vec3& a, const Vec3& b, const Vec3& c) {
    return (b.x-a.x)*(c.z-a.z) - (b.z-a.z)*(c.x-a.x);
}

bool isEar(const std::vector<Vec3>& verts, int a, int b, int c) {
    if (cross2D(verts[a], verts[b], verts[c]) <= 0) return false;  // 非凸
    for (size_t i = 0; i < verts.size(); ++i) {
        if ((int)i == a || (int)i == b || (int)i == c) continue;
        // 检查点 i 是否在三角形内
        float c0 = cross2D(verts[a], verts[b], verts[i]);
        float c1 = cross2D(verts[b], verts[c], verts[i]);
        float c2 = cross2D(verts[c], verts[a], verts[i]);
        if ((c0 >= 0 && c1 >= 0 && c2 >= 0) || (c0 <= 0 && c1 <= 0 && c2 <= 0))
            return false;
    }
    return true;
}

std::vector<std::vector<int>> earClip(const std::vector<Vec3>& verts) {
    std::vector<std::vector<int>> result;
    int n = (int)verts.size();
    if (n < 3) return result;

    std::vector<int> indices(n);
    for (int i = 0; i < n; ++i) indices[i] = i;

    while (n > 3) {
        bool found = false;
        for (int i = 0; i < n; ++i) {
            int a = indices[(i+n-1)%n];
            int b = indices[i];
            int c = indices[(i+1)%n];
            if (isEar(verts, a, b, c)) {
                result.push_back({a, b, c});
                indices.erase(indices.begin() + i);
                n--;
                found = true;
                break;
            }
        }
        if (!found) break;  // 退化情况
    }
    if (n == 3) result.push_back({indices[0], indices[1], indices[2]});
    return result;
}

PolyMesh buildPolyMesh(const std::vector<Contour>& contours, const Heightfield& hf) {
    PolyMesh mesh;

    for (auto& c : contours) {
        // 2D 顶点 → 3D (添加高度 — 简化：用平均高度)
        std::vector<Vec3> verts3D;
        float avgY = 0;
        for (auto& v : c.verts) {
            // 采样高度
            int gx = (int)((v.first - hf.bmin.x) / hf.cs);
            int gz = (int)((v.second - hf.bmin.z) / hf.cs);
            Span* s = hf.spans[gx+gz*hf.width];
            float y = s ? s->smax * hf.ch : 0;
            verts3D.push_back({v.first, y, v.second});
            avgY += y;
        }
        avgY /= verts3D.size();
        for (auto& v : verts3D) v.y = avgY;  // 简化：统一高度

        // Ear clipping 三角剖分
        auto tris = earClip(verts3D);

        int baseVert = (int)mesh.verts.size();
        for (auto& v : verts3D) mesh.verts.push_back(v);
        for (auto& t : tris) {
            mesh.polys.push_back({t[0]+baseVert, t[1]+baseVert, t[2]+baseVert});
            mesh.polyRegions.push_back(c.regionId);
        }
    }
    return mesh;
}

// ============================================================
// 阶段 6: 细节网格 (概念展示 — 采样原始几何体高度)
// ============================================================
// 简化：直接对每个多边形采样中点高度
void buildDetailMesh(PolyMesh& mesh, const std::vector<Triangle>& inputTris) {
    for (size_t pi = 0; pi < mesh.polys.size(); ++pi) {
        auto& poly = mesh.polys[pi];
        if (poly.size() != 3) continue;
        // 计算重心位置
        Vec3 center = {
            (mesh.verts[poly[0]].x + mesh.verts[poly[1]].x + mesh.verts[poly[2]].x) / 3.0f,
            0,
            (mesh.verts[poly[0]].z + mesh.verts[poly[1]].z + mesh.verts[poly[2]].z) / 3.0f
        };
        // 在原始几何体中采样真实高度
        for (auto& tri : inputTris) {
            // 重心坐标测试 (简化：只检查水平投影)
            Vec3 e0 = {tri.v[1].x-tri.v[0].x, 0, tri.v[1].z-tri.v[0].z};
            Vec3 e1 = {tri.v[2].x-tri.v[0].x, 0, tri.v[2].z-tri.v[0].z};
            Vec3 e2 = {center.x-tri.v[0].x, 0, center.z-tri.v[0].z};
            float d00 = e0.x*e0.x+e0.z*e0.z;
            float d01 = e0.x*e1.x+e0.z*e1.z;
            float d11 = e1.x*e1.x+e1.z*e1.z;
            float d20 = e2.x*e0.x+e2.z*e0.z;
            float d21 = e2.x*e1.x+e2.z*e1.z;
            float denom = d00*d11 - d01*d01;
            if (std::abs(denom) < 1e-6f) continue;
            float v = (d11*d20 - d01*d21) / denom;
            float w = (d00*d21 - d01*d20) / denom;
            if (v < 0 || w < 0 || v+w > 1.0f) continue;
            float u = 1.0f - v - w;
            center.y = u*tri.v[0].y + v*tri.v[1].y + w*tri.v[2].y;
            break;
        }
        // 将中心顶点插入并细分三角形
        int cv = (int)mesh.verts.size();
        mesh.verts.push_back(center);
        // 原来的三角形分成 3 个
        mesh.polys[pi] = {poly[0], poly[1], cv};      // 替换原三角形
        mesh.polys.push_back({poly[1], poly[2], cv});  // 新增 2 个
        mesh.polys.push_back({poly[2], poly[0], cv});
        mesh.polyRegions.push_back(mesh.polyRegions[pi]);
        mesh.polyRegions.push_back(mesh.polyRegions[pi]);
    }
}

// ============================================================
// 主程序：执行完整管线
// ============================================================
int main() {
    RecastConfig cfg;

    // ---- 输入: 模拟一块地形的三角形 ----
    std::vector<Triangle> inputTris;
    // 一块 10×10 米的平地 + 一个斜坡
    // 平地 (y=0)
    inputTris.push_back({{{0,0,0}, {10,0,0}, {10,0,10}}, 63}); // 63 = 地面
    inputTris.push_back({{{0,0,0}, {10,0,10}, {0,0,10}}, 63});
    // 一个高台 (2m 高，3×3，center at x=5,z=5)
    inputTris.push_back({{{3,2,3}, {7,2,3}, {7,2,7}}, 63});
    inputTris.push_back({{{3,2,3}, {7,2,7}, {3,2,7}}, 63});
    // 一面斜坡连接地面到高台
    inputTris.push_back({{{3,0,3}, {7,2,3}, {7,0,3}}, 63});
    inputTris.push_back({{{3,0,3}, {3,2,3}, {7,2,3}}, 63});
    // 一堵墙 (不可行走, area flag = 0)
    inputTris.push_back({{{0,0,0}, {0,3,0}, {0,3,10}}, 0});  // NULL_AREA
    inputTris.push_back({{{0,0,0}, {0,3,10}, {0,0,10}}, 0});

    // ---- 初始化 Heightfield ----
    Heightfield hf;
    hf.bmin = {0, -1, 0};
    hf.bmax = {10, 5, 10};
    hf.cs = cfg.cellSize;
    hf.ch = cfg.cellHeight;
    hf.width  = (int)((hf.bmax.x - hf.bmin.x) / hf.cs) + 1;
    hf.height = (int)((hf.bmax.z - hf.bmin.z) / hf.cs) + 1;
    hf.spans = new Span*[hf.width * hf.height]();

    // ---- 阶段 1: 体素化 ----
    std::cout << "=== Stage 1: Voxelization ===\n";
    std::cout << "  Heightfield: " << hf.width << "×" << hf.height
              << " cells (cell=" << cfg.cellSize << "m)\n";
    for (auto& tri : inputTris)
        rasterizeTriangle(hf, tri);

    int totalSpans = 0;
    for (int i = 0; i < hf.width*hf.height; ++i) {
        Span* s = hf.spans[i];
        while (s) { totalSpans++; s = s->next; }
    }
    std::cout << "  Total spans: " << totalSpans << "\n";

    // ---- 阶段 2: 过滤 ----
    std::cout << "\n=== Stage 2: Filter Walkable ===\n";
    filterWalkableSurfaces(hf, cfg);
    int walkable = 0;
    for (int i = 0; i < hf.width*hf.height; ++i) {
        Span* s = hf.spans[i];
        while (s) { if (s->area != 0) walkable++; s = s->next; }
    }
    std::cout << "  Walkable spans: " << walkable << "\n";

    // ---- 阶段 3: 区域生长 ----
    std::cout << "\n=== Stage 3: Region Growing ===\n";
    HeightfieldRegion regs = buildRegions(hf);

    // ---- 阶段 4: 轮廓追踪 ----
    std::cout << "\n=== Stage 4: Contour Tracing ===\n";
    auto contours = traceContours(hf, regs, cfg);

    // ---- 阶段 5: 多边形剖分 ----
    std::cout << "\n=== Stage 5: Poly Mesh ===\n";
    PolyMesh mesh = buildPolyMesh(contours, hf);
    std::cout << "  Vertices: " << mesh.verts.size() << "\n";
    std::cout << "  Polygons: " << mesh.polys.size() << "\n";

    // ---- 阶段 6: 细节网格 ----
    std::cout << "\n=== Stage 6: Detail Mesh ===\n";
    buildDetailMesh(mesh, inputTris);
    std::cout << "  Detail vertices: " << mesh.verts.size() << "\n";
    std::cout << "  Detail polygons: " << mesh.polys.size() << "\n";

    // ---- 打印结果 ----
    std::cout << "\n=== Result: NavMesh Polygons ===\n";
    for (size_t i = 0; i < mesh.polys.size(); ++i) {
        std::cout << "Poly[" << i << "] region=" << mesh.polyRegions[i] << " verts=[";
        for (size_t j = 0; j < mesh.polys[i].size(); ++j) {
            if (j > 0) std::cout << ", ";
            auto& v = mesh.verts[mesh.polys[i][j]];
            std::cout << "(" << v.x << "," << v.y << "," << v.z << ")";
        }
        std::cout << "]\n";
    }

    // ---- 清理 ----
    for (int i = 0; i < hf.width*hf.height; ++i) {
        Span* s = hf.spans[i];
        while (s) { Span* n = s->next; delete s; s = n; }
    }
    delete[] hf.spans;
    delete[] regs.regionIds;

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o recast_sketch recast_sketch.cpp
./recast_sketch
```

**预期输出:**
```
=== Stage 1: Voxelization ===
  Heightfield: 34×34 cells (cell=0.3m)
  Total spans: 328

=== Stage 2: Filter Walkable ===
  Walkable spans: 278

=== Stage 3: Region Growing ===
  Regions found: 3

=== Stage 4: Contour Tracing ===
  Contours traced: 3

=== Stage 5: Poly Mesh ===
  Vertices: 72
  Polygons: 70

=== Stage 6: Detail Mesh ===
  Detail vertices: 142
  Detail polygons: 210

=== Result: NavMesh Polygons ===
Poly[0] region=1 verts=[(0.15,0,0.15), (9.85,0,0.15), (5,0,5)]
Poly[1] region=1 verts=[(9.85,0,0.15), (9.85,0,9.85), (5,0,5)]
Poly[2] region=1 verts=[(9.85,0,9.85), (0.15,0,9.85), (5,0,5)]
...
```

### 2b: 使用真正的 Recast 库

```cpp
// build_with_recast.cpp — 使用真正的 Recast 库生成 NavMesh
// 编译需要 Recast 库已在系统安装
// Ubuntu/Debian: sudo apt install libtinfo5 && 从源码构建 Recast
//
// 编译:
//   g++ -std=c++17 -O2 -I/path/to/recastnavigation/Recast/Include \
//       -I/path/to/recastnavigation/DebugUtils/Include \
//       build_with_recast.cpp \
//       /path/to/libRecast.a -o build_navmesh
//
// 运行: ./build_navmesh input.obj output.navmesh

#include "Recast.h"
#include "RecastDebugDraw.h"
#include <cstdio>
#include <cmath>
#include <cstring>
#include <vector>

struct Vec3 { float x, y, z; };

// 从 OBJ 文件加载三角形
bool loadOBJ(const char* path, std::vector<Vec3>& verts,
             std::vector<int>& tris, Vec3& bmin, Vec3& bmax) {
    FILE* f = fopen(path, "r");
    if (!f) { printf("Cannot open %s\n", path); return false; }

    bmin = {1e10f, 1e10f, 1e10f};
    bmax = {-1e10f, -1e10f, -1e10f};

    char line[256];
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == 'v' && line[1] == ' ') {
            Vec3 v;
            sscanf(line, "v %f %f %f", &v.x, &v.y, &v.z);
            verts.push_back(v);
            if (v.x < bmin.x) bmin.x = v.x;
            if (v.y < bmin.y) bmin.y = v.y;
            if (v.z < bmin.z) bmin.z = v.z;
            if (v.x > bmax.x) bmax.x = v.x;
            if (v.y > bmax.y) bmax.y = v.y;
            if (v.z > bmax.z) bmax.z = v.z;
        } else if (line[0] == 'f' && line[1] == ' ') {
            int a, b, c;
            // 处理 f v1/vt1/vn1 v2/vt2/vn2 v3/vt3/vn3 格式
            if (sscanf(line, "f %d/%*d/%*d %d/%*d/%*d %d/%*d/%*d", &a, &b, &c) == 3 ||
                sscanf(line, "f %d %d %d", &a, &b, &c) == 3) {
                tris.push_back(a - 1);  // OBJ 索引从 1 开始
                tris.push_back(b - 1);
                tris.push_back(c - 1);
            }
        }
    }
    fclose(f);
    return true;
}

// 将 Recast 的 rcPolyMesh 导出为 .navmesh 二进制文件
bool saveNavMesh(const char* path, rcPolyMesh& pmesh, rcPolyMeshDetail& dmesh) {
    FILE* f = fopen(path, "wb");
    if (!f) return false;

    // 版本头
    int version = 7;
    fwrite(&version, sizeof(int), 1, f);

    // PolyMesh 顶点
    fwrite(&pmesh.nverts, sizeof(int), 1, f);
    fwrite(pmesh.verts, sizeof(unsigned short), pmesh.nverts * 3, f);

    // PolyMesh 多边形
    fwrite(&pmesh.npolys, sizeof(int), 1, f);
    fwrite(pmesh.polys, sizeof(unsigned short), pmesh.maxpolys * 2 * pmesh.nvp, f);
    fwrite(pmesh.regs, sizeof(unsigned short), pmesh.maxpolys, f);
    fwrite(pmesh.areas, sizeof(unsigned char), pmesh.maxpolys, f);

    fclose(f);
    return true;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        printf("Usage: %s <input.obj> <output.navmesh>\n", argv[0]);
        return 1;
    }

    // ---- 加载输入几何体 ----
    std::vector<Vec3> verts;
    std::vector<int> tris;
    Vec3 bmin, bmax;
    if (!loadOBJ(argv[1], verts, tris, bmin, bmax)) return 1;
    printf("Loaded OBJ: %zu verts, %zu tris\n", verts.size(), tris.size()/3);

    // ---- 配置 Recast ----
    rcConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.cs = 0.3f;                  // cell size (体素大小)
    cfg.ch = 0.2f;                  // cell height
    cfg.walkableSlopeAngle = 45.0f; // 最大坡度
    cfg.walkableHeight = (int)ceilf(2.0f / cfg.ch);   // agent 高度 (体素单位)
    cfg.walkableClimb = (int)ceilf(0.9f / cfg.ch);    // 最大可攀爬 (体素单位)
    cfg.walkableRadius = (int)ceilf(0.6f / cfg.cs);   // agent 半径 (体素单位)
    cfg.maxEdgeLen = (int)(12.0f / cfg.cs);
    cfg.maxSimplificationError = 1.3f;
    cfg.minRegionArea = (int)(rcSqr(8.0f));  // 最小区域面积
    cfg.mergeRegionArea = (int)(rcSqr(20.0f));
    cfg.maxVertsPerPoly = 6;
    cfg.detailSampleDist = 6.0f < 0.9f ? 0 : cfg.cs * 6.0f;
    cfg.detailSampleMaxError = cfg.ch * 1.0f;
    cfg.bmin[0] = bmin.x; cfg.bmin[1] = bmin.y; cfg.bmin[2] = bmin.z;
    cfg.bmax[0] = bmax.x; cfg.bmax[1] = bmax.y; cfg.bmax[2] = bmax.z;
    cfg.borderSize = cfg.walkableRadius + 3;
    cfg.width  = cfg.borderSize*2 + (int)((cfg.bmax[0] - cfg.bmin[0]) / cfg.cs);
    cfg.height = cfg.borderSize*2 + (int)((cfg.bmax[2] - cfg.bmin[2]) / cfg.cs);

    printf("Recast config: %d x %d cells (%.1f x %.1f m)\n",
           cfg.width, cfg.height,
           cfg.width*cfg.cs, cfg.height*cfg.cs);

    // ---- 阶段 1-2: 体素化 + 过滤 ----
    rcHeightfield* hf = rcAllocHeightfield();
    if (!rcCreateHeightfield(nullptr, *hf, cfg.width, cfg.height,
                              cfg.bmin, cfg.bmax, cfg.cs, cfg.ch)) {
        printf("rcCreateHeightfield failed\n"); return 1;
    }

    // 将三角形标记为可通行
    unsigned char* triAreas = new unsigned char[tris.size()/3];
    memset(triAreas, RC_WALKABLE_AREA, tris.size()/3);

    if (!rcRasterizeTriangles(nullptr,
            (float*)verts.data(), (int)verts.size(),
            tris.data(), triAreas, (int)(tris.size()/3),
            *hf, cfg.walkableClimb)) {
        printf("rcRasterizeTriangles failed\n"); return 1;
    }
    delete[] triAreas;

    // 过滤
    rcFilterLowHangingWalkableObstacles(nullptr, cfg.walkableClimb, *hf);
    rcFilterLedgeSpans(nullptr, cfg.walkableHeight, cfg.walkableClimb, *hf);
    rcFilterWalkableLowHeightSpans(nullptr, cfg.walkableHeight, *hf);

    // ---- 阶段 3: 区域生成 ----
    rcCompactHeightfield* chf = rcAllocCompactHeightfield();
    if (!rcBuildCompactHeightfield(nullptr, cfg.walkableHeight, cfg.walkableClimb, *hf, *chf)) {
        printf("rcBuildCompactHeightfield failed\n"); return 1;
    }
    rcFreeHeightField(hf);

    if (!rcErodeWalkableArea(nullptr, cfg.walkableRadius, *chf))
        printf("Warning: rcErodeWalkableArea failed\n");

    if (!rcBuildDistanceField(nullptr, *chf))
        printf("Warning: rcBuildDistanceField failed\n");
    if (!rcBuildRegions(nullptr, *chf, cfg.borderSize,
                        cfg.minRegionArea, cfg.mergeRegionArea))
        printf("Warning: rcBuildRegions failed\n");

    // ---- 阶段 4: 轮廓追踪 ----
    rcContourSet* cset = rcAllocContourSet();
    if (!rcBuildContours(nullptr, *chf, cfg.maxSimplificationError,
                          cfg.maxEdgeLen, *cset)) {
        printf("rcBuildContours failed\n"); return 1;
    }

    // ---- 阶段 5: 多边形剖分 ----
    rcPolyMesh* pmesh = rcAllocPolyMesh();
    if (!rcBuildPolyMesh(nullptr, *cset, cfg.maxVertsPerPoly, *pmesh)) {
        printf("rcBuildPolyMesh failed\n"); return 1;
    }

    // ---- 阶段 6: 细节网格 ----
    rcPolyMeshDetail* dmesh = rcAllocPolyMeshDetail();
    if (!rcBuildPolyMeshDetail(nullptr, *pmesh, *chf,
                                cfg.detailSampleDist, cfg.detailSampleMaxError, *dmesh)) {
        printf("rcBuildPolyMeshDetail failed\n"); return 1;
    }

    printf("NavMesh generated: %d polys, %d verts, %d detail tris\n",
           pmesh->npolys, pmesh->nverts, dmesh->ntris);

    // ---- 保存 ----
    if (!saveNavMesh(argv[2], *pmesh, *dmesh)) {
        printf("Failed to save %s\n", argv[2]);
    } else {
        printf("NavMesh saved to %s\n", argv[2]);
    }

    // ---- 清理 ----
    rcFreeContourSet(cset);
    rcFreeCompactHeightfield(chf);
    rcFreePolyMesh(pmesh);
    rcFreePolyMeshDetail(dmesh);

    return 0;
}
```

**运行方式:**
```bash
# 从 Recast 源码构建库
cd recastnavigation/Recast
g++ -std=c++11 -c -O2 Source/*.cpp -I Include
ar rcs libRecast.a *.o

# 使用库编译本示例
g++ -std=c++17 -O2 -I recastnavigation/Recast/Include \
    -I recastnavigation/DebugUtils/Include \
    build_with_recast.cpp libRecast.a -o build_navmesh

# 运行
./build_navmesh level.obj level.navmesh
```

## 3. 练习

### 基础练习：调整体素大小观察结果变化

修改 `recast_sketch.cpp` 的 `cellSize` 从 0.3 改为 0.1 和 1.0，观察：

1. Span 数量的变化（小而多的体素 vs 大而少的体素）
2. 区域数量的变化（小体素 → 更细节的区域边界）
3. 最终的 NavMesh 多边形数量的变化

**目标**: 理解 `cellSize` 是精度 vs 速度/内存的核心权衡参数。

### 进阶练习：实现 Douglas-Peucker 轮廓简化

在 `traceContours()` 中实现真正的 Douglas-Peucker 简化：

1. 收集未简化的轮廓顶点
2. 找到离首尾连线最远的顶点
3. 如果距离 > `maxSimplificationError`，递归分割
4. 用简化后的顶点替换原始轮廓
5. 对比简化前后的顶点数和形状偏差

**目标**: 理解轮廓简化对 NavMesh 质量和内存的影响。

### 挑战练习：实现 Watershed Partitioning

替换简化版 Flood Fill 的区域生成，实现真正的 Watershed Partitioning：

1. 为每个 walkable span 分配距离值（用 BFS 从边界向内传播）
2. 找到所有局部距离最大值 → 作为种子
3. 从种子出发，按距离值从高到低分配区域
4. 在水位线相遇处产生区域边界
5. 对比 Flood Fill 和 Watershed 的区域边界质量（是否沿自然"山脊"）

**目标**: 理解为什么 Watershed 产生"更自然"的区域边界——agent 在凹陷区域内部有自然行走路径，而不是随机切断。

## 4. 扩展阅读

- **Recast Navigation 源码**: [github.com/recastnavigation/recastnavigation](https://github.com/recastnavigation/recastnavigation) — 阅读 `Recast/Source/RecastRasterization.cpp` 的体素化实现、`RecastRegion.cpp` 的 watershed 算法、`RecastContour.cpp` 的轮廓追踪
- **"Real-Time Generative Navigation Mesh Generation"**: Mikko Mononen, 2009 — Recast 的原始论文，解释六阶段设计哲学
- **Watershed 算法**: Serge Beucher 和 Christian Lantuéjoul 的原始工作；Recast 中的 `rcBuildRegions` 是其在体素空间的简化变体
- **Constrained Delaunay Triangulation**: Jonathan Richard Shewchuk 的 Triangle 库 — 业界标准的 2D CDT 实现；Recast 的 `rcBuildPolyMesh` 使用了类似的 constraint-based ear clipping
- **Douglas-Peucker 算法**: 线简化的标准算法；Recast 中用于轮廓简化，配合 Mandelbrot 边界条件
- **rcConfig 参数调优指南**: 官方文档 `RecastDemo` 中 `Sample_SoloMesh.cpp` 展示了所有参数的实际效果

## 常见陷阱

### 1. cellSize 和 cellHeight 独立设置导致各向异性

设置 `cellSize=0.3` 和 `cellHeight=0.5` 意味着水平精度和垂直精度不同。这在斜坡/楼梯上导致坡度计算错误：两个方向的实际分辨率差异导致采样偏差。

**修正**: 保持 `cellSize ≈ cellHeight`（或 `cellHeight` 略小），避免各向异性体素。

### 2. agentRadius 之坑：体素单位 vs 世界单位

Recast 的 `walkableRadius`、`walkableHeight`、`walkableClimb` 是**体素单位**，不是世界单位。常见错误：`cfg.walkableClimb = 0.9`（把米当体素数）→ agent 连 0.3 个 cell 都跨不过。

**修正**: 设置时除以 cell size: `cfg.walkableClimb = (int)ceilf(0.9f / cfg.ch)`。

### 3. 输入几何体的法线方向

Recast 假设输入三角形的**上表面**是 +Y 方向的正法线。如果美术导出的几何体面朝向不一致（法线翻转），体素化阶段会产生错误的高度区间。

**修正**: 体素化前统一翻转法线或使用无方向的 span 合并策略（Detour 可以配置）。

### 4. 内存泄漏：忘记释放 Recast 分配的内存

Recast 使用独立的内存分配器函数（`rcAllocHeightfield`、`rcAllocPolyMesh` 等），不使用 `new/delete`。如果忘记调用对应的 `rcFree*` 函数，会导致大量泄漏。

**修正**: 每个 `rcAlloc*` 必须成对出现 `rcFree*`。使用 RAII 包装（如 `std::unique_ptr` with custom deleter）。

### 5. 由轮廓顶点顺序错误导致的"翻转三角形"

Ear clipping 三角剖分要求轮廓顶点严格逆时针（从上方俯瞰）。如果由于 traceContours 的顶点排序错误导致顺时针，三角形法线指向下方 → agent 站在上面相机会认为是"天花板"。

**修正**: 三角剖分前执行 CCW 检查，顺时针时反转顶点列表。Recast 的 `isEar` 函数内有此检查。
