---
title: "碰撞检测：从 AABB 到 GJK/EPA"
updated: 2026-06-05
---

# 碰撞检测：从 AABB 到 GJK/EPA

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 01-数学基础：线性代数与几何

---

## 1. 概念讲解

### 为什么需要碰撞检测？

碰撞检测（Collision Detection）是游戏物理引擎的核心模块之一。没有碰撞检测，角色会穿墙而过、子弹不会命中目标、车辆会互相穿透。它是游戏世界"物理规则"得以成立的基础。

碰撞检测系统通常分为两个阶段：

- **Broad Phase（粗略阶段）**：快速排除不可能碰撞的物体对，降低计算量
- **Narrow Phase（精确阶段）**：对可能碰撞的物体对进行精确的几何相交测试

本章将系统讲解从最简单的包围体碰撞到复杂凸体碰撞的完整技术栈。

### 核心思想

#### 1.1 包围体（Bounding Volumes）

包围体是用简单几何体包裹复杂物体的策略，用于快速排除不相交的情况。

**常见包围体类型：**

| 包围体 | 优点 | 缺点 | 适用场景 |
|--------|------|------|----------|
| AABB | 计算极快，存储紧凑 | 旋转后需重新计算 | 静态场景，轴对齐物体 |
| Sphere | 旋转不变，检测极快 | 对长条形物体包裹差 | 大致球形的角色/物体 |
| OBB | 旋转后仍紧密包裹 | 检测计算较复杂 | 旋转频繁的物体 |
| Capsule | 适合人形角色 | 比Sphere稍慢 | 角色控制器，人形骨骼 |
| k-DOP | 比AABB更紧密 | 计算量增加 | 需要更紧密包围时 |

#### 1.2 AABB（Axis-Aligned Bounding Box，轴对齐包围盒）

AABB 是与坐标轴对齐的长方体，由最小点和最大点定义：

```
struct AABB {
    Vec3 min;  // 最小角点
    Vec3 max;  // 最大角点
};
```

**AABB-AABB 相交测试原理：**

两个 AABB 相交，当且仅当在**所有三个轴上**的投影区间都有重叠。

```
重叠条件（X轴）：a.max.x >= b.min.x && a.min.x <= b.max.x
重叠条件（Y轴）：a.max.y >= b.min.y && a.min.y <= b.max.y
重叠条件（Z轴）：a.max.z >= b.min.z && a.min.z <= b.max.z

相交 = X重叠 && Y重叠 && Z重叠
```

图解：

```
    Y
    ^
    |   +-------+ b
    |   |   +---+---+
    |   |   |   |   |
    |   +---+---+   |
    |       +-------+ a
    +------------------> X

在 X 轴上：a 的区间 [a.min.x, a.max.x] 与 b 的区间 [b.min.x, b.max.x] 重叠
在 Y 轴上：a 的区间 [a.min.y, a.max.y] 与 b 的区间 [b.min.y, b.max.y] 重叠
=> 两个 AABB 相交
```

**AABB 相交测试代码：**

```cpp
bool AABBIntersect(const AABB& a, const AABB& b) {
    return (a.max.x >= b.min.x && a.min.x <= b.max.x) &&
           (a.max.y >= b.min.y && a.min.y <= b.max.y) &&
           (a.max.z >= b.min.z && a.min.z <= b.max.z);
}
```

时间复杂度：O(1)，只需 6 次比较。

#### 1.3 Sphere（球体）碰撞检测

球体由中心和半径定义：

```
struct Sphere {
    Vec3 center;
    float radius;
};
```

**Sphere-Sphere 相交测试原理：**

两个球体相交，当且仅当球心距离小于等于半径之和。

```
相交条件：|c1 - c2| <= r1 + r2

等价于（避免开方）：|c1 - c2|^2 <= (r1 + r2)^2
```

图解：

```
        c1          c2
        *           *
       / \         / \
      /   \       /   \
     /  r1 \     /  r2 \
    /       \   /       \
   +---------+-+---------+
        d = |c1-c2|

相交：d <= r1 + r2
相离：d > r1 + r2
```

**Sphere-Sphere 相交测试代码：**

```cpp
bool SphereIntersect(const Sphere& a, const Sphere& b) {
    Vec3 diff = a.center - b.center;
    float distSq = Dot(diff, diff);
    float radiusSum = a.radius + b.radius;
    return distSq <= radiusSum * radiusSum;
}
```

时间复杂度：O(1)。

#### 1.4 OBB（Oriented Bounding Box，定向包围盒）

OBB 是任意旋转的长方体，由中心点、三个半轴长度和三个轴方向定义：

```
struct OBB {
    Vec3 center;      // 中心点
    Vec3 axes[3];     // 三个局部轴（单位向量，互相正交）
    Vec3 halfExtents; // 三个半轴长度
};
```

**OBB-OBB 相交测试：**

OBB 的相交测试比 AABB 复杂得多。最常用的方法是**分离轴定理（SAT）**。

#### 1.5 分离轴定理（SAT - Separating Axis Theorem）

**定理陈述：**

> 两个凸多面体不相交，当且仅当存在一个轴，使得两个多面体在该轴上的投影不重叠。

**关键推论：**

对于两个凸多面体，只需要测试**有限个**分离轴。具体来说：

- 对于两个凸多边形（2D）：测试所有边的法线方向
- 对于两个 OBB（3D）：测试 15 个轴
  - A 的 3 个局部轴
  - B 的 3 个局部轴
  - 9 个叉积轴（A的每个轴 × B的每个轴）

**SAT 算法步骤：**

```
1. 收集所有候选分离轴
2. 对每个轴：
   a. 将两个形状投影到该轴上，得到两个区间
   b. 如果区间不重叠，则形状不相交，立即返回 false
3. 如果所有轴都重叠，则形状相交，返回 true
```

图解（2D 情况）：

```
         axis
           ^
           |
    +------|------+
    |  A   |      |
    |    +-|--+   |
    |    | |  |   |
    +----+ |  |   |
         | | B|   |
         +----+   |
              +---+

在 axis 方向上：
- A 的投影区间：[p1, p2]
- B 的投影区间：[p3, p4]
- 两个区间重叠 => axis 不是分离轴

         axis
           ^
           |
    +------+------+
    |  A   |      |
    |      |      |
    +------+      |
           |  B   |
           |      |
           +------+

在 axis 方向上：
- A 的投影区间：[p1, p2]
- B 的投影区间：[p3, p4]
- 两个区间不重叠 => axis 是分离轴！A 和 B 不相交
```

**OBB 投影到轴上的方法：**

OBB 在任意轴 L 上的投影半径（从中心到投影端点的距离）为：

```
r = |halfExtents.x * Dot(axes[0], L)| +
    |halfExtents.y * Dot(axes[1], L)| +
    |halfExtents.z * Dot(axes[2], L)|
```

两个 OBB 中心在轴 L 上的投影距离为 `|Dot(centerA - centerB, L)|`。

相交条件：`投影距离 <= rA + rB`

#### 1.6 Capsule（胶囊体）碰撞检测

胶囊体由线段（中心轴）和半径定义：

```
struct Capsule {
    Vec3 a;       // 线段起点
    Vec3 b;       // 线段终点
    float radius; // 半径
};
```

**Capsule-Capsule 相交测试：**

核心思想：计算两条线段之间的最短距离，如果该距离小于等于半径之和，则相交。

```
相交条件：线段间最短距离 <= radius1 + radius2
```

线段间最短距离的计算涉及求解两条直线的最近点，需要考虑线段端点的情况。

#### 1.7 射线与几何体相交

射线检测在游戏中广泛使用：鼠标拾取、子弹命中检测、视线检测等。

**射线定义：**

```
struct Ray {
    Vec3 origin;    // 起点
    Vec3 direction; // 方向（单位向量）
};

// 射线上任意点：P(t) = origin + t * direction, t >= 0
```

**Ray-AABB 相交：**

使用 Slab 方法（ slab = 一对平行平面）：

```
对每个轴（x, y, z）：
  计算射线与该轴两个 slab 平面的交点参数 t1, t2
  维护 t_min = max(t_min, min(t1, t2))
  维护 t_max = min(t_max, max(t1, t2))

相交条件：t_min <= t_max && t_max >= 0
```

**Ray-Sphere 相交：**

将射线方程代入球面方程，求解二次方程：

```
|P(t) - center|^2 = radius^2
|origin + t*direction - center|^2 = radius^2

令 oc = origin - center
|oc + t*direction|^2 = radius^2
(oc + t*direction)·(oc + t*direction) = radius^2

展开：
(direction·direction)*t^2 + 2*(oc·direction)*t + (oc·oc - radius^2) = 0

因为 direction 是单位向量：
t^2 + 2*(oc·direction)*t + (oc·oc - radius^2) = 0

判别式 D = b^2 - 4ac
D < 0：不相交
D >= 0：相交，取最小的非负 t 值
```

**Ray-Triangle 相交：**

使用 Möller-Trumbore 算法：

```
核心思想：将射线参数方程与三角形重心坐标结合

P(t) = origin + t * direction
P(u,v) = v0 + u*(v1-v0) + v*(v2-v0)

求解：origin + t*direction = v0 + u*e1 + v*e2

使用 Cramer 法则求解 t, u, v
相交条件：t >= 0, u >= 0, v >= 0, u+v <= 1
```

#### 1.8 Minkowski 差与 GJK 算法

**Minkowski 和与差：**

对于两个点集 A 和 B：

- **Minkowski 和**：A + B = {a + b | a ∈ A, b ∈ B}
- **Minkowski 差**：A - B = {a - b | a ∈ A, b ∈ B}

**关键定理：**

> A 和 B 相交，当且仅当原点 O 在 A - B 中。

图解 Minkowski 差：

```
A (正方形)          B (三角形)          A - B
+----+              *                   +----+
|    |             / \                  |    |
|    |            /   \                 |    |
+----+           *-----*                +----+

A - B 是将 A 中的每个点与 B 中的每个点相减得到的形状。
如果 A 和 B 相交，则 A - B 必然包含原点。
```

**GJK 算法核心思想：**

GJK（Gilbert-Johnson-Keerthi）算法不需要显式计算 Minkowski 差，而是通过**支持函数（Support Function）**在 Minkowski 差中迭代构建一个单纯形（simplex），判断原点是否在该单纯形内。

**支持函数：**

对于形状 A 和方向 d，支持函数返回 A 在 d 方向上的最远点：

```
S_A(d) = argmax_{a ∈ A} (a · d)
```

Minkowski 差的支持函数可以分解为：

```
S_{A-B}(d) = S_A(d) - S_B(-d)
```

**GJK 算法步骤：**

```
1. 初始化方向 d（任意方向，如 (1,0,0)）
2. 获取 Minkowski 差中的一个点：v = S_A(d) - S_B(-d)
3. 将 v 加入单纯形
4. 循环：
   a. 更新方向 d = -v（指向原点的方向）
   b. 获取新点 w = S_A(d) - S_B(-d)
   c. 如果 w·d <= 0，说明原点在支持方向上不可达，不相交，返回 false
   d. 将 w 加入单纯形
   e. 如果原点在单纯形内，返回 true
   f. 否则，从单纯形中移除不必要的点，更新 v 为单纯形中离原点最近的点
```

单纯形演化过程（2D 示例）：

```
Step 1: 单纯形只有 1 个点
    *
    |
    v (单纯形顶点)
   /
  O (原点)

Step 2: 加入第 2 个点，形成线段
    *----*
    |   /
    |  /
    | /
    O

Step 3: 加入第 3 个点，形成三角形
    *
   / \
  /   \
 *-----*
  \   /
   \ /
    O (原点在三角形内！相交！)
```

#### 1.9 EPA 算法（Expanding Polytope Algorithm）

GJK 只能判断两个凸体是否相交，但无法给出穿透深度和接触法线。EPA 在 GJK 确认相交后执行，用于计算这些信息。

**EPA 核心思想：**

从 GJK 结束时包含原点的单纯形开始，逐步扩展多面体（polytope），找到离原点最近的面，该面的法线就是接触法线，原点到该面的距离就是穿透深度。

**EPA 算法步骤：**

```
1. 从 GJK 的单纯形（包含原点的多面体）开始
2. 循环：
   a. 找到多面体中离原点最近的面
   b. 获取该面的法线方向 n
   c. 用支持函数获取该方向上的新点：w = S_A(n) - S_B(-n)
   d. 如果 w 已经很接近该面（收敛），停止
   e. 否则，用 w 替换所有"可见"的面，扩展多面体
3. 返回：接触法线 = 最近面的法线，穿透深度 = 原点到最近面的距离
```

图解 EPA：

```
        多面体顶点
             *
            / \
           /   \
          /     \
         *-------*
        / \     / \
       /   \   /   \
      /     \ /     \
     *-------*-------*
      \     / \     /
       \   /   \   /
        \ /     \ /
         *-------*
          \     /
           \   /
            \ /
             O (原点)

找到离原点最近的面（下方面），其法线 n 指向下方。
沿 n 方向获取新支持点 w，扩展多面体。
重复直到收敛。
```

#### 1.10 离散碰撞检测（DCD）vs 连续碰撞检测（CCD）

**DCD（Discrete Collision Detection）：**

在每个时间步检测物体是否相交。简单高效，但在高速运动时可能产生**隧道效应（Tunneling）**——物体在一帧内穿过另一个物体。

```
Frame N:    A --->
                    B

Frame N+1:              A --->
            B

A 穿过了 B，但 DCD 在两帧都未检测到相交！
```

**CCD（Continuous Collision Detection）：**

考虑物体在时间步内的运动轨迹，计算精确的碰撞时间（TOI - Time of Impact）。

```
核心思想：将运动表示为参数方程，求解相交时刻

线性 CCD（假设匀速直线运动）：
A(t) = A0 + t * vA, t ∈ [0, 1]
B(t) = B0 + t * vB, t ∈ [0, 1]

求解 A(t) 和 B(t) 首次相交的 t 值
```

常用 CCD 方法：
- **Swept Volume**：将物体运动轨迹扫过的体积作为检测对象
- **Conservative Advancement**：逐步推进，每次推进安全距离
- **Minkowski Portal Refinement**：用于凸体的精确 CCD

#### 1.11 空间划分加速结构

当场景中有 N 个物体时，暴力两两检测需要 O(N^2) 次测试。空间划分将空间分割，只检测同一区域内的物体。

**八叉树（Octree）：**

递归将三维空间分为 8 个子立方体，直到满足终止条件（最大深度或最少物体数）。

```
        +--------+--------+        Level 0: 整个空间
        |   0    |   1    |
        |        |        |
        +--------+--------+        Level 1: 分为 4 个象限（2D 示意）
        |   2    |   3    |
        |        |        |
        +--------+--------+

3D 中每个节点分为 8 个子节点：
(0,0,0), (1,0,0), (0,1,0), (1,1,0),
(0,0,1), (1,0,1), (0,1,1), (1,1,1)
```

**BVH（Bounding Volume Hierarchy）：**

用树结构组织包围体，叶节点存储实际物体，内部节点存储子树的包围体。

```
         [Root AABB]
        /           \
   [Left AABB]   [Right AABB]
      /    \          /    \
   [AABB] [AABB]  [AABB] [AABB]
    |      |        |      |
  Obj1   Obj2     Obj3   Obj4

自顶向下构建：
1. 计算所有物体的整体 AABB 作为根节点
2. 选择一个分割轴（最长轴或 SAH 最优轴）
3. 将物体分为两组，递归构建子树
```

**SAH（Surface Area Heuristic）**：

用于 BVH 构建的代价模型：

```
Cost = C_traversal + (SA_left/SA_parent) * N_left * C_intersect
                   + (SA_right/SA_parent) * N_right * C_intersect

选择使 Cost 最小的分割方案
```

**动态 AABB 树（Dynamic AABB Tree）**：

对于动态场景（物体在移动），BVH 需要支持高效的更新操作。动态 AABB 树是物理引擎 Broad Phase 的标准数据结构。

核心操作：

1. **插入（Insert）**：为新物体创建叶节点，自底向上更新包围盒。如果插入导致树的平衡性变差，可能触发局部重组。
2. **移除（Remove）**：移除叶节点并更新父节点的包围盒。
3. **更新（Update）**：当物体移动时，其 AABB 可能变化。如果新的 AABB 仍然在父节点的包围盒内，只需更新叶节点；如果超出了父包围盒，则需要重新插入。
4. **碰撞查询（Query）**：给定一个 AABB，查询与之重叠的所有叶节点。这用于 Broad Phase 的配对检测。

动态 AABB 树的一个重要优化是**延迟更新（Deferred Update）**。在每一帧，先批量更新所有物体的 AABB（标记需要更新的节点），然后在帧末统一执行树的再平衡操作，而不是每次更新都立即调整树结构。

```cpp
// 动态 AABB 树节点
struct DynamicAABBNode {
    AABB bounds;           // 包围盒
    int parent;            // 父节点索引 (-1 表示根)
    int left;              // 左子节点 (-1 表示叶节点)
    int right;             // 右子节点
    int objectId;          // 叶节点关联的物体 ID
    bool isLeaf;           // 是否为叶节点
};

class DynamicAABBTree {
public:
    std::vector<DynamicAABBNode> nodes;
    int root;
    int freeList;          // 空闲节点链表头

    DynamicAABBTree() : root(-1), freeList(-1) {}

    // 插入物体，返回节点索引
    int Insert(const AABB& bounds, int objectId) {
        int nodeId = AllocateNode();
        nodes[nodeId].bounds = bounds;
        nodes[nodeId].objectId = objectId;
        nodes[nodeId].isLeaf = true;
        nodes[nodeId].left = nodes[nodeId].right = -1;

        if (root == -1) {
            root = nodeId;
            return nodeId;
        }

        // 找到最佳插入位置（使表面积增加最小）
        int bestSibling = FindBestSibling(bounds);
        InsertLeaf(nodeId, bestSibling);
        return nodeId;
    }

    // 更新物体 AABB（如果超出父包围盒则重新插入）
    void Update(int nodeId, const AABB& newBounds, float margin = 0.1f) {
        if (nodeId < 0 || nodeId >= (int)nodes.size()) return;
        auto& node = nodes[nodeId];
        if (!node.isLeaf) return;

        // 如果新 AABB 仍在当前包围盒内（考虑 margin），只需更新
        AABB fatBounds = newBounds;
        fatBounds.min -= Vec3(margin, margin, margin);
        fatBounds.max += Vec3(margin, margin, margin);

        if (node.bounds.Contains(newBounds)) {
            node.bounds = fatBounds;
            // 向上更新父节点
            Refit(nodeId);
        } else {
            // 超出范围，重新插入
            RemoveLeaf(nodeId);
            node.bounds = fatBounds;
            InsertLeaf(nodeId, FindBestSibling(fatBounds));
        }
    }

    // 查询与给定 AABB 重叠的所有物体
    void Query(const AABB& queryBounds, std::vector<int>& results) const {
        if (root == -1) return;
        std::vector<int> stack;
        stack.push_back(root);

        while (!stack.empty()) {
            int nodeId = stack.back();
            stack.pop_back();
            if (nodeId == -1) continue;

            const auto& node = nodes[nodeId];
            if (!AABBIntersect(queryBounds, node.bounds)) continue;

            if (node.isLeaf) {
                results.push_back(node.objectId);
            } else {
                stack.push_back(node.left);
                stack.push_back(node.right);
            }
        }
    }

private:
    int AllocateNode() {
        if (freeList != -1) {
            int id = freeList;
            freeList = nodes[id].parent;  // 复用 parent 作为链表指针
            return id;
        }
        nodes.emplace_back();
        return (int)nodes.size() - 1;
    }

    int FindBestSibling(const AABB& bounds) {
        // 简化实现：从根开始，选择使合并后表面积增加最小的分支
        int current = root;
        while (!nodes[current].isLeaf) {
            float areaLeft = AABB::Merge(bounds, nodes[nodes[current].left].bounds).SurfaceArea();
            float areaRight = AABB::Merge(bounds, nodes[nodes[current].right].bounds).SurfaceArea();
            current = (areaLeft < areaRight) ? nodes[current].left : nodes[current].right;
        }
        return current;
    }

    void InsertLeaf(int leaf, int sibling) {
        // 创建新的内部节点，将 leaf 和 sibling 作为子节点
        int parent = AllocateNode();
        nodes[parent].bounds = AABB::Merge(nodes[leaf].bounds, nodes[sibling].bounds);
        nodes[parent].isLeaf = false;
        nodes[parent].left = leaf;
        nodes[parent].right = sibling;
        nodes[parent].parent = nodes[sibling].parent;

        int oldParent = nodes[sibling].parent;
        nodes[leaf].parent = parent;
        nodes[sibling].parent = parent;

        if (oldParent == -1) {
            root = parent;
        } else {
            if (nodes[oldParent].left == sibling) {
                nodes[oldParent].left = parent;
            } else {
                nodes[oldParent].right = parent;
            }
            // 向上更新包围盒
            Refit(parent);
        }
    }

    void RemoveLeaf(int leaf) {
        if (leaf == root) {
            root = -1;
            return;
        }
        int parent = nodes[leaf].parent;
        int grandParent = nodes[parent].parent;
        int sibling = (nodes[parent].left == leaf) ? nodes[parent].right : nodes[parent].left;

        if (grandParent != -1) {
            nodes[sibling].parent = grandParent;
            if (nodes[grandParent].left == parent) {
                nodes[grandParent].left = sibling;
            } else {
                nodes[grandParent].right = sibling;
            }
            Refit(grandParent);
        } else {
            root = sibling;
            nodes[sibling].parent = -1;
        }

        // 回收父节点
        nodes[parent].parent = freeList;
        freeList = parent;
    }

    void Refit(int nodeId) {
        while (nodeId != -1) {
            auto& node = nodes[nodeId];
            if (!node.isLeaf) {
                node.bounds = AABB::Merge(nodes[node.left].bounds, nodes[node.right].bounds);
            }
            nodeId = node.parent;
        }
    }
};
```

#### 1.12 Broad Phase vs Narrow Phase

```
+------------------+
|   所有物体对      |  N 个物体 => N*(N-1)/2 对
|  (N=1000 => ~50万)|
+------------------+
         |
         v
+------------------+
|   Broad Phase     |  快速排除：空间划分 + 包围体测试
|  (O(N log N))    |
+------------------+
         |
         v
+------------------+
|  潜在碰撞对       |  可能碰撞的物体对（通常 < 1%）
|  (通常几百对)     |
+------------------+
         |
         v
+------------------+
|   Narrow Phase   |  精确几何测试：GJK/SAT/EPA
|  (O(M), M=对数)  |
+------------------+
         |
         v
+------------------+
|   碰撞响应        |  生成接触信息，应用冲量
+------------------+
```

---

## 2. 代码示例

### 2.1 基础数学工具

```cpp
// ============================================================================
// 基础数学工具 (Vec3, Mat3)
// ============================================================================

#include <cmath>
#include <algorithm>
#include <vector>
#include <array>
#include <limits>
#include <iostream>

struct Vec3 {
    float x, y, z;

    Vec3() : x(0), y(0), z(0) {}
    Vec3(float x, float y, float z) : x(x), y(y), z(z) {}

    Vec3 operator+(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x - o.x, y - o.y, z - o.z); }
    Vec3 operator*(float s) const { return Vec3(x * s, y * s, z * s); }
    Vec3 operator/(float s) const { return Vec3(x / s, y / s, z / s); }
    Vec3 operator-() const { return Vec3(-x, -y, -z); }

    Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
    Vec3& operator-=(const Vec3& o) { x -= o.x; y -= o.y; z -= o.z; return *this; }

    float LengthSq() const { return x * x + y * y + z * z; }
    float Length() const { return std::sqrt(LengthSq()); }

    Vec3 Normalized() const {
        float len = Length();
        if (len > 1e-6f) return *this / len;
        return Vec3(0, 0, 0);
    }

    void Normalize() {
        float len = Length();
        if (len > 1e-6f) { x /= len; y /= len; z /= len; }
    }
};

inline Vec3 operator*(float s, const Vec3& v) { return v * s; }

inline float Dot(const Vec3& a, const Vec3& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

inline Vec3 Cross(const Vec3& a, const Vec3& b) {
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    );
}

inline Vec3 Abs(const Vec3& v) {
    return Vec3(std::abs(v.x), std::abs(v.y), std::abs(v.z));
}

inline Vec3 Max(const Vec3& a, const Vec3& b) {
    return Vec3(std::max(a.x, b.x), std::max(a.y, b.y), std::max(a.z, b.z));
}

inline Vec3 Min(const Vec3& a, const Vec3& b) {
    return Vec3(std::min(a.x, b.x), std::min(a.y, b.y), std::min(a.z, b.z));
}

// 3x3 矩阵（用于 OBB 的轴）
struct Mat3 {
    Vec3 cols[3];

    Mat3() {}
    Mat3(const Vec3& c0, const Vec3& c1, const Vec3& c2) {
        cols[0] = c0; cols[1] = c1; cols[2] = c2;
    }

    Vec3 operator*(const Vec3& v) const {
        return cols[0] * v.x + cols[1] * v.y + cols[2] * v.z;
    }

    Vec3 Row(int i) const {
        return Vec3(cols[0].x, cols[1].x, cols[2].x);
    }
};

inline Vec3 operator*(const Mat3& m, const Vec3& v) {
    return m * v;
}
```

### 2.2 包围体定义

```cpp
// ============================================================================
// 包围体定义
// ============================================================================

struct AABB {
    Vec3 min;
    Vec3 max;

    AABB() : min(0, 0, 0), max(0, 0, 0) {}
    AABB(const Vec3& min, const Vec3& max) : min(min), max(max) {}

    Vec3 Center() const { return (min + max) * 0.5f; }
    Vec3 Extents() const { return (max - min) * 0.5f; }

    // 从点集构建 AABB
    static AABB FromPoints(const Vec3* points, int count) {
        Vec3 mn(points[0]), mx(points[0]);
        for (int i = 1; i < count; ++i) {
            mn = Min(mn, points[i]);
            mx = Max(mx, points[i]);
        }
        return AABB(mn, mx);
    }

    // 扩展 AABB 以包含一个点
    void Expand(const Vec3& p) {
        min = Min(min, p);
        max = Max(max, p);
    }

    // 合并两个 AABB
    static AABB Merge(const AABB& a, const AABB& b) {
        return AABB(Min(a.min, b.min), Max(a.max, b.max));
    }

    float SurfaceArea() const {
        Vec3 e = max - min;
        return 2.0f * (e.x * e.y + e.y * e.z + e.z * e.x);
    }
};

struct Sphere {
    Vec3 center;
    float radius;

    Sphere() : center(0, 0, 0), radius(0) {}
    Sphere(const Vec3& c, float r) : center(c), radius(r) {}
};

struct OBB {
    Vec3 center;
    Vec3 axes[3];      // 局部坐标轴（单位向量）
    Vec3 halfExtents;  // 半轴长度

    OBB() : center(0, 0, 0), halfExtents(0, 0, 0) {
        axes[0] = Vec3(1, 0, 0);
        axes[1] = Vec3(0, 1, 0);
        axes[2] = Vec3(0, 0, 1);
    }

    OBB(const Vec3& c, const Vec3 ax[3], const Vec3& he)
        : center(c), halfExtents(he) {
        axes[0] = ax[0]; axes[1] = ax[1]; axes[2] = ax[2];
    }

    // 将局部坐标转换为世界坐标
    Vec3 LocalToWorld(const Vec3& local) const {
        return center +
               axes[0] * local.x +
               axes[1] * local.y +
               axes[2] * local.z;
    }

    // 将世界坐标转换为局部坐标
    Vec3 WorldToLocal(const Vec3& world) const {
        Vec3 d = world - center;
        return Vec3(Dot(d, axes[0]), Dot(d, axes[1]), Dot(d, axes[2]));
    }
};

struct Capsule {
    Vec3 a;       // 线段起点
    Vec3 b;       // 线段终点
    float radius; // 半径

    Capsule() : a(0, 0, 0), b(0, 0, 0), radius(0) {}
    Capsule(const Vec3& a, const Vec3& b, float r) : a(a), b(b), radius(r) {}

    Vec3 Center() const { return (a + b) * 0.5f; }
    float Height() const { return (b - a).Length(); }
    Vec3 Axis() const { return (b - a).Normalized(); }
};

struct Ray {
    Vec3 origin;
    Vec3 direction; // 必须是单位向量

    Ray() : origin(0, 0, 0), direction(0, 0, 1) {}
    Ray(const Vec3& o, const Vec3& d) : origin(o), direction(d.Normalized()) {}

    Vec3 At(float t) const { return origin + direction * t; }
};

struct HitResult {
    bool hit;
    float t;        // 射线参数（沿射线的距离）
    Vec3 point;     // 碰撞点
    Vec3 normal;    // 碰撞法线

    HitResult() : hit(false), t(std::numeric_limits<float>::max()) {}
};
```

### 2.3 AABB 碰撞检测

```cpp
// ============================================================================
// AABB 碰撞检测
// ============================================================================

// AABB-AABB 相交测试
bool AABBIntersect(const AABB& a, const AABB& b) {
    return (a.max.x >= b.min.x && a.min.x <= b.max.x) &&
           (a.max.y >= b.min.y && a.min.y <= b.max.y) &&
           (a.max.z >= b.min.z && a.min.z <= b.max.z);
}

// AABB-AABB 相交测试 + 穿透信息（MTV - Minimum Translation Vector）
bool AABBIntersect(const AABB& a, const AABB& b, Vec3& mtv) {
    // 检查是否相交
    if (!AABBIntersect(a, b)) {
        return false;
    }

    // 计算每个轴上的重叠量
    float overlapX = std::min(a.max.x - b.min.x, b.max.x - a.min.x);
    float overlapY = std::min(a.max.y - b.min.y, b.max.y - a.min.y);
    float overlapZ = std::min(a.max.z - b.min.z, b.max.z - a.min.z);

    // MTV 是重叠最小的轴
    if (overlapX <= overlapY && overlapX <= overlapZ) {
        mtv = Vec3(overlapX, 0, 0);
        // 确定方向（从 b 指向 a）
        if (a.Center().x < b.Center().x) mtv.x = -mtv.x;
    } else if (overlapY <= overlapZ) {
        mtv = Vec3(0, overlapY, 0);
        if (a.Center().y < b.Center().y) mtv.y = -mtv.y;
    } else {
        mtv = Vec3(0, 0, overlapZ);
        if (a.Center().z < b.Center().z) mtv.z = -mtv.z;
    }

    return true;
}

// AABB-Sphere 相交测试
bool AABBSphereIntersect(const AABB& aabb, const Sphere& sphere) {
    // 找到 AABB 上离球心最近的点
    Vec3 closest;
    closest.x = std::max(aabb.min.x, std::min(sphere.center.x, aabb.max.x));
    closest.y = std::max(aabb.min.y, std::min(sphere.center.y, aabb.max.y));
    closest.z = std::max(aabb.min.z, std::min(sphere.center.z, aabb.max.z));

    // 计算该点到球心的距离
    Vec3 diff = closest - sphere.center;
    float distSq = diff.LengthSq();

    return distSq <= sphere.radius * sphere.radius;
}

// 测试 AABB 函数
void TestAABB() {
    std::cout << "=== AABB Tests ===" << std::endl;

    AABB a(Vec3(0, 0, 0), Vec3(2, 2, 2));
    AABB b(Vec3(1, 1, 1), Vec3(3, 3, 3));
    AABB c(Vec3(5, 5, 5), Vec3(6, 6, 6));

    std::cout << "AABB-AABB (intersecting): " << AABBIntersect(a, b) << " (expected: 1)" << std::endl;
    std::cout << "AABB-AABB (separate): " << AABBIntersect(a, c) << " (expected: 0)" << std::endl;

    Vec3 mtv;
    if (AABBIntersect(a, b, mtv)) {
        std::cout << "MTV: (" << mtv.x << ", " << mtv.y << ", " << mtv.z << ")" << std::endl;
    }

    Sphere s(Vec3(3, 3, 3), 2);
    std::cout << "AABB-Sphere (intersecting): " << AABBSphereIntersect(a, s) << " (expected: 1)" << std::endl;
}
```

### 2.4 Sphere 碰撞检测

```cpp
// ============================================================================
// Sphere 碰撞检测
// ============================================================================

// Sphere-Sphere 相交测试
bool SphereIntersect(const Sphere& a, const Sphere& b) {
    Vec3 diff = a.center - b.center;
    float distSq = diff.LengthSq();
    float radiusSum = a.radius + b.radius;
    return distSq <= radiusSum * radiusSum;
}

// Sphere-Sphere 相交测试 + 接触信息
bool SphereIntersect(const Sphere& a, const Sphere& b, Vec3& normal, float& penetration) {
    Vec3 diff = a.center - b.center;
    float distSq = diff.LengthSq();
    float radiusSum = a.radius + b.radius;

    if (distSq > radiusSum * radiusSum || distSq < 1e-6f) {
        return false;
    }

    float dist = std::sqrt(distSq);
    normal = diff / dist;  // 从 b 指向 a
    penetration = radiusSum - dist;
    return true;
}

// Sphere-OBB 相交测试
bool SphereOBBIntersect(const Sphere& sphere, const OBB& obb) {
    // 将球心转换到 OBB 的局部坐标系
    Vec3 localCenter = obb.WorldToLocal(sphere.center);

    // 在局部坐标系中，OBB 是 AABB(-halfExtents, +halfExtents)
    // 找到 AABB 上离局部球心最近的点
    Vec3 closest;
    closest.x = std::max(-obb.halfExtents.x, std::min(localCenter.x, obb.halfExtents.x));
    closest.y = std::max(-obb.halfExtents.y, std::min(localCenter.y, obb.halfExtents.y));
    closest.z = std::max(-obb.halfExtents.z, std::min(localCenter.z, obb.halfExtents.z));

    // 计算距离
    Vec3 diff = closest - localCenter;
    return diff.LengthSq() <= sphere.radius * sphere.radius;
}

// 测试 Sphere 函数
void TestSphere() {
    std::cout << "\n=== Sphere Tests ===" << std::endl;

    Sphere a(Vec3(0, 0, 0), 2);
    Sphere b(Vec3(3, 0, 0), 2);
    Sphere c(Vec3(10, 0, 0), 1);

    std::cout << "Sphere-Sphere (intersecting): " << SphereIntersect(a, b) << " (expected: 1)" << std::endl;
    std::cout << "Sphere-Sphere (separate): " << SphereIntersect(a, c) << " (expected: 0)" << std::endl;

    Vec3 normal;
    float penetration;
    if (SphereIntersect(a, b, normal, penetration)) {
        std::cout << "Normal: (" << normal.x << ", " << normal.y << ", " << normal.z << ")" << std::endl;
        std::cout << "Penetration: " << penetration << std::endl;
    }
}
```

### 2.5 OBB 碰撞检测（SAT）

```cpp
// ============================================================================
// OBB 碰撞检测 - 分离轴定理（SAT）
// ============================================================================

// 计算 OBB 在轴 L 上的投影半径
float OBBProjectRadius(const OBB& obb, const Vec3& L) {
    return obb.halfExtents.x * std::abs(Dot(obb.axes[0], L)) +
           obb.halfExtents.y * std::abs(Dot(obb.axes[1], L)) +
           obb.halfExtents.z * std::abs(Dot(obb.axes[2], L));
}

// SAT 测试两个 OBB 在指定轴上是否分离
// 返回 true 表示在该轴上重叠（不分离）
bool SATTestAxis(const OBB& a, const OBB& b, const Vec3& axis,
                 float& overlap, Vec3& axisOut) {
    // 跳过零长度轴
    float axisLenSq = axis.LengthSq();
    if (axisLenSq < 1e-6f) {
        overlap = std::numeric_limits<float>::max();
        return true;  // 视为重叠
    }

    Vec3 L = axis / std::sqrt(axisLenSq);

    // 计算中心在轴上的投影距离
    Vec3 d = b.center - a.center;
    float dist = std::abs(Dot(d, L));

    // 计算两个 OBB 在该轴上的投影半径之和
    float rA = OBBProjectRadius(a, L);
    float rB = OBBProjectRadius(b, L);

    if (dist > rA + rB) {
        return false;  // 分离！
    }

    // 记录重叠量
    overlap = rA + rB - dist;
    axisOut = L;
    return true;
}

// OBB-OBB 相交测试（完整 SAT）
bool OBBIntersect(const OBB& a, const OBB& b, Vec3& mtv) {
    float minOverlap = std::numeric_limits<float>::max();
    Vec3 minAxis;

    // 需要测试的 15 个轴
    // A 的 3 个轴
    Vec3 axes[15];
    axes[0] = a.axes[0];
    axes[1] = a.axes[1];
    axes[2] = a.axes[2];
    // B 的 3 个轴
    axes[3] = b.axes[0];
    axes[4] = b.axes[1];
    axes[5] = b.axes[2];
    // 9 个叉积轴
    axes[6] = Cross(a.axes[0], b.axes[0]);
    axes[7] = Cross(a.axes[0], b.axes[1]);
    axes[8] = Cross(a.axes[0], b.axes[2]);
    axes[9] = Cross(a.axes[1], b.axes[0]);
    axes[10] = Cross(a.axes[1], b.axes[1]);
    axes[11] = Cross(a.axes[1], b.axes[2]);
    axes[12] = Cross(a.axes[2], b.axes[0]);
    axes[13] = Cross(a.axes[2], b.axes[1]);
    axes[14] = Cross(a.axes[2], b.axes[2]);

    for (int i = 0; i < 15; ++i) {
        float overlap;
        Vec3 axis;
        if (!SATTestAxis(a, b, axes[i], overlap, axis)) {
            return false;  // 找到分离轴，不相交
        }

        // 记录最小重叠轴
        if (overlap < minOverlap) {
            minOverlap = overlap;
            minAxis = axis;
        }
    }

    // 所有轴都重叠，相交
    // 确保 MTV 方向正确（从 b 指向 a）
    Vec3 d = b.center - a.center;
    if (Dot(d, minAxis) < 0) {
        minAxis = -minAxis;
    }
    mtv = minAxis * minOverlap;

    return true;
}

// 测试 OBB 函数
void TestOBB() {
    std::cout << "\n=== OBB Tests ===" << std::endl;

    OBB a;
    a.center = Vec3(0, 0, 0);
    a.halfExtents = Vec3(1, 1, 1);

    OBB b;
    b.center = Vec3(1.5f, 0, 0);
    b.halfExtents = Vec3(1, 1, 1);

    Vec3 mtv;
    std::cout << "OBB-OBB (intersecting): " << OBBIntersect(a, b, mtv) << " (expected: 1)" << std::endl;
    if (mtv.LengthSq() > 0) {
        std::cout << "MTV: (" << mtv.x << ", " << mtv.y << ", " << mtv.z << ")" << std::endl;
    }

    // 旋转的 OBB
    OBB c;
    c.center = Vec3(5, 0, 0);
    c.halfExtents = Vec3(1, 1, 1);
    float angle = 3.14159f / 4;  // 45 度
    c.axes[0] = Vec3(std::cos(angle), std::sin(angle), 0);
    c.axes[1] = Vec3(-std::sin(angle), std::cos(angle), 0);
    c.axes[2] = Vec3(0, 0, 1);

    std::cout << "OBB-OBB (rotated, separate): " << OBBIntersect(a, c, mtv) << " (expected: 0)" << std::endl;
}
```

### 2.6 Capsule 碰撞检测

```cpp
// ============================================================================
// Capsule 碰撞检测
// ============================================================================

// 计算点到线段的最近点
Vec3 ClosestPointOnSegment(const Vec3& p, const Vec3& a, const Vec3& b) {
    Vec3 ab = b - a;
    Vec3 ap = p - a;

    float t = Dot(ap, ab) / ab.LengthSq();
    t = std::max(0.0f, std::min(1.0f, t));

    return a + ab * t;
}

// 计算两条线段之间的最近点
// 返回 (closestA, closestB)
std::pair<Vec3, Vec3> ClosestPointsOnSegments(const Vec3& a1, const Vec3& a2,
                                               const Vec3& b1, const Vec3& b2) {
    Vec3 d1 = a2 - a1;  // A 线段方向
    Vec3 d2 = b2 - b1;  // B 线段方向
    Vec3 r = a1 - b1;

    float a = d1.LengthSq();
    float e = d2.LengthSq();
    float f = Dot(d2, r);

    float s, t;

    if (a <= 1e-6f && e <= 1e-6f) {
        // 两条线段都退化为点
        s = t = 0.0f;
        return {a1, b1};
    }

    if (a <= 1e-6f) {
        // A 退化为点
        s = 0.0f;
        t = f / e;
        t = std::max(0.0f, std::min(1.0f, t));
    } else {
        float c = Dot(d1, r);
        if (e <= 1e-6f) {
            // B 退化为点
            t = 0.0f;
            s = std::max(0.0f, std::min(1.0f, -c / a));
        } else {
            float b = Dot(d1, d2);
            float denom = a * e - b * b;

            if (denom != 0.0f) {
                s = std::max(0.0f, std::min(1.0f, (b * f - c * e) / denom));
            } else {
                s = 0.0f;
            }

            t = (b * s + f) / e;

            if (t < 0.0f) {
                t = 0.0f;
                s = std::max(0.0f, std::min(1.0f, -c / a));
            } else if (t > 1.0f) {
                t = 1.0f;
                s = std::max(0.0f, std::min(1.0f, (b - c) / a));
            }
        }
    }

    return {a1 + d1 * s, b1 + d2 * t};
}

// Capsule-Capsule 相交测试
bool CapsuleIntersect(const Capsule& a, const Capsule& b) {
    auto [closestA, closestB] = ClosestPointsOnSegments(a.a, a.b, b.a, b.b);
    Vec3 diff = closestA - closestB;
    float radiusSum = a.radius + b.radius;
    return diff.LengthSq() <= radiusSum * radiusSum;
}

// Capsule-Capsule 相交测试 + 接触信息
bool CapsuleIntersect(const Capsule& a, const Capsule& b,
                      Vec3& normal, float& penetration) {
    auto [closestA, closestB] = ClosestPointsOnSegments(a.a, a.b, b.a, b.b);
    Vec3 diff = closestA - closestB;
    float distSq = diff.LengthSq();
    float radiusSum = a.radius + b.radius;

    if (distSq > radiusSum * radiusSum || distSq < 1e-6f) {
        return false;
    }

    float dist = std::sqrt(distSq);
    normal = diff / dist;
    penetration = radiusSum - dist;
    return true;
}

// 测试 Capsule 函数
void TestCapsule() {
    std::cout << "\n=== Capsule Tests ===" << std::endl;

    Capsule a(Vec3(0, 0, 0), Vec3(0, 5, 0), 1);
    Capsule b(Vec3(2, 2, 0), Vec3(2, 4, 0), 1);
    Capsule c(Vec3(10, 0, 0), Vec3(10, 5, 0), 1);

    std::cout << "Capsule-Capsule (intersecting): " << CapsuleIntersect(a, b) << " (expected: 1)" << std::endl;
    std::cout << "Capsule-Capsule (separate): " << CapsuleIntersect(a, c) << " (expected: 0)" << std::endl;

    Vec3 normal;
    float penetration;
    if (CapsuleIntersect(a, b, normal, penetration)) {
        std::cout << "Normal: (" << normal.x << ", " << normal.y << ", " << normal.z << ")" << std::endl;
        std::cout << "Penetration: " << penetration << std::endl;
    }
}
```

### 2.7 射线相交检测

```cpp
// ============================================================================
// 射线相交检测
// ============================================================================

// Ray-AABB 相交（Slab 方法）
bool RayAABBIntersect(const Ray& ray, const AABB& aabb, float& tMin, float& tMax) {
    tMin = 0.0f;
    tMax = std::numeric_limits<float>::max();

    for (int i = 0; i < 3; ++i) {
        float invD = 1.0f / (&ray.direction.x)[i];
        float t0 = ((&aabb.min.x)[i] - (&ray.origin.x)[i]) * invD;
        float t1 = ((&aabb.max.x)[i] - (&ray.origin.x)[i]) * invD;

        if (invD < 0.0f) {
            std::swap(t0, t1);
        }

        tMin = std::max(tMin, t0);
        tMax = std::min(tMax, t1);

        if (tMax < tMin) {
            return false;
        }
    }

    return tMax >= 0.0f;
}

// Ray-AABB 相交（完整版，返回 HitResult）
HitResult RayAABBIntersect(const Ray& ray, const AABB& aabb) {
    HitResult result;
    float tMin, tMax;

    if (!RayAABBIntersect(ray, aabb, tMin, tMax)) {
        return result;
    }

    float t = (tMin >= 0.0f) ? tMin : tMax;
    if (t < 0.0f) {
        return result;
    }

    result.hit = true;
    result.t = t;
    result.point = ray.At(t);

    // 计算法线（根据命中的面）
    Vec3 center = aabb.Center();
    Vec3 p = result.point - center;
    Vec3 extents = aabb.Extents();

    float bias = 1.0001f;
    if (std::abs(p.x) * bias >= std::abs(p.y) && std::abs(p.x) * bias >= std::abs(p.z)) {
        result.normal = Vec3(p.x > 0 ? 1.0f : -1.0f, 0, 0);
    } else if (std::abs(p.y) * bias >= std::abs(p.z)) {
        result.normal = Vec3(0, p.y > 0 ? 1.0f : -1.0f, 0);
    } else {
        result.normal = Vec3(0, 0, p.z > 0 ? 1.0f : -1.0f);
    }

    return result;
}

// Ray-Sphere 相交
HitResult RaySphereIntersect(const Ray& ray, const Sphere& sphere) {
    HitResult result;

    Vec3 oc = ray.origin - sphere.center;
    float a = Dot(ray.direction, ray.direction);  // = 1 (方向已归一化)
    float b = 2.0f * Dot(oc, ray.direction);
    float c = oc.LengthSq() - sphere.radius * sphere.radius;

    float discriminant = b * b - 4.0f * a * c;

    if (discriminant < 0.0f) {
        return result;  // 不相交
    }

    float sqrtD = std::sqrt(discriminant);
    float t = (-b - sqrtD) / (2.0f * a);

    if (t < 0.0f) {
        t = (-b + sqrtD) / (2.0f * a);
        if (t < 0.0f) {
            return result;  // 交点在射线后方
        }
    }

    result.hit = true;
    result.t = t;
    result.point = ray.At(t);
    result.normal = (result.point - sphere.center).Normalized();

    return result;
}

// Ray-Triangle 相交（Möller-Trumbore 算法）
HitResult RayTriangleIntersect(const Ray& ray,
                                const Vec3& v0, const Vec3& v1, const Vec3& v2) {
    HitResult result;

    const float EPSILON = 1e-6f;

    Vec3 e1 = v1 - v0;
    Vec3 e2 = v2 - v0;
    Vec3 h = Cross(ray.direction, e2);
    float a = Dot(e1, h);

    if (a > -EPSILON && a < EPSILON) {
        return result;  // 射线与三角形平行
    }

    float f = 1.0f / a;
    Vec3 s = ray.origin - v0;
    float u = f * Dot(s, h);

    if (u < 0.0f || u > 1.0f) {
        return result;
    }

    Vec3 q = Cross(s, e1);
    float v = f * Dot(ray.direction, q);

    if (v < 0.0f || u + v > 1.0f) {
        return result;
    }

    float t = f * Dot(e2, q);

    if (t > EPSILON) {
        result.hit = true;
        result.t = t;
        result.point = ray.At(t);
        result.normal = Cross(e1, e2).Normalized();
        return result;
    }

    return result;  // 交点在射线后方
}

// 测试射线相交
void TestRay() {
    std::cout << "\n=== Ray Tests ===" << std::endl;

    Ray ray(Vec3(0, 0, -5), Vec3(0, 0, 1));

    AABB aabb(Vec3(-1, -1, -1), Vec3(1, 1, 1));
    auto hitAABB = RayAABBIntersect(ray, aabb);
    std::cout << "Ray-AABB: " << hitAABB.hit << " t=" << hitAABB.t
              << " point=(" << hitAABB.point.x << ", " << hitAABB.point.y << ", " << hitAABB.point.z << ")" << std::endl;

    Sphere sphere(Vec3(0, 0, 0), 2);
    auto hitSphere = RaySphereIntersect(ray, sphere);
    std::cout << "Ray-Sphere: " << hitSphere.hit << " t=" << hitSphere.t
              << " point=(" << hitSphere.point.x << ", " << hitSphere.point.y << ", " << hitSphere.point.z << ")" << std::endl;

    Vec3 v0(2, -1, 0), v1(2, 1, 0), v2(2, 0, 1);
    Ray ray2(Vec3(0, 0, 0), Vec3(1, 0, 0));
    auto hitTri = RayTriangleIntersect(ray2, v0, v1, v2);
    std::cout << "Ray-Triangle: " << hitTri.hit << " t=" << hitTri.t
              << " point=(" << hitTri.point.x << ", " << hitTri.point.y << ", " << hitTri.point.z << ")" << std::endl;
}
```

### 2.8 GJK 算法完整实现

```cpp
// ============================================================================
// GJK 算法（Gilbert-Johnson-Keerthi）
// ============================================================================

// 支持函数接口
struct Supportable {
    virtual Vec3 Support(const Vec3& direction) const = 0;
    virtual ~Supportable() = default;
};

// 球体的支持函数
struct SphereSupportable : Supportable {
    Sphere sphere;
    SphereSupportable(const Sphere& s) : sphere(s) {}

    Vec3 Support(const Vec3& direction) const override {
        return sphere.center + direction.Normalized() * sphere.radius;
    }
};

// AABB 的支持函数
struct AABBSupportable : Supportable {
    AABB aabb;
    AABBSupportable(const AABB& a) : aabb(a) {}

    Vec3 Support(const Vec3& direction) const override {
        return Vec3(
            direction.x >= 0 ? aabb.max.x : aabb.min.x,
            direction.y >= 0 ? aabb.max.y : aabb.min.y,
            direction.z >= 0 ? aabb.max.z : aabb.min.z
        );
    }
};

// OBB 的支持函数
struct OBBSupportable : Supportable {
    OBB obb;
    OBBSupportable(const OBB& o) : obb(o) {}

    Vec3 Support(const Vec3& direction) const override {
        // 在世界坐标系中，OBB 的支持点是：
        // center + sum(sign(dot(axis_i, d)) * halfExtent_i * axis_i)
        Vec3 result = obb.center;
        for (int i = 0; i < 3; ++i) {
            float proj = Dot(obb.axes[i], direction);
            if (proj >= 0) {
                result += obb.axes[i] * obb.halfExtents[i];
            } else {
                result -= obb.axes[i] * obb.halfExtents[i];
            }
        }
        return result;
    }
};

// 凸包的支持函数（点集）
struct ConvexHullSupportable : Supportable {
    std::vector<Vec3> vertices;
    ConvexHullSupportable(const std::vector<Vec3>& verts) : vertices(verts) {}

    Vec3 Support(const Vec3& direction) const override {
        float maxDot = -std::numeric_limits<float>::max();
        Vec3 best;
        for (const auto& v : vertices) {
            float d = Dot(v, direction);
            if (d > maxDot) {
                maxDot = d;
                best = v;
            }
        }
        return best;
    }
};

// Minkowski 差的支持函数
Vec3 MinkowskiSupport(const Supportable& shapeA, const Supportable& shapeB,
                      const Vec3& direction) {
    return shapeA.Support(direction) - shapeB.Support(-direction);
}

// GJK 单纯形
struct Simplex {
    Vec3 points[4];
    int count;

    Simplex() : count(0) {}

    void Push(const Vec3& p) {
        // 将新点移到前面
        for (int i = count; i > 0; --i) {
            points[i] = points[i - 1];
        }
        points[0] = p;
        count = std::min(count + 1, 4);
    }

    Vec3& operator[](int i) { return points[i]; }
    const Vec3& operator[](int i) const { return points[i]; }
};

// 2D 单纯形处理（线段）
// 返回 true 表示原点在单纯形中，false 表示需要新的方向
bool LineSimplex(Vec3& a, Vec3& b, Vec3& direction) {
    Vec3 ab = b - a;
    Vec3 ao = -a;  // 从 a 指向原点

    // 检查原点在 ab 的哪一侧
    if (Dot(ab, ao) > 0) {
        // 原点在 ab 的垂直平分线靠近 a 的一侧
        // 新方向是 ab × ao × ab（指向原点的垂直于 ab 的方向）
        direction = Cross(Cross(ab, ao), ab);
    } else {
        // 原点在 a 的"另一侧"，只用 a
        b = a;
        direction = ao;
    }
    return false;
}

// 三角形单纯形处理
bool TriangleSimplex(Vec3& a, Vec3& b, Vec3& c, Vec3& direction) {
    Vec3 ab = b - a;
    Vec3 ac = c - a;
    Vec3 ao = -a;

    Vec3 abc = Cross(ab, ac);  // 三角形法线

    // 检查原点在三角形的哪个 Voronoi 区域
    Vec3 acPerp = Cross(abc, ac);
    if (Dot(acPerp, ao) > 0) {
        // 原点在 ac 边的外侧
        b = a;
        c = a;
        direction = Cross(Cross(ac, ao), ac);
        return false;
    }

    Vec3 abPerp = Cross(ab, abc);
    if (Dot(abPerp, ao) > 0) {
        // 原点在 ab 边的外侧
        c = b;
        b = a;
        direction = Cross(Cross(ab, ao), ab);
        return false;
    }

    // 原点在三角形内部（或上方/下方）
    // 检查是在法线的哪一侧
    if (Dot(abc, ao) > 0) {
        direction = abc;  // 法线方向
    } else {
        // 交换 b 和 c，使法线指向原点
        Vec3 temp = b;
        b = c;
        c = temp;
        direction = -abc;
    }
    return false;
}

// 四面体单纯形处理
bool TetrahedronSimplex(Simplex& simplex, Vec3& direction) {
    Vec3 a = simplex[0];
    Vec3 b = simplex[1];
    Vec3 c = simplex[2];
    Vec3 d = simplex[3];

    Vec3 ab = b - a;
    Vec3 ac = c - a;
    Vec3 ad = d - a;
    Vec3 ao = -a;

    Vec3 abc = Cross(ab, ac);
    Vec3 acd = Cross(ac, ad);
    Vec3 adb = Cross(ad, ab);

    // 检查原点在哪个面的外侧
    if (Dot(abc, ao) > 0) {
        // 原点在 abc 面的外侧
        simplex.count = 3;
        simplex[0] = a;
        simplex[1] = b;
        simplex[2] = c;
        return TriangleSimplex(simplex[0], simplex[1], simplex[2], direction);
    }

    if (Dot(acd, ao) > 0) {
        // 原点在 acd 面的外侧
        simplex.count = 3;
        simplex[0] = a;
        simplex[1] = c;
        simplex[2] = d;
        return TriangleSimplex(simplex[0], simplex[1], simplex[2], direction);
    }

    if (Dot(adb, ao) > 0) {
        // 原点在 adb 面的外侧
        simplex.count = 3;
        simplex[0] = a;
        simplex[1] = d;
        simplex[2] = b;
        return TriangleSimplex(simplex[0], simplex[1], simplex[2], direction);
    }

    // 原点在四面体内部！
    return true;
}

// GJK 主算法
bool GJK(const Supportable& shapeA, const Supportable& shapeB) {
    const int MAX_ITERATIONS = 32;
    const float EPSILON = 1e-6f;

    // 初始方向
    Vec3 direction = Vec3(1, 0, 0);

    // 获取第一个支持点
    Vec3 support = MinkowskiSupport(shapeA, shapeB, direction);

    Simplex simplex;
    simplex.Push(support);

    // 新方向指向原点
    direction = -support;

    for (int iter = 0; iter < MAX_ITERATIONS; ++iter) {
        support = MinkowskiSupport(shapeA, shapeB, direction);

        // 检查新支持点是否越过原点
        if (Dot(support, direction) < EPSILON) {
            // 无法更接近原点，不相交
            return false;
        }

        simplex.Push(support);

        // 处理单纯形
        bool containsOrigin = false;
        if (simplex.count == 2) {
            containsOrigin = LineSimplex(simplex[0], simplex[1], direction);
        } else if (simplex.count == 3) {
            containsOrigin = TriangleSimplex(simplex[0], simplex[1], simplex[2], direction);
        } else if (simplex.count == 4) {
            containsOrigin = TetrahedronSimplex(simplex, direction);
        }

        if (containsOrigin) {
            return true;  // 原点在 Minkowski 差内，相交！
        }
    }

    // 达到最大迭代次数，视为相交（保守估计）
    return true;
}

// 测试 GJK
void TestGJK() {
    std::cout << "\n=== GJK Tests ===" << std::endl;

    // 测试两个相交的 AABB
    AABB aabb1(Vec3(-1, -1, -1), Vec3(1, 1, 1));
    AABB aabb2(Vec3(0.5f, 0.5f, 0.5f), Vec3(2, 2, 2));
    AABBSupportable s1(aabb1), s2(aabb2);
    std::cout << "GJK AABB-AABB (intersecting): " << GJK(s1, s2) << " (expected: 1)" << std::endl;

    // 测试两个不相交的 AABB
    AABB aabb3(Vec3(5, 5, 5), Vec3(6, 6, 6));
    AABBSupportable s3(aabb3);
    std::cout << "GJK AABB-AABB (separate): " << GJK(s1, s3) << " (expected: 0)" << std::endl;

    // 测试球体
    Sphere sphere1(Vec3(0, 0, 0), 2);
    Sphere sphere2(Vec3(3, 0, 0), 2);
    Sphere sphere3(Vec3(10, 0, 0), 1);
    SphereSupportable ss1(sphere1), ss2(sphere2), ss3(sphere3);
    std::cout << "GJK Sphere-Sphere (intersecting): " << GJK(ss1, ss2) << " (expected: 1)" << std::endl;
    std::cout << "GJK Sphere-Sphere (separate): " << GJK(ss1, ss3) << " (expected: 0)" << std::endl;

    // 测试凸包（四面体）
    std::vector<Vec3> tetra1 = {
        Vec3(0, 0, 0), Vec3(2, 0, 0), Vec3(1, 2, 0), Vec3(1, 1, 2)
    };
    std::vector<Vec3> tetra2 = {
        Vec3(1, 1, 1), Vec3(3, 1, 1), Vec3(2, 3, 1), Vec3(2, 2, 3)
    };
    ConvexHullSupportable ch1(tetra1), ch2(tetra2);
    std::cout << "GJK Convex-Convex (intersecting): " << GJK(ch1, ch2) << " (expected: 1)" << std::endl;
}
```

### 2.9 EPA 算法实现

```cpp
// ============================================================================
// EPA 算法（Expanding Polytope Algorithm）
// ============================================================================

// EPA 面定义
struct EPAFace {
    Vec3 a, b, c;      // 三角形的三个顶点
    Vec3 normal;       // 法线（朝外）
    float distance;    // 原点到该面的距离
    int index;         // 在列表中的索引

    EPAFace() : distance(0), index(-1) {}
    EPAFace(const Vec3& a_, const Vec3& b_, const Vec3& c_)
        : a(a_), b(b_), c(c_) {
        normal = Cross(b - a, c - a).Normalized();
        distance = Dot(normal, a);
        if (distance < 0) {
            // 确保法线指向远离原点的方向
            normal = -normal;
            distance = -distance;
            // 交换 b 和 c 保持 winding order
            Vec3 temp = b;
            b = c;
            c = temp;
        }
    }
};

// EPA 边（用于防止重复边）
struct EPAEdge {
    Vec3 a, b;
    bool operator==(const EPAEdge& o) const {
        return (a.x == o.a.x && a.y == o.a.y && a.z == o.a.z &&
                b.x == o.b.x && b.y == o.b.y && b.z == o.b.z);
    }
};

// 查找 EPA 多面体中离原点最近的面
int FindClosestFace(const std::vector<EPAFace>& faces) {
    int closest = 0;
    for (size_t i = 1; i < faces.size(); ++i) {
        if (faces[i].distance < faces[closest].distance) {
            closest = (int)i;
        }
    }
    return closest;
}

// 检查点是否"可见"某个面（从面的外侧看）
bool IsPointVisible(const EPAFace& face, const Vec3& point) {
    return Dot(point - face.a, face.normal) > 0;
}

// EPA 主算法
// 返回 true 表示成功计算穿透信息
bool EPA(const Supportable& shapeA, const Supportable& shapeB,
         const Simplex& gjkSimplex,
         Vec3& normal, float& penetration) {
    const int MAX_ITERATIONS = 32;
    const float EPSILON = 1e-4f;

    // 从 GJK 的单纯形开始构建初始多面体
    std::vector<Vec3> polytope;
    for (int i = 0; i < gjkSimplex.count; ++i) {
        polytope.push_back(gjkSimplex[i]);
    }

    // 构建初始面列表
    std::vector<EPAFace> faces;
    if (gjkSimplex.count == 4) {
        // 四面体 - 4 个面
        faces.emplace_back(polytope[0], polytope[1], polytope[2]);
        faces.emplace_back(polytope[0], polytope[3], polytope[1]);
        faces.emplace_back(polytope[0], polytope[2], polytope[3]);
        faces.emplace_back(polytope[1], polytope[3], polytope[2]);
    } else {
        // EPA 需要至少 4 个点，如果 GJK 以更少点结束，需要额外采样
        return false;
    }

    Vec3 closestNormal;
    float closestDistance = 0;

    for (int iter = 0; iter < MAX_ITERATIONS; ++iter) {
        // 找到离原点最近的面
        int closestFaceIdx = FindClosestFace(faces);
        EPAFace& closestFace = faces[closestFaceIdx];

        // 在该面的法线方向上获取新的支持点
        Vec3 support = MinkowskiSupport(shapeA, shapeB, closestFace.normal);

        // 计算新支持点到该面的距离
        float supportDist = Dot(support, closestFace.normal);

        // 检查是否收敛
        if (supportDist - closestFace.distance < EPSILON) {
            // 收敛！
            normal = closestFace.normal;
            penetration = closestFace.distance;
            return true;
        }

        // 扩展多面体：移除所有"可见"的面，添加新边
        std::vector<EPAEdge> edges;
        std::vector<EPAFace> newFaces;

        for (size_t i = 0; i < faces.size(); ++i) {
            if (IsPointVisible(faces[i], support)) {
                // 这个面可见，需要移除，提取它的边
                EPAEdge edges_to_add[3] = {
                    {faces[i].a, faces[i].b},
                    {faces[i].b, faces[i].c},
                    {faces[i].c, faces[i].a}
                };

                for (int e = 0; e < 3; ++e) {
                    // 检查边是否已存在（反向）
                    bool found = false;
                    for (auto it = edges.begin(); it != edges.end(); ++it) {
                        if (it->a.x == edges_to_add[e].b.x &&
                            it->a.y == edges_to_add[e].b.y &&
                            it->a.z == edges_to_add[e].b.z &&
                            it->b.x == edges_to_add[e].a.x &&
                            it->b.y == edges_to_add[e].a.y &&
                            it->b.z == edges_to_add[e].a.z) {
                            edges.erase(it);
                            found = true;
                            break;
                        }
                    }
                    if (!found) {
                        edges.push_back(edges_to_add[e]);
                    }
                }
            } else {
                newFaces.push_back(faces[i]);
            }
        }

        // 用新点和边构建新面
        for (const auto& edge : edges) {
            newFaces.emplace_back(edge.a, edge.b, support);
        }

        faces = std::move(newFaces);

        if (faces.empty()) {
            return false;
        }
    }

    // 达到最大迭代次数，返回当前最佳估计
    int closestFaceIdx = FindClosestFace(faces);
    normal = faces[closestFaceIdx].normal;
    penetration = faces[closestFaceIdx].distance;
    return true;
}

// 组合 GJK + EPA 的完整碰撞检测
bool GJK_EPA(const Supportable& shapeA, const Supportable& shapeB,
             Vec3& normal, float& penetration) {
    // 先运行 GJK
    const int MAX_ITERATIONS = 32;
    const float EPSILON = 1e-6f;

    Vec3 direction = Vec3(1, 0, 0);
    Vec3 support = MinkowskiSupport(shapeA, shapeB, direction);

    Simplex simplex;
    simplex.Push(support);
    direction = -support;

    for (int iter = 0; iter < MAX_ITERATIONS; ++iter) {
        support = MinkowskiSupport(shapeA, shapeB, direction);

        if (Dot(support, direction) < EPSILON) {
            return false;  // 不相交
        }

        simplex.Push(support);

        bool containsOrigin = false;
        if (simplex.count == 2) {
            containsOrigin = LineSimplex(simplex[0], simplex[1], direction);
        } else if (simplex.count == 3) {
            containsOrigin = TriangleSimplex(simplex[0], simplex[1], simplex[2], direction);
        } else if (simplex.count == 4) {
            containsOrigin = TetrahedronSimplex(simplex, direction);
        }

        if (containsOrigin) {
            // 相交！运行 EPA 获取穿透信息
            return EPA(shapeA, shapeB, simplex, normal, penetration);
        }
    }

    return true;  // 保守估计
}

// 测试 EPA
void TestEPA() {
    std::cout << "\n=== EPA Tests ===" << std::endl;

    // 测试两个相交的球体
    Sphere sphere1(Vec3(0, 0, 0), 2);
    Sphere sphere2(Vec3(3, 0, 0), 2);
    SphereSupportable s1(sphere1), s2(sphere2);

    Vec3 normal;
    float penetration;
    if (GJK_EPA(s1, s2, normal, penetration)) {
        std::cout << "GJK+EPA Sphere-Sphere: intersecting" << std::endl;
        std::cout << "  Normal: (" << normal.x << ", " << normal.y << ", " << normal.z << ")" << std::endl;
        std::cout << "  Penetration: " << penetration << std::endl;
        // 预期：penetration = 4 - 3 = 1
    }

    // 测试两个相交的 AABB
    AABB aabb1(Vec3(-1, -1, -1), Vec3(1, 1, 1));
    AABB aabb2(Vec3(0.5f, 0, 0), Vec3(2.5f, 2, 2));
    AABBSupportable a1(aabb1), a2(aabb2);

    if (GJK_EPA(a1, a2, normal, penetration)) {
        std::cout << "GJK+EPA AABB-AABB: intersecting" << std::endl;
        std::cout << "  Normal: (" << normal.x << ", " << normal.y << ", " << normal.z << ")" << std::endl;
        std::cout << "  Penetration: " << penetration << std::endl;
    }
}
```

### 2.10 BVH（包围体层次结构）

```cpp
// ============================================================================
// BVH（Bounding Volume Hierarchy）
// ============================================================================

struct BVHNode {
    AABB bounds;
    int left;       // 左子节点索引（-1 表示叶节点）
    int right;      // 右子节点索引
    int objectId;   // 叶节点存储的物体 ID（-1 表示内部节点）

    BVHNode() : left(-1), right(-1), objectId(-1) {}
    bool IsLeaf() const { return left == -1; }
};

struct BVH {
    std::vector<BVHNode> nodes;
    int root;

    BVH() : root(-1) {}

    // 构建 BVH（自顶向下，按最长轴分割）
    void Build(const std::vector<AABB>& objectBounds) {
        nodes.clear();
        if (objectBounds.empty()) {
            root = -1;
            return;
        }

        // 创建索引数组
        std::vector<int> indices(objectBounds.size());
        for (size_t i = 0; i < indices.size(); ++i) indices[i] = (int)i;

        root = BuildRecursive(objectBounds, indices, 0, (int)indices.size());
    }

private:
    int BuildRecursive(const std::vector<AABB>& bounds,
                       std::vector<int>& indices, int start, int end) {
        int nodeIdx = (int)nodes.size();
        nodes.emplace_back();
        BVHNode& node = nodes.back();

        // 计算当前范围的包围盒
        node.bounds = bounds[indices[start]];
        for (int i = start + 1; i < end; ++i) {
            node.bounds = AABB::Merge(node.bounds, bounds[indices[i]]);
        }

        int count = end - start;

        // 如果只有一个物体，创建叶节点
        if (count == 1) {
            node.objectId = indices[start];
            return nodeIdx;
        }

        // 找到最长轴
        Vec3 extents = node.bounds.max - node.bounds.min;
        int axis = 0;
        if (extents.y > extents.x) axis = 1;
        if (extents.z > (&extents.x)[axis]) axis = 2;

        // 按中心点在最长轴上的坐标排序
        auto cmp = [&](int a, int b) {
            float ca = (&bounds[a].Center().x)[axis];
            float cb = (&bounds[b].Center().x)[axis];
            return ca < cb;
        };
        std::sort(indices.begin() + start, indices.begin() + end, cmp);

        // 中点分割
        int mid = start + count / 2;

        // 递归构建子树
        node.left = BuildRecursive(bounds, indices, start, mid);
        node.right = BuildRecursive(bounds, indices, mid, end);

        return nodeIdx;
    }

public:
    // 射线与 BVH 相交检测
    bool RayIntersect(const Ray& ray, const std::vector<AABB>& objectBounds,
                      int& hitObject, float& hitT) const {
        if (root == -1) return false;

        hitT = std::numeric_limits<float>::max();
        hitObject = -1;

        // 使用栈进行遍历
        std::array<int, 64> stack;
        int stackPtr = 0;
        stack[stackPtr++] = root;

        while (stackPtr > 0) {
            int nodeIdx = stack[--stackPtr];
            const BVHNode& node = nodes[nodeIdx];

            float tMin, tMax;
            if (!RayAABBIntersect(ray, node.bounds, tMin, tMax)) {
                continue;
            }

            if (node.IsLeaf()) {
                // 测试叶节点的物体
                auto hit = RayAABBIntersect(ray, objectBounds[node.objectId]);
                if (hit.hit && hit.t < hitT) {
                    hitT = hit.t;
                    hitObject = node.objectId;
                }
            } else {
                // 推入子节点
                if (stackPtr + 2 <= (int)stack.size()) {
                    // 优先遍历离射线起点更近的子节点
                    float leftT, rightT;
                    bool leftHit = RayAABBIntersect(ray, nodes[node.left].bounds, leftT, leftT);
                    bool rightHit = RayAABBIntersect(ray, nodes[node.right].bounds, rightT, rightT);

                    if (leftHit && rightHit) {
                        if (leftT < rightT) {
                            stack[stackPtr++] = node.right;
                            stack[stackPtr++] = node.left;
                        } else {
                            stack[stackPtr++] = node.left;
                            stack[stackPtr++] = node.right;
                        }
                    } else if (leftHit) {
                        stack[stackPtr++] = node.left;
                    } else if (rightHit) {
                        stack[stackPtr++] = node.right;
                    }
                }
            }
        }

        return hitObject != -1;
    }

    // BVH 与 AABB 的 Broad Phase 查询
    void QueryOverlap(const AABB& queryBounds,
                      const std::vector<AABB>& objectBounds,
                      std::vector<int>& results) const {
        if (root == -1) return;

        std::array<int, 64> stack;
        int stackPtr = 0;
        stack[stackPtr++] = root;

        while (stackPtr > 0) {
            int nodeIdx = stack[--stackPtr];
            const BVHNode& node = nodes[nodeIdx];

            if (!AABBIntersect(queryBounds, node.bounds)) {
                continue;
            }

            if (node.IsLeaf()) {
                if (AABBIntersect(queryBounds, objectBounds[node.objectId])) {
                    results.push_back(node.objectId);
                }
            } else {
                if (stackPtr + 2 <= (int)stack.size()) {
                    stack[stackPtr++] = node.left;
                    stack[stackPtr++] = node.right;
                }
            }
        }
    }
};

// 测试 BVH
void TestBVH() {
    std::cout << "\n=== BVH Tests ===" << std::endl;

    // 创建 100 个随机 AABB
    std::vector<AABB> objects;
    for (int i = 0; i < 100; ++i) {
        float x = (float)(i % 10) * 2.0f;
        float y = (float)(i / 10) * 2.0f;
        objects.emplace_back(Vec3(x, y, 0), Vec3(x + 1, y + 1, 1));
    }

    BVH bvh;
    bvh.Build(objects);
    std::cout << "BVH built with " << bvh.nodes.size() << " nodes" << std::endl;

    // 射线查询
    Ray ray(Vec3(-1, -1, 0.5f), Vec3(1, 1, 0));
    int hitObj;
    float hitT;
    if (bvh.RayIntersect(ray, objects, hitObj, hitT)) {
        std::cout << "Ray hit object " << hitObj << " at t=" << hitT << std::endl;
    }

    // 重叠查询
    AABB query(Vec3(5, 5, -1), Vec3(7, 7, 2));
    std::vector<int> overlaps;
    bvh.QueryOverlap(query, objects, overlaps);
    std::cout << "Query found " << overlaps.size() << " overlapping objects" << std::endl;
}
```

### 2.11 主程序入口

```cpp
// ============================================================================
// 主程序
// ============================================================================

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  碰撞检测测试套件" << std::endl;
    std::cout << "========================================" << std::endl;

    TestAABB();
    TestSphere();
    TestOBB();
    TestCapsule();
    TestRay();
    TestGJK();
    TestEPA();
    TestBVH();

    std::cout << "\n========================================" << std::endl;
    std::cout << "  所有测试完成！" << std::endl;
    std::cout << "========================================" << std::endl;

    return 0;
}
```

**运行方式:**

```bash
# 编译（使用 g++）
g++ -std=c++17 -O2 collision_detection.cpp -o collision_detection

# 运行
./collision_detection
```

**预期输出:**

```
========================================
  碰撞检测测试套件
========================================
=== AABB Tests ===
AABB-AABB (intersecting): 1 (expected: 1)
AABB-AABB (separate): 0 (expected: 0)
MTV: (1, 0, 0)
AABB-Sphere (intersecting): 1 (expected: 1)

=== Sphere Tests ===
Sphere-Sphere (intersecting): 1 (expected: 1)
Sphere-Sphere (separate): 0 (expected: 0)
Normal: (1, 0, 0)
Penetration: 1

=== OBB Tests ===
OBB-OBB (intersecting): 1 (expected: 1)
MTV: (0.5, 0, 0)
OBB-OBB (rotated, separate): 0 (expected: 0)

=== Capsule Tests ===
Capsule-Capsule (intersecting): 1 (expected: 1)
Capsule-Capsule (separate): 0 (expected: 0)
Normal: (1, 0, 0)
Penetration: 1

=== Ray Tests ===
Ray-AABB: 1 t=4 point=(0, 0, -1)
Ray-Sphere: 1 t=3 point=(0, 0, -2)
Ray-Triangle: 1 t=2 point=(2, 0, 0)

=== GJK Tests ===
GJK AABB-AABB (intersecting): 1 (expected: 1)
GJK AABB-AABB (separate): 0 (expected: 0)
GJK Sphere-Sphere (intersecting): 1 (expected: 1)
GJK Sphere-Sphere (separate): 0 (expected: 0)
GJK Convex-Convex (intersecting): 1 (expected: 1)

=== EPA Tests ===
GJK+EPA Sphere-Sphere: intersecting
  Normal: (1, 0, 0)
  Penetration: 1
GJK+EPA AABB-AABB: intersecting
  Normal: (1, 0, 0)
  Penetration: 0.5

=== BVH Tests ===
BVH built with 199 nodes
Ray hit object 0 at t=...
Query found 4 overlapping objects

========================================
  所有测试完成！
========================================
```

---

## 3. 练习

### 练习 1：实现 OBB-Sphere 相交测试

使用 SAT 思想，实现 OBB 与 Sphere 的相交测试。提示：需要测试的轴包括 OBB 的 3 个局部轴，以及从球心到 OBB 最近点的方向。

**验证：** 创建一个旋转 45 度的 OBB 和一个部分穿透它的球体，验证相交结果和 MTV 方向是否正确。

### 练习 2：优化 GJK 算法

当前 GJK 实现在每次迭代中都重新构建单纯形。请实现以下优化：

1. **添加早期退出**：如果两个物体的包围体（AABB 或 Sphere）不相交，直接返回 false
2. **缓存支持方向**：在 EPA 收敛后缓存最后使用的方向，作为下一次 GJK 的初始方向
3. **添加距离计算模式**：扩展 GJK 使其可以计算两个不相交物体之间的最短距离

**验证：** 创建 1000 对随机位置的 AABB 和球体，对比优化前后的性能差异。

### 练习 3（可选）：实现连续碰撞检测（CCD）

实现基于 Conservative Advancement 的 Sphere-Sphere CCD：

```
算法步骤：
1. 初始化 t = 0
2. 循环：
   a. 计算当前位置的两个球体之间的距离 d
   b. 计算两球接近的相对速度 v（沿连心线方向）
   c. 如果 v <= 0，退出（不再接近）
   d. 安全推进距离 = d / v
   e. t += 安全推进距离
   f. 如果 t >= 1，退出（本时间步内不会碰撞）
   g. 更新球体位置
   h. 如果球体相交，返回碰撞时间 t
```

**验证：** 创建两个高速运动的球体（一帧内移动距离大于直径之和），验证 CCD 能正确检测到碰撞而 DCD 会产生隧道效应。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // OBB-Sphere 相交测试（基于SAT思想）
>
> // 将球心投影到OBB的某个轴上，计算投影区间重叠
> bool OBBSphereIntersect(const OBB& obb, const Sphere& sphere,
>                         Vec3& mtv) {
>     // 将球心转换到OBB局部坐标
>     Vec3 localCenter = obb.WorldToLocal(sphere.center);
>
>     // 找到OBB表面离球心最近的点（在局部坐标系中）
>     Vec3 closest;
>     closest.x = std::max(-obb.halfExtents.x,
>                        std::min(localCenter.x, obb.halfExtents.x));
>     closest.y = std::max(-obb.halfExtents.y,
>                        std::min(localCenter.y, obb.halfExtents.y));
>     closest.z = std::max(-obb.halfExtents.z,
>                        std::min(localCenter.z, obb.halfExtents.z));
>
>     // 最近点与球心的距离
>     Vec3 diff = closest - localCenter;
>     float distSq = diff.LengthSq();
>     float rSq = sphere.radius * sphere.radius;
>
>     if (distSq > rSq) return false;  // 不相交
>
>     // 计算MTV：需要测试以下轴
>     // 1. OBB的3个局部轴
>     // 2. 球心到OBB最近点的方向
>
>     float dist = std::sqrt(distSq);
>
>     if (dist < 1e-6f) {
>         // 球心在OBB内部或表面上，选择穿透最小的OBB轴
>         float overlapX = obb.halfExtents.x
>                        - std::abs(localCenter.x);
>         float overlapY = obb.halfExtents.y
>                        - std::abs(localCenter.y);
>         float overlapZ = obb.halfExtents.z
>                        - std::abs(localCenter.z);
>
>         float minOverlap = std::min({overlapX, overlapY, overlapZ});
>         mtv = obb.axes[0] * (overlapX + sphere.radius);
>         if (overlapY <= overlapX && overlapY <= overlapZ)
>             mtv = obb.axes[1] * (overlapY + sphere.radius);
>         if (overlapZ <= overlapX && overlapZ <= overlapY)
>             mtv = obb.axes[2] * (overlapZ + sphere.radius);
>
>         // 方向修正：push sphere out of OBB
>         Vec3 worldCenter = obb.center;
>         if (Dot(mtv, sphere.center - worldCenter) < 0)
>             mtv = mtv * -1.0f;
>     } else {
>         float penetration = sphere.radius - dist;
>
>         // 最近点方向（在局部空间）
>         Vec3 localNormal = diff / dist;
>
>         // 转换到世界空间
>         Vec3 worldNormal = obb.LocalToWorld(localNormal)
>                          - obb.center;
>         worldNormal.Normalize();
>
>         mtv = worldNormal * penetration;
>     }
>
>     return true;
> }
>
> // 测试函数
> void TestOBBSphere() {
>     // 创建旋转45度的OBB
>     float angle = 3.14159265f / 4.0f;  // 45度
>     Vec3 axisX(std::cos(angle), std::sin(angle), 0);
>     Vec3 axisY(-std::sin(angle), std::cos(angle), 0);
>     Vec3 axisZ(0, 0, 1);
>     Vec3 axes[3] = {axisX, axisY, axisZ};
>     OBB obb(Vec3(0, 0, 0), axes, Vec3(2, 1, 1));
>
>     // 球体部分穿透OBB
>     Sphere sphere(Vec3(2.5, 0.5, 0), 1.0f);
>
>     Vec3 mtv;
>     bool hit = OBBSphereIntersect(obb, sphere, mtv);
>     std::cout << "OBB-Sphere Intersect: " << hit
>               << " (expected: 1)\n";
>     if (hit) {
>         std::cout << "MTV: (" << mtv.x << ", "
>                   << mtv.y << ", " << mtv.z << ")\n";
>     }
>
>     // 不穿透测试
>     Sphere farSphere(Vec3(10, 10, 0), 1.0f);
>     hit = OBBSphereIntersect(obb, farSphere, mtv);
>     std::cout << "OBB-Sphere Far: " << hit
>               << " (expected: 0)\n";
> }
> ```
>
> **核心思路**：OBB-Sphere相交检测分两步：(1)将球心变换到OBB局部坐标——此时OBB退化为AABB(-halfExtents, +halfExtents)，问题简化为AABB-Sphere检测；(2)计算最近点和穿透深度。当球心在OBB内部时，MTV方向取穿透最小的OBB轴；球心在外时，MTV方向由最近点→球心方向决定。SAT需要测试OBB的3个轴加上球心到最近点的方向，但通过坐标变换实际上将问题退化到了更简单的形式。

> [!tip]- 练习 2 参考答案
> ```cpp
> // 优化 GJK 算法
>
> class OptimizedGJK {
> public:
>     // 缓存的上次查询信息
>     struct GJKCache {
>         Vec3 lastDirection;   // 上次分离轴方向
>         bool isValid = false;
>     };
>
>     // 包围体预检测 + 缓存加速 + 距离模式
>     struct GJKResult {
>         bool intersect;
>         float distance;        // 不相交时的最短距离
>         Vec3 closestA, closestB;  // 最短距离对应的最近点对
>         Vec3 separatingAxis;   // 分离轴（缓存下次使用）
>     };
>
>     // 1. 早期退出：包围体预检测
>     bool EarlyOut(const ConvexShape& a, const ConvexShape& b) {
>         // AABB快速预检测
>         AABB aabbA = a.GetAABB();
>         AABB aabbB = b.GetAABB();
>         if (!AABBIntersect(aabbA, aabbB)) return false;
>
>         // Sphere可选预检测
>         Sphere sphereA = a.GetBoundingSphere();
>         Sphere sphereB = b.GetBoundingSphere();
>         float distSq = (sphereA.center - sphereB.center).LengthSq();
>         float rSum = sphereA.radius + sphereB.radius;
>         if (distSq > rSum * rSum) return false;
>
>         return true;  // 包围体重叠，需要精确检测
>     }
>
>     // 2. 带缓存的GJK查询
>     GJKResult ComputeDistance(const ConvexShape& a,
>                                const ConvexShape& b,
>                                GJKCache& cache) {
>         GJKResult result;
>         result.intersect = false;
>         result.distance = std::numeric_limits<float>::max();
>
>         // 早期退出
>         if (!EarlyOut(a, b)) {
>             // 不相交：用分离轴方向估算距离
>             // ...
>             cache.lastDirection =
>                 (b.GetBoundingSphere().center
>                  - a.GetBoundingSphere().center).Normalized();
>             cache.isValid = true;
>             return result;
>         }
>
>         // 使用缓存的方向作为初始搜索方向
>         // 如果缓存有效且物体相邻帧变化不大，通常1-2次迭代就收敛
>         Vec3 direction;
>         if (cache.isValid) {
>             direction = cache.lastDirection;
>         } else {
>             // 首次查询用随机方向或质心方向
>             direction = (b.GetBoundingSphere().center
>                        - a.GetBoundingSphere().center);
>             if (direction.LengthSq() < 1e-6f)
>                 direction = Vec3(1, 0, 0);
>             direction.Normalize();
>         }
>
>         // 标准GJK迭代（这里简化为框架）
>         Simplex simplex;
>         int maxIter = 32;
>
>         for (int iter = 0; iter < maxIter; ++iter) {
>             Vec3 supportA = a.Support(direction);
>             Vec3 supportB = b.Support(-direction);
>             Vec3 supportPoint = supportA - supportB;
>
>             // 如果支持点不在原点方向，物体分离
>             float dot = Dot(supportPoint, direction);
>             if (dot < 0) {
>                 result.intersect = false;
>                 // 3. 距离模式：计算两个形状之间的最短距离
>                 result.distance =
>                     ComputeClosestDistance(simplex, a, b);
>                 break;
>             }
>
>             simplex.Add(supportPoint);
>
>             if (simplex.ContainsOrigin()) {
>                 result.intersect = true;
>                 result.distance = 0.0f;
>                 break;
>             }
>
>             // 更新方向
>             direction = simplex.ComputeNewDirection();
>         }
>
>         // 缓存分离轴方向
>         cache.lastDirection = direction;
>         cache.isValid = true;
>
>         return result;
>     }
>
>     // 最短距离计算（两个分离凸体之间）
>     float ComputeClosestDistance(const Simplex& simplex,
>                                   const ConvexShape& a,
>                                   const ConvexShape& b) {
>         // 使用单纯形中的点计算最近点对
>         // Johnson算法：求解单纯形中离原点最近的点
>         Vec3 closestPoint;  // Minkowski差中离原点最近的点
>         // ... (具体实现依赖单纯形数据结构)
>         return closestPoint.Length();
>     }
> };
>
> // 性能基准测试
> void BenchmarkGJK() {
>     OptimizedGJK gjk;
>     std::vector<ConvexShape> shapes = GenerateRandomShapes(1000);
>
>     auto start = std::chrono::high_resolution_clock::now();
>     int hitCount = 0;
>     for (size_t i = 0; i < shapes.size(); ++i) {
>         for (size_t j = i + 1; j < shapes.size(); ++j) {
>             OptimizedGJK::GJKCache cache;  // 每对有自己的缓存
>             auto result = gjk.ComputeDistance(
>                 shapes[i], shapes[j], cache);
>             if (result.intersect) hitCount++;
>         }
>     }
>     auto end = std::chrono::high_resolution_clock::now();
>     auto ms = std::chrono::duration_cast<
>         std::chrono::milliseconds>(end - start).count();
>
>     std::cout << "Tested " << (shapes.size() * (shapes.size()-1)/2)
>               << " pairs in " << ms << "ms\n";
>     std::cout << "Hits: " << hitCount << "\n";
> }
> ```
>
> **核心思路**：(1)AABB/Sphere包围体预检测用O(1)操作排除大量不可能碰撞对，对n=1000的场景通常排除90%+对。(2)缓存支持方向利用"时间相干性"——相邻帧物体的相对位置变化很小，上一帧的分离轴方向很可能仍是本帧的有效方向，通常只需1-2次迭代。(3)距离模式在分离时返回最短距离和最近点对（如Johnson算法或Casey算法），这对物理引擎的穿透/分离反馈至关重要。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // CCD.hpp —— 基于 Conservative Advancement 的连续碰撞检测
>
> class SphereCCD {
> public:
>     struct CCDResult {
>         bool hit;
>         float toi;  // Time of Impact [0, 1]
>         Vec3 contactPoint;
>         Vec3 contactNormal;
>     };
>
>     // Conservative Advancement: 安全推进直到碰撞或时间耗尽
>     CCDResult Detect(const Sphere& a, const Vec3& velA,
>                      const Sphere& b, const Vec3& velB,
>                      float dt) {
>         CCDResult result;
>         result.hit = false;
>         result.toi = 0.0f;
>
>         float t = 0.0f;
>         Vec3 posA = a.center;
>         Vec3 posB = b.center;
>
>         const float TOLERANCE = 0.001f;
>         int maxIter = 100;
>
>         for (int iter = 0; iter < maxIter; ++iter) {
>             // 当前位置的距离
>             Vec3 diff = posB - posA;
>             float dist = diff.Length();
>             float minDist = a.radius + b.radius;
>
>             // 已经相交
>             if (dist <= minDist + TOLERANCE) {
>                 result.hit = true;
>                 result.toi = t;
>                 Vec3 dir = diff.Normalized();
>                 result.contactNormal = dir;
>                 result.contactPoint = posA + dir * a.radius;
>                 return result;
>             }
>
>             // 相对速度沿连心线方向的分量
>             Vec3 relVel = velB - velA;
>             Vec3 dir = -diff.Normalized();  // A→B方向
>             float closingSpeed = Dot(relVel, dir);
>
>             // 如果不再接近，本次时间步不会碰撞
>             if (closingSpeed <= 1e-6f) {
>                 return result;  // no hit
>             }
>
>             // 安全推进距离（不会产生穿透的最大步长）
>             float safeAdvance = (dist - minDist) / closingSpeed;
>
>             // 确保推进不过头
>             if (t + safeAdvance > dt) {
>                 t = dt;
>                 break;
>             }
>
>             // 推进时间
>             t += safeAdvance + TOLERANCE;
>             if (t >= dt) break;
>
>             // 更新位置
>             posA = a.center + velA * t;
>             posB = b.center + velB * t;
>         }
>
>         return result;
>     }
> };
>
> // CCD vs DCD 对比测试
> void TestCCDvsDCD() {
>     // 两个高速球体：一帧内移动距离 > 直径之和
>     Sphere bullet(Vec3(0, 0, 0), 0.1f);      // 子弹（小）
>     Sphere target(Vec3(1.0f, 0.02f, 0), 0.2f); // 靶子
>     float dt = 1.0f / 60.0f;  // 16.67ms
>
>     // 子弹速度极快：一帧穿越靶子
>     Vec3 bulletVel(100.0f, 0, 0);  // 100 m/s
>     Vec3 targetVel(0, 0, 0);
>
>     // DCD检测
>     Vec3 bulletEnd = bullet.center + bulletVel * dt;
>     Sphere bulletEndSphere(bulletEnd, bullet.radius);
>     bool dcdHit = SphereIntersect(bulletEndSphere, target);
>     std::cout << "DCD: " << (dcdHit ? "HIT" : "MISS")
>               << " — 子弹穿过靶子，DCD漏检!\n";
>
>     // CCD检测
>     SphereCCD ccd;
>     auto ccdResult = ccd.Detect(bullet, bulletVel,
>                                  target, targetVel, dt);
>     std::cout << "CCD: " << (ccdResult.hit ? "HIT" : "MISS")
>               << " — TOI=" << ccdResult.toi
>               << " (正确捕获碰撞)\n";
> }
> ```
>
> **核心思路**：Conservative Advancement通过"最大安全步长"避免了隧道效应。每次迭代计算当前位置下两球体的距离d和接近速度v，安全推进`(d - r1 - r2) / v`的距离——这个步长保证了推进后两球体不会超过切线接触的位置，因此不会产生穿透。DCD（离散碰撞检测）只检查帧末位置，如果物体速度足够快可以在一帧内完全穿越另一个物体（隧道效应），CCD通过沿轨迹连续采样消除了这个盲区。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

### 经典文献

1. **"A Fast Procedure for Computing the Distance Between Complex Objects in Three-Dimensional Space"**
   - Gilbert, Johnson, Keerthi (1988)
   - GJK 算法的原始论文

2. **"Proximity Queries and Penetration Depth Computation on 3D Game Objects"**
   - Christer Ericson, "Real-Time Collision Detection" (2005)
   - 游戏碰撞检测的权威参考书

3. **"Collision Detection in Interactive 3D Environments"**
   - Gino van den Bergen (2003)
   - 深入讲解 GJK/EPA 的实现细节

### 现代优化技术

4. **Incremental GJK**：利用时间相干性，复用上一帧的单纯形作为初始状态，通常只需 1-2 次迭代即可收敛

5. **Signed Volume Method**：替代传统的叉积法判断原点是否在单纯形内，数值稳定性更好

6. **GPU-Accelerated Broad Phase**：使用 CUDA/Compute Shader 并行处理大量物体的 Broad Phase 检测

### 开源实现参考

7. **Bullet Physics**：https://github.com/bulletphysics/bullet3
   - 工业级物理引擎，GJK/EPA 实现非常成熟

8. **Jolt Physics**：https://github.com/jrouwe/JoltPhysics
   - 现代 C++ 物理引擎，性能优异

9. **Box2D**：https://github.com/erincatto/box2d
   - 2D 物理引擎，SAT 和 GJK 的简洁实现

### 进阶主题

10. **Minkowski Portal Refinement (MPR)**：另一种基于 Minkowski 和的碰撞检测算法，在某些场景下比 GJK 更快

11. **Contact Point Generation**：从 EPA 的结果生成多个接触点（用于稳定堆叠）

12. **Speculative Contacts**：基于预测的碰撞响应，减少 CCD 的开销

---

## 常见陷阱

### 陷阱 1：浮点精度问题

GJK 和 EPA 对浮点精度非常敏感。当两个物体几乎相切时，`Dot(support, direction)` 可能非常接近 0，导致错误的相交判断。

**解决方案：**
- 使用合适的 EPSILON（通常 1e-6 到 1e-4）
- 在 EPA 中添加最小穿透深度阈值，避免报告过浅的碰撞
- 考虑使用双精度进行关键计算

### 陷阱 2：退化单纯形

当 GJK 的单纯形中的点几乎共线或共面时，叉积计算会得到接近零向量的结果，导致方向计算错误。

**解决方案：**
- 在构建新面时检查法线长度，如果太小则跳过该面
- 使用鲁棒的单纯形处理算法（如 Signed Volume Method）

### 陷阱 3：EPA 不收敛

EPA 在某些退化情况下（如两个平行的面）可能无限循环。

**解决方案：**
- 始终设置最大迭代次数
- 检查新支持点是否真正扩展了多面体（与已有顶点距离 > EPSILON）
- 如果多面体变得过于复杂，可以退回到使用 GJK 距离算法

### 陷阱 4：射线检测的 t < 0

射线检测可能返回射线起点后方的交点（t < 0），这在游戏逻辑中通常是无效的。

**解决方案：**
- 始终检查 t >= 0
- 对于 AABB，注意 tMin 可能为负而 tMax 为正的情况（射线起点在 AABB 内部）

### 陷阱 5：OBB 轴不正交

OBB 的 3 个轴必须始终保持单位长度且互相正交。如果直接对 OBB 应用非均匀缩放或剪切变换，轴会失去正交性。

**解决方案：**
- 每次变换后重新正交化轴（Gram-Schmidt）
- 或者存储旋转四元数/矩阵，在需要时实时计算轴

### 陷阱 6：BVH 构建质量

简单的中点分割在某些分布下会产生不平衡的 BVH，导致查询性能下降。

**解决方案：**
- 使用 SAH（Surface Area Heuristic）选择最优分割点
- 考虑使用 Binned SAH 在构建速度和树质量之间取得平衡
- 对于动态场景，使用增量式更新或重构策略
