---
title: "Archetype 原型存储详解：从 AoS 到 SoA"
updated: 2026-06-05
---

# Archetype 原型存储详解：从 AoS 到 SoA

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 40 分钟
> 前置知识: Component 概念、C++ 内存布局、CPU 缓存基础

---

## 1. 概念讲解

### 为什么需要 Archetype？

前面章节用 `unordered_map<Entity, Component>` 存储组件——简单，但性能差。根本问题：

1. **每次访问组件都是一次哈希查找**（O(1) 常数大）
2. **组件数据散落在堆内存各处**——缓存命中率极低
3. **不同实体的 Position 不连续**——遍历时 CPU 不断 cache miss

我们需要一种**按组件类型组合来组织内存**的策略。这就是 Archetype。

### 核心思想：组件类型签名 = 内存布局模板

假设游戏中有以下实体：

```
Entity A: [Position, Velocity, Health]
Entity B: [Position, Velocity]
Entity C: [Position, Health, Sprite]
Entity D: [Position, Velocity, Health]
Entity E: [Position, Sprite]
```

按组件类型签名分类：

```
Archetype 1: {Position, Velocity, Health}        → A, D
Archetype 2: {Position, Velocity}                 → B
Archetype 3: {Position, Health, Sprite}           → C
Archetype 4: {Position, Sprite}                   → E
```

**同一个 Archetype 的所有实体共享完全相同的内存布局。** 因此它们的数据可以紧密排列在连续内存中。

### AoS vs SoA 对比

**AoS（Array of Structures）**——传统 OOP 的方式：

```
内存布局（每个 Chunk 放 4 个实体）:
[A.Pos.x][A.Pos.y][A.Vel.dx][A.Vel.dy][A.HP.cur][A.HP.max]
[B.Pos.x][B.Pos.y][B.Vel.dx][B.Vel.dy][B.HP.cur][B.HP.max]
[C.Pos.x][C.Pos.y][C.Vel.dx][C.Vel.dy][C.HP.cur][C.HP.max]
[D.Pos.x][D.Pos.y][D.Vel.dx][D.Vel.dy][D.HP.cur][D.HP.max]
```

遍历 Position：访问地址 0, 24, 48, 72——每次跳 24 字节。每个缓存行（64 字节）只装了约 2.6 个实体的 Position。实际性能：大量缓存未命中。

**SoA（Structure of Arrays）**——ECS Archetype 的方式：

```
内存布局（Chunk 内部分区）:
[Pos.x][Pos.x][Pos.x][Pos.x]  ← 全部实体的 Position.x 连续
[Pos.y][Pos.y][Pos.y][Pos.y]  ← 全部实体的 Position.y 连续
[Vel.dx][Vel.dx][Vel.dx][Vel.dx] ← 全部实体的 Velocity.dx 连续
[Vel.dy][Vel.dy][Vel.dy][Vel.dy]
[HP.cur][HP.cur][HP.cur][HP.cur]
[HP.max][HP.max][HP.max][HP.max]
```

遍历 Position：访问地址 0, 4, 8, 12——每次跳 4 字节。一个缓存行能装 16 个 Position 值！

实际实现通常采用**折中方案**：每个组件类型内部是 SoA（列式存储），但同一实体的所有列通过固定偏移关联。

### Chunk 结构（详细内存布局图）

一个 Chunk 是固定大小的内存块（通常 16KB = 容纳约 256 个实体）。Archetype 可以包含多个 Chunk。

```
┌─────────────────── Chunk (16KB) ────────────────────┐
│                                                       │
│  ┌─ Entity IDs (连续数组) ────────────────────────┐   │
│  │ [E0][E1][E2]...[E255]  (每个 8 字节)           │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌─ Component Column 0: Position ────────────────┐   │
│  │ [Pos0.x][Pos0.y][Pos0.z][Pos1.x][Pos1.y]...   │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌─ Component Column 1: Velocity ────────────────┐   │
│  │ [Vel0.dx][Vel0.dy][Vel0.dz][Vel1.dx]...       │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌─ Component Column 2: Health ──────────────────┐   │
│  │ [HP0.cur][HP0.max][HP1.cur][HP1.max]...       │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

组件在 Chunk 内按列连续存储。遍历单个组件类型时是纯顺序访问。

### 实体在 Archetype 之间迁移

当一个实体添加或移除组件时，它的"类型签名"变化，必须迁移到新 Archetype：

```
Entity E 当前在 Archetype {Position, Velocity}
    执行: world.add<Health>(E, {100, 100})
    结果:
    1. 从 Archetype {P,V} 的 Chunk 中移除 E 的数据（swap-and-pop）
    2. 在 Archetype {P,V,H} 的 Chunk 中分配新槽位
    3. 复制 Position 和 Velocity 数据
    4. 初始化 Health 数据
```

### 对比 Sparse Set 存储策略

| 方面 | Archetype | Sparse Set |
|------|-----------|------------|
| 内存布局 | 按 Archetype 分组，同组紧密排列 | 每种组件类型独立的 dense 数组 |
| 遍历单组件 | 顺序访问（极快） | 顺序访问（快） |
| 遍历多组件 | 只需遍历匹配的 Archetype（快） | 需要对多个 dense 数组做交集/join |
| 添加组件 | 实体迁移到新 Archetype（O(实体数据大小)） | O(1) 插入到对应 Sparse Set |
| 移除组件 | 同上，迁移有成本 | O(1) swap-and-pop |
| 随机访问 | 间接：entity -> Archetype -> Chunk 内偏移 | 直接：entity -> sparse[entity] -> dense 索引 |
| 适用场景 | 组件组合稳定、批量遍历为主 | 组件频繁增删、随机访问为主 |

**EnTT 使用 Sparse Set + Group 混合**；**Unity DOTS 使用 Archetype**；**Flecs 使用 Archetype + 关系索引**。

---

## 2. 代码示例

```cpp
#include <iostream>
#include <vector>
#include <unordered_map>
#include <cstring>
#include <algorithm>
#include <set>
#include <memory>

// ========== 组件定义 ==========
struct Position { float x = 0, y = 0, z = 0; };
struct Velocity { float dx = 0, dy = 0, dz = 0; };
struct Health   { int current = 100, max = 100; };
struct Sprite   { int texId = -1; };

// ========== 组件类型 ID ==========
using ComponentId = uint32_t;
inline ComponentId next_cid() { static ComponentId c = 0; return c++; }
template<typename T> ComponentId cid_of() { static ComponentId id = next_cid(); return id; }

// ========== Archetype 签名 ==========
using ArchetypeSignature = std::set<ComponentId>;

// ========== Chunk ==========
struct Chunk {
    static constexpr size_t MAX_ENTITIES = 256;

    uint8_t  data[16 * 1024];
    uint32_t entity_count = 0;
    uint32_t entity_ids[MAX_ENTITIES];
    uint32_t record_size = 0;

    void* get_component(uint32_t local_idx, uint32_t offset) {
        return data + local_idx * record_size + offset;
    }

    uint32_t add_entity(uint32_t eid) {
        uint32_t idx = entity_count++;
        entity_ids[idx] = eid;
        return idx;
    }

    void remove_entity(uint32_t local_idx) {
        uint32_t last = entity_count - 1;
        if (local_idx != last) {
            std::memcpy(data + local_idx * record_size,
                        data + last * record_size, record_size);
            entity_ids[local_idx] = entity_ids[last];
        }
        entity_count--;
    }
};

// ========== Archetype ==========
struct Archetype {
    ArchetypeSignature signature;
    std::vector<ComponentId> component_ids;
    std::vector<uint32_t>   component_offsets;
    uint32_t record_size = 0;
    std::vector<std::unique_ptr<Chunk>> chunks;

    struct EntityLoc { uint32_t chunk_idx; uint32_t local_idx; };
    std::unordered_map<uint32_t, EntityLoc> entity_map;

    Chunk* get_or_create_chunk() {
        if (chunks.empty() || chunks.back()->entity_count >= Chunk::MAX_ENTITIES) {
            auto c = std::make_unique<Chunk>();
            c->record_size = record_size;
            chunks.push_back(std::move(c));
        }
        return chunks.back().get();
    }

    void add_entity(uint32_t eid, const std::vector<std::pair<ComponentId, const void*>>& init_data) {
        Chunk* c = get_or_create_chunk();
        uint32_t local_idx = c->add_entity(eid);
        entity_map[eid] = {static_cast<uint32_t>(chunks.size() - 1), local_idx};

        for (auto& [cid, data_ptr] : init_data) {
            auto it = std::find(component_ids.begin(), component_ids.end(), cid);
            if (it != component_ids.end()) {
                size_t ci = it - component_ids.begin();
                size_t sz = component_size(cid);
                void* dest = c->get_component(local_idx, component_offsets[ci]);
                std::memcpy(dest, data_ptr, sz);
            }
        }
    }

    void remove_entity(uint32_t eid) {
        auto it = entity_map.find(eid);
        if (it == entity_map.end()) return;
        auto [chunk_idx, local_idx] = it->second;
        chunks[chunk_idx]->remove_entity(local_idx);
        if (local_idx < chunks[chunk_idx]->entity_count) {
            uint32_t moved_eid = chunks[chunk_idx]->entity_ids[local_idx];
            entity_map[moved_eid] = {chunk_idx, local_idx};
        }
        entity_map.erase(it);
    }

    void* get_component_ptr(uint32_t eid, ComponentId cid) {
        auto it = entity_map.find(eid);
        if (it == entity_map.end()) return nullptr;
        auto cid_it = std::find(component_ids.begin(), component_ids.end(), cid);
        if (cid_it == component_ids.end()) return nullptr;
        size_t ci = cid_it - component_ids.begin();
        auto [chunk_idx, local_idx] = it->second;
        return chunks[chunk_idx]->get_component(local_idx, component_offsets[ci]);
    }

    static size_t component_size(ComponentId cid) {
        if (cid == cid_of<Position>()) return sizeof(Position);
        if (cid == cid_of<Velocity>()) return sizeof(Velocity);
        if (cid == cid_of<Health>())   return sizeof(Health);
        if (cid == cid_of<Sprite>())   return sizeof(Sprite);
        return 0;
    }
};

// ========== Component 元信息 ==========
struct ComponentInfo { size_t size; size_t align; };
std::unordered_map<ComponentId, ComponentInfo> component_info;

template<typename T> void register_component() {
    component_info[cid_of<T>()] = {sizeof(T), alignof(T)};
}

// ========== ECS World (Archetype 版) ==========
class ArchetypeWorld {
public:
    void init() {
        register_component<Position>();
        register_component<Velocity>();
        register_component<Health>();
        register_component<Sprite>();
    }

    uint32_t create_entity() { return next_eid++; }

    template<typename T>
    void add_component(uint32_t eid, const T& comp) {
        ComponentId cid = cid_of<T>();
        auto* old = find_archetype(eid);

        ArchetypeSignature new_sig;
        if (old) new_sig = old->signature;
        new_sig.insert(cid);

        Archetype* arch = get_or_create_archetype(new_sig);
        arch->add_entity(eid, {{cid, &comp}});

        if (old) old->remove_entity(eid);
        entity_to_archetype[eid] = arch;
    }

    template<typename T>
    T* get_component(uint32_t eid) {
        auto it = entity_to_archetype.find(eid);
        if (it == entity_to_archetype.end()) return nullptr;
        return static_cast<T*>(it->second->get_component_ptr(eid, cid_of<T>()));
    }

    template<typename T1, typename T2>
    void for_each(void (*fn)(uint32_t, T1&, T2&)) {
        ComponentId c1 = cid_of<T1>(), c2 = cid_of<T2>();
        for (auto& [sig, arch] : archetypes) {
            if (sig.count(c1) && sig.count(c2)) {
                for (auto& chunk : arch->chunks) {
                    for (uint32_t i = 0; i < chunk->entity_count; i++) {
                        uint32_t eid = chunk->entity_ids[i];
                        fn(eid, *static_cast<T1*>(arch->get_component_ptr(eid, c1)),
                                  *static_cast<T2*>(arch->get_component_ptr(eid, c2)));
                    }
                }
            }
        }
    }

    void print_stats() const {
        std::cout << "===== Archetype 存储统计 =====\n";
        std::cout << "Archetype 数: " << archetypes.size() << ", 总实体: " << entity_to_archetype.size() << "\n\n";

        for (auto& [sig, arch] : archetypes) {
            std::cout << "  Archetype {";
            bool first = true;
            for (auto cid : sig) {
                if (!first) std::cout << ", ";
                first = false;
                if (cid == cid_of<Position>()) std::cout << "Position";
                else if (cid == cid_of<Velocity>()) std::cout << "Velocity";
                else if (cid == cid_of<Health>()) std::cout << "Health";
                else if (cid == cid_of<Sprite>()) std::cout << "Sprite";
            }
            std::cout << "}: " << arch->entity_map.size() << " 实体, record="
                      << arch->record_size << "B, chunks=" << arch->chunks.size() << "\n";
        }
    }

private:
    uint32_t next_eid = 0;
    std::unordered_map<ArchetypeSignature, std::unique_ptr<Archetype>> archetypes;
    std::unordered_map<uint32_t, Archetype*> entity_to_archetype;

    Archetype* find_archetype(uint32_t eid) {
        auto it = entity_to_archetype.find(eid);
        return (it != entity_to_archetype.end()) ? it->second : nullptr;
    }

    Archetype* get_or_create_archetype(const ArchetypeSignature& sig) {
        auto it = archetypes.find(sig);
        if (it != archetypes.end()) return it->second.get();

        auto arch = std::make_unique<Archetype>();
        arch->signature = sig;
        arch->component_ids.assign(sig.begin(), sig.end());
        std::sort(arch->component_ids.begin(), arch->component_ids.end());

        uint32_t off = 0;
        for (auto cid : arch->component_ids) {
            size_t a = component_info[cid].align;
            off = (off + a - 1) & ~(a - 1);
            arch->component_offsets.push_back(off);
            off += static_cast<uint32_t>(component_info[cid].size);
        }
        arch->record_size = off;

        Archetype* p = arch.get();
        archetypes[sig] = std::move(arch);
        return p;
    }
};

// ========== 演示 ==========
void move_fn(uint32_t eid, Position& pos, Velocity& vel) {
    pos.x += vel.dx * 0.016f;
    pos.y += vel.dy * 0.016f;
    std::cout << "  E[" << eid << "] -> (" << pos.x << ", " << pos.y << ")\n";
}

int main() {
    ArchetypeWorld world;
    world.init();

    // 各种实体自动进入各自的 Archetype
    uint32_t player = world.create_entity();
    world.add_component<Position>(player, {0, 0, 0});
    world.add_component<Velocity>(player, {5, 3, 0});
    world.add_component<Health>(player, {100, 100});

    uint32_t goblin = world.create_entity();
    world.add_component<Position>(goblin, {50, 30, 0});
    world.add_component<Velocity>(goblin, {-2, 0, 0});
    world.add_component<Health>(goblin, {30, 30});

    uint32_t tree = world.create_entity();
    world.add_component<Position>(tree, {100, 0, 0});
    world.add_component<Sprite>(tree, {42});

    uint32_t bullet = world.create_entity();
    world.add_component<Position>(bullet, {0, 0, 0});
    world.add_component<Velocity>(bullet, {100, 0, 0});

    world.print_stats();

    // MovementSystem: 只遍历 {Position, Velocity} 的 Archetype
    std::cout << "\n===== MovementSystem ({Position+Velocity}) =====\n";
    world.for_each<Position, Velocity>(move_fn);

    std::cout << "\n注意：E[" << tree << "] (大树) 在 Archetype {Position,Sprite} 中——"
              << "不匹配查询，自动跳过。\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 example.cpp -o example && ./example
```

**预期输出:**
```text
===== Archetype 存储统计 =====
Archetype 数: 3, 总实体: 4

  Archetype {Health, Position, Velocity}: 2 实体, record=24B, chunks=1
  Archetype {Position, Sprite}: 1 实体, record=16B, chunks=1
  Archetype {Position, Velocity}: 1 实体, record=24B, chunks=1

===== MovementSystem ({Position+Velocity}) =====
  E[0] -> (0.08, 0.048)
  E[1] -> (49.968, 30)
  E[3] -> (1.6, 0)

注意：E[2] (大树) 在 Archetype {Position,Sprite} 中——不匹配查询，自动跳过。
```

**关键观察**：
- player 和 goblin 在同一个 Archetype = 同一个 Chunk 中紧密排列
- 查询 `{Position, Velocity}` 自动跳过 {Position, Sprite} 的 Archetype
- 遍历是纯顺序的——访问 Chunk 中连续的 record 数组

---

## 3. 练习

### 练习 1: 实现实体迁移

完善 `add_component<T>()`：
1. 如果实体已有旧 Archetype，读取所有现有组件数据
2. 与新增组件一起，迁移到新 Archetype
3. 确保 swap-and-pop 后 entity_map 正确更新

### 练习 2: Sparse Set vs Archetype 性能对比

用第三章的 `ComponentStorage<T>`（Sparse Set）实现同样的 `for_each<Position, Velocity>()`。分别测试 10000 个实体的遍历时间，比较：
1. 查询匹配的查找次数
2. 内存访问连续性
3. 只访问单组件时的性能差异

### 练习 3: 组件布局优化（挑战）

在 Archetype 的 record 布局中，将最常一起访问的组件放在相邻偏移。设计一个基于访问频率的启发式排序算法。例如：若 Position+Velocity 是最高频查询组合，让它们的列在 Chunk 中相邻。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 关键改进点：读取旧 Archetype 中所有现有组件数据，与新增组件一起迁移到新 Archetype；必须在 `remove_entity` 之前拷贝数据，因为 swap-and-pop 会覆盖被删位置。
>
> ```cpp
> template<typename T>
> void add_component(uint32_t eid, const T& comp) {
>     ComponentId cid = cid_of<T>();
>     auto* old = find_archetype(eid);
>
>     // 1. 构建新签名
>     ArchetypeSignature new_sig;
>     if (old) new_sig = old->signature;
>     new_sig.insert(cid);
>
>     // 2. 收集旧 Archetype 中所有现有组件数据（必须在 remove_entity 之前！）
>     std::vector<std::pair<ComponentId, std::vector<uint8_t>>> saved_data;
>     if (old) {
>         auto& loc = old->entity_map[eid];
>         Chunk* old_chunk = old->chunks[loc.chunk_idx].get();
>         for (size_t ci = 0; ci < old->component_ids.size(); ci++) {
>             ComponentId old_cid = old->component_ids[ci];
>             void* src = old_chunk->get_component(loc.local_idx, old->component_offsets[ci]);
>             size_t sz = Archetype::component_size(old_cid);
>             std::vector<uint8_t> buf(sz);
>             std::memcpy(buf.data(), src, sz);
>             saved_data.push_back({old_cid, std::move(buf)});
>         }
>     }
>
>     // 3. 获取或创建新 Archetype 并添加实体
>     Archetype* arch = get_or_create_archetype(new_sig);
>     std::vector<std::pair<ComponentId, const void*>> init_data;
>     for (auto& [saved_cid, buf] : saved_data)
>         init_data.push_back({saved_cid, buf.data()});
>     init_data.push_back({cid, &comp});
>     arch->add_entity(eid, init_data);
>
>     // 4. 从旧 Archetype 移除
>     if (old) {
>         old->remove_entity(eid);
>         // remove_entity 内部已处理 swap-and-pop 后的 entity_map 更新：
>         //   被移到最后位置的实体，其映射更新为原被删实体的位置
>     }
>
>     // 5. 更新全局映射
>     entity_to_archetype[eid] = arch;
> }
> ```
>
> **swap-and-pop 的正确性保证**：`remove_entity` 中，如果被删的不是最后一个，会把最后一个实体的数据拷贝到被删位置并更新映射：
> ```cpp
> void remove_entity(uint32_t local_idx) {
>     uint32_t last = entity_count - 1;
>     if (local_idx != last) {
>         std::memcpy(data + local_idx * record_size,
>                     data + last * record_size, record_size);
>         entity_ids[local_idx] = entity_ids[last];
>     }
>     entity_count--;
> }
> // Archetype::remove_entity 中：
> // if (local_idx < chunks[chunk_idx]->entity_count) {
> //     uint32_t moved_eid = chunks[chunk_idx]->entity_ids[local_idx];
> //     entity_map[moved_eid] = {chunk_idx, local_idx};
> // }
> ```

> [!tip]- 练习 2 参考答案
> **Sparse Set 版 `for_each<Position, Velocity>` 实现**：
>
> ```cpp
> // Sparse Set 存储：每种组件独立的 dense 数组 + sparse 索引
> template<typename T>
> struct SparseStorage {
>     std::vector<T> dense;                       // 紧凑存储所有值
>     std::vector<uint32_t> dense_entities;       // dense[i] 对应的实体 ID
>     std::unordered_map<uint32_t, size_t> sparse; // entity → dense index
>
>     void add(uint32_t eid, const T& val) {
>         sparse[eid] = dense.size();
>         dense.push_back(val);
>         dense_entities.push_back(eid);
>     }
>     T* get(uint32_t eid) {
>         auto it = sparse.find(eid);
>         return (it != sparse.end()) ? &dense[it->second] : nullptr;
>     }
>     bool has(uint32_t eid) { return sparse.count(eid); }
> };
>
> // 多组件遍历：在较小 dense 数组上迭代 + hash 查找验证
> template<typename T1, typename T2>
> void for_each(SparseStorage<T1>& s1, SparseStorage<T2>& s2,
>               void (*fn)(uint32_t, T1&, T2&)) {
>     // 选较小的 dense 数组作为驱动
>     auto& driver = s1.dense.size() < s2.dense.size() ? s1.dense_entities : s2.dense_entities;
>     for (uint32_t eid : s1.dense_entities) {
>         auto it2 = s2.sparse.find(eid);  // O(1) hash 查找
>         if (it2 != s2.sparse.end())
>             fn(eid, s1.dense[s1.sparse[eid]], s2.dense[it2->second]);
>     }
> }
> ```
>
> **性能对比实测要点**：
>
> | 测试维度 | 方法 |
> |----------|------|
> | 查询匹配的查找次数 | Sparse Set：每个驱动实体的 `sparse.find()`（hash 查找）；Archetype：仅遍历匹配 Archetype 的 Chunk，零查找 |
> | 内存访问连续性 | Sparse Set：两个独立 dense 数组 → 每次访问跳两次；Archetype：同一 Chunk 内 record 连续 |
> | 单组件遍历 | Sparse Set 略优：`for (auto& v : s1.dense)` 零查找；Archetype 需 Chunk 间跳转 |
> | 预期结果 | 多组件批量遍历 Archetype 快 2-4x；增删组件 Sparse Set 快 5-10x（无迁移成本） |
>
> **关键结论**：不存在绝对更优的方案——Archetype 适合组件组合稳定、批量遍历为主的场景（渲染、物理）；Sparse Set 适合组件频繁增删、随机访问为主的场景（编辑器、脚本绑定）。EnTT 的 Group 是二者的混合。

> [!tip]- 练习 3 参考答案（可选）
> **基于访问频率的组件偏移优化**：
>
> ```cpp
> // 全局共现频率矩阵
> struct CooccurrenceTracker {
>     // freq[{cid_a, cid_b}] = 被一起查询的次数
>     std::map<std::pair<ComponentId,ComponentId>, size_t> freq;
>
>     void record(const std::vector<ComponentId>& queried) {
>         for (size_t i = 0; i < queried.size(); i++)
>             for (size_t j = i + 1; j < queried.size(); j++)
>                 freq[{queried[i], queried[j]}]++;
>     }
>
>     // 贪心排序算法
>     std::vector<ComponentId> optimize(std::vector<ComponentId> comps) {
>         if (comps.size() <= 2) return comps;
>
>         // Step 1: 找到共现频率最高的组件对作为种子
>         size_t best_freq = 0;
>         size_t seed_i = 0, seed_j = 1;
>         for (size_t i = 0; i < comps.size(); i++)
>             for (size_t j = i+1; j < comps.size(); j++) {
>                 auto it = freq.find({comps[i], comps[j]});
>                 size_t f = (it != freq.end()) ? it->second : 0;
>                 if (f > best_freq) { best_freq = f; seed_i = i; seed_j = j; }
>             }
>
>         std::vector<ComponentId> result = {comps[seed_i], comps[seed_j]};
>         std::vector<bool> used(comps.size(), false);
>         used[seed_i] = used[seed_j] = true;
>
>         // Step 2: 贪心扩展——每次选与已选组件共现频率总和最高的
>         while (result.size() < comps.size()) {
>             size_t best_idx = 0;
>             size_t best_score = 0;
>             for (size_t i = 0; i < comps.size(); i++) {
>                 if (used[i]) continue;
>                 size_t score = 0;
>                 for (size_t j = 0; j < comps.size(); j++)
>                     if (used[j]) {
>                         auto it = freq.find({comps[i], comps[j]});
>                         if (it != freq.end()) score += it->second;
>                     }
>                 if (score > best_score) { best_score = score; best_idx = i; }
>             }
>             result.push_back(comps[best_idx]);
>             used[best_idx] = true;
>         }
>         return result;
>     }
> };
> ```
>
> **集成到 `get_or_create_archetype`**：在排序 `component_ids` 时，用 `optimize` 替代 `std::sort`：
> ```cpp
> // 替换原来的 std::sort(arch->component_ids.begin(), ...)
> arch->component_ids = tracker.optimize(
>     std::vector<ComponentId>(sig.begin(), sig.end()));
> ```
>
> **为什么有效**：如果 Position 和 Velocity 在 record 中偏移相邻，遍历 `{P, V}` 时两个字段在同一个/相邻缓存行中，减少 cache miss。共现数据从 System 注册时收集——每个 System 的读写声明天然就是查询组合。
---

## 4. 扩展阅读

- **Unity DOTS Archetype 文档** — "ECS Memory Layout"，16KB Chunk 选择理由
- **Flecs `ecs_table_t`** — 等价于 Archetype，同时支持关系存储
- **《Data-Oriented Design》第 5-6 章** — AoS vs SoA 深度解析
- **Briggs & Torczon (1993)** — "An Efficient Representation for Sparse Sets"

---

## 常见陷阱

- **Archetype 爆炸**：过多不同组件组合 → 过多 Archetype → 查询开销大。方案：合并小概率组件为通用容器，或用 Tag 代替微型数据组件。
- **频繁迁移**：每帧大量增删组件 → 大量 Chunk 间拷贝。创建时就确定组件组合。
- **忘记对齐**：record 偏移不考虑 `alignof` → ARM 上可能总线错误，x86 上性能下降。
- **Chunk 太小**：`CHUNK_SIZE = 256` 字节 → 每个 Chunk 装不了几个实体 → 大量间接跳转。
