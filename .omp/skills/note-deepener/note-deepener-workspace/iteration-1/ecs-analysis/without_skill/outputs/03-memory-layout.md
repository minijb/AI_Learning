# 3. ECS 内存布局深入

## 来源

- [ECS Back and Forth — Part 2: Archetypes and Sparse Sets (skypjack)](https://skypjack.github.io/2019-03-07-ecs-baf-part-2/)
- [Flecs FAQ: What is an archetype?](https://github.com/SanderMertens/flecs/blob/master/docs/FAQ.md)
- [Building an ECS #2: Archetypes and Vectorization (Sander Mertens)](https://ajmmertens.medium.com/building-an-ecs-2-archetypes-and-vectorization-fe21690805f9)

## 为什么内存布局如此重要

现代 CPU 的速度远远快于内存访问速度。一次 L1 cache 命中约 1ns，而一次主内存访问约 100ns。CPU 通过 prefetching 和 cache lines（通常 64 字节）来缓解这个问题。如果你的数据是**连续的**，CPU 可以一次性将相邻数据加载到 cache 中；如果数据是**散乱的**，每次访问都要等待主内存。

### AoS vs SoA

- **AoS (Array of Structures)**：传统 OOP 方式——每个对象包含所有字段
- **SoA (Structure of Arrays)**：ECS 方式——同类型字段集中在一个数组中

```
AoS（OOP方式）:
┌──────────┬──────────┬──────────┐
│ Player 0 │ Player 1 │ Player 2 │
│ .x .dx   │ .x .dx   │ .x .dx   │
│ .y .dy   │ .y .dy   │ .y .dy   │
│ .hp .ai  │ .hp .ai  │ .hp .ai  │
└──────────┴──────────┴──────────┘
  遍历 movement: 读取 x,dx,y,dy —— 中间夹着 hp,ai（浪费cache line）

SoA（ECS方式）:
Position.x: [0.x, 1.x, 2.x, 3.x, 4.x, ...]
Position.y: [0.y, 1.y, 2.y, 3.y, 4.y, ...]
Velocity:   [0.dx, 0.dy, 1.dx, 1.dy, 2.dx, 2.dy, ...]
Health:     [0.hp, 1.hp, 2.hp, 3.hp, 4.hp, ...]
  遍历 movement: 只读取 Position 和 Velocity 数组（全是有效数据）
```

MovementSystem 不需要 Health 数据——在 AoS 中，每次读取 Position 时，相邻的 Health 数据也被加载到 cache line 中，白白浪费了宝贵的 cache 空间。在 SoA 中，Position 数组是纯粹的位置数据，每条 cache line 都满载有效数据。

## 两大存储模型

### Archetype（原型/原型表）

**代表实现**：Flecs, Unity DOTS, Unreal Mass, Bevy ECS

核心思想：相同 Component 组合的 Entity 存储在同一个 Archetype 中。

```
Archetype A: [Position, Velocity]       ← 只有会动的实体
  Chunk 0: [E0, E1, E2, E3, ...]
  ┌──────────┬──────────┬──────────┬──────────┐
  │ Pos[0-3] │ Vel[0-3] │ Pos[4-7] │ Vel[4-7] │ ← 每个 Column 是连续数组
  └──────────┴──────────┴──────────┴──────────┘

Archetype B: [Position, Health]         ← 静止但有血量的实体
  Chunk 0: [E5, E8, ...]
  ┌──────────┬──────────┐
  │ Pos[5,8] │ HP[5,8]  │
  └──────────┴──────────┘

Archetype C: [Position, Renderable]     ← 纯装饰物
  Chunk 0: [E6, E7, E9, ...]
  ┌──────────┬──────────┐
  │ Pos[6,7] │ Render   │
  └──────────┴──────────┘
```

**优点**：
- 多组件查询快：所需 Entity 全在一个（或少数几个）Archetype 中
- 多线程友好：不同 Archetype 可并行处理
- 内存紧凑：同 Archetype 内无空洞

**缺点**：
- 添加/移除组件时需要**移动**整个 Entity 到新 Archetype（"迁移成本"）
- Archetype 数量可能爆炸（如果有 N 个可选的 boolean-like 组件，理论上可能有 2^N 个组合）
- 碎片化：为不常用的组合也分配了 Archetype

### Sparse Set（稀疏集）

**代表实现**：EnTT

核心思想：每种 Component 类型独立一个 Sparse Set。Sparse Set 由两个数组组成：
- **Sparse Array**（稀疏数组/反向数组）：以 Entity ID 为索引，存储该 Entity 在 Packed Array 中的位置
- **Packed Array**（密集数组/直接数组）：紧密存储所有拥有该 Component 的 Entity 及其 Component 数据

```
Sparse Set for "Position" component:

Sparse Array:                Packed Array:
Index (Entity ID) → Value    Index → (Entity, Position)
[0] → 0                      [0] → (E0, {10,20,30})
[1] → 1                      [1] → (E1, {5, 0, -10})
[2] → invalid                [2] → (E4, {100, 0, 0})
[3] → 2                      
[4] → invalid                
[5] → 3                      [3] → (E5, {0, 0, 0})

查找 Entity 1 是否有 Position:
  packed[sparse[1]].entity == 1  →  packed[1].entity == 1  →  true
迭代所有 Position:
  for (auto& item : packed) { ... }  ← 紧密无空洞！
```

**优点**：
- 添加/移除组件是 O(1)（swap-and-pop）
- 单组件迭代极快（遍历 Packed Array 即可）
- 天然支持 per-component 自定义分配器

**缺点**：
- 多组件查询需要一点额外工作：要么遍历最短的那个 Sparse Set 并在其他 Set 中查找，要么使用 EnTT 的 **Group** 功能
- 多线程不如 Archetype 那样天然"免费"

### 选择：Archetype 还是 Sparse Set？

skypjack 的结论：**两者在正确实现下性能处于同一联盟**，选择更多是**品味问题**。

| 场景 | Archetype (Flecs) 更优 | Sparse Set (EnTT) 更优 |
|------|------------------------|------------------------|
| 单组件迭代 | 好 | **极好**（遍历 Packed Array） |
| 多组件迭代 | **极好**（同 Archetype 内） | 好（Group 优化后可达到极好） |
| 频繁添加/移除组件 | 差（迁移成本） | **极好**（swap-and-pop） |
| 组件组合稳定 | **极好** | 好 |
| 多线程 | **极好**（自然按 Archetype 分） | 好（需手动分区） |
| 组件排序 | 困难 | 容易 |
