---
title: CMake 基础与构建系统概览
updated: 2026-06-10
tags: [cmake, build-system, c++, beginner]
---

# CMake 基础与构建系统概览

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 50min
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要构建系统？

假设你有一个 C++ 源文件 `hello.cpp`：

```cpp
#include <iostream>

int main() {
    std::cout << "Hello, World!" << std::endl;
    return 0;
}
```

用 `g++` 编译它只需要一行命令：

```bash
g++ -o hello hello.cpp
```

但是，真实项目从来不是一个文件。当你的项目增长到几十个源文件、需要链接外部库、需要条件编译、需要跨平台支持时，手动敲 `g++` 命令会变成一场灾难：

- 每次编译都需要记忆并拼写所有源文件路径
- 修改了一个头文件，你需要**记住**哪些 `.cpp` 依赖它并重新编译——漏掉一个就可能导致未定义行为
- 不同的编译器（GCC、Clang、MSVC）有不同的命令行参数
- 调试版和发布版需要不同的编译选项
- 项目结构变化时，所有编译脚本都要同步更新

这些痛点催生了**构建系统（Build System）**。

#### 构建系统的演进：从 Make 到 CMake

> [!note] 构建系统简史
> 构建系统的演进可以看作自动化程度的逐级提升。理解每一级解决什么问题，才能理解 CMake 存在的理由。

**Level 0：手动命令**

```bash
g++ -c main.cpp -o main.o
g++ -c helper.cpp -o helper.o
g++ main.o helper.o -o myapp -lm
```

缺点：重复、易错、无依赖追踪。

**Level 1：Shell 脚本**

```bash
#!/bin/bash
g++ -c main.cpp -o main.o
g++ -c helper.cpp -o helper.o
g++ main.o helper.o -o myapp -lm
```

缺点：每次全部重新编译，修改一个文件也重编整个项目。对于大项目，这浪费数十分钟甚至数小时。

**Level 2：Make / Makefile**

```makefile
myapp: main.o helper.o
	g++ main.o helper.o -o myapp -lm

main.o: main.cpp helper.h
	g++ -c main.cpp -o main.o

helper.o: helper.cpp helper.h
	g++ -c helper.cpp -o helper.o
```

Make 引入了**依赖图**：它知道 `main.o` 依赖 `main.cpp` 和 `helper.h`，只有当这些依赖发生变化时才重新编译。增量编译大幅节省时间。但 Make 有严重局限：

- 语法诡异（以 Tab 缩进区分命令，缩进错误报莫名其妙的错）
- 跨平台困难：Windows 上没有原生的 `make`，路径分隔符不同
- 自动依赖生成需要手写 `${CC} -M` 规则
- 不支持现代 IDE 集成

**Level 3：Autotools（autoconf / automake）**

Autotools 在 Make 之上增加了一层配置层，可以检测系统特性（比如某个头文件是否存在、某个库是否可用），然后生成 Makefile。但它极其复杂：一个典型项目需要 `configure.ac`、`Makefile.am`、`aclocal.m4` 等多个文件，调试起来非常痛苦。而且它本质上仍然生成 Make，跨平台支持有限。

**Level 4：CMake（Meta-Build System）**

CMake 不直接构建代码。它读取 `CMakeLists.txt`，**生成**原生构建文件（Makefiles、Ninja 文件、Visual Studio `.sln`、Xcode 工程），然后由这些原生工具执行实际编译。

这就是 CMake 被称为**元构建系统（Meta-Build System）**的原因：它处在比 Make 更高一层的抽象，不关心具体怎么调用编译器和链接器，而是描述"这个项目有哪些源文件，需要什么选项，依赖什么库"，然后让下层工具去执行。

```
CMakeLists.txt  →  CMake (configure + generate)  →  Makefile / Ninja / .sln  →  make / ninja / MSBuild  →  可执行文件
                     └── 元构建系统 ──┘              └── 原生构建文件 ──┘        └── 原生构建工具 ──┘
```

### CMake 的核心角色

CMake 的核心职责只有一件事：**描述目标（target）和它们之间的关系**，然后生成对应平台下的原生构建文件。

其他的构建系统往往试图包办一切——Meson 有内置的编译驱动、Bazel 有内置的沙箱执行引擎。CMake 则刻意保持"只生成构建文件"的定位。这个取舍带来了几个关键优势：

1. **与你已有的工具栈无缝集成**：你仍然用熟悉的 `make`、`ninja`、Visual Studio 进行编译和调试
2. **IDE 支持极其广泛**：CLion、Visual Studio、VS Code、Qt Creator 都原生理解 CMake 项目
3. **渐进式采用**：可以在已有 Make 项目旁加一个 `CMakeLists.txt`，不需要一次性迁移

> [!tip] CMake 的设计哲学
> CMake 遵循"描述目标，不描述命令"的范式。早期 CMake（≤2.x 时代）用大量命令式 API（如 `include_directories`、`link_libraries`），导致全局污染和难以维护。Modern CMake（3.0+）推崇以 target 为核心的声明式风格——你描述每个 target 需要什么，CMake 负责推导全局构建顺序。

### CMake 的三个阶段

CMake 的执行分为三个严格区分、顺序执行的阶段。理解这个划分是深入掌握 CMake 的第一道门槛。

```
┌────────────────────────┐
│  1. Configure（配置）   │  读取 CMakeLists.txt，执行 CMake 脚本，
│                       │  解析变量、条件分支、宏/函数展开，
│                       │  收集 target、source、properties
└────────┬───────────────┘
         │ 内存中的构建模型
         ▼
┌────────────────────────┐
│  2. Generate（生成）    │  将内存中的构建模型写入原生构建文件：
│                       │  Makefile、build.ninja、.vcxproj 等
│                       │  此阶段结束 → CMake 本身的工作完成
└────────┬───────────────┘
         │ 原生构建文件
         ▼
┌────────────────────────┐
│  3. Build（构建）       │  调用原生构建工具（make / ninja / MSBuild）
│                       │  执行编译、链接——此时 CMake 不再参与
└────────────────────────┘
```

#### 阶段 1：Configure（配置）

这是最关键的阶段。CMake 读取顶层 `CMakeLists.txt`（可能通过 `add_subdirectory` 递归读取子目录），从头到尾执行 CMake 脚本语言：

- 执行 `project()` 命令以检测编译器和平台
- 执行 `find_package()` 查找依赖
- 执行 `add_executable()`、`add_library()` 等 target 定义命令
- 执行变量赋值、条件分支、循环、函数/宏调用
- 将结果写入 `CMakeCache.txt`（缓存持久化）

Configure 完成后，CMake 在内存中持有完整的项目模型——所有 target、它们的属性、依赖关系和编译选项。

> [!warning] Configure 阶段只执行"脚本逻辑"
> 编译器**不会被调用**。生成器表达式（`$<...>`）也**不会被求值**——它们被写入构建文件，等到 Build 阶段才被原生构建工具求值。这是理解生成器表达式的关键：[[08-generator-expressions]]。

#### 阶段 2：Generate（生成）

CMake 将内存中的项目模型"翻译"为特定生成器格式的构建文件：

- Unix Makefiles → 生成 `Makefile`
- Ninja → 生成 `build.ninja`
- Visual Studio → 生成 `.sln` + `.vcxproj`
- Xcode → 生成 `.xcodeproj`

生成器表达式（`$<...>`）在此阶段被求值。也就是说，`$<CONFIG:Debug>` 会根据用户在 Generate 阶段选择的配置输出不同内容。

#### 阶段 3：Build（构建）

原生构建工具接手。CMake 不再参与——`cmake --build` 只是 `make`/`ninja`/`MSBuild` 的前端包装。

这意味着：
- 编译错误由编译器报告，不是 CMake 报告
- 并行编译由原生工具控制（`make -j` 或 `ninja` 自动并行）
- 增量编译由原生工具管理（检查文件时间戳）

#### 为什么必须区分这三个阶段？

早期的构建系统（如 Make）把"配置"和"构建"混在一起——`./configure` 生成 Makefile，然后 `make` 编译。但 `.configure` 生成的 Makefile 是不可移植的，因为配置阶段的检测结果（如找到哪个版本的 Qt）直接硬编码在了 Makefile 里。

CMake 将配置结果存储在 `CMakeCache.txt`（文本文件）中。如果你改了缓存中的选项，CMake 检测到缓存变化会自动重新 Configure + Generate，而不需要手动重新运行。这让增量配置成为可能。

### 安装 CMake

#### 方法一：包管理器（推荐）

```bash
# macOS - Homebrew
brew install cmake

# Ubuntu / Debian
sudo apt install cmake

# Fedora
sudo dnf install cmake

# Windows - winget
winget install Kitware.CMake

# Windows - Chocolatey
choco install cmake
```

#### 方法二：官方二进制

从 [cmake.org/download](https://cmake.org/download) 下载对应平台的安装包。Windows 用户应勾选 "Add CMake to system PATH"。

#### 方法三：pip（跨平台，版本最新）

```bash
pip install cmake
```

安装后验证：

```bash
cmake --version
```

预期输出（版本号可能不同）：

```text
cmake version 3.24.0

CMake suite maintained and supported by Kitware (kitware.com/cmake).
```

> [!important] 版本要求
> 本系列教程**要求 CMake 3.24+**。`cmake_minimum_required(VERSION 3.24)` 确保你的项目在旧版本 CMake 上运行时会给出清晰的报错，而不是产生难以排查的行为差异。

### 你的第一个 CMake 项目

最小 CMake 项目只需要一个 `CMakeLists.txt` 文件。假设项目结构如下：

```
myproject/
├── CMakeLists.txt
└── main.cpp
```

`main.cpp`：

```cpp
#include <iostream>

int main() {
    std::cout << "Hello from CMake!" << std::endl;
    return 0;
}
```

`CMakeLists.txt`：

```cmake
cmake_minimum_required(VERSION 3.24)
project(MyProject VERSION 1.0.0 LANGUAGES CXX)

add_executable(myapp main.cpp)
```

#### 逐行解释

| 行 | 含义 |
|----|------|
| `cmake_minimum_required(VERSION 3.24)` | 声明本项目的 CMake 最低版本。如果用户 CMake 版本低于 3.24，configure 阶段立即报错退出，会明确告知需要的版本。同时启用该版本的策略（Policy）设置。 |
| `project(MyProject VERSION 1.0.0 LANGUAGES CXX)` | 声明项目名称、版本和语言。`LANGUAGES CXX` 表示只启用 C++ 编译器（不启用 C 编译器）。`project()` 会创建大量隐式变量如 `${PROJECT_NAME}`、`${PROJECT_VERSION}`、`${CMAKE_CXX_COMPILER}` 等。 |
| `add_executable(myapp main.cpp)` | 定义一个可执行 target，名为 `myapp`，从 `main.cpp` 编译生成。 |

#### 构建命令

```bash
# 在项目根目录执行
cmake -B build -S .

# 然后编译
cmake --build build
```

- `-B build`：指定构建目录为 `build/`
- `-S .`：指定源码目录为当前目录（`.`）
- `--build build`：调用原生构建工具编译 `build/` 中的项目

> [!important] 始终使用 out-of-source 构建
> `-B build` 创建**独立的**构建目录。不要把 `-S` 和 `-B` 设为同一个目录——那叫 in-source build，会产生大量中间文件污染源码树，难以清理，也可能触发意外的重新配置。Out-of-source build 是 CMake 的最佳实践。

### 生成器（Generators）

生成器决定了 CMake 生成什么格式的原生构建文件。

#### 列出可用生成器

```bash
cmake --help
```

输出的结尾部分会列出当前平台支持的生成器：

```text
Generators

The following generators are available on this platform (* marks default):
* Visual Studio 17 2022        = Generates Visual Studio 2022 project files.
                                 Use -A option to specify architecture.
  Ninja                        = Generates build.ninja files.
  Unix Makefiles               = Generates standard UNIX makefiles.
  MinGW Makefiles              = Generates a makefile for use with mingw32-make.
  ...
```

也可以用编程方式获取：

```bash
cmake -G   # 不带参数，列出所有生成器
```

#### 生成器分类：单配置 vs 多配置

这是 CMake 最重要的概念之一。

**单配置生成器（Single-Config Generators）**：

- Unix Makefiles
- Ninja
- MinGW Makefiles

每次生成只支持**一种**构建配置（如 Debug 或 Release）。构建类型在 Configure 阶段通过 `CMAKE_BUILD_TYPE` 变量指定：

```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug
cmake --build build
```

**多配置生成器（Multi-Config Generators）**：

- Visual Studio 17 2022
- Xcode
- Ninja Multi-Config

一次生成支持**多种**配置。构建类型在 Build 阶段指定：

```bash
cmake -B build -S . -G "Visual Studio 17 2022"
cmake --build build --config Debug   # 或 Release
```

> [!tip] 选择哪个生成器？
> - **Ninja** 是最快的单配置生成器，适合 Linux/macOS 日常开发和 CI
> - **Visual Studio** 生成器适合需要 VS IDE 调试和编辑的 Windows 开发者
> - **Unix Makefiles** 是默认回退选项——如果系统上没有 Ninja，CMake 会选它
> - 在 Windows 上常用 `cmake -G "Visual Studio 17 2022" -A x64` 指定目标架构

#### 指定生成器

```bash
cmake -B build -S . -G Ninja
```

如果指定的生成器不可用，CMake 会在 Configure 阶段报错。

### 构建目录（Build Directory）

CMake 的构建目录包含：

```
build/
├── CMakeCache.txt          # 缓存变量（持久化 configure 结果）
├── CMakeFiles/             # CMake 内部文件（依赖追踪、编译器检测结果）
├── cmake_install.cmake     # install 规则
├── Makefile                # 或 build.ninja 等（原生构建文件）
├── myapp                   # 最终可执行文件（可能在此或子目录中）
└── ...中间文件...
```

> [!note] 构建目录的唯一性
> 每个构建目录与一个**生成器**绑定，并且与一个**配置**（单配置时）绑定。如果你用 Ninja 生成了 Debug 配置，然后想改用 Makefiles 或 Release 配置，应该创建**新的**构建目录：
> ```bash
> cmake -B build-debug-ninja -S . -GNinja -DCMAKE_BUILD_TYPE=Debug
> cmake -B build-release-ninja -S . -GNinja -DCMAKE_BUILD_TYPE=Release
> ```
> 不要把不同生成器的产物混在同一个构建目录中。

### CMake 与其他构建系统的对比

| 系统 | 类型 | 特点 | 何时选择 |
|------|------|------|----------|
| **Make** | 原生构建系统 | 直接驱动编译；语法原始；跨平台困难 | 极简单的 Unix-only 项目 |
| **Autotools** | 配置 + Make | GNU 项目经典选择；极度复杂 | 需要 GNU 风格的 `./configure && make && make install` |
| **CMake** | 元构建系统 | 生成原生构建文件；生态系统最大；IDE 支持最广 | **一般首选**，特别是跨平台 C/C++ 项目 |
| **Meson** | 元构建系统 | 用 Python-like 语法代替 CMake 语言；与 Ninja 深度绑定；速度更快 | 新项目，偏好更简洁的构建描述语言 |
| **Bazel** | 构建系统 | Google 开发；声明式 BUILD 文件；内置沙箱和缓存；单体仓库友好 | 大型单体仓库（monorepo），需要可复现、增量、分布式构建 |
| **xmake** | 元构建系统 | Lua 语法；中国开发者社区活跃 | 轻量级 C/C++ 项目，偏好 Lua |
| **SCons** | 构建系统 | Python 脚本驱动构建；不再活跃 | 遗留项目维护 |

> [!tip] CMake 在本课程中的位置
> CMake 不是万能的——它不擅长包管理（虽然 `FetchContent` 和 `find_package` 在努力）。在真实项目中，你通常会结合 CMake（构建系统） + Conan/vcpkg（包管理） + CTest（测试） + CPack（打包）形成完整的构建工具链。本课程的后续章节将逐一覆盖这些主题。

---

## 2. 代码示例

### 示例 1：最小单文件可执行项目

**项目结构：**

```
example1/
├── CMakeLists.txt
└── main.cpp
```

**`main.cpp`：**

```cpp
#include <iostream>

int main() {
    std::cout << "Hello from CMake!" << std::endl;
    return 0;
}
```

**`CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(HelloWorld VERSION 1.0.0 LANGUAGES CXX)

add_executable(hello main.cpp)
```

**运行方式：**

```bash
mkdir example1 && cd example1
# 创建上述两个文件（见上方内容）

# 配置并生成
cmake -B build -S .

# 查看生成的文件
ls build/

# 构建
cmake --build build

# 运行
./build/hello          # Linux/macOS
build\Debug\hello.exe  # Windows (Visual Studio generator)
```

**预期输出：**

```text
-- The CXX compiler identification is GNU xxx
-- Configuring done
-- Generating done
-- Build files have been written to: .../example1/build
[ 50%] Building CXX object CMakeFiles/hello.dir/main.cpp.o
[100%] Linking CXX executable hello
[100%] Built target hello

Hello from CMake!
```

### 示例 2：双文件项目（main.cpp + helper.cpp）

**项目结构：**

```
example2/
├── CMakeLists.txt
├── main.cpp
├── helper.cpp
└── helper.h
```

**`helper.h`：**

```cpp
#pragma once

int add(int a, int b);
```

**`helper.cpp`：**

```cpp
#include "helper.h"

int add(int a, int b) {
    return a + b;
}
```

**`main.cpp`：**

```cpp
#include <iostream>
#include "helper.h"

int main() {
    int result = add(3, 4);
    std::cout << "3 + 4 = " << result << std::endl;
    return 0;
}
```

**`CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(MultiFile VERSION 1.0.0 LANGUAGES CXX)

add_executable(myapp
    main.cpp
    helper.cpp
)
```

> [!tip] 为什么不需要列出头文件？
> CMake 的 `add_executable` 只需要 `.cpp`/`.c` 文件。头文件通过 `#include` 被编译器自动发现（前提是它们位于 include 路径中）。但为了 IDE 集成（VS Code、CLion 等），你也可以在 target 的源文件列表中加入头文件——它们不会被编译，但会出现在 IDE 的文件树中。

**运行方式：**

```bash
mkdir example2 && cd example2
# 创建上述五个文件

cmake -B build -S .
cmake --build build
./build/myapp
```

**预期输出：**

```text
3 + 4 = 7
```

> [!note] 增量编译验证
> 只修改 `helper.cpp` 后重新 `cmake --build build`，观察只有 `helper.cpp` 被重新编译，`main.cpp` 不会被重新编译。这正是构建系统依赖追踪的价值。

### 示例 3：列出和切换生成器

这个示例帮助你熟悉生成器的查看、选择和切换。

**准备工作：** 延续示例 1 或示例 2 的项目结构（任何有 `CMakeLists.txt` 的项目均可）。

**运行方式：**

```bash
# 步骤 1：查看 CMake 版本和基本信息
cmake --version

# 步骤 2：查看帮助，定位生成器列表（位于输出的末尾部分）
cmake --help

# 步骤 3：尝试用不同生成器构建同一个项目
# 使用 Ninja（如果已安装）
cmake -B build-ninja -S . -G Ninja
cmake --build build-ninja

# 使用默认生成器
cmake -B build-default -S .
cmake --build build-default

# 在 Windows 上使用 VS 生成器（如果安装了 Visual Studio）
cmake -B build-vs -S . -G "Visual Studio 17 2022" -A x64
cmake --build build-vs --config Release

# 步骤 4：观察不同生成器的产物
ls build-ninja/     # 有 build.ninja
ls build-default/   # 有 Makefile（或 build.ninja，取决于默认值）
# build-vs/ 中有 .sln 文件（Windows）
```

**预期输出：** 三种构建方式都能成功编译出可执行文件。注意观察不同构建目录中生成的文件类型完全不同——这正是元构建系统的核心价值：同一份 `CMakeLists.txt`，不同的输出格式。

> [!tip] 生成器缓存警告
> 如果尝试在已有构建目录上切换生成器，CMake 会报错。解决方法：删除旧构建目录（`rm -rf build`），或创建新的构建目录。

---

## 3. 练习

### 练习 1：创建打印 Hello World 的 CMake 项目（基础）

1. 创建一个新目录 `practice1/`
2. 编写 `main.cpp`，输出 `"Hello, CMake!"`
3. 编写 `CMakeLists.txt`，使用标准的 `cmake_minimum_required` + `project` + `add_executable`
4. 用 `cmake -B build -S .` 配置，用 `cmake --build build` 构建
5. 运行生成的可执行文件，验证输出
6. 修改 `main.cpp` 的内容，重新 `cmake --build build`，观察增量编译的日志

**思考：** 为什么步骤 6 不需要重新运行 `cmake -B build -S .`？

### 练习 2：用两种不同生成器构建同一个项目（进阶）

1. 延续练习 1 的项目（或创建一个新的多文件项目）
2. 使用 `cmake --help` 找出系统上可用的所有生成器
3. 用一个单配置生成器（如 Ninja 或 Unix Makefiles）构建到 `build-single/`
4. 用另一个不同的生成器构建到 `build-other/`
5. 对比两个构建目录的内容，找出至少 3 种文件类型的差异
6. 分别在两个目录中运行 `cmake --build <dir>`，验证都能成功编译

**思考：** 如果系统上有 Visual Studio，用 VS 生成器产生的 `build-vs/` 目录能否通过 `cmake --build build-vs` 来构建？如果能，用 `--config` 参数试试 `Debug` 和 `Release` 的区别。

### 练习 3：探索 cmake --help 并找出生成器清单（挑战）

1. 运行 `cmake --help > cmake-help.txt` 将完整帮助输出保存到文件
2. 定位 "Generators" 章节
3. 列出你系统上标记为 `*` 的默认生成器
4. 列出不支持的单配置生成器（如果有）——比如在 Windows 上 "Unix Makefiles" 可能不可用
5. 用 `cmake --help-command add_executable` 查看 `add_executable` 命令的文档
6. 用 `cmake --help-variable CMAKE_BUILD_TYPE` 查看该变量的文档

**思考：** CMake 提供了 `--help-command`、`--help-variable`、`--help-property`、`--help-module`、`--help-policy` 等多种帮助入口。为什么没有一个统一的 `man cmake` 或 `cmake help <topic>` 接口？这是 CMake 的历史遗留问题——这些帮助命令各自负责不同的命名空间，没有统一的查询前端。在实际工作中，更高效的方式是直接查阅 [CMake 官方文档](https://cmake.org/cmake/help/latest/)。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(HelloCMake VERSION 1.0 LANGUAGES CXX)
>
> add_executable(hello main.cpp)
> ```
>
> ```cpp
> #include <iostream>
>
> int main() {
>     std::cout << "Hello, CMake!" << std::endl;
>     return 0;
> }
> ```
>
> **构建步骤：**
>
> ```bash
> cmake -B build -S .
> cmake --build build
> ./build/hello
> ```
>
> **思考题答案：** 步骤 6 不需要重新运行 `cmake -B build -S .`，因为 `cmake --build build` 会检测 `CMakeLists.txt` 和源文件的时间戳变化。如果只有 `main.cpp` 被修改（而非 CMake 配置文件），CMake 不会自动重新 configure+generate——原生构建系统（make/ninja）直接负责增量编译。这就是 CMake 三阶段架构的优势：修改源码只触发构建阶段，无需重新配置。

> [!tip]- 练习 2 参考答案
> **系统上可用生成器（Linux 示例）：**
> ```bash
> cmake --help
> ```
>
> **两个独立构建目录：**
> ```bash
> # Ninja 生成器
> cmake -B build-single -G Ninja
> cmake --build build-single
>
> # Unix Makefiles 生成器
> cmake -B build-other -G "Unix Makefiles"
> cmake --build build-other
> ```
>
> **三个关键文件类型差异：**
>
> | 文件类型 | Ninja (`build-single/`) | Unix Makefiles (`build-other/`) |
> |----------|------------------------|--------------------------------|
> | 构建描述文件 | `build.ninja` | `Makefile` + `CMakeFiles/` |
> | 依赖追踪 | `.ninja_deps`, `.ninja_log` | `CMakeFiles/<target>.dir/depend.make` |
> | 编译规则 | 内嵌在 `build.ninja` | `CMakeFiles/<target>.dir/build.make` |
>
> **思考题答案：** 是的，VS 生成器产生的 `build-vs/` 可以通过 `cmake --build build-vs` 构建，因为 `cmake --build` 会自动检测生成器类型并调用对应的原生工具（此处为 `MSBuild`）。`--config` 参数选择构建配置：
> ```bash
> cmake --build build-vs --config Debug
> cmake --build build-vs --config Release
> ```

> [!tip]- 练习 3 参考答案
> **关键步骤与发现：**
>
> ```bash
> # 1. 保存完整帮助
> cmake --help > cmake-help.txt
>
> # 2. 定位 Generators 章节（通常在文件末尾）
> # 在 cmake-help.txt 中搜索 "Generators"
>
> # 3. 默认生成器（标 * 的）
> # Linux: * Unix Makefiles
> # macOS: * Unix Makefiles（无 Xcode 时）
> # Windows: * Visual Studio 17 2022（有 VS 时）或 * NMake Makefiles
>
> # 5. 查询特定命令文档
> cmake --help-command add_executable
>
> # 6. 查询变量文档
> cmake --help-variable CMAKE_BUILD_TYPE
> ```
>
> **思考题答案：** CMake 没有统一的 `man` 或 `help <topic>` 接口，是因为它的帮助系统是逐步添加的，每个 `--help-*` 子命令对应不同的命名空间（command、variable、property、module、policy、generator）。这些命令互不重叠且语法各异。新版本中 `cmake --help` 已能提供相对完整的索引。实际工作中更推荐使用 [CMake 官方文档](https://cmake.org/cmake/help/latest/)的搜索功能或 IDE 集成（VSCode CMake Tools、CLion）获取即时帮助。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方教程（Step 1: A Basic Starting Point）](https://cmake.org/cmake/help/latest/guide/tutorial/A%20Basic%20Starting%20Point.html)——官方教程第一步
- [Modern CMake 导论](https://cliutils.gitlab.io/modern-cmake/chapters/intro/running.html)——Modern CMake 理念的入门读物
- [Effective Modern CMake (Manuel Binna)](https://gist.github.com/mbinna/c61dbb39bca0e4fb7d1f73b0d66a4fd1)——著名的 CMake 最佳实践 Gist
- [CMake 构建系统原理 (Kitware)](https://cmake.org/cmake/help/latest/manual/cmake-buildsystem.7.html)——官方对构建系统概念的深入解释
- [An Introduction to Build Systems (Bazel 文档)](https://bazel.build/basics) — 从 Bazel 视角看构建系统，有助于理解元构建系统的普遍设计模式

---

## 常见陷阱

> [!warning] In-Source Build（在源码目录中构建）
> **这是最常见的 CMake 错误。** 直接在源码目录运行 `cmake .` 而不指定 `-B`，CMake 会在源码目录中生成构建文件和中间产物，与源代码混在一起。后果：
> - `git status` 看到大量中间文件
> - 无法用不同生成器或不同配置同时构建
> - 清理困难（需要手动删除，没有统一的 `cmake clean`）
>
> **正确做法：** 始终使用 `-B <build-dir>` 指定独立的构建目录。如果已经污染了源码目录，用 `git clean -fdnx` 先预览要删除的文件，确认无误后再 `git clean -fdx` 清理。

> [!warning] 混合生成器类型
> 同一个构建目录必须始终使用同一个生成器。如果你第一次用 Ninja 生成了 `build/`，后来想在 `build/` 中用 Makefiles，必须删除 `build/` 重新生成。CMake 会检测生成器不匹配并报错，但不要依赖这个机制——直接使用不同的构建目录：
>
> ```bash
> cmake -B build-ninja -G Ninja
> cmake -B build-make  -G "Unix Makefiles"
> ```

> [!warning] 未设置 `cmake_minimum_required` 版本
> 省略 `cmake_minimum_required` 不会导致 configure 报错，但 CMake 会使用旧的兼容行为（策略默认值不同），可能导致：
> - `$<CONFIG>` 等生成器表达式行为怪异
> - 新特性不可用
> - 在不同 CMake 版本上的行为不一致
>
> **正确做法：** 始终在 `CMakeLists.txt` 第一行设置 `cmake_minimum_required(VERSION X.Y)`，其中 `X.Y` 是项目实际需要的最低版本。

> [!warning] 修改 `CMakeLists.txt` 后忘记重新 Configure
> 如果你在代码编辑器中修改了 `CMakeLists.txt`（而不是源文件），需要重新触发 Configure + Generate 才能生效。有两种方式：
> - 手动：`cmake -B build -S .`（重新配置）
> - 自动：`cmake --build build` 时 CMake 会检查 `CMakeLists.txt` 的时间戳，如果比缓存新，会自动重新 Configure
>
> 但并非所有工具链都启用了自动重新配置。如果不确定，手动重新配置总是安全的。

> [!warning] 构建目录路径中包含空格
> 在 Windows 上，如果构建路径包含空格（如 `C:\Users\My Name\build`），某些生成器（特别是 Unix Makefiles + MSYS Make）可能无法正确处理。优先使用不含空格的路径，或使用 Ninja 生成器（对空格支持更好）。

> [!warning] Visual Studio 生成器下 Debug/Release 输出路径不同
> 多配置生成器（Visual Studio、Xcode）会将不同配置的产物输出到不同子目录。例如 VS 生成器下 Release 产物在 `build/Release/`，Debug 产物在 `build/Debug/`。在构建和运行时要使用 `--config` 参数来指定配置，否则可能找不到可执行文件。
