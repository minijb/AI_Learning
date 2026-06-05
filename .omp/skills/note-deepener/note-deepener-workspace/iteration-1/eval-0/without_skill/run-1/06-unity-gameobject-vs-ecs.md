# 6. Unity GameObject-Component 与纯 ECS

## 原始问题

> 和 Unity 的 GameObject-Component 模式有什么本质不同？

## 来源

- [ECS Back and Forth — Part 2 (skypjack)](https://skypjack.github.io/2019-03-07-ecs-baf-part-2/)（提到 Unity 采用 Archetype 变体）
- [Unity DOTS Documentation](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/index.html)
- [Flecs FAQ](https://github.com/SanderMertens/flecs/blob/master/docs/FAQ.md)

## Unity 的两套系统

Unity 实际上有**两套** Component 系统：

1. **传统 GameObject-Component（MonoBehaviour）**——大家熟知的 Unity
2. **Unity DOTS / ECS**——2018 年起推出的新一代架构

这两套系统**完全不同**。当我们说"Unity 的 GameObject-Component 模式"时，通常指前者。

## 传统 GameObject-Component 的真相

Unity 的传统模式**看起来像** ECS，但实际上是**披着 ECS 外衣的 OOP**。

```csharp
// Unity 传统方式
public class Player : MonoBehaviour {
    // 数据和行为混合在同一类中
    public float speed = 5f;
    public int health = 100;

    void Update() {
        // 行为直接写在 Component 里
        float h = Input.GetAxis("Horizontal");
        transform.Translate(h * speed * Time.deltaTime, 0, 0);
    }

    void OnCollisionEnter(Collision col) {
        health -= 10;
    }
}
```

## 本质区别：六维对比

### 1. 数据与行为的分离

| | 传统 Unity | 纯 ECS |
|---|---|---|
| Component 的内容 | **数据 + 行为**（都有） | **仅数据**（POD struct） |
| 逻辑所在 | Component 自己的 `Update()` 方法 | 独立的 System 函数 |

Unity 的 `MonoBehaviour` 是一个包含数据和方法的完整类，继承自 `UnityEngine.Object`。它**不是**纯数据组件——它是带有自己生命周期（`Awake`, `Start`, `Update`, `OnDestroy` 等）的微型对象。

### 2. 内存布局

```
Unity GameObject:

  GameObject "Player"
    ├── Transform (引用)
    ├── MeshRenderer (引用)
    ├── PlayerScript (引用)          ← 每个 Component 是一个独立的堆对象
    │   └── ... → 分散在内存各处
    └── Rigidbody (引用)             ← 通过指针引用，随机访问

纯 ECS:

  Position pool: [P0, P1, P2, P3, P4, ...]  ← 紧密连续数组
  Velocity pool: [V0, V1,     V3, ...]      ← 独立连续数组
  Health pool:   [H0,     H2, H3, ...]      ← 独立连续数组
```

在传统 Unity 中，`GetComponent<T>()` 是一个**字典查找**（或类似操作），`GameObject` 通过引用持有 Component。每个 Component 是独立分配的堆对象。遍历 1000 个 Enemy 意味着 1000 次间接引用和遍布内存的随机访问。

### 3. System 的角色

| | 传统 Unity | 纯 ECS |
|---|---|---|
| 谁在"执行" | 每个 Component 自己（`Update()` 中） | 外部 System 遍历符合条件的 Entity |
| 执行顺序 | `Script Execution Order` 设置（手动配置） | 显式 Pipeline / 依赖图 |
| 遍历方式 | Unity 引擎内部遍历所有 MonoBehaviour | System 只遍历拥有特定组件的 Entity |

```csharp
// 传统 Unity：每个 Enemy 自己更新自己
class Enemy : MonoBehaviour {
    void Update() {
        transform.Translate(Vector3.forward * speed * Time.deltaTime);
    }
}

// 纯 ECS (DOTS)：一个 System 处理所有 Enemy
partial struct MovementSystem : ISystem {
    void OnUpdate(ref SystemState state) {
        foreach (var (transform, speed) in
            SystemAPI.Query<RefRW<LocalTransform>, RefRO<Speed>>()) {
            transform.ValueRW.Position +=
                transform.ValueRO.Forward() * speed.ValueRO.value * deltaTime;
        }
    }
}
```

### 4. Entity 的角色

| | 传统 Unity | 纯 ECS |
|---|---|---|
| Entity 是什么 | `GameObject`——有名字、层级、Transform 等内置属性的完整对象 | 仅一个 ID（整数） |
| Entity 的行为 | 通过挂载的 Component 的 `Update()` 执行 | 没有任何行为——行为全在外部 System 中 |

在传统 Unity 中，`GameObject` 有 **大量内置状态**：名字、Tag、Layer、active 状态、Transform 层级、Scene 归属等。在纯 ECS 中，`Entity` 只是一个数字——如果你想要名字，你给它挂一个 `Name` 组件。

### 5. 继承 vs 组合

传统 Unity 仍然依赖 OOP 继承（尽管程度较轻）：

```csharp
// 你的脚本继承 MonoBehaviour
class Enemy : MonoBehaviour { }
class FlyingEnemy : Enemy { }    // 继承链！
class BossEnemy : FlyingEnemy { }
```

纯 ECS 完全通过组件组合：

```cpp
// 没有继承——只有组件
Entity boss = world.create();
world.emplace<Position>(boss, ...);
world.emplace<Health>(boss, 500, 500);
world.emplace<Flying>(boss);
world.emplace<BossTag>(boss);    // 只是一个空 tag
```

### 6. 缓存效率

传统 Unity 的 `Update()` 调用链：

```
Unity Engine → 遍历所有 GameObject →
  检查 active → 遍历 Component →
    调用虚函数 Update() →
      内部调用 GetComponent() →
        字典查找 → 随机内存访问
```

纯 ECS 的 System 执行：

```
MovementSystem:
  获取 Position[] 和 Velocity[] 的指针
  for i in 0..count:
    Position[i] += Velocity[i] * dt   ← 顺序访问，prefetch 友好
```

## Unity DOTS：Unity 自己的纯 ECS

Unity 在 2018 年推出了 **DOTS (Data-Oriented Technology Stack)**，包含：

- **Entities** 包——纯 ECS 实现
- **Burst Compiler**——将 C# IL 编译为高度优化的本机代码
- **Job System**——多线程任务调度
- **Mathematics** 包——SIMD 友好的数学库

```csharp
// Unity DOTS 方式（与纯 ECS 一致）
struct Player : IComponentData { }       // 纯数据
struct Speed : IComponentData {
    public float value;
}

partial struct MovementSystem : ISystem {
    void OnUpdate(ref SystemState state) {
        float dt = SystemAPI.Time.DeltaTime;
        foreach (var (transform, speed) in
            SystemAPI.Query<RefRW<LocalTransform>, RefRO<Speed>>()) {
            transform.ValueRW.Position +=
                transform.ValueRO.Forward() * speed.ValueRO.value * dt;
        }
    }
}
```

DOTS 的存储模型是 Archetype（与 Flecs 相同），这进一步拉开了与传统 GameObject-Component 的距离。

## 总结：一张表看清本质

| 维度 | 传统 Unity GameObject-Component | 纯 ECS (DOTS / EnTT / Flecs) |
|------|----------------------------------|-------------------------------|
| Component 内容 | 数据 + 行为（class，继承 MonoBehaviour） | 纯数据（struct，POD） |
| 逻辑位置 | Component 自己的方法内 | 独立 System 函数内 |
| Entity 本质 | GameObject（有名字/层级/Tag 等的完整对象） | 整数 ID |
| 内存布局 | 每个 Component 是独立堆对象，引用链接 | 同类型组件紧密数组（SoA） |
| 遍历方式 | Unity 引擎内循环 + 虚函数调用 | System 直接遍历连续数组 |
| 组合方式 | 继承 MonoBehaviour + 挂载组件 | 纯组件装配，无继承 |
| 并行能力 | 有限（主线程为主） | 天然适合多线程 |
| 缓存表现 | 差（随机内存访问） | 优（顺序访问，prefetch） |

## 为什么传统 Unity "看起来像" ECS？

Unity 从设计之初就借鉴了 Component 的概念，但其实现仍然是经典的 OOP。这种"看起来像 ECS"的设计让很多开发者误以为自己在使用 ECS，但实际上：

- Unity 的 Component 是 **行为 + 数据的封装体**（OOP 的延续）
- ECS 的 Component 是 **纯数据结构**（与行为完全分离）

这种混淆如此普遍，以至于 Unity 官方在推出 DOTS 时花了大量篇幅解释"这不是你认识的 Component"。
