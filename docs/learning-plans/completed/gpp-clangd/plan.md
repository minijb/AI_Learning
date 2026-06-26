---
title: 学习计划 - g++ 与 clangd 命令
updated: 2026-06-26
tags: [学习计划, cpp, 编译器, clangd, 工具链]
aliases: [gpp-clangd 计划]
---

# 学习计划: g++ 与 clangd 命令

> [!info] 计划概览
> 创建日期: 2026-06-26
> 预计总耗时: 8-10 小时
> 目标水平: 入门到熟练（掌握 C++ 命令行工具链）

---

## 学习目标

完成本计划后，你能：

- 在 Windows / macOS / Linux 上独立安装并配置 `g++` 编译器与 `clangd` 语言服务器
- 用 `g++` 完整编译 C++ 项目：单文件、多文件、分离编译与链接
- 理解 `g++` 的编译四阶段，能按需停留在任意阶段产出中间文件
- 正确使用 `-std`、`-Wall`、`-Wextra`、`-O`、`-g` 等核心选项
- 用 `clangd` 配合编辑器获得精确的代码补全、跳转定义、实时诊断
- 为任意项目生成 `compile_commands.json` 或 `compile_flags.txt` 喂给 clangd

## 前置要求

- 基本的命令行操作能力（`cd`、路径、环境变量）
- 了解 C++ 基本语法（能看懂简单程序即可，无需精通）

## 学习路径

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 01 | [[01-environment-setup\|环境搭建]] | 45min | 基础 | 无 |
| 02 | [[02-gpp-basic-compilation\|g++ 基础编译]] | 45min | 基础 | 01 |
| 03 | [[03-gpp-compilation-stages\|g++ 编译四阶段]] | 60min | 核心 | 02 |
| 04 | [[04-gpp-standards-warnings\|g++ 标准与警告]] | 50min | 核心 | 02 |
| 05 | [[05-gpp-multiple-files\|g++ 多文件与头文件]] | 60min | 核心 | 03 |
| 06 | [[06-gpp-optimization-debugging\|g++ 优化与调试]] | 50min | 进阶 | 04 |
| 07 | [[07-clangd-fundamentals\|clangd 环境与核心概念]] | 50min | 基础 | 01 |
| 08 | [[08-compile-commands\|生成 compile_commands.json]] | 60min | 核心 | 07 |
| 09 | [[09-clangd-editor-integration\|clangd 编辑器集成与配置]] | 60min | 核心 | 08 |

## 里程碑

- [ ] 第一阶段（g++ 基础）：完成 `01`-`04`，能用 g++ 独立编译并理解编译过程
- [ ] 第二阶段（g++ 进阶）：完成 `05`-`06`，能编译多文件项目并调试优化
- [ ] 第三阶段（clangd）：完成 `07`-`09`，让编辑器获得 IDE 级 C++ 支持

> [!tip] 学习建议
> - 每节都动手敲命令，不要只看不练——工具类知识全靠肌肉记忆
> - g++ 部分（`01`-`06`）是基础，clangd 部分（`07`-`09`）依赖对编译命令的理解
> - clangd 的核心是「告诉它怎么编译」，所以 [[08-compile-commands]] 是关键节点
