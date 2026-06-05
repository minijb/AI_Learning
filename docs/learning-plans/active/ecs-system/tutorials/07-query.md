---
title: "查询与迭代详解：找到对的实体"
updated: 2026-06-05
---

# 查询与迭代详解：找到对的实体

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 35 分钟
> 前置知识: Archetype 存储、System 概念、C++ 迭代器模式

---

## 1. 概念讲解

### 为什么查询是 ECS 的核心操作？

ECS 的性能不只取决于"数据怎么存"，更取决于"怎么找到需要的数据"。如果每次 System 执行都要扫描所有实体并检查 `if (has<A>() && has<B>())`，那么 100 万实体 × 5 个 System × 60fps = 每秒 3 亿次哈希查找——不可接受。

查询（Query）的设计目标：**在迭代开始前，就确定要访问哪些实体和内存区域。**

### 核心思想：从 Archetype 到匹配实体

回顾 Archetype 存储：每个 Archetype 的签名是一组组件类型。

```
Archetype A: {Position, Velocity}         → 1000 个实体
Archetype B: {Position, Velocity, Health} → 500 个实体
Archetype C: {Position, Sprite}           → 3000 个实体
Archetype D: {Velocity, Sprite}           → 200 个实体
```

查询 `(Position, Velocity)` 的处理流程：

1. 检查每个 Archetype 的签名 → A 匹配 ✓，B 匹配 ✓，C 不匹配（缺 Velocity），D 不匹配（缺 Position）
2. 只遍历 A 和 B 的 Chunk
3. 在匹配的 Chunk 内，顺序读取 Position 和 Velocity 列

**不需要实体级别的过滤**——Archetype 级别就完成了筛选。

### Filter vs Query

这两个概念经常被混用，但有不同的含义：

**Query（查询）**：迭代开始前就确定的实体集合。创建时固定了组件需求，在整个迭代期间不会改变。

```cpp
// 创建查询——这之后，组件需求不可变
auto query = world.query<Position, Velocity>();
// 每次迭代用同一个查询对象
for (auto [entity, pos, vel] : query.each()) { ... }
```

**Filter（过滤器）**：在迭代过程中动态决定是否处理某个实体。通常用于排除条件（exclude）或可选条件（optional）。

```cpp
auto query = world.query<Position, Velocity>()
                   .exclude<StaticTag>()       // 排除静态实体
                   .optional<Health>();        // 有 Health 就带上，没有也行
```

### 常见查询模式

**模式 1：包含性查询（With）**

```
查询: Position + Velocity
含义: 实体必须同时拥有这两个组件
匹配: Entity A (P+V), Entity B (P+V+H)  ← B 多出来的 Health 不影响匹配
不匹配: Entity C (P), Entity D (P+S)
```

**模式 2：排除性查询（Without/Exclude）**

```
查询: Position + Velocity, 排除 StaticTag
含义: 可移动的非静态实体
匹配: 有 P+V 但没有 StaticTag 的实体
应用: 移动系统跳过地形、建筑等静态物体
```

**模式 3：可选组件（Optional）**

```
查询: Position, 可选 Health
含义: Position 必须，Health 可选
返回: 对于每个实体，Position 总是有效的引用，Health* 可能为 nullptr
应用: 渲染系统渲染所有可见实体，但如果有 HP 条就画血条 UI
```

**模式 4：变更追踪（Changed Filter）**

```
查询: Position (只处理被修改过的)
含义: 自上次执行本 System 以来 Position 被写过的实体
应用: 网络同步——只发送变化的位置，而非每帧发送所有实体
```

### 迭代器设计

**分组迭代（Chunk-based）**：按 Archetype → Chunk → 实体的三层结构遍历。

```
for archetype in matching_archetypes:
    for chunk in archetype.chunks:
        // 获取组件列的起始指针
        Position* pos_array = chunk.position_column();
        Velocity* vel_array = chunk.velocity_column();
        // 对 Chunk 内所有实体批量处理
        for i in 0..chunk.entity_count:
            process(pos_array[i], vel_array[i]);
```

这样的好处是：内层循环完全在连续内存上进行，CPU 预取器完美工作。

**并行迭代**：同一 Archetype 的不同 Chunk 可以分配给不同线程并行处理。

```cpp
// 并行 for_each
world.parallel_query<Position, Velocity>([](Position& p, const Velocity& v) {
    p.x += v.dx * dt;
    p.y += v.dy * dt;
});
// 框架自动将 Chunk 分配给线程池
```

### 变更追踪的实现

变更追踪需要记录"组件自上次 System 执行后是否被修改过"：

```cpp
// 简化实现：每个 Chunk 维护一个版本号
struct Chunk {
    uint32_t change_version;  // 被任何 System 写入后递增
    // ...
};

// System 记录"上次我看到时的版本号"
struct SystemState {
    uint32_t last_seen_version;
};

// 查询时：只返回 change_version != last_seen_version 的实体
```

这是 ECS 中实现"脏标记"自动化的核心机制。

---

## 2. 代码示例

```cpp
#include <iostream>
#include <vector>
#include <unordered_map>
#include <algorithm>
#include <typeindex>
#include <memory>
#include <cstring>
#include <functional>

// ========== 简化基础设施 ==========
struct Entity { uint32_t id; };

// ---- 组件 ----
struct Position     { float x = 0, y = 0, z = 0; };
struct Velocity     { float dx = 0, dy = 0, dz = 0; };
struct Health       { int current = 100, max = 100; };
struct Sprite       { int texId = -1; };
struct Name         { std::string value; };
struct StaticTag    {};  // 标记静态实体
struct ProjectileTag{};

// ---- Component Storage ----
using ComponentTypeId = size_t;
template<typename T> ComponentTypeId cid() {
    return typeid(T).hash_code();
}

class ComponentStore {
public:
    template<typename T>
    void add(Entity e, const T& c) {
        auto& stor = storage<T>();
        stor.components.push_back(c);
        stor.entities.push_back(e.id);
        stor.entity_to_index[e.id] = stor.components.size() - 1;
    }

    template<typename T>
    T* get(Entity e) {
        auto& stor = storage<T>();
        auto it = stor.entity_to_index.find(e.id);
        return (it != stor.entity_to_index.end()) ? &stor.components[it->second] : nullptr;
    }

    template<typename T>
    bool has(Entity e) const {
        auto& stor = storage<T>();
        return stor.entity_to_index.count(e.id);
    }

    template<typename T>
    const std::vector<T>& view() const { return storage<T>().components; }

    template<typename T>
    size_t count() const { return storage<T>().components.size(); }

private:
    template<typename T>
    struct TypedStorage {
        std::vector<T> components;
        std::vector<uint32_t> entities;
        std::unordered_map<uint32_t, size_t> entity_to_index;
    };
    template<typename T>
    static TypedStorage<T>& storage() {
        static TypedStorage<T> s;
        return s;
    }
    template<typename T>
    static const TypedStorage<T>& storage() {
        static TypedStorage<T> s;
        return s;
    }
};

// ========== Query 表示 ==========
struct QueryDesc {
    std::vector<ComponentTypeId> required;   // 必须存在
    std::vector<ComponentTypeId> excluded;   // 必须不存在
    std::vector<ComponentTypeId> optional;   // 可选存在
};

// ========== 查询结果迭代器 ==========
class QueryResult {
public:
    QueryResult(std::vector<std::pair<Entity, std::vector<void*>>>&& data)
        : rows_(std::move(data)) {}

    // 简化：只支持 2 个组件的情况
    template<typename T1, typename T2>
    void for_each(std::function<void(Entity, T1&, T2&)> fn) {
        for (auto& [entity, ptrs] : rows_) {
            fn(entity, *static_cast<T1*>(ptrs[0]), *static_cast<T2*>(ptrs[1]));
        }
    }

    template<typename T1, typename T2, typename T3>
    void for_each(std::function<void(Entity, T1&, T2&, T3&)> fn) {
        for (auto& [entity, ptrs] : rows_) {
            fn(entity, *static_cast<T1*>(ptrs[0]),
                     *static_cast<T2*>(ptrs[1]),
                     *static_cast<T3*>(ptrs[2]));
        }
    }

    size_t size() const { return rows_.size(); }

private:
    std::vector<std::pair<Entity, std::vector<void*>>> rows_;
};

// ========== World with Query ==========
class World {
public:
    Entity create() { Entity e{next_id++}; alive.push_back(e); return e; }

    template<typename T> void add(Entity e, const T& c) { store.add<T>(e, c); }
    template<typename T> T* get(Entity e) { return store.get<T>(e); }
    template<typename T> bool has(Entity e) const { return store.has<T>(e); }

    // Query 构建器
    QueryResult query(const QueryDesc& desc) {
        std::vector<std::pair<Entity, std::vector<void*>>> results;

        for (auto& e : alive) {
            // 检查必须存在的组件
            bool match = true;
            for (auto cid : desc.required) {
                if (!has_component(e, cid)) { match = false; break; }
            }
            if (!match) continue;

            // 检查必须不存在的组件
            for (auto cid : desc.excluded) {
                if (has_component(e, cid)) { match = false; break; }
            }
            if (!match) continue;

            // 收集组件指针
            std::vector<void*> ptrs;
            for (auto cid : desc.required) {
                ptrs.push_back(get_component_ptr(e, cid));
            }
            for (auto cid : desc.optional) {
                ptrs.push_back(get_component_ptr(e, cid)); // may be nullptr
            }
            results.push_back({e, std::move(ptrs)});
        }
        return QueryResult(std::move(results));
    }

    // 变更追踪——简化版
    template<typename T>
    void mark_changed(Entity e) {
        changed_tracker[cid<T>()].insert(e.id);
    }

    template<typename T>
    bool was_changed(Entity e) const {
        auto it = changed_tracker.find(cid<T>());
        return it != changed_tracker.end() && it->second.count(e.id);
    }

    void reset_changed() { changed_tracker.clear(); }

private:
    uint32_t next_id = 0;
    std::vector<Entity> alive;
    ComponentStore store;
    std::unordered_map<ComponentTypeId, std::unordered_set<uint32_t>> changed_tracker;

    bool has_component(Entity e, ComponentTypeId cid) const {
        if (cid == cid<Position>()) return store.has<Position>(e);
        if (cid == cid<Velocity>()) return store.has<Velocity>(e);
        if (cid == cid<Health>())   return store.has<Health>(e);
        if (cid == cid<Sprite>())   return store.has<Sprite>(e);
        if (cid == cid<Name>())     return store.has<Name>(e);
        if (cid == cid<StaticTag>()) return store.has<StaticTag>(e);
        return false;
    }

    void* get_component_ptr(Entity e, ComponentTypeId cid) {
        if (cid == cid<Position>()) return store.get<Position>(e);
        if (cid == cid<Velocity>()) return store.get<Velocity>(e);
        if (cid == cid<Health>())   return store.get<Health>(e);
        if (cid == cid<Sprite>())   return store.get<Sprite>(e);
        if (cid == cid<Name>())     return store.get<Name>(e);
        return nullptr;
    }
};

// ========== 演示 ==========
int main() {
    World world;

    // 创建不同组合的实体
    Entity player = world.create();
    world.add(player, Name{"英雄"});
    world.add(player, Position{0, 0, 0});
    world.add(player, Velocity{5, 3, 0});
    world.add(player, Health{100, 100});

    Entity goblin = world.create();
    world.add(goblin, Name{"哥布林"});
    world.add(goblin, Position{50, 30, 0});
    world.add(goblin, Velocity{-2, 0, 0});
    world.add(goblin, Health{30, 30});

    Entity tree = world.create();
    world.add(tree, Name{"大树"});
    world.add(tree, Position{100, 0, 0});
    world.add(tree, Sprite{42});
    world.add(tree, StaticTag{});   // 标记为静态

    Entity arrow = world.create();
    world.add(arrow, Name{"飞箭"});
    world.add(arrow, Position{20, 5, 0});
    world.add(arrow, Velocity{50, 0, 0});
    world.add(arrow, ProjectileTag{});
    // 箭没有 Health

    Entity wall = world.create();
    world.add(wall, Name{"石墙"});
    world.add(wall, Position{80, 20, 0});
    world.add(wall, Health{200, 200});
    world.add(wall, StaticTag{});
    // 墙没有 Velocity

    std::cout << "===== 查询模式演示 =====\n\n";

    // 查询 1: 包含性查询——所有可移动物体
    std::cout << "--- 查询 1: {Position, Velocity} (所有可移动物体) ---\n";
    auto movable = world.query(QueryDesc{
        {cid<Position>(), cid<Velocity>()},  // required
        {},                                   // excluded
        {}                                    // optional
    });
    movable.for_each<Position, Velocity>(
        [](Entity e, Position& p, Velocity& v) {
            Name* n = nullptr; // 简化——可选组件
            std::cout << "  E[" << e.id << "] pos=(" << p.x << "," << p.y
                      << ") vel=(" << v.dx << "," << v.dy << ")\n";
        });
    std::cout << "  匹配: " << movable.size() << " 个实体\n\n";

    // 查询 2: 排除性查询——可移动但非静态
    std::cout << "--- 查询 2: {Position, Velocity}, 排除 StaticTag ---\n";
    auto movable_nonstatic = world.query(QueryDesc{
        {cid<Position>(), cid<Velocity>()},
        {cid<StaticTag>()},                  // excluded: 排除静态实体
        {}
    });
    movable_nonstatic.for_each<Position, Velocity>(
        [](Entity e, Position& p, Velocity& v) {
            std::cout << "  E[" << e.id << "] pos=(" << p.x << "," << p.y << ")\n";
        });
    std::cout << "  匹配: " << movable_nonstatic.size() << " 个实体\n";
    std::cout << "  注意：大树(StaticTag)虽然也有Position，但Velocity查询不匹配它；\n";
    std::cout << "        若树有Velocity，StaticTag排除仍会过滤它。\n\n";

    // 查询 3: 可选组件——所有有位置的实体，可选 Health
    std::cout << "--- 查询 3: {Position}, 可选 Health ---\n";
    auto with_pos = world.query(QueryDesc{
        {cid<Position>()},
        {},
        {cid<Health>()}                      // optional
    });
    size_t count_with_hp = 0;
    // 手动迭代
    std::cout << "  所有有位置的实体:\n";
    for (auto& e : {player, goblin, tree, arrow, wall}) {
        Position* p = world.get<Position>(e);
        if (!p) continue;
        Health* hp = world.get<Health>(e);
        Name* n = world.get<Name>(e);
        std::cout << "    " << (n ? n->value : "?") << " @(" << p->x << "," << p->y << ")";
        if (hp) { std::cout << " HP:" << hp->current; count_with_hp++; }
        std::cout << "\n";
    }
    std::cout << "  其中有Health的: " << count_with_hp << " 个\n\n";

    // 查询 4: 变更追踪演示
    std::cout << "--- 查询 4: 变更追踪 ---\n";
    world.mark_changed<Position>(player);
    world.mark_changed<Position>(goblin);

    for (auto& e : {player, goblin, tree, arrow, wall}) {
        if (world.was_changed<Position>(e)) {
            Name* n = world.get<Name>(e);
            std::cout << "  " << (n ? n->value : "?") << " 的 Position 被修改过\n";
        }
    }
    std::cout << "  只有 player 和 goblin 被标记为已修改（模拟MovementSystem写入）\n";
    std::cout << "  网络同步/存档系统可以只处理这些变化的实体。\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 example.cpp -o example && ./example
```

**预期输出:**
```text
===== 查询模式演示 =====

--- 查询 1: {Position, Velocity} (所有可移动物体) ---
  E[0] pos=(0,0) vel=(5,3)
  E[1] pos=(50,30) vel=(-2,0)
  E[3] pos=(20,5) vel=(50,0)
  匹配: 3 个实体

--- 查询 2: {Position, Velocity}, 排除 StaticTag ---
  E[0] pos=(0,0)
  E[1] pos=(50,30)
  E[3] pos=(20,5)
  匹配: 3 个实体
  注意：大树(StaticTag)虽然也有Position，但Velocity查询不匹配它；
        若树有Velocity，StaticTag排除仍会过滤它。

--- 查询 3: {Position}, 可选 Health ---
  所有有位置的实体:
    英雄 @(0,0) HP:100
    哥布林 @(50,30) HP:30
    大树 @(100,0)
    飞箭 @(20,5)
    石墙 @(80,20) HP:200
  其中有Health的: 3 个

--- 查询 4: 变更追踪 ---
  英雄 的 Position 被修改过
  哥布林 的 Position 被修改过
  只有 player 和 goblin 被标记为已修改（模拟MovementSystem写入）
  网络同步/存档系统可以只处理这些变化的实体。
```

**关键观察**：
- 查询 1 自动跳过了树（无 Velocity）和墙（无 Velocity），不需要手动检查
- 查询 2 在查询 1 基础上排除 StaticTag——额外过滤
- 查询 3 展示了可选组件模式：返回所有有 Position 的实体，Health 是可选的
- 变更追踪让 System 只处理变化的数据

---

## 3. 练习

### 练习 1: 实现多组件 for_each

当前 `QueryResult::for_each` 只支持固定数量（2 或 3）的组件参数。请实现一个通用的可变参数版本：

```cpp
template<typename... Components>
void for_each(std::function<void(Entity, Components&...)> fn);
```

### 练习 2: 查询缓存

上面的 `query()` 每次调用都重新扫描所有实体——O(N)。请实现查询缓存：

1. 第一次执行查询时扫描所有实体，缓存匹配的实体列表
2. 当实体增删组件时，自动更新相关的缓存查询（或使缓存失效）
3. 对比有缓存和无缓存的性能

### 练习 3: 变更追踪的生产级实现（挑战）

当前实现用 `unordered_set` 记录每个被修改的实体——不适用于大批量实体。设计一个基于版本号的方案：

1. 每个 Chunk 有一个 `change_version`
2. 每个组件类型有一个全局 `type_version`，每次任何该类型的写入递增
3. System 记录上次执行时的 `type_version`
4. 查询时：该 Chunk 的 `change_version > system_last_seen` → 有变化

---

## 4. 扩展阅读

- **EnTT `entt::view` vs `entt::group`** — view 是"运行时匹配"查询，group 是"拥有权预排序"查询，性能差异可达 3-5 倍
- **Unity DOTS `EntityQuery`** — 使用 `ComponentType.ReadOnly<T>()` 标记只读访问，实现自动依赖排序
- **Flecs Query DSL** — `filter{ position, velocity, !static }` 语法，在 C 中实现的声明式查询

---

## 常见陷阱

- **查询后缓存实体列表但忘记更新**：创建查询对象后，后续创建的新实体不会自动加入。需要定期重建查询或使用观察者模式监听实体变化。
- **optional 和 exclude 混用时顺序敏感**：`optional<Health>` 后 `exclude<DeadTag>`——DeadTag 的排除发生在 optional 之后，不影响。
- **在 for_each 内部修改查询条件**：不能"对这个实体调用 remove<Velocity>()"后在本次迭代中突然让它消失于当前查询——使用 CommandBuffer 延迟。
- **变更追踪的粒度错误**：标记整个 Chunk 为变化 vs 标记每个实体——粒度过粗导致大量"伪变更"，过细导致元数据开销过大。
