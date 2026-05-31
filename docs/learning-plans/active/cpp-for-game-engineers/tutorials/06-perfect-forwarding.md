# 06 — 完美转发与万能引用

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 05-移动语义与值类别精讲

---

## 1. 概念讲解

### 为什么需要完美转发

假设你要写一个日志包装器——在调用真正的工作函数前后打日志：

```cpp
template<typename F, typename Arg>
void log_and_call(F&& f, Arg&& arg) {
    log("before");
    f(arg);   // ← 问题：arg 永远是左值！
    log("after");
}
```

无论调用方传入左值还是右值，`arg` 作为具名参数，在函数体内**永远是左值**。这意味着：(1) 右值参数丢失移动优化，被迫拷贝；(2) 接受右值引用的被调用函数完全无法匹配。

**完美转发**解决的就是这个问题：编写一个函数模板，接收任意值类别的参数，然后"原封不动"地把参数的值类别转发给另一个函数。

### 万能引用 vs 右值引用

这是 C++ 中最容易混淆的概念之一。两者的语法形式完全相同（`T&&`），但含义截然不同：

```cpp
// 右值引用（非模板上下文，T 是具体类型）
void take(int&& x);       // x 只绑定右值

// 万能引用（模板上下文，T 被推导）
template<typename T>
void relay(T&& arg);      // arg 可以绑定左值或右值
```

**万能引用的精确条件（两者必须同时满足）：**

1. **`T` 是被推导的类型**——模板参数推导或 `auto&&`
2. **形式正好是 `T&&`**——没有 `const` 修饰、不是 `vector<T>&&` 之类的嵌套形式

```cpp
template<typename T> void f(T&& arg);       // ✅ 万能引用
auto&& x = expr;                             // ✅ auto&& = 万能引用
template<typename T> void g(const T&& arg); // ❌ const 限定 → 纯右值引用
template<typename T> void h(vector<T>&& v); // ❌ 不是 T&& → 纯右值引用
void k(int&& x);                             // ❌ 没有推导 → 纯右值引用
```

### 引用折叠规则

万能引用之所以"万能"，核心在于引用折叠。当模板推导出 `T` 后，`T&&` 中的两个 `&` 会发生折叠：

| `T` 被推导为 | `T&&` 的折叠结果 | 实际参数类型 |
|:------------|:---------------|:-----------|
| `int`       | `int&&`        | 右值引用   |
| `int&`      | `int& &&` → `int&` | 左值引用   |
| `int&&`     | `int&& &&` → `int&&` | 右值引用   |
| `const int&`| `const int& &&` → `const int&` | const 左值引用 |

**规则**：`&` 胜出。四个组合中，只要有一个 `&`，结果就是 `&`；全是 `&&` 才是 `&&`。

### 模板推导规则（关键）

当函数参数是 `T&&`（万能引用形式）：

```cpp
template<typename T>
void f(T&& arg);

int        x = 1;
const int cx = 2;

f(x);             // 实参是左值 int
                  // → T 推导为 int&，arg 类型 = int&（折叠：int& && → int&）

f(cx);            // 实参是 const 左值
                  // → T 推导为 const int&，arg 类型 = const int&

f(42);            // 实参是右值 int
                  // → T 推导为 int，arg 类型 = int&&

f(std::move(x));  // 实参是右值 int
                  // → T 推导为 int，arg 类型 = int&&
```

**核心规则**：实参是左值 → `T` 被推导为左值引用类型；实参是右值 → `T` 被推导为非引用类型。

### std::forward 的工作原理

`std::forward<T>` 就是一个**条件转换**——根据 `T` 中是否包含引用来决定 cast 成什么：

```cpp
// 简化实现（标准库的真实实现更复杂，但本质相同）
template<class T>
constexpr T&& forward(std::remove_reference_t<T>& t) noexcept {
    return static_cast<T&&>(t);
}
```

当 `T = int` 时：`static_cast<int&&>(t)` → 返回右值引用
当 `T = int&` 时：`static_cast<int& &&>(t)` = `static_cast<int&>(t)` → 返回左值引用

**本质**：`std::forward<T>` = `static_cast<T&&>(arg)` + 引用折叠。`T` 中的引用性被保留并应用到结果类型上。

### 完美转发惯用法

```cpp
// 单参数版本
template<typename T>
void wrapper(T&& arg) {
    callee(std::forward<T>(arg));   // 注意：forward<T>，不是 forward<decltype(arg)>
}

// 变参版本（C++11）
template<typename... Args>
void wrapper(Args&&... args) {
    callee(std::forward<Args>(args)...);
}

// 泛型 lambda 版本（C++14）
auto wrapper = [](auto&& arg) {
    return callee(std::forward<decltype(arg)>(arg));
};
```

**关键细节**：`std::forward<T>` 的模板参数 `T` 必须来自外部推导，**不能**用 `decltype(arg)` 替代——因为在函数体内 `arg` 是具名左值，`decltype(arg)` 永远是 `T&` 或 `T`（取决于 `T`），而不是 `T&&`。

### std::forward vs std::move

| | `std::move` | `std::forward<T>` |
|:--|:-----------|:-----------------|
| 语义 | "我放弃这个值，你可以搬走" | "我不改变值类别，原样传递" |
| 结果 | 无条件返回右值引用 | 条件返回（取决于 T） |
| 使用场景 | 你拥有该值，且不再需要它 | 你要把参数转发给下游 |
| 典型调用 | `std::move(local_var)` | `std::forward<T>(templated_arg)` |

**黄金法则**：`std::move` 用于具名对象（你拥有它），`std::forward` 用于转发函数参数（你只是中间人）。

### 引擎中的核心场景

**1. emplace 操作**：STL 容器的 `emplace_back` 正是完美转发的典范——将构造参数原封不动转发给元素类型的构造函数，避免临时对象：

```cpp
// std::vector 内部类似这样的实现
template<typename... Args>
void emplace_back(Args&&... args) {
    // 在预留空间上构造，完美转发所有参数
    ::new (end_ptr) T(std::forward<Args>(args)...);
}
```

**2. 命令队列**：引擎的任务/命令系统需要存储任意类型的函数调用，稍后在特定时机（主线程、渲染线程）执行。完美转发让命令的参数在延迟调用时仍保留值类别。

**3. 事件调度**：事件系统收到事件后，需要转发给所有监听者。`dispatch<E>(std::forward<E>(event))` 保证移动语义传递。

**4. 工厂函数**：`std::make_unique`、`std::make_shared` 都是完美转发的应用。

### 转发失败场景

完美转发不是万能的，以下场景会失败：

| 场景 | 原因 | 解决方案 |
|:-----|:-----|:--------|
| **花括号初始化器** `f({1,2,3})` | `{}` 不是表达式，无法推导模板参数 | 先用 `auto x = {1,2,3}` 再转发 |
| **`0` 或 `NULL` 作为空指针** | 推导为 `int`，不是指针类型 | 使用 `nullptr` |
| **位域** | 不能绑定到引用（没有地址） | 先拷贝到局部变量再转发 |
| **重载函数名** | 仅函数名没有类型信息 | 显式 cast 为函数指针类型 |

### noexcept 转发

如果你知道转发链路上的所有操作都是 `noexcept` 的，可以标记转发函数为 `noexcept`。这在引擎的 Job System 中很重要——任务执行函数被挪到无异常保证的上下文中：

```cpp
template<typename F, typename... Args>
decltype(auto) noexcept_invoke(F&& f, Args&&... args) noexcept(
    noexcept(std::forward<F>(f)(std::forward<Args>(args)...))
) {
    return std::forward<F>(f)(std::forward<Args>(args)...);
}
```

---

## 2. 代码示例

### 示例 1: 完整的引擎事件调度系统

```cpp
// compile: g++ -std=c++20 -O2 event_dispatch.cpp -o event_dispatch
#include <iostream>
#include <string>
#include <vector>
#include <functional>
#include <memory>
#include <chrono>

// ============ 事件基类 ============
struct Event {
    std::string name;
    virtual ~Event() = default;
};

struct MouseEvent : Event {
    float x, y;
    MouseEvent(float x_, float y_) : Event{"MouseMove"}, x(x_), y(y_) {}
};

struct KeyEvent : Event {
    int keycode;
    explicit KeyEvent(int k) : Event{"KeyPress"}, keycode(k) {}
};

// ============ 完美转发的事件分发器 ============
class EventDispatcher {
public:
    using Handler = std::function<void(const Event&)>;

    void subscribe(std::string event_name, Handler h) {
        handlers_.push_back({std::move(event_name), std::move(h)});
    }

    // 核心：完美转发事件对象
    template<typename E>
    void dispatch(E&& event) {
        std::cout << "[Dispatch] " << event.name << std::endl;
        for (auto& [name, handler] : handlers_) {
            if (name == event.name)
                handler(std::forward<E>(event));  // 保留值类别
        }
    }

    // 变参完美转发：延迟构造事件
    template<typename E, typename... Args>
    void emit(Args&&... args) {
        // 直接在 dispatch 中构造，零拷贝
        dispatch(E(std::forward<Args>(args)...));
    }

private:
    std::vector<std::pair<std::string, Handler>> handlers_;
};

// ============ 转发日志包装器 ============
template<typename F, typename... Args>
decltype(auto) profiled_call(const char* tag, F&& f, Args&&... args) {
    auto start = std::chrono::high_resolution_clock::now();

    // 关键：使用 std::forward 保留每个参数的值类别
    decltype(auto) result = std::forward<F>(f)(std::forward<Args>(args)...);

    auto end = std::chrono::high_resolution_clock::now();
    auto us = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
    std::cout << "[Profile] " << tag << " took " << us << "us\n";
    return result;
}

// ============ 命令队列：存储延迟调用 ============
class CommandQueue {
public:
    // 核心：用完美转发捕获任意可调用对象及其参数
    template<typename F, typename... Args>
    void enqueue(F&& f, Args&&... args) {
        // 用 lambda 捕获：对 f 和 args 做完美转发捕获
        commands_.push_back(
            [f = std::forward<F>(f),
             ... args = std::forward<Args>(args)]() mutable {
                f(std::move(args)...);
            }
        );
    }

    void execute_all() {
        for (auto& cmd : commands_)
            cmd();
        commands_.clear();
    }

private:
    std::vector<std::function<void()>> commands_;
};

// ============ 演示 ============
int main() {
    // --- 事件分发 ---
    EventDispatcher ed;
    ed.subscribe("MouseMove", [](const Event& e) {
        auto& me = static_cast<const MouseEvent&>(e);
        std::cout << "  Handler 1: mouse at (" << me.x << ", " << me.y << ")\n";
    });
    ed.subscribe("KeyPress", [](const Event& e) {
        auto& ke = static_cast<const KeyEvent&>(e);
        std::cout << "  Handler 2: key " << ke.keycode << "\n";
    });

    // 直接分发
    ed.dispatch(MouseEvent{100.0f, 200.0f});       // 右值
    MouseEvent me{300.0f, 400.0f};
    ed.dispatch(me);                                 // 左值 — 不移动

    // 延迟构造 + 完美转发
    ed.emit<KeyEvent>(42);
    ed.emit<MouseEvent>(50.0f, 60.0f);

    // --- 性能包装 ---
    auto add = [](int a, int b) { return a + b; };
    int sum = profiled_call("add", add, 3, 4);
    std::cout << "sum = " << sum << "\n";

    // --- 命令队列 ---
    CommandQueue cq;
    cq.enqueue([](int x) { std::cout << "Command: " << x << "\n"; }, 42);
    std::string msg = "hello";
    cq.enqueue([](const std::string& s) { std::cout << "Command: " << s << "\n"; }, msg);
    cq.enqueue([](std::string&& s) { std::cout << "Command moved: " << s << "\n"; },
               std::string("temp string"));
    cq.execute_all();

    return 0;
}
```

### 示例 2: emplace_back vs push_back 内部机制对比

```cpp
// compile: g++ -std=c++20 -O2 emplace_bench.cpp -o emplace_bench
#include <iostream>
#include <vector>
#include <string>
#include <chrono>

struct Particle {
    float x, y, z;
    float vx, vy, vz;
    float lifetime;
    std::string name;

    Particle(float x_, float y_, float z_,
             float vx_, float vy_, float vz_,
             float lt_, std::string n)
        : x(x_), y(y_), z(z_), vx(vx_), vy(vy_), vz(vz_), lifetime(lt_), name(std::move(n)) {}

    // 追踪构造/析构
    Particle(const Particle& other) : x(other.x), y(other.y), z(other.z),
        vx(other.vx), vy(other.vy), vz(other.vz),
        lifetime(other.lifetime), name(other.name) {
        std::cout << "  [COPY] " << name << "\n";
    }
    Particle(Particle&& other) noexcept
        : x(other.x), y(other.y), z(other.z),
          vx(other.vx), vy(other.vy), vz(other.vz),
          lifetime(other.lifetime), name(std::move(other.name)) {
        std::cout << "  [MOVE] " << name << "\n";
    }
};

int main() {
    constexpr int N = 1'000'000;

    // push_back：需要先构造临时对象，再移动（或拷贝）进容器
    {
        std::cout << "=== push_back ===\n";
        std::vector<Particle> particles;
        particles.reserve(N);
        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < 5; ++i) {  // 只演示 5 次避免刷屏
            // 先构造临时对象，然后 push_back 内部移动
            particles.push_back(Particle(1.0f, 2.0f, 3.0f, 0.1f, 0.2f, 0.3f, 5.0f, "p" + std::to_string(i)));
        }
        auto end = std::chrono::high_resolution_clock::now();
        std::cout << "  5 iterations done.\n";
    }

    // emplace_back：参数被完美转发，直接在容器内存上构造
    {
        std::cout << "=== emplace_back ===\n";
        std::vector<Particle> particles;
        particles.reserve(N);
        for (int i = 0; i < 5; ++i) {
            // 参数完美转发 → 直接在 vector 内存空间上调用构造函数
            // 零临时对象！
            particles.emplace_back(1.0f, 2.0f, 3.0f, 0.1f, 0.2f, 0.3f, 5.0f,
                                   "p" + std::to_string(i));
        }
        std::cout << "  5 iterations done — no COPY/MOVE output!\n";
    }

    return 0;
}
```

### 示例 3: 线程安全命令队列（完美转发 + move_only 类型）

```cpp
// compile: g++ -std=c++20 -O2 thread_command_queue.cpp -o thread_command_queue -pthread
#include <iostream>
#include <vector>
#include <functional>
#include <mutex>
#include <memory>
#include <thread>

// 引擎中常用的 move-only GPU 命令句柄
struct RenderCommand {
    int id;
    std::unique_ptr<float[]> data;  // move-only

    RenderCommand(int i, size_t sz) : id(i), data(std::make_unique<float[]>(sz)) {}
    RenderCommand(RenderCommand&&) = default;
    RenderCommand& operator=(RenderCommand&&) = default;

    void execute() const {
        std::cout << "  RenderCmd #" << id << " (data[0]=" << data[0] << ")\n";
    }
};

// 线程安全命令队列 — 完美转发核心
class ThreadSafeCommandQueue {
public:
    template<typename F, typename... Args>
    void enqueue(F&& f, Args&&... args) {
        // 完美转发捕获 move-only 类型
        auto task = [f = std::forward<F>(f),
                     ... args = std::forward<Args>(args)]() mutable {
            f(std::move(args)...);
        };
        std::lock_guard<std::mutex> lock(mutex_);
        queue_.push_back(std::move(task));
    }

    void execute_all() {
        std::vector<std::function<void()>> local;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            local.swap(queue_);
        }
        for (auto& task : local)
            task();
    }

private:
    std::mutex mutex_;
    std::vector<std::function<void()>> queue_;
};

int main() {
    ThreadSafeCommandQueue cq;

    // 入队 move-only 对象 — 完美转发保证不拷贝
    cq.enqueue([](RenderCommand&& cmd) { cmd.execute(); },
               RenderCommand{1, 16});

    cq.enqueue([](std::unique_ptr<float[]>&& data) {
        std::cout << "  Data[0] = " << data[0] << "\n";
    }, std::make_unique<float[]>(8));

    cq.execute_all();

    // 多线程演示
    std::thread producer([&]() {
        for (int i = 0; i < 5; ++i) {
            cq.enqueue([](int id) {
                std::cout << "  Thread cmd #" << id << "\n";
            }, i);
        }
    });

    producer.join();
    cq.execute_all();

    return 0;
}
```

---

## 3. 练习

### 练习 1: 识别转发 Bug（必做）

下面代码有 3 个与转发相关的错误。找出并修复它们，解释每个错误会导致什么问题。

```cpp
template<typename T>
void bad_wrapper(T&& arg) {
    log("before");
    target(std::move(arg));  // Bug 1
    log("after");
}

template<typename T>
void double_forward(T&& arg) {
    sink1(std::forward<T>(arg));
    sink2(std::forward<T>(arg));  // Bug 2
}

template<typename... Args>
auto bad_lambda_capture(Args&&... args) {
    return [args...]() {  // Bug 3
        use(args...);
    };
}
```

**要求**：写出修复后的正确版本，并用注释说明每个 Bug 的后果。验证：用 `int x = 5; bad_wrapper(x);` 测试你的修复是否正确保留了 `x` 的值。

### 练习 2: 实现一个泛型工厂函数（必做）

实现一个 `make_engine_resource<Resource, Allocator>(Allocator& alloc, Args&&... args)` 函数，它：
1. 使用给定的分配器分配内存
2. 在该内存上完美转发构造 `Resource` 对象
3. 返回一个 RAII 句柄（可以是 `unique_ptr` + 自定义删除器，或自定义 `ResourceHandle` 类）
4. 句柄析构时调用析构函数并归还内存给分配器

**要求**：
- 支持 move-only 类型作为构造参数
- 使用 placement new + 完美转发
- 如果 `Resource` 的构造函数抛异常，内存必须被正确归还

### 练习 3: 实现一个转发性能计数器（可选挑战）

实现 `template<typename F> auto count_copies(F&& f)` —— 一个包装器，它：
1. 内部维护几个计数器：总转发次数、导致拷贝的次数、导致移动的次数
2. 对传入的每个参数：如果 `std::forward` 导致拷贝则计数 `copies`，如果导致移动则计数 `moves`
3. 需要区分拷贝和移动——这需要一些元编程技巧

**提示**：可以用 `std::is_lvalue_reference_v<T>` 配合 `std::is_rvalue_reference_v<decltype(std::forward<T>(arg))>` 在编译期检测。用 `if constexpr` 选择不同分支。

---

## 4. 扩展阅读

- **深度探索**: `docs/deep-dives/cpp-perfect-forwarding.md` — 796 行的完整分析，涵盖所有 7 层
- **cppreference**: [std::forward](https://en.cppreference.com/w/cpp/utility/forward), [Reference collapsing](https://en.cppreference.com/w/cpp/language/reference)
- **Scott Meyers**: *Effective Modern C++*, Item 23-30 — 万能引用与完美转发的权威论述
- **C++ 标准提案**: [N4164](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2014/n4164.pdf) (forwarding references 的正式命名)
- **引擎源码参考**: Unreal Engine 的 `TTypeFundamentals.h` 中 `MoveTemp` / `Forward` 实现

---

## 常见陷阱

### 陷阱 1: 用 `std::move` 代替 `std::forward`

```cpp
template<typename T>
void wrapper(T&& arg) {
    sink(std::move(arg));  // 危险！
}

int x = 42;
wrapper(x);   // x 被悄然移动！调用方完全不知道
// 之后访问 x → 未定义行为（取决于 sink 做了什么）
```

**原因**：`std::move` 无条件返回右值引用。左值参数也会被强制转为右值。调用方传入左值时，预期的是"只读/拷贝"，结果却被移动了。

**正确做法**：总是用 `std::forward<T>(arg)` 转发万能引用参数。`std::move` 只用于你拥有所有权的具名对象。

### 陷阱 2: 对同一个转发参数多次调用 `std::forward`

```cpp
template<typename T>
void bad(T&& arg) {
    sink1(std::forward<T>(arg));
    sink2(std::forward<T>(arg));   // 如果 T 非引用（右值），arg 已被移动
}
```

**原因**：当 `T = SomeType`（右值转发）时，第一次 `forward` 将 `arg` 转为右值引用，`sink1` 可能移动了它。第二次 `forward` 转发的就是"已被移动"的对象。

**正确做法**：
```cpp
template<typename T>
void good(T&& arg) {
    sink1(arg);                     // 先用左值方式使用
    sink2(std::forward<T>(arg));    // 只有最后一次才转发
}
```

### 陷阱 3: `const T&&` 不是万能引用

```cpp
template<typename T>
void bad_func(const T&& arg);  // 这不是万能引用！只接受右值
```

**原因**：万能引用的形式必须是裸 `T&&`。加了 `const` 后，模板推导仍然发生，但 `const` 破坏了引用折叠中的"左值路径"。`const T&&` 永远只能绑定到右值。

**影响**：你写了一个模板函数，以为它能接受左值和右值，实际上它只接受右值。所有传入左值的调用都会编译失败。

### 陷阱 4: 转发后继续使用参数（且 T 被推导为非引用）

```cpp
template<typename T>
void bad(T&& arg) {
    sink(std::forward<T>(arg));
    std::cout << arg << "\n";   // arg 可能已被移动！
}
```

如果 `T` 被推导为非引用类型（即原始实参是右值），`forward` 后的 `arg` 处于"有效但未指定"状态。后续访问是合法的（对象仍然存在），但值是未指定的——引擎场景中这会导致难以调试的视觉闪烁或物理异常。

### 陷阱 5: 忽略 `decltype(auto)` 导致返回值丢失引用

```cpp
template<typename T>
auto bad_return(T&& arg) {         // auto 剥去引用 → 返回值类型是 T（非引用）
    return std::forward<T>(arg);   // 可能发生拷贝！
}

template<typename T>
decltype(auto) good_return(T&& arg) {  // decltype(auto) 保留引用性
    return std::forward<T>(arg);
}
```

在引擎的 getter/工厂函数中，这个错误会导致意外的深拷贝——例如在帧循环中每次获取资源都拷贝整个结构体，直接吃掉 16.6ms 预算。
