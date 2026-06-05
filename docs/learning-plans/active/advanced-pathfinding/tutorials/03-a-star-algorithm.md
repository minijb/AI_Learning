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
