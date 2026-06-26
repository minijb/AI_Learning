---
title: 学习资源 - g++ 与 clangd 命令
updated: 2026-06-26
tags: [学习资源, cpp, 编译器, clangd]
---

# 学习资源: g++ 与 clangd 命令

## 官方文档

- [GCC 在线手册 - 优化选项](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html)
- [GCC 在线手册 - 警告选项](https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html)
- [GCC 在线手册 - 预处理选项](https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html)
- [clangd 官方配置文档](https://clangd.llvm.org/config) — `.clangd` / `config.yaml` 全部 schema
- [clangd 官方网站](https://clangd.llvm.org/)
- [LLVM releases（clangd 预编译二进制）](https://github.com/llvm/llvm-project/releases)
- [MSYS2 官网](https://www.msys2.org/)
- [VS Code clangd 扩展](https://marketplace.visualstudio.com/items?itemName=llvm-vs-code-extensions.vscode-clangd)

## 关键文章

- [JSON Compilation Database with non-cmake projects (2025)](https://rsadowski.de/posts/2025/json-compilation-db-non-cmake-projects/) — Bear 生成 compile_commands.json 实战
- [VS Code: Using GCC with MinGW](https://code.visualstudio.com/docs/cpp/config-mingw) — Windows 上 g++ + GDB 官方教程
- [compile_commands.json 生成方式汇总](https://blog.bkryza.com/posts/compile-commands-json-gallery/) — 多种构建系统的生成方法

## 工具

- [Bear](https://github.com/rizsotto/Bear) — 为非 CMake 项目生成 compile_commands.json
- [CMake](https://cmake.org/) — `CMAKE_EXPORT_COMPILE_COMMANDS` 生成编译数据库
- [GDB: GNU Debugger](https://www.gnu.org/software/gdb/) — 配合 `g++ -g` 进行调试

## 社区资源

- [LLVM Discussion Forums (clangd)](https://discourse.llvm.org/c/clangd/) — clangd 官方讨论区
- [gcc-help 邮件列表](https://gcc.gnu.org/lists.html)

## 进阶方向

学完本计划后，可继续深入：

- **构建系统**：学习 CMake / Makefile / Ninja，自动化 g++ 编译流程
- **调试进阶**：GDB 命令详解、`-fsanitize=address` / `-fsanitize=undefined` 深入
- **静态分析**：clang-tidy 检查规则、GCC `-fanalyzer`
- **链接深入**：静态库 / 动态库、符号可见性、`-Wl` 链接器选项
