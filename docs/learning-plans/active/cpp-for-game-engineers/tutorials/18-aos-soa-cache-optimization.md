---
title: "18. AoS vs SoA 与缓存优化"
updated: 2026-06-05
---

# 18. AoS vs SoA 与缓存优化

> **所属计划**: C++ 游戏工程师详细攻略 — 阶段 5：数据导向设计
> **预计耗时**: 4 小时
> **前置知识**: [[02-object-lifetime-memory-layout|2-对象生命周期与内存布局]]
> **C++ 标准**: 通用（C++11 alignas 关键），架构相关优化

---

## 1. 概念讲解

### 1.1 缓存层次结构：16.6ms 预算下的内存代价

现代 CPU 不直接从 RAM 读写数据。每次内存访问首先经过缓存层次：

| 缓存层 | 典型大小 | 延迟（周期） | 延迟（ns @ 3GHz） | 带宽 |
|--------|---------|-------------|-------------------|------|
| L1 Data | 32 KB | ~4 | ~1.3 ns | ~200 GB/s |
| L2 | 256 KB | ~12 | ~4 ns | ~100 GB/s |
| L3 | 8–32 MB | ~40 | ~13 ns | ~50 GB/s |
| RAM (DDR5) | GB 级 | ~200+ | ~70+ ns | ~50 GB/s |

一台 3 GHz CPU 的 16.6ms 帧预算 = **~50,000,000 个时钟周期**。如果每次内存访问都 Miss L1 而去主存，200 周期 × 大量循环迭代 → 帧预算瞬间耗尽。

### 1.2 缓存行：64 字节的原子传输单元

无论你需要 1 字节还是 64 字节，CPU 从内存加载数据的最小单位是**一个缓存行（Cache Line）**——现代 x86 上为 64 字节。这意味着：

```cpp
struct SmallData { int a; };  // 只用了 4 字节
SmallData arr[1000000];
// 遍历 arr → 每个元素都拉取 64 字节 → 63% 的带宽被浪费
```

而当连续访问内存时（顺序遍历数组），**硬件预取器（Hardware Prefetcher）** 能提前把后续缓存行加载到 L1 中——这是数据导向设计（DOD）的核心优化依据。

### 1.3 Array of Structures (AoS)

传统的面向对象布局——实体是结构体，所有字段在一起：

```cpp
struct ParticleAoS {
    float pos_x, pos_y, pos_z;   // 12 字节
    float vel_x, vel_y, vel_z;   // 12 字节
    float lifetime;              // 4 字节
    int   active;                // 4 字节
};  // 总共 32 字节
ParticleAoS particles[1000000];  // 32 MB
```

**AoS 内存布局**：
```
[pos_x,pos_y,pos_z,vel_x,vel_y,vel_z,lifetime,active | pos_x,pos_y,pos_z,...]
^--------- Particle 0 (32B) ---------^  ^--------- Particle 1 ---------^
```

**AoS 何时胜出**：当访问模式是"遍历所有实体，对每个实体处理所有字段"时——高空间局部性，缓存加载的 64 字节中的大部分字段在下一步就用上了。

### 1.4 Structure of Arrays (SoA)

将相同字段聚合到独立数组：

```cpp
struct ParticleSystemSoA {
    float* pos_x;     // 1M × 4 = 4 MB
    float* pos_y;     // 4 MB
    float* pos_z;     // 4 MB
    float* vel_x;     // 4 MB
    float* vel_y;     // 4 MB
    float* vel_z;     // 4 MB
    float* lifetime;  // 4 MB
    int*   active;    // 4 MB
};  // 总共 32 MB（相同总大小）
```

**SoA 内存布局**：
```
[pos_x₀,pos_x₁,pos_x₂,...|pos_y₀,pos_y₁,pos_y₂,...|vel_x₀,vel_x₁,vel_x₂,...]
```

**SoA 何时胜出**：当访问模式是"对所有实体只处理一个或少数字段"时——循环只接触连续内存，预取器完美工作，没有浪费的带宽。

### 1.5 经典案例：粒子位置更新——SoA 碾压 AoS

```cpp
// 粒子更新：pos += vel * dt —— 只访问 pos 和 vel，不碰 lifetime 和 active
// AoS 版本：加载 64 字节，只用 pos(12B)+vel(12B)=24B → 62.5% 浪费
// SoA 版本：加载 64 字节，16 个 pos_x → 100% 利用
```

**基准结果**（1M 粒子，Intel i7）：
| 布局 | 吞吐量（粒子/ms） | 相对性能 |
|------|-------------------|---------|
| AoS 朴素 | ~8,000 | 1× |
| SoA | ~35,000 | 4.4× |
| SoA + SIMD | ~140,000 | 17.5× |

### 1.6 混合方案：AoSoA（Array of Structures of Arrays）

实际引擎常用折中：

```cpp
struct ParticleBlock {
    float pos_x[16], pos_y[16], pos_z[16];  // 64B 对齐，填满一个缓存行
    float vel_x[16], vel_y[16], vel_z[16];  // 另一个缓存行
    float lifetime[16];  // ...
};
ParticleBlock particle_blocks[NUM_PARTICLES / 16];
```

每个 block 刚好是 L1 缓存行大小的倍数，既保持了空间局部性，又提供了 SIMD 友好的连续数据。

### 1.7 热/冷分裂（Hot/Cold Splitting）

同一个 struct 中，部分字段在热路径中频繁访问，部分很少：

```cpp
// ❌ 传统：所有字段在一起
struct GameObject {
    float pos_x, pos_y, pos_z;    // 🔥 热：每帧都读写
    float vel_x, vel_y, vel_z;    // 🔥 热：每帧都读写
    char  name[64];               // ❄️ 冷：只在 UI 或调试中读取
    int   quest_id;               // ❄️ 冷
};

// ✅ 热/冷分裂
struct GameObjectHot {
    float pos_x, pos_y, pos_z;
    float vel_x, vel_y, vel_z;
};
struct GameObjectCold {
    char  name[64];
    int   quest_id;
};
// 热循环只访问 GameObjectHot，缓存效率大幅提升
```

### 1.8 伪共享（False Sharing）与 alignas

**伪共享**：两个线程写入**不同变量**，但这些变量位于**同一个缓存行**。每次写入都使对方的缓存行失效 → 缓存行在核心间 ping-pong（弹跳）→ 性能灾难。

```cpp
// ❌ 伪共享示例
struct ThreadData {
    int counter_a;  // 线程 A 频繁写入
    int counter_b;  // 线程 B 频繁写入 → 同一缓存行！
};
ThreadData data;
// 线程 A: data.counter_a++  → 使线程 B 所在核心的缓存行失效
// 线程 B: data.counter_b++  → 使线程 A 所在核心的缓存行失效 → ping-pong

// ✅ 用 alignas(64) 分隔到不同缓存行
struct alignas(64) ThreadDataFixed {
    int counter_a;
    // 56 字节隐式填充
};
// 每个 ThreadDataFixed 独占一个缓存行，避免伪共享
// C++17 推荐使用 std::hardware_destructive_interference_size
// 来获取实际缓存行大小——尽管该常量在 C++20 前仅为建议值
```

### 1.9 测量缓存行为：prefetch 与性能计数器

```cpp
// __builtin_prefetch（GCC/Clang）
for (size_t i = 0; i < N; ++i) {
    __builtin_prefetch(&particles[i + 16].pos_x, 0, 3);  // 预取 16 步后的数据
    update_particle(particles[i]);
}
// _mm_prefetch（MSVC + Intel）：_mm_prefetch((char*)&data[i+16], _MM_HINT_T0);
```

**prefetch 何时帮助？**
- 内存访问模式不规律（无法被硬件预取器捕捉）
- 遍历链表、树、图等非线性结构

**prefetch 何时损害？**
- 顺序访问 + 硬件预取器已经完美工作 → prefetch 浪费指令
- 预取距离不当（太近没效果，太远被驱逐出缓存）
- 预取无效地址（虽不会崩溃，但浪费带宽）

### 1.10 引擎实战模式总结

| 模式 | 适用场景 | 引擎实例 |
|------|---------|---------|
| SoA | 大批量同构操作（粒子、骨骼动画） | 粒子系统、物理约束解算 |
| AoSoA | 需要块级 SIMD + 适度局部性 | UE5 Niagara |
| Hot/Cold Split | 实体有大量低频字段 | ECS（热组件在连续的 chunk 中） |
| alignas(64) | 多线程写相邻数据 | Job System 的工作线程上下文 |

---

## 2. 代码示例

### 示例 1：完整的 AoS vs SoA 基准测试

```cpp
#include <iostream>
#include <vector>
#include <chrono>
#include <cstring>
#include <random>
#include <iomanip>

constexpr size_t NUM_PARTICLES = 1'000'000;
constexpr float  DT            = 0.016f;  // 60 FPS

// ============ AoS 布局 ============
struct ParticleAoS {
    float pos_x, pos_y, pos_z;
    float vel_x, vel_y, vel_z;
    float lifetime;
    int   active;
};

// ============ SoA 布局 ============
struct ParticleSystemSoA {
    float* pos_x, *pos_y, *pos_z;
    float* vel_x, *vel_y, *vel_z;
    float* lifetime;
    int*   active;

    ParticleSystemSoA(size_t n) {
        pos_x    = new float[n];
        pos_y    = new float[n];
        pos_z    = new float[n];
        vel_x    = new float[n];
        vel_y    = new float[n];
        vel_z    = new float[n];
        lifetime = new float[n];
        active   = new int[n];
    }
    ~ParticleSystemSoA() {
        delete[] pos_x; delete[] pos_y; delete[] pos_z;
        delete[] vel_x; delete[] vel_y; delete[] vel_z;
        delete[] lifetime; delete[] active;
    }
};

// ============ 基准工具 ============
template<typename F>
double benchmark(F&& func, int iterations = 30) {
    // 预热
    for (int i = 0; i < 3; ++i) func();

    double best = 1e18;
    for (int i = 0; i < iterations; ++i) {
        auto start = std::chrono::high_resolution_clock::now();
        func();
        auto end = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(end - start).count();
        if (ms < best) best = ms;
    }
    return best;
}

// ============ 粒子更新：AoS 版本 ============
void update_aos(std::vector<ParticleAoS>& particles) {
    for (size_t i = 0; i < particles.size(); ++i) {
        if (!particles[i].active) continue;
        particles[i].pos_x += particles[i].vel_x * DT;
        particles[i].pos_y += particles[i].vel_y * DT;
        particles[i].pos_z += particles[i].vel_z * DT;
        particles[i].lifetime -= DT;
        if (particles[i].lifetime <= 0) particles[i].active = 0;
    }
}

// ============ 粒子更新：SoA 版本 ============
void update_soa(ParticleSystemSoA& sys, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        if (!sys.active[i]) continue;
        sys.pos_x[i] += sys.vel_x[i] * DT;
        sys.pos_y[i] += sys.vel_y[i] * DT;
        sys.pos_z[i] += sys.vel_z[i] * DT;
        sys.lifetime[i] -= DT;
        if (sys.lifetime[i] <= 0) sys.active[i] = 0;
    }
}

void run_benchmark() {
    // 初始化 AoS
    std::vector<ParticleAoS> aos_particles(NUM_PARTICLES);
    for (size_t i = 0; i < NUM_PARTICLES; ++i) {
        auto& p = aos_particles[i];
        p.pos_x = static_cast<float>(i);
        p.pos_y = static_cast<float>(i * 2);
        p.pos_z = static_cast<float>(i * 3);
        p.vel_x = 1.0f;
        p.vel_y = 0.5f;
        p.vel_z = 0.0f;
        p.lifetime = 5.0f;
        p.active = 1;
    }

    // 初始化 SoA
    ParticleSystemSoA soa(NUM_PARTICLES);
    for (size_t i = 0; i < NUM_PARTICLES; ++i) {
        soa.pos_x[i] = static_cast<float>(i);
        soa.pos_y[i] = static_cast<float>(i * 2);
        soa.pos_z[i] = static_cast<float>(i * 3);
        soa.vel_x[i] = 1.0f;
        soa.vel_y[i] = 0.5f;
        soa.vel_z[i] = 0.0f;
        soa.lifetime[i] = 5.0f;
        soa.active[i] = 1;
    }

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "Benchmark: " << NUM_PARTICLES << " particles, " << "AoS vs SoA\n";

    double aos_time = benchmark([&]() { update_aos(aos_particles); });
    std::cout << "AoS: " << aos_time << " ms  ("
              << (NUM_PARTICLES / aos_time * 1000 / 1e6) << " M particles/s)\n";

    double soa_time = benchmark([&]() { update_soa(soa, NUM_PARTICLES); });
    std::cout << "SoA: " << soa_time << " ms  ("
              << (NUM_PARTICLES / soa_time * 1000 / 1e6) << " M particles/s)\n";

    std::cout << "Speedup: " << (aos_time / soa_time) << "x\n";
}
```

### 示例 2：伪共享演示与修复

```cpp
#include <atomic>
#include <thread>
#include <vector>
#include <iostream>
#include <chrono>

// ❌ 伪共享版本：两个计数器在同一缓存行
struct CountersFalseSharing {
    std::atomic<uint64_t> a{0};
    std::atomic<uint64_t> b{0};
};

// ✅ 修复版本：每个计数器独占缓存行
struct alignas(64) CounterPadded {
    std::atomic<uint64_t> value{0};
};

void false_sharing_demo() {
    constexpr int ITERATIONS = 100'000'000;
    constexpr int RUNS       = 5;

    std::cout << "=== False Sharing Demo ===\n";

    for (int run = 0; run < RUNS; ++run) {
        // 伪共享版本
        CountersFalseSharing counters;
        auto start = std::chrono::high_resolution_clock::now();

        std::thread t1([&]() {
            for (int i = 0; i < ITERATIONS; ++i)
                counters.a.fetch_add(1, std::memory_order_relaxed);
        });
        std::thread t2([&]() {
            for (int i = 0; i < ITERATIONS; ++i)
                counters.b.fetch_add(1, std::memory_order_relaxed);
        });

        t1.join(); t2.join();
        auto end = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(end - start).count();
        std::cout << "[False Sharing] Run " << run << ": " << ms << " ms\n";
    }

    for (int run = 0; run < RUNS; ++run) {
        // 修复版本
        CounterPadded a, b;
        auto start = std::chrono::high_resolution_clock::now();

        std::thread t1([&]() {
            for (int i = 0; i < ITERATIONS; ++i)
                a.value.fetch_add(1, std::memory_order_relaxed);
        });
        std::thread t2([&]() {
            for (int i = 0; i < ITERATIONS; ++i)
                b.value.fetch_add(1, std::memory_order_relaxed);
        });

        t1.join(); t2.join();
        auto end = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(end - start).count();
        std::cout << "[Padded]       Run " << run << ": " << ms << " ms\n";
    }
}
```

### 示例 3：热/冷分裂实战

```cpp
#include <cstring>

// ❄️ 冷数据
struct EntityCold {
    char name[48];
    int  entity_id;
    int  layer_mask;
};

// 🔥 热数据（缓存友好，频繁访问）
struct alignas(64) EntityHot {
    float pos_x, pos_y, pos_z;
    float vel_x, vel_y, vel_z;
    float radius;
    int   flags;
    // padding 到 32 字节——两个热实体正好填满一个缓存行
};

// 关联：通过索引和指针
struct Entity {
    EntityHot*  hot;
    EntityCold* cold;
};

// 热路径：只遍历 EntityHot
void physics_update(EntityHot* hots, size_t count, float dt) {
    for (size_t i = 0; i < count; ++i) {
        auto& h = hots[i];
        h.pos_x += h.vel_x * dt;
        h.pos_y += h.vel_y * dt;
        h.pos_z += h.vel_z * dt;
        // 不碰 cold 数据！缓存完全用于热数据
    }
}
```

### 示例 4：__builtin_prefetch 基准

```cpp
#include <vector>

struct Data { float values[64]; };  // 256 字节

void prefetch_benchmark() {
    constexpr size_t N = 10'000'000;
    std::vector<Data> data(N);

    // 无 prefetch
    volatile float sum = 0;
    auto t1 = std::chrono::high_resolution_clock::now();
    for (size_t i = 0; i < N; ++i) {
        sum += data[i].values[0];
    }
    auto t2 = std::chrono::high_resolution_clock::now();

    // 有 prefetch（提前 16 步）
    auto t3 = std::chrono::high_resolution_clock::now();
    constexpr int PREFETCH_DIST = 16;
    for (size_t i = 0; i < N; ++i) {
        if (i + PREFETCH_DIST < N)
            __builtin_prefetch(&data[i + PREFETCH_DIST], 0, 3);
        sum += data[i].values[0];
    }
    auto t4 = std::chrono::high_resolution_clock::now();

    std::cout << "No prefetch: " << std::chrono::duration<double, std::milli>(t2 - t1).count() << " ms\n";
    std::cout << "Prefetch:    " << std::chrono::duration<double, std::milli>(t4 - t3).count() << " ms\n";
}
```

---

## 3. 练习

### 练习 1（必修）：AoS → SoA 重构与性能测量

1. 取上述示例 1 中的 AoS 粒子系统，将其重构为 SoA 布局
2. 实现 `update_aos` 和 `update_soa` 两个函数
3. 用 `std::chrono` 测量两者的耗时，计算加速比
4. 额外添加一个"只更新位置、不读 lifetime/active"的遍历：`pos_only_update()`——展示 SoA 在部分字段遍历时的优势
5. 至少用 1M 粒子进行测试，确保差异显著

### 练习 2（必修）：识别并修复伪共享

给定以下多线程物理更新代码（假设在 4 核 CPU 上运行，每个线程处理 1/4 的实体）：

```cpp
struct alignas(64) PhysicsBatch {
    float total_impulse;  // 线程 A 写入
    float total_energy;   // 线程 A 写入
    int   collision_count;// 线程 A 写入
    // ... 其他字段
};
// 四个 PhysicsBatch 实例分配在连续内存中
PhysicsBatch batches[4];  // 每个线程一个
```

1. 分析是否存在伪共享（提示：`batches[0]` 和 `batches[1]` 的布局）
2. 设计修复方案（提示：每个 PhysicsBatch 需要 `alignas(64)` 吗？需要填充吗？）
3. 实现伪共享版本和修复版本的基准对比

### 练习 3（选做挑战）：AoSoA 粒子系统

实现一个 AoSoA 布局的粒子系统：

1. 每组 16 个粒子（一个 SIMD 宽度），每个粒子组内是 SoA
2. 每个字段组 `alignas(64)` 对齐
3. 实现 `pos += vel * dt` 更新循环
4. 实现粒子生成和销毁（维护 active 掩码或 swap-remove）
5. 与纯 SoA 和纯 AoS 做吞吐量对比
6. 思考：当粒子数量不是 16 的倍数时如何处理（空位标记）

---

## 4. 扩展阅读

- **"What Every Programmer Should Know About Memory"** (Ulrich Drepper, 2007) — 缓存层次结构的权威经典
- **Data-Oriented Design** (Richard Fabian, 2018) — 在线免费，DOD 实战手册
- **"Pitfalls of Object-Oriented Programming"** (Tony Albrecht, 2009) — 游戏开发的 DOD 宣言
- **CppCon 2014: "Data-Oriented Design and C++"** (Mike Acton) — 改变游戏引擎编程范式的演讲
- **UE5 Niagara 源码**: `Engine/Plugins/FX/Niagara` — 工业级 AoSoA 粒子系统参考
- **Compiler Explorer**: 观察 `alignas(64)` 如何影响 struct 布局
- **perf stat** / **VTune** — 实际测量你机器的缓存命中率

---

## 常见陷阱

### 陷阱 1：盲目将所有数据结构改为 SoA

```cpp
// ❌ 过度优化：对只有 10 个实体的列表也上 SoA
// 代码复杂度上升，性能提升为零（甚至更差——额外的指针间接）

// ✅ 正确策略：只对满足以下条件的热路径数据使用 SoA：
// 1. 元素数量 > 1000
// 2. 更新循环只访问少数字段
// 3. 循环出现在每帧执行的热路径上
```

**判断方法**：先用 AoS 写，用 profiler 找到缓存 Miss 高的循环，再针对性改写。

### 陷阱 2：忘记 `alignas` 导致伪共享

```cpp
// ❌ 对 struct 加 alignas 但忘了数组元素间的填充
struct alignas(64) Worker {
    char data[32];
};
Worker workers[4];
// workers[0] 和 workers[1] 可能在同一个缓存行！（alignas 只保证第一个元素对齐）
// Worker 是 32 字节，64/32=2，所以 workers[0] 和 workers[1] 共享一个缓存行

// ✅ 确保 struct 大小 ≥ 硬件缓存行大小
struct alignas(64) WorkerFixed {
    char data[64];  // 填满 64 字节
};
// 或使用 C++17：alignas(std::hardware_destructive_interference_size)
```

### 陷阱 3：SoA 重构引入复杂的内存管理

```cpp
// ❌ 手动管理多个独立数组容易泄漏和越界
float* x = new float[n];  // 某处忘记释放
float* y = new float[n];  // 如果 n 很大，多次 new 导致碎片化

// ✅ 用一个连续分配管理所有数组
float* data = new float[n * NUM_FIELDS];
float* x = data + 0 * n;
float* y = data + 1 * n;
// 或使用 std::vector<std::array<float, NUM_FIELDS>> 的转置视图
```

### 陷阱 4：prefetch 距离不当

```cpp
// ❌ 预取距离太近：数据还没用到就被挤出 L1
__builtin_prefetch(&data[i + 2]);   // 只提前 2 步

// ❌ 预取距离太远：占用 L1 空间，驱逐当前使用的数据
__builtin_prefetch(&data[i + 500]); // 提前 500 步

// ✅ 经验法则：PREFETCH_DIST ≈ L1_SIZE / sizeof(element) / 3~4
// 对于 64 字节元素：32KB / 64B / 4 ≈ 128，实际常用 8~16
```

### 陷阱 5：将 `alignas` 用在堆分配上但未用 aligned new

```cpp
struct alignas(64) AlignedData { int data[16]; };

// ❌ 默认 new 不保证 64 字节对齐
AlignedData* p = new AlignedData;  // 通常是 16 字节对齐

// ✅ C++17 aligned new
AlignedData* p = new(std::align_val_t{64}) AlignedData;  // 手动指定
// 或者使用自定义对齐分配器（参见 教程 12: Placement New 与对齐控制）
```
