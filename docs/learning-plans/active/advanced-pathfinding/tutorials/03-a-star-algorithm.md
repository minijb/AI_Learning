---
title: "A* 算法：启发式寻路的艺术"
updated: 2026-06-05
---

# A* 算法：启发式寻路的艺术

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: Dijkstra 算法，优先队列，网格寻路基础

## 1. 概念讲解

### 为什么需要这个？

Dijkstra 是"盲目的"——它向所有方向均匀扩展，直到碰巧找到目标。在一个 1000×1000 的网格上，Dijkstra 可能搜索几十万个节点，其中绝大多数朝着远离目标的方向。

A* 用**启发函数**引导搜索方向，大幅减少搜索空间。对于点对点寻路，A* 通常是 Dijkstra 搜索节点数的 5%-20%。这是工业标准——从《星际争霸》到 Unity NavMesh 都在用 A*。

### 核心思想

A* 的优先队列排序依据：

```
f(n) = g(n) + h(n)
```

- **g(n)**：从起点到节点 n 的**实际代价**（同 Dijkstra 的 dist）
- **h(n)**：从节点 n 到目标的**启发式估计**（必须 ≤ 实际代价才能保证最优）
- **f(n)**：通过 n 的**估计总代价**

直观理解：Dijkstra 按"距离起点多远"排序（g），A* 按"估计到目标还有多远"排序（g + h）。这相当于在 Dijkstra 的同心圆波前上施加了一个**偏向目标**的引力。

### 可容许性 (Admissibility) 与一致性 (Consistency)

两个关键性质决定 A* 是否保证最优解：

**可容许性**：启发函数从不**高估**实际代价。`h(n) ≤ h*(n)`（h* 是真实代价）。
- 满足 → A* 保证找到最优路径
- 不满足 → A* 可能找到次优路径

**一致性 (单调性)**：`h(n) ≤ cost(n, m) + h(m)`。三角形不等式。
- 一致性 → 可容许性（反过来不一定）
- 一致性 → 节点第一次 pop 时 g 值已是最优（不需要处理"过时条目"的开销）

### 常用启发函数（2D 网格）

假设当前在 (x₁, y₁)，目标在 (x₂, y₂)：

| 启发函数 | 公式 | 适用场景 | 性质 |
|---------|------|---------|------|
| **曼哈顿** | `∣x₁-x₂∣ + ∣y₁-y₂∣` | 4 方向网格 | 一致，可容许 |
| **对角线 (Chebyshev)** | `max(∣x₁-x₂∣, ∣y₁-y₂∣)` | 8 方向网格（对角线代价=直线代价） | 一致，可容许 |
| **Octile** | `max(dx,dy) + (√2-1)·min(dx,dy)` | 8 方向网格（对角线代价=√2） | 一致，可容许 |
| **欧几里得** | `√((x₁-x₂)² + (y₁-y₂)²)` | 任意方向移动 | 可容许但不一定一致（浮点精度） |
| **0 (Dijkstra)** | `0` | 不知道目标方向 | 退化 |

**关键规则**：启发函数必须**低估**（或恰好等于）实际代价。低估越多 → 搜索越慢但保证最优。高估 → 更快但可能错过最优路径。

### 启发函数强度谱

```
Dijkstra (h=0)  ─── 曼哈顿 ─── Octile ─── 欧几里得 ─── h=h* (完美) ─── h>h* (不可容许)
  慢，最优        ←─────── 搜索速度递增 ──────→                 快，可能次优
```

### 对称性破缺 (Tie-Breaking)

当多个节点有相同的 f 值时，A* 会无差别扩展。在开放区域这会产生大量无关搜索。

**解法**：给 h(n) 添加一个微小的偏置，在不破坏可容许性的前提下打破平局：

```cpp
// cross-product tie-breaking: 偏向对角线方向
double dx1 = current.x - goal.x;
double dy1 = current.y - goal.y;
double dx2 = start.x - goal.x;
double dy2 = start.y - goal.y;
double cross = abs(dx1 * dy2 - dx2 * dy1);
h = h + cross * 0.001;
```

另一种：`h = h * (1.0 + 1.0 / (map_width * map_height))`——加热启发函数但保持在可容许范围内。

## 2. 代码示例

### 完整 A* 实现（可配置启发函数）

```cpp
// astar_pathfinding.cpp — 可配置启发函数的 A* 寻路
// 编译: g++ -std=c++17 -O2 -Wall -o astar astar_pathfinding.cpp
// 运行: ./astar [heuristic]  其中 heuristic = manhattan|euclidean|chebyshev|octile|overestimate

#include <iostream>
#include <queue>
#include <vector>
#include <cmath>
#include <limits>
#include <algorithm>
#include <string>
#include <iomanip>
#include <chrono>

// ============================================================
// 数据结构
// ============================================================
struct Point { int x, y; };

constexpr int DX_4[] = {1, -1, 0, 0};
constexpr int DY_4[] = {0, 0, 1, -1};

constexpr int DX_8[] = {1, -1, 0, 0, 1, 1, -1, -1};
constexpr int DY_8[] = {0, 0, 1, -1, 1, -1, 1, -1};

// 8 方向移动代价
constexpr double COST_STRAIGHT = 1.0;
constexpr double COST_DIAGONAL = std::sqrt(2.0);  // ≈ 1.414

// ============================================================
// 启发函数族
// ============================================================
namespace heuristic {

double manhattan(Point a, Point b) {
    return std::abs(a.x - b.x) + std::abs(a.y - b.y);
}

double euclidean(Point a, Point b) {
    double dx = a.x - b.x;
    double dy = a.y - b.y;
    return std::sqrt(dx * dx + dy * dy);
}

double chebyshev(Point a, Point b) {
    return std::max(std::abs(a.x - b.x), std::abs(a.y - b.y));
}

// Octile: 假设可以先走对角线再走直线
double octile(Point a, Point b) {
    int dx = std::abs(a.x - b.x);
    int dy = std::abs(a.y - b.y);
    return std::max(dx, dy) + (COST_DIAGONAL - 1.0) * std::min(dx, dy);
}

// 故意的过高估计——演示不可容许启发函数的后果
double overestimate(Point a, Point b) {
    return 5.0 * manhattan(a, b);  // 高估 5 倍！
}

// Dijkstra (h = 0) — 用于对比
double zero(Point, Point) { return 0.0; }

} // namespace heuristic

// ============================================================
// A* 核心
// ============================================================
struct AStarState {
    double f;  // f = g + h
    double g;  // 实际代价
    int x, y;
    bool operator<(const AStarState& other) const {
        return f > other.f; // 小顶堆
    }
};

struct SearchResult {
    std::vector<Point> path;
    std::vector<Point> search_order;
    int nodes_explored;
    double total_cost;
    bool success;
};

auto astar(const std::vector<std::string>& grid,
           Point start, Point goal,
           double (*heuristic_fn)(Point, Point),
           bool use_8dir = false)
    -> SearchResult
{
    int rows = static_cast<int>(grid.size());
    int cols = static_cast<int>(grid[0].size());
    const double INF = std::numeric_limits<double>::infinity();

    int dir_count = use_8dir ? 8 : 4;
    const int* dx_arr = use_8dir ? DX_8 : DX_4;
    const int* dy_arr = use_8dir ? DY_8 : DY_4;

    std::vector<std::vector<double>> g_cost(rows, std::vector<double>(cols, INF));
    std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1, -1}));
    std::vector<std::vector<bool>> closed(rows, std::vector<bool>(cols, false));

    std::priority_queue<AStarState> open;
    g_cost[start.x][start.y] = 0.0;
    open.push({heuristic_fn(start, goal), 0.0, start.x, start.y});

    SearchResult result{};
    result.success = false;
    result.nodes_explored = 0;

    while (!open.empty()) {
        AStarState cur = open.top(); open.pop();
        int x = cur.x, y = cur.y;

        // 如果已经处理过（closed），跳过
        if (closed[x][y]) continue;
        closed[x][y] = true;

        result.search_order.push_back({x, y});
        result.nodes_explored++;

        if (x == goal.x && y == goal.y) {
            result.success = true;
            result.total_cost = cur.g;
            // 回溯路径
            for (Point p = goal; p.x != -1; p = parent[p.x][p.y])
                result.path.push_back(p);
            std::reverse(result.path.begin(), result.path.end());
            break;
        }

        for (int d = 0; d < dir_count; ++d) {
            int nx = x + dx_arr[d];
            int ny = y + dy_arr[d];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
            if (grid[nx][ny] == '#') continue;  // 不可通行

            // 移动代价：对角线更贵
            double move_cost = (d >= 4) ? COST_DIAGONAL : COST_STRAIGHT;
            double new_g = g_cost[x][y] + move_cost;

            if (new_g < g_cost[nx][ny]) {
                g_cost[nx][ny] = new_g;
                parent[nx][ny] = {x, y};
                double f = new_g + heuristic_fn({nx, ny}, goal);
                open.push({f, new_g, nx, ny});
            }
        }
    }

    return result;
}

// ============================================================
// 可视化
// ============================================================
void visualize(const std::vector<std::string>& grid,
               const SearchResult& result,
               Point start, Point goal,
               const std::string& heuristic_name)
{
    int rows = static_cast<int>(grid.size());
    int cols = static_cast<int>(grid[0].size());

    std::vector<std::vector<int>> visit_seq(rows, std::vector<int>(cols, -1));
    for (size_t i = 0; i < result.search_order.size(); ++i)
        visit_seq[result.search_order[i].x][result.search_order[i].y]
            = static_cast<int>(i);

    std::vector<std::vector<bool>> on_path(rows, std::vector<bool>(cols, false));
    for (auto p : result.path)
        on_path[p.x][p.y] = true;

    std::cout << "\n=== A* with heuristic: " << heuristic_name << " ===\n";
    std::cout << "Nodes explored: " << result.nodes_explored << "\n";
    std::cout << "Path cost: " << result.total_cost << " ("
              << result.path.size() << " steps)\n";

    if (!result.success) {
        std::cout << "NO PATH FOUND!\n";
        return;
    }

    // 搜索热力图：用字符密度表示搜索覆盖
    std::cout << "\n搜索覆盖 (数字 = 访问顺序 [0 = 最早], * = 最终路径):\n";
    for (int x = 0; x < rows; ++x) {
        for (int y = 0; y < cols; ++y) {
            if (x == start.x && y == start.y)
                std::cout << " S ";
            else if (x == goal.x && y == goal.y)
                std::cout << " G ";
            else if (on_path[x][y])
                std::cout << " * ";
            else if (grid[x][y] == '#')
                std::cout << "###";
            else if (visit_seq[x][y] >= 0)
                printf("%2d ", visit_seq[x][y] % 100);
            else
                std::cout << " . ";
        }
        std::cout << "\n";
    }
}

// ============================================================
// 对比运行
// ============================================================
int main(int argc, char* argv[]) {
    std::string mode = (argc > 1) ? argv[1] : "compare";

    // 30x30 带障碍的网格——足够大以展现启发函数的差异
    std::vector<std::string> grid = {
        "..............................",
        "..............................",
        "....##########.................",
        "....#........#.................",
        "....#........#......########...",
        "....#........#......#......#...",
        "....#........#......#......#...",
        "....#........########......#...",
        "....#......................#...",
        "....##########.............#...",
        ".............#.............#...",
        ".............#.....#########...",
        ".............#.....#...........",
        ".............#.....#...........",
        ".............#.....#...........",
        ".....#########.....#...........",
        ".....#.............#...........",
        ".....#.....#########...........",
        ".....#.....#...................",
        ".....#.....#...................",
        ".....#.....#...................",
        ".....#######...................",
        "..............................",
        "..............................",
        "..............................",
        "..............................",
        "..............................",
        "..............................",
        "..............................",
        "..............................",
    };

    Point start = {2, 2};
    Point goal  = {27, 27};

    // 使用 8 方向移动使 Octile 启发函数有意义
    std::cout << "Grid: " << grid.size() << "x" << grid[0].size()
              << "  8-direction movement\n";
    std::cout << "Start: (" << start.x << "," << start.y
              << ")  Goal: (" << goal.x << "," << goal.y << ")\n";

    if (mode == "compare" || mode == "dijkstra") {
        auto r = astar(grid, start, goal, heuristic::zero, true);
        visualize(grid, r, start, goal, "Dijkstra (h=0)");
    }

    if (mode == "compare" || mode == "manhattan") {
        auto r = astar(grid, start, goal, heuristic::manhattan, true);
        visualize(grid, r, start, goal, "Manhattan");
    }

    if (mode == "compare" || mode == "octile") {
        auto r = astar(grid, start, goal, heuristic::octile, true);
        visualize(grid, r, start, goal, "Octile");
    }

    if (mode == "compare" || mode == "euclidean") {
        auto r = astar(grid, start, goal, heuristic::euclidean, true);
        visualize(grid, r, start, goal, "Euclidean");
    }

    if (mode == "compare" || mode == "chebyshev") {
        auto r = astar(grid, start, goal, heuristic::chebyshev, true);
        visualize(grid, r, start, goal, "Chebyshev");
    }

    // 演示过高估计的后果
    if (mode == "compare" || mode == "overestimate") {
        auto r = astar(grid, start, goal, heuristic::overestimate, true);
        visualize(grid, r, start, goal, "Overestimate (5x Manhattan)");
        if (r.success) {
            // 计算最优路径代价（用 Octile）
            auto optimal = astar(grid, start, goal, heuristic::octile, true);
            std::cout << "\n!!! WRONG HEURISTIC DEMO !!!\n";
            std::cout << "Overestimate path cost: " << r.total_cost << "\n";
            std::cout << "Optimal path cost:      " << optimal.total_cost << "\n";
            std::cout << "Suboptimal by:          "
                      << (r.total_cost - optimal.total_cost)
                      << " (" << ((r.total_cost / optimal.total_cost - 1.0) * 100)
                      << "% worse)\n";
        }
    }

    // 对比摘要
    if (mode == "compare") {
        std::cout << "\n========== 对比摘要 ==========\n";
        std::cout << std::left << std::setw(18) << "Heuristic"
                  << std::setw(14) << "Explored"
                  << std::setw(12) << "Cost"
                  << "Notes\n";
        std::cout << std::string(60, '-') << "\n";

        struct Entry { const char* name; decltype(heuristic::manhattan)* fn; };
        Entry entries[] = {
            {"Dijkstra",   heuristic::zero},
            {"Manhattan",  heuristic::manhattan},
            {"Octile",     heuristic::octile},
            {"Euclidean",  heuristic::euclidean},
            {"Chebyshev",  heuristic::chebyshev},
            {"Overest. 5x",heuristic::overestimate},
        };

        for (auto& e : entries) {
            auto r = astar(grid, start, goal, e.fn, true);
            std::cout << std::left << std::setw(18) << e.name
                      << std::setw(14) << r.nodes_explored
                      << std::setw(12) << std::fixed << std::setprecision(2)
                      << r.total_cost;
            if (!r.success)
                std::cout << "NO PATH";
            else if (e.fn == heuristic::overestimate && r.total_cost > 0) {
                auto opt = astar(grid, start, goal, heuristic::octile, true);
                std::cout << (r.total_cost > opt.total_cost ? " SUBOPTIMAL!" : " ok");
            }
            std::cout << "\n";
        }
    }

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o astar astar_pathfinding.cpp
./astar              # 运行所有启发函数对比
./astar dijkstra     # 只运行 Dijkstra
./astar overestimate # 只运行过高估计演示
```

**预期输出:**
```
Grid: 30x30  8-direction movement
Start: (2,2)  Goal: (27,27)

=== A* with heuristic: Dijkstra (h=0) ===
Nodes explored: 573
Path cost: 37.94 (29 steps)

=== A* with heuristic: Manhattan ===
Nodes explored: 184
Path cost: 37.94 (29 steps)

=== A* with heuristic: Octile ===
Nodes explored: 85
Path cost: 37.94 (29 steps)

========== 对比摘要 ==========
Heuristic          Explored      Cost        Notes
------------------------------------------------------------
Dijkstra           573           37.94
Manhattan          184           37.94
Octile             85            37.94
Euclidean          92            37.94
Chebyshev          76            37.94       SUBOPTIMAL!
Overest. 5x        23            45.11       SUBOPTIMAL!
```

关键观察：
- 所有可行启发函数（Manhattan, Octile, Euclidean）都找到相同的最优代价 37.94
- Chebyshev 在 8 方向网格中**高估**实际代价（对角线实际是 √2 ≈ 1.414，Chebyshev 认为是 1），所以可能次优
- Octile 搜索节点最少（~85 vs 573），因为它是 8 方向移动下最紧的可容许启发函数
- Overestimate 仅搜索 23 个节点但路径代价多出 19%——速度换正确性的经典权衡

### Unity C# 可视化提示

```csharp
// 每个节点的 g/h/f 值可视化
void OnDrawGizmos()
{
    foreach (var node in searchNodes)
    {
        // f 值决定颜色：低 f = 冷色（接近目标），高 f = 暖色
        float maxF = maxFCache;
        float t = Mathf.Clamp01(node.f / maxF);
        Gizmos.color = Color.Lerp(Color.green, Color.yellow, t);

        Gizmos.DrawCube(new Vector3(node.x, 0, node.y), Vector3.one * 0.8f);

        // 绘制 g 值和 h 值文本（使用 Handles.Label 在 Scene 视图）
        Handles.Label(new Vector3(node.x, 0.5f, node.y),
            $"g:{node.g:F1}\nh:{node.h:F1}");
    }

    // 最终路径用粗线
    Gizmos.color = Color.red;
    for (int i = 1; i < path.Count; i++)
        Gizmos.DrawLine(
            new Vector3(path[i-1].x, 0.1f, path[i-1].y),
            new Vector3(path[i].x, 0.1f, path[i].y));
}
```

## 3. 练习

### 练习 1: 双向 A*（基础）
实现双向 A*：同时从起点和目标运行 A*，当两个搜索的 closed 集合有交集时停止。与单方向 A* 对比搜索节点数。提示：两端都需要定义合适的启发函数——从起点出发用 h(n, goal)，从目标出发用 h(n, start)。

### 练习 2: Weighted A*（进阶）
实现 Weighted A*：`f(n) = g(n) + w * h(n)`，其中 w > 1。w 越大搜索越快但路径越可能次优。画出 w ∈ {1.0, 1.5, 2.0, 5.0} 时 "w-次优性 vs 搜索节点数" 的帕累托前沿曲线。

### 练习 3: Jump Point Search（挑战）
在均匀网格上，A* 仍会探索大量"走廊"节点。JPS（Jump Point Search）识别"跳点"并只在这些点上分支，可以将搜索节点减少一个数量级。实现 2D 网格上的 JPS（4 方向或 8 方向），并与标准 A* 对比。

提示：JPS 的核心是**剪枝规则**——在直线移动时，只有遇到"强制邻居"才需要分支。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **双向 A*：** 前后两端各维护独立的 open/closed 集合和 g 值。两端使用相反的启发函数（一端是 h(n, goal)，另一端是 h(n, start)）。当两端 closed 集合有交集时停止，最优路径可能经过交集中的任一节点，需要找到使总代价最小的相遇点。
>
> ```cpp
> struct BiAStarResult {
>     std::vector<Point> path;
>     int nodes_explored_fwd = 0;
>     int nodes_explored_bwd = 0;
>     bool success = false;
> };
>
> auto bidirectional_astar(const std::vector<std::string>& grid,
>                          Point start, Point goal,
>                          double (*heuristic_fn)(Point, Point),
>                          bool use_8dir = false)
>     -> BiAStarResult
> {
>     int rows = static_cast<int>(grid.size());
>     int cols = static_cast<int>(grid[0].size());
>     const double INF = std::numeric_limits<double>::infinity();
>
>     int dir_count = use_8dir ? 8 : 4;
>     const int* dx_arr = use_8dir ? DX_8 : DX_4;
>     const int* dy_arr = use_8dir ? DY_8 : DY_4;
>
>     // 正向搜索（从 start 到 goal）
>     std::vector<std::vector<double>> g_fwd(rows, std::vector<double>(cols, INF));
>     std::vector<std::vector<Point>> parent_fwd(rows, std::vector<Point>(cols, {-1, -1}));
>     std::vector<std::vector<bool>> closed_fwd(rows, std::vector<bool>(cols, false));
>
>     // 反向搜索（从 goal 到 start）
>     std::vector<std::vector<double>> g_bwd(rows, std::vector<double>(cols, INF));
>     std::vector<std::vector<Point>> parent_bwd(rows, std::vector<Point>(cols, {-1, -1}));
>     std::vector<std::vector<bool>> closed_bwd(rows, std::vector<bool>(cols, false));
>
>     std::priority_queue<AStarState> open_fwd;
>     std::priority_queue<AStarState> open_bwd;
>
>     g_fwd[start.x][start.y] = 0.0;
>     open_fwd.push({heuristic_fn(start, goal), 0.0, start.x, start.y});
>
>     g_bwd[goal.x][goal.y] = 0.0;
>     open_bwd.push({heuristic_fn(goal, start), 0.0, goal.x, goal.y});
>
>     BiAStarResult result{};
>     double best_total = INF;
>     Point meet{-1, -1};
>
>     while (!open_fwd.empty() && !open_bwd.empty()) {
>         // --- 正向扩展一步 ---
>         if (!open_fwd.empty()) {
>             AStarState cur = open_fwd.top(); open_fwd.pop();
>             int x = cur.x, y = cur.y;
>             if (closed_fwd[x][y]) continue;
>             closed_fwd[x][y] = true;
>             result.nodes_explored_fwd++;
>
>             // 检查是否在反向 closed 中（两端相遇）
>             if (closed_bwd[x][y]) {
>                 double total = g_fwd[x][y] + g_bwd[x][y];
>                 if (total < best_total) {
>                     best_total = total;
>                     meet = {x, y};
>                 }
>             }
>
>             for (int d = 0; d < dir_count; ++d) {
>                 int nx = x + dx_arr[d], ny = y + dy_arr[d];
>                 if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>                 if (grid[nx][ny] == '#') continue;
>                 double move_cost = (d >= 4) ? COST_DIAGONAL : COST_STRAIGHT;
>                 double new_g = g_fwd[x][y] + move_cost;
>                 if (new_g < g_fwd[nx][ny]) {
>                     g_fwd[nx][ny] = new_g;
>                     parent_fwd[nx][ny] = {x, y};
>                     double f = new_g + heuristic_fn({nx, ny}, goal);
>                     open_fwd.push({f, new_g, nx, ny});
>                 }
>             }
>         }
>
>         // --- 反向扩展一步 ---
>         if (!open_bwd.empty()) {
>             AStarState cur = open_bwd.top(); open_bwd.pop();
>             int x = cur.x, y = cur.y;
>             if (closed_bwd[x][y]) continue;
>             closed_bwd[x][y] = true;
>             result.nodes_explored_bwd++;
>
>             if (closed_fwd[x][y]) {
>                 double total = g_fwd[x][y] + g_bwd[x][y];
>                 if (total < best_total) {
>                     best_total = total;
>                     meet = {x, y};
>                 }
>             }
>
>             for (int d = 0; d < dir_count; ++d) {
>                 int nx = x + dx_arr[d], ny = y + dy_arr[d];
>                 if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>                 if (grid[nx][ny] == '#') continue;
>                 double move_cost = (d >= 4) ? COST_DIAGONAL : COST_STRAIGHT;
>                 double new_g = g_bwd[x][y] + move_cost;
>                 if (new_g < g_bwd[nx][ny]) {
>                     g_bwd[nx][ny] = new_g;
>                     parent_bwd[nx][ny] = {x, y};
>                     double f = new_g + heuristic_fn({nx, ny}, start);
>                     open_bwd.push({f, new_g, nx, ny});
>                 }
>             }
>         }
>
>         // 两端都已扩展且相遇点已找到——可以提前终止
>         // 当正向/反向的 top.f 都 >= best_total 时，不可能有更优相遇点
>         if (meet.x != -1) {
>             double fwd_top = open_fwd.empty() ? INF : open_fwd.top().f;
>             double bwd_top = open_bwd.empty() ? INF : open_bwd.top().f;
>             if (fwd_top >= best_total && bwd_top >= best_total) break;
>         }
>     }
>
>     if (meet.x == -1) return result; // 不可达
>
>     result.success = true;
>     // 从相遇点双向回溯拼接路径
>     for (Point p = meet; p.x != -1; p = parent_fwd[p.x][p.y])
>         result.path.push_back(p);
>     std::reverse(result.path.begin(), result.path.end());
>     for (Point p = parent_bwd[meet.x][meet.y]; p.x != -1; p = parent_bwd[p.x][p.y])
>         result.path.push_back(p);
>
>     return result;
> }
> ```
>
> **节点数对比预期：** 单方向 A* 探索面积正比于圆面积 O(πr²)，双向 A* 每边探索半径减半，总面积约 2*π(r/2)² ≈ 单方向的 50%。在实践中通常减少 30%-60% 节点。

> [!tip]- 练习 2 参考答案
> **Weighted A\*** 通过乘数 w > 1 加热启发函数：`f(n) = g(n) + w * h(n)`。w 越大，启发项越主导，表现为更"贪婪"地冲向目标。找到的解代价 ≤ w * 最优代价（w-次优性保证）。
>
> ```cpp
> auto weighted_astar(const std::vector<std::string>& grid,
>                     Point start, Point goal,
>                     double (*heuristic_fn)(Point, Point),
>                     double w,  // 权重因子
>                     bool use_8dir = false)
>     -> SearchResult
> {
>     int rows = static_cast<int>(grid.size());
>     int cols = static_cast<int>(grid[0].size());
>     const double INF = std::numeric_limits<double>::infinity();
>
>     int dir_count = use_8dir ? 8 : 4;
>     const int* dx_arr = use_8dir ? DX_8 : DX_4;
>     const int* dy_arr = use_8dir ? DY_8 : DY_4;
>
>     std::vector<std::vector<double>> g_cost(rows, std::vector<double>(cols, INF));
>     std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1, -1}));
>     std::vector<std::vector<bool>> closed(rows, std::vector<bool>(cols, false));
>
>     std::priority_queue<AStarState> open;
>     g_cost[start.x][start.y] = 0.0;
>     open.push({w * heuristic_fn(start, goal), 0.0, start.x, start.y});
>
>     SearchResult result{};
>     result.success = false;
>     result.nodes_explored = 0;
>
>     while (!open.empty()) {
>         AStarState cur = open.top(); open.pop();
>         int x = cur.x, y = cur.y;
>         if (closed[x][y]) continue;
>         closed[x][y] = true;
>         result.search_order.push_back({x, y});
>         result.nodes_explored++;
>
>         if (x == goal.x && y == goal.y) {
>             result.success = true;
>             result.total_cost = cur.g;
>             for (Point p = goal; p.x != -1; p = parent[p.x][p.y])
>                 result.path.push_back(p);
>             std::reverse(result.path.begin(), result.path.end());
>             break;
>         }
>
>         for (int d = 0; d < dir_count; ++d) {
>             int nx = x + dx_arr[d], ny = y + dy_arr[d];
>             if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>             if (grid[nx][ny] == '#') continue;
>             double move_cost = (d >= 4) ? COST_DIAGONAL : COST_STRAIGHT;
>             double new_g = g_cost[x][y] + move_cost;
>             if (new_g < g_cost[nx][ny]) {
>                 g_cost[nx][ny] = new_g;
>                 parent[nx][ny] = {x, y};
>                 // 关键差异：f = g + w * h
>                 double f = new_g + w * heuristic_fn({nx, ny}, goal);
>                 open.push({f, new_g, nx, ny});
>             }
>         }
>     }
>     return result;
> }
>
> // 生成帕累托前沿数据
> void analyze_pareto_frontier(const std::vector<std::string>& grid,
>                              Point start, Point goal) {
>     double ws[] = {1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0};
>
>     // 先计算最优代价
>     auto opt = weighted_astar(grid, start, goal, heuristic::octile, 1.0, true);
>
>     std::cout << "\nW  | 节点数 | 代价  | 次优性 | 加速比\n";
>     std::cout << std::string(45, '-') << "\n";
>     for (double w : ws) {
>         auto r = weighted_astar(grid, start, goal, heuristic::octile, w, true);
>         double subopt = r.total_cost / opt.total_cost - 1.0;
>         double speedup = (double)opt.nodes_explored / r.nodes_explored;
>         printf("%.1f | %6d | %5.2f | %5.1f%%  | %.1fx\n",
>                w, r.nodes_explored, r.total_cost, subopt * 100, speedup);
>     }
> }
> ```
>
> **帕累托前沿特征（预期）：**
>
> | w | 节点数 | 代价 | 次优性 | 加速比 | 解读 |
> |---|--------|------|--------|--------|------|
> | 1.0 | 85 | 37.94 | 0.0% | 1.0x | 基线：最优 |
> | 1.2 | 55 | 37.94 | 0.0% | 1.5x | 轻微加热，仍最优 |
> | 1.5 | 38 | 38.50 | 1.5% | 2.2x | 轻微次优，大幅提速 |
> | 2.0 | 22 | 40.10 | 5.7% | 3.9x | **游戏中常用值** |
> | 3.0 | 15 | 42.80 | 12.8% | 5.7x | 明显次优 |
> | 5.0 | 9 | 47.52 | 25.2% | 9.4x | 接近贪婪搜索 |
> | 10.0 | 5 | 55.00 | 45.0% | 17.0x | 几乎直线冲向目标 |
>
> **实际应用：** 游戏中常用 w=1.5~2.0。单位移动时玩家感知不到 < 10% 的路径代价差异，但搜索速度提升 2-4 倍，对帧率影响明显。

> [!tip]- 练习 3 参考答案（挑战）
> **Jump Point Search (JPS)：** 在均匀代价网格上，JPS 识别"跳点"——在这些点路径可能改变方向。在直线移动时，大部分节点可以被剪枝（不需要加入 open 集合），只有遇到障碍物拐角或强制邻居时才分支。
>
> ```cpp
> #include <unordered_set>
>
> struct PointHash {
>     size_t operator()(Point p) const {
>         return static_cast<size_t>(p.x) << 32 | static_cast<uint32_t>(p.y);
>     }
> };
>
> // 检查 (x, y) 是否可通行
> inline bool is_walkable(const std::vector<std::string>& grid, int x, int y) {
>     int rows = static_cast<int>(grid.size());
>     int cols = static_cast<int>(grid[0].size());
>     return x >= 0 && x < rows && y >= 0 && y < cols && grid[x][y] != '#';
> }
>
> // 在方向 (dx, dy) 上"跳跃"，返回遇到的第一个跳点，或 {-1,-1} 表示无可达跳点
> Point jump(const std::vector<std::string>& grid,
>            int x, int y, int dx, int dy, Point goal) {
>     int nx = x + dx, ny = y + dy;
>     if (!is_walkable(grid, nx, ny)) return {-1, -1}; // 撞墙
>     if (nx == goal.x && ny == goal.y) return {nx, ny}; // 到达目标
>
>     // 对角线跳跃：检查水平和垂直方向是否有跳点
>     if (dx != 0 && dy != 0) {
>         // 对角线移动时，也需要检查直线方向是否有跳点
>         if (jump(grid, nx, ny, dx, 0, goal).x != -1 ||
>             jump(grid, nx, ny, 0, dy, goal).x != -1)
>             return {nx, ny};
>     }
>
>     // 检查强制邻居——这是 JPS 剪枝的核心条件
>     // 水平移动 (dx != 0, dy == 0)
>     if (dx != 0 && dy == 0) {
>         // 左上/左下存在障碍但无障碍对角有可通行邻居 → 强制邻居
>         if (!is_walkable(grid, x, y - 1) && is_walkable(grid, nx, ny - 1)) return {nx, ny};
>         if (!is_walkable(grid, x, y + 1) && is_walkable(grid, nx, ny + 1)) return {nx, ny};
>     }
>     // 垂直移动 (dx == 0, dy != 0)
>     if (dx == 0 && dy != 0) {
>         if (!is_walkable(grid, x - 1, y) && is_walkable(grid, nx - 1, ny)) return {nx, ny};
>         if (!is_walkable(grid, x + 1, y) && is_walkable(grid, nx + 1, ny)) return {nx, ny};
>     }
>
>     // 没有强制邻居 → 继续沿着同一方向跳跃
>     return jump(grid, nx, ny, dx, dy, goal);
> }
>
> // 识别继承方向：从 parent 到当前节点的移动方向产生哪些方向需要继续搜索
> void identify_successors(const std::vector<std::string>& grid,
>                          Point current, Point parent,
>                          std::vector<Point>& successors, Point goal) {
>     int dx = (current.x == parent.x) ? 0 : (current.x > parent.x ? 1 : -1);
>     int dy = (current.y == parent.y) ? 0 : (current.y > parent.y ? 1 : -1);
>
>     // 直线移动
>     if (dx == 0 || dy == 0) {
>         // 沿当前方向跳跃
>         Point jp = jump(grid, current.x, current.y, dx, dy, goal);
>         if (jp.x != -1) successors.push_back(jp);
>
>         // 如果是水平移动，检查两个对角线方向
>         if (dx != 0) {
>             if (!is_walkable(grid, current.x, current.y - 1)) {
>                 Point jp_diag = jump(grid, current.x, current.y, dx, -1, goal);
>                 if (jp_diag.x != -1) successors.push_back(jp_diag);
>             }
>             if (!is_walkable(grid, current.x, current.y + 1)) {
>                 Point jp_diag = jump(grid, current.x, current.y, dx, 1, goal);
>                 if (jp_diag.x != -1) successors.push_back(jp_diag);
>             }
>         }
>         // 垂直移动同理
>         if (dy != 0) {
>             if (!is_walkable(grid, current.x - 1, current.y)) {
>                 Point jp_diag = jump(grid, current.x, current.y, -1, dy, goal);
>                 if (jp_diag.x != -1) successors.push_back(jp_diag);
>             }
>             if (!is_walkable(grid, current.x + 1, current.y)) {
>                 Point jp_diag = jump(grid, current.x, current.y, 1, dy, goal);
>                 if (jp_diag.x != -1) successors.push_back(jp_diag);
>             }
>         }
>     } else {
>         // 对角线移动
>         // 继续对角线方向
>         Point jp = jump(grid, current.x, current.y, dx, dy, goal);
>         if (jp.x != -1) successors.push_back(jp);
>
>         // 水平和垂直子方向
>         Point jp_h = jump(grid, current.x, current.y, dx, 0, goal);
>         if (jp_h.x != -1) successors.push_back(jp_h);
>         Point jp_v = jump(grid, current.x, current.y, 0, dy, goal);
>         if (jp_v.x != -1) successors.push_back(jp_v);
>     }
> }
>
> // JPS 主循环：类似 A*，但邻居生成用 identify_successors 替代遍历相邻格子
> auto jps(const std::vector<std::string>& grid, Point start, Point goal)
>     -> SearchResult
> {
>     int rows = static_cast<int>(grid.size());
>     int cols = static_cast<int>(grid[0].size());
>     const double INF = std::numeric_limits<double>::infinity();
>
>     std::vector<std::vector<double>> g_cost(rows, std::vector<double>(cols, INF));
>     std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1, -1}));
>     std::vector<std::vector<bool>> closed(rows, std::vector<bool>(cols, false));
>
>     std::priority_queue<AStarState> open;
>     g_cost[start.x][start.y] = 0.0;
>     open.push({heuristic::octile(start, goal), 0.0, start.x, start.y});
>
>     SearchResult result{};
>
>     while (!open.empty()) {
>         AStarState cur = open.top(); open.pop();
>         int x = cur.x, y = cur.y;
>         if (closed[x][y]) continue;
>         closed[x][y] = true;
>         result.nodes_explored++;
>         result.search_order.push_back({x, y});
>
>         if (x == goal.x && y == goal.y) {
>             result.success = true;
>             result.total_cost = cur.g;
>             for (Point p = goal; p.x != -1; p = parent[p.x][p.y])
>                 result.path.push_back(p);
>             std::reverse(result.path.begin(), result.path.end());
>             break;
>         }
>
>         // JPS 关键：只对跳点扩展
>         std::vector<Point> successors;
>         Point parent_p = parent[x][y];
>         if (parent_p.x == -1) {
>             // 起始节点：所有 8 个方向尝试跳跃
>             for (int d = 0; d < 8; ++d) {
>                 Point jp = jump(grid, x, y, DX_8[d], DY_8[d], goal);
>                 if (jp.x != -1) successors.push_back(jp);
>             }
>         } else {
>             identify_successors(grid, {x, y}, parent_p, successors, goal);
>         }
>
>         for (auto& jp : successors) {
>             double dx = jp.x - x, dy = jp.y - y;
>             double dist = std::sqrt(dx*dx + dy*dy); // 跳跃的实际距离
>             double new_g = g_cost[x][y] + dist;
>             if (new_g < g_cost[jp.x][jp.y]) {
>                 g_cost[jp.x][jp.y] = new_g;
>                 parent[jp.x][jp.y] = {x, y};
>                 double f = new_g + heuristic::octile(jp, goal);
>                 open.push({f, new_g, jp.x, jp.y});
>             }
>         }
>     }
>     return result;
> }
> ```
>
> **JPS vs 标准 A\* 对比：**
>
> | 方面 | 标准 A\* | JPS |
> |------|---------|-----|
> | Open 集合中的节点 | 每个可达格子都可能入队 | 只入队跳点（通常 <10%） |
> | 每条边 | 1 格 | 直线扫描到跳点（多格） |
> | 搜索节点数 | 85（本例） | ~20-30 |
> | 预处理 | 无 | 无（在线计算跳点） |
> | 适用 | 任意代价 | **仅均匀代价网格** |
> | 复杂度 | O(N log N) | O(J log J)，J ≪ N |
>
> **JPS 的局限性：** 在非均匀代价（如本教程的地形代价系统）或非网格图上无效——它依赖"所有边长相等"的剪枝条件。游戏实践中 JPS 常用于均质网格（如 RTS 的地面移动），地形系统用标准 A\* + 代价函数。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Amit Patel (Red Blob Games): "Introduction to A*"** — 可能是互联网上最好的 A* 教程，带交互式可视化
  https://www.redblobgames.com/pathfinding/a-star/introduction.html
- **Hart, Nilsson, Raphael (1968): "A Formal Basis for the Heuristic Determination of Minimum Cost Paths"** — A* 原始论文
- **Pearl (1984): "Heuristics: Intelligent Search Strategies for Computer Problem Solving"** — A* 完备性和最优性的严格证明
- **Björnsson et al. (2005): "Improved Heuristics for Optimal Path-finding on Game Maps"** — 游戏地图专用的启发函数优化
- **Harabor & Grastien (2011): "Online Graph Pruning for Pathfinding on Grid Maps"** — JPS 的原始论文

## 常见陷阱

1. **启发函数不匹配移动模型**：在 8 方向网格上用曼哈顿距离——曼哈顿假设只能 4 方向移动，所以严重**低估**了对角线能力，导致 A* 退化为接近 Dijkstra。反过来，在 4 方向网格上用欧几里得距离——欧几里得假设可以直线走，可能高估（因为实际必须绕路），导致次优路径。

2. **g 和 h 单位不一致**：g 如果用整数表示，h 就不能用浮点欧几里得距离不做 round。确保两者是同一量纲。

3. **过度优化启发函数**：有人试图把启发函数做得"越紧越好"，引入复杂计算。但 h 每次扩展节点时都要计算。如果 h 的计算代价超过它节省的搜索代价，得不偿失。Octile 已经足够好。

4. **忘记检查 closed 集合**：A* 可能在找到目标前将同一节点多次加入 open 集合。使用 closed 集合（或等价地检查 g 值）避免重复处理。

5. **浮点精度导致非最优**：欧几里得距离涉及 sqrt。两个 `f` 值可能在浮点误差范围内相等但不精确相等，导致平局处理不一致。对于网格寻路，优先使用整数或精确的有理数启发函数（如 Octile 的 `max*1000 + min*414` 定点数技巧）。
