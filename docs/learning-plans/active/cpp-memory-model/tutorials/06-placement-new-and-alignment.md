---
title: "Placement New 与对齐存储"
updated: 2026-06-08
---

> 所属计划: [[plan|C++ 内存模型]]
> 预计耗时: 50 分钟
> 前置知识: [[05-new-delete-memory-lifecycle|new/delete 与内存生命周期]]

---

## 1. 概念讲解

### 为什么需要这个？

在性能关键的代码中（渲染、物理、网络），逐个 `new`/`delete` 的堆分配是性能杀手。placement new 允许你**在已分配的内存上原地构造对象**，从而把"分配"和"构造"解耦。

使用场景：
- 池分配器 / Arena 分配器（预分配一大块，从上面切对象）
- `std::vector::emplace_back`（在原位构造，避免拷贝）
- `std::optional` / `std::variant`（在未初始化的存储区延迟构造）
- 序列化/反序列化（从字节流原地构造对象）

### 核心思想

**Placement new = "在别人家的地上盖房子"。**

```mermaid
flowchart LR
    A[准备缓冲] --> B[确保对齐] --> C[new(ptr) T(args)]
    C --> D[手动析构: p->~T()]
```

和常规 `new` 的区别：

| | 常规 `new T` | Placement new |
|---|---|---|
| 内存来源 | 从堆 `operator new` 请求 | 使用你提供的地址 |
| 构造 | 在分配的内存上调用构造函数 | 同上 |
| 析构 | `delete p` 自动析构 + 释放 | **必须**手动 `p->~T()` |
| 内存归还 | `delete` 自动归还 | **你负责**归还内存 |

对齐存储 = 确保内存地址满足 `alignof(T)` 的要求。CPU 访问未对齐地址在某些架构上直接崩溃（ARM `SIGBUS`），在 x86 上有性能惩罚。

> [!tip] 类比
> 常规 `new` 是找房地产开发商买地 + 盖房，一站式服务。Placement new 是你已经有了一块祖传宅基地，请施工队直接在上面盖房——施工队不管地是哪来的，也不负责拆房后的土地处理。

---

## 2. 代码示例

```cpp
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <new>

// --- placement new 基础用法 ---
class Widget {
    int id_;
public:
    explicit Widget(int id) : id_(id) {
        std::cout << "Widget(" << id_ << ") constructed\n";
    }
    ~Widget() {
        std::cout << "Widget(" << id_ << ") destroyed\n";
    }
    int id() const { return id_; }
};

void demo_placement_new() {
    std::cout << "=== Placement new basics ===\n";
    alignas(Widget) char buffer[sizeof(Widget)];

    Widget* w = ::new (buffer) Widget(42);  // 在 buffer 上构造
    std::cout << "w->id() = " << w->id() << "\n";
    std::cout << "buffer addr = " << static_cast<void*>(buffer)
              << ", w = " << static_cast<void*>(w) << "\n";

    w->~Widget();  // 必须手动析构！没有 placement delete
}

// --- std::construct_at / std::destroy_at (C++17/20) ---
void demo_std_construct() {
    std::cout << "\n=== std::construct_at ===\n";
    alignas(Widget) char buf[sizeof(Widget)];

    Widget* w = std::construct_at(reinterpret_cast<Widget*>(buf), 99);
    std::cout << "w->id() = " << w->id() << "\n";
    std::destroy_at(w);  // C++17，比 p->~T() 更清晰
}

// --- 手动对齐：std::align ---
void demo_std_align() {
    std::cout << "\n=== std::align ===\n";
    char raw[128];
    void* ptr = raw;
    std::size_t space = sizeof(raw);

    std::cout << "before align: ptr=" << ptr << " space=" << space << "\n";
    if (std::align(alignof(double), sizeof(double), ptr, space)) {
        std::cout << "after align(8): ptr=" << ptr
                  << " space=" << space << "\n";
        double* d = ::new (ptr) double(3.14);
        std::cout << "*d = " << *d << "\n";
        std::destroy_at(d);
    }
}

// --- Arena (Bump Allocator) 原型 ---
class BumpArena {
    alignas(std::max_align_t) char buffer_[1024];
    char* current_;
    char* end_;

public:
    BumpArena() : current_(buffer_), end_(buffer_ + sizeof(buffer_)) {}

    void* allocate(std::size_t size, std::size_t alignment) {
        void* ptr = current_;
        std::size_t space = end_ - current_;
        if (!std::align(alignment, size, ptr, space)) {
            return nullptr;  // 空间不足
        }
        current_ = static_cast<char*>(ptr) + size;
        return ptr;
    }

    void reset() { current_ = buffer_; }
    // 注意：这个简单版本不支持逐个释放，只支持全部 reset
};

void demo_arena() {
    std::cout << "\n=== Bump Arena ===\n";
    BumpArena arena;

    void* p1 = arena.allocate(sizeof(int), alignof(int));
    void* p2 = arena.allocate(sizeof(double), alignof(double));
    void* p3 = arena.allocate(sizeof(Widget), alignof(Widget));

    std::cout << "p1 (int)    = " << p1 << "\n";
    std::cout << "p2 (double) = " << p2 << "\n";
    std::cout << "p3 (Widget) = " << p3 << "\n";

    int* i = ::new (p1) int(7);
    double* d = ::new (p2) double(2.71);
    Widget* w = ::new (p3) Widget(100);

    std::cout << "values: " << *i << ", " << *d << ", " << w->id() << "\n";

    std::destroy_at(w);
    std::destroy_at(d);
    std::destroy_at(i);

    arena.reset();  // 整块重用
}

// --- over-aligned 类型 (C++17) ---
struct alignas(64) CacheLineBlock {
    int data[16];
};

void demo_overaligned() {
    std::cout << "\n=== Over-aligned type ===\n";
    std::cout << "alignof(CacheLineBlock) = " << alignof(CacheLineBlock) << "\n";

    // C++17 起: new 会自动调用对齐重载
    auto* p = new CacheLineBlock{};
    std::cout << "new CacheLineBlock addr = " << p << "\n";
    std::cout << "addr % 64 = " << (reinterpret_cast<uintptr_t>(p) % 64) << "\n";
    delete p;
}

int main() {
    demo_placement_new();
    demo_std_construct();
    demo_std_align();
    demo_arena();
    demo_overaligned();
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -o placement_new placement_new.cpp && ./placement_new
```

**预期输出:**
```text
=== Placement new basics ===
Widget(42) constructed
w->id() = 42
buffer addr = 0x7ffd..., w = 0x7ffd...
Widget(42) destroyed

=== std::construct_at ===
Widget(99) constructed
w->id() = 99
Widget(99) destroyed

=== std::align ===
before align: ptr=0x7ffd... space=128
after align(8): ptr=0x7ffd... space=120
*d = 3.14

=== Bump Arena ===
p1 (int)    = 0x7ffd...
p2 (double) = 0x7ffd...  // 自动对齐到 8 字节边界
p3 (Widget) = 0x7ffd...
values: 7, 2.71, 100
Widget(100) destroyed

=== Over-aligned type ===
alignof(CacheLineBlock) = 64
new CacheLineBlock addr = 0x55...
addr % 64 = 0
```

---

## 3. 练习

### 练习 1: 最小化 Arena 分配器
在上面的 `BumpArena` 基础上扩展：
1. 支持模板 `allocate<T>(n)`：分配 `n * sizeof(T)` 并对齐到 `alignof(T)`
2. 添加一个 `deallocate_all()` 方法，析构 arena 中所有存活的对象（需要记录对象类型——提示：类型擦除 + 析构函数指针）
3. 确保 `allocate` 在空间不足时抛出 `std::bad_alloc`

### 练习 2: 对齐的条件判断
```cpp
bool is_aligned(void* ptr, size_t alignment);
```
写一个判断指针是否按给定对齐值对齐的函数。然后写一个 `assert_aligned<T>(void* ptr)` 宏，在 Debug 模式下检查 `ptr` 是否满足 `alignof(T)`，Release 模式下无开销。注意 `alignment` 必须是 2 的幂——利用这个性质优化实现。

### 练习 3: 无堆 `std::optional`（可选）
手写一个简化版 `Optional<T>`，内部用 `alignas(T) unsigned char storage_[sizeof(T)]` 存储对象。实现：
- `construct(Args&&... args)`：在 storage 上 placement new
- `destroy()`：显式析构
- `operator*()` / `operator->()`：访问（前置：已构造）
- `has_value()`：跟踪是否包含值
- 确保不支持拷贝/移动时正确删除

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> #include <cstdint>
> #include <cstddef>
> #include <iostream>
> #include <new>
> #include <vector>
>
> class TrackedArena {
>     // 类型擦除的析构函数指针
>     using DestructorFunc = void(*)(void*);
>
>     struct Record {
>         void*          ptr;
>         DestructorFunc destroy;
>     };
>
>     alignas(std::max_align_t) char buffer_[4096];
>     char*       current_;
>     char*       end_;
>     std::vector<Record> records_;
>
> public:
>     TrackedArena() : current_(buffer_), end_(buffer_ + sizeof(buffer_)) {}
>
>     // 模板分配：分配 n 个 T，对齐到 alignof(T)
>     template<typename T>
>     T* allocate(size_t n = 1) {
>         static_assert(alignof(T) <= alignof(std::max_align_t),
>                       "Over-aligned types not supported by this arena");
>
>         size_t size = n * sizeof(T);
>         size_t alignment = alignof(T);
>
>         void* ptr = current_;
>         size_t space = end_ - current_;
>
>         if (!std::align(alignment, size, ptr, space)) {
>             throw std::bad_alloc{};
>         }
>         current_ = static_cast<char*>(ptr) + size;
>
>         // 记录析构函数指针（类型擦除）
>         records_.push_back({ptr, [](void* p) {
>             static_cast<T*>(p)->~T();
>         }});
>
>         return static_cast<T*>(ptr);
>     }
>
>     // 析构所有对象并重置 arena
>     void deallocate_all() {
>         // 按构造的逆序析构（LIFO）
>         for (auto it = records_.rbegin(); it != records_.rend(); ++it) {
>             it->destroy(it->ptr);
>         }
>         records_.clear();
>         current_ = buffer_;
>     }
>
>     void reset() {
>         // 仅重置指针，不析构（调用者自行管理生命周期）
>         current_ = buffer_;
>     }
> };
>
> // 测试
> struct Widget {
>     int id;
>     explicit Widget(int i) : id(i) {
>         std::cout << "Widget(" << id << ") constructed\n";
>     }
>     ~Widget() {
>         std::cout << "Widget(" << id << ") destroyed\n";
>     }
> };
>
> int main() {
>     TrackedArena arena;
>
>     auto* i = arena.allocate<int>();
>     *i = 42;
>     auto* w = arena.allocate<Widget>(1);
>     ::new (w) Widget(7);  // placement new 构造（arena 只分配了内存）
>
>     std::cout << "int=" << *i << ", widget id=" << w->id << "\n";
>
>     arena.deallocate_all();  // 析构 widget，重置 arena
>     return 0;
> }
> ```
>
> **设计要点：**
> - 类型擦除通过 lambda → 函数指针实现，无需虚函数
> - LIFO 析构顺序确保依赖关系正确（后构造的先析构）
> - `allocate<T>` 只分配对齐内存，不调用构造函数——原因：`emplace` 风格需要参数转发，简化版保持分离
> - `std::bad_alloc` 在空间不足时抛出，与标准库行为一致

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <cstdint>
> #include <cstddef>
> #include <cassert>
> #include <iostream>
>
> // 判断指针是否按给定对齐值对齐
> inline bool is_aligned(const void* ptr, std::size_t alignment) {
>     // alignment 必须是 2 的幂：利用位运算优化
>     // ptr % alignment == 0  ⇔  (ptr & (alignment - 1)) == 0
>     auto addr = reinterpret_cast<std::uintptr_t>(ptr);
>     return (addr & (alignment - 1)) == 0;
> }
>
> // Debug 模式下检查对齐的宏，Release 下无开销
> #ifdef NDEBUG
>     #define assert_aligned(ptr, T) ((void)0)
> #else
>     #define assert_aligned(ptr, T) \
>         do { \
>             if (!is_aligned((ptr), alignof(T))) { \
>                 std::cerr << "ASSERT FAILED: " << #ptr \
>                           << " not aligned to " << alignof(T) \
>                           << " (" << __FILE__ << ":" << __LINE__ << ")\n"; \
>                 std::abort(); \
>             } \
>         } while (0)
> #endif
>
> // 测试
> struct alignas(32) Aligned32 { int x; };
>
> int main() {
>     int x = 0;
>     assert_aligned(&x, int);  // OK: int 对齐到 4
>
>     alignas(32) char buf[64];
>     assert_aligned(buf, Aligned32);  // OK: buf 对齐到 32
>
>     char* misaligned = buf + 1;
>     // assert_aligned(misaligned, Aligned32);  // 触发断言失败
>
>     std::cout << "is_aligned(buf, 32) = " << is_aligned(buf, 32) << "\n";
>     std::cout << "is_aligned(buf+1, 32) = " << is_aligned(buf+1, 32) << "\n";
>     return 0;
> }
> ```
>
> **关键点：**
> - `ptr % alignment == 0` 等价于 `(addr & (alignment - 1)) == 0`（仅当 alignment 是 2 的幂时成立，这是所有有效对齐值的特点）——避免了除法指令
> - `NDEBUG` 是标准 assert 宏使用的宏，`assert()` 在 Release 模式下正是这样消除的
> - `do { ... } while(0)` 是宏安全的经典模式，防止 if-else 悬挂

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <cstddef>
> #include <new>
> #include <utility>
> #include <stdexcept>
>
> template<typename T>
> class Optional {
>     alignas(T) unsigned char storage_[sizeof(T)];
>     bool has_value_ = false;
>
> public:
>     Optional() = default;
>
>     ~Optional() {
>         if (has_value_) {
>             reinterpret_cast<T*>(storage_)->~T();
>         }
>     }
>
>     // 不支持拷贝/移动（题目要求）
>     Optional(const Optional&) = delete;
>     Optional& operator=(const Optional&) = delete;
>     Optional(Optional&&) = delete;
>     Optional& operator=(Optional&&) = delete;
>
>     template<typename... Args>
>     void construct(Args&&... args) {
>         if (has_value_) {
>             destroy();  // 覆盖旧值前先析构
>         }
>         ::new (storage_) T(std::forward<Args>(args)...);
>         has_value_ = true;
>     }
>
>     void destroy() {
>         if (has_value_) {
>             reinterpret_cast<T*>(storage_)->~T();
>             has_value_ = false;
>         }
>     }
>
>     bool has_value() const { return has_value_; }
>
>     T& operator*() {
>         if (!has_value_) throw std::logic_error("Optional has no value");
>         return *reinterpret_cast<T*>(storage_);
>     }
>
>     T* operator->() {
>         if (!has_value_) throw std::logic_error("Optional has no value");
>         return reinterpret_cast<T*>(storage_);
>     }
>
>     const T& operator*() const {
>         if (!has_value_) throw std::logic_error("Optional has no value");
>         return *reinterpret_cast<const T*>(storage_);
>     }
>
>     const T* operator->() const {
>         if (!has_value_) throw std::logic_error("Optional has no value");
>         return reinterpret_cast<const T*>(storage_);
>     }
> };
> ```
>
> **核心实现原理（对标 `std::optional`）：**
> 1. `alignas(T) unsigned char storage_[sizeof(T)]` 使用 `alignas` 确保存储区满足 `T` 的对齐要求——这是 placement new 工作的前提
> 2. `construct()` 中的 placement new 在已对齐的 storage 上原地构造 `T`——不分配堆内存
> 3. `destroy()` 显式调用析构函数——placement new 的对象必须手动析构
> 4. `has_value_` 跟踪状态（`std::optional` 内部用 `bool` 或用空指针优化）
> 5. `reinterpret_cast<T*>(storage_)` 是安全地将存储区视为 `T*` 的标准方式（`storage_` 的对齐和大小已经通过 `alignas` 和 `sizeof` 保证）

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- [cppreference — Placement new](https://en.cppreference.com/w/cpp/language/new#Placement_new)
- [cppreference — std::align](https://en.cppreference.com/w/cpp/memory/align)
- [cppreference — std::construct_at](https://en.cppreference.com/w/cpp/memory/construct_at)
- 关联深度探索: [[../../deep-dives/placement-new-aligned-allocation|Placement New 与对齐分配 深度剖析]]
- 《Game Engine Architecture》第 5 章：自定义分配器

---

## 常见陷阱

- **陷阱 1: placement new 后不手动析构。** 没有 "placement delete" 会自动调用。如果忘记 `p->~T()`，析构函数不会执行 → 资源泄漏。
- **陷阱 2: `alignas` 缓冲但忘了 `#include <new>`。** placement new 的 `operator new(size_t, void*)` 定义在 `<new>` 中。如果不包含，某些编译器可能找不到。
- **陷阱 3: 用 `delete p` 释放 placement new 的对象。** `delete` 会再次调用 `operator delete` 释放内存——但这块内存不是你从堆申请的 → 双重释放或堆损坏。
- **陷阱 4: `std::align` 后忘记更新 `space`。** `std::align` 会同时修改 `ptr`（对齐后的地址）和 `space`（剩余空间）。如果你只读 `ptr` 但用原来的缓冲区边界，后续分配可能越界。
