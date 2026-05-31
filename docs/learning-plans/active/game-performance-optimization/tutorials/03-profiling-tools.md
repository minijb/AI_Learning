# Profiling 工具概览

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: 02-profiling-methodology（理解测量方法学）

---

## 1. 概念讲解

### 为什么需要这个？

你已经掌握了测量方法学 — 知道需要统计分布、百分位、暖身。但你还缺少最关键的一环：**工具**。

手动在代码里插 `std::chrono` 能测量你自己写的子系统的耗时，但面对以下问题它力不从心：
- "为什么 `glDrawElements` 调用花了 3ms？是在等 GPU 还是在做驱动验证？"
- "这个函数的 40% 时间花在一个我根本没意识到的隐式转换上"
- "多线程环境下，哪个线程被阻塞了？被谁阻塞的？"
- "GPU 在这一帧里做了什么？像素 Shader 花了多少时间？"

**没有正确的工具，你就像在黑暗中摸索。** 你需要一个覆盖 CPU 和 GPU、从宏观热点到微观指令的多层次工具链。

好消息是：游戏性能分析的工具体系已经非常成熟。坏消息是：工具太多了，需要知道什么时候用什么。

#### 工具盲选的代价

| 场景 | 错误工具 | 后果 |
|------|----------|------|
| CPU 帧时间突增 | 只看 RenderDoc (GPU工具) | 看不到 CPU 侧的瓶颈 |
| GPU 着色时间长 | 只在 CPU 端打点 | PIX 或 RenderDoc 才能看到单个 Draw Call 的 GPU 耗时 |
| 内存泄漏 | 只用 CPU Profiler | 需要内存 Profiler 查看分配栈 |
| 多线程死锁 | 只用单线程 Profiler | 需要支持线程间依赖可视化的工具 |

### 核心思想

将 Profiling 工具分为四个大类，每类解决不同维度的问题：

```
┌─────────────────────────────────────────────────────────────┐
│                    Profiling 工具箱                          │
├─────────────────┬─────────────────┬─────────────────────────┤
│  CPU Profilers  │  GPU Profilers  │  Memory Profilers       │
│  (Tracy, VTune, │  (RenderDoc,    │  (Valgrind/Massif,      │
│   Superluminal, │   PIX, NSight,  │   Heaptrack,            │
│   Instruments)  │   RGP)          │   Unity Memory Profiler)│
├─────────────────┴─────────────────┴─────────────────────────┤
│  引擎内置 Profiler (Unity Profiler, Unreal Insights)          │
│  平台级工具 (ETW/WPA, DTrace, Perfetto, systrace)             │
└─────────────────────────────────────────────────────────────┘
```

#### CPU Profilers — 性能分析的起点

CPU Profiler 回答："程序的时间花在哪里？"

**采样型 (Sampling) Profiler**：
- 原理：以固定频率（通常 1–10kHz）中断 CPU，记录当前指令指针和调用栈
- 优点：开销极低（通常 <5%），不会显著改变程序行为
- 缺点：会漏掉非常短的函数；如果被中断时线程在睡眠，则不会被采样到
- 代表：**Tracy** (游戏行业首选)、Superluminal、VTune、Linux perf、Instruments (macOS)

**插桩型 (Instrumentation) Profiler**：
- 原理：在函数入口/出口自动插入代码（编译器插入或二进制重写）
- 优点：精确到每一次调用，不会漏掉短函数
- 缺点：开销大（可能 2-10 倍慢），且插桩本身改变了缓存行为和时序
- 代表：gprof、Callgrind、Orbit

**Tracy 的特殊之处**：Tracy 是*混合型* — 你手动标记 Zone（插桩），但 Tracy 内部使用采样来收集上下文。这给了你两全其美：精确标注（你知道哪些是你关心的逻辑区段）和低开销。Tracy 还支持 GPU 时间线、锁竞争检测、内存分配追踪、Plot（时序变量）— 这是为什么它已成为游戏行业的事实标准。

#### GPU Profilers — 理解 GPU 行为

GPU Profiler 回答："GPU 在这帧里做了什么？哪个 Pass 最耗时？"

**帧捕获型 (Frame Capture)**：
- 原理：截获一帧所有的图形 API 调用（D3D/Vulkan/Metal），记录其参数、状态和 GPU 耗时
- 可以逐 Draw Call / 逐 Dispatch 查看 GPU 执行时间
- 可以查看输入/输出资源（看到某个 RenderTexture 的中间结果）
- 可以查看 Shader 的汇编代码、寄存器使用、占用率
- 代表：**RenderDoc** (跨平台开源)、PIX (Windows/DirectX 官方)、NSight Graphics (NVIDIA)、Radeon GPU Profiler (AMD)

**连续 Profiling**：
- 原理：不中断执行，持续收集 GPU 性能计数器
- 可以看到长时间的 GPU 行为模式
- 代表：NSight Systems、Tracy GPU 集成

#### 内存 Profilers — 追踪分配

回答："内存在哪里分配？谁在分配？有没有泄漏？"

- **Valgrind/Massif**：Linux 上经典的内存 Profiler，取定期快照看堆使用量
- **Heaptrack**：更现代的工具，记录每次分配的调用栈和生命周期。开销比 Valgrind 低
- **Unity Memory Profiler**：Unity 内置，能看到 Managed 堆和 Native 堆的分配

#### 引擎内置 Profiler — 日常驾驶舱

- **Unity Profiler**：集成了 CPU/GPU/Memory/Rendering/Physics/Audio 等所有子系统的视图。开发时挂在编辑器里持续观察。
- **Unreal Insights**：UE5 的下一代 Profiler，基于 Trace 事件，支持帧内各系统的详细时序。替代了旧版的 Session Frontend。

#### 平台级工具 — 操作系统层面的视图

- **Windows ETW (Event Tracing for Windows) + WPA (Windows Performance Analyzer)**：能看到所有进程的 CPU 调度、磁盘 I/O、网络、电源管理。适合分析"为什么我的游戏偶尔卡半秒"（可能是系统进程在捣乱）。
- **Perfetto / systrace (Android)**：Android 上的系统级 Trace，能看到 CPU 频率变化、调度、GPU 活动。
- **DTrace / Instruments (macOS/iOS)**：Apple 平台的系统级工具。

#### 工具选择决策树

```
想了解整体的 CPU 热点?
├── 是 → 用 Tracy / Superluminal（游戏项目首选）
│       → 或 VTune（Intel CPU 深度分析）
│       → 或 Instruments（macOS/iOS）

想分析单帧的 GPU 行为?
├── 是 → RenderDoc（跨平台开源首选）
│       → PIX（Windows/DirectX 官方）
│       → NSight Graphics（NVIDIA GPU 深度分析）

想知道内存分配情况?
├── 是 → Heaptrack / Massif（Linux）
│       → Tracy Memory（已集成在 CPU Profiling 中）

想在日常开发中持续监控?
├── Unity → Unity Profiler 窗口
├── Unreal → Unreal Insights / stat 命令

遇到多线程竞争/死锁?
├── 是 → Tracy Lock
│       → Superluminal 线程视图
```

---

## 2. 代码示例

以下演示如何将 Tracy 集成到一个 C++ 游戏循环中。Tracy 是 C++ 游戏性能分析的事实标准，因为它：
- 开销极低（手动标记 Zone 的开销约 2-5ns）
- 支持 CPU+GPU 同时追踪
- 实时连接，不需要先记录后分析
- 支持帧标记、Plot（时序变量图）、内存追踪、锁检测

```cpp
// tracy_game_loop.cpp — Minimal Tracy integration for a game loop
//
// 编译前需要:
// 1. 下载 Tracy: git clone https://github.com/wolfpld/tracy
// 2. 将 tracy/public 目录加入 include path
// 3. 将 tracy/public/TracyClient.cpp 加入编译
// 4. 链接: -lpthread -ldl (Linux) 或 ws2_32.lib dbghelp.lib (Windows)

#include <chrono>
#include <thread>
#include <vector>
#include <random>
#include <iostream>

// Tracy 集成 — 只需要一个头文件
// 可选: 定义 TRACY_ENABLE 来启用; 不定义则所有宏编译为空操作
#define TRACY_ENABLE
#include "tracy/Tracy.hpp"

// ====================================================================
// 模拟游戏子系统
// ====================================================================

class PhysicsSystem {
public:
    void Update(float dt) {
        // ZoneScoped 标记此函数为一个 Tracy Zone
        // Tracy 会记录进入/退出时间，并在时间线上显示
        ZoneScoped;
        // 模拟物理计算: 2-4ms
        SimulateWork(2.0f, 4.0f);

        // 报告碰撞对数到 Tracy Plot (折线图)
        int collisions = static_cast<int>(dt * 100.0f) % 50 + 10;
        TracyPlot("Physics/Collisions", collisions);
    }
};

class AISystem {
public:
    void Update(float dt) {
        ZoneScoped;
        // 模拟 AI 决策: 0.5-2ms
        SimulateWork(0.5f, 2.0f);

        int active_agents = 120 + (rand() % 30);
        TracyPlot("AI/ActiveAgents", active_agents);
    }
};

class RenderSystem {
public:
    void BeginFrame() {
        // FrameMark 标记帧边界 — Tracy 据此分割每帧
        FrameMark;
    }

    void CullObjects() {
        ZoneScopedN("CullObjects"); // 带自定义名称的 Zone
        SimulateWork(0.5f, 1.5f);
    }

    void SubmitDrawCalls(int count) {
        ZoneScoped;
        ZoneValue(count); // 记录一个数值 — 在 Tracy GUI 中可以看到这个 Zone 的附加值
        SimulateWork(0.5f, 3.0f);
    }

    void GPUPass() {
        // Tracy 也支持 GPU Zone — 需要图形 API 集成
        // 对于此示例，我们模拟 GPU 时间
        ZoneScopedN("GPUWork");
        // 设置 Zone 颜色为深蓝 (0xRRGGBB)
        ZoneColor(0x224488);
        SimulateWork(3.0f, 8.0f);
    }
};

// ====================================================================
// 辅助: 模拟耗时操作
// ====================================================================
void SimulateWork(float min_ms, float max_ms) {
    static thread_local std::mt19937 rng(42);
    float target = min_ms + (max_ms - min_ms) * (float)(rng() % 1000) / 1000.0f;

    auto start = std::chrono::high_resolution_clock::now();
    while (true) {
        auto now = std::chrono::high_resolution_clock::now();
        double elapsed = std::chrono::duration<double, std::milli>(now - start).count();
        if (elapsed >= target) break;
    }
}

// ====================================================================
// 主循环
// ====================================================================
int main() {
    std::cout << "Tracy-integrated Game Loop\n";
    std::cout << "=========================\n";
    std::cout << "启动 Tracy Profiler GUI (tracy-profiler) 并连接到本程序\n";
    std::cout << "如果未连接 Tracy, 所有宏都是空操作, 零开销\n\n";

    PhysicsSystem physics;
    AISystem      ai;
    RenderSystem  render;

    float delta_time = 1.0f / 60.0f;
    int frame_count = 0;

    // 主消息宏 — 在 Tracy 消息日志中显示
    TracyMessageL("GameLoop: Starting main loop");

    while (frame_count < 600) { // 运行 600 帧用于演示
        render.BeginFrame(); // FrameMark 在这里

        {
            ZoneScopedN("Frame");
            // 用颜色标记帧的不同区间
            ZoneColor(0x448844); // 深绿色

            // ---- 输入处理 ----
            {
                ZoneScopedN("Input");
                ZoneColor(0x888844);
                SimulateWork(0.1f, 0.3f);
            }

            // ---- 游戏逻辑 ----
            {
                ZoneScopedN("GameLogic");
                physics.Update(delta_time);
                ai.Update(delta_time);
            }

            // ---- 渲染 ----
            {
                ZoneScopedN("Rendering");
                ZoneColor(0x444488);

                render.CullObjects();
                render.SubmitDrawCalls(200 + (frame_count % 30) * 10);
                render.GPUPass();
            }
        }

        // 每 60 帧打印进度
        if (frame_count % 60 == 0) {
            std::cout << "Frame " << frame_count << " / 600\n";
        }

        frame_count++;

        // 模拟 vsync 等待
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }

    // 发送完成消息
    TracyMessageL("GameLoop: Finished 600 frames", 600);

    std::cout << "\n完成! 在 Tracy GUI 中你应该看到:\n";
    std::cout << "  1. 按 'Frame' 分割的时间线\n";
    std::cout << "  2. Frame > GameLogic > Physics > Update 的层级\n";
    std::cout << "  3. Physics/Collisions 和 AI/ActiveAgents 的折线图\n";
    std::cout << "  4. 每个 Zone 的 min/max/avg 统计\n";

    return 0;
}

// ====================================================================
// Tracy 设置 — 可选
// ====================================================================
// 如果你想要程序在没有 Tracy 连接时自动退出（不阻塞等待连接）:
// #define TRACY_NO_EXIT
//
// 配置固定的服务端端口:
// #define TRACY_PORT 8086
//
// 只允许本机连接:
// #define TRACY_ONLY_LOCALHOST
//
// 更多选项见 tracy/public/common/TracySystem.cpp
```

**运行方式:**

```bash
# 第一步: 下载 Tracy
git clone https://github.com/wolfpld/tracy.git

# 第二步: 编译本程序 (Linux)
g++ -std=c++17 -O2 -DTRACY_ENABLE \
    -I tracy/public \
    tracy/public/TracyClient.cpp \
    tracy_game_loop.cpp \
    -lpthread -ldl \
    -o tracy_game_loop

# 第三步: 启动 Tracy Profiler GUI
# 从 https://github.com/wolfpld/tracy/releases 下载预编译的 Tracy GUI
# 或自己编译 tracy/profiler

# 第四步: 运行程序
./tracy_game_loop

# 第五步: 在 Tracy GUI 中点击 "Connect" 连接到 localhost
```

**预期输出:**

```text
Tracy-integrated Game Loop
=========================
启动 Tracy Profiler GUI (tracy-profiler) 并连接到本程序
如果未连接 Tracy, 所有宏都是空操作, 零开销

Frame 0 / 600
Frame 60 / 600
...
Frame 540 / 600

完成! 在 Tracy GUI 中你应该看到:
  1. 按 'Frame' 分割的时间线
  2. Frame > GameLogic > Physics > Update 的层级
  3. Physics/Collisions 和 AI/ActiveAgents 的折线图
  4. 每个 Zone 的 min/max/avg 统计
```

**在 Tracy GUI 中你会看到**：
- 主时间线按 Frame 分段，每帧展开 Input → GameLogic → Rendering
- 点击 `Physics::Update` 可以看到该 Zone 的统计：出现次数、平均耗时、min/max
- "Find Zone" 功能可以搜索任意 Zone，查看它的调用栈
- Plot 视图显示 `Physics/Collisions` 随时间的变化
- 内存视图显示分配/释放（如果你启用了 Tracy 内存追踪）

---

## 3. 练习

### 练习 1: 安装 Tracy 并 Instrument 一个 C++ 循环

写一个简单的 C++ 程序：
- 包含 3 个嵌套的函数调用（可以只是 `sleep` 或计算循环）
- 在最外层用 `FrameMark` 标记帧
- 在内层用 `ZoneScoped` 标记每个函数
- 使用 `ZoneValue` 记录一个循环变量

编译运行，在 Tracy GUI 中连接，验证你能看到完整的调用层级。

**验收标准**：Tracy GUI 时间线上能看到 3 层嵌套的 Zone，且展开后能看到 `ZoneValue` 数值。

### 练习 2: 安装 RenderDoc 并捕获一帧

1. 从 https://renderdoc.org/ 下载并安装 RenderDoc
2. 启动任何你有的游戏或 3D 演示程序（如果没有，可以用 RenderDoc 自带的测试程序）
3. 用 RenderDoc 的 "Launch Application" 功能启动目标程序
4. 按 F12 或 PrintScreen 捕获一帧
5. 在 Texture Viewer 中浏览所有 Render Target 的中间状态
6. 在 Event Browser 中找一个耗时最长的 Draw Call，查看它的 Vertex Shader 和 Pixel Shader

**验收标准**：能打开捕获的帧，在时间线上定位到至少一个具体的 Draw Call 并查看其输入/输出纹理。

### 练习 3: 对比 Tracy ZoneScoped 和 std::chrono 的测量开销（可选）

设计一个实验：
- 写一个循环，调用 100,000 次一个非常短的空函数
- 分别用 `ZoneScoped` + Tracy 和 `std::chrono::high_resolution_clock` 测量这 100,000 次调用的总时间
- 也测量没有任何测量的基线（裸调用）
- 计算额外开销：`(有测量 - 基线) / 调用次数`

对比结果：Tracy 的 ZoneScoped 开销约 **2-5 纳秒**（在有 `TRACY_ENABLE` 时），而 `std::chrono` 的开销通常在 **20-100 纳秒**。这就是为什么 Tracy 能做到"几乎无感"的插桩。

---

## 4. 扩展阅读

- [Tracy Profiler — 官方手册](https://github.com/wolfpld/tracy/releases/latest/download/tracy.pdf) — 完整的 PDF 手册，涵盖所有宏和配置
- [RenderDoc Documentation](https://renderdoc.org/docs/) — 官方文档，从入门到高级
- [AMD Radeon GPU Profiler (RGP) Documentation](https://gpuopen.com/rgp/) — AMD GPU 的底层分析工具
- [NVIDIA NSight Graphics Documentation](https://developer.nvidia.com/nsight-graphics) — NVIDIA GPU 专用工具
- [Windows Performance Analyzer (WPA) 入门](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/windows-performance-analyzer) — ETW/WPA 官方文档，理解系统级性能问题

---

## 常见陷阱

- **只用一种工具**：CPU Profiler 看不到 GPU 瓶颈，GPU Profiler 看不到 CPU 瓶颈，内存 Profiler 看不到帧时间。一个完整的分析流程通常需要至少 2-3 种工具配合。

- **在非目标平台上 Profiling**：在开发机（64GB RAM, RTX 4090）上 Profile 和在目标平台（8GB RAM, GTX 1060）上 Profile，结果可能完全不同。内存压力、GPU 能力、CPU 核心数都不同。**始终在最低目标平台上验证性能。**

- **忽略 Profiler 自身的开销**：虽然 Tracy 的 ZoneScoped 开销极低，但过多的 Zone（比如在一个每帧调用 10,000 次的循环里打 Zone）仍会累积。合理设计 Zone 的粒度 — 通常在函数级别或子系统级别插入，而不是在每条语句上。

- **Tracy 回调模式 vs 按需模式混淆**：Tracy 有"客户端主动连接服务端"和"服务端发现客户端"两种模式。如果你用默认设置但 Tracy GUI 连不上，检查防火墙、端口、网络配置。在本地开发时通常用 `TRACY_ONLY_LOCALHOST` 就够了。

- **GPU Profiling 时未考虑 PSO (Pipeline State Object) 创建**：第一次捕获时，很多 Draw Call 的 GPU 时间可能包含 Shader 编译时间。让场景先跑几秒（Shader Warmup）再捕获，否则数据分析会被编译时间误导。
