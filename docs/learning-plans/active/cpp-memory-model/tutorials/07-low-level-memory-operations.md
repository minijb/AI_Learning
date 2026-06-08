---
title: "底层内存操作（memcpy 等）"
updated: 2026-06-08
---

> 所属计划: [[plan|C++ 内存模型]]
> 预计耗时: 45 分钟
> 前置知识: [[02-struct-and-array-layout|struct 与数组的内存布局]]

---

## 1. 概念讲解

### 为什么需要这个？

`memcpy`、`memmove`、`memset`、`memcmp` 是以字节为单位操作原始内存的最底层工具。它们无视类型系统——这是它们最强大的地方，也是最危险的地方。

在引擎中你会反复用到它们：ECS 组件数组搬迁、顶点缓冲上传、网络序列化、状态快照比较。但不加区分地使用 `memcpy` 会导致未定义行为（UB）、对象状态损坏、甚至安全漏洞。

### 核心思想

| 函数 | 作用 | 核心约束 | 最适用场景 |
|------|------|---------|-----------|
| `memcpy(dst, src, n)` | 逐字节复制 | `dst` 和 `src` **不能重叠** | 缓冲上传、快照拷贝 |
| `memmove(dst, src, n)` | 逐字节复制 | **允许重叠** | 数组元素前移/后移 |
| `memset(dst, val, n)` | 逐字节填充 | 不调用构造函数 | 清零 POD 缓冲 |
| `memcmp(a, b, n)` | 逐字节比较 | padding 可能引入假差异 | 原始字节级校验 |

> [!warning] 关键认知
> `memcpy` 操作的是**字节序列**，不是**C++ 对象**。它不调用构造函数、不调用析构函数、不更新虚表指针、不处理 self-referential 类型。把它用在非平凡对象（non-trivial type）上是 UB。

> [!tip] 类比
> `memcpy` 就像影印机：你把一叠纸原样复印到另一叠纸上。如果纸上有需要"激活"的内容（比如优惠券需要盖章才有效），影印机不会帮你盖章——它只管按像素复制。
>
> `memmove` 是带扫描功能的复印机：源和目标可以重叠，它会智能地决定从前到后还是从后到前复印，保证不覆盖未读数据。

---

## 2. 代码示例

```cpp
#include <cstring>
#include <cstdint>
#include <iostream>
#include <vector>

// --- memcpy vs memmove: 重叠场景 ---
void demo_overlap() {
    std::cout << "=== Overlap handling ===\n";

    char buf1[] = "1234567890";
    char buf2[] = "1234567890";

    // 用 memcpy: src 和 dst 重叠 —— UB！
    // 很多实现上 "能跑"，但不要依赖
    // memcpy(buf1 + 2, buf1, 5);  // ← 危险！

    // 用 memmove: 正确处理重叠
    memmove(buf2 + 2, buf2, 5);
    std::cout << "memmove result: " << buf2 << "\n";
    // 结果: "1212345890" —— [0..4] 先被读到临时区，再写到 [2..6]
}

// --- memset 的局限 ---
void demo_memset_limitations() {
    std::cout << "\n=== memset limitations ===\n";

    // OK: POD 数组清零
    int nums[10];
    memset(nums, 0, sizeof(nums));  // 所有 int 变成 0
    std::cout << "nums[0] = " << nums[0] << " (after memset to 0)\n";

    // 危险！memset 到非零值
    int wrong[10];
    memset(wrong, 1, sizeof(wrong));
    std::cout << "wrong[0] = " << wrong[0] << " (after memset to 1)\n";
    // 不是 1！是每个字节为 0x01 → int = 0x01010101 = 16843009
}

// --- memcpy 不能用于非平凡对象 ---
struct PODPoint { float x, y, z; };  // 平凡类型

struct FancyString {
    char* data_;
    size_t len_;
    FancyString(const char* s) : len_(strlen(s)), data_(new char[len_ + 1]) {
        memcpy(data_, s, len_ + 1);
    }
    ~FancyString() { delete[] data_; }
};

void demo_memcpy_ub() {
    std::cout << "\n=== memcpy with non-trivial types ===\n";

    PODPoint p1 = {1.0f, 2.0f, 3.0f};
    PODPoint p2;
    memcpy(&p2, &p1, sizeof(PODPoint));  // OK: POD
    std::cout << "PODPoint copied: (" << p2.x << ", " << p2.y << ", " << p2.z << ")\n";

    // 下面的代码如果取消注释会崩溃（双重释放）
    // FancyString s1("hello");
    // FancyString s2("world");
    // memcpy(&s2, &s1, sizeof(FancyString));
    // // s2 的 data_ 被覆盖为 s1 的 data_ 指针
    // // s2 原来的 data_ 泄漏了
    // // s1 和 s2 析构时 delete[] 同一个指针 → 双重释放崩溃
}

// --- std::copy vs memcpy ---
void demo_std_copy() {
    std::cout << "\n=== std::copy vs memcpy ===\n";

    std::vector<int> src = {1, 2, 3, 4, 5};
    std::vector<int> dst(5);

    // std::copy: 类型安全，会调用移动/拷贝构造（对非 POD）
    std::copy(src.begin(), src.end(), dst.begin());

    // memcpy: 仅能用于 trivially copyable 类型
    static_assert(std::is_trivially_copyable_v<int>);
    memcpy(dst.data(), src.data(), src.size() * sizeof(int));

    std::cout << "dst = ";
    for (auto v : dst) std::cout << v << " ";
    std::cout << "\n";
}

// --- memcmp 和 padding ---
struct WithPadding {
    char a;
    int b;
};

void demo_memcmp_padding() {
    std::cout << "\n=== memcmp and padding ===\n";
    WithPadding s1{'x', 42};
    WithPadding s2{'x', 42};

    // s1 和 s2 逻辑相等，但 memcmp 可能不同（padding 未定义）
    int cmp = memcmp(&s1, &s2, sizeof(WithPadding));
    std::cout << "memcmp result: " << cmp << "\n";
    std::cout << "(0=equal, nonzero=padding differed)\n";

    // 安全的做法：先清零 padding
    memset(&s1, 0, sizeof(s1));
    memset(&s2, 0, sizeof(s2));
    s1.a = 'x'; s1.b = 42;
    s2.a = 'x'; s2.b = 42;
    cmp = memcmp(&s1, &s2, sizeof(WithPadding));
    std::cout << "After zero-init memcmp: " << cmp << "\n";
}

int main() {
    demo_overlap();
    demo_memset_limitations();
    demo_memcpy_ub();
    demo_std_copy();
    demo_memcmp_padding();
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -o mem_ops mem_ops.cpp && ./mem_ops
```

**预期输出:**
```text
=== Overlap handling ===
memmove result: 1212345890

=== memset limitations ===
nums[0] = 0 (after memset to 0)
wrong[0] = 16843009 (after memset to 1)

=== memcpy with non-trivial types ===
PODPoint copied: (1, 2, 3)

=== std::copy vs memcpy ===
dst = 1 2 3 4 5

=== memcmp and padding ===
memcmp result: -47
(0=equal, nonzero=padding differed)
After zero-init memcmp: 0
```

---

## 3. 练习

### 练习 1: 安全批量构造
实现一个函数模板：
```cpp
template<typename T>
void uninitialized_construct_n(T* dst, size_t n);
```
在 `dst` 指向的未初始化内存上构造 `n` 个默认构造的 `T`。要求：
- 对平凡类型（`std::is_trivially_default_constructible_v<T>`）使用 `memset` 或什么都不做
- 对非平凡类型逐个调用默认构造函数
- 如果某个构造抛异常，已构造的对象必须被正确析构（异常安全）

### 练习 2: 重叠检测
写一个函数 `bool ranges_overlap(const void* a, size_t a_len, const void* b, size_t b_len)`，判断两个字节范围是否重叠。然后用它实现一个安全的 `safe_memcpy`——如果检测到重叠就改用 `memmove`，否则用 `memcpy`。

### 练习 3: 序列化校验（可选）
设计一个简单协议：客户端发送一个 `struct Packet { uint32_t type; uint32_t len; float data[4]; }`。用 `memcpy` 把它写入 `std::vector<uint8_t>` 发送。接收端如何从字节流中还原？这个方案有什么问题（考虑对齐、大小端、padding）？如何改进？

---

## 4. 扩展阅读

- [cppreference — `memcpy`](https://en.cppreference.com/w/c/string/byte/memcpy)
- [cppreference — `memmove`](https://en.cppreference.com/w/c/string/byte/memmove)
- [cppreference — `std::is_trivially_copyable`](https://en.cppreference.com/w/cpp/types/is_trivially_copyable)
- 关联深度探索: [[../../deep-dives/cpp-mem-operations|C++ mem 系列操作 深度剖析]]
- 《Game Engine Architecture》第 5 章：低级内存管理

---

## 常见陷阱

- **陷阱 1: `memcpy` 用于有虚函数的类。** 虚表指针被逐字节复制后，目标对象的虚表和源对象相同（这本身 OK），但如果目标对象原本有虚函数且需要不同的派生类虚表，复制后类型信息就错了。更严重的是：如果目标对象原本不是任何合法对象的位模式，`memcpy` 后成了"看起来像对象的字节"——这是严格别名违规。
- **陷阱 2: `memset(ptr, 0, sizeof(T))` 假设"全零 = 合法对象"。** 对指针和浮点数来说，`0x00000000` 确实是 `nullptr` 和 `0.0f`。但对某些类型（如 `std::string` 的 SSO buffer），全零可能是未定义的内部状态。只对 POD 和显式清零安全的类型使用。
- **陷阱 3: `memcmp` 用于 struct 相等性判断。** padding 字节的值未定义。两个内容相同的 struct 可能在 padding 区域不同。解决方案：逐字段比较，或构造前 `memset` 整个 struct 为零。
- **陷阱 4: 误以为 `memcpy` 对重叠区域是安全的。** 重叠必须使用 `memmove`。GB 级别的数据搬迁中这个 bug 会造成静默的数据损坏。
