# 第 6 章：Q4 — 和 Disruptor 模式比谁更快？

## 问题回顾

笔记中问：Lockfree Queue 和 Disruptor 模式比较，谁更快？

## Disruptor 是什么？

LMAX Disruptor 是由英国金融交易公司 LMAX 在 2011 年开源的高性能线程间消息传递库（[LMAX Disruptor User Guide](https://lmax-exchange.github.io/disruptor/user-guide/index.html)，[Mechanical Sympathy Blog](https://mechanitis.blogspot.com/2011/06/dissecting-disruptor-whats-so-special.html)）。

核心架构：**环形缓冲区 + 序列号屏障 (Sequence Barrier) + 多播事件处理器**。

### 关键设计

```
     Producer 1 ──┐
     Producer 2 ──┤
                  ├──→ Ring Buffer (pre-allocated slots)
     Producer N ──┘         │
                    ┌───────┼───────┐
                    ↓       ↓       ↓
               Consumer A  Consumer B  Consumer C
              (各自独立的 sequence counter)
```

不同于传统队列的 FIFO 模型，Disruptor 的核心概念：

1. **无竞争发布**：每个生产者持有自己的 sequence counter，不用 CAS 竞争全局 head/tail。
2. **多播**：同一个事件可以被多个消费者并行读取，无需复制。
3. **无 GC 压力**（Java 语境）：slot 预分配并复用，不产生垃圾对象。
4. **Sequence Barrier**：消费者通过 barrier 等待依赖的 sequence 就位，支持 DAG 依赖图。

## 性能 Benchmark 对比

数据来自 LMAX 白皮书和社区 benchmark（引自 Google 搜索结果中 AI 概述总结）：

| 指标 | Disruptor (Ring Buffer) | ArrayBlockingQueue | Lockfree MPMC Queue |
|------|------------------------|-------------------|---------------------|
| 吞吐量 | **~6–30M ops/s** | ~3–8M ops/s | ~10–25M ops/s |
| 延迟 | **纳秒级**，低抖动 | 微秒级，高抖动 | 纳秒级，极低抖动 |
| 并发控制 | CAS + 内存屏障 | Lock (mutex) | CAS + acquire/release |
| Cache 友好 | ✅ padding 防 false sharing | ❌ 频繁 cache miss | ✅ padding 防 false sharing |
| 内存分配 | 预分配，对象复用 | 每次 enqueue 分配 Node | 预分配 ring buffer |
| GC 压力 | **零**（无分配） | 高 | **零**（预分配） |

> 注意：Disruptor 原生为 Java。Java 的 Lockfree Queue（如 `ConcurrentLinkedQueue`）由于 GC 压力和对象分配开销，吞吐量远低于 C++ 对应实现。

## 架构层面差异

| 特性 | Lockfree SPSC Queue | Lockfree MPMC Queue | LMAX Disruptor |
|------|---------------------|---------------------|----------------|
| 数据模型 | FIFO（消费即移除） | FIFO（消费即移除） | **多播**（多消费者可读同一事件） |
| 生产者模型 | 单生产者 | 多生产者 CAS 竞争 | 多生产者，每个持有独立 sequence |
| 消费者模型 | 单消费者 | 多消费者 CAS 竞争 | **DAG 依赖图**（支持分阶段流水线） |
| 消费者间依赖 | 无 | 无 | 支持（A 必须完成才能 B） |
| Wait Strategy | 需自己实现 | 需自己实现 | **内置**：BusySpin / Yielding / Sleeping / Blocking |

## 为什么 Disruptor 比普通 MPMC 队列更快？

### 1. 无竞争的生产者发布

MPMC 队列的 enqueue 需要所有生产者竞争同一个 `tail` CAS。Disruptor 使用 **MultiProducerSequencer**，虽也用 CAS 认领 slot，但：

- Claim 阶段（抢 sequence）与数据写入阶段分离。
- 使用两阶段提交：先抢号 → 再写数据 → 再发布。减少了 CAS 竞争的临界区长度。

### 2. Sequence Barrier 消除消费者竞争

普通 MPMC 队列中，消费者之间也竞争 `head` 的 CAS。Disruptor 中：

- 每个消费者有独立的 Sequence counter。
- 消费者从 Ring Buffer **多播**读取 — 同一个 slot 可以被多个消费者独立消费。
- Sequence Barrier 只读（不写）Buffer 的 cursor，无竞争。

### 3. 预分配 + 对象复用 = 零 GC

这是 Disruptor 在 Java 生态中的杀手特性。`ArrayBlockingQueue` 每次 push 创建新对象 → GC 触发 → STW 暂停 → 延迟毛刺。Disruptor 预分配 Event 对象并原地覆写，JVM 不产生新垃圾。

在 C++ 中这个优势减弱（C++ 有栈分配、placement new、自定义分配器）。但对象池化避免 `malloc`/`free` 的思路同样有效。

### 4. Mechanical Sympathy

Disruptor 设计极度关注硬件特性：

- Cache line padding（防 false sharing）
- 数据相邻排列（防 cache miss）
- 使用 `lazySet`（ordered store）替代 volatile write（减少 StoreLoad 屏障）
- 位运算取模（2 的幂 ring size）

这些同样可应用于 C++ lockfree queue。

## C++ 中的 Disruptor 风格队列

已有多个 C++ 移植/类似实现：

- [**rigtorp/MPMCQueue**](https://github.com/rigtorp/MPMCQueue)：借鉴 Disruptor 的 sequence 设计，bounded MPMC。
- [**max0x7ba/atomic_queue**](https://github.com/max0x7ba/atomic_queue)：C++14 lock-free queues，支持 SPSC/MPMC 多种变体，极致延迟优化。
- [**moodycamel::ConcurrentQueue**](https://github.com/cameron314/concurrentqueue)：工业级 MPMC，支持 bulk enqueue/dequeue。

## 何时用 Disruptor，何时用 Lockfree Queue？

| 场景 | 推荐 | 原因 |
|------|------|------|
| 简单 1:1 线程通信 | SPSC Lockfree Queue | 最简，零开销 |
| N 生产者 → M 消费者 FIFO | MPMC Lockfree Queue | 标准排队语义 |
| 事件流水线（A → B → C） | **Disruptor** | DAG 依赖图原生支持 |
| 多消费者需读同一条数据 | **Disruptor** | 多播语义，无需复制 |
| GC 语言（Java/C#） | **Disruptor** | 零对象分配，避免 GC |
| 无 GC 语言（C++/Rust） | Lockfree SPSC/MPMC | 没有 GC 压力，Disruptor 优势减弱 |
| 极致延迟（< 50ns） | C++ Lockfree SPSC | C++ 的零成本抽象优于 Java 的 Disruptor |

## 结论

**不是"谁更快"，而是"场景不同"**：

- 对于最简单的 SPSC 通信，C++ 的 lockfree SPSC queue 延迟最低（无任何框架开销）。
- 对于复杂的多阶段事件处理流水线（要求顺序保证 + 多播），Disruptor 的架构优势压倒简单 queue。
- 在 C++ 中，直接借鉴 Disruptor 的设计思想（sequence barrier、padding、预分配）到自己的 MPMC queue 实现中，可以获得逼近 Disruptor 的性能，同时保持 C++ 的零成本抽象优势。

> 游戏引擎中，SPSC Lockfree Queue 是最实用的选择：主线程→渲染线程、主线程→资源线程、主线程→音频线程，都是 1:1 通信。不需要 Disruptor 的多播和 DAG 能力。

---

*上一章：[05-memory-ordering.md](./05-memory-ordering.md)*
