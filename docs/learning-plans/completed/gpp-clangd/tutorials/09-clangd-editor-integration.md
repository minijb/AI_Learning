---
title: clangd 编辑器集成与配置
updated: 2026-06-26
tags: [cpp, 编译器, clangd, lsp]
---

# clangd 编辑器集成与配置

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 60min
> 前置知识: [[08-compile-commands]]

---

## 1. 概念讲解

### 为什么需要这个？

`clangd` 本身只是一个命令行语言服务器，它不会直接出现在编辑器里。要让编辑器获得代码补全、跳转定义、实时诊断等功能，必须完成两件事：

1. **安装编辑器插件/扩展**，由它负责启动 `clangd` 进程并按 LSP（Language Server Protocol）与编辑器通信。
2. **正确配置**，让 `clangd` 知道项目怎么编译（上一节的 `compile_commands.json`）以及个人/团队的偏好（`.clangd` / `config.yaml`）。

如果配置错了，最常见症状是：头文件找不到、补全很怪、红色波浪线乱报、或者两个补全引擎互相打架。本节聚焦 VS Code（绝大多数用户的主力编辑器），末尾简述 Neovim 的最小配置。

### 核心思想

编辑器的 LSP 扩展只是「传话筒」，真正的语义分析在 `clangd` 进程里完成。因此配置分两层：

- **编辑器层**：决定用哪个 `clangd` 二进制、启动时带什么命令行参数（`settings.json`）。
- **clangd 层**：决定针对具体项目如何调整解析行为（项目根 `.clangd`）或个人全局偏好（`config.yaml`）。

两层互不替代：编辑器层管「启动」，clangd 层管「解析」。

---

## 2. 命令示例

### 2.1 安装 VS Code 扩展并禁用冲突插件

在 VS Code 中打开扩展面板，搜索并安装：

```text
llvm-vs-code-extensions.vscode-clangd
```

也可在命令行安装（需把 `code` 加入 PATH）：

```bash
code --install-extension llvm-vs-code-extensions.vscode-clangd
```

> [!warning] 必须禁用 Microsoft C/C++ 扩展的 IntelliSense
> Microsoft 官方扩展 `ms-vscode.cpptools` 也会提供 C++ 智能提示。两个扩展同时工作时会抢同一个文件的补全、诊断和跳转结果，导致行为混乱。安装 clangd 扩展后，请在 `settings.json` 里把 Microsoft 引擎关掉。

在 VS Code 中按 `Ctrl+Shift+P`（macOS `Cmd+Shift+P`），输入 `Preferences: Open User Settings (JSON)`，写入：

````json
{
  "C_Cpp.intelliSenseEngine": "disabled",
  "clangd.path": "clangd",
  "clangd.arguments": [
    "--background-index",
    "--clang-tidy",
    "--header-insertion=iwyu",
    "--all-scopes-completion",
    "--completion-style=detailed",
    "-j=8",
    "--pch-storage=memory"
  ],
  "clangd.fallbackFlags": ["-std=c++17"]
}
````

逐项说明这些参数：

| 参数 | 作用 |
|------|------|
| `--background-index` | 在后台索引整个项目符号，补全/跳转/查找引用更快更完整。 |
| `--clang-tidy` | 启用 `clang-tidy` 静态检查，在编辑器里显示额外诊断与修复建议。 |
| `--header-insertion=iwyu` | 自动 `#include` 时使用 Include What You Use 风格（如 `<vector>` 而不是 `"vector"`）。 |
| `--all-scopes-completion` | 补全时不只考虑当前作用域，也展示全局/命名空间中的符号。 |
| `--completion-style=detailed` | 补全项显示更详细的签名与返回类型信息。 |
| `-j=8` | 后台索引使用 8 个线程，根据 CPU 核心数调整。 |
| `--pch-storage=memory` | 把预编译头缓存放在内存里，速度快但占用更多 RAM；硬盘紧张可改用 `disk`。 |
| `clangd.fallbackFlags` | 当找不到 `compile_commands.json` 时的兜底 flag，例如 `-std=c++17`。 |

### 2.2 项目级配置：`.clangd`

在项目根目录创建 `.clangd` 文件，clangd 会自动读取。下面是一份常用模板：

```yaml
CompileFlags:
  Add: [-std=c++17, -Wall, -I./include]
  Remove: [-W*]
  Compiler: g++

Diagnostics:
  Suppress: [bugprone-narrowing-conversions]

Index:
  Background: Build
  StandardLibrary: true
```

逐块解释：

- `CompileFlags.Add`：给所有文件追加编译 flag。适合没有 `compile_commands.json` 的小项目做兜底，也常用来补一些构建系统没传进去的宏或路径。
- `CompileFlags.Remove`：从现有 flag 里移除匹配项。例如构建系统传了 `-Werror`，但你想在编辑器里只把它当警告，就可以 `Remove: [-Werror]`。
- `CompileFlags.Compiler`：修改 `argv[0]`。clangd 有时会根据「看起来像 gcc 还是 clang」推断 target 和标准库路径，设为 `g++` 可让它更接近 g++ 的行为。
- `Diagnostics.Suppress`：关闭特定诊断 ID。注意这里填的是 clangd 的诊断名，不是 g++ 的 `-Wxxx`。
- `Index`：控制后台索引。`Background: Build` 表示构建索引；`StandardLibrary: true` 也索引标准库符号，悬停和补全更完整。

YAML 单值与数组等价，下面两种写法效果一样：

```yaml
CompileFlags:
  Add: -std=c++17
```

```yaml
CompileFlags:
  Add: [-std=c++17]
```

如果只想对某些文件生效，加上 `If` 条件。例如只让头文件按 C++ 解析：

```yaml
If:
  PathMatch: .*\.h

CompileFlags:
  Add: [-xc++]
```

`.clangd` 改动后通常即时生效；若没生效，用命令面板执行 `clangd: Restart language server`。

### 2.3 用户全局配置：`config.yaml`

`.clangd` 是项目级文件，适合提交到版本库；`config.yaml` 是个人全局配置，不会被提交。

各平台位置：

| 平台 | 路径 |
|------|------|
| Windows | `%LocalAppData%\clangd\config.yaml`（即 `C:\Users\<用户名>\AppData\Local\clangd\config.yaml`） |
| macOS | `~/Library/Preferences/clangd/config.yaml` |
| Linux | `$XDG_CONFIG_HOME/clangd/config.yaml`，默认 `~/.config/clangd/config.yaml` |

适合放这里的内容是个人偏好，例如统一关闭某条 clang-tidy 检查：

```yaml
Diagnostics:
  Suppress: [modernize-use-trailing-return-type]
```

### 2.4 clang-tidy 集成

前面 `clangd.arguments` 已经开了 `--clang-tidy`。接下来在项目根目录创建 `.clang-tidy`：

```yaml
Checks: '*,-bugprone-*'
```

这行表示：启用所有检查，但排除 `bugprone-*` 这一类。实际项目建议更精细，例如：

```yaml
Checks: 'clang-analyzer-*,cppcoreguidelines-*,modernize-*,performance-*,portability-*,readability-*'
```

修改 `.clang-tidy` 后同样重启 clangd 即可生效。编辑器里会用红色/黄色波浪线标出问题，并在灯泡菜单里给出自动修复建议。

### 2.5 功能一览

装好后，下面这些操作都可以直接触发：

| 功能 | 触发方式 | 说明 |
|------|----------|------|
| 代码补全 | 输入或按 `.` / `->` / `::` | 基于 clangd 语义分析，不是简单文本匹配。 |
| 跳转定义 | `F12` | 跳到符号定义处；若有多处可用 `Ctrl+K Ctrl+F12` 查看所有实现。 |
| 悬停信息 | 鼠标 hover | 显示类型、签名、文档注释。 |
| 查找引用 | `Shift+F12` | 列出项目内所有引用。依赖后台索引完整。 |
| 重命名符号 | `F2` | 跨文件安全重命名变量/函数/类。 |
| Inlay hints | 由 `editor.inlayHints.enabled` 控制 | 显示参数名、类型推导结果；非 clangd 独占，由 VS Code 统一渲染。 |
| clang-tidy 诊断 | 红/黄色波浪线 + 灯泡 | 静态检查问题，部分可一键修复。 |

### 2.6 Neovim 最小配置

如果你用 Neovim，可通过 `nvim-lspconfig` 接入 clangd：

```lua
require('lspconfig').clangd.setup({
  cmd = {
    'clangd',
    '--background-index',
    '--clang-tidy',
    '--header-insertion=iwyu',
    '--completion-style=detailed',
  },
})
```

Neovim 没有「扩展冲突」问题，因为它直接把 LSP 客户端交给语言服务器。其余功能（跳转、查找引用、重命名）通过内置 LSP 命令触发，例如 `gd`、`gr`、`rn`。

---

## 3. 扩展阅读

- [clangd 官方配置文档](https://clangd.llvm.org/config)
- [VS Code clangd 扩展市场页](https://marketplace.visualstudio.com/items?itemName=llvm-vs-code-extensions.vscode-clangd)
- [clang-tidy 检查列表与文档](https://clang.llvm.org/extra/clang-tidy/)
- 计划完结，回顾总览：[[plan]] 与 [[progress]]

---

## 常见陷阱

- **没禁用 `ms-vscode.cpptools` 的 IntelliSense**：两个引擎同时工作，补全/诊断会错乱。正确做法是设置 `"C_Cpp.intelliSenseEngine": "disabled"`。
- **改了 `.clangd` 或 `compile_commands.json` 后没重启 clangd**：clangd 会尽量热重载，但大型变更后还是建议在命令面板执行 `clangd: Restart language server`。
- **头文件不在 `compile_commands.json` 里**：clangd 对未录入的 `.h`/`.hpp` 可能不给出诊断。可以让构建系统生成头文件条目，或在 `.clangd` 里用 `If` 条件为头文件补 flag。
- **`clangd.path` 指向错误二进制**：如果 PATH 里有多个 clangd（例如 LLVM 安装包和 VS Code 自带），确认 `clangd --version` 输出的版本是你期望的。
- **缓存陈旧**：索引缓存位于 `~/.cache/clangd`（Linux/macOS）或 `%LocalAppData%\clangd`（Windows）。出现莫名其妙的跳转/诊断时，可以关闭 VS Code 后清空该目录，再重新打开项目。
