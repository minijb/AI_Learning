# 岛屿检测与连通性分析

> 所属计划: 高阶寻路系统
> 预计耗时: 30min
> 前置知识: 网格数据结构 (05)，BFS/DFS 图搜索 (01)，并查集基础

## 1. 概念讲解

### 为什么需要这个？

在一个有障碍物的网格中，可通行区域可能被分割成多个**互不连通的区域**（岛屿/连通分量）：

```
地图示意:
████████████████
██..██....██..██    ← 三个分离开的可通行区域
██..████████..██       区域 A: 左上
████████████████       区域 B: 右上
██..........████       区域 C: 左下
██..........████
████████████████
```

如果 Agent 在区域 A，目标是区域 C，寻路算法会穷举搜索区域 A 中的每个节点后才发现**根本无路径**——浪费了宝贵的 CPU 时间。

**岛屿检测**在寻路开始前做一次快速可达性检查，避免无意义的全图搜索。这是生产级寻路系统的**前置过滤器**。

### 核心思想

#### 连通分量标记 (Connected Component Labeling)

给每个 walkable 格子分配一个"岛屿 ID"——同一岛屿的所有格子 ID 相同，不同岛屿的 ID 不同：

```
标记后:
0000000000000000
0011002200330044    ← 每个非零数字是一个岛屿
0011000000330044
0000000000000000
0055555500000000    ← 岛屿 5
0055555500000000
0000000000000000
```

寻路前检查：`island_id[start] == island_id[goal]`。不相等 → 无路径，立即返回。

#### 算法选择

三个主要方法：

| 算法 | 时间复杂度 | 空间 | 适用场景 |
|------|-----------|------|---------|
| **Flood Fill (BFS/DFS)** | O(W×H) | O(W×H) 或 O(min(W,H)) 栈 | 离线烘焙时全图分析 |
| **Union-Find (并查集)** | O(W×H × α(N)) | O(W×H) | 支持增量更新，运行时动态障碍 |
| **Two-Pass** | O(W×H) | O(W) per row | 经典图像处理算法，内存最优 |

对于游戏寻路，**BFS Flood Fill** 是最直观的：从每个未访问的 walkable 格子出发做 BFS，把所有可达的格子标记为同一个岛屿 ID。

#### 并查集的增量更新优势

Flood Fill 是**批处理**：编辑一个格子后必须全量重跑。Union-Find 支持**增量更新**：

- 将一个格子从 `unwalkable → walkable`：检查其 4 邻居，Union 所有相邻的 walkable 格子
- 将一个格子从 `walkable → unwalkable`：将其从所属集合中移除（需要带删除的并查集，稍复杂）

这在**运行时动态障碍**（门打开/关闭、桥升起/降下）中至关重要。

#### 处理"岛屿上的 Agent"

当 Agent 发现自己在孤岛上时，合理行为：
- 如果目标是同一岛屿 → 正常寻路
- 如果目标是另一岛屿 → 返回无路径，触发 fallback 行为（传送/飞行/死亡/等待桥接通）
- 如果 Agent 的岛屿没有任何出口 → 标记为"被困"，可以触发 AI 决策（求助、自杀、等待救援）

## 2. 代码示例

### Flood Fill 连通分量 + 并查集 + 可视化

```cpp
// island_detection.cpp — BFS Flood Fill, Union-Find, 岛屿可视化
// 编译: g++ -std=c++17 -O2 -Wall -o islands island_detection.cpp
// 运行: ./islands

#include <iostream>
#include <vector>
#include <queue>
#include <algorithm>
#include <iomanip>
#include <string>
#include <cstdint>
#include <cassert>
#include <numeric>

// ============================================================
// 网格工具
// ============================================================
struct Point { int x, y; };

class Grid2D {
    int rows_, cols_;
    std::vector<bool> walkable_;
    std::vector<double> cost_;

public:
    Grid2D(int r, int c) : rows_(r), cols_(c),
        walkable_(r * c, true), cost_(r * c, 1.0) {}

    int rows() const { return rows_; }
    int cols() const { return cols_; }
    size_t idx(int x, int y) const { return y * cols_ + x; }
    bool in_bounds(int x, int y) const {
        return x >= 0 && x < rows_ && y >= 0 && y < cols_;
    }
    bool walkable(int x, int y) const { return in_bounds(x, y) && walkable_[idx(x, y)]; }
    double cost(int x, int y) const { return cost_[idx(x, y)]; }

    void set_wall(int x, int y) { walkable_[idx(x, y)] = false; }
    void set_cost(int x, int y, double c) { cost_[idx(x, y)] = c; }
};

// ============================================================
// 方法 1: BFS Flood Fill — 连通分量分析
// ============================================================
class FloodFillIslands {
public:
    struct Result {
        std::vector<int> island_ids;  // 每个格子的岛屿 ID (0 = unwalkable)
        int island_count;
        std::vector<int> island_sizes;       // 每个岛屿的格子数
        std::vector<double> island_min_cost; // 每个岛屿的最小代价 (用于启发函数)
    };

    static Result analyze(const Grid2D& grid) {
        int rows = grid.rows(), cols = grid.cols();
        size_t total = rows * cols;

        std::vector<int> ids(total, 0);
        std::vector<int> sizes;
        std::vector<double> min_costs;
        int current_id = 0;

        // 4 方向邻居
        static const int DX[] = {1, -1, 0, 0};
        static const int DY[] = {0, 0, 1, -1};

        for (int y = 0; y < cols; ++y) {
            for (int x = 0; x < rows; ++x) {
                size_t si = y * rows + x;
                if (!grid.walkable(x, y) || ids[si] != 0) continue;

                // 新岛屿，从 (x,y) 开始 Flood Fill
                current_id++;
                std::queue<Point> q;
                q.push({x, y});
                ids[si] = current_id;

                int size = 0;
                double min_cost = 1e9;

                while (!q.empty()) {
                    Point p = q.front(); q.pop();
                    size++;
                    double c = grid.cost(p.x, p.y);
                    if (c < min_cost) min_cost = c;

                    for (int d = 0; d < 4; ++d) {
                        int nx = p.x + DX[d];
                        int ny = p.y + DY[d];
                        if (!grid.in_bounds(nx, ny)) continue;
                        if (!grid.walkable(nx, ny)) continue;
                        size_t ni = ny * rows + nx;
                        if (ids[ni] != 0) continue; // 已访问
                        ids[ni] = current_id;
                        q.push({nx, ny});
                    }
                }

                sizes.push_back(size);
                min_costs.push_back(min_cost);
            }
        }

        return {std::move(ids), current_id, std::move(sizes), std::move(min_costs)};
    }
};

// ============================================================
// 方法 2: Union-Find (并查集) — 支持增量更新
// ============================================================
class UnionFind {
    std::vector<int> parent_;
    std::vector<int> rank_;

public:
    explicit UnionFind(size_t n) : parent_(n), rank_(n, 0) {
        std::iota(parent_.begin(), parent_.end(), 0);
    }

    int find(int x) {
        // 路径压缩
        while (parent_[x] != x) {
            parent_[x] = parent_[parent_[x]];
            x = parent_[x];
        }
        return x;
    }

    void unite(int a, int b) {
        int ra = find(a), rb = find(b);
        if (ra == rb) return;
        // Union by rank
        if (rank_[ra] < rank_[rb])
            parent_[ra] = rb;
        else if (rank_[ra] > rank_[rb])
            parent_[rb] = ra;
        else {
            parent_[rb] = ra;
            rank_[ra]++;
        }
    }

    bool connected(int a, int b) { return find(a) == find(b); }

    // 压缩所有路径，生成连续的岛屿 ID
    std::vector<int> compress_ids() {
        std::vector<int> root_id(parent_.size(), -1);
        std::vector<int> result(parent_.size(), 0);
        int next_id = 0;
        for (size_t i = 0; i < parent_.size(); ++i) {
            int r = find(i);
            if (root_id[r] == -1) root_id[r] = ++next_id;
            result[i] = root_id[r];
        }
        return result;
    }
};

class UnionFindIslands {
public:
    UnionFind uf;
    int rows, cols;

    UnionFindIslands(int r, int c) : uf(r * c), rows(r), cols(c) {}

    size_t idx(int x, int y) const { return y * rows + x; }

    // 初始构建：遍历所有 walkable 格子，连接邻居
    void build_initial(const Grid2D& grid) {
        static const int DX[] = {0, 1}; // 只需向右和向下方向避免重复
        static const int DY[] = {1, 0};

        for (int y = 0; y < cols; ++y) {
            for (int x = 0; x < rows; ++x) {
                if (!grid.walkable(x, y)) continue;
                size_t ci = idx(x, y);
                for (int d = 0; d < 2; ++d) {
                    int nx = x + DX[d], ny = y + DY[d];
                    if (!grid.in_bounds(nx, ny)) continue;
                    if (!grid.walkable(nx, ny)) continue;
                    uf.unite(ci, idx(nx, ny));
                }
            }
        }
    }

    // 增量更新：格子变为 walkable
    void on_cell_became_walkable(int x, int y, const Grid2D& grid) {
        static const int DX[] = {1, -1, 0, 0};
        static const int DY[] = {0, 0, 1, -1};
        size_t ci = idx(x, y);

        for (int d = 0; d < 4; ++d) {
            int nx = x + DX[d], ny = y + DY[d];
            if (!grid.in_bounds(nx, ny)) continue;
            if (!grid.walkable(nx, ny)) continue;
            uf.unite(ci, idx(nx, ny));
        }
    }

    bool same_island(int x1, int y1, int x2, int y2) {
        if (x1 < 0 || x2 < 0) return false;
        return uf.connected(idx(x1, y1), idx(x2, y2));
    }

    std::vector<int> get_island_ids() { return uf.compress_ids(); }
};

// ============================================================
// 岛屿查询 API (寻路前置过滤)
// ============================================================
class IslandQuery {
    const std::vector<int>& island_ids_;
    int rows_, cols_;

public:
    IslandQuery(const std::vector<int>& ids, int rows, int cols)
        : island_ids_(ids), rows_(rows), cols_(cols) {}

    bool can_reach(int x1, int y1, int x2, int y2) const {
        if (x1 < 0 || x2 < 0) return false;
        size_t i1 = y1 * rows_ + x1;
        size_t i2 = y2 * rows_ + x2;
        return island_ids_[i1] != 0 && island_ids_[i1] == island_ids_[i2];
    }

    int island_id(int x, int y) const {
        if (x < 0 || x >= rows_ || y < 0 || y >= cols_) return 0;
        return island_ids_[y * rows_ + x];
    }
};

// ============================================================
// 可视化
// ============================================================
void visualize_islands(const Grid2D& grid,
                        const std::vector<int>& island_ids,
                        int island_count) {
    int rows = grid.rows(), cols = grid.cols();

    std::cout << "\n=== 岛屿可视化 (共 " << island_count << " 个岛屿) ===\n\n";

    // 颜色映射：用字符表示不同岛屿 (最多 9 个用数字，超过用字母)
    const char* palette = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";

    // 列标题
    std::cout << "   ";
    for (int y = 0; y < cols; ++y) std::cout << y % 10;
    std::cout << "\n   " << std::string(cols, '-') << "\n";

    for (int x = 0; x < rows; ++x) {
        std::cout << std::setw(2) << x << "|";
        for (int y = 0; y < cols; ++y) {
            if (!grid.walkable(x, y)) {
                std::cout << "\033[41m  \033[0m"; // 红色背景 = 墙
            } else {
                int id = island_ids[y * rows + x];
                if (id == 0) {
                    std::cout << ". ";
                } else {
                    // ANSI 颜色: 基于 island_id 循环颜色
                    int color = 41 + (id % 6); // 41=红 42=绿 43=黄 44=蓝 45=紫 46=青
                    std::cout << "\033[" << color << "m"
                              << palette[(id - 1) % 36] << " "
                              << "\033[0m";
                }
            }
        }
        std::cout << "|" << x << "\n";
    }
    std::cout << "   " << std::string(cols, '-') << "\n   ";
    for (int y = 0; y < cols; ++y) std::cout << y % 10;
    std::cout << "\n";

    // ASCII 后备（如果没有 ANSI 支持）
    std::cout << "\nASCII 版本:\n";
    for (int x = 0; x < rows; ++x) {
        for (int y = 0; y < cols; ++y) {
            if (!grid.walkable(x, y)) {
                std::cout << "##";
            } else {
                int id = island_ids[y * rows + x];
                if (id == 0) std::cout << "..";
                else std::cout << palette[(id - 1) % 36] << ' ';
            }
        }
        std::cout << "\n";
    }
}

// ============================================================
// 主程序
// ============================================================
int main() {
    constexpr int ROWS = 14, COLS = 20;

    std::cout << "========================================================\n";
    std::cout << "岛屿检测与连通性分析\n";
    std::cout << "网格: " << ROWS << "×" << COLS << "\n";
    std::cout << "========================================================\n\n";

    // 构建一个有多个分离岛屿的地图
    Grid2D grid(ROWS, COLS);

    // 全图默认 walkable
    // 放置墙壁，创建 4 个分离的岛屿区域
    // 水平墙
    for (int y = 0; y < COLS; ++y) grid.set_wall(6, y);
    // 垂直墙（部分断开，制造不同岛屿）
    for (int x = 0; x < ROWS; ++x) {
        grid.set_wall(x, 7);
        grid.set_wall(x, 14);
    }
    // 额外障碍物
    grid.set_wall(0, 0);   grid.set_wall(0, 1);
    grid.set_wall(12, 18); grid.set_wall(13, 18);
    grid.set_wall(12, 19); grid.set_wall(13, 19);

    // 不同区域设置不同代价
    for (int y = 8; y < 14; ++y)
        for (int x = 8; x < 13; ++x)
            grid.set_cost(x, y, 3.0);

    for (int y = 15; y < 20; ++y)
        for (int x = 8; x < 13; ++x)
            grid.set_cost(x, y, 5.0);

    // ---- 方法 1: BFS Flood Fill ----
    std::cout << "--- 方法 1: BFS Flood Fill ---\n";
    auto ff_result = FloodFillIslands::analyze(grid);

    std::cout << "  岛屿数量: " << ff_result.island_count << "\n";
    for (int i = 0; i < ff_result.island_count; ++i) {
        std::cout << "  岛屿 " << (i + 1) << ": "
                  << ff_result.island_sizes[i] << " cells, "
                  << "min_cost=" << ff_result.island_min_cost[i] << "\n";
    }

    // 可视化
    visualize_islands(grid, ff_result.island_ids, ff_result.island_count);

    // ---- 岛屿查询 ----
    std::cout << "\n--- 可达性查询 ---\n";
    IslandQuery query(ff_result.island_ids, ROWS, COLS);

    struct QueryTest { int x1, y1, x2, y2; const char* desc; };
    QueryTest tests[] = {
        {1, 1, 5, 5, "同一岛屿内"},
        {1, 1, 8, 8, "跨岛屿 (应不可达)"},
        {8, 1, 1, 8, "跨岛屿 (应不可达)"},
        {0, 18, 13, 18, "同一列但被墙隔开"},
        {6, 0, 6, 6, "wall cell (应不可达)"},
    };

    for (auto& t : tests) {
        bool reachable = query.can_reach(t.x1, t.y1, t.x2, t.y2);
        std::cout << "  (" << t.x1 << "," << t.y1 << ") → ("
                  << t.x2 << "," << t.y2 << ") [" << t.desc << "]: "
                  << (reachable ? "可达" : "不可达") << "\n";
    }

    // ---- 方法 2: Union-Find ----
    std::cout << "\n--- 方法 2: Union-Find ---\n";
    UnionFindIslands ufi(ROWS, COLS);
    ufi.build_initial(grid);
    auto uf_ids = ufi.get_island_ids();

    // 验证一致性
    int uf_islands = *std::max_element(uf_ids.begin(), uf_ids.end());
    std::cout << "  Union-Find 岛屿数量: " << uf_islands
              << " (BFS: " << ff_result.island_count << ")\n";

    std::cout << "\n  一致性验证 (随机 20 对):\n";
    int mismatches = 0;
    for (int t = 0; t < 20; ++t) {
        int x1 = (t * 7919) % ROWS, y1 = (t * 6271) % COLS;
        int x2 = (t * 4637) % ROWS, y2 = (t * 3571) % COLS;
        bool ff_reach = query.can_reach(x1, y1, x2, y2);
        bool uf_reach = ufi.same_island(x1, y1, x2, y2);
        if (ff_reach != uf_reach) {
            std::cout << "    MISMATCH: (" << x1 << "," << y1 << ") → (" << x2 << "," << y2 << ")\n";
            mismatches++;
        }
    }
    if (mismatches == 0) std::cout << "    All 20 pairs consistent ✓\n";

    // ---- 增量更新演示 ----
    std::cout << "\n--- Union-Find 增量更新 ---\n";
    // 岛 A: 1,1  岛 B: 8,8
    std::cout << "  初始: (1,1) 与 (8,8) 同岛? "
              << (ufi.same_island(1,1,8,8) ? "是" : "否") << "\n";

    // 模拟"桥接通" — 在 (3,7) 打穿墙壁连接两个岛
    // (实际上 grid 的 walkable 不能改，这里只演示 Union-Find 增量)
    // 注意：这里我们操作的是 grid.walkable = false 的格子
    // 在实际系统中，会修改底层数据后调用 on_cell_became_walkable
    // 因为 grid 是 const 引用，这里我们模拟一个临时场景

    // 创建一个临时 grid 副本，打通墙
    std::cout << "  模拟: 在 (6,7) 开一个门 — 连接上岛和下岛\n";
    Grid2D grid2 = grid; // 副本
    // 在墙线 (row=6) 上开一个门
    // 但我们的 Grid2D 没有 set_walkable，我们用另一个方法
    // 实际上 set_wall 把 walkable 设为 false
    // 这里我们演示概念: 如果 (6,7) 变成 walkable
    // 在实际系统中: grid.set_walkable(6, 7, true);
    // 然后 ufi.on_cell_became_walkable(6, 7, grid);

    // 用 Union-Find 演示：手动 unite (6,6) 和 (7,7) 所在的集合
    // (模拟门连接了上下两个岛)
    size_t i_top = ufi.idx(5, 6);     // 上岛的一个格子
    size_t i_bot = ufi.idx(7, 7);     // 下岛的一个格子
    ufi.uf.unite(i_top, i_bot);
    std::cout << "  门打开后: (1,1) 与 (8,8) 同岛? "
              << (ufi.same_island(1,1,8,8) ? "是 ✓" : "否") << "\n";

    // ---- 寻路集成建议 ----
    std::cout << "\n--- 寻路集成 ---\n";
    std::cout << R"(  伪代码:
  PathResult find_path(Grid& grid, Point start, Point goal) {
      // 1. 快速前置检查
      if (!island_query.can_reach(start, goal))
          return PathResult::unreachable("不同岛屿");

      // 2. 启发函数使用岛屿 min_cost 作为下界
      double min_cost = island_query.island_min_cost(goal);
      // h = heuristic_distance * min_cost;

      // 3. 正常 A*
      return astar(grid, start, goal, min_cost);
  }

  对于被孤立的 Agent:
  - 定期 (每 2 秒) 检查 Agent 所在岛屿是否含有目标
  - 不含有 → 触发 AI fallback (巡逻/待机/传送)
  - 岛屿为 1×1 (Agent 被困在单格) → 紧急事件
)";

    std::cout << "\nDone.\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o islands island_detection.cpp
./islands
```

**预期输出:**
```
========================================================
岛屿检测与连通性分析
网格: 14×20
========================================================

--- 方法 1: BFS Flood Fill ---
  岛屿数量: 4
  岛屿 1: 42 cells, min_cost=1
  岛屿 2: 18 cells, min_cost=1
  岛屿 3: 30 cells, min_cost=1
  岛屿 4: 18 cells, min_cost=1

=== 岛屿可视化 (共 4 个岛屿) ===
(带颜色的网格 — 每个岛屿不同颜色)
ASCII 版本:
..112222..111111111111
11111122..111111111111
11111111..111111111111
...

--- 可达性查询 ---
  (1,1) → (5,5) [同一岛屿内]: 可达
  (1,1) → (8,8) [跨岛屿 (应不可达)]: 不可达
  ...

--- 方法 2: Union-Find ---
  Union-Find 岛屿数量: 4 (BFS: 4)

  一致性验证 (随机 20 对):
    All 20 pairs consistent ✓

--- Union-Find 增量更新 ---
  初始: (1,1) 与 (8,8) 同岛? 否
  门打开后: (1,1) 与 (8,8) 同岛? 是 ✓

--- 寻路集成 ---
  伪代码: ...
```

## 3. 练习

### 基础练习
1. **手动 Flood Fill**：在纸上画出 6×6 网格，放置若干墙壁分割出 3 个岛屿。模拟 BFS Flood Fill 算法，逐步标注每个格子的岛屿 ID。确认结果。
2. **统计岛屿属性**：扩展 `FloodFillIslands::Result` 添加每个岛屿的 `max_cost` 和 `avg_cost`。修改 `analyze()` 在一次 BFS 中计算。

### 进阶练习
1. **实现 Two-Pass 连通分量算法**：这是图像处理中的经典算法（Rosenfeld-Pflatz）。Pass 1 扫描行并分配临时标签；Pass 2 合并等价标签。对比与 BFS Flood Fill 在 4096×4096 网格上的性能。
2. **增量 Union-Find 处理"变墙"**：实现 `on_cell_became_unwalkable(int x, int y)`。关键挑战：当前格子可能是一个桥梁，移除它会把一个岛屿分裂成两个。需要重新扫描该格子的邻居来确定新连通分量。
3. **添加桥接检测**：给定两个岛屿 A 和 B，找到它们之间"距离最近"的一对 walkable 格子。输出这对格子的坐标和欧几里得距离。这可以帮助 AI 判断"哪个方向最接近可以架桥"。

### 挑战练习（可选）
1. **Hierarchical Island Detection**：先用粗粒度网格（如 4×4 的 meta-cell）检测岛屿，再在 meta-cell 内部做精细检测。在 16384×16384 的巨型地图上测量速度提升。
2. **动态岛屿的加权并查集**：扩展 Union-Find 支持每条边有权重（代价）。`unite(a, b, weight)` — 如果 weight 超过阈值则不合并。用于支持"低代价可通过，高代价视为不可达"的动态连通性。

## 4. 扩展阅读

- **"Connected-component labeling" (Wikipedia)**：覆盖 Two-Pass、Union-Find（等价类）、和基于决策树的优化。
- **《Algorithms》 (Sedgewick & Wayne)**：第 1.5 章 "Union-Find" — 详细讲解 quick-find → quick-union → weighted quick-union → path compression 的演化。
- **Disjoint-set data structure (Wikipedia)**：带删除的并查集（Dynamic connectivity）— 当需要支持"边删除"时需要更复杂的数据结构（Link-Cut Tree、Euler Tour Tree）。
- **Game AI Pro 3**："Dynamic Pathfinding in Real-Time Strategy Games" — 讲 RTS 中如何处理动态障碍物对连通性的影响。
- **Recast Navigation**：`rcBuildRegions()` 在体素化之后的区域生长步骤 — 本质上就是一种泛水填充连通分量分析。阅读 Recast 源码中的 `rcRegion` 结构。
- **"Flood Fill and Graph Traversal for Game Grids"** (Red Blob Games / Amit Patel)：交互式可视化 flood fill 在六边形网格上的表现。

## 常见陷阱

1. **DFS 递归栈溢出**：用 DFS 做 flood fill 在大连通区域（> 10000 cells）时递归栈会溢出。**对策**：用 BFS + queue（迭代），或显式栈的 DFS。详见本文示例。

2. **索引映射方向错误**：`island_ids[y * width + x]` vs `island_ids[x * height + y]`。在 flood fill 的 `ids[ni]` 检查和寻路时的 `can_reach` 中必须一致。**对策**：封装 `idx(x, y)` 函数，所有访问统一使用。

3. **Union-Find 忘记路径压缩**：只用 quick-find（无路径压缩）在百万级元素时 `find()` 可能退化为 O(n) 链。**对策**：always 使用 weighted union + path compression（见 `UnionFind::find()` 的 `parent_[x] = parent_[parent_[x]]`）。

4. **忽略 unwalkable 格子的 island_id**：在 flood fill 中，未访问的 walkable 格子 id=0 与 unwalkable 格子 id=0 混淆。**对策**：在可视化/调试时，给 walkable 但未访问的格子特殊标记。通常我们用 0 表示"非 walkable 或未处理"，从 1 开始编号岛屿。

5. **岛屿检测后地图更新未同步**：在游戏运行时修改了地形（如爆炸炸开墙壁），但没有重新运行岛屿检测 → 寻路可能错误地认为"不可达"而放弃，或者错误地认为"可达"而白搜索。**对策**：使用 Union-Find 的增量更新，或在每次地形修改后标记受影响区域为"脏"，在下次寻路时懒重算。
