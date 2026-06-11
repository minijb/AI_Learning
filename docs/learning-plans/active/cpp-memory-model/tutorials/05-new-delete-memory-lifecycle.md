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

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **编译器调用带 `align_val_t` 版本的时机：**
>
> 当类型的对齐要求超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（通常是 `alignof(std::max_align_t)`，在 x86-64 上为 16）时，编译器自动选择对齐感知的 `operator new` 重载。例如：`alignas(64)` 的类型 → `operator new(size, align_val_t{64})`。
>
> ```cpp
> #include <cstddef>
> #include <cstdlib>
> #include <iostream>
> #include <new>
>
> // 对齐感知的 operator new（C++17）
> void* operator new(std::size_t size, std::align_val_t al) {
>     std::cout << "[aligned new] size=" << size
>               << " align=" << static_cast<std::size_t>(al) << "\n";
>     void* p = std::aligned_alloc(static_cast<std::size_t>(al), size);
>     if (!p) throw std::bad_alloc{};
>     return p;
> }
>
> void operator delete(void* p, std::align_val_t al) noexcept {
>     std::cout << "[aligned delete] align="
>               << static_cast<std::size_t>(al) << "\n";
>     std::free(p);
> }
>
> // 也需重载普通版本（否则非对齐的 new 会找不到）
> void* operator new(std::size_t size) {
>     std::cout << "[normal new] size=" << size << "\n";
>     void* p = std::malloc(size);
>     if (!p) throw std::bad_alloc{};
>     return p;
> }
> void operator delete(void* p) noexcept {
>     std::cout << "[normal delete]\n";
>     std::free(p);
> }
>
> struct alignas(64) OverAligned {
>     int data[16];
> };
>
> struct Normal {
>     int data[4];
> };
>
> int main() {
>     std::cout << "alignof(OverAligned) = "
>               << alignof(OverAligned) << "\n";
>     auto* oa = new OverAligned{};
>     delete oa;
>
>     std::cout << "alignof(Normal) = "
>               << alignof(Normal) << "\n";
>     auto* n = new Normal{};
>     delete n;
>     return 0;
> }
> ```
>
> **输出示例：**
> ```
> alignof(OverAligned) = 64
> [aligned new] size=64 align=64
> [aligned delete] align=64
> alignof(Normal) = 4
> [normal new] size=16
> [normal delete]
> ```
>
> **关键点：** 触发条件 = `alignof(T) > alignof(std::max_align_t)`。这是 C++17 引入的核心特性——在此之前，`new` 无法保证超对齐类型的对象分配在正确的对齐边界上。

> [!tip]- 练习 2 参考答案
> **第一段代码（`operator new` + `operator delete`）（只分配/释放内存）：**
> - 只获取了一块 `sizeof(int) * 10` 字节的原始内存
> - **没有调用任何 `int` 的构造函数** → 这片内存中的 `int` 对象从未开始它们的生命周期
> - 读取 `raw` 指向的内存是 UB（对象不存在）
> - `operator delete` **不调用析构函数**，只归还内存
>
> **对比 `int* p = new int[10]; delete[] p;`：**
> - `new int[10]` 做了两件事：(1) 调用 `operator new[]` 分配 40 字节，(2) 对 10 个 `int` 调用默认构造函数（对 `int` 来说是不做任何事的 trivial 构造，但标准说对象生命周期开始了）
> - `delete[] p` 也做两件事：(1) 对 10 个 `int` 调用析构函数（trivial，无操作），(2) 调用 `operator delete[]` 释放内存
>
> **反过来——先 `new int[10]` 再 `operator delete(p)`：**
> - `new int[10]` 让 10 个 `int` 对象的生命周期开始
> - `operator delete(p)` 只释放内存，**不调用析构函数**
> - 对 `int` 这没问题（析构函数是 trivial 的），所以"碰巧"正确
> - 但对非平凡类型后果严重：析构函数被跳过 → 资源泄漏/UB
> - 更危险的是：`operator delete` 接收的地址必须和 `operator new` 返回的地址**完全相同**。`new[]` 对非平凡类型可能存储 cookie 在返回指针之前，`operator delete(p)` 接收的是用户指针而非 `operator new` 返回的原始块地址 → 堆损坏
>
> **总结：永远配对使用。** `new` ↔ `delete`，`new[]` ↔ `delete[]`，`operator new` ↔ `operator delete`。混搭是 UB，即使看起来"能跑"。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // leak_tracker.h —— 轻量级内存泄漏追踪器
> #pragma once
> #include <cstddef>
> #include <cstdlib>
> #include <cstring>
> #include <cstdio>
>
> namespace leak_tracker {
>
> struct AllocEntry {
>     const char* file;
>     int         line;
>     size_t      size;
>     AllocEntry* next;
> };
>
> static AllocEntry* g_head = nullptr;
>
> // 链表头插法：每次分配插入一个追踪节点
> inline void track_alloc(void* ptr, size_t size, const char* file, int line) {
>     // 将追踪信息存储到分配的内存之前
>     auto* entry = static_cast<AllocEntry*>(ptr);
>     entry->file = file;
>     entry->line = line;
>     entry->size = size;
>     entry->next = g_head;
>     g_head = entry;
> }
>
> inline void track_free(void* ptr) {
>     // 从链表中移除
>     auto* entry = static_cast<AllocEntry*>(ptr);
>     if (g_head == entry) {
>         g_head = entry->next;
>     } else {
>         for (auto* p = g_head; p; p = p->next) {
>             if (p->next == entry) {
>                 p->next = entry->next;
>                 break;
>             }
>         }
>     }
> }
>
> inline void report_leaks() {
>     if (!g_head) {
>         std::printf("[leak_tracker] No leaks detected.\n");
>         return;
>     }
>     std::printf("[leak_tracker] === LEAKS DETECTED ===\n");
>     size_t total = 0;
>     for (auto* p = g_head; p; p = p->next) {
>         std::printf("  %s:%d: %zu bytes (addr=%p)\n",
>                     p->file, p->line, p->size,
>                     static_cast<char*>(static_cast<void*>(p)) + sizeof(AllocEntry));
>         total += p->size;
>     }
>     std::printf("[leak_tracker] Total: %zu bytes in %zu blocks.\n", total, /* count omitted for brevity */ size_t{});
> }
>
> } // namespace leak_tracker
>
> // 重载 operator new：在用户请求的 size 之前分配追踪头
> void* operator new(std::size_t size, const char* file, int line) {
>     // 分配: [AllocEntry header][user data]
>     void* raw = std::malloc(sizeof(leak_tracker::AllocEntry) + size);
>     if (!raw) throw std::bad_alloc{};
>     leak_tracker::track_alloc(raw, size, file, line);
>     return static_cast<char*>(raw) + sizeof(leak_tracker::AllocEntry);
> }
>
> void* operator new[](std::size_t size, const char* file, int line) {
>     return operator new(size, file, line);
> }
>
> void operator delete(void* ptr) noexcept {
>     if (!ptr) return;
>     void* raw = static_cast<char*>(ptr) - sizeof(leak_tracker::AllocEntry);
>     leak_tracker::track_free(raw);
>     std::free(raw);
> }
>
> void operator delete[](void* ptr) noexcept {
>     operator delete(ptr);
> }
>
> // 宏：在调用处捕获 __FILE__ 和 __LINE__
> #define TRACK_NEW new(__FILE__, __LINE__)
>
> // 自动注册退出时报告
> namespace {
>     struct AutoReporter { ~AutoReporter() { leak_tracker::report_leaks(); } };
>     AutoReporter g_reporter;
> }
> ```
>
> **使用方式：** 在所有 `.cpp` 文件中 `#include "leak_tracker.h"`，用 `TRACK_NEW` 替代 `new`（例如 `auto* p = TRACK_NEW int[10];`），用普通 `delete` 释放。程序退出时自动打印未释放的块。
>
> **局限性（为什么实际中用 ASan/Valgrind）：**
> - 只追踪通过 `TRACK_NEW` 的分配，不追踪 `malloc`/`new`（无文件行号的 `new`）
> - 重载 `operator delete` 影响了全局，但未重载 `operator delete(void*, size_t)` 的 sized-deallocation 版本
> - 不处理 `std::nothrow` 版本、`align_val_t` 版本
> - 线程安全需要加锁（本简化版未加）
> - 实际生产代码应使用 AddressSanitizer (`-fsanitize=address`) 或 Valgrind

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

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
