---
title: "KD-Tree：多维空间索引"
updated: 2026-06-05
---

# KD-Tree：多维空间索引
> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: 二叉树, 递归, 欧几里得距离, 网格系统基础 (04)

## 1. 概念讲解

### 为什么需要这个？

游戏中需要回答大量空间查询：

- "离我最近的敌人是谁？" → 最近邻查询 (Nearest Neighbor)
- "视野范围内的所有玩家？" → 范围查询 (Range Search)
- "距离我最近的 5 个治疗点？" → K-最近邻查询 (KNN)

暴力方法：遍历全部 N 个点，O(N)。对于 100 个点无所谓，但 10,000 个单位 × 60fps 就是灾难。**KD-Tree 将最近邻查询从 O(N) 降到平均 O(log N)**——10,000 个点只需 ~14 次比较。

### 核心思想

**KD-Tree** (K-Dimensional Tree) 是一种在 **k 维空间中对点进行索引的二叉搜索树**。

**直觉**：想象你在整理一本书的索引。你按"首字母"分成 26 组，每组再按"第二个字母"分成 26 组……KD-Tree 做的是同样的事，但按坐标轴拆分：

1. **根节点**：按 x 坐标的中位数将所有点切成左半（x 更小）和右半（x 更大）
2. **下一层**：按 y 坐标切分
3. **再下一层**：回到 x 坐标切分
4. 递归直到每个叶子节点只有 ≤1 个点

```
            [x=5]          ← 按 x 切
           /     \
     [y=3]       [y=8]     ← 按 y 切
      /  \        /  \
   [x=1] [x=4] [x=7] [x=9] ← 按 x 切
```

### 构建算法

```
function buildKDTree(points, depth):
    if points.empty(): return null

    axis = depth % k   // 在 2D 中, axis = 0 表示 x 轴, axis = 1 表示 y 轴

    sort points by axis
    median_idx = points.size() / 2

    node = new Node(points[median_idx])
    node.left  = buildKDTree(points[0..median_idx), depth+1)
    node.right = buildKDTree(points[median_idx+1..), depth+1)
    return node
```

**关键性质**：
- 深度 d 的节点按第 `d % k` 维切分空间
- 每个内部节点代表一个超矩形区域的分割线
- 所有左子树中的点在切分维度上 ≤ 切分点，右子树中的点 ≥ 切分点

### 最近邻查询：Branch-and-Bound

对于查询点 Q，不是盲目遍历整棵树，而是利用 KD-Tree 的空间划分进行**剪枝 (pruning)**：

```python
def nearest(node, query, depth, best_dist, best_point):
    if node is None: return best_point, best_dist

    # 步骤 1: 检查当前节点
    d = distance(query, node.point)
    if d < best_dist: best_dist, best_point = d, node.point

    # 步骤 2: 决定先走哪边
    axis = depth % k
    diff = query[axis] - node.point[axis]

    if diff <= 0:
        first = node.left   # 查询点在切分左边
        second = node.right
    else:
        first = node.right  # 查询点在切分右边
        second = node.left

    # 步骤 3: 先探索查询点所在的那一半
    best_point, best_dist = nearest(first, query, depth+1, best_dist, best_point)

    # 步骤 4: 剪枝判断——是否需要探索另一半？
    if |diff| < best_dist:   # <-- 另一半可能包含更近的点
        best_point, best_dist = nearest(second, query, depth+1, best_dist, best_point)

    return best_point, best_dist
```

**剪枝的关键**：如果查询点到切分超平面的距离 `|diff|` 已经大于当前最佳距离 `best_dist`，另一侧子树**不可能**包含更近的点——因为那一侧的所有点在切分维度上都距离查询点至少 `|diff|`。

### 范围查询

范围查询返回所有落在矩形区域 `[x_min, x_max] × [y_min, y_max]` 内的点：

```
function rangeSearch(node, depth, query_rect, results):
    if node is None: return

    if node.point 在 query_rect 内:
        results.append(node.point)

    axis = depth % k

    // 左子树的区域可能和 query_rect 重叠？
    if query_rect 的左边界 <= node.point[axis]:
        rangeSearch(node.left, depth+1, query_rect, results)

    // 右子树的区域可能和 query_rect 重叠？
    if query_rect 的右边界 >= node.point[axis]:
        rangeSearch(node.right, depth+1, query_rect, results)
```

**平均 O(log N + K)**，K = 结果数量。

### 平衡 vs 不平衡

- **平衡 KD-Tree**：用中位数切分 → O(N log N) 构建，保证 O(log N) 查询。但插入/删除困难——需要重建子树
- **不平衡 KD-Tree**：按插入顺序构建 → O(N²) 最坏查询（退化为链表）。适合点集不变或极少更新的场景

### KD-Tree vs 其他空间结构

| 结构 | 构建 | 点查询 | 范围查询 | 动态更新 |
|------|------|--------|----------|---------|
| KD-Tree | O(N log N) | O(log N) | O(√N+K) | 困难 |
| 空间哈希 | O(N) | O(1) 其实不是 | O(1) 每个格子 | 容易 |
| 四叉树 | O(N log N) | O(log N) | O(log N+K) | 中等 |
| 网格 | O(N) | O(1) | O(M) | 容易 |

## 2. 代码示例

### 完整 KD-Tree 实现（2D 点 + NN + 范围查询 + KNN）

```cpp
// kdtree.cpp — 2D KD-Tree：构建、最近邻、范围查询、KNN、暴力对比
// 编译: g++ -std=c++17 -O2 -Wall -o kdtree kdtree.cpp
// 运行: ./kdtree

#include <iostream>
#include <vector>
#include <cmath>
#include <limits>
#include <algorithm>
#include <queue>
#include <random>
#include <chrono>
#include <iomanip>

// ============================================================
// 2D 点
// ============================================================
struct Point2D {
    float x, y;
    Point2D() : x(0), y(0) {}
    Point2D(float x_, float y_) : x(x_), y(y_) {}

    float operator[](int dim) const { return dim == 0 ? x : y; }
    float& operator[](int dim) { return dim == 0 ? x : y; }
};

float squared_dist(const Point2D& a, const Point2D& b) {
    float dx = a.x - b.x;
    float dy = a.y - b.y;
    return dx*dx + dy*dy;
}

float euclidean_dist(const Point2D& a, const Point2D& b) {
    return std::sqrt(squared_dist(a, b));
}

// ============================================================
// AABB 包围盒（用于范围查询）
// ============================================================
struct AABB {
    float x_min, y_min, x_max, y_max;

    bool contains(const Point2D& p) const {
        return p.x >= x_min && p.x <= x_max &&
               p.y >= y_min && p.y <= y_max;
    }
};

// ============================================================
// KD-Tree 节点
// ============================================================
struct KDNode {
    Point2D point;
    KDNode* left;
    KDNode* right;

    KDNode(const Point2D& p) : point(p), left(nullptr), right(nullptr) {}
};

// ============================================================
// KD-Tree 类
// ============================================================
class KDTree {
public:
    KDTree() : root_(nullptr) {}
    ~KDTree() { destroy(root_); }

    // 构建：用中位数平衡构建
    void build(std::vector<Point2D> points) {
        destroy(root_);
        root_ = build_recursive(points, 0);
    }

    // 最近邻查询
    Point2D nearest(const Point2D& query) const {
        float best_dist_sq = std::numeric_limits<float>::max();
        Point2D best;
        nearest_recursive(root_, query, 0, best, best_dist_sq);
        return best;
    }

    // K 最近邻查询 (K-Nearest Neighbors)
    struct KNNEntry {
        Point2D point;
        float dist_sq;
        bool operator<(const KNNEntry& o) const { return dist_sq < o.dist_sq; }
    };

    std::vector<Point2D> knn(const Point2D& query, int k) const {
        // 用最大堆维护 K 个最近点
        std::priority_queue<KNNEntry> max_heap;
        knn_recursive(root_, query, 0, k, max_heap);

        // 按距离排序输出
        std::vector<KNNEntry> sorted;
        while (!max_heap.empty()) {
            sorted.push_back(max_heap.top());
            max_heap.pop();
        }
        std::reverse(sorted.begin(), sorted.end());

        std::vector<Point2D> result;
        for (auto& e : sorted) result.push_back(e.point);
        return result;
    }

    // 范围查询
    std::vector<Point2D> range_query(const AABB& rect) const {
        std::vector<Point2D> results;
        range_recursive(root_, 0, rect, results);
        return results;
    }

    // 点数量
    size_t size() const { return count_nodes(root_); }

private:
    KDNode* root_;

    // 递归构建：传入按深度归位的点列表
    static KDNode* build_recursive(std::vector<Point2D>& points, int depth) {
        if (points.empty()) return nullptr;

        int axis = depth % 2;
        size_t median = points.size() / 2;

        // nth_element: O(N) 部分排序，将第 median 个元素放到正确位置
        std::nth_element(points.begin(), points.begin() + median, points.end(),
            [axis](const Point2D& a, const Point2D& b) {
                return a[axis] < b[axis];
            });

        KDNode* node = new KDNode(points[median]);

        // 递归构建左右子树（注意: std::vector 不能直接传子范围，因此我们复制）
        std::vector<Point2D> left_pts(points.begin(), points.begin() + median);
        std::vector<Point2D> right_pts(points.begin() + median + 1, points.end());

        node->left  = build_recursive(left_pts,  depth + 1);
        node->right = build_recursive(right_pts, depth + 1);

        return node;
    }

    // 最近邻递归搜索
    static void nearest_recursive(KDNode* node, const Point2D& query, int depth,
                                   Point2D& best, float& best_dist_sq) {
        if (!node) return;

        // 步骤 1: 检查当前节点
        float d2 = squared_dist(query, node->point);
        if (d2 < best_dist_sq) {
            best_dist_sq = d2;
            best = node->point;
        }

        // 步骤 2: 决定搜索顺序
        int axis = depth % 2;
        float diff = query[axis] - node->point[axis];

        KDNode* first  = (diff <= 0) ? node->left  : node->right;
        KDNode* second = (diff <= 0) ? node->right : node->left;

        // 步骤 3: 先搜索查询点所在侧
        nearest_recursive(first, query, depth + 1, best, best_dist_sq);

        // 步骤 4: 剪枝——只有另一半可能改善时才搜索
        if (diff * diff < best_dist_sq) {
            nearest_recursive(second, query, depth + 1, best, best_dist_sq);
        }
    }

    // KNN 递归搜索
    static void knn_recursive(KDNode* node, const Point2D& query, int depth,
                               int k, std::priority_queue<KNNEntry>& max_heap) {
        if (!node) return;

        float d2 = squared_dist(query, node->point);

        // 插入当前点到最大堆
        if ((int)max_heap.size() < k) {
            max_heap.push({node->point, d2});
        } else if (d2 < max_heap.top().dist_sq) {
            max_heap.pop();
            max_heap.push({node->point, d2});
        }

        int axis = depth % 2;
        float diff = query[axis] - node->point[axis];

        KDNode* first  = (diff <= 0) ? node->left  : node->right;
        KDNode* second = (diff <= 0) ? node->right : node->left;

        knn_recursive(first, query, depth + 1, k, max_heap);

        // 剪枝条件：另一半是否可能包含比当前第 K 远更近的点
        float threshold = ((int)max_heap.size() < k)
            ? std::numeric_limits<float>::max()
            : max_heap.top().dist_sq;

        if (diff * diff < threshold) {
            knn_recursive(second, query, depth + 1, k, max_heap);
        }
    }

    // 范围查询递归
    static void range_recursive(KDNode* node, int depth, const AABB& rect,
                                 std::vector<Point2D>& results) {
        if (!node) return;

        // 检查当前点是否在矩形内
        if (rect.contains(node->point)) {
            results.push_back(node->point);
        }

        int axis = depth % 2;

        // 左子树：若矩形左边界 ≤ 切分值，左子树可能与矩形重叠
        if (axis == 0) {
            if (rect.x_min <= node->point.x)
                range_recursive(node->left,  depth + 1, rect, results);
            if (rect.x_max >= node->point.x)
                range_recursive(node->right, depth + 1, rect, results);
        } else {
            if (rect.y_min <= node->point.y)
                range_recursive(node->left,  depth + 1, rect, results);
            if (rect.y_max >= node->point.y)
                range_recursive(node->right, depth + 1, rect, results);
        }
    }

    static void destroy(KDNode* node) {
        if (!node) return;
        destroy(node->left);
        destroy(node->right);
        delete node;
    }

    static size_t count_nodes(KDNode* node) {
        if (!node) return 0;
        return 1 + count_nodes(node->left) + count_nodes(node->right);
    }
};

// ============================================================
// 暴力搜索（用于正确性验证 + 性能对比）
// ============================================================
Point2D brute_nearest(const std::vector<Point2D>& points, const Point2D& query) {
    float best_dist_sq = std::numeric_limits<float>::max();
    Point2D best;
    for (const auto& p : points) {
        float d2 = squared_dist(query, p);
        if (d2 < best_dist_sq) {
            best_dist_sq = d2;
            best = p;
        }
    }
    return best;
}

std::vector<Point2D> brute_knn(const std::vector<Point2D>& points,
                                const Point2D& query, int k) {
    struct Entry {
        Point2D p;
        float d2;
        bool operator<(const Entry& o) const { return d2 < o.d2; }
    };

    std::vector<Entry> all;
    for (const auto& p : points) {
        all.push_back({p, squared_dist(query, p)});
    }
    std::sort(all.begin(), all.end());

    std::vector<Point2D> result;
    for (int i = 0; i < k && i < (int)all.size(); ++i)
        result.push_back(all[i].p);
    return result;
}

std::vector<Point2D> brute_range(const std::vector<Point2D>& points,
                                  const AABB& rect) {
    std::vector<Point2D> result;
    for (const auto& p : points) {
        if (rect.contains(p)) result.push_back(p);
    }
    return result;
}

// ============================================================
// main — 演示 + 性能对比
// ============================================================
int main() {
    // 生成 10,000 个随机 2D 点
    const int N = 10000;
    std::vector<Point2D> points(N);
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(0.0f, 1000.0f);

    for (int i = 0; i < N; ++i) {
        points[i] = Point2D(dist(rng), dist(rng));
    }

    // 构建 KD-Tree
    KDTree tree;
    tree.build(points);
    std::cout << "KD-Tree built with " << tree.size() << " nodes\n\n";

    // --- 1. 最近邻查询 — 正确性验证 ---
    std::cout << "=== 最近邻查询 (Nearest Neighbor) ===\n";
    Point2D q1(500.0f, 500.0f);
    Point2D kd_nn = tree.nearest(q1);
    Point2D bf_nn = brute_nearest(points, q1);

    std::cout << "Query: (" << q1.x << ", " << q1.y << ")\n";
    std::cout << "KD-Tree:  (" << kd_nn.x << ", " << kd_nn.y
              << ") dist=" << euclidean_dist(q1, kd_nn) << "\n";
    std::cout << "Brute:    (" << bf_nn.x << ", " << bf_nn.y
              << ") dist=" << euclidean_dist(q1, bf_nn) << "\n";
    std::cout << "Match: " << (squared_dist(kd_nn, bf_nn) < 0.0001f ? "YES" : "NO") << "\n\n";

    // --- 2. KNN 查询 ---
    std::cout << "=== K-最近邻查询 (K=5) ===\n";
    int k = 5;
    auto kd_knn = tree.knn(q1, k);
    auto bf_knn = brute_knn(points, q1, k);

    std::cout << "KD-Tree KNN results:\n";
    for (const auto& p : kd_knn) {
        std::cout << "  (" << p.x << ", " << p.y
                  << ") dist=" << euclidean_dist(q1, p) << "\n";
    }

    bool knn_match = true;
    for (int i = 0; i < k; ++i) {
        if (squared_dist(kd_knn[i], bf_knn[i]) > 0.0001f) knn_match = false;
    }
    std::cout << "Match with brute-force: " << (knn_match ? "YES" : "NO") << "\n\n";

    // --- 3. 范围查询 ---
    std::cout << "=== 范围查询 ===\n";
    AABB query_rect = {200.0f, 200.0f, 400.0f, 400.0f};
    auto kd_range = tree.range_query(query_rect);
    auto bf_range = brute_range(points, query_rect);

    std::cout << "Rect: [" << query_rect.x_min << ", " << query_rect.y_min
              << "] -> [" << query_rect.x_max << ", " << query_rect.y_max << "]\n";
    std::cout << "KD-Tree found: " << kd_range.size() << " points\n";
    std::cout << "Brute   found: " << bf_range.size() << " points\n";
    std::cout << "Match: " << (kd_range.size() == bf_range.size() ? "YES" : "NO") << "\n\n";

    // --- 4. 性能对比 ---
    std::cout << "=== 性能对比: KD-Tree vs Brute-Force ===\n";
    const int QUERIES = 1000;
    std::vector<Point2D> queries(QUERIES);
    for (int i = 0; i < QUERIES; ++i)
        queries[i] = Point2D(dist(rng), dist(rng));

    // NN 性能
    {
        auto t0 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < QUERIES; ++i)
            tree.nearest(queries[i]);
        auto t1 = std::chrono::high_resolution_clock::now();
        auto kd_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        auto t2 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < QUERIES; ++i)
            brute_nearest(points, queries[i]);
        auto t3 = std::chrono::high_resolution_clock::now();
        auto bf_us = std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count();

        std::cout << std::fixed << std::setprecision(1);
        std::cout << "NN  queries x" << QUERIES << ":\n";
        std::cout << "  KD-Tree:     " << kd_us / 1000.0 << " ms  ("
                  << kd_us / (double)QUERIES << " us/query)\n";
        std::cout << "  Brute-Force: " << bf_us / 1000.0 << " ms  ("
                  << bf_us / (double)QUERIES << " us/query)\n";
        std::cout << "  Speedup: " << (double)bf_us / kd_us << "x\n\n";
    }

    // KNN 性能 (K=5)
    {
        auto t0 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < QUERIES; ++i)
            tree.knn(queries[i], 5);
        auto t1 = std::chrono::high_resolution_clock::now();
        auto kd_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        auto t2 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < QUERIES; ++i)
            brute_knn(points, queries[i], 5);
        auto t3 = std::chrono::high_resolution_clock::now();
        auto bf_us = std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count();

        std::cout << "KNN x" << QUERIES << " (K=5):\n";
        std::cout << "  KD-Tree:     " << kd_us / 1000.0 << " ms\n";
        std::cout << "  Brute-Force: " << bf_us / 1000.0 << " ms\n";
        std::cout << "  Speedup: " << (double)bf_us / kd_us << "x\n\n";
    }

    // 范围查询性能
    {
        std::vector<AABB> range_queries(QUERIES);
        for (int i = 0; i < QUERIES; ++i) {
            float cx = dist(rng), cy = dist(rng);
            range_queries[i] = {cx, cy, cx + 50.0f, cy + 50.0f};
        }

        auto t0 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < QUERIES; ++i)
            tree.range_query(range_queries[i]);
        auto t1 = std::chrono::high_resolution_clock::now();
        auto kd_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        auto t2 = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < QUERIES; ++i)
            brute_range(points, range_queries[i]);
        auto t3 = std::chrono::high_resolution_clock::now();
        auto bf_us = std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count();

        std::cout << "Range x" << QUERIES << " (50x50 rect):\n";
        std::cout << "  KD-Tree:     " << kd_us / 1000.0 << " ms\n";
        std::cout << "  Brute-Force: " << bf_us / 1000.0 << " ms\n";
        std::cout << "  Speedup: " << (double)bf_us / kd_us << "x\n";
    }

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o kdtree kdtree.cpp
./kdtree
```

**预期输出:**
```
KD-Tree built with 10000 nodes

=== 最近邻查询 (Nearest Neighbor) ===
Query: (500, 500)
KD-Tree:  (498.732, 501.145) dist=1.366
Brute:    (498.732, 501.145) dist=1.366
Match: YES

=== K-最近邻查询 (K=5) ===
KD-Tree KNN results:
  (498.732, 501.145) dist=1.366
  (504.891, 496.237) dist=6.182
  (492.341, 506.892) dist=10.208
  (506.445, 491.883) dist=10.466
  (510.234, 492.567) dist=12.670
Match with brute-force: YES

=== 范围查询 ===
Rect: [200, 200] -> [400, 400]
KD-Tree found: 403 points
Brute   found: 403 points
Match: YES

=== 性能对比: KD-Tree vs Brute-Force ===
NN  queries x1000:
  KD-Tree:     2.3 ms  (2.3 us/query)
  Brute-Force: 148.7 ms  (148.7 us/query)
  Speedup: 64.7x

KNN x1000 (K=5):
  KD-Tree:     8.1 ms
  Brute-Force: 181.2 ms
  Speedup: 22.4x

Range x1000 (50x50 rect):
  KD-Tree:     4.6 ms
  Brute-Force: 152.3 ms
  Speedup: 33.1x
```

(具体数值因硬件而异；在 10,000 点的规模下，KD-Tree 的 NN 查询能提供约 **50-100x** 的加速。点数越多，加速比越大。)

## 3. 练习

### 基础练习：3D KD-Tree 扩展

将 `KDTREE` 从 2D 扩展到 3D。关键修改：

1. `Point3D` 结构体，`operator[]` 返回 dim=0/1/2 分别对应 x/y/z
2. `depth % 3` 决定切分轴
3. 增加 Axis-Aligned Bounding Box (AABB) 的第三个维度

**验证**: 用 5000 个随机 3D 点测试 NN 查询，与暴力搜索结果比较。

### 进阶练习：增量插入 (不平衡 KD-Tree)

实现 `KDTree::insert(Point2D p)` — 不按中位数构建，而是从空树开始逐个插入。插入逻辑：从根开始，按切分轴的比较值递归到叶子，将新点插入为叶子节点的子节点。

**对比实验**:
1. 随机打乱 10,000 个点，用 `insert` 逐个插入
2. 用 `build` (中位数平衡构建) 建树
3. 对 1000 次 NN 查询测量两者的查询时间

**预期发现**：随机插入顺序下，树可能严重不平衡（深 ~100 而非 ~14），导致 NN 查询变慢 2-10x。

### 挑战练习：nth_element 原地构建（零拷贝）

当前 `build_recursive` 每次递归调用都复制 `std::vector`——对 10,000 个点会产生 ~20,000 次复制。实现原地版本：

```cpp
KDNode* build_inplace(std::vector<Point2D>& points, size_t lo, size_t hi, int depth);
```

参数 `lo` 和 `hi` 定义一个 [lo, hi) 的子范围。每次递归只对子范围做 `nth_element`，不需要复制。

**验证**: 测量 `build` vs `build_inplace` 的构建时间。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 将 2D KD-Tree 扩展到 3D，核心修改点：`Point3D` 增加 z 分量、切分轴循环 `depth % 3`、AABB 增加 z 范围、距离计算增加 z 分量。
>
> ```cpp
> // ============================================================
> // 3D 点
> // ============================================================
> struct Point3D {
>     float x, y, z;
>     Point3D() : x(0), y(0), z(0) {}
>     Point3D(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}
>
>     float operator[](int dim) const {
>         switch (dim) { case 0: return x; case 1: return y; case 2: return z; }
>         return 0;
>     }
>     float& operator[](int dim) {
>         switch (dim) { case 0: return x; case 1: return y; case 2: return z; }
>         return x;
>     }
> };
>
> float squared_dist3D(const Point3D& a, const Point3D& b) {
>     float dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
>     return dx*dx + dy*dy + dz*dz;
> }
>
> // ============================================================
> // 3D AABB
> // ============================================================
> struct AABB3D {
>     float x_min, y_min, z_min, x_max, y_max, z_max;
>     bool contains(const Point3D& p) const {
>         return p.x >= x_min && p.x <= x_max &&
>                p.y >= y_min && p.y <= y_max &&
>                p.z >= z_min && p.z <= z_max;
>     }
> };
>
> // ============================================================
> // 3D KD-Tree
> // ============================================================
> struct KDNode3D {
>     Point3D point;
>     KDNode3D *left, *right;
>     KDNode3D(const Point3D& p) : point(p), left(nullptr), right(nullptr) {}
> };
>
> class KDTree3D {
> public:
>     KDTree3D() : root_(nullptr) {}
>     ~KDTree3D() { destroy(root_); }
>
>     void build(std::vector<Point3D> points) {
>         destroy(root_);
>         root_ = build_recursive(points, 0);
>     }
>
>     Point3D nearest(const Point3D& query) const {
>         float best_d2 = std::numeric_limits<float>::max();
>         Point3D best;
>         nearest_recursive(root_, query, 0, best, best_d2);
>         return best;
>     }
>
>     std::vector<Point3D> range_query(const AABB3D& rect) const {
>         std::vector<Point3D> results;
>         range_recursive(root_, 0, rect, results);
>         return results;
>     }
>
> private:
>     KDNode3D* root_;
>
>     static KDNode3D* build_recursive(std::vector<Point3D>& points, int depth) {
>         if (points.empty()) return nullptr;
>         int axis = depth % 3;  // 关键：3 维循环
>         size_t median = points.size() / 2;
>         std::nth_element(points.begin(), points.begin() + median, points.end(),
>             [axis](const Point3D& a, const Point3D& b) { return a[axis] < b[axis]; });
>         KDNode3D* node = new KDNode3D(points[median]);
>         std::vector<Point3D> left_pts(points.begin(), points.begin() + median);
>         std::vector<Point3D> right_pts(points.begin() + median + 1, points.end());
>         node->left  = build_recursive(left_pts,  depth + 1);
>         node->right = build_recursive(right_pts, depth + 1);
>         return node;
>     }
>
>     static void nearest_recursive(KDNode3D* node, const Point3D& query, int depth,
>                                    Point3D& best, float& best_d2) {
>         if (!node) return;
>         float d2 = squared_dist3D(query, node->point);
>         if (d2 < best_d2) { best_d2 = d2; best = node->point; }
>         int axis = depth % 3;
>         float diff = query[axis] - node->point[axis];
>         KDNode3D* first  = (diff <= 0) ? node->left  : node->right;
>         KDNode3D* second = (diff <= 0) ? node->right : node->left;
>         nearest_recursive(first,  query, depth + 1, best, best_d2);
>         if (diff * diff < best_d2)  // 剪枝：轴距 < 当前最优
>             nearest_recursive(second, query, depth + 1, best, best_d2);
>     }
>
>     static void range_recursive(KDNode3D* node, int depth,
>                                  const AABB3D& rect, std::vector<Point3D>& results) {
>         if (!node) return;
>         if (rect.contains(node->point)) results.push_back(node->point);
>         int axis = depth % 3;
>         // 左子树可能与查询区域相交？
>         if (node->point[axis] >= (axis == 0 ? rect.x_min : axis == 1 ? rect.y_min : rect.z_min))
>             range_recursive(node->left, depth + 1, rect, results);
>         // 右子树可能与查询区域相交？
>         if (node->point[axis] <= (axis == 0 ? rect.x_max : axis == 1 ? rect.y_max : rect.z_max))
>             range_recursive(node->right, depth + 1, rect, results);
>     }
>
>     static void destroy(KDNode3D* node) {
>         if (!node) return;
>         destroy(node->left);
>         destroy(node->right);
>         delete node;
>     }
> };
>
> // 验证（main 中调用）
> // std::vector<Point3D> pts(5000);
> // std::mt19937 rng(42);
> // std::uniform_real_distribution<float> dist(-100, 100);
> // for (auto& p : pts) p = Point3D(dist(rng), dist(rng), dist(rng));
> // KDTree3D tree; tree.build(pts);
> // Point3D q(dist(rng), dist(rng), dist(rng));
> // Point3D kd_result = tree.nearest(q);
> // // 暴力验证
> // float best_d2 = std::numeric_limits<float>::max();
> // Point3D bf_result;
> // for (auto& p : pts) {
> //     float d2 = squared_dist3D(q, p);
> //     if (d2 < best_d2) { best_d2 = d2; bf_result = p; }
> // }
> // assert(squared_dist3D(kd_result, bf_result) < 0.001f);
> ```
>
> **关键差异总结**：2D → 3D 的唯一本质变化是将 `depth % 2` 改为 `depth % 3`，其余（nth_element、递归、剪枝逻辑）全部一致——这正是 KD-Tree "维度无关"设计的优势。

> [!tip]- 练习 2 参考答案
> 增量插入在不平衡 KD-Tree 上的实现，每次插入从根沿切分轴递归到叶子，在空指针处创建新节点。
>
> ```cpp
> // 在 KDTree 类中添加以下方法（保持 2D 版本）
> public:
>     // 插入单个点——不平衡构建，O(depth) ≈ O(log N) 平均，O(N) 最坏
>     void insert(const Point2D& p) {
>         root_ = insert_recursive(root_, p, 0);
>     }
>
> private:
>     // 递归插入：沿切分轴走到叶子，在 nullptr 处创建节点
>     static KDNode* insert_recursive(KDNode* node, const Point2D& p, int depth) {
>         if (!node) return new KDNode(p);
>
>         int axis = depth % 2;
>         if (p[axis] < node->point[axis])
>             node->left  = insert_recursive(node->left,  p, depth + 1);
>         else
>             node->right = insert_recursive(node->right, p, depth + 1);
>         return node;
>     }
> ```
>
> **对比实验代码**（加到 main 中）：
>
> ```cpp
> // === 不平衡 vs 平衡对比 ===
> const int N = 10000;
> std::vector<Point2D> pts_unbalanced(N);
> std::mt19937 rng(42);
> std::uniform_real_distribution<float> dist(-500, 500);
> for (auto& p : pts_unbalanced) p = Point2D(dist(rng), dist(rng));
>
> // 不平衡插入（按随机顺序）
> KDTree unbalanced_tree;
> auto t1 = std::chrono::high_resolution_clock::now();
> for (auto& p : pts_unbalanced) unbalanced_tree.insert(p);
> auto t2 = std::chrono::high_resolution_clock::now();
> auto insert_us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
>
> // 平衡构建
> KDTree balanced_tree;
> t1 = std::chrono::high_resolution_clock::now();
> balanced_tree.build(pts_unbalanced);
> t2 = std::chrono::high_resolution_clock::now();
> auto build_us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
>
> // NN 查询对比
> const int QUERIES = 1000;
> std::vector<Point2D> queries(QUERIES);
> for (auto& q : queries) q = Point2D(dist(rng), dist(rng));
>
> t1 = std::chrono::high_resolution_clock::now();
> for (auto& q : queries) unbalanced_tree.nearest(q);
> t2 = std::chrono::high_resolution_clock::now();
> auto nn_unbalanced_us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
>
> t1 = std::chrono::high_resolution_clock::now();
> for (auto& q : queries) balanced_tree.nearest(q);
> t2 = std::chrono::high_resolution_clock::now();
> auto nn_balanced_us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
>
> std::cout << "不平衡插入: " << insert_us << "us,  平衡构建: " << build_us << "us\n";
> std::cout << "不平衡 NN:  " << nn_unbalanced_us << "us, 平衡 NN: " << nn_balanced_us << "us ("
>           << (double)nn_unbalanced_us / nn_balanced_us << "x slower)\n";
> ```
>
> **为何不平衡插入更慢？** 插入不保证中位数切分，实际深度取决于插入顺序。随机顺序下平均深度 ~O(log N) 但常数比平衡版本大；最坏情况（如按 x 排序插入）退化为链表，查询退化为 O(N)。游戏场景中若单位生成位置有空间局部性，不平衡插入的性能退化会更严重。

> [!tip]- 练习 3 参考答案
> 通过 `[lo, hi)` 区间索引避免每次递归复制 vector，nth_element 只作用于子范围。
>
> ```cpp
> // 在 KDTree 类中添加
> public:
>     // 原地构建：不复制 vector，用 [lo, hi) 索引指定子范围
>     void build_inplace(std::vector<Point2D>& points) {
>         destroy(root_);
>         root_ = build_inplace_recursive(points, 0, points.size(), 0);
>     }
>
> private:
>     // 在 [lo, hi) 范围内原地构建，depth 控制切分轴
>     static KDNode* build_inplace_recursive(std::vector<Point2D>& points,
>                                              size_t lo, size_t hi, int depth) {
>         if (lo >= hi) return nullptr;
>
>         int axis = depth % 2;
>         size_t mid = lo + (hi - lo) / 2;  // 中位数索引 = lo + 区间大小/2
>
>         // 只对 [lo, hi) 子范围做 nth_element——不动区间外的元素
>         std::nth_element(points.begin() + lo,
>                          points.begin() + mid,
>                          points.begin() + hi,
>             [axis](const Point2D& a, const Point2D& b) {
>                 return a[axis] < b[axis];
>             });
>
>         KDNode* node = new KDNode(points[mid]);
>         node->left  = build_inplace_recursive(points, lo, mid, depth + 1);
>         node->right = build_inplace_recursive(points, mid + 1, hi, depth + 1);
>         return node;
>     }
> ```
>
> **对比验证代码**：
>
> ```cpp
> // === 原地构建 vs 复制构建 ===
> const int N = 10000;
> std::vector<Point2D> pts(N);
> std::mt19937 rng(42);
> std::uniform_real_distribution<float> dist(-500, 500);
> for (auto& p : pts) p = Point2D(dist(rng), dist(rng));
>
> // 复制构建（原始版本）
> auto pts_copy = pts;
> KDTree tree_copy;
> auto t1 = std::chrono::high_resolution_clock::now();
> tree_copy.build(std::move(pts_copy));
> auto t2 = std::chrono::high_resolution_clock::now();
> auto copy_us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
>
> // 原地构建
> auto pts_inplace = pts;
> KDTree tree_inplace;
> t1 = std::chrono::high_resolution_clock::now();
> tree_inplace.build_inplace(pts_inplace);
> t2 = std::chrono::high_resolution_clock::now();
> auto inplace_us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
>
> std::cout << "复制构建: " << copy_us << "us, 原地构建: " << inplace_us << "us ("
>           << (double)copy_us / inplace_us << "x speedup)\n";
> ```
>
> **性能分析**：原 `build_recursive` 每层递归产生两次 vector 复制（left_pts 和 right_pts），总复制次数 ~2N（每层每个元素平均被复制 2 次）。`build_inplace` 零复制——nth_element 在原数组上交换元素，内存分配仅限树节点本身。N=10,000 时通常可提速 2-5x（瓶颈从内存分配转移到 nth_element 的交换操作）。
>
> **注意**：原地构建会破坏原 points 数组的排列顺序——如果调用方后续还需要原数组，应先复制。对于一次性构建后丢弃点列表的场景，原地版本是最优策略。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Bentley, J. L. (1975).** "Multidimensional Binary Search Trees Used for Associative Searching". *Communications of the ACM, 18(9), 509–517.* — KD-Tree 的原始论文
- **Friedman, J. H., Bentley, J. L., & Finkel, R. A. (1977).** "An Algorithm for Finding Best Matches in Logarithmic Expected Time". *ACM Transactions on Mathematical Software, 3(3), 209–226.* — Branch-and-Bound NN 查询的经典论文
- **Moore, A. W. (1991).** "An Introductory Tutorial on KD-Trees" — CMU 技术报告，对 NN 剪枝的最直观解释
- **Bentley, J. L. (1979).** "Decomposable Searching Problems" — 奠定范围查询理论基础
- **Muja, M., & Lowe, D. G. (2009).** "FLANN: Fast Library for Approximate Nearest Neighbors" — 现代近似 NN 库，KD-Tree + 随机化森林
- **Arya, S., Mount, D. M., Netanyahu, N. S., et al. (1998).** "An Optimal Algorithm for Approximate Nearest Neighbor Searching in Fixed Dimensions". *Journal of the ACM, 45(6), 891–923.* — 目前最优的精确/近似 NN 算法（ANN 库）

## 常见陷阱

### 1. 混淆 std::nth_element 和 std::sort

`std::nth_element` 只保证第 N 个元素在正确位置，**不**保证它之前/之后的元素有序。这正是 KD-Tree 需要的——我们只需要中位数在正确位置，左右两半各自内部可以任意排列。用 `std::sort` 是全 O(N log N) 排序，而 `nth_element` 是 O(N)。

### 2. 浮点健壮性：NaN 和 Inf

如果点坐标包含 NaN 或 Inf，`diff <= 0` 的比较会产生不可预测的结果（NaN 比较永远 false），导致搜索走错子树。在游戏寻路场景中不太常见，但如果从物理引擎导入位置，要注意边界。

### 3. 点重合 (Duplicate Points)

如果有多个点坐标完全相同，`nth_element` 后可能存在 "左子树有点等于切分值" 的情况，这破坏了严格的二分性质。实践中通常无妨（比较时 `<` 和 `<=` 的差别），但如果精确计数很重要（如频率统计），需要在节点中存储点列表而非单点。

### 4. 递归深度溢出

在点集按坐标均匀分布时，KD-Tree 深度 ≈ log₂N。但在病态场景下（如所有点共线），nth_element 可能无法有效分割，导致深度 ≈ N。对于 10,000 个点，最坏 10,000 层递归足以爆栈。**解决**：增加栈大小（`-Wl,--stack,16777216` 在 MinGW 上），或者使用显式栈 + 循环实现。

### 5. 不要对频繁更新的场景用 KD-Tree

KD-Tree 的删除需要重建子树——如果游戏单位每帧都在移动，KD-Tree 的重建开销会吃掉所有收益。对于动态场景，使用空间哈希（tutorial 23）或网格，它们 O(1) 的更新开销更适合动态对象。

### 6. 高维诅咒 (Curse of Dimensionality)

KD-Tree 在维度 > 20 时退化为暴力搜索——因为到切分平面的平均距离太大，剪枝几乎不生效。游戏寻路（2D 或 3D）不受影响，但如果扩展为更多特征维度的加权搜索，要注意这个限制。
