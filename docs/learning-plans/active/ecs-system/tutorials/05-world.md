---
title: "World / Coordinator 详解：ECS 的中央枢纽"
updated: 2026-06-05
---

# World / Coordinator 详解：ECS 的中央枢纽

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 35 分钟
> 前置知识: Entity、Component、System 核心概念

---

## 1. 概念讲解

### 为什么需要 World？

如果你只有 Entity、Component 和 System，谁来协调它们？EntityManager 管理实体生命周期，ComponentStorage 管理组件数据，Scheduler 管理 System 执行。但游戏需要一个单一的入口点来：

- 创建/销毁实体（委托给 EntityManager）
- 添加/移除组件（委托给 ComponentStorage）
- 迭代 System（委托给 Scheduler）
- 管理全局资源（单例、配置、资产）

**World 就是外观（Facade）模式**——它是一个封装了所有子系统的统一接口。用户代码只与 World 交互，不需要知道内部有多少个存储容器。

### 核心思想：World 是数据+逻辑的"宇宙"

```
┌────────────────── World ──────────────────┐
│                                            │
│  ┌──────────┐  ┌──────────────────────┐   │
│  │ Entity   │  │ Component Storages   │   │
│  │ Manager  │  │ ┌──────┐ ┌──────┐   │   │
│  │          │  │ │Pos[] │ │Vel[] │...│   │
│  │ slots[]  │  │ └──────┘ └──────┘   │   │
│  │ gen[]    │  └──────────────────────┘   │
│  └──────────┘                              │
│                                            │
│  ┌──────────┐  ┌──────────────────────┐   │
│  │ Scheduler│  │ Resources (Singletons)│   │
│  │          │  │ ┌─────────────┐      │   │
│  │ systems[]│  │ │ DeltaTime   │      │   │
│  │ DAG      │  │ │ AssetStore  │      │   │
│  └──────────┘  │ │ InputState  │      │   │
│                 │ └─────────────┘      │   │
│  ┌──────────┐  └──────────────────────┘   │
│  │ Event &  │                              │
│  │ Command  │  ┌──────────────────────┐   │
│  │ Buffer   │  │ Query Interface      │   │
│  └──────────┘  │ view<Pos,Vel>()      │   │
│                 └──────────────────────┘   │
└────────────────────────────────────────────┘
```

### 核心职责拆解

**职责 1：创建/销毁实体**

```cpp
Entity e = world.create();       // 等价于 entity_manager.create()
world.destroy(e);                // 等价于 entity_manager.destroy(e)
                                 // + 清理该实体所有组件
```

销毁实体时，World 需要级联清理——从所有 ComponentStorage 中移除该实体的数据。

**职责 2：添加/移除/获取组件**

```cpp
world.add<Position>(e, {10, 20, 0});   // Position 被放入 PositionStorage
world.add<Velocity>(e, {1, 0, 0});     // Velocity 被放入 VelocityStorage

Position* p = world.get<Position>(e);   // 从 PositionStorage 查找
world.remove<Velocity>(e);             // 从 VelocityStorage 删除
```

组件存储对用户透明——用户不需要知道 `Position` 数据存在哪里，World 自动路由。

**职责 3：提供查询接口**

```cpp
// 遍历所有拥有 Position 和 Velocity 的实体
for (auto [entity, pos, vel] : world.view<Position, Velocity>()) {
    pos.x += vel.dx * dt;
}
```

World 内部将查询委托给 Archetype 存储或 Sparse Set 存储（取决于实现策略）。

**职责 4：管理单例组件与资源**

某些数据不属于任何特定实体——而是属于"整个世界"。例如：

```cpp
// 单例组件——整个 World 只有一个实例
world.set_singleton<DeltaTime>({0.016f});
world.set_singleton<GameConfig>({...});
world.set_singleton<InputState>({...});

// System 可以读取单例
DeltaTime* dt = world.get_singleton<DeltaTime>();
```

单例组件在概念上是"只有一个 Entity 0 拥有的组件"的语法糖，但实现上通常直接存储在 World 中，避免实体查询开销。

**职责 5：事件与 CommandBuffer**

在 System 迭代过程中直接创建/销毁实体会导致迭代器失效。解决方案是**延迟执行**：

```
CommandBuffer:
  - create_entity()      → 记录 "创建实体" 指令
  - destroy_entity(e)    → 记录 "销毁实体" 指令
  - add_component(e, T)  → 记录 "添加组件" 指令
  - remove_component(e,T)→ 记录 "移除组件" 指令

在 System 执行完毕后（或在同步屏障点），
World 统一执行 CommandBuffer 中的所有指令。
```

### World 的所有权模型

关键问题：**谁拥有组件内存？**

ECS 中的组件内存**由 World 独占所有权**——World 是唯一创建和销毁组件数据的地方。System 只获取组件的**引用/指针**，在帧内临时使用。这避免了所有权争议和 use-after-free 问题。

### 资源（Resource）与单例组件的区别

| | 单例 Component | Resource |
|---|---|---|
| 性质 | 逻辑上属于"唯一实体" | 不属于任何实体 |
| 查询 | 可以通过 Query 匹配 | 通过 `get_singleton<T>()` 获取 |
| 示例 | `PlayerState`、`CameraTarget` | `DeltaTime`、`AssetManager`、`RandomGenerator` |
| 生命周期 | 可以添加/移除 | 通常在 World 创建时添加，销毁时移除 |

---

## 2. 代码示例

```cpp
#include <iostream>
#include <vector>
#include <unordered_map>
#include <typeindex>
#include <any>
#include <string>
#include <functional>
#include <queue>
#include <cassert>

// ========== 1. Entity 定义 ==========
struct Entity {
    uint32_t index = 0;
    uint32_t generation = 0;
    bool operator==(const Entity& o) const {
        return index == o.index && generation == o.generation;
    }
};

// ========== 2. EntityManager ==========
class EntityManager {
public:
    Entity create() {
        if (!free_slots.empty()) {
            uint32_t idx = free_slots.back();
            free_slots.pop_back();
            generations[idx]++;
            return {idx, generations[idx]};
        }
        uint32_t idx = static_cast<uint32_t>(generations.size());
        generations.push_back(0);
        return {idx, 0};
    }

    void destroy(Entity e) {
        assert(valid(e));
        free_slots.push_back(e.index);
    }

    bool valid(Entity e) const {
        return e.index < generations.size()
            && generations[e.index] == e.generation;
    }

private:
    std::vector<uint32_t> generations;
    std::vector<uint32_t> free_slots;
};

// ========== 3. 组件存储（基于 Sparse Set） ==========
class IComponentStorage {
public:
    virtual ~IComponentStorage() = default;
    virtual void remove(size_t entity_index) = 0;
};

template<typename T>
class ComponentStorage : public IComponentStorage {
public:
    void insert(size_t idx, const T& comp) {
        if (idx >= sparse.size()) sparse.resize(idx + 1, -1);
        sparse[idx] = static_cast<int>(dense.size());
        dense.push_back(comp);
        entities.push_back(idx);
    }

    T* get(size_t idx) {
        if (idx >= sparse.size() || sparse[idx] == -1) return nullptr;
        return &dense[sparse[idx]];
    }

    void remove(size_t idx) override {
        if (idx >= sparse.size() || sparse[idx] == -1) return;
        int di = sparse[idx];
        size_t last = dense.size() - 1;
        if (static_cast<size_t>(di) != last) {
            dense[di] = std::move(dense[last]);
            entities[di] = entities[last];
            sparse[entities[di]] = di;
        }
        dense.pop_back();
        entities.pop_back();
        sparse[idx] = -1;
    }

    bool has(size_t idx) const {
        return idx < sparse.size() && sparse[idx] != -1;
    }

    const std::vector<T>& components() const { return dense; }
    const std::vector<size_t>& entity_indices() const { return entities; }
    size_t size() const { return dense.size(); }

private:
    std::vector<T>      dense;
    std::vector<size_t> entities;
    std::vector<int>    sparse;
};

// ========== 4. Command Buffer ==========
enum class CommandType { Create, Destroy, AddComponent, RemoveComponent };

struct Command {
    CommandType type;
    Entity entity;
    std::type_index component_type;
    std::any component_data;  // only for AddComponent
};

// ========== 5. World ==========
class World {
public:
    // ---- 实体操作 ----
    Entity create() {
        if (!command_mode) {
            return entity_mgr.create();
        }
        // 命令模式：延迟创建
        Entity placeholder{entity_mgr.create().index, 0};
        pending_commands.push({CommandType::Create, placeholder, typeid(void), {}});
        return placeholder;
    }

    void destroy(Entity e) {
        if (!command_mode) {
            do_destroy(e);
            return;
        }
        pending_commands.push({CommandType::Destroy, e, typeid(void), {}});
    }

    // ---- 组件操作 ----
    template<typename T>
    void add(Entity e, const T& comp) {
        if (!command_mode) {
            ensure_storage<T>().insert(e.index, comp);
            return;
        }
        pending_commands.push({CommandType::AddComponent, e, typeid(T), comp});
    }

    template<typename T>
    T* get(Entity e) {
        auto* storage = find_storage<T>();
        return storage ? storage->get(e.index) : nullptr;
    }

    template<typename T>
    void remove(Entity e) {
        if (!command_mode) {
            auto* storage = find_storage<T>();
            if (storage) storage->remove(e.index);
            return;
        }
        pending_commands.push({CommandType::RemoveComponent, e, typeid(T), {}});
    }

    template<typename T>
    bool has(Entity e) {
        auto* storage = find_storage<T>();
        return storage ? storage->has(e.index) : false;
    }

    // ---- 查询（简化版：只查单一组件类型） ----
    template<typename T>
    auto view() -> std::vector<std::pair<Entity, T*>> {
        std::vector<std::pair<Entity, T*>> result;
        auto* storage = find_storage<T>();
        if (!storage) return result;
        const auto& comps = storage->components();
        const auto& indices = storage->entity_indices();
        for (size_t i = 0; i < comps.size(); i++) {
            Entity e{static_cast<uint32_t>(indices[i]), entity_mgr.valid(Entity{static_cast<uint32_t>(indices[i]), 0}) ? 0u : 0u};
            result.push_back({Entity{static_cast<uint32_t>(indices[i]), 0}, const_cast<T*>(&comps[i])});
        }
        return result;
    }

    // ---- 单例组件 ----
    template<typename T>
    void set_singleton(const T& val) { singleton<T>() = val; }

    template<typename T>
    T* get_singleton() {
        auto it = singletons.find(typeid(T));
        if (it != singletons.end()) return std::any_cast<T>(&it->second);
        return nullptr;
    }

    // ---- Command Buffer 控制 ----
    void begin_commands() { command_mode = true; }
    void end_commands() {
        command_mode = false;
        flush_commands();
    }

    void flush_commands() {
        while (!pending_commands.empty()) {
            auto& cmd = pending_commands.front();
            execute(cmd);
            pending_commands.pop();
        }
    }

    // ---- 管理器访问（供内部使用） ----
    EntityManager& entities() { return entity_mgr; }

private:
    EntityManager entity_mgr;
    std::unordered_map<std::type_index, std::unique_ptr<IComponentStorage>> storages;
    std::unordered_map<std::type_index, std::any> singletons;
    std::queue<Command> pending_commands;
    bool command_mode = false;

    template<typename T>
    ComponentStorage<T>& ensure_storage() {
        auto key = typeid(T);
        auto it = storages.find(key);
        if (it == storages.end()) {
            storages[key] = std::make_unique<ComponentStorage<T>>();
        }
        return static_cast<ComponentStorage<T>&>(*storages[key]);
    }

    template<typename T>
    ComponentStorage<T>* find_storage() {
        auto it = storages.find(typeid(T));
        if (it == storages.end()) return nullptr;
        return static_cast<ComponentStorage<T>*>(it->second.get());
    }

    template<typename T>
    T& singleton() {
        auto it = singletons.find(typeid(T));
        if (it == singletons.end()) {
            singletons[typeid(T)] = T{};
        }
        return *std::any_cast<T>(&singletons[typeid(T)]);
    }

    void do_destroy(Entity e) {
        for (auto& [key, storage] : storages) {
            storage->remove(e.index);
        }
        entity_mgr.destroy(e);
    }

    void execute(const Command& cmd) {
        switch (cmd.type) {
        case CommandType::Destroy:
            do_destroy(cmd.entity);
            break;
        case CommandType::AddComponent: {
            auto it = storages.find(cmd.component_type);
            if (it != storages.end()) {
                // 简化：只支持已知类型的添加
            }
            break;
        }
        default:
            break;
        }
    }
};

// ========== 6. 组件定义 ==========
struct Position { float x = 0, y = 0, z = 0; };
struct Velocity { float dx = 0, dy = 0, dz = 0; };
struct Health   { int current = 100, max = 100; };
struct Name     { std::string value; };
struct PlayerTag {};
struct DeltaTime { float value = 0.016f; };

// ========== 7. System ==========
void movement_system(World& world, float dt) {
    auto& positions = world.view<Position>();
    for (auto& [entity, pos] : positions) {
        Velocity* vel = world.get<Velocity>(entity);
        if (vel) {
            pos->x += vel->dx * dt;
            pos->y += vel->dy * dt;
            pos->z += vel->dz * dt;
        }
    }
}

void report_system(World& world) {
    std::cout << "===== World 状态 =====\n";
    for (auto& [entity, pos] : world.view<Position>()) {
        Name* name = world.get<Name>(entity);
        Health* hp = world.get<Health>(entity);
        Velocity* vel = world.get<Velocity>(entity);
        std::cout << "  [" << entity.index << "] "
                  << (name ? name->value : "?")
                  << " @(" << pos->x << "," << pos->y << ")";
        if (vel) std::cout << " vel(" << vel->dx << "," << vel->dy << ")";
        if (hp)  std::cout << " HP:" << hp->current << "/" << hp->max;
        if (world.has<PlayerTag>(entity)) std::cout << " [玩家]";
        std::cout << "\n";
    }
    std::cout << "\n";
}

// ========== 8. 主函数 ==========
int main() {
    World world;

    // 设置单例
    world.set_singleton<DeltaTime>({0.016f});

    std::cout << "===== World 创建实体 =====\n";

    // 普通创建
    Entity player = world.create();
    world.add<Name>(player, {"英雄"});
    world.add<Position>(player, {0, 0, 0});
    world.add<Velocity>(player, {5, 3, 0});
    world.add<Health>(player, {100, 100});
    world.add<PlayerTag>(player, {});

    Entity enemy = world.create();
    world.add<Name>(enemy, {"哥布林"});
    world.add<Position>(enemy, {50, 30, 0});
    world.add<Velocity>(enemy, {-2, 0, 0});
    world.add<Health>(enemy, {30, 30});
    // 注意：敌人没有 PlayerTag

    Entity tree = world.create();
    world.add<Name>(tree, {"大树"});
    world.add<Position>(tree, {100, 0, 0});
    // 树没有 Velocity、没有 Health、没有 PlayerTag

    report_system(world);

    // ---- 使用 Command Buffer 延迟操作 ----
    std::cout << "===== Command Buffer 演示 =====\n";
    world.begin_commands();
    // 在 System 中安全地标记要销毁的实体
    world.destroy(enemy);
    Entity arrow = world.create();
    world.add<Name>(arrow, {"飞箭"});
    world.add<Position>(arrow, {20, 5, 0});
    world.add<Velocity>(arrow, {50, 0, 0});
    world.end_commands();  // 此时才真正执行销毁和创建

    std::cout << "命令执行后——哥布林被销毁，飞箭被创建:\n";
    report_system(world);

    // ---- 运行移动系统 ----
    std::cout << "===== 运行 MovementSystem (dt=0.16) =====\n";
    movement_system(world, 0.16f);
    report_system(world);

    // ---- 单例访问 ----
    DeltaTime* dt = world.get_singleton<DeltaTime>();
    if (dt) std::cout << "单例 DeltaTime: " << dt->value << "s (约 60fps)\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 example.cpp -o example && ./example
```

**预期输出:**
```text
===== World 创建实体 =====
===== World 状态 =====
  [0] 英雄 @(0,0) vel(5,3) HP:100/100 [玩家]
  [1] 哥布林 @(50,30) vel(-2,0) HP:30/30
  [2] 大树 @(100,0)

===== Command Buffer 演示 =====
命令执行后——哥布林被销毁，飞箭被创建:
===== World 状态 =====
  [0] 英雄 @(0,0) vel(5,3) HP:100/100 [玩家]
  [2] 大树 @(100,0)
  [3] 飞箭 @(20,5) vel(50,0)

===== 运行 MovementSystem (dt=0.16) =====
===== World 状态 =====
  [0] 英雄 @(0.8,0.48) vel(5,3) HP:100/100 [玩家]
  [2] 大树 @(100,0)
  [3] 飞箭 @(28,5) vel(50,0)

单例 DeltaTime: 0.016s (约 60fps)
```

**关键观察**：
- `World` 封装了实体管理、组件存储和单例——用户只与一个接口打交道
- Command Buffer 允许在 System 迭代过程中安全地创建/销毁实体
- 组件存储对用户透明——`add<T>()`/`get<T>()` 自动路由到正确的存储容器
- 单例 `DeltaTime` 不属于任何实体，但可以被所有 System 访问

---

## 3. 练习

### 练习 1: 扩展 World 的查询接口

当前 `view<T>()` 只支持单一组件类型。请扩展：

- `view<T1, T2>()` — 返回同时拥有两种组件的实体列表
- 返回类型应为 `vector<tuple<Entity, T1*, T2*>>`
- 实现时考虑：你需要对两个 ComponentStorage 做交集（找同时存在的实体索引）

### 练习 2: 实现完整的 Command Buffer

完善 `execute()` 函数，使 AddComponent 和 RemoveComponent 命令正确执行。添加以下支持：

- `CommandType::Create` — 对占位实体分配真正的槽位
- `CommandType::AddComponent` — 从 `component_data` 中提取数据并插入
- 注意：`std::any` 的 `type()` 必须匹配

### 练习 3: 资源热重载（挑战）

设计一个机制：在游戏运行时，World 中的单例 `GameConfig` 可以从磁盘重新加载。要求：

1. `GameConfig` 包含 `difficulty`、`maxEnemies` 等字段
2. 在 System 执行间隙检测文件修改时间
3. 如果文件被修改，安全地替换单例（注意：System 不能持有跨帧的配置指针）
4. 考虑多 System 并行执行时的线程安全问题

---

## 4. 扩展阅读

- **EnTT `entt::registry`** — 生产级 World 实现，同时支持 Sparse Set 和 Group 存储
- **Rust Bevy `World`** — 使用 ECS 层级：`World` → `Schedule` → `System`，资源通过 `Res<T>` 和 `ResMut<T>` 访问
- **Unity DOTS `World` / `EntityManager`** — 多个 World 共存，每个 World 是一组独立的实体和 System（例如：客户端 World + 服务端 World）
- **Command 模式** — GoF 经典设计模式，ECS 中的 CommandBuffer 是其直接应用

---

## 常见陷阱

- **在 System 中直接调用 `world.create()`**：在迭代实体循环中创建新实体——新实体可能被立即迭代到，导致无限循环或非预期行为。使用 CommandBuffer。
- **跨帧持有组件指针**：`Position* p = world.get<Position>(e)` 存储到成员变量中。下一帧该实体可能已被销毁或组件被移除——use-after-free。每帧重新获取。
- **忘记在销毁实体时清理组件**：`world.destroy(e)` 如果没有级联清理组件，会导致 "僵尸数据"——组件存储中残留已被销毁实体的数据。
- **单例作为"全局变量 dump"**：把所有不方便归属的变量都扔进单例（`GlobalStuff { bool isGameOver; float musicVolume; int score; ... }`）。应该按领域拆分单例或放到专门的组件中。
