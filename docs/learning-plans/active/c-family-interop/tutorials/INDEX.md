---
title: C 系语言互操作与编译 — 教程目录
updated: 2026-06-18
tags: [interop, index, csharp, cpp, lua]
---

# C 系语言互操作与编译 — 教程目录

> 教程文件按知识依赖关系排序。每节含概念讲解 + 可运行代码示例 + 练习 + 参考答案 + 扩展阅读 + 常见陷阱。事实依据见 [[research-brief|研究简报]]。

## 第一阶段：互操作基础

| 序号 | 文件 | 知识点 | 预计耗时 |
|------|------|--------|---------|
| 01 | [[01-compilation-models\|01-compilation-models]] | 跨语言通信全景与三种编译模型 | 60min |
| 02 | [[02-abi-calling-conventions\|02-abi-calling-conventions]] | ABI、调用约定与符号导出 | 75min |
| 03 | [[03-memory-gc-marshalling\|03-memory-gc-marshalling]] | 内存模型、GC 与封送基础 | 75min |

## 第二阶段：C# ↔ C++

| 序号 | 文件 | 知识点 | 预计耗时 |
|------|------|--------|---------|
| 04 | [[04-pinvoke-in-practice\|04-pinvoke-in-practice]] | P/Invoke 实战（DllImport + 跨平台编译） | 90min |
| 05 | [[05-libraryimport-sourcegen\|05-libraryimport-sourcegen]] | LibraryImport 源生成器与封送优化 | 60min |
| 06 | [[06-reverse-interop\|06-reverse-interop]] | 反向互操作：原生调托管 | 75min |
| 07 | [[07-cpp-cli-and-com\|07-cpp-cli-and-com]] | C++/CLI 包装器与 COM 互操作（进阶） | 60min |

## 第三阶段：Lua ↔ C / C++

| 序号 | 文件 | 知识点 | 预计耗时 |
|------|------|--------|---------|
| 08 | [[08-lua-c-api-stack\|08-lua-c-api-stack]] | Lua C API 与栈模型 | 90min |
| 09 | [[09-cpp-lua-bindings\|09-cpp-lua-bindings]] | 现代 C++ Lua 绑定：LuaBridge 与 sol2 | 75min |
| 10 | [[10-luajit-ffi\|10-luajit-ffi]] | LuaJIT FFI：零绑定调用 C | 60min |

## 第四阶段：Lua ↔ C#

| 序号 | 文件 | 知识点 | 预计耗时 |
|------|------|--------|---------|
| 11 | [[11-lua-csharp-bridge\|11-lua-csharp-bridge]] | Lua ↔ C# 通信原理与 GC 桥（NLua / MoonSharp） | 90min |
| 12 | [[12-xlua-hotfix\|12-xlua-hotfix]] | xLua / toLua 与热更新原理 | 75min |

## 第五阶段：综合实战

| 序号 | 文件 | 知识点 | 预计耗时 |
|------|------|--------|---------|
| 13 | [[13-three-tier-project\|13-three-tier-project]] | 综合项目：C++ 核心 + C# 宿主 + Lua 脚本三层互通 | 120min |
