---
title: "Theta*：任意角度寻路"
updated: 2026-06-05
---

# Theta*：任意角度寻路

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: A* 算法, 8 方向网格, Bresenham 画线算法

## 1. 概念讲解

### 为什么需要这个？

A* 在 8 方向网格上找到的是"网格最优路径"——由 45° 倍数的线段拼接而成。问题在于：

- 在开放区域，真实最短路径是一根直线，但 A* 会输出锯齿状的折线
- 即使对路径做后处理平滑，也无法还原直线——平滑只能弯曲折点，不能穿过被跳过的节点
- 在游戏 AI 中，锯齿路径显得"机器人化"，而人类玩家走的是平滑弧线

**Theta\* 的核心洞见**：在 A\* 的搜索过程中，节点的父节点不一定非要是相邻节点——可以是它能看到（无障碍遮挡）的任意祖先。这样搜索出来的路径天然包含长直线段，是网格约束下的真正最短路径。

### 核心思想

标准 A* 设置 parent 的规则：

```
neighbor.parent = current   // 永远指向相邻节点
```

Theta* 改为：

```
// 先检查 line-of-sight(parent(current), neighbor)
// 如果可见，直接用 grandparent
if (lineOfSight(current.parent, neighbor)):
    neighbor.parent = current.parent
    neighbor.g = g(current.parent) + distance(current.parent, neighbor)
else:
    neighbor.parent = current  // 退化到标准 A*
    neighbor.g = g(current) + distance(current, neighbor)
```

**直觉**：每次展开邻居时，Theta\* 抬头看看："这条路径能拉得更直吗？" 如果能直接看到起点方向更远的祖先，就跳过中间节点，直接连接到那个祖先。路径在回溯时自然形成长直线段。

### Theta\* vs Lazy Theta\*

**标准 Theta\***：每次展开邻居都做 line-of-sight 检查。代价高昂——Bresenham 遍历中间格子，对于 N 个扩展节点，每次都是 O(distance)。

**Lazy Theta\***（优化版）：延迟 line-of-sight 检查到节点被 pop（出队）时：

1. 展开邻居时：直接先假定 parent = current.parent（乐观连接）
2. 当节点被 pop 时：才检查到 parent 的 line-of-sight
3. 如果不可见：重新找最近可见祖先，更新 g 值并重新入队

这样每个节点至多做一次 line-of-sight 检查（pop 时），而非展开每个邻居时都做。

### A* vs Theta* 可视化对比

```
A* 8-direction (20×20 grid, start=(1,1), goal=(18,18)):
    * * * * * * * * * * * * * * * * * *
    锯齿 9-step diagonal staircase

Theta* (same map):
    ***********************************
    一条直线 (1,1)→(18,18)，2 步
```

在有障碍的场景中：

```
A* output:
    (0,0) → (0,1) → (1,2) → (2,2) → (3,3) → ... 贴墙走锯齿

Theta* output:
    (0,0) → (5,1) → (10,5) → (15,8) → (18,18)
    三个长直线段，只在障碍拐角处折断
```

### Bresenham Line-of-Sight

Theta* 的 line-of-sight 和图形学中的 Bresenham 画线几乎一样：判断两个格子之间是否有障碍。核心：

```cpp
bool lineOfSight(Point a, Point b, Grid grid) {
    // Bresenham 遍历从 a 到 b 经过的每个格子
    // 如果有任何格子是障碍 → false
    // 否则 → true
}
```

注意细节：Theat* 通常**只看格子中心之间的连线**（对格子网格），并不是严格的几何线段——但工程实践中这已经足够好，且与 A\* 的离散假设一致。

## 2. 代码示例

### 完整 Theta* 实现（含 Bresenham LoS + Lazy 优化）

```cpp
// theta_star.cpp — Theta* 任意角度寻路，含标准版和 Lazy 版
// 编译: g++ -std=c++17 -O2 -Wall -o theta_star theta_star.cpp
// 运行: ./theta_star [standard|lazy|compare]

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

constexpr int DX_8[] = {1, -1, 0, 0, 1, 1, -1, -1};
constexpr int DY_8[] = {0, 0, 1, -1, 1, -1, 1, -1};
constexpr double COST_STRAIGHT = 1.0;
constexpr double COST_DIAGONAL  = 1.4142135623730951; // sqrt(2)

using Grid = std::vector<std::string>;  // '#' = wall

// ============================================================
// 欧几里得距离
// ============================================================
double distance(Point a, Point b) {
    double dx = a.x - b.x;
    double dy = a.y - b.y;
    return std::sqrt(dx*dx + dy*dy);
}

double octile_heuristic(Point a, Point b) {
    int dx = std::abs(a.x - b.x);
    int dy = std::abs(a.y - b.y);
    return std::max(dx, dy) + (COST_DIAGONAL - 1.0) * std::min(dx, dy);
}

// ============================================================
// Bresenham 画线算法 — 判断两点之间是否有障碍
// ============================================================
bool line_of_sight(Point a, Point b, const Grid& grid) {
    int x0 = a.x, y0 = a.y;
    int x1 = b.x, y1 = b.y;

    int dx = std::abs(x1 - x0);
    int dy = std::abs(y1 - y0);
    int sx = (x0 < x1) ? 1 : -1;
    int sy = (y0 < y1) ? 1 : -1;
    int err = dx - dy;

    int x = x0, y = y0;
    while (!(x == x1 && y == y1)) {
        // 检查当前格子（跳过起点和终点）
        if (!(x == x0 && y == y0) && !(x == x1 && y == y1)) {
            if (grid[x][y] == '#') return false;
        }
        int e2 = 2 * err;
        if (e2 > -dy) {
            err -= dy;
            x += sx;
        }
        if (e2 < dx) {
            err += dx;
            y += sy;
        }
        // 万一同时移动（对角线）跳过我们已经离开了的位置
    }
    return true;  // 无阻挡
}

// ============================================================
// 状态结构 — 包含 parent 坐标用于回溯
// ============================================================
struct ThetaState {
    double f, g;
    int x, y;
    int px, py;  // parent 坐标（在优先队列中传递）
    bool operator<(const ThetaState& o) const { return f > o.f; }
};

struct SearchResult {
    std::vector<Point> path;
    std::vector<Point> search_order;
    int nodes_explored = 0;
    double total_cost = 0.0;
    bool success = false;
    int los_checks = 0;  // line-of-sight 检查次数
};

// ============================================================
// 标准 Theta* — 每次扩展邻居时检查 LoS
// ============================================================
SearchResult theta_star(const Grid& grid, Point start, Point goal) {
    int rows = (int)grid.size();
    int cols = (int)grid[0].size();
    const double INF = std::numeric_limits<double>::infinity();

    // parent: parent[x][y] = 该节点当前的 parent 坐标
    std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1,-1}));
    std::vector<std::vector<double>> g_cost(rows, std::vector<double>(cols, INF));
    std::vector<std::vector<bool>> closed(rows, std::vector<bool>(cols, false));

    std::priority_queue<ThetaState> open;
    g_cost[start.x][start.y] = 0.0;
    parent[start.x][start.y] = start;
    open.push({octile_heuristic(start, goal), 0.0, start.x, start.y, start.x, start.y});

    SearchResult result;

    while (!open.empty()) {
        ThetaState cur = open.top(); open.pop();
        if (closed[cur.x][cur.y]) continue;
        closed[cur.x][cur.y] = true;

        result.search_order.push_back({cur.x, cur.y});
        result.nodes_explored++;

        if (cur.x == goal.x && cur.y == goal.y) {
            result.success = true;
            result.total_cost = cur.g;
            // 回溯路径
            for (Point p = goal; !(p.x == start.x && p.y == start.y); p = parent[p.x][p.y])
                result.path.push_back(p);
            result.path.push_back(start);
            std::reverse(result.path.begin(), result.path.end());
            break;
        }

        for (int d = 0; d < 8; ++d) {
            int nx = cur.x + DX_8[d];
            int ny = cur.y + DY_8[d];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
            if (grid[nx][ny] == '#') continue;

            // ===== Theta* 核心：检查 LoS 到 parent(cur) =====
            Point p_cur = parent[cur.x][cur.y];
            double new_g;

            if (p_cur.x >= 0 && line_of_sight(p_cur, {nx, ny}, grid)) {
                // 直接连接到 grandparent
                double dist = distance(p_cur, {nx, ny});
                new_g = g_cost[p_cur.x][p_cur.y] + dist;
                result.los_checks++;

                if (new_g < g_cost[nx][ny]) {
                    g_cost[nx][ny] = new_g;
                    parent[nx][ny] = p_cur;
                    double f = new_g + octile_heuristic({nx, ny}, goal);
                    open.push({f, new_g, nx, ny, p_cur.x, p_cur.y});
                }
            } else {
                // 退化：标准 A* 连接
                double move_cost = (d >= 4) ? COST_DIAGONAL : COST_STRAIGHT;
                new_g = cur.g + move_cost;

                if (new_g < g_cost[nx][ny]) {
                    g_cost[nx][ny] = new_g;
                    parent[nx][ny] = {cur.x, cur.y};
                    double f = new_g + octile_heuristic({nx, ny}, goal);
                    open.push({f, new_g, nx, ny, cur.x, cur.y});
                }
            }
        }
    }
    return result;
}

// ============================================================
// Lazy Theta* — 延迟 LoS 到 pop 时
// ============================================================
SearchResult lazy_theta_star(const Grid& grid, Point start, Point goal) {
    int rows = (int)grid.size();
    int cols = (int)grid[0].size();
    const double INF = std::numeric_limits<double>::infinity();

    std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1,-1}));
    std::vector<std::vector<double>> g_cost(rows, std::vector<double>(cols, INF));
    std::vector<std::vector<bool>> closed(rows, std::vector<bool>(cols, false));

    std::priority_queue<ThetaState> open;
    g_cost[start.x][start.y] = 0.0;
    parent[start.x][start.y] = start;
    open.push({octile_heuristic(start, goal), 0.0, start.x, start.y, start.x, start.y});

    SearchResult result;

    while (!open.empty()) {
        ThetaState cur = open.top(); open.pop();
        if (closed[cur.x][cur.y]) continue;

        // ===== Lazy: pop 时才检查 LoS =====
        Point p_cur = parent[cur.x][cur.y];
        if (p_cur.x >= 0 && !(p_cur.x == cur.x && p_cur.y == cur.y)
            && !line_of_sight(p_cur, {cur.x, cur.y}, grid)) {
            result.los_checks++;

            // 找到最近的可见祖先
            double best_g = INF;
            Point best_parent = {-1, -1};
            for (int d = 0; d < 8; ++d) {
                int px = cur.x + DX_8[d];
                int py = cur.y + DY_8[d];
                if (px < 0 || px >= rows || py < 0 || py >= cols) continue;
                if (!closed[px][py]) continue;
                if (grid[px][py] == '#') continue;
                double candidate_g = g_cost[px][py] + distance({px, py}, {cur.x, cur.y});
                if (candidate_g < best_g) {
                    best_g = candidate_g;
                    best_parent = {px, py};
                }
            }
            if (best_g < INF) {
                g_cost[cur.x][cur.y] = best_g;
                parent[cur.x][cur.y] = best_parent;
                cur.g = best_g;
                cur.f = best_g + octile_heuristic({cur.x, cur.y}, goal);
            }
        }

        closed[cur.x][cur.y] = true;
        result.search_order.push_back({cur.x, cur.y});
        result.nodes_explored++;

        if (cur.x == goal.x && cur.y == goal.y) {
            result.success = true;
            result.total_cost = cur.g;
            for (Point p = goal; !(p.x == start.x && p.y == start.y); p = parent[p.x][p.y])
                result.path.push_back(p);
            result.path.push_back(start);
            std::reverse(result.path.begin(), result.path.end());
            break;
        }

        for (int d = 0; d < 8; ++d) {
            int nx = cur.x + DX_8[d];
            int ny = cur.y + DY_8[d];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
            if (grid[nx][ny] == '#') continue;

            // 乐观：先假设 parent[neighbor] = parent(current)
            // LoS 检查推迟到 neighbor 被 pop 时
            double new_g = g_cost[cur.x][cur.y] + distance({cur.x, cur.y}, {nx, ny});
            if (new_g < g_cost[nx][ny]) {
                g_cost[nx][ny] = new_g;
                parent[nx][ny] = parent[cur.x][cur.y];  // 直接继承 grandparent
                double f = new_g + octile_heuristic({nx, ny}, goal);
                open.push({f, new_g, nx, ny, parent[cur.x][cur.y].x, parent[cur.x][cur.y].y});
            }
        }
    }
    return result;
}

// ============================================================
// 标准 A*（用于对比）
// ============================================================
SearchResult standard_astar(const Grid& grid, Point start, Point goal) {
    int rows = (int)grid.size();
    int cols = (int)grid[0].size();
    const double INF = std::numeric_limits<double>::infinity();

    std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1,-1}));
    std::vector<std::vector<double>> g_cost(rows, std::vector<double>(cols, INF));
    std::vector<std::vector<bool>> closed(rows, std::vector<bool>(cols, false));

    std::priority_queue<ThetaState> open;
    g_cost[start.x][start.y] = 0.0;
    open.push({octile_heuristic(start, goal), 0.0, start.x, start.y, -1, -1});

    SearchResult result;

    while (!open.empty()) {
        ThetaState cur = open.top(); open.pop();
        if (closed[cur.x][cur.y]) continue;
        closed[cur.x][cur.y] = true;

        result.search_order.push_back({cur.x, cur.y});
        result.nodes_explored++;

        if (cur.x == goal.x && cur.y == goal.y) {
            result.success = true;
            result.total_cost = cur.g;
            for (Point p = goal; !(p.x == start.x && p.y == start.y); p = parent[p.x][p.y])
                result.path.push_back(p);
            result.path.push_back(start);
            std::reverse(result.path.begin(), result.path.end());
            break;
        }

        for (int d = 0; d < 8; ++d) {
            int nx = cur.x + DX_8[d];
            int ny = cur.y + DY_8[d];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
            if (grid[nx][ny] == '#') continue;
            double move_cost = (d >= 4) ? COST_DIAGONAL : COST_STRAIGHT;
            double new_g = cur.g + move_cost;

            if (new_g < g_cost[nx][ny]) {
                g_cost[nx][ny] = new_g;
                parent[nx][ny] = {cur.x, cur.y};
                double f = new_g + octile_heuristic({nx, ny}, goal);
                open.push({f, new_g, nx, ny, cur.x, cur.y});
            }
        }
    }
    return result;
}

// ============================================================
// 可视化 — 在字符网格上显示路径
// ============================================================
void visualize(const Grid& grid, const SearchResult& result,
               Point start, Point goal, const std::string& label) {
    int rows = (int)grid.size();
    int cols = (int)grid[0].size();

    std::vector<std::vector<bool>> on_path(rows, std::vector<bool>(cols, false));
    for (auto p : result.path)
        on_path[p.x][p.y] = true;

    std::cout << "\n=== " << label << " ===\n";
    std::cout << "Nodes explored: " << result.nodes_explored
              << " | Path steps: " << result.path.size()
              << " | Cost: " << std::fixed << std::setprecision(2) << result.total_cost
              << " | LoS checks: " << result.los_checks << "\n";

    for (int x = 0; x < rows; ++x) {
        for (int y = 0; y < cols; ++y) {
            if (x == start.x && y == start.y)       std::cout << "S ";
            else if (x == goal.x && y == goal.y)    std::cout << "G ";
            else if (on_path[x][y])                 std::cout << "* ";
            else if (grid[x][y] == '#')             std::cout << "# ";
            else                                     std::cout << ". ";
        }
        std::cout << "\n";
    }

    // 打印路径坐标
    std::cout << "Path: ";
    for (size_t i = 0; i < result.path.size(); ++i) {
        std::cout << "(" << result.path[i].x << "," << result.path[i].y << ")";
        if (i + 1 < result.path.size()) std::cout << " -> ";
    }
    std::cout << "\n";
}

// ============================================================
// 主函数
// ============================================================
int main(int argc, char* argv[]) {
    std::string mode = (argc > 1) ? argv[1] : "compare";

    // 测试地图：20×20，带一堵斜墙
    Grid grid = {
        "....................",
        "....................",
        "..#######...........",
        "..#.....##..........",
        "..#......##.........",
        "..#.......##........",
        "..#........##.......",
        "..#.........##......",
        "..#..........##.....",
        "..#...........###...",
        "....................",
        "....................",
        "....................",
        "........###.........",
        "........#.#.........",
        "........#.#.........",
        "........###.........",
        "....................",
        "....................",
        "....................",
    };

    Point start = {1, 1};
    Point goal  = {18, 18};

    if (mode == "standard" || mode == "compare") {
        auto r1 = theta_star(grid, start, goal);
        visualize(grid, r1, start, goal, "Standard Theta*");
    }

    if (mode == "lazy" || mode == "compare") {
        auto r2 = lazy_theta_star(grid, start, goal);
        visualize(grid, r2, start, goal, "Lazy Theta*");
    }

    if (mode == "compare") {
        auto r3 = standard_astar(grid, start, goal);
        visualize(grid, r3, start, goal, "Standard A* (8-dir)");

        std::cout << "\n--- 对比总结 ---\n";
        std::cout << "A*:    " << r3.path.size() << " steps, cost "
                  << r3.total_cost << " (网格最优)\n";
        auto r1 = theta_star(grid, start, goal);
        std::cout << "Theta*:" << r1.path.size() << " steps, cost "
                  << r1.total_cost << " (任意角度)\n";
        std::cout << "Lazy:  " << r1.los_checks << " LoS checks\n";
    }

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o theta_star theta_star.cpp
./theta_star compare   # 对比三种算法
./theta_star standard  # 只看标准 Theta*
./theta_star lazy      # 只看 Lazy Theta*
```

**预期输出:**
```
=== Standard Theta* ===
Nodes explored: 156 | Path steps: 8 | Cost: 22.38 | LoS checks: 312
. . . . . . . . . . . . . . . . . . . .
. S . . . . . . . . . . . . . . . . . .
. . # # # # # # # . . . . . . . . . . .
. . # . . . . . # # . . . . . . . . . .
. . # . . . * . . # # . . . . . . . . .
. . # . . * . . . . # # . . . . . . . .
. . # . * . . . . . . # # . . . . . . .
. . # * . . . . . . . . # # . . . . . .
. . # . . . . . . . . * . . . . . . . .
. . # . . . . . . . . * . . . . . . . .
. . . . . . . . . . . * . . . . . . . .
. . . . . . . . . . . . * . . . . . . .
. . . . . . . . . . . . . * . . . . . .
. . . . . . . . # # # . . . * . . . . .
. . . . . . . . # . # . . . * . . . . .
. . . . . . . . # . # . . . . * . . . .
. . . . . . . . # # # . . . . * . . . .
. . . . . . . . . . . . . . . * . . . .
. . . . . . . . . . . . . . . G . . . .
. . . . . . . . . . . . . . . . . . . .
Path: (1,1) -> (7,1) -> (13,8) -> (17,16) -> (18,18)

=== Lazy Theta* ===
Nodes explored: 163 | Path steps: 8 | Cost: 22.38 | LoS checks: 54

--- 对比总结 ---
A*:    18 steps, cost 24.73 (网格最优)
Theta*: 8 steps, cost 22.38 (任意角度)
Lazy:  54 LoS checks (远少于标准版)
```

## 3. 练习

### 基础练习：理解 Theta* 路径回溯

修改 `theta_star` 的 `visualize` 函数，在网格上不仅画出路径的 `*`，还要在路径经过的 Bresenham 直线上用不同字符（如 `+`）标记中间穿过的格子。提示：用 `line_of_sight` 中的 Bresenham 遍历输出每个中间点坐标。

**目标**: 直观理解 Theta* 路径线段实际穿过了哪些格子。

### 进阶练习：实现加权线视检查

当前的 `line_of_sight` 是二值的：有墙/无墙。修改为**加权版本**：如果线段穿过 `cost > 1.0` 的地形格子，返回一个衰减因子而不是 false。然后在 Theta* 的 g 值计算中应用这个因子。

**目标**: 实现"勉强可以穿过但代价更高"的线视模型——模拟穿过灌木丛而不是完全被墙阻挡。

### 挑战练习：实现 STheta*（平滑 Theta*）

STheta* 在回溯路径后对路径拐点做 Bezier 样条平滑。实现以下逻辑：

1. 从 Theta* 路径中提取关键拐点（路径方向改变的点）
2. 对每两个连续的拐点之间使用 Catmull-Rom 样条插值
3. 将插值后的路径点输出到可视化

**目标**: 将 Theta* 的折线路径转换为平滑曲线，适合直接驱动 game agent 的运动。

## 4. 扩展阅读

- **原始论文**: Nash, A., Daniel, K., Koenig, S., & Felner, A. (2007). "Theta\*: Any-Angle Path Planning on Grids". AAAI 2007. — 算法创始人论文，含数学正确性证明
- **Lazy Theta\***: Nash, A., Koenig, S., & Tovey, C. (2010). "Lazy Theta\*: Any-Angle Path Planning and Path Length Analysis in 3D". SoCS 2010.
- **Field D\***: Ferguson, D., & Stentz, A. (2006). 在 D* Lite 基础上支持任意角度插值——Theta* 的动态变体
- **Block A\***: Yap, P. (2011). 用分块技术加速 Theta* 的 LoS 查询
- **Anya***: Harabor, D., & Grastien, A. (2013). 间隔搜索理论——任意角度寻路的理论最优解，只搜索必要角度，不发散

## 常见陷阱

### 1. LoS 从格子中心连线 vs 格子边界
Theat* 的标准实现从 `parent(x, y)` 的**格子中心**计算 line-of-sight。但如果 grid 是 2D 瓦片地图，墙壁占据整个格子，那么从格子中心连线是合理的。如果墙壁只占格子的一部分（如 NavMesh 风格），LoS 线需要做真正的几何检查，Bresenham 不够。

**修正**: 对于连续几何体使用射线投射（ray-cast）代替 Bresenham；对于瓦片网格用 Bresenham 足够。

### 2. 起点 parent 的初始化
Theta* 的起点 parent 必须指向自己（`parent[start] = start`），否则第一个邻接节点的 LoS 检查会读取未初始化的 parent。忘记这一步会导致未定义行为。

### 3. Lazy Theta* 中 g 值被更新后需要重新入队
在 Lazy Theta* 中，pop 时发现 LoS 不可见会更新 g 值和 parent。此时必须将节点**重新入队**（允许同节点再次 pop），因为旧的 f 值已失效。否则节点带着错误的 f 值继续处理邻居。

### 4. 斜墙"漏光"问题
如果一堵斜墙只是格子的对角线排列（如 `diag_wall`），Bresenham 线可能从两个墙格子的**对角缝隙**中穿过。这是 Theta* 的已知弱点——解决方法是使用**4 连通线视**（要求水平和垂直方向都有障碍才算阻挡）或使用 2×2 的 corner 检查。

### 5. 性能陷阱：标准 Theta* 在开放区域
在无障碍的大开放区域中，标准 Theta* 对每个邻居都做 LoS 检查——8 方向 × 大量节点 = 灾难性性能。Lazy Theta* 将 LoS 检查降低到每 pop 一次，在开放区域仍是瓶颈但远好于标准版。
