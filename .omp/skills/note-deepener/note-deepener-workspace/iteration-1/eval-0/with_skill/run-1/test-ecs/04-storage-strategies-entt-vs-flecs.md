# 存储策略对决：Archetype（Flecs）vs Sparse Set（EnTT）

> 基于笔记: drafts/test-ecs.md
> 所属教程: ECS 架构深度剖析
> 章: 4/5

> 回答笔记问题 #2：EnTT 和 Flecs 的区别在哪？

## 四种 ECS 存储策略

要理解 EnTT 和 Flecs 的差异，必须先了解 ECS 的四种主流存储策略 [来源: ECS FAQ - What are the different ways to implement an ECS?](https://github.com/SanderMertens/ecs-faq)：

| 策略 | 核心思想 | 代表库 | 查询速度 | 增删速度 |
|------|---------|--------|---------|---------|
| **Archetype** | 相同 Component 组合的实体存在同一张"表"中 | Flecs, Unity DOTS, Bevy, Unreal Mass | ★★★★★ | ★★★ |
| **Sparse Set** | 每种 Component 独立存储在稀疏集中 | EnTT, Shipyard | ★★★★ | ★★★★★ |
| **Bitset** | Entity ID 作为数组索引 + bitset 标记 | EntityX, Specs | ★★ | ★★★★ |
| **Reactive** | 实体变更事件驱动 | Entitas | ★★★ | ★★ |

EnTT 和 Flecs 分别代表了 Sparse Set 和 Archetype 两种策略的巅峰实现。

## Archetype 策略（Flecs）

### 核心原理

Archetype 的核心思想是：**把所有拥有完全相同 Component 组合的实体归为一组，放在同一张表中**。这张表像一个关系数据库表——Entity 是行，Component 是列。

```
Archetype A: {Position, Velocity}
  Entity | Position.x | Position.y | Position.z | Velocity.dx | Velocity.dy | Velocity.dz
  -------|------------|------------|------------|-------------|-------------|------------
      0  |    1.0     |    2.0     |    0.0     |     0.1     |     0.0     |     0.0
      3  |    5.0     |    0.0     |    1.0     |     0.0     |     0.2     |    -0.1
      7  |   10.0     |    3.0     |    0.0     |    -0.05    |     0.0     |     0.0

Archetype B: {Position, Velocity, Health}
  Entity | Position.x | ... | Velocity.dx | ... | Health.current | Health.maximum
  -------|------------|-----|-------------|-----|----------------|---------------
      1  |    2.0     | ... |     0.0     | ... |      100       |     100
      4  |    7.0     | ... |    -0.2     | ... |       50       |     100

Archetype C: {Position, Mesh}
  ...
```

### 查询流程

当执行 `query<Position, Velocity>()` 时：

1. 找到所有**包含** `Position` 和 `Velocity` 的 Archetype（即 Archetype A 和 B）
2. 遍历这些 Archetype 的所有行
3. 因为组件在 Archetype 中是连续排列的，每次迭代都是线性扫描数组

**关键优势**：不需要检查每个实体是否满足条件——一个 Archetype 中的所有实体必然满足（因为它们有完全相同的组件组合）。这大幅减少了分支预测失败。

### 添加/移除组件的代价

**这是 Archetype 的主要 tradeoff**。当给一个实体添加或删除 Component 时，它必须**从一个 Archetype 迁移到另一个**：

```
Entity 0 在 Archetype A: {Position, Velocity}
给 Entity 0 添加 Health
→ Entity 0 必须移到 Archetype B: {Position, Velocity, Health}
→ 移动过程：从 A 复制 Position 和 Velocity 数据到 B，在 B 中添加 Health
```

这意味着每次组件的增删都可能涉及多次 `memcpy`。对于组件组合在运行时频繁变化的场景（如 Buff/Debuff 系统），这可能成为瓶颈。 [来源: EnTT ECS back and forth Part 2](https://skypjack.github.io/2019-03-07-ecs-baf-part-2/)

### Flecs 特有的优势

Flecs 不仅仅是 Archetype 的实现——它还引入了两个独特特性：

1. **Entity Relationships（实体关系）**：实体之间可以有结构化的关系，如父子关系、所有权关系。这不是通过"组件里存一个 Entity ID"实现的 hack，而是框架原生支持的、可以通过 query 语法直接查询的一等公民。

```cpp
// Flecs 关系查询
auto q = world.query_builder<>()
    .term(flecs::ChildOf, parent_entity)  // parent_entity 的所有子实体
    .build();
```

2. **C99 API 兼容**：Flecs 提供纯 C 接口（C99 实现，C89 兼容接口），可以嵌入到几乎任何平台。同时还提供了现代 C++17 的类型安全包装。

[来源: Flecs README](https://github.com/SanderMertens/flecs) [来源: Flecs Relationships Documentation](https://www.flecs.dev/flecs/md_docs_2Relationships.html)

## Sparse Set 策略（EnTT）

### 核心原理

Sparse Set 使用两层数组来存储每种 Component：

```
Sparse Set<Position>:
  sparse[] = [0, 0, 1, 0, 2, 0, 3]   // 稀疏数组：以 Entity ID 为索引
  packed[] = [1, 4, 5, 9]             // 密集数组：按插入顺序排列

  查询 Entity 5 是否有 Position：
    sparse[5] = 2      → packed[2] = 5，与 Entity 5 匹配 ✓
    
  查询 Entity 2 是否有 Position：
    sparse[2] = 1      → packed[1] = 4 ≠ 2，不匹配 ✗
```

每种 Component 独立拥有自己的 Sparse Set。Component 之间没有耦合——添加 `Health` 到 Entity 0 只修改 Health 的 Sparse Set，不影响 Position 的 Sparse Set。

### 查询流程

EnTT 的查询优化非常精妙：

1. **View**：当查询 `view<Position, Velocity>()` 时，EnTT 选择**最小的** Component 集合作为驱动集合，然后检查其他集合
2. **Group**：EnTT 的 `group` 更进一步——它**主动重排** Component 数组，使得同时拥有这些 Component 的实体排列在一起，实现几乎完美的连续迭代

```cpp
// EnTT 的 view —— 通用查询
auto view = registry.view<Position, Velocity>();
for (auto [entity, pos, vel] : view.each()) {
    pos.x += vel.dx * dt;
    pos.y += vel.dy * dt;
}

// EnTT 的 group —— 预排序的 view
auto group = registry.group<Position, Velocity>();
// 默认保证拥有 Position 和 Velocity 的实体在各自数组中连续排列
// 迭代性能和 Archetype 持平甚至更好（没有跨 Archetype 的跳跃）
```

[来源: EnTT README](https://github.com/skypjack/entt) [来源: EnTT ECS back and forth Part 2](https://skypjack.github.io/2019-03-07-ecs-baf-part-2/)

### 添加/移除组件的代价

**这是 Sparse Set 的主要优势**。因为每种 Component 独立存储：

- 添加 Component = 在目标 Sparse Set 的 packed 数组末尾 push，更新 sparse 数组的索引 → **O(1)**
- 移除 Component = swap-and-pop（将末尾元素交换到被删除位置）→ **O(1)**

不需要移动其他 Component，不需要 memcpy 大量数据。这使得 EnTT 在组件频繁增删的场景中表现优异。

## 全面对比：Flecs vs EnTT

| 维度 | Flecs (Archetype) | EnTT (Sparse Set) |
|------|-------------------|-------------------|
| **语言** | C99 核心 + C++17/11 API | C++17 仅头文件 |
| **存储策略** | Archetype（表） | Sparse Set（稀疏集） |
| **查询迭代** | 极快（跨 Archetype 线性扫描） | 快（View），极快（Group） |
| **增删组件** | 较慢（迁移 Archetype） | 极快（O(1) swap-pop） |
| **组件频繁变动场景** | 不适合 | 非常适合 |
| **组件组合稳定场景** | 极佳 | 很好 |
| **并行支持** | 内置无锁调度器 | 依赖用户使用 flow graph |
| **Entity Relationship** | 原生支持 | 不支持（需要手动实现） |
| **反射/序列化** | 内置 JSON 序列化 | 内置运行时反射 |
| **层级/父子关系** | 原生支持（ChildOf） | 需手动用组件实现 |
| **编译时间** | < 5 秒 | 取决于使用量（header-only） |
| **生产验证** | Hytale, Tempest Rising, The Forge | Minecraft, Diablo II: Resurrected, COD: Vanguard |

### 性能特性对照

```
操作                       Flecs(Archetype)    EnTT(Sparse Set)
─────────────────────────────────────────────────────────────
遍历 query<A,B>             ★★★★★               ★★★★ (View) / ★★★★★ (Group)
添加 Component 到实体        ★★★                  ★★★★★
移除 Component 从实体        ★★★                  ★★★★★
创建实体                    ★★★★                 ★★★★
销毁实体                    ★★★★                 ★★★★★
多线程遍历                  ★★★★★ (自动)          ★★★★ (手动)
内存占用                    ★★★ (可能有碎片)       ★★★★
```

[来源: Flecs FAQ - How is Flecs different from EnTT?](https://www.flecs.dev/flecs/md_docs_2FAQ.html)

## 选择建议

**选择 Flecs 如果**：
- 你的实体组件组合**在运行时比较稳定**（大多数游戏符合）
- 你需要**层级结构**（父/子实体关系）作为一等公民
- 你需要 C 语言兼容性或多语言绑定（C#, Rust, Zig, Lua）
- 你需要内置的**自动多线程调度**
- 你重视**编译速度**（Flecs 编译只需几秒）

**选择 EnTT 如果**：
- 你的实体**组件频繁增减**（如复杂的 Buff/Debuff/状态系统）
- 你已经在使用现代 C++ 生态，且乐于使用模板
- 你需要**完全控制**内存布局和分配策略
- 你不需要层级结构或想自己实现
- 你在 Minecraft 级别的规模需要验证过的性能

**一个常见的混合策略** [推测]：在大项目中，可以用 Flecs 管理"大多稳定的"实体（场景对象、角色、道具），同时在 EnTT 中管理"频繁变动的"临时实体（弹幕、粒子效果、事件对象）。两者通过 Entity ID 映射桥接。

## 下一步

最后一章将回答笔记问题 #3——Unity 的 GameObject-Component 模式与纯 ECS 的本质区别，并总结本教程的关键收获。
