# Disruptor 模式对比

> 基于笔记: drafts/test-lockfree-queue.md
> 所属教程: Lockfree Queue 深度分析
> 章: 5/6

---

## 1. LMAX Disruptor 是什么

LMAX Disruptor 是 LMAX 交易所（英国外汇交易平台）于 2011 年开源的**高性能线程间消息传递框架**。它的核心声称是：在特定的设计约束下，Disruptor 可以**比传统 lockfree queue 快 3-10x**。

> [来源] Martin Thompson et al., "LMAX Disruptor: High Performance Inter-Thread Messaging Library", 2011
> [来源] 原笔记引用: 1024cores.net 中有与 Disruptor 的对比讨论

**关键数字**（原始论文 + 后续 benchmark）：
- 单生产者单消费者：约 **25M ops/sec**（对比 ArrayBlockingQueue 的 ~5M ops/sec）
- 多生产者单消费者：约 **22M ops/sec**
- 延迟：P99 < 100ns（在 tuned JVM 上）

## 2. Disruptor 的核心设计

Disruptor 从根本上重新思考了"队列"——它不把数据从 slot 移到 slot，而是**所有数据预分配在一个巨大的 ring buffer 中，线程通过 sequence number 协调进度**。

### 2.1 预分配 Ring Buffer

```cpp
// 传统 lockfree queue
queue.push(item);   // item 被"移动"到队列内部存储
queue.pop(item);    // item 被"移动"出来

// Disruptor 方式
RingBuffer<OrderEvent> ring_buffer(SIZE);
long seq = ring_buffer.next();     // 声明下一个 slot
OrderEvent& event = ring_buffer[seq];  // 直接写入预分配的 slot
event.price = 1234;
event.quantity = 100;
ring_buffer.publish(seq);          // 发布
```

**为什么这更快？**

- **零分配**：所有 Event 对象在构造 RingBuffer 时一次性分配，生产和消费过程中没有 new/delete
- **零拷贝**：数据从不移动——生产者写入 slot，消费者直接读同一个 slot 的引用
- **缓存友好**：连续内存布局，预取（prefetch）可预测

### 2.2 Sequence Barrier（序列屏障）

Disruptor 的核心同步机制不是 CAS，而是**顺序号的依赖关系**：

```
Producer (Sequence: 1003)
    |
    ├── 写入 slot 1003 完成
    |
RingBuffer
    |
Consumer 1 (依赖 Producer, 消费到 998)
Consumer 2 (依赖 Consumer 1, 消费到 995)  ← 处理慢的消费者
Consumer 3 (依赖 Producer, 消费到 1002)
```

每个消费者维护自己的**消费进度（sequence number）**。关键机制：

- **生产者不能覆盖尚未被最慢消费者读完的 slot**（通过 `gatingSequences` 机制）
- **消费者不能读取生产者尚未发布的 slot**
- **依赖消费者之间的处理顺序**：Consumer 2 必须等 Consumer 1 处理完后才能继续

**Sequence Barrier 的核心操作**：`waitFor(sequence)` —— 阻塞直到目标 sequence 可用。这个等待是基于 `volatile`（Java）或 `atomic`（C++ port）的自旋——但没有 CAS 竞争。

> [来源] Disruptor Technical Paper, LMAX, 2011

### 2.3 为什么没有 CAS 竞争？

Disruptor 的 sequence 是**每个线程独占写入**的：

- 每个生产者线程有自己独立的 claimed sequence（在 `MultiProducerSequencer` 中先 CAS 获得 slot，然后写入——这一步和 MPMC queue 的 CAS 类似）
- 但**发布顺序和声明顺序允许不一致**：Thread A 声明 slot 1001，Thread B 声明 slot 1002。B 可以比 A 先写入完成。但 `publish` 操作确保消费者只读到已经发布的最长连续 prefix。

这就是 Disruptor 的 `availableBuffer` 机制——一个 bit 数组追踪哪些 slot 已完成写入。消费者通过 `waitFor(N)` 循环检查 `availableBuffer`，而不是 CAS head。

```cpp
// 简化的 MultiProducerSequencer::publish
void publish(long sequence) {
    // 设置 availability flag
    // 使用 release store → 消费者 acquire load 可见
    availableBuffer_.set(sequence & mask_);
    cursor_.store(sequence, std::memory_order_release);
}

// 简化的消费者 waitFor
long waitFor(long sequence) {
    long available = cursor_.load(std::memory_order_acquire);
    while (available < sequence) {
        // spin wait with backoff
        available = cursor_.load(std::memory_order_acquire);
    }
    return available;
}
```

## 3. Disruptor vs Lockfree Queue 深度对比

### 3.1 架构对比

```
Traditional SPSC Lockfree Queue:
+----------+     +-----+-----+-----+-----+     +----------+
| Producer | --> |     |     |     |     | --> | Consumer |
+----------+     +-----+-----+-----+-----+     +----------+
                 head →                 ← tail
                 每个 slot 先被生产者写入，再被消费者读取（两阶段）

Disruptor:
+----------+     +-----+-----+-----+-----+     +----------+     +----------+
| Producer | --> |  0  |  1  |  2  |  3  | --> | Consumer | --> | Consumer |
+----------+     +-----+-----+-----+-----+     |    1     |     |    2     |
                                    |          +----------+     +----------+
                                    v
                             Ring Buffer (up to 2^31 slots)
                             所有数据预分配，永不移动
```

### 3.2 性能关键差异

| 维度 | Traditional SPSC Queue | Disruptor |
|------|----------------------|-----------|
| **内存分配** | 每次 push 可能分配（或预分配 buffer slot） | 启动时一次性分配全部 event |
| **数据移动** | item 从参数拷贝/移动到 buffer | 引用写入，无数据移动 |
| **同步原语** | 2 atomic load + 2 atomic store（SPSC） | sequence load（消费者），sequence store（生产者） |
| **CAS 使用** | 无（SPSC）| 无（单一生产者）；CAS（多生产者声明 slot）|
| **多消费者支持** | 每个消费者需要独立队列 | 内置多消费者 + 依赖链 |
| **背压处理** | 队列满 → 丢弃/阻塞 | gating sequence 自动反压 |
| **批处理** | 需要手动循环 pop | `waitFor(N)` 天然支持批处理 |
| **事件对象生命周期** | 出队后销毁 | 永不销毁，循环覆盖 |

### 3.3 延迟特性

```
                Traditional Queue          Disruptor
                =================          =========
P50 延迟:       ~50-100 ns                ~30-50 ns
P99 延迟:       ~200-500 ns (CAS 重试)     ~60-100 ns
P99.9 延迟:     ~1-10 μs (GC/分配)         ~150 ns
```

Disruptor 的延迟分布更**紧凑**——因为：
- 没有动态分配 → 没有 GC 暂停（Java）或 allocator 竞争（C++）
- 没有 CAS 重试 → 延迟不随竞争增加而恶化
- 预分配 → cache 行为可预测

> 数据来源 `[推测]` — 综合 LMAX 原始论文和社区 benchmark

## 4. Disruptor 的 C++ 移植：关键实现

虽然 Disruptor 原始是 Java 项目，但 C++ 生态中有多个移植：

- **[Disruptor-cpp](https://github.com/Abc-Arbitrage/Disruptor-cpp)** — 最完整的 C++11/14 移植
- **[Folly MPMCQueue](https://github.com/facebook/folly)** — Meta 的高性能 MPMC 队列，吸收了 Disruptor 的预分配思想

C++ 移植的核心挑战：

1. **对象生命周期**：Java 有 GC，C++ 没有。预分配意味着 event 对象在队列全生命周期内存在——需要小心管理析构语义。
2. **模板化**：Java 泛型在运行时擦除，C++ 模板在编译时实例化——RingBuffer 的 buffer 数组类型安全但代码膨胀。
3. **内存序**：Java `volatile` 有不同于 C++ `atomic` 的语义——C++ 移植需要精确使用 `acquire`/`release`。

简化的 C++ Disruptor 核心：

```cpp
#include <atomic>
#include <vector>
#include <cstddef>

template<typename T, size_t SIZE>
class DisruptorRingBuffer {
    static_assert((SIZE & (SIZE - 1)) == 0);
    static constexpr size_t MASK = SIZE - 1;

    T buffer_[SIZE];

    // 生产者进度
    alignas(64) std::atomic<size_t> cursor_{-1};
    // 消费者进度
    alignas(64) std::atomic<size_t> gating_sequence_{-1};

public:
    // 生产者：声明下一个 slot
    size_t next() {
        size_t next_seq = cursor_.load(std::memory_order_relaxed) + 1;

        // 确保不覆盖未消费的 slot
        // gating_sequence 是最慢消费者的进度
        while (next_seq - gating_sequence_.load(std::memory_order_acquire) > SIZE) {
            // spin with backoff — 等待消费者追上
            _mm_pause();
        }

        return next_seq;
    }

    // 写入 slot（无锁，因为只有一个生产者）
    T& at(size_t sequence) {
        return buffer_[sequence & MASK];
    }

    // 发布——消费者从此可见
    void publish(size_t sequence) {
        // release: 保证 buffer 写入对消费者可见
        cursor_.store(sequence, std::memory_order_release);
    }

    // 消费者：等待到目标 sequence 可用
    size_t wait_for(size_t sequence) {
        size_t available = cursor_.load(std::memory_order_acquire);
        while (available < sequence) {
            _mm_pause();
            available = cursor_.load(std::memory_order_acquire);
        }
        return available;
    }

    // 消费者：更新消费进度（让生产者知道可覆盖）
    void commit(size_t sequence) {
        // release 保证消费者的读取操作在 sequence 更新前完成
        gating_sequence_.store(sequence, std::memory_order_release);
    }
};
```

**和 SPSC Queue 的关键差异**：

- SPSC Queue 的 `full check` 是 `(tail - head) >= SIZE-1`，检查的是**当前时刻**的差值
- Disruptor 的 `gating_sequence` 检查是**最慢消费者的长期进度**——允许消费者"落后"多个 slot，生产者持续填充前面的 slot（只要不覆盖未消费的）

这在**消费者处理速度不恒定**的场景中至关重要：Disruptor 允许消费者在处理复杂事件时短暂落后，生产者不必被单个 slot 的满/空卡住。

## 5. 什么时候 Disruptor 比 Lockfree Queue 更快？

### Disruptor 更快（3-10x）的场景：

1. **事件对象较大（>64 bytes）**：避免拷贝的收益巨大
2. **需要多级消费者管道**（A→B→C）：Disruptor 内置依赖链，传统方案需要多个队列 + 协调
3. **消费者处理速度不均匀**：gating sequence 容忍暂时落后
4. **批处理场景**：`waitFor(N)` 天然支持批量消费
5. **延迟要求极严格**（P99 < 100ns）：消除 CAS 竞争 + 预分配 → 延迟紧凑

### 传统 Lockfree Queue 更合适的场景：

1. **事件对象小（指针/整数）**：拷贝成本可忽略
2. **只需要简单的 1P1C**：SPSC queue 实现更简单、错误更少
3. **队列容量要求动态调整**：Disruptor 的预分配要求固定大小
4. **C++ 对象有复杂析构逻辑**：预分配+循环覆盖的语义难以处理非 trivially destructible 的类型
5. **团队不熟悉 Disruptor 范式**：维护成本 > 性能收益

## 6. 游戏引擎中的应用

| 引擎/项目 | 使用 | 备注 |
|-----------|------|------|
| Unreal Engine | **不用 Disruptor** | 使用自定义 SPSC/MPSC 队列，事件对象通常较小（FScopeLock, FGraphEvent） |
| Unity | **不用 Disruptor** | Job System 用 ring buffer，但设计理念偏传统 lockfree |
| Bungie (Destiny) | 类似 Disruptor 的 ring buffer | 2015 GDC 演讲提到预分配 ring buffer 处理粒子系统事件 |
| EA Frostbite | 自定义 Job System | 队列批处理 + 工作窃取，吸取了 Disruptor 的批处理思想 |
| 独立引擎（EnTT, flecs） | SPSC 队列为主 | ECS 世界中事件队列通常是多 SPSC，而非 MPMC |

**行业观察** `[推测]`：游戏引擎普遍避免 Disruptor 的复杂依赖链模型，原因：
1. 游戏事件通常是 fire-and-forget，不同消费者独立处理——不需要 Disruptor 的依赖链
2. Cocos/Unity/Unreal 的 Job System 已提供了足够的工作分发自调度
3. Disruptor 的预分配固定容量与动态场景不匹配（玩家行为驱动的事件数量不可预测）

---

*上一章: [Memory Order 在无锁队列中的应用](04-memory-order.md)* | *下一章: [总结与延伸](06-summary.md)*
