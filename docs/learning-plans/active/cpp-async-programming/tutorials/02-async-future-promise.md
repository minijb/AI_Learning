---
title: std::async 与 std::future/std::promise
updated: 2026-06-08
tags: [cpp, async, future, promise]
---

# std::async 与 `std::future`/`std::promise`

> 前置知识：[[01-threads-and-synchronization|线程与同步原语]]
> 后续学习：[[03-packaged-task-shared-future|packaged_task 与 shared_future]]

---

## 一、概念

### 1.1 Future/Promise 模型

C++ 的 future/promise 模型解决了一个核心问题：**如何在不同线程之间传递一个"尚未就绪"的值**。

想象餐厅的场景：

- **顾客（Consumer）** 点了一份牛排，拿到一个 **取餐牌（`std::future`）**。
- **厨师（Producer）** 开始做牛排。厨房的 **订餐系统（Shared State / 共享状态）** 记录了这个订单。
- 顾客可以问"好了没？"（`wait_for()`），也可以干等着（`get()`）。
- 厨师做好后，把牛排放到窗口（`set_value()`）。取餐牌亮起，顾客拿到牛排。
- **关键**：顾客和厨师不直接见面，**共享状态**是它们之间的唯一桥梁。

```
Producer(promise) ── set_value() ──→ [Shared State] ── get() ──→ Consumer(future)
```

> [!note] 核心思想
> **生产者**通过 `std::promise` 把结果放入共享状态；**消费者**通过 `std::future` 从共享状态取出结果。
> 两者完全解耦——可以处于不同线程，甚至 `promise` 可以在 `future` 被请求之前就 set 好值。

### 1.2 `std::async`：最简单的一步式异步

`std::async` 把"创建线程 + 获取返回值"打包成一个调用：

```cpp
auto future = std::async(std::launch::async, [] { return heavy_compute(); });
// 继续干别的...
auto result = future.get();  // 阻塞直到计算完成
```

#### 启动策略（Launch Policy）

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| `std::launch::async` | **必须**在新线程上执行（如同 `std::thread`） | 需要真正的并行 |
| `std::launch::deferred` | **延迟**执行——只在 `get()`/`wait()` 被首次调用时，在**调用者线程**上执行 | 可能不需要结果的计算（lazy evaluation） |
| `async \| deferred`（默认） | 由实现选择——通常优先新线程，但资源不足时可能 fallback 到 deferred | 通用场景 |

> [!warning] 默认策略的陷阱
> 默认 `async | deferred` 允许实现选择 `deferred`，这意味着任务**可能根本不在新线程中运行**。
> 如果你需要保证并行执行，**显式指定 `std::launch::async`**。

### 1.3 `std::future<T>`：消费者的视角

`std::future` 是**唯一消费**（one-shot）的。`get()` 会移动走值，之后 `valid() == false`。

| 操作 | 行为 | 阻塞？ |
|------|------|--------|
| `get()` | 等待结果就绪，然后移动返回值 | 是（直到就绪） |
| `wait()` | 等待结果就绪，但不获取值 | 是（直到就绪） |
| `wait_for(rel)` | 等待一段时间，返回 `future_status` | 最多等 `rel` |
| `wait_until(abs)` | 等待到某个时间点 | 最多等到 `abs` |
| `valid()` | 检查 future 是否持有共享状态 | 否 |
| `share()` | 将 `future` 转移为 `shared_future` | 否 |

`wait_for()` 和 `wait_until()` 返回 `std::future_status`：

| 返回值 | 含义 |
|--------|------|
| `std::future_status::ready` | 结果已就绪 |
| `std::future_status::timeout` | 等待超时 |
| `std::future_status::deferred` | 任务是 deferred 且尚未开始执行 |

### 1.4 `std::promise<T>`：生产者的视角

`std::promise` 是共享状态的**写入端**：

| 操作 | 行为 |
|------|------|
| `get_future()` | 获取关联的 `std::future`（只能调用一次） |
| `set_value(v)` | 设置结果值 |
| `set_value_at_thread_exit(v)` | 在线程退出时设置值 |
| `set_exception(p)` | 设置异常（`std::exception_ptr`） |
| `set_exception_at_thread_exit(p)` | 在线程退出时设置异常 |

> [!important] 一个 promise 对应一个 future
> `get_future()` 只能调用一次——一个 `promise` 只产生一个 `future`。
> 如果需要多个消费者，使用 `std::shared_future`（见 [[03-packaged-task-shared-future]]）。

### 1.5 异常传播

future/promise 模型内置了异常传播机制：

1. **`std::async`** 调用的函数如果抛出异常，异常被运行时捕获，存储在共享状态中，在 `get()` 时重新抛出。
2. **`std::promise`** 可以通过 `set_exception()` 显式设置异常。
3. 如果 `promise` 在设置值或异常之前就被销毁 → `std::future_error`（错误码 `broken_promise`）。
4. 如果 `future` 的 `get()` 被调用时共享状态已被销毁 → `std::future_error`（错误码 `no_state`）。

### 1.6 共享状态（Shared State）

共享状态是 future/promise 机制的核心数据结构：

```
┌───────────────────────────────────────────┐
│              Shared State                 │
│  ┌─────────────────────────────────────┐  │
│  │ 状态：empty / value / exception     │  │
│  │ 存储：T 类型的值 或 exception_ptr   │  │
│  │ 引用计数：promise + future 各持一个  │  │
│  │ 同步：mutex + condition_variable    │  │
│  └─────────────────────────────────────┘  │
└───────────────────────────────────────────┘
```

- 共享状态在堆上分配，由 promise 和 future 的引用计数管理。
- 当 promise 和 future 的引用都释放后，共享状态被销毁。
- **`std::async` 返回的 future 持有共享状态的最后一个引用**——future 的析构函数会阻塞直到任务完成。

> [!warning] 共享状态的隐式同步
> `promise::set_value()` 和 `future::get()` 之间的同步由共享状态内部的 mutex + condition_variable 保证，**不需要用户额外加锁**。

---

## 二、代码示例

以下所有示例均可编译运行。编译命令统一为：

```bash
g++ -std=c++17 -pthread -o example example.cpp && ./example
```

### 2.1 `std::async` 基本用法与启动策略

```cpp
// async_basic.cpp
// 编译: g++ -std=c++17 -pthread -o async_basic async_basic.cpp && ./async_basic

#include <iostream>
#include <future>
#include <thread>
#include <chrono>
#include <vector>
#include <numeric>

int slow_square(int x) {
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    return x * x;
}

int main() {
    // === 策略 1: std::launch::async ===
    // 保证在新线程中执行
    auto f1 = std::async(std::launch::async, slow_square, 10);

    std::cout << "主线程：已提交任务，继续工作...\n";

    // get() 阻塞直到结果就绪
    int result1 = f1.get();
    std::cout << "async 结果: " << result1 << "\n";

    // === 策略 2: std::launch::deferred ===
    // 延迟执行——此时任务尚未开始
    auto f2 = std::async(std::launch::deferred, slow_square, 5);

    std::cout << "deferred future 已创建，但 slow_square(5) 尚未执行\n";

    // get() 触发执行——在调用者线程上运行
    int result2 = f2.get();
    std::cout << "deferred 结果: " << result2 << "\n";

    // === 批量并发: 并行计算多个平方 ===
    std::vector<std::future<int>> futures;
    for (int i = 1; i <= 8; ++i) {
        futures.push_back(std::async(std::launch::async, slow_square, i));
    }

    int sum = 0;
    for (auto& f : futures) {
        sum += f.get();
    }
    std::cout << "并行平方和: " << sum << "\n";

    return 0;
}
```

**预期输出：**

```
主线程：已提交任务，继续工作...
async 结果: 100
deferred future 已创建，但 slow_square(5) 尚未执行
deferred 结果: 25
并行平方和: 204
```

### 2.2 `std::promise` + `std::future`：一对一通信

```cpp
// promise_future.cpp
// 编译: g++ -std=c++17 -pthread -o promise_future promise_future.cpp && ./promise_future

#include <iostream>
#include <future>
#include <thread>
#include <chrono>
#include <string>

void producer(std::promise<std::string> prom) {
    // 模拟耗时计算
    std::this_thread::sleep_for(std::chrono::seconds(1));

    std::string result = "计算结果: 42";
    prom.set_value(result);  // 将结果传给共享状态

    std::cout << "[Producer] 结果已设置\n";
}

void consumer(std::future<std::string> fut) {
    std::cout << "[Consumer] 等待结果...\n";

    // get() 阻塞直到 promise 设置了值
    std::string result = fut.get();

    std::cout << "[Consumer] 收到: " << result << "\n";
}

int main() {
    // 创建 promise
    std::promise<std::string> prom;

    // 从 promise 获取 future
    std::future<std::string> fut = prom.get_future();

    // 启动生产者和消费者线程
    std::thread t1(producer, std::move(prom));
    std::thread t2(consumer, std::move(fut));

    t1.join();
    t2.join();

    return 0;
}
```

**预期输出：**

```
[Consumer] 等待结果...
[Producer] 结果已设置
[Consumer] 收到: 计算结果: 42
```

### 2.3 异常传播

```cpp
// exception_propagation.cpp
// 编译: g++ -std=c++17 -pthread -o exception_propagation exception_propagation.cpp && ./exception_propagation

#include <iostream>
#include <future>
#include <stdexcept>
#include <thread>
#include <exception>

// === 方式 1: std::async 中抛出异常 ===
void async_with_exception() {
    std::cout << "--- std::async 异常传播 ---\n";

    auto fut = std::async(std::launch::async, [] {
        throw std::runtime_error("async 任务内部错误");
        return 42;
    });

    try {
        int result = fut.get();  // 异常在这里重新抛出
        std::cout << "结果: " << result << "\n";  // 不会执行
    } catch (const std::runtime_error& e) {
        std::cout << "捕获到异常: " << e.what() << "\n";
    }
}

// === 方式 2: std::promise 显式设置异常 ===
void promise_set_exception() {
    std::cout << "\n--- std::promise 显式设置异常 ---\n";

    std::promise<int> prom;
    std::future<int> fut = prom.get_future();

    std::thread worker([&prom] {
        try {
            // 模拟失败的操作
            throw std::logic_error("promise 工作线程中的错误");
        } catch (...) {
            // 将当前异常捕获并传递给 future
            prom.set_exception(std::current_exception());
        }
    });

    try {
        int result = fut.get();
        std::cout << "结果: " << result << "\n";  // 不会执行
    } catch (const std::logic_error& e) {
        std::cout << "捕获到异常: " << e.what() << "\n";
    }

    worker.join();
}

// === 方式 3: broken_promise ===
void broken_promise_demo() {
    std::cout << "\n--- broken_promise 演示 ---\n";

    std::future<int> fut;
    {
        std::promise<int> prom;
        fut = prom.get_future();
        // promise 离开作用域被销毁，但未设置值 → broken_promise
    }

    try {
        int result = fut.get();  // 抛出 future_error
        std::cout << "结果: " << result << "\n";  // 不会执行
    } catch (const std::future_error& e) {
        std::cout << "future_error: " << e.what() << "\n";
        std::cout << "错误码: "
                  << (e.code() == std::future_errc::broken_promise
                          ? "broken_promise" : "其他")
                  << "\n";
    }
}

int main() {
    async_with_exception();
    promise_set_exception();
    broken_promise_demo();

    return 0;
}
```

**预期输出：**

```
--- std::async 异常传播 ---
捕获到异常: async 任务内部错误

--- std::promise 显式设置异常 ---
捕获到异常: promise 工作线程中的错误

--- broken_promise 演示 ---
future_error: broken promise
错误码: broken_promise
```

### 2.4 使用 `wait_for()` 实现超时

```cpp
// wait_for_timeout.cpp
// 编译: g++ -std=c++17 -pthread -o wait_for_timeout wait_for_timeout.cpp && ./wait_for_timeout

#include <iostream>
#include <future>
#include <thread>
#include <chrono>

// 模拟一个可能很慢的操作
int unreliable_computation(int seed) {
    if (seed % 3 == 0) {
        // 模拟超长任务
        std::this_thread::sleep_for(std::chrono::seconds(3));
        return -1;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    return seed * 10;
}

int main() {
    // 提交多个任务
    auto fast_task = std::async(std::launch::async, unreliable_computation, 1);
    auto slow_task = std::async(std::launch::async, unreliable_computation, 3);

    std::chrono::milliseconds timeout(500);

    // 等待 fast_task
    {
        auto status = fast_task.wait_for(timeout);
        if (status == std::future_status::ready) {
            std::cout << "fast_task 结果: " << fast_task.get() << "\n";
        } else if (status == std::future_status::timeout) {
            std::cout << "fast_task: 超时！\n";
        }
    }

    // 等待 slow_task
    {
        auto status = slow_task.wait_for(timeout);
        if (status == std::future_status::ready) {
            std::cout << "slow_task 结果: " << slow_task.get() << "\n";
        } else if (status == std::future_status::timeout) {
            std::cout << "slow_task: 超时！继续等待...\n";
            // 可以继续等待——get() 会一直阻塞到就绪
            int result = slow_task.get();
            std::cout << "slow_task 最终结果: " << result << "\n";
        }
    }

    // === deferred 任务的 wait_for ===
    auto deferred = std::async(std::launch::deferred, [] {
        return 99;
    });

    auto def_status = deferred.wait_for(std::chrono::seconds(0));
    if (def_status == std::future_status::deferred) {
        std::cout << "deferred 任务尚未开始执行——调用 get() 来触发\n";
        std::cout << "deferred 结果: " << deferred.get() << "\n";
    }

    return 0;
}
```

**预期输出：**

```
fast_task 结果: 10
slow_task: 超时！继续等待...
slow_task 最终结果: -1
deferred 任务尚未开始执行——调用 get() 来触发
deferred 结果: 99
```

---

## 三、练习

### 练习 1：并行数组求和（入门）

**目标**：用 `std::async` 将一个大数组分成多段并行求和。

**要求：**

1. 创建一个 `std::vector<int>` 包含 1,000,000 个元素（值 = 下标）。
2. 实现函数 `parallel_sum(const std::vector<int>& data, size_t num_threads)`：
   - 将数组分成 `num_threads` 个大致相等的段
   - 每段用 `std::async(std::launch::async, ...)` 提交一个求和任务
   - 收集所有 `std::future` 的结果并汇总
3. 验证：并行结果 == `std::accumulate` 的串行结果。
4. 测试 `num_threads = 1, 2, 4, 8` 时的结果正确性。

**参考框架：**

```cpp
// parallel_sum_exercise.cpp
// 编译: g++ -std=c++17 -pthread -o parallel_sum_exercise parallel_sum_exercise.cpp && ./parallel_sum_exercise

#include <iostream>
#include <future>
#include <vector>
#include <numeric>
#include <cassert>

long long parallel_sum(const std::vector<int>& data, size_t num_threads) {
    // TODO: 实现并行求和
    return 0;
}

int main() {
    std::vector<int> data(1'000'000);
    std::iota(data.begin(), data.end(), 1);  // 1, 2, 3, ...

    long long expected = std::accumulate(data.begin(), data.end(), 0LL);

    for (size_t t : {1, 2, 4, 8}) {
        long long result = parallel_sum(data, t);
        std::cout << "线程数 " << t << ": " << result
                  << (result == expected ? " ✓" : " ✗") << "\n";
    }

    return 0;
}
```

### 练习 2：用 promise/future 实现一次性事件（进阶）

**目标**：用 `std::promise<void>` + `std::future<void>` 实现一个线程间的轻量级信号。

**要求：**

1. 实现类 `OneShotEvent`：
   - `void wait()`：阻塞直到事件被触发
   - `bool wait_for(std::chrono::milliseconds timeout)`：带超时的等待，返回是否被触发
   - `void signal()`：触发事件（线程安全，只能调用一次）
   - `bool is_signaled() const`：检查事件是否已被触发
2. 用 mutex 保护 `signal()` 的竞态条件（多个线程可能同时调用 `signal()`，但只有第一个调用生效）。
3. 测试场景：主线程创建 3 个工作线程，每个线程执行不同的初始化任务，完成后调用 `signal()`。主线程等待事件，超时为 5 秒。

**提示**：`std::promise<void>` 可以通过 `set_value()` 发出信号（值本身为 `void`，只是通知机制）。

### 练习 3：异常安全的并行任务调度器（高级）

**目标**：实现一个能收集所有任务结果（包括异常）的并行任务调度器。

**要求：**

1. 实现函数 `run_all`：
   ```cpp
   template<typename F, typename... Args>
   std::vector<std::optional<typename std::invoke_result_t<F, Args...>>>
   run_all(size_t num_tasks, F&& func, Args&&... args);
   ```
2. 该函数运行 `num_tasks` 个相同的 `func(args...)` 并发执行，并收集结果。
3. 如果某个任务抛出异常，对应的结果位置填 `std::nullopt`，**不要**让异常传播到调用者。
4. 即使某些任务失败，也要等待所有任务完成后再返回结果。

**思考**：为什么必须存储 `std::future` 的返回值？如果不存储，会发生什么？（提示：参考常见陷阱 #1）

---

## 四、常见陷阱

### 陷阱 1：不存储 `std::async` 返回的 future

```cpp
// ❌ 错误：未来的析构函数会阻塞
{
    std::async(std::launch::async, [] {
        std::this_thread::sleep_for(std::chrono::seconds(10));
        std::cout << "完成\n";
    });
    // 临时 future 在这里被销毁——析构函数阻塞 10 秒！
    std::cout << "这行要等 10 秒才会打印\n";
}

// ✅ 正确：显式存储 future，控制销毁时机
{
    auto fut = std::async(std::launch::async, [] {
        std::this_thread::sleep_for(std::chrono::seconds(10));
        std::cout << "完成\n";
    });
    std::cout << "这行立即打印\n";
    fut.get();  // 在这里等待
}
```

> [!warning] `std::async` 返回的 future 是特殊的
> 标准规定：`std::async` 返回的 `std::future` 在其**析构函数中会阻塞**直到任务完成。
> 这与普通 `std::future`（从 `std::promise` 获取的）行为不同——普通 future 析构不阻塞。

### 陷阱 2：Deferred 任务从未被 get/wait

```cpp
// ❌ 错误：deferred 任务永远不会执行
{
    std::async(std::launch::deferred, [] {
        std::cout << "这行永远不会打印！\n";
    });
}   // future 析构——但 deferred 任务在析构时不执行

// ✅ 正确：必须显式等待
{
    auto fut = std::async(std::launch::deferred, [] {
        std::cout << "现在会打印了\n";
    });
    fut.wait();  // 或 fut.get()
}
```

### 陷阱 3：对同一个 future 多次调用 `get()`

```cpp
// ❌ 错误：get() 消费 future——第二次调用未定义行为
auto fut = std::async(std::launch::async, [] { return 42; });
int a = fut.get();   // OK: a = 42
int b = fut.get();   // 未定义行为！fut.valid() 现在是 false

// ✅ 正确：get() 之前检查 valid()，或使用 shared_future
if (fut.valid()) {
    int value = fut.get();
}
```

> [!warning] `get()` 是移动语义
> `get()` **移动**走结果。对于非平凡类型，这意味着被移动后的对象处于空状态。永远不要假设可以多次获取。

### 陷阱 4：Promise 在设置值之前被销毁

```cpp
// ❌ 错误：promise 析构但未 set_value
std::future<int> create_broken_future() {
    std::promise<int> prom;
    auto fut = prom.get_future();
    return fut;          // prom 在这里被销毁！→ broken_promise
    // fut.get() 会抛出 std::future_error
}

// ✅ 正确：确保 promise 在销毁前设置值或异常
std::future<int> create_valid_future() {
    std::promise<int> prom;
    auto fut = prom.get_future();
    prom.set_value(42);  // 设置值
    return fut;          // prom 可以安全销毁
}
```

### 陷阱 5：多线程下共享 promise 的竞态条件

```cpp
// ❌ 错误：多个线程对同一个 promise 调用 set_value
std::promise<int> prom;
auto fut = prom.get_future();

std::thread t1([&] { prom.set_value(1); });  // 竞态！
std::thread t2([&] { prom.set_value(2); });  // 竞态！

// ✅ 正确：promise 不是线程安全的——只有一个线程可以写入
// 使用 std::atomic 或 mutex 协调哪个线程获得写入权
std::promise<int> prom;
auto fut = prom.get_future();
std::once_flag flag;

std::thread t1([&] {
    std::call_once(flag, [&] { prom.set_value(1); });
});
std::thread t2([&] {
    std::call_once(flag, [&] { prom.set_value(2); });
});
```

---

## 五、扩展阅读

- [cppreference: std::async](https://en.cppreference.com/w/cpp/thread/async) — 完整的签名、异常列表、launch policy 详述
- [cppreference: std::future](https://en.cppreference.com/w/cpp/thread/future) — 所有成员函数的精确契约
- [cppreference: std::promise](https://en.cppreference.com/w/cpp/thread/promise) — `set_value_at_thread_exit` 等高级用法
- [C++ Standard: \[futures\] 章节](https://eel.is/c++draft/futures) — 共享状态的正式语义定义
- Anthony Williams, *C++ Concurrency in Action* (2nd Edition) — 第 4 章："Synchronizing concurrent operations"
- Scott Meyers, *Effective Modern C++* — Item 35: "Prefer task-based programming to thread-based"; Item 36: "Specify `std::launch::async` if asynchronicity is essential"; Item 38: "Be aware of varying thread handle destructor behavior"
- [Bartosz Milewski: Futures](https://bartoszmilewski.com/2009/03/03/broken-promises-c0x-futures/) — C++0x future 设计的早期深入讨论（2009 年，但共享状态的核心分析至今有效）
