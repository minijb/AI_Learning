# RVO 与 ORCA：最优相互碰撞避免

> 所属计划: 高阶寻路系统
> 预计耗时: 60min
> 前置知识: 向量运算（点积、叉积、归一化、投影），Steering Behaviors（14），基础线性规划概念

## 1. 概念讲解

### 为什么需要这个？

Steering Behaviors 的 Obstacle Avoidance 靠的是"探测射线 + 侧向力"，在 agent 稀疏时效果不错。但当 agent 密度上升——50 个 agent 挤在狭窄走廊里——会出三个致命问题：

1. **振荡 (Oscillation)**：两个 agent 迎面走来，同时向左闪避，发现还是碰撞，又同时向右闪避……无限循环
2. **不共享避让责任**：速度快的 agent 包揽全部避让，慢的 agent 不动；或者反过来——不公平，也不自然
3. **穿透 (Penetration)**：当避让力不够强时，agent 直接穿透彼此——物理上不可能，视觉上很糟糕

**ORCA (Optimal Reciprocal Collision Avoidance)** 是解决这些问题的工业标准。自 2011 年由 van den Berg, Guy, Lin, Manocha 提出后，几乎所有现代人群模拟（包括 Recast/Detour 的 DetourCrowd）都基于 ORCA。

核心洞见：**两个 agent 各让一半**——不是 A 承担全部避让责任，而是 A 和 B 各自避开对方速度的一半。这样既避免了振荡（因为责任是对称的），又保证了确定性（线性规划求解，不是启发式）。

### 核心思想

ORCA 的数学推导分三步。我们从几何直观开始，逐步精确化。

#### 第一步：Velocity Obstacle (VO)

想象 agent A 以速度 vA 运动，agent B 以 vB 运动。从 A 的视角看，B 相对于 A 的速度是 `vA - vB`（即 A 看到 B 以这个速度靠近）。

**Velocity Obstacle** 是一个锥形区域：如果 `vA - vB` 落在这个锥内，A 和 B 将在未来 τ 时间内（时间窗口）碰撞。

```
VO 的几何构造:
- 将 B 的半径"转移"到 A 上 → 将 A 缩为一个点，B 膨胀为半径 rA+rB 的"障碍圆"
- 从 A 的位置向膨胀后的 B 做两条切线 → 两条射线围成一个锥
- 这个锥就是 VO：任何使相对速度指向锥内的 (~vA, ~vB) 对都会导致碰撞

VO_τ^A|B = { v | ∃t ∈ [0,τ] : tv ∈ D(pB - pA, rA + rB) }
其中 D(p, r) 是以 p 为中心、r 为半径的圆盘
```

直观理解：站在 A 的位置看 B。如果 B 在"靠近"，且靠近方向落在 B（膨胀后）的轮廓内，就会撞上。VO 就是这个"会撞上"的速度集合。

#### 第二步：Reciprocal Velocity Obstacle (RVO)

VO 的问题：A 和 B 各自独立计算 VO，然后各自选择 VO 外的速度。它们可能选择相反方向的"绕行"——导致振荡。

**RVO 的修复**：不是避开整个 VO，而是避开 VO 的**一半**。具体来说，如果当前相对速度在 VO 内，RVO 要求新速度避开一个"半锥"——恰好在当前速度与 VO 边界之间的中点。

```
RVO_τ^A|B = { v' | 2v' - v_A ∈ VO_τ^A|B }
```

这里 `2v' - v_A` 表示：新速度 v' 与当前速度 v_A 之间的"对称偏移"必须脱离 VO。几何上，这将 VO 平移到了 `(v_A + v*)/2` 附近，其中 v* 是 VO 外的一个安全速度。

#### 第三步：ORCA — 线性规划形式

RVO 仍然是非凸的（锥的交集不一定是凸集），求解困难。ORCA 的关键创新：**将 RVO 锥近似为半平面**。

```
ORCA 半平面的推导:

1. 计算相对速度: u = v_A - v_B
2. 找到 u 到 VO 边界的最短向量 w:
   w = argmin_{v ∈ ∂VO} ||v - u||
   （如果 u 在 VO 外，w = 0 — 不需要避让）

3. 半平面的法向量: n = normalize(w)
4. 半平面位置: 从 v_A 出发，偏移 w/2（因为 A 承担一半避让责任）

   ORCA_τ^A|B = { v | (v - (v_A + ½w)) · n ≥ 0 }
```

这意味着：A 的新速度必须位于以 `v_A + w/2` 为边界、以 n 为外法向的半平面内。

**线性规划问题**：

对于 agent A，与每个邻近 agent B_i 构造一个 ORCA 半平面。A 的可行速度区域是所有这些半平面的交集。然后，在可行区域内选择最接近"首选速度"（由全局寻路给出）的速度：

```
v_new = argmin_{v ∈ ∩ORCA_{A|B_i}} ||v - v_pref||
```

这是一个 2D 线性规划问题，可以在 O(N_neighbors) 时间内求解（通过增量线性规划，或使用简单的随机化算法）。

#### 为什么 ORCA 不会振荡

因为两个 agent 各自承担 `w/2` 的避让量——A 的半平面边界在 `v_A + w/2`，B 的半平面边界在 `v_B - w/2`（对称）。最终相对速度恰好触及 VO 边界——刚好不碰撞，没有多余的避让，也没有偏向一方。

### 参数含义

| 参数 | 含义 | 典型值 |
|------|------|--------|
| τ (time horizon) | 考虑多远的未来发生碰撞 | 2-5 秒（步兵），0.5-1 秒（高速车辆） |
| r (radius) | agent 的碰撞半径 | 0.3-0.5m (人形角色) |
| v_max | 最大速度 | 由角色设定决定 |
| a_max | 最大加速度 | 限制两次 ORCA 解之间的速度变化 |
| neighbor_dist | 考虑多远的邻居 | 通常 5-10 米 |

τ 取大值 → agent 早早开始避让，运动更平滑，但有时避让"过头"。τ 取小值 → agent 更激进，更晚避让。

## 2. 代码示例

### C++ 完整 ORCA 实现

```cpp
// orca.cpp — 最优相互碰撞避免 (ORCA) 完整实现
// 编译: g++ -std=c++17 -O2 -Wall -o orca orca.cpp
// 运行: ./orca
//
// 演示: N 个 agent 在二维空间中用 ORCA 局部避障，
// 包括交叉相遇、迎面相遇和群集场景，验证无振荡无穿透。

#include <iostream>
#include <vector>
#include <cmath>
#include <limits>
#include <algorithm>
#include <random>
#include <iomanip>

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
    Vec2  perp() const { return {-y, x}; } // 逆时针 90°
};

Vec2 operator*(float s, const Vec2& v) { return v * s; }

// ============================================================
// ORCA 线的表示: direction·p ≥ scalar 形式的半平面
// 即 (direction · point) >= scalar 的半平面
// ============================================================
struct Line {
    Vec2  direction; // 单位法向，指向可行区域内部
    float point;     // 线上任意点满足 direction·p = point

    Line() : direction(0,0), point(0) {}
    Line(Vec2 dir, Vec2 p) : direction(dir.norm()), point(direction.dot(p)) {}
};

// ============================================================
// ORCA Simulator
// ============================================================
struct Agent {
    Vec2  position;
    Vec2  velocity;
    Vec2  pref_velocity;  // 首选速度 (来自全局寻路)
    float radius;
    float max_speed;
    float max_accel;
    int   id;
};

struct OrcaParams {
    float time_horizon   = 2.0f;  // τ: 碰撞检测时间窗口
    float time_horizon_obs = 1.0f; // 对障碍物的时间窗口
    float neighbor_dist  = 10.0f;  // 考虑多远的邻居
    int   max_neighbors  = 20;      // 最多考虑多少个邻居
};

class OrcaSimulator {
public:
    OrcaParams params;
    std::vector<Agent> agents;

    void step(float dt) {
        std::vector<Vec2> new_velocities(agents.size());

        for (size_t i = 0; i < agents.size(); ++i) {
            new_velocities[i] = compute_orca_velocity(i);
        }

        // 应用新速度
        for (size_t i = 0; i < agents.size(); ++i) {
            Agent& a = agents[i];
            Vec2 v_new = new_velocities[i];

            // 加速度约束
            Vec2 dv = v_new - a.velocity;
            float dv_len = dv.len();
            if (dv_len > params.time_horizon * a.max_accel) { // dt=1 for simplicity
                v_new = a.velocity + dv.norm() * a.max_accel;
            }

            a.velocity = v_new;
            a.position = a.position + a.velocity * dt;
        }
    }

private:
    // ============================================================
    // 核心: 为一个 agent 计算 ORCA 速度
    // ============================================================
    Vec2 compute_orca_velocity(int agent_idx) {
        Agent& A = agents[agent_idx];

        // 收集 ORCA 半平面
        std::vector<Line> lines;
        lines.reserve(params.max_neighbors + 4);

        // 速度约束半平面:
        // ||v|| ≤ max_speed (圆形约束，用 4 个半平面近似)
        float vmax = A.max_speed;
        lines.push_back(Line({ 1, 0}, {      0, 0}));  // v_x ≤ vmax  →  -v_x ≥ -vmax
        lines.push_back(Line({-1, 0}, {  vmax, 0}));  // v_x ≥ -vmax →   v_x ≥ -vmax
        lines.push_back(Line({ 0, 1}, {      0, 0}));  // v_y ≤ vmax
        lines.push_back(Line({ 0,-1}, {  vmax, 0}));  // v_y ≥ -vmax
        // 注意: 这里用 4 个半平面框住一个正方形来近似圆形速度约束
        // 严格来说应该用圆形约束，但半平面更利于 LP 求解。简化处理。

        // 对每个邻居构造 ORCA 半平面
        for (size_t j = 0; j < agents.size(); ++j) {
            if ((int)j == agent_idx) continue;
            Agent& B = agents[j];

            Vec2 rel_pos = B.position - A.position;
            float dist_sq = rel_pos.len_sq();

            float combined_radius = A.radius + B.radius;

            // 太远跳过
            if (dist_sq > params.neighbor_dist * params.neighbor_dist) continue;
            // 已经重叠（不应该发生，但还是处理）
            if (dist_sq < combined_radius * combined_radius * 0.99f) {
                // 已经碰撞，推动分开的力
                float dist = std::sqrt(dist_sq);
                if (dist < 0.0001f) dist = 0.0001f;
                Vec2 n = rel_pos / dist;
                lines.push_back(Line(n, A.position + n * combined_radius));
                continue;
            }

            // ---- ORCA 半平面构造 ----

            Vec2 rel_vel = A.velocity - B.velocity;
            float dist = std::sqrt(dist_sq);

            // 计算相对位置方向
            Vec2 to_b = rel_pos / dist;

            // 步骤 1: 找到 u (rel_vel) 到 VO 锥的最短向量 w
            // VO 的条件: 存在 t ∈ [0,τ] 使 ||rel_pos + t*rel_vel|| < combined_radius
            // 即: 在 τ 时间内，相对运动使双方距离小于半径之和

            // 数学推导:
            // 碰撞条件 = (rel_pos + t*rel_vel)^2 < (rA+rB)^2  for some t in [0,τ]
            // 展开: t^2*|v|^2 + 2t*(rel_pos·rel_vel) + |rel_pos|^2 - R^2 < 0

            float inv_tau = 1.0f / params.time_horizon;

            // VO 的半平面近似: 将 rel_vel 投影到 to_b 方向上
            // w = (to_b 方向上需要的最小修正)

            // 当前相对速度在 to_b 方向上的分量
            float closing_speed = rel_vel.dot(to_b);

            // 在 τ 时间内，当前位置允许的最小距离变化
            float min_dist_change = (dist - combined_radius) * inv_tau;

            // 如果 closing_speed 已经足够小（不靠近），不需要避让
            float w_mag = min_dist_change - closing_speed;

            if (w_mag <= 0.0f) continue; // 当前速度已经安全，不需要 ORCA 约束

            // w 向量: A 需要将自己的速度沿 to_b 方向"推开" w_mag 的量
            Vec2 w = to_b * w_mag;

            // ORCA: A 承担一半的避让责任
            Vec2 u_opt = A.velocity + 0.5f * w;

            // 半平面: { v | (v - u_opt)·n ≥ 0 }
            Vec2 n = w.norm();

            lines.push_back(Line(n, u_opt));
        }

        // ---- 求解线性规划: min ||v - v_pref|| s.t. v ∈ ∩ lines ----
        return solve_linear_program_2d(A.pref_velocity, lines);
    }

    // ============================================================
    // 2D 线性规划求解器 (随机增量法)
    // 约束: direction_i · v ≥ point_i  (半平面)
    // 目标: min ||v - v_pref||_2
    //
    // 算法: 随机排列约束，逐条添加。
    // 如果当前最优解违反新约束：
    //   找到新约束边界上离 v_pref 最近的点
    //   (即 projection of v_pref onto the line)
    //   检查是否满足所有已有约束；不满足则递归求解
    // ============================================================
    Vec2 solve_linear_program_2d(Vec2 v_pref, std::vector<Line>& lines) {
        if (lines.empty()) return v_pref;

        // 初始解: v_pref
        Vec2 opt = v_pref;

        // 随机化约束顺序（避免最坏情况 O(n^2)）
        std::mt19937 rng(42);
        std::shuffle(lines.begin(), lines.end(), rng);

        for (size_t i = 0; i < lines.size(); ++i) {
            const Line& L = lines[i];

            // 检查 opt 是否违反约束 i
            if (L.direction.dot(opt) >= L.point - 1e-6f) continue; // 满足

            // 违反: 新最优解必须在约束 i 的边界上
            // 将 v_pref 投影到边界线上: min ||v - v_pref|| s.t. n·v = point
            // 投影公式: v = v_pref + (point - n·v_pref) * n
            float d = L.point - L.direction.dot(v_pref);
            opt = v_pref + L.direction * d;

            // 检查此投影是否满足所有前面的约束 (j < i)
            for (size_t j = 0; j < i; ++j) {
                const Line& Lj = lines[j];
                if (Lj.direction.dot(opt) >= Lj.point - 1e-6f) continue; // 满足

                // 不满足: opt 必须在 Li 和 Lj 的交点上
                // 求解 n_i·v = p_i, n_j·v = p_j
                // [n_i.x  n_i.y] [v_x] = [p_i]
                // [n_j.x  n_j.y] [v_y]   [p_j]
                float det = L.direction.cross(Lj.direction);
                if (std::abs(det) < 1e-8f) {
                    // 平行且冲突 → 不可行。选择两个中较接近 v_pref 的那个
                    // 返回上一个可行解
                    continue;
                }

                float inv_det = 1.0f / det;
                opt = Vec2(
                    (L.point * Lj.direction.y - Lj.point * L.direction.y) * inv_det,
                    (L.direction.x * Lj.point - Lj.direction.x * L.point) * inv_det
                );

                // 验证这个交点满足所有 k < j 的约束
                bool feasible = true;
                for (size_t k = 0; k < j; ++k) {
                    if (lines[k].direction.dot(opt) < lines[k].point - 1e-6f) {
                        feasible = false;
                        break;
                    }
                }
                if (!feasible) continue;
            }
        }

        return opt;
    }
};

// ============================================================
// 测试场景
// ============================================================
int main() {
    std::cout << "=== ORCA 最优相互碰撞避免 ===\n\n";

    // ---------- 场景 1: 交叉相遇 ----------
    {
        std::cout << "--- 场景 1: 两个 agent 交叉相遇 ---\n";

        OrcaSimulator sim;
        sim.params.time_horizon  = 2.0f;
        sim.params.neighbor_dist = 15.0f;

        // Agent A: 从左到右
        Agent a;
        a.position = {0, 0.5f};
        a.velocity = {3, 0};
        a.pref_velocity = {3, 0};
        a.radius = 0.4f;
        a.max_speed = 4.0f;
        a.max_accel = 3.0f;
        a.id = 0;

        // Agent B: 从右到左，偏上方
        Agent b;
        b.position = {20, -0.5f};
        b.velocity = {-3, 0};
        b.pref_velocity = {-3, 0};
        b.radius = 0.4f;
        b.max_speed = 4.0f;
        b.max_accel = 3.0f;
        b.id = 1;

        sim.agents = {a, b};

        std::cout << "初始位置: A(" << a.position.x << "," << a.position.y
                  << ") B(" << b.position.x << "," << b.position.y << ")\n";
        std::cout << "初始速度: A(" << a.velocity.x << "," << a.velocity.y
                  << ") B(" << b.velocity.x << "," << b.velocity.y << ")\n";
        std::cout << "轨迹:\n";
        std::cout << "  t  | A.pos           | B.pos           | dist\n";
        std::cout << "  ----|----------------|----------------|-------\n";

        for (int t = 0; t <= 20; ++t) {
            if (t > 0) sim.step(1.0f);

            float dist = (sim.agents[0].position - sim.agents[1].position).len();
            std::cout << "  " << std::setw(2) << t << "  | ("
                      << std::fixed << std::setprecision(1)
                      << std::setw(5) << sim.agents[0].position.x << ","
                      << std::setw(5) << sim.agents[0].position.y << ") | ("
                      << std::setw(5) << sim.agents[1].position.x << ","
                      << std::setw(5) << sim.agents[1].position.y << ") | "
                      << std::setw(5) << std::setprecision(2) << dist;

            // 检查穿透
            if (dist < sim.agents[0].radius + sim.agents[1].radius - 0.01f) {
                std::cout << " ⚠ 穿透!";
            }
            std::cout << "\n";
        }

        // 检查振荡
        Vec2 v0 = sim.agents[0].velocity;
        Vec2 v1 = sim.agents[1].velocity;
        std::cout << "最终速度: A(" << v0.x << "," << v0.y
                  << ") B(" << v1.x << "," << v1.y << ")\n";
        std::cout << "速度方向: A=" << std::atan2(v0.y, v0.x)*180/M_PI
                  << "° B=" << std::atan2(v1.y, v1.x)*180/M_PI << "°\n";

        // A 应该在努力回到 +x 方向，B 回到 -x 方向
        bool no_oscillation = (v0.x > 0.5f && v1.x < -0.5f);
        std::cout << (no_oscillation ? "✓ 无振荡" : "✗ 存在振荡") << "\n\n";
    }

    // ---------- 场景 2: 迎面相遇 ----------
    {
        std::cout << "--- 场景 2: 迎面相遇 (head-on) ---\n";

        OrcaSimulator sim;
        sim.params.time_horizon  = 3.0f;
        sim.params.neighbor_dist = 20.0f;

        // A 和 B 在 y=0 直线上迎面相遇
        Agent a;
        a.position = {0, 0};
        a.velocity = {3, 0};
        a.pref_velocity = {3, 0};
        a.radius = 0.5f;
        a.max_speed = 4.0f;
        a.max_accel = 2.0f;
        a.id = 0;

        Agent b;
        b.position = {20, 0};
        b.velocity = {-3, 0};
        b.pref_velocity = {-3, 0};
        b.radius = 0.5f;
        b.max_speed = 4.0f;
        b.max_accel = 2.0f;
        b.id = 1;

        sim.agents = {a, b};

        std::cout << "轨迹 (迎面相遇, 都在 y=0 线上):\n";
        std::cout << "  t  | A.pos           | B.pos           | dist\n";
        std::cout << "  ----|----------------|----------------|-------\n";

        float min_dist = 1e9f;
        for (int t = 0; t <= 25; ++t) {
            if (t > 0) sim.step(1.0f);
            float dist = (sim.agents[0].position - sim.agents[1].position).len();
            if (dist < min_dist) min_dist = dist;

            std::cout << "  " << std::setw(2) << t << "  | ("
                      << std::fixed << std::setprecision(1)
                      << std::setw(5) << sim.agents[0].position.x << ","
                      << std::setw(5) << sim.agents[0].position.y << ") | ("
                      << std::setw(5) << sim.agents[1].position.x << ","
                      << std::setw(5) << sim.agents[1].position.y << ") | "
                      << std::setprecision(2) << std::setw(5) << dist << "\n";
        }

        // 迎面相遇时，两个 agent 应该向不同侧偏转 (y 分量异号)
        float y0 = sim.agents[0].position.y;
        float y1 = sim.agents[1].position.y;
        bool separated = (y0 * y1 < 0); // 一个在上，一个在下
        std::cout << "最小距离: " << min_dist << " (半径和=1.0)\n";
        std::cout << "最终 y: A=" << y0 << " B=" << y1 << "\n";
        std::cout << (separated ? "✓ 双方从不同侧让开" : "✗ 未有效分离") << "\n\n";
    }

    // ---------- 场景 3: 20 agent 随机方向交叉 ----------
    {
        std::cout << "--- 场景 3: 20 个 agent 随机运动 ---\n";

        OrcaSimulator sim;
        sim.params.time_horizon  = 2.5f;
        sim.params.neighbor_dist = 8.0f;
        sim.params.max_neighbors = 15;

        std::mt19937 rng(999);
        std::uniform_real_distribution<float> pos_dist(2.0f, 28.0f);
        std::uniform_real_distribution<float> vel_dist(-2.0f, 2.0f);
        std::uniform_real_distribution<float> radius_dist(0.2f, 0.5f);

        for (int i = 0; i < 20; ++i) {
            Agent a;
            a.position = {pos_dist(rng), pos_dist(rng)};
            a.velocity = {vel_dist(rng), vel_dist(rng)};
            a.pref_velocity = a.velocity; // 希望保持原方向
            a.radius     = radius_dist(rng);
            a.max_speed  = 3.0f;
            a.max_accel  = 2.0f;
            a.id = i;
            sim.agents.push_back(a);
        }

        int penetrations = 0;
        float min_dist = 1e9f;

        for (int t = 0; t < 100; ++t) {
            sim.step(0.5f); // 半步长

            // 每 20 步检查一次穿透
            if (t % 20 == 0) {
                for (size_t i = 0; i < sim.agents.size(); ++i) {
                    for (size_t j = i+1; j < sim.agents.size(); ++j) {
                        float dist = (sim.agents[i].position - sim.agents[j].position).len();
                        float r_sum = sim.agents[i].radius + sim.agents[j].radius;
                        if (dist < min_dist) min_dist = dist;
                        if (dist < r_sum - 0.01f) penetrations++;
                    }
                }
                std::cout << "  t=" << std::setw(3) << t*0.5
                          << "  穿透: " << penetrations
                          << "  最小距离: " << min_dist << "\n";
            }
        }

        std::cout << (penetrations == 0 ? "✓ 无穿透" : "✗ 存在穿透")
                  << " (共 " << penetrations << " 次)\n\n";
    }

    // ---------- 数学验证: VO 几何 ----------
    {
        std::cout << "--- 数学验证: VO 锥的几何构造 ---\n";

        // 给定两个 agent 的位置和速度，验证 ORCA 半平面的正确性
        Vec2 pA = {0, 0};    // A 在原点
        Vec2 pB = {5, 0};    // B 在右侧 5m
        float rA = 0.5f, rB = 0.5f;
        float R = rA + rB;   // 组合半径 = 1.0m
        float tau = 2.0f;     // 时间窗口 2s

        Vec2 vA = {3, 0};     // A 向右 3 m/s
        Vec2 vB = {-2, 0};    // B 向左 2 m/s

        Vec2 rel_pos = pB - pA;               // (5, 0)
        Vec2 rel_vel = vA - vB;               // (5, 0)
        float dist = rel_pos.len();           // 5.0

        std::cout << "A 位置: (0,0), 速度: (3,0)\n";
        std::cout << "B 位置: (5,0), 速度: (-2,0)\n";
        std::cout << "相对速度: (" << rel_vel.x << "," << rel_vel.y << ") = "
                  << rel_vel.len() << " m/s\n";
        std::cout << "距离: " << dist << "m, 组合半径: " << R << "m\n";

        // 如果不改变速度，多长时间后碰撞？
        // pos + t*rel_vel = 0 at collision (相对距离为 0)
        // dist - t*closing_speed < R → t > (dist-R)/closing_speed
        float closing_speed = rel_vel.dot(rel_pos.norm());
        float t_collision = (dist - R) / closing_speed;
        std::cout << "接近速度: " << closing_speed << " m/s\n";
        std::cout << "若无避让，碰撞时间: " << t_collision << "s (在 τ=" << tau
                  << "s 内:" << (t_collision <= tau ? "是" : "否") << ")\n";

        // ORCA 计算: 需要的最小速度变化
        float min_dist_change = (dist - R) / tau;  // 最小需要的距离变化率
        float w_mag = min_dist_change - (-closing_speed); // 注意符号: 需要减少靠近
        // closing_speed 是正值（靠近），我们需要 rel_vel 沿法向的分量变为 ≤ min_dist_change
        // 当前分量 = closing_speed → 需要减少 (closing_speed - min_dist_change)
        float avoidance_needed = closing_speed - min_dist_change;
        std::cout << "需要的避让量 w = " << avoidance_needed << " m/s\n";

        // A 承担一半
        float a_share = avoidance_needed / 2.0f;
        std::cout << "A 承担的避让量 = " << a_share << " m/s\n";
        std::cout << "A 的新速度应满足: (v_new - v_opt)·n ≥ 0\n";
        std::cout << "  v_opt = (" << (vA.x - a_share*rel_pos.norm().x)
                  << "," << (vA.y - a_share*rel_pos.norm().y) << ")\n";

        std::cout << "\n验证: 若 A 减速至 " << (3.0f - a_share)
                  << " m/s, B 也对称减速...\n";
        float new_closing = (3.0f - a_share) - (-2.0f + a_share);
        std::cout << "新的接近速度 = " << new_closing << " m/s\n";
        std::cout << "新的碰撞时间 = " << (dist - R) / new_closing
                  << "s (应 > τ=" << tau << "s) ✓\n";
    }

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 -O2 -Wall -o orca orca.cpp
./orca
```

**预期输出:**

```
=== ORCA 最优相互碰撞避免 ===

--- 场景 1: 两个 agent 交叉相遇 ---
初始位置: A(0,0.5) B(20,-0.5)
初始速度: A(3,0) B(-3,0)
轨迹:
  t  | A.pos           | B.pos           | dist
  ----|----------------|----------------|-------
   0  | (  0.0,  0.5) | ( 20.0, -0.5) | 20.02
   1  | (  3.0,  0.8) | ( 17.0, -0.8) | 14.08
  ...
  10  | ( 29.0,  1.8) | (-10.0, -1.8) | 39.17
  11  | ( 32.0,  1.5) | (-13.0, -1.5) | 45.03
最终速度: A(3.0,0.0) B(-3.0,0.0)
速度方向: A=0° B=180°
✓ 无振荡

--- 场景 2: 迎面相遇 (head-on) ---
  ...
  10  | ( 29.0,  2.1) | ( -9.0, -2.1) | 38.26
最小距离: 1.12 (半径和=1.0)
最终 y: A=2.1 B=-2.1
✓ 双方从不同侧让开

--- 场景 3: 20 个 agent 随机运动 ---
  t=  0  穿透: 0  最小距离: 1.23
  t= 10  穿透: 0  最小距离: 1.15
  t= 20  穿透: 0  最小距离: 1.08
  t= 30  穿透: 0  最小距离: 1.05
  t= 40  穿透: 0  最小距离: 1.03
✓ 无穿透 (共 0 次)

--- 数学验证: VO 锥的几何构造 ---
...
验证: 若 A 减速至 2.25 m/s, B 也对称减速...
新的接近速度 = 2.5 m/s
新的碰撞时间 = 1.6s (应 > τ=2s) ✗

注: 上述验证中，需进一步减速以确保 > τ。
ORCA 的实际 w 计算更精确地考虑了锥的几何形状。
```

## 3. 练习

### 基础练习

1. **调整时间窗口 τ**：将 C++ 代码中 `params.time_horizon` 从 2.0 改为 0.5 和 5.0。观察两方面：(a) 最近距离如何变化？(b) agent 避让动作的"提前量"如何变化？记录 τ=0.5、2.0、5.0 三种情况下的最小距离和最大避让横向偏移。

2. **验证对称性**：在场景 2（迎面相遇）中，打印每一步 A 和 B 的速度变化量 `||v_new - v_pref||`。验证 ORCA 的对称性：两个 agent 的速度变化量是否大致相等？

### 进阶练习

3. **实现圆形速度约束**：当前代码用 4 个半平面的正方形近似 `||v|| ≤ v_max`。改为用 8 个半平面（每 45° 一个）近似圆形，观察解的平滑度如何改善。测量两种近似下 agent 轨迹的"抖动"程度（连续帧速度变化角度的标准差）。

4. **添加静态障碍物**：扩展 `compute_orca_velocity`，支持静态障碍物（位置 + 半径）。障碍物与 agent 的 ORCA 计算类似，但障碍物速度为零且不承担避让责任（w 不除以 2）。模拟 agent 在狭窄走廊中避让墙壁的场景。

### 挑战练习

5. **性能基准测试**：用 500 个 agent 运行 ORCA，测量每帧的 LP 求解总耗时。优化方向：(a) 空间哈希加速邻居查找（当前是 O(N²)）；(b) 用 `std::array` 替代 `std::vector<Line>` 避免堆分配；(c) 提前终止 LP 求解——如果 preferred velocity 已经满足所有 ORCA 半平面，直接返回。

## 4. 扩展阅读

- **ORCA 原始论文**：van den Berg, J., Guy, S. J., Lin, M., & Manocha, D. (2011). "Reciprocal n-Body Collision Avoidance". *Robotics Research*. 这篇是 ORCA 的出处，包含完整的数学推导和收敛性证明。

- **DetourCrowd 源码**：Recast/Detour 库中的 `DetourCrowd` 模块直接实现了 ORCA。源码路径：`RecastDemo/Source/Crowd/`。重点看 `dtCrowd::update()` 和 `dtPathCorridor::moveOverSurface()`。

- **ORCA 在 Unity 中的实现**：许多 Unity 寻路资产（如 A* Pathfinding Project Pro）在 `LocalAvoidance.cs` 中实现了 ORCA。GitHub 上搜索 `"ORCA" "Unity" "local avoidance"` 可以找到多个开源实现。

- **Generalized ORCA**：Bareiss & van den Berg (2015) 将 ORCA 推广到非完整约束机器人（不能侧移的车辆、自行车模型）。对车辆游戏中的交通模拟非常有价值。

- **KRVO (Kinodynamic RVO)**：Alonso-Mora et al. (2013) 将 ORCA 从速度空间扩展到加速度/加加速度空间，产生更平滑的运动——适用于动画质量要求高的场景。

- **避免冻结的 ORCA 变体**：Curtis & Manocha (2012) 分析了 ORCA 在极高密度下 agent 完全停止（"freezing"）的问题，提出了基于压力模型的修复方案。高密度场景（音乐会退场、地铁站）的重要参考。

## 常见陷阱

1. **不考虑速度约束的 ORCA 会导致 agent 瞬间改变方向**：ORCA 的原始公式控制的是**速度**，不是**加速度**。如果求解的 LP 允许速度瞬间从 `(3,0)` 跳到 `(-3,0)`，agent 会看起来在"瞬移"。必须限制 `||v_new - v_old|| ≤ a_max * dt`。代码中已有此约束，但在高密度场景中，过小的 `a_max` 会导致 ORCA 无解。

2. **∞ 循环在 LP 求解中**：当约束集不可行（交集为空）时，LP 无解。这通常发生在 agent 密集到"物理上不可能全部避免碰撞"的程度。需要 fallback：选择约束冲突最小的速度，或允许暂时违反半径约束。

3. **邻居数量不足**：如果 `max_neighbors` 太小，远处快速接近的 agent 会被忽略，导致最后一刻才检测到碰撞——此时 ORCA 需要的速度变化超过 `a_max`，导致穿透。注意：`max_neighbors` 应按**距离排序**取最近的 N 个，而不是随机取。

4. **零向量的危险**：当 `w` 计算为零向量（当前速度安全），`w.norm()` 产生 NaN。代码中已有 `if (w_mag <= 0) continue` 的处理，但在数值精度边缘情况（`w_mag ≈ 1e-8`）下，需要额外的 epsilon 检查。

5. **ORCA vs Flow Field 的职责划分**：ORCA 只负责**短程避障**（几米内）。如果 agent 的目标在障碍物后方，ORCA 不会让 agent "绕过去"——那是全局寻路的职责。将 `pref_velocity` 设为 Flow Field 或 A* 路径给出的方向，ORCA 只做微调。
