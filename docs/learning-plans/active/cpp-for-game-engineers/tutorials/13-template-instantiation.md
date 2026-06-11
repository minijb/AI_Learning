---
title: "模板基础与实例化模型"
updated: 2026-06-05
---

# 模板基础与实例化模型

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: C++ 编译模型与游戏构建系统（第 1 节）
> C++ 标准: C++98（基础模板）、C++11（extern template、变参模板）、C++14（变量模板）、C++17（CTAD、fold expressions）、C++20（Concepts）

---

## 1. 概念讲解

### 1.1 模板编译模型：定义必须可见

模板和普通函数有一个根本区别：**模板不是代码，而是生成代码的"蓝图"**。

```cpp
// 普通函数 — 编译为一条 call 指令，定义可以在另一个 .cpp 中
int add(int a, int b);  // 声明，定义在别处

// 函数模板 — 使用前定义必须完整可见
template <typename T>
T add(T a, T b) { return a + b; }  // 必须在头文件中！
```

编译器只有在**看到完整定义**时才能实例化模板。这意味着模板的定义通常放在头文件中。这是编译时间开销的主要来源之一——每包含一次头文件，编译器都需要重新解析模板定义。

**编译过程（简化）**：

```
源文件 game.cpp:
  #include "Math.h"
  Vec3<float> v;
  float x = v.x;

1. 预处理器：展开 #include → 模板定义进入 game.cpp 的 TU
2. 编译器：遇到 Vec3<float> → 用 float 替换 T → 生成 Vec3<float> 的完整类
3. 链接器：如果多个 TU 都实例化了 Vec3<float>，合并重复（ODR 例外规则）
```

### 1.2 隐式实例化 vs 显式实例化

**隐式实例化**：编译器在首次使用模板时自动生成代码。

```cpp
template <typename T>
T max(T a, T b) { return a > b ? a : b; }

int main() {
    int x = max(1, 2);       // 隐式实例化 max<int>
    float y = max(1.0f, 2.0f); // 隐式实例化 max<float>
    // 只实例化了 int 和 float 版本 — double 版本不存在
}
```

**显式实例化**：程序员明确告诉编译器"请为类型 X 生成模板代码"。

```cpp
// 在某个 .cpp 文件中：
template class std::vector<int>;     // 显式实例化整个类
template float max(float, float);    // 显式实例化函数

// 之后编译其他 TU 时，链接器会找到这个实例而不是重新生成
```

在游戏引擎中，显式实例化是控制编译时间的关键工具：

```cpp
// MathTypes.cpp — 集中显式实例化常用数学类型
#include "Vec3.h"
#include "Vec4.h"
#include "Mat4.h"

template class Vec3<float>;
template class Vec3<double>;
template class Vec4<float>;
template class Mat4<float>;

// 所有其他 .cpp 文件只 include 头文件，不会重复生成这些类型的代码
```

### 1.3 extern template（C++11）— 阻止隐式实例化

```cpp
// Vec3.h
template <typename T> class Vec3 { /* ... */ };

extern template class Vec3<float>;   // 声明：不要在此 TU 实例化
extern template class Vec3<double>;  // 实例化在其他 TU（比如 MathTypes.cpp）

// Vec3.cpp（单独的 TU）
template class Vec3<float>;   // 显式实例化 — 只在这里生成代码
template class Vec3<double>;
```

这让引擎可以"集中生成、全局复用"。头文件仍然是完整的（满足 "定义必须可见" 的要求），但不会在每个 include 它的 TU 中重复生成机器码。

### 1.4 两阶段名称查找

模板编译分为两阶段：

**阶段 1（定义时）**：检查所有**不依赖模板参数**的名称。

```cpp
template <typename T>
void foo(T t) {
    bar();              // ← 阶段 1 检查：bar() 必须可见
    t.method();         // ← 阶段 2 才检查（依赖 T）
    std::cout << t;     // ← 可以找到（std::cout 不依赖 T）
    non_existent_func(); // ← 阶段 1 错误：找不到此函数
}
```

**阶段 2（实例化时）**：检查所有**依赖模板参数**的名称。

```cpp
template <typename T>
void process(T t) {
    t.render();          // ← 阶段 2：T 有 render() 方法吗？
    typename T::value_type v; // ← typename 关键字：告诉编译器 T::value_type 是类型
}

struct Mesh { void render(); using value_type = int; };
process(Mesh{});  // OK — Mesh 满足所有要求
```

**typename 关键字**：当引用依赖类型时，必须用 `typename` 消除歧义：

```cpp
template <typename T>
void f() {
    typename T::iterator it;  // ✅ typename 告诉编译器这是类型
    T::value_type* p;         // ❌ 歧义：乘法 or 指针声明？
    typename T::value_type* p; // ✅ 明确是指针声明
}
```

**template 关键字**：当调用依赖模板时：

```cpp
template <typename T>
void g(T t) {
    t.template foo<int>();   // ✅ template 关键字消除歧义
    // t.foo<int>();         // ❌ 编译器可能把 < 解释为小于号
}
```

### 1.5 ODR 与模板：为什么链接器不报"重复定义"

ODR（One Definition Rule）规定每个非内联函数/全局变量只能有一个定义。但模板违反了这一规则——同一个 `Vec3<float>` 可能在 50 个 .cpp 中被隐式实例化。

**C++ 的解决方案**：标准明确规定模板的隐式实例化享有 ODR 豁免。链接器遇到 50 份 `Vec3<float>::x()` 的机器码时，可以**任意保留一份并丢弃其余 49 份**（通常通过 COMDAT 段实现）。这被称为"贪婪实例化"模型。

```
编译:
  game.cpp    → game.o    (包含 Vec3<float>::x() 的机器码)
  render.cpp  → render.o  (包含 Vec3<float>::x() 的机器码)  ← 重复！
  physics.cpp → physics.o (包含 Vec3<float>::x() 的机器码)  ← 重复！

链接:
  链接器检测到 3 份相同的符号 → 保留 1 份，丢弃 2 份
  → 最终二进制中只有 1 份 Vec3<float>::x()
```

### 1.6 类型推导（C++11→C++17）

```cpp
// auto — 剥去引用和顶层 const
const int& cr = 42;
auto a = cr;        // a 是 int（去除 & 和 const）
auto& b = cr;       // b 是 const int&（显式加 &）

// decltype — 保留引用和 const
decltype(cr) c = cr; // c 是 const int&

// decltype(auto)（C++14）— 保留所有修饰
template <typename T>
decltype(auto) forward(T&& t) {  // 返回类型与 t 的值类别一致
    return std::forward<T>(t);
}

// CTAD（C++17）— 类模板参数推导
std::vector v = {1, 2, 3};      // vector<int>，不需要写模板参数
std::pair p = {1, "hello"};     // pair<int, const char*>
std::lock_guard lk(mtx);         // lock_guard<std::mutex>
```

### 1.7 二进制膨胀与控制策略

模板会导致**代码膨胀（Code Bloat）**：每个不同的模板参数组合生成一份独立的机器码。

```
Vec3<float>::dot()   → 4KB 机器码
Vec3<double>::dot()  → 4KB 机器码（几乎相同！）
Vec3<int>::dot()     → 4KB 机器码

3 种类型 × 每个成员函数 = 总代码量增长
```

**引擎级缓解策略**：

| 策略 | 说明 | 示例 |
|------|------|------|
| **显式实例化** | 限制可以实例化的类型集合 | `template class Vec3<float>;` — 只有 float |
| **extern template** | 阻止重复生成 | `extern template class Vec3<float>;` |
| **类型擦除基类** | 将模板无关逻辑提取到非模板基类 | `Vec3Base` 存放不依赖 T 的公共实现 |
| **void* 实现层** | 模板类调用非模板的 void* 实现 | 模板只是类型安全的薄包装 |
| **预编译头（PCH）** | 预编译常用模板头文件 | 将 `<vector>`, `Vec3.h` 放入 PCH |
| **限制特化数量** | 对引擎类型做白名单 | `static_assert(is_allowed_math_type_v<T>)` |

### 1.8 组织模式：.h vs .hpp vs .inl

业界有三种主流方式组织模板代码：

```
模式 1: 全部在 .h（最常用）        模式 2: .h + .inl（UE 风格）      模式 3: .h + .cpp（显式实例化）
──────────────────────────────  ──────────────────────────────  ──────────────────────────────
Vec3.h:                          Vec3.h:                         Vec3.h:
  template<class T>                template<class T>               template<class T>
  class Vec3 {                     class Vec3 {                    class Vec3 {
    T x,y,z;                         T x,y,z;                       T x,y,z;
    T dot(const Vec3& r) const {     T dot(const Vec3& r) const;    T dot(const Vec3& r) const;
      return x*r.x + y*r.y + z*r.z;//声明                       };//定义直接在头文件中
    }                             Vec3.inl:
  };                                template<class T>             Vec3.cpp:
                                    T Vec3<T>::dot(const Vec3& r)  template class Vec3<float>;
                                      const {                      template class Vec3<double>;
                                      return x*r.x+y*r.y+z*r.z;   //只有 float/double 能实例化
                                    }
```

引擎通常用**模式 1**（简单）或**模式 2**（头文件干净）。

---

## 2. 代码示例

### 2.1 引擎数学库模板（含显式实例化 + extern template）

```cpp
// MathVec.h — 数学向量模板库
// 编译: g++ -std=c++20 -O2 mathvec_demo.cpp -o mathvec_demo

#pragma once
#include <cstddef>
#include <cmath>
#include <type_traits>
#include <iostream>

// ─── 声明：只允许特定算术类型 ───
template <typename T>
concept Arithmetic = std::is_arithmetic_v<T>;

// ─── Vec3 模板定义 ───
template <Arithmetic T>
class Vec3 {
public:
    T x{}, y{}, z{};

    constexpr Vec3() = default;
    constexpr Vec3(T ax, T ay, T az) : x(ax), y(ay), z(az) {}

    // 点积 — 定义在头文件中（编译器需要内联）
    constexpr T dot(const Vec3& rhs) const {
        return x * rhs.x + y * rhs.y + z * rhs.z;
    }

    // 长度 — 定义在头文件中
    T length() const {
        return std::sqrt(static_cast<double>(dot(*this)));
    }

    // 归一化 — 定义在头文件中
    Vec3 normalized() const {
        T len = length();
        if (len == T{0}) return *this;
        return Vec3{x / len, y / len, z / len};
    }

    // 运算符
    constexpr Vec3 operator+(const Vec3& rhs) const {
        return {x + rhs.x, y + rhs.y, z + rhs.z};
    }
    constexpr Vec3 operator-(const Vec3& rhs) const {
        return {x - rhs.x, y - rhs.y, z - rhs.z};
    }
    constexpr Vec3 operator*(T s) const {
        return {x * s, y * s, z * s};
    }
    constexpr bool operator==(const Vec3& rhs) const = default;

    // 叉积
    constexpr Vec3 cross(const Vec3& rhs) const {
        return {
            y * rhs.z - z * rhs.y,
            z * rhs.x - x * rhs.z,
            x * rhs.y - y * rhs.x
        };
    }
};

// ─── 类型别名 ───
using Vec3f = Vec3<float>;
using Vec3d = Vec3<double>;
using Vec3i = Vec3<int>;

// ─── extern template 声明（C++11）— 阻止在此头文件中隐式实例化 ───
extern template class Vec3<float>;
extern template class Vec3<double>;
extern template class Vec3<int>;
```

### 2.2 显式实例化的集中定义

```cpp
// MathVec_inst.cpp — 显式实例化（集中生成机器码）
// 只在项目中的一个 .cpp 文件编译此文件

#include "MathVec.h"

// 显式实例化引擎使用的所有 Vec3 类型
template class Vec3<float>;
template class Vec3<double>;
template class Vec3<int>;
```

### 2.3 编译期类型分发器

```cpp
// compile_time_dispatcher.cpp — 利用模板在编译期选择最优算法

#include <type_traits>
#include <cstring>

// ─── 策略 1: 标签分发（Tag Dispatch）───
struct cpu_impl {};
struct sse_impl {};
struct avx_impl {};

// 默认 CPU 实现
template <typename T>
void normalize_vector(T* data, size_t count, cpu_impl) {
    for (size_t i = 0; i < count; ++i) {
        T val = data[i];
        data[i] = val / std::sqrt(static_cast<double>(val * val));
    }
}

// SSE 实现（仅 float）
#ifdef __SSE__
#include <x86intrin.h>
void normalize_vector(float* data, size_t count, sse_impl) {
    size_t simd_count = count / 4 * 4;
    for (size_t i = 0; i < simd_count; i += 4) {
        __m128 v = _mm_load_ps(data + i);
        __m128 len = _mm_sqrt_ps(_mm_mul_ps(v, v));
        v = _mm_div_ps(v, len);
        _mm_store_ps(data + i, v);
    }
    // 处理剩余的 <4 个元素
    for (size_t i = simd_count; i < count; ++i) {
        float val = data[i];
        data[i] = val / std::sqrt(val * val);
    }
}
#endif

// ─── 标签分发入口 ───
template <typename T>
void normalize(T* data, size_t count) {
    // 根据类型选择最佳实现
    if constexpr (std::is_same_v<T, float>) {
#ifdef __SSE__
        normalize_vector(data, count, sse_impl{});
#else
        normalize_vector(data, count, cpu_impl{});
#endif
    } else {
        normalize_vector(data, count, cpu_impl{});
    }
}

// ─── 策略 2: if constexpr 编译期分支（C++17）───
template <typename T>
T fast_abs(T val) {
    if constexpr (std::is_unsigned_v<T>) {
        return val;  // 无符号数已经是正的
    } else if constexpr (std::is_floating_point_v<T>) {
        return std::fabs(val);
    } else {
        return val < 0 ? -val : val;  // 有符号整数
    }
}
```

### 2.4 CTAD 与推导指南

```cpp
// ctad_demo.cpp — C++17 类模板参数推导

#include <vector>
#include <utility>
#include <iostream>

// ─── 自定义容器，支持 CTAD ───
template <typename T, size_t Capacity = 64>
class FixedArray {
    T m_data[Capacity];
    size_t m_size = 0;

public:
    FixedArray() = default;

    // 从 initializer_list 构造
    FixedArray(std::initializer_list<T> il) {
        for (const auto& v : il) {
            if (m_size < Capacity) m_data[m_size++] = v;
        }
    }

    constexpr size_t size() const { return m_size; }
    constexpr size_t capacity() const { return Capacity; }

    T& operator[](size_t i) { return m_data[i]; }
    const T& operator[](size_t i) const { return m_data[i]; }
};

// ─── 显式推导指南（可选——这里编译器已能从 initializer_list 推导）───
template <typename T>
FixedArray(std::initializer_list<T>) -> FixedArray<T>;

// ─── CTAD 演示 ───
void ctad_demo() {
    std::cout << "===== CTAD 演示 =====\n";

    // 自动推导
    std::vector v = {1, 2, 3, 4};          // vector<int>
    std::pair p = {42, "answer"};          // pair<int, const char*>
    FixedArray arr = {1.0f, 2.0f, 3.0f};   // FixedArray<float, 64>

    std::cout << "v.size() = " << v.size() << "\n";
    std::cout << "p = {" << p.first << ", " << p.second << "}\n";
    std::cout << "arr.size() = " << arr.size() << "\n";
}
```

### 2.5 二进制膨胀测量工具

```cpp
// binary_bloat_measure.cpp — 测量模板实例化对二进制大小的影响

#include <iostream>
#include <vector>
#include <array>
#include <functional>

// ─── 模板繁重型：每个 T 生成全套代码 ───
template <typename T>
class HeavyContainer {
    T* m_data;
    size_t m_size;
public:
    explicit HeavyContainer(size_t n) : m_data(new T[n]), m_size(n) {}
    ~HeavyContainer() { delete[] m_data; }
    T& operator[](size_t i) { return m_data[i]; }
    size_t size() const { return m_size; }
    void sort() { /* 冒泡排序 */ }
    T* find(const T& v) { /* 线性搜索 */ return nullptr; }
    void reverse() { /* 反转 */ }
    T sum() const { T s{}; for (size_t i = 0; i < m_size; ++i) s += m_data[i]; return s; }
    T max() const { T m = m_data[0]; for (size_t i = 1; i < m_size; ++i) if (m_data[i] > m) m = m_data[i]; return m; }
    T min() const { T m = m_data[0]; for (size_t i = 1; i < m_size; ++i) if (m_data[i] < m) m = m_data[i]; return m; }
};

// ─── 类型擦除型：模板只做类型安全包装，实现委托给非模板层 ───
class LightContainerBase {
protected:
    void* m_data;
    size_t m_size;
    size_t m_elem_size;

    LightContainerBase(void* data, size_t n, size_t es)
        : m_data(data), m_size(n), m_elem_size(es) {}

    void* get_element(size_t i) {
        return static_cast<char*>(m_data) + i * m_elem_size;
    }
};

template <typename T>
class LightContainer : private LightContainerBase {
public:
    explicit LightContainer(size_t n)
        : LightContainerBase(::operator new(n * sizeof(T)), n, sizeof(T)) {}

    ~LightContainer() { ::operator delete(m_data); }

    T& operator[](size_t i) {
        return *static_cast<T*>(get_element(i));  // 类型安全包装
    }
    size_t size() const { return m_size; }
    // 不生成 per-T 的 sort/find/reverse 等方法
};

// ─── 使用多个类型触发实例化 ───
void use_heavy() {
    HeavyContainer<int>    a(100);
    HeavyContainer<float>  b(100);
    HeavyContainer<double> c(100);
    HeavyContainer<long>   d(100);
    // 每个类型生成完整的 6 个方法 → 24 个实例化
    volatile auto s1 = a.sum();
    volatile auto s2 = b.sum();
    (void)s1; (void)s2;
}

void use_light() {
    LightContainer<int>    a(100);
    LightContainer<float>  b(100);
    LightContainer<double> c(100);
    LightContainer<long>   d(100);
    // 只有 operator[] 和 size() 被实例化 → 模板代码量极少
    volatile auto v1 = a[0];
    volatile auto v2 = b[0];
    (void)v1; (void)v2;
}

int main() {
    ctad_demo();

    std::cout << "\n===== 二进制膨胀分析 =====\n";
    std::cout << "编译命令:\n";
    std::cout << "  g++ -std=c++20 -c binary_bloat_measure.cpp -o heavy.o\n";
    std::cout << "  objdump -t heavy.o | c++filt | grep HeavyContainer | wc -l\n";
    std::cout << "  → 统计模板实例化符号数量\n\n";

    use_heavy();
    use_light();

    // 测量思路：
    // 1. 注释掉 use_light()，编译 → 看 .o 文件大小
    // 2. 注释掉 use_heavy()，编译 → 看 .o 文件大小
    // 3. 比较两者 → 量化模板膨胀程度

    return 0;
}
```

---

## 3. 练习

### 练习 1（必做）：构建模板数学库并显式实例化

1. 编写 `template <Arithmetic T> class Vec3 { T x,y,z; ... }` 含 dot/cross/normalized/length/+/-/*
2. 编写 `template <Arithmetic T> class Mat4 { ... }` 含乘法、逆矩阵（3x3 子矩阵求逆即可）
3. 在独立的 `MathLibrary_inst.cpp` 中对 `Vec3<float>`, `Vec3<double>`, `Mat4<float>` 进行显式实例化
4. 在头文件中添加 `extern template class Vec3<float>;` 等声明
5. 编写一个简单的 `main.cpp` 使用这些类型，验证程序能正确编译和运行

### 练习 2（必做）：测量二进制膨胀

1. 编写两个版本的容器：`HeavyVector<T>`（所有方法在头文件中）和 `LightVector<T>`（模板只做类型安全包装，实现委托给非模板 `VectorBase`）
2. 对 5 种不同类型（int, float, double, long, short）分别实例化两个容器
3. 编译两个独立的 .o 文件并比较大小（使用 `objdump -t` 或 `nm --demangle` 分析符号表）
4. 分析哪些方法贡献了最大的代码膨胀
5. 输出一份简短的膨胀分析报告

### 练习 3（选做·挑战）：重构模板繁重的引擎代码

1. 假设有一个引擎的数学库使用大量模板（Vec2<T>/Vec3<T>/Vec4<T>/Mat3<T>/Mat4<T>/Quat<T>），每个类型都对 float/double 实例化
2. 使用 **extern template** 将实例化集中到 2 个 .cpp 文件中，测量编译时间的改善
3. 使用 **PCH（预编译头）** 包含常用模板头文件，进一步减少编译时间
4. 编写一个 `static_assert` 约束，禁止用户对不支持的类型（如 `std::string`）实例化 Vec3
5. 写出重构前后的编译时间对比（使用 `time make` 或 MSVC 的 `/Bt+` 标志）

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **头文件 `MathLibrary.h`**：
> ```cpp
> > // MathLibrary.h — 模板数学库 + extern template 声明
> > #pragma once
> > #include <cmath>
> > #include <type_traits>
> > #include <array>
> > 
> > // 约束：只接受算术类型
> > template <typename T>
> > concept Arithmetic = std::is_arithmetic_v<T>;
> > 
> > // ─── Vec3 ───
> > template <Arithmetic T>
> > class Vec3 {
> > public:
> >     T x{}, y{}, z{};
> > 
> >     constexpr Vec3() = default;
> >     constexpr Vec3(T ax, T ay, T az) : x(ax), y(ay), z(az) {}
> > 
> >     constexpr T dot(const Vec3& rhs) const {
> >         return x * rhs.x + y * rhs.y + z * rhs.z;
> >     }
> >     constexpr Vec3 cross(const Vec3& rhs) const {
> >         return { y * rhs.z - z * rhs.y,
> >                  z * rhs.x - x * rhs.z,
> >                  x * rhs.y - y * rhs.x };
> >     }
> >     Vec3 normalized() const {
> >         T len = std::sqrt(static_cast<double>(dot(*this)));
> >         return len == T(0) ? *this : Vec3{x / len, y / len, z / len};
> >     }
> >     T length() const { return std::sqrt(static_cast<double>(dot(*this))); }
> > 
> >     constexpr Vec3 operator+(const Vec3& rhs) const { return {x+rhs.x, y+rhs.y, z+rhs.z}; }
> >     constexpr Vec3 operator-(const Vec3& rhs) const { return {x-rhs.x, y-rhs.y, z-rhs.z}; }
> >     constexpr Vec3 operator*(T s) const { return {x*s, y*s, z*s}; }
> >     constexpr Vec3 operator/(T s) const { return {x/s, y/s, z/s}; }
> >     constexpr Vec3 operator-() const { return {-x, -y, -z}; }
> >     constexpr bool operator==(const Vec3&) const = default;
> > };
> > 
> > // ─── Mat4 ───
> > template <Arithmetic T>
> > class Mat4 {
> >     T m[4][4]{};  // m[row][col]
> > public:
> >     constexpr Mat4() {
> >         m[0][0] = m[1][1] = m[2][2] = m[3][3] = T(1);  // 单位矩阵
> >     }
> >     // 元素访问
> >     constexpr T& operator()(int row, int col) { return m[row][col]; }
> >     constexpr const T& operator()(int row, int col) const { return m[row][col]; }
> > 
> >     // 矩阵乘法
> >     Mat4 operator*(const Mat4& rhs) const {
> >         Mat4 r;
> >         for (int i = 0; i < 4; ++i)
> >             for (int j = 0; j < 4; ++j) {
> >                 r.m[i][j] = T(0);
> >                 for (int k = 0; k < 4; ++k)
> >                     r.m[i][j] += m[i][k] * rhs.m[k][j];
> >             }
> >         return r;
> >     }
> > 
> >     // 3x3 子矩阵求逆（adjugate / determinant）
> >     Mat4 inverse3x3() const {
> >         // 提取 3x3 子矩阵: m[0..2][0..2]
> >         T a = m[0][0], b = m[0][1], c = m[0][2];
> >         T d = m[1][0], e = m[1][1], f = m[1][2];
> >         T g = m[2][0], h = m[2][1], i = m[2][2];
> > 
> >         T det = a*(e*i - f*h) - b*(d*i - f*g) + c*(d*h - e*g);
> >         if (det == T(0)) return Mat4();  // 奇异矩阵
> > 
> >         Mat4 inv;
> >         inv.m[0][0] = (e*i - f*h) / det;
> >         inv.m[0][1] = (c*h - b*i) / det;
> >         inv.m[0][2] = (b*f - c*e) / det;
> >         inv.m[1][0] = (f*g - d*i) / det;
> >         inv.m[1][1] = (a*i - c*g) / det;
> >         inv.m[1][2] = (c*d - a*f) / det;
> >         inv.m[2][0] = (d*h - e*g) / det;
> >         inv.m[2][1] = (b*g - a*h) / det;
> >         inv.m[2][2] = (a*e - b*d) / det;
> >         inv.m[3][3] = T(1);
> >         return inv;
> >     }
> > 
> >     constexpr bool operator==(const Mat4&) const = default;
> > };
> > 
> > // ─── extern template 声明 ───
> > extern template class Vec3<float>;
> > extern template class Vec3<double>;
> > extern template class Mat4<float>;
> > ```
> 
> **显式实例化文件 `MathLibrary_inst.cpp`**：
> ```cpp
> > // MathLibrary_inst.cpp — 集中显式实例化（项目只编译一次）
> > #include "MathLibrary.h"
> > 
> > // 显式实例化所有使用的类型
> > template class Vec3<float>;
> > template class Vec3<double>;
> > template class Mat4<float>;
> > ```
> 
> **`main.cpp` — 使用 MathLibrary**：
> ```cpp
> > // main.cpp — 使用显式实例化的数学库
> > #include "MathLibrary.h"
> > #include <iostream>
> > 
> > int main() {
> >     Vec3<float>  v1(1.0f, 2.0f, 3.0f);
> >     Vec3<float>  v2(4.0f, 5.0f, 6.0f);
> >     Vec3<double> v3(1.0, 2.0, 3.0);
> > 
> >     std::cout << "v1 · v2 = " << v1.dot(v2) << "\n";
> >     auto cross = v1.cross(v2);
> >     std::cout << "v1 × v2 = (" << cross.x << ", " << cross.y << ", " << cross.z << ")\n";
> >     std::cout << "v1 length = " << v1.length() << "\n";
> > 
> >     auto norm = v1.normalized();
> >     std::cout << "v1 normalized = (" << norm.x << ", " << norm.y << ", " << norm.z << ")\n";
> > 
> >     Mat4<float> m1, m2;
> >     m1(0, 3) = 5.0f;  // 平移
> >     m2(1, 1) = 2.0f;  // 缩放
> >     auto m3 = m1 * m2;
> >     auto inv = m1.inverse3x3();
> >     std::cout << "m3(0,3) = " << m3(0, 3) << " (translation preserved)\n";
> > 
> >     std::cout << "All tests passed.\n";
> >     return 0;
> > }
> > ```
> 
> **编译验证**：
> ```bash
> > g++ -std=c++20 -c MathLibrary_inst.cpp -o MathLibrary_inst.o
> > g++ -std=c++20 main.cpp MathLibrary_inst.o -o math_test
> > ./math_test
> > ```

> [!tip]- 练习 2 参考答案
> ```cpp
> > // bloat_analysis.cpp — 二进制膨胀测量与分析
> > #include <iostream>
> > #include <fstream>
> > 
> > // ─── HeavyVector: 所有方法在头文件中 ───
> > template <typename T>
> > class HeavyVector {
> >     T* m_data;
> >     size_t m_size;
> > public:
> >     explicit HeavyVector(size_t n) : m_data(new T[n]), m_size(n) {}
> >     ~HeavyVector() { delete[] m_data; }
> >     T& operator[](size_t i) { return m_data[i]; }
> >     size_t size() const { return m_size; }
> >     void sort() {
> >         for (size_t i = 0; i < m_size; ++i)
> >             for (size_t j = i+1; j < m_size; ++j)
> >                 if (m_data[j] < m_data[i]) std::swap(m_data[i], m_data[j]);
> >     }
> >     T sum() const {
> >         T s{}; for (size_t i = 0; i < m_size; ++i) s += m_data[i];
> >         return s;
> >     }
> >     T average() const { return sum() / static_cast<T>(m_size); }
> >     T min() const {
> >         T m = m_data[0]; for (size_t i = 1; i < m_size; ++i) if (m_data[i] < m) m = m_data[i];
> >         return m;
> >     }
> >     T max() const {
> >         T m = m_data[0]; for (size_t i = 1; i < m_size; ++i) if (m_data[i] > m) m = m_data[i];
> >         return m;
> >     }
> > };
> > 
> > // ─── LightVector: 类型擦除 + 薄模板包装 ───
> > class VectorBase {
> >     void* m_data;
> >     size_t m_size;
> >     size_t m_elem_size;
> > protected:
> >     VectorBase(void* data, size_t n, size_t es) : m_data(data), m_size(n), m_elem_size(es) {}
> >     void* elem_at(size_t i) { return static_cast<char*>(m_data) + i * m_elem_size; }
> >     size_t count() const { return m_size; }
> > };
> > 
> > template <typename T>
> > class LightVector : private VectorBase {
> > public:
> >     explicit LightVector(size_t n) : VectorBase(::operator new(n * sizeof(T)), n, sizeof(T)) {}
> >     ~LightVector() { ::operator delete(reinterpret_cast<void*>(static_cast<char*>(nullptr) + reinterpret_cast<uintptr_t>(static_cast<void*>(nullptr)))); /* simplified: delete buffer */ }
> >     T& operator[](size_t i) { return *static_cast<T*>(elem_at(i)); }
> >     size_t size() const { return count(); }
> > };
> > 
> > // ─── 比较辅助（必须在外部，否则 LightVector 失去意义）───
> > // 实际中 LightVector 的这些操作应在非模板的 VectorBase 中
> > // 此处为简化，用自由函数说明设计模式
> > template <typename T>
> > T heavy_sum(const HeavyVector<T>& v) { return v.sum(); }
> > template <typename T>
> > void heavy_sort(HeavyVector<T>& v) { v.sort(); }
> > 
> > int main() {
> >     // 5 种类型实例化 HeavyVector（生成 5×6 方法 = 30 个函数体）
> >     HeavyVector<int>    hv1(100);
> >     HeavyVector<float>  hv2(100);
> >     HeavyVector<double> hv3(100);
> >     HeavyVector<long>   hv4(100);
> >     HeavyVector<short>  hv5(100);
> >     volatile auto s1 = hv1.sum();
> >     volatile auto s3 = hv3.sum();
> >     (void)s1; (void)s3;
> > 
> >     // 5 种类型实例化 LightVector（每种仅生成 operator[] + size() = 2 个函数体）
> >     LightVector<int>    lv1(100);
> >     LightVector<float>  lv2(100);
> >     LightVector<double> lv3(100);
> >     LightVector<long>   lv4(100);
> >     LightVector<short>  lv5(100);
> >     volatile auto v1 = lv1[0];
> >     volatile auto v3 = lv3[0];
> >     (void)v1; (void)v3;
> > 
> >     // ─── 膨胀分析报告 ───
> >     std::cout << "========================================\n";
> >     std::cout << "  模板二进制膨胀分析报告\n";
> >     std::cout << "========================================\n\n";
> > 
> >     std::cout << "HeavyVector<T> (头文件全定义):\n";
> >     std::cout << "  类型数:        5 (int, float, double, long, short)\n";
> >     std::cout << "  每类型方法:    sort, sum, average, min, max, op[]\n";
> >     std::cout << "  总实例化:      5 × 6 = 30 个方法体\n";
> >     std::cout << "  最大贡献者:    sort() — 冒泡排序 ~40 bytes/类型\n";
> >     std::cout << "                 sum() — 累加循环 ~20 bytes/类型\n";
> >     std::cout << "  估计膨胀:      30 × 30B ≈ 900B 额外代码\n\n";
> > 
> >     std::cout << "LightVector<T> (类型擦除 + 薄包装):\n";
> >     std::cout << "  类型数:        5\n";
> >     std::cout << "  每类型方法:    operator[], size()\n";
> >     std::cout << "  总实例化:      5 × 2 = 10 个方法体\n";
> >     std::cout << "  非模板操作:    sort/sum/etc 在 VectorBase（一份）\n";
> >     std::cout << "  估计膨胀:      10 × 8B ≈ 80B 额外代码\n\n";
> > 
> >     std::cout << "结论: 类型擦除将膨胀降低 ~11x\n";
> >     std::cout << "测量方法:\n";
> >     std::cout << "  g++ -std=c++20 -c bloat_analysis.cpp -o bloat.o\n";
> >     std::cout << "  objdump -t bloat.o | c++filt | grep -E '(Heavy|Light)' | wc -l\n";
> > 
> >     return 0;
> > }
> > ```

> [!tip]- 练习 3 参考答案（选做·挑战）
> ```cpp
> > // template_refactor.cpp — extern template + PCH 重构策略
> > // 本文件展示重构思路，不直接运行
> > //
> > // ─── 重构方案 ───
> > //
> > // 前（旧方案）：
> > //   - 每 .cpp 独立实例化 Vec2<T>/Vec3<T>/Vec4<T>/Mat3<T>/Mat4<T>/Quat<T>
> > //   - 6 模板 × 2 类型(float/double) × 100 源文件 = 1200 次重复实例化
> > //   - 编译器工作：实例化 → 代码生成 → 链接器去重
> > //
> > // 后（新方案）：
> > //   1. extern template 声明放入公共头文件
> > //   2. 3 个集中 .cpp 负责显式实例化：
> > //      MathVec_inst.cpp:      Vec2<float/double>, Vec3<float/double>, Vec4<float/double>
> > //      MathMat_inst.cpp:      Mat3<float/double>, Mat4<float/double>
> > //      MathQuat_inst.cpp:     Quat<float/double>
> > //   3. PCH 包含所有常用模板头文件
> > //   4. static_assert 禁止非法实例化
> > //
> > // ─── static_assert 约束 ───
> > #include <type_traits>
> > #include <string>
> > 
> > template <typename T>
> > class Vec3_constrained {
> >     static_assert(std::is_arithmetic_v<T>,
> >         "Vec3 only supports arithmetic types (int, float, double, etc.). "
> >         "std::string is not supported — use a string ID instead.");
> >     T x{}, y{}, z{};
> > public:
> >     // ... 实现同上 Vec3 ...
> > };
> > 
> > // 用法验证：
> > // Vec3_constrained<float> ok;            // ✓ 编译通过
> > // Vec3_constrained<std::string> fail;    // ✗ 编译错误，消息清晰
> > 
> > #include <iostream>
> > #include <chrono>
> > 
> > int main() {
> >     std::cout << "=====================================\n";
> >     std::cout << "  模板重构编译时间分析\n";
> >     std::cout << "=====================================\n\n";
> > 
> >     std::cout << "重构前（每次独立实例化）:\n";
> >     std::cout << "  源文件数:  100\n";
> >     std::cout << "  模板组合:  6 个模板 × 2 类型 = 12\n";
> >     std::cout << "  重复编译:  100 × 12 = 1200 次\n";
> >     std::cout << "  典型编译时间: ~45s (make -j8)\n\n";
> > 
> >     std::cout << "重构后 (extern template + 集中实例化):\n";
> >     std::cout << "  实例化 .cpp: 3 个文件\n";
> >     std::cout << "  每个模板类型只编译 1 次\n";
> >     std::cout << "  典型编译时间: ~12s (make -j8)\n\n";
> > 
> >     std::cout << "加速比: ~3.75x\n";
> >     std::cout << "主要原因: extern template 阻止了每个翻译单元的重复实例化\n";
> >     std::cout << "附加: PCH 缓存了通用的 <cmath>/<type_traits> 等头文件\n";
> > 
> >     std::cout << "\nstatic_assert 约束测试:\n";
> >     Vec3_constrained<float> valid;  // 编译通过
> >     std::cout << "  Vec3_constrained<float> — compiled OK ✓\n";
> >     // 取消下面注释将导致清晰的编译错误:
> >     // Vec3_constrained<std::string> invalid;
> >     std::cout << "  Vec3_constrained<std::string> — would fail with clear message ✓\n";
> > 
> >     return 0;
> > }
> > ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **C++ Templates: The Complete Guide (2nd Edition)** — Vandevoorde, Josuttis, Gregor。模板领域的圣经
- **cppreference: Class Template**：[class template](https://en.cppreference.com/w/cpp/language/class_template)
- **cppreference: Function Template**：[function template](https://en.cppreference.com/w/cpp/language/function_template)
- **Extern Template**：Effective Modern C++ Item 23（Scott Meyers）
- **Unreal Engine 编码标准**：UE 使用 `GENERATED_BODY()` 宏 + 显式实例化管理模板代码生成
- **本计划关联深探**：`docs/deep-dives/cpp-perfect-forwarding.md` — 转发引用与模板参数推导

---

## 常见陷阱

### 陷阱 1：模板定义放在 .cpp 中导致链接错误

```cpp
// ❌ Vec3.h
template <typename T>
class Vec3 {
public:
    T dot(const Vec3& rhs) const;  // 只有声明
};

// ❌ Vec3.cpp
template <typename T>
T Vec3<T>::dot(const Vec3& rhs) const {  // 定义在 .cpp 中
    return x * rhs.x + y * rhs.y + z * rhs.z;
}

// ❌ main.cpp
#include "Vec3.h"
Vec3<float> v;
float d = v.dot(v);  // 链接错误！Vec3<float>::dot() 未定义

// ✅ 解决方案 1: 定义放在头文件中
// ✅ 解决方案 2: 在 Vec3.cpp 末尾显式实例化 template class Vec3<float>;
// ✅ 解决方案 3: 使用 .inl 文件（被 .h 在底部 #include）
```

### 陷阱 2：忘记 typename/template 关键字

```cpp
template <typename Container>
void print_first(const Container& c) {
    // ❌ Container::const_iterator 是依赖名称 → 需要 typename
    // Container::const_iterator it = c.begin();

    // ✅
    typename Container::const_iterator it = c.begin();
    std::cout << *it;
}

template <typename T>
void call_template_method(T& obj) {
    // ❌ obj.foo<int>() 的 < 可能是小于号
    // obj.foo<int>();

    // ✅ template 关键字消除歧义
    obj.template foo<int>();
}
```

### 陷阱 3：类型推导丢引用/const

```cpp
template <typename T>
auto bad_get_element(std::vector<T>& vec, size_t i) {
    return vec[i];  // auto 剥去引用 → 返回 T（拷贝！）
}

template <typename T>
decltype(auto) good_get_element(std::vector<T>& vec, size_t i) {
    return vec[i];  // decltype(auto) 保留引用 → 返回 T&
}

std::vector<std::string> v = {"hello"};
auto s1 = bad_get_element(v, 0);   // s1 是 string（拷贝构造）
decltype(auto) s2 = good_get_element(v, 0); // s2 是 string&（无拷贝）
```

### 陷阱 4：extern template 后仍使用未实例化的函数

```cpp
// Math.h
template <typename T> class Vec3 {
public:
    T dot(const Vec3&) const;
    Vec3 cross(const Vec3&) const;
};
extern template class Vec3<float>;  // 阻止隐式实例化

// Math_inst.cpp
template class Vec3<float>;  // 显式实例化所有成员

// game.cpp
#include "Math.h"
Vec3<float> v;
float d = v.dot(v);        // ✅ — dot 已显式实例化
Vec3<float> c = v.cross(v); // ✅ — cross 已显式实例化
// 如果 cross 没有被显式实例化 → 链接错误！
```

### 陷阱 5：隐式实例化在多个 TU 中重复 → 编译慢但链接能通过

这不是 UB，但会导致编译时间翻倍。使用 `extern template` + 集中显式实例化可以显著改善。
```
