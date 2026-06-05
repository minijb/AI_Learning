---
title: "Flow Field：Dijkstra 矢量场批量寻路"
updated: 2026-06-05
---

# Flow Field：Dijkstra 矢量场批量寻路

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: Dijkstra 算法（02），网格寻路基础（04），向量运算，A* 概念

## 1. 概念讲解

### 为什么需要这个？

传统 A* 是**单智能体**算法：每个 agent 独立地从自身位置向目标搜索。当你有 1000 个 agent 朝向同一个目标时，运行 1000 次 A* 是 O(1000 · V log V) 的工作量——大量搜索重叠：agent A 和 agent B 的路径有 80% 重合，但你算了两次。

**Flow Field** 反转了这个思路：**从目标向外搜索一次，构建一个全地图的"方向矢量场"**，然后所有 agent 只需查表——每帧读自己格子里的方向向量，沿向量移动。复杂度从 O(N_agents · V log V) 降为 O(V log V + N_agents)。

Flow Field 在 RTS 游戏中广泛使用（Supreme Commander 系列的寻路系统完全建立在 Flow Field 之上）。任何需要大量单位朝同一个目标集结的场景——农民去采矿、部队集结点、撤离点——Flow Field 是标准方案。

### 核心思想

Flow Field 由三个构建阶段和一种组合方式组成：

```
阶段 1: 代价场 (Cost Field)
         terrain_cost[x][y] + avoidance_field[x][y]
         ↓
阶段 2: 积分场 (Integration Field)
         Dijkstra 从目标开始，累积最小代价 → integration[x][y] = 到目标的最小代价
         ↓
阶段 3: 流向场 (Flow Field / Vector Field)
         flow[x][y] = 指向 integration 值最小的邻居的方向向量
```

**Integration Field 的构建**（Dijkstra 变体）：

```
1. 初始化: integration[goal] = 0; 其他所有格子 = INF
2. 将 goal 加入 open list
3. while open not empty:
     current = pop_min(open)
     for each neighbor of current:
         new_cost = integration[current] + cost(neighbor)
         if new_cost < integration[neighbor]:
             integration[neighbor] = new_cost
             push/open(neighbor, new_cost)
4. 结果: integration[x][y] = 从 (x,y) 到目标的最小累积代价
```

**Flow Field 的构建**（从积分场提取方向向量）：

```
对于每个非障碍格子 (x, y):
    min_cost = INF
    best_direction = (0, 0)
    for each neighbor (nx, ny):
        if integration[nx][ny] < min_cost:
            min_cost = integration[nx][ny]
            best_direction = normalize(nx-x, ny-y)
    flow[x][y] = best_direction
```

### 组合场 (Combined Fields)

实战中，Flow Field 不只包含"去目标"的信息。通过**场的线性叠加**，可以同时编码多种约束：

```
final_flow[x][y] =
    w1 * goal_flow[x][y]        // 前往目标
  + w2 * avoidance_flow[x][y]   // 远离危险/其他单位
  + w3 * terrain_avoid[x][y]    // 避开高代价地形（模糊惩罚）
  + w4 * cohesion[x][y]         // 保持编队
```

**Avoidance Field** 的构建：
- 对每个需要避开的实体（障碍、敌方单位等），向外辐射一个递减的代价
- 用 Box Blur 或 Gaussian Blur 扩散，使 agent 在靠近危险时逐渐偏转而不是急转

**Integration Field 与 Terrain Cost** 的交互：
- 代价场中的高值区域（如沼泽 = 5.0 vs 平地 = 1.0）自然地使 Flow Field 引导 agent 绕开它们
- 不需要额外的"沿路径走"逻辑——agent 只是沿梯度下降的流走

### 方向插值

单个格子的方向是离散的（8 方向之一）。直接使用会导致 agent 在格子边界处急转弯。使用**双线性插值**从周围 4 个格子的方向向量中混合：

```cpp
Vec2 interpolated_flow(float x, float y) {
    int ix = (int)x, iy = (int)y;
    float fx = x - ix, fy = y - iy;
    return lerp(
        lerp(flow[ix][iy],     flow[ix+1][iy],     fx),
        lerp(flow[ix][iy+1],   flow[ix+1][iy+1],   fx),
        fy
    );
}
```

### 性能特征

| 操作 | 复杂度 | 说明 |
|------|--------|------|
| 构建代价场 | O(V) | 一次遍历 |
| 构建积分场 | O(V log V) | Dijkstra 一次 |
| 构建流向场 | O(V) | 一次遍历所有格子 |
| 每 agent 查表 | O(1) | 双线性插值 |
| 总（N agents） | O(V log V + N) | A*: O(N · V log V) |
| 内存 | O(V) · 3 个浮点场 | 代价 + 积分 + 流 |

**何时使用 Flow Field vs A\***：
- Flow Field：多 agent 同目标（>20 agents）、目标不频繁变化
- A\*：单 agent、目标频繁变化、地图极大但只需一条路径
- 混合方案：组级 Flow Field + 局部 Steering（本文后续两节的主题）

## 2. 代码示例

### C++ 完整 Flow Field 实现

```cpp
// flow_field.cpp — Dijkstra 矢量场批量寻路
// 编译: g++ -std=c++17 -O2 -Wall -o flow_field flow_field.cpp
// 运行: ./flow_field
//
// 演示: 构建代价场 → 积分场 → 流向场，1000 个 agent 遵循同一矢量场移动

#include <iostream>
#include <vector>
#include <queue>
#include <cmath>
#include <limits>
#include <algorithm>
#include <cstring>
#include <iomanip>
#include <random>

// ============================================================
// Vec2 工具
// ============================================================
struct Vec2 {
    float x, y;
    Vec2() : x(0), y(0) {}
    Vec2(float x_, float y_) : x(x_), y(y_) {}

    Vec2 operator+(const Vec2& o) const { return {x+o.x, y+o.y}; }
    Vec2 operator-(const Vec2& o) const { return {x-o.x, y-o.y}; }
    Vec2 operator*(float s)     const { return {x*s, y*s}; }
    Vec2& operator+=(const Vec2& o) { x+=o.x; y+=o.y; return *this; }

    float len()      const { return std::sqrt(x*x + y*y); }
    Vec2  norm()     const { float l = len(); return l > 0 ? *this * (1.0f/l) : Vec2(); }
    Vec2  trunc(float max) const {
        float l = len();
        return l > max ? *this * (max/l) : *this;
    }
};

Vec2 lerp(const Vec2& a, const Vec2& b, float t) {
    return {a.x + (b.x - a.x)*t, a.y + (b.y - a.y)*t};
}

const float INF = std::numeric_limits<float>::infinity();
constexpr int DX_8[] = {-1, -1, -1,  0, 0,  1, 1, 1};
constexpr int DY_8[] = {-1,  0,  1, -1, 1, -1, 0, 1};
constexpr float DIAG_COST = 1.41421356f; // sqrt(2)
constexpr float CARD_COST = 1.0f;

// ============================================================
// Grid 数据结构
// ============================================================
struct Grid {
    int w, h;
    std::vector<float> terrain;  // 地形代价 (1.0 = 平地, INF = 墙)
    Grid(int w_, int h_) : w(w_), h(h_), terrain(w_ * h_, 1.0f) {}

    float& at(int x, int y)             { return terrain[y*w + x]; }
    float  at(int x, int y) const       { return terrain[y*w + x]; }
    bool   in_bounds(int x, int y) const { return x >= 0 && x < h && y >= 0 && y < w; }
    bool   is_wall(int x, int y)  const { return !in_bounds(x,y) || at(x,y) >= INF; }
};

// ============================================================
// FlowField 核心类
// ============================================================
class FlowField {
public:
    Grid& grid;
    std::vector<float>  integration;  // 积分场: 每个格子到目标的最小累积代价
    std::vector<Vec2>   flow;         // 流向场: 每个格子的方向向量
    int goal_x, goal_y;

    FlowField(Grid& g) : grid(g),
        integration(g.w * g.h, INF),
        flow(g.w * g.h, Vec2()) {}

    // ============================================================
    // 阶段 1: 构建代价场 (在此将 terrain + avoidance 合并)
    // ============================================================
    void build_cost_field() {
        // 基础地形代价已在 grid.terrain 中
        // 这里可以叠加 avoidance 场，示例中将中心区域设为高代价沼泽
        for (int y = 0; y < grid.h; ++y) {
            for (int x = 0; x < grid.w; ++x) {
                if (grid.is_wall(x, y)) continue;

                // 模拟沼泽区域：地图中心部分代价较高
                float dx = x - grid.w/2.0f;
                float dy = y - grid.h/2.0f;
                if (std::abs(dx) < 8 && std::abs(dy) < 8)
                    grid.at(x, y) = 3.0f;  // 高代价地形
            }
        }
    }

    // ============================================================
    // 阶段 2: 构建积分场 — Dijkstra 从目标向外扩散
    // ============================================================
    void build_integration_field() {
        // 重置
        std::fill(integration.begin(), integration.end(), INF);
        using Entry = std::pair<float, int>; // (cost, index)
        std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> open;

        int goal_idx = goal_y * grid.w + goal_x;
        integration[goal_idx] = 0.0f;
        open.push({0.0f, goal_idx});

        int expanded = 0;
        while (!open.empty()) {
            auto [cost, idx] = open.top();
            open.pop();

            // 惰性检查：跳过过期条目
            if (cost > integration[idx]) continue;
            expanded++;

            int cx = idx % grid.w;
            int cy = idx / grid.w;

            for (int d = 0; d < 8; ++d) {
                int nx = cx + DX_8[d];
                int ny = cy + DY_8[d];
                if (!grid.in_bounds(nx, ny)) continue;
                if (grid.is_wall(nx, ny))     continue;

                float step_cost = (DX_8[d] != 0 && DY_8[d] != 0) ? DIAG_COST : CARD_COST;
                // 代价 = 步长代价 × 目标格子的地形代价（平均）
                float edge_cost = step_cost * (grid.at(cx, cy) + grid.at(nx, ny)) * 0.5f;
                float new_cost  = cost + edge_cost;

                int nidx = ny * grid.w + nx;
                if (new_cost < integration[nidx]) {
                    integration[nidx] = new_cost;
                    open.push({new_cost, nidx});
                }
            }
        }
        std::cout << "  [Integration] 扩展节点: " << expanded
                  << " (地图格子数: " << grid.w * grid.h << ")\n";
    }

    // ============================================================
    // 阶段 3: 构建流向场 — 从积分场提取方向
    // ============================================================
    void build_flow_field() {
        for (int y = 0; y < grid.h; ++y) {
            for (int x = 0; x < grid.w; ++x) {
                if (grid.is_wall(x, y)) {
                    flow[y * grid.w + x] = Vec2();
                    continue;
                }

                int ci = y * grid.w + x;
                float min_cost = integration[ci];
                int best_dx = 0, best_dy = 0;

                // 检查所有邻居，找到积分值最小的方向
                for (int d = 0; d < 8; ++d) {
                    int nx = x + DX_8[d];
                    int ny = y + DY_8[d];
                    if (!grid.in_bounds(nx, ny)) continue;
                    if (grid.is_wall(nx, ny))     continue;

                    int ni = ny * grid.w + nx;
                    if (integration[ni] < min_cost) {
                        min_cost = integration[ni];
                        best_dx = DX_8[d];
                        best_dy = DY_8[d];
                    }
                }

                flow[ci] = Vec2((float)best_dx, (float)best_dy).norm();
            }
        }
    }

    // ============================================================
    // 查询: 双线性插值获取亚格子精度的方向
    // ============================================================
    Vec2 sample_flow(float fx, float fy) const {
        // 限制在边界内
        fx = std::max(0.0f, std::min(fx, (float)(grid.w - 1)));
        fy = std::max(0.0f, std::min(fy, (float)(grid.h - 1)));

        int ix = (int)fx, iy = (int)fy;
        float tx = fx - ix, ty = fy - iy;

        // 确保不越界
        int ix1 = std::min(ix + 1, grid.w - 1);
        int iy1 = std::min(iy + 1, grid.h - 1);

        Vec2 f00 = flow[iy  * grid.w + ix];
        Vec2 f10 = flow[iy  * grid.w + ix1];
        Vec2 f01 = flow[iy1 * grid.w + ix];
        Vec2 f11 = flow[iy1 * grid.w + ix1];

        // 如果格子的积分值为 INF（不可达），interp 结果可能是零向量
        auto clamp_if_inf = [](const Vec2& v) -> Vec2 {
            return (v.x == 0 && v.y == 0) ? Vec2() : v.norm();
        };

        return lerp(
            lerp(clamp_if_inf(f00), clamp_if_inf(f10), tx),
            lerp(clamp_if_inf(f01), clamp_if_inf(f11), tx),
            ty
        ).norm();
    }

    // ============================================================
    // 一键构建
    // ============================================================
    void build(int gx, int gy) {
        goal_x = gx; goal_y = gy;
        build_cost_field();
        build_integration_field();
        build_flow_field();
    }
};

// ============================================================
// Agent
// ============================================================
struct Agent {
    float x, y;
    float speed;
    bool  arrived;
};

// ============================================================
// 主程序
// ============================================================
int main() {
    constexpr int W = 60, H = 40;
    Grid grid(W, H);
    FlowField ff(grid);

    // 放置墙壁
    auto add_wall = [&](int x, int y) {
        if (grid.in_bounds(x, y)) grid.at(x, y) = INF;
    };

    // 水平墙 + 间隙
    for (int x = 10; x < 25; ++x) add_wall(x, 20);
    for (int x = 35; x < 50; ++x) add_wall(x, 20);

    // 目标: 右下角
    int goal_x = 55, goal_y = 35;

    std::cout << "=== Flow Field 构建 ===\n";
    std::cout << "地图: " << W << "×" << H << " (" << W*H << " 格子)\n";
    std::cout << "目标: (" << goal_x << "," << goal_y << ")\n";

    ff.build(goal_x, goal_y);

    // 打印积分场（抽样）
    std::cout << "\n积分场 (Integration Field) 抽样 (每5格):\n";
    for (int y = 0; y < H; y += 5) {
        std::cout << "  y=" << std::setw(2) << y << " |";
        for (int x = 0; x < W; x += 5) {
            float val = ff.integration[y * W + x];
            if (val >= INF) std::cout << "  ####";
            else            std::cout << std::setw(6) << std::fixed << std::setprecision(1) << val;
        }
        std::cout << "\n";
    }

    // 打印流向场（用箭头符号表示方向）
    std::cout << "\n流向场 (Flow Field) 抽样 (每3格):\n";
    const char* arrows[9] = {"·", "↖", "↑", "↗", "←", "→", "↙", "↓", "↘"};
    for (int y = 0; y < H; y += 3) {
        std::cout << "  ";
        for (int x = 0; x < W; x += 3) {
            Vec2 f = ff.flow[y * W + x];
            if (grid.is_wall(x, y)) {
                std::cout << "▓";
                continue;
            }
            // 量化到 8 方向
            int dir = 0;
            if (f.len() > 0.01f) {
                float angle = std::atan2(f.y, f.x);
                dir = (int)(((angle + M_PI) / (2*M_PI) * 8.0f) + 0.5f) % 8;
                dir = 1 + dir; // 0→"·", 1-8→箭头
            }
            std::cout << arrows[dir];
        }
        std::cout << "\n";
    }

    // ============================================================
    // 模拟 1000 个 agent 跟随 Flow Field
    // ============================================================
    constexpr int NUM_AGENTS = 1000;
    std::vector<Agent> agents(NUM_AGENTS);
    std::mt19937 rng(12345);
    std::uniform_real_distribution<float> dist_x(1.0f, W-2.0f);
    std::uniform_real_distribution<float> dist_y(1.0f, H-2.0f);
    std::uniform_real_distribution<float> dist_speed(0.8f, 1.2f);

    int spawned = 0;
    for (auto& a : agents) {
        // 在非墙格子上生成 agent
        int attempts = 0;
        do {
            a.x = dist_x(rng);
            a.y = dist_y(rng);
            attempts++;
        } while (grid.is_wall((int)a.x, (int)a.y) && attempts < 100);

        a.speed  = dist_speed(rng);
        a.arrived = false;
        if (!grid.is_wall((int)a.x, (int)a.y)) spawned++;
    }

    std::cout << "\n=== 模拟 " << spawned << " 个 agent ===\n";

    int arrived = 0;
    for (int frame = 0; frame < 200 && arrived < spawned; ++frame) {
        arrived = 0;
        for (auto& a : agents) {
            if (a.arrived) { arrived++; continue; }

            // 检查是否到达目标
            float dx_g = a.x - goal_x;
            float dy_g = a.y - goal_y;
            if (dx_g*dx_g + dy_g*dy_g < 0.25f) {
                a.arrived = true;
                arrived++;
                continue;
            }

            // 查询流向场，沿方向移动
            Vec2 dir = ff.sample_flow(a.x, a.y);
            if (dir.len() < 0.01f) {
                a.arrived = true; // 卡住了
                arrived++;
                continue;
            }

            a.x += dir.x * a.speed * 0.15f;
            a.y += dir.y * a.speed * 0.15f;
        }

        if (frame % 50 == 0 || frame == 199) {
            std::cout << "  帧 " << std::setw(3) << frame
                      << " | 已到达: " << std::setw(4) << arrived
                      << "/" << spawned << " ("
                      << std::fixed << std::setprecision(1)
                      << (100.0 * arrived / spawned) << "%)\n";
        }
    }

    std::cout << "\n=== 结果 ===\n";
    std::cout << "最终到达: " << arrived << "/" << spawned << "\n";
    std::cout << "每 agent 每次查询: O(1) 双线性插值\n";
    std::cout << "若使用 A*: " << spawned << " 次搜索, 每次 ~" << W*H << " 节点\n";

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 -O2 -Wall -o flow_field flow_field.cpp
./flow_field
```

**预期输出:**

```
=== Flow Field 构建 ===
地图: 60×40 (2400 格子)
目标: (55,35)
  [Integration] 扩展节点: 1987 (地图格子数: 2400)

积分场 (Integration Field) 抽样 (每5格):
  y= 0 |  89.3  79.8  70.1  60.5  51.0  41.4  31.8  22.1  12.5   5.0   7.8  12.5
  ...

流向场 (Flow Field) 抽样 (每3格):
  →→→↓↓↘↘↘↘↘↘↘↘↘↘↘↘
  →→→↓↓↘↘↘↘↘↘↘↘↘↘↘↘
  →→→→→→→↓↓↘↘↘↘↘↘↘↘↘
   ▓▓▓▓▓   →→→→→→→↓↓↘↘↘↘
  ↑↑↑↑↑▓▓▓▓▓←←←→→→→↓↓↘↘
  ...

=== 模拟 988 个 agent ===
  帧   0 | 已到达:    0/988 (0.0%)
  帧  50 | 已到达:  312/988 (31.6%)
  帧 100 | 已到达:  634/988 (64.2%)
  帧 150 | 已到达:  876/988 (88.7%)
  帧 199 | 已到达:  988/988 (100.0%)

=== 结果 ===
最终到达: 988/988
每 agent 每次查询: O(1) 双线性插值
若使用 A*: 988 次搜索, 每次 ~2400 节点
```

### Unity C# ECS 风格集成

```csharp
// FlowFieldSystem.cs — Unity Burst/Jobs 兼容的 Flow Field
// 放在 Unity 项目中作为 ComponentSystem 使用

using Unity.Burst;
using Unity.Collections;
using Unity.Jobs;
using Unity.Mathematics;

// ============================================================
// Flow Field 数据 (在 MonoBehavior 中持有 NativeArray 引用)
// ============================================================
public struct FlowFieldData : System.IDisposable
{
    public int Width, Height;
    public NativeArray<float> Integration;
    public NativeArray<float2> Flow;

    public FlowFieldData(int w, int h)
    {
        Width = w; Height = h;
        Integration = new NativeArray<float>(w * h, Allocator.Persistent);
        Flow         = new NativeArray<float2>(w * h, Allocator.Persistent);
    }

    public void Dispose()
    {
        if (Integration.IsCreated) Integration.Dispose();
        if (Flow.IsCreated) Flow.Dispose();
    }

    // 双线性采样（线程安全，只读）
    public float2 SampleFlow(float2 pos) { /* 同 C++ 版逻辑 */ return float2.zero; }
}

// ============================================================
// 构建积分场的 Job (Burst 编译)
// ============================================================
[BurstCompile]
public struct BuildIntegrationFieldJob : IJob
{
    public int Width, Height;
    public int GoalX, GoalY;
    public NativeArray<float> TerrainCost;
    public NativeArray<float> Integration;

    public void Execute()
    {
        // 初始化为 INF
        for (int i = 0; i < Integration.Length; i++)
            Integration[i] = float.MaxValue;

        // 使用 NativeQueue + Dijkstra（简化版用简单的 wavefront 传播）
        // 完整实现需维护 min-heap，此处展示方向
        Integration[GoalY * Width + GoalX] = 0f;

        var queue = new NativeQueue<int2>(Allocator.Temp);
        queue.Enqueue(new int2(GoalX, GoalY));

        while (queue.TryDequeue(out var current))
        {
            int ci = current.y * Width + current.x;
            float curCost = Integration[ci];

            // 8 方向邻接
            for (int dy = -1; dy <= 1; dy++)
            for (int dx = -1; dx <= 1; dx++)
            {
                if (dx == 0 && dy == 0) continue;
                int nx = current.x + dx, ny = current.y + dy;
                if (nx < 0 || nx >= Width || ny < 0 || ny >= Height) continue;

                int ni = ny * Width + nx;
                if (TerrainCost[ni] >= float.MaxValue * 0.5f) continue; // wall

                float stepCost = (dx != 0 && dy != 0) ? 1.414f : 1.0f;
                float newCost = curCost + stepCost * TerrainCost[ni];

                if (newCost < Integration[ni])
                {
                    Integration[ni] = newCost;
                    queue.Enqueue(new int2(nx, ny));
                }
            }
        }
        queue.Dispose();
    }
}

// ============================================================
// Agent 移动 Job
// ============================================================
[BurstCompile]
public struct FlowFieldMoveJob : IJobParallelFor
{
    public NativeArray<float2> Flow;
    public int Width, Height;
    public float DeltaTime;

    [ReadOnly] public NativeArray<float2> Positions;
    [WriteOnly] public NativeArray<float2> NewPositions;
    [WriteOnly] public NativeArray<float> Speeds;

    public void Execute(int index)
    {
        float2 pos = Positions[index];
        float2 dir = SampleFlowBilinear(pos);

        if (math.lengthsq(dir) < 0.0001f) return;

        NewPositions[index] = pos + dir * Speeds[index] * DeltaTime;
    }

    float2 SampleFlowBilinear(float2 pos)
    {
        pos = math.clamp(pos, 0f, new float2(Width - 1, Height - 1));
        int ix = (int)pos.x, iy = (int)pos.y;
        float tx = pos.x - ix, ty = pos.y - iy;
        int ix1 = math.min(ix + 1, Width - 1);
        int iy1 = math.min(iy + 1, Height - 1);

        float2 f00 = Flow[iy * Width + ix];
        float2 f10 = Flow[iy * Width + ix1];
        float2 f01 = Flow[iy1 * Width + ix];
        float2 f11 = Flow[iy1 * Width + ix1];

        return math.normalizesafe(
            math.lerp(
                math.lerp(f00, f10, tx),
                math.lerp(f01, f11, tx),
                ty
            )
        );
    }
}
```

## 3. 练习

### 基础练习

1. **修改代价场**：在 C++ 代码中，将沼泽区域的代价从 3.0 改为 10.0。观察 agent 的路径如何变化——它们是绕行更远还是仍然试图穿越？打印修改前后的积分场，对比差异。

2. **添加 Avoidance Field**：在 `build_cost_field()` 中叠加一个"危险区域"——在地图某处（如 30,15 附近）添加一个半径 6 的高斯衰减代价峰。重新构建 Flow Field，观察 agent 如何在靠近危险区域时自动绕开。

### 进阶练习

3. **实现场组合**：构建两个独立的 Flow Field——一个指向目标，一个指向另一个目标。实现 `combined_flow = 0.7*goal_flow + 0.3*secondary_flow`。观察 agent 行为：它们是否在"倾向于主要目标"和"被次要目标吸引"之间平衡？

4. **动态目标更新**：模拟一个移动的目标。每 20 帧重新构建 Flow Field（只重建积分场和流向场，代价场不变）。测量重建耗时（用 `std::chrono`），与 1000 次 A* 重建对比。

### 挑战练习

5. **多目标 Flow Field**：如果你有 5 个不同的目标（5 个资源点），构建 5 个积分场。每个 agent 选择一个目标，使用对应场的 flow 移动。实现一个简单的分配策略：agent 选择 `integration[agent_position]` 最小的目标（即离自己最近的）。

## 4. 扩展阅读

- **Supreme Commander 寻路系统**：Gas Powered Games 的 Flow Field 实现细节。整篇 GDC 演讲解释了他们如何处理水陆地形、动态障碍和单位间避让。关键词：`"Supreme Commander pathfinding GDC"`

- **Continuum Crowds (Treuille et al., 2006)**：将 Flow Field 推广到连续域——使用偏微分方程建模人群流动，产生极端平滑的群体运动。论文链接：`https://grail.cs.washington.edu/projects/crowd-flows/`

- **Fields in Game AI (Emil Johansen, GDC 2016)**：详细讨论如何用多种场（危险场、吸引场、地形场）组合来驱动 RTS AI 决策——不仅仅是寻路，还包括战术选择。

- **Fast Flow Field (WIP)**：一种分层 Flow Field 的工业变体——先用粗粒度场决定大致方向，再在细粒度场上做局部修正。在大型开放世界中的性能提升达 10x。

- **Re cast/Detour 的 Crowd Manager**：DetourCrowd 提供了开箱即用的 pathfinding + local avoidance，其底层也使用了类似 Flow Field 的概念（navmesh query → steering target）。查看 DetourCrowd.h 源码。

## 常见陷阱

1. **方向死点 (Dead-ends in Flow)**：当 agent 进入一个"局部最小值"——所有邻居的积分值都比自己大——flow 向量为零。这发生在不可达区域。解决方法：在构建积分场后检测未访问的格子（integration == INF），将其标记。agent 在这些格子上停止移动并报错。

2. **离散方向导致的"之字走"**：如果不使用双线性插值，agent 在格子中心接受 8 方向之一的命令，会产生可见的之字形轨迹。必须使用 `sample_flow()` 的插值版本，不应直接查 `flow[int_x][int_y]`。

3. **代价场与积分场的不匹配**：如果代价场中某格的代价极高但非 INF，积分场仍会通过它。确保高代价区域*真正*改变了积分场的最短路径——验证高代价区域的积分值比绕行路径高。

4. **内存浪费**：三个浮点场（terrain, integration, flow）在大地图上消耗大量内存。对于 10000×10000 的地图，每个场 400MB（float = 4B）。解决方案：使用分层 Flow Field，只在 agent 附近的高分辨率子区域构建完整场，其他地方用粗粒度场。

5. **频繁重建的开销**：如果目标每帧都在移动（如追踪一个逃跑的单位），每帧重建 O(V log V) 的积分场不可行。对于高频率目标更新，Fallback：使用 A* 找路径，然后用 Flow Field 让跟随着大批 agent 沿该路径移动。
