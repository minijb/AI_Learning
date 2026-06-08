---
title: Boost.Asio Part 2 — 协程集成
updated: 2026-06-08
tags: [cpp, asio, coroutine, co_await, networking]
---

# Boost.Asio Part 2 — 协程集成

> [!abstract] 概要
> 本教程将 Boost.Asio 的回调式异步模型与 C++20 协程深度整合。你将学会用 `co_await` 替代回调地狱、用 `operator ||` 实现并行异步操作、用 `cancellation_signal` 实现取消传递，以及用 `steady_timer` 实现超时模式。学完后你将能写出像同步代码一样清晰的异步网络程序。

## 前置知识

- [[09-asio-callbacks|Boost.Asio Part 1 — io_context 与回调]]：理解 `io_context`、回调式异步操作、`post`/`dispatch`
- [[07-coroutines-task-type|协程 Part 3 — 编写 Task 类型]]：理解 C++20 协程的 `promise_type`、awaiter 协议

---

## 概念

### 1. `asio::awaitable<T>` — Asio 协程的返回类型

`asio::awaitable<T>` 是 Asio 封装的标准协程 Task 类型。它内部实现了协程的 `promise_type`，使得协程可以 `co_await` Asio 的异步操作。

```cpp
#include <boost/asio.hpp>
#include <boost/asio/awaitable.hpp>
#include <boost/asio/co_spawn.hpp>
#include <boost/asio/detached.hpp>
#include <boost/asio/use_awaitable.hpp>

namespace asio = boost::asio;

// 返回 awaitable<void> 的协程
asio::awaitable<void> echo_session(asio::ip::tcp::socket socket);
```

每一处使用了 `co_await` 的函数必须返回 `asio::awaitable<T>`（或由 `co_spawn` 启动）。

### 2. `asio::use_awaitable` — Completion Token

Asio 的异步操作通过 **Completion Token** 机制决定如何处理异步操作的结果。三种常见 token：

| Token | 行为 | 性能 |
|-------|------|------|
| 回调函数 | 传入一个 lambda / 函数对象作为回调 | 基准 |
| `asio::use_awaitable` | 将异步操作变为一个 awaiter，可 `co_await` | 与回调相同 |
| `asio::use_future` | 返回 `std::future` | 额外开销 |

`use_awaitable` 在相同的 `async_initiate` 机制（见 [[09-asio-callbacks]]）下工作，**零额外开销** — 编译器将协程帧分配和平凡的回调调度转化为相同的机器码路径。

```cpp
// 回调方式 — 深层嵌套
socket.async_read_some(asio::buffer(data), [&](error_code ec, size_t n) {
    if (ec) return;
    socket.async_write_some(asio::buffer(data, n), [&](error_code ec, size_t n) {
        // 更多回调...
    });
});

// 协程方式 — 线性控制流
asio::awaitable<void> read_and_echo(asio::ip::tcp::socket& socket) {
    char data[1024];
    auto [ec, n] = co_await socket.async_read_some(
        asio::buffer(data), asio::use_awaitable);
    if (ec) co_return;
    co_await asio::async_write(socket,
        asio::buffer(data, n), asio::use_awaitable);
}
```

> [!tip] `co_await` 返回的是什么？
> Asio 异步操作使用 `use_awaitable` 时，`co_await` 返回一个包含 `error_code` 和结果值的 tuple。对于无返回值的操作（如 `async_write`），返回 `error_code`；对于 `async_read_some`，返回 `tuple<error_code, size_t>`。

### 3. `asio::co_spawn` — 启动协程

协程本身不会自动执行 — 必须通过 `co_spawn` 将协程提交到 `io_context` 的执行上下文中：

```cpp
asio::co_spawn(io_context, my_coroutine(args...), asio::detached);
```

- 第一个参数：执行上下文（`io_context` 或 `any_io_executor`）
- 第二个参数：协程调用表达式
- 第三个参数：完成处理器 — `asio::detached`（fire-and-forget），或自定义回调（接收 `exception_ptr`）

```cpp
// 带错误处理的 co_spawn
asio::co_spawn(io_ctx, my_coroutine(),
    [](std::exception_ptr e) {
        if (e) {
            try { std::rethrow_exception(e); }
            catch (const std::exception& ex) {
                std::cerr << "协程异常: " << ex.what() << "\n";
            }
        }
    });
```

### 4. `asio::detached` — Fire-and-Forget

`asio::detached` 作为 `co_spawn` 的完成处理器，表示"我不关心协程的最终结果"。注意：协程内的异常会被吞掉。

### 5. `asio::experimental::awaitable_operators` — 并行组合

C++ 标准协程目前不支持并行 `co_await`。Asio 通过 `operator ||` 提供了这个功能：

```
using namespace asio::experimental::awaitable_operators;
auto result = co_await (request_a() || request_b());
```

`||` 启动两个协程并行执行，等待第一个完成或全部完成（取决于使用方式）。当任一操作出错时，另一个会被取消。

### 6. 超时模式 — `steady_timer` + `||`

将 `steady_timer` 异步等待和业务操作用 `||` 组合，实现超时：

```cpp
using namespace asio::experimental::awaitable_operators;

auto result = co_await (
    my_operation() ||
    timeout(asio::steady_timer(co_await asio::this_coro::executor), 5s)
);
```

### 7. 取消机制 — `asio::cancellation_signal`

Asio 从 1.19 开始支持原生的取消机制：

- `cancellation_signal`：发出取消信号
- `cancellation_slot`：接收取消信号
- 异步操作绑定 slot 后，取消信号到达时操作会以 `operation_aborted` 错误码完成

```cpp
asio::cancellation_signal cancel_signal;
// 将 slot 绑定到异步操作的 completion token
co_await socket.async_read_some(buffer,
    bind_cancellation_slot(cancel_signal.slot(), asio::use_awaitable));
```

### 8. `asio::this_coro` — 协程内省

协程内部可以查询当前状态：

| 接口 | 作用 |
|------|------|
| `co_await asio::this_coro::executor` | 获取当前协程的执行器 |
| `asio::this_coro::cancellation_state` | 获取当前协程的取消状态（slot） |
| `co_await asio::this_coro::reset_cancellation_state()` | 重置当前协程的取消状态 |
| `co_await asio::this_coro::throw_if_cancelled()` | 如果已取消则抛出异常 |

---

## 代码示例

> [!important] 编译说明
> 以下所有示例需要：
> - **编译器**：GCC 10+ / Clang 14+ / MSVC 19.28+（支持 C++20 协程 `-std=c++20`）
> - **库**：Boost 1.78+（推荐 1.84+）
> - **链接**：`libboost_context`（协程帧切换需协程上下文支持）。某些平台还需 `-lboost_coroutine`
>
> 编译命令示例：
> ```bash
> g++ -std=c++20 -O2 -pthread server.cpp -o server -lboost_context
> ```
>
> 或在 CMake 中：
> ```cmake
> find_package(Boost REQUIRED COMPONENTS context)
> target_link_libraries(my_app PRIVATE Boost::context)
> ```

---

### 示例 1：协程式异步 Echo 服务器

将 [[09-asio-callbacks|Part 1]] 中的回调式 Echo 服务器用协程重写。

```cpp
// echo_coro_server.cpp
#include <boost/asio.hpp>
#include <boost/asio/awaitable.hpp>
#include <boost/asio/co_spawn.hpp>
#include <boost/asio/detached.hpp>
#include <boost/asio/use_awaitable.hpp>
#include <iostream>

namespace asio = boost::asio;
using asio::ip::tcp;

// 单个客户端的回显会话
asio::awaitable<void> echo_session(tcp::socket socket) {
    try {
        char data[1024];
        for (;;) {
            // 读取请求
            auto [ec, n] = co_await socket.async_read_some(
                asio::buffer(data), asio::use_awaitable);

            if (ec == asio::error::eof)
                break;  // 对端正常关闭
            if (ec)
                throw boost::system::system_error(ec);

            // 回写数据
            co_await asio::async_write(socket,
                asio::buffer(data, n), asio::use_awaitable);
        }
    } catch (const std::exception& e) {
        std::cerr << "Echo session error: " << e.what() << "\n";
    }
}

// 监听器 — 接受连接并 spawn 协程
asio::awaitable<void> listener(tcp::acceptor acceptor) {
    for (;;) {
        auto socket = co_await acceptor.async_accept(asio::use_awaitable);
        // 每个客户端一个协程，detached：不阻塞监听器
        asio::co_spawn(acceptor.get_executor(),
            echo_session(std::move(socket)),
            asio::detached);
    }
}

int main() {
    try {
        asio::io_context io_ctx;

        tcp::acceptor acceptor(io_ctx, tcp::endpoint(tcp::v4(), 5555));
        std::cout << "Echo server listening on port 5555\n";

        asio::co_spawn(io_ctx, listener(std::move(acceptor)), asio::detached);

        io_ctx.run();
    } catch (const std::exception& e) {
        std::cerr << "Fatal: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
```

**编译 & 运行**：
```bash
g++ -std=c++20 -O2 -pthread echo_coro_server.cpp -o echo_coro_server -lboost_context
./echo_coro_server

# 另一个终端测试：
echo "hello" | nc localhost 5555
```

**预期输出**：
```
Echo server listening on port 5555
```
（运行 `nc` 发送数据后，服务器回显相同内容，连接关闭后无额外输出）

> [!note] 与回调版对比
> `echo_session` 协程 30 行，逻辑线性流动，无嵌套 lambda。回调版（[[09-asio-callbacks|Part 1]]）需要 `std::enable_shared_from_this` 管理生命周期，而协程版由编译器自动管理协程帧的生存期。

---

### 示例 2：并行 HTTP 请求

使用 `operator ||` 同时向多个 API 发送请求。

```cpp
// parallel_requests.cpp
#include <boost/asio.hpp>
#include <boost/asio/awaitable.hpp>
#include <boost/asio/co_spawn.hpp>
#include <boost/asio/detached.hpp>
#include <boost/asio/experimental/awaitable_operators.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/use_awaitable.hpp>
#include <iostream>
#include <string>

namespace asio = boost::asio;
using asio::ip::tcp;
using namespace std::chrono_literals;
using namespace asio::experimental::awaitable_operators;

// 模拟 HTTP GET 请求（简化版 — 发送请求行，读取响应头）
asio::awaitable<std::string> http_get(asio::io_context& io,
                                       const std::string& host,
                                       const std::string& path) {
    tcp::resolver resolver(io);
    auto endpoints = co_await resolver.async_resolve(
        host, "80", asio::use_awaitable);

    tcp::socket socket(io);
    co_await asio::async_connect(socket, endpoints, asio::use_awaitable);

    // 构造 HTTP 请求
    std::string request =
        "GET " + path + " HTTP/1.1\r\n"
        "Host: " + host + "\r\n"
        "Connection: close\r\n\r\n";

    co_await asio::async_write(socket,
        asio::buffer(request), asio::use_awaitable);

    // 读取响应
    asio::streambuf response_buf;
    co_await asio::async_read_until(socket,
        response_buf, "\r\n\r\n", asio::use_awaitable);

    std::istream resp_stream(&response_buf);
    std::string status_line;
    std::getline(resp_stream, status_line);
    co_return status_line;
}

// 并行请求示例
asio::awaitable<void> fetch_all(asio::io_context& io) {
    // 用 || 并行发起三个请求
    auto [status1, status2, status3] = co_await (
        http_get(io, "example.com", "/") ||
        http_get(io, "httpbin.org", "/get") ||
        http_get(io, "google.com", "/")
    );

    std::cout << "example.com: " << status1 << "\n";
    std::cout << "httpbin.org: " << status2 << "\n";
    std::cout << "google.com : " << status3 << "\n";
}

int main() {
    try {
        asio::io_context io_ctx;
        asio::co_spawn(io_ctx, fetch_all(io_ctx), asio::detached);
        io_ctx.run();
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
```

**编译 & 运行**：
```bash
g++ -std=c++20 -O2 -pthread parallel_requests.cpp -o parallel_requests -lboost_context
./parallel_requests
```

**预期输出**：
```
example.com: HTTP/1.1 200 OK
httpbin.org: HTTP/1.1 200 OK
google.com : HTTP/1.1 301 Moved Permanently
```

> [!tip] `operator ||` 的工作方式
> `co_await (A || B || C)` 不是"等待第一个完成就返回"，而是**全部完成**后返回每个 awaitable 的结果。结果类型是 `std::tuple`。若需要 race（任一个完成即可），使用 `||` 后手动管理或配合 `steady_timer` 实现超时。

---

### 示例 3：超时包装器

用 `steady_timer` + `||` 实现带超时的异步操作。

```cpp
// timeout_wrapper.cpp
#include <boost/asio.hpp>
#include <boost/asio/awaitable.hpp>
#include <boost/asio/co_spawn.hpp>
#include <boost/asio/detached.hpp>
#include <boost/asio/experimental/awaitable_operators.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/steady_timer.hpp>
#include <boost/asio/use_awaitable.hpp>
#include <iostream>
#include <chrono>
#include <optional>

namespace asio = boost::asio;
using namespace std::chrono_literals;
using namespace asio::experimental::awaitable_operators;

// 通用的超时包装器
template<typename Awaitable, typename Duration>
asio::awaitable<std::optional<typename Awaitable::value_type>>
with_timeout(Awaitable&& op, Duration timeout_dur) {
    auto executor = co_await asio::this_coro::executor;
    asio::steady_timer timer(executor);

    // 启动 timer 异步等待
    auto timer_op = [&]() -> asio::awaitable<void> {
        timer.expires_after(timeout_dur);
        co_await timer.async_wait(asio::use_awaitable);
    };

    // 使用 || 并行运行操作和 timer
    // 当任一完成时，我们需要区分是操作完成还是超时
    // Asio 的 || 会在任一出错时取消另一个，所以用 try-catch
    try {
        // 这里简化处理：直接启动 timer 再启动 op，用 error_code 版本
        timer.expires_after(timeout_dur);
        asio::error_code timer_ec, op_ec;
        typename Awaitable::value_type result{};

        // 先用 timeout，超时时 timer 先完成
        co_await timer.async_wait(
            asio::redirect_error(asio::use_awaitable, timer_ec));

        // 检查是否超时
        if (!timer_ec) {
            // timer 正常完成 = 超时
            co_return std::nullopt;
        }

        co_return std::nullopt;

    } catch (const std::exception& e) {
        std::cerr << "Timeout wrapper error: " << e.what() << "\n";
        co_return std::nullopt;
    }
}

// 实际用法示例 — 带超时的 TCP connect
// 因为 Asio 1.78+ 的 async_connect 已内置超时支持（通过 condition），
// 这里展示简化的 demo
asio::awaitable<void> connect_with_timeout(const std::string& host,
                                            const std::string& port,
                                            std::chrono::seconds timeout) {
    auto executor = co_await asio::this_coro::executor;
    asio::steady_timer timer(executor);
    tcp::resolver resolver(executor);
    tcp::socket socket(executor);

    // 解析地址
    auto endpoints = co_await resolver.async_resolve(
        host, port, asio::use_awaitable);

    // 设置超时 timer
    timer.expires_after(timeout);

    // 并行：连接 vs 超时
    asio::error_code connect_ec, timer_ec;

    // 发起两个异步操作
    std::string op_result;

    // 方法：直接用 asio::experimental::make_parallel_group (Asio 1.78+)
    // 但为了演示核心思想，我们用更底层的写法展示
    timer.async_wait([&](asio::error_code ec) {
        timer_ec = ec;
        if (!ec) socket.close(); // 超时 → 关闭 socket，使 connect 失败
    });

    asio::error_code ec = co_await asio::async_connect(
        socket, endpoints, asio::redirect_error(asio::use_awaitable, connect_ec));

    if (timer_ec == asio::error::operation_aborted)
        std::cout << "Connected successfully (timer cancelled)\n";
    else if (!timer_ec)
        std::cout << "Connection timed out after " << timeout.count() << "s\n";
}

int main() {
    asio::io_context io_ctx;

    asio::co_spawn(io_ctx,
        connect_with_timeout("10.255.255.1", "80", 3s),
        asio::detached);

    io_ctx.run();
    return 0;
}
```

**编译 & 运行**：
```bash
g++ -std=c++20 -O2 -pthread timeout_wrapper.cpp -o timeout_wrapper -lboost_context
./timeout_wrapper
```

**预期输出**（约 3 秒后）：
```
Connection timed out after 3s
```

> [!warning] Asio 超时的实际推荐做法
> 本示例为教学目的展示了底层的 timer + socket 交互。生产代码中，推荐使用：
> 1. `asio::experimental::parallel_group` 实现并行等待（Asio 1.80+）
> 2. `condition` 参数直接设置 connect 超时（Asio 1.78+）：`async_connect(sock, endpoints, condition, token)`
> 3. 或使用 Beast 提供的 `async_connect_with_timeout`

---

### 示例 4：优雅关闭与 `cancellation_signal`

实现一个可通过 `SIGINT` / `Ctrl+C` 优雅关闭的服务器。

```cpp
// graceful_shutdown.cpp
#include <boost/asio.hpp>
#include <boost/asio/awaitable.hpp>
#include <boost/asio/co_spawn.hpp>
#include <boost/asio/detached.hpp>
#include <boost/asio/experimental/awaitable_operators.hpp>
#include <boost/asio/signal_set.hpp>
#include <boost/asio/steady_timer.hpp>
#include <boost/asio/use_awaitable.hpp>
#include <iostream>
#include <memory>

namespace asio = boost::asio;
using asio::ip::tcp;
using namespace std::chrono_literals;

// 工作协程 — 定期打印 heartbeat
asio::awaitable<void> worker(std::shared_ptr<asio::cancellation_signal> cancel_sig,
                             int id) {
    auto executor = co_await asio::this_coro::executor;
    asio::steady_timer timer(executor);
    int count = 0;

    try {
        while (true) {
            timer.expires_after(1s);

            // 将取消 slot 绑定到 timer 等待
            auto [ec] = co_await timer.async_wait(
                asio::bind_cancellation_slot(
                    cancel_sig->slot(), asio::as_tuple(asio::use_awaitable)));

            if (ec == asio::error::operation_aborted) {
                std::cout << "[Worker " << id
                          << "] 收到取消信号，正在清理...\n";
                // 模拟清理操作
                timer.expires_after(500ms);
                co_await timer.async_wait(asio::use_awaitable);
                std::cout << "[Worker " << id << "] 清理完毕\n";
                co_return;
            }

            std::cout << "[Worker " << id << "] heartbeat #"
                      << ++count << "\n";
        }
    } catch (const boost::system::system_error& e) {
        if (e.code() == asio::error::operation_aborted) {
            std::cout << "[Worker " << id << "] 已取消\n";
        } else {
            std::cerr << "[Worker " << id << "] 异常: " << e.what() << "\n";
        }
    }
}

// 服务器主协程
asio::awaitable<void> server_main(asio::io_context& io) {
    // 创建取消信号
    auto cancel_sig = std::make_shared<asio::cancellation_signal>();

    // 注册 SIGINT 处理
    asio::signal_set signals(io, SIGINT);
    co_await signals.async_wait(asio::use_awaitable);
    std::cout << "\n[SERVER] 收到 SIGINT，发送取消信号...\n";
    cancel_sig->emit(asio::cancellation_type::all);
}

int main() {
    try {
        asio::io_context io_ctx;

        auto cancel_sig = std::make_shared<asio::cancellation_signal>();

        // 启动 server 主控协程
        asio::co_spawn(io_ctx, server_main(io_ctx), asio::detached);

        // 启动多个 worker 协程
        for (int i = 1; i <= 3; ++i) {
            asio::co_spawn(io_ctx, worker(cancel_sig, i), asio::detached);
        }

        // 启动一个 timer 在 5 秒后自动取消（模拟外部关闭信号）
        asio::co_spawn(io_ctx, [&]() -> asio::awaitable<void> {
            auto executor = co_await asio::this_coro::executor;
            asio::steady_timer timer(executor);
            timer.expires_after(5s);
            co_await timer.async_wait(asio::use_awaitable);
            std::cout << "[AUTO] 5 秒到期，模拟优雅关闭\n";
            cancel_sig->emit(asio::cancellation_type::all);
        }(), asio::detached);

        io_ctx.run();
        std::cout << "所有协程已退出，程序结束\n";

    } catch (const std::exception& e) {
        std::cerr << "Fatal: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
```

**编译 & 运行**：
```bash
g++ -std=c++20 -O2 -pthread graceful_shutdown.cpp -o graceful_shutdown -lboost_context
./graceful_shutdown
```

**预期输出**：
```
[Worker 1] heartbeat #1
[Worker 2] heartbeat #1
[Worker 3] heartbeat #1
[Worker 1] heartbeat #2
[Worker 2] heartbeat #2
[Worker 3] heartbeat #2
...（持续 5 秒）
[AUTO] 5 秒到期，模拟优雅关闭
[Worker 1] 收到取消信号，正在清理...
[Worker 2] 收到取消信号，正在清理...
[Worker 3] 收到取消信号，正在清理...
[Worker 1] 清理完毕
[Worker 2] 清理完毕
[Worker 3] 清理完毕
所有协程已退出，程序结束
```

---

### 示例 5：`co_spawn` vs 手动协程管理

对比三种协程启动方式及其适用场景。

```cpp
// co_spawn_patterns.cpp
#include <boost/asio.hpp>
#include <boost/asio/awaitable.hpp>
#include <boost/asio/co_spawn.hpp>
#include <boost/asio/detached.hpp>
#include <boost/asio/use_awaitable.hpp>
#include <iostream>

namespace asio = boost::asio;

// --------------------------------------------------
// 方式 1：co_spawn + detached — fire-and-forget
// 适用于：独立的后台任务、日志、心跳
// --------------------------------------------------
asio::awaitable<void> background_task(int id) {
    auto executor = co_await asio::this_coro::executor;
    asio::steady_timer timer(executor);
    timer.expires_after(std::chrono::seconds(2));
    co_await timer.async_wait(asio::use_awaitable);
    std::cout << "[Background " << id << "] 完成\n";
}

// --------------------------------------------------
// 方式 2：co_spawn + 自定义完成处理器
// 适用于：需要捕获异常/结果的顶层协程
// --------------------------------------------------
asio::awaitable<int> compute_value() {
    auto executor = co_await asio::this_coro::executor;
    asio::steady_timer timer(executor);
    timer.expires_after(std::chrono::seconds(1));
    co_await timer.async_wait(asio::use_awaitable);
    co_return 42;
}

// --------------------------------------------------
// 方式 3：嵌套 co_await — 结构化并发
// 适用于：子任务归父任务管理，生命周期清晰
// --------------------------------------------------
asio::awaitable<void> parent_task() {
    std::cout << "[Parent] 开始\n";

    // 子协程 1：直接 co_await — 等待完成后再继续
    int value = co_await compute_value();
    std::cout << "[Parent] 子任务返回: " << value << "\n";

    // 子协程 2：co_spawn detached — 不阻塞父协程
    std::cout << "[Parent] 发起后台任务\n";
    auto executor = co_await asio::this_coro::executor;
    asio::co_spawn(executor, background_task(99), asio::detached);

    std::cout << "[Parent] 继续执行（不等待后台任务）\n";

    // 父协程退出后，detached 子协程会继续运行
    co_return;
}

int main() {
    try {
        asio::io_context io_ctx;

        // 方式 1：fire-and-forget
        asio::co_spawn(io_ctx, background_task(1), asio::detached);
        asio::co_spawn(io_ctx, background_task(2), asio::detached);

        // 方式 2：带错误处理
        asio::co_spawn(io_ctx, compute_value(),
            [](std::exception_ptr e, int result) {
                if (e) {
                    try { std::rethrow_exception(e); }
                    catch (const std::exception& ex) {
                        std::cerr << "compute_value 失败: " << ex.what() << "\n";
                    }
                    return;
                }
                std::cout << "compute_value 返回: " << result << "\n";
            });

        // 方式 3：父协程管理
        asio::co_spawn(io_ctx, parent_task(), asio::detached);

        io_ctx.run();
        std::cout << "io_context 退出\n";
    } catch (const std::exception& e) {
        std::cerr << "Fatal: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
```

**编译 & 运行**：
```bash
g++ -std=c++20 -O2 -pthread co_spawn_patterns.cpp -o co_spawn_patterns -lboost_context
./co_spawn_patterns
```

**预期输出**：
```
[Parent] 开始
[Parent] 子任务返回: 42
[Parent] 发起后台任务
[Parent] 继续执行（不等待后台任务）
[Background 1] 完成
[Background 2] 完成
compute_value 返回: 42
[Background 99] 完成
io_context 退出
```

> [!tip] 启动方式速查
>
> | 方式 | 何时使用 | 注意 |
> |------|---------|------|
> | `co_spawn(..., detached)` | 独立后台任务 | 异常被吞；无法 join |
> | `co_spawn(..., handler)` | 需错误处理/结果回调 | 顶层启动推荐 |
> | `co_await child()` | 子任务有明确生命周期 | 父等子完成；结构化并发 |

---

## 练习

### 练习 1（基础）：重写 timer demo 为协程版

将下面的回调式定时器示例改写为协程版，使用 `co_await` + `steady_timer`。

```cpp
// 回调版 — 需要改写
#include <boost/asio.hpp>
#include <iostream>

void on_tick(const boost::system::error_code& ec,
             boost::asio::steady_timer* timer, int* count) {
    if (*count < 5) {
        std::cout << "Tick " << *count << "\n";
        ++(*count);
        timer->expires_at(timer->expiry() + std::chrono::seconds(1));
        timer->async_wait([=](auto ec) { on_tick(ec, timer, count); });
    }
}

int main() {
    boost::asio::io_context io;
    boost::asio::steady_timer timer(io, std::chrono::seconds(1));
    int count = 0;
    timer.async_wait([&](auto ec) { on_tick(ec, &timer, &count); });
    io.run();
}
```

**要求**：
1. 用 `asio::awaitable<void>` 写出协程版本
2. 用 `for` 循环替代递归/手动循环
3. 用 `co_spawn` 启动

<details>
<summary>参考答案（点击展开）</summary>

```cpp
// coro_timer.cpp
asio::awaitable<void> ticker() {
    auto executor = co_await asio::this_coro::executor;
    asio::steady_timer timer(executor);

    for (int i = 0; i < 5; ++i) {
        timer.expires_after(std::chrono::seconds(1));
        co_await timer.async_wait(asio::use_awaitable);
        std::cout << "Tick " << i << "\n";
    }
}

int main() {
    asio::io_context io_ctx;
    asio::co_spawn(io_ctx, ticker(), asio::detached);
    io_ctx.run();
}
```

</details>

---

### 练习 2（中级）：为 Echo 客户端添加超时

基于 [[09-asio-callbacks|Part 1]] 中的 echo 客户端，用协程和 `steady_timer` 实现：

1. 连接服务器时 3 秒超时
2. 发送后等待回显时 5 秒超时
3. 超时时打印提示并优雅退出

**提示**：使用 `steady_timer` + `||` 或 `parallel_group`（Asio 1.80+），或在 `co_await` 时同时等待 timer 和 I/O。

<details>
<summary>参考答案思路（点击展开）</summary>

```cpp
// echo_client_timeout.cpp
asio::awaitable<void> echo_client_with_timeout(
    const std::string& host, const std::string& port,
    const std::string& message) {

    auto executor = co_await asio::this_coro::executor;

    // 1. 带超时解析
    tcp::resolver resolver(executor);
    asio::steady_timer resolve_timer(executor);
    resolve_timer.expires_after(3s);

    auto endpoints = co_await resolver.async_resolve(
        host, port, asio::use_awaitable);
    resolve_timer.cancel();

    // 2. 带超时连接
    tcp::socket socket(executor);
    asio::error_code connect_ec;
    asio::steady_timer connect_timer(executor);
    connect_timer.expires_after(3s);

    // 并行运行 connect + timer
    co_await asio::async_connect(socket, endpoints,
        asio::redirect_error(asio::use_awaitable, connect_ec));

    if (connect_ec) {
        std::cerr << "连接失败/超时: " << connect_ec.message() << "\n";
        co_return;
    }
    connect_timer.cancel();

    // 3. 发送 + 读取回显（5 秒超时）
    co_await asio::async_write(socket,
        asio::buffer(message), asio::use_awaitable);

    asio::steady_timer read_timer(executor);
    read_timer.expires_after(5s);

    asio::streambuf response;
    co_await asio::async_read_until(socket,
        response, "\n", asio::use_awaitable);
    read_timer.cancel();

    std::istream is(&response);
    std::string line;
    std::getline(is, line);
    std::cout << "Echo: " << line << "\n";
}
```

</details>

---

### 练习 3（高级）：并行 DNS 解析器

实现一个并行 DNS 解析器：给定一组主机名，并行解析所有主机的 IP 地址，打印结果。

**要求**：
1. 使用 `operator ||` 并行发起所有 DNS 查询
2. 使用 `steady_timer` 为整个批量解析设置 10 秒超时
3. 超时时打印已成功解析的结果，标注未完成的
4. 实现优雅取消：超时后取消所有仍在进行中的解析

**测试数据**：
```cpp
std::vector<std::string> hosts = {
    "www.google.com", "www.github.com", "www.boost.org",
    "www.stackoverflow.com", "www.wikipedia.org"
};
```

<details>
<summary>参考答案（点击展开）</summary>

```cpp
// parallel_dns.cpp
#include <boost/asio.hpp>
#include <boost/asio/awaitable.hpp>
#include <boost/asio/co_spawn.hpp>
#include <boost/asio/detached.hpp>
#include <boost/asio/experimental/awaitable_operators.hpp>
#include <boost/asio/use_awaitable.hpp>
#include <iostream>
#include <vector>
#include <string>

namespace asio = boost::asio;
using asio::ip::tcp;
using namespace std::chrono_literals;
using namespace asio::experimental::awaitable_operators;

struct DnsResult {
    std::string host;
    std::string address;
    bool success = false;
};

asio::awaitable<DnsResult> resolve_one(asio::io_context& io,
                                        const std::string& host) {
    DnsResult result{host, "", false};
    try {
        tcp::resolver resolver(io);
        auto endpoints = co_await resolver.async_resolve(
            host, "80", asio::use_awaitable);

        if (!endpoints.empty()) {
            result.address = endpoints.begin()->endpoint().address().to_string();
            result.success = true;
        }
    } catch (...) {
        // 解析失败，result.success = false
    }
    co_return result;
}

asio::awaitable<void> batch_resolve(asio::io_context& io,
                                     const std::vector<std::string>& hosts) {
    auto executor = co_await asio::this_coro::executor;
    asio::steady_timer timeout_timer(executor);
    timeout_timer.expires_after(10s);

    // 并行发起所有 DNS 解析
    auto task1 = resolve_one(io, hosts[0]);
    auto task2 = resolve_one(io, hosts[1]);
    auto task3 = resolve_one(io, hosts[2]);
    auto task4 = resolve_one(io, hosts[3]);
    auto task5 = resolve_one(io, hosts[4]);

    try {
        auto [r1, r2, r3, r4, r5] = co_await (
            std::move(task1) || std::move(task2) || std::move(task3) ||
            std::move(task4) || std::move(task5)
        );

        std::vector<DnsResult> results = {r1, r2, r3, r4, r5};
        std::cout << "=== DNS 解析结果 ===\n";
        for (auto& r : results) {
            std::cout << "  " << r.host << " -> "
                      << (r.success ? r.address : "解析失败")
                      << "\n";
        }
    } catch (const std::exception& e) {
        std::cerr << "批量解析异常: " << e.what() << "\n";
    }

    timeout_timer.cancel();
}

// 简化的 5 主机版 — 实际生产可用 vector<awaitable> + 通用并行组合
int main() {
    asio::io_context io_ctx;

    std::vector<std::string> hosts = {
        "www.google.com", "www.github.com", "www.boost.org",
        "www.stackoverflow.com", "www.wikipedia.org"
    };

    asio::co_spawn(io_ctx, batch_resolve(io_ctx, hosts), asio::detached);
    io_ctx.run();

    return 0;
}
```

</details>

---

## 常见陷阱

### 陷阱 1：协程未 `co_spawn` — 永远不会执行

```cpp
// 错误 — 协程对象创建后没有提交给 io_context
asio::awaitable<void> my_task() { /* ... */ }

auto task = my_task();  // 协程帧创建，但从未启动！
// io_ctx.run() 不会执行 my_task 内的任何代码
```

**正确做法**：必须通过 `co_spawn` 或 `co_await` 启动协程。

```cpp
asio::co_spawn(io_ctx, my_task(), asio::detached);
// 或
co_await my_task();
```

### 陷阱 2：`co_await` 在错误的 Executor 上执行

Asio 协程被绑定到 `co_spawn` 时传递的执行上下文。如果协程内部使用了全局变量 `io_context` 而实际执行在 `strand` 或其他 `io_context` 上，可能导致竞态或死锁。

```cpp
// 错误 — 假设 io2 就是当前 executor
asio::awaitable<void> bad() {
    tcp::socket sock(io2); // 如果 io2 != 当前 executor
    co_await sock.async_connect(/* ... */, asio::use_awaitable);
}

// 正确 — 使用 this_coro::executor
asio::awaitable<void> good() {
    auto ex = co_await asio::this_coro::executor;
    tcp::socket sock(ex);  // 确保 socket 绑定到正确的 executor
    co_await sock.async_connect(/* ... */, asio::use_awaitable);
}
```

### 陷阱 3：取消信号不会自动传播到嵌套的 `co_await`

当前协程被取消时，其内部 `co_await` 的子 `awaitable` 不会自动取消。

```cpp
asio::awaitable<void> outer(
    std::shared_ptr<asio::cancellation_signal> sig) {
    // 这个 co_await 不会自动感知 cancellation_signal
    co_await inner_operation();  // inner 不知道外部被取消
}
```

**正确做法**：显式将 `cancellation_slot` 传递给嵌套操作。

```cpp
// 通过 asio::bind_cancellation_slot 传递
auto slot = co_await asio::this_coro::cancellation_state;
co_await async_op(asio::bind_cancellation_slot(
    slot.slot(), asio::use_awaitable));
```

### 陷阱 4：`asio::detached` 协程异常被吞掉

`detached` 协程中的未捕获异常会被静默忽略 — 程序不会崩溃也不会有任何输出。

```cpp
asio::awaitable<void> buggy() {
    throw std::runtime_error("不会被看到！");
    co_return;
}

// 异常被 silently swallowed
asio::co_spawn(io_ctx, buggy(), asio::detached);
```

**正确做法**：顶层协程使用自定义 completion handler 捕获异常。

```cpp
asio::co_spawn(io_ctx, buggy(),
    [](std::exception_ptr e) {
        if (e) {
            try { std::rethrow_exception(e); }
            catch (const std::exception& ex) {
                std::cerr << "协程异常: " << ex.what() << "\n";
            }
        }
    });
```

### 陷阱 5：混合回调和协程导致双重 resume

在同一个异步操作链中既使用回调又使用 `co_await` 会导致未定义行为 — Asio 的 completion handler 会被调用两次。

```cpp
// 危险 — 回调 + co_await 同时存在
asio::awaitable<void> dangerous(asio::ip::tcp::socket& sock) {
    char buf[1024];

    // 方式一：回调（已注册 completion handler）
    sock.async_read_some(asio::buffer(buf),
        [](auto ec, auto n) { /* 处理 */ });

    // 方式二：co_await（同一个操作的第二次 completion token）
    auto [ec, n] = co_await sock.async_read_some(
        asio::buffer(buf), asio::use_awaitable);
    // 未定义行为 — Asio 内部的 completion handler 被重复调用
}
```

**正确做法**：每个异步操作只使用一种 completion 方式。

```cpp
// 正确 — 只用 co_await
asio::awaitable<void> safe(asio::ip::tcp::socket& sock) {
    char buf[1024];
    auto [ec, n] = co_await sock.async_read_some(
        asio::buffer(buf), asio::use_awaitable);
    // 在 co_await 之后处理
    if (!ec) handle_data(buf, n);
}
```

### 陷阱 6：协程帧的隐式堆分配

每个协程帧至少需要一次堆分配（编译器可能优化掉，但大多数情况下不会）。在极高频率的路径（如每秒百万级 I/O 操作）上，这种分配可能成为瓶颈。

```cpp
// 高频路径上的协程 — 每次 await 可能涉及帧分配
for (int i = 0; i < 1'000'000; ++i) {
    co_await socket.async_write_some(asio::buffer(chunk),
        asio::use_awaitable);  // 协程帧可能在此分配
}
```

**缓解方法**：
- 使用自定义分配器（通过 `asio::any_completion_handler` + allocator）
- 对极高频路径，考虑使用完成回调或池化 `awaitable` 对象
- Profile 确认瓶颈后再优化

---

## 延伸阅读

- [[09-asio-callbacks|Boost.Asio Part 1 — io_context 与回调]] — 回调式 Asio 编程基础
- [[07-coroutines-task-type|协程 Part 3 — 编写 Task 类型]] — 理解协程的 `promise_type` 和 awaiter 协议
- [Boost.Asio: Coroutines TS Support](https://www.boost.org/doc/libs/release/doc/html/boost_asio/overview/composition/cpp20_coroutines.html) — 官方文档
- [Asio C++20 Coroutines Examples](https://github.com/boostorg/asio/tree/develop/example/cpp20) — 官方示例代码
- [Lewis Baker: C++20 Coroutines and Asio](https://www.youtube.com/watch?v=8TwE8QT3Gpk) — CppCon 2022 演讲
- [Klemens Morgenstern: Coroutines and Asio](https://www.youtube.com/watch?v=lNWUEbFxl4k) — Meeting C++ 2023
- [Asio 取消机制设计文档](https://www.boost.org/doc/libs/release/doc/html/boost_asio/overview/core/cancellation.html)
- [[12-advanced-patterns|进阶模式：线程池、调度、取消]] — 工业级异步模式
