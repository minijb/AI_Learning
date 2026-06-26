---
title: 生成 compile_commands.json
updated: 2026-06-26
tags: [cpp, 编译器, clangd, compile-commands]
---

# 生成 compile_commands.json

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 60min
> 前置知识: [[07-clangd-fundamentals]]

---

## 1. 概念讲解

### 为什么需要这个？

`clangd` 不是一个编译器，它是一个**基于编译器前端的语言服务器**。要正确解析你的 C++ 代码，它需要知道：

- 编译器是谁（`g++`、`clang++`、交叉编译链等）；
- 使用哪个语言标准（`-std=c++17` 还是 `c++20`）；
- 头文件搜索路径（`-I`）和预定义宏（`-D`）；
- 其他影响语法解析的选项（如 `--target`、`-isystem`）。

如果 `clangd` 只能用“我猜”的默认命令去解析，结果往往是满屏红色报错：`iostream` 找不到、宏未定义、`std::optional` 不认识……

`compile_commands.json` 的作用就是**把每个源文件的真实编译命令记录下来**，让 `clangd` 逐文件精确复现编译环境。

### 核心思想

JSON Compilation Database（JSON 编译数据库）是一个名为 `compile_commands.json` 的文件，核心结构是一个 JSON 数组，数组中的每一项描述**一个源文件该怎么编译**。

它的关键字段只有三个：

| 字段 | 含义 |
|------|------|
| `directory` | 执行编译命令时的工作目录，必须是**绝对路径** |
| `file` | 被编译的源文件，必须是**绝对路径** |
| `arguments` / `command` | 编译命令；`arguments` 是字符串数组，`command` 是单个字符串 |

`clangd` 查找这个文件的策略很简单：从你打开的源文件所在目录开始，**逐级向上**遍历父目录，找到第一个 `compile_commands.json` 就停下来使用。因此把它放在项目根目录通常最省事。

> [!tip] `compile_flags.txt` 是什么？
> 对于没有构建系统的小型项目，clangd 也支持 `compile_flags.txt`：每行写一条 flag，作用于该目录下**所有**文件。
> 它的优点是零配置；缺点是所有人共用同一组 flag，无法针对单个文件设置不同的 `-I` 或 `-D`。

---

## 2. 命令示例

### 文件格式详解

下面是一个最小但真实的 `compile_commands.json` 片段：

```json
[
  {
    "directory": "/home/me/proj",
    "file": "/home/me/proj/main.cpp",
    "arguments": [
      "/usr/bin/g++",
      "-std=c++17",
      "-I./include",
      "-DNDEBUG",
      "-c",
      "main.cpp"
    ]
  }
]
```

字段说明：

- `directory`：编译时的工作目录。相对路径（如 `./include`）都按这个目录解析。
- `file`：源文件路径，绝对路径最稳妥。
- `arguments`：推荐写法。数组里的每个元素就是命令行上的一个 token，不用担心引号转义。
- `command`：等价的单个字符串写法，例如 `"g++ -std=c++17 -I./include -DNDEBUG -c main.cpp"`。如果命令里包含空格或引号，需要正确转义，容易出错，因此官方更推荐 `arguments`。

> [!warning] 路径要用绝对路径
> 虽然格式允许相对路径，但 `directory` 和 `file` 写成绝对路径能避免 `clangd` 在不同工作目录下解析不一致。

### 方式一：CMake（最主流）

CMake 是目前生成 `compile_commands.json` 最省心的方式。只要在配置构建目录时打开 `CMAKE_EXPORT_COMPILE_COMMANDS`：

```bash
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build
```

执行后会在 `build/compile_commands.json` 生成文件。

> [!note] 仅 Make / Ninja 生成器支持导出
> 如果你用的是 Visual Studio 生成器（Windows 上默认可能是它），`CMAKE_EXPORT_COMPILE_COMMANDS` **不会生效**。
> 此时可以显式指定 `-G "MinGW Makefiles"` 或 `-G Ninja`。

为了让 `clangd` 在项目根目录就能找到，通常会把 `build/compile_commands.json` 链接到项目根：

- Unix / MSYS2：
  ```bash
  ln -sf build/compile_commands.json .
  ```

- Windows PowerShell（需要管理员权限或开启“开发者模式”）：
  ```powershell
  New-Item -ItemType SymbolicLink -Path compile_commands.json -Target build\compile_commands.json
  ```

- 如果无法创建符号链接，直接复制也能工作（但修改 CMakeLists 后需要重新复制）：
  ```bash
  cp build/compile_commands.json .
  ```

一个最小 CMake 项目示例：

```cmake
cmake_minimum_required(VERSION 3.16)
project(demo)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(demo main.cpp utils.cpp)
```

目录结构：

```text
demo/
├── CMakeLists.txt
├── main.cpp
├── utils.cpp
└── compile_commands.json -> build/compile_commands.json
```

### 方式二：Bear（非 CMake / Make 项目）

Bear 是一款专门“监听”构建过程、把每一条编译命令记录下来生成 `compile_commands.json` 的工具。它特别适合老式的 Makefile、自定义脚本或非 CMake 项目。

安装：

```bash
# Debian / Ubuntu
sudo apt install bear

# macOS
brew install bear

# Arch
sudo pacman -S bear
```

使用方式是在原构建命令前加 `bear --`：

```bash
bear -- make
bear --force-wrapper -- make    # 强制使用 wrapper 模式
```

`bear --force-wrapper` 会强制 Bear 通过编译器 wrapper 拦截命令，适用于某些默认拦截模式无法工作的构建系统。

> [!warning] Windows 原生支持有限
> Bear 主要面向 Unix-like 环境。Windows 上建议在 WSL2 或 MSYS2 中使用。

### 方式三：compile_flags.txt（无构建系统）

如果你只是写一个单文件小程序，没有 CMake 也没有 Makefile，可以手写 `compile_flags.txt`，放在项目根目录：

```text
-std=c++17
-Wall
-Wextra
-I./include
-DNDEBUG
```

`clangd` 会读取该目录下所有 C++ 文件的同一组 flag。

**局限**：

- 同一目录下所有文件共用这些 flag，不能给 `main.cpp` 和 `test.cpp` 分别设置不同的 `-D`。
- 不含 `directory`、`file` 等上下文，复杂项目不够用。

适合场景：刷题、临时测试、没有构建系统的玩具项目。

### 验证 clangd 是否读到

生成文件后，可以用 `clangd --check` 让 `clangd` 单独解析一个文件，并打印它实际使用的编译命令：

```bash
clangd --check=main.cpp --log=verbose
```

在输出中寻找类似下面几行：

```text
I[12:34:56.789] Loaded compilation database from /home/me/proj/compile_commands.json
I[12:34:56.790] ASTWorker building file /home/me/proj/main.cpp version 1 with command
[/home/me/proj]
/usr/bin/g++ -std=c++17 -I./include -DNDEBUG -c main.cpp
```

如果看到 `Loaded compilation database from ...`，说明 `clangd` 已经找到了你的数据库。如果它用了 `with command inferred from ...` 或根本没有加载数据库，说明文件位置或路径有问题。

---

## 3. 扩展阅读

- [clangd 官方：Compile commands](https://clangd.llvm.org/design/compile-commands)
- [CMake 官方文档：CMAKE_EXPORT_COMPILE_COMMANDS](https://cmake.org/cmake/help/latest/variable/CMAKE_EXPORT_COMPILE_COMMANDS.html)
- [Bear GitHub 仓库](https://github.com/rizsotto/Bear)
- [JSON Compilation Database with non-cmake projects](https://rsadowski.de/posts/2025/json-compilation-db-non-cmake-projects/)
- [LLVM JSON Compilation Database 格式规范](https://clang.llvm.org/docs/JSONCompilationDatabase.html)

继续学习：[[09-clangd-editor-integration]]

## 常见陷阱

- **用了 Visual Studio 等不支持的 CMake 生成器**：`CMAKE_EXPORT_COMPILE_COMMANDS=ON` 仅对 Make / Ninja 系列生成器有效。Windows 上如果默认使用 Visual Studio 生成器，不会生成 `compile_commands.json`。→ 显式指定 `-G "MinGW Makefiles"` 或 `-G Ninja`。
- **`directory` / `file` 用相对路径**：相对路径容易让 `clangd` 在不同启动目录下解析出错。→ 全部写成绝对路径。
- **把链接期 flag 写进编译命令**：`compile_commands.json` 里只需要编译期 flag（`-I`、`-D`、`-std`、`-c` 等），`-L`、`-l`、`-o` 等链接期 flag 对 `clangd` 没有帮助，甚至可能干扰解析。→ 保留编译命令，不要混入链接命令。
- **Windows 软链接创建失败**：PowerShell 的 `New-Item -ItemType SymbolicLink` 需要管理员权限或开启开发者模式，否则会报错。→ 可以改用复制，或在设置中开启开发者模式。
- **改了 CMakeLists 后忘了重新 `cmake`**：`compile_commands.json` 是生成文件，CMakeLists 或编译选项改动后必须重新执行 `cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`。→ 把生成命令写进构建脚本或 CI，确保每次配置都刷新。
