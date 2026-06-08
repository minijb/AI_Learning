---
title: C++ 异步编程学习计划
updated: 2026-06-08
tags: [cpp, async, concurrency, coroutines, learning-plan]
---

# 学习计划：C++ 异步编程

> 创建日期：2026-06-08
> 预计总耗时：约 18 小时（12 节 × 60–90 分钟）
> 目标水平：精通（从基础到 C++26 前沿）

---

## 学习目标

完成本计划后，你将能够：

- 理解 C++ 线程模型与同步原语（`std::thread`、`std::mutex`、`std::condition_variable`）
- 使用 `std::async` / `std::future` / `std::promise` 实现任务级异步
- 理解 C++20 协程的完整机制：`co_await`、`co_yield`、`promise_type`、awaiter 协议
- 从零实现自定义 Task 类型和 Generator 类型
- 使用 Boost.Asio 构建高性能异步 I/O 应用，并集成 C++20 协程
- 理解 C++26 `std::execution`（Sender/Receiver / P2300）模型及其设计哲学
- 掌握线程池、任务调度器、取消机制、异步错误处理等进阶模式

## 前置要求

- [x] C++ 基础语法（C++11 以上）
- [x] 基本的模板编程（理解 `template<typename T>`）
- [x] 对操作系统线程有初步概念
- [ ] 了解 RAII 和智能指针（推荐先看 [[raii-complete-analysis]]）

## 学习路径

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|:-----|:-------|:---------|:-----|:-----|
| 1 | [[01-threads-and-synchronization\|线程与同步原语]] | 60min | 基础 | 无 |
| 2 | [[02-async-future-promise\|std::async 与 future/promise]] | 60min | 基础 | 1 |
| 3 | [[03-packaged-task-shared-future\|packaged_task 与 shared_future]] | 45min | 基础 | 2 |
| 4 | [[04-atomics-memory-order\|原子操作与内存序]] | 75min | 进阶（可选） | 1 |
| 5 | [[05-coroutines-co-await\|协程 Part 1：co_await 与 Awaitable]] | 75min | 核心 | 2 |
| 6 | [[06-coroutines-promise-type\|协程 Part 2：promise_type 深入]] | 75min | 核心 | 5 |
| 7 | [[07-coroutines-task-type\|协程 Part 3：编写 Task 类型]] | 90min | 核心 | 6 |
| 8 | [[08-generator-co-yield\|Generator 与 co_yield]] | 60min | 核心 | 6 |
| 9 | [[09-asio-callbacks\|Boost.Asio Part 1：io_context 与回调]] | 60min | 应用 | 1, 2 |
| 10 | [[10-asio-coroutines\|Boost.Asio Part 2：协程集成]] | 60min | 应用 | 7, 9 |
| 11 | [[11-sender-receiver\|Sender/Receiver 模型（P2300）]] | 75min | 前沿（可选） | 7, 9 |
| 12 | [[12-advanced-patterns\|进阶模式：线程池、调度、取消]] | 60min | 进阶 | 7, 9 |

## 里程碑

- [ ] 第一阶段（第 1–3 节）：能用 `std::async` + `std::future` 写异步任务，理解基本同步机制
- [ ] 第二阶段（第 5–8 节）：理解协程的完整机制，能从零实现 Task 和 Generator
- [ ] 第三阶段（第 9–10 节）：能用 Boost.Asio + 协程写异步 TCP 服务器
- [ ] 第四阶段（第 11–12 节）：理解 C++26 异步模型和工业级异步模式

### 最终项目

用 Boost.Asio + C++20 协程实现一个 **多客户端异步 TCP Echo 服务器**，支持：
- 同时处理多个客户端连接
- 超时断开空闲连接
- 优雅关闭（graceful shutdown）
- 线程池执行器
