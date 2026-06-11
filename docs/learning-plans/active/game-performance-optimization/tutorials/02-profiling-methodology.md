---
title: "性能测量方法学 — 测量、定位、验证三步法"
updated: 2026-06-05
---

# 性能测量方法学 — 测量、定位、验证三步法

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: 01-why-optimize（理解帧预算概念）

---

## 1. 概念讲解

### 为什么需要这个？

你接手了一个性能差的项目。帧率在 25–40fps 之间跳动。团队意见不一：
- 美术说"肯定是 Shader 太复杂"
- 程序员 A 说"物理系统用了太多 Raycast"
- 程序员 B 说"Draw Call 太多"

谁是对的？**没有测量数据的时候，所有人都在猜。** 盲猜优化的成功率极低 — 你花一周"优化物理"，结果帧率提高了 0.5fps，因为你优化的东西原本只占 2% 的帧时间。

更糟的是，直觉在性能领域经常**系统性地错误**。现代 CPU 和 GPU 的行为极其复杂 — 缓存未命中、分支预测失败、内存带宽瓶颈、驱动层的状态验证 — 这些都不是"看着代码"就能判断的。

性能测量不是一次性的操作。它是一套完整的**方法论**，是在你的游戏生命周期的每个阶段反复执行的科学流程。

#### 不测量就优化的代价

| 行为 | 实际结果 |
|------|----------|
| 优化占运行时间 1% 的代码 | 最大理论收益 1%，实际不可感知 |
| 改了"看起来一样"的数据结构 | 缓存行为改变，可能反而变慢 |
| 引入更复杂的算法"以防万一" | 增加代码复杂度，维护成本，bug 风险 |
| 声称"优化后好了 20%"但没有证据 | 无法复现的"优化"等于没有优化 |

### 核心思想

性能优化是一个**科学实验循环**，不是一次性的代码修改：

```
观察 (Observe) → 假设 (Hypothesize) → 实验 (Experiment) → 验证 (Verify)
    ↑                                                              │
    └────────────────────── 循环 ───────────────────────────────────┘
```

具体化为四个操作步骤：

1. **建立基线 (Baseline)**：用可复现的方式记录当前性能数据
2. **定位热点 (Hotspot)**：用 Profiler 找出占用时间最多的函数或系统
3. **实施修改 (Change)**：做**最小的、可验证的**代码修改
4. **对比验证 (Validate)**：在**相同条件**下重新测量，确认改进是否真实

#### 测量方法的三种范式

| 方法 | 原理 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|----------|
| **插桩 (Instrumentation)** | 在代码中手动插入计时点 | 精确、可定制、可关联业务逻辑 | 侵入代码、有 Heisenbug 风险（测量影响被测对象）、包含插桩本身的开销 | 测量特定子系统的耗时 |
| **采样 (Sampling)** | 以固定频率（如 1kHz）暂停程序，记录当前调用栈 | 低开销、非侵入、整体视图 | 不精确（可能漏掉短函数）、不能直接给出调用次数 | 宏观定位热点 |
| **追踪 (Tracing)** | 记录每个函数进入/退出的事件流 | 完整、精确、可分析调用关系 | 数据量大、开销高、可能改变时序行为 | 深度分析特定问题 |

**实际工作中的最佳实践：先用采样找到热点区域，再在热点区域加插桩精确测量。**

#### 统计显著性：为什么一次测量毫无意义

你的游戏是不确定系统。操作系统调度、其他进程、CPU 睿频/降频、GPU 温度管理、内存带宽竞争 — 每一帧的时间都有波动。

如果你测量一次，得到 15ms；优化后再测一次，得到 14ms。**这不能证明你的优化有效。** 14ms 可能只是因为 OS 当时没有在后台做磁盘 I/O。

需要的是**统计方法**：

1. **多次测量**：至少 300-1000 帧的连续采集
2. **预暖 (Warmup)**：丢弃前 N 帧 — 第一帧通常有大量的一次性初始化（Shader 编译、资源加载）
3. **查看分布**：不只是平均值。`{min, max, mean, median, p50, p95, p99, p99.9}`
4. **标准差**：标准差大 → 帧时间不稳定 → 玩家能感知到抖动

**百分位(Percentile) 分析是性能工程的基石**：
- **P50（中位数）**：一半的帧比这快，一半比这慢。代表"典型"体验。
- **P95**：95% 的帧比这快。只有 5% 的帧更慢。通常这是玩家"感到卡顿"的分界线。
- **P99**：1% 的极端情况。这些是导致玩家投诉"游戏卡"的罪魁祸首。
- **P99.9**：千分之一的极端帧。在 60fps 下，每 16 秒出现一次 — 已经足够让玩家注意到。

#### Amdahl 定律的应用：把钱花在刀刃上

Amdahl 定律：`总体加速比 = 1 / ((1 - p) + p/s)`

其中 `p` 是优化部分占总时间的比例，`s` 是该部分的加速比。

**推论**：即使你把一个操作变成零时间（s=∞），总体加速比也受限于 `1/(1-p)`。

| 被优化部分占比 | 将该部分加速 10 倍 | 将该部分加速 100 倍 | 将该部分变成零时间 |
|:------------:|:-----------------:|:------------------:|:-----------------:|
| 10% | 1.10× | 1.11× | 1.11× |
| 30% | 1.37× | 1.42× | 1.43× |
| 50% | 1.82× | 1.98× | 2.00× |
| 80% | 3.57× | 4.81× | 5.00× |
| 95% | 6.90× | 16.39× | 20.00× |

**结论**：如果一个热点只占帧时间的 10%，你把它优化到零也只能提升 11%。**永远先处理最大的热点。**

#### 变量隔离原则

当你优化时，**一次只改一个变量**。如果你同时改了 3 个地方，性能提升了 30%，你无法知道是哪个改动真正起作用，哪个是无用的噪声，哪个实际上反而拖慢了（被另外两个的收益掩盖了）。

---

## 2. 代码示例

以下是一个完整的 C++ 性能测量框架，实现了暖身阶段、统计计算、百分位分析和 ASCII 直方图。你可以直接复制使用。

```cpp
// profiling_harness.cpp — 性能测量框架
#include <chrono>
#include <vector>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <string>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <cassert>

// ==================== 帧时间采集器 ====================

class FrameProfiler {
public:
    using Clock = std::chrono::high_resolution_clock;
    using TimePoint = Clock::time_point;

    struct Config {
        size_t warmup_frames   = 60;    // 暖身帧数
        size_t measure_frames  = 600;   // 测量帧数
        bool   auto_detect_warmup = true; // 自动检测暖身结束
        double warmup_std_threshold = 0.15; // 标准差下降到均值的 15% 以下视为暖身完成
    };

    struct Result {
        // 基础统计
        double min_ms, max_ms, mean_ms, median_ms;
        double std_dev_ms;
        // 百分位
        double p50_ms, p90_ms, p95_ms, p99_ms, p999_ms;
        // 帧数
        size_t total_frames, warmup_frames, measure_frames;
    };

    explicit FrameProfiler(const Config& cfg = Config{}) : config_(cfg) {}

    // 开始计时一帧
    void BeginFrame() {
        current_frame_start_ = Clock::now();
    }

    // 结束计时一帧，记录帧时间。返回 false 表示测量阶段完成。
    bool EndFrame() {
        double ms = std::chrono::duration<double, std::milli>(
            Clock::now() - current_frame_start_).count();

        all_frame_times_.push_back(ms);
        return all_frame_times_.size() < total_target_frames();
    }

    // 运行完整的测量流程（同步/阻塞版本 — 适用简单场景）
    template<typename F>
    Result Measure(F&& work_func) {
        all_frame_times_.clear();
        all_frame_times_.reserve(total_target_frames());

        std::cout << "[Profiler] 开始采集: 暖身 "
                  << config_.warmup_frames << " 帧 + 测量 "
                  << config_.measure_frames << " 帧\n";

        for (size_t i = 0; i < total_target_frames(); i++) {
            BeginFrame();
            work_func(i);
            EndFrame();
        }

        std::cout << "[Profiler] 采集完成 " << all_frame_times_.size() << " 帧\n";
        return ComputeResult();
    }

    // 分析已有数据
    Result ComputeResult() {
        Result r = {};
        if (all_frame_times_.empty()) return r;

        r.total_frames = all_frame_times_.size();

        // 自动检测暖身结束点
        size_t warmup_end = config_.warmup_frames;
        if (config_.auto_detect_warmup && all_frame_times_.size() > 120) {
            warmup_end = DetectWarmupEnd();
        }

        r.warmup_frames = std::min(warmup_end, all_frame_times_.size());
        r.measure_frames = all_frame_times_.size() - r.warmup_frames;

        if (r.measure_frames == 0) return r;

        // 只分析测量阶段的帧
        auto begin = all_frame_times_.begin() + r.warmup_frames;
        auto end   = all_frame_times_.end();

        r.min_ms = *std::min_element(begin, end);
        r.max_ms = *std::max_element(begin, end);
        r.mean_ms = std::accumulate(begin, end, 0.0) / r.measure_frames;

        // 标准差
        double sq_sum = 0.0;
        for (auto it = begin; it != end; ++it) {
            sq_sum += (*it - r.mean_ms) * (*it - r.mean_ms);
        }
        r.std_dev_ms = std::sqrt(sq_sum / r.measure_frames);

        // 排序用于百分位
        std::vector<double> sorted(begin, end);
        std::sort(sorted.begin(), sorted.end());

        r.median_ms = Percentile(sorted, 0.50);
        r.p50_ms    = Percentile(sorted, 0.50);
        r.p90_ms    = Percentile(sorted, 0.90);
        r.p95_ms    = Percentile(sorted, 0.95);
        r.p99_ms    = Percentile(sorted, 0.99);
        r.p999_ms   = Percentile(sorted, 0.999);

        return r;
    }

    // 打印报告
    static void PrintReport(const Result& r) {
        std::cout << "\n";
        std::cout << "╔══════════════════════════════════════════╗\n";
        std::cout << "║         Perf Measurement Report          ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";
        std::cout << "║ 总帧数:     " << std::setw(8) << r.total_frames << "             ║\n";
        std::cout << "║ 暖身帧:     " << std::setw(8) << r.warmup_frames << "             ║\n";
        std::cout << "║ 测量帧:     " << std::setw(8) << r.measure_frames << "             ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";
        std::cout << std::fixed << std::setprecision(3);
        std::cout << "║ min:    " << std::setw(10) << r.min_ms << " ms            ║\n";
        std::cout << "║ max:    " << std::setw(10) << r.max_ms << " ms            ║\n";
        std::cout << "║ mean:   " << std::setw(10) << r.mean_ms << " ms            ║\n";
        std::cout << "║ std:    " << std::setw(10) << r.std_dev_ms << " ms            ║\n";
        std::cout << "║ p50:    " << std::setw(10) << r.p50_ms << " ms            ║\n";
        std::cout << "║ p90:    " << std::setw(10) << r.p90_ms << " ms            ║\n";
        std::cout << "║ p95:    " << std::setw(10) << r.p95_ms << " ms            ║\n";
        std::cout << "║ p99:    " << std::setw(10) << r.p99_ms << " ms            ║\n";
        std::cout << "║ p99.9:  " << std::setw(10) << r.p999_ms << " ms            ║\n";
        std::cout << "╚══════════════════════════════════════════╝\n";
        std::cout << "\n";
    }

    // 绘制 ASCII 直方图
    static void PrintHistogram(const std::vector<double>& frame_times,
                                size_t num_buckets = 20) {
        if (frame_times.empty()) return;

        double data_min = *std::min_element(frame_times.begin(), frame_times.end());
        double data_max = *std::max_element(frame_times.begin(), frame_times.end());
        double bucket_width = (data_max - data_min) / num_buckets;
        if (bucket_width < 0.001) bucket_width = 0.001;

        std::vector<size_t> buckets(num_buckets, 0);
        for (double t : frame_times) {
            size_t idx = static_cast<size_t>((t - data_min) / bucket_width);
            if (idx >= num_buckets) idx = num_buckets - 1;
            buckets[idx]++;
        }

        size_t max_count = *std::max_element(buckets.begin(), buckets.end());
        const size_t bar_width = 40; // 最大柱宽

        std::cout << "\n=== 帧时间分布直方图 ===\n";
        std::cout << "范围: [" << data_min << "ms, " << data_max << "ms]\n\n";

        for (size_t i = 0; i < num_buckets; i++) {
            double low  = data_min + i * bucket_width;
            double high = low + bucket_width;
            size_t bar_len = (max_count > 0)
                ? static_cast<size_t>((double)buckets[i] / max_count * bar_width)
                : 0;

            std::cout << std::fixed << std::setprecision(1)
                      << std::setw(5) << low << "-"
                      << std::setw(5) << high << "ms |"
                      << std::string(bar_len, '#')
                      << std::string(bar_width - bar_len, ' ')
                      << "| " << buckets[i] << "\n";
        }
    }

    const std::vector<double>& AllFrameTimes() const { return all_frame_times_; }

private:
    size_t total_target_frames() const {
        return config_.warmup_frames + config_.measure_frames;
    }

    // 自动检测暖身：滑动窗口标准差下降到稳定水平
    size_t DetectWarmupEnd() const {
        const size_t window = 30;
        if (all_frame_times_.size() < window * 3) return config_.warmup_frames;

        // 从第 10 帧开始，每次前进 1 帧检测窗口内的标准差
        double global_mean = std::accumulate(
            all_frame_times_.begin() + 10,
            all_frame_times_.begin() + std::min(size_t(100), all_frame_times_.size()),
            0.0) / std::min(size_t(90), all_frame_times_.size() - 10);

        for (size_t i = window; i + window < all_frame_times_.size(); i++) {
            double window_mean = 0.0;
            for (size_t j = i - window; j < i + window; j++)
                window_mean += all_frame_times_[j];
            window_mean /= (window * 2);

            double window_std = 0.0;
            for (size_t j = i - window; j < i + window; j++)
                window_std += (all_frame_times_[j] - window_mean) * (all_frame_times_[j] - window_mean);
            window_std = std::sqrt(window_std / (window * 2));

            if (global_mean > 0.001 && window_std / global_mean < config_.warmup_std_threshold) {
                return i; // 帧时间已稳定
            }
        }
        return config_.warmup_frames;
    }

    static double Percentile(const std::vector<double>& sorted, double p) {
        assert(p >= 0.0 && p <= 1.0);
        if (sorted.empty()) return 0.0;
        double idx = p * (sorted.size() - 1);
        size_t lo = static_cast<size_t>(std::floor(idx));
        size_t hi = static_cast<size_t>(std::ceil(idx));
        if (lo == hi) return sorted[lo];
        double frac = idx - lo;
        return sorted[lo] * (1.0 - frac) + sorted[hi] * frac;
    }

    Config config_;
    TimePoint current_frame_start_;
    std::vector<double> all_frame_times_;
};

// ==================== 使用示例 ====================

// 模拟三种不同的工作负载模式
enum class Workload { STABLE, PERIODIC_SPIKE, RANDOM_JITTER };

double SimulateFrameWork(int frame, Workload mode) {
    // 基准工作量 ~8ms
    double base = 8.0;
    double extra = 0.0;

    switch (mode) {
    case Workload::STABLE:
        // 稳定负载: 每帧约 8ms, 微小随机波动
        extra = (rand() % 100) / 1000.0; // 0 ~ 0.1ms 随机
        break;

    case Workload::PERIODIC_SPIKE:
        // 周期性峰值: 每 25 帧有一个 30ms 的大操作（模拟 GC 或大量 AI 更新）
        if (frame % 25 == 0) extra = 30.0;
        break;

    case Workload::RANDOM_JITTER:
        // 随机抖动: 每帧 5-20ms 之间随机
        extra = -3.0 + (rand() % 150) / 10.0; // -3.0 ~ 12.0
        break;
    }

    double target = base + extra;
    if (target < 1.0) target = 1.0;

    // 忙等待模拟工作
    auto start = std::chrono::high_resolution_clock::now();
    while (true) {
        auto now = std::chrono::high_resolution_clock::now();
        double ms = std::chrono::duration<double, std::milli>(now - start).count();
        if (ms >= target) break;
    }
    return target;
}

int main() {
    // 配置: 暖身 30 帧, 测量 600 帧
    FrameProfiler::Config cfg;
    cfg.warmup_frames  = 30;
    cfg.measure_frames = 600;

    std::cout << "==========================================\n";
    std::cout << "  性能测量方法学 — 三种负载模式对比\n";
    std::cout << "==========================================\n";

    const char* labels[] = {"稳定负载", "周期峰值", "随机抖动"};
    Workload modes[] = {Workload::STABLE, Workload::PERIODIC_SPIKE, Workload::RANDOM_JITTER};

    for (int m = 0; m < 3; m++) {
        std::cout << "\n>>> 模式: " << labels[m] << " <<<\n";

        FrameProfiler profiler(cfg);
        auto result = profiler.Measure([&, m](int frame) {
            SimulateFrameWork(frame, modes[m]);
        });

        FrameProfiler::PrintReport(result);

        // 只看测量阶段的直方图
        auto& all = profiler.AllFrameTimes();
        std::vector<double> measured(
            all.begin() + result.warmup_frames, all.end());
        FrameProfiler::PrintHistogram(measured);
    }

    // 关键对比
    std::cout << "\n==========================================\n";
    std::cout << "  关键观察\n";
    std::cout << "==========================================\n";
    std::cout << "* 稳定模式: 标准差小, P99 接近均值 — '好' 的性能特征\n";
    std::cout << "* 周期峰值: 均值可能较低, 但 P99 远高于均值 — \n";
    std::cout << "            只看平均值会误判为健康\n";
    std::cout << "* 随机抖动: 标准差大, 所有百分位分散 — \n";
    std::cout << "            玩家感受到的是不稳定的帧率\n";

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 -O2 profiling_harness.cpp -o profiling_harness
./profiling_harness
```

**预期输出:**

```text
==========================================
  性能测量方法学 — 三种负载模式对比
==========================================

>>> 模式: 稳定负载 <<<
[Profiler] 开始采集: 暖身 30 帧 + 测量 600 帧
[Profiler] 采集完成 630 帧

╔══════════════════════════════════════════╗
║         Perf Measurement Report         ║
╠══════════════════════════════════════════╣
║ 总帧数:          630             ║
║ 暖身帧:           30             ║
║ 测量帧:          600             ║
╠══════════════════════════════════════════╣
║ min:        8.000 ms            ║
║ max:        8.098 ms            ║
║ mean:       8.050 ms            ║
║ std:        0.029 ms            ║
║ p50:        8.049 ms            ║
║ p90:        8.087 ms            ║
║ p95:        8.091 ms            ║
║ p99:        8.096 ms            ║
║ p99.9:      8.098 ms            ║
╚══════════════════════════════════════════╝

=== 帧时间分布直方图 ===
范围: [8.000ms, 8.098ms]
  8.0- 8.0ms |############                        | ...
  ...

>>> 模式: 周期峰值 <<<
  ...
  P99 远高于均值 — 注意这个差异!

>>> 模式: 随机抖动 <<<
  ...
  标准差大 — 帧率不稳定
```

**关键发现**：对于"周期峰值"模式，均值可能只有 ~9ms（看起来很健康），但 P99 可能高达 ~38ms。**这就是为什么永远不能只看平均值。**

---

## 3. 练习

### 练习 1: 改进暖身检测算法

当前的 `DetectWarmupEnd()` 使用简单的窗口标准差阈值。改进它：

1. 改为**连续 N 个窗口**（N=5）的标准差都低于阈值才认为暖身完成（而不是单次检查）
2. 在暖身检测到之后再等待额外的 `M` 帧（M=10）作为安全边际
3. 输出"暖身检测完成于第 X 帧"的日志信息

**验收标准**：用一段"前 200 帧波动大、之后趋于稳定"的模拟数据测试，确保暖身检测不会在第一个安静的窗口就错误触发。

### 练习 2: 实现自定义百分位比较工具

写一个函数 `CompareProfiles(const Result& before, const Result& after)`：
- 逐百分位点（p50, p75, p90, p95, p99, p99.9）比较 before 和 after
- 计算每个百分位的变化百分比
- 用 ASCII 格式输出对比表格
- 如果某个百分位**变差了 5% 以上**，用 ⚠️ 标记（"可能是回归"）

```cpp
void CompareProfiles(const FrameProfiler::Result& before,
                     const FrameProfiler::Result& after);
```

**验收标准**：用"优化前"和"优化后"两组数据，验证比较工具正确识别了改进和回归。

### 练习 3: 识别假瓶颈和真瓶颈（可选）

写一个合成测试程序，包含以下组件：
- **假瓶颈 A**：一个占帧时间 2% 的循环（`for i in range(1000000): result += sin(i)`）
- **真瓶颈 B**：一个占帧时间 65% 的循环（同样类型的计算，但迭代次数多 32 倍）

用 `FrameProfiler` 测量整体帧时间。然后：
1. 手动给 A 加单独的计时插桩，看到它只占 2%
2. 手动给 B 加单独的计时插桩，看到它占 65%
3. 分别"优化"（减少迭代次数）A 和 B，对比整体帧时间的变化

验证：优化 A 几乎看不到整体帧时间的变化，优化 B 大幅改善。

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // warmup_detection_improved.cpp — 改进的暖身检测
> // 编译: g++ -std=c++17 warmup_detection_improved.cpp -o warmup_detect && ./warmup_detect
> #include <chrono>
> #include <vector>
> #include <algorithm>
> #include <numeric>
> #include <cmath>
> #include <iostream>
> #include <iomanip>
>
> // 改进的暖身检测：连续 N 个窗口 + 安全边际
> size_t DetectWarmupEndImproved(
>     const std::vector<double>& frame_times,
>     double threshold = 0.15,     // 标准差/均值 < 15%
>     int consecutive_windows = 5, // 连续 N 个窗口满足条件
>     int extra_margin = 10)       // 额外安全边际帧
> {
>     const size_t window = 30;
>     const size_t slide_step = 5; // 每 5 帧滑动一次窗口
>
>     if (frame_times.size() < window * (consecutive_windows + 1)) return 0;
>
>     int satisfied_streak = 0;
>
>     for (size_t i = window; i + window <= frame_times.size(); i += slide_step) {
>         // 计算窗口 [i-window, i) 的均值和标准差
>         double sum = 0.0, sq_sum = 0.0;
>         size_t count = window;
>         for (size_t j = i - window; j < i; j++) {
>             sum += frame_times[j];
>         }
>         double mean = sum / count;
>         for (size_t j = i - window; j < i; j++) {
>             sq_sum += (frame_times[j] - mean) * (frame_times[j] - mean);
>         }
>         double std = std::sqrt(sq_sum / count);
>
>         if (mean > 0.001 && std / mean < threshold) {
>             satisfied_streak++;
>             if (satisfied_streak >= consecutive_windows) {
>                 size_t warmup_end = i + extra_margin;
>                 std::cout << "[Profiler] 暖身检测完成于第 " << i
>                           << " 帧 (连续 " << consecutive_windows
>                           << " 个窗口稳定), "
>                           << "加上 " << extra_margin << " 帧安全边际 → 暖身结束于第 "
>                           << warmup_end << " 帧\n";
>                 return warmup_end;
>             }
>         } else {
>             satisfied_streak = 0; // 不连续，重置
>         }
>     }
>     return 0;
> }
>
> // 模拟前 200 帧波动大、之后趋于稳定的数据
> std::vector<double> GenerateWarmupData(int total_frames) {
>     std::vector<double> data(total_frames);
>     // 模拟 Shader 编译/资源加载: 前 200 帧逐渐稳定
>     for (int i = 0; i < total_frames; i++) {
>         double base = 10.0;
>         if (i < 50)        base = 35.0 - i * 0.5;      // 从 35ms 快速下降
>         else if (i < 120)  base = 12.0 + (rand() % 50) / 10.0; // 波动
>         else if (i < 200)  base = 10.0 + (rand() % 20) / 20.0; // 趋稳
>         else               base = 10.0 + (rand() % 5) / 50.0;  // 稳定
>         data[i] = base;
>     }
>     return data;
> }
>
> int main() {
>     srand(42);
>     auto data = GenerateWarmupData(600);
>     size_t warmup_end = DetectWarmupEndImproved(data, 0.15, 5, 10);
>     if (warmup_end > 0) {
>         std::cout << "测量阶段从第 " << warmup_end << " 帧开始\n";
>     } else {
>         std::cout << "暖身未完成 (数据始终不稳定)\n";
>     }
>     return 0;
> }
> ```
>
> **设计要点：**
> - **连续 N 个窗口**（N=5）确保不是偶发稳定 → 避免"第一个安静窗口就错误触发"
> - **滑动步长**：每 5 帧检查一次，而非每帧，减少计算量
> - **satisfied_streak**：每当窗口不满足条件时重置为 0，保证连续性
> - **额外 M 帧安全边际**：暖身完成后再加 10 帧，确保完全进入稳态
> - **日志输出**：明确告知暖身检测完成于哪一帧

> [!tip]- 练习 2 参考答案
> ```cpp
> // profile_comparator.cpp — 百分位比较工具
> // 编译: g++ -std=c++17 profile_comparator.cpp -o profile_comp && ./profile_comp
> #include <iostream>
> #include <iomanip>
> #include <vector>
> #include <string>
> #include <cmath>
>
> struct ProfileResult {
>     double p50, p75, p90, p95, p99, p999;
> };
>
> // 从排序数组提取百分位
> double Percentile(const std::vector<double>& sorted, double p) {
>     if (sorted.empty()) return 0;
>     double idx = p * (sorted.size() - 1);
>     size_t lo = (size_t)std::floor(idx);
>     size_t hi = (size_t)std::ceil(idx);
>     if (lo == hi) return sorted[lo];
>     return sorted[lo] * (1.0 - (idx - lo)) + sorted[hi] * (idx - lo);
> }
>
> void CompareProfiles(
>     const std::vector<double>& before_sorted,
>     const std::vector<double>& after_sorted)
> {
>     ProfileResult before = {
>         Percentile(before_sorted, 0.50), Percentile(before_sorted, 0.75),
>         Percentile(before_sorted, 0.90), Percentile(before_sorted, 0.95),
>         Percentile(before_sorted, 0.99), Percentile(before_sorted, 0.999)
>     };
>     ProfileResult after = {
>         Percentile(after_sorted, 0.50), Percentile(after_sorted, 0.75),
>         Percentile(after_sorted, 0.90), Percentile(after_sorted, 0.95),
>         Percentile(after_sorted, 0.99), Percentile(after_sorted, 0.999)
>     };
>
>     std::cout << "\n╔══════════════════════════════════════════════════╗\n"
>               << "║         性能对比: Before → After                ║\n"
>               << "╠════════╤══════════╤══════════╤══════════╤════════╣\n"
>               << "║ 百分位 │ Before   │ After    │ 变化     │ 判定   ║\n"
>               << "╟────────┼──────────┼──────────┼──────────┼────────╢\n";
>
>     // 用结构体数组驱动表格
>     struct Row {
>         const char* label;
>         double b, a;
>     } rows[] = {
>         {"P50", before.p50, after.p50},
>         {"P75", before.p75, after.p75},
>         {"P90", before.p90, after.p90},
>         {"P95", before.p95, after.p95},
>         {"P99", before.p99, after.p99},
>         {"P99.9", before.p999, after.p999},
>     };
>
>     for (auto& row : rows) {
>         double change = (row.a - row.b) / row.b * 100.0;
>         const char* flag = "";
>         if (change > 5.0) flag = "⚠️ 回归";  // 变差 > 5%
>         else if (change < -5.0) flag = "✅ 改善";
>         else flag = "— 持平";
>
>         std::cout << "║ " << std::setw(6) << row.label
>                   << " │ " << std::fixed << std::setprecision(2) << std::setw(8) << row.b << "ms"
>                   << " │ " << std::setw(8) << row.a << "ms"
>                   << " │ " << std::setw(7) << std::setprecision(1) << std::showpos << change << "%"
>                   << " │ " << std::setw(6) << flag << " ║\n";
>     }
>     std::cout << "╚════════╧══════════╧══════════╧══════════╧════════╝\n";
> }
>
> int main() {
>     // 模拟数据: Before — 有峰值 (每 30 帧 35ms)
>     std::vector<double> before_data;
>     for (int i = 0; i < 600; i++)
>         before_data.push_back((i % 30 == 0) ? 35.0 : 10.0);
>     std::sort(before_data.begin(), before_data.end());
>
>     // After — 优化后峰值降低到 20ms
>     std::vector<double> after_data;
>     for (int i = 0; i < 600; i++)
>         after_data.push_back((i % 30 == 0) ? 20.0 : 10.0);
>     std::sort(after_data.begin(), after_data.end());
>
>     CompareProfiles(before_data, after_data);
>
>     // 也展示回归场景
>     std::cout << "\n=== 回归示例 (P99 变差) ===\n";
>     std::vector<double> regression;
>     for (int i = 0; i < 600; i++)
>         regression.push_back((i % 30 == 0) ? 45.0 : 10.0);
>     std::sort(regression.begin(), regression.end());
>     CompareProfiles(before_data, regression);
>
>     return 0;
> }
> ```
>
> **设计要点：**
> - 逐百分位比较 P50/P75/P90/P95/P99/P99.9
> - 变化 > 5% 标记为"回归"⚠️，< -5% 标记为"改善"✅
> - 表格化输出，直观展示每个百分位的变化
> - 注意：低百分位（P50）稳定不意味着高百分位（P99）也稳定——这是核心洞察

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // true_vs_false_bottleneck.cpp — 真瓶颈 vs 假瓶颈
> // 编译: g++ -std=c++17 true_vs_false_bottleneck.cpp -o bottleneck_test && ./bottleneck_test
> #include <chrono>
> #include <iostream>
> #include <cmath>
> #include <iomanip>
>
> // 假瓶颈 A: 占帧时间 ~2%
> double FakeBottleneck() {
>     volatile double sum = 0.0;
>     for (int i = 0; i < 100000; i++) {  // 注意: 只有 10 万次
>         sum += std::sin(static_cast<double>(i));
>     }
>     return sum;
> }
>
> // 真瓶颈 B: 占帧时间 ~65%
> double TrueBottleneck() {
>     volatile double sum = 0.0;
>     for (int i = 0; i < 3200000; i++) { // 32 倍于 A
>         sum += std::sin(static_cast<double>(i));
>     }
>     return sum;
> }
>
> double TimeWork(void (*work)()) {
>     auto start = std::chrono::high_resolution_clock::now();
>     work();
>     auto end = std::chrono::high_resolution_clock::now();
>     return std::chrono::duration<double, std::milli>(end - start).count();
> }
>
> int main() {
>     // 测量各组件单独耗时
>     std::cout << "========== 组件单独测量 ==========\n";
>
>     double fake_ms = 0, true_ms = 0, base_ms = 0;
>     const int WARMUP = 3, RUNS = 10;
>
>     // 暖身
>     for (int i = 0; i < WARMUP; i++) { FakeBottleneck(); TrueBottleneck(); }
>
>     for (int i = 0; i < RUNS; i++) fake_ms += TimeWork(FakeBottleneck);
>     fake_ms /= RUNS;
>     for (int i = 0; i < RUNS; i++) true_ms += TimeWork(TrueBottleneck);
>     true_ms /= RUNS;
>
>     // 空帧基准
>     auto empty_work = []{ volatile int x = 0; x++; };
>     for (int i = 0; i < RUNS; i++) base_ms += TimeWork([]{
>         volatile int x = 0; x++;
>     });
>     base_ms /= RUNS;
>
>     double total_no_opt = fake_ms + true_ms;
>     std::cout << std::fixed << std::setprecision(3)
>               << "假瓶颈 A (2% 占比):    " << fake_ms << " ms\n"
>               << "真瓶颈 B (65% 占比):    " << true_ms << " ms\n"
>               << "总帧时间 (无优化):     " << total_no_opt << " ms\n"
>               << "A 占比: " << std::setprecision(1) << (fake_ms / total_no_opt * 100) << "%\n"
>               << "B 占比: " << (true_ms / total_no_opt * 100) << "%\n\n";
>
>     // 模拟"优化" A (将 A 的迭代次数减半)
>     std::cout << "========== 模拟优化 ==========\n";
>     auto FakeBottleneckOptimized = []() {
>         volatile double sum = 0.0;
>         for (int i = 0; i < 50000; i++) sum += std::sin(static_cast<double>(i));
>     };
>     auto TrueBottleneckOptimized = []() {
>         volatile double sum = 0.0;
>         for (int i = 0; i < 1600000; i++) sum += std::sin(static_cast<double>(i));
>     };
>
>     double fake_opt_ms = 0, true_opt_ms = 0;
>     for (int i = 0; i < RUNS; i++) fake_opt_ms += TimeWork(FakeBottleneckOptimized);
>     fake_opt_ms /= RUNS;
>     for (int i = 0; i < RUNS; i++) true_opt_ms += TimeWork(TrueBottleneckOptimized);
>     true_opt_ms /= RUNS;
>
>     double opt_a_total = fake_opt_ms + true_ms;
>     double opt_b_total = fake_ms + true_opt_ms;
>
>     std::cout << "优化 A 后总帧时间: " << opt_a_total << " ms"
>               << " (改善 " << ((total_no_opt - opt_a_total) / total_no_opt * 100) << "%)\n"
>               << "优化 B 后总帧时间: " << opt_b_total << " ms"
>               << " (改善 " << ((total_no_opt - opt_b_total) / total_no_opt * 100) << "%)\n\n";
>
>     std::cout << "========== 结论 ==========\n"
>               << "优化假瓶颈 A → 几乎无感知改进 (最大理论收益 ~2%)\n"
>               << "优化真瓶颈 B → 显著改进 (理论收益 ~65%)\n"
>               << "这就是 Amdahl 定律在实际中的体现。\n";
>     return 0;
> }
> ```
>
> **关键发现：**
> - 假瓶颈 A 占帧时间 ~2%（100,000 次 sin），真瓶颈 B 占 ~65%（3,200,000 次 sin）
> - 优化 A 对整体帧时间几乎无影响；优化 B 大幅改善
> - 在没有 Profiler 的情况下，直觉常把代码量多但执行少的路径误判为瓶颈
> - **核心教训**：永远先测量，后用 Amdahl 定律评估优化潜力

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- [How NOT to Measure Latency — Gil Tene (Strangeloop)](https://www.youtube.com/watch?v=lJ8ydIuPFeU) — 测量延迟的经典演讲，包含 Coordinated Omission 问题
- [The AMD64 Architecture Programmer's Manual, Vol 2: System Programming — Chapter on Performance Monitoring](https://www.amd.com/en/search/documentation/hub.html)
- [perf Examples — Brendan Gregg](https://www.brendangregg.com/perf.html) — Linux perf 工具的圣经级教程
- [Statistical Performance Analysis — Andrei Alexandrescu (code::dive)](https://www.youtube.com/watch?v=koTf7u0v41o) — C++ 性能测量的统计方法

---

## 常见陷阱

- **不做暖身直接测量**：第一帧通常包含 Shader 编译、资源加载、JIT 预热等一次性开销。把前 50-200 帧直接丢弃，否则你的"平均帧时间"会被首帧严重污染。同理，第一次运行测试时，操作系统可能还在从磁盘加载可执行文件到页缓存。

- **样本量不足**：只测 10 帧，得到一个"平均 15ms"。下次再测 10 帧，得到"平均 17ms"。你无法判断这是真实变化还是随机波动。至少 300-1000 帧才能得到有统计意义的结果。

- **在 Debug 模式或带调试器附加的情况下测量**：Debug 构建不优化，有额外的安全检查。调试器附加会严重拖慢程序。永远在 Release 模式下、不附加调试器的情况下测量。

- **忽略环境变量**：不同的电源模式（省电 vs 高性能）、后台进程（杀毒软件扫描、Windows Update）、CPU 温度（过热降频）都会影响测量。在测量前，确保：高性能电源计划、关闭不必要后台程序、让 CPU 温度稳定。

- **协程遗漏 (Coordinated Omission)**：如果你的测量循环是"做工作 → 记时间 → 做工作 → 记时间"，长期运行后高延迟操作会"挤出"低延迟操作被记录的机会。正确处理方式：记录的是"从预约到完成的时间"，而不是"从上一帧完成到这一帧完成的时间"。这是性能测量中最隐蔽的陷阱之一。
