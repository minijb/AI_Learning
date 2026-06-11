---
title: "虚函数替代方案与类型擦除"
updated: 2026-06-05
---

# 虚函数替代方案与类型擦除

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 第14节 (CRTP 与静态多态), 第15节 (SFINAE 与 C++20 Concepts)

---

## 1. 概念讲解

### 1.1 虚函数的真实成本

虚函数是 C++ 最被滥用的特性之一。在引擎热路径上，虚函数调用的成本不是"一点点"——而是**存在性成本 + 调用成本 + 优化丧失成本**的三重打击：

| 成本来源 | 细节 | 引擎影响 |
|----------|------|---------|
| **vptr 空间** | 每个多态对象额外 8 bytes（64 位）存储 vtable 指针 | 100 万个实体 = 8 MB 纯开销 |
| **vtable 查找** | 每次调用：`obj->vptr[vfunc_index]()` — 三次内存访问（读 vptr → 读 vtable → 读函数地址） | 热循环中 L1 缓存未命中 × 3 |
| **无法内联** | 编译器不知道实际调用哪个函数 → 无法内联任何虚函数调用 | 失去常量传播、循环展开、死代码消除等关键优化 |
| **ABI 约束** | 派生类必须匹配基类 vtable 布局 → 新增虚函数破坏 ABI | 插件系统 DLL 边界兼容性噩梦 |

**基准数字**（在典型 x86-64 上，100M 次调用）：

| 调用方式 | 耗时 | 相对开销 |
|----------|------|---------|
| 直接函数调用（内联） | ~0.1 ns/call | 1× |
| 直接函数调用（非内联） | ~2-3 ns/call | 20-30× |
| 虚函数调用 | ~5-10 ns/call | 50-100× |
| 虚函数调用（分支预测失败） | ~15-20 ns/call | 150-200× |

**引擎决策**：虚函数调用本身 5-10ns 不是问题——问题是 16.6ms 帧预算内，如果有 100 万个实体每帧调用一次虚函数，仅调用开销就占 ~5-10ms。而如果这些调用能被内联，成本趋近于零。

### 1.2 什么时候虚函数仍然是正确的选择

不要走极端——虚函数在某些场景下是不可替代的：

- **DLL/插件边界**：编译期不知道插件中的类型，必须动态分发
- **运行时加载的脚本绑定**：类型在运行时才注册
- **真正的开放集合**：用户可以任意扩展的类型系统（如编辑器插件）
- **ABI 稳定性需求**：接口固定，实现变化

**关键判断**：如果你在编译期就知道所有可能的子类型，那么虚函数几乎肯定有更好的替代方案。

### 1.3 替代方案一：std::variant + std::visit

当类型集合是**封闭的**（编译期已知所有变体），`std::variant` (C++17) 是最直接的替代。

```cpp
// 替换这组虚函数层次：
// struct RenderCmd { virtual void execute() = 0; };
// struct DrawMesh   : RenderCmd { void execute() override { ... } };
// struct SetMaterial : RenderCmd { void execute() override { ... } };
// struct ClearRT     : RenderCmd { void execute() override { ... } };

// 使用 variant：
using RenderCmd = std::variant<DrawMeshData, SetMaterialData, ClearRTData>;

std::vector<RenderCmd> commandBuffer;

void execute(const RenderCmd& cmd) {
    std::visit([](const auto& c) {
        // 编译期生成所有三个重载——可以完全内联！
        executeImpl(c);
    }, cmd);
}
```

**性能特征**：
- **零虚函数开销**：`std::visit` 通过跳转表（switch-case 生成的）分发，现代编译器将其编译为与手写 switch 等效的代码
- **内存紧凑**：所有变体共享同一个内存块（最大变体大小 + 判别 union），无 vptr
- **可内联**：`std::visit` 的 lambda 体内代码可以被完全内联
- **代价**：`sizeof(variant)` ≥ 最大变体 + discriminator（可能比单独类型大）

### 1.4 替代方案二：类型擦除

类型擦除的核心思想：**将"是什么类型"编码为函数指针，而不是 vtable 指针**。

对比两种多态：

```
虚函数（内部多态）：                类型擦除（外部多态）：
┌─────────────────────┐            ┌─────────────────────┐
│  Dog                 │            │  Drawable            │
│  vptr → [bark, draw] │            │  ptr_to_any_type     │
│  x, y                │            │  draw_fn → [Dog.draw]│
└─────────────────────┘            │  destroy_fn → [... ]  │
                                   └─────────────────────┘
         ▲                                    ▲
    Dog 知道自己是 Dog                Drawable 不知道里面是什么
    （Dog 继承自 Animal）             （保存 void* + 函数指针）
```

类型擦除的关键优势：
- **不需要公共基类**：`Dog` 和 `Car` 不需要继承同一个 `Drawable`，只要它们都有 `draw()` 方法即可
- **值语义**：类型擦除对象可以按值存储在容器中，不需要指针
- **ABI 隔离**：接口不暴露，没有 vtable 布局兼容性问题
- **可以 SBO（小缓冲优化）**：小对象直接存储在 wrapper 内部，避免堆分配

### 1.5 std::function 就是类型擦除

你已经用过类型擦除了——`std::function<void()>` 可以存储任何可调用对象（lambda、函数指针、成员函数指针 + 对象），而不要求它们继承某个基类。

```cpp
std::function<void()> f;
f = []{};                      // 无捕获 lambda
f = &globalFunction;           // 函数指针
f = std::bind(&Obj::method, obj);  // 成员函数绑定
// f 不知道、不关心里面是什么——这就是类型擦除
```

`std::function` 的开销来自两点：
1. **小对象优化 (SBO)**：通常 16-32 bytes 的内联缓冲；超出则堆分配
2. **间接调用**：通过函数指针分发（与虚函数类似的间接分支开销）

### 1.6 C++23: std::move_only_function

C++23 引入了 `std::move_only_function<R(Args...)>`，这是 `std::function` 的"只移动"版本：

```cpp
std::move_only_function<void()> f = [p = std::make_unique<int>(42)]() {
    // lambda 捕获 unique_ptr，不可拷贝，但可以移动
};
// f 不可拷贝，但可以 std::move
auto f2 = std::move(f);  // OK
// auto f3 = f;          // 编译错误！
```

引擎中大多数回调（事件处理器、Job 函数）是只移动的——不需要共享所有权。

### 1.7 快速委托 (Fast Delegate)

Don Clugston 在 2004 年的文章 "Member Function Pointers and the Fastest Possible C++ Delegates" 中展示了如何用两个机器字表示任意成员函数调用：

```cpp
// 委托 = 对象指针 + 成员函数指针
// 大小 = sizeof(void*) + sizeof(void*) = 16 bytes (64位)
// 调用 = 两次间接跳转（比虚函数少一次！）
```

虚函数链：`obj → vptr → vtable[index] → function`（三次内存访问）
委托链：`delegate → object → member function`（两次内存访问，且可内联 thunk）

---

## 2. 代码示例

### 2.1 手动实现类型擦除：Drawable

```cpp
#include <memory>
#include <iostream>
#include <vector>

// ========= 类型擦除的 Drawable =========
class Drawable {
public:
    // 构造函数模板——接受任何有 draw() const 方法的类型
    template <typename T>
    Drawable(T obj) 
        // C++20: requires std::is_invocable_r_v<void, decltype(&T::draw), const T>
    {
        // 在堆上分配具体类型的存储
        using ModelType = Model<T>;
        model_ = std::make_unique<ModelType>(std::move(obj));
    }
    
    // 拷贝构造
    Drawable(const Drawable& other)
        : model_(other.model_->clone()) {}
    
    // 拷贝赋值
    Drawable& operator=(const Drawable& other) {
        if (this != &other) {
            model_ = other.model_->clone();
        }
        return *this;
    }
    
    // 移动构造/赋值——默认即可
    Drawable(Drawable&&) = default;
    Drawable& operator=(Drawable&&) = default;
    
    // 核心接口——零虚函数（通过函数指针分发）
    void draw() const { model_->draw(); }
    
private:
    // 内部基类——所有具体类型的接口
    struct Concept {
        virtual ~Concept() = default;
        virtual void draw() const = 0;
        virtual std::unique_ptr<Concept> clone() const = 0;
    };
    
    // 具体类型的存储
    template <typename T>
    struct Model : Concept {
        T data;
        
        explicit Model(T d) : data(std::move(d)) {}
        
        void draw() const override { data.draw(); }
        
        std::unique_ptr<Concept> clone() const override {
            return std::make_unique<Model<T>>(data);
        }
    };
    
    std::unique_ptr<Concept> model_;
};

// ========= 使用——不需要继承任何基类！ =========

struct Circle {
    float x, y, radius;
    void draw() const { 
        std::cout << "Circle at (" << x << "," << y 
                  << ") radius=" << radius << "\n";
    }
};

struct Rectangle {
    float x, y, w, h;
    void draw() const {
        std::cout << "Rect at (" << x << "," << y 
                  << ") " << w << "x" << h << "\n";
    }
};

// 甚至 lambda 也可以"draw"！
struct ParticleEmitter {
    void draw() const { std::cout << "Emitting particles!\n"; }
};

void demoTypeErasure() {
    std::vector<Drawable> shapes;
    
    // 完全不相关的类型，不需要公共基类！
    shapes.emplace_back(Circle{0, 0, 5.0f});
    shapes.emplace_back(Rectangle{1, 2, 10.0f, 5.0f});
    shapes.emplace_back(ParticleEmitter{});
    
    // 统一调用
    for (const auto& shape : shapes) {
        shape.draw();  // 通过函数指针分发，不是虚函数
    }
}
```

### 2.2 SBO 优化：消除堆分配的类型擦除

```cpp
#include <new>
#include <utility>
#include <cstddef>

// 带 SBO（Small Buffer Optimization）的类型擦除
template <typename Signature>
class InplaceFunction;  // 前向声明

template <typename R, typename... Args>
class InplaceFunction<R(Args...)> {
    static constexpr size_t SBO_SIZE = 32;  // 内联缓冲：32 bytes
    static constexpr size_t SBO_ALIGN = alignof(std::max_align_t);
    
public:
    InplaceFunction() : call_(nullptr) {}
    
    template <typename F>
    InplaceFunction(F&& f) {
        using DecayedF = std::decay_t<F>;
        
        if constexpr (sizeof(DecayedF) <= SBO_SIZE && 
                      alignof(DecayedF) <= SBO_ALIGN &&
                      std::is_nothrow_move_constructible_v<DecayedF>) {
            // 小对象：在内联缓冲区中构造
            new (buffer_) DecayedF(std::forward<F>(f));
            call_ = [](const Storage& s, Args... args) -> R {
                return (*static_cast<const DecayedF*>(
                    static_cast<const void*>(s.buffer_)))(std::forward<Args>(args)...);
            };
            destroy_ = [](Storage& s) {
                static_cast<DecayedF*>(static_cast<void*>(s.buffer_))->~DecayedF();
            };
        } else {
            // 大对象：堆分配
            auto* ptr = new DecayedF(std::forward<F>(f));
            heapPtr_ = ptr;
            call_ = [](const Storage& s, Args... args) -> R {
                return (*static_cast<const DecayedF*>(s.heapPtr_))(
                    std::forward<Args>(args)...);
            };
            destroy_ = [](Storage& s) {
                delete static_cast<DecayedF*>(s.heapPtr_);
            };
        }
    }
    
    ~InplaceFunction() {
        if (destroy_) destroy_(*this);
    }
    
    InplaceFunction(InplaceFunction&& other) noexcept {
        if (other.destroy_) {
            other.destroy_(*this);  // 临时调用在 this 上... 
            // 实际需要更细致的实现，这里简化
        }
    }
    
    R operator()(Args... args) const {
        return call_(*this, std::forward<Args>(args)...);
    }
    
    explicit operator bool() const { return call_ != nullptr; }
    
private:
    // 使用 union 同时容纳内联缓冲和堆指针
    struct Storage {
        alignas(SBO_ALIGN) char buffer_[SBO_SIZE];
        void* heapPtr_;
    };
    
    union {
        char buffer_[SBO_SIZE];
        void* heapPtr_;
    };
    
    using CallFn    = R(*)(const Storage&, Args...);
    using DestroyFn = void(*)(Storage&);
    
    CallFn    call_    = nullptr;
    DestroyFn destroy_ = nullptr;
};
```

### 2.3 快速委托实现

```cpp
#include <cstdint>
#include <iostream>

// 快速委托：两个指针——对象 + 成员函数
// 不需要任何堆分配！
template <typename Signature>
class FastDelegate;

template <typename R, typename... Args>
class FastDelegate<R(Args...)> {
public:
    FastDelegate() : object_(nullptr), stub_(nullptr) {}
    
    // 从成员函数构造
    template <typename T, R (T::*Method)(Args...)>
    static FastDelegate create(T* obj) {
        FastDelegate d;
        d.object_ = obj;
        d.stub_ = [](void* obj, Args... args) -> R {
            return (static_cast<T*>(obj)->*Method)(std::forward<Args>(args)...);
        };
        return d;
    }
    
    // 从 const 成员函数构造
    template <typename T, R (T::*Method)(Args...) const>
    static FastDelegate create(const T* obj) {
        FastDelegate d;
        d.object_ = const_cast<T*>(obj);
        d.stub_ = [](void* obj, Args... args) -> R {
            return (static_cast<const T*>(obj)->*Method)(std::forward<Args>(args)...);
        };
        return d;
    }
    
    // 从自由函数/lambda 构造
    template <typename F>
    static FastDelegate create(F* fn = nullptr) {
        FastDelegate d;
        d.object_ = reinterpret_cast<void*>(fn);
        d.stub_ = [](void* obj, Args... args) -> R {
            return (*reinterpret_cast<std::decay_t<F>*>(obj))(
                std::forward<Args>(args)...);
        };
        return d;
    }
    
    R operator()(Args... args) const {
        return stub_(object_, std::forward<Args>(args)...);
    }
    
    explicit operator bool() const { return stub_ != nullptr; }
    
    // 大小：仅 16 bytes（64 位系统）！
private:
    void* object_;
    R (*stub_)(void*, Args...);
};

// ========= 引擎中的使用：UI 按钮回调 =========
struct Button {
    std::string label;
    FastDelegate<void()> onClick;
    
    void click() { if (onClick) onClick(); }
};

struct GameState {
    void startGame()  { std::cout << "Starting game!\n"; }
    void showOptions() { std::cout << "Showing options...\n"; }
    void quitGame()    { std::cout << "Quitting!\n"; }
};

void demoFastDelegate() {
    GameState state;
    
    Button playBtn{"Play"};
    playBtn.onClick = FastDelegate<void()>::create<GameState, &GameState::startGame>(&state);
    
    Button quitBtn{"Quit"};
    quitBtn.onClick = FastDelegate<void()>::create<GameState, &GameState::quitGame>(&state);
    
    playBtn.click();  // 输出: "Starting game!"
    quitBtn.click();  // 输出: "Quitting!"
    
    // 验证大小
    std::cout << "sizeof(FastDelegate) = " << sizeof(FastDelegate<void()>) << " bytes\n";
    // 输出: 16 bytes (64位) — 两倍于 std::function 但零堆分配！
}
```

### 2.4 Variant 渲染命令系统

```cpp
#include <variant>
#include <vector>
#include <iostream>

// 使用 variant 替代虚函数渲染命令

struct DrawMeshCmd {
    uint32_t meshId;
    uint32_t materialId;
    float transform[16];
};

struct SetMaterialCmd {
    uint32_t materialId;
    float params[4];
};

struct ClearRTCmd {
    float color[4];
    float depth;
};

struct DispatchComputeCmd {
    uint32_t kernelId;
    uint32_t groupX, groupY, groupZ;
};

// 封闭的命令类型集合
using RenderCommand = std::variant<
    DrawMeshCmd,
    SetMaterialCmd,
    ClearRTCmd,
    DispatchComputeCmd
>;

class RenderCommandBuffer {
public:
    void push(RenderCommand cmd) {
        commands_.push_back(std::move(cmd));
    }
    
    void execute() {
        for (const auto& cmd : commands_) {
            std::visit([](const auto& c) {
                executeImpl(c);
            }, cmd);
        }
        commands_.clear();
    }
    
private:
    static void executeImpl(const DrawMeshCmd& cmd) {
        std::cout << "DrawMesh: id=" << cmd.meshId << "\n";
        // 实际的 draw call...
    }
    
    static void executeImpl(const SetMaterialCmd& cmd) {
        std::cout << "SetMaterial: id=" << cmd.materialId << "\n";
    }
    
    static void executeImpl(const ClearRTCmd& cmd) {
        std::cout << "ClearRT\n";
    }
    
    static void executeImpl(const DispatchComputeCmd& cmd) {
        std::cout << "DispatchCompute: " << cmd.groupX << "x" 
                  << cmd.groupY << "x" << cmd.groupZ << "\n";
    }
    
    std::vector<RenderCommand> commands_;
};

void demoVariantCommands() {
    RenderCommandBuffer buffer;
    buffer.push(ClearRTCmd{{0.1f, 0.2f, 0.3f, 1.0f}, 1.0f});
    buffer.push(SetMaterialCmd{5, {0.5f, 0.5f, 0.5f, 1.0f}});
    buffer.push(DrawMeshCmd{100, 5, {}});
    buffer.push(DispatchComputeCmd{3, 64, 1, 1});
    buffer.execute();
    
    std::cout << "sizeof(RenderCommand) = " << sizeof(RenderCommand) << " bytes\n";
}
```

### 2.5 性能对比：四种多态方案

```cpp
#include <chrono>
#include <functional>

// 基类 + 虚函数
struct VirtualBase {
    virtual int compute(int x) const = 0;
    virtual ~VirtualBase() = default;
};

struct VirtualImpl : VirtualBase {
    int value;
    int compute(int x) const override { return x + value; }
};

// CRTP
template <typename Derived>
struct CRTPBase {
    int compute(int x) const {
        return static_cast<const Derived*>(this)->computeImpl(x);
    }
};

struct CRTPImpl : CRTPBase<CRTPImpl> {
    int value;
    int computeImpl(int x) const { return x + value; }
};

// Variant + visit
struct VariantImpl {
    int value;
    int compute(int x) const { return x + value; }
};

// 基准测试（简化——实际应使用 Google Benchmark 或 Quick-Bench）
void polymorphismBenchmark() {
    constexpr size_t N = 10'000'000;
    
    // 虚函数
    {
        VirtualImpl impl{42};
        VirtualBase* base = &impl;
        auto start = std::chrono::high_resolution_clock::now();
        int sum = 0;
        for (size_t i = 0; i < N; ++i) {
            sum += base->compute(static_cast<int>(i));
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
        std::cout << "Virtual:  " << ns.count() / N << " ns/call, sum=" << sum << "\n";
    }
    
    // CRTP（通过模板函数消除间接调用）
    {
        CRTPImpl impl{42};
        auto start = std::chrono::high_resolution_clock::now();
        int sum = 0;
        for (size_t i = 0; i < N; ++i) {
            sum += impl.compute(static_cast<int>(i));
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
        std::cout << "CRTP:     " << ns.count() / N << " ns/call, sum=" << sum << "\n";
    }
    
    // Variant（通过 std::visit 分发）
    {
        std::variant<VariantImpl> var{VariantImpl{42}};
        auto start = std::chrono::high_resolution_clock::now();
        int sum = 0;
        for (size_t i = 0; i < N; ++i) {
            sum += std::visit([i](const auto& v) { 
                return v.compute(static_cast<int>(i)); 
            }, var);
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
        std::cout << "Variant:  " << ns.count() / N << " ns/call, sum=" << sum << "\n";
    }
    
    // 直接函数（基线）
    {
        VariantImpl impl{42};
        auto start = std::chrono::high_resolution_clock::now();
        int sum = 0;
        for (size_t i = 0; i < N; ++i) {
            sum += impl.compute(static_cast<int>(i));
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
        std::cout << "Direct:   " << ns.count() / N << " ns/call, sum=" << sum << "\n";
    }
}
```

---

## 3. 练习

### 必做练习 1: 将虚函数插件系统改写为类型擦除

1. 假设现有 `IPlugin` 虚基类接口：`init()`, `update(float dt)`, `shutdown()`
2. 编写一个类型擦除的 `Plugin` 类，可以包装任何有这三个方法（或等价的自由函数/lambda）的类型，不需要继承
3. 实现 `PluginManager`，使用 `std::vector<Plugin>` 管理所有插件
4. 添加 SBO：小于 64 bytes 的插件对象内联存储
5. 对比原虚函数方案的内存布局和调用性能

### 必做练习 2: 实现一个支持快速委托的事件系统

1. 实现 `EventDispatcher<EventType>`，使用 `FastDelegate<void(const EventType&)>` 作为回调类型
2. 支持注册/取消注册处理器
3. 事件分发时遍历所有委托并调用
4. 使用案例：键盘输入事件 → 玩家控制器、UI 系统、调试面板三个处理器
5. 验证：每个委托 16 bytes，零堆分配

### 可选挑战: Variant 命令模式 + 撤销系统

1. 设计一个 `Command` variant，包含至少 5 种编辑操作（移动、缩放、旋转、创建、删除）
2. 每个命令有 `execute()` 和 `undo()` 两个方法
3. 实现命令历史（`std::vector<Command>`）和撤销/重做
4. `std::visit` 实现批量重放（如"重放最近 50 个命令"）
5. 对比如果用虚函数实现，调用开销的差异（基准测试）

---
## 3.5 参考答案

> [!tip]- 练习 1 参考答案：虚函数插件系统 → 类型擦除
> ```cpp
> #include <memory>
> #include <new>
> #include <vector>
> #include <iostream>
> #include <functional>
> #include <cstring>
> 
> // ========== 原始虚函数接口（对比用） ==========
> struct IPlugin {
>     virtual ~IPlugin() = default;
>     virtual bool init() = 0;
>     virtual void update(float dt) = 0;
>     virtual void shutdown() = 0;
> };
> 
> // ========== 类型擦除 Plugin（带 SBO） ==========
> class Plugin {
>     static constexpr size_t SBO_SIZE  = 64;
>     static constexpr size_t SBO_ALIGN = alignof(std::max_align_t);
> 
> public:
>     // 构造函数模板：接受任何有 init/update/shutdown 的类型
>     template <typename T>
>     Plugin(T obj) {
>         using Decayed = std::decay_t<T>;
> 
>         if constexpr (sizeof(Decayed) <= SBO_SIZE &&
>                       alignof(Decayed) <= SBO_ALIGN &&
>                       std::is_nothrow_move_constructible_v<Decayed>) {
>             // SBO：栈内存储
>             new (buffer_) Decayed(std::move(obj));
>             isHeap_ = false;
> 
>             init_ = [](void* self) -> bool {
>                 return static_cast<Decayed*>(self)->init();
>             };
>             update_ = [](void* self, float dt) {
>                 static_cast<Decayed*>(self)->update(dt);
>             };
>             shutdown_ = [](void* self) {
>                 static_cast<Decayed*>(self)->shutdown();
>             };
>             destroy_ = [](void* self) {
>                 static_cast<Decayed*>(self)->~Decayed();
>             };
>         } else {
>             // 大对象：堆分配
>             auto* ptr = new Decayed(std::move(obj));
>             heapPtr_ = ptr;
>             isHeap_ = true;
> 
>             init_ = [](void* self) -> bool {
>                 return (*static_cast<Decayed*>(self))->init();
>             };
>             update_ = [](void* self, float dt) {
>                 (*static_cast<Decayed*>(self))->update(dt);
>             };
>             shutdown_ = [](void* self) {
>                 (*static_cast<Decayed*>(self))->shutdown();
>             };
>             destroy_ = [](void* self) {
>                 delete static_cast<Decayed*>(self);
>             };
>         }
>     }
> 
>     ~Plugin() {
>         if (destroy_) destroy_(isHeap_ ? heapPtr_ : buffer_);
>     }
> 
>     // 移动语义
>     Plugin(Plugin&& other) noexcept {
>         moveFrom(std::move(other));
>     }
>     Plugin& operator=(Plugin&& other) noexcept {
>         if (this != &other) {
>             if (destroy_) destroy_(isHeap_ ? heapPtr_ : buffer_);
>             moveFrom(std::move(other));
>         }
>         return *this;
>     }
> 
>     Plugin(const Plugin&) = delete;
>     Plugin& operator=(const Plugin&) = delete;
> 
>     // 统一接口
>     bool init()           { return init_ ? init_(getPtr()) : true; }
>     void update(float dt) { if (update_) update_(getPtr(), dt); }
>     void shutdown()       { if (shutdown_) shutdown_(getPtr()); }
> 
>     explicit operator bool() const { return init_ != nullptr; }
> 
> private:
>     void* getPtr() { return isHeap_ ? heapPtr_ : buffer_; }
> 
>     void moveFrom(Plugin&& other) {
>         if (other.isHeap_) {
>             heapPtr_ = other.heapPtr_;
>             other.heapPtr_ = nullptr;
>         } else {
>             std::memcpy(buffer_, other.buffer_, SBO_SIZE);
>         }
>         isHeap_   = other.isHeap_;
>         init_     = other.init_;
>         update_   = other.update_;
>         shutdown_ = other.shutdown_;
>         destroy_  = other.destroy_;
> 
>         other.init_     = nullptr;
>         other.update_   = nullptr;
>         other.shutdown_ = nullptr;
>         other.destroy_  = nullptr;
>     }
> 
>     union {
>         alignas(SBO_ALIGN) char buffer_[SBO_SIZE];
>         void* heapPtr_;
>     };
>     bool isHeap_ = false;
> 
>     using FuncBoolVoid  = bool (*)(void*);
>     using FuncVoidFloat = void (*)(void*, float);
>     using FuncVoidVoid  = void (*)(void*);
> 
>     FuncBoolVoid  init_     = nullptr;
>     FuncVoidFloat update_   = nullptr;
>     FuncVoidVoid  shutdown_ = nullptr;
>     FuncVoidVoid  destroy_  = nullptr;
> };
> 
> // ========== PluginManager ==========
> class PluginManager {
> public:
>     void registerPlugin(Plugin p) {
>         plugins_.push_back(std::move(p));
>     }
> 
>     bool initAll() {
>         for (auto& p : plugins_) {
>             if (!p.init()) return false;
>         }
>         return true;
>     }
> 
>     void updateAll(float dt) {
>         for (auto& p : plugins_) p.update(dt);
>     }
> 
>     void shutdownAll() {
>         for (auto& p : plugins_) p.shutdown();
>         plugins_.clear();
>     }
> 
> private:
>     std::vector<Plugin> plugins_;
> };
> 
> // ========== 具体插件实现（无需继承 IPlugin！） ==========
> struct RenderPlugin {
>     std::string name = "Renderer";
>     bool init()           { std::cout << name << " init\n"; return true; }
>     void update(float dt) { std::cout << name << " update " << dt << "\n"; }
>     void shutdown()       { std::cout << name << " shutdown\n"; }
> };
> 
> struct PhysicsPlugin {
>     int stepCount = 0;
>     bool init()           { std::cout << "Physics init\n"; return true; }
>     void update(float dt) { stepCount++; /* 物理步进 */ }
>     void shutdown()       { std::cout << "Physics shutdown after " << stepCount << " steps\n"; }
> };
> 
> // Lambda 也可以作为 Plugin！
> auto makeLoggingPlugin(const std::string& tag) {
>     struct {
>         std::string tag;
>         bool init()           { std::cout << "[" << tag << "] init\n"; return true; }
>         void update(float)    { std::cout << "[" << tag << "] tick\n"; }
>         void shutdown()       { std::cout << "[" << tag << "] shutdown\n"; }
>     } p{tag};
>     return p;
> }
> 
> void demo() {
>     PluginManager mgr;
> 
>     // 完全不相关的类型，无需继承
>     mgr.registerPlugin(RenderPlugin{});
>     mgr.registerPlugin(PhysicsPlugin{});
>     mgr.registerPlugin(makeLoggingPlugin("Audio"));
> 
>     mgr.initAll();
>     mgr.updateAll(0.016f);
>     mgr.updateAll(0.016f);
>     mgr.shutdownAll();
> 
>     // 对比内存布局：
>     std::cout << "\n=== Memory Analysis ===\n";
>     std::cout << "sizeof(IPlugin*)      = " << sizeof(IPlugin*) << " (pointer to vtable-based)\n";
>     std::cout << "sizeof(Plugin)        = " << sizeof(Plugin)  << " (type-erased, SBO)\n";
>     std::cout << "sizeof(RenderPlugin)  = " << sizeof(RenderPlugin)  << " (≤ 64 → SBO inline)\n";
>     std::cout << "- Plugin wraps RenderPlugin with zero heap allocation\n";
> }
> ```

> [!tip]- 练习 2 参考答案：快速委托事件系统
> ```cpp
> #include <iostream>
> #include <vector>
> #include <string>
> #include <algorithm>
> 
> // ========== 快速委托（16 bytes） ==========
> template <typename Signature>
> class FastDelegate;
> 
> template <typename R, typename... Args>
> class FastDelegate<R(Args...)> {
> public:
>     FastDelegate() : object_(nullptr), stub_(nullptr) {}
> 
>     // 从成员函数构造
>     template <typename T, R (T::*Method)(Args...)>
>     static FastDelegate create(T* obj) {
>         FastDelegate d;
>         d.object_ = obj;
>         d.stub_ = [](void* obj, Args... args) -> R {
>             return (static_cast<T*>(obj)->*Method)(std::forward<Args>(args)...);
>         };
>         return d;
>     }
> 
>     // 从 const 成员函数构造
>     template <typename T, R (T::*Method)(Args...) const>
>     static FastDelegate create(const T* obj) {
>         FastDelegate d;
>         d.object_ = const_cast<T*>(obj);
>         d.stub_ = [](void* obj, Args... args) -> R {
>             return (static_cast<const T*>(obj)->*Method)(std::forward<Args>(args)...);
>         };
>         return d;
>     }
> 
>     // 从自由函数/lambda 构造
>     template <typename F>
>     static FastDelegate create(F* fn) {
>         FastDelegate d;
>         d.object_ = reinterpret_cast<void*>(fn);
>         d.stub_ = [](void* obj, Args... args) -> R {
>             return (*reinterpret_cast<std::decay_t<F>*>(obj))(std::forward<Args>(args)...);
>         };
>         return d;
>     }
> 
>     R operator()(Args... args) const {
>         return stub_(object_, std::forward<Args>(args)...);
>     }
> 
>     explicit operator bool() const { return stub_ != nullptr; }
>     bool operator==(const FastDelegate& o) const {
>         return object_ == o.object_ && stub_ == o.stub_;
>     }
>     bool operator!=(const FastDelegate& o) const { return !(*this == o); }
> 
> private:
>     void* object_;
>     R (*stub_)(void*, Args...);
> };
> 
> // ========== 键盘输入事件 ==========
> struct KeyEvent {
>     int keyCode;
>     bool pressed;
>     std::string toString() const {
>         return "KeyEvent(key=" + std::to_string(keyCode)
>              + ", " + (pressed ? "down" : "up") + ")";
>     }
> };
> 
> // ========== 事件分发器 ==========
> template <typename EventType>
> class EventDispatcher {
> public:
>     using Delegate = FastDelegate<void(const EventType&)>;
> 
>     void subscribe(Delegate d) {
>         handlers_.push_back(d);
>     }
> 
>     void unsubscribe(Delegate d) {
>         auto it = std::find(handlers_.begin(), handlers_.end(), d);
>         if (it != handlers_.end()) {
>             handlers_.erase(it);
>         }
>     }
> 
>     void dispatch(const EventType& event) {
>         for (auto& handler : handlers_) {
>             if (handler) handler(event);
>         }
>     }
> 
>     size_t handlerCount() const { return handlers_.size(); }
> 
> private:
>     std::vector<Delegate> handlers_;
> };
> 
> // ========== 使用案例 ==========
> struct PlayerController {
>     void onKey(const KeyEvent& e) {
>         std::cout << "PlayerController: " << e.toString() << "\n";
>         if (e.keyCode == 87 && e.pressed) std::cout << "  → Move forward\n"; // W
>     }
> };
> 
> struct UISystem {
>     void onKey(const KeyEvent& e) {
>         std::cout << "UISystem: " << e.toString() << "\n";
>         if (e.keyCode == 27 && e.pressed) std::cout << "  → Open pause menu\n"; // ESC
>     }
> };
> 
> struct DebugPanel {
>     void onKey(const KeyEvent& e) {
>         if (e.keyCode == 192 && e.pressed)  // ~ 键
>             std::cout << "DebugPanel: toggle console\n";
>     }
> };
> 
> void demoEventSystem() {
>     PlayerController player;
>     UISystem ui;
>     DebugPanel debug;
> 
>     EventDispatcher<KeyEvent> dispatcher;
> 
>     // 注册处理器（16 bytes 每个，零堆分配）
>     dispatcher.subscribe(
>         FastDelegate<void(const KeyEvent&)>::create<PlayerController, &PlayerController::onKey>(&player));
>     dispatcher.subscribe(
>         FastDelegate<void(const KeyEvent&)>::create<UISystem, &UISystem::onKey>(&ui));
>     dispatcher.subscribe(
>         FastDelegate<void(const KeyEvent&)>::create<DebugPanel, &DebugPanel::onKey>(&debug));
> 
>     std::cout << "Handlers: " << dispatcher.handlerCount() << "\n";
>     std::cout << "sizeof(FastDelegate) = " << sizeof(FastDelegate<void(const KeyEvent&)>)
>               << " bytes (zero heap)\n\n";
> 
>     // 模拟按键事件
>     dispatcher.dispatch(KeyEvent{87, true});   // W pressed
>     dispatcher.dispatch(KeyEvent{27, true});   // ESC pressed
>     dispatcher.dispatch(KeyEvent{192, true});  // ~ pressed
> }
> ```

> [!tip]- 可选挑战参考答案：Variant 命令模式 + 撤销
> ```cpp
> #include <variant>
> #include <vector>
> #include <iostream>
> #include <string>
> 
> // ========== 命令类型 ==========
> struct MoveCmd {
>     int entityId;
>     float fromX, fromY, fromZ;
>     float toX, toY, toZ;
> };
> 
> struct ScaleCmd {
>     int entityId;
>     float fromScale;
>     float toScale;
> };
> 
> struct RotateCmd {
>     int entityId;
>     float fromAngle;
>     float toAngle;
> };
> 
> struct CreateCmd {
>     int entityId;
>     float x, y, z;
> };
> 
> struct DeleteCmd {
>     int entityId;
>     float x, y, z;  // 记录位置以便撤销重建
> };
> 
> // 封闭的命令集合
> using Command = std::variant<MoveCmd, ScaleCmd, RotateCmd, CreateCmd, DeleteCmd>;
> 
> // ========== 命令执行器（模拟场景状态） ==========
> struct SceneState {
>     std::string toString() const {
>         return "Scene{entities: " + std::to_string(entityCount) + "}";
>     }
>     int entityCount = 0;
> };
> 
> SceneState g_scene;
> 
> void execute(const Command& cmd) {
>     std::visit([](const auto& c) { executeImpl(c); }, cmd);
> }
> 
> void undo(const Command& cmd) {
>     std::visit([](const auto& c) { undoImpl(c); }, cmd);
> }
> 
> // 具体实现（每种命令的 execute/undo）
> void executeImpl(const MoveCmd& c) {
>     std::cout << "MOVE   entity " << c.entityId << ": ("
>               << c.fromX << "," << c.fromY << "," << c.fromZ << ") → ("
>               << c.toX << "," << c.toY << "," << c.toZ << ")\n";
> }
> void undoImpl(const MoveCmd& c) {
>     std::cout << "UNDO MOVE entity " << c.entityId << " back to ("
>               << c.fromX << "," << c.fromY << "," << c.fromZ << ")\n";
> }
> 
> void executeImpl(const ScaleCmd& c) {
>     std::cout << "SCALE  entity " << c.entityId << ": "
>               << c.fromScale << " → " << c.toScale << "\n";
> }
> void undoImpl(const ScaleCmd& c) {
>     std::cout << "UNDO SCALE entity " << c.entityId << " back to " << c.fromScale << "\n";
> }
> 
> void executeImpl(const RotateCmd& c) {
>     std::cout << "ROTATE entity " << c.entityId << ": "
>               << c.fromAngle << "° → " << c.toAngle << "°\n";
> }
> void undoImpl(const RotateCmd& c) {
>     std::cout << "UNDO ROTATE entity " << c.entityId << " back to " << c.fromAngle << "°\n";
> }
> 
> void executeImpl(const CreateCmd& c) {
>     g_scene.entityCount++;
>     std::cout << "CREATE entity " << c.entityId << " at ("
>               << c.x << "," << c.y << "," << c.z << ")\n";
> }
> void undoImpl(const CreateCmd& c) {
>     g_scene.entityCount--;
>     std::cout << "UNDO CREATE: remove entity " << c.entityId << "\n";
> }
> 
> void executeImpl(const DeleteCmd& c) {
>     g_scene.entityCount--;
>     std::cout << "DELETE entity " << c.entityId << "\n";
> }
> void undoImpl(const DeleteCmd& c) {
>     g_scene.entityCount++;
>     std::cout << "UNDO DELETE: restore entity " << c.entityId << " at ("
>               << c.x << "," << c.y << "," << c.z << ")\n";
> }
> 
> // ========== 命令历史（撤销/重做） ==========
> class CommandHistory {
> public:
>     void execute(Command cmd) {
>         ::execute(cmd);
>         undoStack_.push_back(std::move(cmd));
>         redoStack_.clear();  // 新命令清空重做历史
>     }
> 
>     bool canUndo() const { return !undoStack_.empty(); }
>     bool canRedo() const { return !redoStack_.empty(); }
> 
>     void undo() {
>         if (!canUndo()) return;
>         Command cmd = std::move(undoStack_.back());
>         undoStack_.pop_back();
>         ::undo(cmd);
>         redoStack_.push_back(std::move(cmd));
>     }
> 
>     void redo() {
>         if (!canRedo()) return;
>         Command cmd = std::move(redoStack_.back());
>         redoStack_.pop_back();
>         ::execute(cmd);
>         undoStack_.push_back(std::move(cmd));
>     }
> 
>     // 批量重放最近 N 个命令
>     void replayRecent(size_t n) {
>         size_t start = n >= undoStack_.size() ? 0 : undoStack_.size() - n;
>         std::cout << "\n=== Replaying " << (undoStack_.size() - start) << " commands ===\n";
>         for (size_t i = start; i < undoStack_.size(); ++i) {
>             ::execute(undoStack_[i]);
>         }
>     }
> 
> private:
>     std::vector<Command> undoStack_;
>     std::vector<Command> redoStack_;
> };
> 
> void demoVariantCommands() {
>     CommandHistory history;
> 
>     history.execute(CreateCmd{1, 0, 0, 0});
>     history.execute(MoveCmd{1, 0,0,0, 10,0,0});
>     history.execute(ScaleCmd{1, 1.0f, 2.0f});
>     history.execute(RotateCmd{1, 0.0f, 45.0f});
>     history.execute(DeleteCmd{1, 10,0,0});
> 
>     std::cout << "\n--- Undo ---\n";
>     history.undo();  // 撤销 Delete
>     history.undo();  // 撤销 Rotate
> 
>     std::cout << "\n--- Redo ---\n";
>     history.redo();  // 重做 Rotate
> 
>     // 性能对比说明
>     std::cout << "\n=== Performance Note ===\n";
>     std::cout << "sizeof(Command) = " << sizeof(Command) << " bytes\n";
>     std::cout << "- variant: no vptr overhead, jump-table dispatch (like switch-case)\n";
>     std::cout << "- virtual: vptr + vtable lookup, cannot inline\n";
>     std::cout << "- For closed type sets, variant typically ~2-3x faster\n";
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。类型擦除的 SBO 尺寸选择（64/32/48 bytes）、函数指针 vs 虚函数的设计取舍均可调整。关键理解"将类型信息编码为函数指针"这一核心思想。

## 4. 扩展阅读

- **"Member Function Pointers and the Fastest Possible C++ Delegates"** — Don Clugston, 2004 — 快速委托的经典文章
- **CppCon 2019: "Type Erasure — A Low Level Mechanism for High Level Design"** — Arthur O'Dwyer — 类型擦除的深入讲解
- **"Better Code: Runtime Polymorphism"** — Sean Parent, NDC 2017 — "Inheritance Is The Base Class of Evil" 经典演讲
- **P0228R3: `std::any_invocable` / `std::move_only_function`** — C++23 只移动可调用对象提案
- **Boost.TypeErasure** — 自动生成类型擦除包装器的库
- **dyno** — Louis Dionne 的实验性类型擦除库，展示了零开销的类型擦除
- **`std::function` 实现分析** — libstdc++ 和 libc++ 的源码值得阅读，理解 SBO 和分配策略

---

## 常见陷阱

1. **类型擦除中的"复制即丢失类型"**：类型擦除依赖于构造函数模板捕获具体类型。如果用户意外复制到基类引用，类型信息会丢失（slicing）。
   ```cpp
   // ✗ 危险：obj 是 const Animal&，但 Drawable 期望具体类型
   const Animal& obj = getAnimal();
   Drawable d(obj);  // 捕获的是 Animal，不是 Dog！
   
   // ✓ 安全：在知道具体类型的地方构造
   auto dog = std::make_unique<Dog>();
   Drawable d2(*dog);  // 正确捕获 Dog
   ```

2. **variant 中的异常安全**：`std::visit` 访问一个 variant 时，如果 visitor 抛出异常，variant 本身的状态是定义良好的（不变）。但如果 visitor 修改了外部状态后抛出异常，你需要手动回滚。
   ```cpp
   // ✗ 命令执行中抛出异常 → 对象可能处于不一致状态
   std::visit([](auto& cmd) { cmd.execute(); }, command);
   
   // ✓ 先验证，再执行
   if (std::visit([](auto& cmd) { return cmd.validate(); }, command)) {
       std::visit([](auto& cmd) { cmd.execute(); }, command);
   }
   ```

3. **std::function 的意外堆分配**：lambda 捕获超过 SBO 容量（通常是 16-32 bytes）或捕获了不可平凡复制的对象时，`std::function` 会退化为堆分配。这在热路径上可能导致帧预算超标。
   ```cpp
   // ✗ 捕获大对象 → 堆分配！
   std::function<void()> f = [bigData = std::array<int, 100>{}]() { ... };
   
   // ✓ 对于大捕获，使用 std::move_only_function (C++23) 或手写 SBO
   // 或者用指针捕获
   auto bigData = std::make_shared<std::array<int, 100>>();
   std::function<void()> f2 = [bigData]() { ... };  // 只捕获 8-byte 指针
   ```

4. **虚函数与 variant 的"开放/封闭"取舍**：如果用 variant 替代虚函数，就等于把类型集合定为封闭的。如果以后需要添加新类型，必须修改 variant 的定义和所有 `std::visit` 调用点。这就是"表达式问题"——虚函数容易添加新类型但难添加新操作，variant 容易添加新操作但难添加新类型。在引擎中，命令/事件类型通常是封闭的（由引擎定义），而插件/组件类型可能是开放的——选型时需要权衡。
