---
title: "CPU Profiling 实战 — Tracy/Superluminal"
updated: 2026-06-05
---

# CPU Profiling 实战 — Tracy/Superluminal
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50 分钟
> 前置知识: 多线程基础（第 14 节）、帧分析基础（第 4 节）、C++ 函数调用与作用域概念
---
## 1. 概念讲解

### 为什么需要这个？

你已经知道了 CPU 端各个子系统（物理、渲染命令生成、AI、动画）在逻辑上是分开的。但**它们在时间线上实际是怎么分布的**？物理计算是不是在某帧突然花了 10ms？AI 寻路是不是在主线程上偷偷阻塞了渲染？多线程任务系统里的 Worker Thread 真的有在工作，还是在等锁空转？

CPU Profiler 回答这些问题。它不是帧计数器——它是 **时间显微镜**，让你看到：
- 每一帧内，CPU 上的每个函数各花了多少微秒
- 多线程之间的依赖关系——谁在等谁
- 内存分配的热点区域
- 帧与帧之间的性能变化轨迹

### 核心思想

CPU Profiling 有两大学派：

| | **Instrumentation（插桩）** | **Sampling（采样）** |
|---|---|---|
| **代表工具** | Tracy, Chrome Tracing | Superluminal, VTune, Instruments |
| **原理** | 在代码中手动插入 `ZoneScoped` 宏，记录进入/退出时间 | 以固定频率（如 1kHz）中断 CPU，记录当前指令地址和调用栈 |
| **精度** | 精确到每次调用的纳秒级 | 统计近似（采样频率越高越准） |
| **开销** | 视 Zone 密度而定（每次进入/退出 ~10-30ns） | 极低（~1-3% CPU），几乎感觉不到 |
| **优点** | 精确时间线、可标注逻辑含义、支持 GPU Zone | 零代码入侵、开销极低、调用栈完整 |
| **缺点** | 需要手动标记代码、过度插桩会影响性能 | 不精确（短函数可能完全漏掉）、语义层缺失 |

**选择策略**：
- 如果你能改代码 + 需要精确时间线 + 跨平台（含 GPU）→ **Tracy**
- 如果你不能改代码（如第三方库内部） + 需要快速定位热点函数 → **Superluminal**
- 实际项目中：两者都备着。Tracy 做日常开发监控，Superluminal 做深度排查。

### Tracy 架构概览

```
┌──────────────────┐          TCP (网络)         ┌─────────────────┐
│ 你的游戏进程      │ ──────────────────────────→  │ Tracy Server     │
│ (Client)         │  实时发送 Zone/Plot/内存数据  │ (GUI)            │
│ 链接 tracy.dll   │                              │ tracy-profiler   │
└──────────────────┘                              └─────────────────┘
```

Tracy 分为两部分：
1. **Client** (`Tracy.hpp` + 链接到你的项目)：收集 Zone、Plot、内存分配等数据
2. **Server** (`Tracy.exe` GUI)：接收、存储、可视化这些数据

通信基于 TCP，因此可以 Profiling 远程设备（如游戏主机、手机）。

### Superluminal 架构概览

Superluminal 是纯采样型的：它通过 ETW（Event Tracing for Windows）从内核获取 CPU 采样数据，不需要你写任何 `ZoneScoped`。它会自动解析 PDB 符号文件，把采样地址映射到函数名。

---
## 2. 代码示例

### 示例 1: Tracy 完整集成

#### 步骤 1: 获取并编译 Tracy

```bash
# 克隆 Tracy 仓库
git clone https://github.com/wolfpld/tracy.git
cd tracy

# Tracy 只需要一个 .cpp 文件被编译到你的项目中
# 核心文件: public/TracyClient.cpp
# 你只需要:
#   1. 添加 public/ 目录到 include path
#   2. 将 public/TracyClient.cpp 添加到你的 CMake 构建
#   3. 在项目根 CMakeLists.txt 中添加一行定义
```

```cmake
# CMakeLists.txt 最小集成示例
cmake_minimum_required(VERSION 3.16)
project(MyGame)

# 定义启用 Tracy 的宏（在 TracyClient.cpp 编译前定义）
# TRACY_ENABLE: 开启 Profiling 数据收集
# TRACY_ON_DEMAND: 只在 Tracy Server 连接时才收集数据（零开销当不连接时）
add_compile_definitions(TRACY_ENABLE TRACY_ON_DEMAND)

# 添加 Tracy 源文件
add_library(tracy_client STATIC
    tracy/public/TracyClient.cpp
)
target_include_directories(tracy_client PUBLIC tracy/public)

# 你的游戏可执行文件
add_executable(my_game
    src/main.cpp
    src/render_system.cpp
    src/physics_system.cpp
    src/ai_system.cpp
    src/particle_system.cpp
    src/job_system.cpp
)
target_link_libraries(my_game PRIVATE tracy_client)

# Windows 需要链接 ws2_32 和 dbghelp（Tracy 的依赖）
if(WIN32)
    target_link_libraries(my_game PRIVATE ws2_32 dbghelp)
endif()
```

#### 步骤 2: 在你的游戏代码中插入 Tracy 标记

```cpp
// main.cpp — 游戏主循环中的 Tracy 集成示例
#include "Tracy.hpp"

// 全局帧标记：在帧开始时调用
// FrameMark 告诉 Tracy "新的一帧开始了"
// 没有它，Tracy 无法按帧切分时间线

int main(int argc, char *argv[]) {
    // Tracy 会自动初始化，无需显式调用任何 Setup 函数
    // 但你可以设置程序名（在 Tracy Server 中显示）：
    // tracy::SetThreadName("MainThread");

    InitEngine();

    while (running) {
        // =============================================
        // 帧标记 — 这是 Tracy 帧分析的基础
        // =============================================
        FrameMark;  // 告诉 Tracy: 上一帧结束，新帧开始

        // =============================================
        // ZoneScoped: 自动作用域 Zone
        // 进入作用域时记录开始时间，离开时记录结束时间
        // 宏自动使用当前函数名作为 Zone 名称
        // =============================================
        {
            ZoneScoped;  // 这个 Zone 名叫 "main loop body"

            float dt = UpdateDeltaTime();

            UpdateInput();
            UpdatePhysics(dt);
            UpdateAI(dt);
            UpdateParticles(dt);
            SubmitRenderCommands();
            PresentFrame();
        }

        // FrameMarkEnd 只在手动帧控制时需要
        // 通常 FrameMark 就足够了
    }

    return 0;
}
```

```cpp
// physics_system.cpp — 多层级 Zone 标记
#include "Tracy.hpp"

// 方式 1: ZoneScoped — 自动用函数名
void UpdatePhysics(float dt) {
    ZoneScoped;  // Zone: "UpdatePhysics"

    BroadPhaseCollision();
    NarrowPhaseCollision(dt);
    ResolveConstraints(dt);
    UpdateTransforms();
}

// 方式 2: ZoneScopedN(name) — 自定义名称
void BroadPhaseCollision() {
    ZoneScopedN("BroadPhase");  // Zone: "BroadPhase"

    // 对大量物体做粗略的 AABB 相交检测
    UpdateBVH();      // 这个函数内部有自己的 ZoneScoped
    QueryOverlaps();
}

// 方式 3: ZoneNamed 宏 — 可以中途结束
void NarrowPhaseCollision(float dt) {
    ZoneNamed(zoneNarrow, "NarrowPhase");  // Zone 从这里开始

    for (auto &pair : g_overlapPairs) {
        // 手动给每个碰撞对加 Zone？开销太大！
        // 改用 ZoneNamed 的条件版本：

        if (pair.distance < g_contactThreshold) {
            ZoneNamedN(zoneContact, "GenerateContacts", true);  // true = active
            GenerateContacts(pair);
            // zoneContact 在此作用域结束时自动关闭
        } // ← zoneContact 的隐式结束
    }

    // zoneNarrow 在此函数结束时自动关闭
} // ← zoneNarrow 的隐式结束

// 方式 4: ZoneText — 给 Zone 附加运行时信息
void ResolveConstraints(float dt) {
    ZoneScoped;

    int totalContacts = 0;
    int iterationsUsed = 0;

    for (int iter = 0; iter < 10; iter++) {
        int solved = SolveConstraintBatch(iter);
        totalContacts += solved;
        iterationsUsed = iter + 1;
        if (solved == 0) break;
    }

    // 在 Tracy 中点击此 Zone 时会显示这段文本
    ZoneTextF("Contacts: %d, Iterations: %d", totalContacts, iterationsUsed);
}
```

```cpp
// ai_system.cpp — Plot（数值追踪）与 Message
#include "Tracy.hpp"

// Plot：追踪某个数值在一段时间内的变化
// 示例：追踪活跃 AI Agent 数量
static int g_activeAgents = 0;

void UpdateAI(float dt) {
    ZoneScoped;

    g_activeAgents = CountActiveAgents();
    // TracyPlot 发送一个数据点到 Server：
    // 在 Server 中可以看到 "Active Agents" 随时间变化的折线图
    TracyPlot("Active Agents", (int64_t)g_activeAgents);

    // 也可以追踪浮点值：
    float avgDecisionTime_ms = UpdateDecisionTrees(dt);
    TracyPlot("AI Avg Decision Time (ms)", avgDecisionTime_ms);

    // Message：在时间线上标记事件
    if (g_activeAgents > 500) {
        TracyMessageL("AI: Agent count exceeded 500!");
    }
}
```

```cpp
// job_system.cpp — 线程与多线程 Zone 标记
#include "Tracy.hpp"

// Tracy 自动追踪线程名称
// 你可以在创建线程时显式设置：
void WorkerThreadFunction(int threadIndex) {
    // 设置线程名（在 Tracy Server 中可见）
    tracy::SetThreadNameF("Worker-%d", threadIndex);

    while (true) {
        Job *job = WaitForJob();
        if (!job) continue;

        {
            ZoneScopedN("Execute Job");

            // Zone 可以附加颜色（ARGB）
            ZoneColor(tracy::Color::Blue4);

            job->Execute();
        }
    }
}

// 对于 Task Graph / Job System：
struct PhysicsJob : public Job {
    void Execute() override {
        ZoneScopedN("Physics Job");
        // ...
    }
};
```

```cpp
// render_system.cpp — GPU Zone + Vulkan/DX12 集成
#include "Tracy.hpp"
#include "TracyVulkan.hpp"  // Vulkan GPU Zone
// 或 #include "TracyD3D12.hpp"  // D3D12 GPU Zone
// 或 #include "TracyOpenGL.hpp" // OpenGL GPU Zone

// =====================================================
// Vulkan GPU Zone 集成示例
// =====================================================

// 1. 在 VkDevice 创建后，创建 TracyVkCtx
TracyVkCtx g_tracyVkCtx;

void InitVulkanTracy(VkPhysicalDevice physDevice, VkDevice device,
                     VkQueue graphicsQueue, VkCommandBuffer cmdBuf) {
    // 需要传入物理设备、设备、图形队列、一个用于校准时间戳的命令缓冲
    g_tracyVkCtx = TracyVkContext(physDevice, device, graphicsQueue, cmdBuf);
    // TracyVkContext 会自动查询时间戳频率并做 CPU/GPU 时间校准
}

// 2. 在渲染代码中使用 GPU Zone
void RenderFrame() {
    ZoneScoped;  // CPU 端的根 Zone

    VkCommandBuffer cmd = BeginCommandBuffer();

    // =============================================
    // GPU Zone: 标记 GPU 时间线上的区间
    // =============================================
    {
        // 在 Record Command Buffer 时收集 GPU Zone
        // TracyVkZone 宏需要一个 CommandBuffer
        TracyVkZone(g_tracyVkCtx, cmd, "Shadow Pass");

        vkCmdBeginRenderPass(cmd, &shadowPassInfo, VK_SUBPASS_CONTENTS_INLINE);
        RenderShadowPass(cmd);
        vkCmdEndRenderPass(cmd);
    } // ← GPU Zone "Shadow Pass" 结束

    {
        TracyVkZone(g_tracyVkCtx, cmd, "GBuffer Pass");
        vkCmdBeginRenderPass(cmd, &gbufferPassInfo, VK_SUBPASS_CONTENTS_INLINE);
        RenderOpaqueGeometry(cmd);
        vkCmdEndRenderPass(cmd);
    }

    {
        TracyVkZone(g_tracyVkCtx, cmd, "Lighting Pass");
        vkCmdBeginRenderPass(cmd, &lightingPassInfo, VK_SUBPASS_CONTENTS_INLINE);
        ComputeLighting(cmd);
        vkCmdEndRenderPass(cmd);
    }

    // 3. 在 Submit 时调用 TracyVkCollect 收集 GPU 时间戳
    EndCommandBuffer(cmd);
    vkQueueSubmit(graphicsQueue, 1, &submitInfo, fence);

    // 必须在 Queue Submit 之后调用
    TracyVkCollect(g_tracyVkCtx, cmd);
}

// 4. 清理
void ShutdownVulkanTracy() {
    TracyVkDestroy(g_tracyVkCtx);
}
```

```cpp
// memory_tracking.cpp — 内存分配追踪
#include "Tracy.hpp"

// Tracy 可以替代全局 operator new/delete 来追踪所有内存分配
// 无需在每个 new/delete 处手动标记！

// 方法 1: 使用 Tracy 提供的宏替换全局 new/delete
// 在 CMake 中添加: target_compile_definitions(my_game PRIVATE TRACY_ENABLE TRACY_ON_DEMAND)
// 确保编译 public/TracyClient.cpp 时启用了 TRACY_ENABLE

// 方法 2: 手动使用 TracyAlloc/TracyFree
void *operator new(std::size_t count) {
    void *ptr = std::malloc(count);
    TracyAlloc(ptr, count);  // 通知 Tracy：分配了 count 字节
    return ptr;
}

void operator delete(void *ptr) noexcept {
    TracyFree(ptr);  // 通知 Tracy：释放了这块内存
    std::free(ptr);
}

// 方法 3: 自定义分配器中使用
class GameAllocator {
public:
    void *Allocate(size_t size, const char *tag) {
        void *ptr = ::malloc(size);
        // 带调用栈的分配追踪
        TracyAllocS(ptr, size, 10);  // 10 = 调用栈深度
        return ptr;
    }

    void Deallocate(void *ptr) {
        TracyFree(ptr);
        ::free(ptr);
    }
};

// 方法 4: 按类别追踪内存
// 在 Tracy Server 的 "Memory" 面板中，可以看到按标签分组的分配情况
void *AllocateTexture(size_t size) {
    void *ptr = ::malloc(size);
    TracyAllocN(ptr, size, "Texture");
    return ptr;
}
void *AllocateMesh(size_t size) {
    void *ptr = ::malloc(size);
    TracyAllocN(ptr, size, "Mesh");
    return ptr;
}
```

### 示例 2: Tracy Server 界面解读

启动 Tracy Server（`Tracy.exe`）后，它会在 `localhost:8086` 监听连接。当你的游戏启动并连接到 Server 后，你会看到以下几个核心面板：

#### 面板 1: Frame Timeline（帧时间线）

这是最重要的面板。横轴是时间（微秒），纵轴是线程。

```
Main Thread  |█████████░░░░░░|█████████████░░|███████████████|
             | Update    Idle | Phys  Render  | AI   Present  |
Worker-0     |░░░░░░█████░░░░░|███████████████|░░░░░░░░░░░░░░░|
             |        Job 1   | Physics Jobs   |               |
Worker-1     |░░░░░░███████░░░|███████████████|░░░░░░░░░░░░░░░|
             |        Job 2   | Physics Jobs   |               |
GPU          |················|████████████████|███████████████|
             |                | Shadow GBuf Lit|  PostProcess  |
```

**解读要点**：
- **主线程上的空白（Idle）** → 主线程在等待什么？可能是 vsync、worker 完成、或锁
- **Worker 线程大量空白** → Job 不够多，或者 Job 尺寸太大导致负载不均衡
- **GPU 延迟启动**（`····`）→ CPU 提交命令到 GPU 实际执行之间有延迟，说明 CPU 在前半帧没有提交足够的工作给 GPU

#### 面板 2: Zone Statistics（Zone 统计）

显示所有 Zone 的聚合统计：

| Zone Name | Total Time (ms) | Count | Mean (μs) | Min (μs) | Max (μs) |
|-----------|-----------------|-------|-----------|----------|----------|
| UpdatePhysics | 72.4 | 300 | 241.3 | 180 | 890 |
| BroadPhase | 38.1 | 300 | 127.0 | 95 | 450 |
| NarrowPhase | 34.3 | 300 | 114.3 | 85 | 440 |
| UpdateAI | 45.2 | 300 | 150.7 | 120 | 2300 |

**解读**：AI 的 Max 是 2300μs (2.3ms) 而 Mean 只有 151μs。这说明 AI 大部分时候很快，但偶尔有一个巨大的尖峰。你应该用 "Compare Frames" 功能找出尖峰对应的那帧，查看该帧内 AI Zone 的详细子 Zone 分布。

#### 面板 3: Find Zone

可以全局搜索 Zone 名。例如搜索 "alloc" 找出所有内存分配相关的 Zone。结合 `TracyAlloc` 宏，你可以直接在时间线上看到每次分配的时机和大小。

#### 面板 4: Compare Frames

选择两帧（如：一帧正常、一帧卡顿），Tracy 会高亮时间差异。差异大的 Zone 就是性能波动的原因。

### 示例 3: Superluminal 替代方案

如果你不想插桩任何代码，Superluminal 提供零入侵的 CPU 分析：

```bash
# 1. 安装 Superluminal (https://www.superluminal.eu/)
#    免费试用版，商业版付费

# 2. 启动 Superluminal、选择 "Profile"
#    选择你的 .exe 文件、点击 "Start"

# 3. Superluminal 会:
#    - 自动采集 CPU 采样（ETW 内核级，1kHz 默认）
#    - 自动解析 PDB 符号
#    - 显示热点函数排序

# 4. Superluminal 的关键视图:
```

| 视图 | 功能 | 类似 Tracy 的什么 |
|------|------|------------------|
| **Timeline** | 线程级时间线，显示函数调用栈 | Frame Timeline |
| **Functions** | 按 Self Time / Total Time 排序的函数列表 | Zone Statistics |
| **Call Tree** | 选中函数的完整调用树（谁调用了它，它调用了谁） | 无直接对应 |
| **Threads** | 每个线程的 CPU 利用率曲线 | 无直接对应 |

Superluminal 的核心优势：**直接告诉你"CPU 时间花在了哪个函数上"**，不需要任何代码修改。但它不能区分"物理"和"渲染"——它只能告诉你时间花在 `SomeTemplateFunction<float>::Compute()` 里，而你需要在脑海中映射回业务含义。

---
## 3. 练习

### 练习 1: Tracy 基础集成 (基础)

**目标**：将 Tracy 集成到一个简单的 C++ 程序中，并在 Tracy Server 中看到时间线。

**步骤**：
1. 创建一个最简单的 C++ 程序（只有一个 `main()` 和一个耗时循环）
2. 克隆 Tracy 到本地，按示例 1 的 CMakeLists.txt 配置
3. 在 `main()` 中插入 `FrameMark` 和一个 `ZoneScoped`
4. 运行程序
5. 启动 `Tracy.exe`（在 `tracy/profiler/build/win32/` 下）
6. 观察 Server 中出现的连接和时间线

**验收标准**：在 Tracy Server 的 Timeline 面板中能看到你的 Zone，且名称与你在代码中设置的一致。

### 练习 2: 多线程场景分析 (进阶)

**目标**：在一个多线程程序中使用 Tracy 分析线程调度效率。

**步骤**：
1. 创建一个 Job System：4 个 Worker Thread + 1 个 Main Thread
2. 创建 100 个模拟 Job（每个 Job 做不同时长的计算：`std::this_thread::sleep_for(random_ms)`)
3. 在 Main Thread 中分发 Job，等待所有 Job 完成
4. 在 Tracy Server 中：
   - 查看所有 5 个线程的时间线
   - 找出哪个 Worker 的负载最大（最后完成的）
   - 计算 **负载不均衡度** = (最忙 Worker 时间 - 最闲 Worker 时间) / 平均时间
5. 修改 Job 分配策略（按预估耗时排序分配），重新观察不均衡度

**验收标准**：能用 Tracy 的 Zone Statistics 面板精确说出每个线程的总工作时间，并计算不均衡度。

### 练习 3: GPU Zone 集成（可选，挑战）

**目标**：在 Vulkan 或 D3D12 应用中集成 Tracy GPU Zone。

**步骤**：
1. 使用 `TracyVkContext` 或 `TracyD3D12Context` 初始化 GPU 上下文
2. 在渲染帧中为至少 3 个 Render Pass 添加 `TracyVkZone` / `TracyD3D12Zone`
3. 在 Tracy Server 中确认 GPU 时间线出现，且各 Pass 的起止时间合理
4. 对比 CPU 提交时间和 GPU 执行时间的差异（CPU→GPU 延迟）

**验收标准**：Tracy Server 中可见 GPU 时间线，且 CPU 和 GPU Zone 有正确的先后关系（CPU Submit 后 GPU 才执行）。

---
## 4. 扩展阅读

- [Tracy 官方手册 (PDF)](https://github.com/wolfpld/tracy/releases) — 每个 Tracy 版本的 Release 中都包含一份 PDF 手册，详尽介绍了每个宏、每个面板
- [Tracy 源码 (GitHub)](https://github.com/wolfpld/tracy) — 源码即文档。`public/Tracy.hpp` 文件包含了所有可用宏的说明
- [Superluminal 官方文档](https://docs.superluminal.eu/) — API 手册和最佳实践
- [Apple Instruments Help](https://help.apple.com/instruments/) — macOS/iOS 下的首选 Profiling 工具，支持 Metal GPU 和 CPU 联合分析
- [perf 与 FlameGraph (Linux)](https://www.brendangregg.com/flamegraphs.html) — Linux 服务端构建的性能分析黄金组合
- [Optick — 轻量级 Profiler](https://github.com/bombomby/optick) — 另一个开源 CPU/GPU Profiler，UE4 的 Profiler 前身
- [GDC 2019: Practical Approaches to CPU Performance](https://www.gdcvault.com/play/1025967/) — Bungie 工程师分享的 CPU 优化实战经验

---
## 常见陷阱

1. **过度插桩导致性能扭曲**。每个 `ZoneScoped` 有约 10-30ns 的开销。如果你在一个每帧调用 10,000 次的内层循环中插入 `ZoneScoped`，开销会大到扭曲测量结果。**原则**：只标记有意义的作用域（函数级别或子系统级别），避免在 inner loop 中插桩。如果必须测 inner loop，用 `TracyPlot` 记录迭代次数而非进入/退出时间。

2. **忘记 FrameMark**。没有 `FrameMark`，Tracy Server 无法将数据按帧切分，所有 Zone 会连成一条无限的时间线。你无法使用 "Compare Frames" 或 "Frame Statistics" 面板。最简单的修复：在主循环开始的第一个语句放 `FrameMark`。

3. **Tracy Server 连接不上**。常见原因：
   - 防火墙阻止了 8086 端口
   - 程序和 Server 不在同一网络（远程 Profiling 需要指定 IP）
   - 程序在 Tracy Server 启动**之前**就完成了（如果程序很快退出，Server 可能来不及连接）
   - 解决：在 `main()` 开头加 `while (!tracy::GetProfiler().IsConnected()) { std::this_thread::sleep_for(std::chrono::milliseconds(100)); }` 等待连接

4. **GPU Zone 时间不准**。GPU Zone 的精度依赖于 GPU 硬件时间戳。某些移动 GPU 和低端集成 GPU 的时间戳粒度极粗（~μs 级甚至不可用）。测试前应确认你的设备支持。Tracy 在初始化时会查询时间戳频率并在日志中输出。

5. **Superluminal 看不到函数名**。Superluminal 需要 PDB（Program Database）符号文件来将地址映射为函数名。确保：
   - 以 Release 模式编译（Debug 模式的性能数据无意义）
   - 但开启了 PDB 生成：MSVC 中 `/Zi` 或 `/ZI`，链接器 `/DEBUG:FULL`
   - Superluminal 设置中指定了正确的符号路径

6. **只用平均值看性能**。Tracy 的 Zone Statistics 默认显示平均值，但游戏中最致命的是**尖峰**（Max 值）。把统计面板切换到显示 Max 或选择 Histogram 模式来发现间歇性卡顿的来源。

7. **在 Release 构建中忘记条件编译 Tracy**。即使 `TRACY_ON_DEMAND` 能让未连接时零开销，Tracy 的 Zone Scoped 对象仍然会构造/析构（只是不做实际工作）。最稳妥的方式：在最终发布构建中完全禁用 Tracy 相关代码，使用构建配置宏（如 `#if !defined(SHIPPING)`）。注意：`TRACY_ENABLE` 是编译宏，如果你没有定义它，`Tracy.hpp` 中的宏都会变成空操作，所以最简单的做法是在 Shipping 构建中不定义 `TRACY_ENABLE`。
