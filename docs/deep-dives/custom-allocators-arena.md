# Custom Allocators and Arena 深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 游戏引擎开发工程师 — [C++ 引擎编程：语言特性精要](../learning-plans/active/game-engine-dev/tutorials/00-cpp-for-game-engines.md)
> 关联深度探索: [RAII 深度剖析](raii-complete-analysis.md)、[C++ 智能指针](cpp-smart-pointers.md)、[C++ 特殊成员函数](cpp-special-member-functions.md)
> 分析日期: 2026-05-28

---

## 第 1 层: 直觉理解

**自定义分配器是"我决定内存在哪、怎么分、何时还"的机制。Arena 是"租一整个仓库，而不是逐个买保险柜"。**

### 默认分配器的思维模型

每次 `new T` 或 `malloc(N)`，你向操作系统"买"一块内存。每次 `delete ptr` 或 `free(ptr)`，你把它"还"回去。这是一对一的交易——分配与释放必须在时间上耦合。

其中隐藏了两个成本：

| 成本 | 来源 |
|------|------|
| **分配开销** | `malloc` 内部搜索空闲链表、分裂/合并块、更新元数据。每次调用都有几十到几百纳秒开销 |
| **释放开销** | `free` 同样需要查找元数据、合并相邻空闲块、可能触发系统调用归还给 OS |
| **碎片化** | 按任意顺序分配和释放不同大小的块 → 内存中散布不可用的"空洞" |

### Arena 的思维模型

一个 Arena 分配器做的事是：**一次性向操作系统要一大块内存（或多次要大块），然后从这块内存的"顶部"依次切出小块给各个请求**。释放时不是逐个归还，而是**整块丢弃**。

**类比：**

```
默认分配器 (malloc/free):
  你逐个租保险柜 → 每个要签合同、拿钥匙 → 到期逐个归还
  每次操作都有手续成本。如果你租 10000 个，手续费比箱子还贵。

Arena 分配器:
  你租一整个仓库 → 在里面放东西按自己的布局 → 到期整仓交还
  仓库内部没有"归还单个物品"的概念，因为整仓都要还，没必要逐件清点。
```

**关键洞察：** Arena 分配器利用了"内存的释放不需要知道里面装了什么"这一事实。如果你可以保证：当 Arena 销毁时，里面所有对象都不需要各自清理（析构），你就可以获取巨大的性能收益。

### RAII 与 Arena 的关系

这是本分析的核心命题：

```text
传统 RAII：     每个对象 = 一个 RAII 守卫 → 析构时释放自己的资源
Arena + RAII：  Arena 本身 = 一个 RAII 守卫 → 析构时整批释放所有内存
               第 2 层：placement new → 对象构造在 Arena 内部
               第 3 层（可选）：SpecificBumpPtrAllocator → 对非平凡类型调用析构
```

RAII 的"资源"从"单个对象的生存期"提升到了"整个分配池的生存期"。对象不需要各自 RAII 包裹——Arena 一次性回收一切。

---

## 第 2 层: 使用场景

### 典型场景

**1. 游戏引擎 — 帧分配器（Frame Allocator）**

每一帧渲染期间产生的临时数据——变换矩阵、剔除结果、绘制命令列表——只在这一帧内有效。帧结束时全部丢弃。

```cpp
class FrameAllocator {
    char*  buffer;     // 预分配 64MB
    size_t offset;
    // ...
public:
    void* allocate(size_t bytes) {
        void* ptr = buffer + offset;
        offset += bytes;
        return ptr;
    }
    void reset() { offset = 0; }  // 帧尾调用，零成本"释放"
};
```

帧分配器不需要 `free()` 方法。每帧 `reset()` 把指针拨回起点——O(1) 时间释放所有该帧分配的内存。

**2. 编译器 — AST 节点分配**

LLVM/Clang 在编译一个翻译单元时，创建成千上万 AST 节点。这些节点在编译期间被修改、引用、分析，但在编译结束后全部丢弃。LLVM 使用 `BumpPtrAllocator`（详见第 6 层），编译结束 → 析构 → 所有 AST 节点一次性释放。

**3. JSON 解析 — 临时 DOM 树**

RapidJSON 解析一个 JSON 文档时，创建的所有节点（Object、Array、String、Number）都从 `MemoryPoolAllocator` 分配。解析完成后，用户消费 DOM，然后整个分配器清空。

**4. 物理引擎 — 碰撞检测临时数据**

每帧的窄碰撞检测产生大量临时几何体（GJK 单形体、EPA 多面体）。这些不需要析构（都是纯数学结构），适合 Arena。

**5. 网络层 — 消息封包**

序列化一个网络消息时，所有中间缓冲区、包头、字段偏移表都是临时的。打包完成、发送出去后全部丢弃。

### 不适用场景

| 场景 | 为什么 Arena 不合适 |
|------|---------------------|
| 可变长生存期的对象 | Arena 只支持"一次性释放所有"。如果对象 A 活 5 帧、B 活 100 帧，需要分层 Arena 或退回通用分配器 |
| 频繁删除特定对象 | Arena 没有 `free()`，删除个别对象是浪费（内存不回收）。用对象池替代 |
| 需要析构的资源管理 | Arena 默认不调用析构。持有文件句柄、锁、GPU 资源的对象需要显式清理或 `SpecificBumpPtrAllocator` |
| 单个巨大对象（> Arena 大小） | 回退到 `malloc`，或触发 Arena 的 oversized 分配路径 |
| 多线程共享 | Arena 通常不是线程安全的。每个线程应有自己的 Arena |

### 决策树

```text
你需要分配大量对象吗？
├─ 否 → 直接用 new/make_unique
└─ 是 → 这些对象的生存期是否一致？
    ├─ 否 → 对象生存期模式？
    │   ├─ 固定大小 + 频繁分配/释放 → 对象池 (Pool Allocator)
    │   ├─ 按栈顺序分配/释放（LIFO）→ 栈分配器 (Stack Allocator)
    │   └─ 随机生存期 → malloc/free 或 tcmalloc/jemalloc
    └─ 是 → 对象是否需要析构？
        ├─ 是（持有 OS 资源）→ SpecificBumpPtrAllocator 或显式 Arena + RAII
        └─ 否（纯数据）→ 标准 Arena / Bump Allocator  ← 最大收益
```

---

## 第 3 层: API 层

### 3.1 C++ 标准分配器接口

STL 容器通过分配器抽象来解耦"数据结构"和"内存来源"：

```cpp
// 标准分配器 — 最简实现
template <typename T>
struct MyAllocator {
    using value_type = T;

    MyAllocator() = default;

    // 从其他类型的分配器构造（rebind 的关键）
    template <typename U>
    MyAllocator(const MyAllocator<U>&) {}

    // 分配 n 个未初始化的 T
    T* allocate(std::size_t n) {
        return static_cast<T*>(::operator new(n * sizeof(T)));
    }

    // 释放 n 个 T（不调用析构！）
    void deallocate(T* p, std::size_t n) {
        ::operator delete(p);
    }
};

// 使用
std::vector<int, MyAllocator<int>> vec;
```

`allocator_traits` 填充默认实现，你的分配器最少只需 `value_type`、`allocate`、`deallocate` 和跨类型构造。

### 3.2 C++17 `std::pmr` — 多态分配器

C++17 引入了类型擦除的分配器抽象，通过基类指针在运行时切换分配策略：

| 类型 | 角色 |
|------|------|
| `std::pmr::memory_resource` | 抽象基类，定义 `do_allocate()` / `do_deallocate()` / `do_is_equal()` |
| `std::pmr::polymorphic_allocator<T>` | 类型安全的包装器，持有 `memory_resource*` |
| `std::pmr::monotonic_buffer_resource` | **标准库的 Bump Allocator** |
| `std::pmr::unsynchronized_pool_resource` | 线程局部的多大小池分配器 |
| `std::pmr::synchronized_pool_resource` | 线程安全的池分配器 |
| `std::pmr::new_delete_resource()` | 全局函数，返回对 `new`/`delete` 的包装 |

使用 `pmr` 容器：

```cpp
#include <memory_resource>
#include <vector>
#include <list>

// 创建一个 64KB 栈上缓冲的 Arena
char buffer[65536];
std::pmr::monotonic_buffer_resource arena(buffer, sizeof(buffer));

// 使用 pmr 容器
std::pmr::vector<int> vec(&arena);
std::pmr::list<std::pmr::string> lst(&arena);

// 所有分配从 arena 走；arena 析构时整批释放
```

### 3.3 `std::pmr::monotonic_buffer_resource` 完整接口

| 成员 | 说明 |
|------|------|
| `monotonic_buffer_resource()` | 默认构造，使用 `new_delete_resource()` 作为上游 |
| `monotonic_buffer_resource(void* buf, size_t sz, memory_resource* upstream)` | 使用用户提供的初始缓冲 |
| `monotonic_buffer_resource(size_t initial_sz, memory_resource* upstream)` | 自动分配初始缓冲 |
| `~monotonic_buffer_resource()` | 释放所有内部块（不释放用户提供的 buffer！） |
| `release()` | 释放所有内部块，重置当前缓冲指针 |
| `upstream_resource()` | 返回上游分配器 |
| `do_allocate(size, align)` | 分配（override） |
| `do_deallocate(p, size, align)` | **空操作** — 不会真正释放内存！关键行为 |

### 3.4 `std::allocator_traits` — 默认实现填充器

```cpp
template <class Alloc>
struct allocator_traits {
    // 类型别名（从 Alloc 提取，或使用默认）
    using allocator_type = Alloc;
    using value_type      = typename Alloc::value_type;
    using pointer         = /* Alloc::pointer 或 value_type* */;
    using const_pointer   = /* Alloc::const_pointer 或 const value_type* */;
    using size_type       = /* ... */;
    using difference_type = /* ... */;

    // 如果 Alloc 没定义这些，traits 提供默认实现
    template <class T>
    using rebind_alloc = /* Alloc::rebind<T>::other 或直接构造 */;

    static pointer allocate(Alloc& a, size_type n);
    static void deallocate(Alloc& a, pointer p, size_type n);
    template <class T, class... Args>
    static void construct(Alloc& a, T* p, Args&&... args);  // placement new
    template <class T>
    static void destroy(Alloc& a, T* p);                     // p->~T()
    static size_type max_size(const Alloc& a);
};
```

### 3.5 引擎级分配器接口

游戏引擎通常不依赖 `std::allocator`，而是定义自己的分配器接口：

```cpp
// 基类：引擎分配器接口
class IAllocator {
public:
    virtual ~IAllocator() = default;
    virtual void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) = 0;
    virtual void  deallocate(void* ptr, size_t size) = 0;
    virtual size_t allocated_size(void* ptr) = 0;  // 依赖元数据
};

// 具体分配器：Arena
class ArenaAllocator : public IAllocator {
    char*  begin;
    char*  end;
    char*  current;
public:
    void* allocate(size_t size, size_t alignment) override {
        // bump pointer, 对齐
    }
    void deallocate(void*, size_t) override {
        // 空操作 — Arena 不单独释放
    }
    void reset() { current = begin; }
};
```

---

## 第 4 层: 行为契约

### 4.1 标准分配器概念要求

C++ 标准 ([allocator.requirements]) 定义分配器必须满足：

| 要求 | 细节 |
|------|------|
| **`*p` 可解引用** | `allocate(n)` 返回的指针 `p`，`[p, p+n)` 是有效的未初始化内存 |
| **`deallocate(p, n)` 前置条件** | `p` 必须是同一分配器之前 `allocate(n)` 返回的；`n` 必须匹配 |
| **Rebind 传递性** | `Alloc::rebind<T>::other::rebind<U>::other` 等于 `Alloc::rebind<U>::other` |
| **跨类型复制** | `Alloc<T>` 可复制构造为 `Alloc<U>` |
| **相等语义** | `a1 == a2` → `a1.allocate(n)` 分配的内存可由 `a2.deallocate(p, n)` 释放 |
| **传播 trait** | `propagate_on_container_copy_assignment` / `propagate_on_container_move_assignment` / `propagate_on_container_swap` |
| **`is_always_equal`** | 如果为 `true`，分配器是无状态的（如 `std::allocator`），容器可以省略存储分配器实例 |

### 4.2 `monotonic_buffer_resource` 特殊契约

| 行为 | 约定 |
|------|------|
| **`deallocate` 是空操作** | 调用后内存**不会**返回给分配器，也不会被复用。仅仅是一个 no-op |
| **指针稳定性** | 调用 `release()` 后，所有之前分配的指针变为悬垂。在两次 `release()` 之间，指针保持有效 |
| **不调用析构** | 与非平凡析构类型的 `std::pmr::vector` 配合时，`vector::~vector()` 调用元素的析构，但 `monotonic_buffer_resource` 不参与其中 |
| **上游分配器** | 当当前块耗尽时，自动向上游分配器请求更大的块 |

### 4.3 Arena 对对象类型的隐形约束

这是 Arena 分配器最容易被误用的特性：

```cpp
char buffer[4096];
std::pmr::monotonic_buffer_resource arena(buffer, sizeof(buffer));
std::pmr::vector<std::string> vec(&arena);

vec.push_back("hello");  // string 从 arena 分配
// vec 析构 → 调用每个 string 的析构 → string::~string() 释放 char* 内部缓冲
// → 但 string 的内部缓冲也是从 arena 分配的！
// → string::~string() 释放时用的是 arena.deallocate() → 空操作
// → 没有泄漏！因为 arena 析构时整块丢弃
```

**关键见解：** 即使对象有非平凡析构，只要析构"释放"的资源也来自同一个 Arena，最终整块丢弃时不会有泄漏。但如果 string 的内部缓冲来自 `new[]`（默认行为），那就回到通用堆，Arena 管不到。

这就是 `std::pmr::string` 的价值——它的内部分配也走 `polymorphic_allocator`，确保所有分配都在同一个 Arena 内。

### 4.4 内存对齐契约

| 操作 | 对齐保证 |
|------|----------|
| `::operator new(n)` | `alignof(std::max_align_t)`（通常 16 字节） |
| Arena 默认分配 | 同上，或调用者指定的对齐 |
| SIMD 类型需要 | 32 字节（AVX-256）或 64 字节（AVX-512）——Arena 必须支持请求的对齐 |
| 过度对齐 | Arena 实现中 `alignAddr(ptr, alignment)` 可能浪费最多 `alignment - 1` 字节 |

---

## 第 5 层: 实现原理

### 5.1 Bump (Linear) Allocator — 最简 Arena

```text
初始状态:
  [                                                           ]
  ^begin                                                 ^end
  ^current

分配 16 字节:
  [  16B allocated  |                                        ]
  ^begin            ^current                                 ^end

分配 8 字节 (对齐到 8):
  [  16B allocated  |  8B  |                                 ]
  ^begin                    ^current                         ^end

reset():
  [                                                           ]
  ^begin                                                 ^end
  ^current
```

伪代码：

```python
class BumpAllocator:
    def __init__(self, size):
        self.memory = malloc(size)
        self.begin  = self.memory
        self.end    = self.memory + size
        self.current = self.begin

    def allocate(self, size, alignment=8):
        # 对齐当前指针
        aligned = align_up(self.current, alignment)
        next_ptr = aligned + size
        if next_ptr > self.end:
            return None   # 或从上游分配新块
        self.current = next_ptr
        return aligned

    def deallocate(self, ptr, size):
        pass  # 关键：不做任何事

    def reset(self):
        self.current = self.begin  # O(1) 释放所有内存

    def destroy(self):
        free(self.memory)
```

**时间复杂度：** `allocate` = O(1)（仅指针加法 + 对齐），`deallocate` = O(1)（空操作），`reset` = O(1)。

### 5.2 Slab-Based Bump Allocator（LLVM 风格）

当单块内存不够时，分配器维护一组 slab：

```text
Slab 0 (4KB):     [████████████████████████|..........]
                                               ^current  ^end
Slab 1 (8KB):     [██████████████████████████████████████|...]
                                                               ^current ^end
Slab 2 (16KB):    [..........................]  ← 尚未使用
```

分配时：
1. 尝试在当前 slab 分配
2. 不够 → 分配新 slab，大小按 GrowthDelay 策略增长
3. 如果请求的 size > SizeThreshold → 分配专用 "custom-sized slab"

`Reset()` 策略：释放除第一个 slab 外的所有 slab，将第一个 slab 的 `current` 拨回 `begin`。

### 5.3 Stack Allocator（带标记释放）

比 Bump Allocator 更进一步——支持 LIFO 释放：

```cpp
class StackAllocator {
    char*  begin;
    char*  end;
    char*  current;

public:
    struct Marker {
        char* ptr;
    };

    Marker get_marker() { return Marker{current}; }

    void* allocate(size_t size, size_t alignment) {
        // 同 Bump Allocator
    }

    void free_to_marker(Marker m) {
        current = m.ptr;  // 一次性释放从标记以来的所有分配
    }
};

// 使用
auto m = stack.get_marker();
auto* temp1 = stack.allocate(128);
auto* temp2 = stack.allocate(256);
// ... 使用 temp1, temp2 ...
stack.free_to_marker(m);  // 两个临时分配都被回收
```

比 bump allocator 更灵活——你可以在帧中间"弹出"一组临时分配，而不是等到帧尾。

### 5.4 Pool Allocator（固定大小对象池）

```text
Pool (每块 64 字节):
[0] → free → [1] → free → [2] → free → [3] → free → [4] → ...
 ↑
 head (空闲链表)

分配: 取 head，head = head->next，返回该块
释放: 该块->next = head，head = 该块
```

实现：

```cpp
template <typename T>
class PoolAllocator {
    union Node {
        T     data;
        Node* next;  // 空闲时复用为链表指针
    };

    Node* pool;       // 预分配的大数组
    Node* free_list;
    size_t capacity;

public:
    PoolAllocator(size_t n) {
        pool = static_cast<Node*>(malloc(n * sizeof(Node)));
        // 构建空闲链表
        for (size_t i = 0; i < n - 1; i++)
            pool[i].next = &pool[i + 1];
        pool[n - 1].next = nullptr;
        free_list = pool;
    }

    T* allocate() {
        if (!free_list) return nullptr;
        Node* node = free_list;
        free_list = node->next;
        return &node->data;
    }

    void deallocate(T* ptr) {
        Node* node = reinterpret_cast<Node*>(ptr);
        node->next = free_list;
        free_list = node;
    }
};
```

**时间复杂度：** 分配和释放都是 O(1)（链表头操作）。极度缓存友好——所有对象在连续内存中。

### 5.5 Free List Allocator（可变大小）

维护多个大小类（size class）的空闲链表。分配时找合适的大小类，没有则向上级分配器请求新内存。释放时插入对应大小类的链表。

这就是 `malloc` 的简化版。Arena 通常不走到这个复杂度——那是通用分配器（jemalloc, mimalloc, tcmalloc）的领域。

---

## 第 6 层: 源码分析

### 6.1 LLVM `BumpPtrAllocator` — 编译器分配器标杆

**项目:** LLVM
**文件:** `llvm/include/llvm/Support/Allocator.h`
**许可:** Apache 2.0 with LLVM Exceptions

这是生产级 Bump Allocator 最经典的实现。Clang 用它分配 AST 节点，每个翻译单元（.cpp 文件）有自己的 `BumpPtrAllocator`。

```cpp
template <typename AllocatorT = MallocAllocator, size_t SlabSize = 4096,
          size_t SizeThreshold = SlabSize, size_t GrowthDelay = 128>
class BumpPtrAllocatorImpl {
    char *CurPtr = nullptr;     // 当前 slab 中的空闲位置
    char *End = nullptr;        // 当前 slab 的末尾
    SmallVector<void *, 4> Slabs;              // 普通 slab 列表
    SmallVector<std::pair<void *, size_t>, 0> CustomSizedSlabs;  // 超大分配
    size_t BytesAllocated = 0;

    // slab 大小增长策略
    static size_t computeSlabSize(unsigned SlabIdx) {
        return SlabSize * ((size_t)1 << std::min<size_t>(30, SlabIdx / GrowthDelay));
    }
};
```

**增长策略：** `SlabSize=4096`，`GrowthDelay=128`。前 128 个 slab 每个 4KB，之后每 128 个 slab 大小翻倍（最多到 2^30 × 4KB = 4TB 上限）。这意味着在 128 个 slab 之后，分配频率大幅下降。

**核心分配路径:**

```cpp
void *Allocate(size_t Size, Align Alignment) {
    BytesAllocated += Size;

    size_t SizeToAllocate = Size;
    uintptr_t AlignedPtr = alignAddr(CurPtr, Alignment);
    uintptr_t AllocEndPtr = AlignedPtr + SizeToAllocate;

    // 快速路径: 当前 slab 有足够空间
    if (LLVM_LIKELY(AllocEndPtr <= uintptr_t(End) && CurPtr != nullptr)) {
        CurPtr = reinterpret_cast<char *>(AllocEndPtr);
        return reinterpret_cast<char *>(AlignedPtr);
    }

    return AllocateSlow(Size, SizeToAllocate, Alignment);
}
```

**慢路径 `AllocateSlow`:**

```cpp
void *AllocateSlow(size_t Size, size_t SizeToAllocate, Align Alignment) {
    // 超大分配 → 独立的 custom-sized slab
    size_t PaddedSize = SizeToAllocate + Alignment.value() - 1;
    if (PaddedSize > SizeThreshold) {
        void *NewSlab = this->getAllocator().Allocate(PaddedSize, alignof(std::max_align_t));
        CustomSizedSlabs.push_back(std::make_pair(NewSlab, PaddedSize));
        // 对齐 + 返回
    }

    // 普通分配 → 新的 slab
    StartNewSlab();
    // 对齐 + 返回
}
```

**`Deallocate` 的实现:**

```cpp
void Deallocate(const void *Ptr, size_t Size, size_t /*Alignment*/) {
    __asan_poison_memory_region(Ptr, Size);  // ASan 支持，但不释放
}
```

**关键设计：** `Deallocate` 不是空操作，而是使用 ASan 的 poison 机制标记内存不可访问。这在 Debug 构建中能捕获 use-after-free，但不实际回收内存。

**`Reset()` — 帧尾释放:**

```cpp
void Reset() {
    DeallocateCustomSizedSlabs();
    CustomSizedSlabs.clear();
    if (Slabs.empty()) return;

    BytesAllocated = 0;
    CurPtr = (char *)Slabs.front();
    End = CurPtr + SlabSize;

    DeallocateSlabs(std::next(Slabs.begin()), Slabs.end());
    Slabs.erase(std::next(Slabs.begin()), Slabs.end());
}
```

保留第一个 slab，释放其余 slab，把 `CurPtr` 拨回第一个 slab 的开头。O(1) 个 slab 数的操作。

**`SpecificBumpPtrAllocator<T>` — 带析构的 Bump Allocator:**

```cpp
template <typename T>
class SpecificBumpPtrAllocator {
    BumpPtrAllocator Allocator;

    void DestroyAll() {
        auto DestroyElements = [](char *Begin, char *End) {
            for (char *Ptr = Begin; Ptr + sizeof(T) <= End; Ptr += sizeof(T))
                reinterpret_cast<T *>(Ptr)->~T();  // 遍历调用析构
        };
        // 对所有 slab 执行 DestroyElements
        Allocator.Reset();
    }

    ~SpecificBumpPtrAllocator() { DestroyAll(); }
};
```

当 Arena 中的对象需要析构（如持有非 Arena 资源），`SpecificBumpPtrAllocator` 可以在释放前遍历所有 slab，对每个 T 调用 `~T()`。

**设计亮点:**

1. **模板参数控制增长策略** — `SlabSize`、`SizeThreshold`、`GrowthDelay` 都是编译期常量，零运行时开销
2. **`LLVM_LIKELY` 快速路径** — 99% 的分配只走一条 if 语句
3. **Sanitizer 集成** — ASan poison 捕获 use-after-free；MSan 标记初始化
4. **`operator new` 重载** — `new (bumpAllocator) T(args...)` 直接走 BumpPtrAllocator，不需要额外的 placement new 包装

### 6.2 Godot `PagedAllocator` — 引擎对象池

**项目:** Godot Engine
**文件:** `core/templates/paged_allocator.h`
**许可:** MIT

Godot 用 `PagedAllocator` 管理频繁创建/销毁的引擎小对象（如 `Variant` 内部数据）。

```cpp
template <typename T, bool thread_safe = false, uint32_t DEFAULT_PAGE_SIZE = 4096>
class PagedAllocator {
    T **page_pool = nullptr;          // 页指针数组
    T ***available_pool = nullptr;    // [页索引][槽索引] → T* 的空闲槽
    uint32_t pages_allocated = 0;
    uint32_t allocs_available = 0;    // 可用槽总数
    uint32_t page_shift = 0;          // 快速除法的位运算
    uint32_t page_mask = 0;           // 快速取模的位运算
};
```

**分配路径:**

```cpp
T *alloc(Args &&...p_args) {
    if (unlikely(allocs_available == 0)) {
        // 分配新页
        page_pool[pages_used] = (T *)memalloc(sizeof(T) * page_size);
        // 填充空闲槽索引
        for (uint32_t i = 0; i < page_size; i++) {
            available_pool[0][i] = &page_pool[pages_used][i];
        }
        allocs_available += page_size;
    }
    allocs_available--;
    // 从空闲池弹出最后一个槽
    T *alloc = available_pool[allocs_available >> page_shift]
                             [allocs_available & page_mask];
    memnew_placement(alloc, T(p_args...));  // placement new
    return alloc;
}
```

**释放路径:**

```cpp
void free(T *p_mem) {
    p_mem->~T();    // 调用析构——注意这里！
    // 把槽推回空闲池
    available_pool[allocs_available >> page_shift]
                  [allocs_available & page_mask] = p_mem;
    allocs_available++;
}
```

**与 Arena 的区别:**

| 特性 | Arena / Bump Allocator | PagedAllocator |
|------|------------------------|----------------|
| 释放单个对象 | 不支持 | 支持（O(1) 推回空闲池） |
| 对象析构 | 不支持（或靠外部） | 支持（`free()` 中显式调用 `~T()`） |
| 碎片 | 零（连续 bump） | 无外部碎片，但可能有内部空闲槽 |
| 适用场景 | 临时数据，帧分配 | 固定大小对象，频繁分配/释放 |

**设计亮点:**

1. **位运算索引** — `allocs_available >> page_shift` 和 `allocs_available & page_mask` 替代除法和取模
2. **`available_pool` 作为栈** — 不是链表，而是栈式空闲管理。`allocs_available` 递减时弹出，递增时推入
3. **可选线程安全** — `thread_safe` 模板参数编译期选择是否加 `SpinLock`
4. **`_reset()` 的 `is_trivially_destructible` 检查** — 如果类型是平凡析构的，`reset(false)` 时不需要所有对象都已被释放

### 6.3 RapidJSON `MemoryPoolAllocator` — 最小化 Arena

**项目:** RapidJSON
**文件:** `include/rapidjson/allocators.h`
**许可:** MIT

RapidJSON 的设计哲学是"不依赖 STL"。它的 `MemoryPoolAllocator` 极简但完整：

```cpp
template <typename BaseAllocator = CrtAllocator>
class MemoryPoolAllocator {
    static const bool kNeedFree = false;  // 告诉用户：不用调用 Free

    struct ChunkHeader {
        size_t capacity;
        size_t size;
        ChunkHeader *next;
    };
    ChunkHeader *chunkHead_;        // 单向链表，头节点是当前活跃 chunk
    size_t chunk_capacity_;
    void *userBuffer_;              // 用户提供的初始缓冲

    void* Malloc(size_t size) {
        size = RAPIDJSON_ALIGN(size);
        // 当前 chunk 不够 → 分配新 chunk
        if (chunkHead_ == 0 || chunkHead_->size + size > chunkHead_->capacity)
            if (!AddChunk(chunk_capacity_ > size ? chunk_capacity_ : size))
                return NULL;

        // Bump pointer
        void *buffer = reinterpret_cast<char *>(chunkHead_)
                     + RAPIDJSON_ALIGN(sizeof(ChunkHeader))
                     + chunkHead_->size;
        chunkHead_->size += size;
        return buffer;
    }

    static void Free(void *ptr) { (void)ptr; }  // 空操作！
};
```

**设计亮点:**

1. **零外部依赖** — 不依赖 STL，可嵌入任何项目
2. **`kNeedFree = false`** — 编译期常量告知用户"Arena 不需要逐个 free"
3. **Chunk 链表** — 支持无限增长（受限于上游分配器）
4. **用户提供初始缓冲** — 如果在栈上有固定大小缓冲，可以不触发任何 `malloc` 调用

### 6.4 `std::pmr::monotonic_buffer_resource` 的设计要点

虽然标准库的实现各有不同（libstdc++ / libc++），但核心行为是标准化的：

```cpp
// libstdc++ 简化实现 (GCC 12+, bits/monotonic_buffer_resource.cc)
class monotonic_buffer_resource : public memory_resource {
    void* _M_current_buf;
    size_t _M_current_size;
    memory_resource* _M_upstream;
    // 已分配块的链表（用于析构时释放）
    struct _Block { _Block* _M_next; };
    _Block* _M_blocks;

    void* do_allocate(size_t __bytes, size_t __alignment) override {
        // 如果当前缓冲不够，分配新缓冲，把旧的加入 _M_blocks 链表
        // bump pointer 分配
    }

    void do_deallocate(void*, size_t, size_t) override {
        // 空操作
    }

    void release() {
        // 遍历 _M_blocks，逐个归还给 _M_upstream
        // 重置 _M_current_buf 到初始状态
    }
};
```

---

## 第 7 层: 对比与边界

### 7.1 Arena vs `malloc`/`free` — 性能对比

| 维度 | `malloc`/`free` | Arena (Bump Allocator) |
|------|----------------|------------------------|
| **分配** | ~20-100ns（取决于实现和碎片状态） | ~2-5ns（指针加法 + 对齐） |
| **释放** | ~10-50ns per `free()` | 0ns per object（`deallocate` 空操作） |
| **总体释放** | O(n) — n 个对象需要 n 次 `free()` | O(1) — 一次 `reset()` |
| **碎片** | 外部碎片，随时间积累 | 零碎片（分配期间） |
| **内存开销** | 每分配块 ~8-16 字节元数据 | ~0 字节 per allocation（只在 slab 层级有少量元数据） |
| **缓存局部性** | 差 — 分配散布在堆上 | 好 — 分配紧密排列在同一 slab 中 |
| **并发** | 通常有全局锁或线程缓存 | 单线程设计；多线程需要每个线程自己的 Arena |

**实测数据（大致量级）:** 使用 Arena 分配 100 万个小对象（32 字节）并整批释放，比 `new`/`delete` 快 **30-100 倍**。提速来自两方面：分配本身快 5-10 倍，释放快 N 倍（1 次 `reset()` vs 100 万次 `delete`）。

### 7.2 `std::allocator` vs `std::pmr::polymorphic_allocator`

| 维度 | `std::allocator<T>` | `std::pmr::polymorphic_allocator<T>` |
|------|---------------------|--------------------------------------|
| **分派机制** | 编译期（模板参数） | 运行时（虚函数） |
| **类型** | `vector<int, MyAlloc<int>>` 是独立类型 | `pmr::vector<int>` 是单类型，分配器是值 |
| **运行时切换** | 不可能 | 可能 — 更换 `memory_resource*` |
| **ABI 影响** | 使用不同分配器的容器类型不同 | 所有 `pmr` 容器有相同类型 |
| **虚函数开销** | 无 | 每次分配有虚函数调用开销（~2-5ns） |
| **适用场景** | 系统级编程，零开销需求 | 库接口，运行时配置 |

**选择指南：**
- 引擎内部 → 模板分配器（零开销）
- 插件 API / 库接口 → `pmr`（类型统一）
- 帧分配器 → 直接自己实现（不需要适应 STL 分配器概念）

### 7.3 Arena + RAII 模式 vs 传统析构

```cpp
// 模式 A: 传统 — 逐个析构
{
    std::vector<ExpensiveObject> vec;
    for (int i = 0; i < 100000; i++)
        vec.emplace_back(...);
    // 作用域结束 → 100000 次 ~ExpensiveObject() → 100000 次 deallocate
}

// 模式 B: Arena — 整批释放
{
    Arena arena(64 * 1024 * 1024);
    std::vector<TrivialData*> ptrs;
    for (int i = 0; i < 100000; i++)
        ptrs.push_back(arena.allocate<TrivialData>(...));
    // 作用域结束 → arena 析构 → 1 次释放 → 0 次 ~TrivialData()
}
```

模式 B 的前提是 `TrivialData` 不需要析构（平凡析构类型），或者其析构"释放"的资源也来自同一个 Arena。

### 7.4 `placement new` — Arena 分配与对象构造的桥梁

```cpp
// Arena 返回原始内存
void* memory = arena.allocate(sizeof(MyType), alignof(MyType));
// placement new 在指定地址构造对象
MyType* obj = new (memory) MyType(args...);

// 与常规 new 的对比:
MyType* obj2 = new MyType(args...);
// 等价于:
// void* mem = ::operator new(sizeof(MyType));  // 从全局堆分配
// MyType* obj2 = new (mem) MyType(args...);    // placement new 构造
```

Arena 分配器通常不直接返回 `T*`，而是返回 `void*`。调用者负责 placement new。这是有意为之的——分离"内存来源"和"对象构造"。

### 7.5 平凡析构 (`std::is_trivially_destructible`) 的 Arena 意义

```cpp
// 平凡析构类型 — Arena 完美适用
struct Vec3 { float x, y, z; };                    // ✅ 平凡
struct Matrix4x4 { float m[16]; };                  // ✅ 平凡
struct DrawCommand { uint32_t meshID; Mat4 transform; };  // ✅ 平凡

// 非平凡析构类型 — 需要额外处理
struct FileResource { FILE* f; ~FileResource() { fclose(f); } };  // ❌ 持有 OS 句柄
struct GpuBuffer { GLuint id; ~GpuBuffer() { glDeleteBuffers(1, &id); } };  // ❌

// 混合策略：SpecificBumpPtrAllocator<GpuBuffer> — Arena 释放前遍历调用析构
```

### 7.6 设计取舍

| 取舍 | Arena 的选择 | 代价 |
|------|-------------|------|
| **灵活性 vs 性能** | 放弃单独释放，换取极致性能 | 不能释放单个对象（除非用 Arena 之上的对象池） |
| **运行时 vs 编译期** | `std::pmr` 选择运行时多态 | 虚函数调用开销 |
| **内存效率 vs 速度** | Arena 用 slab 增长，可能有少量浪费 | 最后一个 slab 未用完的部分 |
| **安全 vs 速度** | 默认不调用析构 | 需要开发者理解哪些类型可以放在 Arena 中 |
| **所有权 vs 速度** | 单所有者（Arena），不支持共享 | 无法用 `shared_ptr` 从 Arena 分配 |

---

## 常见面试题

### Q1: "Arena 分配器为什么不能单独释放？如果要支持，应该怎么做？"

Arena 的"bump pointer"设计没有记录每个分配的大小和状态。如果 `deallocate` 某个中间块，会产生无法利用的"空洞"。

要支持单独释放，有三种方案：
1. **Pool Allocator** — 所有分配大小固定，释放时推回空闲链表
2. **Stack Allocator + Marker** — 支持 LIFO 释放到标记点
3. **在 Arena 之上加 Free List** — 释放时加入空闲链表，分配时先查空闲链表再 bump。但这样碎片又会回来。

### Q2: "`std::pmr::polymorphic_allocator` 和模板分配器各有什么优缺点？"

模板分配器：编译期分派，零开销；但改变分配器就改变了容器类型——`vector<int, ArenaAlloc>` 和 `vector<int, MallocAlloc>` 是不同的类型。

`pmr::polymorphic_allocator`：所有 `pmr::vector<int>` 是同一个类型，可以在运行时切换分配策略。代价是每次分配有虚函数调用。适合库边界和需要运行时配置的场景。

### Q3: "如何在 Arena 中管理持有文件句柄的对象？"

三种方案：
1. **显式清理** — 在 Arena 释放前，遍历所有对象手动调用 `close()`
2. **`SpecificBumpPtrAllocator<T>` 模式** — Arena 知道对象类型，遍历调用 `~T()`
3. **双层分配** — Arena 只管理对象的内存，对象的内部资源（file handle）由 RAII wrapper 管理，不在 Arena 中

### Q4: "为什么游戏引擎的帧分配器通常不用 `std::pmr`？"

1. **历史** — 游戏引擎的帧分配器早在 C++17 之前就存在了
2. **零开销** — `std::pmr` 的虚函数分派在每帧 10 万+ 分配下是不可忽略的开销
3. **不需要类型擦除** — 帧分配器只有一个，运行时不会切换策略
4. **与引擎内存系统的集成** — 引擎有自己的内存追踪、debug 标签系统，`std::pmr` 不提供这些

### Q5: "`monotonic_buffer_resource::deallocate()` 是空操作——这会导致内存泄漏吗？"

不会。因为 `monotonic_buffer_resource` 的析构函数（或 `release()`）会整批释放所有内部块。单个 `deallocate` 不释放，是**故意延迟**——所有个体释放延迟到整批释放时一次性完成。这不是泄漏，而是批量回收策略。

---

## 延伸主题

学完自定义分配器与 Arena 后，建议按顺序探索：

1. **`std::pmr` 完整生态** — `unsynchronized_pool_resource`、`synchronized_pool_resource`、自定义 `memory_resource`
2. **`jemalloc` / `mimalloc` / `tcmalloc` 对比** — 通用分配器的线程缓存、大小类、arena 管理
3. **对象池模式** — 与 Arena 互补——Arena 管理"一次性的分配"，对象池管理"复用性分配"
4. **SoA (Structure of Arrays) vs AoS** — 在 Arena 中的内存布局优化，利用缓存行
5. **Rust 的 `bumpalo` / Zig 的显式分配器** — 其他语言如何解决相同问题
6. **C++26 `std::inplace_vector` / `std::hive`** — 标准库新增的对分配器更友好的容器
