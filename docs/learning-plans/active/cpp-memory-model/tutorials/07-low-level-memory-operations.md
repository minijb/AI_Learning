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

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> #include <cstring>
> #include <new>
> #include <type_traits>
>
> template<typename T>
> void uninitialized_construct_n(T* dst, size_t n) {
>     if constexpr (std::is_trivially_default_constructible_v<T>) {
>         // 平凡类型：无需逐个构造，memset 到 0 是安全且高效的
>         // （标准保证：全零字节是合法值 0/nullptr/0.0f）
>         std::memset(dst, 0, n * sizeof(T));
>     } else {
>         // 非平凡类型：逐个默认构造，异常安全
>         size_t constructed = 0;
>         try {
>             for (; constructed < n; ++constructed) {
>                 ::new (static_cast<void*>(dst + constructed)) T{};
>             }
>         } catch (...) {
>             // 回滚：析构已构造的对象
>             for (size_t j = 0; j < constructed; ++j) {
>                 dst[j].~T();
>             }
>             throw;  // 重新抛出
>         }
>     }
> }
>
> // 测试用例
> #include <iostream>
> #include <string>
>
> struct Counter {
>     static int alive;
>     int id;
>     Counter() : id(++alive) { std::cout << "Counter(" << id << ")\n"; }
>     ~Counter() { std::cout << "~Counter(" << id << ")\n"; --alive; }
> };
> int Counter::alive = 0;
>
> struct ThrowOn3 {
>     ThrowOn3() {
>         static int count = 0;
>         if (++count == 3) throw std::runtime_error("构造失败在第 3 个");
>     }
>     ~ThrowOn3() = default;
> };
>
> int main() {
>     // 测试 1：平凡类型 (int) —— memset 优化
>     int ints[5];
>     uninitialized_construct_n(ints, 5);
>     std::cout << "int test: " << ints[0] << " " << ints[4] << "\n";
>
>     // 测试 2：非平凡类型 —— 逐个构造
>     alignas(Counter) char buf[3 * sizeof(Counter)];
>     auto* counters = reinterpret_cast<Counter*>(buf);
>     uninitialized_construct_n(counters, 3);
>     for (size_t i = 0; i < 3; ++i) counters[i].~Counter();
>
>     // 测试 3：异常安全
>     try {
>         alignas(ThrowOn3) char buf2[5 * sizeof(ThrowOn3)];
>         auto* t = reinterpret_cast<ThrowOn3*>(buf2);
>         uninitialized_construct_n(t, 5);
>     } catch (const std::exception& e) {
>         std::cout << "Caught: " << e.what() << "\n";
>         std::cout << "异常安全：前 2 个对象已被正确析构\n";
>     }
>     return 0;
> }
> ```
>
> **关键设计：**
> - `if constexpr` 使两个分支在编译期分离——平凡类型路径完全不生成循环代码（仅一个 `memset`），非平凡类型路径走逐构造历
> - `constructed` 计数器实现异常安全：try 块中跟踪已构造数量，catch 中回滚析构
> - Placement new `::new (dst + i) T{}` 在预分配的未初始化内存上构造——注意 `dst + i` 不需要 `void*` 转换，编译器能正确计算偏移
> - 这不是标准库的 `std::uninitialized_default_construct_n`（C++17），但展示了其实现原理

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <cstdint>
> #include <cstddef>
> #include <cstring>
> #include <iostream>
>
> // 判断两个字节范围是否重叠
> bool ranges_overlap(const void* a, size_t a_len,
>                     const void* b, size_t b_len) {
>     auto a_start = reinterpret_cast<uintptr_t>(a);
>     auto a_end   = a_start + a_len;
>     auto b_start = reinterpret_cast<uintptr_t>(b);
>     auto b_end   = b_start + b_len;
>
>     // 重叠当且仅当一个范围的起始在另一个范围内
>     // 公式：[a_start, a_end) 和 [b_start, b_end) 重叠 ⇔ a_start < b_end && b_start < a_end
>     return (a_start < b_end) && (b_start < a_end);
> }
>
> // 安全版 memcpy：检测重叠就降级为 memmove
> void* safe_memcpy(void* dst, const void* src, size_t n) {
>     if (ranges_overlap(dst, n, src, n)) {
>         std::cout << "[safe_memcpy] overlap detected, using memmove\n";
>         return std::memmove(dst, src, n);
>     }
>     return std::memcpy(dst, src, n);
> }
>
> // 测试
> int main() {
>     // 测试 1：不重叠
>     char a[10] = "hello";
>     char b[10] = {};
>     safe_memcpy(b, a, 6);
>     std::cout << "non-overlap: " << b << "\n";
>
>     // 测试 2：重叠
>     char c[20] = "0123456789";
>     safe_memcpy(c + 3, c, 5);
>     std::cout << "overlap: " << c << "\n";
>     // 预期：0120123456789
>
>     // 测试 3：完全不重叠的边界情况
>     char d[20] = "abcdef";
>     // d 和 d+6 不重叠（起始地址差 6 >= 复制长度 5）
>     safe_memcpy(d + 6, d, 5);
>     std::cout << "adjacent: " << d << "\n";
>     // 预期：abcdefabcde
>
>     return 0;
> }
> ```
>
> **重叠判断的数学原理：** 两个区间 `[s1, e1)` 和 `[s2, e2)` 重叠 ⇔ `s1 < e2 && s2 < e1`。这是两个排序条件的等价表达：一个区间的起点小于另一个的终点**且**反之亦然。注意这里使用的是半开区间 `[start, start + len)`。
>
> **为什么 `safe_memcpy` 不是标准做法：** 标准库设计上就区分了重叠（`memmove`）和非重叠（`memcpy`）场景。99% 的使用场景中开发者**知道**是否重叠。运行时检测增加了分支开销，而 memcpy 的热路径通常需要最高性能。更好的做法是用 `memmove` 当你不确定，用 `memcpy` 当你确定不重叠——两者语义的对立本身就是最强的静态保证。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <cstdint>
> #include <vector>
> #include <cstring>
> #include <iostream>
>
> struct Packet {
>     uint32_t type;
>     uint32_t len;
>     float    data[4];
> };
>
> // 发送端：序列化到字节流
> std::vector<uint8_t> serialize_packet(const Packet& pkt) {
>     // 大小：type(4) + len(4) + data(16) = 24 bytes
>     // 注意：此 Packet 无 padding（所有成员自然对齐: 4,4,4）
>     std::vector<uint8_t> buf(sizeof(Packet));
>     std::memcpy(buf.data(), &pkt, sizeof(Packet));
>     return buf;
> }
>
> // 接收端：从字节流还原
> Packet deserialize_packet(const uint8_t* data, size_t len) {
>     if (len < sizeof(Packet)) {
>         throw std::runtime_error("buffer too small");
>     }
>     Packet pkt;
>     std::memcpy(&pkt, data, sizeof(Packet));
>     return pkt;
> }
>
> int main() {
>     Packet original{1, 4, {1.0f, 2.0f, 3.0f, 4.0f}};
>     auto buf = serialize_packet(original);
>
>     std::cout << "buf size: " << buf.size() << " (expected 24)\n";
>     auto restored = deserialize_packet(buf.data(), buf.size());
>
>     std::cout << "type=" << restored.type
>               << " len=" << restored.len
>               << " data[0]=" << restored.data[0] << "\n";
>     return 0;
> }
> ```
>
> **问题分析：**
>
> 1. **对齐：** 本例中 `Packet` 恰好无 padding（所有成员 `uint32_t` 和 `float` 对齐要求都是 4，且布局紧凑）。如果加入 `double` 或 `char`，`memcpy` 会把 padding 字节也写入字节流——浪费空间且暴露未初始化数据
> 2. **大小端：** `memcpy` 逐字节复制，不转换字节序。如果发送端是小端 x86，接收端是大端 ARM → `type` 和 `len` 的字节顺序反转 → 读取到错误值。`float` 同理（IEEE 754 的位模式端序与整数一致）。**解决方案：** 序列化前用 `htonl(type)`, `htonl(len)` 转网络字节序；对 `float` 先 `memcpy` 到 `uint32_t` 再 `htonl`
> 3. **未来兼容性：** 发送端和接收端编译成不同版本的 `Packet`（如增加字段）→ `sizeof(Packet)` 不同 → `memcpy` 读越界或截断。**解决方案：** 使用 Protobuf/FlatBuffers/Cap'n Proto 提供模式演化
> 4. **安全性：** `memcpy` 无边界检查；如果有恶意构造的 `len` 字段声称数据体更大，接收端可能越界读。**解决方案：** 验证 `len` 字段 ≤ 缓冲区剩余大小
>
> **改进方向：** 逐字段序列化 + 端序转换 + 长度验证。实际工程中强烈建议使用成熟序列化框架而非手写 `memcpy` 协议。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

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
