---
title: "dotnet CLI 与 C# 工程构建 — 推荐资源"
updated: 2026-06-10
tags: [dotnet, csharp, cli, resources]
---

# dotnet CLI 与 C# 工程构建 — 推荐资源

## 官方文档

- [dotnet CLI 官方文档](https://learn.microsoft.com/zh-cn/dotnet/core/tools/) — 所有 dotnet 命令的权威参考
- [.NET 项目结构 (SDK 风格项目)](https://learn.microsoft.com/zh-cn/dotnet/core/project-sdk/overview) — SDK 风格 `.csproj` 详解
- [MSBuild 官方文档](https://learn.microsoft.com/zh-cn/visualstudio/msbuild/msbuild) — MSBuild 属性和目标参考
- [NuGet 官方文档](https://learn.microsoft.com/zh-cn/nuget/) — 包管理、创建、发布
- [.NET 发布概述](https://learn.microsoft.com/zh-cn/dotnet/core/deploying/) — 部署模式对比
- [EF Core CLI 工具](https://learn.microsoft.com/zh-cn/ef/core/cli/dotnet) — `dotnet ef` 命令参考
- [.NET 工具 (dotnet tool)](https://learn.microsoft.com/zh-cn/dotnet/core/tools/global-tools) — 全局/本地工具管理

## 深入文章

- [SDK 风格项目 vs 旧式项目](https://learn.microsoft.com/zh-cn/dotnet/core/project-sdk/overview#project-file-differences) — 迁移指南
- [Directory.Build.props 共享属性](https://learn.microsoft.com/zh-cn/visualstudio/msbuild/customize-your-build#directorybuildprops-and-directorybuildtargets) — 多项目配置统一
- [多目标框架编译](https://learn.microsoft.com/zh-cn/dotnet/standard/library-guidance/cross-platform-targeting) — 跨版本类库开发
- [NuGet 包版本控制最佳实践](https://learn.microsoft.com/zh-cn/nuget/concepts/package-versioning) — 语义化版本
- [global.json SDK 版本固定](https://learn.microsoft.com/zh-cn/dotnet/core/tools/global-json) — 团队 SDK 统一

## 视频教程

- [.NET CLI 深入讲解 — Nick Chapsas (YouTube)](https://www.youtube.com/@nickchapsas) — 高质量 .NET 视频教程
- [dotnet CLI Crash Course — FreeCodeCamp](https://www.youtube.com/c/freecodecamp) — 入门级完整教程

## 开源项目参考

- [ASP.NET Core 源码](https://github.com/dotnet/aspnetcore) — 微软官方，学习大型 .NET 解决方案结构
- [Dapper 源码](https://github.com/DapperLib/Dapper) — 轻量级 ORM，学习类库打包和发布
- [Serilog 源码](https://github.com/serilog/serilog) — 日志框架，学习多目标框架项目结构

## 社区与讨论

- [.NET 官方社区](https://dotnet.microsoft.com/zh-cn/platform/community) — 官方论坛和活动
- [Stack Overflow dotnet-cli 标签](https://stackoverflow.com/questions/tagged/dotnet-cli) — 常见问题解答
- [r/dotnet (Reddit)](https://www.reddit.com/r/dotnet/) — 社区讨论

## 工具与扩展

- [dotnet-outdated](https://github.com/dotnet-outdated/dotnet-outdated) — 检查过时的 NuGet 包
- [dotnet-format](https://github.com/dotnet/format) — 代码格式化工具
- [CSharpier](https://github.com/belav/csharpier) — 代码格式化工具（opinionated）
- [dotnet-dump / dotnet-trace / dotnet-counters](https://learn.microsoft.com/zh-cn/dotnet/core/diagnostics/) — 运行时诊断工具
