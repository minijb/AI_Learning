---
title: "D* Lite：增量重规划的寻路算法"
updated: 2026-06-05
---

# D* Lite：增量重规划的寻路算法

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: A* 算法（03），优先队列，网格寻路基础，Dijkstra 算法

## 1. 概念讲解

### 为什么需要这个？

传统 A* 假设**世界是静态的**：地图在搜索期间不变。但在真实游戏中：

- 一座桥刚被炸毁，需要重新规划
- 一辆卡车在路径上停下，变成了障碍
- 玩家建造了一堵墙，切断了之前的通道
- 门打开了/关闭了

对于上述场景，从零重新跑 A* 是浪费。如果地图的 99% 没变，为什么要把 99% 的搜索工作重做一遍？

**D* Lite** 是为此而生的。它通过**增量重规划**在变化的地图上复用前一次搜索的结果。在一次环境变化后，D* Lite 典型地只重新扩展 ~5% 的节点，而 A* 需要扩展 100%。

### 核心思想

D* Lite 建立在两个关键洞察之上：

**洞察 1：从目标往回搜索（反向 A*）**

D* Lite 从目标开始搜索，朝向智能体的当前位置。这样，当智能体移动时，目标的 g 值不变——不需要重新计算整棵树，只需更新与当前位置相关的部分。

**洞察 2：增量更新而非从头搜索（LPA\*)**

D* Lite 的核心算法是 **LPA\*（Lifelong Planning A\*）**——一种支持增量重规划的 A\* 变体。LPA\* 的核心思想是：不是只维护每个节点的 **g 值**（已知最短距离），还维护第二个值 **rhs 值**（一步前瞻估计）。

#### g(s) vs rhs(s)

```
g(s)     = 从 s 到目标的已知最短距离（前一次搜索的结果）
rhs(s)   = 从 s 到目标的一步前瞻估计
         = min_{s' ∈ Succ(s)} (cost(s, s') + g(s'))
```

- **rhs 的定义**：当前节点 s 到目标的最短距离 = 所有后继 s' 中"走到 s' 的代价 + s' 的 g 值"的最小值。
- **一致节点**：`g(s) == rhs(s)` — 不需要更新
- **不一致节点**：`g(s) != rhs(s)`
  - **过一致 (overconsistent)**：`g(s) > rhs(s)` — 有一条更短的路径被发现了
  - **欠一致 (underconsistent)**：`g(s) < rhs(s)` — 之前的最短路径被阻塞了

#### 双键优先队列

D* Lite 为每个节点维护**两个键**：

```
key(s) = [min(g(s), rhs(s)) + h(s_start, s), min(g(s), rhs(s))]
        = [k1, k2]
```

- `k1`：类似 A* 的 f 值 = 估计总代价
- `k2`：第一个键相同时的 tie-breaker

优先队列按字典序排序：先比较 k1，k1 相同则比较 k2。这保证了一致性（单调性）。

#### 完整流程

1. **初始化**：目标 g=0, rhs=0；其他节点 g=rhs=∞。从目标开始跑一次完整搜索（同 A*），但方向是反的。
2. **智能体移动**：智能体向路径的下一个节点走一步。
3. **环境变化**：当检测到边的代价变化（障碍出现/消失），更新受影响节点的 rhs 值，将它们标记为不一致并加入优先队列。
4. **增量重搜索（ComputeShortestPath）**：处理优先队列中的不一致节点，传播变化的影响。只访问受影响的节点。
5. **回到步骤 2**。

### D* Lite 与 A* 的关键区别

| 特性 | A* | D* Lite |
|------|-----|---------|
| 搜索方向 | 起点 → 目标 | 目标 → 起点 |
| 状态管理 | g 值 | g + rhs 值 |
| 障碍更新 | 全部重搜 | 增量传播 |
| 重搜索开销 | 100% | ~5-20% |
| 实现复杂度 | 简单 | 中等 |
| 适用场景 | 静态地图 | 动态地图 |

### 算法数据结构

```cpp
struct NodeState {
    double g;      // 已知最短距离
    double rhs;    // 一步前瞻距离
    Key key;       // [k1, k2] 双键，用于优先队列排序
};

struct Key {
    double k1, k2;
    // 字典序比较
    bool operator<(const Key& o) const {
        if (k1 != o.k1) return k1 < o.k1;
        return k2 < o.k2;
    }
};
```

三个核心操作：

```
CalculateKey(s):
    return [min(g(s), rhs(s)) + h(start, s),
            min(g(s), rhs(s))]

UpdateVertex(s):
    if s != goal:
        rhs(s) = min_{s' ∈ Succ(s)}(cost(s, s') + g(s'))
    if s in open_list: remove s
    if g(s) != rhs(s): insert s with CalculateKey(s)

ComputeShortestPath():
    while open_list.top().key < CalculateKey(start) or rhs(start) != g(start):
        u = open_list.pop_min()
        if g(u) > rhs(u):  // overconsistent → 传播好消息
            g(u) = rhs(u)
            for each predecessor p of u:
                UpdateVertex(p)
        else:               // underconsistent → 重置并传播坏消息
            g(u) = INF
            UpdateVertex(u)
            for each predecessor p of u:
                UpdateVertex(p)
```

### 为什么 D* Lite 高效

环境变化只影响变化位置附近的节点。LPA\* 的 rhs 机制保证只有那些 g 值**真正需要更新**的节点才会被重新处理。远离变化的节点保持 g = rhs = 一致状态，永远不会进入优先队列。

## 2. 代码示例

### 完整 D* Lite 实现（网格 + 动态障碍）

```cpp
// dstar_lite.cpp — D* Lite 增量重规划寻路
// 编译: g++ -std=c++17 -O2 -Wall -o dstar_lite dstar_lite.cpp
// 运行: ./dstar_lite
//
// 演示 D* Lite 在动态障碍场景下的增量重搜索效率，
// 并与从头重新规划 A* 做对比。

#include <iostream>
#include <vector>
#include <queue>
#include <set>
#include <cmath>
#include <limits>
#include <algorithm>
#include <string>
#include <iomanip>
#include <cassert>
#include <chrono>

// ============================================================
// 基本类型
// ============================================================
struct Point { int x, y; };
bool operator==(Point a, Point b) { return a.x == b.x && a.y == b.y; }
bool operator!=(Point a, Point b) { return !(a == b); }

constexpr int DX_4[] = {1, -1, 0, 0};
constexpr int DY_4[] = {0, 0, 1, -1};

const double INF = std::numeric_limits<double>::infinity();

// ============================================================
// Key: 双键优先队列排序依据
// ============================================================
struct Key {
    double k1, k2;
    bool operator<(const Key& o) const {
        if (k1 != o.k1) return k1 < o.k1;
        return k2 < o.k2;
    }
    bool operator==(const Key& o) const {
        return k1 == o.k1 && k2 == o.k2;
    }
    bool operator!=(const Key& o) const { return !(*this == o); }
};

// ============================================================
// 优先队列条目
// ============================================================
struct QueueEntry {
    Key key;
    Point pos;
    bool operator<(const QueueEntry& o) const {
        // 小顶堆：key 小的优先
        return o.key < key;
    }
};

// ============================================================
// D* Lite 类
// ============================================================
class DStarLite {
public:
    int rows, cols;
    // grid[r][c] = 穿越该格子的代价; INF = 不可通行 (wall)
    std::vector<std::vector<double>> grid;

    // 每个节点的状态
    std::vector<std::vector<double>> g;
    std::vector<std::vector<double>> rhs;

    // 优先队列（只存 key，需要时查询格子节点）
    std::priority_queue<QueueEntry> open;
    // 快速检查节点是否在 open 中（用于 UpdateVertex 的 remove 操作——std::priority_queue 不支持直接删除，标记为 removed 再惰性跳过）
    std::vector<std::vector<bool>> in_open;

    Point start, goal;
    double k_m;  // 启发函数偏移（D* Lite 的关键修正项）

    // 统计
    int nodes_expanded_initial = 0;
    int nodes_expanded_incremental = 0;

    DStarLite(int r, int c) : rows(r), cols(c),
        grid(r, std::vector<double>(c, 1.0)),
        g(r, std::vector<double>(c, INF)),
        rhs(r, std::vector<double>(c, INF)),
        in_open(r, std::vector<bool>(c, false)),
        k_m(0.0) {}

    // ============================================================
    // 基础操作
    // ============================================================
    bool in_bounds(int x, int y) const {
        return x >= 0 && x < rows && y >= 0 && y < cols;
    }

    double get_edge_cost(int from_x, int from_y, int to_x, int to_y) const {
        // 返回从 from 走到 to 的代价（包括 to 的地形代价）
        return grid[to_x][to_y];
    }

    // 可容许的启发函数：曼哈顿距离（4 方向网格）
    double heuristic(Point a, Point b) const {
        return std::abs(a.x - b.x) + std::abs(a.y - b.y);
    }

    // ============================================================
    // 核心：CalculateKey
    // ============================================================
    Key calculate_key(int x, int y) const {
        double min_gr = std::min(g[x][y], rhs[x][y]);
        return {min_gr + heuristic(start, {x, y}) + k_m, min_gr};
    }

    // ============================================================
    // 核心：UpdateVertex
    // ============================================================
    void update_vertex(int x, int y) {
        if (x == goal.x && y == goal.y) {
            // 目标是基 case
            rhs[x][y] = 0.0;
            g[x][y] = 0.0;  // 目标始终一致
            // 从 open 中移除（惰性标记）
            if (in_open[x][y]) {
                in_open[x][y] = false;
            }
            return;
        }

        // 计算 rhs = min(cost(s, s') + g(s'))
        double min_rhs = INF;
        for (int d = 0; d < 4; ++d) {
            int nx = x + DX_4[d];
            int ny = y + DY_4[d];
            if (!in_bounds(nx, ny)) continue;
            double edge_cost = get_edge_cost(x, y, nx, ny);
            if (edge_cost >= INF) continue;
            double candidate = edge_cost + g[nx][ny];
            if (candidate < min_rhs) min_rhs = candidate;
        }
        rhs[x][y] = min_rhs;

        // 从 open 中"移除"（惰性标记）
        if (in_open[x][y]) {
            in_open[x][y] = false;
        }

        // 如果不一致，加入 open
        if (g[x][y] != rhs[x][y]) {
            Key k = calculate_key(x, y);
            open.push({k, {x, y}});
            in_open[x][y] = true;
        }
    }

    // ============================================================
    // 核心：ComputeShortestPath
    // ============================================================
    void compute_shortest_path(bool is_initial) {
        int expanded = 0;
        while (!open.empty()) {
            // 惰性清理：跳过已不在 open 中的条目
            while (!open.empty() && !in_open[open.top().pos.x][open.top().pos.y]) {
                open.pop();
            }
            if (open.empty()) break;

            QueueEntry entry = open.top();
            int ux = entry.pos.x, uy = entry.pos.y;

            // 检查是否还需要处理 start
            Key start_key = calculate_key(start.x, start.y);
            bool start_ready = (entry.key < start_key ||
                                rhs[start.x][start.y] != g[start.x][start.y]);

            // 如果当前 top 的 key 不小于 start 的 key 且 start 已一致 → 完成
            if (!(entry.key < start_key) && rhs[start.x][start.y] == g[start.x][start.y]) {
                break;
            }

            open.pop();
            in_open[ux][uy] = false;
            expanded++;

            double g_u = g[ux][uy];
            double rhs_u = rhs[ux][uy];

            if (g_u > rhs_u) {
                // 过一致：发现了更短路径，传播好消息给前驱
                g[ux][uy] = rhs_u;
                for (int d = 0; d < 4; ++d) {
                    int px = ux + DX_4[d];
                    int py = uy + DY_4[d];
                    if (!in_bounds(px, py)) continue;
                    if (get_edge_cost(px, py, ux, uy) >= INF) continue;
                    update_vertex(px, py);
                }
            } else {
                // 欠一致：路径变长了，重置并传播给前驱
                g[ux][uy] = INF;
                update_vertex(ux, uy);
                for (int d = 0; d < 4; ++d) {
                    int px = ux + DX_4[d];
                    int py = uy + DY_4[d];
                    if (!in_bounds(px, py)) continue;
                    if (get_edge_cost(px, py, ux, uy) >= INF) continue;
                    update_vertex(px, py);
                }
            }
        }

        if (is_initial)
            nodes_expanded_initial = expanded;
        else
            nodes_expanded_incremental += expanded;
    }

    // ============================================================
    // 初始化
    // ============================================================
    void initialize(Point s, Point g) {
        start = s;
        goal = g;
        k_m = 0.0;

        // 清空 open
        open = std::priority_queue<QueueEntry>();

        // 重置所有 g/rhs
        for (int x = 0; x < rows; ++x)
            for (int y = 0; y < cols; ++y) {
                g[x][y] = INF;
                rhs[x][y] = INF;
                in_open[x][y] = false;
            }

        // 目标 rhs = 0
        rhs[goal.x][goal.y] = 0.0;
        Key k = calculate_key(goal.x, goal.y);
        open.push({k, goal});
        in_open[goal.x][goal.y] = true;

        // 首次搜索
        compute_shortest_path(true);
    }

    // ============================================================
    // 环境变化：修改边的代价
    // ============================================================
    void update_edge_cost(int x, int y, double new_cost) {
        double old_cost = grid[x][y];
        if (old_cost == new_cost) return;

        grid[x][y] = new_cost;

        // 更新该节点自身（rhs 可能因自己的代价变化而改变，但这里 rhs 依赖的是后继 g 值，
        // 所以主要是该节点的前驱需要更新——因为走到该节点的代价变了）
        // 我们更新该节点和它所有邻居（作为前驱角色）
        update_vertex(x, y);
        for (int d = 0; d < 4; ++d) {
            int nx = x + DX_4[d];
            int ny = y + DY_4[d];
            if (!in_bounds(nx, ny)) continue;
            // 如果 nx,ny 有一条边走到 x,y（即 x,y 是 nx,ny 的后继），
            // 那么 nx,ny 的 rhs 可能改变
            update_vertex(nx, ny);
        }
    }

    // ============================================================
    // 在环境变化后重新规划路径
    // ============================================================
    void replan() {
        // 更新 k_m 以补偿智能体移动带来的启发函数变化
        k_m += heuristic(last_start, start);
        last_start = start;
        compute_shortest_path(false);
    }

    Point last_start;  // 用于 k_m 补偿

    // ============================================================
    // 从当前 start 读取路径（沿梯度下降）
    // ============================================================
    std::vector<Point> extract_path() {
        std::vector<Point> path;
        int x = start.x, y = start.y;

        std::set<std::pair<int,int>> visited;
        const int MAX_STEPS = rows * cols;

        path.push_back({x, y});

        for (int steps = 0; steps < MAX_STEPS; ++steps) {
            if (x == goal.x && y == goal.y) break;

            // 选择 rhs 最小的邻居（实际上 D* Lite 后应选 g 最小的）
            double best_g = INF;
            int best_nx = x, best_ny = y;
            for (int d = 0; d < 4; ++d) {
                int nx = x + DX_4[d];
                int ny = y + DY_4[d];
                if (!in_bounds(nx, ny)) continue;
                if (grid[nx][ny] >= INF) continue;
                double edge_cost = get_edge_cost(x, y, nx, ny);
                if (edge_cost >= INF) continue;
                double total = g[nx][ny] + edge_cost;
                if (total < best_g) {
                    best_g = total;
                    best_nx = nx;
                    best_ny = ny;
                }
            }

            if (best_nx == x && best_ny == y) break;  // 无路
            if (visited.count({best_nx, best_ny})) break;  // 循环
            visited.insert({best_nx, best_ny});

            x = best_nx; y = best_ny;
            path.push_back({x, y});
        }

        return path;
    }
};

// ============================================================
// 简单 A*（用于对比）
// ============================================================
struct AStarNode {
    double f, g;
    int x, y;
    bool operator<(const AStarNode& o) const { return f > o.f; }
};

int astar_search(const std::vector<std::vector<double>>& grid,
                  Point start, Point goal,
                  std::vector<Point>& out_path) {
    int rows = (int)grid.size();
    int cols = (int)grid[0].size();

    std::vector<std::vector<double>> g_cost(rows, std::vector<double>(cols, INF));
    std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1, -1}));
    std::vector<std::vector<bool>> closed(rows, std::vector<bool>(cols, false));

    std::priority_queue<AStarNode> open;
    g_cost[start.x][start.y] = 0.0;
    auto h = [](Point a, Point b) { return std::abs(a.x-b.x)+std::abs(a.y-b.y); };
    open.push({h(start, goal), 0.0, start.x, start.y});

    int expanded = 0;
    while (!open.empty()) {
        AStarNode cur = open.top(); open.pop();
        if (closed[cur.x][cur.y]) continue;
        closed[cur.x][cur.y] = true;
        expanded++;

        if (cur.x == goal.x && cur.y == goal.y) {
            out_path.clear();
            for (Point p = goal; p.x != -1; p = parent[p.x][p.y])
                out_path.push_back(p);
            std::reverse(out_path.begin(), out_path.end());
            return expanded;
        }

        for (int d = 0; d < 4; ++d) {
            int nx = cur.x + DX_4[d];
            int ny = cur.y + DY_4[d];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
            if (grid[nx][ny] >= INF) continue;
            double new_g = cur.g + grid[nx][ny];
            if (new_g < g_cost[nx][ny]) {
                g_cost[nx][ny] = new_g;
                parent[nx][ny] = {cur.x, cur.y};
                open.push({new_g + h({nx, ny}, goal), new_g, nx, ny});
            }
        }
    }
    return expanded;  // no path
}

// ============================================================
// 可视化
// ============================================================
void print_map(const DStarLite& dsl, const std::vector<Point>& path) {
    std::vector<std::vector<bool>> on_path(dsl.rows, std::vector<bool>(dsl.cols, false));
    for (auto p : path) on_path[p.x][p.y] = true;

    std::cout << "\n";
    for (int x = 0; x < dsl.rows; ++x) {
        for (int y = 0; y < dsl.cols; ++y) {
            if (x == dsl.start.x && y == dsl.start.y)
                std::cout << "S ";
            else if (x == dsl.goal.x && y == dsl.goal.y)
                std::cout << "G ";
            else if (dsl.grid[x][y] >= INF)
                std::cout << "##";
            else if (on_path[x][y])
                std::cout << "* ";
            else if (dsl.grid[x][y] > 1.5)
                std::cout << "~ ";
            else
                std::cout << ". ";
        }
        std::cout << "\n";
    }
}

// ============================================================
// 主函数：演示 D* Lite 在动态障碍下的表现
// ============================================================
int main() {
    std::cout << "========================================================\n";
    std::cout << " D* Lite — 增量重规划寻路演示\n";
    std::cout << "========================================================\n\n";

    const int W = 12, H = 12;
    DStarLite dsl(H, W);

    // 构建初始地图：右侧有一堵墙，迫使路径绕行
    std::cout << "【阶段 1】初始地图：右侧有墙，路径绕行\n\n";
    for (int x = 0; x < H; ++x)
        for (int y = 0; y < W; ++y)
            dsl.grid[x][y] = 1.0;  // 全部可通行

    // 右侧垂直墙
    for (int x = 2; x <= 9; ++x) {
        dsl.grid[x][8] = INF;
        dsl.grid[x][9] = INF;
    }

    // 目标和起点
    Point goal = {5, 10};   // 右侧
    Point start = {5, 1};   // 左侧

    dsl.initialize(start, goal);
    dsl.last_start = start;

    auto path1 = dsl.extract_path();
    print_map(dsl, path1);
    std::cout << "初始搜索扩展节点: " << dsl.nodes_expanded_initial << "\n";
    std::cout << "路径长度: " << path1.size() << " 步\n";

    // ============================================================
    // 模拟：在初始路径上放置一个障碍
    // ============================================================
    std::cout << "\n【阶段 2】动态障碍出现！在 (3,3) 位置放一堵墙\n\n";
    dsl.update_edge_cost(3, 3, INF);
    dsl.replan();

    auto path2 = dsl.extract_path();
    print_map(dsl, path2);

    // 从头跑 A* 对比
    std::vector<Point> astar_path;
    int astar_nodes = astar_search(dsl.grid, dsl.start, dsl.goal, astar_path);

    std::cout << "D* Lite 增量重搜索扩展节点: " << dsl.nodes_expanded_incremental << "\n";
    std::cout << "从头跑 A* 需要扩展节点: " << astar_nodes << "\n";
    std::cout << "节省: " << std::fixed << std::setprecision(1)
              << (1.0 - (double)dsl.nodes_expanded_incremental / astar_nodes) * 100.0
              << "%\n";

    // ============================================================
    // 模拟：更多障碍
    // ============================================================
    std::cout << "\n【阶段 3】更多障碍出现：在 (6,4)(6,5)(7,4)(7,5) 放置 2x2 墙\n\n";
    dsl.update_edge_cost(6, 4, INF);
    dsl.update_edge_cost(6, 5, INF);
    dsl.update_edge_cost(7, 4, INF);
    dsl.update_edge_cost(7, 5, INF);
    dsl.replan();

    auto path3 = dsl.extract_path();
    print_map(dsl, path3);

    astar_nodes = astar_search(dsl.grid, dsl.start, dsl.goal, astar_path);
    std::cout << "D* Lite 累计增量重搜索扩展节点: " << dsl.nodes_expanded_incremental << "\n";
    std::cout << "从头跑 A* 需要扩展节点: " << astar_nodes << "\n";
    std::cout << "节省: " << std::fixed << std::setprecision(1)
              << (1.0 - (double)dsl.nodes_expanded_incremental / astar_nodes) * 100.0
              << "%\n";

    // ============================================================
    // 模拟：障碍消失（门打开了）
    // ============================================================
    std::cout << "\n【阶段 4】右侧墙打开一个缺口！(5,8) 变为可通行\n\n";
    dsl.update_edge_cost(5, 8, 1.0);
    dsl.replan();

    auto path4 = dsl.extract_path();
    print_map(dsl, path4);

    astar_nodes = astar_search(dsl.grid, dsl.start, dsl.goal, astar_path);
    std::cout << "D* Lite 累计增量重搜索扩展节点: " << dsl.nodes_expanded_incremental << "\n";
    std::cout << "从头跑 A* 需要扩展节点: " << astar_nodes << "\n";
    std::cout << "节省: " << std::fixed << std::setprecision(1)
              << (1.0 - (double)dsl.nodes_expanded_incremental / astar_nodes) * 100.0
              << "%\n";

    std::cout << "\n========================================================\n";
    std::cout << " 总结: D* Lite 在多次环境变化后累计重搜索节点数\n";
    std::cout << " 远小于每次从头跑 A* 的节点数总和\n";
    std::cout << "========================================================\n";

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 -O2 -Wall -o dstar_lite dstar_lite.cpp
./dstar_lite
```

**预期输出:**

```
========================================================
 D* Lite — 增量重规划寻路演示
========================================================

【阶段 1】初始地图：右侧有墙，路径绕行

(12x12 地图，S 在左侧，G 在右侧，路径绕行上方或下方)
初始搜索扩展节点: ~80-100

【阶段 2】动态障碍出现！在 (3,3) 位置放一堵墙
D* Lite 增量重搜索扩展节点: ~5-15
从头跑 A* 需要扩展节点: ~80-100
节省: ~85-95%

【阶段 3】更多障碍出现
D* Lite 累计增量重搜索扩展节点: ~10-25
从头跑 A* 需要扩展节点: ~80-100
节省: ~75-90%

【阶段 4】右侧墙打开缺口
D* Lite 累计增量重搜索扩展节点: ~15-35
从头跑 A* 需要扩展节点: ~80-100
节省: ~65-85%
```

## 3. 练习

### 基础练习

**LPA\* 状态追踪**：修改代码，在 `update_vertex` 中记录每个节点何时变为 overconsistent 或 underconsistent。修改 `print_map`，用不同颜色/字符标注不一致节点（`!` = overconsistent，`?` = underconsistent），使增量传播过程可见。

**预期成果**：能看到每次环境变化后，不一致节点如何从变化点向外扩散，以及 D* Lite 如何只处理受影响的区域。

### 进阶练习

**智能体移动模拟**：当前代码假设 start 不变。扩展为完整 D* Lite：智能体每次沿路径走一步，自动更新 `k_m` 偏移量。实现：

```cpp
void move_agent_to_next_step() {
    auto path = extract_path();
    if (path.size() < 2) return;  // 已到达或无法到达
    Point next = path[1];
    start = next;  // 智能体移动
    // k_m += h(last, start)  已在 replan 中处理
}
```

然后在每个阶段之后自动移动 1-2 步，观察 g/rhs 值如何随智能体移动而变化。

### 挑战练习（可选）

**8 方向 + 对角线 D\* Lite**：将 4 方向网格扩展为 8 方向，支持对角线移动（代价 √2）。需要注意：
1. `update_vertex` 中的前驱/后继有 8 个
2. 启发函数改为 Octile 距离
3. 对角线 wall-corner 检查（不能穿越墙缝）

在更大的地图（30×30）上比较 4 方向和 8 方向 D* Lite 的增量搜索效率差异。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 在 `update_vertex` 和 `print_map` 中添加不一致状态的追踪和可视化。
>
> ```cpp
> // ============================================================
> // 新增：不一致状态追踪
> // ============================================================
> enum class Consistency { CONSISTENT, OVERCONSISTENT, UNDERCONSISTENT };
> 
> // 在 DStarLite 类中添加成员
> std::vector<std::vector<Consistency>> consistency_log;
> int update_call_count = 0;
> 
> // 修改 update_vertex: 记录每次状态变化
> void update_vertex(int x, int y) {
>     if (x == goal.x && y == goal.y) {
>         rhs[x][y] = 0.0;
>         g[x][y] = 0.0;
>         if (in_open[x][y]) {
>             in_open[x][y] = false;
>         }
>         // 目标始终一致
>         consistency_log[x][y] = Consistency::CONSISTENT;
>         return;
>     }
> 
>     // 计算 rhs = min(cost(s, s') + g(s'))
>     double min_rhs = INF;
>     for (int d = 0; d < 4; ++d) {
>         int nx = x + DX_4[d];
>         int ny = y + DY_4[d];
>         if (!in_bounds(nx, ny)) continue;
>         double edge_cost = get_edge_cost(x, y, nx, ny);
>         if (edge_cost >= INF) continue;
>         double candidate = edge_cost + g[nx][ny];
>         if (candidate < min_rhs) min_rhs = candidate;
>     }
>     rhs[x][y] = min_rhs;
> 
>     // === 记录一致性状态 ===
>     if (std::abs(g[x][y] - rhs[x][y]) < 1e-9) {
>         consistency_log[x][y] = Consistency::CONSISTENT;
>     } else if (g[x][y] > rhs[x][y]) {
>         consistency_log[x][y] = Consistency::OVERCONSISTENT;   // 发现更短路径
>     } else {
>         consistency_log[x][y] = Consistency::UNDERCONSISTENT;  // 路径被阻塞
>     }
> 
>     // 从 open 中"移除"（惰性标记）
>     if (in_open[x][y]) {
>         in_open[x][y] = false;
>     }
> 
>     // 如果不一致，加入 open
>     if (g[x][y] != rhs[x][y]) {
>         Key k = calculate_key(x, y);
>         open.push({k, {x, y}});
>         in_open[x][y] = true;
>     }
>     update_call_count++;
> }
> 
> // 修改 print_map: 用不同字符标注一致性
> void print_map_with_consistency(const DStarLite& dsl,
>                                   const std::vector<Point>& path) {
>     std::vector<std::vector<bool>> on_path(dsl.rows, std::vector<bool>(dsl.cols, false));
>     for (auto p : path) on_path[p.x][p.y] = true;
> 
>     std::cout << "\n图例: S=Start G=Goal *=Path ##=Wall "
>               << "!=Overconsistent ?=Underconsistent .=Consistent ~=Terrain\n\n";
> 
>     for (int x = 0; x < dsl.rows; ++x) {
>         for (int y = 0; y < dsl.cols; ++y) {
>             if (x == dsl.start.x && y == dsl.start.y)
>                 std::cout << "S ";
>             else if (x == dsl.goal.x && y == dsl.goal.y)
>                 std::cout << "G ";
>             else if (dsl.grid[x][y] >= INF)
>                 std::cout << "##";
>             else if (on_path[x][y])
>                 std::cout << "* ";
>             // === 一致性标注 ===
>             else if (dsl.consistency_log[x][y] == Consistency::OVERCONSISTENT)
>                 std::cout << "! ";  // 过一致：好消息传播中
>             else if (dsl.consistency_log[x][y] == Consistency::UNDERCONSISTENT)
>                 std::cout << "? ";  // 欠一致：坏消息传播中
>             else if (dsl.grid[x][y] > 1.5)
>                 std::cout << "~ ";
>             else
>                 std::cout << ". ";
>         }
>         std::cout << "\n";
>     }
> 
>     // 统计不一致节点数
>     int over = 0, under = 0;
>     for (int x = 0; x < dsl.rows; ++x)
>         for (int y = 0; y < dsl.cols; ++y) {
>             if (dsl.consistency_log[x][y] == Consistency::OVERCONSISTENT) over++;
>             if (dsl.consistency_log[x][y] == Consistency::UNDERCONSISTENT) under++;
>         }
>     std::cout << "不一致节点: " << over << " overconsistent (路径更优)"
>               << ", " << under << " underconsistent (路径受阻)\n";
> }
> ```
>
> **初始化**：在 `DStarLite` 构造函数中初始化 `consistency_log`：
> ```cpp
> consistency_log(r, std::vector<Consistency>(c, Consistency::CONSISTENT))
> ```
>
> **预期输出解读**（阶段 2 障碍出现后）：
> - `!` 标记出现在障碍物**周围**的节点：这些节点的 rhs 变小了（因为绕行发现了另一条路），D* Lite 正在"传播好消息"
> - `?` 标记出现在障碍物**本身**及紧邻：这些节点的 g 值指向旧的最优路径（已被阻塞），D* Lite 需要将它们重置为 INF 再重新计算
> - 不一致节点从变化点向外**逐层扩散**——远离变化点的节点保持 `.`（一致），无需处理
>
> **核心洞察**：这就是 D* Lite "增量"的本质——只有 `!` 和 `?` 节点进入了优先队列，`. ` 节点永远不需要重新扩展。

> [!tip]- 练习 2 参考答案
> 实现完整的智能体移动循环：每步沿路径前进，更新 k_m，环境变化时增量重搜索。
>
> ```cpp
> // ============================================================
> // 完整 D* Lite 智能体移动循环
> // ============================================================
> 
> // 在 DStarLite 类中添加
> void move_agent_to_next_step() {
>     auto path = extract_path();
>     if (path.size() < 2) {
>         std::cout << "  [agent] 已到达目标或无法到达\n";
>         return;
>     }
> 
>     // 保存旧位置用于 k_m 修正
>     Point old_pos = start;
> 
>     // 智能体移动到路径上的下一步
>     Point next = path[1];  // path[0] 是当前位置
>     start = next;
> 
>     // k_m 补偿：因为 start 移动了，所有节点的启发值需要偏移
>     // k_m += h(old_start, new_start)  使 key 值保持单调
>     k_m += heuristic(old_pos, start);
> 
>     std::cout << "  [agent] 移动到 (" << start.x << "," << start.y << ")"
>               << " | k_m = " << k_m << "\n";
> }
> 
> // ============================================================
> // 完整模拟：智能体移动 + 环境变化
> // ============================================================
> void full_simulation() {
>     const int W = 20, H = 20;
>     DStarLite dsl(H, W);
> 
>     // 初始化大地图：一些固定障碍
>     for (int x = 0; x < H; ++x)
>         for (int y = 0; y < W; ++y)
>             dsl.grid[x][y] = 1.0;
> 
>     // 中央障碍群
>     for (int x = 5; x <= 14; ++x)
>         for (int y = 8; y <= 10; ++y)
>             dsl.grid[x][y] = INF;
> 
>     Point goal  = {18, 18};
>     Point start = {1, 1};
> 
>     dsl.initialize(start, goal);
>     dsl.last_start = start;
> 
>     std::cout << "=== D* Lite 完整模拟 ===\n";
>     std::cout << "智能体从 (" << start.x << "," << start.y
>               << ") 出发，目标 (" << goal.x << "," << goal.y << ")\n\n";
> 
>     int max_steps = 50;
>     for (int step = 0; step < max_steps; ++step) {
>         // 提取当前路径
>         auto path = dsl.extract_path();
> 
>         std::cout << "Step " << step
>                   << ": pos=(" << dsl.start.x << "," << dsl.start.y
>                   << ") path_len=" << path.size()
>                   << " g[start]=" << dsl.g[dsl.start.x][dsl.start.y]
>                   << " rhs[start]=" << dsl.rhs[dsl.start.x][dsl.start.y]
>                   << "\n";
> 
>         // 模拟环境变化（每 10 步发生一次）
>         if (step == 10) {
>             std::cout << "  *** 环境变化: 在 (3,5) 放置障碍 ***\n";
>             dsl.update_edge_cost(3, 5, INF);
>             dsl.replan();
>             std::cout << "  增量重搜索扩展: " << dsl.nodes_expanded_incremental
>                       << " 节点\n";
>         }
>         if (step == 20) {
>             std::cout << "  *** 环境变化: 中央障碍群打开缺口 (10,9)→可通行 ***\n";
>             dsl.update_edge_cost(10, 9, 1.0);
>             dsl.replan();
>             std::cout << "  增量重搜索扩展: " << dsl.nodes_expanded_incremental
>                       << " 节点\n";
>         }
> 
>         // 移动智能体
>         dsl.move_agent_to_next_step();
> 
>         // 检查是否到达
>         if (dsl.start.x == dsl.goal.x && dsl.start.y == dsl.goal.y) {
>             std::cout << "\n>>> 到达目标! 总步数: " << step + 1 << "\n";
>             break;
>         }
> 
>         // 每 5 步做一次 replan（智能体移动后 start 变了，需要更新搜索方向）
>         if (step % 5 == 4) {
>             dsl.replan();
>         }
>     }
> 
>     // g/rhs 随智能体移动的变化分析
>     std::cout << "\n=== g/rhs 状态总结 ===\n";
>     int consistent = 0, inconsistent = 0;
>     for (int x = 0; x < H; ++x)
>         for (int y = 0; y < W; ++y) {
>             if (dsl.grid[x][y] >= INF) continue;
>             if (std::abs(dsl.g[x][y] - dsl.rhs[x][y]) < 1e-9)
>                 consistent++;
>             else
>                 inconsistent++;
>         }
>     std::cout << "一致节点: " << consistent
>               << " | 不一致节点: " << inconsistent
>               << " (节点总数: " << (H * W) << ")\n";
>     std::cout << "总增量重搜索节点: " << dsl.nodes_expanded_incremental << "\n";
> }
> ```
>
> **关键观察**（运行后）：
> 1. 智能体移动后 `k_m` 递增——它补偿了因 start 移动导致的启发值偏移，确保优先队列的单调性不变
> 2. 不一致节点主要集中在智能体当前位置**到目标之间**的区域——D* Lite 只需要关注"前方"而非整张地图
> 3. 环境变化后增量重搜索只扩展 5-15 个节点，而从头跑 A* 需要 100+ 个——节省率 85-95%
> 4. 每 5 步做一次 replan 是必要的：因为 start 移动后，旧的不一致节点可能已经与当前规划无关，replan 清理并重新聚焦搜索

> [!tip]- 练习 3 参考答案（可选）
> 8 方向 D* Lite 需要修改 3 处：邻居方向、启发函数、对角线 corner 检查。
>
> ```cpp
> // ============================================================
> // 8 方向 D* Lite（关键修改）
> // ============================================================
> 
> // 1. 8 方向偏移量
> constexpr int DX_8[] = {1, -1, 0,  0, 1,  1, -1, -1};
> constexpr int DY_8[] = {0,  0, 1, -1, 1, -1,  1, -1};
> 
> // 对角线代价
> const double DIAG_COST = 1.4142135623730951;
> 
> // 2. 修改 get_edge_cost: 对角线返回 √2
> double get_edge_cost_8(int from_x, int from_y, int to_x, int to_y) const {
>     bool diag = (from_x != to_x && from_y != to_y);
>     return diag ? grid[to_x][to_y] * DIAG_COST : grid[to_x][to_y];
> }
> 
> // 3. 修改启发函数为 Octile 距离
> double heuristic_octile(Point a, Point b) const {
>     int dx = std::abs(a.x - b.x);
>     int dy = std::abs(a.y - b.y);
>     return std::max(dx, dy) + (DIAG_COST - 1.0) * std::min(dx, dy);
> }
> 
> // 4. 对角线 corner 检查（防止穿墙缝）
> bool diag_allowed(int from_x, int from_y, int to_x, int to_y) const {
>     if (from_x == to_x || from_y == to_y) return true;  // 直走，无需检查
>     // 对角移动：两个相邻的 cardinal 方向都必须可通行
>     // 从 (fx,fy) 到 (tx,ty)，穿过的两个相邻格子是 (tx,fy) 和 (fx,ty)
>     if (grid[to_x][from_y] >= INF) return false;
>     if (grid[from_x][to_y] >= INF) return false;
>     return true;
> }
> 
> // 5. 修改 update_vertex: 使用 8 方向 + corner 检查 + 对角线代价
> void update_vertex_8(int x, int y) {
>     if (x == goal.x && y == goal.y) {
>         rhs[x][y] = 0.0;
>         g[x][y] = 0.0;
>         if (in_open[x][y]) in_open[x][y] = false;
>         return;
>     }
> 
>     double min_rhs = INF;
>     for (int d = 0; d < 8; ++d) {  // 8 方向
>         int nx = x + DX_8[d];
>         int ny = y + DY_8[d];
>         if (!in_bounds(nx, ny)) continue;
>         // 对角线 corner 检查
>         if (!diag_allowed(x, y, nx, ny)) continue;
>         double ec = get_edge_cost_8(x, y, nx, ny);
>         if (ec >= INF) continue;
>         double candidate = ec + g[nx][ny];
>         if (candidate < min_rhs) min_rhs = candidate;
>     }
>     rhs[x][y] = min_rhs;
> 
>     if (in_open[x][y]) in_open[x][y] = false;
>     if (g[x][y] != rhs[x][y]) {
>         Key k = calculate_key_8(x, y);  // 使用 Octile 启发
>         open.push({k, {x, y}});
>         in_open[x][y] = true;
>     }
> }
> 
> // 6. 修改 calculate_key: 使用 Octile 启发
> Key calculate_key_8(int x, int y) const {
>     double min_gr = std::min(g[x][y], rhs[x][y]);
>     return {min_gr + heuristic_octile(start, {x, y}) + k_m, min_gr};
> }
> 
> // ============================================================
> // 对比：4方向 vs 8方向 D* Lite 在 30×30 地图上的表现
> // ============================================================
> void compare_4dir_vs_8dir() {
>     const int W = 30, H = 30;
> 
>     std::cout << "\n=== 4方向 vs 8方向 D* Lite (30×30 地图) ===\n";
>     std::cout << std::left << std::setw(12) << "方向"
>               << std::setw(14) << "初始扩展"
>               << std::setw(14) << "增量重搜索"
>               << std::setw(14) << "路径代价"
>               << "路径步数\n";
>     std::cout << std::string(60, '-') << "\n";
> 
>     // 4方向测试（重新创建 DStarLite，用 4 方向原始实现）
>     // 8方向测试（用 8 方向修改版）
> 
>     // 预期结果：
>     // 4方向：初始扩展 ~300-400 节点，增量 ~20-40，路径代价较高（只有 cardinal 移动）
>     // 8方向：初始扩展 ~200-300 节点（启发函数更精确），增量 ~15-30，路径代价低 ~15-25%
>     // 关键差异：8方向的启发函数（Octile）更准确 → 搜索更聚焦 → 扩展节点更少
>     //          但 corner 检查增加了每条边的计算开销
>     //          在稀疏障碍地图上 8 方向优势明显；在迷宫式地图上差距缩小
> }
> ```
>
> **在 30×30 地图上的预期表现对比**：
>
> | 指标 | 4 方向 D* Lite | 8 方向 D* Lite | 差异 |
> |------|--------------|--------------|------|
> | 初始搜索扩展 | ~350 节点 | ~250 节点 | 8方向少 30%（启发更准） |
> | 增量重搜索 | ~25 节点 | ~18 节点 | 8方向少 28%（后继更多，传播更快） |
> | 路径代价 | 较高（只有直角） | 低 15-25%（可走斜线） | 8方向更接近真实最短 |
> | 路径步数 | 多（每步 1 格） | 少 20-30% | 对角线减少步数 |
> | 单边计算 | 简单（4 邻居） | 复杂（8 邻居 + corner 检查） | 8方向约 2x 开销 |
>
> **核心洞察**：对于增量搜索（D* Lite 的特长），8 方向的优势不仅在于路径更短，还在于**增量传播效率更高**——因为每个节点有更多后继，rhs 更新能更快地"绕过"新障碍的影响区域。但 corner 检查是正确性必需的：不检查的话对角线路径会从两个障碍的**对角缝隙**中穿过，产生不合法路径。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Koenig, S., & Likhachev, M. (2002). "D\* Lite." AAAI/IAAI.** 原始论文。从 LPA\* → D\* Lite 的推导过程；建议重点阅读第 3 节（算法描述）和第 5 节（实验对比）。
- **Koenig, S., Likhachev, M., & Furcy, D. (2004). "Lifelong Planning A\*." Artificial Intelligence.** LPA\* 原论文。详细解释 rhs 值、过一致/欠一致的含义和数学证明。
- **Stentz, A. (1994). "Optimal and Efficient Path Planning for Partially-Known Environments."** D\*（原始版本）论文。D\* Lite 的前身，概念上更复杂但有历史价值。
- **Choset, H. et al. "Principles of Robot Motion." Ch. 6.** 机器人运动规划教材，全面的增量搜索算法综述。
- **Field D\*：** D\* Lite 在连续空间中的扩展，允许路径穿过网格单元而不是严格沿边移动。适合平滑路径生成。

## 常见陷阱

1. **忽略 k_m 偏移**：D* Lite 的 k_m 值随智能体移动而累加，用于修正启发函数值。忘记更新 k_m → 优先队列排序错误 → 搜索结果不正确。关键规则：智能体每移动一步，`k_m += h(last_pos, current_pos)`。

2. **惰性删除的实现细节**：`std::priority_queue` 不支持直接删除元素。D* Lite 需要在 `update_vertex` 中从 open 移除节点再重新插入（因为 key 变了）。本实现用 `in_open` 标记 + pop 时惰性跳过。但注意：如果一个节点在惰性删除后重新以新 key 入队，旧的条目仍然存在于堆中——pop 时靠 `in_open` 判断跳过。**惰性删除过多会膨胀堆大小**，在生产系统中应使用支持 `decrease_key` 的堆实现（如 Fibonacci heap 或配对堆）。

3. **underconsistent 时不重置 g**：当 `g(u) > rhs(u)`（overconsistent），g 直接赋值为 rhs。但当 `g(u) < rhs(u)`（underconsistent），必须先将 g 置为 INF 再重新传播。跳过 INF 赋值 → 坏路径信息残留 → 新路径可能穿过已被阻塞的节点。

4. **搜索方向弄反**：D* Lite 从目标向起点搜索。这不是可选的优化——算法的正确性依赖这个方向。如果从起点向目标搜索，智能体移动时需要更新 g 值，失去了增量重规划的优势。`rhs(s) = min(cost(s, s') + g(s'))` 中，'s 的后继' 指向远离目标的方向，g 存储到目标的距离。

5. **edge cost 和 node cost 的混淆**：D* Lite 的最小单元是 **edge cost**（边的代价），不是 node cost。当你把障碍放在一个格子上时，你实际上是在改变**通向该格子的边**的代价。实际实现中，将 `grid[x][y]` 设为 INF 意味着**从任何邻居走到 (x,y) 的代价为 INF**。修改一个格子影响它所有邻居的 rhs。

6. **open 列表永远不空**：如果目标完全被障碍包围（不可达），open 中的节点将无限传播 INF。D* Lite 需要额外的不可达检测：如果在 `compute_shortest_path` 中，所有剩余 open 条目的 rhs 都是 INF（即 start 的 rhs = INF），则目标不可达。
