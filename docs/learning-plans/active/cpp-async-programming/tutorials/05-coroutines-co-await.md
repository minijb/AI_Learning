---
title: 协程 Part 1 — co_await 与 Awaitable 协议
updated: 2026-06-08
tags: [cpp, coroutine, co_await, awaitable]
---

# 协程 Part 1 — co_await 与 Awaitable 协议

> **所属计划**: [[cpp-async-programming|C++ 异步编程]]
> **预计耗时**: 75 分钟
> **前置知识**: [[01-threads-and-synchronization|线程与同步原语]], [[02-async-future-promise|std::async 与 future/promise]]
> **C++ 标准**: C++20（协程 TS 已合入标准）
> **编译选项**: `g++ -std=c++20 -fcoroutines`（GCC 10+）或 `clang++ -std=c++20 -stdlib=libc++`（Clang 14+）

---

## 1. 概念讲解

### 1.1 协程要解决什么问题

传统的异步编程需要手动管理状态机：

```cpp
// 回调地狱：嵌套 3 层就已经难以阅读
void fetch_user(int id, std::function<void(User)> callback) {
    db_query("SELECT * FROM users WHERE id = ?", id, [callback](auto result) {
        if (!result) return;
        auto user = parse_user(result);
        fetch_avatar(user.avatar_url, [callback, user](auto avatar) {
            user.avatar = avatar;
            load_friends(user.id, [callback, user](auto friends) {
                user.friends = friends;
                callback(user);  // 4 层缩进，控制流完全丢失
            });
        });
    });
}
```

协程让你用**同步风格写异步代码**——编译器自动生成状态机：

```cpp
// 等价于上面的回调地狱，但读起来像顺序代码
Task<User> fetch_user(int id) {
    auto result = co_await db_query("SELECT * FROM users WHERE id = ?", id);
    if (!result) co_return std::nullopt;

    auto user = parse_user(result);
    user.avatar = co_await fetch_avatar(user.avatar_url);
    user.friends = co_await load_friends(user.id);
    co_return user;
}
```

**核心价值**：将"跨越 suspension 点的状态保存/恢复"从手写转交给编译器。

### 1.2 三个关键字：一个函数如何变成协程

只要函数体中出现 **任意一个** 以下关键字，该函数就成为一个协程：

| 关键字 | 用途 | 位置 |
|--------|------|------|
| `co_await` | 挂起当前协程，等待某个操作完成 | 表达式中 |
| `co_yield` | 挂起并向调用者产出一个值 | 表达式中 |
| `co_return` | 返回最终值并结束协程 | 替代 `return` |

```cpp
// 普通函数
int normal_func() { return 42; }

// 协程 —— 只因为出现了 co_return
Task<int> coro_func() { co_return 42; }
```

> [!important] 协程的返回类型不能是任意类型
> 协程的返回类型必须满足 `promise_type` 协议。这是 Part 2 的核心内容。本节先用简单的占位类型来演示 `co_await` 机制本身。

### 1.3 协程是"无栈协程"

C++20 协程是 **stackless coroutine**（无栈协程），与 Go / Lua 的 stackful 协程有本质区别：

| 特性 | 无栈 (C++20) | 有栈 (Go, Lua) |
|------|-------------|----------------|
| 状态存储 | 堆分配的 coroutine frame | 独立栈（通常 2KB~1MB） |
| 挂起点 | 仅顶层函数可挂起 | 任意嵌套调用都可挂起 |
| 创建开销 | ~一次 `new`（编译器可能优化掉） | ~一次 `mmap` / `malloc` |
| 切换开销 | ~恢复函数指针 + 几个赋值 | ~切换栈指针 + 寄存器组 |
| 内存占用 | 精确等于局部变量大小 | 固定栈大小 |

**关键限制**：在 C++ 协程中，只有协程函数本身可以 `co_await`。你不能在协程调用的普通子函数中 `co_await`——子函数必须也是协程。

### 1.4 Awaiter 协议：三个方法

一个可以被 `co_await` 使用的类型必须实现 **Awaiter 协议** 的三个方法：

```cpp
struct Awaiter {
    // 1. 是否已经就绪？返回 true → 跳过挂起，直接执行 await_resume
    bool await_ready();

    // 2. 挂起时被调用。参数是当前协程的 coroutine_handle。
    //    返回类型可以是 void / bool / coroutine_handle<>
    ??? await_suspend(std::coroutine_handle<> h);

    // 3. co_await 表达式的返回值
    ??? await_resume();
};
```

**`await_ready()` — 决定是否真的挂起**

返回 `true` = "结果已经可用，不要挂起"；返回 `false` = "需要等待，请挂起"。

**`await_suspend(handle)` — 挂起后做什么**

三种合法的返回类型：

| 返回类型 | 行为 |
|----------|------|
| `void` | 挂起后控制权返回给调用者 / 恢复者。通常在这里保存 `handle`，之后由外部事件恢复 |
| `bool` | `true` = 返回给调用者；`false` = 不挂起，立即恢复 |
| `std::coroutine_handle<>` | **对称转移**（symmetric transfer）：不回到调用者，直接跳转到返回的协程 |

`await_suspend` 是实现异步的核心：这里可以启动 I/O、投递任务到线程池、设置定时器——然后保存 `handle`。外部完成后调用 `handle.resume()`。

**`await_resume()` — 恢复后得到什么**

这是 `co_await` 表达式的返回值。通常返回异步操作的结果（如数据库查询的结果集）。

### 1.5 Awaitable vs Awaiter

这两个概念经常被混淆：

- **Awaitable**：一个支持 `co_await` 的类型。它可以自己实现 Awaiter 协议，也可以提供 `operator co_await()` 来返回一个 Awaiter。
- **Awaiter**：实现了 `await_ready / await_suspend / await_resume` 三个方法的类型。

```cpp
// Awaitable：提供 operator co_await() 返回 Awaiter
struct ReadFile {
    std::string path;

    // 返回内部 Awaiter 类型
    auto operator co_await() {
        struct Awaiter {
            ReadFile& parent;
            std::string content;

            bool await_ready() { return false; }
            void await_suspend(std::coroutine_handle<> h) {
                // 启动异步读取...
            }
            std::string await_resume() { return std::move(content); }
        };
        return Awaiter{*this};
    }
};

// 使用
std::string data = co_await ReadFile{"config.json"};
```

> [!tip] 为何需要这个区分
> 你的类型可能需要在 `operator co_await()` 中做一些准备工作，或者根据上下文返回不同的 Awaiter。标准库中的 `std::suspend_always` 和一些第三方库都利用了这个设计。

### 1.6 `co_await` 表达式的逐步变换

当你写 `co_await expr` 时，编译器执行以下变换（简化版）：

```cpp
// 你写的代码：
auto result = co_await expr;

// 编译器生成的等价伪代码：

// Step 1: 获取 Awaitable
auto&& awaitable = expr;  // 或 promise.await_transform(expr) — 见 1.7

// Step 2: 获取 Awaiter
auto&& awaiter = awaitable.operator co_await();  // 如果存在
// 或直接使用 awaitable 作为 awaiter

// Step 3: 检查是否就绪
if (!awaiter.await_ready()) {
    // Step 4: 保存协程状态到 frame
    // （编译器自动完成，你是看不见的）

    // Step 5: 调用 await_suspend
    auto suspend_result = awaiter.await_suspend(coroutine_handle);

    // Step 6: 根据返回类型决定行为
    // - void: 返回给调用者
    // - bool(true): 返回给调用者
    // - bool(false): 立即调用 await_resume
    // - coroutine_handle: 跳转到目标协程
    // （此处协程处于挂起状态，由外部 .resume() 恢复）
}

// Step 7: 协程被恢复后，执行 await_resume 获取结果
auto result = awaiter.await_resume();
```

> [!note] 简化说明
> 实际变换还涉及 `promise_type` 的 `await_transform` 扩展点和 `unhandled_exception` 路径。完整细节见 [[06-coroutines-promise-type|协程 Part 2]]。

### 1.7 `await_transform`：`promise_type` 的扩展点

`promise_type` 可以定义一个 `await_transform()` 方法，拦截 `co_await` 后面的表达式：

```cpp
struct MyPromise {
    // 如果定义了 await_transform，则 co_await X 变成 co_await promise.await_transform(X)
    template<typename T>
    auto await_transform(T&& value) {
        // 可以对所有 co_await 做统一的预处理
        // 例如包装错误处理、超时、取消检查等
        return std::forward<T>(value);
    }

    // 特化：禁止 co_await 某些类型
    void await_transform(std::nullptr_t) = delete;  // 禁止 co_await nullptr
};
```

**实际用途**：
- 统一添加超时机制
- 统一添加取消检查
- 在单线程执行器中禁止 `co_await` 某些异步操作
- 包装所有 awaiter 添加日志 / 追踪

### 1.8 `std::suspend_always` 与 `std::suspend_never`

标准库提供了两个预定义的 awaiter，用于控制协程的初始和最终挂起：

```cpp
// <coroutine> 中定义

struct suspend_always {
    bool await_ready() const noexcept { return false; }
    void await_suspend(std::coroutine_handle<>) const noexcept {}
    void await_resume() const noexcept {}
};

struct suspend_never {
    bool await_ready() const noexcept { return true; }
    void await_suspend(std::coroutine_handle<>) const noexcept {}
    void await_resume() const noexcept {}
};
```

它们用在 `promise_type` 的 `initial_suspend()` 和 `final_suspend()` 中：

| 钩子 | `suspend_always` | `suspend_never` |
|------|-----------------|-----------------|
| `initial_suspend` | 协程启动后立即挂起（惰性启动） | 协程启动后直接执行到第一个挂起点（急切启动） |
| `final_suspend` | 协程结束后保持挂起（允许外部读取结果） | 协程结束后自动销毁（不能读取结果） |

> [!warning] `final_suspend` 返回 `suspend_never` 的风险
> 如果 `final_suspend()` 返回 `suspend_never`，协程 frame 在 `co_return` 后立即销毁——此时 `promise_type` 的数据成员如果被外部引用，就会成为悬空引用。

---

## 2. 代码示例

### 示例 1：简单日志 Awaiter — 打印挂起/恢复的完整生命周期

**编译与运行**：

```bash
g++ -std=c++20 -fcoroutines -o example1 example1.cpp && ./example1
```

**预期输出**：

```
[main] 创建协程
[coro] 进入协程
[awaiter] await_ready() → 返回 false，将挂起
[awaiter] await_suspend() — 协程已挂起
[main] 协程返回后继续执行
[main] 2 秒后手动恢复协程
[awaiter] await_resume() — 协程已恢复
[coro] co_await 完成，返回值 = 42
[coro] 协程结束
[main] 协程已销毁
```

```cpp
#include <coroutine>
#include <iostream>
#include <thread>
#include <chrono>

// --- 自定义 Awaiter ---
struct LoggingAwaiter {
    int value;

    bool await_ready() const noexcept {
        std::cout << "[awaiter] await_ready() → 返回 false，将挂起\n";
        return false;  // 总是需要挂起
    }

    void await_suspend(std::coroutine_handle<> h) const noexcept {
        std::cout << "[awaiter] await_suspend() — 协程已挂起\n";
        // 注意：这里没有保存 handle，所以协程永远不会被恢复（见下方）
        // 为了能演示恢复，我们在 main 中手动保存
        // 实际代码应在这里保存 h 到某个全局/成员变量
    }

    int await_resume() const noexcept {
        std::cout << "[awaiter] await_resume() — 协程已恢复\n";
        return value;
    }
};

// --- 占位 promise_type（Part 2 会深入） ---
struct Task {
    struct promise_type {
        Task get_return_object() { return {}; }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
    };
};

// --- 使用协程 ---
std::coroutine_handle<> saved_handle;

Task my_coroutine() {
    std::cout << "[coro] 进入协程\n";

    int result = co_await LoggingAwaiter{42};

    std::cout << "[coro] co_await 完成，返回值 = " << result << "\n";
    std::cout << "[coro] 协程结束\n";
}

int main() {
    std::cout << "[main] 创建协程\n";
    my_coroutine();  // 协程执行到 co_await 后挂起，返回

    std::cout << "[main] 协程返回后继续执行\n";

    // 实际问题：我们丢失了 coroutine_handle，无法恢复！
    // 下面展示正确方式：在 await_suspend 中保存 handle
    std::cout << "[main] 警告：协程永远不会被恢复 — 内存泄漏！\n";

    return 0;
}
```

> [!warning] 上面代码有 bug
> 上述代码展示了**最常见错误**：`await_suspend` 中没有保存 `handle` 导致协程泄漏。正确的做法见下面改进版。

**改进版：在 `await_suspend` 中保存 handle**

```cpp
#include <coroutine>
#include <iostream>

std::coroutine_handle<> saved_handle;  // 全局/或传入 awaiter

struct ResumeAfterSave {
    bool await_ready() const noexcept { return false; }

    void await_suspend(std::coroutine_handle<> h) {
        std::cout << "[awaiter] 保存 handle，协程已挂起\n";
        saved_handle = h;  // ✅ 保存，后续可以 .resume()
    }

    int await_resume() const noexcept {
        std::cout << "[awaiter] 协程被恢复\n";
        return 99;
    }
};

struct Task {
    struct promise_type {
        Task get_return_object() { return {}; }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
    };
};

Task demo() {
    std::cout << "[coro] 开始\n";
    int val = co_await ResumeAfterSave{};
    std::cout << "[coro] 恢复后 val = " << val << "\n";
}

int main() {
    std::cout << "[main] 启动协程\n";
    demo();
    std::cout << "[main] 协程已挂起，手动恢复\n";
    saved_handle.resume();  // ✅ 恢复协程
    std::cout << "[main] 结束\n";
}
```

**预期输出**：

```
[main] 启动协程
[coro] 开始
[awaiter] 保存 handle，协程已挂起
[main] 协程已挂起，手动恢复
[awaiter] 协程被恢复
[coro] 恢复后 val = 99
[main] 结束
```

### 示例 2：`std::suspend_always` 与 `std::suspend_never` 的行为对比

**编译与运行**：

```bash
g++ -std=c++20 -fcoroutines -o example2 example2.cpp && ./example2
```

**预期输出**：

```
=== suspend_never (急切启动) ===
[main] 创建协程
[coro] 直接执行到 co_await
[awaiter] 挂起
[main] 协程挂起后才到达这一行
[main] 恢复协程
[coro] 恢复后结束

=== suspend_always (惰性启动) ===
[main] 创建协程
[main] 协程尚未执行！需要手动 .resume()
[main] 手动恢复 → 协程开始执行
[coro] 这才开始执行
[awaiter] 挂起
[main] 再次回到 main
```

```cpp
#include <coroutine>
#include <iostream>
#include <thread>
#include <chrono>

std::coroutine_handle<> g_handle;

struct SimpleAwaiter {
    bool await_ready() const noexcept { return false; }
    void await_suspend(std::coroutine_handle<> h) const noexcept {
        std::cout << "[awaiter] 挂起\n";
        g_handle = h;
    }
    void await_resume() const noexcept { std::cout << "[awaiter] 恢复\n"; }
};

// --- 急切启动的协程 ---
struct EagerTask {
    struct promise_type {
        EagerTask get_return_object() { return {}; }
        std::suspend_never initial_suspend() { return {}; }   // ← 不挂起
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
    };
};

EagerTask eager_coro() {
    std::cout << "[coro] 直接执行到 co_await\n";
    co_await SimpleAwaiter{};
    std::cout << "[coro] 恢复后结束\n";
}

// --- 惰性启动的协程 ---
struct LazyTask {
    struct promise_type {
        LazyTask get_return_object() {
            return LazyTask{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }
        std::suspend_always initial_suspend() { return {}; }  // ← 初始挂起
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
    };

    std::coroutine_handle<promise_type> handle;

    void resume() { handle.resume(); }
    explicit LazyTask(std::coroutine_handle<promise_type> h) : handle(h) {}
};

LazyTask lazy_coro() {
    std::cout << "[coro] 这才开始执行\n";
    co_await SimpleAwaiter{};
    std::cout << "[coro] 恢复后结束\n";
}

int main() {
    std::cout << "=== suspend_never (急切启动) ===\n";
    std::cout << "[main] 创建协程\n";
    eager_coro();
    std::cout << "[main] 协程挂起后才到达这一行\n";
    std::cout << "[main] 恢复协程\n";
    g_handle.resume();
    g_handle = nullptr;

    std::cout << "\n=== suspend_always (惰性启动) ===\n";
    std::cout << "[main] 创建协程\n";
    auto task = lazy_coro();
    std::cout << "[main] 协程尚未执行！需要手动 .resume()\n";
    std::cout << "[main] 手动恢复 → 协程开始执行\n";
    task.resume();
    std::cout << "[main] 再次回到 main\n";
    g_handle.resume();  // 恢复第二个挂起点
}
```

### 示例 3：自定义 Awaitable 实现线程切换

**编译与运行**：

```bash
g++ -std=c++20 -fcoroutines -pthread -o example3 example3.cpp && ./example3
```

**预期输出**（线程 ID 因系统而异）：

```
[main]   线程 140290873423680 — 启动
[coro]   线程 140290873423680 — 进入协程（在 main 线程上）
[coro]   线程 140290873423680 — co_await switch_to_new_thread
[awaiter] 线程 140290865030848 — await_suspend：切换到新线程
[main]   线程 140290873423680 — 协程挂起后回到 main
[coro]   线程 140290865030848 — 协程恢复（现在在新线程上！）
[awaiter] 线程 140290865030848 — await_resume：在新线程上
[main]   线程 140290873423680 — 等待新线程完成
```

```cpp
#include <coroutine>
#include <iostream>
#include <thread>
#include <chrono>

std::thread::id main_thread_id;

// --- 线程切换 Awaiter ---
struct SwitchToThread {
    std::thread new_thread;

    // 真正的 Awaiter，由 operator co_await 返回
    struct Awaiter {
        std::coroutine_handle<> coro_handle;

        bool await_ready() const noexcept { return false; }

        void await_suspend(std::coroutine_handle<> h) {
            // 在新线程中恢复协程！
            std::thread([h, this]() {
                std::cout << "[awaiter] 线程 " << std::this_thread::get_id()
                          << " — await_suspend：切换到新线程\n";
                h.resume();  // 在新线程上恢复
            }).detach();
        }

        void await_resume() const noexcept {
            // 现在在新线程上执行
            std::cout << "[awaiter] 线程 " << std::this_thread::get_id()
                      << " — await_resume：在新线程上\n";
        }
    };

    // operator co_await：Awaitable → Awaiter
    auto operator co_await() {
        return Awaiter{};
    }
};

// --- Task 类型 ---
struct Task {
    struct promise_type {
        Task get_return_object() { return {}; }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
    };
};

std::thread::id coro_start_thread;

Task my_coroutine() {
    coro_start_thread = std::this_thread::get_id();
    std::cout << "[coro]   线程 " << coro_start_thread
              << " — 进入协程（在 main 线程上）\n";

    co_await SwitchToThread{};  // 在这里切换线程

    auto now_thread = std::this_thread::get_id();
    std::cout << "[coro]   线程 " << now_thread
              << " — 协程恢复（现在在新线程上！）\n";
}

int main() {
    main_thread_id = std::this_thread::get_id();
    std::cout << "[main]   线程 " << main_thread_id << " — 启动\n";

    my_coroutine();

    std::cout << "[main]   线程 " << main_thread_id
              << " — 协程挂起后回到 main\n";

    // 给新线程足够时间完成（生产中应使用同步机制）
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    std::cout << "[main]   线程 " << main_thread_id
              << " — 等待新线程完成\n";

    return 0;
}
```

### 示例 4：`await_transform` — 拦截所有 `co_await`

**编译与运行**：

```bash
g++ -std=c++20 -fcoroutines -o example4 example4.cpp && ./example4
```

**预期输出**：

```
[await_transform] 拦截 co_await: type = i (int)
[awaiter]    await_ready: false
[await_transform] 拦截 co_await: type = d (double)
[awaiter]    await_ready: false
[coro] 结果: 42 (int), 3.14 (double)
[await_transform] 拒绝 co_await nullptr!
```

```cpp
#include <coroutine>
#include <iostream>
#include <type_traits>

std::coroutine_handle<> g_handle;

// --- 简单 Awaiter ---
struct SimpleAwaiter {
    bool await_ready() const noexcept {
        std::cout << "[awaiter]    await_ready: false\n";
        return false;
    }
    void await_suspend(std::coroutine_handle<> h) const noexcept {
        g_handle = h;
    }
    void await_resume() const noexcept {}
};

// --- Awaitable：包装值 ---
template<typename T>
struct LoggingAwaitable {
    T value;

    auto operator co_await() {
        struct Awaiter {
            T val;
            bool await_ready() const noexcept { return false; }
            void await_suspend(std::coroutine_handle<> h) const noexcept {
                g_handle = h;
            }
            T await_resume() const noexcept { return val; }
        };
        return Awaiter{value};
    }
};

// --- promise_type 带 await_transform ---
struct Task {
    struct promise_type {
        Task get_return_object() { return {}; }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}

        // -- await_transform 扩展点 --

        // 通用版本：打印类型信息
        template<typename T>
        auto await_transform(T&& val) {
            using Raw = std::remove_cvref_t<T>;
            std::cout << "[await_transform] 拦截 co_await: type = "
                      << (std::is_same_v<Raw, int> ? "i" :
                          std::is_same_v<Raw, double> ? "d" : "?")
                      << " (" << typeid(Raw).name() << ")\n";
            return LoggingAwaitable<Raw>{std::forward<T>(val)};
        }

        // 特化：禁止 co_await nullptr
        void await_transform(std::nullptr_t) = delete;
    };
};

Task demo() {
    std::cout << "[coro] 开始\n";

    int a = co_await 42;       // 触发 await_transform(int&&)
    double b = co_await 3.14;  // 触发 await_transform(double&&)

    std::cout << "[coro] 结果: " << a << " (int), " << b << " (double)\n";

    // co_await nullptr;  // 编译错误！await_transform(nullptr) = delete
}

int main() {
    demo();
    g_handle.resume();  // a = 42
    g_handle.resume();  // b = 3.14

    // 证明 nullptr 被阻止
    std::cout << "[await_transform] 拒绝 co_await nullptr!\n";
    return 0;
}
```

---

## 3. 练习

### 练习 1：实现 LoggingAwaiter（入门）

编写一个 `LoggingAwaiter`，满足以下要求：

- 构造时接受一个 `std::string label` 参数
- `await_ready()` 返回 `false`
- `await_suspend()` 打印 `"[label] suspended"`
- `await_resume()` 打印 `"[label] resumed"`，返回一个 `int` 值
- 在协程中使用它，手动保存 `coroutine_handle` 并在 `main` 中恢复

**提示**：参考示例 1 的 `LoggingAwaiter`，补充 `await_ready` / `await_suspend` / `await_resume` 的实现。

**编译验证**：

```bash
g++ -std=c++20 -fcoroutines -Wall -Wextra -o ex1 ex1.cpp && ./ex1
```

**期望输出**：

```
[main] 启动
[coro] co_await "first" 前
[first] suspended
[main] 恢复
[first] resumed
[coro] 得到结果: 100
[coro] co_await "second" 前
[second] suspended
[main] 恢复
[second] resumed
[coro] 得到结果: 200
[coro] 结束
```

### 练习 2：实现 DelayAwaiter（进阶）

编写一个 `DelayAwaiter`，在指定毫秒后自动恢复协程：

- 构造时接受 `int delay_ms` 参数
- `await_ready()` 返回 `false`
- `await_suspend()` 中启动一个独立线程，sleep `delay_ms` 毫秒后调用 `handle.resume()`
- `await_resume()` 打印 `"[delay] resumed after Nms"`（打印实际耗时）

**要求**：
- 使用 `<chrono>` 的 `high_resolution_clock` 测量实际耗时
- 在 `await_suspend` 被调用时记录开始时间，在 `await_resume` 中计算差值

**编译验证**：

```bash
g++ -std=c++20 -fcoroutines -pthread -o ex2 ex2.cpp && ./ex2
```

**期望输出**（耗时约 500ms）：

```
[main] 创建协程
[coro] 开始 co_await 500ms ...
[main] 协程已挂起
[delay] resumed after 501ms
[coro] 完成
```

### 练习 3：实现 SwitchToThread Awaiter（挑战）

在示例 3 的基础上，实现一个增强版 `switch_to_thread`，支持**回到原线程**：

1. **`SwitchToNewThread`**：切换到新线程（示例 3 已实现）
2. **`SwitchBack`**：回到 `main` 线程——需要传递 `main` 线程的 `std::thread::id`，在 `await_suspend` 中通过消息队列或 `std::promise`/`std::future` 通知 `main` 线程来恢复

**额外要求**：
- 使用 `std::condition_variable` + `std::mutex` 实现线程间通知（不要 busy-waiting）
- 协程路径：`main thread → new thread → main thread`

**编译验证**：

```bash
g++ -std=c++20 -fcoroutines -pthread -o ex3 ex3.cpp && ./ex3
```

**期望输出**（线程 ID 因系统而异）：

```
[main]   线程 140290873423680 — 开始
[coro]   线程 140290873423680 — 在 main 线程
[awaiter] 线程 140290865030848 — switch_to_new_thread: await_suspend
[main]   线程 140290873423680 — 协程已离开 main 线程
[coro]   线程 140290865030848 — 现在在新线程
[awaiter] 线程 140290873423680 — switch_back: await_suspend，通知 main
[main]   线程 140290873423680 — 收到通知, 恢复协程
[coro]   线程 140290873423680 — 回到 main 线程！
[main]   线程 140290873423680 — 完成
```

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> #include <coroutine>
> #include <iostream>
> #include <string>
> 
> struct LoggingAwaiter {
>     std::string label;
>     int result_value;
> 
>     bool await_ready() const noexcept { return false; }
> 
>     void await_suspend(std::coroutine_handle<> h) {
>         // 打印挂起信息并保存 handle 供外部恢复
>         std::cout << "[" << label << "] suspended\n";
>         saved_handle = h;  // 全局保存，main 中恢复
>     }
> 
>     int await_resume() const noexcept {
>         std::cout << "[" << label << "] resumed\n";
>         return result_value;  // co_await 表达式的返回值
>     }
> };
> 
> // 全局 handle，简化示例（生产代码应封装在 promise_type 中）
> std::coroutine_handle<> saved_handle;
> 
> // --- 最小协程返回类型（仅用于演示 awaiter） ---
> struct Task {
>     struct promise_type {
>         Task get_return_object() {
>             return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
>         }
>         std::suspend_never initial_suspend() { return {}; }
>         std::suspend_always final_suspend() noexcept { return {}; }
>         void return_void() {}
>         void unhandled_exception() { std::terminate(); }
>     };
> 
>     std::coroutine_handle<promise_type> handle;
>     explicit Task(std::coroutine_handle<promise_type> h) : handle(h) {}
>     ~Task() { if (handle) handle.destroy(); }
>     Task(const Task&) = delete;
>     Task& operator=(const Task&) = delete;
>     Task(Task&&) = default;
>     Task& operator=(Task&&) = default;
> };
> 
> Task my_coroutine() {
>     std::cout << "[coro] co_await \"first\" 前\n";
>     int r1 = co_await LoggingAwaiter{"first", 100};
>     std::cout << "[coro] 得到结果: " << r1 << "\n";
> 
>     std::cout << "[coro] co_await \"second\" 前\n";
>     int r2 = co_await LoggingAwaiter{"second", 200};
>     std::cout << "[coro] 得到结果: " << r2 << "\n";
> 
>     std::cout << "[coro] 结束\n";
> }
> 
> int main() {
>     std::cout << "[main] 启动\n";
>     auto task = my_coroutine();   // 协程立即开始（initial_suspend = never）
> 
>     std::cout << "[main] 恢复\n";
>     if (saved_handle) saved_handle.resume();  // 恢复第一次挂起
> 
>     std::cout << "[main] 恢复\n";
>     if (saved_handle) saved_handle.resume();  // 恢复第二次挂起
> }
> ```
> 
> **关键点**：
> - `await_suspend` 中保存 `coroutine_handle`——这是协程恢复的唯一入口
> - `await_resume` 的返回值成为 `co_await` 表达式的结果
> - `initial_suspend` 用 `suspend_never` 让协程立即执行到第一个 `co_await`

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <coroutine>
> #include <iostream>
> #include <thread>
> #include <chrono>
> 
> struct DelayAwaiter {
>     int delay_ms;
>     std::chrono::steady_clock::time_point start_time;
> 
>     bool await_ready() const noexcept { return false; }
> 
>     void await_suspend(std::coroutine_handle<> h) {
>         // 记录开始时间，启动独立线程在 delay_ms 后恢复协程
>         start_time = std::chrono::steady_clock::now();
>         std::thread([h, ms = delay_ms] {
>             std::this_thread::sleep_for(std::chrono::milliseconds(ms));
>             h.resume();  // 在独立线程中恢复协程
>         }).detach();     // detach：线程自行结束，无需 join
>     }
> 
>     void await_resume() {
>         auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
>             std::chrono::steady_clock::now() - start_time).count();
>         std::cout << "[delay] resumed after " << elapsed << "ms\n";
>     }
> };
> 
> // --- 最小协程返回类型（同练习 1） ---
> struct Task {
>     struct promise_type {
>         Task get_return_object() {
>             return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
>         }
>         std::suspend_never initial_suspend() { return {}; }
>         std::suspend_always final_suspend() noexcept { return {}; }
>         void return_void() {}
>         void unhandled_exception() { std::terminate(); }
>     };
> 
>     std::coroutine_handle<promise_type> handle;
>     explicit Task(std::coroutine_handle<promise_type> h) : handle(h) {}
>     ~Task() { if (handle) handle.destroy(); }
>     Task(const Task&) = delete;
>     Task& operator=(const Task&) = delete;
>     Task(Task&&) = default;
>     Task& operator=(Task&&) = default;
> };
> 
> Task my_coroutine() {
>     std::cout << "[coro] 开始 co_await 500ms ...\n";
>     co_await DelayAwaiter{500};
>     std::cout << "[coro] 完成\n";
> }
> 
> int main() {
>     std::cout << "[main] 创建协程\n";
>     auto task = my_coroutine();
>     std::cout << "[main] 协程已挂起\n";
> 
>     // 协程在 delay 线程完成后会被自动恢复
>     // 给足够时间让它完成（> 500ms）
>     std::this_thread::sleep_for(std::chrono::milliseconds(600));
> }
> ```
> 
> **设计要点**：
> - `await_suspend` 中 `detach()` 线程——线程自行结束，不阻塞 awaiter
> - 使用 `std::chrono::steady_clock` 测量实际耗时（不受系统时间调整影响）
> - **注意线程安全**：`h.resume()` 在另一个线程中调用，确保协程的 `promise_type` 支持多线程

> [!tip]- 练习 3 参考答案
> ```cpp
> #include <coroutine>
> #include <iostream>
> #include <thread>
> #include <mutex>
> #include <condition_variable>
> #include <queue>
> 
> // --- 跨线程恢复的基础设施 ---
> std::mutex mtx;
> std::condition_variable cv;
> std::queue<std::coroutine_handle<>> ready_queue;  // 待恢复的协程队列
> std::thread::id main_thread_id;
> 
> void enqueue_resume(std::coroutine_handle<> h) {
>     {
>         std::lock_guard lk(mtx);
>         ready_queue.push(h);
>     }
>     cv.notify_one();
> }
> 
> // --- 线程信息打印辅助 ---
> std::string thread_str() {
>     auto id = std::this_thread::get_id();
>     std::ostringstream oss;
>     oss << id;
>     return oss.str();
> }
> 
> // --- Awaiter：切换到新线程 ---
> struct SwitchToNewThread {
>     bool await_ready() const noexcept { return false; }
> 
>     void await_suspend(std::coroutine_handle<> h) {
>         std::cout << "[awaiter] 线程 " << thread_str()
>                   << " — switch_to_new_thread: await_suspend\n";
>         // 在新线程中恢复协程
>         std::thread([h] {
>             h.resume();
>         }).detach();
>     }
> 
>     void await_resume() const noexcept {}
> };
> 
> // --- Awaiter：切换回 main 线程 ---
> struct SwitchBack {
>     bool await_ready() const noexcept { return false; }
> 
>     void await_suspend(std::coroutine_handle<> h) {
>         std::cout << "[awaiter] 线程 " << thread_str()
>                   << " — switch_back: await_suspend，通知 main\n";
>         // 将协程加入队列，通知 main 线程恢复
>         enqueue_resume(h);
>     }
> 
>     void await_resume() const noexcept {}
> };
> 
> // --- 最小协程返回类型 ---
> struct Task {
>     struct promise_type {
>         Task get_return_object() {
>             return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
>         }
>         std::suspend_never initial_suspend() { return {}; }
>         std::suspend_always final_suspend() noexcept { return {}; }
>         void return_void() {}
>         void unhandled_exception() { std::terminate(); }
>     };
> 
>     std::coroutine_handle<promise_type> handle;
>     explicit Task(std::coroutine_handle<promise_type> h) : handle(h) {}
>     ~Task() { if (handle) handle.destroy(); }
>     Task(const Task&) = delete;
>     Task& operator=(const Task&) = delete;
>     Task(Task&&) = default;
>     Task& operator=(Task&&) = default;
> };
> 
> Task my_coroutine() {
>     std::cout << "[coro]   线程 " << thread_str() << " — 在 main 线程\n";
> 
>     co_await SwitchToNewThread{};
>     std::cout << "[coro]   线程 " << thread_str() << " — 现在在新线程\n";
> 
>     co_await SwitchBack{};
>     std::cout << "[coro]   线程 " << thread_str() << " — 回到 main 线程！\n";
> }
> 
> int main() {
>     main_thread_id = std::this_thread::get_id();
>     std::cout << "[main]   线程 " << thread_str() << " — 开始\n";
> 
>     auto task = my_coroutine();
>     std::cout << "[main]   线程 " << thread_str() << " — 协程已离开 main 线程\n";
> 
>     // main 线程事件循环：等待协程恢复请求
>     bool running = true;
>     while (running && !task.handle.done()) {
>         std::unique_lock lk(mtx);
>         cv.wait(lk, [] { return !ready_queue.empty(); });
> 
>         while (!ready_queue.empty()) {
>             auto h = ready_queue.front();
>             ready_queue.pop();
>             lk.unlock();
> 
>             std::cout << "[main]   线程 " << thread_str() << " — 收到通知, 恢复协程\n";
>             h.resume();
> 
>             lk.lock();
>         }
>     }
>     std::cout << "[main]   线程 " << thread_str() << " — 完成\n";
> }
> ```
> 
> **架构要点**：
> 
> - **消息队列 + condition_variable**：避免 busy-waiting，main 线程在 cv 上阻塞等待
> - **协程路径**：`main thread → SwitchToNewThread (new thread) → SwitchBack (queue → main)`
> - **SwitchToNewThread**：`await_suspend` 中启动新线程，新线程调用 `h.resume()` 恢复协程
> - **SwitchBack**：`await_suspend` 中将 handle 入队，`cv.notify_one()` 唤醒 main 线程
> - **线程安全**：`ready_queue` 由 `mutex` + `cv` 保护，确保多个 awaiter 并发入队安全

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 常见陷阱

### 陷阱 1：忘记 `resume()` → 协程泄漏

```cpp
// ❌ 错误：协程挂起后永远不被恢复
Task bad_coro() {
    co_await SomeAwaiter{};  // await_suspend 中未保存 handle
    // 协程永远到不了这里
}
```

协程的 frame 是在堆上分配的。如果 `await_suspend` 中没有保存 `coroutine_handle` 并在合适的时机调用 `.resume()`，该 frame **永远不会被释放**——造成内存泄漏。

**解决方案**：
- 总是在 `await_suspend` 中保存 `handle`
- 确保最终有代码调用 `handle.resume()` 或 `handle.destroy()`
- 如果协程不再需要，调用 `handle.destroy()` 主动释放

### 陷阱 2：协程 frame 中引用参数悬空

```cpp
// ❌ 危险：参数 s 是引用，但协程在 s 生命周期结束后才恢复
Task read_file(const std::string& path) {
    auto data = co_await async_read(path);  // path 可能已悬空！
    co_return data;
}

void caller() {
    std::string p = "/tmp/data.txt";
    auto task = read_file(p);   // 传引用
    p.clear();                   // path 的存储被修改
    // 协程恢复时 path 可能已被破坏
}
```

协程的参数如果通过引用传递，它们的存储可能比协程 frame 先销毁。特别是当 `initial_suspend()` 返回 `suspend_always` 时——协程尚未开始执行，但调用者可能已经离开作用域。

**解决方案**：
- 协程参数**尽量按值传递**
- 如果必须用引用，确保调用者的生命周期覆盖整个协程
- 使用 `std::shared_ptr` 等共享所有权机制

### 陷阱 3：Awaiter 析构时机不当

```cpp
// ❌ 危险：awaiter 在 co_await 表达式结束后被销毁
struct DangerousAwaiter {
    int* ptr;

    bool await_ready() { return false; }
    void await_suspend(std::coroutine_handle<> h) {
        saved = h;
    }
    int* await_resume() {
        return ptr;  // ptr 指向谁的数据？
    }
};

Task bad() {
    int local = 42;
    auto* p = co_await DangerousAwaiter{&local};
    // 此时 DangerAwaiter 已经被销毁！
    // p 指向 awaiter 内部的 ptr，而 awaiter 已经不存在了
}
```

Awaiter 对象**在 `await_resume()` 返回后立即销毁**（它是 `co_await` 表达式中的临时对象）。因此：

- 不要在 `await_resume()` 中返回指向 awaiter 自身成员的指针或引用
- 如果 `await_resume()` 需要返回复杂对象，**move 出来**

### 陷阱 4：`await_suspend` 返回 `coroutine_handle` 类型错误

```cpp
// ❌ 不同类型之间的对称转移可能出错
struct BadAwaiter {
    bool await_ready() { return false; }

    // 返回 std::coroutine_handle<> (无类型擦除)
    std::coroutine_handle<> await_suspend(std::coroutine_handle<Task::promise_type> h) {
        // 如果返回的 handle 类型不匹配，行为未定义
        return some_other_handle;  // ⚠️ 必须确保目标协程与此兼容
    }
};
```

对称转移时，如果返回的 `coroutine_handle` 类型与实际目标不一致，结果未定义。尤其注意：

- `std::coroutine_handle<void>` vs `std::coroutine_handle<PromiseType>` — 它们是不同类型
- 使用 `.address()` 比较两个 handle 时，确保两者类型一致

**解决方案**：
- 对称转移前，确保目标的 `promise_type` 与你返回的 handle 类型匹配
- 不确定时，返回 `void` 并在外部通过统一调度器恢复

### 陷阱 5：异常在协程中的传播

```cpp
// ❌ 如果 awaiter 在 await_suspend 中抛出异常，行为取决于 promise_type
struct ThrowingAwaiter {
    bool await_ready() { return false; }
    void await_suspend(std::coroutine_handle<> h) {
        throw std::runtime_error("oops");  // 异常传播到 promise_type::unhandled_exception()
    }
    void await_resume() {}
};
```

- 如果 `promise_type::unhandled_exception()` 未正确处理，程序 `std::terminate()`
- 在生产代码中，所有 `await_suspend` 实现必须是 `noexcept` 或将异常转化为错误码

### 陷阱 6：多线程恢复的竞态条件

当多个线程可能同时恢复同一个协程时，存在竞态：

```cpp
// ❌ 两个 awaiter 可能同时 .resume() 同一个协程
void timer_callback(std::coroutine_handle<> h) {
    h.resume();  // 线程 A 恢复
}

void io_callback(std::coroutine_handle<> h) {
    h.resume();  // 线程 B 同时恢复 → 数据竞争
}
```

**解决方案**：
- 确保每个协程同一时刻只被一个线程恢复
- 使用原子标志位防止重复恢复
- 通过 `await_suspend` 返回另一个 `coroutine_handle` 实现无锁对称转移

---

## 5. 延伸阅读

> [!note] 本节是该系列的基础。下一节将深入 `promise_type` 的内部机制。

### 必读

- [[06-coroutines-promise-type|协程 Part 2：promise_type 深入]] — 下一节，掌握协程的控制核心
- [Lewis Baker: Understanding `operator co_await`](https://lewissbaker.github.io/2017/11/17/understanding-operator-co-await) — co_await 机制的经典文章
- [cppreference: Coroutines (C++20)](https://en.cppreference.com/w/cpp/language/coroutines) — 标准参考

### 推荐

- [C++ Coroutines: Understanding the promise type](https://lewissbaker.github.io/2018/09/05/understanding-the-promise-type) — Lewis Baker 的 promise_type 详解
- [CppCon 2022: C++20 Coroutines — The Low Level Interface](https://www.youtube.com/watch?v=8sEe-4tig_A) — Andreas Fertig 的演讲（视频）
- [cppcoro 库](https://github.com/lewissbaker/cppcoro) — Lewis Baker 的协程库参考实现

### 进阶

- [C++ Coroutines: Symmetric Transfer](https://lewissbaker.github.io/2020/05/11/understanding_symmetric_transfer) — 对称转移与无栈协程的调度优化
- [Compiler Explorer](https://godbolt.org/) — 在线查看协程代码的编译器变换（搜索 "coroutine" 示例）
- [C++ Insights](https://cppinsights.io/) — 查看协程的编译器展开（编译器生成的代码）

### 本书单相关

- **C++ Concurrency in Action (2nd Edition)** — Anthony Williams：第 3 章（线程基础）和协程相关附录
- **C++ High Performance (2nd Edition)** — Björn Andrist：第 9 章（协程与异步编程）
