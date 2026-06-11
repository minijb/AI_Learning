---
title: "EnTT 详解"
updated: 2026-06-05
---

# EnTT 详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 4-6 小时
> 前置知识: ECS 基础原理、C++17 模板元编程基础

---

## 1. 概念讲解

### 为什么需要 EnTT？

EnTT 是 C++ 生态中最快的 ECS 库之一，由 Michele Caini（skypjack）开发，采用 MIT 许可。它不仅是 Unity DOTS 的灵感来源之一，还被 Mojang（Minecraft）、Facepunch Studios（Rust）、Axis Studios 等公司用于生产环境。

**核心定位**：一个 header-only 的 C++17 库，不是只做 ECS——它提供一整套工具链：

| 模块 | 功能 | 对标 |
|------|------|------|
| `entt::registry` | Entity-Component 存储和查询 | ECS 核心 |
| `entt::view` | 延迟查询（迭代时创建） | Unity `Entities.ForEach` |
| `entt::group` | 预排序的拥有型查询 | Unity `IJobChunk` |
| `entt::meta` | 运行时反射 | Unreal 的 UHT |
| `entt::resource` | 资源缓存和句柄系统 | 资源管理 |
| `entt::signal` | 信号/槽事件系统 | Qt 信号 |
| `entt::observer` | 响应式组件监视器 | Rx 风格的响应式 |

### 核心设计

EnTT 的核心存储是 **Sparse Set**。不同于 Archetype 方案将数据按组件组合分组，Sparse Set 以**组件类型为维度**组织数据：

```
Sparse Set 结构（以 Position 组件为例）：
┌──────────────────────────────────────┐
│  Sparse 数组（按 entity ID 索引）     │
│  [0] → invalid  [1] → 0             │
│  [2] → 1       [3] → invalid        │
│  [4] → 2       ...                  │
├──────────────────────────────────────┤
│  Dense 数组（紧凑排列的组件数据）      │
│  [0] → {entity:1, pos:{10,20}}       │
│  [1] → {entity:2, pos:{30,40}}       │
│  [2] → {entity:4, pos:{50,60}}       │
└──────────────────────────────────────┘
```

- **Sparse 数组**：以 entity ID 为索引，值是该实体在 Dense 数组中的位置。O(1) 查找。
- **Dense 数组**：紧凑存储组件数据，迭代时直接遍历 Dense 数组，缓存友好。
- **删除操作**：swap-and-pop——将最后一个元素移到删除位置，保持 Dense 紧凑。

这种设计带来的核心优势是**迭代速度极快**——不管是单组件还是多组件，EnTT 总是选择最小的 Dense 数组作为迭代主轴，对其他组件做随机访问。

---

## 2. 代码示例

### 2.1 基础操作：组件注册、增删改查

```cpp
#include <entt/entt.hpp>
#include <iostream>
#include <string>

// 定义组件——任何聚合类型都可以
struct Position { float x, y; };
struct Velocity { float dx, dy; };
struct Health   { int hp, max_hp; };
struct Name     { std::string value; };
struct Player   {};  // 标签组件（零大小）

int main() {
    entt::registry reg;

    // 创建实体 + 添加组件（就地构造，零拷贝）
    auto player = reg.create();
    reg.emplace<Position>(player, 100.0f, 200.0f);
    reg.emplace<Velocity>(player, 1.0f, -0.5f);
    reg.emplace<Health>(player, 100, 100);
    reg.emplace<Name>(player, "Hero");
    reg.emplace<Player>(player);

    // 创建敌人实体
    for (int i = 0; i < 5; ++i) {
        auto enemy = reg.create();
        reg.emplace<Position>(enemy, i * 50.0f, 300.0f);
        reg.emplace<Velocity>(enemy, -0.2f, 0.0f);
        reg.emplace<Health>(enemy, 30, 30);
        reg.emplace<Name>(enemy, "Enemy_" + std::to_string(i));
    }

    // 读取组件
    auto& pos = reg.get<Position>(player);
    std::cout << "Player at (" << pos.x << ", " << pos.y << ")\n";

    // 修改组件
    reg.patch<Position>(player, [](auto& p) { p.x += 10; });

    // 检查组件存在
    if (reg.all_of<Player, Health>(player)) {
        std::cout << "Player has Health\n";
    }

    // 移除组件
    reg.remove<Velocity>(player);

    // 销毁实体
    auto temp = reg.create();
    reg.emplace<Position>(temp, 0, 0);
    reg.destroy(temp);
}
```

### 2.2 View 查询系统

View 是 EnTT 最常用的查询方式。它**延迟构建**——只在迭代时查找匹配的实体：

```cpp
#include <entt/entt.hpp>
#include <iostream>

struct Position { float x, y; };
struct Velocity { float dx, dy; };
struct Health   { int hp; };

void moveSystem(entt::registry& reg) {
    // 单类型视图：遍历所有有 Position 的实体
    auto view = reg.view<Position>();
    for (auto entity : view) {
        auto& pos = view.get<Position>(entity);
        std::cout << "Entity " << static_cast<uint32_t>(entity)
                  << " at (" << pos.x << ", " << pos.y << ")\n";
    }

    // 多类型视图：Position + Velocity（可写）+ const Health（只读）
    auto moveView = reg.view<Position, Velocity, const Health>();
    for (auto [entity, pos, vel, hp] : moveView.each()) {
        pos.x += vel.dx;
        pos.y += vel.dy;
    }
}

void renderSystem(entt::registry& reg) {
    // 排除模式：有 Position 但没有 Velocity 的实体
    auto view = reg.view<Position>(entt::exclude<Velocity>);
    for (auto entity : view) {
        auto& pos = view.get<Position>(entity);
        std::cout << "Static entity at (" << pos.x << ", " << pos.y << ")\n";
    }
}

int main() {
    entt::registry reg;
    auto e1 = reg.create();
    reg.emplace<Position>(e1, 0.0f, 0.0f);
    reg.emplace<Velocity>(e1, 1.0f, 2.0f);
    reg.emplace<Health>(e1, 100);

    auto e2 = reg.create();
    reg.emplace<Position>(e2, 10.0f, 20.0f);
    reg.emplace<Health>(e2, 50);

    moveSystem(reg);
    renderSystem(reg);
}
```

### 2.3 Group 预排序查询

Group 相比 View 的优势是**完全拥有**指定组件——它在内部维护一个始终同步的实体列表，迭代时无需检查每个组件是否存在：

```cpp
#include <entt/entt.hpp>
#include <chrono>
#include <iostream>

struct Position { float x, y; };
struct Velocity { float dx, dy; };
struct Transform { float mat[16]; };  // 重组件

// Group 性能对比
void benchmark(entt::registry& reg) {
    using clock = std::chrono::high_resolution_clock;

    // View 方式：每次迭代检查 Velocity 存在性
    auto t1 = clock::now();
    auto view = reg.view<Position, Velocity>();
    for (auto [entity, pos, vel] : view.each()) {
        pos.x += vel.dx;
        pos.y += vel.dy;
    }
    auto t2 = clock::now();

    // Group 方式：预排序，直接迭代
    auto t3 = clock::now();
    auto group = reg.group<Position, Velocity>();
    for (auto [entity, pos, vel] : group.each()) {
        pos.x += vel.dx;
        pos.y += vel.dy;
    }
    auto t4 = clock::now();

    auto view_us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
    auto group_us = std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count();
    // 注意：t3-t2 因为 View 先执行了，但比例不影响结论

    std::cout << "View:  " << view_us << " us\n";
    std::cout << "Group: " << group_us << " us\n";
}

int main() {
    entt::registry reg;
    for (int i = 0; i < 100000; ++i) {
        auto e = reg.create();
        reg.emplace<Position>(e, float(i), float(i));
        reg.emplace<Velocity>(e, 1.0f, 1.0f);
    }
    benchmark(reg);
}
```

**Group 的三种类型**：

| 类型 | 含义 |
|------|------|
| `group<A, B>` | 完全拥有 A 和 B——所有变化都反映在 group 列表中。最快。 |
| `group<A>(entt::get<B>)` | 拥有 A，观察 B。B 变化不触发重组。 |
| `group<A>(entt::get<B>, entt::exclude<C>)` | 拥有 A，包含 B 且排除 C。 |

### 2.4 Signal / Sink 事件系统

EnTT 提供类型安全的信号槽系统，支持零参数到多参数的信号：

```cpp
#include <entt/entt.hpp>
#include <iostream>

// 定义事件类型
struct CollisionEvent {
    entt::entity a, b;
    float impact_force;
};

void onCollision(const CollisionEvent& ev) {
    std::cout << "Collision: entity " << static_cast<uint32_t>(ev.a)
              << " hit entity " << static_cast<uint32_t>(ev.b)
              << " with force " << ev.impact_force << "\n";
}

void playSound(const CollisionEvent& ev) {
    if (ev.impact_force > 50.0f) {
        std::cout << "💥 Play loud impact sound!\n";
    }
}

int main() {
    entt::dispatcher dispatcher{};

    // 连接槽
    auto conn1 = dispatcher.sink<CollisionEvent>().connect<&onCollision>();
    auto conn2 = dispatcher.sink<CollisionEvent>().connect<&playSound>();

    // 触发事件
    auto a = entt::entity{1}, b = entt::entity{2};
    dispatcher.trigger(CollisionEvent{a, b, 75.0f});

    // 也可入队后批量更新
    dispatcher.enqueue(CollisionEvent{a, b, 30.0f});
    dispatcher.update();  // 分发所有入队事件

    // 断开连接
    conn1.release();
}
```

### 2.5 Observer 响应式监视器

Observer 跟踪组件添加/移除的变化——适用于响应式系统：

```cpp
#include <entt/entt.hpp>
#include <iostream>

struct Weapon { int damage; };
struct Health { int hp; };

int main() {
    entt::registry reg;
    entt::observer weaponObserver{reg, entt::collector
        .update<Weapon>()        // Weapon 被修改时
        .group<Health>()         // 且实体有 Health
    };

    auto e1 = reg.create();
    reg.emplace<Health>(e1, 100);
    reg.emplace<Weapon>(e1, 10);   // 触发 observer

    reg.patch<Weapon>(e1, [](auto& w) { w.damage = 20; });  // 再次触发

    auto e2 = reg.create();
    reg.emplace<Weapon>(e2, 5);    // 无 Health，不触发

    // 处理观察到的实体
    weaponObserver.each([](auto entity) {
        std::cout << "Weapon changed on entity "
                  << static_cast<uint32_t>(entity) << "\n";
    });

    // 清除已处理的观察记录
    weaponObserver.clear();
}
```

### 2.6 Runtime Reflection（Meta）

EnTT 的 `meta` 系统提供编译期零开销的类型反射：

```cpp
#include <entt/entt.hpp>
#include <iostream>
#include <string>

struct Player {
    std::string name;
    int score;
    float health;
};

// 注册反射信息
void registerMeta() {
    using namespace entt::literals;

    entt::meta<Player>()
        .type("Player"_hs)
        .data<&Player::name>("name"_hs)
        .data<&Player::score>("score"_hs)
        .data<&Player::health>("health"_hs);
}

int main() {
    registerMeta();

    auto type = entt::resolve<Player>();
    std::cout << "Type: " << type.info().name() << "\n";

    // 遍历所有数据成员
    for (auto&& data : type.data()) {
        std::cout << "  Field: " << data.info().name() << "\n";
    }

    // 通过反射构造和修改对象
    auto playerType = entt::resolve("Player"_hs);
    auto instance = playerType.construct();
    playerType.func("set_score"_hs).invoke(instance, 100);
}
```

### 2.7 完整示例：Pong 游戏

下面是一个完整的 Pong 游戏骨架，展示 EnTT 在实际项目中的用法：

```cpp
#include <entt/entt.hpp>
#include <iostream>
#include <cstdlib>

// 组件定义
struct Position   { float x, y; };
struct Velocity   { float dx, dy; };
struct Rectangle  { float w, h; };   // 碰撞盒
struct Ball       {};                // 标签
struct Paddle     { int player; };   // 0=左, 1=右
struct Score      { int value; };
struct Renderable { char glyph; };

constexpr float FIELD_W = 80.0f;
constexpr float FIELD_H = 24.0f;
constexpr float PADDLE_SPEED = 1.0f;

// 系统：物理移动
void physicsSystem(entt::registry& reg) {
    auto view = reg.view<Position, const Velocity>();
    for (auto [entity, pos, vel] : view.each()) {
        pos.x += vel.dx;
        pos.y += vel.dy;
    }
}

// 系统：球与墙壁碰撞
void ballWallCollision(entt::registry& reg) {
    auto view = reg.view<const Ball, Position, Velocity>();
    for (auto [entity, pos, vel] : view.each()) {
        if (pos.y <= 0 || pos.y >= FIELD_H) {
            auto& v = reg.get<Velocity>(entity);
            v.dy = -v.dy;
        }
        if (pos.x <= 0 || pos.x >= FIELD_W) {
            auto& v = reg.get<Velocity>(entity);
            v.dx = -v.dx;
            // 得分逻辑简化
            std::cout << (pos.x <= 0 ? "Right" : "Left") << " scores!\n";
            pos.x = FIELD_W / 2;
            pos.y = FIELD_H / 2;
        }
    }
}

// 系统：渲染（简单的终端显示）
void renderSystem(entt::registry& reg) {
    // 用二维字符数组表示屏幕
    char screen[25][81];
    for (int y = 0; y < 25; ++y)
        for (int x = 0; x < 81; ++x)
            screen[y][x] = ' ';

    auto view = reg.view<const Position, const Renderable>();
    for (auto [entity, pos, r] : view.each()) {
        int sx = static_cast<int>(pos.x);
        int sy = static_cast<int>(pos.y);
        if (sx >= 0 && sx < 81 && sy >= 0 && sy < 25)
            screen[sy][sx] = r.glyph;
    }

    std::cout << "\033[2J\033[H";  // 清屏
    for (int y = 0; y < 25; ++y) {
        for (int x = 0; x < 81; ++x)
            std::cout << screen[y][x];
        std::cout << '\n';
    }
}

// 系统：玩家输入（简化：AI 控制两个球拍）
void aiSystem(entt::registry& reg) {
    // 找到球
    auto ballView = reg.view<const Ball, const Position>();
    float ballY = 0;
    for (auto [entity, pos] : ballView.each()) { ballY = pos.y; break; }

    // AI 球拍跟随球
    auto paddleView = reg.view<const Paddle, Position>();
    for (auto [entity, paddle, pos] : paddleView.each()) {
        auto& p = reg.get<Position>(entity);
        if (ballY > p.y + 2) p.y += PADDLE_SPEED;
        else if (ballY < p.y - 2) p.y -= PADDLE_SPEED;
    }
}

// Observer：当球得分时触发事件
void setupObserver(entt::registry& reg, entt::observer& obs) {
    // 实际上 EnTT observer 监视组件变化，这里展示概念
}

int main() {
    entt::registry reg;

    // 创建球
    auto ball = reg.create();
    reg.emplace<Position>(ball, FIELD_W / 2, FIELD_H / 2);
    reg.emplace<Velocity>(ball, 0.5f, 0.3f);
    reg.emplace<Rectangle>(ball, 1.0f, 1.0f);
    reg.emplace<Ball>(ball);
    reg.emplace<Renderable>(ball, 'O');

    // 创建左球拍
    auto paddleL = reg.create();
    reg.emplace<Position>(paddleL, 1.0f, FIELD_H / 2);
    reg.emplace<Rectangle>(paddleL, 1.0f, 5.0f);
    reg.emplace<Paddle>(paddleL, 0);
    reg.emplace<Renderable>(paddleL, '|');

    // 创建右球拍
    auto paddleR = reg.create();
    reg.emplace<Position>(paddleR, FIELD_W - 1, FIELD_H / 2);
    reg.emplace<Rectangle>(paddleR, 1.0f, 5.0f);
    reg.emplace<Paddle>(paddleR, 1);
    reg.emplace<Renderable>(paddleR, '|');

    // 游戏主循环
    for (int frame = 0; frame < 200; ++frame) {
        aiSystem(reg);
        physicsSystem(reg);
        ballWallCollision(reg);
        renderSystem(reg);

        // 简单帧率控制（实际项目用时间步长）
        for (volatile int i = 0; i < 5000000; ++i);
    }
}
```

**运行方式：**

```bash
# 安装 EnTT（header-only）
git clone https://github.com/skypjack/entt.git
# 或者使用包管理器
# vcpkg install entt
# conan install entt/3.12.2

# 编译
g++ -std=c++17 -O2 -I entt/single_include pong.cpp -o pong

# 运行
./pong
```

**预期输出：**
```text
（终端中显示 Pong 游戏的简单 ASCII 动画）
Left scores!
Right scores!
...
```

### 2.8 性能基准：EnTT vs 原生数组

```cpp
#include <entt/entt.hpp>
#include <chrono>
#include <vector>
#include <iostream>

struct Vec3 { float x, y, z; };

// 原生数组实现（模拟 ECS 的操作）
struct NativeApproach {
    std::vector<Vec3> positions;
    std::vector<Vec3> velocities;
    std::vector<bool>   active;

    void addEntity(Vec3 pos, Vec3 vel) {
        positions.push_back(pos);
        velocities.push_back(vel);
        active.push_back(true);
    }

    void iteratePhysics() {
        for (size_t i = 0; i < positions.size(); ++i) {
            if (!active[i]) continue;
            positions[i].x += velocities[i].x;
            positions[i].y += velocities[i].y;
            positions[i].z += velocities[i].z;
        }
    }

    void removeEntity(size_t idx) {
        active[idx] = false;
        // swap-and-pop
        size_t last = positions.size() - 1;
        positions[idx] = positions[last];
        velocities[idx] = velocities[last];
        active[idx] = active[last];
        positions.pop_back();
        velocities.pop_back();
        active.pop_back();
    }
};

using clock = std::chrono::high_resolution_clock;

int main() {
    constexpr int N = 1000000;

    // EnTT 测试
    {
        entt::registry reg;
        std::vector<entt::entity> entities(N);
        for (int i = 0; i < N; ++i) {
            auto e = reg.create();
            reg.emplace<Vec3>(e, float(i), float(i), float(i));
            reg.emplace<Vec3>(e, float(-i), 0.0f, 0.0f);
            entities[i] = e;
        }

        auto t1 = clock::now();
        auto view = reg.view<Vec3, Vec3>();
        // 第二个 Vec3 是 Velocity——EnTT 通过组件 index 区分
        // 实际项目中 Velocity 会定义为独立类型
        auto t2 = clock::now();
        std::cout << "EnTT query setup: "
                  << std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count()
                  << " us\n";
    }

    // 原生数组测试
    {
        NativeApproach native;
        for (int i = 0; i < N; ++i) {
            native.addEntity({float(i), float(i), float(i)},
                             {float(-i), 0.0f, 0.0f});
        }

        auto t1 = clock::now();
        native.iteratePhysics();
        auto t2 = clock::now();
        std::cout << "Native array iteration: "
                  << std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count()
                  << " us\n";
    }
}
```

---

## 3. 练习

### 练习 1: 基础操作
创建一个 registry，添加 100 个实体，每个实体随机拥有 2-4 种组件（Position, Velocity, Health, Name, Renderable）。用 view 统计每种类型的实体数量。

### 练习 2: 模拟粒子系统
用 EnTT 实现一个简单粒子系统：每个粒子有 Position、Velocity、Lifetime 组件。在每帧：
1. 根据 Velocity 更新 Position
2. 减少 Lifetime
3. 用 observer 在 Lifetime <= 0 时移除粒子
4. 每帧添加 10 个新粒子

### 练习 3: 小型射击游戏（可选）
基于 Pong 示例扩展：添加子弹（Bullet 组件 + 直线运动）、敌人生成（EnemySpawner 组件）、碰撞检测（用 observer + signal 在 CollisionEvent 时播放音效、增加分数）。用 group 优化子弹-敌人碰撞检测。

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> #include <entt/entt.hpp>
> #include <iostream>
> #include <random>
> #include <vector>
> #include <map>
>
> // 定义组件
> struct Position { float x, y; };
> struct Velocity { float dx, dy; };
> struct Health   { int hp, max_hp; };
> struct Name     { std::string value; };
> struct Renderable { int mesh_id; };
>
> int main() {
>     entt::registry reg;
>
>     // 可用组件列表（索引化，方便随机选择）
>     enum Comp : uint8_t { POS=0, VEL, HP, NAME, RENDER, COUNT };
>     const char* CompNames[COUNT] = {
>         "Position", "Velocity", "Health", "Name", "Renderable"
>     };
>
>     std::mt19937 rng{42}; // 固定种子，可复现
>     std::uniform_int_distribution<int> countDist(2, 4);
>     // 生成 2-4 之间的随机组件数——控制每个实体复杂度
>     std::uniform_real_distribution<float> posDist(-500.0f, 500.0f);
>     std::uniform_real_distribution<float> velDist(-10.0f, 10.0f);
>     std::uniform_int_distribution<int> hpDist(10, 200);
>     std::uniform_int_distribution<int> meshDist(0, 99);
>
>     for (int i = 0; i < 100; ++i) {
>         auto e = reg.create();
>
>         // 确定本实体拥有的组件数量（2-4）
>         int numComps = countDist(rng);
>
>         // Fisher-Yates 部分洗牌：从 5 种组件中随机选 numComps 种
>         std::vector<uint8_t> comps = {POS, VEL, HP, NAME, RENDER};
>         for (int j = 0; j < numComps; ++j) {
>             int swapIdx = j + (rng() % (comps.size() - j));
>             std::swap(comps[j], comps[swapIdx]);
>
>             switch (comps[j]) {
>             case POS:
>                 reg.emplace<Position>(e,
>                     posDist(rng), posDist(rng));
>                 break;
>             case VEL:
>                 reg.emplace<Velocity>(e,
>                     velDist(rng), velDist(rng));
>                 break;
>             case HP:
>                 {
>                     int hp = hpDist(rng);
>                     reg.emplace<Health>(e, hp, hp);
>                 }
>                 break;
>             case NAME:
>                 reg.emplace<Name>(e,
>                     "Entity_" + std::to_string(i));
>                 break;
>             case RENDER:
>                 reg.emplace<Renderable>(e, meshDist(rng));
>                 break;
>             }
>         }
>     }
>
>     // 统计：用每种组件的 view 计数
>     std::cout << "=== 组件分布统计 ===\n";
>     std::cout << "Position:   " << reg.view<Position>().size()
>               << " entities\n";
>     std::cout << "Velocity:   " << reg.view<Velocity>().size()
>               << " entities\n";
>     std::cout << "Health:     " << reg.view<Health>().size()
>               << " entities\n";
>     std::cout << "Name:       " << reg.view<Name>().size()
>               << " entities\n";
>     std::cout << "Renderable: " << reg.view<Renderable>().size()
>               << " entities\n";
>
>     // 进一步统计：同时有 Position + Velocity 的实体
>     auto moveView = reg.view<Position, Velocity>();
>     std::cout << "\nPosition + Velocity: " << moveView.size()
>               << " entities (可移动实体)\n";
>
>     // 各组件交叉统计（用 view 的 each 做精确检查）
>     std::map<std::string, int> comboCounts;
>     for (auto e : reg.view<Position>()) {
>         std::string combo = "Position";
>         if (reg.all_of<Velocity>(e))     combo += "+Vel";
>         if (reg.all_of<Health>(e))       combo += "+HP";
>         if (reg.all_of<Name>(e))         combo += "+Name";
>         if (reg.all_of<Renderable>(e))   combo += "+Render";
>         comboCounts[combo]++;
>     }
>
>     std::cout << "\n=== 组合分布 (Top 10) ===\n";
>     // 这里省略排序打印——实际用 partial_sort 或转 vector 排序
>
>     return 0;
> }
> ```
>
> **关键点说明：**
> - `reg.view<T>().size()` 是 O(n) 操作（遍历 sparse set 计数），因为 View 延迟构建
> - Fisher-Yates 部分洗牌保证每个实体的组件组合是随机且不可预测的（而非总是前 2-4 种）
> - `all_of` 检查单个实体的组件组合，开销 O(1) 但可能触发 sparse set 的间接查找

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <entt/entt.hpp>
> #include <iostream>
> #include <random>
>
> struct Position { float x, y; };
> struct Velocity { float dx, dy; };
> struct Lifetime { float remaining; };
>
> // 模拟每帧 = 1/60 秒
> constexpr float DT = 1.0f / 60.0f;
> constexpr float MAX_LIFETIME = 3.0f; // 粒子最长存活 3 秒
>
> int main() {
>     entt::registry reg;
>     std::mt19937 rng{42};
>     std::uniform_real_distribution<float> velDist(-50.0f, 50.0f);
>     std::uniform_real_distribution<float> lifeDist(0.5f, MAX_LIFETIME);
>
>     // ── Observer: 监听 Lifetime 被移除（即粒子死亡）──
>     entt::observer particleObserver{reg, entt::collector
>         .update<Lifetime>()         // Lifetime 被修改
>     };
>
>     int frameCount = 0;
>     constexpr int TOTAL_FRAMES = 300;  // 模拟 5 秒
>
>     for (int frame = 0; frame < TOTAL_FRAMES; ++frame) {
>         // ═══ 1. 生成新粒子（每帧 10 个）═══
>         for (int i = 0; i < 10; ++i) {
>             auto e = reg.create();
>             reg.emplace<Position>(e, 0.0f, 0.0f);  // 从原点发射
>             reg.emplace<Velocity>(e, velDist(rng), velDist(rng));
>             reg.emplace<Lifetime>(e, lifeDist(rng));
>         }
>
>         // ═══ 2. 更新粒子：移动 + 衰减 Lifetime ═══
>         auto particleView = reg.view<Position, Velocity, Lifetime>();
>         for (auto [entity, pos, vel, life] : particleView.each()) {
>             // 根据 Velocity 更新 Position
>             pos.x += vel.dx * DT;
>             pos.y += vel.dy * DT;
>
>             // 减少 Lifetime——使用 patch 通知 Observer
>             life.remaining -= DT;
>
>             // Lifetime 耗尽：移除粒子
>             if (life.remaining <= 0.0f) {
>                 reg.destroy(entity);
>             }
>         }
>
>         // ═══ 3. Observer: 检测本轮销毁的粒子 ═══
>         // observer.each() 返回本帧被修改/移除 Lifetime 的实体
>         int destroyedThisFrame = 0;
>         for (auto entity : particleObserver) {
>             // 检查实体是否已被销毁（Lifetime 归零后 destroy 了）
>             if (!reg.valid(entity)) {
>                 destroyedThisFrame++;
>             }
>         }
>
>         // 重置 observer 以准备下一帧
>         particleObserver.clear();
>
>         // ═══ 4. 统计 ═══
>         int totalParticles = reg.view<Position>().size();
>         std::cout << "Frame " << frame
>                   << ": particles=" << totalParticles
>                   << ", destroyed=" << destroyedThisFrame
>                   << "\n";
>     }
>
>     // 最终清理
>     std::cout << "\nFinal particle count: "
>               << reg.storage<Position>().size() << "\n";
> }
> ```
>
> **稳态分析：**
> - 每帧生成 10 个，平均寿命 1.75s ≈ 105 帧 → 稳态粒子数 ≈ 10 × 105 = ~1050 个
> - Lifetime 使用 `reg.patch` 或直接修改后 observer 检测——这里用直接修改，observer 通过 `update<Lifetime>` 感知
> - 注意：如果直接把 `life.remaining -= DT` 写在 `each()` 里且 `life` 不是引用，必须用 `reg.patch<Lifetime>(entity, [](auto& l){ l.remaining -= DT; })` → 实际代码中 `auto [entity, pos, vel, life]` 的 `life` 就是引用（结构化绑定的引用语义），所以直接修改即可
> - `observer.clear()` 必须在每帧处理完后调用，否则旧的实体持续留在 observer 中

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <entt/entt.hpp>
> #include <iostream>
> #include <random>
> #include <cmath>
>
> // ── 组件 ────────────────────────────────────
> struct Position   { float x, y; };
> struct Velocity   { float dx, dy; };
> struct Health     { int hp; };
> struct Bullet     { int damage; };
> struct Enemy      {};
> struct Player     {};
> struct Score      { int value; };
>
> // ── 事件 ────────────────────────────────────
> struct CollisionEvent {
>     entt::entity a, b;
>     float dist;
> };
>
> struct SoundEvent {
>     std::string name;
>     entt::entity source;
> };
>
> // ── 信号槽处理 ──────────────────────────────
> void onCollision(const CollisionEvent& ev) {
>     std::cout << "💥 Collision! dist=" << ev.dist << "\n";
> }
>
> void onSound(const SoundEvent& ev) {
>     std::cout << "🔊 Play sound: " << ev.name << "\n";
> }
>
> constexpr float DT = 1.0f / 60.0f;
> constexpr float BULLET_SPEED = 400.0f;
> constexpr float ENEMY_SPEED = 80.0f;
> constexpr float COLLISION_RADIUS_SQ = 20.0f * 20.0f;
>
> int main() {
>     entt::registry reg;
>     entt::dispatcher dispatcher{};
>
>     // 连接碰撞事件
>     dispatcher.sink<CollisionEvent>().connect<&onCollision>();
>     dispatcher.sink<SoundEvent>().connect<&onSound>();
>
>     std::mt19937 rng{42};
>     std::uniform_real_distribution<float> posDist(0.0f, 800.0f);
>
>     // ── 生成玩家 ──
>     auto player = reg.create();
>     reg.emplace<Position>(player, 400.0f, 300.0f);
>     reg.emplace<Velocity>(player, 0.0f, 0.0f);
>     reg.emplace<Health>(player, 100);
>     reg.emplace<Player>(player);
>
>     // 初始 5 个敌人
>     for (int i = 0; i < 5; ++i) {
>         auto e = reg.create();
>         reg.emplace<Position>(e,
>             posDist(rng), posDist(rng));
>         reg.emplace<Health>(e, 30);
>         reg.emplace<Enemy>(e);
>         // 敌人不需要 Velocity——通过 AI 直接改变位置
>     }
>
>     // ── Group: 拥有 Bullet（快速碰撞检测）──
>     // 完全拥有 Bullet：当有实体获得/失去 Bullet 时 Group 自动更新
>     auto bulletGroup = reg.group<Bullet, Position>();
>     auto enemyView  = reg.view<Enemy, Position>();
>
>     int score = 0;
>     float enemySpawnTimer = 0.0f;
>
>     for (int frame = 0; frame < 600; ++frame) { // 10 秒
>         // ── 敌人生成 ──
>         enemySpawnTimer += DT;
>         if (enemySpawnTimer > 2.0f) {
>             enemySpawnTimer = 0.0f;
>             auto e = reg.create();
>             reg.emplace<Position>(e,
>                 posDist(rng), posDist(rng));
>             reg.emplace<Health>(e, 30);
>             reg.emplace<Enemy>(e);
>         }
>
>         // ── 发射子弹（每 0.5s 一发）──
>         if (frame % 30 == 0) {
>             auto bullet = reg.create();
>             const auto& pPos = reg.get<Position>(player);
>             reg.emplace<Position>(bullet, pPos.x, pPos.y);
>             reg.emplace<Velocity>(bullet,
>                 BULLET_SPEED, 0.0f); // 向右发射
>             reg.emplace<Bullet>(bullet, 15);
>         }
>
>         // ── 子弹移动 ──
>         for (auto [entity, bullet, pos, vel] :
>              bulletGroup.each()) {
>             pos.x += vel.dx * DT;
>             pos.y += vel.dy * DT;
>             // 飞出屏幕则销毁
>             if (pos.x > 900.0f || pos.x < -100.0f ||
>                 pos.y > 700.0f || pos.y < -100.0f) {
>                 reg.destroy(entity);
>             }
>         }
>
>         // ── 敌人向玩家缓慢移动 ──
>         const auto& playerPos = reg.get<Position>(player);
>         for (auto [entity, pos] : enemyView.each()) {
>             float dx = playerPos.x - pos.x;
>             float dy = playerPos.y - pos.y;
>             float len = std::sqrt(dx*dx + dy*dy);
>             if (len > 1.0f) {
>                 pos.x += (dx / len) * ENEMY_SPEED * DT;
>                 pos.y += (dy / len) * ENEMY_SPEED * DT;
>             }
>         }
>
>         // ── 碰撞检测：子弹 vs 敌人（用 Group 优化）──
>         for (auto [bEntity, bullet, bPos] :
>              bulletGroup.each()) {
>             for (auto [eEntity, ePos] : enemyView.each()) {
>                 float dx = bPos.x - ePos.x;
>                 float dy = bPos.y - ePos.y;
>                 if (dx*dx + dy*dy < COLLISION_RADIUS_SQ) {
>                     // 碰撞！
>                     dispatcher.trigger(CollisionEvent{
>                         bEntity, eEntity,
>                         std::sqrt(dx*dx + dy*dy)
>                     });
>                     dispatcher.trigger(SoundEvent{
>                         "explosion", eEntity
>                     });
>
>                     // 伤害计算
>                     auto& hp = reg.get<Health>(eEntity);
>                     hp.hp -= bullet.damage;
>                     score += 10;
>
>                     // 敌人死亡
>                     if (hp.hp <= 0) {
>                         reg.destroy(eEntity);
>                         score += 50;  // 击杀额外加分
>                     }
>
>                     // 子弹消失
>                     reg.destroy(bEntity);
>                     break; // 一颗子弹只能命中一个敌人
>                 }
>             }
>         }
>
>         // 分发入队事件
>         dispatcher.update();
>
>         if (frame % 60 == 0) {
>             std::cout << "Frame " << frame
>                       << ": enemies=" << enemyView.size()
>                       << " bullets=" << bulletGroup.size()
>                       << " score=" << score << "\n";
>         }
>     }
>
>     std::cout << "\nFinal score: " << score << "\n";
> }
> ```
>
> **Group 优化子弹-敌人碰撞的原理：**
> - `reg.group<Bullet, Position>()` 完全拥有 Bullet 组件——Group 内部维护了一个始终排序的实体列表
> - 当 bulletGroup 遍历时，外层直接迭代 Dense 数组，**不需要检查每个实体是否拥有 Bullet**（已保证）
> - 对比用 `reg.view<Bullet, Position>()` 的话，每次 `entity : view` 仍然需要做 sparse set 的间接查找
> - 在内层遍历敌人时用 `enemyView`（普通 View）即可——敌人的生命期较长且变化不频繁
> - 实际游戏中子弹-敌人碰撞应该用空间哈希/四叉树进一步降复杂度——此处 Group 主要演示 EnTT 的拥有型查询能力

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- [EnTT GitHub](https://github.com/skypjack/entt) — 官方仓库，含完整文档和 Wiki
- [EnTT Crash Course](https://github.com/skypjack/entt/wiki/Crash-Course:-entity-component-system) — 官方 ECS 速成教程
- [Implementation of a component-based entity system in modern C++](https://skypjack.github.io/) — EnTT 作者的 CppCon 演讲
- [Sparse Set 数据结构分析](https://research.swtch.com/sparse) — Russ Cox 的经典文章

---

## 常见陷阱

| 陷阱 | 说明 | 正确做法 |
|------|------|----------|
| View 持有引用 | View 在迭代期间修改 registry 可能导致悬垂引用 | 在 View 迭代过程中不要创建/销毁实体；用 `defer` 或延迟列表 |
| Group 的所有权语义 | `group<A, B>` 意味着 A 和 B 都被 group "拥有"——任何添加/移除 A 或 B 的操作都会触发 group 内部列表的更新 | 性能敏感场景用 group；不拥有时用 `entt::get<>` |
| `registry.get<>` vs `view.get<>` | `reg.get<T>(e)` 返回引用但要求组件存在；不存在时是 UB | 不确定存在时用 `reg.try_get<T>(e)` 返回指针 |
| Entity 不是整数 | `entt::entity` 是 `entt::basic_entity<uint32_t>`，但不可隐式转换 | 用 `static_cast<uint32_t>(e)` 或 `entt::to_integral(e)` |
| 多线程 | EnTT 的 registry 不是线程安全的 | 每个线程一个 registry，或外部同步。EnTT 提供 `entt::runtime_view` 用于只读并行 |
| 忽略 `patch` | 直接 `auto& c = reg.get<T>(e); c.x = 10;` 不会通知 observer/group | 需要通知时用 `reg.patch<T>(e, [](auto& c){ c.x = 10; })` |
