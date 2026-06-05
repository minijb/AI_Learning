---
title: "Rust ECS 生态对比"
updated: 2026-06-05
---

# Rust ECS 生态对比

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 3-5 小时
> 前置知识: Rust 基础、Bevy ECS 基础、ECS 原理

---

## 1. 概念讲解

### 为什么需要对比？

Rust 生态中存在多个 ECS 库，它们的设计哲学差异巨大。选择错误的库可能导致严重的性能问题或架构上的死胡同。本节对比 4 个主流库：**Legion**、**Bevy ECS**、**Shipyard**、**Planeshift**（后更名为 `hecs`）。

| 库 | 作者/组织 | 设计理念 | 状态 |
|----|----------|---------|------|
| **Legion** | Amethyst 团队 | 从 Specs 迭代而来，Chunk-based Archetype | 维护模式（社区 fork 活跃） |
| **Bevy ECS** | Bevy 引擎团队 | 引擎集成、App Builder、编译期验证 | 最活跃 |
| **Shipyard** | leudz | 基于 Workload 的系统编排、Sparse Set | 稳定但慢 |
| **hecs** | Ralith | 极简 Archetype ECS，无调度器 | 活跃维护 |

### 核心设计差异

#### 存储策略

```
Legion / Bevy ECS（Archetype）：
┌────────────────────────────────────────────┐
│ Archetype {Pos, Vel}  │ Archetype {Pos}    │
│ [Chunk 0] [Chunk 1]   │ [Chunk 0]          │
│ Pos|Pos|Pos|Pos       │ Pos|Pos            │
│ Vel|Vel|Vel|Vel       │                    │
└────────────────────────────────────────────┘

Shipyard（Sparse Set）：
┌────────────────────────────────────────────┐
│ Position SparseSet    │ Velocity SparseSet │
│ Sparse: [entity→idx]  │ Sparse: [entity→idx]│
│ Dense:  [Pos|Pos|Pos] │ Dense:  [Vel|Vel]  │
└────────────────────────────────────────────┘

hecs（Archetype，无 Chunk）：
┌────────────────────────────────────────────┐
│ Archetype {Pos, Vel}: Vec<(Pos, Vel)>      │
│ Archetype {Pos}:      Vec<Pos>             │
└────────────────────────────────────────────┘
```

**含义**：
- **Archetype（Bevy/Legion）**：迭代时所有组件在同一内存块中——超高的缓存局部性。但添加/移除组件需 Archetype 迁移（移动全部数据）。
- **Sparse Set（Shipyard/EnTT）**：添加/移除组件 O(1)。但多组件迭代时对每个组件分别随机访问——缓存不友好。
- **hecs**：Archetype 但不分 Chunk——简单，但大型 archetype 会导致 Vec 重分配开销。

#### API 风格

| 库 | 查询方式 | 系统定义 | 调度器 |
|----|---------|---------|--------|
| Legion | `Read<Pos> + Write<Vel>` | `#[system] fn` | Builder 模式 |
| Bevy ECS | `Query<&Pos, &mut Vel>` | 普通 fn | App Builder + SystemSet |
| Shipyard | `&Pos, &mut Vel` view macro | 普通 fn | Workload 系统 |
| hecs | `query::<(&Pos, &mut Vel)>()` | 无——手动迭代 | 无 |

---

## 2. 代码示例

### 2.1 Legion 基础用法

Legion 使用**类型元组**来描述查询，用 `#[system]` 属性宏标注系统函数：

```rust
use legion::prelude::*;

// 组件
#[derive(Clone, Copy, Debug, PartialEq)]
struct Position { x: f32, y: f32 }

#[derive(Clone, Copy, Debug, PartialEq)]
struct Velocity { dx: f32, dy: f32 }

#[derive(Clone, Copy, Debug, PartialEq)]
struct Health { hp: i32 }

#[derive(Clone, Copy, Debug, PartialEq)]
struct Player;

#[derive(Clone, Copy, Debug, PartialEq)]
struct Enemy;

// 系统定义——通过 Read/Write 声明访问模式
#[system(for_each)]
fn movement(pos: &mut Position, vel: &Velocity) {
    pos.x += vel.dx;
    pos.y += vel.dy;
}

#[system(for_each)]
fn damage_enemies(#[resource] dt: &f32, health: &mut Health) {
    // dt 从 World 资源中注入
    health.hp -= (10.0 * dt) as i32;
}

#[system]
fn print_player_pos(
    query: &mut Query<(Read<Position>, Read<Health>), With<Player>>,
) {
    for (pos, health) in query.iter() {
        println!("Player at ({:.1}, {:.1}), HP: {}", pos.x, pos.y, health.hp);
    }
}

// 调度器
fn build_schedule() -> Schedule {
    Schedule::builder()
        .add_system(movement_system())
        .add_system(damage_enemies_system())
        .add_system(print_player_pos_system())
        .build()
}

fn main() {
    let mut world = World::default();
    let mut resources = Resources::default();
    resources.insert(0.016f32);  // dt

    // 创建实体
    world.push((Position { x: 0.0, y: 0.0 },
                Velocity { dx: 1.0, dy: 0.0 },
                Health { hp: 100 },
                Player));

    for i in 0..5 {
        world.push((Position { x: i as f32 * 50.0, y: 200.0 },
                    Velocity { dx: -0.5, dy: 0.0 },
                    Health { hp: 30 },
                    Enemy));
    }

    let mut schedule = build_schedule();
    for _ in 0..10 {
        schedule.execute(&mut world, &mut resources);
    }
}
```

### 2.2 Shipyard 的 Workload 系统

Shipyard 使用宏和 trait 来定义系统。它的 `World` 是组件存储，`Workload` 是系统编排：

```rust
use shipyard::prelude::*;

#[derive(Clone, Copy, Debug)]
struct Position(f32, f32);
#[derive(Clone, Copy, Debug)]
struct Velocity(f32, f32);
#[derive(Clone, Copy, Debug)]
struct Health(i32);

// 系统——使用 view! 宏
fn movement(pos: ViewMut<Position>, vel: View<Velocity>) {
    for (pos, vel) in (&mut pos, &vel).iter() {
        pos.0 += vel.0;
        pos.1 += vel.1;
    }
}

fn health_check(health: View<Health>) {
    for health in health.iter() {
        println!("Health: {}", health.0);
    }
}

fn spawn_entities(mut entities: EntitiesViewMut,
                  mut pos: ViewMut<Position>,
                  mut vel: ViewMut<Velocity>,
                  mut health: ViewMut<Health>) {
    entities.add_entity(
        (&mut pos, &mut vel, &mut health),
        (Position(0.0, 0.0), Velocity(1.0, 0.0), Health(100)),
    );
}

fn main() {
    let world = World::new();

    // Workload——定义系统执行顺序和依赖
    world.run(|mut entities, pos, vel, health| {
        spawn_entities(mut entities, pos, vel, health);
    });

    world
        .add_workload("GameLoop")
        .with_system(system!(movement))
        .with_system(system!(health_check))
        .build();

    for _ in 0..5 {
        world.run_workload("GameLoop").unwrap();
    }
}
```

### 2.3 hecs 极简风格

hecs 放弃调度器，让用户完全手动控制系统执行：

```rust
use hecs::*;

#[derive(Debug)]
struct Position { x: f32, y: f32 }
#[derive(Debug)]
struct Velocity { dx: f32, dy: f32 }
#[derive(Debug)]
struct Health { hp: i32 }

fn main() {
    let mut world = World::new();

    // 创建实体
    let player = world.spawn((
        Position { x: 0.0, y: 0.0 },
        Velocity { dx: 1.0, dy: 0.0 },
        Health { hp: 100 },
    ));

    for i in 0..5 {
        world.spawn((
            Position { x: i as f32 * 50.0, y: 200.0 },
            Health { hp: 30 },
        ));
    }

    // 手动构建查询和迭代
    for _ in 0..5 {
        // 查询：有 Position 和 Velocity 的实体
        for (_, (pos, vel)) in world.query::<(&mut Position, &Velocity)>().iter() {
            pos.x += vel.dx;
            pos.y += vel.dy;
        }

        // 查询：所有有 Health 的实体
        let mut to_despawn = Vec::new();
        for (entity, health) in world.query::<&Health>().iter() {
            if health.hp <= 0 {
                to_despawn.push(entity);
            }
        }
        for e in to_despawn {
            world.despawn(e).unwrap();
        }
    }
}
```

### 2.4 同一场景：Legion vs Bevy ECS

用 Legion 实现第 32 节的 2D 游戏场景：

```rust
use legion::prelude::*;
use rand::Rng;

// ── 组件 ──────────────────────────────
#[derive(Clone, Copy, Debug, PartialEq)]
struct Position { x: f32, y: f32 }
#[derive(Clone, Copy, Debug, PartialEq)]
struct Velocity { dx: f32, dy: f32 }
#[derive(Clone, Copy, Debug, PartialEq)]
struct Health { hp: i32 }
#[derive(Clone, Copy, Debug, PartialEq)]
struct Collider { radius: f32 }
#[derive(Clone, Copy, Debug, PartialEq)]
struct Player;
#[derive(Clone, Copy, Debug, PartialEq)]
struct Enemy;

// ── 资源 ──────────────────────────────
#[derive(Clone, Debug)]
struct ScoreBoard { score: u32, game_over: bool, dt: f32 }

// ── 系统 ──────────────────────────────

#[system]
fn player_input(
    #[resource] keyboard: &Vec<KeyCode>,  // 简化：外部传入
    query: &mut Query<Write<Velocity>, With<Player>>,
) {
    for mut vel in query.iter_mut() {
        vel.dx = 0.0; vel.dy = 0.0;
        let speed = 200.0;
        for key in keyboard {
            match key {
                KeyCode::W => vel.dy = speed,
                KeyCode::S => vel.dy = -speed,
                KeyCode::A => vel.dx = -speed,
                KeyCode::D => vel.dx = speed,
                _ => {}
            }
        }
    }
}

#[system(for_each)]
fn movement(pos: &mut Position, vel: &Velocity, #[resource] dt: &ScoreBoard) {
    pos.x += vel.dx * dt.dt;
    pos.y += vel.dy * dt.dt;
}

#[system(for_each)]
fn enemy_ai(
    pos: &mut Position,
    vel: &mut Velocity,
    #[resource] player_pos: &Position,
) {
    let dx = player_pos.x - pos.x;
    let dy = player_pos.y - pos.y;
    let dist = (dx * dx + dy * dy).sqrt();
    if dist > 1.0 {
        let speed = 80.0;
        vel.dx = dx / dist * speed;
        vel.dy = dy / dist * speed;
    }
}

#[system]
fn collision_detection(
    players: &mut Query<(Read<Position>, Read<Collider>), With<Player>>,
    enemies: &mut Query<(Read<Position>, Read<Collider>, Write<Health>), With<Enemy>>,
    #[resource] score: &mut ScoreBoard,
) {
    let player_data: Vec<_> = players.iter().map(|(p, c)| (*p, *c)).collect();
    if player_data.is_empty() { return; }
    let (p_pos, p_col) = player_data[0];

    for (e_pos, e_col, health) in enemies.iter_mut() {
        let dx = p_pos.x - e_pos.x;
        let dy = p_pos.y - e_pos.y;
        if dx * dx + dy * dy < (p_col.radius + e_col.radius).powi(2) {
            health.hp -= 5;
            println!("Player hit! HP: {}", health.hp);
            if health.hp <= 0 {
                score.game_over = true;
            }
        }
    }
}

#[system]
fn despawn_dead(
    command_buffer: &mut CommandBuffer,
    query: &mut Query<(Entity, Read<Health>), With<Enemy>>,
    #[resource] score: &mut ScoreBoard,
) {
    for (entity, health) in query.iter() {
        if health.hp <= 0 {
            command_buffer.remove(*entity);
            score.score += 10;
            println!("Enemy killed! Score: {}", score.score);
        }
    }
}

#[system]
fn spawn_enemies(
    command_buffer: &mut CommandBuffer,
    #[resource] score: &mut ScoreBoard,
) {
    let mut rng = rand::thread_rng();
    command_buffer.push((
        Position { x: rng.gen_range(0.0..800.0), y: rng.gen_range(0.0..600.0) },
        Velocity { dx: rng.gen_range(-50.0..50.0), dy: rng.gen_range(-50.0..50.0) },
        Health { hp: 20 },
        Collider { radius: 10.0 },
        Enemy,
    ));
}

#[system]
fn print_state(#[resource] score: &ScoreBoard) {
    println!("Score: {} | Game Over: {}", score.score, score.game_over);
}

fn build_schedule() -> Schedule {
    Schedule::builder()
        .add_system(player_input_system())
        .add_system(enemy_ai_system())
        .flush()  // 同步点
        .add_system(movement_system())
        .add_system(collision_detection_system())
        .add_system(despawn_dead_system())
        .add_system(spawn_enemies_system())
        .add_system(print_state_system())
        .build()
}

// 简化 KeyCode enum
#[derive(Clone, Debug)]
enum KeyCode { W, A, S, D }

fn main() {
    let mut world = World::default();
    let mut resources = Resources::default();

    resources.insert(ScoreBoard { score: 0, game_over: false, dt: 0.016 });
    resources.insert(Position { x: 400.0, y: 300.0 });  // player_pos
    resources.insert(Vec::<KeyCode>::new());              // keyboard state

    // 生成玩家
    world.push((
        Position { x: 400.0, y: 300.0 },
        Velocity { dx: 0.0, dy: 0.0 },
        Health { hp: 100 },
        Collider { radius: 15.0 },
        Player,
    ));

    let mut schedule = build_schedule();
    for _frame in 0..100 {
        schedule.execute(&mut world, &mut resources);
    }
}
```

**Bevy 版本见第 32 节。对比要点**：

| 方面 | Legion | Bevy ECS |
|------|--------|----------|
| 系统定义 | `#[system]` 属性宏 | 普通 fn，参数类型驱动 |
| 查询 API | `Read<T>` / `Write<T>` / `Tagged<T>` | `Query<&T>` / `Query<&mut T>` |
| 单例 | `#[resource]` 参数注解 | `Res<T>` / `ResMut<T>` 参数 |
| 延迟操作 | `CommandBuffer`（手动声明） | `Commands`（自动提供） |
| 事件 | 无内建支持 | `EventWriter<T>` / `EventReader<T>` |
| 过滤 | `With<T>` / `Tagged<T>` | `With<T>` / `Without<T>` / `Changed<T>` |
| 调度器 | `Schedule::builder().flush()` | `SystemSet` + `chain()` / `before()` / `after()` |
| 维护状态 | 社区维护，活跃度下降 | 引擎团队维护，最活跃 |

---

## 3. 性能基准

以下数据来自 [ecs_bench_suite](https://github.com/rust-gamedev/ecs_bench_suite)（1M 实体，AMD Ryzen 7）：

| 操作 | Legion | Bevy ECS | Shipyard | hecs | EnTT (C++) |
|------|--------|----------|----------|------|-------------|
| 实体创建 (μs) | 850 | 920 | 1,100 | 780 | 620 |
| 1 组件迭代 (μs) | 210 | 240 | 380 | 190 | 170 |
| 3 组件迭代 (μs) | 450 | 480 | 890 | 410 | 320 |
| 添加组件 (μs) | 1,200 | 1,350 | 650 | 1,100 | 580 |
| 移除组件 (μs) | 1,150 | 1,300 | 620 | 1,050 | 540 |
| 内存 (MB/100K) | 8.2 | 8.5 | 12.3 | 7.8 | 6.1 |

**解读**：
- **迭代速度**：Archetype 方案（Legion/Bevy/hecs）略优于 Sparse Set 方案（Shipyard）。
- **组件添加/移除**：Sparse Set 方案（Shipyard）因不需要 Archetype 迁移而明显更快。
- **内存**：hecs 没有 Chunk 开销，内存最省。EnTT 因 C++ 无虚表开销而最小。
- **Bevy** 在 Chunk 编排上做了优化，虽比裸 Legion 稍慢但差距在可接受范围内。

---

## 4. 选型指南

```
项目需求决策树：

需要引擎集成（渲染/音频/输入）？
  ├─ 是 → Bevy（内置 ECS）
  └─ 否 ↓

团队熟悉 C++ 更多？
  ├─ 是 → EnTT（更好的性能，更成熟的生态）
  └─ 否 ↓

需要高级调度功能（Workload、SystemSet）？
  ├─ 是 ↓
  │   ├─ 需要活跃社区 → Bevy ECS
  │   └─ 接受稳定但慢 → Shipyard
  └─ 否 ↓

追求极简 + 手动控制？
  ├─ 是 → hecs
  └─ 否 → Legion（平衡）

项目规模 < 10K 实体 → 任意选，差别不大
项目规模 10K-100K  → Bevy ECS / Legion
项目规模 > 100K     → EnTT（C++）/ Bevy ECS（Rust）
```

---

## 5. 练习

### 练习 1: 跨库对比
用 Legion 和 hecs 分别实现同一个简单场景（100 个实体，有 Position + Velocity，每帧更新位置并统计平均坐标）。对比代码量和可读性。

### 练习 2: 性能基准
在你自己的机器上用 `ecs_bench_suite` 跑一遍基准测试。对比 Legion、Bevy ECS、hecs 在你的硬件上的实际性能。分析与你用例相关的瓶颈（迭代 vs 组件变更频率）。

### 练习 3: 从零选择（可选）
设计一个新项目（例如：一个回合制 Roguelike，10K 实体，频繁的 buff/debuff 添加移除）。用决策树选择库，写 200 字说明选择理由。

---

## 6. 扩展阅读

- [ecs_bench_suite](https://github.com/rust-gamedev/ecs_bench_suite) — Rust ECS 性能基准
- [Legion Book](https://github.com/amethyst/legion) — Legion 的 README 和示例
- [Specs vs Legion](https://github.com/amethyst/specs/blob/master/docs/legion_intro.md) — Amethyst 团队解释为何从 Specs 迁移到 Legion
- [Bevy ECS 内部实现](https://bevy-cheatbook.github.io/programming/ecs-intro.html) — 非官方但详尽的内部剖析

---

## 常见陷阱

| 陷阱 | 说明 | 正确做法 |
|------|------|----------|
| 过度依赖宏 | Legion 的 `#[system]` 宏隐藏了不少细节——出错时错误信息难读 | 先手动写迭代循环，确认正确后再改用宏 |
| Shipyard 的 `view!` 宏 | `view!` 宏中的类型顺序必须与系统参数顺序严格一致 | 使用 `system!` 宏自动处理匹配 |
| hecs 无调度器 | 需手动管理所有系统执行——容易写出竞态条件 | 小型项目 or 配合外部调度器（如 `bevy_tasks`） |
| 跨库社区差异 | Bevy ECS 更新极快——API 每 2-3 个月可能变动 | 锁定版本号，或跟随 Bevy 的主分支 |
| Legion 维护状态 | Legion 已处于维护模式，无计划添加事件系统 | 需要事件系统时选 Bevy ECS 或手动实现 |
