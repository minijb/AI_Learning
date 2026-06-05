---
title: "std::expected 深度剖析"
updated: 2026-06-05
---

# std::expected 深度剖析

> 深度等级: 第 7 层（对比与边界）
> 关联学习计划: 无
> 分析日期: 2026-05-29
> 关键词: `std::expected`, `std::unexpected`, monadic error handling, C++23, `and_then`, `or_else`, `transform`

---

## 第 1 层: 直觉理解

`std::expected<T, E>` 是一个"**要么有值，要么有错误**"的容器——它同时持有**两个槽位**，但每次只有一个是活跃的。

**类比：快递包裹**

你下单了一个商品。快递送到时有两种可能：

- **包裹完好** → 你拆开拿到商品（`T`）
- **包裹损坏** → 你得到一张破损报告单（`E`），上面写着损坏原因

你不会同时拿到商品和报告单。`std::expected` 就是这个"包裹"——它替你管理这两种状态的切换，强迫你在使用前**显式检查**到底是哪一种。

```cpp
std::expected<int, std::string> divide(int a, int b) {
    if (b == 0)
        return std::unexpected("division by zero");
    return a / b;
}

auto result = divide(10, 2);
if (result) {
    std::cout << "结果: " << *result << '\n';  // 5
} else {
    std::cout << "错误: " << result.error() << '\n';
}
```

**核心思想**：把错误当作**一等公民**放在返回类型里，而不是靠异常或全局 errno 这种"旁路"传递。

---

## 第 2 层: 使用场景

### 什么时候用 `std::expected`

| 场景 | 为什么 |
|------|--------|
| 函数可能失败，且失败是**可预期的** | 文件解析、网络请求、配置验证——这些失败不是"异常"，是正常业务流程 |
| 需要**强制调用方处理错误** | `[[nodiscard]]` 属性 + 访问值前必须检查，编译器/静态分析帮你找到遗漏 |
| 错误需要携带**结构化信息** | 不仅是"失败了"，还要传递错误码、错误消息、上下文 |
| 在**组合/管道式**调用链里传递错误 | 配合 `and_then`、`or_else`、`transform`，不用写层层嵌套的 if-else |
| **无异常环境**（嵌入式、游戏引擎、noexcept 约束的代码） | 很多项目禁用了异常，但又不想回到 C 风格的 int 返回码 |

### 什么时候不用

| 场景 | 原因 | 替代方案 |
|------|------|---------|
| 函数不会失败 | 用 `expected` 是过度设计 | 直接返回 `T` |
| 失败是**不可恢复**的（precondition violation、程序 bug） | 应该用 assert 或异常 | `assert()`、抛出异常 |
| 只需要"有/没有"语义，不需要错误信息 | `expected` 的 E 会携带额外开销 | `std::optional<T>` |
| 错误类型繁复，需要多态或继承体系 | `expected<T, E>` 的 E 是固定类型 | `std::exception` + try/catch |
| 需要在**多层调用栈**间自动传播错误 | `expected` 每层都要显式检查或组合，做不到异常那种"自动冒泡" | 异常 |

### 决策流程

```
函数可能失败吗？
  ├─ 否 → 返回 T
  └─ 是 → 失败是程序 bug 吗？
           ├─ 是 → assert / 异常
           └─ 否 → 需要传递错误详情吗？
                    ├─ 否 → std::optional<T>
                    └─ 是 → std::expected<T, E>
```

---

## 第 3 层: API 层

### 头文件和基本类型

```cpp
#include <expected>

// 主模板
template<class T, class E>
class expected;

// void 偏特化
template<class E>
class expected<void, E>;

// 辅助类型
struct unexpect_t { explicit unexpect_t() = default; };
inline constexpr unexpect_t unexpect{};

template<class E>
class unexpected;  // 包装错误值的类型
```

### 构造函数

```cpp
// 从值构造
std::expected<int, std::string> e1 = 42;           // 隐式

// 从 unexpected 构造（= 错误状态）
std::expected<int, std::string> e2 =
    std::unexpected<std::string>("oops");           // 显式

// 用 unexpect_t 标记 + 原地构造错误
std::expected<int, std::string> e3(
    std::unexpect, "file not found");               // 转发参数构造 E

// 原地构造值
std::expected<std::vector<int>, Err> e4(
    std::in_place, 10, 42);                         // vector(10, 42)

// 从可转换的类型构造
std::expected<int, std::string> e5 = 3.14;          // int(3)

// 拷贝/移动
auto e6 = e1;                                       // 拷贝
auto e7 = std::move(e1);                            // 移动
```

### 观测器（Observers）

```cpp
std::expected<T, E> e = compute();

// 检查是否有值
bool b1 = e.has_value();      // true 当持有 T
bool b2 = e;                   // operator bool, 等价 has_value()

// 访问值（未检查 → 未定义行为）
T&  v1 = *e;                   // 无检查解引用
T*  v2 = e.operator->();      // 指针访问
T&  v3 = e.value();           // 有检查：无值时抛 bad_expected_access<E>

// 带默认值
T    v4 = e.value_or(fallback);

// 访问错误（未检查 → 未定义行为，仅在无值时合法）
E&   err = e.error();

// 移动语义版本（右值重载）
T&&  v5 = *std::move(e);
E&&  v6 = std::move(e).error();
```

### `bad_expected_access<E>` 异常

```cpp
template<class E>
class bad_expected_access : public std::bad_expected_access<void> {
public:
    explicit bad_expected_access(E e);
    const char* what() const noexcept override;
    E& error() & noexcept;
    const E& error() const & noexcept;
    E&& error() && noexcept;
    const E&& error() const && noexcept;
};
```

调用 `.value()` 且对象处于错误状态时抛出。

### 单子操作（Monadic Operations, C++23）

这是 `std::expected` 最强大的部分——允许链式组合带上错误传播。

```cpp
// and_then: 如果有值，用该值调用 f，f 返回 expected
//           如果无值，直接传播错误
template<class F>
constexpr auto and_then(F&& f) &;
// 返回类型: invoke_result_t<F, T&>（必须是 expected 的特化）

// or_else: 如果有值，返回自身
//          如果无值，用错误调用 f，f 返回 expected
template<class F>
constexpr auto or_else(F&& f) &;

// transform: 如果有值，映射 T → U，包装回 expected<U, E>
//            如果无值，传播错误
template<class F>
constexpr auto transform(F&& f) &;
// 返回类型: expected<invoke_result_t<F, T&>, E>

// transform_error: 如果无值，映射 E → G，包装回 expected<T, G>
//                  如果有值，传播值
template<class F>
constexpr auto transform_error(F&& f) &;
// 返回类型: expected<T, invoke_result_t<F, E&>>
```

**示例：链式组合**

```cpp
std::expected<std::string, AppError> process_file(const std::string& path) {
    return read_file(path)                    // expected<vector<byte>, AppError>
        .and_then(parse_json)                 // 仅在前一步成功时调用
        .transform(extract_field)             // 映射值
        .or_else(fallback_to_cache)           // 失败时的恢复路径
        .transform_error(enrich_error);       // 丰富错误信息
}
```

### 比较运算符

```cpp
// 两个 expected 比较：
// - 两者都有值 → 比较值
// - 两者都有错误 → 比较错误
// - 状态不同 → has_value 的 < 无值的
e1 == e2;  e1 != e2;
e1 <  e2;  e1 <= e2;  e1 >  e2;  e1 >= e2;

// 与值比较：
e == T{42};   T{42} == e;
// 仅当 e 有值时有效，且等价于 *e == T{42}

// 与 unexpected 比较：
e == std::unexpected<E>{err};
```

### swap

```cpp
e1.swap(e2);
// 两者都有值 → swap 值
// 两者都有错误 → swap 错误
// 状态不同 → 需要移动构造 + 析构
```

---

## 第 4 层: 行为契约

### 生命周期状态机

```
                    ┌──────────────┐
                    │  构造/赋值    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼                         ▼
      ┌──────────────┐          ┌──────────────┐
      │ 有值状态      │          │ 错误状态      │
      │ (T 活跃)      │          │ (E 活跃)      │
      └──────┬───────┘          └──────┬───────┘
             │ 移动赋值/               │ 移动赋值/
             │ 赋值 = T/               │ 赋值 = unexpected/
             │ emplace                 │ emplace(unexpect,...)
             └────────────┼────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ 析构          │
                    │ (销毁活跃成员)│
                    └──────────────┘
```

### 不变式（Invariants）

1. **互斥性**：`has_value() == true` ⟺ `T` 活越且 `E` 不活跃；`has_value() == false` ⟺ `E` 活跃且 `T` 不活跃
2. **析构安全性**：析构函数只销毁当前活跃的成员（`T` 或 `E`）
3. **移动后的状态**：移动后的 `expected` 仍持有值（T 被移动，处于"有效但未指定"状态），`has_value()` 不变
4. **`unexpected<E>` 要求**：`E` 必须不是 `std::in_place_t`、`std::unexpect_t`，且必须可析构

### 前置 / 后置条件

| 操作 | 前置条件 | 后置条件 | 违反后果 |
|------|---------|---------|---------|
| `operator*()` | `has_value() == true` | 返回 T 的左值引用 | **未定义行为** |
| `operator->()` | `has_value() == true` | 返回 T 的指针 | **未定义行为** |
| `value()` | 无 | 有值时返回 T；否则抛出 `bad_expected_access<E>` | 异常 |
| `error()` | `has_value() == false` | 返回 E 的左值引用 | **未定义行为** |
| `emplace(args...)` | 无（T 可从 args 构造） | `has_value() == true` | 构造失败则 `expected` 处于无效状态（[INFERENCE] 取决于实现是否提供强异常保证） |
| `and_then(f)` | 无（f 的返回类型必须是 `expected` 特化） | 传播错误或返回 f 的结果 | 编译错误 |

### 异常安全

标准要求 `std::expected` 提供**基本异常保证（basic guarantee）**：
- 操作抛出异常后，对象仍处于有效状态（可安全析构）
- 但不保证值或错误状态保持不变

**构造/赋值的保证**：
- 从值构造/赋值：如果 T 的构造/赋值抛出，`expected` 的行为取决于实现在析构旧值、构造新值之间的顺序
- `emplace`：如果 T 的构造抛出，`expected` 可能丢失旧值（取决于实现是否提供了强异常保证）
- **关键约束**：一旦进入了错误状态，再 `emplace` 值如果失败，对象应保持错误状态

### 单子法则（Monad Laws）

对于 `and_then` 和 `or_else`，期望的行为遵循单子定律：

**左单位元（Left Identity）**：
```cpp
// 包装一个值然后 and_then(f) ≡ 直接对值应用 f
make_expected(x).and_then(f) ≡ f(x)
```

**右单位元（Right Identity）**：
```cpp
// and_then(make_expected) ≡ 原样返回
e.and_then([](auto&& v) { return std::expected<T, E>(v); }) ≡ e
```

**结合律（Associativity）**：
```cpp
e.and_then(f).and_then(g) ≡ e.and_then([&](auto&& v) { return f(v).and_then(g); })
```

---

## 第 5 层: 实现原理

### 存储结构

`std::expected<T, E>` 的典型实现使用 **tagged union**（带标签的联合体）：

```cpp
template<class T, class E>
class expected {
    union {
        T m_val;   // 值槽位
        E m_err;   // 错误槽位
    };
    bool m_has_value;  // 判别式
};
```

**关键设计决策**：

1. **为什么用 union 而不是 `std::variant`？**
   - `std::variant` 在 C++17 中不支持单子操作，且动态分配在某些实现中不可避免
   - `expected` 是类型安全的、编译期确定的两种状态，不需要 variant 的通用性
   - union 方案零开销，大小精确可控

2. **为什么不是 `bool` + `optional`？**
   - 两个 `optional` 会携带两个 `bool` 判别式，浪费空间
   - 语义上，`expected` 是"互斥的"，`optional` 是"独立的"

### `std::expected<void, E>` 的偏特化

当 `T = void` 时，不需要存储值：

```cpp
template<class E>
class expected<void, E> {
    union {
        std::monostate m_dummy;  // 可能用于对齐
        E m_err;
    };
    bool m_has_value;
};
```

这用于**只表示成功/失败**的场景——类似 `std::optional` 但可以携带错误信息。

### `std::unexpected<E>` 的实现

`unexpected` 是一个轻量包装器，存在目的纯粹是**消歧义**——让编译器区分"用值构造"和"用错误构造"：

```cpp
template<class E>
class unexpected {
public:
    constexpr explicit unexpected(const E& e) : m_val(e) {}
    constexpr explicit unexpected(E&& e) : m_val(std::move(e)) {}

    // 支持从其他类型构造（用于隐式转换场景）
    template<class... Args>
    constexpr explicit unexpected(std::in_place_t, Args&&... args)
        : m_val(std::forward<Args>(args)...) {}

    constexpr const E& error() const & noexcept { return m_val; }
    constexpr E& error() & noexcept { return m_val; }
    constexpr E&& error() && noexcept { return std::move(m_val); }

private:
    E m_val;
};
```

**为什么是 `explicit` 构造函数？** 防止意外将错误值隐式转换为 `expected` 的值。例如：

```cpp
void f(std::expected<int, std::string> e);
f("error");  // 如果没有 explicit：该调用谁？int 还是 string？
             // 有了 explicit，必须写成 f(std::unexpected("error"))
```

### 赋值操作的实现

赋值是 `expected` 实现中最复杂的部分——需要在四种状态转换间正确处理析构和构造：

```cpp
template<class T, class E>
expected<T,E>& expected<T,E>::operator=(const expected& rhs) {
    if (this == &rhs) return *this;

    if (m_has_value && rhs.m_has_value) {
        m_val = rhs.m_val;                          // 值 → 值：拷贝赋值
    } else if (m_has_value && !rhs.m_has_value) {
        m_val.~T();                                 // 值 → 错误：析构值
        ::new (&m_err) E(rhs.m_err);                //                    构造错误
    } else if (!m_has_value && rhs.m_has_value) {
        m_err.~E();                                 // 错误 → 值：析构错误
        ::new (&m_val) T(rhs.m_val);                //                    构造值
    } else {
        m_err = rhs.m_err;                          // 错误 → 错误：拷贝赋值
    }

    m_has_value = rhs.m_has_value;
    return *this;
}
```

**关键技巧**：使用 placement new + 显式析构管理 union 的活跃成员。C++ 标准库实现通常使用 `std::construct_at` 和 `std::destroy_at`（C++17 起提供）来替代直接调用，提供更好的 constexpr 支持。

### `and_then` 的实现

```cpp
template<class T, class E>
template<class F>
constexpr auto expected<T, E>::and_then(F&& f) & -> /* 返回类型 */ {
    using U = std::remove_cvref_t<
        std::invoke_result_t<F, T&>
    >;  // 必须是 expected 的特化

    if (m_has_value) {
        return std::invoke(std::forward<F>(f), m_val);
    } else {
        return U(std::unexpect, m_err);
    }
}
```

### 平凡可析构优化

现代 STL 实现（libstdc++ 14+）会对**平凡可析构**的 `T` 和 `E` 做优化：
- 如果 `T` 和 `E` 都是 trivially destructible，`expected` 也是 trivially destructible
- 如果 `T` 和 `E` 都是 trivially copyable，拷贝/移动操作也可能被优化为 `memcpy`

```cpp
// libstdc++ 14 的实现策略（简化）
// 使用条件编译根据 is_trivially_destructible_v<T/E> 选择析构策略
~expected() {
    if constexpr (!std::is_trivially_destructible_v<T> ||
                  !std::is_trivially_destructible_v<E>) {
        if (m_has_value)
            std::destroy_at(&m_val);
        else
            std::destroy_at(&m_err);
    }
    // 否则：平凡析构，什么都不用做
}
```

### 空间开销

```cpp
sizeof(std::expected<char, std::error_code>)    // 典型: 16 (1 + 3 填充 + 8 + 4 的 error_code)
sizeof(std::expected<int,  int>)                 // 典型: 8  (4 + 4, bool 对齐到 int)
sizeof(std::expected<std::string, std::string>)  // 典型: 最大者 + bool + 填充
```

开销 = `max(alignof(T), alignof(E))` 对齐后的 union + 至少 1 字节判别式 + 填充 → 通常比最大的成员多 1 个字（word）。

---

## 第 6 层: 源码分析

### libstdc++ (GCC 14+)

文件位置: `libstdc++-v3/include/std/expected`

```cpp
// GCC 14 libstdc++ 实现（关键路径，有简化）
// 文件: libstdc++-v3/include/std/expected
// 版本: GCC 14.1 (2024-05)

template<typename _Tp, typename _Er>
class expected {
    // 核心存储结构
    struct _Expected_base {
        union {
            _Tp _M_val;
            _Er _M_err;
        };
        bool _M_has_val;

        // trivially destructible 优化
        constexpr ~_Expected_base() {
            if constexpr (!is_trivially_destructible_v<_Tp>
                       || !is_trivially_destructible_v<_Er>) {
                if (_M_has_val)
                    _M_val.~_Tp();
                else
                    _M_err.~_Er();
            }
        }
    } _M_base;

    // and_then 实现
    template<typename _Fn>
    constexpr auto and_then(_Fn&& __f) & {
        using _Up = remove_cvref_t<invoke_result_t<_Fn, _Tp&>>;
        static_assert(__is_expected_specialization<_Up>::value,
            "and_then: result must be a specialization of expected");

        if (_M_base._M_has_val)
            return std::invoke(std::forward<_Fn>(__f), _M_base._M_val);
        else
            return _Up(unexpect, _M_base._M_err);
    }

    // transform 实现
    template<typename _Fn>
    constexpr auto transform(_Fn&& __f) & {
        using _Up = remove_cv_t<invoke_result_t<_Fn, _Tp&>>;
        using _Res = expected<_Up, _Er>;

        if (_M_base._M_has_val)
            return _Res(std::invoke(std::forward<_Fn>(__f), _M_base._M_val));
        else
            return _Res(unexpect, _M_base._M_err);
    }
};
```

**libstdc++ 的特点**：
- 在 GCC 14 中完成了对 `expected` 的单子操作支持
- 使用了 `__is_expected_specialization` 内部 type trait 来在 `and_then` 中做编译期校验
- 使用条件 `if constexpr` 实现平凡可析构优化
- `_M_base` 结构体将 union 和 bool 捆绑，利于 ABI 稳定

### libc++ (Clang 19+)

文件位置: `libcxx/include/expected`

```cpp
// Clang libc++ 实现（简化）
// 文件: include/expected
// 版本: LLVM 19 (2024-09)

template<class _Tp, class _Err>
class expected {
    // libc++ 使用 _LIBCPP_NO_UNIQUE_ADDRESS 优化判别式
    struct _Rep {
        union {
            _Tp __val_;
            _Err __err_;
        };
        bool __has_val_;
    };
    _Rep __rep_;

    // 使用 __expected_construct 抽象构造操作，统一处理
    // trivially destructible 与非平凡的情况
    _LIBCPP_HIDE_FROM_ABI constexpr ~expected()
        noexcept(is_nothrow_destructible_v<_Tp>
              && is_nothrow_destructible_v<_Err>)
    {
        if constexpr (!is_trivially_destructible_v<_Tp> ||
                      !is_trivially_destructible_v<_Err>) {
            if (__rep_.__has_val_)
                std::destroy_at(&__rep_.__val_);
            else
                std::destroy_at(&__rep_.__err_);
        }
    }

    // and_then 实现（和 libstdc++ 几乎相同）
    template<class _Func>
    _LIBCPP_HIDE_FROM_ABI constexpr auto and_then(_Func&& __f) & {
        using _Up = remove_cvref_t<__invoke_of<_Func, _Tp&>>;
        static_assert(__is_expected<_Up>::value,
            "result of f() must be a specialization of std::expected");

        if (__rep_.__has_val_)
            return std::invoke(std::forward<_Func>(__f), __rep_.__val_);
        else
            return _Up(unexpect, __rep_.__err_);
    }
};
```

**libc++ 的特点**：
- 使用 `_LIBCPP_NO_UNIQUE_ADDRESS`（基于 `[[no_unique_address]]`）来在特定场景下优化 `bool` 的内存占用
- 使用 `__invoke_of` 内部类型萃取（等价于 `std::invoke_result`）

### MSVC STL (Visual Studio 2022 17.10+)

文件位置: MSVC STL `expected` 头文件

```cpp
// Microsoft STL 实现（简化）
// 文件: <expected>
// 版本: VS 2022 17.10 (2024-05)

template <class _Ty, class _Err>
class expected {
private:
    struct _Storage {
        union {
            _Ty _Value;
            _Err _Error;
        };
        bool _Has_value;

        constexpr ~_Storage() {
            if constexpr (!conjunction_v<
                    is_trivially_destructible<_Ty>,
                    is_trivially_destructible<_Err>>) {
                if (_Has_value) {
                    _Value.~_Ty();
                } else {
                    _Error.~_Err();
                }
            }
        }
    };
    _Storage _My storage;

    // transform 实现
    template <class _Fn>
    constexpr auto transform(_Fn&& _Func) & {
        using _Ret = remove_cv_t<invoke_result_t<_Fn, _Ty&>>;
        using _Result_type = expected<_Ret, _Err>;

        if (_Mystorage._Has_value) {
            return _Result_type(
                std::invoke(std::forward<_Fn>(_Func), _Mystorage._Value));
        } else {
            return _Result_type(unexpect, _Mystorage._Error);
        }
    }

    // void 偏特化
    template <class _Err>
    class expected<void, _Err> {
        // 没有值槽位，只有一个 optional-like error
        // ...
    };
};
```

**MSVC 的特点**：
- 使用 `_Mystorage` 命名约定（微软传统风格）
- void 偏特化直接不分配值的存储空间
- VS 2022 17.10（2024 年 5 月）首次完整支持

### 三巨头对比

| 特性 | libstdc++ (GCC 14) | libc++ (Clang 19) | MSVC STL (VS 17.10) |
|------|-------------------|-------------------|---------------------|
| 单子操作 | ✅ | ✅ | ✅ |
| 平凡可析构优化 | ✅ `if constexpr` | ✅ `if constexpr` | ✅ `if constexpr` |
| `[[no_unique_address]]` 优化 | ✅ 直接 union+bool | ✅ `_LIBCPP_NO_UNIQUE_ADDRESS` | ✅ 直接 union+bool |
| `constexpr` 支持 | 全部构造/赋值/单子操作 | 全部 | 全部 |
| `void` 偏特化 | ✅ 已实现 | ✅ 已实现 | ✅ 已实现 |

---

## 第 7 层: 对比与边界

### 与同类方案的全维度对比

| 维度 | `std::expected<T,E>` | 异常 | 错误码 (`std::error_code`) | `std::optional<T>` | Rust `Result<T,E>` |
|------|---------------------|------|--------------------------|-------------------|-------------------|
| **错误信息** | 任意类型 `E` | 多态 `std::exception` | `int` + category | 无 | 任意类型 `E` |
| **性能（成功路径）** | 接近零开销 | 零开销（实际） | 返回码的一字节 | 接近零开销 | 接近零开销（枚举判别式优化） |
| **性能（失败路径）** | 返回码+构造 `E` | 栈展开（~数十 ns 到 μs） | 返回码 | N/A | 返回码+构造 `E` |
| **强制检查** | ⚠️ `operator*` 不检查；`value()` 抛异常 | ❌ 可忽略 catch | ❌ `[[nodiscard]]` 只是建议 | ⚠️ `operator*` 不检查 | ✅ `unwrap()`/`?` 强制 |
| **组合能力** | ✅ `and_then/or_else/transform` | ❌ 需 try/catch 嵌套 | ❌ 需手动 if 检查 | ✅ `and_then/or_else/transform` | ✅ 丰富的组合子 |
| **跨函数自动传播** | ❌ 每层都要参与传播 | ✅ 自动冒泡 | ❌ 每层都要检查+返回 | N/A (无错误状态) | ✅ `?` 运算符自动传播 |
| **二进制大小** | 小（无 unwinding 表） | 大（每个函数有 LSDA） | 最小 | 小 | 小 |
| **学习曲线** | 中等（单子思维） | 低（try/catch 直觉） | 低 | 低 | 中等 |
| **ABI 稳定性** | ⚠️ 取决于 T 和 E | ✅ 固定接口 | ✅ 固定类型 | ⚠️ 取决于 T | N/A (Rust 无稳定 ABI) |

### 性能特征

#### 成功路径

```cpp
// 对比：返回 expected vs 返回 optional vs 抛异常
// 编译: GCC 14 -O2

std::expected<int, std::string> f_expected(int a, int b) {
    if (b == 0) return std::unexpected("div0");
    return a / b;
}
// 成功路径生成的代码 ≈ 直接返回 int + 设置 has_value 标志
// mov eax, edi
// idiv esi
// mov byte [has_value], 1
// ret

int f_exception(int a, int b) {
    if (b == 0) throw std::runtime_error("div0");
    return a / b;
}
// 成功路径: 纯除法指令，无额外开销
// idiv esi
// ret
// （失败路径的开销在异常表中，不影响成功路径）
```

**结论**：成功路径上 `expected` 比异常多约 1-2 条指令（设置 `has_value` 位），差异可忽略。但异常的成功路径是真正零开销的。

#### 失败路径

```cpp
// expected 的失败路径
// 构造 unexpected → 移动到返回值 → 调用方检查 has_value → 取 error()
// 开销: ~几 ns 到几十 ns（取决于 E 的构造开销）

// 异常的失败路径
// throw → __cxa_allocate_exception → 构造异常 → 栈展开
//      → 查找 catch → __cxa_begin_catch
// 开销: 几十 μs 到几百 μs（取决于调用栈深度）
```

**结论**：失败路径上 `expected` 比异常快 **100-1000 倍**。这就是为什么无异常项目（游戏引擎、嵌入式）选择 `expected`。

### 设计取舍与争议

#### 1. `operator*` 不检查是安全漏洞吗？

```cpp
std::expected<int, Err> e = std::unexpected(Err{});
int x = *e;  // 未定义行为！静默失败
```

**为什么设计成这样？**

与 `std::optional` 一致。标准委员会认为：提供无检查版本是为了**性能关键路径**——如果你**已经**在上一行检查了 `has_value()`，再来一次检查是浪费。

```cpp
if (!e) return e.error();  // 已检查
int x = *e;                 // 此时是安全的，不需要再检查
```

**最佳实践**：永远使用 `.value()`（抛异常）或 `.value_or(fallback)`，只在性能关键且已验证的路径上使用 `operator*`/`operator->`。

#### 2. 为什么 `E` 不支持 `void`？

标准不要求 `E` 支持 `void`。如果需要"知道失败了但不知道原因"，用 `std::optional<T>`。

`std::expected<void, E>` 存在的意义是：**只表示成功/失败，但失败时有详细信息**。

```cpp
// 返回 expected<void, ErrCode>：表示一个可能失败的操作
// 返回成功: return {};
// 返回失败: return std::unexpected(ErrCode::Timeout);

std::expected<void, ErrCode> connect(const std::string& host);
```

#### 3. 没有 `try` 运算符（对比 Rust 的 `?`）

C++23 的 `std::expected` **没有**类似 Rust `?` 的自动传播运算符。提案 P2561（`operator??`）曾被讨论，但未进入标准。

**变通方案**：

```cpp
// 宏方案（常见于游戏引擎代码库）
#define TRY(expr)                                         \
    ({                                                     \
        auto&& _tmp = (expr);                              \
        if (!_tmp) return std::unexpected(_tmp.error());   \
        *_tmp;                                             \
    })

auto result = TRY(may_fail_one()) + TRY(may_fail_two());

// 单子链方案
auto result = may_fail_one()
    .and_then([](int a) {
        return may_fail_two()
            .transform([a](int b) { return a + b; });
    });
```

#### 4. `expected<T,E>` vs `expected<T,error_code>`：泛型 vs 统一错误类型

`std::expected` 允许**任意** `E`，这带来了灵活性，但也带来了**错误类型不兼容**的问题：

```cpp
std::expected<int, FileError>  read_int();
std::expected<int, ParseError> parse_int(const std::string&);

// 无法直接组合！
read_int().and_then(parse_int);  // 编译错误: FileError != ParseError
```

**解决方案**：
- 统一使用 `std::error_code` 或项目定义的通用错误 enum
- 用 `transform_error` 将一种错误映射为另一种
- 定义项目的 `AppError` 类型包含所有子错误

#### 5. 移动语义的陷阱

```cpp
std::expected<std::string, Err> e = std::string("hello");

// 陷阱：移动后 e 仍然 has_value() == true
auto s = std::move(*e);
// e 现在持有被移动的 string（空、但有效）
// has_value() 仍然是 true！

// 更好的做法：
auto s2 = std::move(e).value();  // 或 std::move(*e)
// 明确表达移动语义
```

### C++ 版本演进时间线

| 版本 | 状态 |
|------|------|
| C++20 | `std::expected` 提案 P0323R10 被接受，但**未进入** C++20 |
| C++23 | P0323R12 → 正式纳入标准，含单子操作 |
| C++26 (草案) | P2561 `operator??` 被讨论；可能的 `try_emplace` 扩展 |

### `std::expected` vs Other Monads

| 类型 | 作用 | 单子操作 | 错误 |
|------|------|---------|------|
| `std::optional<T>` | 可能有值/可能为空 | `and_then`, `or_else`, `transform` | 无信息 |
| `std::expected<T, E>` | 值或错误 | `and_then`, `or_else`, `transform`, `transform_error` | 任意 `E` |
| `std::variant<Ts...>` | N 选 1 | 无（需 `std::visit`） | 间接表达 |
| `tl::expected<T,E>` (TartanLlama) | 值或错误 (C++11+) | `map`, `and_then`, `or_else` | 任意 `E` |
| `boost::outcome::result<T>` | 值或错误（含错误码） | `and_then`, `map` | `error_code` + `exception_ptr` |

---

## 常见面试题

### Q1: `std::expected` 和 `std::optional` 的核心区别是什么？

**A**: `optional<T>` 的"空"状态不携带任何错误信息——你只知道"没有值"。`expected<T,E>` 在"无值"时携带一个 `E` 类型的错误，可以传递结构化信息（错误码、消息、上下文）。

判断标准：如果调用方只需要知道"成功/失败"，用 `optional`；如果需要知道"为什么失败"，用 `expected`。

### Q2: `std::expected` 的存储模型是什么？为什么不用 `std::variant`？

**A**: `expected` 使用 tagged union（union + bool 判别式），而非 `variant`。理由：

1. `variant` 是泛型的 N 选 1，`expected` 只需 2 选 1——不需要 variant 的通用性开销
2. 固定的两种状态允许更优的编译期优化（平凡可析构路径可以完全消除析构代码）
3. `expected` 的双向单子操作（`and_then` 改变值、`or_else` 改变错误）在语义上与 variant 不匹配

### Q3: 为什么 `std::expected<T,E>` 的 `operator*` 不检查 `has_value()`？这是设计缺陷吗？

**A**: 不是设计缺陷，是有意的权衡：

- 性能关键路径上，调用方已经检查过 `has_value()`，不需要再检查一次
- 与 `std::optional` 保持一致
- `.value()` 提供了带检查的替代方案（抛 `bad_expected_access`）

如果项目要求强制安全，可以通过静态分析工具或包装类型强制执行 `.value()` 调用。

### Q4: 如何用 `std::expected` 在无异常的代码库中实现错误传播？

**A**: 三种策略：

1. **宏方案**：`#define TRY(expr) ...` — 模拟 Rust `?` 运算符
2. **单子链**：`.and_then().transform().or_else()` — 函数式组合
3. **手动传播**：`if (!result) return std::unexpected(result.error());` — 显式但冗长

生产级代码通常用方案 1 或 2，取决于团队对宏的接受程度。

### Q5: `std::expected<void, E>` 有什么用途？

**A**: 用于只返回成功/失败信号但失败时携带详细错误信息的场景。典型如：

```cpp
std::expected<void, DbError> begin_transaction();
std::expected<void, NetError> connect(const std::string& host);
std::expected<void, ParseError> validate_config(const Config& cfg);
```

这些函数成功时不产生任何值，但失败时需要传递具体的错误原因。

---

## 延伸主题

学完 `std::expected` 后可以探索的相关主题：

- **Rust 的 `Result<T,E>` 和 `?` 运算符** — 理解 C++ `expected` 的设计灵感来源。Rust 的类型系统和所有权模型如何让错误处理更安全
- **`std::optional`** — `expected` 的简化版兄弟。学习其单子操作和与 `expected` 的差异
- **Haskell 的 `Either` 和 `Maybe` monad** — 函数式编程中错误处理的理论基础。理解 monad laws 和 do-notation
- **`boost::outcome::result<T>`** — 比 `expected` 更强大的错误处理库，支持"成功/失败/异常"三态 + `error_code` 集成
- **异常 vs 错误码的大辩论** — 理解 C++ 社区关于错误处理的长达 30 年的争论。什么时候该用哪个
- **`[[nodiscard]]` 和编译器属性** — 如何利用 `[[nodiscard]]` 和静态分析强制调用方检查错误
- **C++ 协程 + `expected`** — P2564 提案探索了 `expected` 作为协程返回类型的可能性，让协程的错误处理更加自然
- **`tl::expected` (TartanLlama)** — C++11/14 中可用的 `expected` 实现。理解在 C++23 之前的工业级 polyfill 如何实现
