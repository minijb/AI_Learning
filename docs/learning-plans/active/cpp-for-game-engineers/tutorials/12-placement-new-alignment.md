---
title: "Placement New 与对齐控制"
updated: 2026-06-05
---

# Placement New 与对齐控制

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 对象生命周期与内存布局（第 2 节）、自定义分配器入门（第 8 节）
> C++ 标准: C++03（placement new）、C++11（alignas/alignof）、C++17（对齐 new/delete、destroy_at）、C++20（construct_at）

---

## 1. 概念讲解

### 1.1 分离"分配"与"构造"

常规 `new` 表达式做了两件事：

```cpp
auto* p = new Widget(args);
// 等价于:
//   1. void* mem = operator new(sizeof(Widget));  ← 向堆请求内存
//   2. Widget* w = new (mem) Widget(args);         ← 在 mem 上构造对象
```

在游戏引擎中，我们经常需要**自己控制第 1 步（从哪分配内存），只让编译器做第 2 步（构造对象）**。这就是 Placement New 的用武之地。

### 1.2 Placement New 语法与语义

```cpp
#include <new>  // 提供 void* operator new(size_t, void*) noexcept

alignas(Widget) char storage[sizeof(Widget)];  // 准备"地皮"
Widget* w = ::new (storage) Widget(42);         // 在 storage 上构造 Widget
//            ^^^^^^^^^^^ placement-args
w->~Widget();  // 手动析构 —— placement new 没有对应的 delete！
```

Placement new **不分配内存**。标准库提供的 placement `operator new` 实现只有一行：

```cpp
void* operator new(std::size_t, void* ptr) noexcept { return ptr; }
```

这只是把传入的指针原样返回。编译器拿到这个指针后，将其作为 `this` 调用构造函数。

**关键分离**：

| 操作 | 分配内存 | 构造对象 | 析构对象 | 释放内存 |
|------|---------|---------|---------|---------|
| `new T` | ✓ | ✓ | — | — |
| `delete p` | — | — | ✓ | ✓ |
| `new (ptr) T` | ✗ | ✓ | — | — |
| `p->~T()` | — | — | ✓ | ✗ |
| `operator new(N)` | ✓ | ✗ | — | — |
| `operator delete(p)` | — | — | ✗ | ✓ |

### 1.3 为什么需要对齐？

CPU 从内存读取数据不是逐字节的，而是按"字"（word，4/8/16/32/64 字节）的。当一个 N 字节的数据跨越了两个字的边界，CPU 需要两次读取再拼接——这在某些架构（ARM、SPARC）上会直接触发 **总线错误（SIGBUS）**，在 x86 上则产生显著的性能惩罚。

```
对齐的含义：
  alignof(int) == 4  → int 必须放在地址 0x...0, 0x...4, 0x...8, 0x...C 上

未对齐访问（int 在地址 0x1001）：
  第一次读取: [0x1000, 0x1004) — 取后 3 字节
  第二次读取: [0x1004, 0x1008) — 取前 1 字节
  拼接         → 两次内存访问完成一次读取
```

游戏引擎中的对齐需求比普通应用更高：

| 对齐要求 | 使用场景 |
|---------|---------|
| 16 字节 | SSE/NEON SIMD（`__m128`） |
| 32 字节 | AVX SIMD（`__m256`） |
| 64 字节 | AVX-512（`__m512`）、GPU DMA 缓冲区 |
| 64 字节 | 缓存行对齐（避免 false sharing） |
| 256 字节 | GPU 常量缓冲区对齐（DirectX） |

### 1.4 alignas 与 alignof（C++11）

```cpp
// alignof — 查询类型的对齐要求（编译期）
static_assert(alignof(int) == 4);
static_assert(alignof(double) == 8);

// alignas — 指定对齐（只能增大，不能减小）
struct alignas(16) Vec4 { float x, y, z, w; };
static_assert(alignof(Vec4) == 16);

// 变量对齐
alignas(64) char cache_line[64];  // 确保在缓存行边界

// 类型对齐
struct alignas(32) AVXVector {
    float data[8];  // 自动满足 32 字节对齐
};
```

`alignas` 只能**增大**对齐要求。如果你写 `alignas(2) int x;`，编译器会忽略（或警告），因为 `alignof(int)` 已经是 4。

### 1.5 std::construct_at 与 std::destroy_at（C++17/20）

C++17 引入了 `std::destroy_at`，C++20 引入了 `std::construct_at`，它们是对 placement new 和手动析构的标准化包装：

```cpp
#include <memory>

// C++20: 在指定地址构造对象
template<class T, class... Args>
constexpr T* construct_at(T* p, Args&&... args);
// 等价于: ::new (const_cast<void*>(static_cast<const volatile void*>(p))) T(forward<Args>(args)...)

// C++17: 析构对象
template<class T>
constexpr void destroy_at(T* p);
// 等价于: p->~T()
```

相比裸 placement new，`construct_at` 的优势：
1. **语义清晰**：明确表达"构造"意图
2. **constexpr**（C++20）：可在编译期使用
3. **SFINAE 友好**：参数类型不匹配时是替换失败而非硬错误
4. **返回值**：返回 `T*` 方便链式调用

### 1.6 std::aligned_alloc 与对齐 operator new（C++17）

C++17 之前，从堆上分配对齐内存的唯一可移植方式是"多分配一点然后手动对齐"。C++17 引入：

```cpp
// C 风格（<cstdlib>）
void* std::aligned_alloc(size_t alignment, size_t size);
// 要求：alignment 是 2 的幂，size 是 alignment 的倍数
// 释放用 free()

// C++ 风格（C++17 — 编译器自动选择正确重载）
struct alignas(32) BigType { char d[128]; };
auto* p = new BigType;  // 编译器检测到 alignof(BigType) > __STDCPP_DEFAULT_NEW_ALIGNMENT__
                        // 自动调用 operator new(sizeof(BigType), align_val_t{32})

// 手动指定对齐
void* operator new(size_t count, std::align_val_t al);    // C++17
void operator delete(void* ptr, std::align_val_t al);     // C++17
```

> **引擎注意**：如果你自定义了全局 `operator new`，必须同时自定义对齐版本，否则分配 over-aligned 类型时会绕过你的分配器，直接走标准库！

### 1.7 std::launder — 编译器优化屏障（C++17）

当你在同一块内存上析构再构造对象（如对象池复用），编译器可能基于旧对象的类型做假设，导致未定义行为：

```cpp
struct A { int x; };
struct B { int x; };

alignas(A) alignas(B) char pool[std::max(sizeof(A), sizeof(B))];
A* a = new (pool) A{42};
int v1 = a->x;     // OK
a->~A();
B* b = new (pool) B{100};

int v2 = a->x;     // ❌ UB: a 指向的内存上不再是 A 对象
int v3 = b->x;     // OK
int v4 = std::launder(a)->x;  // ❌ a 的类型仍是 A*，launder 不改变类型
B* b2 = std::launder(reinterpret_cast<B*>(pool));  // ✅ 正确获取 B 对象
```

`std::launder` 告诉编译器"忽略关于这个指针的别名假设，重新从内存中读"。在引擎对象池中，当槽位被不同类型复用、且通过旧指针访问时，可能需要 `std::launder`。

---

## 2. 代码示例

### 2.1 自定义分配器 + Placement New

```cpp
// placement_new_allocator.cpp — 完整的 Placement New 驱动分配系统
// 编译: g++ -std=c++20 -O2 placement_new_allocator.cpp -o pn_demo

#include <cstdlib>
#include <cstddef>
#include <new>
#include <memory>
#include <cassert>
#include <iostream>
#include <vector>

// ============================================================
// 1. 通用对齐感知分配器
// ============================================================
class AlignedAllocator {
public:
    explicit AlignedAllocator(size_t size_bytes)
        : m_buffer(static_cast<char*>(std::aligned_alloc(64, size_bytes)))
        , m_size(size_bytes)
        , m_offset(0)
    {
        assert(m_buffer && "aligned_alloc failed");
    }

    ~AlignedAllocator() { std::free(m_buffer); }

    AlignedAllocator(const AlignedAllocator&) = delete;
    AlignedAllocator& operator=(const AlignedAllocator&) = delete;

    // 对齐分配 — 返回满足 alignment 要求的指针
    void* allocate(size_t size, size_t alignment) {
        assert((alignment & (alignment - 1)) == 0 && "alignment must be power of 2");

        void* current = m_buffer + m_offset;
        size_t space = m_size - m_offset;

        void* aligned = current;
        if (!std::align(alignment, size, aligned, space)) {
            return nullptr;  // 空间不足
        }

        m_offset = static_cast<char*>(aligned) + size - m_buffer;
        return aligned;
    }

    void reset() { m_offset = 0; }
    size_t used()     const { return m_offset; }
    size_t capacity() const { return m_size; }

private:
    char*  m_buffer;
    size_t m_size;
    size_t m_offset;
};

// ============================================================
// 2. 固定大小对象池 — 使用 Placement New
// ============================================================
template <typename T, size_t PoolSize = 1024>
class ObjectPool {
    static_assert(alignof(T) <= 64, "Pool alignment capped at 64");

    struct alignas(64) Slot {
        alignas(T) char data[sizeof(T)];
        bool occupied = false;
    };

    Slot m_slots[PoolSize];
    size_t m_active = 0;

public:
    // 从池中分配一个 T，在槽位上 placement new 构造
    template <typename... Args>
    T* create(Args&&... args) {
        for (size_t i = 0; i < PoolSize; ++i) {
            if (!m_slots[i].occupied) {
                m_slots[i].occupied = true;
                ++m_active;
                return std::construct_at(
                    reinterpret_cast<T*>(m_slots[i].data),
                    std::forward<Args>(args)...
                );
            }
        }
        return nullptr;  // 池满
    }

    // 销毁对象并归还槽位
    void destroy(T* ptr) {
        for (size_t i = 0; i < PoolSize; ++i) {
            if (reinterpret_cast<T*>(m_slots[i].data) == ptr) {
                std::destroy_at(ptr);       // C++17 — 调用析构
                m_slots[i].occupied = false;
                --m_active;
                return;
            }
        }
    }

    // 批量销毁（逆序析构）
    void destroy_all() {
        for (size_t i = PoolSize; i > 0; --i) {
            if (m_slots[i - 1].occupied) {
                std::destroy_at(reinterpret_cast<T*>(m_slots[i - 1].data));
                m_slots[i - 1].occupied = false;
            }
        }
        m_active = 0;
    }

    size_t size()     const { return m_active; }
    size_t capacity() const { return PoolSize; }
};

// ============================================================
// 3. 缓存行对齐的 SIMD 向量类
// ============================================================
#include <x86intrin.h>  // SSE/AVX intrinsics (x86 only; ARM use arm_neon.h)

// 16 字节对齐 — SSE 要求
struct alignas(16) Vec4 {
    float x, y, z, w;

    Vec4() : x(0), y(0), z(0), w(0) {}
    Vec4(float a, float b, float c, float d) : x(a), y(b), z(c), w(d) {}

    // 使用 SIMD 加速加法
    Vec4 operator+(const Vec4& rhs) const {
        __m128 a = _mm_load_ps(&x);         // 要求 16 字节对齐！
        __m128 b = _mm_load_ps(&rhs.x);     // 未对齐会触发 GP fault（或性能严重下降）
        __m128 c = _mm_add_ps(a, b);

        Vec4 result;
        _mm_store_ps(&result.x, c);          // 要求 16 字节对齐！
        return result;
    }

    float dot(const Vec4& rhs) const {
        __m128 a = _mm_load_ps(&x);
        __m128 b = _mm_load_ps(&rhs.x);
        __m128 mul = _mm_mul_ps(a, b);

        // 水平求和: [m0,m1,m2,m3] → m0+m1+m2+m3
        __m128 shuf = _mm_shuffle_ps(mul, mul, _MM_SHUFFLE(2, 3, 0, 1));
        __m128 sums = _mm_add_ps(mul, shuf);
        shuf = _mm_movehl_ps(shuf, sums);
        sums = _mm_add_ss(sums, shuf);
        return _mm_cvtss_f32(sums);
    }

    // 验证对齐
    static void verify_alignment() {
        static_assert(alignof(Vec4) == 16, "Vec4 must be 16-byte aligned for SSE");
        std::cout << "Vec4 alignment: " << alignof(Vec4) << " bytes ✓\n";
    }
};

// ============================================================
// 4. 对齐 vs 未对齐 SIMD 加载的性能对比
// ============================================================
#include <chrono>

// 已对齐的数组
void benchmark_aligned(size_t iterations) {
    alignas(16) float src[4] = {1.0f, 2.0f, 3.0f, 4.0f};
    alignas(16) float dst[4];

    auto start = std::chrono::high_resolution_clock::now();
    for (size_t i = 0; i < iterations; ++i) {
        __m128 v = _mm_load_ps(src);       // 对齐加载 — 1 条指令
        v = _mm_mul_ps(v, v);
        _mm_store_ps(dst, v);               // 对齐存储
    }
    auto end = std::chrono::high_resolution_clock::now();
    auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
    std::cout << "对齐加载+存储:   " << ns / (double)iterations << " ns/iter\n";

    // 防止优化消除
    volatile float sink = dst[0];
    (void)sink;
}

// 未对齐的数组（模拟从网络/磁盘读取的打包数据）
void benchmark_unaligned(size_t iterations) {
    alignas(16) float src[5];  // 多分配 1 个元素以便偏移
    alignas(16) float dst[4];

    float* unaligned_src = reinterpret_cast<float*>(
        reinterpret_cast<char*>(src) + 1);  // 故意偏移 1 字节 → 未对齐

    for (int i = 0; i < 4; ++i) unaligned_src[i] = static_cast<float>(i + 1);

    auto start = std::chrono::high_resolution_clock::now();
    for (size_t i = 0; i < iterations; ++i) {
        __m128 v = _mm_loadu_ps(unaligned_src); // 未对齐加载 — 可能 2 条 μop
        v = _mm_mul_ps(v, v);
        _mm_store_ps(dst, v);                    // 对齐存储
    }
    auto end = std::chrono::high_resolution_clock::now();
    auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
    std::cout << "未对齐加载:       " << ns / (double)iterations << " ns/iter\n";
}

// ============================================================
// 5. 引擎 SOA 粒子数组（对齐保证）
// ============================================================
template <size_t MaxParticles>
class ParticleSystem {
    // 结构体数组（SoA）布局 — 每字段独立、连续、对齐
    alignas(32) float m_pos_x[MaxParticles];
    alignas(32) float m_pos_y[MaxParticles];
    alignas(32) float m_pos_z[MaxParticles];
    alignas(32) float m_vel_x[MaxParticles];
    alignas(32) float m_vel_y[MaxParticles];
    alignas(32) float m_vel_z[MaxParticles];
    alignas(32) float m_lifetime[MaxParticles];
    size_t m_count = 0;

public:
    // 生成粒子 — placement new 构造（对于 float 数组不需要，仅作示范）
    void spawn(float px, float py, float pz, float vx, float vy, float vz, float life) {
        if (m_count >= MaxParticles) return;
        size_t i = m_count++;

        // 使用 placement new 在预对齐内存中构造（对 float 是多余的，但对复杂类型必须）
        std::construct_at(&m_pos_x[i], px);
        std::construct_at(&m_pos_y[i], py);
        std::construct_at(&m_pos_z[i], pz);
        std::construct_at(&m_vel_x[i], vx);
        std::construct_at(&m_vel_y[i], vy);
        std::construct_at(&m_vel_z[i], vz);
        std::construct_at(&m_lifetime[i], life);
    }

    // 使用 SSE 批量更新 4 个粒子（必须 16 字节对齐）
    void update_batch_4(size_t start_idx, float dt) {
        assert(start_idx % 4 == 0 && "Batch start must be 4-aligned");

        // 加载 4 个粒子的 x 坐标（连续内存 → 一条 MOVAPS）
        __m128 px = _mm_load_ps(&m_pos_x[start_idx]);
        __m128 vx = _mm_load_ps(&m_vel_x[start_idx]);
        __m128 py = _mm_load_ps(&m_pos_y[start_idx]);
        __m128 vy = _mm_load_ps(&m_vel_y[start_idx]);

        __m128 dt4 = _mm_set1_ps(dt);
        px = _mm_add_ps(px, _mm_mul_ps(vx, dt4));  // pos += vel * dt
        py = _mm_add_ps(py, _mm_mul_ps(vy, dt4));

        _mm_store_ps(&m_pos_x[start_idx], px);
        _mm_store_ps(&m_pos_y[start_idx], py);
    }

    size_t count() const { return m_count; }

    // 验证所有数组的对齐
    static void check_alignment() {
        std::cout << "ParticleSystem 对齐检查:\n";
        std::cout << "  pos_x:  " << alignof(decltype(m_pos_x)) << " bytes\n";
        std::cout << "  alignas 要求: 32\n";
    }
};
```

### 2.2 Placement New 数组的"C++ Cookie"问题

```cpp
// placement_array_demo.cpp — placement new[] 的隐藏陷阱

#include <new>
#include <iostream>
#include <cstring>

struct Widget {
    int id;
    Widget(int i = 0) : id(i) {
        std::cout << "  Widget(" << id << ") @" << this << "\n";
    }
    ~Widget() {
        std::cout << "  ~Widget(" << id << ") @" << this << "\n";
    }
};

void placement_array_demo() {
    std::cout << "===== Placement New 数组陷阱 =====\n\n";

    alignas(Widget) char buffer[sizeof(Widget) * 8];

    // ❌ 错误 — placement new[] 可能在前 8 字节存储元素计数（"cookie"）
    // Widget* arr = ::new (buffer) Widget[5];
    // 如果编译器存储了 cookie，arr 可能指向 buffer + 8 而非 buffer！
    // delete[] arr 时编译器会去 arr-8 处找元素个数 → 如果 buffer 只有 8 个对象的空间
    // 而 cookie 覆盖了 Widget[0]，数据就损坏了。

    // ✅ 正确 — 逐个 placement new
    Widget* widgets[5];
    for (int i = 0; i < 5; ++i) {
        widgets[i] = ::new (reinterpret_cast<Widget*>(buffer) + i) Widget(i * 10);
    }

    // 按构造的逆序析构
    for (int i = 4; i >= 0; --i) {
        widgets[i]->~Widget();
    }

    std::cout << "\n规则：永远不要用 placement new[] 分配数组。\n";
    std::cout << "改为逐个 placement new + 循环。\n";
}
```

### 2.3 完整引擎对象池（含 std::launder）

```cpp
// engine_object_pool.cpp — 生产级对象池

template <typename T, size_t N = 256>
class EnginePool {
    // 槽位类型 — 确保对齐
    struct Slot {
        alignas(T) unsigned char data[sizeof(T)];
        uint32_t generation = 0;  // ABA 问题防护
        bool occupied = false;
    };

    Slot m_slots[N];
    size_t m_free_list[N];  // 简单空闲链表（索引数组）
    size_t m_free_count = N;

public:
    EnginePool() {
        for (size_t i = 0; i < N; ++i) {
            m_free_list[i] = N - 1 - i;
        }
    }

    ~EnginePool() {
        // 销毁所有活跃对象
        for (auto& slot : m_slots) {
            if (slot.occupied) {
                std::destroy_at(reinterpret_cast<T*>(slot.data));
                slot.occupied = false;
            }
        }
    }

    // 非复制
    EnginePool(const EnginePool&) = delete;
    EnginePool& operator=(const EnginePool&) = delete;

    template <typename... Args>
    T* create(Args&&... args) {
        if (m_free_count == 0) return nullptr;

        size_t idx = m_free_list[--m_free_count];
        Slot& slot = m_slots[idx];

        T* obj = std::construct_at(
            reinterpret_cast<T*>(slot.data),
            std::forward<Args>(args)...
        );
        slot.occupied = true;
        slot.generation++;
        return obj;
    }

    void destroy(T* ptr) {
        for (size_t i = 0; i < N; ++i) {
            // 使用 std::launder 确保编译器不对指针做别名假设
            T* candidate = std::launder(reinterpret_cast<T*>(m_slots[i].data));
            if (candidate == ptr && m_slots[i].occupied) {
                std::destroy_at(ptr);
                m_slots[i].occupied = false;
                m_free_list[m_free_count++] = i;
                return;
            }
        }
    }

    size_t size()     const { return N - m_free_count; }
    size_t capacity() const { return N; }
};
```

### 2.4 主演示函数

```cpp
int main() {
    std::cout << "========== Placement New 与对齐控制 ==========\n\n";

    // 1. Vec4 对齐验证
    Vec4::verify_alignment();
    Vec4 a(1, 2, 3, 4), b(5, 6, 7, 8);
    Vec4 c = a + b;
    std::cout << "a + b = (" << c.x << ", " << c.y << ", " << c.z << ", " << c.w << ")\n";
    std::cout << "a · b = " << a.dot(b) << "\n\n";

    // 2. SIMD 对齐 vs 未对齐性能
    std::cout << "========== SIMD 对齐 vs 未对齐 ==========\n";
    benchmark_aligned(10'000'000);
    benchmark_unaligned(10'000'000);

    // 3. Placement new 数组陷阱
    std::cout << "\n";
    placement_array_demo();

    // 4. 对象池测试
    std::cout << "\n========== 对象池测试 ==========\n";
    ObjectPool<Widget, 4> pool;
    Widget* w1 = pool.create(1);
    Widget* w2 = pool.create(2);
    Widget* w3 = pool.create(3);
    std::cout << "池中对象: " << pool.size() << "/" << pool.capacity() << "\n";
    pool.destroy(w2);
    std::cout << "销毁 w2 后: " << pool.size() << "/" << pool.capacity() << "\n";
    Widget* w4 = pool.create(4);  // 复用 w2 的槽位
    std::cout << "创建 w4 后: " << pool.size() << "/" << pool.capacity() << "\n";
    pool.destroy_all();

    // 5. 对齐感知分配器
    std::cout << "\n========== 对齐感知分配器 ==========\n";
    AlignedAllocator alloc(4096);
    void* p1 = alloc.allocate(100, 16);
    void* p2 = alloc.allocate(32, 64);  // 缓存行对齐
    std::cout << "p1 = " << p1 << " (alignment: " << (reinterpret_cast<uintptr_t>(p1) % 16 == 0 ? "OK" : "FAIL") << ")\n";
    std::cout << "p2 = " << p2 << " (alignment: " << (reinterpret_cast<uintptr_t>(p2) % 64 == 0 ? "OK" : "FAIL") << ")\n";
    std::cout << "used: " << alloc.used() << "/" << alloc.capacity() << "\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1（必做）：构建固定大小对象池

用 placement new 实现一个完整的固定大小对象池 `FixedPool<T, N>`：

1. 池使用 `alignas(T) char[N * sizeof(T)]` 作为底层存储
2. `create(Args&&...)` 从池中分配槽位，用 `std::construct_at` 构造对象，返回 `T*`
3. `destroy(T*)` 调用 `std::destroy_at` 并归还槽位
4. 支持 `create()` 与 `destroy()` 的任意顺序交错调用（复用空闲槽位）
5. 构造函数不抛出异常时无内存开销（仅 sizeof 缓冲 + 位图）
6. 编写测试：创建 → 销毁 → 复用 — 验证对象被正确构造和析构

### 练习 2（必做）：实现 SIMD 安全对齐的数学向量库

1. 定义 `struct alignas(16) Vec4 { float x,y,z,w; }`
2. 使用 SSE intrinsics（`_mm_load_ps` / `_mm_store_ps` / `_mm_add_ps` / `_mm_mul_ps` / `_mm_dp_ps`）实现加法、点积、叉积
3. 编写一个函数 `void transform_batch(Vec4* positions, const float* matrix, size_t count)`，使用 SSE 批量变换顶点
4. 验证：如果 `positions` 不是 16 字节对齐，程序会有什么行为？（x86 上性能下降，ARM 上崩溃）
5. 添加 `static_assert(alignof(Vec4) == 16)` 防止误用

### 练习 3（选做·挑战）：实现对齐感知通用分配器

1. 实现 `GeneralAlignedAllocator`，支持从堆上分配任意对齐要求的内存块
2. 使用 C++17 的 `operator new(size_t, align_val_t)` 进行对齐分配
3. 实现一个"对齐归还"机制：记录每个分配的基础地址和对齐值，确保 `deallocate` 正确释放
4. 编写碎片化测量：分配 1000 个不同对齐要求（8/16/32/64）的块，测量内部碎片率
5. 对比你的分配器和原始 `malloc` 的内部碎片率

---

## 4. 扩展阅读

- **cppreference: Placement new**：[new expression](https://en.cppreference.com/w/cpp/language/new)
- **cppreference: alignas / alignof**：[alignas specifier](https://en.cppreference.com/w/cpp/language/alignas)
- **`std::construct_at`**（C++20）：[cppreference](https://en.cppreference.com/w/cpp/memory/construct_at)
- **Intel Intrinsics Guide**：[`_mm_load_ps` 等 SSE 指令参考](https://www.intel.com/content/www/us/en/docs/intrinsics-guide/index.html)
- **Agner Fog's optimization manuals**：第 5 章 "Data Alignment" 有详尽的对齐性能数据
- **本计划关联深探**：`docs/deep-dives/placement-new-aligned-allocation.md` — 7 层深度分析

---

## 常见陷阱

### 陷阱 1：忘记调用析构函数导致资源泄漏

```cpp
// ❌ 错误 — std::string 持有堆内存，不析构会泄漏
alignas(std::string) char buf[sizeof(std::string)];
auto* s = ::new (buf) std::string("this is a long string that allocates on heap");
// ... 使用 s ...
// 忘记 s->~basic_string()  → char* 内部缓冲泄漏！

// ✅ 正确
std::destroy_at(s);  // 或 s->~basic_string();
```

### 陷阱 2：在同一地址多次 placement new 而不先析构

```cpp
alignas(Widget) char buf[sizeof(Widget)];
auto* w1 = ::new (buf) Widget(1);
// ❌ 错误 — 在 w1 仍存活时再次构造，未定义行为
auto* w2 = ::new (buf) Widget(2);  // UB！

// ✅ 正确 — 先析构再重建
w1->~Widget();
auto* w2 = ::new (buf) Widget(2);

// 例外：implicit-lifetime 类型（int, float, char[] 等）可以跳过析构
auto* p1 = ::new (buf) int(42);
// 对于 int，下面的操作是安全的（C++20 起）
auto* p2 = ::new (buf) int(100);  // OK，int 是 implicit-lifetime 类型
```

### 陷阱 3：未对齐内存上 placement new 导致崩溃

```cpp
// ❌ UB — Widget 需要 8 字节对齐，但 buf+1 可能是奇数地址
char buf[sizeof(Widget) + 8];
auto* w = ::new (buf + 1) Widget(42);  // ARM 上 SIGBUS！

// ✅ 1. 使用 alignas 强制对齐
alignas(Widget) char buf2[sizeof(Widget)];
auto* w2 = ::new (buf2) Widget(42);  // 安全

// ✅ 2. 使用 std::align 动态计算对齐地址
char raw_buf[sizeof(Widget) + alignof(Widget)];
void* p = raw_buf;
size_t space = sizeof(raw_buf);
std::align(alignof(Widget), sizeof(Widget), p, space);
auto* w3 = ::new (p) Widget(42);  // 安全
```

### 陷阱 4：对齐 operator new 被绕过

```cpp
// 假设你自定义了全局 operator new
void* operator new(size_t size) {
    return MyCustomAlloc(size);  // 你的分配器
}

struct alignas(32) Big { char data[128]; };

// ❌ 当你分配 over-aligned 类型时，编译器调用的是标准库的
//    operator new(sizeof(Big), align_val_t{32})
//    完全绕过了你的 MyCustomAlloc！
auto* b = new Big;

// ✅ 必须同时自定义对齐版本
void* operator new(size_t size, std::align_val_t al) {
    return MyCustomAllocAligned(size, static_cast<size_t>(al));
}
```

### 陷阱 5：placement new[] 的隐藏 cookie

```cpp
// ❌ 不可移植！编译器可能在前 8 字节存储元素计数
alignas(Widget) char buf[sizeof(Widget) * 10];
auto* arr = ::new (buf) Widget[5];

// 在 MSVC/Itanium ABI 下：
//   arr 可能等于 buf + 8（跳过了 cookie）
//   delete[] arr 会去 arr[-1] 处找元素个数
//   如果 buf 恰好只有 5*sizeof(Widget) 空间，cookie 就覆盖了 Widget[0]！

// ✅ 永远用循环 + 单个 placement new
for (int i = 0; i < 5; ++i) {
    ::new (reinterpret_cast<Widget*>(buf) + i) Widget(i);
}
```
