# SFINAE 与 C++20 Concepts

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 模板基础与实例化模型（第 13 节）
> C++ 标准: C++98（SFINAE 起源）、C++11（enable_if、void_t）、C++14（enable_if_t 别名）、C++17（if constexpr、is_detected）、C++20（Concepts）

---

## 1. 概念讲解

### 1.1 SFINAE 原理

SFINAE（Substitution Failure Is Not An Error，替换失败不是错误）是 C++ 模板系统中最强大也最令人困惑的机制之一。它的核心含义是：

> 当模板参数替换导致语法无效时，编译器**不报错**，而是**将这个候选从重载集中移除**，然后继续尝试其他候选。

```cpp
// 两个重载，编译器根据 SFINAE 选择正确的版本
template <typename T>
typename T::value_type sum(const T& container) {  // 候选 1
    typename T::value_type total{};
    for (const auto& v : container) total += v;
    return total;
}

template <typename T>
T sum(T a, T b) {  // 候选 2
    return a + b;
}

std::vector<int> v = {1, 2, 3};
int r1 = sum(v);    // T = vector<int> → 候选 1: vector<int>::value_type = int ✓
                    //                   候选 2: vector<int> + vector<int> → 无效 ✓
                    //               → 选择候选 1

int r2 = sum(3, 4); // T = int → 候选 1: int::value_type → 替换失败，静默丢弃
                    //           候选 2: int + int → 有效
                    //         → 选择候选 2
```

没有 SFINAE 的话，编译器在尝试 `int::value_type` 时就会终止并报错。有了 SFINAE，它只是默默跳过这个候选，继续寻找下一个重载。

**SFINAE 的适用场景**：只发生在**函数模板重载解析**期间的**直接替换失败**。以下情况不算 SFINAE：

- 模板定义本身的语法错误（如少写分号）→ 硬错误
- 模板特化中的错误 → 硬错误
- 函数体内部的错误 → 硬错误（SFINAE 只看签名）

### 1.2 std::enable_if — 经典 SFINAE 手段（C++11）

`enable_if` 通过条件性地使返回类型"非法"来实现重载选择：

```cpp
// enable_if 的基本形态
template <bool Condition, typename T = void>
struct enable_if {};

template <typename T>
struct enable_if<true, T> { using type = T; };

// C++14 别名
template <bool C, typename T = void>
using enable_if_t = typename enable_if<C, T>::type;

// ─── 使用示例 ───
// 版本 1: 当 T 是整数时启用
template <typename T>
enable_if_t<std::is_integral_v<T>, T>
divide(T a, T b) {
    return a / b;  // 整数除法
}

// 版本 2: 当 T 是浮点数时启用
template <typename T>
enable_if_t<std::is_floating_point_v<T>, T>
divide(T a, T b) {
    return a / b;  // 浮点除法（同样的表达式，但语义不同）
}
```

**`enable_if` 的四种常见位置**：

```cpp
// 1. 返回类型（最常用）
template <typename T>
enable_if_t<std::is_integral_v<T>, bool>
is_power_of_two(T x) { return (x & (x - 1)) == 0; }

// 2. 模板参数（C++11 风格）
template <typename T, typename = enable_if_t<std::is_integral_v<T>>>
void process(T val);

// 3. 非类型模板参数
template <typename T, enable_if_t<std::is_integral_v<T>, int> = 0>
void process(T val);

// 4. 函数参数（C++11/14）
template <typename T>
void process(T val, enable_if_t<std::is_integral_v<T>>* = nullptr);
```

### 1.3 void_t 检测惯用法（C++17）

`void_t` 是 SFINAE 的增强工具——它可以检测一个类型**是否拥有**某个成员、方法或操作：

```cpp
// void_t 只要所有模板参数都合法，就产生 void
template <typename...>
using void_t = void;

// ─── 检测是否有 render() 方法 ───
template <typename T, typename = void>
struct has_render : std::false_type {};

template <typename T>
struct has_render<T, void_t<decltype(std::declval<T>().render())>>
    : std::true_type {};

template <typename T>
inline constexpr bool has_render_v = has_render<T>::value;

// ─── 使用 ───
struct Mesh { void render() {} };
struct Texture { void bind() {} };

static_assert(has_render_v<Mesh>);     // ✓
static_assert(!has_render_v<Texture>); // ✓ — Texture 有 bind() 但没有 render()

// ─── 更复杂的检测：是否有 serialize(Archive&) ───
template <typename T, typename Archive, typename = void>
struct is_serializable : std::false_type {};

template <typename T, typename Archive>
struct is_serializable<T, Archive,
    void_t<decltype(std::declval<T>().serialize(std::declval<Archive&>()))>>
    : std::true_type {};
```

### 1.4 if constexpr — 编译期分支（C++17）

`if constexpr` 是 C++17 引入的**编译期条件判断**，它在很多场景下比 SFINAE 更简洁：

```cpp
// ─── SFINAE 方式（C++11）───
template <typename T>
enable_if_t<std::is_integral_v<T>, T> get_value(T val) {
    return val;
}
template <typename T>
enable_if_t<!std::is_integral_v<T>, T> get_value(T val) {
    return val;  // 两段完全相同的代码！
}

// ─── if constexpr 方式（C++17）───
template <typename T>
T get_value(T val) {
    if constexpr (std::is_integral_v<T>) {
        // 编译器丢弃未选中的分支 → 该分支不会实例化
        return val & 0xFF;  // 仅对整数有效
    } else {
        return val;          // 对非整数有效
    }
}
```

**关键区别**：`if constexpr` 被丢弃的分支**完全不会被实例化**。这意味着你可以在一段代码中混合在常规 `if` 下不能混用的类型：

```cpp
template <typename T>
auto serialize(T& obj, std::vector<uint8_t>& out) {
    if constexpr (std::is_trivially_copyable_v<T>) {
        // 对平凡拷贝类型：直接 memcpy（高效）
        out.resize(out.size() + sizeof(T));
        std::memcpy(out.data() + out.size() - sizeof(T), &obj, sizeof(T));
    } else {
        // 对复杂类型：调用 serialize 方法
        obj.serialize(out);
    }
}
```

在常规 `if` 中，两个分支都必须对给定 T 编译通过，而 `if constexpr` 只要求被选中的分支编译通过。

### 1.5 C++20 Concepts — SFINAE 的现代替代

C++20 引入了 Concepts，它用**声明式约束**替代了 SFINAE 的晦涩模板技巧。错误消息从"100 行模板噪声"变为"1 行清晰的约束失败报告"。

```cpp
// ─── 定义一个 Concept ───
template <typename T>
concept Renderable = requires(T obj) {
    { obj.render() } -> std::same_as<void>;  // render() 必须返回 void
};

// ─── 使用 Concept 约束模板 ───
// 方式 1: requires 子句
template <typename T>
requires Renderable<T>
void draw(const T& obj) {
    obj.render();
}

// 方式 2: Concept 代替 typename（简洁形式）
template <Renderable T>
void draw(const T& obj) {
    obj.render();
}

// 方式 3: 缩写函数模板（最简洁 — C++20）
void draw(const Renderable auto& obj) {
    obj.render();
}

// ─── 调用 ───
struct Mesh { void render() {} };
struct Texture { void bind() {} };

draw(Mesh{});     // ✓ — Mesh 满足 Renderable
// draw(Texture{}); // ✗ — Texture::render() 不存在
// 错误消息: "Texture does not satisfy concept Renderable"
```

### 1.6 标准 Concepts（C++20）

标准库在 `<concepts>` 中提供了一组预定义的 Concepts：

| Concept | 含义 | 游戏引擎用途 |
|---------|------|------------|
| `std::integral<T>` | T 是整数类型 | 限制网格索引、位运算参数 |
| `std::floating_point<T>` | T 是浮点类型 | 限制数学库类型 |
| `std::signed_integral<T>` | T 是有符号整数 | 限制需要负值的参数 |
| `std::unsigned_integral<T>` | T 是无符号整数 | 限制数组索引、位集 |
| `std::same_as<T, U>` | T 和 U 是同一类型 | 确保类型一致性 |
| `std::derived_from<T, Base>` | T 继承自 Base | 限制组件/实体继承关系 |
| `std::convertible_to<T, U>` | T 可隐式转换为 U | 确保 API 兼容性 |
| `std::movable<T>` | T 可移动 | 限制容器元素类型 |
| `std::copyable<T>` | T 可拷贝 | 限制值语义类型 |
| `std::semiregular<T>` | T 可默认构造+拷贝 | 标准容器元素要求 |
| `std::regular<T>` | T 满足 equality 比较 | 值类型完整性要求 |

### 1.7 错误消息对比：SFINAE vs Concepts

```
// ─── SFINAE 版本 ───
template <typename T>
enable_if_t<has_render_v<T> && is_serializable_v<T>, void>
process_asset(T& asset) { /* ... */ }

// 当 T 不满足条件时，错误消息类似：
// error: no matching function for call to 'process_asset(Texture&)'
// note: template argument deduction/substitution failed:
// note: the expression 'enable_if_t<false, void>' evaluated to 'false'
// note:   in instantiation of 'process_asset<Texture>'
// ... 数十行模板回溯 ...

// ─── Concepts 版本 ───
template <typename T>
concept Asset = requires(T a) {
    { a.render() } -> std::same_as<void>;
    { a.serialize(std::declval<std::vector<uint8_t>&>()) } -> std::same_as<void>;
};

template <Asset T>
void process_asset(T& asset) { /* ... */ }

// 当 T 不满足条件时，错误消息类似：
// error: no matching function for call to 'process_asset(Texture&)'
// note: the associated constraints are not satisfied
// note: the expression 'a.serialize(...)' is invalid
```

### 1.8 引擎中的 SFINAE/Concepts 实战模式

**模式 1：编译期组件类型验证**

```cpp
template <typename T>
concept Component = std::semiregular<T> && requires {
    typename T::Family;  // 每个组件必须有 Family 类型别名
};

template <Component T>
class ComponentManager { /* 只接受满足 Component 的类型 */ };
```

**模式 2：数学类型约束**

```cpp
template <typename T>
concept MathScalar = std::is_arithmetic_v<T> && !std::is_same_v<T, bool>;

template <MathScalar T>
class Vec3 { /* 只接受算术类型，排除 bool */ };
```

**模式 3：迭代器约束**

```cpp
template <typename T>
concept GameEntityIterator = std::forward_iterator<T> &&
    requires(T it) {
        { it->get_position() } -> std::convertible_to<Vec3f>;
    };
```

---

## 2. 代码示例

### 2.1 SFINAE 组件检测器

```cpp
// sfinae_component_detector.cpp — 完整的 SFINAE/Concepts 实战
// 编译: g++ -std=c++20 -O2 sfinae_demo.cpp -o sfinae_demo

#include <iostream>
#include <type_traits>
#include <vector>
#include <string>
#include <concepts>
#include <memory>
#include <cstring>

// ============================================================
// 1. void_t 检测惯用法 — 检测方法是否存在
// ============================================================

// 通用 void_t
template <typename...>
using void_t = void;

// ─── 检测 render() ───
template <typename, typename = void>
struct has_render : std::false_type {};

template <typename T>
struct has_render<T, void_t<decltype(std::declval<const T&>().render())>>
    : std::true_type {};

template <typename T>
inline constexpr bool has_render_v = has_render<T>::value;

// ─── 检测 serialize(Archive&) ───
template <typename T, typename Archive, typename = void>
struct has_serialize : std::false_type {};

template <typename T, typename Archive>
struct has_serialize<T, Archive,
    void_t<decltype(std::declval<T&>().serialize(std::declval<Archive&>()))>>
    : std::true_type {};

template <typename T, typename Archive>
inline constexpr bool has_serialize_v = has_serialize<T, Archive>::value;

// ─── 检测 C 风格数组大小（编译期）───
template <typename, typename = void>
struct array_size : std::integral_constant<size_t, 0> {};

template <typename T>
struct array_size<T, void_t<decltype(sizeof(T) / sizeof(std::declval<T>()[0]))>>
    : std::integral_constant<size_t, std::extent_v<T>> {};

// ─── 检测是否有 value_type（如 STL 容器）───
template <typename, typename = void>
struct has_value_type : std::false_type {};

template <typename T>
struct has_value_type<T, void_t<typename T::value_type>>
    : std::true_type {};

// ============================================================
// 2. enable_if 分发 — 根据类型特征选择不同实现
// ============================================================

// ─── 对整数：使用位运算 ───
template <typename T>
std::enable_if_t<std::is_integral_v<T>, bool>
is_power_of_two(T x) {
    return x > 0 && (x & (x - 1)) == 0;
}

// ─── 对浮点数：使用数学方式 ───
template <typename T>
std::enable_if_t<std::is_floating_point_v<T>, bool>
is_power_of_two(T x) {
    if (x <= 0) return false;
    int exp;
    std::frexp(x, &exp);
    T mantissa = std::ldexp(x, -exp);
    return mantissa == 1.0;  // 尾数为 1.0 说明是 2 的幂
}

// ─── 类型驱动的分配器选择 ───
template <typename T>
std::enable_if_t<std::is_trivially_destructible_v<T>, void>
cleanup(T* data, size_t count) {
    // 平凡析构：什么都不做（最快）
    std::cout << "  cleanup: trivial (no-op)\n";
}

template <typename T>
std::enable_if_t<!std::is_trivially_destructible_v<T>, void>
cleanup(T* data, size_t count) {
    // 非平凡析构：逐个析构
    std::cout << "  cleanup: calling destructors for " << count << " items\n";
    for (size_t i = 0; i < count; ++i) {
        data[i].~T();
    }
}

// ============================================================
// 3. Tag Dispatch — 用空标签选择重载
// ============================================================

struct cpu_tag {};
struct sse_tag {};
struct avx_tag {};

// 根据 CPU 特性选择 SIMD 实现
template <typename T>
void matrix_multiply_impl(const T* A, const T* B, T* C, int N, cpu_tag) {
    // 标量实现
    for (int i = 0; i < N; ++i)
        for (int j = 0; j < N; ++j) {
            C[i * N + j] = 0;
            for (int k = 0; k < N; ++k)
                C[i * N + j] += A[i * N + k] * B[k * N + j];
        }
}

#ifdef __SSE__
void matrix_multiply_impl(const float* A, const float* B, float* C, int N, sse_tag) {
    // SSE 矩阵乘法（简化为向量点积）
    for (int i = 0; i < N; ++i)
        for (int j = 0; j < N; ++j) {
            __m128 sum = _mm_setzero_ps();
            for (int k = 0; k < N; k += 4) {
                __m128 a = _mm_loadu_ps(&A[i * N + k]);
                __m128 b = _mm_loadu_ps(&B[k * N + j]);
                sum = _mm_add_ps(sum, _mm_mul_ps(a, b));
            }
            float tmp[4];
            _mm_storeu_ps(tmp, sum);
            C[i * N + j] = tmp[0] + tmp[1] + tmp[2] + tmp[3];
        }
}
#endif

// ─── 标签分发入口 ───
template <typename T>
void matrix_multiply(const T* A, const T* B, T* C, int N) {
    if constexpr (std::is_same_v<T, float>) {
#ifdef __AVX__
        matrix_multiply_impl(A, B, C, N, avx_tag{});
#elif defined(__SSE__)
        matrix_multiply_impl(A, B, C, N, sse_tag{});
#else
        matrix_multiply_impl(A, B, C, N, cpu_tag{});
#endif
    } else {
        matrix_multiply_impl(A, B, C, N, cpu_tag{});
    }
}

// ============================================================
// 4. C++20 Concepts — 引擎数学类型约束
// ============================================================

// 定义引擎数学标量类型 Concept
template <typename T>
concept MathScalar = std::is_arithmetic_v<T> && !std::is_same_v<T, bool>;

// 定义可迭代对象 Concept
template <typename T>
concept Iterable = requires(T& c) {
    typename T::iterator;
    { c.begin() } -> std::same_as<typename T::iterator>;
    { c.end() }   -> std::same_as<typename T::iterator>;
};

// 定义 ECS 组件 Concept
template <typename T>
concept ECComponent = std::semiregular<T> && requires {
    typename T::Family;  // 每个组件必须定义 Family 类型
    { T::Family::id } -> std::convertible_to<size_t>;
};

// 定义可渲染对象 Concept
template <typename T>
concept RenderableObject = requires(const T& obj) {
    { obj.render() } -> std::same_as<void>;
    { obj.get_mesh_id() } -> std::convertible_to<int>;
};

// ─── 使用 Concepts 约束模板 ───
template <MathScalar T>
class MathVec3 {
    T m_data[3];
public:
    constexpr MathVec3(T x, T y, T z) : m_data{x, y, z} {}

    constexpr T dot(const MathVec3& rhs) const {
        return m_data[0] * rhs.m_data[0]
             + m_data[1] * rhs.m_data[1]
             + m_data[2] * rhs.m_data[2];
    }

    // operator== 自动定义
    constexpr bool operator==(const MathVec3&) const = default;
};

// ─── 约束渲染系统 ───
class RenderSystem {
    std::vector<int> m_visible_meshes;
public:
    template <RenderableObject T>
    void submit(const T& obj) {
        m_visible_meshes.push_back(obj.get_mesh_id());
    }

    void draw_all() {
        // 提交给 GPU...
        std::cout << "Drawing " << m_visible_meshes.size() << " meshes\n";
    }
};

// ============================================================
// 5. 编译期验证的 ECS 组件注册系统
// ============================================================

// 演示类型
struct Position { float x, y, z; };
struct Velocity { float vx, vy, vz; };

// 组件 Family 定义
template <typename T>
struct ComponentFamily {
    static constexpr size_t id = []() {
        static size_t next_id = 0;
        return next_id++;
    }();
};

// 改造演示类型使其满足 ECComponent Concept
struct ECS_Position : Position {
    using Family = ComponentFamily<ECS_Position>;
};
struct ECS_Velocity : Velocity {
    using Family = ComponentFamily<ECS_Velocity>;
};
struct ECS_Health {
    float hp;
    using Family = ComponentFamily<ECS_Health>;
};

// 组件注册 — 编译期验证
template <ECComponent... Components>
class ComponentRegistry {
public:
    static constexpr size_t count = sizeof...(Components);

    static void print_registered() {
        std::cout << "Registered " << count << " component(s)\n";
        ((std::cout << "  Component[" << Components::Family::id << "]\n"), ...);
    }
};

// ============================================================
// 6. requires 表达式 — 精细约束
// ============================================================

// 约束：类型必须可哈希
template <typename T>
concept Hashable = requires(T a) {
    { std::hash<T>{}(a) } -> std::convertible_to<size_t>;
};

// 约束：类型必须可比较相等
template <typename T>
concept EqualityComparable = requires(const T& a, const T& b) {
    { a == b } -> std::convertible_to<bool>;
    { a != b } -> std::convertible_to<bool>;
};

// 约束：可排序（组合多个 Concept）
template <typename T>
concept Sortable = EqualityComparable<T> && requires(T a, T b) {
    { a < b } -> std::convertible_to<bool>;
};

// ─── 使用组合 Concept ───
template <Sortable T>
void engine_sort(std::vector<T>& items) {
    std::sort(items.begin(), items.end());  // 需要 operator<
}

// ─── Concept 约束 auto 参数 ───
void debug_print(const Sortable auto& value) {
    std::cout << "Value is sortable\n";
}
```

### 2.2 主演示函数

```cpp
int main() {
    std::cout << "========== SFINAE 与 C++20 Concepts ==========\n\n";

    // ─── 1. void_t 检测 ───
    std::cout << "--- void_t 检测 ---\n";
    struct WithRender    { void render() const {} };
    struct WithoutRender { void bind() const {} };

    std::cout << "WithRender has render():    " << has_render_v<WithRender> << "\n";
    std::cout << "WithoutRender has render(): " << has_render_v<WithoutRender> << "\n";
    std::cout << "int has value_type:         " << has_value_type<int>::value << "\n";
    std::cout << "vector<int> has value_type: " << has_value_type<std::vector<int>>::value << "\n\n";

    // ─── 2. enable_if 分发 ───
    std::cout << "--- enable_if 分发 ---\n";
    std::cout << "is_power_of_two(64):   " << is_power_of_two(64) << "\n";
    std::cout << "is_power_of_two(100):  " << is_power_of_two(100) << "\n";
    std::cout << "is_power_of_two(0.25): " << is_power_of_two(0.25) << "\n\n";

    // ─── 3. cleanup 选择 ───
    std::cout << "--- cleanup 类型驱动选择 ---\n";
    cleanup(reinterpret_cast<int*>(0x1000), 100);     // int 是平凡析构
    cleanup(reinterpret_cast<std::string*>(0x2000), 100); // string 不是
    std::cout << "\n";

    // ─── 4. Concepts 约束 ───
    std::cout << "--- C++20 Concepts 约束 ---\n";

    // MathVec3 只接受算术类型
    MathVec3<float> v1(1.0f, 2.0f, 3.0f);
    MathVec3<float> v2(4.0f, 5.0f, 6.0f);
    std::cout << "v1·v2 = " << v1.dot(v2) << "\n";

    // MathVec3<bool> v3(true, false, true);  // ❌ bool 被 MathScalar 排除

    // ─── 5. ECS 组件注册 ───
    std::cout << "\n--- ECS 组件注册 ---\n";
    using GameComponents = ComponentRegistry<ECS_Position, ECS_Velocity, ECS_Health>;
    GameComponents::print_registered();

    // ─── 6. Sortable Concept ───
    std::cout << "\n--- Sortable Concept ---\n";
    std::vector<int> nums = {5, 2, 8, 1, 9};
    engine_sort(nums);  // int 满足 Sortable
    std::cout << "Sorted: ";
    for (int n : nums) std::cout << n << " ";
    std::cout << "\n";

    // 下面一行会编译失败（带清晰的错误消息）：
    // struct NonSortable {};
    // std::vector<NonSortable> bad;
    // engine_sort(bad);  // ✗ NonSortable 不满足 Sortable → 清晰的 Concept 错误

    debug_print(42);
    debug_print(3.14);

    return 0;
}
```

---

## 3. 练习

### 练习 1（必做）：编写检测 T 是否有 serialize() 方法的类型特征

1. 使用 `void_t` 惯用法实现 `has_serialize<T, Archive>` 特征
2. 实现两个版本：一个检测 `serialize(Archive&)`，另一个检测 `serialize(const Archive&)`
3. 编写 `serialize_to_file<T>(const T& obj, const char* path)` 函数：
   - 如果 T 有 `serialize` 方法，调用它
   - 如果 T 是 `std::is_trivially_copyable`，使用 `fwrite`
   - 否则使用 `static_assert` 报错（友好的错误消息）
4. 测试至少三种类型：`Mesh`（有 serialize）、`int`（平凡可拷贝）、`std::vector<float>`（两者都不是）

### 练习 2（必做）：将 SFINAE 分发器重构为 C++20 Concepts

1. 给定以下 SFINAE 代码，将其重写为使用 C++20 Concepts：

```cpp
template <typename T>
enable_if_t<has_render_v<T>, void>
render_object(const T& obj) { obj.render(); }

template <typename T>
enable_if_t<!has_render_v<T> && has_value_type<T>::value, void>
render_object(const T& container) {
    for (const auto& elem : container) render_object(elem);
}
```

2. 定义 `Renderable` Concept（要求 `render()` 返回 void）
3. 定义 `RenderableContainer` Concept（要求是容器且元素满足 `Renderable`）
4. 比较重构前后的错误消息质量
5. 添加 `static_assert` 在无匹配重载时提供友好的错误消息

### 练习 3（选做·挑战）：构建编译期验证的 ECS 组件注册系统

1. 定义 Component Concept：要求类型有 `using Family = ComponentFamily<Self>;` 且 `Family::id` 是编译期常量
2. 定义 System Concept：要求类型有 `update(float dt)` 方法且有 `using RequiredComponents = TypeList<...>;`
3. 实现 `ComponentManager`，使用 `if constexpr` 和 `requires` 验证所有注册的组件满足 Component
4. 实现编译期检查：当 System 试图使用未注册的组件时，产生清晰的编译错误
5. 使用 `static_assert` 验证所有注册类型满足约束
6. 编写测试：正确注册的组件系统 → 编译通过；错误组件 → 清晰的编译错误

---

## 4. 扩展阅读

- **cppreference: SFINAE**：[SFINAE](https://en.cppreference.com/w/cpp/language/sfinae)
- **cppreference: Concepts**：[Constraints and Concepts](https://en.cppreference.com/w/cpp/language/constraints)
- **cppreference: `<concepts>`**：[Standard Concepts Library](https://en.cppreference.com/w/cpp/concepts)
- **Walter Brown's void_t talk (CppCon 2014)**："Modern Template Metaprogramming: A Compendium" — void_t 的经典之作
- **Andrei Alexandrescu, "Modern C++ Design"**：Policy-based design 和 Type Lists
- **Eric Niebler, "Concepts: The Future of Generic Programming" (CppCon 2018)**：Concepts 的设计哲学
- **本计划关联**：第 17 节 "constexpr 与编译期计算"将进一步探索编译期编程

---

## 常见陷阱

### 陷阱 1：SFINAE 不覆盖函数体错误

```cpp
template <typename T>
auto process(T val) -> decltype(val.method()) {
    return val.method() + non_existent_var;  // ❌ 硬错误！SFINAE 不保护函数体
}

// SFINAE 只在函数签名（返回类型、参数类型）的替换阶段生效。
// 函数体是实例化阶段才检查的，此时替换已经成功 → 硬错误。
```

### 陷阱 2：enable_if 的重载歧义

```cpp
// 两个 enable_if 条件互补，但可能同时满足！
template <typename T>
enable_if_t<std::is_integral_v<T>, void> f(T) {}      // ①

template <typename T>
enable_if_t<std::is_arithmetic_v<T>, void> f(T) {}    // ②

f(42);  // ❌ 歧义！int 同时满足 is_integral 和 is_arithmetic

// ✅ 修正 — 确保条件互斥
template <typename T>
enable_if_t<std::is_integral_v<T>, void> f(T) {}

template <typename T>
enable_if_t<!std::is_integral_v<T> && std::is_arithmetic_v<T>, void> f(T) {}
```

### 陷阱 3：void_t 中的 SFINAE 表达式不会短路

```cpp
// 你期望：如果 T 没有 value_type，整个表达式失败
template <typename T>
using value_type_t = typename T::value_type;  // ❌ 这不是 SFINAE 上下文！

// ✅ 必须在 SFINAE 上下文中使用
template <typename T, typename = void>
struct get_value_type {};

template <typename T>
struct get_value_type<T, void_t<typename T::value_type>> {
    using type = typename T::value_type;
};
```

### 陷阱 4：Concept 不能被递归约束

```cpp
// ❌ 这不工作 — Concept 在定义完成前不能被引用
template <typename T>
concept Recursive = requires(T t) {
    { t.child() } -> Recursive;  // ❌ Recursive 尚未完成定义
};

// ✅ 解决方法：使用类型特征或间接层
template <typename T>
struct is_recursive : std::false_type {};

template <typename T>
concept HasChild = requires(T t) {
    { t.child() } -> std::same_as<typename T::child_type>;
};
```

### 陷阱 5：if constexpr 分支中的 static_assert 会让编译失败

```cpp
template <typename T>
void process(T val) {
    if constexpr (std::is_integral_v<T>) {
        // 整数分支
    } else {
        static_assert(sizeof(T) == 0, "Only integers supported");  // ❌
        // static_assert 总是被评估（即使分支被丢弃）！
    }
}

// ✅ 修正 — 使用 always_false 惯用法
template <typename T>
struct always_false : std::false_type {};

template <typename T>
void process(T val) {
    if constexpr (std::is_integral_v<T>) {
        // 整数分支
    } else {
        static_assert(always_false<T>::value, "Only integers supported");  // ✓
    }
}
```
