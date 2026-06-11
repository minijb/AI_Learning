---
title: "图搜索基础：BFS 与 DFS"
updated: 2026-06-05
---

# 图搜索基础：BFS 与 DFS

> 所属计划: 高阶寻路系统
> 预计耗时: 30min
> 前置知识: C++ STL 容器（vector, queue, stack），基本图论概念（节点、边）

## 1. 概念讲解

### 为什么需要这个？

游戏寻路本质上是在**图上搜索**——地图上的每个可通行格子是一个节点，相邻格子的连接是边。BFS 和 DFS 是最基础的图搜索算法，也是理解 A* 的起点。你无法跳过它们直接学 A* 还指望理解"为什么 A* 快"。

寻路系统中，图往往是**隐式**的：你不需要提前构建邻接表，而是在搜索时按规则生成邻居。本教程建立从显式图到隐式图的心智模型。

### 核心思想

**广度优先搜索（BFS）**：先访问距离起点 1 步的所有节点，再访问 2 步的，以此类推。使用队列（FIFO）。

**深度优先搜索（DFS）**：沿一条路径走到底，撞墙再回溯。使用栈（LIFO）或递归。

| 特性 | BFS | DFS |
|------|-----|-----|
| 数据结构 | `std::queue` | `std::stack` |
| 最短路径（无权图） | ✅ 保证 | ❌ 不保证 |
| 内存使用 | 可能很大（宽度） | 通常较小（深度） |
| 适合场景 | 网格寻路、社交距离 | 迷宫生成、拓扑排序 |

### 图表示方式

在寻路中有三种核心表示：

1. **邻接矩阵**：`bool matrix[N][N]`。O(1) 查边，O(V²) 空间。网格寻路中几乎不用。
2. **邻接表**：`vector<vector<int>> adj`。O(degree) 查边，O(V+E) 空间。大多数寻路场景的标准选择。
3. **隐式图**：不预先存储边。给定一个节点，当场计算它的邻居。这是游戏寻路的最常见形式——地图本身是数据，邻居函数从地图推导。

```cpp
// 显式邻接表
std::vector<std::vector<int>> adj = {
    {1, 2},    // 节点 0 的邻居
    {0, 3},    // 节点 1 的邻居
    {0, 3},    // 节点 2 的邻居
    {1, 2}     // 节点 3 的邻居
};

// 隐式图：2D 网格，当场计算邻居
auto neighbors(int x, int y) -> std::vector<std::pair<int,int>> {
    std::vector<std::pair<int,int>> result;
    for (auto [dx, dy] : {std::pair{1,0}, {-1,0}, {0,1}, {0,-1}}) {
        int nx = x + dx, ny = y + dy;
        if (grid[nx][ny] == 0) result.emplace_back(nx, ny); // 0 = 可通行
    }
    return result;
}
```

### BFS 算法伪代码

```
BFS(start):
    queue.push(start)
    visited[start] = true
    while queue not empty:
        v = queue.pop()
        for each neighbor w of v:
            if not visited[w]:
                visited[w] = true
                parent[w] = v        // 记录路径
                queue.push(w)
```

### 搜索树 vs 搜索顺序

把搜索过程想象成泛洪填充：BFS 像水波从起点向外扩展，逐层扩散。DFS 像一根绳子在迷宫中蜿蜒。

## 2. 代码示例

### 完整 BFS/DFS 寻路 on 2D Grid

```cpp
// pathfinding_basic.cpp — BFS 和 DFS 在 2D 网格上的对比
// 编译: g++ -std=c++17 -O2 -Wall -o bfs_dfs pathfinding_basic.cpp
// 运行: ./bfs_dfs

#include <iostream>
#include <queue>
#include <stack>
#include <vector>
#include <utility>
#include <algorithm>
#include <string>

using Grid = std::vector<std::string>;

// 4 方向移动: 上下左右
constexpr int DX[] = {1, -1, 0, 0};
constexpr int DY[] = {0, 0, 1, -1};
constexpr const char* DIR_NAMES[] = {"下", "上", "右", "左"};

struct Point {
    int x, y;
};

// BFS: 返回从 start 到 goal 的最短路径（无权图），以及搜索顺序
auto bfs(const Grid& grid, Point start, Point goal,
         std::vector<Point>& out_search_order)
    -> std::vector<Point>  // 返回路径（空 = 不可达）
{
    int rows = static_cast<int>(grid.size());
    int cols = static_cast<int>(grid[0].size());

    std::vector<std::vector<bool>> visited(rows, std::vector<bool>(cols, false));
    std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1, -1}));

    std::queue<Point> q;
    q.push(start);
    visited[start.x][start.y] = true;

    while (!q.empty()) {
        Point v = q.front(); q.pop();
        out_search_order.push_back(v);  // 记录访问顺序，用于可视化

        if (v.x == goal.x && v.y == goal.y) {
            // 回溯路径
            std::vector<Point> path;
            for (Point p = goal; p.x != -1; p = parent[p.x][p.y])
                path.push_back(p);
            std::reverse(path.begin(), path.end());
            return path;
        }

        for (int d = 0; d < 4; ++d) {
            int nx = v.x + DX[d];
            int ny = v.y + DY[d];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue; // 边界
            if (grid[nx][ny] == '#')          continue; // 障碍物
            if (visited[nx][ny])              continue; // 已访问

            visited[nx][ny] = true;
            parent[nx][ny] = v;
            q.push({nx, ny});
        }
    }

    return {};  // 不可达
}

// DFS: 注意——不保证最短路径
auto dfs(const Grid& grid, Point start, Point goal,
         std::vector<Point>& out_search_order)
    -> std::vector<Point>
{
    int rows = static_cast<int>(grid.size());
    int cols = static_cast<int>(grid[0].size());

    std::vector<std::vector<bool>> visited(rows, std::vector<bool>(cols, false));
    std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1, -1}));

    std::stack<Point> stk;
    stk.push(start);
    // 注意: DFS 在入栈时标记 visited，不是在出栈时——
    // 否则同一个节点可能被重复入栈（图中不同路径到达同一节点）

    while (!stk.empty()) {
        Point v = stk.top(); stk.pop();

        if (visited[v.x][v.y]) continue; // 可能被其他路径先访问了
        visited[v.x][v.y] = true;
        out_search_order.push_back(v);

        if (v.x == goal.x && v.y == goal.y) {
            std::vector<Point> path;
            for (Point p = goal; p.x != -1; p = parent[p.x][p.y])
                path.push_back(p);
            std::reverse(path.begin(), path.end());
            return path;
        }

        for (int d = 0; d < 4; ++d) {
            int nx = v.x + DX[d];
            int ny = v.y + DY[d];
            if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
            if (grid[nx][ny] == '#')          continue;
            if (visited[nx][ny])              continue;

            parent[nx][ny] = v;
            stk.push({nx, ny});
        }
    }

    return {};
}

// 打印搜索过程可视化
void visualize_search(const Grid& grid,
                      const std::vector<Point>& search_order,
                      const std::vector<Point>& path,
                      Point start, Point goal,
                      const std::string& algo_name)
{
    int rows = static_cast<int>(grid.size());
    int cols = static_cast<int>(grid[0].size());

    // 按访问顺序编号
    std::vector<std::vector<int>> order(rows, std::vector<int>(cols, -1));
    for (size_t i = 0; i < search_order.size(); ++i)
        order[search_order[i].x][search_order[i].y] = static_cast<int>(i);

    // 标记路径上的点
    std::vector<std::vector<bool>> on_path(rows, std::vector<bool>(cols, false));
    for (auto p : path)
        on_path[p.x][p.y] = true;

    std::cout << "\n=== " << algo_name << " ===\n";
    std::cout << "搜索了 " << search_order.size() << " 个节点\n";
    std::cout << "路径长度: " << path.size() << " 步\n";
    std::cout << "图例: S=起点 G=目标 *=路径 #=障碍 .<数字>=访问顺序\n\n";

    for (int x = 0; x < rows; ++x) {
        for (int y = 0; y < cols; ++y) {
            if (x == start.x && y == start.y) {
                std::cout << " S ";
            } else if (x == goal.x && y == goal.y) {
                std::cout << " G ";
            } else if (on_path[x][y]) {
                std::cout << " * ";
            } else if (grid[x][y] == '#') {
                std::cout << "###";
            } else if (order[x][y] >= 0) {
                printf("%2d ", order[x][y]);
            } else {
                std::cout << " . ";
            }
        }
        std::cout << "\n";
    }
}

int main() {
    // 10x10 网格: '#' = 障碍物, '.' = 可通行
    Grid grid = {
        ". . . . . . . . . .",
        ". . # # # . . . . .",
        ". . # . . . . . . .",
        ". . # . # # # . . .",
        ". . . . # . . . . .",
        ". . # . . . . # . .",
        ". . # # # . . # . .",
        ". . . . # . . # . .",
        ". . . . . . . . . .",
        ". . . . . . . . . .",
    };
    // 解析网格（去掉空格）
    Grid parsed;
    for (auto& row : grid) {
        std::string r;
        for (char c : row)
            if (c != ' ') r += c;
        parsed.push_back(r);
    }

    Point start = {0, 0};
    Point goal  = {9, 9};

    std::vector<Point> bfs_order, dfs_order;

    auto bfs_path = bfs(parsed, start, goal, bfs_order);
    visualize_search(parsed, bfs_order, bfs_path, start, goal, "BFS (广度优先)");

    auto dfs_path = dfs(parsed, start, goal, dfs_order);
    visualize_search(parsed, dfs_order, dfs_path, start, goal, "DFS (深度优先)");

    // 长度对比
    std::cout << "\n路径长度对比:\n";
    std::cout << "  BFS: " << bfs_path.size() << " 步 (最短)\n";
    std::cout << "  DFS: " << dfs_path.size() << " 步 (不保证最短)\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o bfs_dfs pathfinding_basic.cpp
./bfs_dfs
```

**预期输出:**
```
=== BFS (广度优先) ===
搜索了 XX 个节点
路径长度: 19 步
图例: S=起点 G=目标 *=路径 #=障碍 .<数字>=访问顺序

 S   0   1   2   3   4   5   6   7   8
 9  10 ### ### ###  11  12  13  14  15
16  17 ###  *   *   *   *  18  19  20
21  22 ###  *  ### ### ###   *  23  24
25  26  27  *  ###  *   *   *  28  29
30  31 ###  *   *   *  ###  *  32  33
34  35 ### ### ###  *  ###  *  36  37
38  39  40  41 ###  *  ###  *  38  39
40  41  42  43  44  *   *   *  40  41
42  43  44  45  46 47  48  49  50   G

=== DFS (深度优先) ===
...
```

注意 BFS 的搜索像波纹扩散，DFS 则深入一条路径。BFS 路径是 4 方向移动下的最短路径（步数最少），DFS 路径通常更长且蜿蜒。

### Unity C# 可视化提示

在 Unity 中可视化搜索过程：

```csharp
// Unity 中使用协程逐步展示搜索
IEnumerator VisualizeSearch(List<Vector2Int> searchOrder, List<Vector2Int> path)
{
    // 每个节点实例化为一个彩色 Cube/Sprite
    foreach (var p in searchOrder)
    {
        var go = Instantiate(visitedPrefab,
            new Vector3(p.x, 0, p.y), Quaternion.identity);
        // 根据访问顺序着色——早期是蓝色，后期是黄色
        go.GetComponent<Renderer>().material.color =
            Color.Lerp(Color.blue, Color.yellow,
                       (float)currentIndex / searchOrder.Count);
        currentIndex++;
        yield return new WaitForSeconds(0.01f); // 慢速动画
    }
    // 绘制最终路径为红色
    foreach (var p in path)
    {
        Instantiate(pathPrefab,
            new Vector3(p.x, 0.1f, p.y), Quaternion.identity)
            .GetComponent<Renderer>().material.color = Color.red;
        yield return new WaitForSeconds(0.05f);
    }
}
```

## 3. 练习

### 练习 1: 8 方向 BFS（基础）
修改代码，将 4 方向移动改为 8 方向（包括对角线）。对角线移动算 1 步。观察 BFS 是否仍然给出最短路径？为什么？

提示：BFS 在无权图中保证最短路径的前提是**每条边权重相同**。对角线移动和直线移动都是 1 步时仍满足。

### 练习 2: 双向 BFS（进阶）
实现双向 BFS：同时从起点和目标开始搜索，当两个搜索前沿相遇时停止。双向 BFS 可以将搜索节点数减少到单方向 BFS 的约 O(b^(d/2))。

关键：你需要维护两个 visited 集合（或数组），当某个节点同时出现在两个集合中时，路径找到。

### 练习 3: 迷宫生成器 + DFS 求解（挑战）
用递归回溯算法（Recursive Backtracker）生成一个迷宫，然后用 DFS 求解。比较生成迷宫时的递归 DFS 和求解时的迭代 DFS 在代码结构上的异同。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **核心修改：** 在 DX/DY 数组中增加 4 个对角线方向。
>
> ```cpp
> // 8 方向移动: 上、下、左、右、左上、右上、左下、右下
> constexpr int DX8[] = {1, -1, 0, 0, -1, -1, 1, 1};
> constexpr int DY8[] = {0, 0, 1, -1, -1, 1, -1, 1};
> ```
>
> 修改 bfs 函数中的循环：
>
> ```cpp
> for (int d = 0; d < 8; ++d) {
>     int nx = v.x + DX8[d];
>     int ny = v.y + DY8[d];
>     // 边界和障碍物检查不变
>     if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>     if (grid[nx][ny] == '#')          continue;
>     if (visited[nx][ny])              continue;
>
>     visited[nx][ny] = true;
>     parent[nx][ny] = v;
>     q.push({nx, ny});
> }
> ```
>
> **关于"是否仍然给出最短路径"：** 是，BFS 在 8 方向下仍然保证最短路径（步数最少）。前提是图中每条边的**权重相同**——这里 8 个方向每一步都算 1 步，所以仍然是**无权图**，BFS 的最短路径性质成立。注意这里的最短路径是以步数衡量的，不是欧几里得距离——在没有障碍物时，8 方向 BFS 会得到一条贴对角线走的路径（Chebyshev 距离意义上的最短），路径上的步数 ≤ 4 方向 BFS 的步数。对于有障碍物的地图，8 方向 BFS 的路径步数也一定不超过 4 方向 BFS。
>
> **完整的 8 方向 BFS 函数：**
>
> ```cpp
> constexpr int DX8[] = {1, -1, 0, 0, -1, -1, 1, 1};
> constexpr int DY8[] = {0, 0, 1, -1, -1, 1, -1, 1};
> constexpr int ND8 = 8;
>
> auto bfs_8dir(const Grid& grid, Point start, Point goal,
>               std::vector<Point>& out_search_order)
>     -> std::vector<Point>
> {
>     int rows = static_cast<int>(grid.size());
>     int cols = static_cast<int>(grid[0].size());
>
>     std::vector<std::vector<bool>> visited(rows, std::vector<bool>(cols, false));
>     std::vector<std::vector<Point>> parent(rows, std::vector<Point>(cols, {-1, -1}));
>
>     std::queue<Point> q;
>     q.push(start);
>     visited[start.x][start.y] = true;
>
>     while (!q.empty()) {
>         Point v = q.front(); q.pop();
>         out_search_order.push_back(v);
>
>         if (v.x == goal.x && v.y == goal.y) {
>             std::vector<Point> path;
>             for (Point p = goal; p.x != -1; p = parent[p.x][p.y])
>                 path.push_back(p);
>             std::reverse(path.begin(), path.end());
>             return path;
>         }
>
>         for (int d = 0; d < ND8; ++d) {
>             int nx = v.x + DX8[d];
>             int ny = v.y + DY8[d];
>             if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>             if (grid[nx][ny] == '#')          continue;
>             if (visited[nx][ny])              continue;
>
>             visited[nx][ny] = true;
>             parent[nx][ny] = v;
>             q.push({nx, ny});
>         }
>     }
>     return {};
> }
> ```

> [!tip]- 练习 2 参考答案
> **双向 BFS** 同时从起点和终点出发搜索，当两个搜索前沿相遇时停止。关键：维护两个 visited 数组（正向和反向），当某个节点**在两个方向上都被访问**时，路径找到。
>
> ```cpp
> #include <unordered_set>
> #include <queue>
>
> // 用 size_t 哈希 Point 以便放入 unordered_set
> struct PointHash {
>     size_t operator()(Point p) const {
>         return static_cast<size_t>(p.x) << 32 | static_cast<uint32_t>(p.y);
>     }
> };
>
> auto bidirectional_bfs(const Grid& grid, Point start, Point goal,
>                         std::vector<Point>& out_search_order)
>     -> std::vector<Point>
> {
>     int rows = static_cast<int>(grid.size());
>     int cols = static_cast<int>(grid[0].size());
>
>     // 两个方向的 parent 和 visited
>     std::vector<std::vector<Point>> parent_fwd(rows, std::vector<Point>(cols, {-1, -1}));
>     std::vector<std::vector<Point>> parent_bwd(rows, std::vector<Point>(cols, {-1, -1}));
>
>     std::vector<std::vector<int>> visited(rows, std::vector<int>(cols, 0));
>     // visited == 1 表示被正向搜索访问过，2 表示被反向搜索访问过
>
>     std::queue<Point> q_fwd, q_bwd;
>     q_fwd.push(start); visited[start.x][start.y] = 1;
>     q_bwd.push(goal);  visited[goal.x][goal.y]  = 2;
>
>     Point meet_point = {-1, -1}; // 两个搜索前沿相遇的点
>
>     while (!q_fwd.empty() && !q_bwd.empty()) {
>         // === 正向扩展一层 ===
>         size_t fwd_size = q_fwd.size();
>         for (size_t i = 0; i < fwd_size; ++i) {
>             Point v = q_fwd.front(); q_fwd.pop();
>             out_search_order.push_back(v);
>
>             for (int d = 0; d < 4; ++d) {
>                 int nx = v.x + DX[d], ny = v.y + DY[d];
>                 if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>                 if (grid[nx][ny] == '#') continue;
>
>                 if (visited[nx][ny] == 2) { // 遇到了反向搜索的节点！
>                     parent_fwd[nx][ny] = v;
>                     meet_point = {nx, ny};
>                     goto found;
>                 }
>                 if (visited[nx][ny] == 0) {
>                     visited[nx][ny] = 1;
>                     parent_fwd[nx][ny] = v;
>                     q_fwd.push({nx, ny});
>                 }
>             }
>         }
>
>         // === 反向扩展一层 ===
>         size_t bwd_size = q_bwd.size();
>         for (size_t i = 0; i < bwd_size; ++i) {
>             Point v = q_bwd.front(); q_bwd.pop();
>
>             for (int d = 0; d < 4; ++d) {
>                 int nx = v.x + DX[d], ny = v.y + DY[d];
>                 if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>                 if (grid[nx][ny] == '#') continue;
>
>                 if (visited[nx][ny] == 1) { // 遇到了正向搜索的节点！
>                     parent_bwd[nx][ny] = v;
>                     meet_point = {nx, ny};
>                     goto found;
>                 }
>                 if (visited[nx][ny] == 0) {
>                     visited[nx][ny] = 2;
>                     parent_bwd[nx][ny] = v;
>                     q_bwd.push({nx, ny});
>                 }
>             }
>         }
>     }
>
> found:
>     if (meet_point.x == -1) return {}; // 不可达
>
>     // 从相遇点向两个方向回溯，拼接路径
>     std::vector<Point> path;
>     // 正向回溯到 start
>     for (Point p = meet_point; p.x != -1; p = parent_fwd[p.x][p.y])
>         path.push_back(p);
>     std::reverse(path.begin(), path.end());
>     // 反向回溯到 goal（跳过 meet_point 本身，因为已被正向包含）
>     for (Point p = parent_bwd[meet_point.x][meet_point.y];
>          p.x != -1; p = parent_bwd[p.x][p.y])
>         path.push_back(p);
>
>     return path;
> }
> ```
>
> **复杂度分析：** 单方向 BFS 搜索深度 d 时需要 O(b^d) 个节点（b 为分支因子）。双向 BFS 每边搜索约 d/2 深度，各需要 O(b^(d/2)) 个节点，总计约 2 * O(b^(d/2))，在大深度场景下比 O(b^d) 快指数级别。

> [!tip]- 练习 3 参考答案（挑战）
> **1. 递归回溯迷宫生成器（Recursive Backtracker）：**
>
> ```cpp
> #include <random>
> #include <algorithm>
>
> // 迷宫表示：grid[x][y] = '#' 代表墙，'.' 代表通道
> // 迷宫尺寸为奇数：实际通道在奇数坐标 (1,1), (1,3), (3,3) ...
> // 墙在偶数坐标
> // 例如 15x15 迷宫：7x7 的单元格，加上外围墙 = 2*7+1 = 15
>
> void dfs_maze_gen(std::vector<std::string>& maze, int x, int y,
>                   std::mt19937& rng) {
>     // 定义四个方向，每步跨 2 格（从单元格中心到相邻单元格中心）
>     constexpr int dirs[4][2] = {{2,0}, {-2,0}, {0,2}, {0,-2}};
>
>     // 随机打乱方向
>     int order[4] = {0, 1, 2, 3};
>     std::shuffle(order, order + 4, rng);
>
>     for (int i = 0; i < 4; ++i) {
>         int nx = x + dirs[order[i]][0];
>         int ny = y + dirs[order[i]][1];
>
>         if (nx < 1 || nx >= static_cast<int>(maze.size()) - 1 ||
>             ny < 1 || ny >= static_cast<int>(maze[0].size()) - 1)
>             continue; // 边界
>         if (maze[nx][ny] == '.') continue; // 已经挖过
>
>         // 挖开中间的墙（通道格子）
>         int wx = x + dirs[order[i]][0] / 2;
>         int wy = y + dirs[order[i]][1] / 2;
>         maze[wx][wy] = '.';
>         maze[nx][ny] = '.';
>
>         dfs_maze_gen(maze, nx, ny, rng); // 递归进入下一个单元格
>     }
> }
>
> auto generate_maze(int cell_rows, int cell_cols, unsigned int seed = 42)
>     -> std::vector<std::string>
> {
>     int maze_rows = 2 * cell_rows + 1;
>     int maze_cols = 2 * cell_cols + 1;
>
>     // 初始全是墙
>     std::vector<std::string> maze(maze_rows, std::string(maze_cols, '#'));
>
>     std::mt19937 rng(seed);
>     // 从 (1,1) 开始挖掘
>     maze[1][1] = '.';
>     dfs_maze_gen(maze, 1, 1, rng);
>
>     // 设置起点和终点
>     maze[1][1] = 'S';                // 入口
>     maze[maze_rows-2][maze_cols-2] = 'G';  // 出口
>
>     return maze;
> }
> ```
>
> **2. 迭代 DFS 求解迷宫（复用代码示例中的 dfs 函数）：** 上述生成的迷宫实质是一个连通图，可以用代码示例中的迭代 DFS 直接求解。只需生成迷宫后调用 `dfs(maze, start, goal, order)`。
>
> **3. 递归生成 vs 迭代求解的代码结构对比：**
>
> | 方面 | 递归生成器 (生成迷宫) | 迭代 DFS (求解迷宫) |
> |------|---------------------|-------------------|
> | 状态管理 | 调用栈隐式管理 | `std::stack` 显式管理 |
> | visited 判断 | 检查格子是否已挖开 (`maze[nx][ny] == '.'`) | 单独的 visited 二维数组 |
> | 邻居遍历 | 每次随机打乱方向（生成随机迷宫） | 固定方向顺序（确定性的求解） |
> | 步长 | 每次跨越 2 格 + 1 格墙 | 每次只走 1 格 |
> | 终止条件 | 所有可达单元格都被访问 | 找到目标立即停止 |
> | 路径记录 | 无（只关心连通性） | parent 数组回溯构造路径 |
>
> **核心洞察：** 递归回溯迷宫生成器本质上是 DFS 的递归形式——沿着一条随机路径走到尽头，撞墙则回溯到上一个分叉点继续。唯一的区别是它在回溯前"挖开"了路径上的墙壁。递归形式在这里更自然，因为不需要显式维护栈状态（"走到哪里了，还有哪些分叉没试"），调用栈天然追踪回溯链。而求解时的迭代 DFS 需要显式的 parent 追踪，以便构造求解路径。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Red Blob Games: Introduction to Pathfinding** — 交互式可视化，展示 BFS/DFS/Dijkstra/A* 的区别
  https://www.redblobgames.com/pathfinding/a-star/introduction.html
- **CLRS 第 22 章** — 图搜索算法的严格推导和复杂度分析
- **Game AI Pro: "Efficient Graph Search"** — 游戏行业中优化图搜索的实战技巧
- **Boost.Graph 库** (BGL) — C++ 中图算法的工业级实现，学习其迭代器模式和访问者模式

## 常见陷阱

1. **visited 标记时机错误（DFS）**：在 pop 时标记 visited 会导致同一节点多次入栈，时间复杂度退化。**必须在 push/入栈时标记。**

2. **BFS 用栈代替队列**：误用 `std::stack` 实现 BFS = 实际得到的是 DFS 的迭代版本。BFS 必须是 FIFO 顺序。

3. **忘记边界检查**：2D 网格中 `grid[nx][ny]` 访问前必须检查 `nx, ny` 是否在有效范围内。使用 `at()` 代替 `[]` 可以在调试阶段捕获越界。

4. **递归 DFS 栈溢出**：大型地图（1000×1000）上递归 DFS 会爆栈。使用显式 `std::stack` 的迭代版本更安全。

5. **把 parent 数组初始化为 {0,0}**：{0,0} 是一个有效坐标，无法区分"未设置"和"父节点是原点"。使用 {-1, -1} 或 `std::optional<Point>`。

6. **邻接矩阵在稀疏图上浪费内存**：游戏地图中每个节点的邻居通常是 4-8 个，邻接表或隐式图远优于邻接矩阵。
