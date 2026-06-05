# Lockfree Queue 深度分析教程

> 基于笔记 `drafts/test-lockfree-queue.md` 展开的深度教程，逐层剖析无锁队列的原理、实现与优化。

## 原始笔记

来自 [1024cores.net Lock-Free Queues](https://www.1024cores.net/home/lock-free-algorithms/queues) 的阅读笔记，提问四个核心问题。

## 目录

| 章节 | 文件 | 回答的问题 |
|------|------|-----------|
| 1 | [01-why-lockfree-queue.md](./01-why-lockfree-queue.md) | 为什么需要 Lockfree Queue？ |
| 2 | [02-spsc-queue-fundamentals.md](./02-spsc-queue-fundamentals.md) | SPSC Queue 的基本设计与 Ring Buffer |
| 3 | [03-spin-wait-optimization.md](./03-spin-wait-optimization.md) | Q1: Spin 循环如何避免浪费 CPU？ |
| 4 | [04-spsc-vs-mpmc.md](./04-spsc-vs-mpmc.md) | Q2: MPMC 与 SPSC 的区别？ |
| 5 | [05-memory-ordering.md](./05-memory-ordering.md) | Q3: memory_order_acquire/release 怎么用？ |
| 6 | [06-disruptor-comparison.md](./06-disruptor-comparison.md) | Q4: 和 Disruptor 模式比谁更快？ |

## 引用来源

- [1024cores.net — Lock-Free Algorithms: Queues](https://www.1024cores.net/home/lock-free-algorithms/queues) (Dmitriy V'jukov)
- [Preshing on Programming — An Introduction to Lock-Free Programming](https://preshing.com/20120612/an-introduction-to-lock-free-programming/)
- [cppreference.com — std::memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order)
- [LMAX Disruptor User Guide](https://lmax-exchange.github.io/disruptor/user-guide/index.html)
- [Stack Overflow — What is the purpose of the "PAUSE" instruction in x86?](https://stackoverflow.com/questions/12894078/what-is-the-purpose-of-the-pause-instruction-in-x86)
- [Intel Software Developer Manuals — PAUSE Instruction](https://www.felixcloutier.com/x86/pause)
- [Medium — Lock-Free Bounded Queue, Made Understandable](https://medium.com/bytecraft/lock-free-bounded-queue-made-understandable) (Vyukov-style MPMC)
- [moodycamel.com — A Fast Lock-Free Queue for C++](https://moodycamel.com/blog/a-fast-lock-free-queue-for-c++)
- [Mechanical Sympathy Blog — Dissecting the Disruptor](https://mechanitis.blogspot.com/2011/06/dissecting-disruptor-whats-so-special.html)
