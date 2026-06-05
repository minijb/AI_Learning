# OOP 继承 vs ECS 组合：钻石问题与内存革命

> 基于笔记: drafts/test-ecs.md
> 所属教程: ECS 架构深度剖析
> 章: 2/5

## 钻石问题（Diamond Problem）：继承的死穴

笔记中提到了经典的"钻石问题"。让我们把它具体化：

```cpp
// OOP 继承的噩梦
class GameObject {
    glm::vec3 position;
    // ... 100 个其他字段和虚函数
};

class PhysicsObject : public GameObject {
    float mass;
    glm::vec3 velocity;
};

class RenderableObject : public GameObject {
    Mesh* mesh;
    Material* material;
};

// 现在想要一个既能物理模拟又能渲染的对象
class PhysicsBall : public PhysicsObject, public RenderableObject {
    // 问题：position 从哪条路径继承？
    // PhysicsObject::GameObject::position  还是
    // RenderableObject::GameObject::position ？
};
```

这就是著名的**菱形继承（钻石）问题**。`PhysicsBall` 有两条路径到达 `GameObject`，导致：
1. `position` 有两份副本 —— 物理系统更新了一份，渲染系统读的是另一份
2. C++ 的虚拟继承（`virtual`）可以解决"两份数据"的问题，但引入了额外的间接寻址开销
3. 随着继承层次加深，谁拥有什么数据、谁修改了什么数据变得完全不可追踪

> 这不是理论问题。Unreal Engine 的 `UObject` 层次深到你怀疑人生，而 Unity 早年也因为 `MonoBehaviour` 的继承链导致大量困惑。 [来源: ECS FAQ - How is ECS different from OOP?](https://github.com/SanderMertens/ecs-faq)

## ECS 的答案：组合替代继承

ECS 彻底消除了继承层次。在 ECS 中：

```cpp
// 没有 GameObject 基类，没有继承链
struct Position { float x, y, z; };
struct Velocity { float dx, dy, dz; };
struct Mass { float value; };
struct Mesh { /* ... */ };
struct Material { /* ... */ };

// "物理球" = 一个实体 + 五个组件
Entity physics_ball = world.create();
world.emplace<Position>(physics_ball, 0, 0, 0);
world.emplace<Velocity>(physics_ball, 0, 0, 0);
world.emplace<Mass>(physics_ball, 1.0f);
world.emplace<Mesh>(physics_ball, sphere_mesh);
world.emplace<Material>(physics_ball, metal_material);

// "纯装饰球" = 同一个实体结构，只是不加 Velocity 和 Mass
Entity decorative_ball = world.create();
world.emplace<Position>(decorative_ball, 5, 0, 3);
world.emplace<Mesh>(decorative_ball, sphere_mesh);
world.emplace<Material>(decorative_ball, gold_material);
```

**没有任何继承，没有任何类型层次，没有任何重复数据。** 每个 Component 只有一份，存在它自己的连续数组中。

## 为什么组合更强大

| 维度 | OOP 继承 | ECS 组合 |
|------|---------|---------|
| 添加新能力 | 修改类层次或添加新基类 | 给实体加一个 Component |
| 运行时改变类型 | 几乎不可能（需要重新构造对象） | 增删 Component 即可 |
| 代码复用 | 通过继承链（脆弱） | 通过 System 匹配 Component 组合 |
| 跨"类型"复用 | 需要公共基类 | 任何实体只要挂上对应 Component 就能被处理 |
| 数据重复 | 继承层次越深，字段重复风险越大 | 每个 Component 全局只有一份存储 |

**核心洞察**：在游戏开发中，对象的"类型"往往是模糊且动态的。一个角色可能受伤后变成尸体（失去 `PlayerInput`，保留 `Position` 和 `Mesh`），可能捡起武器（增加 `Weapon` 组件），可能进入载具（增加 `VehiclePassenger` 组件）。在 OOP 中实现这些状态转换需要大量状态机代码和类型转换；在 ECS 中，只需要 `add<T>()` 和 `remove<T>()`。

## 内存布局的革命：从 AoS 到 SoA

这可能是 ECS 相对于 OOP **最实质性的性能优势**。

### OOP 的内存布局（AoS：Array of Structures）

```cpp
// OOP 中，对象在堆上单独分配
class GameObject {
    Position pos;   // 12 bytes
    Velocity vel;   // 12 bytes
    Health hp;      // 8 bytes
    // ... vtable pointer, padding ...
};

// 内存中的实际布局（简化）：
// [pos|vel|hp|...] [padding] [pos|vel|hp|...] [padding] ...
//   GameObject 0              GameObject 1
```

当 `MovementSystem` 只需要读取 `pos` 和 `vel` 时，CPU 仍然会把整个 `GameObject`（包括不相关的 `hp` 和其他字段）拉进缓存行。这不仅浪费了宝贵的缓存空间，还意味着每次访问一个对象时都可能触发一次缓存未命中（cache miss）——如果对象在堆上随机分配的话。

### ECS 的内存布局（SoA：Structure of Arrays）

```
Position 数组: [P0] [P1] [P2] [P3] [P4] [P5] [P6] ...
Velocity 数组: [V0] [V1] [V2] [V3] [V4] [V5] [V6] ...
Health 数组:   [H0] [H1] [H2] [H3] [H4] [H5] [H6] ...
```

当 `MovementSystem` 遍历所有 `Position + Velocity` 实体时：
1. 它只需访问 `Position` 数组和 `Velocity` 数组
2. 两个数组都是**连续**的 —— CPU 预取器（prefetcher）可以提前加载后续数据
3. 不会被无关的 `Health` 数据污染缓存行
4. 每次缓存行加载的都是**有效数据**，没有浪费

### 量化对比

假设一个缓存行是 64 字节：
- **OOP AoS**：一个 `GameObject` 可能占 64-128 字节，一个缓存行只包含 0.5-1 个对象。遍历 10000 个对象 ≈ 10000+ 次缓存未命中。
- **ECS SoA**：`Position` 是 12 字节，一个缓存行可以装 5 个 Position。遍历 10000 个对象 ≈ 2000 次缓存未命中（仅 Position）+ 2000 次（仅 Velocity）= 4000 次。

**减少了 60% 以上的缓存未命中。** 在实际基准测试中，对于大量实体的线性遍历，ECS 通常比等效的 OOP 实现快 2-5 倍。 [来源: Flecs FAQ - What is AoS/SoA?](https://github.com/SanderMertens/ecs-faq) [来源: EnTT ECS back and forth Part 1](https://skypjack.github.io/2019-02-14-ecs-baf-part-1/)

## 数据导向设计（Data-Oriented Design, DoD）

ECS 是 DoD 哲学在游戏开发中最典型的实践。DoD 的核心原则：

1. **先理解数据流，再写代码**：不是先想"有哪些类"，而是先想"每一帧要处理哪些数据，按什么顺序"
2. **按访问模式组织数据**：把经常一起访问的数据放在一起（SoA），不经常一起访问的分开（hot/cold splitting）
3. **为缓存层次编程**：理解 L1/L2/L3 cache 的大小和行大小，让数据访问模式对缓存友好

> DoD 不等于 ECS。DoD 是一种更广泛的思维模式——你可以用 DoD 的方式写 OOP 代码（尽管不太自然），而 ECS 是最能让 DoD 原则自然落地的架构。 [来源: ECS FAQ - Is ECS the same as DoD?](https://github.com/SanderMertens/ecs-faq)

## 什么时候不需要 ECS？

尽管 ECS 在性能和组织上有优势，但它不是万能药：
- **实体数量少（<1000）且类型固定**：OOP 的简单性可能更有价值
- **不需要动态组合**：如果游戏的类型层次稳定且浅，ECS 的灵活性可能是过度设计
- **团队不熟悉**：引入 ECS 有学习曲线，对于小团队和小项目可能不值得

正如 EnTT 的作者所说：> 除非你在做 AAA 游戏，否则使用 ECS 的主要原因是代码组织，而不是性能。 [来源: EnTT ECS back and forth Part 1](https://skypjack.github.io/2019-02-14-ecs-baf-part-1/)

## 下一步

理解了 ECS 的核心概念和内存优势后，下一章将回答笔记中的第一个问题：System 之间的执行顺序如何管理？多个 System 的依赖关系如何定义和调度？
