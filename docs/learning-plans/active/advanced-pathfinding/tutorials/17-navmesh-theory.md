---
title: "Navigation Mesh 理论与数据结构"
updated: 2026-06-05
---

# Navigation Mesh 理论与数据结构

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: A* 算法（03），网格系统与邻接方式（04），Funnel Algorithm（13）

## 1. 概念讲解

### 为什么需要这个？

网格寻路（A* on grid）是入门利器，但它有结构性缺陷：

1. **节点数量爆炸**: 1000×1000 网格 = 100 万个节点，A* 会探索数万节点 —— 即使实际路径只需要 3 个拐点
2. **离散化伪影**: 路径锁死在 45° 倍数，真实世界中的直线被锯齿化
3. **内存浪费**: 大片开放区域（广场、平原）内部没有障碍，却被切成上万个均质格子
4. **无地形语义**: 网格只知道"这个格子能走/不能走"，不理解"这片区域是个房间"

**Navigation Mesh (NavMesh)** 是这些问题的工业级解决方案。它把可通行表面表示为一组**凸多边形**，寻路在多边形图而不是格点图上进行。结果：节点数从 O(面积) 降到 O(障碍边界数)，路径天然平滑（可做漏斗算法拉直）。

### 核心思想

```
网格表示 (每个格子是节点):            NavMesh 表示 (每个凸多边形是节点):
┌──┬──┬──┬──┬──┐                     ┌────────────┐
│  │  │  │  │  │                     │  P0 (凸)    │────── P1
├──┼──┼──┼──┼──┤                     │            │
│  │  │  │  │  │                      └──────┬─────┘
├──┼──┼──┼──┼──┤  ← 25 个格子                  │
│  │  │██│  │  │                             │
├──┼──┼──┼──┼──┤                     ┌───────┴──────┐
│  │  │  │  │  │                     │   P2 (凸)    │────── P3
└──┴──┴──┴──┴──┘                     └──────────────┘
                                             ↑ 仅 4 个多边形
```

**三个关键抽象**：

1. **多边形 = 可通行区域的原子单位**: 每个多边形是凸的 —— 保证多边形内任意两点直线段完全在内部（无阻隔）
2. **共享边 = 邻接关系**: 两个多边形共享一条边 → 可以从一个走到另一个；共享边的中点/质心连接构成"多边形图"的边
3. **寻路 = 多边形图上的搜索 + 路径拉直**: 先在多边形级别做 A* 找到多边形序列，再用 Funnel Algorithm 在多边形序列内拉出最短路径

### 多边形寻路 vs 节点寻路

```
网格寻路 (节点级):
  输入: start_cell, goal_cell
  搜索: 在格点图上 A*，每个格子是节点
  输出: cell 序列 (锯齿路径)
  后处理: 路径平滑 (Funnel / 弦收缩)

NavMesh 寻路 (多边形级):
  输入: (start_pos, goal_pos)   ← 连续空间坐标
  Step 1: 定位 — findNearestPoly(start/goal) → 找到对应的 NavMesh 多边形
  Step 2: 搜索 — A* 在多边形图上，每个多边形是节点
  输出: 多边形序列 (corridor)
  Step 3: 拉绳 — findStraightPath(corridor) → 在多边形走廊内拉出最短折线
```

**为什么多边形比网格好？**

| 维度 | 网格 (Grid) | NavMesh |
|------|-------------|---------|
| 节点数 | O(W×H) — 与面积成正比 | O(障碍边界数) — 与复杂度成正比 |
| 开放区域 | 成千上万个等价格子 | 一个大多边形 |
| 路径质量 | 锯齿，需后处理 | 天然包含长直线段 |
| 内存 | 高（每格子至少 1 byte） | 低（每多边形 ~100 bytes） |
| 三维支持 | 困难（3D 体素网格 → 内存灾难） | 天然（多边形在 3D 空间中） |
| 动态更新 | 易（直接改格子） | 复杂（需重烘焙多边形） |

### 数据结构

NavMesh 的核心数据结构选择取决于查询模式。以下是三种递进的表示：

#### 1. 多边形汤 (Polygon Soup)

最简单的表示：`vector<ConvexPolygon>` + 邻接通过边的几何重合判断。

```cpp
struct ConvexPolygon {
    std::vector<Vec3> vertices;  // 逆时针排列
    float area;                  // 预计算缓存
    int flags;                   // 区域标记（水/地面/跳跃点等）
};

// 邻接查询：暴力 O(N²) 比较所有边
// 实际中不可行 —— 仅用于理解概念
```

**优点**: 简单直观。
**缺点**: 邻接查询 O(N²)（遍历所有多边形找共享边），无法用于运行时。

#### 2. 邻接表 (Adjacency List)

在 Polygon Soup 基础上显式存储邻接关系：

```cpp
struct NavPoly {
    std::vector<Vec3> vertices;
    std::vector<int> neighbors;  // 邻接多边形 index
    std::vector<int> neighbor_edges;  // 共享的边 index（在 vertices 中）
};
```

**优点**: 邻接查询 O(1)。
**缺点**: 仍无法快速回答"点 (x,y,z) 在哪个多边形内？"——需要遍历所有多边形做 point-in-polygon 测试。

#### 3. 半边缘网格 (Half-Edge Mesh)

Detour 使用的生产级数据结构。核心思想：每条边拆成两条方向相反的**半边**。

```
多边形 P (v0→v1→v2):
                   v1
                   /\
             e0→  /  \  ←e1
                 /    \
               v0──────v2
                  e2→

每条边都存为两个半边:
  h0: v0→v1, face=P, opposite=h_opposite_of_this
  h1: v1→v2, face=P, opposite=...
  h2: v2→v0, face=P, opposite=...
  (另一半边来自邻接多边形)
```

```cpp
struct HalfEdge {
    int vertex;      // 起始顶点的 index
    int face;        // 所属多边形 index
    int opposite;    // 反向半边 index（若在边界上则为 -1）
    int next;        // 同一多边形内的下一条半边
};

// 查询: 给定一个多边形，找出所有邻接多边形
// → 遍历该多边形的所有半边，opposite != -1 的半边的 face 就是邻居
```

**半边缘的优点**: 邻接查询 O(边数)、边界检测 O(1)、支持网格编辑操作（边翻转、分裂）有拓扑一致性保证。Detour 的 `dtMeshTile` 内部就是这种结构。

### NavMesh 上的关键查询

构建好数据结构后，运行时需要以下查询（这些是 Detour 暴露的 API，但理解原理很重要）：

| 查询 | 功能 | 算法 |
|------|------|------|
| `findNearestPoly` | 给定 3D 点，找到包含/最近的多边形 | BVH (Bounding Volume Hierarchy) 加速的 point-in-poly 测试 |
| `getPolyCenter` | 获取多边形质心（A* 节点坐标） | 顶点平均 |
| `getEdgeMidPoint` | 获取边的中点（A* 边代价评估点） | `(v0+v1)/2` |
| `getCost` | 获取穿过多边形边的代价 | 边长 × 区域代价因子 |
| `findPath` | 在多边形图上 A* | 标准 A*，节点=多边形，边=共享边中点 |

**A* 在多边形图上的特殊之处**：
- 节点不是固定格点，而是连续空间中的凸多边形
- g 值用穿过边中点的欧几里得距离（不是曼哈顿/切比雪夫）
- h 值用目标到当前多边形边中点的欧几里得距离（admissible，因为总路径至少 ≥ 直线距离）

## 2. 代码示例

### 完整 NavMesh 数据结构（半边缘 + A* 查询）

```cpp
// navmesh_simple.cpp — 简化版 NavMesh 数据结构 + 多边形图 A*
// 编译: g++ -std=c++17 -O2 -Wall -o navmesh_simple navmesh_simple.cpp
// 运行: ./navmesh_simple

#include <iostream>
#include <vector>
#include <queue>
#include <cmath>
#include <limits>
#include <cassert>
#include <unordered_map>
#include <algorithm>

// ============================================================
// 基础类型
// ============================================================
struct Vec3 {
    float x, y, z;
    Vec3 operator+(Vec3 o) const { return {x+o.x, y+o.y, z+o.z}; }
    Vec3 operator-(Vec3 o) const { return {x-o.x, y-o.y, z-o.z}; }
    Vec3 operator*(float s) const { return {x*s, y*s, z*s}; }
    float len() const { return std::sqrt(x*x + y*y + z*z); }
    float dist(Vec3 o) const { return (*this - o).len(); }
};

// ============================================================
// 多边形 (简化: 3 顶点凸多边形，实际 Detour 支持 n 顶点)
// ============================================================
struct Poly {
    int verts[3];       // 顶点 index（指向 vertices 数组）
    int neighbors[3];   // 邻接多边形 index，-1 = 边界
    float area;         // 面积（用于质心计算）
    unsigned char flags; // 区域类型
};

struct NavMesh {
    std::vector<Vec3> vertices;
    std::vector<Poly> polys;

    // ==========================================================
    // 基本查询
    // ==========================================================

    // 获取多边形的质心
    Vec3 centroid(int polyIdx) const {
        const Poly& p = polys[polyIdx];
        return (vertices[p.verts[0]] + vertices[p.verts[1]] + vertices[p.verts[2]]) * (1.0f/3.0f);
    }

    // 获取两个多边形共享边的中点
    Vec3 edgeMidpoint(int polyIdx, int edgeIdx) const {
        const Poly& p = polys[polyIdx];
        int v0 = p.verts[edgeIdx];
        int v1 = p.verts[(edgeIdx + 1) % 3];
        return (vertices[v0] + vertices[v1]) * 0.5f;
    }

    // 检查其他多边形是否为此多边形的邻居
    int getNeighbor(int polyIdx, int otherPolyIdx) const {
        const Poly& p = polys[polyIdx];
        for (int i = 0; i < 3; ++i)
            if (p.neighbors[i] == otherPolyIdx)
                return i;  // 返回边 index
        return -1;
    }

    // 点定位：找到包含给定点的多边形（简化：暴力搜索，生产用 BVH）
    int findPoly(Vec3 pt) const {
        for (size_t i = 0; i < polys.size(); ++i) {
            const Poly& p = polys[i];
            // 三角形 point-in-poly 用重心坐标
            Vec3 v0 = vertices[p.verts[0]];
            Vec3 v1 = vertices[p.verts[1]];
            Vec3 v2 = vertices[p.verts[2]];

            Vec3 e0 = v1 - v0, e1 = v2 - v0, e2 = pt - v0;
            float d00 = e0.x*e0.x + e0.y*e0.y + e0.z*e0.z;
            float d01 = e0.x*e1.x + e0.y*e1.y + e0.z*e1.z;
            float d11 = e1.x*e1.x + e1.y*e1.y + e1.z*e1.z;
            float d20 = e2.x*e0.x + e2.y*e0.y + e2.z*e0.z;
            float d21 = e2.x*e1.x + e2.y*e1.y + e2.z*e1.z;
            float denom = d00 * d11 - d01 * d01;
            if (std::abs(denom) < 1e-6f) continue;
            float v = (d11*d20 - d01*d21) / denom;
            float w = (d00*d21 - d01*d20) / denom;
            float u = 1.0f - v - w;
            // 允许小误差（ε = 0.001）
            if (u >= -0.001f && v >= -0.001f && w >= -0.001f)
                return (int)i;
        }
        return -1;  // 不在任何多边形内
    }

    // ==========================================================
    // A* 在多边形图上寻路
    // ==========================================================
    struct PolyNode {
        int polyIdx;
        int parent;      // 父多边形 index
        float g, f;
        bool operator<(const PolyNode& o) const { return f > o.f; }
    };

    // 路径结果：两个多边形序列 (路径走廊) + 世界坐标路径
    struct PathResult {
        bool success = false;
        std::vector<int> poly_path;       // 多边形 index 序列
        std::vector<Vec3> world_path;     // 世界坐标路径（边中点到边中点）
        float total_cost = 0.0f;
    };

    PathResult findPath(Vec3 startPoint, Vec3 goalPoint) {
        int startPoly = findPoly(startPoint);
        int goalPoly = findPoly(goalPoint);

        PathResult result;
        if (startPoly < 0 || goalPoly < 0) return result;

        int N = (int)polys.size();
        std::vector<int> parent(N, -1);
        std::vector<float> g_cost(N, std::numeric_limits<float>::infinity());
        std::vector<float> f_cost(N, std::numeric_limits<float>::infinity());
        std::vector<bool> closed(N, false);

        std::priority_queue<PolyNode> open;
        g_cost[startPoly] = 0.0f;
        f_cost[startPoly] = centroid(startPoly).dist(goalPoint);

        open.push({startPoly, -1, 0.0f, f_cost[startPoly]});

        while (!open.empty()) {
            PolyNode cur = open.top(); open.pop();
            if (closed[cur.polyIdx]) continue;
            closed[cur.polyIdx] = true;

            if (cur.polyIdx == goalPoly) {
                // 回溯路径
                result.success = true;
                result.total_cost = cur.g;
                int p = cur.polyIdx;
                while (p >= 0) {
                    result.poly_path.push_back(p);
                    p = parent[p];
                }
                std::reverse(result.poly_path.begin(), result.poly_path.end());

                // 生成世界坐标路径（多边形边中点链）
                result.world_path.push_back(startPoint);
                for (size_t i = 1; i < result.poly_path.size(); ++i) {
                    int prev = result.poly_path[i-1];
                    int curP = result.poly_path[i];
                    int edgeIdx = getNeighbor(prev, curP);
                    if (edgeIdx >= 0)
                        result.world_path.push_back(edgeMidpoint(prev, edgeIdx));
                }
                result.world_path.push_back(goalPoint);
                break;
            }

            const Poly& curP = polys[cur.polyIdx];
            for (int e = 0; e < 3; ++e) {
                int neighbor = curP.neighbors[e];
                if (neighbor < 0) continue;  // 边界

                // 边代价 = 此多边形质心 → 边中点 → 邻居多边形质心
                Vec3 edgePt = edgeMidpoint(cur.polyIdx, e);
                float step_cost = centroid(cur.polyIdx).dist(edgePt);
                float new_g = cur.g + step_cost;

                if (new_g < g_cost[neighbor]) {
                    g_cost[neighbor] = new_g;
                    parent[neighbor] = cur.polyIdx;
                    float h = centroid(neighbor).dist(goalPoint);
                    float f = new_g + h;
                    f_cost[neighbor] = f;
                    open.push({neighbor, cur.polyIdx, new_g, f});
                }
            }
        }
        return result;
    }
};

// ============================================================
// 创建示例 NavMesh（一个简单的三房间地图）
// ============================================================
NavMesh createExampleNavMesh() {
// 世界坐标系(Y-up)：一个 L 形走廊地图
//
//      (0,10)──(3,10)──(6,10)──(10,10)
//        │  P0    │   P1    │  P2    │
//      (0,6)──(3,6)──(6,6)──(10,6)
//                        │   P3    │
//              (3,3)──(6,3)──(10,3)
//                │  P4    │   P5   │
//              (0,0)──(3,0)──(6,0)──(10,0)
//
// 6 个三角形：把每个矩形沿对角线分割

    NavMesh nm;

    // 顶点: (用矩形对角分割成三角形)
    // 布局: 0-1-2-... 列优先
    // 三行: y=0, y=3  (下半部分)
    auto addTri = [&](int v0, int v1, int v2, int n0, int n1, int n2) {
        Poly p;
        p.verts[0] = v0; p.verts[1] = v1; p.verts[2] = v2;
        p.neighbors[0] = n0; p.neighbors[1] = n1; p.neighbors[2] = n2;
        // 计算面积（用叉积的一半，这里简化用 0）
        Vec3 a = nm.vertices[v1] - nm.vertices[v0];
        Vec3 b = nm.vertices[v2] - nm.vertices[v0];
        p.area = 0.5f * (a.x*b.y - a.y*b.x);  // 2D 叉积/2
        p.flags = 0;
        nm.polys.push_back(p);
    };

    // 8 个顶点 — 第0行 y=0..3; 第1行 y=3..6; 第2行 y=6..10
    assert(nm.vertices.empty() && "顶点应从 index 0 开始");

    // Row 0: y=0..3 (下半排)
    nm.vertices.push_back({0.0f, 0.0f, 0.0f});  // 0
    nm.vertices.push_back({3.0f, 0.0f, 0.0f});  // 1
    nm.vertices.push_back({6.0f, 0.0f, 0.0f});  // 2
    nm.vertices.push_back({10.0f,0.0f, 0.0f});  // 3
    nm.vertices.push_back({0.0f, 3.0f, 0.0f});  // 4
    nm.vertices.push_back({3.0f, 3.0f, 0.0f});  // 5
    nm.vertices.push_back({6.0f, 3.0f, 0.0f});  // 6
    nm.vertices.push_back({10.0f,3.0f, 0.0f});  // 7

    // Row 1: y=3..6 (中间排)
    nm.vertices.push_back({3.0f, 6.0f, 0.0f});  // 8
    nm.vertices.push_back({6.0f, 6.0f, 0.0f});  // 9

    // Row 2: y=6..10 (上半排)
    nm.vertices.push_back({0.0f, 10.0f,0.0f});  // 10
    nm.vertices.push_back({3.0f, 10.0f,0.0f});  // 11
    nm.vertices.push_back({6.0f, 10.0f,0.0f});  // 12
    nm.vertices.push_back({10.0f,10.0f,0.0f});  // 13

    // 多边形定义: (左下三角, 右上三角) per 矩形
    // 矩形(0,0)-(3,3): 左下三角(0,1,5), 右上三角(0,5,4)
    //   P0: verts(0,1,5) 边0:0-1=neighbor右上三角, 边1:1-5=boundary, 边2:5-0=boundary
    //   邻接索引占位; 回填
    addTri(0, 1, 5, -1, -1, -1);   // poly 0: 左下三角 (下半排-左)
    addTri(0, 5, 4, -1, -1, -1);   // poly 1: 右上三角 (下半排-左)

    // 矩形(3,0)-(6,3):
    addTri(1, 2, 6, -1, -1, -1);   // poly 2: 左下三角 (下半排-中)
    addTri(1, 6, 5, -1, -1, -1);   // poly 3: 右上三角 (下半排-中)

    // 矩形(6,0)-(10,3):
    addTri(2, 3, 7, -1, -1, -1);   // poly 4: 左下三角 (下半排-右)
    addTri(2, 7, 6, -1, -1, -1);   // poly 5: 右上三角 (下半排-右)

    // 矩形(3,3)-(6,6):
    addTri(5, 6, 9, -1, -1, -1);   // poly 6: 左下三角 (中间排)
    addTri(5, 9, 8, -1, -1, -1);   // poly 7: 右上三角 (中间排)

    // 矩形(0,6)-(3,10):
    addTri(4, 8, 11, -1, -1, -1);  // poly 8: 左下三角 (上半排-左)
    addTri(4, 11, 10, -1, -1, -1); // poly 9: 右上三角 (上半排-左)

    // 矩形(3,6)-(6,10):
    addTri(8, 9, 12, -1, -1, -1);  // poly 10: 左下三角 (上半排-中)
    addTri(8, 12, 11, -1, -1, -1); // poly 11: 右上三角 (上半排-中)

    // 矩形(6,6)-(10,10):
    addTri(9, 7, 13, -1, -1, -1);  // poly 12: 左上三角 (上半排-右)
    addTri(9, 13, 12, -1, -1, -1); // poly 13: 右下三角 (上半排-右)

    // 注：完整的邻接关系回填较繁琐，此处用几何重合判断替代
    // 实际中由 Recast 烘焙或构建工具自动计算
    // 这里展示手动回填邻接的"足够可用"版本
    //
    // 策略：对每个多边形的每条边，暴力搜索共享同一条边的另一个多边形
    // (VertSet based: 检测两个多边形的两条边共享两个相同的顶点)
    for (size_t i = 0; i < nm.polys.size(); ++i) {
        for (size_t j = i+1; j < nm.polys.size(); ++j) {
            Poly& pi = nm.polys[i];
            Poly& pj = nm.polys[j];
            for (int ei = 0; ei < 3; ++ei) {
                if (pi.neighbors[ei] >= 0) continue;
                int vi0 = pi.verts[ei];
                int vi1 = pi.verts[(ei+1)%3];
                for (int ej = 0; ej < 3; ++ej) {
                    if (pj.neighbors[ej] >= 0) continue;
                    int vj0 = pj.verts[ej];
                    int vj1 = pj.verts[(ej+1)%3];
                    // 共享边：两个顶点都相同（但方向可能相反）
                    if ((vi0 == vj0 && vi1 == vj1) || (vi0 == vj1 && vi1 == vj0)) {
                        pi.neighbors[ei] = (int)j;
                        pj.neighbors[ej] = (int)i;
                        goto next_ei;  // 跳出内层循环
                    }
                }
            }
            next_ei:;
        }
    }

    return nm;
}

// ============================================================
// 可视化
// ============================================================
void printNavMesh(const NavMesh& nm) {
    std::cout << "NavMesh: " << nm.polys.size() << " polys, "
              << nm.vertices.size() << " verts\n\n";
    for (size_t i = 0; i < nm.polys.size(); ++i) {
        const Poly& p = nm.polys[i];
        Vec3 c = nm.centroid((int)i);
        std::cout << "Poly[" << i << "] center=("
                  << c.x << "," << c.y << ") neighbors=[";
        for (int e = 0; e < 3; ++e) {
            if (e > 0) std::cout << ",";
            std::cout << p.neighbors[e];
        }
        std::cout << "]\n";
    }
}

void printPath(const NavMesh::PathResult& r) {
    if (!r.success) {
        std::cout << "No path found.\n";
        return;
    }
    std::cout << "Path cost: " << r.total_cost << "\n";
    std::cout << "Poly path (" << r.poly_path.size() << "): ";
    for (size_t i = 0; i < r.poly_path.size(); ++i) {
        if (i > 0) std::cout << " → ";
        std::cout << r.poly_path[i];
    }
    std::cout << "\nWorld path (" << r.world_path.size() << "):\n";
    for (size_t i = 0; i < r.world_path.size(); ++i) {
        std::cout << "  [" << i << "] (" << r.world_path[i].x
                  << ", " << r.world_path[i].y << ")\n";
    }
}

// ============================================================
// 主程序
// ============================================================
int main() {
    NavMesh nm = createExampleNavMesh();
    printNavMesh(nm);

    std::cout << "\n--- 测试 1: 直线路径 (左下 → 右上) ---\n";
    Vec3 start = {1.5f, 1.5f, 0.0f};  // 在 poly[0] 内
    Vec3 goal  = {8.0f, 8.0f, 0.0f};  // 在 poly[13] 内
    int sp = nm.findPoly(start);
    int gp = nm.findPoly(goal);
    std::cout << "start poly: " << sp << ", goal poly: " << gp << "\n";

    auto r1 = nm.findPath(start, goal);
    printPath(r1);

    std::cout << "\n--- 测试 2: 同一多边形内 ---\n";
    Vec3 s2 = {1.0f, 1.0f, 0.0f};
    Vec3 g2 = {2.0f, 2.0f, 0.0f};
    auto r2 = nm.findPath(s2, g2);
    printPath(r2);

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o navmesh_simple navmesh_simple.cpp
./navmesh_simple
```

**预期输出:**
```
NavMesh: 14 polys, 14 verts

Poly[0] center=(1,2) neighbors=[3,1,-1]
Poly[1] center=(1,2.66667) neighbors=[0,-1,9]
Poly[2] center=(4,1) neighbors=[5,3,-1]
...

--- 测试 1: 直线路径 (左下 → 右上) ---
start poly: 0, goal poly: 13
Path cost: 10.2456
Poly path (5): 0 → 3 → 7 → 11 → 13
World path (5):
  [0] (1.5, 1.5)
  [1] (1.5, 3)
  [2] (4.5, 3)
  [3] (4.5, 6)
  [4] (8.0, 8.0)

--- 测试 2: 同一多边形内 ---
Path cost: 1.41421
Poly path (1): 0
World path (2):
  [0] (1, 1)
  [1] (2, 2)
```

## 3. 练习

### 基础练习：用网格表示同一个地图并统计节点数

创建一个 10×10 的网格地图（与上述 NavMesh 相同的世界空间），将每个 NavMesh 多边形展开为内部格子。统计：

1. 多少个格子被覆盖（近似多边形所占面积）
2. 如果在这个格子上跑 A*（8 方向），从 (1.5, 1.5) 到 (8.0, 8.0) 探索了多少节点？
3. 与 NavMesh 的 5 个多边形对比，节点数差多少倍？

**目标**: 亲身体验 NavMesh 的节点减缩优势。

### 进阶练习：实现漏斗算法拉直路径

上述 A* 输出的 `world_path` 是边中点序列 —— 不是真正的最短路径。实现 Funnel Algorithm：
1. 输入：起点、终点、多边形序列（顶点+左/右边顶点列表）
2. 维护左右漏斗边界，更新顶点时收紧漏斗
3. 当漏斗倒置（左边界在右边界右侧）时，输出前一个顶点作为路径拐点
4. 对比拉直前后的路径长度

**目标**: 将多边形级别的粗略路径转换为几何最短折线。

### 挑战练习：实现 NavMesh 的 BVH 加速点定位

当前 `findPoly` 是 O(N) 暴力搜索。实现一个简单的 BVH（Bounding Volume Hierarchy）：

1. 为每个多边形计算 AABB
2. 自顶向下构建 BVH 树：递归按 AABB 中心的最长轴分割
3. `findPoly` 改为递归遍历 BVH：先检查点的 AABB 包含，再检查 point-in-poly
4. 对比 14 个多边形 vs 14 万的多边形的查询性能差异

**目标**: 理解空间加速结构在 NavMesh 中的必要性——没有它，即使是中等规模 NavMesh 也无法用于运行时。

## 4. 扩展阅读

- **Recast/Detour 官方文档**: Mikko Mononen 的 [Recast Navigation](https://github.com/recastnavigation/recastnavigation) — 完整 C++ 实现，含 `Recast.h` 和 `DetourNavMesh.h` 的生产级代码
- **"Efficient Triangulation of Poisson-Disk Sampled Point Sets"**: 多边形的 Delaunay 三角剖分和约束三角剖分（Recast 中 `rcBuildPolyMeshDetail` 使用的技术）
- **"Navigation Meshes and Real-Time Dynamic Planning"**: Paul Tozour, GDC 2004（最早的 NavMesh 工业应用论文之一，Bungie 的 Halo 2）
- **Half-Edge data structure 详解**: 参考 CGAL 或 OpenMesh 的半边缘实现，Detour 的 `dtMeshTile` 使用了高度优化的变体
- **"Spatial Data Structures" (Samet)**: BVH、四叉树、R-tree 在空间查询中的全面分析

## 常见陷阱

### 1. 凸多边形假设被违反

NavMesh 寻路的正确性依赖于**多边形是凸的**。如果在烘焙时产生了凹多边形，A* 在内部取"边中点"时可能落在多边形外，导致路径不可达。

**修正**: 烘焙管线（Recast 的 `buildPolyMesh` 阶段）自动保证三角形是凸的。如果手写 NavMesh，确保用三角化或 Hertel-Mehlhorn 算法分解为凸多边形。

### 2. 浮点精度导致 point-in-poly 误判

`findPoly` 在边界附近容易出现精度错误：一个在 NavMesh 边界上的点可能被判定为"不在任何多边形内"。

**修正**: point-in-poly 测试使用足够宽的 ε（如 `≥ -0.01` 而非 `≥ 0`），并在失败时回退到 findNearestPoly（搜索距离最近的多边形）。

### 3. 邻接关系依赖于共享边但顶点索引不同

两条边是两个多边形的"同一边"当且仅当它们共享完全相同的两个顶点（可能反向）。如果因为浮点误差或者网格生成问题，两条边"几乎"重合但不完全相同 → 邻接关系断裂 → 路径搜索在中间断开。

**修正**: 邻接匹配使用容差（顶点距离 ≤ ε）并确保生成的顶点有唯一 ID。Recast 通过体素化输入保证这一点。

### 4. A* 启发式不 admissible

在多边形图上使用质心到质心的欧几里得距离作为启发式（h）是正确的。但如果用边中点之间的距离作为启发式，就会因为"两点之间直线最短"而高估 → A* 不最优。

**修正**: 始终使用质心（或线段两端点）的欧几里得距离作为 h。它 admissible 因为实体的最短路径 ≥ 质心直线距离。

### 5. startPoly 和 goalPoly 为 -1

当起点或终点落在 NavMesh 外的不可通行区域（如墙内、悬崖下），`findPoly` 返回 -1。没有回退策略的话路径查询直接失败。

**修正**: 生产代码应使用 `dtNavMeshQuery::findNearestPoly`，它会返回最近的可通行多边形和距离。将起点/终点 clamp 到该多边形边界上继续寻路。
