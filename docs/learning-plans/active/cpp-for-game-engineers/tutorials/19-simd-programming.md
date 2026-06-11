---
title: "19. SIMD 编程入门"
updated: 2026-06-05
---

# 19. SIMD 编程入门

> **所属计划**: C++ 游戏工程师详细攻略 — 阶段 5：数据导向设计
> **预计耗时**: 4 小时
> **前置知识**: [[12-placement-new-alignment|12-Placement New 与对齐控制]]、[[18-aos-soa-cache-optimization|18-AoS vs SoA 与缓存优化]]
> **C++ 标准**: 不可移植的 intrinsic（需 `<xmmintrin.h>`, `<immintrin.h>` 等）

---

## 1. 概念讲解

### 1.1 什么是一组指令处理多份数据

SIMD（Single Instruction, Multiple Data）**不是多线程**。它是一条 CPU 指令同时操作多个数据元素——例如一次加法同时完成 4 对浮点数的相加。

```
标量 (scalar)：        a0 + b0 = c0
                           ↓ 一条 addss 指令

SIMD (128-bit)：       [a0,a1,a2,a3] + [b0,b1,b2,b3] = [c0,c1,c2,c3]
                           ↓ 一条 addps 指令（packed single）
```

**游戏引擎为何关心**：粒子更新、顶点变换、骨骼动画混合、碰撞检测 (AABB) 都是大量**同构运算**——天然适合 SIMD。

### 1.2 三键指令集层级

| 指令集 | 寄存器宽度 | 浮点数容量 | 引入时代 | 游戏支持现状 |
|--------|----------|-----------|---------|-------------|
| SSE (1-4.2) | 128 bit (`xmm0`) | 4× float | ~2000 (Pentium III) | 所有 x64 CPU 必备 |
| AVX | 256 bit (`ymm0`) | 8× float | 2011 (Sandy Bridge) | 主流支持 |
| AVX-512 | 512 bit (`zmm0`) | 16× float | 2016 (Xeon Phi/Skylake-X) | 高端/服务器，游戏机不支持 |
| NEON | 128 bit | 4× float | ARM (所有手机/ Switch) | 跨平台必备 |

**可移植性策略**：引擎通常提供 SSE 作为最低共同基准，用预处理器选择 AVX/NEON 路径。

### 1.3 核心数据类型

```cpp
#include <xmmintrin.h>   // SSE
#include <emmintrin.h>   // SSE2
#include <pmmintrin.h>   // SSE3
#include <immintrin.h>   // AVX, AVX2, FMA (包含所有 SSE)

__m128  reg;             // 4× float
__m128d regd;            // 2× double
__m128i regi;            // 4× int32 / 8× int16 / 16× int8
__m256  reg_avx;         // 8× float
__m256d regd_avx;        // 4× double
__m256i regi_avx;        // 可变 int
```

**关键理解**：`__m128` 不是四个独立的 `float`。它是一个**寄存器内容**——数据必须通过 `_mm_load_ps` / `_mm_set_ps` 装入，用 `_mm_store_ps` / `_mm_extract_ps` 取出。

### 1.4 Intrinsic 命名约定

Intrinsic（内部函数）的命名由三部分组成：

```
_mm_<operation>_<suffix>
 _mm256_ 用于 AVX 256-bit
 _mm512_ 用于 AVX-512

后缀含义：
  ps  = packed single  (4× float 同时运算)
  ss  = scalar single  (只操作最低 32-bit 的 float)
  pd  = packed double  (2× double)
  sd  = scalar double
  epi32 = extended packed integer 32-bit (4× int32)
  si128 = 128-bit 整数（不解释类型）
```

```cpp
_mm_add_ps(a, b);      // 4 个 float 同时相加
_mm_add_ss(a, b);      // 只有 a[0] 加 b[0]，其他保持不变
_mm_hadd_ps(a, b);     // 水平相加（horizontal add）
_mm_shuffle_ps(a, b, mask);  // 重排
```

### 1.5 基本操作：load, store, add, mul

```cpp
// 加载（LOAD）
__m128 v = _mm_load_ps(&float_array[0]);       // 要求 16 字节对齐 → 速度更快
__m128 v = _mm_loadu_ps(&float_array[0]);      // 不要求对齐 → 可移植但可能稍慢

// 设置（SET）——手动构造
__m128 v = _mm_set_ps(z, y, x, w);              // v = [w, x, y, z]（注意顺序！）
__m128 v = _mm_set1_ps(1.0f);                  // v = [1, 1, 1, 1]（广播）
__m128 v = _mm_setzero_ps();                    // v = [0, 0, 0, 0]

// 算术
__m128 s = _mm_add_ps(a, b);                   // s[i] = a[i] + b[i]
__m128 d = _mm_sub_ps(a, b);                   // d[i] = a[i] - b[i]
__m128 p = _mm_mul_ps(a, b);                   // p[i] = a[i] * b[i]
__m128 q = _mm_div_ps(a, b);                   // q[i] = a[i] / b[i]

// 融合乘加（FMA, AVX 引入）—— 一次完成乘法+加法
__m128 r = _mm_fmadd_ps(a, b, c);              // r[i] = a[i] * b[i] + c[i]

// 存储（STORE）
_mm_store_ps(&float_array[0], v);              // 对齐存储
_mm_storeu_ps(&float_array[0], v);             // 非对齐存储
```

### 1.6 水平 vs 垂直操作

**垂直操作** (Vertical)：同一下标间的运算——几乎所有 SIMD 指令都是垂直的。

```
a:  [a0, a1, a2, a3]
b:  [b0, b1, b2, b3]
──────────────────
add:[a0+b0, a1+b1, a2+b2, a3+b3]  ← 垂直加法
```

**水平操作** (Horizontal)：同一寄存器内部的约简——像点积、求和这类需要跨通道组合的操作。

```cpp
// 水平加法：将 a 和 b 的元素两两相加，结果交错
// _mm_hadd_ps([a0,a1,a2,a3], [b0,b1,b2,b3])
//   → [a0+a1, a2+a3, b0+b1, b2+b3]
// 两次 hadd 可实现 4 元素全求和
```

**何时用水平**：点积、向量模长、矩阵行列式等需要约简的操作。

**引擎最佳实践**：能垂直处理就垂直处理——水平操作延迟高，会打断流水线。

### 1.7 Shuffle 与排列：SIMD 的灵魂

`_mm_shuffle_ps` 是最强大也最难掌握的操作——它从两个源寄存器中**任意选取通道**组成结果：

```cpp
// _mm_shuffle_ps(a, b, _MM_SHUFFLE(z, y, x, w))
// 结果:
//   result[0] = a[w]    (w 选择 a 的哪个通道)
//   result[1] = a[x]
//   result[2] = b[y]    (y, z 选择 b 的通道)
//   result[3] = b[z]

// 经典用法：将 a 的所有通道广播到结果的各位置
__m128 all_x = _mm_shuffle_ps(v, v, _MM_SHUFFLE(0,0,0,0));  // [v.x,v.x,v.x,v.x]
__m128 all_y = _mm_shuffle_ps(v, v, _MM_SHUFFLE(1,1,1,1));  // [v.y,v.y,v.y,v.y]
__m128 all_z = _mm_shuffle_ps(v, v, _MM_SHUFFLE(2,2,2,2));  // [v.z,v.z,v.z,v.z]
```

**引擎用途**：矩阵运算中广播矩阵列/行，批量点积中广播相同向量。

### 1.8 SIMD 点积与叉积

```cpp
// 点积：broadcast→mul→horizontal add
inline __m128 dot_ps(__m128 a, __m128 b) {
    // a:[ax,ay,az,aw]  b:[bx,by,bz,bw]
    __m128 mul  = _mm_mul_ps(a, b);     // [ax*bx, ay*by, az*bz, aw*bw]
    __m128 hadd = _mm_hadd_ps(mul, mul);// [ax*bx+ay*by, az*bz+aw*bw, ...]
    return _mm_hadd_ps(hadd, hadd);     // [result, result, result, result]
}

// 叉积：shuffle→mul→sub
inline __m128 cross_ps(__m128 a, __m128 b) {
    // a:[ax,ay,az,aw]  b:[bx,by,bz,bw]
    __m128 a_yzx = _mm_shuffle_ps(a, a, _MM_SHUFFLE(3,0,2,1)); // [ay,az,ax,aw]
    __m128 b_yzx = _mm_shuffle_ps(b, b, _MM_SHUFFLE(3,0,2,1));
    __m128 a_zxy = _mm_shuffle_ps(a, a, _MM_SHUFFLE(3,1,0,2)); // [az,ax,ay,aw]
    __m128 b_zxy = _mm_shuffle_ps(b, b, _MM_SHUFFLE(3,1,0,2));

    __m128 left  = _mm_mul_ps(a_yzx, b_zxy);
    __m128 right = _mm_mul_ps(a_zxy, b_yzx);
    return _mm_sub_ps(left, right);      // result in xyz, w unchanged
}
```

### 1.9 SoA + SIMD = 性能倍增

这就是为什么上一节讲 SoA：

```cpp
// SoA 数据：pos_x[4] 连续存储
float pos_x[4] = {1, 2, 3, 4};
float vel_x[4] = {0.1, 0.2, 0.3, 0.4};

// 一次 load + 一次 add + 一次 store → 4 个粒子的 x 坐标同时更新
__m128 px = _mm_load_ps(pos_x);    // [1, 2, 3, 4]
__m128 vx = _mm_load_ps(vel_x);    // [0.1, 0.2, 0.3, 0.4]
__m128 dt = _mm_set1_ps(0.016f);   // [0.016, 0.016, 0.016, 0.016]
px = _mm_add_ps(px, _mm_mul_ps(vx, dt));  // pos += vel * dt（4 路并行）
_mm_store_ps(pos_x, px);
```

**如果数据是 AoS 布局**：每个粒子的 x 坐标相隔 32+ 字节 → 无法用一次 load 装填 4 个 x → 必须 gather 指令（AVX2 `_mm_i32gather_ps`，慢得多）。

### 1.10 对齐要求

```cpp
// _mm_load_ps 要求 16 字节对齐——如果不对齐 → SIGSEGV（硬崩溃）
// _mm_loadu_ps 不要求对齐 → 在旧 CPU 上稍慢，现代 x86 差异很小（但仍需注意）

// 确保对齐：
alignas(16) float data[4];       // C++11 alignas
// 或
float* data = (float*)_aligned_malloc(64 * sizeof(float), 16);  // MSVC
float* data = (float*)aligned_alloc(16, 64 * sizeof(float));    // C++17
```

**引擎建议**：所有 SIMD 操作的数据缓冲区都 `alignas(16)` 或更大，使用对齐 load/store。

### 1.11 自动向量化与 `__restrict`

编译器可以在特定条件下自动将标量循环转为 SIMD 指令——**自动向量化**。

```cpp
// 编译器能自动向量化的循环特征：
// 1. 简单循环计数（可确定迭代次数）
// 2. 连续内存访问（数组，不是链表）
// 3. 指针不重叠（无别名）

// __restrict 告诉编译器"这两个指针不重叠"——关键提示
void update_positions(float* __restrict pos, const float* __restrict vel,
                      float dt, int count) {
    for (int i = 0; i < count; ++i)
        pos[i] += vel[i] * dt;   // 编译器可以合法地向量化
}
```

**检查编译器是否自动向量化**：
- GCC/Clang: `-fopt-info-vec` 或 `-Rpass=vector`
- MSVC: `/Qvec-report:2`
- 最佳工具：**Compiler Explorer (godbolt.org)** ——直接看汇编

**什么阻碍自动向量化？**
- 循环内有函数调用（除非函数被内联且可向量化）
- `if`/`break`/`continue` 打破连续流
- 指针别名不确定
- 非连续内存（链表、map、间接索引）

---

## 2. 代码示例

### 示例 1：SSE Vec3 数学库

```cpp
#include <xmmintrin.h>
#include <cmath>

struct Vec3 {
    union { __m128 m; struct { float x, y, z, w; }; };

    Vec3(float x_=0, float y_=0, float z_=0)
        : m(_mm_set_ps(0, z_, y_, x_)) {}  // 注意 set_ps 参数顺序

    Vec3(__m128 v) : m(v) {}
};

inline Vec3 operator+(Vec3 a, Vec3 b) { return _mm_add_ps(a.m, b.m); }
inline Vec3 operator-(Vec3 a, Vec3 b) { return _mm_sub_ps(a.m, b.m); }
inline Vec3 operator*(Vec3 a, Vec3 b) { return _mm_mul_ps(a.m, b.m); }
inline Vec3 operator*(Vec3 a, float s) { return _mm_mul_ps(a.m, _mm_set1_ps(s)); }

// SIMD 点积
inline float dot(Vec3 a, Vec3 b) {
    __m128 mul  = _mm_mul_ps(a.m, b.m);
    __m128 shuf = _mm_shuffle_ps(mul, mul, _MM_SHUFFLE(2,3,0,1));
    __m128 sum  = _mm_add_ps(mul, shuf);
    shuf = _mm_shuffle_ps(sum, sum, _MM_SHUFFLE(1,1,2,2));
    sum  = _mm_add_ps(sum, shuf);
    return _mm_cvtss_f32(sum);  // 提取最低 float
}

// SIMD 叉积
inline Vec3 cross(Vec3 a, Vec3 b) {
    __m128 a_yzx = _mm_shuffle_ps(a.m, a.m, _MM_SHUFFLE(3,0,2,1));
    __m128 b_yzx = _mm_shuffle_ps(b.m, b.m, _MM_SHUFFLE(3,0,2,1));
    __m128 a_zxy = _mm_shuffle_ps(a.m, a.m, _MM_SHUFFLE(3,1,0,2));
    __m128 b_zxy = _mm_shuffle_ps(b.m, b.m, _MM_SHUFFLE(3,1,0,2));
    return _mm_sub_ps(_mm_mul_ps(a_yzx, b_zxy),
                      _mm_mul_ps(a_zxy, b_yzx));
}

// SIMD 归一化
inline Vec3 normalize(Vec3 v) {
    float d = dot(v, v);
    __m128 rcp_sqrt = _mm_rsqrt_ss(_mm_set_ss(d));  // 快速倒数平方根
    float scale = _mm_cvtss_f32(rcp_sqrt);
    // 一次 Newton-Raphson 迭代提高精度
    scale = scale * (1.5f - 0.5f * d * scale * scale);
    return _mm_mul_ps(v.m, _mm_set1_ps(scale));
}

// SIMD 长度
inline float length(Vec3 v) {
    return std::sqrt(dot(v, v));
}
```

### 示例 2：SSE 粒子位置更新

```cpp
#include <xmmintrin.h>
#include <vector>

void sse_particle_update(float* pos_x, float* pos_y, float* pos_z,
                         const float* vel_x, const float* vel_y, const float* vel_z,
                         float dt, size_t count) {
    __m128 vdt = _mm_set1_ps(dt);

    for (size_t i = 0; i + 3 < count; i += 4) {
        // 加载 4 个粒子的数据
        __m128 px = _mm_load_ps(pos_x + i);
        __m128 py = _mm_load_ps(pos_y + i);
        __m128 pz = _mm_load_ps(pos_z + i);
        __m128 vx = _mm_load_ps(vel_x + i);
        __m128 vy = _mm_load_ps(vel_y + i);
        __m128 vz = _mm_load_ps(vel_z + i);

        // pos += vel * dt（全部 4 通道并行）
        px = _mm_add_ps(px, _mm_mul_ps(vx, vdt));
        py = _mm_add_ps(py, _mm_mul_ps(vy, vdt));
        pz = _mm_add_ps(pz, _mm_mul_ps(vz, vdt));

        // 存储回去
        _mm_store_ps(pos_x + i, px);
        _mm_store_ps(pos_y + i, py);
        _mm_store_ps(pos_z + i, pz);
    }

    // 剩余不足 4 个的粒子用标量处理
    for (size_t i = count & ~3ull; i < count; ++i) {
        pos_x[i] += vel_x[i] * dt;
        pos_y[i] += vel_y[i] * dt;
        pos_z[i] += vel_z[i] * dt;
    }
}
```

### 示例 3：SSE AABB 重叠测试

```cpp
// AABB: 由 min 和 max 两个点定义
struct AABB {
    alignas(16) float min_x, min_y, min_z, _pad1;
    alignas(16) float max_x, max_y, max_z, _pad2;
};

// 返回 true 如果两个 AABB 重叠
inline bool aabb_overlap_sse(const AABB& a, const AABB& b) {
    // 加载两个 AABB 的 min 和 max（xyz，忽略 pad）
    __m128 a_min = _mm_load_ps(&a.min_x);
    __m128 a_max = _mm_load_ps(&a.max_x);
    __m128 b_min = _mm_load_ps(&b.min_x);
    __m128 b_max = _mm_load_ps(&b.max_x);

    // 分离轴定理：所有轴上的投影必须重叠
    // a.max >= b.min 且 b.max >= a.min（三个维度同时检测）
    __m128 cmp1 = _mm_cmpge_ps(a_max, b_min);  // a_max >= b_min
    __m128 cmp2 = _mm_cmpge_ps(b_max, a_min);  // b_max >= a_min
    __m128 both = _mm_and_ps(cmp1, cmp2);       // 两者都为真

    // 检查所有三个通道（x, y, z）是否都为真
    int mask = _mm_movemask_ps(both);           // 每个 float 的 sign bit → 4-bit mask
    return (mask & 0x7) == 0x7;                 // 0x7 = 0111（忽略 w）
}
```

### 示例 4：对齐强制演示

```cpp
#include <cstdlib>

template<typename T, size_t Alignment>
struct AlignedAllocator {
    using value_type = T;

    T* allocate(size_t n) {
        if (n == 0) return nullptr;

        size_t size = n * sizeof(T);
        // 确保 size 是 Alignment 的倍数（避免越界访问）
        size = (size + Alignment - 1) & ~(Alignment - 1);

        void* ptr = nullptr;
        #ifdef _WIN32
            ptr = _aligned_malloc(size, Alignment);
        #else
            ptr = std::aligned_alloc(Alignment, size);
        #endif
        if (!ptr) throw std::bad_alloc();
        return static_cast<T*>(ptr);
    }

    void deallocate(T* ptr, size_t) {
        #ifdef _WIN32
            _aligned_free(ptr);
        #else
            std::free(ptr);
        #endif
    }
};

// 用法：16 字节对齐的 float 数组
std::vector<float, AlignedAllocator<float, 16>> simd_buffer(1024);
// simd_buffer.data() 保证 16 字节对齐
```

### 示例 5：4×4 矩阵 × 向量（SSE）

```cpp
// 4×4 矩阵按行存储
struct alignas(16) Mat4 { float m[4][4]; };

// 矩阵 × 向量 = 4 次点积
Vec3 mat4_mul_vec3(const Mat4& mat, Vec3 v) {
    __m128 v4 = _mm_set_ps(1.0f, v.z, v.y, v.x);  // [x,y,z,1]

    // 每行做点积：broadcast 行的每个分量 → mul → 水平加
    __m128 row0 = _mm_load_ps(mat.m[0]);
    __m128 row1 = _mm_load_ps(mat.m[1]);
    __m128 row2 = _mm_load_ps(mat.m[2]);

    __m128 r0 = _mm_mul_ps(row0, v4);
    __m128 r1 = _mm_mul_ps(row1, v4);
    __m128 r2 = _mm_mul_ps(row2, v4);

    // 水平求和
    r0 = _mm_hadd_ps(r0, r0);
    r0 = _mm_hadd_ps(r0, r0);
    r1 = _mm_hadd_ps(r1, r1);
    r1 = _mm_hadd_ps(r1, r1);
    r2 = _mm_hadd_ps(r2, r2);
    r2 = _mm_hadd_ps(r2, r2);

    float x = _mm_cvtss_f32(r0);
    float y = _mm_cvtss_f32(r1);
    float z = _mm_cvtss_f32(r2);
    return {x, y, z};
}
```

---

## 3. 练习

### 练习 1（必修）：SSE 粒子位置更新

1. 基于示例 2，实现完整的 `sse_particle_update()` 函数
2. 同时实现标量版本 `scalar_particle_update()`
3. 用 `std::chrono` 测量两者处理 1M 粒子的耗时
4. 确保数据使用 SoA 布局并对齐到 16 字节
5. 计算加速比。预期 SSE 版本应快 2-4 倍

### 练习 2（必修）：SSE 4×4 矩阵 × 向量乘法

1. 实现 `void sse_mat4_mul_vec4(float result[4], const float mat[16], const float vec[4])` 
2. 同时实现标量版本
3. 用相同矩阵和向量调用 1M 次做基准测试
4. 使用 `_mm_dp_ps`（SSE4.1 dot product，如果可用）作为替代实现比较
5. 可选：扩展到批量模式——一次处理 4 个向量（每个向量使用相同的矩阵）

### 练习 3（选做挑战）：SSE vs AVX 对比 + 可移植性抽象

1. 实现 SSE 和 AVX 两个版本的粒子更新（处理 1M 粒子）
2. 使用预处理器宏 (`#ifdef __AVX__` 等) 实现一个统一的 `simd_particle_update()` 接口
3. 使用编译器标志分别编译 SSE 版本和 AVX 版本：
   - SSE: `g++ -std=c++20 -msse4.2 -O2`
   - AVX: `g++ -std=c++20 -mavx2 -O2`
4. 基准测试两者，观察 AVX 是否达到接近 2× 的加速（理论上）
5. 讨论：为什么实际加速比可能低于理论值（内存带宽瓶颈？）

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> > #include <iostream>
> > #include <chrono>
> > #include <xmmintrin.h>  // SSE
> > #include <cstdlib>      // aligned_alloc (C++17)
> >
> > constexpr size_t NUM = 1'000'000;
> > constexpr float  DT  = 0.016f;
> >
> > // ============ SoA 布局 + 16 字节对齐 ============
> > struct ParticleSSE {
> >     alignas(16) float* pos_x, *pos_y, *pos_z;
> >     alignas(16) float* vel_x, *vel_y, *vel_z;
> >     size_t count;
> >
> >     ParticleSSE(size_t n) : count(n) {
> >         // 确保对齐分配（16 字节对齐）
> >         pos_x = static_cast<float*>(std::aligned_alloc(16, n * sizeof(float)));
> >         pos_y = static_cast<float*>(std::aligned_alloc(16, n * sizeof(float)));
> >         pos_z = static_cast<float*>(std::aligned_alloc(16, n * sizeof(float)));
> >         vel_x = static_cast<float*>(std::aligned_alloc(16, n * sizeof(float)));
> >         vel_y = static_cast<float*>(std::aligned_alloc(16, n * sizeof(float)));
> >         vel_z = static_cast<float*>(std::aligned_alloc(16, n * sizeof(float)));
> >     }
> >     ~ParticleSSE() {
> >         std::free(pos_x); std::free(pos_y); std::free(pos_z);
> >         std::free(vel_x); std::free(vel_y); std::free(vel_z);
> >     }
> > };
> >
> > // ============ SSE 粒子更新 ============
> > void sse_particle_update(ParticleSSE& p) {
> >     size_t n = p.count - (p.count % 4);  // 处理 4 的倍数
> >     __m128 dt = _mm_set1_ps(DT);
> >
> >     for (size_t i = 0; i < n; i += 4) {
> >         // 加载 4 个连续 float
> >         __m128 px = _mm_load_ps(&p.pos_x[i]);
> >         __m128 py = _mm_load_ps(&p.pos_y[i]);
> >         __m128 pz = _mm_load_ps(&p.pos_z[i]);
> >         __m128 vx = _mm_load_ps(&p.vel_x[i]);
> >         __m128 vy = _mm_load_ps(&p.vel_y[i]);
> >         __m128 vz = _mm_load_ps(&p.vel_z[i]);
> >
> >         // pos += vel * dt（4 路并行）
> >         px = _mm_add_ps(px, _mm_mul_ps(vx, dt));
> >         py = _mm_add_ps(py, _mm_mul_ps(vy, dt));
> >         pz = _mm_add_ps(pz, _mm_mul_ps(vz, dt));
> >
> >         // 存回
> >         _mm_store_ps(&p.pos_x[i], px);
> >         _mm_store_ps(&p.pos_y[i], py);
> >         _mm_store_ps(&p.pos_z[i], pz);
> >     }
> >
> >     // 尾数处理（n%4 != 0 时）
> >     for (size_t i = n; i < p.count; ++i) {
> >         p.pos_x[i] += p.vel_x[i] * DT;
> >         p.pos_y[i] += p.vel_y[i] * DT;
> >         p.pos_z[i] += p.vel_z[i] * DT;
> >     }
> > }
> >
> > // ============ 标量版本 ============
> > void scalar_particle_update(ParticleSSE& p) {
> >     for (size_t i = 0; i < p.count; ++i) {
> >         p.pos_x[i] += p.vel_x[i] * DT;
> >         p.pos_y[i] += p.vel_y[i] * DT;
> >         p.pos_z[i] += p.vel_z[i] * DT;
> >     }
> > }
> >
> > // ============ 初始化 ============
> > void init_particles(ParticleSSE& p) {
> >     for (size_t i = 0; i < p.count; ++i) {
> >         p.pos_x[i] = static_cast<float>(i);
> >         p.pos_y[i] = static_cast<float>(i * 2);
> >         p.pos_z[i] = static_cast<float>(i * 3);
> >         p.vel_x[i] = 1.0f;
> >         p.vel_y[i] = 0.5f;
> >         p.vel_z[i] = 0.0f;
> >     }
> > }
> >
> > // ============ 基准 ============
> > template<typename F>
> > double bench(F&& f, int iters = 30) {
> >     for (int i = 0; i < 3; ++i) f();
> >     double best = 1e18;
> >     for (int i = 0; i < iters; ++i) {
> >         auto t1 = std::chrono::high_resolution_clock::now();
> >         f();
> >         auto t2 = std::chrono::high_resolution_clock::now();
> >         double ms = std::chrono::duration<double, std::milli>(t2 - t1).count();
> >         if (ms < best) best = ms;
> >     }
> >     return best;
> > }
> >
> > int main() {
> >     // 准备两份相同的数据
> >     ParticleSSE p1(NUM), p2(NUM);
> >     init_particles(p1);
> >     init_particles(p2);
> >
> >     double scalar_ms = bench([&]() { scalar_particle_update(p1); });
> >     double sse_ms    = bench([&]() { sse_particle_update(p2); });
> >
> >     std::cout << "Scalar: " << scalar_ms << " ms\n";
> >     std::cout << "SSE:    " << sse_ms    << " ms\n";
> >     std::cout << "加速比: " << scalar_ms / sse_ms << "x\n";
> >     // 预期 SSE 快 2-4 倍
> >     return 0;
> > }
> > ```

> [!tip]- 练习 2 参考答案
> ```cpp
> > #include <iostream>
> > #include <chrono>
> > #include <xmmintrin.h>
> > #include <smmintrin.h>   // SSE4.1 _mm_dp_ps
> > #include <cstring>
> >
> > // ============ SSE 4x4 矩阵 × 向量 ============
> > // 矩阵按列优先排列：mat[0..3] = 第0列, mat[4..7] = 第1列, ...
> > inline void sse_mat4_mul_vec4(float* __restrict result,
> >                                 const float* __restrict mat,
> >                                 const float* __restrict vec) {
> >     // 加载向量 [vx, vy, vz, vw]
> >     __m128 v = _mm_loadu_ps(vec);
> >
> >     // 广播各分量
> >     __m128 v0 = _mm_shuffle_ps(v, v, _MM_SHUFFLE(0, 0, 0, 0));  // [vx,vx,vx,vx]
> >     __m128 v1 = _mm_shuffle_ps(v, v, _MM_SHUFFLE(1, 1, 1, 1));  // [vy,vy,vy,vy]
> >     __m128 v2 = _mm_shuffle_ps(v, v, _MM_SHUFFLE(2, 2, 2, 2));  // [vz,vz,vz,vz]
> >     __m128 v3 = _mm_shuffle_ps(v, v, _MM_SHUFFLE(3, 3, 3, 3));  // [vw,vw,vw,vw]
> >
> >     // 加载矩阵的 4 列
> >     __m128 c0 = _mm_loadu_ps(mat + 0);
> >     __m128 c1 = _mm_loadu_ps(mat + 4);
> >     __m128 c2 = _mm_loadu_ps(mat + 8);
> >     __m128 c3 = _mm_loadu_ps(mat + 12);
> >
> >     // 逐列乘加
> >     __m128 r = _mm_mul_ps(c0, v0);
> >     r = _mm_add_ps(r, _mm_mul_ps(c1, v1));
> >     r = _mm_add_ps(r, _mm_mul_ps(c2, v2));
> >     r = _mm_add_ps(r, _mm_mul_ps(c3, v3));
> >
> >     _mm_storeu_ps(result, r);
> > }
> >
> > // ============ SSE4.1 点积版本（使用 _mm_dp_ps） ============
> > inline void sse_dp_mat4_mul_vec4(float* __restrict result,
> >                                    const float* __restrict mat,
> >                                    const float* __restrict vec) {
> >     __m128 v = _mm_loadu_ps(vec);
> >
> >     // 每行与 vec 做点积
> >     // _mm_dp_ps(a, b, mask): mask 控制哪些通道参与、结果存放位置
> >     // 0xF1 = 1111 0001b → 全通道参与，结果写回最低位
> >     __m128 r0 = _mm_dp_ps(_mm_loadu_ps(mat + 0), v, 0xF1);
> >     __m128 r1 = _mm_dp_ps(_mm_loadu_ps(mat + 4), v, 0xF2);  // 结果在 bit[32..63]
> >     __m128 r2 = _mm_dp_ps(_mm_loadu_ps(mat + 8), v, 0xF4);
> >     __m128 r3 = _mm_dp_ps(_mm_loadu_ps(mat + 12), v, 0xF8);
> >
> >     // 合并（或操作）
> >     __m128 r01 = _mm_or_ps(r0, r1);
> >     __m128 r23 = _mm_or_ps(r2, r3);
> >     _mm_storeu_ps(result, _mm_or_ps(r01, r23));
> > }
> >
> > // ============ 标量版本 ============
> > inline void scalar_mat4_mul_vec4(float* __restrict result,
> >                                    const float* __restrict mat,
> >                                    const float* __restrict vec) {
> >     for (int row = 0; row < 4; ++row) {
> >         result[row] = mat[row+0]  * vec[0]
> >                     + mat[row+4]  * vec[1]
> >                     + mat[row+8]  * vec[2]
> >                     + mat[row+12] * vec[3];
> >     }
> > }
> >
> > // ============ 批量模式：1 个矩阵 × 4 个向量 ============
> > // 4 个 vec 组成 [v0x,v1x,v2x,v3x] [v0y,v1y,v2y,v3y] ...
> > // 适合 SoA 布局的批量向量
> >
> > // ============ 基准 ============
> > int main() {
> >     alignas(16) float mat[16] = {
> >         1,0,0,0, 0,1,0,0, 0,0,1,0, 2,3,4,1
> >     };
> >     alignas(16) float vec[4] = {1, 2, 3, 1};
> >     alignas(16) float res_sse[4], res_scalar[4];
> >
> >     constexpr int ITERS = 1'000'000;
> >
> >     // SSE 版本
> >     auto t1 = std::chrono::high_resolution_clock::now();
> >     for (int i = 0; i < ITERS; ++i)
> >         sse_mat4_mul_vec4(res_sse, mat, vec);
> >     auto t2 = std::chrono::high_resolution_clock::now();
> >
> >     // 标量版本
> >     auto t3 = std::chrono::high_resolution_clock::now();
> >     for (int i = 0; i < ITERS; ++i)
> >         scalar_mat4_mul_vec4(res_scalar, mat, vec);
> >     auto t4 = std::chrono::high_resolution_clock::now();
> >
> >     double sse_ms = std::chrono::duration<double, std::milli>(t2-t1).count();
> >     double sca_ms = std::chrono::duration<double, std::milli>(t4-t3).count();
> >
> >     std::cout << "SSE result:    [" << res_sse[0] << "," << res_sse[1]
> >               << "," << res_sse[2] << "," << res_sse[3] << "]\n";
> >     std::cout << "Scalar result: [" << res_scalar[0] << "," << res_scalar[1]
> >               << "," << res_scalar[2] << "," << res_scalar[3] << "]\n";
> >     std::cout << "SSE: " << sse_ms << " ms, Scalar: " << sca_ms << " ms\n";
> >     std::cout << "加速比: " << sca_ms / sse_ms << "x\n";
> >     return 0;
> > }
> > ```

> [!tip]- 练习 3 参考答案
> ```cpp
> > #include <iostream>
> > #include <chrono>
> > #include <cstdlib>
> > #include <cstring>
> >
> > #ifdef __AVX__
> >   #include <immintrin.h>  // AVX
> > #else
> >   #include <xmmintrin.h>   // SSE fallback
> > #endif
> >
> > constexpr size_t NUM = 1'000'000;
> > constexpr float  DT  = 0.016f;
> >
> > // ============ 统一 SIMD 接口 ============
> > #ifdef __AVX__
> >   constexpr size_t SIMD_WIDTH = 8;  // 8× float per __m256
> >   using simd_t = __m256;
> >
> >   inline simd_t simd_load(const float* p)  { return _mm256_load_ps(p); }
> >   inline void   simd_store(float* p, simd_t v) { _mm256_store_ps(p, v); }
> >   inline simd_t simd_set1(float x)         { return _mm256_set1_ps(x); }
> >   inline simd_t simd_add(simd_t a, simd_t b)  { return _mm256_add_ps(a,b); }
> >   inline simd_t simd_mul(simd_t a, simd_t b)  { return _mm256_mul_ps(a,b); }
> > #else
> >   constexpr size_t SIMD_WIDTH = 4;  // 4× float per __m128
> >   using simd_t = __m128;
> >
> >   inline simd_t simd_load(const float* p)  { return _mm_load_ps(p); }
> >   inline void   simd_store(float* p, simd_t v) { _mm_store_ps(p, v); }
> >   inline simd_t simd_set1(float x)         { return _mm_set1_ps(x); }
> >   inline simd_t simd_add(simd_t a, simd_t b)  { return _mm_add_ps(a,b); }
> >   inline simd_t simd_mul(simd_t a, simd_t b)  { return _mm_mul_ps(a,b); }
> > #endif
> >
> > // ============ 统一粒子更新 ============
> > void simd_particle_update(float* pos_x, float* pos_y, float* pos_z,
> >                            float* vel_x, float* vel_y, float* vel_z,
> >                            size_t count) {
> >     simd_t dt = simd_set1(DT);
> >     size_t n = count - (count % SIMD_WIDTH);
> >
> >     for (size_t i = 0; i < n; i += SIMD_WIDTH) {
> >         simd_t px = simd_load(&pos_x[i]);
> >         simd_t py = simd_load(&pos_y[i]);
> >         simd_t pz = simd_load(&pos_z[i]);
> >         simd_t vx = simd_load(&vel_x[i]);
> >         simd_t vy = simd_load(&vel_y[i]);
> >         simd_t vz = simd_load(&vel_z[i]);
> >
> >         px = simd_add(px, simd_mul(vx, dt));
> >         py = simd_add(py, simd_mul(vy, dt));
> >         pz = simd_add(pz, simd_mul(vz, dt));
> >
> >         simd_store(&pos_x[i], px);
> >         simd_store(&pos_y[i], py);
> >         simd_store(&pos_z[i], pz);
> >     }
> >
> >     // 尾数
> >     for (size_t i = n; i < count; ++i) {
> >         pos_x[i] += vel_x[i] * DT;
> >         pos_y[i] += vel_y[i] * DT;
> >         pos_z[i] += vel_z[i] * DT;
> >     }
> > }
> >
> > int main() {
> >     auto* px = static_cast<float*>(std::aligned_alloc(32, NUM * sizeof(float)));
> >     auto* py = static_cast<float*>(std::aligned_alloc(32, NUM * sizeof(float)));
> >     auto* pz = static_cast<float*>(std::aligned_alloc(32, NUM * sizeof(float)));
> >     auto* vx = static_cast<float*>(std::aligned_alloc(32, NUM * sizeof(float)));
> >     auto* vy = static_cast<float*>(std::aligned_alloc(32, NUM * sizeof(float)));
> >     auto* vz = static_cast<float*>(std::aligned_alloc(32, NUM * sizeof(float)));
> >
> >     for (size_t i = 0; i < NUM; ++i) {
> >         px[i] = (float)i; py[i] = (float)(i*2); pz[i] = (float)(i*3);
> >         vx[i] = 1.0f; vy[i] = 0.5f; vz[i] = 0.0f;
> >     }
> >
> >     auto t1 = std::chrono::high_resolution_clock::now();
> >     for (int iter = 0; iter < 30; ++iter)
> >         simd_particle_update(px, py, pz, vx, vy, vz, NUM);
> >     auto t2 = std::chrono::high_resolution_clock::now();
> >
> >     double ms = std::chrono::duration<double, std::milli>(t2-t1).count() / 30.0;
> >     std::cout << "SIMD width = " << SIMD_WIDTH << '\n';
> >     std::cout << "Average: " << ms << " ms per update\n";
> >     std::cout << "Throughput: " << (NUM / ms / 1000.0) << " M particles/s\n";
> >
> >     // 讨论：实际 AVX 加速比可能低于 2×
> >     // 原因 1：内存带宽成为瓶颈（DRAM 带宽有限）
> >     // 原因 2：AVX 指令在某些 CPU 上会降低频率（AVX offset）
> >     // 原因 3：如果数据已在 L2/L3 中，SSE 已接近带宽极限
> >     // 原因 4：编译器可能已对 SSE 路径做了更好的优化
> >     std::cout << "\n注意：编译时用 -mavx2 或 -msse4.2 切换指令集\n";
> >
> >     std::free(px); std::free(py); std::free(pz);
> >     std::free(vx); std::free(vy); std::free(vz);
> >     return 0;
> > }
> > ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- **Intel Intrinsics Guide** (https://www.intel.com/content/www/us/en/docs/intrinsics-guide/index.html) — 所有 x86 intrinsic 的交互式查询工具，**每日必查**
- **"SIMD at Insomniac Games"** (CppCon 2019, Andreas Fredriksson) — 游戏引擎中 SIMD 的工业级实践
- **"Data Parallel C++"** (James Reinders et al.) — SYCL/oneAPI 可移植 SIMD
- **sse2neon** (https://github.com/DLTcollab/sse2neon) — SSE intrinsic 自动转 NEON 的头文件，跨 ARM 移植利器
- **Compiler Explorer** (godbolt.org) — 写 SIMD 代码的必备工具：即时查看汇编输出，验证向量化
- **UE5 Math/UnrealMathSSE.h** — Unreal Engine 的 SIMD 数学实现，工业级参考
- **DirectXMath** (Microsoft) — Windows/xbox 上的 SIMD 数学库，头文件即库

---

## 常见陷阱

### 陷阱 1：`_mm_set_ps` 参数顺序与直觉相反

```cpp
// ❌ 错误：以为 set_ps(x,y,z,w) → [x,y,z,w]
// 实际参数顺序：set_ps(最高位, ..., 最低位) = set_ps(w, z, y, x)
__m128 v = _mm_set_ps(1, 2, 3, 4);  // v = [4, 3, 2, 1]

// ✅ 正确：用 _mm_setr_ps（reverse 顺序）
__m128 v = _mm_setr_ps(1, 2, 3, 4); // v = [1, 2, 3, 4]

// 或显式注释
__m128 v = _mm_set_ps(/*w*/0, /*z*/3, /*y*/2, /*x*/1); // v = [1,2,3,0]
```

### 陷阱 2：未对齐的 load 导致崩溃

```cpp
float data[8];  // 栈上数组，不保证 16 字节对齐
__m128 v = _mm_load_ps(data);  // ❌ 可能 SIGSEGV

// ✅ 两个方案：
// 方案 1：显式对齐
alignas(16) float data[8];

// 方案 2：使用 unaligned load（推荐，除非有对齐保证）
__m128 v = _mm_loadu_ps(data);

// 注意：现代 CPU 上 _mm_loadu_ps 的性能损失极小（Haswell+），
// 但 _mm_load_ps 在未对齐时直接崩溃——安全 > 微优化
```

### 陷阱 3：混用 SSE 和 AVX 导致状态切换惩罚

```cpp
// ❌ 在 AVX 函数中混用 SSE intrinsic
__m256 a = _mm256_add_ps(x, y);   // AVX（写 ymm）
__m128 b = _mm_add_ps(c, d);      // SSE（写 xmm 低 128 位）
// CPU 需要保存/恢复 ymm 寄存器的高 128 位 → 状态切换惩罚

// ✅ 两种方案：
// 方案 1：保持一致——使用 _mm256 全家桶
// 方案 2：在过渡点调用 _mm256_zeroupper() 清零 ymm 高位
__m256 a = _mm256_add_ps(x, y);
_mm256_zeroupper();                // 告诉 CPU "我不再用 ymm 了"
__m128 b = _mm_add_ps(c, d);
```

### 陷阱 4：认为 SIMD 总是更快

```cpp
// ❌ 对小数据量用 SIMD——设置开销 > 计算收益
alignas(16) float arr[4] = {1, 2, 3, 4};
__m128 v = _mm_load_ps(arr);
v = _mm_add_ps(v, v);    // 2 条指令，但标量也是 4 条指令
_mm_store_ps(arr, v);    // load+store 的开销可能抵消 SIMD 优势

// ✅ SIMD 收益来源于批量——处理数百/数千/数百万元素时
for (int i = 0; i < 1000000; i += 4) {
    // 每次处理 4 个元素，1000000/4 = 250000 次迭代
}
```

### 陷阱 5：忽视可移植性 —— 绑定单一指令集

```cpp
// ❌ 硬编码 AVX
__m256 data = _mm256_load_ps(ptr);
data = _mm256_fmadd_ps(data, scale, bias);  // FMA 需要 AVX2+Haswell

// ✅ 提供回退路径
template<typename T>
T simd_madd(T data, T scale, T bias) {
    #if defined(__AVX2__) && defined(__FMA__)
        return _mm256_fmadd_ps(data, scale, bias);
    #elif defined(__SSE__)
        return _mm_add_ps(_mm_mul_ps(data, scale), bias);
    #else
        // 标量回退
        return data * scale + bias;
    #endif
}
```

**引擎级方案**：使用 `std::experimental::simd` (C++26 的 Parallelism TS v2) 或直接使用像 DirectXMath 这样已处理好跨平台的数学库。自己封装 intrinsic 是巨大的维护负担。
