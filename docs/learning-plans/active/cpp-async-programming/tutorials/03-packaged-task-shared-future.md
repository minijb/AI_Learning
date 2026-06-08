---
title: std::packaged_task 与 std::shared_future
updated: 2026-06-08
tags: [cpp, async, packaged_task, shared_future]
---

# std::packaged_task 与 std::shared_future

> [!abstract] 本节目标
> 理解 `std::packaged_task` 如何将可调用对象封装为「可投递的任务单元」，掌握它与 `std::async` 的本质区别；学会使用 `std::shared_future` 实现一对多结果广播。

前置知识：[[02-async-future-promise]]

---

## 一、概念

### 1.1 从 `std::async` 到 `std::packaged_task`

回顾 [[02-async-future-promise]]：`std::async` 帮你完成三件事——创建 `std::promise` 的内部共享状态、在一个线程（或线程池）中执行可调用对象、将结果写入共享状态。你拿到一个 `std::future`，但不能控制任务在哪个线程上跑、何时跑。

`std::packaged_task` 把控制权还给你：

```cpp
// std::async 的方式：你无法控制执行线程
auto future = std::async(std::launch::async, [] { return compute(); });

// std::packaged_task 的方式：你决定何时、在哪个线程执行
std::packaged_task<int()> task([] { return compute(); });
auto future = task.get_future();
// ... 稍后，把 task 交给某个线程执行
std::thread t(std::move(task));
t.join();
int result = future.get();
```

> [!note] 核心类比
> - `std::async` = 「帮我跑这个任务，跑完告诉我结果」，**执行时机不可控**。
> - `std::packaged_task` = 「这是任务包，附带取结果的凭条（future）。你拿走在任意线程跑，跑完后通过凭条取结果」，**执行时机完全由你控制**。

### 1.2 `std::packaged_task<R(Args...)>` 详解

```cpp
template <class> class packaged_task; // 未定义

template <class R, class... Args>
class packaged_task<R(Args...)>;  // 以函数签名 R(Args...) 为模板参数
```

核心接口：

| 成员 | 说明 |
|------|------|
| `packaged_task(F&& f)` | 构造，传入一个可调用对象 |
| `future<R> get_future()` | 获取关联的 future |
| `void operator()(Args... args)` | 执行任务，结果写入共享状态 |
| `void make_ready_at_thread_exit(Args... args)` | 执行任务，但仅在当前线程退出时标记 ready |
| `bool valid()` | 检查是否持有共享状态 |
| `void reset()` | 重置，重新绑定新的共享状态（**要求之前的 promise 已经满足**） |
| `void swap(packaged_task&)` | 交换两个 task 的共享状态 |

`packaged_task` 是 **move-only**（不可拷贝）。

### 1.3 `packaged_task` 作为线程池构建块

`packaged_task` 最关键的价值：它是任务调度器的基本单元。

```text
[提交任务] → packaged_task → [任务队列] → [工作线程取出并执行]
                 ↓
              future 返回给调用者
```

线程池中的典型模式：
1. 用户提交一个函数 → 封装为 `packaged_task`，取其 `future` 返回给用户
2. `packaged_task` 被推入线程安全的任务队列
3. 工作线程从队列取出 task 并调用 `operator()`
4. 用户的 `future.get()` 得到结果

### 1.4 `std::shared_future<R>`：让多个消费者等待同一个结果

`std::future::get()` 只能调用一次——它 **移动** 内部值。当多个线程需要等待同一个结果时，`std::shared_future` 登场。

```text
                     ┌──→ Thread A: sf.get() → 42
promise.set_value(42) ──→ shared_future ─┼──→ Thread B: sf.get() → 42
                     └──→ Thread C: sf.get() → 42
```

关键区别：

| 特性 | `std::future<T>` | `std::shared_future<T>` |
|------|------------------|------------------------|
| `get()` 返回值 | `T`（移动） | `const T&`（引用） |
| 可多次调用 | 否 | 是 |
| 线程安全 | 否（多线程调用 `get()` 为 data race） | 是（多线程可并发调用 `get()`、`wait()` 等） |
| 如何创建 | 从 `promise`/`packaged_task`/`async` | `future::share()` 或 `promise::get_shared_future()` |
| 拷贝 | 否（move-only） | 是（多个副本共享同一状态） |

从 `future` 获得 `shared_future`：

```cpp
std::promise<int> p;
std::future<int> fut = p.get_future();

// 方式一：future::share() — future 被移动，变为 invalid
std::shared_future<int> sf = fut.share();
assert(!fut.valid());

// 方式二：从 future 移动构造（RVO 通常消除移动）
std::shared_future<int> sf2 = std::move(fut);
```

> [!warning] `shared_future::get()` 返回 `const T&`
> 对于非 `void` 类型 `T`，`shared_future<T>::get()` 返回 `const T&`。如果你需要一个可修改的副本，需要显式拷贝。详见 [[#4.3 陷阱：shared_future::get() 返回 const 引用|常见陷阱]]。

### 1.5 何时用 `shared_future` 而非 `future`

- **一对多通知**：一个生产者计算完结果后，多个消费者线程需要读取同一结果（如配置加载完成、初始化完毕信号）。
- **条件变量替代**：`shared_future` 的 `wait()` + `get()` 可作为轻量级的一次性条件变量。

> [!tip] 日常场景
> 大多数情况下 `std::future` 就够用了。`shared_future` 主要用于广播型场景，比如：
> - 主线程加载完全局配置 → 所有工作线程通过 `shared_future` 等待配置就绪
> - 数据库连接池初始化完成 → 所有请求处理线程收到就绪信号

---

## 二、代码示例

> [!note] 编译说明
> 所有示例需要 C++17 或以上。编译命令（以第一个为例）：
> ```bash
> g++ -std=c++17 -pthread -O2 01_packaged_task_basic.cpp -o 01_packaged_task_basic
> ```
> Windows 下 MSVC 无需 `-pthread`，直接 `cl /EHsc /std:c++17 01_packaged_task_basic.cpp` 即可。

### 2.1 `packaged_task` 配合手动线程

**文件：`01_packaged_task_basic.cpp`**

```cpp
#include <iostream>
#include <future>
#include <thread>
#include <string>
#include <chrono>

// 一个耗时计算
int compute_answer(const std::string& question) {
    std::cout << "[worker] 正在计算: " << question << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    return 42;
}

int main() {
    // 1. 创建 packaged_task，包装 compute_answer
    std::packaged_task<int(const std::string&)> task(compute_answer);

    // 2. 获取 future — 这是"凭条"
    std::future<int> result = task.get_future();

    // 3. 将 task 交给线程执行（packaged_task 不可拷贝，必须移动）
    std::thread worker(std::move(task), "生命、宇宙以及一切的意义？");

    // 4. 主线程可以干别的事
    std::cout << "[main] 任务已提交，等待结果..." << std::endl;

    // 5. 等待并获取结果
    int answer = result.get();
    std::cout << "[main] 答案是: " << answer << std::endl;

    worker.join();
    return 0;
}
```

**关键点**：
- `packaged_task` 是 move-only：交给线程时必须 `std::move`
- `get_future()` 必须在 task 被移动前调用，否则 task 已空
- `future.get()` 会阻塞直到任务完成

### 2.2 简易线程池

**文件：`02_simple_thread_pool.cpp`**

下面是一个最小但完整的线程池，展示 `packaged_task` 作为任务投递机制：

```cpp
#include <iostream>
#include <future>
#include <thread>
#include <vector>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <type_traits>

class SimpleThreadPool {
public:
    explicit SimpleThreadPool(size_t num_threads) {
        for (size_t i = 0; i < num_threads; ++i) {
            workers_.emplace_back([this] {
                for (;;) {
                    std::function<void()> task;
                    {
                        std::unique_lock lock(queue_mutex_);
                        cv_.wait(lock, [this] { return stop_ || !tasks_.empty(); });
                        if (stop_ && tasks_.empty()) return;
                        task = std::move(tasks_.front());
                        tasks_.pop();
                    }
                    task();
                }
            });
        }
    }

    ~SimpleThreadPool() {
        {
            std::lock_guard lock(queue_mutex_);
            stop_ = true;
        }
        cv_.notify_all();
        for (auto& t : workers_) {
            if (t.joinable()) t.join();
        }
    }

    // 提交任务，返回 future
    template <typename F, typename... Args>
    auto submit(F&& f, Args&&... args)
        -> std::future<typename std::invoke_result_t<F, Args...>>
    {
        using return_type = typename std::invoke_result_t<F, Args...>;

        // 将可调用对象包装为 packaged_task
        auto task = std::make_shared<std::packaged_task<return_type()>>(
            std::bind(std::forward<F>(f), std::forward<Args>(args)...)
        );

        std::future<return_type> result = task->get_future();

        {
            std::lock_guard lock(queue_mutex_);
            if (stop_) {
                throw std::runtime_error("submit on stopped pool");
            }
            // 将 packaged_task 作为 std::function<void()> 入队
            tasks_.emplace([task] { (*task)(); });
        }
        cv_.notify_one();
        return result;
    }

private:
    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;
    std::mutex queue_mutex_;
    std::condition_variable cv_;
    bool stop_ = false;
};

// ====== 使用示例 ======
int heavy_compute(int n) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    return n * n;
}

int main() {
    SimpleThreadPool pool(4);

    // 提交多个任务，收集 future
    std::vector<std::future<int>> results;
    for (int i = 1; i <= 10; ++i) {
        results.push_back(pool.submit(heavy_compute, i));
    }

    // 等待并输出结果
    for (int i = 0; i < static_cast<int>(results.size()); ++i) {
        std::cout << "heavy_compute(" << (i + 1) << ") = "
                  << results[i].get() << std::endl;
    }

    return 0; // 析构时自动 join
}
```

**设计要点**：
- `submit` 内部用 `std::make_shared<std::packaged_task<...>>` 创建 task，通过 `shared_ptr` 在队列中传递（避免 `packaged_task` 不可拷贝的问题）
- `tasks_` 队列类型擦除为 `std::function<void()>`，lambda 捕获 `shared_ptr<task>` 并调用 `operator()`
- `submit` 立即返回 `future`，调用者可以稍后 `get()`

### 2.3 `shared_future` 广播结果

**文件：`03_shared_future_broadcast.cpp`**

场景：一个线程加载配置，多个工作线程等待配置就绪后才开始工作。

```cpp
#include <iostream>
#include <future>
#include <thread>
#include <vector>
#include <string>
#include <chrono>
#include <sstream>
#include <mutex>

// 模拟：加载全局配置（耗时操作）
std::string load_config() {
    std::cout << "[loader] 开始加载配置..." << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(800));
    return R"({"db": "192.168.1.100:3306", "pool_size": 8})";
}

// 工作线程：等待配置就绪，然后开始工作
void worker(int id, std::shared_future<std::string> config_future) {
    std::cout << "[worker " << id << "] 等待配置就绪..." << std::endl;

    // 阻塞直到配置加载完成
    const std::string& config = config_future.get();

    // 所有 worker 拿到的是同一份 config 的 const 引用
    std::ostringstream oss;
    oss << "[worker " << id << "] 获取到配置: " << config
        << " — 开始工作" << std::endl;
    std::cout << oss.str();

    std::this_thread::sleep_for(std::chrono::milliseconds(300));
}

int main() {
    // 创建 promise 和 shared_future
    std::promise<std::string> config_promise;
    std::shared_future<std::string> config_future =
        config_promise.get_future().share();

    // 启动多个工作线程，每个持有 shared_future 的副本
    constexpr int kWorkerCount = 5;
    std::vector<std::thread> workers;
    for (int i = 0; i < kWorkerCount; ++i) {
        workers.emplace_back(worker, i, config_future); // shared_future 可以拷贝！
    }

    // 主线程加载配置
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    config_promise.set_value(load_config());

    // 等待所有工作线程完成
    for (auto& t : workers) t.join();

    std::cout << "[main] 所有 worker 已完成。" << std::endl;
    return 0;
}
```

**运行输出示例**：
```
[loader] 开始加载配置...
[worker 0] 等待配置就绪...
[worker 1] 等待配置就绪...
[worker 2] 等待配置就绪...
[worker 3] 等待配置就绪...
[worker 4] 等待配置就绪...
[worker 0] 获取到配置: {"db": "192.168.1.100:3306", "pool_size": 8} — 开始工作
[worker 1] 获取到配置: {"db": "192.168.1.100:3306", "pool_size": 8} — 开始工作
...
```

**关键点**：
- `shared_future` 可以拷贝（与 `future` 不同），每个 worker 获得一个副本
- 多个线程并发调用 `shared_future::get()` 是线程安全的
- `get()` 返回 `const T&`，所有线程看到同一份数据的相同引用

---

## 三、练习

### 练习 1（基础）：用 `packaged_task` 包装已有代码

**场景**：你有一段同步函数，需要改为异步调用。

```cpp
// 已有的同步函数 — 不要修改它
std::string fetch_data_from_db(int id) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    return "Record #" + std::to_string(id); // 模拟 DB 查询
}
```

**要求**：
1. 用 `packaged_task` 包装 `fetch_data_from_db`
2. 在一个单独的 `std::thread` 中执行 task
3. 主线程在此期间打印 `"主线程在做其他事..."`
4. 主线程通过 `future.get()` 拿到结果并打印 `"获取到: Record #42"`

**提示**：模板参数是 `std::packaged_task<std::string(int)>`。

### 练习 2（进阶）：实现 submit 支持任意返回类型

扩展 [[#2.2 简易线程池|2.2 节的线程池]]，添加以下功能：

1. `submit` 方法返回 `std::future<R>`，其中 `R` 是任务函数的返回类型（已实现，但请理解它并手写一版）
2. 写一个测试：提交 5 个不同类型的任务（返回 `int`、`double`、`std::string`、`void`），验证 `future.get()` 得到正确结果
3. **（可选）** 支持任务的优先级队列

### 练习 3（综合）：`shared_future` 实现阶段性屏障

**场景**：有一个多阶段流水线。阶段 1 的结果需要被阶段 2 的所有线程消费。

```
Phase 1: 计算输入数据 → shared_future<Data>
                              ↓
Phase 2: 3 个 worker 并发处理 Data → 各有自己的结果
```

**要求**：
1. 用一个 `std::promise` 和一个 `shared_future` 实现阶段间同步
2. Phase 1 在单独线程中计算 `Data`（一个包含 `std::vector<int>` 的结构体）
3. Phase 2 的 3 个 worker 通过 `shared_future` 等待并拿到 `Data`，各自处理一部分（如：worker 0 处理 `[0, n/3)`，worker 1 处理 `[n/3, 2n/3)`，等等）
4. 主线程等待所有 phase 完成

---

## 四、常见陷阱

### 4.1 `packaged_task` 被移动后变成无效状态

```cpp
std::packaged_task<int()> task([] { return 42; });
auto f1 = task.get_future();

std::thread t(std::move(task));  // task 被移动，现在 task.valid() == false
t.join();

// ❌ 错误：task 已经无效
// task();  

// ✅ 正确：通过之前获取的 future 拿结果
int result = f1.get();
```

> [!warning] 铁律
> `packaged_task` 在被 `std::move` 之后处于 **valid-but-unspecified** 状态。你只能对它调用 `valid()`（返回 `false`）、析构、或赋值一个新的 task。在移动之前就要调用 `get_future()`。

### 4.2 `packaged_task` 必须被调用，future 才会就绪

```cpp
std::packaged_task<int()> task([] { return 42; });
auto f = task.get_future();

// 忘记调用 task() 或其等价物
// task 在此作用域结束时析构 → future 的共享状态存储了 std::future_error
//                          （broken_promise）

// ❌ 下面这行会抛出 std::future_error: broken_promise
// int result = f.get();
```

**发生了什么**：`packaged_task` 析构时，如果它持有的共享状态尚未 ready，析构函数会存储一个 `std::future_error`（错误码 `broken_promise`），导致后续 `future.get()` 抛出异常。

```cpp
// ✅ 正确：确保 task 被执行
std::packaged_task<int()> task([] { return 42; });
auto f = task.get_future();
task(); // 必须在析构前调用
int result = f.get();
```

### 4.3 `shared_future::get()` 返回 `const` 引用

这是最容易被忽略的语义差异：

```cpp
std::promise<std::vector<int>> p;
std::shared_future<std::vector<int>> sf = p.get_future().share();

p.set_value({1, 2, 3, 4, 5});

// get() 返回 const std::vector<int>&，不是移动
const std::vector<int>& ref = sf.get();

// 如果你想要一个可修改的副本，需要显式拷贝
std::vector<int> my_copy = sf.get(); // 拷贝构造

// shared_future<void> 的 get() 返回 void（无此问题）
```

> [!warning] 与 `std::future` 的差异
> `std::future<T>::get()` 在非 `void` 时返回 `T`（移动语义），但 `std::shared_future<T>::get()` 返回 `const T&`。因为 `shared_future` 允许多次调用，不能移动。

### 4.4 `packaged_task::reset()` 的陷阱

`reset()` 会丢弃旧的共享状态并创建新的。但 **旧的共享状态必须已经 ready**：

```cpp
std::packaged_task<int()> task([] { return 42; });
auto f1 = task.get_future();
task(); // 执行，使共享状态 ready
int r = f1.get(); // 取走结果

task.reset(); // OK — 旧状态已经 ready
auto f2 = task.get_future();
task(); // 再次执行
int r2 = f2.get();
```

如果在旧状态未 ready 时 `reset()`，旧的 promise 被销毁，产生 `broken_promise`：

```cpp
std::packaged_task<int()> task([] { return 42; });
auto f1 = task.get_future();
// 没有调用 task()
task.reset(); // ❌ 旧状态未 ready，future 将携带 broken_promise
```

### 4.5 `shared_future` 的 wait 与条件变量对比

`shared_future` 适合**一次性通知**。如果通知需要重复多次（如生产者-消费者队列），仍然应该使用 `std::condition_variable`。`shared_future` 不能被「重置」来等待第二个值。

```cpp
// shared_future 适用场景：一次性初始化信号
std::shared_future<Config> config_ready = ...;
// ✅ 各线程等待一次配置加载

// shared_future 不适用场景：反复通知
// ❌ producer 每生产一个 item 就 broadcast → 用 condition_variable
```

---

## 五、扩展阅读

- [[02-async-future-promise]] — 本节的前置知识，`std::promise` 和 `std::future` 的基础
- [[12-advanced-patterns]] — 进阶模式：线程池设计、任务调度器、取消机制
- [cppreference: `std::packaged_task`](https://en.cppreference.com/w/cpp/thread/packaged_task) — 完整 API 文档
- [cppreference: `std::shared_future`](https://en.cppreference.com/w/cpp/thread/shared_future) — 完整 API 文档
- **C++ Concurrency in Action (2nd Edition)** — Anthony Williams：第 4 章详细讨论 `packaged_task` 在线程池中的应用，第 4.2.3 节专门讲解 `shared_future`
- [Bartosz Milewski: Broken promises–C++0x futures](https://bartoszmilewski.com/2009/03/03/broken-promises-c0x-futures/) — 深入 `future`/`promise` 的设计哲学（2009 年的博客但仍然是经典）
