---
title: Mermaid 学习资源汇总
updated: 2026-06-11
tags: [mermaid, resources]
---

# Mermaid 学习资源汇总

## 官方资源

| 资源 | 链接 | 说明 |
|------|------|------|
| 官方文档 | https://mermaid.js.org/ | 最权威的语法参考 |
| Live Editor | https://mermaid.live | 在线实时编辑 + 预览 + 导出 |
| GitHub 仓库 | https://github.com/mermaid-js/mermaid | 源码、Issues、讨论 |
| Mermaid Chart | https://www.mermaidchart.com/ | 官方团队协作平台（付费） |

## 平台集成

| 平台 | 说明 |
|------|------|
| Obsidian | 原生渲染 ` ```mermaid ` 代码块，阅读模式可见 |
| GitHub | Issues / PR / `.md` 文件中原生渲染 |
| GitLab | 同 GitHub |
| Notion | `/mermaid` 命令插入 Mermaid 块 |
| VS Code | 扩展 "Markdown Preview Mermaid Support" |
| Typora | 原生支持 |
| Confluence | 需安装 Mermaid 插件 |
| JetBrains | 需安装 "Mermaid" 插件 |

## 学习社区

- [Mermaid.js 官方博客](https://mermaid.js.org/blog/)：版本发布、使用技巧
- [Stack Overflow — mermaid 标签](https://stackoverflow.com/questions/tagged/mermaid)：常见问题解答
- [Mermaid Discord](https://discord.gg/AgrbSrBer3)：社区讨论

## 进阶参考

- [Mermaid 主题配置](https://mermaid.js.org/config/theming.html)：自定义主题变量
- [Mermaid 配置大全](https://mermaid.js.org/config/configuration.html)：所有可配置项
- [Mermaid API 文档](https://mermaid.js.org/config/usage.html)：通过 JS API 动态生成图表

## 同类工具对比

| 工具 | 风格 | 适用场景 |
|------|------|---------|
| Mermaid | 文本 DSL | Markdown 内嵌，Git 友好 |
| PlantUML | 文本 DSL | UML 图更全面，需 Java 运行时 |
| Graphviz (DOT) | 文本 DSL | 图论布局，自动排布算法强 |
| draw.io | 拖拽 | 一次性图表，非版本控制 |
| Excalidraw | 手绘风格 | 白板讨论，非正式图表 |

## 推荐学习路径

1. 先通读本计划 [[mermaid-syntax 01 - 基础与快速上手|第 1 节]]，在 [Mermaid Live Editor](https://mermaid.live) 上手
2. 按需学习对应图表类型（不需要全部学完才开始用）
3. 遇到渲染问题时，在 Live Editor 中调试——它的错误提示比 Obsidian 更友好
4. 参考 [官方示例库](https://mermaid.js.org/syntax/examples.html) 寻找灵感
