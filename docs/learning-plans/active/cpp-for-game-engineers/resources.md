---
title: "推荐学习资源汇总"
updated: 2026-06-05
---

# 推荐学习资源汇总

> 按学习阶段分类。标注 [必读][推荐][进阶][参考] 四个等级。

---

## 核心书籍

- **[必读] Effective Modern C++** (Scott Meyers, 2014) — 移动语义、完美转发、智能指针的最佳实践圣经。涵盖 C++11/14。
- **[必读] C++ Concurrency in Action (2nd ed.)** (Anthony Williams, 2019) — C++ 并发圣经。第 5 章内存序是全网最佳讲解之一。
- **[推荐] A Tour of C++ (3rd ed.)** (Bjarne Stroustrup, 2022) — C++20 精华速览，快速建立现代 C++ 全貌。
- **[推荐] C++ Templates: The Complete Guide (2nd ed.)** (Vandevoorde, Josuttis, Gregor, 2017) — 模板权威参考，需要时查，不必通读。
- **[推荐] Game Engine Architecture (3rd ed.)** (Jason Gregory, 2018) — 游戏引擎工程全景，与 C++ 知识互补。
- **[进阶] Data-Oriented Design** (Richard Fabian, 2018) — 数据导向设计的实战手册，免费在线版。
- **[进阶] Optimized C++** (Kurt Guntheroth, 2016) — C++ 性能优化专论，缓存、字符串、数据结构优化。

## 官方标准文档

- **[参考] C++ Reference** — https://en.cppreference.com/ — 每日必查的在线标准库文档
- **[参考] C++17 Standard (N4659)** — https://timsong-cpp.github.io/cppwp/n4659/ — 标准草案全文
- **[参考] C++20 Standard (N4868)** — https://timsong-cpp.github.io/cppwp/n4868/
- **[参考] C++23 Standard (N4950)** — https://timsong-cpp.github.io/cppwp/n4950/
- **[参考] Compiler Explorer** — https://godbolt.org/ — 在线查看任何 C++ 代码的编译结果，学习编译期行为的必备工具

## 游戏引擎 C++ 专项

- **[必读] Unreal Engine C++ Coding Standard** — https://docs.unrealengine.com/en-US/ProductionPipelines/DevelopmentSetup/CodingStandard/ — UE 的 C++ 规范，大量实战考量
- **[推荐] EASTL (Electronic Arts Standard Template Library)** — https://github.com/electronicarts/EASTL — EA 的开源 STL 替代实现，学习引擎级 STL 设计
- **[推荐] EnTT** — https://github.com/skypjack/entt — 最快的 C++ ECS 库，模板元编程的极致展示
- **[推荐] Tracy Profiler** — https://github.com/wolfpld/tracy — C++ 性能分析器，学习插桩宏设计
- **[进阶] Google Abseil** — https://abseil.io/ — Google 的 C++ 库，许多设施（如 SwissTable）已成为 C++ 标准的重要参考

## 内存与分配器

- **[必读] "What Every Programmer Should Know About Memory"** (Ulrich Drepper, 2007) — 内存层次结构经典
- **[推荐] mimalloc** — https://github.com/microsoft/mimalloc — 微软高性能通用分配器，源码精炼值得学习
- **[推荐] jemalloc** — https://jemalloc.net/ — FreeBSD 的内存分配器，Facebook 大规模使用

## 并发与无锁编程

- **[必读] "Memory Barriers: a Hardware View for Software Hackers"** (Paul McKenney) — 理解内存屏障的最佳短文
- **[推荐] 1024cores.net** (Dmitry Vyukov) — Lock-Free 算法详解，包括著名的 MPMC 队列
- **[进阶] "Is Parallel Programming Hard, And, If So, What Can You Do About It?"** (Paul McKenney) — Linux RCU 作者的长篇巨著，免费在线

## 在线课程与视频

- **[推荐] CppCon Back to Basics 系列** — YouTube 搜索 "CppCon Back to Basics" — 每年都有高质量基础回顾
- **[推荐] "The Bits Between the Bits"** (Matt Godbolt) — CppCon 演讲，编译器行为深度分析
- **[进阶] "Designing a Fast, Efficient, Cache-friendly Hash Table"** (Matt Kulukundis, CppCon 2017) — SwissTable 设计详解

## 博客与持续学习资源

- **[必读] Raymond Chen's The Old New Thing** — https://devblogs.microsoft.com/oldnewthing/ — Windows 内部机制，理解平台层
- **[推荐] Bartosz Milewski's Programming Cafe** — https://bartoszmilewski.com/ — 从范畴论视角看 C++ 与并发
- **[推荐] The r/cpp subreddit** — https://reddit.com/r/cpp — C++ 社区讨论，追踪标准提案进展
- **[参考] C++ Weekly (YouTube)** — Jason Turner 的每周 C++ 技巧

---

## 工具

| 工具 | 用途 | 必备程度 |
|------|------|---------|
| Compiler Explorer (godbolt.org) | 查看编译结果 | ⭐⭐⭐⭐⭐ |
| Quick Bench | 微基准性能对比 | ⭐⭐⭐⭐ |
| C++ Insights | 编译器视角查看模板展开 | ⭐⭐⭐⭐⭐ |
| Valgrind / ASan | 内存错误检测 | ⭐⭐⭐⭐ |
| perf / VTune | CPU 性能分析 | ⭐⭐⭐⭐⭐ |
| Tracy | 实时性能剖析（引擎级） | ⭐⭐⭐⭐⭐ |
| Ccache / sccache | 编译缓存加速 | ⭐⭐⭐ |
