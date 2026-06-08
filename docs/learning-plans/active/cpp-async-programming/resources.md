---
title: C++ 异步编程 — 推荐资源
updated: 2026-06-08
tags: [cpp, async, resources]
---

# 推荐资源汇总

## 官方文档与标准

- [cppreference: Concurrency support library](https://en.cppreference.com/w/cpp/thread) — `std::thread`, `std::mutex`, `std::future` 等全部 API
- [cppreference: Coroutines (C++20)](https://en.cppreference.com/w/cpp/language/coroutines) — 协程语言规范
- [P2300R10: `std::execution`](https://wg21.link/P2300) — Sender/Receiver 异步模型提案
- [C++ Draft: exec](https://eel.is/c++draft/exec) — 最新草案中的 execution 库章节

## 书籍

- **C++ Concurrency in Action (2nd Edition)** — Anthony Williams · 2019
  C++ 并发编程的权威之作，覆盖线程、锁、原子操作、无锁数据结构、并行算法。C++17。
- **C++ High Performance (2nd Edition)** — Björn Andrist, Viktor Sehr · 2020
  涵盖并发、协程、SIMD 等现代 C++ 高性能编程主题。
- **The C++ Standard Library (2nd Edition)** — Nicolai M. Josuttis
  对 `<thread>`, `<future>`, `<atomic>` 等库组件有详细讲解。

## 在线教程与博客

- [Lewis Baker: C++ Coroutines — Understanding the promise type](https://lewissbaker.github.io/2018/09/05/understanding-the-promise-type)
  深入理解协程 `promise_type` 的经典文章。
- [Lewis Baker: C++ Coroutines — Understanding operator co_await](https://lewissbaker.github.io/2017/11/17/understanding-operator-co-await)
  协程 awaiter 协议的详细解析。
- [Eric Niebler: What Are Senders Good For, Anyway?](https://ericniebler.com/2024/02/04/what-are-senders-good-for-anyway/)
  Sender/Receiver 模型的实战应用。
- [Lucian Teodorescu: Senders/Receivers in C++](https://lucteo.ro/2024/08/12/senders-receivers-in-cxx/)
  P2300 模型的系统介绍。
- [Boost.Asio Documentation](https://www.boost.org/doc/libs/release/doc/html/boost_asio.html)
  官方文档，含教程和示例。
- [ACCU Overload 184: From std::async to P2300 Senders/Receivers](https://accu.org/journals/overload/32/184/teodorescu/)
  从 `std::async` 到 Sender/Receiver 的演进历史。

## 视频

- **CppCon 2022: C++20 Coroutines — The Low Level Interface** — Andreas Fertig
- **CppCon 2023: Senders and Receivers in C++** — Eric Niebler
- **CppNow 2024: Using the C++ Sender/Receiver Framework** — Steve Downey
- **ACCU 2025: C++ Coroutines Demystified** — Phil Nash
- **Meeting C++ 2023: Asynchronous Programming with Boost.Asio + Coroutines**

## 开源库

- [Boost.Asio](https://github.com/boostorg/asio) — 跨平台异步 I/O 库（已进入标准化轨道）
- [cppcoro](https://github.com/lewissbaker/cppcoro) — Lewis Baker 的协程库（参考实现，教学价值极高）
- [libunifex](https://github.com/facebookexperimental/libunifex) — Meta 的 Sender/Receiver 原型实现
- [stdexec](https://github.com/NVIDIA/stdexec) — NVIDIA 的 `std::execution` 参考实现
- [folly::coro](https://github.com/facebook/folly) — Facebook 的工业级协程框架

## 工具

- [Compiler Explorer](https://godbolt.org/) — 在线查看协程代码的汇编输出
- [C++ Insights](https://cppinsights.io/) — 查看协程的编译器变换
