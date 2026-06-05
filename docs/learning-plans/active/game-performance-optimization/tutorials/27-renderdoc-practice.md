---
title: "GPU Capture 实战 — RenderDoc 全流程"
updated: 2026-06-05
---

# GPU Capture 实战 — RenderDoc 全流程
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60 分钟
> 前置知识: 帧分析基础（第 4 节）、GPU 架构简析（第 23 节）、了解至少一种图形 API（Vulkan/DX12/OpenGL/DX11）
---
## 1. 概念讲解

### 为什么需要这个？

写完 Shader、调好管线、跑通场景之后，你怎么**真正知道** GPU 上发生了什么？引擎编辑器里的 FPS 计数器只能告诉你"慢了"，但慢在哪里——是某个 Draw Call 绑了 4K 纹理？是某组粒子把填充率打爆？是一个 Uniform Buffer 每帧都在 CPU→GPU 之间复制？

RenderDoc 是一个**帧级 GPU 调试器**：它能截获一帧内所有图形 API 调用（Draw Call、Dispatch、Copy、Barrier），并允许你离线逐条检查。你可以：
- 查看任意 Draw Call 的输入/输出纹理、Buffer 内容
- 追踪单个像素的完整绘制历史（Pixel History）
- 查看 Mesh 的顶点数据、索引缓冲
- 在线修改 Shader 并热重载当前帧（Shader Edit & Continue）
- 导出帧捕获文件与他人协作排查

几乎所有现代图形 API（Vulkan, D3D12, D3D11, OpenGL, OpenGL ES）都支持。免费、开源、跨平台。

### 核心思想

RenderDoc 的工作原理是**API 拦截**：

1. **注入阶段**：RenderDoc 以动态库（`renderdoc.dll`/`librenderdoc.so`）形式注入目标进程。注入时机可以是启动时（环境变量）、运行时（`renderdoccmd inject`），或通过应用内 API（`renderdoc.h`）。
2. **捕获阶段**：按下捕获快捷键（默认 F12）后，RenderDoc 开始记录之后一帧内所有的图形 API 调用，包括所有参数、资源内容。
3. **回放阶段**：捕获完成后，在 RenderDoc 的 GUI 中可以**逐 Draw Call 重放**，查看任意时刻的管线状态、资源内容。

关键理解：**RenderDoc 不是 Profiler，它是 Debugger**。它给你的是"这一帧到底发生了什么"的完整记录，而不是运行时采样统计。两者互补：
- RenderDoc → 为什么这一帧有闪烁/黑块/错误的形状？为什么这个 Draw Call 开销大？
- GPU Profiler（RGP、NSight、PIX）→ 哪个阶段的 GPU 时间占比最高？是否有管线气泡？

### RenderDoc 的界面结构

打开一个 `.rdc` 捕获文件后，主窗口分为以下几个核心面板：

| 面板 | 功能 |
|------|------|
| **Event Browser** | 列出所有 Draw Call、Dispatch、Clear、Copy、Barrier，按时间排序 |
| **Texture Viewer** | 显示任意 Event 的输入/输出纹理，支持通道分离、Mip 级别切换、像素值拾取 |
| **Mesh Viewer** | 以 3D 方式查看某次 Draw Call 的顶点数据，包含 VS 输入和 VS 输出 |
| **Pipeline State** | 选中 Event 时的完整管线配置：所有 Shader Stage、绑定的资源、Blend/Depth/Stencil 状态 |
| **Pixel History** | 选择一个像素→查看该像素在本帧所有被写入/测试的事件序列 |
| **Shader Debugger** | 步进调试 Shader 代码，查看寄存器值 |
| **Resource Inspector** | 列出本帧所有创建/使用的资源，可检查格式、尺寸、生命周期 |
| **Performance Counter Viewer** | 硬件性能计数器（需 GPU 驱动支持） |

---
## 2. 代码示例

### 示例 0: 下载与安装 RenderDoc

```bash
# Windows: 下载安装包
# https://renderdoc.org/  → 下载最新稳定版 (v1.x)
# 安装时勾选 "Add to PATH"

# Linux (Ubuntu/Debian):
sudo apt install renderdoc

# macOS (通过 Homebrew):
brew install renderdoc
```

### 示例 1: 集成 RenderDoc 到你的引擎 — 应用内捕获 API

以下代码展示如何通过 `renderdoc.h` 在你的 C++ 引擎中实现程序化捕获——无需手动按 F12，可由代码逻辑触发（例如：在帧时间超过阈值后自动捕获）。

```cpp
// renderdoc_capture.h
// 独立头文件，无需链接 RenderDoc 库即可在运行时动态加载
#pragma once

#include <cstdint>
#include <string>

// RenderDoc API version 1.6.0 核心类型
// 完整定义见 renderdoc.h (RenderDoc 安装目录/include/)

#define RENDERDOC_CC __cdecl

// 从 renderdoc.h 中摘录的必要类型
enum RENDERDOC_CaptureOption {
    eRENDERDOC_Option_AllowVSync        = 0,
    eRENDERDOC_Option_AllowFullscreen   = 1,
    eRENDERDOC_Option_APIValidation     = 2,
    eRENDERDOC_Option_CaptureCallstacks = 3,
    eRENDERDOC_Option_CaptureCallstacksOnlyDraws = 4,
    eRENDERDOC_Option_DelayForDebugger  = 5,
    eRENDERDOC_Option_VerifyMapWrites   = 6,
    eRENDERDOC_Option_HookIntoChildren  = 7,
    eRENDERDOC_Option_RefAllResources   = 8,
    eRENDERDOC_Option_SaveAllInitials   = 9,
    eRENDERDOC_Option_CaptureAllCmdLists = 10,
    eRENDERDOC_Option_DebugOutputMute   = 11,
    eRENDERDOC_Option_AllowUnsupportedVendors = 12,
};

// RenderDoc 的核心 API 接口（RENDERDOC_API_1_6_0）
typedef void (RENDERDOC_CC *pRENDERDOC_GetAPIVersion)(int *major, int *minor, int *patch);
typedef int  (RENDERDOC_CC *pRENDERDOC_SetCaptureOptionU32)(RENDERDOC_CaptureOption opt, uint32_t val);
typedef int  (RENDERDOC_CC *pRENDERDOC_SetCaptureOptionF32)(RENDERDOC_CaptureOption opt, float val);
typedef uint32_t (RENDERDOC_CC *pRENDERDOC_GetOverlayBits)();
typedef void (RENDERDOC_CC *pRENDERDOC_MaskOverlayBits)(uint32_t And, uint32_t Or);
typedef void (RENDERDOC_CC *pRENDERDOC_RemoveHooks)();
typedef void (RENDERDOC_CC *pRENDERDOC_UnloadCrashHandler)();
typedef void (RENDERDOC_CC *pRENDERDOC_SetCaptureFilePathTemplate)(const char *path_template);
typedef const char * (RENDERDOC_CC *pRENDERDOC_GetCaptureFilePathTemplate)();
typedef uint32_t (RENDERDOC_CC *pRENDERDOC_GetNumCaptures)();
typedef uint32_t (RENDERDOC_CC *pRENDERDOC_GetCapture)(uint32_t idx, char *filename, uint32_t *pathlength, uint64_t *timestamp);
typedef void (RENDERDOC_CC *pRENDERDOC_SetCaptureFileComments)(const char *file_path, const char *comments);

// 核心捕获控制
typedef void (RENDERDOC_CC *pRENDERDOC_TriggerCapture)();
typedef void (RENDERDOC_CC *pRENDERDOC_TriggerMultiFrameCapture)(uint32_t numFrames);
typedef uint32_t (RENDERDOC_CC *pRENDERDOC_IsTargetControlConnected)();
typedef uint32_t (RENDERDOC_CC *pRENDERDOC_LaunchReplayUI)(uint32_t connectTargetControl, const char *cmdline);
typedef void (RENDERDOC_CC *pRENDERDOC_SetActiveWindow)(void *device, void *wndHandle);

// 设置/取消焦点切换键
typedef void (RENDERDOC_CC *pRENDERDOC_SetFocusToggleKeys)(int *keys, int num);
typedef void (RENDERDOC_CC *pRENDERDOC_SetCaptureKeys)(int *keys, int num);

// 完整接口结构
typedef struct RENDERDOC_API_1_6_0 {
    pRENDERDOC_GetAPIVersion              GetAPIVersion;
    pRENDERDOC_SetCaptureOptionU32        SetCaptureOptionU32;
    pRENDERDOC_SetCaptureOptionF32        SetCaptureOptionF32;
    pRENDERDOC_GetOverlayBits             GetOverlayBits;
    pRENDERDOC_MaskOverlayBits            MaskOverlayBits;
    pRENDERDOC_RemoveHooks                RemoveHooks;
    pRENDERDOC_UnloadCrashHandler         UnloadCrashHandler;
    pRENDERDOC_SetCaptureFilePathTemplate SetCaptureFilePathTemplate;
    pRENDERDOC_GetCaptureFilePathTemplate GetCaptureFilePathTemplate;
    pRENDERDOC_GetNumCaptures             GetNumCaptures;
    pRENDERDOC_GetCapture                 GetCapture;
    pRENDERDOC_SetCaptureFileComments     SetCaptureFileComments;
    pRENDERDOC_TriggerCapture             TriggerCapture;
    pRENDERDOC_TriggerMultiFrameCapture   TriggerMultiFrameCapture;
    pRENDERDOC_IsTargetControlConnected   IsTargetControlConnected;
    pRENDERDOC_LaunchReplayUI             LaunchReplayUI;
    pRENDERDOC_SetActiveWindow            SetActiveWindow;
    pRENDERDOC_SetFocusToggleKeys         SetFocusToggleKeys;
    pRENDERDOC_SetCaptureKeys             SetCaptureKeys;
} RENDERDOC_API_1_6_0;

// 导出符号名称
#define RENDERDOC_GetAPI_FuncName "RENDERDOC_GetAPI"

// 从 renderdoc.dll 导出的 C 函数
typedef int (RENDERDOC_CC *pRENDERDOC_GetAPI)(int version, void **outAPIPointers);
```

```cpp
// renderdoc_capture.cpp
// RenderDoc 运行时集成 — 在生产构建中通过 #ifdef 禁用即可
#include "renderdoc_capture.h"

#ifdef _WIN32
    #define WIN32_LEAN_AND_MEAN
    #include <windows.h>
#else
    #include <dlfcn.h>
#endif

#include <cstdio>
#include <cstdlib>

static RENDERDOC_API_1_6_0 g_rdoc    = {};
static bool                g_rdoc_ok = false;

// ---------------------------------------------------------------
// 初始化：从已注入的 RenderDoc 获取 API 指针
// 必须在图形 API 初始化之前调用
// ---------------------------------------------------------------
bool RenderDoc_Init() {
    if (g_rdoc_ok) return true;

#ifdef _WIN32
    HMODULE mod = GetModuleHandleA("renderdoc.dll");
    if (!mod) {
        // RenderDoc 未注入，尝试手动加载（仅在开发模式下有意义）
        mod = LoadLibraryA("renderdoc.dll");
        if (!mod) return false;
    }
    pRENDERDOC_GetAPI RENDERDOC_GetAPI =
        (pRENDERDOC_GetAPI)GetProcAddress(mod, RENDERDOC_GetAPI_FuncName);
#else
    void *mod = dlopen("librenderdoc.so", RTLD_NOW | RTLD_NOLOAD);
    if (!mod) return false;
    pRENDERDOC_GetAPI RENDERDOC_GetAPI =
        (pRENDERDOC_GetAPI)dlsym(mod, RENDERDOC_GetAPI_FuncName);
#endif

    if (!RENDERDOC_GetAPI) return false;

    int ret = RENDERDOC_GetAPI(eRENDERDOC_API_Version_1_6_0, (void **)&g_rdoc);
    if (ret != 1) return false;

    g_rdoc_ok = true;

    // 配置：允许从全屏窗口捕获
    g_rdoc.SetCaptureOptionU32(eRENDERDOC_Option_AllowFullscreen, 1);
    // 开启 VSync 捕获（通常建议关闭 VSync 来捕获，但这里保持兼容）
    g_rdoc.SetCaptureOptionU32(eRENDERDOC_Option_AllowVSync, 1);
    // 捕获调用栈信息（对调试有帮助，稍微增加捕获文件大小）
    g_rdoc.SetCaptureOptionU32(eRENDERDOC_Option_CaptureCallstacks, 1);
    // 只对 Draw/Dispatch 记录调用栈（减少开销）
    g_rdoc.SetCaptureOptionU32(eRENDERDOC_Option_CaptureCallstacksOnlyDraws, 1);

    printf("[RenderDoc] API initialized successfully.\n");
    return true;
}

// ---------------------------------------------------------------
// 触发单帧捕获
// ---------------------------------------------------------------
void RenderDoc_TriggerCapture() {
    if (!g_rdoc_ok) {
        printf("[RenderDoc] Not available — is renderdoc.dll injected?\n");
        return;
    }
    g_rdoc.TriggerCapture();
    printf("[RenderDoc] Frame capture triggered.\n");
}

// ---------------------------------------------------------------
// 触发多帧捕获（例如：捕获 5 帧用于比较）
// ---------------------------------------------------------------
void RenderDoc_TriggerMultiFrameCapture(uint32_t numFrames) {
    if (!g_rdoc_ok) return;
    g_rdoc.TriggerMultiFrameCapture(numFrames);
    printf("[RenderDoc] Multi-frame capture (%u frames) triggered.\n", numFrames);
}

// ---------------------------------------------------------------
// 检查 RenderDoc 是否连接（GUI 是否在监听）
// ---------------------------------------------------------------
bool RenderDoc_IsConnected() {
    if (!g_rdoc_ok) return false;
    return g_rdoc.IsTargetControlConnected() != 0;
}

// ---------------------------------------------------------------
// 设置捕获文件保存路径
// ---------------------------------------------------------------
void RenderDoc_SetCapturePath(const char *path_template) {
    if (!g_rdoc_ok) return;
    g_rdoc.SetCaptureFilePathTemplate(path_template);
}
```

```cpp
// main_example.cpp — 使用示例：在你的游戏主循环中集成
#include "renderdoc_capture.h"

// 在主循环中使用
void GameLoop() {
    // ... 初始化图形 API 后 ...
    RenderDoc_Init();

    // 可选：设置自定义保存路径
    RenderDoc_SetCapturePath("captures/my_game_frame_");

    float worst_frame_time_ms = 0.0f;
    float auto_capture_threshold_ms = 33.33f; // 低于 30fps 时自动捕获

    while (running) {
        float dt_ms = UpdateGame();

        // 策略 1: 手动按键触发（通常映射到一个开发功能键）
        if (Input_IsKeyJustPressed(KEY_F12)) {
            RenderDoc_TriggerCapture();
        }

        // 策略 2: 自动捕获 — 当帧时间超过阈值时触发
        // 这在你想要捕获"卡顿"帧时非常有用
        if (dt_ms > auto_capture_threshold_ms && dt_ms > worst_frame_time_ms) {
            worst_frame_time_ms = dt_ms;
            RenderDoc_TriggerCapture();
            printf("Auto-captured slow frame: %.2f ms\n", dt_ms);
        }

        RenderFrame();
    }
}
```

### 示例 2: 使用 `renderdoccmd` 命令行捕获

除了应用内 API，你还可以通过命令行启动并捕获：

```bash
# 启动你的应用并注入 RenderDoc
renderdoccmd capture -w my_game.exe --wait-for-exit

# 注入到已经运行的进程
renderdoccmd inject -p <PID>                # 注入并等待手动捕获
renderdoccmd inject -p <PID> -c capture.rdc # 注入并立即捕获一帧

# 批量捕获（自动化测试场景）
renderdoccmd capture -w my_game.exe -c output.rdc --delay 5
# ↑ 启动程序，等待 5 秒后自动捕获一帧，然后退出
```

### 示例 3: 分析一次真实帧捕获 — 找出 Top 5 最贵的 Draw Call

以下是一份典型分析步骤，配合一个假设的 3D 场景捕获。**你需要一个实际的 `.rdc` 文件来跟着操作**——可以用 RenderDoc 捕获任何游戏或引擎 Demo。

**步骤 1: 加载捕获，概览 Event Browser**

打开 RenderDoc → File → Open Capture → 选择 `.rdc` 文件。Event Browser 会显示类似这样的列表（假设一个 3D 场景）：

```
EID    Event Name                             Action
----   -----------------------------------    ------
1      vkBeginCommandBuffer
2-8    各种 Copy/Buffer Update
...
42     vkCmdBeginRenderPass (GBuffer)
43     vkCmdBindPipeline (gbuffer_pso)
44     vkCmdBindDescriptorSets
45     vkCmdDrawIndexed (4632 indices)        ← Draw Call
46     vkCmdDrawIndexed (12048 indices)
...
```

**步骤 2: 使用 Performance Counter Viewer**（如果硬件支持）

在 RenderDoc 中点击 `Tools → Performance Counter Viewer`，或在 Event Browser 右侧查看"Timer"列（如果捕获时开启了 Timing 选项）。通常你会看到类似：

| Draw Call | Vertices | Triangles | GPU Time (μs) | 说明 |
|-----------|----------|-----------|---------------|------|
| `#73`: Shadow Depth Pass | 284,312 | 94,771 | 1,240 | 阴影贴图，顶点数高 |
| `#142`: GBuffer Opaque | 850,234 | 283,411 | 2,850 | 主场景不透明物体，几何体密集 |
| `#189`: Particle Render | 24 | 8 (billboards) | 3,120 | **异常！** 只有 8 个三角形却耗时 3ms |
| `#201`: PostProcess Bloom | 6 (fullscreen tri) | 2 | 1,850 | 全屏 Bloom，带宽敏感 |
| `#210`: Skybox | 36 | 12 | 180 | 天空盒，开销极低 |

**步骤 3: 逐 Draw Call 深入分析**

下面是对上述 Top 5 的详细诊断：

#### Top 1: `#189` Particle Render（粒子渲染）— 3.12ms

**为什么贵？** 8 个三角形不可能花 3ms。选择该 Event，打开 **Pipeline State** 面板：

- **Fragment Shader** 中发现：Shader 内有一个 `while` 循环做光线步进（Ray Marching），每个粒子遍历 128 步
- **Texture Viewer** 显示 Output 是一张 1920×1080 的纹理——每个粒子都是全屏 Quad 做软粒子效果
- **根本原因**: 全屏 Shader × 128 步 × 8 个粒子 = 大量 ALU + 纹理采样

**解决方案**：
- 将 Ray Marching 降到 32 步，视觉效果差异可接受
- 使用 `discard` 提前退出非粒子覆盖区域的像素
- 减小粒子渲染目标分辨率（Half-Res particles）

#### Top 2: `#142` GBuffer Opaque — 2.85ms

**为什么贵？** 85 万顶点，28 万三角形，合理范围内。但进一步检查：

- 在 **Texture Viewer** 中查看 Albedo 纹理：都是 2048×2048 RGBA8，共 ~200 个不同材质
- 在 **Pipeline State** 中查看绑定的资源：**每个 Draw Call 绑定不同的纹理集**——这意味着频繁的 Descriptor Set 切换、材质排序被打断
- 使用 `Tools → Resource Inspector` 统计：本帧引用了 214 个独特纹理

**解决方案**：
- 使用 Texture Atlas 合并小纹理
- 材质合并，减少 Unique Material 数量
- 按材质排序渲染（Sort by Material Key）

#### Top 3: `#201` PostProcess Bloom — 1.85ms

**为什么贵？** 选择该 Event，在 **Texture Viewer** 中查看输入/输出。

- 输入纹理是 HDR 格式（RGBA16F），Output 也是
- Bloom 包含 12 次高斯模糊 Pass（6×Downsample + 6×Upsample）
- 在 **Pipeline State** 中查看 Shader：每次 Blur 遍历 15×15 卷积核 = 225 次纹理采样/Pixel

**解决方案**：
- 使用双线性采样 + 更小的 Kernel（Kawase Blur 或 Dual Filtering）
- 减少 Bloom Mip 层级数：6 级降为 4 级
- 在较低分辨率下做模糊然后上采样

#### Top 4: `#73` Shadow Depth Pass — 1.24ms

**为什么贵？** 在 **Texture Viewer** 中查看 Shadow Map 输出：

- Shadow Map 分辨率 4096×4096，但场景中的阴影投射物只需要 2048×2048
- 在 Event Browser 中观察到：Shadow Pass 包含 120+ 个 Draw Call（每个投影物一个）

**解决方案**：
- 降低 Shadow Map 分辨率到 2048（移动平台甚至 1024）
- 对静态场景物体使用 Shadow Cache（只在光源移动时重新渲染）
- 合并静态物体的 Shadow Casting 到单个 Mesh

#### Top 5: `#210` Skybox — 0.18ms

**没问题**。但可以用 **Pixel History** 验证一个常见问题——天空盒是否在被其他物体覆盖的像素上还在绘制：

1. 选中 `#210` Skybox Draw Call
2. 点击工具栏的 **Pixel History** 按钮（或按 `H`）
3. 点击场景中间位置（一个被建筑物完全覆盖的像素）
4. Pixel History 显示该像素的完整历史：

```
#45  GBuffer Building:    Passed Depth,  Write Color=...
#82  GBuffer Ground:      Failed Depth    ← 深度测试失败，未写入
#142 GBuffer Character:   Failed Depth
#210 Skybox:              Passed Depth,  Write Color=...  ← 被前面覆盖了！
```

这说明天空盒在所有不透明物体**之后**绘制，但没有使用 Early-Z 优化——被覆盖的像素仍然执行了完整的 Fragment Shader。

**解决方案**：调整渲染顺序，先渲染天空盒，或确保 Depth Pass 先写入全深度。

### 示例 4: Shader Edit & Continue

RenderDoc 最强大的功能之一——在线修改 Shader 并立即查看效果。

1. 选择你关心的 Draw Call
2. 右键 → **Edit Shader**（或选中后按 `Ctrl+E`）
3. 选择一个 Shader Stage（如 Pixel Shader）
4. 修改代码，例如：

```hlsl
// 原始代码
float3 color = texture(albedoTex, uv).rgb;
return float4(color * lightFactor, 1.0);

// 修改为：验证是否是纹理分辨率问题
float3 color = float3(1.0, 0.0, 0.0); // 纯红色
return float4(color, 1.0);
```

5. 点击 **Apply** — RenderDoc 会重新编译该 Shader，并用新版本重放当前 Draw Call
6. Texture Viewer 会立即更新为红色——证明该 Shader 确实被该 Draw Call 使用了

这在排查"某个效果到底是哪个 Shader 产生的"时极其有用——直接改成醒目的颜色，一目了然。

### 示例 5: Mesh Viewer 使用

Mesh Viewer 可以帮助诊断顶点数据问题：

1. 选择一个 Draw Call
2. 点击 **Mesh Viewer** 面板
3. 选择查看模式：
   - **VS Input**: 显示顶点缓冲区的原始数据（Position, Normal, UV 等）
   - **VS Output**: 显示 Vertex Shader 变换后的裁剪空间顶点
4. 可以逐顶点查看属性值——例如检查 Normal 是否被错误地归一化，或 UV 是否超出 [0,1] 范围

常见的 Mesh Viewer 使用场景：
- 模型看起来"炸开"了——检查 VS Output，确认骨骼蒙皮变换是否正确
- 纹理看起来拉伸——在 VS Input 中检查 UV 值
- 某个物体不渲染——在 VS Output 中确认是否在视锥体外（被裁剪了）

---
## 3. 练习

### 练习 1: 第一次帧捕获 (基础)

**目标**：用 RenderDoc 捕获任意 3D 应用的至少一帧，并浏览 Event Browser。

**步骤**：
1. 启动 RenderDoc GUI
2. 在 "Launch Application" 标签页中：
   - Executable Path: 指向一个 3D 应用（如果没有，使用 RenderDoc 自带的 `Sample.exe`）
   - 勾选 "Capture Child Processes"
3. 点击 "Launch"
4. 程序启动后，按 **F12**（默认捕获键）或 **Print Screen**
5. 在 Event Browser 中观察捕获的 Event 列表
6. 双击任意 `vkCmdDrawIndexed` / `glDrawElements` Event，查看 Texture Viewer 的渲染结果

**验收标准**：能看到 Texture Viewer 中显示该 Draw Call 的输出画面。

### 练习 2: 定位并分析最慢的 3 个 Draw Call (进阶)

**目标**：使用 RenderDoc 的 Timing 数据（或手动观察）找到最慢的 Draw Call，并用 Texture Viewer/Pipeline State 分析原因。

**步骤**：
1. 在捕获时确保开启了 Timing 功能：
   - 在 Launch 设置中：`Capture Options → Collect GPU Timers` 勾选
2. 捕获一帧，打开 Performance Counter Viewer（`Tools → Performance Counter Viewer`）
3. 按 "Duration" 降序排列，选择前 3 个 Draw Call
4. 对每个 Draw Call，回答：
   - 它渲染了什么？（Texture Viewer 查看）
   - 用了什么 Shader？（Pipeline State → Shader Stages）
   - 绑定了哪些纹理？分辨率多大？（Pipeline State → Bound Resources）
   - 你认为它的开销主要原因是什么？

**验收标准**：能对每个 Top Draw Call 写出 ≥1 条优化建议。

### 练习 3: Pixel History 调试 Overdraw (挑战)

**目标**：使用 Pixel History 分析一个像素在整个帧中被重复绘制了多少次，并计算 Overdraw 因子。

**步骤**：
1. 在捕获的帧中，找到一个粒子效果密集或 UI 层叠较多的场景
2. 使用 Pixel History 工具（快捷键 `H`）
3. 在 Texture Viewer 中点击几个不同位置的像素
4. 记录每个像素被写入（Passed Depth/Stencil + Wrote Color）的次数
5. 计算 **Overdraw 因子** = 实际写入次数 / 理想写入次数（1）
6. 分析哪些写入是"浪费的"（被后续 Draw Call 完全覆盖的）
7. 尝试修改渲染顺序（如果引擎支持），观察 Overdraw 因子的变化

**验收标准**：提供一个像素的完整 Pixel History 截图（或文字记录），包含 ≥5 次写入事件，并能说出每个事件对应场景中的哪个物体。

---
## 4. 扩展阅读

- [RenderDoc 官方文档](https://renderdoc.org/docs/) — 完整的工具使用手册，包含每个面板和快捷键的详细说明
- [RenderDoc 源码 (GitHub)](https://github.com/baldurk/renderdoc) — 理解其内部实现，尤其有助于自定义集成
- [RenderDoc Step-by-Step Vulkan Tutorial (vulkan-tutorial.com)](https://vulkan-tutorial.com/Development_environment#page_RenderDoc) — Vulkan 初学者的 RenderDoc 上手教程
- [GPUOpen — RenderDoc Python API](https://renderdoc.org/docs/python_api/index.html) — 用 Python 脚本批量分析 `.rdc` 文件（自动化测试利器）
- [AMD Radeon GPU Profiler (RGP)](https://gpuopen.com/rgp/) — 与 RenderDoc 互补：专注 GPU 硬件性能计数器，展示各 Pipeline Stage 的时间分布
- [NVIDIA NSight Graphics](https://developer.nvidia.com/nsight-graphics) — NVIDIA 的 GPU 调试器，功能类似但增加 RTX/Ray Tracing 调试支持

---
## 常见陷阱

1. **忘记在捕获前关闭 VSync**。VSync 会导致帧时间被限制，隐藏真实瓶颈。在 RenderDoc 的 Capture Options 中勾选 "Allow VSync" 只是让捕获不失败，但帧数据仍然受 VSync 影响。**建议**：实际分析时在应用内关闭 VSync。

2. **性能计数器不显示数据**。大多数集成 GPU 和部分移动 GPU 不支持硬件性能计数器。你需要在 RenderDoc 设置中查看 "GPU Timer" 是否可用。如果不可用，使用 NSight Graphics（NVIDIA）或 RGP（AMD）获取详细的 GPU 时间数据。

3. **Pixel History 里看不到完整历史**。Pixel History 只能追踪通过传统 Depth/Stencil/Blend 测试的绘制。如果你的 Draw Call 使用了 `discard`、在 Fragment Shader 中手动写 `gl_FragDepth`，或使用了某些高级混合模式，Pixel History 可能不完整。遇到这种情况，用 Shader Debugger 步进调试。

4. **Texture Viewer 显示 "No resource bound"**。说明你选的 Event 没有渲染到当前显示的 Render Target。切换到其他绑定的纹理（Texture Viewer 右上角的下拉列表）。通常 GBuffer Pass 的 Albedo 纹理和最终 Backbuffer 是不同的 Render Target。

5. **捕获文件太大（>1GB）**。在 Capture Options 中：
   - 关闭 "Save All Initials"（初始资源状态只对调试资源创建问题有用）
   - 关闭 "Ref All Resources"（只保存实际被引用的资源）
   - 大纹理和高多边形 Mesh 是存储大户——考虑在测试场景中使用低质量资产来缩小捕获文件

6. **Shader Edit & Continue 编译失败**。RenderDoc 内置的编译器版本可能与你的原始 Shader 编译器不完全一致。复杂的 `#include`、预处理器宏、计算出的常量可能导致重新编译失败。解决方法：在原始工程中修改 Shader、重新构建、重新捕获。

7. **程序化捕获不生效**。确认：
   - `renderdoc.dll` 确实已注入（检查 `GetModuleHandleA("renderdoc.dll")` 返回值）
   - 你在图形 API 初始化**之前**调用了 `RenderDoc_Init()`
   - RenderDoc GUI 正在运行（`IsTargetControlConnected()` 检查）
   - 如果通过 `LOAD_LIBRARY` 手动加载，确认 DLL 在搜索路径中
