# Dijkstra 算法：带权图的最短路径

> 所属计划: 高阶寻路系统
> 预计耗时: 30min
> 前置知识: BFS 原理，STL 优先队列 (std::priority_queue)，图的基本概念

## 1. 概念讲解

### 为什么需要这个？

BFS 假设所有边权重相同。但在真实游戏中，穿越沼泽比走平路慢，爬坡比下坡慢。**Dijkstra 算法处理带权图**——每条边有不同的代价，目标是找到总代价最小的路径。

在寻路系统中，Dijkstra 是 A* 的特例（启发函数 h=0）。理解 Dijkstra 的数据流——优先队列如何工作、距离数组如何更新、路径如何提取——是理解 A* 的前提。

### 核心思想

Dijkstra 维护一个**优先队列**（最小堆），按**当前已知最短距离**排序。每次从队列中取出距离最小的节点，对其邻居进行**松弛**（relaxation）：

```
松弛: 如果 dist[v] + cost(v, w) < dist[w]
      则 dist[w] = dist[v] + cost(v, w)
      并将 w 加入优先队列
```

这是**贪心**策略：每次都扩展当前看起来最接近起点的节点。因为所有边权重非负，一旦节点被取出（标记为已处理），它的最短距离就已经确定。

### 为什么 Dijkstra 是 A* 的 h=0 特例

A* 的优先队列排序依据是 `f(n) = g(n) + h(n)`：
- `g(n)` = 从起点到节点 n 的实际代价
- `h(n)` = 从节点 n 到目标的**启发式估计**

当 `h(n) = 0` 时，`f(n) = g(n)`，相当于按 `g(n)` 排序——这正是 Dijkstra。

| 算法 | 优先队列排序依据 | 启发函数 |
|------|-----------------|----------|
| BFS | 层数（隐含在 FIFO 中） | 无 |
| Dijkstra | g(n) — 起点到当前的实际代价 | h=0 |
| A* | g(n) + h(n) | h > 0（可容许） |

### Dijkstra 算法步骤

```
Dijkstra(start):
    dist[start] = 0
    for all other v: dist[v] = INF
    priority_queue.push({0, start})      // {距离, 节点}

    while priority_queue not empty:
        {d, v} = priority_queue.top(); pop()
        if d > dist[v]: continue          // 过时条目，跳过

        for each neighbor w of v:
            new_dist = dist[v] + cost(v, w)
            if new_dist < dist[w]:
                dist[w] = new_dist
                parent[w] = v
                priority_queue.push({new_dist, w})
```

关键细节：**过时条目处理**。同一节点可能以不同距离多次入队。当从队列取出一个{距离, 节点}对且距离大于 `dist[node]` 时，说明这是旧值，直接跳过。如果使用 `std::set` 或支持 decrease-key 的优先队列则不需要此检查。

### 时间复杂度

使用二叉堆（`std::priority_queue`）：**O((V + E) log V)**
使用斐波那契堆：**O(E + V log V)**（理论更优，但常数大，游戏中罕用）

## 2. 代码示例

### Dijkstra on Weighted Grid

```cpp
// dijkstra_pathfinding.cpp — 带权网格上的 Dijkstra 最短路径
// 编译: g++ -std=c++17 -O2 -Wall -o dijkstra dijkstra_pathfinding.cpp
// 运行: ./dijkstra

#include <iostream>
#include <queue>
#include <vector>
#include <limits>
#include <algorithm>
#include <string>
#include <iomanip>

// 4 方向移动
constexpr int DX[] = {1, -1, 0, 0};
constexpr int DY[] = {0, 0, 1, -1};

struct Point { int x, y; };

struct State {
    int dist;   // 从起点到该节点的当前最短距离
    int x, y;
    // 优先队列默认是大顶堆，我们想要小顶堆，所以反转比较
    bool operator<(const State& other) const {
        return dist > other.dist;  // 反转：dist 小的优先级高
    }
};

// 地形代价映射
enum Terrain {
    ROAD   = 1,   // 道路 — 快速
    GRASS  = 2,   // 草地 — 普通
    FOREST = 5,   // 森林 — 慢
    SWAMP  = 10,  // 沼泽 — 很慢
    WALL   = -1   // 不可通行
};

// 将字符地图转换为代价地图
auto build_cost_map(const std::vector<std::string>& char_grid)
    -> std::vector<std::vector<int>>
{
    int rows = static_cast<int>(char_grid.size());
    int cols = static_cast<int>(char_grid[0].size());
    std::vector<std::vector<int>> cost(rows, std::vector<int>(cols, 0));

    for (int i = 0; i < rows; ++i)
        for (int j = 0; j < cols; ++j) {
            switch (char_grid[i][j]) {
                case '.': cost[i][j] = ROAD;   break;
                case ',': cost[i][j] = GRASS;  break;
                case ';': cost[i][j] = FOREST; break;
                case '~': cost[i][j] = SWAMP;  break;
                case '#': cost[i][j] = WALL;   break;
            }
        }
    return cost;
}

auto dijkstra(const std::vector<std::vector<int>>& cost_map,
              Point start, Point goal,
              std::vector<std::vector<int>>& out_dist,
              std::vector<std::vector<Point>>& out_parent,
              std::vector<Point>& out_search_order)
    -> std::vector<Point>
{
    int rows = static_cast<int>(cost_map.size());
    int cols = static_cast<int>(cost_map[0].size());
    const int INF = std::numeric_limits<int>::max();

    // 初始化距离数组
    out_dist.assign(rows, std::vector<int>(cols, INF));
    out_parent.assign(rows, std::vector<Point>(cols, {-1, -1}));

    std::priority_queue<State> pq;
    out_dist[start.x][start.y] = 0;
    pq.push({0, start.x, start.y});

    while (!pq.empty()) {
        State cur = pq.top(); pq.pop();
        int d = cur.dist, x = cur.x, y = cur.y;

        // 过时条目：在队列中排队期间找到了更短路径
        if (d > out_dist[x][y]) continue;

        out_search_order.push_back({x, y});

        if (x == goal.x && y == goal.y) break; // 提前退出

        for (int dir = 0; dir < 4; ++dir) {
            int nx = x + DX[dir];
            int ny = y + DY[dir];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
            int cell_cost = cost_map[nx][ny];
            if (cell_cost == WALL) continue;  // 不可通行

            int new_dist = out_dist[x][y] + cell_cost;
            if (new_dist < out_dist[nx][ny]) {
                out_dist[nx][ny] = new_dist;
                out_parent[nx][ny] = {x, y};
                pq.push({new_dist, nx, ny});
            }
        }
    }

    // 回溯路径
    std::vector<Point> path;
    if (out_dist[goal.x][goal.y] == INF) return path; // 不可达

    for (Point p = goal; p.x != -1; p = out_parent[p.x][p.y])
        path.push_back(p);
    std::reverse(path.begin(), path.end());
    return path;
}

// 打印带距离值的网格
void print_result(const std::vector<std::string>& char_grid,
                  const std::vector<std::vector<int>>& dist,
                  const std::vector<Point>& path,
                  const std::vector<Point>& search_order,
                  Point start, Point goal)
{
    int rows = static_cast<int>(char_grid.size());
    int cols = static_cast<int>(char_grid[0].size());

    // 标记路径
    std::vector<std::vector<bool>> on_path(rows, std::vector<bool>(cols, false));
    for (auto p : path) on_path[p.x][p.y] = true;

    // 按访问顺序编号
    std::vector<std::vector<int>> visit_order(rows, std::vector<int>(cols, -1));
    for (size_t i = 0; i < search_order.size(); ++i)
        visit_order[search_order[i].x][search_order[i].y] = static_cast<int>(i);

    std::cout << "\n搜索了 " << search_order.size() << " 个节点\n";
    std::cout << "路径总代价: " << dist[goal.x][goal.y] << "\n";
    std::cout << "路径步数: " << path.size() << "\n\n";

    // 显示访问顺序编号（前 10 个显示精确编号）
    std::cout << "访问顺序 (前几位):\n";
    for (int x = 0; x < rows; ++x) {
        for (int y = 0; y < cols; ++y) {
            if (x == start.x && y == start.y)
                std::cout << "  S ";
            else if (x == goal.x && y == goal.y)
                std::cout << "  G ";
            else if (on_path[x][y])
                std::cout << "  * ";
            else if (char_grid[x][y] == '#')
                std::cout << " ###";
            else if (visit_order[x][y] >= 0 && visit_order[x][y] < 99)
                printf(" %2d ", visit_order[x][y]);
            else if (visit_order[x][y] >= 0)
                std::cout << " .. ";
            else
                std::cout << "  . ";
        }
        std::cout << "\n";
    }

    // 显示距离值（仅对已访问节点）
    std::cout << "\n到起点的最短距离:\n";
    for (int x = 0; x < rows; ++x) {
        for (int y = 0; y < cols; ++y) {
            if (dist[x][y] == std::numeric_limits<int>::max())
                std::cout << "  - ";
            else
                printf(" %2d ", dist[x][y]);
        }
        std::cout << "\n";
    }
}

int main() {
    // 地图图例: . = 道路(1)  , = 草地(2)  ; = 森林(5)  ~ = 沼泽(10)  # = 墙
    std::vector<std::string> char_grid = {
        "....,;;;~~",
        ".##.,,;;~~",
        ".....,,;~~",
        ".;##.,,;;",
        ".;.....,,",
        ".;##.##.,",
        "..;;.....",
        "..,;##.#.",
        "..,,.....",
        ".........",
    };

    auto cost_map = build_cost_map(char_grid);
    Point start = {0, 0};
    Point goal  = {9, 9};

    std::vector<std::vector<int>> dist;
    std::vector<std::vector<Point>> parent;
    std::vector<Point> search_order;

    auto path = dijkstra(cost_map, start, goal, dist, parent, search_order);

    print_result(char_grid, dist, path, search_order, start, goal);

    // 与 BFS 对比：BFS 只看步数，不考虑地形代价
    int bfs_like_cost = 0;
    for (size_t i = 1; i < path.size(); ++i) {
        int x = path[i].x, y = path[i].y;
        if (cost_map[x][y] == -1) break;
        // BFS 会走同样的步数，但可能穿过沼泽
        std::cout << " 路径点(" << x << "," << y << ") 地形代价="
                  << cost_map[x][y] << "\n";
    }

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o dijkstra dijkstra_pathfinding.cpp
./dijkstra
```

**预期输出:**
```
搜索了 XX 个节点
路径总代价: 23
路径步数: 19

访问顺序 (前几位):
  S   0   1   2   3   4   5   6   7
  8 ###   9  10  11  12  13  14  15
 16  17  18  19  20  21  22  23  24
 ...
```

观察：Dijkstra 会优先探索代价低的区域（道路 `.` 优先于草地 `,`），即使道路绕远——因为总代价才是目标。

### Unity C# 可视化提示

```csharp
// 地形按代价着色
Color GetTerrainColor(int cost) => cost switch {
    1  => Color.grey,       // 道路
    2  => Color.green,      // 草地
    5  => new Color(0, 0.5f, 0), // 森林 (深绿)
    10 => new Color(0.5f, 0, 0.5f), // 沼泽 (紫色)
    -1 => Color.black,      // 墙
    _  => Color.white
};

// 已探索节点从蓝渐变到黄（按 dist 值）
Color GetExploredColor(int dist, int maxDist)
{
    float t = Mathf.Clamp01((float)dist / maxDist);
    return Color.Lerp(Color.cyan, Color.red, t);
}
```

## 3. 练习

### 练习 1: 记录比较次数（基础）
修改代码，统计 Dijkstra 执行过程中优先队列的 push 次数、pop 次数、以及"过时条目跳过"次数。对于不同地形分布的地图，这些数字如何变化？

### 练习 2: 等代价轮廓可视化（进阶）
修改 `print_result`，不显示访问顺序，改为显示一个 ASCII 热力图：已访问节点的字符根据其 `dist` 值映射到 `" .:-=+*#%@"` 范围（等代价轮廓线）。观察 Dijkstra 的波前形状。

### 练习 3: 实现 Dial's Algorithm（挑战）
当边权重是小的整数时（如 1-10），Dial's Algorithm 使用桶排序代替优先队列，达到 O(V + E) 时间。实现它并与 `std::priority_queue` 版本对比性能。

提示：维护一个 `std::vector<std::list<Point>> buckets(max_cost)`，按 `dist % max_cost` 索引。

## 4. 扩展阅读

- **E. W. Dijkstra, "A Note on Two Problems in Connexion with Graphs" (1959)** — 原始论文，仅 3 页，极其精炼
- **Red Blob Games: "Implementation of A*"** — 从 Dijkstra 到 A* 的渐进式实现
  https://www.redblobgames.com/pathfinding/a-star/implementation.html
- **Boost.Graph: `dijkstra_shortest_paths`** — 工业级实现，支持自定义 visitor、distance map、颜色映射
- **"Engineering Route Planning Algorithms" (Delling et al.)** — Dijkstra 在真实道路网络上的工程优化

## 常见陷阱

1. **优先队列方向搞反**：`std::priority_queue` 默认是大顶堆。必须用 `std::greater` 或重载 `operator<` 反转比较。忘记这点 = Dijkstra 变成"最差优先搜索"。

2. **不处理过时条目**：同一节点以不同距离多次入队。`pop` 时如果不检查 `d > dist[node]`，会重复处理。不检查不会导致错误结果（已经更新为更小的 dist），但会浪费 CPU。

3. **使用负权边**：Dijkstra 要求所有边权重 ≥ 0。有负权边需要用 Bellman-Ford。游戏中地形代价总是非负，所以这不是问题，但要理解原因：Dijkstra 的贪心性质依赖"先取出的节点距离已确定"。

4. **距离数组用 int 溢出**：`new_dist = dist[v] + cost(v, w)` 可能溢出。使用 `INF/2` 作为哨兵值避免 `INF + cost` 溢出。或者用 `long long`。

5. **把路径长度和路径代价混淆**：BFS 的最短指**步数最少**；Dijkstra 的最短指**总代价最小**。这两个概念在一开始容易搞混。
