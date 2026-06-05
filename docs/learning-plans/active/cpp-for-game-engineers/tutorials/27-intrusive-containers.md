---
title: "Intrusive 容器与零分配数据结构"
updated: 2026-06-05
---

# Intrusive 容器与零分配数据结构

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 第8节 (自定义分配器入门), 第9节 (池分配器与自由链表)

---

## 1. 概念讲解

### 1.1 什么是 Intrusive 容器

传统 STL 容器（`std::list<T>`、`std::map<K,V>`）是**非侵入式**的：容器自己分配和管理节点，节点内部存储你的数据。每次插入都调用 `new` 分配一个节点对象。

**Intrusive 容器**反其道而行：**链表指针（next/prev）就放在你的数据结构内部**。容器不分配任何内存——它只是"穿针引线"，把已经存在的对象链接起来。

```
非侵入式 std::list<Entity>:
  [Entity data] ← 拷贝到 → [list_node{prev, next, Entity data}]  ← 堆分配！

侵入式 IntrusiveList<Entity>:
  [Entity{prev, next, ...data...}] ← 对象自带指针，容器只链接它们
```

**核心收益**：零分配插入删除。对象已经在内存中（栈、池、Arena），容器只修改指针。在 16.6ms 帧预算内，这意味着每帧可以零分配地管理成千上万个实体。

### 1.2 什么时候用 Intrusive 容器

| 场景 | 为什么 Intrusive |
|------|-----------------|
| 对象已被池/区域管理 | 对象已分配好了，只需链表连接 |
| 每帧高频插入/删除 | 零 malloc/free，缓存更友好 |
| 对象同时属于多个容器 | 内嵌多个 hook 节点，零开销多重索引 |
| 不需要容器管理生命周期 | 对象生命周期由池/ECS 管理 |
| 节省内存 | 不需要单独的节点分配开销（每个节点有 ~16-32 bytes 的 allocator 开销） |

### 1.3 Intrusive 单向链表

最小侵入——每个元素只需一个 `next` 指针（8 bytes 在 64 位）。适合只需要前向遍历的场景。

```cpp
struct IntrusiveSListNode {
    IntrusiveSListNode* next = nullptr;
};

// 你的数据类型继承这个节点
struct Entity : IntrusiveSListNode {
    uint32_t  id;
    float     x, y, z;
    // ... 更多数据
};
```

操作复杂度：
- `push_front`: O(1) — 修改 head 和新节点的 next
- `push_back`: O(n) — 无尾指针时需要遍历到末尾
- `pop_front`: O(1)
- `erase`: O(n) — 单向链表无法直接访问前驱

### 1.4 Intrusive 双向链表

每个元素携带 `prev` 和 `next` 两个指针（16 bytes 在 64 位）。支持 O(1) 任意位置插入/删除。

```cpp
struct IntrusiveDListNode {
    IntrusiveDListNode* prev = nullptr;
    IntrusiveDListNode* next = nullptr;
};
```

双向链表的核心优势是 `unlink()` —— 节点可以**把自己从链表中移除**，不需要知道它属于哪个容器：

```cpp
void unlink() {
    if (prev) prev->next = next;
    if (next) next->prev = prev;
    prev = next = nullptr;
}
```

### 1.5 Intrusive 哈希表

哈希表节点携带一个 `next` 指针形成桶链。元素本身包含哈希节点：

```cpp
struct IntrusiveHashNode {
    IntrusiveHashNode* hash_next = nullptr;
};

// 查找：hash(key) → bucket[index] → 遍历链表
```

结合双向链表和哈希表可以实现 **LRU 缓存**——双向链表维护访问顺序，哈希表提供 O(1) 查找。

### 1.6 多重成员关系：Hook 模式

一个对象可能需要同时出现在多个容器中（比如既在"激活实体"链表中，又在"可见实体"链表中）。两种方案：

**方案 A：多继承节点基类**（简单但有菱形继承风险）：
```cpp
struct Entity : IntrusiveActiveHook, IntrusiveVisibleHook { ... };
```

**方案 B：内嵌 Hook 成员**（推荐——更清晰）：
```cpp
struct Entity {
    IntrusiveDListNode activeLink;   // 在激活实体链表中
    IntrusiveDListNode visibleLink;  // 在可见实体链表中
    IntrusiveHashNode  nameHashLink; // 在名字哈希表中
    // 实际数据...
};
```

容器操作时需要从 hook 指针反推出包含它的对象。这通过 `offsetof` 或更安全的指针运算实现：

```cpp
// 从 activeLink 的地址计算 Entity 的地址
Entity* containerOf(IntrusiveDListNode* node) {
    return reinterpret_cast<Entity*>(
        reinterpret_cast<char*>(node) - offsetof(Entity, activeLink)
    );
}
```

### 1.7 与 Boost.Intrusive 的关系

Boost.Intrusive 提供了经过实战验证的侵入式容器实现，支持高级特性：

| 特性 | 说明 |
|------|------|
| `safe_link` | 调试模式下检测节点是否已链接、重复链接等错误 |
| `auto_unlink` | 对象析构时自动从容器中移除自己 |
| `link_mode` | `normal_link`（默认）、`safe_link`（调试）、`auto_unlink`（自动） |
| `constant_time_size` | 可选 O(1) `size()`，以额外内存为代价 |
| `cache_last` | 单向链表缓存尾节点，使 push_back 变为 O(1) |

在引擎中可以直接使用 Boost.Intrusive，但理解其实现原理至关重要——许多引擎（UE、Godot）在基础层有自己的实现，因为它们不能依赖 Boost。

---

## 2. 代码示例

### 2.1 完整的侵入式双向链表

```cpp
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <cassert>

// ========= 节点定义 =========
struct IntrusiveDListNode {
    IntrusiveDListNode* prev = this;  // 默认自环（空链表）
    IntrusiveDListNode* next = this;
    
    // 是否在链表中
    bool isLinked() const { return prev != this; }
    
    // 从链表中移除自己（不需要知道容器！）
    void unlink() {
        prev->next = next;
        next->prev = prev;
        prev = next = this;  // 重置为自环
    }
};

// ========= 容器辅助宏 =========
// 从成员指针获取容器指针
template <typename T, typename Member>
T* containerOf(Member T::*member, Member* ptr) {
    return reinterpret_cast<T*>(
        reinterpret_cast<char*>(ptr) - 
        reinterpret_cast<uintptr_t>(&(static_cast<T*>(nullptr)->*member))
    );
}

// 便捷宏
#define INTRUSIVE_CONTAINER_OF(ptr, T, member) \
    containerOf(&T::member, ptr)

// ========= 侵入式双向链表 =========
template <typename T, IntrusiveDListNode T::*HookPtr>
class IntrusiveList {
public:
    using value_type = T;
    
    IntrusiveList() = default;
    
    // 不可拷贝（容器不拥有对象）
    IntrusiveList(const IntrusiveList&) = delete;
    IntrusiveList& operator=(const IntrusiveList&) = delete;
    
    // 可移动：接管哨兵节点
    IntrusiveList(IntrusiveList&& other) noexcept {
        if (other.empty()) {
            sentinel_.prev = &sentinel_;
            sentinel_.next = &sentinel_;
        } else {
            sentinel_.prev = other.sentinel_.prev;
            sentinel_.next = other.sentinel_.next;
            sentinel_.prev->next = &sentinel_;
            sentinel_.next->prev = &sentinel_;
            other.sentinel_.prev = &other.sentinel_;
            other.sentinel_.next = &other.sentinel_;
        }
        size_ = other.size_;
        other.size_ = 0;
    }
    
    // ===== 容量 =====
    bool empty() const { return sentinel_.next == &sentinel_; }
    size_t size() const { return size_; }  // O(1)
    
    // ===== 插入 =====
    
    // 在头部插入
    void push_front(T& obj) {
        IntrusiveDListNode& node = obj.*HookPtr;
        assert(!node.isLinked());  // 不能重复插入！
        insertAfter(&sentinel_, &node);
    }
    
    // 在尾部插入
    void push_back(T& obj) {
        IntrusiveDListNode& node = obj.*HookPtr;
        assert(!node.isLinked());
        insertAfter(sentinel_.prev, &node);
    }
    
    // 在指定元素前插入
    void insert_before(T& before, T& obj) {
        IntrusiveDListNode& pos = before.*HookPtr;
        IntrusiveDListNode& node = obj.*HookPtr;
        assert(!node.isLinked());
        insertAfter(pos.prev, &node);
    }
    
    // ===== 访问 =====
    T& front() { 
        assert(!empty());
        return *INTRUSIVE_CONTAINER_OF(sentinel_.next, T, HookPtr);
    }
    
    T& back() {
        assert(!empty());
        return *INTRUSIVE_CONTAINER_OF(sentinel_.prev, T, HookPtr);
    }
    
    // ===== 删除 =====
    void pop_front() {
        assert(!empty());
        sentinel_.next->unlink();
        --size_;
    }
    
    void pop_back() {
        assert(!empty());
        sentinel_.prev->unlink();
        --size_;
    }
    
    // 删除指定元素（O(1)，因为双向链表可以直接访问前驱！）
    void erase(T& obj) {
        IntrusiveDListNode& node = obj.*HookPtr;
        assert(node.isLinked());
        node.unlink();
        --size_;
    }
    
    // 清空（所有节点的 unlink）
    void clear() {
        while (!empty()) {
            sentinel_.next->unlink();
            --size_;
        }
    }
    
    // ===== 迭代器 =====
    class iterator {
    public:
        using iterator_category = std::bidirectional_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using pointer = T*;
        using reference = T&;
        
        explicit iterator(IntrusiveDListNode* node) : current_(node) {}
        
        T& operator*() const {
            return *INTRUSIVE_CONTAINER_OF(current_, T, HookPtr);
        }
        T* operator->() const {
            return INTRUSIVE_CONTAINER_OF(current_, T, HookPtr);
        }
        
        iterator& operator++() { 
            current_ = current_->next;
            return *this; 
        }
        iterator operator++(int) {
            iterator tmp = *this;
            current_ = current_->next;
            return tmp;
        }
        
        iterator& operator--() {
            current_ = current_->prev;
            return *this;
        }
        iterator operator--(int) {
            iterator tmp = *this;
            current_ = current_->prev;
            return tmp;
        }
        
        bool operator==(const iterator& other) const { 
            return current_ == other.current_; 
        }
        bool operator!=(const iterator& other) const {
            return current_ != other.current_;
        }
        
    private:
        IntrusiveDListNode* current_;
    };
    
    iterator begin() { return iterator(sentinel_.next); }
    iterator end()   { return iterator(&sentinel_); }
    
private:
    void insertAfter(IntrusiveDListNode* pos, IntrusiveDListNode* node) {
        node->next = pos->next;
        node->prev = pos;
        pos->next->prev = node;
        pos->next = node;
        ++size_;
    }
    
    IntrusiveDListNode sentinel_;  // 哨兵节点
    size_t size_ = 0;
};

// ========= 测试用例 =========
struct Entity {
    uint32_t id;
    float x, y, z;
    IntrusiveDListNode link;  // 侵入式 hook
    
    Entity(uint32_t i, float px, float py, float pz)
        : id(i), x(px), y(py), z(pz) {}
};

void testIntrusiveList() {
    // 对象在栈上或池中——不需要 new！
    Entity e1{1, 0.0f, 0.0f, 0.0f};
    Entity e2{2, 1.0f, 0.0f, 0.0f};
    Entity e3{3, 2.0f, 0.0f, 0.0f};
    
    IntrusiveList<Entity, &Entity::link> activeList;
    
    // 零分配插入！
    activeList.push_back(e1);
    activeList.push_back(e2);
    activeList.push_front(e3);  // e3 在头部
    
    std::cout << "Active entities (" << activeList.size() << "):\n";
    for (auto& entity : activeList) {
        std::cout << "  Entity #" << entity.id 
                  << " at (" << entity.x << ", " << entity.y << ", " << entity.z << ")\n";
    }
    // 输出: Entity #3, Entity #1, Entity #2
    
    // O(1) 删除——不需要查找！
    activeList.erase(e1);
    std::cout << "After removing Entity #1: " << activeList.size() << " remaining\n";
}
```

### 2.2 侵入式哈希表

```cpp
#include <vector>
#include <functional>

template <typename T, IntrusiveDListNode T::*HookPtr>
class IntrusiveHashMap {
public:
    explicit IntrusiveHashMap(size_t bucketCount = 64)
        : buckets_(bucketCount) {}
    
    // 插入（key 由 T::getKey() 提供）
    void insert(T& obj) {
        size_t index = hash_(obj.getKey()) % buckets_.size();
        
        // 检查是否已存在
        for (auto it = buckets_[index]; it != nullptr; it = it->hashNext) {
            if ((*it)->getKey() == obj.getKey()) {
                return;  // 重复
            }
        }
        
        // 插入到桶链表头部
        IntrusiveHashNode& node = obj.*HookPtr;
        node.hashNext = buckets_[index];
        buckets_[index] = &node;
        ++size_;
    }
    
    // 查找
    T* find(const typename T::KeyType& key) {
        size_t index = hash_(key) % buckets_.size();
        for (auto it = buckets_[index]; it != nullptr; it = it->hashNext) {
            if (INTRUSIVE_CONTAINER_OF(it, T, HookPtr)->getKey() == key) {
                return INTRUSIVE_CONTAINER_OF(it, T, HookPtr);
            }
        }
        return nullptr;
    }
    
    // 删除
    bool erase(const typename T::KeyType& key) {
        size_t index = hash_(key) % buckets_.size();
        IntrusiveHashNode** prev = &buckets_[index];
        
        for (auto it = *prev; it != nullptr; prev = &it->hashNext, it = it->hashNext) {
            if (INTRUSIVE_CONTAINER_OF(it, T, HookPtr)->getKey() == key) {
                *prev = it->hashNext;
                it->hashNext = nullptr;
                --size_;
                return true;
            }
        }
        return false;
    }
    
    size_t size() const { return size_; }
    size_t bucket_count() const { return buckets_.size(); }
    
private:
    std::vector<IntrusiveHashNode*> buckets_;
    size_t size_ = 0;
    std::hash<typename T::KeyType> hash_;
};
```

### 2.3 基于池的实体管理（完整示例）

```cpp
#include <array>
#include <vector>

// 实体池——所有实体预分配在数组中
template <typename T, size_t MaxCount>
class EntityPool {
public:
    // 创建实体（从池中获取）
    T* create() {
        if (count_ >= MaxCount) return nullptr;
        T* entity = &storage_[count_++];
        new (entity) T();  // placement new（如果 T 非平凡）
        return entity;
    }
    
    // 回收实体（简化版——没有自由链表）
    // 生产代码应实现自由链表复用已销毁的槽位
    void destroy(T* entity) {
        entity->~T();
    }
    
    size_t active() const { return count_; }
    
    T* data() { return storage_.data(); }
    size_t capacity() const { return MaxCount; }
    
private:
    std::array<T, MaxCount> storage_;
    size_t count_ = 0;
};

// 使用侵入式链表管理激活/休眠实体
void entityManagementDemo() {
    constexpr size_t MAX_ENTITIES = 10000;
    
    EntityPool<Entity, MAX_ENTITIES> pool;
    IntrusiveList<Entity, &Entity::link> activeEntities;
    IntrusiveList<Entity, &Entity::link> sleepingEntities;
    
    // 创建所有实体——分配和初始化一次性完成
    for (size_t i = 0; i < 1000; ++i) {
        Entity* e = pool.create();
        e->id = static_cast<uint32_t>(i);
        e->x = static_cast<float>(i * 10);
        
        if (i % 3 == 0) {
            activeEntities.push_back(*e);
        } else {
            sleepingEntities.push_back(*e);
        }
    }
    
    std::cout << "Active: " << activeEntities.size() 
              << ", Sleeping: " << sleepingEntities.size() << "\n";
    
    // 激活一个实体——O(1) 移动，零分配！
    Entity& toActivate = sleepingEntities.front();
    sleepingEntities.erase(toActivate);      // 从休眠列表移除
    activeEntities.push_back(toActivate);    // 加入激活列表
    
    // 关键：整个过程没有 new/delete！
    // 实体始终在池中，指针始终有效
}
```

### 2.4 与 std::list 的性能对比

```cpp
#include <chrono>
#include <list>
#include <random>

struct StdEntity {
    uint32_t id;
    float x, y, z;
    
    explicit StdEntity(uint32_t i) : id(i), x(0), y(0), z(0) {}
};

struct IntrusiveEntity {
    uint32_t id;
    float x, y, z;
    IntrusiveDListNode link;
    
    explicit IntrusiveEntity(uint32_t i) : id(i), x(0), y(0), z(0) {}
};

void benchmarkIntrusiveVsStd() {
    constexpr size_t N = 100000;
    constexpr size_t ITERATIONS = 1000;
    
    // === std::list ===
    std::list<StdEntity> stdList;
    auto t1 = std::chrono::high_resolution_clock::now();
    
    for (size_t iter = 0; iter < ITERATIONS; ++iter) {
        for (size_t i = 0; i < N; ++i) {
            stdList.emplace_back(static_cast<uint32_t>(i));  // 堆分配！
        }
        stdList.clear();  // N 次 free！
    }
    
    auto t2 = std::chrono::high_resolution_clock::now();
    
    // === IntrusiveList ===
    // 对象预分配在 vector 中
    std::vector<IntrusiveEntity> entities;
    entities.reserve(N);
    for (size_t i = 0; i < N; ++i) {
        entities.emplace_back(static_cast<uint32_t>(i));
    }
    
    IntrusiveList<IntrusiveEntity, &IntrusiveEntity::link> intrList;
    auto t3 = std::chrono::high_resolution_clock::now();
    
    for (size_t iter = 0; iter < ITERATIONS; ++iter) {
        for (auto& e : entities) {
            intrList.push_back(e);  // 零分配！
        }
        intrList.clear();  // 只修改指针
    }
    
    auto t4 = std::chrono::high_resolution_clock::now();
    
    auto stdMs = std::chrono::duration_cast<std::chrono::milliseconds>(t2 - t1).count();
    auto intrMs = std::chrono::duration_cast<std::chrono::milliseconds>(t4 - t3).count();
    
    std::cout << "std::list:  " << stdMs  << " ms\n";
    std::cout << "Intrusive: " << intrMs << " ms\n";
    std::cout << "Speedup:   " << static_cast<double>(stdMs) / intrMs << "x\n";
    
    // 典型结果（无优化）：Intrusive 快 3-8 倍
    // 原因：零 malloc/free，更好的缓存局部性
}
```

---

## 3. 练习

### 必做练习 1: 实现侵入式双向链表实体的激活/休眠系统

1. 实现一个 `Entity` 结构体，包含 `activeLink` 和 `sleepLink` 两个侵入式 hook
2. 实现 `EntityManager`，使用 `IntrusiveList` 管理激活和休眠实体
3. 实现 O(1) 的激活/休眠切换（`wakeUp(entityID)` / `putToSleep(entityID)`）
4. 每帧遍历激活实体，调用 `update(deltaTime)`
5. 添加调试断言：同个实体不能同时在两个列表中

要求：所有实体预分配在 `std::vector` 中，整个系统零动态分配。

### 必做练习 2: 实测侵入式 vs STL 分配性能

1. 使用你的侵入式链表和 `std::list` 分别做 100,000 次 push_back + clear
2. 在三个编译优化级别下测试：-O0, -O2, -O3
3. 测量分配次数（使用全局计数器重载 `operator new`）
4. 分析结果差异的来源（分配器开销、缓存效应、分支预测）
5. 额外对比：验证侵入式链表遍历（顺序访问缓存中的连续元素）和 std::list 遍历（跳转访问堆上分散节点）的缓存性能差异

### 可选挑战: 实现 LRU 缓存

1. 使用侵入式双向链表 + 侵入式哈希表实现 LRU 缓存
2. 同一对象包含两个 hook：`listLink`（用于访问顺序）和 `hashLink`（用于哈希查找）
3. `get(key)`：哈希查找 → O(1) → 如果命中，将节点移到链表头部 → O(1)
4. `put(key, value)`：如果不存在，插入链表头部和哈希表；如果容量超限，删除链表尾部（O(1)）并从哈希表移除
5. 基准测试：对比你的 LRU 和基于 `std::list` + `std::unordered_map` 的实现

提示：参考 `containerOf` 宏从哈希 hook 反推对象指针。

---

## 4. 扩展阅读

- **Boost.Intrusive 文档** — https://www.boost.org/doc/libs/release/doc/html/intrusive.html — 侵入式容器设计的权威参考，包含所有高级特性说明
- **Game Engine Architecture (3rd ed.)** Ch. 5.2 — 引擎中的基础数据结构
- **EASTL intrusive_list** — https://github.com/electronicarts/EASTL — EA 的开源侵入式容器实现
- **Linux Kernel linked list** (`include/linux/list.h`) — 内核级的侵入式双向链表，`container_of` 宏的经典实现
- **Handmade Hero** Day 161-180 — Casey Muratori 关于游戏引擎数据结构的讨论
- **"Intrusive Linked Lists"** — Bjarne Stroustrup, "The C++ Programming Language" Sec. 7.2.1

---

## 常见陷阱

1. **对象销毁后仍在链表中——悬垂指针**：侵入式容器不管理生命周期。如果对象被销毁（离开作用域或显式 delete/free）但其 hook 仍在链表中，后续遍历会访问已释放内存。
   ```cpp
   // ✗ 危险！
   {
       Entity e{1, 0, 0, 0};
       list.push_back(e);
   }  // e 析构，但 list 中仍保留其地址！
   // list 遍历 → 访问已释放的 e → 未定义行为
   
   // ✓ 正确：确保生命周期覆盖
   // 方案 A：从池中分配，池的生命周期覆盖所有容器
   // 方案 B：析构前显式 erase
   // 方案 C：使用 auto_unlink（Boost.Intrusive 提供）
   ```

2. **重复插入同一个节点——循环链表**：如果节点已在链表中，再次 push_back 会创建循环。
   ```cpp
   Entity e;
   list.push_back(e);
   list.push_back(e);  // ✗ e 已在链表中！next/prev 被覆盖
   // 结果：链表损坏，遍历可能死循环
   
   // ✓ 正确：插入前检查是否已链接
   assert(!(e.*HookPtr).isLinked());
   ```

3. **`containerOf` 的空指针解引用**：使用 `offsetof` 是标准做法，但在 C++ 中对非标准布局类型使用 `offsetof` 是未定义行为（虽然几乎所有编译器都支持）。`container_of` 模板使用了 `reinterpret_cast` 对 null 指针做成员指针运算，这在严格标准下也是未定义行为，但实践中在所有主流编译器上工作。如果你的类型非常复杂（虚基类），应该谨慎验证。

4. **迭代器失效**：与 `std::list` 不同，侵入式链表在 erase 元素后，**指向其他元素的迭代器仍然有效**——因为节点地址不变。但务必注意：`erase(it++)` 模式仍然需要，因为 `erase` 后 `it` 指向的节点已从链表移除。
   ```cpp
   for (auto it = list.begin(); it != list.end(); ) {
       if (shouldRemove(*it)) {
           auto toRemove = it++;
           list.erase(*toRemove);  // ✗ 正确：erase 不影响其他迭代器
       } else {
           ++it;
       }
   }
   ```

5. **多线程访问**：侵入式容器本身不提供线程安全。在多个线程可能同时修改链表时，需要外部同步。与 `std::list` 相同，节点地址不变是优势——可以在持有锁时遍历，释放锁后仍可安全访问节点数据（前提是节点不会被其他线程回收）。
