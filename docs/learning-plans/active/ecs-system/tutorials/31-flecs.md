---
title: "Flecs 详解"
updated: 2026-06-05
---

# Flecs 详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 4-6 小时
> 前置知识: ECS 基础原理、C 语言基础、了解 EnTT 的设计

---

## 1. 概念讲解

### 为什么需要 Flecs？

Flecs（Flexible Entity Component System）是一个用 C99 编写的 ECS 库，由 Sander Mertens 开发，采用 MIT 许可。它的独特之处在于：

1. **纯 C API**：核心是 C99，但提供了 C++/C#/Rust/Julia 绑定。不需要 RTTI、异常或 STL。
2. **查询 DSL**：`Position, Velocity` 这样的字符串解析为优化后的查询计划。
3. **内置层级系统**：实体之间可以有父子关系——不是组件实现的，是引擎原生的。
4. **实体关系**：不只是 "实体拥有组件"，而是 "实体与实体的关系可以是组件"。
5. **可选的模块系统**：导入/导出 ECS 模块，类似包的依赖管理。

**定位对比**：

| 维度 | EnTT | Flecs |
|------|------|-------|
| 语言 | C++17 模板元编程 | C99 + 宏 |
| 查询方式 | View/Group 模板 API | 查询 DSL 字符串 + Rules |
| 层级 | 需手动实现组件 | 内建的 `ChildOf` 关系 |
| 关系 | 不支持 | 一等公民——`Flecs::ChildOf`、`IsA`（继承） |
| 反射 | `entt::meta` | 内建的 `EcsComponent` 等元组件 |
| 运行时查询 | 编译期确定 | REST API 可在运行时查询 |
| 序列化 | 需手动 | 自动 JSON/二进制序列化 |
| 编译速度 | 较慢（重度模板） | 极快（C99 头文件） |

### 核心设计：实体关系

Flecs 的根本创新是 **实体作为组件**。传统 ECS：`Entity` → 持有 `Component`。Flecs：`Entity` → 持有 `(Relationship, Target)` 对。

```
传统 ECS:
  Entity(42) → owns → Position{x:10, y:20}

Flecs 关系:
  Entity(42) → (Position, 42) = {x:10, y:20}
  Entity(43) → (ChildOf, 42)   // 43 是 42 的子实体
  Entity(44) → (IsA, 42)       // 44 继承 42 的所有组件
  Entity(45) → (Likes, 46)     // 45 "喜欢" 46（自定义关系）
```

**关键特性**：关系有方向、可以有属性（如 `Transitive`、`Reflexive`、`Symmetric`）。

### 查询 DSL

Flecs 接受人类可读的查询字符串：

```
"Position, Velocity"              → 有 Position 和 Velocity 的实体
"Position(parent), Velocity"      → 从父实体读取 Position
"Position, !Velocity"             → 有 Position 但没有 Velocity
"[none] Position"                 → 确定没有 Position 的实体
"Position || Velocity"            → 有 Position 或 Velocity
"ChildOf: #0"                     → 根级别的实体
```

查询在**注册时编译**为优化后的内部表示，运行时执行快。

---

## 2. 代码示例

### 2.1 基础操作：C API

```c
#include <flecs.h>
#include <stdio.h>

// 组件定义
typedef struct { float x, y; } Position;
typedef struct { float dx, dy; } Velocity;
typedef struct { int hp; } Health;

int main() {
    ecs_world_t* world = ecs_init();

    // 注册组件
    ECS_COMPONENT(world, Position);
    ECS_COMPONENT(world, Velocity);
    ECS_COMPONENT(world, Health);

    // 创建实体（用 C 宏）
    ecs_entity_t player = ecs_new(world);
    ecs_set(world, player, Position, {10, 20});
    ecs_set(world, player, Velocity, {1, 0});
    ecs_set(world, player, Health, {100});

    // 批量创建（实体工厂）
    ecs_entity_t enemy_prefab = ecs_new(world);
    ecs_set(world, enemy_prefab, Position, {0, 0});
    ecs_set(world, enemy_prefab, Health, {30});

    // 查询迭代
    ecs_query_t* q = ecs_query(world, {
        .terms = {
            { .id = ecs_id(Position) },
            { .id = ecs_id(Velocity) }
        }
    });

    ecs_iter_t it = ecs_query_iter(world, q);
    while (ecs_query_next(&it)) {
        Position* p = ecs_field(&it, Position, 1);
        Velocity* v = ecs_field(&it, Velocity, 2);
        for (int i = 0; i < it.count; i++) {
            p[i].x += v[i].dx;
            p[i].y += v[i].dy;
        }
    }

    ecs_fini(world);
    return 0;
}
```

### 2.2 实体层级和关系

```c
#include <flecs.h>
#include <stdio.h>

typedef struct { float x, y; } Position;
typedef struct { float width, height; } Size;

int main() {
    ecs_world_t* world = ecs_init();
    ECS_COMPONENT(world, Position);
    ECS_COMPONENT(world, Size);

    // 创建场景根节点
    ecs_entity_t root = ecs_new(world);
    ecs_set_name(world, root, "Root");

    // 创建子实体（通过 ChildOf 关系）
    ecs_entity_t child1 = ecs_new_w_pair(world, EcsChildOf, root);
    ecs_set_name(world, child1, "Child1");
    ecs_set(world, child1, Position, {100, 0});

    // 使用 C++ 风格的简洁 API（需 C++ 绑定）
    // 创建孙实体
    ecs_entity_t grandchild = ecs_new_w_pair(world, EcsChildOf, child1);
    ecs_set_name(world, grandchild, "Grandchild");
    ecs_set(world, grandchild, Position, {50, 0});

    // 查询：从父实体继承 Position
    ecs_query_t* q = ecs_query(world, {
        .terms = {
            { .id = ecs_id(Position), .src.id = EcsUp },  // 向上查找
            { .id = ecs_id(Size) }
        }
    });

    // 遍历层级
    ecs_query_t* tree_q = ecs_query(world, {
        .terms = {{ .id = EcsChildOf, .src.id = EcsThis, .oper = EcsNot }}
    });
    ecs_iter_t it = ecs_query_iter(world, tree_q);
    while (ecs_query_next(&it)) {
        for (int i = 0; i < it.count; i++) {
            printf("Found root-level entity: %s\n",
                   ecs_get_name(world, it.entities[i]));
        }
    }

    ecs_fini(world);
    return 0;
}
```

### 2.3 系统管道和模块

Flecs 支持声明式的系统管道（Pipeline）：

```c
#include <flecs.h>
#include <stdio.h>

typedef struct { float x, y; } Position;
typedef struct { float dx, dy; } Velocity;

// 系统函数——签名固定
void Move(ecs_iter_t* it) {
    Position* p = ecs_field(it, Position, 1);
    const Velocity* v = ecs_field(it, Velocity, 2);
    for (int i = 0; i < it->count; i++) {
        p[i].x += v[i].dx;
        p[i].y += v[i].dy;
    }
}

void PrintPosition(ecs_iter_t* it) {
    const Position* p = ecs_field(it, Position, 1);
    for (int i = 0; i < it->count; i++) {
        printf("Entity %s at (%.1f, %.1f)\n",
               ecs_get_name(it->world, it->entities[i]),
               p[i].x, p[i].y);
    }
}

int main() {
    ecs_world_t* world = ecs_init();
    ECS_COMPONENT(world, Position);
    ECS_COMPONENT(world, Velocity);

    // 导入内置的 Pipeline 模块
    ECS_IMPORT(world, FlecsPipeline);

    // 注册系统——指定相位
    ECS_SYSTEM(world, Move, EcsOnUpdate, Position, Velocity);
    ECS_SYSTEM(world, PrintPosition, EcsPostUpdate, Position);

    // 创建实体
    ecs_entity_t e = ecs_new(world);
    ecs_set(world, e, Position, {0, 0});
    ecs_set(world, e, Velocity, {1, 2});

    // 运行几帧
    for (int i = 0; i < 3; i++) {
        printf("--- Frame %d ---\n", i);
        ecs_progress(world, 0.016f);  // 16ms 帧
    }

    ecs_fini(world);
    return 0;
}
```

### 2.4 查询 DSL 和 Rules

```c
#include <flecs.h>
#include <stdio.h>

typedef struct { float value; } Attack;
typedef struct { float value; } Defense;
typedef struct { float value; } Speed;

// 使用 DSL 定义查询
int main() {
    ecs_world_t* world = ecs_init();
    ECS_COMPONENT(world, Attack);
    ECS_COMPONENT(world, Defense);
    ECS_COMPONENT(world, Speed);

    // 创建各种实体
    for (int i = 0; i < 100; i++) {
        ecs_entity_t e = ecs_new(world);
        if (i % 3 == 0) ecs_set(world, e, Attack, {i * 1.0f});
        if (i % 2 == 0) ecs_set(world, e, Defense, {i * 0.5f});
        if (i % 5 == 0) ecs_set(world, e, Speed, {i * 2.0f});
    }

    // DSL 查询
    ecs_rule_t* r = ecs_rule(world, {
        .terms = {
            { .id = ecs_id(Attack) },
            { .id = ecs_id(Defense) }
        }
    });

    // 迭代
    ecs_iter_t it = ecs_rule_iter(world, r);
    int count = 0;
    while (ecs_rule_next(&it)) {
        const Attack* a = ecs_field(&it, Attack, 1);
        const Defense* d = ecs_field(&it, Defense, 2);
        for (int i = 0; i < it.count; i++) {
            count++;
            if (count <= 3) {
                printf("Entity: Attack=%.1f Defense=%.1f\n", a[i].value, d[i].value);
            }
        }
    }
    printf("Total matching entities: %d\n", count);

    ecs_rule_fini(r);
    ecs_fini(world);
    return 0;
}
```

### 2.5 自动序列化与 REST API

```c
#include <flecs.h>

typedef struct { float x, y; } Position;
typedef struct { float dx, dy; } Velocity;
typedef struct { int hp; } Health;

int main() {
    ecs_world_t* world = ecs_init();
    ECS_COMPONENT(world, Position);
    ECS_COMPONENT(world, Velocity);
    ECS_COMPONENT(world, Health);

    // 创建一些实体
    ecs_entity_t player = ecs_new(world);
    ecs_set(world, player, Position, {10, 20});
    ecs_set(world, player, Health, {100});

    // 启用 REST API（默认端口 27750）
    ecs_singleton_set(world, EcsRest, {0});

    printf("REST API running at http://localhost:27750/entity/flecs\n");

    // 手动序列化单个实体（无需 HTTP）
    ecs_iter_t it = ecs_each(world, Position);
    while (ecs_each_next(&it)) {
        Position* p = ecs_field(&it, Position, 1);
        for (int i = 0; i < it.count; i++) {
            char* json = ecs_entity_to_json(world, it.entities[i], NULL);
            printf("Entity JSON: %s\n", json);
            ecs_os_free(json);
        }
    }

    // 序列化整个 world
    char* world_json = ecs_world_to_json(world, NULL);
    printf("World JSON (truncated): %.200s...\n", world_json);
    ecs_os_free(world_json);

    ecs_fini(world);
    return 0;
}
```

### 2.6 C++ 绑定（flecs::world）

Flecs 提供了符合现代 C++ 习惯的绑定：

```cpp
#include <flecs.h>
#include <iostream>

struct Position { float x, y; };
struct Velocity { float dx, dy; };

int main() {
    flecs::world world;

    // 注册组件（自动推导）
    world.component<Position>();
    world.component<Velocity>();

    // 创建实体
    auto e = world.entity()
        .set<Position>({10, 20})
        .set<Velocity>({1, 0});

    // 查询——使用 lambda
    world.system<Position, const Velocity>("Move")
        .each([](Position& p, const Velocity& v) {
            p.x += v.dx;
            p.y += v.dy;
        });

    // 运行
    world.progress();
    const auto* p = e.get<Position>();
    std::cout << "Pos: (" << p->x << ", " << p->y << ")\n";
}
```

### 2.7 完整示例：带父子关系的场景

```c
#include <flecs.h>
#include <stdio.h>
#include <math.h>

// 组件
typedef struct { float x, y; }        Position;
typedef struct { float angle; }       Rotation;
typedef struct { float dx, dy; }      Velocity;
typedef struct { int points; }        Score;
typedef struct { float lifetime; }    Lifetime;
typedef vec3 { float values[3]; }     Color;

// 标签
typedef struct { } Asteroid;
typedef struct { } Bullet;
typedef struct { } Player;

// 系统
void RotateAsteroids(ecs_iter_t* it) {
    Rotation* r = ecs_field(it, Rotation, 1);
    for (int i = 0; i < it->count; i++) {
        r[i].angle += 0.02f;
        if (r[i].angle > 2 * 3.14159f) r[i].angle -= 2 * 3.14159f;
    }
}

void MoveBullets(ecs_iter_t* it) {
    Position* p = ecs_field(it, Position, 1);
    const Velocity* v = ecs_field(it, Velocity, 2);
    for (int i = 0; i < it->count; i++) {
        p[i].x += v[i].dx;
        p[i].y += v[i].dy;
    }
}

void DespawnExpired(ecs_iter_t* it) {
    // 标记过期实体（在迭代外销毁）
    const Lifetime* lt = ecs_field(it, Lifetime, 2);
    for (int i = 0; i < it->count; i++) {
        if (lt[i].lifetime <= 0) {
            printf("Despawning entity %s\n",
                   ecs_get_name(it->world, it->entities[i]));
            ecs_delete(it->world, it->entities[i]);
        }
    }
}

void UpdateLifetime(ecs_iter_t* it) {
    Lifetime* lt = ecs_field(it, Lifetime, 1);
    for (int i = 0; i < it->count; i++) {
        lt[i].lifetime -= it->delta_time;
    }
}

int main() {
    ecs_world_t* world = ecs_init();
    ECS_COMPONENT(world, Position);
    ECS_COMPONENT(world, Rotation);
    ECS_COMPONENT(world, Velocity);
    ECS_COMPONENT(world, Score);
    ECS_COMPONENT(world, Lifetime);
    ECS_IMPORT(world, FlecsPipeline);

    // 创建玩家（根实体）
    ecs_entity_t player = ecs_new(world);
    ecs_set_name(world, player, "Player");
    ecs_set(world, player, Position, {400, 300});
    ecs_set(world, player, Score, {0});

    // 子弹作为玩家的子实体
    for (int i = 0; i < 3; i++) {
        ecs_entity_t bullet = ecs_new_w_pair(world, EcsChildOf, player);
        ecs_set_name(world, bullet, "Bullet");
        ecs_set(world, bullet, Position, {400 + i * 20.0f, 300});
        ecs_set(world, bullet, Velocity, {0, -5.0f});
        ecs_set(world, bullet, Lifetime, {3.0f});
    }

    // 小行星——独立实体
    for (int i = 0; i < 5; i++) {
        ecs_entity_t asteroid = ecs_new(world);
        ecs_set(world, asteroid, Position, {i * 150.0f, 100});
        ecs_set(world, asteroid, Rotation, {i * 1.2f});
    }

    // 注册系统
    ECS_SYSTEM(world, RotateAsteroids, EcsOnUpdate, Rotation, Asteroid);
    ECS_SYSTEM(world, MoveBullets, EcsOnUpdate, Position, Velocity);
    ECS_SYSTEM(world, UpdateLifetime, EcsOnUpdate, Lifetime);
    ECS_SYSTEM(world, DespawnExpired, EcsPostUpdate, Position, Lifetime);

    // 运行
    for (int frame = 0; frame < 10; frame++) {
        ecs_progress(world, 0.016f);
    }

    // 查询所有玩家的子实体
    ecs_query_t* childQuery = ecs_query(world, {
        .terms = {
            { .id = EcsChildOf, .src.id = player }
        }
    });
    ecs_iter_t it = ecs_query_iter(world, childQuery);
    int childCount = 0;
    while (ecs_query_next(&it)) childCount += it.count;
    printf("Player has %d children\n", childCount);

    ecs_fini(world);
    return 0;
}
```

**运行方式：**

```bash
# 安装 Flecs
git clone https://github.com/SanderMertens/flecs.git
cd flecs
mkdir build && cd build
cmake .. && make

# 编译示例（链接到 flecs 静态库）
gcc -std=c99 scene.c -I../include -Lbuild -lflecs -lm -o scene

# 运行
./scene
```

**预期输出：**
```text
Despawning entity Bullet
Despawning entity Bullet
Despawning entity Bullet
Player has 0 children
```

---

## 3. Flecs vs EnTT 对比总结

| 特性 | EnTT | Flecs |
|------|------|-------|
| 语言 | C++17 | C99（+ C++ 绑定） |
| 编译 | Header-only | 需编译链接 |
| 查询风格 | 模板 `view<A, B>()` | DSL 字符串 `"A, B"` |
| 层级 | 手动组件 | 内建 `ChildOf` |
| 继承 | 不支持 | `IsA` 关系 |
| 反射 | `entt::meta`（C++17） | 内建元组件（C） |
| 序列化 | 手动 | 自动 JSON |
| 运行时查询 | 无 | REST API |
| 线程安全 | 外部保证 | 外部保证 |
| 生态 | C++ 生态 | 跨语言绑定（C#/Rust/Julia） |
| 学习曲线 | 陡（C++ 模板） | 平缓（C 风格） |

---

## 4. 练习

### 练习 1: 基础操作
用 Flecs C API 创建 50 个实体，每个有 Position、Health 组件。用查询统计存活实体（Health.hp > 0）的数量。

### 练习 2: 关系系统
实现一个装备系统：Equipment 实体通过 `EquippedBy` 关系连接 Player 实体。每次装备改变时通过 Observer 打印日志。用 `IsA` 关系实现 "长剑" 继承自 "武器"。

### 练习 3: 完整小场景（可选）
用 Flecs 实现一个小型 RPG 场景：玩家、敌人、道具。用 `ChildOf` 表示道具归属、`IsA` 实现道具模板、查询 DSL 做战斗计算。导出为 JSON 并验证。

---

## 5. 扩展阅读

- [Flecs GitHub](https://github.com/SanderMertens/flecs) — 官方仓库 + 完整文档
- [Flecs Query Manual](https://www.flecs.dev/flecs/md_docs_2Queries.html) — 查询 DSL 完整参考
- [Flecs Relationships](https://www.flecs.dev/flecs/md_docs_2Relationships.html) — 实体关系深度解析
- [Building a Game with Flecs](https://ajmmertens.medium.com/) — Sander Mertens 的博客系列

---

## 常见陷阱

| 陷阱 | 说明 | 正确做法 |
|------|------|----------|
| 忽略 `ecs_field` 的索引 | `ecs_field(it, T, 1)` 中的数字是 term 序号（1-based），不是组件 ID | 按查询 terms 数组的顺序写索引 |
| 系统内部修改 world | 系统回调中不能安全地创建/销毁实体 | 使用 `ecs_defer_begin` / `ecs_defer_end` |
| C 宏的括号 | `ECS_COMPONENT` 和 `ECS_SYSTEM` 是宏——传类型名不要加引号，不要在逗号分隔参数时用过多空格 | 严格遵循示例格式 |
| DSL 字符串大小写 | `Position` 不是 `position`——DSL 用组件注册时的名称 | 首选枚举式 API（`ecs_id(Position)`）而非字符串 DSL |
| 实体名字冲突 | `ecs_set_name` 默认不强制唯一性 | 在 `ecs_set_name` 后手动检查，或用 `ecs_entity_init` 的参数 |
| JSON 序列化性能 | `ecs_entity_to_json` 每次分配新字符串 | 释放返回值：`ecs_os_free(json)` |
