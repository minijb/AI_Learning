# Entity 详解：一切只是 ID

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 25 分钟
> 前置知识: ECS 概述、C++ 整数类型与结构体

---

## 1. 概念讲解

### 为什么 Entity 只是一个数字？

如果你在 Unity 中用过 `GameObject`，或在 Unreal 中使用过 `AActor`，你已经习惯了"实体就是一个对象实例"——它有方法、有成员变量、有自己的 `Update()` 和 `Destroy()`。

ECS 把这个观念彻底逆转：**Entity 不包含任何东西。它只是一个键（key），用来在外部表中查找数据。**

为什么这样设计？两个核心原因：

**原因 1：避免胖指针和碎片化。** 如果 Entity 是一个包含 `vector<Component*>` 的对象，那么 100 万个实体 = 100 万个独立对象在堆上分配，内存碎片严重，缓存局部性极差。

**原因 2：解耦数据与身份。** 实体的"身份"（ID）应该与实体的"当前状态"（组件集合）完全分离。同一个 ID 今天可能是一只鸟（有 `Position`、`Velocity`、`WingFlap`），明天被转换成一块石头（移除所有组件，只加 `Position` 和 `StaticMesh`）。ID 不变，数据全变。

### 核心思想：Entity = 索引 + 版本号

最简单的 Entity 是一个 `uint32_t`。但更好的设计是**泛型句柄（Generic Handle）**：包含索引和版本号（generation）。

```
struct Entity {
    uint32_t index;       // 在实体数组中的槽位索引
    uint32_t generation;  // 版本号：这个槽位被复用了几次
};
```

**为什么需要 generation（版本号）？** 考虑以下场景：

1. 创建一个实体，得到 Entity{ index=5, generation=0 }
2. 某个 System 存储了这个 Entity 的引用（比如"正在追踪实体的摄像机"）
3. 该实体被销毁。槽位 5 被释放。
4. 创建新实体，恰好分配到槽位 5。新 Entity{ index=5, generation=1 }
5. 那个持有旧引用的 System 尝试访问 Entity{5, 0}——但槽位 5 现在的版本是 1，不匹配！

**generation 检查**：在访问实体数据前，比较请求的 generation 与当前槽位的 generation。如果不匹配 → 实体已死，安全地忽略或报错。这就是**悬空引用（dangling reference）的无成本解决方案**——不需要引用计数、不需要 shared_ptr。

### 实体生命周期

```
        create_entity()
             │
             ▼
    ┌────[ 活跃 (ALIVE) ]◄──────────┐
    │        │                       │
    │   deactivate()            activate()
    │        │                       │
    │        ▼                       │
    │  [ 停用 (INACTIVE) ]─────►─────┘
    │        │
    │   destroy()
    │        │
    │        ▼
    └───►[ 已销毁 (DEAD) ]
              │
        槽位可能被后续 create_entity() 复用
        (generation 递增)
```

- **创建**：分配一个槽位，初始化 generation（新槽位 generation=0，复用槽位 generation++）
- **停用**：实体仍然存在，但所有 System 应跳过它。常用于"切出屏幕"的敌人——不销毁，但也不处理
- **激活**：重新启用已停用的实体
- **销毁**：标记槽位为空，递增 generation。组件数据被清理

### 实体上的标签和层级

虽然 ECS 的 Entity 只是 ID，但实际游戏开发中需要额外机制：

**标签（Tag）**：零大小的标记组件。如 `PlayerTag{}`、`EnemyTag{}`。不携带数据，只用于 System 查询过滤。

**层级关系（Hierarchy）**：通过组件实现，不是 Entity 的内置功能：
```cpp
struct Parent { Entity entity; };
struct Children { std::vector<Entity> entities; };
```
这种"关系也是组件"的设计保持了纯粹性——层级关系与其他组件一视同仁，可以被查询、修改。

### 对比 OOP 中的 GameObject/Actor

| 方面 | OOP GameObject | ECS Entity |
|------|----------------|------------|
| 是什么 | 包含所有数据和行为的对象实例 | 32~64 位的标识符 |
| 大小 | 数百到数千字节（包含所有组件引用） | 8 字节（uint64）或更少 |
| 创建成本 | new/构造函数/虚表初始化 | 递增计数器 |
| 销毁成本 | delete/析构链/虚表清理 | 标记槽位为空，递增 generation |
| 类型检查 | `dynamic_cast<Player*>(obj)` | 检查实体是否有 `PlayerTag` 组件 |
| "我是谁" | 由类层次定义 | 由当前拥有的组件集合定义 |
| 运行时变身 | 几乎不可能（需复制构造） | 添加/移除组件即可 |

---

## 2. 代码示例

```cpp
#include <iostream>
#include <vector>
#include <cstdint>
#include <cassert>

// ========== 方案一：C 风格简单 ID ==========
// 最简单的情况——Entity 只是一个整数
using EntityId = uint32_t;
constexpr EntityId INVALID_ENTITY = UINT32_MAX;

// ========== 方案二：泛型句柄（推荐） ==========
struct Entity {
    uint32_t index = 0;
    uint32_t generation = 0;

    bool operator==(const Entity& other) const {
        return index == other.index && generation == other.generation;
    }
    bool operator!=(const Entity& other) const { return !(*this == other); }

    // 支持作为 unordered_map 的 key
    struct Hash {
        size_t operator()(const Entity& e) const {
            return (static_cast<uint64_t>(e.index) << 32) | e.generation;
        }
    };
};

// ========== 实体管理器：维护槽位和版本号 ==========
class EntityManager {
public:
    Entity create() {
        if (!free_slots.empty()) {
            // 复用已释放的槽位
            uint32_t idx = free_slots.back();
            free_slots.pop_back();
            generations[idx]++;  // 关键：递增版本号，使旧引用失效
            alive[idx] = true;
            return Entity{idx, generations[idx]};
        }
        // 分配新槽位
        uint32_t idx = static_cast<uint32_t>(generations.size());
        generations.push_back(0);
        alive.push_back(true);
        return Entity{idx, 0};
    }

    void destroy(Entity e) {
        assert(is_alive(e) && "Cannot destroy dead entity");
        alive[e.index] = false;
        free_slots.push_back(e.index);
    }

    bool is_alive(Entity e) const {
        return e.index < generations.size()
            && generations[e.index] == e.generation
            && alive[e.index];
    }

    bool is_valid(Entity e) const {
        // 比 is_alive 更宽：entity 曾经存在过（generation 匹配），
        // 但可能已被销毁
        return e.index < generations.size()
            && generations[e.index] == e.generation;
    }

    size_t alive_count() const {
        return generations.size() - free_slots.size();
    }

private:
    std::vector<uint32_t> generations;   // 每个槽位的当前版本号
    std::vector<bool>     alive;         // 每个槽位是否存活
    std::vector<uint32_t> free_slots;    // 可复用的空槽位
};

// ========== 实体层级——通过组件实现 ==========
struct Parent   { Entity entity = {UINT32_MAX, 0}; };
struct Children { std::vector<Entity> list; };

// ========== 标签组件——零大小 ==========
struct PlayerTag {};
struct EnemyTag {};
struct ProjectileTag {};

// ========== 演示 ==========
int main() {
    EntityManager mgr;

    // 创建实体
    Entity player = mgr.create();
    std::cout << "创建 Player: index=" << player.index
              << " gen=" << player.generation << "\n";

    Entity enemy1 = mgr.create();
    std::cout << "创建 Enemy1: index=" << enemy1.index
              << " gen=" << enemy1.generation << "\n";

    Entity enemy2 = mgr.create();
    std::cout << "创建 Enemy2: index=" << enemy2.index
              << " gen=" << enemy2.generation << "\n";

    std::cout << "存活实体数: " << mgr.alive_count() << "\n\n";

    // ---- 演示 generation 保护 ----
    Entity enemy1_ref = enemy1;  // 保存引用
    mgr.destroy(enemy1);
    std::cout << "销毁 Enemy1。is_alive(enemy1_ref) = "
              << std::boolalpha << mgr.is_alive(enemy1_ref) << "\n";

    Entity enemy3 = mgr.create();  // 可能复用槽位 1
    std::cout << "创建 Enemy3: index=" << enemy3.index
              << " gen=" << enemy3.generation
              << " (复用了槽位 " << enemy1_ref.index << ")\n";

    // 旧引用现在无效——generation 不匹配
    std::cout << "用旧引用访问 is_alive(enemy1_ref) = "
              << mgr.is_alive(enemy1_ref) << " — 不会被误认为 Enemy3!\n\n";

    // ---- 演示层级关系 ----
    // 注意：层级关系数据存储在外部，不在 Entity 内部
    Children children;
    children.list.push_back(enemy2);
    children.list.push_back(enemy3);

    std::cout << "子实体列表: ";
    for (auto child : children.list) {
        std::cout << "Entity(" << child.index << "," << child.generation << ") ";
    }
    std::cout << "\n";

    // ---- 格式化的 Entity 输出 ----
    std::cout << "\n===== 总结 =====\n";
    std::cout << "Entity 只是 {index, generation} 对——总共 "
              << sizeof(Entity) << " 字节\n";
    std::cout << "它不拥有任何数据、不持有任何指针、不定义任何行为。\n";
    std::cout << "它唯一的作用：作为键去 Component 存储中查找数据。\n";

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 example.cpp -o example && ./example
```

**预期输出:**
```text
创建 Player: index=0 gen=0
创建 Enemy1: index=1 gen=0
创建 Enemy2: index=2 gen=0
存活实体数: 3

销毁 Enemy1。is_alive(enemy1_ref) = false
创建 Enemy3: index=1 gen=1 (复用了槽位 1)
用旧引用访问 is_alive(enemy1_ref) = false — 不会被误认为 Enemy3!

子实体列表: Entity(2,0) Entity(1,1)

===== 总结 =====
Entity 只是 {index, generation} 对——总共 8 字节
它不拥有任何数据、不持有任何指针、不定义任何行为。
它唯一的作用：作为键去 Component 存储中查找数据。
```

**关键观察**：enemy1 被销毁后槽位 1 被 enemy3 复用，generation 从 0 变为 1。持有旧引用 `{1,0}` 的代码查询 `is_alive` 时返回 `false`——不会误操作到 enemy3。这个安全检查完全是 O(1) 的整数比较，零额外开销。

---

## 3. 练习

### 练习 1: 实现实体回收策略

当前实现用 `free_slots` 栈（LIFO）回收槽位。请实现一个不同策略：

- **FIFO 回收**：使用队列，最早释放的槽位最先被复用
- 比较两种策略的 **generation 溢出风险**——哪种策略下某个槽位的 generation 更容易接近 `UINT32_MAX`？
- 如果 generation 真的溢出会发生什么？如何防护？

### 练习 2: 批量创建性能

编写一个基准测试程序：
1. 用 `EntityManager` 创建 100 万个实体
2. 销毁其中 50 万个
3. 再创建 50 万个
4. 测量每个阶段的时间

对比用 `new GameObject()` / `delete obj` 完成同样操作的时间（估算即可，不需要真的实现 OOP 版本）。分析差距的原因。

### 练习 3: 设计关系组件（挑战）

除了 `Parent/Children` 层级，游戏中还需要哪些关系？请设计：

- **Owner/Owned**：一个"拥有"另一个（比如角色和它的武器）
- **Target**：一个实体"瞄准"另一个（A 正在攻击 B）
- **Team**：多个实体属于同一阵营

用组件来表达这些关系。当被瞄准的目标实体被销毁时，持有 `Target` 引用的实体应该怎么处理？（提示：generation 检查。）

---

## 4. 扩展阅读

- **《Game Programming Patterns》 — 对象池模式**：与 Entity 槽位管理思想接近
- **Handle 模式**：`index + generation` 是一种经典的**句柄（Handle）设计**，广泛应用于图形 API（Vulkan 的 `VkBuffer`、OpenGL 的对象名）
- **EnTT `entt::entity`**：实际生产级实现，entity 同时编码了 index 和 version 到一个 `uint64_t` 中（32+32 或 20+12+32 位拆分）

---

## 常见陷阱

- **在 Entity 中存储指针**：`struct Entity { void* userData; }`——这破坏了 ECS 的核心前提。所有数据都应通过组件外部存储。
- **忽略 generation 检查**：直接拿 `entity.index` 去查表而不验证 `generation`。结果是"幽灵引用"——访问到被销毁后复用槽位的新实体。
- **`entity == INVALID_ENTITY` 检查不充分**：如果 generation 用于版本验证，那么单独比较 index 是不够的。定义清晰的 `Entity::invalid()` 方法或 `null` 实体常量。
- **在 System 中混用 Entity 和 `void*`**：不要把 Entity 强转成指针或对象引用。永远通过 World 提供的接口用 Entity 查询组件。
