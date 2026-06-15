---
title: 学习计划 - Shell 脚本编程：Bash、Zsh 与 Fish
updated: 2026-06-15
tags: [shell, bash, zsh, fish, scripting, linux]
---

# 学习计划: Shell 脚本编程：Bash、Zsh 与 Fish

> 创建日期: 2026-06-15
> 预计总耗时: 10-12 小时
> 目标水平: 入门到进阶

---

## 学习目标

完成本计划后，你将能够：

- 编写可运行的 Bash 脚本完成文件处理、系统自动化等常见任务
- 使用 `set -euo pipefail`、`trap`、引号等最佳实践写出健壮的脚本
- 理解 Bash、Zsh、Fish 三者的核心语法差异和适用场景
- 根据目标环境（POSIX 兼容性、macOS、交互体验）选择合适的 shell
- 使用 ShellCheck 等工具检查和改进脚本质量

## 前置要求

- [ ] 熟悉基本命令行操作（`cd`、`ls`、`cat`、`mkdir` 等）
- [ ] 有一个可运行的 Linux / macOS / Windows WSL 环境
- [ ] 已安装 Bash（默认都有），可选安装 Zsh 和 Fish

## 学习路径

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 1 | [[01-bash-first-script|Bash 第一个脚本与运行方式]] | 45min | 基础 | 无 |
| 2 | [[02-bash-variables-io|Bash 变量、输入输出与引号]] | 60min | 基础 | 1 |
| 3 | [[03-bash-conditions|Bash 条件判断与流程控制]] | 60min | 基础 | 2 |
| 4 | [[04-bash-loops-functions|Bash 循环与函数]] | 60min | 基础 | 3 |
| 5 | [[05-bash-arrays-strings-files|Bash 数组、字符串与文件操作]] | 60min | 进阶 | 4 |
| 6 | [[06-bash-best-practices|Bash 最佳实践：严格模式、错误处理与 ShellCheck]] | 60min | 进阶 | 2-5 |
| 7 | [[07-bash-project-batch-renamer|Bash 实战：批量文件重命名工具]] | 90min | 项目 | 1-6 |
| 8 | [[08-zsh-scripting|Zsh 脚本：Bash 超集与增强特性]] | 60min | 进阶 | 1-6 |
| 9 | [[09-fish-scripting|Fish 脚本：非 POSIX 语法与交互友好设计]] | 60min | 进阶 | 1-6 |
| 10 | [[10-shell-comparison-selection|Bash / Zsh / Fish 对比与选型]] | 45min | 综合 | 1-9 |

## 里程碑

- [ ] 第一阶段（第 `#1`–`#4` 节）: 完成 Bash 基础语法学习，能编写简单的 Bash 自动化脚本处理日常任务
- [ ] 第二阶段（第 `#5`–`#7` 节）: 掌握 Bash 进阶特性和最佳实践，能够编写健壮、可维护的脚本，并完成一个批量文件重命名实战项目
- [ ] 第三阶段（第 `#8`–`#10` 节）: 了解 Zsh 和 Fish 的核心特性与语法差异，能够根据实际场景在三种 shell 之间做出合理的技术选型
