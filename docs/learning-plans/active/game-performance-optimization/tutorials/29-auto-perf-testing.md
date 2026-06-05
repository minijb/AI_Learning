---
title: "自动化性能测试与回归检测"
updated: 2026-06-05
---

# 自动化性能测试与回归检测
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45 分钟
> 前置知识: 性能测量方法学（第 2 节）、基本 CI/CD 概念、Python 脚本基础
---
## 1. 概念讲解

### 为什么需要这个？

你花了一周优化粒子系统，帧时间从 18ms 降到 12ms。提交代码。两周后，有人加了一个"水面反射"功能，帧时间悄悄回到了 17ms。没人注意到，因为没人手动跑帧分析——直到玩家在论坛抱怨"更新后变卡了"。

手动 Profiling 无法规模化。一个 20 人的团队每周可能有 200+ 次提交，你不可能每次提交后都打开 RenderDoc 手动捕获一帧。

**自动化性能测试**让 CI（持续集成）系统在每次提交后自动运行基准测试，检测帧时间、内存、Draw Call 数量是否超出了预设的阈值。如果超出，CI 构建失败，提交者必须在合并前修复或解释。

### 核心思想

自动化性能测试的架构分三层：

```
┌───────────────────────────────────────────────────────────────────┐
│ 第一层: 微基准测试 (Micro-benchmark)                               │
│ 使用 Google Benchmark / Catch2-Benchmark                           │
│ 测试单个函数/算法的性能（如: TransformUpdate 的吞吐量）             │
│ 运行条件: 每次提交 (PR/MR)                                         │
│ 期望耗时: <1 分钟                                                   │
├───────────────────────────────────────────────────────────────────┤
│ 第二层: 帧级回放测试 (Frame-level Replay)                          │
│ 使用 RenderDoc Python API 或引擎内置录制回放                        │
│ 回放预先录制的帧序列，比较 GPU/CPU 时间                              │
│ 运行条件: 每次提交后 (Post-merge) 或 Nightly                        │
│ 期望耗时: <10 分钟                                                  │
├───────────────────────────────────────────────────────────────────┤
│ 第三层: 游戏场景端到端测试 (Scene-level E2E)                        │
│ 启动游戏构建，自动播放预设路径/输入，记录整个场景的帧时间            │
│ 运行条件: Nightly 或每周                                            │
│ 期望耗时: <1 小时                                                   │
└───────────────────────────────────────────────────────────────────┘
```

每一层有不同的精度/速度权衡。第一层最快但离真实场景最远，第三层最真实但最慢。

**为什么需要统计方法？**

同一段代码跑两次，运行时间不会精确相等。原因：
- CPU 动态频率调节（Turbo Boost / thermal throttling）
- OS 调度器的不确定性
- 其他进程的干扰
- 缓存状态（冷启动 vs 热启动）

所以你不能简单比较"这次 10ms，上次 9ms → 慢了 10%"然后判定回归。你需要：
- **跑 N 次**（N ≥ 5，推荐 10-30）
- **丢弃异常值**（热身后前几次，或 OS 中断导致的尖峰）
- **统计显著性检验**（如 Mann-Whitney U 检验）

---
## 2. 代码示例

### 示例 1: Google Benchmark 微基准测试

Google Benchmark 是 C++ 中最广泛使用的微基准测试库。

```bash
# 安装 Google Benchmark
git clone https://github.com/google/benchmark.git
cd benchmark
cmake -B build -DCMAKE_BUILD_TYPE=Release -DBENCHMARK_ENABLE_TESTING=OFF
cmake --build build --config Release
# 头文件在 include/，库在 build/src/
```

```cpp
// engine_benchmarks.cpp — 关键引擎函数的微基准测试
#include <benchmark/benchmark.h>
#include <vector>
#include <random>
#include <algorithm>
#include <cmath>

// ================================================================
// 模拟游戏引擎中的真实数据结构
// ================================================================

struct alignas(64) TransformComponent {
    float posX, posY, posZ;
    float rotX, rotY, rotZ, rotW;
    float scaleX, scaleY, scaleZ;
    // padding to 64 bytes for cache-line alignment
    char _pad[12];
};
static_assert(sizeof(TransformComponent) == 64, "Cache line alignment");

struct TransformComponentSoA {
    std::vector<float> posX, posY, posZ;
    std::vector<float> rotX, rotY, rotZ, rotW;
    std::vector<float> scaleX, scaleY, scaleZ;
};

// 准备测试数据
std::vector<TransformComponent> GenerateAoSData(int count) {
    std::vector<TransformComponent> data(count);
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-100.0f, 100.0f);
    for (int i = 0; i < count; ++i) {
        data[i].posX = dist(rng);
        data[i].posY = dist(rng);
        data[i].posZ = dist(rng);
        data[i].rotX = dist(rng);
        data[i].rotY = dist(rng);
        data[i].rotZ = dist(rng);
        data[i].rotW = dist(rng);
    }
    return data;
}

TransformComponentSoA GenerateSoAData(int count) {
    TransformComponentSoA r;
    r.posX.resize(count); r.posY.resize(count); r.posZ.resize(count);
    r.rotX.resize(count); r.rotY.resize(count); r.rotZ.resize(count); r.rotW.resize(count);
    r.scaleX.resize(count); r.scaleY.resize(count); r.scaleZ.resize(count);
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-100.0f, 100.0f);
    for (int i = 0; i < count; ++i) {
        r.posX[i] = dist(rng); r.posY[i] = dist(rng); r.posZ[i] = dist(rng);
        r.rotX[i] = dist(rng); r.rotY[i] = dist(rng); r.rotZ[i] = dist(rng); r.rotW[i] = dist(rng);
    }
    return r;
}

// ================================================================
// 基准测试 1: Transform Update — AoS vs SoA
// ================================================================

// AoS 版本：遍历结构体数组，每帧更新位置（模拟刚体移动）
static void BM_TransformUpdate_AoS(benchmark::State &state) {
    int count = state.range(0);
    auto data = GenerateAoSData(count);
    const float dt = 1.0f / 60.0f;

    for (auto _ : state) {
        for (int i = 0; i < count; ++i) {
            // 模拟: position += velocity * dt
            // 这里简化：直接做浮点运算
            data[i].posX += data[i].rotX * dt;
            data[i].posY += data[i].rotY * dt;
            data[i].posZ += data[i].rotZ * dt;
            // 防止编译器优化掉整个循环
            benchmark::DoNotOptimize(data[i].posX);
        }
    }
    state.SetItemsProcessed(state.iterations() * count);
}

// SoA 版本：同样的计算，但数据布局不同
static void BM_TransformUpdate_SoA(benchmark::State &state) {
    int count = state.range(0);
    auto data = GenerateSoAData(count);
    const float dt = 1.0f / 60.0f;

    for (auto _ : state) {
        for (int i = 0; i < count; ++i) {
            data.posX[i] += data.rotX[i] * dt;
            data.posY[i] += data.rotY[i] * dt;
            data.posZ[i] += data.rotZ[i] * dt;
            benchmark::DoNotOptimize(data.posX[i]);
        }
    }
    state.SetItemsProcessed(state.iterations() * count);
}
BENCHMARK(BM_TransformUpdate_AoS)->Arg(1000)->Arg(10000)->Arg(100000);
BENCHMARK(BM_TransformUpdate_SoA)->Arg(1000)->Arg(10000)->Arg(100000);

// ================================================================
// 基准测试 2: Frustum Culling (视锥体裁剪)
// ================================================================

struct alignas(16) AABB {
    float minX, minY, minZ;
    float maxX, maxY, maxZ;
};

// 模拟平面数据（6 个视锥体平面，每个是 Normal + Distance）
struct Plane {
    float nx, ny, nz, d;
};

static Plane g_frustumPlanes[6] = {
    { 0.0f,  0.0f, -1.0f, 100.0f},  // Near
    { 0.0f,  0.0f,  1.0f,   0.0f},  // Far
    {-0.7f,  0.0f,  0.7f,   0.0f},  // Left
    { 0.7f,  0.0f,  0.7f,   0.0f},  // Right
    { 0.0f, -0.7f,  0.7f,   0.0f},  // Bottom
    { 0.0f,  0.7f,  0.7f,   0.0f},  // Top
};

// 基础实现：逐平面测试
static bool FrustumCull_Basic(const AABB &box) {
    for (int p = 0; p < 6; ++p) {
        const Plane &pl = g_frustumPlanes[p];
        // 找到 AABB 在平面法线方向上的最远点
        float furthest = box.minX * (pl.nx > 0 ? 1.0f : 0.0f) +
                         box.maxX * (pl.nx > 0 ? 0.0f : 1.0f);
        // ... 为简洁起见，这里用简化版本：
        // 测试 AABB 中心是否在平面正半空间
        float cx = (box.minX + box.maxX) * 0.5f;
        float cy = (box.minY + box.maxY) * 0.5f;
        float cz = (box.minZ + box.maxZ) * 0.5f;
        float dist = pl.nx * cx + pl.ny * cy + pl.nz * cz + pl.d;
        // 实际算法应使用 AABB 半径做保守测试，这里简化
        float r = (box.maxX - box.minX) * 0.5f * fabsf(pl.nx) +
                  (box.maxY - box.minY) * 0.5f * fabsf(pl.ny) +
                  (box.maxZ - box.minZ) * 0.5f * fabsf(pl.nz);
        if (dist + r < 0.0f) return false;  // 完全在平面外侧
    }
    return true;  // 可能与视锥体相交
}

// SIMD 友好的实现：对 4 个 AABB 同时测试
// 使用简单的标量循环批处理来模拟 (实际应使用 SSE/AVX intrinsics)
static void FrustumCull_Batched(const AABB *boxes, bool *results, int count) {
    for (int i = 0; i < count; ++i) {
        results[i] = FrustumCull_Basic(boxes[i]);
    }
}

static void BM_FrustumCull_Single(benchmark::State &state) {
    int count = state.range(0);
    std::vector<AABB> boxes(count);
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-50.0f, 50.0f);
    for (int i = 0; i < count; ++i) {
        float cx = dist(rng), cy = dist(rng), cz = dist(rng);
        boxes[i] = {cx - 1, cy - 1, cz - 1, cx + 1, cy + 1, cz + 1};
    }

    int visible = 0;
    for (auto _ : state) {
        visible = 0;
        for (int i = 0; i < count; ++i) {
            if (FrustumCull_Basic(boxes[i])) ++visible;
        }
        benchmark::DoNotOptimize(visible);
    }
    state.SetItemsProcessed(state.iterations() * count);
}

BENCHMARK(BM_FrustumCull_Single)->Arg(1000)->Arg(10000);

// ================================================================
// 基准测试 3: 粒子模拟 — 使用 Google Benchmark 的 Fixture
// ================================================================

class ParticleSimBench : public benchmark::Fixture {
protected:
    struct Particle {
        float x, y, z;
        float vx, vy, vz;
        float life;
    };
    std::vector<Particle> particles;

public:
    void SetUp(const benchmark::State &st) override {
        int count = st.range(0);
        particles.resize(count);
        std::mt19937 rng(42);
        std::uniform_real_distribution<float> pos(-10.0f, 10.0f);
        std::uniform_real_distribution<float> vel(-1.0f, 1.0f);
        for (int i = 0; i < count; ++i) {
            particles[i] = {pos(rng), pos(rng), pos(rng),
                            vel(rng), vel(rng), vel(rng), 1.0f};
        }
    }

    void TearDown(const benchmark::State &) override {
        particles.clear();
    }
};

BENCHMARK_DEFINE_F(ParticleSimBench, Update)(benchmark::State &st) {
    const float dt = 1.0f / 60.0f;
    const float gravity = -9.8f;
    int alive = 0;

    for (auto _ : st) {
        alive = 0;
        for (auto &p : particles) {
            if (p.life <= 0.0f) continue;
            p.vx += 0.0f * dt;  // wind (none for now)
            p.vy += gravity * dt;
            p.vz += 0.0f * dt;
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            p.z += p.vz * dt;
            p.life -= dt;
            ++alive;
        }
        benchmark::DoNotOptimize(alive);
    }
    st.SetItemsProcessed(st.iterations() * particles.size());
}
BENCHMARK_REGISTER_F(ParticleSimBench, Update)->Arg(1000)->Arg(10000)->Arg(100000);

// ================================================================
// 主函数
// ================================================================
BENCHMARK_MAIN();
```

```bash
# 编译并运行基准测试
cmake -B build_bench -DCMAKE_BUILD_TYPE=Release
cmake --build build_bench --config Release

# 运行所有基准测试，输出 JSON 结果
./build_bench/engine_benchmarks \
    --benchmark_out=results.json \
    --benchmark_out_format=json \
    --benchmark_repetitions=10 \
    --benchmark_report_aggregates_only=true

# 与上次基线比较
./build_bench/engine_benchmarks \
    --benchmark_out=results_new.json \
    --benchmark_out_format=json
# 然后用 Python 脚本比较 results_baseline.json vs results_new.json

# Google Benchmark 也支持基准测试间比较:
# python3 compare.py benchmarks results_baseline.json results_new.json
# （compare.py 随 Google Benchmark 一起发布在 tools/ 目录下）
```

### 示例 2: Python 帧时间统计比较脚本

以下脚本读取游戏运行时输出的帧时间日志，运行统计检验判断是否有性能回归：

```python
#!/usr/bin/env python3
"""
perf_regression_test.py — 自动化性能回归检测
读取游戏构建输出的帧时间日志，运行统计比较。

输入格式: CSV, 每行一个帧时间（毫秒）
    例如:
    frame,dt_ms
    1,16.67
    2,16.45
    ...

用法:
    python3 perf_regression_test.py --baseline baseline.csv --current current.csv --threshold 0.05
"""
import argparse
import csv
import sys
import math
from pathlib import Path

# ---------------------------------------------------------------
# 统计工具函数
# ---------------------------------------------------------------

def load_frame_times(csv_path: str, skip_warmup_frames: int = 60) -> list[float]:
    """
    从 CSV 加载帧时间数据。
    默认跳过前 60 帧（warmup: 场景加载、shader 编译等初始化开销）。
    """
    times = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            times.append(float(row.get('dt_ms', row.get('frame_time_ms', 0))))
    if len(times) <= skip_warmup_frames:
        raise ValueError(f"Not enough frames: {len(times)} <= {skip_warmup_frames} warmup")
    return times[skip_warmup_frames:]


def mean(data: list[float]) -> float:
    return sum(data) / len(data)


def stddev(data: list[float], mu: float = None) -> float:
    if mu is None:
        mu = mean(data)
    if len(data) < 2:
        return 0.0
    return math.sqrt(sum((x - mu) ** 2 for x in data) / (len(data) - 1))


def percentile(data: list[float], p: float) -> float:
    """返回第 p 百分位数 (0.0-1.0)."""
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_data):
        return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
    return sorted_data[f]


def remove_outliers_iqr(data: list[float], factor: float = 1.5) -> list[float]:
    """使用 IQR 方法移除异常值."""
    q1 = percentile(data, 0.25)
    q3 = percentile(data, 0.75)
    iqr = q3 - q1
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    return [x for x in data if lower <= x <= upper]


def mann_whitney_u(x: list[float], y: list[float]) -> tuple[float, float]:
    """
    Mann-Whitney U 检验 (简化版，对小样本适用)。
    返回 (U_statistic, approximate_p_value via normal approximation).

    原假设 H0: 两个样本来自同一分布
    备择假设 H1: X 的分布系统性大于 Y（即性能退化）

    p < 0.05 → 拒绝 H0，存在统计显著的差异
    """
    combined = [(v, 0) for v in x] + [(v, 1) for v in y]
    combined.sort(key=lambda t: t[0])

    n1, n2 = len(x), len(y)
    rank_sum = 0
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        # 处理平局: 平均排名
        avg_rank = (i + j + 1) / 2.0
        for k in range(i, j):
            if combined[k][1] == 0:
                rank_sum += avg_rank
        i = j

    U1 = rank_sum - n1 * (n1 + 1) / 2.0
    U2 = n1 * n2 - U1
    U = min(U1, U2)

    # 正态近似
    mu = n1 * n2 / 2.0
    # 平局校正的方差 (简化版)
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)

    if sigma == 0:
        return U, 1.0

    z = abs((U - mu) / sigma)
    # 近似 p-value (标准正态)
    # 使用 Abramowitz & Stegun 近似
    p = 2.0 * (1.0 - normal_cdf(z))
    return U, min(p, 1.0)


def normal_cdf(x: float) -> float:
    """标准正态分布 CDF 的近似."""
    # Hart 近似 (1968)
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------
# 主检测逻辑
# ---------------------------------------------------------------

def detect_regression(
    baseline_csv: str,
    current_csv: str,
    threshold_pct: float = 0.05,
    min_frames: int = 300,
) -> dict:
    """
    比较 baseline 和 current 的帧时间。

    threshold_pct: 例如 0.05 = 5%，如果平均帧时间增长超过 5%，判定回归
    """
    baseline = load_frame_times(baseline_csv)
    current  = load_frame_times(current_csv)

    if len(baseline) < min_frames or len(current) < min_frames:
        return {
            "pass": False,
            "error": f"Not enough frames (need ≥{min_frames})",
            "baseline_mean": mean(baseline),
            "current_mean": mean(current),
        }

    # 移除异常值
    baseline_clean = remove_outliers_iqr(baseline)
    current_clean  = remove_outliers_iqr(current)

    b_mean = mean(baseline_clean)
    c_mean = mean(current_clean)
    b_p99  = percentile(baseline_clean, 0.99)
    c_p99  = percentile(current_clean, 0.99)
    b_p999 = percentile(baseline_clean, 0.999)
    c_p999 = percentile(current_clean, 0.999)

    # 计算变化百分比
    mean_change_pct = ((c_mean - b_mean) / b_mean) * 100.0
    p99_change_pct  = ((c_p99 - b_p99) / b_p99) * 100.0

    # Mann-Whitney U 检验
    u_stat, p_value = mann_whitney_u(baseline_clean, current_clean)

    # 判定
    regression_detected = (
        mean_change_pct > threshold_pct * 100.0  # 平均帧时间增长超过阈值
        and p_value < 0.01  # 统计显著
    )

    return {
        "pass": not regression_detected,
        "baseline_mean": b_mean,
        "current_mean": c_mean,
        "mean_change_pct": mean_change_pct,
        "baseline_p99": b_p99,
        "current_p99": c_p99,
        "p99_change_pct": p99_change_pct,
        "baseline_p999": b_p999,
        "current_p999": c_p999,
        "u_statistic": u_stat,
        "p_value": p_value,
    }


# ---------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="检测游戏帧时间性能回归"
    )
    parser.add_argument("--baseline", required=True,
                        help="基线帧时间 CSV 文件路径")
    parser.add_argument("--current", required=True,
                        help="当前构建的帧时间 CSV 文件路径")
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="回归检测阈值 (e.g. 0.05 = 5%%)")
    parser.add_argument("--output-json", default=None,
                        help="JSON 格式的结果输出路径")
    parser.add_argument("--min-frames", type=int, default=300,
                        help="最少需要的帧数")
    args = parser.parse_args()

    result = detect_regression(
        args.baseline, args.current,
        threshold_pct=args.threshold,
        min_frames=args.min_frames,
    )

    # 终端输出
    print("=" * 60)
    print("性能回归检测报告")
    print("=" * 60)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(2)

    print(f"基线文件:     {args.baseline}")
    print(f"当前文件:     {args.current}")
    print(f"回归阈值:     {args.threshold * 100:.0f}%")
    print("-" * 60)
    print(f"基線平均帧时间:   {result['baseline_mean']:7.2f} ms")
    print(f"当前平均帧时间:   {result['current_mean']:7.2f} ms")
    print(f"均值变化:         {result['mean_change_pct']:+7.2f}%")
    print(f"基線 P99:         {result['baseline_p99']:7.2f} ms")
    print(f"当前 P99:         {result['current_p99']:7.2f} ms")
    print(f"P99 变化:         {result['p99_change_pct']:+7.2f}%")
    print(f"基線 P99.9:       {result['baseline_p999']:7.2f} ms")
    print(f"当前 P99.9:       {result['current_p999']:7.2f} ms")
    print(f"Mann-Whitney U:   {result['u_statistic']:.2f}")
    print(f"p-value:          {result['p_value']:.6f}")
    print("-" * 60)

    if result["pass"]:
        print("✓ 通过: 未检测到统计显著的性能回归")
        exit_code = 0
    else:
        print("✗ 失败: 检测到统计显著的性能回归!")
        print(f"  平均帧时间增长了 {result['mean_change_pct']:.2f}% (阈值 {args.threshold * 100:.0f}%)")
        print(f"  p = {result['p_value']:.6f} (显著水平 0.01)")
        exit_code = 1

    # 可选的 JSON 输出
    if args.output_json:
        import json
        with open(args.output_json, 'w') as f:
            json.dump(result, f, indent=2)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
```

```bash
# 使用示例
# 第一步: 从游戏构建中收集帧时间 (假设游戏输出格式化的日志)
./my_game --benchmark-scene=test_level_1 --output-csv=current.csv

# 第二步: 与基线比较
python3 perf_regression_test.py \
    --baseline ci_baselines/test_level_1_baseline.csv \
    --current current.csv \
    --threshold 0.05 \
    --output-json result.json

# 示例输出:
# ============================================================
# 性能回归检测报告
# ============================================================
# 基线文件:     ci_baselines/test_level_1_baseline.csv
# 当前文件:     current.csv
# 回归阈值:     5%
# ------------------------------------------------------------
# 基線平均帧时间:    16.50 ms
# 当前平均帧时间:    17.82 ms
# 均值变化:          +8.00%
# 基線 P99:          22.10 ms
# 当前 P99:          25.40 ms
# P99 变化:          +14.93%
# 基線 P99.9:        35.20 ms
# 当前 P99.9:        42.80 ms
# Mann-Whitney U:    42300.00
# p-value:           0.000312
# ------------------------------------------------------------
# ✗ 失败: 检测到统计显著的性能回归!
#    平均帧时间增长了 8.00% (阈值 5%)
#    p = 0.000312 (显著水平 0.01)
```

### 示例 3: GitHub Actions CI 集成

```yaml
# .github/workflows/perf-regression.yml
# GitHub Actions: 自动化性能回归检测
# 触发条件: PR 到 main 分支时

name: Performance Regression Test

on:
  pull_request:
    branches: [main, develop]
    paths:
      # 只在相关源码变更时触发
      - 'src/**'
      - 'include/**'
      - 'shaders/**'
      - 'CMakeLists.txt'
  push:
    branches: [main]
    # 合并后也跑一次，更新基线

jobs:
  # ---------------------------------------------------------------
  # Job 1: 微基准测试 (Google Benchmark)
  # ---------------------------------------------------------------
  micro-benchmarks:
    name: Micro-benchmarks
    runs-on: [self-hosted, perf-test]  # 专用性能测试机器，避免共享硬件的噪声
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - name: Configure CMake
        run: |
          cmake -B build_bench -DCMAKE_BUILD_TYPE=Release \
            -DBUILD_BENCHMARKS=ON

      - name: Build Benchmarks
        run: cmake --build build_bench --config Release --target engine_benchmarks

      - name: Run Benchmarks
        run: |
          ./build_bench/engine_benchmarks \
            --benchmark_out=current_bench.json \
            --benchmark_out_format=json \
            --benchmark_repetitions=10 \
            --benchmark_report_aggregates_only=true \
            --benchmark_min_time=0.5s

      - name: Download Baseline
        uses: actions/cache/restore@v4
        with:
          path: baseline_bench.json
          key: perf-baseline-bench-${{ runner.os }}-${{ github.event.pull_request.base.sha || github.event.before }}

      - name: Compare Benchmarks
        run: |
          if [ -f baseline_bench.json ]; then
            python3 tools/perf_test/compare_benchmarks.py \
              --baseline baseline_bench.json \
              --current current_bench.json \
              --threshold 0.03  # 3% 回归阈值（微基准测试更严格）
          else
            echo "No baseline found — saving current as new baseline"
            cp current_bench.json baseline_bench.json
          fi

      - name: Update Baseline (on main push)
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: actions/cache/save@v4
        with:
          path: baseline_bench.json
          key: perf-baseline-bench-${{ runner.os }}-${{ github.sha }}

  # ---------------------------------------------------------------
  # Job 2: 场景级帧时间回归检测
  # ---------------------------------------------------------------
  scene-frametime-test:
    name: Scene Frame-Time Test
    runs-on: [self-hosted, perf-test, gpu]  # 需要 GPU 的 self-hosted runner
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - name: Build Game (Release)
        run: |
          cmake -B build -DCMAKE_BUILD_TYPE=Release
          cmake --build build --config Release

      - name: Run Benchmark Scene
        run: |
          # 启动游戏，自动播放固定的测试场景
          # 游戏需要支持命令行参数来:
          #   --headless (无窗口渲染)
          #   --benchmark-scene <name> (固定的测试场景)
          #   --benchmark-duration <seconds> (播放时长)
          #   --output-csv <path> (帧时间输出)
          ./build/my_game \
            --headless \
            --benchmark-scene=perf_test_city \
            --benchmark-duration=30 \
            --output-csv=current_frametimes.csv \
            --fixed-timestep \       # 固定时间步长，确保逻辑确定性
            --resolution=1920x1080   # 固定分辨率

      - name: Fetch Baseline Frametimes
        uses: actions/cache/restore@v4
        with:
          path: baseline_frametimes.csv
          key: perf-baseline-scene-city-${{ runner.os }}-${{ github.event.pull_request.base.sha || github.event.before }}

      - name: Detect Regression
        run: |
          if [ -f baseline_frametimes.csv ]; then
            python3 tools/perf_test/perf_regression_test.py \
              --baseline baseline_frametimes.csv \
              --current current_frametimes.csv \
              --threshold 0.05 \
              --output-json regression_result.json
          else
            echo "No baseline found — saving current as new baseline"
            cp current_frametimes.csv baseline_frametimes.csv
          fi

      - name: Upload Results
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: perf-regression-results
          path: |
            regression_result.json
            current_frametimes.csv
            baseline_frametimes.csv

      - name: Comment PR with Results
        if: github.event_name == 'pull_request' && failure()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const result = JSON.parse(fs.readFileSync('regression_result.json', 'utf8'));
            const body = `⚠️ **性能回归检测失败**
            - 平均帧时间: ${result.baseline_mean.toFixed(2)}ms → ${result.current_mean.toFixed(2)}ms (${result.mean_change_pct > 0 ? '+' : ''}${result.mean_change_pct.toFixed(2)}%)
            - P99: ${result.baseline_p99.toFixed(2)}ms → ${result.current_p99.toFixed(2)}ms (${result.p99_change_pct > 0 ? '+' : ''}${result.p99_change_pct.toFixed(2)}%)
            - p-value: ${result.p_value.toFixed(6)}
            `;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: body
            });
```

### 示例 4: 帧时间日志输出（游戏端）

你的游戏需要输出帧时间数据供 CI 脚本消费。以下是最简单的实现：

```cpp
// frame_time_logger.h
// 游戏端的帧时间记录和 CSV 输出
#pragma once

#include <cstdio>
#include <vector>
#include <chrono>
#include <string>

class FrameTimeLogger {
public:
    struct Config {
        std::string outputPath;     // CSV 输出路径
        bool        enabled = true; // 是否启用记录
        size_t      maxFrames = 6000; // 最多记录帧数（~100 秒 @ 60fps）
    };

    explicit FrameTimeLogger(const Config &cfg) : m_cfg(cfg) {
        if (m_cfg.enabled && !m_cfg.outputPath.empty()) {
            m_times.reserve(m_cfg.maxFrames);
        }
    }

    // 每帧结束时调用
    void RecordFrame(double frameTimeMs) {
        if (!m_cfg.enabled) return;
        if (m_times.size() >= m_cfg.maxFrames) return;
        m_times.push_back(frameTimeMs);
    }

    // 程序退出前调用
    void FlushToCSV() {
        if (m_times.empty()) return;

        FILE *f = fopen(m_cfg.outputPath.c_str(), "w");
        if (!f) {
            fprintf(stderr, "[FrameTimeLogger] Cannot open %s\n",
                    m_cfg.outputPath.c_str());
            return;
        }
        fprintf(f, "frame,dt_ms\n");
        for (size_t i = 0; i < m_times.size(); ++i) {
            fprintf(f, "%zu,%.4f\n", i + 1, m_times[i]);
        }
        fclose(f);
        printf("[FrameTimeLogger] Wrote %zu frames to %s\n",
               m_times.size(), m_cfg.outputPath.c_str());
    }

    ~FrameTimeLogger() {
        FlushToCSV();
    }

private:
    Config            m_cfg;
    std::vector<double> m_times;
};

// 使用方式:
// int main() {
//     FrameTimeLogger logger({"perf_output.csv"});
//     while (running) {
//         auto t0 = std::chrono::high_resolution_clock::now();
//         RunFrame();
//         auto t1 = std::chrono::high_resolution_clock::now();
//         double dt_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
//         logger.RecordFrame(dt_ms);
//     }
// }
```

### 示例 5: 比较 Google Benchmark JSON 输出的 Python 脚本

```python
#!/usr/bin/env python3
"""
compare_benchmarks.py — 比较两个 Google Benchmark JSON 输出文件
检测任何基准测试的时间增长超过指定阈值。
"""
import json
import sys


def load_benchmark_json(path: str) -> dict:
    """加载 Google Benchmark JSON 输出。"""
    with open(path, 'r') as f:
        data = json.load(f)

    result = {}
    for bench in data.get("benchmarks", []):
        name = bench["name"]
        # 使用 "real_time"（挂钟时间而非 CPU 时间 — 游戏更关注这个）
        real_time = bench.get("real_time", bench.get("cpu_time", 0))
        result[name] = real_time
    return result


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 compare_benchmarks.py <baseline.json> <current.json> <threshold>")
        print("  threshold: 例如 0.03 = 3%")
        sys.exit(2)

    baseline_path = sys.argv[1]
    current_path  = sys.argv[2]
    threshold     = float(sys.argv[3])

    baseline = load_benchmark_json(baseline_path)
    current  = load_benchmark_json(current_path)

    all_pass = True

    for name in sorted(set(baseline.keys()) & set(current.keys())):
        b_time = baseline[name]
        c_time = current[name]
        change_pct = ((c_time - b_time) / b_time) * 100.0

        status = "✓" if change_pct <= threshold * 100.0 else "✗ REGRESSION"
        if change_pct > threshold * 100.0:
            all_pass = False

        print(f"{status:>15} | {name:<50} | {b_time:>10.2f} → {c_time:>10.2f} ns | {change_pct:+7.2f}%")

    if not all_pass:
        print("\n❌ BENCHMARK REGRESSION DETECTED")
        sys.exit(1)
    else:
        print("\n✅ All benchmarks pass")


if __name__ == "__main__":
    main()
```

---
## 3. 练习

### 练习 1: 运行 Google Benchmark 并比较结果 (基础)

**目标**：为至少 2 个游戏相关函数编写基准测试，运行并分析结果。

**步骤**：
1. 安装 Google Benchmark（参考示例 1）
2. 写两个基准测试函数：
   - 函数 A：对一个 `std::vector<int>` 做 `std::sort`
   - 函数 B：对一个 `std::vector<int>` 做 `std::stable_sort`
3. 分别在 1,000、10,000、100,000 个元素上运行
4. 用 `--benchmark_out=results.json` 导出结果
5. 用 Python 脚本（或手算）比较两个排序的性能差异

**验收标准**：能准确说出在不同数据规模下，`sort` 和 `stable_sort` 的相对性能差异（百分比）。

### 练习 2: 构建帧时间回归检测流水线 (进阶)

**目标**：从零搭建一个完整的"修改代码 → 构建 → 运行 → 比较基线"的本地回归检测流程。

**步骤**：
1. 创建一个简单的测试程序：
   - 循环 500 帧，每帧做固定量的计算（例如：1000 次 `sqrt()`）
   - 输出 CSV 格式的帧时间到 `frametimes.csv`
2. 运行程序 2 次，生成 `baseline.csv` 和 `current.csv`
3. 使用示例 2 的 `perf_regression_test.py` 脚本比较两个文件
4. 修改程序，增加计算量（例如：每帧多做 200 次 `sqrt()`）
5. 重新运行脚本，验证它能检测出回归
6. 调整 `--threshold` 参数，观察阈值如何影响检测结果

**验收标准**：脚本在计算量增加时正确报告回归，在计算量不变时正确通过。

### 练习 3: 设计一个 CI 性能门禁方案（可选，挑战）

**目标**：为你的（或假设的）游戏仓库设计一个完整的 CI 性能门禁方案。

**步骤**：
1. 列出你的游戏中最关键的 3 个性能指标（如：平均帧时间、P99 帧时间、Draw Call 数量）
2. 为每个指标设计：
   - 采集方式（怎么获取这个数据）
   - 基线来源（从哪里获取上次的数据作为基线）
   - 回归阈值（增长多少算回归）
3. 画出 CI 流程图：PR 提交 → 构建 → 测试 → 比较基线 → 通过/失败 → 通知
4. 考虑以下边界情况：
   - CI 机器换了怎么办？（基线失效）
   - 有意的大改动（如场景重做）导致"合理"的性能下降怎么办？
   - 多平台检测（Windows/Linux/主机）如何并行

**验收标准**：产出一份 1 页的方案文档（可以用中文），包含流程图和边界情况处理方案。

---
## 4. 扩展阅读

- [Google Benchmark 用户指南](https://github.com/google/benchmark/blob/main/docs/user_guide.md) — 完整的 API 文档，包括 Fixture、多线程基准测试、复杂度分析
- [Performance Testing in CI — Dropbox Tech Blog](https://dropbox.tech/infrastructure/performance-testing-in-continuous-integration) — Dropbox 在 CI 中集成性能测试的工程实践
- [Statistical Performance Analysis — Brendan Gregg](https://www.brendangregg.com/statistics.html) — 性能数据统计分析的方法论，涵盖可视化、分布比较、假设检验
- [Catch2 Benchmarks](https://github.com/catchorg/Catch2/blob/devel/docs/benchmarks.md) — Catch2 测试框架内置的 Benchmark 支持（如果已经在用 Catch2 做单元测试）
- [RenderDoc Python API 文档](https://renderdoc.org/docs/python_api/index.html) — 用 Python 脚本批量分析 RenderDoc 捕获文件，适用于帧级自动化测试
- [UE Automation System](https://docs.unrealengine.com/5.0/en-US/automation-system-in-unreal-engine/) — UE 内置的自动化测试框架，支持 Gauntlet 性能场景测试
- [Unity Performance Testing Extension](https://docs.unity3d.com/Packages/com.unity.test-framework.performance@3.1/manual/index.html) — Unity 官方性能测试包，支持 `Measure.Method()` 和 `Measure.Frames()`

---
## 常见陷阱

1. **冷启动数据污染基线**。程序刚启动的前几帧/Pixel存在 Shader 编译、资源加载、GPU Pipeline 创建等一次性开销。必须在统计中跳过这些"warmup"帧。默认跳过 60 帧（~1 秒）是最低要求，复杂的 AAA 场景可能需要跳过 300+ 帧。

2. **在共享 CI Runner 上跑性能测试**。GitHub Actions 的共享 runner 运行在虚拟机上，与其他任务共享物理 CPU。结果会有巨大的随机噪声（±20% 都正常）。**你必须使用专用的 self-hosted runner**，并确保：
   - 关闭 CPU 频率动态调节（固定频率或 High Performance 电源计划）
   - 关闭其他非必要的后台进程
   - 固定线程亲和性（taskset / SetThreadAffinityMask）

3. **只用平均值判断回归**。游戏性能最致命的是帧时间方差（Frame Time Variance）。平均值可能从 16ms 变为 17ms（"只慢了 6%"），但 P99 可能从 20ms 变为 35ms（"每 100 帧有 1 帧卡顿半秒"）。**必须同时监控 P99 和 P99.9**。

4. **忽略 GPU 热节流**。GPU 在持续高负载下会热节流（降频）。如果场景级测试运行了 30 分钟，后半段的帧时间会因为 GPU 降频而系统性偏高。解决方法：
   - 固定 GPU 频率（工具制造商提供，如 NVIDIA `nvidia-smi -lgc`）
   - 只取测试中间段的帧（排除两端的热累积期）

5. **头文件中的 `BENCHMARK` 宏和主程序冲突**。Google Benchmark 的 `BENCHMARK_MAIN()` 会定义 `main()`，如果你的游戏也有 `main()`，会发生冲突。解决方法：将基准测试编译为独立的可执行文件（推荐），或使用 `RegisterBenchmark` + 自定义 Runner。

6. **统计检验的陷阱**：
   - 样本太小（<30）：Mann-Whitney U 检验的正态近似不准确。使用精确检验或增加样本
   - 多重比较问题：同时比较 20 个基准测试，大约有 1 个会"碰巧"显著（p<0.05）。使用 Bonferroni 校正（阈值 = 0.05 / N_tests）
   - p < 0.05 不代表"一定有性能回归"——它只代表"在 H0 假设下，观察到这个差异的概率小于 5%"。结合效应量（effect size = 均值差 / 基线标准差）来综合判断

7. **"Baseline of 1" 问题**。刚添加性能测试时没有基线可以比较。最佳实践：
   - 第一次运行时：将当前结果保存为基线
   - 之后的每次运行：与基线比较
   - 定期（每周/每 milestone）手动更新基线——因为合法的性能变化会累积（优化改进纳入基线）
