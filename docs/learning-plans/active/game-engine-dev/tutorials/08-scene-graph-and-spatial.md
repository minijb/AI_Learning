# 场景图与空间数据结构

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 6h
> 前置知识: 01-数学基础：线性代数与几何

---

## 1. 概念讲解

### 为什么需要这个？

想象你正在开发一个开放世界游戏，场景中有数百万个物体：树木、岩石、建筑、NPC、粒子特效。如果每一帧都遍历所有物体进行渲染和物理计算，性能将完全不可接受。一个典型的 3A 游戏场景可能包含：

- 数十万到数百万个静态物体
- 数千个动态物体
- 复杂的灯光和阴影系统
- 物理碰撞检测

**核心问题：** 如何在海量物体中快速找到"当前帧真正需要处理的物体"？

场景图和空间数据结构就是解决这个问题的核心工具：

1. **场景图（Scene Graph）** — 用层次结构组织物体，高效管理变换关系和渲染状态
2. **空间数据结构** — 将三维空间划分成区域，实现 O(log n) 甚至 O(1) 的查询效率
3. **剔除系统** — 快速排除不可见物体，减少 GPU 负载

不学这些的后果：你的引擎只能处理几百个物体，帧率随物体数量线性下降，永远无法做出真正的 3D 游戏。

### 核心思想

场景图的核心思想是**层次化组织**：将世界分解为父子关系的节点树，子节点继承父节点的变换（位置、旋转、缩放）。一辆汽车包含车身和四个轮子，轮子随车身移动——这就是变换继承。

空间数据结构的核心思想是**分而治之**：将三维空间递归划分，只在相关区域搜索物体。就像查字典不用逐页翻，而是先看目录找到大致范围。

---

### 1.1 场景图（Scene Graph）

#### 层次结构与变换继承

场景图是一个有向无环图（DAG）或树结构，每个节点代表场景中的一个实体（物体、灯光、相机等）。

**变换继承机制：**

每个节点存储**局部变换**（Local Transform），相对于父节点。世界变换（World Transform）通过递归计算得到：

```
WorldTransform(Node) = WorldTransform(Parent) × LocalTransform(Node)
```

例如，一辆坦克的场景图：

```
World (Root)
└── Tank (local: pos=(10, 0, 5), rot=30°)
    ├── Turret (local: pos=(0, 2, 0), rot=0°)
    │   └── Barrel (local: pos=(0, 0.5, 1.5), rot=0°)
    ├── LeftTrack (local: pos=(-1.5, 0, 0))
    └── RightTrack (local: pos=(1.5, 0, 0))
```

当坦克向前移动时，炮塔、炮管、履带自动跟随——这就是变换继承的力量。

#### DAG vs Tree

| 特性 | 树（Tree） | 有向无环图（DAG） |
|------|-----------|-----------------|
| 结构 | 每个节点只有一个父节点 | 一个节点可被多个父节点引用 |
| 实现复杂度 | 简单 | 较复杂（需处理共享节点） |
| 内存占用 | 节点可重复 | 节点共享，节省内存 |
| 典型应用 | 简单场景、UI 系统 | 实例化渲染、骨骼共享 |
| 遍历 | 简单递归 | 需标记已访问节点 |

**DAG 的典型场景：** 同一个树木模型在森林中出现 1000 次。用 DAG，树叶节点被 1000 个父节点引用，只需一份几何数据 + 1000 个变换矩阵。

#### 场景图的设计权衡与 ECS 架构

场景图的设计需要考虑以下权衡：

| 设计选择 | 优点 | 缺点 |
|---------|------|------|
| 严格树结构 | 简单、缓存友好 | 难以表达共享（一个物体属于多个父节点）|
| DAG (有向无环图) | 支持实例化和共享 | 复杂性增加 |
| 扁平化 + 空间结构 | 渲染效率高 | 失去变换继承 |
| 组件化 (ECS) | 数据局部性好、缓存友好 | 设计复杂度高 |

现代游戏引擎（如 Unity、Unreal、Bevy）越来越倾向于使用**ECS（Entity-Component-System）**架构来替代传统的场景图。ECS 将场景拆分为三个部分：

- **Entity（实体）**：一个唯一的标识符（通常只是一个整数）。
- **Component（组件）**：纯数据，不包含逻辑。例如 `TransformComponent`（位置+旋转+缩放）、`MeshComponent`（Mesh 引用+材质引用）。
- **System（系统）**：处理特定 Component 类型的逻辑。例如 `RenderSystem` 处理所有有 `MeshComponent` 的实体。

ECS 的核心优势是**数据局部性（Data Locality）**：相同类型的 Component 被连续存储在内存中，系统处理时可以顺序访问，充分利用 CPU 缓存。这种架构对现代 CPU 的缓存行非常友好，能显著提升性能。

一个典型的 ECS 实现使用**稀疏集（Sparse Set）**或**Archetype（原型）**来组织 Component 存储。以 Bevy 引擎的 Archetype 模型为例，具有相同 Component 组合的实体被存储在一起（如所有同时有 Transform + Mesh 的实体存储在一个 Archetype 中），系统可以高效地遍历特定 Archetype 中的所有实体。

> 关于 ECS 的完整实现和深入讲解，请参考本计划的 [04-ecs-architecture.md](04-ecs-architecture.md) 教程。

---

### 1.2 包围体（Bounding Volumes）

包围体是用简单几何体包裹复杂物体的近似表示，用于快速碰撞检测和剔除。

#### AABB（轴对齐包围盒）

与坐标轴对齐的长方体，由最小点和最大点定义。

- **优点：** 构建极快，相交测试简单（逐分量比较）
- **缺点：** 旋转物体时包围盒膨胀严重
- **存储：** 6 个 float（min.x, min.y, min.z, max.x, max.y, max.z）
- **相交测试：** 6 次比较

#### OBB（定向包围盒）

可任意旋转的长方体，有方向性。

- **优点：** 紧密贴合旋转物体
- **缺点：** 相交测试复杂（分离轴定理），构建较慢
- **存储：** 15 个 float（中心 3 + 三个轴方向 9 + 半边长 3）
- **相交测试：** 15 次分离轴投影

#### 包围球（Bounding Sphere）

- **优点：** 旋转不变，相交测试最快（距离比较）
- **缺点：** 对细长物体包裹松散
- **存储：** 4 个 float（中心 3 + 半径 1）
- **相交测试：** 1 次距离平方比较

#### 胶囊体（Capsule）

线段 + 半径，常用于角色碰撞。

- **优点：** 适合人形角色，碰撞响应平滑
- **缺点：** 比球体复杂
- **存储：** 7 个 float（线段起点 3 + 终点 3 + 半径 1）

#### k-DOP（k-Discrete Oriented Polytope）

用 k 组平行平面切割空间形成的凸包。

- **k=6：** 就是 AABB
- **k=14：** 6 个轴对齐面 + 8 个对角面，更紧密
- **k=18, 26：** 更紧密但计算更复杂
- **优点：** 在紧密性和计算成本间可调
- **缺点：** k 增大时收益递减

**选择指南：**

| 场景 | 推荐包围体 |
|------|-----------|
| 粗略剔除/ broad-phase | AABB 或 Sphere |
| 旋转物体紧密包围 | OBB 或 k-DOP |
| 角色碰撞 | Capsule |
| 射线检测加速 | Sphere（计算最快） |
| 静态场景 | AABB（构建一次） |

---

### 1.3 LOD 系统（Level of Detail）

**LOD（Level of Detail，细节层次）**是减少远距离物体渲染开销的核心技术。其基本原理是：物体离相机越远，使用越简化的模型和纹理来渲染，因为远距离的细节玩家难以察觉。

#### LOD 类型对比

| LOD 类型 | 切换方式 | 视觉质量 | 实现复杂度 | 适用场景 |
|---------|---------|---------|----------|---------|
| 离散 LOD | 距离阈值切换不同模型 | 可能有跳变 | 低 | 角色、道具 |
| 连续 LOD (CLOD) | 渐进网格，顶点逐步减少 | 平滑 | 高 | 地形、大规模场景 |
| 网格 LOD (Mesh LOD) | 预计算多个 LOD 模型 | 良好 | 中 | 角色、建筑 |
| 材质 LOD (Shader LOD) | 远距离切换简化 Shader | 良好 | 低 | 所有物体 |
| 纹理 LOD (Mipmap) | GPU 自动选择 Mipmap 层级 | 优秀 | 极低 | 所有纹理 |

**离散 LOD**是最简单的实现方式。美术人员为每个模型制作多个 LOD 级别（如 LOD0 为最高精度，LOD1 减少 50% 面数，LOD2 减少 75% 面数），引擎根据物体到相机的距离自动切换。为了防止 LOD 切换时的视觉跳变（Pop），可以使用**距离过渡融合（Distance Transition Blending）**或**屏幕空间抖动（Dithered LOD Transition）**来在两个 LOD 级别之间进行交叉淡入淡出。

**连续 LOD（CLOD）**在运行时动态调整模型的细节级别。对于地形系统，最常用的 CLOD 技术是**Geomipmapping**和**ROAM（Real-time Optimally Adapting Meshes）**。这些技术根据地形块到相机的距离，动态调整网格的分辨率——近处使用高密度网格，远处使用低密度网格。

现代引擎（如 Unreal Engine 5）引入了更先进的**虚拟几何（Virtualized Geometry）**技术（Nanite），它将几何体分解为微多边形集群，使用 GPU-Driven 流水线进行自动 LOD 和剔除。这种技术使得使用电影级精度的模型在实时场景中成为可能，从根本上改变了 LOD 的概念。

---

### 1.4 遮挡剔除（Occlusion Culling）

**遮挡剔除（Occlusion Culling）**是去除被其他物体完全遮挡的物体的技术。即使一个物体在视锥内，如果它被更近的大型物体（如建筑、山丘）完全遮挡，那么渲染它也是浪费。

遮挡剔除的主要方法包括：

1. **软件光栅化遮挡查询**：在 CPU 上维护一个低分辨率（如 256x256）的深度缓冲区，用简化的几何体（如包围盒）光栅化场景，然后用它来测试其他物体的可见性。这种方法的优点是无需 GPU-CPU 同步，缺点是增加了 CPU 开销。

2. **硬件遮挡查询**：使用 GPU 的遮挡查询功能（如 `BeginOcclusionQuery` / `EndOcclusionQuery`）。先渲染大型遮挡物（如建筑），然后对可能被遮挡的物体执行遮挡查询。这种方法的优点是精确，缺点是 GPU-CPU 同步延迟。

3. **预计算可见性（Precomputed Visibility）**：对于静态场景，可以预计算每个可能相机位置的可见物体集合。存储方式通常使用**潜在可见集（Potentially Visible Set, PVS）**。这种方法在运行时开销极低，但内存占用较大，且不适用于动态物体。

4. **遮挡网格（Occlusion Mesh）**：为遮挡物生成简化的遮挡网格（仅包含外轮廓），用这些简化网格进行遮挡测试。

Unreal Engine 5 引入了 **Lumen** 全局光照系统，它使用了硬件加速的射线追踪来实现更高效的遮挡查询和光照计算。

---

### 1.5 空间划分结构

#### 八叉树（Octree）

将三维空间递归划分为 8 个子立方体，直到满足终止条件（节点内物体数少于阈值或达到最大深度）。

```
节点分裂过程：
        +--------+--------+
       /|       /|       /|
      / |      / |      / |
     +--------+--------+  |
     |  |     |  |     |  |
     |  +-----|--+-----|--+
     | /      | /      | /
     |/       |/       |/
     +--------+--------+
     
     每个节点分裂为 2×2×2 = 8 个子节点
```

- **构建：** O(n log n)（平均）
- **查询（点/范围）：** O(log n)
- **优点：** 实现简单，对均匀分布数据效果好
- **缺点：** 高深度时内存开销大，非均匀分布时树不平衡
- **适用：** 地形渲染、大规模静态场景、粒子系统

#### 四叉树（Quadtree）

八叉树的二维版本，将平面递归划分为 4 个子区域。

- **适用：** 地形 LOD、2D 游戏、GIS 系统、俯视视角剔除

#### BVH（Bounding Volume Hierarchy）

用包围体层次包裹物体，叶节点存储实际物体，内部节点存储子树的包围体。

```
        [AABB: 整个场景]
           /        \
    [AABB: 左半]  [AABB: 右半]
      /    \         /    \
   [Obj1] [Obj2]  [Obj3] [Obj4]
```

- **构建：** O(n log n)（SAH 优化）
- **查询：** O(log n)
- **优点：** 紧密贴合物体分布，对动态物体友好（可自底向上更新）
- **缺点：** 构建成本高于八叉树
- **适用：** 光线追踪、动态场景碰撞检测、视锥剔除

**SAH（Surface Area Heuristic）**：选择分割平面的启发式方法，最小化期望查询代价：

```
Cost = C_traversal + (SA_left / SA_parent) × N_left × C_intersect
                   + (SA_right / SA_parent) × N_right × C_intersect
```

#### BSP 树（Binary Space Partitioning）

用任意平面（不限于轴对齐）递归分割空间。

- **构建：** O(n log n) 到 O(n²)
- **查询：** O(log n)
- **优点：** 可处理任意多边形，对室内场景完美
- **缺点：** 构建复杂，树深度可能很大
- **适用：** 传统 FPS 的室内场景（Quake、Unreal Engine 1/2）、画家算法排序

**历史地位：** BSP 在 90 年代是主流，现代引擎中主要用于特定场景或编辑器中的 CSG 操作。

#### 均匀网格（Uniform Grid）

将空间划分为等大小的网格单元，每个单元维护其中的物体列表。

- **构建：** O(n)
- **查询：** O(1)（直接计算单元索引）
- **优点：** 实现最简单，查询最快，缓存友好
- **缺点：** 非均匀分布时效率骤降，大量空单元浪费内存
- **适用：** 粒子系统、SPH 流体、均匀分布的物体群

**哈希网格（Spatial Hashing）**：对均匀网格的改进，只存储非空单元（用哈希表），大幅节省内存。

#### 四叉树地形（Quadtree Terrain）

**四叉树（Quadtree）**是管理大型地形的高效数据结构。它将地形平面递归地划分为四个相等的子区域，每个节点对应一个地形块（Terrain Chunk）。

四叉树地形的核心特性：

1. **视锥裁剪**：四叉树的层次结构使得视锥裁剪非常高效。如果一个节点不在视锥内，其所有子节点也不需要处理。
2. **LOD 管理**：四叉树的深度对应 LOD 级别——根节点是最粗略的表示，叶节点是最详细的表示。根据距离选择不同深度的节点来渲染。
3. **裂缝修补**：相邻的地形块可能处于不同的 LOD 级别，导致接缝处出现裂缝（T-junction）。解决方案包括**裙边法（Skirts）**在接缝处添加垂直面，以及**索引修补（Index Stitching）**调整边界处的索引连接。

四叉树的**剔除效率**来自一个重要的观察：如果一个地形块（四叉树节点）完全在视锥外或被更近的地形完全遮挡，那么它的所有子节点也不需要渲染。这种层次化剔除将视锥测试的数量从 O(n)（每个地形块单独测试）降低到 O(log n)。

```
四叉树地形划分示意：

        +------------------+------------------+
        |                  |                  |
        |    Chunk 0       |    Chunk 1       |
        |   (根节点)       |   (根节点)       |
        |                  |                  |
        +------------------+------------------+
        |                  |                  |
        |    Chunk 2       |    Chunk 3       |
        |   (根节点)       |   (根节点)       |
        |                  |                  |
        +------------------+------------------+

当相机靠近 Chunk 0 时，Chunk 0 继续细分：

        +----------+----------+------------------+
        |  C0-0    |  C0-1    |                  |
        | (高细节) | (高细节) |    Chunk 1       |
        +----------+----------+   (低细节)       |
        |  C0-2    |  C0-3    |                  |
        | (高细节) | (高细节) |                  |
        +----------+----------+------------------+
        |                  |                  |
        |    Chunk 2       |    Chunk 3       |
        |   (低细节)       |   (低细节)       |
        |                  |                  |
        +------------------+------------------+
```

---

### 1.6 视锥剔除（Frustum Culling）

相机视野是一个平截头体（Frustum），由 6 个平面组成：近裁剪面、远裁剪面、左、右、上、下。

**视锥剔除**就是快速判断物体是否在这个平截头体内。

**测试策略（从便宜到昂贵）：

1. **距离测试** — 物体太远？直接剔除
2. **包围球测试** — 与 6 个平面做快速测试
3. **AABB 测试** — 更精确但稍慢
4. **精确测试** — 极少需要

**测试结果分类：**

- **完全在外（OUTSIDE）** — 剔除
- **完全在内（INSIDE）** — 完全渲染
- **相交（INTERSECT）** — 需要进一步测试或保守渲染

**优化技巧：**

- **层次剔除：** 先测试父节点包围体，若完全在外则跳过整个子树
- **遮挡查询：** 利用 GPU 的遮挡查询（Occlusion Query）做硬件加速剔除

---

### 1.5 遮挡剔除（Occlusion Culling）基础

视锥剔除只解决"在视野内吗"，不解决"被其他物体挡住吗"。一栋大楼可能挡住后面数百个物体——遮挡剔除就是找出这些被挡住的物体。

**基本方法：**

1. **软件遮挡剔除：**
   - 用低分辨率深度缓冲渲染遮挡物（如大型建筑）
   - 测试被遮挡物的包围盒是否完全在遮挡物后面
   - UE4 的 Software Occlusion Culling 采用此方案

2. **硬件遮挡查询（Hardware Occlusion Queries）：**
   - GPU 渲染包围盒，查询是否有像素通过深度测试
   - 延迟一帧，需要小心处理
   - 现代 GPU 支持高效实现

3. **Portal 系统（室内场景）：**
   - 将场景划分为房间，通过 Portal（门/窗）连接
   - 只渲染通过 Portal 可见的房间
   - 经典方案，对室内游戏极高效

4. **HZB（Hierarchical Z-Buffer）：**
   - 构建深度缓冲的 Mipmap 金字塔
   - 在粗糙层级快速排除被遮挡物体
   - 现代引擎主流方案

---

### 1.6 LOD（Level of Detail）简介

LOD 是"用更简单的模型表示远处的物体"，与空间数据结构配合使用。

**LOD 切换方式：**

| 方式 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 离散 LOD | 预生成 3-5 个精度版本 | 简单，可控 | 切换时可能跳变 |
| 连续 LOD（CLOD）| 运行时动态简化网格 | 平滑过渡 | CPU 开销大 |
| 视锥相关 LOD | 根据屏幕占比选择 | 直观 | 需要预计算 |

**LOD 与空间结构的结合：**

- 八叉树/BVH 的节点可存储不同 LOD 的几何数据
- 节点距离相机远时，直接渲染简化版本甚至合并为 Impostor（ billboard 贴图）

---

### 1.7 各数据结构复杂度对比

| 数据结构 | 构建 | 插入 | 删除 | 范围查询 | 最近邻 | 适用场景 |
|---------|------|------|------|---------|--------|---------|
| 均匀网格 | O(n) | O(1) | O(1) | O(1+k) | O(m) | 均匀分布、粒子 |
| 四叉树 | O(n log n) | O(log n) | O(log n) | O(log n + k) | O(log n) | 2D 地形、GIS |
| 八叉树 | O(n log n) | O(log n) | O(log n) | O(log n + k) | O(log n) | 3D 静态场景 |
| BVH | O(n log n) | O(log n)* | O(log n)* | O(log n + k) | O(log n) | 光线追踪、动态场景 |
| BSP | O(n log n)~O(n²) | O(n) | O(n) | O(log n) | - | 室内场景（传统） |
| KD-Tree | O(n log n) | O(log n) | O(log n) | O(log n + k) | O(log n) | 光线追踪、点云 |

*n = 物体数, k = 查询结果数, m = 每格平均物体数*

*BVH 的动态更新可通过自底向上刷新实现均摊 O(log n)*

### 1.8 多层次裁剪策略与 TLAS/BLAS

对于大型开放世界场景，单一的空间数据结构往往无法满足性能需求。现代引擎采用**多层次裁剪策略**，在不同粒度上使用不同的数据结构：

**层次化裁剪架构：**

| 层次 | 数据结构 | 管理对象 | 更新频率 | 作用 |
|------|---------|---------|---------|------|
| 顶层 | 四叉树 / 八叉树 | 地形块、大区段 | 极低（地形变化时） | 快速排除远距离区域 |
| 中层 | BVH | 静态物体（建筑、植被） | 低（物体添加/移除时） | 精确剔除静态几何 |
| 底层 | AABB 列表 / 均匀网格 | 动态物体（角色、载具） | 每帧 | 快速更新动态物体 |

**TLAS/BLAS 双层结构：**

现代光线追踪 API（DXR、Vulkan Ray Tracing）采用**Top-Level Acceleration Structure (TLAS)** 和 **Bottom-Level Acceleration Structure (BLAS)** 的双层设计：

- **BLAS**：每个静态 Mesh 构建一次，存储三角形网格的空间加速结构。物体变形时需要重建（如骨骼动画后的网格）。
- **TLAS**：每帧重建（或更新），包含场景中所有需要光线追踪的物体实例。每个实例引用一个 BLAS 并携带变换矩阵。

这种分离使得动态物体只需更新 TLAS 中的实例变换，而不必重建整个加速结构，大幅降低了每帧的构建开销。

---

## 2. 代码示例

以下代码是一个完整的、可编译运行的场景图与空间数据结构实现。使用 C++17，无外部依赖。

```cpp
// scene_graph_and_spatial.cpp
// 编译: g++ -std=c++17 -O2 -o scene_graph scene_graph_and_spatial.cpp
// 或:  cl /std:c++17 /O2 scene_graph_and_spatial.cpp

#include <iostream>
#include <vector>
#include <memory>
#include <algorithm>
#include <cmath>
#include <string>
#include <stack>
#include <queue>
#include <limits>
#include <cassert>

// ============================================================================
// 数学基础工具
// ============================================================================

struct Vec3 {
    float x, y, z;
    Vec3() : x(0), y(0), z(0) {}
    Vec3(float x, float y, float z) : x(x), y(y), z(z) {}
    
    Vec3 operator+(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x - o.x, y - o.y, z - o.z); }
    Vec3 operator*(float s) const { return Vec3(x * s, y * s, z * s); }
    Vec3 operator/(float s) const { return Vec3(x / s, y / s, z / s); }
    
    float dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
    Vec3 cross(const Vec3& o) const {
        return Vec3(y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x);
    }
    float length() const { return std::sqrt(x * x + y * y + z * z); }
    float lengthSq() const { return x * x + y * y + z * z; }
    Vec3 normalized() const {
        float len = length();
        if (len > 1e-6f) return *this / len;
        return Vec3(0, 0, 0);
    }
    
    Vec3 operator*(const Vec3& o) const { return Vec3(x * o.x, y * o.y, z * o.z); } // 分量乘
    
    Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
    
    bool operator==(const Vec3& o) const {
        return std::abs(x - o.x) < 1e-5f && std::abs(y - o.y) < 1e-5f && std::abs(z - o.z) < 1e-5f;
    }
    
    friend std::ostream& operator<<(std::ostream& os, const Vec3& v) {
        os << "(" << v.x << ", " << v.y << ", " << v.z << ")";
        return os;
    }
};

// 4x4 矩阵（列主序，与 OpenGL/DirectX 兼容）
struct Mat4 {
    float m[16];
    
    Mat4() { identity(); }
    
    void identity() {
        for (int i = 0; i < 16; ++i) m[i] = (i % 5 == 0) ? 1.0f : 0.0f;
    }
    
    float& operator()(int row, int col) { return m[col * 4 + row]; }
    const float& operator()(int row, int col) const { return m[col * 4 + row]; }
    
    Mat4 operator*(const Mat4& o) const {
        Mat4 r;
        for (int i = 0; i < 4; ++i) {
            for (int j = 0; j < 4; ++j) {
                r(i, j) = 0;
                for (int k = 0; k < 4; ++k) {
                    r(i, j) += (*this)(i, k) * o(k, j);
                }
            }
        }
        return r;
    }
    
    Vec3 transformPoint(const Vec3& p) const {
        float x = m[0]*p.x + m[4]*p.y + m[8]*p.z + m[12];
        float y = m[1]*p.x + m[5]*p.y + m[9]*p.z + m[13];
        float z = m[2]*p.x + m[6]*p.y + m[10]*p.z + m[14];
        float w = m[3]*p.x + m[7]*p.y + m[11]*p.z + m[15];
        return w != 0 ? Vec3(x/w, y/w, z/w) : Vec3(x, y, z);
    }
    
    Vec3 transformVector(const Vec3& v) const {
        return Vec3(
            m[0]*v.x + m[4]*v.y + m[8]*v.z,
            m[1]*v.x + m[5]*v.y + m[9]*v.z,
            m[2]*v.x + m[6]*v.y + m[10]*v.z
        );
    }
    
    static Mat4 translation(const Vec3& t) {
        Mat4 r; r.identity();
        r(0, 3) = t.x; r(1, 3) = t.y; r(2, 3) = t.z;
        return r;
    }
    
    static Mat4 scale(const Vec3& s) {
        Mat4 r; r.identity();
        r(0, 0) = s.x; r(1, 1) = s.y; r(2, 2) = s.z;
        return r;
    }
    
    static Mat4 rotationY(float angleDeg) {
        float rad = angleDeg * 3.14159265f / 180.0f;
        float c = std::cos(rad), s = std::sin(rad);
        Mat4 r; r.identity();
        r(0, 0) = c;  r(0, 2) = s;
        r(2, 0) = -s; r(2, 2) = c;
        return r;
    }
    
    static Mat4 rotationX(float angleDeg) {
        float rad = angleDeg * 3.14159265f / 180.0f;
        float c = std::cos(rad), s = std::sin(rad);
        Mat4 r; r.identity();
        r(1, 1) = c; r(1, 2) = -s;
        r(2, 1) = s; r(2, 2) = c;
        return r;
    }
    
    static Mat4 rotationZ(float angleDeg) {
        float rad = angleDeg * 3.14159265f / 180.0f;
        float c = std::cos(rad), s = std::sin(rad);
        Mat4 r; r.identity();
        r(0, 0) = c; r(0, 1) = -s;
        r(1, 0) = s; r(1, 1) = c;
        return r;
    }
    
    // 提取平移分量
    Vec3 getTranslation() const { return Vec3(m[12], m[13], m[14]); }
};

// ============================================================================
// 包围体
// ============================================================================

struct AABB {
    Vec3 min, max;
    
    AABB() : min(Vec3(0,0,0)), max(Vec3(0,0,0)) {}
    AABB(const Vec3& min, const Vec3& max) : min(min), max(max) {}
    
    static AABB fromPoint(const Vec3& p) { return AABB(p, p); }
    
    void expand(const Vec3& p) {
        min.x = std::min(min.x, p.x); min.y = std::min(min.y, p.y); min.z = std::min(min.z, p.z);
        max.x = std::max(max.x, p.x); max.y = std::max(max.y, p.y); max.z = std::max(max.z, p.z);
    }
    
    void expand(const AABB& o) {
        expand(o.min); expand(o.max);
    }
    
    Vec3 center() const { return (min + max) * 0.5f; }
    Vec3 extent() const { return (max - min) * 0.5f; }
    
    float surfaceArea() const {
        Vec3 e = max - min;
        return 2.0f * (e.x * e.y + e.y * e.z + e.z * e.x);
    }
    
    bool contains(const Vec3& p) const {
        return p.x >= min.x && p.x <= max.x &&
               p.y >= min.y && p.y <= max.y &&
               p.z >= min.z && p.z <= max.z;
    }
    
    bool intersects(const AABB& o) const {
        return min.x <= o.max.x && max.x >= o.min.x &&
               min.y <= o.max.y && max.y >= o.min.y &&
               min.z <= o.max.z && max.z >= o.min.z;
    }
    
    // 变换 AABB（保守估计：变换 8 个角点重新包围）
    AABB transform(const Mat4& mat) const {
        AABB result = AABB::fromPoint(mat.transformPoint(Vec3(min.x, min.y, min.z)));
        result.expand(mat.transformPoint(Vec3(max.x, min.y, min.z)));
        result.expand(mat.transformPoint(Vec3(min.x, max.y, min.z)));
        result.expand(mat.transformPoint(Vec3(max.x, max.y, min.z)));
        result.expand(mat.transformPoint(Vec3(min.x, min.y, max.z)));
        result.expand(mat.transformPoint(Vec3(max.x, min.y, max.z)));
        result.expand(mat.transformPoint(Vec3(min.x, max.y, max.z)));
        result.expand(mat.transformPoint(Vec3(max.x, max.y, max.z)));
        return result;
    }
    
    friend std::ostream& operator<<(std::ostream& os, const AABB& b) {
        os << "AABB[min=" << b.min << ", max=" << b.max << "]";
        return os;
    }
};

struct BoundingSphere {
    Vec3 center;
    float radius;
    
    BoundingSphere() : center(0,0,0), radius(0) {}
    BoundingSphere(const Vec3& c, float r) : center(c), radius(r) {}
    
    bool intersects(const BoundingSphere& o) const {
        float distSq = (center - o.center).lengthSq();
        float rsum = radius + o.radius;
        return distSq <= rsum * rsum;
    }
    
    // 从 AABB 构建包围球
    static BoundingSphere fromAABB(const AABB& box) {
        return BoundingSphere(box.center(), box.extent().length());
    }
};

// ============================================================================
// 场景图节点
// ============================================================================

class SceneNode : public std::enable_shared_from_this<SceneNode> {
public:
    std::string name;
    Vec3 localPosition = Vec3(0, 0, 0);
    Vec3 localRotation = Vec3(0, 0, 0); // Euler angles in degrees
    Vec3 localScale = Vec3(1, 1, 1);
    
    // 世界变换（缓存，脏标记机制）
    mutable Mat4 worldMatrix;
    mutable bool worldDirty = true;
    
    std::weak_ptr<SceneNode> parent;
    std::vector<std::shared_ptr<SceneNode>> children;
    
    // 物体本地包围盒（模型空间）
    AABB localBounds;
    
    SceneNode(const std::string& name = "Node") : name(name) {
        localBounds = AABB(Vec3(-0.5f, -0.5f, -0.5f), Vec3(0.5f, 0.5f, 0.5f));
    }
    
    // 添加子节点
    void addChild(std::shared_ptr<SceneNode> child) {
        if (child->parent.lock()) {
            // 从原父节点移除
            auto oldParent = child->parent.lock();
            auto& siblings = oldParent->children;
            siblings.erase(std::remove(siblings.begin(), siblings.end(), child), siblings.end());
        }
        child->parent = weak_from_this();
        children.push_back(child);
        child->markDirty();
    }
    
    // 标记自身及所有子节点的世界变换为脏
    void markDirty() {
        worldDirty = true;
        for (auto& c : children) {
            c->markDirty();
        }
    }
    
    // 设置局部变换（自动标记脏）
    void setLocalTransform(const Vec3& pos, const Vec3& rot, const Vec3& scl) {
        localPosition = pos;
        localRotation = rot;
        localScale = scl;
        markDirty();
    }
    
    // 计算局部变换矩阵
    Mat4 getLocalMatrix() const {
        Mat4 T = Mat4::translation(localPosition);
        Mat4 Rx = Mat4::rotationX(localRotation.x);
        Mat4 Ry = Mat4::rotationY(localRotation.y);
        Mat4 Rz = Mat4::rotationZ(localRotation.z);
        Mat4 S = Mat4::scale(localScale);
        // 顺序: T * Rz * Ry * Rx * S (列主序，从右往左应用)
        return T * Rz * Ry * Rx * S;
    }
    
    // 获取世界变换矩阵（带缓存）
    const Mat4& getWorldMatrix() const {
        if (worldDirty) {
            Mat4 local = getLocalMatrix();
            if (auto p = parent.lock()) {
                worldMatrix = p->getWorldMatrix() * local;
            } else {
                worldMatrix = local;
            }
            worldDirty = false;
        }
        return worldMatrix;
    }
    
    // 获取世界空间包围盒
    AABB getWorldBounds() const {
        return localBounds.transform(getWorldMatrix());
    }
    
    // 获取世界位置（快捷方式）
    Vec3 getWorldPosition() const {
        return getWorldMatrix().getTranslation();
    }
    
    // 遍历所有节点（前序）
    void traverse(std::function<void(SceneNode&)> callback) {
        callback(*this);
        for (auto& c : children) {
            c->traverse(callback);
        }
    }
    
    // 打印场景图结构
    void print(int indent = 0) const {
        std::string prefix(indent * 2, ' ');
        Vec3 wp = const_cast<SceneNode*>(this)->getWorldPosition();
        std::cout << prefix << name << " [local=" << localPosition 
                  << ", world=" << wp << "]" << std::endl;
        for (const auto& c : children) {
            c->print(indent + 1);
        }
    }
};

// ============================================================================
// 八叉树实现
// ============================================================================

template<typename T>
class Octree {
public:
    struct OctreeNode {
        AABB bounds;
        std::vector<std::pair<AABB, T>> objects; // (包围盒, 数据)
        std::unique_ptr<OctreeNode> children[8];
        bool isLeaf = true;
        int depth;
        
        OctreeNode(const AABB& bounds, int depth) : bounds(bounds), depth(depth) {}
    };
    
    std::unique_ptr<OctreeNode> root;
    int maxDepth;
    int maxObjectsPerNode;
    
    Octree(const AABB& worldBounds, int maxDepth = 8, int maxObjects = 8)
        : maxDepth(maxDepth), maxObjectsPerNode(maxObjects) {
        root = std::make_unique<OctreeNode>(worldBounds, 0);
    }
    
    // 插入物体
    void insert(const AABB& bounds, const T& data) {
        insert(root.get(), bounds, data);
    }
    
    // 范围查询：返回与查询框相交的所有物体
    std::vector<T> queryRange(const AABB& range) const {
        std::vector<T> results;
        queryRange(root.get(), range, results);
        return results;
    }
    
    // 点查询：返回包含该点的所有物体
    std::vector<T> queryPoint(const Vec3& point) const {
        std::vector<T> results;
        queryPoint(root.get(), point, results);
        return results;
    }
    
    // 视锥查询：返回与视锥相交的所有物体
    std::vector<T> queryFrustum(const struct Frustum& frustum) const;
    
    // 统计节点数量
    int countNodes() const {
        return countNodes(root.get());
    }
    
    // 统计总物体引用数
    int countObjects() const {
        return countObjects(root.get());
    }
    
private:
    void insert(OctreeNode* node, const AABB& bounds, const T& data) {
        // 如果物体不完全在节点内，也允许插入（或做处理）
        if (!node->bounds.intersects(bounds) && !node->bounds.contains(bounds.center())) {
            // 物体在节点外，保守处理：仍然插入
        }
        
        if (node->isLeaf) {
            node->objects.push_back({bounds, data});
            
            // 需要分裂？
            if ((int)node->objects.size() > maxObjectsPerNode && node->depth < maxDepth) {
                split(node);
            }
        } else {
            // 找到合适的子节点插入
            bool inserted = false;
            for (int i = 0; i < 8; ++i) {
                if (node->children[i] && node->children[i]->bounds.intersects(bounds)) {
                    // 物体可能跨越多个子节点，这里简化：插入第一个相交的
                    // 更精确的做法是插入所有完全包含的，跨界的留在父节点
                    if (node->children[i]->bounds.contains(bounds.min) &&
                        node->children[i]->bounds.contains(bounds.max)) {
                        insert(node->children[i].get(), bounds, data);
                        inserted = true;
                        break;
                    }
                }
            }
            if (!inserted) {
                // 跨越多个子节点，留在当前节点
                node->objects.push_back({bounds, data});
            }
        }
    }
    
    void split(OctreeNode* node) {
        Vec3 center = node->bounds.center();
        Vec3 ext = node->bounds.extent();
        
        // 创建 8 个子节点
        for (int i = 0; i < 8; ++i) {
            Vec3 childMin, childMax;
            // i 的 bit0 = x, bit1 = y, bit2 = z
            childMin.x = (i & 1) ? center.x : node->bounds.min.x;
            childMax.x = (i & 1) ? node->bounds.max.x : center.x;
            childMin.y = (i & 2) ? center.y : node->bounds.min.y;
            childMax.y = (i & 2) ? node->bounds.max.y : center.y;
            childMin.z = (i & 4) ? center.z : node->bounds.min.z;
            childMax.z = (i & 4) ? node->bounds.max.z : center.z;
            
            node->children[i] = std::make_unique<OctreeNode>(
                AABB(childMin, childMax), node->depth + 1);
        }
        
        node->isLeaf = false;
        
        // 重新分配物体
        auto oldObjects = std::move(node->objects);
        node->objects.clear();
        
        for (const auto& [bounds, data] : oldObjects) {
            insert(node, bounds, data);
        }
    }
    
    void queryRange(OctreeNode* node, const AABB& range, std::vector<T>& results) const {
        if (!node || !node->bounds.intersects(range)) return;
        
        for (const auto& [bounds, data] : node->objects) {
            if (bounds.intersects(range)) {
                results.push_back(data);
            }
        }
        
        if (!node->isLeaf) {
            for (int i = 0; i < 8; ++i) {
                if (node->children[i]) {
                    queryRange(node->children[i].get(), range, results);
                }
            }
        }
    }
    
    void queryPoint(OctreeNode* node, const Vec3& point, std::vector<T>& results) const {
        if (!node || !node->bounds.contains(point)) return;
        
        for (const auto& [bounds, data] : node->objects) {
            if (bounds.contains(point)) {
                results.push_back(data);
            }
        }
        
        if (!node->isLeaf) {
            for (int i = 0; i < 8; ++i) {
                if (node->children[i]) {
                    queryPoint(node->children[i].get(), point, results);
                }
            }
        }
    }
    
    int countNodes(OctreeNode* node) const {
        if (!node) return 0;
        int count = 1;
        for (int i = 0; i < 8; ++i) {
            count += countNodes(node->children[i].get());
        }
        return count;
    }
    
    int countObjects(OctreeNode* node) const {
        if (!node) return 0;
        int count = (int)node->objects.size();
        for (int i = 0; i < 8; ++i) {
            count += countObjects(node->children[i].get());
        }
        return count;
    }
};

// ============================================================================
// 视锥体（Frustum）
// ============================================================================

struct Plane {
    Vec3 normal; // 指向外部
    float distance; // 到原点的有符号距离
    
    Plane() : normal(0, 1, 0), distance(0) {}
    Plane(const Vec3& n, float d) : normal(n.normalized()), distance(d) {}
    
    // 从三点构建平面（逆时针为正面）
    static Plane fromPoints(const Vec3& a, const Vec3& b, const Vec3& c) {
        Vec3 n = (b - a).cross(c - a).normalized();
        float d = -n.dot(a);
        return Plane(n, d);
    }
    
    float distanceToPoint(const Vec3& p) const {
        return normal.dot(p) + distance;
    }
    
    // 判断 AABB 与平面的关系
    // 返回: 1=完全在内侧(可见), -1=完全在外侧(剔除), 0=相交
    int classifyAABB(const AABB& box) const {
        // 找到对平面法线方向最正的角点
        Vec3 positiveVertex(
            normal.x > 0 ? box.max.x : box.min.x,
            normal.y > 0 ? box.max.y : box.min.y,
            normal.z > 0 ? box.max.z : box.min.z
        );
        // 找到最负的角点
        Vec3 negativeVertex(
            normal.x > 0 ? box.min.x : box.max.x,
            normal.y > 0 ? box.min.y : box.max.y,
            normal.z > 0 ? box.min.z : box.max.z
        );
        
        float dPos = distanceToPoint(positiveVertex);
        float dNeg = distanceToPoint(negativeVertex);
        
        if (dNeg > 0) return 1;   // 最负的点都在内侧，整个盒子在内
        if (dPos < 0) return -1;  // 最正的点都在外侧，整个盒子在外
        return 0;                  // 相交
    }
    
    // 包围球测试
    int classifySphere(const Vec3& center, float radius) const {
        float dist = distanceToPoint(center);
        if (dist > radius) return 1;
        if (dist < -radius) return -1;
        return 0;
    }
};

struct Frustum {
    // 顺序: 左, 右, 下, 上, 近, 远
    Plane planes[6];
    
    // 从相机参数构建视锥
    static Frustum fromCamera(const Vec3& eye, const Vec3& lookAt, const Vec3& up,
                               float fovDeg, float aspect, float nearPlane, float farPlane) {
        Frustum f;
        Vec3 forward = (lookAt - eye).normalized();
        Vec3 right = forward.cross(up).normalized();
        Vec3 trueUp = right.cross(forward);
        
        float fovRad = fovDeg * 3.14159265f / 180.0f;
        float tanFov = std::tan(fovRad * 0.5f);
        
        float nearHeight = 2.0f * nearPlane * tanFov;
        float nearWidth = nearHeight * aspect;
        float farHeight = 2.0f * farPlane * tanFov;
        float farWidth = farHeight * aspect;
        
        Vec3 nearCenter = eye + forward * nearPlane;
        Vec3 farCenter = eye + forward * farPlane;
        
        // 近平面
        f.planes[4] = Plane(-forward, forward.dot(nearCenter));
        // 远平面
        f.planes[5] = Plane(forward, -forward.dot(farCenter));
        
        // 四个侧面
        Vec3 nearTopLeft = nearCenter + trueUp * (nearHeight * 0.5f) - right * (nearWidth * 0.5f);
        Vec3 nearTopRight = nearCenter + trueUp * (nearHeight * 0.5f) + right * (nearWidth * 0.5f);
        Vec3 nearBottomLeft = nearCenter - trueUp * (nearHeight * 0.5f) - right * (nearWidth * 0.5f);
        Vec3 nearBottomRight = nearCenter - trueUp * (nearHeight * 0.5f) + right * (nearWidth * 0.5f);
        
        Vec3 farTopLeft = farCenter + trueUp * (farHeight * 0.5f) - right * (farWidth * 0.5f);
        
        f.planes[0] = Plane::fromPoints(nearBottomLeft, nearTopLeft, farTopLeft); // 左
        f.planes[1] = Plane::fromPoints(nearTopRight, nearBottomRight, farCenter + trueUp * (farHeight * 0.5f) + right * (farWidth * 0.5f)); // 右
        f.planes[2] = Plane::fromPoints(nearBottomRight, nearBottomLeft, farCenter - trueUp * (farHeight * 0.5f) - right * (farWidth * 0.5f)); // 下
        f.planes[3] = Plane::fromPoints(nearTopLeft, nearTopRight, farTopLeft); // 上
        
        return f;
    }
    
    // 简化版：从 8 个角点构建（用于测试）
    static Frustum fromCorners(const Vec3 corners[8]) {
        Frustum f;
        // 假设 corners[0..3] 是近平面（逆时针），corners[4..7] 是远平面
        f.planes[4] = Plane::fromPoints(corners[0], corners[1], corners[2]); // 近
        f.planes[5] = Plane::fromPoints(corners[4], corners[6], corners[5]); // 远
        f.planes[0] = Plane::fromPoints(corners[0], corners[4], corners[1]); // 左
        f.planes[1] = Plane::fromPoints(corners[2], corners[6], corners[3]); // 右
        f.planes[2] = Plane::fromPoints(corners[0], corners[2], corners[4]); // 下
        f.planes[3] = Plane::fromPoints(corners[1], corners[5], corners[3]); // 上
        return f;
    }
    
    // 测试 AABB 是否在视锥内
    // 返回: true = 可见（完全在内或相交）, false = 完全在外（剔除）
    bool testAABB(const AABB& box) const {
        for (int i = 0; i < 6; ++i) {
            if (planes[i].classifyAABB(box) == -1) {
                return false; // 完全在某个平面的外侧
            }
        }
        return true;
    }
    
    // 测试包围球
    bool testSphere(const Vec3& center, float radius) const {
        for (int i = 0; i < 6; ++i) {
            if (planes[i].classifySphere(center, radius) == -1) {
                return false;
            }
        }
        return true;
    }
};

// 前向声明后的 Octree 视锥查询实现
template<typename T>
std::vector<T> Octree<T>::queryFrustum(const Frustum& frustum) const {
    std::vector<T> results;
    std::queue<OctreeNode*> nodes;
    nodes.push(root.get());
    
    while (!nodes.empty()) {
        OctreeNode* node = nodes.front(); nodes.pop();
        if (!node) continue;
        
        // 快速剔除：节点包围盒与视锥测试
        if (!frustum.testAABB(node->bounds)) continue;
        
        // 收集该节点中的物体
        for (const auto& [bounds, data] : node->objects) {
            if (frustum.testAABB(bounds)) {
                results.push_back(data);
            }
        }
        
        // 继续遍历子节点
        if (!node->isLeaf) {
            for (int i = 0; i < 8; ++i) {
                if (node->children[i]) {
                    nodes.push(node->children[i].get());
                }
            }
        }
    }
    
    return results;
}

// ============================================================================
// BVH 实现
// ============================================================================

template<typename T>
class BVH {
public:
    struct BVHNode {
        AABB bounds;
        std::unique_ptr<BVHNode> left, right;
        int objectIndex = -1; // 叶节点存储物体索引，-1 表示内部节点
        
        bool isLeaf() const { return objectIndex >= 0; }
    };
    
    std::unique_ptr<BVHNode> root;
    std::vector<std::pair<AABB, T>> objects;
    
    BVH() = default;
    
    // 从物体列表构建 BVH
    void build(std::vector<std::pair<AABB, T>>&& objs) {
        objects = std::move(objs);
        if (objects.empty()) return;
        
        std::vector<int> indices(objects.size());
        for (size_t i = 0; i < indices.size(); ++i) indices[i] = (int)i;
        
        root = buildNode(indices, 0, (int)indices.size());
    }
    
    // 射线查询
    bool rayIntersect(const Vec3& origin, const Vec3& dir, float& tMin, T& outData) const {
        if (!root) return false;
        tMin = std::numeric_limits<float>::max();
        bool hit = false;
        T bestData;
        rayIntersectNode(root.get(), origin, dir, tMin, hit, bestData);
        if (hit) outData = bestData;
        return hit;
    }
    
    // 范围查询
    std::vector<T> queryRange(const AABB& range) const {
        std::vector<T> results;
        if (!root) return results;
        queryRangeNode(root.get(), range, results);
        return results;
    }
    
    // 视锥查询
    std::vector<T> queryFrustum(const Frustum& frustum) const {
        std::vector<T> results;
        if (!root) return results;
        queryFrustumNode(root.get(), frustum, results);
        return results;
    }
    
    // 统计节点数
    int countNodes() const {
        return countNodes(root.get());
    }
    
private:
    std::unique_ptr<BVHNode> buildNode(std::vector<int>& indices, int start, int end) {
        auto node = std::make_unique<BVHNode>();
        
        // 计算当前范围的包围盒
        AABB bounds = objects[indices[start]].first;
        for (int i = start + 1; i < end; ++i) {
            bounds.expand(objects[indices[i]].first);
        }
        node->bounds = bounds;
        
        int count = end - start;
        
        // 叶节点条件
        if (count <= 2) {
            node->objectIndex = indices[start];
            // 如果有多个物体，需要特殊处理。这里简化：每个叶节点存一个
            if (count > 1) {
                // 创建右子节点存第二个物体
                node->left = std::make_unique<BVHNode>();
                node->left->bounds = objects[indices[start]].first;
                node->left->objectIndex = indices[start];
                node->right = std::make_unique<BVHNode>();
                node->right->bounds = objects[indices[start + 1]].first;
                node->right->objectIndex = indices[start + 1];
                node->objectIndex = -1; // 变为内部节点
            }
            return node;
        }
        
        // SAH 启发式选择分割轴和位置
        Vec3 extent = bounds.extent();
        int axis = 0;
        if (extent.y > extent.x) axis = 1;
        if (extent.z > extent.y && extent.z > extent.x) axis = 2;
        
        // 按中心点排序
        int mid = start + count / 2;
        std::nth_element(indices.begin() + start, indices.begin() + mid, indices.begin() + end,
            [this, axis](int a, int b) {
                float ca = objects[a].first.center()[axis == 0 ? 'x' : axis == 1 ? 'y' : 'z'];
                float cb = objects[b].first.center()[axis == 0 ? 'x' : axis == 1 ? 'y' : 'z'];
                // 用 switch 避免上面的 trick
                return false; // 占位
            });
        
        // 重新用 lambda 正确实现
        auto cmp = [this, axis](int a, int b) {
            Vec3 ca = objects[a].first.center();
            Vec3 cb = objects[b].first.center();
            return axis == 0 ? ca.x < cb.x : (axis == 1 ? ca.y < cb.y : ca.z < cb.z);
        };
        std::nth_element(indices.begin() + start, indices.begin() + mid, indices.begin() + end, cmp);
        
        node->left = buildNode(indices, start, mid);
        node->right = buildNode(indices, mid, end);
        
        return node;
    }
    
    void rayIntersectNode(BVHNode* node, const Vec3& origin, const Vec3& dir,
                          float& tMin, bool& hit, T& bestData) const {
        if (!node) return;
        
        // 射线-AABB 相交测试（简化版：Slab method）
        if (!rayAABBIntersect(origin, dir, node->bounds, tMin)) return;
        
        if (node->isLeaf()) {
            // 这里简化：假设射线命中
            hit = true;
            bestData = objects[node->objectIndex].second;
            return;
        }
        
        // 优先遍历更近的子节点（这里简化：先左后右）
        rayIntersectNode(node->left.get(), origin, dir, tMin, hit, bestData);
        rayIntersectNode(node->right.get(), origin, dir, tMin, hit, bestData);
    }
    
    bool rayAABBIntersect(const Vec3& origin, const Vec3& dir, const AABB& box, float tMax) const {
        float tmin = 0.0f, tmax = tMax;
        
        for (int i = 0; i < 3; ++i) {
            float invD = 1.0f / (i == 0 ? dir.x : i == 1 ? dir.y : dir.z);
            float t0 = ((i == 0 ? box.min.x : i == 1 ? box.min.y : box.min.z) - 
                       (i == 0 ? origin.x : i == 1 ? origin.y : origin.z)) * invD;
            float t1 = ((i == 0 ? box.max.x : i == 1 ? box.max.y : box.max.z) - 
                       (i == 0 ? origin.x : i == 1 ? origin.y : origin.z)) * invD;
            
            if (invD < 0) std::swap(t0, t1);
            tmin = std::max(tmin, t0);
            tmax = std::min(tmax, t1);
            if (tmax < tmin) return false;
        }
        return true;
    }
    
    void queryRangeNode(BVHNode* node, const AABB& range, std::vector<T>& results) const {
        if (!node || !node->bounds.intersects(range)) return;
        
        if (node->isLeaf()) {
            if (objects[node->objectIndex].first.intersects(range)) {
                results.push_back(objects[node->objectIndex].second);
            }
            return;
        }
        
        queryRangeNode(node->left.get(), range, results);
        queryRangeNode(node->right.get(), range, results);
    }
    
    void queryFrustumNode(BVHNode* node, const Frustum& frustum, std::vector<T>& results) const {
        if (!node) return;
        
        if (!frustum.testAABB(node->bounds)) return;
        
        if (node->isLeaf()) {
            if (frustum.testAABB(objects[node->objectIndex].first)) {
                results.push_back(objects[node->objectIndex].second);
            }
            return;
        }
        
        queryFrustumNode(node->left.get(), frustum, results);
        queryFrustumNode(node->right.get(), frustum, results);
    }
    
    int countNodes(BVHNode* node) const {
        if (!node) return 0;
        return 1 + countNodes(node->left.get()) + countNodes(node->right.get());
    }
};

// ============================================================================
// 均匀网格
// ============================================================================

template<typename T>
class UniformGrid {
public:
    Vec3 origin;      // 网格原点
    Vec3 cellSize;    // 每个单元格的大小
    int cellsX, cellsY, cellsZ;
    
    // 用一维数组存储三维网格
    std::vector<std::vector<std::pair<AABB, T>>> cells;
    
    UniformGrid(const Vec3& origin, const Vec3& worldSize, const Vec3& cellSize)
        : origin(origin), cellSize(cellSize) {
        cellsX = std::max(1, (int)std::ceil(worldSize.x / cellSize.x));
        cellsY = std::max(1, (int)std::ceil(worldSize.y / cellSize.y));
        cellsZ = std::max(1, (int)std::ceil(worldSize.z / cellSize.z));
        cells.resize(cellsX * cellsY * cellsZ);
    }
    
    void insert(const AABB& bounds, const T& data) {
        int minX, minY, minZ, maxX, maxY, maxZ;
        getCellRange(bounds, minX, minY, minZ, maxX, maxY, maxZ);
        
        for (int z = minZ; z <= maxZ; ++z) {
            for (int y = minY; y <= maxY; ++y) {
                for (int x = minX; x <= maxX; ++x) {
                    int idx = getIndex(x, y, z);
                    if (idx >= 0 && idx < (int)cells.size()) {
                        cells[idx].push_back({bounds, data});
                    }
                }
            }
        }
    }
    
    std::vector<T> queryPoint(const Vec3& point) const {
        std::vector<T> results;
        int x = (int)((point.x - origin.x) / cellSize.x);
        int y = (int)((point.y - origin.y) / cellSize.y);
        int z = (int)((point.z - origin.z) / cellSize.z);
        
        if (x < 0 || x >= cellsX || y < 0 || y >= cellsY || z < 0 || z >= cellsZ)
            return results;
        
        int idx = getIndex(x, y, z);
        for (const auto& [bounds, data] : cells[idx]) {
            if (bounds.contains(point)) {
                results.push_back(data);
            }
        }
        return results;
    }
    
    std::vector<T> queryRange(const AABB& range) const {
        std::vector<T> results;
        int minX, minY, minZ, maxX, maxY, maxZ;
        getCellRange(range, minX, minY, minZ, maxX, maxY, maxZ);
        
        for (int z = minZ; z <= maxZ; ++z) {
            for (int y = minY; y <= maxY; ++y) {
                for (int x = minX; x <= maxX; ++x) {
                    int idx = getIndex(x, y, z);
                    if (idx < 0 || idx >= (int)cells.size()) continue;
                    for (const auto& [bounds, data] : cells[idx]) {
                        if (bounds.intersects(range) && 
                            std::find(results.begin(), results.end(), data) == results.end()) {
                            results.push_back(data);
                        }
                    }
                }
            }
        }
        return results;
    }
    
private:
    int getIndex(int x, int y, int z) const {
        return z * cellsY * cellsX + y * cellsX + x;
    }
    
    void getCellRange(const AABB& bounds, int& minX, int& minY, int& minZ,
                      int& maxX, int& maxY, int& maxZ) const {
        minX = std::max(0, (int)((bounds.min.x - origin.x) / cellSize.x));
        minY = std::max(0, (int)((bounds.min.y - origin.y) / cellSize.y));
        minZ = std::max(0, (int)((bounds.min.z - origin.z) / cellSize.z));
        maxX = std::min(cellsX - 1, (int)((bounds.max.x - origin.x) / cellSize.x));
        maxY = std::min(cellsY - 1, (int)((bounds.max.y - origin.y) / cellSize.y));
        maxZ = std::min(cellsZ - 1, (int)((bounds.max.z - origin.z) / cellSize.z));
    }
};

// ============================================================================
// 测试与演示
// ============================================================================

void testSceneGraph() {
    std::cout << "========================================" << std::endl;
    std::cout << "  场景图测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    auto world = std::make_shared<SceneNode>("World");
    auto tank = std::make_shared<SceneNode>("Tank");
    auto turret = std::make_shared<SceneNode>("Turret");
    auto barrel = std::make_shared<SceneNode>("Barrel");
    auto leftTrack = std::make_shared<SceneNode>("LeftTrack");
    auto rightTrack = std::make_shared<SceneNode>("RightTrack");
    
    world->addChild(tank);
    tank->addChild(turret);
    turret->addChild(barrel);
    tank->addChild(leftTrack);
    tank->addChild(rightTrack);
    
    // 设置局部变换
    tank->setLocalTransform(Vec3(10, 0, 5), Vec3(0, 30, 0), Vec3(1, 1, 1));
    turret->setLocalTransform(Vec3(0, 2, 0), Vec3(0, 0, 0), Vec3(1, 1, 1));
    barrel->setLocalTransform(Vec3(0, 0.5f, 1.5f), Vec3(0, 0, 0), Vec3(1, 1, 1));
    leftTrack->setLocalTransform(Vec3(-1.5f, 0, 0), Vec3(0, 0, 0), Vec3(1, 1, 1));
    rightTrack->setLocalTransform(Vec3(1.5f, 0, 0), Vec3(0, 0, 0), Vec3(1, 1, 1));
    
    std::cout << "\n初始场景图：" << std::endl;
    world->print();
    
    // 移动坦克，观察变换继承
    std::cout << "\n坦克向前移动 (10, 0, 5) -> (15, 0, 8)：" << std::endl;
    tank->setLocalTransform(Vec3(15, 0, 8), Vec3(0, 30, 0), Vec3(1, 1, 1));
    world->print();
    
    // 炮塔旋转
    std::cout << "\n炮塔旋转 45 度：" << std::endl;
    turret->setLocalTransform(Vec3(0, 2, 0), Vec3(0, 45, 0), Vec3(1, 1, 1));
    world->print();
    
    // 世界包围盒测试
    std::cout << "\n包围盒测试：" << std::endl;
    tank->traverse([](SceneNode& node) {
        AABB wb = node.getWorldBounds();
        std::cout << "  " << node.name << " world bounds: " << wb << std::endl;
    });
}

void testOctree() {
    std::cout << "\n========================================" << std::endl;
    std::cout << "  八叉树测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    AABB worldBounds(Vec3(-100, -100, -100), Vec3(100, 100, 100));
    Octree<int> octree(worldBounds, 6, 4);
    
    // 插入 100 个随机物体
    std::vector<AABB> objectBounds;
    for (int i = 0; i < 100; ++i) {
        float x = (rand() % 200) - 100.0f;
        float y = (rand() % 200) - 100.0f;
        float z = (rand() % 200) - 100.0f;
        AABB bounds(Vec3(x, y, z), Vec3(x + 5, y + 5, z + 5));
        objectBounds.push_back(bounds);
        octree.insert(bounds, i);
    }
    
    std::cout << "插入 100 个物体" << std::endl;
    std::cout << "八叉树节点数: " << octree.countNodes() << std::endl;
    std::cout << "八叉树总物体引用: " << octree.countObjects() << std::endl;
    
    // 范围查询
    AABB queryRange(Vec3(-20, -20, -20), Vec3(20, 20, 20));
    auto results = octree.queryRange(queryRange);
    std::cout << "范围查询 " << queryRange << " 命中: " << results.size() << " 个物体" << std::endl;
    
    // 点查询
    Vec3 queryPoint(5, 5, 5);
    auto pointResults = octree.queryPoint(queryPoint);
    std::cout << "点查询 " << queryPoint << " 命中: " << pointResults.size() << " 个物体" << std::endl;
}

void testFrustumCulling() {
    std::cout << "\n========================================" << std::endl;
    std::cout << "  视锥剔除测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 创建相机视锥
    Vec3 eye(0, 10, -20);
    Vec3 lookAt(0, 0, 0);
    Vec3 up(0, 1, 0);
    Frustum frustum = Frustum::fromCamera(eye, lookAt, up, 60.0f, 16.0f/9.0f, 0.1f, 100.0f);
    
    // 创建一些测试物体
    struct GameObject { std::string name; AABB bounds; };
    std::vector<GameObject> objects = {
        {"Center_Cube", AABB(Vec3(-2, -2, -2), Vec3(2, 2, 2))},
        {"Far_Left", AABB(Vec3(-50, 0, 0), Vec3(-45, 5, 5))},
        {"Far_Right", AABB(Vec3(45, 0, 0), Vec3(50, 5, 5))},
        {"Behind_Camera", AABB(Vec3(-5, 0, -50), Vec3(5, 5, -40))},
        {"Too_Far", AABB(Vec3(-5, 0, 150), Vec3(5, 5, 155))},
        {"Near_Ground", AABB(Vec3(-10, -1, -10), Vec3(10, 0, 10))},
    };
    
    std::cout << "相机位置: " << eye << ", 看向: " << lookAt << std::endl;
    std::cout << "\n视锥剔除结果：" << std::endl;
    
    int visible = 0, culled = 0;
    for (const auto& obj : objects) {
        bool isVisible = frustum.testAABB(obj.bounds);
        std::cout << "  " << obj.name << ": " << (isVisible ? "VISIBLE" : "CULLED") 
                  << " " << obj.bounds << std::endl;
        if (isVisible) visible++; else culled++;
    }
    
    std::cout << "\n统计: " << visible << " 可见, " << culled << " 被剔除" << std::endl;
    std::cout << "剔除率: " << (culled * 100 / (visible + culled)) << "%" << std::endl;
}

void testBVH() {
    std::cout << "\n========================================" << std::endl;
    std::cout << "  BVH 测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    BVH<int> bvh;
    std::vector<std::pair<AABB, int>> objects;
    
    // 创建 50 个物体
    for (int i = 0; i < 50; ++i) {
        float x = (i % 10) * 10.0f - 50.0f;
        float y = (i / 10) * 10.0f - 25.0f;
        float z = 0.0f;
        objects.push_back({AABB(Vec3(x, y, z), Vec3(x + 5, y + 5, z + 5)), i});
    }
    
    bvh.build(std::move(objects));
    std::cout << "BVH 节点数: " << bvh.countNodes() << std::endl;
    
    // 范围查询
    AABB query(Vec3(-10, -10, -5), Vec3(10, 10, 5));
    auto results = bvh.queryRange(query);
    std::cout << "范围查询命中: " << results.size() << " 个物体" << std::endl;
    
    // 视锥查询
    Vec3 eye(0, 20, -30);
    Frustum frustum = Frustum::fromCamera(eye, Vec3(0, 0, 0), Vec3(0, 1, 0), 60.0f, 16.0f/9.0f, 0.1f, 100.0f);
    auto frustumResults = bvh.queryFrustum(frustum);
    std::cout << "视锥查询命中: " << frustumResults.size() << " 个物体" << std::endl;
}

void testUniformGrid() {
    std::cout << "\n========================================" << std::endl;
    std::cout << "  均匀网格测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    UniformGrid<int> grid(Vec3(-50, -50, -50), Vec3(100, 100, 100), Vec3(10, 10, 10));
    
    // 插入物体
    for (int i = 0; i < 100; ++i) {
        float x = (rand() % 100) - 50.0f;
        float y = (rand() % 100) - 50.0f;
        float z = (rand() % 100) - 50.0f;
        grid.insert(AABB(Vec3(x, y, z), Vec3(x + 3, y + 3, z + 3)), i);
    }
    
    std::cout << "网格大小: " << grid.cellsX << " x " << grid.cellsY << " x " << grid.cellsZ << std::endl;
    std::cout << "总单元格数: " << grid.cells.size() << std::endl;
    
    // 点查询
    auto results = grid.queryPoint(Vec3(0, 0, 0));
    std::cout << "点查询 (0,0,0) 命中: " << results.size() << " 个物体" << std::endl;
    
    // 范围查询
    auto rangeResults = grid.queryRange(AABB(Vec3(-10, -10, -10), Vec3(10, 10, 10)));
    std::cout << "范围查询命中: " << rangeResults.size() << " 个物体" << std::endl;
}

void testBoundingVolumes() {
    std::cout << "\n========================================" << std::endl;
    std::cout << "  包围体测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // AABB 测试
    AABB box1(Vec3(0, 0, 0), Vec3(10, 10, 10));
    AABB box2(Vec3(5, 5, 5), Vec3(15, 15, 15));
    AABB box3(Vec3(20, 20, 20), Vec3(30, 30, 30));
    
    std::cout << "AABB 相交测试：" << std::endl;
    std::cout << "  box1 " << box1 << " vs box2 " << box2 << ": " 
              << (box1.intersects(box2) ? "相交" : "不相交") << std::endl;
    std::cout << "  box1 " << box1 << " vs box3 " << box3 << ": " 
              << (box1.intersects(box3) ? "相交" : "不相交") << std::endl;
    
    // 包围球测试
    BoundingSphere s1(Vec3(0, 0, 0), 5);
    BoundingSphere s2(Vec3(8, 0, 0), 5);
    BoundingSphere s3(Vec3(20, 0, 0), 5);
    
    std::cout << "\n包围球相交测试：" << std::endl;
    std::cout << "  s1(中心" << s1.center << ", r=" << s1.radius << ") vs s2(中心" 
              << s2.center << ", r=" << s2.radius << "): "
              << (s1.intersects(s2) ? "相交" : "不相交") << std::endl;
    std::cout << "  s1 vs s3(中心" << s3.center << ", r=" << s3.radius << "): "
              << (s1.intersects(s3) ? "相交" : "不相交") << std::endl;
    
    // AABB -> 包围球
    BoundingSphere bs = BoundingSphere::fromAABB(box1);
    std::cout << "\nAABB " << box1 << " 的包围球: 中心" << bs.center 
              << ", 半径=" << bs.radius << std::endl;
    
    // 变换测试
    Mat4 rotY30 = Mat4::rotationY(30);
    AABB transformed = box1.transform(rotY30);
    std::cout << "box1 旋转 30 度后: " << transformed << std::endl;
}

void benchmarkComparison() {
    std::cout << "\n========================================" << std::endl;
    std::cout << "  性能对比（简化版）" << std::endl;
    std::cout << "========================================" << std::endl;
    
    const int N = 10000;
    std::cout << "物体数量: " << N << std::endl;
    
    // 准备数据
    std::vector<std::pair<AABB, int>> objects;
    for (int i = 0; i < N; ++i) {
        float x = (rand() % 1000) - 500.0f;
        float y = (rand() % 1000) - 500.0f;
        float z = (rand() % 1000) - 500.0f;
        objects.push_back({AABB(Vec3(x, y, z), Vec3(x + 5, y + 5, z + 5)), i});
    }
    
    // 八叉树
    Octree<int> octree(AABB(Vec3(-600, -600, -600), Vec3(600, 600, 600)), 10, 8);
    for (const auto& [b, d] : objects) octree.insert(b, d);
    std::cout << "八叉树节点数: " << octree.countNodes() << std::endl;
    
    // BVH
    BVH<int> bvh;
    auto objectsCopy = objects;
    bvh.build(std::move(objectsCopy));
    std::cout << "BVH 节点数: " << bvh.countNodes() << std::endl;
    
    // 均匀网格
    UniformGrid<int> grid(Vec3(-600, -600, -600), Vec3(1200, 1200, 1200), Vec3(50, 50, 50));
    for (const auto& [b, d] : objects) grid.insert(b, d);
    
    // 查询测试
    AABB queryRange(Vec3(-50, -50, -50), Vec3(50, 50, 50));
    
    auto octreeResults = octree.queryRange(queryRange);
    auto bvhResults = bvh.queryRange(queryRange);
    auto gridResults = grid.queryRange(queryRange);
    
    std::cout << "\n范围查询结果一致性检查：" << std::endl;
    std::cout << "  八叉树命中: " << octreeResults.size() << std::endl;
    std::cout << "  BVH 命中: " << bvhResults.size() << std::endl;
    std::cout << "  均匀网格命中: " << gridResults.size() << std::endl;
    
    // 视锥查询
    Vec3 eye(0, 100, -200);
    Frustum frustum = Frustum::fromCamera(eye, Vec3(0, 0, 0), Vec3(0, 1, 0), 60.0f, 16.0f/9.0f, 1.0f, 500.0f);
    
    auto octreeFrustum = octree.queryFrustum(frustum);
    auto bvhFrustum = bvh.queryFrustum(frustum);
    
    std::cout << "\n视锥剔除结果：" << std::endl;
    std::cout << "  八叉树可见: " << octreeFrustum.size() << " (" 
              << (octreeFrustum.size() * 100 / N) << "%)" << std::endl;
    std::cout << "  BVH 可见: " << bvhFrustum.size() << " (" 
              << (bvhFrustum.size() * 100 / N) << "%)" << std::endl;
}

int main() {
    std::cout << "游戏引擎场景图与空间数据结构演示" << std::endl;
    std::cout << "================================" << std::endl;
    
    srand(42); // 固定种子保证可复现
    
    testSceneGraph();
    testBoundingVolumes();
    testOctree();
    testFrustumCulling();
    testBVH();
    testUniformGrid();
    benchmarkComparison();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  所有测试完成！" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}
```

**运行方式:**

```bash
# Linux/macOS
g++ -std=c++17 -O2 -o scene_graph scene_graph_and_spatial.cpp
./scene_graph

# Windows (MSVC)
cl /std:c++17 /O2 scene_graph_and_spatial.cpp
scene_graph.exe
```

**预期输出:**

```text
游戏引擎场景图与空间数据结构演示
================================
========================================
  场景图测试
========================================

初始场景图：
World [local=(0, 0, 0), world=(0, 0, 0)]
  Tank [local=(10, 0, 5), world=(10, 0, 5)]
    Turret [local=(0, 2, 0), world=(10, 2, 5)]
      Barrel [local=(0, 0.5, 1.5), world=(10, 2.5, 6.5)]
    LeftTrack [local=(-1.5, 0, 0), world=(8.5, 0, 5)]
    RightTrack [local=(1.5, 0, 0), world=(11.5, 0, 5)]

坦克向前移动 (10, 0, 5) -> (15, 0, 8)：
World [local=(0, 0, 0), world=(0, 0, 0)]
  Tank [local=(15, 0, 8), world=(15, 0, 8)]
    Turret [local=(0, 2, 0), world=(15, 2, 8)]
      Barrel [local=(0, 0.5, 1.5), world=(15, 2.5, 9.5)]
    LeftTrack [local=(-1.5, 0, 0), world=(13.5, 0, 8)]
    RightTrack [local=(1.5, 0, 0), world=(16.5, 0, 8)]

炮塔旋转 45 度：
...（炮管位置随旋转更新）...

包围盒测试：
  Tank world bounds: AABB[min=(...), max=(...)]
  Turret world bounds: AABB[min=(...), max=(...)]
  ...

========================================
  包围体测试
========================================
AABB 相交测试：
  box1 AABB[min=(0, 0, 0), max=(10, 10, 10)] vs box2 ...: 相交
  box1 ... vs box3 ...: 不相交

包围球相交测试：
  s1(中心(0, 0, 0), r=5) vs s2(...): 相交
  s1 vs s3(...): 不相交

========================================
  八叉树测试
========================================
插入 100 个物体
八叉树节点数: ...
八叉树总物体引用: ...
范围查询 ... 命中: ... 个物体
点查询 ... 命中: ... 个物体

========================================
  视锥剔除测试
========================================
相机位置: (0, 10, -20), 看向: (0, 0, 0)

视锥剔除结果：
  Center_Cube: VISIBLE ...
  Far_Left: CULLED ...
  Far_Right: CULLED ...
  Behind_Camera: CULLED ...
  Too_Far: CULLED ...
  Near_Ground: VISIBLE ...

统计: 2 可见, 4 被剔除
剔除率: 66%

========================================
  BVH 测试
========================================
BVH 节点数: ...
范围查询命中: ... 个物体
视锥查询命中: ... 个物体

========================================
  均匀网格测试
========================================
网格大小: 10 x 10 x 10
总单元格数: 1000
点查询 (0,0,0) 命中: ... 个物体
范围查询命中: ... 个物体

========================================
  性能对比（简化版）
========================================
物体数量: 10000
八叉树节点数: ...
BVH 节点数: ...

范围查询结果一致性检查：
  八叉树命中: ...
  BVH 命中: ...
  均匀网格命中: ...

视锥剔除结果：
  八叉树可见: ... (%)
  BVH 可见: ... (%)

========================================
  所有测试完成！
========================================
```

---

## 3. 练习

### 练习 1: 场景图扩展（基础）

为 `SceneNode` 添加以下功能：

1. **世界旋转和世界缩放获取**：添加 `getWorldRotation()` 和 `getWorldScale()` 方法。提示：从世界矩阵中提取（注意：非均匀缩放 + 旋转的组合会让这个问题变得复杂，先假设均匀缩放）。

2. **节点查找**：实现 `findNodeByName(const std::string& name)` 方法，支持按名称搜索场景图中的节点。

3. **节点移除**：实现 `removeChild(std::shared_ptr<SceneNode> child)`，安全地将子节点从父节点移除。

### 练习 2: 八叉树光线追踪查询（进阶）

实现八叉树的射线查询功能：

```cpp
// 在 Octree 类中添加
std::vector<T> queryRay(const Vec3& origin, const Vec3& direction, float maxDistance) const;
```

要求：
- 使用 Slab method 测试射线与 AABB 的相交
- 利用八叉树结构快速跳过不相交的节点
- 返回所有与射线相交的物体（按距离排序）

**提示：** 射线与 AABB 相交测试的核心是检查射线在每个轴上的入射/出射参数区间是否有重叠。

### 练习 3: 动态 BVH（挑战，可选）

当前 BVH 实现只支持静态构建。实现一个支持动态更新的 BVH：

1. 每个叶节点存储物体的当前包围盒
2. 当物体移动时，更新其包围盒并自底向上刷新父节点的包围盒
3. 如果物体移出当前叶节点的合理范围，触发局部重建

**思考：** 完全重建 BVH 的代价是多少？增量更新在什么条件下更优？参考 Intel Embree 和 NVIDIA OptiX 的处理策略。

---

## 4. 扩展阅读

### 书籍

- **《Real-Time Rendering, 4th Edition》** — Tomas Akenine-Moller 等
  - 第 19 章：加速算法（空间数据结构、剔除）
  - 第 22 章：场景图与变换层次
  - 这是游戏渲染领域的权威参考书

- **《Game Engine Architecture, 3rd Edition》** — Jason Gregory
  - 第 4.3 节：场景图
  - 第 6.4 节：碰撞检测中的空间划分
  - 第 10 章：渲染引擎中的剔除与 LOD

- **《Physically Based Rendering, 3rd Edition》** — Matt Pharr 等
  - 第 4 章：BVH 和 KD-Tree 的深入讲解
  - 适合对光线追踪加速结构感兴趣的读者

### 论文与文章

- **"Optimized Spatial Hashing for Collision Detection of Deformable Objects"** (Teschner et al., 2003)
  - 空间哈希的经典论文，适合粒子/流体模拟

- **"Fast BVH Construction on GPUs"** (Lauterbach et al., 2009)
  - GPU 并行构建 BVH 的方法

- **"HLBVH: Hierarchical LBVH Construction for Real-Time Ray Tracing"** (Pantaleoni & Luebke, 2010)
  - 现代光线追踪引擎的 BVH 构建方案

- **"Imperfect Shadow Maps for Efficient Computation of Indirect Illumination"** (Ritschel et al., 2008)
  - 涉及不规则场景表示的有趣应用

### 开源参考

- **Godot Engine** (`scene/main/node.cpp`, `scene/3d/octree.h`)
  - 相对简单的场景图实现，适合学习

- **Filament** (`libs/ibl`, `libs/utils` 中的空间数据结构)
  - Google 的现代移动端渲染引擎

- **Intel Embree** (`kernels/bvh/`)
  - 工业级光线追踪 BVH，代码质量极高

- **Unreal Engine 4/5** (`Engine/Source/Runtime/Engine/Private/Components/SceneComponent.cpp`)
  - 复杂的商业级场景图，包含组件系统

### 视频教程

- **GDC Vault: "Advanced Graphics Techniques Tutorial"** 系列
  - 每年 GDC 都有最新的剔除和场景管理技术分享

---

## 常见陷阱

- **陷阱 1：欧拉角万向节锁（Gimbal Lock）**
  
  场景图中使用欧拉角（pitch/yaw/roll）表示旋转时，当 pitch = +/- 90 度时会出现万向节锁，丢失一个旋转自由度。
  
  **正确做法：** 内部用四元数（Quaternion）存储旋转，仅在需要时转换为欧拉角显示。矩阵组合时也优先使用四元数插值（Slerp）。

- **陷阱 2：非均匀缩放破坏正交性**
  
  如果父节点有非均匀缩放（如 scale=(2, 1, 1)），子节点的世界旋转矩阵会被"剪切"，导致法线变换错误、包围盒变形。
  
  **正确做法：** 尽量避免非均匀缩放；如果必须支持，法线变换需要使用逆转置矩阵（Normal Matrix = (M^-1)^T）。

- **陷阱 3：AABB 变换后过度膨胀**
  
  旋转后的 AABB 通过 8 个角点重新包围会导致包围盒比实际需要大很多（尤其是细长物体旋转 45 度时）。
  
  **正确做法：** 对旋转频繁的细长物体使用 OBB 或 k-DOP；静态物体可以预计算多个旋转角度的 AABB 取最小包围。

- **陷阱 4：八叉树中物体重叠导致重复引用**
  
  跨越多个子节点的物体会被存储在多个叶节点中，导致查询结果重复。
  
  **正确做法：** 查询结果用 `std::set` 或标记数组去重；或者将跨界物体存储在父节点（loose octree 策略）。

- **陷阱 5：视锥剔除的平面法线方向错误**
  
  视锥平面法线必须一致指向外部（或内部），否则剔除逻辑会反。
  
  **正确做法：** 构建视锥后，用已知在内/外的测试点验证每个平面。可视化视锥是调试的最佳手段。

- **陷阱 6：BVH 构建时 SAH 分割不平衡**
  
  如果物体在空间中极度聚集，中点分割会导致一侧几乎没有物体，树退化。
  
  **正确做法：** 实现完整的 SAH，尝试多个候选分割平面（如物体包围盒的边界），选择代价最小的。或者使用 Binned SAH 近似。

- **陷阱 7：忽略缓存友好性**
  
  指针跳跃（pointer chasing）在八叉树/BVH 遍历中会导致大量缓存未命中。
  
  **正确做法：** 考虑线性化存储（如 Morton Code 排序的 LBVH）；将节点数据紧凑排列；优先遍历与射线相交更近的子节点以提高早期剔除效率。

- **陷阱 8：动态物体与静态空间结构混用**
  
  将频繁移动的物体放入八叉树/BVH 中会导致每帧重建或大量更新。
  
  **正确做法：** 分离静态和动态物体。静态物体用八叉树/BVH，动态物体用均匀网格或每帧重建的简易 BVH。现代引擎通常维护两套系统。
