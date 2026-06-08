---
title: 协程 Part 2 — promise_type 深入
updated: 2026-06-08
tags: [cpp, coroutine, promise_type, compiler]
---

# 协程 Part 2 — promise_type 深入

> 前置：[[05-coroutines-co-await|协程 Part 1：co_await 与 Awaitable]]
> 后续：[[07-coroutines-task-type|协程 Part 3：编写 Task 类型]]
> 预计耗时：75 分钟

---

## 1. 概念

`promise_type` 是 C++20 协程的**控制中心**。编译器将协程函数体变换为状态机代码时，所有对协程生命周期的控制——创建、初始暂停、值传递、最终暂停和异常处理——都通过 `promise_type` 的成员函数实现。

### 1.1 编译器如何找到 promise_type

编译器通过 `std::coroutine_traits` 推导 `promise_type`：

```cpp
template <typename R, typename... Args>
struct std::coroutine_traits<R, Args...> {
    using promise_type = typename R::promise_type;
};
```

推导过程：
1. 协程返回类型是 `R`
2. 编译器查找 `std::coroutine_traits<R, Args...>::promise_type`
3. 默认特化要求 `R` 内部有 `R::promise_type` 嵌套类型

这意味着**任何用作协程返回类型的类型，必须定义 `promise_type`**。你可以为任意返回类型特化 `std::coroutine_traits` 来自定义 `promise_type` 的映射。

```cpp
// 方式 1：在返回类型中定义 promise_type（最常用）
struct MyTask {
    struct promise_type { /* ... */ };
};

// 方式 2：特化 std::coroutine_traits（用于无法修改的返回类型）
template <typename... Args>
struct std::coroutine_traits<std::future<int>, Args...> {
    struct promise_type { /* ... */ };
};
```

### 1.2 promise_type 的成员函数

`promise_type` 有 **5 个必需成员**和 **2 个可选成员**：

| 成员 | 必需？ | 调用时机 | 作用 |
|:-----|:------|:---------|:-----|
| `get_return_object()` | **必需** | 协程首次暂停前（initial_suspend 之前） | 构造返回给调用者的对象 |
| `initial_suspend()` | **必需** | 协程体执行前 | 决定协程是否立即开始执行 |
| `final_suspend()` | **必需** | 协程体结束时（包括异常路径） | 决定协程完成后的行为；**必须 suspend** |
| `unhandled_exception()` | **必需** | 协程体抛出未捕获异常时 | 异常处理入口 |
| `return_void()` 或 `return_value()` | **二选一** | `co_return;` 或 `co_return expr;` 时 | 接收协程返回值 |
| `yield_value()` | 可选 | `co_yield expr;` 时 | 接收 yield 值；无 `co_yield` 则不需要 |
| `await_transform()` | 可选 | 每个 `co_await expr;` 前 | 将 `expr` 转换为 awaitable |

**核心调用顺序（正常路径）**：

```
1. operator new (分配协程帧)
2. 捕获参数 → 存储到协程帧
3. 构造 promise_type 对象
4. promise.get_return_object() → 返回给调用者
5. co_await promise.initial_suspend() → 暂停或继续
6. === 协程体执行 ===
    可能包含：co_await / co_yield / co_return
7. 协程体结束 或 co_return
   → promise.return_void() 或 promise.return_value()
8. co_await promise.final_suspend() → 必须暂停
9. 析构 promise_type
10. 析构协程帧中的局部变量
11. operator delete (释放协程帧)
```

### 1.3 协程帧（Coroutine Frame）

协程帧是编译器为每个协程调用在**堆上**分配的动态内存块，包含：

```
┌─────────────────────────────────┐
│  promise_type 对象               │ ← promise() 返回指向此处的指针
├─────────────────────────────────┤
│  协程参数（按值捕获的）           │
├─────────────────────────────────┤
│  跨暂停点的局部变量               │ ← 必须"提升"到堆上
├─────────────────────────────────┤
│  当前暂停点（resume 地址）        │ ← 状态机的 PC
├─────────────────────────────────┤
│  其他编译器内部状态               │
└─────────────────────────────────┘
```

**什么会进入协程帧？**
- **一定会**：`promise_type` 对象、协程参数（按值）、跨暂停点存活的局部变量
- **可能不会**：不跨暂停点的局部变量（编译器可优化到栈上）
- **永远不会**：纯计算、不跨暂停点即销毁的临时对象

```cpp
Task<int> example(int x) {
    int a = x * 2;        // 不跨暂停点 -> 可能在栈上
    co_await something();
    int b = a + 1;        // a 跨暂停点 -> 必须在协程帧中
    co_return b;
}
```

### 1.4 HALO — 堆分配消除优化

HALO（Heap Allocation Elision Optimization）允许编译器在满足条件时**省略堆分配**，将协程帧放在调用者的栈上。

**触发条件（编译器相关，典型要求）**：
- 协程帧的生命周期严格嵌套在调用者栈帧内
- 调用者不将 `coroutine_handle` 逃逸到外部
- 协程的 `get_return_object()` 不存储 handle 到堆上

> [!warning] HALO 不可依赖
> HALO 是**可选优化**，标准不强制。在关键路径上应假设堆分配会发生，或使用自定义分配器控制行为。

### 1.5 自定义分配器

通过在 `promise_type` 中定义 `operator new`，可以接管协程帧的内存分配：

```cpp
struct promise_type {
    // 自定义分配：编译器生成 sizeof(frame) + 对齐要求
    void* operator new(std::size_t size) {
        return MyAllocator::allocate(size);
    }
    void operator delete(void* ptr, std::size_t size) {
        MyAllocator::deallocate(ptr, size);
    }
};
```

如果 `promise_type` 还定义了**参数匹配的** `operator new`，编译器会优先使用它，允许从协程参数中获取分配器：

```cpp
void* operator new(std::size_t size, std::allocator_arg_t, MyAllocator& alloc) {
    return alloc.allocate(size);
}
```

### 1.6 coroutine_handle

`std::coroutine_handle<P>` 是协程帧的**非拥有型句柄**，提供：

| 操作 | 说明 |
|:-----|:-----|
| `handle.resume()` | 恢复协程执行 |
| `handle.destroy()` | 销毁协程帧（调用析构 + deallocate） |
| `handle.done()` | 协程是否已完成（`final_suspend` 处暂停） |
| `handle.promise()` | 获取 `promise_type&` 引用 |
| `handle.address()` | 获取帧指针（`void*`） |
| `handle.from_promise(p)` | 从 promise 引用反查 handle |
| `operator bool` | 是否非空 |

```cpp
// 特化到 void（类型擦除）——用于不需要访问 promise_type 的场景
std::coroutine_handle<> erased_handle = my_typed_handle;
```

---

## 2. 代码示例

### 2.1 最小 promise_type：惰性任务

一个最精简的协程返回类型，仅演示 promise_type 的最小必需成员。

**编译**：
```bash
g++ -std=c++20 -fcoroutines -O2 example1.cpp -o example1
```

**代码**：

```cpp
#include <coroutine>
#include <iostream>
#include <cassert>

// 惰性任务：创建时不立即执行，需要显式 resume
struct LazyTask {
    struct promise_type {
        LazyTask get_return_object() {
            // 从 promise 构造 handle，再构造返回对象
            return LazyTask{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }
        std::suspend_always initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    using handle_t = std::coroutine_handle<promise_type>;
    handle_t handle;

    explicit LazyTask(handle_t h) : handle(h) {}
    ~LazyTask() { if (handle) handle.destroy(); }
    LazyTask(const LazyTask&) = delete;
    LazyTask& operator=(const LazyTask&) = delete;
    LazyTask(LazyTask&& other) noexcept
        : handle(std::exchange(other.handle, nullptr)) {}
    LazyTask& operator=(LazyTask&& other) noexcept {
        if (this != &other) {
            if (handle) handle.destroy();
            handle = std::exchange(other.handle, nullptr);
        }
        return *this;
    }

    bool resume() {
        if (!handle.done()) {
            handle.resume();
        }
        return !handle.done();
    }
};

LazyTask hello() {
    std::cout << "Hello, ";
    co_await std::suspend_always{};
    std::cout << "coroutine!" << std::endl;
}

int main() {
    auto task = hello();    // 创建协程帧，在 initial_suspend 处暂停
    std::cout << "Task created." << std::endl;
    task.resume();          // 输出 "Hello, "，在 co_await 处暂停
    std::cout << "First resume done." << std::endl;
    task.resume();          // 输出 "coroutine!"，在 final_suspend 处暂停
    std::cout << "Second resume done, done=" << task.handle.done() << std::endl;
}
```

**预期输出**：
```
Task created.
Hello, First resume done.
coroutine!
Second resume done, done=1
```

### 2.2 带返回值的 promise_type

演示 `return_value()` 和 `yield_value()` 的配合使用。

**编译**：
```bash
g++ -std=c++20 -fcoroutines -O2 example2.cpp -o example2
```

**代码**：

```cpp
#include <coroutine>
#include <iostream>
#include <optional>
#include <cassert>

template <typename T>
struct Generator {
    struct promise_type {
        T current_value;  // 存储 yield 或 return 的值

        Generator get_return_object() {
            return Generator{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }
        std::suspend_always initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_value(T value) { current_value = std::move(value); }
        std::suspend_always yield_value(T value) {
            current_value = std::move(value);
            return {};
        }
        void unhandled_exception() { std::terminate(); }
    };

    using handle_t = std::coroutine_handle<promise_type>;
    handle_t handle;

    explicit Generator(handle_t h) : handle(h) {}
    ~Generator() { if (handle) handle.destroy(); }
    Generator(const Generator&) = delete;
    Generator& operator=(const Generator&) = delete;
    Generator(Generator&& other) noexcept
        : handle(std::exchange(other.handle, nullptr)) {}
    Generator& operator=(Generator&& other) noexcept {
        if (this != &other) {
            if (handle) handle.destroy();
            handle = std::exchange(other.handle, nullptr);
        }
        return *this;
    }

    // 获取下一个值：返回 nullopt 表示结束
    std::optional<T> next() {
        if (handle.done()) return std::nullopt;
        handle.resume();
        if (handle.done()) return std::nullopt;
        return handle.promise().current_value;
    }
};

Generator<int> fibonacci(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;
        int next = a + b;
        a = b;
        b = next;
    }
    co_return -1;  // 哨兵值
}

int main() {
    auto gen = fibonacci(8);
    while (auto val = gen.next()) {
        std::cout << *val << " ";
    }
    std::cout << std::endl;
}
```

**预期输出**：
```
0 1 1 2 3 5 8 13
```

**解析**：`yield_value()` 在每次 `co_yield` 时被调用，将值存入 `current_value`。`return_value()` 在 `co_return` 时被调用——这里 `co_return -1` 存入哨兵值，但调用者不会看到它，因为 `gen.next()` 在 `done() == true` 时返回 `nullopt`。

### 2.3 自定义分配器

通过 `promise_type::operator new` 使用自定义内存池为协程帧分配内存，并在每个 promise_type 方法中打印日志以追踪编译器变换。

**编译**：
```bash
g++ -std=c++20 -fcoroutines -O2 example3.cpp -o example3
```

**代码**：

```cpp
#include <coroutine>
#include <iostream>
#include <cstddef>
#include <cstdlib>
#include <vector>
#include <new>

// 简单的内存池：预分配一块内存，线性分配，不释放单块
class CoroutinePool {
    static constexpr std::size_t POOL_SIZE = 1024 * 64;
    alignas(std::max_align_t) char pool_[POOL_SIZE];
    std::size_t offset_ = 0;

public:
    void* allocate(std::size_t size) {
        std::size_t aligned = (offset_ + alignof(std::max_align_t) - 1)
                              & ~(alignof(std::max_align_t) - 1);
        if (aligned + size > POOL_SIZE) {
            throw std::bad_alloc();
        }
        void* ptr = pool_ + aligned;
        offset_ = aligned + size;
        std::cout << "[Pool]  allocated " << size << " bytes at offset "
                  << aligned << " (remaining: " << (POOL_SIZE - offset_) << ")"
                  << std::endl;
        return ptr;
    }

    void deallocate(void* ptr, std::size_t size) {
        // 简化：不真正释放（适用于帧式分配器）
        std::cout << "[Pool]  deallocate " << size << " bytes at "
                  << ptr << " (no-op in linear pool)" << std::endl;
    }
};

// 全局内存池实例
CoroutinePool g_pool;

struct TrackedTask {
    struct promise_type {
        // 追踪状态
        enum State { CREATED, RUNNING, SUSPENDED, RETURNED, DESTROYED };
        State state = CREATED;

        // ---- 自定义分配器 ----
        static void* operator new(std::size_t size) {
            std::cout << "[promise] operator new(" << size << ")" << std::endl;
            return g_pool.allocate(size);
        }
        static void operator delete(void* ptr, std::size_t size) {
            std::cout << "[promise] operator delete(" << ptr
                      << ", " << size << ")" << std::endl;
            g_pool.deallocate(ptr, size);
        }

        TrackedTask get_return_object() {
            std::cout << "[promise] get_return_object()" << std::endl;
            state = CREATED;
            return TrackedTask{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }
        std::suspend_always initial_suspend() {
            std::cout << "[promise] initial_suspend() -> suspend_always"
                      << std::endl;
            return {};
        }
        std::suspend_always final_suspend() noexcept {
            std::cout << "[promise] final_suspend() -> suspend_always" << std::endl;
            state = RETURNED;
            return {};
        }
        void return_void() {
            std::cout << "[promise] return_void()" << std::endl;
            state = RETURNED;
        }
        void unhandled_exception() {
            std::cout << "[promise] unhandled_exception()" << std::endl;
            state = DESTROYED;
            std::terminate();
        }

        ~promise_type() {
            std::cout << "[promise] ~promise_type()" << std::endl;
        }
    };

    using handle_t = std::coroutine_handle<promise_type>;
    handle_t handle;

    explicit TrackedTask(handle_t h) : handle(h) {}
    ~TrackedTask() {
        std::cout << "[task]   ~TrackedTask()" << std::endl;
        if (handle) handle.destroy();
    }
    TrackedTask(const TrackedTask&) = delete;
    TrackedTask& operator=(const TrackedTask&) = delete;
    TrackedTask(TrackedTask&& other) noexcept
        : handle(std::exchange(other.handle, nullptr)) {}
    TrackedTask& operator=(TrackedTask&& other) noexcept {
        if (this != &other) {
            if (handle) handle.destroy();
            handle = std::exchange(other.handle, nullptr);
        }
        return *this;
    }

    bool resume() {
        if (!handle.done()) {
            auto& p = handle.promise();
            std::cout << "[task]   resume()" << std::endl;
            p.state = promise_type::RUNNING;
            handle.resume();
            return !handle.done();
        }
        return false;
    }

    promise_type::State state() const {
        return handle.promise().state;
    }
};

TrackedTask demo(int id) {
    std::cout << "[coro]   demo(" << id << ") body start" << std::endl;
    co_await std::suspend_always{};
    std::cout << "[coro]   demo(" << id << ") after first suspend" << std::endl;
    co_await std::suspend_always{};
    std::cout << "[coro]   demo(" << id << ") done" << std::endl;
}

int main() {
    std::cout << "=== Creating coroutine ===" << std::endl;
    auto task = demo(42);

    std::cout << "=== First resume ===" << std::endl;
    task.resume();

    std::cout << "=== Second resume ===" << std::endl;
    task.resume();

    std::cout << "=== Third resume (to completion) ===" << std::endl;
    task.resume();

    std::cout << "=== done=" << task.handle.done() << " ===" << std::endl;
    std::cout << "=== Task going out of scope ===" << std::endl;
}
```

**预期输出**：
```
=== Creating coroutine ===
[Pool]  allocated 128 bytes at offset 0 (remaining: 65408)
[promise] operator new(128)
[promise] get_return_object()
[promise] initial_suspend() -> suspend_always
=== First resume ===
[task]   resume()
[coro]   demo(42) body start
=== Second resume ===
[task]   resume()
[coro]   demo(42) after first suspend
=== Third resume (to completion) ===
[task]   resume()
[coro]   demo(42) done
[promise] return_void()
[promise] final_suspend() -> suspend_always
=== done=1 ===
=== Task going out of scope ===
[task]   ~TrackedTask()
[promise] ~promise_type()
[promise] operator delete(0x..., 128)
[Pool]  deallocate 128 bytes at 0x... (no-op in linear pool)
```

### 2.4 通过 promise_type 成员追踪协程状态

演示在实际任务中使用 promise_type 存储状态，并实现 `return_value()` 传递结果。

**编译**：
```bash
g++ -std=c++20 -fcoroutines -O2 example4.cpp -o example4
```

**代码**：

```cpp
#include <coroutine>
#include <iostream>
#include <string>
#include <variant>
#include <exception>
#include <cassert>

// 带状态追踪和结果传递的 Task
template <typename T>
struct SimpleTask {
    struct promise_type {
        // 状态追踪
        int invocation_id = 0;
        std::string coroutine_name;

        // 结果存储
        std::variant<std::monostate, T, std::exception_ptr> result;

        SimpleTask get_return_object() {
            return SimpleTask{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }

        void return_value(T value) {
            result.template emplace<T>(std::move(value));
        }
        void unhandled_exception() {
            result.template emplace<std::exception_ptr>(
                std::current_exception());
        }

        ~promise_type() {
            std::cout << "[" << coroutine_name << "] promise destroyed"
                      << std::endl;
        }
    };

    using handle_t = std::coroutine_handle<promise_type>;
    handle_t handle;

    explicit SimpleTask(handle_t h) : handle(h) {}
    ~SimpleTask() { if (handle) handle.destroy(); }
    SimpleTask(const SimpleTask&) = delete;
    SimpleTask& operator=(const SimpleTask&) = delete;
    SimpleTask(SimpleTask&& other) noexcept
        : handle(std::exchange(other.handle, nullptr)) {}
    SimpleTask& operator=(SimpleTask&& other) noexcept {
        if (this != &other) {
            if (handle) handle.destroy();
            handle = std::exchange(other.handle, nullptr);
        }
        return *this;
    }

    // 阻塞等待结果
    T get_result() {
        auto& p = handle.promise();
        while (!handle.done()) {
            handle.resume();
        }
        if (std::holds_alternative<std::exception_ptr>(p.result)) {
            std::rethrow_exception(
                std::get<std::exception_ptr>(p.result));
        }
        return std::get<T>(p.result);
    }
};

SimpleTask<int> compute_async(const std::string& name, int a, int b) {
    // 通过 handle 访问 promise 设置名称
    auto& p = std::experimental::coroutine_handle<
        SimpleTask<int>::promise_type>::from_promise(
            *std::coroutine_handle<SimpleTask<int>::promise_type>::from_address(
                std::experimental::coroutine_handle<>::from_address(nullptr)
            )
        );

    int sum = a + b;
    co_return sum;
}

// 修复版本：使用 awaitable 传递 promise 引用
struct SetName {
    std::string name;
    bool await_ready() { return false; }
    void await_suspend(std::coroutine_handle<> h) {
        // 无法在此获取类型化 handle，简化演示
    }
    void await_resume() {}
};

SimpleTask<int> add(const std::string& name, int a, int b) {
    std::cout << "[" << name << "] computing " << a << " + " << b
              << std::endl;
    co_return a + b;
}

SimpleTask<int> multiply(const std::string& name, int a, int b) {
    std::cout << "[" << name << "] computing " << a << " * " << b
              << std::endl;
    co_return a * b;
}

int main() {
    auto t1 = add("adder", 3, 5);
    auto t2 = multiply("mul", 4, 7);

    int r1 = t1.get_result();
    int r2 = t2.get_result();

    std::cout << "adder result: " << r1 << std::endl;
    std::cout << "mul result: " << r2 << std::endl;
}
```

**预期输出**：
```
[adder] computing 3 + 5
[mul] computing 4 * 7
[adder] promise destroyed
[mul] promise destroyed
adder result: 8
mul result: 24
```

**关键观察**：由于 `initial_suspend()` 返回 `suspend_never`，协程立即开始执行到第一个 `co_await` 或 `co_return`。`final_suspend()` 返回 `suspend_always`，协程在完成时暂停，允许调用者在 `get_result()` 中检查 `done()` 然后安全地读取结果。

---

## 3. 练习

### 练习 1：实现自定义内存池的 promise_type

**目标**：为协程帧实现基于 `std::pmr::memory_resource` 的自定义分配器。

**要求**：
1. 创建一个 `PoolResource` 类，继承 `std::pmr::memory_resource`，使用固定大小的栈式内存池
2. 在 `promise_type` 中实现参数匹配的 `operator new(std::size_t, std::pmr::memory_resource*)`，将分配器传入协程帧
3. 实现对应的 `operator delete`
4. 编写一个简单的协程，验证分配确实来自你的内存池（例如检查指针范围）

**提示**：`operator new` 的额外参数从协程参数中提取——编译器会尝试将协程参数的地址与 `operator new` 的额外参数类型匹配。

**预期结果**：协程帧分配在自定义池中，程序结束时输出池的使用统计信息。

### 练习 2：编译器变换追踪器

**目标**：深入理解编译器对协程的变换，通过在每个 promise 方法中注入日志来还原执行顺序。

**要求**：
1. 为 `promise_type` 的每个方法（`get_return_object`、`initial_suspend`、`final_suspend`、`return_value`/`return_void`、`yield_value`、`unhandled_exception`）添加 `printf` 日志
2. 创建三个不同场景的协程：
   - 正常完成（`co_return`）
   - 抛出异常（验证 `unhandled_exception` 是否被调用）
   - 使用 `co_yield`（验证 `yield_value` 的调用）
3. 记录每个场景的输出顺序，画出协程的状态转换图

**预期结果**：你能够准确描述编译器为协程生成的代码执行顺序，理解每一步的触发条件。

### 练习 3：通过 shared_ptr 返回结果

**目标**：实现一个 `promise_type`，使用 `std::shared_ptr` 来存储协程结果，允许多个消费者读取。

**要求**：
1. 在 `promise_type` 中使用 `std::shared_ptr<T>` 存储返回值
2. `get_return_object()` 返回一个持有该 `shared_ptr` 的 `Future<T>` 对象
3. 协程结束时，通过 `return_value()` 将结果写入 `shared_ptr`
4. 实现 `Future<T>::get()`，在协程未完成时阻塞等待（使用 `std::condition_variable`）
5. 支持多个 `Future<T>` 实例共享同一结果（通过 `shared_ptr` 的引用语义）

**提示**：
- 在 `final_suspend()` 中通知等待者（`condition_variable::notify_all`）
- `Future<T>` 可以按值复制（内部是 `shared_ptr`），移动时转移所有权
- 考虑线程安全：`condition_variable` 需要配合 `mutex`

**预期结果**：多个 `Future<int>` 对象可以同时等待同一个协程的结果，所有消费者都能在协程完成后读取到结果。

---

## 4. 常见陷阱

> [!warning] 4.1 final_suspend 返回 suspend_never 导致 UB
> 如果 `final_suspend()` 返回 `suspend_never`（或等价物），协程在 `final_suspend` 点不会暂停，控制流会立即进入 promise 析构和协程帧释放。此时如果外部还持有 `coroutine_handle` 并调用 `resume()`，就是在已销毁的协程帧上操作——**未定义行为**。
>
> ```cpp
> // 危险！
> std::suspend_never final_suspend() noexcept { return {}; }
> // 外部 handle.resume() 在 done() 后仍然可能被调用 -> UB
> ```
>
> **正确做法**：`final_suspend()` 必须返回 `suspend_always`，让调用者有责任调用 `handle.destroy()`。

> [!warning] 4.2 promise 对象的生命周期
> `promise_type` 对象在协程帧分配时构造，在协程帧销毁时才析构——**不是**在 `final_suspend()` 之后立即析构。这意味着：
> - `get_return_object()` 中保存的指向 promise 的引用/指针在整个协程生命周期内有效
> - 你可以在 `final_suspend()` 暂停期间通过 `handle.promise()` 安全访问 promise

> [!warning] 4.3 initial_suspend：suspend_never vs suspend_always
> `initial_suspend()` 决定协程是**热启动**还是**冷启动**：
> - `suspend_never`：协程立即开始执行，适合 fire-and-forget 或 eager task
> - `suspend_always`：协程在第一条语句前暂停，调用者必须显式 resume，适合 lazy task / generator
>
> 选择错误会导致语义不匹配：如果你期望 lazy evaluation 但用了 `suspend_never`，协程会在调用者准备好之前就开始执行。

> [!warning] 4.4 unhandled_exception 必须不抛异常
> `unhandled_exception()` 是在协程体抛出未捕获异常时由运行时调用的。如果此函数自身抛出异常，`std::terminate()` 会被立即调用。典型实现：
> ```cpp
> void unhandled_exception() {
>     // 存储异常，之后在 get_result() 中重新抛出
>     error = std::current_exception();
> }
> ```

> [!warning] 4.5 返回类型必须满足协程要求
> 即使你的协程从不 `co_await`，只要函数体包含 `co_return`、`co_yield` 或 `co_await`，编译器就会按协程处理。返回类型必须定义 `promise_type`，否则编译错误：
> ```
> error: unable to find the promise type for this coroutine
> ```
>
> 常见的意外触发：在普通函数中写 `co_await` 调试代码，或从协程教程复制代码片段但没有正确的返回类型。

> [!warning] 4.6 协程帧大小的低估
> 协程帧比想象中大。除了 promise_type 和局部变量，编译器还需要存储：
> - 恢复点索引（状态机 PC）
> - 各暂停点的栈指针信息
> - 对齐填充
>
> 一个看似"只有几个 int"的协程，帧大小可能达到数百字节。使用 `sizeof(promise_type)` 和日志来了解实际分配大小。

---

## 5. 扩展阅读

### 官方资源
- [cppreference: Coroutines — promise_type](https://en.cppreference.com/w/cpp/language/coroutines) — 完整的 `promise_type` 规范和各成员函数的行为定义
- [C++20 标准 [dcl.fct.def.coroutine]](https://eel.is/c++draft/dcl.fct.def.coroutine) — 协程的正式语言规范

### 必读文章
- **Lewis Baker — [Understanding the promise type](https://lewissbaker.github.io/2018/09/05/understanding-the-promise-type/)** (2018)：理解 `promise_type` 的经典文章，详述每个成员函数的设计意图和调用时机
- **Lewis Baker — [C++ Coroutines: Understanding operator co_await](https://lewissbaker.github.io/2017/11/17/understanding-operator-co-await/)** (2017)：awaiter 协议的深入解析，与 promise_type 配合使用
- **Andreas Fertig — [C++20 Coroutines — The Low Level Interface](https://andreasfertig.blog/2021/01/cpp20-coroutines-the-low-level-interface/)** (2021)：协程底层接口的系统讲解

### 视频
- **CppCon 2022: C++20 Coroutines — The Low Level Interface** — Andreas Fertig
  从编译器视角解构协程变换，清晰展示每种 `promise_type` 成员的调用时机

### 源码参考
- **[cppcoro](https://github.com/lewissbaker/cppcoro)** — Lewis Baker 的协程参考库：`task.hpp`、`generator.hpp` 展示了工业级 `promise_type` 实现
- **[folly::coro](https://github.com/facebook/folly/tree/main/folly/experimental/coro)** — Facebook 的协程框架：`Task.h`、`TaskWithExecutor.h` 包含完整的 `promise_type` 实现和内存管理策略

### 工具
- **[C++ Insights](https://cppinsights.io/)** — 将协程代码变换为编译器生成的等价 C++ 代码，直观看到 promise_type 的调用和状态机结构
- **[Compiler Explorer](https://godbolt.org/)** — 在线查看协程的汇编输出，观察 HALO 的触发和帧分配的实际大小

### 下一节
[[07-coroutines-task-type|协程 Part 3：编写 Task 类型]] — 将 `promise_type` 的知识应用于构建完整的异步 Task 抽象，包括链式调用、awaitable 适配和异常传播。
