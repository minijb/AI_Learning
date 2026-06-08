---
title: C++ 异步编程 — 教程索引
updated: 2026-06-08
tags: [cpp, async, index]
---

# 教程索引

## 基础篇

| 序号 | 教程 | 预计耗时 | 前置 |
|:-----|:-----|:---------|:-----|
| 1 | [[01-threads-and-synchronization|线程与同步原语]] | 60min | 无 |
| 2 | [[02-async-future-promise|std::async 与 future/promise]] | 60min | 1 |
| 3 | [[03-packaged-task-shared-future|packaged_task 与 shared_future]] | 45min | 2 |
| 4 | [[04-atomics-memory-order|原子操作与内存序]]（可选） | 75min | 1 |

## 协程篇

| 序号 | 教程 | 预计耗时 | 前置 |
|:-----|:-----|:---------|:-----|
| 5 | [[05-coroutines-co-await|协程 Part 1：co_await 与 Awaitable]] | 75min | 2 |
| 6 | [[06-coroutines-promise-type|协程 Part 2：promise_type 深入]] | 75min | 5 |
| 7 | [[07-coroutines-task-type|协程 Part 3：编写 Task 类型]] | 90min | 6 |
| 8 | [[08-generator-co-yield|Generator 与 co_yield]] | 60min | 6 |

## 生态与进阶篇

| 序号 | 教程 | 预计耗时 | 前置 |
|:-----|:-----|:---------|:-----|
| 9 | [[09-asio-callbacks|Boost.Asio Part 1：io_context 与回调]] | 60min | 1, 2 |
| 10 | [[10-asio-coroutines|Boost.Asio Part 2：协程集成]] | 60min | 7, 9 |
| 11 | [[11-sender-receiver|Sender/Receiver 模型（P2300）]]（可选） | 75min | 7, 9 |
| 12 | [[12-advanced-patterns|进阶模式：线程池、调度、取消]] | 60min | 7, 9 |
