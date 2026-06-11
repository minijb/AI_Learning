---
title: "struct 与数组的内存布局"
updated: 2026-06-08
---

> 所属计划: [[plan|C++ 内存模型]]
> 预计耗时: 50 分钟
> 前置知识: [[01-byte-word-and-memory-basics|字节、字、地址与整数内存表示]]

---

## 1. 概念讲解

### 为什么需要这个？

`struct` 是 C++ 中所有复合类型的基础。引擎中的顶点格式、网络协议包头、配置文件解析都重度依赖 `struct`。
不了解 `struct` 的内存布局，你会：
- 浪费 30% 的内存在对齐填充上
- 写出无法正确网络传输的结构体
- 误以为 `memcmp` 能比较两个 `struct`
- 手动序列化时把 padding 字节当成有效数据写入磁盘

### 核心思想

**`struct` 的内存 = 成员的内存按声明顺序拼接，中间插入 padding。**

编译器插入 padding 的规则很简单：
1. 每个成员的起始地址必须是该成员 `alignof` 的整数倍
2. 整个 `struct` 的 `sizeof` 必须是其最严格对齐成员 `alignof` 的整数倍（尾部填充）

> [!tip] 类比
> 想象搬家时把家具装进货柜。大件家具（double，8 字节对齐）不能从任意位置开始放——必须从货柜的 8 的倍数位置开始。如果前一件家具占用了 3 字节，下一件 8 字节家具就得空 5 字节再开始。装完后，为了下次搬家方便，整柜子的总长度也得是最大件家具宽度的整数倍。

---

## 2. 代码示例

```cpp
#include <cstddef>
#include <cstdint>
#include <iostream>

// --- 基础 struct 布局分析 ---
struct BadLayout {
    char  a;     // 1 byte
    double b;    // 8 byte, align 8
    char  c;     // 1 byte
};

struct GoodLayout {
    double b;    // 8 byte
    char   a;    // 1 byte
    char   c;    // 1 byte
};

// 手动控制对齐：#pragma pack
#pragma pack(push, 1)
struct Packed {
    char   a;
    double b;
    char   c;
};
#pragma pack(pop)

// --- 数组布局 ---
struct Vec3 {
    float x, y, z;
};

// --- 内存可视化工具 ---
template <typename T>
void dump_layout(const char* name) {
    std::cout << "\n=== " << name << " ===\n";
    std::cout << "sizeof  = " << sizeof(T) << "\n";
    std::cout << "alignof = " << alignof(T) << "\n";
}

int main() {
    dump_layout<BadLayout>("BadLayout [char; double; char]");
    dump_layout<GoodLayout>("GoodLayout [double; char; char]");
    dump_layout<Packed>("Packed #pragma pack(1)");

    // 手动验证内部偏移
    std::cout << "\n--- BadLayout member offsets ---\n";
    std::cout << "offsetof(a) = " << offsetof(BadLayout, a) << "\n";
    std::cout << "offsetof(b) = " << offsetof(BadLayout, b) << "\n";
    std::cout << "offsetof(c) = " << offsetof(BadLayout, c) << "\n";

    // 数组的连续性
    std::cout << "\n--- Vec3 数组连续性 ---\n";
    Vec3 verts[3] = {{1,0,0}, {0,1,0}, {0,0,1}};
    std::cout << "sizeof(Vec3[3]) = " << sizeof(verts) << "\n";
    std::cout << "&verts[1].x - &verts[0].x = "
              << (&verts[1].x - &verts[0].x) << " floats (= "
              << (&verts[1].x - &verts[0].x) * sizeof(float) << " bytes)\n";
    // 差值应该是 3（Vec3 有 3 个 float），即连续紧密排列

    // 验证数组是紧密排列的：没有元素间的 padding
    static_assert(sizeof(Vec3) == 12, "Vec3 should be tightly packed");

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -o struct_layout struct_layout.cpp && ./struct_layout
```

**预期输出 (x86-64, gcc/clang/msvc):**
```text
=== BadLayout [char; double; char] ===
sizeof  = 24
alignof = 8

=== GoodLayout [double; char; char] ===
sizeof  = 16
alignof = 8

=== Packed #pragma pack(1) ===
sizeof  = 10
alignof = 1

--- BadLayout member offsets ---
offsetof(a) = 0
offsetof(b) = 8
offsetof(c) = 16

--- Vec3 数组连续性 ---
sizeof(Vec3[3]) = 36
&verts[1].x - &verts[0].x = 3 floats (= 12 bytes)
```

> [!info] 布局图
> ```
> BadLayout (24 bytes):
> ┌────────┬────────────────────────┬────────┬────────────────────────┐
> │ a(1B)  │ padding(7B)            │ b(8B)  │ c(1B) + padding(7B)    │
> └────────┴────────────────────────┴────────┴────────────────────────┘
>
> GoodLayout (16 bytes):
> ┌────────────────────────┬────────┬────────┬────────────────────────┐
> │ b(8B)                  │ a(1B)  │ c(1B)  │ padding(6B)            │
> └────────────────────────┴────────┴────────┴────────────────────────┘
>
> Packed (10 bytes, 无 padding):
> ┌────────┬────────────────────────┬────────┐
> │ a(1B)  │ b(8B)                  │ c(1B)  │
> └────────┴────────────────────────┴────────┘
> ```

---

## 3. 练习

### 练习 1: 重排优化
给定以下 `struct`，不动 `#pragma pack`、不动成员类型，只改变声明顺序，让 `sizeof` 最小化：
```cpp
struct Messy {
    char   a;
    int    b;
    char   c;
    double d;
    char   e;
};
```
写出优化后的顺序，并计算 `sizeof(Optimized)`。

### 练习 2: `memcmp` 陷阱
```cpp
struct S { char a; int b; };
S s1 = {'x', 42};
S s2 = {'x', 42};
if (memcmp(&s1, &s2, sizeof(S)) == 0) {
    std::cout << "equal\n";
}
```
这段代码在某些情况下会输出 "not equal"。解释原因，并写出正确的比较方式。

### 练习 3: 手动序列化（可选）
为一个 `struct Vertex { float pos[3]; uint32_t color; float uv[2]; }` 写一个 `serialize()` 函数，将其写入 `std::vector<uint8_t>`，保证结果不包含 padding 字节。再写一个 `deserialize()` 从字节流还原。注意处理大小端问题。

---
## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 重排规则：按对齐要求从大到小排列成员，减少 padding。
>
> - `double d`：alignof=8，需求最大，放最前
> - `int b`：alignof=4，紧接其后（offset 8，恰好是 4 的倍数）
> - `char a, c, e`：alignof=1，放最后，三个 char 连续占用 3 字节
> - 尾部需填充到 8 的倍数 → +5 字节 padding
>
> ```cpp
> struct Optimized {
>     double d;   // offset 0, 8 bytes
>     int    b;   // offset 8, 4 bytes
>     char   a;   // offset 12, 1 byte
>     char   c;   // offset 13, 1 byte
>     char   e;   // offset 14, 1 byte
>     // padding: 1 byte (tail to alignof=8)
> };
> ```
>
> `sizeof(Optimized) = 16`（8 + 4 + 3 + 1 tail padding）。
>
> 对比原始 `Messy`：`char a(1) + pad(3) + int b(4) + char c(1) + pad(3) + double d(8) + char e(1) + pad(7) = 28`。节省 12 字节（43%）。

> [!tip]- 练习 2 参考答案
> **原因：padding 字节的值是未定义的。**
>
> `struct S { char a; int b; }` 中，`char a` 之后有 3 字节 padding（因为 `int` 必须对齐到 4 的倍数）。`s1` 和 `s2` 是栈上的局部变量，这 3 字节 padding 可能包含栈上的残留值（垃圾数据）。即使 `s1.a == s2.a == 'x'` 且 `s1.b == s2.b == 42`，`memcmp` 会逐字节比较包括 padding 在内的全部 8 字节——padding 不同 → "not equal"。
>
> **正确做法：**
> ```cpp
> // 方案 1：逐字段比较（最安全，推荐）
> bool equal = (s1.a == s2.a) && (s1.b == s2.b);
>
> // 方案 2：memset 清零后再赋值，然后 memcmp
> S s1{}, s2{};  // 值初始化把 padding 也清零
> s1.a = 'x'; s1.b = 42;
> s2.a = 'x'; s2.b = 42;
> // 现在 memcmp(&s1, &s2, sizeof(S)) == 0 是安全的
>
> // 方案 3（C++20）：默认 operator== 对平凡类型也安全
> bool equal = (s1 == s2);  // 编译器生成的逐字段比较
> ```

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <cstdint>
> #include <vector>
> #include <cstring>
>
> struct Vertex {
>     float pos[3];
>     uint32_t color;
>     float uv[2];
> };
>
> // 序列化：逐字段写入，不写入 padding
> std::vector<uint8_t> serialize(const Vertex& v) {
>     // sizeof(Vertex) = 12 + 4 + 8 = 24，无 padding（所有成员自然对齐）
>     // 但为健壮性，不依赖 sizeof，显式逐字段写入
>     std::vector<uint8_t> buf;
>     buf.resize(sizeof(v.pos) + sizeof(v.color) + sizeof(v.uv));
>
>     uint8_t* dst = buf.data();
>     memcpy(dst, v.pos, sizeof(v.pos));              dst += sizeof(v.pos);
>     memcpy(dst, &v.color, sizeof(v.color));         dst += sizeof(v.color);
>     memcpy(dst, v.uv, sizeof(v.uv));
>
>     return buf;
> }
>
> Vertex deserialize(const uint8_t* data, size_t len) {
>     const size_t expected = sizeof(float)*3 + sizeof(uint32_t) + sizeof(float)*2;
>     // 实际生产中应检查 len >= expected
>     Vertex v;
>     const uint8_t* src = data;
>     memcpy(v.pos, src, sizeof(v.pos));              src += sizeof(v.pos);
>     memcpy(&v.color, src, sizeof(v.color));         src += sizeof(v.color);
>     memcpy(v.uv, src, sizeof(v.uv));
>     return v;
> }
> ```
>
> **大小端处理：** 以上代码未处理大小端——`color` 字段在不同端序机器上字节顺序不同。解决方案：序列化时用 `htonl`/`htons` 将多字节整数转为网络字节序（大端），反序列化时用 `ntohl`/`ntohs` 转回本地序。浮点数可先用 `memcpy` 转 `uint32_t` 再处理，或约定使用 IEEE 754 并处理端序。更好的做法是使用 Protobuf 或 FlatBuffers——它们已内置处理端序和对齐。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。


## 4. 扩展阅读

- [cppreference — Alignment](https://en.cppreference.com/w/cpp/language/object#Alignment)
- [Microsoft: `offsetof` macro](https://learn.microsoft.com/en-us/cpp/cpp/offsefof-macro)
- [Google: Protocol Buffers — why padding matters](https://protobuf.dev/programming-guides/dos-donts/)
- 《Game Engine Architecture》第 14 章：引擎中的内存布局

---

## 常见陷阱

- **陷阱 1: `memcmp` 比较 struct。** padding 字节的值是未定义的。两个逻辑相等的 struct 可能在 padding 区域有垃圾值。正确做法：逐字段比较，或使用 `memcmp` 前把 struct 用 `memset` 清零。
- **陷阱 2: `#pragma pack` 用于网络传输后就完事。** 打包会降低访问效率（未对齐访问有性能惩罚），而且某些类型的未对齐访问本身就是 UB（如 `double` 在 ARM 上）。方案：传输时用紧凑格式，加载时手动解压到对齐的本地 struct。
- **陷阱 3: 以为数组元素之间没有 padding。** 数组元素之间**绝对没有**padding。标准保证 `sizeof(T[N]) == N * sizeof(T)`。但如果 `T` 内部有 padding，那数组中每个元素都携带这些 padding。
- **陷阱 4: 跨平台忽略对齐差异。** x86-64 上 `long double` 是 16 字节，ARM64 上可能是 8 或 16。跨平台 struct 的大小和布局可能完全不同。序列化时必须显式指定对齐和大小。
