---
title: "dotnet publish / pack — 发布与打包"
updated: 2026-06-10
tags: [dotnet, cli, publish, pack, nuget, deployment]
---

# dotnet publish / pack — 发布与打包

> [!abstract] 本节目标
> 掌握 `dotnet publish` 的六种部署模式及其适用场景，学会将类库打包为 NuGet 包并推送到仓库。完成本节后，你能将任何 .NET 项目发布为可部署产物，能将类库发布为团队共享的 NuGet 包。

前置知识：[[06-csproj-and-sln-deep-dive]]

---

## 一、概念讲解

### 1.1 `dotnet publish` 是什么

`dotnet publish` 将项目编译、整理依赖，输出一个**可直接部署运行**的文件夹。和 `dotnet build` 不同：

| | `dotnet build` | `dotnet publish` |
|---|---|---|
| 产物用途 | 开发调试 | 部署到目标环境 |
| 包含运行时 | 否 | 取决于模式 |
| 优化级别 | Debug (默认) | Release (通常) |
| 依赖修剪 | 否 | 可选 (`PublishTrimmed`) |
| 单文件打包 | 否 | 可选 (`PublishSingleFile`) |

本质上 `publish` = `build` + 依赖解析 + 裁剪 + 打包。它触发与 build 相同的 MSBuild 目标，然后额外执行发布步骤。

### 1.2 六种部署模式

理解每种模式的取舍是 `dotnet publish` 的核心。下表以 Linux x64、.NET 8 控制台应用为例：

| 模式 | 命令标志 | 产出大小 | 需要目标安装 .NET Runtime | 启动速度 |
|------|----------|----------|--------------------------|---------|
| **FDD** (Framework-Dependent) | (默认) | ~150 KB | 是 | 正常 |
| **SCD** (Self-Contained) | `--self-contained` | ~65 MB | 否 | 正常 |
| **Single-File** | `-p:PublishSingleFile=true` | ~150 KB / ~65 MB | 依赖 FDD/SCD | 首次较慢(解压) |
| **Trimmed** | `-p:PublishTrimmed=true` | ~10–25 MB (SCD) | 否 | 正常 |
| **ReadyToRun** | `-p:PublishReadyToRun=true` | 略大 | 依赖 FDD/SCD | **更快** |
| **Native AOT** | `-p:PublishAot=true` | ~3–8 MB | 否 | **最快** |

#### FDD — Framework-Dependent Deployment（默认）

只产出你的代码 + 第三方依赖的 DLL。目标机器必须安装对应版本的 .NET Runtime。

```bash
dotnet publish -c Release
```

**产物示例（win-x64 FDD）**：

```
publish/
├── MyApp.exe              # 宿主可执行文件（Windows）
├── MyApp.dll              # 你的程序集
├── MyApp.deps.json        # 依赖清单
├── MyApp.runtimeconfig.json  # 运行时配置（指定需要的 .NET 版本）
├── Newtonsoft.Json.dll    # 第三方依赖
└── ...
```

`.runtimeconfig.json` 声明了所需 runtime 版本：

```json
{
  "runtimeOptions": {
    "tfm": "net8.0",
    "framework": {
      "name": "Microsoft.NETCore.App",
      "version": "8.0.0"
    }
  }
}
```

> [!tip] FDD 的优势
> 产出体积小（~150 KB 不含依赖），可以跨平台（只要目标机器装了 .NET Runtime），服务端批量部署时节省磁盘和带宽。

#### SCD — Self-Contained Deployment

将 .NET Runtime 一同打包，目标机器**无需安装 .NET**。

```bash
dotnet publish -c Release --self-contained -r win-x64
```

**产物对比（同一项目）**：

```
publish/                       # FDD: ~500 KB (含所有 NuGet 依赖)
publish/                       # SCD: ~65 MB (含完整 runtime)
├── MyApp.exe
├── MyApp.dll
├── coreclr.dll                # CoreCLR 运行时
├── System.Private.CoreLib.dll # BCL 核心库
├── clrjit.dll                 # JIT 编译器
├── hostfxr.dll                # Host 框架解析器
└── ...300+ 文件
```

> [!warning] SCD 的代价
> 每个 SCD 应用都带一份完整的 runtime（~65 MB），磁盘和带宽成本高。但换来的是"解压即用"——不需要预装 .NET，适合客户端分发。

#### Single-File — 单文件发布

将所有产出**打包成一个可执行文件**。既可以与 FDD 结合（小文件 + 需要 runtime），也可以与 SCD 结合（大文件 + 独立运行）。

```bash
# FDD 单文件（约 150 KB 的 exe + 目标机器需要 .NET 8）
dotnet publish -c Release -p:PublishSingleFile=true

# SCD 单文件（约 65 MB，完全独立）
dotnet publish -c Release -p:PublishSingleFile=true --self-contained -r win-x64
```

> [!tip] 单文件原理
> 发布时将程序集和资源嵌入宿主可执行文件。首次运行时解压到临时目录，后续运行复用缓存——所以**第二次启动更快**。

#### Trimmed — 程序集裁剪

移除未使用的代码路径，显著缩小 SCD 体积。

```bash
dotnet publish -c Release -p:PublishTrimmed=true --self-contained -r win-x64
```

**效果**（一个简单的"Hello World"控制台应用）：

```
SCD 未裁剪:  ~65 MB
SCD + 裁剪:  ~10 MB  ← 体积缩减 85%
```

> [!warning] 裁剪的兼容性风险
> 裁剪依赖静态分析，**无法检测反射调用的代码**。如果你的代码或依赖使用了反射（如 `Assembly.Load`、`Type.GetMethod`、JSON 序列化器的动态绑定），裁剪可能错误移除所需代码，导致运行时 `MissingMethodException`。必须通过 `<TrimmerRootAssembly>` 或 `DynamicallyAccessedMembers` 标注保留。

#### ReadyToRun (R2R)

预编译 IL 为本机代码（提前编译部分方法），**牺牲体积换启动速度**。

```bash
dotnet publish -c Release -p:PublishReadyToRun=true -r win-x64
```

> [!tip] R2R vs 裁剪 vs AOT
> - **R2R**：IL + 预编译代码并存，JIT 仍参与。兼容性最好，体积略大。
> - **Trimmed**：移除未用 IL 代码。兼容性有风险，体积缩小明显。
> - **AOT**：完全移除 JIT 和 IL。兼容性最受限，体积最小、启动最快。

#### Native AOT — 本机提前编译

将 C# 代码**直接编译为本机二进制**（无 JIT、无 IL），类似 C++ 编译。

```bash
dotnet publish -c Release -p:PublishAot=true -r win-x64
```

**特点**：

```
启动时间:  ~0.1s（AOT）vs ~1s（JIT）
内存占用:  显著降低（无 JIT 开销）
磁盘体积:  ~3–8 MB（小型应用）
```

> [!warning] AOT 的限制
> AOT 不支持：
> - 运行时反射发出（`AssemblyBuilder`、`ILGenerator`）
> - 动态加载程序集（`Assembly.LoadFrom`）
> - 某些序列化器（如 `BinaryFormatter`）
> - 所有代码必须在编译时可知——`MakeGenericType` 等不受支持
>
> 适用于 CLI 工具、微服务、游戏脚本宿主等场景，不适合使用大量动态特性的框架。

### 1.3 常用选项速查

| 选项 | 说明 | 示例 |
|------|------|------|
| `-c` / `--configuration` | 生成配置 | `-c Release` |
| `-r` / `--runtime` | 目标运行时标识符 (RID) | `-r linux-x64` |
| `--self-contained` | 自包含部署 | `--self-contained` |
| `--no-self-contained` | 强制 FDD | `--no-self-contained` |
| `-o` / `--output` | 输出目录 | `-o ./out` |
| `-p:PublishSingleFile=true` | 单文件发布 | 见上文 |
| `-p:PublishTrimmed=true` | 程序集裁剪 | 见上文 |
| `-p:PublishReadyToRun=true` | R2R 编译 | 见上文 |
| `-p:PublishAot=true` | Native AOT | 见上文 |
| `--no-restore` | 跳过隐式还原 | 加快 CI |
| `--sc` | `--self-contained` 的缩写 | 同义 |
| `--version-suffix` | 设置版本后缀 | `--version-suffix beta1` |

### 1.4 运行时标识符 (RID)

RID 指定目标的**操作系统 + 架构**。常用的：

| RID | 目标平台 |
|-----|---------|
| `win-x64` | Windows x64 |
| `win-x86` | Windows x86 |
| `win-arm64` | Windows ARM64 |
| `linux-x64` | Linux x64 (glibc) |
| `linux-musl-x64` | Linux x64 (Alpine/musl) |
| `linux-arm64` | Linux ARM64 |
| `osx-x64` | macOS Intel |
| `osx-arm64` | macOS Apple Silicon |

跨平台发布示例：

```bash
# 在 Windows 上发布 Linux 版本
dotnet publish -c Release -r linux-x64 --self-contained -o ./publish/linux

# 发布 macOS ARM 版本
dotnet publish -c Release -r osx-arm64 --self-contained -o ./publish/macos
```

> [!tip] 查看支持的全部 RID
> 在项目目录执行 `dotnet publish -r` 后按 Tab（通过 shell 补全查看），或查阅 [.NET RID Catalog](https://learn.microsoft.com/en-us/dotnet/core/rid-catalog)。

### 1.5 `.csproj` 中的发布配置

将发布选项固化到 `.csproj`，避免每次输入长命令行：

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>

    <!-- 发布配置 -->
    <PublishSingleFile>true</PublishSingleFile>
    <PublishTrimmed>true</PublishTrimmed>
    <SelfContained>true</SelfContained>
    <RuntimeIdentifier>win-x64</RuntimeIdentifier>

    <!-- 可选：AOT -->
    <!-- <PublishAot>true</PublishAot> -->
  </PropertyGroup>

</Project>
```

固化后只需：

```bash
dotnet publish -c Release
```

> [!tip] 有条件的发布配置
> 可以按配置区分发布行为：
>
> ```xml
> <PropertyGroup Condition="'$(Configuration)' == 'Release'">
>   <PublishSingleFile>true</PublishSingleFile>
> </PropertyGroup>
> ```

---

## 二、`dotnet pack` — 类库打包

### 2.1 什么是 NuGet 包

NuGet 包（`.nupkg`）本质是一个 ZIP 压缩包，内部结构：

```
MyLibrary.1.0.0.nupkg
├── MyLibrary.nuspec          # 包元数据（XML）
├── lib/
│   └── net8.0/
│       ├── MyLibrary.dll     # 程序集
│       └── MyLibrary.xml     # XML 文档（可选）
├── contentFiles/             # 内容文件（可选）
├── tools/                    # 工具（可选）
└── [Content_Types].xml       # OPC 内容类型
```

`dotnet pack` 读取 `.csproj` 中的元数据，编译项目，打包为 `.nupkg`。

### 2.2 基本用法

```bash
# 创建一个类库
dotnet new classlib -n MyLibrary
cd MyLibrary

# 打包
dotnet pack -c Release
```

默认输出到 `bin/Release/net8.0/MyLibrary.1.0.0.nupkg`。

### 2.3 包元数据配置

在 `.csproj` 中设置元数据（**无这些字段 pack 会成功但生成警告**）：

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>

    <!-- 核心 NuGet 元数据 -->
    <PackageId>MyCompany.MyLibrary</PackageId>
    <Version>1.2.0</Version>
    <Description>一个用于处理用户认证的类库</Description>
    <Authors>YourName</Authors>
    <Company>MyCompany</Company>

    <!-- 可选 -->
    <PackageTags>auth;identity;oauth</PackageTags>
    <PackageProjectUrl>https://github.com/mycompany/mylibrary</PackageProjectUrl>
    <RepositoryUrl>https://github.com/mycompany/mylibrary</RepositoryUrl>
    <PackageLicenseExpression>MIT</PackageLicenseExpression>
    <PackageReadmeFile>README.md</PackageReadmeFile>
    <PackageIcon>icon.png</PackageIcon>
  </PropertyGroup>

  <!-- 将 README 和图标包含在包中 -->
  <ItemGroup>
    <None Include="README.md" Pack="true" PackagePath="\"/>
    <None Include="icon.png" Pack="true" PackagePath="\"/>
  </ItemGroup>

</Project>
```

> [!tip] PackageId vs 程序集名
> `PackageId` 是 NuGet 包的唯一标识，可以和项目名不同。如果省略，默认使用项目名（不含 `.csproj` 扩展名）。推荐显式设置以避免命名冲突。

### 2.4 常用选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `-c` | 生成配置 | `-c Release` |
| `-o` / `--output` | 输出目录 | `-o ./nupkgs` |
| `--include-symbols` | 同时生成符号包 | 生成 `.snupkg` |
| `--include-source` | 符号包中包含源码 | 配合 `--include-symbols` |
| `--no-build` | 跳过编译（直接打包已有 DLL） | CI 中已编译 |
| `-p:Version=2.0.0` | 覆盖版本号 | CI 动态版本 |
| `--version-suffix` | 预发布后缀 | `--version-suffix rc1` 生成 `1.0.0-rc1` |

### 2.5 符号包 (`.snupkg`)

符号包允许调试时下载源码和 PDB：

```bash
dotnet pack -c Release --include-symbols
```

产出两个文件：

```
MyLibrary.1.2.0.nupkg       # 主包
MyLibrary.1.2.0.snupkg      # 符号包（PDB + 源映射）
```

将符号包推送到 NuGet 符号服务器（如 `https://symbols.nuget.org/download/symbols`），使用者在 Visual Studio 中配置符号源后即可在调试时自动下载源码。

> [!tip] 配置嵌入式调试信息
> 在 `.csproj` 中设置：
>
> ```xml
> <PropertyGroup>
>   <DebugType>portable</DebugType>
>   <EmbedAllSources>true</EmbedAllSources>
> </PropertyGroup>
> ```
>
> 这样 pack 时 PDB 和源码信息都嵌入 `.nupkg`，再配合 `--include-symbols` 生成 `.snupkg` 更完整。

### 2.6 `dotnet nuget push` — 推送到仓库

本地打包完成后，推送到 NuGet 仓库：

```bash
# 推送到 nuget.org（需要 API Key）
dotnet nuget push ./nupkgs/MyLibrary.1.2.0.nupkg --api-key YOUR_API_KEY --source https://api.nuget.org/v3/index.json

# 推送到私有仓库（如 Azure Artifacts、GitHub Packages）
dotnet nuget push ./nupkgs/MyLibrary.1.2.0.nupkg --source https://pkgs.dev.azure.com/org/_packaging/feed/nuget/v3/index.json
```

### 2.7 `dotnet nuget` 其他命令

```bash
# 列出本地缓存中的包
dotnet nuget locals all --list

# 清除 NuGet 缓存（解决缓存损坏、元数据过期等问题）
dotnet nuget locals all --clear

# 仅清除 HTTP 缓存
dotnet nuget locals http-cache --clear

# 删除远程仓库中的包（需要 API Key，nuget.org 有限制）
dotnet nuget delete MyLibrary 1.2.0 --source https://api.nuget.org/v3/index.json --api-key KEY
```

> [!warning] nuget.org 的删除限制
> nuget.org 允许在推送后 **1 小时内** 删除包。超时后只能"unlist"（取消列表），包仍可被引用但不出现在搜索结果中。私有仓库通常无此限制。

---

## 三、完整可运行示例

### 示例 1：发布控制台应用为单文件 SCD

```bash
# 1. 创建项目
mkdir PublishDemo && cd PublishDemo
dotnet new console -n Calculator
cd Calculator

# 2. 替换 Program.cs 为简单计算器
```

`Program.cs`：

```csharp
Console.WriteLine("=== 简单计算器 ===");
Console.Write("输入表达式（如 2+3）: ");
var input = Console.ReadLine();

try
{
    var result = Evaluate(input!);
    Console.WriteLine($"结果: {result}");
}
catch (Exception ex)
{
    Console.WriteLine($"错误: {ex.Message}");
}

static double Evaluate(string expr)
{
    var parts = expr.Split(['+', '-', '*', '/']);
    var a = double.Parse(parts[0].Trim());
    var b = double.Parse(parts[1].Trim());
    var op = expr.First(c => "+-*/".Contains(c));

    return op switch
    {
        '+' => a + b,
        '-' => a - b,
        '*' => a * b,
        '/' => b != 0 ? a / b : throw new DivideByZeroException("除数不能为零"),
        _ => throw new ArgumentException($"未知运算符: {op}")
    };
}
```

```bash
# 3. 发布为 SCD 单文件（Windows x64）
dotnet publish -c Release -r win-x64 --self-contained -p:PublishSingleFile=true -o ./publish

# 4. 查看产出
ls ./publish
# 输出: Calculator.exe  (只有一个文件，约 65 MB)

# 5. 复制到一台没有 .NET 的 Windows 机器上，双击运行
```

### 示例 2：打包类库为 NuGet 包

```bash
# 1. 创建类库
mkdir PackDemo && cd PackDemo
dotnet new classlib -n StringUtils
cd StringUtils

# 2. 删除 Class1.cs，创建 StringHelper.cs
rm Class1.cs
```

`StringHelper.cs`：

```csharp
namespace StringUtils;

public static class StringHelper
{
    /// <summary>
    /// 将字符串截断到指定长度，超出部分用省略号替代
    /// </summary>
    public static string Truncate(this string value, int maxLength, string ellipsis = "...")
    {
        ArgumentNullException.ThrowIfNull(value);
        if (maxLength < 0)
            throw new ArgumentOutOfRangeException(nameof(maxLength), "长度不能为负");

        if (value.Length <= maxLength)
            return value;

        return string.Concat(value.AsSpan(0, maxLength), ellipsis);
    }

    /// <summary>
    /// 将字符串反转（支持 Unicode 代理对）
    /// </summary>
    public static string Reverse(this string value)
    {
        ArgumentNullException.ThrowIfNull(value);

        var chars = value.ToCharArray();
        Array.Reverse(chars);
        return new string(chars);
    }
}
```

`.csproj` 配置：

```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>

    <!-- NuGet 元数据 -->
    <PackageId>StringUtils.Toolkit</PackageId>
    <Version>1.0.0</Version>
    <Description>常用字符串处理扩展方法</Description>
    <Authors>LearningDemo</Authors>
    <PackageTags>string;utility;extension</PackageTags>
    <PackageLicenseExpression>MIT</PackageLicenseExpression>

    <!-- 生成 XML 文档 -->
    <GenerateDocumentationFile>true</GenerateDocumentationFile>
  </PropertyGroup>

</Project>
```

```bash
# 3. 打包
dotnet pack -c Release -o ./nupkgs

# 输出:
#   Successfully created package './nupkgs/StringUtils.Toolkit.1.0.0.nupkg'.
```

```bash
# 4. 验证包内容（使用 dotnet 内置功能或解压查看）
# 查看 nupkg 的元数据
dotnet nuget verify ./nupkgs/StringUtils.Toolkit.1.0.0.nupkg
```

### 示例 3：在另一个项目中使用本地包

模拟团队内部使用：打完包不推送到远程，直接本地引用。

```bash
# 回到 PackDemo 目录
cd ../..

# 创建本地包源目录
mkdir local-packages

# 复制 nupkg 到本地源
cp PackDemo/StringUtils/nupkgs/StringUtils.Toolkit.1.0.0.nupkg local-packages/

# 创建消费项目
dotnet new console -n UseStringUtils
cd UseStringUtils

# 添加本地 NuGet 源（仅当前目录生效）
dotnet nuget add source ../local-packages --name LocalSource --configfile ./nuget.config

# 添加包引用
dotnet add package StringUtils.Toolkit --source LocalSource
```

`Program.cs`：

```csharp
using StringUtils;

var longText = "这是一段很长的文本，我们需要将其截断显示";
Console.WriteLine(longText.Truncate(10));     // 输出: 这是一段很长的文本，...
Console.WriteLine("Hello World".Reverse());   // 输出: dlroW olleH
```

```bash
dotnet run
```

---

## 四、练习

> [!note] 练习说明
> 每个练习预计 15–20 分钟。创建独立目录，完成后对照预期输出。

### 练习 1：发布模式对比（20min）

**目标**：直观感受六种发布模式的体积和结构差异。

**步骤**：

1. 创建一个 .NET 8 控制台项目（任意功能，如输出 "Hello Publish"）
2. 分别用以下 6 种方式发布到不同子目录，记录每种模式的文件数和总大小：

```bash
# 模式 1: FDD（默认）
dotnet publish -c Release -r win-x64 -o ./out/fdd

# 模式 2: SCD
dotnet publish -c Release -r win-x64 --self-contained -o ./out/scd

# 模式 3: SCD + 单文件
dotnet publish -c Release -r win-x64 --self-contained -p:PublishSingleFile=true -o ./out/scd-single

# 模式 4: SCD + 裁剪
dotnet publish -c Release -r win-x64 --self-contained -p:PublishTrimmed=true -o ./out/scd-trimmed

# 模式 5: SCD + R2R
dotnet publish -c Release -r win-x64 --self-contained -p:PublishReadyToRun=true -o ./out/scd-r2r

# 模式 6: AOT
dotnet publish -c Release -r win-x64 -p:PublishAot=true -o ./out/aot
```

3. 对比结果，填写下表：

| 模式 | 文件数 | 总大小 | 最小文件（主 exe/dll） |
|------|--------|--------|----------------------|
| FDD | | | |
| SCD | | | |
| SCD + Single | | | |
| SCD + Trimmed | | | |
| SCD + R2R | | | |
| AOT | | | |

> [!tip]- 预期答案（Hello World 近似值）
>
> | 模式 | 文件数 | 总大小 | 主文件 |
> |------|--------|--------|--------|
> | FDD | ~5 | ~150 KB | ~10 KB (dll) |
> | SCD | ~350 | ~65 MB | ~180 KB (exe) |
> | SCD + Single | 1 | ~65 MB | ~65 MB (exe) |
> | SCD + Trimmed | ~150 | ~25 MB | ~25 MB (如果单文件) |
> | SCD + R2R | ~350 | ~80 MB | ~250 KB (exe) |
> | AOT | 1（无额外依赖） | ~8 MB | ~8 MB (exe) |

### 练习 2：打包并本地消费类库（20min）

**目标**：完成从创建类库 → 打包 → 本地引用 → 消费的完整链路。

**步骤**：

1. 创建类库 `MathLib`，实现一个静态类 `MathHelper`：
   - `static double Average(params double[] values)` — 计算平均值
   - `static double StandardDeviation(params double[] values)` — 计算标准差
2. 在 `.csproj` 中配置完整的 NuGet 元数据（`PackageId`、`Version`、`Description`、`Authors`、`PackageTags`）
3. `dotnet pack -c Release -o ./nupkgs` 生成包
4. 创建控制台项目 `MathClient`，通过本地 NuGet 源引用 `MathLib`
5. 在 `Main` 中调用两个方法并输出结果
6. 运行确认输出正确

> [!tip]- 预期调用结果
> `Average(1,2,3,4,5)` → `3`
> `StandardDeviation(1,2,3,4,5)` → `1.414...`

### 练习 3：跨平台发布脚本（20min）

**目标**：编写一个脚本，一键发布三个平台版本。

**步骤**：

1. 创建一个项目，编写一个简单的功能（如显示当前平台信息）：

```csharp
using System.Runtime.InteropServices;

Console.WriteLine($"OS: {RuntimeInformation.OSDescription}");
Console.WriteLine($"Architecture: {RuntimeInformation.OSArchitecture}");
Console.WriteLine($"Framework: {RuntimeInformation.FrameworkDescription}");
```

2. 编写 PowerShell / Bash 脚本 `publish-all.(ps1|sh)`，依次发布三个平台：

```powershell
# publish-all.ps1
$rids = @("win-x64", "linux-x64", "osx-arm64")

foreach ($rid in $rids) {
    Write-Host "Publishing for $rid..."
    dotnet publish -c Release -r $rid --self-contained `
        -p:PublishSingleFile=true `
        -o "./publish/$rid"
}

Write-Host "Done! Check ./publish/"
```

3. 运行脚本，验证三个目录都有产物

4. （如果条件允许）将 Linux 版本复制到 WSL 中运行，验证输出

---

## 五、扩展阅读

| 资源 | 地址 | 说明 |
|------|------|------|
| .NET 应用发布概览 | [learn.microsoft.com/en-us/dotnet/core/deploying](https://learn.microsoft.com/en-us/dotnet/core/deploying/) | 官方部署文档 |
| Single-file 发布详解 | [learn.microsoft.com/en-us/dotnet/core/deploying/single-file](https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/) | 单文件原理与限制 |
| 程序集裁剪文档 | [learn.microsoft.com/en-us/dotnet/core/deploying/trimming](https://learn.microsoft.com/en-us/dotnet/core/deploying/trimming/) | 裁剪兼容性、警告处理 |
| Native AOT 文档 | [learn.microsoft.com/en-us/dotnet/core/deploying/native-aot](https://learn.microsoft.com/en-us/dotnet/core/deploying/native-aot/) | AOT 限制与最佳实践 |
| ReadyToRun 详解 | [learn.microsoft.com/en-us/dotnet/core/deploying/ready-to-run](https://learn.microsoft.com/en-us/dotnet/core/deploying/ready-to-run/) | R2R 编译原理、RID 选择 |
| RID 目录 | [learn.microsoft.com/en-us/dotnet/core/rid-catalog](https://learn.microsoft.com/en-us/dotnet/core/rid-catalog) | 完整运行时标识符列表 |
| NuGet 包创建 | [learn.microsoft.com/en-us/nuget/create-packages/creating-a-package](https://learn.microsoft.com/en-us/nuget/create-packages/creating-a-package) | MSBuild 打包完整指南 |
| NuGet 符号包 | [learn.microsoft.com/en-us/nuget/create-packages/symbol-packages-snupkg](https://learn.microsoft.com/en-us/nuget/create-packages/symbol-packages-snupkg) | `.snupkg` 配置与推送 |
| 发布到 nuget.org | [learn.microsoft.com/en-us/nuget/nuget-org/publish-a-package](https://learn.microsoft.com/en-us/nuget/nuget-org/publish-a-package) | 实体签名、API Key 流程 |

---

## 六、常见陷阱

### 6.1 错误的 RID（运行时标识符）

```bash
# 错误：在 macOS 上指定 win-x64
❯ dotnet publish -r win-x64 -o ./out
# 可能成功（NuGet 包可能已缓存），但生成的 exe 无法在 macOS 运行

# 正确
❯ dotnet publish -r osx-arm64 -o ./out
```

> [!warning] RID 不匹配的两种表现
> - NuGet 包的 native 依赖（如 `SQLite.Interop.dll`）针对错误平台，运行时 `DllNotFoundException`
> - 生成的宿主可执行文件无法在当前 OS 启动

### 6.2 缺少 PackageId 导致包名冲突

```xml
<!-- 错误：无 PackageId，使用项目名 "Common"——与 NuGet 上已有包冲突 -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Version>1.0.0</Version>
  </PropertyGroup>
</Project>

<!-- 正确 -->
<PropertyGroup>
  <PackageId>MyCompany.Common</PackageId>
  ...
</PropertyGroup>
```

### 6.3 Self-Contained vs FDD 混淆

```
症状：在开发机上 dotnet run 正常，复制到服务器报 "dotnet not found"

原因：服务器未安装 .NET Runtime，而你用的是 FDD 发布

修复：
  dotnet publish -c Release --self-contained -r linux-x64
```

> [!tip] 基本决策原则
> - **服务器/容器**：FDD + 安装 Runtime（体积小，批量部署高效）
> - **客户端/桌面应用**：SCD + Single-File（用户无需安装 .NET）
> - **CLI 工具链/微服务**：AOT（追求启动速度）

### 6.4 裁剪 (Trimming) 破坏反射

```csharp
// 这段代码在裁剪后会崩溃
var type = Type.GetType("MyApp.SomeClass");  // 可能返回 null
var method = type.GetMethod("DoWork");        // NullReferenceException
method.Invoke(null, null);
```

**修复方式 1**：在 `.csproj` 中标记需要保留的类型：

```xml
<ItemGroup>
  <TrimmerRootAssembly Include="MyApp" />
</ItemGroup>
```

**修复方式 2**：使用 `DynamicallyAccessedMembers` 标注：

```csharp
[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicMethods)]
public static void ProcessType(Type type)
{
    foreach (var m in type.GetMethods())  // 裁剪器知道需要保留 PublicMethods
    {
        // ...
    }
}
```

**修复方式 3**：在 `rd.xml`（运行时指令文件）中声明：

```xml
<Directives>
  <Application>
    <Assembly Name="MyApp" Dynamic="Required All" />
  </Application>
</Directives>
```

### 6.5 AOT 中使用了不支持的特性

```
症状：dotnet publish -p:PublishAot=true 编译失败，报错类似：
  "AOT analysis warning IL3050: Using member 'System.Reflection.Assembly.LoadFrom' ..."

原因：AOT 不支持运行时反射发出

修复：
  1. 移除 AOT 不兼容的代码
  2. 使用源生成器（source generator）替代运行时反射
  3. 在 .csproj 中标记 AOT 不兼容的方法为需替换：
     <IlcTrimMetadata>false</IlcTrimMetadata>
```

### 6.6 Single-File 首次启动慢

```
症状：用户双击单文件 exe，第一次启动需要 2-3 秒，后续正常

原因：单文件首次运行时需要解压所有嵌入程序集到临时目录

缓解：
  - 在安装程序中预解压（运行一次 warmup）
  - 使用 ReadyToRun 减少 JIT 开销
  - 接受这个成本（仅首次）
```

### 6.7 NuGet 缓存问题

```
症状：更新了包但 dotnet restore 仍使用旧版本
修复：
  dotnet nuget locals all --clear
  dotnet restore --no-cache
```

### 6.8 发布时没有包含必要的内容文件

```xml
<!-- 错误：发布后找不到配置文件 -->
<!-- config.json 未标记为复制到输出目录 -->

<!-- 修复 1：在 .csproj 中 -->
<ItemGroup>
  <Content Include="config.json">
    <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
    <CopyToPublishDirectory>PreserveNewest</CopyToPublishDirectory>
  </Content>
</ItemGroup>

<!-- 修复 2：或直接在代码中使用嵌入资源 -->
<ItemGroup>
  <EmbeddedResource Include="config.json" />
</ItemGroup>
```

---

> [!summary] 本节小结
> - `dotnet publish` 有六种部署模式，选型取决于目标环境、体积要求和兼容性需求
> - FDD（需要 Runtime）优先用于服务器场景；SCD + Single-File 优先用于客户端分发
> - AOT 提供最快启动和最小体积，但兼容性受限
> - `dotnet pack` 将类库打包为 `.nupkg`，配合 `dotnet nuget push` 完成分发
> - 包元数据（`PackageId`、`Version`、`Description`）必须在 `.csproj` 中显式配置
> - 裁剪和 AOT 都可能破坏反射，需要额外标注保留
>
> 下一步：[[09-multi-targeting]] — 学习如何让一个项目同时编译为多个目标框架版本。
