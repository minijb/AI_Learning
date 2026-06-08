---
title: "new/delete 与内存生命周期"
updated: 2026-06-08
---

> 所属计划: [[plan|C++ 内存模型]]
> 预计耗时: 50 分钟
> 前置知识: [[03-class-memory-layout|类对象的内存模型]]

---

## 1. 概念讲解

### 为什么需要这个？

`new` 和 `delete` 是 C++ 中最基础的内存操作，但它们的"简单"背后隐藏着两阶段过程：内存获取 + 对象构造。搞混这两个阶段是导致内存泄漏、双重释放、使用了未构造内存的万恶之源。

### 核心思想

**`new T` = `operator new`（分配内存）+ 构造函数（在内存上构造对象）**
**`delete p` = 析构函数（销毁对象）+ `operator delete`（归还内存）**

```mermaid
flowchart TD
    A[new T] --> B[operator new: 分配 sizeof(T) 字节]
    B --> C[构造函数: 初始化对象]
    D[delete p] --> E[析构函数: 清理资源]
    E --> F[operator delete: 归还内存]
```

关键区分：
1. **`new`/`delete` 是表达式** — 不可重载，永远做构造+析构
2. **`operator new`/`operator delete` 是函数** — 可以重载，只做内存分配/释放
3. **`new[]`/`delete[]`** — 处理数组，需要知道元素个数（通常通过在分配的内存前存 cookie）

> [!tip] 类比
> `new` 就像租房子：先找房东（operator new）拿到钥匙（内存地址），然后搬家具进去（构造函数）。`delete` 就是退房：先把家具搬出来（析构函数），再把钥匙还房东（operator delete）。`new[]` 是整层整层租——房东需要在走廊里挂个牌子记录"这层住了几户人家"（cookie），退房时按户数逐户搬家具。

---

## 2. 代码示例

```cpp
#include <cstddef>
#include <cstdlib>
#include <iostream>
#include <new>

// --- 追踪内存分配的自定义 operator new/delete ---
static size_t g_alloc_count = 0;
static size_t g_alloc_bytes = 0;

void* operator new(size_t size) {
    void* p = std::malloc(size);
    if (!p) throw std::bad_alloc{};
    ++g_alloc_count;
    g_alloc_bytes += size;
    std::cout << "[alloc] size=" << size
              << " addr=" << p << " total=" << g_alloc_count << "\n";
    return p;
}

void operator delete(void* p) noexcept {
    std::cout << "[free]  addr=" << p << "\n";
    std::free(p);
}

// 数组版本
void* operator new[](size_t size) {
    return operator new(size);  // 委托给单对象版本
}
void operator delete[](void* p) noexcept {
    operator delete(p);
}

// --- 带析构追踪的类 ---
class Tracked {
    int id_;
public:
    explicit Tracked(int id) : id_(id) {
        std::cout << "  Tracked(" << id_ << ") constructed\n";
    }
    ~Tracked() {
        std::cout << "  Tracked(" << id_ << ") destroyed\n";
    }
};

// --- 含析构函数的类：new[] / delete[] 的 cookie 效应 ---
struct POD { int x; };           // 平凡析构
struct NonPOD { int x; ~NonPOD() {} };

int main() {
    std::cout << "=== Single object ===\n";
    Tracked* t = new Tracked(1);
    delete t;

    std::cout << "\n=== Array of tracked ===\n";
    Tracked* arr = new Tracked[3]{1, 2, 3};
    delete[] arr;

    std::cout << "\n=== Cookie comparison ===\n";
    std::cout << "sizeof(POD)=" << sizeof(POD)
              << ", new POD[3] overhead check:\n";
    POD* podArr = new POD[3];
    std::cout << "  podArr = " << static_cast<void*>(podArr) << "\n";
    delete[] podArr;

    std::cout << "\nsizeof(NonPOD)=" << sizeof(NonPOD)
              << ", new NonPOD[3] overhead check:\n";
    NonPOD* npArr = new NonPOD[3];
    std::cout << "  npArr = " << static_cast<void*>(npArr) << "\n";
    // 如果编译器存储了 cookie，实际分配的地址可能往前偏移
    delete[] npArr;

    std::cout << "\n=== Mismatched new/delete ===\n";
    int* p = new int[5];
    // delete p;   // ← UB! 必须用 delete[]
    delete[] p;     // ← 正确

    std::cout << "\n=== g_alloc summary ===\n";
    std::cout << "count=" << g_alloc_count
              << " bytes=" << g_alloc_bytes << "\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -o new_delete new_delete.cpp && ./new_delete
```

**预期输出:**
```text
=== Single object ===
[alloc] size=4 addr=0x55... total=1
  Tracked(1) constructed
  Tracked(1) destroyed
[free]  addr=0x55...

=== Array of tracked ===
[alloc] size=... addr=0x55... total=2
  Tracked(1) constructed
  Tracked(2) constructed
  Tracked(3) constructed
  Tracked(3) destroyed
  Tracked(2) destroyed
  Tracked(1) destroyed
[free]  addr=0x55...

=== Cookie comparison ===
sizeof(POD)=4, new POD[3] overhead check:
  podArr = 0x55...
sizeof(NonPOD)=4, new NonPOD[3] overhead check:
  npArr = 0x55...
  // 在某些编译器上，NonPOD 数组可能分配更多字节以存储元素个数

=== Mismatched new/delete ===
[alloc] size=20 addr=0x55... total=3
[free]  addr=0x55...

=== g_alloc summary ===
count=3 bytes=...
```

> [!info] 数组 Cookie 机制
> 当类有非平凡析构函数时，编译器需要在 `new[]` 分配的内存前存储元素个数（cookie），这样 `delete[]` 才能调用正确次数的析构函数。对于 POD（平凡析构）数组，编译器不需要 cookie，可能直接调用 `operator delete`（无元素计数）。不同编译器处理不同：MSVC 始终存储 cookie，GCC/Clang 只对有析构函数的类型存储。

---

## 3. 练习

### 练习 1: 四种 `operator new`
```cpp
void* operator new(std::size_t count);
void* operator new[](std::size_t count);
void* operator new(std::size_t count, std::align_val_t al);      // C++17
void* operator new(std::size_t count, std::align_val_t al, std::nothrow_t const&);
```
在什么情况下编译器会调用带 `align_val_t` 的版本？写一个 `alignas(64)` 的 struct，并用自定义 `operator new` 追踪它实际请求的对齐值。

### 练习 2: new/delete 不匹配检测
```cpp
void* raw = operator new(sizeof(int) * 10);  // 只分配内存
// ...
operator delete(raw);  // 只释放内存
```
和 `int* p = new int[10]; delete[] p;` 相比，这段代码有什么区别？如果反过来——先 `new int[10]` 再 `operator delete(p)`——会发生什么？

### 练习 3: 内存泄漏追踪器（可选）
写一个头文件 `leak_tracker.h`，通过重载全局 `operator new`/`delete` 记录每次分配的文件名和行号（使用宏技巧）。在程序退出时打印所有未释放的内存块。不要依赖任何外部库（如 AddressSanitizer），纯标准 C++ 实现。

---

## 4. 扩展阅读

- [cppreference — new expression](https://en.cppreference.com/w/cpp/language/new)
- [cppreference — delete expression](https://en.cppreference.com/w/cpp/language/delete)
- [cppreference — Operator new](https://en.cppreference.com/w/cpp/memory/new/operator_new)
- [Microsoft: new and delete](https://learn.microsoft.com/en-us/cpp/cpp/new-and-delete-operators)
- 《C++ Primer》第 12 章：动态内存

---

## 常见陷阱

- **陷阱 1: `new[]` 配 `delete`（不匹配）。** 对非 POD 类型会导致只调用第一个元素的析构函数，且 `delete` 不知道实际的分配大小。如果有 cookie 机制，`delete` 会把 cookie 当成对象的一部分析构 → 崩溃或损坏堆。
- **陷阱 2: `delete` 多次调用。** `delete p;` 后 `p` 变成悬垂指针，再次 `delete p` 是双重释放（double-free），属于 UB。防御：delete 后立即 `p = nullptr;`（但只能防你自己代码中的 `if (p) delete p;`）。
- **陷阱 3: 用 `malloc` 配 `delete`，或用 `new` 配 `free`。** C 的 `malloc`/`free` 对和 C++ 的 `new`/`delete` 对使用不同的堆管理器（在大多数实现中其实是相同的，但不要依赖这一点）。更重要的是：`new` 会调用构造函数，`free` 不会调用析构函数。
- **陷阱 4: 在构造函数中抛异常后忘记处理已分配资源。** 如果构造函数中 `new` 了资源 A，然后在 `new` 资源 B 时抛异常，资源 A 泄漏。解决方案：RAII（用 `unique_ptr` 管理中间资源），或者构造函数函数据体中的每个 `new` 都要对应一个析构或异常安全处理。
