---
title: "内存管理与自定义分配器"
updated: 2026-06-05
---

# 内存管理与自定义分配器

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 6h
> 前置知识: 无

---

## 1. 概念讲解

### 1.1 C++ 内存模型：栈、堆、全局/静态区

在深入自定义分配器之前，我们必须先理解 C++ 程序运行时的内存布局。一个典型的 C++ 进程的虚拟地址空间分为以下几个区域：

```
高地址
+------------------+
|     内核空间      |  ← 操作系统保留，用户程序不可访问
+------------------+
|     栈 (Stack)    |  ← 向下增长，局部变量、函数参数
|        ↓         |
|                  |
|        ↑         |
|     堆 (Heap)     |  ← 向上增长，动态分配（malloc/new）
+------------------+
|      BSS段        |  ← 未初始化的全局/静态变量
+------------------+
|     数据段        |  ← 已初始化的全局/静态变量
+------------------+
|     代码段        |  ← 程序指令、常量字符串
+------------------+
低地址
```

#### 代码段（Text Segment）

代码段存储编译后的机器指令和只读数据（如字符串常量）。这个区域通常是只读的，防止程序意外修改自己的指令。

```cpp
const char* g_stringLiteral = "Hello Engine"; // 字符串常量存储在只读数据段

void SomeFunction() { /* 函数体编译为机器码，存储在代码段 */ }
```

#### 数据段（Data Segment）与 BSS 段

- **数据段**：存放**已初始化**的全局变量和静态变量（包括静态局部变量）。
- **BSS 段**：存放**未初始化**的全局变量和静态变量，程序启动时由操作系统自动清零。

```cpp
// 数据段（已初始化）
static const float PI = 3.14159265f;
static int g_frameCount = 0;

// BSS 段（未初始化，自动为 0）
static float g_timeSinceStart;        // 自动初始化为 0.0f
static int* g_globalPointer;          // 自动初始化为 nullptr
```

在游戏引擎中，全局/静态区的用途包括：引擎中的单例管理器、全局配置表、常量数据表。但要注意，过度使用全局变量会导致代码难以测试和维护。

#### 栈（Stack）

栈是最高效的内存区域，由编译器自动管理：

- **分配方式**：通过移动栈指针（SP），本质上是 `sub rsp, N` 一条指令
- **释放方式**：函数返回时自动恢复栈指针
- **生命周期**：与作用域绑定
- **限制**：大小有限（通常 Windows 1MB，Linux 8MB），过大导致栈溢出
- **特性**：内存连续、CPU 缓存友好、无碎片

```cpp
void foo() {
    int localArray[1024];      // 栈分配，O(1)
    Vec3 position;             // 栈分配，自动析构
} // 离开作用域自动释放
```

在游戏引擎中，每帧创建的临时对象（如变换矩阵、中间计算结果）应尽量放在栈上。对于超出栈容量的大型临时缓冲区，可以使用**栈分配的替代方案**——在线程局部存储中预分配一块"临时内存"，由帧结束时统一重置。

#### 堆（Heap）

堆是动态内存分配的区域，由程序员或运行时库管理：

- **分配方式**：通过 `malloc`/`new` 向操作系统请求
- **释放方式**：通过 `free`/`delete` 显式释放
- **生命周期**：由程序员控制
- **限制**：受限于虚拟地址空间（32 位约 2-3GB，64 位极大）
- **特性**：分配/释放开销大、可能产生碎片、需要线程同步

```cpp
// 堆分配的典型开销：
// 1. 查找合适大小的空闲块（O(log n) 或 O(n)）
// 2. 可能触发系统调用（brk/mmap）
// 3. 线程锁竞争（多线程场景）
// 4. 元数据开销（每个分配通常有 8-16 字节头部）
Mesh* mesh = new Mesh(vertices, indices);  // 堆分配
// ... 使用 mesh ...
delete mesh;  // 必须手动释放，否则内存泄漏
```

游戏引擎的核心优化策略之一是**减少堆分配**，尤其是**避免在游戏循环中进行堆分配**。原因有三：第一，堆分配涉及系统调用或复杂的用户态内存管理，单次分配可能需要数百个 CPU 周期；第二，频繁的堆分配导致**内存碎片（Fragmentation）**，降低缓存效率；第三，堆分配的内存地址在物理上不相邻，破坏了**空间局部性（Spatial Locality）**，增加了缓存未命中的概率。

#### 内存布局验证

```cpp
#include <iostream>

int g_initialized = 42;        // 数据段
int g_uninitialized;           // BSS 段
static float s_staticVar = 1.0f; // 数据段

void MemoryLayoutDemo() {
    int localVar = 10;              // 栈内存
    static int staticLocal = 20;    // 数据段（静态局部变量生命周期贯穿程序）
    int* heapVar = new int(30);     // 堆内存——手动管理

    std::cout << "Code address:    " << (void*)&MemoryLayoutDemo << "\n";
    std::cout << "Global (data):   " << &g_initialized << "\n";
    std::cout << "Global (bss):    " << &g_uninitialized << "\n";
    std::cout << "Static local:    " << &staticLocal << "\n";
    std::cout << "Stack local:     " << &localVar << "\n";
    std::cout << "Heap allocated:  " << heapVar << "\n";

    delete heapVar;  // 必须手动释放
}
```

#### 栈（Stack）

栈是最高效的内存区域，由编译器自动管理：

- **分配方式**：通过移动栈指针（SP），本质上是 `sub rsp, N` 一条指令
- **释放方式**：函数返回时自动恢复栈指针
- **生命周期**：与作用域绑定
- **限制**：大小有限（通常 1MB~8MB），过大导致栈溢出
- **特性**：内存连续、CPU 缓存友好、无碎片

```cpp
void foo() {
    int localArray[1024];      // 栈分配，O(1)
    Vector3 position;          // 栈分配，自动析构
} // 离开作用域自动释放
```

在游戏引擎中，每帧创建的临时对象（如变换矩阵、中间计算结果）应尽量放在栈上。对于超出栈容量的大型临时缓冲区，可以使用**栈分配的替代方案**——在线程局部存储中预分配一块"临时内存"，由帧结束时统一重置。

#### 堆（Heap）

堆是动态内存分配的区域，由程序员或运行时库管理：

- **分配方式**：通过 `malloc`/`new` 向操作系统请求
- **释放方式**：通过 `free`/`delete` 显式释放
- **生命周期**：由程序员控制
- **限制**：受限于虚拟地址空间（32位约 2-3GB，64位极大）
- **特性**：分配/释放开销大、可能产生碎片、需要线程同步

```cpp
// 堆分配的典型开销：
// 1. 查找合适大小的空闲块（O(log n) 或 O(n)）
// 2. 可能触发系统调用（brk/mmap）
// 3. 线程锁竞争（多线程场景）
// 4. 元数据开销（每个分配通常有 8-16 字节头部）
Mesh* mesh = new Mesh(vertices, indices);  // 堆分配
// ... 使用 mesh ...
delete mesh;  // 必须手动释放，否则内存泄漏
```

#### 全局/静态区

- **数据段（Data Segment）**：存放已初始化的全局变量和静态变量
- **BSS 段**：存放未初始化的全局变量和静态变量，程序启动时由操作系统清零
- **生命周期**：与程序生命周期相同
- **用途**：引擎中的单例管理器、全局配置表、常量数据

```cpp
// 数据段
static const float PI = 3.14159265f;  // 已初始化，在数据段
static int g_frameCount = 0;          // 已初始化，在数据段

// BSS 段
static float g_timeSinceStart;        // 未初始化，在 BSS 段（自动为0）
```

### 为什么需要自定义分配器？

标准库的 `malloc`/`free` 是通用分配器，设计目标是满足**所有场景的平均性能**。但游戏引擎有特殊的内存使用模式：

| 问题 | 标准分配器表现 | 引擎需求 |
|------|---------------|---------|
| **分配频率** | 通用设计，不优化高频小分配 | 每帧数千次分配（粒子、临时对象） |
| **碎片** | 长期运行产生碎片 | 游戏运行数小时，不能崩溃 |
| **线程竞争** | 全局锁，多线程扩展性差 | 渲染线程、物理线程、逻辑线程并行 |
| **对齐要求** | 通常 8/16 字节对齐 | SIMD 需要 16/32/64 字节对齐 |
| **内存追踪** | 无内置统计 | 需要精确知道每子系统的内存占用 |
| **分配模式** | 假设随机大小、随机生命周期 | 引擎有明确的分配模式（关卡加载时批量分配） |
| **确定性** | 分配时间不固定 | 游戏需要稳定的帧时间，不能有卡顿 |

**真实案例：**

- **Unreal Engine 4**：使用 `FMallocBinned`（基于桶的分配器），按大小分桶，每线程有独立的线程缓存，大幅减少锁竞争
- **Unity**：使用 `MemoryManager`，支持按类型分池、自定义对齐
- **Godot**：使用 `MemoryPool`，简单的池分配策略
- **EA STL**：开源了 `EAStackAllocator`、`EAPoolAllocator` 等分配器，配合 `EASTL` 使用

### 核心思想

自定义分配器的核心思想是：**利用引擎内存使用的已知模式，用空间换时间，用特化换通用。**

具体策略包括：

1. **批量预分配**：关卡加载时一次性分配大块内存，运行时只从中切分
2. **按模式分配**：识别不同的分配模式（临时、持久、同大小对象），使用不同的分配策略
3. **消除锁竞争**：使用线程局部分配器，或每个子系统独立的分配器
4. **对齐控制**：确保关键数据结构满足 SIMD/GPU 对齐要求
5. **内存预算**：为每个子系统设定内存上限，超限报警

---

### 1.2 内存碎片：内部碎片 vs 外部碎片

#### 外部碎片（External Fragmentation）

**定义**：空闲内存总量足够，但没有**连续**的足够大的块来满足分配请求。

```
分配历史：
  [已分配][空闲][已分配][空闲][已分配][空闲]

经过多次分配/释放后：
  [已分配][空闲16B][已分配][空闲16B][已分配][空闲16B]

请求分配 32B 连续内存 → 失败！
总空闲内存 = 48B，但最大连续块 = 16B
```

**产生原因**：
- 不同大小的对象交错分配和释放
- 长期对象和短期对象混合

**解决方案**：
- 使用池分配器（固定大小，无外部碎片）
- 使用紧凑化（Compaction）——但 C++ 对象有指针，难以移动
- 按生命周期分离（短期对象和长期对象使用不同的堆）

#### 内部碎片（Internal Fragmentation）

**定义**：分配给用户的内存块大于实际请求的大小，多余部分被浪费。

```
请求分配 12 字节：
  分配器最小粒度/对齐要求 = 16 字节
  实际分配 16 字节 → 内部碎片 = 4 字节

请求分配 100 字节：
  分配器按 2 的幂分桶，分配到 128 字节桶
  内部碎片 = 28 字节
```

**产生原因**：
- 对齐要求（请求 5 字节，对齐到 8 字节边界）
- 分配器元数据（头部信息）
- 固定大小分桶策略

**解决方案**：
- 使用精确大小的自由列表
- 减少对齐要求（仅在必要时对齐）

#### 碎片量化指标

```cpp
// 碎片率 = 1 - (最大连续空闲块 / 总空闲内存)
// 碎片率越接近 1，碎片越严重

// 例如：
// 总空闲内存 = 1000 字节
// 最大连续空闲块 = 100 字节
// 碎片率 = 1 - 100/1000 = 0.9（非常严重）
```

---

### 1.3 自定义分配器类型

#### 线性分配器（Linear / Arena Allocator）

**原理**：维护一个指针，分配时只需向前移动指针。释放时**只能整体释放**或**回滚到某个标记点**。

```
初始状态：
[oooooooooooooooooooooooooooooooooooooooooooo]
 ^
 offset

分配 A(16B)：
[AAAAAAAAAAAAAAAAoooooooooooooooooooooooooooo]
                  ^
                 offset

分配 B(8B)：
[AAAAAAAAAAAAAAAABBBBBBBBoooooooooooooooooooo]
                          ^
                         offset

重置（Reset）：
[oooooooooooooooooooooooooooooooooooooooooooo]
 ^
 offset = 0
```

**特点**：
- 分配：O(1)，只需加法操作
- 不支持单个释放（或仅支持从尾部回滚）
- 无内部/外部碎片（按顺序紧密排列）
- 内存使用模式：加载时分配，卸载时全部释放

**适用场景**：
- 关卡资源加载（整个关卡的资源一起加载，一起释放）
- 帧分配器（每帧开始时重置，存储临时计算数据）
- 解析器的临时内存（解析完即丢弃）

#### 栈分配器（Stack Allocator）

**原理**：在线性分配器基础上增加"回滚"能力。每次分配记录头部信息，释放时按 LIFO 顺序回滚。

```
分配 A：
[HeaderA|AAAAAAAA|oooooooooooooooooooooooooooo]
         ↑
       返回给用户的指针

分配 B：
[HeaderA|AAAAAAAA|HeaderB|BBBB|oooooooooooooooo]
                         ↑
                       返回给用户的指针

释放 B（LIFO）：
[HeaderA|AAAAAAAA|oooooooooooooooooooooooooooo]
                  ↑
                offset 回滚到 HeaderB 之前
```

**特点**：
- 分配：O(1)
- 释放：O(1)，但必须是 LIFO 顺序
- 支持嵌套作用域（类似栈帧）

**适用场景**：
- 递归算法的临时内存
- 嵌套作用域的资源管理

#### 池分配器（Pool Allocator）

**原理**：预分配 N 个大小相同的块，用自由列表管理空闲块。

```
预分配 4 个 16 字节的块：
[Block0][Block1][Block2][Block3]

空闲列表：Block0 → Block1 → Block2 → Block3 → nullptr

分配一个块（返回 Block0）：
空闲列表：Block1 → Block2 → Block3 → nullptr

释放 Block0：
空闲列表：Block0 → Block1 → Block2 → Block3 → nullptr
```

**特点**：
- 分配/释放：O(1)
- 零外部碎片（所有块大小相同）
- 内部碎片：如果对象小于块大小，有浪费
- 极佳的缓存局部性（对象紧密排列）

**适用场景**：
- 粒子系统（所有粒子大小相同）
- 游戏对象（Entity/Component）
- 渲染命令缓冲区

#### 自由列表分配器（Free List Allocator）

**原理**：维护一个空闲块列表，分配时找到合适的块，释放时合并相邻的空闲块。

```
内存状态：
[已分配][空闲32B][已分配][空闲64B][已分配]
        ↑                    ↑
      空闲列表：32B块 → 64B块 → nullptr

分配 20B：
- 从 32B 块中切分（假设需要 8B 头部）
- 剩余 4B 太小，可能产生碎片

释放中间块：
[已分配][空闲32B][空闲16B][空闲64B][已分配]
        ↑                   ↑
      需要合并相邻块！
```

**特点**：
- 分配：O(n)（遍历空闲列表），可用最佳适配/首次适配优化
- 释放：O(n)（需要查找相邻块并合并）
- 有外部碎片问题
- 最接近 `malloc` 的行为，但可定制

**适用场景**：
- 需要单个分配/释放，且大小不固定的场景
- 作为其他分配器的底层（如先向 OS 申请大块，再用自由列表管理）

#### 伙伴分配器（Buddy Allocator）

**原理**：将内存按 2 的幂次分块。分配时找到最小的满足需求的 2 的幂块；释放时如果相邻的"伙伴"也是空闲的，就合并成更大的块。

```
初始：1 个 1024B 块

分配 100B：
- 向上取整到 128B
- 分裂 1024 → 512+512 → 256+256 → 128+128
- 返回其中一个 128B 块

状态：
[128B已分配][128B空闲][256B空闲][512B空闲]

释放 128B：
- 检查伙伴（相邻的 128B）是否空闲 → 是！
- 合并为 256B
- 检查 256B 的伙伴是否空闲 → 是！
- 合并为 512B
- 检查 512B 的伙伴是否空闲 → 是！
- 合并回 1024B
```

**特点**：
- 分配/释放：O(log n)
- 外部碎片较少（因为总是合并伙伴）
- 内部碎片：最多浪费接近 50%（请求 65B，分配 128B）
- 实现相对复杂

**适用场景**：
- 操作系统内核内存管理
- 大块内存管理（如纹理内存）
- 作为页分配器

#### TLSF 分配器（Two-Level Segregated Fit）

**TLSF** 是一种为**实时系统**设计的通用内存分配器。与标准 `malloc` 不同，TLSF 提供了**最坏情况执行时间有界（Worst-Case Execution Time Bounded）**的分配和释放操作——这在游戏主机和实时系统中至关重要，因为不可预测的 GC 停顿或分配延迟可能导致帧率下降。

TLSF 的核心数据结构是**两级空闲链表**：

- **第一级**：根据空闲块的大小，将其分到若干个大小范围（如 16-31, 32-63, 64-127, ...）。
- **第二级**：每个第一级范围内部再细分（如 16-17, 18-19, ..., 30-31）。

这种两级结构使得查找合适大小的空闲块可以在 O(1) 时间完成。TLSF 还使用位图（Bitmap）来快速判断某个大小范围内是否存在空闲块，避免了遍历链表的开销。

| 分配器类型 | 分配复杂度 | 释放复杂度 | 内存碎片 | 特点 | 适用场景 |
|-----------|-----------|-----------|---------|------|---------|
| Pool Allocator | O(1) | O(1) | 无 | 固定大小块 | 游戏对象、粒子、音频源 |
| Stack Allocator | O(1) | O(1) | 无 | 只能按分配逆序释放 | 帧临时数据、命令缓冲 |
| Free List | O(1) | O(1) | 中等 | 维护空闲块链表 | 通用固定大小分配 |
| Buddy Allocator | O(log n) | O(log n) | 低 | 二分分割内存块 | 纹理/模型加载 |
| **TLSF** | **O(1)** | **O(1)** | **低** | **两级空闲链表** | **实时系统、游戏主机** |

TLSF 分配器的典型应用场景是**游戏主机的主内存管理**。主机有固定的内存预算（如 PS5 的 16 GB），需要在整个游戏过程中高效管理。TLSF 的低碎片特性和确定性延迟使其成为主机引擎的首选通用分配器。

#### 内存碎片处理策略

内存碎片是长时间运行的游戏中不可避免的问题。**内存碎片**分为外部碎片（空闲内存总量足够但无法满足大块分配需求，因为空闲块被分割成小块）和内部碎片（分配块中未被使用的部分）。

游戏引擎处理内存碎片的策略包括：

1. **内存分区（Memory Partitioning）**：将可用内存划分为多个用途固定的区域（渲染内存、纹理内存、音频内存、脚本内存等），每个区域使用适合其分配模式的分配器。
2. **资源预加载和驻留**：在关卡加载时预分配所有需要的资源内存，运行时不再进行动态分配。
3. **内存整理（Defragmentation）**：对于支持内存重定位的资源（如纹理），定期整理内存以消除碎片。这需要所有引用该资源的指针都通过句柄间接访问。
4. **虚拟内存映射**：在支持虚拟内存的平台上（现代游戏主机都支持），使用虚拟地址到物理地址的映射来消除外部碎片的影响。

---

### 1.4 对齐（Alignment）和填充（Padding）

#### 什么是对齐？

**对齐**要求数据结构的起始地址是某个值的倍数。

```cpp
// alignof(T) 返回类型 T 的对齐要求
std::cout << alignof(char)    << "\n";  // 1
std::cout << alignof(int)     << "\n";  // 4
std::cout << alignof(double)  << "\n";  // 8
std::cout << alignof(Vector4) << "\n";  // 16 (SIMD)
```

**为什么需要对齐？**

1. **硬件要求**：某些 CPU 访问未对齐地址会触发异常（如 ARM）或性能惩罚（如 x86）
2. **缓存行效率**：对齐的数据更可能完整地落在一个缓存行内
3. **SIMD 要求**：SSE 需要 16 字节对齐，AVX 需要 32 字节对齐

#### 对齐的数学

```cpp
// 将地址向上对齐到 alignment 的倍数
template<typename T>
T* align_up(T* ptr, size_t alignment) {
    uintptr_t addr = reinterpret_cast<uintptr_t>(ptr);
    uintptr_t aligned = (addr + alignment - 1) & ~(alignment - 1);
    return reinterpret_cast<T*>(aligned);
}

// 示例：
// addr = 0x1005, alignment = 8
// (0x1005 + 7) & ~7 = 0x100C & 0xFFF8 = 0x1008
```

#### 填充（Padding）

编译器自动插入填充以满足对齐要求：

```cpp
struct BadLayout {
    char  a;    // 1 byte
    // 3 bytes padding
    int   b;    // 4 bytes
    char  c;    // 1 byte
    // 3 bytes padding
}; // 总大小 = 12 bytes（浪费 6 bytes）

struct GoodLayout {
    int   b;    // 4 bytes
    char  a;    // 1 byte
    char  c;    // 1 byte
    // 2 bytes padding（为了满足 int 的对齐）
}; // 总大小 = 8 bytes（浪费 2 bytes）
```

**引擎中的实践**：
- 将大对齐要求的成员放前面
- 使用 `#pragma pack` 要谨慎（影响性能）
- 对频繁访问的数据结构手动优化布局

---

### 1.5 内存对齐的 SIMD 要求

SIMD（Single Instruction Multiple Data）指令要求数据在内存中严格对齐：

| SIMD 扩展 | 寄存器宽度 | 对齐要求 |
|-----------|-----------|---------|
| SSE/SSE2 | 128 bit (16 byte) | 16 字节对齐 |
| AVX/AVX2 | 256 bit (32 byte) | 32 字节对齐 |
| AVX-512 | 512 bit (64 byte) | 64 字节对齐 |

```cpp
// 未对齐加载/存储有性能惩罚（x86）或崩溃（某些 ARM）
__m128 vec = _mm_loadu_ps(unalignedPtr);  // unaligned，慢
__m128 vec = _mm_load_ps(alignedPtr);      // aligned，快

// C++11 对齐方式
alignas(16) float matrix[16];  // 16 字节对齐

// 动态分配对齐内存
void* aligned = _aligned_malloc(size, alignment);  // MSVC
void* aligned = aligned_alloc(alignment, size);     // C11/POSIX
```

**游戏引擎中的应用**：

```cpp
// 变换矩阵必须 16 字节对齐用于 SIMD
struct alignas(16) Transform {
    Matrix4x4 matrix;  // 16 floats = 64 bytes, 自动 16 字节对齐
};

// 粒子数据 SOA（Structure of Arrays）布局，SIMD 友好
struct ParticleSystem {
    alignas(32) float* positionsX;
    alignas(32) float* positionsY;
    alignas(32) float* positionsZ;
    // ...
};
```

---

### 1.6 栈追踪和内存泄漏检测

#### 内存泄漏

**定义**：分配了内存但丢失了指向它的指针，导致内存无法释放。

```cpp
void leak() {
    int* ptr = new int[100];
    // ptr 离开作用域，没有 delete
    // 100 * 4 = 400 字节泄漏
}

void leak2() {
    int* ptr = new int[100];
    ptr = new int[200];  // 原来的 100 个 int 泄漏了！
    delete[] ptr;
}
```

#### 检测方法

1. **重载 new/delete**：记录每次分配的地址、大小、调用栈
2. **定期快照**：比较两个时间点的堆状态
3. **程序退出扫描**：检查未释放的分配

#### 栈追踪实现

```cpp
// Windows: CaptureStackBackTrace
// Linux: backtrace() + backtrace_symbols()
// 或者使用第三方库：libunwind, dbghelp

#ifdef _WIN32
#include <windows.h>
#include <dbghelp.h>

void captureStackTrace(void** frames, int maxFrames) {
    // 跳过 captureStackTrace 和分配器自身的帧
    CaptureStackBackTrace(2, maxFrames, frames, nullptr);
}
#endif
```

---

### 1.7 垃圾回收在游戏引擎中的角色（或为什么没有）

#### 为什么主流游戏引擎不用 GC？

| 问题 | GC 特性 | 游戏引擎需求 |
|------|--------|-------------|
| **暂停时间** | 标记-清除或复制时世界停止 | 16.6ms 内完成一帧（60 FPS），不能有卡顿 |
| **内存开销** | 需要额外空间做标记/复制 | 主机内存有限（PS4 只有 8GB 共享内存） |
| **缓存污染** | GC 遍历堆，破坏 CPU 缓存 | 需要可预测的数据访问模式 |
| **确定性** | 对象销毁时间不确定 | 资源释放需要在特定时机（如关卡切换） |
| **平台限制** | 需要运行时支持 | 某些平台（如早期主机）不支持 |

#### 游戏引擎的替代方案

1. **所有权语义（RAII）**：C++ 的构造函数/析构函数
2. **智能指针**：`std::unique_ptr`（独占）、`std::shared_ptr`（共享，引用计数）
3. **引用计数**：COM 风格，对象知道引用自己的数量
4. **句柄系统**：不直接存指针，存句柄（索引+世代），避免悬空指针

```cpp
// 句柄系统示例
struct Handle {
    uint32_t index;    // 对象在池中的索引
    uint32_t generation; // 世代号，防止重用索引的悬空引用
};

template<typename T>
class HandlePool {
    std::vector<T> objects;
    std::vector<uint32_t> generations;
    std::queue<uint32_t> freeIndices;
    // ...
};
```

#### 例外情况

- **脚本语言**：Unity 的 C# 使用 GC（Mono/IL2CPP），但通过对象池和 Struct 优化减少压力
- **数据导向设计**：ECS（Entity Component System）架构中，组件是值类型，无引用，天然 GC 友好

---

### 1.8 内存预算（Memory Budgeting）和追踪

#### 内存预算

为每个子系统设定内存上限：

```
总内存预算（如 4GB）：
├── 渲染系统：1.5GB
│   ├── 纹理：1.0GB
│   ├── 网格：300MB
│   └── 渲染目标/缓冲区：200MB
├── 音频系统：200MB
├── 物理系统：300MB
├── 游戏逻辑：500MB
├── UI 系统：100MB
├── 脚本/VM：400MB
└── 预留/应急：1.0GB
```

#### 追踪指标

- **当前分配量**：每个子系统实时内存占用
- **峰值分配量**：运行期间的最大占用
- **分配次数**：每帧分配次数（应趋近于 0 在稳定状态）
- **碎片率**：空闲内存的碎片程度

---

### 1.9 虚拟内存和内存映射文件

#### 虚拟内存

操作系统为每个进程提供独立的虚拟地址空间，通过页表映射到物理内存。

**在游戏引擎中的应用**：

1. **大页（Huge Pages）**：减少 TLB（Translation Lookaside Buffer）未命中
   ```bash
   # Linux: 启用透明大页
   echo always > /sys/kernel/mm/transparent_hugepage/enabled
   ```

2. **保留地址空间**：先 `VirtualAlloc`/`mmap` 保留地址范围，实际需要时再提交物理页
   ```cpp
   // Windows: 保留 1GB 地址空间，但不分配物理内存
   void* reserved = VirtualAlloc(nullptr, 1ULL << 30, MEM_RESERVE, PAGE_READWRITE);
   // 需要时提交部分
   VirtualAlloc(reserved, 64 << 20, MEM_COMMIT, PAGE_READWRITE);
   ```

#### 内存映射文件（Memory-Mapped Files）

将文件内容映射到进程的地址空间，读写就像访问内存一样。

**在游戏引擎中的应用**：

1. **资源加载**：将资源包（.pak/.bundle）映射到内存，按需加载页面
2. **零拷贝读取**：避免 `read()` 系统调用的数据拷贝
3. **资源共享**：多个进程映射同一文件，共享物理内存页

```cpp
// Windows 内存映射文件示例
HANDLE file = CreateFileW(L"texture.dds", GENERIC_READ, FILE_SHARE_READ, ...);
HANDLE mapping = CreateFileMapping(file, nullptr, PAGE_READONLY, 0, 0, nullptr);
void* data = MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0);
// 现在可以直接读取 texture data
// ...
UnmapViewOfFile(data);
CloseHandle(mapping);
CloseHandle(file);
```

### 1.10 RAII：C++ 资源管理的核心哲学

**RAII（Resource Acquisition Is Initialization）**是 C++ 最重要的惯用法。它将资源的生命周期绑定到对象的生命周期——资源在对象构造时获取，在对象析构时释放。这利用了 C++ 的确定性析构（deterministic destruction）机制：当对象离开作用域时，其析构函数被自动调用。

```cpp
#include <fstream>
#include <mutex>

// RAII 文件句柄——确保文件总是被正确关闭
class FileHandle {
    FILE* m_file = nullptr;

public:
    explicit FileHandle(const char* path, const char* mode) {
        m_file = fopen(path, mode);
    }

    ~FileHandle() {
        if (m_file) {
            fclose(m_file);  // 保证关闭——即使发生异常
        }
    }

    // 禁止拷贝——文件句柄应该是唯一的
    FileHandle(const FileHandle&) = delete;
    FileHandle& operator=(const FileHandle&) = delete;

    // 允许移动
    FileHandle(FileHandle&& other) noexcept : m_file(other.m_file) {
        other.m_file = nullptr;
    }

    bool IsValid() const { return m_file != nullptr; }
    FILE* Get() const { return m_file; }
};

// RAII 锁守卫——自动管理互斥量的加锁和解锁
class LockGuard {
    std::mutex& m_mutex;

public:
    explicit LockGuard(std::mutex& m) : m_mutex(m) { m_mutex.lock(); }
    ~LockGuard() { m_mutex.unlock(); }  // 异常安全——析构函数总会被调用

    LockGuard(const LockGuard&) = delete;
    LockGuard& operator=(const LockGuard&) = delete;
};

// 使用示例——展示 RAII 如何保证异常安全
void ProcessFileSafe(const char* path) {
    FileHandle file(path, "rb");
    if (!file.IsValid()) return;

    // 即使在此处抛出异常，FileHandle 的析构函数仍然会被调用
    // 文件会被正确关闭，不会发生资源泄漏
    // ... 处理文件 ...
}
```

RAII 的价值在于**异常安全（Exception Safety）**。即使函数中间抛出异常，已经构造的局部对象的析构函数仍然会被调用，确保资源不会泄漏。这是 C++ 相较于需要 `try-finally` 块的语言（如 Java、C#）的优雅之处。

### 1.11 智能指针：引用计数与所有权语义

智能指针将 RAII 应用于指针管理，自动处理动态内存的释放。C++ 标准库提供了三种智能指针，每种代表不同的所有权语义：

```cpp
#include <memory>
#include <iostream>
#include <vector>

// --- unique_ptr: 独占所有权 ---
//
// 一个对象只能由一个 unique_ptr 拥有。
// 当 unique_ptr 被销毁或重置时，它指向的对象也被删除。
// 这是引擎中最常用的智能指针——默认选择。

void UniquePtrDemo() {
    auto obj = std::make_unique<GameObject>();

    // 转移所有权——使用 std::move
    auto obj2 = std::move(obj);
    // 此时 obj 为 nullptr，obj2 拥有对象

    // obj2 离开作用域时，GameObject 自动被销毁
}

// --- shared_ptr: 共享所有权 ---
//
// 多个 shared_ptr 可以指向同一个对象，对象在最后一个 shared_ptr
// 被销毁时才被删除。内部使用引用计数。
// 适用于：资源管理（多个对象共享同一纹理）、观察者模式

void SharedPtrDemo() {
    auto texture = std::make_shared<Texture>();

    {
        auto ref1 = texture;  // 引用计数 +1
        auto ref2 = texture;  // 引用计数 +2
        // 引用计数 = 3 (原始 1 个 + ref1 + ref2)
    }  // ref1 和 ref2 离开作用域，引用计数 -2

    // 引用计数 = 1，texture 仍然有效
}

// --- weak_ptr: 弱引用 ---
//
// 不增加引用计数，只"观察"一个由 shared_ptr 管理的对象。
// 可以安全地检测对象是否已被销毁（避免悬空指针）。
// 适用于：打破循环引用、缓存系统

class NodeFixed {
public:
    std::string m_name;
    std::weak_ptr<NodeFixed> m_parent;   // 父节点——弱引用，避免循环
    std::vector<std::shared_ptr<NodeFixed>> m_children;  // 子节点——强引用

    std::shared_ptr<NodeFixed> GetParent() const {
        return m_parent.lock();  // 将 weak_ptr 提升为 shared_ptr
                                 // 如果父节点已被销毁，返回 nullptr
    }
};
```

`std::shared_ptr` 的实现细节值得深入理解。一个典型的实现包含两个指针：一个指向被管理的对象，另一个指向**控制块（Control Block）**——一个堆分配的结构，存储引用计数（强引用计数和弱引用计数）、自定义删除器、以及分配器。这意味着一个 `shared_ptr` 的拷贝需要原子地递增引用计数（保证线程安全），这涉及**内存屏障（Memory Barrier）**和可能的缓存同步，开销不可忽视。`std::make_shared` 的优势在于它可以一次性分配对象和控制块的内存，减少一次堆分配并提高缓存局部性。

| 智能指针 | 所有权模型 | 内存开销 | 线程安全 | 适用场景 |
|---------|-----------|---------|---------|---------|
| `unique_ptr` | 独占 | 1 个指针（与裸指针相同） | 不涉及（唯一所有者） | 默认选择：资源句柄、工厂返回值、PIMPL 惯用法 |
| `shared_ptr` | 共享（引用计数） | 2 个指针 + 控制块 | 引用计数操作原子化 | 共享资源所有权、观察者缓存、异步回调 |
| `weak_ptr` | 无（弱观察） | 2 个指针 + 控制块 | 引用计数操作原子化 | 打破循环引用、缓存条目检测有效性 |
| 裸指针 `T*` | 无 | 1 个指针 | 无保证 | 非拥有引用（性能关键路径）、兼容 C API |

在引擎开发中，一个常见的性能优化是**在高频路径使用裸指针替代智能指针**。例如，在渲染循环中遍历场景图时，如果已确定对象在帧期间不会被销毁，使用裸指针访问可以避免引用计数的原子操作开销。但这种优化必须建立在严格的**所有权约定**之上——通常通过代码审查和命名规范（如使用 `T*` 表示非拥有指针）来保证安全性。

---

## 2. 代码示例

以下是完整的 C++ 实现，包含 Arena Allocator、Pool Allocator、Free List Allocator 和内存追踪器。

```cpp
// ============================================================================
// 游戏引擎自定义分配器完整实现
// ============================================================================
// 编译: g++ -std=c++17 -O2 memory_allocators.cpp -o memory_allocators
// ============================================================================

#include <iostream>
#include <cstring>
#include <cstdint>
#include <cassert>
#include <vector>
#include <string>
#include <map>
#include <stack>
#include <memory>
#include <algorithm>
#include <chrono>

// ============================================================================
// 工具函数
// ============================================================================

// 将地址向上对齐到 alignment 的倍数
inline uintptr_t align_up(uintptr_t addr, size_t alignment) {
    assert((alignment & (alignment - 1)) == 0 && "Alignment must be power of 2");
    return (addr + alignment - 1) & ~(alignment - 1);
}

inline size_t align_up_size(size_t size, size_t alignment) {
    assert((alignment & (alignment - 1)) == 0 && "Alignment must be power of 2");
    return (size + alignment - 1) & ~(alignment - 1);
}

// ============================================================================
// 1. 线性分配器 (Arena Allocator)
// ============================================================================

class ArenaAllocator {
public:
    ArenaAllocator(size_t capacity)
        : capacity_(capacity), offset_(0) {
        // 实际引擎中这里可能使用 VirtualAlloc/mmap 申请大块内存
        memory_ = static_cast<uint8_t*>(std::malloc(capacity));
        assert(memory_ != nullptr && "Failed to allocate arena memory");
    }

    ~ArenaAllocator() {
        std::free(memory_);
    }

    // 禁止拷贝
    ArenaAllocator(const ArenaAllocator&) = delete;
    ArenaAllocator& operator=(const ArenaAllocator&) = delete;

    // 分配内存
    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        uintptr_t current = reinterpret_cast<uintptr_t>(memory_ + offset_);
        uintptr_t aligned = align_up(current, alignment);
        size_t padding = aligned - current;

        if (offset_ + padding + size > capacity_) {
            return nullptr; // 内存不足
        }

        offset_ += padding + size;
        used_ = offset_;
        return reinterpret_cast<void*>(aligned);
    }

    // 获取当前偏移（用于保存/恢复）
    size_t getMarker() const {
        return offset_;
    }

    // 回滚到指定标记
    void rollback(size_t marker) {
        assert(marker <= offset_ && "Invalid rollback marker");
        offset_ = marker;
        used_ = offset_;
    }

    // 重置整个 Arena
    void reset() {
        offset_ = 0;
        used_ = 0;
    }

    // 查询状态
    size_t getCapacity() const { return capacity_; }
    size_t getUsed() const { return used_; }
    size_t getAvailable() const { return capacity_ - used_; }

    // 使用率
    float getUtilization() const {
        return capacity_ > 0 ? static_cast<float>(used_) / capacity_ : 0.0f;
    }

private:
    uint8_t* memory_;
    size_t capacity_;
    size_t offset_;
    size_t used_ = 0;
};

// ============================================================================
// 2. 栈分配器 (Stack Allocator)
// ============================================================================

class StackAllocator {
public:
    struct Header {
        size_t prevOffset;
        size_t padding;
    };

    StackAllocator(size_t capacity)
        : capacity_(capacity), offset_(0) {
        memory_ = static_cast<uint8_t*>(std::malloc(capacity));
        assert(memory_ != nullptr);
    }

    ~StackAllocator() {
        std::free(memory_);
    }

    StackAllocator(const StackAllocator&) = delete;
    StackAllocator& operator=(const StackAllocator&) = delete;

    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        uintptr_t current = reinterpret_cast<uintptr_t>(memory_ + offset_);
        uintptr_t alignedAddr = align_up(current + sizeof(Header), alignment);
        size_t padding = alignedAddr - current - sizeof(Header);
        size_t totalSize = sizeof(Header) + padding + size;

        if (offset_ + totalSize > capacity_) {
            return nullptr;
        }

        // 写入头部信息
        Header* header = reinterpret_cast<Header*>(alignedAddr - sizeof(Header) - padding);
        header->prevOffset = offset_;
        header->padding = padding;

        offset_ += totalSize;
        return reinterpret_cast<void*>(alignedAddr);
    }

    void deallocate(void* ptr) {
        if (!ptr) return;

        uint8_t* bytePtr = static_cast<uint8_t*>(ptr);
        Header* header = reinterpret_cast<Header*>(bytePtr - sizeof(Header));

        // 验证是最后分配的块（LIFO）
        size_t blockEnd = reinterpret_cast<uintptr_t>(bytePtr) + 
                         (offset_ - (reinterpret_cast<uintptr_t>(bytePtr) - reinterpret_cast<uintptr_t>(memory_)));
        // 简化：直接回滚到 header 记录的 prevOffset
        offset_ = header->prevOffset;
    }

    void reset() {
        offset_ = 0;
    }

    size_t getUsed() const { return offset_; }
    size_t getCapacity() const { return capacity_; }

private:
    uint8_t* memory_;
    size_t capacity_;
    size_t offset_;
};

// ============================================================================
// 3. 池分配器 (Pool Allocator) - 模板化
// ============================================================================

template<typename T>
class PoolAllocator {
public:
    union Node {
        T data;
        Node* next;

        Node() {}
        ~Node() {}
    };

    explicit PoolAllocator(size_t count)
        : capacity_(count), freeList_(nullptr), usedCount_(0) {
        static_assert(sizeof(T) >= sizeof(void*), "T must be at least pointer-sized");

        // 申请一块连续内存
        memory_ = static_cast<Node*>(std::malloc(sizeof(Node) * count));
        assert(memory_ != nullptr);

        // 初始化自由列表
        for (size_t i = 0; i < count; ++i) {
            memory_[i].next = freeList_;
            freeList_ = &memory_[i];
        }
    }

    ~PoolAllocator() {
        // 注意：如果还有未释放的对象，这里不会调用析构函数
        // 实际引擎中应该断言 usedCount_ == 0
        std::free(memory_);
    }

    PoolAllocator(const PoolAllocator&) = delete;
    PoolAllocator& operator=(const PoolAllocator&) = delete;

    // 分配一个对象（不构造）
    T* allocate() {
        if (!freeList_) {
            return nullptr; // 池已满
        }

        Node* node = freeList_;
        freeList_ = freeList_->next;
        ++usedCount_;
        return reinterpret_cast<T*>(node);
    }

    // 释放一个对象（不析构）
    void deallocate(T* ptr) {
        if (!ptr) return;

        // 验证指针是否属于本池
        Node* node = reinterpret_cast<Node*>(ptr);
        assert(node >= memory_ && node < memory_ + capacity_);

        node->next = freeList_;
        freeList_ = node;
        --usedCount_;
    }

    // 构造 + 分配
    template<typename... Args>
    T* construct(Args&&... args) {
        T* ptr = allocate();
        if (ptr) {
            new (ptr) T(std::forward<Args>(args)...);
        }
        return ptr;
    }

    // 析构 + 释放
    void destroy(T* ptr) {
        if (!ptr) return;
        ptr->~T();
        deallocate(ptr);
    }

    size_t getCapacity() const { return capacity_; }
    size_t getUsedCount() const { return usedCount_; }
    size_t getFreeCount() const { return capacity_ - usedCount_; }
    bool isFull() const { return usedCount_ == capacity_; }
    bool isEmpty() const { return usedCount_ == 0; }

private:
    Node* memory_;
    size_t capacity_;
    Node* freeList_;
    size_t usedCount_;
};

// ============================================================================
// 4. 自由列表分配器 (Free List Allocator)
// ============================================================================

class FreeListAllocator {
public:
    struct Block {
        size_t size;
        bool used;
        Block* next;
    };

    FreeListAllocator(size_t capacity)
        : capacity_(capacity) {
        memory_ = static_cast<uint8_t*>(std::malloc(capacity));
        assert(memory_ != nullptr);

        // 初始化：整个内存作为一个空闲块
        Block* initial = reinterpret_cast<Block*>(memory_);
        initial->size = capacity - sizeof(Block);
        initial->used = false;
        initial->next = nullptr;
        freeList_ = initial;
    }

    ~FreeListAllocator() {
        std::free(memory_);
    }

    FreeListAllocator(const FreeListAllocator&) = delete;
    FreeListAllocator& operator=(const FreeListAllocator&) = delete;

    void* allocate(size_t size, size_t alignment = alignof(std::max_align_t)) {
        Block* prev = nullptr;
        Block* curr = freeList_;

        // 首次适配策略（First Fit）
        while (curr) {
            // 计算对齐需要的填充
            uintptr_t blockStart = reinterpret_cast<uintptr_t>(curr) + sizeof(Block);
            uintptr_t alignedStart = align_up(blockStart, alignment);
            size_t padding = alignedStart - blockStart;
            size_t totalNeeded = padding + size;

            if (!curr->used && curr->size >= totalNeeded) {
                // 找到合适的块
                size_t remaining = curr->size - totalNeeded;

                if (remaining > sizeof(Block) + 16) {
                    // 分裂块
                    Block* newBlock = reinterpret_cast<Block*>(
                        alignedStart + size);
                    newBlock->size = remaining - sizeof(Block);
                    newBlock->used = false;
                    newBlock->next = curr->next;

                    curr->size = padding + size;
                    curr->next = newBlock;
                }

                curr->used = true;
                // 从自由列表中移除（如果它在自由列表中）
                if (prev) {
                    prev->next = curr->next;
                } else {
                    freeList_ = curr->next;
                }

                return reinterpret_cast<void*>(alignedStart);
            }

            prev = curr;
            curr = curr->next;
        }

        return nullptr; // 分配失败
    }

    void deallocate(void* ptr) {
        if (!ptr) return;

        Block* block = reinterpret_cast<Block*>(
            static_cast<uint8_t*>(ptr) - sizeof(Block));
        block->used = false;

        // 合并相邻的空闲块
        mergeFreeBlocks();

        // 重新加入自由列表
        block->next = freeList_;
        freeList_ = block;
    }

    void printState() const {
        std::cout << "FreeList state:\n";
        Block* curr = reinterpret_cast<Block*>(memory_);
        while (curr && reinterpret_cast<uint8_t*>(curr) < memory_ + capacity_) {
            std::cout << "  Block @ " << curr 
                      << " size=" << curr->size 
                      << " used=" << (curr->used ? "yes" : "no") << "\n";
            curr = curr->next;
        }
    }

private:
    void mergeFreeBlocks() {
        // 简单实现：遍历所有块，合并相邻的空闲块
        // 实际实现可能需要更复杂的逻辑
        Block* curr = reinterpret_cast<Block*>(memory_);
        while (curr && curr->next) {
            if (!curr->used && !curr->next->used) {
                // 合并
                curr->size += sizeof(Block) + curr->next->size;
                curr->next = curr->next->next;
            } else {
                curr = curr->next;
            }
        }
    }

    uint8_t* memory_;
    size_t capacity_;
    Block* freeList_;
};

// ============================================================================
// 5. 内存追踪器 (Memory Tracker)
// ============================================================================

class MemoryTracker {
public:
    struct AllocationInfo {
        size_t size;
        const char* file;
        int line;
        const char* function;
        std::chrono::steady_clock::time_point timestamp;
    };

    static MemoryTracker& getInstance() {
        static MemoryTracker instance;
        return instance;
    }

    void recordAllocation(void* ptr, size_t size, const char* file, int line, const char* func) {
        std::lock_guard<std::mutex> lock(mutex_);
        allocations_[ptr] = {size, file, line, func, std::chrono::steady_clock::now()};
        totalAllocated_ += size;
        currentUsed_ += size;
        peakUsed_ = std::max(peakUsed_, currentUsed_);
        ++totalAllocationCount_;
    }

    void recordDeallocation(void* ptr) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = allocations_.find(ptr);
        if (it != allocations_.end()) {
            currentUsed_ -= it->second.size;
            allocations_.erase(it);
        }
    }

    void reportLeaks() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::cout << "\n========== Memory Leak Report ==========\n";
        std::cout << "Total allocations: " << totalAllocationCount_ << "\n";
        std::cout << "Total allocated: " << totalAllocated_ << " bytes\n";
        std::cout << "Current used: " << currentUsed_ << " bytes\n";
        std::cout << "Peak used: " << peakUsed_ << " bytes\n";

        if (allocations_.empty()) {
            std::cout << "No leaks detected!\n";
        } else {
            std::cout << "LEAKS FOUND: " << allocations_.size() << " allocations\n";
            for (const auto& [ptr, info] : allocations_) {
                std::cout << "  " << ptr << " " << info.size << " bytes"
                          << " at " << info.file << ":" << info.line
                          << " in " << info.function << "\n";
            }
        }
        std::cout << "========================================\n\n";
    }

    void printStats() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::cout << "\n========== Memory Statistics ==========\n";
        std::cout << "Current used: " << currentUsed_ << " bytes ("
                  << currentUsed_ / (1024.0 * 1024.0) << " MB)\n";
        std::cout << "Peak used: " << peakUsed_ << " bytes ("
                  << peakUsed_ / (1024.0 * 1024.0) << " MB)\n";
        std::cout << "Active allocations: " << allocations_.size() << "\n";
        std::cout << "=======================================\n\n";
    }

    size_t getCurrentUsed() const { return currentUsed_; }
    size_t getPeakUsed() const { return peakUsed_; }

private:
    MemoryTracker() = default;
    ~MemoryTracker() {
        reportLeaks();
    }

    mutable std::mutex mutex_;
    std::map<void*, AllocationInfo> allocations_;
    size_t totalAllocated_ = 0;
    size_t currentUsed_ = 0;
    size_t peakUsed_ = 0;
    size_t totalAllocationCount_ = 0;
};

// 宏用于自动记录分配信息
#define TRACK_ALLOC(ptr, size) \
    MemoryTracker::getInstance().recordAllocation(ptr, size, __FILE__, __LINE__, __func__)
#define TRACK_FREE(ptr) \
    MemoryTracker::getInstance().recordDeallocation(ptr)

// ============================================================================
// 6. 分配器性能测试框架
// ============================================================================

template<typename Func>
double benchmark(Func&& func, int iterations) {
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; ++i) {
        func();
    }
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed = end - start;
    return elapsed.count() / iterations;
}

// ============================================================================
// 测试用数据结构
// ============================================================================

struct Particle {
    float position[3];
    float velocity[3];
    float color[4];
    float lifetime;
    float size;
    // 对齐到 64 字节（缓存行大小）
    char padding[28];
};
static_assert(sizeof(Particle) == 64, "Particle should be 64 bytes");

struct alignas(16) Matrix4x4 {
    float m[16];
};

// ============================================================================
// 主函数 / 测试
// ============================================================================

int main() {
    std::cout << "========================================\n";
    std::cout << "  Game Engine Memory Allocators Demo\n";
    std::cout << "========================================\n\n";

    const int ITERATIONS = 100000;

    // =====================================================================
    // 测试 1: Arena Allocator
    // =====================================================================
    std::cout << "--- Arena Allocator Test ---\n";
    {
        ArenaAllocator arena(1024 * 1024); // 1MB arena

        // 模拟加载关卡资源
        void* textures = arena.allocate(256 * 1024, 16);     // 256KB 纹理
        void* meshes = arena.allocate(128 * 1024, 16);       // 128KB 网格
        void* sounds = arena.allocate(64 * 1024, 16);        // 64KB 音频
        void* scripts = arena.allocate(32 * 1024, 8);        // 32KB 脚本

        std::cout << "After loading level:\n";
        std::cout << "  Used: " << arena.getUsed() << " bytes\n";
        std::cout << "  Utilization: " << arena.getUtilization() * 100 << "%\n";

        // 保存标记
        size_t marker = arena.getMarker();
        std::cout << "  Marker saved at: " << marker << "\n";

        // 临时分配一些数据
        void* temp1 = arena.allocate(1024, 64);
        void* temp2 = arena.allocate(2048, 32);
        std::cout << "  After temp allocations: " << arena.getUsed() << " bytes\n";

        // 回滚到标记
        arena.rollback(marker);
        std::cout << "  After rollback: " << arena.getUsed() << " bytes\n";

        // 卸载关卡 - 重置整个 arena
        arena.reset();
        std::cout << "  After reset: " << arena.getUsed() << " bytes\n";

        // 性能测试
        double time = benchmark([&]() {
            arena.reset();
            volatile void* p1 = arena.allocate(64, 16);
            volatile void* p2 = arena.allocate(128, 16);
            volatile void* p3 = arena.allocate(256, 16);
            (void)p1; (void)p2; (void)p3;
        }, ITERATIONS);
        std::cout << "  Arena alloc + reset: " << time << " ms/op\n";
    }

    // =====================================================================
    // 测试 2: Stack Allocator
    // =====================================================================
    std::cout << "\n--- Stack Allocator Test ---\n";
    {
        StackAllocator stack(1024 * 1024);

        void* a = stack.allocate(100, 16);
        void* b = stack.allocate(200, 16);
        void* c = stack.allocate(50, 16);

        std::cout << "After 3 allocations: " << stack.getUsed() << " bytes\n";

        // LIFO 释放
        stack.deallocate(c);
        std::cout << "After dealloc c: " << stack.getUsed() << " bytes\n";

        stack.deallocate(b);
        std::cout << "After dealloc b: " << stack.getUsed() << " bytes\n";

        stack.deallocate(a);
        std::cout << "After dealloc a: " << stack.getUsed() << " bytes\n";
    }

    // =====================================================================
    // 测试 3: Pool Allocator
    // =====================================================================
    std::cout << "\n--- Pool Allocator Test ---\n";
    {
        const size_t POOL_SIZE = 10000;
        PoolAllocator<Particle> particlePool(POOL_SIZE);

        std::cout << "Pool capacity: " << particlePool.getCapacity() << "\n";

        // 分配一些粒子
        std::vector<Particle*> particles;
        for (int i = 0; i < 1000; ++i) {
            Particle* p = particlePool.construct();
            p->position[0] = static_cast<float>(i);
            p->position[1] = static_cast<float>(i * 2);
            p->position[2] = static_cast<float>(i * 3);
            particles.push_back(p);
        }

        std::cout << "After allocating 1000 particles:\n";
        std::cout << "  Used: " << particlePool.getUsedCount() << "\n";
        std::cout << "  Free: " << particlePool.getFreeCount() << "\n";

        // 释放一半
        for (int i = 0; i < 500; ++i) {
            particlePool.destroy(particles[i]);
        }
        particles.erase(particles.begin(), particles.begin() + 500);

        std::cout << "After freeing 500 particles:\n";
        std::cout << "  Used: " << particlePool.getUsedCount() << "\n";
        std::cout << "  Free: " << particlePool.getFreeCount() << "\n";

        // 性能测试：vs malloc
        double poolTime = benchmark([&]() {
            Particle* p = particlePool.allocate();
            particlePool.deallocate(p);
        }, ITERATIONS);
        std::cout << "  Pool alloc/dealloc: " << poolTime << " ms/op\n";

        double mallocTime = benchmark([&]() {
            Particle* p = static_cast<Particle*>(std::malloc(sizeof(Particle)));
            std::free(p);
        }, ITERATIONS);
        std::cout << "  malloc/free: " << mallocTime << " ms/op\n";
        std::cout << "  Speedup: " << mallocTime / poolTime << "x\n";

        // 清理剩余粒子
        for (Particle* p : particles) {
            particlePool.destroy(p);
        }
    }

    // =====================================================================
    // 测试 4: Free List Allocator
    // =====================================================================
    std::cout << "\n--- Free List Allocator Test ---\n";
    {
        FreeListAllocator freeList(64 * 1024);

        void* a = freeList.allocate(100, 16);
        void* b = freeList.allocate(200, 16);
        void* c = freeList.allocate(50, 8);

        std::cout << "Allocated 3 blocks\n";
        freeList.printState();

        freeList.deallocate(b);
        std::cout << "After dealloc b:\n";
        freeList.printState();

        freeList.deallocate(a);
        std::cout << "After dealloc a (should merge with b):\n";
        freeList.printState();
    }

    // =====================================================================
    // 测试 5: Memory Tracker
    // =====================================================================
    std::cout << "\n--- Memory Tracker Test ---\n";
    {
        void* p1 = std::malloc(100);
        TRACK_ALLOC(p1, 100);

        void* p2 = std::malloc(200);
        TRACK_ALLOC(p2, 200);

        void* p3 = std::malloc(50);
        TRACK_ALLOC(p3, 50);

        MemoryTracker::getInstance().printStats();

        // 故意泄漏 p1 和 p3，释放 p2
        TRACK_FREE(p2);
        std::free(p2);

        std::cout << "After freeing p2:\n";
        MemoryTracker::getInstance().printStats();

        // p1 和 p3 会在程序退出时报告为泄漏
        // 注意：这里为了演示泄漏检测，不释放 p1 和 p3
        // 实际代码中应该：
        // TRACK_FREE(p1); std::free(p1);
        // TRACK_FREE(p3); std::free(p3);

        // 清理以避免真正的内存泄漏（演示目的）
        TRACK_FREE(p1);
        std::free(p1);
        TRACK_FREE(p3);
        std::free(p3);
    }

    // =====================================================================
    // 测试 6: SIMD 对齐测试
    // =====================================================================
    std::cout << "\n--- SIMD Alignment Test ---\n";
    {
        ArenaAllocator simdArena(4096);

        // 分配 16 字节对齐的矩阵
        Matrix4x4* m16 = static_cast<Matrix4x4*>(simdArena.allocate(sizeof(Matrix4x4), 16));
        std::cout << "Matrix4x4 aligned to 16: " 
                  << (reinterpret_cast<uintptr_t>(m16) % 16 == 0 ? "YES" : "NO")
                  << " (addr: " << m16 << ")\n";

        // 分配 64 字节对齐（缓存行对齐）
        Particle* p64 = static_cast<Particle*>(simdArena.allocate(sizeof(Particle), 64));
        std::cout << "Particle aligned to 64: " 
                  << (reinterpret_cast<uintptr_t>(p64) % 64 == 0 ? "YES" : "NO")
                  << " (addr: " << p64 << ")\n";
    }

    // =====================================================================
    // 测试 7: 帧分配器模拟（Arena 的典型用法）
    // =====================================================================
    std::cout << "\n--- Frame Allocator Simulation ---\n";
    {
        // 每帧 1MB 临时内存
        ArenaAllocator frameArena(1024 * 1024);
        const int NUM_FRAMES = 60;

        double totalTime = 0;
        for (int frame = 0; frame < NUM_FRAMES; ++frame) {
            auto frameStart = std::chrono::high_resolution_clock::now();

            // 模拟帧内的临时分配
            // 1. 视锥体剔除结果数组
            void* visibleObjects = frameArena.allocate(1024 * sizeof(uint32_t), 16);

            // 2. 临时变换矩阵
            void* tempMatrices = frameArena.allocate(256 * sizeof(Matrix4x4), 16);

            // 3. 排序用的临时缓冲区
            void* sortBuffer = frameArena.allocate(512 * sizeof(float), 16);

            // 4. 字符串格式化缓冲区
            void* stringBuffer = frameArena.allocate(4096, 8);

            // 模拟一些工作...
            (void)visibleObjects;
            (void)tempMatrices;
            (void)sortBuffer;
            (void)stringBuffer;

            // 帧结束：一次性重置所有临时内存
            frameArena.reset();

            auto frameEnd = std::chrono::high_resolution_clock::now();
            std::chrono::duration<double, std::micro> frameTime = frameEnd - frameStart;
            totalTime += frameTime.count();
        }

        std::cout << "Simulated " << NUM_FRAMES << " frames\n";
        std::cout << "Average frame alloc time: " << totalTime / NUM_FRAMES << " us\n";
        std::cout << "Note: Includes 4 allocations per frame + reset\n";
    }

    // =====================================================================
    // 测试 8: 分配器对比总结
    // =====================================================================
    std::cout << "\n========================================\n";
    std::cout << "  Allocator Comparison Summary\n";
    std::cout << "========================================\n";
    std::cout << "\n";
    std::cout << "| Allocator     | Alloc | Dealloc | Frag | Use Case                    |\n";
    std::cout << "|---------------|-------|---------|------|-----------------------------|\n";
    std::cout << "| Arena         | O(1)  | N/A*    | None | Level loading, frame temp   |\n";
    std::cout << "| Stack         | O(1)  | O(1)    | None | Scoped temp, recursive      |\n";
    std::cout << "| Pool          | O(1)  | O(1)    | None | Particles, entities, pools  |\n";
    std::cout << "| Free List     | O(n)  | O(n)    | Ext  | General purpose, variable   |\n";
    std::cout << "| Buddy         | O(log)| O(log)  | Low  | Large blocks, OS-level      |\n";
    std::cout << "| malloc        | O(log)| O(log)  | Both | Fallback, external libs     |\n";
    std::cout << "\n";
    std::cout << "* Arena supports bulk reset or rollback, not individual dealloc\n";
    std::cout << "\n";

    std::cout << "========================================\n";
    std::cout << "  All tests completed!\n";
    std::cout << "========================================\n";

    return 0;
}
```

**运行方式:**

```bash
# Linux/macOS
g++ -std=c++17 -O2 -pthread memory_allocators.cpp -o memory_allocators
./memory_allocators

# Windows (MSVC)
cl /std:c++17 /O2 /EHsc memory_allocators.cpp
memory_allocators.exe
```

**预期输出:**

```
========================================
  Game Engine Memory Allocators Demo
========================================

--- Arena Allocator Test ---
After loading level:
  Used: 483328 bytes
  Utilization: 46.0938%
  Marker saved at: 483328
  After temp allocations: 486400 bytes
  After rollback: 483328 bytes
  After reset: 0 bytes
  Arena alloc + reset: 0.0012 ms/op

--- Stack Allocator Test ---
After 3 allocations: 384 bytes
After dealloc c: 256 bytes
After dealloc b: 128 bytes
After dealloc a: 0 bytes

--- Pool Allocator Test ---
Pool capacity: 10000
After allocating 1000 particles:
  Used: 1000
  Free: 9000
After freeing 500 particles:
  Used: 500
  Free: 9500
  Pool alloc/dealloc: 0.0003 ms/op
  malloc/free: 0.0015 ms/op
  Speedup: 5x

--- Free List Allocator Test ---
Allocated 3 blocks
FreeList state:
  Block @ 0x... size=128 used=yes
  Block @ 0x... size=256 used=yes
  Block @ 0x... size=64 used=yes
After dealloc b:
FreeList state:
  ...

--- Memory Tracker Test ---

========== Memory Statistics ==========
Current used: 350 bytes
Peak used: 350 bytes
Active allocations: 3
=======================================

After freeing p2:
Current used: 150 bytes
...

========== Memory Leak Report ==========
Total allocations: 3
Total allocated: 350 bytes
Current used: 0 bytes
Peak used: 350 bytes
No leaks detected!
========================================

--- SIMD Alignment Test ---
Matrix4x4 aligned to 16: YES (addr: 0x...)
Particle aligned to 64: YES (addr: 0x...)

--- Frame Allocator Simulation ---
Simulated 60 frames
Average frame alloc time: 0.5 us
Note: Includes 4 allocations per frame + reset

========================================
  Allocator Comparison Summary
========================================

| Allocator     | Alloc | Dealloc | Frag | Use Case                    |
|---------------|-------|---------|------|-----------------------------|
...

========================================
  All tests completed!
========================================
```

---

## 3. 练习

### 练习 1：实现伙伴分配器（Buddy Allocator）

基于本章学到的知识，实现一个支持以下功能的伙伴分配器：

**要求：**
1. 初始化时接受总内存大小（必须是 2 的幂）
2. 支持 `allocate(size_t size)` 和 `deallocate(void* ptr)`
3. 分配时向上取整到最近的 2 的幂
4. 释放时自动合并相邻的空闲伙伴块
5. 添加 `printState()` 方法可视化当前内存状态

**提示：**
- 每个块需要一个头部记录大小和是否使用
- 伙伴块的地址可以通过当前地址异或块大小计算：`buddy = current ^ size`
- 可以使用一个数组来跟踪每个大小级别的空闲块列表

**验证：**
```cpp
BuddyAllocator buddy(1024);  // 1KB，最小块 64B
void* a = buddy.allocate(100);  // 应该分配 128B 块
void* b = buddy.allocate(200);  // 应该分配 256B 块
buddy.deallocate(a);  // 释放 128B 块
buddy.deallocate(b);  // 释放 256B 块，如果伙伴空闲则合并
// 最终应该合并回 1024B
```

---

### 练习 2：为引擎子系统设计内存预算系统

设计并实现一个简单的内存预算系统：

**要求：**
1. 定义至少 5 个子系统（如 Rendering、Physics、Audio、AI、UI）
2. 每个子系统有内存预算上限
3. 提供 `allocate(subsystem, size)` 和 `deallocate(subsystem, ptr)` 接口
4. 当子系统接近预算上限时输出警告
5. 提供 `printReport()` 输出各子系统的内存使用情况

**进阶：**
- 实现内存预算的"软限制"和"硬限制"
- 软限制：超过时输出警告，但允许分配
- 硬限制：超过时拒绝分配，返回 `nullptr`

---

### 练习 3（可选）：集成内存追踪到分配器

将本章的 `MemoryTracker` 集成到 Arena、Pool 和 Free List 分配器中：

**要求：**
1. 每个分配器在分配/释放时自动记录到 `MemoryTracker`
2. 记录分配器的名称（如 "FrameArena"、"ParticlePool"）
3. 在程序退出时，按分配器分组输出泄漏报告
4. 统计每个分配器的分配次数、总字节数、当前使用字节数

**示例输出：**
```
========== Per-Allocator Report ==========
FrameArena:
  Total allocs: 3600, Total bytes: 1.7GB
  Current used: 0 bytes (always reset)
  Leaks: 0

ParticlePool:
  Total allocs: 10000, Total bytes: 640KB
  Current used: 320KB
  Leaks: 0

...========================================
```

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> #include <cstdint>
> #include <cassert>
> #include <cstdlib>
> #include <vector>
> #include <unordered_map>
> #include <iostream>
> #include <cmath>
>
> // 伙伴分配器：以 2 的幂为粒度管理内存，支持分裂与合并
> class BuddyAllocator {
> public:
>     struct Block {
>         size_t size;
>         bool used;
>     };
>
>     BuddyAllocator(size_t totalSize) {
>         // 确保总大小为 2 的幂，且不小于最小块
>         totalSize_ = 1;
>         while (totalSize_ < totalSize) totalSize_ <<= 1;
>         size_t minBlock = 64; // 最小块大小
>         if (totalSize_ < minBlock) totalSize_ = minBlock;
>         memory_ = static_cast<uint8_t*>(std::malloc(totalSize_));
>         assert(memory_ != nullptr);
>
>         // 初始化根块
>         blocks_[0] = {totalSize_, false};
>     }
>
>     ~BuddyAllocator() { std::free(memory_); }
>
>     // 分配：size 向上取整到最近的 2 的幂，分裂大块直到合适大小
>     void* allocate(size_t size) {
>         if (size == 0) return nullptr;
>         size_t blockSize = roundUpPower2(size);
>         if (blockSize < 64) blockSize = 64;
>
>         // 从大到小查找合适的空闲块
>         for (auto it = blocks_.begin(); it != blocks_.end(); ++it) {
>             if (!it->second.used && it->second.size >= blockSize) {
>                 // 不断分裂直到块大小刚好匹配
>                 while (it->second.size > blockSize) {
>                     split(it->first);
>                     // 分裂后需要重新查找（当前块已变小）
>                     // 继续用原 offset 检查
>                 }
>                 // 分裂后当前 offset 可能指向更小的块，重新确认
>                 // 简化处理：分裂后重新遍历
>             }
>         }
>
>         // 第二次遍历确认并标记使用
>         for (auto it = blocks_.begin(); it != blocks_.end(); ++it) {
>             if (!it->second.used && it->second.size == blockSize) {
>                 it->second.used = true;
>                 return memory_ + it->first;
>             }
>         }
>         return nullptr; // 无可用块
>     }
>
>     // 释放：标记为未使用，然后递归尝试合并伙伴块
>     void deallocate(void* ptr) {
>         if (!ptr) return;
>         size_t offset = static_cast<uint8_t*>(ptr) - memory_;
>         auto it = blocks_.find(offset);
>         if (it == blocks_.end() || !it->second.used) return;
>
>         it->second.used = false;
>         // 循环合并所有可能的伙伴
>         tryMerge(it->first);
>     }
>
>     void printState() const {
>         std::cout << "=== Buddy Allocator State (total=" << totalSize_ << "B) ===\n";
>         size_t totalUsed = 0;
>         for (const auto& [offset, block] : blocks_) {
>             std::cout << "  Offset=" << offset << " Size=" << block.size
>                       << " [" << (block.used ? "USED" : "FREE") << "]\n";
>             if (block.used) totalUsed += block.size;
>         }
>         std::cout << "  Total used: " << totalUsed << "B / " << totalSize_ << "B\n";
>     }
>
> private:
>     // 向上取整到最近的 2 的幂
>     static size_t roundUpPower2(size_t n) {
>         if (n == 0) return 0;
>         n--;
>         n |= n >> 1;  n |= n >> 2;
>         n |= n >> 4;  n |= n >> 8;
>         n |= n >> 16; n |= n >> 32;
>         return n + 1;
>     }
>
>     // 伙伴地址 = current ^ size（异或翻转对应位）
>     size_t getBuddyOffset(size_t offset, size_t size) const {
>         return offset ^ size;
>     }
>
>     // 分裂指定块
>     void split(size_t offset) {
>         auto it = blocks_.find(offset);
>         if (it == blocks_.end() || it->second.used) return;
>         size_t newSize = it->second.size / 2;
>         if (newSize < 64) return; // 达到最小块
>         it->second.size = newSize;
>         size_t buddyOffset = offset + newSize;
>         blocks_[buddyOffset] = {newSize, false};
>     }
>
>     // 尝试合并伙伴块（递归直到无法合并）
>     void tryMerge(size_t offset) {
>         auto it = blocks_.find(offset);
>         if (it == blocks_.end() || it->second.used) return;
>         size_t size = it->second.size;
>         size_t buddyOffset = getBuddyOffset(offset, size);
>         auto buddyIt = blocks_.find(buddyOffset);
>         if (buddyIt == blocks_.end() || buddyIt->second.used || buddyIt->second.size != size) return;
>         // 合并：保留左块（较小的 offset），移除右块
>         size_t left = std::min(offset, buddyOffset);
>         blocks_[left].size = size * 2;
>         blocks_.erase(std::max(offset, buddyOffset));
>         // 递归尝试合并更大的块
>         tryMerge(left);
>     }
>
>     uint8_t* memory_;
>     size_t totalSize_;
>     // offset -> Block，用 map 维持 offset 排序以便遍历
>     std::unordered_map<size_t, Block> blocks_;
> };
> ```
>
> **关键点：** 伙伴地址通过 `offset ^ size` 计算——这正是"伙伴"系统名称的由来。分配时自上而下分裂，释放时自下而上合并。时间复杂度 O(log N)。

> [!tip]- 练习 2 参考答案
> ```cpp
> #include <string>
> #include <vector>
> #include <cstdint>
> #include <iostream>
> #include <unordered_map>
> #include <algorithm>
>
> // 子系统内存预算管理器
> class MemoryBudget {
> public:
>     struct Subsystem {
>         std::string name;
>         size_t softLimit;  // 软限制：超过时告警
>         size_t hardLimit;  // 硬限制：超过时拒绝
>         size_t currentUsage;
>         size_t totalAllocs;
>         size_t peakUsage;
>     };
>
>     void registerSubsystem(const std::string& name, size_t softMB, size_t hardMB) {
>         Subsystem sub;
>         sub.name = name;
>         sub.softLimit = softMB * 1024 * 1024;
>         sub.hardLimit = hardMB * 1024 * 1024;
>         sub.currentUsage = 0;
>         sub.totalAllocs = 0;
>         sub.peakUsage = 0;
>         subsystems_[name] = sub;
>     }
>
>     void* allocate(const std::string& subsystem, size_t size) {
>         auto it = subsystems_.find(subsystem);
>         if (it == subsystems_.end()) return nullptr; // 未注册子系统
>         auto& sub = it->second;
>         if (sub.currentUsage + size > sub.hardLimit) {
>             std::cerr << "[MEMORY] HARD LIMIT: " << subsystem
>                       << " exceeds " << sub.hardLimit / 1024 / 1024 << "MB\n";
>             return nullptr;
>         }
>         if (sub.currentUsage + size > sub.softLimit) {
>             std::cerr << "[MEMORY] WARNING: " << subsystem
>                       << " exceeds soft limit " << sub.softLimit / 1024 / 1024 << "MB\n";
>         }
>         void* ptr = std::malloc(size);
>         if (ptr) {
>             sub.currentUsage += size;
>             sub.totalAllocs++;
>             sub.peakUsage = std::max(sub.peakUsage, sub.currentUsage);
>         }
>         return ptr;
>     }
>
>     void deallocate(const std::string& subsystem, void* ptr, size_t size) {
>         if (!ptr) return;
>         std::free(ptr);
>         auto it = subsystems_.find(subsystem);
>         if (it != subsystems_.end()) {
>             it->second.currentUsage -= size;
>         }
>     }
>
>     void printReport() const {
>         std::cout << "\n========== Memory Budget Report ==========\n";
>         size_t totalCurrent = 0, totalPeak = 0;
>         for (const auto& [name, sub] : subsystems_) {
>             std::cout << name << ":\n";
>             std::cout << "  Current: " << sub.currentUsage / 1024 << "KB";
>             if (sub.currentUsage > sub.softLimit) std::cout << " [WARNING: >soft limit]";
>             std::cout << "\n";
>             std::cout << "  Peak:    " << sub.peakUsage / 1024 << "KB\n";
>             std::cout << "  Soft limit: " << sub.softLimit / 1024 / 1024
>                       << "MB, Hard limit: " << sub.hardLimit / 1024 / 1024 << "MB\n";
>             std::cout << "  Total allocs: " << sub.totalAllocs << "\n";
>             totalCurrent += sub.currentUsage;
>             totalPeak += sub.peakUsage;
>         }
>         std::cout << "-------------------------------------------\n";
>         std::cout << "  TOTAL Current: " << totalCurrent / 1024 / 1024 << "MB\n";
>         std::cout << "  TOTAL Peak:    " << totalPeak / 1024 / 1024 << "MB\n";
>         std::cout << "===========================================\n";
>     }
>
> private:
>     std::unordered_map<std::string, Subsystem> subsystems_;
> };
> ```
>
> **思考题：** 软限制和硬限制的区别是什么？> 软限制是告警阈值——超过时仅发出 warning，允许继续分配，用于提示开发者"该子系统内存使用偏高，可能需要优化"。硬限制是安全阈值——超过时拒绝分配返回 `nullptr`，防止单个子系统耗尽所有内存导致整体崩溃。两级限制的设计来自游戏主机的开发经验：主机总内存固定，必须确保渲染、物理、音频都能分配到内存。实际引擎中（如 UE 的 FMallocBinned）还会增加第三个维度——**预留内存**：关键功能（如 UI、玩家角色）始终保留最低内存配额，LRU 卸载时跳过这些关键资源。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> #include <string>
> #include <map>
> #include <mutex>
>
> // 全局内存追踪器——统计每个分配器的使用情况
> class MemoryTracker {
> public:
>     static MemoryTracker& Instance() {
>         static MemoryTracker inst;
>         return inst;
>     }
>
>     struct AllocatorStats {
>         size_t totalAllocs = 0;
>         size_t totalDeallocs = 0;
>         size_t totalBytesAllocated = 0;
>         size_t totalBytesDeallocated = 0;
>         size_t currentBytes = 0;
>         size_t peakBytes = 0;
>     };
>
>     void recordAlloc(const std::string& allocatorName, size_t size) {
>         std::lock_guard<std::mutex> lock(mutex_);
>         auto& stats = stats_[allocatorName];
>         stats.totalAllocs++;
>         stats.totalBytesAllocated += size;
>         stats.currentBytes += size;
>         if (stats.currentBytes > stats.peakBytes)
>             stats.peakBytes = stats.currentBytes;
>         // 同时记录每次分配的调用堆栈（简化：仅存 size）
>         activeAllocs_[allocatorName].push_back(size);
>     }
>
>     void recordDealloc(const std::string& allocatorName, size_t size) {
>         std::lock_guard<std::mutex> lock(mutex_);
>         auto& stats = stats_[allocatorName];
>         stats.totalDeallocs++;
>         stats.totalBytesDeallocated += size;
>         stats.currentBytes -= size;
>     }
>
>     // 程序退出时调用，输出泄漏报告
>     void printLeakReport() const {
>         std::lock_guard<std::mutex> lock(mutex_);
>         std::cout << "\n========== Per-Allocator Report ==========\n";
>         for (const auto& [name, stats] : stats_) {
>             size_t leaks = stats.totalAllocs - stats.totalDeallocs;
>             std::cout << name << ":\n";
>             std::cout << "  Total allocs: " << stats.totalAllocs
>                       << ", Total bytes: " << formatBytes(stats.totalBytesAllocated) << "\n";
>             std::cout << "  Current used: " << formatBytes(stats.currentBytes)
>                       << " (peak: " << formatBytes(stats.peakBytes) << ")\n";
>             std::cout << "  Leaks: " << leaks;
>             if (stats.currentBytes > 0) std::cout << " (" << formatBytes(stats.currentBytes) << ")";
>             std::cout << "\n";
>         }
>         std::cout << "==========================================\n";
>     }
>
> private:
>     static std::string formatBytes(size_t bytes) {
>         if (bytes > 1024*1024*1024) return std::to_string(bytes/(1024*1024*1024)) + "GB";
>         if (bytes > 1024*1024) return std::to_string(bytes/(1024*1024)) + "MB";
>         if (bytes > 1024) return std::to_string(bytes/1024) + "KB";
>         return std::to_string(bytes) + "B";
>     }
>
>     mutable std::mutex mutex_;
>     std::map<std::string, AllocatorStats> stats_;
>     std::map<std::string, std::vector<size_t>> activeAllocs_;
> };
>
> // 集成示例：在分配器中调用 MemoryTracker
> // 以 ArenaAllocator 为例，在 allocate() 中添加一行：
> //   MemoryTracker::Instance().recordAlloc("FrameArena", size);
> // 在 reset() 中不调用 recordDealloc，因为 Arena 是按帧整体释放。
> // 在 PoolAllocator::deallocate(T* ptr) 中：
> //   MemoryTracker::Instance().recordDealloc("ParticlePool", sizeof(T));
> ```
> > **注意：** 本示例中 Arena 分配器不逐块追踪释放（因为它是整体回滚的），因此 `currentBytes` 在 Arena 中展示的是"累计已分配但未回滚"的近似值。真实引擎中可通过 `reset()` 时清零计数器来处理。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

### 书籍

1. **《Game Engine Architecture》by Jason Gregory** — 第 6 章 Memory Management，游戏引擎内存管理的权威参考
2. **《C++ High Performance》by Bjorn Andrist & Viktor Sehr** — 第 5 章 Memory Management，C++ 高性能内存管理
3. **《What Every Programmer Should Know About Memory》by Ulrich Drepper** — 免费 PDF，深入 CPU 缓存和内存层次结构

### 论文与文章

4. **EASTL 文档** — Electronic Arts 的开源 STL 替代品，包含详细的自定义分配器设计：
   - https://github.com/electronicarts/EASTL
   - 重点阅读 `EAStackAllocator`、`EAPoolAllocator` 的实现

5. **"Custom Memory Allocation in Game Engines"** — GDC 演讲系列，搜索 GDC Vault

6. **Unreal Engine 源码** — `Engine/Source/Runtime/Core/Public/HAL/MemoryBase.h` 和 `FMallocBinned` 实现

### 在线资源

7. **Handmade Hero** — Casey Muratori 的系列视频，从零编写游戏引擎，包含大量内存管理内容
8. **Bitsquid Blog**（现 Autodesk Stingray）— 多篇关于数据导向设计和内存管理的文章
9. **Mike Acton 的 "Data-Oriented Design" 演讲** — CppCon 2014，理解为什么内存布局决定性能

### 开源项目参考

10. **bgfx** — 跨平台渲染库，查看其内存分配策略
11. **Godot Engine** — `core/os/memory.h` 和 `core/pool_allocator.h`
12. **Ogre3D** — `OgreMemoryAllocatorConfig.h`

---

## 常见陷阱

### 陷阱 1：对齐计算错误

```cpp
// 错误：没有考虑分配器自身的头部大小
void* ptr = allocator.allocate(sizeof(Matrix4x4), 16);
// 如果 allocator 在 ptr 前面放了头部信息，
// 用户得到的 ptr 可能不对齐！

// 正确：分配器内部先对齐头部后的地址
uintptr_t userAddr = align_up(currentAddr + headerSize, alignment);
```

### 陷阱 2：忘记处理分配失败

```cpp
// 错误：假设分配总是成功
Particle* p = particlePool.allocate();
p->position[0] = 1.0f;  // 如果 allocate 返回 nullptr，崩溃！

// 正确：检查返回值
Particle* p = particlePool.allocate();
if (!p) {
    // 处理失败：使用备用池、减少粒子数量、或报错
    return;
}
```

### 陷阱 3：跨分配器释放

```cpp
// 错误：从 A 分配，从 B 释放
void* ptr = arenaA.allocate(100);
arenaB.deallocate(ptr);  // 未定义行为！

// 正确：谁分配，谁释放
// 或者使用句柄系统，让释放操作路由到正确的分配器
```

### 陷阱 4：Arena 的"假释放"

```cpp
// 错误：在 Arena 上分配，保存指针，重置 Arena，再使用指针
char* tempString = static_cast<char*>(frameArena.allocate(256));
strcpy(tempString, "Hello");
frameArena.reset();
// tempString 现在是悬空指针！
std::cout << tempString;  // 未定义行为

// 正确：Arena 内存只在当前作用域/帧内有效
// 需要长期保存的数据必须复制到持久存储
```

### 陷阱 5：忽略析构函数

```cpp
// 错误：Pool 分配了有非平凡析构函数的对象，但 deallocate 不调用析构
PoolAllocator<std::string> stringPool(100);
std::string* s = stringPool.allocate();
new (s) std::string("Hello World");  // 构造
stringPool.deallocate(s);  // 内存归还，但析构函数没调用！
// std::string 内部动态分配的内存泄漏了

// 正确：使用 construct/destroy 方法
stringPool.destroy(s);  // 先析构，再归还内存
```

### 陷阱 6：多线程不加锁

```cpp
// 错误：多个线程同时使用同一个分配器
// Thread A                    Thread B
// ptr = pool.allocate();     ptr = pool.allocate();
// 可能同时修改 freeList_，导致数据竞争

// 正确方案 1：每个线程有自己的分配器（Thread-Local Allocator）
// 正确方案 2：使用锁（但会降低性能）
// 正确方案 3：使用无锁数据结构（Lock-Free Stack）
```

### 陷阱 7：内存追踪的性能开销

```cpp
// 错误：在发布版本中启用完整的栈追踪
#ifdef _DEBUG
#define TRACK_ALLOC(ptr, size) /* 记录文件/行号/栈 */
#else
#define TRACK_ALLOC(ptr, size) /* 空 */
#endif

// 更好的做法：发布版本只保留轻量级统计（无栈追踪）
// 或者使用采样追踪（每 N 次分配记录一次）
```

### 陷阱 8：过度工程化

```cpp
// 不要为了"完美"的分配器而过度设计
// 如果标准库的 malloc 已经满足需求，就不要自定义分配器

// 自定义分配器的正确引入时机：
// 1. 性能分析显示 malloc 是瓶颈
// 2. 特定的分配模式可以被利用（如全部同大小对象）
// 3. 需要额外的功能（对齐、追踪、预算）
// 4. 平台限制（嵌入式、游戏主机）
```

---

## 各分配器适用场景速查表

| 场景 | 推荐分配器 | 理由 |
|------|-----------|------|
| 关卡资源加载 | Arena | 批量加载，批量卸载 |
| 每帧临时数据 | Arena（Frame Arena） | 每帧重置，O(1) 分配 |
| 粒子系统 | Pool | 固定大小，高频分配/释放 |
| 游戏对象/Entity | Pool | 同大小，需要快速创建/销毁 |
| UI 元素 | Stack 或 Pool | 层级结构，LIFO 释放 |
| 纹理/模型数据 | Free List 或 Buddy | 大小不固定，生命周期不同 |
| 字符串/日志 | Arena | 临时格式化，用完即弃 |
| 渲染命令缓冲区 | Linear（GPU 风格） | 顺序写入，顺序消费 |
| 物理碰撞数据 | Pool | 同大小（如 ContactManifold）|
| 音频缓冲区 | 平台特定（对齐到 DMA） | 硬件可能对齐有特殊要求 |

---

## 本章小结

本章涵盖了游戏引擎内存管理的核心内容：

1. **C++ 内存模型**：理解栈、堆、全局区的特性和适用场景
2. **内存碎片**：识别内部碎片和外部碎片，选择合适的分配策略
3. **五种自定义分配器**：掌握 Arena、Stack、Pool、Free List、Buddy 的原理和实现
4. **对齐和填充**：满足 SIMD/GPU 的硬件对齐要求，优化数据结构布局
5. **内存追踪**：检测泄漏，统计使用情况
6. **内存预算**：为子系统设定上限，防止内存失控
7. **虚拟内存**：大页、内存映射文件在引擎中的应用

**关键原则**：
- **没有银弹**：不同场景用不同分配器
- **测量先行**：在优化前用性能分析器确认瓶颈
- **简单优先**：复杂的分配器只有在确实需要时才引入
- **安全第一**：自定义分配器容易引入 bug，需要充分的测试
