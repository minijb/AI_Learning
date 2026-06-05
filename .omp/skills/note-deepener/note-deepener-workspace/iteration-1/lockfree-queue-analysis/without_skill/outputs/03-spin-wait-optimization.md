# 第 3 章：Q1 — Spin 循环如何避免浪费 CPU？

## 问题回顾

笔记中原始伪代码使用了裸 spin 循环：

```
while (tail + 1) % SIZE == head:
    spin      // ← CPU 100% 空转
```

在多核系统中，这个循环会：
- 耗尽整个 CPU 核心（100% 使用率）
- 不断读取共享变量，产生 cache 一致性流量
- 与同一物理核心上的超线程竞争执行资源

## 答案：渐进式退避 (Progressive Backoff)

目标：**在等待时间极短时保持低延迟，等待时间变长时逐步释放 CPU 资源**。

三层策略：

```
等待时间:     < 几微秒     →  ~几十微秒     →  > 几百微秒
策略:         _mm_pause    →  yield        →  sleep/condvar
延迟:         极低          →  中等          →  高（但释放 CPU）
功耗:         中            →  低            →  极低
```

## Level 1: `_mm_pause()` — 硬件提示

x86 架构提供了 `PAUSE` 指令。Intel 软件开发者手册描述（引自 [Stack Overflow](https://stackoverflow.com/questions/12894078/what-is-the-purpose-of-the-pause-instruction-in-x86)，[Felix Cloutier x86 参考](https://www.felixcloutier.com/x86/pause)）：

> The PAUSE instruction provides a hint to the processor that the code sequence is a spin-wait loop. The processor uses this hint to avoid the memory order violation and pipeline flush.

### PAUSE 做三件事

1. **避免内存序违规导致的流水线冲刷**：当自旋锁在等待一个被其他核心修改的内存位置时，CPU 的投机执行会检测到内存序违规（store 出现在 load 之后），被迫冲刷整条指令流水线。PAUSE 告诉 CPU "我在等别人写"，避免投机执行 → 避免冲刷。
2. **短暂延迟**：执行约 10–140 个时钟周期（取决于微架构），降低对内存总线的轮询频率。
3. **超线程优化**：在支持 SMT (Hyper-Threading) 的处理器上，将执行资源让给同物理核心上的另一个逻辑线程。

### C++ 可移植写法

```cpp
#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__)
    #include <immintrin.h>
    #define CPU_PAUSE() _mm_pause()
#elif defined(__aarch64__) || defined(_M_ARM64)
    #include <arm_acle.h>
    #define CPU_PAUSE() __yield()   // ARM 等价指令: YIELD
#else
    #define CPU_PAUSE() ((void)0)
#endif
```

## Level 2: `std::this_thread::yield()` — 调度器让步

当 `_mm_pause` 无法在短时间内等到结果时，应该把 CPU 让给其他就绪线程。

```cpp
#include <thread>
std::this_thread::yield();
```

- 告诉 OS 调度器：**放弃当前时间片的剩余部分**。
- 调度器将该线程移到就绪队列末尾，选取另一个线程运行。
- 开销：一次 context switch（~1–10µs）。比 `PAUSE` 贵得多，但比继续空转释放更多 CPU 资源。

## Level 3: `sleep_for` / `condition_variable` — 进入睡眠

当等待可能持续毫秒级时，应该让线程进入阻塞状态。

```cpp
std::this_thread::sleep_for(std::chrono::milliseconds(1));
// 或者用 condition_variable 实现事件驱动唤醒
```

- 线程进入 `TASK_INTERRUPTIBLE` 状态，**完全不消耗 CPU**。
- 代价：唤醒延迟 ≥ 调度器的 tick 粒度（通常 1–10ms）。
- 适合：队列长时间为空、工作线程等待下一帧的场景。

## 完整的渐进退避实现

```cpp
#include <atomic>
#include <thread>
#include <chrono>
#include <immintrin.h>

// 渐进退避的 spin-wait 辅助类
class SpinWait {
    int count_ = 0;

    static constexpr int PAUSE_LIMIT   = 16;   // 先 PAUSE 16 次
    static constexpr int YIELD_LIMIT   = 64;   // 再 yield  48 次

public:
    void wait() {
        if (count_ < PAUSE_LIMIT) {
            _mm_pause();
        } else if (count_ < YIELD_LIMIT) {
            std::this_thread::yield();
        } else {
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }
        ++count_;
    }

    void reset() { count_ = 0; }

    bool did_spin() const { return count_ > 0; }
};

// 使用示例：SPSC 队列的生产者端
bool enqueue_with_backoff(const T& item) {
    SpinWait sw;
    while (true) {
        if (enqueue(item)) {
            return true;
        }
        sw.wait();
    }
}
```

> 注意：`enqueue(item)` 本身是不阻塞的（如果满则立即返回 `false`），退避逻辑由调用方决定。库层面通常提供 `try_enqueue` + 调用方自由选择退避策略。

## 另一种思路：混合模式

有些库将退避策略封装在队列内部，提供两种 API：

- `enqueue(item)` — 返回 `bool`，立即返回（非阻塞）
- `enqueue_blocking(item)` — 内部自旋 + yield + sleep 直到成功

游戏引擎通常用前者：生产者在每帧开始时空队列做 dispatch，若队列满则丢弃命令或降级处理，而不是阻塞帧循环。

## 实际性能数据

| 策略 | CPU 使用率 (等待时) | 唤醒延迟 | 适用场景 |
|------|--------------------|---------|---------|
| 裸 spin | 100% | ~ns | 不推荐，仅用于锁持有时间 < 50ns |
| `_mm_pause` | 30–60% | ~ns | 持有时间 < 1µs |
| `yield` | 5–15% | ~µs | 持有时间 < 100µs |
| `sleep_for` | ~0% | ~ms | 持有时间 > 1ms |

> 数据为近似值，受 CPU 频率、核心数、OS 调度策略影响。

## 总结

- **不要裸 spin**。在等待超过几个微秒时，应该用 `_mm_pause` / `yield` / `sleep` 的渐进组合。
- **选择退避深度 = 预期等待时间的函数**。制作帧间通信的队列很少需要 `sleep`，但后台工作线程可能需要。
- PAUSE 在 x86 上至关重要，忽略它会因为流水线冲刷导致严重的性能倒退。

---

*上一章：[02-spsc-queue-fundamentals.md](./02-spsc-queue-fundamentals.md)*
*下一章：[04-spsc-vs-mpmc.md](./04-spsc-vs-mpmc.md) — Q2: MPMC 与 SPSC 的区别？*
