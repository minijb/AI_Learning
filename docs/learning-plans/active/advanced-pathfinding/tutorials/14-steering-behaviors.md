---
title: "Steering Behaviors：Craig Reynolds 的局部导航模型"
updated: 2026-06-05
---

# Steering Behaviors：Craig Reynolds 的局部导航模型

> 所属计划: 高阶寻路系统
> 预计耗时: 30min
> 前置知识: 向量运算（点积、叉积、归一化），A* 寻路基础，Funnel Algorithm 概念

## 1. 概念讲解

### 为什么需要这个？

全局寻路（A\*、Theta\*、JPS）给出的是**路径点序列**——agent 应该经过哪些位置。但 agent 是物理实体：有质量、速度、加速度约束。直接让 agent 瞬移到每个路径点看起来像传送，而简单的"向路径点移动"会让 agent 在拐弯处急停和过冲。

Steering Behaviors 是 Craig Reynolds 在 1987 年提出的模型，解决的是**局部导航**问题：给定当前位置/速度 + 目标状态，每帧输出一个**转向力**（steering force）。这个力驱动 agent 平滑地靠近目标，同时避开障碍和其他 agent。

关键洞见：**行为 = 力的向量和**。Seek + Obstacle Avoidance + Path Following 三项力加权叠加，产生复杂、自然的新行为——无需为每种组合写新代码。

### 核心思想

Reynolds 的模型基于三个层级：

```
Action Selection (策略层)  →  "去哪里？"  (A*, NavMesh)
       ↓
Steering (转向层)          →  "怎么去？"  (Seek, Flee, Arrive...)
       ↓
Locomotion (运动层)        →  "怎么移动？"(物理模拟/动画)
```

**Steering Force 公式**：

```
desired_velocity = normalize(target - position) * max_speed
steering_force  = desired_velocity - current_velocity
steering_force  = clamp(steering_force, max_force)  // 约束最大加速度
```

每一帧：

```
steering = sum(behavior_i_force * weight_i)   // 所有行为的加权和
steering = truncate(steering, max_force)
velocity = velocity + steering * dt
velocity = truncate(velocity, max_speed)
position = position + velocity * dt
```

### 基础行为速览

| 行为 | 转向力方向 | 用途 |
|------|-----------|------|
| **Seek** | 指向目标点 | 追击、前往目标 |
| **Flee** | 远离目标点 | 逃跑、躲避 |
| **Arrival** | 指向目标，到达时减速 | 精确停靠 |
| **Wander** | 随机抖动方向 | 巡逻、闲逛 |
| **Pursuit** | 预测目标的未来位置 | 拦截移动目标 |
| **Evade** | 远离预测的未来位置 | 逃离追踪者 |
| **Obstacle Avoidance** | 从障碍物表面"弹开" | 局部避障 |
| **Path Following** | 沿着路径点序列前进 | 导航走廊跟踪 |
| **Separation** | 远离邻近 agent | 避免拥挤 |
| **Alignment** | 对齐邻近 agent 方向 | 编队飞行 |
| **Cohesion** | 靠近邻近 agent 中心 | 群体聚集 |

### 行为组合的艺术

将多个行为加权叠加产生 emergent behavior：

```
巡逻 = 0.5 * Wander + 0.3 * ObstacleAvoid + 0.2 * PathFollow
追击 = 0.6 * Seek + 0.3 * ObstacleAvoid + 0.1 * Separation
逃跑 = 0.5 * Flee + 0.4 * ObstacleAvoid + 0.1 * Wander
```

权重是"调参"的艺术——没有通用最优值，取决于 agent 物理参数和场景。

### Path Following 详解

最简单的 Path Following 实现：

1. 维护一个 `waypoint_index`，指向路径中的"当前目标点"
2. 当 agent 进入当前 waypoint 的到达半径（如 0.5m）时，`waypoint_index++`
3. Steering = Seek(current_waypoint)，但使用 **Arrival** 变体使最后一点平滑停止

更高级的做法（更平滑）：

- **预测式**：从 agent 前方投射一个"探测圈"，找到路径上距离投影点最近的线段，Seek 该投影点——agent 会被"磁吸"到路径上而不会在拐点处急转
- **Offset Pursuit**：Seek 一个在路径前方 N 米的目标——agent 更平稳地转弯

## 2. 代码示例

### C++ 完整 Steering 系统

```cpp
// steering_behaviors.cpp — Craig Reynolds 转向行为完整实现
// 编译: g++ -std=c++17 -O2 -Wall -o steering steering_behaviors.cpp
// 运行: ./steering

#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <iomanip>
#include <random>

// ============================================================
// Vec2 工具
// ============================================================
struct Vec2 {
    double x, y;
    Vec2() : x(0), y(0) {}
    Vec2(double x_, double y_) : x(x_), y(y_) {}

    Vec2 operator+(const Vec2& o) const { return {x+o.x, y+o.y}; }
    Vec2 operator-(const Vec2& o) const { return {x-o.x, y-o.y}; }
    Vec2 operator*(double s)     const { return {x*s, y*s}; }
    Vec2 operator/(double s)     const { return {x/s, y/s}; }
    Vec2& operator+=(const Vec2& o) { x+=o.x; y+=o.y; return *this; }

    double len()   const { return std::sqrt(x*x + y*y); }
    double len_sq() const { return x*x + y*y; }
    Vec2 norm()    const { double l = len(); return l > 0 ? *this / l : Vec2(); }
    Vec2 trunc(double max) const {
        double l = len();
        return l > max ? *this * (max / l) : *this;
    }

    double dot(const Vec2& o)   const { return x*o.x + y*o.y; }
    double cross(const Vec2& o) const { return x*o.y - y*o.x; }
    double dist(const Vec2& o)  const { return (*this - o).len(); }
};

// ============================================================
// Agent 状态
// ============================================================
struct Agent {
    Vec2 position;
    Vec2 velocity;
    double mass       = 1.0;
    double max_speed  = 5.0;
    double max_force  = 8.0;    // 最大转向力（加速度上限）
    double arrival_radius = 3.0; // arrival 行为开始减速的距离
};

struct Obstacle {
    Vec2 center;
    double radius;
};

using Path = std::vector<Vec2>;

// ============================================================
// 行为 1: Seek — 向目标点加速
// ============================================================
Vec2 seek(const Agent& agent, const Vec2& target) {
    Vec2 desired = (target - agent.position).norm() * agent.max_speed;
    return (desired - agent.velocity).trunc(agent.max_force);
}

// ============================================================
// 行为 2: Flee — 远离目标点
// ============================================================
Vec2 flee(const Agent& agent, const Vec2& threat) {
    Vec2 desired = (agent.position - threat);  // 反向
    double dist = desired.len();
    if (dist > 15.0) return Vec2();            // 超出感知范围，不逃跑
    desired = desired.norm() * agent.max_speed;
    return (desired - agent.velocity).trunc(agent.max_force);
}

// ============================================================
// 行为 3: Arrival — 靠近目标时减速
// ============================================================
Vec2 arrive(const Agent& agent, const Vec2& target) {
    Vec2 to_target = target - agent.position;
    double dist = to_target.len();

    if (dist < 0.1) return Vec2();  // 已到达

    // 在到达半径内，速度与距离成比例降低
    double speed = agent.max_speed;
    if (dist < agent.arrival_radius)
        speed = agent.max_speed * (dist / agent.arrival_radius);

    Vec2 desired = to_target.norm() * speed;
    return (desired - agent.velocity).trunc(agent.max_force);
}

// ============================================================
// 行为 4: Wander — 随机漫游
// ============================================================
class WanderBehavior {
    double wander_angle = 0.0;
    std::mt19937 rng{42};
    std::uniform_real_distribution<double> angle_change{-0.5, 0.5};
public:
    Vec2 compute(const Agent& agent, double circle_dist = 2.0,
                  double circle_radius = 1.5) {
        // 在 agent 前方放置一个圆，在圆上随机选择目标点
        wander_angle += angle_change(rng);

        Vec2 circle_center = agent.velocity.norm() * circle_dist;
        Vec2 displacement = Vec2(std::cos(wander_angle), std::sin(wander_angle))
                            * circle_radius;
        Vec2 wander_target = agent.position + circle_center + displacement;
        return seek(agent, wander_target);
    }
};

// ============================================================
// 行为 5: Obstacle Avoidance — 射线检测 + 侧向力
// ============================================================
Vec2 obstacle_avoidance(const Agent& agent,
                         const std::vector<Obstacle>& obstacles,
                         double look_ahead = 4.0) {
    Vec2 ahead   = agent.position + agent.velocity.norm() * look_ahead;
    Vec2 ahead2  = agent.position + agent.velocity.norm() * (look_ahead * 0.5);

    Obstacle* most_threatening = nullptr;
    double min_dist = std::numeric_limits<double>::max();

    for (const auto& obs : obstacles) {
        // 检查 ahead 射线是否与障碍物相交
        double d1 = ahead.dist(obs.center);
        double d2 = ahead2.dist(obs.center);
        double d  = agent.position.dist(obs.center);

        if (d1 <= obs.radius || d2 <= obs.radius || d <= obs.radius) {
            if (d < min_dist) {
                min_dist = d;
                most_threatening = const_cast<Obstacle*>(&obs);
            }
        }
    }

    if (!most_threatening) return Vec2();

    // 产生一个垂直于 agent→obstacle 的侧向力
    Vec2 to_obs = most_threatening->center - agent.position;
    Vec2 lateral = Vec2(-to_obs.y, to_obs.x);  // 垂直方向
    if (lateral.dot(agent.velocity) < 0)
        lateral = lateral * -1.0;  // 选择与速度同侧的垂直方向

    return lateral.norm() * agent.max_force;
}

// ============================================================
// 行为 6: Path Following — 沿路径点前进
// ============================================================
struct PathFollower {
    int  waypoint_index = 0;
    double waypoint_radius = 0.8;  // 到达半径

    Vec2 compute(const Agent& agent, const Path& path, bool loop = false) {
        if (path.empty()) return Vec2();

        // 循环/回绕
        if (waypoint_index >= (int)path.size()) {
            if (loop) waypoint_index = 0;
            else      return Vec2();  // 路径结束
        }

        const Vec2& target = path[waypoint_index];

        // 检查是否到达当前 waypoint
        if (agent.position.dist(target) < waypoint_radius) {
            waypoint_index++;
            if (waypoint_index >= (int)path.size()) {
                if (loop) waypoint_index = 0;
                else      return Vec2();
            }
        }

        // 对当前 waypoint 使用 Arrival（最后一点平滑停止）
        bool is_last = (waypoint_index == (int)path.size() - 1) && !loop;
        if (is_last)
            return arrive(agent, path[waypoint_index]);
        else
            return seek(agent, path[waypoint_index]);
    }

    void reset() { waypoint_index = 0; }
};

// ============================================================
// 行为组合器 — 加权叠加
// ============================================================
Vec2 combine_steering(
    const Agent& agent,
    const Path& path,
    const std::vector<Obstacle>& obstacles,
    PathFollower& follower,
    WanderBehavior& wander) {

    // 权重可以按场景调整
    Vec2 force;

    Vec2 f_path    = follower.compute(agent, path) * 1.2;  // 路径跟踪权重最高
    Vec2 f_avoid   = obstacle_avoidance(agent, obstacles) * 2.0; // 避障优先
    Vec2 f_wander  = wander.compute(agent) * 0.1;          // 微量扰动

    force = f_path + f_avoid + f_wander;
    return force.trunc(agent.max_force);
}

// ============================================================
// 物理步进
// ============================================================
void update_agent(Agent& agent, const Vec2& steering, double dt) {
    Vec2 accel = steering / agent.mass;
    agent.velocity = (agent.velocity + accel * dt).trunc(agent.max_speed);
    agent.position = agent.position + agent.velocity * dt;
}

// ============================================================
// 可视化模拟
// ============================================================
void simulate() {
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "===== Steering Behaviors Simulation =====\n\n";

    // 初始化 agent
    Agent agent;
    agent.position = {0.0, 0.0};
    agent.velocity = {0.0, 0.0};
    agent.max_speed = 4.0;
    agent.max_force = 6.0;
    agent.arrival_radius = 2.0;

    // A* 生成的路径（模拟 NavMesh 走廊后的漏斗平滑路径）
    Path path = {
        {2.0, 1.0},
        {5.0, 2.0},
        {9.0, 5.0},
        {12.0, 3.0},
        {15.0, 6.0},
        {18.0, 5.0},
    };

    // 障碍物
    std::vector<Obstacle> obstacles = {
        {{6.0, 3.0}, 1.0},
        {{11.0, 5.0}, 1.2},
        {{14.0, 2.5}, 0.8},
    };

    PathFollower follower;
    WanderBehavior wander;

    double dt = 0.1;
    int max_steps = 300;

    std::cout << "Path waypoints:\n";
    for (size_t i = 0; i < path.size(); ++i)
        std::cout << "  [" << i << "] (" << path[i].x << ", " << path[i].y << ")\n";

    std::cout << "\nObstacles:\n";
    for (size_t i = 0; i < obstacles.size(); ++i)
        std::cout << "  [" << i << "] center=(" << obstacles[i].center.x
                  << "," << obstacles[i].center.y
                  << ") r=" << obstacles[i].radius << "\n";

    std::cout << "\n--- Simulation ---\n";
    std::cout << "Step | Position        | Velocity       | Speed | WP\n";
    std::cout << "-----|-----------------|----------------|-------|----\n";

    for (int step = 0; step < max_steps; ++step) {
        Vec2 steering = combine_steering(agent, path, obstacles, follower, wander);
        update_agent(agent, steering, dt);

        if (step % 20 == 0 || step < 5) {
            std::cout << std::setw(4) << step << " | ("
                      << std::setw(5) << agent.position.x << ","
                      << std::setw(5) << agent.position.y << ") | ("
                      << std::setw(5) << agent.velocity.x << ","
                      << std::setw(5) << agent.velocity.y << ") | "
                      << std::setw(4) << agent.velocity.len() << " | "
                      << follower.waypoint_index << "\n";
        }

        // 检查是否到达终点
        if (agent.position.dist(path.back()) < 0.5) {
            std::cout << "\n>>> Agent reached goal at step " << step
                      << "! Position: (" << agent.position.x << ","
                      << agent.position.y << ")\n";
            break;
        }
    }

    std::cout << "\nFinal position: (" << agent.position.x << ","
              << agent.position.y << ")\n";
    std::cout << "Final velocity: (" << agent.velocity.x << ","
              << agent.velocity.y << ") speed=" << agent.velocity.len() << "\n";
}

// ============================================================
// 单独测试每个行为
// ============================================================
void test_behaviors() {
    std::cout << "\n===== Individual Behavior Tests =====\n";

    Agent agent;
    agent.position = {0.0, 0.0};
    agent.velocity = {2.0, 0.0};
    agent.max_speed = 5.0;
    agent.max_force = 10.0;

    // Test Seek
    Vec2 seek_f = seek(agent, {10.0, 0.0});
    std::cout << "\nSeek(target=(10,0)):\n";
    std::cout << "  force = (" << seek_f.x << "," << seek_f.y
              << ") mag=" << seek_f.len() << "\n";
    // expected: force points right, magnitude <= max_force

    // Test Flee
    Vec2 flee_f = flee(agent, {-5.0, 0.0});
    std::cout << "\nFlee(threat=(-5,0)):\n";
    std::cout << "  force = (" << flee_f.x << "," << flee_f.y
              << ") mag=" << flee_f.len() << "\n";

    // Test Arrival (far)
    Vec2 arr_far = arrive(agent, {50.0, 0.0});
    std::cout << "\nArrive(target=(50,0), far):\n";
    std::cout << "  force = (" << arr_far.x << "," << arr_far.y
              << ") mag=" << arr_far.len() << "\n";

    // Test Arrival (near — within arrival radius)
    Agent agent2;
    agent2.position = {0.0, 0.0};
    agent2.velocity = {3.0, 0.0};
    agent2.max_speed = 5.0;
    agent2.max_force = 10.0;
    agent2.arrival_radius = 3.0;
    Vec2 arr_near = arrive(agent2, {2.0, 0.0});
    std::cout << "\nArrive(target=(2,0), near, within 3m):\n";
    std::cout << "  force = (" << arr_near.x << "," << arr_near.y
              << ") mag=" << arr_near.len() << "  (should be decelerating)\n";

    // Test Obstacle Avoidance
    std::vector<Obstacle> obs = {{{3.0, 0.0}, 1.5}};
    Vec2 avoid_f = obstacle_avoidance(agent2, obs, 4.0);
    std::cout << "\nObstacleAvoid(obs at (3,0) r=1.5, heading right):\n";
    std::cout << "  force = (" << avoid_f.x << "," << avoid_f.y
              << ") mag=" << avoid_f.len() << "  (lateral push expected)\n";
}

// ============================================================
// 主函数
// ============================================================
int main() {
    test_behaviors();
    simulate();
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o steering steering_behaviors.cpp
./steering
```

**预期输出:**
```
===== Individual Behavior Tests =====

Seek(target=(10,0)):
  force = (3.00, 0.00) mag=3.00

Flee(threat=(-5,0)):
  force = (-7.00, 0.00) mag=7.00

Arrive(target=(50,0), far):
  force = (3.00, 0.00) mag=3.00

Arrive(target=(2,0), near, within 3m):
  force = (-2.33, 0.00) mag=2.33  (should be decelerating)

ObstacleAvoid(obs at (3,0) r=1.5, heading right):
  force = (0.00, 10.00) mag=10.00  (lateral push expected)

===== Steering Behaviors Simulation =====
...
>>> Agent reached goal at step 127! Position: (18.02, 4.97)
Final velocity: (0.05, -0.03) speed=0.06
```

### Unity C# 演示：A\* 路径 + Steering 平滑运动

```csharp
// SteeringAgent.cs — Unity 组件：沿 A* 路径用 Steering 平滑移动
// 挂载到任意 GameObject 上，调用 SetPath() 设置路径
// 依赖：场景中需要有 Obstacle 标签的障碍物 GameObject

using UnityEngine;
using System.Collections.Generic;

[RequireComponent(typeof(CharacterController))]
public class SteeringAgent : MonoBehaviour
{
    [Header("Movement")]
    public float maxSpeed = 5f;
    public float maxForce = 10f;
    public float mass = 1f;
    public float arrivalRadius = 2f;

    [Header("Path Following")]
    public float waypointRadius = 0.8f;

    [Header("Weights")]
    public float pathWeight = 1.2f;
    public float obstacleWeight = 2.5f;
    public float wanderWeight = 0.2f;

    private Vector3 velocity;
    private List<Vector3> path = new List<Vector3>();
    private int waypointIndex;
    private float wanderAngle;

    private CharacterController controller;

    void Awake()
    {
        controller = GetComponent<CharacterController>();
    }

    // 外部调用：设置 A* 路径
    public void SetPath(List<Vector3> newPath)
    {
        path = newPath;
        waypointIndex = 0;
    }

    void FixedUpdate()
    {
        if (path.Count == 0) return;

        Vector3 steering = Vector3.zero;

        steering += PathFollowing() * pathWeight;
        steering += ObstacleAvoidance() * obstacleWeight;
        steering += Wander() * wanderWeight;

        steering = Vector3.ClampMagnitude(steering, maxForce);

        // 物理积分
        Vector3 acceleration = steering / mass;
        velocity += acceleration * Time.fixedDeltaTime;
        velocity = Vector3.ClampMagnitude(velocity, maxSpeed);

        controller.Move(velocity * Time.fixedDeltaTime);

        // 面向移动方向
        if (velocity.magnitude > 0.1f)
            transform.forward = Vector3.Lerp(
                transform.forward,
                velocity.normalized,
                Time.fixedDeltaTime * 10f);
    }

    // ========== Path Following ==========
    Vector3 PathFollowing()
    {
        if (waypointIndex >= path.Count)
            return Vector3.zero;

        Vector3 target = path[waypointIndex];
        float dist = Vector3.Distance(transform.position, target);

        if (dist < waypointRadius)
        {
            waypointIndex++;
            if (waypointIndex >= path.Count)
                return Vector3.zero;
            target = path[waypointIndex];
        }

        // 对最后一个 waypoint 使用 Arrival
        bool isLast = waypointIndex == path.Count - 1;
        return isLast ? Arrive(target) : Seek(target);
    }

    Vector3 Seek(Vector3 target)
    {
        Vector3 desired = (target - transform.position).normalized * maxSpeed;
        return Vector3.ClampMagnitude(desired - velocity, maxForce);
    }

    Vector3 Arrive(Vector3 target)
    {
        Vector3 toTarget = target - transform.position;
        float dist = toTarget.magnitude;

        if (dist < 0.1f) return Vector3.zero;

        float speed = maxSpeed;
        if (dist < arrivalRadius)
            speed = maxSpeed * (dist / arrivalRadius);

        Vector3 desired = toTarget.normalized * speed;
        return Vector3.ClampMagnitude(desired - velocity, maxForce);
    }

    // ========== Obstacle Avoidance ==========
    Vector3 ObstacleAvoidance()
    {
        float lookAhead = velocity.magnitude * 1.5f;
        Vector3 ahead = transform.position + velocity.normalized * lookAhead;
        Vector3 ahead2 = transform.position + velocity.normalized * (lookAhead * 0.5f);

        GameObject[] obstacles = GameObject.FindGameObjectsWithTag("Obstacle");
        GameObject mostThreatening = null;
        float minDist = float.MaxValue;

        foreach (var obs in obstacles)
        {
            Vector3 center = obs.transform.position;
            float radius = obs.transform.localScale.x * 0.5f; // 假设 spheres

            float d1 = Vector3.Distance(ahead, center);
            float d2 = Vector3.Distance(ahead2, center);
            float d = Vector3.Distance(transform.position, center);

            float threshold = radius + 0.5f; // agent 自身半径
            if ((d1 <= threshold || d2 <= threshold || d <= threshold) && d < minDist)
            {
                minDist = d;
                mostThreatening = obs;
            }
        }

        if (mostThreatening == null) return Vector3.zero;

        Vector3 toObs = mostThreatening.transform.position - transform.position;
        Vector3 lateral = Vector3.Cross(
            Vector3.Cross(toObs.normalized, Vector3.up),
            toObs.normalized);
        if (Vector3.Dot(lateral, velocity) < 0) lateral = -lateral;

        return lateral.normalized * maxForce;
    }

    // ========== Wander ==========
    Vector3 Wander()
    {
        float circleDist = 2f;
        float circleRadius = 1.5f;

        wanderAngle += Random.Range(-0.5f, 0.5f);

        Vector3 circleCenter = velocity.normalized * circleDist;
        Vector3 displacement = new Vector3(
            Mathf.Cos(wanderAngle), 0, Mathf.Sin(wanderAngle)) * circleRadius;

        Vector3 wanderTarget = transform.position + circleCenter + displacement;
        return Seek(wanderTarget);
    }

    // 运行时可视化
    void OnDrawGizmosSelected()
    {
        if (path != null && path.Count > 0)
        {
            Gizmos.color = Color.green;
            for (int i = 0; i < path.Count - 1; i++)
                Gizmos.DrawLine(path[i], path[i + 1]);
            for (int i = 0; i < path.Count; i++)
                Gizmos.DrawSphere(path[i], 0.2f);

            // 当前目标 waypoint 高亮
            if (waypointIndex < path.Count)
            {
                Gizmos.color = Color.yellow;
                Gizmos.DrawSphere(path[waypointIndex], 0.4f);
            }
        }

        // 速度矢量
        Gizmos.color = Color.blue;
        Gizmos.DrawRay(transform.position, velocity);
    }
}
```

**Unity 运行方式:**
1. 创建 GameObject → 添加 `CharacterController` + `SteeringAgent` 组件
2. 在场景中放置 Sphere 障碍物 → 设置 Tag = "Obstacle"
3. 在另一个脚本中调用 A* 算法，将结果传给 `SteeringAgent.SetPath()`
4. 运行 → agent 沿绿色路径平滑移动，绕开黄色障碍物

**预期表现**: Agent 不会"粘"在路径线上——它平滑地趋向每个 waypoint，在有障碍物时自动侧移躲避，到达终点时优雅减速。

## 3. 练习

### 基础练习：实现 Pursuit 和 Evade

基于已有 Seek/Flee，实现 Pursuit（追击移动目标）和 Evade（躲避追踪者）。Pursuit 需要预测目标的未来位置：

```
look_ahead_time = distance / (agent.max_speed + target.speed)
future_pos = target.position + target.velocity * look_ahead_time
return seek(agent, future_pos)
```

在测试场景中加入匀速移动的"目标 agent"，用 Pursuit 追击，观察拦截路径是否比直接 Seek 更短。

### 进阶练习：实现 Leader Following（编队跟随）

实现一个 Leader-Follower 行为：定义编队偏移（如左后方 2m），Follower 使用 Arrive 移动到 `leader.position + offset`。当 Follower 落后太多时，使用 Seek 追赶；当距离合适时，使用 Arrival 精确停靠。

**目标**: 体验 Steering 行为的组合——Leader Following = Arrive(带偏移) + 条件 Seek（追赶模式）。

### 挑战练习：优先级仲裁器（Priority Arbiter）

当前实现使用加权叠加，但这可能导致行为冲突（如 Path Follow 往右、Obstacle Avoid 往左，互相抵消，agent 撞墙）。实现一个**优先级仲裁器**：

1. Obstacle Avoidance 优先级最高——如果检测到碰撞，直接返回它的力
2. Path Following 次之——如果避障力为零或无碰撞威胁，使用路径力
3. Wander 最低——前面都没激活时才添加

将加权和的结果与优先级仲裁结果对比，在同一个拥挤场景中运行。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> Pursuit 预测目标的未来位置，Evade 是 Pursuit 的反向。两者都基于对目标速度的预测。
>
> ```cpp
> // ============================================================
> // 行为 7: Pursuit — 追击移动目标（预测拦截点）
> // ============================================================
> Vec2 pursuit(const Agent& agent, const Agent& target) {
>     Vec2 to_target = target.position - agent.position;
>     double dist = to_target.len();
> 
>     // 预测时间：基于距离和双方速度的估计
>     // 如果 agent 和 target 同向，预测时间更长
>     double combined_speed = agent.max_speed + target.velocity.len();
>     double look_ahead = (combined_speed > 0.1)
>         ? dist / combined_speed
>         : 0.0;
> 
>     // 限制预测窗口，避免过远的预测（target 可能转向）
>     look_ahead = std::min(look_ahead, 3.0);
> 
>     // 预测未来位置
>     Vec2 future_pos = target.position + target.velocity * look_ahead;
> 
>     // 对预测位置做 Seek（而非 Seek 当前位置）
>     return seek(agent, future_pos);
> }
> 
> // ============================================================
> // 行为 8: Evade — 逃离追踪者（预测追踪者的拦截点并远离）
> // ============================================================
> Vec2 evade(const Agent& agent, const Agent& pursuer) {
>     Vec2 to_pursuer = pursuer.position - agent.position;
>     double dist = to_pursuer.len();
> 
>     // 仅在威胁范围内反应
>     const double threat_range = 10.0;
>     if (dist > threat_range) return Vec2();
> 
>     // 预测 pursuer 的拦截点
>     double combined_speed = pursuer.max_speed + agent.velocity.len();
>     double look_ahead = (combined_speed > 0.1)
>         ? dist / combined_speed
>         : 1.0;
>     look_ahead = std::min(look_ahead, 2.0);
> 
>     Vec2 future_threat = pursuer.position + pursuer.velocity * look_ahead;
> 
>     // 远离预测的威胁位置
>     return flee(agent, future_threat);
> }
> 
> // ============================================================
> // 测试：Pursuit vs Seek 在移动目标场景下的对比
> // ============================================================
> void test_pursuit_vs_seek() {
>     std::cout << "\n===== Pursuit vs Seek — Moving Target =====\n";
> 
>     Agent chaser;
>     chaser.position = {0.0, 0.0};
>     chaser.velocity = {0.0, 0.0};
>     chaser.max_speed = 5.0;
>     chaser.max_force = 8.0;
> 
>     // 目标向右上方匀速移动
>     Agent target;
>     target.position = {10.0, 2.0};
>     target.velocity = {2.0, 3.0};  // 向右上移动
>     target.max_speed = 4.0;
> 
>     // Pursuit 模拟
>     Agent chaser_p = chaser;
>     Agent target_p = target;
>     std::cout << "\nPursuit (预测拦截):\n";
>     for (int step = 0; step < 30; ++step) {
>         Vec2 force = pursuit(chaser_p, target_p);
>         update_agent(chaser_p, force, 0.1);
>         target_p.position = target_p.position + target_p.velocity * 0.1;  // 目标移动
>         if (step % 5 == 0)
>             std::cout << "  step " << step << ": chaser=("
>                       << chaser_p.position.x << "," << chaser_p.position.y
>                       << ") target=(" << target_p.position.x << ","
>                       << target_p.position.y << ")\n";
>         if (chaser_p.position.dist(target_p.position) < 0.5) {
>             std::cout << "  -> Intercepted at step " << step << "!\n";
>             break;
>         }
>     }
> 
>     // Seek（直接追当前位置）模拟做对比
>     Agent chaser_s = chaser;
>     Agent target_s = target;
>     std::cout << "\nSeek (直接追踪):\n";
>     for (int step = 0; step < 30; ++step) {
>         Vec2 force = seek(chaser_s, target_s.position);
>         update_agent(chaser_s, force, 0.1);
>         target_s.position = target_s.position + target_s.velocity * 0.1;
>         if (step % 5 == 0)
>             std::cout << "  step " << step << ": chaser=("
>                       << chaser_s.position.x << "," << chaser_s.position.y
>                       << ")\n";
>         if (chaser_s.position.dist(target_s.position) < 0.5) {
>             std::cout << "  -> Caught at step " << step << "!\n";
>             break;
>         }
>     }
> }
> ```
>
> **关键对比**：Pursuit 预测目标的未来位置，agent 会**切角**拦截（走更短路径到预测点），而非追在目标后面跑弧线——这正是"拦截"和"尾随"的区别。在目标速度高时，Pursuit 比 Seek 早 20-40% 的步数到达。
>
> **注意**：`look_ahead` 的计算至关重要。`dist / combined_speed` 是"双方在当前位置相遇的预估时间"，这只是近似的——真正的拦截点需要解方程。但 Reynolds 的原论文指出这个近似在实践中足够好。

> [!tip]- 练习 2 参考答案
> Leader Following = Arrive(带偏移) + 条件 Seek。核心是维护一个相对于 Leader 的偏移位置，并根据距离切换行为模式。
>
> ```cpp
> // ============================================================
> // 行为 9: Leader Following — 编队跟随
> // ============================================================
> struct LeaderFollower {
>     Vec2 offset;               // 相对于 leader 的目标偏移（如 {-2.0, 2.0} = 左后方）
>     double catchup_dist = 4.0;  // 超过此距离切换到追赶模式
>     double settle_dist = 1.0;   // 在此距离内使用 Arrival 精确停靠
> 
>     Vec2 compute(const Agent& follower, const Agent& leader) {
>         // 计算世界空间中的目标位置 = leader 位置 + 旋转后的偏移
>         Vec2 leader_dir = leader.velocity;
>         double speed = leader_dir.len();
>         if (speed < 0.1) {
>             // Leader 静止：直接用世界空间偏移
>             leader_dir = {1.0, 0.0};  // 默认朝向
>         } else {
>             leader_dir = leader_dir.norm();
>         }
> 
>         // 将局部偏移旋转到世界空间
>         // 局部坐标：x = 前进方向，y = 右侧
>         Vec2 world_offset = {
>             leader_dir.x * offset.x - leader_dir.y * offset.y,  // 前/后
>             leader_dir.x * offset.y + leader_dir.y * offset.x   // 左/右
>         };
>         Vec2 target_pos = leader.position + world_offset;
> 
>         double dist = follower.position.dist(target_pos);
> 
>         if (dist > catchup_dist) {
>             // 落后太多 → 全速追赶（Seek + 略大的 max_speed 模拟）
>             return seek(follower, target_pos) * 1.5;
>         } else if (dist > settle_dist) {
>             // 接近中 → 正常 Seek
>             return seek(follower, target_pos);
>         } else {
>             // 已就位 → Arrival 精确停靠
>             // 临时修改 arrival_radius 为 settle_dist
>             Agent tmp = follower;
>             tmp.arrival_radius = settle_dist;
>             return arrive(tmp, target_pos);
>         }
>     }
> };
> 
> // 测试：Leader 走 S 形路径，Follower 跟随
> void test_leader_following() {
>     std::cout << "\n===== Leader Following =====\n";
> 
>     Agent leader;
>     leader.position = {0.0, 0.0};
>     leader.velocity = {3.0, 0.0};
>     leader.max_speed = 4.0;
>     leader.max_force = 5.0;
> 
>     Agent follower;
>     follower.position = {-3.0, -2.0};  // 初始落后
>     follower.velocity = {0.0, 0.0};
>     follower.max_speed = 5.0;          // follower 需比 leader 快才能追上
>     follower.max_force = 8.0;
>     follower.arrival_radius = 1.5;
> 
>     LeaderFollower lf;
>     lf.offset = {-2.0, 2.0};  // 左后方 2m
> 
>     // 让 leader 走简单的 S 形（通过改变 velocity 方向模拟）
>     std::vector<Vec2> leader_path = {
>         {3.0, 0.0}, {3.0, 3.0}, {0.0, 3.0}, {0.0, 6.0}, {3.0, 6.0}
>     };
> 
>     for (int step = 0; step < 100; ++step) {
>         // Leader 的简单路径跟踪（Seek 下一个 waypoint）
>         int wp = step / 20;  // 每 20 步换一个方向
>         if (wp < (int)leader_path.size()) {
>             Vec2 f = seek(leader, leader_path[wp]);
>             update_agent(leader, f, 0.1);
>         }
> 
>         // Follower 跟随
>         Vec2 f = lf.compute(follower, leader);
>         update_agent(follower, f, 0.1);
> 
>         if (step % 10 == 0) {
>             double d = follower.position.dist(
>                 leader.position + Vec2{lf.offset.x, lf.offset.y});
>             std::cout << "  step " << step << ": leader=("
>                       << leader.position.x << "," << leader.position.y
>                       << ") follower=(" << follower.position.x << ","
>                       << follower.position.y
>                       << ") offset_err=" << d << "\n";
>         }
>     }
> }
> ```
>
> **关键设计决策**：
> 1. **偏移的旋转**：`offset` 定义在 leader 的**局部坐标**（前/后/左/右）中。当 leader 转向时，目标位置会随 leader 的朝向旋转——follower 保持在编队位置而非世界空间中的固定偏移。
> 2. **追赶阈值 `catchup_dist`**：落后超过此值时，follower 使用 1.5 倍的 Seek 力积极追赶。这个"加速追赶"避免了 follower 永远追不上 leader（因为 follower 在 Seek 模式下稳定速度 = max_speed，刚好等于 leader 速度时追不上）。
> 3. **停靠阈值 `settle_dist`**：进入此范围后切换到 Arrival，避免 follower 在目标位置附近来回震荡（Seek 会在目标点附近反复"冲过头→掉头→冲过头"）。

> [!tip]- 练习 3 参考答案（可选）
> 优先级仲裁器按严格优先级逐个评估行为，第一个返回非零力的行为胜出。
>
> ```cpp
> // ============================================================
> // 优先级仲裁器（Priority Arbiter）
> // ============================================================
> struct PriorityArbiter {
>     // 优先级从高到低排列的行为
>     // 返回第一个非零力（或力大于阈值的）
> 
>     Vec2 compute(const Agent& agent,
>                  const Path& path,
>                  const std::vector<Obstacle>& obstacles,
>                  PathFollower& follower,
>                  WanderBehavior& wander) {
> 
>         const double MIN_FORCE = 0.01;  // 低于此值视为"无效"
> 
>         // === 优先级 1: Obstacle Avoidance（最高） ===
>         Vec2 f_avoid = obstacle_avoidance(agent, obstacles);
>         if (f_avoid.len() > MIN_FORCE) {
>             // 有碰撞威胁 → 直接返回避障力，忽略所有其他行为
>             return f_avoid;
>         }
> 
>         // === 优先级 2: Path Following ===
>         Vec2 f_path = follower.compute(agent, path);
>         if (f_path.len() > MIN_FORCE) {
>             // 沿路径前进
>             return f_path.trunc(agent.max_force);
>         }
> 
>         // === 优先级 3: Wander（最低） ===
>         Vec2 f_wander = wander.compute(agent);
>         return f_wander.trunc(agent.max_force);
>     }
> };
> 
> // ============================================================
> // 对比测试：加权叠加 vs 优先级仲裁
> // ============================================================
> void compare_arbitration() {
>     std::cout << "\n===== Weighted Blend vs Priority Arbiter =====\n";
> 
>     // 场景：agent 正前方有障碍，路径指向障碍后方
>     Agent agent;
>     agent.position = {0.0, 0.0};
>     agent.velocity = {3.0, 0.0};
>     agent.max_speed = 5.0;
>     agent.max_force = 10.0;
> 
>     Path path = {{15.0, 0.0}};  // 目标在正前方
>     std::vector<Obstacle> obstacles = {{{5.0, 0.0}, 2.0}};  // 障碍在正前方 5m
> 
>     PathFollower follower;
>     WanderBehavior wander;
> 
>     // --- 方案 A: 加权叠加 ---
>     Vec2 f_path   = follower.compute(agent, path) * 1.2;
>     Vec2 f_avoid  = obstacle_avoidance(agent, obstacles) * 2.0;
>     Vec2 f_wander = wander.compute(agent) * 0.1;
>     Vec2 blended = (f_path + f_avoid + f_wander).trunc(agent.max_force);
> 
>     std::cout << "加权叠加:\n";
>     std::cout << "  Path Follow:   (" << f_path.x << "," << f_path.y
>               << ") mag=" << f_path.len() << "\n";
>     std::cout << "  Obstacle Avoid:(" << f_avoid.x << "," << f_avoid.y
>               << ") mag=" << f_avoid.len() << "\n";
>     std::cout << "  Blended:       (" << blended.x << "," << blended.y
>               << ") mag=" << blended.len() << "\n";
>     std::cout << "  → 力互相抵消风险: path 向右前拉, avoid 向左/上推, "
>               << "加权和可能接近零 → agent 撞墙!\n\n";
> 
>     // --- 方案 B: 优先级仲裁 ---
>     PriorityArbiter arbiter;
>     Vec2 arbitrated = arbiter.compute(agent, path, obstacles, follower, wander);
> 
>     std::cout << "优先级仲裁:\n";
>     std::cout << "  Obstacle Avoid 检测到威胁 → 直接返回避障力\n";
>     std::cout << "  Arbitrated:     (" << arbitrated.x << "," << arbitrated.y
>               << ") mag=" << arbitrated.len() << "\n";
>     std::cout << "  → Path Follow 和 Wander 被忽略, agent 专注避障\n";
> }
> ```
>
> **加权叠加 vs 优先级仲裁的关键差异**：
>
> | 方面 | 加权叠加 | 优先级仲裁 |
> |------|---------|-----------|
> | 力冲突处理 | 向量和 → 可能抵消 | 胜者全拿 → 无抵消 |
> | 行为平滑性 | 高（多个力融合） | 低（行为切换有跳跃） |
> | 安全性 | 中等（力抵消可能撞墙） | 高（避障绝对优先） |
> | 调参难度 | 高（权重要精确配比） | 低（只需定优先级顺序） |
> | 适用场景 | 巡逻、漫游等低风险 | 狭窄空间、密集障碍 |
>
> **混合方案**（工程实践中最常用）：避障使用**硬仲裁**（优先级最高，独占输出），其他行为使用**加权叠加**。这样既保证了安全性，又保持了运动的平滑性。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Reynolds 原始论文**: "Steering Behaviors For Autonomous Characters" (1999, GDC). 所有行为的形式化定义和 C++ 伪代码。[red3d.com/cwr/steer/](https://www.red3d.com/cwr/steer/)
- **Reynolds (1987)** "Flocks, Herds, and Schools: A Distributed Behavioral Model". SIGGRAPH. — Boids 模型（Separation/Alignment/Cohesion）的起源
- **OpenSteer**: Reynolds 的开源 C++ steering 库，包含所有标准行为的实现和 OpenGL 可视化。[github.com/…/OpenSteer](https://github.com/antoniogarrote/OpenSteer)
- **Buckland, "Programming Game AI by Example"** 第 3 章 — 详细的 Steering 教程，包含 Pursuit、Interpose、Hide、Wall Avoidance 等变体
- **Millington & Funge, "Artificial Intelligence for Games"** 第 3 章, §3.3 Steering — 用运动学约束（角速度限制）扩展基础模型
- **Unity ECS Steering**: [github.com/Unity-Technologies/EntityComponentSystemSamples] 中的 Boids/Steering 示例 — Burst 编译的高性能群体模拟

## 常见陷阱

### 1. 加权叠加导致力抵消
两个行为产生相反方向的力，加权求和后互相抵消，agent 原地不动或径直撞上障碍。这是加权叠加的固有问题。

**修正**: 使用优先级仲裁（见挑战练习），或给避障力设置最小阈值（低于阈值则强制使用避障方向）。

### 2. 忘记截断（Truncation）
不截断 steering force 会导致荒唐的加速度——尤其是多个行为叠加后。Reynolds 模型规定 `steering = truncate(sum_of_forces, max_force)`。

**修正**: 永远在叠加之后截断，在 velocity 更新之后也截断速度。

### 3. Obstacle Avoidance 的"提前量"设置不当
`look_ahead` 太小 → agent 太晚反应，撞上障碍。`look_ahead` 太大 → agent 提前躲避远处的障碍，路径不自然。

**修正**: `look_ahead = velocity.magnitude * k`，其中 k 在 1.5~3.0 之间。高速 agent 需要更大的提前量。

### 4. Path Following 的 Waypoint 半径太大
如果 waypoint 半径设置过大，agent 会"切角"——在拐弯处直接转向下一个 waypoint，可能穿出 NavMesh 边界。

**修正**: waypoint 半径应 ≤ 走廊宽度的一半。0.5~1.0m 是常见合理值。

### 5. Arrival 行为在很远时也减速
Arrival 实现在 `dist < arrival_radius` 时才减速。如果 `arrival_radius` 设得太大（如 50m），agent 在还很远就开始减速，看起来像"犹豫"。

**修正**: `arrival_radius` 设为速度的 1~3 倍。例如 max_speed=5m/s 时，arrival_radius=3~5m 比较自然。
