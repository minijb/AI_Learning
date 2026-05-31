# C++20 协程与引擎应用

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 5h
> 前置知识: 第24节 (C++20 特性引擎实战)

---

## 1. 概念讲解

### 1.1 协程是什么

协程 (coroutine) 是一个**可以被暂停和恢复的函数**。与普通函数不同——普通函数从第一行执行到最后一行后栈帧销毁——协程可以在中途挂起，把控制权交还给调用者，稍后从挂起点继续执行。

游戏引擎中最自然的类比：**协程就像一个可以在 `yield` 处暂停、下一帧继续的 Update 函数**。

```cpp
// 普通函数：执行完就结束
void normalFunction() {
    step1();  // 必须等 step1 完成
    step2();  // 才能执行 step2
    step3();  // 最后 step3
}

// 协程：可以暂停、等待、恢复
Task entityBehavior() {
    co_await moveTo(target);      // 暂停直到到达目标
    co_await waitSeconds(2.0f);   // 暂停 2 秒
    co_await playAnimation("die"); // 暂停直到动画结束
    destroySelf();                 // 最后执行
}
```

### 1.2 三种关键字

C++20 引入了三个协程关键字（注意：不是 C++17，C++20 才标准化）：

| 关键字 | 含义 | 效果 |
|--------|------|------|
| `co_await` | 暂停并等待一个操作完成 | 将当前协程挂起，等待 awaitable 对象就绪后恢复 |
| `co_yield` | 产出一个值并暂停 | 向调用者返回一个值，然后挂起；调用者可以继续请求下一个值 |
| `co_return` | 返回最终值并结束协程 | 与普通 `return` 不同——它通知 promise 对象，然后销毁协程帧 |

**关键规则**：只要函数体内出现了 `co_await`、`co_yield` 或 `co_return` 中**任意一个**，编译器就把这个函数编译成协程——即使它实际上从不挂起。

### 1.3 编译器做了什么：从函数到状态机

协程的核心魔法在于编译器自动生成的状态机。让我们通过一个简化例子看清楚：

```cpp
Task<int> computeAsync() {
    int a = co_await readFile("a.txt");    // 挂起点 #1
    int b = co_await readFile("b.txt");    // 挂起点 #2
    co_return a + b;
}
```

编译器将其转换为（伪代码）：

```cpp
struct computeAsync_frame {
    // promise 对象
    Task<int>::promise_type __promise;
    
    // 局部变量被提升为帧成员
    int a;
    int b;
    
    // 当前恢复点：0=开始, 1=从挂起点#1恢复, 2=从挂起点#2恢复
    int __resume_point = 0;
    
    // awaitable 临时对象
    Awaitable_FileReader __await1;
    Awaitable_FileReader __await2;
};

void computeAsync_resume(computeAsync_frame* frame) {
    switch (frame->__resume_point) {
    case 0:  // 初始执行
        frame->__await1 = readFile("a.txt").operator co_await();
        if (!frame->__await1.await_ready()) {
            frame->__resume_point = 1;
            frame->__await1.await_suspend(handle);
            return;  // 挂起！
        }
        // 如果 ready，直接落入 case 1 (fallthrough)
        
    case 1:  // 从第一个 co_await 恢复
        frame->a = frame->__await1.await_resume();
        frame->__await2 = readFile("b.txt").operator co_await();
        if (!frame->__await2.await_ready()) {
            frame->__resume_point = 2;
            frame->__await2.await_suspend(handle);
            return;  // 再次挂起！
        }
        
    case 2:  // 从第二个 co_await 恢复
        frame->b = frame->__await2.await_resume();
        frame->__promise.return_value(frame->a + frame->b);  // co_return
    }
}
```

**关键观察**：
- 协程帧在**堆上分配**（默认行为）——每个协程实例有自己的帧
- 局部变量变成了帧的成员——这就是为什么协程可以在挂起后仍能访问它们
- 栈变量不复存在——协程挂起时 C++ 栈帧被销毁，但帧在堆上存活
- `__resume_point` 是状态机的"程序计数器"

在 [godbolt.org](https://godbolt.org/) 上用 `-std=c++20 -O0` 编译一个简单的协程，你可以看到编译器生成的实际代码结构。

### 1.4 协程的三个核心组件

C++ 协程框架由三部分构成，其设计哲学是"机制而非策略"——标准库只提供了底层机制，具体的协程类型（Task、Generator 等）由库作者实现。

#### Promise 类型

Promise 是协程的"控制中心"。编译器在协程帧内创建 promise 对象，并通过它控制协程的生命周期：

```cpp
struct promise_type {
    // 获取返回对象（协程第一次挂起前调用）
    Task get_return_object();
    
    // 初始挂起点：返回 suspend_never{} 则不挂起直接执行
    std::suspend_always initial_suspend() { return {}; }
    
    // 最终挂起点：协程结束后
    std::suspend_always final_suspend() noexcept { return {}; }
    
    // 处理 co_return（无值版本）
    void return_void() {}
    
    // 处理未捕获异常
    void unhandled_exception() { std::terminate(); }
};
```

#### Awaitable 和 Awaiter

`co_await` 右边可以是一个 Awaitable（定义了 `operator co_await()`）或直接是一个 Awaiter（定义了 `await_ready/await_suspend/await_resume`）：

```cpp
struct SimpleAwaiter {
    bool await_ready() const noexcept { 
        return false;  // 总是挂起
    }
    
    void await_suspend(std::coroutine_handle<> h) const noexcept {
        // 在这里安排何时恢复协程
        // 可以先存储 h，稍后调用 h.resume()
    }
    
    void await_resume() const noexcept {
        // 协程恢复后，await_ready/suspend/resume 的返回值
        // 作为 co_await 表达式的值
    }
};
```

**执行流程**：
1. 计算 `co_await expr` → 获取 Awaiter 对象
2. 调用 `awaiter.await_ready()` — 如果返回 `true`，跳过挂起
3. 如果返回 `false` → 调用 `awaiter.await_suspend(handle)`
4. 协程挂起，控制权返回调用者
5. 未来的某个时刻，`handle.resume()` 被调用
6. 协程从挂起点继续 → 调用 `awaiter.await_resume()` → 获取结果

#### coroutine_handle

`std::coroutine_handle<P>` 是一个非拥有指针，指向协程帧。它可以：
- `resume()` — 恢复挂起的协程
- `done()` — 检查协程是否已完成
- `destroy()` — 销毁协程帧（释放堆内存）
- `promise()` — 访问协程的 promise 对象
- `address()` — 获取协程帧的地址（用于哈希、调试）

### 1.5 对称转移 (Symmetric Transfer)

C++20 引入了 `std::noop_coroutine()` 和对 `await_suspend` 返回值的扩展支持，实现了**对称转移**——一个协程挂起时可以直接跳转到另一个协程，而不经过调用者。

```cpp
// await_suspend 可以返回 coroutine_handle：
std::coroutine_handle<> await_suspend(std::coroutine_handle<> h) {
    // 返回另一个协程的 handle → 编译器直接跳转到它
    // 不需要回到调度器再调度
    return nextJob.handle;
}
```

这避免了逐级返回调用栈的开销。在任务系统中，一个 Job 的 completion 可以**直接**恢复等待它的协程，无需调度器的参与——这是零开销的关键。

### 1.6 引擎视点：协程 vs 线程 vs 回调

| 维度 | 线程 | 回调 | 协程 |
|------|------|------|------|
| 栈大小 | ~1-8 MB | 无额外栈 | ~几十到几百字节帧 |
| 切换成本 | 系统调用, ~1-10μs | 函数调用 | ~10-50ns (函数调用级别) |
| 编程模型 | 同步 | 异步, 回调地狱 | 看起来同步，实际异步 |
| 堆分配 | 无 | 可能需要 (std::function) | 默认帧堆分配（可自定义） |
| 每帧可创建数 | 极少 | 多 | 极多 (几十万) |

**引擎中的取舍**：协程适合"逻辑上的并发"（像行为树、资源加载等需要等待的场景），不适合"物理上的并发"（需要多核并行计算）。在 16.6ms 帧预算内，协程的切换开销几乎可忽略。

---

## 2. 代码示例

### 2.1 一个简单的 Generator（co_yield 用法）

```cpp
#include <coroutine>
#include <iostream>
#include <optional>

// Generator: 懒序列——按需产生值
template <typename T>
struct Generator {
    struct promise_type {
        T current_value;
        
        Generator get_return_object() {
            return Generator{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }
        
        std::suspend_always initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        
        // co_yield expr → 存储值，挂起
        std::suspend_always yield_value(T value) {
            current_value = value;
            return {};
        }
        
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };
    
    std::coroutine_handle<promise_type> handle;
    
    explicit Generator(std::coroutine_handle<promise_type> h) : handle(h) {}
    ~Generator() { if (handle) handle.destroy(); }
    
    // 不可拷贝（协程帧唯一）
    Generator(const Generator&) = delete;
    Generator& operator=(const Generator&) = delete;
    
    // 可移动
    Generator(Generator&& other) noexcept : handle(other.handle) {
        other.handle = nullptr;
    }
    Generator& operator=(Generator&& other) noexcept {
        if (this != &other) {
            if (handle) handle.destroy();
            handle = other.handle;
            other.handle = nullptr;
        }
        return *this;
    }
    
    // 迭代器支持
    struct iterator {
        std::coroutine_handle<promise_type> handle;
        
        T operator*() const { return handle.promise().current_value; }
        iterator& operator++() {
            handle.resume();
            return *this;
        }
        bool operator!=(std::default_sentinel_t) const {
            return !handle.done();
        }
    };
    
    iterator begin() {
        handle.resume();  // 启动协程，执行到第一个 co_yield
        return {handle};
    }
    
    std::default_sentinel_t end() { return {}; }
};

// 使用案例：引擎中的资产 ID 序列
Generator<int> assetIDs(int from, int to) {
    for (int i = from; i <= to; ++i) {
        co_yield i;  // 懒生成——只在迭代请求时才计算
    }
}

// 演示
void demoGenerator() {
    // 不会一次性生成所有 ID——按需产生
    for (int id : assetIDs(1000, 2000)) {
        // 每帧处理一个资产
        processAsset(id);
    }
}
```

### 2.2 异步文件加载器（引擎级 Task + 自定义 Awaitable）

```cpp
#include <coroutine>
#include <iostream>
#include <thread>
#include <queue>
#include <functional>
#include <memory>
#include <string>
#include <chrono>

// ============= 第一部分：协程任务类型 =============

struct Task {
    struct promise_type {
        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_never initial_suspend() { return {}; }  // 立即开始执行
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };
    
    std::coroutine_handle<promise_type> handle;
    
    explicit Task(std::coroutine_handle<promise_type> h) : handle(h) {}
    ~Task() { if (handle) handle.destroy(); }
    Task(const Task&) = delete;
    Task& operator=(const Task&) = delete;
    Task(Task&& other) noexcept : handle(other.handle) { other.handle = nullptr; }
    Task& operator=(Task&& other) noexcept {
        if (this != &other) {
            if (handle) handle.destroy();
            handle = other.handle;
            other.handle = nullptr;
        }
        return *this;
    }
    
    bool done() const { return handle.done(); }
    void resume() { if (!handle.done()) handle.resume(); }
};

// ============= 第二部分：IO 操作抽象 =============

// 模拟异步 I/O 完成通知的回调
struct IORequest {
    std::string path;
    std::function<void(std::string)> onComplete;
};

class IOSystem {
public:
    void submitRead(std::string path, std::function<void(std::string)> callback) {
        // 在真实引擎中，这里会发起系统级异步 I/O
        // 这里用线程模拟
        auto req = std::make_shared<IORequest>();
        req->path = path;
        req->onComplete = std::move(callback);
        
        std::thread([req]() {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            std::string result = "Content of " + req->path;
            req->onComplete(std::move(result));
        }).detach();
    }
};

// ============= 第三部分：自定义 Awaitable =============

// co_await 一个文件读取操作
struct AsyncFileRead {
    IOSystem& io;
    std::string path;
    
    bool await_ready() const noexcept { 
        return false;  // 文件 I/O 总是异步的
    }
    
    void await_suspend(std::coroutine_handle<> h) {
        io.submitRead(path, [h, this](std::string content) mutable {
            result = std::move(content);
            h.resume();  // 数据就绪，恢复协程
        });
    }
    
    std::string await_resume() const noexcept {
        return std::move(result);
    }
    
    mutable std::string result;
};

// ============= 第四部分：引擎层调度器 =============

class CoroutineScheduler {
public:
    void schedule(Task task) {
        pendingTasks.push(std::move(task));
    }
    
    // 每帧调用一次
    void update(size_t maxResumePerFrame = 100) {
        size_t count = 0;
        while (!pendingTasks.empty() && count < maxResumePerFrame) {
            auto& task = pendingTasks.front();
            if (task.done()) {
                pendingTasks.pop();
            } else {
                task.resume();
                if (!task.done()) {
                    // 任务又挂起了，放回队列末尾
                    pendingTasks.push(std::move(task));
                }
                pendingTasks.pop();
            }
            ++count;
        }
    }
    
    bool hasPendingWork() const { return !pendingTasks.empty(); }
    
private:
    std::queue<Task> pendingTasks;
};

// ============= 第五部分：实际使用 =============

IOSystem ioSystem;

// 协程化的资产加载逻辑——看起来像同步代码，实际是异步的
Task loadLevelAssets(CoroutineScheduler& scheduler) {
    // 并发发起所有加载请求
    auto textureFuture = AsyncFileRead{ioSystem, "level01/texture.png"};
    auto meshFuture    = AsyncFileRead{ioSystem, "level01/mesh.obj"};
    auto audioFuture   = AsyncFileRead{ioSystem, "level01/bgm.ogg"};
    
    // 顺序等待（实际可以并发，这里展示逐个等待）
    std::string texture = co_await textureFuture;
    std::cout << "Texture loaded: " << texture << "\n";
    
    std::string mesh = co_await meshFuture;
    std::cout << "Mesh loaded: " << mesh << "\n";
    
    std::string audio = co_await audioFuture;
    std::cout << "Audio loaded: " << audio << "\n";
    
    std::cout << "All assets loaded!\n";
    
    // co_return 隐式（return_void）
}

// 模拟游戏主循环
void gameLoopDemo() {
    CoroutineScheduler scheduler;
    scheduler.schedule(loadLevelAssets(scheduler));
    
    // 模拟 60fps 游戏循环，每帧执行调度
    for (int frame = 0; frame < 300; ++frame) {
        scheduler.update(10);  // 每帧最多恢复 10 个协程
        if (!scheduler.hasPendingWork()) {
            std::cout << "All coroutines completed at frame " << frame << "\n";
            break;
        }
    }
}
```

### 2.3 行为树协程（引擎 AI 系统）

```cpp
#include <coroutine>
#include <iostream>
#include <chrono>
#include <cmath>

// 行为树节点使用协程——每个行为可以在等待中挂起
struct BehaviorAwaitable {
    float duration;  // 等待的秒数
    float elapsed = 0.0f;
    
    bool await_ready() const noexcept { return elapsed >= duration; }
    
    void await_suspend(std::coroutine_handle<> h) {
        // 真实引擎中：向时间系统注册回调，deltaTime 到达后 resume
        // 这里用静态存储演示
        storedHandle = h;
    }
    
    void await_resume() const noexcept {}
    
    static std::coroutine_handle<> storedHandle;
    static void tick(float dt) {
        // 由引擎每帧调用
    }
};

std::coroutine_handle<> BehaviorAwaitable::storedHandle;

// 等待指定秒数
BehaviorAwaitable waitSeconds(float duration) {
    return {duration, 0.0f};
}

// 移动到目标位置（模拟）
BehaviorAwaitable moveTo(float x, float y, float z) {
    // 真实实现会向移动系统发送请求，等待到达
    return {0.5f, 0.0f};  // 假设移动需要 0.5 秒
}

// 一个实体的行为协程
Task enemyPatrolBehavior() {
    while (true) {
        // 移动到巡逻点 A
        co_await moveTo(10.0f, 0.0f, 5.0f);
        co_await waitSeconds(2.0f);  // 在 A 点停留
        
        // 移动到巡逻点 B
        co_await moveTo(-10.0f, 0.0f, -5.0f);
        co_await waitSeconds(2.0f);  // 在 B 点停留
        
        // 无限循环巡逻
    }
}
```

### 2.4 自定义协程帧分配器（消除堆分配）

```cpp
#include <coroutine>
#include <cstddef>
#include <new>
#include <vector>

// 简单的 Arena 分配器用于协程帧
class CoroutineArena {
public:
    explicit CoroutineArena(size_t size) 
        : buffer(new char[size]), capacity(size), offset(0) {}
    
    ~CoroutineArena() { delete[] buffer; }
    
    void* allocate(size_t size, size_t alignment) {
        // 对齐指针
        uintptr_t addr = reinterpret_cast<uintptr_t>(buffer + offset);
        uintptr_t aligned = (addr + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned - addr;
        
        if (offset + padding + size > capacity) {
            return nullptr;  // 空间不足
        }
        
        offset = offset + padding + size;
        return reinterpret_cast<void*>(aligned);
    }
    
    void reset() { offset = 0; }  // 帧结束时重置
    
private:
    char* buffer;
    size_t capacity;
    size_t offset;
};

// 使用自定义 operator new 为协程帧分配内存
struct ArenaTask {
    struct promise_type {
        // 编译器会调用这个 operator new 来分配协程帧
        static void* operator new(size_t frameSize, CoroutineArena& arena) {
            return arena.allocate(frameSize, alignof(std::max_align_t));
        }
        
        // 对应的 operator delete（正常析构路径）
        static void operator delete(void* ptr) {
            // Arena 不做单独释放——帧结束时整批丢弃
        }
        
        Task get_return_object();
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };
};

// 使用方式
void frameUpdate(CoroutineArena& arena) {
    // 协程帧从 arena 分配——零动态分配开销
    // auto task = createSomeTask(arena);
    // scheduler.schedule(task);
    
    // 帧结束时，arena.reset() 回收所有协程帧
}
```

### 2.5 协程 + Job System 集成

```cpp
#include <coroutine>
#include <functional>
#include <atomic>

// Job 完成后的 awaitable
struct JobAwaitable {
    std::atomic<bool>& completed;
    
    bool await_ready() const noexcept {
        return completed.load(std::memory_order_acquire);
    }
    
    bool await_suspend(std::coroutine_handle<> h) {
        // 如果 Job 还没完成，存储 handle 等待
        storedHandle = h;
        // Job 完成后会调用 storedHandle.resume()
        return !completed.load(std::memory_order_acquire);
    }
    
    void await_resume() const noexcept {}
    
    std::coroutine_handle<> storedHandle;
};

// 协程等待 Job 完成——主线程不会阻塞
Task processPhysicsAndRender() {
    JobAwaitable physicsJob = submitPhysicsJob();
    co_await physicsJob;  // 主线程可以处理其他协程，不阻塞！
    
    // 物理完成后继续渲染设置
    JobAwaitable cullingJob = submitCullingJob();
    co_await cullingJob;
    
    submitRenderCommands();
}
```

---

## 3. 练习

### 必做练习 1: 实现异步资产加载系统

基于 2.2 节代码，实现一个完整的异步资产加载系统：

1. 支持多种资产类型（Texture、Mesh、Audio），通过 `template<typename T>` 抽象
2. 实现并发加载——同时发起多个 I/O 请求，使用自定义 awaitable 等待**所有**完成（wait-all 模式）
3. 添加加载进度回调——每完成一个资产，更新进度条
4. 超时处理——如果某个资产 5 秒内未完成，取消等待并报告错误

要求：所有 I/O 操作使用协程，不阻塞主线程。测试时模拟至少 10 个并发资产加载。

### 必做练习 2: 行为树协程系统

实现一个基于协程的行为树节点系统：

1. 定义基本行为节点：Sequence、Selector、Parallel、Decorator（至少这些）
2. 每个叶子行为是可 `co_await` 的操作（`moveTo`、`waitSeconds`、`playAnimation` 等）
3. 实现一个 `while(true)` 巡逻敌人和一个对玩家反应的状态机敌人
4. 集成到帧循环中——每帧调度器驱动所有行为协程

要求：行为可以跨帧挂起和恢复，不阻塞渲染。

### 可选挑战: 协程 + Job System 全集成

将协程调度器与一个真实的 Job System 集成：

1. 实现一个多线程 Job System（可简化，重点在集成接口）
2. 协程可以 `co_await` 一个 Job 的完成（跨线程安全恢复）
3. 实现工作窃取：空闲线程可以从其他线程的协程队列窃取可恢复协程
4. 基准测试：对比协程调度 vs 回调调度在处理 10000 个依赖任务时的性能差异

提示：使用第 20-22 节（原子操作、多线程架构、Lock-Free 队列）学到的知识。

---

## 4. 扩展阅读

- **C++20 标准 (N4868)** `[expr.await]` — 协程表达式的标准定义
- **C++ Coroutines: Understanding operator co_await** — Lewis Baker 的系列文章，协程内部机制的最佳讲解
- **CppCon 2022: C++ Coroutines From Scratch** — Phil Nash 的演讲，从零实现协程类型
- **libcoro** — 生产级 C++20 协程库，包含 Task、Generator、async_mutex 等
- **cppcoro** — Lewis Baker 的协程库，展示了协程设计模式
- **Godbolt** — https://godbolt.org/ 上用 `-std=c++20 -O0` 编译协程，观察编译器生成的状态机代码
- **Game Engine Architecture (3rd ed.)** Ch. 7.4 — 引擎中的并发模型讨论
- **Boost.Coroutine2** — C++11 的栈式协程（与 C++20 的无栈协程对比）

---

## 常见陷阱

1. **悬挂引用——协程参数的生命周期**：协程挂起时，调用者的栈帧已销毁。如果协程参数是引用，挂起后引用变为悬垂。
   ```cpp
   // ✗ 错误：传入临时变量引用
   Task bad(const std::string& path) {
       co_await loadAsync(path);  // 如果调用者传入了临时 string，挂起后 path 悬垂
   }
   
   // ✓ 正确：按值传递或确保引用指向的对象生命周期覆盖整个协程
   Task good(std::string path) {
       co_await loadAsync(path);  // path 被复制到协程帧中
   }
   ```

2. **忘记 destroy() 协程帧——内存泄漏**：`final_suspend` 返回 `suspend_always` 时，协程结束后帧不会自动销毁。必须在外部调用 `handle.destroy()`。如果 Task 的析构函数中忘记了 `destroy()`，帧永远泄漏。
   ```cpp
   // ✓ 确保在适当的地方 destroy
   ~Task() { 
       if (handle) handle.destroy();  // 必须！
   }
   ```

3. **co_return vs co_yield 混淆**：`co_yield` 是"产出一个值并挂起，调用者可以继续请求下一个值"；`co_return` 是"协程到此结束，返回最终值"。在 Generator 中用 `co_return` 会导致序列提前终止；在 Task 中用 `co_yield` 可能永远不结束。

4. **堆分配爆炸**：默认情况下每个协程帧都在堆上分配。在高频场景（每帧数千个协程）中，`new`/`delete` 的开销会吃掉帧预算。解决方案：
   - 使用自定义 `operator new`（如 2.4 节的 Arena）
   - 使用协程池——预分配帧，回收复用
   - C++23 起可以使用协程帧的栈分配优化（编译器对 trivially-destructible 的协程帧进行 elision）

5. **异常穿透**：如果协程中抛出异常且 `promise_type::unhandled_exception()` 没有正确处理（默认调用 `std::terminate()`），整个程序终止。在生产代码中必须实现适当的异常处理路径。
