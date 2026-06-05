---
title: "Overdraw 与填充率优化"
updated: 2026-06-05
---

# Overdraw 与填充率优化
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50min
> 前置知识: 05-Draw Call 优化 (了解渲染顺序和透明物体混合)

---

## 1. 概念讲解

### 为什么需要这个？

Overdraw 是游戏性能中最隐蔽的杀手之一。不像 Draw Call 有明确的数字（"这帧有 2000 个 Draw Call"）、不像三角形数可以看到（"这个模型 50 万面"），Overdraw 是看不见的浪费：**同一个像素被 Shader 执行了多次，但用户只看到最后一次结果**。

典型数据：
- 一个 FPS 游戏的场景平均 Overdraw 可能在 1.5x–3.0x（即每个像素平均被绘制 1.5–3 次）
- 粒子特效密集区域 Overdraw 可以到 10x–20x
- 透明 UI 层叠区域可以达到惊人的 50x+
- **在移动端**，Overdraw 是帧率的头号敌人。ARM 的 Mali GPU 白皮书指出，降低 Overdraw 是提升移动端游戏帧率最有效的单一手段

填充率瓶颈的典型症状：降低分辨率帧率大幅提升，但降低几何复杂度帧率不变。这说明 GPU 的瓶颈不在顶点处理或三角形光栅化，而在像素着色器执行次数。

### 核心思想

#### 1. Overdraw 的成因

**Overdraw = 同一个像素被多次绘制。** 具体场景：

| 成因 | Overdraw 倍数 | 场景 |
|------|---------------|------|
| 不透明物体从后往前绘制 | 2-4x | 不透明物体没有按 depth 排序或被 Early-Z 剔除 |
| 透明物体层叠 | 5-50x | 粒子叠加、半透明 UI、玻璃 |
| 复杂几何体的深度复杂度 | 2-8x | 植被（树叶交错）、建筑内部 |
| 后处理全屏 Pass | 1x/pass | 每加一个后处理 = 全屏像素再算一次 |
| UI 面板嵌套 | 10-100x | Image → Panel → Panel → Canvas 每层都在画 |

**Tile-Based GPU（移动端）的特殊性**：
- Mali、Adreno、Apple GPU 是 Tile-Based Deferred Rendering (TBDR)
- 整个帧被分成小 Tile（如 16×16 或 32×32 像素）
- 每个 Tile 独立处理，暂时存储在片上 SRAM
- **优势**：TBDR 会做 Hidden Surface Removal (HSR)，自动剔除被遮挡的不透明像素
- **劣势**：Tile 内的透明物体无法被 HDR 优化；Tile 之间需要 flush 到主存（带宽开销）
- 这意味着移动端对透明物体的 Overdraw 比桌面端更敏感

#### 2. 可视化 Overdraw

**RenderDoc**：打开帧捕获 → Overlay → "Quad Overdraw" 视图。颜色代表：
- 深蓝/黑 → 1x（无 Overdraw）— 理想
- 绿色 → 2x–3x
- 黄色 → 4x–6x — 需要注意
- 红色 → 8x+ — 严重问题
- 白色 → 16x+ — 立即修复

**Unity**：Scene 视图 → 下拉菜单 → "Overdraw" 模式
**UE**：`viewmode quad_overdraw` 或 `r.ShaderComplexity 1`

#### 3. 解决方案

**方案 1：Z-Prepass（深度预渲染）**
```
标准流程：
1. 渲染所有不透明物体的深度（只写深度，不写颜色，用最简单的 VS/PS）
2. 渲染不透明物体的颜色（Early-Z 自动剔除被遮挡的像素）
3. 渲染透明物体（从前到后排序）
```

代价：一个额外的全场景渲染 Pass（顶点数加倍但像素 Shader 极轻）。收益：将不透明物体的 Overdraw 从 2-4x 降到接近 1.0x。

何时用 Z-Prepass：
- ✅ 场景中有大量复杂的不透明几何体重叠
- ✅ 最终的颜色 Pass 使用昂贵的 Pixel Shader
- ❌ 场景简单、Draw Call 已经是瓶颈（再加一个 Pass 加重 CPU 负担）
- ❌ 移动端 TBDR GPU（硬件已经做了 HSR，Z-Prepass 反而可能降低性能）

**方案 2：不透明物体从前到后排序**

早期 GPU 没有 Early-Z 时，从前到后排序至关重要。现代 GPU 都有 Early-Z，但排序仍然有帮助：
- 提高 Early-Z 的剔除效率（先渲染的深度值已经写入，后渲染的能被剔除）
- 提高 Depth Buffer 的压缩率

Unity 中：Opaque Queue 的 Sort Key 会考虑距离。UE 中：Base Pass 默认按距离排序（但可以通过 `r.BasePassSortOrder` 调整）。

**方案 3：减少透明区域**

```hlsl
// 半透明粒子纹理通常有大面积完全透明的区域
// 这些区域的像素仍然会执行 Pixel Shader！

// 优化：在 VS 中计算每顶点的透明度信息
// 或在 PS 最前面用 clip() 减少实际计算
float alpha = tex.Sample(sampler, uv).a;
clip(alpha - 0.01);  // 如果几乎透明，丢弃像素
// 但注意：clip/discard 会禁用 Early-Z
```

更好的做法：使用紧凑的 Mesh 形状匹配纹理的不透明区域，而不是用一个全尺寸的 Quad。

**方案 4：粒子优化**

| 技术 | 效果 |
|------|------|
| 减少粒子数 | 最直接 — 每减少 1 个 Quad = 减少该像素上的一次 PS 调用 |
| 更小的粒子 | 当前帧可见的粒子 Quad 总面积更小 |
| 软粒子用 Depth Test 替代 | 少一个深度采样和软边缘计算 |
| GPU Particles | 在 GPU 上直接生成和渲染粒子，减少 CPU→GPU 数据传输 |
| 使用非透明粒子 | 如果效果允许，opaque 粒子可以被 Early-Z 剔除 |

#### 4. 填充率瓶颈判定

**填充率 = Pixel Shader 执行次数 × 每条指令成本**

在渲染管线中，Pixel Shader 执行次数 = 屏幕分辨率 × Overdraw 倍数。

判断是否为填充率瓶颈：
1. 降低分辨率（如 1080p→540p）帧率翻倍 → **是填充率瓶颈**
2. 简化 Pixel Shader（如移除法线贴图）帧率大幅提升 → **是填充率瓶颈**
3. 降低分辨率帧率不变 → 瓶颈在其他地方（CPU、顶点处理、带宽）

#### 5. Tile-Based GPU 专属优化

TBDR GPU（所有移动 GPU + Apple Silicon）的特殊优化：
- **不要做 Z-Prepass**：TBDR 硬件自己会做 HSR，Z-Prepass 破坏了 Tile 内的处理流程
- **减少 Render Target 切换**：每次切换 RT 需要 flush Tile 到主存
- **避免在 PS 中修改深度**：`gl_FragDepth` 破坏 Early-Z 和 HSR
- **Framebuffer Fetch（Subpass Input）**：Vulkan 的 `subpassLoad()` 可以直接读取当前像素的上一次渲染结果，无需写回主存

---

## 2. 代码示例

### 示例 1：C++ OpenGL 演示 Z-Prepass 效果

```cpp
// overdraw_demo.cpp — 对比有无 Z-Prepass 的渲染效率
// 依赖: GLFW + glad + OpenGL 4.3+
// 编译: g++ -std=c++17 overdraw_demo.cpp -lglfw -ldl -o overdraw_demo

// 注：完整可运行代码需完整 OpenGL 环境。此处展示核心概念和测量逻辑。
// 核心结构可在任何渲染框架（DX12/Vulkan/Metal）中复现。

#include <iostream>
#include <vector>
#include <string>
#include <chrono>

// ====== 模拟渲染管线 ======

// 模拟 GPU Timer（实际中应使用 GL_ARB_timer_query 或 DX12 timestamp queries）
class MockGPUTimer {
public:
    void BeginQuery() {}
    void EndQuery() {}
    double GetElapsedMS() const {
        // 模拟：返回基于 Overdraw 的计算时间
        return simulatedTime_;
    }
    void SetSimulatedTime(double ms) { simulatedTime_ = ms; }
private:
    double simulatedTime_ = 0.0;
};

// 模拟一次渲染 Pass
struct RenderPass {
    std::string name;
    int drawCalls;
    float overdraw;       // 平均 Overdraw 倍数
    float psCostPerPx;    // 每个像素的 PS 成本（归一化单位）
    bool writesDepth;
    bool writesColor;
};

// 帧渲染器
class FrameRenderer {
private:
    int screenW, screenH;
    std::vector<RenderPass> passes;

public:
    FrameRenderer(int w, int h) : screenW(w), screenH(h) {}

    void AddPass(const RenderPass& pass) {
        passes.push_back(pass);
    }

    // 模拟一帧的渲染开销
    double SimulateFrame() {
        int totalPixels = screenW * screenH;
        double totalCost = 0.0;

        std::cout << "========== 帧渲染模拟 ==========\n";
        std::cout << "分辨率: " << screenW << "×" << screenH
                  << " (" << (totalPixels / 1000) << "K 像素)\n\n";

        for (auto& pass : passes) {
            // 像素着色器执行次数 = 屏幕像素 × Overdraw
            int psInvocations = (int)(totalPixels * pass.overdraw);

            // 像素着色器成本
            double psCost = psInvocations * pass.psCostPerPx;

            // Draw Call 成本（假设每个 Draw Call 100 个单位的 CPU 时间）
            double dcCost = pass.drawCalls * 100.0;

            double passCost = psCost + dcCost;
            totalCost += passCost;

            std::cout << "Pass: " << pass.name << "\n";
            std::cout << "  Draw Calls:     " << pass.drawCalls << "\n";
            std::cout << "  Overdraw:       " << pass.overdraw << "x\n";
            std::cout << "  PS 调用:        " << (psInvocations / 1000) << "K\n";
            std::cout << "  Pass 成本:      " << passCost << " 单位\n";
            std::cout << "  (PS: " << psCost << ", DC: " << dcCost << ")\n\n";
        }

        return totalCost;
    }

    void Clear() { passes.clear(); }
};

int main() {
    const int SCREEN_W = 1920;
    const int SCREEN_H = 1080;

    // ===== 场景 A：无 Z-Prepass =====
    {
        std::cout << "\n╔══════════════════════════════════╗\n";
        std::cout << "║  场景 A: 无 Z-Prepass           ║\n";
        std::cout << "║  不透明物体从后到前渲染         ║\n";
        std::cout << "╚══════════════════════════════════╝\n\n";

        FrameRenderer renderer(SCREEN_W, SCREEN_H);

        // 100 个不透明物体，深度测试开启，但从后到前渲染
        // 导致 Overdraw = 3.0x（假设平均每个像素被 3 个物体覆盖）
        renderer.AddPass({
            "Opaque Pass (无 Z-Prepass)",
            100,     // 100 draw calls
            3.0f,    // 3x overdraw — 物体从后到前，靠深度测试也无法完全避免
            1.0f,    // 完整 PBR PS 成本
            true,
            true
        });

        double costA = renderer.SimulateFrame();
        std::cout << ">>> 总帧成本: " << costA << " 单位\n";

        // 实际 FPS 估算（假设 1000000 单位 = 16.67ms = 60fps）
        double frameTimeA = costA / 1000000.0 * 16.67;
        std::cout << ">>> 预估帧时间: " << frameTimeA << " ms\n";
        std::cout << ">>> 预估 FPS: " << (1000.0 / frameTimeA) << "\n";
    }

    // ===== 场景 B：有 Z-Prepass =====
    {
        std::cout << "\n╔══════════════════════════════════╗\n";
        std::cout << "║  场景 B: 有 Z-Prepass           ║\n";
        std::cout << "║  Pass 1: 只写深度（轻量 PS）    ║\n";
        std::cout << "║  Pass 2: 颜色渲染（Early-Z）    ║\n";
        std::cout << "╚══════════════════════════════════╝\n\n";

        FrameRenderer renderer(SCREEN_W, SCREEN_H);

        // Pass 1: Z-Prepass
        renderer.AddPass({
            "Z-Prepass (仅深度)",
            100,     // 相同数量的 draw calls
            1.0f,    // Overdraw = 1.0x（每个像素只处理一次，最近的胜出）
            0.02f,   // 深度写入的 PS 成本极低（几乎为空 Shader）
            true,    // 写深度
            false    // 不写颜色
        });

        // Pass 2: 颜色渲染
        renderer.AddPass({
            "Opaque Color Pass (Early-Z 剔除)",
            100,     // 相同 draw calls
            1.05f,   // Overdraw ≈ 1.0x（Early-Z 几乎完全剔除被遮挡像素）
            1.0f,    // 完整 PBR PS
            false,   // 不写深度（已有深度缓冲）
            true
        });

        double costB = renderer.SimulateFrame();
        std::cout << ">>> 总帧成本: " << costB << " 单位\n";

        double frameTimeB = costB / 1000000.0 * 16.67;
        std::cout << ">>> 预估帧时间: " << frameTimeB << " ms\n";
        std::cout << ">>> 预估 FPS: " << (1000.0 / frameTimeB) << "\n";
    }

    // ===== 对比分析 =====
    std::cout << "\n========== 分析 ==========\n";
    std::cout << "Z-Prepass 将 Overdraw 从不透明 Pass 的 3x 降到约 1x\n";
    std::cout << "代价是增加一个轻量级的深度 Pass（PS 成本仅为颜色的 2%）\n";
    std::cout << "净收益: 取决于原始颜色 Pass 的 PS 复杂度\n";
    std::cout << "\n使用 Z-Prepass 的条件:\n";
    std::cout << "  1. 原始 PS 成本 > 深度 Pass PS 成本的 3 倍\n";
    std::cout << "  2. 场景 Overdraw > 2.0x\n";
    std::cout << "  3. 不是移动端 TBDR GPU\n";
    std::cout << "  4. Draw Call 不是主要瓶颈（Z-Prepass 会增加 Draw Call）\n";

    return 0;
}
```

### 示例 2：Overdraw 计算器

```cpp
// overdraw_calculator.cpp — 计算实际 Overdraw 和填充率
// 编译: g++ -std=c++17 overdraw_calculator.cpp -o od_calc && ./od_calc

#include <iostream>
#include <vector>
#include <iomanip>
#include <cmath>

struct OverdrawLayer {
    const char* name;      // 层级名称
    float alpha;           // 该层的平均透明度
    float coverage;        // 该层覆盖屏幕的比例（0-1）
};

struct FrameStats {
    int resolutionW;
    int resolutionH;
    std::vector<OverdrawLayer> opaqueLayers;
    std::vector<OverdrawLayer> transparentLayers;
    int postProcessPasses;
};

// 计算平均 Overdraw
// 不透明层：深度复杂度（每个像素上的三角形数量，但只有最近的那个最终可见）
// 透明层：每个像素上的透明物体数量（所有层都贡献）
float CalculateAverageOverdraw(const FrameStats& stats) {
    float od = 0.0f;

    // 不透明 Overdraw：几何复杂度
    float opaqueOD = 0.0f;
    for (auto& layer : stats.opaqueLayers) {
        opaqueOD += layer.coverage;
    }
    // 不透明物体的 Overdraw 最少为 1（背景），且 Close-to-far 排序后 Early-Z 可以大幅减少
    float effectiveOpaqueOD = 1.0f + (opaqueOD - 1.0f) * 0.3f; // 假设 Early-Z 减少 70%

    // 透明 Overdraw：每层都完全贡献
    float transparentOD = 0.0f;
    for (auto& layer : stats.transparentLayers) {
        if (layer.alpha < 0.01f) continue; // 完全透明的跳过
        transparentOD += layer.coverage;
    }

    // 后处理：每个 Pass 都是全屏
    float postOD = (float)stats.postProcessPasses;

    return effectiveOpaqueOD + transparentOD + postOD;
}

// 计算填充率（像素着色器执行次数/秒）
uint64_t CalculateFillRate(const FrameStats& stats, float fps) {
    int totalPixels = stats.resolutionW * stats.resolutionH;
    float od = CalculateAverageOverdraw(stats);
    float pixelsPerFrame = totalPixels * od;
    return (uint64_t)(pixelsPerFrame * fps);
}

void PrintSceneAnalysis(const FrameStats& stats) {
    std::cout << "========== Overdraw 分析 ==========\n\n";
    std::cout << "分辨率: " << stats.resolutionW << "×"
              << stats.resolutionH << " ("
              << (stats.resolutionW * stats.resolutionH / 1000000.0) << "MP)\n\n";

    std::cout << "不透明层:\n";
    float opaqueSum = 0;
    for (auto& l : stats.opaqueLayers) {
        std::cout << "  " << std::setw(25) << std::left << l.name
                  << " 覆盖率: " << std::fixed << std::setprecision(0)
                  << (l.coverage * 100) << "%\n";
        opaqueSum += l.coverage;
    }
    std::cout << "  不透明深度复杂度: " << opaqueSum << "x\n\n";

    std::cout << "透明层:\n";
    float transSum = 0;
    for (auto& l : stats.transparentLayers) {
        std::cout << "  " << std::setw(25) << std::left << l.name
                  << " 覆盖率: " << std::fixed << std::setprecision(0)
                  << (l.coverage * 100) << "%"
                  << " Alpha: " << std::setprecision(2) << l.alpha << "\n";
        transSum += l.coverage;
    }
    std::cout << "  透明层总覆盖率: " << transSum << "x\n\n";

    std::cout << "后处理 Pass: " << stats.postProcessPasses << "\n\n";

    float od = CalculateAverageOverdraw(stats);
    std::cout << "========================================\n";
    std::cout << "平均 Overdraw: " << std::fixed << std::setprecision(1)
              << od << "x\n";

    uint64_t fillRate60 = CalculateFillRate(stats, 60.0f);
    uint64_t fillRate30 = CalculateFillRate(stats, 30.0f);

    std::cout << "填充率需求:\n";
    std::cout << "  @60fps: " << (fillRate60 / 1000000.0) << "M pixels/s\n";
    std::cout << "  @30fps: " << (fillRate30 / 1000000.0) << "M pixels/s\n";
}

int main() {
    // 场景 A：典型 FPS 游戏主场景
    std::cout << "╔══════════════════════════════════════╗\n";
    std::cout << "║  场景 A: 典型 FPS — 户外战场       ║\n";
    std::cout << "╚══════════════════════════════════════╝\n\n";

    FrameStats fpsOutdoor;
    fpsOutdoor.resolutionW = 1920;
    fpsOutdoor.resolutionH = 1080;
    fpsOutdoor.opaqueLayers = {
        {"地形 (Terrain)", 1.0f},
        {"建筑 (Buildings)", 0.6f},
        {"植被 (Vegetation)", 0.4f},
        {"角色武器 (Weapon)", 0.15f},
    };
    fpsOutdoor.transparentLayers = {
        {"粒子: 烟雾 (Smoke)", 0.3f, 0.08f},
        {"粒子: 火花 (Sparks)", 0.1f, 0.1f},
        {"粒子: 枪口火焰 (Muzzle)", 0.05f, 0.2f},
        {"UI: HUD", 0.15f, 0.9f},
    };
    fpsOutdoor.postProcessPasses = 4;  // Bloom, Tonemap, DOF, MotionBlur

    PrintSceneAnalysis(fpsOutdoor);

    // 场景 B：UI 密集型
    std::cout << "\n╔══════════════════════════════════════╗\n";
    std::cout << "║  场景 B: UI 密集 — 主菜单/背包      ║\n";
    std::cout << "╚══════════════════════════════════════╝\n\n";

    FrameStats uiHeavy;
    uiHeavy.resolutionW = 1920;
    uiHeavy.resolutionH = 1080;
    uiHeavy.opaqueLayers = {
        {"3D 背景", 1.0f},
    };
    uiHeavy.transparentLayers = {
        {"UI: 半透明背景", 1.0f, 0.7f},
        {"UI: 面板 A", 0.6f, 0.85f},
        {"UI: 面板 B (嵌套)", 0.4f, 0.9f},
        {"UI: 面板 C (嵌套的嵌套)", 0.3f, 0.8f},
        {"UI: 物品图标 ×20", 0.25f, 0.95f},
        {"UI: 文字提示", 0.1f, 1.0f},
        {"UI: 光标", 0.01f, 1.0f},
    };
    uiHeavy.postProcessPasses = 1;

    PrintSceneAnalysis(uiHeavy);

    // 优化建议
    std::cout << "\n========== 优化建议 ==========\n\n";
    std::cout << "FPS 户外场景:\n";
    std::cout << "  1. 减少粒子重叠区 (烟雾+火花 覆盖面大) → 降低粒子数 50%\n";
    std::cout << "  2. HUD 元素尽量用不透明渲染（UI 通常不需要半透明）\n";
    std::cout << "  3. DOF 和 MotionBlur 降半分辨率 → 后处理 Overdraw 从 4x → 2.5x\n";
    std::cout << "\nUI 密集场景:\n";
    std::cout << "  1. 合并 UI 面板 → 减少层级 (7 层 → 3 层)\n";
    std::cout << "  2. 面板 A/B/C 可以考虑不透明（默认 alpha=1 的 Image）\n";
    std::cout << "  3. 不在屏幕上的 UI 元素用 CanvasGroup.alpha=0 或 SetActive(false)\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: 用 RenderDoc 测量实际 Overdraw

捕获你项目中任意一帧：
1. 打开 Quad Overdraw 视图
2. 截图并标注出红色/白色区域（Overdraw > 8x）
3. 对于每个红色区域，判断导致 Overdraw 的原因（透明物体？粒子？UI？）
4. 对每个原因提出一个优化方案

### 练习 2: 透明排序验证

创建一个简单场景：在 OpenGL/Vulkan/Unity 中渲染 3 个部分透明的四边形，交叉排列。分别用：
- 从后到前排序
- 从前到后排序
- 不做排序

观察渲染结果的差异，理解为什么透明物体必须从后到前排序。

### 练习 3: 填充率 vs 带宽瓶颈分离（挑战）

设计一个测试：
1. 场景 A：简单的 Unlit 纹理 Shader（极轻 PS，主要开销是纹理带宽）
2. 场景 B：复杂的 Perlin Noise 纯计算 Shader（不采样纹理，主要是 ALU）
3. 对比降低分辨率对两个场景的影响
4. 如果 A 提升小，B 提升大 → 场景 A 是带宽瓶颈，B 是填充率瓶颈

---

## 4. 扩展阅读

- **ARM Mali GPU 优化指南** — https://developer.arm.com/documentation/101897/latest/：Tile-Based GPU 的权威优化手册，深入讲解 HSR 和 Overdraw
- **RenderDoc Quad Overdraw** — https://renderdoc.org/docs/window/texture_viewer.html#quad-overdraw：RenderDoc 的 Overdraw 可视化使用
- **GPU Zen — Fill Rate Optimization** — 填充率优化的经典章节
- **UE Quad Overdraw Viewmode** — https://docs.unrealengine.com/5.0/en-US/rendering-optimization-view-modes-in-unreal-engine/#quadoverdraw

---

## 常见陷阱

- **移动端做 Z-Prepass**：TBDR 已经做了 HSR（Hidden Surface Removal），再做 Z-Prepass 破坏了 Tile 内流程，反而增加带宽和延迟。移动端永不使用 Z-Prepass。
- **把 UI Canvas 设置为 Screen Space - Overlay 时忽略 Overdraw**：Overlay Canvas 总是在所有内容之上渲染，每个像素 > 1 次 PS。如果叠加多层半透明 UI + 模糊背景，Overdraw 轻松 10x–30x。
- **粒子发射器数量爆炸**：50 个粒子发射器 × 平均 40 个粒子 = 2000 个透明 Quad，每个覆盖半个屏幕 → Overdraw = 1000x。
- **透明材质写深度**：默认透明 Shader 不写深度。如果某个透明材质意外写了深度（ZWrite On），会导致后面的透明物体被错误剔除。
- **植被 Overdraw 被忽略**：一片草地 100,000 个三角形，即使是 opaque，刀片的重叠也产生严重的深度复杂度。考虑用地形草的 Cluster Rendering（UE 的 Grass System）或 Instance 裁剪。
- **全屏模糊后处理不做降采样**：Bloom、DOF 等模糊效果应该在 1/2 或 1/4 分辨率执行。1080p 的高斯模糊 15×15 kernel 在 540p 下做，PS 调用从 207 万降到 52 万。
