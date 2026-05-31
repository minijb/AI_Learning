# UI 性能优化 — Canvas/UMG/UIToolkit

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50min
> 前置知识: Sprite 合批与图集优化（第 40 节）
>
> 核心要点: UI 是游戏性能的隐形杀手 — 一个看似简单的 HUD 可能在后台消耗 5-10ms 的 CPU 时间来重建 Canvas、重新布局、重新生成顶点。理解 Canvas 脏标记机制、分离动态/静态 UI、使用 GPU 驱动的 UI 框架，是让 UI 从性能瓶颈变为零开销背景的关键。

---

## 1. 概念讲解

### 为什么需要这个？

一个典型的游戏 UI 包含：血条、小地图、技能图标、聊天窗口、任务追踪、伤害数字、装备面板……可能数百个 UI 元素。

问题不在"元素多"，而在 **UI 的重建机制**。当一个 UI 元素的属性发生任何变化（位置、颜色、文本、图片），整个 Canvas 可能触发一次完整的 "Rebuild" 流程：

```
属性变化（如移动一个图标）
  → 标记 Canvas 为 Dirty
    → Layout Rebuild（重新计算所有元素的 Size/RectTransform）
      → Graphic Rebuild（重新生成所有元素的顶点/Mesh）
        → 提交到 GPU 渲染
```

一次简单的 HP 值更新，可能触发了 500 个 UI 元素的重新布局。这在一个 16ms 的帧预算中是不可接受的。

**关键洞察**：UI 性能问题几乎从来不是"元素太多"，而是"不该重建的东西被重建了"。

### 核心思想

#### 1. Unity uGUI Canvas 重建机制

Unity 的 uGUI（`UnityEngine.UI`）是**脏标记驱动的批处理系统**：

```
CanvasUpdateRegistry
  ├── PerformUpdate() — 每帧调用
  │   ├── Layout Rebuild（仅 Dirty Layout）
  │   └── Graphic Rebuild（仅 Dirty Graphic）
  └── Dirty 标记来源：
      ├── RectTransform 尺寸变化 → 标记自身 + 父级为 Dirty Layout
      ├── Graphic 的颜色/材质/Sprite 变化 → 标记自身为 Dirty Graphic
      └── Transform 变化（Position/Rotation/Scale）→ 标记自身 + 父级为 Dirty Layout
```

**最昂贵的操作**：
- `LayoutRebuilder.MarkLayoutForRebuild()` — 递归向上传播到 Canvas 根
- `Canvas.SendWillRenderCanvases()` — 每帧遍历所有启用 Canvas
- `Graphic.SetVerticesDirty()` — 触发顶点重建（Mesh Generation）

**为什么移动 UI 元素很昂贵**：

```csharp
// 这段看似无害的代码每帧触发一次完整的 Layout Rebuild：
void Update() {
    healthBarTransform.position = newPosition; // → Dirty Layout！
}
// 如果 healthBar 在一个有 ContentSizeFitter + LayoutGroup 的父级下，
// 整个层级链都会重建布局。
```

#### 2. Canvas 分离策略

将 UI 按"更新频率"分割到不同的 Canvas：

```
Canvas A (Static)     Canvas B (Dynamic)     Canvas C (High-Freq)
├── 背景图            ├── 血条 (HP 变化)      ├── 伤害数字（每帧位置变化）
├── 静态按钮          ├── 技能冷却图标          └── 浮动提示
├── 框架边框          └── 小地图
└── 标题文字
```

**原则**：
- Canvas A 几乎不重建（仅在场景切换时）
- Canvas B 仅在属性值变化时重建（低频）
- Canvas C 每帧重建 → 但只包含少量元素，重建成本低

**Canvas 分离的成本**：每个额外 Canvas 增加 ~1 个 Draw Call（Canvas 的 Mesh）。相比省下的 Layout Rebuild 时间，这个代价微不足道。

#### 3. Unity UI Toolkit（新系统）

Unity 在 2021+ 推出的 UI Toolkit 从根本上改变了 UI 架构：

| 特性 | uGUI (GameObject-based) | UI Toolkit (Retained Mode) |
|------|------------------------|---------------------------|
| 渲染模型 | 立即模式（Canvas 逐元素生成顶点） | 保留模式（GPU 驱动布局，类 Web DOM） |
| 布局系统 | LayoutGroup（CPU 每帧计算） | Yoga Layout（Flexbox，CSS-like） |
| 合批 | Canvas 为单位合批 | 自动纹理合批，减少 Draw Calls |
| 样式 | 每个组件独立设置 | USS（CSS-like 样式表），集中管理 |
| 动画 | 每帧修改 Transform | GPU 动画（`transition` 属性），零 CPU 开销 |
| 性能特点 | 大量元素时重建开销大 | 大量元素时布局更快，但首次构建慢 |

**UI Toolkit 的合批优势**：

uGUI 每个 Canvas 产生至少 1 个 Draw Call（更多如果图片来自不同 Atlas）。UI Toolkit 将所有 UI 渲染到一个 RenderTexture → 整个 UI 仅 1 个 Draw Call（在屏幕空间覆盖时）。

#### 4. UE UMG 优化

UE 的 UMG（Unreal Motion Graphics）使用 **Widget 树 + Slate 渲染**：

```
Widget Blueprint
  └── Canvas Panel
      ├── Image (背景)
      ├── Text Block (标题)
      └── Vertical Box
          ├── Progress Bar (血条)
          └── Button (技能)
              ├── Image (图标)
              └── Text Block (冷却时间)
```

**关键优化工具**：

| 组件 | 作用 | 使用场景 |
|------|------|---------|
| **Invalidation Box** | 缓存 Widget 的渲染结果，仅在内容变化时重绘 | 包裹变化频率低的 Widget 子树 |
| **Retainer Box** | 后台渲染 Widget 到 RenderTarget，屏幕每次绘制时直接贴图 | 复杂但静态的 UI（如小地图、背包网格） |
| **Widget Component** | 将 UMG 渲染到世界空间 | 3D/2D 世界中的 UI（如角色头顶血条） |

**Invalidation Box 原理**：

```
无 Invalidation Box:
每帧: Widget Tree 遍历 → 计算布局 → 生成顶点 → 渲染
                 ↑ 即使内容没变也全部重做

有 Invalidation Box:
每帧: 检查缓存是否有效 → 有效则直接使用缓存的顶点数据 → 渲染
                 ↑ 跳过布局和顶点生成
```

**Retainer Box 原理**：

```
Retainer Box 内部 Widget:
  ┌───────────────────┐
  │  复杂 UI（100+    │  渲染到后台 RenderTarget（如 512×512）
  │  个子 Widget）    │  → 仅此渲染时消耗 GPU
  └───────────────────┘
                    ↓
每帧渲染时：将 RenderTarget 作为一张纹理
          贴到屏幕上 → 1 个 Draw Call！
```

**代价**：Retainer Box 消耗额外的 GPU 内存（RenderTarget），且每次内容变化都需要重新渲染整个 RenderTarget。适合**复杂但更新频率低**的 UI。

#### 5. 字体性能

| 方案 | 优势 | 劣势 |
|------|------|------|
| **Legacy Text** (Unity) | 简单、无依赖 | 每字符生成一个 Quad → 顶点数多，无 SDF |
| **TextMeshPro** (Unity) | SDF 渲染，任意缩放清晰，单 Draw Call | 需要预热字体 Atlas，管理 Atlas 纹理 |
| **TextBlock** (UE) | Slate 原生，高效 | 大量动态文本仍有开销 |
| **Rich Text Block** (UE) | 支持富文本格式 | 解析开销更大 |

**TextMeshPro 的 SDF 渲染原理**：

传统文字渲染：每个字符一张位图 → 放大模糊 → 缩小锯齿。
SDF（Signed Distance Field）：存储到字符边缘的距离 → 缩放时动态计算 → 永远清晰。

**关键**：SDF 字体 Atlas 只需一张纹理，所有字号共享 → **单 Draw Call 绘制所有文字**。

**TextMeshPro Atlas 管理陷阱**：
- 默认 Atlas 大小为 512×512，仅容纳 ~1000 个字符
- 如果游戏使用中文/日文/韩文，字符集远超 1000 → Atlas 溢出 → 动态重新生成 Atlas → 严重卡顿
- 解决方案：使用 `TMP_FontAsset` 的 **Fallback Fonts** 链或多 Atlas 模式

#### 6. UI 动画性能

**不应该用 Layout 属性做动画**（为什么）：

```csharp
// 坏：每帧修改 RectTransform.sizeDelta → 触发 Layout Rebuild
void Update() {
    rt.sizeDelta = Vector2.Lerp(rt.sizeDelta, targetSize, t);
}

// 好：修改 Transform.scale → 仅影响该元素，不触发父级重建
void Update() {
    transform.localScale = Vector3.Lerp(transform.localScale, targetScale, t);
}
```

| 动画方式 | Layout Rebuild? | Graphic Rebuild? | 性能 |
|---------|----------------|-----------------|------|
| 修改 RectTransform 属性 | 是（+父级递归） | 可能 | 差 |
| 修改 Transform.localScale | 否 | 否 | 好 |
| 修改 CanvasRenderer 颜色 | 否 | 否（仅标记 Dirty） | 好 |
| 修改 Material 属性 | 否 | 否 | 最佳 |
| UI Toolkit transition | 否 | 否（GPU 端） | 最佳 |

#### 7. 性能量化：Canvas.BuildBatch 时间

Unity 的 `Canvas.BuildBatch` 是 Canvas 重建的核心函数。你可以通过 Profiler 的 `Canvas.BuildBatch` 标记测量每个 Canvas 的重建时间。

**典型数值**：

| Canvas 元素数 | 无变化 BuildBatch | 全部 Dirty BuildBatch |
|--------------|-------------------|----------------------|
| 50 | ~0.1ms | ~0.3ms |
| 200 | ~0.3ms | ~1.5ms |
| 500 | ~0.5ms | ~4ms |
| 1000 | ~1ms | ~10ms |

**关键**：优化目标是**减少 Dirty Element 数量**，而不是减少总元素数量。1000 个从不变化的元素不花钱。

---

## 2. 代码示例

### 示例 A：Unity — UI 合批性能对比

```csharp
// UIBenchmark.cs
// 对比：(A) 1000 个 UI 元素在同一个 Canvas 中移动 → 触发大规模重建
//       (B) 1000 个 UI 元素分布在 10 个 Sub-Canvas 中 → 仅重建变化的 Canvas
// 用法：挂载到场景中的 Benchmark 对象，点击 Play 观察 Profiler

using UnityEngine;
using UnityEngine.UI;
using System.Collections.Generic;
using System.Diagnostics;

public class UIBenchmark : MonoBehaviour
{
    [Header("Canvas 设置")]
    [SerializeField] private bool useSubCanvases = false;
    [SerializeField] private int elementCount = 1000;
    [SerializeField] private int subCanvasCount = 10;

    [Header("动画")]
    [SerializeField] private bool animateElements = true;
    [SerializeField] private float animationSpeed = 50f;

    private List<GameObject> uiElements = new List<GameObject>();
    private List<RectTransform> elementTransforms = new List<RectTransform>();

    private Canvas rootCanvas;

    private void Start()
    {
        rootCanvas = GetComponent<Canvas>();
        if (rootCanvas == null)
        {
            rootCanvas = gameObject.AddComponent<Canvas>();
            gameObject.AddComponent<CanvasScaler>();
            gameObject.AddComponent<GraphicRaycaster>();
        }

        CreateUIElements();
    }

    private void CreateUIElements()
    {
        if (useSubCanvases)
            CreateWithSubCanvases();
        else
            CreateSingleCanvas();
    }

    private void CreateSingleCanvas()
    {
        RectTransform rootRT = GetComponent<RectTransform>();
        Sprite dummySprite = CreateDummySprite();

        for (int i = 0; i < elementCount; i++)
        {
            GameObject go = new GameObject($"UIElem_{i}");
            go.transform.SetParent(transform);
            go.transform.localScale = Vector3.one;

            RectTransform rt = go.AddComponent<RectTransform>();
            float x = Random.Range(0f, rootRT.rect.width);
            float y = Random.Range(0f, rootRT.rect.height);
            rt.anchoredPosition = new Vector2(x, y);
            rt.sizeDelta = new Vector2(32, 32);

            Image img = go.AddComponent<Image>();
            img.sprite = dummySprite;
            img.color = new Color(Random.value, Random.value, Random.value, 1f);

            uiElements.Add(go);
            elementTransforms.Add(rt);
        }

        UnityEngine.Debug.Log(
            $"[Benchmark] 单 Canvas 模式: {elementCount} 个 Image" +
            $"\n  所有元素共享 1 个 Canvas — 任一元素变化触发全部重建"
        );
    }

    private void CreateWithSubCanvases()
    {
        RectTransform rootRT = GetComponent<RectTransform>();
        Sprite dummySprite = CreateDummySprite();
        int perCanvas = elementCount / subCanvasCount;

        for (int c = 0; c < subCanvasCount; c++)
        {
            // 创建 Sub-Canvas
            GameObject canvasGO = new GameObject($"SubCanvas_{c}");
            canvasGO.transform.SetParent(transform);
            canvasGO.transform.localScale = Vector3.one;

            Canvas subCanvas = canvasGO.AddComponent<Canvas>();
            canvasGO.AddComponent<GraphicRaycaster>(); // 仅当需要交互时
            RectTransform canvasRT = canvasGO.GetComponent<RectTransform>();
            canvasRT.anchorMin = Vector2.zero;
            canvasRT.anchorMax = Vector2.one;
            canvasRT.sizeDelta = Vector2.zero;

            for (int i = 0; i < perCanvas; i++)
            {
                GameObject go = new GameObject($"UIElem_c{c}_{i}");
                go.transform.SetParent(canvasGO.transform);
                go.transform.localScale = Vector3.one;

                RectTransform rt = go.AddComponent<RectTransform>();
                float x = Random.Range(0f, rootRT.rect.width);
                float y = Random.Range(0f, rootRT.rect.height);
                rt.anchoredPosition = new Vector2(x, y);
                rt.sizeDelta = new Vector2(32, 32);

                Image img = go.AddComponent<Image>();
                img.sprite = dummySprite;
                img.color = new Color(Random.value, Random.value, Random.value, 1f);

                uiElements.Add(go);
                elementTransforms.Add(rt);
            }
        }

        UnityEngine.Debug.Log(
            $"[Benchmark] 多 Canvas 模式: {elementCount} 个 Image 分布在 {subCanvasCount} 个 Sub-Canvas\n" +
            $"  每个 Canvas ~{perCanvas} 个元素 — 变化仅影响所在 Canvas"
        );
    }

    private Sprite CreateDummySprite()
    {
        // 创建一个 1×1 的白色纹理作为占位 Sprite
        Texture2D tex = new Texture2D(1, 1);
        tex.SetPixel(0, 0, Color.white);
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, 1, 1), Vector2.one * 0.5f);
    }

    private void Update()
    {
        if (!animateElements || elementTransforms.Count == 0) return;

        // 移动每个 UI 元素的 RectTransform → 触发 Layout Dirty
        float t = Time.time;
        int count = Mathf.Min(200, elementTransforms.Count); // 仅动画前 200 个以展示效果

        for (int i = 0; i < count; i++)
        {
            Vector2 pos = elementTransforms[i].anchoredPosition;
            pos.x += Mathf.Sin(t * 3f + i * 0.3f) * animationSpeed * Time.deltaTime;
            pos.y += Mathf.Cos(t * 2f + i * 0.3f) * animationSpeed * Time.deltaTime;
            elementTransforms[i].anchoredPosition = pos;
        }
    }

    private void OnDestroy()
    {
        foreach (var go in uiElements)
            if (go != null) Destroy(go);
        uiElements.Clear();
        elementTransforms.Clear();
    }
}

// 测量方法：
// 1. 运行场景，设置 animateElements=true
// 2. 打开 Unity Profiler (Window → Analysis → Profiler)
// 3. 选中 CPU Usage 模块，搜索 "Canvas.BuildBatch"
// 4. 记录平均和峰值 BuildBatch 时间
// 5. 切换 useSubCanvases 标志重新运行，对比差异
//
// 预期结果：
// 单 Canvas:  Canvas.BuildBatch ≈ 4-8ms（200 个元素移动触发全量重建）
// 多 Canvas:  Canvas.BuildBatch ≈ 0.5-2ms（仅受影响的 Sub-Canvas 重建 ~20 个元素）
```

### 示例 B：Unity — TextMeshPro vs Legacy Text 对比

```csharp
// TextBenchmark.cs
// 对比 500 个 Text 标签实时更新时的性能差异
// 需要 TMPro 包：Window → Package Manager → TextMeshPro

using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections.Generic;

public class TextBenchmark : MonoBehaviour
{
    [Header("模式")]
    [SerializeField] private bool useTextMeshPro = true;
    [SerializeField] private int labelCount = 500;

    [Header("字体资源")]
    [SerializeField] private TMP_FontAsset tmpFont;
    [SerializeField] private Font legacyFont;

    private List<GameObject> labels = new List<GameObject>();
    private List<Text> legacyTexts = new List<Text>();
    private List<TMP_Text> tmpTexts = new List<TMP_Text>();

    private Canvas canvas;

    private void Start()
    {
        canvas = GetComponent<Canvas>();
        if (canvas == null)
        {
            canvas = gameObject.AddComponent<Canvas>();
            gameObject.AddComponent<CanvasScaler>();
            gameObject.AddComponent<GraphicRaycaster>();
        }

        CreateLabels();

        UnityEngine.Debug.Log(
            $"[TextBenchmark] 模式: {(useTextMeshPro ? "TextMeshPro" : "Legacy Text")}" +
            $"\n  Label 数量: {labelCount}" +
            $"\n  所有 Label 每帧更新文本内容"
        );
    }

    private void CreateLabels()
    {
        RectTransform rootRT = GetComponent<RectTransform>();

        for (int i = 0; i < labelCount; i++)
        {
            GameObject go = new GameObject($"Label_{i}");
            go.transform.SetParent(transform);
            go.transform.localScale = Vector3.one;

            RectTransform rt = go.AddComponent<RectTransform>();
            float x = Random.Range(0f, rootRT.rect.width);
            float y = Random.Range(0f, rootRT.rect.height);
            rt.anchoredPosition = new Vector2(x, y);
            rt.sizeDelta = new Vector2(100, 30);

            if (useTextMeshPro)
            {
                TMP_Text tmp = go.AddComponent<TextMeshProUGUI>();
                tmp.font = tmpFont;
                tmp.fontSize = 14;
                tmp.alignment = TextAlignmentOptions.Center;
                tmp.text = $"TMP_{i}";
                tmp.raycastTarget = false; // ★ 禁用 Raycast 减少事件系统开销
                tmpTexts.Add(tmp);
            }
            else
            {
                Text legacy = go.AddComponent<Text>();
                legacy.font = legacyFont;
                legacy.fontSize = 14;
                legacy.alignment = TextAnchor.MiddleCenter;
                legacy.text = $"Legacy_{i}";
                legacy.raycastTarget = false;
                legacyTexts.Add(legacy);
            }

            labels.Add(go);
        }
    }

    private void Update()
    {
        float t = Time.time;

        if (useTextMeshPro)
        {
            for (int i = 0; i < tmpTexts.Count; i++)
            {
                // 每帧更新文本内容 → 触发 Graphic Dirty → 顶点重建
                tmpTexts[i].text = $"HP:{Mathf.FloorToInt(Mathf.Sin(t + i * 0.1f) * 50 + 100)}";
            }
        }
        else
        {
            for (int i = 0; i < legacyTexts.Count; i++)
            {
                legacyTexts[i].text = $"HP:{Mathf.FloorToInt(Mathf.Sin(t + i * 0.1f) * 50 + 100)}";
            }
        }
    }

    private void OnDestroy()
    {
        foreach (var go in labels)
            if (go != null) Destroy(go);
        labels.Clear();
        legacyTexts.Clear();
        tmpTexts.Clear();
    }
}

// 性能测量：
// 1. 先设置 useTextMeshPro=true（需要 TMP_FontAsset 引用）
// 2. 运行，在 Profiler 中搜索 "Canvas.BuildBatch"
// 3. 再设置 useTextMeshPro=false（需要 Legacy Font 引用）
// 4. 对比 BuildBatch 时间 + "Graphic.Rebuild" 标记
//
// 预期结果（labelCount=500）：
// Legacy Text: BuildBatch ≈ 3-6ms (每字符独立 Quad，顶点数多)
// TextMeshPro:  BuildBatch ≈ 1-2ms (SDF 单 Quad 每字符，顶点数少)
//
// 注意：TMP 的优势主要在顶点生成阶段，SDF 采样在 Shader 中有额外开销
// 但 GPU 端开销远小于 CPU 端顶点生成开销
```

### 示例 C：UE UMG — Invalidation Box 与 Retainer Box

```cpp
// UMGWidgetOptimizer.cpp
// UE UMG Widget 性能优化示例
// 在 Widget Blueprint 中配合使用 C++ 逻辑

#include "UMGWidgetOptimizer.h"
#include "Components/InvalidationBox.h"
#include "Components/RetainerBox.h"
#include "Components/CanvasPanel.h"
#include "Components/ProgressBar.h"
#include "Components/TextBlock.h"
#include "Components/Image.h"
#include "Engine/Engine.h"
#include "TimerManager.h"

void UUMGWidgetOptimizer::NativeConstruct()
{
    Super::NativeConstruct();

    // 初始化性能统计
    FTimerHandle statsTimer;
    GetWorld()->GetTimerManager().SetTimer(
        statsTimer,
        this,
        &UUMGWidgetOptimizer::LogPerformanceStats,
        5.0f,  // 每 5 秒输出一次
        true
    );
}

void UUMGWidgetOptimizer::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
    Super::NativeTick(MyGeometry, InDeltaTime);

    frameCount++;
    tickAccumulator += InDeltaTime;
}

void UUMGWidgetOptimizer::LogPerformanceStats()
{
    if (tickAccumulator > 0.f)
    {
        float avgTickMs = (tickAccumulator / frameCount) * 1000.f;
        FString msg = FString::Printf(
            TEXT("[UMG Optimizer] Avg Tick: %.3fms over %d frames | "
                 "Invalidation Boxes: %s | Retainer Boxes: %s"),
            avgTickMs,
            frameCount,
            bUseInvalidationBoxes ? TEXT("ON") : TEXT("OFF"),
            bUseRetainerBoxes ? TEXT("ON") : TEXT("OFF")
        );
        GEngine->AddOnScreenDebugMessage(-1, 5.f, FColor::Cyan, msg);
    }

    frameCount = 0;
    tickAccumulator = 0.f;
}

// ★ 优化 1：动态启用/禁用 Invalidation Box ★
void UUMGWidgetOptimizer::ApplyInvalidationBoxOptimization(bool bEnable)
{
    bUseInvalidationBoxes = bEnable;

    // 遍历 Widget 树，为适当的子 Widget 包裹 Invalidation Box
    if (bEnable)
    {
        // 找到静态内容的容器（如背包面板、设置面板）
        // 在 Blueprint 中手动包裹效率更高，这里是代码示例
        if (InventoryPanel)
        {
            UInvalidationBox* invalBox = NewObject<UInvalidationBox>(this);
            invalBox->SetVisibility(ESlateVisibility::SelfHitTestInvisible);

            // 将 InventoryPanel 从当前父级移入 InvalidationBox
            UPanelSlot* oldSlot = InventoryPanel->Slot;
            UCanvasPanel* parent = Cast<UCanvasPanel>(InventoryPanel->GetParent());
            if (parent && oldSlot)
            {
                parent->RemoveChild(InventoryPanel);
                parent->AddChild(invalBox);

                // 设置 InvalidationBox 的 Slot 属性（保持原布局）
                if (UCanvasPanelSlot* invalSlot =
                    Cast<UCanvasPanelSlot>(invalBox->Slot))
                {
                    UCanvasPanelSlot* oldCanvasSlot = Cast<UCanvasPanelSlot>(oldSlot);
                    if (oldCanvasSlot)
                    {
                        invalSlot->SetPosition(oldCanvasSlot->GetPosition());
                        invalSlot->SetSize(oldCanvasSlot->GetSize());
                    }
                }

                invalBox->AddChild(InventoryPanel);
            }

            UE_LOG(LogTemp, Log,
                TEXT("[UMG Optimizer] Invalidation Box applied to Inventory Panel"));
        }
    }
    else
    {
        // 移除所有动态创建的 Invalidation Box（简化示例）
        // 实际项目中建议在 Blueprint 中手动管理
    }
}

// ★ 优化 2：Retainer Box 用于复杂但低频更新的 UI ★
void UUMGWidgetOptimizer::ApplyRetainerBoxToMiniMap(URetainerBox* RetainerBox)
{
    if (!RetainerBox || !MiniMapWidget) return;

    bUseRetainerBoxes = true;

    RetainerBox->SetRetainerRenderingPhase(0);     // 第一阶段渲染（在背景后）
    RetainerBox->SetRetainerRenderingTextureParameter(FName("MiniMapRT"));
    RetainerBox->SetEffectMaterial(nullptr);         // 无后处理效果
    RetainerBox->SetTextureParameter(FName("MiniMapRT"));

    UE_LOG(LogTemp, Log,
        TEXT("[UMG Optimizer] Retainer Box applied to MiniMap — "
             "renders to RT, 1 draw call on screen"));
}

// ★ 优化 3：批量更新 Widget 属性减少 Invalidation ★
void UUMGWidgetOptimizer::BatchUpdateHealthBars(
    const TArray<UProgressBar*>& HealthBars,
    const TArray<float>& HealthValues)
{
    check(HealthBars.Num() == HealthValues.Num());

    // 在一次 Tick 内批量更新所有血条
    // 它们位于同一个 Invalidation Box 内 → 仅一次 Invalidation
    for (int32 i = 0; i < HealthBars.Num(); ++i)
    {
        if (HealthBars[i])
        {
            HealthBars[i]->SetPercent(HealthValues[i]);
        }
    }
    // 如果所有 HealthBars 在同一个 InvalidationBox 下，
    // 整个子树的 Invalidation 只触发一次重绘
}
```

```cpp
// UMGWidgetOptimizer.h
#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "UMGWidgetOptimizer.generated.h"

class UInvalidationBox;
class URetainerBox;
class UProgressBar;
class UWidget;

UCLASS()
class UUMGWidgetOptimizer : public UUserWidget
{
    GENERATED_BODY()

public:
    virtual void NativeConstruct() override;
    virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

    UFUNCTION(BlueprintCallable, Category = "Optimization")
    void ApplyInvalidationBoxOptimization(bool bEnable);

    UFUNCTION(BlueprintCallable, Category = "Optimization")
    void ApplyRetainerBoxToMiniMap(URetainerBox* RetainerBox);

    UFUNCTION(BlueprintCallable, Category = "Optimization")
    void BatchUpdateHealthBars(
        const TArray<UProgressBar*>& HealthBars,
        const TArray<float>& HealthValues);

private:
    void LogPerformanceStats();

    // Blueprint 绑定的 Widget 引用
    UPROPERTY(meta = (BindWidget))
    UWidget* InventoryPanel;

    UPROPERTY(meta = (BindWidget))
    UWidget* MiniMapWidget;

    // 状态
    bool bUseInvalidationBoxes = false;
    bool bUseRetainerBoxes = false;
    int32 frameCount = 0;
    float tickAccumulator = 0.f;
};
```

**Usage in Blueprint**:
1. Create a Widget Blueprint inheriting from `UMGWidgetOptimizer`
2. Name your child widgets to match the `BindWidget` meta properties (`InventoryPanel`, `MiniMapWidget`)
3. Call `ApplyInvalidationBoxOptimization(true)` on `Event Construct`
4. Set up a `RetainerBox` around the MiniMap and pass it to `ApplyRetainerBoxToMiniMap`

---

## 3. 练习

### 练习 1: Canvas 拆分前后对比（基础）

**目标**：亲手验证 Canvas 分离策略的效果

1. 创建一个包含以下元素的 UI 场景：
   - 10 个静态 Image（背景框架）
   - 5 个 Button（菜单按钮）
   - 3 个 Slider（设置面板）
   - 1 个以 60fps 旋转的图标（加载动画）
2. 全部放在一个 Canvas 下，运行并记录 `Canvas.BuildBatch` 时间
3. 重构：将静态元素放入 Canvas A，动态图标放入 Canvas B
4. 再次测量 `Canvas.BuildBatch` 时间
5. 回答：为什么仅仅拆分 Canvas 就能减少重建时间？（提示：Dirty Flag 传播范围）

### 练习 2: TextMeshPro Atlas 管理（进阶）

**目标**：配置 TMP 字体 Atlas 以支持中文字符集

1. 创建一个 `TMP_FontAsset`，使用包含 6763 个常用汉字的字符集
2. 设置 Atlas Resolution 为 2048×2048
3. 观察：Atlas 是否能容纳所有字符？
   - 如果不能 → 使用 **Fallback Font** 链：主字体（常用字）+ 备用字体（罕见字）
   - 或使用 **Multi-Atlas** 模式：同一字体多个 Atlas 纹理
4. 创建 200 个 TMP 标签随机显示中文字符，运行并测量：
   - 首次显示时的 Atlas 填充开销
   - 动态文本更新时的 Canvas 重建时间

### 练习 3: UI Toolkit 迁移实验（挑战，可选）

**目标**：将 uGUI 的 HUD 迁移到 UI Toolkit，对比性能

1. 在 Unity 2021.3+ 中创建一个简单的 HUD（血条、技能图标、小地图、聊天窗口）
2. 先用 uGUI 实现（GameObject + Canvas）
3. 再用 UI Toolkit 实现（UXML + USS + C#）
4. 对比：
   - 初始加载时间（首次构建 UI）
   - 每帧 `Canvas.BuildBatch` / UI Toolkit 的布局时间
   - 内存占用
   - Draw Call 数量
5. 记录哪个方案在哪种场景下更有优势

---

## 4. 扩展阅读

- **Unity UI 优化指南**: https://unity.com/how-to/unity-ui-optimization-tips
- **Unity UI Toolkit 文档**: https://docs.unity3d.com/Manual/UIElements.html
- **TextMeshPro 官方文档**: https://docs.unity3d.com/Packages/com.unity.textmeshpro@latest
- **UE UMG 性能指南**: https://docs.unrealengine.com/en-US/optimizing-umg-user-interfaces/
- **UE Slate/UMG Invalidation**: https://docs.unrealengine.com/en-US/slate-invalidation-in-unreal-engine/
- **"Optimizing Unity UI" (Unite 2017)** — Ian Dundore 的经典演讲
- **"Practical UMG Optimization" (UE Dev Community)** — 社区整理的实战技巧

---

## 常见陷阱

1. **所有 UI 放在同一个 Canvas。** 任何元素变化 → 整个 Canvas 重建 → 800 个静态元素被无意义地重新计算。**分离静态/动态 Canvas 是最简单有效的 UI 优化。**

2. **每帧修改 text 属性的非必要更新。** 如果文本值没变就不要赋值：
   ```csharp
   // 坏
   void Update() { healthText.text = $"HP: {hp}"; } // 即使 hp 没变也触发重建
   // 好
   void UpdateHealth(int newHp) { if (hp != newHp) { hp = newHp; healthText.text = $"HP: {hp}"; } }
   ```

3. **ContentSizeFitter + LayoutGroup 组合。** 这是 Canvas 重建的"核武器"—— ContentSizeFitter 强制 LayoutGroup 每帧重新计算所有子元素的尺寸。**仅在必要时使用，或为它们包裹单独的 Canvas。**

4. **GraphicRaycaster 在不需要交互的 Canvas 上。** 每个 GraphicRaycaster 每帧遍历 Canvas 下所有 Graphic，即使没有点击。对纯显示用的 Canvas（如背景），**务必禁用 Raycaster** 组件。

5. **TextMeshPro 字符集不足导致运行时 Atlas 重建。** 如果运行时遇到不在 Atlas 中的字符，TMP 会触发 Atlas 重新生成（Rebake）→ **严重卡顿（可能 >100ms）**。**在开发阶段就确认所有需要的字符都在 Atlas 中。**

6. **UE Retainer Box 滥用。** 将整个 HUD 包裹在 Retainer Box 中看似减少 Draw Calls，但 (a) 每次微小的内容变化都触发完整 RenderTarget 重绘 (b) 消耗大量 GPU 内存。**仅对复杂且低频更新的 Widget 子树使用。**

7. **UMG 中的 Tick 开销。** 每个继承自 `UUserWidget` 的 Widget Blueprint 默认启用 Tick。如果在 Blueprint 中实现了 `Event Tick`，即使只有一个空函数调用，也有开销。**清空不需要的 Tick 逻辑，或在 C++ 中设置 `bHasScriptImplementedTick = false`。**
