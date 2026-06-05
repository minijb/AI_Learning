# Lockfree Queue 深度分析

> 基于笔记: drafts/test-lockfree-queue.md
> 生成日期: 2026-06-05
> 关键词: lockfree queue, SPSC, MPMC, memory_order, acquire-release, Disruptor, CAS, ring buffer, spin optimization, game engine, thread communication

## 原笔记摘要

原笔记从 1024cores.net 的 lockfree queue 教程出发，记录了游戏引擎中主线程和渲染线程通信时避免 mutex 抖动的需求。笔记给出了 SPSC ring buffer 的基本伪代码，并提出四个待深入的问题：spin 如何避免浪费 CPU、MPMC 与 SPSC 的区别、memory_order_acquire/release 的应用、以及 Disruptor 模式的性能对比。

## 章节导航

| 序号 | 章节 | 文件 | 核心内容 |
|------|------|------|----------|
| 1 | 核心概念：Lockfree SPSC 队列 | [01-core-concept.md](01-core-concept.md) | Ring buffer 设计、基本 C++ 实现、为什么 SPSC 不需要 CAS |
| 2 | CPU 自旋优化策略 | [02-spin-optimization.md](02-spin-optimization.md) | _mm_pause → yield → adaptive backoff → futex 五层递进策略 |
| 3 | MPMC 多生产者多消费者队列 | [03-mpmc-queue.md](03-mpmc-queue.md) | CAS 循环、per-slot sequence、false sharing 防护、Vyukov 风格完整实现 |
| 4 | Memory Order 在无锁队列中的应用 | [04-memory-order.md](04-memory-order.md) | acquire/release 配对模式、完整生产级 SPSC 实现、与 Treiber Stack 的内存序对比 |
| 5 | Disruptor 模式对比 | [05-disruptor-comparison.md](05-disruptor-comparison.md) | 预分配 ring buffer、sequence barrier、gating sequence、C++ 移植、性能取舍 |
| 6 | 总结与延伸 | [06-summary.md](06-summary.md) | 四问总结、技术选型决策树、关键 insight、延伸阅读资源 |

## 关键收获

1. **SPSC 队列不需要 CAS** —— 指针所有权分离（生产者独占 tail、消费者独占 head）自然实现了 lockfree，仅需 atomic load+store，延迟 ~10ns
2. **Spin 优化的精髓是根据等待时间选择退避策略** —— `_mm_pause` 适合 100ns 级、yield 适合 μs 级、futex 适合 ms 级。游戏引擎应优先用 pause+backoff，避免在主线程上 yield
3. **Acquire/release 形成跨线程的 happens-before 链** —— 生产者 buffer 写入 → release store tail → consumer acquire load tail → 读取 buffer 数据，这条链保证数据可见性。离开这条链就是数据竞争
4. **Disruptor 快不是因为算法聪明，而是因为改变了问题** —— 预分配消除分配开销、sequence number 替代数据移动、gating sequence 容忍消费速度不恒定。代价是固定容量和更高的设计复杂度
5. **"Lockfree 替代 mutex" 的真正价值不是吞吐量，而是避免优先级反转和死锁** —— 在无竞争时，mutex fast path（futex，~25ns）和 MPMC CAS loop 差不多。Lockfree 的不可替代性在于系统级进展保证

## 延伸阅读

| 资源 | 说明 |
|------|------|
| [1024cores.net - Lock-Free Queues](http://www.1024cores.net/home/lock-free-algorithms/queues) | 原笔记来源。Dmitry Vyukov 的无锁算法全集 |
| [LMAX Disruptor Technical Paper](https://lmax-exchange.github.io/disruptor/disruptor.html) | Martin Thompson 原始论文，详细设计动机和性能分析 |
| [folly::ProducerConsumerQueue](https://github.com/facebook/folly/blob/main/folly/ProducerConsumerQueue.h) | Meta 的生产级 SPSC 实现 |
| [MoodyCamel::ConcurrentQueue](https://github.com/cameron314/concurrentqueue) | 最流行的 C++ MPMC 无锁队列 |
| [Preshing on Programming - Lock-Free](https://preshing.com/20120612/an-introduction-to-lock-free-programming/) | Jeff Preshing 的 lockfree 入门，内存序解释的黄金标准 |
| [C++ Concurrency in Action (2nd Ed.)](https://www.manning.com/books/c-plus-plus-concurrency-in-action-second-edition) | Anthony Williams 著作，第 7 章专讲无锁数据结构 |
| [`cpp-memory-order-game-engine.md`](../../../../docs/deep-dives/cpp-memory-order-game-engine.md) | 本工作区关联的 C++ 内存序深度分析，第 4 章的前置阅读 |
