---
title: P/Invoke 实战（DllImport + 跨平台编译）
updated: 2026-06-18
tags: [interop, pinvoke, dllimport, marshalling, csharp, cpp]
aliases: []
---

# P/Invoke 实战（DllImport + 跨平台编译）

> 所属计划: [[plan|C 系语言互操作与编译学习计划]]
> 预计耗时: 90 min
> 前置知识: 第 `02` 节、第 `03` 节

---

## 1. 概念讲解

在 [[research-brief|研究简报 §4]] 里，P/Invoke 被描述为 **"C# 调用原生 C/C++ 函数的官方机制"**。它的本质并不神秘：CLR 在托管代码与原生机器码之间插入一段薄层（stub），负责把 C# 的对象/类型转换成 C 能理解的布局，然后像调用普通函数一样跳过去。

### 为什么需要这个？

C# 跑在 CLR 上，有 GC、类型系统、内存压缩；C/C++ 直接面对裸内存、手动管理资源。两者不可能直接共享对象。如果你需要：

- 复用一个已有的 C/C++ 算法库（物理引擎、编解码、图像处理）。
- 调用操作系统专属 API（Win32、POSIX）。
- 在 Unity / .NET 里榨取原生代码的峰值性能。

就必须有一个**中立边界**把两边隔开。P/Invoke 就是 .NET 提供的这座桥——桥的两端都讲 C ABI。

### 核心思想

调用链只有四步：

```mermaid
flowchart LR
    subgraph "C# 托管代码"
        A["`[DllImport('mylib')]`<br/>`static extern float PointDistance(...)`"]
    end
    subgraph "CLR"
        B["IL stub<br/>（首次调用生成）<br/>参数封送 / pin"]
    end
    subgraph "原生世界"
        C["动态库<br/>mylib.dll / libmylib.so"]
    end
    A -->|"P/Invoke 请求"| B
    B -->|"jmp / call"| C
    C -->|"原生返回"| B
    B -->|"反向封送"| A
```

第 `` `#1` `` 次调用某个 `[DllImport]` 方法时，CLR 会**动态生成一段 IL stub**。这段 stub 做三件事：

1. **参数封送**：把 `string` 转成 `char*`、把 `bool` 转成平台相关宽度、把结构体按 `[StructLayout]` 拍平到栈/寄存器。
2. **Pin 住托管内存**：对 blittable 数组/结构体，在调用期间固定地址，防止 GC 移动。
3. **跳板调用**：按调用约定压栈/填寄存器，跳进原生函数；返回后再反向封送结果。

> [!note]
> 这个 stub 是运行时生成的，所以启动第 `` `#1` `` 次调用会有一点点额外开销；后续调用会走已编译好的路径。下一节的 `LibraryImport` 源生成器会把这份开销从运行时挪到编译期。

### `[DllImport]` 关键字段

| 字段 | 作用 | 常见取值 / 建议 |
|------|------|----------------|
| `EntryPoint` | 指定原生导出的符号名。当 C# 方法名与原生符号不一致，或想导出重载的 C 函数时使用。 | `"point_distance"` |
| `CallingConvention` | 告诉 stub 按哪种约定压栈/清理。 | `CallingConvention.Cdecl`（C/C++ 默认，跨平台惯例） |
| `CharSet` | 控制字符串封送编码；现代代码更推荐显式 `[MarshalAs]`。 | `CharSet.Unicode` / `CharSet.Ansi` |
| `SetLastError` | 调用结束后让 CLR 捕获 `GetLastError()` / `errno`，供 `Marshal.GetLastPInvokeError()` 读取。 | `true`（只要原生侧用错误码） |
| `ExactSpelling` | 为 `true` 时不会自动尝试追加 `A`/`W` 后缀匹配 ANSI/Unicode 版本。 | 通常保持默认即可 |

### 复杂类型封送

| 场景 | C# 声明要点 | 关键属性 |
|------|-------------|----------|
| 结构体 | `[StructLayout(LayoutKind.Sequential)] struct Point { public float X, Y; }` | `Pack`、`CharSet` 控制对齐 |
| blittable 数组 | `byte[]`、`int[]` | 自动 pin，调用期间直接传指针 |
| 字符串入参 | `string name` + `[MarshalAs(UnmanagedType.LPUTF8Str)]` | 跨平台推荐 UTF-8 |
| 字符串出参（预分配缓冲） | `byte[] outBuffer` 或 `IntPtr` | 调用方负责缓冲大小与释放 |
| 原生分配的内存 | `IntPtr` + `Marshal.PtrToStringUTF8` / `NativeMemory.Free` | 必须明确所有权 |
| 二进制兼容指针 | `IntPtr`、`unsafe void*` | 零封送，性能最高 |

> [!tip]
> 结构体默认布局是 `LayoutKind.Auto`，CLR 会重新排列字段，**绝对不能直接传给原生代码**。必须显式标记 `Sequential` 或 `Explicit`。

### 错误处理：`SetLastError`

C 风格错误通常是 **"返回值 + 全局/线程错误码"**：

- Windows：`SetLastError(dw)` → C# `Marshal.GetLastWin32Error()`（旧）或 `Marshal.GetLastPInvokeError()`（.NET 6+）。
- Linux/macOS：`errno` → 同样通过 `Marshal.GetLastPInvokeError()` 读取。

只要 `[DllImport(..., SetLastError = true)]`，CLR 就会在原生调用结束后帮你把线程错误码保存下来，托管代码里再读取即可。

### 绝对不能踩的红线：C++ 异常跨边界

C++ 异常携带栈展开信息、析构调用，**绝不能越过 P/Invoke 边界回到 CLR**。一旦原生函数里抛出的异常没被捕获，行为是未定义的：

- Windows：可能直接 `STATUS_UNHANDLED_EXCEPTION` 崩溃。
- Linux/macOS：可能触发 `std::terminate`，进程被 `abort()`。

> [!danger]
> **原生侧必须 `try/catch(...)` 吞掉异常并返回错误码。** 这是 P/Invoke 设计里的硬性规则，没有例外。

---

## 2. 代码示例

下面两个示例都是**独立可运行**的最小项目。环境要求：

- .NET 8 SDK
- CMake 3.16+
- Windows：MSVC 2019+（Visual Studio 或 Build Tools）
- Linux：GCC 11+ 或 Clang 14+

### 示例 1：结构体 + 跨平台动态库

实现一个 C 库，导出 `point_distance(Point a, Point b)`；C# 侧用 `[StructLayout(Sequential)]` 定义镜像结构体，通过 P/Invoke 调用。

#### 原生库：`PointLib/pointlib.h`

```cpp
#pragma once

#ifdef _WIN32
    #define API __declspec(dllexport)
#else
    #define API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float x;
    float y;
} Point;

API float point_distance(Point a, Point b);

#ifdef __cplusplus
}
#endif
```

#### 原生库：`PointLib/pointlib.cpp`

```cpp
#include "pointlib.h"
#include <cmath>

float point_distance(Point a, Point b)
{
    float dx = a.x - b.x;
    float dy = a.y - b.y;
    return std::sqrt(dx * dx + dy * dy);
}
```

#### 原生库：`PointLib/CMakeLists.txt`

```cmake
cmake_minimum_required(VERSION 3.16)
project(PointLib LANGUAGES CXX)

add_library(mylib SHARED pointlib.cpp pointlib.h)
set_target_properties(mylib PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
)

# 保持跨平台命名一致：Windows -> mylib.dll；Linux -> libmylib.so
if(NOT WIN32)
    set_target_properties(mylib PROPERTIES PREFIX "lib")
endif()
```

#### C# 宿主：`PointDemo/Program.cs`

```csharp
using System;
using System.Reflection;
using System.Runtime.InteropServices;

namespace PointDemo
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Point
    {
        public float X;
        public float Y;
    }

    public static class Native
    {
        static Native()
        {
            NativeLibrary.SetDllImportResolver(typeof(Native).Assembly, ResolveLibrary);
        }

        private static IntPtr ResolveLibrary(string libraryName, Assembly assembly, DllImportSearchPath? searchPath)
        {
            if (libraryName != "mylib")
                return IntPtr.Zero; // 让运行时走默认解析

            string file = OperatingSystem.IsWindows() ? "mylib.dll"
                : OperatingSystem.IsLinux() ? "libmylib.so"
                : throw new PlatformNotSupportedException();

            return NativeLibrary.Load(file);
        }

        [DllImport("mylib",
            EntryPoint = "point_distance",
            CallingConvention = CallingConvention.Cdecl)]
        public static extern float PointDistance(Point a, Point b);
    }

    class Program
    {
        static void Main()
        {
            Point a = new() { X = 0.0f, Y = 0.0f };
            Point b = new() { X = 3.0f, Y = 4.0f };

            float distance = Native.PointDistance(a, b);
            Console.WriteLine($"distance = {distance}");
        }
    }
}
```

#### 运行方式

**Windows（MSVC，PowerShell / cmd）：**

```bash
cd PointLib
mkdir build && cd build
cmake .. -A x64
cmake --build . --config Release
# 把 PointLib\build\Release\mylib.dll 复制到 PointDemo\ 目录下
cd ..\..\PointDemo
dotnet run
```

**Linux（GCC）：**

```bash
cd PointLib
mkdir build && cd build
cmake ..
cmake --build .
# 把 PointLib/build/libmylib.so 复制到 PointDemo/ 目录下
cd ../../PointDemo
dotnet run
```

#### 预期输出

```text
distance = 5
```

---

### 示例 2：字符串缓冲 + 错误码

原生函数 `greet(const char* name, char* out, int outlen)` 把问候语写入调用方提供的缓冲，返回 `0` 表示成功，非零表示错误。C# 侧演示 `SetLastError` 与 `Marshal.GetLastPInvokeError()`。

#### 原生库：`GreetLib/greetlib.h`

```cpp
#pragma once

#ifdef _WIN32
    #define API __declspec(dllexport)
    #include <windows.h>
#else
    #define API __attribute__((visibility("default")))
    #include <cerrno>
#endif

#ifdef __cplusplus
extern "C" {
#endif

API int greet(const char* name, char* out, int outlen);

#ifdef __cplusplus
}
#endif
```

#### 原生库：`GreetLib/greetlib.cpp`

```cpp
#include "greetlib.h"
#include <cstdio>

int greet(const char* name, char* out, int outlen)
{
    if (!name || !out || outlen <= 0)
    {
#ifdef _WIN32
        SetLastError(1);
#else
        errno = 1;
#endif
        return 1;
    }

    int n = snprintf(out, static_cast<size_t>(outlen), "Hello, %s!", name);
    if (n < 0 || n >= outlen)
    {
#ifdef _WIN32
        SetLastError(2);
#else
        errno = 2;
#endif
        return 2;
    }

    return 0;
}
```

#### 原生库：`GreetLib/CMakeLists.txt`

```cmake
cmake_minimum_required(VERSION 3.16)
project(GreetLib LANGUAGES CXX)

add_library(greetlib SHARED greetlib.cpp greetlib.h)
set_target_properties(greetlib PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
)

if(NOT WIN32)
    set_target_properties(greetlib PROPERTIES PREFIX "lib")
endif()
```

#### C# 宿主：`GreetDemo/Program.cs`

```csharp
using System;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

namespace GreetDemo
{
    class Program
    {
        static Program()
        {
            NativeLibrary.SetDllImportResolver(typeof(Program).Assembly, (name, asm, path) =>
            {
                if (name != "greetlib")
                    return IntPtr.Zero;

                string file = OperatingSystem.IsWindows() ? "greetlib.dll"
                    : OperatingSystem.IsLinux() ? "libgreetlib.so"
                    : throw new PlatformNotSupportedException();

                return NativeLibrary.Load(file);
            });
        }

        [DllImport("greetlib",
            CallingConvention = CallingConvention.Cdecl,
            SetLastError = true)]
        static extern int greet(
            [MarshalAs(UnmanagedType.LPUTF8Str)] string name,
            byte[] outBuffer,
            int outlen);

        static void Main()
        {
            byte[] buffer = new byte[64];
            int rc = greet("P/Invoke", buffer, buffer.Length);

            if (rc != 0)
            {
                Console.WriteLine($"greet failed: rc={rc}, last error={Marshal.GetLastPInvokeError()}");
                return;
            }

            int zeroIndex = buffer.AsSpan().IndexOf((byte)0);
            int length = zeroIndex >= 0 ? zeroIndex : buffer.Length;
            string text = Encoding.UTF8.GetString(buffer, 0, length);
            Console.WriteLine($"result: {text}");

            // 演示错误路径：缓冲太小
            byte[] tiny = new byte[4];
            int rc2 = greet("P/Invoke", tiny, tiny.Length);
            if (rc2 != 0)
            {
                Console.WriteLine($"truncated greet: rc={rc2}, last error={Marshal.GetLastPInvokeError()}");
            }
        }
    }
}
```

#### 运行方式

与示例 1 相同，只需把 `PointLib` 换成 `GreetLib`，把 `PointDemo` 换成 `GreetDemo`。

#### 预期输出

```text
result: Hello, P/Invoke!
truncated greet: rc=2, last error=2
```

---

## 3. 练习

### 练习 1: 编译并调用距离函数

按示例 1 建立 `PointLib` 与 `PointDemo`，在 Windows 或 Linux 上编译出动态库，并从 C# 正确输出 `distance = 5`。尝试修改两个点的坐标，确认结果与勾股定理一致。

### 练习 2: 观察 C++ 异常跨边界并修复

把示例 1 的 `point_distance` 改成内部 `throw std::runtime_error("boom");`，重新编译并运行 C# 程序，观察进程崩溃/异常终止现象。随后在原函数内部用 `try { ... } catch (...) { return -1.0f; }` 捕获所有异常并返回错误码，确认 C# 侧能安全收到 `-1` 而不再崩溃。

### 练习 3: 封送含定长数组的结构体（挑战）

定义一个 C 结构体：

```c
struct Buf {
    int data[4];
};
```

并在原生侧实现 `void buf_double(Buf* b)`，把数组每个元素乘以 2。C# 侧用 `[StructLayout]` + `[MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]` 定义镜像结构体，通过 `ref Buf` 调用，验证调用后 `data` 内容确实被修改。

---

## 3.5 参考答案

> 参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

> [!tip]- 练习 1 参考答案
> 完整代码与示例 1 一致。关键检查点：
> - C++ 头文件用 `extern "C"` 关闭名称重整。
> - C# 结构体标记 `[StructLayout(LayoutKind.Sequential)]`。
> - `[DllImport]` 的 `CallingConvention` 写 `Cdecl`。
> - 编译后把动态库放在 C# 程序能找到的位置（同一目录或配置 `NativeLibrary.SetDllImportResolver`）。

> [!tip]- 练习 2 参考答案
> 会触发崩溃的版本（C++）：
> ```cpp
> #include "pointlib.h"
> #include <cmath>
> #include <stdexcept>
>
> float point_distance(Point a, Point b)
> {
>     throw std::runtime_error("boom");
>     float dx = a.x - b.x;
>     float dy = a.y - b.y;
>     return std::sqrt(dx * dx + dy * dy);
> }
> ```
> 运行 `dotnet run` 后，原生异常会向上穿透 CLR，进程通常会直接终止。
>
> 修复版本：
> ```cpp
> #include "pointlib.h"
> #include <cmath>
> #include <stdexcept>
>
> float point_distance(Point a, Point b)
> {
>     try
>     {
>         if (a.x < 0)
>             throw std::runtime_error("negative x is not allowed");
>
>         float dx = a.x - b.x;
>         float dy = a.y - b.y;
>         return std::sqrt(dx * dx + dy * dy);
>     }
>     catch (...)
>     {
>         return -1.0f;
>     }
> }
> ```
> C# 侧把 `a.X` 改成负数即可验证返回 `-1`：
> ```csharp
> Point a = new() { X = -1.0f, Y = 0.0f };
> Point b = new() { X = 3.0f, Y = 4.0f };
> Console.WriteLine($"distance = {Native.PointDistance(a, b)}");
> ```

> [!tip]- 练习 3 参考答案
> 原生头文件：
> ```cpp
> #pragma once
>
> #ifdef _WIN32
>     #define API __declspec(dllexport)
> #else
>     #define API __attribute__((visibility("default")))
> #endif
>
> #ifdef __cplusplus
> extern "C" {
> #endif
>
> typedef struct {
>     int data[4];
> } Buf;
>
> API void buf_double(Buf* b);
>
> #ifdef __cplusplus
> }
> #endif
> ```
>
> 原生实现：
> ```cpp
> #include "buflib.h"
>
> void buf_double(Buf* b)
> {
>     if (!b) return;
>     for (int i = 0; i < 4; ++i)
>         b->data[i] *= 2;
> }
> ```
>
> C# 侧：
> ```csharp
> using System;
> using System.Runtime.InteropServices;
>
> [StructLayout(LayoutKind.Sequential)]
> struct Buf
> {
>     [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
>     public int[] Data;
> }
>
> class Program
> {
>     [DllImport("buflib", CallingConvention = CallingConvention.Cdecl)]
>     static extern void buf_double(ref Buf b);
>
>     static void Main()
>     {
>         Buf b = new Buf { Data = new int[] { 1, 2, 3, 4 } };
>         buf_double(ref b);
>         Console.WriteLine(string.Join(", ", b.Data));
>     }
> }
> ```
>
> 预期输出：
> ```text
> 2, 4, 6, 8
> ```

---

## 4. 扩展阅读

- [官方文档: P/Invoke 概述](https://learn.microsoft.com/dotnet/standard/native-interop/pinvoke)
- [官方文档: DllImportAttribute 类](https://learn.microsoft.com/dotnet/api/system.runtime.interopservices.dllimportattribute)
- [官方文档: MarshalAsAttribute 类](https://learn.microsoft.com/dotnet/api/system.runtime.interopservices.marshalasattribute)
- [官方文档: StructLayoutAttribute 类](https://learn.microsoft.com/dotnet/api/system.runtime.interopservices.structlayoutattribute)
- [官方文档: 使用 blittable 和 non-blittable 类型](https://learn.microsoft.com/dotnet/standard/native-interop/best-practices#blittable-and-non-blittable-types)
- [Microsoft Learn: 平台调用数据类型](https://learn.microsoft.com/dotnet/standard/native-interop/type-marshalling)
- [.NET Runtime 源码: DllImport 解析与 stub 生成](https://github.com/dotnet/runtime/tree/main/src/coreclr/vm/dllimport.cpp)

---

## 常见陷阱

- **C++ 异常跨 P/Invoke 边界**：原生函数里抛出的 `std::exception` 或任意异常不能被 CLR 理解，会导致未定义行为甚至进程崩溃。**正确做法**：原生侧 `try/catch(...)` 捕获后返回错误码，C# 侧检查返回值。

- **找不到符号**：运行时提示 `Unable to find an entry point named 'xxx' in DLL`。常见原因：
  - 忘了 `extern "C"`，C++ 把函数名重整成 `?xxx@@...`。
  - C# 的 `EntryPoint` 写错。
  - 库文件不在搜索路径（没有复制到输出目录、或 `NativeLibrary` 没解析到）。
  **正确做法**：先用 `dumpbin /exports` 或 `nm -D` 确认导出名；必要时用 `NativeLibrary.SetDllImportResolver` 显式加载。

- **结构体布局不一致**：C# 结构体字段顺序、对齐（`Pack`）与原结构体不同，导致读错内存。**正确做法**：显式 `[StructLayout(LayoutKind.Sequential, Pack = N)]`，必要时用 `LayoutKind.Explicit` + `FieldOffset`。

- **`SetLastError` 误用**：只在原生侧真的会设置 `GetLastError()` / `errno` 时才开；开了之后必须立即用 `Marshal.GetLastPInvokeError()` 读取，否则 CLR 里下一次 P/Invoke 会覆盖它。不要用返回值成功后去读取上一次的残留错误码。

- **字符串默认编码踩坑**：`string` 默认在 Windows 上可能走 ANSI，导致 Linux 上乱码。**正确做法**：跨平台传字符串显式用 `[MarshalAs(UnmanagedType.LPUTF8Str)]`，或在热路径直接传 `ReadOnlySpan<byte>` / `byte[]`。

- **把非 blittable 类型当成 blittable 传**：例如 `bool` 默认是 4 字节 Win32 `BOOL`，Linux 上可能不对；`char` 宽度也取决于 `CharSet`。**正确做法**：对互操作结构体，字段类型尽量只用 `byte/sbyte/short/ushort/int/uint/long/ulong/IntPtr/float/double` 这些 blittable 类型。
