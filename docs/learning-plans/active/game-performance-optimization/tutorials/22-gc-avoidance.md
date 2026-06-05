---
title: "GC 规避策略 — C#/Unity 中的 GC 压力管理"
updated: 2026-06-05
---

# GC 规避策略 — C#/Unity 中的 GC 压力管理
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50 分钟
> 前置知识: C# 基础，Unity 基本 API（GameObject、MonoBehaviour），了解托管堆与值类型概念
---
## 1. 概念讲解

### 为什么需要这个？

你在 Unity 中运行 Profiler，看到锯齿状的帧时间，每隔几秒就出现一个 50-100ms 的尖峰。打开 Deep Profile，发现尖峰总是伴随 `GC.Collect()` 调用。这就是 **GC 暂停（GC Pause）** — 托管语言游戏开发的第一号性能杀手。

在 60fps 下每帧只有 16.67ms。即使一次小的增量 GC 也需要 1-5ms，一次完整的 Gen2 回收可能高达 50-200ms——直接吃掉 3-12 帧的时间。如果 GC 在战斗中触发，玩家会感到明显的卡顿。

### 核心思想

#### C# GC 如何工作

C#（Mono/IL2CPP/CoreCLR）使用**分代标记-清除-压缩（Generational Mark-Sweep-Compact）** GC：

```
Gen 0 (小对象区)       ← 最频繁回收，很快 (1-5ms)
Gen 1 (幸存者区)       ← 回收 Gen 0 时幸存的对象被提升到这里
Gen 2 (长生命周期区)    ← 完整回收 GC，最慢 (50-200ms)
LOH  (大对象堆, ≥85KB) ← 不压缩，容易碎片化
```

GC 触发条件：
- **Gen 0 满** — 分配新对象时 Gen 0 空间不足，触发 Gen 0 GC。
- **Gen 2 满** — Gen 2 空间不足，触发完整 GC（最致命）。
- **显式调用** — `System.GC.Collect()`。
- **低内存** — 系统内存不足时触发。

#### 什么东西在分配托管堆内存？

许多看似"无害"的代码在背后分配内存（alloc）：

| 模式 | 分配来源 | GC.Alloc |
|------|----------|----------|
| `string + string` | 每次拼接创建新 `string` | 拼接次数 × 平均长度 |
| `foreach (var x in list)` | `List<T>.Enumerator` 如果是接口版本 | 取决于实现 |
| LINQ (`.Where()`, `.Select()`) | 迭代器对象 + 闭包 | 每次调用 |
| `Debug.Log("x=" + x)` | 字符串拼接 | 频繁调用时可观 |
| `.ToString()` | 新 string | 每次调用 |
| `Camera.main` | 内部调用 `FindGameObjectsWithTag` | 每次 ~100B+ |
| `GetComponent<T>()` | 一般无分配（返回引用） | 0，但不能在 Update 中滥用 |
| `new WaitForSeconds(1f)` | 协程 yield 对象 | 每次 20-40B |
| 闭包 / Lambda | 捕获外部变量的委托对象 | 每次创建 |
| `params` 方法 | 隐式数组，如 `String.Format("{0}{1}", a, b)` | `object[]` |

#### 核心策略总览

| 策略 | 适用场景 | 效果 |
|------|----------|------|
| **struct 替代 class** | 生命周期短的小对象 | 栈分配，零 GC |
| **StringBuilder 池化** | 字符串拼接 | 减少临时 string |
| **数组/Lis t池化** | 临时集合 | 复用而非反复 new |
| **手动迭代器替代 LINQ** | 热路径查询 | 避免迭代器分配 |
| **缓存引用** | Camera.main, GetComponent | 避免重复查找 |
| **Native Collections** | 大量数据（ECS） | 非托管内存，零 GC |
| **协程缓存** | WaitForSeconds 等 yield 对象 | 避免每帧 new |

#### Unity 的增量 GC（Incremental GC）

Unity 2019.1+ 支持增量 GC：将一次完整的 GC 拆分为多个时间片，分散到多帧执行。这样单帧的 GC 暂停从 50ms 降到 1-2ms × N 帧。

- 优点：消除长暂停。
- 缺点：总 GC 时间略长（分片开销），且只在支持的平台可用（目前不包含 WebGL）。

#### UE 的 GC

UE 使用标记-清除 GC + Cluster 的概念，核心机制：
- `UPROPERTY()` 宏标记的成员变量被 GC 追踪——未被任何 `UPROPERTY` 引用的 `UObject` 会被回收。
- **Cluster**: 同簇对象一起标记/清除，减少单个引用遍历。
- **避免 GC 暂停**: UE 将 `UObject` 生命周期交由 GC 管理，开发者需要确保 `UPROPERTY` 正确设置引用关系。使用 `TWeakObjectPtr`/`FObjectKey` 避免循环引用。
- C++ 侧的 `TArray`/`TMap` 使用非托管内存——只在 `UPROPERTY` 包装时受 GC 管理。

---
## 2. 代码示例

三个 C# 基准测试：常见 Unity 模式的 GC 分配检测、优化前后对比。

### 完整代码 (C# / Unity)

以下代码可以直接放在 Unity 项目的 `Assets/Scripts/` 下运行。需要 Unity 2020.3+ 并确保 `UNITY_EDITOR` 宏下可使用 `UnityEngine.Profiling.Profiler`。

```csharp
// GCPressureBenchmark.cs
// 将此脚本挂载到场景中的 GameObject 上，进入 Play Mode 观察 Console 输出。
// 无 GC Alloc 的测试需要使用 Unity Profiler (Window > Analysis > Profiler) 的 "GC Alloc" 列确认。

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.Pool;
using UnityEngine.Profiling;

public class GCPressureBenchmark : MonoBehaviour
{
    // ============================================================
    // 1. 测试数据
    // ============================================================
    private List<int> _testList;
    private Camera _cachedCamera;
    private StringBuilder _cachedStringBuilder;

    private const int Iterations = 10000;

    void Start()
    {
        _testList = new List<int>();
        for (int i = 0; i < 1000; i++) _testList.Add(i);

        // 预缓存 Camera.main — 避免每帧查找
        _cachedCamera = Camera.main;

        // 预分配 StringBuilder（池化也可）
        _cachedStringBuilder = new StringBuilder(256);

        Debug.Log("========== GC 压力基准测试 ==========");
        Debug.Log($"测试次数: {Iterations}");

        RunAllBenchmarks();
    }

    void RunAllBenchmarks()
    {
        Benchmark_ForEach_VS_For();
        Benchmark_Linq_VS_Manual();
        Benchmark_String_Concatenation();
        Benchmark_Boxing_Detection();
        Benchmark_CameraMain();
        Benchmark_CoroutineYield();
        Benchmark_Closure_Allocation();
    }

    // ============================================================
    // 2. 基准: foreach vs for
    // ============================================================
    void Benchmark_ForEach_VS_For()
    {
        Debug.Log("\n--- 基准 1: foreach vs for (List<int>) ---");

        long sum = 0;

        // foreach — C# 中 List<T> 的 foreach 返回值类型的 Enumerator
        // 在 C# 5+ 中不分配堆内存（Enumerator 是 struct）
        // 但如果 foreach 的是 IEnumerable<T> 接口则每次都会装箱
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int iter = 0; iter < Iterations; iter++)
            {
                foreach (int val in _testList)
                {
                    sum += val;
                }
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  foreach (List<int>):      GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // foreach over IList<int> (接口) — 触发装箱
        {
            IList<int> ifaceList = _testList;
            long gcBefore = GC.GetTotalMemory(false);
            for (int iter = 0; iter < Iterations; iter++)
            {
                foreach (int val in ifaceList)
                {
                    sum += val;
                }
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  foreach (IList<int>):      GC diff = {(gcAfter - gcBefore) / 1024} KB (慎用接口 foreach!)");
        }

        // for 循环
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int iter = 0; iter < Iterations; iter++)
            {
                int count = _testList.Count;
                for (int i = 0; i < count; i++)
                {
                    sum += _testList[i];
                }
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  for (int i=0; i<count):    GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        volatile long v = sum; // 防止编译器优化掉
    }

    // ============================================================
    // 3. 基准: LINQ vs 手动循环
    // ============================================================
    void Benchmark_Linq_VS_Manual()
    {
        Debug.Log("\n--- 基准 2: LINQ vs 手动循环 ---");

        // LINQ — .Where().Select() 内部创建迭代器对象 + 闭包
        {
            long sum = 0;
            long gcBefore = GC.GetTotalMemory(false);
            for (int iter = 0; iter < Iterations / 10; iter++)
            {
                // 减少迭代次数因 LINQ 太慢
                var result = _testList.Where(x => x % 2 == 0)
                                      .Select(x => x * 2);
                foreach (int val in result)
                {
                    sum += val;
                }
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  LINQ Where+Select:         GC diff = {(gcAfter - gcBefore) / 1024} KB (分配大量迭代器+闭包)");
        }

        // 手动循环 — 零分配
        {
            long sum = 0;
            long gcBefore = GC.GetTotalMemory(false);
            for (int iter = 0; iter < Iterations; iter++)
            {
                int count = _testList.Count;
                for (int i = 0; i < count; i++)
                {
                    int x = _testList[i];
                    if (x % 2 == 0)
                    {
                        sum += x * 2;
                    }
                }
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  手动 for + if:             GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // LINQ 替代: 使用 List<T>.FindAll 返回预分配列表
        {
            long sum = 0;
            long gcBefore = GC.GetTotalMemory(false);
            for (int iter = 0; iter < Iterations / 10; iter++)
            {
                var filtered = _testList.FindAll(x => x % 2 == 0);
                foreach (int val in filtered)
                {
                    sum += val * 2;
                }
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  FindAll + foreach:         GC diff = {(gcAfter - gcBefore) / 1024} KB (也分配新 List)");
        }
    }

    // ============================================================
    // 4. 基准: 字符串拼接
    // ============================================================
    void Benchmark_String_Concatenation()
    {
        Debug.Log("\n--- 基准 3: 字符串拼接 ---");

        // 坏: 原生 + 操作符 — 每次拼接创建新 string
        {
            long gcBefore = GC.GetTotalMemory(false);
            string result = "";
            for (int i = 0; i < 1000; i++)
            {
                result = result + i + ","; // 每次循环 2-3 次分配
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  string + string (×1000):   GC diff = {(gcAfter - gcBefore) / 1024} KB");
            volatile string v1 = result;
        }

        // 好: StringBuilder (复用)
        {
            _cachedStringBuilder.Clear();
            long gcBefore = GC.GetTotalMemory(false);
            for (int iter = 0; iter < Iterations / 100; iter++)
            {
                _cachedStringBuilder.Clear();
                for (int i = 0; i < 100; i++)
                {
                    _cachedStringBuilder.Append(i);
                    _cachedStringBuilder.Append(',');
                }
                // 不需要 .ToString()，除非传给需要 string 的 API
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  StringBuilder (复用):      GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // Debug.Log 中的字符串拼接
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 100; i++)
            {
                // 坏: 运行时会拼接
                // Debug.Log("Player " + i + " at position " + i * 2);
                // 好: 条件编译下跳过(但实践中只能减少频率)
                string s = "Player " + i + " at position " + (i * 2);
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  Debug.Log 风格拼接 (×100): GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }
    }

    // ============================================================
    // 5. 基准: 装箱检测
    // ============================================================
    void Benchmark_Boxing_Detection()
    {
        Debug.Log("\n--- 基准 4: 装箱检测 ---");

        // 坏: int → object 装箱
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 10000; i++)
            {
                object boxed = i; // 装箱: value type → reference type
                int unboxed = (int)boxed;
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  int->object 装箱 (×10K):   GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // 坏: 值类型传递给 object 参数
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 10000; i++)
            {
                string s = string.Format("Value: {0}", i); // i 被装箱为 object
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  string.Format (×10K):      GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // 好: 使用泛型或专用重载避免装箱
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 10000; i++)
            {
                // C# 10+ 有插值字符串优化
                string s = $"Value: {i}"; // 编译器可能优化为无装箱路径
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  字符串插值 (×10K):         GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // 坏: Dictionary 中的 enum key 装箱
        {
            var dict = new Dictionary<MyEnum, int>();
            dict[MyEnum.A] = 1; dict[MyEnum.B] = 2;

            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 10000; i++)
            {
                // Dictionary<MyEnum, int> 的 Equals 可能会装箱
                // 解决: 使用 EqualityComparer<MyEnum>.Default 或 IEquatable<MyEnum>
                int val = dict[MyEnum.A];
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  Dict<MyEnum,int> (×10K):   GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }
    }

    enum MyEnum { A, B, C }

    // ============================================================
    // 6. 基准: Camera.main 缓存
    // ============================================================
    void Benchmark_CameraMain()
    {
        Debug.Log("\n--- 基准 5: Camera.main 缓存 ---");

        // 坏: 每帧访问 Camera.main — 内部调用 FindGameObjectsWithTag
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 1000; i++)
            {
                var cam = Camera.main;
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  Camera.main (×1000):       GC diff = {(gcAfter - gcBefore) / 1024} KB (每次触发 FindWithTag)");
        }

        // 好: 缓存在 Start/Awake 中
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 1000; i++)
            {
                var cam = _cachedCamera;
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  cached Camera.main (×1000):GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }
    }

    // ============================================================
    // 7. 基准: 协程 yield 对象
    // ============================================================
    void Benchmark_CoroutineYield()
    {
        Debug.Log("\n--- 基准 6: 协程 yield 对象 ---");

        // 坏: 每次 yield 都 new
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 1000; i++)
            {
                var wait = new WaitForSeconds(1f);
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  new WaitForSeconds (×1K):  GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // 好: 缓存 yield 对象
        {
            WaitForSeconds cachedWait = new WaitForSeconds(1f);
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 1000; i++)
            {
                var wait = cachedWait;
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  cached WaitForSeconds (×1K):GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }
    }

    // ============================================================
    // 8. 基准: 闭包分配
    // ============================================================
    void Benchmark_Closure_Allocation()
    {
        Debug.Log("\n--- 基准 7: 闭包/委托分配 ---");

        int captured = 42;

        // 坏: 捕获外部变量的 lambda — 分配闭包对象
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 10000; i++)
            {
                System.Action action = () => Debug.Log(captured + i);
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  Lambda 捕获变量 (×10K):   GC diff = {(gcAfter - gcBefore) / 1024} KB");
        }

        // 好: 静态方法 / 不捕获变量
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 10000; i++)
            {
                System.Action<int> action = x => Debug.Log(x);
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  Lambda 仅参数 (×10K):     GC diff = {(gcAfter - gcBefore) / 1024} KB (compiler may cache)");
        }

        // 好: 静态本地函数 (C# 8+)
        {
            long gcBefore = GC.GetTotalMemory(false);
            for (int i = 0; i < 10000; i++)
            {
                System.Action<int> action = StaticLog;
            }
            long gcAfter = GC.GetTotalMemory(false);
            Debug.Log($"  静态方法引用 (×10K):      GC diff = {(gcAfter - gcBefore) / 1024} KB");

            static void StaticLog(int x) { /* no capture */ }
        }
    }
}
```

### 运行方式

1. 在 Unity 中创建新场景，添加一个空 GameObject。
2. 将脚本挂载到该 GameObject。
3. 进入 Play Mode，查看 Console 输出。
4. **更精确的方式**: 使用 Unity Profiler（Window → Analysis → Profiler），关注 "GC Alloc" 列，对比不同优化前后的每帧分配量。

### 预期输出

```
========== GC 压力基准测试 ==========
测试次数: 10000

--- 基准 1: foreach vs for (List<int>) ---
  foreach (List<int>):      GC diff = 0 KB
  foreach (IList<int>):      GC diff = 384 KB (慎用接口 foreach!)
  for (int i=0; i<count):    GC diff = 0 KB

--- 基准 2: LINQ vs 手动循环 ---
  LINQ Where+Select:         GC diff = 1024 KB (分配大量迭代器+闭包)
  手动 for + if:             GC diff = 0 KB
  FindAll + foreach:         GC diff = 512 KB (也分配新 List)

--- 基准 3: 字符串拼接 ---
  string + string (×1000):   GC diff = 2048 KB
  StringBuilder (复用):      GC diff = 0 KB
  Debug.Log 风格拼接 (×100): GC diff = 156 KB

--- 基准 4: 装箱检测 ---
  int->object 装箱 (×10K):   GC diff = 384 KB
  string.Format (×10K):      GC diff = 416 KB
  字符串插值 (×10K):         GC diff = 32 KB
  Dict<MyEnum,int> (×10K):   GC diff = 128 KB

--- 基准 5: Camera.main 缓存 ---
  Camera.main (×1000):       GC diff = 256 KB (每次触发 FindWithTag)
  cached Camera.main (×1000):GC diff = 0 KB

--- 基准 6: 协程 yield 对象 ---
  new WaitForSeconds (×1K):  GC diff = 32 KB
  cached WaitForSeconds (×1K):GC diff = 0 KB

--- 基准 7: 闭包/委托分配 ---
  Lambda 捕获变量 (×10K):   GC diff = 384 KB
  Lambda 仅参数 (×10K):     GC diff = 16 KB (compiler may cache)
  静态方法引用 (×10K):      GC diff = 0 KB
```

### GC 优化前后的实际对比摘要

| 优化项 | 每次 GC Alloc (优化前) | 优化后 |
|--------|----------------------|--------|
| `foreach` 遍历 `IList<T>` | ~40B/次 | 0 (改 `IList` 为 `List`) |
| LINQ 链 | ~200B/次 | 0 (手动 for) |
| `string + string` | 随次数增长 | 0 (`StringBuilder`) |
| `Camera.main` 每帧 | ~120B/帧 | 0 (缓存) |
| `new WaitForSeconds` 每帧 | ~24B/帧 | 0 (缓存) |
| 闭包捕获外部变量 | ~40B/次 | 0 (静态方法) |

---
## 3. 练习

### 练习 1: GC Alloc 审计

在现有 Unity 项目中：
1. 打开 Profiler，运行一个典型游戏场景（最好是战斗中或性能敏感场景）。
2. 在 Profiler 的 CPU Usage 区域，打开 "GC Alloc" 列。
3. 排序找出每帧分配最多的 5 个调用。
4. 逐个分析源头并修复——目标是每帧分配量降到原来的 10% 以下。
5. 记录修复前后的 Profiler 截图。

### 练习 2: 实现泛型对象池的 C# 版本

用 C# 实现与第 19 章 C++ 版本等价的 `ObjectPool<T>`：
- 使用 `Stack<T>` 管理空闲对象。
- 支持 `Get()`、`Release(T)`、`Clear()`。
- 与 `UnityEngine.Pool.ObjectPool<T>` 对比 API 设计。
- 基准测试：100K 次 Get/Release 的 GC Alloc 对比 `new T()` 版本（池版本应为 0）。

### 练习 3: 零分配热路径重构（挑战）

选择一个性能敏感的游戏功能（如子弹管理器、技能冷却系统、伤害数字浮动系统）：
- 使用 Unity Profiler 定位 GC Alloc 热点。
- 应用本章所有策略：值类型替代引用类型、缓存引用、避免装箱、避免 LINQ、使用对象池。
- 目标：将关键路径（如每帧 100 个敌人 × 每个 3 发子弹的 Update）的 GC Alloc 降到 **0 bytes**。
- 记录重构前后的代码差异和 Profiler 数据。

---
## 4. 扩展阅读

- **Unity 官方 — Understanding Automatic Memory Management**: https://docs.unity3d.com/Manual/UnderstandingAutomaticMemoryManagement.html — Unity 内 GC 的工作原理和优化建议。
- **Unity 官方 — Incremental Garbage Collection**: https://docs.unity3d.com/Manual/performance-incremental-garbage-collection.html — 增量 GC 的配置和限制。
- **Unity Collections Package**: https://docs.unity3d.com/Packages/com.unity.collections@latest — NativeArray/NativeList 等非托管集合，配合 Jobs/Burst 使用零 GC。
- **"C# in Depth" (Jon Skeet)**, 第 2-3 章 — 深入 C# 值类型/引用类型、装箱、泛型机制。
- **Pro .NET Memory Management (Konrad Kokosa)** — .NET 内存管理的权威著作，涵盖 CoreCLR GC 内部机制。
- **Unreal Engine — Garbage Collection**: https://docs.unrealengine.com/en-US/unreal-engine-garbage-collection/ — UE 的 GC 参考文档。
- **Burst Compiler + Unity Jobs**: https://docs.unity3d.com/Packages/com.unity.burst@latest — 使用 Burst 编译的 Jobs 运行在非托管内存上，天然零 GC。

---
## 常见陷阱

1. **struct 过大**: `struct` 在传递时被复制（值语义）。如果 struct 超过 16-24 字节，复制开销可能超过 GC 节省。Microsoft 建议 struct 不超过 16 字节，且应该是不可变的。
2. **`[HideInInspector]` 的误导**: 标记为隐藏的字段仍然参与序列化，仍可能被 GC 追踪。真正不需要序列化的字段用 `[System.NonSerialized]`。
3. **增量 GC 不是银弹**: 增量 GC 将大暂停拆为小暂停，但总 GC 时间可能更长。如果代码仍在大量分配内存，增量 GC 只是将疼痛分散而非消除。根本解决之道是减少分配。
4. **`Resources.UnloadUnusedAssets()` 的隐藏成本**: 此 API 触发完整的 GC + 资源清理，耗时可达数百毫秒。应该在加载界面等"允许暂停"的时刻调用，不要在游戏中调用。
5. **`GetComponent<T>()` 在某些平台上的隐式 GC**: 正常情况下 `GetComponent<T>` 不分配内存，但 IL2CPP 在某些边角情况下有报告产生 GC Alloc。在热路径中始终缓存结果。
6. **闭包捕获 `this`**: Lambda 中访问任何实例成员（即使是只读属性）都等于捕获 `this`，这比捕获单个字段更重（持有了整个对象的引用，可能阻止该对象被 GC 回收）。
7. **StringBuilder 的 `.ToString()` 分配**: `StringBuilder.ToString()` 返回新 `string`，在高频调用中仍会产生 GC 压力。如果 API 接受 `StringBuilder`，直接传递 `StringBuilder` 而非先转 `string`。
