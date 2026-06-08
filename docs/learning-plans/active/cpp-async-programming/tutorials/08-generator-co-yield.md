---
title: Generator 与 co_yield
updated: 2026-06-08
tags: [cpp, coroutine, generator, co_yield, ranges]
---

# Generator 与 co_yield

> [!abstract] 本节目标
> 理解 `co_yield` 的底层机制，掌握 Generator 模式的实现与使用，能够从零编写自定义 Generator 类型，并利用它解决惰性序列生成问题。

## 一、概念

### 1.1 co_yield 的本质

`co_yield` 是 C++20 协程的关键字之一，它的语义是"暂停协程并向外产出一个值"。从编译器变换的角度看：

```cpp
co_yield expr;
```

等价于：

```cpp
co_await promise.yield_value(expr);
```

也就是说，`co_yield` 并非独立的协程原语——它只是 `co_await` 的语法糖，实际工作委托给 `promise_type::yield_value()`。

与 `co_return` 的对比：

| 关键字 | 含义 | promise 调用 | 协程状态 |
|--------|------|--------------|----------|
| `co_await` | 等待一个 Awaitable | `promise.await_transform(expr)` 或直接 `expr.operator co_await()` | 暂停，等待恢复 |
| `co_yield` | 产出值并暂停 | `promise.yield_value(expr)` | 暂停，可由调用者恢复 |
| `co_return` | 返回最终值并结束 | `promise.return_value(expr)` 或 `promise.return_void()` | 结束，不可恢复 |
| `co_return;` | 无值返回并结束 | `promise.return_void()` | 结束，不可恢复 |

### 1.2 Generator vs Task

| 特性 | Generator | Task |
|------|-----------|------|
| 产出模式 | 多次产出（序列） | 单次产出 |
| 调用者角色 | 拉取（pull） | 等待（await） |
| 恢复时机 | 调用者每次请求下一个值时 | 异步操作完成后自动恢复 |
| 典型场景 | 序列生成、惰性迭代、管道 | 异步 I/O、并发计算 |
| 迭代器支持 | 通常实现 `input_iterator` | 无（不支持迭代） |

Generator 是**拉取模型**（pull model）：调用者主动请求下一个值，协程在产出值后挂起等待下一次请求。Task 是**推送模型**（push model）：Task 在内部等待异步操作完成后自行恢复，最终将结果推送给等待者。

### 1.3 惰性求值

Generator 的核心优势是**惰性求值**（lazy evaluation）：值在需要时才被计算，而非一次性全部生成。

```cpp
// 急切求值：一次性分配全部内存
auto eager_squares(int n) -> std::vector<int> {
    std::vector<int> v(n);
    for (int i = 0; i < n; ++i) v[i] = i * i;
    return v;
}

// 惰性求值：每次只计算一个值，无需分配大数组
auto lazy_squares(int n) -> generator<int> {
    for (int i = 0; i < n; ++i)
        co_yield i * i;
}
```

惰性求值的优势：
- **内存效率**：不需要一次性存储整个序列，适合处理大型或无限序列
- **计算效率**：如果调用者提前终止消费，后续值根本不会被计算
- **组合性**：可以像 Unix 管道一样串联多个 Generator 变换

### 1.4 std::generator\<T\>（C++23）

C++23 标准库引入了 `std::generator<T>`，定义在 `<generator>` 头文件中。它是最简单的 Generator 类型：

```cpp
#include <generator>

std::generator<int> fib(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;
        auto next = a + b;
        a = b;
        b = next;
    }
}

// 使用
for (int x : fib(10))
    std::cout << x << ' ';  // 0 1 1 2 3 5 8 13 21 34
```

> [!warning] 编译器支持
> `std::generator` 需要较新的编译器版本：GCC 14+、Clang 19+（部分支持）、MSVC 19.38+（VS 17.8+）。如果你的编译器尚不支持，请使用本节中自定义 Generator 实现，或 [[05-coroutines-co-await|cppcoro 库]] 的 `cppcoro::generator<T>`。

## 二、代码示例

### 2.1 自定义 Generator 骨架

在深入示例之前，先给出一个最小可用的自定义 `generator<T>` 实现。理解这个骨架是掌握 Generator 模式的关键。

```cpp
#include <coroutine>
#include <exception>
#include <iterator>
#include <utility>

template <typename T>
struct generator {
    struct promise_type {
        T current_value;

        auto get_return_object() -> generator {
            return generator{
                std::coroutine_handle<promise_type>::from_promise(*this)};
        }

        auto initial_suspend() -> std::suspend_always { return {}; }
        auto final_suspend() noexcept -> std::suspend_always { return {}; }
        void unhandled_exception() { std::terminate(); }

        auto yield_value(T value) -> std::suspend_always {
            current_value = std::move(value);
            return {};
        }

        void return_void() {}
    };

    using handle_type = std::coroutine_handle<promise_type>;

    explicit generator(handle_type h) : coro_(h) {}

    generator(generator&& other) noexcept : coro_(std::exchange(other.coro_, nullptr)) {}

    generator(const generator&) = delete;
    auto operator=(const generator&) -> generator& = delete;

    ~generator() {
        if (coro_) coro_.destroy();
    }

    generator& operator=(generator&& other) noexcept {
        if (this != &other) {
            if (coro_) coro_.destroy();
            coro_ = std::exchange(other.coro_, nullptr);
        }
        return *this;
    }

    struct iterator {
        handle_type coro_;

        using value_type = T;
        using difference_type = std::ptrdiff_t;

        auto operator++() -> iterator& {
            coro_.resume();
            if (coro_.done()) coro_ = nullptr;
            return *this;
        }

        auto operator*() const -> const T& { return coro_.promise().current_value; }
        auto operator==(std::default_sentinel_t) const -> bool { return coro_ == nullptr; }
    };

    auto begin() -> iterator {
        if (coro_) coro_.resume();
        if (coro_ && coro_.done()) coro_ = nullptr;
        return iterator{coro_};
    }

    auto end() -> std::default_sentinel_t { return {}; }

private:
    handle_type coro_;
};
```

编译与使用：
```bash
g++ -std=c++20 -fcoroutines -O2 example.cpp -o example
```
预期输出：依赖具体协程的 `co_yield` 序列。

> [!note] 关键设计要点
> - `initial_suspend()` 返回 `suspend_always`：协程启动后立即挂起，由 `begin()` 手动恢复，实现惰性启动
> - `final_suspend()` 返回 `suspend_always`：协程结束后挂起，允许 `iterator` 读取 `done()` 状态
> - `yield_value()` 将值存入 `promise`，调用者通过迭代器读取
> - 析构函数 `destroy()` 协程帧：确保协程资源被正确释放
> - `iterator::operator++()` 恢复协程执行到下一个 `co_yield` 点

### 2.2 斐波那契数列生成器

```cpp
#include "generator.h"  // 使用 2.1 节的自定义 generator<T>
#include <iostream>

generator<int> fibonacci(int limit) {
    int a = 0, b = 1;
    while (a <= limit) {
        co_yield a;
        auto next = a + b;
        a = b;
        b = next;
    }
}

int main() {
    std::cout << "斐波那契数列 (<= 100):\n";
    for (int x : fibonacci(100)) {
        std::cout << x << ' ';
    }
    std::cout << '\n';
}
```

编译与运行：
```bash
g++ -std=c++20 -fcoroutines -O2 fib_generator.cpp -o fib_generator
./fib_generator
```

预期输出：
```text
斐波那契数列 (<= 100):
0 1 1 2 3 5 8 13 21 34 55 89
```

> [!tip] 如何验证惰性求值？
> 在 `co_yield` 前后加 `std::cout` 打印，或在 `for` 循环中提前 `break`，观察后面的值是否未被计算。

### 2.3 无限序列生成器（iota）

Generator 天然支持无限序列——因为值只在被消费时才计算，不产生无限的内存开销。

```cpp
#include "generator.h"
#include <iostream>

// 生成从 start 开始的无限递增序列
generator<int> iota(int start = 0) {
    while (true) {
        co_yield start++;
    }
}

int main() {
    std::cout << "无限序列 iota(10) 的前 15 个值:\n";
    int count = 0;
    for (int x : iota(10)) {
        std::cout << x << ' ';
        if (++count == 15) break;  // 提前终止——剩余值不会被计算
    }
    std::cout << '\n';
}
```

编译与运行：
```bash
g++ -std=c++20 -fcoroutines -O2 iota_generator.cpp -o iota_generator
./iota_generator
```

预期输出：
```text
无限序列 iota(10) 的前 15 个值:
10 11 12 13 14 15 16 17 18 19 20 21 22 23 24
```

> [!note] 无限序列终止
> Generator 不会因为序列无限而"失控"——调用者通过 `break` 或只取前 N 个值来终止消费。注意协程帧在 Generator 析构时被销毁，因此 `break` 后协程不会继续执行。

### 2.4 从容器/范围生成值

```cpp
#include "generator.h"
#include <iostream>
#include <vector>
#include <string>

template <std::ranges::input_range R>
generator<std::ranges::range_value_t<R>> from_range(R&& range) {
    for (auto&& elem : range) {
        co_yield std::forward<decltype(elem)>(elem);
    }
}

int main() {
    std::vector<std::string> words = {"hello", "world", "coroutine", "generator"};

    std::cout << "从 vector 生成:\n";
    for (const auto& w : from_range(words)) {
        std::cout << w << ' ';
    }
    std::cout << '\n';

    // 也支持临时容器——但需注意临时对象的生命周期
    std::cout << "从临时 initializer_list:\n";
    for (int x : from_range(std::vector{1, 4, 9, 16, 25})) {
        std::cout << x << ' ';
    }
    std::cout << '\n';
}
```

编译与运行：
```bash
g++ -std=c++20 -fcoroutines -O2 range_generator.cpp -o range_generator
./range_generator
```

预期输出：
```text
从 vector 生成:
hello world coroutine generator
从临时 initializer_list:
1 4 9 16 25
```

> [!warning] 悬垂引用陷阱
> `from_range(std::vector{1, 4, 9})` 中，临时 `std::vector` 的生命周期延长到完整表达式结束。由于 `for` 循环在同一个完整表达式中消费 Generator，这恰好是安全的。但如果你先将 Generator 存储到变量再迭代，则会悬垂——详见 [[#4.3 悬垂引用产出|常见陷阱 4.3]]。

### 2.5 递归树遍历生成器

Generator 可以在递归函数中使用，非常适合遍历树形结构。

```cpp
#include "generator.h"
#include <iostream>
#include <memory>
#include <vector>

struct TreeNode {
    int value;
    std::vector<std::unique_ptr<TreeNode>> children;

    explicit TreeNode(int v) : value(v) {}
    void add_child(int v) { children.push_back(std::make_unique<TreeNode>(v)); }
};

// 前序遍历树
generator<int> preorder_traverse(const TreeNode* node) {
    if (!node) co_return;

    co_yield node->value;

    for (const auto& child : node->children) {
        // 关键：递归 Generator 不能直接在 for 循环中使用
        // 需要手动迭代子 Generator
        auto sub_gen = preorder_traverse(child.get());
        for (int val : sub_gen) {
            co_yield val;
        }
    }
}

int main() {
    // 构建树：
    //       1
    //     / | \
    //    2  3  4
    //   / \    |
    //  5   6   7
    auto root = std::make_unique<TreeNode>(1);
    root->add_child(2);
    root->add_child(3);
    root->add_child(4);
    root->children[0]->add_child(5);
    root->children[0]->add_child(6);
    root->children[2]->add_child(7);

    std::cout << "前序遍历: ";
    for (int x : preorder_traverse(root.get())) {
        std::cout << x << ' ';
    }
    std::cout << '\n';
}
```

编译与运行：
```bash
g++ -std=c++20 -fcoroutines -O2 tree_generator.cpp -o tree_generator
./tree_generator
```

预期输出：
```text
前序遍历: 1 2 5 6 3 4 7
```

> [!important] 递归 Generator 的性能注意
> 上面的实现中，每次递归调用都创建了一个新的 `generator` 对象及其协程帧。对于深层树，这会累积大量堆分配。在 C++23 中，`std::generator` 支持 `generator<T>::recursive_reference` 机制（通过 `yield_value` 重载），允许子 Generator 直接"委托"产出，避免嵌套迭代的开销。如果你的编译器支持 C++23，请优先使用该特性。

### 2.6 使用 C++23 std::generator\<T\>

```cpp
// 需要 GCC 14+ / MSVC 19.38+ / Clang 19+
#include <generator>
#include <iostream>
#include <vector>
#include <ranges>

std::generator<int> even_numbers(int up_to) {
    for (int i = 0; i <= up_to; i += 2) {
        co_yield i;
    }
}

// 结合 ranges::views 使用
std::generator<int> doubled(std::generator<int> source) {
    for (int x : source) {
        co_yield x * 2;
    }
}

int main() {
    std::cout << "0-10 的偶数: ";
    for (int x : even_numbers(10)) {
        std::cout << x << ' ';
    }
    std::cout << '\n';

    std::cout << "偶数加倍: ";
    for (int x : doubled(even_numbers(5))) {
        std::cout << x << ' ';
    }
    std::cout << '\n';
}
```

编译与运行：
```bash
# GCC 14+
g++ -std=c++23 -O2 std_generator.cpp -o std_generator
./std_generator
```

预期输出：
```text
0-10 的偶数: 0 2 4 6 8 10
偶数加倍: 0 4 8 12 16 20
```

> [!note] std::generator 与 ranges 的关系
> `std::generator<T>` 满足 `std::ranges::input_range` concept，因此可以直接与 `<ranges>` 中的视图（views）和适配器组合使用。但注意 Generator 是 input range（只能遍历一次），不是 forward range。

## 三、练习

### 3.1 入门：素数生成器

**目标**：实现一个 Generator，按需生成素数序列。

**要求**：
- 函数签名 `generator<int> primes(int up_to)`
- 使用简单的试除法判断素数（对 `2` 到 `sqrt(n)` 检查）
- 支持提前终止：调用者可以随时停止消费

**测试场景**：

```cpp
// 生成 100 以内的素数
for (int p : primes(100)) {
    std::cout << p << ' ';
}
// 预期输出: 2 3 5 7 11 13 17 19 23 29 31 37 41 43 47 53 59 61 67 71 73 79 83 89 97
```

**编译**：
```bash
g++ -std=c++20 -fcoroutines -O2 prime_exercise.cpp -o prime_exercise
./prime_exercise
```

> [!tip]- 参考思路
> 1. 特判 `2`（唯一的偶素数）
> 2. 从 `3` 开始只检查奇数
> 3. 试除因子只需检查奇数 `<= sqrt(n)`
> 4. 使用 `static` 变量或闭包可以缓存已找到的素数，加速后续判断

### 3.2 进阶：递归扁平化嵌套容器

**目标**：实现一个递归 Generator，将任意嵌套的 `std::vector<std::vector<...<int>...>>` 扁平化为单层序列。

**要求**：
- 使用 `co_yield` 产出每个元素
- 支持任意深度的嵌套（使用递归）
- 对非嵌套的元素直接产出，对嵌套的 `std::vector<int>` 递归展开

**测试场景**：

```cpp
std::vector<std::any> nested = {
    std::any(1),
    std::any(std::vector<std::any>{
        std::any(2),
        std::any(std::vector<std::any>{
            std::any(3), std::any(4)
        }),
        std::any(5)
    }),
    std::any(6)
};

for (int x : flatten(nested)) {
    std::cout << x << ' ';
}
// 预期输出: 1 2 3 4 5 6
```

**编译**：
```bash
g++ -std=c++20 -fcoroutines -O2 flatten_exercise.cpp -o flatten_exercise
./flatten_exercise
```

> [!tip]- 参考思路
> 方案 A：使用 `std::any` + `std::any_cast` 判断元素是 `int` 还是 `std::vector<std::any>`，分别处理
> 方案 B：使用 `std::variant<int, std::vector<...>>` 替代 `std::any`，类型更安全
> 方案 C：使用重载 + 模板递归展开（最优雅但模板元编程代价高）

### 3.3 挑战：实现 range-adaptor 风格的管道

**目标**：实现一个类似 `std::views::filter` 和 `std::views::transform` 的 Generator 管道。

**要求**：
- 实现 `generator<T> filter(auto gen, auto pred)`：只产出满足谓词的元素
- 实现 `generator<U> transform(auto gen, auto fn)`：对每个元素应用变换函数后产出
- 支持链式调用（管道风格）

**测试场景**：

```cpp
auto gen = iota(1);  // 无限序列 1, 2, 3, ...
auto even_squares = transform(
    filter(std::move(gen), [](int x) { return x % 2 == 0; }),
    [](int x) { return x * x; }
);

int count = 0;
for (int x : even_squares) {
    std::cout << x << ' ';
    if (++count == 5) break;
}
// 预期输出: 4 16 36 64 100
//      (即 2²=4, 4²=16, 6²=36, 8²=64, 10²=100)
```

**编译**：
```bash
g++ -std=c++20 -fcoroutines -O2 pipeline_exercise.cpp -o pipeline_exercise
./pipeline_exercise
```

> [!tip]- 参考思路
> 1. `filter` 内部消费源 Generator，对满足谓词的值 `co_yield`，不满足则跳过
> 2. `transform` 内部消费源 Generator，对每个值应用函数后 `co_yield`
> 3. 注意 `std::move(gen)` 的必要性——Generator 是 move-only 类型
> 4. 进阶：考虑使用 `operator|` 重载实现更自然的管道语法

## 四、常见陷阱

### 4.1 协程帧未销毁导致资源泄漏

```cpp
// 错误
auto get_values() -> generator<int> {
    for (int i = 0; i < 5; ++i)
        co_yield i;
}

int main() {
    auto g = get_values();
    // 只取前 2 个值，然后丢弃 g
    auto it = g.begin();
    std::cout << *it << '\n';  // 0
    ++it;
    std::cout << *it << '\n';  // 1
    // 没有 ++it 到结束，协程帧是否被销毁？
    return 0;  // ✅ g 的析构函数会调用 coro_.destroy()，帧被正确销毁
}
```

> [!warning] 关键点
> 协程帧的生命周期绑定到 `generator` 对象的生命周期。只要自定义 `generator<T>` 的析构函数正确调用了 `coro_.destroy()`（如 [[#2.1 自定义 Generator 骨架|2.1 节]] 所示），在 `generator` 对象离开作用域时帧就会被销毁，即使没有遍历完所有值。**但如果你手动操作 `coroutine_handle` 而没有在析构时销毁，则会导致帧泄漏。**

```cpp
// 危险：手动 handle 未销毁
auto h = get_values_coro_handle();  // 返回 std::coroutine_handle<>
h.resume();  // 获取第一个值
// 忘记调用 h.destroy() —— 协程帧泄漏！
```

### 4.2 访问已移动的 Generator

Generator 通常是 move-only 类型（因为协程句柄独占所有权）。

```cpp
// 错误
generator<int> g = fibonacci(50);
auto g2 = std::move(g);

// g 已处于"空"状态（coro_ == nullptr）
for (int x : g) {   // ❌ 未定义行为：g 的 coro_ 已被移走
    std::cout << x;
}

for (int x : g2) {  // ✅ 正确：使用移动后的 g2
    std::cout << x;
}
```

> [!important] 防御措施
> 在 `begin()` 中检查 `coro_` 是否为空：
> ```cpp
> auto begin() -> iterator {
>     if (!coro_) return iterator{nullptr};  // 空 Generator → 空迭代器
>     if (coro_.done()) { coro_.destroy(); coro_ = nullptr; return iterator{nullptr}; }
>     coro_.resume();
>     if (coro_.done()) { coro_.destroy(); coro_ = nullptr; return iterator{nullptr}; }
>     return iterator{coro_};
> }
> ```

### 4.3 悬垂引用产出

这是 Generator 中最危险的陷阱之一。当你 `co_yield` 一个引用时，必须确保被引用对象的生命周期覆盖整个消费过程。

```cpp
// 错误：co_yield 引用到局部变量
generator<const std::string&> bad_generator(const std::vector<std::string>& vec) {
    for (const auto& s : vec) {
        std::string upper = s;
        // 将 upper 转为大写...
        co_yield upper;  // ❌ upper 在下一个 co_yield 时被销毁！
    }
}

// 正确：co_yield 值类型（拷贝）
generator<std::string> good_generator(const std::vector<std::string>& vec) {
    for (const auto& s : vec) {
        std::string upper = s;
        co_yield upper;  // ✅ upper 被移动/拷贝到 promise 中
    }
}
```

另一个常见场景——引用传入的临时对象：

```cpp
// 错误
generator<const int&> ref_from_temp() {
    auto vec = std::vector{1, 2, 3};  // 局部变量
    for (const auto& x : vec) {
        co_yield x;  // ❌ 协程挂起期间 vec 不会被销毁...
    }                 // 但 vec 在协程结束后被销毁，如果还有引用则悬垂
}

// 更隐蔽的错误
generator<const int&> from_vec(const std::vector<int>& vec) {
    for (const auto& x : vec) {
        co_yield x;  // 调用者传入的是一个临时 vector 吗？
    }
}

// 调用侧
for (int x : from_vec(std::vector{1, 2, 3})) {  // ❌ 临时 vector 已销毁！
    std::cout << x;  // 悬垂引用
}
```

> [!danger] 防御原则
> 1. **默认使用值类型**产出（`generator<T>` 而非 `generator<const T&>`）
> 2. 如果确实需要产出引用，确保所有者的生命周期严格包含消费循环
> 3. 使用 `std::generator<T>` 时注意：它不支持产出引用（`generator<const T&>` 在某些实现中不可用）
> 4. 传引用参数给协程时，在文档中明确标注生命周期要求

### 4.4 混用 co_yield 和 co_return

```cpp
// 错误：意图不明
generator<int> confused() {
    co_yield 1;
    co_yield 2;
    co_return 42;  // ❌ Generator 不支持 return_value，只支持 return_void
}

// 编译器报错：
// error: no member named 'return_value' in 'promise_type'
```

> [!note] 规则
> Generator 的 `promise_type` 应只提供 `return_void()`，不提供 `return_value()`。如果你需要同时产出序列和返回最终值，那不是 Generator —— 考虑设计成 Task 返回 `std::vector<T>`，或使用 [[#2.4 从容器/范围生成值|from_range]] 模式。

如果需要传递"最终统计信息"，可以这样做：

```cpp
generator<int> with_stats(int& out_count) {
    int i = 0;
    while (i < 10) {
        co_yield i++;
    }
    out_count = i;  // 通过引用参数传出
}

int count;
for (int x : with_stats(count)) {
    std::cout << x << ' ';
}
std::cout << "\n共产出 " << count << " 个值\n";
```

### 4.5 忘记检查 Generator 是否还有值

```cpp
// 错误：假设 Generator 至少有一个值
auto it = some_generator().begin();
auto first = *it;  // ❌ 如果 Generator 为空，解引用空句柄 → 未定义行为
```

正确做法：

```cpp
auto g = some_conditionally_empty_generator();
for (int x : g) {       // ✅ range-for 正确处理空范围
    std::cout << x;
}
// 或
auto it = g.begin();
if (it != g.end()) {    // ✅ 先检查
    auto first = *it;
}
```

### 4.6 final_suspend 返回 suspend_never 导致的陷阱

如果 `final_suspend()` 返回 `std::suspend_never`：

```cpp
struct promise_type {
    // ...
    auto final_suspend() noexcept -> std::suspend_never { return {}; }
    // 危险！协程在 co_return 后立即销毁自己的帧
};
```

这会导致协程帧在 `co_return` 后立即被销毁。如果 `iterator` 还持有 `coroutine_handle`，调用 `done()` 或访问 `promise().current_value` 都是访问已释放的内存。**Generator 的 `final_suspend` 几乎总是应该返回 `suspend_always`**，以便调用者检查 `done()` 状态后再销毁帧。

## 五、扩展阅读

### C++ 标准与参考

- [cppreference: Coroutines — co_yield](https://en.cppreference.com/w/cpp/language/coroutines) — `co_yield` 的语言规范
- [cppreference: std::generator (C++23)](https://en.cppreference.com/w/cpp/coroutine/generator) — 标准库 Generator 文档
- [P2502R2: `std::generator` — synchronous coroutine generator for ranges](https://wg21.link/P2502R2) — `std::generator` 的设计提案

### 深入文章

- [Lewis Baker: C++ Coroutines — Understanding operator co_await](https://lewissbaker.github.io/2017/11/17/understanding-operator-co-await) — `co_await` / `co_yield` 的底层变换
- [Lewis Baker: C++ Coroutines — Understanding the promise type](https://lewissbaker.github.io/2018/09/05/understanding-the-promise-type) — `promise_type` 的完整机制
- [Barry Revzin: An Overview of Standard Ranges](https://brevzin.github.io/c++/2023/04/03/an-overview-of-standard-ranges/) — Ranges 与 Generator 的关系
- [Raymond Chen: The many ways to kill a coroutine](https://devblogs.microsoft.com/oldnewthing/20210504-00/?p=105173) — 协程生命周期管理

### 视频

- **CppCon 2022: C++20's \[\[nodiscard\]\] Coroutines** — Arthur O'Dwyer — 协程设计模式与陷阱
- **CppCon 2022: Lightning Talk: Generator Coroutines** — 快速了解 Generator

### 库与实现参考

- [cppcoro::generator](https://github.com/lewissbaker/cppcoro) — 教学级参考实现
- [NVIDIA stdexec](https://github.com/NVIDIA/stdexec) — `std::execution` 参考实现中的 Generator
- [range-v3](https://github.com/ericniebler/range-v3) — Ranges 库，展示了 Generator 在惰性管道中的完整应用

### 前置与后续

- 前置：[[06-coroutines-promise-type|协程 Part 2：promise_type 深入]] — 理解 `promise_type` 是编写自定义 Generator 的前提
- 后续：[[10-asio-coroutines|Boost.Asio Part 2：协程集成]] — 将协程技能应用到异步 I/O
- 相关：[[05-coroutines-co-await|协程 Part 1：co_await 与 Awaitable]] — `co_yield` 的底层依赖
- 相关：[[07-coroutines-task-type|协程 Part 3：编写 Task 类型]] — Task 是 Generator 的"单次产出"对应物
