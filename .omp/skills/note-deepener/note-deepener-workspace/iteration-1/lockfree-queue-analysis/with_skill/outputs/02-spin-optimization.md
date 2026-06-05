# CPU 自旋优化策略

> 基于笔记: drafts/test-lockfree-queue.md
> 所属教程: Lockfree Queue 深度分析
> 章: 2/6

---

## 1. 原始问题

原笔记的伪代码在队列满/空时使用了裸 spin：

```
while (tail + 1) % SIZE == head:  // full
    spin
```

`spin` 本质是一个无限忙等循环。在硬件层面：

```cpp
while (head_.load() == tail_.load()) {
    // nothing — CPU 全速执行 load 指令
}
```

这个循环每秒执行数十亿次 load，导致的后果：

| 问题 | 机制 |
|------|------|
| **100% CPU 占用** | 操作系统调度器看到线程从未 yield，视为 CPU-bound，不给它降频 |
| **功耗飙升** | 现代 CPU 在忙等时不进入 C-state（省电状态），持续高功耗 |
| **超线程争抢** | 同物理核的另一个逻辑线程被挤压，性能骤降 |
| **thermal throttling** | 持续满载触发降频，反而**拖慢**实际需要的计算 |

在游戏引擎场景尤其突出：主线程 spin 等待渲染线程消费，CPU 满载 → 温度上升 → 降频 → **所有线程变慢** → 恶性循环。

## 2. 五层自旋优化策略

### 第 1 层：`_mm_pause`（Intel）/ `__yield`（ARM）

```cpp
#include <emmintrin.h>  // x86

while (head_.load(std::memory_order_acquire) == tail_.load(std::memory_order_acquire)) {
    _mm_pause();  // PAUSE 指令
}
```

**PAUSE 指令做什么**：
1. 提示 CPU 这是 spin-wait 循环 → CPU 避免内存顺序违规（memory order violation）导致的流水线清空
2. 在超线程架构上，让出执行资源给同物理核的另一个逻辑线程
3. 降低功耗（CPU 内部节流）

**延迟**：约 10-140 个时钟周期（取决于 CPU 代数，Skylake 之后约 140 cycles）

**何时用**：等待时间 < 几百纳秒（预期其他线程很快释放资源）

> [来源] Intel® 64 and IA-32 Architectures Optimization Reference Manual, Section 3.4.5 "PAUSE"
> [来源] 原笔记来源: Dmitry Vyukov, 1024cores.net — 推荐在 spin 循环中始终使用 `_mm_pause()`

**跨平台封装**：

```cpp
inline void cpu_relax() {
#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__)
    _mm_pause();
#elif defined(__aarch64__)
    __asm__ volatile("yield");
#else
    // 不可移植：至少告诉编译器不要优化掉循环
    __asm__ volatile("" ::: "memory");
#endif
}
```

### 第 2 层：`std::this_thread::yield()`

```cpp
#include <thread>

while (head_.load(std::memory_order_acquire) == tail_.load(std::memory_order_acquire)) {
    std::this_thread::yield();  // 让出当前时间片
}
```

**行为**：主动告诉操作系统"我暂时不需要 CPU，给其他线程"。

**代价**：上下文切换开销（~1-10μs），而且调度器可能把你放到等待队列末尾——如果其他线程很多，你可能会等一个完整调度周期（通常 1-10ms）才能回来。

**何时用**：等待时间在微秒到毫秒级，且系统有其他就绪线程。

**陷阱**：在游戏引擎主线程中使用 `yield()` 很危险——如果你让出 CPU 后调度器很久才让你回来，可能直接丢帧。

### 第 3 层：指数退避（Exponential Backoff）

结合 `_mm_pause` 和 `yield`，根据等待时间动态调整策略：

```cpp
#include <thread>
#include <emmintrin.h>

bool push_with_backoff(const T& item) {
    size_t t, h;
    constexpr int PAUSE_BEFORE_YIELD = 16;   // 先 pause 16 次
    constexpr int YIELD_BEFORE_SLEEP = 10;    // yield 10 次后 sleep

    int pause_count = 0;
    int yield_count = 0;

    while (true) {
        t = tail_.load(std::memory_order_relaxed);
        h = head_.load(std::memory_order_acquire);

        if ((t + 1) != h) {
            buffer_[t & (SIZE - 1)] = item;
            tail_.store(t + 1, std::memory_order_release);
            return true;
        }

        // 如果等了很久 → 延长退避
        if (pause_count < PAUSE_BEFORE_YIELD) {
            _mm_pause();
            ++pause_count;
        } else if (yield_count < YIELD_BEFORE_SLEEP) {
            std::this_thread::yield();
            ++yield_count;
        } else {
            // 最终手段：让 OS 挂起线程
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
    }
}
```

**为什么不用指数增长 sleep 时间**（如 1μs, 2μs, 4μs, ...）？因为游戏引擎场景的等待时间通常极短（<100μs）。如果已经到了需要 sleep 的地步，说明消费者可能被阻塞了——这是需要调查的 bug，不是正常路径。

### 第 4 层：自适应退避（Adaptive Backoff）

记录历史等待时间，动态调整策略：

```cpp
class AdaptiveBackoff {
    int min_pause_ = 1;
    int max_pause_ = 64;
    int current_pause_ = 1;
    int success_count_ = 0;
    static constexpr int ADJUST_INTERVAL = 1000;

public:
    void wait() {
        for (int i = 0; i < current_pause_; ++i) {
            _mm_pause();
        }
    }

    void on_success() {
        ++success_count_;
        if (success_count_ >= ADJUST_INTERVAL) {
            // 最近 1000 次都很顺利 → 减少等待
            current_pause_ = std::max(min_pause_, current_pause_ / 2);
            success_count_ = 0;
        }
    }

    void on_timeout() {
        // 等了太久 → 增加等待
        current_pause_ = std::min(max_pause_, current_pause_ * 2);
        success_count_ = 0;
    }
};
```

**适用场景**：负载波动大的环境。游戏引擎在加载场景时队列压力大，正常游戏时压力小——自适应退避可以在两种模式下自动调整。

> [来源] Dmitry Vyukov, "Adaptive Spin-Blocking" — 描述了在无锁数据结构中使用自适应退避的模式

### 第 5 层：Futex / `std::atomic::wait`（C++20）

C++20 引入了 `std::atomic::wait` / `notify_one` / `notify_all`——内核辅助的高效等待：

```cpp
#include <atomic>  // C++20

// 生产者
bool push_waitable(const T& item) {
    size_t t = tail_.load(std::memory_order_relaxed);
    size_t h = head_.load(std::memory_order_acquire);

    if ((t + 1) & (SIZE - 1)) == (h & (SIZE - 1))) {
        // 队列满 → 等待消费者
        // 注意：需要额外的等待策略，wait 在当前值变化时才醒来
        head_.wait(h, std::memory_order_acquire);
        t = tail_.load(std::memory_order_relaxed);
        h = head_.load(std::memory_order_acquire);
        // 重新检查队列状态...
    }

    buffer_[t & (SIZE - 1)] = item;
    tail_.store(t + 1, std::memory_order_release);

    // 通知等待 tail 的消费者
    tail_.notify_one();
    return true;
}

// 消费者
bool pop_waitable(T& item) {
    size_t h = head_.load(std::memory_order_relaxed);
    size_t t = tail_.load(std::memory_order_acquire);

    if (h == t) {
        tail_.wait(t, std::memory_order_acquire);
        h = head_.load(std::memory_order_relaxed);
        t = tail_.load(std::memory_order_acquire);
    }

    // ... 读取 item，更新 head，notify producer
    head_.store(h + 1, std::memory_order_release);
    head_.notify_one();
    return true;
}
```

**`wait` 的工作原理**（Linux 上基于 `futex`）：
1. 读取原子变量的当前值
2. 如果值和期望值匹配 → 内核挂起线程（不消耗 CPU）
3. 另一个线程调用 `notify_one()` → 内核唤醒等待线程
4. 醒来后重新检查值是否变化（防止虚假唤醒）

**性能特征**：
- 无竞争时：约 30-50 ns（仅原子 load + store，futex 未触发）
- 有竞争且等待 < ~1μs：futex 开销高于 spin，spin 更好
- 有竞争且等待 > ~10μs：futex 远优于 spin（不浪费 CPU）

> [来源] C++20 standard, [cppreference: `std::atomic<T>::wait`](https://en.cppreference.com/w/cpp/atomic/atomic/wait)

## 3. 策略选择决策树

```
等待时间预期？
├── < 100ns（几乎立即可用）
│   → _mm_pause × 1-4（或直接 spin）
│   场景：消费速度 >> 生产速度
│
├── 100ns – 1μs
│   → _mm_pause × N（固定循环）
│   场景：生产者偶尔赶上消费者
│
├── 1μs – 100μs
│   → 指数退避（pause → yield → sleep）
│   场景：批处理提交，队列短暂满载
│
├── 100μs – 1ms
│   → C++20 atomic::wait（futex）
│   场景：低频事件，如关卡加载完成的回调
│
└── > 1ms
    → 你的架构有问题。Lockfree queue 等这么久说明消费者可能已经 dead lock 或你的任务粒度太粗。检查架构设计。
```

## 4. 游戏引擎的实际做法

| 引擎/项目 | 策略 | 来源 |
|-----------|------|------|
| Unreal Engine | `FPlatformProcess::Yield()` + 自定义 spin | `HAL/ThreadingBase.h` |
| Unity (IL2CPP) | `sched_yield()` in spin loops | IL2CPP runtime source |
| Godot | 简单 `_mm_pause` spin，队列设计为极少满 | `core/templates/ring_buffer.h` |
| folly (Meta) | 完整自适应退避：`pause → yield → futex` | `folly/synchronization/AtomicNotification.cpp` |

> [来源] 以上基于开源代码分析和社区讨论。具体实现在各引擎版本间可能有变化。`[推测]`

## 5. 反直觉发现

- **spin 不一定比 yield 慢**：在等待时间 < 10μs 时，spin + `_mm_pause` 比 `yield()` 更快到达目标状态，因为避免了上下文切换的固定开销
- **在超线程系统上 spin 可能害人**：两个 spin 线程在同物理核上会互相抢占，表现可能比单线程还差
- **`_mm_pause` 的正确次数**：Dmitry Vyukov (1024cores.net) 建议 spin 64 次 `_mm_pause`（约 5-15μs）后再考虑 yield。但具体值应 benchmark 确定

---

*上一章: [核心概念：Lockfree SPSC 队列](01-core-concept.md)* | *下一章: [MPMC 多生产者多消费者队列](03-mpmc-queue.md)*
