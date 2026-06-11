---
title: "Arena 分配器与区域内存管理"
updated: 2026-06-05
---

# Arena 分配器与区域内存管理

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 自定义分配器入门（第 8 节）、栈分配器与帧分配器（第 10 节）
> C++ 标准: C++11（Arena 基本实现）、C++17（std::pmr::monotonic_buffer_resource）、C++20（std::construct_at）

---

## 1. 概念讲解

### 1.1 什么是 Arena 分配器？

Arena 分配器（又称 Bump Allocator、Region Allocator、Monotonic Allocator）是最简单的自定义分配器。它的核心算法只有一句话：**维护一个指针，分配时向前移动指针，释放时整体重置**。

```
初始状态（8KB 缓冲区）:
[oooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooo]
 ^ptr

分配 256 字节 → 返回 ptr，ptr += 256:
[AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAoooooooooooooooooooooooooooooooo]
                                  ^ptr

分配 128 字节 → 返回 ptr，ptr += 128:
[AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBoooooooooooooooo]
                                                      ^ptr

reset() → ptr 回到起点，整个缓冲区"瞬间清空":
[oooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooo]
 ^ptr
```

与标准 `malloc`/`free` 相比，Arena 的特点非常鲜明：

| 特性 | malloc/free | Arena |
|------|------------|-------|
| 分配 | O(log n) 或更差，搜索空闲链表 | O(1)，指针加法 |
| 释放 | O(log n)，可能需要合并相邻块 | 无单次释放操作 |
| 批量释放 | O(n) — 逐个 free | O(1) — reset() |
| 碎片 | 外部碎片随时间累积 | **零外部碎片**（从不断裂） |
| 线程安全 | 通常需要全局锁 | 无锁（单线程使用） |
| 元数据开销 | 每块 8-16 字节 | 零（无头部信息） |

### 1.2 "从不单独释放"是特性，不是 Bug

Arena 最令人困惑的特性是：**它没有 `free()` 方法**。你不能释放单个对象。初看这是严重的限制，但在游戏引擎中，这恰恰是最大的优势：

- **零碎片**：因为没有"归还-再分配"的循环，内存布局是一块连续的、永远向前增长的区域，永远不会出现空洞
- **零释放开销**：`reset()` 只是一条赋值语句，不遍历任何数据结构
- **数据局部性**：所有对象按分配顺序紧密排列，缓存命中率极高
- **无内存泄漏检测负担**：Arena 析构时整批释放，不存在"忘记释放某个对象"的问题

在游戏引擎中，大量资源具有 **统一的生命周期**：

- **关卡/场景资源**：加载关卡时分配所有模型、纹理、碰撞体，切换关卡时全部释放
- **帧临时数据**：每帧产生的绘制命令、变换矩阵、裁剪结果，帧结束时丢弃
- **加载期临数据**：资源烹饪（cooking）、序列化反序列化过程的中间产物
- **物理中间结果**：GJK 单形体、EPA 多面体等纯数学结构

这些场景中，"单独释放某个对象"的需求从未出现过——所有对象同时死亡。Arena 为这种模式量身定做。

### 1.3 标准库中的 Arena：`std::pmr::monotonic_buffer_resource`（C++17）

C++17 在 `<memory_resource>` 中引入了 `std::pmr::monotonic_buffer_resource`，这就是标准库的 Arena 实现：

```cpp
#include <memory_resource>
#include <vector>

// 使用栈上的 64KB 缓冲区作为 Arena
char buffer[65536];
std::pmr::monotonic_buffer_resource arena(buffer, sizeof(buffer));

// 容器使用 Arena 分配
std::pmr::vector<int> numbers(&arena);  // 所有内部分配从 arena 走
for (int i = 0; i < 1000; ++i) numbers.push_back(i);

// arena.release() 释放所有内部 buffer，但用户提供的 buffer 不受影响
arena.release();
```

关键行为：`monotonic_buffer_resource::deallocate()` 是**空操作**（no-op）。调用后内存不会被回收，也不会被复用。这是有意为之——Arena 的哲学就是"不关心单个释放"。

### 1.4 嵌套 Arena（Nested Arena）

对于具有层级生命周期的系统（如引擎子系统生命周期 ⊆ 关卡生命周期），可以使用**嵌套 Arena** 模式：

```
全局 Arena（整个游戏生命周期）
├── 关卡 Arena（单次关卡生命周期）
│   ├── 资源加载 Arena（关卡加载期）
│   │   ├── Texture 数据
│   │   └── Mesh 数据
│   └── 关卡运行时 Arena（游戏进行中）
│       ├── Entity 动态数据
│       └── 脚本状态
└── 帧 Arena（每帧重置）
    ├── 绘制命令
    └── 临时变换矩阵
```

子 Arena 从父 Arena 中分配其工作内存——当父 Arena 重置时，所有子 Arena 的内存随之释放。

### 1.5 Arena 与析构函数

默认 Arena 不调用析构函数。对于持有外部资源（文件句柄、GPU 资源、网络连接）的类型，这会导致资源泄漏。解决方案有二：

**方案一：仅将平凡可析构类型放入 Arena** — 纯数据、POD、数学类型。这是最常见的做法，也是性能最优的方案。

**方案二：跟踪析构函数列表** — 维护一个函数指针列表，`reset()` 时逆序调用。此方案需要为每个分配到 Arena 的对象注册析构回调。

LLVM 的做法（`SpecificBumpPtrAllocator<T>`）：对特定类型 T，在分配器中维护一个析构函数指针数组，`DestroyAll()` 时逆序调用。

### 1.6 内存碎片详解

**外部碎片（External Fragmentation）**：总空闲内存足够，但没有连续的大块能满足分配请求。

```
[malloc 分配的典型碎片场景]
分配 A(128B) → 分配 B(64B) → 分配 C(256B) → 释放 B
结果: [A(128)][空洞(64)][C(256)]
再请求 128B → 找不到连续 128B！(空洞只有 64B)
```

**内部碎片（Internal Fragmentation）**：分配的空间大于实际请求。由对齐填充和分配器元数据产生。

Arena 分配器**零外部碎片**——因为从不归还，所以永远不会产生"空洞"。这是 Arena 在长期运行（数小时游戏）中保持稳定性能的根本原因。

### 1.7 分配器选择决策矩阵

| 分配模式 | 推荐分配器 | 原因 |
|---------|----------|------|
| 同生命周期大批量对象 | **Arena** | O(1) 分配 + 批量释放 |
| 固定大小频繁分配/释放 | 池分配器 | 无碎片、快速复用 |
| LIFO 分配/释放 | 栈分配器 | O(1) + 部分回滚 |
| 混合模式 | Arena + 池组合 | 关卡从 Arena 分配、实体从池分配 |
| 随机大小随机生命周期 | malloc | 没有更好的选择 |

---

## 2. 代码示例

### 2.1 完整 Arena 分配器实现（150+ 行）

```cpp
// arena_allocator.h — 完整的 Bump Allocator 实现
// 编译: g++ -std=c++20 -O2 arena_demo.cpp -o arena_demo

#include <cstddef>      // size_t
#include <cstdint>      // uintptr_t
#include <cstdlib>      // malloc, free
#include <cstring>      // memcpy
#include <new>          // placement new
#include <type_traits>  // is_trivially_destructible_v
#include <vector>
#include <functional>
#include <cassert>
#include <iostream>

// ============================================================
// 1. 基础 Arena 分配器 — 最简单的 bump allocator
// ============================================================
class ArenaAllocator {
public:
    explicit ArenaAllocator(size_t size_bytes)
        : m_buffer(static_cast<char*>(std::malloc(size_bytes)))
        , m_size(size_bytes)
        , m_offset(0)
    {
        assert(m_buffer && "Failed to allocate arena buffer");
    }

    ~ArenaAllocator() {
        std::free(m_buffer);
    }

    // 禁止拷贝
    ArenaAllocator(const ArenaAllocator&) = delete;
    ArenaAllocator& operator=(const ArenaAllocator&) = delete;

    // 允许移动
    ArenaAllocator(ArenaAllocator&& other) noexcept
        : m_buffer(other.m_buffer), m_size(other.m_size), m_offset(other.m_offset)
    {
        other.m_buffer = nullptr;
        other.m_size = 0;
        other.m_offset = 0;
    }

    // 分配指定大小的内存，可选对齐（必须是 2 的幂）
    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        // 计算对齐后的指针位置
        uintptr_t raw_addr = reinterpret_cast<uintptr_t>(m_buffer + m_offset);
        uintptr_t aligned_addr = (raw_addr + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned_addr - raw_addr;

        size_t total_needed = padding + size;
        if (m_offset + total_needed > m_size) {
            return nullptr;  // 空间不足
        }

        m_offset += total_needed;
        void* result = reinterpret_cast<void*>(aligned_addr);
        m_alloc_count++;
        return result;
    }

    // 分配并构造一个类型 T 的对象（使用 placement new）
    template <typename T, typename... Args>
    T* create(Args&&... args) {
        void* mem = allocate(sizeof(T), alignof(T));
        if (!mem) return nullptr;
        return ::new (mem) T(std::forward<Args>(args)...);
    }

    // 分配 n 个 T 的数组（不调用构造函数）
    template <typename T>
    T* allocate_array(size_t count) {
        return static_cast<T*>(allocate(sizeof(T) * count, alignof(T)));
    }

    // 重置：将所有分配"一键释放"（不调用析构！）
    void reset() {
        m_offset = 0;
        m_alloc_count = 0;
    }

    // 查询
    size_t used()      const { return m_offset; }
    size_t capacity()  const { return m_size; }
    size_t alloc_count() const { return m_alloc_count; }

private:
    char*  m_buffer;
    size_t m_size;
    size_t m_offset;
    size_t m_alloc_count = 0;
};

// ============================================================
// 2. 带析构跟踪的 Arena（处理非平凡类型）
// ============================================================
class TrackedArena {
public:
    explicit TrackedArena(size_t size_bytes)
        : m_arena(size_bytes) {}

    ~TrackedArena() {
        destroy_all();
    }

    // 分配未初始化的内存
    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        return m_arena.allocate(size, alignment);
    }

    // 分配并构造对象（自动注册析构函数）
    template <typename T, typename... Args>
    T* create(Args&&... args) {
        void* mem = m_arena.allocate(sizeof(T), alignof(T));
        if (!mem) return nullptr;
        T* obj = ::new (mem) T(std::forward<Args>(args)...);

        // 只有非平凡析构类型才需要注册
        if constexpr (!std::is_trivially_destructible_v<T>) {
            m_destructors.push_back([obj]() { obj->~T(); });
        }
        return obj;
    }

    // 逆序调用所有注册的析构函数，然后重置 Arena
    void reset() {
        destroy_all();
        m_arena.reset();
    }

    size_t used()      const { return m_arena.used(); }
    size_t capacity()  const { return m_arena.capacity(); }

private:
    void destroy_all() {
        // 逆序析构 — LIFO 确保依赖关系正确
        for (auto it = m_destructors.rbegin(); it != m_destructors.rend(); ++it) {
            (*it)();
        }
        m_destructors.clear();
    }

    ArenaAllocator m_arena;
    std::vector<std::function<void()>> m_destructors;
};

// ============================================================
// 3. 嵌套 Arena — 子 Arena 从父 Arena 分配
// ============================================================
class NestedArena {
public:
    // 子 Arena 不自己管理内存，而是从父 Arena 中切分一块
    NestedArena(ArenaAllocator& parent, size_t size_bytes)
        : m_parent(parent)
        , m_buffer(static_cast<char*>(parent.allocate(size_bytes)))
        , m_size(m_buffer ? size_bytes : 0)
        , m_offset(0)
    {}

    // 子 Arena 不支持移动（memory 来自父 Arena）
    NestedArena(const NestedArena&) = delete;
    NestedArena& operator=(const NestedArena&) = delete;

    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        uintptr_t raw_addr = reinterpret_cast<uintptr_t>(m_buffer + m_offset);
        uintptr_t aligned_addr = (raw_addr + alignment - 1) & ~(alignment - 1);
        size_t padding = aligned_addr - raw_addr;

        if (m_offset + padding + size > m_size) return nullptr;

        m_offset += padding + size;
        return reinterpret_cast<void*>(aligned_addr);
    }

    template <typename T, typename... Args>
    T* create(Args&&... args) {
        void* mem = allocate(sizeof(T), alignof(T));
        if (!mem) return nullptr;
        return ::new (mem) T(std::forward<Args>(args)...);
    }

    void reset() { m_offset = 0; }

    size_t used()     const { return m_offset; }
    size_t capacity() const { return m_size; }

private:
    ArenaAllocator& m_parent;  // 不拥有内存，只引用
    char*  m_buffer;
    size_t m_size;
    size_t m_offset;
};

// ============================================================
// 4. 引擎用例：Arena 驱动的关卡加载系统
// ============================================================
struct Mesh {
    const char* name;
    int vertex_count;
    int index_count;
    float* vertices;  // 从 Arena 分配
    uint32_t* indices;

    Mesh(const char* n, int vc, int ic, float* v, uint32_t* ind)
        : name(n), vertex_count(vc), index_count(ic), vertices(v), indices(ind) {}
};

struct Texture {
    const char* name;
    int width, height;
    uint8_t* pixels;  // 从 Arena 分配

    Texture(const char* n, int w, int h, uint8_t* px)
        : name(n), width(w), height(h), pixels(px) {}
};

class LevelLoader {
public:
    LevelLoader(size_t arena_size_mb = 64)
        : m_level_arena(arena_size_mb * 1024 * 1024) {}

    // 加载整个关卡 — 所有资源从 m_level_arena 分配
    bool load_level(const char* level_name) {
        std::cout << "加载关卡: " << level_name << "\n";

        // 加载 3 个 Mesh（模拟）
        for (int i = 0; i < 3; ++i) {
            float* verts = m_level_arena.allocate_array<float>(100);
            uint32_t* inds = m_level_arena.allocate_array<uint32_t>(300);
            for (int j = 0; j < 100; ++j) verts[j] = static_cast<float>(j);
            for (int j = 0; j < 300; ++j) inds[j] = static_cast<uint32_t>(j);

            char* name_buf = m_level_arena.allocate_array<char>(32);
            snprintf(name_buf, 32, "%s_mesh_%d", level_name, i);

            auto* mesh = m_level_arena.create<Mesh>(name_buf, 100, 300, verts, inds);
            m_meshes.push_back(mesh);
        }

        // 加载 2 个纹理（模拟 — 每个 64KB）
        for (int i = 0; i < 2; ++i) {
            uint8_t* pixels = m_level_arena.allocate_array<uint8_t>(64 * 1024);
            char* name_buf = m_level_arena.allocate_array<char>(32);
            snprintf(name_buf, 32, "%s_tex_%d", level_name, i);

            auto* tex = m_level_arena.create<Texture>(name_buf, 256, 256, pixels);
            m_textures.push_back(tex);
        }

        std::cout << "  分配了 " << m_meshes.size() << " Mesh, "
                  << m_textures.size() << " Texture\n";
        std::cout << "  内存使用: " << m_level_arena.used() / 1024.0f << " KB\n";
        return true;
    }

    // 卸载关卡 — 一键释放所有资源
    void unload_level() {
        std::cout << "卸载关卡 — 释放 " << m_level_arena.used() / 1024.0f << " KB\n";
        m_meshes.clear();
        m_textures.clear();
        m_level_arena.reset();  // O(1) — 所有内存瞬时归还
    }

private:
    ArenaAllocator m_level_arena;
    std::vector<Mesh*> m_meshes;    // 指向 Arena 内的对象
    std::vector<Texture*> m_textures;
};
```

### 2.2 Arena 性能对比演示

```cpp
// arena_benchmark.cpp — Arena vs malloc 性能对比
#include <chrono>
#include <vector>
#include <random>
#include <iomanip>

// ============================================================
// 碎片化测量工具
// ============================================================
struct AllocRecord {
    void* ptr;
    size_t size;
};

// 测量 Arena: 分配 N 次，然后 reset
double bench_arena(size_t num_allocs) {
    ArenaAllocator arena(128 * 1024 * 1024); // 128MB

    auto start = std::chrono::high_resolution_clock::now();
    for (size_t i = 0; i < num_allocs; ++i) {
        void* p = arena.allocate(64 + (i % 8) * 16, 16);
        if (!p) { std::cerr << "Arena OOM at " << i << "\n"; break; }
    }
    arena.reset();
    auto end = std::chrono::high_resolution_clock::now();

    return std::chrono::duration<double, std::micro>(end - start).count();
}

// 测量 malloc/free: 分配 N 次，再逐个 free
double bench_malloc(size_t num_allocs) {
    std::vector<AllocRecord> records;
    records.reserve(num_allocs);

    auto start = std::chrono::high_resolution_clock::now();

    // 分配
    for (size_t i = 0; i < num_allocs; ++i) {
        size_t sz = 64 + (i % 8) * 16;
        void* p = std::malloc(sz);
        records.push_back({p, sz});
    }

    // 释放（逆序 — 对 malloc 最友好，减少碎片）
    for (auto it = records.rbegin(); it != records.rend(); ++it) {
        std::free(it->ptr);
    }

    auto end = std::chrono::high_resolution_clock::now();
    return std::chrono::duration<double, std::micro>(end - start).count();
}

// 碎片率测量：分配 + 每隔一个释放 → 测量最大连续空闲块
double measure_fragmentation(size_t num_allocs) {
    std::vector<void*> mallocs;
    mallocs.reserve(num_allocs);

    // 分配所有块
    for (size_t i = 0; i < num_allocs; ++i) {
        mallocs.push_back(std::malloc(64 + (i % 4) * 32));
    }

    // 每隔一个释放 → 制造碎片
    for (size_t i = 0; i < num_allocs; i += 2) {
        std::free(mallocs[i]);
    }

    // Arena 模拟：分配同样数量，但不释放 → 碎片率 = 0
    // malloc: 尝试分配一个较大的块来估算最大连续空闲块
    size_t max_contiguous = 0;
    for (size_t attempt = 8 * 1024 * 1024; attempt >= 64; attempt /= 2) {
        void* p = std::malloc(attempt);
        if (p) {
            max_contiguous = attempt;
            std::free(p);
            break;
        }
    }

    // 清理剩余的块
    for (size_t i = 1; i < num_allocs; i += 2) {
        std::free(mallocs[i]);
    }

    // Arena 的碎片率永远是 0（不产生碎片）
    return max_contiguous;
}

int main() {
    std::cout << std::fixed << std::setprecision(1);

    std::cout << "========== Arena vs malloc 性能对比 ==========\n\n";

    const size_t trials[] = {1000, 10000, 100000};

    for (size_t n : trials) {
        std::cout << "--- " << n << " 次分配 ---\n";

        double arena_time = bench_arena(n);
        double malloc_time = bench_malloc(n);

        std::cout << "  Arena:    " << arena_time << " μs\n";
        std::cout << "  malloc:   " << malloc_time << " μs\n";
        std::cout << "  加速比:   " << malloc_time / arena_time << "x\n\n";
    }

    std::cout << "========== 碎片化测试 ==========\n";
    size_t frag_allocs = 10000;
    size_t max_block = measure_fragmentation(frag_allocs);
    std::cout << "malloc: " << frag_allocs << " 次分配 + 每隔一个释放后\n";
    std::cout << "  最大连续空闲块: " << max_block / 1024.0f << " KB\n";
    std::cout << "Arena: 同样操作后碎片率 = 0% (从未释放，无碎片)\n";

    return 0;
}
```

### 2.3 Arena + Pool 混合策略

```cpp
// hybrid_allocator.cpp — Arena + Pool 混合系统
// 实体从池分配（频繁创建/销毁），关卡数据从 Arena 分配

template <typename T, size_t BlockSize = 256>
class PoolAllocator {
    struct Block {
        alignas(T) char data[sizeof(T) * BlockSize];
        bool used[BlockSize] = {};
    };
    std::vector<Block*> blocks_;
    ArenaAllocator& arena_;  // 池的 Block 从 Arena 分配！

public:
    explicit PoolAllocator(ArenaAllocator& arena) : arena_(arena) {}

    T* allocate() {
        // 查找空闲槽位
        for (auto* block : blocks_) {
            for (size_t i = 0; i < BlockSize; ++i) {
                if (!block->used[i]) {
                    block->used[i] = true;
                    return reinterpret_cast<T*>(&block->data[i * sizeof(T)]);
                }
            }
        }
        // 需要新 Block — 从 Arena 分配
        auto* new_block = arena_.create<Block>();
        blocks_.push_back(new_block);
        new_block->used[0] = true;
        return reinterpret_cast<T*>(&new_block->data[0]);
    }

    void deallocate(T* ptr) {
        for (auto* block : blocks_) {
            if (ptr >= reinterpret_cast<T*>(block->data) &&
                ptr < reinterpret_cast<T*>(block->data + BlockSize)) {
                size_t idx = ptr - reinterpret_cast<T*>(block->data);
                block->used[idx] = false;
                ptr->~T();
                return;
            }
        }
    }
};

struct Entity {
    float x, y, z;
    int id;
    Entity(int i) : x(0), y(0), z(0), id(i) {}
};

void hybrid_demo() {
    ArenaAllocator level_arena(64 * 1024 * 1024);
    PoolAllocator<Entity> entity_pool(level_arena);

    // 关卡加载：从 Arena 分配关卡资源
    auto* level_mesh = level_arena.create<Mesh>("level_mesh", 5000, 15000,
        level_arena.allocate_array<float>(15000),
        level_arena.allocate_array<uint32_t>(45000));

    // 运行时：实体从池分配（频繁创建/销毁）
    std::vector<Entity*> entities;
    for (int i = 0; i < 100; ++i) {
        entities.push_back(entity_pool.allocate());
        ::new (entities.back()) Entity(i);
    }

    // 消灭一半实体
    for (size_t i = 0; i < entities.size(); i += 2) {
        entity_pool.deallocate(entities[i]);
    }

    // 关卡切换：一键释放所有（Arena + 池的 Block）
    level_arena.reset();
    // 注意：实体池的 Block 失效了，不能再使用！
}
```

---

## 3. 练习

### 练习 1（必做）：构建关卡加载/卸载系统

使用 Arena 分配器实现一个关卡加载系统，满足以下要求：

1. `LevelArena` 在关卡加载时预分配 128MB 内存
2. 关卡包含：100 个 `Mesh`（顶点+索引数据）、50 个 `Texture`（像素数据）、200 个 `Material`（参数数据）
3. 所有数据必须从 Arena 分配，不得使用 `new` 或 `malloc`
4. `unload_level()` 以 O(1) 时间释放所有资源
5. 实现 `get_memory_usage()` 查询当前内存使用量
6. 编写测试：加载 → 卸载 → 再加载（验证 Arena 正确重置）

### 练习 2（必做）：测量 Arena vs malloc 碎片化

1. 编写一个碎片化测试程序：
   - 使用 malloc 分配 10000 个不同大小的块，随机释放其中 50%
   - 测量此时的最大连续空闲块大小
   - 与 Arena 对比：同样分配模式，Arena 的碎片率
2. 输出两个分配器的内存统计：已使用、空闲、最大连续块、碎片率
3. 分析为什么 Arena 的碎片率为零

### 练习 3（选做·挑战）：实现带析构跟踪的多级 Arena

1. 实现 `DestructorTrackingArena`，维护一个类型擦除的析构回调列表
2. 实现两级嵌套 Arena 系统：全局 Arena → 关卡 Arena → 帧 Arena
3. 每个子 Arena 从其父 Arena 分配内存
4. 编写 `NonTrivial` 类（持有文件句柄或动态分配内存），验证析构函数被正确调用
5. 测量析构回调列表的内存开销

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> > // level_arena_system.cpp — 关卡加载/卸载系统
> > #include <cstdlib>
> > #include <cstdint>
> > #include <cstring>
> > #include <cstdio>
> > #include <new>
> > #include <vector>
> > #include <cassert>
> > #include <iostream>
> > 
> > // ============================================================
> > // Arena 分配器
> > // ============================================================
> > class Arena {
> > public:
> >     explicit Arena(size_t size_bytes)
> >         : m_buffer(static_cast<char*>(std::malloc(size_bytes)))
> >         , m_size(size_bytes)
> >         , m_offset(0)
> >     {
> >         assert(m_buffer);
> >     }
> >     ~Arena() { std::free(m_buffer); }
> >     Arena(const Arena&) = delete;
> >     Arena& operator=(const Arena&) = delete;
> > 
> >     void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
> >         uintptr_t raw  = reinterpret_cast<uintptr_t>(m_buffer + m_offset);
> >         uintptr_t aligned = (raw + alignment - 1) & ~(alignment - 1);
> >         size_t padding = aligned - raw;
> >         if (m_offset + padding + size > m_size) return nullptr;
> >         m_offset += padding + size;
> >         return reinterpret_cast<void*>(aligned);
> >     }
> > 
> >     template <typename T, typename... Args>
> >     T* create(Args&&... args) {
> >         void* mem = allocate(sizeof(T), alignof(T));
> >         if (!mem) return nullptr;
> >         return ::new (mem) T(std::forward<Args>(args)...);
> >     }
> > 
> >     template <typename T>
> >     T* allocate_array(size_t count) {
> >         return static_cast<T*>(allocate(sizeof(T) * count, alignof(T)));
> >     }
> > 
> >     void reset() { m_offset = 0; }
> >     size_t used()     const { return m_offset; }
> >     size_t capacity() const { return m_size; }
> > 
> > private:
> >     char*  m_buffer;
> >     size_t m_size;
> >     size_t m_offset;
> > };
> > 
> > // ============================================================
> > // 资源类型
> > // ============================================================
> > struct Mesh {
> >     const char* name;
> >     int vertex_count, index_count;
> >     float*    vertices;
> >     uint32_t* indices;
> > };
> > 
> > struct Texture {
> >     const char* name;
> >     int width, height;
> >     uint8_t* pixels;
> > };
> > 
> > struct Material {
> >     const char* name;
> >     float roughness, metallic;
> >     float base_color[3];
> > };
> > 
> > // ============================================================
> > // LevelArena — 关卡加载系统
> > // ============================================================
> > class LevelArena {
> > public:
> >     LevelArena() : m_arena(128ULL * 1024 * 1024) {}  // 预分配 128 MB
> > 
> >     bool load_level(const char* level_name) {
> >         // 1. 加载 100 个 Mesh
> >         for (int i = 0; i < 100; ++i) {
> >             float*    verts = m_arena.allocate_array<float>(5000);
> >             uint32_t* inds  = m_arena.allocate_array<uint32_t>(15000);
> >             for (int j = 0; j < 5000; ++j) verts[j] = static_cast<float>(j);
> >             for (int j = 0; j < 15000; ++j) inds[j] = static_cast<uint32_t>(j);
> > 
> >             char* name_buf = m_arena.allocate_array<char>(32);
> >             snprintf(name_buf, 32, "%s_mesh_%d", level_name, i);
> >             m_meshes.push_back({name_buf, 5000, 15000, verts, inds});
> >         }
> > 
> >         // 2. 加载 50 个 Texture
> >         for (int i = 0; i < 50; ++i) {
> >             uint8_t* pixels = m_arena.allocate_array<uint8_t>(256 * 256 * 4);
> >             char* name_buf = m_arena.allocate_array<char>(32);
> >             snprintf(name_buf, 32, "%s_tex_%d", level_name, i);
> >             m_textures.push_back({name_buf, 256, 256, pixels});
> >         }
> > 
> >         // 3. 加载 200 个 Material
> >         for (int i = 0; i < 200; ++i) {
> >             float* params = m_arena.allocate_array<float>(4);  // rgbr, metallic, roughness, _
> >             params[0] = 0.8f; params[1] = 0.5f; params[2] = 0.3f;
> >             char* name_buf = m_arena.allocate_array<char>(32);
> >             snprintf(name_buf, 32, "%s_mat_%d", level_name, i);
> >             m_materials.push_back({name_buf, 0.5f, 0.3f, {0.8f, 0.5f, 0.2f}});
> >         }
> > 
> >         std::cout << "Loaded " << level_name << ": "
> >                   << m_meshes.size() << " meshes + "
> >                   << m_textures.size() << " textures + "
> >                   << m_materials.size() << " materials\n";
> >         return true;
> >     }
> > 
> >     void unload_level() {
> >         m_meshes.clear();
> >         m_textures.clear();
> >         m_materials.clear();
> >         m_arena.reset();  // O(1) — 只移动 offset 指针
> >     }
> > 
> >     size_t get_memory_usage() const { return m_arena.used(); }
> > 
> > private:
> >     Arena m_arena;
> >     std::vector<Mesh>     m_meshes;
> >     std::vector<Texture>  m_textures;
> >     std::vector<Material> m_materials;
> > };
> > 
> > int main() {
> >     LevelArena la;
> > 
> >     // 测试：加载 → 卸载 → 再加载
> >     la.load_level("level_01");
> >     std::cout << "Memory after load: " << la.get_memory_usage() / 1024.0f / 1024.0f << " MB\n";
> > 
> >     la.unload_level();
> >     std::cout << "Memory after unload: " << la.get_memory_usage() << " bytes (should be 0)\n";
> >     assert(la.get_memory_usage() == 0);
> > 
> >     la.load_level("level_02");  // 验证 Arena 正确重置后可重用
> >     std::cout << "Memory after reload: " << la.get_memory_usage() / 1024.0f / 1024.0f << " MB\n";
> >     assert(la.get_memory_usage() > 0);
> > 
> >     std::cout << "All checks passed.\n";
> >     return 0;
> > }
> > ```

> [!tip]- 练习 2 参考答案
> ```cpp
> > // fragmentation_test.cpp — Arena vs malloc 碎片化对比
> > #include <cstdlib>
> > #include <cstdio>
> > #include <cstring>
> > #include <vector>
> > #include <algorithm>
> > #include <random>
> > #include <cassert>
> > #include <cstdint>
> > 
> > constexpr size_t NUM_ALLOCS = 10000;
> > 
> > // ─── Arena 碎片测量 ───
> > struct ArenaStats {
> >     size_t used;
> >     size_t free;
> >     size_t max_contiguous;
> >     double fragmentation_rate;
> > };
> > 
> > ArenaStats measure_arena_fragmentation() {
> >     // 一次性分配大缓冲区，模拟所有 malloc 分配的总和
> >     size_t total = 0;
> >     std::vector<size_t> sizes(NUM_ALLOCS);
> >     std::mt19937 rng(42);
> >     std::uniform_int_distribution<size_t> dist(8, 1024);
> >     for (auto& s : sizes) s = dist(rng);
> >     for (auto s : sizes) total += s;
> > 
> >     char* buf = static_cast<char*>(std::malloc(total));
> >     assert(buf);
> >     size_t offset = 0;
> > 
> >     // 模拟 Arena 分配（bump 指针）
> >     for (size_t s : sizes) {
> >         void* p = buf + offset;
> >         offset += s;
> >         (void)p;
> >     }
> > 
> >     ArenaStats result;
> >     result.used = offset;
> >     result.free = total - offset;
> >     // Arena 的"最大连续空闲块" = 剩余全部（没有碎片）
> >     result.max_contiguous = result.free;
> >     // 碎片率 = (总空闲 - 最大连续空闲) / 总空闲 = 0
> >     result.fragmentation_rate = 0.0;
> > 
> >     std::free(buf);
> >     return result;
> > }
> > 
> > // ─── malloc 碎片测量 ───
> > struct MallocStats {
> >     size_t total_allocated;
> >     size_t total_freed;
> >     size_t max_contiguous;      // 最大连续空闲块
> >     double fragmentation_rate;
> > };
> > 
> > MallocStats measure_malloc_fragmentation() {
> >     std::mt19937 rng(42);
> >     std::uniform_int_distribution<size_t> size_dist(8, 1024);
> > 
> >     std::vector<void*> ptrs(NUM_ALLOCS);
> >     size_t total_allocated = 0;
> > 
> >     // 1. 分配 10000 个不同大小的块
> >     for (size_t i = 0; i < NUM_ALLOCS; ++i) {
> >         size_t sz = size_dist(rng);
> >         ptrs[i] = std::malloc(sz);
> >         if (ptrs[i]) total_allocated += sz;
> >     }
> > 
> >     // 2. 随机释放 50%
> >     std::vector<size_t> indices(NUM_ALLOCS);
> >     for (size_t i = 0; i < NUM_ALLOCS; ++i) indices[i] = i;
> >     std::shuffle(indices.begin(), indices.end(), rng);
> > 
> >     size_t total_freed = 0;
> >     for (size_t i = 0; i < NUM_ALLOCS / 2; ++i) {
> >         size_t idx = indices[i];
> >         // 无法精确知道释放的大小，但这对碎片化分析无影响
> >         std::free(ptrs[idx]);
> >         ptrs[idx] = nullptr;
> >         total_freed += size_dist(rng);  // 近似
> >     }
> > 
> >     // 3. 测量最大连续空闲块 — 尝试分配越来越大的块直到失败
> >     size_t max_contiguous = 0;
> >     size_t step = 1024 * 1024;  // 从 1 MB 开始试
> >     while (step >= 8) {
> >         void* p = std::malloc(step);
> >         if (p) {
> >             max_contiguous = step;
> >             std::free(p);
> >             // 尝试更大的块
> >             step += step / 2;
> >             if (step > 256ULL * 1024 * 1024) break;
> >         } else {
> >             step /= 2;
> >         }
> >     }
> > 
> >     // 4. 释放剩余块
> >     for (size_t i = 0; i < NUM_ALLOCS; ++i) {
> >         if (ptrs[i]) std::free(ptrs[i]);
> >     }
> > 
> >     MallocStats result;
> >     result.total_allocated = total_allocated;
> >     result.total_freed     = total_freed;
> >     result.max_contiguous  = max_contiguous;
> >     // 碎片率 = (总空闲 - 最大连续空闲) / 总空闲
> >     size_t net_free = total_allocated - (total_allocated - total_freed);
> >     if (total_freed > 0)
> >         result.fragmentation_rate = 1.0 - static_cast<double>(max_contiguous) / total_freed;
> >     else
> >         result.fragmentation_rate = 0.0;
> >     return result;
> > }
> > 
> > int main() {
> >     printf("===== 碎片化对比: Arena vs malloc =====\n\n");
> > 
> >     auto arena_stats = measure_arena_fragmentation();
> >     auto malloc_stats = measure_malloc_fragmentation();
> > 
> >     printf("--- Arena 分配器 ---\n");
> >     printf("  已使用:     %zu KB\n", arena_stats.used / 1024);
> >     printf("  空闲:       %zu KB\n", arena_stats.free / 1024);
> >     printf("  最大连续块: %zu KB\n", arena_stats.max_contiguous / 1024);
> >     printf("  碎片率:     %.1f%%\n\n", arena_stats.fragmentation_rate * 100);
> > 
> >     printf("--- malloc 分配器 ---\n");
> >     printf("  总分配:     %zu KB\n", malloc_stats.total_allocated / 1024);
> >     printf("  已释放:     %zu KB\n", malloc_stats.total_freed / 1024);
> >     printf("  最大连续块: %zu KB\n", malloc_stats.max_contiguous / 1024);
> >     printf("  碎片率:     %.1f%%\n\n", malloc_stats.fragmentation_rate * 100);
> > 
> >     printf("--- 分析 ---\n");
> >     printf("Arena 碎片率为零的原因:\n");
> >     printf("  1. Arena 使用 bump 指针顺序分配，永不释放单个块\n");
> >     printf("  2. 所有空间在 reset() 时整体回收，不存在\"空洞\"\n");
> >     printf("  3. malloc 在随机释放后产生大量不连续空闲块\n");
> >     printf("  4. 外部碎片导致 malloc 即使总空闲够用，也无法满足大块分配\n");
> > 
> >     return 0;
> > }
> > ```

> [!tip]- 练习 3 参考答案（选做·挑战）
> ```cpp
> > // destructor_tracking_arena.cpp — 带析构跟踪的多级 Arena
> > #include <cstdlib>
> > #include <cstdint>
> > #include <new>
> > #include <functional>
> > #include <vector>
> > #include <cstring>
> > #include <cassert>
> > #include <iostream>
> > #include <fstream>
> > 
> > // Arena 基础（同练习 1）
> > class Arena {
> >     char*  m_buffer;
> >     size_t m_size;
> >     size_t m_offset;
> > public:
> >     explicit Arena(size_t sz)
> >         : m_buffer(static_cast<char*>(std::malloc(sz))), m_size(sz), m_offset(0) {}
> >     ~Arena() { std::free(m_buffer); }
> >     Arena(const Arena&) = delete;
> >     Arena& operator=(const Arena&) = delete;
> > 
> >     void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
> >         uintptr_t raw = reinterpret_cast<uintptr_t>(m_buffer + m_offset);
> >         uintptr_t aligned = (raw + alignment - 1) & ~(alignment - 1);
> >         size_t padding = aligned - raw;
> >         if (m_offset + padding + size > m_size) return nullptr;
> >         m_offset += padding + size;
> >         return reinterpret_cast<void*>(aligned);
> >     }
> >     void reset() { m_offset = 0; }
> >     size_t used()     const { return m_offset; }
> >     size_t capacity() const { return m_size; }
> > };
> > 
> > // ============================================================
> > // DestructorTrackingArena — 类型擦除析构回调
> > // ============================================================
> > class DestructorTrackingArena {
> > public:
> >     // ① 从父 Arena 分配（嵌套场景）
> >     DestructorTrackingArena(Arena& parent, size_t size_bytes)
> >         : m_own_buffer(true), m_size(size_bytes)
> >     {
> >         m_buffer = static_cast<char*>(parent.allocate(size_bytes));
> >         if (!m_buffer) { m_size = 0; return; }
> >     }
> > 
> >     // ② 独立模式（直接 malloc）
> >     explicit DestructorTrackingArena(size_t size_bytes)
> >         : m_own_buffer(false), m_size(size_bytes)
> >     {
> >         m_buffer = static_cast<char*>(std::malloc(size_bytes));
> >         assert(m_buffer);
> >     }
> > 
> >     ~DestructorTrackingArena() {
> >         destroy_all();
> >         if (!m_own_buffer) std::free(m_buffer);
> >     }
> > 
> >     DestructorTrackingArena(const DestructorTrackingArena&) = delete;
> >     DestructorTrackingArena& operator=(const DestructorTrackingArena&) = delete;
> > 
> >     void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
> >         uintptr_t raw = reinterpret_cast<uintptr_t>(m_buffer + m_offset);
> >         uintptr_t aligned = (raw + alignment - 1) & ~(alignment - 1);
> >         size_t padding = aligned - raw;
> >         if (m_offset + padding + size > m_size) return nullptr;
> >         m_offset += padding + size;
> >         return reinterpret_cast<void*>(aligned);
> >     }
> > 
> >     // 构造对象并注册析构回调
> >     template <typename T, typename... Args>
> >     T* create(Args&&... args) {
> >         void* mem = allocate(sizeof(T), alignof(T));
> >         if (!mem) return nullptr;
> >         T* obj = ::new (mem) T(std::forward<Args>(args)...);
> >         if constexpr (!std::is_trivially_destructible_v<T>) {
> >             m_dtors.push_back([obj]() { obj->~T(); });
> >         }
> >         return obj;
> >     }
> > 
> >     // 逆序析构 + 重置
> >     void reset() {
> >         destroy_all();
> >         m_offset = 0;
> >     }
> > 
> >     size_t dtor_count() const { return m_dtors.size(); }
> >     size_t dtor_overhead() const { return m_dtors.capacity() * sizeof(std::function<void()>); }
> > 
> > private:
> >     void destroy_all() {
> >         for (auto it = m_dtors.rbegin(); it != m_dtors.rend(); ++it)
> >             (*it)();
> >         m_dtors.clear();
> >     }
> > 
> >     char*  m_buffer = nullptr;
> >     size_t m_size = 0;
> >     size_t m_offset = 0;
> >     bool   m_own_buffer;  // false → 自己 malloc; true → 来自父 Arena
> >     std::vector<std::function<void()>> m_dtors;
> > };
> > 
> > // ============================================================
> > // NonTrivial — 持有文件句柄 + 动态内存
> > // ============================================================
> > struct NonTrivial {
> >     int   id;
> >     char* heap_data;
> >     FILE* file_handle;
> > 
> >     NonTrivial(int i) : id(i) {
> >         heap_data = new char[256];
> >         snprintf(heap_data, 256, "resource_%d", id);
> >         file_handle = tmpfile();  // 临时文件句柄
> >         std::cout << "  NonTrivial(" << id << ") constructed\n";
> >     }
> > 
> >     ~NonTrivial() {
> >         delete[] heap_data;
> >         if (file_handle) fclose(file_handle);
> >         std::cout << "  ~NonTrivial(" << id << ") destroyed\n";
> >     }
> > };
> > 
> > // ============================================================
> > // 测试入口
> > // ============================================================
> > int main() {
> >     // ─── 三级嵌套 Arena ───
> >     Arena global_arena(64 * 1024 * 1024);  // 64 MB 全局
> > 
> >     std::cout << "=== 两级嵌套 Arena 系统 ===\n\n";
> > 
> >     // 从全局 Arena 切出关卡 Arena
> >     DestructorTrackingArena level_arena(global_arena, 32 * 1024 * 1024);
> >     std::cout << "Global used after level allocation: "
> >               << global_arena.used() / 1024.0f / 1024.0f << " MB\n";
> > 
> >     // 从关卡 Arena 切出帧 Arena
> >     DestructorTrackingArena frame_arena(level_arena, 8 * 1024 * 1024);
> > 
> >     // 分配 NonTrivial 对象（验证析构跟踪）
> >     auto* obj1 = level_arena.create<NonTrivial>(1);
> >     auto* obj2 = level_arena.create<NonTrivial>(2);
> >     auto* obj3 = frame_arena.create<NonTrivial>(3);
> > 
> >     std::cout << "\n析构回调数: " << level_arena.dtor_count()
> >               << " (level) + frame\n";
> > 
> >     // 测量析构回调开销
> >     std::cout << "析构回调列表开销: "
> >               << level_arena.dtor_overhead() << " bytes\n";
> > 
> >     // 帧结束 → 析构帧内的对象
> >     std::cout << "\n--- 帧结束 ---\n";
> >     frame_arena.reset();
> > 
> >     // 关卡结束 → 析构关卡内的对象
> >     std::cout << "\n--- 关卡结束 ---\n";
> >     level_arena.reset();
> > 
> >     std::cout << "\n所有析构函数已正确调用 ✓\n";
> >     return 0;
> > }
> > ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **LLVM BumpPtrAllocator**：`llvm/Support/Allocator.h` — 最经典的 Arena 工业实现，支持 slab 链式扩展和 `SpecificBumpPtrAllocator<T>` 析构跟踪
- **RapidJSON MemoryPoolAllocator**：纯 C++ 实现的 JSON 解析器内置 Arena
- **C++17 `std::pmr::monotonic_buffer_resource`**：[cppreference](https://en.cppreference.com/w/cpp/memory/monotonic_buffer_resource)
- **Jason Gregory《Game Engine Architecture》第 6 章**："Memory Management" 一节对引擎分配器有深入讨论
- **本计划关联深探**：`docs/deep-dives/custom-allocators-arena.md` — Arena 的 7 层深度分析

---

## 常见陷阱

### 陷阱 1：将非平凡析构类型放入普通 Arena

```cpp
// ❌ 错误 — string 持有 char* 内部缓冲，Arena reset() 不会释放
ArenaAllocator arena(4096);
auto* str = arena.create<std::string>("hello, world");
arena.reset();  // 内存泄漏！string 的 char* 缓冲没有被释放

// ✅ 正确方案 1 — 使用 TrackedArena
TrackedArena tracked(4096);
auto* str2 = tracked.create<std::string>("hello");
tracked.reset();  // 析构函数被调用

// ✅ 正确方案 2 — 在 reset() 前手动析构
auto* str3 = arena.create<std::string>("hello");
str3->~basic_string();  // 手动析构
arena.reset();
```

### 陷阱 2：Arena reset() 后继续使用悬垂指针

```cpp
ArenaAllocator arena(4096);
Mesh* mesh = arena.create<Mesh>(...);
Texture* tex = arena.create<Texture>(...);

arena.reset();  // mesh 和 tex 现在指向未定义内存！

// ❌ 未定义行为
mesh->vertex_count = 100;  // 写入已释放的内存

// ✅ 正确 — reset 后所有指针作废，需重新分配
arena.reset();
mesh = arena.create<Mesh>(...);  // 重新分配
```

### 陷阱 3：混合使用 Arena 指针和外部指针

```cpp
ArenaAllocator arena(4096);
auto* mesh = arena.create<Mesh>(...);
auto* tex = arena.create<Texture>(...);

// ❌ 错误 — 把 Arena 内的对象放入外部容器，Arena reset 后容器里全是悬垂指针
std::vector<Mesh*> global_mesh_list;
global_mesh_list.push_back(mesh);  // 危险！
arena.reset();
// global_mesh_list[0] 现在是悬垂指针

// ✅ 正确 — 在 reset 前清空外部引用
global_mesh_list.clear();
arena.reset();
```

### 陷阱 4：对齐计算错误导致未定义行为

```cpp
// ❌ 错误的手动对齐 — 不处理 alignment 不是 2 的幂的情况
void* bad_align_alloc(ArenaAllocator& arena, size_t size, size_t alignment) {
    char* p = static_cast<char*>(arena.allocate(size + alignment));
    // 如果 alignment 不是 2 的幂，(uintptr_t(p) + alignment - 1) & ~(alignment - 1) 是错误的
    return reinterpret_cast<void*>(
        (reinterpret_cast<uintptr_t>(p) + alignment - 1) & ~(alignment - 1)
    );
}

// ✅ 正确 — 使用 std::align 或确保 alignment 是 2 的幂
void* good_align_alloc(ArenaAllocator& arena, size_t size, size_t alignment) {
    assert((alignment & (alignment - 1)) == 0 && "Alignment must be power of 2");
    void* p = arena.allocate(size + alignment - 1);
    size_t space = size + alignment - 1;
    void* aligned = p;
    std::align(alignment, size, aligned, space);  // 标准库函数
    return aligned;
}
```
