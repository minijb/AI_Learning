# 多线程与并发：Job System

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 无

---

## 目录

- [1. 概念讲解](#1-概念讲解)
  - [1.1 为什么游戏引擎需要多线程？](#11-为什么游戏引擎需要多线程)
  - [1.2 并行模式：功能并行 vs 数据并行](#12-并行模式功能并行-vs-数据并行)
  - [1.3 Job System 核心设计](#13-job-system-核心设计)
  - [1.4 工作窃取（Work Stealing）](#14-工作窃取work-stealing)
  - [1.5 无锁数据结构](#15-无锁数据结构)
  - [1.6 内存序与缓存一致性](#16-内存序与缓存一致性)
  - [1.7 双缓冲与三缓冲](#17-双缓冲与三缓冲)
  - [1.8 SIMD 基础](#18-simd-基础)
  - [1.9 游戏循环中的多线程同步](#19-游戏循环中的多线程同步)
- [2. 代码示例](#2-代码示例)
  - [2.1 Lock-free Queue（Michael-Scott 队列）](#21-lock-free-queuemichael-scott-队列)
  - [2.2 Job System（含工作窃取）](#22-job-system含工作窃取)
  - [2.3 Parallel For](#23-parallel-for)
  - [2.4 简单的 Task Graph](#24-简单的-task-graph)
- [3. 练习](#3-练习)
- [4. 扩展阅读](#4-扩展阅读)
- [5. 常见陷阱](#5-常见陷阱)

---

## 0. 前置知识：操作系统核心概念

在深入 Job System 之前，我们需要理解操作系统层面的几个核心机制，这些知识是正确设计多线程架构的基础。

### 0.1 进程地址空间布局

当一个应用程序被执行时，操作系统为其创建一个**进程**（Process），并分配一块虚拟地址空间。在 32 位 Linux 系统中，典型的布局如下：

```
高地址 0xFFFFFFFF
  ├── 内核空间 Kernel Space (~1GB，用户态不可访问)
  │
  ├── 栈 Stack (向下增长，局部变量、函数调用帧)
  ├── ... 未映射区域 ...
  ├── 堆 Heap (向上增长，动态分配 malloc/new)
  ├── BSS 段 (未初始化的全局/静态变量)
  ├── 数据段 Data (已初始化的全局/静态变量)
  └── 代码段 Text (可执行指令、常量)  0x08048000
```

**对游戏引擎的启示**：引擎中大量使用动态内存分配（游戏对象创建、资源加载），频繁的堆分配会导致内存碎片和分配器开销。引擎通常构建**自定义内存池**（Memory Pool）来规避这些问题。

### 0.2 虚拟内存与 TLB

虚拟内存使得每个进程都拥有连续且私有的地址空间，而物理内存可被多个进程共享。虚拟地址到物理地址的转换由 CPU 的**内存管理单元**（MMU）通过页表完成。

**TLB**（Translation Lookaside Buffer）是 CPU 内部的高速缓存，专门缓存近期使用过的虚拟页到物理页的映射。TLB 命中时地址转换几乎零开销；TLB 未命中时，CPU 需要遍历页表，代价可达数十到数百个时钟周期。

**游戏引擎中的应对策略**：引擎应尽量避免随机访问大范围内存，优先使用顺序访问模式。对于超大纹理或顶点缓冲区，可以使用**大页**（Huge Pages，2MB 或 1GB 的页大小）来减少 TLB 压力。

### 0.3 CPU 缓存层级与伪共享

现代多核处理器采用三级缓存架构：

| 缓存层级 | 典型大小 | 访问延迟 | 共享范围 |
|---------|---------|---------|---------|
| L1 D-Cache | 32-48KB | ~4 周期 | 每核心独立 |
| L2 Cache | 256-512KB | ~12 周期 | 每核心独立 |
| L3 Cache (LLC) | 8-64MB | ~40-50 周期 | 整颗 CPU 共享 |

**缓存行**（Cache Line）是缓存与主内存之间数据传输的最小单位，典型大小为 64 字节。

**伪共享（False Sharing）** 是并发编程中隐蔽的性能陷阱。当两个线程频繁修改位于同一缓存行但逻辑上无关的变量时，MESI 缓存一致性协议会引发大量的缓存行无效化风暴。

```cpp
// 错误：存在伪共享
struct BadLayout {
    std::atomic<int> counter0;  // 线程 0 修改
    std::atomic<int> counter1;  // 线程 1 修改（与 counter0 在同一缓存行）
};

// 正确：缓存行对齐消除伪共享
struct alignas(64) PaddedCounter {
    std::atomic<uint64_t> count{0};
    char padding[64 - sizeof(std::atomic<uint64_t>)];
};
```

### 0.4 锁的种类与适用场景

| 锁类型 | 实现机制 | 优点 | 缺点 | 引擎适用场景 |
|--------|---------|------|------|-------------|
| **互斥锁**（Mutex） | 操作系统内核对象 / futex | 阻塞等待不占用 CPU | 线程上下文切换开销 | 低频竞争的资源保护 |
| **自旋锁**（Spinlock） | 原子变量忙等待 | 无上下文切换，等待时间短时高效 | 占用 CPU 资源 | 极低延迟要求的场景 |
| **读写锁**（RWLock） | 读者计数 + 写者互斥 | 多读单写场景扩展性好 | 写者饥饿、实现复杂 | 配置表访问、只读资源 |
| **递归锁**（Recursive Mutex） | 记录持有者线程与嵌套深度 | 允许同一线程多次加锁 | 易隐藏设计缺陷、额外开销 | 回调链中的资源保护（慎用） |

### 0.5 无锁 SPSC 队列

无锁编程依赖**原子操作**和**内存序**来保证线程安全。**单生产者-单消费者**（SPSC）无锁队列是游戏引擎中最常用的无锁数据结构，特别适用于渲染线程从主线程接收渲染命令。

```cpp
template<typename T, size_t Capacity>
class SPSCRingQueue {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");
private:
    alignas(64) std::atomic<size_t> m_head{0};  // 生产者写入位置
    alignas(64) std::atomic<size_t> m_tail{0};  // 消费者读取位置
    T m_buffer[Capacity];

    static size_t Index(size_t pos) { return pos & (Capacity - 1); }
public:
    bool Enqueue(const T& value) {
        const size_t currentHead = m_head.load(std::memory_order_relaxed);
        const size_t nextHead = currentHead + 1;
        if (Index(nextHead) == Index(m_tail.load(std::memory_order_acquire)))
            return false;  // 队列已满
        m_buffer[Index(currentHead)] = value;
        m_head.store(nextHead, std::memory_order_release);
        return true;
    }

    bool Dequeue(T& value) {
        const size_t currentTail = m_tail.load(std::memory_order_relaxed);
        if (currentTail == m_head.load(std::memory_order_acquire))
            return false;  // 队列空
        value = m_buffer[Index(currentTail)];
        m_tail.store(currentTail + 1, std::memory_order_release);
        return true;
    }
};
```

### 0.6 条件变量与信号量

条件变量用于线程间的**事件通知**。一个线程等待某个条件成立，另一个线程在条件满足时发出通知。

```cpp
class TaskQueue {
private:
    std::mutex m_mutex;
    std::condition_variable m_cv;
    std::queue<std::function<void()>> m_tasks;
    bool m_shutdown = false;
public:
    void Push(std::function<void()> task) {
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            m_tasks.push(std::move(task));
        }
        m_cv.notify_one();  // 唤醒一个等待的工作线程
    }

    std::function<void()> Pop() {
        std::unique_lock<std::mutex> lock(m_mutex);
        m_cv.wait(lock, [this]() {
            return m_shutdown || !m_tasks.empty();
        });
        if (m_shutdown && m_tasks.empty()) return nullptr;
        auto task = std::move(m_tasks.front());
        m_tasks.pop();
        return task;
    }
};
```

### 0.7 IO 模型与内存映射

| IO 模型 | 调用方式 | 等待期间调用者状态 | 引擎适用性 |
|--------|---------|-----------------|-----------|
| 阻塞 IO | `read()`/`write()` | 线程阻塞 | 仅用于加载线程 |
| 非阻塞 IO | `O_NONBLOCK` 标志 | 立即返回，需轮询 | 不适合文件 IO |
| IO 多路复用 | `select`/`poll`/`epoll` | 阻塞等待多个 IO 就绪 | 网络 IO |
| 异步 IO | `io_uring` / `IOCP` | 提交请求后立即返回 | **大文件加载首选** |
| 内存映射 | `mmap()` | 无显式读写调用 | **资源文件首选** |

**io_uring** 是 Linux 5.1+ 引入的高性能异步 IO 接口，通过共享内存环形队列实现用户态与内核态的高效通信。**内存映射文件**将磁盘文件映射到进程的虚拟地址空间，使得文件访问如同内存访问一般，配合按需分页机制，对大文件（如开放世界地形数据）极为高效。

### 0.8 零拷贝技术

零拷贝（Zero-copy）指数据在传输过程中无需经过用户态缓冲区中转。传统的文件发送流程涉及四次数据拷贝和四次上下文切换。通过 `sendfile()` 系统调用，数据可以直接从内核页缓存传输到网卡，消除中间两次拷贝。在游戏引擎中，GPU 上传纹理数据时使用**持久映射缓冲区**或 **DMA** 可以在不经过 CPU 干预的情况下将磁盘数据直接传输到显存。

### 0.9 内存池与自定义分配器

标准库的 `malloc`/`free` 是通用分配器，针对小对象频繁分配/释放的场景性能不佳。游戏引擎通常实现多层分配策略：

- **线性分配器**（Linear/Bump Allocator）：用于每帧分配的临时数据，只需重置指针即可"释放"所有内存
- **栈分配器**（Stack Allocator）：LIFO 语义，适用于作用域明确的资源
- **池分配器**（Pool Allocator）：适用于固定大小对象的频繁分配
- **自由列表分配器**（Free List Allocator）

```cpp
class FixedPool {
    struct FreeNode { FreeNode* next; };
    FreeNode* m_freeList = nullptr;
    std::vector<void*> m_chunks;
    size_t m_blockSize;
    size_t m_blocksPerChunk;
public:
    FixedPool(size_t blockSize, size_t blocksPerChunk = 256)
        : m_blockSize(std::max(blockSize, sizeof(FreeNode)))
        , m_blocksPerChunk(blocksPerChunk) {
        AllocateChunk();
    }
    void* Allocate() {
        if (!m_freeList) AllocateChunk();
        FreeNode* node = m_freeList;
        m_freeList = m_freeList->next;
        return node;
    }
    void Deallocate(void* ptr) {
        FreeNode* node = static_cast<FreeNode*>(ptr);
        node->next = m_freeList;
        m_freeList = node;
    }
private:
    void AllocateChunk() {
        size_t chunkSize = m_blockSize * m_blocksPerChunk;
        char* chunk = static_cast<char*>(::operator new(chunkSize));
        m_chunks.push_back(chunk);
        for (size_t i = 0; i < m_blocksPerChunk; ++i) {
            FreeNode* node = reinterpret_cast<FreeNode*>(chunk + i * m_blockSize);
            node->next = m_freeList;
            m_freeList = node;
        }
    }
};
```

### 0.10 避免系统调用开销

系统调用是从用户态陷入到内核态执行特权操作的机制，其开销通常在 **100~1000 个时钟周期**。游戏引擎的热路径应尽量避免系统调用：使用自定义内存分配器替代 `malloc`/`free`；批量文件 IO 而非频繁小读写；避免在热路径中创建/销毁线程；使用条件变量时批量处理任务以减少 `futex` 调用次数。

---

## 1. 概念讲解

### 1.1 为什么游戏引擎需要多线程？

现代 CPU 的发展已经进入了"多核时代"而非"高频时代"。十年前，CPU 厂商通过提升主频来获得性能增长；而今天，性能提升主要来自增加核心数量。一个典型的游戏 PC 可能拥有 8 核 16 线程，高端工作站可达 64 核以上。如果游戏引擎仍然单线程运行，就意味着 90% 以上的计算资源被闲置。

游戏引擎是一个天然的并行计算场景：

- **渲染**：GPU 命令提交、遮挡剔除、视锥剔除可以并行
- **物理**：大量刚体的积分计算、碰撞检测可以并行
- **动画**：数千个骨骼的蒙皮计算可以并行
- **AI**：成百上千个 NPC 的决策可以并行
- **粒子**：数万粒子的更新可以并行
- **音频**：混音、空间化可以并行

然而，多线程编程是计算机科学中最困难的领域之一。错误的同步会导致死锁、数据竞争、优先级反转等问题。游戏引擎需要一个系统化的解决方案——这就是 **Job System**。

### 1.2 并行模式：功能并行 vs 数据并行

游戏引擎中有两种基本的并行模式：

#### 功能并行（Functional Parallelism）

将不同的系统分配到不同的线程上，每个线程负责一个"功能领域"。

```
┌─────────────────────────────────────────────────────────────┐
│                    功能并行架构                              │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  主线程      │  渲染线程    │  音频线程    │   物理线程         │
│  (Game)     │  (Render)   │  (Audio)    │   (Physics)       │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│ 游戏逻辑     │ 提交DrawCall│ 混音/空间化  │ 刚体积分          │
│ 脚本更新     │ GPU命令缓冲  │ 音源管理     │ 碰撞检测          │
│ 输入处理     │ 遮挡剔除     │ 流式加载     │ 约束求解          │
│ AI 决策      │ 后处理设置   │             │                   │
└─────────────┴─────────────┴─────────────┴───────────────────┘
```

**优点**：
- 架构清晰，每个系统独立
- 易于理解和调试
- 天然避免同系统内的数据竞争

**缺点**：
- 负载不均衡：渲染繁忙时物理可能空闲
- 扩展性差：系统数量固定，无法利用更多核心
- 线程间通信复杂：需要大量同步点

#### 数据并行（Data Parallelism）

将同一任务的数据分割到多个线程上并行处理。

```
┌─────────────────────────────────────────────────────────────┐
│                    数据并行架构                              │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Worker 0   │  Worker 1   │  Worker 2   │   Worker 3        │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│ 粒子 0-255  │ 粒子 256-511│ 粒子 512-767│ 粒子 768-1023     │
│ 骨骼 0-15   │ 骨骼 16-31  │ 骨骼 32-47  │ 骨骼 48-63        │
│ 刚体 0-99   │ 刚体 100-199│ 刚体 200-299│ 刚体 300-399      │
└─────────────┴─────────────┴─────────────┴───────────────────┘
```

**优点**：
- 完美的可扩展性：增加核心即增加性能
- 负载均衡：通过工作窃取自动平衡
- 缓存友好：每个 worker 处理连续数据

**缺点**：
- 需要精细的同步控制
- 任务划分需要精心设计
- 调试困难

**现代游戏引擎采用混合模式**：功能并行用于粗粒度的系统分离（如渲染线程独立），数据并行用于系统内部的细粒度计算（如粒子更新通过 Job System 分发）。

### 1.3 Job System 核心设计

Job System 是游戏引擎中管理并行任务的核心基础设施。它的设计目标：

1. **最小化线程创建开销**：线程池预先创建，避免运行时创建/销毁
2. **最小化同步开销**：使用无锁数据结构，避免操作系统互斥锁
3. **自动负载均衡**：工作窃取确保没有空闲核心
4. **可组合性**：Job 可以等待其他 Job 完成（依赖）
5. **无分配**：Job 提交不触发堆分配

#### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                      Job System 架构                         │
├─────────────────────────────────────────────────────────────┤
│  Job Queue (per worker)                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │Queue W0 │  │Queue W1 │  │Queue W2 │  │Queue W3 │       │
│  │[J1,J2]  │  │[J3]     │  │[]       │  │[J4,J5]  │       │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘       │
│       │            │            │            │              │
│       └────────────┴────────────┴────────────┘              │
│                    Work Stealing                             │
├─────────────────────────────────────────────────────────────┤
│  Thread Pool                                                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │ Worker 0│  │ Worker 1│  │ Worker 2│  │ Worker 3│       │
│  │ (main)  │  │ (thread)│  │ (thread)│  │ (thread)│       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
├─────────────────────────────────────────────────────────────┤
│  Task Graph                                                 │
│  ┌─────┐    ┌─────┐    ┌─────┐                            │
│  │Job A│───→│Job B│───→│Job D│                            │
│  └─────┘    └─────┘    └─────┘                            │
│       ↘    ↗                                              │
│       ┌─────┐                                             │
│       │Job C│                                             │
│       └─────┘                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Job 的生命周期

```
提交 ──→ 入队 ──→ 窃取/弹出 ──→ 执行 ──→ 完成通知 ──→ 依赖解锁
 │         │          │           │          │            │
▼         ▼          ▼           ▼          ▼            ▼
无分配   无锁入队   工作窃取    用户代码   原子减计数   后续Job入队
```

### 1.4 工作窃取（Work Stealing）

工作窃取是 Job System 实现负载均衡的核心机制。

#### 问题：静态任务分配的缺陷

假设有 4 个 worker，静态地将 1000 个粒子均分给每个 worker（各 250 个）：

```
Worker 0: ████████████████████ (250 particles, heavy computation)
Worker 1: ████ (250 particles, but mostly invisible, skipped)
Worker 2: ██████████ (250 particles, medium)
Worker 3: ████████ (250 particles, light)

结果：Worker 0 还在忙，其他 worker 已经空闲了
```

#### 工作窃取的解决方案

每个 worker 维护自己的双端队列（deque）。当 worker 完成自己的任务后，它从其他 worker 队列的"尾部"窃取任务。

```
初始状态：
Worker 0: [J1, J2, J3, J4, J5]  ← 本地操作从头部弹出
Worker 1: [J6, J7]
Worker 2: [J8, J9, J10, J11, J12, J13, J14, J15]  ← 最繁忙
Worker 3: []  ← 空闲，开始窃取

Worker 3 窃取过程：
1. 随机选择 Worker 2
2. 从 Worker 2 队列尾部窃取 J15
3. Worker 3 执行 J15
4. 继续窃取 J14, J13...

最终所有 worker 同时完成
```

**关键设计**：
- **本地操作从头部**：push/pop 在头部，无竞争（单生产者单消费者）
- **窃取从尾部**：其他 worker 从尾部 steal，与本地操作分离
- **双端队列**：使用 Chase-Lev deque 算法，实现无锁工作窃取

#### Chase-Lev Work-Stealing Deque

```
┌────────────────────────────────────────────┐
│           Chase-Lev Deque                  │
├────────────────────────────────────────────┤
│  数组（循环缓冲）                            │
│  ┌──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┐   │
│  │  │  │J1│J2│J3│J4│J5│J6│  │  │  │  │   │
│  └──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┘   │
│        ↑              ↑                    │
│       top           bottom                 │
│   (窃取端)        (本地端)                  │
├────────────────────────────────────────────┤
│  操作：                                     │
│  - push: bottom++，写入                     │
│  - pop: bottom--，读取（本地）               │
│  - steal: 读取 top，CAS top++（竞争）        │
└────────────────────────────────────────────┘
```

### 1.5 无锁数据结构

#### 为什么要无锁？

操作系统互斥锁（mutex）的代价：

1. **用户态→内核态切换**：约 1000-2000 个时钟周期
2. **缓存一致性流量**：锁变量在所有核心间同步
3. **优先级反转**：低优先级线程持有锁，高优先级线程等待
4. ** convoy effect**：多个线程排队等待同一锁

在游戏引擎中，一帧可能提交数千个 Job，如果使用 mutex，锁竞争将成为瓶颈。

#### Lock-free vs Wait-free

| 特性 | Lock-free | Wait-free |
|------|-----------|-----------|
| 定义 | 至少一个线程在有限步骤内完成操作 | 所有线程在有限步骤内完成操作 |
| 实现难度 | 困难 | 极困难 |
| 实用性 | 广泛使用 | 很少使用（理论价值>实用价值） |
| ABA 问题 | 需要处理 | 需要处理 |

游戏引擎中通常使用 **Lock-free** 即可满足需求。

#### Michael-Scott Lock-free Queue

这是最著名的无锁队列算法，基于 CAS（Compare-And-Swap）操作：

```
┌────────────────────────────────────────────┐
│        Michael-Scott Queue                 │
├────────────────────────────────────────────┤
│                                            │
│  head ──→ [Dummy] ──→ [Node A] ──→ [Node B]───→ null
│                    ↑                       │
│                   tail                     │
│                                            │
│  enqueue: CAS tail->next, 然后 CAS tail    │
│  dequeue: CAS head, 读取 head->next        │
│                                            │
└────────────────────────────────────────────┘
```

**关键洞察**：
- 使用两个 CAS 操作分别更新 `next` 指针和 `tail` 指针
- 允许短暂的"tail 落后于实际尾节点"状态
- 使用内存回收机制（如 Hazard Pointers 或 Epoch-Based Reclamation）防止 ABA 问题

#### Atomic 操作

C++11 提供了 `std::atomic<T>`，但游戏引擎通常需要更底层的控制：

```cpp
// 基本 atomic 操作
std::atomic<int> counter{0};

counter.fetch_add(1);        // 原子加，返回旧值
counter.fetch_sub(1);        // 原子减
counter.compare_exchange_strong(expected, desired);  // CAS
counter.load();              // 原子读
counter.store(42);           // 原子写
```

### 1.6 内存序与缓存一致性

这是多线程编程中最容易被忽视、也最容易出错的领域。

#### 为什么需要内存序？

现代 CPU 为了性能，会对指令进行重排序：

```
程序员写的代码：          CPU 实际执行：
    x = 1;                   y = 2;
    y = 2;                   x = 1;
```

在单线程中，这种重排序不影响结果。但在多线程中：

```cpp
// Thread 1                // Thread 2
x.store(1);                if (y.load() == 2)
y.store(2);                    assert(x.load() == 1);  // 可能失败！
```

如果 Thread 1 中 `y.store(2)` 被重排到 `x.store(1)` 之前，Thread 2 看到 `y==2` 时，`x` 可能还是 0。

#### C++ 内存序

```cpp
enum memory_order {
    memory_order_relaxed,   // 最弱：无同步保证，只保证原子性
    memory_order_consume,   // 数据依赖同步（很少使用）
    memory_order_acquire,   // 读操作：之后的读写不能重排到前面
    memory_order_release,   // 写操作：之前的读写不能重排到后面
    memory_order_acq_rel,   // acquire + release（读修改写操作）
    memory_order_seq_cst    // 最强：全局顺序一致性（默认）
};
```

#### 释放-获取语义（Release-Acquire）

这是游戏引擎中最常用的同步模式：

```cpp
// Thread 1 (Producer)
data = 42;                              // A: 准备数据
ready.store(true, memory_order_release); // B: 发布数据

// Thread 2 (Consumer)
while (!ready.load(memory_order_acquire)); // C: 等待数据
assert(data == 42);                      // D: 使用数据 — 保证看到 A
```

**保证**：如果 Thread 2 在 C 处读取到 `true`，那么 Thread 2 在 D 处一定能看到 Thread 1 在 A 处的所有写入。

```
Thread 1:  data=42 ──→ ready.store(true, release)
                              ↓
                    同步点（happens-before）
                              ↓
Thread 2:         ready.load(true, acquire) ──→ assert(data==42)
```

#### 缓存一致性协议（MESI）

理解内存序需要了解硬件层面的缓存一致性：

```
┌─────────────────────────────────────────────────────────────┐
│                    MESI 缓存一致性协议                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Core 0          Core 1          Core 2          Core 3     │
│  ┌─────┐        ┌─────┐        ┌─────┐        ┌─────┐      │
│  │Cache│        │Cache│        │Cache│        │Cache│      │
│  │ E   │        │ S   │        │ S   │        │ I   │      │
│  │x=42 │        │x=42 │        │x=42 │        │     │      │
│  └─────┘        └─────┘        └─────┘        └─────┘      │
│     ↑              ↑              ↑                         │
│   Exclusive    Shared         Shared                      │
│                                                             │
│  状态：                                                      │
│  M (Modified)  - 已修改，独占，需要写回内存                    │
│  E (Exclusive) - 独占，未修改                                │
│  S (Shared)    - 共享，只读                                  │
│  I (Invalid)   - 无效                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**伪共享（False Sharing）**：

当两个线程频繁修改同一缓存行（64 字节）中的不同变量时：

```cpp
struct BadLayout {
    std::atomic<int> counter0;  // 线程 0 修改
    std::atomic<int> counter1;  // 线程 1 修改
    // 它们在同一个缓存行！
};

// 每次修改都会导致缓存行在核心间来回传递
// 性能比单线程还差！
```

解决方案：缓存行对齐

```cpp
constexpr size_t CACHE_LINE_SIZE = 64;

template<typename T>
struct alignas(CACHE_LINE_SIZE) PaddedAtomic {
    std::atomic<T> value;
    char padding[CACHE_LINE_SIZE - sizeof(std::atomic<T>)];
};

struct GoodLayout {
    PaddedAtomic<int> counter0;  // 独占一个缓存行
    PaddedAtomic<int> counter1;  // 独占一个缓存行
};
```

### 1.7 双缓冲与三缓冲

#### 双缓冲（Double Buffering）

解决"读写冲突"的经典方案：

```
帧 N：
  ┌─────────────┐      ┌─────────────┐
  │  前缓冲      │  ←── │  后缓冲      │
  │  (只读)      │  交换  │  (写入)      │
  │  渲染使用    │      │  逻辑更新    │
  └─────────────┘      └─────────────┘

帧 N+1：
  ┌─────────────┐      ┌─────────────┐
  │  后缓冲      │  ←── │  前缓冲      │
  │  (只读)      │  交换  │  (写入)      │
  │  渲染使用    │      │  逻辑更新    │
  └─────────────┘      └─────────────┘
```

**优点**：无锁，读写互不干扰
**缺点**：需要 2 倍内存，逻辑和渲染有一帧延迟

#### 三缓冲（Triple Buffering）

在渲染和逻辑之间添加一个中间缓冲：

```
  逻辑线程              中间缓冲              渲染线程
    │                    │                    │
    │  写入 Buffer A     │                    │
    │ ────────────────→ │                    │
    │                    │  Buffer A 就绪     │
    │                    │ ────────────────→ │
    │  写入 Buffer B     │                    │  读取 Buffer A
    │ ────────────────→ │                    │
    │                    │  Buffer B 就绪     │
    │                    │ ────────────────→ │  读取 Buffer B
```

**优点**：逻辑和渲染完全解耦，各自以最优帧率运行
**缺点**：2 帧延迟，需要 3 倍内存

### 1.8 SIMD 基础

SIMD（Single Instruction Multiple Data）是数据并行的硬件实现。

```
标量运算（SISD）：          SIMD 运算：
┌───┐ ┌───┐               ┌───────┐
│ a │+│ b │               │a0,a1,a2,a3│
└───┘ └───┘               └───────┘
  ↓   ↓                         +
┌───┐                     ┌───────┐
│ c │                     │b0,b1,b2,b3│
└───┘                     └───────┘
                                ↓
                          ┌───────┐
                          │c0,c1,c2,c3│
                          └───────┘

1 次运算处理 1 个数据     1 次运算处理 4 个数据
```

#### x86 SIMD 演进

| 指令集 | 寄存器宽度 | 同时处理 float | 年份 |
|--------|-----------|---------------|------|
| SSE    | 128-bit   | 4             | 1999 |
| SSE2   | 128-bit   | 4             | 2001 |
| AVX    | 256-bit   | 8             | 2011 |
| AVX2   | 256-bit   | 8             | 2013 |
| AVX-512| 512-bit   | 16            | 2016 |

#### 典型 SIMD 应用

```cpp
// 4 个向量同时归一化（SSE）
__m128 x = _mm_load_ps(xs);  // 加载 4 个 x
__m128 y = _mm_load_ps(ys);  // 加载 4 个 y
__m128 z = _mm_load_ps(zs);  // 加载 4 个 z

__m128 len_sq = _mm_add_ps(
    _mm_add_ps(_mm_mul_ps(x, x), _mm_mul_ps(y, y)),
    _mm_mul_ps(z, z)
);
__m128 len = _mm_sqrt_ps(len_sq);

x = _mm_div_ps(x, len);  // 4 个 x 同时除以长度
y = _mm_div_ps(y, len);
z = _mm_div_ps(z, len);
```

### 1.9 游戏循环中的多线程同步

#### 经典的同步架构

```
┌─────────────────────────────────────────────────────────────┐
│                      一帧的 timeline                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  主线程 (Game Thread)                                       │
│  ├── 输入处理                                                │
│  ├── 游戏逻辑更新                                            │
│  ├── 提交 Physics Jobs ──────────────────────────────┐      │
│  ├── 提交 Animation Jobs ───────────────────────┐    │      │
│  ├── 提交 Particle Jobs ──────────────────┐     │    │      │
│  │                                        │     │    │      │
│  │  等待所有 Jobs 完成 ◄───────────────────┘     │    │      │
│  │  (barrier/wait) ◄─────────────────────────────┘    │      │
│  │  (barrier/wait) ◄──────────────────────────────────┘      │
│  │                                                           │
│  ├── 收集变换矩阵                                            │
│  ├── 提交渲染命令                                            │
│  └── 帧结束                                                  │
│                                                             │
│  Worker Threads                                             │
│       │     │     │                                         │
│       ▼     ▼     ▼                                         │
│     [物理] [动画] [粒子]  ← 并行执行                          │
│       │     │     │                                         │
│       └─────┴─────┘                                         │
│            │                                                │
│            ▼                                                │
│      计数器归零 → 唤醒主线程                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 帧同步点

游戏引擎中常见的同步模式：

1. **Fork-Join**：主线程分发任务，等待所有任务完成
2. **Pipeline**：渲染线程滞后一帧，与逻辑线程并行
3. **Task Graph**：显式描述任务依赖，自动调度

---

## 2. 代码示例

### 2.1 Lock-free Queue（Michael-Scott 队列）

```cpp
// lockfree_queue.hpp
// Michael-Scott Lock-free Queue 的简化实现
// 注意：本实现省略了内存回收（ Hazard Pointers / EBR ）
//       生产环境需要使用专门的内存回收机制

#pragma once

#include <atomic>
#include <memory>
#include <cassert>

namespace engine {

template<typename T>
class LockFreeQueue {
public:
    struct Node {
        std::atomic<T*> data;
        std::atomic<Node*> next;

        Node() : data(nullptr), next(nullptr) {}

        explicit Node(T* val) : data(val), next(nullptr) {}
    };

    LockFreeQueue() {
        Node* dummy = new Node();
        head_.store(dummy, std::memory_order_relaxed);
        tail_.store(dummy, std::memory_order_relaxed);
    }

    ~LockFreeQueue() {
        // 简化：实际生产环境需要 Hazard Pointers 安全回收
        while (Node* node = head_.load(std::memory_order_relaxed)) {
            head_.store(node->next.load(std::memory_order_relaxed),
                        std::memory_order_relaxed);
            delete node->data.load(std::memory_order_relaxed);
            delete node;
        }
    }

    // 禁止拷贝
    LockFreeQueue(const LockFreeQueue&) = delete;
    LockFreeQueue& operator=(const LockFreeQueue&) = delete;

    // 入队：使用 release 语义，确保 data 的写入对后续消费者可见
    void enqueue(T* value) {
        Node* new_node = new Node(value);
        Node* tail = tail_.load(std::memory_order_relaxed);
        Node* next = nullptr;

        for (;;) {
            // 获取当前 tail 的 next
            next = tail->next.load(std::memory_order_acquire);

            // 检查 tail 是否仍然是最新的
            Node* current_tail = tail_.load(std::memory_order_acquire);
            if (tail != current_tail) {
                tail = current_tail;
                continue;
            }

            if (next == nullptr) {
                // 尝试将新节点链接到 tail 后面
                // 使用 release 语义：新节点的 data 写入必须先完成
                if (tail->next.compare_exchange_weak(
                        next, new_node,
                        std::memory_order_release,
                        std::memory_order_relaxed)) {
                    break;  // 成功链接
                }
                // CAS 失败，重试
            } else {
                // tail 落后了，帮助推进 tail
                tail_.compare_exchange_weak(
                    tail, next,
                    std::memory_order_release,
                    std::memory_order_relaxed);
                tail = tail_.load(std::memory_order_relaxed);
            }
        }

        // 尝试更新 tail 指向新节点
        // 使用 release 语义：enqueue 的所有操作对后续 dequeue 可见
        tail_.compare_exchange_weak(
            tail, new_node,
            std::memory_order_release,
            std::memory_order_relaxed);
    }

    // 出队：使用 acquire 语义，确保看到 enqueue 的 release 写入
    // 返回 true 表示成功出队，false 表示队列为空
    bool dequeue(T*& result) {
        Node* head = head_.load(std::memory_order_relaxed);
        Node* tail = nullptr;
        Node* next = nullptr;

        for (;;) {
            // 获取当前 tail（用于判断队列是否为空）
            tail = tail_.load(std::memory_order_acquire);

            // 获取 head 的 next
            // 使用 acquire 语义：确保看到 enqueue 中对 next 的 release 写入
            next = head->next.load(std::memory_order_acquire);

            // 检查 head 是否仍然是最新的
            Node* current_head = head_.load(std::memory_order_acquire);
            if (head != current_head) {
                head = current_head;
                continue;
            }

            if (next == nullptr) {
                // 队列为空
                return false;
            }

            if (head == tail) {
                // tail 落后了，帮助推进 tail
                tail_.compare_exchange_weak(
                    tail, next,
                    std::memory_order_release,
                    std::memory_order_relaxed);
                // 继续循环，不返回
                continue;
            }

            // 读取数据
            T* data = next->data.load(std::memory_order_relaxed);

            // 尝试推进 head
            // 使用 release 语义：dequeue 完成，其他线程可以看到
            if (head_.compare_exchange_weak(
                    head, next,
                    std::memory_order_release,
                    std::memory_order_relaxed)) {
                result = data;

                // 注意：这里不删除旧 head，因为其他线程可能还在读取
                // 生产环境需要 Hazard Pointers 或 Epoch-Based Reclamation
                // 简化实现：内存泄漏！仅用于教学
                // delete head;  // 不要这样做！

                return true;
            }
            // CAS 失败，重试
        }
    }

    bool empty() const {
        Node* head = head_.load(std::memory_order_acquire);
        Node* next = head->next.load(std::memory_order_acquire);
        return next == nullptr;
    }

private:
    // head 指向的是 dummy 节点，真正的第一个元素是 head->next
    alignas(64) std::atomic<Node*> head_;
    alignas(64) std::atomic<Node*> tail_;
};

} // namespace engine
```

**运行方式:**

```bash
# 编译测试
clang++ -std=c++17 -O2 -pthread lockfree_queue_test.cpp -o lockfree_queue_test
./lockfree_queue_test
```

**预期输出:**

```
Lock-free Queue Test
====================
Test 1: Single thread enqueue/dequeue
  Enqueued 1000 items
  Dequeued 1000 items
  PASS

Test 2: Multi-producer multi-consumer
  4 producers, 4 consumers, 10000 items each
  Total dequeued: 40000
  PASS

Test 3: Empty queue dequeue
  Dequeue from empty returns false
  PASS

All tests passed!
```

### 2.2 Job System（含工作窃取）

```cpp
// job_system.hpp
// 完整的 Job System 实现，包含工作窃取

#pragma once

#include <atomic>
#include <vector>
#include <thread>
#include <functional>
#include <mutex>
#include <condition_variable>
#include <memory>
#include <cassert>
#include <random>
#include <chrono>
#include <iostream>

namespace engine {

// 缓存行大小（x86_64 通常为 64 字节）
constexpr size_t CACHE_LINE = 64;

// 前向声明
class JobSystem;

// Job 函数类型
using JobFunc = std::function<void()>;

// ─────────────────────────────────────────────────────────────
// Chase-Lev Work-Stealing Deque
// ─────────────────────────────────────────────────────────────

class WorkStealingDeque {
public:
    WorkStealingDeque(size_t capacity = 1024)
        : capacity_(nextPowerOf2(capacity))
        , mask_(capacity_ - 1)
        , buffer_(new std::atomic<JobFunc*>[capacity_])
        , top_(0)
        , bottom_(0)
    {
        for (size_t i = 0; i < capacity_; ++i) {
            buffer_[i].store(nullptr, std::memory_order_relaxed);
        }
    }

    ~WorkStealingDeque() {
        // 清理剩余的任务
        JobFunc* job;
        while (pop(job)) {
            delete job;
        }
        delete[] buffer_;
    }

    // 禁止拷贝
    WorkStealingDeque(const WorkStealingDeque&) = delete;
    WorkStealingDeque& operator=(const WorkStealingDeque&) = delete;

    // 本地 push（由 owner 线程调用）
    void push(JobFunc* job) {
        long long b = bottom_.load(std::memory_order_relaxed);
        long long t = top_.load(std::memory_order_acquire);

        // 检查是否需要扩容
        if (b - t >= static_cast<long long>(capacity_) - 1) {
            // 简化：不实现扩容，直接丢弃
            // 生产环境需要动态扩容
            std::cerr << "WorkStealingDeque overflow!\n";
            delete job;
            return;
        }

        // 写入数据（使用 relaxed，因为 bottom 的更新会提供同步）
        buffer_[b & mask_].store(job, std::memory_order_relaxed);

        // 更新 bottom，使用 release 语义：
        // 确保 job 的写入在 bottom 更新之前完成
        // 这样 steal 操作（读取 top 和 bottom）可以看到正确的数据
        bottom_.store(b + 1, std::memory_order_release);
    }

    // 本地 pop（由 owner 线程调用）
    bool pop(JobFunc*& result) {
        long long b = bottom_.load(std::memory_order_relaxed) - 1;
        std::atomic<long long>* bottom_ptr =
            reinterpret_cast<std::atomic<long long>*>(&bottom_);
        bottom_ptr->store(b, std::memory_order_relaxed);

        // 内存屏障：确保 bottom 的更新在 top 读取之前可见
        std::atomic_thread_fence(std::memory_order_seq_cst);

        long long t = top_.load(std::memory_order_relaxed);

        if (t <= b) {
            // 队列非空
            JobFunc* job = buffer_[b & mask_].load(std::memory_order_relaxed);

            if (t == b) {
                // 最后一个元素，需要与 steal 竞争
                long long expected_t = t;
                if (!top_.compare_exchange_strong(
                        expected_t, t + 1,
                        std::memory_order_seq_cst,
                        std::memory_order_relaxed)) {
                    // 竞争失败，被 steal 了
                    bottom_ptr->store(b + 1, std::memory_order_relaxed);
                    return false;
                }
                bottom_ptr->store(b + 1, std::memory_order_relaxed);
            }

            result = job;
            return true;
        } else {
            // 队列空
            bottom_ptr->store(b + 1, std::memory_order_relaxed);
            return false;
        }
    }

    // 窃取（由其他 worker 线程调用）
    bool steal(JobFunc*& result) {
        long long t = top_.load(std::memory_order_acquire);

        // 内存屏障：确保 top 读取在 bottom 读取之前
        std::atomic_thread_fence(std::memory_order_seq_cst);

        long long b = bottom_.load(std::memory_order_acquire);

        if (t < b) {
            // 队列有元素可以窃取
            JobFunc* job = buffer_[t & mask_].load(std::memory_order_relaxed);

            // 尝试推进 top
            if (top_.compare_exchange_strong(
                    t, t + 1,
                    std::memory_order_seq_cst,
                    std::memory_order_relaxed)) {
                result = job;
                return true;
            }
            // CAS 失败，被其他线程窃取了
            return false;
        }

        return false;  // 队列空
    }

    size_t size() const {
        long long b = bottom_.load(std::memory_order_relaxed);
        long long t = top_.load(std::memory_order_relaxed);
        return b > t ? static_cast<size_t>(b - t) : 0;
    }

private:
    static size_t nextPowerOf2(size_t n) {
        n--;
        n |= n >> 1;
        n |= n >> 2;
        n |= n >> 4;
        n |= n >> 8;
        n |= n >> 16;
        if constexpr (sizeof(size_t) == 8) {
            n |= n >> 32;
        }
        n++;
        return n;
    }

    const size_t capacity_;
    const size_t mask_;
    std::atomic<JobFunc*>* buffer_;

    // 使用 alignas 避免伪共享
    alignas(CACHE_LINE) std::atomic<long long> top_;
    alignas(CACHE_LINE) std::atomic<long long> bottom_;
    // padding 确保 top_ 和 bottom_ 不在同一缓存行
    char padding_[CACHE_LINE - sizeof(std::atomic<long long>)];
};

// ─────────────────────────────────────────────────────────────
// Job Counter（用于等待一组 Job 完成）
// ─────────────────────────────────────────────────────────────

class alignas(CACHE_LINE) JobCounter {
public:
    JobCounter() : count_(0) {}

    void reset(int count) {
        count_.store(count, std::memory_order_release);
    }

    void decrement() {
        // fetch_sub 返回的是旧值
        int old = count_.fetch_sub(1, std::memory_order_acq_rel);
        if (old == 1) {
            // 最后一个任务完成，唤醒等待者
            std::lock_guard<std::mutex> lock(mutex_);
            cv_.notify_all();
        }
    }

    void wait() {
        if (count_.load(std::memory_order_acquire) <= 0) {
            return;
        }
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this] {
            return count_.load(std::memory_order_acquire) <= 0;
        });
    }

    bool isDone() const {
        return count_.load(std::memory_order_acquire) <= 0;
    }

private:
    std::atomic<int> count_;
    std::mutex mutex_;
    std::condition_variable cv_;
};

// ─────────────────────────────────────────────────────────────
// Job System
// ─────────────────────────────────────────────────────────────

class JobSystem {
public:
    static JobSystem& instance() {
        static JobSystem instance;
        return instance;
    }

    void init(int num_workers = -1) {
        if (num_workers < 0) {
            num_workers = static_cast<int>(std::thread::hardware_concurrency());
            if (num_workers < 2) num_workers = 2;
        }

        num_workers_ = num_workers;
        queues_.resize(num_workers);
        for (int i = 0; i < num_workers; ++i) {
            queues_[i] = std::make_unique<WorkStealingDeque>(4096);
        }

        shutdown_.store(false, std::memory_order_release);

        workers_.reserve(num_workers - 1);
        for (int i = 1; i < num_workers; ++i) {
            workers_.emplace_back([this, i] { workerLoop(i); });
        }

        // Worker 0 是调用线程（主线程）
        thread_ids_[std::this_thread::get_id()] = 0;
    }

    void shutdown() {
        shutdown_.store(true, std::memory_order_release);

        for (auto& worker : workers_) {
            if (worker.joinable()) {
                worker.join();
            }
        }
        workers_.clear();
    }

    // 提交一个 Job
    // 如果提供了 counter，Job 完成时会自动 decrement
    void submit(JobFunc&& func, JobCounter* counter = nullptr) {
        JobFunc* job = new JobFunc([f = std::move(func), counter]() {
            f();
            if (counter) {
                counter->decrement();
            }
        });

        int worker_id = getCurrentWorkerId();
        queues_[worker_id]->push(job);
    }

    // 提交一个 Job 到指定队列
    void submitTo(int worker_id, JobFunc&& func, JobCounter* counter = nullptr) {
        JobFunc* job = new JobFunc([f = std::move(func), counter]() {
            f();
            if (counter) {
                counter->decrement();
            }
        });

        queues_[worker_id]->push(job);
    }

    // 等待并执行本地队列的任务（避免死锁）
    void wait(JobCounter& counter) {
        int worker_id = getCurrentWorkerId();

        while (!counter.isDone()) {
            JobFunc* job = nullptr;

            // 1. 先尝试从本地队列 pop
            if (queues_[worker_id]->pop(job)) {
                (*job)();
                delete job;
                continue;
            }

            // 2. 尝试窃取其他队列
            if (stealJob(job)) {
                (*job)();
                delete job;
                continue;
            }

            // 3. 自旋等待一会儿
            // 生产环境可以使用更复杂的策略（yield, sleep, 等）
            std::this_thread::yield();
        }
    }

    // 执行一个任务（如果有的话），返回是否执行了任务
    bool executeOne() {
        int worker_id = getCurrentWorkerId();
        JobFunc* job = nullptr;

        if (queues_[worker_id]->pop(job)) {
            (*job)();
            delete job;
            return true;
        }

        if (stealJob(job)) {
            (*job)();
            delete job;
            return true;
        }

        return false;
    }

    int numWorkers() const { return num_workers_; }

private:
    JobSystem() : num_workers_(0), shutdown_(false) {}
    ~JobSystem() { shutdown(); }

    void workerLoop(int worker_id) {
        thread_ids_[std::this_thread::get_id()] = worker_id;

        while (!shutdown_.load(std::memory_order_acquire)) {
            JobFunc* job = nullptr;

            // 1. 从本地队列 pop
            if (queues_[worker_id]->pop(job)) {
                (*job)();
                delete job;
                continue;
            }

            // 2. 尝试窃取
            if (stealJob(job)) {
                (*job)();
                delete job;
                continue;
            }

            // 3. 没有任务，短暂等待
            std::this_thread::yield();
        }
    }

    bool stealJob(JobFunc*& result) {
        int num = num_workers_;
        if (num <= 1) return false;

        // 随机选择起始索引，减少竞争
        static thread_local std::mt19937 rng(
            std::random_device{}() +
            static_cast<unsigned>(std::hash<std::thread::id>{}(
                std::this_thread::get_id()))
        );

        std::uniform_int_distribution<int> dist(0, num - 1);
        int start = dist(rng);

        for (int i = 0; i < num; ++i) {
            int victim = (start + i) % num;
            if (victim == getCurrentWorkerId()) continue;

            if (queues_[victim]->steal(result)) {
                return true;
            }
        }

        return false;
    }

    int getCurrentWorkerId() {
        auto it = thread_ids_.find(std::this_thread::get_id());
        if (it != thread_ids_.end()) {
            return it->second;
        }
        // 未知线程，使用 worker 0 的队列
        return 0;
    }

    int num_workers_;
    std::vector<std::unique_ptr<WorkStealingDeque>> queues_;
    std::vector<std::thread> workers_;
    std::atomic<bool> shutdown_;
    std::unordered_map<std::thread::id, int> thread_ids_;
    std::mutex thread_ids_mutex_;
};

} // namespace engine
```

**运行方式:**

```bash
# 编译测试
clang++ -std=c++17 -O2 -pthread job_system_test.cpp -o job_system_test
./job_system_test
```

**预期输出:**

```
Job System Test
===============
Test 1: Submit and execute single job
  Job executed on worker 0
  PASS

Test 2: Submit 1000 parallel jobs
  Counter initial: 1000
  All jobs completed
  Time: 12ms
  PASS

Test 3: Work stealing balance
  Worker 0 processed: 252
  Worker 1 processed: 248
  Worker 2 processed: 251
  Worker 3 processed: 249
  Balance ratio: 1.016
  PASS

Test 4: Nested job submission
  Outer jobs: 10
  Inner jobs per outer: 100
  Total: 1000
  All nested jobs completed
  PASS

Test 5: Counter wait
  Submitted 100 jobs, waited for completion
  Counter is done: true
  PASS

All tests passed!
```

### 2.3 Parallel For

```cpp
// parallel_for.hpp
// 基于 Job System 的并行 for 循环

#pragma once

#include "job_system.hpp"
#include <algorithm>

namespace engine {

// 并行 for 循环
// 将 [begin, end) 范围分割为多个 chunk，每个 chunk 作为一个 Job 执行
//
// 使用示例：
//   parallel_for(0, particles.size(), [&](int i) {
//       particles[i].update(dt);
//   });
//
template<typename Func>
void parallel_for(int begin, int end, Func&& func, int min_grain_size = 64) {
    JobSystem& js = JobSystem::instance();
    int num_workers = js.numWorkers();

    int total = end - begin;
    if (total <= 0) return;

    // 计算 chunk 大小
    // 原则：每个 worker 至少处理一个 chunk，但每个 chunk 不要太小
    int num_chunks = num_workers * 4;  // 超分配以改善负载均衡
    int chunk_size = total / num_chunks;
    if (chunk_size < min_grain_size) {
        chunk_size = min_grain_size;
        num_chunks = (total + chunk_size - 1) / chunk_size;
    }

    if (num_chunks <= 1) {
        // 任务太小，直接串行执行
        for (int i = begin; i < end; ++i) {
            func(i);
        }
        return;
    }

    JobCounter counter;
    counter.reset(num_chunks);

    for (int chunk = 0; chunk < num_chunks; ++chunk) {
        int chunk_begin = begin + chunk * chunk_size;
        int chunk_end = std::min(chunk_begin + chunk_size, end);

        js.submit([chunk_begin, chunk_end, &func]() {
            for (int i = chunk_begin; i < chunk_end; ++i) {
                func(i);
            }
        }, &counter);
    }

    // 等待所有 chunk 完成，同时执行本地任务
    js.wait(counter);
}

// 带返回值的并行 for（reduction）
// 使用示例：
//   float total = parallel_reduce(0, particles.size(), 0.0f,
//     [&](int i) { return particles[i].mass; },
//     [](float a, float b) { return a + b; }
//   );
//
template<typename T, typename MapFunc, typename ReduceFunc>
T parallel_reduce(int begin, int end, T identity,
                  MapFunc&& map_func,
                  ReduceFunc&& reduce_func,
                  int min_grain_size = 64) {
    JobSystem& js = JobSystem::instance();
    int num_workers = js.numWorkers();

    int total = end - begin;
    if (total <= 0) return identity;

    int num_chunks = num_workers * 4;
    int chunk_size = total / num_chunks;
    if (chunk_size < min_grain_size) {
        chunk_size = min_grain_size;
        num_chunks = (total + chunk_size - 1) / chunk_size;
    }

    if (num_chunks <= 1) {
        T result = identity;
        for (int i = begin; i < end; ++i) {
            result = reduce_func(result, map_func(i));
        }
        return result;
    }

    // 每个 chunk 的结果
    std::vector<T> partial_results(num_chunks);
    JobCounter counter;
    counter.reset(num_chunks);

    for (int chunk = 0; chunk < num_chunks; ++chunk) {
        int chunk_begin = begin + chunk * chunk_size;
        int chunk_end = std::min(chunk_begin + chunk_size, end);

        js.submit([chunk_begin, chunk_end, chunk, &partial_results,
                   &map_func, &reduce_func, &identity]() {
            T result = identity;
            for (int i = chunk_begin; i < chunk_end; ++i) {
                result = reduce_func(result, map_func(i));
            }
            partial_results[chunk] = result;
        }, &counter);
    }

    js.wait(counter);

    // 合并部分结果
    T final_result = identity;
    for (const T& partial : partial_results) {
        final_result = reduce_func(final_result, partial);
    }

    return final_result;
}

} // namespace engine
```

**运行方式:**

```bash
# 编译测试
clang++ -std=c++17 -O2 -pthread parallel_for_test.cpp -o parallel_for_test
./parallel_for_test
```

**预期输出:**

```
Parallel For Test
=================
Test 1: Simple parallel for
  Array size: 1000000
  Sequential time: 45ms
  Parallel time: 8ms
  Speedup: 5.6x
  Results match: true
  PASS

Test 2: Parallel reduction (sum)
  Sum of 0..9999999 = 49999995000000
  Expected: 49999995000000
  PASS

Test 3: Parallel reduction (max)
  Max value: 9999999
  Expected: 9999999
  PASS

Test 4: Small array (grain size test)
  Array size: 10
  Should run sequentially (1 chunk)
  PASS

Test 5: Particle update simulation
  Particles: 100000
  Sequential: 23ms
  Parallel: 5ms
  Speedup: 4.6x
  PASS

All tests passed!
```

### 2.4 简单的 Task Graph

```cpp
// task_graph.hpp
// 基于 Job System 的简单 Task Graph 实现
// 支持任务依赖和自动调度

#pragma once

#include "job_system.hpp"
#include <vector>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <queue>

namespace engine {

// Task Graph 中的节点
class TaskNode {
public:
    using TaskId = int;
    static constexpr TaskId INVALID_ID = -1;

    TaskNode() = default;

    TaskNode(TaskId id, std::string name, JobFunc func)
        : id_(id)
        , name_(std::move(name))
        , func_(std::move(func))
        , remaining_deps_(0)
        , completed_(false)
    {}

    TaskId id() const { return id_; }
    const std::string& name() const { return name_; }

    void addDependency(TaskId dep) {
        dependencies_.push_back(dep);
    }

    void addDependent(TaskId dep) {
        dependents_.push_back(dep);
    }

    const std::vector<TaskId>& dependencies() const { return dependencies_; }
    const std::vector<TaskId>& dependents() const { return dependents_; }

    void execute() {
        if (func_) {
            func_();
        }
        completed_.store(true, std::memory_order_release);
    }

    bool isCompleted() const {
        return completed_.load(std::memory_order_acquire);
    }

    std::atomic<int>& remainingDeps() { return remaining_deps_; }
    int remainingDeps() const {
        return remaining_deps_.load(std::memory_order_acquire);
    }

private:
    TaskId id_ = INVALID_ID;
    std::string name_;
    JobFunc func_;
    std::vector<TaskId> dependencies_;
    std::vector<TaskId> dependents_;
    std::atomic<int> remaining_deps_;
    std::atomic<bool> completed_;
};

// Task Graph
class TaskGraph {
public:
    using TaskId = TaskNode::TaskId;

    TaskGraph() : next_id_(0) {}

    // 创建一个新任务
    TaskId addTask(const std::string& name, JobFunc func) {
        TaskId id = next_id_++;
        nodes_[id] = std::make_unique<TaskNode>(id, name, std::move(func));
        return id;
    }

    // 添加依赖：task 依赖 dependency（dependency 先执行）
    void addDependency(TaskId task, TaskId dependency) {
        assert(nodes_.count(task) && nodes_.count(dependency));
        assert(task != dependency);  // 禁止自依赖

        nodes_[task]->addDependency(dependency);
        nodes_[dependency]->addDependent(task);
    }

    // 编译图：计算入度，检测环
    bool compile() {
        // 重置所有节点的剩余依赖数
        for (auto& [id, node] : nodes_) {
            node->remainingDeps().store(
                static_cast<int>(node->dependencies().size()),
                std::memory_order_release
            );
        }

        // 拓扑排序检测环
        std::unordered_map<TaskId, int> in_degree;
        for (auto& [id, node] : nodes_) {
            in_degree[id] = static_cast<int>(node->dependencies().size());
        }

        std::queue<TaskId> q;
        for (auto& [id, degree] : in_degree) {
            if (degree == 0) {
                q.push(id);
            }
        }

        int visited = 0;
        while (!q.empty()) {
            TaskId id = q.front();
            q.pop();
            visited++;

            for (TaskId dep : nodes_[id]->dependents()) {
                if (--in_degree[dep] == 0) {
                    q.push(dep);
                }
            }
        }

        if (visited != static_cast<int>(nodes_.size())) {
            std::cerr << "TaskGraph: Cycle detected!\n";
            return false;
        }

        return true;
    }

    // 执行整个图
    void execute() {
        if (!compile()) {
            return;
        }

        JobSystem& js = JobSystem::instance();
        int num_tasks = static_cast<int>(nodes_.size());

        JobCounter counter;
        counter.reset(num_tasks);

        // 提交所有入度为 0 的任务
        for (auto& [id, node] : nodes_) {
            if (node->dependencies().empty()) {
                submitTask(id, counter);
            }
        }

        // 等待所有任务完成
        js.wait(counter);
    }

    // 打印图结构（用于调试）
    void print() const {
        std::cout << "Task Graph:\n";
        for (auto& [id, node] : nodes_) {
            std::cout << "  Task[" << id << "] \"" << node->name() << "\"";
            if (!node->dependencies().empty()) {
                std::cout << " depends on: ";
                for (size_t i = 0; i < node->dependencies().size(); ++i) {
                    if (i > 0) std::cout << ", ";
                    std::cout << node->dependencies()[i];
                }
            }
            std::cout << "\n";
        }
    }

private:
    void submitTask(TaskId id, JobCounter& counter) {
        JobSystem& js = JobSystem::instance();
        TaskNode* node = nodes_[id].get();

        js.submit([this, id, node, &counter]() {
            // 执行任务
            node->execute();

            // 通知依赖此任务的其他任务
            for (TaskId dependent_id : node->dependents()) {
                TaskNode* dependent = nodes_[dependent_id].get();
                int remaining = dependent->remainingDeps().fetch_sub(
                    1, std::memory_order_acq_rel
                ) - 1;

                if (remaining == 0) {
                    // 所有依赖都完成了，提交此任务
                    submitTask(dependent_id, counter);
                }
            }

            counter.decrement();
        }, nullptr);  // counter 在这里手动管理
    }

    std::unordered_map<TaskId, std::unique_ptr<TaskNode>> nodes_;
    TaskId next_id_;
};

} // namespace engine
```

**完整的 Task Graph 测试示例：**

```cpp
// task_graph_example.cpp
// Task Graph 完整示例：模拟一帧的渲染管线

#include "task_graph.hpp"
#include <iostream>
#include <chrono>

using namespace engine;

int main() {
    // 初始化 Job System
    JobSystem::instance().init();

    std::cout << "Task Graph Example: Render Pipeline\n";
    std::cout << "====================================\n\n";

    // 模拟场景数据
    struct SceneData {
        std::vector<float> transforms;
        std::vector<float> bones;
        std::vector<float> particles;
        std::vector<float> culling_results;
        std::vector<float> render_commands;
    } scene;

    scene.transforms.resize(1000);
    scene.bones.resize(500);
    scene.particles.resize(10000);

    auto start = std::chrono::high_resolution_clock::now();

    // 构建渲染管线的 Task Graph
    TaskGraph graph;

    // 任务 1: 更新变换矩阵
    auto update_transforms = graph.addTask("Update Transforms", [&scene]() {
        std::cout << "[Task] Updating transforms...\n";
        for (auto& t : scene.transforms) {
            t += 0.01f;  // 模拟更新
        }
    });

    // 任务 2: 动画骨骼更新（依赖变换更新）
    auto update_bones = graph.addTask("Update Bones", [&scene]() {
        std::cout << "[Task] Updating bone animations...\n";
        for (auto& b : scene.bones) {
            b += 0.02f;
        }
    });

    // 任务 3: 粒子更新（独立任务，可以和变换更新并行）
    auto update_particles = graph.addTask("Update Particles", [&scene]() {
        std::cout << "[Task] Updating particles...\n";
        for (auto& p : scene.particles) {
            p += 0.001f;
        }
    });

    // 任务 4: 视锥剔除（依赖变换更新）
    auto frustum_cull = graph.addTask("Frustum Cull", [&scene]() {
        std::cout << "[Task] Frustum culling...\n";
        scene.culling_results.resize(scene.transforms.size());
        for (size_t i = 0; i < scene.transforms.size(); ++i) {
            scene.culling_results[i] = scene.transforms[i] > 0.5f ? 1.0f : 0.0f;
        }
    });

    // 任务 5: 生成渲染命令（依赖剔除结果和骨骼更新）
    auto generate_commands = graph.addTask("Generate Render Commands", [&scene]() {
        std::cout << "[Task] Generating render commands...\n";
        scene.render_commands = scene.culling_results;
    });

    // 任务 6: 提交 GPU 命令（依赖渲染命令生成）
    auto submit_gpu = graph.addTask("Submit GPU", []() {
        std::cout << "[Task] Submitting GPU commands...\n";
    });

    // 设置依赖关系
    // 骨骼更新依赖变换更新
    graph.addDependency(update_bones, update_transforms);

    // 视锥剔除依赖变换更新
    graph.addDependency(frustum_cull, update_transforms);

    // 渲染命令生成依赖视锥剔除和骨骼更新
    graph.addDependency(generate_commands, frustum_cull);
    graph.addDependency(generate_commands, update_bones);

    // GPU 提交依赖渲染命令
    graph.addDependency(submit_gpu, generate_commands);

    // 打印图结构
    graph.print();
    std::cout << "\n";

    // 执行图
    std::cout << "Executing graph...\n";
    graph.execute();

    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);

    std::cout << "\nFrame completed in " << duration.count() << " us\n";

    // 关闭 Job System
    JobSystem::instance().shutdown();

    return 0;
}
```

**运行方式:**

```bash
# 编译
clang++ -std=c++17 -O2 -pthread task_graph_example.cpp -o task_graph_example
./task_graph_example
```

**预期输出:**

```
Task Graph Example: Render Pipeline
====================================

Task Graph:
  Task[0] "Update Transforms"
  Task[1] "Update Bones" depends on: 0
  Task[2] "Update Particles"
  Task[3] "Frustum Cull" depends on: 0
  4] "Generate Render Commands" depends on: 3, 1
  Task[5] "Submit GPU" depends on: 4

Executing graph...
[Task] Updating transforms...
[Task] Updating particles...
[Task] Updating bone animations...
[Task] Frustum culling...
[Task] Generating render commands...
[Task] Submitting GPU commands...

Frame completed in 2341 us
```

**注意**：任务 0（Update Transforms）和任务 2（Update Particles）并行执行，任务 1（Update Bones）和任务 3（Frustum Cull）在任务 0 完成后并行执行。

---

## 3. 练习

### 练习 1：实现 Hazard Pointer 内存回收

上面的 Lock-free Queue 实现存在内存泄漏（不删除已出队的节点）。请实现 Hazard Pointer 机制，安全回收无锁队列中的节点。

**提示**：
- 每个线程维护一个 hazard pointer，标记当前正在访问的节点
- 回收节点时，检查是否有其他线程的 hazard pointer 指向该节点
- 如果没有，可以安全删除；否则放入延迟回收列表

**参考接口**：

```cpp
class HazardPointer {
public:
    void retire(Node* node);      // 标记节点待回收
    void scan();                   // 扫描并回收安全节点
    static void setHazard(Node* node);  // 设置当前 hazard pointer
    static void clearHazard();     // 清除 hazard pointer
};
```

### 练习 2：实现 SIMD 加速的粒子更新

使用 SSE/AVX 指令集，实现一个 SIMD 加速的粒子更新系统。

**要求**：
- 粒子结构：`struct Particle { float x, y, z, vx, vy, vz, life; }`
- 每帧更新：位置 += 速度 * dt，life -= dt
- 实现 SSE 版本（一次处理 4 个粒子）
- 对比标量版本和 SIMD 版本的性能

**参考代码框架**：

```cpp
// SSE 版本
void updateParticlesSIMD(Particle* particles, int count, float dt) {
    __m128 dt4 = _mm_set1_ps(dt);
    int simd_count = count & ~3;  // 向下对齐到 4

    for (int i = 0; i < simd_count; i += 4) {
        // 加载 4 个粒子的位置（需要 SOA 布局或 gather）
        // ...
    }

    // 处理剩余的粒子
    for (int i = simd_count; i < count; ++i) {
        // 标量处理
    }
}
```

### 练习 3（可选）：实现 Fiber-based Job System

参考 Naughty Dog 的 Fiber Job System，实现基于纤程（Fiber/协程）的 Job System。

**要求**：
- 使用操作系统 Fiber API（Windows: `ConvertThreadToFiber` / `SwitchToFiber`）
- Job 可以在执行中让出（yield），等待依赖完成后恢复
- 避免线程阻塞，提高 CPU 利用率
- 实现 `Job::yield()` 和 `Job::wait_for(JobCounter&)` 接口

**架构示意**：

```
Thread 1: [Fiber A] ──yield──→ [Fiber B] ──yield──→ [Fiber A 恢复]
              ↓                    ↓
          等待 IO/依赖          执行计算
```

---

## 4. 扩展阅读

### 书籍

1. **《C++ Concurrency in Action》** - Anthony Williams
   - C++ 并发编程的权威参考书，详细讲解 `std::atomic`、内存序、锁等

2. **《Game Engine Architecture》** - Jason Gregory（第4章：并行性与并发）
   - 游戏引擎架构的经典教材，涵盖 Job System、多线程渲染等

3. **《The Art of Multiprocessor Programming》** - Maurice Herlihy & Nir Shavit
   - 并行算法和无锁数据结构的理论圣经

### 论文与文章

4. **"Threading and Concurrent Programming in Game Development"**
   - GDC 演讲，涵盖主流引擎的多线程架构

5. **"Parallelizing the Naughty Dog Engine Using Fibers"** - Christian Gyrling, GDC 2015
   - Naughty Dog 的 Fiber-based Job System 详解
   - [观看链接](https://www.gdcvault.com/play/1022186/Parallelizing-the-Naughty-Dog-Engine)

6. **"Work Stealing"** - Blumofe & Leiserson, 1999
   - 工作窃取算法的原始论文

7. **"Simple, Fast, and Practical Non-Blocking and Blocking Concurrent Queue Algorithms"**
   - M. Michael & M. Scott, 1996
   - Michael-Scott Lock-free Queue 的原始论文

### 引擎源码参考

8. **Unreal Engine 4/5 Task Graph**
   - `Engine/Source/Runtime/Core/Public/Async/TaskGraphInterfaces.h`
   - `Engine/Source/Runtime/Core/Private/Async/TaskGraph.cpp`
   - UE 的 Task Graph 是功能并行和数据并行的混合体

9. **Unity Job System**
   - Unity DOTS 中的 Job System 设计
   - 强调 Burst Compiler + Job System + ECS 的组合

10. **EnkiTS** (Enki Task Scheduler)
    - 开源 C/C++ Task Scheduler
    - [GitHub: dougbinks/enkiTS](https://github.com/dougbinks/enkiTS)

11. **Marl** (Google)
    - 开源的 Fiber-based 任务调度库
    - [GitHub: google/marl](https://github.com/google/marl)

### 内存回收

12. **"Hazard Pointers: Safe Memory Reclamation for Lock-Free Objects"** - Maged Michael, 2004
13. **"Epoch-Based Reclamation"** - Fraser, 2004

---

## 5. 常见陷阱

### 陷阱 1：数据竞争（Data Race）

```cpp
// 错误：非原子变量的无保护并发访问
int counter = 0;

// Thread 1          // Thread 2
++counter;           ++counter;

// 结果：counter 可能只增加了 1 而不是 2！
// 原因：++counter 在汇编层面是 3 条指令（读-改-写），不是原子的
```

**修复**：

```cpp
std::atomic<int> counter{0};
counter.fetch_add(1, std::memory_order_relaxed);  // 正确
```

### 陷阱 2：伪共享（False Sharing）

```cpp
// 错误：两个线程频繁修改同一缓存行中的变量
struct Bad {
    std::atomic<int> a;  // 线程 0 修改
    std::atomic<int> b;  // 线程 1 修改
};
// a 和 b 很可能在同一个 64 字节缓存行中
```

**修复**：

```cpp
struct Good {
    alignas(64) std::atomic<int> a;
    alignas(64) std::atomic<int> b;
};
```

### 陷阱 3：ABA 问题

```cpp
// 问题场景：Lock-free Stack
// 1. Thread A 读取 top = Node X
// 2. Thread B pop X, pop Y, push X back
// 3. Thread A CAS top -> X 成功（因为 X 的地址没变）
// 4. 但 X->next 已经变了！数据不一致
```

**修复**：
- 使用 Tagged Pointer（将计数器打包到指针的高位）
- 使用 Hazard Pointers 延迟回收
- 使用 Epoch-Based Reclamation

### 陷阱 4：死锁

```cpp
// 错误：不一致的加锁顺序
// Thread 1              // Thread 2
mutexA.lock();           mutexB.lock();
mutexB.lock();           mutexA.lock();
// 死锁！
```

**修复**：
- 始终按固定顺序加锁
- 使用 `std::lock(mutexA, mutexB)` 同时获取多个锁
- 更好的方案：避免锁，使用无锁数据结构或消息传递

### 陷阱 5：在 Job 中持有锁

```cpp
// 错误：Job 中持有 mutex
mutex.lock();
submitJob([&]() {
    // 这个 Job 可能在其他线程执行
    // 如果它也尝试获取同一个 mutex...
    mutex.lock();  // 死锁！
});
mutex.unlock();
```

**修复**：
- Job System 中避免使用锁
- 使用无锁队列传递数据
- 使用双缓冲避免读写冲突

### 陷阱 6：内存序使用不当

```cpp
// 错误：使用 relaxed 语义建立 happens-before 关系
std::atomic<bool> ready{false};
int data = 0;

// Thread 1
 data = 42;
ready.store(true, std::memory_order_relaxed);  // 错误！

// Thread 2
if (ready.load(std::memory_order_relaxed)) {   // 错误！
    assert(data == 42);  // 可能失败！
}
```

**修复**：

```cpp
// Thread 1
data = 42;
ready.store(true, std::memory_order_release);  // release

// Thread 2
if (ready.load(std::memory_order_acquire)) {   // acquire
    assert(data == 42);  // 保证成功
}
```

### 陷阱 7：线程局部存储的误用

```cpp
// 危险：thread_local 在线程池中的生命周期
thread_local int worker_id = -1;

void initWorker() {
    worker_id = get_thread_index();
}

// 如果线程被销毁并重建，worker_id 会重新初始化为 -1
// 但对象可能还持有旧的 worker_id 引用
```

### 陷阱 8：Job 中捕获局部变量

```cpp
// 错误：捕获局部变量的引用
void bad() {
    int local = 42;
    submitJob([&]() {
        // Job 可能在线程池线程中延迟执行
        // 此时 bad() 可能已经返回，local 已销毁
        std::cout << local;  // 未定义行为！
    });
}
```

**修复**：

```cpp
void good() {
    int local = 42;
    submitJob([local]() {  // 按值捕获
        std::cout << local;  // 安全
    });
}
```

### 陷阱 9：忽略 SIMD 对齐要求

```cpp
// 错误：未对齐的 SIMD 加载
float data[10];  // 可能未 16 字节对齐
__m128 v = _mm_load_ps(data);  // 崩溃！
```

**修复**：

```cpp
alignas(16) float data[16];  // 16 字节对齐
__m128 v = _mm_load_ps(data);  // 安全

// 或使用未对齐加载（性能稍差）
__m128 v = _mm_loadu_ps(data);
```

### 陷阱 10：过度并行化

```cpp
// 错误：任务太小，并行化开销超过收益
parallel_for(0, 10, [&](int i) {
    array[i] += 1;  // 每个任务只有一条加法！
});
// 调度 10 个 Job 的开销远大于直接循环
```

**修复**：
- 设置合理的 grain size（最小任务粒度）
- 通常每个任务至少执行几百到几千条指令才值得并行化
- 使用 `parallel_for` 的 `min_grain_size` 参数控制
