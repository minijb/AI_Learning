# C++ 协程、异步与 RAII 资源管理 深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 游戏引擎开发工程师 — C++ 引擎编程：语言特性精要
> 关联深度探索: [RAII 完整分析](./raii-complete-analysis.md), [栈展开](./stack-unwinding.md)
> 分析日期: 2026-05-28

---

## 第 1 层: 直觉理解

**协程是可以"暂停并稍后恢复"的函数。** 普通函数被调用后必须从头跑到尾才能返回；协程可以在中途停住，把控制权还给调用者，之后再从上次停住的地方继续执行。

**类比：一本书和一张书签。** 普通函数就像一口气读完一本书——你翻开第一页，不读完不放下。协程则允许你在任何一页夹上书签、合上书，去做别的事；回来时翻开书签位置，继续读。最关键的区别在于——你把书合上时，所有状态（书签在哪一页、你在书页空白处写的笔记、你折的角）都保留在"书"这个容器里，而不是凭空消失。

在 C++ 中，这个"书"叫做**协程帧（coroutine frame）**——一块堆（或栈）上分配的内存，存储了协程的所有局部变量、参数、以及当前执行到了哪个暂停点。

**异步是什么：** 协程最常见的用途就是异步编程。"异步"意味着"我不等结果，我先去做别的，结果到了通知我"。传统异步用回调（callback）——嵌套地狱。协程让你用同步的写法写异步的代码：

```cpp
// 看起来像同步代码，实际上每次 co_await 都可能暂停
Task<Response> fetchAndProcess(std::string url) {
    auto data = co_await httpGet(url);     // 暂停，等网络返回
    auto parsed = co_await parseJson(data); // 暂停，等解析完成
    co_return parsed;
}
```

每次 `co_await` 都是一个"夹书签"的点——协程暂停，控制权返还给调用者或调度器，局部变量 `data` 和 `url` 安然躺在协程帧里，等待下次恢复。

**RAII 的挑战：** 普通函数的 RAII 很简单——变量在栈上，离开作用域自动析构，栈展开保证析构执行。但协程的局部变量活在**堆上的协程帧**里，而协程的执行流是**分段**的（暂停后可能隔很久才恢复，甚至永远不恢复）。这意味着：

- 协程被销毁时，协程帧里的局部变量会不会被析构？
- `co_await` 暂停后，如果协程永远不被恢复，那些已经获取的资源（锁、文件、内存）谁来释放？
- 局部变量的引用和指针在暂停期间是否仍然有效？

这些问题使得"协程中的 RAII"远不是自动免费午餐，而是需要精心设计的契约。

---

## 第 2 层: 使用场景

### 典型场景

1. **异步 I/O（网络请求、文件读写）** — 最高频场景。用同步写法表达异步逻辑，避免回调地狱。每个 `co_await` 等待一个 I/O 操作完成，协程在 I/O 期间不占用线程。
2. **惰性序列生成（generator）** — `co_yield` 逐个产出值，调用者按需拉取。适合处理无限序列、大文件逐行读取、组合数学递推。
3. **状态机扁平化** — 复杂的多步异步流程（如 OAuth 握手：请求 token → 解析 → 请求资源 → 重试）传统写法是嵌套回调或状态机跳转表；协程可以写成线性代码，编译器自动生成状态机。
4. **并发任务的组合编排** — `co_await when_all(taskA, taskB)` 等待多个异步操作同时完成，用同步语法表达 fork-join。

### 不适用场景

1. **计算密集型热路径** — 协程有不可忽视的分配和间接跳转成本。如果函数不涉及 I/O 等待，使用协程纯属浪费。
2. **已有成熟异步框架的项目** — 如果项目大量使用 callback、future/promise（非协程版）、或 Boost.Asio 旧式回调，引入协程需要适配层，成本可能大于收益。
3. **对延迟要求极高的嵌入式/实时系统** — 协程帧的堆分配不可预测（虽然 HALO 可能消除，但不能依赖），`type-erased` coroutine_handle 的间接调用也有成本。
4. **不需要暂停的场景** — 纯计算函数、简单转换函数。协程的本质优势是"暂停和恢复"，不用这个能力的场景不要硬上。

### 决策树

```
你有等待异步结果的需求吗？
├─ 是 → 你需要在多个异步操作之间保持"上下文"吗？
│   ├─ 是 → 上下文是否包含 RAII 资源（锁、文件、GPU 句柄）？
│   │   ├─ 是 → 需要特别设计资源管理策略（见第 7 层）→ 考虑 co_resource / async RAII
│   │   └─ 否 → C++20 协程非常适合
│   └─ 否 → 简单的 callback 或 std::async 就够了
└─ 否 → 你需要惰性生成序列吗？
    ├─ 是 → co_yield generator 非常适合
    └─ 否 → 你不需要协程
```

---

## 第 3 层: API 层

C++20 协程不是提供了"一个协程类"，而是提供了一套**语言级别的构建块**，由库作者组合出具体的协程类型。理解 API 需要从三个视角展开。

### 3.1 语言关键字（编译器识别的）

| 关键字 | 含义 | 出现位置 |
|--------|------|----------|
| `co_await` | 暂停当前协程，等待 awaitable 就绪 | 协程体内任意位置 |
| `co_yield` | 暂停并产出一个值给调用者 | 协程体内任意位置 |
| `co_return` | 返回最终值并结束协程 | 协程体内（替代 `return`） |

**关键规则：** 函数体内只要出现以上任一关键字，编译器就将其识别为**协程函数**，应用协程变换（见第 5 层）。识别发生在编译期，与运行时类型无关。

### 3.2 Promise 类型（库作者定义的）

编译器通过 `std::coroutine_traits<ReturnType, Args...>::promise_type` 查找协程的 **promise_type**。这个类型是"协程的控制面板"——编译器在协程生命周期的关键节点调用 promise 的成员函数。

```cpp
// 一个最小化的 promise_type（以 Task<T> 为例）
struct TaskPromise {
    // --- 生命周期钩子 ---
    Task<T> get_return_object();           // 协程启动前，构造返回给调用者的对象

    // --- 暂停控制 ---
    std::suspend_never initial_suspend();  // 启动时是否立即暂停？
                                           // suspend_never → 直接执行到第一个 co_await
                                           // suspend_always → 先暂停，等待调用者显式 resume

    std::suspend_always final_suspend() noexcept;  // 结束时是否暂停？
                                           // suspend_always → 保持协程帧存活，等待手动 destroy
                                           // suspend_never → 协程结束后自动销毁帧

    // --- 值与异常 ---
    void return_value(T value);            // co_return value; 调用
    void return_void();                    // co_return; 调用
    void unhandled_exception();            // 协程体抛异常且未捕获时调用

    // --- yield ---
    std::suspend_always yield_value(T value);  // co_yield value; 调用
};
```

**`initial_suspend` 和 `final_suspend` 的协作决定了协程帧的生命周期**——这是理解 RAII 行为的核心，详见第 4 层。

### 3.3 Awaitable / Awaiter 协议

`co_await expr` 的 `expr` 必须是一个 **awaitable**。编译器将 `co_await` 转换为对 awaiter 的调用序列：

```
awaitable → 通过 operator co_await() 或 promise.await_transform() 获得 → awaiter
```

**Awaiter 的三个必需方法：**

| 方法 | 返回值 | 语义 |
|------|--------|------|
| `await_ready()` | `bool` | 返回 `true`：结果已就绪，**不暂停**，直接进入 `await_resume` |
| | | 返回 `false`：结果未就绪 → 暂停协程 → 调用 `await_suspend` |
| `await_suspend(handle)` | `void` / `bool` / `coroutine_handle<>` | 传入当前协程的 handle，负责安排"稍后恢复" |
| `await_resume()` | 协程需要的值类型 | 恢复执行后调用，返回值作为 `co_await` 表达式的结果 |

**`await_suspend` 的三种返回值语义：**

| 返回类型 | 语义 |
|----------|------|
| `void` | 暂停后控制权返回调用者/恢复者 |
| `bool` | `true` → 暂停；`false` → 不暂停，立即恢复 |
| `coroutine_handle<>` | **对称转移（symmetric transfer）**：不经过调用者，直接跳转到目标协程（零额外栈帧） |

### 3.4 `std::coroutine_handle<Promise>` — 协程的外部控制句柄

```cpp
template <typename Promise = void>
struct coroutine_handle {
    static coroutine_handle from_promise(Promise&);   // 从 promise 引用反查 frame 地址
    void* address() const noexcept;                    // frame 的基地址
    static coroutine_handle from_address(void*);       // 从地址构造句柄
    explicit operator bool() const noexcept;           // 是否非空
    void operator()() const;                           // resume() 的别名
    void resume() const;                               // 恢复协程执行
    void destroy() const noexcept;                     // 销毁协程帧（调用析构 → 释放内存）
    bool done() const noexcept;                        // 协程是否已执行到 final_suspend
    Promise& promise() const;                          // 获取 promise 引用
};
```

**`destroy()` 是关键方法：** 它销毁协程帧，调用帧内所有存活局部变量的析构函数，然后释放帧内存。如果协程在某个 `co_await` 暂停点被 `destroy()` 了，那么只有在该暂停点**之前**构造的对象会被析构——暂停点之后的对象尚未构造。

### 3.5 预定义 Awaitable

| 类型 | `await_ready()` | 效果 |
|------|-----------------|------|
| `std::suspend_never` | `true` | 永远不暂停 |
| `std::suspend_always` | `false` | 永远暂停 |

---

## 第 4 层: 行为契约

### 4.1 协程帧的分配与生命周期

```
协程帧 = [promise] [参数拷贝] [局部变量（按声明顺序）] [临时对象] [暂停点状态]
```

- **分配时机：** 协程函数被调用时，编译器插入 `operator new` 分配协程帧（除非 HALO 消除——见第 5 层）
- **释放时机：** `coroutine_handle::destroy()` 被调用时。释放顺序：先调用 `promise` 的析构函数，再析构帧内所有局部变量（逆序），最后 `operator delete` 释放内存
- **`final_suspend` 决定谁调用 `destroy()`：**
  - `final_suspend` 返回 `suspend_always` → 协程结束时暂停，不自动销毁帧。**调用者**负责在适当时候调 `destroy()`。这是最常见的模式——调用者通过返回的 Task 对象持有 handle，在 Task 析构时 destroy
  - `final_suspend` 返回 `suspend_never` → 协程结束时自动销毁帧，**控制权不能返回调用者**（因为帧已经被销毁了，调用者持有的 handle 变为悬空）。HAZARD

### 4.2 局部变量在暂停点的 RAII 行为

这是整个话题最关键的部分：

**在一个 `co_await` 暂停点，已经构造的局部变量不会被析构——它们继续存活在协程帧中。**

```cpp
Task<void> example() {
    std::fstream file("data.txt");   // ① 构造：打开文件（RAII 获取资源）
    auto data = co_await readAsync(); // ② 暂停：file 依然打开，资源被"冻结"在帧中
    process(file, data);              // ③ 恢复后继续使用 file
}                                      // ④ 作用域结束 → file 析构 → 文件关闭
```

**但如果协程在暂停点被 `destroy()` 了呢？**

```cpp
Task<void> example() {
    auto lock = std::unique_lock(mutex);  // ① 加锁
    co_await someAsyncOp();               // ② 暂停——锁还持有！（可能死锁）
    // 如果协程在②处被 destroy()：
    // → lock 的析构函数会被调用 → 解锁 ✓（RAII 正常工作）
} // ③
```

**关键点：** `handle.destroy()` 会**逆序析构帧内所有已构造的局部变量**。如果协程在暂停点被强制销毁，RAII 仍然生效——每个已获取的资源都会被释放。这让协程中的 RAII 在"协程被销毁"路径上保持了异常安全性。

**但有一个致命陷阱：** 协程可能在暂停点**永远不被恢复，也永远不被销毁**——泄漏。

### 4.3 `unhandled_exception` 与异常传播

协程体内抛出的未捕获异常：

1. 协程立即进入"异常状态"，后续代码不执行
2. 编译器调用 `promise.unhandled_exception()` ——在这里可以调用 `std::current_exception()` 获取异常对象
3. 然后协程直接跳到 `final_suspend` ——不执行任何中间代码，也不执行任何局部变量的析构 → 不，实际上是执行析构的

**纠正：** 标准规定（[dcl.fct.def.coroutine]/10），当协程因未捕获异常而终止时，活跃的局部变量**会被析构**（通过标准的栈展开机制，不过是"帧展开"）。`unhandled_exception` 通常用于将异常存储在 promise 中，等调用者通过 `co_await` 的 `await_resume` 重新抛出：

```cpp
void unhandled_exception() {
    exception_ = std::current_exception();  // 存储异常
}

// 在 final_suspend 之后，调用者通过 Task 的某个方法获取：
T result() {
    if (exception_) std::rethrow_exception(exception_);
    return value_;
}
```

### 4.4 线程安全

- **协程帧本身不提供任何线程安全保证。** 如果多个线程并发访问协程帧内的数据（比如通过共享的 `shared_ptr`），需要手动同步
- **`coroutine_handle::resume()` 本身不是线程安全的：** 从多个线程并发 `resume()` 同一协程是数据竞争
- **协程可以在不同线程上被恢复：** 线程 A 上暂停，线程 B 上 `resume()`——这是合法的，也是异步 I/O 的标准模式（I/O 线程池中的某个线程完成 I/O 后恢复协程）
- **RAII 的线程绑定被打破：** 传统 RAII 中，构造和析构发生在同一线程。协程中，一个 `std::mutex` 的 `lock` 可能在暂停前线程 A 上发生，但 `unlock` 在恢复后线程 B 上执行——如果 mutex 本身不是递归的且要求同一线程解锁，这是 UB

**这就是协程中 RAII 的张力的核心：** 很多 RAII 类型（`lock_guard`、某些 GPU 上下文对象）隐式假设构造和析构在同一线程。协程打破了这一假设。

### 4.5 引用和指针的有效性

| 指向对象 | 在 co_await 暂停后是否有效 |
|----------|---------------------------|
| 局部变量（值语义） | ✓ 有效（存在帧中） |
| 局部变量的引用/指针 | ✓ 有效（但使用者需要在协程存活期间访问） |
| 函数参数（按值传递） | ✓ 有效（被拷贝到帧中） |
| 函数参数（按引用传递） | ⚠ 仅当引用指向的对象比协程活得更久 |
| Lambda 捕获的引用 | ⚠ 同上 |
| `this` 指针 | ⚠ 仅当协程是成员函数且对象比协程活得久 |

**最常见陷阱：** 按引用传递的参数在 `co_await` 后变为悬空引用。

```cpp
Task<void> bad(std::string const& ref) {
    co_await something();  // 暂停...
    use(ref);              // ...如果调用者已经销毁了 ref 指向的 string，UB！
}
```

---

## 第 5 层: 实现原理

### 5.1 编译器变换（Compiler Transform）

编译器将协程函数体转换为一个**状态机类**。这个变换是理解 RAII 行为的基础。

**原始代码：**

```cpp
Task<int> compute(int x) {
    int y = x * 2;
    int z = co_await fetch(y);
    co_return z + 1;
}
```

**编译器变换（伪代码）：**

```
// 编译器生成的状态机（一个概念模型）
struct __compute_frame {
    // --- 协程帧 ---
    TaskPromise __promise;     // promise 对象
    int x;                     // 参数拷贝（按值）
    int y;                     // 局部变量
    int z;                     // 局部变量
    int __state = 0;           // 当前状态/暂停点编号
    // awaiter 占位符
    decltype(fetch(y))::awaiter_type __awaiter;

    // --- 恢复入口 ---
    void __resume() {
        switch (__state) {
        case 0: goto __initial_suspend;
        case 1: goto __after_co_await_1;
        case -1: return; // final_suspend 后，done
        }

    __initial_suspend:
        // 1. initial_suspend
        auto __init_awaiter = __promise.initial_suspend();
        if (!__init_awaiter.await_ready()) {
            __state = 0;
            __init_awaiter.await_suspend(handle_from_frame());
            return;  // 暂停
        }
        __init_awaiter.await_resume();

        // 2. 用户代码 → 状态 1
        y = x * 2;
        __awaiter = fetch(y);  // 获取 awaiter
        if (!__awaiter.await_ready()) {
            __state = 1;
            __awaiter.await_suspend(handle_from_frame());
            return;  // 暂停 ← 局部变量 y 仍然存活在帧中
        }

    __after_co_await_1:
        // 3. 恢复后继续
        z = __awaiter.await_resume();

        // 4. co_return
        __promise.return_value(z + 1);
        goto __final_suspend;

    __final_suspend:
        // 5. final_suspend（局部变量在此之后析构）
        {
            auto __final_awaiter = __promise.final_suspend();
            if (!__final_awaiter.await_ready()) {
                __state = -1;
                __final_awaiter.await_suspend(handle_from_frame());
                return;  // 最终暂停——等待 destroy()
            }
            // 如果 final_awaiter.await_ready() 为 true：
            // 帧在此自动销毁（suspend_never 模式）
        }
    }
};
```

**关键推导：**

1. 局部变量在帧中按声明顺序排布，位于 promise 之后
2. 每个暂停点 (`__state = N; return;`) 之前，所有在该暂停点之前声明的变量都已完成构造
3. 当 `handle.destroy()` 被调用时，帧内的析构按逆序执行——从最后构造的变量开始，到 promise 结束
4. 这意味着：**在暂停点被 destroy 时，只有暂停点之前的变量会被析构**。暂停点之后声明的变量从未被构造，跳过

### 5.2 对称转移（Symmetric Transfer）

`await_suspend` 返回 `coroutine_handle<>` 时触发对称转移：

```
// 传统模式（每次恢复都要经过调度器）：
scheduler.resume(A) → A 暂停 → return → scheduler.resume(B) → B 暂停 → return → ...

// 对称转移（协程直接链式跳转）：
A 暂停 → await_suspend 返回 B.handle → 直接跳转到 B.__resume()
```

对称转移的关键特性：**不增加调用栈深度**。即使 A→B→C→D 链式暂停恢复，栈深度始终为 O(1)。这对于游戏引擎中每帧可能处理数千个协程的场景至关重要。

### 5.3 HALO — 堆分配消除（Heap Allocation eLision Optimization）

如果编译器能证明协程帧的生命周期严格嵌套在调用者的栈帧内，它可以**将协程帧分配在调用者的栈上**，消除堆分配。

条件：
- 协程的 `operator new` 必须是可内联的（不能是自定义的、跨翻译单元的版本）
- 调用者的所有路径中，协程帧的 `destroy()` 必须在调用者返回之前完成
- 协程帧的地址不能逃逸到调用者之外

**RAII 含义：** HALO 让协程中的 RAII 回到普通栈变量的行为模型——帧在栈上，离开作用域自动析构，不再需要担心"是否有人调用了 destroy"。但 HALO 是**可选优化**，不能作为正确性的依赖。

### 5.4 协程帧内存布局（MSVC ABI 示意）

```
┌─────────────────────────┐ ← frame 基地址
│  Promise (TaskPromise)  │  fixed offset
├─────────────────────────┤
│  参数 N ...             │  按值拷贝的参数
│  参数 2                 │
│  参数 1                 │
├─────────────────────────┤
│  局部变量 1             │  按声明顺序
│  局部变量 2             │
│  ...                    │
│  局部变量 K             │
├─────────────────────────┤
│  await_ready() 临时     │
│  临时对象               │
├─────────────────────────┤
│  __state (int)          │  当前暂停点编号
└─────────────────────────┘
```

---

## 第 6 层: 源码分析

### 6.1 MSVC STL: `coroutine_handle` 实现

> 源文件: `microsoft/STL` `stl/inc/coroutine`, main 分支, 2025 年版本

```cpp
// 核心：handle 只是一个包装了 void* 的轻量对象
template <class _CoroPromise>
struct coroutine_handle {
    void* _Ptr = nullptr;  // 指向协程帧基地址

    // 从 promise 引用反查到 frame 地址 —— 依赖编译器内建函数
    static coroutine_handle from_promise(_CoroPromise& _Prom) noexcept {
        const auto _Prom_ptr  = const_cast<void*>(
            static_cast<const volatile void*>(_STD addressof(_Prom)));
        // __builtin_coro_promise(ptr, align, from_promise?)
        // from_promise=true → 已知 promise 地址，计算 frame 基地址
        const auto _Frame_ptr = __builtin_coro_promise(_Prom_ptr, 0, true);
        coroutine_handle _Result;
        _Result._Ptr = _Frame_ptr;
        return _Result;
    }

    // 销毁：调用编译器内建函数，递归析构 frame
    void destroy() const noexcept {
        __builtin_coro_destroy(_Ptr);
    }

    // 恢复：调用编译器内建函数，跳转回 resume 点
    void resume() const {
        __builtin_coro_resume(_Ptr);
    }

    // 访问 promise
    _CoroPromise& promise() const noexcept {
        return *reinterpret_cast<_CoroPromise*>(
            __builtin_coro_promise(_Ptr, 0, false));
    }
};
```

**设计观察：**
- `coroutine_handle` 是**类型擦除**的——只存储 `void*`，不携带 promise 的类型信息（模板参数仅在编译期用于类型安全）
- `sizeof(coroutine_handle<>)` = `sizeof(void*)` = 8 字节（64 位），零开销
- `destroy()` 标记为 `noexcept`——销毁协程帧不应抛异常（和析构函数的隐式 noexcept 契约一致）

### 6.2 cppcoro: `task<T>` 的 RAII 模式

> 源文件: `lewissbaker/cppcoro` `include/cppcoro/task.hpp`, commit `a87e97f`, 2021 年版本（最具影响力的协程库参考实现）

```cpp
template<typename T>
class task {
public:
    using promise_type = task_promise<T>;

    // task 拥有 coroutine_handle —— task 析构时自动清理
    explicit task(coroutine_handle<promise_type> h) noexcept : coro_(h) {}

    task(task&& other) noexcept : coro_(std::exchange(other.coro_, {})) {}

    ~task() {
        if (coro_) coro_.destroy();  // ← RAII：task 对象析构 → 协程帧析构
    }

    // 对称转移版本的 awaiter
    auto operator co_await() const& = delete;  // 禁止从左值 await（强制移动语义）

    auto operator co_await() && noexcept {
        struct awaiter {
            coroutine_handle<promise_type> coro_;

            bool await_ready() const noexcept { return coro_.done(); }

            // 对称转移：直接跳转到被 await 的协程
            coroutine_handle<> await_suspend(
                coroutine_handle<> awaiting) noexcept {
                coro_.promise().set_continuation(awaiting);
                return coro_;  // 直接转移，不经过调度器
            }

            decltype(auto) await_resume() {
                return coro_.promise().result();
            }
        };
        return awaiter{coro_};
    }

private:
    coroutine_handle<promise_type> coro_;
};
```

**关键设计：**
- `task` 的析构函数调用 `coro_.destroy()`——这是协程中 RAII 的**外层包装**。只要 task 对象是 RAII 管理的（栈上或 unique_ptr），协程帧就必然被清理
- `task` 是 move-only 的——移动后源对象的 handle 置空，确保只有一个 task 对象拥有协程帧（**独占所有权**）
- `operator co_await` 只在右值上可用——防止在 `co_await` 后继续使用同一个 task 对象的迭代器语义问题

### 6.3 `task_promise` 的 final_suspend 设计

```cpp
template<typename T>
struct task_promise {
    // ... 其他成员 ...

    // 关键：final_suspend 返回一个自定义 awaiter
    auto final_suspend() noexcept {
        struct final_awaiter {
            bool await_ready() const noexcept { return false; }  // 总是暂停

            // 对称转移回到 continuation
            coroutine_handle<> await_suspend(
                coroutine_handle<task_promise> h) noexcept {
                auto& promise = h.promise();
                if (promise.continuation_) {
                    return promise.continuation_;  // 对称转移给等待者
                }
                return std::noop_coroutine();       // 没有等待者就挂起
            }

            void await_resume() noexcept {}
        };
        return final_awaiter{};
    }

    coroutine_handle<> continuation_;
};
```

**为什么 final_suspend 总是暂停：** 这是**延迟销毁（deferred destruction）** 模式。如果 final_suspend 不暂停，协程帧会在 `await_suspend` 返回前就被销毁——但此时调用者（continuation）可能还在使用协程的返回值。通过暂停，调用者可以先读取结果，再销毁协程。

**但这也意味着：必须有人在 final_suspend 后调用 `destroy()`**。在 cppcoro 中，这个责任由 `task` 的析构函数承担（见上文）。如果 task 对象被丢弃而没有析构（比如裸指针管理的 task），协程帧就泄漏了。

### 6.4 `co_resource<T>` 模式：资源管理的协程

> 源自: `vector-of-bool/neo-fun` `src/neo/co_resource.hpp` 和 WG21 提案 P1662R0

```cpp
// 概念模型：将协程作为一个 RAII 资源的生命周期容器
template<typename T>
class co_resource {
public:
    // co_resource 的核心思想：用一个生成型协程包装资源
    // 协程体负责创建资源并在最终清理
    // 调用者通过 co_await 获取资源访问权

    // 伪实现
    struct promise_type {
        T* resource_ = nullptr;

        auto get_return_object() { return co_resource{*this}; }

        auto initial_suspend() { return std::suspend_always{}; }
        auto final_suspend() noexcept {
            // 在 final_suspend 中清理资源
            if (resource_) {
                resource_->~T();      // 显式析构
                ::operator delete(resource_);  // 释放内存
            }
            return std::suspend_never{};  // 清理后自动销毁帧
        }

        auto yield_value(T& ref) {
            resource_ = &ref;
            return std::suspend_always{};
        }
        // ...
    };

    // 析构co_resource → 销毁协程帧 → final_suspend 自动清理资源
    ~co_resource() { handle_.destroy(); }

private:
    coroutine_handle<promise_type> handle_;
};

// 使用示例
co_resource<File> openFile(const char* path) {
    File f = File::open(path);
    co_yield f;  // 交出访问权
    // 协程暂停在这里——f 活在协程帧中
    // 当 co_resource 被销毁时：
    //   → handle.destroy() → final_suspend → f 析构 → 文件关闭
}
```

**这是协程中 RAII 的最高级模式：协程本身就是资源的作用域。** 协程体内的变量按正常 RAII 管理，协程帧的销毁由 `co_resource` 的 RAII 包装保证，形成双层 RAII 嵌套。

---

## 第 7 层: 对比与边界

### 7.1 协程中的 RAII 陷阱全景

| 陷阱 | 原因 | 解决方案 |
|------|------|----------|
| **暂停点持有锁** | `co_await` 暂停时锁不释放，其他协程可能永久等待 | 使用 `co_await` 友好的异步锁；或在 `co_await` 前手动释放锁 |
| **按引用参数悬空** | 协程帧复制了引用本身，但引用指向的对象可能已销毁 | 按值传递；或用 `shared_ptr` 延长生命周期 |
| **协程帧泄漏** | 无人调用 `handle.destroy()` | 使用 RAII 包装的 task 类型（如 cppcoro::task） |
| **final_suspend 后忘记 destroy** | final_suspend 总是暂停，但 task 对象被忽略 | 编译器警告 + task 析构函数中 destroy |
| **在 final_suspend 访问已析构变量** | `final_suspend` 的 await_suspend 体中，局部变量还未析构；`await_resume` 体中，局部变量已析构 | 不在 final_suspend 之后访问协程局部状态 |
| **线程亲和性被打破** | `lock_guard` 在暂停点前线程 A 加锁，恢复后线程 B 解锁 | 使用支持跨线程解锁的同步原语（如 `std::mutex` 本身就是合法的——它不要求同一线程）——等等，`std::mutex::unlock()` 确实要求在持有锁的线程上调用。用 `std::recursive_mutex` 或异步原语 |
| **协程移动后资源重复释放** | 如果手动管理 handle，移动后源对象的 handle 仍是有效的 | 遵循 move-only 模式，移动后源对象置空 |

### 7.2 `std::mutex` 与协程的真相

很多人认为协程不能持有 `std::mutex`。实际上：

- `std::mutex::lock()` 和 `unlock()` **不要求同一线程**——POSIX 标准未规定这一限制，C++ 标准也未规定
- 但 `std::unique_lock` 在析构时调 `unlock()`，如果持有线程不同，虽然技术上合法，但违反了"谁加锁谁解锁"的惯用法，极易导致逻辑错误
- **正确做法：** `co_await` 前释放锁，`co_await` 后重新获取。或者使用专门设计的异步互斥锁

```cpp
Task<void> safe_example(std::mutex& m, SharedState& s) {
    {
        auto lock = std::unique_lock(m);
        s.prepare();        // 临界区操作
    }                        // ← lock 析构，释放锁（在 co_await 之前！）
    co_await s.async_op();   // 暂停——锁已经释放了
    {
        auto lock = std::unique_lock(m);
        s.finalize();        // 恢复后重新获取锁
    }
}
```

### 7.3 对比：不同异步模型的 RAII 特性

| 特性 | C++20 协程 | Rust `async`/`.await` | Go `goroutine` | 回调 (C) | `std::future` |
|------|-----------|----------------------|----------------|----------|---------------|
| **RAII 自动清理** | ✓（如果帧被正确销毁） | ✓（编译器保证） | ✗（GC，无析构函数） | ✗（手动管理） | ✓（shared state） |
| **暂停点显式** | ✓（co_await） | ✓（.await） | ✗（任意 I/O 都可能调度走） | — | N/A（阻塞，不暂停） |
| **堆分配成本** | 1 次（或 HALO 消除） | 0（编译期固定大小分配） | ~4KB 栈 | 0 | 1 次（shared state） |
| **栈深度控制** | 对称转移 O(1) | 编译期状态机 | 动态扩栈 | 正常栈 | 正常栈 |
| **线程切换** | 手动（await_suspend 中安排） | 手动（waker） | 自动（运行时） | 手动 | OS 线程池 |
| **学习曲线** | 极高（5+ 个新概念） | 中高 | 低 | 低 | 中 |

### 7.4 设计取舍：为什么 C++ 不提供"安全的协程"

C++ 委员会做出了一个有意的选择：**提供底层构建块，让库作者构建安全的抽象**，而不是提供一个开箱即用的 `async`/`await` 运行时。

**取舍分析：**

| 方面 | 好处 | 代价 |
|------|------|------|
| **无运行时** | 零开销；可用于嵌入式；不与特定 I/O 模型绑定 | 每个库都重新发明 task、调度器、异步 I/O |
| **自定义分配** | `operator new` 可重载；Arena 分配；PMR | 初学者直接踩进分配陷阱 |
| **类型擦除的 handle** | `coroutine_handle<>` 可用于通用调度器 | 丢失了类型信息，需要手动类型恢复 |
| **编译器变换而非库实现** | 不依赖 RTTI/异常启用；二进制兼容性好 | 调试困难；错误信息晦涩 |

**结果：** C++ 协程的"不安全"不是 bug，而是 feature——它给了你控制一切的自由，包括摧毁一切的权力。

### 7.5 WG21 的补救方向

| 提案 | 解决的问题 | 状态 |
|------|-----------|------|
| P1662R0: async RAII | 协程中 RAII 资源的安全释放 | 探索中 |
| P2300: `std::execution` (Senders/Receivers) | 统一异步模型，结构化并发 | C++26 已采纳 |
| P2477R3: 控制协程消除 | 允许程序员保证/禁止 HALO | 探索中 |
| P1745R0: `co_resource` | 基于协程的 RAII 资源管理 | 探索中 |

**P2300 的重要性：** `std::execution` 的 sender/receiver 模型本质上是用**编译期组合**替代运行时协程，资源管理由 sender 的连接和销毁保证。如果 sender 的析构函数取消未完成的异步操作并释放资源，RAII 在异步场景中重新变得安全。但这是 C++26 的事。

### 7.6 实战最佳实践清单

1. **永远用 RAII 包装 `coroutine_handle`** — 别让裸 handle 逃逸到类之外
2. **final_suspend 用 `suspend_always`** — 让调用者控制帧的销毁时机，别让帧自动销毁
3. **`co_await` 前释放锁** — 用作用域块 `{ lock...; }` 包裹临界区
4. **按值传递参数** — 除非明确保证引用的生命周期长于协程
5. **用 `unique_ptr` / `shared_ptr` 管理协程中动态分配的资源** — 不要在协程中 `new` 裸指针
6. **在 task 析构函数中调 `handle.destroy()`** — 让协程帧的生命周期绑定到 task 的 RAII
7. **异常路径必须清理** — 如果 `unhandled_exception` 中存储了异常，task 的析构/result 访问必须处理
8. **启用 ASan/TSan** — 协程的悬空引用和线程安全问题非常难以肉眼发现
9. **对称转移优先** — `await_suspend` 返回 `coroutine_handle<>` 来避免栈帧积累
10. **不要假设 HALO** — 永远把协程帧当作堆分配来对待，除非你在做 perf 优化

---

## 常见面试题

**Q1: `co_await` 暂停时，协程的局部变量会发生什么？它们会被析构吗？**

不会。局部变量存储在协程帧（堆或栈上的一块内存）中。`co_await` 暂停时，已构造的局部变量保持存活，未被析构。只有当协程帧被 `destroy()` 或协程正常执行到作用域结束时，它们才会被析构。

**Q2: 协程中可以使用 `std::lock_guard` 吗？**

技术上可以，但极不推荐。`co_await` 暂停时锁仍然被持有——这意味着锁定区间跨越了暂停点，而暂停时长不可预测（可能永远不恢复）。其他需要该锁的协程将被永久阻塞。正确做法是在 `co_await` 之前释放锁，恢复后重新获取。

**Q3: `final_suspend` 返回 `suspend_never` 和 `suspend_always` 的区别是什么？**

`suspend_never`：协程执行完毕后立即销毁帧，调用者持有的 `coroutine_handle` 变为悬空。适合不关心返回值的"发射后不管"（fire-and-forget）协程。
`suspend_always`：协程结束后保持帧存活，等待调用者显式调用 `destroy()`。适合需要获取返回值的协程（调用者先读结果，再销毁帧）。最常见。

**Q4: 如何避免协程帧泄漏？**

用 RAII 类型（如 `cppcoro::task`）包装 `coroutine_handle`，在其析构函数中调用 `handle.destroy()`。确保这个 RAII 包装类型本身也是 RAII 管理的（栈变量、`unique_ptr`、容器元素）。

**Q5: 解释对称转移（symmetric transfer）及其优势。**

对称转移允许一个协程在暂停时直接将控制权**转移到**另一个协程，而不经过调度器。`await_suspend` 返回 `coroutine_handle<>` 时触发。优势：不增加调用栈深度（O(1) 栈），减少调度器开销，对于协程间的链式调用（A 等待 B，B 等待 C）尤为重要。

---

## 延伸主题

- **P2300 `std::execution`**: C++26 的 sender/receiver 异步模型 — 编译期组合替代运行时协程
- **Boost.Asio 协程集成**: 实战中最成熟的 C++ 异步 I/O + 协程方案
- **Rust `async`/`await`**: 零分配编译器变换，对比 C++ 协程的设计差异（Pin、Waker、编译期状态机）
- **io_uring + 协程**: Linux 高性能异步 I/O 与 C++ 协程的结合
- **游戏引擎中的 job system + 协程**: 如何将协程用作工作窃取线程池的任务单元
- **[栈展开与异常安全](./stack-unwinding.md)**: 协程中的异常如何在暂停点间传播
