---
title: "为什么要优化 — 性能优化的经济学与时机"
updated: 2026-06-05
---

# 为什么要优化 — 性能优化的经济学与时机

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要这个？

想象你在做一个 3D 游戏。美术给你一个场景，里面放了 500 棵树，每棵树用 2000 个三角形。你把它扔进引擎，按下 Play — 帧率只有 18fps。玩家转动视角时画面卡成幻灯片。为什么？

因为**性能预算**是真实存在的硬约束。

在 60fps 的目标下，每一帧只有 **16.66 毫秒**。这不是建议，是物理限制：1秒 ÷ 60帧 = 16.66ms。在 30fps 下是 33.33ms，在 120fps 下只有 8.33ms。这个预算必须覆盖**所有**工作 — 游戏逻辑、物理模拟、AI、动画、渲染提交、GPU 渲染、音频、网络同步。

一个 Draw Call（向 GPU 提交一次绘制指令）在 CPU 端大约消耗 **5–50μs**（取决于 API、驱动、平台）。5000 个 Draw Call 在最坏情况下就是 `5000 × 50μs = 250ms` — 你已经用了 15 帧的预算，但只做了渲染提交，GPU 还没开始干活。

这就是性能问题的本质：**你没有无限的时间，每一项操作都在从同一个预算中支取。**

更重要的是，性能问题有复利效应。当帧率从 60 掉到 30，玩家体验已经严重恶化；但从 30 掉到 15 的体感差异更大。而最糟糕的是：**帧率不稳定比低帧率更令人难受**。40fps 每帧均匀 25ms 的体验远比 60fps 但每 3 帧有一帧卡 50ms 的体验好。

#### 如果不优化会怎样？

| 后果 | 影响 |
|------|------|
| 玩家流失 | Steam 评价"优化稀烂"是销售杀手 |
| 平台审核失败 | 主机平台有最低帧率要求（通常 30fps 稳定） |
| VR 不可用 | VR 需要稳定 72–120fps，低于此值用户会晕动症 |
| 手机发烫/耗电 | CPU/GPU 满负载导致降频，帧率进一步下降 |
| 维护成本爆炸 | 补丁式"修一个卡一个"的游戏后期无解 |

### 核心思想

**性能优化不是事后的救火行动，而是贯穿整个开发周期的预算管理。** 就像你不会在房子盖完之后才发现地基歪了，你不应该在游戏快发布时才开始考虑性能。

优化有它自己的金字塔：

```
        ┌──────────────┐
        │  验证 (Verify) │  ← 确认改对了，没引入新问题
        ├──────────────┤
        │  修复 (Fix)    │  ← 实施最小改动
        ├──────────────┤
        │  定位 (Locate) │  ← 找到瓶颈 — 可能是出乎意料的地方
        ├──────────────┤
        │  测量 (Measure)│  ← 量化当前状态，建立基线
        └──────────────┘
```

这个金字塔的底座是**测量**。没有数值的优化是盲人摸象。你觉得"这个循环很慢" — 慢多少？占帧时间的 0.1% 还是 80%？优化 0.1% 的代码不会带来任何可感知的改进。这就是 Amdahl 定律的核心：**加速比受限于被优化部分的占比**。如果你只能优化占运行时间 5% 的代码，即使把它变成零时间，整体加速比也只有 `1 / (1 - 0.05) ≈ 1.053`，即 5.3% 的提升。

#### Knuth 的名言：放在正确的语境里理解

> "过早的优化是万恶之源。" — Donald Knuth

这句话被滥用了。Knuth 说的"过早优化"是指**在没有测量数据的情况下，为了微小的理论性能收益而牺牲代码清晰度**。他不是说不要考虑性能 — 事实上，在同一篇文章里他还写道：

> "我们应该忘记小的效率，大约 97% 的时间。过早优化是万恶之源。**但我们不应该放弃那关键的 3% 的机会。**"

在游戏开发中，"那 3%"几乎总是存在的。渲染循环、物理更新、资源加载 — 这些是游戏的命脉。在这些地方做架构决策时**必须**考虑性能。这不是"过早"的优化，而是正确的工程设计。

#### 什么时候该优化？

按项目阶段：

| 阶段 | 策略 |
|------|------|
| **预研/原型** | 验证核心性能假设即可："我们能不能在场景中放 1000 个单位？" |
| **中期开发** | 建立自动化性能测试基线，每次功能合入时检查帧时间是否退化 |
| **Alpha** | 系统的 Profiling 和瓶颈分析。此时所有功能大致完成，但数据量可能不足 |
| **Beta** | 全力以赴 — 此时的数据量最接近最终产品。修复瓶颈、降级策略、平台适配 |
| **发布后** | 基于真实用户数据（Telemetry）的定向优化 |

**黄金法则：永远基于测量数据做决策。** 这句话值得重复三遍。

---

## 2. 代码示例

以下是一个完整的 C++ 帧预算监控器。它测量每帧的耗时，当帧时间超过 16.6ms 时发出警告，并记录帧时间分布统计。

```cpp
// frame_budget.h — 帧预算监控器
#pragma once

#include <chrono>
#include <vector>
#include <algorithm>
#include <numeric>
#include <string>
#include <iostream>
#include <iomanip>
#include <cmath>

class FrameBudget {
public:
    using Clock = std::chrono::high_resolution_clock;
    using TimePoint = Clock::time_point;
    using Duration = std::chrono::duration<double, std::milli>;  // 以毫秒为单位

    explicit FrameBudget(double target_fps = 60.0, size_t history_size = 300)
        : target_frame_time_(1000.0 / target_fps)
        , history_size_(history_size)
    {
        frame_times_.reserve(history_size_);
    }

    // 在帧开始时调用
    void BeginFrame() {
        frame_start_ = Clock::now();
    }

    // 在帧结束时调用，返回本帧耗时（毫秒）
    double EndFrame() {
        auto frame_end = Clock::now();
        double elapsed = Duration(frame_end - frame_start_).count();

        frame_times_.push_back(elapsed);
        if (frame_times_.size() > history_size_) {
            frame_times_.erase(frame_times_.begin());
        }

        frame_count_++;

        if (elapsed > target_frame_time_) {
            over_budget_count_++;
            // 只在刚超过预算的瞬间或每 60 帧报告一次，避免日志洪水
            if (over_budget_count_ == 1 || frame_count_ % 60 == 0) {
                ReportOverBudget(elapsed);
            }
        }

        return elapsed;
    }

    // 统计信息
    struct Stats {
        double min_ms;
        double max_ms;
        double mean_ms;
        double median_ms;
        double p99_ms;        // 99th 百分位
        double budget_ms;     // 目标帧时间
        size_t sample_count;
        size_t over_budget_count;
        double over_budget_pct;
    };

    Stats GetStats() const {
        Stats s = {};
        if (frame_times_.empty()) return s;

        // 在当前窗口上操作（拷贝一份排序用于中位数和百分位）
        std::vector<double> sorted = frame_times_;
        std::sort(sorted.begin(), sorted.end());

        s.min_ms = sorted.front();
        s.max_ms = sorted.back();
        s.mean_ms = std::accumulate(sorted.begin(), sorted.end(), 0.0) / sorted.size();

        size_t n = sorted.size();
        s.median_ms = (n % 2 == 0)
            ? (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
            : sorted[n / 2];

        // p99: 排序数组的 99% 索引
        size_t p99_idx = static_cast<size_t>(std::ceil(n * 0.99)) - 1;
        if (p99_idx >= n) p99_idx = n - 1;
        s.p99_ms = sorted[p99_idx];

        s.budget_ms = target_frame_time_;
        s.sample_count = n;
        s.over_budget_count = over_budget_count_;
        s.over_budget_pct = (n > 0)
            ? 100.0 * over_budget_count_ / n
            : 0.0;

        return s;
    }

    void Reset() {
        frame_times_.clear();
        over_budget_count_ = 0;
        frame_count_ = 0;
    }

private:
    void ReportOverBudget(double elapsed) {
        double excess = elapsed - target_frame_time_;
        std::cerr << "[FrameBudget] 帧超预算! "
                  << std::fixed << std::setprecision(2)
                  << "实际: " << elapsed << "ms, "
                  << "预算: " << target_frame_time_ << "ms, "
                  << "超出: " << excess << "ms ("
                  << std::setprecision(1) << (excess / target_frame_time_ * 100.0)
                  << "%)\n";
    }

    TimePoint frame_start_;
    std::vector<double> frame_times_;
    size_t history_size_;
    size_t frame_count_ = 0;
    size_t over_budget_count_ = 0;
    double target_frame_time_;
};

// ==================== 使用示例 ====================

// 模拟游戏逻辑：有些帧做"重活"，有些帧做"轻活"
void SimulateGameWork(int frame_index) {
    // 模拟：每 30 帧有一次"重"操作（比如 GC 触发、大量 AI 更新）
    if (frame_index % 30 == 0) {
        // 忙等待约 25ms — 模拟昂贵的操作
        auto start = std::chrono::high_resolution_clock::now();
        while (true) {
            auto now = std::chrono::high_resolution_clock::now();
            double ms = std::chrono::duration<double, std::milli>(now - start).count();
            if (ms >= 25.0) break;
        }
    } else {
        // 正常帧约 8ms 的工作
        auto start = std::chrono::high_resolution_clock::now();
        while (true) {
            auto now = std::chrono::high_resolution_clock::now();
            double ms = std::chrono::duration<double, std::milli>(now - start).count();
            if (ms >= 8.0) break;
        }
    }
}

void PrintStats(const FrameBudget::Stats& s) {
    std::cout << "\n========== 帧时间统计 ==========\n"
              << std::fixed << std::setprecision(2)
              << "  样本数:      " << s.sample_count << "\n"
              << "  目标帧时间:  " << s.budget_ms << "ms\n"
              << "  最小:        " << s.min_ms << "ms\n"
              << "  最大:        " << s.max_ms << "ms\n"
              << "  均值:        " << s.mean_ms << "ms\n"
              << "  中位数:      " << s.median_ms << "ms\n"
              << "  P99:         " << s.p99_ms << "ms\n"
              << "  超预算次数:  " << s.over_budget_count
                  << " (" << std::setprecision(1) << s.over_budget_pct << "%)\n";
}

int main() {
    FrameBudget budget(60.0);  // 目标 60fps → 16.67ms 预算

    std::cout << "模拟 300 帧游戏循环...\n";
    std::cout << "每 30 帧有一次 25ms 的峰值操作\n\n";

    for (int i = 0; i < 300; i++) {
        budget.BeginFrame();
        SimulateGameWork(i);
        budget.EndFrame();
    }

    PrintStats(budget.GetStats());

    return 0;
}
```

**运行方式:**

```bash
# 使用任何 C++17 编译器
g++ -std=c++17 -O2 frame_budget.cpp -o frame_budget
./frame_budget

# 或使用 MSVC
cl /std:c++17 /O2 frame_budget.cpp
frame_budget.exe
```

**预期输出:**

```text
模拟 300 帧游戏循环...
每 30 帧有一次 25ms 的峰值操作

[FrameBudget] 帧超预算! 实际: 25.00ms, 预算: 16.67ms, 超出: 8.33ms (50.0%)

========== 帧时间统计 ==========
  样本数:      300
  目标帧时间:  16.67ms
  最小:        8.00ms
  最大:        25.00ms
  均值:        8.57ms
  中位数:      8.00ms
  P99:         25.00ms
  超预算次数:  10 (3.3%)
```

注意：均值只有 8.57ms — 看起来很健康。但 P99 是 25ms — **3.3% 的帧超过了 16.67ms 预算**。这在游戏中意味着每 30 帧有一个可感知的卡顿。这说明为什么只看平均值是危险的。

---

## 3. 练习

### 练习 1: 写一个带分级警告的预算监控器

扩展上面的 `FrameBudget` 类，增加**分级警告**：
- 帧时间超过预算 10%：黄色警告（"轻微超预算"）
- 帧时间超过预算 50%：红色警告（"严重超预算"）
- 连续 5 帧超过预算：触发"持续降帧"报警

运行 500 帧模拟，其中每 20 帧随机生成一个 10-30ms 的帧时间，验证分级警告是否正确触发。

**验收标准：** 程序输出中能看到三种不同级别的警告信息，且统计中"轻微"和"严重"超预算的计数正确。

### 练习 2: 性能预算计算器

写一个工具函数，输入：
- 目标帧率 （如 60、120、144）
- 各项系统的预计耗时列表（如：Render=8ms, Physics=3ms, AI=2ms, Audio=1ms, UI=1ms）

输出：
- 总预算
- 各项占比（百分比条形图 — ASCII 即可）
- 如果某项超过预算的 50%，给出红色警告
- 剩余预算 （"slack time"）

```cpp
// 接口建议
void AnalyzeBudget(double target_fps,
                   const std::vector<std::pair<std::string, double>>& systems);
```

**验收标准：** 输入一个明显超预算的系统配置（如目标 60fps，但 Render=12ms, Physics=8ms），程序应正确识别并警告。

### 练习 3: 构建一个帧方差分析器（可选）

扩展 `FrameBudget`，实现：
- 计算帧时间的**标准差**（standard deviation）
- 计算 **jank rate** — 连续两帧之间帧时间差异超过 8ms 的比例（这是 Google 在 Android 上定义卡顿的阈值）
- 输出一个简单的 ASCII 直方图（用 `#` 字符表示帧时间分布，分 10 个桶，范围从 min 到 max）

用这个分析器测试三种不同的"负载模式"：
1. **均匀负载** — 每帧固定 10ms
2. **周期峰值** — 每 15 帧有一个 30ms 峰值
3. **随机抖动** — 帧时间在 5-20ms 之间均匀随机分布

比较三种模式的 jank rate。

---

## 4. 扩展阅读

- [The Performance Budget — Addy Osmani](https://addyosmani.com/blog/performance-budgets/) (Web 视角，但预算概念通用)
- [Knuth, "Structured Programming with go to Statements" (1974)](https://dl.acm.org/doi/10.1145/356635.356640) — "过早优化"名言的原出处
- [Game Performance: The Frame Budget — GDC Vault](https://www.gdcvault.com/) — 搜索 "frame budget" 相关演讲
- [Inside the Windows Performance Toolkit — Bruce Dawson](https://randomascii.wordpress.com/) — PPT 大师的随机 ASCII 博客，游戏性能测量圣经

---

## 常见陷阱

- **只看平均值忽略 P99**：平均值 8ms 看起来很安全，但 P99 可能是 45ms — 意味着每 100 帧有一帧卡到 45ms，玩家能明显感知。永远看分布，不要只看均值。

- **在 Debug 构建下做性能测试**：Debug 模式的优化关闭、断言开启，帧时间可能是 Release 的 3-10 倍。优化决策必须基于 Release 构建（或至少 RelWithDebInfo）的数据。

- **"我觉得这里慢"而没有数据**：直觉在性能领域经常出错。CPU 的分支预测、缓存预取、编译器优化 — 这些对你来说是黑盒。没有 Profiler 的"优化"更像掷骰子。

- **过早优化的真正含义被曲解**：不在循环里用 `std::map` 做 O(log n) 查找而用 `std::unordered_map` 做 O(1) 查找，这不是"过早优化" — 这是正确的数据结构选择。"过早优化"是指你花三天手写了一段 SIMD 汇编来优化一个占总运行时间 0.3% 的函数。

- **优化后不再验证**：你改了代码，性能"看起来好了"。但你真的测量了吗？新代码可能因为改变了内存布局而让另一个 hotspot 变慢了两倍。优化要形成闭环：测量 → 定位 → 修复 → **再测量**。
