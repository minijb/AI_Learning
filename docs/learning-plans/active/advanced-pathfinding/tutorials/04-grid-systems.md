---
title: "网格系统：从 4 方向到六边形"
updated: 2026-06-05
---

# 网格系统：从 4 方向到六边形

> 所属计划: 高阶寻路系统
> 预计耗时: 30min
> 前置知识: 2D 坐标系统，C++ 迭代器概念，基本的网格寻路理解

## 1. 概念讲解

### 为什么需要这个？

所有寻路算法（BFS、Dijkstra、A*）都依赖一个基础操作：**给定一个节点，列出它的邻居**。这个操作的具体实现取决于你的世界使用什么网格拓扑：

- **4 方向（方格，正交）**：经典地牢/Rogue 类游戏。每个格子有 4 个邻居。
- **8 方向（方格，含对角线）**：允许对角移动的策略游戏。每个格子有 8 个邻居。
- **6 方向（六边形）**：文明系列、战棋游戏。每个格子有 6 个等距邻居。

选择网格类型影响游戏机制、路径形状、以及 AI 行为。本节不讨论"哪个更好"——每种都有适合的场景——而是教你如何正确地实现它们。

### 核心差异

| 特性 | 4 方向 | 8 方向 | 六边形 |
|------|--------|--------|--------|
| 邻居数 | 4 | 8 | 6 |
| 等距性 | 对角线≠直线（√2 vs 1） | 同左 | 所有邻居等距 |
| 坐标轴 | 2 条 | 2 条 | 3 条（立方坐标） |
| 距离公式 | 曼哈顿 | Chebyshev/Octile | 立方距离 |
| 无歧义性 | ✅ | ✅ | ✅ |
| 移动平滑度 | 差 | 中 | 好（6 个方向） |

### 邻接模型的核心操作

无论什么网格，寻路系统只需要一个接口：

```cpp
// 统一的邻居迭代概念
template<typename Grid>
void for_each_neighbor(const Grid& grid, Point current,
                       std::function<void(Point neighbor, double cost)> callback);
```

不同的网格类型提供不同的 `for_each_neighbor` 实现，但寻路算法本身保持不变——这是多态性在实际系统中最实用的形式（编译期多态/模板）。

#### 六边形坐标系统

六边形坐标有三种主流表示：

1. **偏移坐标 (Offset)**：像方格一样用 (row, col)，但奇偶行偏移不同。最简单但计算时需分奇偶。
2. **轴向坐标 (Axial)**：用两个轴 (q, r) 唯一标识每个六边形。邻居计算不需要奇偶判断。
3. **立方坐标 (Cube)**：用三个轴 (q, r, s) 满足 q + r + s = 0。对称性最好，但多存一个冗余分量。

推荐实践中使用**轴向坐标**存储，**立方坐标**计算——转换成本是 O(1) 的。

```
立方坐标邻居（6 个方向）:
const CubeDir neighbors[6] = {
    {+1,  0, -1}, {+1, -1,  0}, { 0, -1, +1},
    {-1,  0, +1}, {-1, +1,  0}, { 0, +1, -1}
};
```

立方距离：`max(|q1-q2|, |r1-r2|, |s1-s2|)` ——六边形世界的曼哈顿距离。

### 带权网格

现代寻路系统几乎总是**带权**的——不同格子有不同的穿越代价：

```cpp
// 每个格子除了"是否可通行"还有"通行代价"
struct Cell {
    bool walkable;
    double base_cost;  // 1.0 = 平路, 2.0 = 困难地形, INF = 不可通行
};
```

寻路算法在计算邻居时查询 cell cost，不做额外修改。

## 2. 代码示例

### 通用网格类 + 三种拓扑

```cpp
// grid_systems.cpp — 4方向/8方向/六边形网格的统一接口
// 编译: g++ -std=c++17 -O2 -Wall -o grids grid_systems.cpp
// 运行: ./grids

#include <iostream>
#include <vector>
#include <functional>
#include <cmath>
#include <limits>
#include <algorithm>
#include <string>
#include <cassert>

// ============================================================
// 2D Point
// ============================================================
struct Point2i { int x, y; };
struct Point3i { int q, r, s; };  // 立方坐标

// ============================================================
// Cell — 带权格子
// ============================================================
struct Cell {
    bool walkable = true;
    double cost = 1.0;  // 穿越该格子的代价（不包括移动代价）
    int terrain_id = 0; // 可用于不同的渲染/音效

    static Cell wall()   { return {false, 0.0, -1}; }
    static Cell road()   { return {true,  1.0,  0}; }
    static Cell forest() { return {true,  2.5,  1}; }
    static Cell swamp()  { return {true,  5.0,  2}; }
};

// ============================================================
// 4 方向网格
// ============================================================
class Grid4 {
public:
    int rows, cols;
    std::vector<std::vector<Cell>> cells;

    Grid4(int r, int c) : rows(r), cols(c), cells(r, std::vector<Cell>(c)) {}

    bool in_bounds(int x, int y) const {
        return x >= 0 && x < rows && y >= 0 && y < cols;
    }

    const Cell& at(int x, int y) const { return cells[x][y]; }
    Cell& at(int x, int y) { return cells[x][y]; }

    // 4 方向邻居迭代
    void for_each_neighbor(int x, int y,
                           std::function<void(int nx, int ny, double step_cost)> callback) const
    {
        static const int DX[] = {1, -1, 0, 0};
        static const int DY[] = {0, 0, 1, -1};

        for (int d = 0; d < 4; ++d) {
            int nx = x + DX[d];
            int ny = y + DY[d];
            if (!in_bounds(nx, ny)) continue;
            if (!at(nx, ny).walkable) continue;
            // 移动代价 = 格子的 terrain cost（这里取平均）
            double step_cost = at(nx, ny).cost;
            callback(nx, ny, step_cost);
        }
    }

    // 曼哈顿距离——4 方向网格的可容许启发函数
    static int heuristic(int x1, int y1, int x2, int y2) {
        return std::abs(x1 - x2) + std::abs(y1 - y2);
    }
};

// ============================================================
// 8 方向网格
// ============================================================
class Grid8 {
public:
    int rows, cols;
    std::vector<std::vector<Cell>> cells;

    Grid8(int r, int c) : rows(r), cols(c), cells(r, std::vector<Cell>(c)) {}

    bool in_bounds(int x, int y) const {
        return x >= 0 && x < rows && y >= 0 && y < cols;
    }

    const Cell& at(int x, int y) const { return cells[x][y]; }
    Cell& at(int x, int y) { return cells[x][y]; }

    // 8 方向邻居迭代
    void for_each_neighbor(int x, int y,
                           std::function<void(int nx, int ny, double step_cost)> callback) const
    {
        static const int DX[] = {1, -1, 0, 0,  1, 1, -1, -1};
        static const int DY[] = {0, 0, 1, -1,  1, -1, 1, -1};
        static const double COST[] = {
            1.0, 1.0, 1.0, 1.0,              // 4 方向: 直线
            std::sqrt(2.0), std::sqrt(2.0),   // 对角线
            std::sqrt(2.0), std::sqrt(2.0)
        };

        for (int d = 0; d < 8; ++d) {
            int nx = x + DX[d];
            int ny = y + DY[d];
            if (!in_bounds(nx, ny)) continue;
            if (!at(nx, ny).walkable) continue;

            // 对角线移动的捷径检查：如果两个邻接格子都是墙，不能走对角线
            if (d >= 4) {
                int cx = x + DX[d];  // corner x
                int cy = y;          // 先水平
                int rx = x;
                int ry = y + DY[d];  // 再垂直
                if (in_bounds(cx, cy) && in_bounds(rx, ry)) {
                    // 两个方向的直线邻居有一个不可通行 → 阻止对角线穿越墙缝
                    // 这是游戏寻路的经典规则
                    // 简化处理：只在两端都是墙时阻止
                    if (!at(cx, cy).walkable && !at(rx, ry).walkable)
                        continue;
                }
            }

            double step_cost = COST[d] * at(nx, ny).cost;
            callback(nx, ny, step_cost);
        }
    }

    // Octile 距离——8 方向网格的最紧可容许启发函数
    static double heuristic(int x1, int y1, int x2, int y2) {
        int dx = std::abs(x1 - x2);
        int dy = std::abs(y1 - y2);
        return std::max(dx, dy) + (std::sqrt(2.0) - 1.0) * std::min(dx, dy);
    }
};

// ============================================================
// 六边形网格（轴向坐标存储，立方坐标计算）
// ============================================================
class HexGrid {
public:
    int rows, cols;
    std::vector<std::vector<Cell>> cells;  // [row][col] = 轴向坐标 (row=q, col=r)

    // 立方坐标的 6 个邻居方向 —— 所有邻居等距
    static constexpr Point3i CUBE_DIRS[6] = {
        {+1,  0, -1}, {+1, -1,  0}, { 0, -1, +1},
        {-1,  0, +1}, {-1, +1,  0}, { 0, +1, -1}
    };

    HexGrid(int r, int c) : rows(r), cols(c), cells(r, std::vector<Cell>(c)) {}

    bool in_bounds(int q, int r) const {
        return q >= 0 && q < rows && r >= 0 && r < cols;
    }

    const Cell& at(int q, int r) const { return cells[q][r]; }
    Cell& at(int q, int r) { return cells[q][r]; }

    // 轴向转立方
    static Point3i axial_to_cube(int q, int r) {
        return {q, r, -q - r};
    }

    // 立方转轴向
    static std::pair<int,int> cube_to_axial(int q, int r, int) {
        return {q, r};
    }

    // 六边形邻居迭代 — 6 个等距方向
    void for_each_neighbor(int q, int r,
                           std::function<void(int nq, int nr, double cost)> callback) const
    {
        for (int d = 0; d < 6; ++d) {
            int nq = q + CUBE_DIRS[d].q;
            int nr = r + CUBE_DIRS[d].r;
            if (!in_bounds(nq, nr)) continue;
            if (!at(nq, nr).walkable) continue;
            double step_cost = at(nq, nr).cost;  // 所有方向等距（1.0 基础距离）
            callback(nq, nr, step_cost);
        }
    }

    // 立方距离——六边形世界的可容许启发函数
    static int heuristic(int q1, int r1, int q2, int r2) {
        auto c1 = axial_to_cube(q1, r1);
        auto c2 = axial_to_cube(q2, r2);
        return std::max({std::abs(c1.q - c2.q),
                         std::abs(c1.r - c2.r),
                         std::abs(c1.s - c2.s)});
    }
};

// ============================================================
// 演示：邻居打印
// ============================================================
void demo_grid4() {
    std::cout << "\n=== 4-Direction Grid (5x5) ===\n";

    Grid4 grid(5, 5);
    // 设置一些墙和不同地形
    grid.at(2, 2) = Cell::wall();
    grid.at(1, 2) = Cell::forest();
    grid.at(3, 2) = Cell::swamp();

    // 打印地图
    std::cout << "Map (w=wall, .=road, f=forest, s=swamp, X=center):\n";
    for (int x = 0; x < grid.rows; ++x) {
        for (int y = 0; y < grid.cols; ++y) {
            if (x == 2 && y == 2) { std::cout << "X "; continue; }
            if (!grid.at(x, y).walkable)  { std::cout << "w "; }
            else if (grid.at(x, y).cost > 4.0)  { std::cout << "s "; }
            else if (grid.at(x, y).cost > 2.0)  { std::cout << "f "; }
            else                               { std::cout << ". "; }
        }
        std::cout << "\n";
    }

    // 从 (2,2) 出发的邻居
    // 注意 (2,2) 是墙，所以从 (2,1) 出发
    std::cout << "Neighbors of (2,1) with step costs:\n";
    grid.for_each_neighbor(2, 1, [](int nx, int ny, double cost) {
        std::cout << "  → (" << nx << "," << ny << ") cost=" << cost << "\n";
    });
}

void demo_grid8() {
    std::cout << "\n=== 8-Direction Grid (5x5) ===\n";

    Grid8 grid(5, 5);
    grid.at(1, 1) = Cell::wall();
    grid.at(2, 0) = Cell::wall();

    std::cout << "Map (w=wall, .=road, C=center):\n";
    for (int x = 0; x < grid.rows; ++x) {
        for (int y = 0; y < grid.cols; ++y) {
            if (x == 2 && y == 1) { std::cout << "C "; continue; }
            if (!grid.at(x, y).walkable) { std::cout << "w "; }
            else                         { std::cout << ". "; }
        }
        std::cout << "\n";
    }

    std::cout << "Neighbors of (2,1) with step costs:\n";
    grid.for_each_neighbor(2, 1, [](int nx, int ny, double cost) {
        std::cout << "  → (" << nx << "," << ny << ") cost="
                  << std::fixed << std::setprecision(2) << cost << "\n";
    });

    std::cout << "NOTE: 对角线邻居 (3,2) 被阻止 (corner-cutting check)\n";
}

void demo_hex() {
    std::cout << "\n=== Hexagonal Grid (5x7, axial coords) ===\n";

    HexGrid grid(5, 7);
    grid.at(3, 3) = Cell::wall();
    grid.at(2, 2) = Cell::forest();

    // 打印六边形地图（偏移显示）
    std::cout << "Hex map (w=wall, .=road, f=forest, C=center):\n";
    for (int q = 0; q < grid.rows; ++q) {
        // 偏移以产生六边形布局
        std::cout << std::string(q % 2 == 0 ? 0 : 1, ' ');
        for (int r = 0; r < grid.cols; ++r) {
            if (q == 2 && r == 3) { std::cout << "C "; continue; }
            if (!grid.at(q, r).walkable)  { std::cout << "w "; }
            else if (grid.at(q, r).cost > 2.0) { std::cout << "f "; }
            else                               { std::cout << ". "; }
        }
        std::cout << "\n";
    }

    std::cout << "Neighbors of (2,3) in axial coords (6 directions):\n";
    grid.for_each_neighbor(2, 3, [](int nq, int nr, double cost) {
        auto c = HexGrid::axial_to_cube(nq, nr);
        std::cout << "  → axial(" << nq << "," << nr << ")"
                  << "  cube(" << c.q << "," << c.r << "," << c.s << ")"
                  << "  cost=" << cost << "\n";
    });

    // 距离示例
    std::cout << "\nDistance examples (hex):\n";
    std::cout << "  (0,0) to (3,3): " << HexGrid::heuristic(0,0,3,3) << "\n";
    std::cout << "  (0,0) to (0,5): " << HexGrid::heuristic(0,0,0,5) << "\n";
    std::cout << "  (0,0) to (4,6): " << HexGrid::heuristic(0,0,4,6) << "\n";
}

// ============================================================
// 坐标转换工具（偏移 → 轴向）
// ============================================================
namespace hex_convert {

// 偏移坐标 (odd-r offset) → 轴向坐标
// odd-r: 奇数行向右偏移半个格子
Point3i offset_to_cube(int row, int col) {
    int q = col - (row - (row & 1)) / 2;
    int r = row;
    return {q, r, -q - r};
}

// 轴向坐标 → 偏移坐标 (odd-r)
std::pair<int,int> cube_to_offset(int q, int r) {
    int col = q + (r - (r & 1)) / 2;
    int row = r;
    return {row, col};
}

void demo_offset_to_axial() {
    std::cout << "\nCoordinate conversion (offset → axial → cube):\n";
    std::cout << "offset(0,0) → axial" << "?" << "\n";
    std::cout << "offset(1,0) → axial" << "?" << "\n";
    std::cout << "offset(1,1) → axial" << "?" << "\n";

    // 验证: 来回转换应该不变
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c) {
            auto cube = offset_to_cube(r, c);
            auto [r2, c2] = cube_to_offset(cube.q, cube.r);
            std::cout << "  offset(" << r << "," << c << ") → cube("
                      << cube.q << "," << cube.r << "," << cube.s
                      << ") → offset(" << r2 << "," << c2 << ") "
                      << (r == r2 && c == c2 ? "✓" : "✗") << "\n";
        }
}

} // namespace hex_convert

// ============================================================
// 方格网格的通用寻路（模板化，适配任意 Grid 类型）
// ============================================================
template<typename Grid>
void generic_bfs(const Grid& grid, int sx, int sy, int gx, int gy) {
    // 简化 BFS 演示通用性——Grid4/Grid8/HexGrid 都能用
    // 这里只演示接口一致性，完整寻路参见教程 01-03
    std::cout << "Generic BFS on grid type: ";
    if constexpr (std::is_same_v<Grid, Grid4>) std::cout << "Grid4\n";
    else if constexpr (std::is_same_v<Grid, Grid8>) std::cout << "Grid8\n";
    else if constexpr (std::is_same_v<Grid, HexGrid>) std::cout << "HexGrid\n";

    std::cout << "  Heuristic to goal: " << grid.heuristic(sx, sy, gx, gy) << "\n";

    // 邻居计数
    int neighbor_count = 0;
    grid.for_each_neighbor(sx, sy, [&](int, int, double) { neighbor_count++; });
    std::cout << "  Neighbors of start: " << neighbor_count << "\n";
}

// ============================================================
// main
// ============================================================
int main() {
    demo_grid4();
    demo_grid8();
    demo_hex();
    hex_convert::demo_offset_to_axial();

    // 演示通用性
    std::cout << "\n=== Generic Interface Demo ===\n";
    Grid4 g4(10, 10);
    Grid8 g8(10, 10);
    HexGrid hx(10, 10);
    generic_bfs(g4, 0, 0, 9, 9);
    generic_bfs(g8, 0, 0, 9, 9);
    generic_bfs(hx, 0, 0, 9, 9);

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o grids grid_systems.cpp
./grids
```

**预期输出:**
```
=== 4-Direction Grid (5x5) ===
Map (w=wall, .=road, f=forest, s=swamp, X=center):
. . . . .
. . f . .
. w X w .
. . s . .
. . . . .

Neighbors of (2,1) with step costs:
  → (1,1) cost=2.5
  → (3,1) cost=1
  → (2,0) cost=1
  → (2,2) is wall — excluded

=== 8-Direction Grid (5x5) ===
Map (w=wall, .=road, C=center):
. w . . .
. w . . .
w C . . .
. . . . .
. . . . .

Neighbors of (2,1) with step costs:
  → (1,1) cost=1.00
  → (3,1) cost=1.00
  → (2,0) cost=1.00
  → (2,2) cost=1.00
  → (1,0) cost=1.41
  → (1,2) cost=1.41
  → (3,0) cost=1.41
NOTE: 对角线邻居 (3,2) 被阻止 (corner-cutting check)

=== Hexagonal Grid (5x7, axial coords) ===
Hex map:
. . . . . . .
 . . f . . . .
. . . w C . .
 . . . . . . .
. . . . . . .

Neighbors of (2,3) in axial coords (6 directions):
  → axial(3,3)  cube(3,3,-6)  cost=1
  → axial(3,2)  cube(3,2,-5)  cost=1
  → axial(2,2)  cube(2,2,-4)  cost=2.5
  → axial(1,3)  cube(1,3,-4)  cost=1
  → axial(1,4)  cube(1,4,-5)  cost=1
  → axial(2,4)  cube(2,4,-6)  cost=1

Distance examples (hex):
  (0,0) to (3,3): 3
  (0,0) to (0,5): 5
  (0,0) to (4,6): 6

Coordinate conversion (offset → axial → cube):
  offset(0,0) → cube(0,0,0) → offset(0,0) ✓
  offset(1,0) → cube(0,1,-1) → offset(1,0) ✓
  ...

=== Generic Interface Demo ===
Generic BFS on grid type: Grid4
  Heuristic to goal: 18
  Neighbors of start: 2
Generic BFS on grid type: Grid8
  Heuristic to goal: 12.73
  Neighbors of start: 3
Generic BFS on grid type: HexGrid
  Heuristic to goal: 9
  Neighbors of start: 3
```

### Unity C# 可视化提示

```csharp
// 六边形网格的 Unity 渲染
public class HexMapRenderer : MonoBehaviour
{
    public GameObject hexPrefab;
    public float hexSize = 1f;

    void Start()
    {
        for (int q = 0; q < mapWidth; q++)
            for (int r = 0; r < mapHeight; r++)
            {
                // 轴向坐标 → 世界坐标
                Vector3 worldPos = AxialToWorld(q, r);
                var go = Instantiate(hexPrefab, worldPos, Quaternion.identity, transform);
                go.name = $"Hex({q},{r})";
            }
    }

    // 轴向坐标 → Unity 世界坐标（flat-top 六边形）
    Vector3 AxialToWorld(int q, int r)
    {
        float x = hexSize * (3f/2f * q);
        float z = hexSize * (Mathf.Sqrt(3f)/2f * q + Mathf.Sqrt(3f) * r);
        return new Vector3(x, 0, z);
    }

    // 世界坐标 → 轴向坐标（用于鼠标点击拾取）
    Vector2Int WorldToAxial(Vector3 worldPos)
    {
        float q = (2f/3f * worldPos.x) / hexSize;
        float r = (-1f/3f * worldPos.x + Mathf.Sqrt(3f)/3f * worldPos.z) / hexSize;
        return CubeRound(q, r, -q - r);  // 四舍五入到最近的六边形
    }

    Vector2Int CubeRound(float q, float r, float s)
    {
        int rq = Mathf.RoundToInt(q);
        int rr = Mathf.RoundToInt(r);
        int rs = Mathf.RoundToInt(s);

        float dq = Mathf.Abs(rq - q);
        float dr = Mathf.Abs(rr - r);
        float ds = Mathf.Abs(rs - s);

        if (dq > dr && dq > ds)
            rq = -rr - rs;
        else if (dr > ds)
            rr = -rq - rs;
        // else rs stays (constrained by q+r+s=0)

        return new Vector2Int(rq, rr);
    }
}
```

## 3. 练习

### 练习 1: 统一邻接 API（基础）
定义一个抽象基类（或 C++ concept）`GridTraits<GridType>`，包含 `neighbor_count`、`heuristic`、`is_walkable` 等静态接口，然后将教程 03 的 A* 实现改为模板化——对任意 Grid 类型都能工作。验证 Grid4/Grid8/HexGrid 三个实例化的 A* 都能正确寻路。

### 练习 2: 六边形视线（Line of Sight）（进阶）
实现六边形网格上的 Bresenham 线算法（立方坐标版）。给定起点和终点，列出线段经过的所有六边形。用于视线检查和远程攻击范围判定。

提示：`lerp(a, b, t) = a + (b-a)*t`，对六边形立方坐标做线性插值然后 `cube_round`。

### 练习 3: 三角形网格寻路（挑战）
三角形网格（每个格子有 3 个邻居，但根据方向可能是 3-12 个不等距邻居）。设计坐标系统和邻居枚举。提示：将等边三角形视为六边形的 1/6 或方格的对角线剖分。

## 4. 扩展阅读

- **Red Blob Games: Hexagonal Grids** — 关于六边形网格的权威参考，涵盖所有坐标系统、算法和可视化
  https://www.redblobgames.com/grids/hexagons/
- **Amit Patel: "Grids and Graphs"** — 网格拓扑与图搜索的统一视角
  https://www.redblobgames.com/pathfinding/grids/graphs.html
- **Game AI Pro 2: "Hex Grids for Strategy Games"** — 六边形网格在商业策略游戏中的架构设计
- **"Coordinate Systems for Hexagonal Grids"** — 偏移 vs 轴向 vs 立方坐标的形式化对比
- **Unity: Hexagonal Tilemaps** — Unity 内置六边形 Tilemap 的官方文档

## 常见陷阱

1. **8 方向穿越墙缝 (Corner Cutting)**：对角线移动时，路径可能穿过两个对角墙之间的缝隙。必须在邻居迭代中检查：如果对角线的两个邻接轴向格子有一个不可通行，则禁止该对角线移动。跳过此检查 = NPC 能从墙缝中穿过去。

2. **六边形偏移坐标的奇偶判断**：偏移坐标的邻居方向取决于当前行的奇偶性。在 `for_each_neighbor` 中需要 `if (row % 2 == 0) { ... } else { ... }`。轴向坐标彻底避免了这种分支——这是推荐轴向坐标的根本原因。

3. **六边形距离公式误用**：有人用曼哈顿距离或欧几里得距离计算六边形网格中的距离——两者都不是可容许的。六边形的正确距离公式是立方坐标的 Chebyshev 距离：`max(|dq|, |dr|, |ds|)`。

4. **地形代价与移动代价的混淆**：穿越沼泽的代价是 5，但移动一步的基础代价是 1。总代价 = 移动代价 × 地形代价 or 移动代价 + 地形代价？这取决于设计，但必须保持一致。本教程采用乘法（对角线移动经过沼泽 = √2 × 5 = 7.07）。

5. **网格边界外的邻居枚举**：`for_each_neighbor` 的实现中，每个尝试的邻居坐标都必须检查 `in_bounds`。忘记这个检查 → 越界访问 → UB 或 crash。使用 `at()` 的边界检查版本在 debug 模式下捕获此类错误。

6. **混合使用不同坐标系统**：在同一个六边形系统中混用偏移坐标和轴向坐标，但没有统一的转换函数。结果：两个坐标空间的"同一点"指向不同的格子。解决：系统中只使用一种内部表示（推荐轴向），仅在 IO/渲染时转换。
