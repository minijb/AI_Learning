# C++ 内存序 (memory_order) 深度剖析

> 深度等级: 第 6 层（源码分析）
> 关联学习计划: [[game-engine-dev]]
> 分析日期: 2026-05-20
> 关键词: `std::memory_order`, `acquire-release`, `happens-before`, `synchronize-with`, Job System, 无锁队列

---

## 第 1 层: 直觉理解

想象你在一个大型工厂（多核 CPU）工作。工厂里有很多工人（线程），他们需要共享一个公告板（内存）来传递信息。

**问题**：现代工厂为了提高效率，允许工人**不按顺序**完成手头的任务（指令重排序），只要最终结果看起来正确。但当你需要**团队协作**时，这种"乱序"就可能导致灾难——你收到了"任务完成"的通知，但实际上部分工作还没做完。

**内存序**就是一套"沟通协议"，告诉工人什么时候必须按顺序来，什么时候可以乱序。

---

## 第 2 层: 使用场景

### 什么时候必须用原子操作 + 内存序？

| 场景 | 为什么 | 典型引擎应用 |
|------|--------|-------------|
| 一个线程写、另一个线程读同一变量 | 防止编译器优化掉写入，防止 CPU 乱序导致读到旧值 | 主线程提交渲染数据，渲染线程消费 |
| 多线程竞争更新计数器 | 防止"读后写"竞争导致更新丢失 | 全局帧计数器、性能统计 |
| 无锁数据结构 | 需要精确控制可见性顺序 | Job System 任务队列、消息总线 |
| 标志位同步 | 需要保证标志位之前的所有写入可见 | 游戏状态切换、关卡加载完成通知 |

### 什么时候不需要？

- 单线程程序
- 已经用 `std::mutex` 保护的数据（mutex 的 lock/unlock 自带内存序语义）
- 只读共享数据（初始化完成后不再修改）

---

## 第 3 层: API 层

### 六种 memory_order

```cpp
enum memory_order {
    memory_order_relaxed,   // 最弱：只保证原子性
    memory_order_consume,   // 依赖顺序（C++17 后不建议使用）
    memory_order_acquire,   // 获取语义：用于读操作
    memory_order_release,   // 释放语义：用于写操作
    memory_order_acq_rel,   // 获取+释放：用于读-修改-写操作
    memory_order_seq_cst    // 默认：顺序一致性，最强
};
```

### 合法的组合

| 操作类型 | 允许的 memory_order |
|---------|-------------------|
| load | relaxed, consume, acquire, seq_cst |
| store | relaxed, release, seq_cst |
| 读-修改-写 (RMW) | relaxed, acquire, release, acq_rel, seq_cst |

### std::atomic 核心操作

```cpp
std::atomic<T> a;

a.load(order);                          // 原子读
a.store(val, order);                    // 原子写
a.exchange(val, order);                 // 原子交换（返回旧值）
a.compare_exchange_weak(expected, desired, success_order, failure_order);
a.compare_exchange_strong(expected, desired, success_order, failure_order);
// compare_exchange：如果当前值 == expected，则设为 desired，返回 true
//                   否则把当前值写入 expected，返回 false
// weak 可能伪失败（即使值相等也返回 false），但在循环中性能更好
```

---

## 第 4 层: 行为契约

### happens-before 关系

C++ 内存模型的核心是定义**happens-before**关系：如果操作 A happens-before 操作 B，那么 A 的所有副作用对 B 可见。

happens-before 关系的建立方式：
1. **同一线程内**：如果 A 在源代码中先于 B，则 A sequenced-before B，进而 A happens-before B
2. **原子操作间**：如果 A 是 release 写，B 是读取该值的 acquire 读，则 A synchronizes-with B，进而 A happens-before B
3. **传递性**：如果 A happens-before B，B happens-before C，则 A happens-before C

### synchronize-with 的精确条件

```cpp
// 线程 1
atomic.store(x, release);   // A

// 线程 2
auto y = atomic.load(acquire);  // B

// A synchronizes-with B 当且仅当：
// 1. A 是 release 或更强的写操作
// 2. B 是 acquire 或更强的读操作
// 3. B 读到了 A 写入的值（或同一变量后续的写）
// 4. A 和 B 访问的是同一个原子变量
```

**关键限制**：synchronize-with 是**成对**的。一个 release 写只能和一个读到该值的 acquire 读建立关系。

### 陷阱：不同变量之间没有同步

```cpp
std::atomic<int> a{0};
std::atomic<int> b{0};
int x = 0;

// 线程 1
x = 42;              // (1) 非原子写
a.store(1, release); // (2) release 写

// 线程 2
while (a.load(acquire) != 1) {}  // (3) 读到 1，与 (2) synchronize-with
assert(x == 42);                  // (4) 安全！x 的写 happens-before 这里

// 线程 3
while (b.load(acquire) != 1) {}  // (5) 读 b，但 b 从未被写入！
// 即使线程 3 "同时"在执行，它和线程 1 没有 synchronize-with 关系
// 如果 b 被某个操作设为 1，那个操作必须和线程 1 有 happens-before 关系
// 否则 x 的可见性无法传递到线程 3
```

---

## 第 5 层: 实现原理

### 编译器重排序

编译器为了优化，可能在单线程语义等价的前提下重排序指令：

```cpp
int a = 1;      // (1)
int b = 2;      // (2)
atomic_flag.store(true, release);  // (3)
```

如果没有内存序限制，编译器可能重排序为 (2), (1), (3)，因为在单线程看来结果一样。

但 `release` 告诉编译器：**(1) 和 (2) 不能移到 (3) 之后**。这通过在 (3) 之前插入编译器屏障（compiler barrier）实现：

```cpp
// 伪代码：编译器视角
int a = 1;
int b = 2;
COMPILER_BARRIER();  // 阻止重排序
atomic_store_release(&flag, true);
```

### CPU 重排序和内存屏障

现代 CPU（x86、ARM）为了性能也会重排序指令：

| 架构 | Store-Store 重排序 | Store-Load 重排序 | Load-Load 重排序 | Load-Store 重排序 |
|------|-------------------|------------------|-----------------|-----------------|
| x86/x64 | 不允许 | 允许 | 不允许 | 不允许 |
| ARM | 允许 | 允许 | 允许 | 允许 |

**这意味着**：
- x86 上，`memory_order_acquire/release` 通常不需要额外的 CPU 屏障指令（因为 x86 本身就不允许某些重排序），只需编译器屏障
- ARM 上，需要插入 `dmb`（Data Memory Barrier）指令来保证顺序

```cpp
// 伪汇编：release store on ARM
// C++: flag.store(1, memory_order_release);
str r1, [flag]      // 存储 flag
dmb ish             // 内存屏障（Inner Shareable）

// 伪汇编：acquire load on ARM
// C++: while (flag.load(memory_order_acquire) == 0);
dmb ish             // 内存屏障
ldr r1, [flag]      // 加载 flag
cmp r1, #0
beq loop
```

### x86 上的优化

```cpp
// x86 上，所有 store 都自带 release 语义，所有 load 都自带 acquire 语义
// 所以 memory_order_relaxed 的 store/load 在 x86 上和 release/acquire 有相同的硬件行为
// 但编译器优化层面不同！

// 编译器仍然可以在 relaxed 下重排序：
atomic.store(1, relaxed);  // 编译器可能把前面的非原子操作移到这里之后

// 所以即使 x86 上，也不能用 relaxed 替代 acquire/release！
```

---

## 第 6 层: 源码分析

### 分析 1：libstdc++ 的 atomic_store

```cpp
// GCC/libstdc++ 实现（简化）
// 文件: libstdc++-v3/include/bits/atomic_base.h

template<typename _Tp>
inline void atomic_store_explicit(atomic<_Tp>* __a, _Tp __i, memory_order __m) noexcept {
    __atomic_store_n(&__a->_M_i, __i, static_cast<int>(__m));
}

// __atomic_store_n 是 GCC 内置函数，编译器根据内存序和目标架构生成正确代码
```

### 分析 2：无锁栈（Treiber Stack）

```cpp
// 经典的无锁栈实现，常用于引擎的内存池或任务池
// 源码来源: Treiber, 1986 "Systems Programming: Coping with Parallelism"

template<typename T>
class LockFreeStack {
    struct Node {
        T data;
        Node* next;
    };

public:
    void push(const T& data) {
        Node* newNode = new Node{data, nullptr};

        // acquire：读取 head 的当前值
        newNode->next = head_.load(std::memory_order_acquire);

        // compare_exchange_weak:
        // - success_order = release：如果成功，新 head 的写入带 release 语义
        //   保证 newNode 的构造对后续 pop 线程可见
        // - failure_order = acquire：如果失败，重新读取 head 带 acquire 语义
        while (!head_.compare_exchange_weak(
            newNode->next,       // expected: 如果 head 没变，这是旧 head
            newNode,             // desired: 新 head
            std::memory_order_release,   // success
            std::memory_order_acquire))  // failure
        {
            // 如果失败，newNode->next 被更新为当前 head，继续尝试
        }
    }

    bool pop(T& result) {
        // acquire：读取 head，保证看到 push 线程的 release 写入
        Node* oldHead = head_.load(std::memory_order_acquire);

        while (oldHead != nullptr) {
            // 尝试把 head 更新为 oldHead->next
            // success: 获取 head 所有权
            // failure: 重新读取 head（acquire）
            if (head_.compare_exchange_weak(
                oldHead,
                oldHead->next,
                std::memory_order_acquire,  // success: 获取所有权
                std::memory_order_acquire)) // failure: 重读
            {
                result = oldHead->data;
                // 危险：这里不能 delete oldHead！
                // 因为其他线程可能还在读取 oldHead->next
                // 生产环境需要 Hazard Pointer 或 Epoch-Based Reclamation
                return true;
            }
        }
        return false;  // 栈空
    }

private:
    std::atomic<Node*> head_{nullptr};
};
```

**内存序分析：**

| 操作 | 内存序 | 为什么 |
|------|--------|--------|
| push 读 head | acquire | 看到之前 pop 对 head 的更新 |
| push 写 head (成功) | release | 保证 newNode 的构造和数据对 pop 可见 |
| pop 读 head | acquire | 看到之前 push 的 release 写入 |
| pop 写 head (成功) | acquire | 获取 Node 的所有权，保证后续读取 data 是安全的 |
| pop 写 head (失败) | acquire | 重读 head，需要看到最新的 push 操作 |

### 分析 3：Jolt Physics Job System 的同步原语

```cpp
// Jolt Physics 源码（简化）
// 文件: Jolt/Core/JobSystem.h, Jolt/Core/JobSystem.cpp
// 版本: v5.x

class JobSystem {
public:
    // Job 完成后，减少依赖计数
    void JobFinished(Job* job) {
        // 获取需要通知的 jobs
        uint32_t numDependencies = job->mNumDependencies;
        uint32_t dependencyTableIdx = job->mDependencyTable;

        for (uint32_t i = 0; i < numDependencies; ++i) {
            Job* dependency = mDependencyTable[dependencyTableIdx + i];

            // 原子递减依赖计数（acq_rel）
            // - 之前的写操作（如 Job 结果写入）需要 release
            // - 递减后检查是否为 0，需要 acquire 看到其他线程的递减
            uint32_t remaining = dependency->mNumDependencies.fetch_sub(1, std::memory_order_acq_rel);

            if (remaining == 1) {
                // 最后一个依赖完成，可以执行了
                QueueJob(dependency);
            }
        }
    }

    // 主线程添加 Job
    void AddJob(Job* job) {
        // release：保证 job 的所有设置对工作者线程可见
        job->mNumDependencies.store(initialDependencyCount, std::memory_order_release);
        QueueJob(job);
    }

    // 工作者线程执行 Job
    void ExecuteJob(Job* job) {
        // acquire：确保看到 AddJob 中的 release 写入
        job->Execute();
        JobFinished(job);
    }

private:
    // ...
};
```

**关键点**：`fetch_sub(1, acq_rel)` 是 RMW 操作：
- 读部分用 acquire：看到之前所有对 `mNumDependencies` 的递减
- 写部分用 release：如果后续有线程读到这个递减后的值，它能看到这个线程之前的所有写操作

---

## 第 7 层: 对比与边界

### 不同内存序的性能对比

| 内存序 | x86 开销 | ARM 开销 | 典型延迟增加 |
|--------|---------|---------|------------|
| relaxed | 无（纯编译器） | 无 | 基准 |
| acquire/release | 无（x86 自带） | 1x dmb 指令 | ARM: ~20-50ns |
| seq_cst | 无或 mfence | 1x dmb | 可能触发总线同步 |

**注意**：延迟数字高度依赖具体 CPU 和场景。在高度竞争的情况下，内存屏障的开销可能远大于指令本身。

### 什么时候用 seq_cst？

```cpp
// 场景：多生产者竞争入队，需要确定"谁先谁后"

std::atomic<uint64_t> ticket{0};

void enqueue(Task task) {
    // seq_cst 保证所有线程以相同顺序看到 ticket 的递增
    uint64_t myTicket = ticket.fetch_add(1, std::memory_order_seq_cst);
    queue[myTicket % CAPACITY] = task;
}

// 如果用 relaxed：
// 线程 A 读到 ticket=5
// 线程 B 读到 ticket=5（同一时刻）
// 两者都认为自己拥有 slot 5，数据竞争！
// seq_cst 保证 fetch_add 是全局有序的，不会出现这种情况
```

### 常见误用模式

```cpp
// 误用 1：用 relaxed 实现标志位同步
std::atomic<bool> ready{false};
int data = 0;

// 线程 1
data = 42;
ready.store(true, relaxed);  // 不保证 data 的写入先完成！

// 线程 2
if (ready.load(relaxed)) {   // 可能看到 true 但 data 还是 0
    assert(data == 42);      // 可能失败！
}

// 误用 2：store 用 acquire / load 用 release
ready.store(true, acquire);  // 编译错误！store 不能用 acquire
ready.load(release);         // 编译错误！load 不能用 release

// 误用 3：认为 atomic 变量本身自动同步其他变量
// 错误理解："我把 data 设为 42，然后 atomic_flag = true，
//           另一个线程看到 flag=true 就自动看到 data=42"
// 正确理解：atomic_flag.store(true, release) + flag.load(acquire) 的 pair
//           才建立 synchronize-with，进而传递 data 的可见性
```

### 与 mutex 的选择

| 条件 | 推荐方案 | 理由 |
|------|---------|------|
| 竞争不激烈 (<10% 时间争用) | mutex | 简单、正确、可维护 |
| 极热路径、高竞争 | 无锁 + 正确内存序 | 避免上下文切换和内核态 |
| 需要等待（条件变量语义） | mutex + condition_variable | 无锁不能阻塞等待 |
| 数据结构简单（计数器、栈） | 原子操作 | 实现简单，收益大 |
| 数据结构复杂（哈希表、树） | mutex + 定期优化 | 无锁实现极其复杂且易错 |

---

## 常见面试题

1. **为什么 `compare_exchange_weak` 比 `compare_exchange_strong` 在循环中更快？**
   - weak 在某些架构上（如 SPARC、ARM）允许伪失败，即即使比较值相等也可能返回 false。这避免了在极少数竞争情况下生成额外的内存屏障代码。在循环中重试是预期行为，所以 weak 更合适。

2. **x86 上 `memory_order_relaxed` 和 `memory_order_release` 的 store 有硬件区别吗？**
   - 没有硬件区别。x86 的所有 store 都自带 release 语义。但编译器优化层面有区别：release 阻止编译器重排序，relaxed 不阻止。所以即使在 x86 上也不能用 relaxed 替代 release。

3. **什么是 ABA 问题？如何解决？**
   - ABA：线程 1 读取 A，线程 2 把 A→B→A，线程 1 的 CAS 成功但实际状态已变。解决：tagged pointer（低几位存版本号）、Hazard Pointer、Epoch-Based Reclamation。

4. **`volatile` 能替代 `std::atomic` 吗？**
   - 绝对不能。volatile 只告诉编译器"不要优化掉对这个变量的读写"，它不提供原子性、不保证内存序、不阻止 CPU 重排序。

---

## 延伸主题

- [[lock-free-data-structures]] — 无锁队列、无锁哈希表、Hazard Pointer
- [[cache-coherency-protocols]] — MESI 协议、伪共享、缓存行对齐
- [[job-system-implementation]] — 工作窃取、任务图依赖、线程亲和性
- [[constexpr-metaprogramming]] — 编译期计算替代运行时原子操作的可能性
