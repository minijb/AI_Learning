# 对象生命周期与内存布局

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 01-compilation-model（C++ 编译模型）

---

## 1. 概念讲解

### 1.1 存储期：对象住在哪里

C++ 有四种存储期（storage duration），决定对象何时创建、何时销毁：

| 存储期 | 关键字 | 创建时机 | 销毁时机 | 引擎典型用途 |
|--------|--------|---------|---------|-------------|
| **自动** | （局部变量） | 进入作用域/声明点 | 离开作用域 | 帧内临时数据、栈分配器缓冲 |
| **静态** | `static`, 全局 | 程序启动（首次到达时） | 程序结束 | 全局配置、类型注册表、内存管理器 |
| **线程局部** | `thread_local` | 线程启动/首次访问 | 线程退出 | 每线程 Scratch Buffer、线程日志 |
| **动态** | `new`/`new[]` | 显式调用 new | `delete`/`delete[]` | 堆对象、Arena 分配的对象 |

```cpp
// 四种存储期示例
int g_global;                         // 静态存储期

thread_local int t_scratchBuffer[256]; // 线程局部存储期

void frameUpdate() {
    int local = 42;                   // 自动存储期
    static int callCount = 0;        // 静态存储期（局部 static）
    ++callCount;

    auto* p = new int[1024];         // 动态存储期
    // ... 使用 p ...
    delete[] p;
}
```

**引擎视角：** 在每帧 16.6ms 的预算内，`malloc`/`new` 的开销是不可预测的（可能触发系统调用、锁竞争、缺页）。因此引擎热路径上大量使用自动存储期（栈上分配）和 Arena/帧分配器（从预分配大块中切分），而非每次动态分配。

### 1.2 栈帧与调用约定

当一个函数被调用时，CPU 在栈上创建一个**栈帧（stack frame）**：

```
高地址 ──────────────────────────────
  调用者的栈帧
  ├─ 返回地址        ← 调用完该回哪
  ├─ 保存的基指针     ← 调用者的栈帧基址
  └─ 参数（部分）     ← 寄存器传不完的参数压栈
  当前函数的栈帧 ───────────────────
  ├─ 保存的寄存器     ← 被调用者保存的寄存器
  ├─ 局部变量         ← 函数内的自动对象
  └─ 溢出区          ← 寄存器不够用时临时存放
低地址 ────── 栈指针 (rsp) ─────────
```

**x64 调用约定的核心规则**（Windows 与 System V AMD64 略有差异，这是简化版）：
- 前 4-6 个参数通过寄存器传递（整数用 rcx/rdx/r8/r9，浮点用 xmm0-xmm3）
- 返回值 ≤ 8 字节通过 rax 返回；更大的通过隐藏指针参数
- **平凡（trivial）类型**通过寄存器传递并返回——零内存开销
- **非平凡类型**（有析构/拷贝）必须通过栈或隐藏指针传递——这就是为什么引擎数学类型必须保持平凡

### 1.3 对象生命周期：构造→使用→析构

C++ 标准中，对象的"生命周期"有精确定义：

```
对象生命周期边界
───────────────────────────────
  存储分配完成
  └→ 构造函数执行完毕  ← 生命周期开始
        ├─ 对象可用（可以调用成员、读取状态）
        └→ 析构函数开始执行  ← 生命周期结束
              └→ 存储释放
───────────────────────────────
```

**关键规则：**
- 生命周期开始前：存储已分配但未初始化，读取是未定义行为（UB）
- 生命周期内：对象的所有操作都是合法的
- 生命周期结束后：不能再访问该对象（UB），但存储本身仍然存在直到释放
- 对于 **trivially copyable** 类型，拷贝字节（`memcpy`）等同于复制对象，生命周期在目标位置自动开始（隐式生命周期类型）

```cpp
alignas(int) std::byte storage[sizeof(int)];
// storage 中有内存，但没有 int 对象
int* p = new (storage) int(42);  // 生命周期开始
int x = *p;                       // OK，对象活着
p->~int();                        // 生命周期结束
// storage 仍然存在，但不能再通过 *p 读取
```

### 1.4 Trivial 类型：性能的基石

C++ 类型按照"编译器是否需要做事"分为以下几类：

```cpp
#include <type_traits>

struct Trivial {
    int x;                    // ✅ 平凡：编译器不会插入任何代码
};                            // 拷贝 = memcpy，析构 = no-op

struct NonTrivial {
    std::string name;         // ❌ 非平凡：需要深拷贝、释放内存
    ~NonTrivial() {}          // 用户定义析构 → 非平凡
};

struct TriviallyCopyable {
    int* ptr;                 // ⚠️ 平凡可拷贝，但非平凡（有指针！）
};                            // memcpy 会复制指针值——浅拷贝

// 检查
static_assert(std::is_trivial_v<Trivial>);             // true
static_assert(!std::is_trivial_v<NonTrivial>);         // true
static_assert(std::is_trivially_copyable_v<Trivial>);  // true
```

**引擎中要求平凡类型的原因：**
- 平凡的拷贝 = `memcpy` → SIMD 向量化 → 几纳秒完成
- 平凡的析构 → 释放数组时无需循环调用析构，一次释放即可
- 平凡的移动 → 零开销，等同拷贝

这就是为什么引擎数学类型（`Vec3`, `Vec4`, `Mat4`, `Quat`）必须是平凡的——它们每帧被拷贝数百万次。

### 1.5 内存布局：对齐、填充、大小

编译器在 struct 内部插入**填充（padding）**以满足对齐要求：

```cpp
struct BadLayout {
    char  a;   // 1 字节 @ offset 0
    //  padding: 3 字节 @ offset 1-3  (int 需要 4 字节对齐)
    int   b;   // 4 字节 @ offset 4
    char  c;   // 1 字节 @ offset 8
    //  padding: 3 字节 @ offset 9-11 (结构体总大小须为 max_alignof 的倍数)
    double d;  // 8 字节 @ offset 16 (需要 8 字节对齐)
    //  total: 24 字节
};

struct GoodLayout {
    double d;  // 8 字节 @ offset 0
    int    b;  // 4 字节 @ offset 8
    char   a;  // 1 字节 @ offset 12
    char   c;  // 1 字节 @ offset 13
    //  padding: 2 字节 @ offset 14-15
    //  total: 16 字节
};
```

**排序原则（从大到小）：** 将对齐要求最大的成员放在最前面，可以减少填充。在图形引擎中，顶点数据结构的内存布局直接影响 GPU 上传——填充字节浪费总线带宽、降低缓存效率。

### 1.6 `alignas` 和 `alignof`：精确控制对齐

```cpp
// 查询对齐
static_assert(alignof(int) == 4);
static_assert(alignof(double) == 8);

// SIMD 类型通常需要 16 或 32 字节对齐
struct alignas(16) Vec4_SSE {
    float x, y, z, w;  // sizeof == 16, alignof == 16
};

// 缓存行对齐（避免 false sharing）
struct alignas(64) ThreadLocalData {
    int jobsCompleted;
    // 确保该结构体独占一个缓存行
};

// 过对齐分配（C++17）
auto* p = new (std::align_val_t{64}) ThreadLocalData;
delete p;  // 编译器自动调用对齐版本的 operator delete
```

**引擎实践：**
- SIMD 向量类型必须 `alignas(16)` 或 `alignas(32)`（AVX）
- Job System 中的每线程数据结构必须 `alignas(64)` 避免 false sharing
- 从 Arena 分配器分配时，手动用 `std::align` 计算对齐后的地址

### 1.7 Standard Layout 类型

若一个类型的布局像 C 结构体一样可预测，则是 **Standard Layout** 类型：

```cpp
// ✅ Standard Layout: 可安全序列化、映射到 GPU/网络
struct TransformComponent { // C 兼容布局
    Vec4 position;           // 所有非静态成员有相同的访问控制
    Vec4 rotation;           // 没有虚函数、虚基类
    Vec4 scale;              // 基类也必须是 standard layout
    uint32_t entityId;       // 没有引用成员
};
static_assert(std::is_standard_layout_v<TransformComponent>);

// ❌ 非 Standard Layout
struct BadComponent {
    virtual void update() = 0;  // 虚函数 → 引入 vtable 指针
private:
    int privateData;            // 混合访问控制
public:
    int publicData;
};
```

**引擎为什么检查 `is_standard_layout`：**
- **GPU 上传**：顶点/索引缓冲、Uniform 块必须与着色器中定义的布局精确匹配
- **网络序列化**：将 struct 直接 `memcpy` 到网络包中（须注意字节序）
- **磁盘存储**：存档系统的二进制格式依赖确定性布局
- **共享内存/MMap**：在进程间共享数据结构

### 1.8 对象表示 vs 值表示

```cpp
// 对象表示 (object representation): 对象在内存中的确切字节序列
// 值表示 (value representation): 决定对象值的位集合

float f = 1.0f;
// 对象表示: 0x3F800000 (4 字节)
// 值表示:  符号位(0) + 指数(127) + 尾数(0)

// 对于 int，对象表示 == 值表示（没有填充位）
// 对于 float，部分位模式是 NaN（非正规值）
// bool 的大小是 1 字节，但值只有 true(1) 或 false(0)
bool b = true;   // 对象表示: 0x01
// 但如果你写入 0x02 → 值表示是 true，但对象表示异常 → UB！
```

**引擎中的影响：** 当从网络/磁盘读取字节流直接 reinterpret_cast 为结构体时，你依赖于对象表示的确定性。这引出了下一个关键话题——

### 1.9 严格别名规则 (Strict Aliasing)

编译器假定：**不同类型的指针永远不指向同一块内存**（除了少数例外）。基于这个假设，编译器可以重排指令以实现更好的优化。

```cpp
// ❌ 未定义行为：违反严格别名
float q_rsqrt(float number) {
    int i;
    float x2, y;
    x2 = number * 0.5f;
    y  = number;
    i  = *(int*)&y;      // UB! 将 float* 转型为 int* 再解引用
    i  = 0x5f3759df - (i >> 1);
    y  = *(float*)&i;    // UB! 同上
    return y;
}

// ✅ C++20 正确方式：std::bit_cast
float q_rsqrt_safe(float number) {
    int i = std::bit_cast<int>(number);  // OK，编译期保证安全
    i = 0x5f3759df - (i >> 1);
    return std::bit_cast<float>(i);      // OK
}
```

**例外（可以别名的类型）：** `char`, `unsigned char`, `std::byte` —— 这些类型可以检查任何对象的对象表示。这是 `memcpy` 和 `std::bit_cast` 实现的基础。

### 1.10 `std::launder`：告诉优化器"刷新你的假设"

```cpp
alignas(X) std::byte buf[sizeof(X)];
auto* p1 = new (buf) X{1};   // 在 buf 中构造 X{1}
auto* p2 = new (buf) X{2};   // 在同一地址构造 X{2}，X{1} 的生存期结束
// p1 仍然 == p2（地址相同）
// 但 p1 现在指向生存期已结束的对象——无法通过 p1 访问！
auto x = std::launder(p1);    // ✅ "这个地址现在有一个活着的 X"
// std::launder 阻止编译器基于旧 p1 值进行常量传播优化
```

`std::launder` 在引擎中主要用于**placement new 替换对象的场景**——比如 `std::vector` 的重分配、`std::optional` 的重新赋值、Arena 分配器中复用内存。大多数情况下你不需要手动调用它，但理解它的存在可以解释某些"明明改了值，编译器却不认"的诡异优化行为。

---

## 2. 代码示例

### 示例 1：内存布局可视化工具

```cpp
// mem_layout.cpp — 打印结构体的内存布局
// 编译: g++ -std=c++20 -O2 mem_layout.cpp -o mem_layout && ./mem_layout

#include <iostream>
#include <iomanip>
#include <cstddef>

template<typename T>
void printLayout(const char* name) {
    std::cout << "=== " << name << " ===\n";
    std::cout << "  sizeof: " << sizeof(T) << " bytes\n";
    std::cout << "  alignof: " << alignof(T) << " bytes\n";

    if constexpr (std::is_standard_layout_v<T>) {
        std::cout << "  standard_layout: yes\n";
    }
    if constexpr (std::is_trivially_copyable_v<T>) {
        std::cout << "  trivially_copyable: yes\n";
    }
    if constexpr (std::is_trivial_v<T>) {
        std::cout << "  trivial: yes\n";
    }
    std::cout << '\n';
}

struct Bad {
    char   a;
    int    b;
    char   c;
    double d;
};

struct Good {
    double d;
    int    b;
    char   a;
    char   c;
};

struct Transform {
    float posX, posY, posZ;
    float rotX, rotY, rotZ;
    float scaleX, scaleY, scaleZ;
};

struct alignas(16) TransformSSE {
    float posX, posY, posZ, pad1;
    float rotX, rotY, rotZ, pad2;
    float scaleX, scaleY, scaleZ, pad3;
};

// 使用 offsetof 宏打印各成员偏移
#define PRINT_OFFSET(T, member) \
    std::cout << "  " #member " @ offset " << offsetof(T, member) << '\n'

int main() {
    printLayout<Bad>("Bad (wasteful padding)");
    PRINT_OFFSET(Bad, a);
    PRINT_OFFSET(Bad, b);
    PRINT_OFFSET(Bad, c);
    PRINT_OFFSET(Bad, d);
    std::cout << "  → Wasted: " << (sizeof(Bad) - (sizeof(char)+sizeof(int)+sizeof(char)+sizeof(double)))
              << " bytes of padding\n\n";

    printLayout<Good>("Good (packed efficiently)");
    PRINT_OFFSET(Good, d);
    PRINT_OFFSET(Good, b);
    PRINT_OFFSET(Good, a);
    PRINT_OFFSET(Good, c);
    std::cout << "  → Wasted: " << (sizeof(Good) - (sizeof(double)+sizeof(int)+2*sizeof(char)))
              << " bytes of padding\n\n";

    printLayout<Transform>("Transform (9 floats)");
    printLayout<TransformSSE>("TransformSSE (aligned, padded for SIMD)");
    return 0;
}
```

**运行方式：**
```bash
g++ -std=c++20 -O2 mem_layout.cpp -o mem_layout && ./mem_layout
```

**预期输出：**
```text
=== Bad (wasteful padding) ===
  sizeof: 24 bytes
  alignof: 8 bytes
  standard_layout: yes
  trivially_copyable: yes
  trivial: yes
  a @ offset 0
  b @ offset 4
  c @ offset 8
  d @ offset 16
  → Wasted: 10 bytes of padding

=== Good (packed efficiently) ===
  sizeof: 16 bytes
  alignof: 8 bytes
  standard_layout: yes
  trivially_copyable: yes
  trivial: yes
  d @ offset 0
  b @ offset 8
  a @ offset 12
  c @ offset 13
  → Wasted: 2 bytes of padding

=== Transform (9 floats) ===
  sizeof: 36 bytes
  alignof: 4 bytes
  ...

=== TransformSSE (aligned, padded for SIMD) ===
  sizeof: 48 bytes
  alignof: 16 bytes
```

### 示例 2：对象表示字节打印器

```cpp
// obj_repr.cpp — 打印任意类型的对象表示（底层字节）
// 编译: g++ -std=c++20 -O2 obj_repr.cpp -o obj_repr && ./obj_repr

#include <iostream>
#include <iomanip>
#include <bit>       // std::bit_cast (C++20)
#include <cstring>   // std::memcpy (for the fallback path)

// 打印任何可平凡拷贝类型的底层字节
template<typename T>
requires std::is_trivially_copyable_v<T>
void printBytes(const T& value, const char* label) {
    std::cout << label << " (sizeof=" << sizeof(T) << "):\n  hex: ";
    const auto* bytes = reinterpret_cast<const unsigned char*>(&value);
    for (size_t i = 0; i < sizeof(T); ++i) {
        std::cout << std::hex << std::setw(2) << std::setfill('0')
                  << static_cast<int>(bytes[i]) << ' ';
    }
    std::cout << std::dec << '\n';
}

int main() {
    int negative = -1;
    printBytes(negative, "int -1");

    float one = 1.0f;
    printBytes(one, "float 1.0");

    float negZero = -0.0f;
    printBytes(negZero, "float -0.0");

    double pi = 3.141592653589793;
    printBytes(pi, "double π");

    // 安全类型双关 (C++20)
    float f = 1.5f;
    int bits = std::bit_cast<int>(f);
    std::cout << "\nstd::bit_cast: float 1.5 → int bits = 0x"
              << std::hex << bits << std::dec << '\n';

    float back = std::bit_cast<float>(bits);
    std::cout << "std::bit_cast: back to float = " << back << '\n';

    // 演示大小端
    uint32_t val = 0x12345678;
    printBytes(val, "uint32_t 0x12345678 (check endianness)");
    const auto* b = reinterpret_cast<const unsigned char*>(&val);
    if (b[0] == 0x78) {
        std::cout << "  → Little-endian detected\n";
    } else {
        std::cout << "  → Big-endian detected\n";
    }

    return 0;
}
```

**运行方式：**
```bash
g++ -std=c++20 -O2 obj_repr.cpp -o obj_repr && ./obj_repr
```

---

## 3. 练习

### 练习 1：绘制结构体内存布局（基础）

对于以下每个结构体，手工绘制其内存布局图（标明每个成员的偏移量、填充字节、总大小）：
```cpp
struct A { char a; short b; int c; };
struct B { char a; long long b; char c; short d; };
struct C { double a; bool b; int c; bool d; };
struct D { char a[3]; int b; char c; };
```
然后用 `static_assert(sizeof(...) == X)` 和 `offsetof` 验证你的答案。解释每个结构体为什么有特定的填充模式。

### 练习 2：实现类型检查工具（进阶）

编写一个泛型函数 `describe_type<T>()`，输出类型的以下信息：
- `sizeof`, `alignof`
- 是否 `trivial`, `trivially_copyable`, `standard_layout`
- 是否 `aggregate`, 是否 `polymorphic`（有虚函数）
- 如果是类类型：是否 `abstract`, `final`
- 将结果以 Markdown 表格形式打印

对至少 10 种不同 C++ 类型运行此工具（`int`, `std::string`, `std::unique_ptr<int>`, `std::vector<int>`, 自定义 struct 等），观察模式。

### 练习 3：缓存行对齐的性能影响（可选）

设计一个包含 8 个原子计数器的结构体，分别用两种方式实现：
- **版本 A**：8 个 `std::atomic<int64_t>` 紧密排列（可能在同一个缓存行内）
- **版本 B**：每个计数器用 `alignas(64)` 隔开，独占一个缓存行

编写多线程基准测试（8 个线程，每个自增自己的计数器 1000 万次），测量两者的耗时差异。解释观察到的性能差异与 **false sharing** 的关系。提示：使用 `std::hardware_destructive_interference_size`（C++17）。

---

## 4. 扩展阅读

- **[必读] C++ Reference — Object lifetime:** https://en.cppreference.com/w/cpp/language/lifetime — 对象生命周期的标准条款
- **[必读] C++ Reference — Storage duration:** https://en.cppreference.com/w/cpp/language/storage_duration
- **[必读] C++ Reference — TrivialType:** https://en.cppreference.com/w/cpp/named_req/TrivialType
- **[推荐] "What Every Programmer Should Know About Memory" (Drepper, 2007)** — 缓存行、对齐、内存层次
- **[推荐] "The Lost Art of C Structure Packing" (Eric S. Raymond)** — http://www.catb.org/esr/structure-packing/
- **[进阶] C++ Reference — `std::launder`** — https://en.cppreference.com/w/cpp/utility/launder
- **[进阶] "Type Punning, Strict Aliasing, and Optimization" (Raymond Chen)** — https://devblogs.microsoft.com/oldnewthing/?p=101653
- **[工具] C++ Insights** — https://cppinsights.io/ — 看看编译器如何展开你的代码

---

## 常见陷阱

1. **读取未初始化的内存。**
   ```cpp
   // ❌ 错误
   int x;           // 自动存储期 → 不确定的值
   if (x > 0) {}    // UB！读取未初始化变量
   
   // ✅ 正确
   int x = 0;       // 显式初始化
   int y{};          // 值初始化 → 0
   ```
   在 Release 编译中，未初始化的局部变量可能恰好是之前栈上的残留值——表现出"有时能跑有时崩溃"的非确定性行为，极难调试。

2. **假定 `memcpy` 可安全用于非平凡类型。**
   ```cpp
   // ❌ 错误
   std::string src = "hello";
   std::string dst;
   std::memcpy(&dst, &src, sizeof(std::string));  // UB!
   // dst 和 src 的指针指向同一块堆内存 → 双重释放
   
   // ✅ 正确
   std::string dst = src;  // 调用拷贝构造，正确深拷贝
   // 或检查类型性质
   static_assert(std::is_trivially_copyable_v<std::string> == false);
   ```

3. **违反严格别名规则进行类型双关。**
   ```cpp
   // ❌ 错误
   float f = 1.0f;
   int i = *reinterpret_cast<int*>(&f);  // UB! 违反严格别名
   
   // ✅ 正确（C++20）
   int i = std::bit_cast<int>(f);
   
   // ✅ 正确（C++17/14）— 通过 memcpy 是合法旁路
   int i;
   std::memcpy(&i, &f, sizeof(float));
   ```
   严格别名违规的可怕之处在于：在低优化级别 "碰巧能跑"，但 `-O2` 以上编译器会做出激进的假设，导致神秘 bug。

4. **忘记对齐要求导致 placement new 崩溃。**
   ```cpp
   // ❌ 错误
   char buf[sizeof(double)];    // 可能在奇数地址
   auto* p = new (buf) double(3.14);  // double 需要 8 字节对齐
   
   // ✅ 正确
   alignas(double) char buf[sizeof(double)];
   auto* p = new (buf) double(3.14);
   
   // ✅ 更通用的方式
   alignas(alignof(T)) std::byte buf[sizeof(T)];
   ```
   在 x86 上未对齐访问通常只是慢，但在 ARM/移动平台上会触发 SIGBUS 直接崩溃。作为跨平台引擎，必须始终遵守对齐。

5. **混淆 struct 的 `sizeof` 与成员大小的和。**
   ```cpp
   struct S { char a; int b; };
   // sizeof(S) == 8，但 sizeof(a) + sizeof(b) == 5
   // 3 字节填充——常在网络/序列化代码中被忽略
   // 不要手动计算大小，始终使用 sizeof(S)
   ```
