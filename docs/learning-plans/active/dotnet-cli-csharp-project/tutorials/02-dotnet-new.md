---
title: "dotnet new — 创建项目与解决方案"
updated: 2026-06-10
tags: [dotnet, cli, new, templates, project-creation]
---

# `dotnet new` — 创建项目与解决方案

> 所属计划: [[../plan|dotnet CLI 与 C# 工程构建]]
> 预计耗时: 60min
> 前置知识: [[01-dotnet-env-setup]]

---

## 1. 概念讲解

### 为什么需要 `dotnet new`？

每个 .NET 项目都需要一整套文件才能正常工作：项目文件（`.csproj`）、入口代码、配置文件。如果你每次都手工创建这些文件，不仅繁琐，而且容易遗漏关键配置——比如目标框架声明、隐式 using、可空引用类型等。

`dotnet new` 把这一切自动化了。一条命令就能生成一个完整的、可直接编译运行的项目骨架。它是整个 dotnet CLI 工作流的**起点**——先 `new`，然后 `build`、`run`、`test`、`publish`。

> [!tip] 类比
> `dotnet new` 对 .NET 的作用，就像 `rails new` 对 Rails、`create-react-app` 对 React 一样——它是项目的"一键生成器"。

### 核心概念：模板 (Template)

`dotnet new` 不直接生成文件。它使用**模板 (template)** —— 模板是一个预定义的目录结构 + 文件内容 + 占位符替换规则。你用 `dotnet new <模板名>` 来调用某个模板。

.NET SDK 自带约 20+ 个内置模板，涵盖最常见的项目类型：

| 模板短名 | 项目类型 | 语言 | 产出 |
|---------|---------|------|------|
| `console` | 控制台应用 | C#, F#, VB | 可执行 `.exe` |
| `classlib` | 类库 | C#, F#, VB | `.dll` 类库 |
| `web` | ASP.NET Core 空项目 | C#, F# | Web 应用 |
| `webapi` | ASP.NET Core Web API | C#, F# | REST API |
| `mvc` | ASP.NET Core MVC | C#, F# | MVC Web 应用 |
| `webapp` | ASP.NET Core Razor Pages | C# | Razor Pages 应用 |
| `blazor` | Blazor Server + WebAssembly | C# | 全栈 Web |
| `blazorwasm` | Blazor WebAssembly 独立 | C# | 前端 WebAssembly |
| `blazorserver` | Blazor Server 独立 | C# | 服务端渲染 |
| `worker` | Worker Service（后台服务） | C#, F# | 长时间运行进程 |
| `grpc` | gRPC 服务 | C# | gRPC 微服务 |
| `angular` | Angular + ASP.NET Core | C# | SPA 前端 |
| `react` | React + ASP.NET Core | C# | SPA 前端 |
| `mstest` | MSTest 测试项目 | C#, F#, VB | 单元测试 |
| `xunit` | xUnit 测试项目 | C#, F#, VB | 单元测试 |
| `nunit` | NUnit 测试项目 | C#, F#, VB | 单元测试 |
| `sln` | 解决方案文件 | — | `.sln` 文件 |
| `gitignore` | .gitignore 文件 | — | `dotnet` 版 `.gitignore` |
| `editorconfig` | .editorconfig 文件 | — | 编辑器配置 |
| `globaljson` | global.json 文件 | — | SDK 版本锁定 |
| `nugetconfig` | NuGet 配置文件 | — | 包源配置 |

> [!note] 模板短名 = 模板标识符
> `dotnet new console` 中的 `console` 就是"模板短名 (short name)"。一个模板可能有多语言变体，例如 `console` 默认是 C# 版本，你可以用 `-lang F#` 切换到 F# 版本。

### `dotnet new` 命令基本结构

```bash
dotnet new <模板短名> [-n <项目名>] [-o <输出目录>] [-f <目标框架>] [--参数名 值] [选项]
```

**最常用选项：**

| 选项 | 说明 | 示例 |
|------|------|------|
| `-n`，`--name` | 项目/解决方案名称 | `-n MyApp` |
| `-o`，`--output` | 输出目录（不存在则自动创建） | `-o src/MyApp` |
| `-f`，`--framework` | 目标框架 | `-f net9.0` |
| `--force` | 强制覆盖已有文件 | `--force` |
| `--dry-run` | 仅显示将创建什么，不实际创建 | `--dry-run` |
| `-lang` | 编程语言 | `-lang F#` |
| `--no-restore` | 创建后不自动恢复 NuGet 包 | `--no-restore` |

---

## 2. 代码示例

### 2.1 列出所有可用模板

在动手创建项目之前，先看看你有哪些模板可用：

```bash
dotnet new list
```

**预期输出（部分）：**

```text
These templates matched your input:

Template Name                  Short Name    Language  Tags
-----------------------------  ------------  --------  ----------------
Console App                    console       [C#],F#,VB  Common/Console
Class Library                  classlib      [C#],F#,VB  Common/Library
ASP.NET Core Empty             web           [C#],F#     Web/Empty
ASP.NET Core Web API           webapi        [C#],F#     Web/WebAPI
ASP.NET Core Web App (Razor)   webapp        [C#]        Web/MVC/Razor Pages
Blazor Web App                 blazor        [C#]        Web/Blazor
Worker Service                 worker        [C#],F#     Common/Worker/Web
xUnit Test Project             xunit         [C#],F#,VB  Test/xUnit
MSTest Test Project            mstest        [C#],F#,VB  Test/MSTest
Solution File                  sln                         Solution
...
```

> [!tip] 过滤模板列表
> 用 `dotnet new list --tag web` 只看 Web 相关模板，`dotnet new list --author Microsoft` 只看微软官方模板。

### 2.2 创建控制台应用

这是最常使用的模板——创建一个能从命令行运行的可执行程序：

```bash
# 在当前目录下创建名为 MyApp 的项目
dotnet new console -n MyApp -o src/MyApp
```

**执行后生成的目录结构：**

```text
src/MyApp/
├── MyApp.csproj       ← 项目文件
├── Program.cs         ← 入口点（顶级语句）
├── appsettings.json   ← 配置文件（.NET 9+）
└── obj/               ← 构建中间文件（自动生成）
```

**`MyApp.csproj` 内容：**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net9.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
```

**`Program.cs` 内容（顶级语句风格）：**

```csharp
// See https://aka.ms/new-console-template for more information
Console.WriteLine("Hello, World!");
```

> [!note] 顶级语句 (Top-level Statements)
> .NET 6+ 的 `console` 模板默认使用顶级语句——不需要显式写 `class Program` 和 `static void Main`，代码直接写在文件顶层。这背后编译器会生成完整的 `Main` 方法，功能完全一致。

**试运行：**

```bash
dotnet run --project src/MyApp
```

**预期输出：**

```text
Hello, World!
```

### 2.3 创建类库

类库没有入口点，它的产物是一个 `.dll` 文件，供其他项目引用：

```bash
dotnet new classlib -n MyLib -o src/MyLib
```

**生成的目录结构：**

```text
src/MyLib/
├── MyLib.csproj       ← 项目文件（注意：无 OutputType）
├── Class1.cs          ← 示例类文件
└── obj/
```

**`MyLib.csproj` 内容：**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
```

> [!warning] 注意 `OutputType` 的区别
> `console` 的 `.csproj` 有 `<OutputType>Exe</OutputType>`——产物是 `.exe`。
> `classlib` 没有这行——产物是 `.dll`，不能直接运行。

### 2.4 创建解决方案文件

解决方案（`.sln`）文件是一个"容器"——它引用多个项目，让它们组成一个整体。在 IDE 中双击 `.sln` 就能打开整个多项目工程：

```bash
# 创建解决方案文件
dotnet new sln -n MySolution -o .
```

**生成的文件：**

```text
MySolution.sln        ← 解决方案文件
```

> [!tip] `sln` 模板的特殊性
> `sln` 模板只有一个 `.sln` 文件。创建后需要用 `dotnet sln add` 把项目加入其中（详见 [[05-dotnet-sln|05-dotnet-sln]]）。

**一个完整的"解决方案 + 项目"创建流：**

```bash
# 1. 创建解决方案
dotnet new sln -n MyApp -o .

# 2. 创建控制台项目
dotnet new console -n MyApp.Cli -o src/MyApp.Cli

# 3. 创建类库
dotnet new classlib -n MyApp.Core -o src/MyApp.Core

# 4. 将项目加入解决方案
dotnet sln add src/MyApp.Cli/MyApp.Cli.csproj
dotnet sln add src/MyApp.Core/MyApp.Core.csproj
```

**最终目录结构：**

```text
MyApp.sln             ← 解决方案
src/
├── MyApp.Cli/        ← 入口应用
│   ├── MyApp.Cli.csproj
│   └── Program.cs
└── MyApp.Core/       ← 业务逻辑库
    ├── MyApp.Core.csproj
    └── Class1.cs
```

### 2.5 创建测试项目

三种主流 .NET 测试框架各有自己的模板：

```bash
# xUnit — 最流行，轻量级，广泛使用
dotnet new xunit -n MyLib.Tests -o tests/MyLib.Tests

# NUnit — 老牌框架，约束断言风格
dotnet new nunit -n MyLib.Tests -o tests/MyLib.Tests

# MSTest — 微软官方，与 VS 深度集成
dotnet new mstest -n MyLib.Tests -o tests/MyLib.Tests
```

**xUnit 测试项目生成的目录结构：**

```text
tests/MyLib.Tests/
├── MyLib.Tests.csproj
├── UnitTest1.cs       ← 示例测试类
└── obj/
```

**`UnitTest1.cs` 内容（xUnit 版本）：**

```csharp
namespace MyLib.Tests;

public class UnitTest1
{
    [Fact]
    public void Test1()
    {
        // Arrange, Act, Assert
    }
}
```

**运行测试：**

```bash
dotnet test tests/MyLib.Tests
```

### 2.6 创建 ASP.NET Core Web 项目

```bash
# 空 ASP.NET Core 项目（最小 Web 服务）
dotnet new web -n MyWeb -o src/MyWeb

# Web API（REST API 服务，含 Swagger）
dotnet new webapi -n MyApi -o src/MyApi

# Razor Pages（服务端渲染 Web 应用）
dotnet new webapp -n MyWebApp -o src/MyWebApp

# Blazor Web App（全栈，Server + WebAssembly 混合）
dotnet new blazor -n MyBlazorApp -o src/MyBlazorApp
```

**Web API 项目 (`webapi`) 生成的典型结构：**

```text
src/MyApi/
├── MyApi.csproj
├── Program.cs             ← 启动配置 + 路由注册
├── Controllers/           ← API 控制器目录
├── appsettings.json       ← 配置文件
├── appsettings.Development.json
└── Properties/
    └── launchSettings.json
```

### 2.7 指定目标框架

用 `-f` 选项选择 .NET 版本：

```bash
# 默认 .NET 9（当前 SDK 版本）
dotnet new console -n ModernApp -o ModernApp

# 显式指定 .NET 8（如果安装了 .NET 8 SDK）
dotnet new console -n LegacyApp -o LegacyApp -f net8.0

# 指定长期支持版本
dotnet new console -n LTSApp -o LTSApp -f net8.0
```

> [!tip] 可用框架版本
> 一个 SDK 安装可能支持多个目标框架。用 `dotnet new console --help` 查看 `-f` 可接受的值列表。

### 2.8 辅具模板：`.gitignore`、`.editorconfig`、`global.json`

这些不是"项目模板"，而是生成单个配置文件的**辅具模板 (utility templates)**：

```bash
# 为 .NET 项目定制的 .gitignore
dotnet new gitignore

# .editorconfig — 统一代码风格（缩进、换行、命名规则）
dotnet new editorconfig

# global.json — 锁定项目使用的 SDK 版本
dotnet new globaljson

# NuGet 配置 — 自定义包源
dotnet new nugetconfig
```

**生成的 `.gitignore` 片段（针对 .NET）：**

```gitignore
## .NET
bin/
obj/
*.user
*.suo
*.userosscache
*.sln.docstates
...

## NuGet
**/[Pp]ackages/*
!**/[Pp]ackages/build/
*.nupkg
...
```

> [!tip] 用法建议
> 在仓库根目录执行 `dotnet new gitignore`，然后对所有开发人员有效。

### 2.9 安装/卸载模板包

除了内置模板，社区和团队经常发布自定义模板为 NuGet 包。用 `dotnet new install` 安装：

```bash
# 安装一个自定义模板包（NuGet 包 ID）
dotnet new install MyCompany.Templates

# 从本地目录安装模板
dotnet new install ./local-templates/

# 从 NuGet 包文件安装
dotnet new install ./path/to/package.nupkg
```

**卸载模板包：**

```bash
# 用安装时的标识符卸载
dotnet new uninstall MyCompany.Templates

# 查看已安装的模板包
dotnet new list
# 输出中会包含 "These templates matched your input" 后跟来源
dotnet new uninstall
# 无参数运行会列出已安装的包
```

### 2.10 `--dry-run`：预览而不创建

不确定某个模板会生成什么？用 `--dry-run` 安全预览：

```bash
dotnet new webapi -n TestApi -o TestApi --dry-run
```

**输出：**

```text
File actions would have been taken:
  Create: TestApi/TestApi.csproj
  Create: TestApi/Program.cs
  Create: TestApi/Controllers/WeatherForecastController.cs
  Create: TestApi/Properties/launchSettings.json
  Create: TestApi/appsettings.json
  Create: TestApi/appsettings.Development.json
  Create: TestApi/TestApi.http
```

不会实际创建任何文件，可以放心探索。

### 2.11 `--force`：覆盖已有内容

当输出目录已存在时，`dotnet new` 默认会提示冲突。`--force` 强制覆盖：

```bash
# 即使 src/MyApp 已存在，也覆盖其中的文件
dotnet new console -n MyApp -o src/MyApp --force
```

> [!warning] `--force` 的危险
> `--force` 会覆盖同名文件（如 `Program.cs`、`.csproj`），但**不会**删除目录中已有的其他文件。如果你要完全清空重建，先手动删除目标目录。

### 2.12 模板自定义参数

很多模板支持额外的参数，通过 `--参数名 值` 的方式传递。查看某个模板的所有参数：

```bash
dotnet new console --help
```

常见自定义参数：

```bash
# console: 不使用顶级语句（恢复传统 Main 方法风格）
dotnet new console -n OldStyleApp --use-program-main

# webapi: 不生成示例控制器
dotnet new webapi -n CleanApi --use-controllers false

# webapi: 禁用 OpenAPI/Swagger
dotnet new webapi -n NoSwagger --use-openapi false

# classlib: 不生成 Class1.cs
dotnet new classlib -n MyLib --allow-scripts false
```

> [!note] `--` 参数前缀
> 模板参数始终用 `--` 作为前缀（如 `--use-program-main`），而 dotnet CLI 本身的选项用 `-` 或 `--`（如 `-n`、`--name`）。两者混在一起使用时，`dotnet new` 会自动区分。

### 2.13 综合示例：一次创建完整的多项目结构

```bash
# 创建解决方案
dotnet new sln -n BookStore -o BookStore
cd BookStore

# 创建各层项目
dotnet new webapi    -n BookStore.Api      -o src/BookStore.Api
dotnet new classlib  -n BookStore.Core     -o src/BookStore.Core
dotnet new classlib  -n BookStore.Data     -o src/BookStore.Data
dotnet new xunit     -n BookStore.Core.Tests -o tests/BookStore.Core.Tests

# 添加到解决方案
dotnet sln add src/BookStore.Api/BookStore.Api.csproj
dotnet sln add src/BookStore.Core/BookStore.Core.csproj
dotnet sln add src/BookStore.Data/BookStore.Data.csproj
dotnet sln add tests/BookStore.Core.Tests/BookStore.Core.Tests.csproj

# 生成配置文件
dotnet new gitignore
dotnet new editorconfig
```

**最终目录结构：**

```text
BookStore/
├── .gitignore
├── .editorconfig
├── BookStore.sln
├── src/
│   ├── BookStore.Api/
│   │   ├── BookStore.Api.csproj
│   │   ├── Program.cs
│   │   ├── Controllers/
│   │   └── appsettings.json
│   ├── BookStore.Core/
│   │   ├── BookStore.Core.csproj
│   │   └── Class1.cs
│   └── BookStore.Data/
│       ├── BookStore.Data.csproj
│       └── Class1.cs
└── tests/
    └── BookStore.Core.Tests/
        ├── BookStore.Core.Tests.csproj
        └── UnitTest1.cs
```

---

## 3. 练习

### 练习 1: 模板探索

1. 在终端中运行 `dotnet new list`，观察输出
2. 分别运行 `dotnet new list --tag web`、`dotnet new list --tag test`，对比过滤前后的区别
3. 选一个你没见过的模板（如 `worker` 或 `grpc`），运行 `dotnet new <模板名> --help`，阅读它的可用参数
4. 用 `dotnet new <模板名> -o <dir> --dry-run` 预览它将创建的文件列表

### 练习 2: 创建完整项目结构

用 `dotnet new` 从零创建一个"计算器"解决方案，满足以下要求：

1. 创建解决方案 `Calculator.sln`
2. 创建控制台项目 `Calculator.Cli`（入口应用，放在 `src/Calculator.Cli/`）
3. 创建类库项目 `Calculator.Core`（计算逻辑，放在 `src/Calculator.Core/`）
4. 创建 xUnit 测试项目 `Calculator.Core.Tests`（放在 `tests/Calculator.Core.Tests/`）
5. 将所有项目加入解决方案
6. 生成 `.gitignore` 和 `.editorconfig`
7. 修改 `Calculator.Cli/Program.cs`，让它在控制台输出你可以写一个加法计算器的思路

**验收标准：**
- 目录结构清晰分层（`src/` 放源码，`tests/` 放测试）
- 所有项目都在同一个 `.sln` 中
- `dotnet build` 从解决方案根目录执行成功

### 练习 3: 模板参数实验

1. 用 `dotnet new console --use-program-main` 创建项目，对比与默认模板的 `Program.cs` 有什么不同
2. 用 `-f` 参数指定不同的目标框架创建项目（如果装了多个 SDK 版本）
3. 尝试在一个已有内容的目录中运行 `dotnet new console -o .`，观察会发生什么。然后用 `--force` 重试

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **模板探索**：
>
> ```bash
> # 1. 列出所有可用模板
> dotnet new list
> # 观察输出列：Template Name（模板全名）、Short Name（命令用）、Language、Tags
>
> # 2. 按 tag 过滤
> dotnet new list --tag web
> # 只显示 web, webapi, mvc, webapp, blazor 等 Web 相关模板
> dotnet new list --tag test
> # 只显示 xunit, nunit, mstest 等测试模板
> # 关键发现：list 命令支持按 Tags 列过滤，Tags 是模板分类的核心机制
>
> # 3. 探索 worker 模板
> dotnet new worker --help
> # 观察：worker 模板有 -n/-o/-f 通用参数，没有 --use-program-main
> #       因为 worker 是 BackgroundService 模式，不是控制台
>
> # 4. 预览 grpc 模板（不实际创建文件）
> dotnet new grpc -n GrpcDemo -o GrpcDemo --dry-run
> # 输出示例：
> #   Create: GrpcDemo/GrpcDemo.csproj
> #   Create: GrpcDemo/Program.cs
> #   Create: GrpcDemo/Services/GreeterService.cs
> #   Create: GrpcDemo/Protos/greet.proto
> #   Create: GrpcDemo/Properties/launchSettings.json
> # 关键洞察：--dry-run 在不确定模板行为时是安全预览工具
> ```
>
> **思考题答案**：`--dry-run` 的核心价值在于降低探索成本——你不需要担心创建了不需要的文件再去清理。对于 `worker`、`grpc` 这类你从未用过的模板，先用 `--dry-run` 看看会生成哪些文件，再决定是否真正创建。

> [!tip]- 练习 2 参考答案
> **创建 Calculator 完整项目结构**：
>
> ```bash
> # 1. 创建根目录和解决方案
> mkdir Calculator && cd Calculator
> dotnet new sln -n Calculator
>
> # 2. 创建项目（src/ 和 tests/ 分层）
> dotnet new console -n Calculator.Cli -o src/Calculator.Cli
> dotnet new classlib -n Calculator.Core -o src/Calculator.Core
> dotnet new xunit -n Calculator.Core.Tests -o tests/Calculator.Core.Tests
>
> # 3. 将所有项目加入解决方案
> dotnet sln Calculator.sln add src/Calculator.Cli/Calculator.Cli.csproj
> dotnet sln Calculator.sln add src/Calculator.Core/Calculator.Core.csproj
> dotnet sln Calculator.sln add tests/Calculator.Core.Tests/Calculator.Core.Tests.csproj
>
> # 4. 生成配置文件
> dotnet new gitignore
> dotnet new editorconfig
> ```
>
> **修改 `src/Calculator.Cli/Program.cs`**：
>
> ```csharp
> // Calculator.Cli — 加法计算器思路
>
> Console.WriteLine("=== Calculator 设计思路 ===");
> Console.WriteLine();
> Console.WriteLine("1. Calculator.Core 类库中定义 Calculator 类：");
> Console.WriteLine("   - decimal Add(decimal a, decimal b)  — 加法");
> Console.WriteLine("   - decimal Subtract(decimal a, decimal b) — 减法");
> Console.WriteLine("   - decimal Multiply(decimal a, decimal b) — 乘法");
> Console.WriteLine("   - decimal Divide(decimal a, decimal b) — 除法（除零检查）");
> Console.WriteLine();
> Console.WriteLine("2. Calculator.Cli 控制台读取用户输入：");
> Console.WriteLine("   - 读取第一个数字");
> Console.WriteLine("   - 读取运算符（+, -, *, /）");
> Console.WriteLine("   - 读取第二个数字");
> Console.WriteLine("   - 调用 Calculator.Core 的对应方法");
> Console.WriteLine("   - 输出结果");
> Console.WriteLine();
> Console.WriteLine("3. Calculator.Core.Tests 测试：");
> Console.WriteLine("   - 测试加法：2 + 3 = 5");
> Console.WriteLine("   - 测试除零：应抛出异常或返回错误");
> Console.WriteLine("   - 测试小数精度：0.1 + 0.2 的 decimal 处理");
> Console.WriteLine();
> Console.WriteLine("4. 项目引用链：");
> Console.WriteLine("   Calculator.Cli → Calculator.Core");
> Console.WriteLine("   Calculator.Core.Tests → Calculator.Core");
> ```
>
> **验收验证**：
>
> ```bash
> # 在解决方案根目录执行
> dotnet build
> # 预期：3 个项目全部编译成功，0 Error
>
> # 验证项目结构
> dotnet sln list
> # 预期输出：
> #   src/Calculator.Cli/Calculator.Cli.csproj
> #   src/Calculator.Core/Calculator.Core.csproj
> #   tests/Calculator.Core.Tests/Calculator.Core.Tests.csproj
> ```
>
> **最终目录结构**：
>
> ```text
> Calculator/
> ├── .gitignore
> ├── .editorconfig
> ├── Calculator.sln
> ├── src/
> │   ├── Calculator.Cli/
> │   │   ├── Calculator.Cli.csproj
> │   │   └── Program.cs
> │   └── Calculator.Core/
> │       ├── Calculator.Core.csproj
> │       └── Class1.cs
> └── tests/
>     └── Calculator.Core.Tests/
>         ├── Calculator.Core.Tests.csproj
>         └── UnitTest1.cs
> ```
>
> **关键设计点**：`src/` 和 `tests/` 的分层是工业标准结构，.NET 官方模板库（如 `dotnet new sln` 的 --use-program-main 示例）都遵循此布局。

> [!tip]- 练习 3 参考答案
> **模板参数实验**：
>
> ```bash
> # 1. 对比顶级语句 vs 传统 Main
> dotnet new console -n TopLevel -o TopLevel
> cat TopLevel/Program.cs
> # 输出（顶级语句）：
> #   Console.WriteLine("Hello, World!");
>
> dotnet new console -n Traditional --use-program-main -o Traditional
> cat Traditional/Program.cs
> # 输出（传统风格）：
> #   namespace Traditional;
> #   class Program
> #   {
> #       static void Main(string[] args)
> #       {
> #           Console.WriteLine("Hello, World!");
> #       }
> #   }
> ```
>
> **关键发现**：
> - 顶级语句：代码直接在文件顶层，没有 `class Program` 和 `Main` 包裹
> - 传统 `Main`：显式声明命名空间、类和 `static void Main(string[] args)`
> - 两种风格编译后的 IL 完全一致——这是纯语法糖
> - `--use-program-main` 参数仅 `console` 模板有此特性
>
> ```bash
> # 2. 指定目标框架（需要安装多个 SDK 版本才能验证）
> dotnet new console -n Net8App -f net8.0 -o Net8App
> dotnet new console -n Net9App -f net9.0 -o Net9App
> # 对比 .csproj 中的 <TargetFramework> 值差异
> ```
>
> ```bash
> # 3. 已有目录中的创建冲突与 --force
> mkdir ExistingDir
> echo "existing file" > ExistingDir/notes.txt
> # 首次创建 — 会因 Program.cs 冲突而报错或提示
> dotnet new console -o ExistingDir
> # 观察：dotnet new 检测到已有的 Program.cs 和 .csproj，报错
>
> # 用 --force 强制覆盖
> dotnet new console -o ExistingDir --force
> # 观察：Program.cs 和 .csproj 被覆盖，但 notes.txt 保留
> # 关键教训：--force 只覆盖模板生成的同名文件，不会清空目录
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- [dotnet new command — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-new)
- [.NET 项目模板概述](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-new-sdk-templates)
- [自定义模板教程 — 创建自己的 `dotnet new` 模板](https://learn.microsoft.com/en-us/dotnet/core/tools/custom-templates)
- [dotnet new list 命令参考](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-new-list)
- [gitignore 模板库 — GitHub gitignore](https://github.com/github/gitignore/blob/main/VisualStudio.gitignore)（dotnet 生成的 `.gitignore` 基于此）
- [editorconfig 官方文档](https://editorconfig.org/)
- [.NET 顶级语句（Top-level statements）详解](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/program-structure/top-level-statements)

---

## 常见陷阱

- **模板名写错** — `dotnet new console` 正确，`dotnet new console-app` 或 `dotnet new consoleapp` 错误。如果不确定名称，先用 `dotnet new list` 查看准确的"Short Name"列

- **输出目录冲突** — 如果目标目录已存在且包含同名文件（如已有 `Program.cs`），`dotnet new` 会报错。解决：① 用 `--force` 强制覆盖；② 指定一个不存在的目录；③ 先手动删除目标目录

- **创建了项目但没加入解决方案** — `dotnet new <type>` 只创建项目文件，不会自动注册到 `.sln`。你需要额外执行 `dotnet sln add <project>`。忘记这步的话，在 VS/Rider 里打开 `.sln` 看不到那个项目

- **`-n` 和 `-o` 混用导致的困惑** — `-n MyApp` 只是设置项目名，文件放在**当前目录**；`-o src/MyApp` 创建子目录并把文件放进去。推荐同时使用：`-n MyApp -o src/MyApp`。如果你只用了 `-n`，C# 命名空间会是对的，但目录结构会乱

- **`.sln` 文件路径** — `dotnet new sln -n Foo` 会在**当前目录**创建 `Foo.sln`。建议在一个空目录中执行，或者指定 `-o` 参数

- **`--force` 不会清空旧目录** — 它只覆盖模板生成的同名文件。如果你把 `console` 改成 `webapi` 用 `--force`，旧的 `Program.cs` 会被覆盖，但原来在目录里的其他文件（如你自己写的类文件）仍保留。这可能导致混乱——该用新目录时用新目录

- **顶级语句 vs 传统 `Main`** — 默认 `console` 模板使用顶级语句。如果你习惯了传统的 `static void Main` 写法，可以用 `dotnet new console --use-program-main` 来生成传统风格。效果完全一样，只是风格偏好问题

- **NuGet 恢复超时或失败** — `dotnet new` 完成后自动运行 `dotnet restore`。如果网络不好或代理配置有问题，这一步可能失败。项目文件本身已经创建成功，可以稍后手动 `dotnet restore`
