---
title: "dotnet tool — 全局与本地工具"
updated: 2026-06-10
tags: [dotnet, cli, tool, global-tool, local-tool]
---

# `dotnet tool` — 全局与本地工具

> 学习阶段: 第四阶段 — 扩展工具与实战
> 预计耗时: 45 分钟
> 前置: [[01-dotnet-env-setup]]

---

## 概念讲解

### 什么是 .NET Tool

.NET Tool 是通过 `dotnet` CLI 安装和运行的命令行工具。它们是 NuGet 包的一种特殊形式，打包了可执行的控制台应用程序。

> [!note] 类比
> .NET Tool 之于 `dotnet` CLI，就像 npm 全局包之于 `node`，或者 `pip install --user` 之于 Python。它们扩展了 `dotnet` 的能力，让你可以在终端里直接调用新命令。

### 全局工具 vs 本地工具

| 维度 | 全局工具 (`-g`) | 本地工具 (manifest) |
|------|----------------|---------------------|
| **安装位置** | 用户 profile 目录 (`~/.dotnet/tools/`) | 当前仓库的 `.config/dotnet-tools.json` |
| **作用域** | 整个机器，任何目录都能用 | 仅当前仓库 (及其子目录) |
| **版本管理** | 手动管理，全局唯一版本 | 通过 manifest 锁定版本，团队成员共享 |
| **适用场景** | 个人通用工具 (格式化、诊断) | 项目特定的工具 (EF Core 迁移、代码分析) |
| **调用方式** | 直接输入命令名 (如 `dotnet-format`) | `dotnet tool run <名称>` 或直接 `dotnet <名称>` |

> [!tip] 什么时候用哪种
> - **全局**: 你每天都会用的通用工具，比如代码格式化器、NuGet 包检查器
> - **本地**: 项目团队共同依赖的工具，版本需要锁定，确保 CI/CD 和每个开发者行为一致

### 工具清单 (Tool Manifest)

本地工具依赖一个 **Tool Manifest** 文件，位于 `.config/dotnet-tools.json`。它记录了当前仓库需要哪些工具、各自版本号——类似 `package.json` 之于 Node 项目。

```json
{
  "version": 1,
  "isRoot": true,
  "tools": {
    "dotnet-ef": {
      "version": "8.0.0",
      "commands": ["dotnet-ef"]
    },
    "dotnet-format": {
      "version": "5.1.250801",
      "commands": ["dotnet-format"]
    }
  }
}
```

> [!important] Manifest 文件必须提交到版本控制
> `.config/dotnet-tools.json` 应该纳入 Git 管理。其他团队成员 `dotnet tool restore` 即可安装完全相同的工具版本。

---

## 命令详解

### `dotnet new tool-manifest` — 创建 Manifest

在使用本地工具之前，先创建 manifest 文件：

```bash
dotnet new tool-manifest
```

输出:
```
The template "Dotnet local tool manifest file" was created successfully.
```

这会在当前目录的 `.config/` 下生成 `dotnet-tools.json`。如果 `.config/` 不存在，会自动创建。

> [!warning] 不要在已有 manifest 的仓库再运行此命令
> 如果 `.config/dotnet-tools.json` 已经存在，运行 `dotnet new tool-manifest` 会**覆盖**它，丢失所有已安装工具的记录。

### `dotnet tool install` — 安装工具

#### 安装全局工具

```bash
dotnet tool install -g dotnet-format
```

- `-g` / `--global`: 安装到全局
- 安装后，工具命令可直接在终端中使用

#### 安装本地工具

```bash
# 先确保有 manifest
dotnet new tool-manifest

# 安装本地工具
dotnet tool install dotnet-format
```

- 不加 `-g` 就是本地安装
- 工具信息写入 `.config/dotnet-tools.json`

#### 指定版本

```bash
dotnet tool install -g dotnet-format --version 5.1.250801
```

- `--version <VERSION>`: 安装特定版本
- 如果不指定，默认安装最新稳定版

#### 常用安装选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `-g` / `--global` | 全局安装 | `dotnet tool install -g dotnet-format` |
| `--local` | 本地安装 (显式声明, 默认行为) | `dotnet tool install --local dotnet-format` |
| `--version` | 指定版本 | `dotnet tool install dotnet-format --version 7.3.0` |
| `--tool-path <PATH>` | 安装到自定义目录 | `dotnet tool install dotnet-format --tool-path ./tools/` |
| `--tool-manifest <PATH>` | 指定 manifest 路径 | `dotnet tool install dotnet-format --tool-manifest sub/.config/dotnet-tools.json` |
| `--add-source <URL>` | 从额外的 NuGet 源安装 | `dotnet tool install MyTool --add-source ./local-packages/` |
| `--configfile <PATH>` | 使用自定义 NuGet 配置 | `dotnet tool install MyTool --configfile NuGet.custom.config` |
| `--prerelease` | 允许安装预发布版本 | `dotnet tool install -g dotnet-ef --prerelease` |
| `--framework <TFM>` | 指定目标框架 | `dotnet tool install MyTool --framework net8.0` |

### `dotnet tool uninstall` — 卸载工具

```bash
# 卸载全局工具
dotnet tool uninstall -g dotnet-format

# 卸载本地工具
dotnet tool uninstall dotnet-format
```

### `dotnet tool update` — 更新工具

```bash
# 更新全局工具到最新版本
dotnet tool update -g dotnet-format

# 更新本地工具到最新版本
dotnet tool update dotnet-format

# 更新到指定版本
dotnet tool update -g dotnet-format --version 8.0.0
```

### `dotnet tool list` — 列出已安装的工具

```bash
# 列出全局工具
dotnet tool list -g

# 列出本地工具 (当前目录的 manifest)
dotnet tool list

# 列出本地工具 (指定 manifest)
dotnet tool list --tool-manifest sub/.config/dotnet-tools.json
```

输出示例:
```
Package Id      Version      Commands
-----------------------------------------------------------
dotnet-format   7.3.0        dotnet-format
dotnet-ef       8.0.0        dotnet-ef
```

### `dotnet tool run` — 运行本地工具

本地安装的工具不能直接在终端中输入命令名，需要通过 `dotnet tool run` 调用：

```bash
# 运行本地安装的 dotnet-format
dotnet tool run dotnet-format

# 传递参数给工具
dotnet tool run dotnet-format -- --check

# 简写形式: dotnet <tool-name> (直接以 dotnet 开头)
# 注意：这只对名称以 "dotnet-" 开头的工具有效
dotnet format --check
```

> [!tip] `dotnet tool run` vs 直接调用
> - 本地工具: 必须用 `dotnet tool run <name>` (或对 `dotnet-*` 工具可简写 `dotnet <shortname>`)
> - 全局工具: 直接输入 `dotnet-format` 即可，不需要 `dotnet tool run`

### `dotnet tool restore` — 还原本地工具

当克隆一个已有 manifest 的仓库时，运行此命令安装 manifest 中声明的所有工具：

```bash
# 在仓库根目录运行
dotnet tool restore
```

> [!note] CI/CD 集成
> 在 CI 流水线中，构建脚本的第一步通常是 `dotnet tool restore`，确保所有需要的本地工具已安装。

---

## Manifest 文件格式

`.config/dotnet-tools.json` 的完整结构：

```json
{
  "version": 1,
  "isRoot": true,
  "tools": {
    "<PackageId>": {
      "version": "<version-string>",
      "commands": ["<command-name>"]
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | `int` | Manifest 格式版本，当前固定为 `1` |
| `isRoot` | `bool` | 是否是该仓库的根 manifest。`true` = 根目录, `false` = 子目录 |
| `tools` | `object` | 工具字典，key 是 NuGet 包 ID |
| `tools.<pkg>.version` | `string` | 安装的工具版本号 (NuGet 语义版本) |
| `tools.<pkg>.commands` | `string[]` | 该工具包暴露的命令名列表 |

### `isRoot` 的用途

一个仓库可以有**多个** manifest 文件 (每个子目录一个)，但只有根目录的 manifest `isRoot` 为 `true`。子目录的 manifest 继承父级工具，`isRoot` 为 `false` 表示它还会去上级目录寻找 manifest。

```bash
# 示例：为子目录创建独立的 manifest
cd ./src/MyLibrary
dotnet new tool-manifest
```

这会生成 `isRoot: false` 的 manifest——该子目录的工具集会合并且覆盖父级定义。

---

## 常用 .NET 工具一览

### 代码质量类

| 工具 | 包 ID | 用途 | 安装命令 |
|------|-------|------|---------|
| **dotnet-format** | `dotnet-format` | 代码格式化 (基于 .editorconfig) | `dotnet tool install -g dotnet-format` |
| **CSharpier** | `csharpier` | 代码格式化 (类 Prettier 风格) | `dotnet tool install -g csharpier` |
| **dotnet-sonarscanner** | `dotnet-sonarscanner` | SonarQube / SonarCloud 代码分析 | `dotnet tool install -g dotnet-sonarscanner` |

### 数据与 ORM 类

| 工具 | 包 ID | 用途 | 安装命令 |
|------|-------|------|---------|
| **dotnet-ef** | `dotnet-ef` | EF Core CLI — 数据库迁移、脚手架 | `dotnet tool install -g dotnet-ef` |

### 依赖管理类

| 工具 | 包 ID | 用途 | 安装命令 |
|------|-------|------|---------|
| **dotnet-outdated** | `dotnet-outdated-tool` | 检查项目中过时的 NuGet 包 | `dotnet tool install -g dotnet-outdated-tool` |

### 诊断与性能类

| 工具 | 包 ID | 用途 | 安装命令 |
|------|-------|------|---------|
| **dotnet-dump** | `dotnet-dump` | 收集和分析 Windows/Linux 内存转储 | `dotnet tool install -g dotnet-dump` |
| **dotnet-trace** | `dotnet-trace` | 收集运行时事件和 CPU 采样 | `dotnet tool install -g dotnet-trace` |
| **dotnet-counters** | `dotnet-counters` | 实时监控运行时性能计数器 | `dotnet tool install -g dotnet-counters` |

### 各工具典型用法

```bash
# dotnet-format: 检查代码风格但不修改
dotnet format --verify-no-changes

# CSharpier: 格式化整个解决方案
dotnet csharpier .

# dotnet-ef: 创建数据库迁移
dotnet ef migrations add InitialCreate

# dotnet-outdated: 检查哪些包有新版本可用
dotnet outdated

# dotnet-dump: 分析进程转储
dotnet dump collect -p <PID>
dotnet dump analyze dump.dmp

# dotnet-trace: 收集 30 秒 CPU 采样
dotnet trace collect -p <PID> --duration 00:00:30

# dotnet-counters: 监控 GC、CPU、内存
dotnet counters monitor -p <PID>
```

---

## 完整示例

### 示例一：全局安装 dotnet-format

从头到尾演示全局工具的安装和使用。

```bash
# Step 1: 验证 .NET SDK 可用
dotnet --version
# 输出: 8.0.100 (你的版本可能不同)

# Step 2: 安装 dotnet-format 全局工具
dotnet tool install -g dotnet-format
# 输出:
# 可使用以下命令调用工具: dotnet-format
# 已成功安装工具 "dotnet-format"(版本 "7.3.1")。

# Step 3: 验证安装
dotnet tool list -g
# 输出:
# 包 ID              版本         命令
# -----------------------------------------------------------
# dotnet-format      7.3.1        dotnet-format

# Step 4: 创建测试项目
mkdir FormatDemo && cd FormatDemo
dotnet new console -n FormatDemo
cd FormatDemo

# Step 5: 写一段格式混乱的代码 (故意缩进不一致)
# 编辑 Program.cs 为:
cat > Program.cs << 'EOF'
using System;
namespace FormatDemo {
class Program {
    static void Main(string[] args)
    {
    Console.WriteLine("Hello, World!");
        Console.WriteLine("This is poorly formatted.");
    }
}
}
EOF

# Step 6: 格式化代码
dotnet-format

# Step 7: 验证格式化结果
cat Program.cs
# 输出: (缩进已自动修正)
# using System;
#
# namespace FormatDemo
# {
#     class Program
#     {
#         static void Main(string[] args)
#         {
#             Console.WriteLine("Hello, World!");
#             Console.WriteLine("This is poorly formatted.");
#         }
#     }
# }

# Step 8: 更新工具到最新版
dotnet tool update -g dotnet-format

# Step 9: 卸载工具
dotnet tool uninstall -g dotnet-format
```

### 示例二：创建 Tool Manifest 并安装本地工具

演示团队协作场景下的本地工具管理。

```bash
# Step 1: 初始化一个新仓库场景
mkdir ToolManifestDemo && cd ToolManifestDemo
dotnet new sln -n ToolManifestDemo

# Step 2: 创建 tool manifest
dotnet new tool-manifest
# 输出: The template "Dotnet local tool manifest file" was created successfully.

# Step 3: 查看生成的 manifest 文件
cat .config/dotnet-tools.json
# 输出:
# {
#   "version": 1,
#   "isRoot": true,
#   "tools": {}
# }

# Step 4: 安装本地工具
dotnet tool install dotnet-format
# 输出:
# 可使用以下命令调用工具: dotnet-format
# 已成功安装工具 "dotnet-format"(版本 "7.3.1")。

# Step 5: 再安装一个本地工具
dotnet tool install dotnet-outdated-tool
# 输出:
# 可使用以下命令调用工具: dotnet-outdated
# 已成功安装工具 "dotnet-outdated-tool"(版本 "4.5.0")。

# Step 6: 查看 manifest 的变化
cat .config/dotnet-tools.json
# 输出:
# {
#   "version": 1,
#   "isRoot": true,
#   "tools": {
#     "dotnet-format": {
#       "version": "7.3.1",
#       "commands": ["dotnet-format"]
#     },
#     "dotnet-outdated-tool": {
#       "version": "4.5.0",
#       "commands": ["dotnet-outdated"]
#     }
#   }
# }

# Step 7: 列出本地工具
dotnet tool list
# 输出:
# 包 ID                  版本         命令
# -----------------------------------------------------------
# dotnet-format          7.3.1        dotnet-format
# dotnet-outdated-tool   4.5.0        dotnet-outdated

# Step 8: 使用本地工具
# 方式 A: dotnet tool run
dotnet tool run dotnet-format -- --check

# 方式 B: 对 dotnet-* 工具可用简写
dotnet format --check
dotnet outdated --version

# Step 9: 模拟团队成员克隆仓库后还原工具
# 重新安装到临时目录
mkdir ../RestoreTest
cd ../RestoreTest
cp ../ToolManifestDemo/.config/dotnet-tools.json .config/ -r
# 即使没有 tools-install 历史，restore 依然能安装
# (实际场景中 manifest 文件来自 git clone)

# Step 10: 卸载本地工具
cd ../ToolManifestDemo
dotnet tool uninstall dotnet-format
dotnet tool uninstall dotnet-outdated-tool
```

### 示例三：CI/CD 流水线集成

一个典型的 CI 脚本中使用本地工具的模式：

```bash
#!/bin/bash
# ci-build.sh — 典型 .NET CI 构建脚本

set -e

echo "Restoring .NET tools..."
dotnet tool restore

echo "Checking code formatting..."
dotnet format --verify-no-changes

echo "Checking for outdated packages..."
dotnet outdated --fail-on-outdated

echo "Building solution..."
dotnet build -c Release

echo "Running tests..."
dotnet test -c Release --no-build

echo "CI build completed successfully."
```

对应的 `.config/dotnet-tools.json`:

```json
{
  "version": 1,
  "isRoot": true,
  "tools": {
    "dotnet-format": {
      "version": "7.3.1",
      "commands": ["dotnet-format"]
    },
    "dotnet-outdated-tool": {
      "version": "4.5.0",
      "commands": ["dotnet-outdated"]
    }
  }
}
```

---

## 练习

### 练习 1: 全局工具生命周期

1. 安装 `dotnet-outdated-tool` 为全局工具
2. 创建一个新的控制台项目，添加一个过时的 NuGet 包 (如 `Newtonsoft.Json` 的旧版本)
3. 运行 `dotnet outdated` 查看输出
4. 更新 `dotnet-outdated-tool` 到最新版
5. 列出所有全局工具，确认版本
6. 卸载该工具

> [!tip] 提示
> 用 `dotnet add package Newtonsoft.Json --version 12.0.1` 添加一个旧版本包。然后 `dotnet outdated` 会告诉你哪些包有新版本可用。

### 练习 2: 本地工具与 Team Workflow

1. 在一个新目录中初始化 git 仓库，创建 `.sln` 文件
2. 用 `dotnet new tool-manifest` 创建 manifest
3. 安装 `dotnet-format` 作为本地工具 (指定一个具体版本，如 `--version 6.0.0`)
4. 将 `.config/dotnet-tools.json` 加入 git 并提交
5. 切换到另一个目录，仅拷贝 manifest 文件过去
6. 运行 `dotnet tool restore` 还原工具
7. 列出本地工具，验证版本一致

> [!tip] 提示
> 模拟多人协作场景的关键：你提交的是 manifest 文件，不是工具本身。新成员 clone 后 `dotnet tool restore` 即可。

### 练习 3: 诊断工具实战

1. 安装 `dotnet-counters` 为全局工具
2. 创建一个简单的 .NET 控制台程序，持续运行 (比如一个 `while(true)` 循环做 CPU 密集型计算)
3. 用 `dotnet-counters` 监控该进程的 CPU 使用率和 GC 统计
4. 再用 `dotnet-trace` 收集 5 秒的性能采样
5. 查看 trace 结果，观察程序的 CPU 热点

> [!tip] 提示
> ```bash
> # 监控进程 (先获取 PID 用 dotnet-counters ps)
> dotnet-counters monitor -p <PID> --counters System.Runtime
>
> # 收集 trace
> dotnet-trace collect -p <PID> --duration 00:00:05 -o trace.nettrace
> ```

---

## 扩展阅读

- [.NET 工具官方文档 (Microsoft Learn)](https://learn.microsoft.com/en-us/dotnet/core/tools/global-tools)
- [dotnet tool install 命令参考](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-tool-install)
- [.NET 工具清单架构](https://learn.microsoft.com/en-us/dotnet/core/tools/local-tools-how-to-use)
- [dotnet format — GitHub 仓库](https://github.com/dotnet/format)
- [CSharpier — Opinionated Code Formatter](https://csharpier.com/)
- [dotnet-outdated — GitHub 仓库](https://github.com/dotnet-outdated/dotnet-outdated)
- [dotnet-ef — EF Core 工具参考](https://learn.microsoft.com/en-us/ef/core/cli/dotnet)
- [诊断工具概览 (`dotnet-dump`, `dotnet-trace`, `dotnet-counters`)](https://learn.microsoft.com/en-us/dotnet/core/diagnostics/tools-overview)
- [SonarScanner for .NET](https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner-for-dotnet/)

---

## 常见陷阱

### 陷阱 1: 全局安装后工具找不到

**现象**:
```bash
$ dotnet tool install -g dotnet-format
$ dotnet-format
bash: dotnet-format: command not found
```

**原因**: 全局工具安装到 `~/.dotnet/tools/` 目录，但此目录不在 `PATH` 中。

**解决**: 将工具目录加入 `PATH`:

```bash
# Linux / macOS — 加入 ~/.bashrc 或 ~/.zshrc
export PATH="$HOME/.dotnet/tools:$PATH"

# Windows — 该目录通常已自动添加；
# 如果仍然找不到，手动添加:
# %USERPROFILE%\.dotnet\tools
```

安装后**重启终端**或执行 `source ~/.bashrc` 使配置生效。

### 陷阱 2: 本地工具不通过 manifest 找不到

**现象**:
```bash
$ dotnet tool install dotnet-format        # 忘了先创建 manifest
无法安装工具，因为没有可用的工具清单文件。
对于目标运行时，可能没有清单。
```

**原因**: 本地工具依赖 `.config/dotnet-tools.json` manifest 文件。

**解决**: 先创建 manifest，再安装:

```bash
dotnet new tool-manifest
dotnet tool install dotnet-format
```

### 陷阱 3: 本地工具命令找不到

**现象**:
```bash
$ dotnet format --check
# 或
$ dotnet-format --check
bash: dotnet-format: command not found
```

**原因**: 本地工具不会注册为系统命令。即使工具名以 `dotnet-` 开头，也需要通过 `dotnet` CLI 间接调用。

**解决**: 通过 `dotnet` 调用:

```bash
# 正确方式
dotnet format --check

# 等价于
dotnet tool run dotnet-format -- --check
```

> [!note] 注意参数分隔符 `--`
> `dotnet tool run` 后的 `--` 用于分隔 `dotnet` 自身的选项和工具的选项。省略时工具的选项可能被 `dotnet` 误解析。

### 陷阱 4: Manifest 被意外覆盖

**现象**: 在已有 manifest 的目录运行 `dotnet new tool-manifest`，之前安装的工具全部丢失。

**原因**: `dotnet new tool-manifest` 会**覆盖**已有文件。

**解决**: 使用 `dotnet tool install` 添加新工具即可，不需要重新创建 manifest。如果确实需要初始化 manifest，先检查文件是否存在：

```bash
if [ ! -f .config/dotnet-tools.json ]; then
    dotnet new tool-manifest
fi
```

### 陷阱 5: 版本不兼容

**现象**:
```bash
$ dotnet tool install -g dotnet-ef --version 3.1.0
错误: 工具包与当前 .NET SDK 版本不兼容。
```

**原因**: 某些工具版本有最低 .NET SDK 版本要求。例如 `dotnet-ef 8.0.0` 需要 .NET 8 SDK。

**解决**:
- 用 `dotnet --version` 确认当前 SDK 版本
- 安装与 SDK 匹配的工具版本
- 或者升级 .NET SDK

```bash
# 查看工具支持的框架版本 (在包管理器或 nuget.org 上查询)
# 一般规则: dotnet-ef X.0.Y 需要 .NET X SDK
dotnet tool install -g dotnet-ef --version 8.0.0  # 需要 .NET 8

# 如果用的是 .NET 6，用对应的版本:
dotnet tool install -g dotnet-ef --version 6.0.0
```

### 陷阱 6: `isRoot: false` 导致工具不可见

**现象**: 在子目录运行 `dotnet ef` 失败，但在根目录可以。

**原因**: 子目录有自己的 manifest 且 `isRoot: false`，工具定义可能冲突或父级 manifest 未被正确发现。

**解决**:
- 检查子目录 manifest 的 `isRoot` 值
- 如果不需要子目录级工具覆盖，删除子目录的 manifest (只保留根目录的)
- 或者在子目录 manifest 中也声明需要的工具

### 陷阱 7: 全局工具与本地工具版本冲突

**现象**: 同一个工具既全局安装了旧版，又本地安装了新版。使用时不确定调用的哪一个。

**原因**: `dotnet` CLI 在调用 `dotnet-*` 工具时，优先使用本地 manifest 中的版本；如果没有 manifest，则查找全局安装。

**解决**:
- 用 `dotnet tool list -g` 和 `dotnet tool list` 分别确认版本
- 对于项目级工具，统一使用本地 manifest，卸载同名的全局版本
- 在 `.editorconfig` 等配置中锁定格式化器版本策略
