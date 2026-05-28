# C++ 特殊成员函数 深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 游戏引擎开发工程师 — [C++ 引擎编程：语言特性精要](../learning-plans/active/game-engine-dev/tutorials/00-cpp-for-game-engines.md#22-rule-of-zero--rule-of-five)
> 关联深度探索: [RAII 深度剖析](raii-complete-analysis.md)
> 分析日期: 2026-05-27

---

## 第 1 层: 直觉理解

**特殊成员函数是编译器帮你写的"家务代码"。你自己不写，编译器就帮你写一份；你写了任何一个，编译器就少帮你写一些。**

想象你去餐厅点了一份套餐。套餐里包含前菜、主菜、甜点、饮料——这些都是"默认包含的"。但如果你单点了甜点，套餐里的甜点就不送了。更微妙的是：你单点主菜，前菜和甜点可能也不送了，因为厨房认为你"有特殊要求"。

C++ 编译器帮你自动生成的函数包括：

| 函数 | 职责 | 类比 |
|------|------|------|
| 默认构造函数 | "空对象怎么诞生" | 给你一个空盘子 |
| 析构函数 | "对象怎么死去" | 收盘子 + 洗碗 |
| 拷贝构造函数 | "怎么克隆一个对象" | 照着你的菜再做一份 |
| 拷贝赋值 | "怎么把B变成A的克隆" | 把B的菜倒掉，照着A再做一份 |
| 移动构造函数 | "怎么把A的资源抢过来" | 直接把A的盘子端给你，A变成空盘 |
| 移动赋值 | "抢B，然后把A的资源给B" | 把B的菜倒了，把A的盘子端给B |

**核心矛盾**：编译器能自动生成教科书般正确的代码，但它不知道你的"资源"（GPU 句柄、文件描述符、裸指针）意味着什么。一旦你管理了原始资源，你必须告诉编译器"拷贝、移动、销毁"的真正含义。

---

## 第 2 层: 使用场景

### 什么时候依赖编译器生成的

```cpp
// 场景 1：纯数据聚合（aggregate）——让编译器全权处理
struct Vec3 {
    float x, y, z;
    // 不写任何特殊成员——编译器全部正确生成
    // 默认构造（未初始化）、拷贝、移动、析构：全部对
};

// 场景 2：只包含标准库成员的类
class ParticleSystem {
    std::vector<Particle> particles_;
    std::string name_;
    float lifetime_ = 5.0f;
    // Rule of Zero! 所有成员都管理好了自己
    // 默认构造 ✓  析构 ✓  拷贝 ✓  移动 ✓
};
```

### 什么时候必须手写

```cpp
// 手动管理原始资源的类——必须明确所有权语义
class GLTexture {
    GLuint id_ = 0;          // GPU 资源句柄

public:
    // 必须手写：构造获取资源
    explicit GLTexture(const char* path) {
        glGenTextures(1, &id_);
        // load from path...
    }

    // 必须手写：析构释放资源
    ~GLTexture() {
        if (id_) glDeleteTextures(1, &id_);
    }

    // 必须手写——GPU 纹理不能"拷贝"（只有一个 GPU 对象）
    GLTexture(const GLTexture&) = delete;
    GLTexture& operator=(const GLTexture&) = delete;

    // 必须手写——但可以"转移所有权"
    GLTexture(GLTexture&& other) noexcept : id_(other.id_) {
        other.id_ = 0;
    }
    GLTexture& operator=(GLTexture&& other) noexcept {
        if (this != &other) {
            if (id_) glDeleteTextures(1, &id_);
            id_ = other.id_;
            other.id_ = 0;
        }
        return *this;
    }
};
```

### 什么时候用 `= default` / `= delete`

```cpp
class NonCopyable {
public:
    NonCopyable() = default;                     // "用编译器生成的"
    NonCopyable(const NonCopyable&) = delete;    // "这个操作禁止"
    NonCopyable& operator=(const NonCopyable&) = delete;
};

class MoveOnly : NonCopyable {
public:
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;              // "用编译器生成的移动"
    MoveOnly& operator=(MoveOnly&&) = default;
    // 拷贝被基类禁止，自动不会生成
};
```

### 不适用特殊成员函数自动生成的情况

| 情况 | 为什么不能依赖自动生成 |
|------|----------------------|
| 类包含裸指针（拥有所有权） | 编译器逐成员拷贝指针，不会深拷贝指向的数据 |
| 类包含非 RAII 的 OS 资源 | `GLuint`、`HANDLE`、`int fd` 的拷贝/析构语义需要你定义 |
| 类需要自定义的构造逻辑 | 比如构造时需要注册到全局管理器 |
| 类有虚函数（多态基类） | 通常需要虚析构函数，不能依赖默认的 |

---

## 第 3 层: API 层 — 六种特殊成员函数的声明语法

### 函数签名速查表

```cpp
class MyClass {
public:
    // 1. 默认构造函数
    MyClass();                                   // 声明但不定义
    MyClass() = default;                         // 显式要求编译器生成
    MyClass() = delete;                          // 禁止默认构造

    // 2. 析构函数
    ~MyClass();                                  // 声明
    ~MyClass() noexcept;                         // C++11: 不抛异常
    virtual ~MyClass() = default;                // 多态基类标配

    // 3. 拷贝构造函数
    MyClass(const MyClass& other);               // 传统写法
    MyClass(const MyClass&) = default;           // 编译器生成
    MyClass(const MyClass&) = delete;            // 禁止拷贝

    // 4. 拷贝赋值运算符
    MyClass& operator=(const MyClass& other);    // 返回引用（链式赋值）
    MyClass& operator=(const MyClass&) = default;
    MyClass& operator=(const MyClass&) = delete;

    // 5. 移动构造函数
    MyClass(MyClass&& other) noexcept;           // noexcept 极其重要！
    MyClass(MyClass&&) noexcept = default;
    MyClass(MyClass&&) = delete;

    // 6. 移动赋值运算符
    MyClass& operator=(MyClass&& other) noexcept;
    MyClass& operator=(MyClass&&) noexcept = default;
    MyClass& operator=(MyClass&&) = delete;
};
```

### `= default` vs 不写

| | 不写任何声明 | `= default` |
|---|---|---|
| 何时可用 | 类没有用户声明的"冲突"函数时 | 任何情况（即使你写了其他特殊成员） |
| 生成时机 | 编译器**隐式声明**，首次 odr-use 时**隐式定义** | 编译器在你写的地方**显式声明** |
| 是否可能是平凡的 (trivial) | 可能 | 可能 |
| 编译器报错时机 | 使用时报错（如果被隐式删除） | 声明时报错（如果编译器无法生成） |

**关键差异**：`= default` 强制编译器尝试生成函数体，并在发现无法生成时立即报错。这比"不写，等用到时才发现"更好。

### `= delete` vs `private`（C++98 技法）

```cpp
// C++98 的"禁止拷贝"写法（缺陷很多）
class OldWay {
private:
    OldWay(const OldWay&);           // 只声明，不定义
    OldWay& operator=(const OldWay&);
    // 问题：成员函数和友元可以"看到"声明，链接时才报错
};

// C++11 的"禁止拷贝"写法（正确）
class NewWay {
public:
    NewWay(const NewWay&) = delete;  // 编译期报错，任何上下文
    NewWay& operator=(const NewWay&) = delete;
};
```

---

## 第 4 层: 行为契约 — 隐式生成与删除规则

这是 C++ 中最复杂、最容易出错的规则之一。以下基于 ISO C++ 标准 `[class.default.ctor]`、`[class.copy.ctor]`、`[class.dtor]` 等章节。

### 核心原则：编译器生成函数的两个阶段

1. **隐式声明（implicitly declared）**：编译器决定"要不要提供这个函数"
2. **隐式定义（implicitly defined）**：首次 odr-use 该函数时，编译器生成函数体；但如果无法生成，则标记为 **deleted**

### 自动生成决策矩阵

> 来源：Howard Hinnant, ACCU 2014, "Everything You Ever Wanted To Know About Move Semantics"

```
你声明的特殊成员              编译器自动生成的特殊成员
                        默认构造  析构    拷贝构造  拷贝赋值  移动构造  移动赋值
─────────────────────────────────────────────────────────────────────────
（什么都不声明）         ✓        ✓       ✓        ✓        ✓        ✓
析构函数                 ✓        —       ✓        ✓        ✗        ✗
拷贝构造函数             ✗        ✓       —        ✓        ✗        ✗
拷贝赋值                 ✓        ✓       ✓        —        ✗        ✗
移动构造函数             ✗        ✓       ✗        ✗        —        ✗
移动赋值                 ✓        ✓       ✗        ✗        ✗        —
拷贝构造 + 拷贝赋值       ✗        ✓       —        —        ✗        ✗
拷贝构造 + 移动构造       ✗        ✓       —        ✗        —        ✗
（声明任何移动操作）      —        —       ✗        ✗        —        —
```

**关键记忆法则：**

1. **声明析构 → 移动不生成**（C++11 的保守设计；C++20 中该行为被标记为 deprecated）
2. **声明拷贝 → 移动不生成、默认构造不生成**
3. **声明移动 → 拷贝被删除（不是"不生成"，而是生成了 deleted 版本）**
4. **默认构造**：声明了**任何其他构造函数**（包括拷贝/移动），默认构造就不会自动生成

### 隐式定义为 deleted 的条件

编译器生成了声明，但把函数体标记为 `= delete`（而非不生成），当以下情况之一为真：

```cpp
// 情况 1：成员无法拷贝/移动
struct Bad {
    std::unique_ptr<int> p;
    // 拷贝构造 被隐式删除——因为 unique_ptr 的拷贝构造是 deleted
    // 移动构造 ✓（unique_ptr 可移动）
};

// 情况 2：const 成员 + 移动
struct CantMove {
    const int x = 42;
    // 移动构造被隐式删除！移动 const int 等于拷贝——编译器不生成
};

// 情况 3：基类的对应函数无法访问
class Base {
    Base(const Base&) = delete;  // 禁止拷贝
};
class Derived : public Base {
    // 拷贝构造被隐式删除——基类拷贝不可用
};

// 情况 4：析构函数无法访问
class PrivateDtor {
    ~PrivateDtor() = delete;
};
class Holder {
    PrivateDtor m;
    // 默认构造被隐式删除——m 无法析构
};
```

### `noexcept` 的自动推导

- 编译器生成的**移动构造/移动赋值**，如果所有成员和基类的移动都是 `noexcept`，则自动为 `noexcept`
- 手动写的移动操作必须显式标注 `noexcept`，否则 `std::vector` 扩容时不会使用

---

## 第 5 层: 实现原理

### 编译器生成的函数体做什么

```cpp
struct Example {
    std::string s;
    std::vector<int> v;
    int n;
};
```

编译器生成的代码等价于：

```
// 默认构造 (≈)
Example() : s(), v(), n() {}
// 逐成员默认初始化。int 的"默认初始化"是不初始化（indeterminate value）
// 但如果你写了 int n = 0; 则用这个默认值

// 析构 (≈)
~Example() {
    // 按声明逆序销毁成员
    n.~int();          // no-op（平凡析构）
    v.~vector<int>();  // 释放动态内存
    s.~string();       // 释放动态内存
}

// 拷贝构造 (≈)
Example(const Example& other)
    : s(other.s), v(other.v), n(other.n) {}
// 逐成员拷贝构造

// 拷贝赋值 (≈)
Example& operator=(const Example& other) {
    s = other.s;
    v = other.v;
    n = other.n;
    return *this;
}

// 移动构造 (≈)
Example(Example&& other) noexcept
    : s(std::move(other.s)), v(std::move(other.v)), n(other.n) {}
// 逐成员移动构造。注意 n 没有移动构造，所以执行拷贝。
// 但 other.n 不会被置零——int 没有"空"状态。

// 移动赋值 (≈)
Example& operator=(Example&& other) noexcept {
    s = std::move(other.s);
    v = std::move(other.v);
    n = other.n;
    return *this;
}
```

### 平凡 vs 非平凡

编译器内部将特殊成员标记为 **trivial（平凡的）** 或 **non-trivial**：

```cpp
// 平凡析构：编译器不需要生成任何代码
struct Trivial {
    int x, y, z;
    // ~Trivial() 是平凡的——析构时什么都不做
};
// Trivial 的对象可以直接丢弃内存，不需要调用析构函数

// 非平凡析构：编译器必须生成函数体
struct NonTrivial {
    std::vector<int> items;
    // ~NonTrivial() 是非平凡的——需要调用 vector 的析构来释放内存
};
```

**为什么这很重要：**
- 平凡特殊成员不阻止类型用于 `union`
- 平凡拷贝/移动允许用 `memcpy` 复制（如 `std::is_trivially_copyable`）
- 平凡析构允许省略析构调用（如在 Arena 中批量释放）

### 编译器内部的决策流程（以 Clang 为例）

> 参考：`clang/lib/Sema/SemaDeclCXX.cpp` (LLVM 17.0.6)

```
编译器遇到一个类定义时的内部决策流程：

ShouldDeclareDefaultConstructor(X):
    if X 有用户声明的任何构造函数:
        return false  // 不生成
    if X 有 const 成员且无默认初始化器:
        // 标记为 deleted（但声明仍然存在）
    if 任何成员/基类的默认构造被删除/不可访问:
        // 标记为 deleted
    return true  // 生成

ShouldDeclareCopyConstructor(X):
    if X 有用户声明的移动构造 或 移动赋值:
        return false  // 拷贝被删除（不是"不生成"）
    if X 有用户声明的拷贝构造:
        return false
    if X 有用户声明的析构:
        return true   // C++98 兼容：有析构不影响拷贝
    return true

ShouldDeclareMoveConstructor(X):
    if X 有用户声明的拷贝构造/拷贝赋值/移动赋值/析构:
        return false  // 不生成
    if 任何成员/基类不能被移动:
        // 标记为 deleted
    return true
```

---

## 第 6 层: 源码分析

### 6.1 Clang — `ShouldDeleteSpecialMember`

**项目**: LLVM Clang
**版本**: `llvmorg-17.0.6`
**文件**: `clang/lib/Sema/SemaDeclCXX.cpp`

Clang 中判断隐式特殊成员是否应标记为 `deleted` 的核心函数是 `ShouldDeleteSpecialMember`（数千行的巨大函数）。关键逻辑：

```cpp
// 简化和注释化的核心逻辑还原
bool ShouldDeleteSpecialMember(CXXMethodDecl *MD, CXXSpecialMemberKind Kind) {
    CXXRecordDecl *RD = MD->getParent();

    // 遍历所有基类
    for (const auto &Base : RD->bases()) {
        CXXRecordDecl *BaseDecl = Base.getType()->getAsCXXRecordDecl();
        CXXMethodDecl *BaseSM = LookupSpecialMember(BaseDecl, Kind);

        // 如果基类的对应特殊成员是 deleted 或不可访问 →
        // 派生类的这个特殊成员也 deleted
        if (!BaseSM || BaseSM->isDeleted() || !BaseSM->isAccessible())
            return true;
    }

    // 遍历所有非静态成员
    for (const auto *Field : RD->fields()) {
        QualType FieldType = Field->getType();
        CXXRecordDecl *FieldDecl = FieldType->getAsCXXRecordDecl();

        if (Kind == CXXDefaultConstructor) {
            // const 成员 + 没有默认初始化器 → deleted
            if (FieldType.isConstQualified() && !Field->hasInClassInitializer())
                return true;
        }

        if (Kind == CXXMoveConstructor || Kind == CXXMoveAssignment) {
            // 如果成员类型没有对应的特殊成员 → deleted
            // 注意：对于移动构造，const 成员无法"移动"，但不会 deleted
            // （移动 const 等价于拷贝 → 编译通过）
        }

        // 成员的对应特殊成员 deleted/不可访问 → 本类也 deleted
        if (FieldDecl) {
            CXXMethodDecl *FieldSM = LookupSpecialMember(FieldDecl, Kind);
            if (!FieldSM || FieldSM->isDeleted() || !FieldSM->isAccessible())
                return true;
        }
    }

    // 虚析构函数的特殊情况：
    // 如果基类的析构是 deleted，派生类无法生成析构
    // 这会导致 new Derived() 无法 delete → 编译报错

    return false;  // 可以生成
}
```

### 6.2 Clang — `DefineImplicitDefaultConstructor`

当实际需要函数体时（odr-use），Clang 调用 `DefineImplicitDefaultConstructor`：

```cpp
// clang/lib/Sema/SemaDeclCXX.cpp
void Sema::DefineImplicitDefaultConstructor(SourceLocation CurrentLocation,
                                            CXXConstructorDecl *Constructor) {
    // 1. 确保 decl 是默认构造函数
    assert(Constructor->isDefaultConstructor());

    // 2. 为所有需要初始化的成员生成初始化器（member initializers）
    //    包括：
    //    - 基类的默认构造调用
    //    - 有类内初始化器（int x = 5;）的成员
    //    - 类类型成员的默认构造调用
    //    不初始化：
    //    - 内置类型的成员（如 int, float）——保持未初始化值

    // 3. 设置构造函数体为空（复合语句：{}）

    // 4. 标记为已定义，设置 "implicitly-defined" 属性
    Constructor->setImplicitlyDefined(true);
    Constructor->setBody(new CompoundStmt({}));
}
```

### 6.3 Clang — 隐式声明规则的核心

Clang 在声明类时（`ActOnFields` → `CheckCompletedCXXClass`）调用 `AddImplicitlyDeclaredMembersToClass`：

```cpp
// 伪代码还原关键判断逻辑
void AddImplicitlyDeclaredMembersToClass(CXXRecordDecl *RD) {
    // 1. 默认构造函数
    if (!RD->hasUserDeclaredConstructor()) {
        if (ShouldDeclareDefaultConstructor(RD))
            AddDefaultConstructor(RD);
    }

    // 2. 析构函数
    if (!RD->hasUserDeclaredDestructor())
        AddDestructor(RD);

    // 3. 拷贝构造函数
    if (ShouldDeclareCopyConstructor(RD)) {
        if (!RD->hasUserDeclaredCopyConstructor())
            AddCopyConstructor(RD);  // 如果成员/基类不可拷贝 → deleted
    }

    // 4. 拷贝赋值
    if (ShouldDeclareCopyAssignment(RD)) { /* 类似 */ }

    // 5. 移动构造函数
    if (ShouldDeclareMoveConstructor(RD))
        AddMoveConstructor(RD);

    // 6. 移动赋值
    if (ShouldDeclareMoveAssignment(RD))
        AddMoveAssignment(RD);
}
```

### 6.4 Howard Hinnant 的 Rule of Five 提案（2013）

**来源**: N3578 "Proposing the Rule of Five" (open-std.org)

Hinnant 在这篇短文中正式命名了 "Rule of Five"，源自他在 StackOverflow 的回答和 ACCU 2014 演讲。核心论点：

> If you define any of the five special member functions (destructor, copy constructor, copy assignment, move constructor, move assignment), you should explicitly declare all five. The compiler will not guess your intent—it will conservatively suppress or delete the ones you didn't write.

这统一了 C++98 的 Rule of Three 和 C++11 的移动语义，避免了"写了析构函数后移动操作不生成"这个最常见的陷阱。

---

## 第 7 层: 对比与边界

### 7.1 Rule of Zero vs Rule of Five vs Rule of Three

| | Rule of Three (C++98) | Rule of Five (C++11) | Rule of Zero (C++11) |
|---|---|---|---|
| **定义** | 自定义析构/拷贝构造/拷贝赋值中的任一个，就要定义全部三个 | 自定义五个特殊成员（析构+拷贝2+移动2）中的任一个，就要定义全部五个 | 不自定义任何特殊成员，让成员自己管理自己 |
| **前提** | 类管理原始资源 | 类管理原始资源，且需要移动语义 | 类只包含 RAII 成员 |
| **工作量** | 3 个函数 | 5 个函数 | 0 个函数 |
| **编译器依赖** | 低 | 低 | 高（成员必须正确实现 RAII） |
| **引擎适用范围** | 遗留代码 | 新代码中的资源类（GLBuffer, FileHandle） | 所有高层组合类 |

**选择指南：**

```cpp
// Rule of Zero —— 90% 的类应该用这个
class RenderSystem {
    std::unique_ptr<IRenderBackend> backend_;  // RAII
    std::vector<RenderPass> passes_;           // RAII
    // 0 个特殊成员函数声明
};

// Rule of Five —— 管理原始资源的类
class GPUBuffer {
    GLuint id_ = 0;
public:
    GPUBuffer() = default;
    ~GPUBuffer() { if (id_) glDeleteBuffers(1, &id_); }
    GPUBuffer(const GPUBuffer&) = delete;
    GPUBuffer& operator=(const GPUBuffer&) = delete;
    GPUBuffer(GPUBuffer&& o) noexcept : id_(o.id_) { o.id_ = 0; }
    GPUBuffer& operator=(GPUBuffer&& o) noexcept { /* ... */ return *this; }
};

// Rule of Three —— C++98 遗留代码，或 target 不支持 C++11 移动语义
class LegacyResource {
    FILE* file_ = nullptr;
public:
    LegacyResource() = default;
    ~LegacyResource() { if (file_) fclose(file_); }
    LegacyResource(const LegacyResource&);     // 深拷贝
    LegacyResource& operator=(const LegacyResource&);
    // 没有移动——回退到拷贝（编译器自动，C++98 无移动）
};
```

### 7.2 各语言中类似机制的对比

| 语言 | 默认构造 | 析构 | 拷贝 | 移动 | 特殊之处 |
|------|---------|------|------|------|---------|
| **C++** | 自动生成或手写 | 自动生成或手写 | 手写或 `= default` | 手写或 `= default` | 最精细的控制，但规则最复杂 |
| **Rust** | `Default` trait (opt-in) | `Drop` trait (手写) | `Clone` trait (opt-in) | 移动是默认！`Copy` trait 才是 opt-in | 编译器拒绝 use-after-move |
| **Go** | 零值初始化（自动） | 无析构（只有 `defer`） | 逐字段拷贝（自动+深拷贝部分类型） | 同拷贝 | 无 RAII，需显式 `defer` |
| **C#** | 总是有默认构造 | 无确定析构（GC + `IDisposable`） | `ICloneable` + 手写 | 无 | 非内存资源需 `using` 块手动释放 |
| **Python** | `__init__` (手写) | `__del__` (不可靠的 GC 回调) | `copy.copy`/`copy.deepcopy` | 无 | 无确定性销毁 |

### 7.3 性能特征

```cpp
// Benchmark: 拷贝 vs 移动 1MB 数据的开销
// （x86-64, -O2, std::vector<int> 约 262144 个元素）

struct CopyOnly {
    std::vector<int> data;
    CopyOnly(const CopyOnly& o) : data(o.data) {}     // ~0.5ms (深拷贝 1MB)
};

struct MoveOnly {
    std::vector<int> data;
    MoveOnly(MoveOnly&& o) noexcept : data(std::move(o.data)) {}
    // ~3ns (交换三个指针！)
};

struct Defaulted {
    std::vector<int> data;
    // 不写任何特殊成员
    // 拷贝 ~0.5ms
    // 移动 ~3ns
    // 编译器生成的与手写性能相同——零成本抽象
};
```

**关键数据：**
- `= default` 的移动构造与手写**汇编完全一致**（编译器内联展开为逐成员 `std::move`）
- `= default` 的拷贝构造同样零开销
- 唯一"成本"是**二进制体积**：每个翻译单元可能生成一份函数体副本（除非链接时优化）

### 7.4 陷阱与边界情况

**陷阱 1：写了析构 → 移动消失了**

```cpp
struct Timer {
    std::chrono::steady_clock::time_point start;
    Timer() : start(std::chrono::steady_clock::now()) {}
    ~Timer() { log("elapsed: ", std::chrono::steady_clock::now() - start); }
    // 没有声明拷贝和移动
};

// 使用时：
std::vector<Timer> timers;
timers.push_back(Timer{});  // 调用的是拷贝构造！不是移动！
// 因为 Timer 有用户声明析构 → 移动不生成 → 回退到拷贝
// 但拷贝构造调用了编译器生成的版本（逐成员拷贝，没问题）
//
// 解决方案：显式 = default 移动操作
Timer(Timer&&) noexcept = default;
Timer& operator=(Timer&&) noexcept = default;
```

**陷阱 2：虚析构 + Rule of Zero**

```cpp
class IPlugin {
public:
    virtual ~IPlugin() = default;  // 虚析构
    virtual void execute() = 0;
    // 有用户声明析构 → 移动不生成！
    // 但基类通常通过 unique_ptr<IPlugin> 管理，不直接移动
    // 所以这不是真正的陷阱——但要知道原因
};
```

**陷阱 3：`noexcept` 遗漏导致性能暴跌**

```cpp
class Bad {
    std::vector<int> data;
public:
    Bad(Bad&& other)       // 忘记写 noexcept
        : data(std::move(other.data)) {}
    // ... 拷贝 ...
};

std::vector<Bad> items;
items.reserve(100);
// 扩容时：vector 检测到 Bad 的移动构造不是 noexcept
// → 回退到拷贝构造！逐个深拷贝 1MB 数据
// → vs 移动的 3ns 指针交换，拷贝花了 0.5ms × 100 = 50ms
```

**陷阱 4：移动后源对象不能假设为空**

```cpp
// 编译器生成的移动：对内置类型成员（int, float, 指针）做的是拷贝！
struct Particle {
    std::string name;  // 移动 → 源变为空字符串
    float lifetime;    // 移动就是拷贝！源保持原值
};

Particle a{"fire", 3.0f};
Particle b = std::move(a);
// b.name == "fire"  ✓
// a.name == ""      ✓ (std::string 移动后为空)
// b.lifetime == 3.0 ✓
// a.lifetime == 3.0 ← 仍然是 3.0！移动没有"偷走"这个值
```

---

## 常见面试题

### Q1: "Rule of Three 和 Rule of Five 分别是什么？什么时候用哪个？"

- **Rule of Three**（C++98）：自定义析构、拷贝构造、拷贝赋值中任何一个 → 自定义全部三个。
- **Rule of Five**（C++11）：扩展为五个——析构、拷贝构造、拷贝赋值、移动构造、移动赋值。
- **Rule of Zero**（C++11）：不自定义任何特殊成员，只包含 RAII 成员，让编译器全权处理。

**选择**：优先 Rule of Zero。当且仅当类直接管理原始资源（裸指针、文件句柄、GPU 资源）时用 Rule of Five。Rule of Three 仅用于遗留代码和 C++98 兼容目标。

### Q2: "编译器什么时候会自动生成移动构造函数？什么时候不生成？"

不生成移动构造的条件（满足任一）：

1. 有用户声明的拷贝构造函数
2. 有用户声明的拷贝赋值运算符
3. 有用户声明的移动赋值运算符
4. 有用户声明的析构函数
5. 有成员或基类不能被移动（此时**声明存在但标记为 deleted**，而非不生成）

另：即使以上都不满足，如果有任何非静态成员是 `const` 或引用类型，移动构造会被**隐式删除**。

### Q3: "`= default` 和完全不写有什么区别？"

| | 不写 | `= default` |
|---|---|---|
| 隐式声明时机 | 编译器在类定义完成时 | 你显式写的地方 |
| 若编译器无法生成 | odr-use 时报错（或被隐式删除） | 声明处立即报错 |
| 是否为平凡 | 可能 | 可能 |
| 你声明了析构后还能用吗 | 对移动构造：不生成 | 对移动构造：可以 `= default` 强制生成 |
| 推荐 | 符合 Rule of Zero 时 | 需要显式表达意图时 |

### Q4: "为什么移动构造必须标记 `noexcept`？"

`std::vector` 扩容时的异常安全保证：如果移动构造抛异常，源数据已在移动中途被修改——无法回退。因此 `vector` 检测移动构造是否 `noexcept`；如果不是，回退到**拷贝构造**（拷贝失败时源数据完好）。

这导致性能差异可达 **10000 倍**（拷贝 1MB vector vs 移动 3 个指针）。

### Q5: "基类的析构函数为什么应该是 virtual 的？"

通过基类指针 `delete` 派生类对象时，如果基类析构不是 virtual，只会调用基类析构而不会调用派生类析构——派生类的资源泄漏。

```cpp
class Base { ~Base() {} };              // 非虚析构——灾难
class Derived : public Base {
    std::vector<int> huge_data;
};

Base* p = new Derived();
delete p;  // 只调用了 ~Base()！huge_data 泄漏！
```

规则：**只要一个类被设计为基类，析构函数就应该是 `public virtual` 或 `protected non-virtual`**（C++ Core Guidelines C.35）。

---

## 延伸主题

1. **移动语义与完美转发** — `std::move` 和 `std::forward` 的深层原理
2. **trivial vs non-trivial** — 为什么 `std::is_trivially_copyable` 在引擎的 `memcpy` 优化中至关重要
3. **C++20/23 比较运算符 `<=>`** — 三路比较如何影响特殊成员函数的生成
4. **虚函数表（vtable）与多态** — 虚析构的底层实现和对齐影响
5. **编译器 RVO/NRVO（返回值优化）** — 为什么你的移动构造可能永远不会被调用
