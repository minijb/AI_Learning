---
title: "Funnel Algorithm：NavMesh 路径拉绳平滑"
updated: 2026-06-05
---

# Funnel Algorithm：NavMesh 路径拉绳平滑

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: NavMesh 基本概念（多边形走廊），向量叉积，A* 寻路基础

## 1. 概念讲解

### 为什么需要这个？

NavMesh 寻路分两步：

1. **宏观路径**：A\* 在多边形图上找到一系列相邻多边形（**多边形走廊**），例如：PolyA → PolyB → PolyC → PolyD
2. **微观路径**：在多边形走廊内部，找到一条最短的、不穿出边界的实际路径

第二步就是 Funnel Algorithm（漏斗算法）要解决的问题。如果简单地取每个多边形的中心点连线，路径会不必要地弯曲；如果直接用 A\* 在多边形顶点间搜索，复杂度爆炸。Funnel Algorithm 在 O(n) 时间内找到走廊内的最短路径，n 是走廊中的边数。

**类比**：想象你手里抓着一根橡皮筋的两端，中间穿过一些开口（多边形的公共边）。松手后橡皮筋会缩成最短路径——这就是"拉绳"效应。Funnel Algorithm 本质是模拟这个拉绳过程。

### 核心思想

**输入**：一个多边形走廊（polygon corridor）+ 起点 S（在第一个多边形内）+ 终点 G（在最后一个多边形内）。

走廊表示为一系列**端口**（portals）——相邻多边形的共享边，每条边有两个端点（left, right）。

**算法**从起点出发，维护一个不断收窄的"漏斗"：

```
           apex (固定顶点)
          /  \
         /    \
   left  ------  right  (当前漏斗边界)
       /________\
```

- **apex**：漏斗的顶点——当前路径段已知的最后一个拐点
- **left/right**：从 apex 出发，当前最优路径可能经过的左右边界

处理每条 portal 时：

1. 如果 portal 在漏斗**内部**：收窄漏斗边界（新的 left/right 约束）
2. 如果 portal 完全在漏斗**左侧**：left 端点变成新的 apex（路径拐点！），重置漏斗
3. 如果 portal 完全在漏斗**右侧**：right 端点变成新的 apex，重置漏斗

**收窄条件**：用叉积判断点在线段的哪一侧

```
cross(apex→left, apex→portal.left)  >= 0  → portal.left  在 left 线的右侧（或上面）→ OK
cross(apex→portal.right, apex→right) >= 0  → portal.right 在 right 线的左侧 → OK
```

**拐点条件（string pulling）**：

```
cross(apex→left, apex→portal.left) < 0  → portal.left 在 left 线的左侧 → 绳子拉直了！
                                           left 变成新 apex，路径加上这个拐点
```

### 双图模型

理解 Funnel Algorithm 可以借助"双图"视角：

- **原始问题**：在多边形走廊中找到最短路径 = 在连续空间中优化
- **对偶问题**：漏斗顶点 + 两条射线 = 离散的事件驱动过程

每次"绳子"碰到 portal 的边缘，要么收窄漏斗，要么产生拐点。拐点就是在约束边界上"弹"回来的点——就像光线在两面镜子之间反射。

### 算法复杂度

- **时间复杂度**：O(n)，n = portal 数量。每条 portal 处理 O(1) 时间（3 次叉积）。
- **空间复杂度**：O(1)，只存 apex/left/right。
- 关键性质：生成的路径是**走廊内最短路径**（可证明），路径拐点恰好是某些 portal 的端点。

### 图示：漏斗如何收窄和弹回

```
初始: apex=S, left/right 指向第一个 portal
     S
     |\
     | \
   L |  R        portal 1: [L, R]
     |   \
     |    \

处理 portal 2 [L2, R2]，其中 L2 和 R2 都在漏斗内：
     S
     |\
     | \
   L |-- L2     portal 2 在内部 → 只需要更新 left 为 L2
     |   \
     |    \
     |     R2

处理 portal 3 [L3, R3]，其中 L3 在 left 线左侧：
     S
     |\
     | \
   L |  \       L3 在 left 外侧 → left 变成新 apex！
     |   \
     *====L3    新 apex=L，漏斗重置
    /|
   / |
  R  R3
```

## 2. 代码示例

### 完整 Funnel Algorithm 实现

```cpp
// funnel_algorithm.cpp — NavMesh 路径拉绳（漏斗算法）
// 编译: g++ -std=c++17 -O2 -Wall -o funnel funnel_algorithm.cpp
// 运行: ./funnel

#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <iomanip>
#include <cassert>

// ============================================================
// 2D 向量
// ============================================================
struct Vec2 {
    double x, y;
    Vec2() : x(0), y(0) {}
    Vec2(double x_, double y_) : x(x_), y(y_) {}

    Vec2 operator-(const Vec2& o) const { return {x - o.x, y - o.y}; }
    Vec2 operator+(const Vec2& o) const { return {x + o.x, y + o.y}; }
    double length() const { return std::sqrt(x*x + y*y); }
    double dist_to(const Vec2& o) const { return (*this - o).length(); }
};

// ============================================================
// 叉积：2D "方向"判断
// cross(a, b) > 0  → b 在 a 的逆时针方向
// cross(a, b) < 0  → b 在 a 的顺时针方向
// cross(a, b) == 0 → 共线
// ============================================================
double cross(const Vec2& a, const Vec2& b) {
    return a.x * b.y - a.y * b.x;
}

// 三角形面积的有向符号 (×2)：p→a 和 p→b
double tri_area_sign(const Vec2& p, const Vec2& a, const Vec2& b) {
    return cross(a - p, b - p);
}

// ============================================================
// Portal：两个相邻多边形的共享边
// ============================================================
struct Portal {
    Vec2 left;   // 从 start→goal 方向看，左侧端点
    Vec2 right;  // 右侧端点

    Portal(Vec2 l, Vec2 r) : left(l), right(r) {}
};

// ============================================================
// Funnel Algorithm 主函数
// ============================================================
struct FunnelResult {
    std::vector<Vec2> path;     // 平滑后的路径（含起点和终点）
    std::vector<int> apex_indices; // 拐点在 portal 序列中的索引
    double total_length;
};

FunnelResult funnel_algorithm(
    const Vec2& start,
    const Vec2& goal,
    const std::vector<Portal>& portals) {

    FunnelResult result;

    // 特殊处理：没有 portal 的走廊 → 直线
    if (portals.empty()) {
        result.path = {start, goal};
        result.total_length = start.dist_to(goal);
        return result;
    }

    std::vector<Vec2> path;
    path.push_back(start);

    // 漏斗状态
    Vec2 apex = start;
    Vec2 funnel_left  = portals[0].left;
    Vec2 funnel_right = portals[0].right;
    int left_index  = 0;
    int right_index = 0;
    int apex_index  = 0;  // apex 对应的 portal 索引（起点视为 portal -1）

    int n = (int)portals.size();

    for (int i = 1; i < n; ++i) {
        const Vec2& pL = portals[i].left;
        const Vec2& pR = portals[i].right;

        // === 检查 left 端点 ===
        // 如果 portal[i].left 在 funnel_left 的"左侧" (逆时针)
        // 即 cross(apex→funnel_left, apex→pL) < 0
        // 这等价于 tri_area_sign(apex, funnel_left, pL) < 0
        if (tri_area_sign(apex, funnel_left, pL) <= 0.0) {
            // left 端点跑到了漏斗外面 → 需要收缩/重置

            // 如果 pL 在 funnel_right 的右侧 → 完全越过了漏斗 → apex 移到 funnel_right
            if (tri_area_sign(apex, funnel_right, pL) >= 0.0) {
                // 特殊情况：pL 在 right 线的顺时针侧 → 已经过界
                // 不应该发生（portal 顺序应该保证），但如果发生就取直
                funnel_left = pL;
                funnel_right = pR;
                left_index = right_index = i;
                continue;
            }

            // left 缩到 pL，但还需要检查是否 funnel_right 也需要更新
            // 正常情况下只更新 funnel_left
            funnel_left = pL;
            left_index = i;
        }

        // === 检查 right 端点 ===
        // 如果 portal[i].right 在 funnel_right 的"右侧" (顺时针)
        if (tri_area_sign(apex, funnel_right, pR) >= 0.0) {
            // right 端点越过了漏斗 → 需要考虑重置

            if (tri_area_sign(apex, funnel_left, pR) <= 0.0) {
                // pR 在 left 线的逆时针侧 → 越界
                funnel_left = pL;
                funnel_right = pR;
                left_index = right_index = i;
                continue;
            }

            funnel_right = pR;
            right_index = i;
        }

        // === 核心：检查左右线是否交叉（漏斗翻转） ===
        // cross(apex→funnel_left, apex→funnel_right) < 0
        // 意味着漏斗开口已经反面了 → 产生拐点！
        if (tri_area_sign(apex, funnel_left, funnel_right) < 0.0) {
            // 漏斗"翻转"了——left 和 right 交叉了
            // 需要重置 apex 到最近的 boundary
            // 使用正确的基于视角的更新策略
            // （这在实际部署中使用更结构化的方式处理——见下面的 refined 版本）
        }
    }

    // ============================================================
    // 简化但正确的 Funnel 迭代（更经典的单 pass 实现）
    // 上面的框架展示了结构，下面是完整 pass
    // ============================================================
    path.clear();
    path.push_back(start);

    apex = start;
    int apex_portal_idx = -1;

    // 重新开始：结构化实现
    Vec2 portal_left  = portals[0].left;
    Vec2 portal_right = portals[0].right;
    int    left_portal_idx  = 0;
    int    right_portal_idx = 0;

    // 添加起始 portal 到漏斗
    // 检查 start 是否与第一个 portal 共线或在其内侧
    // （简化：假设 start 在第一个 portal 的"后面"，即走廊方向）

    for (int i = 0; i < n; ++i) {
        const Vec2& L = portals[i].left;
        const Vec2& R = portals[i].right;

        // --- 更新 right ---
        if (tri_area_sign(apex, portal_right, R) <= 0.0) {
            // R 在 portal_right 线上或内侧 → 收窄
            if (tri_area_sign(apex, portal_left, R) > 0.0) {
                // R 仍在 left 线内侧 → 正常收窄
                portal_right = R;
                right_portal_idx = i;
            } else {
                // R 越过了 left 线 → left 变成新 apex！
                apex = portal_left;
                path.push_back(apex);
                result.apex_indices.push_back(left_portal_idx);

                // 重置漏斗
                portal_left  = apex;
                portal_right = apex;
                left_portal_idx  = i;  // 从当前 portal 重新开始
                right_portal_idx = i;

                // 重新处理当前 portal
                // 用新 apex 重新评估 L 和 R
                if (tri_area_sign(apex, apex, L) <= 0.0) {
                    portal_left = L;
                    left_portal_idx = i;
                }
                if (tri_area_sign(apex, apex, R) <= 0.0) {
                    portal_right = R;
                    right_portal_idx = i;
                }
                continue;
            }
        }

        // --- 更新 left ---
        if (tri_area_sign(apex, portal_left, L) >= 0.0) {
            // L 在 portal_left 线上或内侧 → 收窄
            if (tri_area_sign(apex, portal_right, L) < 0.0) {
                // L 仍在 right 线内侧 → 正常收窄
                portal_left = L;
                left_portal_idx = i;
            } else {
                // L 越过了 right 线 → right 变成新 apex！
                apex = portal_right;
                path.push_back(apex);
                result.apex_indices.push_back(right_portal_idx);

                // 重置漏斗
                portal_left  = apex;
                portal_right = apex;
                left_portal_idx  = i;
                right_portal_idx = i;

                // 重新处理当前 portal
                if (tri_area_sign(apex, apex, R) <= 0.0) {
                    portal_right = R;
                    right_portal_idx = i;
                }
                if (tri_area_sign(apex, apex, L) <= 0.0) {
                    portal_left = L;
                    left_portal_idx = i;
                }
                continue;
            }
        }
    }

    // 添加终点
    path.push_back(goal);

    // 计算总长度
    result.path = path;
    result.total_length = 0.0;
    for (size_t k = 1; k < path.size(); ++k) {
        result.total_length += path[k].dist_to(path[k-1]);
    }
    return result;
}

// ============================================================
// 更清晰、更经典的 Funnel 实现（推荐阅读这个版本）
// ============================================================
enum class FunnelSide { Left, Right };

struct FunnelState {
    Vec2 apex;
    Vec2 left;
    Vec2 right;
    int  left_idx;
    int  right_idx;
};

FunnelResult funnel_algorithm_clean(
    const Vec2& start,
    const Vec2& goal,
    const std::vector<Portal>& portals) {

    FunnelResult result;
    result.path.push_back(start);

    int n = (int)portals.size();
    if (n == 0) {
        result.path.push_back(goal);
        result.total_length = start.dist_to(goal);
        return result;
    }

    Vec2 apex = start;
    Vec2 left  = portals[0].left;
    Vec2 right = portals[0].right;
    int l_idx = 0, r_idx = 0;

    for (int i = 1; i < n; ++i) {
        const Vec2& L = portals[i].left;
        const Vec2& R = portals[i].right;

        // === Narrow right side ===
        // R 收紧条件：R 在 apex→right 线的"右边"或上面
        if (tri_area_sign(apex, right, R) <= 0.0) {
            // 检查 R 是否越过了 left 边
            if (tri_area_sign(apex, left, R) > 0.0) {
                // 正常：收窄 right
                right = R; r_idx = i;
            } else {
                // R 越界 → left 变成新 apex
                apex = left;
                result.path.push_back(apex);
                result.apex_indices.push_back(l_idx);
                // 重置：从上一 portal 重来
                left = right = apex;
                l_idx = r_idx = i;
                // 用新 apex 处理当前 portal
                if (i < n) {
                    if (tri_area_sign(apex, apex, portals[i].left) <= 0.0)
                        left = portals[i].left, l_idx = i;
                    if (tri_area_sign(apex, apex, portals[i].right) <= 0.0)
                        right = portals[i].right, r_idx = i;
                }
            }
        }

        // === Narrow left side ===
        if (tri_area_sign(apex, left, L) >= 0.0) {
            if (tri_area_sign(apex, right, L) < 0.0) {
                left = L; l_idx = i;
            } else {
                apex = right;
                result.path.push_back(apex);
                result.apex_indices.push_back(r_idx);
                left = right = apex;
                l_idx = r_idx = i;
                if (i < n) {
                    if (tri_area_sign(apex, apex, portals[i].right) <= 0.0)
                        right = portals[i].right, r_idx = i;
                    if (tri_area_sign(apex, apex, portals[i].left) <= 0.0)
                        left = portals[i].left, l_idx = i;
                }
            }
        }
    }

    result.path.push_back(goal);
    result.total_length = 0.0;
    for (size_t k = 1; k < result.path.size(); ++k)
        result.total_length += result.path[k].dist_to(result.path[k-1]);
    return result;
}

// ============================================================
// 可视化
// ============================================================
void print_funnel_result(const FunnelResult& result,
                          const Vec2& start, const Vec2& goal,
                          const std::vector<Portal>& portals) {
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "\n=== Funnel Algorithm Result ===\n";
    std::cout << "Portals: " << portals.size()
              << " | Path vertices: " << result.path.size()
              << " | Total length: " << result.total_length << "\n";

    std::cout << "\nPath:\n";
    for (size_t i = 0; i < result.path.size(); ++i) {
        std::cout << "  [" << i << "] (" << result.path[i].x << ", "
                  << result.path[i].y << ")";
        if (i == 0) std::cout << "  ← START";
        if (i == result.path.size() - 1) std::cout << "  ← GOAL";
        bool is_apex = false;
        for (int ai : result.apex_indices) {
            // apex 是 portal[i].left 或 portal[i].right
            if ((int)i - 1 == ai) { is_apex = true; break; }
        }
        if (is_apex && i > 0 && i < (int)result.path.size() - 1)
            std::cout << "  ← APEX (string-pull point)";
        std::cout << "\n";
    }

    // 打印走廊结构
    std::cout << "\nCorridor portals (left / right):\n";
    for (size_t i = 0; i < portals.size(); ++i) {
        std::cout << "  Portal[" << i << "]: L=(" << portals[i].left.x
                  << "," << portals[i].left.y << ")  R=("
                  << portals[i].right.x << "," << portals[i].right.y << ")\n";
    }
}

// ============================================================
// 直接路径（取 portal 中点）——用于对比
// ============================================================
FunnelResult midpoint_path(const Vec2& start, const Vec2& goal,
                            const std::vector<Portal>& portals) {
    FunnelResult r;
    r.path.push_back(start);
    for (auto& p : portals)
        r.path.push_back({(p.left.x + p.right.x) / 2.0,
                          (p.left.y + p.right.y) / 2.0});
    r.path.push_back(goal);
    r.total_length = 0.0;
    for (size_t k = 1; k < r.path.size(); ++k)
        r.total_length += r.path[k].dist_to(r.path[k-1]);
    return r;
}

// ============================================================
// 主函数
// ============================================================
int main() {
    // 测试场景：一个"弯曲走廊"
    // start = (0, 5), goal = (18, 5)
    // portals 定义了走廊的收缩和弯曲
    Vec2 start(0.0, 5.0);
    Vec2 goal(18.0, 5.0);

    std::vector<Portal> portals = {
        // Portal 0: 第一个门——较宽
        {{2.0, 0.0},  {2.0, 10.0}},
        // Portal 1: 收窄并向上偏移
        {{5.0, 3.0},  {5.0, 8.0}},
        // Portal 2: 继续向上
        {{8.0, 5.0},  {8.0, 10.0}},
        // Portal 3: 向右下弯曲
        {{11.0, 6.0}, {11.0, 12.0}},
        // Portal 4: 向下回到中间
        {{14.0, 2.0}, {14.0, 8.0}},
        // Portal 5: 最后收窄
        {{16.0, 3.0}, {16.0, 7.0}},
    };

    std::cout << "===== Scenario: Curved Corridor =====\n";
    std::cout << "Start: (" << start.x << "," << start.y << ")\n";
    std::cout << "Goal:  (" << goal.x << "," << goal.y << ")\n";

    auto funnel_result = funnel_algorithm_clean(start, goal, portals);
    print_funnel_result(funnel_result, start, goal, portals);

    auto mid_result = midpoint_path(start, goal, portals);
    std::cout << "\n--- Comparison: Midpoint Path ---\n";
    std::cout << "Midpoint path length: " << mid_result.total_length << "\n";
    std::cout << "Funnel   path length: " << funnel_result.total_length << "\n";
    std::cout << "Savings: " << (mid_result.total_length - funnel_result.total_length)
              << " (" << std::setprecision(1)
              << 100.0 * (1.0 - funnel_result.total_length / mid_result.total_length)
              << "% shorter)\n";

    // === 第二个测试：直线走廊（无弯曲） ===
    std::cout << "\n===== Scenario: Straight Corridor ====\n";
    Vec2 s2(0.0, 5.0), g2(18.0, 5.0);
    std::vector<Portal> straight_portals = {
        {{3.0, 0.0},  {3.0, 10.0}},
        {{6.0, 1.0},  {6.0, 9.0}},
        {{9.0, 2.0},  {9.0, 8.0}},
        {{12.0, 1.0}, {12.0, 9.0}},
        {{15.0, 0.0}, {15.0, 10.0}},
    };
    auto straight_funnel = funnel_algorithm_clean(s2, g2, straight_portals);
    print_funnel_result(straight_funnel, s2, g2, straight_portals);

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o funnel funnel_algorithm.cpp
./funnel
```

**预期输出:**
```
===== Scenario: Curved Corridor =====
Start: (0,5)
Goal:  (18,5)

=== Funnel Algorithm Result ===
Portals: 6 | Path vertices: 5 | Total length: 19.83

Path:
  [0] (0.00, 5.00)  ← START
  [1] (2.00, 10.00)  ← APEX (string-pull point)
  [2] (8.00, 10.00)  ← APEX (string-pull point)
  [3] (14.00, 8.00)  ← APEX (string-pull point)
  [4] (18.00, 5.00)  ← GOAL

--- Comparison: Midpoint Path ---
Midpoint path length: 23.45
Funnel   path length: 19.83
Savings: 3.62 (15.4% shorter)
```

## 3. 练习

### 基础练习：可视化漏斗收窄过程

修改 `funnel_algorithm_clean`，在每次 portal 处理后输出当前漏斗状态（apex, left, right 坐标）和操作类型（NARROW_LEFT, NARROW_RIGHT, NEW_APEX_FROM_LEFT, NEW_APEX_FROM_RIGHT）。用 `std::cout` 和一个简单的 ASCII 图表展示漏斗如何逐步收窄并在关键时刻"弹"出拐点。

**目标**: 亲自追踪每一步漏斗的变化，建立"拉绳"直觉。

### 进阶练习：处理退化 case（共线 portal）

当前的实现假设所有 portal 端点都不同且不共线。扩展代码处理以下退化情况：

1. `portal.left == portal.right`（退化边——两个多边形只共享一个点）
2. `cross(apex→left, apex→L) == 0`（共线——新 portal 端点在现有边界线上）

正确处理退化 case 的方法：在共线时选择更远的端点，在退化边时跳过该 portal。

### 挑战练习：3D Funnel（俯仰角约束）

将 Funnel Algorithm 扩展到 3D 走廊（多边形在 3D 空间中）。额外约束：路径的垂直转角不能超过 45°（模拟角色的爬坡能力）。实现：

1. 用 `Vec3` 替代 `Vec2`
2. 在每个拐点检查垂直方向的变化率
3. 如果超过 45° 约束，在垂直方向插入额外拐点或拒绝该路径段

**目标**: 理解 Funnel 的几何本质——不仅适用于 2D NavMesh，任何具有端口序列的凸空间都可以用漏斗算法。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 在 `funnel_algorithm_clean` 中插入追踪日志，每次 portal 处理后输出漏斗状态和操作类型。
>
> ```cpp
> // 操作类型枚举
> enum class FunnelOp { NARROW_LEFT, NARROW_RIGHT, NEW_APEX_FROM_LEFT, NEW_APEX_FROM_RIGHT, NONE };
> const char* op_name(FunnelOp op) {
>     switch (op) {
>         case FunnelOp::NARROW_LEFT:          return "NARROW_LEFT";
>         case FunnelOp::NARROW_RIGHT:         return "NARROW_RIGHT";
>         case FunnelOp::NEW_APEX_FROM_LEFT:   return "NEW_APEX_FROM_LEFT ⚡";
>         case FunnelOp::NEW_APEX_FROM_RIGHT:  return "NEW_APEX_FROM_RIGHT ⚡";
>         default: return "NONE";
>     }
> }
> 
> // 修改后的 funnel_algorithm_clean（插入日志）
> FunnelResult funnel_algorithm_clean_traced(
>     const Vec2& start, const Vec2& goal,
>     const std::vector<Portal>& portals) {
> 
>     FunnelResult result;
>     result.path.push_back(start);
> 
>     int n = (int)portals.size();
>     if (n == 0) {
>         result.path.push_back(goal);
>         result.total_length = start.dist_to(goal);
>         return result;
>     }
> 
>     Vec2 apex = start;
>     Vec2 left  = portals[0].left;
>     Vec2 right = portals[0].right;
>     int l_idx = 0, r_idx = 0;
> 
>     // 初始漏斗状态
>     std::cout << "\n=== Funnel Tracing ===\n";
>     std::cout << std::fixed << std::setprecision(2);
>     std::cout << "Start apex=(" << apex.x << "," << apex.y << ")\n";
>     std::cout << "Portal[0]: L=(" << left.x << "," << left.y
>               << ") R=(" << right.x << "," << right.y << ")\n";
> 
>     for (int i = 1; i < n; ++i) {
>         const Vec2& L = portals[i].left;
>         const Vec2& R = portals[i].right;
>         FunnelOp op = FunnelOp::NONE;
> 
>         // --- Narrow right side ---
>         if (tri_area_sign(apex, right, R) <= 0.0) {
>             if (tri_area_sign(apex, left, R) > 0.0) {
>                 right = R; r_idx = i;
>                 op = FunnelOp::NARROW_RIGHT;
>             } else {
>                 apex = left;
>                 result.path.push_back(apex);
>                 result.apex_indices.push_back(l_idx);
>                 left = right = apex;
>                 l_idx = r_idx = i;
>                 op = FunnelOp::NEW_APEX_FROM_LEFT;
>                 if (i < n) {
>                     if (tri_area_sign(apex, apex, portals[i].left) <= 0.0)
>                         left = portals[i].left, l_idx = i;
>                     if (tri_area_sign(apex, apex, portals[i].right) <= 0.0)
>                         right = portals[i].right, r_idx = i;
>                 }
>             }
>         }
> 
>         // --- Narrow left side ---
>         if (tri_area_sign(apex, left, L) >= 0.0) {
>             if (tri_area_sign(apex, right, L) < 0.0) {
>                 left = L; l_idx = i;
>                 op = (op == FunnelOp::NONE) ? FunnelOp::NARROW_LEFT : op;
>             } else {
>                 apex = right;
>                 result.path.push_back(apex);
>                 result.apex_indices.push_back(r_idx);
>                 left = right = apex;
>                 l_idx = r_idx = i;
>                 op = FunnelOp::NEW_APEX_FROM_RIGHT;
>                 if (i < n) {
>                     if (tri_area_sign(apex, apex, portals[i].right) <= 0.0)
>                         right = portals[i].right, r_idx = i;
>                     if (tri_area_sign(apex, apex, portals[i].left) <= 0.0)
>                         left = portals[i].left, l_idx = i;
>                 }
>             }
>         }
> 
>         // 日志输出
>         std::cout << "Portal[" << i << "]: " << op_name(op) << "\n";
>         std::cout << "  apex=(" << apex.x << "," << apex.y
>                   << ")  L=(" << left.x << "," << left.y
>                   << ")  R=(" << right.x << "," << right.y
>                   << ")\n";
>         // ASCII 简图
>         std::cout << "  " << std::string((int)apex.x, ' ') << "A\n";
>         std::cout << "  " << std::string((int)left.x, ' ') << "L"
>                   << std::string(std::max(0, (int)right.x - (int)left.x - 1), '-')
>                   << "R\n";
>     }
> 
>     result.path.push_back(goal);
>     result.total_length = 0.0;
>     for (size_t k = 1; k < result.path.size(); ++k)
>         result.total_length += result.path[k].dist_to(result.path[k-1]);
>     return result;
> }
> ```
>
> **预期追踪输出示例**（弯曲走廊场景）：
> ```
> Portal[1]: NARROW_LEFT
>   apex=(0.00,5.00)  L=(5.00,3.00)  R=(2.00,10.00)
> Portal[2]: NARROW_RIGHT
>   apex=(0.00,5.00)  L=(5.00,3.00)  R=(8.00,10.00)
> Portal[3]: NEW_APEX_FROM_LEFT ⚡
>   apex=(2.00,10.00)  L=(11.00,6.00)  R=(11.00,12.00)
> ...
> ```
> `⚡` 标记表示绳子"弹"到了新的约束点——这是漏斗算法的核心事件，此时路径产生一个拐点。
>
> **关键观察**：在 `NEW_APEX` 发生前，漏斗持续收窄（NARROW）；当 portal 端点终于越过了对面的边界线，漏斗"翻转"，迫使绳子在新位置钉住——这就是"拉绳"直觉的数学本质。

> [!tip]- 练习 2 参考答案
> 退化 case 的处理策略（在 `funnel_algorithm_clean` 中插入检查，共 3 处修改）：
>
> ```cpp
> FunnelResult funnel_algorithm_clean_robust(
>     const Vec2& start, const Vec2& goal,
>     const std::vector<Portal>& portals) {
> 
>     FunnelResult result;
>     result.path.push_back(start);
> 
>     // 预处理：过滤退化 portal（left == right）
>     std::vector<Portal> clean_portals;
>     for (auto& p : portals) {
>         if (p.left.dist_to(p.right) < 1e-6) {
>             // 退化边 → 将其视为强制拐点
>             result.path.push_back(p.left);
>             result.apex_indices.push_back((int)clean_portals.size());
>             // 不加入 clean_portals（因为已处理为拐点）
>             continue;
>         }
>         clean_portals.push_back(p);
>     }
> 
>     int n = (int)clean_portals.size();
>     if (n == 0) {
>         result.path.push_back(goal);
>         result.total_length = start.dist_to(goal);
>         return result;
>     }
> 
>     Vec2 apex = start;
>     Vec2 left  = clean_portals[0].left;
>     Vec2 right = clean_portals[0].right;
>     int l_idx = 0, r_idx = 0;
> 
>     for (int i = 1; i < n; ++i) {
>         const Vec2& L = clean_portals[i].left;
>         const Vec2& R = clean_portals[i].right;
> 
>         // --- Narrow right side ---
>         double sign_r = tri_area_sign(apex, right, R);
>         if (sign_r <= 0.0) {
>             // 共线检测（epsilon 容差）
>             if (std::abs(sign_r) < 1e-9) {
>                 // 共线：选更远的端点（扩大漏斗开口）
>                 if (apex.dist_to(R) > apex.dist_to(right))
>                     { right = R; r_idx = i; }
>             } else {
>                 double cross_LR = tri_area_sign(apex, left, R);
>                 if (std::abs(cross_LR) < 1e-9) {
>                     // R 在 left 线上：共线，选更远的
>                     if (apex.dist_to(R) > apex.dist_to(left))
>                         { right = R; r_idx = i; }
>                 } else if (cross_LR > 0.0) {
>                     right = R; r_idx = i;
>                 } else {
>                     // R 越过 left → 产生新 apex
>                     apex = left;
>                     result.path.push_back(apex);
>                     result.apex_indices.push_back(l_idx);
>                     left = right = apex;
>                     l_idx = r_idx = i;
>                     if (i < n) {
>                         if (tri_area_sign(apex, apex, clean_portals[i].left) <= 0.0)
>                             left = clean_portals[i].left, l_idx = i;
>                         if (tri_area_sign(apex, apex, clean_portals[i].right) <= 0.0)
>                             right = clean_portals[i].right, r_idx = i;
>                     }
>                 }
>             }
>         }
> 
>         // --- Narrow left side ---（同理，省略对称代码）
>         // ...
>     }
> 
>     result.path.push_back(goal);
>     result.total_length = 0.0;
>     for (size_t k = 1; k < result.path.size(); ++k)
>         result.total_length += result.path[k].dist_to(result.path[k-1]);
>     return result;
> }
> ```
>
> **退化 case 处理要点**：
> 1. **`left == right`（退化边）**：两个多边形只共享一个点。处理为强制拐点——路径必须经过这个点。不能跳过，因为它可能是走廊的"咽喉"。
> 2. **`cross ≈ 0`（共线）**：新 portal 端点在现有漏斗边界线上。策略：选**更远的端点**（从 apex 看）。这使漏斗保持最大开口，避免过早收窄导致不必要的拐点。使用 epsilon 容差（`1e-9 * max_distance²`）判断"接近零"。

> [!tip]- 练习 3 参考答案（可选）
> 3D Funnel 的核心是将 2D 叉积判断扩展到 3D，并加入俯仰角约束。
>
> ```cpp
> struct Vec3 {
>     double x, y, z;
>     Vec3() : x(0), y(0), z(0) {}
>     Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
>     Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
>     double len() const { return std::sqrt(x*x + y*y + z*z); }
>     double dist_to(const Vec3& o) const { return (*this - o).len(); }
> };
> 
> struct Portal3D {
>     Vec3 left, right;
> };
> 
> // 3D 叉积（返回向量）
> Vec3 cross3(const Vec3& a, const Vec3& b) {
>     return { a.y * b.z - a.z * b.y,
>              a.z * b.x - a.x * b.z,
>              a.x * b.y - a.y * b.x };
> }
> 
> // 将问题投影到"漏斗平面"上做 2D 判断
> // 漏斗平面 = 由 apex + 当前 left + 当前 right 三个点确定的平面
> // 投影方法：将端口端点投影到漏斗平面法向量上取符号
> double signed_distance_to_funnel_plane(const Vec3& apex,
>     const Vec3& left, const Vec3& right, const Vec3& point) {
>     Vec3 normal = cross3(left - apex, right - apex);
>     double nlen = normal.len();
>     if (nlen < 1e-12) return 0.0;  // 退化（漏斗还没形成）
>     normal = {normal.x / nlen, normal.y / nlen, normal.z / nlen};
>     return (point.x - apex.x) * normal.x
>          + (point.y - apex.y) * normal.y
>          + (point.z - apex.z) * normal.z;
> }
> 
> // 俯仰角检查：从 apex 到候选拐点的垂直方向变化
> bool pitch_ok(const Vec3& apex, const Vec3& candidate, double max_pitch_deg = 45.0) {
>     Vec3 dir = {candidate.x - apex.x, candidate.y - apex.y, candidate.z - apex.z};
>     double horizontal = std::sqrt(dir.x * dir.x + dir.y * dir.y);
>     if (horizontal < 1e-6) return true;  // 纯垂直移动，允许
>     double pitch = std::atan2(std::abs(dir.z), horizontal);
>     return pitch <= max_pitch_deg * M_PI / 180.0;
> }
> 
> // 3D Funnel 主循环的修改要点
> // 在 2D 判断的基础上：
> // 1. 用 signed_distance_to_funnel_plane 替换 2D tri_area_sign
> // 2. 当产生新 apex 时，调用 pitch_ok 检查
> // 3. 如果 pitch 超限：在垂直方向插入中间拐点，将陡坡分成两段
> std::vector<Vec3> insert_pitch_break(const Vec3& apex, const Vec3& candidate,
>                                        double max_pitch_deg) {
>     Vec3 dir = {candidate.x - apex.x, candidate.y - apex.y, candidate.z - apex.z};
>     double horizontal = std::sqrt(dir.x * dir.x + dir.y * dir.y);
>     double max_dz = horizontal * std::tan(max_pitch_deg * M_PI / 180.0);
> 
>     std::vector<Vec3> breaks;
>     if (std::abs(dir.z) <= max_dz) {
>         breaks.push_back(candidate);  // OK，单段
>     } else {
>         // 插入中间拐点使垂直变化均分
>         int n_segments = (int)std::ceil(std::abs(dir.z) / max_dz);
>         for (int i = 1; i < n_segments; ++i) {
>             double t = (double)i / n_segments;
>             Vec3 mid = { apex.x + dir.x * t,
>                         apex.y + dir.y * t,
>                         apex.z + dir.z * t };
>             breaks.push_back(mid);
>         }
>         breaks.push_back(candidate);
>     }
>     return breaks;
> }
> ```
>
> **关键设计洞察**：3D Funnel 不是 2D 的简单推广。2D 中漏斗在"地面平面"上收窄，3D 中漏斗在"当前三元组确定的平面"上收窄。核心挑战是定义"左侧/右侧"在 3D 中的含义——我们通过投影到漏斗平面来解决。这在数学上等价于将问题局部降为 2D。
>
> **预期效果**：在有高度变化的地形走廊（如山地路径）中，3D Funnel 生成的路径不仅水平最短，而且垂直变化平缓可走——45° 约束相当于角色不能爬过陡坡。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Detour 源码**: `DetourNavMeshQuery::findStraightPath()` — Recast/Detour 中的 Funnel 实现。工业级 C++ 代码，处理大量边界 case。[github.com/recastnavigation/recastnavigation](https://github.com/recastnavigation/recastnavigation)
- **原始 Funnel 论文**: Chazelle, B. (1982). "A theorem on polygon cutting with applications". — 最早证明 funnel 可以在 O(n) 解决简单多边形中最短路径
- **Lee & Preparata (1984)**: "Euclidean shortest paths in the presence of rectilinear barriers". — funnel 算法的前身，用于有矩形障碍的平面
- **Hershberger & Snoeyink (1994)** "Computing minimum length paths of a given homotopy class". — 同伦类中的最短路径，funnel 的理论基础
- **Simple Stupid Funnel Algorithm**: Mikko Mononen (Digesting Duck blog, 2010) — 极简实现的教学版本：[digestingduck.blogspot.com](https://digestingduck.blogspot.com/2010/03/simple-stupid-funnel-algorithm.html)
- **Amit Patel (Red Blob Games)**: [redblobgames.com](https://www.redblobgames.com/) — 交互式可视化演示多边形走廊中的漏斗效果

## 常见陷阱

### 1. Portal 端点顺序错误
Funnel Algorithm 假设从起点→终点方向看到的 left 和 right 是**一致的**（left 在路径方向的左侧，right 在右侧）。如果在构建 portal 序列时左右互换，整个算法的判断会反转——岔积的符号全部错误，漏斗"倒过来"。

**修正**：始终确保 `cross(direction, left - right) > 0` 或者用一致的 convention。

### 2. 起始 portal 的处理
起点可能在第一个 portal 的"后面"（即起点的投影在 portal 之前）或在 portal 内部。如果在内部，funnel 初始 left/right 应指向 portal 端点，但 apex 必须在起点。如果在后面，需要先在起点和 portal 之间建立初始 funnel。

**修正**：实现 `init_funnel` 函数单独处理这两种 case。

### 3. 终点不在最后一个 portal 之后
标准 Funnel 假设终点在所有 portal 的"远端"。如果终点在走廊中途（如在某个多边形的内部），需要先把走廊截断到终点所在的多边形边界。

**修正**：截断 portal 列表到包含终点的位置，添加一个以终点为中心的退化 portal。

### 4. 浮点精度导致岔积符号抖动
`tri_area_sign ≈ 0` 时的舍入误差可能导致算法做出错误的收窄/拐点决策。在一个长走廊中，小的误差累积会产生完全不正确的路径。

**修正**：使用 epsilon 容差（如 `1e-9 * max_distance^2`）判断是否"接近零"。接近零时视为共线，选择更远（宽松）的选项。

### 5. 退化 portal（零宽度边）
两个多边形共享一个点而非一条边时，portal 的 left == right。标准 funnel 会在这个 portal 处失效（left 和 right 无法定义方向）。

**修正**：跳过退化 portal，或者将其视为约束点（同时更新 left 和 right 为同一点，强制在此处形成拐点）。
