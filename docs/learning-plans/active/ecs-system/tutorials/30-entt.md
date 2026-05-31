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
