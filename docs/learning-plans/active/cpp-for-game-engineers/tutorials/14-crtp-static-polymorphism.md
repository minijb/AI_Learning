---
title: "CRTP 与静态多态"
updated: 2026-06-05
---

# CRTP 与静态多态

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 模板基础与实例化模型（第 13 节）
> C++ 标准: C++98（CRTP 模式）、C++11（继承构造函数）、C++17（if constexpr）、C++20（Concepts 替代部分 CRTP）

---

## 1. 概念讲解

### 1.1 什么是 CRTP？

CRTP（Curiously Recurring Template Pattern，奇异递归模板模式）是一种 C++ 惯用法：**派生类将自己作为模板参数传递给基类**。

```cpp
// 核心形式
template <typename Derived>
class Base {
public:
    void interface() {
        // 通过 static_cast 调用派生类的方法
        static_cast<Derived*>(this)->implementation();
    }
};

class MyClass : public Base<MyClass> {
public:
    void implementation() {
        // 实际实现
    }
};
```

这个模式利用了两个关键事实：

1. **模板的延迟实例化**：`Base<Derived>` 在 `Derived` 的定义被看到后才实例化（此时 `Derived` 已经是完整类型）
2. **static_cast 的编译期安全**：`static_cast<Derived*>(this)` 在编译期验证继承关系，没有运行时开销

### 1.2 静态多态 vs 虚函数

CRTP 的核心价值是用编译期分发替代运行时虚函数调用：

```cpp
// ─── 虚函数版本（动态多态）───
struct IRenderable {
    virtual void render() const = 0;
    virtual ~IRenderable() = default;
};

struct MeshRenderer : IRenderable {
    void render() const override { /* 绘制网格 */ }
};

void render_all(const std::vector<IRenderable*>& objects) {
    for (auto* obj : objects) {
        obj->render();  // 虚函数调用 → vtable 查找 → 间接跳转
    }
}

// ─── CRTP 版本（静态多态）───
template <typename Derived>
class Renderable {
public:
    void render() const {
        static_cast<const Derived*>(this)->render_impl();
    }
};

class MeshRenderer : public Renderable<MeshRenderer> {
public:
    void render_impl() const { /* 绘制网格 */ }
};

// 使用（编译期多态 — 需要知道具体类型）
template <typename T>
void render_one(const Renderable<T>& obj) {
    obj.render();  // 编译期绑定 → 直接调用 → 可内联
}

// 调用
MeshRenderer mesh;
render_one(mesh);  // 编译器直接生成对 MeshRenderer::render_impl() 的调用
```

**性能对比**：

| 方面 | 虚函数 | CRTP |
|------|-------|------|
| 函数调用开销 | vtable 间接跳转（~2-5 ns） | 直接调用（0 ns，通常内联） |
| 内联优化 | 极少（编译器看不到具体类型） | 充分（编译器看到完整调用链） |
| 对象大小 | +8 字节（vptr） | 无额外开销 |
| 运行时多态 | ✓ 支持 | ✗ 不支持 |
| 二进制大小 | 1 份函数代码 | 每种派生类 1 份 |
| 调试体验 | 符号可见 | 模板展开复杂 |

在游戏引擎中，当你不需要运行时类型切换时（例如：渲染循环中所有对象类型在编译期已知），CRTP 可以消除虚函数调用的所有开销。

### 1.3 CRTP 调用链的编译过程

```cpp
template <typename Derived>
class Base {
public:
    void interface() {
        static_cast<Derived*>(this)->impl();  // ①
    }
};

class Derived : public Base<Derived> {
public:
    void impl() { /* ... */ }  // ②
};

Derived d;
d.interface();  // ③

// 编译器处理过程:
// 1. 解析 Derived → 看到继承 Base<Derived> → 触发 Base<Derived> 的隐式实例化
// 2. Base<Derived> 此时只"记住"了接口，impl() 的调用（①）被延迟到 interface() 实际被使用时
// 3. d.interface() → 实例化 Base<Derived>::interface()
//    → static_cast<Derived*>(this) 在编译期验证：Derived 确实继承自 Base<Derived>
//    → 调用 Derived::impl() → 直接跳转或内联
```

### 1.4 CRTP Mixin — 组合式功能叠加

Mixin 模式使用 CRTP 为派生类"混入"额外功能：

```cpp
// Mixin 1: 对象引用计数
template <typename Derived>
class ObjectCounter {
    static inline size_t s_count = 0;
public:
    ObjectCounter()   { ++s_count; }
    ~ObjectCounter()  { --s_count; }
    static size_t count() { return s_count; }
};

// Mixin 2: Clone 能力
template <typename Derived>
class Cloneable {
public:
    std::unique_ptr<Derived> clone() const {
        return std::make_unique<Derived>(
            static_cast<const Derived&>(*this)
        );
    }
};

// Mixin 3: 运算符重载（只需要派生类提供 == 即可生成 !=）
template <typename Derived>
class EqualityComparable {
    friend bool operator!=(const Derived& lhs, const Derived& rhs) {
        return !(lhs == rhs);
    }
    // > >= <= 也可以类似生成
};

// ─── 组合使用 ───
class Entity : public ObjectCounter<Entity>,
               public Cloneable<Entity>,
               public EqualityComparable<Entity>
{
    int m_id;
public:
    Entity(int id) : m_id(id) {}
    bool operator==(const Entity& other) const { return m_id == other.m_id; }
};

// Entity 自动获得:
// - count() 静态方法（跟踪所有实例数）
// - clone() 方法（深拷贝）
// - operator!= （自动从 operator== 生成）
```

### 1.5 Policy-Based Design（策略驱动设计）

Policy 类作为模板参数，允许在编译期组合行为：

```cpp
// 分配策略
struct MallocPolicy {
    static void* allocate(size_t n) { return std::malloc(n); }
    static void deallocate(void* p) { std::free(p); }
};

struct ArenaPolicy {
    static inline ArenaAllocator* arena = nullptr;
    static void* allocate(size_t n) { return arena->allocate(n); }
    static void deallocate(void*) {}  // Arena 不单独释放
};

// 线程安全策略
struct SingleThreaded {
    static void lock() {}
    static void unlock() {}
};

struct MultiThreaded {
    static inline std::mutex mtx;
    static void lock()   { mtx.lock(); }
    static void unlock() { mtx.unlock(); }
};

// ─── 策略驱动的容器 ───
template <typename T,
          template <typename> class AllocPolicy = MallocPolicy,
          typename ThreadPolicy = SingleThreaded>
class PolicyVector : private AllocPolicy<T>, private ThreadPolicy {
    T* m_data = nullptr;
    size_t m_size = 0;
    size_t m_cap = 0;

    using Alloc = AllocPolicy<T>;
    using Thread = ThreadPolicy;

public:
    void push_back(const T& val) {
        Thread::lock();
        if (m_size == m_cap) {
            size_t new_cap = m_cap ? m_cap * 2 : 4;
            T* new_data = static_cast<T*>(Alloc::allocate(new_cap * sizeof(T)));
            for (size_t i = 0; i < m_size; ++i) {
                ::new (new_data + i) T(m_data[i]);
                m_data[i].~T();
            }
            Alloc::deallocate(m_data);
            m_data = new_data;
            m_cap = new_cap;
        }
        ::new (m_data + m_size) T(val);
        ++m_size;
        Thread::unlock();
    }

    ~PolicyVector() {
        for (size_t i = 0; i < m_size; ++i) m_data[i].~T();
        Alloc::deallocate(m_data);
    }

    T& operator[](size_t i) { return m_data[i]; }
    size_t size() const { return m_size; }
};

// 用法 — 编译期选择策略，零运行时开销
using FrameVec = PolicyVector<Particle, MallocPolicy, SingleThreaded>;
using SharedVec = PolicyVector<Event, MallocPolicy, MultiThreaded>;
```

### 1.6 CRTP 的局限性

| 局限 | 说明 | 缓解方法 |
|------|------|---------|
| 不能运行时切换类型 | 必须在编译期知道所有类型 | 配合 `std::variant` + `std::visit` |
| 二进制膨胀 | 每种派生类生成独立代码 | 类型擦除基类、合理限制派生类数量 |
| 难以调试 | 模板展开后符号名极长 | 使用 `using` 别名、写清晰注释 |
| 不支持虚继承混合 | CRTP 和虚函数是正交的两种机制 | 可以用 `virtual` + CRTP 混合（少见） |

---

## 2. 代码示例

### 2.1 完整 CRTP 组件系统

```cpp
// crtp_component_system.cpp — 完整的静态多态组件系统
// 编译: g++ -std=c++20 -O2 crtp_component_system.cpp -o crtp_demo

#include <memory>
#include <vector>
#include <iostream>
#include <chrono>
#include <type_traits>
#include <functional>

// ============================================================
// 1. CRTP 基类 — 可渲染对象
// ============================================================
template <typename Derived>
class Renderable {
public:
    void render() const {
        static_cast<const Derived*>(this)->render_impl();
    }

    // 统一接口：获取包围盒
    void get_bounds(float& min_x, float& min_y, float& min_z,
                    float& max_x, float& max_y, float& max_z) const {
        static_cast<const Derived*>(this)->get_bounds_impl(
            min_x, min_y, min_z, max_x, max_y, max_z);
    }
};

// ============================================================
// 2. 具体组件 — 静态网格
// ============================================================
class StaticMesh : public Renderable<StaticMesh> {
    int m_vertex_count;
    int m_index_count;

public:
    StaticMesh(int vc, int ic) : m_vertex_count(vc), m_index_count(ic) {}

    void render_impl() const {
        // 实际 GPU 绘制调用（此处模拟）
        volatile int draw_call = m_vertex_count + m_index_count;
        (void)draw_call;
    }

    void get_bounds_impl(float& min_x, float& min_y, float& min_z,
                         float& max_x, float& max_y, float& max_z) const {
        min_x = -1.0f; min_y = -1.0f; min_z = -1.0f;
        max_x =  1.0f; max_y =  1.0f; max_z =  1.0f;
    }
};

// ============================================================
// 3. CRTP Mixin — Singleton
// ============================================================
template <typename Derived>
class Singleton {
public:
    static Derived& instance() {
        static Derived inst;
        return inst;
    }

protected:
    Singleton() = default;
    Singleton(const Singleton&) = delete;
    Singleton& operator=(const Singleton&) = delete;
};

// ============================================================
// 4. CRTP Mixin — DebugDraw
// ============================================================
template <typename Derived>
class DebugDrawable {
public:
    void draw_debug() const {
        std::cout << "── Debug: " << static_cast<const Derived*>(this)->debug_name()
                  << " ──\n";
        static_cast<const Derived*>(this)->draw_debug_impl();
    }
};

class PhysicsBody : public DebugDrawable<PhysicsBody> {
    float m_x, m_y, m_mass;
public:
    PhysicsBody(float x, float y, float m) : m_x(x), m_y(y), m_mass(m) {}

    const char* debug_name() const { return "PhysicsBody"; }

    void draw_debug_impl() const {
        std::cout << "  position: (" << m_x << ", " << m_y << ")\n";
        std::cout << "  mass: " << m_mass << "\n";
    }
};

// ============================================================
// 5. 运算符 Mixin — 提供 operator++ 的 CRTP 惯用法
// ============================================================
template <typename Derived>
class Incrementable {
public:
    Derived& operator++() {         // ++x
        auto& self = static_cast<Derived&>(*this);
        self.increment();
        return self;
    }

    Derived operator++(int) {       // x++
        Derived tmp = static_cast<Derived&>(*this);
        ++(*this);
        return tmp;
    }
};

class FrameCounter : public Incrementable<FrameCounter> {
    uint64_t m_frames = 0;
public:
    void increment() { ++m_frames; }
    uint64_t value() const { return m_frames; }
};

// ============================================================
// 6. 多个 CRTP 基类组合
// ============================================================
class GameEntity : public Renderable<GameEntity>,
                   public DebugDrawable<GameEntity>,
                   public Singleton<GameEntity>
{
    int m_id;
public:
    explicit GameEntity(int id) : m_id(id) {}

    void render_impl() const {
        std::cout << "  Rendering Entity #" << m_id << "\n";
    }

    void draw_debug_impl() const {
        std::cout << "  Entity ID: " << m_id << "\n";
    }

    const char* debug_name() const { return "GameEntity"; }
};

// ============================================================
// 7. 虚函数 vs CRTP 性能基准测试
// ============================================================

// 虚函数版本
struct IVirtual {
    virtual void update(float dt) = 0;
    virtual ~IVirtual() = default;
};

struct VirtualParticle : IVirtual {
    float x = 0, y = 0, vx = 1, vy = 0.5f;
    void update(float dt) override {
        x += vx * dt;
        y += vy * dt;
    }
};

// CRTP 版本
template <typename Derived>
class CRTPUpdatable {
public:
    void update(float dt) {
        static_cast<Derived*>(this)->update_impl(dt);
    }
};

class CRTPParticle : public CRTPUpdatable<CRTPParticle> {
    float x = 0, y = 0, vx = 1, vy = 0.5f;
public:
    void update_impl(float dt) {
        x += vx * dt;
        y += vy * dt;
    }
    float get_x() const { return x; }
};

// 基准测试
template <typename Func>
double benchmark(Func&& f, size_t iterations) {
    auto start = std::chrono::high_resolution_clock::now();
    f(iterations);
    auto end = std::chrono::high_resolution_clock::now();
    return std::chrono::duration<double, std::nano>(end - start).count() / iterations;
}

void run_particle_benchmark() {
    const size_t N = 10'000'000;

    // 虚函数
    std::vector<std::unique_ptr<IVirtual>> vparticles;
    for (int i = 0; i < 1000; ++i) {
        vparticles.push_back(std::make_unique<VirtualParticle>());
    }

    double vtime = benchmark([&](size_t n) {
        for (size_t i = 0; i < n; ++i) {
            for (auto& p : vparticles) {
                p->update(0.016f);  // 虚函数调用
            }
        }
    }, 1);

    std::cout << "虚函数版本:  " << vtime << " ns/update\n";

    // CRTP — 需要展开循环（无法放入统一容器）
    // 注意：这是 CRTP 的限制 — 必须逐个类型处理
    std::vector<CRTPParticle> cparticles(1000);
    double ctime = benchmark([&](size_t n) {
        for (size_t i = 0; i < n; ++i) {
            for (auto& p : cparticles) {
                p.update(0.016f);  // 编译期绑定 → 直接调用
            }
        }
    }, 1);

    std::cout << "CRTP 版本:    " << ctime << " ns/update\n";
    std::cout << "加速比:       " << vtime / ctime << "x\n";
}
```

### 2.2 Policy-Based Allocator（策略驱动分配器）

```cpp
// policy_allocator.cpp — 策略化的分配器

// 大小策略
struct FixedSize { static constexpr size_t value = 64; };
struct SmallSize  { static constexpr size_t value = 256; };
struct LargeSize  { static constexpr size_t value = 4096; };

// 增长策略
struct NoGrowth {
    static size_t grow(size_t current) { return current; }
};
struct DoubleGrowth {
    static size_t grow(size_t current) {
        return current == 0 ? 4 : current * 2;
    }
};

// 对齐策略
template <size_t A>
struct Aligned { static constexpr size_t alignment = A; };
using Align16 = Aligned<16>;
using Align64 = Aligned<64>;

// ─── 策略驱动的内存池 ───
template <typename T,
          typename SizePolicy = FixedSize,
          typename GrowthPolicy = DoubleGrowth,
          typename AlignPolicy = Align16>
class PolicyPool {
    static constexpr size_t BlockSize = SizePolicy::value;
    static constexpr size_t Alignment = AlignPolicy::alignment;

    struct Block {
        alignas(Alignment) char data[sizeof(T) * BlockSize];
        bool used[BlockSize] = {};
    };

    std::vector<Block*> m_blocks;

public:
    T* allocate() {
        for (auto* block : m_blocks) {
            for (size_t i = 0; i < BlockSize; ++i) {
                if (!block->used[i]) {
                    block->used[i] = true;
                    return reinterpret_cast<T*>(&block->data[i * sizeof(T)]);
                }
            }
        }
        // 需要新 Block
        auto* new_block = new Block();
        m_blocks.push_back(new_block);
        new_block->used[0] = true;
        return reinterpret_cast<T*>(&new_block->data[0]);
    }

    void deallocate(T* ptr) {
        for (auto* block : m_blocks) {
            if (ptr >= reinterpret_cast<T*>(block->data) &&
                ptr < reinterpret_cast<T*>(block->data + BlockSize)) {
                size_t idx = ptr - reinterpret_cast<T*>(block->data);
                block->used[idx] = false;
                ptr->~T();
                return;
            }
        }
    }

    ~PolicyPool() {
        for (auto* b : m_blocks) delete b;
    }
};
```

### 2.3 主演示

```cpp
int main() {
    std::cout << "========== CRTP 与静态多态 ==========\n\n";

    // 1. CRTP 组件渲染
    std::cout << "--- 组件渲染 ---\n";
    StaticMesh mesh(1024, 3072);
    mesh.render();
    std::cout << "StaticMesh 渲染完成\n\n";

    // 2. Debug Draw
    std::cout << "--- Debug Draw ---\n";
    PhysicsBody body(10.0f, 20.0f, 5.0f);
    body.draw_debug();
    std::cout << "\n";

    // 3. 运算符 Mixin
    std::cout << "--- 运算符 Mixin ---\n";
    FrameCounter fc;
    ++fc; ++fc; ++fc;
    std::cout << "Frames: " << fc.value() << "\n\n";

    // 4. 多 Mixin 组合
    std::cout << "--- 多 Mixin 组合 ---\n";
    auto& entity = GameEntity::instance();
    entity.render();
    entity.draw_debug();
    std::cout << "\n";

    // 5. Policy-Based Allocator
    std::cout << "--- Policy-Based Allocator ---\n";
    PolicyPool<int, LargeSize, DoubleGrowth, Align64> pool;
    int* a = pool.allocate();
    int* b = pool.allocate();
    *a = 42; *b = 100;
    std::cout << "Pool alloc: " << *a << ", " << *b << "\n";

    // 6. 性能基准
    std::cout << "\n--- 虚函数 vs CRTP 性能 ---\n";
    run_particle_benchmark();

    return 0;
}
```

---

## 3. 练习

### 练习 1（必做）：构建 CRTP 事件处理器系统

1. 定义 CRTP 基类 `EventHandler<Derived>`，提供 `handle(const Event&)` 接口，内部调用 `Derived::handle_impl`
2. 实现三种具体处理器：`MouseHandler`（处理鼠标事件）、`KeyboardHandler`（处理键盘事件）、`GamepadHandler`（处理手柄事件）
3. 每种处理器定义自己的 `Event` 结构（如 `MouseEvent{x, y, buttons}`）
4. 实现模板函数 `dispatch(const Event&, EventHandler<T>&)` 用于类型安全的事件分发
5. 编写测试：创建所有处理器并分发相应事件，验证编译期类型检查阻止了错误的事件类型传递

### 练习 2（必做）：对比虚函数与 CRTP 的粒子更新性能

1. 实现两个版本的粒子系统：`VirtualParticle`（使用虚函数 `update`）和 `CRTPParticle`（使用 CRTP `CRTPUpdatable<Particle>::update`）
2. 对 100~10,000 个粒子分别测量每帧的更新耗时
3. 改变粒子的复杂度（只更新位置 vs 更新位置+速度+生命周期+颜色）
4. 绘制性能对比图表（或输出表格），分析虚函数开销占总更新时间的比例
5. 解释为什么粒子的 `update` 越简单，虚函数相对开销越大

### 练习 3（选做·挑战）：实现 Singleton + Cloneable + Serializable CRTP Mixin 系统

1. 实现 `Singleton<Derived>` — 经典的 Meyer's Singleton
2. 实现 `Cloneable<Derived>` — 通过拷贝构造实现 `clone()` 返回 `unique_ptr<Derived>`
3. 实现 `Serializable<Derived>` — 要求 Derived 提供 `serialize(Archive&)` 方法，Mixin 自动提供 `save_to_file(const char* path)` 和 `load_from_file(const char* path)`
4. 创建一个使用所有三个 Mixin 的 `ConfigManager` 类
5. 验证：Singleton 保证全局唯一、Cloneable 支持深拷贝、Serializable 支持文件读写
6. 分析三个 Mixin 的内存开销（应为零——EBO/Empty Base Optimization）

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> > // crtp_event_handler.cpp — CRTP 事件处理器系统
> > #include <iostream>
> > #include <string>
> > 
> > // ============================================================
> > // 事件类型
> > // ============================================================
> > struct MouseEvent    { int x, y; int buttons; };
> > struct KeyboardEvent { int key; bool pressed; };
> > struct GamepadEvent  { int button; float axis_value; };
> > 
> > // ============================================================
> > // CRTP 基类: EventHandler<Derived>
> > // ============================================================
> > template <typename Derived>
> > class EventHandler {
> > public:
> >     template <typename Event>
> >     void handle(const Event& e) {
> >         static_cast<Derived*>(this)->handle_impl(e);
> >     }
> > };
> > 
> > // ============================================================
> > // 具体处理器
> > // ============================================================
> > class MouseHandler : public EventHandler<MouseHandler> {
> > public:
> >     void handle_impl(const MouseEvent& e) {
> >         std::cout << "  [MouseHandler] pos=(" << e.x << "," << e.y
> >                   << ") buttons=" << e.buttons << "\n";
> >     }
> >     // handle_impl(const KeyboardEvent&) 不存在 → 编译期阻止错误类型
> >     void handle_impl(const GamepadEvent&) {
> >         std::cout << "  [MouseHandler] 不处理 GamepadEvent\n";
> >     }
> > };
> > 
> > class KeyboardHandler : public EventHandler<KeyboardHandler> {
> > public:
> >     void handle_impl(const KeyboardEvent& e) {
> >         std::cout << "  [KeyboardHandler] key=" << e.key
> >                   << " pressed=" << (e.pressed ? "true" : "false") << "\n";
> >     }
> >     void handle_impl(const MouseEvent&) {
> >         std::cout << "  [KeyboardHandler] 不处理 MouseEvent\n";
> >     }
> >     void handle_impl(const GamepadEvent&) {
> >         std::cout << "  [KeyboardHandler] 不处理 GamepadEvent\n";
> >     }
> > };
> > 
> > class GamepadHandler : public EventHandler<GamepadHandler> {
> > public:
> >     void handle_impl(const GamepadEvent& e) {
> >         std::cout << "  [GamepadHandler] button=" << e.button
> >                   << " axis=" << e.axis_value << "\n";
> >     }
> >     void handle_impl(const MouseEvent&) {
> >         std::cout << "  [GamepadHandler] 不处理 MouseEvent\n";
> >     }
> >     void handle_impl(const KeyboardEvent&) {
> >         std::cout << "  [GamepadHandler] 不处理 KeyboardEvent\n";
> >     }
> > };
> > 
> > // ============================================================
> > // 类型安全的事件分发
> > // ============================================================
> > template <typename Event, typename Handler>
> > void dispatch(const Event& e, EventHandler<Handler>& h) {
> >     h.handle(e);  // 编译期：如果 Handler 没有 handle_impl(Event) → 编译错误
> > }
> > 
> > // ============================================================
> > // 测试
> > // ============================================================
> > int main() {
> >     MouseHandler    mouse;
> >     KeyboardHandler keyboard;
> >     GamepadHandler  gamepad;
> > 
> >     std::cout << "=== 正确分发 ===\n";
> >     MouseEvent    me{100, 200, 3};
> >     KeyboardEvent ke{65, true};   // key 'A'
> >     GamepadEvent  ge{0, 0.75f};
> > 
> >     dispatch(me, mouse);
> >     dispatch(ke, keyboard);
> >     dispatch(ge, gamepad);
> > 
> >     std::cout << "\n=== 交叉分发（验证编译期类型检查）===\n";
> >     dispatch(ge, mouse);     // 允许（MouseHandler 有 handle_impl(GamepadEvent)）
> >     dispatch(me, keyboard);  // 允许（KeyboardHandler 有 handle_impl(MouseEvent)）
> > 
> >     // 下面这行如果取消注释会编译失败（编译期类型安全）：
> >     // dispatch(ge, keyboard);
> >     // 错误: GamepadHandler::handle_impl(KeyboardEvent) is private / not defined
> >     // 这正是 CRTP + 模板 dispatch 编译期阻止错误事件类型传递的效果
> > 
> >     std::cout << "\n编译期类型检查: 阻止了错误事件类型传递 ✓\n";
> >     return 0;
> > }
> > ```

> [!tip]- 练习 2 参考答案
> ```cpp
> > // virtual_vs_crtp_benchmark.cpp — 虚函数 vs CRTP 粒子性能对比
> > #include <iostream>
> > #include <vector>
> > #include <memory>
> > #include <chrono>
> > #include <iomanip>
> > #include <cmath>
> > 
> > // ============================================================
> > // 虚函数版本
> > // ============================================================
> > struct IVirtualParticle {
> >     virtual void update_simple(float dt) = 0;
> >     virtual void update_complex(float dt) = 0;
> >     virtual ~IVirtualParticle() = default;
> > };
> > 
> > struct VirtualParticle : IVirtualParticle {
> >     float x=0, y=0, z=0, vx=1, vy=0.5f, vz=0.2f;
> >     float lifetime=10.0f, color[3]={1,0,0};
> > 
> >     void update_simple(float dt) override {
> >         x += vx * dt;
> >         y += vy * dt;
> >     }
> >     void update_complex(float dt) override {
> >         x += vx * dt;
> >         y += vy * dt;
> >         z += vz * dt;
> >         lifetime -= dt;
> >         color[0] = lifetime / 10.0f;  // fade out
> >         color[1] = 1.0f - lifetime / 10.0f;
> >     }
> > };
> > 
> > // ============================================================
> > // CRTP 版本
> > // ============================================================
> > template <typename Derived>
> > class CRTPUpdatable {
> > public:
> >     void update_simple(float dt) {
> >         static_cast<Derived*>(this)->update_simple_impl(dt);
> >     }
> >     void update_complex(float dt) {
> >         static_cast<Derived*>(this)->update_complex_impl(dt);
> >     }
> > };
> > 
> > struct CRTPParticle : CRTPUpdatable<CRTPParticle> {
> >     float x=0, y=0, z=0, vx=1, vy=0.5f, vz=0.2f;
> >     float lifetime=10.0f, color[3]={1,0,0};
> > 
> >     void update_simple_impl(float dt) {
> >         x += vx * dt;
> >         y += vy * dt;
> >     }
> >     void update_complex_impl(float dt) {
> >         x += vx * dt;
> >         y += vy * dt;
> >         z += vz * dt;
> >         lifetime -= dt;
> >         color[0] = lifetime / 10.0f;
> >         color[1] = 1.0f - lifetime / 10.0f;
> >     }
> > };
> > 
> > // ============================================================
> > // 基准测试工具
> > // ============================================================
> > using Clock = std::chrono::high_resolution_clock;
> > 
> > template <typename InitFn, typename UpdateFn>
> > double measure(InitFn init, UpdateFn update, size_t particle_count, size_t iterations) {
> >     init();
> >     auto start = Clock::now();
> >     for (size_t i = 0; i < iterations; ++i) {
> >         update();
> >     }
> >     auto end = Clock::now();
> >     auto total_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
> >     return static_cast<double>(total_ns) / iterations;  // ns/iteration
> > }
> > 
> > int main() {
> >     const size_t particle_counts[] = {100, 1000, 10000};
> >     const size_t iterations = 1000;
> > 
> >     std::cout << std::fixed << std::setprecision(2);
> >     std::cout << "==============================================================\n";
> >     std::cout << "  虚函数 vs CRTP 粒子更新性能对比\n";
> >     std::cout << "==============================================================\n\n";
> > 
> >     for (size_t N : particle_counts) {
> >         std::cout << "--- " << N << " 粒子 ---\n";
> > 
> >         // ─── 简单更新（仅位置）───
> >         std::cout << "  [简单更新：仅位置]\n";
> > 
> >         // 虚函数
> >         std::vector<std::unique_ptr<IVirtualParticle>> vparts(N);
> >         auto v_init = [&]() {
> >             for (size_t i = 0; i < N; ++i) vparts[i] = std::make_unique<VirtualParticle>();
> >         };
> >         auto v_update = [&]() {
> >             for (auto& p : vparts) p->update_simple(0.016f);
> >         };
> >         double v_simple = measure(v_init, v_update, N, iterations);
> > 
> >         // CRTP
> >         std::vector<CRTPParticle> cparts(N);
> >         auto c_update = [&]() {
> >             for (auto& p : cparts) p.update_simple(0.016f);
> >         };
> >         double c_simple = measure([](){}, c_update, N, iterations);
> > 
> >         std::cout << "    虚函数: " << std::setw(8) << v_simple << " ns/iter\n";
> >         std::cout << "    CRTP:   " << std::setw(8) << c_simple << " ns/iter\n";
> >         std::cout << "    加速比: " << std::setw(8) << v_simple / c_simple << "x\n";
> > 
> >         // ─── 复杂更新（位置+速度+生命周期+颜色）───
> >         std::cout << "  [复杂更新：位置+速度+生命周期+颜色]\n";
> > 
> >         auto v_complex_init = [&]() {
> >             for (size_t i = 0; i < N; ++i) vparts[i] = std::make_unique<VirtualParticle>();
> >         };
> >         auto v_complex_update = [&]() {
> >             for (auto& p : vparts) p->update_complex(0.016f);
> >         };
> >         double v_complex = measure(v_complex_init, v_complex_update, N, iterations);
> > 
> >         auto c_complex_update = [&]() {
> >             for (auto& p : cparts) p.update_complex(0.016f);
> >         };
> >         double c_complex = measure([](){}, c_complex_update, N, iterations);
> > 
> >         std::cout << "    虚函数: " << std::setw(8) << v_complex << " ns/iter\n";
> >         std::cout << "    CRTP:   " << std::setw(8) << c_complex << " ns/iter\n";
> >         std::cout << "    加速比: " << std::setw(8) << v_complex / c_complex << "x\n";
> > 
> >         // 虚函数开销占比
> >         double simple_overhead = (v_simple - c_simple) / v_simple * 100;
> >         double complex_overhead = (v_complex - c_complex) / v_complex * 100;
> >         std::cout << "    虚函数开销占比: simple=" << simple_overhead
> >                   << "%, complex=" << complex_overhead << "%\n\n";
> >     }
> > 
> >     // ─── 分析 ───
> >     std::cout << "==============================================================\n";
> >     std::cout << "  分析\n";
> >     std::cout << "==============================================================\n";
> >     std::cout << "1. 简单更新时虚函数开销占比更大:\n";
> >     std::cout << "   - 因为虚函数调用本身有固定开销（vtable 查找 + 间接跳转）\n";
> >     std::cout << "   - 当方法体很简单（仅几条指令），虚函数开销占比高\n";
> >     std::cout << "   - 当方法体复杂（更多计算），虚函数开销被摊薄\n\n";
> > 
> >     std::cout << "2. CRTP 优势:\n";
> >     std::cout << "   - 编译期绑定 → 直接调用（无 vtable 间接）\n";
> >     std::cout << "   - 编译器可以内联 CRTP::update → 消除函数调用\n";
> >     std::cout << "   - 但代价是代码膨胀（每个 Derived 生成一份代码）\n\n";
> > 
> >     std::cout << "3. 引擎建议:\n";
> >     std::cout << "   - 粒子/实体等高频更新的小对象 → CRTP\n";
> >     std::cout << "   - 复杂的游戏对象/需要多态容器 → 虚函数\n";
> >     std::cout << "   - 关键路径避免虚函数，非关键路径允许虚函数\n";
> > 
> >     return 0;
> > }
> > ```

> [!tip]- 练习 3 参考答案（选做·挑战）
> ```cpp
> > // crtp_mixin_system.cpp — Singleton + Cloneable + Serializable CRTP Mixin
> > #include <memory>
> > #include <fstream>
> > #include <string>
> > #include <cstring>
> > #include <iostream>
> > #include <type_traits>
> > 
> > // ============================================================
> > // 1. Singleton<Derived> — Meyer's Singleton
> > // ============================================================
> > template <typename Derived>
> > class Singleton {
> > public:
> >     static Derived& instance() {
> >         static Derived inst;
> >         return inst;
> >     }
> > protected:
> >     Singleton() = default;
> >     Singleton(const Singleton&) = delete;
> >     Singleton& operator=(const Singleton&) = delete;
> > };
> > 
> > // ============================================================
> > // 2. Cloneable<Derived> — 深拷贝
> > // ============================================================
> > template <typename Derived>
> > class Cloneable {
> > public:
> >     std::unique_ptr<Derived> clone() const {
> >         return std::make_unique<Derived>(static_cast<const Derived&>(*this));
> >     }
> > };
> > 
> > // ============================================================
> > // 3. Serializable<Derived> — 文件读写
> > // ============================================================
> > struct Archive {
> >     std::string data;
> > };
> > 
> > template <typename Derived>
> > class Serializable {
> > public:
> >     bool save_to_file(const char* path) const {
> >         Archive ar;
> >         static_cast<const Derived*>(this)->serialize(ar);
> > 
> >         std::ofstream out(path, std::ios::binary);
> >         if (!out) return false;
> >         out.write(ar.data.c_str(), ar.data.size());
> >         return out.good();
> >     }
> > 
> >     bool load_from_file(const char* path) {
> >         std::ifstream in(path, std::ios::binary);
> >         if (!in) return false;
> > 
> >         // 读取文件到 string
> >         std::string content((std::istreambuf_iterator<char>(in)),
> >                              std::istreambuf_iterator<char>());
> > 
> >         Archive ar;
> >         ar.data = std::move(content);
> >         static_cast<Derived*>(this)->deserialize(ar);
> >         return true;
> >     }
> > };
> > 
> > // ============================================================
> > // 4. ConfigManager — 使用三个 Mixin
> > // ============================================================
> > class ConfigManager
> >     : public Singleton<ConfigManager>
> >     , public Cloneable<ConfigManager>
> >     , public Serializable<ConfigManager>
> > {
> > public:
> >     int    volume   = 75;
> >     float  master_fx = 0.8f;
> >     bool   vsync    = true;
> >     int    resolution_w = 1920;
> >     int    resolution_h = 1080;
> > 
> >     // Serializable 要求: serialize + deserialize
> >     void serialize(Archive& ar) const {
> >         ar.data += "volume="  + std::to_string(volume)  + "\n";
> >         ar.data += "master_fx=" + std::to_string(master_fx) + "\n";
> >         ar.data += "vsync="   + std::to_string(vsync)   + "\n";
> >         ar.data += "res=" + std::to_string(resolution_w)
> >                   + "x" + std::to_string(resolution_h) + "\n";
> >     }
> > 
> >     void deserialize(const Archive& ar) {
> >         // 简化: 解析 "key=value\n" 格式
> >         const auto& d = ar.data;
> >         auto pos = d.find("volume=");
> >         if (pos != std::string::npos)
> >             volume = std::stoi(d.substr(pos + 7));
> >         pos = d.find("master_fx=");
> >         if (pos != std::string::npos)
> >             master_fx = std::stof(d.substr(pos + 10));
> >         pos = d.find("vsync=");
> >         if (pos != std::string::npos)
> >             vsync = (d[pos+6] == '1');
> >     }
> > 
> >     void print() const {
> >         std::cout << "ConfigManager {\n"
> >                   << "  volume:    " << volume << "\n"
> >                   << "  master_fx: " << master_fx << "\n"
> >                   << "  vsync:     " << (vsync ? "true" : "false") << "\n"
> >                   << "  res:       " << resolution_w << "x" << resolution_h << "\n"
> >                   << "}\n";
> >     }
> > };
> > 
> > // ============================================================
> > // 测试
> > // ============================================================
> > int main() {
> >     std::cout << "=== CRTP Mixin 系统验证 ===\n\n";
> > 
> >     // ─── 1. Singleton ───
> >     std::cout << "--- Singleton ---\n";
> >     auto& cfg1 = ConfigManager::instance();
> >     auto& cfg2 = ConfigManager::instance();
> >     std::cout << "cfg1 == cfg2: " << (&cfg1 == &cfg2 ? "true ✓" : "false ✗") << "\n";
> >     std::cout << "Singleton 保证全局唯一\n\n";
> > 
> >     // ─── 2. Cloneable ───
> >     std::cout << "--- Cloneable ---\n";
> >     auto& original = ConfigManager::instance();
> >     original.volume = 80;
> >     original.vsync  = false;
> >     auto cloned = original.clone();
> >     std::cout << "original:\n"; original.print();
> >     std::cout << "cloned:\n";   cloned->print();
> >     std::cout << "Cloneable 支持深拷贝 ✓\n\n";
> > 
> >     // ─── 3. Serializable ───
> >     std::cout << "--- Serializable ---\n";
> >     const char* path = "config_save.txt";
> >     bool saved = original.save_to_file(path);
> >     std::cout << "Saved: " << (saved ? "true ✓" : "false ✗") << "\n";
> > 
> >     // 修改原始配置
> >     original.volume = 50;
> >     original.master_fx = 0.5f;
> >     std::cout << "Modified config:\n"; original.print();
> > 
> >     // 从文件恢复
> >     bool loaded = original.load_from_file(path);
> >     std::cout << "Loaded: " << (loaded ? "true ✓" : "false ✗") << "\n";
> >     std::cout << "Restored config:\n"; original.print();
> > 
> >     // ─── 4. EBO 内存分析 ───
> >     std::cout << "\n--- Empty Base Optimization 分析 ---\n";
> >     std::cout << "sizeof(Singleton<ConfigManager>)    = "
> >               << sizeof(Singleton<ConfigManager>) << "\n";
> >     std::cout << "sizeof(Cloneable<ConfigManager>)    = "
> >               << sizeof(Cloneable<ConfigManager>) << "\n";
> >     std::cout << "sizeof(Serializable<ConfigManager>) = "
> >               << sizeof(Serializable<ConfigManager>) << "\n";
> >     std::cout << "sizeof(ConfigManager) = "
> >               << sizeof(ConfigManager) << "\n";
> >     std::cout << "\n三个 Mixin 类都是空基类（无成员变量）\n";
> >     std::cout << "EBO 保证继承时不增加 Derived 的大小\n";
> >     if (sizeof(ConfigManager) == sizeof(int)*3 + sizeof(float) + sizeof(bool) + 4 /*padding*/) {
> >         std::cout << "内存开销为零 ✓\n";
> >     }
> > 
> >     // 清理测试文件
> >     std::remove(path);
> > 
> >     return 0;
> > }
> > ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **CRTP 维基百科**：[Curiously Recurring Template Pattern](https://en.wikipedia.org/wiki/Curiously_recurring_template_pattern)
- **Mixin 模式**：C++ 中的 Mixin-based Programming（Smaragdakis, Batory）
- **Policy-Based Design**：Andrei Alexandrescu 的 *Modern C++ Design* 是策略驱动设计的开创性著作
- **std::enable_shared_from_this**：标准库自带的 CRTP 示例
- **Unreal Engine**：`TIsValidObjectPtr<T>` 等大量使用 CRTP 进行编译期类型检查
- **本计划关联**：第 28 节 "虚函数替代方案与类型擦除" 将进一步探讨 CRTP 的局限和弥补方案

---

## 常见陷阱

### 陷阱 1：基类构造函数中调用 Derived 方法

```cpp
template <typename Derived>
class Base {
public:
    Base() {
        // ❌ 未定义行为！Derived 尚未构造完毕
        static_cast<Derived*>(this)->init();
    }
};

class MyClass : public Base<MyClass> {
public:
    int m_value = 42;  // 在 Base 构造函数中，m_value 还是未初始化状态！
    void init() { std::cout << m_value; }  // 打印未定义值
};

// ✅ 正确 — 使用两阶段初始化（或工厂函数）
MyClass obj;
obj.init();  // 在完整构造后调用
```

### 陷阱 2：错误继承导致未定义行为

```cpp
template <typename Derived>
class Base {
public:
    void do_work() {
        static_cast<Derived*>(this)->work_impl();
    }
};

// ❌ 错误 — Foo 没有继承自 Base<Foo>
class Foo {
public:
    void work_impl() { /* ... */ }
};

// ❌ 如果这样做：
// Foo f;
// static_cast<Base<Foo>*>(&f)->do_work();  // 完全不相关的类型！

// ✅ 正确 — 必须确保继承链
class Bar : public Base<Bar> {
public:
    void work_impl() { /* ... */ }
};

// 额外的编译期防护（C++20 Concepts）：
template <typename Derived>
concept CRTPDerived = std::is_base_of_v<Base<Derived>, Derived>;

template <CRTPDerived D>
void safe_call(Base<D>& b) { b.do_work(); }
```

### 陷阱 3：同一类型被多个 Mixin 基类继承时的方法名冲突

```cpp
template <typename D> class MixinA { public: void init() { /* A */ } };
template <typename D> class MixinB { public: void init() { /* B */ } };

class MyClass : public MixinA<MyClass>, public MixinB<MyClass> {};

MyClass obj;
// obj.init();  // ❌ 歧义 — 哪个 init？

// ✅ 解决方法：显式限定或使用 using 声明
obj.MixinA<MyClass>::init();
// 或在 MyClass 中添加: using MixinA<MyClass>::init;
```

### 陷阱 4：滥用 CRTP 导致不可维护的编译错误

CRTP 的错误消息通常极长且难以阅读。当派生类忘记实现基类要求的方法时：

```
error: 'class MyDerived' has no member named 'required_method'
  ... 50 行模板实例化回溯 ...

// ✅ 缓解 — 使用 C++20 Concepts 提前检查
template <typename Derived>
concept HasRequiredMethod = requires(Derived d) {
    { d.required_method() } -> std::same_as<void>;
};

template <HasRequiredMethod Derived>
class Base { /* ... */ };
// 错误消息变为: "constraint 'HasRequiredMethod<MyDerived>' not satisfied"
```
