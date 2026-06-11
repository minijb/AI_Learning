---
title: "10 — 栈分配器与帧分配器"
updated: 2026-06-05
---

# 10 — 栈分配器与帧分配器

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 08-自定义分配器入门

---

## 1. 概念讲解

### 栈分配器的核心思想

栈分配器（Stack Allocator / Linear Allocator）是你能写出的**最简单的分配器**——也是游戏引擎中**使用最频繁**的分配器。它的原理直截了当：

```
持有一块连续内存 + 一个偏移指针
allocate(N) → 返回当前指针位置，指针 += N
free()      → 不存在！
reset()     → 指针归零，整块内存"瞬间回收"
```

没有空闲链表、没有碎片合并、没有元数据——分配就是一次指针加法。这使其成为每帧临时数据管理的终极方案。

### 为什么引擎离不开栈分配器

游戏引擎每一帧都在制造大量"活不过一帧"的数据：

| 临时数据 | 典型大小 | 生存期 |
|:---------|:--------|:------|
| 变换矩阵（蒙皮） | 每骨骼 64B × 100 骨骼 × 100 角色 | 一帧 |
| 视锥剔除结果 | 每对象 16B × 50,000 对象 | 一帧 |
| 绘制命令列表 | 每命令 128B × 10,000 命令 | 一帧 |
| 中间渲染缓冲 | 32MB 全屏缓冲 | 一帧 |
| 物理碰撞对 | 每对 32B × 5,000 对 | 一帧 |
| 网络序列化缓冲 | 64KB 消息 | 一帧 |
| 字符串拼接 | 各种日志、调试名 | 一帧 |

所有这些数据用 `malloc` 分配并在帧尾逐个 `free`？每个 `free` 都可能有链表操作、合并检查。10,000 次 `free` → 可能 500us，而 `reset()` → <5ns。

### 检查点机制（Checkpoint / Rollback）

栈分配器的一个关键特性是**检查点**：

```cpp
auto marker = stack.get_marker();   // 记录当前位置
// ... 做一些需要临时内存的工作 ...
stack.reset_to(marker);             // 回退到标记位置
// 在 marker 之后分配的所有内存都被"释放"
```

这比每次都创建新的栈分配器更灵活——你可以嵌套使用同一个分配器，每个子系统通过检查点管理自己的临时数据：

```cpp
void render_frame() {
    auto frame_marker = stack.get_marker();

    render_shadows(stack);           // 内部有自己的检查点
    render_opaque(stack);            // 内部有自己的检查点
    render_transparent(stack);       // 内部有自己的检查点

    stack.reset_to(frame_marker);    // 帧结束，全部回收
}
```

### 双端栈分配器

如果你需要在同一个缓冲区中管理两类临时数据（例如"从低地址往高地址增长"和"从高地址往低地址增长"），可以使用**双端栈分配器**：

```text
┌─────────────────────────────────────────────────────────┐
│  ← Lower Allocator 增长 →     ← Upper Allocator 增长 ←  │
│  lower_offset_ →              ← upper_offset_           │
│  (从 0 开始)                   (从 capacity-1 开始)       │
└─────────────────────────────────────────────────────────┘
```

两个分配器共享同一块内存，从两端向中间增长。当 `lower_offset_ > upper_offset_` 时，内存耗尽。这在引擎管线中很常见：例如渲染线程从底层填充绘制命令，物理线程从顶层填充碰撞对。

### 帧分配器的设计

帧分配器是栈分配器的一个特化——它与游戏主循环的生命周期绑定：

```cpp
class FrameAllocator : public StackAllocator {
public:
    void begin_frame() {
        // 可选：检查上一帧是否有泄漏（marker 没有回到起点）
        reset();
    }
    void end_frame() {
        reset();  // 整帧临时数据瞬间回收
    }
};
```

关键设计决策：**帧分配器应该有多大？**

- 过小 → 帧中 OOM，需要回退到 `malloc`（性能退化）
- 过大 → 浪费内存
- 典型做法：分配一个较大的初始缓冲（例如 32MB），如果帧中耗尽则动态扩展（分配更大的块，但旧的块在帧尾一起释放）

### 与其他分配器的对比

| | 栈分配器 | 池分配器 | Arena 分配器 | malloc/free |
|:--|:--------|:--------|:------------|:-----------|
| 分配速度 | O(1), ~2ns | O(1), ~3ns | O(1), ~2ns | ~30-200ns |
| 释放速度 | 不能单独释放 | O(1) | 不能单独释放 | ~30-200ns |
| 批量释放 | O(1) reset | 逐个 deallocate | O(1) reset | 逐个 free |
| 碎片 | 无 | 无 | 无 | 严重 |
| 适合对象大小 | 任意 | 固定 | 任意 | 任意 |
| 主要限制 | 不能释放中间对象 | 对象大小必须 <= Slot 大小 | 不能释放中间对象 | 慢、碎片化 |

---

## 2. 代码示例

### 示例 1: 完整的栈分配器

```cpp
// compile: g++ -std=c++20 -O2 stack_allocator.cpp -o stack_allocator
#include <iostream>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <new>

class StackAllocator {
public:
    StackAllocator() = default;

    StackAllocator(const StackAllocator&) = delete;
    StackAllocator& operator=(const StackAllocator&) = delete;

    StackAllocator(StackAllocator&& other) noexcept
        : memory_(other.memory_)
        , capacity_(other.capacity_)
        , offset_(other.offset_)
    {
        other.memory_   = nullptr;
        other.capacity_ = 0;
        other.offset_   = 0;
    }

    StackAllocator& operator=(StackAllocator&& other) noexcept {
        if (this != &other) {
            destroy();
            memory_   = other.memory_;
            capacity_ = other.capacity_;
            offset_   = other.offset_;
            other.memory_   = nullptr;
            other.capacity_ = 0;
            other.offset_   = 0;
        }
        return *this;
    }

    void create(size_t size) {
        destroy();
        memory_ = static_cast<char*>(std::aligned_alloc(alignof(std::max_align_t), size));
        if (!memory_) throw std::bad_alloc();
        capacity_ = size;
        offset_   = 0;
    }

    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        // 对齐计算
        uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + offset_;
        uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned - current;

        if (offset_ + padding + size > capacity_) {
            std::cerr << "[StackAllocator] OUT OF MEMORY ("
                      << offset_ + padding + size << " > " << capacity_ << ")\n";
            return nullptr;
        }

        offset_ += padding + size;
        std::memset(reinterpret_cast<void*>(aligned), 0, size);  // 可选：清零
        return reinterpret_cast<void*>(aligned);
    }

    // 获取检查点标记
    struct Marker {
        size_t offset;
    };

    Marker get_marker() const {
        return Marker{offset_};
    }

    void reset_to(Marker marker) {
        assert(marker.offset <= capacity_);
        offset_ = marker.offset;
    }

    void reset() {
        offset_ = 0;
    }

    size_t used()  const { return offset_; }
    size_t avail() const { return capacity_ - offset_; }
    size_t capacity() const { return capacity_; }

    // 获取底层内存指针（用于 placement new 或 DMA 操作）
    char* data() { return memory_; }

    void destroy() {
        if (memory_) {
            std::free(memory_);
            memory_ = nullptr;
        }
        capacity_ = 0;
        offset_   = 0;
    }

    ~StackAllocator() { destroy(); }

private:
    char*  memory_   = nullptr;
    size_t capacity_ = 0;
    size_t offset_   = 0;
};

// ============ RAII 检查点守卫 ============
class ScopedCheckpoint {
public:
    explicit ScopedCheckpoint(StackAllocator& alloc)
        : alloc_(alloc), marker_(alloc.get_marker()) {}

    ~ScopedCheckpoint() {
        alloc_.reset_to(marker_);
    }

    ScopedCheckpoint(const ScopedCheckpoint&) = delete;
    ScopedCheckpoint& operator=(const ScopedCheckpoint&) = delete;

private:
    StackAllocator& alloc_;
    StackAllocator::Marker marker_;
};

// ============ 引擎子系统模拟 ============
struct Vector3 { float x, y, z; };
struct Matrix4x4 { float m[16]; };

void simulate_physics_step(StackAllocator& stack) {
    ScopedCheckpoint checkpoint(stack);

    // 分配碰撞对数组
    size_t num_pairs = 1000;
    auto* pairs = static_cast<Vector3*>(stack.allocate(sizeof(Vector3) * num_pairs));
    // ... 填充碰撞对 ...

    std::cout << "  [Physics] Allocated " << num_pairs << " collision pairs ("
              << stack.used() << "B used)\n";
    // 在 checkpoint 析构时自动回收
}

void simulate_rendering(StackAllocator& stack) {
    ScopedCheckpoint checkpoint(stack);

    // 分配变换矩阵数组
    size_t num_matrices = 200;
    auto* matrices = static_cast<Matrix4x4*>(
        stack.allocate(sizeof(Matrix4x4) * num_matrices, alignof(Matrix4x4)));

    // 分配绘制命令列表
    size_t num_commands = 5000;
    auto* commands = static_cast<char*>(stack.allocate(num_commands * 128));

    std::cout << "  [Render] Allocated matrices + commands ("
              << stack.used() << "B used)\n";
}

void simulate_audio(StackAllocator& stack) {
    ScopedCheckpoint checkpoint(stack);

    auto* buffer = static_cast<float*>(stack.allocate(sizeof(float) * 4096, 64));
    std::cout << "  [Audio] Allocated mix buffer (" << stack.used() << "B used)\n";
}

int main() {
    constexpr size_t FRAME_BUFFER = 8 * 1024 * 1024;  // 8MB

    StackAllocator frame_stack;
    frame_stack.create(FRAME_BUFFER);
    std::cout << "Frame allocator: " << frame_stack.capacity() / 1024 << "KB\n\n";

    // 模拟游戏帧
    for (int frame = 1; frame <= 3; ++frame) {
        std::cout << "=== Frame " << frame << " ===\n";
        auto frame_marker = frame_stack.get_marker();

        simulate_physics_step(frame_stack);
        simulate_rendering(frame_stack);
        simulate_audio(frame_stack);

        // 帧结束 — 全部回收
        frame_stack.reset_to(frame_marker);
        std::cout << "  After frame: " << frame_stack.used() << "B used\n\n";
    }

    // 验证栈分配器速度
    constexpr int N = 1'000'000;
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            volatile void* p = frame_stack.allocate(64);
        }
        frame_stack.reset();
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
        std::cout << "Stack alloc x " << N << ": "
                  << ns / 1e6 << "ms (" << ns / (double)N << "ns/op)\n";
    }

    return 0;
}
```

### 示例 2: 双端栈分配器

```cpp
// compile: g++ -std=c++20 -O2 double_ended_stack.cpp -o double_ended_stack
#include <iostream>
#include <cstdlib>
#include <cassert>

class DoubleEndedStackAllocator {
public:
    void create(size_t size) {
        destroy();
        memory_ = static_cast<char*>(std::aligned_alloc(alignof(std::max_align_t), size));
        if (!memory_) throw std::bad_alloc();
        capacity_  = size;
        lower_off_ = 0;
        upper_off_ = size;   // 从顶端开始
    }

    // 从底部（低地址）分配
    void* alloc_lower(size_t size, size_t alignment = alignof(std::max_align_t)) {
        uintptr_t addr = reinterpret_cast<uintptr_t>(memory_) + lower_off_;
        uintptr_t aligned = (addr + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned - addr;

        if (lower_off_ + padding + size > upper_off_) {
            std::cerr << "[DEStack] Lower end OOM\n";
            return nullptr;
        }

        lower_off_ += padding + size;
        return reinterpret_cast<void*>(aligned);
    }

    // 从顶部（高地址）分配
    void* alloc_upper(size_t size, size_t alignment = alignof(std::max_align_t)) {
        // 向下对齐
        uintptr_t end_addr = reinterpret_cast<uintptr_t>(memory_) + upper_off_;
        uintptr_t aligned_end = end_addr & ~(alignment - 1);
        if (aligned_end < size) {
            std::cerr << "[DEStack] Upper end OOM\n";
            return nullptr;
        }
        uintptr_t start = aligned_end - size;

        if (start < reinterpret_cast<uintptr_t>(memory_) + lower_off_) {
            std::cerr << "[DEStack] Collision! Upper met Lower\n";
            return nullptr;
        }

        upper_off_ = start - reinterpret_cast<uintptr_t>(memory_);
        return reinterpret_cast<void*>(start);
    }

    void reset() {
        lower_off_ = 0;
        upper_off_ = capacity_;
    }

    size_t lower_used() const { return lower_off_; }
    size_t upper_used() const { return capacity_ - upper_off_; }
    size_t total_free() const { return upper_off_ - lower_off_; }

    void destroy() {
        if (memory_) std::free(memory_);
        memory_    = nullptr;
        capacity_  = 0;
        lower_off_ = 0;
        upper_off_ = 0;
    }

    ~DoubleEndedStackAllocator() { destroy(); }

private:
    char*  memory_    = nullptr;
    size_t capacity_  = 0;
    size_t lower_off_ = 0;
    size_t upper_off_ = 0;
};

int main() {
    DoubleEndedStackAllocator de_stack;
    de_stack.create(1024 * 1024);  // 1MB

    std::cout << "Initial free: " << de_stack.total_free() << "B\n";

    // 渲染线程从底部分配
    auto* render_cmds = de_stack.alloc_lower(128 * 1000);
    std::cout << "After render alloc (128KB): lower=" << de_stack.lower_used()
              << " upper=" << de_stack.upper_used()
              << " free=" << de_stack.total_free() << "\n";

    // 物理线程从顶部分配
    auto* physics_pairs = de_stack.alloc_upper(64 * 5000);
    std::cout << "After physics alloc (320KB): lower=" << de_stack.lower_used()
              << " upper=" << de_stack.upper_used()
              << " free=" << de_stack.total_free() << "\n";

    // 帧结束
    de_stack.reset();
    std::cout << "After reset: free=" << de_stack.total_free() << "B\n";

    return 0;
}
```

### 示例 3: 带退路的帧分配器 + 基准测试

```cpp
// compile: g++ -std=c++20 -O2 frame_allocator_fallback.cpp -o frame_allocator_fallback
#include <iostream>
#include <chrono>
#include <cstdlib>
#include <cstring>

// ============ 带 malloc 退路的帧分配器 ============
class FrameAllocator {
public:
    void create(size_t initial_size) {
        destroy();
        memory_   = static_cast<char*>(std::aligned_alloc(alignof(std::max_align_t), initial_size));
        if (!memory_) throw std::bad_alloc();
        capacity_ = initial_size;
        offset_   = 0;
        overflow_count_ = 0;
    }

    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + offset_;
        uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned - current;

        if (offset_ + padding + size <= capacity_) {
            offset_ += padding + size;
            return reinterpret_cast<void*>(aligned);
        }

        // 退路：用 malloc
        overflow_count_++;
        void* p = std::aligned_alloc(alignment, size);
        overflow_ptrs_.push_back(p);
        return p;
    }

    void reset() {
        offset_ = 0;
        // 释放退路分配
        for (auto* p : overflow_ptrs_)
            std::free(p);
        overflow_ptrs_.clear();
        overflow_count_ = 0;
    }

    size_t used()        const { return offset_; }
    size_t overflowed()  const { return overflow_count_; }
    size_t capacity()    const { return capacity_; }

    void destroy() {
        for (auto* p : overflow_ptrs_) std::free(p);
        overflow_ptrs_.clear();
        if (memory_) std::free(memory_);
        memory_ = nullptr;
        capacity_ = 0;
        offset_ = 0;
    }

    ~FrameAllocator() { destroy(); }

private:
    char*  memory_   = nullptr;
    size_t capacity_ = 0;
    size_t offset_   = 0;
    size_t overflow_count_ = 0;
    std::vector<void*> overflow_ptrs_;
};

int main() {
    constexpr int N = 10'000'000;

    // ===== FrameAllocator =====
    {
        FrameAllocator fa;
        fa.create(64 * 1024 * 1024);  // 64MB

        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            volatile void* p = fa.allocate(64);
            (void)p;
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
        std::cout << "Stack  alloc x " << N << ": "
                  << ns / 1e6 << "ms (" << ns / (double)N << "ns/op)\n";
    }

    // ===== malloc =====
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            volatile void* p = std::malloc(64);
            (void)p;
        }
        // 注意：没有 free，这里只测 alloc 速度
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
        std::cout << "malloc       x " << N << ": "
                  << ns / 1e6 << "ms (" << ns / (double)N << "ns/op)\n";
        std::cout << "  (note: no free() called — real usage is worse)\n";
    }

    return 0;
}
```

---

## 3. 练习

### 练习 1: 实现帧分配器（必做）

从零实现一个 `FrameAllocator`，要求：

1. 构造函数接受初始缓冲大小（例如 64MB）
2. `allocate(size, alignment)` — bump pointer 分配，返回对齐后的指针
3. 支持检查点：`get_marker()` 返回位置，`reset_to(marker)` 回退
4. `reset()` — 帧结束时调用，回收所有内存
5. 处理 OOM：如果帧中耗尽内存，回退到 `malloc`（或动态扩展缓冲）
6. 统计信息：`total_allocated()`、`peak_usage()`、`overflow_count()`

**测试**：
- 模拟 60 帧游戏循环，每帧分配不同大小的临时数据
- 验证每帧结束后 `reset()` 正确回收
- 故意制造 OOM 场景，验证退路机制生效

### 练习 2: 实现 RAII 检查点守卫（必做）

实现 `class ScopedMarker`，要求：

1. 构造时记录栈分配器的当前 marker
2. 析构时自动 `reset_to(marker)`
3. 支持 `commit()` — 放弃回退（即检查点的分配变为永久）
4. 禁止拷贝，允许移动
5. 示例用法：

```cpp
void process_frame(StackAllocator& stack) {
    ScopedMarker frame_marker(stack);

    for (auto& system : systems) {
        ScopedMarker sys_marker(stack);
        system.update(stack);
        // sys_marker 析构，system 的临时数据被回收
    }

    // frame_marker 析构，整帧数据回收
}
```

### 练习 3: 多线程帧分配器基准测试（可选挑战）

实现一个基准测试程序，对比：

1. **单栈分配器** — 所有线程共享一个栈（加锁）
2. **每线程栈分配器** — 每个线程有自己的栈（无锁）
3. **mimalloc** — 高质量通用分配器

每种方案运行 4 个线程，每个线程每秒进行 1,000,000 次分配（64B 对象），持续 5 秒。测量：
- 总吞吐量（allocations/sec）
- 平均延迟（ns/alloc）
- P99 延迟

**提示**：使用 `std::thread` + `std::barrier`（C++20）同步启动。使用 `thread_local StackAllocator` 实现每线程栈分配器。验证所有线程正确释放了分配的内存。

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案：实现帧分配器
> ```cpp
> #include <iostream>
> #include <cstdlib>
> #include <cstdint>
> #include <cstring>
> #include <cassert>
> #include <new>
> #include <vector>
> #include <iomanip>
>
> class FrameAllocator {
> public:
>     struct Marker {
>         size_t offset;
>     };
>
>     explicit FrameAllocator(size_t initial_size) {
>         create(initial_size);
>     }
>
>     void create(size_t size) {
>         destroy();
>         memory_ = static_cast<char*>(
>             std::aligned_alloc(alignof(std::max_align_t), size));
>         if (!memory_) throw std::bad_alloc();
>         capacity_ = size;
>         offset_   = 0;
>         peak_used_ = 0;
>         total_allocated_ = 0;
>         overflow_count_  = 0;
>     }
>
>     // bump pointer 分配 + 对齐
>     void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
>         uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + offset_;
>         uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
>         size_t padding = aligned - current;
>
>         if (offset_ + padding + size <= capacity_) {
>             offset_ += padding + size;
>             total_allocated_ += size;
>             if (offset_ > peak_used_) peak_used_ = offset_;
>             return reinterpret_cast<void*>(aligned);
>         }
>
>         // OOM → 回退到 malloc
>         overflow_count_++;
>         void* p = std::aligned_alloc(alignment, size);
>         if (!p) return nullptr;
>         overflow_ptrs_.push_back(p);
>         overflow_bytes_ += size;
>         return p;
>     }
>
>     Marker get_marker() const {
>         return Marker{offset_};
>     }
>
>     void reset_to(Marker marker) {
>         assert(marker.offset <= capacity_);
>         offset_ = marker.offset;
>     }
>
>     void reset() {
>         offset_ = 0;
>         // 释放所有退路分配
>         for (auto* p : overflow_ptrs_)
>             std::free(p);
>         overflow_ptrs_.clear();
>         overflow_bytes_  = 0;
>         overflow_count_  = 0;
>         total_allocated_ = 0;
>         peak_used_       = 0;
>     }
>
>     // 统计信息
>     size_t total_allocated() const { return total_allocated_; }
>     size_t peak_usage()      const { return peak_used_; }
>     size_t overflow_count()  const { return overflow_count_; }
>     size_t used()            const { return offset_; }
>     size_t capacity()        const { return capacity_; }
>
>     void destroy() {
>         for (auto* p : overflow_ptrs_) std::free(p);
>         overflow_ptrs_.clear();
>         if (memory_) std::free(memory_);
>         memory_   = nullptr;
>         capacity_ = 0;
>         offset_   = 0;
>     }
>
>     ~FrameAllocator() { destroy(); }
>
> private:
>     char*   memory_   = nullptr;
>     size_t  capacity_ = 0;
>     size_t  offset_   = 0;
>     size_t  peak_used_  = 0;
>     size_t  total_allocated_ = 0;
>     size_t  overflow_count_  = 0;
>     size_t  overflow_bytes_  = 0;
>     std::vector<void*> overflow_ptrs_;
> };
>
> // ============ 测试 ============
> constexpr size_t MB = 1024 * 1024;
>
> int main() {
>     FrameAllocator frame_alloc(8 * MB);  // 8MB 帧缓冲区
>     std::cout << "Frame allocator: " << frame_alloc.capacity() / MB << "MB\n\n";
>
>     // 测试 1：模拟 60 帧游戏循环
>     std::cout << "=== 60-frame simulation ===\n";
>     for (int frame = 1; frame <= 60; ++frame) {
>         auto marker = frame_alloc.get_marker();
>
>         // 渲染：分配变换矩阵
>         size_t num_matrices = 100 + (frame % 5) * 20;
>         auto* matrices = static_cast<float*>(
>             frame_alloc.allocate(num_matrices * 16 * sizeof(float), 64));
>         assert(matrices);
>
>         // 物理：分配碰撞对
>         size_t num_pairs = 200 + frame * 10;
>         auto* pairs = static_cast<double*>(
>             frame_alloc.allocate(num_pairs * 3 * sizeof(double)));
>         assert(pairs);
>
>         // 音频
>         auto* audio_buf = static_cast<float*>(
>             frame_alloc.allocate(4096 * sizeof(float), 64));
>         assert(audio_buf);
>
>         // 帧结束，验证 reset 正确回收
>         frame_alloc.reset_to(marker);
>
>         if (frame <= 3 || frame == 60) {
>             std::cout << "Frame " << std::setw(2) << frame
>                       << ": peak=" << std::setw(8) << frame_alloc.peak_usage()
>                       << "B, after reset: " << frame_alloc.used() << "B\n";
>         }
>     }
>     std::cout << "  Peak usage over all frames: "
>               << frame_alloc.peak_usage() << "B\n\n";
>
>     // 测试 2：OOM 退路机制
>     std::cout << "=== OOM fallback test ===\n";
>     FrameAllocator small_alloc(1024);  // 仅 1KB!
>     auto* normal = static_cast<int*>(small_alloc.allocate(512));
>     assert(normal && !small_alloc.overflow_count());
>     std::cout << "  512B alloc: OK, overflow=" << small_alloc.overflow_count() << "\n";
>
>     // 这个分配会触发 OOM → 回退到 malloc
>     auto* huge = static_cast<char*>(small_alloc.allocate(2 * MB));
>     std::cout << "  2MB alloc (OOM): ptr=" << (void*)huge
>               << ", overflow=" << small_alloc.overflow_count() << "\n";
>
>     // reset 后 OOM 分配也被释放
>     small_alloc.reset();
>     std::cout << "  After reset: overflow=" << small_alloc.overflow_count() << "\n";
>
>     std::cout << "\nAll tests passed!\n";
>     return 0;
> }
> ```

> [!tip]- 练习 2 参考答案：RAII 检查点守卫
> ```cpp
> #include <iostream>
> #include <cstdlib>
> #include <cstdint>
> #include <utility>
>
> // ── 复用 StackAllocator（与 FrameAllocator 类似，简化版）──
> class StackAllocator {
> public:
>     struct Marker { size_t offset; };
>
>     void create(size_t size) {
>         memory_ = static_cast<char*>(
>             std::aligned_alloc(alignof(std::max_align_t), size));
>         if (!memory_) throw std::bad_alloc();
>         capacity_ = size;
>         offset_ = 0;
>     }
>
>     void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
>         uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + offset_;
>         uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
>         size_t padding = aligned - current;
>         if (offset_ + padding + size > capacity_) return nullptr;
>         offset_ += padding + size;
>         return reinterpret_cast<void*>(aligned);
>     }
>
>     Marker get_marker() const { return Marker{offset_}; }
>     void reset_to(Marker m) { offset_ = m.offset; }
>     void reset() { offset_ = 0; }
>     size_t used() const { return offset_; }
>
>     void destroy() { if (memory_) std::free(memory_); memory_ = nullptr; }
>     ~StackAllocator() { destroy(); }
>
> private:
>     char*  memory_   = nullptr;
>     size_t capacity_ = 0;
>     size_t offset_   = 0;
> };
>
> // ============ ScopedMarker ============
> class ScopedMarker {
> public:
>     explicit ScopedMarker(StackAllocator& alloc)
>         : alloc_(&alloc)
>         , marker_(alloc.get_marker())
>         , committed_(false) {}
>
>     ~ScopedMarker() {
>         if (!committed_ && alloc_) {
>             alloc_->reset_to(marker_);
>         }
>     }
>
>     // 禁止拷贝
>     ScopedMarker(const ScopedMarker&) = delete;
>     ScopedMarker& operator=(const ScopedMarker&) = delete;
>
>     // 允许移动
>     ScopedMarker(ScopedMarker&& other) noexcept
>         : alloc_(other.alloc_)
>         , marker_(other.marker_)
>         , committed_(other.committed_) {
>         other.alloc_     = nullptr;
>         other.committed_ = true;  // 移动后源对象不再负责回退
>     }
>
>     ScopedMarker& operator=(ScopedMarker&& other) noexcept {
>         if (this != &other) {
>             if (!committed_ && alloc_) alloc_->reset_to(marker_);
>             alloc_     = other.alloc_;
>             marker_    = other.marker_;
>             committed_ = other.committed_;
>             other.alloc_     = nullptr;
>             other.committed_ = true;
>         }
>         return *this;
>     }
>
>     // commit() — 放弃回退，分配变为永久
>     void commit() {
>         committed_ = true;
>     }
>
> private:
>     StackAllocator* alloc_;
>     StackAllocator::Marker marker_;
>     bool committed_;
> };
>
> // ============ 模拟引擎子系统 ============
> struct Vector3 { float x, y, z; };
> struct Matrix4x4 { float m[16]; };
>
> struct PhysicsSystem {
>     void update(StackAllocator& stack) {
>         ScopedMarker sys_marker(stack);
>
>         auto* pairs = static_cast<Vector3*>(
>             stack.allocate(sizeof(Vector3) * 1000));
>         std::cout << "  [Physics] " << stack.used() << "B used\n";
>         // sys_marker 析构 → 回收 physics 的临时数据
>     }
> };
>
> struct RenderSystem {
>     void update(StackAllocator& stack) {
>         ScopedMarker sys_marker(stack);
>
>         auto* matrices = static_cast<Matrix4x4*>(
>             stack.allocate(sizeof(Matrix4x4) * 200, alignof(Matrix4x4)));
>         std::cout << "  [Render] " << stack.used() << "B used\n";
>         // sys_marker 析构 → 回收 render 的临时数据
>     }
> };
>
> void process_frame(StackAllocator& stack) {
>     ScopedMarker frame_marker(stack);
>
>     std::cout << "[Frame start] " << stack.used() << "B\n";
>
>     static PhysicsSystem physics;
>     static RenderSystem  render;
>
>     physics.update(stack);
>     render.update(stack);
>
>     // commit() 演示：某些分配需要保留到帧外
>     auto* persistent = static_cast<int*>(stack.allocate(sizeof(int) * 100));
>     *persistent = 42;
>     // 不 commit → frame_marker 析构时会回收 persistent
>
>     // 如果确实需要保留：
>     // frame_marker.commit();
>
>     std::cout << "[Frame end] " << stack.used() << "B (before reset)\n";
>     // frame_marker 析构 → 回收整帧数据
> }
>
> int main() {
>     constexpr size_t MB = 1024 * 1024;
>     StackAllocator stack;
>     stack.create(8 * MB);
>     std::cout << "Stack allocator: " << 8 << "MB\n\n";
>
>     for (int frame = 1; frame <= 3; ++frame) {
>         std::cout << "=== Frame " << frame << " ===\n";
>         process_frame(stack);
>         std::cout << "After frame: " << stack.used() << "B (should be ~0)\n\n";
>     }
>
>     // 验证 commit 行为
>     std::cout << "=== Commit demo ===\n";
>     {
>         ScopedMarker marker(stack);
>         auto* data = static_cast<float*>(stack.allocate(sizeof(float) * 64));
>         data[0] = 3.14f;
>         std::cout << "Before commit: used=" << stack.used() << "B\n";
>         marker.commit();
>         std::cout << "After commit: marker will NOT rollback\n";
>     }
>     std::cout << "After scope: used=" << stack.used()
>               << "B (data preserved!)\n";
>
>     stack.reset();
>     std::cout << "Full reset: used=" << stack.used() << "B\n";
>
>     return 0;
> }
> ```

> [!info]- 思考题 3 参考答案：多线程帧分配器基准测试
> ```cpp
> #include <iostream>
> #include <chrono>
> #include <thread>
> #include <vector>
> #include <atomic>
> #include <barrier>
> #include <mutex>
> #include <cstdlib>
> #include <cstdint>
> #include <iomanip>
> #include <algorithm>
>
> // ============ 简化的线程安全栈分配器 ============
> class ThreadSafeStackAllocator {
> public:
>     void create(size_t size) {
>         memory_ = static_cast<char*>(
>             std::aligned_alloc(alignof(std::max_align_t), size));
>         if (!memory_) throw std::bad_alloc();
>         capacity_ = size;
>         offset_   = 0;
>     }
>
>     void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
>         std::lock_guard<std::mutex> lock(mutex_);
>         uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + offset_;
>         uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
>         size_t padding = aligned - current;
>         if (offset_ + padding + size > capacity_) return nullptr;
>         offset_ += padding + size;
>         return reinterpret_cast<void*>(aligned);
>     }
>
>     void reset() {
>         std::lock_guard<std::mutex> lock(mutex_);
>         offset_ = 0;
>     }
>
>     void destroy() { if (memory_) std::free(memory_); memory_ = nullptr; }
>     ~ThreadSafeStackAllocator() { destroy(); }
>
> private:
>     char*  memory_   = nullptr;
>     size_t capacity_ = 0;
>     size_t offset_   = 0;
>     std::mutex mutex_;
> };
>
> // ============ 每线程栈分配器 ============
> thread_local StackAllocatorPerThread {
> public:
>     static StackAllocatorPerThread& instance() {
>         static thread_local StackAllocatorPerThread tls;
>         return tls;
>     }
>
>     void ensure_created() {
>         if (!memory_) {
>             memory_ = static_cast<char*>(
>                 std::aligned_alloc(alignof(std::max_align_t), 64 * 1024 * 1024));
>             if (!memory_) throw std::bad_alloc();
>             capacity_ = 64 * 1024 * 1024;
>         }
>     }
>
>     void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
>         uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + offset_;
>         uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
>         size_t padding = aligned - current;
>         if (offset_ + padding + size > capacity_) return nullptr;
>         offset_ += padding + size;
>         return reinterpret_cast<void*>(aligned);
>     }
>
>     void reset() { offset_ = 0; }
>
>     ~StackAllocatorPerThread() { if (memory_) std::free(memory_); }
>
> private:
>     StackAllocatorPerThread() = default;
>     char*  memory_   = nullptr;
>     size_t capacity_ = 0;
>     size_t offset_   = 0;
> };
> // 需要在类外声明 thread_local（此处为演示合并写）
> // 实际编译时需拆分为声明+定义
>
> // ============ 基准测试结构 ============
> struct BenchResult {
>     double total_ops_per_sec;
>     double avg_ns;
>     double p99_ns;
> };
>
> constexpr int    NUM_THREADS = 4;
> constexpr int    DURATION_SEC = 5;
> constexpr size_t ALLOC_SIZE   = 64;
> constexpr size_t OPS_PER_BATCH = 10000; // 每 batch 做 1万次，避免频繁计时
>
> // 方案 1：共享栈 + 互斥锁
> BenchResult bench_shared_stack() {
>     ThreadSafeStackAllocator shared;
>     shared.create(256 * 1024 * 1024);  // 256MB
>     std::atomic<bool> stop{false};
>     std::atomic<size_t> total_ops{0};
>     std::vector<double> all_latencies;
>     std::mutex lat_mutex;
>
>     std::barrier sync_point(NUM_THREADS + 1);
>
>     std::vector<std::thread> threads;
>     for (int t = 0; t < NUM_THREADS; ++t) {
>         threads.emplace_back([&]() {
>             sync_point.arrive_and_wait(); // 等待同步启动
>             size_t local_ops = 0;
>             while (!stop.load(std::memory_order_relaxed)) {
>                 auto start = std::chrono::high_resolution_clock::now();
>                 for (size_t i = 0; i < OPS_PER_BATCH; ++i) {
>                     volatile void* p = shared.allocate(ALLOC_SIZE);
>                     (void)p;
>                 }
>                 auto end = std::chrono::high_resolution_clock::now();
>                 double ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
>                     end - start).count() / (double)OPS_PER_BATCH;
>
>                 std::lock_guard<std::mutex> lock(lat_mutex);
>                 all_latencies.push_back(ns);
>
>                 local_ops += OPS_PER_BATCH;
>                 // 每 ~1000 万次 reset 一次（模拟帧边界）
>                 if (local_ops % (OPS_PER_BATCH * 1000) == 0)
>                     shared.reset();
>             }
>             total_ops.fetch_add(local_ops, std::memory_order_relaxed);
>         });
>     }
>
>     sync_point.arrive_and_wait();
>     std::this_thread::sleep_for(std::chrono::seconds(DURATION_SEC));
>     stop.store(true);
>     for (auto& t : threads) t.join();
>
>     // 计算 P99
>     std::sort(all_latencies.begin(), all_latencies.end());
>     double p99 = all_latencies[all_latencies.size() * 99 / 100];
>     double total = total_ops.load();
>     double avg  = all_latencies.empty() ? 0 :
>         std::accumulate(all_latencies.begin(), all_latencies.end(), 0.0) / all_latencies.size();
>
>     return {total / DURATION_SEC, avg, p99};
> }
>
> // 方案 2：每线程栈（无锁）
> BenchResult bench_per_thread_stack() {
>     std::atomic<bool> stop{false};
>     std::atomic<size_t> total_ops{0};
>     std::vector<double> all_latencies;
>     std::mutex lat_mutex;
>
>     std::barrier sync_point(NUM_THREADS + 1);
>
>     std::vector<std::thread> threads;
>     for (int t = 0; t < NUM_THREADS; ++t) {
>         threads.emplace_back([&]() {
>             auto& tls = StackAllocatorPerThread::instance();
>             tls.ensure_created();
>
>             sync_point.arrive_and_wait();
>             size_t local_ops = 0;
>             while (!stop.load(std::memory_order_relaxed)) {
>                 auto start = std::chrono::high_resolution_clock::now();
>                 for (size_t i = 0; i < OPS_PER_BATCH; ++i) {
>                     volatile void* p = tls.allocate(ALLOC_SIZE);
>                     (void)p;
>                 }
>                 auto end = std::chrono::high_resolution_clock::now();
>                 double ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
>                     end - start).count() / (double)OPS_PER_BATCH;
>
>                 std::lock_guard<std::mutex> lock(lat_mutex);
>                 all_latencies.push_back(ns);
>
>                 local_ops += OPS_PER_BATCH;
>                 if (local_ops % (OPS_PER_BATCH * 1000) == 0)
>                     tls.reset();
>             }
>             total_ops.fetch_add(local_ops, std::memory_order_relaxed);
>         });
>     }
>
>     sync_point.arrive_and_wait();
>     std::this_thread::sleep_for(std::chrono::seconds(DURATION_SEC));
>     stop.store(true);
>     for (auto& t : threads) t.join();
>
>     std::sort(all_latencies.begin(), all_latencies.end());
>     double p99 = all_latencies[all_latencies.size() * 99 / 100];
>     double total = total_ops.load();
>     double avg  = all_latencies.empty() ? 0 :
>         std::accumulate(all_latencies.begin(), all_latencies.end(), 0.0) / all_latencies.size();
>
>     return {total / DURATION_SEC, avg, p99};
> }
>
> // 方案 3：malloc（模拟通用分配器 —— 近似 mimalloc/tcmalloc）
> BenchResult bench_malloc() {
>     std::atomic<bool> stop{false};
>     std::atomic<size_t> total_ops{0};
>     std::vector<double> all_latencies;
>     std::mutex lat_mutex;
>
>     std::barrier sync_point(NUM_THREADS + 1);
>
>     std::vector<std::thread> threads;
>     for (int t = 0; t < NUM_THREADS; ++t) {
>         threads.emplace_back([&]() {
>             sync_point.arrive_and_wait();
>             size_t local_ops = 0;
>             while (!stop.load(std::memory_order_relaxed)) {
>                 auto start = std::chrono::high_resolution_clock::now();
>                 for (size_t i = 0; i < OPS_PER_BATCH; ++i) {
>                     volatile void* p = std::malloc(ALLOC_SIZE);
>                     (void)p;
>                 }
>                 auto end = std::chrono::high_resolution_clock::now();
>                 double ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
>                     end - start).count() / (double)OPS_PER_BATCH;
>
>                 std::lock_guard<std::mutex> lock(lat_mutex);
>                 all_latencies.push_back(ns);
>
>                 local_ops += OPS_PER_BATCH;
>             }
>             total_ops.fetch_add(local_ops, std::memory_order_relaxed);
>         });
>     }
>
>     sync_point.arrive_and_wait();
>     std::this_thread::sleep_for(std::chrono::seconds(DURATION_SEC));
>     stop.store(true);
>     for (auto& t : threads) t.join();
>
>     std::sort(all_latencies.begin(), all_latencies.end());
>     double p99 = all_latencies[all_latencies.size() * 99 / 100];
>     double total = total_ops.load();
>     double avg  = all_latencies.empty() ? 0 :
>         std::accumulate(all_latencies.begin(), all_latencies.end(), 0.0) / all_latencies.size();
>
>     return {total / DURATION_SEC, avg, p99};
> }
>
> int main() {
>     std::cout << "=== Multi-threaded Stack Allocator Benchmark ===\n";
>     std::cout << "Threads: " << NUM_THREADS
>               << ", Duration: " << DURATION_SEC << "s"
>               << ", Alloc size: " << ALLOC_SIZE << "B\n\n";
>
>     std::cout << "Running benchmarks...\n";
>
>     auto result1 = bench_shared_stack();
>     auto result2 = bench_per_thread_stack();
>     auto result3 = bench_malloc();
>
>     std::cout << std::left << std::fixed << std::setprecision(1);
>     std::cout << std::setw(24) << "Scheme"
>               << std::setw(18) << "Throughput(ops/s)"
>               << std::setw(14) << "Avg(ns)"
>               << std::setw(14) << "P99(ns)\n";
>     std::cout << std::string(70, '-') << "\n";
>
>     auto print = [](const char* name, const BenchResult& r) {
>         std::cout << std::left
>                   << std::setw(24) << name
>                   << std::setw(18) << static_cast<size_t>(r.total_ops_per_sec)
>                   << std::setw(14) << r.avg_ns
>                   << std::setw(14) << r.p99_ns << "\n";
>     };
>
>     print("Shared + mutex",      result1);
>     print("Per-thread (lock-free)", result2);
>     print("malloc (general)",    result3);
>
>     std::cout << "\n分析：\n";
>     std::cout << "  共享栈 + mutex: 所有线程争用同一把锁，吞吐最差，\n"
>               << "    P99 延迟可能很高（等锁）。\n";
>     std::cout << "  每线程栈: 完全无锁，仅需一次 bump pointer 操作\n"
>               << "    （约 2-5ns），吞吐接近线性扩展。\n"
>               << "  malloc: 通用分配器有线程缓存（tcmalloc/jemalloc/mimalloc），\n"
>               << "    但仍然需要处理不同大小的分配、碎片等。\n"
>               << "    通常比每线程栈慢 5-20 倍。\n";
>
>     return 0;
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- **深度探索**: `docs/deep-dives/custom-allocators-arena.md` — 913 行完整分析，涵盖 Arena 与栈分配器的深入对比
- **Jason Gregory**: *Game Engine Architecture*, §5.4 — 游戏引擎中的栈/线性分配器实践
- **Christian Gyrling**: [GDC 2015 — 顽皮狗的内存管理](https://www.gdcvault.com/) — 帧分配器在 AAA 引擎中的实战
- **Andrei Alexandrescu**: *Modern C++ Design*, §4 — 小型对象分配器基础理论
- **LLVM 源码参考**: `llvm/include/llvm/Support/Allocator.h` — `BumpPtrAllocator` 实现（栈分配器的工业化版本）
- **mimalloc**: [Microsoft/mimalloc](https://github.com/microsoft/mimalloc) — mimalloc 中有 `mi_heap_area_t` 的区域分配也借鉴了栈分配思想

---

## 常见陷阱

### 陷阱 1: 忘记对齐导致崩溃或性能退化

```cpp
// 错误：简单的 bump pointer，没有对齐
void* allocate(size_t size) {
    void* p = buffer_ + offset_;
    offset_ += size;         // 没有对齐！
    return p;
}

auto* matrices = allocate(sizeof(Matrix4x4) * 100);
// Matrix4x4 需要 16-byte 对齐 → 可能 crash（ARM）或性能退化（x86 SSE）
```

**原因**：`buffer_ + offset_` 返回的指针可能不满足 `alignment` 要求。x86 上未对齐的 SIMD 访问慢 2-5 倍；ARM 上直接触发总线错误。

**正确做法**：始终计算对齐偏移：
```cpp
uintptr_t aligned = (reinterpret_cast<uintptr_t>(buffer_) + offset_ + alignment - 1)
                    & ~(alignment - 1);
offset_ = aligned - reinterpret_cast<uintptr_t>(buffer_) + size;
```

### 陷阱 2: reset() 后继续使用已分配指针

```cpp
auto* cmd = static_cast<RenderCommand*>(frame_allocator.allocate(sizeof(RenderCommand)));
render_queue.push_back(cmd);
frame_allocator.reset();  // 帧结束
// GPU 线程还在用 render_queue 中的 cmd！→ 未定义行为
```

**原因**：`reset()` 后栈分配器的内存被"逻辑释放"，但 GPU 线程可能还在异步读取。下一帧的分配会覆盖同一块内存。

**解决方案**：使用双缓冲或环形缓冲确保异步消费者在 `reset()` 之前完成读取。或者通过 fence/信号量同步。

### 陷阱 3: 在栈分配器上分配的对象有非平凡析构函数

```cpp
auto* str = static_cast<std::string*>(stack.allocate(sizeof(std::string)));
new (str) std::string("long string that allocates on heap");
// ...
stack.reset();  // string 的内部堆分配泄漏！
```

**原因**：`reset()` 只是把指针拨回起点，不会调用任何析构函数。`std::string` 的内部 `char*` 缓冲区通过 `malloc` 分配，永远不会被释放。

**解决方案**：(1) 不要在栈分配器上分配有非平凡析构的类型；(2) 如果需要，在 `reset()` 之前手动调用析构函数；(3) 使用 `SpecificBumpPtrAllocator`（见 Arena 分配器教程）。

### 陷阱 4: 栈溢出 — 帧分配器 OOM

```cpp
FrameAllocator frame(4 * 1024 * 1024);  // 4MB — 可能不够
// 帧中段分配了 3.5MB，再来一个 1MB 缓冲 → nullptr
auto* buf = frame.allocate(1024 * 1024);
if (!buf) { /* 崩溃或回退 */ }
```

**症状**：帧中突然出现 `nullptr` 返回或 `std::bad_alloc`，通常发生在复杂场景（大量粒子、多角色蒙皮）中。难以重现——只在特定场景组合下才触发。

**解决方案**：(1) 预留充足的缓冲（64-128MB）；(2) 实现回退机制——OOM 时用 `malloc` 分配，帧尾统一释放；(3) 在开发阶段用标记监控峰值使用量，调大缓冲区。

### 陷阱 5: 检查点嵌套顺序错误

```cpp
auto m1 = stack.get_marker();
auto m2 = stack.get_marker();
// ... 分配 ...
stack.reset_to(m1);  // 正确
// 但如果先 reset_to(m2) 再 reset_to(m1)，m2 的标记可能已失效
```

虽然单纯的 offset 值（整数）不会"失效"，但如果你的栈分配器在 OOM 时重新分配了更大的底层缓冲（动态扩展），旧的 marker 就会指向已被 `free` 的旧缓冲区——使用它们会导致堆损坏。

**最佳实践**：使用 RAII（`ScopedCheckpoint`）自动管理嵌套，避免手动调用 `reset_to`。
