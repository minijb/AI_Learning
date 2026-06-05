# 2. ECS 与 OOP 继承的本质区别

## 来源

- [ECS Back and Forth — Part 1 (skypjack)](https://skypjack.github.io/2019-02-14-ecs-baf-part-1/)
- [Game Programming Patterns — Component (Robert Nystrom)](https://gameprogrammingpatterns.com/component.html)

## 钻石问题（Diamond Problem）

经典 OOP 继承面临的核心困境。假设游戏中有以下继承层次：

```
        GameObject
        /        \
   Movable    Renderable
        \        /
       Player (??)
```

- `GameObject` 定义了 `position`
- `Movable` 继承 `GameObject`，添加 `velocity`
- `Renderable` 继承 `GameObject`，添加 `meshId`
- `Player` 多重继承 `Movable` 和 `Renderable`

**问题**：`Player` 通过两条路径继承了 `GameObject`，因此拥有**两份** `position` 数据。哪一份是正确的？编译器不知道，程序员需要用虚继承（virtual inheritance）来手动解决，这又引入了额外的运行时开销和复杂性。

更深层的问题不止于此：

```cpp
// 如果需求变成"有的敌人会飞，有的不会"
// "有的装饰物要渲染但没有碰撞"
// "有一个会说话的门——它是物体，但有对话逻辑"
//
// 继承树会爆炸成：
//    GameObject
//    ├── Movable
//    │   ├── FlyingMovable
//    │   └── WalkingMovable
//    ├── Renderable
//    │   ├── AnimatedRenderable
//    │   └── StaticRenderable
//    ├── Interactable
//    │   ├── Talkable
//    │   └── Usable
//    └── ...（组合爆炸）
//
// 最后你发现你需要 FlyingInteractableTalkableWalkingMovableAnimatedRenderable
```

## 组合替代继承

ECS 的核心哲学：**组合优于继承**（Composition over Inheritance）。

OOP 中的 `Player` 类：

```cpp
class Player : public Movable, public Renderable, public CombatCapable {
    // 类爆炸：Player、Enemy、NPC、FlyingEnemy、Boss...
    // 每加一个"能力"就要重新设计继承树
};
```

ECS 中的 Player：

```cpp
Entity player = world.create();

// 组合需要的能力——运行时动态装配
world.emplace<Position>(player, 0, 0, 0);
world.emplace<Velocity>(player, 0, 0, 0);
world.emplace<Health>(player, 100, 100);
world.emplace<Renderable>(player, meshId_player, matId);
world.emplace<PlayerControlled>(player);  // 只是一个 tag

// 如果要让 Player 会飞——加一个组件即可，不用重构继承树
world.emplace<Flying>(player);

// 如果要让敌人也会说话——同样简单
world.emplace<Dialogue>(enemy, "我是反派！");
```

## ECS 中的"概念"不再以类的形式存在

一个重要的思维转变：在 ECS 中，**不存在 `Elf` 类或 `Player` 类**。你有的只是一批拥有特定 Component 组合的 Entity。

- OOP：`Elf` 是一个类，它的实例是 `Elf` 对象
- ECS：一个 Entity 拥有 `{Position, Velocity, Health, Renderable, ElfTag}` 这一组 Component，它"恰好表现得像"一个精灵

这种"概念"的消失是**刻意为之**——它给予了巨大的灵活性。一个 Entity 可以在运行时动态改变自己的能力组合，这在传统继承体系中几乎不可行（除非使用复杂的状态模式）。

## 代码对比

### OOP 方式

```cpp
class GameObject {
public:
    virtual void update(float dt) = 0;
    virtual void render() = 0;
};

class Movable : virtual public GameObject {
    Vector3 position, velocity;
public:
    void update(float dt) override {
        position += velocity * dt;
    }
};

class Renderable : virtual public GameObject {
    Mesh* mesh;
    Material* material;
public:
    void render() override { /* ... */ }
};

class Player : public Movable, public Renderable {
    int hp;
public:
    void update(float dt) override {
        Movable::update(dt);
        // Player-specific logic...
    }
};

// 主循环
std::vector<GameObject*> objects;
for (auto* obj : objects) {
    obj->update(dt);  // 虚函数调用，随机内存访问
}
```

### ECS 方式

```cpp
// 只有数据
struct Position { float x, y, z; };
struct Velocity { float dx, dy, dz; };
struct Health { int current, max; };
struct Renderable { int meshId, materialId; };
struct PlayerTag {};  // empty tag

// 只有逻辑
void movement_system(World& world, float dt) {
    for (auto [pos, vel] : world.query<Position, Velocity>()) {
        pos.x += vel.dx * dt;
        pos.y += vel.dy * dt;
        pos.z += vel.dz * dt;
    }
}

void render_system(World& world) {
    for (auto [pos, render] : world.query<Position, Renderable>()) {
        draw_mesh(render.meshId, render.materialId, pos);
    }
}

// 主循环
movement_system(world, dt);  // 连续内存遍历，cache 友好
render_system(world);
```

## 总结对比

| 维度 | OOP 继承 | ECS 组合 |
|------|----------|----------|
| 代码复用方式 | 继承层次 | 组件装配 |
| 运行时修改能力 | 困难（需重构继承） | 简单（添加/移除组件） |
| 内存布局 | 对象分散，随机访问 | 同类型组件连续存储 |
| 类型爆炸风险 | 高（组合数 = 类数） | 无（类 = Entity，没有子类型） |
| 虚函数开销 | 有 | 无 |
| 缓存命中率 | 低 | 高 |
