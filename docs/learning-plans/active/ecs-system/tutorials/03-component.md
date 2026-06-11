---
title: "Component 详解：纯数据，零行为"
updated: 2026-06-05
---

# Component 详解：纯数据，零行为

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 30 分钟
> 前置知识: Entity 概念、C++ struct 与内存布局、POD 类型

---

## 1. 概念讲解

### 为什么 Component 必须是纯数据？

在 OOP 中，一个典型的"组件"是这样的：

```cpp
class HealthComponent {
    int hp;
public:
    void TakeDamage(int amount) {
        hp -= amount;
        if (hp <= 0) Die();
    }
    void Die() { /* 播放死亡动画、掉落物品、通知成就系统... */ }
};
```

这看起来很方便，但隐藏了三个问题：

**问题 1：隐式依赖。** `Die()` 内部可能引用了 `AnimationSystem`、`InventorySystem`、`AchievementSystem`——你调用 `TakeDamage()`，却触发了三个系统的逻辑。追踪 bug 时你发现伤害计算是对的，但不知道为什么物品掉落了两次。

**问题 2：顺序不可控。** 当多个系统都要访问 `HealthComponent` 时（伤害计算、UI 更新、AI 决策），谁来保证它们以正确的顺序执行？如果伤害系统先扣血、AI 系统后判断"如果血量低就逃跑"，但渲染系统在中间读取了血量——顺序的微妙差别可能导致视觉 bug。

**问题 3：不可并行。** `TakeDamage()` 有副作用（调用其他系统），两个线程不能同时对两个实体调用它，因为不知道内部会访问什么共享状态。

ECS 的回答很简单：**Component 不包含方法。它只是一个带有公开字段的结构体。**

```cpp
// ECS 方式：纯数据
struct Health {
    int current = 100;
    int max = 100;
};
// 所有逻辑在 System 中，显式声明输入输出
```

### 核心思想：POD（Plain Old Data）优先

一个 ECS Component 应该满足 POD 的要求，这意味着：

- **没有虚函数**：没有 vtable 指针，sizeof 是精确的
- **没有构造函数/析构函数（或只有平凡的）**：可以 `memcpy` 安全复制
- **没有继承（或只有空基类）**：内存布局简单可预测
- **没有指针（或只有指向其他 Component 的原始指针）**：不拥有资源

为什么不拥有资源？因为 Component 只描述属性。如果 `struct Sprite { Texture2D* texture; }` 中的 `texture` 由资源管理器统一管理生命周期，那么 Component 只是借用它。**资源的所有权属于 World 或专门的 ResourceManager。**

### 内存布局考量

```
struct Position { float x, y; };     // 8 字节，对齐 4
struct Velocity { float dx, dy; };   // 8 字节
struct Health   { int current, max; };// 8 字节
struct Transform {                    // 36 字节（假设 4 字节对齐）
    float x, y, z;                   // 12 字节
    float qx, qy, qz, qw;            // 16 字节（四元数旋转）
    float sx, sy, sz;                // 12 字节
};
```

**缓存行友好**：一个缓存行是 64 字节。`Position` 只有 8 字节——一个缓存行可以装 8 个 Position。当 System 顺序遍历时，一次内存访问把 8 个实体的位置一起拉入缓存。

**避免填充（padding）**：如果顺序排列 `[float x][padding 4][double value][float y][padding 4]` 因为对齐浪费了大量空间。保持字段类型一致，或按降序排列（大的先，小的后）。

### 组件类型作为编译期标签

在 C++ 中，每个 Component 类型本身就是唯一的标识符——不需要手动分配类型 ID：

```cpp
// 每个 struct 是一个不同的类型，编译器自动区分
struct Position { float x, y; };
struct Velocity { float dx, dy; };
// Position 和 Velocity 即使字段相同，也是完全不同的类型
```

ECS 框架通常用模板和类型系统在编译期注册组件：
```cpp
// 获取组件类型的唯一 ID（运行时）
template<typename T>
ComponentTypeId get_component_type_id() {
    static ComponentTypeId id = next_type_id++;
    return id;
}
```

### 常见组件示例

**游戏逻辑组件：**
```cpp
struct Position    { float x = 0, y = 0, z = 0; };
struct Velocity    { float dx = 0, dy = 0, dz = 0; };
struct Acceleration{ float ax = 0, ay = 0, az = 0; };
struct Health      { int current = 100, max = 100; };
struct Damage      { int amount = 10; float range = 1.0f; };
struct Mana        { int current = 50, max = 50; float regenRate = 1.0f; };
struct Lifetime    { float remaining = 5.0f; }; // 用于临时实体（弹丸、特效）
```

**渲染组件：**
```cpp
struct Sprite      { int textureId = -1; int width = 32, height = 32; };
struct MeshRenderer{ int meshId = -1; int materialId = -1; };
struct Color       { uint8_t r = 255, g = 255, b = 255, a = 255; };
```

**物理组件：**
```cpp
struct RigidBody   { float mass = 1.0f; float restitution = 0.5f; };
struct Collider    { float radius = 1.0f; /* 或 AABB min/max */ };
```

**AI/行为组件：**
```cpp
struct PatrolPath  { std::vector<Position> waypoints; int currentIdx = 0; };
struct Target      { Entity entity; float aggroRange = 10.0f; };
```

### 对比 OOP 的数据+行为混合

| 方面 | OOP Component | ECS Component |
|------|---------------|---------------|
| 内容 | 数据 + 方法 | 只有数据 |
| 大小 | 不确定（vtable + 成员） | 确定的 sizeof |
| 复制 | 需要拷贝构造（深拷贝资源） | memcpy 安全 |
| 序列化 | 需要写序列化函数 | 直接 `fwrite(&comp, sizeof(comp), 1, f)` |
| 测试 | 需要 mock 依赖 | 直接构造值，纯输入输出 |
| 网络同步 | 需要标记脏字段 | 比较两个 struct 的 memcmp |
| 与 System 关系 | System 是 Component 的方法 | System 是独立函数，Component 是参数 |

---

## 2. 代码示例

```cpp
#include <iostream>
#include <vector>
#include <cstring>
#include <typeindex>
#include <unordered_map>
#include <cassert>

// ========== 组件类型 ID 系统 ==========
using ComponentTypeId = uint32_t;

inline ComponentTypeId next_component_type_id() {
    static ComponentTypeId counter = 0;
    return counter++;
}

template<typename T>
ComponentTypeId get_component_type_id() {
    static ComponentTypeId id = next_component_type_id();
    return id;
}

// ========== 组件定义——全部是纯 POD ==========
struct Position {
    float x = 0.0f, y = 0.0f, z = 0.0f;
};
struct Velocity {
    float dx = 0.0f, dy = 0.0f, dz = 0.0f;
};
struct Health {
    int current = 100;
    int max = 100;
};
struct Mana {
    int current = 50;
    int max = 50;
};
struct Damage {
    int amount = 10;
};
struct Sprite {
    int textureId = -1;
    int width = 32, height = 32;
};
struct Lifetime {
    float remaining = 5.0f;
};

// 零大小标签组件
struct PlayerTag {};
struct EnemyTag {};

// ========== 验证 POD 性质 ==========
static_assert(std::is_trivially_copyable_v<Position>, "Position must be trivially copyable");
static_assert(std::is_trivially_copyable_v<Velocity>, "Velocity must be trivially copyable");
static_assert(std::is_trivially_copyable_v<Health>,   "Health must be trivially copyable");

// ========== 组件存储（简化的 per-type vector） ==========
template<typename T>
class ComponentStorage {
public:
    void insert(size_t entity_index, const T& comp) {
        if (entity_index >= sparse.size()) {
            sparse.resize(entity_index + 1, -1);
        }
        sparse[entity_index] = static_cast<int>(dense.size());
        dense.push_back(comp);
        entities.push_back(entity_index);
    }

    void remove(size_t entity_index) {
        int idx = sparse[entity_index];
        if (idx == -1) return;
        // swap-and-pop 删除
        size_t last = dense.size() - 1;
        dense[idx] = dense[last];
        entities[idx] = entities[last];
        sparse[entities[idx]] = idx;
        dense.pop_back();
        entities.pop_back();
        sparse[entity_index] = -1;
    }

    T* get(size_t entity_index) {
        int idx = sparse[entity_index];
        return (idx != -1) ? &dense[idx] : nullptr;
    }

    const T* get(size_t entity_index) const {
        int idx = sparse[entity_index];
        return (idx != -1) ? &dense[idx] : nullptr;
    }

    bool has(size_t entity_index) const {
        return entity_index < sparse.size() && sparse[entity_index] != -1;
    }

    // 遍历所有组件
    const std::vector<T>& components() const { return dense; }
    const std::vector<size_t>& entity_indices() const { return entities; }

    size_t size() const { return dense.size(); }

private:
    std::vector<T>      dense;      // 紧凑存储所有组件数据
    std::vector<size_t> entities;   // dense[i] 对应的实体索引
    std::vector<int>    sparse;     // 从实体索引映射到 dense 索引
};

// ========== 演示 ==========
int main() {
    std::cout << "===== Component 类型 ID 示例 =====\n";
    std::cout << "Position 类型 ID: " << get_component_type_id<Position>() << "\n";
    std::cout << "Velocity 类型 ID: " << get_component_type_id<Velocity>() << "\n";
    std::cout << "Health   类型 ID: " << get_component_type_id<Health>() << "\n";
    std::cout << "Mana     类型 ID: " << get_component_type_id<Mana>() << "\n\n";

    std::cout << "===== Component 大小和对齐 =====\n";
    std::cout << "sizeof(Position):  " << sizeof(Position)  << " bytes (align " << alignof(Position)  << ")\n";
    std::cout << "sizeof(Velocity):  " << sizeof(Velocity)  << " bytes (align " << alignof(Velocity)  << ")\n";
    std::cout << "sizeof(Health):    " << sizeof(Health)    << " bytes (align " << alignof(Health)    << ")\n";
    std::cout << "sizeof(Damage):    " << sizeof(Damage)    << " bytes (align " << alignof(Damage)    << ")\n";
    std::cout << "sizeof(Sprite):    " << sizeof(Sprite)    << " bytes (align " << alignof(Sprite)    << ")\n";
    std::cout << "sizeof(PlayerTag): " << sizeof(PlayerTag) << " bytes (空标签——但 C++ 要求至少 1 字节)\n\n";

    std::cout << "===== Component 存储演示 =====\n";
    ComponentStorage<Position> positions;
    ComponentStorage<Velocity> velocities;
    ComponentStorage<Health>   healths;

    // 用实体索引模拟（简化：直接用索引代替 Entity handle）
    size_t player_idx = 0;
    size_t enemy_idx  = 1;
    size_t bullet_idx = 2;

    // 玩家：Position + Velocity + Health
    positions.insert(player_idx, Position{0, 0, 0});
    velocities.insert(player_idx, Velocity{5, 0, 0});
    healths.insert(player_idx, Health{100, 100});

    // 敌人：Position + Health（无速度——固定炮台）
    positions.insert(enemy_idx, Position{50, 30, 0});
    healths.insert(enemy_idx, Health{80, 80});

    // 子弹：Position + Velocity（无生命值）
    positions.insert(bullet_idx, Position{0, 0, 0});
    velocities.insert(bullet_idx, Velocity{100, 0, 0});

    std::cout << "Position 组件数: " << positions.size() << "\n";
    std::cout << "Velocity 组件数: " << velocities.size() << "\n";
    std::cout << "Health   组件数: " << healths.size() << "\n\n";

    // 检查特定实体的组件
    std::cout << "player 有 Velocity? " << velocities.has(player_idx) << "\n";
    std::cout << "enemy  有 Velocity? " << velocities.has(enemy_idx) << "\n";
    std::cout << "bullet 有 Health?   " << healths.has(bullet_idx) << "\n";

    // 遍历：模拟 MovementSystem
    std::cout << "\n===== 模拟 MovementSystem =====\n";
    for (size_t i = 0; i < positions.size(); i++) {
        size_t e = positions.entity_indices()[i];
        Position& p = const_cast<Position&>(positions.components()[i]);
        Velocity* v = velocities.get(e);
        if (v) {
            float dt = 0.016f; // ~60fps
            p.x += v->dx * dt;
            p.y += v->dy * dt;
            p.z += v->dz * dt;
            std::cout << "Entity[" << e << "] 移动到 (" << p.x << "," << p.y << ")\n";
        } else {
            std::cout << "Entity[" << e << "] 无 Velocity——保持原位\n";
        }
    }

    // 演示 memcpy 安全
    std::cout << "\n===== POD 特性：memcpy 安全 =====\n";
    Position a{1, 2, 3};
    Position b;
    std::memcpy(&b, &a, sizeof(Position));
    std::cout << "memcpy 复制: (" << b.x << "," << b.y << "," << b.z << ") == ("
              << a.x << "," << a.y << "," << a.z << ") ✓\n";

    // 演示序列化
    std::cout << "\n===== 直接序列化（无额外代码） =====\n";
    Health h{75, 100};
    // 可以直接写入文件或网络包
    uint8_t buffer[sizeof(Health)];
    std::memcpy(buffer, &h, sizeof(Health));
    Health h2;
    std::memcpy(&h2, buffer, sizeof(Health));
    std::cout << "序列化/反序列化: Health(" << h2.current << "/" << h2.max << ") ✓\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 example.cpp -o example && ./example
```

**预期输出:**
```text
===== Component 类型 ID 示例 =====
Position 类型 ID: 0
Velocity 类型 ID: 1
Health   类型 ID: 2
Mana     类型 ID: 3

===== Component 大小和对齐 =====
sizeof(Position):  12 bytes (align 4)
sizeof(Velocity):  12 bytes (align 4)
sizeof(Health):    8 bytes (align 4)
sizeof(Damage):    4 bytes (align 4)
sizeof(Sprite):    12 bytes (align 4)
sizeof(PlayerTag): 1 bytes (空标签——但 C++ 要求至少 1 字节)

===== Component 存储演示 =====
Position 组件数: 3
Velocity 组件数: 2
Health   组件数: 2

player 有 Velocity? 1
enemy  有 Velocity? 0
bullet 有 Health?   0

===== 模拟 MovementSystem =====
Entity[0] 移动到 (0.08,0)
Entity[1] 无 Velocity——保持原位
Entity[2] 移动到 (1.6,0)

===== POD 特性：memcpy 安全 =====
memcpy 复制: (1,2,3) == (1,2,3) ✓

===== 直接序列化（无额外代码） =====
序列化/反序列化: Health(75/100) ✓
```

**关键观察**：
- 每个 `ComponentStorage<T>` 内的数据是连续的内存块，遍历时缓存友好
- 同一实体索引可以有不同的组件组合——entity[1]（敌人）有 Position 和 Health，但没有 Velocity
- Health 可以直接 `memcpy` 到缓冲区再反序列化——不需要写任何序列化代码

---

## 3. 练习

### 练习 1: 设计一组完整的游戏组件

为一个 2D 射击游戏设计至少 10 个组件类型。包括：

- 运动相关：Position、Velocity、Rotation、AngularVelocity
- 战斗相关：Health、Damage、Shield、Armor
- 视觉相关：Sprite、Animation、ParticleEmitter
- 行为相关：AIState、PatrolPath、Target

定义它们的 struct，确保都是 POD。注明每个的大小和对齐。

### 练习 2: 热重载组件

假设你正在运行一个服务器，需要在不重启的情况下修改组件定义。因为组件是 POD，你可以：

1. 当前进程用 `struct Health_V1 { int hp; };`（4 字节）
2. 新代码用 `struct Health_V2 { int current, max; };`（8 字节）

设计一个机制让新旧组件共存，并逐步迁移数据。提示：利用 `ComponentTypeId` 的版本化——`HealthV1` 和 `HealthV2` 是两个不同的类型 ID。

### 练习 3: 组件压缩（挑战）

某些组件数据有大量冗余。例如 `Position` 如果是固定网格（如棋类游戏），x 只需 0-7（3 位）。设计一个方案：

- 使用 `uint32_t` 位域同时编码多个小组件
- 对比压缩前后的内存占用
- 分析运行时解压的开销是否值得


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // ========== 2D 射击游戏组件定义（全部 POD） ==========
>
> // ---- 运动相关 ----
> struct Position {       // 8 bytes, align 4
>     float x = 0, y = 0;
> };
> struct Velocity {       // 8 bytes, align 4
>     float dx = 0, dy = 0;
> };
> struct Rotation {       // 4 bytes, align 4 — 弧度制
>     float angle = 0;
> };
> struct AngularVelocity { // 4 bytes, align 4
>     float radiansPerSec = 0;
> };
>
> // ---- 战斗相关 ----
> struct Health {         // 8 bytes, align 4
>     int current = 100, max = 100;
> };
> struct Damage {         // 8 bytes, align 4
>     int amount = 10;
>     int sourceTeam = 0; // 避免友军伤害
> };
> struct Shield {         // 8 bytes, align 4
>     int current = 50, max = 50;
>     float rechargeDelay = 3.0f;  // 脱战 3 秒后开始回盾
> };
> struct Armor {          // 4 bytes, align 4
>     float reductionPercent = 0.2f;  // 20% 减伤
> };
>
> // ---- 视觉相关 ----
> struct Sprite {         // 12 bytes, align 4
>     int textureId = -1;
>     int width = 32, height = 32;
> };
> struct Animation {      // 16 bytes, align 4
>     int animSetId = -1;
>     int currentFrame = 0;
>     float frameTime = 0.1f;      // 每帧持续时间
>     float elapsed = 0;            // 当前帧已过时间
> };
> struct ParticleEmitter { // 20 bytes, align 4
>     int particleType = -1;
>     float emitRate = 10.0f;      // 每秒发射粒子数
>     float elapsed = 0;
>     float lifetime = 2.0f;       // 发射器持续时间
>     bool looping = true;
> };
>
> // ---- 行为相关 ----
> struct AIState {        // 8 bytes, align 4
>     enum State { Idle, Patrol, Chase, Attack, Flee } state = Idle;
>     float stateTimer = 0;        // 当前状态已持续时间
> };
> struct PatrolPath {     // 动态大小（std::vector），非严格 POD
>     std::vector<Position> waypoints;  // 注意：含 vector，不可 memcpy
>     int currentIdx = 0;
> };
> struct Target {         // 12 bytes, align 4
>     uint32_t entityIndex = -1;   // 用 index 而非完整 Entity 减少大小
>     float aggroRange = 10.0f;
> };
>
> // 编译期验证
> static_assert(std::is_trivially_copyable_v<Position>, "");
> static_assert(std::is_trivially_copyable_v<Health>, "");
> static_assert(std::is_trivially_copyable_v<Sprite>, "");
> // PatrolPath 含有 std::vector，不是 trivially copyable——这是合理的设计取舍
> ```
>
> **设计要点**：大多数组件保持在 4-16 字节，一个缓存行（64 字节）可容纳 4-16 个组件。`PatrolPath` 因含 `vector` 不是严格 POD，但这是必要的——路点数量动态变化。实际 ECS 中少量非 POD 组件是可接受的，核心原则是避免虚函数和 `shared_ptr`。

> [!tip]- 练习 2 参考答案
> ```cpp
> // ========== 版本化组件热迁移方案 ==========
>
> // 步骤 1: V1 版本（旧代码）
> struct Health_V1 { int hp; };
> ComponentTypeId TYPE_HEALTH_V1 = get_component_type_id<Health_V1>();
>
> // 步骤 2: V2 版本（新代码）
> struct Health_V2 { int current; int max; };
> ComponentTypeId TYPE_HEALTH_V2 = get_component_type_id<Health_V2>();
>
> // 步骤 3: 迁移函数
> // 在 World 初始化或 tick 开始时调用
> void migrate_health_v1_to_v2(WorldLike& world) {
>     // 遍历所有拥有 V1 组件的实体
>     for (auto e : entities_with<Health_V1>()) {
>         Health_V1* old = world.get<Health_V1>(e);
>         // 从 V1 数据构造 V2（hp=100 → current=100, max=100）
>         Health_V2 newData{old->hp, old->hp};  // 用 V1 的 hp 作为 max
>         world.add<Health_V2>(e, newData);
>         world.remove<Health_V1>(e);           // 移除旧版本
>     }
>     // 迁移完成后，所有 System 只查询 V2——旧 V1 代码可废弃
> }
>
> // 步骤 4: System 过渡期兼容
> // 如果无法一次性迁移所有实体，System 需要同时检查两个版本：
> void damage_system_compat(WorldLike& world, Entity e, int dmg) {
>     auto* h2 = world.get<Health_V2>(e);
>     if (h2) {
>         h2->current -= dmg;
>     } else {
>         auto* h1 = world.get<Health_V1>(e);
>         if (h1) h1->hp -= dmg;
>     }
> }
> ```
>
> **核心思路**：
> - `ComponentTypeId` 按类型分配 → `Health_V1` 和 `Health_V2` 获得**不同的类型 ID**
> - 新旧组件在存储中**完全隔离**——两个不同的 `ComponentStorage` 实例
> - 迁移是逐步的：新 System 同时读 V1/V2，后台线程迁移数据，最后移除 V1 支持
> - 这对服务器热更新至关重要：不需要停服即可升级数据格式

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // ========== 位域压缩方案（棋类游戏示例） ==========
>
> // 原始方案（每个组件独立）：Position 8B + Owner 8B + PieceType 4B = 20 bytes/实体
> struct Position { float x, y; };  // 8 bytes
> struct Owner    { int player; };    // 4 bytes
> struct PieceType { int type; };     // 4 bytes
>
> // 压缩方案：一个 uint32_t 编码所有信息
> struct CompactPiece {
>     uint32_t data;  // 4 bytes —— 压缩比 5:1
>     // 位布局（32 位）：
>     // [31:24] Row       — 8 位（0-255，棋盘最大 255 格）
>     // [23:16] Col       — 8 位
>     // [15:12] Owner     — 4 位（0-15 个玩家）
>     // [11:8]  Type      — 4 位（16 种棋子）
>     // [7:4]   State     — 4 位（正常/被吃/升变/...)
>     // [3:0]   预留       — 4 位
>
>     int row()        const { return (data >> 24) & 0xFF; }
>     int col()        const { return (data >> 16) & 0xFF; }
>     int owner()      const { return (data >> 12) & 0xF; }
>     int piece_type() const { return (data >> 8)  & 0xF; }
>
>     void set_row(int r) { data = (data & ~0xFF000000u) | (uint32_t(r) << 24); }
>     void set_col(int c) { data = (data & ~0x00FF0000u) | (uint32_t(c) << 16); }
> };
> ```
>
> **压缩 vs 原始对比**：
> | 指标 | 原始方案 | 位域压缩 |
> |------|---------|---------|
> | 每实体字节 | 20 B | 4 B |
> | 10000 实体 | 200 KB | 40 KB |
> | 缓存行利用率 | 3.2 实体/行 | 16 实体/行 |
> | 解压开销/字段 | ~0 ns（直接 load） | ~2-3 条指令（shift+mask） |
>
> **是否值得**：
> - **值得的场景**：数据量大（百万级）、访问频率高（每帧遍历）、字段值域小（像棋类游戏的 8×8 棋盘）
> - **不值得的场景**：字段需要浮点精度（位置用 float 而非 int）、字段值域大（无法用位域表示）、System 频繁修改单个字段（解压+重压开销 > 节省的内存带宽）
> - **工程实践**：大多数游戏不需要这种极致优化——先用普通 struct，profiling 发现瓶颈后再考虑
---

## 4. 扩展阅读

- **C++ `std::is_trivially_copyable`** — C++11 引入的类型特征，用于在编译期验证类型是否可安全 `memcpy`
- **结构数组（SoA）布局** — 见后续章节"Archetype 原型存储详解"
- **《Data-Oriented Design》— Richard Fabian，第 2 章** — 详细解释了为什么数据布局比算法选择更影响性能
- **EnTT `entt::meta` 系统** — 提供了运行时的组件反射和工厂构造，适合需要编辑器/序列化支持的场景

---

## 常见陷阱

- **Component 中有虚函数**：`struct Component { virtual void Update() = 0; }`——这回到了 OOP。虚表指针破坏 POD 性质，且引入了运行时多态开销。
- **Component 持有 `shared_ptr`**：`struct Sprite { shared_ptr<Texture> tex; }`——原子引用计数在多线程下成为竞争热点。资源应该由 `AssetManager` 统一持，Component 用原始指针或 ID 引用。
- **Component 之间相互引用（形成图）**：`struct A { B* b; }; struct B { A* a; };`——循环引用使生命周期管理复杂。改用 Entity ID 间接引用。
- **过度粒度的组件**：每个字段都拆成独立组件（`struct PosX { float x; }; struct PosY { float y; }`）——每增加一个组件类型就增加一次 Archetype 查询。保持在 1-4 个字段的粒度。
- **Component 没有默认值**：`struct Health { int current; int max; }`——没有 `= 100` 初始化。这导致未初始化的随机值 bug。始终给字段默认值。
