# 第 1 章：为什么需要 Lockfree Queue？

## 场景：游戏引擎的线程通信

现代游戏引擎通常采用多线程架构。典型的分工如下：

- **主线程 (Game Thread)**：运行游戏逻辑 — AI、物理、场景更新。
- **渲染线程 (Render Thread)**：消费 draw commands，提交 GPU 工作。
- **资源线程 (Resource Thread)**：异步加载纹理、模型、音频。

主线程与渲染线程之间需要一条**命令队列**。主线程每帧产生数百条渲染命令（`DrawMesh`、`SetMaterial`、`UpdateLight` 等），渲染线程逐条消费它们。

## 用 Mutex 会怎样？

最直观的方案：`std::queue` + `std::mutex` + `std::condition_variable`。

```cpp
// Producer (Game Thread)
{
    std::lock_guard<std::mutex> lock(mtx_);
    queue_.push(cmd);
}
cv_.notify_one();

// Consumer (Render Thread)
{
    std::unique_lock<std::mutex> lock(mtx_);
    cv_.wait(lock, [] { return !queue_.empty(); });
    auto cmd = queue_.front();
    queue_.pop();
    return cmd;
}
```

问题：

1. **帧率抖动 (Jitter)**：如果主线程试图 `lock()` 时，渲染线程正持有锁（哪怕只是在拷贝数据），主线程会被 **OS 挂起 (context switch)**。一次 context switch 开销 ~1–10µs。在 16.6ms 的帧预算（60 FPS）中这似乎不大，但如果一帧内有数十次队列操作 + 偶然的线程抢占，累积延迟会导致 **丢帧**。

2. **优先级反转**：OS 调度器可能暂停持有锁的高优先级线程，让低优先级线程运行。持有锁的线程被阻塞 → 所有等待方一起卡住。

3. **内核态切换**：`futex`（Linux）或 `SRWLOCK`（Windows）涉及用户态→内核态→用户态的往返。对于仅需拷贝几十字节的轻量命令，这个开销与工作本身不成比例。

## Lockfree 核心理念

**用原子操作 (Atomic Operations) 替代锁**，核心工具是 **CAS (Compare-And-Swap)**：

```cpp
// CAS 语意：如果 *ptr == expected，则 *ptr = desired 并返回 true；否则 *ptr → expected 并返回 false
bool compare_exchange_weak(T* ptr, T& expected, T desired);
```

CAS 是硬件级别的原子指令（x86: `LOCK CMPXCHG`，ARM: `LDREX/STREX`），**不会被线程调度打断**。它可以直接构建无锁数据结构。

### 什么是 Lock-Free？

根据 Herlihy & Shavit 的定义（见 Preshing 博客）：

> 在一个无限执行中，无限频繁地有某个方法调用完成。

换句话说：**任何时刻挂起任意线程，其余线程仍然能够整体向前推进**。不会出现一个线程持有锁不释放、导致其余所有线程永远等待的情况。

### 重要子类

- **Wait-Free**：更强的保证 — 每个线程都在**有限步骤内**完成操作。无 CAS 重试循环。
- **Lock-Free**：至少一个线程会取得进展（可能有线程一直在重试）。
- **Obstruction-Free**：最弱 — 单线程隔离执行时能完成。

大多数实用实现是 Lock-Free 级别。

## 在游戏引擎中的实际收益

| 维度 | Mutex Queue | Lockfree Queue |
|------|-------------|----------------|
| 最坏延迟 | 不确定（等待锁释放 + 调度延迟） | 确定（几次 CAS 重试） |
| 上下文切换 | 可能发生 | 不发生 |
| 吞吐量 | 中等（内核态开销） | 高（纯用户态） |
| 优先级反转 | 可能 | 不会 |
| 实现复杂度 | 低 | 高（ABA、内存序等陷阱） |

对于 **60/120/240 FPS 的帧循环**，Lockfree Queue 消除了不可预测的 OS 调度干扰，这是它被游戏引擎广泛采用的根本原因。

## 其他应用场景

- **金融交易系统**：纳秒级延迟，LMAX Disruptor 的诞生地。
- **网络 I/O 框架**：事件循环之间的任务分发。
- **音频处理**：实时音频线程与 UI 线程之间的数据通路。
- **操作系统内核**：中断处理与下半部 (bottom half) 之间的通信。

---

*下一章：[02-spsc-queue-fundamentals.md](./02-spsc-queue-fundamentals.md) — SPSC Queue 的基本实现*
