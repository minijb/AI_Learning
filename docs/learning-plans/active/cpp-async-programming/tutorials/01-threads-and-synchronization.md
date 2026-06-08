---
title: 线程与同步原语
updated: 2026-06-08
tags: [cpp, concurrency, thread, mutex]
---

# 线程与同步原语

> 预计耗时：60 分钟
> 前置：无（C++ 基础语法即可）
> 下一节：[[02-async-future-promise|std::async 与 future/promise]]

---

## 一、概念

### 1.1 线程是什么？

线程是操作系统能调度的最小执行单元。一个进程可以包含多个线程，它们共享进程的地址空间（全局变量、堆内存），但各自拥有独立的栈和寄存器状态。

C++11 引入了标准线程库，让跨平台的多线程编程不再依赖 pthread（POSIX）或 Win32 API。核心类型：

| 类型 | 作用 | 引入版本 |
|------|------|----------|
| `std::thread` | 表示一个可执行线程 | C++11 |
| `std::jthread` | 自动 join 的线程，支持停止令牌 | C++20 |

### 1.2 `std::thread` — 线程的创建与生命周期

`std::thread` 构造时接受一个可调用对象（函数、lambda、函数对象），构造完成后线程立即开始执行。

**关键规则**：`std::thread` 对象析构前，必须调用 `join()` 或 `detach()`，否则 `std::terminate` 会被调用，程序直接崩溃。

```cpp
#include <thread>
#include <iostream>

void worker(int id) {
    std::cout << "Thread " << id << " running\n";
}

int main() {
    std::thread t1(worker, 1);       // 启动线程，执行 worker(1)
    std::thread t2([] {               // lambda 也可
        std::cout << "Lambda thread\n";
    });

    t1.join();   // 等待 t1 完成 — 阻塞当前线程
    t2.join();   // 等待 t2 完成
    // join 后线程对象可安全析构
}
```

- **`join()`**：调用线程阻塞，直到被 join 的线程执行完毕。join 后 `std::thread` 对象不再关联任何线程（`joinable() == false`）。
- **`detach()`**：将线程与 `std::thread` 对象"脱钩"，线程在后台独立运行。脱离后不再能 join。**危险**：如果后台线程访问已被销毁的局部变量，会导致未定义行为。

### 1.3 `std::jthread` — C++20 的改进

`std::jthread` 解决了两大痛点：

1. **析构时自动 join**：不需要记得手动 join/detach，RAII 风格。
2. **停止令牌（stop token）**：可以向线程请求停止，代替共享布尔标志。

```cpp
#include <thread>
#include <iostream>

void worker(std::stop_token st, int id) {
    while (!st.stop_requested()) {
        std::cout << "Thread " << id << " working...\n";
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Thread " << id << " stopped.\n";
}

int main() {
    std::jthread t(worker, 1);
    std::this_thread::sleep_for(std::chrono::seconds(1));
    // 不需要手动 join；t 析构时自动请求停止并 join
}
```

> [!tip] 优先使用 `std::jthread`
> 在新代码中，除非你需要 C++17 兼容性或显式 detach 行为，否则优先使用 `std::jthread`。它消除了最常见的线程管理 bug——忘记 join。

### 1.4 互斥量（Mutex）— 保护共享数据

当多个线程访问同一块内存，且至少有一个线程在写入时，必须同步，否则发生**数据竞争（data race）**——未定义行为。

| 类型 | 特点 | 引入版本 |
|------|------|----------|
| `std::mutex` | 基本互斥量，不可重入 | C++11 |
| `std::recursive_mutex` | 同一线程可重复 lock | C++11 |
| `std::timed_mutex` | 支持 `try_lock_for()` / `try_lock_until()` | C++11 |
| `std::shared_mutex` | 读写锁（多个读/独占写） | C++17 |

**锁守卫（Lock Guard）**— RAII 管理锁生命周期：

| 类型 | 特点 |
|------|------|
| `std::lock_guard` | 最轻量：构造 lock，析构 unlock，不可手动 unlock |
| `std::unique_lock` | 可延迟 lock、手动 unlock、转移所有权。配合条件变量必需 |
| `std::scoped_lock` | C++17：同时锁多个 mutex，避免死锁 |
| `std::shared_lock` | C++14：与 `std::shared_mutex` 配合，获取读锁 |

> [!important] RAII 锁管理
> 永远不要裸调用 `mutex.lock()` / `mutex.unlock()`。用锁守卫，让析构函数保证 unlock——即使异常或提前返回也不会死锁。

### 1.5 条件变量（Condition Variable）— 线程间通知

条件变量解决"等待某条件为真"的问题。没有条件变量时，线程只能**忙等（busy-wait）**，浪费 CPU：

```cpp
// 糟糕的忙等
while (!data_ready) {
    // 空转！CPU 100%
}
```

条件变量让线程在等待时**睡眠**，直到另一个线程通知它条件可能满足：

```cpp
std::mutex mtx;
std::condition_variable cv;
bool data_ready = false;

// 等待线程
std::unique_lock lk(mtx);
cv.wait(lk, [] { return data_ready; });  // 等价于 while(!data_ready) cv.wait(lk);
// 此时 data_ready == true 且持有锁

// 通知线程
{
    std::lock_guard lk(mtx);
    data_ready = true;
}
cv.notify_one();  // 或 notify_all()
```

**关键细节**：

- `wait()` 在等待前释放锁，被唤醒后重新获取锁。
- 必须配合 `std::unique_lock`（而非 `lock_guard`），因为条件变量内部需要 unlock/lock。
- 使用**带谓词的 wait**（`cv.wait(lk, predicate)`）防止虚假唤醒。

### 1.6 死锁（Deadlock）— 成因与预防

死锁的四个必要条件（Coffman 条件）：

1. **互斥**：资源不能共享
2. **持有并等待**：线程持有一个锁，同时等待另一个
3. **不可剥夺**：锁不能被外部释放
4. **循环等待**：线程 A 等 B，B 等 A

预防策略：

| 策略 | 手段 |
|------|------|
| 避免嵌套锁 | 尽量不要在一个锁内获取另一个锁 |
| 固定锁顺序 | 如果必须多锁，总是以相同顺序获取 |
| 使用 `std::scoped_lock` | C++17：原子地获取多个锁 |
| 使用 `std::lock` | C++11：同时锁多个 mutex，配合 `std::unique_lock` |
| 使用 `try_lock` | 获取失败时释放已有锁，稍后重试 |

---

## 二、代码示例

### 2.1 基础 `std::thread` + join

**编译**：`g++ -std=c++17 -pthread 01_basic_thread.cpp -o 01_basic_thread`

```cpp
// 01_basic_thread.cpp
#include <thread>
#include <iostream>
#include <vector>
#include <chrono>

void do_work(int id, int delay_ms) {
    std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
    std::cout << "[Thread " << id << "] done after " << delay_ms << "ms\n";
}

int main() {
    constexpr int N = 5;
    std::vector<std::thread> threads;

    // 创建 N 个线程
    for (int i = 0; i < N; ++i) {
        threads.emplace_back(do_work, i, (N - i) * 100);
    }

    std::cout << "[Main] waiting for all threads...\n";

    // 等待所有线程完成
    for (auto& t : threads) {
        t.join();
    }

    std::cout << "[Main] all threads finished.\n";
}
```

**预期输出**（顺序可能不同）：

```
[Main] waiting for all threads...
[Thread 4] done after 100ms
[Thread 3] done after 200ms
[Thread 2] done after 300ms
[Thread 1] done after 400ms
[Thread 0] done after 500ms
[Main] all threads finished.
```

### 2.2 `std::jthread` 自动 join + 停止令牌（C++20）

**编译**：`g++ -std=c++20 -pthread 02_jthread.cpp -o 02_jthread`

```cpp
// 02_jthread.cpp
#include <thread>
#include <iostream>
#include <chrono>
#include <vector>

void worker(std::stop_token st, int id) {
    int count = 0;
    while (!st.stop_requested()) {
        std::cout << "Thread " << id << ": iteration " << ++count << '\n';
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
    }
    std::cout << "Thread " << id << " stopped after " << count << " iterations.\n";
}

int main() {
    std::vector<std::jthread> threads;

    // 启动 3 个线程
    for (int i = 0; i < 3; ++i) {
        threads.emplace_back(worker, i);
    }

    // 主线程等 1.5 秒后退出作用域
    std::this_thread::sleep_for(std::chrono::seconds(1));
    std::cout << "[Main] going out of scope — jthreads will auto-join\n";

    // jthread 析构时自动 request_stop() + join()
}
```

> [!note] 不需要手动 join
> `threads` vector 析构时，每个 `std::jthread` 的析构函数会调用 `request_stop()` 然后 `join()`，线程安全退出。

### 2.3 Mutex + `lock_guard` 保护共享计数器

**编译**：`g++ -std=c++17 -pthread 03_mutex_counter.cpp -o 03_mutex_counter`

```cpp
// 03_mutex_counter.cpp
#include <thread>
#include <iostream>
#include <vector>
#include <mutex>

int main() {
    int counter = 0;
    std::mutex mtx;
    constexpr int THREADS = 10;
    constexpr int ITER_PER_THREAD = 100000;

    auto increment = [&] {
        for (int i = 0; i < ITER_PER_THREAD; ++i) {
            // lock_guard 在本作用域结束时自动释放锁
            std::lock_guard<std::mutex> lk(mtx);
            ++counter;
        }
    };

    std::vector<std::thread> threads;
    for (int i = 0; i < THREADS; ++i) {
        threads.emplace_back(increment);
    }

    for (auto& t : threads) t.join();

    std::cout << "Expected: " << THREADS * ITER_PER_THREAD << '\n';
    std::cout << "Actual:   " << counter << '\n';
}
```

**预期输出**：

```
Expected: 1000000
Actual:   1000000
```

> [!warning] 不加锁的后果
> 去掉 `lock_guard` 后再运行几次——结果几乎总是不对。`++counter` 不是原子操作（读-改-写），两个线程可能读到相同的旧值。

### 2.4 条件变量：生产者-消费者

**编译**：`g++ -std=c++17 -pthread 04_producer_consumer.cpp -o 04_producer_consumer`

```cpp
// 04_producer_consumer.cpp
#include <thread>
#include <iostream>
#include <queue>
#include <mutex>
#include <condition_variable>

int main() {
    std::queue<int> queue;
    std::mutex mtx;
    std::condition_variable cv;
    constexpr int MAX_ITEMS = 10;

    // 生产者线程
    std::thread producer([&] {
        for (int i = 0; i < MAX_ITEMS; ++i) {
            {
                std::lock_guard lk(mtx);
                queue.push(i);
                std::cout << "[Producer] produced " << i << '\n';
            }
            cv.notify_one();  // 通知消费者
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    });

    // 消费者线程
    std::thread consumer([&] {
        for (int i = 0; i < MAX_ITEMS; ++i) {
            std::unique_lock lk(mtx);
            // 带谓词的 wait：queue 不空才继续
            cv.wait(lk, [&] { return !queue.empty(); });
            int val = queue.front();
            queue.pop();
            std::cout << "[Consumer] consumed " << val << '\n';
            // unique_lock 离开作用域时自动 unlock
        }
    });

    producer.join();
    consumer.join();
}
```

**关键点**：

- 消费者用 `std::unique_lock`（而非 `lock_guard`），条件变量需要它。
- `cv.wait(lk, predicate)` 等价于 `while (!predicate()) { cv.wait(lk); }`，避免虚假唤醒 bug。
- `notify_one()` 在释放锁之后调用也可——但在锁内通知可以减少"惊群"开销。

### 2.5 死锁演示 + `scoped_lock` 修复

**编译**：`g++ -std=c++17 -pthread 05_deadlock_fix.cpp -o 05_deadlock_fix`

```cpp
// 05_deadlock_fix.cpp
#include <thread>
#include <iostream>
#include <mutex>

// 危险版本 — 可能死锁
void unsafe_transfer(int& from, int& to, int amount,
                     std::mutex& mtx_from, std::mutex& mtx_to) {
    std::lock_guard lk1(mtx_from);
    std::this_thread::sleep_for(std::chrono::milliseconds(1)); // 放大竞争窗口
    std::lock_guard lk2(mtx_to);
    from -= amount;
    to   += amount;
}

// 安全版本 — 用 scoped_lock 同时锁定
void safe_transfer(int& from, int& to, int amount,
                   std::mutex& mtx_from, std::mutex& mtx_to) {
    std::scoped_lock lk(mtx_from, mtx_to);
    from -= amount;
    to   += amount;
}

int main() {
    int a = 100, b = 100;
    std::mutex mtx_a, mtx_b;

    std::cout << "Initial: a=" << a << ", b=" << b << '\n';

    // 注释掉 unsafe 版，使用 safe 版
    std::thread t1(safe_transfer, std::ref(a), std::ref(b), 30, std::ref(mtx_a), std::ref(mtx_b));
    std::thread t2(safe_transfer, std::ref(b), std::ref(a), 20, std::ref(mtx_b), std::ref(mtx_a));

    t1.join();
    t2.join();

    std::cout << "Final:   a=" << a << ", b=" << b << '\n';
    std::cout << "Sum preserved: " << (a + b == 200 ? "yes" : "no") << '\n';
}
```

**为什么 `unsafe_transfer` 可能死锁？**
t1 先锁 mtx_a 再锁 mtx_b，t2 先锁 mtx_b 再锁 mtx_a——循环等待。

**`std::scoped_lock` 如何解决？**
C++17 的 `std::scoped_lock` 使用与 `std::lock` 相同的死锁避免算法（try-and-back-off），原子地获取所有传入的锁。

> [!note] `std::lock` + `std::unique_lock`（C++11 等价写法）
> ```cpp
> std::unique_lock lk1(mtx_from, std::defer_lock);
> std::unique_lock lk2(mtx_to, std::defer_lock);
> std::lock(lk1, lk2);  // 同时锁两个
> ```

---

## 三、练习

### 练习 1（基础）：Lambda 线程

编写一个程序，创建 3 个 `std::thread`，每个线程用 lambda 打印自己的线程 ID（使用 `std::this_thread::get_id()`）和一条消息。主线程在创建后 join 所有线程。

**要求**：
- 用 lambda 而非函数指针
- 用 `std::vector<std::thread>` 管理线程
- 编译运行验证

### 练习 2（中级）：并行求和

编写程序，用多个线程并行计算一个大数组的和。

**要求**：
1. 创建一个包含 1000000 个 `int` 的 `std::vector`，填充 1
2. 创建 4 个线程，每个处理数组的 1/4 段（每段 250000 个元素）
3. 用**一个** `std::mutex` 保护总和变量
4. 输出结果应为 `1000000`

**思考**：
- 如果去掉 mutex，结果会是多少？为什么？
- 这种粒度下，锁竞争严重吗？有没有更好的方案？（提示：局部求和 + 最后合并）

### 练习 3（挑战）：线程安全队列

实现一个 `ThreadSafeQueue<T>` 类模板，支持多生产者-多消费者场景。

**接口要求**：

- `void push(T value)` — 向队列添加元素
- `T pop()` — 移除并返回队首元素；若队列为空，**阻塞等待**直到有元素可用
- `bool try_pop(T& value)` — 非阻塞版本，成功返回 true
- `bool empty() const` — 检查队列是否为空
- `size_t size() const` — 返回队列当前大小

**测试**：
1. 启动 2 个生产者线程，各 push 100 个整数
2. 启动 2 个消费者线程，各 pop 100 次并累加
3. 验证总和

**提示**：需要 `std::mutex` + `std::condition_variable`。

---

## 四、常见陷阱

> [!warning] 陷阱 1：忘记 join/detach 导致 `std::terminate`
>
> `std::thread` 对象在析构时如果仍是 joinable 状态（既没 join 也没 detach），会调用 `std::terminate()` 强制终止整个程序。
>
> ```cpp
> void bad() {
>     std::thread t([]{ /* ... */ });
>     // 函数结束 → t 析构 → std::terminate!
> }
> ```
>
> **修复**：确保每个线程都 join 或 detach；或使用 `std::jthread`（C++20）自动处理。

> [!warning] 陷阱 2：数据竞争（Data Race）
>
> 两个线程同时访问同一内存，且至少一个是写操作，且没有任何同步——这就是数据竞争，属于未定义行为。
>
> ```cpp
> // 未定义行为：counter 无保护
> int counter = 0;
> void race() { for (int i = 0; i < 100000; ++i) ++counter; }
> ```
>
> **修复**：用 `std::mutex` 或 `std::atomic<int>`。

> [!warning] 陷阱 3：虚假唤醒（Spurious Wakeup）
>
> `condition_variable::wait()` 可能在没有通知的情况下返回。**必须用带谓词的 wait 或手动 while 循环**。
>
> ```cpp
> // 错误：虚假唤醒可能导致在 queue 为空时 pop
> cv.wait(lk);  // 可能虚假唤醒！
> int val = queue.front();
>
> // 正确：带谓词
> cv.wait(lk, [&] { return !queue.empty(); });
> ```

> [!warning] 陷阱 4：锁顺序不一致导致死锁
>
> 线程 A 先锁 mutex1 再锁 mutex2，线程 B 先锁 mutex2 再锁 mutex1——死锁。
>
> ```cpp
> // 线程 A
> lock(m1); lock(m2);  // m1 → m2
>
> // 线程 B
> lock(m2); lock(m1);  // m2 → m1 — 死锁!
> ```
>
> **修复**：
> - 固定全局锁顺序
> - 使用 `std::scoped_lock(m1, m2)`（C++17）
> - 或 `std::lock(lk1, lk2)`（C++11）

> [!warning] 陷阱 5：detach 后访问已销毁的局部变量
>
> `detach()` 后线程在后台运行，如果访问了主线程栈上已销毁的变量，导致悬垂引用——未定义行为。
>
> ```cpp
> void dangerous() {
>     int local = 42;
>     std::thread t([&local] {
>         std::this_thread::sleep_for(std::chrono::seconds(1));
>         std::cout << local;  // local 可能已被销毁!
>     });
>     t.detach();
> }  // local 销毁，但线程可能还在用
> ```
>
> **修复**：传值而非引用；或保证线程在局部变量销毁前完成（用 join）。

> [!warning] 陷阱 6：条件变量丢失通知（Lost Wakeup）
>
> 如果通知在等待之前发生，等待线程可能永远阻塞。
>
> ```cpp
> // 错误顺序
> cv.notify_one();                     // 先通知 — 没人等
> cv.wait(lk, [&]{ return ready; });   // 后等待 — 永远等不到
> ```
>
> **修复**：通知和等待共享一个 mutex 保护的谓词变量；先锁再检查谓词。

---

## 五、扩展阅读

### C++ 参考

- [std::thread — cppreference](https://en.cppreference.com/w/cpp/thread/thread)
- [std::jthread — cppreference](https://en.cppreference.com/w/cpp/thread/jthread)
- [std::mutex — cppreference](https://en.cppreference.com/w/cpp/thread/mutex)
- [std::condition_variable — cppreference](https://en.cppreference.com/w/cpp/thread/condition_variable)
- [std::scoped_lock — cppreference](https://en.cppreference.com/w/cpp/thread/scoped_lock)

### 深入阅读

- [C++ Concurrency in Action (2nd Edition) — Anthony Williams](https://www.manning.com/books/c-plus-plus-concurrency-in-action-second-edition) — 本章内容的权威参考
- [The Deadlock Empire — 死锁互动教程](https://deadlockempire.github.io/) — 通过游戏理解并发 bug
- [Thread Sanitizer — Clang/GCC 文档](https://clang.llvm.org/docs/ThreadSanitizer.html) — 自动检测数据竞争的工具

### 本系列下一节

[[02-async-future-promise|std::async 与 future/promise]] — 从手动线程管理到任务级异步的飞跃。
