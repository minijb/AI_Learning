# RAII 与资源管理深度解析

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 02-object-lifetime-memory-layout（对象生命周期与内存布局）

---

## 1. 概念讲解

### 1.1 RAII 的哲学：构造=获取，析构=释放

RAII（Resource Acquisition Is Initialization）是 C++ 最核心的惯用法，也是 C++ 区别于所有 GC 语言的根本特性。它的本质非常简单：**将资源的生命周期绑定到对象的生命周期**。

```
┌──────────────────────────────────────────┐
│            RAII 不变量                    │
│                                          │
│  对象构造完成 → 资源必定已获取            │
│  对象析构完成 → 资源必定已释放            │
│  异常发生    → 栈展开 → 析构 → 资源释放  │
│                                          │
│  这三个保证在任何条件下都成立。            │
└──────────────────────────────────────────┘
```

类比：想象你去借一把极其昂贵的电钻。你不用的时候它必须归还，否则整个工地的施工都会停滞。RAII 的做法是：**把归还义务焊在借用人身上**。你拿到电钻的那一刻，归还义务就激活；你离开（离开作用域/异常/提前返回）的时刻，电钻自动归还。不需要"记得"——物理上不可能忘记。

### 1.2 游戏引擎为什么禁用异常但仍然使用 RAII？

许多 AAA 引擎（UE、idTech、Frostbite）禁用 C++ 异常，但 RAII 仍然无处不在。这看起来矛盾——RAII 不是依赖栈展开来处理异常吗？

**实际上，RAII 的核心是"确定性析构"，异常只是触发确定性析构的机制之一。** 即使没有异常，return、break、continue、goto、作用域结束都会触发析构。引擎禁用异常的原因是异常本身（动态栈展开、类型匹配、堆分配）的性能不可预测性，而非 RAII 有问题。

```cpp
// 这段代码在任何控制流下都不会泄漏资源（有异常或无异常）
void processFrame() {
    GPUContext ctx;       // 构造：记录 GPU 状态
    ScopedLock lock(mtx); // 构造：加锁
    auto* buf = ctx.mapBuffer(vbo);  // 映射 GPU 缓冲

    renderScene();        // ← 如果这里 return/throw/崩溃？

    ctx.unmapBuffer(vbo); // 如果提前退出，这行不会执行
    // lock 析构 → 解锁     ← 但这三行一定会执行
    // ctx 析构 → 恢复状态  ←
}  // buf 是裸指针，它的"资源"由 ctx 管理 ←
```

### 1.3 引擎中的 RAII 模式分类

| 资源类型 | RAII 封装 | 构造做什么 | 析构做什么 |
|---------|-----------|-----------|-----------|
| **GPU 缓冲** | `GPUBuffer` | `glGenBuffers` / `vkCreateBuffer` | `glDeleteBuffers` / `vkDestroyBuffer` |
| **GPU 纹理** | `GPUTexture` | 创建纹理 + 上传数据 | 删除纹理 + 释放 staging |
| **锁** | `ScopedLock` | `mutex.lock()` | `mutex.unlock()` |
| **文件** | `FileHandle` | `fopen` / `CreateFile` | `fclose` / `CloseHandle` |
| **线程** | `ScopedThread` | 构造 std::thread | 析构时 join 或 detach |
| **Profiler Zone** | `ProfilerScope` | 记录时间戳 + 区域名 | 记录结束时间戳 |
| **帧分配器** | `FrameAllocatorScope` | 保存当前偏移 | 回退偏移 + 析构所有对象 |
| **数据库事务** | `Transaction` | BEGIN TRANSACTION | COMMIT 或 ROLLBACK |
| **引用计数对象** | `RefCountPtr` | `IncRef()` | `DecRef() → 可能 delete` |

### 1.4 Scope Guard 模式：非 RAII API 的外挂

许多 C API（OpenGL、Vulkan、POSIX）不提供 RAII 接口。Scope Guard 给这些 C API 穿上 RAII 的外衣：

```cpp
// 概念：一个可调用对象的 RAII 包装
// 析构时自动执行"清理"逻辑
template<typename F>
class ScopeGuard {
    F f_;
    bool active_ = true;
public:
    explicit ScopeGuard(F f) : f_(std::move(f)) {}
    ~ScopeGuard() { if (active_) f_(); }
    void dismiss() { active_ = false; }
    ScopeGuard(const ScopeGuard&) = delete;
    ScopeGuard& operator=(const ScopeGuard&) = delete;
};
```

**引擎典型用法：**
```cpp
void renderFrame(VkCommandBuffer cmd) {
    vkBeginCommandBuffer(cmd, &beginInfo);
    ScopeGuard endCmd([cmd]{ vkEndCommandBuffer(cmd); });

    vkCmdBeginRenderPass(cmd, &renderPassInfo, ...);
    ScopeGuard endPass([cmd]{ vkCmdEndRenderPass(cmd); });

    // ...大量渲染命令...

    // 无论从哪里返回，endPass 先析构（上后下先），endCmd 后析构
    // 保证 Vulkan 命令序列的正确嵌套
}
```

### 1.5 二阶段初始化：当构造函数不能失败

引擎中许多资源的创建可能失败（GPU 内存不足、文件不存在、网络超时）。C++ 构造函数不能返回错误（没有 `Result<T, E>` 返回值）。对此，引擎有三种策略：

**策略 1：工厂函数 + `std::optional` / `std::expected`（C++23）**
```cpp
std::optional<GPUTexture> GPUTexture::create(const char* path) {
    GLuint id = 0;
    glGenTextures(1, &id);
    if (!loadFromFile(id, path)) {
        glDeleteTextures(1, &id);
        return std::nullopt;  // 构造失败，不留垃圾
    }
    return GPUTexture{id};    // 私有构造函数 + 友元工厂
}
```

**策略 2：默认构造 + `init()` / `shutdown()`（传统引擎风格）**
```cpp
class PhysicsWorld {
    bool initialized_ = false;
public:
    PhysicsWorld() = default;  // 空对象，不分配

    bool init(const PhysicsConfig& cfg) {
        // 可能失败的操作都在这里
        solver_ = createSolver(cfg);
        if (!solver_) return false;
        initialized_ = true;
        return true;
    }

    ~PhysicsWorld() {
        if (initialized_) shutdown();
    }

    void shutdown() {
        destroySolver(solver_);
        initialized_ = false;
    }
};
```
这种模式要求调用方遵守"先 init 后使用"的契约。`std::optional` 更安全但相对新。

**策略 3：构造函数参数完整传递，析构无条件清理（推荐）**
```cpp
class FileMapping {
    void* ptr_ = nullptr;
    size_t size_ = 0;
public:
    FileMapping(const char* path)
        : ptr_(mmap_file(path, size_))  // 失败返回 nullptr
    {
        // 不抛异常：用 IsValid() 检查
    }
    ~FileMapping() {
        if (ptr_) munmap_file(ptr_, size_);
    }
    bool IsValid() const { return ptr_ != nullptr; }
};
```

### 1.6 `noexcept` 移动与 RAII 的契约

这是引擎代码中最重要的交互之一：**移动构造/赋值必须标记为 `noexcept`**。

原因：`std::vector` 扩容时，需要将元素从旧缓冲区移动到新缓冲区。如果移动操作可能抛出异常，`vector` 会选择**拷贝**而非**移动**来保证异常安全——意味着你的 GPU 纹理缓冲在扩容时会被逐元素拷贝（可能调用被删除的拷贝构造 → 编译失败）。

```cpp
class GPUBuffer {
    GLuint id_ = 0;
public:
    // ✅ 标记 noexcept: vector 扩容时使用移动（高效）
    GPUBuffer(GPUBuffer&& other) noexcept : id_(other.id_) {
        other.id_ = 0;
    }

    // ❌ 不标记 noexcept: vector 扩容时会尝试拷贝（可能 =delete → 编译失败）
    // GPUBuffer(GPUBuffer&& other) : id_(other.id_) { ... }

    GPUBuffer(const GPUBuffer&) = delete;  // GPU 资源不可拷贝
};
```

### 1.7 RAII vs GC vs 手动管理

| 方面 | RAII (C++) | GC (C#/Java/Go) | 手动 new/delete (C) |
|------|-----------|-----------------|---------------------|
| **确定性** | 精确到行（作用域结束） | STW 时回收，不可预测 | 精确到行 |
| **异常安全** | 自动（栈展开） | 需要 try-finally / using | 需要手动 cleanup |
| **性能** | 零开销（编译期决定） | GC 开销（STW、并发标记） | 零开销 |
| **泄漏风险** | 极低（除非循环引用） | 低（除非忘记注销引用） | 极高 |
| **内存碎片** | 可控（自定义分配器） | 压缩 GC 减少碎片 | 取决于 malloc |
| **适用场景** | 游戏引擎（帧预算严格） | 业务应用（开发效率优先） | 嵌入式 / 内核 |

**引擎选择 RAII 的决定性原因：确定性时序。** 在 16.6ms 的帧预算内，你不能承受 GC 在渲染循环中间暂停 3ms 来回收内存。RAII 让你精确控制每个字节的生命周期——在帧开始时分配，在帧结束时统一释放。

---

## 2. 代码示例

### 示例 1：完整的 GPU 缓冲区 RAII 包装

```cpp
// gpu_buffer_raii.cpp — OpenGL 缓冲区 RAII 包装
// 编译: g++ -std=c++20 -O2 gpu_buffer_raii.cpp -o gpu_buffer_raii
// 注意: 需要 OpenGL 上下文才能实际运行；此处演示 API 设计

#include <iostream>
#include <vector>
#include <utility>     // std::exchange, std::move
#include <cstdint>

// 模拟 OpenGL API（实际使用时替换为真实 gl* 函数）
namespace GL {
    using uint = unsigned int;
    inline void GenBuffers(int n, uint* ids) {
        static uint nextId = 1;
        for (int i = 0; i < n; ++i) ids[i] = nextId++;
        std::cout << "  GL: GenBuffers(" << n << ") → id=" << ids[0] << '\n';
    }
    inline void DeleteBuffers(int n, const uint* ids) {
        std::cout << "  GL: DeleteBuffers(" << n << ") → id=" << ids[0] << '\n';
    }
    inline void BindBuffer(uint target, uint id) {
        std::cout << "  GL: BindBuffer(target=" << target << ", id=" << id << ")\n";
    }
    inline void BufferData(uint target, size_t size, const void* data, uint usage) {
        std::cout << "  GL: BufferData(size=" << size << ")\n";
    }
}

// ===== RAII GPU 缓冲区封装 =====
class GPUBuffer {
public:
    // 工厂函数：创建并上传数据
    static GPUBuffer create(const void* data, size_t size) {
        GL::uint id = 0;
        GL::GenBuffers(1, &id);
        GL::BindBuffer(0x8892, id);  // GL_ARRAY_BUFFER
        GL::BufferData(0x8892, size, data, 0x88E4);  // GL_STATIC_DRAW
        return GPUBuffer(id);
    }

    // 析构：释放 GPU 资源
    ~GPUBuffer() noexcept {
        if (id_ != 0) {
            GL::DeleteBuffers(1, &id_);
        }
    }

    // 移动（noexcept——必须）
    GPUBuffer(GPUBuffer&& other) noexcept : id_(other.id_) {
        other.id_ = 0;
    }

    GPUBuffer& operator=(GPUBuffer&& other) noexcept {
        if (this != &other) {
            // 先释放自己的旧资源，再接管新资源
            if (id_ != 0) GL::DeleteBuffers(1, &id_);
            id_ = other.id_;
            other.id_ = 0;
        }
        return *this;
    }

    // 禁止拷贝（GPU 资源不可拷贝）
    GPUBuffer(const GPUBuffer&) = delete;
    GPUBuffer& operator=(const GPUBuffer&) = delete;

    // 访问原始句柄（用于 OpenGL API 调用）
    GL::uint id() const noexcept { return id_; }
    bool valid() const noexcept { return id_ != 0; }

private:
    explicit GPUBuffer(GL::uint id) noexcept : id_(id) {}
    GL::uint id_ = 0;
};

// ===== 使用演示 =====
int main() {
    std::cout << "=== GPU Buffer RAII Demo ===\n\n";

    // 创建顶点缓冲
    float vertices[] = {0.0f, 0.5f, 0.0f,  -0.5f, -0.5f, 0.0f,  0.5f, -0.5f, 0.0f};
    auto vbo = GPUBuffer::create(vertices, sizeof(vertices));
    std::cout << "VBO created: id=" << vbo.id() << '\n';

    // 移动到容器中（无拷贝）
    std::vector<GPUBuffer> bufferList;
    bufferList.push_back(std::move(vbo));
    std::cout << "After move: vbo.valid()=" << vbo.valid()
              << ", bufferList[0].id()=" << bufferList[0].id() << '\n';

    // vector 扩容时会调用 noexcept 移动
    std::cout << "\n--- Expanding vector ---\n";
    bufferList.push_back(GPUBuffer::create(nullptr, 1024));
    std::cout << "Expansion complete\n";

    std::cout << "\n--- Frame end: destructors run ---\n";
    // bufferList 析构 → 每个 GPUBuffer 析构 → glDeleteBuffers
    return 0;
}
```

**运行方式：**
```bash
g++ -std=c++20 -O2 gpu_buffer_raii.cpp -o gpu_buffer_raii && ./gpu_buffer_raii
```

**预期输出：**
```text
=== GPU Buffer RAII Demo ===

  GL: GenBuffers(1) → id=1
  GL: BindBuffer(target=34962, id=1)
  GL: BufferData(size=36)
VBO created: id=1
After move: vbo.valid()=0, bufferList[0].id()=1

--- Expanding vector ---
  GL: GenBuffers(1) → id=2
  GL: BindBuffer(target=34962, id=2)
  GL: BufferData(size=1024)
Expansion complete

--- Frame end: destructors run ---
  GL: DeleteBuffers(1) → id=1
  GL: DeleteBuffers(1) → id=2
```

### 示例 2：Scope Guard 实现 + Profiler Zone

```cpp
// scope_guard.cpp — 通用 ScopeGuard + 性能插桩区域
// 编译: g++ -std=c++20 -O2 scope_guard.cpp -o scope_guard && ./scope_guard

#include <iostream>
#include <chrono>
#include <string>
#include <utility>
#include <functional>

// ===== 通用 ScopeGuard（C++17 CTAD 版本）=====
template<typename F>
class ScopeGuard {
    F f_;
    bool active_ = true;
public:
    explicit ScopeGuard(F&& f) noexcept : f_(std::forward<F>(f)) {}
    ScopeGuard(ScopeGuard&& other) noexcept
        : f_(std::move(other.f_)), active_(other.active_) {
        other.dismiss();
    }
    ~ScopeGuard() noexcept(noexcept(f_())) {
        if (active_) f_();
    }
    void dismiss() noexcept { active_ = false; }
    ScopeGuard(const ScopeGuard&) = delete;
    ScopeGuard& operator=(const ScopeGuard&) = delete;
};

// C++17 推导指引（让 ScopeGuard(lambda) 自动推导模板参数）
template<typename F>
ScopeGuard(F) -> ScopeGuard<F>;

// ===== Profiler Scope（RAII 时间戳记录）=====
class ProfilerScope {
    using Clock = std::chrono::steady_clock;
    const char* name_;
    Clock::time_point start_;
public:
    explicit ProfilerScope(const char* name) noexcept
        : name_(name), start_(Clock::now()) {}

    ~ProfilerScope() noexcept {
        auto end = Clock::now();
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(
            end - start_).count();
        std::cout << "[PROFILE] " << name_ << ": " << us << " us\n";
    }

    ProfilerScope(const ProfilerScope&) = delete;
    ProfilerScope& operator=(const ProfilerScope&) = delete;
};

// ===== 使用演示 =====
void processEntity(int id) {
    ProfilerScope zone("processEntity");

    // 模拟一些工作
    volatile int sum = 0;
    for (int i = 0; i < 1000000; ++i) sum += i;
}

void renderFrame() {
    ProfilerScope zone("renderFrame");

    // 加载数据，但我们需要确保在出错时清理
    int* rawData = new int[100];  // 假设这是 C API 返回的资源
    auto cleanup = ScopeGuard([&rawData]{
        std::cout << "  Cleanup: deleting rawData\n";
        delete[] rawData;
    });

    // 做渲染...
    processEntity(42);

    // 如果中途 return，cleanup 析构会自动 delete[] rawData
    // 正常结束：dismiss 阻止重复释放
    cleanup.dismiss();
    std::cout << "  Explicit cleanup\n";
    delete[] rawData;
}

int main() {
    std::cout << "=== ScopeGuard + Profiler Demo ===\n\n";
    renderFrame();
    std::cout << "\nFrame complete.\n";
    return 0;
}
```

**运行方式：**
```bash
g++ -std=c++20 -O2 scope_guard.cpp -o scope_guard && ./scope_guard
```

---

## 3. 练习

### 练习 1：封装 RAII 文件句柄（基础）

实现一个 `ScopedFile` 类：
- 构造时打开文件（`fopen` 的 C API），支持 `"r"`, `"w"`, `"rb"` 等模式
- 析构时自动 `fclose`
- 使用工厂函数 `create` 返回 `std::optional<ScopedFile>`（文件不存在时返回空）
- 实现移动语义（`noexcept`），删除拷贝
- 提供 `read`, `write`, `size` 等成员函数
- 编写测试：写入数据到文件，移动到 vector，验证自动关闭

### 练习 2：实现 Profiler 的范围插桩系统（进阶）

设计一套引擎性能插桩系统：
- `ProfilerZone` 类：构造时记录 Zone 名 + 开始时间，析构时将测量数据推入全局 Profiler
- 全局 `Profiler` 单例：收集所有完成的 Zone 数据，支持嵌套（多级调用栈）
- 支持每帧重置统计数据
- 使用 `thread_local` 存储每线程的调用栈
- 编写基准测试：比较插桩开启和关闭时的性能差异，验证插桩本身的开销 < 100ns

### 练习 3：RAII GPU 资源管理器（可选）

设计一个管理多种 GPU 资源的 RAII 系统：
- `GPUTexture`, `GPUBuffer`, `GPUShader` 各有一个 RAII 封装
- 所有三种类型都继承自一个 `GPUResource` 基类（带虚析构）
- 使用一个 `GPUResourceManager` 单例跟踪所有活跃资源
- 在 `GPUResourceManager` 析构时，检查是否有资源未被释放（断言 + 报告泄漏）
- 当引擎关闭时，`GPUResourceManager` 必须在所有 `GPUResource` 对象之前析构——说明如何用 C++ 保证这个顺序

---

## 4. 扩展阅读

- **[必读] C++ Reference — RAII:** https://en.cppreference.com/w/cpp/language/raii — RAII 的标准定义
- **[必读] 本计划 Deep Dive — RAII 深度剖析:** `docs/deep-dives/raii-complete-analysis.md` — 7 层深度分析从 API 到汇编
- **[必读] 本计划 Deep Dive — Scoped Lock 深度剖析:** `docs/deep-dives/lock-guard-scoped-lock.md`
- **[推荐] "The Rule of Zero" (R. Martinho Fernandes, 2012)** — https://rmf.io/cxx11/rule-of-zero — 为什么你不该写析构函数
- **[推荐] "Scope Guard Statement" (Andrei Alexandrescu, 2000)** — Dr. Dobb's — Scope Guard 的原始提出
- **[进阶] Unreal Engine — FScopeCycleCounter** — UE 的 RAII 性能插桩源码分析

---

## 常见陷阱

1. **移动赋值/构造没有标记 `noexcept`。**
   ```cpp
   // ❌ 错误
   GPUBuffer(GPUBuffer&& other) : id_(other.id_) { other.id_ = 0; }
   // 缺少 noexcept → std::vector 扩容时不会使用移动！

   // ✅ 正确
   GPUBuffer(GPUBuffer&& other) noexcept : id_(other.id_) { other.id_ = 0; }
   ```
   如果你写了一个移动构造函数但忘记 `noexcept`，`std::vector` 会自动回退到拷贝——如果拷贝被 `= delete`，会直接编译失败（而非运行时的性能问题）。

2. **在 RAII 对象析构时抛异常。**
   ```cpp
   // ❌ 极其危险
   ~FileHandle() {
       if (fclose(file_) != 0)
           throw std::runtime_error("fclose failed");  // UB! 可能 std::terminate
   }
   // ✅ 正确：析构必须 noexcept（隐式），吞掉错误或仅记录
   ~FileHandle() noexcept {
       if (fclose(file_) != 0) {
           // 记录日志，但不要抛异常
           LogError("Failed to close file");
       }
   }
   ```
   如果析构抛出异常，且当前已有异常在传播，C++ 会直接调用 `std::terminate` 终止程序。

3. **忘了 Rule of Five：只写析构，不写拷贝/移动。**
   ```cpp
   // ❌ 危险
   class Texture {
       GLuint id_;
   public:
       Texture() { glGenTextures(1, &id_); }
       ~Texture() { glDeleteTextures(1, &id_); }
       // 编译器自动生成了拷贝构造和拷贝赋值！
       // 两份 Texture 指向同一个 id_ → 双重删除！
   };

   // ✅ 正确
   class Texture {
       GLuint id_;
   public:
       Texture() { glGenTextures(1, &id_); }
       ~Texture() { glDeleteTextures(1, &id_); }
       Texture(const Texture&) = delete;
       Texture& operator=(const Texture&) = delete;
       Texture(Texture&&) noexcept = default;       // 可以移动
       Texture& operator=(Texture&&) noexcept = default;
   };
   ```

4. **在移动构造中忘记将源对象置为"空"状态。**
   ```cpp
   // ❌ 错误
   GPUBuffer(GPUBuffer&& other) noexcept : id_(other.id_) {}
   // other.id_ 仍然是旧值 → 源对象析构时释放了我们刚接管的资源！
   // → 双重删除

   // ✅ 正确
   GPUBuffer(GPUBuffer&& other) noexcept : id_(other.id_) {
       other.id_ = 0;  // 必须！将源对象剥离
   }
   // 或使用 std::exchange 更优雅
   GPUBuffer(GPUBuffer&& other) noexcept
       : id_(std::exchange(other.id_, 0)) {}
   ```
   这个 bug 的可怕之处在于：如果移动后源对象立刻离开作用域，会立刻双重删除并崩溃；但如果源对象存活一段时间后才析构，可能表现为"随机崩溃"。

5. **将 ScopeGuard 用于异步回调。**
   ```cpp
   // ❌ 危险
   void submitAsyncJob() {
       auto* data = new JobData;
       auto cleanup = ScopeGuard([data]{ delete data; });
       threadPool.submit([data] { /* 使用 data */ });
       cleanup.dismiss();
   }
   // 如果 submit 抛异常，cleanup 会删除 data
   // 但线程池可能已经开始使用 data → use-after-free
   // RAII 的作用域在这里是同步边界，无法跨越异步边界
   ```
   ScopeGuard 绑定**同步**作用域。跨异步边界的资源管理需要使用 `shared_ptr` 或显式的引用计数系统。
