---
title: 学习资源汇总：Unity 字体系统
updated: 2026-06-17
tags: [unity, font, resources]
---

# 学习资源汇总：Unity 字体系统

## 官方文档

- [TextMeshPro Font Asset Creator](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/FontAssetsCreator.html) — 创建 TMP Font Asset 的每个参数说明。
- [About SDF fonts | TextMeshPro](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/FontAssetsSDF.html) — SDF 渲染原理与效果对比。
- [Fallback font assets | TextMeshPro](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/FontAssetsFallback.html) — fallback 链的完整搜索顺序。
- [Shaders | TextMeshPro](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/Shaders.html) — SDF / Bitmap / Surface / Overlay shader 概览。
- [UI Toolkit: Introduction to font assets](https://docs.unity3d.com/Manual/UIE-font-asset.html) — TextCore Font Asset、atlas population/render modes。
- [UI Toolkit Text best practices](https://docs.unity3d.com/Manual/best-practice-guides/ui-toolkit-for-advanced-unity-developers/text.html) — UI Toolkit 文字使用与性能建议。
- [Comparison of UI systems in Unity](https://docs.unity3d.com/Manual/UI-system-compare.html) — uGUI、UI Toolkit、IMGUI 的功能对比。
- [Optimizing Unity UI - Unity Learn](https://learn.unity.com/course/doozyui-related-tutorials/tutorial/optimizing-unity-ui) — UI 与文字批量优化课程。

## Scripting API 参考

- [UnityEngine.TextCore.Glyph](https://docs.unity3d.com/ScriptReference/TextCore.Glyph.html)
- [UnityEngine.TextCore.GlyphMetrics](https://docs.unity3d.com/ScriptReference/TextCore.GlyphMetrics.html)
- [UnityEngine.TextCore.GlyphRect](https://docs.unity3d.com/ScriptReference/TextCore.GlyphRect.html)
- [TMPro.TMP_Text](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/api/TMPro.TMP_Text.html)
- [TMPro.TMP_FontAsset](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/api/TMPro.TMP_FontAsset.html)
- [TMPro.TMP_TextInfo](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/api/TMPro.TMP_TextInfo.html)

## 源码与实现参考

- [UnityCsReference: TextCoreTextEngine/TextGenerator.cs](https://github.com/Unity-Technologies/UnityCsReference/blob/master/Modules/TextCoreTextEngine/Managed/TextGenerator.cs) — TextCore 文本生成管线源码。
- [needle-mirror/com.unity.textmeshpro](https://github.com/needle-mirror/com.unity.textmeshpro) — TMP 包的非官方 mirror，可查看 `TMP_Text.cs` 等实现。
- [needle-mirror/com.unity.textcore](https://github.com/needle-mirror/com.unity.textcore) — TextCore 包的 mirror。

## 社区文章与工具

- [TextMeshPro Font Asset Creation & Packaging Guide](https://github.com/bbepis/XUnity.AutoTranslator/wiki/TextMeshPro-Font-Asset-Creation-&-Packaging-Guide) — 打包与创建字体资产的社区指南。
- [Optimizing TextMesh Pro Font Atlas for language localization](https://killertee.wordpress.com/2021/04/23/optimizing-workflow-textmesh-pro-font-atlas-for-language-localization/) — CJK 本地化图集拆分经验。
- [Unity Font: TMP Font Assets, Fallbacks, and Localization](https://www.transphere.com/unity-font-textmesh-pro-font-assets-fallbacks-and-localization/) — 多语言 fallback 与本地化策略。
- [GitHub - MerlinVR/Unity-MSDF-Fonts](https://github.com/MerlinVR/Unity-MSDF-Fonts) — 多通道 SDF 字体渲染的社区实现。
- [GitHub - InitialPrefabs/InitialPrefabs.Msdf](https://github.com/InitialPrefabs/InitialPrefabs.Msdf) — 另一 MSDF for Unity 方案。

## 扩展论文与技术

- Chris Green, "Improved Alpha-Tested Magnification for Vector Textures and Special Effects" — 经典 SDF 论文。
- Viktor Chlumský, "Shape Decomposition for Multi-Channel Distance Fields" — MSDF 原理论文。

## 推荐阅读顺序

1. 先读官方 SDF 文档与 Font Asset Creator，建立概念。
2. 跟着本教程第 3–5 节动手创建 asset、写 shader、读 `textInfo`。
3. 遇到具体 API 问题时查 Scripting API 与 UnityCsReference 源码。
4. 准备多语言项目时参考社区 localization 文章与 fallback 指南。
5. 想了解更前沿的字体渲染时阅读 SDF/MSDF 论文。
