---
title: "C++ 内存模型与原子操作"
updated: 2026-06-08
---

> 所属计划: [[plan|C++ 内存模型]]
> 预计耗时: 60 分钟
> 前置知识: [[07-low-level-memory-operations|底层内存操作（memcpy 等）]]

---

## 1. 概念讲解

### 为什么需要这个？

多线程编程是游戏引擎、服务器、操作系统开发者的 daily bread。但"代码看起来按顺序执行"的直觉在多核 CPU + 编译器优化 + CPU 乱序执行的现实中完全失效。

C++11 引入了标准化的内存模型，定义了：
- 什么是"线程间可见"的写操作
- 编译器可以对代码做什么重排
- 什么样的同步能保证数据竞争不导致 UB

不学这个，你写的"无锁队列"可能是数据竞争炸弹。

### 核心思想

**C++ 内存模型 = "指定哪些内存操作的可见性顺序"。**

三个核心概念：
1. **Sequenced-before**：同一线程内，表达式按程序顺序执行（但编译器可能重排，只要不改变单线程可观测行为）
2. **Happens-before**：跨线程的因果关系。如果 A happens-before B，线程 B 中能看到 A 的结果
3. **Synchronizes-with**：原子操作之间的"发布-订阅"关系。`release` 写和 `acquire` 读配对，建立 happens-before

```mermaid
sequenceDiagram
    participant T1 as Thread 1
    participant Mem as Memory
    participant T2 as Thread 2

    T1->>Mem: atomic_store(&flag, 1, memory_order_release)
    Note over T1,Mem: release: 之前的所有写不能重排到本操作之后
    Mem->>T2: atomic_load(&flag, memory_order_acquire)
    Note over Mem,T2: acquire: 之后的所有读不能重排到本操作之前
    T2->>T2: 此时 T2 可以看到 flag==1，<br/>且 T1 在 store 之前的<br/>所有写也对 T2 可见
```

六种内存序：

| 内存序 | 语义 | 适用场景 |
|--------|------|---------|
| `memory_order_relaxed` | 无同步，只保证原子性 | 计数器（不要求顺序） |
| `memory_order_consume` | 依赖关系同步（少用） | 数据依赖链读取 |
| `memory_order_acquire` | 之后的读不能重排到本操作之前 | 锁的 `lock()` |
| `memory_order_release` | 之前的写不能重排到本操作之后 | 锁的 `unlock()` |
| `memory_order_acq_rel` | 同时 acquire + release | CAS 循环 |
| `memory_order_seq_cst` | 全局顺序一致性（最严格） | 默认，最简单但有时过强 |

> [!tip] 类比
> 想象两个办公室（线程）通过公告板（共享内存）通信。
> - `relaxed`：你写了公告，但不保证对方什么时候看到。消息最终会到，但顺序不定。
> - `release`/`acquire`：你在公告上贴了一张"已更新"标签（release）。对方看到标签后（acquire），知道标签之前的所有内容都已经贴好了。
> - `seq_cst`：全公司只有一个麦克风。谁拿到麦克风谁才能广播，所有人听到的顺序完全一致。

---

## 2. 代码示例

```cpp
#include <atomic>
#include <iostream>
#include <thread>
#include <vector>

// --- 基础原子操作 ---
void demo_atomic_basics() {
    std::cout << "=== Atomic basics ===\n";
    std::atomic<int> counter{0};

    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&counter] {
            for (int j = 0; j < 100000; ++j) {
                counter.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }
    for (auto& t : threads) t.join();
    std::cout << "counter = " << counter.load() << " (expected 400000)\n";
}

// --- Release/Acquire 同步 ---
std::atomic<int> data{0};
std::atomic<bool> ready{false};

void producer() {
    data.store(42, std::memory_order_relaxed);
    ready.store(true, std::memory_order_release);  // 之前的写对 acquire 方可见
}

void consumer() {
    while (!ready.load(std::memory_order_acquire)) {
        // 自旋等待
    }
    // 到这里，data 必然等于 42
    std::cout << "data = " << data.load(std::memory_order_relaxed) << "\n";
}

void demo_release_acquire() {
    std::cout << "\n=== Release/Acquire ===\n";
    data = 0;
    ready = false;
    std::thread t1(producer);
    std::thread t2(consumer);
    t1.join(); t2.join();
}

// --- 有锁 vs 无锁 ---
class Spinlock {
    std::atomic<bool> locked_{false};
public:
    void lock() {
        while (locked_.exchange(true, std::memory_order_acquire)) {
            // 自旋：已被锁定，继续尝试
        }
    }
    void unlock() {
        locked_.store(false, std::memory_order_release);
    }
};

int shared_counter = 0;
Spinlock spin;

void demo_spinlock() {
    std::cout << "\n=== Spinlock ===\n";
    shared_counter = 0;
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([] {
            for (int j = 0; j < 100000; ++j) {
                spin.lock();
                ++shared_counter;  // 临界区
                spin.unlock();
            }
        });
    }
    for (auto& t : threads) t.join();
    std::cout << "shared_counter = " << shared_counter << "\n";
}

// --- 内存序对比：内存序过强/过弱的后果 ---
std::atomic<int> x{0};
std::atomic<int> y{0};
std::atomic<int> r1{0};
std::atomic<int> r2{0};

void memory_order_demo() {
    std::cout << "\n=== Memory order comparison ===\n";
    int reorder_count = 0;
    for (int trial = 0; trial < 100000; ++trial) {
        x = 0; y = 0;
        std::thread t1([] {
            x.store(1, std::memory_order_relaxed);
            y.store(1, std::memory_order_relaxed);
        });
        std::thread t2([] {
            int a = y.load(std::memory_order_relaxed);
            int b = x.load(std::memory_order_relaxed);
            r1 = a;
            r2 = b;
        });
        t1.join(); t2.join();
        if (r1 == 1 && r2 == 0) {
            ++reorder_count;  // 观察到 reorder!
        }
    }
    std::cout << "Observed reorder (r1=1, r2=0) in "
              << reorder_count << "/100000 trials\n";
}

int main() {
    demo_atomic_basics();
    demo_release_acquire();
    demo_spinlock();
    memory_order_demo();
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -pthread -o atomics atomics.cpp && ./atomics
```

**预期输出:**
```text
=== Atomic basics ===
counter = 400000 (expected 400000)

=== Release/Acquire ===
data = 42

=== Spinlock ===
shared_counter = 400000

=== Memory order comparison ===
Observed reorder (r1=1, r2=0) in .../100000 trials
  // 在 x86-64 上可能很少观察到，因为 x86 本身有较强一致性
  // 但在 ARM/POWER 上 reorder 非常常见
```

> [!info] x86 与 ARM 差异
> x86-64 架构本身提供较强的内存一致性（所有写操作自动具有 release 语义，所有读具有 acquire 语义），所以 `relaxed` 在 x86 上往往"看起来"工作正常。但编译器重排仍然可能发生。ARM 和 POWER 是弱内存序架构——如果你不正确使用内存序，100% 会触发数据竞争。
>
> **编写平台无关的并发代码：始终显式指定内存序，不要依赖 x86 的"宽容"。**

---

## 3. 练习

### 练习 1: 正确的双检查锁 (DCLP)
经典的"双检查锁"单例模式在 C++11 前是 broken 的：
```cpp
// 错误版本（C++11 前 broken）
Singleton* getInstance() {
    if (!instance_) {                    // `#1`
        std::lock_guard<std::mutex> lock(mutex_);
        if (!instance_) {
            instance_ = new Singleton(); // `#2` 可能重排！
        }
    }
    return instance_;                    // `#3`
}
```
问题：第 `#2` 步中，指针赋值可能先于构造函数完成，导致 `#3` 返回一个未完全构造的对象。用 `std::atomic` 和正确的内存序修复这个问题。（提示：`std::memory_order_acquire` + `std::memory_order_release`，或直接用 `std::call_once`/`magic static`）

### 练习 2: 无锁栈 (Treiber Stack)
实现一个最简单的无锁栈：
```cpp
class LockFreeStack {
    struct Node { int data; Node* next; };
    std::atomic<Node*> head_{nullptr};
public:
    void push(int value);
    bool pop(int& value);  // 返回 false 表示栈空
};
```
使用 `compare_exchange_weak` 实现 `push` 和 `pop`。注意 ABA 问题会在本练习中存在——描述它，并说明 `std::atomic` 的 `compare_exchange` 不解决 ABA。（高阶方案：使用 hazard pointer 或 tagged pointer）

### 练习 3: 伪共享 (False Sharing) 实验（可选）
```cpp
struct alignas(64) PaddedCounter {
    std::atomic<int> value{0};
    char pad[64 - sizeof(std::atomic<int>)];
};
```
创建两个线程，一个只写 `counter[0]`，另一个只写 `counter[1]`。分别测试 `counter` 有 padding 和没有 padding 时的性能差异。解释为什么无 padding 时变慢（缓存行竞争）。

---
## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **问题根源：** `instance_ = new Singleton()` 包含三步：(1) 分配内存，(2) 调用构造函数，(3) 把指针赋值给 `instance_`。编译器和 CPU 可以重排 (2) 和 (3)，导致 `#1` 处看到非空指针但对象尚未构造完成。
>
> **方案 A：用 `std::atomic` + release/acquire 修复 DCLP（C++11 起正确）：**
> ```cpp
> #include <atomic>
> #include <mutex>
>
> class Singleton {
> public:
>     static Singleton* getInstance() {
>         // acquire：确保读到 instance 非空时，构造函数的效果也可见
>         Singleton* tmp = instance_.load(std::memory_order_acquire);
>         if (tmp == nullptr) {
>             std::lock_guard<std::mutex> lock(mutex_);
>             tmp = instance_.load(std::memory_order_relaxed);
>             if (tmp == nullptr) {
>                 tmp = new Singleton();
>                 // release：确保构造完成后再写入 instance_
>                 instance_.store(tmp, std::memory_order_release);
>             }
>         }
>         return tmp;
>     }
>
> private:
>     Singleton() = default;
>     static std::atomic<Singleton*> instance_;
>     static std::mutex mutex_;
> };
>
> std::atomic<Singleton*> Singleton::instance_{nullptr};
> std::mutex Singleton::mutex_;
> ```
>
> **方案 B（推荐）：用 C++11 magic static（最简最安全）：**
> ```cpp
> class Singleton {
> public:
>     static Singleton& getInstance() {
>         // C++11 起：局部静态变量的初始化是线程安全的
>         // 编译器自动插入了 DCLP 所需的 acquire/release 屏障
>         static Singleton instance;
>         return instance;
>     }
> private:
>     Singleton() = default;
> };
> ```
>
> **方案 C（标准库方案）：`std::call_once` + `std::once_flag`：**
> ```cpp
> #include <mutex>
> class Singleton {
> public:
>     static Singleton& getInstance() {
>         std::call_once(flag_, [] { instance_.reset(new Singleton); });
>         return *instance_;
>     }
> private:
>     Singleton() = default;
>     static std::once_flag flag_;
>     static std::unique_ptr<Singleton> instance_;
> };
> ```
>
> **为什么方案 B 最优：** `static` 局部变量自 C++11 起由编译器保证线程安全初始化——它内部使用与 DCLP 相同的 acquire/release 语义，但**(1)** 零出错可能（编译器替你写了正确的内存序），**(2)** 无显式锁/原子操作维护负担，**(3)** 析构顺序由标准定义（与构造逆序）。游戏引擎中如非有特殊理由（如需要提前释放、跨 DLL 边界），一律用 magic static。

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <atomic>
> #include <iostream>
> #include <thread>
> #include <vector>
>
> class LockFreeStack {
>     struct Node {
>         int  data;
>         Node* next;
>         Node(int d, Node* n = nullptr) : data(d), next(n) {}
>     };
>
>     std::atomic<Node*> head_{nullptr};
>
> public:
>     ~LockFreeStack() {
>         // 简单清理（单线程下安全；多线程下需更复杂的退休机制）
>         Node* n = head_.load(std::memory_order_relaxed);
>         while (n) {
>             Node* next = n->next;
>             delete n;
>             n = next;
>         }
>     }
>
>     void push(int value) {
>         Node* new_node = new Node(value);
>         // 将 new_node 的 next 设为当前 head
>         new_node->next = head_.load(std::memory_order_relaxed);
>
>         // CAS 循环：尝试把 head 从 old_head 改为 new_node
>         // compare_exchange_weak 可能伪失败（spurious failure），需要循环
>         while (!head_.compare_exchange_weak(
>                     new_node->next,   // expected: 期望的 head 值
>                     new_node,         // desired:  要写入的新值
>                     std::memory_order_release,
>                     std::memory_order_relaxed)) {
>             // CAS 失败时，new_node->next 被更新为当前 head
>             // 循环继续尝试
>         }
>     }
>
>     bool pop(int& value) {
>         Node* old_head = head_.load(std::memory_order_acquire);
>
>         while (old_head != nullptr) {
>             // 尝试 CAS：把 head 从 old_head 改为 old_head->next
>             if (head_.compare_exchange_weak(
>                         old_head,          // expected
>                         old_head->next,    // desired
>                         std::memory_order_acquire,
>                         std::memory_order_relaxed)) {
>                 value = old_head->data;
>                 // ⚠️ ABA 问题窗口：这里 delete old_head 不安全
>                 // （另一线程可能在 old_head 被删除后重新分配了相同地址的节点）
>                 // delete old_head;  // 取消注释会暴露 ABA 问题
>                 return true;
>             }
>             // CAS 失败 → old_head 被更新为当前 head，继续循环
>         }
>         return false;  // 栈空
>     }
> };
> ```
>
> **ABA 问题详解：**
>
> 时间线：线程 A 读 `head = X`，线程 B 弹出 X 并 delete X，线程 B 又 push 新节点恰好分配到 X 的地址，线程 A 的 CAS 成功——但它比较的是地址值，不知道 X 已经被删除+重用过。结果：线程 A 的 `old_head->next` 指向一个已释放或已被重用的节点。
>
> **为什么 `std::atomic::compare_exchange` 不解决 ABA：** CAS 只比较**值**（地址）——它不知道指针指向的对象的生命周期。在 C++ 的无 GC 环境中，地址可以被 `delete` + `new` 重用，使得 CAS 看到"相同"的地址但对象已经不同。
>
> **解决方案（超出本练习范围但标注方向）：**
> 1. **Tagged pointer（标记指针）：** 在指针高位存储一个版本号，每次修改递增。CAS 同时比较地址+版本号——地址可能重用但版本号不会回退（x86-64 上可用 48 位地址 + 16 位计数器）
> 2. **Hazard pointer：** 读取线程在解引用前"发布"它正在使用的指针，删除线程检查是否有线程持有该指针后再真正释放
> 3. **Epoch-based reclamation (RCU)：** 延迟删除——确认没有线程还在临界区后批量回收

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <atomic>
> #include <chrono>
> #include <iostream>
> #include <thread>
>
> // 无 padding：两个 counter 在同一缓存行（64 字节）
> struct NoPadding {
>     std::atomic<int> a{0};
>     std::atomic<int> b{0};
> };
>
> // 有 padding：每个 counter 独占一个缓存行
> struct alignas(64) PaddedCounter {
>     alignas(64) std::atomic<int> a{0};
>     alignas(64) std::atomic<int> b{0};
> };
>
> template<typename Counters>
> void run_benchmark(const char* label) {
>     Counters c;
>     const int ITERS = 10'000'000;
>
>     auto start = std::chrono::high_resolution_clock::now();
>
>     std::thread t1([&] {
>         for (int i = 0; i < ITERS; ++i) {
>             c.a.store(i, std::memory_order_relaxed);
>         }
>     });
>     std::thread t2([&] {
>         for (int i = 0; i < ITERS; ++i) {
>             c.b.store(i, std::memory_order_relaxed);
>         }
>     });
>     t1.join(); t2.join();
>
>     auto end = std::chrono::high_resolution_clock::now();
>     auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
>     std::cout << label << ": " << ms << " ms\n";
> }
>
> int main() {
>     std::cout << "sizeof(NoPadding)     = " << sizeof(NoPadding) << "\n";
>     std::cout << "sizeof(PaddedCounter) = " << sizeof(PaddedCounter) << "\n";
>     std::cout << "L1 cache line        = 64 bytes (typical)\n\n";
>
>     run_benchmark<NoPadding>("NoPadding    ");
>     run_benchmark<PaddedCounter>("PaddedCounter");
>     return 0;
> }
> ```
>
> **编译运行：**
> ```bash
> g++ -std=c++17 -O2 -pthread -o false_sharing false_sharing.cpp && ./false_sharing
> ```
>
> **预期结果：** `PaddedCounter` 版本显著快于 `NoPadding`（通常 2-5x）。
>
> **原理解释：**
> - 现代 CPU 的缓存一致性协议（如 MESI）以**缓存行**（通常 64 字节）为单位管理缓存一致性
> - `NoPadding` 中 `a` 和 `b` 在同一缓存行内。线程 1 写 `a` 时，该缓存行在核心 1 的 L1 中变为 Modified；线程 2 写 `b` 时，缓存行必须先失效、从核心 1 传输到核心 2 → 每次写触发缓存行在核心间 ping-pong
> - 即使两个线程操作的是**不同的变量**，因为它们共享缓存行，硬件也当成"同一块数据在竞争" → 称为**伪共享（False Sharing）**
> - `PaddedCounter` 通过 `alignas(64)` 将 `a` 和 `b` 分隔到不同缓存行，两个线程各自持有各自行的 Exclusive/Modified 状态，无需传输缓存行 → 性能显著提升
>
> **工程实践：** 游戏引擎中的多线程 ECS、任务调度器、无锁队列的生产-消费索引频繁遇到伪共享。防御手段：`alignas(64)` 或 `alignas(std::hardware_destructive_interference_size)` (C++17) 进行缓存行隔离。但不要盲目 padding 所有原子变量——只在性能分析确认伪共享是瓶颈时才用。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。


## 4. 扩展阅读

- [cppreference — Memory order](https://en.cppreference.com/w/cpp/atomic/memory_order)
- [cppreference — std::atomic](https://en.cppreference.com/w/cpp/atomic/atomic)
- [cppreference — compare_exchange_weak](https://en.cppreference.com/w/cpp/atomic/atomic/compare_exchange)
- [Herb Sutter: atomic Weapons](https://www.youtube.com/watch?v=A8eCGOqgvH4) (CppCon 2012)
- [Jeff Preshing: Memory Barrier](https://preshing.com/20120710/memory-barriers-are-like-source-control-operations/)
- 《C++ Concurrency in Action》by Anthony Williams

---

## 常见陷阱

- **陷阱 1: 用 `volatile` 做线程同步。** `volatile` 只阻止编译器优化（确保每次都读写内存），不保证原子性、不保证内存序、不阻止 CPU 乱序执行。对 `volatile int` 做 `++` 不是原子的。线程间同步用 `std::atomic`。
- **陷阱 2: 假设 `std::atomic<int>` 的默认操作是顺序一致性。** `counter++` 使用 `memory_order_seq_cst`（最安全但最慢）。在热路径上应该显式使用 `fetch_add(..., memory_order_relaxed)` 如果语义允许。
- **陷阱 3: Release/Acquire 配对不完整。** `store(..., release)` 后必须有对应的 `load(..., acquire)`。如果读方用 `relaxed`，happens-before 不建立，之前的写可能不可见。
- **陷阱 4: 对有依赖的数据用 `relaxed`。** 如果线程 B 读取一个指针（`relaxed`），然后解引用该指针读取数据，`relaxed` 不保证数据的可见性。应该用 `acquire`/`consume`。
