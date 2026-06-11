---
title: "特殊成员函数全解：Rule of Five"
updated: 2026-06-05
---

# 特殊成员函数全解：Rule of Five

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 02-object-lifetime-memory-layout（对象生命周期），03-raii-resource-management（RAII）

---

## 1. 概念讲解

### 1.1 六种特殊成员函数

C++ 标准定义了六种"编译器可以自动生成"的特殊成员函数：

| # | 函数 | 签名形式 | 何时自动生成 | 引擎中的意义 |
|---|------|---------|-------------|-------------|
| 1 | **默认构造** | `T()` | 没有用户声明的任何构造函数 | 创建"空"对象 |
| 2 | **析构** | `~T()` | （几乎总是自动生成） | 释放资源 |
| 3 | **拷贝构造** | `T(const T&)` | 没有用户声明的移动操作 | 深拷贝/浅拷贝 |
| 4 | **拷贝赋值** | `T& operator=(const T&)` | 同上 | 覆盖已有对象 |
| 5 | **移动构造** | `T(T&&)` | 没有用户声明析构/拷贝/移动 | 转移资源所有权 |
| 6 | **移动赋值** | `T& operator=(T&&)` | 同上 | 资源交接 |

**核心直觉：** 编译器不知道你的类管理了 GPU 句柄还是文件描述符还是只是纯数学数据。它只能"猜"——逐成员拷贝、逐成员析构。如果你管理的资源有非平凡的所有权语义（比如 GPU 对象 ID 不能被拷贝），你必须告诉编译器。

### 1.2 隐式生成与删除规则（完整矩阵）

这是 C++ 中最重要（也最复杂）的表。来源：Howard Hinnant (2014), C++ 标准 `[class.default.ctor]` / `[class.copy.ctor]` / `[class.dtor]`。

```
你声明的特殊成员              编译器自动生成的特殊成员
                     默认构造   析构   拷贝构造  拷贝赋值  移动构造  移动赋值
────────────────────────────────────────────────────────────────────
什么都不声明           ✓        ✓      ✓        ✓        ✓        ✓
析构函数               ✓        —      ✓        ✓        ✗        ✗
拷贝构造函数           ✗        ✓      —        ✓        ✗        ✗
拷贝赋值               ✓        ✓      ✓        —        ✗        ✗
移动构造函数           ✗        ✓      ✗        ✗        —        ✗
移动赋值               ✓        ✓      ✗        ✗        ✗        —
声明任何移动           —        —      ✗        ✗        —        —
```

**三句口诀：**
1. **声明析构 → 移动不生成**（C++11 保守设计；C++20 标记 deprecated，但仍不生成）
2. **声明拷贝 → 移动不生成、默认构造不生成**
3. **声明移动 → 拷贝被删除**（不是"不生成"，而是生成为 `= delete`）

**引擎实践推论：** 如果你写了一个管理 GPU 资源的类，写了析构函数（必然），移动函数就不会自动生成。你必须显式写 `= default` 或手动实现——否则你的类退化为不可移动。

### 1.3 `= default` 与 `= delete`：表达意图

```cpp
class NonCopyable {
public:
    NonCopyable() = default;                      // "给我默认构造"
    NonCopyable(const NonCopyable&) = delete;     // "禁止拷贝"
    NonCopyable& operator=(const NonCopyable&) = delete;
    // 编译器不会再生成移动——因为用户声明了拷贝
};

class MoveOnly : public NonCopyable {
public:
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;               // "给我默认移动"
    MoveOnly& operator=(MoveOnly&&) = default;
    // 拷贝被基类删除 → 隐式不生成
};

class GPUResource {
    int handle_ = -1;
public:
    GPUResource() = default;
    explicit GPUResource(int h) : handle_(h) {}
    ~GPUResource() noexcept { if (handle_ >= 0) release(handle_); }

    GPUResource(const GPUResource&) = delete;            // GPU 不拷贝
    GPUResource& operator=(const GPUResource&) = delete;

    GPUResource(GPUResource&& other) noexcept            // 手动实现移动
        : handle_(other.handle_) { other.handle_ = -1; }

    GPUResource& operator=(GPUResource&& other) noexcept {
        if (this != &other) {
            if (handle_ >= 0) release(handle_);
            handle_ = other.handle_;
            other.handle_ = -1;
        }
        return *this;
    }

private:
    static void release(int h) { /* API 调用 */ }
};
```

`= default` vs 不写的关键区别：`= default` 强制编译器**立即**尝试生成函数体，生成失败则编译报错。不写则是"按需生成"——可能到链接时才发现问题。

### 1.4 Rule of Zero / Three / Five

**Rule of Zero（零法则）— 默认首选：**
如果一个类的所有成员都管理好了自己（都是 RAII 类型），那么不要声明任何特殊成员函数。

```cpp
// ✅ Rule of Zero: 编译器生成的足够好
struct ParticleSystem {
    std::vector<Particle> particles;
    std::string           name;
    float                 lifetime = 5.0f;
    // 默认构造 ✓  析构 ✓  拷贝 ✓  移动 ✓
    // 全部正确——不需要写一行特殊成员
};
```

**Rule of Five（五法则）— 管理原始资源时：**
如果一个类管理了至少一个原始资源（裸指针、文件句柄、GPU ID 等），你需要显式声明或删除全部五个：析构、拷贝构造、拷贝赋值、移动构造、移动赋值。

```cpp
// ✅ Rule of Five: 管理裸指针
class Buffer {
    char* data_ = nullptr;
    size_t size_ = 0;
public:
    Buffer() = default;
    explicit Buffer(size_t n) : data_(new char[n]), size_(n) {}
    ~Buffer() noexcept { delete[] data_; }
    Buffer(const Buffer& other) : data_(new char[other.size_]), size_(other.size_) {
        std::copy(other.data_, other.data_ + size_, data_);
    }
    Buffer& operator=(const Buffer& other) {
        if (this != &other) {
            delete[] data_;
            size_ = other.size_;
            data_ = new char[size_];
            std::copy(other.data_, other.data_ + size_, data_);
        }
        return *this;
    }
    Buffer(Buffer&& other) noexcept
        : data_(std::exchange(other.data_, nullptr))
        , size_(std::exchange(other.size_, 0)) {}
    Buffer& operator=(Buffer&& other) noexcept {
        if (this != &other) {
            delete[] data_;
            data_ = std::exchange(other.data_, nullptr);
            size_ = std::exchange(other.size_, 0);
        }
        return *this;
    }
};
```

**Rule of Three（三法则，C++98 时代）— 向后兼容：**
在没有移动语义的时代，只需要析构、拷贝构造、拷贝赋值。现代 C++ 代码中，Rule of Five 是 Rule of Three 的自然扩展。

### 1.5 `std::exchange`：移动实现的惯用模式

```cpp
// ❌ 容易出错的手动写法
Foo(Foo&& other) noexcept : ptr_(other.ptr_) {
    other.ptr_ = nullptr;
}

// ✅ 惯用模式（一行，不重不漏）
Foo(Foo&& other) noexcept
    : ptr_(std::exchange(other.ptr_, nullptr)) {}
```

`std::exchange(obj, new_value)` 等价于 `{ auto old = obj; obj = new_value; return old; }`。在移动语义中，它同时完成"获取旧值"和"置空源对象"两个操作——不可分割，杜绝忘记置空的 bug。

### 1.6 引擎中的特殊成员函数模式

| 引擎中的类 | 默认构造 | 析构 | 拷贝 | 移动 | 理由 |
|-----------|---------|------|------|------|------|
| **Vec3/Mat4/Quat** | =default | =default | =default | =default | 纯数据，平凡类型 |
| **GPUBuffer** | =default | 释放 GPU 句柄 | =delete | noexcept 手动 | GPU 对象不可拷贝 |
| **GPUTexture** | =default | 释放 GPU 句柄 | =delete | noexcept 手动 | 同上 |
| **ScopedLock** | 需要 mutex 引用 | 解锁 | =delete | =delete | 不可转移 |
| **unique_ptr<T>** | =default | delete/自定义 | =delete | noexcept | 独占所有权 |
| **GameObject** | =default | =default | =delete | =default | 实体不可拷贝，可移动 |
| **JobSystem** | 初始化线程池 | 等待+join | =delete | =delete | 全局单例 |
| **VertexBuffer** | =default | 释放 GPU 句柄 | =delete | noexcept 手动 | 大型资源，拷贝昂贵 |

### 1.7 `noexcept` 的重要性：vector 扩容的证明

这是引擎开发者必须理解的核心机制。当 `std::vector` 扩容时，它必须将旧元素搬迁到新缓冲区：

```cpp
// vector 扩容时的策略选择（简化伪代码）
if constexpr (std::is_nothrow_move_constructible_v<T>) {
    // 路径 A：移动（快速、零额外分配）
    new (newBuf + i) T(std::move(oldBuf[i]));
} else if constexpr (std::is_copy_constructible_v<T>) {
    // 路径 B：拷贝（慢、需要额外分配）
    new (newBuf + i) T(oldBuf[i]);  // const T&
} else {
    // 路径 C：编译失败
}
```

**关键：** `std::is_nothrow_move_constructible_v<T>` 只有在移动构造明确标记为 `noexcept` 时才为 `true`。如果移动构造没有 `noexcept`，`vector` 会回退到**拷贝**而非移动——性能下降且可能导致编译错误（如果拷贝是 deleted）。

这个设计是为了异常安全：如果移动中途抛异常，旧缓冲区已被部分移动，无法回滚；拷贝则不影响旧缓冲区。

---

## 2. 代码示例

### 示例 1：特殊成员函数调用追踪器

```cpp
// trace_special.cpp — 追踪所有特殊成员函数的调用
// 编译: g++ -std=c++20 -O0 trace_special.cpp -o trace_special && ./trace_special

#include <iostream>
#include <string>
#include <vector>

// 记录所有特殊成员调用的类
struct Traced {
    std::string name;

    explicit Traced(std::string n) : name(std::move(n)) {
        std::cout << "  [ctor]     " << name << '\n';
    }

    ~Traced() noexcept {
        std::cout << "  [dtor]     " << name << '\n';
    }

    Traced(const Traced& other) : name(other.name + "(copy)") {
        std::cout << "  [copy ctor] " << other.name << " → " << name << '\n';
    }

    Traced& operator=(const Traced& other) {
        std::cout << "  [copy =]    " << name << " ← " << other.name << '\n';
        name = other.name + "(copy=)";
        return *this;
    }

    Traced(Traced&& other) noexcept : name(std::move(other.name)) {
        std::cout << "  [move ctor] moved into " << name << '\n';
    }

    Traced& operator=(Traced&& other) noexcept {
        std::cout << "  [move =]    " << name << " ← " << other.name << '\n';
        name = std::move(other.name);
        return *this;
    }
};

int main() {
    std::cout << "=== Special Member Function Trace ===\n\n";

    std::cout << "--- 1. Default Construction ---\n";
    Traced a("A");

    std::cout << "\n--- 2. Copy Construction ---\n";
    Traced b = a;  // 拷贝构造（不是赋值！）

    std::cout << "\n--- 3. Move Construction ---\n";
    Traced c = std::move(a);  // 移动构造

    std::cout << "\n--- 4. Copy Assignment ---\n";
    Traced d("D");
    d = b;

    std::cout << "\n--- 5. Move Assignment ---\n";
    d = std::move(c);

    std::cout << "\n--- 6. vector push_back (copy) ---\n";
    std::vector<Traced> v;
    v.push_back(b);  // b 是左值 → 拷贝

    std::cout << "\n--- 7. vector push_back (move from temp) ---\n";
    v.push_back(Traced("Temp"));  // 临时对象 → 移动

    std::cout << "\n--- 8. vector emplace_back (in-place) ---\n";
    v.emplace_back("Emplaced");  // 直接构造，无拷贝/移动

    std::cout << "\n--- 9. End of main: all destructors run ---\n";
    return 0;
}
```

**运行方式：**
```bash
g++ -std=c++20 -O0 trace_special.cpp -o trace_special && ./trace_special
```

### 示例 2：noexcept 对 vector 扩容的影响

```cpp
// noexcept_demo.cpp — 证明 noexcept 移动对 std::vector 的影响
// 编译: g++ -std=c++20 -O2 noexcept_demo.cpp -o noexcept_demo && ./noexcept_demo

#include <iostream>
#include <vector>
#include <string>

// 没有 noexcept 移动的类
struct NoNoexcept {
    std::string data;
    NoNoexcept(std::string s) : data(std::move(s)) {}
    NoNoexcept(const NoNoexcept& other) : data(other.data) {
        std::cout << "  (copy NoNoexcept)\n";
    }
    // 移动没有标记 noexcept！
    NoNoexcept(NoNoexcept&& other) : data(std::move(other.data)) {
        std::cout << "  (move NoNoexcept)\n";
    }
};

// 有 noexcept 移动的类
struct YesNoexcept {
    std::string data;
    YesNoexcept(std::string s) : data(std::move(s)) {}
    YesNoexcept(const YesNoexcept& other) : data(other.data) {
        std::cout << "  (copy YesNoexcept)\n";
    }
    YesNoexcept(YesNoexcept&& other) noexcept  // ← 注意 noexcept
        : data(std::move(other.data)) {
        std::cout << "  (move YesNoexcept)\n";
    }
};

static_assert(!std::is_nothrow_move_constructible_v<NoNoexcept>);
static_assert(std::is_nothrow_move_constructible_v<YesNoexcept>);

int main() {
    std::cout << "=== noexcept Matters for std::vector ===\n\n";

    std::cout << "--- Without noexcept ---\n";
    {
        std::vector<NoNoexcept> v;
        v.emplace_back("first");
        std::cout << "Pushing second (will trigger realloc)...\n";
        v.emplace_back("second");  // 扩容 → vector 会选择拷贝！
    }

    std::cout << "\n--- With noexcept ---\n";
    {
        std::vector<YesNoexcept> v;
        v.emplace_back("first");
        std::cout << "Pushing second (will trigger realloc)...\n";
        v.emplace_back("second");  // 扩容 → vector 会选择移动！
    }

    std::cout << "\nConclusion: noexcept move enables vector to use move on realloc.\n";
    std::cout << "Without noexcept, vector falls back to copy for exception safety.\n";
    return 0;
}
```

**运行方式：**
```bash
g++ -std=c++20 -O2 noexcept_demo.cpp -o noexcept_demo && ./noexcept_demo
```

**预期输出：**
```text
=== noexcept Matters for std::vector ===

--- Without noexcept ---
Pushing second (will trigger realloc)...
  (copy NoNoexcept)
  ...

--- With noexcept ---
Pushing second (will trigger realloc)...
  (move YesNoexcept)
  ...

Conclusion: noexcept move enables vector to use move on realloc.
Without noexcept, vector falls back to copy for exception safety.
```

---

## 3. 练习

### 练习 1：设计 Rule of Zero / Three / Five 类（基础）

设计三个类，分别遵循三种法则：

**类 A（Rule of Zero）：** `Transform` 组件——包含 `Vec3 position`, `Vec3 rotation`, `Vec3 scale`。验证编译器自动生成的所有特殊成员函数。

**类 B（Rule of Three / Five）：** `DynamicArray<T>`——一个简化的动态数组。包含 `T* data_` 和 `size_t size_`。实现所有五个特殊成员函数。

**类 C（Custom Rule）：** `GPUShader`——管理 OpenGL/模拟的 Shader 句柄。拷贝=delete，移动=noexcept 手动。析构调用 `glDeleteShader`。

对每个类，用 `static_assert` 验证它们的性质（`is_copy_constructible`, `is_nothrow_move_constructible` 等）。

### 练习 2：追踪编译器行为（进阶）

创建一个包含 `std::unique_ptr<int>` 成员的类 `Holder`。不声明任何特殊成员函数。然后用注释回答以下问题（并用代码验证）：
1. `Holder` 是否可拷贝？为什么？
2. `Holder` 是否可移动？移动构造是否 noexcept？
3. 如果一个类包含 `const int` 成员，它的移动构造是什么状态？
4. 声明析构后，移动构造的状态如何变化？
5. 分别用 `=default` 和 `=delete` 声明拷贝/移动后，用 `static_assert` 验证结果

### 练习 3：修复一个"安静拷贝 GPU 资源"的 Bug（可选）

以下代码有一个严重的 bug——GPU 资源被隐形拷贝了。诊断问题并修复：

```cpp
class GPUTexture {
    GLuint id_ = 0;
    size_t width_, height_;
public:
    GPUTexture(size_t w, size_t h) : width_(w), height_(h) {
        glGenTextures(1, &id_);
        glBindTexture(GL_TEXTURE_2D, id_);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    }
    ~GPUTexture() { if (id_) glDeleteTextures(1, &id_); }
    // 没有声明拷贝和移动！

    void bind() { glBindTexture(GL_TEXTURE_2D, id_); }
    GLuint id() const { return id_; }
};

void renderScene() {
    std::vector<GPUTexture> textures;
    textures.emplace_back(512, 512);   // 第一个纹理
    textures.emplace_back(256, 256);   // 第二个 → vector 扩容！
    // 问题：扩容时发生了什么？两个 GPUTexture 可能会指向同一个 GPU 对象吗？
}
```

写出修复方案，解释为什么你的修复是正确的。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案：Rule of Zero / Three / Five
> ```cpp
> // rule_classes.cpp — 三种法则的类设计
> // 编译: g++ -std=c++20 -O2 rule_classes.cpp -o rule_classes && ./rule_classes
>
> #include <iostream>
> #include <type_traits>
> #include <utility>    // std::exchange
> #include <cstddef>
> #include <algorithm>  // std::copy
>
> // ===== 类 A：Rule of Zero — Transform 组件 =====
> struct Vec3 { float x = 0, y = 0, z = 0; };
>
> struct Transform {
>     Vec3 position;
>     Vec3 rotation;
>     Vec3 scale{1.0f, 1.0f, 1.0f};
>     // 不声明任何特殊成员 → 编译器全部正确生成
> };
>
> // 验证 Rule of Zero 的属性
> static_assert(std::is_default_constructible_v<Transform>);
> static_assert(std::is_copy_constructible_v<Transform>);
> static_assert(std::is_copy_assignable_v<Transform>);
> static_assert(std::is_move_constructible_v<Transform>);
> static_assert(std::is_move_assignable_v<Transform>);
> static_assert(std::is_nothrow_move_constructible_v<Transform>);
> static_assert(std::is_trivially_copyable_v<Transform>);  // 全是 float → trivial
>
> // ===== 类 B：Rule of Five — DynamicArray<T> =====
> template<typename T>
> class DynamicArray {
> public:
>     DynamicArray() = default;
>
>     explicit DynamicArray(size_t n) : data_(new T[n]), size_(n) {}
>
>     ~DynamicArray() noexcept { delete[] data_; }
>
>     // 拷贝构造
>     DynamicArray(const DynamicArray& other)
>         : data_(new T[other.size_]), size_(other.size_) {
>         std::copy(other.data_, other.data_ + size_, data_);
>     }
>
>     // 拷贝赋值
>     DynamicArray& operator=(const DynamicArray& other) {
>         if (this != &other) {
>             delete[] data_;
>             size_ = other.size_;
>             data_ = new T[size_];
>             std::copy(other.data_, other.data_ + size_, data_);
>         }
>         return *this;
>     }
>
>     // 移动构造（noexcept — 必须）
>     DynamicArray(DynamicArray&& other) noexcept
>         : data_(std::exchange(other.data_, nullptr))
>         , size_(std::exchange(other.size_, 0)) {}
>
>     // 移动赋值（noexcept — 必须）
>     DynamicArray& operator=(DynamicArray&& other) noexcept {
>         if (this != &other) {
>             delete[] data_;
>             data_ = std::exchange(other.data_, nullptr);
>             size_ = std::exchange(other.size_, 0);
>         }
>         return *this;
>     }
>
>     // 访问器
>     T& operator[](size_t i) { return data_[i]; }
>     const T& operator[](size_t i) const { return data_[i]; }
>     size_t size() const { return size_; }
>
> private:
>     T* data_ = nullptr;
>     size_t size_ = 0;
> };
>
> // 验证 DynamicArray<int> 的属性
> static_assert(std::is_copy_constructible_v<DynamicArray<int>>);
> static_assert(std::is_nothrow_move_constructible_v<DynamicArray<int>>);
> static_assert(std::is_nothrow_move_assignable_v<DynamicArray<int>>);
> static_assert(!std::is_trivially_copyable_v<DynamicArray<int>>);
>
> // ===== 类 C：Custom Rule — GPUShader =====
> // 模拟 OpenGL 函数
> namespace GL {
>     inline unsigned genShader()   { static unsigned id = 100; return id++; }
>     inline void delShader(unsigned id) {
>         std::cout << "  GL: delShader(" << id << ")\n";
>     }
> }
>
> class GPUShader {
> public:
>     GPUShader() : id_(GL::genShader()) {
>         std::cout << "  GPUShader: created #" << id_ << '\n';
>     }
>
>     ~GPUShader() noexcept {
>         if (id_ != 0) GL::delShader(id_);
>     }
>
>     // 拷贝=delete
>     GPUShader(const GPUShader&) = delete;
>     GPUShader& operator=(const GPUShader&) = delete;
>
>     // 移动=noexcept 手动
>     GPUShader(GPUShader&& other) noexcept
>         : id_(std::exchange(other.id_, 0)) {
>         std::cout << "  GPUShader: moved #" << id_ << '\n';
>     }
>
>     GPUShader& operator=(GPUShader&& other) noexcept {
>         if (this != &other) {
>             if (id_ != 0) GL::delShader(id_);
>             id_ = std::exchange(other.id_, 0);
>         }
>         return *this;
>     }
>
>     unsigned id() const { return id_; }
>     bool valid() const { return id_ != 0; }
>
> private:
>     unsigned id_ = 0;
> };
>
> // 验证 GPUShader 的属性
> static_assert(!std::is_copy_constructible_v<GPUShader>);
> static_assert(!std::is_copy_assignable_v<GPUShader>);
> static_assert(std::is_nothrow_move_constructible_v<GPUShader>);
> static_assert(std::is_nothrow_move_assignable_v<GPUShader>);
>
> // ===== 演示 =====
> int main() {
>     std::cout << "=== Rule of Zero / Five / Custom ===\n\n";
>
>     std::cout << "--- Rule of Zero: Transform ---\n";
>     Transform t1;
>     t1.position.x = 10.0f;
>     Transform t2 = t1;                   // 拷贝
>     Transform t3 = std::move(t1);        // 移动（平凡类型 = 拷贝）
>     std::cout << "  t2.position.x = " << t2.position.x << '\n';
>
>     std::cout << "\n--- Rule of Five: DynamicArray ---\n";
>     DynamicArray<int> arr1(5);
>     arr1[0] = 42;
>     DynamicArray<int> arr2 = std::move(arr1);  // 移动
>     std::cout << "  arr1.size() = " << arr1.size()         // 0
>               << ", arr2.size() = " << arr2.size()         // 5
>               << ", arr2[0] = " << arr2[0] << '\n';        // 42
>
>     std::cout << "\n--- Custom Rule: GPUShader ---\n";
>     GPUShader s1;
>     GPUShader s2 = std::move(s1);
>     std::cout << "  s1.valid() = " << s1.valid()
>               << ", s2.id() = " << s2.id() << '\n';
>
>     std::cout << "\n=== All static_asserts passed ===\n";
>     return 0;
> }
> ```

> [!tip]- 练习 2 参考答案：追踪编译器行为
> ```cpp
> // holder_trace.cpp — 编译器特殊成员生成追踪
> // 编译: g++ -std=c++20 -O0 holder_trace.cpp -o holder_trace && ./holder_trace
>
> #include <iostream>
> #include <memory>
> #include <type_traits>
>
> // 问题 1 & 2：包含 unique_ptr 的类
> class Holder {
>     std::unique_ptr<int> ptr_;
> public:
>     // 不声明任何特殊成员函数
>     Holder() = default;
>     explicit Holder(int v) : ptr_(std::make_unique<int>(v)) {}
>     int get() const { return ptr_ ? *ptr_ : -1; }
> };
>
> // 答 1: Holder 不可拷贝，因为 std::unique_ptr 的拷贝构造=delete
> //       编译器检测到成员不可拷贝 → 隐式删除 Holder 的拷贝构造/赋值
> static_assert(!std::is_copy_constructible_v<Holder>);
> static_assert(!std::is_copy_assignable_v<Holder>);
>
> // 答 2: Holder 可移动，因为 std::unique_ptr 有 noexcept 移动
> //       编译器逐成员移动 → Holder 的移动也是 noexcept
> static_assert(std::is_move_constructible_v<Holder>);
> static_assert(std::is_nothrow_move_constructible_v<Holder>);
> static_assert(std::is_move_assignable_v<Holder>);
> static_assert(std::is_nothrow_move_assignable_v<Holder>);
>
> // ===== 问题 3：包含 const int 成员的类 =====
> class ConstMember {
> public:
>     const int value;
>     explicit ConstMember(int v) : value(v) {}
> };
>
> // 答 3: const 成员不能被赋值 → 移动赋值被隐式删除
> //       但移动构造仍然生成（可以初始化 const 成员，只需构造）
> static_assert(std::is_copy_constructible_v<ConstMember>);
> static_assert(std::is_move_constructible_v<ConstMember>);
> static_assert(!std::is_copy_assignable_v<ConstMember>);   // const 不能改
> static_assert(!std::is_move_assignable_v<ConstMember>);   // 同上
>
> // ===== 问题 4：声明析构后，移动的状态 =====
> class WithDtor {
> public:
>     WithDtor() = default;
>     ~WithDtor() {}  // 用户声明析构
> };
>
> // 答 4: 声明析构 → 移动构造/赋值不再自动生成（C++11 规则）
> //       但拷贝仍然自动生成（C++11/14/17，C++20 标记 deprecated）
> static_assert(std::is_copy_constructible_v<WithDtor>);
> static_assert(std::is_copy_assignable_v<WithDtor>);
> // 移动被隐式生成了吗？
> // static_assert(!std::is_move_constructible_v<WithDtor>);  // C++11-17
> // C++11-17: 移动"不生成"但可以被拷贝替代（回退到拷贝）
> // 实际上 is_move_constructible 为 true，因为拷贝构造可以接受 T&&
> // 真正的区别: is_nothrow_move_constructible 和实际调用
> static_assert(std::is_move_constructible_v<WithDtor>);
> // 注意：非 noexcept，且内部是拷贝
>
> // ===== 问题 5：=default vs =delete 验证 =====
> class ExplicitMove {
>     int* p_ = nullptr;
> public:
>     ExplicitMove() = default;
>     ExplicitMove(const ExplicitMove&) = delete;
>     ExplicitMove& operator=(const ExplicitMove&) = delete;
>     ExplicitMove(ExplicitMove&&) noexcept = default;
>     ExplicitMove& operator=(ExplicitMove&&) noexcept = default;
>     ~ExplicitMove() = default;
> };
>
> static_assert(!std::is_copy_constructible_v<ExplicitMove>);
> static_assert(std::is_nothrow_move_constructible_v<ExplicitMove>);
> static_assert(std::is_nothrow_move_assignable_v<ExplicitMove>);
>
> int main() {
>     std::cout << "=== Holder Compiler Behavior Trace ===\n\n";
>
>     Holder h1(42);
>     // Holder h2 = h1;  // 编译错误: use of deleted function
>
>     Holder h2 = std::move(h1);  // OK: noexcept 移动
>     std::cout << "h1.get() = " << h1.get()    // 0 (nullptr)
>               << ", h2.get() = " << h2.get()  // 42
>               << '\n';
>
>     ConstMember cm1(100);
>     ConstMember cm2 = std::move(cm1);  // 移动构造 OK
>     std::cout << "cm2.value = " << cm2.value << '\n';
>
>     std::cout << "\n=== All static_asserts passed ===\n";
>     return 0;
> }
> ```

> [!info]- 练习 3 思考题参考答案：修复 GPUTexture Bug
> **问题诊断：**
> `GPUTexture` 声明了析构函数（释放 `id_`），但没有声明拷贝/移动构造。
> 编译器自动生成了拷贝构造 → 两个 `GPUTexture` 持有同一个 `id_` → 双方析构时双重 `glDeleteTextures`。
> 同时，编译器**不会**自动生成移动构造（因为析构被声明了），所以 `vector` 扩容时回退使用拷贝构造。
>
> **修复方案：**
> ```cpp
> // 修复后的 GPUTexture
> class GPUTexture {
>     unsigned id_ = 0;    // 使用 unsigned 替代 GLuint
>     size_t width_, height_;
> public:
>     GPUTexture(size_t w, size_t h) : width_(w), height_(h) {
>         glGenTextures(1, &id_);
>         glBindTexture(GL_TEXTURE_2D, id_);
>         glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, (int)w, (int)h,
>                      0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
>     }
>
>     ~GPUTexture() {
>         if (id_ != 0) glDeleteTextures(1, &id_);
>     }
>
>     // 删除拷贝（GPU 资源不可拷贝）
>     GPUTexture(const GPUTexture&) = delete;
>     GPUTexture& operator=(const GPUTexture&) = delete;
>
>     // 实现 noexcept 移动
>     GPUTexture(GPUTexture&& other) noexcept
>         : id_(std::exchange(other.id_, 0))
>         , width_(other.width_), height_(other.height_) {}
>
>     GPUTexture& operator=(GPUTexture&& other) noexcept {
>         if (this != &other) {
>             if (id_ != 0) glDeleteTextures(1, &id_);
>             id_ = std::exchange(other.id_, 0);
>             width_ = other.width_;
>             height_ = other.height_;
>         }
>         return *this;
>     }
>
>     void bind() const { glBindTexture(GL_TEXTURE_2D, id_); }
>     unsigned id() const { return id_; }
> };
>
> // 验证修复
> static_assert(!std::is_copy_constructible_v<GPUTexture>);
> static_assert(std::is_nothrow_move_constructible_v<GPUTexture>);
> // 现在 std::vector<GPUTexture> 扩容时使用 noexcept 移动，不使用拷贝
> ```
>
> **为什么修复正确：**
> 1. 拷贝=delete → 编译期阻止意外拷贝
> 2. 移动=noexcept → `std::vector` 扩容时使用移动而非拷贝
> 3. 析构后移动构造不再自动生成 → 必须手动实现
> 4. `std::exchange` 确保源对象的 `id_` 被置零 → 不会双重删除

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了编译和测试，或分析得出了合理结论，就是正确的。

## 4. 扩展阅读

- **[必读] C++ Reference — Rule of Three/Five/Zero:** https://en.cppreference.com/w/cpp/language/rule_of_three
- **[必读] 本计划 Deep Dive — C++ 特殊成员函数深度剖析:** `docs/deep-dives/cpp-special-member-functions.md` — 从隐式生成规则到汇编实现
- **[推荐] "Everything You Ever Wanted To Know About Move Semantics" (Howard Hinnant, ACCU 2014)** — 隐式生成矩阵的原始出处
- **[推荐] "The Rule of Zero" (R. Martinho Fernandes)** — https://rmf.io/cxx11/rule-of-zero
- **[进阶] C++ Reference — `std::exchange`** — https://en.cppreference.com/w/cpp/utility/exchange
- **[工具] C++ Insights** — https://cppinsights.io/ — 看看编译器实际生成了哪些特殊成员

---

## 常见陷阱

1. **声明了析构函数但忘记处理拷贝/移动。**
   ```cpp
   // ❌ 危险 — 编译器仍自动生成拷贝（C++11/14/17）
   class Resource {
       int* p;
   public:
       Resource(int v) : p(new int(v)) {}
       ~Resource() { delete p; }     // 声明了析构
       // 编译器生成了拷贝构造！→ 双重删除
   };
   
   // ✅ 正确 — 显式声明所有
   class Resource {
       int* p;
   public:
       Resource(int v) : p(new int(v)) {}
       ~Resource() { delete p; }
       Resource(const Resource&) = delete;           // 禁止拷贝
       Resource& operator=(const Resource&) = delete;
       Resource(Resource&&) noexcept = default;
       Resource& operator=(Resource&&) noexcept = default;
   };
   ```
   声明析构后，拷贝仍然自动生成（只是移动不再生成）。这是最常见的双重删除 bug 来源。

2. **移动构造/赋值忘记 `noexcept`。**
   ```cpp
   // ❌ 性能 bug（可能变成编译错误）
   MyType(MyType&& other) : data_(other.data_) { other.data_ = nullptr; }
   // vector 扩容时不会使用这个移动构造！

   // ✅ 正确
   MyType(MyType&& other) noexcept : data_(std::exchange(other.data_, nullptr)) {}
   ```

3. **移动赋值中忘记自赋值检查，或使用错误的检查方式。**
   ```cpp
   // ❌ 不安全的移动赋值
   MyType& operator=(MyType&& other) noexcept {
       delete data_;                          // 释放自己
       data_ = other.data_;                   // 接管
       other.data_ = nullptr;
       return *this;
   }  // 如果 &other == this → 释放了自己的 data_，然后拿到了悬垂指针！

   // ✅ 正确
   MyType& operator=(MyType&& other) noexcept {
       if (this != &other) {
           delete data_;
           data_ = std::exchange(other.data_, nullptr);
       }
       return *this;
   }
   ```

4. **拷贝赋值中没有处理自赋值和旧资源。**
   ```cpp
   // ❌ 泄漏 + 自赋值危险
   MyType& operator=(const MyType& other) {
       data_ = new int(*other.data_);  // 旧 data_ 泄漏！
       return *this;
   }

   // ✅ 正确：先保存旧值，分配新值，再释放旧值（copy-and-swap 或 RAII 内部分配）
   MyType& operator=(const MyType& other) {
       if (this != &other) {
           auto* tmp = new int(*other.data_);
           delete data_;
           data_ = tmp;
       }
       return *this;
   }
   ```
   另一个惯用写法是 **copy-and-swap**：拷贝构造临时对象 + swap。但引擎代码中通常避免额外分配，使用上述手动写法。

5. **在基类析构函数不是虚函数时用基类指针删除派生对象。**
   ```cpp
   // ❌ 未定义行为
   class Base { public: ~Base() {} };  // 非虚析构
   class Derived : public Base { int* data = new int[100]; ~Derived() { delete[] data; } };
   Base* p = new Derived;
   delete p;  // 只调用 ~Base() → data 泄漏！

   // ✅ 正确
   class Base { public: virtual ~Base() = default; };
   ```
   引擎多态基类（如 `Component`, `RenderPass`, `Asset`）的析构函数必须是 `virtual`。
