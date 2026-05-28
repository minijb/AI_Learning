# `std::pmr` 多态内存资源深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 游戏引擎开发工程师 — RAII 资源管理延伸
> 分析日期: 2026-05-28

---

## 第 1 层: 直觉理解

**`std::pmr` 把"怎么分配内存"从编译期决策变成了运行期决策——同时保持 RAII 的全部保证。**

传统 C++ 分配器（`std::allocator<T>`）是模板参数：你在写下 `std::vector<int>` 的时候就决定了它用 `::operator new` 分配内存。你把 10 个 `vector` 传给同一个函数，它们都从同一个全局堆拿内存。

`std::pmr` 的做法不同：容器不直接知道"内存从哪来"。它持有一个指向抽象 `memory_resource` 的指针（通过 `polymorphic_allocator`）。你可以给一个 `vector` 一个"只在当前帧存活"的 monotonic buffer，给另一个 `vector` 一个线程安全的池化分配器——同一个类型，不同的分配策略。

**类比：厨房与食材供应商**

| 概念 | 厨房类比 | C++ |
|------|---------|-----|
| 菜 (数据) | 你做菜需要的食材 | `int`, `string`, `GameObject` |
| 冰箱 (容器) | 存放食材的地方 | `std::pmr::vector<int>` |
| 供应商 (分配器) | 谁负责采购、什么时候退货 | `polymorphic_allocator<int>` |
| 供应链策略 (memory_resource) | 从哪个农场进货、怎么运输 | `monotonic_buffer_resource` |
| 传统方式 | 每道菜写死供应商（模板参数） | `std::allocator<T>` |
| pmr 方式 | 冰箱上贴个供应商名片（运行时指针） | `polymorphic_allocator` + `memory_resource*` |

传统方式就像每家厨房门口挂了个固定的"XX农场直供"招牌——换供应商要重新装修（换类型，重新编译）。pmr 方式是在冰箱上贴个便利贴——随时换，同一台冰箱可以用不同的供应商。

**RAII 的角色没有变**：冰箱（容器）销毁时，会自动通知供应商（通过 `polymorphic_allocator::deallocate()` → `memory_resource::do_deallocate()`）"食材用完了，退回去"。供应商（`monotonic_buffer_resource`）本身销毁时，也会把自己从上游批发商拿的所有食材一次性退还（`release()`）。

---

## 第 2 层: 使用场景

### 典型场景

1. **帧级 Arena 分配（游戏引擎）** — 每帧创建一个 `monotonic_buffer_resource`，帧内所有临时分配（路径查找、粒子计算、渲染命令缓冲）都在这个 arena 里。帧结束时析构 → 一次释放所有内存，无需逐个 `free`。比 `malloc`/`free` 快 10-100 倍。

2. **固定大小对象池** — 游戏实体、网络包、事件对象。用 `unsynchronized_pool_resource` 管理固定大小块的分配。避免了全局堆的碎片化和锁竞争。

3. **多态容器在接口边界传递** — 一个函数接受 `std::pmr::vector<int>&`，调用者可以传入用任何 `memory_resource` 构造的 vector。不需要模板化整个函数。

4. **嵌入式/受限环境** — 用一个预分配的栈上 buffer 初始化 `monotonic_buffer_resource`，上游设为 `null_memory_resource()`。所有分配在固定 buffer 内完成，不碰堆。

5. **测试** — 用 `null_memory_resource` 确保某条代码路径不分配内存。用自定义 resource 追踪分配次数和大小。

### 不适用场景

1. **性能极端敏感的分配热点，且分配大小和生命周期完全可预测** — 如果每个字节的内存布局都需要手动控制（例如 ECS 架构中的 archetype 存储），直接用 `malloc` + placement new 更精确。pmr 的虚函数调用有间接开销。

2. **需要跨 DLL/SO 边界的分配** — `memory_resource::do_is_equal()` 的比较语义在跨模块时需要谨慎处理。如果两个模块各自有 `monotonic_buffer_resource` 的实例，即使行为完全相同，`do_is_equal` 默认返回 `false`。

3. **已经有成熟的自定义分配器体系** — 如果代码库大量使用基于 `std::allocator` 模板参数的分配器，迁移到 pmr 需要改动容器类型（`std::vector<T>` → `std::pmr::vector<T>`），成本可能高于收益。

### 决策树

```
你需要控制内存分配策略吗？
├─ 策略需要在运行时切换？ → std::pmr
│   ├─ 临时分配，批量释放 → monotonic_buffer_resource
│   ├─ 大量同大小对象 → unsynchronized_pool_resource
│   ├─ 多线程 + 池化 → synchronized_pool_resource
│   └─ 完全自定义 → 继承 memory_resource
├─ 策略在编译期确定 → 传统模板分配器足够
└─ 不需要控制 → std::allocator（默认）
```

---

## 第 3 层: API 层

### 核心类型总览

| 类型 | 角色 | 头文件 |
|------|------|--------|
| `std::pmr::memory_resource` | 抽象基类，定义分配/释放接口 | `<memory_resource>` |
| `std::pmr::polymorphic_allocator<T>` | 分配器适配器，把 `memory_resource*` 包装成标准分配器 | `<memory_resource>` |
| `std::pmr::vector<T>` | `std::vector` 的 pmr 别名 | `<vector>` |
| `std::pmr::string` | `std::string` 的 pmr 别名 | `<string>` |
| `std::pmr::monotonic_buffer_resource` | 只增不减的 arena 分配器 | `<memory_resource>` |
| `std::pmr::unsynchronized_pool_resource` | 非线程安全的池化分配器 | `<memory_resource>` |
| `std::pmr::synchronized_pool_resource` | 线程安全的池化分配器 | `<memory_resource>` |

### `memory_resource` — 抽象基类

```cpp
class memory_resource {
public:
    void* allocate(size_t bytes, size_t alignment = alignof(max_align_t));
    void  deallocate(void* p, size_t bytes, size_t alignment = alignof(max_align_t));
    bool  is_equal(const memory_resource& other) const noexcept;

private:
    virtual void* do_allocate(size_t bytes, size_t alignment) = 0;
    virtual void  do_deallocate(void* p, size_t bytes, size_t alignment) = 0;
    virtual bool  do_is_equal(const memory_resource& other) const noexcept = 0;
};
```

**NVI (Non-Virtual Interface) 模式**：公开的 `allocate()` 是非虚函数，内部调用 `do_allocate()` 后包了一层 `::operator new` 来记录返回指针（用于调试/leak sanitizer）。用户只继承并实现 `do_*` 私有虚函数。

### `polymorphic_allocator<T>` — 分配器适配器

| 成员 | 签名 | 说明 |
|------|------|------|
| 默认构造 | `polymorphic_allocator()` | 使用 `get_default_resource()` |
| 指针构造 | `polymorphic_allocator(memory_resource* r)` | 绑定到指定 resource |
| 模板拷贝 | `polymorphic_allocator(const polymorphic_allocator<U>&)` | 跨类型转换，共享同一 resource |
| `allocate(n)` | `T* allocate(size_t n)` | 分配 n 个 T 的内存 |
| `deallocate(p, n)` | `void deallocate(T* p, size_t n)` | 释放 |
| `resource()` | `memory_resource* resource()` | 获取底层 resource 指针 |
| `construct(p, args...)` | `void construct(T* p, Args&&...)` | placement new（C++17）；C++20 起 deprecated |
| `destroy(p)` | `void destroy(T* p)` | 调用析构（C++17）；C++20 起 deprecated |
| `select_on_container_copy_construction()` | 返回默认构造的 allocator | **容器拷贝时不传播** — 新容器用 default resource |

**关键设计**：`propagate_on_container_copy_assignment` = `false_type`，`propagate_on_container_move_assignment` = `false_type`，`propagate_on_container_swap` = `false_type`，`is_always_equal` = `false_type`。

这意味着：
- 拷贝容器时，新容器使用 `get_default_resource()`，而不是源容器的 resource。
- 移动容器时，如果 allocator 不相等（`*a.resource() != *b.resource()`），移动变成逐元素拷贝。
- `swap` 两个不同 resource 的容器是**未定义行为**。

### 内置 memory_resource 实现

#### `new_delete_resource()`

```cpp
memory_resource* new_delete_resource() noexcept;
```

包装全局 `::operator new` / `::operator delete`。始终返回同一个单例指针。是默认 resource。

#### `null_memory_resource()`

```cpp
memory_resource* null_memory_resource() noexcept;
```

`do_allocate()` 永远抛 `std::bad_alloc`。`do_deallocate()` 是 no-op。用于测试和作为 `monotonic_buffer_resource` 的上游（强制只用初始 buffer）。

#### `monotonic_buffer_resource`

| 构造函数 | 说明 |
|----------|------|
| `monotonic_buffer_resource()` | 默认上游 = `get_default_resource()` |
| `monotonic_buffer_resource(size_t initial_size)` | 指定 `_M_next_bufsiz` 初始值 |
| `monotonic_buffer_resource(void* buffer, size_t size)` | 使用预分配 buffer |
| `monotonic_buffer_resource(void* buffer, size_t size, memory_resource* upstream)` | 预分配 buffer + 指定上游 |
| `monotonic_buffer_resource(memory_resource* upstream)` | 指定上游 |
| `monotonic_buffer_resource(size_t initial_size, memory_resource* upstream)` | 同时指定 |

| 成员 | 说明 |
|------|------|
| `release()` | 释放所有从上游分配的内存，恢复到构造时状态（如果构造时提供了初始 buffer，恢复之） |
| `upstream_resource()` | 返回上游 resource |
| 析构函数 | 调用 `release()` |

**核心行为**：`do_deallocate()` 是空操作！分配是指针递增（bump allocation），内存只增不减，直到 `release()` 或析构。

#### `unsynchronized_pool_resource`

| 构造函数 | 说明 |
|----------|------|
| `unsynchronized_pool_resource()` | 默认选项 + 默认上游 |
| `unsynchronized_pool_resource(const pool_options& opts)` | 自定义调优参数 |
| `unsynchronized_pool_resource(memory_resource* upstream)` | 指定上游 |
| `unsynchronized_pool_resource(const pool_options& opts, memory_resource* upstream)` | 同时指定 |

| 成员 | 说明 |
|------|------|
| `release()` | 释放所有池内存回上游 |
| `upstream_resource()` | 返回上游 resource |
| `options()` | 返回使用的 `pool_options` |

#### `synchronized_pool_resource`

接口同 `unsynchronized_pool_resource`，但线程安全。内部使用 `shared_mutex` + 线程局部存储的 per-thread pool。

#### `pool_options`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `max_blocks_per_chunk` | 0（由实现决定） | 每个 chunk 最大块数 |
| `largest_required_pool_block` | 0（由实现决定） | 超过此大小的分配直接走 upstream |

### 容器别名

```cpp
namespace std::pmr {
    template<typename T> using vector = std::vector<T, polymorphic_allocator<T>>;
    template<typename T> using deque  = std::deque<T, polymorphic_allocator<T>>;
    template<typename T> using list   = std::list<T, polymorphic_allocator<T>>;
    using string  = std::basic_string<char, std::char_traits<char>, polymorphic_allocator<char>>;
    using wstring = std::basic_string<wchar_t, std::char_traits<wchar_t>, polymorphic_allocator<wchar_t>>;
    template<typename K, typename V> using map     = std::map<K, V, std::less<K>, polymorphic_allocator<std::pair<const K, V>>>;
    template<typename K, typename V> using unordered_map = std::unordered_map<K, V, std::hash<K>, std::equal_to<K>, polymorphic_allocator<std::pair<const K, V>>>;
    // ... 等其他容器
}
```

### 全局 resource 管理

```cpp
memory_resource* get_default_resource() noexcept;          // 获取当前默认 resource
memory_resource* set_default_resource(memory_resource* r) noexcept;  // 替换默认 resource；若 r==nullptr 则设为 new_delete_resource()
```

默认 resource 是全局状态，存储在函数局部静态变量中（线程安全初始化）。

---

## 第 4 层: 行为契约

### `memory_resource` 核心契约

| 操作 | 前置条件 | 后置条件 | 异常 |
|------|---------|---------|------|
| `allocate(bytes, alignment)` | `alignment` 是 2 的幂 | 返回非空指针，对齐到 `alignment`，至少 `bytes` 字节可用 | `std::bad_alloc` 当无法满足请求 |
| `deallocate(p, bytes, alignment)` | `p` 来自同一 resource 的 `allocate(bytes, alignment)`，或为 `nullptr` | 内存回归 resource 管理 | `noexcept` 级（不抛） |
| `is_equal(other)` | 无 | 返回 `this == &other \|\| do_is_equal(other)` | `noexcept` |

**invariant**：
- `p != nullptr` 时，`deallocate(p, n, a)` 中的 `n` 和 `a` 必须与 `allocate` 时的值相等。这是与传统 `free(p)` 最关键的区别——resource 需要知道大小和对齐才能正确回收。
- `allocate(0, a)` 的行为是实现定义的，但必须是良定义的。

### `polymorphic_allocator` 关键契约

| 操作 | 语义 |
|------|------|
| 拷贝构造 | 共享同一个 `memory_resource*`（浅拷贝） |
| 赋值 | `= delete` |
| 不同 `value_type` 间的拷贝构造 | 共享同一 resource；允许 `polymorphic_allocator<int>` → `polymorphic_allocator<double>` |
| `operator==` | 调用 `*a.resource() == *b.resource()` — 比较的是 resource 的 `do_is_equal`，不是指针 |
| 容器拷贝传播 | `select_on_container_copy_construction()` 返回**默认构造的 allocator**（即 `get_default_resource()`）。新容器不继承源容器的 resource。 |
| 容器移动传播 | 不传播。移动时若 `*a.resource() != *b.resource()`，移动退化为逐元素拷贝。 |

**这是最容易被误解的部分**：

```cpp
monotonic_buffer_resource pool;
std::pmr::vector<int> v1(&pool);
v1.push_back(42);  // 分配在 pool 上

auto v2 = v1;      // v2 使用 get_default_resource()！不是 pool！
                   // 因为 select_on_container_copy_construction() 返回默认 allocator
```

如果你想让拷贝也使用同一 pool，需要显式传递 allocator：

```cpp
std::pmr::vector<int> v2(v1, &pool);  // v2 也使用 pool
```

### `monotonic_buffer_resource` 契约

| 操作 | 语义 |
|------|------|
| `do_allocate(0, a)` | 内部将 0 提升为 1 字节（`__builtin_expect(__bytes == 0, false)` → `__bytes = 1`），避免返回相同指针 |
| `do_deallocate(p, n, a)` | **空操作**。内存不归还，直到 `release()` 或析构 |
| 构造时提供 buffer | 初始分配在提供的内存上执行；耗尽后从 upstream 分配新 chunk |
| 构造时未提供 buffer | 首次分配从 upstream 获取；默认首次请求大小 = `_S_init_bufsize = 128 * sizeof(void*)` |
| `release()` | 释放所有从 upstream 获取的 chunk，恢复初始 buffer 状态 |
| 析构 | 调用 `release()` |
| 当前 buffer 耗尽 | 从 upstream 分配新 chunk，大小 = max(request, `_M_next_bufsiz`)，然后 `_M_next_bufsiz *= 1.5`（几何增长） |
| 对齐超过 buffer 剩余 | 调用 `std::align()`；若失败，分配新 chunk。旧 buffer 的剩余碎片被丢弃（不回收） |

### 线程安全

| 类型 | 线程安全 |
|------|---------|
| `memory_resource` | 取决于具体子类 |
| `new_delete_resource()` / `null_memory_resource()` | 线程安全（内部无状态） |
| `monotonic_buffer_resource` | **非线程安全** — 多线程并发 `allocate` 会数据竞争 |
| `unsynchronized_pool_resource` | **非线程安全** |
| `synchronized_pool_resource` | **线程安全** — 内部使用 `shared_mutex` + per-thread pool |
| `get_default_resource()` / `set_default_resource()` | 线程安全 — 内部使用 `atomic<memory_resource*>` 或 `mutex` 保护 |
| `polymorphic_allocator` | 取决于底层 `memory_resource` 的线程安全性 |

---

## 第 5 层: 实现原理

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    std::pmr::vector<int>                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │       polymorphic_allocator<int>                  │   │
│  │  ┌──────────────────────────────────────────┐    │   │
│  │  │    memory_resource* _M_resource          │    │   │
│  │  └──────────────┬───────────────────────────┘    │   │
│  └─────────────────┼────────────────────────────────┘   │
└────────────────────┼────────────────────────────────────┘
                     │ 虚函数调用
         ┌───────────▼───────────┐
         │   memory_resource     │  (抽象基类)
         │  do_allocate() = 0    │
         │  do_deallocate() = 0  │
         │  do_is_equal() = 0    │
         └───────────┬───────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
 monotonic      pool_resource    custom
_buffer_resource  (un/sync)     resource
```

**关键开销**：每次分配/释放都要经过一次虚函数调用。对比传统 `std::allocator`（编译期内联到 `::operator new`），pmr 多做了一次间接跳转。

### `memory_resource::allocate()` 的 NVI 包装

```text
allocate(bytes, alignment):
    return ::operator new(bytes, do_allocate(bytes, alignment))
    //                      ↑
    //     虚调用 → 子类的实际分配逻辑
    //     ::operator new 只是标记这个指针来自 new，让 LeakSanitizer 等工具追踪
```

这里的 `::operator new(bytes, void* p)` 是 placement new 的特殊重载——它不实际分配内存，只是返回 `p`，但告诉编译器/工具链"这个地址是通过 new 表达式获得的"。

### `monotonic_buffer_resource` — 指针递增分配（Bump Allocator）

```
_M_current_buf ──────────────►
┌────────────────────────────────────────────────┐
│  已分配  │         _M_avail (剩余可用)          │
└────────────────────────────────────────────────┘
           ↑
    下次 allocate 从这里开始

allocate(1024, 32):
    1. 将 _M_current_buf 用 std::align 对齐到 32
    2. 如果 aligned 后 _M_avail < 1024 → _M_new_buffer(1024, 32)
    3. p = _M_current_buf
    4. _M_current_buf += 1024
    5. _M_avail -= 1024
    6. return p

_M_new_buffer(bytes, alignment):
    1. n = max(bytes, _M_next_bufsiz)
    2. 从 upstream 分配 n + sizeof(_Chunk) 字节，对齐到 max(alignment, alignof(max_align_t))
    3. 在 buffer 末尾构造 _Chunk(记录 size, alignment, next 指针)
    4. _M_current_buf = 新 buffer 起始, _M_avail = n
    5. _M_next_bufsiz *= 1.5
```

复杂度：O(1)（不计对齐调整）。

### `unsynchronized_pool_resource` — 大小分级池

```
pool_sizes[] = {8, 16, 24, 32, 48, 64, 80, 96, 112, 128, 192, ...}

allocate(bytes):
    if bytes > largest_pooled_block:
        → 从 upstream 直接分配（作为 _BigBlock 记录）
    else:
        pool_index = _M_find_pool(bytes)  // 二分查找或直接索引
        return pools[pool_index].allocate(upstream_resource(), options)

Pool::allocate(r, opts):
    if (p = try_allocate())  // 扫描 chunk 链表找空闲块
        return p
    replenish(r, opts)       // 从 upstream 分配新 chunk
    return chunks.back().reserve(block_size)

deallocate(p, bytes, alignment):
    if bytes > largest_pooled_block:
        → 从 _M_unpooled 中移除并释放回 upstream
    else:
        pool_index = _M_find_pool(bytes)
        pools[pool_index].deallocate(upstream_resource(), p)
        // 注：即使 chunk 变空也不归还给 upstream，池只增不减
```

**Chunk 内部结构**：

```
┌──────────────────────────────────────────────────────┬──────────┐
│   block 0  │ block 1 │ ... │ block N-1               │ bitset   │
└──────────────────────────────────────────────────────┴──────────┘
                                                         ↑
                                                   N bits (64-bit words)

chunk::reserve(block_size):
    n = bitset.get_first_unset()    // 找到第一个未设置位（空闲块）
    if n == -1: return nullptr      // chunk 已满
    return _M_p + n * block_size

chunk::release(p, block_size):
    offset = (byte*)p - _M_p
    assert(offset % block_size == 0)
    n = offset / block_size
    bitset.clear(n)
```

bitset 用 `uint64_t` 数组实现，`get_first_unset()` 利用 `__builtin_ctzll`（count trailing zeros）在一条指令内找到第一个空闲块。`_M_next_word` 记住第一个不满的 word，避免每次都从头扫描。

### `synchronized_pool_resource` 的线程局部设计

```
synchronized_pool_resource
  ├─ _M_impl: __pool_resource        // "共享"池 — 当线程局部池满了以后从这里取
  ├─ _M_tpools: _TPools*             // 线程局部池链表
  ├─ _M_key: __gthread_key_t         // pthread key / TlsAlloc
  └─ _M_mx: shared_mutex

allocate(bytes, alignment):
    1. 如果 bytes > largest_pooled → _M_impl.allocate() (shared_mutex)
    2. tpools = _M_thread_specific_pools()  // 从 TLS 取本线程的 pool 集
    3. 尝试从 tpools 分配
    4. 若失败 → lock(_M_mx) → 从 _M_impl 分配 → 移动到 tpools
    5. 若仍失败 → lock(_M_mx) → _M_alloc_tpools() → 分配新 chunk
```

每个线程有自己的 pool chunk 集合。线程局部池满了才访问共享池（需要锁）。这是典型的 **Thread-Local Cache + Global Pool** 模式，与 jemalloc/tcmalloc 的设计思路一致。

---

## 第 6 层: 源码分析

> 源码来源：GCC 14.2.0 libstdc++ (GPLv3 + Runtime Library Exception)
> 文件：
> - `libstdc++-v3/include/bits/memory_resource.h` — `memory_resource` 基类 + `polymorphic_allocator`
> - `libstdc++-v3/include/std/memory_resource` — 具体 resource 类
> - `libstdc++-v3/src/c++17/memory_resource.cc` — 实现

### 6.1 `memory_resource` 基类的 NVI

```cpp
// bits/memory_resource.h:72-105 (GCC 14.2.0)
class memory_resource {
    static constexpr size_t _S_max_align = alignof(max_align_t);
public:
    [[nodiscard]]
    void*
    allocate(size_t __bytes, size_t __alignment = _S_max_align)
    __attribute__((__returns_nonnull__, __alloc_size__(2), __alloc_align__(3)))
    { return ::operator new(__bytes, do_allocate(__bytes, __alignment)); }

    void
    deallocate(void* __p, size_t __bytes, size_t __alignment = _S_max_align)
    __attribute__((__nonnull__))
    { return do_deallocate(__p, __bytes, __alignment); }
    // ...
private:
    virtual void* do_allocate(size_t __bytes, size_t __alignment) = 0;
    virtual void  do_deallocate(void* __p, size_t __bytes, size_t __alignment) = 0;
    virtual bool  do_is_equal(const memory_resource& __other) const noexcept = 0;
};
```

`__attribute__((__alloc_size__(2)))` 和 `__attribute__((__alloc_align__(3)))` 是 GCC 扩展，告诉编译器分配大小和对齐——用于 `-Walloc-size` 等静态检查。

`::operator new(__bytes, do_allocate(...))` 中的 `::operator new(size_t, void*)` 是标准库提供的 placement-new 重载——它不分配内存，直接返回第二个参数。这里的目的是让 ASan/LSan 知道这是一个合法分配。

### 6.2 全局 resource 的单例实现

```cpp
// memory_resource.cc:63-107 (GCC 14.2.0)
namespace {
    class newdel_res_t final : public memory_resource {
        void* do_allocate(size_t __bytes, size_t __alignment) override
        { return ::operator new(__bytes, std::align_val_t(__alignment)); }
        void  do_deallocate(void* __p, size_t __bytes, size_t __alignment) noexcept override
        { ::operator delete(__p, __bytes, std::align_val_t(__alignment)); }
        bool  do_is_equal(const memory_resource& __other) const noexcept override
        { return &__other == this; }
    };

    __constinit constant_init<newdel_res_t> newdel_res{};
}
```

使用 `constant_init` 包装保证编译期初始化（避免 static initialization order fiasco）。`constant_init<T>` 通过 `union { T obj; }` 技巧——联合体不自动调用析构函数，所以程序退出时 `newdel_res` 不会被析构（这是故意的，因为此时全局 `::operator delete` 可能已不可用）。

### 6.3 `monotonic_buffer_resource::do_allocate` — bump allocation 核心

```cpp
// std/memory_resource:420-442 (GCC 14.2.0)
void*
do_allocate(size_t __bytes, size_t __alignment) override
{
    if (__builtin_expect(__bytes == 0, false))
        __bytes = 1; // 确保不返回相同指针

    void* __p = std::align(__alignment, __bytes, _M_current_buf, _M_avail);
    if (__builtin_expect(__p == nullptr, false))
    {
        _M_new_buffer(__bytes, __alignment);
        __p = _M_current_buf;
    }
    _M_current_buf = (char*)_M_current_buf + __bytes;
    _M_avail -= __bytes;
    return __p;
}
```

**关键细节**：
- `std::align(alignment, bytes, ptr&, space&)` 尝试在 `[ptr, ptr+space)` 内找到一个对齐地址。成功返回对齐后的指针，并更新 `ptr` 和 `space`（缩减）。失败返回 `nullptr`。
- `__builtin_expect(__bytes == 0, false)` 是 `[[unlikely]]` 的 GCC 内置——零字节分配是极端罕见的情况。
- `_M_new_buffer` 在 buffer 末尾嵌入 `_Chunk` 元数据：`void* __back = (char*)__p + __size - sizeof(_Chunk)`，然后 placement new 构造 `_Chunk(size, align, next)`。

### 6.4 Chunk 链表和几何增长

```cpp
// memory_resource.cc:193-223 (GCC 14.2.0)
static constexpr size_t _S_init_bufsize = 128 * sizeof(void*);  // 1024 on 64-bit
static constexpr float _S_growth_factor = 1.5;

void
monotonic_buffer_resource::_M_new_buffer(size_t bytes, size_t alignment)
{
    const size_t n = std::max(bytes, _M_next_bufsiz);
    const size_t m = aligned_ceil(alignment, alignof(std::max_align_t));
    auto [p, size] = _Chunk::allocate(_M_upstream, n, m, _M_head);
    _M_current_buf = p;
    _M_avail = size;
    _M_next_bufsiz *= _S_growth_factor;
}
```

增长因子 1.5 与 `std::vector` 相同——这是内存分配器的甜点：1.5 允许复用之前释放的块（因为下一个块的大小仍小于前面所有块之和）。

### 6.5 Pool resource 的 bitset 空闲块追踪

```cpp
// memory_resource.cc:323-414 (GCC 14.2.0)
// bitset using uint64_t words
size_type get_first_unset() noexcept
{
    const size_type wd = _M_next_word;
    if (wd < nwords())
    {
        const size_type n = std::__countr_one(_M_words[wd]);
        if (n < bits_per_word)
        {
            const word bit = word(1) << n;
            _M_words[wd] |= bit;
            update_next_word();
            return (wd * bits_per_word) + n;
        }
    }
    return size_type(-1);
}
```

`std::__countr_one` 是 `std::countr_one(word)` — 返回一个 word 从最低位开始连续 1 的个数。这是单条 CPU 指令（`TZCNT` 在 x86 上）。当一个 word 全为 1 时，`_M_next_word` 前进到下一个不满的 word——避免每次分配都扫描整个 bitset。

### 6.6 大小对齐编码技巧

```cpp
// memory_resource.cc:136-146 (GCC 14.2.0)
// aligned_size<N>: size 存储在 value 的高位，log2(alignment) 存储在低位
template<unsigned N>
struct aligned_size
{
    constexpr aligned_size(size_t sz, size_t align) noexcept
    : value(sz | (std::__bit_width(align) - 1u)) {}
    // value = size | log2(alignment)
    // 例如 allocate(1024, 32) → value = 1024 + 5 = 1029
};
```

这利用了对齐总是 2 的幂且 size 是 N 的倍数（N=64 时低 6 位始终为 0）的性质，将对齐值和大小打包进一个 `size_t`，节省了元数据空间。

---

## 第 7 层: 对比与边界

### 对比：pmr vs 传统 `std::allocator`

| 维度 | `std::allocator<T>` | `std::pmr::polymorphic_allocator<T>` |
|------|---------------------|--------------------------------------|
| 分配策略 | 编译期固定（`new`/`delete`） | 运行期可切换 |
| 类型影响 | 是类型的一部分 → 不同 allocator = 不同类型 | 不是类型特征 → `pmr::vector<int>` 只有一个类型 |
| 虚函数开销 | 无（内联到 `::operator new`） | 每次分配一次虚调用 |
| 状态存储 | 通常无状态（EBO 优化到 0 字节） | 存储一个指针（8 字节 on 64-bit） |
| 容器间传播 | 取决于 traits（通常 `true_type`） | 拷贝/移动/swap 均不传播 |
| ABI 边界 | 类型包含分配器 → 接口必须是模板 | 类型不包含分配器 → 可以用于非模板接口 |
| 自定义难度 | 需实现完整分配器接口 + traits | 只需继承 `memory_resource`，实现 3 个函数 |

### 对比：pmr 内置 resource 性能特征

| Resource | 分配复杂度 | 释放复杂度 | 内存利用率 | 适用场景 |
|----------|-----------|-----------|-----------|---------|
| `new_delete_resource` | ~100ns (TLS cached) | ~100ns | 高（通用分配器） | 通用 |
| `monotonic_buffer_resource` | ~5ns (bump) | N/A (no-op) | 中（碎片无法回收） | 帧级临时分配 |
| `unsynchronized_pool_resource` | ~20ns (bitset扫描) | ~20ns (bitset清除) | 中（空 chunk 不归还） | 同大小对象池 |
| `synchronized_pool_resource` | ~30ns (TLS fast path) | ~30ns | 中 | 多线程对象池 |

> 数据为量级估计，实际取决于 CPU、缓存状态、分配模式。`monotonic` 的 5ns 量级是纯指针递增（~3条指令），pool 的 20ns 包含了 bitset 操作和分支预测。

### 对比：pmr vs `malloc`/`free` 直接使用

| 维度 | `malloc`/`free` | `pmr::monotonic` | `pmr::pool` |
|------|----------------|-----------------|-------------|
| RAII 集成 | 手动管理，易泄漏 | `release()` 或析构自动回收 | 析构自动回收 |
| 分配速度 | 慢（通用算法） | 极快（O(1) bump） | 快（O(1) pool） |
| 释放速度 | 慢 | N/A | 快 |
| 碎片化 | 会（随时间累积） | 不会（但空间可能浪费） | 不会（同大小块） |
| 异常安全 | 需手动保证 | RAII 自动保证 | RAII 自动保证 |
| 大小追踪 | 需自行记录 | 自动（`_Chunk` 链表） | 自动（bitset） |

### 对比：pmr vs jemalloc / tcmalloc / mimalloc

| 维度 | pmr 内置 resource | jemalloc / tcmalloc / mimalloc |
|------|-------------------|-------------------------------|
| 范围 | 选定的容器/分配 | 全局替换 `malloc` |
| 控制粒度 | 每个容器/对象池独立 | 全局配置 |
| 集成方式 | 使用 pmr 容器类型 | 链接时替换（LD_PRELOAD 或静态链接） |
| 适用场景 | 特定子系统的优化 | 整个程序的通用优化 |
| 学习曲线 | 需要修改容器类型 | 几乎透明（替换 malloc） |

**组合使用**：`mimalloc` 作为上游 resource，再套一层 `monotonic_buffer_resource`：

```cpp
// 假设有一个 MimallocResource : public memory_resource
MimallocResource mimalloc;
std::pmr::monotonic_buffer_resource frame_arena(65536, &mimalloc);
// frame_arena 的小 bump 分配走栈上 buffer
// 大分配走 mimalloc（比默认 malloc 快）
```

### pmr 与 RAII 的分层关系

RAII 在 pmr 体系中工作在**两个层次**：

```
层次 1: 容器 RAII
┌──────────────────────────────────────┐
│ pmr::vector<int> v(&arena);          │
│ v.push_back(42);   // allocate       │
│ // ...                               │
│ } ← 析构: v 对每个元素调用 deallocate │
│        → polymorphic_allocator       │
│        → memory_resource::do_deallocate │
└──────────────────────────────────────┘

层次 2: memory_resource RAII
┌──────────────────────────────────────────┐
│ {                                        │
│   monotonic_buffer_resource arena(4096); │
│   // 大量分配...                         │
│ } ← 析构: arena.release()                │
│      → 一次性归还所有 chunk 给 upstream   │
└──────────────────────────────────────────┘
```

这两个层次可以**解耦**：
- 容器的生命周期（层次 1）决定**何时**释放单个分配
- memory_resource 的生命周期（层次 2）决定**如何**以及**以什么粒度**释放

在 `monotonic` 的情况下，层次 1 的 `do_deallocate` 是空操作——释放延迟到层次 2。这是一种**策略上的 RAII**：不是每个分配都要立刻归还，而是在合适的时机批量处理。

### 设计取舍与陷阱

1. **`select_on_container_copy_construction()` 返回默认 allocator** — 这是最大陷阱。拷贝 `pmr::vector` 不会继承源容器的 resource。这是故意的设计选择：pmr allocator 没有值语义，两个 allocator 的"相等"取决于 resource 的 `do_is_equal`，不是指针比较。如果拷贝也共享 resource，那么一个栈上的 `monotonic_buffer_resource` 被拷贝出去后，副本容器会持有指向已销毁对象的指针。

2. **`do_is_equal` 的语义** — 默认实现 `return this == &__other`。两个不同的 `monotonic_buffer_resource` 实例永远不相等，即使行为完全相同。这导致移动和 swap 操作退化为拷贝。如果需要"可互换"的 resource，需要覆写 `do_is_equal`。

3. **虚函数开销是可选的** — 如果分配是热点路径且 resource 在编译期已知，可以用 `final` 关键字让编译器去虚化：

   ```cpp
   class MyResource final : public memory_resource { /* ... */ };
   ```

   当编译器能确定具体类型时，虚调用可以被内联消除。

4. **`monotonic_buffer_resource` 的对齐浪费** — `std::align` 失败时整个剩余 buffer 被丢弃（碎片），新 chunk 从 upstream 分配。这意味着频繁的极端对齐需求（如 SIMD 的 64 字节对齐）可能导致大量内存浪费。

---

## 常见面试题

**Q1: `pmr::polymorphic_allocator` 和传统 `std::allocator` 的本质区别是什么？**

传统 allocator 是类型的一部分（通过模板参数），不同 allocator 产生不同的容器类型。pmr allocator 使用类型擦除（通过 `memory_resource*`），所有 `pmr::vector<int>` 是同一类型，分配策略在运行时绑定。

**Q2: 为什么 `pmr::monotonic_buffer_resource::do_deallocate` 是空操作？这对 RAII 意味着什么？**

它把释放从"每次 deallocate"延迟到"resource 析构"。这在 RAII 框架下是合法的——资源（内存）的最终释放仍然由析构函数保证（`release()`），只是粒度从 per-object 变成了 per-frame/per-phase。

**Q3: 两个不同 `memory_resource` 的 `pmr::vector` 之间 swap 会发生什么？**

如果 `*a.resource() != *b.resource()`，swap 是未定义行为。因为 `propagate_on_container_swap` 是 `false_type`，标准要求两个 allocator 必须相等才能 swap。实际上大多数实现在 Debug 模式下会 assert。

**Q4: 什么场景下应该使用 `synchronized_pool_resource` 而不是 `unsynchronized_pool_resource`？**

当多个线程需要从同一个池中分配/释放对象。`synchronized_pool_resource` 使用 thread-local pools + shared mutex，大多数分配走 fast path（无锁）。如果确定只有单线程访问，`unsynchronized` 去掉了 TLS 和锁的开销。

**Q5: `polymorphic_allocator` 的大小是多少？它为什么能这么小？**

8 字节（64-bit 平台上）。它只存储一个 `memory_resource*`。传统 `std::allocator` 是空类（EBO 优化后占用 0 字节）。这 8 字节是"运行时多态"的代价。

---

## 延伸主题

- **自定义 `memory_resource` 实战** — 实现一个基于 `mmap`/`VirtualAlloc` 的 resource，或一个日志记录 resource（追踪所有分配）
- **`std::allocator_traits` 深度分析** — 理解 allocator 的完整契约，`construct`/`destroy` 在 C++20 的变化
- **C++20 `std::make_shared` 与 pmr** — C++20 添加了 `allocate_shared` 的 pmr 支持
- **游戏引擎内存架构** — 帧级 arena、对象池、streaming pool 的完整设计
- **mimalloc/jemalloc 源码阅读** — 现代通用分配器的内部实现（thread-local cache, size classes, huge pages）
