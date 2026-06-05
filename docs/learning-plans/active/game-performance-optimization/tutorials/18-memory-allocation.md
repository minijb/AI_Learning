---
title: "内存分配策略 — 池/Arena/帧分配器"
updated: 2026-06-05
---

# 内存分配策略 — 池/Arena/帧分配器
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50 分钟
> 前置知识: C++ 指针与动态内存基础，理解 malloc/free 语义
---
## 1. 概念讲解

### 为什么需要这个？

游戏每帧只有 16.67ms（60fps）或 33.33ms（30fps）。在这一帧中，如果发生大量 `malloc`/`new` 调用，你会遇到三个致命问题：

1. **全局锁竞争** — 大多数通用内存分配器（如 glibc 的 ptmalloc2）内部有一把全局锁。多线程同时分配时，线程们在锁上排队，单次 `malloc` 可能耗时数百微秒。
2. **碎片化** — 反复分配释放不同大小的内存，堆变成"瑞士奶酪"：总空闲空间足够，但没有一块连续空间能容纳新请求。这会导致分配失败或触发昂贵的堆压缩。
3. **系统调用开销** — 当堆空间不足时，`malloc` 会通过 `brk()`/`mmap()` 向操作系统申请内存，一次系统调用的成本是用户态操作的数百倍。

游戏引擎用**自定义分配器**解决这些问题：预分配大块内存，用自己的算法从中切分，避免全局锁和系统调用。

### 核心思想

自定义分配器的本质是一个简单的等式：

```
自定义分配器 = 预分配大块内存 + 自定义分配策略
```

常见的分配策略有四种：

#### 1. 线性/Arena 分配器（Bump Allocator）

最极致的方案：一个指针指向空闲区域起点，每次分配只移动指针，从不释放单个对象。

```
[A][B][C][空闲................................]
               ^
               bump_ptr
```

- **分配**: `ptr = bump_ptr; bump_ptr += size; return ptr;` — O(1)，几乎零开销。
- **释放**: 不释放单个对象。用完整个 Arena 后一次性重置 `bump_ptr` 到起始位置。
- **适用**: 帧内临时数据、关卡加载期间的构造数据、不需要单独释放的对象。

UE 的 `FMemory::Malloc` 在某些场景使用类似策略；许多引擎的"Frame Allocator"本质就是 Arena。

#### 2. 池分配器（Pool Allocator）

固定大小对象的分配器。预分配 N 个同样大小的槽位，用空闲链表追踪哪些槽位可用。

```
[slot0|slot1|slot2|slot3|...|slotN]
   ^              ^
 free_list → slot2 → slot0 → nullptr
```

- **分配**: 从 free_list 头部取一个槽位 — O(1)，无锁。
- **释放**: 将槽位插回 free_list 头部 — O(1)。
- **适用**: 粒子、子弹、AI 状态机节点、网络消息包 — 任何大量同类型小对象反复创建/销毁的场景。

#### 3. 栈分配器（Stack Allocator）

Arena 的变体：支持 LIFO 释放。用一个标记（marker）记录当前指针位置，稍后可以回滚。

```
[A][B][C]          → 记录 marker → [A][B][C][D][E] → 回滚到 marker → [A][B][C]
         ^marker
```

- **适用**: 递归算法、临时对象作用域、函数调用期间的临时分配。

#### 4. 帧分配器（Frame Allocator）

每帧开始时自动重置的 Arena。游戏领域最常见的模式之一：

```cpp
// 每帧:
frame_allocator.reset();  // 回卷 bump_ptr
update_physics(frame_allocator);
update_ai(frame_allocator);
render(frame_allocator);
// 帧内所有临时分配自动回收
```

本质上是把"手动管理生命周期"退化为"每帧生命周期"——对游戏帧循环极其自然。

#### 对齐与填充

CPU 访问未对齐的内存会触发未对齐异常（某些架构）或性能下降（x86 可容忍但有惩罚）。分配器必须保证返回地址满足对齐要求：

```cpp
// 确保 ptr 对齐到 alignment 的倍数
uintptr_t aligned = (uintptr_t(raw_ptr) + alignment - 1) & ~(alignment - 1);
```

SIMD 指令通常要求 16/32 字节对齐，GPU 资源常要求 256 字节对齐。

#### 调试功能

自定义分配器可以内置调试能力，这是通用分配器难以提供的：

- **Guard Pages**: 在分配块两端放置不可访问的内存页，越界访问立即触发 segfault。
- **Canary**: 在分配块首尾写入魔术数字，释放时检查是否被覆盖。
- **Leak Detection**: Arena 重置时检查是否还有未释放的对象（通过引用计数或标记）。
- **栈回溯**: 记录每次分配的调用栈，泄漏时精准定位。

#### 真实引擎中的分配器

- **UE (Unreal Engine)**:
  - `FMallocBinned` — 基于大小分箱的分配器，类似 jemalloc。将分配请求映射到不同大小的 bin，减少碎片。
  - `FMallocAnsi` — 标准 C `malloc` 的薄封装。
  - `FMallocStomp` — 调试分配器，在每块内存周围插入填充并填充已知字节模式以检测越界。
  - `FMallocProfiler` — 性能分析包装器。
  - 引擎中大量使用 `TMemStackAllocator`（帧栈分配器）和对象池。

- **Unity**:
  - Unity 使用 tcmalloc/jemalloc 作为底层分配器。
  - `NativeArray` 等使用 Unity 内部的内存区域（Memory Regions）。
  - 托管侧则依赖 Mono/IL2CPP GC（后文 22 章详述）。

---
## 2. 代码示例

下面实现三种核心分配器并对 `malloc` 进行基准测试。

### 完整代码

```cpp
// allocators_benchmark.cpp
// 编译: g++ -std=c++17 -O2 -o alloc_bench allocators_benchmark.cpp
// 运行: ./alloc_bench

#include <iostream>
#include <chrono>
#include <vector>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cassert>
#include <algorithm>

// ============================================================
// 1. 线性 Arena 分配器
// ============================================================
class LinearArena {
public:
    LinearArena(size_t size_bytes)
        : memory_(static_cast<char*>(std::malloc(size_bytes)))
        , capacity_(size_bytes)
        , offset_(0)
    {
        assert(memory_ && "Arena allocation failed");
    }

    ~LinearArena() { std::free(memory_); }

    // 禁止拷贝
    LinearArena(const LinearArena&) = delete;
    LinearArena& operator=(const LinearArena&) = delete;

    void* alloc(size_t size, size_t alignment = alignof(std::max_align_t)) {
        // 对齐 offset_
        uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + offset_;
        uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned - current;
        size_t total = padding + size;

        if (offset_ + total > capacity_) {
            return nullptr; // 内存耗尽
        }

        offset_ += total;
        return reinterpret_cast<void*>(aligned);
    }

    void reset() { offset_ = 0; }

    size_t used() const { return offset_; }
    size_t capacity() const { return capacity_; }

private:
    char*  memory_;
    size_t capacity_;
    size_t offset_;
};

// ============================================================
// 2. 自由链表池分配器
// ============================================================
class PoolAllocator {
    struct FreeNode {
        FreeNode* next;
    };

public:
    PoolAllocator(size_t object_size, size_t object_count, size_t alignment = alignof(std::max_align_t))
        : object_size_(std::max(object_size, sizeof(FreeNode))) // 槽位至少容纳一个指针
        , alignment_(alignment)
        , free_list_(nullptr)
    {
        // 计算实际每个槽位的大小（含对齐）
        size_t padded = (object_size_ + alignment_ - 1) & ~(alignment_ - 1);
        slot_size_ = padded;

        // 分配整块内存
        size_t pool_bytes = padded * object_count;
        memory_ = static_cast<char*>(std::malloc(pool_bytes));
        assert(memory_ && "Pool allocation failed");
        capacity_ = object_count;

        // 构建空闲链表
        for (size_t i = 0; i < object_count; ++i) {
            FreeNode* node = reinterpret_cast<FreeNode*>(memory_ + i * padded);
            node->next = free_list_;
            free_list_ = node;
        }
    }

    ~PoolAllocator() { std::free(memory_); }

    PoolAllocator(const PoolAllocator&) = delete;
    PoolAllocator& operator=(const PoolAllocator&) = delete;

    void* alloc() {
        if (!free_list_) return nullptr; // 池耗尽
        FreeNode* node = free_list_;
        free_list_ = node->next;
        return node;
    }

    void free(void* ptr) {
        if (!ptr) return;
        FreeNode* node = static_cast<FreeNode*>(ptr);
        node->next = free_list_;
        free_list_ = node;
    }

    size_t slot_size()  const { return slot_size_; }
    size_t capacity()   const { return capacity_; }

private:
    char*     memory_;
    FreeNode* free_list_;
    size_t    object_size_;
    size_t    alignment_;
    size_t    slot_size_;
    size_t    capacity_ = 0;
};

// ============================================================
// 3. 帧分配器（带 marker 的栈式 Arena）
// ============================================================
class FrameAllocator {
public:
    FrameAllocator(size_t size_bytes)
        : memory_(static_cast<char*>(std::malloc(size_bytes)))
        , capacity_(size_bytes)
        , top_(0)
    {
        assert(memory_ && "Frame allocator allocation failed");
    }

    ~FrameAllocator() { std::free(memory_); }

    FrameAllocator(const FrameAllocator&) = delete;
    FrameAllocator& operator=(const FrameAllocator&) = delete;

    struct Marker {
        size_t offset;
    };

    Marker get_marker() const { return Marker{top_}; }

    void* alloc(size_t size, size_t alignment = alignof(std::max_align_t)) {
        uintptr_t current = reinterpret_cast<uintptr_t>(memory_) + top_;
        uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned - current;
        size_t total = padding + size;

        if (top_ + total > capacity_) return nullptr;

        top_ += total;
        return reinterpret_cast<void*>(aligned);
    }

    void reset_to(Marker m) { top_ = m.offset; }
    void reset()            { top_ = 0; }

    size_t used()     const { return top_; }
    size_t capacity() const { return capacity_; }

private:
    char*  memory_;
    size_t capacity_;
    size_t top_;
};

// ============================================================
// 4. 基准测试工具
// ============================================================
class Timer {
public:
    using Clock = std::chrono::high_resolution_clock;
    using Ms    = std::chrono::microseconds;

    void start() { start_ = Clock::now(); }
    double elapsed_ms() {
        auto end = Clock::now();
        return std::chrono::duration<double, std::milli>(end - start_).count();
    }

private:
    Clock::time_point start_;
};

// ============================================================
// 5. 基准测试
// ============================================================

constexpr size_t KB = 1024;
constexpr size_t MB = 1024 * KB;
constexpr size_t ARENA_SIZE = 64 * MB;
constexpr size_t BATCH      = 100'000;

void bench_arena_vs_malloc() {
    std::cout << "\n=== 基准 1: Arena vs malloc (单线程, " << BATCH << " 次分配) ===\n\n";

    // --- Arena: 分配+释放 ---
    {
        LinearArena arena(ARENA_SIZE);
        Timer t;
        t.start();

        std::vector<void*> ptrs;
        ptrs.reserve(BATCH);

        // 分配 100K 个不同大小的块
        size_t sizes[] = {16, 32, 64, 128, 256, 512, 1024, 4096};
        for (size_t i = 0; i < BATCH; ++i) {
            size_t sz = sizes[i & 7];
            void*  p  = arena.alloc(sz);
            ptrs.push_back(p);
        }

        double alloc_time = t.elapsed_ms();

        // Arena 不逐块释放 — 一次性 reset
        t.start();
        arena.reset();
        double free_time = t.elapsed_ms();

        std::cout << "  Arena 分配:    " << alloc_time << " ms\n";
        std::cout << "  Arena 重置:    " << free_time << " ms\n";
        std::cout << "  Arena 总耗时:  " << (alloc_time + free_time) << " ms\n";
        std::cout << "  Arena 使用量:  " << arena.used() / 1024.0 << " KB\n";
    }

    // --- malloc/free ---
    {
        Timer t;
        t.start();

        std::vector<void*> ptrs;
        ptrs.reserve(BATCH);

        size_t sizes[] = {16, 32, 64, 128, 256, 512, 1024, 4096};
        for (size_t i = 0; i < BATCH; ++i) {
            size_t sz = sizes[i & 7];
            void*  p  = std::malloc(sz);
            ptrs.push_back(p);
        }

        double alloc_time = t.elapsed_ms();

        t.start();
        for (void* p : ptrs) {
            std::free(p);
        }
        double free_time = t.elapsed_ms();

        std::cout << "  malloc 分配:   " << alloc_time << " ms\n";
        std::cout << "  free 释放:     " << free_time << " ms\n";
        std::cout << "  malloc 总耗时: " << (alloc_time + free_time) << " ms\n";
    }
}

void bench_pool_vs_malloc() {
    std::cout << "\n=== 基准 2: Pool vs new/delete (单线程, " << BATCH << " 次 acquire/release) ===\n\n";

    constexpr size_t OBJ_SIZE   = 64;
    constexpr size_t POOL_COUNT = BATCH;

    // --- Pool ---
    {
        PoolAllocator pool(OBJ_SIZE, POOL_COUNT);
        Timer t;
        t.start();

        std::vector<void*> ptrs;
        ptrs.reserve(BATCH);

        for (size_t i = 0; i < BATCH; ++i) {
            ptrs.push_back(pool.alloc());
        }

        for (void* p : ptrs) {
            pool.free(p);
        }

        double elapsed = t.elapsed_ms();
        std::cout << "  Pool acquire/release:  " << elapsed << " ms\n";
        std::cout << "  (每操作 " << (elapsed / (BATCH * 2)) * 1000 << " ns)\n";
    }

    // --- new/delete ---
    {
        Timer t;
        t.start();

        std::vector<char*> ptrs;
        ptrs.reserve(BATCH);

        for (size_t i = 0; i < BATCH; ++i) {
            ptrs.push_back(new char[OBJ_SIZE]);
        }

        for (char* p : ptrs) {
            delete[] p;
        }

        double elapsed = t.elapsed_ms();
        std::cout << "  new/delete:            " << elapsed << " ms\n";
        std::cout << "  (每操作 " << (elapsed / (BATCH * 2)) * 1000 << " ns)\n";
    }
}

void bench_frame_allocator() {
    std::cout << "\n=== 基准 3: 帧分配器模拟 (60fps, 每帧 1000 次分配, 1000 帧) ===\n\n";

    FrameAllocator frame(16 * MB);
    constexpr size_t FRAMES      = 1000;
    constexpr size_t ALLOCS_PER  = 1000;
    size_t sizes[] = {8, 16, 32, 48, 64, 96, 128, 256};

    Timer t;
    t.start();

    for (size_t frame_idx = 0; frame_idx < FRAMES; ++frame_idx) {
        // 模拟帧内随机分配
        for (size_t i = 0; i < ALLOCS_PER; ++i) {
            size_t sz = sizes[(frame_idx * 7 + i * 13) & 7];
            frame.alloc(sz);
        }
        // 每帧结束 — 重置
        frame.reset();
    }

    double elapsed = t.elapsed_ms();
    std::cout << "  总帧数:   " << FRAMES << "\n";
    std::cout << "  每帧分配: " << ALLOCS_PER << "\n";
    std::cout << "  总分配数: " << (FRAMES * ALLOCS_PER) << "\n";
    std::cout << "  总耗时:   " << elapsed << " ms\n";
    std::cout << "  每帧:     " << (elapsed / FRAMES) * 1000 << " μs\n";
    std::cout << "  每分配:   " << (elapsed / (FRAMES * ALLOCS_PER)) * 1000 << " ns\n";
}

// ============================================================
// 6. 对齐与填充 演示
// ============================================================
void demo_alignment() {
    std::cout << "\n=== 对齐演示 ===\n\n";

    LinearArena arena(1024);

    // 分配 3 字节的对象，但要求 16 字节对齐
    void* p1 = arena.alloc(3, 16);
    std::cout << "  alloc(3, align=16) -> " << p1
              << " (对齐到 16: " << (reinterpret_cast<uintptr_t>(p1) % 16 == 0 ? "是" : "否") << ")\n";

    // 分配 7 字节的对象，要求 8 字节对齐
    void* p2 = arena.alloc(7, 8);
    std::cout << "  alloc(7, align=8)  -> " << p2
              << " (对齐到 8: "  << (reinterpret_cast<uintptr_t>(p2) % 8 == 0  ? "是" : "否") << ")\n";

    // SIMD 类型对齐需求
    struct alignas(32) SimdVec { float data[8]; };
    std::cout << "  sizeof(SimdVec) = " << sizeof(SimdVec)
              << ", alignof(SimdVec) = " << alignof(SimdVec) << "\n";

    void* p3 = arena.alloc(sizeof(SimdVec), alignof(SimdVec));
    std::cout << "  alloc(SimdVec, align=32) -> " << p3
              << " (对齐到 32: " << (reinterpret_cast<uintptr_t>(p3) % 32 == 0 ? "是" : "否") << ")\n";
}

int main() {
    std::cout << "========== 游戏内存分配器基准测试 ==========\n";

    bench_arena_vs_malloc();
    bench_pool_vs_malloc();
    bench_frame_allocator();
    demo_alignment();

    std::cout << "\n========== 完成 ==========\n";
    return 0;
}
```

### 预期输出（示例，实际数值因机器而异）

```
========== 游戏内存分配器基准测试 ==========

=== 基准 1: Arena vs malloc (单线程, 100000 次分配) ===

  Arena 分配:    0.012 ms
  Arena 重置:    0.001 ms
  Arena 总耗时:  0.013 ms
  Arena 使用量:  263.672 KB
  malloc 分配:   3.847 ms
  free 释放:     2.103 ms
  malloc 总耗时: 5.950 ms

=== 基准 2: Pool vs new/delete (单线程, 100000 次 acquire/release) ===

  Pool acquire/release:  0.891 ms
  (每操作 4.455 ns)
  new/delete:            15.234 ms
  (每操作 76.17 ns)

=== 基准 3: 帧分配器模拟 (60fps, 每帧 1000 次分配, 1000 帧) ===

  总帧数:   1000
  每帧分配: 1000
  总分配数: 1000000
  总耗时:   0.156 ms
  每帧:     0.156 μs
  每分配:   0.156 ns

=== 对齐演示 ===

  alloc(3, align=16) -> 0x... (对齐到 16: 是)
  alloc(7, align=8)  -> 0x... (对齐到 8: 是)
  sizeof(SimdVec) = 32, alignof(SimdVec) = 32
  alloc(SimdVec, align=32) -> 0x... (对齐到 32: 是)
```

关键观察：
- Arena **分配**比 malloc 快约 **300-500 倍**（无锁、无碎片管理、无系统调用）。
- Pool 比 new/delete 快约 **15-20 倍**（free_list 是 O(1) 的链表操作）。
- 帧分配器每分配仅 ~0.15ns，因为只有指针加法 + 对齐掩码。

---
## 3. 练习

### 练习 1: 实现带边界检查的 Arena

在 `LinearArena` 的基础上添加调试模式：
- 在每块分配的前后插入 4 字节的 canary（值 `0xDEADBEEF`）。
- 在 `reset()` 或析构时扫描所有 canary，若发现被覆盖则报告越界写入。
- 记录每次分配的文件名和行号（使用宏 `ALLOC(arena, size)` 替代 `arena.alloc(size)`）。

### 练习 2: 多线程安全的池分配器

将 `PoolAllocator` 改造为无锁多线程版本：
- 使用 `std::atomic<FreeNode*>` 和 CAS (compare-and-swap) 操作实现 lock-free free_list。
- 基准测试：4 线程同时 acquire/release 各 100K 次，对比单线程版本。
- 提示：CAS 循环 + `std::atomic<T*>::compare_exchange_weak`。

### 练习 3: 策略选择器（挑战）

设计一个 `StrategyAllocator`，根据分配大小自动选择策略：
- `size <= 256`   → 从池中分配（预创建 8/16/32/64/128/256 六个池）。
- `256 < size <= 4096` → 从 Arena 分配。
- `size > 4096` → fallback 到 `malloc`。
- 实现对应的 `free(void*)` — 需要能在释放时判断指针属于哪个分配器。提示：在分配块头部存储元数据。

---
## 4. 扩展阅读

- **jemalloc (Facebook)** — 广泛应用于游戏引擎的生产级分配器，支持线程局部缓存和大小分箱。源码: https://github.com/jemalloc/jemalloc
- **mimalloc (Microsoft)** — 比 jemalloc 更轻量的分配器，free list sharding 设计。源码: https://github.com/microsoft/mimalloc
- **UE 源码**: `Engine/Source/Runtime/Core/Public/HAL/MallocBinned.h` — UE 的分箱分配器实现。`FMemory` 封装了整个分配器体系，支持运行时切换不同策略。
- **Game Engine Architecture (Jason Gregory)**, 第 6.2 节 — 详述游戏引擎中的内存管理策略。
- **"Writing a Memory Allocator" (Dmitry Soshnikov)** — 从零实现 malloc 的教程系列。
- **C++ `std::pmr` (Polymorphic Memory Resources)** — C++17 标准库的多态分配器支持，允许在容器级别切换分配策略。

---
## 常见陷阱

1. **Arena 中的对象析构**: Arena reset 时不会调用析构函数。如果 Arena 中的对象持有非平凡资源（文件句柄、GPU 资源），必须在 reset 前手动析构。考虑在 Arena 上注册 cleanup 回调。
2. **池分配器的对象大小**: 池的槽位大小 ≥ `sizeof(FreeNode)`（通常 ≥ 8 字节）。对小于指针的对象（如 `char`）使用池分配器会浪费空间。
3. **栈分配器越界**: 使用 `Marker` 时，如果存在多个嵌套的 marker 且不按 LIFO 顺序释放，会导致未定义行为。考虑在调试版中添加 marker 层级计数器。
4. **对齐过度**: 不是所有数据都需要 64 字节对齐。过度对齐浪费内存（内部碎片）。只对 SSE/AVX 运算数据使用高对齐。
5. **Arena 扩容**: 当 Arena 耗尽时不能简单 `realloc`（会改变基地址，使已分配指针失效）。正确的做法是分配一个新的 Arena 块并用链表串联。UE 的 `FMallocBinned` 内部就是这么做的。
6. **线程安全幻觉**: 即使使用了自定义分配器，如果多个线程共享同一个 Arena 且没有加锁，依然会出现数据竞争。每个线程应拥有自己的 Arena 或 Frame Allocator，或者在线程间传递已分配好的数据。
