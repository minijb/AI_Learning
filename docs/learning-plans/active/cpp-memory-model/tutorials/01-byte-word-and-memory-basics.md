---
title: "字节、字、地址与整数内存表示"
updated: 2026-06-08
---

> 所属计划: [[plan|C++ 内存模型]]
> 预计耗时: 45 分钟
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要这个？

C++ 是极少数让你直接和内存对话的主流语言。不了解"内存到底长什么样"，你写的代码就是在黑箱里操作。
当你遇到这些问题时：
- 为什么 `sizeof(bool)` 是 1，但 `std::vector<bool>` 却按位压缩？
- 为什么交换两个 `struct` 成员的顺序会改变 `sizeof`？
- 为什么 `reinterpret_cast` 有时"能跑"，有时是 UB？

答案都在这节。

### 核心思想

**内存 = 一长排信箱。** 每个信箱有编号（地址），内部只能放固定大小的东西（`char` = 1 字节）。CPU 不给单个 bit 编址——最小单位是字节。

但 CPU 读取内存不是逐个信箱（字节）的，而是按"捆"读：
- `int` 是 4 字节一捆
- `double` 是 8 字节一捆
- `__m128` (SIMD) 是 16 字节一捆

如果一捆东西没有按"捆的边界"对齐（比如 `int` 没放在 4 的倍数地址上），有些 CPU 直接崩溃（`SIGBUS`），有些 CPU 用额外周期拼接读取。这就是**对齐**。

> [!tip] 类比
> 想象超市的货架，每个格子宽 4 厘米。你有一盒 4 厘米宽的商品。如果盒子恰好放在一个格子里，拿一下就好。如果盒子跨了两个格子（从格子 3 的后 2cm 到格子 4 的前 2cm），你必须先拿格子 3 的一半、再拿格子 4 的一半，在手里拼好。有些货架（CPU 架构）根本不支持这种操作。

---

## 2. 代码示例

```cpp
#include <cstdint>
#include <cstddef>
#include <iostream>
#include <type_traits>

int main() {
    // --- 基础类型的大小与对齐 ---
    std::cout << "=== Sizes & Alignments ===\n";
    std::cout << "char:   sz=" << sizeof(char)   
              << " align=" << alignof(char)   << "\n";
    std::cout << "short:  sz=" << sizeof(short)
              << " align=" << alignof(short)  << "\n";
    std::cout << "int:    sz=" << sizeof(int)
              << " align=" << alignof(int)    << "\n";
    std::cout << "float:  sz=" << sizeof(float)
              << " align=" << alignof(float)  << "\n";
    std::cout << "double: sz=" << sizeof(double)
              << " align=" << alignof(double) << "\n";
    std::cout << "void*:  sz=" << sizeof(void*)
              << " align=" << alignof(void*)  << "\n";

    // --- 指针与地址 ---
    std::cout << "\n=== Pointer Arithmetic ===\n";
    int arr[4] = {10, 20, 30, 40};
    int* p = arr;
    std::cout << "arr[0] addr = " << static_cast<void*>(p)     << " val=" << *p << "\n";
    std::cout << "arr[1] addr = " << static_cast<void*>(p + 1) << " val=" << *(p + 1) << "\n";
    // p + 1 不是地址 +1，而是 + sizeof(int)！

    // --- 整数的内存表示 ---
    std::cout << "\n=== Integer Memory Representation ===\n";
    int32_t a = 0x1234ABCD;
    uint8_t* bytes = reinterpret_cast<uint8_t*>(&a);
    std::cout << "int32_t 0x" << std::hex << a << std::dec
              << " bytes (little-endian): ";
    for (int i = 0; i < 4; ++i) {
        std::cout << std::hex << static_cast<int>(bytes[i]) << " ";
    }
    std::cout << "\n";
    // 小端: 低字节存低地址。输出通常是: cd ab 34 12

    // --- 位域的内存表示 ---
    std::cout << "\n=== Bit-fields ===\n";
    struct Flags {
        uint8_t a : 4;  // 4 bits
        uint8_t b : 2;  // 2 bits
        uint8_t c : 2;  // 2 bits
    };
    Flags f{3, 2, 1};
    std::cout << "sizeof(Flags) = " << sizeof(Flags) << "\n";
    uint8_t* raw = reinterpret_cast<uint8_t*>(&f);
    std::cout << "Raw byte value: " << static_cast<int>(*raw) << "\n";
    // 二进制: c(2b) b(2b) a(4b) = 01 10 0011 = 0x63 (取决于实现细节)

    return 0;
}
```

**运行方式:**
```bash
# Linux/macOS
g++ -std=c++17 -o mem_basics mem_basics.cpp && ./mem_basics

# Windows MSVC
cl /std:c++17 /EHsc mem_basics.cpp && mem_basics.exe
```

**预期输出:**
```text
=== Sizes & Alignments ===
char:   sz=1 align=1
short:  sz=2 align=2
int:    sz=4 align=4
float:  sz=4 align=4
double: sz=8 align=8
void*:  sz=8 align=8

=== Pointer Arithmetic ===
arr[0] addr = 0x7ffd... val=10
arr[1] addr = 0x7ffd... val=20
  (差值 = 4 字节 = sizeof(int))

=== Integer Memory Representation ===
int32_t 0x1234abcd bytes (little-endian): cd ab 34 12

=== Bit-fields ===
sizeof(Flags) = 1
Raw byte value: 99   // 0x63，可能因编译器而异
```

---

## 3. 练习

### 练习 1: 大小端检测器
写一个程序，不依赖于编译器预定义宏，仅靠类型转换检测当前机器是大端（big-endian）还是小端（little-endian）。要求输出 "little-endian" 或 "big-endian"。

### 练习 2: 手动 `memcpy`
写一个 `void my_memcpy(void* dst, const void* src, size_t n)`，只使用 `char*` 逐字节拷贝，不使用标准库的 `memcpy`。然后用它来拷贝一个 `int` 数组，验证结果正确。

### 练习 3: 位域布局实验（可选）
定义两个不同的位域 `struct：
```cpp
struct A { uint32_t a:4, b:4, c:8, d:16; };
struct B { uint32_t a:16, b:8, c:4, d:4; };
```
用 `static_assert` 断言两者的大小。然后用 `reinterpret_cast` 查看它们的原始字节序列，解释为什么会有区别。

---

## 4. 扩展阅读

- [cppreference — Memory model](https://en.cppreference.com/w/cpp/language/memory_model)
- [cppreference — Object](https://en.cppreference.com/w/cpp/language/object)
- [IBM: Endianness explained](https://developer.ibm.com/articles/au-endianc/)
- 《深入理解计算机系统》第 3 章：程序的机器级表示

---

## 常见陷阱

- **陷阱 1: 认为 `sizeof(char) == 1` 意味着 char 只有 8 位。** C 标准只保证 `char` 至少 8 位，实际上绝大多数平台是 8 位。`CHAR_BIT` (from `<climits>`) 告诉你具体值。
- **陷阱 2: 用 `void*` 做指针算术。** `void*` 不支持 `+1` 运算——你不知道步长是多少。先转成 `char*` 或 `uint8_t*`。
- **陷阱 3: 位域的跨平台假设。** 位域的内存布局是**实现定义的**（implementation-defined）：分配方向（最低位优先还是最高位优先）、是否跨字边界、填充行为都因编译器而异。不要把位域用于跨平台二进制协议。
