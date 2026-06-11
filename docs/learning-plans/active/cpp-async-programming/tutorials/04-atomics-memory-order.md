---
title: 原子操作与内存序
updated: 2026-06-08
tags: [cpp, atomic, memory-order, lock-free]
---

# 04. 原子操作与内存序

> **所属计划**: C++ 异步编程学习计划
> **预计耗时**: 75 分钟
> **前置知识**: [[01-threads-and-synchronization|线程与同步原语]]
> **C++ 标准**: C++11 (`std::atomic`, `memory_order`), C++20 (`std::atomic_ref`, `std::atomic::wait/notify_one/notify_all`)
> **难度**: 进阶（可选）

---

## 1. 概念讲解

### 1.1 为什么需要原子操作

多核 CPU 上，每个核心有独立的 L1/L2 缓存和**写缓冲区 (Store Buffer)**。CPU 为了性能会对指令重排序 —— 在不违反单线程语义的前提下，实际执行顺序可能和代码顺序完全不同。

```cpp
// 你写的代码：
int a = 1;          // (1)
int b = 2;          // (2)
ready = true;       // (3)

// CPU 实际可能执行的顺序：
int b = 2;          // (2)
ready = true;       // (3) ← 重排到前面
int a = 1;          // (1) ← 重排到后面
```

单线程中没问题 —— 没有人看得见中间态。但多线程中，另一个线程可能在 `ready == true` 可见时读到 `a == 0`（旧值）。

**C++ 内存模型定义了一套规则体系来解决这个问题**，而 `std::atomic` 是这个体系的基础设施。

### 1.2 数据竞争：UB 的唯一定义

> [!warning] 数据竞争 = 未定义行为
> 两个线程并发访问同一内存位置，至少一个是写操作，且两个操作之间没有任何 happens-before 关系。**有数据竞争的程序是 UB**。

```cpp
int counter = 0;

// 线程 A: counter++;   // 读-修改-写，非原子
// 线程 B: counter++;   // 同时执行 → 数据竞争 → UB
```

`counter++` 实际是三个步骤：读 → 加 1 → 写。两个线程同时执行时，可能都读到旧值，最终 `counter` 只增加了 1 而不是 2。

### 1.3 `std::atomic<T>`：消除数据竞争的基础设施

`std::atomic<T>` 保证对 `T` 的读写是**不可分割的**（原子的）—— 要么完全执行，要么完全不执行。所有 C++ 内存序体系都建立在 `std::atomic` 之上。

```cpp
#include <atomic>

std::atomic<int> counter{0};

void increment() {
    counter.fetch_add(1);  // ✅ 原子化的「读-修改-写」：没有数据竞争
}
```

**lock-free 检测**：

```cpp
std::atomic<int> a;
if (a.is_lock_free()) {
    // 硬件原子指令实现（x86: LOCK 前缀，ARM: LDREX/STREX）
} else {
    // 编译器用内部互斥锁实现原子性（罕见，仅在大型结构体上发生）
}
```

> [!note] lock-free vs wait-free
> - **lock-free**：至少有一个线程能在有限步内完成操作（其他线程可能被阻塞）。
> - **wait-free**：所有线程都能在有限步内完成操作（无饥饿）。C++ 标准库不保证 wait-free，只保证 lock-free。

**`always_lock_free` 编译期常量**（C++17）：

```cpp
if constexpr (std::atomic<int>::is_always_lock_free) {
    // 该类型在所有平台上都是 lock-free
}
```

**`std::atomic` 对 `T` 的要求**：
- `T` 必须是 trivially copyable 的（可用 `memcpy` 拷贝）。
- 常用特化：`atomic<bool>`, `atomic<int>`, `atomic<size_t>`, `atomic<T*>`。
- C++20 引入 `std::atomic_ref<T>`：为非原子对象的原子操作提供包装，不拥有数据。

### 1.4 原子操作接口速查

| 操作 | 语义 | 允许的内存序 |
|------|------|-------------|
| `load()` | 原子读 | `relaxed`, `consume`, `acquire`, `seq_cst` |
| `store(val)` | 原子写 | `relaxed`, `release`, `seq_cst` |
| `exchange(val)` | 原子交换：写入 `val`，返回旧值 | `relaxed`, `acq_rel`, `seq_cst` |
| `compare_exchange_weak(exp, des)` | CAS：若 `*this == exp` 则 `*this = des`，否则 `exp = *this` | 成功/失败各自指定 |
| `compare_exchange_strong(exp, des)` | 同上但无伪失败 | 同上 |
| `fetch_add(val)` | 原子加：返回旧值 | `relaxed`, `acq_rel`, `seq_cst` |
| `fetch_sub(val)` | 原子减：返回旧值 | 同上 |
| `fetch_and(val)` / `fetch_or` / `fetch_xor` | 原子位运算 | 同上 |
| `operator++` / `operator--` | 默认 `seq_cst` | — |
| `operator+=` / `operator-=` | 默认 `seq_cst` | — |

> [!warning] `store()` 不能用 `acquire`，`load()` 不能用 `release`
> 编译器会报错。这是设计约束：`store` 是"发布"，`load` 是"获取"，不能反过来。

### 1.5 happens-before 与 synchronize-with

C++ 内存模型用 **happens-before** 定义线程间可见性：

- **sequenced-before**：同一线程内，A 在源码中先于 B → A happens-before B。
- **synchronize-with**：线程间 —— 若 A 是对原子变量 M 的 release 写，B 是对 M 的 acquire 读且读到了 A 写入的值（或 A 之后的某个值）→ A synchronize-with B → A happens-before B。
- **传递性**：A → B 且 B → C 则 A → C。

```cpp
// 线程 1
data = 42;                              // (1) 写 data（非原子）
flag.store(true, std::memory_order_release);  // (2) release 写 flag

// 线程 2
while (!flag.load(std::memory_order_acquire)) {}  // (3) acquire 读 flag
assert(data == 42);                     // (4) data 的写入对线程 2 保证可见 ✅

// 推导链：
// (1) sequenced-before (2)  →  (1) happens-before (2) [同线程]
// (2) synchronize-with (3) →  (2) happens-before (3) [同一原子变量]
// 传递性： (1) happens-before (4)  →  assert 不会失败
```

> [!warning] synchronize-with 只在同一个原子变量上成立
> 线程 1 对 `flag_a` 的 release 写，**不会**和线程 2 对 `flag_b` 的 acquire 读建立 synchronize-with 关系！

### 1.6 六种内存序

| `memory_order` | 保证 | CPU 开销 | 典型场景 |
|:---------------|:-----|:--------|:---------|
| `relaxed` | 仅保证原子性，无顺序约束 | 最低 | 统计计数器、进度追踪 |
| `consume` | 依赖序（C++17 起不推荐使用） | 低（但编译器支持差） | 几乎不用 |
| `acquire` | 后续读写不能重排到此 load 之前 | ARM: DMB；x86: 仅编译器屏障 | 锁的 lock、消费者读取 |
| `release` | 之前的读写不能重排到此 store 之后 | ARM: DMB；x86: 仅编译器屏障 | 锁的 unlock、生产者写入 |
| `acq_rel` | acquire + release | 两者开销之和 | RMW 操作如 `fetch_add` |
| `seq_cst` | 全局统一顺序（最强保证） | 最高（可能触发总线锁） | 需要严格全序的场景 |

**操作的合法内存序组合**：

| 操作 | 允许的 `memory_order` |
|------|----------------------|
| `load()` | `relaxed`, `consume`, `acquire`, `seq_cst` |
| `store()` | `relaxed`, `release`, `seq_cst` |
| RMW（`exchange`, `fetch_add` 等） | `relaxed`, `acquire`, `release`, `acq_rel`, `seq_cst` |
| `compare_exchange_weak/strong` | 成功/失败序各自指定；失败不能强于成功 |

### 1.6.1 `relaxed`：只有原子性，没有顺序

```cpp
std::atomic<size_t> frame_counter{0};

// 渲染线程
frame_counter.fetch_add(1, std::memory_order_relaxed);

// 主线程
size_t frames = frame_counter.load(std::memory_order_relaxed);
// 不关心和其他变量的相对顺序 —— 只做性能统计
```

`relaxed` 的合法用途：单纯的计数器、进度追踪 —— **不需要和其他变量建立 happens-before 关系**。

### 1.6.2 `acquire` / `release`：锁和队列的基石

```cpp
// 标志位同步模式（最常见）
std::atomic<bool> data_ready{false};
Payload shared_payload;  // 非原子共享数据

// 生产者
void produce() {
    shared_payload = compute_payload();        // (A) 准备数据
    data_ready.store(true, std::memory_order_release);  // (B) release 写
    // 保证：任何看到 (B) 结果的线程，也保证能看到 (A) 的结果
}

// 消费者
void consume() {
    while (!data_ready.load(std::memory_order_acquire)) {}  // (C) acquire 读
    process(shared_payload);                    // (D) 安全访问
    // (B) synchronize-with (C) → (A) happens-before (D) ✅
}
```

### 1.6.3 `seq_cst`：最易理解也最贵

`seq_cst` 保证**所有 seq_cst 操作之间有一个全局统一的顺序** —— 每个线程看到的所有 seq_cst 操作的顺序是一致的。

```cpp
std::atomic<bool> x{false}, y{false};
std::atomic<int>  z{0};

// 线程 1                      线程 2
x.store(true, seq_cst);      y.store(true, seq_cst);
if (y.load(seq_cst))         if (x.load(seq_cst))
    z++;                         z++;

// 使用 seq_cst：线程 1 和 2 不可能同时看到对方为 false → z 至少为 1
// 使用 acquire/release：可能同时为 false → z 可能为 0！（x86 上不会，ARM/PowerPC 上可能）
```

> [!note] 内存序选择建议
> 当你对内存序不确定时，先用 `seq_cst`。profile 后用 `acquire` / `release` 替换热路径。**正确性优先于性能**。

### 1.7 `std::atomic_flag` vs `std::atomic<bool>`

| | `std::atomic_flag` | `std::atomic<bool>` |
|--|--------------------|---------------------|
| 保证 lock-free | ✅（标准明确要求） | 取决于平台 |
| 接口 | `test_and_set()`, `clear()` | `load()`, `store()`, `exchange()` |
| 初始化 | `ATOMIC_FLAG_INIT` | `atomic<bool>{false}` |
| 用途 | 自旋锁、一次初始化 | 标志位同步 |

```cpp
#include <atomic>

// 自旋锁的最简实现
class SpinLock {
    std::atomic_flag locked = ATOMIC_FLAG_INIT;
public:
    void lock() {
        while (locked.test_and_set(std::memory_order_acquire)) {
            // 自旋等待
        }
    }
    void unlock() {
        locked.clear(std::memory_order_release);
    }
};
```

### 1.8 `compare_exchange`：lock-free 的核心原语

`compare_exchange` 是原子化的"如果值等于预期就替换"操作 —— 几乎所有 lock-free 数据结构都建立在此之上。

**两个版本**：

| 特性 | `compare_exchange_weak` | `compare_exchange_strong` |
|------|------------------------|--------------------------|
| 伪失败 (spurious failure) | 允许（即使 `*this == expected` 也可能返回 false） | 不允许 |
| 底层指令 | 通常更简单、更快 | 在 LL/SC 架构上需要额外循环 |
| 使用场景 | **循环中**（重试是预期行为） | 不需要循环时 |

```cpp
// 签名
bool compare_exchange_weak(T& expected, T desired,
                           std::memory_order success = seq_cst,
                           std::memory_order failure = seq_cst);

// 语义：
// if (*this == expected) { *this = desired; return true; }
// else                  { expected = *this;  return false; }
```

**weak 的伪失败**：在某些架构上（ARM 使用 LDREX/STREX），CAS 可能因为中断等原因伪失败 —— 此时即使值匹配也返回 false。**在循环中使用 `weak` 是惯用法**：

```cpp
std::atomic<int> value{0};

void increment() {
    int expected = value.load(std::memory_order_relaxed);
    do {
        int desired = expected + 1;
        // 在循环中重试：伪失败只是多转一圈
    } while (!value.compare_exchange_weak(expected, desired,
                                          std::memory_order_release,
                                          std::memory_order_relaxed));
}
```

> [!note] 内存序规则
> `compare_exchange` 的失败内存序不能强于成功内存序（例如：成功用 `release`、失败用 `acquire` 会被编译期拒绝）。失败序通常设置 `relaxed` 即可，因为没有修改发生。

### 1.9 C++20 原子等待与通知

C++20 为 `std::atomic` 添加了等待/通知机制，可以替代部分 `condition_variable` 的场景：

```cpp
#include <atomic>
#include <thread>

std::atomic<int> value{0};

// 等待线程：阻塞直到 value != 0
void waiter() {
    int old = value.load();
    value.wait(old);  // 阻塞直到 value 不再等于 old
    // value 已改变
}

// 通知线程
void notifier() {
    value.store(42);
    value.notify_one();  // 唤醒一个等待线程
    // 或 value.notify_all();
}
```

> [!note]
> `atomic::wait` 在内部使用 futex（Linux）或 WaitOnAddress（Windows），比 condition_variable 更轻量，但通知必须在对**同一个原子变量**的修改之后发出。

---

## 2. 代码示例

### 示例 1：`std::atomic<int>` 基本操作

```cpp
// compile: g++ -std=c++20 -pthread -O2 basic_atomic.cpp -o basic_atomic
// run: ./basic_atomic

#include <atomic>
#include <iostream>
#include <thread>
#include <vector>

int main() {
    std::atomic<int> counter{0};

    auto increment = [&counter]() {
        for (int i = 0; i < 100'000; ++i) {
            counter.fetch_add(1, std::memory_order_relaxed);
        }
    };

    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back(increment);
    }
    for (auto& t : threads) {
        t.join();
    }

    std::cout << "Final counter: " << counter.load() << "\n";
    // 输出：400000 ✅（无数据竞争）

    // 对比：非原子的 int 会产生数据竞争 → UB
    int unsafe_counter = 0;
    auto unsafe_inc = [&unsafe_counter]() {
        for (int i = 0; i < 100'000; ++i) {
            ++unsafe_counter;  // ❌ 数据竞争！
        }
    };
    // 不要运行上面的 unsafe_inc —— 可能工作，可能崩溃，可能静默错误

    return 0;
}
```

### 示例 2：`compare_exchange_weak` 实现 Lock-Free 计数器

```cpp
// compile: g++ -std=c++20 -pthread -O2 cas_counter.cpp -o cas_counter
// run: ./cas_counter

#include <atomic>
#include <iostream>
#include <thread>
#include <vector>

class LockFreeCounter {
    std::atomic<uint64_t> value_{0};

public:
    uint64_t increment() {
        uint64_t expected = value_.load(std::memory_order_relaxed);
        do {
            uint64_t desired = expected + 1;
            // weak: 允许伪失败，在循环中重试即可
            if (value_.compare_exchange_weak(expected, desired,
                                             std::memory_order_release,
                                             std::memory_order_relaxed)) {
                return desired;  // 返回新值
            }
            // CAS 失败 → expected 已被更新为当前值，继续循环
        } while (true);
    }

    // 无竞争时的快速路径（可选优化）
    uint64_t increment_fast() {
        uint64_t expected = value_.load(std::memory_order_relaxed);
        uint64_t desired;
        do {
            desired = expected + 1;
        } while (!value_.compare_exchange_weak(expected, desired,
                                               std::memory_order_release,
                                               std::memory_order_relaxed));
        return desired;
    }

    uint64_t load() const {
        return value_.load(std::memory_order_acquire);
    }
};

int main() {
    LockFreeCounter counter;

    std::vector<std::thread> threads;
    for (int t = 0; t < 8; ++t) {
        threads.emplace_back([&counter]() {
            for (int i = 0; i < 50'000; ++i) {
                counter.increment();
            }
        });
    }
    for (auto& t : threads) {
        t.join();
    }

    std::cout << "Final: " << counter.load()
              << " (expected 400000)\n";
    return 0;
}
```

### 示例 3：`acquire` / `release` 标志位同步

```cpp
// compile: g++ -std=c++20 -pthread -O2 flag_sync.cpp -o flag_sync
// run: ./flag_sync

#include <atomic>
#include <iostream>
#include <thread>
#include <string>
#include <chrono>

struct SharedData {
    std::string payload;
    bool        checksum_ok;
};

std::atomic<bool> data_ready{false};
SharedData        shared;

void producer() {
    // 模拟耗时计算
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    shared.payload = "重要数据";
    shared.checksum_ok = true;

    // release 写：保证 shared 的所有写入在其他线程看到 flag 之前完成
    data_ready.store(true, std::memory_order_release);
    std::cout << "[Producer] 数据已发布\n";
}

void consumer() {
    // acquire 读：等待 flag 变为 true，并获取 producer 的所有写入
    while (!data_ready.load(std::memory_order_acquire)) {
        std::this_thread::yield();  // 避免忙等 CPU
    }

    // 此时 shared.payload 和 shared.checksum_ok 保证是最新值
    std::cout << "[Consumer] 收到: " << shared.payload
              << " (校验: " << std::boolalpha << shared.checksum_ok << ")\n";
}

int main() {
    std::thread t1(producer);
    std::thread t2(consumer);

    t1.join();
    t2.join();
    return 0;
}
```

> [!note] 关键点
> `data_ready` 是一个原子变量但其保护的 `shared` 不是。**原子变量在这里充当"门"的角色**：release 写确保门打开前屋内已打扫干净，acquire 读确保进门后看到的是打扫后的状态。

### 示例 4：简单 Lock-Free SPSC 有界队列

```cpp
// compile: g++ -std=c++20 -pthread -O2 spsc_queue.cpp -o spsc_queue
// run: ./spsc_queue

#include <atomic>
#include <cstddef>
#include <iostream>
#include <thread>
#include <vector>
#include <cassert>

template<typename T, size_t Capacity>
class SPSCQueue {
    static_assert((Capacity & (Capacity - 1)) == 0,
                  "Capacity must be power of 2");

    // 对齐到缓存行，避免伪共享
    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    T buffer_[Capacity];

public:
    bool enqueue(const T& item) {
        size_t head = head_.load(std::memory_order_relaxed);
        size_t tail = tail_.load(std::memory_order_acquire);

        if (head - tail >= Capacity) return false;  // 满

        buffer_[head & (Capacity - 1)] = item;

        // release：保证 item 的写入在 head 更新之前完成
        head_.store(head + 1, std::memory_order_release);
        return true;
    }

    bool dequeue(T& item) {
        size_t tail = tail_.load(std::memory_order_relaxed);
        size_t head = head_.load(std::memory_order_acquire);

        if (tail == head) return false;  // 空

        item = buffer_[tail & (Capacity - 1)];

        // release：保证 item 的读取在 tail 更新之前完成
        tail_.store(tail + 1, std::memory_order_release);
        return true;
    }

    bool empty() const {
        return tail_.load(std::memory_order_acquire)
            == head_.load(std::memory_order_acquire);
    }
};

int main() {
    SPSCQueue<int, 256> queue;

    // 生产者
    std::thread producer([&queue]() {
        for (int i = 0; i < 1000; ++i) {
            while (!queue.enqueue(i)) {
                std::this_thread::yield();
            }
        }
    });

    // 消费者
    std::thread consumer([&queue]() {
        int count = 0;
        int item;
        while (count < 1000) {
            if (queue.dequeue(item)) {
                ++count;
            } else {
                std::this_thread::yield();
            }
        }
        std::cout << "Consumer processed " << count << " items\n";
    });

    producer.join();
    consumer.join();

    assert(queue.empty());
    std::cout << "SPSC queue test passed!\n";
    return 0;
}
```

**内存序分析**：

| 操作 | 内存序 | 原因 |
|------|--------|------|
| `head_.load()` 在 enqueue | `relaxed` | 生产者只读自己的 head，不需要同步 |
| `tail_.load()` 在 enqueue | `acquire` | 需要看到消费者最新的 tail 更新 |
| `head_.store()` 在 enqueue | `release` | 保证 item 写入对消费者可见 |
| `tail_.load()` 在 dequeue | `relaxed` | 消费者只读自己的 tail |
| `head_.load()` 在 dequeue | `acquire` | 需要看到生产者最新的 head 更新和 item 数据 |
| `tail_.store()` 在 dequeue | `release` | 保证 item 读取完成后再通知生产者 |

---

## 3. 练习

### 练习 1：原子计数器（入门）

实现一个 `AtomicCounter` 类，支持多线程安全的自增、自减和获取当前值。要求：

1. 使用 `std::atomic<int64_t>` 存储值。
2. 提供 `increment()`、`decrement()` 和 `get()` 方法。
3. 使用 `fetch_add` 和 `fetch_sub` + `relaxed` 内存序。
4. 10 个线程各自增 10 万次，验证最终结果正确。

### 练习 2：自旋锁（进阶）

使用 `std::atomic_flag` 实现一个自旋锁 `SpinLock`：

1. 实现 `lock()` 和 `unlock()` 方法。
2. `lock()` 中使用 `test_and_set(std::memory_order_acquire)`。
3. `unlock()` 中使用 `clear(std::memory_order_release)`。
4. 用自旋锁保护一个非原子计数器，10 线程各自增 10 万次，验证结果。
5. （可选）对比 `std::mutex` 的性能差异 —— 低竞争下自旋锁更快，高竞争下 mutex 更优。

### 练习 3：Lock-Free 栈（挑战）

实现一个简单的 lock-free 单链表栈（Treiber Stack）：

```cpp
template<typename T>
class LockFreeStack {
    struct Node {
        T data;
        Node* next;
        Node(const T& val) : data(val), next(nullptr) {}
    };
    std::atomic<Node*> head_{nullptr};
    // ...
};
```

1. **push**：创建新节点，将其 `next` 指向当前 head，用 `compare_exchange_weak` 更新 head。
2. **pop**：读取 head，用 `compare_exchange_weak` 将 head 更新为 `head->next`。成功后返回节点数据。
3. 内存序：
   - push: CAS 成功用 `release`，失败用 `relaxed`
   - pop: `load` 用 `acquire`，CAS 成功用 `acquire`，失败用 `relaxed`
4. 多线程 push/pop 混合测试，验证不会有节点丢失。
5. （可选）实现内存回收方案（引用计数或 hazard pointer）。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> #include <atomic>
> #include <thread>
> #include <vector>
> #include <cassert>
> 
> class AtomicCounter {
>     std::atomic<int64_t> value_{0};
> 
> public:
>     void increment() {
>         // relaxed 足够：仅保证原子性，不需要和其他变量建立顺序
>         value_.fetch_add(1, std::memory_order_relaxed);
>     }
> 
>     void decrement() {
>         value_.fetch_sub(1, std::memory_order_relaxed);
>     }
> 
>     int64_t get() const {
>         return value_.load(std::memory_order_relaxed);
>     }
> };
> 
> int main() {
>     constexpr int kThreads = 10;
>     constexpr int kPerThread = 100'000;
>     AtomicCounter counter;
> 
>     std::vector<std::thread> threads;
>     for (int t = 0; t < kThreads; ++t) {
>         threads.emplace_back([&counter] {
>             for (int i = 0; i < kPerThread; ++i)
>                 counter.increment();
>         });
>     }
>     for (auto& t : threads) t.join();
> 
>     assert(counter.get() == int64_t(kThreads) * kPerThread);
> }
> ```
>
> **关键设计决策**：
> - 使用 `relaxed` 内存序：纯计数器只需原子性，不需要顺序保证
> - `fetch_add` 和 `fetch_sub` 返回旧值——如果需要新值，用返回值 + n
> - `int64_t` 确保大范围计数不溢出

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <atomic>
> #include <thread>
> #include <vector>
> #include <iostream>
> #include <chrono>
> 
> class SpinLock {
>     std::atomic_flag locked_ = ATOMIC_FLAG_INIT;
> 
> public:
>     void lock() {
>         // acquire: lock 之后的读写不能重排到此 test_and_set 之前
>         while (locked_.test_and_set(std::memory_order_acquire)) {
>             // 自旋等待——可加入 _mm_pause() 或 std::this_thread::yield()
>         }
>     }
> 
>     void unlock() {
>         // release: lock 之前的写入对后续 acquire 可见
>         locked_.clear(std::memory_order_release);
>     }
> };
> 
> int main() {
>     constexpr int kThreads = 10;
>     constexpr int kPerThread = 100'000;
> 
>     SpinLock spinlock;
>     int counter = 0;  // 非原子，由自旋锁保护
> 
>     auto start = std::chrono::high_resolution_clock::now();
> 
>     std::vector<std::thread> threads;
>     for (int t = 0; t < kThreads; ++t) {
>         threads.emplace_back([&] {
>             for (int i = 0; i < kPerThread; ++i) {
>                 spinlock.lock();
>                 ++counter;
>                 spinlock.unlock();
>             }
>         });
>     }
>     for (auto& t : threads) t.join();
> 
>     auto elapsed = std::chrono::high_resolution_clock::now() - start;
>     auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(elapsed).count();
> 
>     std::cout << "SpinLock result: " << counter
>               << " (expected " << kThreads * kPerThread << ")"
>               << ", time: " << ms << "ms\n";
> }
> ```
> 
> **对比 std::mutex 的性能对比代码**：
> 
> ```cpp
> // 将 SpinLock 替换为 std::mutex，其余代码不变：
> std::mutex mtx;
> // ...
> mtx.lock();
> ++counter;
> mtx.unlock();
> ```
> 
> **关键洞见**：
> - spinlock 在**低竞争**下通常更快（避免系统调用）
> - mutex 在**高竞争**下更优（等待者被挂起，不浪费 CPU）
> - `test_and_set` 的 acquire 语义确保进入临界区后能看到之前 release 写的结果
> - 生产代码中可在循环中加入 `_mm_pause()`（x86）减少功耗

> [!tip]- 练习 3 参考答案
> ```cpp
> #include <atomic>
> #include <memory>
> #include <thread>
> #include <vector>
> #include <cassert>
> 
> template<typename T>
> class LockFreeStack {
>     struct Node {
>         T data;
>         Node* next;
>         Node(const T& val) : data(val), next(nullptr) {}
>     };
>     std::atomic<Node*> head_{nullptr};
> 
> public:
>     void push(const T& value) {
>         Node* new_node = new Node(value);
>         new_node->next = head_.load(std::memory_order_relaxed);
> 
>         while (!head_.compare_exchange_weak(
>                     new_node->next, new_node,
>                     std::memory_order_release,
>                     std::memory_order_relaxed)) {
>             // CAS 失败 → new_node->next 已被更新为当前 head，循环再试
>         }
>     }
> 
>     std::shared_ptr<T> pop() {
>         Node* old_head = head_.load(std::memory_order_acquire);
> 
>         do {
>             if (old_head == nullptr) return nullptr;
>         } while (!head_.compare_exchange_weak(
>                     old_head, old_head->next,
>                     std::memory_order_acquire,
>                     std::memory_order_relaxed));
> 
>         auto result = std::make_shared<T>(std::move(old_head->data));
>         delete old_head;  // ⚠️ 简化版：存在 ABA 问题
>         return result;
>     }
> 
>     bool empty() const {
>         return head_.load(std::memory_order_relaxed) == nullptr;
>     }
> };
> 
> int main() {
>     LockFreeStack<int> stack;
>     constexpr int kThreads = 4;
>     constexpr int kPerThread = 1000;
> 
>     std::vector<std::thread> producers;
>     for (int t = 0; t < kThreads; ++t) {
>         producers.emplace_back([&stack, t] {
>             for (int i = 0; i < kPerThread; ++i)
>                 stack.push(t * kPerThread + i);
>         });
>     }
>     for (auto& t : producers) t.join();
> 
>     int pop_count = 0;
>     std::vector<std::thread> consumers;
>     for (int t = 0; t < kThreads; ++t) {
>         consumers.emplace_back([&stack, &pop_count] {
>             for (int i = 0; i < kPerThread; ++i) {
>                 auto val = stack.pop();
>                 if (val) ++pop_count;
>                 else --i;  // 被其他线程抢先，重试
>             }
>         });
>     }
>     for (auto& t : consumers) t.join();
> 
>     assert(pop_count == kThreads * kPerThread);
>     assert(stack.empty());
> }
> ```
> 
> **内存序设计分析**：
> 
> | 操作 | 成功序 | 失败序 | 原因 |
> |------|--------|--------|------|
> | push CAS | `release` | `relaxed` | push 修改了数据，需对 pop 可见 |
> | pop CAS | `acquire` | `relaxed` | pop 读取数据，需看到 push 的结果 |
> | head load (pop 前) | `acquire` | — | 与上一个成功的 push/release 配对 |
> 
> **ABA 问题说明**：本实现通过 CAS 循环避免了基础竞态，但线程 B 在执行 A→B→A（pop A, pop B, push 新节点到 A 的地址）后，线程 A 的 CAS 可能误以为 head 没变。修复方案：
> - **Tagged pointer**：高位存储版本号（需 double-width CAS）
> - **Hazard Pointer**：延迟释放直到无线程引用该节点

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 常见陷阱

### 4.1 ABA 问题

**场景**：线程 A 读到 head=A，线程 B 执行 A→B→A（先 pop A，再 pop B，再 push A），线程 A 的 CAS 发现 head 还是 A——CAS 成功。但实际上链表结构已经变了，B 可能已被释放（use-after-free）。

```cpp
// 线程 A: 读到 head = 节点 A (值 1)
// 线程 B: pop A (值 1), pop B (值 2), push 新节点 A' (值 3)
//         head 又指向了 A 的地址（但内容已不同）
// 线程 A: CAS(&head, A, A->next) → 成功！
//         但 A->next 可能已被释放 → use-after-free 💥
```

**解决方案**：
- **Tagged pointer**：指针高位存版本号，每次操作递增。这样 A 和 A' 的 tag 不同，CAS 不会误判。
- **Hazard Pointer**：延迟释放，直到确认没有线程还在引用该节点。
- **Epoch-Based Reclamation (EBR)**：分 epoch，只有所有线程进入新 epoch 后才释放旧 epoch 的内存。

### 4.2 `relaxed` 用在不该用的地方

```cpp
// ❌ 错误：用 relaxed 做同步
std::atomic<bool> done{false};
int result;

// 线程 1
result = compute();
done.store(true, std::memory_order_relaxed);  // ❌ result 可能对线程 2 不可见

// 线程 2
while (!done.load(std::memory_order_relaxed)) {}  // ❌ 看不到 result
std::cout << result;  // 可能读到垃圾值
```

**修正**：将 `store` 改为 `release`，`load` 改为 `acquire`。

### 4.3 `compare_exchange_weak` 伪失败必须循环

```cpp
// ❌ 错误：没有循环
std::atomic<int> v{0};
int expected = 0;
v.compare_exchange_weak(expected, 1);  // 伪失败 → expected = 0 但 v 没变
// 此时 v 可能还是 0，但你没有重试！

// ✅ 正确：始终在循环中使用
int expected = v.load();
do {
    // 计算 desired...
} while (!v.compare_exchange_weak(expected, desired, ...));
```

### 4.4 原子和非原子混用同一变量

```cpp
// ❌ 极端错误
std::atomic<int> x{0};

// 线程 1
x.store(42, std::memory_order_relaxed);

// 线程 2
int* ptr = reinterpret_cast<int*>(&x);  // 💀 绝不要这样做
*ptr = 100;  // 数据竞争 → UB
```

同一变量要么全用原子操作访问，要么全用互斥锁保护 —— 绝不可混用。即使 `std::atomic<T>` 在内存布局上可能和 `T` 相同，这仍是 UB。

### 4.5 `volatile` 不能替代 `atomic`

| | `volatile` | `std::atomic` |
|--|-----------|---------------|
| 防止编译器优化掉读写 | ✅ | ✅ |
| 防止编译器重排序 | ✅（仅 vs 其他 volatile 访问） | ✅ |
| 防止 CPU 重排序 | ❌ | ✅ |
| 保证原子性 | ❌ | ✅ |
| 建立 happens-before | ❌ | ✅ |
| 多线程同步 | ❌ **绝不正确** | ✅ |
| 正当用途 | MMIO、信号处理函数 | 多线程同步 |

### 4.6 忘记缓存行对齐（伪共享）

```cpp
// ❌ head 和 tail 在同一缓存行 → 伪共享
std::atomic<size_t> head{0};
std::atomic<size_t> tail{0};  // 和 head 在同一 64 字节行内

// ✅ 各自独占缓存行
alignas(64) std::atomic<size_t> head{0};
alignas(64) std::atomic<size_t> tail{0};
```

生产者写 `head` 和消费者写 `tail` 时会互相使对方的缓存行失效，即使它们访问的是不同变量 —— 这就是伪共享 (false sharing)。

### 4.7 内存序选择的总结

| 场景 | 推荐内存序 | 理由 |
|------|-----------|------|
| 纯计数器（最终值正确即可） | `relaxed` | 无需顺序保证 |
| 生产者发布数据 | `release` | 保证数据先于 flag 可见 |
| 消费者读取数据 | `acquire` | 保证看到 flag 后再读数据 |
| RMW 操作（`fetch_add` 等） | `acq_rel` | 既能看到前面的 release，又能通知后面的 acquire |
| 不确定 / 调试阶段 | `seq_cst` | 最安全，最易理解 |

---

## 5. 扩展阅读

### 必读

- [cppreference: `std::atomic`](https://en.cppreference.com/w/cpp/atomic/atomic) — 原子操作接口的权威参考。
- [cppreference: `std::memory_order`](https://en.cppreference.com/w/cpp/atomic/memory_order) — 六种内存序的详细说明和形式化语义。
- Herb Sutter, *"Atomic Weapons"* ([Part 1](https://herbsutter.com/2013/02/11/atomic-weapons-the-c-memory-model-and-modern-hardware/), [Part 2](https://herbsutter.com/2013/02/18/atomic-weapons-the-c-memory-model-and-modern-hardware-part-2/)) — C++ 内存模型的经典讲解。

### 深入

- Preshing on Programming, *[The Purpose of memory_order_consume in C++11](https://preshing.com/20140709/the-purpose-of-memory_order_consume-in-cpp11/)* — 理解 consume 为何失败。
- Jeff Preshing, *[How to Build a Lock-Free Queue](https://preshing.com/20120202/roll-your-own-lightweight-mutex/)* — 实际 lock-free 数据结构构建指南。
- Dmitry Vyukov, *[1024cores: Lock-Free Algorithms](https://www.1024cores.net/home/lock-free-algorithms)* — 俄罗斯专家的 lock-free 深度系列。

### C++20 新特性

- [cppreference: `std::atomic_ref`](https://en.cppreference.com/w/cpp/atomic/atomic_ref) — 为非原子对象提供原子操作。
- [cppreference: `std::atomic::wait` / `notify_one` / `notify_all`](https://en.cppreference.com/w/cpp/atomic/atomic/wait) — 原子等待/通知机制。

### 相关知识点

- [[01-threads-and-synchronization|线程与同步原语]] — 互斥锁、条件变量的标准用法。
- [[02-async-future-promise|std::async 与 future/promise]] — 任务级异步。
- Memory reclamation: Hazard Pointers, RCU, Epoch-Based Reclamation — lock-free 数据结构的内存安全回收方案。

---

## 附录：快速参考卡

### 原子操作速查

```cpp
std::atomic<T> a;

// 基本读写
a.store(val, order);        // 原子写（release / relaxed / seq_cst）
a.load(order);              // 原子读（acquire / relaxed / seq_cst）
a.exchange(val, order);     // 交换并返回旧值

// RMW（读-修改-写）
a.fetch_add(n, order);      // 加 n，返回旧值
a.fetch_sub(n, order);      // 减 n，返回旧值
a.fetch_and(n, order);      // 按位与，返回旧值
a.fetch_or(n, order);       // 按位或，返回旧值
a.fetch_xor(n, order);      // 按位异或，返回旧值

// CAS
a.compare_exchange_weak(expected, desired, succ, fail);
a.compare_exchange_strong(expected, desired, succ, fail);

// 便捷运算符（默认 seq_cst）
++a; a++; a += n;

// C++20
a.wait(old);                // 阻塞直到值 ≠ old
a.notify_one();             // 唤醒一个等待者
a.notify_all();             // 唤醒所有等待者
```

### 内存序速查

```
             load 可用的序        store 可用的序
relaxed      ✅                   ✅
consume      ✅ (不推荐)          ❌
acquire      ✅                   ❌
release      ❌                   ✅
acq_rel      ❌ (仅 RMW)          ❌ (仅 RMW)
seq_cst      ✅ (默认)            ✅ (默认)
```
