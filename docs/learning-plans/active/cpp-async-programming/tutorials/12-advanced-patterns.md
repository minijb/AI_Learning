---
title: 进阶模式 — 线程池、调度器与取消
updated: 2026-06-08
tags: [cpp, async, thread-pool, scheduler, cancellation]
---

# 进阶模式：线程池、调度器与取消

> 本教程覆盖工业级异步编程的四个核心主题：线程池设计、任务调度、取消机制、以及结构化并发。完成本教程后，你将能设计和实现一个完整的异步任务执行框架。

---

## 一、概念

### 1.1 线程池设计

线程池是最基础的异步执行器。核心设计权衡：

**固定大小 vs 动态大小**

| 策略 | 优点 | 缺点 |
|------|------|------|
| 固定大小 | 无创建/销毁开销，资源可预测 | 任务突发时可能排队过长 |
| 动态大小 | 弹性应对负载变化 | 线程创建延迟，可能耗尽资源 |

生产环境通常使用**有界动态池**：设置最小和最大线程数，空闲线程在超时后回收。

**工作窃取 vs 共享队列**

```
共享队列（Shared Queue）：
  所有线程从同一个队列取任务
  + 实现简单，负载自然均衡
  - 队列成为竞争热点（contention），高并发下吞吐量下降

工作窃取（Work Stealing）：
  每个线程有自己的本地队列，线程优先处理本地任务
  本地队列空时，从其他线程的队列"窃取"任务
  + 极大减少竞争，缓存友好
  - 实现复杂，窃取策略需调优
```

工作窃取是 C++ 标准库 `std::execution` 并行算法、Intel TBB、Java ForkJoinPool 的共同选择。

**Fork-Join 并行**

递归地将任务拆分（fork）为子任务，子任务完成后再合并（join）结果。典型场景：分治算法、并行 `std::reduce`。

### 1.2 任务调度

调度器决定"哪个任务在哪个线程上何时执行"。

- **FIFO 调度** — 最简单的先入先出队列，公平但无优先级概念
- **优先级调度** — 每个任务携带优先级，高优先级任务优先执行。注意**优先级反转**和**饥饿**问题
- **截止时间调度** — 任务有 `deadline`，调度器按最早截止时间优先（EDF）执行。适用于实时系统
- **NUMA 感知调度** — 在多路服务器上，调度器尽量将任务分配到"靠近"其数据的 NUMA 节点上，减少跨节点内存访问

> [!tip] 调度器是"策略"层
> 好的线程池设计将**执行机制**（线程管理、队列）与**调度策略**（优先级、亲和性）分离，通过可插拔的调度器接口实现。

### 1.3 取消机制（C++20 `std::stop_token`）

异步任务的取消是一个经典的分布式系统问题：任务可能在等待 I/O、在队列中排队、或正在执行中。

C++20 引入 `std::stop_token` / `std::stop_source` / `std::stop_callback` 三位一体：

```
stop_source ──创建──▶ stop_token ──传递给──▶ 异步任务
    │                                           │
    │ .request_stop()                           │ .stop_requested()
    ▼                                           ▼
  发出取消信号                              检测取消并退出
                   stop_callback
                   注册取消时的回调
```

**协作式取消**：取消是"请求"，不是"强制"。任务必须主动检查 `stop_token.stop_requested()` 并自行退出。这与 `pthread_cancel` 的强制终止有本质区别——后者可能导致资源泄漏和不变量破坏。

**RAII 取消注册**：`std::stop_callback` 在构造时注册回调，析构时自动注销。利用 RAII 可以安全地"在取消时做一些清理工作"。

```cpp
std::stop_callback cb(token, [&] {
    // 取消时关闭 socket、释放资源等
    running_io_context.stop();
});
```

> [!warning] 取消不是免费的
> 每个协程挂起点之后，都应该检查 `stop_token`。漏掉检查意味着任务可能在你"已请求取消"之后继续执行很长时间。

### 1.4 异步错误处理

同步代码中异常沿调用栈传播。异步代码的调用栈在挂起点被"切断"，异常传播机制需要显式设计。

- **通过 `std::future` 传播** — 任务中抛出的异常被 `future` 捕获，在 `get()` 时重新抛出
- **通过协程 promise_type 传播** — `promise_type::unhandled_exception()` 捕获异常，存储在 `future`/`task` 的结果中
- **`std::expected<T, E>`（C++23）** — 将错误作为返回值的一部分，避免异常开销，适合性能敏感路径
- **回退与重试** — 任务失败后自动重试 N 次（通常带指数退避），或降级到备用路径

```cpp
// C++23 风格
std::expected<Result, Error> async_compute(Args... args);

auto outcome = co_await async_compute(data);
if (!outcome) {
    // 处理错误
    co_return outcome.error();
}
```

### 1.5 结构化并发

结构化并发（Structured Concurrency）的核心思想：**异步工作的生命周期不应超过其发起者**。

```
parent scope
├── task A ──────┐
├── task B ──────┤ 所有子任务
├── task C ──────┘ 在 scope 结束时
│                  被 join 或 cancel
▼
scope 析构 → 确保所有子任务已完成
```

类比：栈上对象的析构保证资源释放；结构化并发保证**并发工作的生命周期被限定在明确的 scope 内**。

- `when_all` — 等待所有子任务完成
- `when_any` — 任一子任务完成即返回，其余取消
- Async Scope — 析构时自动取消并等待所有未完成的子任务

> [!important] 为什么重要
> 没有结构化并发，你很容易写出"fire and forget"任务——它们可能在父任务已销毁后仍访问悬空引用，导致难以调试的 use-after-free。

---

## 二、代码示例

### 2.1 简单的固定大小线程池

**编译**：支持 C++20 的编译器（需要 `std::jthread` 和 `std::stop_token`）。

```bash
g++ -std=c++20 -O2 thread_pool.cpp -o thread_pool
```

```cpp
#include <iostream>
#include <vector>
#include <queue>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <future>
#include <stop_token>

class ThreadPool {
public:
    explicit ThreadPool(size_t num_threads) {
        for (size_t i = 0; i < num_threads; ++i) {
            workers_.emplace_back([this](std::stop_token st) {
                while (!st.stop_requested()) {
                    std::function<void()> task;
                    {
                        std::unique_lock lock(queue_mutex_);
                        cv_.wait(lock, [&] {
                            return st.stop_requested() || !tasks_.empty();
                        });
                        if (st.stop_requested() && tasks_.empty()) return;
                        task = std::move(tasks_.front());
                        tasks_.pop();
                    }
                    task();
                }
            });
        }
    }

    ~ThreadPool() {
        for (auto& w : workers_) {
            w.request_stop();
        }
        cv_.notify_all();
        // jthread 析构自动 join
    }

    template<typename F, typename... Args>
    auto submit(F&& f, Args&&... args)
        -> std::future<std::invoke_result_t<F, Args...>>
    {
        using ReturnType = std::invoke_result_t<F, Args...>;
        auto task = std::make_shared<std::packaged_task<ReturnType()>>(
            std::bind_front(std::forward<F>(f), std::forward<Args>(args)...)
        );
        std::future<ReturnType> result = task->get_future();
        {
            std::lock_guard lock(queue_mutex_);
            tasks_.emplace([task] { (*task)(); });
        }
        cv_.notify_one();
        return result;
    }

    size_t pending() const {
        std::lock_guard lock(queue_mutex_);
        return tasks_.size();
    }

private:
    std::vector<std::jthread> workers_;
    std::queue<std::function<void()>> tasks_;
    mutable std::mutex queue_mutex_;
    std::condition_variable_any cv_;
};

// === 使用示例 ===
int main() {
    ThreadPool pool(4);

    auto f1 = pool.submit([](int x) { return x * x; }, 10);
    auto f2 = pool.submit([](int a, int b) { return a + b; }, 3, 7);
    auto f3 = pool.submit([] {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        return std::string("done");
    });

    std::cout << "10^2 = " << f1.get() << "\n";      // 100
    std::cout << "3+7 = "  << f2.get() << "\n";      // 10
    std::cout << "f3 = "   << f3.get() << "\n";      // done
    std::cout << "Pending: " << pool.pending() << "\n"; // 0
}
```

**预期输出**：

```
10^2 = 100
3+7 = 10
f3 = done
Pending: 0
```

> [!note] 设计要点
> - 使用 `std::jthread` 自动管理线程生命周期——析构时自动 `join`
> - `std::condition_variable_any` 配合 `std::stop_token` 实现可中断的等待
> - `std::packaged_task` 包装任意可调用对象，返回 `std::future`
> - 析构时先 `request_stop()`，再 `notify_all()` 唤醒所有等待线程

---

### 2.2 `std::stop_token` 取消示例

**编译**：

```bash
g++ -std=c++20 -O2 cancellation.cpp -o cancellation
```

```cpp
#include <iostream>
#include <thread>
#include <chrono>
#include <stop_token>
#include <syncstream>  // C++20

// 模拟一个可取消的长时间计算
void search_in_range(std::stop_token token, int start, int end) {
    for (int i = start; i < end; ++i) {
        // 每次迭代检查取消
        if (token.stop_requested()) {
            std::osyncstream(std::cout)
                << "[thread " << std::this_thread::get_id()
                << "] 在 i=" << i << " 时收到取消请求，退出\n";
            return;
        }

        // 模拟耗时操作
        std::this_thread::sleep_for(std::chrono::milliseconds(50));

        // 找到"结果"
        if (i == 42) {
            std::osyncstream(std::cout)
                << "[thread " << std::this_thread::get_id()
                << "] 找到答案: " << i << "\n";
        }
    }
}

int main() {
    // stop_source 是取消的"发射端"
    std::stop_source source;

    // 从 source 获取 token 并传给线程
    std::jthread worker(search_in_range, source.get_token(), 0, 10000);

    // 主线程等待 300ms 后取消
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    std::cout << "主线程: 请求取消\n";
    source.request_stop();

    // jthread 析构自动 join

    // === 带 stop_callback 的 RAII 清理 ===
    std::stop_source source2;
    {
        std::stop_callback cb(source2.get_token(), [] {
            std::cout << "回调: 清理资源（关闭 socket、释放锁等）\n";
        });
        std::cout << "stop_callback 已注册（在作用域内）\n";
        source2.request_stop(); // 触发回调
    }
    std::cout << "stop_callback 已析构（离开作用域）\n";

    // 再次请求——回调已不存在，不会触发
    source2.request_stop();
    std::cout << "再次请求停止，无回调触发\n";
}
```

**预期输出**（实际 i 值可能略有不同）：

```
主线程: 请求取消
[thread ...] 在 i=... 时收到取消请求，退出
stop_callback 已注册（在作用域内）
回调: 清理资源（关闭 socket、释放锁等）
stop_callback 已析构（离开作用域）
再次请求停止，无回调触发
```

> [!tip] 三重角色
> - `std::stop_source` — 取消信号的**发起者**（只有它能 `request_stop()`）
> - `std::stop_token` — 取消信号的**观察者**（查询 `stop_requested()`）
> - `std::stop_callback` — 取消时的**回调注册**（RAII 生命周期）

---

### 2.3 带指数退避的协程重试

**编译**：需要 C++20 协程支持。

```bash
g++ -std=c++20 -O2 retry_coro.cpp -o retry_coro
```

```cpp
#include <iostream>
#include <chrono>
#include <random>
#include <coroutine>
#include <optional>
#include <thread>
#include <stop_token>

// ========== 简易 Task 类型 ==========
template<typename T>
struct Task {
    struct promise_type {
        std::optional<T> result;
        std::exception_ptr error;

        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_value(T v) { result = std::move(v); }
        void unhandled_exception() { error = std::current_exception(); }
    };

    using handle_type = std::coroutine_handle<promise_type>;
    handle_type handle;

    explicit Task(handle_type h) : handle(h) {}
    ~Task() { if (handle) handle.destroy(); }
    Task(Task&& other) noexcept : handle(std::exchange(other.handle, nullptr)) {}
    Task& operator=(Task&& other) noexcept {
        if (this != &other) { if (handle) handle.destroy(); handle = std::exchange(other.handle, nullptr); }
        return *this;
    }
    Task(const Task&) = delete;

    T get() {
        if (handle.promise().error) std::rethrow_exception(handle.promise().error);
        return std::move(*handle.promise().result);
    }
};

// ========== 可取消的 sleep ==========
struct SleepAwaitable {
    std::chrono::milliseconds duration;
    std::stop_token token;

    bool await_ready() { return token.stop_requested(); }
    void await_suspend(std::coroutine_handle<>) {
        // 简单实现：轮询检查
        auto start = std::chrono::steady_clock::now();
        while (!token.stop_requested() &&
               std::chrono::steady_clock::now() - start < duration) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }
    void await_resume() {}
};

// ========== 模拟可能失败的操作 ==========
std::mt19937 rng{std::random_device{}()};

bool try_connect(int attempt) {
    // 模拟 70% 失败率
    if (std::uniform_int_distribution<>(1, 10)(rng) <= 7) {
        throw std::runtime_error("连接失败（尝试 #" + std::to_string(attempt) + "）");
    }
    return true;
}

// ========== 带指数退避的重试协程 ==========
Task<bool> connect_with_retry(std::stop_token token,
                                int max_retries = 5,
                                std::chrono::milliseconds base_delay = std::chrono::milliseconds(100))
{
    for (int attempt = 1; attempt <= max_retries; ++attempt) {
        // 挂起前检查取消
        if (token.stop_requested()) {
            std::cout << "[取消] 检测到取消请求，停止重试\n";
            co_return false;
        }

        try {
            bool ok = try_connect(attempt);
            std::cout << "[成功] 第 " << attempt << " 次尝试成功\n";
            co_return ok;
        } catch (const std::exception& e) {
            std::cout << "[失败] " << e.what() << "\n";
        }

        if (attempt < max_retries) {
            // 指数退避: delay = base * 2^(attempt-1) ± jitter
            auto delay = base_delay * (1 << (attempt - 1));
            auto jitter = std::chrono::milliseconds(
                std::uniform_int_distribution<>(0, 50)(rng));
            std::cout << "[等待] " << (delay + jitter).count() << "ms 后重试...\n";
            co_await SleepAwaitable{delay + jitter, token};

            // 挂起后再次检查取消
            if (token.stop_requested()) {
                std::cout << "[取消] sleep 期间收到取消请求\n";
                co_return false;
            }
        }
    }
    std::cout << "[放弃] 已达最大重试次数\n";
    co_return false;
}

int main() {
    std::stop_source stop_src;

    // 正常重试
    std::cout << "=== 场景 1: 正常重试 ===\n";
    auto task1 = connect_with_retry(stop_src.get_token(), 5);
    bool result1 = task1.get();
    std::cout << "结果: " << (result1 ? "已连接" : "未连接") << "\n\n";

    // 超时取消
    std::cout << "=== 场景 2: 超时取消 ===\n";
    auto task2 = connect_with_retry(stop_src.get_token(), 10,
                                      std::chrono::milliseconds(200));
    std::thread cancel_thread([&stop_src] {
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        stop_src.request_stop();
    });
    bool result2 = task2.get();
    cancel_thread.join();
    std::cout << "结果: " << (result2 ? "已连接" : "未连接") << "\n";
}
```

**预期输出**（随机，大致示意）：

```
=== 场景 1: 正常重试 ===
[失败] 连接失败（尝试 #1）
[等待] 100ms 后重试...
[失败] 连接失败（尝试 #2）
[等待] 200ms 后重试...
[成功] 第 3 次尝试成功
结果: 已连接

=== 场景 2: 超时取消 ===
[失败] 连接失败（尝试 #1）
[等待] 200ms 后重试...
[失败] 连接失败（尝试 #2）
[等待] 400ms 后重试...
[取消] sleep 期间收到取消请求
结果: 未连接
```

> [!note] 指数退避公式
> `delay = base_delay × 2^(attempt - 1)`
> 第 1 次: `100ms`，第 2 次: `200ms`，第 3 次: `400ms`，第 4 次: `800ms`，第 5 次: `1600ms`
> 添加随机 jitter（抖动）防止**惊群效应**（thundering herd）。

---

### 2.4 结构化并发 — `when_all` 模式

**编译**：

```bash
g++ -std=c++20 -O2 structured_concurrency.cpp -o structured_concurrency
```

```cpp
#include <iostream>
#include <vector>
#include <thread>
#include <future>
#include <chrono>
#include <algorithm>
#include <numeric>
#include <syncstream>

// ========== 任务组：等待所有任务完成 ==========
template<typename... Futures>
auto when_all(Futures&... futures) {
    return std::tuple<Futures&...>(futures...);
}

// 辅助：等待 tuple 中所有 future
namespace detail {
    template<typename Tuple, size_t... Is>
    void wait_all_impl(Tuple& t, std::index_sequence<Is...>) {
        (std::get<Is>(t).wait(), ...);
    }
}

template<typename... Futures>
void wait_all(std::tuple<Futures&...> group) {
    detail::wait_all_impl(group, std::make_index_sequence<sizeof...(Futures)>{});
}

// ========== 结构化并发 Scope ==========
class AsyncScope {
public:
    ~AsyncScope() {
        // 析构时等待所有已提交的任务
        for (auto& f : futures_) {
            if (f.valid()) {
                f.wait();
            }
        }
    }

    AsyncScope(const AsyncScope&) = delete;
    AsyncScope& operator=(const AsyncScope&) = delete;
    AsyncScope(AsyncScope&&) = delete;

    // 提交任务到 scope
    template<typename F, typename... Args>
    void spawn(F&& f, Args&&... args) {
        auto task = std::async(std::launch::async,
            std::forward<F>(f), std::forward<Args>(args)...);
        futures_.push_back(std::move(task));
    }

    size_t running() const { return futures_.size(); }

private:
    std::vector<std::future<void>> futures_;
};

// ========== 使用示例 ==========
int compute_part(int part_id, int workload_ms) {
    std::osyncstream(std::cout)
        << "[Part " << part_id << "] 开始（耗时 " << workload_ms << "ms）\n";
    std::this_thread::sleep_for(std::chrono::milliseconds(workload_ms));
    std::osyncstream(std::cout)
        << "[Part " << part_id << "] 完成\n";
    return part_id * 100;
}

int main() {
    std::cout << "=== 模式 1: when_all ===\n";
    {
        auto f1 = std::async(std::launch::async, [] { return compute_part(1, 100); });
        auto f2 = std::async(std::launch::async, [] { return compute_part(2, 150); });
        auto f3 = std::async(std::launch::async, [] { return compute_part(3, 80); });

        // 等待所有完成
        auto group = when_all(f1, f2, f3);
        wait_all(group);

        // 安全获取结果
        int total = f1.get() + f2.get() + f3.get();
        std::cout << "总和: " << total << "\n"; // 100 + 200 + 300 = 600
    }

    std::cout << "\n=== 模式 2: AsyncScope ===\n";
    {
        AsyncScope scope;
        scope.spawn([] { compute_part(10, 200); });
        scope.spawn([] { compute_part(20, 120); });
        scope.spawn([] { compute_part(30, 150); });
        std::cout << "Scope 中有 " << scope.running() << " 个任务\n";
        // scope 析构时自动等待所有任务
    }
    std::cout << "Scope 已析构，所有任务已完成\n";

    std::cout << "\n=== 模式 3: when_all + 结果汇总 ===\n";
    {
        std::vector<std::future<int>> parts;
        for (int i = 0; i < 5; ++i) {
            parts.push_back(std::async(std::launch::async, [i] {
                std::this_thread::sleep_for(std::chrono::milliseconds(50 + i * 20));
                return i * i;
            }));
        }

        // 等待全部完成并收集结果
        std::vector<int> results;
        for (auto& f : parts) {
            results.push_back(f.get());
        }

        int sum = std::accumulate(results.begin(), results.end(), 0);
        std::cout << "平方和 (0²+1²+2²+3²+4²) = " << sum << "\n"; // 0+1+4+9+16 = 30
    }
}
```

**预期输出**：

```
=== 模式 1: when_all ===
[Part 1] 开始（耗时 100ms）
[Part 2] 开始（耗时 150ms）
[Part 3] 开始（耗时 80ms）
[Part 3] 完成
[Part 1] 完成
[Part 2] 完成
总和: 600

=== 模式 2: AsyncScope ===
Scope 中有 3 个任务
[Part 10] 开始（耗时 200ms）
[Part 20] 开始（耗时 120ms）
[Part 30] 开始（耗时 150ms）
[Part 20] 完成
[Part 30] 完成
[Part 10] 完成
Scope 已析构，所有任务已完成

=== 模式 3: when_all + 结果汇总 ===
平方和 (0²+1²+2²+3²+4²) = 30
```

> [!important] AsyncScope 的铁律
> `AsyncScope` 析构时 `wait` 所有 future——这保证了**没有任务逃逸**。但注意：析构函数**阻塞**等待所有任务完成，可能导致意料之外的长时间阻塞。在生产代码中，可能需要加入超时逻辑或 `when_any` 变体。

---

## 三、练习

### 练习 1：实现工作窃取线程池

**难度**：`⭐ 基础`

将 [[#2.1 简单的固定大小线程池]] 中的共享队列替换为**每线程本地队列 + 工作窃取**。

**要求**：

- 每个工作线程拥有自己的 `std::deque<std::function<void()>>`（双端队列）
- `submit()` 将任务放入当前线程（或随机线程）的本地队列
- 工作线程从自己队列的**尾部**取任务（LIFO，缓存友好）
- 当本地队列为空时，随机选择另一个线程，从其队列的**头部**窃取任务（FIFO）
- 使用 `std::mutex` 保护每个本地队列（窃取时需要加锁）

**提示**：

```cpp
struct Worker {
    std::jthread thread;
    std::deque<std::function<void()>> queue;
    std::mutex mutex;
};

// 从尾部取（自己用，LIFO）
task = std::move(worker.queue.back());
worker.queue.pop_back();

// 从头部窃取（别人用，FIFO）
task = std::move(victim.queue.front());
victim.queue.pop_front();
```

### 练习 2：实现带优先级的任务调度器

**难度**：`⭐⭐ 中级`

在练习 1 的工作窃取线程池基础上，添加优先级调度支持。

**要求**：

- 任务携带优先级（`enum class Priority { Low, Normal, High, Critical }`）
- 每个工作线程的本地队列按优先级排序（使用 `std::priority_queue` 或维护多个队列）
- 高优先级任务应优先执行
- 添加**优先级继承**：如果高优先级任务等待低优先级任务的结果，临时提升低优先级任务的优先级

**思考**：

- 当高优先级任务不断涌入时，低优先级任务可能永远得不到执行（饥饿）。如何设计**老化**（aging）机制？
- 内存开销：每个任务多存储一个 `Priority` 字段是否可接受？

### 练习 3：实现可取消的 AsyncScope

**难度**：`⭐⭐⭐ 高级`

实现一个完整的 `CancellableAsyncScope`：

**要求**：

- 支持 `spawn()` 提交任务，返回 `std::future`
- 支持 `request_cancel()` 向所有子任务发出取消信号
- 析构时：先 `request_cancel()`，再 `wait` 所有子任务（超时 5 秒后 `detach` 并记录警告）
- 每个子任务的取消令牌是 scope 取消令牌的子令牌——scope 取消时，所有子令牌也标记为已取消
- 异常安全：某个子任务抛出异常不应影响其他任务的取消和等待

**接口示意**：

```cpp
class CancellableAsyncScope {
public:
    template<typename F>
    auto spawn(F&& f) -> std::future<decltype(f(std::declval<std::stop_token>()))>;

    void request_cancel();
    bool is_cancelled() const;

    ~CancellableAsyncScope(); // cancel + wait with timeout
};
```

**测试场景**：

1. 提交 3 个长时间运行的任务，1 秒后 cancel，验证所有任务在 5 秒内退出
2. 提交 1 个任务，让它正常完成，验证 scope 析构不阻塞
3. 提交 1 个无限循环任务，验证析构在超时后 `detach` 并输出警告

---

## 四、常见陷阱

> [!warning] 陷阱 1：共享队列竞争
> 高并发场景下，多个线程争抢同一个 `std::queue` 的互斥锁成为性能瓶颈。
> **解决**：使用工作窃取（per-thread queue）或无锁队列（如 `boost::lockfree::queue`）。在生产环境中，共享队列的吞吐量可能只有工作窃取的 1/10。

> [!warning] 陷阱 2：线程池析构时未 join 所有线程
> 如果析构函数不等待工作线程退出，线程可能在访问已释放的成员变量（如任务队列）时崩溃。
> **解决**：使用 `std::jthread` 代替 `std::thread`——它的析构函数自动 `join`。或者在析构函数中显式 `request_stop()` + `cv.notify_all()` + `join()`。

> [!warning] 陷阱 3：取消竞态条件
> 在检查 `stop_requested()` 和实际挂起操作之间存在窗口期——取消信号可能在此期间到达，导致任务"忽略"取消并挂起。
> ```cpp
> // 错误：窗口期
> if (!token.stop_requested()) {
>     // ← 取消信号可能在此到达
>     co_await some_operation(); // 挂起后不检查取消
> }
> // 正确：挂起前后都检查
> if (token.stop_requested()) co_return;
> // 确保 some_operation 内部传入 token 进行检查
> co_await some_operation(token);
> if (token.stop_requested()) co_return;
> ```

> [!warning] 陷阱 4：Fire-and-Forget 任务的异常吞没
> "提交后不管"（`pool.submit([] { risky_operation(); });` 不保存返回的 `future`）意味着：
> - 任务中抛出的异常被静默丢弃——**永远不会被捕获或记录**
> - 你甚至不知道任务是否已执行
> **解决**：至少使用 `std::async` 并将返回的 `future` 保存在某处；或在任务内部 `try-catch` 并记录日志。更好的方式是使用结构化并发的 `AsyncScope`。

> [!warning] 陷阱 5：嵌套提交导致的死锁
> 在固定大小线程池中，如果一个任务（占着一个线程）又向同一个池提交新任务并阻塞等待其结果，而池中没有空闲线程执行新任务——**死锁**。
> ```cpp
> ThreadPool pool(4);
> auto outer = pool.submit([&pool] {
>     auto inner = pool.submit([] { return 42; });
>     return inner.get(); // 如果所有线程都阻塞在这里 → 死锁
> });
> ```
> **解决**：
> - 使用 `std::launch::deferred` 或分离的执行上下文
> - 动态扩展线程池（允许临时超出最大线程数）
> - 设计上避免同池嵌套等待——父任务不应阻塞等待同一池中的子任务

> [!warning] 陷阱 6：协程生命周期比引用的对象更长
> 协程的 `promise_type` 在堆上分配（通常），其生命周期独立于调用者。如果协程捕获了栈上对象的引用，而调用者已经返回：
> ```cpp
> Task<int> bad(std::vector<int> v) {
>     auto& ref = v[0];        // v 在栈上
>     co_await something();
>     return ref;              // 悬空引用！v 可能已析构
> }
> ```
> **解决**：协程参数按值传递或使用 `shared_ptr`；对引用参数使用 `std::move` 语义。结构化并发的 scope 可以缓解此问题——scope 保证调用者的生命周期覆盖所有子协程。

---

## 五、扩展阅读

- [[05-coroutines-co-await]] — 协程 awaiter 协议和挂起机制
- [[07-coroutines-task-type]] — 从零实现 `Task<T>` 类型
- [[11-sender-receiver]] — C++26 `std::execution`（Sender/Receiver 模型），工业级调度器的标准答案
- [Lewis Baker: Structured Concurrency](https://lewissbaker.github.io/2022/03/27/structured-concurrency-in-cpp) — 结构化并发的 C++ 实践
- [Intel TBB Design Patterns](https://oneapi-src.github.io/oneTBB/) — TBB 的工作窃取实现和任务调度模式
- [Folly::coro documentation](https://github.com/facebook/folly/blob/main/folly/experimental/coro/) — Facebook 的协程框架，包含 `Task`、`AsyncScope`、`when_all` 等生产级实现
- [cppcoro: task.hpp](https://github.com/lewissbaker/cppcoro/blob/master/include/cppcoro/task.hpp) — Lewis Baker 的教学级 `Task` 实现，代码清晰，适合深入学习
- [[raii-complete-analysis]] — RAII 在异步资源管理中的应用
