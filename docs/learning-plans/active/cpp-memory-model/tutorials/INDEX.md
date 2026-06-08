---
title: "C++ 内存模型 — 教程索引"
updated: 2026-06-08
---

# C++ 内存模型 — 教程索引

> 本目录包含 8 节教程，覆盖从字节级内存表示到 C++11 内存模型的完整学习路径。
> 每节包含概念讲解、可运行代码示例、练习和常见陷阱。

---

| 序号 | 文件名 | 知识点 | 预计耗时 | 前置 |
|------|--------|--------|---------|------|
| 1 | [[01-byte-word-and-memory-basics]] | 字节、字、地址与整数内存表示 | 45min | 无 |
| 2 | [[02-struct-and-array-layout]] | `struct` 与数组的内存布局 | 50min | `#1` |
| 3 | [[03-class-memory-layout]] | 类对象的内存模型 | 55min | `#2` |
| 4 | [[04-virtual-functions-and-inheritance]] | 继承、虚函数与虚继承 | 60min | `#3` |
| 5 | [[05-new-delete-memory-lifecycle]] | `new`/`delete` 与内存生命周期 | 50min | `#3` |
| 6 | [[06-placement-new-and-alignment]] | Placement New 与对齐存储 | 50min | `#5` |
| 7 | [[07-low-level-memory-operations]] | 底层内存操作（`memcpy` 等） | 45min | `#2` |
| 8 | [[08-cpp-memory-model-and-atomics]] | C++ 内存模型与原子操作 | 60min | `#7` |

---

## 学习建议

- **基础路径（必修）**：`#1` → `#2` → `#3` → `#4` → `#5`
- **引擎开发路径**：在上述基础上加 `#6`（Arena 分配器）和 `#7`（序列化/缓冲操作）
- **并发编程路径**：完成基础后学习 `#8`，配合《C++ Concurrency in Action》

## 关联深度探索

- [[../../deep-dives/placement-new-aligned-allocation|Placement New 与对齐分配 深度剖析]]
- [[../../deep-dives/cpp-mem-operations|C++ mem 系列操作 深度剖析]]
- [[../../deep-dives/raii-complete-analysis|RAII 深度剖析]]
- [[../../deep-dives/cpp-special-member-functions|C++ 特殊成员函数]]
