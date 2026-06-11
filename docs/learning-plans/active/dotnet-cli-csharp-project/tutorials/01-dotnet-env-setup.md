---
title: "dotnet 环境安装与验证"
updated: 2026-06-10
tags: [dotnet, cli, setup, sdk]
---

# dotnet 环境安装与验证

> 所属计划: [[dotnet-cli-csharp-project|dotnet CLI 与 C# 工程构建]]
> 预计耗时: 40 分钟
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要这个？

在写第一行 C# 代码之前，你必须先把 .NET 工具链装好。这听起来是"点几下安装包"的事——但实际工作中你经常会遇到这些问题：

- 机器上有多个 .NET 版本，项目该用哪个？
- CI/CD 构建机需要装 SDK 还是只装 Runtime？
- `dotnet` 命令不识别？十有八九是 PATH 没配好。
- 项目下载后编译报错"SDK version not found"——因为 `global.json` 锁定了特定版本。

这节把这几个问题一次性讲清楚。

### 核心思想

.NET 生态中 **SDK** 和 **Runtime** 是两个不同的东西：

| 概念 | 作用 | 类比 |
|------|------|------|
| **SDK** (Software Development Kit) | 包含编译器、`dotnet` CLI、MSBuild、NuGet、模板引擎、所有运行时的集合 | 一个完整的"工具箱"——你可以用它开发和运行 .NET 应用 |
| **Runtime** | 只包含运行 .NET 应用所需的最小运行时库（CoreCLR + 基础类库） | 只够"播放音乐"，不能"写歌" |
| **ASP.NET Core Runtime** | 在 Runtime 基础上增加 ASP.NET Core 组件 | 可以跑 Web 应用，但不能编译新项目 |

> [!tip] 记忆口诀
> **SDK 包含 Runtime，Runtime 不包含 SDK。** 开发机装 SDK，服务器/容器装 Runtime（更小、更安全，减少攻击面）。

### .NET 版本号说明

.NET 版本采用 `主版本.次版本.补丁` 格式，例如 `8.0.4`：

- **8** = 主版本，代表一代（.NET 8, .NET 9, .NET 10…）——每年 11 月发布新主版本
- **0** = 次版本，同一个主版本内的功能更新（目前 .NET 主版本次版本号始终为 0）
- **4** = 补丁版本，安全修复和 bug 修复，每月第二个周二发布

此外还有 **STS**（标准期限支持，偶数年 11 月发布）和 **LTS**（长期支持，奇数年 11 月发布）两种发布节奏。.NET 8 和 .NET 10 是 LTS，.NET 9 是 STS。

---

## 2. 安装指南

### 2.1 Windows

**方式一：官方安装包（推荐）**

1. 打开 [https://dotnet.microsoft.com/en-us/download](https://dotnet.microsoft.com/en-us/download)
2. 点击 **".NET SDK x64"** 下载 `.exe` 安装包
3. 双击运行，一路 Next 完成安装
4. 安装程序会自动将 `C:\Program Files\dotnet\` 加入系统 `PATH`

**方式二：winget（命令行）**

```powershell
winget install Microsoft.DotNet.SDK.8
```

**方式三：Visual Studio 自带**

如果已安装 Visual Studio 2022，选上 **".NET 桌面开发"** 工作负载，安装器会自动附带 .NET SDK。

### 2.2 macOS

**方式一：官方安装包**

1. 打开 [https://dotnet.microsoft.com/en-us/download](https://dotnet.microsoft.com/en-us/download)
2. 选择 **"macOS"** 标签，下载 `.pkg` 安装包
3. 双击运行，按提示完成安装
4. SDK 默认安装到 `/usr/local/share/dotnet/`，并在 `/usr/local/bin/dotnet` 创建符号链接

**方式二：Homebrew**

```bash
brew install dotnet-sdk
```

### 2.3 Linux

不同发行版略有差异，以下是常见发行版的安装方式：

**Ubuntu 22.04+ / Debian 12+**

```bash
# 1. 添加 Microsoft 包仓库
wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
rm packages-microsoft-prod.deb

# 2. 安装 SDK
sudo apt-get update
sudo apt-get install -y dotnet-sdk-8.0
```

**Fedora / RHEL / CentOS**

```bash
sudo dnf install dotnet-sdk-8.0
```

**使用安装脚本（所有发行版通用）**

```bash
curl -sSL https://dot.net/v1/dotnet-install.sh | bash /dev/stdin --channel 8.0
```

安装脚本默认安装到 `$HOME/.dotnet/`，需要手动将路径加入 `PATH`（见 4.3 节）。

---

## 3. 验证安装

### 3.1 基本版本检查

打开终端（Windows 用 PowerShell 或 CMD），运行：

```bash
dotnet --version
```

如果输出类似 `8.0.4`，说明安装成功。`--version` 返回的是**当前活跃的 SDK 的版本号**（受 `global.json` 影响，见第 6 节）。

### 3.2 完整环境信息

```bash
dotnet --info
```

这个命令输出所有你需要知道的运行环境信息。**务必看懂这个命令的输出**——排查环境问题时，它是第一个要看的地方。

**典型输出（Windows，.NET 8 SDK）：**

```text
.NET SDK:
 Version:           8.0.404
 Commit:            2c8ae4c300
 Workload version:  8.0.400-manifests.a16f05a9
 MSBuild version:   17.11.9+a69bbaaf5

运行时环境:
 OS Name:     Windows
 OS Version:  10.0.26100
 OS Platform: Windows
 RID:         win-x64
 Base Path:   C:\Program Files\dotnet\sdk\8.0.404\

.NET workloads installed:
 没有安装任何工作负载。

Host:
  Version:      8.0.11
  Architecture: x64
  Commit:       08338fcaa5

.NET SDKs installed:
  8.0.404 [C:\Program Files\dotnet\sdk]

.NET runtimes installed:
  Microsoft.AspNetCore.App 8.0.11 [C:\Program Files\dotnet\shared\Microsoft.AspNetCore.App]
  Microsoft.NETCore.App 8.0.11 [C:\Program Files\dotnet\shared\Microsoft.NETCore.App]
  Microsoft.WindowsDesktop.App 8.0.11 [C:\Program Files\dotnet\shared\Microsoft.WindowsDesktop.App]
```

> [!note] 关键字段解读
> - **.NET SDKs installed** — 你装了哪些 SDK 版本，每个能编译对应版本的代码
> - **.NET runtimes installed** — 你装了哪些运行时，应用运行时实际使用的是这里列出的
> - **RID** (Runtime Identifier) — `win-x64`、`osx-arm64`、`linux-x64` 等，决定发布时的目标平台
> - **Base Path** — SDK 的安装路径

### 3.3 列出已安装的 SDK 和运行时

```bash
# 列出所有已安装的 SDK 版本
dotnet --list-sdks

# 列出所有已安装的运行时
dotnet --list-runtimes
```

**典型输出 `dotnet --list-sdks`：**

```text
6.0.428 [C:\Program Files\dotnet\sdk]
8.0.404 [C:\Program Files\dotnet\sdk]
```

**典型输出 `dotnet --list-runtimes`：**

```text
Microsoft.AspNetCore.App 6.0.36 [C:\Program Files\dotnet\shared\Microsoft.AspNetCore.App]
Microsoft.AspNetCore.App 8.0.11 [C:\Program Files\dotnet\shared\Microsoft.AspNetCore.App]
Microsoft.NETCore.App 6.0.36 [C:\Program Files\dotnet\shared\Microsoft.NETCore.App]
Microsoft.NETCore.App 8.0.11 [C:\Program Files\dotnet\shared\Microsoft.NETCore.App]
Microsoft.WindowsDesktop.App 8.0.11 [C:\Program Files\dotnet\shared\Microsoft.WindowsDesktop.App]
```

> [!tip] 多版本共存
> .NET 的 SDK 和 Runtime 可以**并存多个主版本和补丁版本**，互不冲突。`dotnet` CLI 会根据项目文件自动选择合适的版本。没有项目上下文时（如执行 `dotnet --version`），默认使用最新安装的 SDK。

### 3.4 检查已安装的工作负载（Workloads）

```bash
# 列出已安装的工作负载
dotnet workload list

# 搜索可用的工作负载
dotnet workload search
```

**典型输出：**

```text
已安装的工作负载 ID     清单版本                          安装源
-------------------------------------------------------------------
wasm-tools             8.0.11/8.0.100                     SDK 8.0.400
maui-android           8.0.82/8.0.100                     SDK 8.0.400
```

> [!note] 什么是 Workload
> Workload 是 .NET 6 引入的可选 SDK 组件，用于特定技术栈：
> - `wasm-tools` — WebAssembly 编译工具链
> - `maui` — .NET MAUI 移动/桌面开发
> - `android` / `ios` — 移动平台开发
> - `aspire` — 云原生开发工具
>
> 如果只是做控制台/Web/类库开发，不需要安装任何 workload。

---

## 4. 环境变量配置

### 4.1 关键环境变量

| 变量 | 作用 | 备注 |
|------|------|------|
| `PATH` | 必须包含 `dotnet` 可执行文件所在目录 | 官方安装包自动设置 |
| `DOTNET_ROOT` | 指定 .NET 安装根目录 | 手动安装时需设置，特别是 CI 环境 |
| `DOTNET_CLI_TELEMETRY_OPTOUT` | 设为 `1` 或 `true` 关闭遥测 | 可选，CI 环境建议关闭 |
| `DOTNET_MULTILEVEL_LOOKUP` | 设为 `0` 禁用多级版本查找 | 在 Docker 等隔离环境中确保版本隔离 |
| `NUGET_PACKAGES` | 指定全局 NuGet 缓存目录 | 默认 `%USERPROFILE%\.nuget\packages` |
| `DOTNET_NOLOGO` | 设为 `1` 或 `true` 隐藏版权横幅 | CI 日志更干净 |

### 4.2 查看当前环境变量

```bash
# Windows (PowerShell)
echo $env:PATH | Select-String "dotnet"
echo $env:DOTNET_ROOT

# macOS / Linux
echo $PATH | tr ':' '\n' | grep dotnet
echo $DOTNET_ROOT
```

### 4.3 手动安装时的 PATH 配置

如果你使用 `dotnet-install.sh` / `dotnet-install.ps1` 脚本安装了 .NET 到非默认路径（如 `$HOME/.dotnet/`），必须手动配置环境变量：

**Linux / macOS (`~/.bashrc` 或 `~/.zshrc`)：**

```bash
export DOTNET_ROOT="$HOME/.dotnet"
export PATH="$DOTNET_ROOT:$PATH"
```

**Windows (PowerShell，添加到 Profile)：**

```powershell
[Environment]::SetEnvironmentVariable(
    "DOTNET_ROOT",
    "$env:USERPROFILE\.dotnet",
    [EnvironmentVariableTarget]::User
)

# 将 $HOME\.dotnet 加入 PATH（如果尚未加入）
$dotnetPath = "$env:USERPROFILE\.dotnet"
if ($env:PATH -notlike "*$dotnetPath*") {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$env:PATH;$dotnetPath",
        [EnvironmentVariableTarget]::User
    )
}
```

> [!warning] 修改后必须重开终端
> 修改 `~/.bashrc` / `~/.zshrc` 或 Windows 系统环境变量后，必须**重新打开终端**才能生效。或者执行 `source ~/.bashrc`（Linux/macOS）或 `refreshenv`（如果安装了 Chocolatey）。

---

## 5. 完整验证：创建并运行 Hello World 控制台应用

环境配好后，用下面这个完整流程验证一切正常工作。

### 步骤 1：创建工作目录

```bash
mkdir dotnet-test && cd dotnet-test
```

### 步骤 2：创建控制台项目

```bash
dotnet new console -n HelloWorld
```

**输出：**
```text
欢迎使用 .NET 8.0!
---------------------
已成功创建模板"控制台应用"。

正在处理创建后操作...
正在还原 D:\dotnet-test\HelloWorld\HelloWorld.csproj:
  正在确定要还原的项目…
  已还原 D:\dotnet-test\HelloWorld\HelloWorld.csproj (用时 123 ms)。
已成功还原。
```

### 步骤 3：查看项目结构

```bash
cd HelloWorld
ls    # Linux/macOS
dir   # Windows
```

你会看到两个文件：
- `HelloWorld.csproj` — 项目配置文件
- `Program.cs` — 入口代码文件

### 步骤 4：查看生成的代码

生成的 `Program.cs` 内容（.NET 8+ 默认使用顶级语句，不需要显式 `Main` 方法）：

```csharp
// 查看 Program.cs
Console.WriteLine("Hello, World!");
```

### 步骤 5：运行

```bash
dotnet run
```

**预期输出：**

```text
Hello, World!
```

### 步骤 6：编译验证

```bash
dotnet build

# 或者只编译不运行
dotnet build --configuration Release
```

**预期输出：**

```text
MSBuild version 17.11.9+a69bbaaf5 for .NET
  正在确定要还原的项目…
  所有项目均是最新的，无法还原。
  HelloWorld -> D:\dotnet-test\HelloWorld\bin\Release\net8.0\HelloWorld.dll

已成功生成。
    0 个警告
    0 个错误
```

### 步骤 7：直接运行编译产物

```bash
# Windows
.\bin\Release\net8.0\HelloWorld.exe

# macOS / Linux
./bin/Release/net8.0/HelloWorld
```

**预期输出：**

```text
Hello, World!
```

### 步骤 8：清理

```bash
# 回到上级目录
cd ..

# 删除整个测试目录
rm -rf dotnet-test   # Linux/macOS
# 或
Remove-Item -Recurse -Force dotnet-test   # PowerShell
```

---

## 6. global.json — 锁定 SDK 版本

### 6.1 问题场景

团队项目使用 .NET 8.0.4 开发，但你的机器上安装了 8.0.4 和 9.0.0。如果其他人也混用不同版本，可能导致：

- 不同开发者编译出的 IL 代码细微差异
- 某个 SDK 版本引入的 bug 只在一部分人机器上出现
- CI 使用 8.0.4 构建通过，本地 9.0.0 编译失败（或反之）

### 6.2 解决方案

在项目根目录（通常是 solution 根目录）放置 `global.json` 文件，明确声明需要的 SDK 版本。

```json
{
  "sdk": {
    "version": "8.0.404",
    "rollForward": "latestPatch",
    "allowPrerelease": false
  }
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | `string` | 需要的 SDK 版本 |
| `rollForward` | `string` | 版本回退策略（见下表） |
| `allowPrerelease` | `bool` | 是否允许使用预览版 SDK（默认 `false`） |

### 6.3 rollForward 策略

`rollForward` 控制当指定版本不可用时，CLI 如何选择替代版本：

| 值 | 行为 |
|----|------|
| `patch` | 使用同主次版本的更高补丁（默认，.NET 9+）。只在该主次版本内查找 |
| `latestPatch` | 等同于 `patch`，使用同主次版本的最高补丁 |
| `minor` | 可以回退到相同主版本的更高次版本 |
| `major` | 可以回退到更高主版本 |
| `latestMinor` | 使用相同主版本下最高的次版本（及其最新补丁） |
| `latestMajor` | 使用安装的最高主版本——**不建议用于团队项目** |
| `disable` | 不向前回退。精确版本不匹配就报错 |

> [!tip] 推荐策略
> 团队项目推荐使用 `latestPatch` 或 `patch`——允许安全补丁自动修复，但限制主次版本变更。个人项目可以使用 `latestMinor` 享受最新功能。

### 6.4 创建 global.json

```bash
# 在项目根目录创建 global.json，锁定当前安装的最新 SDK
dotnet new globaljson

# 或手动指定版本
dotnet new globaljson --sdk-version 8.0.404
```

### 6.5 验证 global.json 生效

```bash
# 在包含 global.json 的目录下运行
dotnet --version
```

如果机器上没有 `global.json` 指定的版本（且 `rollForward` 无法找到合适版本），会看到类似以下错误：

```text
The command could not be loaded, possibly because:
  * You intended to execute a .NET application:
      The application '--version' does not exist.
  * You intended to execute a .NET SDK command:
      A compatible .NET SDK was not found.

Requested SDK version: 8.0.404
global.json file: D:\projects\myapp\global.json

Installed SDKs:
  6.0.428 [C:\Program Files\dotnet\sdk]

Install the [8.0.404] .NET SDK or update [D:\projects\myapp\global.json] to match an installed SDK.
```

> [!warning] global.json 的作用范围
> `global.json` 影响它所在目录**及所有子目录**下的 `dotnet` 命令。根目录放一个 `global.json`，整个 solution 都受影响。多个 `global.json` 时，最近的（最接近当前目录的）生效。

---

## 7. 练习

### 练习 1：环境清单（基础）

执行以下命令，把输出记录下来：

```bash
dotnet --version
dotnet --list-sdks
dotnet --list-runtimes
dotnet workload list
```

然后回答以下问题：
1. 你的机器上安装了哪几个 SDK 版本？
2. 当前活跃的 SDK 版本是什么？
3. 安装了哪些 Runtime？这些 Runtime 分别是什么用途（`NETCore.App`、`AspNetCore.App`、`WindowsDesktop.App`）？
4. 是否安装了任何 workload？如果有，是什么用途的工作负载？

### 练习 2：global.json 版本锁定实验（中级）

1. 创建一个临时目录，在其中创建一个 `global.json` 文件，将 SDK 版本锁定为你机器上**不存在**的版本（例如 `99.9.999`），`rollForward` 设为 `disable`。
2. 在该目录下尝试运行 `dotnet --version`，观察错误信息。
3. 将 `rollForward` 改为 `latestMajor`，再次运行 `dotnet --version`，观察是否成功，输出的是什么版本。
4. 删除 `global.json`，确认 `dotnet --version` 恢复原来的输出。

> [!tip] 提示
> 创建 `global.json` 可用命令：`dotnet new globaljson --sdk-version 99.9.999`，然后手动编辑 `rollForward` 字段。

### 练习 3：多版本 SDK 共存实验（挑战）

如果你的机器上安装了多个 SDK 版本：

1. 创建两个独立的目录 `proj-v6` 和 `proj-v8`。
2. 在 `proj-v6` 中创建 `global.json` 锁定 SDK 6.0，在 `proj-v8` 中锁定 SDK 8.0。
3. 分别在两个目录中执行 `dotnet --version`，验证它们返回不同的 SDK 版本号。
4. 在两个目录中各创建一个控制台项目（`dotnet new console`），查看生成的 `.csproj` 中 `<TargetFramework>` 的默认值有何不同。
5. 在两个项目中分别将 `Program.cs` 修改为输出当前 .NET 运行时版本：

```csharp
using System.Runtime.InteropServices;
Console.WriteLine($"Running on .NET {RuntimeInformation.FrameworkDescription}");
```

分别运行，观察输出差异。

---

## 8. 扩展阅读

- [.NET 官方下载页](https://dotnet.microsoft.com/en-us/download) — 获取最新 SDK 和 Runtime
- [.NET SDK 和 Runtime 版本说明](https://learn.microsoft.com/en-us/dotnet/core/releases-and-support) — 生命周期、LTS/STS 策略、补丁发布计划
- [选择要使用的 .NET 版本](https://learn.microsoft.com/en-us/dotnet/core/versions/selection) — `global.json`、`rollForward` 的完整官方文档
- [dotnet-install 脚本参考](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-install-script) — CI/CD 自动化安装的官方指南
- [检查已安装的 .NET 版本](https://learn.microsoft.com/en-us/dotnet/core/install/how-to-detect-installed-versions) — Windows/macOS/Linux 上的完整检测方法
- [.NET 环境变量](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-environment-variables) — 所有 `DOTNET_*` 变量的完整列表和说明
- [.NET 容器化最佳实践](https://learn.microsoft.com/en-us/dotnet/core/docker/introduction) — Docker 镜像中 SDK vs Runtime 的选择策略

---

## 9. 常见陷阱

### 陷阱 1: `dotnet` 命令不识别（"不是内部或外部命令"）

**原因**：`PATH` 环境变量不包含 `dotnet` 可执行文件所在目录。

**排查**：

```bash
# Windows — 检查 dotnet 在哪里
where dotnet

# macOS / Linux
which dotnet
```

**修复**：
- **官方安装包**：通常自动配置 PATH。如果没有，检查 `C:\Program Files\dotnet\` 或 `/usr/share/dotnet/` 是否在 PATH 中
- **手动安装**：按 4.3 节配置 `DOTNET_ROOT` 和 `PATH`
- **Windows 特殊情况**：安装后必须**重新打开终端**（新开的终端才会读取更新后的系统环境变量）

### 陷阱 2: `dotnet --version` 和预期不符

**原因**：当前目录或其父目录中存在 `global.json` 锁定了特定版本。

**排查**：

```bash
# 检查当前目录是否有 global.json
dotnet --list-sdks
# 对比 --version 输出和 --list-sdks 列出的版本
```

如果 `--version` 的值不是你安装的最新 SDK，说明有 `global.json` 在起作用。找到它：

```bash
# Windows
Get-ChildItem -Path . -Recurse -Filter global.json -Depth 5

# macOS / Linux
find . -name global.json -maxdepth 5
```

### 陷阱 3: `dotnet new` 创建的项目默认目标框架不是预期的

**原因**：不同 SDK 主版本的默认 `TargetFramework` 不同。例如 SDK 8.0 默认生成 `net8.0`，SDK 6.0 默认生成 `net6.0`。

**排查**：

```bash
dotnet --version
# 输出决定了 dotnet new 产生的默认 TargetFramework
```

**修复**：创建项目时显式指定目标框架：

```bash
dotnet new console -n MyApp --framework net8.0
```

### 陷阱 4: 安装了 SDK 但仍然报 "A compatible .NET SDK was not found"

**原因**：`global.json` 中的 `rollForward` 策略和已安装的 SDK 不匹配，或者 `rollForward` 被设为 `disable` 但指定的 SDK 不存在。

**修复**：
1. 运行 `dotnet --list-sdks` 确认已安装的版本
2. 修改 `global.json` 中的 `version` 为已安装的版本
3. 或将 `rollForward` 改为 `latestMajor`（但注意团队协作的一致性）

### 陷阱 5: Docker 镜像中 SDK 体积过大

**原因**：开发阶段使用 `mcr.microsoft.com/dotnet/sdk:8.0` 镜像，发布阶段使用 `mcr.microsoft.com/dotnet/runtime:8.0` 镜像。但很多人把 SDK 镜像也推到生产环境。

**正确做法**：使用多阶段构建（multi-stage build）：

```dockerfile
# 阶段 1: 构建 — 使用 SDK 镜像
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish -c Release -o /app

# 阶段 2: 运行 — 使用 Runtime 镜像（更小、更安全）
FROM mcr.microsoft.com/dotnet/runtime:8.0
WORKDIR /app
COPY --from=build /app .
ENTRYPOINT ["./MyApp"]
```

最终镜像只包含 Runtime，体积从 ~800MB 缩减到 ~200MB。

### 陷阱 6: 忘记安装 ASP.NET Core Runtime

**原因**：开发机上的 SDK 自带 ASP.NET Core Runtime，所以 `dotnet run` 能用。但发布到服务器后，如果只装了 `Microsoft.NETCore.App` 而没有装 `Microsoft.AspNetCore.App`，Web 应用启动时会报错。

**修复**：服务器上安装 ASP.NET Core Runtime（不是 SDK）：

```bash
# Ubuntu
sudo apt-get install -y aspnetcore-runtime-8.0

# 或使用安装脚本
curl -sSL https://dot.net/v1/dotnet-install.sh | bash /dev/stdin --runtime aspnetcore --channel 8.0
```

用 `dotnet --list-runtimes` 确认 `Microsoft.AspNetCore.App` 已安装。
