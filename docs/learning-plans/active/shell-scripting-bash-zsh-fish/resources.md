---
title: 学习资源汇总
updated: 2026-06-15
tags: [resources, shell-scripting]
---

# 学习资源

> 以下资源按类别整理，供各阶段学习时参考。每个资源附简短说明和链接。

## 官方文档

- **[GNU Bash Manual](https://www.gnu.org/software/bash/manual/)** — Bash 官方参考手册，涵盖所有内建命令、参数扩展、数组等。权威但内容庞杂，适合查阅而非通读。
- **[Zsh Documentation](https://zsh.sourceforge.io/Doc/)** — Zsh 官方文档，包含 User Guide、FAQ 和完整的选项/模块参考。
- **[Fish Shell Documentation](https://fishshell.com/docs/current/)** — Fish 官方文档，写作风格亲切易懂，新手友好。包含 Tutorial、FAQ 和交互式设计理念说明。

## 推荐书籍

- **[The Linux Command Line](https://linuxcommand.org/tlcl.php)**（William Shotts）— 经典的命令行入门书，前 10 章涵盖 Bash 基础，后续章节覆盖文本处理、正则表达式和 Shell 脚本。免费在线阅读。
- **[Bash Guide for Beginners](https://tldp.org/LDP/Bash-Beginners-Guide/html/)**（Machtelt Garrels）— TLDP 项目出品，面向零基础读者，每章附练习（带答案），是本计划的理想补充读物。
- **[Advanced Bash-Scripting Guide](https://tldp.org/LDP/abs/html/)**（Mendel Cooper）— 内容非常全面的 Bash 参考书，覆盖几乎所有 Bash 特性。适合进阶查阅，不建议零基础通读。
- **[Shell Scripting: Expert Recipes for Linux, Bash, and More](https://www.wiley.com/en-us/Shell+Scripting%3A+Expert+Recipes+for+Linux%2C+Bash%2C+and+More-p-9781118024485)**（Steve Parker）— 注重实践和最佳实践，涵盖 Bash、ksh 和通用 Unix Shell 脚本技巧。

## 在线教程

- **[freeCodeCamp — Bash Scripting Tutorial](https://www.freecodecamp.org/news/bash-scripting-tutorial-linux-shell-script-and-command-line-for-beginners/)** — 面向初学者的长篇教程，从 Hello World 到 cron 自动化，结构清晰。
- **[Ryan's Tutorials — Bash Scripting Tutorial](https://ryanstutorials.net/bash-scripting-tutorial/)** — 章节短小精悍，每节聚焦一个主题，配有大量示例和练习题。
- **[explainshell.com](https://explainshell.com/)** — 粘贴一条 Shell 命令，自动解析每个参数的含义（来自 man page）。调试和学习的利器。
- **[The Bash Hackers Wiki](https://wiki.bash-hackers.org/)** — 社区维护的 Bash 深度知识库，涵盖参数扩展、进程替换、coproc 等高级特性。

## 社区资源

- **[Stack Overflow — bash 标签](https://stackoverflow.com/questions/tagged/bash)** — 最大的 Shell 相关问答集散地，遇到问题优先搜索此处。
- **[r/bash (Reddit)](https://www.reddit.com/r/bash/)** — Bash 社区论坛，汇集脚本分享、技巧讨论和问题求助。
- **[Oh My Zsh](https://ohmyz.sh/)** — Zsh 最流行的社区配置框架，提供 300+ 插件和 150+ 主题。安装后即可获得 Git 提示、语法高亮、自动建议等增强体验。
- **[Unix & Linux Stack Exchange](https://unix.stackexchange.com/)** — 更偏系统管理场景的问答社区，适合 Shell 脚本与系统环境结合的问题。

## 工具

> [!important] 必备工具
> 以下工具建议在开始学习前安装，后续教程中将频繁使用。

- **[ShellCheck](https://www.shellcheck.net/)** — Shell 脚本静态分析工具，能检测常见错误、引用遗漏、未使用变量等。本地安装：`sudo apt install shellcheck` 或 `brew install shellcheck`。在线版可直接粘贴脚本检查。
- **[shfmt](https://github.com/mvdan/sh)** — Shell 脚本格式化工具，支持 Bash/POSIX/mksh 语法。与 ShellCheck 配合使用可同时保证脚本正确性和可读性。
- **[Bats](https://github.com/bats-core/bats-core)** — Bash 自动化测试框架，TAP 兼容。用于为 Shell 脚本编写单元测试，在实际项目中保证脚本持续可靠。
- **[Bash Debugger (bashdb)](https://bashdb.sourceforge.net/)** — Bash 专用调试器，支持断点、单步执行、变量查看。比 `bash -x` 更适合复杂脚本的调试场景。
