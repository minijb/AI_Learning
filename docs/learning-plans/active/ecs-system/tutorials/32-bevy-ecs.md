---
title: "Bevy ECS 详解"
updated: 2026-06-05
---

# Bevy ECS 详解

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 5-7 小时
> 前置知识: Rust 基础（所有权、生命周期、trait）、ECS 基础原理

---

## 1. 概念讲解

### 为什么需要 Bevy ECS？

Bevy 是一个用 Rust 编写的游戏引擎，其 ECS 层是引擎的心跳。与独立 ECS 库不同，Bevy ECS 深度集成到引擎的 App 模型中。它的设计哲学：

1. **Rust 类型系统驱动**：Component 是任何实现 `Component` trait 的类型（通常通过 `#[derive(Component)]`）。System 是普通函数，参数通过 trait 系统从 World 中自动提取。
2. **编译期查询验证**：`Query<&Position, &mut Velocity>` 在编译期检查组件访问冲突——不会有两个系统同时可变借用同一个组件。
3. **App Builder 模式**：通过链式 `.add_systems()`、`.add_plugins()` 构建整个应用。
4. **零成本抽象**：所有类型擦除发生在编译期，运行时没有虚函数调用。

### 核心设计

**Component**：任何 Rust 类型，标注 `#[derive(Component)]` 即可。存储在 `World` 中按 Archetype 组织。

```rust
#[derive(Component)]
struct Position { x: f32, y: f32 }

#[derive(Component)]
struct Velocity { dx: f32, dy: f32 }

#[derive(Component)]
struct Player;  // 零大小标记组件
```

**System**：参数从 `World` 中提取的函数。参数类型决定了系统访问什么：

```rust
fn move_system(
    mut query: Query<(&mut Position, &Velocity)>,
    time: Res<Time>,
) {
    for (mut pos, vel) in query.iter_mut() {
        pos.x += vel.dx * time.delta_seconds();
        pos.y += vel.dy * time.delta_seconds();
    }
}
```

系统参数的类型系统：

| 参数类型 | 含义 | 访问模式 |
|----------|------|----------|
| `Query<&T>` | 只读查询 | 共享引用 |
| `Query<&mut T>` | 可变查询 | 独占引用 |
| `Query<(&A, &B)>` | 多组件查询 | 按组合规则 |
| `Query<&T, With<A>>` | 过滤：必须有 A | |
| `Query<&T, Without<B>>` | 过滤：不能有 B | |
| `Query<&T, Changed<C>>` | 过滤：C 在本帧被修改 | |
| `Res<T>` | 资源（单例） | 共享引用 |
| `ResMut<T>` | 可变资源 | 独占引用 |
| `Commands` | 延迟实体操作 | |
| `EventWriter<E>` | 发送事件 | |
| `EventReader<E>` | 读取事件 | |

**App Builder**：整个应用的组装线：

```rust
fn main() {
    App::new()
        .add_plugins(DefaultPlugins)      // 默认插件组
        .add_systems(Startup, spawn_camera)
        .add_systems(Update, (move_system, collision_system))
        .run();
}
```

---

## 2. 代码示例

### 2.1 基础操作：生成、查询、修改

```rust
use bevy::prelude::*;

#[derive(Component)]
struct Position { x: f32, y: f32 }

#[derive(Component)]
struct Velocity { dx: f32, dy: f32 }

#[derive(Component)]
struct Health { current: i32, max: i32 }

fn spawn_entities(mut commands: Commands) {
    // 生成玩家
    commands.spawn((
        Position { x: 0.0, y: 0.0 },
        Velocity { dx: 1.0, dy: 0.0 },
        Health { current: 100, max: 100 },
        Name::new("Player"),
    ));

    // 批量生成敌人
    for i in 0..5 {
        commands.spawn((
            Position { x: i as f32 * 50.0, y: 200.0 },
            Velocity { dx: -0.5, dy: 0.0 },
            Health { current: 30, max: 30 },
            Name::new(format!("Enemy_{}", i)),
        ));
    }
}

fn movement(mut query: Query<(&mut Position, &Velocity)>, time: Res<Time>) {
    let dt = time.delta_seconds();
    for (mut pos, vel) in query.iter_mut() {
        pos.x += vel.dx * dt;
        pos.y += vel.dy * dt;
    }
}

fn print_positions(query: Query<(&Name, &Position)>) {
    for (name, pos) in query.iter() {
        println!("{}: ({:.1}, {:.1})", name, pos.x, pos.y);
    }
}

fn main() {
    App::new()
        .add_plugins(MinimalPlugins)  // 最小插件集，不加载渲染
        .add_systems(Startup, spawn_entities)
        .add_systems(Update, (movement, print_positions).chain())
        .run();
}
```

### 2.2 Query 过滤：With、Without、Changed

```rust
use bevy::prelude::*;

#[derive(Component)] struct Player;
#[derive(Component)] struct Enemy { score_value: u32 }
#[derive(Component)] struct Alive;
#[derive(Component)] struct Dead;
#[derive(Component)] struct Position { x: f32, y: f32 }

// 只对玩家实体操作
fn player_system(query: Query<&Position, With<Player>>) {
    for pos in query.iter() {
        println!("Player at ({:.1}, {:.1})", pos.x, pos.y);
    }
}

// 排除已死亡的实体
fn alive_enemy_system(mut query: Query<(&mut Position, &Enemy), (With<Alive>, Without<Dead>)>) {
    for (mut pos, enemy) in query.iter_mut() {
        pos.x += 0.1;
    }
}

// 只处理刚被修改的组件——性能优化
fn on_damage_taken(query: Query<&Health, Changed<Health>>) {
    for health in query.iter() {
        println!("Health changed! Now: {}/{}", health.current, health.max);
    }
}
```

### 2.3 Commands 延迟操作

`Commands` 不会立即执行——它们被缓冲，在系统执行后批量应用，保证 World 的一致性：

```rust
use bevy::prelude::*;

#[derive(Component)] struct Position { x: f32, y: f32 }
#[derive(Component)] struct Health { hp: i32 }
#[derive(Component)] struct Dead;

fn despawn_dead(
    mut commands: Commands,
    query: Query<(Entity, &Health)>,
) {
    for (entity, health) in query.iter() {
        if health.hp <= 0 {
            // 延迟执行——不会在当前迭代中立即删除
            commands.entity(entity).despawn();
            println!("Scheduled despawn for entity {:?}", entity);
        }
    }
}

fn spawn_wave(
    mut commands: Commands,
    time: Res<Time>,
    // Local 是系统本地状态
    mut last_spawn: Local<f32>,
) {
    if time.elapsed_seconds() - *last_spawn > 3.0 {
        for i in 0..5 {
            commands.spawn((
                Position { x: i as f32 * 60.0, y: 400.0 },
                Health { hp: 20 },
            ));
        }
        *last_spawn = time.elapsed_seconds();
        println!("Spawned wave!");
    }
}

// 向实体添加/移除组件
fn mark_dead(
    mut commands: Commands,
    query: Query<(Entity, &Health), Without<Dead>>,
) {
    for (entity, health) in query.iter() {
        if health.hp <= 0 {
            commands.entity(entity).insert(Dead);
        }
    }
}
```

### 2.4 Resource（单例）

Resource 是全局唯一的数据——适合配置、状态机、全局缓存：

```rust
use bevy::prelude::*;

#[derive(Resource)]
struct GameConfig {
    max_enemies: u32,
    spawn_interval: f32,
}

#[derive(Resource, Default)]
struct ScoreBoard {
    player_score: u32,
    wave: u32,
}

// 默认插入
impl Default for GameConfig {
    fn default() -> Self {
        GameConfig { max_enemies: 50, spawn_interval: 2.0 }
    }
}

fn setup(mut commands: Commands) {
    commands.insert_resource(GameConfig::default());
    commands.insert_resource(ScoreBoard::default());
}

fn spawn_system(
    mut commands: Commands,
    config: Res<GameConfig>,
    mut score: ResMut<ScoreBoard>,
) {
    if score.wave < config.max_enemies {
        // ...
        score.wave += 1;
    }
}
```

### 2.5 Events 系统

Events 是 Bevy 中的消息传递机制——先入队，下帧读取：

```rust
use bevy::prelude::*;

#[derive(Event)]
struct DamageEvent {
    attacker: Entity,
    target: Entity,
    amount: i32,
}

#[derive(Component)] struct Health { hp: i32 }

fn attack_system(
    mut damage_events: EventWriter<DamageEvent>,
    query: Query<Entity>,
) {
    // 发送事件
    let entities: Vec<Entity> = query.iter().collect();
    if entities.len() >= 2 {
        damage_events.send(DamageEvent {
            attacker: entities[0],
            target: entities[1],
            amount: 15,
        });
    }
}

fn damage_system(
    mut damage_events: EventReader<DamageEvent>,
    mut query: Query<&mut Health>,
) {
    // 读取事件（一次性消费）
    for ev in damage_events.read() {
        if let Ok(mut health) = query.get_mut(ev.target) {
            health.hp -= ev.amount;
            println!("Entity {:?} took {} damage! HP: {}",
                     ev.target, ev.amount, health.hp);
        }
    }
}

fn main() {
    App::new()
        .add_plugins(MinimalPlugins)
        .add_event::<DamageEvent>()
        .add_systems(Update, (attack_system, damage_system).chain())
        .run();
}
```

### 2.6 SystemSet 与执行顺序

```rust
use bevy::prelude::*;

#[derive(SystemSet, Debug, Hash, PartialEq, Eq, Clone)]
enum GameSet {
    Input,
    Physics,
    Collision,
    Rendering,
}

fn input_system()    { println!("-- Input --"); }
fn physics_system()  { println!("-- Physics --"); }
fn collision_system(){ println!("-- Collision --"); }
fn render_system()   { println!("-- Render --"); }

fn main() {
    App::new()
        .add_plugins(MinimalPlugins)
        .configure_sets(Update, (
            GameSet::Input,
            GameSet::Physics.after(GameSet::Input),
            GameSet::Collision.after(GameSet::Physics),
            GameSet::Rendering.after(GameSet::Collision),
        ))
        .add_systems(Update, input_system.in_set(GameSet::Input))
        .add_systems(Update, physics_system.in_set(GameSet::Physics))
        .add_systems(Update, collision_system.in_set(GameSet::Collision))
        .add_systems(Update, render_system.in_set(GameSet::Rendering))
        .run();
}
```

### 2.7 Change Detection 性能优化

Bevy 自动跟踪每个组件是否在本帧被修改。`Changed<T>` 过滤器让你跳过未变更的数据：

```rust
use bevy::prelude::*;

#[derive(Component)] struct Position { x: f32, y: f32 }
#[derive(Component)] struct DirtyFlag;

// 只有移动过的实体才重新计算边界
fn update_bounds(
    mut commands: Commands,
    query: Query<Entity, (With<Position>, Changed<Position>)>,
) {
    for entity in query.iter() {
        commands.entity(entity).insert(DirtyFlag);
    }
}

// 懒更新：只处理标记了 DirtyFlag 的
fn lazy_render(
    mut commands: Commands,
    query: Query<(Entity, &Position), With<DirtyFlag>>,
) {
    for (entity, pos) in query.iter() {
        println!("Rendering entity {:?} at ({}, {})", entity, pos.x, pos.y);
        commands.entity(entity).remove::<DirtyFlag>();
    }
}
```

### 2.8 完整示例：2D 游戏

以下是一个完整的微型游戏骨架——玩家移动 + 敌人 AI + 碰撞：

```rust
use bevy::prelude::*;
use rand::Rng;

// ── 组件 ──────────────────────────────────────
#[derive(Component)] struct Player;
#[derive(Component)] struct Enemy;
#[derive(Component)] struct Position { x: f32, y: f32 }
#[derive(Component)] struct Velocity { dx: f32, dy: f32 }
#[derive(Component)] struct Health { hp: i32 }
#[derive(Component)] struct Collider { radius: f32 }

// ── 资源 ──────────────────────────────────────
#[derive(Resource)] struct GameState { score: u32, game_over: bool }

#[derive(Event)] struct CollisionEvent { a: Entity, b: Entity }

// ── 系统 ──────────────────────────────────────

fn spawn_player(mut commands: Commands) {
    commands.spawn((
        Player, Name::new("Hero"),
        Position { x: 400.0, y: 300.0 },
        Velocity { dx: 0.0, dy: 0.0 },
        Health { hp: 100 },
        Collider { radius: 15.0 },
    ));
}

fn spawn_enemies(mut commands: Commands, time: Res<Time>, mut timer: Local<f32>) {
    *timer += time.delta_seconds();
    if *timer > 1.5 {
        *timer = 0.0;
        let mut rng = rand::thread_rng();
        commands.spawn((
            Enemy, Name::new("Enemy"),
            Position { x: rng.gen_range(0.0..800.0), y: rng.gen_range(0.0..600.0) },
            Velocity { dx: rng.gen_range(-50.0..50.0), dy: rng.gen_range(-50.0..50.0) },
            Health { hp: 20 },
            Collider { radius: 10.0 },
        ));
    }
}

fn player_input(
    keyboard: Res<ButtonInput<KeyCode>>,
    mut query: Query<&mut Velocity, With<Player>>,
) {
    if let Ok(mut vel) = query.get_single_mut() {
        vel.dx = 0.0; vel.dy = 0.0;
        let speed = 200.0;
        if keyboard.pressed(KeyCode::KeyW) { vel.dy = speed; }
        if keyboard.pressed(KeyCode::KeyS) { vel.dy = -speed; }
        if keyboard.pressed(KeyCode::KeyA) { vel.dx = -speed; }
        if keyboard.pressed(KeyCode::KeyD) { vel.dx = speed; }
    }
}

fn movement(mut query: Query<(&mut Position, &Velocity)>, time: Res<Time>) {
    let dt = time.delta_seconds();
    for (mut pos, vel) in query.iter_mut() {
        pos.x += vel.dx * dt;
        pos.y += vel.dy * dt;
    }
}

fn enemy_ai(
    player_q: Query<&Position, With<Player>>,
    mut enemy_q: Query<(&mut Velocity, &Position), With<Enemy>>,
) {
    if let Ok(player_pos) = player_q.get_single() {
        for (mut vel, pos) in enemy_q.iter_mut() {
            let dx = player_pos.x - pos.x;
            let dy = player_pos.y - pos.y;
            let dist = (dx * dx + dy * dy).sqrt();
            if dist > 1.0 {
                let speed = 80.0;
                vel.dx = dx / dist * speed;
                vel.dy = dy / dist * speed;
            }
        }
    }
}

fn collision_detection(
    players: Query<(Entity, &Position, &Collider), With<Player>>,
    enemies: Query<(Entity, &Position, &Collider), With<Enemy>>,
    mut collision_events: EventWriter<CollisionEvent>,
) {
    for (p_entity, p_pos, p_col) in players.iter() {
        for (e_entity, e_pos, e_col) in enemies.iter() {
            let dx = p_pos.x - e_pos.x;
            let dy = p_pos.y - e_pos.y;
            let dist_sq = dx * dx + dy * dy;
            let min_dist = p_col.radius + e_col.radius;
            if dist_sq < min_dist * min_dist {
                collision_events.send(CollisionEvent {
                    a: p_entity,
                    b: e_entity,
                });
            }
        }
    }
}

fn handle_collisions(
    mut reader: EventReader<CollisionEvent>,
    mut health_q: Query<&mut Health>,
    mut state: ResMut<GameState>,
) {
    for ev in reader.read() {
        if let Ok(mut health) = health_q.get_mut(ev.a) {
            health.hp -= 5;
            println!("Player hit! HP: {}", health.hp);
            if health.hp <= 0 {
                state.game_over = true;
                println!("GAME OVER!");
            }
        }
    }
}

fn despawn_dead_enemies(
    mut commands: Commands,
    query: Query<(Entity, &Health), With<Enemy>>,
    mut state: ResMut<GameState>,
) {
    for (entity, health) in query.iter() {
        if health.hp <= 0 {
            commands.entity(entity).despawn();
            state.score += 10;
            println!("Enemy killed! Score: {}", state.score);
        }
    }
}

fn print_state(state: Res<GameState>) {
    if state.is_changed() {
        println!("Score: {}, Game Over: {}", state.score, state.game_over);
    }
}

// ── 主入口 ────────────────────────────────────

fn main() {
    App::new()
        .add_plugins(MinimalPlugins)
        .insert_resource(GameState { score: 0, game_over: false })
        .add_event::<CollisionEvent>()
        .add_systems(Startup, spawn_player)
        .add_systems(Update, (
            player_input,
            enemy_ai,
            spawn_enemies,
            movement,
            collision_detection,
            handle_collisions,
            despawn_dead_enemies,
            print_state,
        ).chain())
        .run();
}
```

**运行方式：**

```bash
# 创建项目
cargo new bevy_game && cd bevy_game

# 编辑 Cargo.toml 添加依赖：
# [dependencies]
# bevy = "0.14"
# rand = "0.8"

cargo run
```

**预期输出：**
```text
Player hit! HP: 95
Enemy killed! Score: 10
Player hit! HP: 90
Enemy killed! Score: 20
...
```

### 2.9 Bevy ECS vs 传统 Rust OOP

```rust
// ─── 传统 OOP 风格 ──────────────────────────
struct GameObject {
    x: f32, y: f32,
    dx: f32, dy: f32,
    hp: i32,
    kind: ObjectKind,  // enum { Player, Enemy, Bullet }
}

struct GameWorld {
    objects: Vec<GameObject>,
}

impl GameWorld {
    fn update(&mut self) {
        for obj in &mut self.objects {
            match obj.kind {
                ObjectKind::Player => { /* 玩家逻辑 */ }
                ObjectKind::Enemy  => { /* 敌人逻辑 */ }
                ObjectKind::Bullet => { /* 子弹逻辑 */ }
            }
            obj.x += obj.dx;
            obj.y += obj.dy;
        }
    }
}
// 问题：
// 1. 所有游戏对象共享同一 struct——缓存浪费（子弹不需要 hp）
// 2. match 分支在热路径——分支预测失败开销大
// 3. 新增类型需修改 enum 和所有 match——
//    违反开闭原则

// ─── Bevy ECS 风格 ───────────────────────────
// 见上文完整示例。
// 优势：
// 1. 按组件组合存储——Position+Velocity 在连续内存中
// 2. 按系统职责分离——移动系统只迭代 Position+Velocity 实体
// 3. 新增类型只需添加组件组合——无需修改现有代码
```

---

## 3. 练习

### 练习 1: 基础操作
用 Bevy 创建一个应用，生成 100 个随机位置的实体。实现一个系统在每帧输出所有实体的平均位置。用 `Changed<Position>` 优化——只在有实体移动时重新计算。

### 练习 2: 小游戏扩展
在上面的 2D 游戏骨架中扩展：
1. 添加子弹系统——玩家按空格发射子弹
2. 子弹碰到敌人时造成 15 点伤害
3. 用 Events 解耦射击和碰撞

### 练习 3: ECS 设计模式（可选）
实现一个 Buff/Debuff 系统：
- Buff 组件包含 `duration`、`effect_type`
- 用 `Commands` 在实体上动态添加/移除 `SpeedModifier` 等效果组件
- 用 `SystemSet` 保证 Buff 系统在移动系统之前执行
- 用 `RemovedComponents<T>` 检测 Buff 过期并触发事件

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```rust
> use bevy::prelude::*;
> use rand::Rng;
>
> #[derive(Component)]
> struct Position { x: f32, y: f32 }
>
> #[derive(Component)]
> struct Velocity { dx: f32, dy: f32 }
>
> // 缓存资源——存储上一帧的平均位置和是否需要重算
> // 如果没有任何实体 Changed<Position>，则复用缓存
> #[derive(Resource, Default)]
> struct AveragePositionCache {
>     avg_x: f32,
>     avg_y: f32,
>     entity_count: usize,
>     dirty: bool,  // true = 本帧有实体移动，需要重算
> }
>
> fn spawn_entities(mut commands: Commands) {
>     let mut rng = rand::thread_rng();
>     for _ in 0..100 {
>         commands.spawn((
>             Position {
>                 x: rng.gen_range(-500.0..500.0),
>                 y: rng.gen_range(-500.0..500.0),
>             },
>             Velocity {
>                 dx: rng.gen_range(-10.0..10.0),
>                 dy: rng.gen_range(-10.0..10.0),
>             },
>         ));
>     }
> }
>
> fn movement(
>     mut query: Query<(&mut Position, &Velocity)>,
>     time: Res<Time>,
> ) {
>     let dt = time.delta_seconds();
>     for (mut pos, vel) in query.iter_mut() {
>         pos.x += vel.dx * dt;
>         pos.y += vel.dy * dt;
>     }
> }
>
> // ── 核心优化：仅在 Changed<Position> 时重算平均位置 ──
> // 步骤 1：标记缓存为 dirty（如果任何 Position 被修改）
> fn detect_changes(
>     changed_query: Query<(), Changed<Position>>,
>     mut cache: ResMut<AveragePositionCache>,
> ) {
>     // 即使只有 1 个实体移动，也要重算——Changed 查询本身是 O(1)（仅检查 Archetype 级别的 change tick）
>     if changed_query.iter().count() > 0 {
>         cache.dirty = true;
>     }
> }
>
> // 步骤 2：如果 dirty，重新计算平均值；否则跳过
> fn compute_average(
>     query: Query<&Position>,
>     mut cache: ResMut<AveragePositionCache>,
> ) {
>     if !cache.dirty {
>         // 无任何实体移动——直接复用缓存
>         println!("(cached) Average: ({:.1}, {:.1})",
>             cache.avg_x, cache.avg_y);
>         return;
>     }
>
>     let count = query.iter().count();
>     if count == 0 { return; }
>
>     let (mut sum_x, mut sum_y) = (0.0f32, 0.0f32);
>     for pos in query.iter() {
>         sum_x += pos.x;
>         sum_y += pos.y;
>     }
>
>     cache.avg_x = sum_x / count as f32;
>     cache.avg_y = sum_y / count as f32;
>     cache.entity_count = count;
>     cache.dirty = false;
>
>     println!("(recomputed) Average: ({:.1}, {:.1}) over {} entities",
>         cache.avg_x, cache.avg_y, count);
> }
>
> fn main() {
>     App::new()
>         .add_plugins(MinimalPlugins)
>         .init_resource::<AveragePositionCache>()
>         .add_systems(Startup, spawn_entities)
>         .add_systems(Update, (
>             movement,
>             // 必须先 detect_changes 再 compute_average
>             detect_changes,
>             compute_average.after(detect_changes),
>         ).chain())
>         .run();
> }
> ```
>
> **Changed<Position> 的优化原理：**
> - Bevy 为每个 Archetype 维护 "change tick"——当该 Archetype 中任何 `Position` 被写入时，tick 递增
> - `Changed<Position>` 查询只返回 change tick 大于上次查询 tick 的实体——无需逐个比较数据
> - 如果一整帧没有任何实体移动，`detect_changes` 的 `iter().count()` 返回 0 → `dirty` 保持 false → `compute_average` 跳过 O(N) 求和
> - 注意：这里仍然遍历了一次 `all_positions` 来求和——真正避免的是**每帧都 O(N)**，而在静止帧完全跳过
> - 进阶优化：如果只有个别实体移动，可以增量更新平均值（`avg_new = (avg_old * N_old + delta) / N_new`）而非全量重算

> [!tip]- 练习 2 参考答案
> ```rust
> use bevy::prelude::*;
> use rand::Rng;
>
> // ── 组件 ──────────────────────────────────────
> #[derive(Component)] struct Player;
> #[derive(Component)] struct Enemy;
> #[derive(Component)] struct Bullet { damage: i32 }
> #[derive(Component)] struct Position { x: f32, y: f32 }
> #[derive(Component)] struct Velocity { dx: f32, dy: f32 }
> #[derive(Component)] struct Health { hp: i32 }
> #[derive(Component)] struct Collider { radius: f32 }
>
> // ── 事件 ──────────────────────────────────────
> #[derive(Event)]
> struct DamageEvent {
>     target: Entity,
>     amount: i32,
>     source: Entity,
> }
>
> #[derive(Event)]
> struct BulletHitEvent {
>     bullet: Entity,
>     enemy: Entity,
>     damage: i32,
> }
>
> // ── 发射子弹（按空格）──
> fn player_shoot(
>     mut commands: Commands,
>     keyboard: Res<ButtonInput<KeyCode>>,
>     player_query: Query<&Position, With<Player>>,
>     // 用 Local 缓存发射冷却，防止每帧连续发射
>     mut cooldown: Local<f32>,
>     time: Res<Time>,
> ) {
>     *cooldown -= time.delta_seconds();
>     if *cooldown > 0.0 { return; }
>
>     if keyboard.just_pressed(KeyCode::Space) {
>         if let Ok(player_pos) = player_query.get_single() {
>             commands.spawn((
>                 Bullet { damage: 15 },
>                 Position {
>                     x: player_pos.x + 30.0, // 从玩家前方发射
>                     y: player_pos.y,
>                 },
>                 Velocity { dx: 400.0, dy: 0.0 },
>                 Collider { radius: 5.0 },
>             ));
>             *cooldown = 0.3; // 300ms 冷却
>             println!("🔫 Bullet fired!");
>         }
>     }
> }
>
> // ── 子弹碰撞检测（子弹 vs 敌人）──
> fn bullet_collision(
>     bullets: Query<(Entity, &Position, &Bullet, &Collider)>,
>     enemies: Query<(Entity, &Position, &Collider), With<Enemy>>,
>     mut hit_events: EventWriter<BulletHitEvent>,
> ) {
>     for (b_entity, b_pos, bullet, b_col) in bullets.iter() {
>         for (e_entity, e_pos, e_col) in enemies.iter() {
>             let dx = b_pos.x - e_pos.x;
>             let dy = b_pos.y - e_pos.y;
>             let dist_sq = dx * dx + dy * dy;
>             let min_dist = b_col.radius + e_col.radius;
>
>             if dist_sq < min_dist * min_dist {
>                 // 委托事件处理伤害和销毁
>                 hit_events.send(BulletHitEvent {
>                     bullet: b_entity,
>                     enemy: e_entity,
>                     damage: bullet.damage,
>                 });
>                 break; // 一颗子弹只命中一个敌人
>             }
>         }
>     }
> }
>
> // ── 处理子弹命中事件：造成伤害 + 销毁子弹 ──
> fn handle_bullet_hits(
>     mut commands: Commands,
>     mut hit_events: EventReader<BulletHitEvent>,
>     mut health_query: Query<&mut Health>,
>     mut damage_events: EventWriter<DamageEvent>,
> ) {
>     for event in hit_events.read() {
>         // 销毁子弹
>         commands.entity(event.bullet).despawn();
>
>         // 造成伤害
>         if let Ok(mut health) = health_query.get_mut(event.enemy) {
>             health.hp -= event.damage;
>             println!("💥 Enemy {:?} took {} damage! HP: {}",
>                 event.enemy, event.damage, health.hp);
>
>             // 发送伤害事件（供 UI/HUD 系统消费）
>             damage_events.send(DamageEvent {
>                 target: event.enemy,
>                 amount: event.damage,
>                 source: event.bullet,
>             });
>
>             // 死亡检查
>             if health.hp <= 0 {
>                 commands.entity(event.enemy).despawn();
>                 println!("💀 Enemy {:?} destroyed!", event.enemy);
>             }
>         }
>     }
> }
>
> // ── 玩家-敌人碰撞 ──
> fn player_enemy_collision(
>     player_query: Query<&Position, (With<Player>, With<Collider>)>,
>     enemy_query: Query<(Entity, &Position, &Collider), With<Enemy>>,
>     mut damage_events: EventWriter<DamageEvent>,
> ) {
>     if let Ok(p_pos) = player_query.get_single() {
>         for (e_entity, e_pos, e_col) in enemy_query.iter() {
>             let dx = p_pos.x - e_pos.x;
>             let dy = p_pos.y - e_pos.y;
>             if dx * dx + dy * dy < e_col.radius * e_col.radius {
>                 damage_events.send(DamageEvent {
>                     target: e_entity,
>                     amount: 5, // 身体碰撞伤害
>                     source: Entity::PLACEHOLDER,
>                 });
>             }
>         }
>     }
> }
>
> // ── 显示伤害事件 ──
> fn log_damage(mut events: EventReader<DamageEvent>) {
>     for ev in events.read() {
>         println!("📊 Damage: {:?} received {} damage",
>             ev.target, ev.amount);
>     }
> }
> ```
>
> **Events 解耦的核心价值：**
> - `bullet_collision` 系统只负责检测碰撞 → 发送 `BulletHitEvent`
> - `handle_bullet_hits` 系统只负责处理命中 → 修改 HP、销毁实体、发送 `DamageEvent`
> - 添加新的碰撞反应（如粒子特效系统、音效系统）只需新增一个读取 `BulletHitEvent` 的系统，**无需修改碰撞检测代码**
> - Events 是双缓冲的——在帧 N 写入的事件，在帧 N+1（或同一帧内的后续 System）读取，避免 World 借用冲突

> [!tip]- 练习 3 参考答案（可选）
> ```rust
> use bevy::prelude::*;
> use std::time::Duration;
>
> // ── 时序控制：SystemSet 分层 ──
> #[derive(SystemSet, Debug, Hash, PartialEq, Eq, Clone)]
> enum GameLogicSet {
>     BuffApplication,   // 应用 Buff 效果（添加/移除修饰器）
>     Movement,          // 移动系统（受 SpeedModifier 影响）
>     BuffExpiration,    // 过期 Buff 清理
> }
>
> // ── 组件 ──────────────────────────────────────
> #[derive(Component)] struct Position { x: f32, y: f32 }
>
> // 速度修饰器——Buff 系统动态添加和移除这个组件
> #[derive(Component)]
> struct SpeedModifier {
>     multiplier: f32,   // 1.5 = 加速 50%，0.5 = 减速 50%
>     source: BuffType,
> }
>
> // Buff 组件——挂载在实体上，表示该实体正在受到某种 Buff
> #[derive(Component)]
> struct Buff {
>     buff_type: BuffType,
>     duration: f32,         // 剩余时间（秒）
>     original_duration: f32, // 原始时长（用于显示）
> }
>
> #[derive(Clone, Copy, PartialEq, Eq, Debug)]
> enum BuffType {
>     SpeedBoost,   // 加速 50%
>     Slow,         // 减速 50%
> }
>
> // ── 事件 ──────────────────────────────────────
> #[derive(Event)]
> struct BuffExpiredEvent {
>     entity: Entity,
>     buff_type: BuffType,
> }
>
> // ── 系统：应用 Buff 效果（在 BuffApplication 阶段执行）──
> fn apply_buffs(
>     // 查询所有有 Buff 但还没有 SpeedModifier 的实体
>     query: Query<(Entity, &Buff), Without<SpeedModifier>>,
>     mut commands: Commands,
> ) {
>     for (entity, buff) in query.iter() {
>         let modifier = match buff.buff_type {
>             BuffType::SpeedBoost => SpeedModifier {
>                 multiplier: 1.5,
>                 source: BuffType::SpeedBoost,
>             },
>             BuffType::Slow => SpeedModifier {
>                 multiplier: 0.5,
>                 source: BuffType::Slow,
>             },
>         };
>         commands.entity(entity).insert(modifier);
>         println!("✅ Applied {:?} buff to {:?}",
>             buff.buff_type, entity);
>     }
> }
>
> // ── 系统：移动（在 Movement 阶段执行，使用 SpeedModifier）──
> fn movement(
>     mut query: Query<(&mut Position, Option<&SpeedModifier>)>,
>     time: Res<Time>,
> ) {
>     let dt = time.delta_seconds();
>     let base_speed = 100.0;
>
>     for (mut pos, modifier) in query.iter_mut() {
>         let mult = modifier.map_or(1.0, |m| m.multiplier);
>         pos.x += base_speed * mult * dt;
>         pos.y += base_speed * mult * 0.1 * dt; // 微弱漂移
>     }
> }
>
> // ── 系统：衰减 Buff 持续时间 + 检测过期 ──
> fn tick_buffs(
>     time: Res<Time>,
>     mut query: Query<(Entity, &mut Buff)>,
>     mut commands: Commands,
>     mut expired_events: EventWriter<BuffExpiredEvent>,
> ) {
>     let dt = time.delta_seconds();
>     for (entity, mut buff) in query.iter_mut() {
>         buff.duration -= dt;
>         if buff.duration <= 0.0 {
>             // Buff 过期：移除 Buff 组件
>             commands.entity(entity).remove::<Buff>();
>             // 发送过期事件——由 BuffExpiration 阶段处理
>             expired_events.send(BuffExpiredEvent {
>                 entity,
>                 buff_type: buff.buff_type,
>             });
>             println!("⏰ Buff {:?} expired on {:?}",
>                 buff.buff_type, entity);
>         }
>     }
> }
>
> // ── 使用 RemovedComponents 检测 Buff 被移除 ──
> // RemovedComponents<T> 在 Bevy 0.14+ 中更名为 RemovedComponents
> fn on_buff_removed(
>     mut commands: Commands,
>     mut removed: RemovedComponents<Buff>,
>     // 需要知道移除了哪种 Buff 的 SpeedModifier 也要移除
>     speed_query: Query<&SpeedModifier>,
>     mut expired_events: EventReader<BuffExpiredEvent>,
> ) {
>     // 方法 1：通过 RemovedComponents 检测（不需要事件）
>     for entity in removed.read() {
>         if let Ok(modifier) = speed_query.get(entity) {
>             let buff_type = modifier.source;
>             commands.entity(entity).remove::<SpeedModifier>();
>             println!("🧹 Cleaned up {:?} SpeedModifier from {:?}",
>                 buff_type, entity);
>         }
>     }
>
>     // 方法 2：通过事件检测（在 BuffExpiration 阶段）
>     for event in expired_events.read() {
>         // 双重保险：如果还有 SpeedModifier 残留则清理
>         if let Ok(modifier) = speed_query.get(event.entity) {
>             if modifier.source == event.buff_type {
>                 commands.entity(event.entity)
>                     .remove::<SpeedModifier>();
>                 println!("🧹 (via event) Cleaned up {:?} from {:?}",
>                     event.buff_type, event.entity);
>             }
>         }
>     }
> }
>
> // ── 施放 Buff 的测试系统（按数字键）──
> fn test_buff_input(
>     mut commands: Commands,
>     keyboard: Res<ButtonInput<KeyCode>>,
>     query: Query<Entity>, // 对存在的第一个实体施放
> ) {
>     if keyboard.just_pressed(KeyCode::Digit1) {
>         if let Some(entity) = query.iter().next() {
>             commands.entity(entity).insert(Buff {
>                 buff_type: BuffType::SpeedBoost,
>                 duration: 5.0,
>                 original_duration: 5.0,
>             });
>             println!("⚡ SpeedBoost applied!");
>         }
>     }
>     if keyboard.just_pressed(KeyCode::Digit2) {
>         if let Some(entity) = query.iter().next() {
>             commands.entity(entity).insert(Buff {
>                 buff_type: BuffType::Slow,
>                 duration: 3.0,
>                 original_duration: 3.0,
>             });
>             println!("🐌 Slow applied!");
>         }
>     }
> }
>
> fn main() {
>     App::new()
>         .add_plugins(MinimalPlugins)
>         .add_event::<BuffExpiredEvent>()
>         // ═══ SystemSet 顺序保证 ───
>         .configure_sets(Update, (
>             GameLogicSet::BuffApplication,
>             GameLogicSet::Movement
>                 .after(GameLogicSet::BuffApplication),
>             GameLogicSet::BuffExpiration
>                 .after(GameLogicSet::Movement),
>         ))
>         // ═══ 系统注册 ═══
>         .add_systems(Startup, |mut commands: Commands| {
>             commands.spawn(Position { x: 0.0, y: 0.0 });
>         })
>         .add_systems(Update, (
>             apply_buffs.in_set(GameLogicSet::BuffApplication),
>             tick_buffs, // 可以在任何阶段（不影响 Set 顺序）
>             movement.in_set(GameLogicSet::Movement),
>             on_buff_removed.in_set(GameLogicSet::BuffExpiration),
>             test_buff_input,
>         ))
>         .run();
> }
> ```
>
> **SystemSet 时序关键点：**
>
> 1. **`BuffApplication` 先于 `Movement`**：确保当帧添加的 `SpeedModifier` 能立即影响移动计算
> 2. **`Movement` 先于 `BuffExpiration`**：过期的 Buff 速度修饰器在移动完成后再移除，不影响当帧移动
> 3. **`RemovedComponents<Buff>` 是 Bevy 内置机制**：每次 `Buff` 组件被移除时自动记录，下一帧可读取——比手动发事件更可靠（不依赖开发者记得发事件）
> 4. 如果用多个 `BuffType` 叠加（如同时有 SpeedBoost+Slow），需要将 `SpeedModifier` 改为乘法叠加（`multiplier *= 1.5 * 0.5`），或者用 `Vec<SpeedModifier>` 存储多个修饰器

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- [Bevy Book](https://bevyengine.org/learn/book/) — 官方教程
- [Bevy ECS 速查表](https://bevy-cheatbook.github.io/) — 非官方但极其实用的速查表
- [Rust ECS 模式](https://github.com/rust-gamedev/ecs_bench_suite) — 各 Rust ECS 的性能基准
- [Bevy 源码](https://github.com/bevyengine/bevy/tree/main/crates/bevy_ecs) — ECS crate 本身值得阅读

---

## 常见陷阱

| 陷阱 | 说明 | 正确做法 |
|------|------|----------|
| `Query<&mut T>` 冲突 | 同一系统中不能有两个 `Query<&mut T>` | 合并为一个 `Query<(&mut A, &mut B)>`，或分散到不同系统 |
| `Commands` 非即时 | `commands.entity(e).despawn()` 不会立即删除 | 在后续系统或同帧其他系统中实体仍然存在——考虑用 `Without<Dead>` 过滤 |
| `get_single()` vs `get(entity)` | `get_single()` 期望恰好 1 个匹配实体，否则 panic | 不确定时用 `query.iter().next()` 或 `get(entity)` |
| `Changed<T>` 的时机 | `Changed<T>` 在第一次添加 T 时不触发 | 需要首次也触发时额外检查 `Added<T>` |
| 系统参数顺序不重要 | 但借用规则不变——参数顺序不影响 `World` 的借用检查 | Rust 编译器保证正确性；编译过不了就调整参数 |
| `chain()` 不是依赖声明 | `.chain()` 保证执行顺序，但不保证数据依赖 | 数据依赖通过 Query 类型自动推导；`.chain()` 用于副作用顺序 |
| 忘记 `Res<Time>` | `time.delta_seconds()` 需要 `Res<Time>` 参数 | 每个需要 dt 的系统都加 `time: Res<Time>` |
