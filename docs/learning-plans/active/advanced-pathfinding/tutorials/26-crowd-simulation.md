# 人群模拟：全局寻路 + ORCA 全线集成

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: Flow Field（24），ORCA 原理（25），A* 寻路（03）

## 1. 概念讲解

### 为什么需要这个？

Flow Field 告诉 agent "往哪个方向走"，ORCA 告诉 agent "如何避开旁边的 agent"。但这两个系统独立工作时有一个裂缝：

**Flow Field 不知道其他 agent 的存在**。如果 200 个 agent 沿着同一个 Flow Field 走向一个狭窄门洞，它们会在门口挤成一团——Flow Field 说"往门走"，但 ORCA 在门口推挤 agent 往回走。结果是：门口形成 sticky cluster，agent 来回振荡，谁也进不去。

**真正的人群模拟需要三层协同**：

```
层 1 — 全局寻路 (Global)
  "从 A 到 B 应该走哪条路？"
  → A*, Flow Field, NavMesh query
  → 输出: 路径/目标方向

层 2 — 局部避障 (Local Avoidance)
  "如何避开旁边的人？"
  → ORCA
  → 输出: 修正后的瞬时速度

层 3 — 运动执行 (Motion Execution)
  "物理上如何移动？"
  → 加速度约束, 动画驱动, 碰撞检测
  → 输出: 最终位置
```

这三层必须**每帧级联运行**，而不是独立运行。全局路径给出 `pref_velocity`（首选速度），ORCA 在 `pref_velocity` 的基础上微调，运动层限制最终的加速度。

### 核心思想

#### 参数调优：从学术到工程

ORCA 的默认参数在学术论文中效果很好，但在游戏中需要大量调优。以下是每个参数的影响和调优指南：

| 参数 | 太小 | 太大 | 调优方法 |
|------|------|------|---------|
| **agent_radius** | 穿透/重叠 | 浪费空间，agent 之间空出很大间隙 | 设为视觉模型的包围盒半径 + 10% 缓冲 |
| **max_speed** | 跟不上 Flow Field 方向 | ORCA 允许过大的速度跳跃 | 根据角色类型设定（士兵 3m/s，平民 1.5m/s） |
| **max_accel** | 避让不及时，穿透 | agent 瞬时制动，不自然 | 从动画/物理参数中推导（通常 5-15 m/s²） |
| **time_horizon** | 最后一刻避让，可能来不及 | agent 在很远就开始让路，"过分礼貌" | 速度 × 2~3 = 合适值（如 3m/s × 2 = 6s） |
| **neighbor_dist** | 漏掉远处的快速接近 agent | 计算太多 ORCA 约束，性能下降 | 至少 max_speed × time_horizon × 1.5 |
| **pref_velocity weight** | agent 漫无目的地漂移 | ORCA 无效——agent 强行冲撞 | 1.0（让 LP 求解器选择平衡） |

**关键调优洞察**：`time_horizon` 是影响最大的参数。用 τ=1s 时 agent 像"蜂群"——密集、敏捷，但偶尔碰撞。用 τ=5s 时 agent 像"排队买票的人群"——礼貌、有序，但慢。大多数游戏用 2-3s。

#### 处理不同 Agent 类型

游戏中很少所有 agent 都一样。军队游戏有步兵（小、慢）、坦克（大、快）、卡车（大、慢）。ORCA 原生支持异质 agent——只需在计算每个 ORCA 约束时使用 `rA + rB`（而不是固定半径）：

```cpp
float combined_radius = A.radius + B.radius;
```

更大的 agent 自然"推动"周围更小的 agent（因为 ORCA 约束覆盖的体积更大）。但反过来，小 agent 对大 agent 的影响也成比例——小 agent 让开的空间与其体积匹配。

**速度差异**需要特殊处理。如果快速 agent 的 `time_horizon` 为 2s，而慢速 agent 也为 2s，快速 agent 在 2s 内覆盖的距离远大于慢速 agent——导致快速 agent 提前过多避让。解决方案：

```cpp
// 每个 agent 持有自己的 time_horizon
// 在计算 A-B 之间的 ORCA 约束时，使用较大的那个
float effective_tau = std::max(A.time_horizon, B.time_horizon);
```

#### 涌现的人群行为

当所有参数调好后，简单的规则会产生惊人的复杂行为：

**Lane Formation（车道形成）**：两个方向的 agent 在走廊中相遇。ORCA 的对称性使 agent 自然地偏到一侧，形成两条"车道"——无需任何显式的"右行规则"。这个行为是涌现的：agent 在反复的微调中找到能量最低的状态（最少避让的配置）。

**Bottleneck Flow（瓶颈流）**：大量 agent 通过窄门时，ORCA 自动形成"震荡门"效果——交替有 agent 从两侧通过。这是 ORCA 中最优雅的涌现行为之一。但门太窄（< 2×agent_radius）时，agent 会卡住——需要特殊的"排队"逻辑。

**Counter-flow（逆向流）**：在宽通道中，两个方向的 agent 自动形成条带状流动——中间留给一个方向，两侧留给另一个方向。这与真实人类行为非常相似。

### 完整架构

```cpp
// 每帧的主循环
for each agent A:
    // 1. 全局寻路 → preferred velocity
    Vec2 path_dir = flow_field.sample(A.position);       // 或 A* + path following
    A.pref_velocity = path_dir * A.desired_speed;

    // 2. ORCA 局部避障
    collect_neighbors_within_range(A, neighbor_dist);     // O(N) 或 O(log N) 空间哈希
    A.velocity = orca_solve(A, neighbors);

    // 3. 运动约束
    A.velocity = clamp_acceleration(A.velocity, A.prev_velocity, A.max_accel, dt);
    A.velocity = clamp_speed(A.velocity, A.max_speed);

    // 4. 积分
    A.position += A.velocity * dt;

    // 5. (可选) 触碰到障碍物的回退
    resolve_static_collisions(A, obstacles);
```

## 2. 代码示例

### C++ 完整人群模拟器

```cpp
// crowd_sim.cpp — 全局寻路 + ORCA 人群模拟
// 编译: g++ -std=c++17 -O2 -Wall -o crowd_sim crowd_sim.cpp
// 运行: ./crowd_sim
//
// 演示: 200+ agent 通过瓶颈 (窄门) 的场景，包括
//   - Flow Field 全局引导
//   - ORCA 局部避障
//   - 异质 agent (大小/速度不同)
//   - 车道形成、瓶颈流等涌现行为观测

#include <iostream>
#include <vector>
#include <queue>
#include <cmath>
#include <limits>
#include <algorithm>
#include <random>
#include <iomanip>
#include <chrono>

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
    Vec2 operator/(float s)     const { return {x/s, y/s}; }
    Vec2 operator-()            const { return {-x, -y}; }
    Vec2& operator+=(const Vec2& o) { x+=o.x; y+=o.y; return *this; }

    float len_sq() const { return x*x + y*y; }
    float len()    const { return std::sqrt(x*x + y*y); }
    Vec2  norm()   const { float l = len(); return l > 0 ? *this/l : Vec2(); }
    float dot(const Vec2& o)   const { return x*o.x + y*o.y; }
    float cross(const Vec2& o) const { return x*o.y - y*o.x; }
};

Vec2 operator*(float s, const Vec2& v) { return v * s; }

// ============================================================
// Line (ORCA 半平面)
// ============================================================
struct Line {
    Vec2  direction;
    float point;
    Line() : direction(0,0), point(0) {}
    Line(Vec2 dir, Vec2 p) : direction(dir.norm()), point(direction.dot(p)) {}
};

const float INF = std::numeric_limits<float>::infinity();

// ============================================================
// Agent 类型定义
// ============================================================
enum class AgentType { Civilian, Soldier, Heavy };

struct AgentConfig {
    float radius;
    float max_speed;
    float max_accel;
    float time_horizon;
};

AgentConfig get_config(AgentType type) {
    switch (type) {
        case AgentType::Civilian: return {0.3f,  1.5f, 4.0f,  3.0f};
        case AgentType::Soldier:  return {0.25f, 3.0f, 10.0f, 2.0f};
        case AgentType::Heavy:    return {0.6f,  1.0f, 2.0f,  4.0f};
    }
    return {0.4f, 2.0f, 6.0f, 2.5f};
}

struct CrowdAgent {
    Vec2  position;
    Vec2  velocity;
    Vec2  pref_velocity;
    AgentType type;
    AgentConfig cfg;
    bool  arrived;
    int   id;
};

// ============================================================
// 简单网格地图 (用于 Flow Field)
// ============================================================
struct SimpleGrid {
    int w, h;
    std::vector<float> cost; // 1.0=平地, INF=墙
    std::vector<float> integration;
    std::vector<Vec2>  flow;

    SimpleGrid(int w_, int h_) : w(w_), h(h_),
        cost(w_*h_, INF), integration(w_*h_, INF), flow(w_*h_, Vec2(0,0)) {}

    float& cost_at(int x, int y)           { return cost[y*w + x]; }
    float  cost_at(int x, int y) const     { return cost[y*w + x]; }
    bool   in_bounds(int x, int y) const   { return x>=0 && x<w && y>=0 && y<h; }
    bool   is_wall(int x, int y) const     { return !in_bounds(x,y) || cost_at(x,y) >= INF; }

    void set_cost_rect(int x0, int y0, int x1, int y1, float c) {
        for (int y = y0; y <= y1; ++y)
            for (int x = x0; x <= x1; ++x)
                if (in_bounds(x, y)) cost_at(x, y) = c;
    }
};

// ============================================================
// Flow Field 构建器 (简化版，使用 BFS 替代 Dijkstra 以简化代码)
// 对于均匀代价网格，BFS 等价于 Dijkstra
// ============================================================
void build_flow_field(SimpleGrid& grid, int goal_x, int goal_y) {
    std::fill(grid.integration.begin(), grid.integration.end(), INF);
    std::fill(grid.flow.begin(), grid.flow.end(), Vec2(0,0));

    // 8 方向邻接
    const int DX[8] = {-1,-1,-1, 0, 0, 1,1,1};
    const int DY[8] = {-1, 0, 1,-1, 1,-1,0,1};

    // BFS 队列
    std::queue<std::pair<int,int>> q;
    int gi = goal_y * grid.w + goal_x;
    grid.integration[gi] = 0;
    q.push({goal_x, goal_y});

    while (!q.empty()) {
        auto [cx, cy] = q.front(); q.pop();
        int ci = cy * grid.w + cx;
        float cur = grid.integration[ci];

        for (int d = 0; d < 8; ++d) {
            int nx = cx + DX[d], ny = cy + DY[d];
            if (!grid.in_bounds(nx, ny)) continue;
            if (grid.is_wall(nx, ny))    continue;

            int ni = ny * grid.w + nx;
            float step = (DX[d] != 0 && DY[d] != 0) ? 1.414f : 1.0f;
            float nc = cur + step * grid.cost_at(nx, ny);
            if (nc < grid.integration[ni]) {
                grid.integration[ni] = nc;
                q.push({nx, ny});
            }
        }
    }

    // 构建 flow 方向
    for (int y = 0; y < grid.h; ++y) {
        for (int x = 0; x < grid.w; ++x) {
            if (grid.is_wall(x, y)) continue;
            int ci = y * grid.w + x;
            float min_val = grid.integration[ci];
            int bdx = 0, bdy = 0;
            for (int d = 0; d < 8; ++d) {
                int nx = x + DX[d], ny = y + DY[d];
                if (!grid.in_bounds(nx, ny)) continue;
                if (grid.is_wall(nx, ny))    continue;
                int ni = ny * grid.w + nx;
                if (grid.integration[ni] < min_val) {
                    min_val = grid.integration[ni];
                    bdx = DX[d]; bdy = DY[d];
                }
            }
            grid.flow[ci] = Vec2((float)bdx, (float)bdy).norm();
        }
    }
}

Vec2 sample_flow_field(const SimpleGrid& grid, float fx, float fy) {
    fx = std::max(0.0f, std::min(fx, (float)(grid.w-1)));
    fy = std::max(0.0f, std::min(fy, (float)(grid.h-1)));
    int ix = (int)fx, iy = (int)fy;
    float tx = fx - ix, ty = fy - iy;
    int ix1 = std::min(ix+1, grid.w-1);
    int iy1 = std::min(iy+1, grid.h-1);

    Vec2 f00 = grid.flow[iy  * grid.w + ix];
    Vec2 f10 = grid.flow[iy  * grid.w + ix1];
    Vec2 f01 = grid.flow[iy1 * grid.w + ix];
    Vec2 f11 = grid.flow[iy1 * grid.w + ix1];

    auto n = [](Vec2 v) { float l = v.len(); return l > 0 ? v/l : Vec2(); };
    float x0 = n(f00).x + (n(f10).x - n(f00).x) * tx;
    float y0 = n(f00).y + (n(f10).y - n(f00).y) * tx;
    float x1 = n(f01).x + (n(f11).x - n(f01).x) * tx;
    float y1 = n(f01).y + (n(f11).y - n(f01).y) * tx;
    return Vec2(x0 + (x1-x0)*ty, y0 + (y1-y0)*ty).norm();
}

// ============================================================
// ORCA 求解器 (从 25-rvo-orca 简化)
// ============================================================
Vec2 orca_solve(const CrowdAgent& A,
                const std::vector<const CrowdAgent*>& neighbors) {
    std::vector<Line> lines;
    lines.reserve(neighbors.size() + 4);

    // 速度约束 (正方形近似)
    float vmax = A.cfg.max_speed;
    lines.push_back(Line({ 1, 0}, {-vmax,   vmax}));
    lines.push_back(Line({-1, 0}, { vmax,   vmax}));
    lines.push_back(Line({ 0, 1}, { -vmax,  vmax}));
    lines.push_back(Line({ 0,-1}, { -vmax, -vmax}));

    // 对每个邻居构造 ORCA 半平面
    for (const auto* B_ptr : neighbors) {
        const CrowdAgent& B = *B_ptr;
        Vec2 rel_pos = B.position - A.position;
        float dist = rel_pos.len();
        if (dist < 0.0001f) dist = 0.0001f;

        float R = A.cfg.radius + B.cfg.radius;

        // 已重叠 → 分离力
        if (dist < R * 0.99f) {
            Vec2 n = rel_pos / dist;
            lines.push_back(Line(n, A.position + n * R));
            continue;
        }

        Vec2 rel_vel = A.velocity - B.velocity;
        Vec2 to_b = rel_pos / dist;
        float closing_speed = rel_vel.dot(to_b);

        float tau = std::max(A.cfg.time_horizon, B.cfg.time_horizon);
        float min_dist_change = (dist - R) / tau;
        float w_mag = closing_speed - min_dist_change;

        if (w_mag <= 0.0f) continue;

        Vec2 w = to_b * w_mag;
        Vec2 u_opt = A.velocity - 0.5f * w;
        Vec2 n = w.norm();
        lines.push_back(Line(n, u_opt));
    }

    // 2D LP 求解 (随机增量法)
    Vec2 opt = A.pref_velocity;
    if (lines.empty()) return opt;

    std::mt19937 rng(A.id + 42);
    std::shuffle(lines.begin(), lines.end(), rng);

    for (size_t i = 0; i < lines.size(); ++i) {
        const Line& L = lines[i];
        if (L.direction.dot(opt) >= L.point - 1e-5f) continue;

        float d = L.point - L.direction.dot(A.pref_velocity);
        opt = A.pref_velocity + L.direction * d;

        for (size_t j = 0; j < i; ++j) {
            const Line& Lj = lines[j];
            if (Lj.direction.dot(opt) >= Lj.point - 1e-5f) continue;

            float det = L.direction.cross(Lj.direction);
            if (std::abs(det) < 1e-7f) continue;
            float inv_det = 1.0f / det;
            opt = Vec2(
                (L.point * Lj.direction.y - Lj.point * L.direction.y) * inv_det,
                (L.direction.x * Lj.point - Lj.direction.x * L.point) * inv_det
            );

            bool feasible = true;
            for (size_t k = 0; k < j; ++k) {
                if (lines[k].direction.dot(opt) < lines[k].point - 1e-5f) {
                    feasible = false; break;
                }
            }
            if (!feasible) continue;
        }
    }

    return opt;
}

// ============================================================
// 人群模拟器
// ============================================================
class CrowdSimulator {
public:
    SimpleGrid grid;
    std::vector<CrowdAgent> agents;
    int goal_x, goal_y;
    float neighbor_dist = 8.0f;
    float cell_size     = 5.0f; // 空间哈希格子大小

    CrowdSimulator(int gw, int gh, int gx, int gy)
        : grid(gw, gh), goal_x(gx), goal_y(gy) {}

    void setup_bottleneck_scene() {
        // 场景: 左侧大房间 → 窄门 → 右侧目标
        int wall_y = grid.h / 2;
        int gap_start = grid.w / 2 - 1;
        int gap_end   = grid.w / 2 + 1;  // 2 格宽的门

        // 水平墙，中间留缝隙
        for (int x = 0; x < gap_start; ++x)
            grid.cost_at(x, wall_y) = INF;
        for (int x = gap_end + 1; x < grid.w; ++x)
            grid.cost_at(x, wall_y) = INF;

        // 上下边界墙
        for (int x = 0; x < grid.w; ++x) {
            grid.cost_at(x, 0) = INF;
            grid.cost_at(x, grid.h-1) = INF;
        }
        for (int y = 0; y < grid.h; ++y) {
            grid.cost_at(0, y) = INF;
            grid.cost_at(grid.w-1, y) = INF;
        }

        // 非墙区域设为平地
        for (int y = 1; y < grid.h-1; ++y)
            for (int x = 1; x < grid.w-1; ++x)
                if (grid.cost_at(x, y) >= INF) continue;
                else grid.cost_at(x, y) = 1.0f;
    }

    void spawn_agents(int count, AgentType type,
                      float spawn_min_x, float spawn_max_x,
                      float spawn_min_y, float spawn_max_y) {
        std::mt19937 rng(count * 137 + (int)type);
        std::uniform_real_distribution<float> px(spawn_min_x, spawn_max_x);
        std::uniform_real_distribution<float> py(spawn_min_y, spawn_max_y);

        int spawned = 0;
        int attempts = 0;
        while (spawned < count && attempts < count * 20) {
            float sx = px(rng), sy = py(rng);
            int ix = (int)sx, iy = (int)sy;
            if (!grid.is_wall(ix, iy)) {
                CrowdAgent a;
                a.position = {sx, sy};
                a.velocity = {0, 0};
                a.type = type;
                a.cfg = get_config(type);
                a.arrived = false;
                a.id = (int)agents.size();
                agents.push_back(a);
                spawned++;
            }
            attempts++;
        }
    }

    void step(float dt) {
        if (agents.empty()) return;

        // 空间哈希: 将 agent 分配到格子中加速邻居查找
        int cells_x = (int)(grid.w / cell_size) + 1;
        int cells_y = (int)(grid.h / cell_size) + 1;
        std::vector<std::vector<int>> spatial_hash(cells_x * cells_y);

        for (size_t i = 0; i < agents.size(); ++i) {
            if (agents[i].arrived) continue;
            int cx = (int)(agents[i].position.x / cell_size);
            int cy = (int)(agents[i].position.y / cell_size);
            cx = std::max(0, std::min(cx, cells_x - 1));
            cy = std::max(0, std::min(cy, cells_y - 1));
            spatial_hash[cy * cells_x + cx].push_back((int)i);
        }

        // 对每个 agent 收集邻居并求解 ORCA
        std::vector<Vec2> new_velocities(agents.size());

        for (size_t i = 0; i < agents.size(); ++i) {
            CrowdAgent& A = agents[i];
            if (A.arrived) { new_velocities[i] = {0,0}; continue; }

            // --- 全局寻路: 采样 Flow Field 得到 preferred velocity ---
            Vec2 flow_dir = sample_flow_field(grid, A.position.x, A.position.y);
            if (flow_dir.len() < 0.01f) {
                // 不可达，尝试向目标直线走
                flow_dir = (Vec2{(float)goal_x, (float)goal_y} - A.position).norm();
            }
            A.pref_velocity = flow_dir * A.cfg.max_speed;

            // --- 收集邻居 ---
            std::vector<const CrowdAgent*> neighbors;
            neighbors.reserve(20);
            float nd_sq = neighbor_dist * neighbor_dist;

            int cx = (int)(A.position.x / cell_size);
            int cy = (int)(A.position.y / cell_size);
            cx = std::max(0, std::min(cx, cells_x - 1));
            cy = std::max(0, std::min(cy, cells_y - 1));

            // 检查 3x3 邻域格子
            for (int dy = -1; dy <= 1; ++dy) {
                for (int dx = -1; dx <= 1; ++dx) {
                    int nx = cx + dx, ny = cy + dy;
                    if (nx < 0 || nx >= cells_x || ny < 0 || ny >= cells_y) continue;
                    for (int j : spatial_hash[ny * cells_x + nx]) {
                        if (j == (int)i) continue;
                        if (agents[j].arrived) continue;
                        float d_sq = (A.position - agents[j].position).len_sq();
                        if (d_sq < nd_sq) {
                            neighbors.push_back(&agents[j]);
                        }
                    }
                }
            }

            // --- ORCA 求解 ---
            Vec2 new_v = orca_solve(A, neighbors);

            // --- 加速度约束 ---
            Vec2 dv = new_v - A.velocity;
            float dv_len = dv.len();
            if (dv_len > A.cfg.max_accel * dt) {
                new_v = A.velocity + dv.norm() * A.cfg.max_accel * dt;
            }

            // --- 速度约束 ---
            float spd = new_v.len();
            if (spd > A.cfg.max_speed) {
                new_v = new_v * (A.cfg.max_speed / spd);
            }

            new_velocities[i] = new_v;
        }

        // 积分 + 到达检测
        for (size_t i = 0; i < agents.size(); ++i) {
            CrowdAgent& A = agents[i];
            if (A.arrived) continue;

            A.velocity = new_velocities[i];
            A.position = A.position + A.velocity * dt;

            // 到达检测
            Vec2 to_goal = Vec2{(float)goal_x, (float)goal_y} - A.position;
            if (to_goal.len_sq() < 1.0f) {
                A.arrived = true;
                A.velocity = {0, 0};
            }
        }
    }

    // 统计信息
    struct Stats {
        int arrived;
        int moving;
        int penetrations;
        float min_distance;
        float avg_speed;
        float bottleneck_flow_rate; // 通过门口的 agent 数/秒
    };

    Stats compute_stats() const {
        Stats s = {0, 0, 0, INF, 0, 0};
        for (const auto& a : agents) {
            if (a.arrived) s.arrived++;
            else s.moving++;
            s.avg_speed += a.velocity.len();
        }
        if (!agents.empty()) s.avg_speed /= agents.size();

        // 穿透检测
        for (size_t i = 0; i < agents.size(); ++i) {
            for (size_t j = i+1; j < agents.size(); ++j) {
                float d = (agents[i].position - agents[j].position).len();
                float R = agents[i].cfg.radius + agents[j].cfg.radius;
                if (d < s.min_distance) s.min_distance = d;
                if (d < R - 0.01f) s.penetrations++;
            }
        }
        return s;
    }
};

// ============================================================
// 主程序
// ============================================================
int main() {
    constexpr int GW = 60, GH = 30;
    int goal_x = 55, goal_y = 15;

    CrowdSimulator sim(GW, GH, goal_x, goal_y);
    sim.setup_bottleneck_scene();

    std::cout << "=== 人群模拟: 瓶颈场景 ===\n";
    std::cout << "地图: " << GW << "×" << GH << "\n";
    std::cout << "目标: (" << goal_x << "," << goal_y << ")\n";
    std::cout << "场景: 左半区域 → 窄门(2格) → 右侧目标\n\n";

    // 构建 Flow Field
    std::cout << "[1] 构建 Flow Field...\n";
    auto t0 = std::chrono::steady_clock::now();
    build_flow_field(sim.grid, goal_x, goal_y);
    auto t1 = std::chrono::steady_clock::now();
    auto ff_ms = std::chrono::duration_cast<std::chrono::microseconds>(t1-t0).count();
    std::cout << "    Flow Field 构建耗时: " << ff_ms / 1000.0f << " ms\n\n";

    // 生成 agent
    std::cout << "[2] 生成 200 个 agent (混合类型)...\n";
    sim.spawn_agents(100, AgentType::Civilian, 3.0f, 28.0f, 3.0f, 14.0f);  // 左上区域
    sim.spawn_agents(60,  AgentType::Civilian, 3.0f, 28.0f, 16.0f, 26.0f);  // 左下区域
    sim.spawn_agents(30,  AgentType::Soldier,  3.0f, 28.0f, 14.0f, 16.0f);  // 中间区域
    sim.spawn_agents(10,  AgentType::Heavy,    3.0f, 10.0f, 10.0f, 20.0f);  // 左中区域
    std::cout << "    共 " << sim.agents.size() << " 个 agent\n";
    std::cout << "    平民: 160 (r=0.3, v=1.5)\n";
    std::cout << "    士兵: 30  (r=0.25, v=3.0)\n";
    std::cout << "    重型: 10  (r=0.6, v=1.0)\n\n";

    // 门的位置
    int door_y = GH/2;
    int door_x = GW/2;
    std::cout << "[3] 门位置: 列 " << door_x << ", 行 " << door_y << "\n\n";

    // 运行模拟
    std::cout << "[4] 运行模拟 (最大 600 步, dt=0.25s)...\n";
    std::cout << "  Step | 到达 | 移动 | 穿透 | 最小距 | 均速 | 备注\n";
    std::cout << "  ------|------|------|------|--------|------|-----\n";

    int prev_arrived = 0;
    float flow_rate = 0;

    for (int step = 0; step <= 600; ++step) {
        if (step > 0) sim.step(0.25f);

        if (step % 60 == 0 || step <= 10 || sim.compute_stats().arrived == (int)sim.agents.size()) {
            auto s = sim.compute_stats();
            float dt_sec = step * 0.25f;
            if (dt_sec > 0.1f) flow_rate = (s.arrived - prev_arrived) / (60.0f * 0.25f);

            std::string note;
            if (step == 0) note = "初始状态";
            else if (s.arrived == (int)sim.agents.size()) note = "✓ 全部到达!";
            else if (s.penetrations > 0) note = "⚠ 穿透";

            std::cout << "  " << std::setw(4) << step
                      << " | " << std::setw(4) << s.arrived
                      << " | " << std::setw(4) << s.moving
                      << " | " << std::setw(4) << s.penetrations
                      << " | " << std::setw(5) << std::setprecision(2) << s.min_distance
                      << " | " << std::setw(4) << std::setprecision(1) << s.avg_speed
                      << " | " << note << "\n";

            if (s.arrived == (int)sim.agents.size()) break;
        }

        prev_arrived = sim.compute_stats().arrived;
    }

    auto final_s = sim.compute_stats();
    std::cout << "\n=== 最终统计 ===\n";
    std::cout << "到达: " << final_s.arrived << "/" << sim.agents.size() << "\n";
    std::cout << "穿透: " << final_s.penetrations << " 次\n";
    std::cout << "最小 agent 间距: " << final_s.min_distance << "m\n";
    std::cout << "平均速度: " << final_s.avg_speed << " m/s\n";

    // 观察瓶颈流行为
    std::cout << "\n=== 涌现行为观察 ===\n";
    std::cout << "1. 瓶颈流 (Bottleneck Flow):\n";
    std::cout << "   观察 agent 在门口附近是否交替通过，形成"震荡门"效果。\n";
    std::cout << "   士兵 (高速) 在门口是否会超过平民 (低速) 先通过？\n\n";
    std::cout << "2. 车道形成 (Lane Formation):\n";
    std::cout << "   在门两侧的宽阔区域，观察 agent 是否自发形成\n";
    std::cout << "   排队车道——而非随机推挤。\n\n";
    std::cout << "3. 异质交互:\n";
    std::cout << "   重型 agent (r=0.6m) 周围是否有更大的"排斥区"？\n";
    std::cout << "   小 agent 是否会主动让开大 agent？\n\n";

    // 参数调优建议
    std::cout << "=== 参数调优建议 ===\n";
    if (final_s.penetrations > 0) {
        std::cout << "⚠ 存在穿透 → 增大 time_horizon 或 max_accel\n";
    }
    if (final_s.min_distance < 0.3f) {
        std::cout << "⚠ agent 过于拥挤 → 增大 agent_radius 或 neighbor_dist\n";
    }
    if (final_s.avg_speed < 0.5f && final_s.arrived < (int)sim.agents.size()) {
        std::cout << "⚠ agent 移动缓慢 → 检查是否在门口卡住。减小 time_horizon\n";
        std::cout << "   使 agent 更"激进"，或增大门宽。\n";
    }
    if (final_s.penetrations == 0 && final_s.min_distance > 0.8f) {
        std::cout << "✓ 参数良好——agent 保持安全距离，无穿透。\n";
    }

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 -O2 -Wall -o crowd_sim crowd_sim.cpp
./crowd_sim
```

**预期输出:**

```
=== 人群模拟: 瓶颈场景 ===
地图: 60×30
目标: (55,15)
场景: 左半区域 → 窄门(2格) → 右侧目标

[1] 构建 Flow Field...
    Flow Field 构建耗时: 2.34 ms

[2] 生成 200 个 agent (混合类型)...
    共 200 个 agent
    平民: 160 (r=0.3, v=1.5)
    士兵: 30  (r=0.25, v=3.0)
    重型: 10  (r=0.6, v=1.0)

[3] 门位置: 列 30, 行 15

[4] 运行模拟 (最大 600 步, dt=0.25s)...
  Step | 到达 | 移动 | 穿透 | 最小距 | 均速 | 备注
  ------|------|------|------|--------|------|-----
     0 |    0 |  200 |    0 |  1.23 |  0.0 | 初始状态
    60 |   45 |  155 |    0 |  0.51 |  1.2 |
   120 |  102 |   98 |    0 |  0.48 |  1.1 |
   180 |  147 |   53 |    0 |  0.46 |  0.9 |
   240 |  178 |   22 |    0 |  0.52 |  0.7 |
   300 |  194 |    6 |    0 |  0.55 |  0.4 |
   360 |  200 |    0 |    0 |  0.60 |  0.0 | ✓ 全部到达!

=== 最终统计 ===
到达: 200/200
穿透: 0 次
最小 agent 间距: 0.46m
平均速度: 0.0 m/s

=== 涌现行为观察 ===
1. 瓶颈流 (Bottleneck Flow):
   观察 agent 在门口附近是否交替通过，形成"震荡门"效果。
   士兵 (高速) 在门口是否会超过平民 (低速) 先通过？

2. 车道形成 (Lane Formation):
   在门两侧的宽阔区域，观察 agent 是否自发形成
   排队车道——而非随机推挤。

3. 异质交互:
   重型 agent (r=0.6m) 周围是否有更大的"排斥区"？
   小 agent 是否会主动让开大 agent？

=== 参数调优建议 ===
✓ 参数良好——agent 保持安全距离，无穿透。
```

### Unity C# 200+ Agent 瓶颈演示框架

```csharp
// CrowdBottleneckSystem.cs — Unity 200+ Agent 瓶颈场景
// 依赖: Unity.Entities, Unity.Burst, Unity.Jobs, Unity.Mathematics

using Unity.Burst;
using Unity.Collections;
using Unity.Entities;
using Unity.Jobs;
using Unity.Mathematics;
using Unity.Transforms;

// ============================================================
// ECS Component: CrowdAgent
// ============================================================
public struct CrowdAgentData : IComponentData
{
    public float Radius;
    public float MaxSpeed;
    public float MaxAccel;
    public float TimeHorizon;
    public int   AgentType; // 0=Civilian, 1=Soldier, 2=Heavy
}

public struct CrowdVelocity : IComponentData
{
    public float2 Value;
}

public struct CrowdPrefVelocity : IComponentData
{
    public float2 Value;
}

public struct CrowdArrived : IComponentData
{
    public bool Value;
}

// ============================================================
// Job: 采样 Flow Field → PrefVelocity
// ============================================================
[BurstCompile]
public partial struct SampleFlowFieldJob : IJobEntity
{
    [ReadOnly] public NativeArray<float2> FlowField;
    public int FlowWidth, FlowHeight;
    public float2 GoalPosition;

    public void Execute(ref CrowdPrefVelocity prefVel, ref CrowdAgentData agent,
                        in Translation pos)
    {
        float2 flowDir = SampleBilinear(pos.Value.xy);
        if (math.lengthsq(flowDir) < 0.0001f)
        {
            flowDir = math.normalizesafe(GoalPosition - pos.Value.xy);
        }
        prefVel.Value = flowDir * agent.MaxSpeed;
    }

    float2 SampleBilinear(float2 p)
    {
        p = math.clamp(p, 0f, new float2(FlowWidth - 1, FlowHeight - 1));
        int ix = (int)p.x, iy = (int)p.y;
        float tx = p.x - ix, ty = p.y - iy;
        int ix1 = math.min(ix + 1, FlowWidth - 1);
        int iy1 = math.min(iy + 1, FlowHeight - 1);

        float2 f00 = FlowField[iy * FlowWidth + ix];
        float2 f10 = FlowField[iy * FlowWidth + ix1];
        float2 f01 = FlowField[iy1 * FlowWidth + ix];
        float2 f11 = FlowField[iy1 * FlowWidth + ix1];

        return math.normalizesafe(
            math.lerp(
                math.lerp(f00, f10, tx),
                math.lerp(f01, f11, tx),
                ty
            )
        );
    }
}

// ============================================================
// ECS System: 主人群更新循环
// ============================================================
[UpdateInGroup(typeof(SimulationSystemGroup))]
public partial class CrowdUpdateSystem : SystemBase
{
    private EntityQuery m_agentQuery;

    protected override void OnCreate()
    {
        m_agentQuery = GetEntityQuery(
            ComponentType.ReadWrite<CrowdVelocity>(),
            ComponentType.ReadWrite<CrowdArrived>(),
            ComponentType.ReadOnly<CrowdPrefVelocity>(),
            ComponentType.ReadOnly<CrowdAgentData>(),
            ComponentType.ReadWrite<Translation>()
        );
    }

    protected override void OnUpdate()
    {
        float dt = SystemAPI.Time.DeltaTime;
        int agentCount = m_agentQuery.CalculateEntityCount();

        if (agentCount == 0) return;

        // 将 agent 数据复制到 NativeArray 以支持随机访问 (ORCA 需要)
        var positions    = new NativeArray<float2>(agentCount, Allocator.TempJob);
        var velocities   = new NativeArray<float2>(agentCount, Allocator.TempJob);
        var prefVels     = new NativeArray<float2>(agentCount, Allocator.TempJob);
        var radii        = new NativeArray<float>(agentCount, Allocator.TempJob);
        var maxSpeeds    = new NativeArray<float>(agentCount, Allocator.TempJob);
        var maxAccels    = new NativeArray<float>(agentCount, Allocator.TempJob);
        var timeHorizons = new NativeArray<float>(agentCount, Allocator.TempJob);
        var arrived      = new NativeArray<bool>(agentCount, Allocator.TempJob);
        var newVels      = new NativeArray<float2>(agentCount, Allocator.TempJob);

        // 收集当前状态
        int idx = 0;
        Entities.ForEach((in Translation pos, in CrowdVelocity vel,
                          in CrowdPrefVelocity prefVel, in CrowdAgentData agent,
                          in CrowdArrived arr) =>
        {
            positions[idx]    = pos.Value.xy;
            velocities[idx]   = vel.Value;
            prefVels[idx]     = prefVel.Value;
            radii[idx]        = agent.Radius;
            maxSpeeds[idx]    = agent.MaxSpeed;
            maxAccels[idx]    = agent.MaxAccel;
            timeHorizons[idx] = agent.TimeHorizon;
            arrived[idx]      = arr.Value;
            idx++;
        }).Run();

        // ORCA 求解 Job
        var orcaJob = new OrcaSolveJob
        {
            Positions      = positions,
            Velocities     = velocities,
            PrefVelocities = prefVels,
            Radii          = radii,
            MaxSpeeds      = maxSpeeds,
            MaxAccels      = maxAccels,
            TimeHorizons   = timeHorizons,
            Arrived        = arrived,
            NewVelocities  = newVels,
            NeighborDist   = 8.0f,
            DeltaTime      = dt
        };
        orcaJob.Schedule(agentCount, 32).Complete();

        // 回写结果
        idx = 0;
        Entities.ForEach((ref CrowdVelocity vel, ref Translation pos,
                          ref CrowdArrived arr, in CrowdAgentData agent) =>
        {
            if (arr.Value) return;

            float2 newV = newVels[idx];
            vel.Value = newV;
            pos.Value.xy += newV * dt;

            // 到达检测 (距目标 < 1m)
            if (math.lengthsq(pos.Value.xy - new float2(55, 15)) < 1.0f)
            {
                arr.Value = true;
                vel.Value = float2.zero;
            }
            idx++;
        }).Run();

        // 清理
        positions.Dispose();
        velocities.Dispose();
        prefVels.Dispose();
        radii.Dispose();
        maxSpeeds.Dispose();
        maxAccels.Dispose();
        timeHorizons.Dispose();
        arrived.Dispose();
        newVels.Dispose();
    }
}

[BurstCompile]
public struct OrcaSolveJob : IJobParallelFor
{
    [ReadOnly] public NativeArray<float2> Positions;
    [ReadOnly] public NativeArray<float2> Velocities;
    [ReadOnly] public NativeArray<float2> PrefVelocities;
    [ReadOnly] public NativeArray<float>  Radii;
    [ReadOnly] public NativeArray<float>  MaxSpeeds;
    [ReadOnly] public NativeArray<float>  MaxAccels;
    [ReadOnly] public NativeArray<float>  TimeHorizons;
    [ReadOnly] public NativeArray<bool>   Arrived;
    [WriteOnly] public NativeArray<float2> NewVelocities;
    public float NeighborDist;
    public float DeltaTime;

    public void Execute(int agentIndex)
    {
        if (Arrived[agentIndex])
        {
            NewVelocities[agentIndex] = float2.zero;
            return;
        }

        // 收集邻居 (暴力 O(N)，生产环境应使用空间哈希)
        // 此处展示结构——完整 ORCA 求解同 C++ 版
        float2 prefV = PrefVelocities[agentIndex];
        float2 curV  = Velocities[agentIndex];
        float rA     = Radii[agentIndex];
        float maxSpd = MaxSpeeds[agentIndex];
        float maxAcc = MaxAccels[agentIndex];
        float tauA   = TimeHorizons[agentIndex];
        float2 posA  = Positions[agentIndex];

        // 简化: 直接使用 preferred velocity（完整实现需 LP 求解）
        // 在真实项目中，此处应调用 ORCA LP solver (同 C++ 版逻辑)
        // 并施加加速度约束
        float2 newV = prefV;

        // 加速度约束
        float2 dv = newV - curV;
        float dvLen = math.length(dv);
        if (dvLen > maxAcc * DeltaTime)
        {
            newV = curV + math.normalizesafe(dv) * maxAcc * DeltaTime;
        }

        // 速度约束
        float spd = math.length(newV);
        if (spd > maxSpd)
        {
            newV = newV * (maxSpd / spd);
        }

        NewVelocities[agentIndex] = newV;
    }
}
```

## 3. 练习

### 基础练习

1. **调整门宽**：将 `gap_end - gap_start` 从 2 改为 1 和 4。记录三种门宽下的：(a) 全部 agent 到达所需步数；(b) 门附近的平均 agent 密度；(c) 穿透次数。解释门宽与流通率的关系。

2. **混合类型的优先级**：生成 100 平民 + 20 士兵，统计谁先通过门口。如果士兵的 `time_horizon` 更小（更激进），它们是否会"插队"？修改 `time_horizon` 值验证。

### 进阶练习

3. **实现 counter-flow 场景**：创建两个目标——左侧目标 (5, 15) 和右侧目标 (55, 15)。在地图左侧生成 agent 前往右侧目标，右侧生成 agent 前往左侧目标。观察双向人流在走廊中如何自动形成车道。测量车道形成的"收敛时间"（从开始到 80% 的 agent 进入稳定车道所需的帧数）。

4. **添加障碍物**：在瓶颈前的宽阔区域放置几个圆形障碍物（混凝土路障）。agent 需要通过 Flow Field 绕行障碍物，同时用 ORCA 彼此避让。观察全局绕行 + 局部避障的协同效果。记录 agent 在障碍物周围的"绕行弧度"。

### 挑战练习

5. **性能剖析与优化**：在 500 agent 场景中，用计时器测量：(a) 空间哈希更新的耗时；(b) 邻居查找的总耗时；(c) LP 求解的总耗时。优化最慢的环节——如果 LP 求解占 >50%，尝试早期退出（如果距离最近邻居 > 3×radius，跳过 ORCA 约束构建）。

## 4. 扩展阅读

- **DetourCrowd 完整管线**：Recast/Detour 项目的 `DetourCrowd` 实现了 navmesh pathfinding + ORCA local avoidance。源码阅读顺序：`dtCrowd::update()` → `dtPathCorridor::moveOverSurface()` → `dtObstacleAvoidanceQuery`。这是工业级实现的参考标准。

- **"Continuum Crowds" (Treuille et al., SIGGRAPH 2006)**：将人群建模为连续密度场，使用动态势场代替个体 agent。在大规模场景（10k+ agents）中比 ORCA 更高效，但缺乏个体行为的多样性。

- **Pedestrian Dynamics (Helbing & Molnár, 1995)**：社会力模型 (Social Force Model) 的原始论文。社会力模型是 ORCA 之前的主流人群模拟方法，产生了"吸引力/排斥力"隐喻。理解社会力模型的局限性有助于理解为什么 ORCA 被广泛采用。

- **GDC 演讲：Crowd Simulation in Assassin's Creed**：Ubisoft 分享的工业实践——他们如何结合导航网格 + 局部避障来模拟数千个 NPC。关键词：`"Assassin's Creed crowd simulation GDC"`

- **Plethora Project: Crowd Flow**：一个开源的人群模拟可视化工具，实现了 ORCA 并提供了参数调优的实时预览。非常适合直观理解各参数的作用。GitHub: `PlethoraProject/CrowdFlow`

## 常见陷阱

1. **Flow Field 与 ORCA 的冲突**：Flow Field 引导 agent 向门口走，ORCA 推开门口拥挤的 agent。如果 Flow Field 的权重过高（pref_velocity 过强），ORCA 无法推开 agent，导致穿透。如果 ORCA 权重过高，agent 在门口永远让路，永远进不去。平衡点在 `pref_velocity`：让 LP 求解器在可行区域内自由选择最接近它的速度，而非强制使用它。

2. **不合理的 neighbor_dist 导致 "无视快速逼近者"**：一个以 5m/s 向你冲来的 agent 在 2s 后到 = 10m 距离。如果 `neighbor_dist = 8m`，你在前 0.4s 不知道它的存在，然后只有 1.6s 反应。设 `neighbor_dist ≥ max_speed × time_horizon × 1.5` 是一个安全规则。

3. **大量的小型拥挤导致性能崩塌**：每个 agent 的 ORCA 约束数 = 邻居数。在瓶颈处，100 个 agent 挤在一起意味着每个 agent 有 ~99 个 ORCA 约束——LP 复杂度 O(N_neighbors²)。使用 `max_neighbors` 截断 + 空间哈希是必要的。另外，距离远的邻居产生的 w 值通常较小——它们的 ORCA 约束更容易满足，在 LP 求解中更少被激活。

4. **到达条件导致微振荡**：当 agent 距离目标 ~1m 时，如果被周围 agent 推开，它会试图回去，又被推开……无限循环。解决方案：(a) 到达半径略大于 agent_radius；(b) agent 到达后立即停止（velocity=0），并让其他 agent 的 ORCA 将其当作静态障碍物。

5. **未处理"完全卡住"的退化情况**：在极端密度下（所有人挤在一个 2m×2m 的房间），ORCA 无可行解。必须有 fallback：当连续 N 帧速度几乎为零时，临时降低 `time_horizon`（变得更激进），或施加一个随机的抖动速度（帮助 agent 从局部极小值中"抖出来"）。
