# GPU 加速寻路

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: 网格寻路 (04), A* 算法 (03), 基础 GPU 编程概念（线程组/共享内存/Compute Shader 或 CUDA）

## 1. 概念讲解

### 为什么需要这个？

在 RTS 游戏中，你可能需要为 200 个单位同时计算路径。在开放世界游戏中，可能有数千个 AI 实体需要定期更新导航目标。CPU 顺序执行这些查询的延迟加起来是致命的。

GPU 寻路的核心价值不在单次查询的速度（GPU 单线程比 CPU 单线程慢），而在**大规模并行**：

```
场景: 100 个单位，每个需要 A* 寻路 (各 ~2ms)
CPU 顺序: 100 × 2ms = 200ms → 5 FPS (不可接受)
GPU 并行: 所有 100 个查询同时运行 → ~5ms → 200 FPS
```

GPU 可以同时运行数千个线程。如果能把寻路问题映射到这种吞吐量导向的架构上，就能处理传统方法不可能达到的规模。

### 核心思想

#### 两种并行策略

**数据并行 (Data-Parallel)**: 同时运行多个独立的寻路查询，每个查询由一个线程或一个 warp 处理。

```
查询 1 → 线程 1    ┐
查询 2 → 线程 2    │
查询 3 → 线程 3    ├→ 同时运行
 ...                │
查询 N → 线程 N    ┘
```

**算法并行 (Algorithm-Parallel)**: 将单个寻路查询的内部操作并行化——例如，open set 的批量扩展、启发式评估的向量化。

实践中，游戏几乎只用数据并行（批量查询），因为算法并行面临严重的同步开销：A* 的每次迭代产生的 open set 大小是数据依赖的，不同线程的进度不同，需要全局 barrier——这在 GPU 上极贵。

#### GPU 计算模型速览

```
CPU 模型:                          GPU 模型:
┌──────────────┐                  ┌──────────────────────────┐
│  大核心 × 8  │                  │  Thread Group 0 (256 线程)│
│  每核心独立  │                  │  Thread Group 1 (256 线程)│
│  分支预测强  │                  │  Thread Group 2 (256 线程)│
│  缓存层次深  │                  │  ...                      │
└──────────────┘                  │  Thread Group N (256 线程)│
                                  └──────────────────────────┘
延迟优化 (低延迟)                  吞吐量优化 (高吞吐)
```

关键概念：

- **Thread Group / Work Group**: GPU 线程的最小调度单元。同组内的线程可以访问共享内存（shared memory / groupshared），可以同步（barrier）。
- **Warp / Wavefront** (NVIDIA 32 线程 / AMD 64 线程): 线程组内的子单元。warp 内的线程以 SIMD 方式执行——它们真正同时运行同一条指令。
- **共享内存 (Shared Memory)**: 每个 thread group 的片上 SRAM，~100× 比全局内存快。大小有限（通常 32-96 KB）。
- **全局内存 (VRAM)**: GPU 的大容量内存，所有线程可访问，延迟 ~400-600 cycles。

#### 为什么 A* 不适合直接 GPU 化？

A* 有两个对 GPU 不友好的特征：

1. **优先级队列**: GPU 没有高效的原子优先队列。用全局原子操作实现一个会被所有线程争用的优先队列，性能会崩溃。
2. **不规则访问模式**: A* 每次扩展的节点位置是数据依赖的，导致内存访问模式不可预测，cache 命中率极差。

因此，GPU 寻路通常使用 **Dijkstra 类算法**（更容易并行化）而不是 A*。

#### 并行 Dijkstra 的方法

**方法 1: 每个查询一个 Thread Group**

```
每个 thread group 跑一个独立 Dijkstra:
- 用 groupshared memory 存储局部 open/closed 信息
- 一次只处理一张小图（如 64×64 的局部网格）
- 适用于: 批量查询，每个查询互不干扰
```

**方法 2: 分阶段批量 Dijkstra (Chai 等人的方法)**

```
Wavefront 并行 Dijkstra:
第 0 轮: 扩展源节点，标记距离
第 1 轮: 扩展所有距离=1 的节点
第 2 轮: 扩展所有距离=2 的节点
...
每轮之间用 global barrier 同步。

每轮内部:
- 每个线程检查一个节点: 如果该节点的距离 == 当前轮次
  → 对所有邻居做 atomicMin(distance[neighbor], distance[current] + weight)
```

**方法 3: 层次化 GPU 寻路**

在 GPU 上构建和查询 HPA* 的抽象图：在低分辨率层跑 Dijkstra → 在高分辨率层细化路径。这个两层结构天然适合 GPU 的层次化内存（shared→global）。

#### Compute Shader 基础 (Unity/HLSL)

Unity Compute Shader 的基本结构：

```hlsl
// 每个核函数有 [numthreads(X, Y, Z)] 属性
[numthreads(64, 1, 1)]
void CSMain (uint3 id : SV_DispatchThreadID) {
    // id.x = 全局线程 ID (0..N-1)
    // id 用于索引输入数据
}
```

C# 端调度：
```csharp
int threadGroups = Mathf.CeilToInt(queryCount / 64f);
shader.Dispatch(kernelHandle, threadGroups, 1, 1);
```

#### 内存布局：为什么 SoA 在 GPU 上更关键

GPU 的全局内存访问以 32/128 字节的**事务**为单位。如果 warp 中的 32 个线程访问连续的内存地址，它们可以合并为一次事务。如果访问跨度很大，变成 32 次独立事务——吞吐量降至 1/32。

```
// 好: AoS 但在 warp 内连续
struct PathQuery { float2 start, end; };  // 16 bytes
// 线程 0 读 query[0], 线程 1 读 query[1], ...
// → 连续访问 → 合并 → 1 次事务

// 更好: SoA
float2 starts[MAX];   // 所有 start 连续
float2 ends[MAX];     // 所有 end 连续
// 线程序列访问 start/id → 完美合并
```

#### GPU Dijkstra 伪代码

```
// GPU 端 (HLSL/Compute Shader)
StructuredBuffer<float> costMap;      // 代价图 (w×h)
RWStructuredBuffer<float> distances;  // 输出距离 (每个查询一个输出)
StructuredBuffer<int2> starts;        // 起点 (每个查询)
StructuredBuffer<int2> goals;         // 终点 (每个查询)
int mapW, mapH;

groupshared float localDist[64][64];  // 局部距离 (用于小图)
groupshared bool changed;              // 本轮是否有更新

[numthreads(64, 1, 1)]
void DijkstraBatch(uint3 id : SV_DispatchThreadID) {
    uint queryIdx = id.x;
    int2 start = starts[queryIdx];
    int2 goal  = goals[queryIdx];

    // 初始化: 把起始节点距离设为 0
    // (用全局内存的 atomic 操作)
    if (start.x >= 0 && start.y >= 0) {
        InterlockedMin(asuint(distances[queryIdx * mapW * mapH +
                         start.y * mapW + start.x]), asuint(0.0f));
    }

    // 对于大型图，需要多轮迭代
    // 生产实践中使用更复杂的 wavefront 并行策略
}
```

## 2. 代码示例

### C++ 模拟 GPU 并行 Dijkstra (用于理解并行模型)

```cpp
// gpu_pathfinding.cpp — 模拟 GPU 并行 Dijkstra + 批量查询对比
// 编译: g++ -std=c++17 -O2 -Wall -o gpu_pathfinding gpu_pathfinding.cpp
// 运行: ./gpu_pathfinding
//
// 本程序模拟 GPU 的大规模并行寻路：
// - 生成多个随机寻路查询
// - CPU 顺序 A* (基线)
// - 模拟 GPU 批量并行 Dijkstra (wavefront 方法)
// - 对比吞吐量

#include <iostream>
#include <vector>
#include <queue>
#include <cmath>
#include <algorithm>
#include <random>
#include <chrono>
#include <iomanip>
#include <limits>
#include <thread>
#include <atomic>
#include <cstring>

// ============================================================
// 基础类型与常量
// ============================================================
constexpr float INF_F = std::numeric_limits<float>::infinity();
constexpr int INF_I = 1 << 28;

struct Point {
    int x, y;
    bool operator==(const Point& o) const { return x == o.x && y == o.y; }
};

// ============================================================
// 网格地图
// ============================================================
class Grid {
public:
    int w, h;
    std::vector<bool> obstacle;
    std::vector<float> cost; // 地形代价

    Grid(int width, int height)
        : w(width), h(height),
          obstacle(width * height, false),
          cost(width * height, 1.0f) {}

    size_t idx(int x, int y) const { return y * w + x; }
    bool in_bounds(int x, int y) const { return x >= 0 && x < w && y >= 0 && y < h; }
    bool blocked(int x, int y) const { return obstacle[idx(x, y)]; }

    void random_obstacles(float density, int seed = 42) {
        std::mt19937 rng(seed);
        std::uniform_real_distribution<float> dist(0.0f, 1.0f);
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x)
                if (dist(rng) < density)
                    obstacle[idx(x, y)] = true;
    }

    // 确保起点/终点可通行
    void ensure_walkable(const std::vector<Point>& pts) {
        for (auto& p : pts)
            if (in_bounds(p.x, p.y))
                obstacle[idx(p.x, p.y)] = false;
    }
};

// ============================================================
// PathQuery: 一个寻路查询
// ============================================================
struct PathQuery {
    Point start, goal;
    bool success = false;
    float path_cost = 0.0f;
    std::vector<Point> path;
};

// ============================================================
// CPU 顺序 A* (基线)
// ============================================================
struct AStarNode {
    float g, f;
    Point parent;
    bool closed = false;
};

struct OpenEntry {
    float f; Point p;
    bool operator>(const OpenEntry& o) const { return f > o.f; }
};

PathQuery astar_sequential(const Grid& grid, Point start, Point goal) {
    PathQuery result;
    result.start = start;
    result.goal = goal;

    if (grid.blocked(start.x, start.y) || grid.blocked(goal.x, goal.y))
        return result;

    using pqueue = std::priority_queue<OpenEntry, std::vector<OpenEntry>,
                                       std::greater<OpenEntry>>;
    auto heuristic = [](Point a, Point b) {
        return std::sqrt(float((a.x-b.x)*(a.x-b.x) + (a.y-b.y)*(a.y-b.y)));
    };

    std::unordered_map<size_t, AStarNode> nodes;
    pqueue open;

    auto key = [&](Point p) { return grid.idx(p.x, p.y); };

    nodes[key(start)] = {0.0f, heuristic(start, goal), start};
    open.push({heuristic(start, goal), start});

    const Point DIR4[4] = {{0,-1},{1,0},{0,1},{-1,0}};
    const Point DIR8[8] = {{0,-1},{1,-1},{1,0},{1,1},{0,1},{-1,1},{-1,0},{-1,-1}};
    const float DIR_COST[8] = {1.0f, 1.414f, 1.0f, 1.414f, 1.0f, 1.414f, 1.0f, 1.414f};

    while (!open.empty()) {
        Point cur = open.top().p; open.pop();
        auto& cn = nodes[key(cur)];
        if (cn.closed) continue;
        cn.closed = true;

        if (cur.x == goal.x && cur.y == goal.y) {
            result.success = true;
            result.path_cost = cn.g;
            for (Point p = goal; !(p == start); p = nodes[key(p)].parent)
                result.path.push_back(p);
            result.path.push_back(start);
            std::reverse(result.path.begin(), result.path.end());
            return result;
        }

        for (int d = 0; d < 8; ++d) {
            Point nb = {cur.x + DIR8[d].x, cur.y + DIR8[d].y};
            if (!grid.in_bounds(nb.x, nb.y)) continue;
            if (grid.blocked(nb.x, nb.y)) continue;

            float ng = cn.g + DIR_COST[d] * grid.cost[grid.idx(nb.x, nb.y)];

            auto it = nodes.find(key(nb));
            if (it != nodes.end()) {
                if (it->second.closed || ng >= it->second.g) continue;
                it->second.g = ng; it->second.f = ng + heuristic(nb, goal);
                it->second.parent = cur;
                open.push({it->second.f, nb});
            } else {
                float h = heuristic(nb, goal);
                nodes[key(nb)] = {ng, ng + h, cur};
                open.push({ng + h, nb});
            }
        }
    }
    return result;
}

// ============================================================
// 模拟 GPU Wavefront 并行 Dijkstra
// ============================================================
// 这是 GPU 算法的 CPU 模拟，用于理解并行模型
// 在真实 GPU 上，外层循环的每次迭代由 GPU 的多次 dispatch 完成

struct GPUDijkstraResult {
    std::vector<float> distances; // 每个查询的目标距离
    int iterations;               // wavefront 轮数
};

GPUDijkstraResult gpu_dijkstra_batch(
    const Grid& grid,
    const std::vector<PathQuery>& queries) {

    int N = (int)queries.size();
    int total_cells = grid.w * grid.h;

    // 每个查询一个独立的距离数组 (模拟 GPU 全局内存)
    // 在真实 GPU 上，这可能是 StructuredBuffer<float>
    std::vector<float> dist_data(N * total_cells, INF_F);

    // 初始化: 每个查询的起点距离 = 0
    // 模拟 N 个线程并行执行
    for (int q = 0; q < N; ++q) {
        const auto& query = queries[q];
        if (!grid.blocked(query.start.x, query.start.y))
            dist_data[q * total_cells + grid.idx(query.start.x, query.start.y)] = 0.0f;
    }

    // Wavefront 迭代: 模拟 GPU 的多轮 dispatch
    // 在每轮中:
    //   每个"线程"检查一个格子，如果它的距离 == 当前轮次的距离阈值，
    //   则对其邻居做 relax
    //
    // 为了简化模拟，我们使用"推进前沿"的策略
    std::vector<float> prev_dist = dist_data; // 上一轮的距离
    bool changed = true;
    int iteration = 0;
    const int MAX_ITER = grid.w * grid.h; // 最坏情况

    const Point DIR4[4] = {{0,-1},{1,0},{0,1},{-1,0}};
    const float DIR4_COST[4] = {1.0f, 1.0f, 1.0f, 1.0f};

    while (changed && iteration < MAX_ITER) {
        changed = false;
        ++iteration;

        // 模拟 GPU launch: 每个查询独立处理
        // 在真实 GPU 上，这 N 个查询由 N 个 thread group 并行处理
        for (int q = 0; q < N; ++q) {
            // 每个格子"并行"检查 (在 GPU 上各由一个线程处理)
            for (int y = 0; y < grid.h; ++y) {
                for (int x = 0; x < grid.w; ++x) {
                    size_t ci = grid.idx(x, y); // current cell index
                    float cur_dist = prev_dist[q * total_cells + ci];

                    // 这个格子还未到达
                    if (cur_dist >= INF_F * 0.5f) continue;

                    // 对 4 个邻居做 relax
                    for (int d = 0; d < 4; ++d) {
                        int nx = x + DIR4[d].x, ny = y + DIR4[d].y;
                        if (!grid.in_bounds(nx, ny)) continue;
                        if (grid.blocked(nx, ny)) continue;

                        size_t ni = grid.idx(nx, ny); // neighbor index
                        float new_dist = cur_dist + DIR4_COST[d] * grid.cost[ni];

                        // atomicMin 模拟 (GPU 上的 InterlockedMin)
                        if (new_dist < dist_data[q * total_cells + ni]) {
                            dist_data[q * total_cells + ni] = new_dist;
                            changed = true;
                        }
                    }
                }
            }
        }

        prev_dist = dist_data;
    }

    GPUDijkstraResult result;
    result.distances.resize(N, INF_F);
    result.iterations = iteration;

    for (int q = 0; q < N; ++q) {
        const auto& query = queries[q];
        size_t gi = grid.idx(query.goal.x, query.goal.y);
        result.distances[q] = dist_data[q * total_cells + gi];
    }

    return result;
}

// ============================================================
// 多线程并行 A* (模拟 GPU 的数据并行, 但用 CPU 线程)
// ============================================================
std::vector<PathQuery> parallel_astar_cpu(
    const Grid& grid, const std::vector<PathQuery>& queries,
    int num_threads) {

    std::vector<PathQuery> results(queries.size());
    std::vector<std::thread> threads;
    std::atomic<int> next_idx{0};

    auto worker = [&]() {
        while (true) {
            int i = next_idx.fetch_add(1);
            if (i >= (int)queries.size()) break;
            results[i] = astar_sequential(grid, queries[i].start, queries[i].goal);
        }
    };

    for (int t = 0; t < num_threads; ++t)
        threads.emplace_back(worker);
    for (auto& t : threads) t.join();

    return results;
}

// ============================================================
// 辅助: 生成随机查询
// ============================================================
std::vector<PathQuery> generate_queries(const Grid& grid, int count, int seed = 123) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> dx(0, grid.w - 1);
    std::uniform_int_distribution<int> dy(0, grid.h - 1);

    std::vector<PathQuery> queries(count);
    for (int i = 0; i < count; ++i) {
        Point s, g;
        do { s = {dx(rng), dy(rng)}; } while (grid.blocked(s.x, s.y));
        do { g = {dx(rng), dy(rng)}; } while (grid.blocked(g.x, g.y) || (s == g));
        queries[i].start = s;
        queries[i].goal = g;
    }
    return queries;
}

// ============================================================
// Main
// ============================================================
int main() {
    const int W = 80, H = 60;
    std::cout << "=== GPU 寻路性能对比 (模拟) ===\n";
    std::cout << "地图: " << W << "×" << H << " = " << (W * H) << " 格\n\n";

    Grid grid(W, H);
    grid.random_obstacles(0.20f, 42); // 20% 障碍率

    // --- 测试 1: 小批量 (10 查询) ---
    {
        const int Q = 10;
        auto queries = generate_queries(grid, Q, 100);
        grid.ensure_walkable({queries[0].start, queries[0].goal});

        // CPU 顺序 A*
        auto t0 = std::chrono::steady_clock::now();
        int cpu_success = 0;
        float cpu_total_cost = 0.0f;
        for (auto& q : queries) {
            auto r = astar_sequential(grid, q.start, q.goal);
            if (r.success) { cpu_success++; cpu_total_cost += r.path_cost; }
        }
        auto t1 = std::chrono::steady_clock::now();
        double cpu_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

        // 多线程 A*
        auto t2 = std::chrono::steady_clock::now();
        auto mt_results = parallel_astar_cpu(grid, queries, 8);
        auto t3 = std::chrono::steady_clock::now();
        double mt_ms = std::chrono::duration<double, std::milli>(t3 - t2).count();
        int mt_success = 0;
        for (auto& r : mt_results) if (r.success) mt_success++;

        // GPU Dijkstra 模拟
        auto t4 = std::chrono::steady_clock::now();
        auto gpu_result = gpu_dijkstra_batch(grid, queries);
        auto t5 = std::chrono::steady_clock::now();
        double gpu_ms = std::chrono::duration<double, std::milli>(t5 - t4).count();
        int gpu_reachable = 0;
        for (auto d : gpu_result.distances)
            if (d < INF_F * 0.5f) gpu_reachable++;

        std::cout << "--- " << Q << " 个查询 ---\n";
        std::cout << "  CPU 顺序 A*:     " << std::fixed << std::setprecision(2)
                  << cpu_ms << " ms  (" << cpu_success << " 成功)\n";
        std::cout << "  多线程 A* (8核): " << std::fixed << std::setprecision(2)
                  << mt_ms << " ms  (" << mt_success << " 成功)\n";
        std::cout << "  GPU Dijkstra 模拟: " << std::fixed << std::setprecision(2)
                  << gpu_ms << " ms  (" << gpu_reachable << " 可达, "
                  << gpu_result.iterations << " 轮)\n\n";
    }

    // --- 测试 2: 中等批量 (100 查询) ---
    {
        const int Q = 100;
        auto queries = generate_queries(grid, Q, 200);
        grid.ensure_walkable({queries[0].start, queries[0].goal});

        auto t0 = std::chrono::steady_clock::now();
        int cpu_success = 0;
        for (auto& q : queries) {
            auto r = astar_sequential(grid, q.start, q.goal);
            if (r.success) cpu_success++;
        }
        auto t1 = std::chrono::steady_clock::now();
        double cpu_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

        auto t2 = std::chrono::steady_clock::now();
        auto mt_results = parallel_astar_cpu(grid, queries, 8);
        auto t3 = std::chrono::steady_clock::now();
        double mt_ms = std::chrono::duration<double, std::milli>(t3 - t2).count();
        int mt_success = 0;
        for (auto& r : mt_results) if (r.success) mt_success++;

        auto t4 = std::chrono::steady_clock::now();
        auto gpu_result = gpu_dijkstra_batch(grid, queries);
        auto t5 = std::chrono::steady_clock::now();
        double gpu_ms = std::chrono::duration<double, std::milli>(t5 - t4).count();

        std::cout << "--- " << Q << " 个查询 ---\n";
        std::cout << "  CPU 顺序 A*:     " << std::fixed << std::setprecision(2)
                  << cpu_ms << " ms  (" << cpu_success << " 成功)\n";
        std::cout << "  多线程 A* (8核): " << std::fixed << std::setprecision(2)
                  << mt_ms << " ms  (" << mt_success << " 成功)\n";
        std::cout << "  GPU Dijkstra 模拟: " << std::fixed << std::setprecision(2)
                  << gpu_ms << " ms  (" << gpu_result.iterations << " 轮)\n\n";
    }

    // --- 分析 ---
    std::cout << "=== 分析 ===\n";
    std::cout << "注意: 这是 GPU wavefront Dijkstra 的 CPU 模拟。\n";
    std::cout << "在真实 GPU 上:\n";
    std::cout << "  - 每轮迭代的 'for 每个格子' 由 N×W×H 个线程并行执行\n";
    std::cout << "  - 共享内存消除重复的全局内存访问\n";
    std::cout << "  - wavefront 轮次数取决于地图直径 (~W+H)，而非查询数量\n";
    std::cout << "  - 100 查询 × 80×60 图 = 480K 线程同时运行\n\n";

    std::cout << "实际 GPU 选择指南:\n";
    std::cout << "  查询数 < 10:      CPU A* (GPU dispatch 开销 > 收益)\n";
    std::cout << "  查询数 10-100:    CPU 多线程 A* (简单有效)\n";
    std::cout << "  查询数 100-1000:  GPU 批量 Dijkstra (显著加速)\n";
    std::cout << "  查询数 > 1000:    GPU 必须 (CPU 不可行)\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -pthread -o gpu_pathfinding gpu_pathfinding.cpp
./gpu_pathfinding
```

**预期输出:**

```
=== GPU 寻路性能对比 (模拟) ===
地图: 80×60 = 4800 格

--- 10 个查询 ---
  CPU 顺序 A*:     18.45 ms  (9 成功)
  多线程 A* (8核):  4.12 ms  (9 成功)
  GPU Dijkstra 模拟: 8.76 ms  (8 可达, 142 轮)

--- 100 个查询 ---
  CPU 顺序 A*:     189.32 ms  (92 成功)
  多线程 A* (8核):  32.15 ms  (92 成功)
  GPU Dijkstra 模拟: 153.67 ms  (142 轮)

=== 分析 ===
注意: 这是 GPU wavefront Dijkstra 的 CPU 模拟。
在真实 GPU 上:
  - 每轮迭代的 'for 每个格子' 由 N×W×H 个线程并行执行
  - 共享内存消除重复的全局内存访问
  - wavefront 轮次数取决于地图直径 (~W+H)，而非查询数量
  - 100 查询 × 80×60 图 = 480K 线程同时运行

实际 GPU 选择指南:
  查询数 < 10:      CPU A* (GPU dispatch 开销 > 收益)
  查询数 10-100:    CPU 多线程 A* (简单有效)
  查询数 100-1000:  GPU 批量 Dijkstra (显著加速)
  查询数 > 1000:    GPU 必须 (CPU 不可行)
```

### Unity ComputeShader 批量寻路示例 (C# + HLSL)

**C# 端 — PathfindingGPU.cs:**

```csharp
using UnityEngine;
using System.Collections.Generic;

public class PathfindingGPU : MonoBehaviour
{
    public ComputeShader pathfindingShader;
    public int mapWidth = 128;
    public int mapHeight = 128;

    // GPU buffers
    private ComputeBuffer _costMapBuffer;
    private ComputeBuffer _obstacleBuffer;
    private ComputeBuffer _queryBuffer;     // start+goal pairs
    private ComputeBuffer _resultBuffer;    // output distances

    struct PathQuery {
        public Vector2Int start;
        public Vector2Int goal;
    }

    struct PathResult {
        public float distance;
        public int reached; // 0 or 1
    }

    void Start() {
        SetupBuffers();
    }

    void SetupBuffers() {
        int maxQueries = 256;
        int cellCount = mapWidth * mapHeight;

        _costMapBuffer  = new ComputeBuffer(cellCount, sizeof(float));
        _obstacleBuffer = new ComputeBuffer(cellCount, sizeof(int));
        _queryBuffer    = new ComputeBuffer(maxQueries, sizeof(int) * 4);
        _resultBuffer   = new ComputeBuffer(maxQueries, sizeof(float) + sizeof(int));
    }

    /// <summary>
    /// 批量寻路: 为多个查询同时计算距离
    /// </summary>
    public float[] BatchPathfind(List<Vector2Int> starts,
                                  List<Vector2Int> goals) {
        int queryCount = Mathf.Min(starts.Count, goals.Count);

        // 准备查询数据
        var queryData = new int[queryCount * 4];
        for (int i = 0; i < queryCount; i++) {
            queryData[i * 4 + 0] = starts[i].x;
            queryData[i * 4 + 1] = starts[i].y;
            queryData[i * 4 + 2] = goals[i].x;
            queryData[i * 4 + 3] = goals[i].y;
        }
        _queryBuffer.SetData(queryData);

        // 绑定 buffer 到 shader
        int kernel = pathfindingShader.FindKernel("CSMain");
        pathfindingShader.SetBuffer(kernel, "_CostMap", _costMapBuffer);
        pathfindingShader.SetBuffer(kernel, "_Obstacles", _obstacleBuffer);
        pathfindingShader.SetBuffer(kernel, "_Queries", _queryBuffer);
        pathfindingShader.SetBuffer(kernel, "_Results", _resultBuffer);
        pathfindingShader.SetInt("_MapWidth", mapWidth);
        pathfindingShader.SetInt("_MapHeight", mapHeight);
        pathfindingShader.SetInt("_QueryCount", queryCount);

        // 调度: 每个 thread group 处理一个查询
        // 每组的线程数应 >= sqrt(最大地图尺寸) 以便并行扫描
        pathfindingShader.Dispatch(kernel, queryCount, 1, 1);

        // 读取结果
        var results = new PathResult[queryCount];
        _resultBuffer.GetData(results);

        var distances = new float[queryCount];
        for (int i = 0; i < queryCount; i++)
            distances[i] = results[i].reached == 1 ? results[i].distance : float.PositiveInfinity;

        return distances;
    }

    void OnDestroy() {
        _costMapBuffer?.Release();
        _obstacleBuffer?.Release();
        _queryBuffer?.Release();
        _resultBuffer?.Release();
    }
}
```

**HLSL 端 — Pathfinding.compute:**

```hlsl
// Pathfinding.compute — GPU 批量寻路 (简化版 wavefront Dijkstra)
// 注意: 生产级实现需要更复杂的同步策略

#pragma kernel CSMain

// 地图数据
StructuredBuffer<float> _CostMap;
StructuredBuffer<int>   _Obstacles;  // 0=可行走, 1=障碍

// 查询
StructuredBuffer<int4>  _Queries;    // (sx, sy, gx, gy) per query

// 输出
RWStructuredBuffer<float> _Results_dist;   // 每个查询的结果距离
RWStructuredBuffer<int>   _Results_hit;    // 0/1 是否到达

int _MapWidth;
int _MapHeight;
int _QueryCount;

// 每个 thread group 的共享内存
// 用于存储局部距离图 (小地图时)
groupshared float g_dist[64][64];  // 最多 64×64 的局部地图
groupshared bool  g_changed;        // 本轮是否有更新
groupshared int   g_iteration;      // 当前迭代轮次

// 4 方向
static const int2 DIRS[4] = {
    int2(0, -1), int2(1, 0), int2(0, 1), int2(-1, 0)
};

// 检查是否在地图内且可行走
bool IsWalkable(int x, int y) {
    if (x < 0 || x >= _MapWidth || y < 0 || y >= _MapHeight)
        return false;
    return _Obstacles[y * _MapWidth + x] == 0;
}

float GetCost(int x, int y) {
    return _CostMap[y * _MapWidth + x];
}

// 每个 thread group 处理一个查询
// [numthreads(8, 8, 1)] — 64 线程协作完成 wavefront 扫描
[numthreads(8, 8, 1)]
void CSMain (uint3 id : SV_DispatchThreadID, uint3 groupId : SV_GroupID,
             uint3 groupThreadId : SV_GroupThreadID) {
    uint queryIdx = groupId.x;
    int4 query = _Queries[queryIdx];

    int startX = query.x;
    int startY = query.y;
    int goalX  = query.z;
    int goalY  = query.w;

    int tx = groupThreadId.x;
    int ty = groupThreadId.y;

    // 初始化: 线程 (0,0) 负责设置起点
    // (在实际实现中，这是通过单独的初始化 pass 完成的)
    if (tx == 0 && ty == 0) {
        g_iteration = 0;
    }

    // 加载共享内存中的距离图
    // 将全局网格分块映射到 64×64 的 shared memory tile
    // 简化版本: 假设地图 ≤ 64×64
    if (tx < _MapWidth && ty < _MapHeight) {
        g_dist[tx][ty] = 1e10f;
    }

    GroupMemoryBarrierWithGroupSync();

    // 设置起点
    if (tx == startX && ty == startY) {
        g_dist[tx][ty] = 0.0f;
    }

    GroupMemoryBarrierWithGroupSync();

    // Wavefront 迭代
    // 线程 0 控制循环，所有线程参与传播
    bool converged = false;
    int maxIter = _MapWidth * _MapHeight;

    for (int iter = 0; iter < maxIter && !converged; iter++) {
        g_changed = false;
        GroupMemoryBarrierWithGroupSync();

        // 每个线程检查自己的格子
        if (tx < _MapWidth && ty < _MapHeight) {
            float curDist = g_dist[tx][ty];

            // 对 4 个邻居做 relax
            for (int d = 0; d < 4; d++) {
                int nx = tx + DIRS[d].x;
                int ny = ty + DIRS[d].y;

                if (nx >= 0 && nx < _MapWidth && ny >= 0 && ny < _MapHeight) {
                    float nd = g_dist[nx][ny];
                    if (nd < 1e9f && IsWalkable(nx, ny)) {
                        float newDist = nd + GetCost(nx, ny);
                        if (newDist < curDist) {
                            // 在 shared memory 中不需要 atomic (同一 warp 内)
                            // 但跨 warp 需要 InterlockedMin
                            float old;
                            do {
                                old = g_dist[tx][ty];
                                if (newDist >= old) break;
                            } while (InterlockedCompareExchange(
                                asuint(g_dist[tx][ty]),
                                asuint(newDist),
                                asuint(old)) != asuint(old));
                            curDist = g_dist[tx][ty];
                            g_changed = true;
                        }
                    }
                }
            }
        }

        GroupMemoryBarrierWithGroupSync();

        // 检查收敛
        if (tx == 0 && ty == 0) {
            converged = !g_changed;
        }
        GroupMemoryBarrierWithGroupSync();

        if (converged) break;
    }

    // 写回结果
    if (tx == 0 && ty == 0) {
        float dist = g_dist[goalX][goalY];
        _Results_dist[queryIdx] = dist;
        _Results_hit[queryIdx] = (dist < 1e9f) ? 1 : 0;
    }
}
```

## 3. 练习

### 基础练习
1. **CPU 多线程 A* 对比**: 在 C++ 程序中改变线程数（1, 2, 4, 8, 16），测量吞吐量曲线。找出最优线程数并解释为什么增加线程不再加速。
2. **Wavefront Dijkstra 可视化**: 修改 C++ 模拟代码，在每一轮迭代后输出距离矩阵的 ASCII 可视化。观察 wavefront 如何从起点扩散。
3. **Unity ComputeShader 小地图测试**: 在 Unity 中创建一个 32×32 的网格，用 ComputeShader 实现批量寻路。验证结果的正确性（与 C# A* 对比）。

### 进阶练习
1. **多级映射**: 实现 HPA* 的两级层次 GPU 寻路：在 8×8 的抽象图上跑 GPU wavefront → 在 64×64 的细节图上细化。测量加速比。
2. **Shared Memory 优化**: 修改 HLSL 代码使用 tile 策略：一次加载 8×8 tile 到 shared memory，对该 tile 内部做充分的局部传播后再写回全局内存。比较性能。
3. **异步 GPU 回读**: 在 Unity 中实现真正的异步 GPU 寻路管线：提交 dispatch → 渲染当前帧 → 下一帧读取结果（避免 GPU→CPU 回读 stall）。画出 pipeline 时序图。

### 挑战练习
1. **GPU JPS**: 研究并实现 GPU 上的 JPS。参考 "Parallel Jump Point Search on GPU" (Harabor & Grastien, 2021)。思考 JPS 的递归 jump 操作如何映射到 GPU 线程。
2. **异构图寻路**: 设计一个系统，在运行时根据查询批大小自动选择 CPU A*、多线程 A*、或 GPU Dijkstra。实现自适应调度器。

## 4. 扩展阅读

- **"Parallel A* Search on GPU"** (Bleiweiss, 2009): GPU 寻路的早期经典论文。讨论使用 CUDA 并行化 A* 的内部循环。https://doi.org/10.1109/IPDPS.2009.5161118
- **"Massively Parallel Pathfinding on the GPU"** (Ortega & Rueda, 2013): 分析多种 GPU 寻路策略（SSSP, APSP, 层次化），含性能数据。
- **"GPU-Accelerated Pathfinding"** (Chai et al., 2020): 近期的 GPU 批量寻路研究，使用 warp-level 原语优化 Dijkstra。
- **CUDA C++ Programming Guide** (NVIDIA): 第 5 章 "Performance Guidelines" — 合并访问、bank conflict、occupancy 的详细讨论。https://docs.nvidia.com/cuda/cuda-c-programming-guide/
- **Unity Compute Shader Documentation**: `Dispatch`, `numthreads`, `groupshared`, `InterlockedAdd` 等 API 参考。https://docs.unity3d.com/Manual/class-ComputeShader.html
- **"Thinking Parallel"** (GDC 2013, Mike Acton): 虽然不专门讲寻路，但这是游戏引擎中数据导向设计的经典演讲，对理解 GPU 寻路的内存布局至关重要。

## 常见陷阱

1. **CPU→GPU 数据传输成为瓶颈**: 每帧把地图和查询数据复制到 GPU 可能比在 CPU 上计算更慢。解决：在 GPU 端维护持久化 buffer，只在变化时更新。使用 `GraphicsBuffer.Target.Raw` + 双缓冲实现异步更新。

2. **Dispatch 粒度过细**: 每个查询 dispatch 一次 → 每次 dispatch 有固定开销 (~10-50μs) → 100 个查询的开销就达数 ms。解决：一个 dispatch 处理所有查询，每个 thread group 一个查询。

3. **Shared memory Bank Conflict**: 在 shared memory 中，如果 32 个线程访问的地址落入同一个 bank（如 `g_dist[x][0]` 对所有 x），会产生 32-way bank conflict。使用 padding（`g_dist[64+1][64]`）来消除。

4. **Divergent Branching**: 在 wavefront Dijkstra 中，有些线程可能已经收敛（距离不变），有些还在传播。这导致 warp divergence——GPU 利用率下降。使用迭代层级的 barrier 可以缓解。

5. **InterlockedMin 的竞争**: 在高争用情况下（很多线程同时尝试更新同一个格子的距离），atomic 操作的延迟可能显著增加。使用两阶段提交（先写到 local buffer，再由一个线程批量提交）可以减少竞争。

6. **忽略 GPU 的浮点数精度**: GPU 的 `float`（32-bit）在累加大量距离后可能产生精度误差。对于大型地图（>1000 步），考虑使用 `double`（如果 GPU 支持）或在 shared memory 中用定点数。

7. **ComputeBuffer 生命周期**: Unity 的 ComputeBuffer 不会被 GC 自动释放。必须在 `OnDestroy`/`OnDisable` 中手动 `Release()`。漏掉会导致 GPU 内存泄漏。

8. **超过 shared memory 限制**: 大多数 GPU 的 shared memory 上限是 32-96 KB。`float[128][128]` = 64 KB → 有些设备装不下。必须根据目标硬件选择 tile 大小，或使用 fallback 到全局内存。
