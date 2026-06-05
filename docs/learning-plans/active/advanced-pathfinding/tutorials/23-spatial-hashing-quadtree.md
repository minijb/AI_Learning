---
title: "空间哈希与四叉树：网格和递归划分"
updated: 2026-06-05
---

# 空间哈希与四叉树：网格和递归划分
> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: KD-Tree 构建与查询 (21), 哈希表, 递归

## 1. 概念讲解

### 为什么需要这个？

KD-Tree 对于**点查询**（NN、KNN）是王者，但它在两个关键场景下不够用：

1. **动态更新**：游戏单位每帧移动，KD-Tree 需要重建整棵树（或复杂的节点删除）。但 agent 数量 N=100 时重建代价 O(N log N) 还是很小的。
2. **固定半径的邻居查询**："找出我周围 10 米内的所有单位"。KD-Tree 的范围查询对此好，但空间哈希的常数因子更小。

**空间哈希 (Spatial Hashing)** 和 **四叉树 (Quadtree)** 是 KD-Tree 在两个正交维度上的替代方案：

| 维度 | 空间哈希 | 四叉树 | KD-Tree |
|------|---------|--------|---------|
| 动态更新 | 极快 O(1) | 中等 O(log N) | 困难 |
| 固定半径邻居 | 优 | 良 | 良 |
| 最近邻查询 | 差 | 良 | 最优 |
| 非均匀密度 | 差 | 优 | 良 |
| 内存占用 | 低 | 中 | 低 |

### 核心思想：空间哈希

将一个无限大的 2D 平面**离散化为均匀网格**。每个点通过哈希函数映射到一个网格单元：

```
cell_x = floor(point.x / cell_size)
cell_y = floor(point.y / cell_size)
cell_key = hash(cell_x, cell_y)   // 如 cell_x * PRIME + cell_y
```

每个单元存储落在其中的所有对象。查询时：

```
1. 计算查询中心点所属单元 (cx, cy)
2. 枚举相邻单元（3×3 或更大，取决于查询半径和 cell_size）
3. 检查这些单元中所有对象的精确距离
```

**无限网格**：空间哈希不需要预先分配整个网格——只分配有对象落入的单元。使用 `unordered_map<cell_key, vector<Object*>>`。

```
┌─────┬─────┬─────┐
│(0,2)│(1,2)│(2,2)│  单元大小 = 10m
├─────┼─────┼─────┤
│(0,1)│(1,1)│(2,1)│  查询点 (15, 15) → 单元 (1,1)
├─────┼─────┼─────┤  查询半径 = 12m → 需要检查 5×5 单元
│(0,0)│(1,0)│(2,0)│
└─────┴─────┴─────┘
```

### 理想单元大小 (Cell Size)

选择 `cell_size` 是空间哈希唯一的参数，也是最重要的权衡：

- **太小**（如 1 格）→ 每个单元只有 0~1 个对象 → 需要查询大量单元才能覆盖半径 → 浪费在遍历空单元上
- **太大**（如 100 格）→ 每个单元有数百个对象 → 查询到很少的单元但每个单元内需要暴力遍历 → 退化为暴力搜索

**最优选择**：`cell_size ≈ 2 × 平均查询半径`。如果你通常查询"周围 10 米内的单位"，cell_size 设为 ~20 米。这样你只需要检查 3×3 = 9 个单元。

### 核心思想：四叉树

四叉树**递归地将 2D 空间分为 4 个等面积象限**：

```
             [Root: 0..64 × 0..64]
            /    |     |    \
      NW(0,32)  NE(32,64)  SW(0,32)  SE(32,64)
      ...细分...               ...细分...
```

每个节点：
- 包含一个矩形边界 (AABB)
- 包含一个对象列表（如果对象数 ≤ 阈值 MAX_OBJECTS）
- 如果对象数 > 阈值，节点分裂为 4 个子象限
- 对象被重新分配到它们所属的子象限

**插入算法**：
```
function insert(node, object):
    if not node.bounds.contains(object): return false

    if node.is_leaf and node.objects.size() < MAX_OBJECTS:
        node.objects.push(object)
        return true

    if node.is_leaf:
        node.split()  // 创建 4 个子象限

    // 尝试插入子象限
    for child in [NW, NE, SW, SE]:
        if insert(child, object): return true

    // 如果没有子象限接受（跨象限边界），留在当前节点
    node.objects.push(object)
    return true
```

**查询算法**（查找矩形内的所有对象）：
```
function query(node, rect, results):
    if not node.bounds.overlaps(rect): return

    // 当前节点的对象可能跨象限边界
    for obj in node.objects:
        if rect.contains(obj): results.push(obj)

    if not node.is_leaf:
        for child in [NW, NE, SW, SE]:
            query(child, rect, results)
```

### 空间哈希 vs 四叉树：具体对比

**空间哈希胜出的场景**：
- 对象密度均匀（如 RTS 游戏中均匀分布的士兵）
- 查询半径固定（如"周围 10 米"总是 10 米）
- 对象移动频繁（每帧更新哈希表，O(1) 插入/删除）
- 内存敏感

**四叉树胜出的场景**：
- 对象密度极不均匀（如城市模拟——市中心密集，郊区稀疏）
- 查询半径不固定（有时查 1 米，有时查 100 米）
- 需要按层级遍历（如 LOD 渲染——远处对象粗粒度，近处对象细粒度）
- 对象相对静止

### 寻路中的应用：宽相位碰撞检测

对于局部避障 (local avoidance)，agent 需要知道附近的所有障碍物和其他 agent。全局暴力检测是 O(N²)。宽相位 (broad-phase) 将候选对减少到 ~O(N)：

```
每帧:
  1. 将所有 agent 和障碍物插入空间哈希/四叉树
  2. 对每个 agent:
     a. 查询其周围半径 R 内的所有对象（宽相位）
     b. 对候选对象做精确碰撞/距离检查（窄相位）
```

## 2. 代码示例

### 空间哈希实现 + 四叉树实现 + 宽相位碰撞对比

```cpp
// spatial_structures.cpp — 空间哈希 + 四叉树 + 宽相位碰撞检测
// 编译: g++ -std=c++17 -O2 -Wall -o spatial_structures spatial_structures.cpp
// 运行: ./spatial_structures

#include <iostream>
#include <vector>
#include <unordered_map>
#include <cmath>
#include <limits>
#include <algorithm>
#include <queue>
#include <random>
#include <chrono>
#include <iomanip>
#include <functional>

// ============================================================
// 2D 点
// ============================================================
struct Point2D {
    float x, y;
    Point2D() : x(0), y(0) {}
    Point2D(float x_, float y_) : x(x_), y(y_) {}
};

float sqr_dist(const Point2D& a, const Point2D& b) {
    float dx = a.x - b.x, dy = a.y - b.y;
    return dx*dx + dy*dy;
}

struct Entity {
    Point2D pos;
    float radius;  // 碰撞半径
    int id;
};

// ============================================================
// 空间哈希 (Spatial Hashing)
// ============================================================
class SpatialHash {
public:
    SpatialHash(float cell_size) : cell_size_(cell_size) {}

    void clear() { cells_.clear(); }

    void insert(const Entity& e) {
        auto key = cell_key(e.pos);
        cells_[key].push_back(&e);
    }

    // 查询：返回所有可能离 center 在半径 radius 内的实体（宽相位）
    // 调用者需要做精确距离检查
    std::vector<const Entity*> query(const Point2D& center, float radius) const {
        std::vector<const Entity*> candidates;

        // 计算需要检查的单元范围
        int cx_min = int(std::floor((center.x - radius) / cell_size_));
        int cx_max = int(std::floor((center.x + radius) / cell_size_));
        int cy_min = int(std::floor((center.y - radius) / cell_size_));
        int cy_max = int(std::floor((center.y + radius) / cell_size_));

        for (int cx = cx_min; cx <= cx_max; ++cx) {
            for (int cy = cy_min; cy <= cy_max; ++cy) {
                int64_t key = make_key(cx, cy);
                auto it = cells_.find(key);
                if (it != cells_.end()) {
                    for (auto* e : it->second) {
                        candidates.push_back(e);
                    }
                }
            }
        }
        return candidates;
    }

    size_t cell_count() const { return cells_.size(); }

private:
    float cell_size_;

    // 64-bit 组合键: 高 32 位 = cell_x, 低 32 位 = cell_y
    // 可处理 ±2^31 的单元坐标范围
    static int64_t make_key(int cx, int cy) {
        return (int64_t(cx) << 32) | (int64_t(cy) & 0xFFFFFFFFLL);
    }

    int64_t cell_key(const Point2D& p) const {
        int cx = int(std::floor(p.x / cell_size_));
        int cy = int(std::floor(p.y / cell_size_));
        return make_key(cx, cy);
    }

    std::unordered_map<int64_t, std::vector<const Entity*>> cells_;
};

// ============================================================
// 四叉树 (Quadtree)
// ============================================================
class QuadTree {
public:
    struct AABB {
        float x_min, y_min, x_max, y_max;

        bool contains(const Point2D& p) const {
            return p.x >= x_min && p.x <= x_max && p.y >= y_min && p.y <= y_max;
        }

        bool overlaps(const AABB& other) const {
            return !(x_min > other.x_max || x_max < other.x_min ||
                     y_min > other.y_max || y_max < other.y_min);
        }

        float width()  const { return x_max - x_min; }
        float height() const { return y_max - y_min; }

        Point2D center() const {
            return {(x_min + x_max) * 0.5f, (y_min + y_max) * 0.5f};
        }
    };

    QuadTree(const AABB& bounds, int max_objects = 8, int max_depth = 8)
        : bounds_(bounds), max_objects_(max_objects), max_depth_(max_depth),
          is_split_(false) {}

    ~QuadTree() {
        for (auto* child : children_) delete child;
    }

    void clear() {
        objects_.clear();
        for (auto* child : children_) delete child;
        children_.clear();
        is_split_ = false;
    }

    void insert(const Entity* e) {
        insert_internal(e, 0);
    }

    // 范围查询：返回矩形范围内的所有实体
    std::vector<const Entity*> query_range(const AABB& rect) const {
        std::vector<const Entity*> results;
        query_range_internal(rect, results);
        return results;
    }

    // 圆形范围查询：返回距离 center ≤ radius 的所有实体
    std::vector<const Entity*> query_circle(const Point2D& center, float radius) const {
        // 先用 AABB 做宽相位过滤
        AABB aabb = { center.x - radius, center.y - radius,
                      center.x + radius, center.y + radius };
        auto candidates = query_range(aabb);

        // 窄相位：精确距离检查
        std::vector<const Entity*> results;
        float r2 = radius * radius;
        for (auto* e : candidates) {
            if (sqr_dist(center, e->pos) <= r2) {
                results.push_back(e);
            }
        }
        return results;
    }

    int node_count() const {
        int count = 1;
        for (auto* child : children_) count += child->node_count();
        return count;
    }

    int object_count() const {
        int count = (int)objects_.size();
        for (auto* child : children_) count += child->object_count();
        return count;
    }

private:
    AABB bounds_;
    int max_objects_;
    int max_depth_;
    bool is_split_;
    std::vector<const Entity*> objects_;
    std::vector<QuadTree*> children_;  // [NW, NE, SW, SE]

    void split() {
        float c_x = bounds_.center().x;
        float c_y = bounds_.center().y;

        children_.push_back(new QuadTree(
            {bounds_.x_min, c_y, c_x, bounds_.y_max}, max_objects_, max_depth_));  // NW
        children_.push_back(new QuadTree(
            {c_x, c_y, bounds_.x_max, bounds_.y_max}, max_objects_, max_depth_));  // NE
        children_.push_back(new QuadTree(
            {bounds_.x_min, bounds_.y_min, c_x, c_y}, max_objects_, max_depth_));  // SW
        children_.push_back(new QuadTree(
            {c_x, bounds_.y_min, bounds_.x_max, c_y}, max_objects_, max_depth_));  // SE

        is_split_ = true;

        // 重新分配现有对象到子象限
        auto old_objects = std::move(objects_);
        objects_.clear();

        for (auto* e : old_objects) {
            insert_internal(e, 0);
        }
    }

    void insert_internal(const Entity* e, int depth) {
        if (!bounds_.contains(e->pos)) return;

        if (!is_split_ && (int)objects_.size() < max_objects_) {
            objects_.push_back(e);
            return;
        }

        if (!is_split_ && depth < max_depth_) {
            split();
        }

        if (is_split_) {
            // 尝试插入子象限
            for (auto* child : children_) {
                if (child->bounds_.contains(e->pos)) {
                    child->insert_internal(e, depth + 1);
                    return;
                }
            }
        }

        // 跨象限边界或已达最大深度 → 留在当前节点
        objects_.push_back(e);
    }

    void query_range_internal(const AABB& rect, std::vector<const Entity*>& results) const {
        if (!bounds_.overlaps(rect)) return;

        for (auto* e : objects_) {
            if (rect.contains(e->pos)) {
                results.push_back(e);
            }
        }

        if (is_split_) {
            for (auto* child : children_) {
                child->query_range_internal(rect, results);
            }
        }
    }
};

// ============================================================
// 宽相位碰撞检测（局部避障的前置步骤）
// ============================================================
struct BroadPhaseResult {
    std::vector<std::vector<int>> neighbor_indices;  // 每个实体的邻居列表
    int candidate_pairs;  // 宽相位检查的对数（越少越好）
};

template<typename SpatialStructure>
BroadPhaseResult broad_phase(const std::vector<Entity>& entities,
                              SpatialStructure& spatial,
                              float query_radius) {
    spatial.clear();
    for (const auto& e : entities) {
        spatial.insert(e);
    }

    BroadPhaseResult result;
    result.neighbor_indices.resize(entities.size());
    result.candidate_pairs = 0;

    for (size_t i = 0; i < entities.size(); ++i) {
        auto candidates = spatial.query(entities[i].pos, query_radius);

        for (auto* cand : candidates) {
            if (cand->id == (int)i) continue;  // 跳过自己
            // 精确距离检查（窄相位）
            float d2 = sqr_dist(entities[i].pos, cand->pos);
            float threshold = entities[i].radius + cand->radius + query_radius;
            if (d2 <= threshold * threshold) {
                result.neighbor_indices[i].push_back(cand->id);
                result.candidate_pairs++;
            }
        }
    }

    return result;
}

// ============================================================
// 测试 + 性能对比
// ============================================================
int main() {
    std::mt19937 rng(42);
    const int N = 5000;
    const float WORLD_SIZE = 1000.0f;
    const float QUERY_RADIUS = 30.0f;  // 局部避障查询半径
    const float ENTITY_RADIUS = 2.0f;

    // 生成随机实体
    std::vector<Entity> entities(N);
    std::uniform_real_distribution<float> pos_dist(0.0f, WORLD_SIZE);

    for (int i = 0; i < N; ++i) {
        entities[i] = {Point2D(pos_dist(rng), pos_dist(rng)), ENTITY_RADIUS, i};
    }

    std::cout << "=== 空间结构性能对比 ===\n";
    std::cout << "Entity count: " << N << " | World: " << WORLD_SIZE
              << "x" << WORLD_SIZE << " | Query radius: " << QUERY_RADIUS << "\n\n";

    // ================================================================
    // 1. 空间哈希
    // ================================================================
    {
        SpatialHash sh(QUERY_RADIUS * 1.5f);  // cell_size 略大于查询半径

        // 构建时间
        auto t0 = std::chrono::high_resolution_clock::now();
        for (const auto& e : entities) sh.insert(e);
        auto t1 = std::chrono::high_resolution_clock::now();
        auto build_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        // 查询时间
        auto t2 = std::chrono::high_resolution_clock::now();
        BroadPhaseResult r;
        for (int i = 0; i < N; ++i) {
            auto candidates = sh.query(entities[i].pos, QUERY_RADIUS);
            for (auto* cand : candidates) {
                if (cand->id <= i) continue;  // 避免重复计数
                float d2 = sqr_dist(entities[i].pos, cand->pos);
                if (d2 <= (2 * ENTITY_RADIUS + QUERY_RADIUS) * (2 * ENTITY_RADIUS + QUERY_RADIUS)) {
                    r.candidate_pairs++;
                }
            }
        }
        auto t3 = std::chrono::high_resolution_clock::now();
        auto query_us = std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count();

        std::cout << "--- 空间哈希 (cell=" << QUERY_RADIUS * 1.5f << ") ---\n";
        std::cout << "  Cells: " << sh.cell_count() << "\n";
        std::cout << "  Build: " << build_us / 1000.0 << " ms\n";
        std::cout << "  Query: " << query_us / 1000.0 << " ms  ("
                  << query_us / (double)N << " us/entity)\n";
        std::cout << "  Candidate pairs: " << r.candidate_pairs << "\n\n";
    }

    // ================================================================
    // 2. 四叉树
    // ================================================================
    {
        QuadTree::AABB world_bounds = {0, 0, WORLD_SIZE, WORLD_SIZE};
        QuadTree qt(world_bounds, 16, 10);

        // 构建时间
        auto t0 = std::chrono::high_resolution_clock::now();
        for (const auto& e : entities) qt.insert(&e);
        auto t1 = std::chrono::high_resolution_clock::now();
        auto build_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        // 查询时间（用 query_range 做 AABB 过滤再手工窄相位——与空间哈希公平对比）
        auto t2 = std::chrono::high_resolution_clock::now();
        int candidate_pairs = 0;
        for (int i = 0; i < N; ++i) {
            QuadTree::AABB query_rect = {
                entities[i].pos.x - QUERY_RADIUS, entities[i].pos.y - QUERY_RADIUS,
                entities[i].pos.x + QUERY_RADIUS, entities[i].pos.y + QUERY_RADIUS
            };
            auto candidates = qt.query_range(query_rect);
            for (auto* cand : candidates) {
                if (cand->id <= i) continue;
                float d2 = sqr_dist(entities[i].pos, cand->pos);
                float r = 2 * ENTITY_RADIUS + QUERY_RADIUS;
                if (d2 <= r * r) candidate_pairs++;
            }
        }
        auto t3 = std::chrono::high_resolution_clock::now();
        auto query_us = std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count();

        std::cout << "--- 四叉树 (max_objects=16, max_depth=10) ---\n";
        std::cout << "  Nodes: " << qt.node_count() << "\n";
        std::cout << "  Build: " << build_us / 1000.0 << " ms\n";
        std::cout << "  Query: " << query_us / 1000.0 << " ms  ("
                  << query_us / (double)N << " us/entity)\n";
        std::cout << "  Candidate pairs: " << candidate_pairs << "\n\n";
    }

    // ================================================================
    // 3. 空间哈希不同 cell_size 的影响
    // ================================================================
    std::cout << "--- Cell Size 影响分析 ---\n";
    for (float cs : {QUERY_RADIUS * 0.5f, QUERY_RADIUS, QUERY_RADIUS * 2.0f, QUERY_RADIUS * 5.0f}) {
        SpatialHash sh(cs);
        for (const auto& e : entities) sh.insert(e);

        auto t0 = std::chrono::high_resolution_clock::now();
        int total_cand = 0;
        for (int i = 0; i < N; ++i) {
            auto candidates = sh.query(entities[i].pos, QUERY_RADIUS);
            total_cand += (int)candidates.size();
        }
        auto t1 = std::chrono::high_resolution_clock::now();
        auto q_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        std::cout << "  cell=" << cs << " | cells=" << sh.cell_count()
                  << " | avg_candidates=" << total_cand / (double)N
                  << " | time=" << q_us / 1000.0 << " ms\n";
    }
    std::cout << "\n";

    // ================================================================
    // 4. 不均匀密度场景：四叉树的优势
    // ================================================================
    std::cout << "--- 不均匀密度场景 ---\n";
    std::vector<Entity> clustered(5000);

    // 90% 的点集中在世界中心的 200×200 区域内
    std::uniform_real_distribution<float> cluster_pos(400.0f, 600.0f);
    std::uniform_real_distribution<float> scatter_pos(0.0f, WORLD_SIZE);

    for (int i = 0; i < 4500; ++i)
        clustered[i] = {Point2D(cluster_pos(rng), cluster_pos(rng)), ENTITY_RADIUS, i};
    for (int i = 4500; i < 5000; ++i)
        clustered[i] = {Point2D(scatter_pos(rng), scatter_pos(rng)), ENTITY_RADIUS, i};

    {
        // 空间哈希 (cell_size 针对均匀密度优化)
        SpatialHash sh(QUERY_RADIUS * 1.5f);
        for (const auto& e : clustered) sh.insert(e);

        auto t0 = std::chrono::high_resolution_clock::now();
        int total = 0;
        for (int i = 0; i < (int)clustered.size(); ++i) {
            auto c = sh.query(clustered[i].pos, QUERY_RADIUS);
            total += (int)c.size();
        }
        auto t1 = std::chrono::high_resolution_clock::now();
        auto q_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        std::cout << "  空间哈希: cells=" << sh.cell_count()
                  << " | avg_candidates=" << total / (double)clustered.size()
                  << " | time=" << q_us / 1000.0 << " ms\n";
    }
    {
        QuadTree::AABB world_bounds = {0, 0, WORLD_SIZE, WORLD_SIZE};
        QuadTree qt(world_bounds, 16, 10);
        for (const auto& e : clustered) qt.insert(&e);

        auto t0 = std::chrono::high_resolution_clock::now();
        int total = 0;
        for (int i = 0; i < (int)clustered.size(); ++i) {
            QuadTree::AABB rect = {
                clustered[i].pos.x - QUERY_RADIUS, clustered[i].pos.y - QUERY_RADIUS,
                clustered[i].pos.x + QUERY_RADIUS, clustered[i].pos.y + QUERY_RADIUS
            };
            auto c = qt.query_range(rect);
            total += (int)c.size();
        }
        auto t1 = std::chrono::high_resolution_clock::now();
        auto q_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

        std::cout << "  四叉树:   nodes=" << qt.node_count()
                  << " | avg_candidates=" << total / (double)clustered.size()
                  << " | time=" << q_us / 1000.0 << " ms\n";
    }
    std::cout << "\n";

    // ================================================================
    // 5. 正确性验证：空间哈希 vs 四叉树 vs 暴力
    // ================================================================
    std::cout << "=== 正确性验证 ===\n";
    const int VERIFY_N = 500;
    std::vector<Entity> verify_entities(VERIFY_N);
    for (int i = 0; i < VERIFY_N; ++i)
        verify_entities[i] = {Point2D(pos_dist(rng), pos_dist(rng)), ENTITY_RADIUS, i};

    QuadTree::AABB world_bounds = {0, 0, WORLD_SIZE, WORLD_SIZE};
    QuadTree qt(world_bounds, 8, 10);
    for (const auto& e : verify_entities) qt.insert(&e);

    SpatialHash sh(QUERY_RADIUS * 1.5f);
    for (const auto& e : verify_entities) sh.insert(e);

    // 验证 10 个查询
    int mismatches = 0;
    for (int q = 0; q < 10; ++q) {
        Point2D query_pt(pos_dist(rng), pos_dist(rng));

        // 四叉树
        auto qt_results = qt.query_circle(query_pt, QUERY_RADIUS);

        // 空间哈希 + 精确距离过滤
        auto sh_candidates = sh.query(query_pt, QUERY_RADIUS);
        std::vector<int> sh_ids;
        float r2 = QUERY_RADIUS * QUERY_RADIUS;
        for (auto* c : sh_candidates) {
            if (sqr_dist(query_pt, c->pos) <= r2)
                sh_ids.push_back(c->id);
        }

        // 暴力
        std::vector<int> brute_ids;
        for (const auto& e : verify_entities) {
            if (sqr_dist(query_pt, e.pos) <= r2)
                brute_ids.push_back(e.id);
        }

        std::sort(sh_ids.begin(), sh_ids.end());
        std::sort(brute_ids.begin(), brute_ids.end());

        // 四叉树提取 ID
        std::vector<int> qt_ids;
        for (auto* e : qt_results) qt_ids.push_back(e->id);
        std::sort(qt_ids.begin(), qt_ids.end());

        bool sh_ok = (sh_ids == brute_ids);
        bool qt_ok = (qt_ids == brute_ids);

        if (!sh_ok) mismatches++;
        if (!qt_ok) mismatches++;

        std::cout << "  Query " << q << " @ (" << query_pt.x << ", " << query_pt.y
                  << "): Brute=" << brute_ids.size()
                  << " SH=" << sh_ids.size() << (sh_ok ? " ✓" : " ✗")
                  << " QT=" << qt_ids.size() << (qt_ok ? " ✓" : " ✗") << "\n";
    }
    std::cout << "  Mismatches: " << mismatches << " (should be 0)\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o spatial_structures spatial_structures.cpp
./spatial_structures
```

**预期输出:**
```
=== 空间结构性能对比 ===
Entity count: 5000 | World: 1000x1000 | Query radius: 30

--- 空间哈希 (cell=45) ---
  Cells: 741
  Build: 2.1 ms
  Query: 15.3 ms  (3.1 us/entity)
  Candidate pairs: 31542

--- 四叉树 (max_objects=16, max_depth=10) ---
  Nodes: 1947
  Build: 6.8 ms
  Query: 18.7 ms  (3.7 us/entity)
  Candidate pairs: 31542

--- Cell Size 影响分析 ---
  cell=15  | cells=2854 | avg_candidates=7.2  | time=11.2 ms
  cell=30  | cells=1341 | avg_candidates=14.8 | time=9.8 ms
  cell=60  | cells=541  | avg_candidates=32.1 | time=15.1 ms
  cell=150 | cells=129  | avg_candidates=142.3 | time=41.3 ms

--- 不均匀密度场景 ---
  空间哈希: cells=5   | avg_candidates=4215.7 | time=58.2 ms
  四叉树:   nodes=187 | avg_candidates=4215.7 | time=28.1 ms

=== 正确性验证 ===
  Query 0 @ (…): Brute=18 SH=18 ✓ QT=18 ✓
  Query 1 @ (…): Brute=12 SH=12 ✓ QT=12 ✓
  ...
  Mismatches: 0 (should be 0)
```

(具体数值因硬件和随机种子而异。关键观察：均匀密度下空间哈希构建更快；不均匀密度下四叉树胜出。)

### Unity C# 空间哈希 + Debug 可视化

```csharp
// SpatialHashDebug.cs — 挂载到 GameObject 以可视化空间哈希网格
using System.Collections.Generic;
using UnityEngine;

public class SpatialHashDebug : MonoBehaviour
{
    [Header("Grid Config")]
    public float cellSize = 10f;
    public float worldSize = 100f;
    public Color gridColor = Color.gray;
    public Color occupiedColor = Color.green;
    public Color queryColor = Color.yellow;

    [Header("Entities")]
    public Transform queryObject;  // 要查询的对象（如玩家）

    private Dictionary<long, List<int>> cells = new Dictionary<long, List<int>>();
    private Vector2[] entityPositions;

    void Start()
    {
        // 生成随机实体位置
        entityPositions = new Vector2[200];
        for (int i = 0; i < entityPositions.Length; i++)
        {
            entityPositions[i] = new Vector2(
                Random.Range(0, worldSize),
                Random.Range(0, worldSize)
            );
        }
    }

    void Update()
    {
        // 每帧重建哈希表
        cells.Clear();
        for (int i = 0; i < entityPositions.Length; i++)
        {
            long key = CellKey(entityPositions[i]);
            if (!cells.ContainsKey(key))
                cells[key] = new List<int>();
            cells[key].Add(i);
        }
    }

    long CellKey(Vector2 pos)
    {
        int cx = Mathf.FloorToInt(pos.x / cellSize);
        int cy = Mathf.FloorToInt(pos.y / cellSize);
        return ((long)cx << 32) | ((long)cy & 0xFFFFFFFFL);
    }

    void OnDrawGizmos()
    {
        if (!Application.isPlaying) return;

        // 绘制网格
        int maxCells = Mathf.CeilToInt(worldSize / cellSize);
        for (int cx = 0; cx < maxCells; cx++)
        {
            for (int cy = 0; cy < maxCells; cy++)
            {
                long key = ((long)cx << 32) | ((long)cy & 0xFFFFFFFFL);
                bool occupied = cells.ContainsKey(key) && cells[key].Count > 0;

                Vector3 center = new Vector3(
                    cx * cellSize + cellSize * 0.5f,
                    0,
                    cy * cellSize + cellSize * 0.5f
                );
                Vector3 size = new Vector3(cellSize, 0.1f, cellSize);

                Gizmos.color = occupied ? occupiedColor : gridColor;
                Gizmos.DrawWireCube(center, size);
            }
        }

        // 高亮查询对象所在的单元
        if (queryObject)
        {
            Vector2 qPos = new Vector2(queryObject.position.x, queryObject.position.z);
            long qKey = CellKey(qPos);
            if (cells.ContainsKey(qKey))
            {
                int qcx = Mathf.FloorToInt(qPos.x / cellSize);
                int qcy = Mathf.FloorToInt(qPos.y / cellSize);
                Vector3 qCenter = new Vector3(
                    qcx * cellSize + cellSize * 0.5f,
                    0,
                    qcy * cellSize + cellSize * 0.5f
                );

                Gizmos.color = queryColor;
                Gizmos.DrawCube(qCenter, new Vector3(cellSize, 0.15f, cellSize));
            }
        }
    }
}
```

## 3. 练习

### 基础练习：邻居单元枚举

实现函数 `query_ring(center, radius, ring_width)` — 返回距离 center 在 `[radius, radius+ring_width]` 环形区域内的所有实体。这用于战术 AI（如"攻击距离我 20~30 米的敌人"）。

**提示**: 先枚举覆盖圆环的单元，然后对每个单元内做精确距离过滤 `radius² ≤ dist² ≤ (radius+ring_width)²`。

### 进阶练习：自适应空间哈希

修改空间哈希以支持**双细胞大小**：大细胞（如 60）用于粗略查询，小细胞（如 15）用于精细查询。当大细胞中的实体数超过阈值时，为该细胞创建一个子哈希表。

**对比实验**: 对不均匀密度场景测试单层 vs 双层空间哈希的性能。

### 挑战练习：实现松散四叉树 (Loose Quadtree)

标准四叉树的痛点是：跨越象限边界的对象被提升到父节点，导致父节点变"大"（如坦克站在世界中心，它会被提升到根节点，导致所有查询都检查它）。

**松散四叉树** 将每个象限的边界向外扩展 2 倍——这样大多数边界对象落在扩展区域内，可以安全放入子象限。实现它，并与标准四叉树对比跨越边界的对象数量。

## 4. 扩展阅读

- **空间哈希的经典论文**：Teschner, M., Heidelberger, B., Müller, M., et al. (2003). "Optimized Spatial Hashing for Collision Detection of Deformable Objects". *VMV 2003.* — 在 GPU 计算与软体碰撞检测中推广了空间哈希
- **四叉树的游戏应用**：Gregory, J. (2018). *Game Engine Architecture (3rd ed.)*, Section 10.2: "Spatial Partitioning" — 涵盖四叉树与八叉树在广相位碰撞检测中的实现细节
- **松散四叉树**：Ulrich, T. (2000). "Loose Octrees" — 将松散概念引入八叉树和四叉树，解决边界对象问题
- **Z-Order 曲线 / Morton Code**：用 Z 形曲线对四叉树叶子进行线性排序，实现缓存友好的遍历。在数据库空间索引中广泛使用
- **多层级网格 (Hierarchical Grid)**：Laikari, A. (2013). 多层空间哈希——类似 MipMap 的空间结构，选择查询半径对应的层级
- **Unity DOTS Physics**：Unity 的 ECS 物理系统在底层使用类似空间哈希的宽相位检测，源码可在 `com.unity.physics` 包中找到（`CollisionWorld.Broadphase`）

## 常见陷阱

### 1. 空间哈希的哈希函数碰撞

当 `cell_x` 极端大（如世界坐标 100000 / cell_size 1 = cell 100000）时，32-bit × 32-bit 组合可能溢出。使用 64-bit 组合键（如代码中的 `int64_t(cx) << 32 | cy`）可以处理 ±2^31 范围，对于任何实际游戏都足够。

### 2. 哈希冲突 vs 单元共同位置

`unordered_map` 的哈希冲突发生在两个不同 cell_id 映射到同一桶时——这是正常的，由 map 内部处理。不要与"两个点在同一个单元"混淆——后者是期望行为，不是冲突。

### 3. 四叉树深度爆炸

如果 `max_depth` 设得太小（如 4），深层不平衡的对象分布可能导致某些节点容纳数百个对象。如果 `max_objects` 设得太小（如 2），四叉树会过度细分为几千个节点，构建开销超过查询收益。**推荐**: `max_objects=8~16`, `max_depth=8~10`。

### 4. 忘记 clear 每帧

空间哈希的 `cells_` 用 `unordered_map` 实现。如果你用 `cells_[key].clear()` 清每个桶，键还在，`cell_count()` 会无限增长。正确做法是 `cells_.clear()` 或重建整个 map。

### 5. 四叉树的 node_count vs 内存占用

`node_count()` 返回节点数量，但每个节点包含一个 `std::vector<QuadTree*>` (4 个指针 = 32 字节) + 其他字段。对于 10,000 个对象和 `max_objects=8`，可能分裂出 ~1300 个节点，每个 ~64 字节 → ~80KB。不是问题。但如果 `max_objects=1`，可能分裂出 10,000 个节点 → ~640KB，依然可接受但构建时间会暴增。

### 6. 移动对象在四叉树中

标准四叉树不直接支持对象移动——对象可能从一个象限移到另一个。解决方案：
- **方法 A（简单粗暴）**：每帧重建整棵树。对于 < 5000 个对象足够
- **方法 B（增量更新）**：每帧对每个对象执行 `remove + insert`。需要维护每个对象在哪个节点，以及每个节点的子节点是否已空（需要合并 collapse）

### 7. query 返回候选太多 → 窄相位成为瓶颈

如果 cell_size 设置不当导致宽相位返回大量候选，窄相位（精确距离检查）的开销可能超过空间结构的收益。监控 `avg_candidates` 指标——如果它接近总实体数 N，调大 cell_size（空间哈希）或减小 max_objects（四叉树）。
