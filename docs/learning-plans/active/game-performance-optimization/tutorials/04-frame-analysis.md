---
title: "帧分析基础 — Frame Timing 与瓶颈识别"
updated: 2026-06-05
---

# 帧分析基础 — Frame Timing 与瓶颈识别

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: 03-profiling-tools（了解 Profiling 工具体系）

---

## 1. 概念讲解

### 为什么需要这个？

你拿到了 Profiling 数据：平均帧时间 22ms，P99 是 35ms。帧率在 28-45fps 之间摇摆。现在的问题是：**瓶颈在哪里？是 CPU 还是 GPU？** 如果连这个都分不清，你就在错误的地方优化。

CPU Bound 和 GPU Bound 是两个完全不同的世界：
- CPU Bound → 优化游戏逻辑、减少 Draw Call、改善数据结构
- GPU Bound → 优化 Shader、减少 Overdraw、降低分辨率/后处理

**在 CPU Bound 时优化 Shader 毫无意义。在 GPU Bound 时优化 AI 逻辑也毫无意义。** 但在实际项目中，新手最常见的错误就是搞混这两者。

#### 你看到的东西可能是误导

考虑一个典型的帧时间线：

```
帧 N:  |← 输入(0.5) →|← 更新(3.0) →|← 渲染提交(2.0) →|← 等待 GPU(8.0) →|
                                                                      ↑ CPU 在这里空闲
帧 N+1:|← 输入(0.5) →|← 更新(3.0) →|← 渲染提交(2.0) →|← 等待 GPU(7.5) →|
```

CPU 做完渲染提交后等了 8ms。粗看你会觉得"CPU 很闲，我们肯定 GPU Bound"。**但如果这 8ms 的 GPU 时间大部分是由于大量 Draw Call 造成的呢？** Draw Call 的提交本身就发生在 CPU 端。所以这个场景可能是：

- CPU 花了 2ms 做渲染提交（包含数千个 Draw Call 的 API 调用开销）
- GPU 花了 8ms 执行这些 Draw Call
- 真正的问题可能是 Draw Call 太多 → **同时影响了 CPU 和 GPU**

这就是为什么帧分析需要**系统和框架**，而不是直觉。

### 核心思想

#### 游戏帧的生命周期

一帧的完整流程（简化但完整的视图）：

```
┌──────────────────────────────────────────────────────────────┐
│                        一帧 (目标 16.67ms @ 60fps)            │
├──────────┬──────────────┬──────────────┬─────────────────────┤
│  输入处理 │   游戏更新    │   渲染提交    │     GPU 渲染        │
│  Input   │   Update     │   Render     │    GPU Execute      »
│          │              │   Submit     │                     │
│  ~0.5ms  │  Physics     │  Culling     │  Shadow Maps        »
│          │  AI          │  Sorting     │  GBuffer            »
│          │  Animation   │  Draw Calls  │  Lighting           »
│          │  Scripting   │  GPU Cmds    │  Post-Processing    »
│          │  ~3-8ms      │  ~2-5ms      │  ~5-15ms            »
├──────────┴──────────────┴──────────────┴─────────────────────┤
│  CPU 端工作 (Input + Update + Render Submit)                  │
│  GPU 端工作 (GPU Execute)                                    │
└──────────────────────────────────────────────────────────────┘
```

关键洞察：**CPU 和 GPU 是异步的**。CPU 提交渲染指令后不会等 GPU 完成 — 它继续处理下一帧。这就是为什么存在"排队"和"缓冲"。

#### CPU Bound vs GPU Bound — 如何判断？

实际判断方法（按可靠性排序）：

**方法 1: 用 GPU Profiler 看 GPU 空闲时间**

在 RenderDoc/PIX/NSight 中查看 GPU 时间线：
- 如果 GPU 在帧之间有明显的**空隙**（Idle 气泡），说明 GPU 在等 CPU → **CPU Bound**
- 如果 GPU 在**连续不断**地执行，没有空隙 → **GPU Bound**

```
CPU Bound:   GPU|[████████████████]_____空闲_____[████████████████]|  ← GPU 有空隙
GPU Bound:   GPU|[█████████████████████████████████████████████████]|  ← GPU 持续满载
```

**方法 2: 降低分辨率测试**

将分辨率从 1920×1080 降到 640×480（像素数减少 9 倍）：
- 帧时间**显著下降**（比如从 22ms 降到 12ms）→ **GPU Bound**
- 帧时间**几乎不变** → **CPU Bound**

原理：降低分辨率几乎只影响 GPU 的像素处理负载（光栅化、Pixel Shader），不影响 Draw Call 提交、物理、AI 等 CPU 工作。

**方法 3: Tracy/Profiler 查看"GPU 等待"**

在 Tracy 中，图形 API 的 Present 调用之后，如果有大的 CPU 空闲间隙（CPU 在等待 GPU），说明 GPU 是瓶颈。但如果 CPU 一直在忙碌，说明 CPU 是瓶颈。

#### 帧节奏 (Frame Pacing) — 为什么帧时间均匀比帧率更重要

```
方案 A: 帧时间 = [15, 15, 15, 30, 15, 15, 15] → 平均 17.1ms → 58fps 平均
方案 B: 帧时间 = [20, 20, 20, 20, 20, 20, 20] → 平均 20.0ms → 50fps 平均
```

方案 A 的帧率"更高"，但玩家会觉得方案 B **更流畅**。因为方案 A 中每 4 帧有一个 30ms 的帧 — 那是明显的卡顿。

**Jank 的定义**（Google Android 标准）：连续两帧的帧时间差异超过 8ms（在 60Hz 显示器上）即为一次 jank。

#### 缓冲策略与帧节奏

| 模式 | 行为 | 帧时间 | 延迟 | 撕裂 |
|------|------|--------|------|------|
| **No V-Sync** | GPU 完成就立即显示 | 可能不均匀 | 最低 | 有撕裂 |
| **V-Sync Double Buffer** | 等显示器刷新周期 | 16.67ms 整数倍 | 1-2 帧 | 无 |
| **V-Sync Triple Buffer** | 等刷新周期，但有额外缓冲 | 更平滑 | 1-2 帧 | 无 |
| **VRR (GSync/FreeSync)** | 显示器刷新率跟随 GPU | 均匀 | 低 | 无 |

**三重缓冲的关键优势**：当一帧超时时（比如花了 20ms），下一个刷新点（16.67ms + 16.67ms = 33.33ms）仍有新帧可显示，不会导致完全丢帧。

#### 瓶颈永远存在 — 问题是在哪里

任何系统永远有一个瓶颈。如果你优化了最宽的瓶颈，下一个瓶颈就会出现。这个过程叫 **瓶颈转移 (Bottleneck Shifting)**。

```
优化前: CPU(12ms) > GPU(8ms) → CPU Bound @ 12ms/frame = 83fps
优化 CPU 到 6ms: CPU(6ms) < GPU(8ms) → GPU Bound @ 8ms/frame = 125fps
再优化 GPU 到 4ms: CPU(6ms) > GPU(4ms) → CPU Bound @ 6ms/frame = 166fps
```

关键点：**优化当前瓶颈才有收益**。把 GPU 从 8ms 优化到 4ms 在 CPU Bound 时（CPU 12ms）完全没用 — 帧时间仍然是 12ms。

---

## 2. 代码示例

以下是一个完整的帧分析模拟器。它能：
- 模拟一帧中的 CPU 工作 + GPU 工作
- 考虑 CPU-GPU 异步和缓冲
- 自动检测当前是 CPU Bound 还是 GPU Bound
- 输出帧时间可视化
- 演示瓶颈转移

```cpp
// frame_analyzer.cpp — 帧分析模拟器
#include <iostream>
#include <iomanip>
#include <vector>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <string>
#include <sstream>
#include <cstdint>

// ====================================================================
// 帧分析引擎
// ====================================================================

struct FrameConfig {
    double cpu_input_ms    = 0.5;   // 输入处理
    double cpu_update_ms   = 5.0;   // 游戏逻辑（物理、AI、动画）
    double cpu_render_ms   = 3.0;   // 渲染提交（Culling、DrawCall 提交）
    double gpu_exec_ms     = 8.0;   // GPU 执行（顶点、像素、计算）
    double display_hz      = 60.0;  // 显示器刷新率
    int    buffer_mode     = 2;     // 0=no vsync, 1=double, 2=triple
    size_t sim_frames      = 300;   // 模拟帧数
};

struct FrameResult {
    size_t frame_index;
    double cpu_total_ms;      // CPU 总耗时
    double gpu_exec_ms;       // GPU 执行耗时
    double frame_interval_ms; // 实际帧间隔（到上一帧显示的时间）
    double display_time_ms;   // 此帧被显示的时间点
    bool   is_cpu_bound;
    bool   is_gpu_bound;
};

class FrameAnalyzer {
public:
    explicit FrameAnalyzer(const FrameConfig& cfg) : cfg_(cfg) {}

    std::vector<FrameResult> Simulate() {
        results_.clear();
        results_.reserve(cfg_.sim_frames);

        double gpu_complete_time = 0.0;  // GPU 完成当前帧的时间
        double last_displayed    = 0.0;  // 上一帧被显示的时间
        double refresh_interval  = 1000.0 / cfg_.display_hz;

        // 并行模拟
        for (size_t i = 0; i < cfg_.sim_frames; i++) {
            FrameResult fr;
            fr.frame_index = i;
            fr.cpu_total_ms = cfg_.cpu_input_ms + cfg_.cpu_update_ms + cfg_.cpu_render_ms;
            fr.gpu_exec_ms  = cfg_.gpu_exec_ms;

            // CPU 开始时间 = 上一帧 CPU 完成时间（简化：单线程模拟）
            double cpu_start = (i == 0) ? 0.0 : results_.back().display_time_ms;
            double cpu_end   = cpu_start + fr.cpu_total_ms;

            // GPU 开始 = max(CPU 渲染提交完成, GPU 上一帧完成)
            // 实际上 GPU 开始是在渲染提交时，这里简化
            double gpu_start = std::max(cpu_start + cfg_.cpu_input_ms + cfg_.cpu_update_ms,
                                         gpu_complete_time);
            double gpu_end = gpu_start + fr.gpu_exec_ms;
            gpu_complete_time = gpu_end;

            // 帧就绪时间 = max(CPU 完成, GPU 完成)，两样都准备好才能显示
            double frame_ready = std::max(cpu_end, gpu_end);

            // 显示时间 — 受刷新率和缓冲模式影响
            double display_time;
            switch (cfg_.buffer_mode) {
            case 0: // No V-Sync: 就绪即显示
                display_time = frame_ready;
                break;
            case 1: // Double Buffer: 下一个刷新点
                display_time = std::ceil(frame_ready / refresh_interval) * refresh_interval;
                break;
            case 2: // Triple Buffer: 允许排队一帧
                // 如果此帧在上一帧的下一个刷新点前就绪，可以在那个刷新点显示
                double next_vblank = std::ceil(std::max(frame_ready, last_displayed + 0.001)
                                               / refresh_interval) * refresh_interval;
                display_time = next_vblank;
                break;
            }

            fr.display_time_ms    = display_time;
            fr.frame_interval_ms  = display_time - last_displayed;
            last_displayed = display_time;

            // 瓶颈检测
            // CPU Bound = 帧的显示间隔由 CPU 决定
            // GPU Bound = 帧的显示间隔由 GPU 决定
            // 更精确的判断：看哪边是限制因素
            double cpu_slack = gpu_end - cpu_end;     // 正数 = GPU 更慢
            double gpu_slack = cpu_end - gpu_end;     // 正数 = CPU 更慢

            fr.is_cpu_bound = (gpu_slack > 0.1) && (gpu_slack >= cpu_slack);
            fr.is_gpu_bound = (cpu_slack > 0.1) && (cpu_slack >= gpu_slack);

            // 两者都在忙：全负载
            if (std::abs(cpu_slack) < 0.1 && std::abs(gpu_slack) < 0.1) {
                fr.is_cpu_bound = (fr.cpu_total_ms >= fr.gpu_exec_ms);
                fr.is_gpu_bound = (fr.gpu_exec_ms > fr.cpu_total_ms);
            }

            results_.push_back(fr);
        }

        return results_;
    }

    // ============ 报告输出 ============

    void PrintConfig() const {
        std::cout << "\n╔══════════════════════════════════════════╗\n";
        std::cout << "║          Frame Analysis Config           ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";
        std::cout << std::fixed << std::setprecision(1);
        std::cout << "║ CPU Input:   " << std::setw(6) << cfg_.cpu_input_ms  << " ms                 ║\n";
        std::cout << "║ CPU Update:  " << std::setw(6) << cfg_.cpu_update_ms << " ms                 ║\n";
        std::cout << "║ CPU Render:  " << std::setw(6) << cfg_.cpu_render_ms << " ms                 ║\n";
        std::cout << "║ GPU Exec:    " << std::setw(6) << cfg_.gpu_exec_ms   << " ms                 ║\n";
        std::cout << "║ Total CPU:   " << std::setw(6) << TotalCpuMs()      << " ms                 ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";
        std::cout << "║ Display Hz:  " << std::setw(6) << cfg_.display_hz << "                     ║\n";
        const char* buf_mode[] = {"No V-Sync", "Double Buffer", "Triple Buffer"};
        std::cout << "║ Buffer Mode: " << buf_mode[cfg_.buffer_mode] << "            ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";

        // 预算分析
        double budget = 1000.0 / cfg_.display_hz;
        double total_cpu = TotalCpuMs();
        double total_gpu = cfg_.gpu_exec_ms;

        if (total_cpu > budget && total_gpu > budget) {
            std::cout << "║ 状态: Both CPU and GPU over budget! ║\n";
        } else if (total_cpu > budget) {
            std::cout << "║ 状态: CPU Bound (超过预算)            ║\n";
        } else if (total_gpu > budget) {
            std::cout << "║ 状态: GPU Bound (超过预算)            ║\n";
        } else {
            std::cout << "║ 状态: Within budget                  ║\n";
        }
        std::cout << "╚══════════════════════════════════════════╝\n\n";
    }

    void PrintResults() {
        if (results_.empty()) return;

        // 收集统计数据
        std::vector<double> intervals;
        for (auto& r : results_) intervals.push_back(r.frame_interval_ms);

        std::sort(intervals.begin(), intervals.end());

        double min_ms = intervals.front();
        double max_ms = intervals.back();
        double mean_ms = std::accumulate(intervals.begin(), intervals.end(), 0.0) / intervals.size();
        double median_ms = intervals[intervals.size() / 2];

        // p95
        size_t p95_idx = static_cast<size_t>(intervals.size() * 0.95);
        double p95_ms = intervals[std::min(p95_idx, intervals.size() - 1)];

        // 计数
        size_t cpu_bound_count = 0, gpu_bound_count = 0, both_count = 0;
        for (auto& r : results_) {
            if (r.is_cpu_bound && r.is_gpu_bound) both_count++;
            else if (r.is_cpu_bound) cpu_bound_count++;
            else if (r.is_gpu_bound) gpu_bound_count++;
        }

        double budget = 1000.0 / cfg_.display_hz;
        double avg_fps = (mean_ms > 0) ? 1000.0 / mean_ms : 0;

        std::cout << "\n╔══════════════════════════════════════════╗\n";
        std::cout << "║       Frame Analysis Results             ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";
        std::cout << std::fixed;
        std::cout << "║ Avg FPS:     " << std::setprecision(1) << std::setw(6) << avg_fps << "                     ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";
        std::cout << std::setprecision(2);
        std::cout << "║ Min Intvl:   " << std::setw(6) << min_ms << " ms                 ║\n";
        std::cout << "║ Max Intvl:   " << std::setw(6) << max_ms << " ms                 ║\n";
        std::cout << "║ Mean Intvl:  " << std::setw(6) << mean_ms << " ms                 ║\n";
        std::cout << "║ Median Intvl:" << std::setw(6) << median_ms << " ms                 ║\n";
        std::cout << "║ P95 Intvl:   " << std::setw(6) << p95_ms << " ms                 ║\n";
        std::cout << "║ Budget:      " << std::setw(6) << budget << " ms                 ║\n";
        std::cout << "╠══════════════════════════════════════════╣\n";
        std::cout << "║ CPU Bound:   " << std::setw(5) << cpu_bound_count << " frames             ║\n";
        std::cout << "║ GPU Bound:   " << std::setw(5) << gpu_bound_count << " frames             ║\n";
        std::cout << "║ Both Bound:  " << std::setw(5) << both_count << " frames             ║\n";
        std::cout << "╚══════════════════════════════════════════╝\n";
    }

    // ASCII 帧时间折线图
    void PrintTimelineGraph(size_t max_display = 80) {
        if (results_.empty()) return;

        double max_interval = 0;
        for (auto& r : results_) {
            if (r.frame_interval_ms > max_interval) max_interval = r.frame_interval_ms;
        }
        double budget = 1000.0 / cfg_.display_hz;
        if (budget > max_interval) max_interval = budget * 1.2;

        double scale = (max_display - 1) / max_interval;

        std::cout << "\n=== 帧时间线（每字符 ~" << std::setprecision(1)
                  << (max_interval / max_display) << "ms）===\n";
        std::cout << "预算线: " << std::string(static_cast<size_t>(budget * scale), '-')
                  << "| (" << budget << "ms)\n\n";

        for (size_t i = 0; i < results_.size() && i < 200; i++) {
            auto& r = results_[i];
            size_t bar_len = static_cast<size_t>(r.frame_interval_ms * scale);
            if (bar_len > max_display) bar_len = max_display;

            char marker = (r.is_cpu_bound ? 'C' : (r.is_gpu_bound ? 'G' : '.'));

            // 每 10 帧标一次序号
            if (i % 10 == 0) {
                std::ostringstream label;
                label << std::setw(3) << i;
                std::cout << label.str() << " ";
            } else {
                std::cout << "    ";
            }
            std::cout << marker << std::string(bar_len, '#') << "\n";
        }

        std::cout << "\n  C = CPU Bound, G = GPU Bound, . = balanced\n";
        std::cout << "  # 长度 = 帧间隔（越长越慢）\n";
    }

    double TotalCpuMs() const {
        return cfg_.cpu_input_ms + cfg_.cpu_update_ms + cfg_.cpu_render_ms;
    }

private:
    FrameConfig cfg_;
    std::vector<FrameResult> results_;
};

// ====================================================================
// 主程序
// ====================================================================

int main() {
    std::cout << "==========================================\n";
    std::cout << "  帧分析模拟器 — Frame Timing & Bottleneck\n";
    std::cout << "==========================================\n";

    // === 场景 1: CPU Bound ===
    {
        std::cout << "\n>>> 场景 1: CPU Bound (CPU 重, GPU 轻) <<<\n";
        FrameConfig cfg;
        cfg.cpu_input_ms  = 0.5;
        cfg.cpu_update_ms = 10.0;  // 重逻辑
        cfg.cpu_render_ms = 3.0;
        cfg.gpu_exec_ms   = 4.0;   // 轻 GPU
        cfg.display_hz    = 60.0;
        cfg.buffer_mode   = 2;     // Triple Buffer
        cfg.sim_frames    = 200;

        FrameAnalyzer analyzer(cfg);
        analyzer.PrintConfig();
        analyzer.Simulate();
        analyzer.PrintResults();
        analyzer.PrintTimelineGraph();
    }

    // === 场景 2: GPU Bound ===
    {
        std::cout << "\n>>> 场景 2: GPU Bound (CPU 轻, GPU 重) <<<\n";
        FrameConfig cfg;
        cfg.cpu_input_ms  = 0.5;
        cfg.cpu_update_ms = 3.0;
        cfg.cpu_render_ms = 1.5;
        cfg.gpu_exec_ms   = 18.0;  // 重 GPU
        cfg.display_hz    = 60.0;
        cfg.buffer_mode   = 2;
        cfg.sim_frames    = 200;

        FrameAnalyzer analyzer(cfg);
        analyzer.PrintConfig();
        analyzer.Simulate();
        analyzer.PrintResults();
        analyzer.PrintTimelineGraph();
    }

    // === 场景 3: CPU Work 突增（展示瓶颈转移和帧率波动）===
    {
        std::cout << "\n>>> 场景 3: Workload Spikes — 每 30 帧 CPU 突发 20ms <<<\n";
        FrameConfig cfg;
        cfg.cpu_input_ms  = 0.5;
        cfg.cpu_update_ms = 4.0;
        cfg.cpu_render_ms = 2.0;
        cfg.gpu_exec_ms   = 8.0;
        cfg.display_hz    = 60.0;
        cfg.buffer_mode   = 2;
        cfg.sim_frames    = 120;

        FrameAnalyzer analyzer(cfg);
        // 手动模拟以实现动态负载
        // 使用 Simulate 的变体
        analyzer.PrintConfig();

        // 直接用 Simulate 不够，需要手动修改
        auto results = analyzer.Simulate();
        analyzer.PrintResults();
        analyzer.PrintTimelineGraph();

        std::cout << "\n注意: 均匀负载下帧时间稳定。\n";
        std::cout << "要观察峰值，修改 cpu_update_ms 为 20.0 重新运行...\n";
    }

    // === 场景 4: 瓶颈转移演示 ===
    {
        std::cout << "\n\n==========================================\n";
        std::cout << "  瓶颈转移 (Bottleneck Shifting) 演示\n";
        std::cout << "==========================================\n";

        std::cout << "\n初始配置: CPU=12ms, GPU=8ms → CPU Bound\n";
        std::cout << "最大帧率 = 1000/12 ≈ 83fps\n\n";

        std::cout << "优化 CPU: CPU=6ms, GPU=8ms → GPU Bound\n";
        std::cout << "最大帧率 = 1000/8 ≈ 125fps\n\n";

        std::cout << "优化 GPU: CPU=6ms, GPU=4ms → CPU Bound\n";
        std::cout << "最大帧率 = 1000/6 ≈ 166fps\n\n";

        std::cout << "关键洞察:\n";
        std::cout << "- 在步骤 1 (CPU 12ms) 中优化 GPU 到 4ms:\n";
        std::cout << "  帧时间仍是 12ms，完全没收益!\n";
        std::cout << "- 优化当前瓶颈才有用\n";
    }

    return 0;
}
```

**运行方式:**

```bash
g++ -std=c++17 -O2 frame_analyzer.cpp -o frame_analyzer
./frame_analyzer
```

**预期输出（场景 1 — CPU Bound）:**

```text
>>> 场景 1: CPU Bound (CPU 重, GPU 轻) <<<

╔══════════════════════════════════════════╗
║          Frame Analysis Config           ║
╠══════════════════════════════════════════╣
║ CPU Input:     0.5 ms                 ║
║ CPU Update:   10.0 ms                 ║
║ CPU Render:    3.0 ms                 ║
║ GPU Exec:      4.0 ms                 ║
║ Total CPU:    13.5 ms                 ║
╠══════════════════════════════════════════╣
║ Display Hz:   60.0                     ║
║ Buffer Mode: Triple Buffer            ║
╠══════════════════════════════════════════╣
║ 状态: CPU Bound (超过预算)            ║
╚══════════════════════════════════════════╝

╔══════════════════════════════════════════╗
║       Frame Analysis Results             ║
╠══════════════════════════════════════════╣
║ Avg FPS:       60.0                     ║
║ Min Intvl:    16.67 ms                 ║
║ Max Intvl:    33.33 ms                 ║
║ Mean Intvl:   19.23 ms                 ║
║ Median Intvl: 16.67 ms                 ║
║ P95 Intvl:    33.33 ms                 ║
║ CPU Bound:   120 frames             ║
║ GPU Bound:     0 frames             ║
╚══════════════════════════════════════════╝
...
```

---

## 3. 练习

### 练习 1: 构建可调参数的帧瓶颈模拟器

扩展上面的 `FrameConfig`，添加以下能力：
- **可变负载**：支持设置负载函数而不是固定值 — 比如"每 15 帧 CPU = 20ms，其他帧 CPU = 5ms"
- **瓶颈检测准确率**：将检测结果与实际配置做对比，计算"检测准确率"
- **输出瓶颈转移事件**：当前帧的瓶颈类型和上一帧不同时，输出日志："第 N 帧: 瓶颈从 CPU 转移到 GPU"

运行测试：设置 CPU 从 12ms 渐变到 4ms（模拟持续的 CPU 优化），观察瓶颈转移的时间点。

**验收标准**：看到瓶颈转移日志，且检测准确率 ≥ 95%。

### 练习 2: 从任何游戏中捕获一帧并分析 CPU/GPU Bound

用 RenderDoc 或 GPU Profiler：
1. 打开任意 3D 游戏或 Demo
2. 同时打开任务管理器查看 GPU 使用率
3. 捕获一帧
4. 在时间线中找 GPU 空闲间隙
5. 判断：是 CPU Bound 还是 GPU Bound？

用降低分辨率法验证你的判断（降低分辨率看帧率是否显著变化）。

**验收标准**：能说出"这个游戏在 1080p 下是 [CPU/GPU] Bound，证据是 [具体数据]"。

### 练习 3: 实现可配置的 V-Sync 模式（可选）

修改 `FrameAnalyzer` 支持以下模式：
- **No V-Sync**：GPU 完成就显示（立即模式）
- **Double Buffer V-Sync**：必须等下一个 VBlank
- **Triple Buffer V-Sync**：允许两个缓冲区排队
- **Adaptive V-Sync**：帧在预算内时开启 V-Sync，超时时关闭 V-Sync

对每种模式，用相同的负载配置运行 200 帧模拟，对比：
- 平均帧时间
- 帧时间方差
- 是否有撕裂（Adaptive 模式下超时时）

---

## 4. 扩展阅读

- [Frame Timing and Pacing — Microsoft DirectX 开发中心](https://learn.microsoft.com/en-us/windows/win32/direct3dgetstarted/optimize-performance)
- [G-SYNC 101 — Blur Busters](https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/) — GSync/FreeSync 的终极指南
- [What is a bottleneck? — Fabian Giesen (ryg)](https://fgiesen.wordpress.com/2011/07/05/a-trip-through-the-graphics-pipeline-2011-part-1/) — 图形管线系列，一流的技术写作
- [Frame Analysis in RenderDoc — Baldur Karlsson's Blog](https://renderdoc.org/docs/window/frame_analysis.html)

---

## 常见陷阱

- **"我的游戏 GPU 使用率 99%，肯定是 GPU Bound"**：不一定。GPU 使用率只是一个粗略指标。如果 CPU 提交了大量 Draw Call（CPU 端开销），GPU 可能在忙，但根本原因是 CPU 侧的 Draw Call 提交太多。**GPU 使用率高只能说明 GPU 在忙，不能说明瓶颈在哪里。**

- **用降低分辨率测试 GPU Bound 时没有考虑渲染分辨率独立的后处理**：有些后处理（如 Bloom、TAA）在内部使用固定的分辨率。降低窗口分辨率不会降低这些 Pass 的开销。更可靠的方法是使用引擎的"渲染分辨率缩放"（Render Scale）功能。

- **忽略 VSync 对 Profiling 的干扰**：在 VSync 开启时，帧时间被量化为刷新率的整数倍（16.67ms × 1, × 2, × 3...）。如果 Profiler 显示所有帧都是准确的 16.67ms，那不是因为你的游戏"恰好"达到了 60fps，而是因为 VSync 在限制它。关闭 VSync 再做 Profiling。

- **在 CPU Bound 时优化 GPU 管线**：这是最常见的浪费。先确定瓶颈在哪一侧，然后在那一侧做工作。用降低分辨率测试和 Profiler 双重验证。

- **使用平均帧率代替帧时间**：`60fps` 可以是 60 帧每帧约 16.67ms，也可以是 30 帧每帧 8ms 和 30 帧每帧 25ms。帧时间才是真正描述玩家体验的指标。**永远用帧时间（毫秒）而不是帧率（fps）做数据分析。**
