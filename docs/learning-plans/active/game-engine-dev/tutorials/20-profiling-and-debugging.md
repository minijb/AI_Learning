---
title: "性能分析与调试工具"
updated: 2026-06-05
---

# 性能分析与调试工具

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 5h
> 前置知识: 无

---

## 1. 概念讲解

游戏引擎是性能敏感型软件，每一帧都必须在 16.67ms（60 FPS）甚至更短的时间（如 8.33ms 对应 120 FPS）内完成所有工作：物理模拟、AI 计算、渲染提交、音频处理、输入响应等。当帧率下降时，开发者需要精确地知道"时间花在哪里"。性能分析与调试工具就是回答这个问题的利器。

本章涵盖七大核心领域：CPU Profiling、Instrumentation Profiler、GPU Profiling、内存 Profiling、帧率分析、调试可视化和 Assert/崩溃报告系统。

### 为什么需要这个？

想象一下：你的游戏在大部分场景都能稳定 60 FPS，但每当玩家进入某个特定房间，帧率就会暴跌到 30 FPS。没有 Profiling 工具，你可能需要逐行审查代码、猜测瓶颈所在。而有了 Profiling 工具，你可以：

1. **精确定位热点**：知道哪一行代码、哪一个函数占用了最多的 CPU 时间
2. **发现隐藏问题**：内存泄漏、不合理的内存分配、GPU 管线空转
3. **量化优化效果**：优化前后的性能数据对比，避免"感觉变快了"的主观判断
4. **监控长期趋势**：在持续开发中追踪性能退化（Performance Regression）

一句话：**"你无法优化你无法测量的东西"**（You can't optimize what you can't measure）。

### 性能预算（Performance Budget）

以 60FPS 为目标，每帧有 16.67ms 的时间预算，分配给各个子系统：

| 子系统 | 预算 |
|--------|------|
| 渲染 | ~8ms |
| 物理 | ~3ms |
| 游戏逻辑 | ~3ms |
| 动画 | ~2ms |
| 音频 | ~0.5ms |
| IO | 异步，不占用帧时间 |

优化不是无限制的，而是将各子系统的消耗控制在预算之内。

### 核心思想

#### 1.1 CPU Profiling：采样 vs 插桩

CPU Profiling 有两种基本方法论：

**采样分析（Sampling Profiling）**

原理：以固定频率（如每秒 1000 次）中断程序运行，记录当前 CPU 正在执行的函数调用栈。统计每个函数在采样中出现的次数，近似估算其占用的时间比例。

- **优点**：开销极低（通常 <5%），不需要修改代码，适合全程序概览
- **缺点**：时间精度受采样频率限制，可能遗漏执行时间极短但调用频繁的函数，无法精确测量单次调用耗时

类比：就像每隔一分钟拍一张工厂车间的照片，统计每个工位出现的工人数量来估算工作量。

**插桩分析（Instrumentation Profiling）**

原理：在代码中手动插入计时点（Instrumentation），精确记录每个被标记的代码段的进入和退出时间。

- **优点**：时间精度极高（微秒甚至纳秒级），能精确测量单次调用耗时，可捕获完整的调用层次结构
- **缺点**：需要修改代码，插桩点本身有开销（虽然通常很小），如果标记太多会影响性能

类比：就像给每个工人配一个计时器，精确记录每项工作的起止时间。

在游戏引擎中，两种方法通常**配合使用**：采样 Profiler 用于发现"大概哪里慢"，插桩 Profiler 用于"精确测量特定系统的耗时"。

#### Intel VTune 微架构分析

Intel VTune Profiler 是功能最强大的 CPU 性能分析工具之一。其 **Top-Down 微架构分析方法** 将 CPU 执行时间分为四类：

- **Frontend Bound**（前端受限）：CPU 无法足够快地解码和分发指令。原因可能是指令缓存未命中、ITLB 未命中或复杂指令解码瓶颈。
- **Backend Bound**（后端受限）：执行单元或内存子系统成为瓶颈。进一步分为 **Core Bound**（执行单元饱和）和 **Memory Bound**（L1/L2/L3 缓存未命中或内存带宽不足）。
- **Bad Speculation**（错误推测）：分支预测失败导致流水线冲刷。
- **Retiring**（正常退休）：指令正常执行完成的比例——越高越好。

对于游戏引擎，最常见的瓶颈是 **Backend Memory Bound**（数据访问模式不友好，缓存未命中）和 **Bad Speculation**（分支密集、虚函数调用过多）。

| 分析类型 | 数据收集方式 | 适用场景 | 精度与开销 |
|---------|------------|---------|-----------|
| **Hotspots** | 硬件性能计数器（PMU） | 定位消耗 CPU 时间最多的函数 | 高精度，低开销 |
| **Microarchitecture Exploration** | PMU 事件（uops retired, cache miss 等） | 识别微架构层面的瓶颈 | 最详细，中等开销 |
| **Memory Consumption** | 堆分配跟踪 | 定位内存泄漏和频繁分配点 | 较高开销 |
| **Threading** | 线程状态采样 | 分析线程竞争、锁等待时间 | 中等开销 |

#### 1.2 Chrome Tracing 格式

Chrome 浏览器内置了一个强大的性能分析可视化工具 `chrome://tracing`，它接受特定格式的 JSON 文件，可以渲染出交互式的火焰图（Flame Chart）。游戏引擎社区广泛采用这个格式作为跨平台的 Profiling 数据交换标准。

Chrome Tracing JSON 的核心结构：

```json
{
  "displayTimeUnit": "ms",
  "traceEvents": [
    {
      "name": "FunctionName",
      "ph": "B",
      "ts": 1234567890,
      "pid": 1,
      "tid": 1
    },
    {
      "name": "FunctionName",
      "ph": "E",
      "ts": 1234568123,
      "pid": 1,
      "tid": 1
    }
  ]
}
```

关键字段：
- `ph`: 阶段（Phase），`B` = Begin（开始），`E` = End（结束）
- `ts`: 时间戳（微秒）
- `pid`: 进程 ID
- `tid`: 线程 ID
- `name`: 事件名称（显示在火焰图上）

通过配对 `B` 和 `E` 事件，Chrome Tracing 可以渲染出时间轴上的条形图，形成完整的调用层次火焰图。

#### 1.3 GPU Profiling

GPU 与 CPU 是异步工作的。CPU 提交渲染命令到命令缓冲区（Command Buffer），GPU 随后异步执行。测量 GPU 时间不能简单地在 CPU 端计时，需要使用 GPU Timer Queries。

**GPU Timer Query 原理**：
1. CPU 在命令流中插入一个"开始计时"标记（Begin Query）
2. GPU 执行到该标记时，记录当前 GPU 时间戳
3. CPU 稍后插入"结束计时"标记（End Query）
4. 经过若干帧的延迟后，CPU 读取查询结果，获得 GPU 实际执行时间

不同图形 API 的实现：
- **OpenGL**: `GL_TIME_ELAPSED` 查询对象
- **Vulkan**: `vkCmdWriteTimestamp` + `VK_QUERY_TYPE_TIMESTAMP`
- **D3D12**: `ID3D12CommandList::EndQuery` + `D3D12_QUERY_TYPE_TIMESTAMP`

GPU Profiling 工具：
- **RenderDoc**：开源、跨平台（Windows/Linux/Android），支持捕获单帧并逐 Draw Call 分析，可查看纹理、着色器、管线状态
- **NVIDIA Nsight Graphics**：NVIDIA 显卡专用，深度 GPU 分析，支持 CUDA 和光线追踪
- **Intel GPA**：Intel 显卡专用，Frame Analyzer 功能强大
- **AMD Radeon GPU Profiler (RGP)**：AMD 显卡专用，底层硬件计数器分析

#### 1.4 内存 Profiling

游戏引擎中的内存问题主要有两类：

**分配热点（Allocation Hotspots）**：频繁的 `new`/`delete` 或 `malloc`/`free` 调用会导致：
- 分配器锁竞争（多线程场景）
- 内存碎片
- 缓存不友好（每次分配返回的地址不连续）

分析方法是拦截所有内存分配调用，记录分配大小、调用栈、分配频率。

**内存错误**：
- 内存泄漏（分配后未释放）
- 越界访问（Buffer Overflow/Underflow）
- 使用已释放内存（Use-After-Free）
- 未初始化内存读取

工具：
- **Valgrind**（Linux）：`memcheck` 工具可检测内存泄漏和越界访问，但运行极慢（10-50x  slowdown）
- **AddressSanitizer (ASan)**：编译器内置（GCC/Clang/MSVC），运行时开销约 2x，可检测越界、UAF、堆栈溢出
- **MemorySanitizer (MSan)**：检测未初始化内存读取
- **自定义分配器追踪**：在引擎中集成分配统计

#### 1.5 帧率分析与卡顿检测

**帧时间分解**：一帧的时间通常分为几个阶段：

```
帧时间 = 输入处理 + 游戏逻辑更新 + 物理模拟 + 场景剔除 + 渲染提交 + GPU 执行 + 垂直同步等待
```

通过插桩 Profiler，可以将每个阶段的时间可视化，快速发现瓶颈。

**卡顿检测（Spike Detection）**：

卡顿是指帧时间突然大幅超过目标值（如从 16ms 跳到 50ms）。检测方法：
1. 记录每帧的帧时间
2. 维护一个滑动窗口平均值
3. 当单帧时间超过平均值的一定倍数（如 3x）或绝对阈值（如 33ms）时，标记为 Spike
4. 在 Spike 发生时，自动触发详细 Profiling 数据捕获

#### 1.6 调试可视化（Debug Visualization）

调试可视化是将引擎内部状态以图形方式渲染到屏幕上，帮助开发者直观理解运行时行为。

常见类型：
- **碰撞体可视化**：将不可见的碰撞体（AABB、OBB、球体、胶囊体、凸包）以线框方式绘制
- **法线/切线可视化**：在顶点位置绘制法线向量（通常蓝色）和切线向量（通常红色），验证法线贴图和切线空间计算
- **相机视锥可视化**：绘制相机的视锥体（近裁剪面、远裁剪面、四个侧面），用于调试剔除和 LOD
- **导航网格可视化**：绘制 AI 导航网格的节点和连接边
- **光照探针可视化**：绘制光照探针的位置和影响范围

实现方式通常是在主渲染管线的末尾增加一个"Debug Pass"，使用线框模式或简单的几何体绘制。

#### 1.7 Assert 系统与崩溃报告

**Assert（断言）**：在代码中检查"绝不应该发生"的条件，如果违反则立即终止程序并输出诊断信息。

游戏引擎中的 Assert 通常分级：
- `ASSERT`：仅在 Debug 构建中启用，Release 构建中完全消失（零开销）
- `ASSERT_ALWAYS`：在所有构建中都启用，用于检查关键不变量
- `VERIFY`：在 Debug 中检查条件，Release 中仍执行表达式但忽略结果（常用于检查函数返回值）

**崩溃报告系统**：当程序崩溃（段错误、非法指令等）时，自动收集并保存：
- 崩溃类型和信号
- 调用栈（Stack Trace）
- 寄存器状态
- 内存转储（Mini-dump 或 Core dump）
- 最近的日志输出

实现通常依赖平台特定的 API：
- Windows: `SetUnhandledExceptionFilter` + `StackWalk64`
- Linux: `sigaction` + `backtrace` / `libunwind`
- macOS: `NSSetUncaughtExceptionHandler` + `backtrace`

---

## 2. 代码示例

### 2.1 Instrumentation Profiler（Chrome Tracing 格式输出）

以下是一个完整的、可在真实项目中使用的 C++ Instrumentation Profiler。它支持多线程、自动作用域计时、以及 Chrome Tracing JSON 输出。

```cpp
// profiler.hpp
#pragma once

#include <string>
#include <vector>
#include <chrono>
#include <mutex>
#include <fstream>
#include <algorithm>
#include <thread>

// ============================================================
// Instrumentation Profiler
// 输出 Chrome Tracing 格式的 JSON 文件
// 用法：
//   void MyFunction() {
//       PROFILE_SCOPE("MyFunction");
//       // ... 工作代码 ...
//   }
// ============================================================

// 在 Debug 或 Profile 构建中启用，Release 构建中完全消失
#if defined(ENABLE_PROFILING)
    #define PROFILE_SCOPE(name) InstrumentationTimer _timer_##__LINE__(name)
    #define PROFILE_FUNCTION()  PROFILE_SCOPE(__FUNCTION__)
#else
    #define PROFILE_SCOPE(name)
    #define PROFILE_FUNCTION()
#endif

struct ProfileResult {
    std::string name;
    long long start;      // 微秒级时间戳
    long long end;        // 微秒级时间戳
    uint32_t threadID;
};

class Profiler {
public:
    static Profiler& Instance() {
        static Profiler instance;
        return instance;
    }

    void BeginSession(const std::string& name, const std::string& filepath) {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_sessionName = name;
        m_outputStream.open(filepath);
        WriteHeader();
        m_profileCount = 0;
    }

    void EndSession() {
        std::lock_guard<std::mutex> lock(m_mutex);
        WriteFooter();
        m_outputStream.close();
        m_profileCount = 0;
    }

    void WriteProfile(const ProfileResult& result) {
        std::lock_guard<std::mutex> lock(m_mutex);

        if (m_profileCount++ > 0) {
            m_outputStream << ",";
        }

        std::string name = result.name;
        // 转义 JSON 字符串中的特殊字符
        size_t pos = 0;
        while ((pos = name.find('"', pos)) != std::string::npos) {
            name.replace(pos, 1, "\\\"");
            pos += 2;
        }

        m_outputStream << "\n    {"
            << "\"cat\":\"function\","
            << "\"dur\":" << (result.end - result.start) << ","
            << "\"name\":\"" << name << "\","
            << "\"ph\":\"X\","   // X = Complete event (begin+end in one)
            << "\"pid\":0,"
            << "\"tid\":" << result.threadID << ","
            << "\"ts\":" << result.start
            << "}";

        // 每写入 100 条刷新一次，避免崩溃时丢失太多数据
        if (m_profileCount % 100 == 0) {
            m_outputStream.flush();
        }
    }

private:
    Profiler() = default;
    ~Profiler() {
        if (m_outputStream.is_open()) {
            EndSession();
        }
    }

    void WriteHeader() {
        m_outputStream << "{\n  \"displayTimeUnit\": \"ms\",\n  \"traceEvents\": [";
    }

    void WriteFooter() {
        m_outputStream << "\n  ]\n}";
    }

    std::string m_sessionName;
    std::ofstream m_outputStream;
    std::mutex m_mutex;
    int m_profileCount = 0;
};

class InstrumentationTimer {
public:
    explicit InstrumentationTimer(const char* name)
        : m_name(name), m_stopped(false) {
        m_startTimepoint = std::chrono::high_resolution_clock::now();
    }

    ~InstrumentationTimer() {
        if (!m_stopped) {
            Stop();
        }
    }

    void Stop() {
        auto endTimepoint = std::chrono::high_resolution_clock::now();
        auto start = std::chrono::time_point_cast<std::chrono::microseconds>(
            m_startTimepoint).time_since_epoch().count();
        auto end = std::chrono::time_point_cast<std::chrono::microseconds>(
            endTimepoint).time_since_epoch().count();

        uint32_t threadID = static_cast<uint32_t>(
            std::hash<std::thread::id>{}(std::this_thread::get_id()));

        Profiler::Instance().WriteProfile({m_name, start, end, threadID});
        m_stopped = true;
    }

private:
    const char* m_name;
    std::chrono::time_point<std::chrono::high_resolution_clock> m_startTimepoint;
    bool m_stopped;
};
```

```cpp
// profiler_demo.cpp
// 编译: g++ -std=c++17 -DENABLE_PROFILING profiler_demo.cpp -o profiler_demo -lpthread

#include "profiler.hpp"
#include <iostream>
#include <vector>
#include <cmath>
#include <thread>

// 模拟一个耗时的数学计算
void HeavyComputation(int iterations) {
    PROFILE_FUNCTION();
    volatile double result = 0.0;
    for (int i = 0; i < iterations; ++i) {
        result += std::sin(i) * std::cos(i);
    }
    (void)result; // 抑制未使用变量警告
}

// 模拟内存分配密集型操作
void MemoryAllocationTest() {
    PROFILE_FUNCTION();
    std::vector<std::vector<int>> buffers;
    for (int i = 0; i < 100; ++i) {
        PROFILE_SCOPE("AllocateBuffer");
        buffers.emplace_back(10000, i);
    }
}

// 模拟游戏引擎的更新循环
void GameUpdate() {
    PROFILE_FUNCTION();

    {
        PROFILE_SCOPE("InputProcessing");
        // 模拟输入处理
        std::this_thread::sleep_for(std::chrono::microseconds(500));
    }

    {
        PROFILE_SCOPE("PhysicsUpdate");
        HeavyComputation(50000);
    }

    {
        PROFILE_SCOPE("AIUpdate");
        HeavyComputation(30000);
    }

    {
        PROFILE_SCOPE("AnimationUpdate");
        HeavyComputation(20000);
    }
}

// 模拟渲染线程
void RenderThread() {
    PROFILE_FUNCTION();

    for (int frame = 0; frame < 10; ++frame) {
        PROFILE_SCOPE("RenderFrame");

        {
            PROFILE_SCOPE("ShadowPass");
            HeavyComputation(10000);
        }

        {
            PROFILE_SCOPE("GBufferPass");
            HeavyComputation(20000);
        }

        {
            PROFILE_SCOPE("LightingPass");
            HeavyComputation(15000);
        }

        {
            PROFILE_SCOPE("PostProcess");
            HeavyComputation(5000);
        }
    }
}

// 模拟主循环
void MainLoop() {
    PROFILE_FUNCTION();

    for (int frame = 0; frame < 60; ++frame) {
        PROFILE_SCOPE("Frame");
        GameUpdate();

        // 模拟 GPU 等待
        {
            PROFILE_SCOPE("GPUWait");
            std::this_thread::sleep_for(std::chrono::microseconds(200));
        }
    }
}

int main() {
    std::cout << "Starting profiling session..." << std::endl;

    Profiler::Instance().BeginSession("GameEngineProfile", "profile.json");

    // 主线程工作
    MainLoop();

    // 启动渲染线程
    std::thread renderThread([]() {
        RenderThread();
    });

    // 同时做一些内存分配测试
    MemoryAllocationTest();

    renderThread.join();

    Profiler::Instance().EndSession();

    std::cout << "Profiling complete. Open 'profile.json' in chrome://tracing" << std::endl;
    return 0;
}
```

**运行方式:**
```bash
# Linux/macOS
g++ -std=c++17 -DENABLE_PROFILING -O2 profiler_demo.cpp -o profiler_demo -lpthread
./profiler_demo

# Windows (MSVC)
cl /std:c++17 /DENABLE_PROFILING /O2 profiler_demo.cpp
profiler_demo.exe
```

**预期输出:**
```text
Starting profiling session...
Profiling complete. Open 'profile.json' in chrome://tracing
```

生成的 `profile.json` 可以用 Chrome 或 Edge 浏览器打开 `chrome://tracing` 或 `edge://tracing` 加载查看。

---

### 2.2 如何阅读 Chrome Tracing 火焰图

打开 `chrome://tracing` 后，点击"Load"按钮选择生成的 `profile.json` 文件。

**界面元素说明：**

1. **时间轴（横轴）**：从左到右表示时间流逝。可以通过 `W`/`S` 键缩放，`A`/`D` 键平移。

2. **线程列表（纵轴）**：每个线程（tid）显示为一行。可以看到主线程和渲染线程并行工作的情况。

3. **条形图（事件）**：每个彩色条形代表一个被 `PROFILE_SCOPE` 标记的代码段。
   - 条形的长度 = 耗时
   - 条形的颜色 = 随机分配，仅用于区分
   - 条形的嵌套 = 调用层次（如 `Frame` 包含 `GameUpdate`，`GameUpdate` 包含 `PhysicsUpdate`）

4. **火焰图模式**：点击一个事件，下方会显示该事件的详细信息（名称、耗时、起止时间）。

**分析技巧：**

- **找长条**：一眼看去最长的条形就是当前热点
- **看嵌套**：如果一个函数条形的内部大部分被某个子调用占据，说明优化应该聚焦在那个子调用上
- **看空白**：线程行上的空白区域表示该线程处于空闲/等待状态
- **跨线程分析**：对比不同线程的时间轴，可以发现同步问题（如主线程在等待渲染线程）

**示例分析场景：**

假设你看到 `Frame` 条形中 `GPUWait` 占了 8ms，而目标帧时间是 16ms。这说明 GPU 是瓶颈——CPU 已经提前完成了工作，在等待 GPU 完成上一帧的渲染。优化方向应该是减少 GPU 负载（如降低着色器复杂度、减少 Overdraw）。

#### 性能瓶颈定位方法论

系统化的性能瓶颈定位遵循以下流程：

1. **建立性能基准**：确定目标帧率和预算
2. **宏观分析**：使用 VTune Hotspots 或自定义 Profiler 定位 Top 10 耗时函数
3. **微架构分析**：识别 Frontend/Backend/Bad Speculation 瓶颈类型
4. **针对性优化**：
   - Memory Bound -> 优化数据布局（SoA/DOD/缓存行对齐）
   - Core Bound -> 减少指令数（SIMD/算法优化）
   - Bad Speculation -> 消除分支（排序/分支less/虚函数消除）
   - Frontend Bound -> 减少代码体积（内联控制/I-cache 友好）
5. **验证优化效果**：重新 Profile 对比
6. **记录优化方案**：建立性能回归测试

---

### 2.3 简单的 FPS 计数器和帧时间显示

```cpp
// fps_counter.hpp
#pragma once

#include <vector>
#include <chrono>
#include <numeric>
#include <algorithm>
#include <string>

// ============================================================
// FPS 计数器 + 帧时间分析器
// 支持：
//   - 实时 FPS 显示
//   - 平均帧时间 / 最小 / 最大
//   - 卡顿检测（Spike Detection）
// ============================================================

class FPSCounter {
public:
    explicit FPSCounter(size_t historySize = 120)
        : m_historySize(historySize), m_frameCount(0), m_spikeThresholdMultiplier(3.0f) {}

    // 每帧调用一次，传入上一帧的耗时（秒）
    void RecordFrame(double deltaTimeSeconds) {
        double dtMs = deltaTimeSeconds * 1000.0; // 转为毫秒

        m_frameTimes.push_back(dtMs);
        if (m_frameTimes.size() > m_historySize) {
            m_frameTimes.erase(m_frameTimes.begin());
        }

        m_frameCount++;

        // 卡顿检测
        DetectSpike(dtMs);
    }

    // 获取当前 FPS（基于最近一帧）
    double GetCurrentFPS() const {
        if (m_frameTimes.empty()) return 0.0;
        return 1000.0 / m_frameTimes.back();
    }

    // 获取平均帧时间（毫秒）
    double GetAverageFrameTimeMs() const {
        if (m_frameTimes.empty()) return 0.0;
        return std::accumulate(m_frameTimes.begin(), m_frameTimes.end(), 0.0) / m_frameTimes.size();
    }

    // 获取平均 FPS
    double GetAverageFPS() const {
        double avgDt = GetAverageFrameTimeMs();
        return avgDt > 0.0 ? 1000.0 / avgDt : 0.0;
    }

    // 获取最小/最大帧时间
    double GetMinFrameTimeMs() const {
        if (m_frameTimes.empty()) return 0.0;
        return *std::min_element(m_frameTimes.begin(), m_frameTimes.end());
    }

    double GetMaxFrameTimeMs() const {
        if (m_frameTimes.empty()) return 0.0;
        return *std::max_element(m_frameTimes.begin(), m_frameTimes.end());
    }

    // 获取 1% Low FPS（将帧时间排序后取最差的 1% 的平均 FPS）
    // 这是游戏评测中常用的指标，比平均 FPS 更能反映卡顿体验
    double Get1PercentLowFPS() const {
        if (m_frameTimes.size() < 100) return GetAverageFPS();

        std::vector<double> sorted = m_frameTimes;
        std::sort(sorted.begin(), sorted.end(), std::greater<double>());

        size_t count = std::max(size_t(1), sorted.size() / 100);
        double avgWorst = std::accumulate(sorted.begin(), sorted.begin() + count, 0.0) / count;
        return avgWorst > 0.0 ? 1000.0 / avgWorst : 0.0;
    }

    // 获取 0.1% Low FPS（最差的 0.1% 帧的平均 FPS）
    double Get01PercentLowFPS() const {
        if (m_frameTimes.size() < 1000) return Get1PercentLowFPS();

        std::vector<double> sorted = m_frameTimes;
        std::sort(sorted.begin(), sorted.end(), std::greater<double>());

        size_t count = std::max(size_t(1), sorted.size() / 1000);
        double avgWorst = std::accumulate(sorted.begin(), sorted.begin() + count, 0.0) / count;
        return avgWorst > 0.0 ? 1000.0 / avgWorst : 0.0;
    }

    // 获取百分比帧时间（如 P99 = 99% 的帧都低于这个时间）
    double GetPercentileFrameTimeMs(double percentile) const {
        if (m_frameTimes.empty()) return 0.0;

        std::vector<double> sorted = m_frameTimes;
        std::sort(sorted.begin(), sorted.end());

        size_t index = static_cast<size_t>(percentile / 100.0 * sorted.size());
        index = std::min(index, sorted.size() - 1);
        return sorted[index];
    }

    // 获取统计信息字符串（适合显示在屏幕上）
    std::string GetStatsString() const {
        char buffer[256];
        snprintf(buffer, sizeof(buffer),
            "FPS: %.1f | Avg: %.2fms | Min: %.2fms | Max: %.2fms | 1%% Low: %.1f",
            GetCurrentFPS(),
            GetAverageFrameTimeMs(),
            GetMinFrameTimeMs(),
            GetMaxFrameTimeMs(),
            Get1PercentLowFPS()
        );
        return std::string(buffer);
    }

    // 设置卡顿检测阈值倍数（默认 3x 平均帧时间）
    void SetSpikeThresholdMultiplier(float multiplier) {
        m_spikeThresholdMultiplier = multiplier;
    }

    // 获取最近检测到的卡顿信息
    bool HasRecentSpike() const { return m_recentSpike; }
    double GetLastSpikeTimeMs() const { return m_lastSpikeTimeMs; }
    std::string GetLastSpikeInfo() const { return m_lastSpikeInfo; }

    // 重置卡顿标记（通常在读取后调用）
    void ClearSpikeFlag() { m_recentSpike = false; }

private:
    void DetectSpike(double dtMs) {
        m_recentSpike = false;

        if (m_frameTimes.size() < 10) return;

        // 使用滑动窗口平均值（排除当前帧）
        double avg = 0.0;
        size_t count = m_frameTimes.size() - 1;
        for (size_t i = 0; i < count; ++i) {
            avg += m_frameTimes[i];
        }
        avg /= count;

        // 检测条件：当前帧时间超过平均值的阈值倍数，且超过 33ms（约 30 FPS）
        if (dtMs > avg * m_spikeThresholdMultiplier && dtMs > 33.0) {
            m_recentSpike = true;
            m_lastSpikeTimeMs = dtMs;

            char buffer[128];
            snprintf(buffer, sizeof(buffer),
                "SPIKE DETECTED: %.2fms (avg=%.2fms, multiplier=%.1fx)",
                dtMs, avg, m_spikeThresholdMultiplier);
            m_lastSpikeInfo = buffer;
        }
    }

    std::vector<double> m_frameTimes;
    size_t m_historySize;
    uint64_t m_frameCount;

    float m_spikeThresholdMultiplier;
    bool m_recentSpike = false;
    double m_lastSpikeTimeMs = 0.0;
    std::string m_lastSpikeInfo;
};
```

```cpp
// fps_counter_demo.cpp
// 编译: g++ -std=c++17 fps_counter_demo.cpp -o fps_counter_demo

#include "fps_counter.hpp"
#include <iostream>
#include <thread>
#include <cstdlib>

int main() {
    FPSCounter fps(120);
    fps.SetSpikeThresholdMultiplier(2.5f);

    std::cout << "=== FPS Counter Demo ===" << std::endl;
    std::cout << "Simulating 120 frames with occasional spikes..." << std::endl << std::endl;

    for (int frame = 0; frame < 120; ++frame) {
        // 模拟正常帧时间：约 16ms（60 FPS），带一点随机波动
        double baseTime = 16.0 + (rand() % 5 - 2);

        // 每 30 帧模拟一次卡顿（50ms）
        if (frame % 30 == 15) {
            baseTime = 50.0 + (rand() % 20);
        }

        fps.RecordFrame(baseTime / 1000.0);

        if (fps.HasRecentSpike()) {
            std::cout << "[!] " << fps.GetLastSpikeInfo() << std::endl;
            fps.ClearSpikeFlag();
        }

        // 每 10 帧输出一次统计
        if (frame % 10 == 9) {
            std::cout << "Frame " << (frame + 1) << ": " << fps.GetStatsString() << std::endl;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    std::cout << std::endl << "=== Final Statistics ===" << std::endl;
    std::cout << "Average FPS: " << fps.GetAverageFPS() << std::endl;
    std::cout << "1% Low FPS: " << fps.Get1PercentLowFPS() << std::endl;
    std::cout << "0.1% Low FPS: " << fps.Get01PercentLowFPS() << std::endl;
    std::cout << "P50 Frame Time: " << fps.GetPercentileFrameTimeMs(50) << "ms" << std::endl;
    std::cout << "P99 Frame Time: " << fps.GetPercentileFrameTimeMs(99) << "ms" << std::endl;

    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 fps_counter_demo.cpp -o fps_counter_demo
./fps_counter_demo
```

**预期输出:**
```text
=== FPS Counter Demo ===
Simulating 120 frames with occasional spikes...

Frame 10: FPS: 64.9 | Avg: 15.92ms | Min: 14.00ms | Max: 18.00ms | 1% Low: 64.9
Frame 20: FPS: 64.1 | Avg: 15.95ms | Min: 14.00ms | Max: 18.00ms | 1% Low: 64.1
[!] SPIKE DETECTED: 52.00ms (avg=16.33ms, multiplier=2.5x)
Frame 30: FPS: 19.2 | Avg: 17.67ms | Min: 14.00ms | Max: 52.00ms | 1% Low: 19.2
...
=== Final Statistics ===
Average FPS: 58.5
1% Low FPS: 19.2
0.1% Low FPS: 19.2
P50 Frame Time: 16.00ms
P99 Frame Time: 52.00ms
```

---

### 2.4 GPU Timer Query 封装（OpenGL）

```cpp
// gpu_timer.hpp
#pragma once

#include <glad/glad.h>  // 或您使用的 OpenGL 加载器
#include <vector>
#include <string>
#include <unordered_map>
#include <chrono>

// ============================================================
// GPU Timer Query 封装（OpenGL）
// 用法：
//   GPUTimer timer;
//   timer.BeginQuery("ShadowPass");
//   // ... 渲染阴影 ...
//   timer.EndQuery("ShadowPass");
//
//   // 若干帧后读取结果
//   double ms = timer.GetElapsedMs("ShadowPass");
// ============================================================

class GPUTimer {
public:
    struct QueryPair {
        GLuint beginQuery = 0;
        GLuint endQuery = 0;
        bool pending = false;
    };

    GPUTimer() = default;

    ~GPUTimer() {
        // 清理所有查询对象
        for (auto& [name, pair] : m_queries) {
            if (pair.beginQuery) glDeleteQueries(1, &pair.beginQuery);
            if (pair.endQuery) glDeleteQueries(1, &pair.endQuery);
        }
    }

    // 开始一个 GPU 计时查询
    void BeginQuery(const std::string& name) {
        auto& pair = m_queries[name];

        if (pair.beginQuery == 0) {
            glGenQueries(1, &pair.beginQuery);
            glGenQueries(1, &pair.endQuery);
        }

        // 使用 GL_TIME_ELAPSED 查询 GPU 执行时间
        glBeginQuery(GL_TIME_ELAPSED, pair.beginQuery);
        pair.pending = true;
    }

    // 结束 GPU 计时查询
    void EndQuery(const std::string& name) {
        auto it = m_queries.find(name);
        if (it == m_queries.end() || !it->second.pending) {
            return;
        }

        glEndQuery(GL_TIME_ELAPSED);
    }

    // 获取查询结果（毫秒）。如果结果尚未可用，返回上一次的有效结果
    double GetElapsedMs(const std::string& name) {
        auto it = m_queries.find(name);
        if (it == m_queries.end()) return 0.0;

        auto& pair = it->second;
        if (!pair.pending) return m_lastResults[name];

        // 检查查询是否可用（GPU 是异步的，结果可能需要延迟几帧）
        GLint available = 0;
        glGetQueryObjectiv(pair.beginQuery, GL_QUERY_RESULT_AVAILABLE, &available);

        if (available) {
            GLuint64 elapsed = 0;
            glGetQueryObjectui64v(pair.beginQuery, GL_QUERY_RESULT, &elapsed);
            double ms = static_cast<double>(elapsed) / 1'000'000.0; // 纳秒转毫秒
            m_lastResults[name] = ms;
            pair.pending = false;
            return ms;
        }

        return m_lastResults[name];
    }

    // 获取所有计时结果的字符串摘要
    std::string GetSummaryString() const {
        std::string result = "GPU Timings:\n";
        double total = 0.0;

        for (const auto& [name, ms] : m_lastResults) {
            char buf[128];
            snprintf(buf, sizeof(buf), "  %s: %.3f ms\n", name.c_str(), ms);
            result += buf;
            total += ms;
        }

        char totalBuf[64];
        snprintf(totalBuf, sizeof(totalBuf), "  Total: %.3f ms", total);
        result += totalBuf;

        return result;
    }

    // 检查是否有任何查询仍在等待结果
    bool HasPendingQueries() const {
        for (const auto& [name, pair] : m_queries) {
            if (pair.pending) return true;
        }
        return false;
    }

private:
    std::unordered_map<std::string, QueryPair> m_queries;
    std::unordered_map<std::string, double> m_lastResults;
};

// ============================================================
// 跨平台 GPU Timer Query 抽象基类
// 可以派生出 OpenGL / Vulkan / D3D12 的具体实现
// ============================================================

class IGPUTimer {
public:
    virtual ~IGPUTimer() = default;
    virtual void BeginQuery(const std::string& name) = 0;
    virtual void EndQuery(const std::string& name) = 0;
    virtual double GetElapsedMs(const std::string& name) = 0;
};
```

**使用示例：**

```cpp
void RenderFrame() {
    static GPUTimer gpuTimer;

    // 阴影 Pass
    gpuTimer.BeginQuery("ShadowPass");
    RenderShadowMap();
    gpuTimer.EndQuery("ShadowPass");

    // G-Buffer Pass
    gpuTimer.BeginQuery("GBuffer");
    RenderGBuffer();
    gpuTimer.EndQuery("GBuffer");

    // 光照 Pass
    gpuTimer.BeginQuery("Lighting");
    RenderLighting();
    gpuTimer.EndQuery("Lighting");

    // 后处理
    gpuTimer.BeginQuery("PostProcess");
    RenderPostProcess();
    gpuTimer.EndQuery("PostProcess");

    // 读取结果（注意：可能有 1-3 帧的延迟）
    std::cout << gpuTimer.GetSummaryString() << std::endl;
}
```

**关键注意事项：**

1. **异步延迟**：GPU Timer Query 的结果通常需要 1-3 帧后才能读取。这是因为 GPU 执行是异步的，CPU 需要等待 GPU 完成查询范围内的所有命令。

2. **嵌套限制**：OpenGL 的 `GL_TIME_ELAPSED` 查询不支持嵌套（不能在一个 `BeginQuery` 内部再 `BeginQuery` 同一个目标）。如果需要嵌套计时，可以使用 `GL_TIMESTAMP` 查询（记录绝对时间点，然后相减）。

3. **精度**：现代 GPU 支持纳秒级精度的时间戳查询，但实际精度取决于 GPU 的时钟频率。

---

### 2.5 调试可视化示例

```cpp
// debug_visualization.hpp
#pragma once

#include <vector>
#include <glm/glm.hpp>      // 使用 GLM 数学库
#include <glm/gtc/matrix_transform.hpp>

// ============================================================
// 调试可视化渲染器
// 使用简单的线框渲染来可视化引擎内部状态
// 注意：这只是一个接口设计示例，实际实现需要集成到您的渲染管线中
// ============================================================

struct DebugLine {
    glm::vec3 start;
    glm::vec3 end;
    glm::vec3 color;
};

class DebugVisualizer {
public:
    // 添加一条线段到调试绘制列表
    void DrawLine(const glm::vec3& start, const glm::vec3& end, const glm::vec3& color) {
        m_lines.push_back({start, end, color});
    }

    // 绘制 AABB（轴对齐包围盒）
    void DrawAABB(const glm::vec3& min, const glm::vec3& max, const glm::vec3& color) {
        // 底面
        DrawLine(glm::vec3(min.x, min.y, min.z), glm::vec3(max.x, min.y, min.z), color);
        DrawLine(glm::vec3(max.x, min.y, min.z), glm::vec3(max.x, min.y, max.z), color);
        DrawLine(glm::vec3(max.x, min.y, max.z), glm::vec3(min.x, min.y, max.z), color);
        DrawLine(glm::vec3(min.x, min.y, max.z), glm::vec3(min.x, min.y, min.z), color);
        // 顶面
        DrawLine(glm::vec3(min.x, max.y, min.z), glm::vec3(max.x, max.y, min.z), color);
        DrawLine(glm::vec3(max.x, max.y, min.z), glm::vec3(max.x, max.y, max.z), color);
        DrawLine(glm::vec3(max.x, max.y, max.z), glm::vec3(min.x, max.y, max.z), color);
        DrawLine(glm::vec3(min.x, max.y, max.z), glm::vec3(min.x, max.y, min.z), color);
        // 竖边
        DrawLine(glm::vec3(min.x, min.y, min.z), glm::vec3(min.x, max.y, min.z), color);
        DrawLine(glm::vec3(max.x, min.y, min.z), glm::vec3(max.x, max.y, min.z), color);
        DrawLine(glm::vec3(max.x, min.y, max.z), glm::vec3(max.x, max.y, max.z), color);
        DrawLine(glm::vec3(min.x, min.y, max.z), glm::vec3(min.x, max.y, max.z), color);
    }

    // 绘制球体（线框）
    void DrawSphere(const glm::vec3& center, float radius, const glm::vec3& color, int segments = 16) {
        for (int i = 0; i < segments; ++i) {
            float theta1 = 2.0f * 3.14159f * i / segments;
            float theta2 = 2.0f * 3.14159f * (i + 1) / segments;

            // XY 平面圆
            DrawLine(
                center + radius * glm::vec3(cos(theta1), sin(theta1), 0),
                center + radius * glm::vec3(cos(theta2), sin(theta2), 0),
                color
            );
            // XZ 平面圆
            DrawLine(
                center + radius * glm::vec3(cos(theta1), 0, sin(theta1)),
                center + radius * glm::vec3(cos(theta2), 0, sin(theta2)),
                color
            );
            // YZ 平面圆
            DrawLine(
                center + radius * glm::vec3(0, cos(theta1), sin(theta1)),
                center + radius * glm::vec3(0, cos(theta2), sin(theta2)),
                color
            );
        }
    }

    // 绘制法线（用于验证法线方向）
    void DrawNormal(const glm::vec3& position, const glm::vec3& normal, float length, const glm::vec3& color) {
        DrawLine(position, position + normal * length, color);
    }

    // 绘制切线空间（法线=蓝，切线=红，副切线=绿）
    void DrawTangentSpace(const glm::vec3& position,
                          const glm::vec3& normal,
                          const glm::vec3& tangent,
                          const glm::vec3& bitangent,
                          float length) {
        DrawLine(position, position + normal * length, glm::vec3(0, 0, 1));      // 蓝色 = 法线
        DrawLine(position, position + tangent * length, glm::vec3(1, 0, 0));     // 红色 = 切线
        DrawLine(position, position + bitangent * length, glm::vec3(0, 1, 0));   // 绿色 = 副切线
    }

    // 绘制相机视锥体
    void DrawFrustum(const glm::mat4& invViewProj, const glm::vec3& color) {
        // NDC 空间的 8 个角点
        glm::vec4 ndcCorners[8] = {
            {-1, -1, -1, 1}, {1, -1, -1, 1}, {1, 1, -1, 1}, {-1, 1, -1, 1},  // 近裁剪面
            {-1, -1,  1, 1}, {1, -1,  1, 1}, {1, 1,  1, 1}, {-1, 1,  1, 1},  // 远裁剪面
        };

        glm::vec3 worldCorners[8];
        for (int i = 0; i < 8; ++i) {
            glm::vec4 world = invViewProj * ndcCorners[i];
            worldCorners[i] = glm::vec3(world) / world.w;
        }

        // 近裁剪面
        DrawLine(worldCorners[0], worldCorners[1], color);
        DrawLine(worldCorners[1], worldCorners[2], color);
        DrawLine(worldCorners[2], worldCorners[3], color);
        DrawLine(worldCorners[3], worldCorners[0], color);
        // 远裁剪面
        DrawLine(worldCorners[4], worldCorners[5], color);
        DrawLine(worldCorners[5], worldCorners[6], color);
        DrawLine(worldCorners[6], worldCorners[7], color);
        DrawLine(worldCorners[7], worldCorners[4], color);
        // 连接边
        DrawLine(worldCorners[0], worldCorners[4], color);
        DrawLine(worldCorners[1], worldCorners[5], color);
        DrawLine(worldCorners[2], worldCorners[6], color);
        DrawLine(worldCorners[3], worldCorners[7], color);
    }

    // 绘制坐标轴（用于调试定位）
    void DrawAxes(const glm::vec3& origin, float length) {
        DrawLine(origin, origin + glm::vec3(length, 0, 0), glm::vec3(1, 0, 0)); // X = 红
        DrawLine(origin, origin + glm::vec3(0, length, 0), glm::vec3(0, 1, 0)); // Y = 绿
        DrawLine(origin, origin + glm::vec3(0, 0, length), glm::vec3(0, 0, 1)); // Z = 蓝
    }

    // 获取所有线段数据（提交给渲染器）
    const std::vector<DebugLine>& GetLines() const { return m_lines; }

    // 清空本帧的调试绘制数据（每帧开始时调用）
    void Clear() { m_lines.clear(); }

private:
    std::vector<DebugLine> m_lines;
};
```

---

### 2.6 Assert 系统与崩溃报告

```cpp
// assert_system.hpp
#pragma once

#include <iostream>
#include <sstream>
#include <string>
#include <csignal>
#include <cstdlib>

// ============================================================
// 跨平台 Assert 系统和崩溃报告
// ============================================================

// 平台特定的调用栈获取
#if defined(_WIN32)
    #include <windows.h>
    #include <dbghelp.h>
    #pragma comment(lib, "dbghelp.lib")
#elif defined(__linux__) || defined(__APPLE__)
    #include <execinfo.h>
    #include <unistd.h>
#endif

// 构建配置检测
#if defined(NDEBUG) || defined(RELEASE)
    #define IS_RELEASE_BUILD 1
#else
    #define IS_RELEASE_BUILD 0
#endif

// 断言宏
#if IS_RELEASE_BUILD
    // Release 构建：ASSERT 完全消失
    #define ASSERT(condition) ((void)0)
    #define ASSERT_MSG(condition, msg) ((void)0)
#else
    // Debug 构建：ASSERT 启用
    #define ASSERT(condition) \
        do { \
            if (!(condition)) { \
                AssertHandler(#condition, __FILE__, __LINE__, __FUNCTION__, ""); \
            } \
        } while(0)

    #define ASSERT_MSG(condition, msg) \
        do { \
            if (!(condition)) { \
                AssertHandler(#condition, __FILE__, __LINE__, __FUNCTION__, msg); \
            } \
        } while(0)
#endif

// 所有构建都启用的关键断言
#define ASSERT_ALWAYS(condition) \
    do { \
        if (!(condition)) { \
            AssertHandler(#condition, __FILE__, __LINE__, __FUNCTION__, "CRITICAL ASSERT"); \
        } \
    } while(0)

// VERIFY：Release 中执行表达式但忽略结果
#if IS_RELEASE_BUILD
    #define VERIFY(expression) ((void)(expression))
#else
    #define VERIFY(expression) ASSERT(expression)
#endif

// 断言处理函数
inline void AssertHandler(const char* condition, const char* file, int line,
                          const char* function, const char* message) {
    std::cerr << "\n========== ASSERTION FAILED ==========" << std::endl;
    std::cerr << "Condition: " << condition << std::endl;
    std::cerr << "File:      " << file << ":" << line << std::endl;
    std::cerr << "Function:  " << function << std::endl;
    if (message && message[0]) {
        std::cerr << "Message:   " << message << std::endl;
    }
    std::cerr << "=======================================" << std::endl;

    // 输出调用栈
    PrintStackTrace();

    // 触发调试器断点或终止
    #if defined(_WIN32)
        __debugbreak();  // 触发断点，如果调试器附加会停下来
    #else
        raise(SIGTRAP);  // Unix: 发送 SIGTRAP
    #endif

    std::abort();
}

// 调用栈打印
inline void PrintStackTrace(int maxFrames = 64) {
    std::cerr << "\nCall Stack:" << std::endl;

    #if defined(_WIN32)
        HANDLE process = GetCurrentProcess();
        SymInitialize(process, NULL, TRUE);

        void* stack[maxFrames];
        WORD frames = CaptureStackBackTrace(0, maxFrames, stack, NULL);

        SYMBOL_INFO* symbol = (SYMBOL_INFO*)calloc(sizeof(SYMBOL_INFO) + 256 * sizeof(char), 1);
        symbol->MaxNameLen = 255;
        symbol->SizeOfStruct = sizeof(SYMBOL_INFO);

        for (WORD i = 0; i < frames; ++i) {
            SymFromAddr(process, (DWORD64)(stack[i]), 0, symbol);
            std::cerr << "  [" << i << "] " << symbol->Name << std::endl;
        }

        free(symbol);
        SymCleanup(process);

    #elif defined(__linux__) || defined(__APPLE__)
        void* buffer[maxFrames];
        int nptrs = backtrace(buffer, maxFrames);
        char** strings = backtrace_symbols(buffer, nptrs);

        for (int i = 0; i < nptrs; ++i) {
            std::cerr << "  [" << i << "] " << strings[i] << std::endl;
        }

        free(strings);
    #else
        std::cerr << "  (Stack trace not supported on this platform)" << std::endl;
    #endif
}

// ============================================================
// 崩溃报告系统
// ============================================================

class CrashReporter {
public:
    static void Install() {
        #if defined(_WIN32)
            SetUnhandledExceptionFilter(WindowsExceptionHandler);
        #else
            struct sigaction sa;
            sa.sa_sigaction = UnixSignalHandler;
            sa.sa_flags = SA_SIGINFO;
            sigemptyset(&sa.sa_mask);

            sigaction(SIGSEGV, &sa, nullptr);  // 段错误
            sigaction(SIGFPE, &sa, nullptr);   // 浮点异常
            sigaction(SIGILL, &sa, nullptr);   // 非法指令
            sigaction(SIGABRT, &sa, nullptr);  // abort()
        #endif
    }

private:
    #if defined(_WIN32)
    static LONG WINAPI WindowsExceptionHandler(EXCEPTION_POINTERS* exceptionInfo) {
        std::cerr << "\n========== CRASH REPORT ==========" << std::endl;
        std::cerr << "Exception Code: " << std::hex << exceptionInfo->ExceptionRecord->ExceptionCode << std::dec << std::endl;
        std::cerr << "Address: " << exceptionInfo->ExceptionRecord->ExceptionAddress << std::endl;

        PrintStackTrace();

        std::cerr << "\nGenerating minidump..." << std::endl;
        GenerateMinidump(exceptionInfo);

        return EXCEPTION_EXECUTE_HANDLER;
    }

    static void GenerateMinidump(EXCEPTION_POINTERS* exceptionInfo) {
        HANDLE hFile = CreateFileA("crash.dmp", GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (hFile != INVALID_HANDLE_VALUE) {
            MINIDUMP_EXCEPTION_INFORMATION mdei;
            mdei.ThreadId = GetCurrentThreadId();
            mdei.ExceptionPointers = exceptionInfo;
            mdei.ClientPointers = FALSE;

            MiniDumpWriteDump(GetCurrentProcess(), GetCurrentProcessId(), hFile,
                MiniDumpNormal, &mdei, NULL, NULL);
            CloseHandle(hFile);
            std::cerr << "Minidump saved to crash.dmp" << std::endl;
        }
    }
    #else
    static void UnixSignalHandler(int sig, siginfo_t* info, void* context) {
        const char* sigName = "Unknown";
        switch (sig) {
            case SIGSEGV: sigName = "SIGSEGV (Segmentation Fault)"; break;
            case SIGFPE:  sigName = "SIGFPE (Floating Point Exception)"; break;
            case SIGILL:  sigName = "SIGILL (Illegal Instruction)"; break;
            case SIGABRT: sigName = "SIGABRT (Abort)"; break;
        }

        std::cerr << "\n========== CRASH REPORT ==========" << std::endl;
        std::cerr << "Signal: " << sigName << std::endl;
        std::cerr << "Address: " << info->si_addr << std::endl;

        PrintStackTrace();

        // 恢复默认处理程序并重新触发信号，让系统生成 core dump
        signal(sig, SIG_DFL);
        raise(sig);
    }
    #endif
};
```

**使用示例：**

```cpp
#include "assert_system.hpp"

int main() {
    // 安装崩溃报告处理器
    CrashReporter::Install();

    // 基本断言
    int* ptr = new int(42);
    ASSERT(ptr != nullptr);           // Debug 构建中检查
    ASSERT_MSG(ptr != nullptr, "Memory allocation failed");

    // 关键断言（所有构建都启用）
    ASSERT_ALWAYS(ptr != nullptr);

    // VERIFY（Release 中也会执行表达式）
    FILE* file = fopen("data.txt", "r");
    VERIFY(file != nullptr);          // Debug 中断言，Release 中忽略但 file 仍被赋值

    // 触发一个崩溃测试
    // int* badPtr = nullptr;
    // *badPtr = 123;  // 这将触发崩溃报告

    delete ptr;
    return 0;
}
```

---

## 3. 练习

### 练习 1: 扩展 Instrumentation Profiler

为 `InstrumentationTimer` 添加以下功能：

1. **分类着色**：在 Chrome Tracing JSON 输出中增加 `cname` 字段，为不同类别的函数分配不同颜色。例如：渲染相关函数用蓝色，物理用红色，AI 用绿色。修改 `PROFILE_SCOPE` 宏为 `PROFILE_SCOPE_CATEGORY(name, category)`。

2. **即时模式统计**：在 `Profiler` 类中增加一个方法 `PrintStats()`，在程序结束时输出每个被分析函数的总耗时、调用次数、平均耗时排序列表。

3. **线程名标注**：在 JSON 输出中增加 `metadata` 事件，为每个线程设置可读名称（如"MainThread"、"RenderThread"、"JobWorker-0"），而不是显示数字 tid。

**提示**：Chrome Tracing 的线程名通过 `ph: "M"`（Metadata）事件设置：
```json
{"name":"thread_name","ph":"M","pid":0,"tid":1,"args":{"name":"MainThread"}}
```

### 练习 2: 集成 GPU 和 CPU 时间到统一分析器

创建一个 `FrameProfiler` 类，将 CPU 插桩时间和 GPU 查询时间整合到同一个 Chrome Tracing JSON 输出中。要求：

1. 每帧自动记录 `Frame` 事件，内部包含 `CPU_Update`、`CPU_RenderSubmit`、`GPU_Render` 等子事件
2. GPU 事件在火焰图中显示在独立的"GPU"线程行上
3. 处理 GPU 查询的异步延迟，确保 GPU 事件条形的开始时间与实际提交时间对齐
4. 添加一个 `FrameBudget` 概念：目标帧时间（如 16.67ms），如果某帧超过预算，自动将该帧标记为红色高亮

**提示**：由于 GPU 查询有延迟，你可能需要一个环形缓冲区来存储最近 N 帧的 GPU 时间，在结果可用时再写入 JSON。

### 练习 3: 内存分配追踪器（可选，挑战）

实现一个自定义的内存分配追踪器，拦截全局的 `new`/`delete` 和 `malloc`/`free` 调用：

1. 重载全局 `operator new` / `operator delete`（注意大小对齐版本）
2. 记录每次分配的大小、调用栈（使用 `backtrace` 或 `CaptureStackBackTrace`）、分配时间
3. 实现一个 `MemoryProfiler` 类，可以输出：
   - 当前总分配内存量
   - 分配次数最频繁的大小（如"1024 字节的分配发生了 5000 次"）
   - 分配热点调用栈 Top 10
   - 检测内存泄漏（程序退出时未释放的分配）
4. 将内存分配事件也输出为 Chrome Tracing 格式（使用 `ph: "i"` 即时事件），在独立线程上显示，可以看到内存分配的时间分布

**注意**：这个练习涉及全局运算符重载，建议在独立的测试项目中进行，避免影响其他代码。

---
## 3.5 参考答案

> [!tip]- 练习 1: 扩展 Instrumentation Profiler
>
> #### 1.1 分类着色 — `PROFILE_SCOPE_CATEGORY` + `cname` 字段
>
> ```cpp
> // 新增：类别枚举与颜色映射
> enum class ProfileCategory : uint8_t {
>     Default,    // 默认灰
>     Rendering,  // 蓝色
>     Physics,    // 红色
>     AI,         // 绿色
>     Audio,      // 黄色
>     IO,         // 青色
>     Count
> };
>
> // Chrome Tracing "cname" 对每种 category 使用固定的 CSS 颜色名
> constexpr const char* kCategoryColors[] = {
>     "grey",                // Default
>     "blue",                // Rendering
>     "red",                 // Physics
>     "green",               // AI
>     "olive",               // Audio
>     "cyan",                // IO
> };
>
> static_assert(std::size(kCategoryColors) == static_cast<size_t>(ProfileCategory::Count));
> ```
>
> ```cpp
> // ProfileResult 新增 category 字段
> struct ProfileResult {
>     std::string name;
>     long long start;
>     long long end;
>     uint32_t threadID;
>     ProfileCategory category = ProfileCategory::Default;
> };
> ```
>
> ```cpp
> // Profiler::WriteProfile() 增加 cname 输出
> void WriteProfile(const ProfileResult& result) {
>     std::lock_guard<std::mutex> lock(m_mutex);
>     if (m_profileCount++ > 0) m_outputStream << ",";
>
>     // 转义
>     std::string escapedName = result.name;
>     for (size_t i = 0; i < escapedName.size(); ++i) {
>         if (escapedName[i] == '"') { escapedName.insert(i, "\\"); ++i; }
>     }
>
>     m_outputStream << "\n    {"
>         << "\"cat\":\"" << kCategoryColors[static_cast<int>(result.category)] << "\","
>         << "\"dur\":" << (result.end - result.start) << ","
>         << "\"name\":\"" << escapedName << "\","
>         << "\"ph\":\"X\","
>         << "\"pid\":0,"
>         << "\"tid\":" << result.threadID << ","
>         << "\"ts\":" << result.start;
>
>     // 如果注册了渲染类别，写入 cname（Chrome Trace Event 规范字段）
>     if (result.category != ProfileCategory::Default) {
>         m_outputStream << ",\"cname\":\"" << kCategoryColors[static_cast<int>(result.category)] << "\"";
>     }
>     m_outputStream << "}";
>
>     // 同时记录统计
>     m_stats[result.name].totalUs += (result.end - result.start);
>     m_stats[result.name].callCount++;
>
>     if (m_profileCount % 100 == 0) m_outputStream.flush();
> }
> ```
>
> ```cpp
> // 重载宏：保留原 PROFILE_SCOPE 向后兼容，新增分类版
> #if defined(ENABLE_PROFILING)
>     #define PROFILE_SCOPE(name) \
>         InstrumentationTimer _timer_##__LINE__(name, ProfileCategory::Default)
>     #define PROFILE_SCOPE_CATEGORY(name, cat) \
>         InstrumentationTimer _timer_##__LINE__(name, cat)
>     #define PROFILE_FUNCTION()     PROFILE_SCOPE(__FUNCTION__)
>     #define PROFILE_FUNCTION_CAT(cat) PROFILE_SCOPE_CATEGORY(__FUNCTION__, cat)
> #else
>     #define PROFILE_SCOPE(name)
>     #define PROFILE_SCOPE_CATEGORY(name, cat)
>     #define PROFILE_FUNCTION()
>     #define PROFILE_FUNCTION_CAT(cat)
> #endif
> ```
>
> ```cpp
> // InstrumentationTimer 增加 category 参数
> class InstrumentationTimer {
> public:
>     explicit InstrumentationTimer(const char* name,
>                                   ProfileCategory cat = ProfileCategory::Default)
>         : m_name(name), m_category(cat), m_stopped(false)
>     {
>         m_startTimepoint = std::chrono::high_resolution_clock::now();
>     }
>
>     ~InstrumentationTimer() { if (!m_stopped) Stop(); }
>
>     void Stop() {
>         auto endTimepoint = std::chrono::high_resolution_clock::now();
>         auto start = std::chrono::time_point_cast<std::chrono::microseconds>(
>             m_startTimepoint).time_since_epoch().count();
>         auto end = std::chrono::time_point_cast<std::chrono::microseconds>(
>             endTimepoint).time_since_epoch().count();
>
>         uint32_t threadID = static_cast<uint32_t>(
>             std::hash<std::thread::id>{}(std::this_thread::get_id()));
>
>         ProfileResult r{m_name, start, end, threadID, m_category};
>         Profiler::Instance().WriteProfile(r);
>         m_stopped = true;
>     }
>
> private:
>     const char* m_name;
>     ProfileCategory m_category;
>     std::chrono::time_point<std::chrono::high_resolution_clock> m_startTimepoint;
>     bool m_stopped;
> };
> ```
>
> ```cpp
> // 使用示例
> void RenderScene() {
>     PROFILE_SCOPE_CATEGORY("RenderScene", ProfileCategory::Rendering);
>     // ...
> }
> ```
>
> #### 1.2 即时模式统计 — `PrintStats()`
>
> ```cpp
> // 在 Profiler 类中添加统计结构和 PrintStats 方法
> struct ProfileStat {
>     long long totalUs = 0;
>     int callCount = 0;
> };
>
> // Profiler 私有成员
> std::unordered_map<std::string, ProfileStat> m_stats;
>
> // PrintStats 实现 — 在 EndSession 前调用，输出排序后的统计表
> void PrintStats(std::ostream& out = std::cout) {
>     std::lock_guard<std::mutex> lock(m_mutex);
>
>     // 按 totalUs 降序排列
>     std::vector<std::pair<std::string, ProfileStat>> sorted;
>     for (const auto& [name, stat] : m_stats) {
>         sorted.emplace_back(name, stat);
>     }
>     std::sort(sorted.begin(), sorted.end(),
>         [](const auto& a, const auto& b) { return a.second.totalUs > b.second.totalUs; });
>
>     out << "\n========= Profile Statistics (sorted by total time) =========\n";
>     out << std::left
>         << std::setw(40) << "Name"
>         << std::setw(12) << "Calls"
>         << std::setw(14) << "Total(ms)"
>         << std::setw(14) << "Avg(ms)"
>         << std::setw(12) << "%" << "\n";
>     out << std::string(92, '-') << "\n";
>
>     long long grandTotalUs = 0;
>     for (const auto& [_, stat] : m_stats) grandTotalUs += stat.totalUs;
>
>     for (const auto& [name, stat] : sorted) {
>         double totalMs = stat.totalUs / 1000.0;
>         double avgMs = totalMs / static_cast<double>(stat.callCount);
>         double pct = grandTotalUs > 0
>             ? (100.0 * stat.totalUs / static_cast<double>(grandTotalUs)) : 0.0;
>
>         out << std::left
>             << std::setw(40) << name
>             << std::setw(12) << stat.callCount
>             << std::setw(14) << std::fixed << std::setprecision(3) << totalMs
>             << std::setw(14) << std::fixed << std::setprecision(3) << avgMs
>             << std::setw(11) << std::fixed << std::setprecision(1) << pct << "%\n";
>     }
>     out << std::string(92, '-') << "\n";
>     out << "Grand Total: " << (grandTotalUs / 1000.0) << " ms\n";
> }
> ```
>
> #### 1.3 线程名标注 — `metadata` 事件
>
> ```cpp
> // 在 Profiler 类中新增：注册线程名 + 写入 meta 事件
> class Profiler {
> public:
>     // 线程启动时调用一次，会在 JSON 头部插入 metadata 事件
>     static void SetThreadName(const std::string& name) {
>         std::lock_guard<std::mutex> lock(Instance().m_mutex);
>         Instance().m_threadNames[std::this_thread::get_id()] = name;
>
>         // 如果 profiling session 已开启，立刻写入 metadata
>         if (Instance().m_outputStream.is_open()) {
>             WriteThreadNameMeta(Instance().m_outputStream, name);
>         }
>     }
>
> private:
>     // WriteHeader 被修改为同时写入已注册的线程名
>     void WriteHeader() {
>         m_outputStream << "{\n  \"displayTimeUnit\": \"ms\",\n  \"traceEvents\": [";
>         // 为主线程写入默认名
>         WriteThreadNameMeta(m_outputStream, "MainThread");
>
>         // 写入所有已注册的非主线程名
>         auto mainId = std::this_thread::get_id();
>         for (const auto& [id, name] : m_threadNames) {
>             if (id != mainId) {
>                 m_outputStream << ",";
>                 WriteThreadNameMeta(m_outputStream, name);
>             }
>         }
>     }
>
>     static void WriteThreadNameMeta(std::ofstream& out, const std::string& name) {
>         uint32_t tid = static_cast<uint32_t>(
>             std::hash<std::thread::id>{}(std::this_thread::get_id()));
>         out << "\n    {"
>             << "\"name\":\"thread_name\","
>             << "\"ph\":\"M\","      // M = Meta event
>             << "\"pid\":0,"
>             << "\"tid\":" << tid << ","
>             << "\"args\":{\"name\":\"" << name << "\"}"
>             << "}";
>     }
>
>     std::unordered_map<std::thread::id, std::string> m_threadNames;
>     // ... 其他成员不变
> };
> ```
>
> ```cpp
> // 使用示例
> void RenderThreadMain() {
>     Profiler::SetThreadName("RenderThread");
>     while (running) { /* ... */ }
> }
> ```

> [!tip]- 练习 2: 集成 GPU 和 CPU 时间到统一分析器（FrameProfiler）
>
> #### 2.1 环形缓冲区处理 GPU 异步延迟
>
> ```cpp
> // frame_profiler.hpp
> #pragma once
>
> #include "profiler.hpp"  // 复用前面章节的 CPU Profiler
> #include <array>
> #include <string>
>
> // ============================================================
> // GPU 查询结果（简化版 — 不依赖具体图形 API）
> // ============================================================
> struct GPUQuerySlot {
>     std::string name;
>     int frameIndex = -1;          // 所属帧序号
>     double cpuSubmitTimeMs = 0.0; // CPU 提交命令时的帧时间（用于火焰图横轴对齐）
>     double gpuDurationMs = 0.0;   // GPU 执行耗时（从 query 读回）
>     bool ready = false;
>     ProfileCategory category = ProfileCategory::Rendering;
> };
>
> // ============================================================
> // FrameProfiler — 统一 CPU + GPU 的帧级分析器
> // ============================================================
> class FrameProfiler {
> public:
>     static constexpr size_t kRingBufferSize = 4;  // GPU query 最多延迟 3 帧
>     static constexpr double kDefaultBudgetMs = 16.67; // 60FPS
>
>     FrameProfiler()
>         : m_frameIndex(0), m_currentWriter(0), m_frameBudgetUs(
>             static_cast<long long>(kDefaultBudgetMs * 1000.0))
>     {}
>
>     // ---- 每帧入口 ----
>     void BeginFrame() {
>         m_frameStartUs = NowUs();
>         // 用 CPU Profiler 记录 Frame 事件起点
>         Profiler::Instance().WriteProfile(
>             {"Frame", m_frameStartUs, m_frameStartUs,
>              CurrentThreadID(), ProfileCategory::Default});
>     }
>
>     void EndFrame() {
>         long long now = NowUs();
>         // 写出 Frame Complete 事件（ph:"X"），Chrome Tracing 自动渲染为条形
>         m_frameWriter[0] = now; // 临时用；实际由 WriteProfile 处理
>
>         // 计算帧耗时并检测超预算
>         long long frameUs = now - m_frameStartUs;
>
>         // 写入 Flame 提示事件（超预算时红色高亮）
>         auto cat = (frameUs > m_frameBudgetUs)
>             ? ProfileCategory::Default : ProfileCategory::Default;
>         // 超预算帧用不同的 name 后缀，方便在火焰图中一眼看到
>         std::string frameName = "Frame";
>         if (frameUs > m_frameBudgetUs) {
>             frameName += " [OVER BUDGET " + std::to_string(frameUs / 1000) + "ms]";
>         }
>
>         Profiler::Instance().WriteProfile(
>             {frameName, m_frameStartUs, now,
>              CurrentThreadID(), ProfileCategory::Rendering});
>
>         // 轮转环形缓冲区 — 从 N 帧前的 slot 读取 GPU 结果
>         CollectGPUResults();
>
>         // 将本帧的 GPU 提交记录推进环形缓冲区
>         AdvanceRingBuffer();
>         m_frameIndex++;
>     }
>
>     // ---- CPU 计时：帧内子事件（仍然用 Profiler 自动记录） ----
>     // 宏方式：FRAME_PROFILE_SCOPE_CAT(name, cat)
>     // 此处提供 manual API 版本
>     void RecordCPUEvent(const std::string& name, long long startUs, long long endUs,
>                         ProfileCategory cat = ProfileCategory::Default) {
>         Profiler::Instance().WriteProfile(
>             {name, startUs, endUs, CurrentThreadID(), cat});
>     }
>
>     // ---- GPU 计时：提交查询 ----
>     // 在 CPU 提交渲染命令时调用，记录提交时间以供后续对齐
>     void SubmitGPUQuery(const std::string& name, ProfileCategory cat) {
>         auto& slot = m_ringBuffer[m_currentWriter];
>         slot.name = name;
>         slot.frameIndex = m_frameIndex;
>         slot.cpuSubmitTimeMs = static_cast<double>(
>             std::chrono::duration_cast<std::chrono::microseconds>(
>                 std::chrono::high_resolution_clock::now().time_since_epoch()
>             ).count()) / 1000.0;
>         slot.category = cat;
>         slot.ready = false; // 等待 GPU 完成
>         m_currentWriter = (m_currentWriter + 1) % kRingBufferSize;
>     }
>
>     // 当 GPU 查询结果可用时，由外部调用填入耗时
>     void CompleteGPUQuery(const std::string& name, double gpuDurationMs,
>                           int frameIndex) {
>         for (auto& slot : m_ringBuffer) {
>             if (slot.name == name && slot.frameIndex == frameIndex && !slot.ready) {
>                 slot.gpuDurationMs = gpuDurationMs;
>                 slot.ready = true;
>                 break;
>             }
>         }
>     }
>
>     // 设置帧预算（微秒）
>     void SetFrameBudgetUs(long long us) { m_frameBudgetUs = us; }
>
> private:
>     // 收集已就绪的 GPU 结果并写入 JSON
>     void CollectGPUResults() {
>         for (auto& slot : m_ringBuffer) {
>             if (slot.ready && slot.frameIndex >= 0) {
>                 // GPU 事件写入独立的 Thread（用一个固定的大 tid 值标识）
>                 constexpr uint32_t kGPUThreadID = 9999;
>
>                 long long gpuStartUs = static_cast<long long>(
>                     slot.cpuSubmitTimeMs * 1000.0);
>                 long long gpuEndUs = gpuStartUs +
>                     static_cast<long long>(slot.gpuDurationMs * 1000.0);
>
>                 Profiler::Instance().WriteProfile(
>                     {slot.name, gpuStartUs, gpuEndUs,
>                      kGPUThreadID, slot.category});
>
>                 slot.ready = false; // 消费完毕
>                 slot.frameIndex = -1;
>             }
>         }
>     }
>
>     void AdvanceRingBuffer() {
>         // 环形缓冲区只需轮流覆盖；CollectGPUResults 已消费就绪 slot
>     }
>
>     static long long NowUs() {
>         return std::chrono::duration_cast<std::chrono::microseconds>(
>             std::chrono::high_resolution_clock::now().time_since_epoch()
>         ).count();
>     }
>
>     static uint32_t CurrentThreadID() {
>         return static_cast<uint32_t>(
>             std::hash<std::thread::id>{}(std::this_thread::get_id()));
>     }
>
>     long long m_frameStartUs = 0;
>     long long m_frameBudgetUs = static_cast<long long>(kDefaultBudgetMs * 1000.0);
>     long long m_frameWriter[1]{}; // 辅助用
>     int m_frameIndex = 0;
>     size_t m_currentWriter = 0;
>     std::array<GPUQuerySlot, kRingBufferSize> m_ringBuffer;
> };
> ```
>
> #### 2.2 使用示例
>
> ```cpp
> FrameProfiler g_frameProfiler;
>
> void MainLoop() {
>     Profiler::Instance().BeginSession("GameProfile", "frame_trace.json");
>
>     while (isRunning) {
>         g_frameProfiler.BeginFrame();
>
>         // === CPU 阶段 ===
>         {
>             PROFILE_SCOPE_CATEGORY("CPU_Update", ProfileCategory::Default);
>             UpdateGameLogic();
>         }
>         {
>             PROFILE_SCOPE_CATEGORY("CPU_RenderSubmit", ProfileCategory::Rendering);
>             CullScene();
>             BuildCommandBuffers();
>         }
>
>         // === GPU 提交（在 RenderThread 上） ===
>         g_frameProfiler.SubmitGPUQuery("GPU_ShadowPass", ProfileCategory::Rendering);
>         RenderShadowMap();
>         // 实际引擎中，GPU query 结果由 RenderThread 回填
>         g_frameProfiler.CompleteGPUQuery("GPU_ShadowPass",
>             gpuTimer.GetElapsedMs("ShadowPass"), currentFrame);
>
>         g_frameProfiler.EndFrame();
>
>         // 如果超过预算，用红色标注 — 已在 EndFrame 内处理
>     }
>
>     Profiler::Instance().EndSession();
> }
> ```
>
> #### 2.3 FrameBudget 红色高亮实现机制
>
> Chrome Tracing 本身不直接支持按阈值着色，这里使用三种互补策略：
>
> 1. **事件名称后缀**：超预算帧在 name 中追加 `[OVER BUDGET]`，火焰图中一目了然
> 2. **cname 覆盖**：可在 `EndFrame` 中将超预算帧的 category 指定为特定颜色（如 `"red"` 对应红色）
> 3. **额外的 Instant 事件**：超预算时写一条 `ph:"i"` 事件，在时间轴上显示为红色标记点
>
> ```cpp
> // 在 EndFrame 中超预算检测后追加
> if (frameUs > m_frameBudgetUs) {
>     // Instant 标记事件 — 在时间轴上显示为红色感叹号
>     Profiler::Instance().WriteProfile(
>         {"FrameBudgetExceeded", now, now,
>          CurrentThreadID(), ProfileCategory::Default});
>     // 同时输出一条专用的 complete 事件作为红色条
>     Profiler::Instance().WriteProfile(
>         {"BudgetOverhead", m_frameStartUs + m_frameBudgetUs, now,
>          CurrentThreadID(), ProfileCategory::Physics}); // 复用红色
> }
> ```

> [!tip]- 练习 3（可选）: 内存分配追踪器
>
> #### 3.1 全局 operator new/delete 重载 + malloc/free 拦截
>
> ```cpp
> // memory_profiler.hpp
> #pragma once
>
> #include <cstddef>
> #include <cstdint>
> #include <cstdio>
> #include <chrono>
> #include <unordered_map>
> #include <vector>
> #include <mutex>
> #include <atomic>
> #include <algorithm>
> #include <fstream>
>
> // ============================================================
> // MemoryProfiler — 全局内存分配追踪
> // ============================================================
>
> // 平台相关的栈回溯深度
> #ifdef _WIN32
>     #include <windows.h>
>     #define MEMPROF_STACK_DEPTH 16
>     #define MEMPROF_CAPTURE_STACK(frames, depth) \
>         (depth) = CaptureStackBackTrace(0, MEMPROF_STACK_DEPTH, (frames), nullptr)
>     using StackFrame = void*;
> #else
>     #include <execinfo.h>
>     #define MEMPROF_STACK_DEPTH 16
>     #define MEMPROF_CAPTURE_STACK(frames, depth) \
>         (depth) = backtrace((frames), MEMPROF_STACK_DEPTH)
>     using StackFrame = void*;
> #endif
>
> struct AllocationRecord {
>     void* ptr;
>     size_t size;
>     long long timestampUs;          // 分配时间（微秒）
>     StackFrame callstack[MEMPROF_STACK_DEPTH];
>     int stackDepth;
>     bool isArray;
> };
>
> class MemoryProfiler {
> public:
>     static MemoryProfiler& Instance() {
>         static MemoryProfiler inst;
>         return inst;
>     }
>
>     // 启用追踪（在 main 最开头调用）
>     void Enable() { m_enabled.store(true, std::memory_order_release); }
>     void Disable() { m_enabled.store(false, std::memory_order_release); }
>
>     // 记录一次分配
>     void OnAlloc(void* ptr, size_t size, bool isArray) {
>         if (!m_enabled.load(std::memory_order_acquire)) return;
>         if (!ptr) return;
>
>         AllocationRecord rec;
>         rec.ptr = ptr;
>         rec.size = size;
>         rec.isArray = isArray;
>         rec.timestampUs = NowUs();
>         MEMPROF_CAPTURE_STACK(rec.callstack, rec.stackDepth);
>
>         std::lock_guard<std::mutex> lock(m_mutex);
>         m_liveAllocs[ptr] = rec;
>         m_totalAllocBytes += size;
>         m_totalAllocCount++;
>         m_sizesHistogram[size]++;
>
>         // 记录到事件流（用于 Chrome Tracing 导出）
>         m_events.push_back({rec.timestampUs, size, true});
>     }
>
>     // 记录一次释放
>     void OnFree(void* ptr) {
>         if (!m_enabled.load(std::memory_order_acquire)) return;
>         if (!ptr) return;
>
>         std::lock_guard<std::mutex> lock(m_mutex);
>         auto it = m_liveAllocs.find(ptr);
>         if (it != m_liveAllocs.end()) {
>             m_totalAllocBytes -= it->second.size;
>             m_liveAllocs.erase(it);
>         }
>         m_totalFreeCount++;
>         m_events.push_back({NowUs(), 0, false});
>     }
>
>     // ---- 报告接口 ----
>
>     // 当前总分配量
>     size_t GetCurrentAllocatedBytes() const { return m_totalAllocBytes; }
>     size_t GetTotalAllocCount()     const { return m_totalAllocCount; }
>     size_t GetLiveAllocationCount() const {
>         std::lock_guard<std::mutex> lock(m_mutex);
>         return m_liveAllocs.size();
>     }
>
>     // 分配热点 — 按大小排序的 Top N
>     std::vector<std::pair<size_t, size_t>> GetAllocationHotspots(int topN = 10) {
>         std::lock_guard<std::mutex> lock(m_mutex);
>         std::vector<std::pair<size_t, size_t>> sorted(
>             m_sizesHistogram.begin(), m_sizesHistogram.end());
>         std::sort(sorted.begin(), sorted.end(),
>             [](const auto& a, const auto& b) { return a.second > b.second; });
>         if (static_cast<int>(sorted.size()) > topN)
>             sorted.resize(topN);
>         return sorted;
>     }
>
>     // 泄漏检测 — 程序退出时调用，列出所有未释放的分配
>     std::vector<AllocationRecord> DetectLeaks() {
>         std::lock_guard<std::mutex> lock(m_mutex);
>         std::vector<AllocationRecord> leaks;
>         for (const auto& [ptr, rec] : m_liveAllocs) {
>             leaks.push_back(rec);
>         }
>         std::sort(leaks.begin(), leaks.end(),
>             [](const auto& a, const auto& b) { return a.size > b.size; });
>         return leaks;
>     }
>
>     // 输出 Chrome Tracing 格式（ph:"i" 即时事件，展示在独立内存线程行）
>     void WriteChromeTrace(const std::string& filepath) {
>         std::lock_guard<std::mutex> lock(m_mutex);
>         std::ofstream out(filepath);
>
>         out << "{\"displayTimeUnit\":\"ms\",\"traceEvents\":[\n";
>
>         // 内存线程 metadata
>         out << "{\"name\":\"thread_name\",\"ph\":\"M\",\"pid\":0,\"tid\":8888,"
>             << "\"args\":{\"name\":\"Memory\"}},\n";
>
>         bool first = true;
>         for (const auto& ev : m_events) {
>             if (!first) out << ",\n";
>             first = false;
>
>             // ph:"i" = 即时事件（无时长），以圆形标记显示
>             // 大小缩放为标记半径的粗略映射
>             size_t sizeKB = ev.isAlloc ? (ev.size / 1024) : 0;
>             out << "{\"name\":\"" << (ev.isAlloc ? "Alloc" : "Free") << "\","
>                 << "\"ph\":\"i\","
>                 << "\"pid\":0,\"tid\":8888,"
>                 << "\"ts\":" << ev.timestampUs << ","
>                 << "\"s\":\"t\","
>                 << "\"args\":{\"size\":" << ev.size
>                 << ",\"sizeKB\":" << sizeKB << "}"
>                 << "}";
>         }
>
>         out << "\n]}\n";
>         out.close();
>     }
>
>     // 打印泄漏报告
>     void PrintLeakReport(std::ostream& out = std::cerr) {
>         auto leaks = DetectLeaks();
>         if (leaks.empty()) {
>             out << "[MemoryProfiler] No leaks detected.\n";
>             return;
>         }
>         out << "\n========== MEMORY LEAK REPORT ==========\n";
>         out << "Total leaked allocations: " << leaks.size() << "\n";
>         size_t totalLeaked = 0;
>         for (const auto& l : leaks) {
>             totalLeaked += l.size;
>             out << "  ptr=" << l.ptr
>                 << "  size=" << l.size
>                 << "  isArray=" << (l.isArray ? "true" : "false")
>                 << "\n";
>         }
>         out << "Total leaked bytes: " << totalLeaked << "\n";
>         out << "==========================================\n";
>     }
>
>     // 打印分配热点
>     void PrintHotspotReport(std::ostream& out = std::cout) {
>         auto hotspots = GetAllocationHotspots();
>         out << "\n========== ALLOCATION HOTSPOTS ==========\n";
>         for (const auto& [size, count] : hotspots) {
>             out << "  size=" << size << " bytes  -> " << count << " allocations\n";
>         }
>         out << "==========================================\n";
>     }
>
> private:
>     MemoryProfiler() = default;
>     ~MemoryProfiler() { PrintLeakReport(); }
>
>     static long long NowUs() {
>         return std::chrono::duration_cast<std::chrono::microseconds>(
>             std::chrono::high_resolution_clock::now().time_since_epoch()).count();
>     }
>
>     struct EventEntry {
>         long long timestampUs;
>         size_t size;
>         bool isAlloc;
>     };
>
>     std::atomic<bool> m_enabled{false};
>     mutable std::mutex m_mutex;
>     std::unordered_map<void*, AllocationRecord> m_liveAllocs;
>     std::unordered_map<size_t, size_t> m_sizesHistogram; // size->count
>     std::vector<EventEntry> m_events;
>
>     std::atomic<size_t> m_totalAllocBytes{0};
>     std::atomic<size_t> m_totalAllocCount{0};
>     std::atomic<size_t> m_totalFreeCount{0};
> };
> ```
>
> ```cpp
> // 全局 operator new/delete 重载（放在 memory_profiler.cpp 或独立翻译单元）
> #include "memory_profiler.hpp"
>
> // ---- scalar new/delete ----
> void* operator new(size_t size) {
>     void* ptr = std::malloc(size);
>     if (!ptr) throw std::bad_alloc();
>     MemoryProfiler::Instance().OnAlloc(ptr, size, false);
>     return ptr;
> }
>
> void operator delete(void* ptr) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     std::free(ptr);
> }
>
> void operator delete(void* ptr, size_t /*size*/) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     std::free(ptr);
> }
>
> // ---- array new/delete ----
> void* operator new[](size_t size) {
>     void* ptr = std::malloc(size);
>     if (!ptr) throw std::bad_alloc();
>     MemoryProfiler::Instance().OnAlloc(ptr, size, true);
>     return ptr;
> }
>
> void operator delete[](void* ptr) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     std::free(ptr);
> }
>
> void operator delete[](void* ptr, size_t /*size*/) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     std::free(ptr);
> }
>
> // ---- aligned new/delete (C++17) ----
> void* operator new(size_t size, std::align_val_t align) {
>     void* ptr = ::_aligned_malloc(size, static_cast<size_t>(align));
>     if (!ptr) throw std::bad_alloc();
>     MemoryProfiler::Instance().OnAlloc(ptr, size, false);
>     return ptr;
> }
>
> void operator delete(void* ptr, std::align_val_t /*align*/) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     ::_aligned_free(ptr);
> }
>
> void operator delete(void* ptr, size_t /*size*/, std::align_val_t /*align*/) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     ::_aligned_free(ptr);
> }
>
> void* operator new[](size_t size, std::align_val_t align) {
>     void* ptr = ::_aligned_malloc(size, static_cast<size_t>(align));
>     if (!ptr) throw std::bad_alloc();
>     MemoryProfiler::Instance().OnAlloc(ptr, size, true);
>     return ptr;
> }
>
> void operator delete[](void* ptr, std::align_val_t /*align*/) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     ::_aligned_free(ptr);
> }
>
> void operator delete[](void* ptr, size_t /*size*/, std::align_val_t /*align*/) noexcept {
>     MemoryProfiler::Instance().OnFree(ptr);
>     ::_aligned_free(ptr);
> }
> ```
>
> #### 3.2 使用示例
>
> ```cpp
> // main.cpp
> #include "memory_profiler.hpp"
>
> int main() {
>     MemoryProfiler::Instance().Enable();
>
>     // 应用程序主循环
>     for (int i = 0; i < 100; ++i) {
>         auto* buf = new char[1024];  // 刻意制造泄漏
>         if (i % 50 == 0) delete[] buf;
>     }
>
>     // 程序退出前输出报告
>     MemoryProfiler::Instance().PrintHotspotReport();
>     MemoryProfiler::Instance().WriteChromeTrace("memory_trace.json");
>
>     // 注意：DetectLeaks() / PrintLeakReport() 在 ~MemoryProfiler() 中自动调用
>     // 但由于静态析构顺序问题，建议显式调用
>     MemoryProfiler::Instance().PrintLeakReport();
>
>     MemoryProfiler::Instance().Disable();
>     return 0;
> }
> ```
>
> #### 3.3 设计要点与注意事项
>
> 1. **线程安全**：使用细粒度锁保护 `m_liveAllocs` 和 `m_events`，热路径上计数使用 `std::atomic` 避免锁竞争
> 2. **递归保护**：`OnAlloc` 内部可能触发 `std::unordered_map` 的内存分配，形成无限递归。解决方案：
>    - 使用 `std::pmr::unordered_map` + 预分配内存池，或
>    - 在 `OnAlloc` 入口处用 `thread_local` 标志位跳过追踪
> 3. **避免影响性能**：仅在 `ENABLE_MEMORY_PROFILING` 宏下编译，Release 构建中完全移除
> 4. **Chrome Tracing 输出**：内存事件写在 tid=8888 的虚拟线程上，使用 `ph:"i"` 即时事件；分配大小通过 `args.size` 字段携带
> 5. **泄漏检测可靠性**：静态对象在 `main` 返回后的析构顺序不确定，`MemoryProfiler` 的析构可能在其他静态对象之前执行，导致误报。建议显式调用 `PrintLeakReport()` 作为 `main` 的最后一步

## 4. 扩展阅读

### 官方文档与工具

- **Chrome Tracing 格式规范**: https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview
- **RenderDoc 官方文档**: https://renderdoc.org/docs/index.html
- **NVIDIA Nsight Graphics**: https://developer.nvidia.com/nsight-graphics
- **Intel GPA**: https://www.intel.com/content/www/us/en/developer/tools/graphics-performance-analyzers/overview.html
- **AMD Radeon GPU Profiler**: https://gpuopen.com/rgp/

### 深入文章

- **"The Care and Feeding of Profilers"** by Mike Acton（CppCon）：关于如何正确使用 Profiler 的经典演讲
- **"Writing a Profiler"** 系列文章：从零实现一个完整的 CPU/GPU Profiler
- **"Frame Pacing and Frame Time Analysis"**：关于 1% Low FPS 和帧时间一致性的重要性
- **"Optimizing Game Engines"** by GDC Vault：各大游戏公司的性能优化实践

### 开源参考

- **Optick**: https://github.com/bombomby/optick — C++ 跨平台 Profiler，支持 Chrome Tracing 输出，设计简洁
- **Tracy Profiler**: https://github.com/wolfpld/tracy — 功能极其强大的 C++ Profiler，支持 CPU/GPU/内存/锁分析，有独立 GUI
- **Remotery**: https://github.com/Celtoys/Remotery — 轻量级 C 语言 Profiler，Web 界面实时查看
- **microprofile**: https://github.com/jonasmr/microprofile — 嵌入式 C++ Profiler，集成简单

### 视频教程

- **CppCon 演讲**: "Writing Fast Code" by Andrei Alexandrescu
- **GDC Talk**: "Profiling and Optimizing Game Engines" 系列
- **Handmade Hero**: Casey Muratori 在开发过程中大量使用自定义 Profiler，展示了真实世界的 Profiling 实践

---

## 常见陷阱

- **过度插桩导致测量失真**：在一个极小的函数（如内联的 Vector3::Dot）上添加 `PROFILE_SCOPE`，插桩本身的开销可能比函数执行时间还长。只对"有意义的代码块"（如 Pass 级别、系统级别）插桩。

- **混淆 CPU 和 GPU 时间**：在 CPU 端对 `glDrawElements` 调用计时，得到的时间只是"提交命令"的时间，不是 GPU 实际执行的时间。GPU 工作必须用 GPU Timer Query 测量。

- **忽略多线程同步开销**：Profiler 显示主线程在等待，但这可能是因为工作线程还没完成。只看单线程火焰图会误判瓶颈。确保所有线程的 Timeline 都可见。

- **Release 构建中保留 Profiler**：Instrumentation Profiler 在 Release 构建中应该完全消失（通过宏控制），否则会影响性能且测量结果不代表真实发布版本的性能。

- **GPU Query 嵌套错误**：OpenGL 的 `GL_TIME_ELAPSED` 查询在同一目标上不能嵌套。如果需要测量嵌套区域，使用 `GL_TIMESTAMP` 记录时间点然后相减。

- **帧时间平均值的误导**：平均 FPS 可能看起来很好（如 58 FPS），但如果有偶发的 100ms 卡顿，玩家体验仍然很差。务必关注 1% Low FPS 和 P99 帧时间。

- **Debug 可视化影响性能**：调试可视化本身会消耗 GPU 资源（额外的 Draw Call、线框渲染）。确保它可以通过开关完全禁用，且默认在 Release 构建中关闭。

- **Assert 中执行副作用**：`ASSERT(ptr = GetPointer())` 这种写法在 Release 构建中会完全消失，导致 `GetPointer()` 不被调用。Assert 中只应检查条件，不应有副作用。使用 `VERIFY` 如果需要执行表达式。

- **崩溃报告中的死锁**：如果在信号处理函数中调用非异步信号安全的函数（如 `malloc`、`printf`、某些锁操作），可能导致死锁。崩溃处理函数应尽可能简单，优先使用系统调用写入日志文件。
