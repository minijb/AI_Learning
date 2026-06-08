---
title: "C++ 内存模型 — 推荐资源"
updated: 2026-06-08
---

# C++ 内存模型 — 推荐资源

---

## 官方文档

- [cppreference — Memory model](https://en.cppreference.com/w/cpp/language/memory_model) — C++ 内存模型的标准参考
- [cppreference — Object](https://en.cppreference.com/w/cpp/language/object) — 对象、对齐、对象表示
- [cppreference — Alignment](https://en.cppreference.com/w/cpp/language/object#Alignment) — 对齐规则详解
- [cppreference — Virtual functions](https://en.cppreference.com/w/cpp/language/virtual) — 虚函数机制
- [cppreference — std::atomic](https://en.cppreference.com/w/cpp/atomic/atomic) — 原子类型与内存序

---

## 书籍

| 书名 | 作者 | 推荐理由 |
|------|------|---------|
| 《深入理解计算机系统》(CS:APP) | Randal E. Bryant 等 | 第 3 章「程序的机器级表示」是内存布局的最佳入门 |
| 《C++ Primer》 | Stanley Lippman 等 | 第 12 章「动态内存」、第 15 章「面向对象程序设计」 |
| 《Inside the C++ Object Model》 | Stanley B. Lippman | 唯一专门讲解 C++ 对象内存布局的经典 |
| 《C++ Concurrency in Action》 | Anthony Williams | 内存模型与并发编程的权威参考书 |
| 《Game Engine Architecture》 | Jason Gregory | 第 5、14 章：引擎中的内存管理与布局 |

---

## 在线文章

- [Jeff Preshing: Memory Barriers Are Like Source Control Operations](https://preshing.com/20120710/memory-barriers-are-like-source-control-operations/) — 内存序最直观的类比解释
- [Jeff Preshing: Weak vs. Strong Memory Models](https://preshing.com/20120930/weak-vs-strong-memory-models/) — 弱内存序 vs 强内存序
- [Itanium C++ ABI](https://itanium-cxx-abi.github.io/cxx-abi/abi.html) — GCC/Clang 的 ABI 规范，包含完整的虚表布局定义

---

## 视频

- [CppCon 2012: atomic Weapons by Herb Sutter](https://www.youtube.com/watch?v=A8eCGOqgvH4) — C++11 内存模型的权威讲解
- [CppCon 2016: Understanding Compiler Optimization by Chandler Carruth](https://www.youtube.com/watch?v=FnGCDLhaxKU) — 编译器如何重排代码，与内存模型的关系

---

## 工具

- [Compiler Explorer (godbolt.org)](https://godbolt.org/) — 在线查看编译器生成的汇编代码，验证内存布局假设
- [AddressSanitizer](https://clang.llvm.org/docs/AddressSanitizer.html) — 检测内存错误（use-after-free、heap-buffer-overflow 等）
- [UBSan](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html) — 检测未定义行为（未对齐访问、有符号溢出等）
- [valgrind](https://valgrind.org/) — 内存泄漏和错误检测（Linux）
