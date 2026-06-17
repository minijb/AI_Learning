---
title: Unity 字体系统研究简报
description: 供 subagent 撰写教程时引用的底层事实、API 与最佳实践汇总
tags: [unity, textmeshpro, textcore, font, research]
updated: 2026-06-17
---

# Unity 字体系统研究简报

> 搜索日期: 2026-06-17
> 来源: Unity 官方文档、Scripting API、UnityCsReference 源码 mirror、社区最佳实践

---

## 1. 三大文字系统的关系

| 系统 | 底层渲染 | 使用场景 | 当前定位 |
|------|----------|----------|----------|
| uGUI `Text` (Legacy) | 传统动态图集 (`UnityEngine.Font`) | 老项目维护 | 已不推荐使用 |
| TextMeshPro (`TMP_Text`) | SDF/Bitmap 图集，独立 Font Asset | 3D 文字、UI 文字 | Unity 2018+ 的标准文字方案 |
| UI Toolkit `Label` | TextCore（基于 TMP 思路重构） | 新 UI 系统、Editor 扩展 | Unity 2021+ 主推 |

- UI Toolkit / TextCore 与 TextMeshPro 共享核心概念：font asset、atlas、glyph、signed distance field。
- TextCore 的 `TextGenerator.GenerateText(settings, textInfo)` 是 UI Toolkit 文字网格生成入口（见 `UnityCsReference/Modules/TextCoreTextEngine/Managed/TextGenerator.cs`）。

---

## 2. Font Asset 的内部结构

- TrueType/OpenType (`.ttf` / `.otf`) 不会直接用于渲染，需要转换成 **Font Asset**。
- Font Asset 包含：
  - **Atlas Texture**：存字形位图或 SDF 场。
  - **Glyph Table**：每个 glyph 的 `GlyphMetrics`（尺寸、advance、bearing）、`GlyphRect`（在 atlas 中的位置）。
  - **Character Table**：Unicode → glyph index 映射。
  - **Face Info**：line height、ascender、descender、scale、baseline。
  - **Material & Shader**：默认 `TextMeshPro/SDF` 或 UI Toolkit 的对应 shader。
  - **Fallback Font Assets**：当前 asset 缺字时继续查找的链。
  - **Font Weights / Style**：用于模拟粗体/斜体。

关键 API:
- `UnityEngine.TextCore.Glyph`：`atlasIndex`, `glyphRect`, `metrics`, `index`, `scale`。
- `UnityEngine.TextCore.GlyphMetrics`：`width`, `height`, `horizontalBearingX`, `horizontalBearingY`, `horizontalAdvance`。
- `UnityEngine.TextCore.GlyphRect`：atlas 中的 `x, y, width, height`。

---

## 3. Atlas 生成参数

### Population Mode
- **Static**：构建时预烘焙指定字符集，包体大、运行时无动态生成开销。
- **Dynamic**：运行时按需将字符光栅化到 atlas，需要源字体文件（.ttf）在 build 中。
- **Dynamic OS**：引用操作系统字体，不打包源字体，适合做 fallback / emoji。

### Render Mode
- **Bitmap**：`SMOOTH`, `SMOOTH_HINTED`, `RASTER`, `RASTER_HINTED`, `COLOR`, `COLOR_HINTED`。
  - 适合像素风、小字号、需要与屏幕像素严格对齐的场景。
- **SDF**：`SDF`, `SDFAA`, `SDFAA_HINTED`, `SDF8`, `SDF16`, `SDF32`。
  - 越高 oversampling（8/16/32）生成越慢但质量越高，适合大标题或复杂字形。
  - 默认动态图集使用 `SDFAA`（速度优先）。

### Padding 与采样
- Padding 是 glyph 在 atlas 中的空白边距，给 SDF 渐变和特效（outline、glow）留空间。
- 经验比例：**sampling point size : padding ≈ 10:1**。
- ASCII 专用：512×512 + padding 5 通常足够；CJK/emoji 需要 2048×2048 或多图集。

---

## 4. SDF 渲染原理（重点）

- SDF atlas 存储的不是颜色，而是 **每个像素到最近字形轮廓的有符号距离**。
- 中点（距离=0）对应字形边缘；正值在字形内部，负值在外部。
- 片元着色器通过采样距离场并与阈值比较，得到锐利边缘，支持任意缩放。
- 特效原理：
  - **Outline**：在轮廓内外一定距离区间叠加颜色。
  - **Underlay / Drop Shadow**：偏移 UV 后采样距离场，再与原片元混合。
  - **Glow / Dilate**：基于距离场做软边扩展。
- 图集 padding 不足时，相邻 glyph 的距离场会互相渗透，导致边缘artifact。

---

## 5. Fallback 链（TextMeshPro）

TextMeshPro 搜索 missing glyph 的顺序：

1. 主 Font Asset
2. 主 asset 的 Fallback Font Assets（递归）
3. 当前 Text 的 Sprite Asset（按 Unicode 匹配）
4. Project Settings 中的 Global Fallback Font Assets（递归）
5. Default Sprite Asset
6. Default Font Asset
7. Missing glyphs 占位符

- 对 CJK、emoji、生僻符号，应拆分到多个 fallback asset。
- UI Toolkit 同样支持 fallback font asset 与 global fallback。

---

## 6. 网格生成与批处理

- 每次文字变化时，`TMP_Text` / TextCore `TextGenerator` 会：
  1. 解析字符串与 rich text tag。
  2. 查找每个字符对应的 glyph（必要时触发动态光栅化）。
  3. 计算 layout：line break、alignment、kerning、baseline。
  4. 生成 quad（4 顶点 + UV）并填充 vertex color。
  5. 提交 CanvasRenderer / UI Toolkit renderer。
- 动态文字每帧修改会导致 atlas 更新和网格重建，属于常见性能瓶颈。
- 同一 material 的 UI 文字可以被 Canvas batch；3D TextMeshPro 不参与 UI batch。

---

## 7. 性能要点

- 避免在 `Update` 中持续修改 `text`。
- 大段文本拆分到多个 Text 组件，减少单组件顶点数。
- 静态文本预生成 static atlas；动态文本限制字符集。
- 谨慎使用 `Best Fit`，它会反复重排并可能重生成图集。
- 移动平台注意 atlas 尺寸上限与 fill-rate。
- UI Toolkit PanelSettings 之间不 batch，但同一 Panel 内多个元素可 batch。

---

## 8. 自定义与扩展

- TextMeshPro 支持 **Material Presets**：同一 atlas 使用不同 material 变体。
- 可编写自定义 shader（基于 `TextMeshPro/SDF`）实现波纹、描边渐变等效果。
- Sprite Asset：将图标/表情作为特殊 glyph 插入文本，按 Unicode 或名称引用。
- Text Stylesheet：定义 `<style=name>` 富文本样式，集中管理。
- MSDF（Multi-channel SDF）是社区方案，可进一步消除 SDF 在尖锐拐角的模糊；Unity 内置不直接支持 MSDF，需要第三方工具/插件。

---

## 9. 关键官方链接

- [TextMeshPro Font Asset Creator](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/FontAssetsCreator.html)
- [TextMeshPro About SDF fonts](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/FontAssetsSDF.html)
- [TextMeshPro Fallback font assets](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/FontAssetsFallback.html)
- [TextMeshPro Shaders](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/Shaders.html)
- [UI Toolkit Introduction to font assets](https://docs.unity3d.com/Manual/UIE-font-asset.html)
- [UI Toolkit Text best practices](https://docs.unity3d.com/Manual/best-practice-guides/ui-toolkit-for-advanced-unity-developers/text.html)
- [UnityCsReference TextGenerator.cs](https://github.com/Unity-Technologies/UnityCsReference/blob/master/Modules/TextCoreTextEngine/Managed/TextGenerator.cs)
- [Unity Scripting API: TextCore.Glyph](https://docs.unity3d.com/ScriptReference/TextCore.Glyph.html)
- [Unity Scripting API: TextCore.GlyphMetrics](https://docs.unity3d.com/ScriptReference/TextCore.GlyphMetrics.html)
- [Unity Scripting API: TextCore.GlyphRect](https://docs.unity3d.com/ScriptReference/TextCore.GlyphRect.html)
