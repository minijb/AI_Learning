# 第 4 章：Q2 — MPMC 与 SPSC 的区别？

## 问题回顾

从 SPSC 到 MPMC（多生产者多消费者），难度跃升多少？区别在哪里？

## 核心区别一览

| 维度 | SPSC | MPMC |
|------|------|------|
| 生产者数量 | 固定 1 | N（任意） |
| 消费者数量 | 固定 1 | N（任意） |
| 写竞争 | 无（各自独占索引） | 有（多个生产者竞争 tail，多个消费者竞争 head） |
| 需要的原子操作 | `load/store` (acquire/release) | `compare_exchange_weak` (CAS 循环) |
| 进度保证 | **Wait-Free** | **Lock-Free** |
| 实现复杂度 | ~50 行 | ~150 行 |
| 吞吐量（同核心数） | 最高 | 较低（CAS 竞争开销） |
| 内存序复杂性 | 低（2 对 acq/rel） | 中（每个 slot 独立 seq 号） |

## SPSC: 不对称 = 简单

回顾 SPSC 设计：

```
生产者只写 tail → 消费者只读 tail
消费者只写 head → 生产者只读 head
```

**没有两个线程写同一个原子变量**。因此不需要 CAS — 每个线程可以用 `store` 更新自己的索引，另一个线程用 `load` 读取。

这是 Wait-Free：每个操作在常数步数内完成。

## MPMC: 多写者需要 CAS

当多个生产者并发入队时：

```
Producer A: tail = 5 → 写入 slot 5 → tail = 6
Producer B: tail = 5 → 写入 slot 5 → tail = 6   ← 冲突！
```

A 和 B 都读到 `tail = 5`，都试图写入 slot 5，都试图推进 `tail`。这是数据竞争。

解决方案：**用 CAS 原子地预约 slot**。

```cpp
// 每个生产者用 CAS 竞争下一个写入位置
size_t pos = tail_.load();
do {
    // pos 是我期望的下一个写入位置
} while (!tail_.compare_exchange_weak(pos, pos + 1));
// 我拿到了 pos 号 slot 的独占写入权
```

同样，多个消费者用 CAS 竞争 `head`。

## Vyukov 经典 MPMC 算法

Dmitriy V'jukov（1024cores.net 作者）在 2010 年提出了经典的 bounded MPMC 队列算法。以下是其核心思想。

### 数据结构

```cpp
template <typename T>
class MPMCQueue {
    struct Cell {
        std::atomic<size_t> sequence;  // 槽位"代际号"
        T data;
    };

    std::vector<Cell> buffer_;          // 环形数组
    size_t mask_;                       // capacity - 1

    alignas(64) std::atomic<size_t> enqueue_pos_{0};
    alignas(64) std::atomic<size_t> dequeue_pos_{0};
};
```

### 关键洞察：Sequence Number

`enqueue_pos_` 和 `dequeue_pos_` 是单调递增的**无限计数**（不取模），而各 slot 的 `sequence` 字段指示该 slot 处于哪一轮的哪个状态。

```
slot[i].sequence == enqueue_pos  → slot 空闲可写
slot[i].sequence == enqueue_pos + 1  → 已写入，可读
slot[i].sequence == dequeue_pos + capacity → 已被消费，可覆写
```

### Enqueue 流程

```cpp
bool enqueue(const T& value) {
    size_t pos = enqueue_pos_.load(std::memory_order_relaxed);
    for (;;) {
        Cell* cell = &buffer_[pos & mask_];
        size_t seq = cell->sequence.load(std::memory_order_acquire);
        intptr_t diff = (intptr_t)seq - (intptr_t)pos;

        if (diff == 0) {
            // slot 空闲：尝试用 CAS 预约
            if (enqueue_pos_.compare_exchange_weak(pos, pos + 1,
                                                   std::memory_order_relaxed)) {
                // 预约成功，写入数据
                cell->data = value;
                // 发布：标记为 "已写入"
                cell->sequence.store(pos + 1, std::memory_order_release);
                return true;
            }
            // CAS 失败：pos 被自动更新为新值，重新循环
        } else if (diff < 0) {
            // 队列满：当前 slot 还在被慢速消费者占用
            return false;
        } else {
            // 另一个线程已经推进了 enqueue_pos_，更新 pos 重试
            pos = enqueue_pos_.load(std::memory_order_relaxed);
        }
    }
}
```

### Dequeue 流程

```cpp
bool dequeue(T& value) {
    size_t pos = dequeue_pos_.load(std::memory_order_relaxed);
    for (;;) {
        Cell* cell = &buffer_[pos & mask_];
        size_t seq = cell->sequence.load(std::memory_order_acquire);
        intptr_t diff = (intptr_t)seq - (intptr_t)(pos + 1);

        if (diff == 0) {
            // slot 有数据：尝试用 CAS 预约
            if (dequeue_pos_.compare_exchange_weak(pos, pos + 1,
                                                   std::memory_order_relaxed)) {
                value = cell->data;
                // 发布：标记为 "已消费，可覆写"
                cell->sequence.store(pos + mask_ + 1,
                                     std::memory_order_release);
                return true;
            }
        } else if (diff < 0) {
            // 队列空
            return false;
        } else {
            pos = dequeue_pos_.load(std::memory_order_relaxed);
        }
    }
}
```

## 关键差异深入

### 1. CAS 竞争开销

SPSC 的 `enqueue` 只有两次 `load` + 一次 `store`。MPMC 在最坏情况下需要多次 CAS 循环 — 每次 CAS 失败意味着另一个线程抢先完成了操作，当前线程必须重试。

当生产者和消费者数量超过 CPU 核心数时，CAS 失败率急剧上升（线程被抢占后，它期望的 `pos` 值早已过时）。

### 2. Memory Order 复杂性

SPSC 需要 4 个显式的内存序控制的 `load`/`store`，MPMC 在具体实现中每个 slot 需要独立的 sequence 号 + 多个 CAS 操作。内存序错误在 MPMC 中更难调试，因为出错时机取决于确切的并发交错。

### 3. 空间开销

MPMC 需要：
- 每个 slot 额外存储一个 `size_t sequence`（~8 bytes）
- `enqueue_pos_` 和 `dequeue_pos_` 分别在独立的 cache line（各 64 bytes padding）

SPSC 只需要 `head_` 和 `tail_` 两个原子变量（各 64 bytes cache line padding）。

### 4. 进度保证

- SPSC 是 **Wait-Free**：每个操作在常数步数完成（无循环重试）。
- MPMC 是 **Lock-Free**：一个线程可能被其他线程无限次抢先，但**整体系统**总在推进。

## 实际选择建议

| 场景 | 推荐 | 原因 |
|------|------|------|
| 主线程 ↔ 渲染线程 | SPSC | 1:1 关系，最简最高效 |
| 主线程 ↔ 工作线程池 | SPSC（每 worker 一个） | 避免共享队列的 CAS 竞争 |
| 多生产者日志系统 | MPMC | 多个生产者，单独队列无法处理 |
| 网络事件分发 | MPMC 或 MPSC | 取决于消费者模型 |
| Job System 任务窃取 | SPSC（每 worker 一个队列） | 任务窃取范式不需要 MPMC |

> 经验法则：**优先用多个 SPSC 队列替代一个 MPMC 队列**。只有当逻辑上确实需要多生产者/多消费者共享同一队列时，才引入 MPMC 的复杂度。

---

*上一章：[03-spin-wait-optimization.md](./03-spin-wait-optimization.md)*
*下一章：[05-memory-ordering.md](./05-memory-ordering.md) — Q3: memory_order 怎么用？*
