---
title: 学习计划：Unity 字体系统（TextMeshPro / TextCore / uGUI Text）
updated: 2026-06-17
tags: [unity, textmeshpro, textcore, font, learning-plan]
aliases: [Unity Font System]
---

# 学习计划：Unity 字体系统（TextMeshPro / TextCore / uGUI Text）

> 创建日期: 2026-06-17
> 预计总耗时: 约 18 小时（8 章 × 60–90 分钟 + 综合项目）
> 目标水平: 进阶 / 精通底层机制

---

## 学习目标

完成本计划后，你将能够：

- 解释 TrueType/OTF 字体文件、glyph、font metrics、atlas 之间的关系。
- 在 Unity 中创建并调优 TextMeshPro / UI Toolkit 的 Font Asset。
- 理解 SDF（Signed Distance Field）渲染原理，并据此解决描边、发光、缩放模糊等问题。
- 追踪 TMP_Text / TextCore 的网格生成管线，定位文字显示异常。
- 为多语言、emoji、输入框设计 fallback 与动态图集策略。
- 优化文字渲染性能，避免常见的 draw call、overdraw 和内存浪费。
- 编写自定义文字 shader / material preset，扩展视觉表现力。

---

## 前置要求

- [ ] 熟练使用 Unity Editor 和 C# 脚本。
- [ ] 了解 Shader 基础（属性、顶点/片元着色器、UV、纹理采样）。
- [ ] 有 uGUI 或 UI Toolkit 的实际使用经验（至少做过按钮、文本界面）。
- [ ] 了解基础线性代数（向量、矩阵变换）会有帮助。

---

## 学习路径

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 1 | 文字渲染基础：glyph、metrics、atlas、光栅化 | 60 min | 基础 | 无 |
| 2 | Unity 三大文字系统全景：uGUI Text、TMP、UI Toolkit/TextCore | 45 min | 基础 | 1 |
| 3 | Font Asset 创建与内部结构 | 75 min | 核心 | 1、2 |
| 4 | SDF 渲染与 Shader 特效 | 90 min | 核心 | 3 |
| 5 | 文本布局与网格生成管线 | 90 min | 核心 | 3、4 |
| 6 | 动态图集、Fallback 链与本地化 | 75 min | 进阶 | 3、5 |
| 7 | 性能优化与调试 | 60 min | 进阶 | 4、5、6 |
| 8 | 自定义 Shader、Sprite Asset 与高级主题 | 90 min | 进阶 | 4、7 |
| 9 | 综合项目：多语言游戏 HUD 文字方案 | 120 min | 实战 | 全部 |

---

## 里程碑

- [ ] 第一阶段（第 1–3 节）：能独立导入字体、生成 Font Asset，并解释 atlas 中的 glyph 数据。
- [ ] 第二阶段（第 4–5 节）：能手写 SDF  shader 效果，并读懂 TMP_Text 网格生成关键代码。
- [ ] 第三阶段（第 6–7 节）：能为 CJK/emoji 设计 fallback 链，并使用 Profiler 定位文字性能瓶颈。
- [ ] 最终项目（第 9 节）：实现一个支持中英文 + emoji 的游戏 HUD，配置合理的 static/dynamic atlas 与 fallback 策略。

---

## 推荐学习资源

详见 [[resources|学习资源汇总]]。

## 进度追踪

详见 [[progress|进度追踪]]。
