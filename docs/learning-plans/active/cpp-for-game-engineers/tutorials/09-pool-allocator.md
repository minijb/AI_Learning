# 09 — 池分配器与自由链表

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 08-自定义分配器入门

---

## 1. 概念讲解

### 池分配器的核心思想

在游戏引擎中，大量对象具有相同的大小：粒子（64B）、子弹（32B）、网络包（512B）、渲染命令（128B）、音频采样块（256B）。这些对象的分配/释放在热路径上频繁发生。

池分配器（Pool Allocator）利用这个"固定大小"的特性：

```
预分配一大块内存，切成 N 个等大的 Slot
→ 分配：从空闲链表中取一个 Slot（O(1)）
→ 释放：将 Slot 插回空闲链表（O(1)）
→ 零碎片：所有 Slot 大小相同，不存在"外部碎片"
→ 极佳缓存局部性：连续 Slot 可能在同一缓存行
```

对固定大小对象的分配，池分配器可以比 `malloc` 快 **10-100 倍**。

### 自由链表的设计

自由链表（Free List）是池分配器的心脏。两种实现方式：

**侵入式自由链表**（引擎首选）：
空闲 Slot 的内存本身被用来存储"下一个空闲 Slot"的指针。不需要额外的链表节点——空闲内存就是节点。

```text
内存布局（每个 Slot 至少 sizeof(void*) 字节）:
┌──────┬──────┬──────┬──────┬──────┐
│ Slot0│ Slot1│ Slot2│ Slot3│ Slot4│  ...
└──┬───┴──┬───┴──┬───┴──┬───┴──────┘
   │      │      │      │
   ▼      ▼      ▼      ▼
[List]→[Slot1]→[Slot2]→[Slot3]→[nullptr]
  free_head_ = &Slot0 (Slot0 被分配出去了)
```

当 Slot 空闲时，其前 `sizeof(void*)` 字节存储指向下一个空闲 Slot 的指针。当 Slot 被分配时，这些字节被用户数据覆盖——用户不需要知道这个机制。

**外部自由链表**（位图/数组）：
用一个独立的 `std::bitset<N>` 或 `bool[N]` 标记每个 Slot 是否空闲。不需要占用 Slot 空间，但需要额外存储和扫描开销。

引擎中侵入式自由链表是标准选择——零额外内存，O(1) 操作。

### 侵入式自由链表的关键约束

```
sizeof(Slot) >= sizeof(void*)   ← 强制性要求！
```

如果 `Slot` 小于一个指针（例如 `char`、`short`），空闲时无法存储 `next` 指针。这种情况下可以用外部位图，或者使用索引代替指针（如果 Slot 数量 < 65536，用 `uint16_t` 索引）。

### 池分配器的完整接口

```cpp
class PoolAllocator {
public:
    void  create(size_t slot_size, size_t num_slots);
    void* allocate();
    void  deallocate(void* ptr);
    void  destroy();

    size_t slot_size()    const;
    size_t num_slots()    const;
    size_t num_used()     const;   // 调试用
    bool   owns(void* p)  const;    // 指针是否来自本池
};
```

### 调试特性

生产级池分配器应内置：

| 特性 | 目的 | 实现 |
|:-----|:-----|:-----|
| **Canary 值** | 检测越界写入 | 在 Slot 头尾写入魔数（`0xDEADBEEF`），alloc/free 时校验 |
| **分配跟踪** | 检测泄漏 | 记录活跃分配数，destroy() 时断言 `num_used == 0` |
| **Double-free 检测** | 防御 UAF | 在 free 时检查该 Slot 是否已在 free list 中 |
| **调用栈记录** | 定位泄漏源 | 每次 alloc 时记录 `__FILE__:__LINE__` |

### 模板包装：Pool<T>

为了让池分配器像 `new`/`delete` 一样自然使用：

```cpp
template<typename T>
class Pool {
    PoolAllocator allocator_;
public:
    Pool(size_t num) { allocator_.create(sizeof(T), num); }

    T* allocate() { return static_cast<T*>(allocator_.allocate()); }
    void deallocate(T* p) { allocator_.deallocate(p); }

    // 支持 STL
    // using value_type = T;
    // T* allocate(size_t n) ...  // std::allocator 接口
};
```

配合重载的 `operator new` / `operator delete`（每个类），可以实现完全透明的池分配：

```cpp
struct Particle {
    float data[8];
    static Pool<Particle> pool;  // 全局池

    void* operator new(size_t) { return pool.allocate(); }
    void operator delete(void* p) { pool.deallocate(static_cast<Particle*>(p)); }
};
```

### 线程安全考虑

基础的池分配器**不是线程安全的**——多个线程同时 `allocate()` / `deallocate()` 会破坏自由链表。引擎中的典型做法：

1. **每线程一个池**：每个工作线程拥有自己的粒子池、命令池。零同步开销。
2. **无锁自由链表**：用 `std::atomic` + CAS 实现 Treiber Stack。开销约 5-10ns/操作。
3. **加锁**：简单但会在高竞争下成为瓶颈。仅用于低频操作。

---

## 2. 代码示例

### 示例 1: 完整的侵入式自由链表池分配器

```cpp
// compile: g++ -std=c++20 -O2 pool_allocator.cpp -o pool_allocator
#include <iostream>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <new>

class PoolAllocator {
public:
    PoolAllocator() = default;

    // 禁止拷贝
    PoolAllocator(const PoolAllocator&) = delete;
    PoolAllocator& operator=(const PoolAllocator&) = delete;

    // 允许移动
    PoolAllocator(PoolAllocator&& other) noexcept {
        *this = std::move(other);
    }
    PoolAllocator& operator=(PoolAllocator&& other) noexcept {
        if (this != &other) {
            destroy();
            memory_      = other.memory_;
            free_head_   = other.free_head_;
            slot_size_   = other.slot_size_;
            num_slots_   = other.num_slots_;
            num_used_    = other.num_used_;
            other.memory_    = nullptr;
            other.free_head_ = nullptr;
            other.num_slots_ = 0;
        }
        return *this;
    }

    void create(size_t slot_size, size_t num_slots) {
        destroy();

        // 确保 Slot 能容纳一个指针（侵入式自由链表）
        if (slot_size < sizeof(void*))
            slot_size = sizeof(void*);

        // 对齐：确保每个 Slot 从对齐边界开始
        slot_size_ = (slot_size + alignof(std::max_align_t) - 1)
                     & ~(alignof(std::max_align_t) - 1);

        num_slots_  = num_slots;
        size_t total = slot_size_ * num_slots;

        memory_ = static_cast<char*>(std::aligned_alloc(alignof(std::max_align_t), total));
        if (!memory_)
            throw std::bad_alloc();

        // 初始化自由链表：将所有 Slot 串联
        free_head_ = reinterpret_cast<void**>(memory_);
        for (size_t i = 0; i < num_slots - 1; ++i) {
            void** current = reinterpret_cast<void**>(memory_ + i * slot_size_);
            void** next    = reinterpret_cast<void**>(memory_ + (i + 1) * slot_size_);
            *current = next;
        }
        void** last = reinterpret_cast<void**>(memory_ + (num_slots - 1) * slot_size_);
        *last = nullptr;  // 链表尾部

        num_used_ = 0;
    }

    void* allocate() {
        if (!free_head_) {
            std::cerr << "[PoolAllocator] OUT OF MEMORY!\n";
            return nullptr;
        }

        void** slot = free_head_;
        free_head_ = static_cast<void**>(*slot);  // 取下一个空闲 Slot
        num_used_++;
        return static_cast<void*>(slot);
    }

    void deallocate(void* ptr) {
        if (!ptr) return;
        assert(owns(ptr) && "Pointer does not belong to this pool!");

        // 将 Slot 插回自由链表头部
        void** slot = static_cast<void**>(ptr);
        *slot = free_head_;
        free_head_ = slot;
        num_used_--;
    }

    void destroy() {
        if (memory_) {
            std::free(memory_);
            memory_ = nullptr;
        }
        free_head_ = nullptr;
        num_slots_ = 0;
        num_used_  = 0;
    }

    bool owns(void* p) const {
        if (!memory_ || !p) return false;
        uintptr_t addr = reinterpret_cast<uintptr_t>(p);
        uintptr_t start = reinterpret_cast<uintptr_t>(memory_);
        uintptr_t end = start + slot_size_ * num_slots_;
        if (addr < start || addr >= end) return false;
        // 确保地址对齐到 Slot 边界
        return (addr - start) % slot_size_ == 0;
    }

    size_t slot_size() const { return slot_size_; }
    size_t num_slots() const { return num_slots_; }
    size_t num_used()  const { return num_used_;  }

    ~PoolAllocator() { destroy(); }

private:
    char*   memory_    = nullptr;
    void**  free_head_ = nullptr;
    size_t  slot_size_ = 0;
    size_t  num_slots_ = 0;
    size_t  num_used_  = 0;
};

// ============ 演示 ============
int main() {
    constexpr size_t NUM_SLOTS = 8;
    constexpr size_t SLOT_SIZE = 64;

    PoolAllocator pool;
    pool.create(SLOT_SIZE, NUM_SLOTS);

    std::cout << "Pool created: " << pool.num_slots() << " slots of "
              << pool.slot_size() << " bytes\n";

    // 分配
    std::vector<void*> ptrs;
    for (size_t i = 0; i < NUM_SLOTS; ++i) {
        void* p = pool.allocate();
        std::cout << "  alloc #" << i << " → " << p
                  << " (used: " << pool.num_used() << ")\n";
        ptrs.push_back(p);
        // 写入数据验证
        std::memset(p, static_cast<int>(i + 1), SLOT_SIZE);
    }

    // 再分配应该返回 nullptr
    void* overflow = pool.allocate();
    std::cout << "  overflow alloc → " << (overflow ? "non-null!" : "nullptr (correct)")
              << "\n";

    // 释放一半
    for (size_t i = 0; i < NUM_SLOTS; i += 2) {
        pool.deallocate(ptrs[i]);
        std::cout << "  free #" << i << " (used: " << pool.num_used() << ")\n";
    }

    // 重新分配 — 应复用刚释放的 Slot
    for (size_t i = 0; i < NUM_SLOTS / 2; ++i) {
        void* p = pool.allocate();
        std::cout << "  re-alloc → " << p << " (used: " << pool.num_used() << ")\n";
        std::memset(p, 0xFF, SLOT_SIZE);
    }

    // 检查 owns()
    void* external = std::malloc(SLOT_SIZE);
    std::cout << "  owns(external) = " << pool.owns(external) << " (should be 0)\n";
    std::cout << "  owns(pool ptr) = " << pool.owns(ptrs[1]) << " (should be 1)\n";
    std::free(external);

    pool.destroy();
    std::cout << "Pool destroyed.\n";
    return 0;
}
```

### 示例 2: 基准测试 — Pool vs malloc

```cpp
// compile: g++ -std=c++20 -O2 pool_benchmark.cpp -o pool_benchmark
#include <iostream>
#include <chrono>
#include <cstdlib>
#include <vector>

// 复用上面的 PoolAllocator（省略类定义，实际使用时 #include）

int main() {
    constexpr size_t NUM_OPS    = 1'000'000;
    constexpr size_t SLOT_SIZE  = 64;
    constexpr size_t NUM_SLOTS  = NUM_OPS;  // 足够大，不会 OOM

    // ===== Pool Allocator =====
    {
        PoolAllocator pool;
        pool.create(SLOT_SIZE, NUM_SLOTS);

        auto start = std::chrono::high_resolution_clock::now();
        for (size_t i = 0; i < NUM_OPS; ++i) {
            void* p = pool.allocate();
            pool.deallocate(p);
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();

        std::cout << "Pool alloc+free x " << NUM_OPS << ": "
                  << ns / 1e6 << "ms ("
                  << ns / (double)NUM_OPS << "ns/op)\n";
    }

    // ===== malloc/free =====
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (size_t i = 0; i < NUM_OPS; ++i) {
            void* p = std::malloc(SLOT_SIZE);
            std::free(p);
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();

        std::cout << "malloc+free x " << NUM_OPS << ": "
                  << ns / 1e6 << "ms ("
                  << ns / (double)NUM_OPS << "ns/op)\n";
    }

    return 0;
}
```

### 示例 3: 带 Canary 的调试池 + Pool<T> 模板

```cpp
// compile: g++ -std=c++20 -O2 debug_pool.cpp -o debug_pool
#include <iostream>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdlib>

// ============ 调试池分配器（带 Canary 检测） ============
static constexpr uint32_t CANARY_FRONT = 0xDEADBEEF;
static constexpr uint32_t CANARY_BACK  = 0xCAFEBABE;

class DebugPoolAllocator {
public:
    void create(size_t user_slot_size, size_t num_slots) {
        // 每个 Slot 前后各加 canary
        internal_slot_size_ = user_slot_size + 2 * sizeof(uint32_t);
        if (internal_slot_size_ < sizeof(void*))
            internal_slot_size_ = sizeof(void*);
        internal_slot_size_ = (internal_slot_size_ + alignof(std::max_align_t) - 1)
                              & ~(alignof(std::max_align_t) - 1);

        num_slots_ = num_slots;
        memory_ = static_cast<char*>(
            std::aligned_alloc(alignof(std::max_align_t),
                               internal_slot_size_ * num_slots));
        if (!memory_) throw std::bad_alloc();

        // 初始化自由链表
        free_head_ = reinterpret_cast<void**>(memory_);
        for (size_t i = 0; i < num_slots - 1; ++i) {
            void** curr = reinterpret_cast<void**>(memory_ + i * internal_slot_size_);
            void** next = reinterpret_cast<void**>(memory_ + (i + 1) * internal_slot_size_);
            *curr = next;
        }
        void** last = reinterpret_cast<void**>(memory_ + (num_slots - 1) * internal_slot_size_);
        *last = nullptr;

        num_used_ = 0;
    }

    void* allocate() {
        if (!free_head_) return nullptr;

        void** slot = free_head_;
        free_head_ = static_cast<void**>(*slot);

        // 写入前 canary
        *reinterpret_cast<uint32_t*>(slot) = CANARY_FRONT;
        // 写入后 canary
        uint32_t* back = reinterpret_cast<uint32_t*>(
            reinterpret_cast<char*>(slot) + internal_slot_size_ - sizeof(uint32_t));
        *back = CANARY_BACK;

        num_used_++;
        // 返回用户数据指针（跳过前 canary）
        return reinterpret_cast<char*>(slot) + sizeof(uint32_t);
    }

    void deallocate(void* ptr) {
        if (!ptr) return;

        // 获取包含 canary 的原始 Slot 指针
        char* raw = reinterpret_cast<char*>(ptr) - sizeof(uint32_t);

        // 验证 canary
        uint32_t front = *reinterpret_cast<uint32_t*>(raw);
        uint32_t back  = *reinterpret_cast<uint32_t*>(
            raw + internal_slot_size_ - sizeof(uint32_t));

        if (front != CANARY_FRONT) {
            std::cerr << "CORRUPTION: front canary overwritten at " << ptr << "\n";
            std::abort();
        }
        if (back != CANARY_BACK) {
            std::cerr << "CORRUPTION: back canary overwritten at " << ptr << "\n";
            std::abort();
        }

        // 插回自由链表
        void** slot = reinterpret_cast<void**>(raw);
        *slot = free_head_;
        free_head_ = slot;
        num_used_--;
    }

    void destroy() {
        if (num_used_ > 0) {
            std::cerr << "LEAK: " << num_used_ << " allocations not freed!\n";
        }
        if (memory_) std::free(memory_);
        memory_ = nullptr;
        free_head_ = nullptr;
    }

    ~DebugPoolAllocator() { destroy(); }

private:
    char*   memory_    = nullptr;
    void**  free_head_ = nullptr;
    size_t  internal_slot_size_ = 0;
    size_t  num_slots_ = 0;
    size_t  num_used_  = 0;
};

// ============ Pool<T> 模板包装 ============
template<typename T>
class Pool {
public:
    explicit Pool(size_t num_objects) {
        allocator_.create(sizeof(T), num_objects);
    }

    T* allocate() {
        void* p = allocator_.allocate();
        return p ? static_cast<T*>(p) : nullptr;
    }

    void deallocate(T* p) {
        allocator_.deallocate(static_cast<void*>(p));
    }

    // 用于 STL 容器的 std::allocator 接口（最小实现）
    using value_type = T;
    T* allocate(size_t n) {
        assert(n == 1 && "Pool allocator only supports n=1");
        return this->allocate();
    }
    void deallocate(T* p, size_t n) {
        assert(n == 1);
        this->deallocate(p);
    }

private:
    DebugPoolAllocator allocator_;
};

// ============ 引擎实体示例 ============
struct Particle {
    float x, y, z;
    float vx, vy, vz;
    float lifetime;
    uint32_t flags;
    // = 36 bytes — 加上 canary 约 44 bytes per slot

    // 与全局 Pool 绑定
    static Pool<Particle>& get_pool() {
        static Pool<Particle> pool(100'000);
        return pool;
    }

    void* operator new(size_t) { return get_pool().allocate(); }
    void operator delete(void* p) { get_pool().deallocate(static_cast<Particle*>(p)); }
};

int main() {
    std::cout << "=== Debug Pool Allocator Demo ===\n";

    // 直接使用调试池
    DebugPoolAllocator dpool;
    dpool.create(64, 10);

    void* p1 = dpool.allocate();
    void* p2 = dpool.allocate();
    std::cout << "Allocated 2 slots\n";

    // 模拟越界写入（只演示检测逻辑，实际会 abort）
    // char* raw = static_cast<char*>(p1) - sizeof(uint32_t);
    // *(reinterpret_cast<uint32_t*>(raw)) = 0;  // 破坏 canary

    dpool.deallocate(p1);
    dpool.deallocate(p2);
    dpool.destroy();

    // 使用 Pool<T> + operator new 重载
    std::cout << "\n=== Pool<T> + operator new ===\n";
    auto* particle = new Particle();
    std::cout << "Particle allocated at " << particle << "\n";
    particle->x = 1.0f;
    delete particle;
    std::cout << "Particle deleted\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: 实现一个基本的池分配器（必做）

从头实现一个 `SimplePoolAllocator`，要求：

1. `create(slot_size, num_slots)` — 分配内存并初始化侵入式自由链表
2. `allocate()` — 从链表头取一个 Slot
3. `deallocate(ptr)` — 将 Slot 插回链表头
4. `destroy()` — 释放底层内存
5. 正确处理对齐（`slot_size` 向上取整到 `alignof(std::max_align_t)`）
6. 正确处理 `slot_size < sizeof(void*)` 的情况

**测试**：
- 分配所有 Slot，验证每个指针都不同且都在池范围内
- 释放一半后重新分配，验证复用了刚释放的 Slot
- 分配超出容量时返回 `nullptr`（不要崩溃）

### 练习 2: 基准测试（必做）

对你实现的 `SimplePoolAllocator` 做基准测试：

1. 测试 `allocate()` + `deallocate()` 交替（模拟粒子的生灭循环）
2. 与 `malloc`/`free` 对比（同样的操作模式）
3. 与 `new`/`delete` 对比
4. 测试不同 Slot 大小（16B, 64B, 256B, 1024B）下的性能差异
5. 输出表格：`| Slot Size | Pool ns/op | malloc ns/op | Speedup |`

**提示**：用 `std::chrono::high_resolution_clock`，每种测试运行足够多次（>100,000）以消除噪声。

### 练习 3: 线程安全池分配器（可选挑战）

实现 `LockFreePoolAllocator`，要求：

1. 自由链表使用无锁 Treiber Stack（`std::atomic<void*>` + CAS）
2. `allocate()` 使用 `compare_exchange_weak` 循环
3. `deallocate()` 同样使用 CAS
4. 基准测试：单线程下与加锁版本对比（`std::mutex` + 普通链表）
5. 基准测试：多线程（4 线程）下与加锁版本对比

**提示**：参考 [Treiber, 1986](https://en.wikipedia.org/wiki/Treiber_stack)。注意 ABA 问题——在这个场景中 Slot 被分配后使用者可能再次释放，如果释放回同一个池，传统 ABA 问题在"不跨池"的场景下自然避免。但如果指针被重用就需要 tagged pointer。

---

## 4. 扩展阅读

- **Andrei Alexandrescu**: *Modern C++ Design*, Chapter 4 — 经典的小型对象分配器设计
- **Jason Gregory**: *Game Engine Architecture*, §5.4 — 池分配器在游戏引擎中的实践
- **Christian Gyrling**: [GDC 2015 — 顽皮狗引擎内存系统](https://www.gdcvault.com/)
- **Paul McKenney**: [Is Parallel Programming Hard?](https://mirrors.edge.kernel.org/pub/linux/kernel/people/paulmck/perfbook/perfbook.html) — 无锁数据结构章节
- **mimalloc**: 查看其 page-local free list 设计——池分配器思想的工业化实现

---

## 常见陷阱

### 陷阱 1: Slot 大小小于 `sizeof(void*)`

```cpp
PoolAllocator pool;
pool.create(2, 1000);  // slot_size = 2 < sizeof(void*) = 8
// 空闲时写 next 指针会越界！
```

**症状**：在 `allocate()` 或 `deallocate()` 时随机崩溃，或数据结构悄悄损坏。`next` 指针（8 bytes）写入 2-byte Slot 的边界外。

**修复**：`create()` 中将 `slot_size` 上取整到 `max(slot_size, sizeof(void*))`。

### 陷阱 2: 传递非池指针给 `deallocate()`

```cpp
Particle stack_particle;
pool.deallocate(&stack_particle);  // 栈对象被"释放"到池中
// 下次 allocate() 返回栈地址 → 写入导致栈损坏
```

**修复**：在调试模式下用 `owns()` 检查（地址范围 + 对齐验证）。Release 模式下可以省略以节省开销。

### 陷阱 3: Double-free

```cpp
void* p = pool.allocate();
pool.deallocate(p);
pool.deallocate(p);  // 同一个 Slot 被插入自由链表两次
// → 自由链表出现环 → 同一 Slot 被分配两次 → 数据竞争
```

**修复**：在调试模式下维护一个"活跃分配"集合（`std::unordered_set<void*>`），`deallocate` 时检查是否已在集合中。或者在 Slot 中写入一个 magic value，deallocate 时检查该 magic 是否已被覆盖（意味着已被释放过）。

### 陷阱 4: 在池析构后使用已分配的内存

```cpp
PoolAllocator* pool = new PoolAllocator();
pool->create(64, 100);
void* p = pool->allocate();
delete pool;            // 释放了底层内存
std::memset(p, 0, 64); // p 现在是悬垂指针！
```

池分配器析构时释放底层内存，所有之前分配的 Slot 变成悬垂指针。在引擎中，确保池的生命周期比所有使用者都长——通常在系统级管理（例如 `ParticleSystem` 拥有 `Pool<Particle>`，在 `ParticleSystem` 析构时所有粒子早已被销毁）。

### 陷阱 5: 忘记调用析构函数

```cpp
struct Particle {
    std::string name;
    ~Particle() { /* 释放资源 */ }
};

Pool<Particle> pool(100);
auto* p = pool.allocate();
new (p) Particle();   // placement new
// ...
pool.deallocate(p);   // 没有调用 p->~Particle()！
// → name 的 std::string 内部内存泄漏！
```

池分配器不负责调用析构函数——它只管理原始内存。如果类型有非平凡析构函数，你必须在 `deallocate` 之前手动调用析构。或者使用一个智能包装器（`PoolPtr<T>`）在 RAII 中处理。
