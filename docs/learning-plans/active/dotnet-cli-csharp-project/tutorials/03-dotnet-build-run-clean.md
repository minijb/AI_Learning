---
title: "dotnet build / run / clean — 编译运行与清理"
updated: 2026-06-10
tags: [dotnet, cli, build, run, clean, restore]
---

# `dotnet build` / `run` / `clean` — 编译运行与清理

> 预计耗时: 60min
> 前置: [[02-dotnet-new]]
> 本教程逐步演示如何编译、运行、清理 .NET 项目，涵盖 `dotnet build`、`dotnet run`、`dotnet clean`、`dotnet restore` 四个核心命令。

---

## 概念讲解

创建了项目之后，下一步是让代码"动起来"。`dotnet new` 生成的 `.csproj` 和 `.cs` 文件只是文本——它们需要被编译器转换为可执行的程序。四个命令构成最日常的构建循环:

| 命令 | 作用 | 类比 |
|------|------|------|
| `dotnet restore` | 下载项目依赖的 NuGet 包 | 去仓库取原材料 |
| `dotnet build` | 编译源代码生成程序集 | 把原材料加工成产品 |
| `dotnet run` | 编译 + 立即执行 | 直接一键启动 |
| `dotnet clean` | 删除所有构建产物 | 清理工作台 |

这四个命令构成了最日常的开发循环: **改代码 → 运行 → 改代码 → 运行**。

---

## `dotnet restore` — 恢复依赖

### 为什么需要 restore

.NET 项目通过 NuGet 包引用第三方库。这些包并不随源代码存储——`.csproj` 中只记录"需要哪些包"，实际 `.dll` 文件需要从 NuGet 服务器下载。`dotnet restore` 做的事就是:

```text
读取 .csproj → 解析依赖树 → 下载缺失的包 → 放到全局缓存
```

> [!info] 全局包缓存位置
> Windows: `%USERPROFILE%\.nuget\packages`
> Linux/macOS: `~/.nuget/packages`
>
> 下载过一次的包会缓存在这里，同一台机器上的所有项目共享。

### 自动 vs 手动 restore

```bash
# 显式 restore — 你手动触发
dotnet restore

# 隐式 restore — 这些命令默认会先 restore
dotnet build    # 隐含 restore
dotnet run      # 隐含 build → 隐含 restore
dotnet test     # 隐含 build → 隐含 restore
dotnet publish  # 隐含 restore
```

> [!tip] 什么时候显式 restore
> - 刚 `git clone` 一个项目，想先下载依赖再看代码
> - 只想验证 `NuGet.config` 源配置是否正确，不需要编译
> - CI/CD 流程中将 restore 与 build 分离以利用缓存

使用 `--no-restore` 可以跳过自动 restore:

```bash
dotnet build --no-restore
```

### 自定义 NuGet 源

企业环境下可能使用私有 NuGet 仓库。配置方式:

```bash
# 临时指定源
dotnet restore --source https://nuget.mycompany.com/v3/index.json

# 或通过 NuGet.config 文件持久化配置（推荐）
```

具体配置见 [[04-dotnet-add-remove]]。

---

## `dotnet build` — 编译项目

### 基本用法

```bash
# 在当前目录编译（查找所在目录的 .csproj 或 .sln）
dotnet build

# 编译指定项目
dotnet build src/MyApp/MyApp.csproj

# 编译整个解决方案
dotnet build MySolution.sln
```

> [!note] 项目 vs 解决方案
> `dotnet build` 在目录下查找逻辑是:
> 1. 如果目录下有 `.sln` 文件 → 编译整个解决方案
> 2. 如果没有 `.sln` 但有 `.csproj` → 编译这一个项目
> 3. 如果有多个 `.csproj` 但没有 `.sln` → 报错，需要显式指定

### 核心选项

| 选项 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--configuration` | `-c` | Debug 或 Release | `-c Release` |
| `--framework` | `-f` | 目标框架 | `-f net8.0` |
| `--output` | `-o` | 输出目录 | `-o ./out` |
| `--no-restore` | — | 跳过隐式 restore | `--no-restore` |
| `--verbosity` | `-v` | 日志详细度 | `-v detailed` |
| `--runtime` | `-r` | 目标运行时 | `-r win-x64` |

**Configuration (`-c`)**:

```bash
# Debug 模式（默认）: 包含调试符号，不做优化
dotnet build -c Debug

# Release 模式: 启用优化，去掉调试信息
dotnet build -c Release
```

> [!warning] Debug vs Release 差异显著
> Debug 和 Release 不仅仅是"有没有调试信息"的区别。Release 模式会:
> - 启用 JIT 优化（内联、循环展开）
> - 移除 `#if DEBUG` 代码块
> - 某些情况下行为可能不同（浮点精度、对象生命周期）
>
> 本地开发用 Debug，CI/CD 和最终发布用 Release。

**Verbosity (`-v`)**:

```bash
# 五个级别: q[uiet], m[inimal], n[ormal], d[etailed], diag[nostic]
dotnet build -v detailed   # 显示每个编译的文件
dotnet build -v diag       # 极详细的诊断输出（排查构建问题用）
```

### 增量编译

`dotnet build` 不是每次都全量重新编译。它比较源文件和输出文件的时间戳:

```text
source.cs 修改时间 > bin/Debug/net8.0/MyApp.dll 修改时间?
├─ 是 → 重新编译这个文件
└─ 否 → 跳过（"up-to-date"）
```

输出中看到 `MyApp -> ...\MyApp.dll` 说明实际发生了编译。如果没有输出路径，说明被跳过了。

> [!tip] 增量编译的局限
> 修改 `.csproj` 中的配置（如 `<DefineConstants>`）可能不会触发重新编译。如果遇到"改了代码但行为没变"的情况，先执行 `dotnet clean` 再 `dotnet build`。

### 编译输出解读

一次成功的构建输出:

```text
$ dotnet build
MSBuild version 17.9.8+b34f75857 for .NET
  Determining projects to restore...
  All projects are up-to-date for restore.
  MyApp -> C:\Projects\MyApp\bin\Debug\net8.0\MyApp.dll
  MyApp -> C:\Projects\MyApp\bin\Debug\net8.0\MyApp.exe

Build succeeded.
    0 Warning(s)
    0 Error(s)

Time Elapsed 00:00:01.23
```

关键行解读:

| 输出 | 含义 |
|------|------|
| `Determining projects to restore...` | 检查 NuGet 依赖 |
| `All projects are up-to-date for restore` | 所有包已就绪，无需下载 |
| `MyApp -> ...MyApp.dll` | 实际编译并产出了程序集 |
| `Build succeeded.` | 编译成功 |

如果出现 **Warning(s)** 或 **Error(s)**，会列出具体问题和文件位置。

---

## 构建输出目录结构

编译完成后，项目目录下会多出两个文件夹:

```text
MyApp/
├── MyApp.csproj
├── Program.cs
├── bin/                          ← 最终可执行输出
│   └── Debug/
│       └── net8.0/
│           ├── MyApp.dll         ← 编译后的程序集
│           ├── MyApp.exe         ← 可执行入口（Windows）
│           ├── MyApp.pdb         ← 调试符号文件
│           ├── MyApp.deps.json   ← 依赖清单
│           └── MyApp.runtimeconfig.json  ← 运行时配置
└── obj/                          ← 中间产物（临时文件）
    ├── project.assets.json       ← 依赖解析结果
    ├── project.nuget.cache       ← NuGet 缓存标记
    ├── MyApp.csproj.nuget.dgspec.json
    ├── MyApp.csproj.nuget.g.props
    ├── MyApp.csproj.nuget.g.targets
    └── Debug/
        └── net8.0/
            ├── apphost.exe       ← .NET 宿主程序
            ├── MyApp.dll         ← 编译中间产物
            ├── MyApp.pdb
            └── refint/           ← 引用程序集（内部使用）
```

### `bin/` vs `obj/`

| 目录 | 用途 | 可以删除? |
|------|------|-----------|
| `bin/` | 最终输出: 可运行的程序、依赖的 DLL | 是，`dotnet clean` 删除 |
| `obj/` | 中间产物: 编译器暂存文件、增量编译缓存 | 是，`dotnet clean` 删除 |

> [!warning] 不要手动改 `bin/` 和 `obj/`
> 这两个目录由 SDK 自动管理。日常开发中通常添加到 `.gitignore`:
>
> ```gitignore
> bin/
> obj/
> ```

### 输出路径命名规则

默认路径: `bin/<Configuration>/<TargetFramework>/`

- `bin/Debug/net8.0/` — Debug 配置 + net8.0 目标框架
- `bin/Release/net8.0/` — Release 配置 + net8.0 目标框架

使用 `-o` 可以指定输出目录:

```bash
dotnet build -o ./out
# 输出到 ./out/MyApp.dll，不再区分 Debug/Release
```

---

## `dotnet run` — 编译并运行

### 基本用法

```bash
# 在当前目录编译并运行
dotnet run

# 指定项目
dotnet run --project src/MyApp/MyApp.csproj

# 不重新编译，直接运行已有的输出
dotnet run --no-build
```

`dotnet run` = `dotnet build` + 执行生成的程序。它是开发阶段最高频的命令。

### 向应用程序传递参数

`--` 是一个分隔符。`--` 之前是 `dotnet run` 自己的参数，`--` 之后是传给应用程序的参数:

```bash
# --project 是 dotnet run 的参数
# --name Alice --count 5 是应用程序的参数
dotnet run --project MyApp -- --name Alice --count 5
```

> [!important] `--` 分隔符
> 如果没有 `--`，`--name Alice` 会被 `dotnet run` 解析为自己的选项（通常不识别而报错）。**永远用 `--` 分隔 dotnet 参数和应用程序参数。**

```bash
# ❌ 错误: --name 被 dotnet run 解析
dotnet run --name Alice

# ✅ 正确: --name 传递给应用程序
dotnet run -- --name Alice
```

### 运行解决方案中的特定项目

```bash
# 在解决方案目录中，指定要运行的项目
dotnet run --project src/WebApi/WebApi.csproj

# 或者直接 cd 到项目目录
cd src/WebApi
dotnet run
```

### `--no-build` 的使用场景

你已经知道输出目录下有编译好的文件，不想浪费时间重新编译:

```bash
dotnet run --no-build
```

> [!warning] `--no-build` 的前提
> 输出目录中必须有之前编译好的 DLL。如果刚 `dotnet clean` 过或者改了代码还没编译，`--no-build` 会失败。

---

## `dotnet clean` — 清理构建产物

### 基本用法

```bash
# 清理当前目录的项目或解决方案
dotnet clean

# 清理指定项目
dotnet clean src/MyApp/MyApp.csproj
```

`dotnet clean` 会删除 `bin/` 和 `obj/` 目录下的所有产物。效果等同于手动 `rm -rf bin obj`。

### 什么时候需要 clean

| 场景 | 为什么 |
|------|--------|
| 切换 Configuration (Debug ↔ Release) | 避免混合不同配置的产物 |
| 切换 Target Framework | 避免旧框架的 DLL 残留 |
| 拉取新代码后构建失败 | 清除上一次构建的"脏"状态 |
| 增量编译"失灵" — 改了代码没生效 | `obj/` 缓存可能导致误判"无需编译" |
| CI/CD 环境 | 确保每次构建从零开始 |

> [!tip] clean 的成本
> `dotnet clean` 只是删除文件。下次 `dotnet build` 需要全量编译，比增量编译慢。日常工作流中**不需要频繁 clean**——只有在出现异常时才用。

---

## 完整演练: 创建 → 构建 → 运行 → 修改 → 重建 → 清理

下面我们从头到尾走一遍完整的开发循环。请打开终端，跟着操作。

### Step 1: 创建项目

```bash
# 创建并进入项目目录
mkdir BuildDemo
cd BuildDemo
dotnet new console -n MyApp
```

> [!note]- 当前目录结构
> ```text
> BuildDemo/
> └── MyApp/
>     ├── MyApp.csproj
>     └── Program.cs
> ```

### Step 2: 查看 Program.cs

```bash
# Windows
type MyApp\Program.cs

# Linux/macOS
cat MyApp/Program.cs
```

输出内容:

```csharp
// See https://aka.ms/new-console-template for more information
Console.WriteLine("Hello, World!");
```

### Step 3: 首次 restore

```bash
cd MyApp
dotnet restore
```

预期输出:

```text
  Determining projects to restore...
  Restored C:\Projects\BuildDemo\MyApp\MyApp.csproj (in 123 ms).
```

首次 restore 会从 NuGet.org 下载隐式依赖（如 `Microsoft.NET.Sdk` 的基础包）。

### Step 4: 首次 build

```bash
dotnet build
```

预期输出:

```text
MSBuild version 17.9.8+b34f75857 for .NET
  Determining projects to restore...
  All projects are up-to-date for restore.
  MyApp -> C:\Projects\BuildDemo\MyApp\bin\Debug\net8.0\MyApp.dll

Build succeeded.
    0 Warning(s)
    0 Error(s)

Time Elapsed 00:00:02.50
```

### Step 5: 检查输出

```bash
# 查看 bin 目录
# Windows: dir bin\Debug\net8.0
# Linux/macOS: ls bin/Debug/net8.0/
ls bin/Debug/net8.0/
```

预期文件:

```text
MyApp.dll
MyApp.exe          (Windows)
MyApp.pdb
MyApp.deps.json
MyApp.runtimeconfig.json
```

### Step 6: 运行

```bash
dotnet run
```

预期输出:

```text
Hello, World!
```

### Step 7: 再次 build (增量 — 应跳过)

```bash
dotnet build
```

预期输出:**未显示 `MyApp -> ...dll` 这一行**。说明源码未改变，增量编译跳过。

```text
MSBuild version 17.9.8+b34f75857 for .NET
  Determining projects to restore...
  All projects are up-to-date for restore.
  MyApp: ( Assets file) -> C:\Projects\BuildDemo\MyApp\bin\Debug\net8.0\MyApp.dll

Build succeeded.
    0 Warning(s)
    0 Error(s)

Time Elapsed 00:00:00.30    ← 注意时间远短于首次编译
```

### Step 8: 修改代码

把 `Program.cs` 中的内容改为:

```csharp
Console.WriteLine("Hello, .NET Build System!");
Console.WriteLine($"Current time: {DateTime.Now}");
```

保存文件。

### Step 9: 增量化重新 build

```bash
dotnet build
```

这次会看到实际编译:

```text
...
  MyApp -> C:\Projects\BuildDemo\MyApp\bin\Debug\net8.0\MyApp.dll
...
```

### Step 10: 运行新版本

```bash
dotnet run
```

预期输出:

```text
Hello, .NET Build System!
Current time: 2026-06-10 14:30:25
```

### Step 11: 传递命令行参数

修改 `Program.cs`:

```csharp
if (args.Length > 0)
{
    Console.WriteLine($"Received {args.Length} argument(s):");
    foreach (var arg in args)
    {
        Console.WriteLine($"  - {arg}");
    }
}
else
{
    Console.WriteLine("No arguments provided.");
}
```

运行并传递参数:

```bash
dotnet run -- --name Alice --count 5 --verbose
```

预期输出:

```text
Received 5 argument(s):
  - --name
  - Alice
  - --count
  - 5
  - --verbose
```

### Step 12: Release 构建

```bash
dotnet build -c Release
```

现在检查输出:

```bash
ls bin/Release/net8.0/
```

Release 编译产物比 Debug 版本更小（编译优化后的结果）。

### Step 13: 清理

```bash
dotnet clean
```

预期输出:

```text
Build succeeded.
    0 Warning(s)
    0 Error(s)
```

验证清理结果:

```bash
# bin/ 和 obj/ 应该被清空或不存在
ls bin/
ls obj/
```

### Step 14: 返回并清理实验目录

```bash
cd ../..
# rm -rf BuildDemo   (或手动删除)
```

---

## 练习

### 练习 1: 多项目解决方案的构建

1. 使用 `dotnet new` 创建一个解决方案 `BuildLab`，包含:
   - 一个控制台项目 `App`
   - 一个类库项目 `Lib`
2. 在 `Lib` 中创建一个 `public class Greeter`，包含一个方法 `string Greet(string name)`
3. 在 `App` 中引用 `Lib`，调用 `Greeter.Greet("World")`
4. 用 `dotnet build` 编译整个解决方案
5. 用 `dotnet run` 运行 `App` 项目

> 提示: 需要使用 `dotnet sln add` 将项目加入解决方案，以及 `dotnet add reference` 添加项目引用。具体语法见 [[02-dotnet-new]]。

预期输出: `Hello, World!`

### 练习 2: 探索 verbosity 级别

1. 创建一个控制台项目 `VerboseDemo`
2. 分别以 `-v minimal`、`-v normal`、`-v detailed` 运行 `dotnet build`
3. 比较三个级别的输出差异
4. 用 `-v diag` 运行一次，观察输出量（可以重定向到文件: `dotnet build -v diag > build.log`）
5. 在 `build.log` 中搜索 `csc`（C# 编译器命令行），观察编译器收到的完整参数

### 练习 3: 增量编译实验

1. 创建一个控制台项目 `IncrementalDemo`
2. 运行两次 `dotnet build`，记录两次的耗时
3. 修改 `Program.cs` 中的一个字符，再次 build，记录耗时
4. 修改 `.csproj` 中的 `<TargetFramework>`（如从 `net8.0` 改为 `net9.0`——如果只安装了 net8.0 则不要真改），观察 `obj/` 目录的变化
5. 运行 `dotnet clean`，观察 `bin/` 和 `obj/` 目录的变化
6. 再次 build，记录耗时（应与首次完整编译相当）

提交你的观察结果: 哪次 build 最快? 哪次最慢? 为什么?

---

## 扩展阅读

- [dotnet build — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-build)
- [dotnet run — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-run)
- [dotnet clean — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-clean)
- [dotnet restore — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-restore)
- [MSBuild 增量构建原理](https://learn.microsoft.com/en-us/visualstudio/msbuild/incremental-builds)
- [Understanding .NET Build Output](https://learn.microsoft.com/en-us/dotnet/core/deploying/runtime-store)
- [NuGet Package Restore](https://learn.microsoft.com/en-us/nuget/consume-packages/package-restore)

---

## 常见陷阱

### 陷阱 1: 忘记 restore 导致编译失败

```bash
$ dotnet build --no-restore
error NU1100: Unable to resolve 'Newtonsoft.Json (>= 13.0.0)' for 'net8.0'.
```

**原因**: 在 `git clone` 新项目后直接 `dotnet build --no-restore`。NuGet 包尚未下载。

**解决**: 先执行 `dotnet restore`，或者去掉 `--no-restore`。

### 陷阱 2: 忘记 `--` 导致参数被吞

```bash
$ dotnet run --name Alice
Unrecognized option '--name'
```

**原因**: `--name` 被 `dotnet run` 当作自己的参数解析。

**解决**: 使用 `dotnet run -- --name Alice`。

### 陷阱 3: 修改了代码但 run 还是旧行为

```bash
$ dotnet run --no-build
```

**原因**: `--no-build` 跳过了编译，运行的还是上一次的 DLL。

**解决**: 去掉 `--no-build`，让 `dotnet run` 自动编译。

### 陷阱 4: 切换 Configuration 后构建失败

```bash
$ dotnet build -c Debug
# ... 成功
$ dotnet build -c Release --no-restore
error CS0246: The type or namespace name 'Xxx' could not be found
```

**原因**: `obj/` 中残留了 Debug 配置的中间文件，导致 Release 构建时误判依赖。

**解决**: 先 `dotnet clean`，再 `dotnet build -c Release`。

### 陷阱 5: staled `obj/` 导致增量编译"失灵"

```bash
# 改了代码，但 dotnet build 说 "up-to-date"
$ dotnet build
Build succeeded.    0 Warning(s)    0 Error(s)
# 可运行后发现行为没变
```

**原因**: 复制项目目录、修改 `.csproj` 某些属性、或手动动了 `obj/` 中的时间戳后，MSBuild 的增量检测可能出现 false-positive 的"无需编译"判断。

**解决**: `dotnet clean && dotnet build`。

### 陷阱 6: 运行时 dll vs 可执行文件混淆

```text
$ dotnet MyApp.dll   ← 这样也可以运行!
```

`dotnet MyApp.dll` 直接用 .NET 运行时加载已编译好的 DLL 执行。这和 `dotnet run --no-build` 效果相同，但不需要 `.csproj` 存在。适合在 CI/CD 中"只拷贝 bin 目录"的场景。

不过要注意: 某些平台只有 `.dll` 而没有独立的可执行入口（`.exe` 是 Windows 特有的）。跨平台运行的正确方式是 `dotnet <app>.dll`。

---

## 命令速查

```bash
# 恢复依赖
dotnet restore

# 编译 (Debug)
dotnet build

# 编译 (Release)
dotnet build -c Release

# 编译并指定输出目录
dotnet build -o ./out

# 详细日志
dotnet build -v detailed

# 跳过 restore
dotnet build --no-restore

# 编译并运行
dotnet run

# 运行指定项目
dotnet run --project src/App/App.csproj

# 传递参数给应用
dotnet run -- --name Alice --count 5

# 跳过编译直接运行
dotnet run --no-build

# 清理
dotnet clean

# 清理并重新编译
dotnet clean && dotnet build
```

---

> 下一步: [[04-dotnet-add-remove]] — 学习如何管理 NuGet 包引用和项目引用。
