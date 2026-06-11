---
title: "08 — 自定义分配器入门：为什么游戏引擎需要它们"
updated: 2026-06-05
---

# 08 — 自定义分配器入门：为什么游戏引擎需要它们

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 02-对象生命周期与内存布局, 03-RAII 与资源管理深度解析

---

## 1. 概念讲解

### 通用分配器在游戏中的失败

每一帧 16.6ms（60 FPS）中，你的引擎需要：

- 分配数百个粒子结构体
- 创建数千个渲染命令
- 构造临时碰撞检测数据
- 序列化网络消息
- 更新动画骨骼变换

如果所有这些操作都用 `malloc`/`new`——每一帧都可能触发不可预测的开销：

| 问题 | 通用分配器的表现 | 引擎需要的 |
|:-----|:---------------|:---------|
| **延迟不可预测** | `malloc` 可能搜索空闲链表、触发系统调用、甚至缺页中断 | 每次分配在 < 50ns 内完成 |
| **碎片化** | 运行 10 分钟后，32GB 堆中有 8GB "空闲"但无法分配一个连续的 256KB 块 | 零碎片或可控碎片 |
| **隐藏开销** | 每次分配 16-32 字节的元数据（块大小、标志位、链表指针） | 分配器开销 < 1% 有效数据 |
| **缓存污染** | 元数据和实际数据散布在堆中 → 缓存行浪费 | 数据紧密排列，最大化缓存命中 |
| **无生命周期感知** | `malloc` 不知道你的数据只活一帧 | 帧结束后整批回收，O(1) |

### malloc 的实测开销

每次 `malloc(N)` 返回的指针前有元数据块（allocator metadata）。在 glibc malloc 中：

```text
┌──────────────┬─────────────────────┐
│  meta (16B)  │  用户数据 (N bytes)  │
└──────────────┴─────────────────────┘
               ↑ malloc() 返回这里
```

实际开销因实现而异：glibc ptmalloc2 ~16-24B、jemalloc ~8-16B、mimalloc ~8-16B。但这只是"浪费的空间"。更致命的是**时间开销**——一个小 `malloc(64)` 可能耗时 30-200ns；如果触发了 brk/mmap 系统调用则可飙升到微秒级。

在 16.6ms 的帧预算中，10,000 次小分配即使每次只 100ns 也吃掉 1ms —— 这还不算 `free` 的开销。

### 分配器分类速查

游戏引擎中常用的分配器按内存回收策略分类：

| 分配器类型 | 分配 | 释放 | 最佳场景 |
|:----------|:----|:-----|:--------|
| **栈/线性分配器** | O(1) — bump pointer | 不能单独释放，只能整批 Reset | 帧临时数据、关卡加载 |
| **池分配器** | O(1) — 取 free list 头部 | O(1) — 插回 free list | 固定大小对象：粒子、子弹、网络包 |
| **Arena/区域分配器** | O(1) — bump pointer | 不能单独释放，整批丢弃 | 编译期 AST、JSON 解析 |
| **Slab 分配器** | O(1) — 从 slab 取 | O(1) — 归还到 slab | 操作系统内核对象、引擎中同类对象池 |
| **Buddy 分配器** | O(log N) — 二分搜索 | O(log N) — 合并伙伴 | 需要可变大小 + 紧凑碎片管理 |
| **通用分配器** (mimalloc/jemalloc) | ~O(1) 分摊 | ~O(1) 分摊 | 生命周期不可预测的分配 |

### 引擎集成架构

一个典型的游戏引擎会分层使用多种分配器：

```text
Frame Allocator (每帧 Reset)                    ← 临时渲染数据
  ├─ Stack Allocator (每帧 Reset)               ← 临时字符串、中间缓冲
  ├─ Pool Allocator (Particle, 64B)             ← 粒子系统
  ├─ Pool Allocator (RenderCmd, 128B)           ← 渲染命令
  └─ Pool Allocator (NetworkPkt, 512B)          ← 网络消息

Level Allocator (关卡卸载时整体丢弃)              ← 关卡几何、纹理元数据
  └─ Arena of Arenas

Persistent Allocator (随引擎生命周期)             ← 全局系统
  └─ mimalloc / jemalloc / tcmalloc              ← 兜底
```

### std::allocator 接口与引擎分配器的差异

STL 容器的分配器接口（`std::allocator<T>`）定义在 C++98，继承自 HP/SGI STL：

```cpp
template<typename T>
struct MyAllocator {
    using value_type = T;
    T* allocate(size_t n);
    void deallocate(T* p, size_t n);
    // rebind 用于 list/map 等节点容器
    template<typename U> struct rebind { using other = MyAllocator<U>; };
};
```

**引擎分配器通常不使用这套接口**，原因是：

1. `allocate(n)` 返回 `T*` —— 耦合了类型和分配，引擎更需要 `void* allocate(size, alignment)`
2. `rebind` 机制对容器内部节点类型透明 —— 引擎需要显式控制
3. 不能传递分配时的元数据（debug name、category、frame index）
4. 对 move-only 分配器的支持直到 C++17 PMR 才改善

### C++17 PMR 概述

`std::pmr`（Polymorphic Memory Resource）引入类型擦除的分配器抽象：

```cpp
// 基类
class std::pmr::memory_resource {
    virtual void* do_allocate(size_t bytes, size_t alignment) = 0;
    virtual void do_deallocate(void* p, size_t bytes, size_t alignment) = 0;
    virtual bool do_is_equal(const memory_resource& other) const noexcept = 0;
};

// 内置实现
std::pmr::monotonic_buffer_resource    // bump allocator — 不释放单个分配
std::pmr::unsynchronized_pool_resource // 线程局部的池分配器
std::pmr::synchronized_pool_resource   // 线程安全的池分配器
std::pmr::new_delete_resource()        // 全局 new/delete 包装
```

**PMR 的核心优势**：容器不需模板参数指定分配器类型 → `std::pmr::vector<int>` 可以在运行时切换分配策略。代价是虚函数调用开销（每次分配间接调用一次）。

### 跟踪分配模式：找到热点

在写自定义分配器之前，你要先知道**哪里需要它**。一个简单的分配追踪器：

```cpp
struct AllocTracker {
    std::atomic<size_t> alloc_count{0};
    std::atomic<size_t> free_count{0};
    std::atomic<size_t> total_bytes{0};

    void record_alloc(size_t bytes) { alloc_count++; total_bytes += bytes; }
    void record_free(size_t bytes)  { free_count++; total_bytes -= bytes; }
};
```

重载全局 `operator new` 和 `operator delete`，在分配追踪器中记录每一帧的分配/释放。几帧后就能看到热点：哪个系统分配最频繁？哪个分配大小最常见？——这些信息决定你该使用哪种分配器。

---

## 2. 代码示例

### 示例 1: malloc 开销测量

```cpp
// compile: g++ -std=c++20 -O2 malloc_overhead.cpp -o malloc_overhead
#include <iostream>
#include <cstdlib>
#include <chrono>
#include <vector>
#include <cstdint>

// 获取 malloc 的真实块大小（glibc 扩展）
#ifdef __GLIBC__
#include <malloc.h>
size_t malloc_usable_size(void* ptr) { return ::malloc_usable_size(ptr); }
#else
size_t malloc_usable_size(void* ptr) { return 0; }  // not available
#endif

int main() {
    constexpr int N = 100'000;
    constexpr size_t sizes[] = {8, 16, 32, 64, 128, 256, 512, 1024};

    std::cout << "=== malloc overhead measurement ===\n";
    std::cout << "Requested | Actual  | Overhead | Ratio\n";

    for (auto req : sizes) {
        std::vector<void*> ptrs(N);
        size_t total_requested = 0;
        size_t total_actual = 0;

        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            ptrs[i] = std::malloc(req);
            total_requested += req;
            total_actual += malloc_usable_size(ptrs[i]);
        }
        auto alloc_end = std::chrono::high_resolution_clock::now();

        for (int i = 0; i < N; ++i)
            std::free(ptrs[i]);
        auto free_end = std::chrono::high_resolution_clock::now();

        auto alloc_us = std::chrono::duration_cast<std::chrono::microseconds>(
            alloc_end - start).count();
        auto free_us = std::chrono::duration_cast<std::chrono::microseconds>(
            free_end - alloc_end).count();

        std::cout << req << "B\t" << (total_actual / N)
                  << "B\t" << (total_actual - total_requested) / N
                  << "B\talloc=" << (double)alloc_us / N * 1000 << "ns"
                  << " free=" << (double)free_us / N * 1000 << "ns\n";
    }

    // 碎片化测试
    std::cout << "\n=== Fragmentation test ===\n";
    std::vector<void*> ptrs;
    // 交错分配不同大小
    for (int i = 0; i < 10000; ++i) {
        ptrs.push_back(std::malloc(64 + (i % 4) * 32));
    }
    // 每隔一个释放一个
    for (int i = 0; i < 10000; i += 2) {
        std::free(ptrs[i]);
        ptrs[i] = nullptr;
    }
    // 尝试分配一个大的连续块
    void* big = std::malloc(1 << 20);  // 1MB
    std::cout << "After fragmentation: malloc(1MB) "
              << (big ? "succeeded" : "FAILED") << "\n";
    std::free(big);
    for (int i = 1; i < 10000; i += 2) std::free(ptrs[i]);

    return 0;
}
```

### 示例 2: 分配追踪器

```cpp
// compile: g++ -std=c++20 -O2 alloc_tracker.cpp -o alloc_tracker
#include <iostream>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <unordered_map>
#include <vector>
#include <algorithm>

// ============ 分配追踪器 ============
struct AllocationRecord {
    size_t count;
    size_t total_bytes;
    size_t max_bytes;
};

class AllocTracker {
public:
    static AllocTracker& instance() {
        static AllocTracker tracker;
        return tracker;
    }

    void record_alloc(void* ptr, size_t size) {
        total_allocs_++;
        total_bytes_ += size;
        peak_bytes_ = std::max(peak_bytes_, total_bytes_.load());

        // 按分配大小分桶
        auto& rec = by_size_[size_to_bucket(size)];
        rec.count++;
        rec.total_bytes += size;
        rec.max_bytes = std::max(rec.max_bytes, size);
    }

    void record_free(void* ptr, size_t size) {
        total_frees_++;
        total_bytes_ -= size;
    }

    void report() const {
        std::cout << "\n========== Allocation Report ==========\n";
        std::cout << "Total allocations: " << total_allocs_ << "\n";
        std::cout << "Total frees:       " << total_frees_ << "\n";
        std::cout << "Current bytes:     " << total_bytes_ << "\n";
        std::cout << "Peak bytes:        " << peak_bytes_ << "\n";
        std::cout << "Leaked (allocs - frees): "
                  << (total_allocs_ - total_frees_) << "\n\n";

        std::cout << "By size bucket:\n";
        for (auto& [bucket, rec] : by_size_) {
            std::cout << "  " << bucket << "B: count=" << rec.count
                      << " total=" << rec.total_bytes
                      << " max=" << rec.max_bytes << "\n";
        }
    }

    void reset() {
        total_allocs_ = 0;
        total_frees_ = 0;
        total_bytes_ = 0;
        peak_bytes_ = 0;
        by_size_.clear();
    }

private:
    std::atomic<size_t> total_allocs_{0};
    std::atomic<size_t> total_frees_{0};
    std::atomic<size_t> total_bytes_{0};
    size_t peak_bytes_{0};

    // 将大小规整到 2 的幂次桶
    static size_t size_to_bucket(size_t size) {
        if (size <= 8) return 8;
        size_t bucket = 16;
        while (bucket < size && bucket < (1 << 20)) bucket <<= 1;
        return bucket;
    }

    // 简化：单线程无锁。生产环境应分线程或加锁
    std::unordered_map<size_t, AllocationRecord> by_size_;
};

// ============ 全局 operator new/delete 重载 ============
void* operator new(size_t size) {
    void* ptr = std::malloc(size);
    if (!ptr) throw std::bad_alloc();
    AllocTracker::instance().record_alloc(ptr, size);
    return ptr;
}

void operator delete(void* ptr) noexcept {
    AllocTracker::instance().record_free(ptr, 0);  // size unknown in delete(void*)
    std::free(ptr);
}

void operator delete(void* ptr, size_t size) noexcept {
    AllocTracker::instance().record_free(ptr, size);
    std::free(ptr);
}

// ============ 演示 ============
struct Vector3 { float x, y, z; };

int main() {
    AllocTracker::instance().reset();

    {
        std::vector<int> vec;
        for (int i = 0; i < 1000; ++i)
            vec.push_back(i);  // 多次 reallocation
    }

    {
        std::vector<Vector3> positions;
        positions.reserve(10000);
        for (int i = 0; i < 10000; ++i)
            positions.emplace_back();
    }

    AllocTracker::instance().report();
    return 0;
}
```

### 示例 3: PMR 集成 — 粒子系统

```cpp
// compile: g++ -std=c++20 -O2 pmr_particles.cpp -o pmr_particles
#include <iostream>
#include <memory_resource>
#include <vector>
#include <chrono>

struct Particle {
    float x, y, z;
    float vx, vy, vz;
    float lifetime;
};

// 帧分配器模拟：预分配缓冲，每帧 Reset
class FrameBufferResource : public std::pmr::memory_resource {
public:
    FrameBufferResource(size_t size)
        : buffer_(new char[size]), capacity_(size), offset_(0) {}

    ~FrameBufferResource() override { delete[] buffer_; }

    void reset() { offset_ = 0; }

protected:
    void* do_allocate(size_t bytes, size_t alignment) override {
        // 对齐计算
        uintptr_t current = reinterpret_cast<uintptr_t>(buffer_) + offset_;
        uintptr_t aligned = (current + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned - current;
        size_t total = padding + bytes;

        if (offset_ + total > capacity_)
            throw std::bad_alloc();  // 帧分配器满了！需要更大缓冲或回退

        offset_ += total;
        return reinterpret_cast<void*>(aligned);
    }

    void do_deallocate(void*, size_t, size_t) override {
        // 帧分配器不单独释放 — 整帧 Reset 时才回收
    }

    bool do_is_equal(const memory_resource& other) const noexcept override {
        return this == &other;
    }

private:
    char* buffer_;
    size_t capacity_;
    size_t offset_;
};

int main() {
    constexpr size_t FRAME_BUFFER_SIZE = 64 * 1024 * 1024;  // 64MB

    // 每帧使用的帧分配器
    FrameBufferResource frame_arena(FRAME_BUFFER_SIZE);

    constexpr int FRAMES = 60;
    constexpr int PARTICLES_PER_FRAME = 100'000;

    auto start = std::chrono::high_resolution_clock::now();

    for (int f = 0; f < FRAMES; ++f) {
        // 使用 pmr::vector — 所有分配走 frame_arena
        std::pmr::vector<Particle> particles(&frame_arena);
        particles.reserve(PARTICLES_PER_FRAME);

        for (int i = 0; i < PARTICLES_PER_FRAME; ++i)
            particles.push_back({1.0f, 2.0f, 3.0f, 0.1f, 0.2f, 0.3f, 5.0f});

        // 模拟粒子更新
        for (auto& p : particles) {
            p.x += p.vx;
            p.y += p.vy;
            p.z += p.vz;
        }

        // 帧结束 — 所有粒子内存一次性回收
        frame_arena.reset();
    }

    auto end = std::chrono::high_resolution_clock::now();
    auto us = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
    std::cout << FRAMES << " frames of " << PARTICLES_PER_FRAME
              << " particles: " << us / 1000.0 << "ms\n";
    std::cout << "Average per frame: " << us / (double)FRAMES
              << "us (budget: 16666us)\n";

    return 0;
}
```

### 示例 4: STL 容器使用自定义分配器

```cpp
// compile: g++ -std=c++20 -O2 custom_stl_allocator.cpp -o custom_stl_allocator
#include <iostream>
#include <vector>
#include <cstdlib>

// ---- 最简自定义分配器 ----
template<typename T>
struct TrackingAllocator {
    using value_type = T;

    TrackingAllocator() = default;

    template<typename U>
    TrackingAllocator(const TrackingAllocator<U>&) {}

    T* allocate(size_t n) {
        size_t bytes = n * sizeof(T);
        std::cout << "  alloc " << n << " x " << sizeof(T) << "B = " << bytes << "B\n";
        if (bytes == 0) return nullptr;
        void* p = std::malloc(bytes);
        if (!p) throw std::bad_alloc();
        return static_cast<T*>(p);
    }

    void deallocate(T* p, size_t n) {
        std::cout << "  free  " << n << " x " << sizeof(T) << "B\n";
        std::free(p);
    }

    // C++17+: propagate on container swap
    using propagate_on_container_swap = std::true_type;
};

template<typename T, typename U>
bool operator==(const TrackingAllocator<T>&, const TrackingAllocator<U>&) {
    return true;
}
template<typename T, typename U>
bool operator!=(const TrackingAllocator<T>&, const TrackingAllocator<U>&) {
    return false;
}

int main() {
    std::cout << "=== vector<int> with TrackingAllocator ===\n";
    {
        std::vector<int, TrackingAllocator<int>> vec;
        for (int i = 0; i < 10; ++i)
            vec.push_back(i);
        std::cout << "  Final capacity: " << vec.capacity() << "\n";
    }
    std::cout << "  (destructor freed)\n";
    return 0;
}
```

---

## 3. 练习

### 练习 1: 写一个分配追踪器（必做）

实现一个 `SimpleAllocTracker`，要求：

1. 重载全局 `operator new` / `operator delete` 以记录每次分配和释放
2. 按帧组织数据：提供一个 `begin_frame()` / `end_frame()` 接口
3. 在每帧结束时输出：该帧分配次数、释放次数、总分配字节、峰值字节
4. 测试：创建一个循环，模拟 60 帧游戏运行，每帧进行不同模式的分配/释放
5. 输出如：`Frame 12: 340 allocs, 290 frees, 15,360 new bytes, peak 128,456 bytes`

**要求**：不要用全局变量（除了重载的 operator new/delete 需要一个全局 tracker）。用单例模式或者显式传入。

### 练习 2: 用 PMR 优化一个粒子系统（必做）

给定一个简单的粒子模拟器：

```cpp
struct Particle { float x, y, z, vx, vy, vz, life; };
std::vector<Particle> particles;
void simulate_frame() {
    particles.clear();
    for (int i = 0; i < 50000; ++i)
        particles.push_back({...});
    // 更新粒子...
}
```

将其改造为使用 `std::pmr::monotonic_buffer_resource`：

1. 在一个预分配的栈缓冲区上创建 `monotonic_buffer_resource`
2. 改用 `std::pmr::vector<Particle>`
3. 测量改造前后的性能差异（用 `chrono` 计时）
4. 确保每帧 `release()` 回收内存

**输出要求**：报告每帧的平均分配耗时（改造前 vs 改造后）。

### 练习 3: 实现一个多级分配追踪器（可选挑战）

扩展示例 2 的 `AllocTracker`：

1. 支持按**分配类别**追踪（例如 `"Physics"`, `"Rendering"`, `"Audio"`）——通过模板参数或 tag 分派
2. 为每个类别维护独立的统计（分配次数、字节数、峰值）
3. 提供层级报告：总体统计 + 每类别统计
4. 检测泄漏：在程序退出时报告"已分配但未释放"的块（按类别分组）

**提示**：如果使用 tag 分派，可以考虑 `template<typename Category> struct TaggedAllocTracker` 配合 `thread_local` 存储。

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案：分配追踪器
> ```cpp
> #include <iostream>
> #include <cstdlib>
> #include <new>
> #include <atomic>
> #include <vector>
> #include <iomanip>
>
> // ============ 帧级分配追踪器 ============
> class SimpleAllocTracker {
> public:
>     static SimpleAllocTracker& instance() {
>         static SimpleAllocTracker t;
>         return t;
>     }
>
>     void begin_frame() {
>         frame_allocs_   = 0;
>         frame_frees_    = 0;
>         frame_bytes_    = 0;
>         frame_peak_     = 0;
>     }
>
>     void end_frame(int frame_num) {
>         std::cout << "Frame " << std::setw(3) << frame_num
>                   << ": " << std::setw(6) << frame_allocs_  << " allocs, "
>                   << std::setw(6) << frame_frees_   << " frees, "
>                   << std::setw(10) << frame_bytes_  << " new bytes, "
>                   << "peak " << std::setw(10) << frame_peak_ << " bytes\n";
>     }
>
>     // 全局统计
>     void report_total() const {
>         std::cout << "\n=== Total ===\n"
>                   << "Allocations: " << total_allocs_ << "\n"
>                   << "Frees:       " << total_frees_  << "\n"
>                   << "Leaked:      " << (total_allocs_ - total_frees_) << "\n";
>     }
>
>     // 供 operator new/delete 调用的内部接口
>     void on_alloc(size_t size) {
>         total_allocs_++;
>         frame_allocs_++;
>         frame_bytes_ += size;
>         if (frame_bytes_ > frame_peak_)
>             frame_peak_ = frame_bytes_;
>     }
>
>     void on_free() {
>         total_frees_++;
>         frame_frees_++;
>     }
>
> private:
>     SimpleAllocTracker() = default;
>
>     // 全局累计
>     std::atomic<size_t> total_allocs_{0};
>     std::atomic<size_t> total_frees_{0};
>
>     // 当前帧统计（单线程场景，非原子即可）
>     size_t frame_allocs_ = 0;
>     size_t frame_frees_  = 0;
>     size_t frame_bytes_  = 0;
>     size_t frame_peak_   = 0;
> };
>
> // ============ 全局 operator new/delete 重载 ============
> void* operator new(size_t size) {
>     void* p = std::malloc(size);
>     if (!p) throw std::bad_alloc();
>     SimpleAllocTracker::instance().on_alloc(size);
>     return p;
> }
>
> void operator delete(void* p) noexcept {
>     SimpleAllocTracker::instance().on_free();
>     std::free(p);
> }
>
> void operator delete(void* p, size_t /*size*/) noexcept {
>     SimpleAllocTracker::instance().on_free();
>     std::free(p);
> }
>
> // 数组版本
> void* operator new[](size_t size) {
>     void* p = std::malloc(size);
>     if (!p) throw std::bad_alloc();
>     SimpleAllocTracker::instance().on_alloc(size);
>     return p;
> }
>
> void operator delete[](void* p) noexcept {
>     SimpleAllocTracker::instance().on_free();
>     std::free(p);
> }
>
> // ============ 模拟游戏帧 ============
> struct Vector3 { float x, y, z; };
> struct Particle { Vector3 pos, vel; float life; };
>
> int main() {
>     std::cout << "=== 60-Frame Allocation Simulation ===\n\n";
>     std::cout << std::setfill(' ');
>
>     for (int frame = 1; frame <= 60; ++frame) {
>         SimpleAllocTracker::instance().begin_frame();
>
>         // 每帧模拟不同的分配模式
>         int num_alloc = (frame % 10) * 100 + 50; // 50~950 次分配/帧
>
>         for (int i = 0; i < num_alloc; ++i) {
>             volatile auto* p = new Particle();  // 分配
>             // 随机释放一部分（模拟生灭循环）
>             if (i % 3 != 0) {
>                 delete static_cast<const Particle*>(p);
>             }
>         }
>
>         // 每 10 帧做一堆 Vector3 分配
>         if (frame % 10 == 0) {
>             for (int i = 0; i < 500; ++i) {
>                 volatile auto* v = new Vector3();
>                 delete static_cast<const Vector3*>(v);
>             }
>         }
>
>         // 每 5 帧做一次大批量分配
>         if (frame % 5 == 0) {
>             std::vector<int*> temp;
>             for (int i = 0; i < 200; ++i)
>                 temp.push_back(new int(i));
>             // 故意不释放一半（模拟内存泄漏检测场景）
>             for (size_t i = 0; i < temp.size(); i += 2)
>                 delete temp[i];
>             // 注意：另一半泄漏了——end_frame 报告中 allocs > frees
>             // 在实际调试中用 total report 发现泄漏
>         }
>
>         SimpleAllocTracker::instance().end_frame(frame);
>     }
>
>     SimpleAllocTracker::instance().report_total();
>     return 0;
> }
> ```

> [!tip]- 练习 2 参考答案：PMR 粒子系统优化
> ```cpp
> #include <iostream>
> #include <memory_resource>
> #include <vector>
> #include <chrono>
> #include <iomanip>
>
> struct Particle {
>     float x, y, z;
>     float vx, vy, vz;
>     float life;
> };
>
> constexpr int FRAMES          = 60;
> constexpr int PARTICLES       = 50000;
> constexpr size_t BUFFER_SIZE  = PARTICLES * sizeof(Particle) * 2; // 留有余量
>
> // ============ 改造前：标准 std::vector ============
> double bench_default_vector() {
>     double total_us = 0;
>
>     for (int f = 0; f < FRAMES; ++f) {
>         auto start = std::chrono::high_resolution_clock::now();
>
>         std::vector<Particle> particles;
>         particles.reserve(PARTICLES);
>
>         for (int i = 0; i < PARTICLES; ++i)
>             particles.push_back({1.0f, 2.0f, 3.0f, 0.1f, 0.2f, 0.3f, 5.0f});
>
>         for (auto& p : particles) {
>             p.x += p.vx;
>             p.y += p.vy;
>             p.z += p.vz;
>             p.life -= 0.016f;
>         }
>
>         auto end = std::chrono::high_resolution_clock::now();
>         total_us += std::chrono::duration_cast<std::chrono::microseconds>(
>             end - start).count();
>     }
>
>     return total_us / FRAMES;
> }
>
> // ============ 改造后：std::pmr::vector + monotonic_buffer_resource ============
> double bench_pmr_vector() {
>     double total_us = 0;
>
>     // 在栈上预分配缓冲区
>     char buffer[BUFFER_SIZE];
>     std::pmr::monotonic_buffer_resource pool(
>         buffer, sizeof(buffer),
>         std::pmr::null_memory_resource());  // 不回退到堆 — 测试纯粹栈分配
>
>     for (int f = 0; f < FRAMES; ++f) {
>         auto start = std::chrono::high_resolution_clock::now();
>
>         // pmr::vector 从 monotonic buffer 分配
>         std::pmr::vector<Particle> particles(&pool);
>         particles.reserve(PARTICLES);
>
>         for (int i = 0; i < PARTICLES; ++i)
>             particles.push_back({1.0f, 2.0f, 3.0f, 0.1f, 0.2f, 0.3f, 5.0f});
>
>         for (auto& p : particles) {
>             p.x += p.vx;
>             p.y += p.vy;
>             p.z += p.vz;
>             p.life -= 0.016f;
>         }
>
>         auto end = std::chrono::high_resolution_clock::now();
>         total_us += std::chrono::duration_cast<std::chrono::microseconds>(
>             end - start).count();
>
>         // 帧结束 — 一次性回收所有内存
>         pool.release();
>     }
>
>     return total_us / FRAMES;
> }
>
> int main() {
>     std::cout << "=== PMR 粒子系统性能对比 ===\n";
>     std::cout << "Particles per frame: " << PARTICLES << "\n";
>     std::cout << "Frames: " << FRAMES << "\n\n";
>
>     // 预热
>     bench_default_vector();
>     bench_pmr_vector();
>
>     double default_avg = bench_default_vector();
>     double pmr_avg     = bench_pmr_vector();
>
>     double speedup = default_avg / pmr_avg;
>
>     std::cout << std::fixed << std::setprecision(1);
>     std::cout << "std::vector           avg: " << std::setw(8) << default_avg << " us/frame\n";
>     std::cout << "pmr::vector + mono    avg: " << std::setw(8) << pmr_avg     << " us/frame\n";
>     std::cout << "Speedup:              " << std::setw(6) << speedup << "x\n\n";
>
>     std::cout << "分析：pmr::vector 从预分配的栈缓冲区分配，\n"
>               << "  避免了 50000 次 malloc 调用。monotonic_buffer_resource\n"
>               << "  的 allocate 仅为 bump pointer（约 2-5ns），\n"
>               << "  而 malloc 每次需要数十到数百纳秒。\n"
>               << "  更重要的是，帧结束时仅需一次 release()，\n"
>               << "  而不是 50000 次 free，极大减少分配器内部碎片整理开销。\n";
>
>     return 0;
> }
> ```

> [!info]- 思考题 3 参考答案：多级分配追踪器
> ```cpp
> #include <cstdlib>
> #include <new>
> #include <iostream>
> #include <string>
> #include <unordered_map>
> #include <iomanip>
> #include <algorithm>
> #include <mutex>
>
> // ============ 分配类别 Tag ============
> struct PhysicsTag   { static constexpr const char* name = "Physics";   };
> struct RenderingTag { static constexpr const char* name = "Rendering"; };
> struct AudioTag     { static constexpr const char* name = "Audio";     };
> struct GenericTag   { static constexpr const char* name = "Generic";   };
>
> // ============ 分配记录 ============
> struct AllocRecord {
>     void* ptr;
>     size_t size;
>     const char* category;
> };
>
> // ============ 每类别统计 ============
> struct CategoryStats {
>     size_t alloc_count   = 0;
>     size_t free_count    = 0;
>     size_t total_bytes   = 0;   // 当前活跃字节
>     size_t peak_bytes    = 0;
>     size_t leaked_count  = 0;
>     size_t leaked_bytes  = 0;
> };
>
> // ============ 多级追踪器（单例，线程安全） ============
> class MultiLevelAllocTracker {
> public:
>     static MultiLevelAllocTracker& instance() {
>         static MultiLevelAllocTracker t;
>         return t;
>     }
>
>     // 按类别记录分配
>     void on_alloc(void* ptr, size_t size, const char* category) {
>         std::lock_guard<std::mutex> lock(mutex_);
>
>         auto& stats = category_stats_[category];
>         stats.alloc_count++;
>         stats.total_bytes += size;
>         stats.peak_bytes = std::max(stats.peak_bytes, stats.total_bytes);
>
>         live_allocs_[ptr] = {ptr, size, category};
>
>         total_.alloc_count++;
>         total_.total_bytes += size;
>         total_.peak_bytes = std::max(total_.peak_bytes, total_.total_bytes);
>     }
>
>     void on_free(void* ptr) {
>         std::lock_guard<std::mutex> lock(mutex_);
>
>         auto it = live_allocs_.find(ptr);
>         if (it == live_allocs_.end()) {
>             std::cerr << "[Tracker] WARNING: freeing unknown ptr " << ptr << "\n";
>             return;
>         }
>
>         const auto& rec = it->second;
>         auto& stats = category_stats_[rec.category];
>         stats.free_count++;
>         stats.total_bytes -= rec.size;
>         total_.free_count++;
>         total_.total_bytes -= rec.size;
>
>         live_allocs_.erase(it);
>     }
>
>     // 层级报告
>     void report() const {
>         std::lock_guard<std::mutex> lock(mutex_);
>
>         std::cout << "\n============================================================\n";
>         std::cout << "           Multi-Level Allocation Report\n";
>         std::cout << "============================================================\n\n";
>
>         // 总体统计
>         std::cout << "--- Overall ---\n";
>         print_stats("TOTAL", total_);
>
>         // 每类别统计
>         std::cout << "\n--- By Category ---\n";
>         std::cout << std::left
>                   << std::setw(14) << "Category"
>                   << std::setw(10) << "Allocs"
>                   << std::setw(10) << "Frees"
>                   << std::setw(12) << "Active(B)"
>                   << std::setw(12) << "Peak(B)"
>                   << std::setw(10) << "Leaked\n";
>         std::cout << std::string(68, '-') << "\n";
>
>         for (auto& [cat, stats] : category_stats_) {
>             std::cout << std::left
>                       << std::setw(14) << cat
>                       << std::setw(10) << stats.alloc_count
>                       << std::setw(10) << stats.free_count
>                       << std::setw(12) << stats.total_bytes
>                       << std::setw(12) << stats.peak_bytes
>                       << std::setw(10) << (stats.alloc_count - stats.free_count)
>                       << "\n";
>         }
>
>         // 泄漏报告
>         if (!live_allocs_.empty()) {
>             std::cout << "\n--- LEAK DETECTION ---\n";
>             std::cout << "Live allocations: " << live_allocs_.size() << "\n";
>
>             // 按类别分组汇总泄漏
>             std::unordered_map<std::string, std::pair<size_t, size_t>> leak_by_cat;
>             for (auto& [ptr, rec] : live_allocs_) {
>                 auto& [cnt, bytes] = leak_by_cat[rec.category];
>                 cnt++;
>                 bytes += rec.size;
>             }
>
>             for (auto& [cat, info] : leak_by_cat) {
>                 std::cout << "  " << cat << ": "
>                           << info.first << " blocks, "
>                           << info.second << " bytes\n";
>             }
>         } else {
>             std::cout << "\n--- No leaks detected ---\n";
>         }
>     }
>
>     void reset() {
>         std::lock_guard<std::mutex> lock(mutex_);
>         category_stats_.clear();
>         live_allocs_.clear();
>         total_ = CategoryStats{};
>     }
>
> private:
>     MultiLevelAllocTracker() = default;
>
>     static void print_stats(const char* name, const CategoryStats& s) {
>         std::cout << "  " << name << ": "
>                   << s.alloc_count << " allocs, "
>                   << s.free_count << " frees, "
>                   << "active: " << s.total_bytes << "B, "
>                   << "peak: " << s.peak_bytes << "B\n";
>     }
>
>     mutable std::mutex mutex_;
>     std::unordered_map<std::string, CategoryStats> category_stats_;
>     std::unordered_map<void*, AllocRecord> live_allocs_;
>     CategoryStats total_;
> };
>
> // ============ 带 Tag 的 new 重载（演示用） ============
> // 实际使用中可以通过模板参数自动获取类别名
> template<typename Category>
> void* tagged_new(size_t size) {
>     void* p = std::malloc(size);
>     if (!p) throw std::bad_alloc();
>     MultiLevelAllocTracker::instance().on_alloc(p, size, Category::name);
>     return p;
> }
>
> template<typename Category>
> void tagged_delete(void* p) {
>     MultiLevelAllocTracker::instance().on_free(p);
>     std::free(p);
> }
>
> // ============ 模拟引擎使用 ============
> int main() {
>     MultiLevelAllocTracker::instance().reset();
>
>     std::cout << "=== Multi-Level Allocation Tracker Demo ===\n";
>
>     // 物理系统分配
>     {
>         std::vector<void*> physics_ptrs;
>         for (int i = 0; i < 100; ++i) {
>             physics_ptrs.push_back(tagged_new<PhysicsTag>(256));
>         }
>         // 释放 80 个
>         for (int i = 0; i < 80; ++i)
>             tagged_delete<PhysicsTag>(physics_ptrs[i]);
>         // 剩余 20 个故意不释放 → 模拟泄漏
>     }
>
>     // 渲染系统分配
>     {
>         std::vector<void*> render_ptrs;
>         for (int i = 0; i < 200; ++i) {
>             render_ptrs.push_back(tagged_new<RenderingTag>(512));
>         }
>         for (int i = 0; i < 200; ++i)
>             tagged_delete<RenderingTag>(render_ptrs[i]);
>     }
>
>     // 音频系统分配
>     {
>         for (int i = 0; i < 50; ++i) {
>             void* p = tagged_new<AudioTag>(128);
>             tagged_delete<AudioTag>(p);
>         }
>     }
>
>     MultiLevelAllocTracker::instance().report();
>
>     std::cout << "\n预期：Physics 有 20 个泄漏块（5,120 bytes），"
>               << "Rendering 和 Audio 无泄漏。\n";
>
>     return 0;
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- **深度探索**: `docs/deep-dives/custom-allocators-arena.md` — 913 行 Arena 完整分析
- **深度探索**: `docs/deep-dives/cpp-pmr-polymorphic-memory-resources.md` — PMR 详尽分析
- **Andrei Alexandrescu**: *Modern C++ Design*, Ch4 — 小型对象分配器
- **Jason Gregory**: *Game Engine Architecture*, Ch5.4 — 游戏引擎内存管理
- **Christian Gyrling**: [2015 GDC — 内存管理](https://www.gdcvault.com/)
- **mimalloc**: [Microsoft/mimalloc](https://github.com/microsoft/mimalloc) — 高质量通用分配器，引擎兜底首选

---

## 常见陷阱

### 陷阱 1: 假设 `new`/`delete` 开销可以忽略

```cpp
// 错误观念："new 和 delete 很快，现代分配器已经优化好了"
for (int i = 0; i < 100000; ++i) {
    auto* cmd = new RenderCommand();  // 每帧 10 万次 new → ~3ms 仅分配时间
    // ...
    delete cmd;
}
```

**现实**：即使是 tcmalloc/jemalloc，10 万次小对象分配/释放也需要毫秒级时间。16.6ms 帧预算中，3ms 花在分配器上就是 18% —— 不可接受。解决方案：池分配器或帧分配器。

### 陷阱 2: PMR `deallocate` 是空操作

`std::pmr::monotonic_buffer_resource::do_deallocate()` 是 **no-op** —— 它不会真正释放内存，也不会将该内存标记为可复用：

```cpp
char buf[1024];
std::pmr::monotonic_buffer_resource arena(buf, sizeof(buf));
std::pmr::vector<int> vec(&arena);

vec.push_back(1);
vec.clear();           // 调用了 deallocate → 但内存没回收！
vec.push_back(2);      // 从 arena 当前位置继续分配 → 浪费了之前的内存
```

**教训**：`monotonic_buffer_resource` 只适用于"整个容器生命周期与 arena 一致"的场景。如果你需要复用内存，用 `unsynchronized_pool_resource` 或自定义分配器。

### 陷阱 3: 全局 `operator new` 重载的副作用

```cpp
void* operator new(size_t size) {
    void* p = my_alloc(size);  // 假设你的分配器
    return p;
}
```

**问题**：STL 内部、第三方库、甚至 C++ 运行时都可能调用 `operator new`。你的追踪器会记录所有分配——包括你不需要关心的。而且如果你的自定义分配器有 bug（例如不处理零大小分配），整个程序都会崩溃。

**最佳实践**：使用局部分配器（PMR 或模板参数）而非全局重载来做应用级追踪。全局重载只用于诊断工具。

### 陷阱 4: 忘记对齐

```cpp
// 简单 bump allocator — 错误！
void* allocate(size_t size) {
    void* p = buffer_ + offset_;
    offset_ += size;         // 没有对齐！
    return p;
}
```

许多 CPU 指令（尤其是 SIMD）要求 16/32/64 字节对齐。未对齐访问在 x86 上可能只"慢一些"，在 ARM 上可能触发总线错误。始终对齐 `allocate` 返回的指针。

### 陷阱 5: 在释放后使用分配器的内存

```cpp
auto* p = frame_allocator.allocate(64);
frame_allocator.reset();       // p 现在悬垂！
render_command(p);             // 未定义行为
```

帧分配器的 `reset()` 使所有之前分配的指针变为悬垂。引擎中常见的 Bug 是：在帧中段获取了帧分配器的指针，帧尾 `reset()` 后又在下一帧的异步回调中使用——此时该内存可能已被新帧的数据覆盖。
