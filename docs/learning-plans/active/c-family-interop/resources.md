---
title: 学习资源：C 系语言互操作与编译
updated: 2026-06-18
tags: [interop, resources, learning-plan]
---

# 学习资源：C 系语言互操作与编译

## 官方文档

- [.NET Native interoperability](https://learn.microsoft.com/dotnet/standard/native-interop/) — P/Invoke、指针、类型封送总览
- [P/Invoke source generation (LibraryImport)](https://learn.microsoft.com/dotnet/standard/native-interop/pinvoke-source-generation)
- [NativeAOT deployment](https://learn.microsoft.com/dotnet/core/deploying/native-aot/) — 含 `[UnmanagedCallersOnly]` 导出
- [C++/CLI migration](https://learn.microsoft.com/cpp/dotnet/dotnet-programming-with-cpp-cli-visual-cpp)
- [Marshalling between .NET and C++](https://learn.microsoft.com/dotnet/standard/native-interop/customize-parameter-marshalling)
- [Lua 5.4 Reference Manual](https://www.lua.org/manual/5.4/manual.html)
- [LuaJIT FFI documentation](https://luajit.org/ext_ffi.html)
- [LuaBridge Reference Manual](https://vinniefalco.github.io/LuaBridge/Manual.html)
- [sol2 documentation](https://sol2.readthedocs.io/)

## 推荐书籍与深度资料

- 《Expert .NET 2.0 IL Assembler》— 理解 IL 与互操作 stub 的底层
- 《Lua 程序设计（第 4 版）》Roberto Ierusalimschy — Lua 官方作者，含 C API 章节
- 《C++ ABI》Itanium C++ ABI 规范 — [itanium-cxx-abi.github.io](https://itanium-cxx-abi.github.io/cxx-abi/abi.html)

## 在线教程与文章

- [.NET 原生代码互操作性（中文）](https://segmentfault.com/a/1190000046871744)
- [C# and C++ Interop using P/Invoke](https://www.vorstieg.eu/blog/platform-invoke)
- [C++ library in a .NET/C# project with CMake](https://decovar.dev/blog/2025/11/11/cpp-library-in-csharp/)
- [C# Architecture Insights: Native Interop](https://stevenstuartm.com/study-guides/dotnet/c-sharp/advanced/native-interop.html)
- [Why a C++/CLI Wrapper Is Often the Best Way](https://comcomponent.com/en/blog/2026/03/07/000-cpp-cli-wrapper-for-native-dlls/)
- [Using Lua with C++ (and C)](https://edw.is/using-lua-with-cpp/)
- [A Lua C API Cheat Sheet](https://www.codingwiththomas.com/blog/a-lua-c-api-cheat-sheet)
- [Comprehensive Guide to ABI in C and C++](https://gist.github.com/MangaD/506a0f3273724ef3af26b8c085accdcb)

## 社区资源与讨论

- [dotnet/runtime Discussion #84246 — interop of C# and C++/CLI in .NET Core](https://github.com/dotnet/runtime/discussions/84246)
- [Stack Overflow: C++ and C# interoperability: P/Invoke vs C++/CLI](https://stackoverflow.com/questions/3150477/c-and-c-sharp-interoperability-p-invoke-vs-c-cli)
- [Stack Overflow: P/Invoke Pinning](https://manski.net/articles/csharp-dotnet/pinvoke-tutorial/part-4--pinning)

## 开源项目（对照学习）

- [NLua](https://github.com/NLua/NLua) — C# 对 Lua C API 的封装，读源码理解栈桥
- [MoonSharp](https://github.com/moonsharp-devs/moonsharp) — 纯 C# Lua 解释器实现
- [xLua (Tencent)](https://github.com/Tencent/xLua) — Unity Lua 热更新，含 Wrap 代码生成与 Hotfix IL 注入
- [sol2](https://github.com/ThePhD/sol2) — 现代 C++ Lua 绑定
- [LuaBridge](https://github.com/vinniefalco/LuaBridge) — 轻量 C++ Lua 绑定
- [LuaJIT](https://luajit.org/) — 含 FFI 与 JIT 的 Lua 实现

## 构建工具

- [CMake](https://cmake.org/) — 跨平台 C++/Lua 构建的事实标准
- [.NET SDK](https://dotnet.microsoft.com/) — C# 编译、P/Invoke、LibraryImport 源生成器
- [dumpbin](https://learn.microsoft.com/cpp/build/reference/dumpbin-reference) / [nm](https://man7.org/linux/man-pages/man1/nm.1.html) — 符号导出检查工具

## 相关深度笔记

- [[csharp-cpp-stream-deep-dive|C# Stream 与 C++ iostream 深度剖析]] — 跨语言抽象对比
- [[raii-complete-analysis|RAII 完整分析]] — 理解原生侧资源管理
- [[stack-unwinding|栈展开]] — 理解为什么异常/longjmp 不能跨边界
