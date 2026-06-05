# 第 2 章：SPSC Queue 基本实现

## 最简场景：单生产者单消费者 (SPSC)

SPSC 是最简单的无锁队列场景。只有一个线程生产数据，一个线程消费数据。这是一个**天然不对称**的访问模式：

- 生产者只写 `tail` 索引并读取 `head`
- 消费者只写 `head` 索引并读取 `tail`

这种不对称性是正确性的基础：两个线程不会对同一个索引变量并发写入。

## 环形缓冲区 (Ring Buffer)

核心数据结构是一个定长数组 + 两个索引：

```
          head (consumer)
            ↓
    ┌───┬───┬───┬───┬───┬───┬───┬───┐
    │ D │ D │ D │   │   │   │   │   │
    └───┴───┴───┴───┴───┴───┴───┴───┘
                        ↑
                      tail (producer)

    D = 已填充数据，等待消费
    空格 = 可写入

    head: 消费者下一个要读取的位置
    tail: 生产者下一个要写入的位置
```

- `head == tail` → 队列为空
- `(tail + 1) % SIZE == head` → 队列已满（浪费一个槽位以区分空/满）

## 原始伪代码分析

笔记中的伪代码：

```
push(item):
  while (tail + 1) % SIZE == head:  // full
    spin
  buffer[tail] = item
  tail = (tail + 1) % SIZE

pop():
  while head == tail:  // empty
    spin
  item = buffer[head]
  head = (head + 1) % SIZE
  return item
```

这段代码在**单线程视角下**是正确的，但在多核 CPU 上存在严重问题：

1. **无内存屏障**：编译器/CPU 可能重排指令 — 生产者可能在 `buffer[tail] = item` 写入之前就更新了 `tail`，导致消费者读到垃圾数据。
2. **Spin 死循环**：当队列满/空时，CPU 100% 占用的忙等。
3. **非原子的 `tail`/`head`**：如果不使用 `std::atomic`，编译器可能将读写优化寄存。

## 正确的 C++11 SPSC 实现

```cpp
#include <atomic>
#include <vector>
#include <cstddef>

template <typename T>
class SPSCQueue {
    static constexpr size_t CACHELINE = 64;

    // 用 cache line 对齐防止 false sharing
    alignas(CACHELINE) std::atomic<size_t> head_{0};
    alignas(CACHELINE) std::atomic<size_t> tail_{0};
    alignas(CACHELINE) std::vector<T> buffer_;
    size_t mask_;  // capacity - 1

public:
    explicit SPSCQueue(size_t capacity) {
        // capacity 必须是 2 的幂，便于用位运算取模
        size_t cap = 1;
        while (cap < capacity) cap <<= 1;
        buffer_.resize(cap);
        mask_ = cap - 1;
    }

    // 生产者调用
    bool enqueue(const T& item) {
        size_t tail = tail_.load(std::memory_order_relaxed);
        size_t head = head_.load(std::memory_order_acquire);

        // 满？
        if ((tail - head) == mask_ + 1)
            return false;

        buffer_[tail & mask_] = item;

        // release: 确保 buffer_ 写入对消费者可见
        tail_.store(tail + 1, std::memory_order_release);
        return true;
    }

    // 消费者调用
    bool dequeue(T& item) {
        size_t head = head_.load(std::memory_order_relaxed);
        size_t tail = tail_.load(std::memory_order_acquire);

        // 空？
        if (head == tail)
            return false;

        item = buffer_[head & mask_];

        // release: 确保读取完成后再推进 head
        head_.store(head + 1, std::memory_order_release);
        return true;
    }
};
```

### 关键设计决策

| 决策 | 原因 |
|------|------|
| `capacity` 为 2 的幂 | `index & mask_` 替代 `%` 运算，快 5–10 倍 |
| `alignas(64)` | 防止 false sharing — head 和 tail 位于不同 cache line |
| `acquire` 读对方索引 | 建立 happens-before，确保数据可见 |
| `release` 写己方索引 | 通知对方：数据已就绪 / 槽位已释放 |
| 每次先读己方 relaxed | 减少不必要的内存屏障开销 |

## 为什么 SPSC 简单？

因为**没有竞争写**。生产者和消费者各自独占一个索引的写入权。这让 SPSC 可以完全避免 CAS 循环 — 实际上它是 **Wait-Free**（每次操作都在固定步骤内完成）。

SPSC 是所有更复杂无锁队列的基础构件。

---

*下一章：[03-spin-wait-optimization.md](./03-spin-wait-optimization.md) — Q1: Spin 循环如何避免浪费 CPU？*
