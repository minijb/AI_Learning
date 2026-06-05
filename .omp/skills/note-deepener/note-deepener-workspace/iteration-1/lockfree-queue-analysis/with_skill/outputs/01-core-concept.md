# 核心概念：Lockfree SPSC 队列

> 基于笔记: drafts/test-lockfree-queue.md
> 所属教程: Lockfree Queue 深度分析
> 章: 1/6

---

## 1. 为什么游戏引擎需要 Lockfree Queue

游戏引擎的主线程和渲染线程、音频线程、物理线程之间需要高频交换数据。典型场景：

- **主线程 → 渲染线程**：提交 Draw Call、材质更新、变换矩阵
- **渲染线程 → 主线程**：返回 GPU 查询结果、 occlusion culling 数据
- **物理线程 → 主线程**：碰撞事件、物理体状态

传统方案是 `std::mutex` + `std::queue`：

```cpp
void SubmitDrawCall(const DrawCall& dc) {
    std::lock_guard<std::mutex> lock(mtx_);
    queue_.push(dc);
}
```

**问题**：如果渲染线程正在消费队列、持有锁，主线程尝试提交时就会阻塞。在 60 FPS（16.6ms 帧预算）约束下，一次意外的内核调度导致 mutex 竞争持续 1-2ms，就足以造成**帧率抖动（frame jitter）**——这是游戏体验中不可接受的。

Lockfree 的核心思路：**用原子 CAS（Compare-And-Swap）操作替代锁，确保至少一个线程在任何时刻都能取得进展**（lockfree 的定义：系统整体永远不阻塞）。

> **Lockfree ≠ Wait-free**：Lockfree 保证**整体**系统不会饿死，但单个线程可能无限重试。Wait-free 保证**每个**操作在有限步数内完成——实现成本更高，游戏引擎场景通常不需要。

## 2. Ring Buffer 设计

SPSC（Single Producer, Single Consumer）队列最常用的底层数据结构是**定长环形缓冲区（Fixed-Size Ring Buffer）**：

```
   +---+---+---+---+---+---+---+---+
   | A | B | C |   |   |   |   |   |
   +---+---+---+---+---+---+---+---+
     ^           ^
    head       tail
   (消费者)    (生产者)
```

- `head` 指针：指向**下一个待消费**的 slot（消费者专用，只有消费者写入）
- `tail` 指针：指向**下一个待写入**的空闲 slot（生产者专用，只有生产者写入）
- **Empty 条件**：`head == tail`（没有可消费的数据）
- **Full 条件**：`(tail + 1) % SIZE == head`（预留一个空位区分 empty 和 full）

> **为什么预留一个空位？** 如果不预留，`head == tail` 既可能表示空也可能表示满（当队列完全填满时）。预留一个 slot 是最简单且无锁的区分方式。代价是容量 = SIZE - 1。

## 3. 原笔记伪代码解析

原笔记的伪代码（经语言修正后）：

```
push(item):
  while (tail + 1) % SIZE == head:  // full → spin wait
    spin
  buffer[tail] = item
  tail = (tail + 1) % SIZE

pop():
  while head == tail:  // empty → spin wait
    spin
  item = buffer[head]
  head = (head + 1) % SIZE
  return item
```

**这段伪代码在单线程视角下逻辑正确，但在多线程环境下有三个致命问题**：

| 问题 | 描述 | 后果 |
|------|------|------|
| 1. 无内存序保护 | 对 `head`/`tail` 的读写是普通变量，无 happens-before 保证 | 消费者可能看到 `tail` 更新了但 `buffer[tail]` 的写入尚未可见——读到垃圾数据 |
| 2. 数据竞争（UB） | 多个线程同时读写非原子变量 | C++ 标准下是未定义行为，编译器可能做任何优化 |
| 3. Spin 浪费 CPU | 忙等循环无退避 | 100% CPU 占用，功耗飙升，还可能抢占对方线程的 CPU 时间 |

下面我们将逐步修复这些问题，构建一个**生产级 C++ SPSC Lockfree Queue**。

## 4. 最小可工作实现（仅 relaxed 语义）

先从最基础的 C++ 原子版本开始——它修正了问题 1 和 2，但先不考虑最优内存序：

```cpp
#include <atomic>
#include <vector>
#include <cstddef>

template<typename T, size_t SIZE>
class SPSCQueue_V1 {
    static_assert((SIZE & (SIZE - 1)) == 0, "SIZE must be power of 2");

    T buffer_[SIZE];
    std::atomic<size_t> head_{0};
    std::atomic<size_t> tail_{0};

public:
    // 生产者调用
    bool push(const T& item) {
        size_t t = tail_.load(std::memory_order_relaxed);
        size_t h = head_.load(std::memory_order_relaxed);

        // Full: (tail + 1) % SIZE == head
        // 因为 SIZE 是 2 的幂，% SIZE 可用 & (SIZE-1) 替代（快约 20x）
        if ((t + 1) & (SIZE - 1)) == (h & (SIZE - 1))) {
            return false;  // 队列满
        }

        buffer_[t & (SIZE - 1)] = item;

        // 为什么先写 buffer_ 再更新 tail？
        // 消费者读到新 tail 时，必须确保 buffer_[old_tail] 已写入完成
        tail_.store(t + 1, std::memory_order_relaxed);
        return true;
    }

    // 消费者调用
    bool pop(T& item) {
        size_t h = head_.load(std::memory_order_relaxed);
        size_t t = tail_.load(std::memory_order_relaxed);

        // Empty: head == tail
        if (h == t) {
            return false;  // 队列空
        }

        item = buffer_[h & (SIZE - 1)];

        // 为什么先读 buffer_ 再更新 head？
        // 生产者读到新 head 后才能覆盖该 slot
        head_.store(h + 1, std::memory_order_relaxed);
        return true;
    }
};
```

**关键优化**：用 `SIZE & (SIZE - 1)` 约束 SIZE 为 2 的幂，再将 `% SIZE` 替换为 `& (SIZE - 1)`（位运算比取模快一个数量级）。这是无锁队列的标准做法。

**设计决策——返回 bool vs spin**：原笔记的伪代码在满/空时 spin 等待。这个版本改为返回 `bool`，让调用方决定策略（spin、yield、sleep、丢弃等）。见下一章详细分析。

## 5. SPSC 为什么"天然"无锁

SPSC 队列之所以是 lockfree 中最简单的形态，因为：

- **生产者只写 tail、只读 head**（head 可能被消费者并发写入）
- **消费者只写 head、只读 tail**（tail 可能被生产者并发写入）
- **没有两个线程写同一个变量** → 不需要 CAS 循环 → 单次 load + store 即可完成

这种设计下，生产者永远不会阻塞消费者，消费者也永远不会阻塞生产者。唯一需要原子操作的地方是**读到对方指针的最新值**，这由 `std::atomic` 保证。

对比下章将讨论的 MPMC 队列，那里多个生产者竞争同一个 tail——需要 CAS 循环，复杂度急剧上升。

## 6. 与现有知识的关联

本教程在内存序部分会大量引用另一个深度分析：[`cpp-memory-order-game-engine.md`](../../../../docs/deep-dives/cpp-memory-order-game-engine.md)，它已经覆盖了：
- `memory_order_relaxed` / `acquire` / `release` 的语义
- `happens-before` / `synchronize-with` 的精确条件
- 编译器/CPU 重排序在各架构上的表现
- Treiber Stack 的完整实现分析

本教程在该基础上聚焦**queue 特有的内存序使用模式**——queue 和 stack 在同步需求上有微妙但重要的差异。

---

*下一章: [CPU 自旋优化策略](02-spin-optimization.md)*
