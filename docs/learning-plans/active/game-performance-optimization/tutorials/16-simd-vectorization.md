---
title: "SIMD 与向量化入门"
updated: 2026-06-05
---

# SIMD 与向量化入门
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: C++ 基础、数据布局基础（第 13 课）
---
## 1. 概念讲解

### 为什么需要这个？

CPU 执行一条标量（scalar）加法指令，产生**一个**结果。SIMD（Single Instruction, Multiple Data）执行一条指令，同时对**多个**数据元素做相同的操作。

```
标量：ADD a, b  →  1 个结果
SIMD：ADD [a0,a1,a2,a3], [b0,b1,b2,b3]  →  4 个结果，同时产生
```

对于游戏开发中大量重复的数学运算——向量归一化、矩阵乘法、顶点变换、颜色混合——SIMD 可以让你用同样的时钟周期做 4 倍（SSE）、8 倍（AVX）、甚至 16 倍（AVX-512）的工作。

**一个具体例子**：你有 100 万个 3D 顶点，每个需要 `transform = matrix * vertex`（4×4 矩阵 × 4D 向量）。标量版需要 `4 × 4 = 16` 次乘法 + `4 × 3 = 12` 次加法 = 28 次运算/顶点。SSE 版可以在 4 次 `_mm_mul_ps` + 3 次 `_mm_add_ps` + 一些 shuffle 中完成 → **接近 4x 加速**。

### 核心思想

#### SIMD 寄存器宽度

| 指令集 | 寄存器宽度 | 可同时处理的 float | 可同时处理的 int32 | 引入年份 |
|--------|-----------|-------------------|-------------------|---------|
| SSE  | 128-bit (XMM) | 4 | 4 | 1999 |
| AVX  | 256-bit (YMM) | 8 | 8 | 2011 |
| AVX-512 | 512-bit (ZMM) | 16 | 16 | 2016 |
| NEON (ARM) | 128-bit (Q) | 4 | 4 | 2011 |

**游戏引擎的现状**：
- PC 游戏：SSE2 是 baseline（x86-64 保证支持），AVX/AVX2 广泛可用
- 主机（PS4/Xbox One）：SSE-like 128-bit
- 主机（PS5/Xbox Series）：AVX2 256-bit
- 移动端（iOS/Android）：NEON 128-bit（所有 ARMv8 设备）

#### 三种使用方式

**1. 手写 Intrinsics（内联函数）**

```cpp
#include <xmmintrin.h>  // SSE
__m128 a = _mm_set_ps(1.0f, 2.0f, 3.0f, 4.0f);
__m128 b = _mm_set_ps(5.0f, 6.0f, 7.0f, 8.0f);
__m128 c = _mm_add_ps(a, b);  // [6, 8, 10, 12]
```

优点：完全控制。缺点：不可移植、代码难读。

**2. 编译器自动向量化**

```cpp
// 编译器可能自动转为 SIMD 的循环
for (int i = 0; i < n; ++i) {
    c[i] = a[i] + b[i];
}
```

编译器自动向量化的前提：
- 循环次数在编译时已知（或可推测）
- 没有循环间依赖（iteration N 不依赖 iteration N-1 的结果）
- 没有指针别名问题（`restrict`/`__restrict` 关键字）
- 数据对齐（`alignas(16)` 等）
- 循环体足够简单

**3. 包装库**

引擎通常封装自己的 SIMD 抽象：
- UE: `VectorRegister`（`FVector4` 的 SIMD 实现）
- Unity Burst: 自动从 C# 生成优化 SIMD 代码
- DirectXMath / GLM: 数学库内置 SIMD

#### 数据对齐

SIMD 加载指令要求数据地址对齐到寄存器宽度的倍数：
- SSE 需要 16 字节对齐（`_mm_load_ps` 是 aligned load）
- 未对齐加载（`_mm_loadu_ps`）比对齐加载慢约 20-50%
- AVX 对齐到 32 字节

```cpp
struct alignas(16) Vec4 { float x, y, z, w; };  // 确保 16 字节对齐
```

#### 游戏中的典型 SIMD 场景

| 场景 | SIMD 操作 | 加速比 |
|------|----------|--------|
| 向量归一化（批量） | `_mm_rsqrt_ps` + `_mm_mul_ps` | 3-4x |
| 4×4 矩阵乘法 | `_mm_mul_ps` + `_mm_add_ps` + shuffle | 2-3x |
| AABB 变换（8 个顶点） | 8 次矩阵×点，部分结果复用 | 3-4x |
| 颜色混合（RGBA） | 单条 `_mm_add_ps` | 4x |
| 动画骨骼蒙皮 | SSE 批量处理 4 个顶点 | 3-4x |
| 粒子更新 | 批量位置+=速度（SoA 布局配合 SIMD） | 4-8x |
| 音频混音（批量加法） | SSE/AVX 批量 mix | 4-8x |

---

## 2. 代码示例

以下代码实现：(A) 批量 vec4 点积的 SSE 版本 (B) 4×4 矩阵乘法的 SSE 版本，并与标量版对比。

**编译命令**：
```bash
# Linux/macOS (需要 -msse 或 -msse2 — x86-64 默认开启):
g++ -std=c++17 -O2 -msse2 -o simd_bench simd_bench.cpp

# Windows (MSVC 自动启用 SSE2):
cl /std:c++17 /O2 /arch:SSE2 /EHsc simd_bench.cpp

# 查看生成的汇编（验证 SIMD 指令）:
g++ -std=c++17 -O2 -msse2 -S -o simd_bench.s simd_bench.cpp
# 在 simd_bench.s 中搜索: mulps, addps, movaps 等 SSE 指令
```

```cpp
// simd_bench.cpp — SSE SIMD vs Scalar 性能对比
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <iomanip>
#include <random>
#include <vector>

// SSE 头文件
#include <xmmintrin.h>  // SSE
#include <emmintrin.h>  // SSE2

// ============================================================================
// 辅助
// ============================================================================

class Timer {
    using Clock = std::chrono::high_resolution_clock;
    Clock::time_point start_;
    const char* name_;
public:
    Timer(const char* name) : name_(name), start_(Clock::now()) {}
    ~Timer() {
        auto end = Clock::now();
        double ms = std::chrono::duration<double, std::milli>(end - start_).count();
        std::cout << "  [" << name_ << "] " << std::fixed << std::setprecision(3)
                  << ms << " ms" << std::endl;
    }
};

// ============================================================================
// 数据结构
// ============================================================================

struct alignas(16) Vec4 {
    float x, y, z, w;
};

struct alignas(16) Mat4 {
    // 列主序存储（适合 SIMD 矩阵×向量）
    Vec4 col[4];
};

// ============================================================================
// Part A: 批量 Vec4 点积
// ============================================================================

// 标量版: vec4 dot product
float ScalarDot(const Vec4& a, const Vec4& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;
}

// SSE 版: 单次 dot product
float SSEDot(__m128 a, __m128 b) {
    // _mm_mul_ps:   [a0*b0, a1*b1, a2*b2, a3*b3]
    // _mm_hadd_ps:  水平加法 [a0*b0+a1*b1, a2*b2+a3*b3, x, x]
    // 再 hadd 一次: [a0*b0+a1*b1+a2*b2+a3*b3, x, x, x]
    __m128 mul = _mm_mul_ps(a, b);
    __m128 hadd = _mm_hadd_ps(mul, mul);
    __m128 result = _mm_hadd_ps(hadd, hadd);
    return _mm_cvtss_f32(result);  // 提取最低 float
}

// 批量点积 — 标量版
void ScalarBatchDot(const Vec4* a, const Vec4* b, float* result, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        result[i] = ScalarDot(a[i], b[i]);
    }
}

// 批量点积 — SSE 版
void SSEBatchDot(const Vec4* a, const Vec4* b, float* result, size_t count) {
    size_t i = 0;
    for (; i + 3 < count; i += 4) {
        // 加载 4 个 Vec4 为一组
        // A0..A3:  a[i].x, a[i].y, a[i].z, a[i].w ~ a[i+3].x, a[i+3].y...
        // 用 SSE 同时处理 4 个 dot product
        // 这是一种简化的广播策略：
        //   对每个分量做乘法再累加
        __m128 ax = _mm_set_ps(a[i+3].x, a[i+2].x, a[i+1].x, a[i].x);
        __m128 bx = _mm_set_ps(b[i+3].x, b[i+2].x, b[i+1].x, b[i].x);
        __m128 sum = _mm_mul_ps(ax, bx);

        __m128 ay = _mm_set_ps(a[i+3].y, a[i+2].y, a[i+1].y, a[i].y);
        __m128 by = _mm_set_ps(b[i+3].y, b[i+2].y, b[i+1].y, b[i].y);
        sum = _mm_add_ps(sum, _mm_mul_ps(ay, by));

        __m128 az = _mm_set_ps(a[i+3].z, a[i+2].z, a[i+1].z, a[i].z);
        __m128 bz = _mm_set_ps(b[i+3].z, b[i+2].z, b[i+1].z, b[i].z);
        sum = _mm_add_ps(sum, _mm_mul_ps(az, bz));

        __m128 aw = _mm_set_ps(a[i+3].w, a[i+2].w, a[i+1].w, a[i].w);
        __m128 bw = _mm_set_ps(b[i+3].w, b[i+2].w, b[i+1].w, b[i].w);
        sum = _mm_add_ps(sum, _mm_mul_ps(aw, bw));

        _mm_storeu_ps(&result[i], sum);
    }
    // 尾部余量用标量
    for (; i < count; ++i) {
        result[i] = ScalarDot(a[i], b[i]);
    }
}

// 批量点积 — SSE 优化版（使用 SoA 布局避免 gather）
// 输入: float* ax, ay, az, aw 是分量的连续数组（SoA）
void SSEBatchDot_SoA(const float* ax, const float* ay, const float* az, const float* aw,
                     const float* bx, const float* by, const float* bz, const float* bw,
                     float* result, size_t count) {
    size_t i = 0;
    for (; i + 3 < count; i += 4) {
        // 直接加载连续的 4 个 float → 单条 movaps 指令
        __m128 ax4 = _mm_loadu_ps(&ax[i]);
        __m128 bx4 = _mm_loadu_ps(&bx[i]);
        __m128 sum = _mm_mul_ps(ax4, bx4);

        __m128 ay4 = _mm_loadu_ps(&ay[i]);
        __m128 by4 = _mm_loadu_ps(&by[i]);
        sum = _mm_add_ps(sum, _mm_mul_ps(ay4, by4));

        __m128 az4 = _mm_loadu_ps(&az[i]);
        __m128 bz4 = _mm_loadu_ps(&bz[i]);
        sum = _mm_add_ps(sum, _mm_mul_ps(az4, bz4));

        __m128 aw4 = _mm_loadu_ps(&aw[i]);
        __m128 bw4 = _mm_loadu_ps(&bw[i]);
        sum = _mm_add_ps(sum, _mm_mul_ps(aw4, bw4));

        _mm_storeu_ps(&result[i], sum);
    }
    for (; i < count; ++i) {
        result[i] = ax[i]*bx[i] + ay[i]*by[i] + az[i]*bz[i] + aw[i]*bw[i];
    }
}

// ============================================================================
// Part B: 4×4 矩阵乘法
// ============================================================================

// 标量版
void ScalarMat4Mul(const Mat4& A, const Mat4& B, Mat4& C) {
    for (int row = 0; row < 4; ++row) {
        for (int col = 0; col < 4; ++col) {
            float sum = 0.0f;
            for (int k = 0; k < 4; ++k) {
                sum += reinterpret_cast<const float*>(&A.col[k])[row]
                     * reinterpret_cast<const float*>(&B.col[col])[k];
            }
            reinterpret_cast<float*>(&C.col[col])[row] = sum;
        }
    }
}

// SSE 版 — 用 _mm_mul_ps + _mm_add_ps 计算
// 策略: B 的列 × A 的行的缩放因子
void SSEMat4Mul(const Mat4& A, const Mat4& B, Mat4& C) {
    // A 的列加载为 __m128
    __m128 A0 = _mm_load_ps(&A.col[0].x); // A 的第 0 行（按列主序，col0 的 4 个分量是一行）
    __m128 A1 = _mm_load_ps(&A.col[1].x);
    __m128 A2 = _mm_load_ps(&A.col[2].x);
    __m128 A3 = _mm_load_ps(&A.col[3].x);

    for (int col = 0; col < 4; ++col) {
        // 加载 B 的一列
        __m128 Bcol = _mm_load_ps(&B.col[col].x);

        // C.col[col] = A0 * Bcol[0] + A1 * Bcol[1] + A2 * Bcol[2] + A3 * Bcol[3]
        // _mm_set1_ps 把 Bcol 的一个分量广播到全寄存器的 4 个 lane
        __m128 t0 = _mm_mul_ps(A0, _mm_set1_ps(reinterpret_cast<const float*>(&Bcol)[0]));
        __m128 t1 = _mm_mul_ps(A1, _mm_set1_ps(reinterpret_cast<const float*>(&Bcol)[1]));
        __m128 t2 = _mm_mul_ps(A2, _mm_set1_ps(reinterpret_cast<const float*>(&Bcol)[2]));
        __m128 t3 = _mm_mul_ps(A3, _mm_set1_ps(reinterpret_cast<const float*>(&Bcol)[3]));

        __m128 res = _mm_add_ps(_mm_add_ps(t0, t1), _mm_add_ps(t2, t3));
        _mm_store_ps(&C.col[col].x, res);
    }
}

// 批量矩阵乘法 — 标量
void ScalarBatchMat4Mul(const Mat4* A, const Mat4* B, Mat4* C, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        ScalarMat4Mul(A[i], B[i], C[i]);
    }
}

// 批量矩阵乘法 — SSE
void SSEBatchMat4Mul(const Mat4* A, const Mat4* B, Mat4* C, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        SSEMat4Mul(A[i], B[i], C[i]);
    }
}

// ============================================================================
// Part C: 向量归一化（常见于骨骼动画、物理）
// ============================================================================

// 标量版：归一化一个 Vec4 的 xyz（w 忽略）
void ScalarNormalize(Vec4& v) {
    float len = std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
    if (len > 1e-8f) {
        float inv = 1.0f / len;
        v.x *= inv; v.y *= inv; v.z *= inv;
    }
}

// SSE 版：一次归一化 4 个向量的 xyz
// 输入: 4 个 Vec4 组成的 SoA 数据（4 个 x, 4 个 y, 4 个 z）
void SSENormalize4(float* x4, float* y4, float* z4) {
    __m128 xs = _mm_loadu_ps(x4);
    __m128 ys = _mm_loadu_ps(y4);
    __m128 zs = _mm_loadu_ps(z4);

    // len² = x² + y² + z²
    __m128 len_sq = _mm_add_ps(
        _mm_add_ps(_mm_mul_ps(xs, xs), _mm_mul_ps(ys, ys)),
        _mm_mul_ps(zs, zs));

    // 1/sqrt(len²) — SSE 的快速倒数平方根（精度 ~12 bit）
    // _mm_rsqrt_ps 比 _mm_sqrt_ps + 除法快得多
    __m128 inv_len = _mm_rsqrt_ps(len_sq);

    // 可选：一次 Newton-Raphson 迭代提高精度到 ~23 bit
    // inv_len = _mm_mul_ps(
    //     _mm_mul_ps(_mm_set1_ps(0.5f), inv_len),
    //     _mm_sub_ps(_mm_set1_ps(3.0f),
    //         _mm_mul_ps(_mm_mul_ps(len_sq, inv_len), inv_len)));

    _mm_storeu_ps(x4, _mm_mul_ps(xs, inv_len));
    _mm_storeu_ps(y4, _mm_mul_ps(ys, inv_len));
    _mm_storeu_ps(z4, _mm_mul_ps(zs, inv_len));
}

void ScalarNormalizeBatch(Vec4* vecs, size_t count) {
    for (size_t i = 0; i < count; ++i) ScalarNormalize(vecs[i]);
}

void SSENormalizeBatch(Vec4* vecs, size_t count) {
    size_t i = 0;
    for (; i + 3 < count; i += 4) {
        float x4[4] = {vecs[i].x, vecs[i+1].x, vecs[i+2].x, vecs[i+3].x};
        float y4[4] = {vecs[i].y, vecs[i+1].y, vecs[i+2].y, vecs[i+3].y};
        float z4[4] = {vecs[i].z, vecs[i+1].z, vecs[i+2].z, vecs[i+3].z};
        SSENormalize4(x4, y4, z4);
        for (int j = 0; j < 4; ++j) {
            vecs[i+j].x = x4[j];
            vecs[i+j].y = y4[j];
            vecs[i+j].z = z4[j];
        }
    }
    for (; i < count; ++i) ScalarNormalize(vecs[i]);
}

// ============================================================================
// main
// ============================================================================

int main() {
    constexpr size_t VEC_COUNT   = 1'000'000;
    constexpr size_t MAT_COUNT   = 500'000;
    constexpr size_t NORM_COUNT  = 500'000;
    constexpr int    ITERATIONS  = 10;

    std::cout << "=== SIMD (SSE) vs Scalar Benchmark ===" << std::endl;
    std::cout << "Vec4 count: " << VEC_COUNT
              << " | Mat4 count: " << MAT_COUNT
              << " | Normalize count: " << NORM_COUNT << std::endl;
    std::cout << "Iterations: " << ITERATIONS << std::endl;

    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-10.0f, 10.0f);

    // ===== 准备数据 =====
    std::vector<Vec4> avec(VEC_COUNT), bvec(VEC_COUNT);
    std::vector<float> result(VEC_COUNT);
    for (size_t i = 0; i < VEC_COUNT; ++i) {
        avec[i] = {dist(rng), dist(rng), dist(rng), dist(rng)};
        bvec[i] = {dist(rng), dist(rng), dist(rng), dist(rng)};
    }

    // SoA 数据（分量拆分）
    std::vector<float> ax(VEC_COUNT), ay(VEC_COUNT), az(VEC_COUNT), aw(VEC_COUNT);
    std::vector<float> bx(VEC_COUNT), by(VEC_COUNT), bz(VEC_COUNT), bw(VEC_COUNT);
    for (size_t i = 0; i < VEC_COUNT; ++i) {
        ax[i] = avec[i].x; ay[i] = avec[i].y; az[i] = avec[i].z; aw[i] = avec[i].w;
        bx[i] = bvec[i].x; by[i] = bvec[i].y; bz[i] = bvec[i].z; bw[i] = bvec[i].w;
    }

    // 矩阵数据
    std::vector<Mat4> matA(MAT_COUNT), matB(MAT_COUNT), matC(MAT_COUNT);
    for (size_t i = 0; i < MAT_COUNT; ++i) {
        for (int c = 0; c < 4; ++c) {
            matA[i].col[c] = {dist(rng), dist(rng), dist(rng), dist(rng)};
            matB[i].col[c] = {dist(rng), dist(rng), dist(rng), dist(rng)};
        }
    }

    // 归一化数据
    std::vector<Vec4> norm_vecs(NORM_COUNT);
    for (size_t i = 0; i < NORM_COUNT; ++i) {
        norm_vecs[i] = {dist(rng), dist(rng), dist(rng), 0.0f};
    }

    volatile float sink = 0.0f;

    // ===== Benchmark: Vec4 Dot Product =====
    std::cout << "\n--- Vec4 Dot Product (AoS layout) ---" << std::endl;
    {
        Timer t("Scalar");
        for (int iter = 0; iter < ITERATIONS; ++iter)
            ScalarBatchDot(avec.data(), bvec.data(), result.data(), VEC_COUNT);
        sink = result[0];
    }
    {
        Timer t("SSE (AoS→gather)");
        for (int iter = 0; iter < ITERATIONS; ++iter)
            SSEBatchDot(avec.data(), bvec.data(), result.data(), VEC_COUNT);
        sink = result[0];
    }

    std::cout << "\n--- Vec4 Dot Product (SoA layout) ---" << std::endl;
    {
        Timer t("SSE SoA (contiguous load)");
        for (int iter = 0; iter < ITERATIONS; ++iter)
            SSEBatchDot_SoA(ax.data(), ay.data(), az.data(), aw.data(),
                           bx.data(), by.data(), bz.data(), bw.data(),
                           result.data(), VEC_COUNT);
        sink = result[0];
    }

    // ===== Benchmark: Mat4 × Mat4 =====
    std::cout << "\n--- 4x4 Matrix Multiplication ---" << std::endl;
    {
        Timer t("Scalar");
        for (int iter = 0; iter < ITERATIONS; ++iter)
            ScalarBatchMat4Mul(matA.data(), matB.data(), matC.data(), MAT_COUNT);
        sink = matC[0].col[0].x;
    }
    {
        Timer t("SSE");
        for (int iter = 0; iter < ITERATIONS; ++iter)
            SSEBatchMat4Mul(matA.data(), matB.data(), matC.data(), MAT_COUNT);
        sink = matC[0].col[0].x;
    }

    // ===== Benchmark: Vector Normalize =====
    std::cout << "\n--- Vector Normalize (xyz) ---" << std::endl;
    {
        Timer t("Scalar");
        for (int iter = 0; iter < ITERATIONS; ++iter)
            ScalarNormalizeBatch(norm_vecs.data(), NORM_COUNT);
        sink = norm_vecs[0].x;
    }
    {
        Timer t("SSE (4 at a time, rsqrt)");
        for (int iter = 0; iter < ITERATIONS; ++iter)
            SSENormalizeBatch(norm_vecs.data(), NORM_COUNT);
        sink = norm_vecs[0].x;
    }
    (void)sink;

    // ===== 正确性验证 =====
    std::cout << "\n--- 正确性验证 ---" << std::endl;
    // Dot product 验证
    Vec4 va = {1.0f, 2.0f, 3.0f, 4.0f};
    Vec4 vb = {5.0f, 6.0f, 7.0f, 8.0f};
    float sd = ScalarDot(va, vb);
    float ss = SSEDot(_mm_load_ps(&va.x), _mm_load_ps(&vb.x));
    std::cout << "Dot product: scalar=" << sd << " sse=" << ss
              << " match=" << (std::abs(sd-ss) < 0.001f ? "YES" : "NO") << std::endl;

    std::cout << "\n=== 汇编检查提示 ===" << std::endl;
    std::cout << "编译后用以下命令确认 SIMD 指令生成:" << std::endl;
    std::cout << "  objdump -d simd_bench | grep -E 'mulps|addps|movaps|rsqrtps'" << std::endl;
    std::cout << "或查看生成的 .s 文件搜索 SIMD 操作码" << std::endl;

    return 0;
}
```

**预期输出示例**：
```
=== SIMD (SSE) vs Scalar Benchmark ===
Vec4 count: 1000000 | Mat4 count: 500000 | Normalize count: 500000
Iterations: 10

--- Vec4 Dot Product (AoS layout) ---
  [Scalar]           4.823 ms
  [SSE (AoS→gather)] 3.105 ms     ← gather 消耗了部分收益

--- Vec4 Dot Product (SoA layout) ---
  [SSE SoA (contiguous load)] 1.245 ms  ← 连续的 load 才是真正的 SIMD 峰值

--- 4x4 Matrix Multiplication ---
  [Scalar]          8.912 ms
  [SSE]             3.341 ms     ← ~2.7x 加速

--- Vector Normalize (xyz) ---
  [Scalar]          5.678 ms
  [SSE (4 at a time, rsqrt)] 1.512 ms  ← ~3.8x 加速（rsqrt 比 sqrt+div 快很多）
```

关键观察：AoS 布局下的 SSE 版本需要 `_mm_set_ps` 来 gather 分散的数据——这本身就有开销。SoA 布局配合 `_mm_loadu_ps` 连续加载才是真正的 SIMD 峰值性能。**数据布局决定 SIMD 收益**。

---

## 3. 练习

### 练习 1: [基础] 分析编译器自动向量化

编写一个简单的循环：

```cpp
void add_arrays(const float* a, const float* b, float* c, size_t n) {
    for (size_t i = 0; i < n; ++i) c[i] = a[i] + b[i];
}
```

用不同编译选项编译并检查生成的汇编：

```bash
g++ -O2 -S -o novec.s add.cpp         # 可能不向量化
g++ -O2 -ftree-vectorize -S -o vec.s add.cpp   # 尝试向量化
g++ -O3 -march=native -S -o native.s add.cpp   # 针对本机 CPU
```

记录每次生成的汇编中有哪些 SIMD 指令。如果编译器没有自动向量化，分析原因（是否缺 `restrict`？有无别名问题？）。

### 练习 2: [进阶] 实现 AABB 变换的 SSE 优化

一个 AABB（轴对齐包围盒）由 `min` 和 `max` 两个 `Vec3` 表示。当 AABB 被一个 `Mat4` 变换时，需要把 AABB 的 8 个顶点都乘以矩阵，然后取 min/max。

1. 实现标量版 AABB 变换
2. 实现 SSE 版 AABB 变换（利用 SSE 同时处理 4 个分量）
3. Benchmark 对比（批量 100K 个 AABB）

提示：AABB 的 8 个顶点可以通过组合 min/max 的各分量构造，不需要逐一计算。

### 练习 3: [挑战] 用 AVX 实现 8 路并行粒子更新

将第 13 课的粒子系统 SoA 更新用 AVX（256-bit）改写。注意：
- AVX 一次处理 8 个 float（不是 SSE 的 4 个）
- 需要 `#include <immintrin.h>`
- 编译器选项需要 `-mavx` 或 `-mavx2`
- Benchmark 对比 SSE（4 路）和 AVX（8 路）

---

## 4. 扩展阅读

| 资源 | 说明 |
|------|------|
| Intel Intrinsics Guide | 在线工具，搜索 intrinsics 函数、延迟、吞吐量 |
| *SIMD at Insomniac Games* (GDC 2015) | Insomniac 如何在 Ratchet & Clank 中使用 SIMD 优化渲染/物理 |
| Agner Fog's optimization manuals | 权威的指令延迟表、微架构细节 |
| DirectXMath 源码 (GitHub: microsoft/DirectXMath) | 工业级 SIMD 数学库，大量 SSE/AVX 实践 |
| Unity Burst Compiler 文档 | 如何从 C# 生成 SIMD 代码 |
| *Computer Architecture: A Quantitative Approach* 第 4 章 | SIMD 的硬件原理和设计思想 |
| UE5 VectorRegister 源码 | UE 的 SIMD 抽象层实现 |
| `__builtin_expect`, `#pragma GCC ivdep` 等编译器提示 | 辅助编译器做更好的向量化决策 |

---

## 常见陷阱

| 陷阱 | 说明 | 纠正方法 |
|------|------|----------|
| **AoS 布局 + SIMD = gather 开销** | `_mm_set_ps(a[i].x, a[i+1].x, ...)` 需要 4 次标量加载 + 组合 | 转 SoA，用 `_mm_load_ps` 一次加载 4 个连续值 |
| **忘记对齐** | `_mm_load_ps` 在未对齐地址上会崩溃（SIGSEGV） | 用 `alignas(16)` 确保对齐，或用 `_mm_loadu_ps` |
| **`_mm_rsqrt_ps` 精度不足** | `rsqrtps` 精度只有 ~12 bit，累积在物理模拟中可能漂移 | 重要场景用 `_mm_sqrt_ps` + `_mm_div_ps`，或加一次 Newton-Raphson |
| **在循环内 shuffle 数据** | `_mm_shuffle_ps` 在热循环中频繁使用会影响吞吐 | 提前布局数据，让 SIMD 操作都是 straight-line |
| **SSE 和 AVX 混用导致状态切换** | 从 SSE（128-bit）切换到 AVX（256-bit）时 CPU 有 ~100 周期惩罚 | 整个函数要么全用 SSE，要么全用 AVX；使用 `_mm256_zeroupper` |
| **假设 SIMD 总比标量快** | 数据量小、分支复杂、频繁 gather/scatter 时，SIMD 可能更慢 | 只在批量操作（>1000 元素）中使用 SIMD |
