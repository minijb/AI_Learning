---
title: "多目标框架与条件编译"
updated: 2026-06-10
tags: [dotnet, multi-targeting, conditional-compilation, tfm]
---

# 多目标框架与条件编译

> [!abstract] 本节目标
> 理解 .NET 项目如何同时面向多个框架编译，使用条件编译和条件 `ItemGroup` 在不同运行时下编写适配代码。完成本节后，你能创建多目标类库并为不同平台提供差异化实现。

---

## 概念讲解

### 什么是多目标框架？

一个 .NET 项目默认面向**单个**目标框架（Target Framework Moniker，简称 TFM），例如 `net8.0` 表示面向 .NET 8 运行时。多目标（multi-targeting）允许**同一个** `.csproj` 项目同时编译出**多份**不同 TFM 的程序集。

例如：

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <!-- 注意：是 TargetFrameworks（复数），分号分隔 -->
    <TargetFrameworks>net8.0;net7.0;netstandard2.0</TargetFrameworks>
  </PropertyGroup>
</Project>
```

一次 `dotnet build` 会产出三个文件夹：

```
bin/Debug/
├── net8.0/
│   └── MyLib.dll          ← 供 .NET 8 消费方使用
├── net7.0/
│   └── MyLib.dll          ← 供 .NET 7 消费方使用
└── netstandard2.0/
    └── MyLib.dll          ← 供 .NET Framework 4.6.1+ / .NET Core 2.0+ 消费方使用
```

NuGet 消费方在安装包时，NuGet 会自动选择与其项目 TFM 匹配的程序集。

### 为什么需要多目标？

多目标最常见于**NuGet 类库作者**。场景：

| 场景 | 说明 |
|------|------|
| 库需要兼容旧版 .NET Framework | 企业项目仍跑在 `net48` 上，你的库需要同时支持 `net48` 和 `net8.0` |
| 利用新版 API 但保留旧版回退 | `net8.0` 上用 `System.Text.Json`，`netstandard2.0` 上用 `Newtonsoft.Json` |
| 跨平台适配 | Windows 上做某些事（WPF/WinForms），其他平台不做 |
| 逐步迁移 | 代码逐步添加新 TFM 支持，而不是一次性切换 |

### `TargetFramework` vs `TargetFrameworks`

这是最常犯的错误之一：

- **`TargetFramework`**（单数）：只生成一个 TFM 的程序集
- **`TargetFrameworks`**（复数）：生成多个 TFM，值用分号 `;` 分隔

```xml
<!-- 单目标 -->
<TargetFramework>net8.0</TargetFramework>

<!-- 多目标：注意词尾多了个 's' -->
<TargetFrameworks>net8.0;netstandard2.0</TargetFrameworks>
```

> [!warning] 常见错误
> 误写成 `<TargetFrameworks>net8.0</TargetFrameworks>`（复数但只有一个值）或 `<TargetFramework>net8.0;netstandard2.0</TargetFramework>`（单数但有分号）都不会按预期工作。一个值 → 用单数；多个值 → 用复数。

### 框架标识符一览

以下是常用 TFM 标识符：

| TFM | 对应运行时 | 备注 |
|-----|-----------|------|
| `net8.0` | .NET 8 | 当前 LTS |
| `net7.0` | .NET 7 | 已停止支持 |
| `net6.0` | .NET 6 | LTS，2024年11月停止支持 |
| `netstandard2.1` | .NET Standard 2.1 | .NET Core 3.0+ / Mono 6.4+ / Xamarin 等 |
| `netstandard2.0` | .NET Standard 2.0 | 最广泛兼容：.NET Framework 4.6.1+ / .NET Core 2.0+ / UWP / Xamarin |
| `net48` | .NET Framework 4.8 | 仅 Windows；需要 MSBuild 且安装对应 targeting pack |
| `net472` | .NET Framework 4.7.2 | 同上 |

> [!tip] TFM 选择策略
> 编写 NuGet 类库时，通常从 `netstandard2.0` 起步以获得最大兼容性，然后按需添加 `net8.0` 等现代 TFM 以利用新 API。`netstandard2.1` 的兼容面远小于 `netstandard2.0`，仅在你明确需要且消费方能接受时使用。

### 条件编译：`#if` / `#elif` / `#else` / `#endif`

每个 TFM 在编译时都会自动注入对应的预处理器符号。你可以在 C# 代码中用 `#if` 指令让编译器按 TFM 选择性地包含或排除代码。

#### 自动定义一览

SDK 会根据 `TargetFramework` 自动设置以下符号（将 `.` 和 `-` 替换为 `_` 并转为大写）：

| TFM | 自动定义的预处理器符号 |
|-----|----------------------|
| `net8.0` | `NET8_0`，`NET8_0_OR_GREATER`，`NET7_0_OR_GREATER`，... |
| `net7.0` | `NET7_0`，`NET7_0_OR_GREATER`，... |
| `net6.0` | `NET6_0`，`NET6_0_OR_GREATER`，... |
| `netstandard2.1` | `NETSTANDARD2_1` |
| `netstandard2.0` | `NETSTANDARD2_0` |
| `net48` | `NET48`，`NET48_OR_GREATER` |
| `net472` | `NET472` |

此外还有一些通用符号在所有 TFM 上都可用：

- `DEBUG` — Debug 配置
- `RELEASE` — Release 配置
- `TRACE` — 默认开启

> [!tip] `_OR_GREATER` 系列
> 在 .NET 5+ 上，除了精确版本符号，还会定义 `NET5_0_OR_GREATER`、`NET6_0_OR_GREATER` 等累进符号。写 `#if NET6_0_OR_GREATER` 比逐个列举 `NET6_0 || NET7_0 || NET8_0` 更简洁。

#### 基础示例

```csharp
public static class PlatformInfo
{
    public static string GetRuntimeName()
    {
#if NET8_0
        return ".NET 8.0";
#elif NETSTANDARD2_0
        return ".NET Standard 2.0";
#elif NET48
        return ".NET Framework 4.8";
#else
        return "Unknown";
#endif
    }
}
```

编译 `net8.0` 时，编译器看到的是：

```csharp
public static string GetRuntimeName()
{
    return ".NET 8.0";
}
```

编译 `netstandard2.0` 时，编译器看到的是：

```csharp
public static string GetRuntimeName()
{
    return ".NET Standard 2.0";
}
```

中间的 `#elif` / `#else` / `#endif` 在预处理阶段就被移除了，不产生任何 IL 代码。

#### 条件编译整个类型或方法

`#if` 可以作用于任意代码块，包括整个方法甚至整个类：

```csharp
#if NET8_0
// 整个类型仅在 .NET 8 上存在
public class Net8OnlyFeature
{
    public static string DoSomethingNew()
    {
        // 使用 .NET 8 新增的 API
        return System.Text.Json.JsonSerializer.Serialize(new { Name = "demo" });
    }
}
#endif
```

编译 `netstandard2.0` 时，`Net8OnlyFeature` 这个类**根本不存在**于程序集中——调用方如果用 `netstandard2.0` 会收到编译错误，这正是你想要的效果。

### 条件 `ItemGroup`

除了代码层面的条件编译，你还可以在 `.csproj` 中用 `Condition` 属性对**构建项**做条件区分。

#### 条件包引用

不同 TFM 需要不同的 NuGet 包：

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>net8.0;netstandard2.0</TargetFrameworks>
  </PropertyGroup>

  <!-- netstandard2.0 缺少 System.Text.Json，改用 Newtonsoft.Json -->
  <ItemGroup Condition="'$(TargetFramework)' == 'netstandard2.0'">
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
  </ItemGroup>
</Project>
```

> [!note] `'$(TargetFramework)'` 的值
> 在构建过程中，`$(TargetFramework)` 会依次取 `net8.0` 和 `netstandard2.0` 各构建一次。每次构建时，`Condition` 在该次构建中求值——字符串比较精确匹配当前 TFM。

#### 条件源文件包含

有些源文件只对特定平台有意义：

```xml
<!-- Windows 专用文件，仅在 net8.0-windows 上编译 -->
<ItemGroup Condition="$([MSBuild]::IsOSPlatform('Windows'))">
  <Compile Include="Platforms\**\*.cs" />
</ItemGroup>
```

#### 条件引用程序集

不同 TFM 依赖不同的框架程序集：

```xml
<!-- netstandard2.0 需要额外引用 -->
<ItemGroup Condition="'$(TargetFramework)' == 'netstandard2.0'">
  <Reference Include="System.Net.Http" />
</ItemGroup>
```

### `<DefineConstants>` 自定义符号

除了 SDK 自动注入的符号，你可以用 `DefineConstants` 手动定义自己的预处理器符号：

```xml
<PropertyGroup>
  <DefineConstants>TRACE;MY_FEATURE_FLAG</DefineConstants>
</PropertyGroup>
```

```csharp
#if MY_FEATURE_FLAG
    Console.WriteLine("Feature is ON");
#endif
```

实际工作中常用的自定义场景：

```xml
<!-- Debug 配置下开启额外检测 -->
<PropertyGroup Condition="'$(Configuration)' == 'Debug'">
  <DefineConstants>$(DefineConstants);ENABLE_DIAGNOSTICS</DefineConstants>
</PropertyGroup>
```

> [!warning] 追加而非覆盖
> 使用 `$(DefineConstants);新符号` 语法来**追加**，而不是覆盖 SDK 或之前的定义。如果直接写 `<DefineConstants>MY_FLAG</DefineConstants>` 会把 `TRACE` 等内置符号全部冲掉。

### 按框架构建

多目标项目默认一次构建所有 TFM。你也可以只构建其中一个：

```bash
# 只构建 net8.0
dotnet build -f net8.0

# 只构建 netstandard2.0
dotnet build -f netstandard2.0
```

这在调试某个 TFM 特有的编译错误时非常有用——不必等待所有 TFM 都构建完。

同样适用于 `dotnet test` 和 `dotnet publish`：

```bash
dotnet test -f net8.0
dotnet publish -f net8.0 -c Release
```

### API 可用性检测

条件编译之外，运行时有时也需要检测当前运行的平台——尤其是库代码不确定最终在什么环境下执行时。

```csharp
using System.Runtime.InteropServices;

// 运行时检测（不需要条件编译）
if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
{
    Console.WriteLine("Running on Windows");
}
else if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux))
{
    Console.WriteLine("Running on Linux");
}
```

`System.OperatingSystem`（.NET 5+）提供了更简洁的 API：

```csharp
// 仅在 .NET 5+ 可用
if (OperatingSystem.IsWindows())
    Console.WriteLine("Windows");
else if (OperatingSystem.IsLinux())
    Console.WriteLine("Linux");
else if (OperatingSystem.IsMacOS())
    Console.WriteLine("macOS");
```

> [!tip] 条件编译 vs 运行时检测
> **条件编译**决定哪段代码**存在**于程序集中（编译时决策）；**运行时检测**在已存在的代码中**选择路径**（运行时决策）。如果一个 API 在某个 TFM 上根本不存在（编译就会报错），你必须用 `#if` 排除那段代码；如果 API 存在但行为因平台而异，用运行时检测即可。

此外，一些编译时 attribute 和枚举值也因 TFM 而异。例如 `MethodImplOptions`：

```csharp
using System.Runtime.CompilerServices;

// AggressiveOptimization 在 .NET Core 3.0+ 才可用
#if NETCOREAPP3_0_OR_GREATER || NET5_0_OR_GREATER
[MethodImpl(MethodImplOptions.AggressiveOptimization)]
#endif
public static void HotPath()
{
    // 性能敏感的代码
}
```

在 `netstandard2.0` 上，`MethodImplOptions.AggressiveOptimization` 不存在，必须用 `#if` 排除。

---

## 完整示例：多目标类库

下面从头创建一个多目标类库 `StringUtils`，同时面向 `net8.0` 和 `netstandard2.0`。

### 步骤 1：创建项目

```bash
dotnet new classlib -n StringUtils -o StringUtils
cd StringUtils
```

### 步骤 2：修改 `.csproj`

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <!-- 多目标 -->
    <TargetFrameworks>net8.0;netstandard2.0</TargetFrameworks>
    <ImplicitUsings>disable</ImplicitUsings>
    <RootNamespace>StringUtils</RootNamespace>
  </PropertyGroup>

  <!-- net8.0 启用可空引用类型 -->
  <PropertyGroup Condition="'$(TargetFramework)' == 'net8.0'">
    <Nullable>enable</Nullable>
    <LangVersion>12</LangVersion>
  </PropertyGroup>

  <!-- netstandard2.0 禁用（C# 7.3 不支持） -->
  <PropertyGroup Condition="'$(TargetFramework)' == 'netstandard2.0'">
    <Nullable>disable</Nullable>
    <LangVersion>7.3</LangVersion>
  </PropertyGroup>

  <!-- 仅在 netstandard2.0 上需要 Newtonsoft.Json（net8.0 有内置的 System.Text.Json） -->
  <ItemGroup Condition="'$(TargetFramework)' == 'netstandard2.0'">
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
  </ItemGroup>

</Project>
```

### 步骤 3：编写条件代码

将 `Class1.cs` 替换为：

```csharp
using System;

namespace StringUtils
{
    public static class StringHelper
    {
        /// <summary>
        /// 将对象序列化为 JSON 字符串。
        /// net8.0 使用 System.Text.Json；netstandard2.0 回退到 Newtonsoft.Json。
        /// </summary>
        public static string ToJson(object obj)
        {
            if (obj == null)
                throw new ArgumentNullException(nameof(obj));

#if NET8_0
            return System.Text.Json.JsonSerializer.Serialize(obj);
#elif NETSTANDARD2_0
            return Newtonsoft.Json.JsonConvert.SerializeObject(obj);
#else
            throw new PlatformNotSupportedException("No JSON serializer available for this TFM.");
#endif
        }

        /// <summary>
        /// 返回当前编译目标框架的名称。
        /// </summary>
        public static string GetCurrentFramework()
        {
#if NET8_0
            return "net8.0";
#elif NETSTANDARD2_0
            return "netstandard2.0";
#else
            return "unknown";
#endif
        }

        /// <summary>
        /// 运行时检测当前操作系统 — 仅示例，所有 TFM 都可使用 RuntimeInformation。
        /// </summary>
        public static string GetCurrentOS()
        {
            return System.Runtime.InteropServices.RuntimeInformation.OSDescription;
        }

#if NET8_0
        /// <summary>
        /// 仅在 .NET 8 上可用的方法。
        /// </summary>
        public static string GetDotNetVersion()
        {
            return Environment.Version.ToString();
        }
#endif
    }
}
```

### 步骤 4：构建并验证

```bash
# 构建所有 TFM
dotnet build

# 查看输出
ls bin/Debug/
# Output:
# net8.0/
# netstandard2.0/
```

预期输出：构建成功，0 错误，0 警告，两个 TFM 的程序集各自输出到独立文件夹。

### 步骤 5：消费测试

创建一个控制台项目引用该类库并运行：

```bash
# 在 StringUtils 的同级目录
dotnet new console -n TestApp -o TestApp
cd TestApp
dotnet add reference ../StringUtils/StringUtils.csproj
```

`Program.cs`：

```csharp
using System;
using StringUtils;

Console.WriteLine($"Framework: {StringHelper.GetCurrentFramework()}");
Console.WriteLine($"OS: {StringHelper.GetCurrentOS()}");

var obj = new { Name = "MultiTarget", Version = 1 };
Console.WriteLine($"JSON: {StringHelper.ToJson(obj)}");

#if NET8_0
Console.WriteLine($".NET Version: {StringHelper.GetDotNetVersion()}");
#endif
```

运行：

```bash
dotnet run
```

预期输出：

```
Framework: net8.0
OS: Microsoft Windows 10.0.26100
JSON: {"Name":"MultiTarget","Version":1}
.NET Version: 8.0.x
```

> [!note] 消费方的框架决议
> 当 `TestApp` 是 `net8.0`（或更高）项目时，NuGet/项目引用自动选择 `StringUtils` 的 `net8.0` 构建结果；如果 `TestApp` 是 `net48` 项目，则会选择 `netstandard2.0` 构建结果。

---

## 练习

### 练习 1：添加第三个 TFM

**目标**：在 `StringUtils` 项目中追加 `.NET Framework 4.8`（`net48`）目标，并在 `ToJson` 方法中增加 `#elif NET48` 分支。

> [!warning] 前提
> 编译 `net48` 需要安装 .NET Framework 4.8 targeting pack（通过 Visual Studio Installer 或单独下载）。如果没有，可以用一个你有 targeting pack 的 `net4xx` 代替。

**要求**：
1. 在 `TargetFrameworks` 中添加 `net48`
2. 在 `ToJson` 方法中添加 `#elif NET48` 分支（同样使用 `Newtonsoft.Json`）
3. 构建所有 TFM，确认无错误

**参考提示**：

```xml
<TargetFrameworks>net8.0;netstandard2.0;net48</TargetFrameworks>
```

### 练习 2：条件 `DefineConstants` 控制功能开关

**目标**：在 `StringUtils` 中添加一个 `ENABLE_LOGGING` 自定义符号，并在代码中根据该符号决定是否编译日志输出。

**要求**：
1. 在 `.csproj` 中用 `DefineConstants` 定义 `ENABLE_LOGGING`
2. 在 `ToJson` 方法中用 `#if ENABLE_LOGGING` 添加 `Console.WriteLine("[LOG] Serializing...")`
3. 构建并确认 Debug 输出包含日志、Release 输出不含日志

**提示**：将 `DefineConstants` 放在条件 `PropertyGroup` 中：

```xml
<PropertyGroup Condition="'$(Configuration)' == 'Debug'">
  <DefineConstants>$(DefineConstants);ENABLE_LOGGING</DefineConstants>
</PropertyGroup>
```

### 练习 3：平台条件编译

**目标**：在 `StringUtils` 中新增一个 `PlatformHelper` 类，用 MSBuild 条件检查是否为 Windows，在 Windows 上使用 `System.Media.SystemSounds` 播放提示音（简单调用即可，不需要真的发出声音）。

**要求**：
1. 创建一个 `PlatformHelper.cs`，其中 `#if NET8_0` 内部再用 `if (OperatingSystem.IsWindows())` 做运行时检测
2. 在 `net8.0` 编译中调用 `OperatingSystem.IsWindows()`；在 `netstandard2.0` 回退到 `RuntimeInformation.IsOSPlatform(OSPlatform.Windows)`
3. 创建一个控制台测试程序，调用 `PlatformHelper.IsWindows()` 并打印结果

---

## 扩展阅读

| 资源 | 链接 | 说明 |
|------|------|------|
| MSBuild 条件文档 | https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-conditions | `Condition` 属性的完整语法参考 |
| TFM 官方列表 | https://learn.microsoft.com/en-us/dotnet/standard/frameworks | 所有目标框架标识符及对应映射 |
| 跨平台条件编译 | https://learn.microsoft.com/en-us/dotnet/core/tutorials/libraries#how-to-multitarget | 微软官方 multi-target 教程 |
| .NET Standard 版本兼容表 | https://learn.microsoft.com/en-us/dotnet/standard/net-standard | 各 `netstandard` 版本支持的平台清单 |
| C# 预处理指令 | https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/preprocessor-directives | `#if` / `#define` / `#region` 等完整说明 |
| RuntimeInformation API | https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.runtimeinformation | 运行时 OS/Arch 检测 |
| OperatingSystem API | https://learn.microsoft.com/en-us/dotnet/api/system.operatingsystem | .NET 5+ 的 OS 检测静态方法 |

---

## 常见陷阱

### 1. 预处理器符号名称写错

```csharp
// ❌ 错误 — 符号名是 NET8_0，不是 NET80 或 NET_8_0
#if NET80
// ❌ 错误 — netstandard 符号是 NETSTANDARD2_0，不是 NETSTANDARD_20
#if NETSTANDARD2.0
// ✅ 正确
#if NET8_0
#if NETSTANDARD2_0
```

> [!tip] 如何确认符号名
> 不确定某个 TFM 的预处理器符号叫什么？在代码里写 `#if INVALID_NAME` 然后构建——编译器会在错误信息中列出当前 TFM 可用的所有符号。

### 2. API 在旧 TFM 上不存在

```csharp
// ❌ 错误 — System.Text.Json 在 netstandard2.0 上不存在，编译直接报错
public static string ToJson(object obj)
{
    return System.Text.Json.JsonSerializer.Serialize(obj);
}
```

在 `netstandard2.0` 编译时，`System.Text.Json` 命名空间不存在，编译失败。解决方案：
- 使用 `#if NET8_0` 包裹新 API 调用
- 或在 `netstandard2.0` 上通过 NuGet 安装 `System.Text.Json` 包（.NET Standard 2.0 版）

### 3. 忘记构建所有目标就发布

多目标项目在开发时可能只调试 `net8.0`，但发布 NuGet 包前**必须**确认所有 TFM 都能通过编译：

```bash
# 仅构建 net8.0 — 可能隐藏 netstandard2.0 的编译错误
dotnet build -f net8.0

# 始终在发布前执行全量构建
dotnet build
dotnet test
```

> [!danger] CI 中的教训
> 在 CI/CD 管道中，务必运行无 `-f` 参数的 `dotnet build`，否则可能只构建了单个 TFM 并漏掉了其他目标框架的编译错误。

### 4. `LangVersion` 不一致导致编译失败

```xml
<!-- ❌ 全局 LangVersion 设为 latest，netstandard2.0 使用 C# 7.3 编译器会导致不兼容 -->
<PropertyGroup>
  <TargetFrameworks>net8.0;netstandard2.0</TargetFrameworks>
  <LangVersion>latest</LangVersion>
</PropertyGroup>
```

不同 TFM 的默认 C# 版本不同（netstandard2.0 → C# 7.3，net8.0 → C# 12）。应条件化设置：

```xml
<PropertyGroup Condition="'$(TargetFramework)' == 'net8.0'">
  <LangVersion>12</LangVersion>
</PropertyGroup>
<PropertyGroup Condition="'$(TargetFramework)' == 'netstandard2.0'">
  <LangVersion>7.3</LangVersion>
</PropertyGroup>
```

### 5. 条件 `ItemGroup` 中的字符串比较大小写

```xml
<!-- ✅ 正确 — TFM 值统一为小写 -->
<ItemGroup Condition="'$(TargetFramework)' == 'net8.0'">

<!-- ❌ 虽然碰巧工作，但依赖未文档化的行为 —— 不要加空格 -->
<ItemGroup Condition="'$(TargetFramework)' == ' net8.0 '">
```

### 6. `DefineConstants` 覆盖默认值

```xml
<!-- ❌ 直接赋值覆盖了 TRACE 等内置符号 -->
<PropertyGroup>
  <DefineConstants>MY_FLAG</DefineConstants>
</PropertyGroup>

<!-- ✅ 使用 $(DefineConstants) 追加 -->
<PropertyGroup>
  <DefineConstants>$(DefineConstants);MY_FLAG</DefineConstants>
</PropertyGroup>
```

---

> [!summary] 小结
> - `TargetFrameworks`（复数）实现一次编码、多个 TFM 编译
> - `#if NET8_0` / `#elif NETSTANDARD2_0` 做编译期代码排除
> - `Condition="'$(TargetFramework)' == 'net8.0'"` 做构建期项排除
> - 运行时检测（`RuntimeInformation`、`OperatingSystem`）处理同代码中不同平台逻辑
> - 发布前永远 `dotnet build` 所有目标，不要依赖 `-f` 单框架构建
