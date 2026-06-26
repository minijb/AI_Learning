---
title: 环境搭建
updated: 2026-06-26
tags: [cpp, 编译器, 工具链, clangd]
---

# 环境搭建

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 45min
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要这个？

写 C++ 程序时，你写的 `.cpp` 文件只是人类能读懂的文本。要让机器运行它，需要有人把它翻译成操作系统能加载的可执行文件——这个角色就是**编译器**。`g++` 是 GCC（GNU Compiler Collection）的 C++ 前端，它负责读取 C++ 源码，检查语法、生成目标文件、链接库，最终产出可执行程序。

光能编译还不够。在编辑器里写代码时，你希望：

- 输入 `.` 或 `->` 时自动弹出成员列表；
- 函数名写错时立即出现红色下划线；
- 按住 `Ctrl` 点击函数名就能跳转到定义。

这些能力不是编译器提供的，而是**语言服务器**通过 LSP（Language Server Protocol）协议向编辑器提供的。`clangd` 就是 C/C++ 领域最常用的语言服务器之一，它基于 LLVM/clang 的前端分析能力，提供补全、跳转、诊断、重构等功能。

> [!important] 角色区分
> `g++` 产出可执行文件；`clangd` 不产可执行文件，只给编辑器提供代码理解服务。两者经常一起工作，但职责完全不同。

### 核心思想

命令行工具链是现代 C++ 开发的地基。无论是 Visual Studio、VS Code、CLion 还是 Qt Creator，IDE 的“一键编译”“智能提示”背后，都是在调用 `g++`、`clangd`、`gdb` 这类命令行工具。直接掌握命令行，你才能：

- 看懂构建脚本和 CI 配置；
- 在编辑器出问题时知道从哪里排查；
- 在不同平台、不同 IDE 之间迁移项目时不被锁定。

本节先把 `g++` 和 `clangd` 安装到你的系统里，并跑通第一个程序，为后续每一节打下基础。

---

## 2. 命令示例

### 安装 g++

#### Windows（推荐：MSYS2 UCRT64）

Windows 本身不带 `g++`，最干净的方式是通过 MSYS2 安装 MinGW-w64 工具链。

1. 访问 [MSYS2 官网](https://www.msys2.org/) 下载安装器并安装到默认位置（例如 `C:\msys64`）。
2. 打开 **MSYS2 UCRT64** 终端（开始菜单里会有多个 MSYS2 图标，选带 `UCRT64` 的那个）。
3. 更新包数据库和核心包：

```bash
pacman -Syu
```

> [!warning] 可能提示关闭终端
> 更新核心包时，MSYS2 可能会提示你需要先关闭终端再完成更新。按提示关闭窗口，然后重新打开 **UCRT64** 终端，继续运行：
>
> ```bash
> pacman -Su
> ```

4. 安装 GCC 工具链（这会同时安装 `g++`、`gcc`、`gdb` 等）：

```bash
pacman -S mingw-w64-ucrt-x86_64-gcc
```

5. 把 `g++` 所在目录加入系统 `PATH`，这样 PowerShell 和 VS Code 才能直接找到它：

```text
C:\msys64\ucrt64\bin
```

添加方式：在 Windows 搜索栏输入“编辑系统环境变量” → 打开后点击“环境变量” → 在下方“系统变量”里找到 `Path` → 编辑 → 新建 → 粘贴 `C:\msys64\ucrt64\bin` → 一路确定。

> [!tip] 子系统选择
> MSYS2 提供多个子系统环境，日常 C++ 编译用 **UCRT64**。简单对比：
>
> | 环境 | 定位 | 是否推荐 |
> |------|------|:--------:|
> | UCRT64 | 现代 Windows 运行时（UCRT），兼容性最好 | ✅ 推荐 |
> | MINGW64 | 传统 MinGW 运行时 | 可用 |
> | MSYS | 类 Unix 兼容层，主要服务 MSYS2 自身 | 不推荐用来编译普通 C++ 程序 |

#### macOS

macOS 自带的 `g++` 命令实际上是 Apple clang 的别名，对初学者足够，但如果你想用真正的 GNU g++：

```bash
# 安装 Apple 命令行工具（得到 clang，以及一个指向 clang 的 g++ 命令）
xcode-select --install

# 或者用 Homebrew 安装真正的 GNU g++
brew install gcc
```

安装 Homebrew 版本后，真正的 GNU 命令通常是 `g++-14`（版本号随时间变化）。

#### Linux

根据发行版选择对应的包管理器：

```bash
# Debian / Ubuntu
sudo apt install g++ build-essential

# Fedora
sudo dnf install gcc-c++

# Arch Linux
sudo pacman -S gcc
```

### 验证安装

**关闭旧的终端窗口，重新打开一个新的终端**，让 `PATH` 生效，然后运行：

```bash
g++ --version
```

在 Windows 的 PowerShell 里，还可以查看可执行文件位置：

```powershell
Get-Command g++
# 或者
where.exe g++
```

在 macOS 或 Linux 上：

```bash
which g++
```

预期输出示例：

```text
g++ (Rev10, Built by MSYS2 project) 14.2.0
Copyright (C) 2024 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
```

### 第一个程序

新建文件 `hello.cpp`，输入以下内容：

```cpp
#include <iostream>

int main() {
    std::cout << "Hello, World!" << std::endl;
    return 0;
}
```

在终端中切换到该文件所在目录，编译：

```bash
g++ hello.cpp -o hello
```

- `-o hello` 表示把输出文件命名为 `hello`。
- 如果不写 `-o`，Windows 会生成 `a.exe`，Linux/macOS 会生成 `a.out`。

运行：

```bash
# macOS / Linux
./hello

# Windows（PowerShell / CMD）
hello.exe
# 或者省略扩展名
hello
```

预期输出：

```text
Hello, World!
```

### 安装 clangd

`clangd` 的详细配置会在 [[07-clangd-fundamentals]] 中展开，这里只列出安装命令并验证。

#### Windows

如果你已经用 MSYS2 安装了 GCC，可以继续用 MSYS2 安装 clangd：

```bash
pacman -S mingw-w64-ucrt-x86_64-clang-tools-extra
```

也可以直接下载 [LLVM 官方 Windows 安装包](https://github.com/llvm/llvm-project/releases) 并安装。

验证：

```bash
clangd --version
```

#### macOS

```bash
brew install llvm
```

#### Linux

```bash
# Debian / Ubuntu
sudo apt install clangd

# Fedora
sudo dnf install clang-tools-extra
```

验证：

```bash
clangd --version
```

---

## 3. 扩展阅读

- [MSYS2 官网与安装指南](https://www.msys2.org/)
- [VS Code 官方 MinGW 配置教程](https://code.visualstudio.com/docs/cpp/config-mingw)
- [clangd 官方文档](https://clangd.llvm.org/)
- 继续学习：[[02-gpp-basic-compilation]]

---

## 常见陷阱

- **陷阱：修改 `PATH` 后仍在旧终端里运行 `g++ --version`，提示找不到命令。**
  → 正确做法：环境变量修改只对**新打开**的终端生效。关闭当前窗口，重新打开 PowerShell / 终端再试。

- **陷阱：MSYS2 子系统选错，导致找不到 `mingw-w64-ucrt-x86_64-gcc` 包或安装的编译器路径不在预期位置。**
  → 正确做法：安装和更新时始终使用 **UCRT64** 终端；PATH 里加的是 `C:\msys64\ucrt64\bin`，不是 `C:\msys64\usr\bin` 或 `C:\msys64\mingw64\bin`。

- **陷阱：macOS 上运行 `g++ --version`，发现显示的是 `Apple clang`，却以为自己装的是 GNU g++。**
  → 正确做法：macOS 系统自带的 `g++` 是 clang 别名。需要真 GNU g++ 时，用 `brew install gcc`，然后使用 `g++-14` 这类带版本号的命令。

- **陷阱：Windows 下输入 `g++ hello.cpp -o hello` 后，找不到名为 `hello` 的可执行文件。**
  → 正确做法：Windows 可执行文件扩展名是 `.exe`，生成的文件名是 `hello.exe`。运行时可以写 `hello.exe`，也可以直接写 `hello`（PowerShell/CMD 通常能自动补全扩展名）。

