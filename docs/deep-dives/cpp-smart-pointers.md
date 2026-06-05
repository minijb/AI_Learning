---
title: "C++ 智能指针 深度剖析"
updated: 2026-06-05
---

# C++ 智能指针 深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 游戏引擎开发工程师 — [[../learning-plans/active/game-engine-dev/tutorials/00-cpp-for-game-engines#4-智能指针策略引擎中的取舍|C++ 引擎编程：语言特性精要]]
> 关联深度探索: [[raii-complete-analysis|RAII 深度剖析]]、[[cpp-special-member-functions|特殊成员函数]]
> 分析日期: 2026-05-28

---

## 第 1 层: 直觉理解

**智能指针是 "会自己收拾的指针"。**

裸指针（`T*`）只记录地址，不记录"谁负责销毁这个对象"。裸指针就像一张写了地址的便签——你拿着便签找到房子，但你不知道房东是谁、房租谁交。

三种智能指针各解决一个问题：

| 指针类型 | 它解决的问题 | 类比 |
|---------|-------------|------|
| `unique_ptr<T>` | **独占所有权**。只有一个人持有钥匙，搬走时交还房东 | 独租一套房，退租时你负责清理 |
| `shared_ptr<T>` | **共享所有权**。多人各有一把钥匙，最后走的人关灯锁门 | 合租，最后一个室友搬走时做退租打扫 |
| `weak_ptr<T>` | **观察但不拥有**。能看到房子是不是还在，但不能进去 | 路过看一眼——房子被拆了你知道，但你没有钥匙 |

`unique_ptr` 是默认选择。你用 `unique_ptr` 除非你有明确理由需要共享所有权；而你用 `shared_ptr` 时应该能解释清楚"为什么这里不能是 `unique_ptr`"。

---

## 第 2 层: 使用场景

### unique_ptr — 引擎中的默认选择

```cpp
// 场景 1：工厂函数返回动态创建的对象
std::unique_ptr<IRenderBackend> createBackend(RenderAPI api) {
    switch (api) {
        case RenderAPI::Vulkan:
            return std::make_unique<VulkanBackend>();
        case RenderAPI::DX12:
            return std::make_unique<DX12Backend>();
    }
    return nullptr;
}

// 场景 2：容器中的多态对象
class Scene {
    std::vector<std::unique_ptr<Entity>> entities_;
public:
    void add(std::unique_ptr<Entity> e) {
        entities_.push_back(std::move(e));
    }
    // 析构时所有 Entity 自动销毁，不需要手动 delete
};

// 场景 3：GPU 资源 + 自定义删除器
auto glDeleter = [](GLuint* id) {
    glDeleteBuffers(1, id);
    delete id;
};
std::unique_ptr<GLuint, decltype(glDeleter)> vbo(new GLuint{0}, glDeleter);
```

### shared_ptr — 少数合理场景

```cpp
// 场景 1：异步加载——加载线程和主线程都需要引用资源
class AsyncTexture {
    std::shared_ptr<TextureData> data_;
public:
    void loadAsync(const char* path) {
        auto data = std::make_shared<TextureData>(path);
        data_ = data;  // 主线程持有
        ioThread.submit([data] {  // 加载线程也持有
            data->decode();
        });
        // 两个线程都释放后，data 自动销毁
    }
};

// 场景 2：多个材质共享同一个 Shader
class Material {
    std::shared_ptr<ShaderProgram> shader_;  // 与其他材质共享
public:
    Material(std::shared_ptr<ShaderProgram> s) : shader_(std::move(s)) {}
};

// 场景 3：观察者模式的临时共享（C++26 之前）
// 之后可以用 std::observer_ptr
```

### weak_ptr — 打破循环引用 + 安全观察

```cpp
// 经典场景：树结构中的 parent 不应该导致 child 无法销毁
struct TreeNode : std::enable_shared_from_this<TreeNode> {
    std::weak_ptr<TreeNode> parent_;                             // 弱引用
    std::vector<std::shared_ptr<TreeNode>> children_;            // 强引用
};

// 使用 weak_ptr::lock() 安全访问
void TreeNode::doSomething() {
    if (auto p = parent_.lock()) {  // 如果 parent 还活着
        p->notify();
    }  // p 的 shared_ptr 临时副本在这里销毁
}
```

### 不适用智能指针的场景

| 不要用 | 原因 | 替代 |
|-------|------|------|
| `shared_ptr` 表示实体引用关系 | 引用计数原子操作在热路径上很贵 | 句柄系统（`uint32_t EntityID`） |
| `shared_ptr` 在紧凑循环中拷贝 | 每次拷贝都原子递增 | 传 `const shared_ptr&` 或用原始指针遍历 |
| `unique_ptr` 管理对象但需要共享观察 | 不能用 | `shared_ptr` + `weak_ptr`，或句柄系统 |
| 任何智能指针管理 `this` 时直接 `shared_ptr(this)` | 创建多个独立的 control block → 双重删除 | `enable_shared_from_this` |

---

## 第 3 层: API 层

### `std::unique_ptr<T, Deleter>`（C++11）

```cpp
template <class T, class Deleter = std::default_delete<T>>
class unique_ptr {
public:
    // 构造
    constexpr unique_ptr() noexcept;                     // 空指针
    constexpr unique_ptr(std::nullptr_t) noexcept;
    explicit constexpr unique_ptr(pointer p) noexcept;   // 接管裸指针
    constexpr unique_ptr(pointer p, const Deleter& d);   // 接管 + 自定义删除器
    constexpr unique_ptr(unique_ptr&& u) noexcept;        // 移动

    // 禁止拷贝
    unique_ptr(const unique_ptr&) = delete;

    // 析构：若非空，调用 Deleter(ptr)
    constexpr ~unique_ptr();

    // 访问
    pointer   get() const noexcept;          // 获取裸指针（所有权不移交）
    Deleter&  get_deleter() noexcept;
    T&        operator*() const;             // 解引用（前置：非空）
    pointer   operator->() const noexcept;

    // 所有权操作
    pointer   release() noexcept;            // 放弃所有权，返回裸指针
    void      reset(pointer p = nullptr);    // 释放旧资源，接管新资源
    void      swap(unique_ptr& other);

    explicit operator bool() const noexcept; // 非空检查
};

// 工厂函数
template <class T, class... Args>
unique_ptr<T> make_unique(Args&&... args);       // C++14

template <class T>
unique_ptr<T> make_unique_for_overwrite();       // C++20（不初始化值）
```

### `std::shared_ptr<T>`（C++11）

```cpp
template <class T>
class shared_ptr {
public:
    // 构造
    constexpr shared_ptr() noexcept;
    constexpr shared_ptr(std::nullptr_t) noexcept;
    template <class Y> explicit shared_ptr(Y* p);          // 接管裸指针
    template <class Y, class Deleter>
        shared_ptr(Y* p, Deleter d);                       // + 自定义删除器
    shared_ptr(const shared_ptr& r) noexcept;              // 拷贝（引用计数+1）
    shared_ptr(shared_ptr&& r) noexcept;                   // 移动（源置空）
    template <class Y> shared_ptr(const shared_ptr<Y>& r); // 派生类转换
    template <class Y> explicit shared_ptr(const weak_ptr<Y>& r);  // 从 weak_ptr 提升

    // 析构：引用计数-1，归零时释放
    ~shared_ptr();

    // 访问
    T*        get() const noexcept;
    T&        operator*() const;
    T*        operator->() const noexcept;
    long      use_count() const noexcept;      // 引用次数（调试用，不要用于逻辑判断！）

    // 所有权
    void      reset();
    template <class Y> void reset(Y* p);
    void      swap(shared_ptr& other);
    explicit  operator bool() const noexcept;

    // 比较
    bool owner_before(const shared_ptr<T>& other) const;   // 基于 control block 地址
};

// 工厂函数
template <class T, class... Args>
shared_ptr<T> make_shared(Args&&... args);                 // C++11

template <class T>
shared_ptr<T> make_shared_for_overwrite();                 // C++20

// 转型
template <class T, class U>
shared_ptr<T> static_pointer_cast(const shared_ptr<U>& r);
template <class T, class U>
shared_ptr<T> dynamic_pointer_cast(const shared_ptr<U>& r);
```

### `std::weak_ptr<T>`（C++11）

```cpp
template <class T>
class weak_ptr {
public:
    constexpr weak_ptr() noexcept;
    weak_ptr(const weak_ptr& r) noexcept;
    template <class Y> weak_ptr(const shared_ptr<Y>& r) noexcept;  // 从 shared_ptr 创建

    weak_ptr& operator=(const weak_ptr& r) noexcept;

    // 核心操作
    bool        expired() const noexcept;        // 被观察对象是否已销毁
    shared_ptr<T> lock() const noexcept;         // 尝试获取 shared_ptr
    long        use_count() const noexcept;      // shared_ptr 的引用计数
    void        reset() noexcept;                // 放弃观察
};
```

### `std::enable_shared_from_this<T>`（C++11）

```cpp
template <class T>
class enable_shared_from_this {
protected:
    constexpr enable_shared_from_this() noexcept;
    enable_shared_from_this(const enable_shared_from_this&) noexcept;
    ~enable_shared_from_this();

public:
    shared_ptr<T> shared_from_this();            // 获取管理 this 的 shared_ptr
    shared_ptr<const T> shared_from_this() const;
    weak_ptr<T> weak_from_this() noexcept;       // C++17
};
```

---

## 第 4 层: 行为契约

### unique_ptr

| 操作 | 前置条件 | 后置条件 | 异常 |
|------|---------|---------|------|
| `unique_ptr(p)` | `p` 由 `new` 分配或为 `nullptr` | `get() == p` | `noexcept` |
| `~unique_ptr()` | 无 | 若 `get()` 非空，`Deleter(get())` 已调用 | 要求 Deleter 不抛异常 |
| `release()` | 无 | `get() == nullptr`，返回旧指针 | `noexcept` |
| `reset(q)` | `q` 由匹配的 `new` 分配 | 旧资源已释放，`get() == q` | `noexcept` |
| 移动构造/赋值 | 源可移动 | 源 `get() == nullptr`，目标 `get()` 为源旧值 | `noexcept` |

### shared_ptr

| 操作 | 行为 |
|------|------|
| 拷贝构造 | `use_count` 原子递增 1 |
| 拷贝赋值 | 左侧旧引用 `use_count-1`，右侧 `use_count+1` |
| 移动构造 | 源 `use_count` 不变，源指针置空——**无原子操作** |
| 析构 | `use_count` 原子递减 1；若归零 → 调用 deleter → `weak_count-1` |
| `reset()` | 等价于 `shared_ptr().swap(*this)` |
| 线程安全 | 引用计数操作是原子的（线程安全）；被指向对象的访问需要外部同步 |

### weak_ptr

| 操作 | 行为 |
|------|------|
| `lock()` | 原子读取 `use_count`；若 > 0 → CAS 递增 +1，返回 `shared_ptr`；若 = 0 → 返回空 `shared_ptr` |
| `expired()` | `use_count() == 0` |
| 为什么需要 `lock()` 而不是直接 `expired()` + `*shared_ptr` | TOCTOU 竞态：`expired()` 返回 false 后到实际解引用之间，对象可能被其他线程销毁 |

### enable_shared_from_this 的前置条件

```cpp
// ✓ 正确用法
struct Good : std::enable_shared_from_this<Good> {
    std::shared_ptr<Good> getPtr() {
        return shared_from_this();  // OK —— Good 被 shared_ptr 管理
    }
};
auto g = std::make_shared<Good>();
g->getPtr();  // OK

// ✗ 错误用法
Good bad;
bad.getPtr();  // 抛出 std::bad_weak_ptr —— bad 不在 shared_ptr 中！
```

---

## 第 5 层: 实现原理

### unique_ptr 的内存布局

`unique_ptr<T>` = 一个指针的大小（8 字节，64 位），前提是 Deleter 为空类（`default_delete`）。

```
unique_ptr<int>:
  ┌──────────┐
  │  int* p  │  8 bytes
  └──────────┘
  (default_delete 通过 EBO 不占空间)

unique_ptr<FILE, FileDeleter>:
  ┌──────────┬────────────┐
  │ FILE* p  │ FileDeleter│  8 + sizeof(FileDeleter)
  └──────────┴────────────┘
```

### shared_ptr 的内存布局

`shared_ptr<T>` = 两个指针的大小（16 字节，64 位）：

```
shared_ptr<int>:
  ┌──────────┬───────────────┐
  │ T* ptr   │ control_block* │  8 + 8 = 16 bytes
  └──────────┴───────────────┘
       │              │
       │              ▼
       │    ┌─────────────────────┐
       │    │ vtable*             │  虚函数表指针
       │    │ use_count  (strong) │  引用计数（原子变量）
       │    │ weak_count (weak)   │  弱引用计数（原子变量）
       │    │ Deleter             │  删除器（可能空）
       │    │ Allocator           │  分配器（可能空）
       │    └─────────────────────┘
       ▼
  ┌──────────┐
  │ managed  │  被管理的对象
  │ object   │
  └──────────┘
```

### control block 何时创建

| 构造方式 | control block 的分配 |
|---------|---------------------|
| `shared_ptr<T>(new T(...))` | 单独堆分配（两次分配：对象 + control block） |
| `make_shared<T>(...)` | 单次分配（对象和 control block 连续存放） |
| `shared_ptr(unique_ptr<T>)` | 从 unique_ptr 转移时创建 control block |
| 拷贝 shared_ptr | 不创建——复用已有的 control block |
| 从 weak_ptr::lock() | 不创建——复用已有的 control block |

**关键洞察——`make_shared` 的布局优化：**

```
make_shared<int>(42):

  单次堆分配（连续内存块）：
  ┌──────────────────────────────────┐
  │ vtable* │ use_count │ weak_count │  control block 头部
  │   42    │  (padding)             │  托管对象
  └──────────────────────────────────┘
        ▲         ▲
        │         │
  shared_ptr 的 control_block 指针指向头部
  shared_ptr 的 ptr 指针指向托管对象
```

**优点**：一次分配代替两次 → 更快、缓存更友好。

**缺点**：所有 `weak_ptr` 释放前，整个内存块（包括已经销毁的托管对象所占的空间）不会归还给 OS。如果有大量长生命周期 `weak_ptr`，可能造成内存滞留。

### unique_ptr 的算法（伪代码）

```
class unique_ptr<T, Deleter = default_delete<T>>:
    ptr: T*

    destructor():
        if ptr != null:
            Deleter()(ptr)

    release() -> T*:
        old = ptr
        ptr = null
        return old

    reset(new_ptr: T* = null):
        old = ptr
        ptr = new_ptr
        if old != null:
            Deleter()(old)

    move_construct(other: unique_ptr&&):
        ptr = other.release()    // other 的 ptr 被置空
        deleter = move(other.deleter)
```

### shared_ptr 的引用计数算法（伪代码）

基于 libc++ 的实现（`__shared_count` + `__shared_weak_count`）：

```
class shared_ptr<T>:
    ptr: T*
    cntl: __shared_weak_count*    // control block

    copy_construct(other: shared_ptr&):
        ptr = other.ptr
        cntl = other.cntl
        cntl.__add_shared()       // use_count += 1 (atomic, relaxed)

    destructor():
        if cntl != null:
            if cntl.__release_shared():   // use_count -= 1 (atomic, acq_rel)
                                          // 返回 true = 计数归零
                cntl = null

    move_construct(other: shared_ptr&&):
        ptr = other.ptr
        cntl = other.cntl
        other.ptr = null           // 源置空——无原子操作！
        other.cntl = null

class __shared_weak_count:
    shared_owners: long     // strong count (use_count = shared_owners + 1)
    weak_owners: long       // weak count

    __add_shared():
        atomic_fetch_add(shared_owners, 1, relaxed)

    __release_shared() -> bool:
        // 原子递减并检查是否归零
        if atomic_fetch_sub(shared_owners, 1, acq_rel) == 0:
            __on_zero_shared()    // 调用 Deleter(ptr)，销毁对象
            __release_weak()      // weak count -= 1
            return true
        return false

    __add_weak():
        atomic_fetch_add(weak_owners, 1, relaxed)

    __release_weak():
        if atomic_fetch_sub(weak_owners, 1, acq_rel) == 0:
            __on_zero_shared_weak()  // 释放 control block 自身
```

**内存序选择**：
- `shared_owners` 递增用 `relaxed`：只需要原子性，不需要与其他内存操作同步
- `shared_owners` 递减用 `acq_rel`：释放对象前必须看到所有线程对此对象的写入
- 参见 libc++ 的注释：`// NOTE: Relaxed and acq/rel atomics (for increment and decrement respectively) should be sufficient for thread safety.`

### weak_ptr::lock() 的算法（伪代码）

```
function weak_ptr.lock() -> shared_ptr:
    // 原子读取 use_count
    count = atomic_load(cntl->shared_owners, relaxed)

    loop:
        if count == -1:     // 所有 strong ref 已释放（shared_owners 从 0 开始计数）
            return shared_ptr()  // 空

        // CAS: 如果 shared_owners 还是 count，设为 count + 1
        if atomic_compare_exchange_weak(cntl->shared_owners,
                                        &count, count + 1,
                                        acq_rel, relaxed):
            return shared_ptr(ptr, cntl)  // 成功提升
        // 否则 retry（count 已被 CAS 更新为当前值）
```

**为什么必须用 CAS 循环？**

线程 A 和 B 同时调用 `lock()`，且此时 `use_count == 1`（都看到对象还活着）。如果不用 CAS，两个线程都可能"认为"自己成功增加了计数 → `use_count` 变成 3 但实际只有 2 个 `shared_ptr` → 计数永不归零。CAS 保证只有一个线程成功递增。

### libstdc++ 的双计数器优化

libstdc++ 在 `_Sp_counted_base<_S_atomic>::_M_release()` 中使用了**双字 CAS 优化**：

当两个引用计数都是 1（最后一个 strong ref，无 weak ref），它在一条 64 位 CAS 中同时操作 `use_count` 和 `weak_count`，跳过递减+销毁的两步流程直接回收整个 control block + 对象。这是在 x86-64 上利用了 8 字节 CAS 可以原子操作 16 字节的条件（lock cmpxchg16b）。

---

## 第 6 层: 源码分析

### 6.1 libc++ — `__shared_weak_count` 控制块

**项目**: LLVM libc++
**版本**: `main` 分支（2025）
**文件**: `libcxx/include/__memory/shared_count.h`

```cpp
class __shared_count {
protected:
    long __shared_owners_;    // use_count = __shared_owners_ + 1

    virtual void __on_zero_shared() noexcept = 0;  // 析构托管对象

public:
    explicit __shared_count(long __refs = 0) noexcept : __shared_owners_(__refs) {}

    void __add_shared() noexcept {
        __libcpp_atomic_refcount_increment(__shared_owners_);  // relaxed
    }

    bool __release_shared() noexcept {
        if (__libcpp_atomic_refcount_decrement(__shared_owners_) == -1) {  // acq_rel
            __on_zero_shared();
            return true;
        }
        return false;
    }
};

class __shared_weak_count : private __shared_count {
    long __shared_weak_owners_;

    virtual void __on_zero_shared_weak() noexcept = 0;  // 释放 control block

public:
    void __add_weak() noexcept {
        __libcpp_atomic_refcount_increment(__shared_weak_owners_);
    }

    void __release_shared() noexcept {
        if (__shared_count::__release_shared())  // 先减 strong
            __release_weak();                      // strong 归零后减 weak
    }
};
```

**设计意图**：`__shared_owners_` 使用 `-1` 表示 "0 个 shared_ptr"。这使得 `use_count()` 实现极为简单——返回 `shared_owners_ + 1`。

### 6.2 libc++ — `__shared_ptr_pointer`（裸指针 + 删除器的控制块）

```cpp
template <class _Tp, class _Dp, class _Alloc>
class __shared_ptr_pointer : public __shared_weak_count {
    // __compressed_pair 的 triplet 版本:
    // 利用 EBO/[[no_unique_address]] 消除空删除器和空分配器的空间开销
    _LIBCPP_COMPRESSED_TRIPLE(_Tp, __ptr_, _Dp, __deleter_, _Alloc, __alloc_);

    void __on_zero_shared() noexcept override {
        __deleter_(__ptr_);         // 调用自定义删除器
        __deleter_.~_Dp();          // 销毁删除器（可能是函数对象）
    }

    void __on_zero_shared_weak() noexcept override {
        // 使用分配器释放 control block 自身
        typename __allocator_traits_rebind<_Alloc, __shared_ptr_pointer>::type __a(__alloc_);
        __alloc_.~_Alloc();
        __a.deallocate(pointer_traits<...>::pointer_to(*this), 1);
    }
};
```

**核心要点**：虚函数 `__on_zero_shared` 和 `__on_zero_shared_weak` 通过 vtable 实现了**类型擦除（type erasure）**——`shared_ptr<void>` 不需要知道具体类型，也能正确调用删除器和释放 control block。

### 6.3 libc++ — `__shared_ptr_emplace`（make_shared 的控制块）

```cpp
template <class _Tp, class _Alloc>
struct __shared_ptr_emplace : __shared_weak_count {
    // make_shared/T 和 control block 在同一个内存块中！
    struct _Storage {
        struct _Data {
            _LIBCPP_COMPRESSED_PAIR(_Alloc, __alloc_, __value_type, __elem_);
        };
        alignas(_Data) char __buffer_[sizeof(_Data)];
        // ...
    };
    _Storage __storage_;

    // 构造：在 __storage_ 中原地构造对象
    template <class... _Args>
    explicit __shared_ptr_emplace(_Alloc __a, _Args&&... __args)
        : __storage_(std::move(__a)) {
        // 使用 rebind 的分配器在 __storage_ 内原地构造对象
        ::new (__get_elem()) __value_type(std::forward<_Args>(__args)...);
    }

    void __on_zero_shared() noexcept override {
        __get_elem()->~__value_type();   // 只析构对象，不释放内存
    }

    void __on_zero_shared_weak() noexcept override {
        // 当所有 weak_ptr 也释放时，才释放整个内存块
        using _CBAlloc = __allocator_traits_rebind<_Alloc, __shared_ptr_emplace>::type;
        _CBAlloc __tmp(*__get_alloc());
        __storage_.~_Storage();
        __tmp.deallocate(pointer_traits<...>::pointer_to(*this), 1);
    }
};
```

**布局图**：

```
make_shared<T>(args...) 在一次分配中创建的内存块：

  ┌───────────────────────────────────────────────────┐
  │ __shared_weak_count (基类)                         │
  │   long __shared_owners_                           │
  │   long __shared_weak_owners_                      │
  ├───────────────────────────────────────────────────┤
  │ _Storage::__buffer__                               │
  │   ┌─────────────────┬─────────────────┐           │
  │   │ _Alloc (EBO)    │ T (托管对象)     │           │
  │   └─────────────────┴─────────────────┘           │
  └───────────────────────────────────────────────────┘

shared_ptr<T>:
  ptr → 指向 _Storage 中的 T
  cntl → 指向整个内存块的起始（基类子对象）
```

### 6.4 libstdc++ — `_Sp_counted_base` 的三种同步策略

**项目**: GCC libstdc++
**版本**: `master` 分支（2025）
**文件**: `libstdc++-v3/include/bits/shared_ptr_base.h`

```cpp
template<_Lock_policy _Lp = __default_lock_policy>
class _Sp_counted_base : public _Mutex_base<_Lp> {
    _Atomic_word _M_use_count;   // #shared
    _Atomic_word _M_weak_count;  // #weak + (#shared != 0)
    // ...
};
```

三种锁策略（编译期选择）：

| 策略 | `_M_use_count` 递增 | `_M_use_count` 递减 | 适用平台 |
|------|---------------------|---------------------|---------|
| `_S_single` | 普通 `+=1` | 普通 `-=1` | 单线程（`-D_GLIBCXX_USE_SCHED_YIELD`） |
| `_S_atomic` | `__atomic_add_fetch(relaxed)` | `__atomic_add_fetch(acq_rel)` + 双字优化 | 有原子指令的现代 CPU |
| `_S_mutex` | mutex 保护 | mutex 保护 | 无原子指令的嵌入式平台 |

`_S_atomic` 的 `_M_release()` 中有一个精巧优化：用 64 位 CAS 同时读取/修改 `use_count` 和 `weak_count`——当两者都是 1 时（最后一个 strong ref + 第一个 weak ref），一条指令完成"检查两个计数并同时设置为 0 + 析构对象 + 释放 control block"，跳过单独递减再检查的两次原子操作。

### 6.5 libstdc++ — `_Sp_counted_ptr_inplace`（make_shared 的完整实现）

```cpp
template<typename _Tp, typename _Alloc, _Lock_policy _Lp>
class _Sp_counted_ptr_inplace final : public _Sp_counted_base<_Lp> {
    // EBO 优化空分配器
    [[__no_unique_address__]] _Sp_ebo_helper<_Alloc> _M_alloc;
    // 对齐缓冲区存放托管对象
    __gnu_cxx::__aligned_buffer<__remove_cv_t<_Tp>> _M_storage;

    // 构造：在 _M_storage 中原地构造 T
    template<typename... _Args>
    _Sp_counted_ptr_inplace(_Alloc __a, _Args&&... __args)
        : _M_alloc{__a} {
        allocator_traits<_Alloc>::construct(__a, _M_ptr(),
            std::forward<_Args>(__args)...);
    }

    void _M_dispose() noexcept override {
        allocator_traits<_Alloc>::destroy(_M_alloc._M_obj, _M_ptr());
    }

    void _M_destroy() noexcept override {
        // 使用 rebind 后的分配器释放整个内存块
        __allocator_type __a(_M_alloc._M_obj);
        this->~_Sp_counted_ptr_inplace();
    }
};
```

---

## 第 7 层: 对比与边界

### 7.1 unique_ptr vs shared_ptr 性能

```
Benchmark: 创建/销毁 1M 个指针（x86-64, -O2）

unique_ptr<int>     ~3ms    （1 次 new/delete）
shared_ptr<int>     ~18ms   （2 次 new/delete + 原子操作）
                    ─────
make_shared<int>    ~12ms   （1 次分配，但仍有原子操作）
make_unique<int>    ~3ms    （与 unique_ptr 相同）

拷贝 1M 次：
unique_ptr         不能拷贝
shared_ptr          ~25ms   （100% 原子递增/递减开销）
shared_ptr (move)   ~2ms    （无原子操作！）
```

**关键结论**：`shared_ptr` 的移动操作比拷贝快约 **12 倍**——移动不碰原子变量。

### 7.2 make_shared vs new + shared_ptr

| | `make_shared<T>(args)` | `shared_ptr<T>(new T(args))` |
|---|---|---|
| 堆分配次数 | 1 | 2（对象 + control block） |
| 异常安全 | 安全（构造失败时自动清理） | 可能泄漏（如果 new 和 shared_ptr 构造之间抛异常） |
| 内存布局 | 对象和 control block 相邻（缓存友好） | 分散在两个堆位置 |
| weak_ptr 内存滞留 | 所有 weak_ptr 释放前，对象占用的空间不归还 OS | 对象释放后立即归还，control block 等待 weak_ptr |
| 自定义删除器 | 不支持 | 支持 |

```cpp
// 异常安全对比
void bad(std::shared_ptr<int> a, std::shared_ptr<int> b);
bad(shared_ptr<int>(new int(1)), shared_ptr<int>(new int(2)));
// 编译器可能：
// 1. new int(1)
// 2. new int(2)
// 3. shared_ptr<int>(...)  ← 如果抛异常 → (1) 泄漏！
//
// 正确：
bad(make_shared<int>(1), make_shared<int>(2));
```

### 7.3 智能指针在游戏引擎中的替代方案

| 引擎 | 策略 |
|------|------|
| **Unreal Engine 5** | `TUniquePtr`（自实现，避免 `<memory>` 头文件体积）、`TSharedPtr`（线程安全引用计数）、`TWeakPtr`、`TSharedRef`（不可空的 shared_ptr） |
| **Godot 4** | `Ref<T>`（侵入式引用计数，对象继承 `RefCounted`）+ `memdelete()` 手动释放非引用计数对象 |
| **Unity (IL2CPP)** | GC——引用计数和标记清除混合 |
| **Doom 3 BFG** | 无智能指针。原始指针 + Arena 分配器 + 严格的显式生命周期 |

**为什么引擎自实现 shared_ptr？**

1. **模板实例化爆炸**：`std::shared_ptr<T>` 对每种 T 实例化一套代码。在数百种资源类型的引擎中，这导致显著的编译时间和二进制膨胀。
2. **侵入式引用计数**（Godot 的 `Ref<T>`）：引用计数存储在对象内部而非 control block 中——省去了一次堆分配，且允许从 `this` 安全获取 `Ref<T>` 而不需要 `enable_shared_from_this`。
3. **线程安全定制**：引擎可以在编译期关闭引用计数的原子操作（单线程子系统），或使用更轻量的同步原语。
4. **调试与分析**：自实现可以集成内存追踪、泄漏检测、引用循环检测。

### 7.4 unique_ptr vs T*：真的零开销吗？

```cpp
// 函数参数
void process(const std::unique_ptr<Foo>& foo);  // 不好——强制调用者使用 unique_ptr
void process(Foo* foo);                          // 好——接受任何来源的 Foo

// 返回
std::unique_ptr<Foo> create();  // 好——明确转移所有权
Foo* create();                  // 不好——谁负责 delete？
```

**核心指导**（C++ Core Guidelines）：

- **传参**：用 `T*` 或 `T&`（不转移所有权）
- **返回**：用 `unique_ptr<T>`（转移所有权）
- **存储成员**：用 `unique_ptr<T>` 或 `T`（值语义）

### 7.5 陷阱集合

**陷阱 1**：`shared_ptr(this)` 地狱

```cpp
struct Node {
    std::vector<std::shared_ptr<Node>> children;

    std::shared_ptr<Node> getShared() {
        return std::shared_ptr<Node>(this);  // 灾难！！！
        // 每次调用创建独立的 control block
        // use_count 都是 1 → 多次 delete！
    }
};

// 修复
struct Node : std::enable_shared_from_this<Node> {
    std::shared_ptr<Node> getShared() {
        return shared_from_this();  // 复用已有 control block
    }
};
```

**陷阱 2**：`unique_ptr` 到 `shared_ptr` 的静默转换

```cpp
std::unique_ptr<Foo> u = std::make_unique<Foo>();
std::shared_ptr<Foo> s = std::move(u);
// u 是 nullptr！unique_ptr 的所有权被**转移**了
// 如果之后再使用 u → 空指针
```

**陷阱 3**：`use_count()` 竞态

```cpp
if (ptr.use_count() == 1) {
    // 另一个线程可能在这里创建了一个拷贝
    ptr->modify();  // 竞态！
}
// use_count() 只用于调试。永远不要用它来做逻辑判断！
```

**陷阱 4**：循环引用

```cpp
struct A { std::shared_ptr<B> b; };
struct B { std::shared_ptr<A> a; };

auto a = std::make_shared<A>();
auto b = std::make_shared<B>();
a->b = b;
b->a = a;
// a 和 b 的 use_count 都是 2
// 出作用域后各减到 1 → 永不释放 → 泄漏！
//
// 修复：其中一个用 weak_ptr
```

---

## 常见面试题

### Q1: "`unique_ptr` 和 `shared_ptr` 的区别？各自大小是多少？"

- `unique_ptr<T>`：独占所有权，不可拷贝，可移动。大小 = 1 个指针（8 字节，64 位），前提是默认删除器。
- `shared_ptr<T>`：共享所有权，可拷贝（引用计数+1）。大小 = 2 个指针（16 字节：对象指针 + control block 指针）。

### Q2: "`make_shared` 比 `new shared_ptr` 好在哪里？有什么缺点？"

**优点**：一次堆分配、异常安全、缓存局部性好。

**缺点**：不支持自定义删除器；如果存在长生命周期 `weak_ptr`，即使所有 `shared_ptr` 已释放，对象占用的内存也不会归还 OS（因为 control block 和对象在同一内存块中，control block 必须等 weak_ptr 也全部释放）。

### Q3: "为什么 `weak_ptr` 的 `lock()` 需要 CAS 循环？"

TOCTOU（time-of-check-time-of-use）问题。两个线程同时看到 `use_count == 1`，如果不用 CAS 原子地"检查+递增"，两个线程可能都认为自己成功递增了计数 → 引用计数永不归零。CAS 保证只有一个线程成功。

### Q4: "`shared_ptr` 的引用计数是线程安全的吗？"

引用计数**本身**的操作是线程安全的（原子操作）。但被指向的**对象的访问**不是——需要额外的同步（mutex 或 atomic）。拷贝 `shared_ptr` 本身在多线程中是安全的（各自操作各自的 `shared_ptr` 对象），但多个线程并发修改同一个 `shared_ptr` 变量不是线程安全的。

### Q5: "什么时候用 `weak_ptr`？什么时候不用？"

**用**：打破循环引用（如树的 parent 指针）、实现缓存/观察者（不需要延长对象生命周期）、异步回调中安全检测对象是否仍然存活。

**不用**：如果 `weak_ptr` 的性能开销（CAS 循环的 `lock()`）在热路径上不可接受；如果对象的生命周期已经通过架构保证了——用原始指针更高效。

---

## 延伸主题

1. **引擎自实现智能指针** — Unreal `TSharedPtr`、Godot `Ref<T>` 的侵入式引用计数设计
2. **`std::atomic<std::shared_ptr>`**（C++20）— 无锁的共享指针原子操作
3. **`std::observer_ptr`**（C++26 提案）— 零开销的非拥有指针
4. **句柄系统 vs 智能指针** — ECS 架构中 EntityID + generation 的悬垂引用检测
5. **`std::pmr` + 智能指针** — 多态分配器与智能指针的配合
