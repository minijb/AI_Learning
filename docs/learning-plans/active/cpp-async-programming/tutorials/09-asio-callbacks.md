---
title: Boost.Asio Part 1 — io_context 与回调模型
updated: 2026-06-08
tags: [cpp, asio, async-io, networking]
---

# Boost.Asio Part 1 — io_context 与回调模型

> 学习路径：[[../plan|C++ 异步编程学习计划]]
> 前置：[[01-threads-and-synchronization|线程与同步原语]]、[[02-async-future-promise|std::async 与 future/promise]]
> 预计耗时：60 分钟

---

## 一、核心概念

### 1.1 Boost.Asio 是什么

Boost.Asio 是 C++ 生态中最成熟的跨平台异步 I/O 库，自 2005 年起作为 Boost 的一部分发布，2012 年起有独立版本（`asio`，无需 Boost）。C++ Networking TS（`std::execution` 的灵感来源之一）直接以 Asio 为原型。

Asio 的核心价值：

- **Proactor 模式**：将 I/O 操作提交给操作系统，OS 完成后通知应用层。与 Reactor（libevent/libuv 使用的模式，由应用层轮询就绪状态后自行执行 I/O）不同，Proactor 中真正的 I/O 由 OS 内核完成，应用仅处理"已完成"的结果。
- **统一的异步模型**：网络、定时器、串口、信号、文件 I/O（部分平台）使用同一套异步接口。
- **零开销抽象**：异步操作的分配可通过自定义分配器优化；同步操作在概念上不经过事件循环。

> [!info] Proactor vs Reactor
>
> - **Reactor**：内核通知"fd 可读" → 应用层调用 `read()` → 数据拷贝到用户空间 → 处理数据。应用层负责执行实际 I/O。
> - **Proactor**：应用层提交异步 `read()` → 内核完成 I/O 并将数据拷贝到用户缓冲区 → 内核通知"读取完成" → 应用层直接使用数据。应用层只处理结果。
>
> Windows IOCP 是原生 Proactor；Linux `epoll` 是 Reactor，Asio 在 Linux 上通过内部 Reactor 模拟 Proactor 语义。

### 1.2 io_context：事件循环的心脏

`io_context`（旧称 `io_service`）是 Asio 的核心，它驱动所有异步操作：

- **`io_context::run()`** 是事件循环。它阻塞当前线程，调度并执行就绪的完成处理程序（completion handler），直到没有待处理的异步操作时返回。
- 异步操作的状态（"正在等待某 I/O 完成"）也算"工作"——所以只要有活跃的异步操作，`run()` 就不会返回。
- 多个线程可以同时调用同一个 `io_context` 的 `run()`，实现线程池式并发。

```cpp
// 最小工作循环
asio::io_context ctx;
// ... 启动异步操作 ...
ctx.run();  // 阻塞直到所有异步操作完成
```

> [!important] `run()` 的返回条件
> `run()` 在**没有待处理的工作**时返回。这里的"工作"包括：
> 1. 尚未就绪的异步操作（正在等待 I/O/定时器）
> 2. 通过 `post()`/`dispatch()`/`defer()` 排队的处理程序
>
> 所有异步操作完成 + 队列空 → `run()` 返回。

### 1.3 I/O 对象

Asio 提供两类 I/O 对象：

| 类别 | 关键类型 | 说明 |
|------|---------|------|
| 定时器 | `asio::steady_timer` | 基于单调时钟的定时器 |
| 定时器 | `asio::system_timer` | 基于系统时钟的定时器 |
| TCP | `asio::ip::tcp::socket` | TCP 套接字 |
| TCP | `asio::ip::tcp::acceptor` | TCP 监听/接受连接 |
| TCP | `asio::ip::tcp::resolver` | DNS 解析 |
| UDP | `asio::ip::udp::socket` | UDP 套接字 |
| 串口 | `asio::serial_port` | 串口通信 |
| 信号 | `asio::signal_set` | POSIX 信号处理 |

所有 I/O 对象都需要关联一个 `io_context`，在构造时传入：

```cpp
asio::io_context ctx;
asio::steady_timer timer(ctx);        // 关联到 ctx
asio::ip::tcp::socket socket(ctx);    // 关联到 ctx
```

### 1.4 三种完成机制

Asio 支持三种方式接收异步操作的结果：

| 机制 | 语法 | 特点 |
|------|------|------|
| **回调函数 (Callback)** | 传入一个可调用对象 | 最基础、最灵活 |
| **Future** | 使用 `asio::use_future` | 阻塞等待，与 `std::async` 风格统一 |
| **C++20 协程** | 使用 `asio::use_awaitable` | 最现代化，写同步风格代码 |

```cpp
// 回调
timer.async_wait([](std::error_code ec) { /* ... */ });

// Future
std::future<void> f = timer.async_wait(asio::use_future);
f.get();  // 阻塞等待

// 协程（C++20）
co_await timer.async_wait(asio::use_awaitable);
```

> [!tip] 本教程聚焦回调模型
> 本教程（Part 1）聚焦回调模型——这是理解 Asio 运行机制的基石。Part 2（[[10-asio-coroutines|协程集成]]）将深入协程与 Asio 的结合。

### 1.5 Strand：串行化执行

当多个线程调用同一个 `io_context::run()` 时，完成处理程序会并发执行。如果你的数据结构不是线程安全的，你需要串行化访问。

`asio::strand` 保证**提交到同一个 strand 的处理程序不会并发执行**——它们被序列化（但顺序不一定保证）。

```cpp
asio::io_context ctx;
asio::strand strand(ctx);

// 这两个处理程序不会并发执行，即使多个线程在跑 ctx.run()
asio::post(strand, []{ /* 临界区 A */ });
asio::post(strand, []{ /* 临界区 B */ });
```

> [!warning] Strand 只保护处理程序，不保护数据
> Strand 保证被它包装的处理程序不会并发执行，但**不保护在 strand 外部直接访问的共享数据**。如果你在 strand 外直接修改同一块内存，strand 无能为力。

### 1.6 Work Guard：防止 io_context 提前返回

有时你需要 `io_context` 保持运行，即使当前没有活跃的异步操作。例如，你可能稍后会动态启动新的异步操作。

`asio::executor_work_guard` 创建一个"虚假的工作"，阻止 `io_context::run()` 返回：

```cpp
asio::io_context ctx;
auto work = asio::make_work_guard(ctx);
// 此时 ctx.run() 不会返回，即使没有其他异步操作
ctx.run();  // 将一直阻塞，直到 work.reset() 被调用
```

### 1.7 post / dispatch / defer：主动调度

你可以将任意处理程序手动注入到 `io_context` 的事件循环：

| 函数 | 行为 |
|------|------|
| `asio::post(ctx, handler)` | 将 handler 排队，**总是异步执行**（不立即执行，放入队列） |
| `asio::dispatch(ctx, handler)` | 如果调用者在 `io_context` 线程内 → **立即执行**；否则 → 排队 |
| `asio::defer(ctx, handler)` | 将 handler 排队，**总是延迟执行**（与 post 类似，但语义上暗示"稍后"） |

---

## 二、代码示例

> [!info] 编译要求
> 所有示例需要 Boost.Asio（或独立版 asio）和 pthread。安装 Boost 后，头文件路径通常为 `/usr/include`（或自定义路径）。使用独立版 asio 时设置 `-DASIO_STANDALONE`。
>
> **编译命令模板**：
> ```bash
> # 使用 Boost.Asio
> g++ -std=c++17 -pthread -I/path/to/boost example.cpp -o example
>
> # 使用独立 asio（无需链接 boost_system）
> g++ -std=c++17 -pthread -DASIO_STANDALONE example.cpp -o example
> ```

### 2.1 简单定时器回调

```cpp
// compile: g++ -std=c++17 -pthread -DASIO_STANDALONE timer_callback.cpp -o timer_callback
#include <asio.hpp>
#include <iostream>
#include <chrono>

int main() {
    asio::io_context ctx;

    asio::steady_timer timer(ctx, std::chrono::seconds(2));

    timer.async_wait([](const std::error_code& ec) {
        if (!ec) {
            std::cout << "Timer fired! (2 seconds elapsed)" << std::endl;
        } else if (ec == asio::error::operation_aborted) {
            std::cout << "Timer was cancelled." << std::endl;
        }
    });

    std::cout << "Waiting for timer... (io_context::run() blocks here)" << std::endl;
    ctx.run();
    std::cout << "io_context::run() returned. Exiting." << std::endl;
}
```

**预期输出**：
```
Waiting for timer... (io_context::run() blocks here)
Timer fired! (2 seconds elapsed)
io_context::run() returned. Exiting.
```

**要点分析**：

- `async_wait` 是非阻塞的——它立即返回，注册回调后继续执行。
- `ctx.run()` 阻塞直到定时器触发、回调执行完毕、没有其他待处理工作。
- 回调的参数 `std::error_code` 是 Asio 的错误传递机制——不抛异常。

### 2.2 单线程 TCP Echo 服务器

```cpp
// compile: g++ -std=c++17 -pthread -DASIO_STANDALONE tcp_echo_server.cpp -o tcp_echo_server
#include <asio.hpp>
#include <iostream>
#include <memory>
#include <vector>

using asio::ip::tcp;

// 连接会话：管理单个客户端的读写循环
class Session : public std::enable_shared_from_this<Session> {
public:
    explicit Session(tcp::socket socket)
        : socket_(std::move(socket)) {}

    void start() {
        do_read();
    }

private:
    void do_read() {
        auto self = shared_from_this();  // 保持 Session 存活
        socket_.async_read_some(
            asio::buffer(data_),
            [this, self](std::error_code ec, std::size_t length) {
                if (!ec) {
                    do_write(length);
                }
                // 如果 ec 非零（对端关闭或出错），Session 自然析构
            });
    }

    void do_write(std::size_t length) {
        auto self = shared_from_this();
        asio::async_write(
            socket_,
            asio::buffer(data_, length),
            [this, self](std::error_code ec, std::size_t /*written*/) {
                if (!ec) {
                    do_read();  // 写回后继续读
                }
            });
    }

    tcp::socket socket_;
    std::array<char, 1024> data_;
};

// 接受器：等待新连接
class Server {
public:
    Server(asio::io_context& ctx, unsigned short port)
        : acceptor_(ctx, tcp::endpoint(tcp::v4(), port)) {
        do_accept();
    }

private:
    void do_accept() {
        acceptor_.async_accept(
            [this](std::error_code ec, tcp::socket socket) {
                if (!ec) {
                    std::cout << "New connection from: "
                              << socket.remote_endpoint() << std::endl;
                    std::make_shared<Session>(std::move(socket))->start();
                }
                // 继续接受下一个连接
                do_accept();
            });
    }

    tcp::acceptor acceptor_;
};

int main() {
    try {
        asio::io_context ctx;
        Server server(ctx, 12345);
        std::cout << "Echo server listening on port 12345..." << std::endl;
        ctx.run();
    } catch (const std::exception& e) {
        std::cerr << "Exception: " << e.what() << std::endl;
    }
}
```

**测试方法**：
```bash
# 终端 1：启动服务器
./tcp_echo_server

# 终端 2：使用 netcat/telnet 测试
echo "Hello Asio" | nc localhost 12345
# 输出：Hello Asio
```

**要点分析**：

- `std::enable_shared_from_this`：异步回调可能在对象销毁后执行，`shared_from_this()` 保证 `Session` 在回调执行期间存活。
- `do_read → do_write → do_read → ...` 形成异步读写循环。每次回调安排好下一轮 I/O。
- `Server::do_accept()` 在回调末尾重新调用自己，形成持续的接受循环。
- 整个服务器是单线程的，但可以同时服务多个客户端——Asio 的事件循环交替执行每个活跃 `Session` 的就绪回调。

### 2.3 多线程 io_context 与 Strand

```cpp
// compile: g++ -std=c++17 -pthread -DASIO_STANDALONE strand_example.cpp -o strand_example
#include <asio.hpp>
#include <iostream>
#include <thread>
#include <vector>
#include <mutex>

class Counter {
public:
    // 通过 strand 保证 increment 不会并发执行
    void increment() {
        // 实际上 increment 的操作很快，但演示 strand 保证串行化
        ++value_;
        std::cout << "Counter = " << value_
                  << " [thread " << std::this_thread::get_id() << "]"
                  << std::endl;
    }

    int value() const { return value_; }

private:
    int value_ = 0;
};

int main() {
    asio::io_context ctx;
    Counter counter;

    // 创建 strand 用于串行化对 counter 的访问
    asio::strand<asio::io_context::executor_type> strand(
        asio::make_strand(ctx));

    // 从多个"线程"提交 increment 操作——实际上我们 post 到 io_context
    // strand 保证这些操作不会并发执行
    for (int i = 0; i < 20; ++i) {
        asio::post(strand, [&counter, i] {
            counter.increment();
        });
    }

    // 启动 4 个工作线程运行 io_context
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&ctx] { ctx.run(); });
    }

    // 等待所有线程完成
    for (auto& t : threads) {
        t.join();
    }

    std::cout << "Final counter value: " << counter.value() << std::endl;
}
```

**预期输出**（线程 ID 不同，但 `Counter` 值严格递增 1-20）：
```
Counter = 1 [thread 12345]
Counter = 2 [thread 67890]
Counter = 3 [thread 12345]
...
Counter = 20 [thread 67890]
Final counter value: 20
```

> [!important] 观察
> 虽然 4 个线程同时跑 `ctx.run()`，但通过 strand 提交的 20 个 increment 操作**不会并发**（Counter 值严格连续递增 1, 2, 3...）。如果没有 strand，多个线程会同时执行 `++value_`，产生数据竞争。

### 2.4 Work Guard 模式

```cpp
// compile: g++ -std=c++17 -pthread -DASIO_STANDALONE work_guard.cpp -o work_guard
#include <asio.hpp>
#include <iostream>
#include <thread>
#include <chrono>

int main() {
    asio::io_context ctx;

    // 创建 work guard —— 阻止 io_context::run() 在无工作时返回
    auto work = asio::make_work_guard(ctx);

    // 在另一个线程运行事件循环
    std::thread worker([&ctx] {
        std::cout << "[worker] io_context::run() started" << std::endl;
        ctx.run();
        std::cout << "[worker] io_context::run() returned" << std::endl;
    });

    // 主线程：动态 post 任务
    for (int i = 1; i <= 5; ++i) {
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        asio::post(ctx, [i] {
            std::cout << "Task " << i << " executing on thread "
                      << std::this_thread::get_id() << std::endl;
        });
    }

    std::cout << "[main] All tasks posted. Resetting work guard..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(1));

    // 释放 work guard → io_context 不再有"虚假工作"
    // 当前排队的任务完成后，run() 将返回
    work.reset();

    worker.join();
    std::cout << "[main] Done." << std::endl;
}
```

**预期输出**：
```
[worker] io_context::run() started
Task 1 executing on thread ...
Task 2 executing on thread ...
Task 3 executing on thread ...
Task 4 executing on thread ...
Task 5 executing on thread ...
[main] All tasks posted. Resetting work guard...
[worker] io_context::run() returned
[main] Done.
```

**要点分析**：

- 没有 work guard，`ctx.run()` 在主循环启动后立即返回（没有待处理的异步操作和被 post 的 handler）。
- work guard 让 `io_context` 保持"有工作"状态，即使 post 的任务之间有间隔。
- `work.reset()` 后，`io_context` 在当前已排队的任务全部执行完后返回。

### 2.5 post / dispatch / defer 区别

```cpp
// compile: g++ -std=c++17 -pthread -DASIO_STANDALONE post_dispatch_defer.cpp -o post_dispatch_defer
#include <asio.hpp>
#include <iostream>
#include <thread>
#include <chrono>

int main() {
    asio::io_context ctx;
    auto work = asio::make_work_guard(ctx);  // 防止 run() 提前返回

    // 从 io_context 线程内部调用
    asio::post(ctx, [&ctx] {
        std::cout << "=== Inside io_context thread ===" << std::endl;

        // post: 总是排队（异步）
        asio::post(ctx, [] {
            std::cout << "  post:    executed (always queued)" << std::endl;
        });

        // dispatch: 如果在 io_context 线程内 → 立即执行
        asio::dispatch(ctx, [] {
            std::cout << "  dispatch: executed immediately (same thread)" << std::endl;
        });

        // defer: 总是排队（与 post 类似）
        asio::defer(ctx, [] {
            std::cout << "  defer:   executed (always queued)" << std::endl;
        });

        std::cout << "=== Handler returned ===" << std::endl;
    });

    std::thread worker([&ctx] { ctx.run(); });
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    work.reset();
    worker.join();
}
```

**预期输出**：
```
=== Inside io_context thread ===
  dispatch: executed immediately (same thread)
=== Handler returned ===
  post:    executed (always queued)
  defer:   executed (always queued)
```

**要点分析**：

- `dispatch` 在 io_context 线程内立即执行（内联），不经过事件循环队列。
- `post` 和 `defer` 都延迟到当前处理程序返回后才执行。
- `post` 与 `defer` 的语义差异微妙：`defer` 的"稍后"意味着即使从外部线程调用它也不会立即执行（与 `post` 相同），但在与 custom executor 结合时可能有不同行为。在标准 `io_context` 上，二者等效。

---

## 三、练习

### 3.1 TCP Daytime 服务器（入门）

实现一个 TCP 服务器，监听端口 13000。当客户端连接后，服务器**立即发送**当前日期时间字符串（如 `"2026-06-08 14:30:00"`），然后关闭连接。

**要求**：
- 使用 `asio::steady_timer` 或 `std::time` 获取当前时间
- 使用异步回调风格（不用协程）
- 服务器必须能处理多个并发客户端

**提示**：参考 2.2 的 Echo 服务器模式，但 Session 的 `start()` 换成直接发送日期然后关闭。

### 3.2 异步文件读取器（进阶）

实现一个程序，使用 Asio 异步读取一个文本文件并打印内容。

**要求**：
- 程序启动后，使用 `asio::steady_timer` 延迟 1 秒（模拟等待文件就绪）
- 定时器触发后，使用 C 标准库 `fopen`/`fread`（在回调中同步执行）读取文件
- 将文件内容打印到标准输出
- 使用 `asio::post` 将 "读取完成" 的通知发送回 io_context

**提示**：

```cpp
asio::steady_timer timer(ctx, std::chrono::seconds(1));
timer.async_wait([&](std::error_code ec) {
    // 这个回调在 io_context 线程中执行
    // 这里的同步 I/O 是安全的——它是普通的文件读取
    FILE* f = fopen("test.txt", "r");
    // ... 读取内容 ...
    fclose(f);

    // post 一个"完成"通知
    asio::post(ctx, [content = std::move(buffer)] {
        std::cout << "File content:\n" << content << std::endl;
    });
});
```

### 3.3 多线程 Echo 服务器 + Strand（挑战）

扩展 2.2 的单线程 Echo 服务器，使其使用**多线程运行 io_context**，同时使用 **strand** 保护每个 Session 的读写操作。

**要求**：
- 4 个工作线程调用 `ctx.run()`
- 每个 `Session` 的 `do_read()` 和 `do_write()` 通过 strand 提交
- 每个 `Session` 拥有自己的 strand（`asio::strand<asio::io_context::executor_type>`）
- 确保回显正确：客户端发送的数据必须原样返回，不能出现交叉

**关键设计**：`bind_executor(strand, handler)` 将 handler 绑定到特定 strand 执行。

```cpp
void do_read() {
    auto self = shared_from_this();
    socket_.async_read_some(
        asio::buffer(data_),
        asio::bind_executor(strand_,
            [this, self](std::error_code ec, std::size_t length) {
                if (!ec) do_write(length);
            }));
}
```

---

## 四、常见陷阱（4+）

### 4.1 `io_context::run()` 提前返回

**现象**：`run()` 启动后立即返回，异步操作似乎没有执行。

**原因**：`run()` 在没有任何待处理工作时立即返回。如果异步操作尚未被启动（对象还没构造或 `async_*` 还没调用），或者所有异步操作都已完成且队列为空，`run()` 就会返回。

**解决**：

```cpp
// 错误：run() 立即返回
asio::io_context ctx;
std::thread t([&] { ctx.run(); });  // run() 立即返回，因为没有工作
t.join();

// 正确：使用 work guard
asio::io_context ctx;
auto work = asio::make_work_guard(ctx);
std::thread t([&] { ctx.run(); });
// ... 稍后 post 任务 ...
work.reset();
t.join();
```

### 4.2 回调中捕获引用导致悬垂

**现象**：程序崩溃或行为异常，通常在回调执行时访问已销毁的对象。

**原因**：异步回调中按引用捕获了局部变量或 `this` 指针。当回调执行时，捕获的对象可能已经离开作用域。

**解决**：

```cpp
// 错误：buffer 是局部变量，回调执行时它已被销毁
void bad_func(asio::io_context& ctx) {
    std::string buffer = "hello";
    asio::post(ctx, [&buffer] {
        std::cout << buffer << std::endl;  // 悬垂引用！
    });
}

// 正确：移动捕获或 shared_ptr
void good_func(asio::io_context& ctx) {
    auto buffer = std::make_shared<std::string>("hello");
    asio::post(ctx, [buffer] {
        std::cout << *buffer << std::endl;  // 安全
    });
}

// 对于类成员：使用 enable_shared_from_this
class MyClass : public std::enable_shared_from_this<MyClass> {
    void do_async() {
        auto self = shared_from_this();
        timer_.async_wait([this, self](std::error_code ec) {
            // this 安全——self 保证 MyClass 存活
            this->on_timer(ec);
        });
    }
    // ...
};
```

> [!warning] `shared_from_this()` 的前提
> 对象必须由 `std::shared_ptr` 管理。如果对象在栈上或由 `unique_ptr` 管理，调用 `shared_from_this()` 会导致未定义行为（通常抛 `std::bad_weak_ptr`）。

### 4.3 Strand 不保护外部直接访问的数据

**现象**：虽然有 strand，仍然出现数据竞争或非预期的交错。

**原因**：Strand 只保证**通过 strand 提交的处理程序**不会并发执行。如果你在 strand 之外（例如同步代码、另一个线程、或在未包装的处理程序中）直接访问共享数据，strand 无能为力。

**解决**：

```cpp
// 错误：sync_read 在主线程直接访问 shared_data_
// 即使 do_async 通过 strand 提交，sync_read 没被保护
std::vector<int> shared_data_;

void sync_read() {
    for (int v : shared_data_) { /* 数据竞争！ */ }
}

void do_async() {
    asio::post(strand_, [this] {
        shared_data_.push_back(42);
    });
}

// 正确：所有访问都通过 strand
void sync_read() {
    asio::dispatch(strand_, [this] {
        for (int v : shared_data_) { /* 安全 */ }
    });
}
```

### 4.4 阻塞 io_context 线程

**现象**：一个异步操作的回调中执行了长时间同步工作，导致其他异步操作的回调严重延迟。

**原因**：`io_context::run()` 在单个线程上串行执行所有就绪的回调。如果某个回调阻塞（同步 sleep、大量计算、同步 I/O），该线程上的其他所有回调都被饥饿。

**解决**：

```cpp
// 错误：回调中阻塞
timer.async_wait([&](std::error_code) {
    std::this_thread::sleep_for(std::chrono::seconds(10));  // 阻塞整个 io_context！
    do_real_work();
});

// 正确：将重计算 post 到线程池
timer.async_wait([&](std::error_code) {
    // 将重计算交给专门的线程池
    std::thread([this] {
        heavy_computation();
        // 计算完成后，post 结果回 io_context
        asio::post(ctx, [this, result] { handle_result(result); });
    }).detach();
});
```

### 4.5 从完成处理程序抛异常

**现象**：程序调用 `std::terminate()`，没有正常的异常信息。

**原因**：Asio 使用 `noexcept` 规范运行完成处理程序。如果回调抛出异常且未被内部捕获，Asio 调用 `std::terminate()`。这是有意设计——在回调中抛异常意味着"我的 io_context 处于不可恢复状态"。

**解决**：**永远不要在异步完成处理程序中让异常逃逸**。

```cpp
// 错误：异常逃逸
timer.async_wait([](std::error_code) {
    throw std::runtime_error("oops");  // → std::terminate()
});

// 正确：内部处理所有异常
timer.async_wait([](std::error_code) {
    try {
        risky_operation();
    } catch (const std::exception& e) {
        // 记录错误，但不要让异常逃逸
        std::cerr << "Error in handler: " << e.what() << std::endl;
    }
});
```

### 4.6 忘记绑定 executor 到内部 handler

**现象**：使用 strand 包装了顶层 handler，但内部（嵌套）的异步操作回调没有被包装，导致 strand 保护失效。

**原因**：`asio::post(strand, handler)` 只包装最外层的 handler。如果 handler 内部发起新的异步操作，该操作的回调不会被自动包装。

**解决**：使用 `bind_executor` 将 strand 绑定到所有异步操作。

```cpp
// 错误：inner_read 的回调没有 strand 保护
asio::post(strand_, [this] {
    // 这个在 strand 中执行 ✓
    socket_.async_read_some(buffer,
        [this](auto ec, auto n) {  // 这个不在 strand 中 ✗
            handle_read(ec, n);
        });
});

// 正确：bind_executor 绑定 strand
socket_.async_read_some(buffer,
    asio::bind_executor(strand_,
        [this](auto ec, auto n) {  // 现在在 strand 中执行 ✓
            handle_read(ec, n);
        }));
```

---

## 五、扩展阅读

### 官方文档

- [Boost.Asio 官方文档](https://www.boost.org/doc/libs/release/doc/html/boost_asio.html) — 最权威的参考
- [Asio 独立版文档](https://think-async.com/Asio/) — 无需 Boost
- [Asio 教程与示例](https://www.boost.org/doc/libs/release/doc/html/boost_asio/tutorial.html) — 官方教程，涵盖了 Timer、Daytime、Echo 等经典示例

### 核心概念深入

- [io_context 基本原理](https://www.boost.org/doc/libs/release/doc/html/boost_asio/overview/core/basics.html) — 深入理解 `run()` / `poll()` / `run_one()` 的区别
- [Proactor 设计模式](https://www.boost.org/doc/libs/release/doc/html/boost_asio/overview/core/async.html) — Asio 作者 Chris Kohlhoff 对 Proactor 模式的阐述
- [Strand 详解](https://www.boost.org/doc/libs/release/doc/html/boost_asio/overview/core/strands.html) — strand 的不同实现策略（lock-based vs lock-free）

### 书籍

- *Boost.Asio C++ Network Programming* (John Torjo, 2013) — 专注 Asio 网络编程的实用书籍
- *C++ Networking* 系列 (Richard Thomson) — 基于 Asio 的 C++ 网络编程教程，YouTube 上有对应视频

### 相关教程

- [[10-asio-coroutines|Boost.Asio Part 2 — 协程集成]] — 下一步：将协程与 Asio 结合
- [[11-sender-receiver|Sender/Receiver 模型（P2300）]] — 理解 C++26 异步模型的统一设计

> [!note] 独立版 asio vs Boost.Asio
> 独立版 asio（`-DASIO_STANDALONE`）是 Boost.Asio 的纯头文件版本，不需要链接 Boost 库。两者的 API 几乎完全一致，只在命名空间上有差异（`asio::` vs `boost::asio::`）。对于本教程的示例，使用独立版即可，无需安装整个 Boost。
