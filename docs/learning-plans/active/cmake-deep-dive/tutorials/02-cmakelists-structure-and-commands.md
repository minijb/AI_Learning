---
title: CMakeLists.txt 结构与核心命令
updated: 2026-06-10
tags: [cmake, cmakelists, commands, fundamentals]
---

# CMakeLists.txt 结构与核心命令

> 所属计划: [[../plan|cmake-deep-dive]]
> 预计耗时: 60min
> 前置知识: [[01-cmake-basics-and-build-systems]]

---

## 1. 概念讲解

每个 CMake 项目的核心是一份或多份 `CMakeLists.txt` 文件。这份文件既是项目声明，也是构建蓝图——CMake 读取它，解析出目标 (target)、依赖关系、编译选项，然后生成平台特定的构建文件（Makefile、Visual Studio 解决方案、Ninja 文件等）。

本章深入讲解 `CMakeLists.txt` 中最核心的命令。理解这些命令的语义和行为，是后续所有内容的前提。

### 1.1 CMakeLists.txt 的执行模型

在深入单个命令之前，必须先理解 CMake 是如何执行 `CMakeLists.txt` 的。

CMake 的构建过程分为**两个阶段**：

1. **配置阶段 (Configure Phase)**：CMake 像解释器一样，从顶层 `CMakeLists.txt` 开始，逐行向下执行。遇到 `add_subdirectory()` 时，暂停当前目录，进入子目录的 `CMakeLists.txt` 执行完毕后返回。这是一个**命令式、自顶向下**的过程——就像运行一个脚本。配置阶段完成后，CMake 在内存中拥有一颗完整的构建目标树。

2. **生成阶段 (Generate Phase)**：CMake 根据内存中的目标树，生成平台特定的构建文件（Makefile、`.vcxproj`、`build.ninja` 等）。

> [!note] 关键区别
> 配置阶段执行 CMake 命令，生成阶段**不执行**任何 CMake 命令。生成阶段只做一件事：把配置阶段的结果"翻译"成构建系统的输入。理解这一点对调试至关重要——如果你修改了 `CMakeLists.txt`，CMake 会在下次构建时自动重新运行配置阶段。

**配置阶段**还会再细分为两个子阶段：
- **第一次处理 (first pass)**：目录作用域的创建、`cmake_minimum_required` 和 `project()` 的初始化
- **第二次处理 (second pass)**：剩余的配置逻辑执行

> [!tip] 实际影响
> 你不需要手动管理这两个子阶段。只需记住：`project()` 必须在其他涉及语言/编译器的命令之前调用，因为它在第一次处理中设置了语言相关的全局状态。

### 1.2 cmake_minimum_required() — 版本策略

这是每个 `CMakeLists.txt` **必须**出现的第一个命令（注释除外）。

```cmake
cmake_minimum_required(VERSION 3.24)
```

#### 为什么需要这个命令？

CMake 随着版本演进不断添加新特性、修复旧行为、废弃过时 API。当你写 `cmake_minimum_required(VERSION 3.24)` 时，你在告诉 CMake 两件事：

1. **你的项目至少需要 CMake 3.24 才能正确配置。** 如果有人用 CMake 3.20 运行你的项目，CMake 会立即报错并停止，而不是在配置到一半时出现莫名其妙的错误。

2. **启用指定版本的策略设置 (policies)。** CMake 有一个策略系统——每当某个行为需要变化时，CMake 引入一个新的 policy，给用户一个过渡期。`cmake_minimum_required` 隐式地设置了所有 ≤ 指定版本的 policy 为 `NEW`（新行为）。

#### 策略系统详解

CMake 的策略命名规则是 `CMP<NNNN>`，例如 `CMP0048`、`CMP0077`。每个策略控制一个行为变更。策略有三种状态：

| 状态 | 含义 |
|------|------|
| `OLD` | 使用旧行为（兼容模式） |
| `NEW` | 使用新行为（推荐） |
| 未设置 | CMake 打印警告，仍使用 `OLD` |

当你写 `cmake_minimum_required(VERSION 3.24)` 时，所有 `CMP0000` 到 `CMP0159`（对应 3.24 的最后一个策略号）中被标记为"该版本引入"的 policy 都会被隐式设置为 `NEW`。

> [!warning] FATAL_ERROR 的误解
> 旧教程中常看到 `cmake_minimum_required(VERSION 2.8 FATAL_ERROR)`。在 CMake 2.6 时代，不满足最低版本要求只会打印警告继续运行——`FATAL_ERROR` 强制停止。**从 CMake 3.0 开始，不满足版本要求默认就是 fatal 的，`FATAL_ERROR` 关键字已被弃用，在 CMake 4.0 中将被移除。** 不要再写它。

```cmake
# ✅ 正确：Modern CMake 风格
cmake_minimum_required(VERSION 3.24)

# ❌ 过时：2.6 时代的残留写法
cmake_minimum_required(VERSION 2.8 FATAL_ERROR)

# ❌ 过低：失去现代特性
cmake_minimum_required(VERSION 2.8.12)
```

#### 版本选择策略

选择哪个最低版本？一个实用的参考：

| 版本 | 关键特性 |
|------|---------|
| 3.16 | `FetchContent` 稳定、`target_precompile_headers`、Unity builds |
| 3.20 | `CXX_STANDARD 23`、Presets v3、`cmake_path()` |
| 3.21 | `PROJECT_IS_TOP_LEVEL`、`C_STANDARD 23`、`--install-prefix` |
| 3.24 | `CMAKE_COMPILE_WARNING_AS_ERROR`、`SEMICOLON` 在 `cmake -E` 中 |
| 3.28 | `EXPORT_NO_SYSTEM` for `install(TARGETS)`、HIP 语言支持 |

> [!tip] 实战建议
> 新项目起步选择你环境中安装的最高版本减 2，例如你装了 CMake 3.28，就选 3.26。库项目考虑下游用户，选择更保守的版本（3.16 或 3.20）。

### 1.3 project() — 项目声明

```cmake
project(<项目名>
        [VERSION <主>[.<次>[.<补丁>]]]
        [DESCRIPTION <项目描述>]
        [HOMEPAGE_URL <URL>]
        [LANGUAGES <语言1> [<语言2>...]]
)
```

`project()` 告诉 CMake 这是项目根，并设置一系列全局变量。调用 `project()` 后，CMake 会检测指定的编译器。

```cmake
project(MyEngine
        VERSION 1.2.3
        DESCRIPTION "A lightweight game engine"
        HOMEPAGE_URL "https://github.com/me/MyEngine"
        LANGUAGES C CXX
)
```

#### 做了什么？

调用 `project(MyEngine VERSION 1.2.3 ...)` 后，CMake 自动设置以下变量：

| 变量名 | 值 |
|--------|-----|
| `PROJECT_NAME` | `MyEngine` |
| `PROJECT_VERSION` | `1.2.3` |
| `PROJECT_VERSION_MAJOR` | `1` |
| `PROJECT_VERSION_MINOR` | `2` |
| `PROJECT_VERSION_PATCH` | `3` |
| `PROJECT_DESCRIPTION` | `"A lightweight game engine"` |
| `PROJECT_HOMEPAGE_URL` | `"https://github.com/me/MyEngine"` |
| `CMAKE_PROJECT_NAME` | `MyEngine`（顶层项目名） |
| `PROJECT_SOURCE_DIR` | 当前 `CMakeLists.txt` 所在目录 |
| `PROJECT_BINARY_DIR` | 当前构建目录 |
| `MyEngine_SOURCE_DIR` | 同上（以项目名命名的变量） |
| `MyEngine_BINARY_DIR` | 同上 |

> [!warning] `PROJECT_SOURCE_DIR` vs `CMAKE_SOURCE_DIR`
> `PROJECT_SOURCE_DIR` 是最近一次调用 `project()` 的目录，而 `CMAKE_SOURCE_DIR` 永远是顶层 `CMakeLists.txt` 所在目录。在子目录中（通过 `add_subdirectory`），它们的值不同。**永远使用 `PROJECT_SOURCE_DIR`，除非你确定需要顶层目录。**

#### LANGUAGES

默认不写 `LANGUAGES` 时，CMake 检测 C 和 CXX（C++）。如果你的项目是纯 C 或纯 C++，显式指定：

```cmake
project(MyLib LANGUAGES C)       # 纯 C 项目
project(MyApp LANGUAGES CXX)     # 纯 C++ 项目
project(MyTool LANGUAGES NONE)   # 无需编译器（纯脚本项目）
```

设置 `NONE` 可以跳过编译器检测——适用于头文件库 (header-only library) 或用 CMake 做脚本编排的项目。

> [!tip] `PROJECT_IS_TOP_LEVEL`
> CMake 3.21+ 引入 `PROJECT_IS_TOP_LEVEL` 变量，在顶层 `CMakeLists.txt` 的 `project()` 调用后为 `TRUE`。这对于区分"我的项目作为顶层构建"和"我的项目作为子目录被 include"非常有用。

### 1.4 add_executable() 和 add_library() — 两个核心目标命令

CMake 的一切围绕**目标 (target)** 构建。目标代表一个构建产物：可执行文件、库、或自定义输出。

```cmake
# 可执行文件
add_executable(<目标名> [WIN32] [MACOSX_BUNDLE]
               [EXCLUDE_FROM_ALL]
               <源文件1> [<源文件2> ...]
)

# 库
add_library(<目标名> [STATIC | SHARED | MODULE | OBJECT | INTERFACE]
            [EXCLUDE_FROM_ALL]
            <源文件1> [<源文件2> ...]
)
```

#### add_executable 详解

```cmake
add_executable(my_app main.cpp utils.cpp)
```

这创建一个名为 `my_app` 的可执行目标。构建时会编译 `main.cpp` 和 `utils.cpp` 并链接为 `my_app`（Linux/macOS）或 `my_app.exe`（Windows）。

关键选项：
- `WIN32`：Windows 上编译为 GUI 应用（无控制台窗口），Linux/macOS 无效果。
- `MACOSX_BUNDLE`：macOS 上编译为 `.app` Bundle。
- `EXCLUDE_FROM_ALL`：此目标不会在默认 `make`/`cmake --build .` 时构建，需显式指定目标名。

#### add_library 详解

CMake 支持五种库类型：

| 类型 | 关键词 | 产物 | 用途 |
|------|--------|------|------|
| STATIC | `STATIC` | `.a` / `.lib` | 编译时链接到可执行文件 |
| SHARED | `SHARED` | `.so` / `.dll` + `.lib` | 运行时动态加载 |
| MODULE | `MODULE` | `.so` / `.dll` | 插件，不用于链接 |
| OBJECT | `OBJECT` | `.o` / `.obj` | 编译但不链接，用于组合 |
| INTERFACE | `INTERFACE` | 无产物 | Header-only 库，传递编译要求 |

```cmake
add_library(my_static STATIC lib.cpp)
add_library(my_shared SHARED lib.cpp)
add_library(my_module MODULE plugin.cpp)
add_library(my_objects OBJECT obj1.cpp obj2.cpp)
add_library(my_header_only INTERFACE)
```

> [!note] OBJECT 库的特殊性
> `OBJECT` 库只编译源文件为 `.o`/`.obj` 但不链接。多个 `add_executable` 或 `add_library` 可以使用同一个 OBJECT 库的目标文件，通过 `$<TARGET_OBJECTS:my_objects>` 生成器表达式引用。这在需要将同一份编译产物链接到不同目标时非常有用。

> [!note] INTERFACE 库的特殊性
> `INTERFACE` 库不编译任何源文件——它本身没有产物。它的作用是**传递编译要求**（头文件路径、编译定义、链接选项等）给使用它的目标。Header-only 库的标准写法就是用 `INTERFACE` 库。

如果在 `add_library` 中不指定类型，CMake 根据 `BUILD_SHARED_LIBS` 变量决定：
- `BUILD_SHARED_LIBS=ON` → `SHARED`
- `BUILD_SHARED_LIBS=OFF`（默认）→ `STATIC`

```cmake
# 用户可以通过 -DBUILD_SHARED_LIBS=ON 切换
add_library(my_flexible lib.cpp)
```

### 1.5 add_subdirectory() — 构建多目录项目

```cmake
add_subdirectory(<源目录> [<二进制目录>] [EXCLUDE_FROM_ALL])
```

`add_subdirectory()` 让 CMake 进入一个子目录，处理那里的 `CMakeLists.txt`。这是组织多目录项目的核心机制。

```
my_project/
├── CMakeLists.txt          ← 顶层
├── src/
│   ├── CMakeLists.txt      ← add_subdirectory(src)
│   ├── main.cpp
│   └── utils.cpp
└── lib/
    ├── CMakeLists.txt      ← add_subdirectory(lib)
    └── math.cpp
```

顶层 `CMakeLists.txt`：
```cmake
cmake_minimum_required(VERSION 3.24)
project(MyProject LANGUAGES CXX)

add_subdirectory(lib)
add_subdirectory(src)
```

子目录 `src/CMakeLists.txt`：
```cmake
add_executable(my_app main.cpp utils.cpp)
target_link_libraries(my_app PRIVATE my_math)  # my_math 定义在 lib/ 中
```

子目录 `lib/CMakeLists.txt`：
```cmake
add_library(my_math STATIC math.cpp)
```

#### 目录作用域

`add_subdirectory()` 的**关键语义**：它创建一个新的**变量作用域 (variable scope)**。子目录中的 CMake 命令拥有：
- 父目录变量的**副本**（修改不影响父目录）
- 父目录目标的**完整访问权**（目标本身在全局命名空间中）

```cmake
# 顶层 CMakeLists.txt
set(VAR "parent")
add_subdirectory(sub)    # sub/CMakeLists.txt 修改了 VAR
message("VAR = ${VAR}")  # 输出: VAR = parent  ← 不受子目录影响！
```

```cmake
# sub/CMakeLists.txt
message("VAR = ${VAR}")  # 输出: VAR = parent  ← 继承了父目录的值
set(VAR "child")          # 只修改自己的副本
```

> [!warning] 将变量传回父目录
> 如果子目录需要修改父目录的变量，使用 `set(VAR "value" PARENT_SCOPE)`。详见 [[04-variables-cache-and-scope]]。

#### EXCLUDE_FROM_ALL

加上 `EXCLUDE_FROM_ALL` 后，子目录中的所有目标都不会参与默认构建，除非被显式依赖或显式指定。

```cmake
add_subdirectory(tests EXCLUDE_FROM_ALL)  # 默认不构建测试
add_subdirectory(examples EXCLUDE_FROM_ALL)  # 默认不构建示例
```

### 1.6 target_sources() — Modern CMake 添加源文件的方式

```cmake
target_sources(<目标名>
  <PRIVATE|PUBLIC|INTERFACE> <源文件1> [<源文件2> ...]
  [<PRIVATE|PUBLIC|INTERFACE> <源文件3> [<源文件4> ...]]
  ...
)
```

在传统写法中，源文件直接写在 `add_executable` 或 `add_library` 里：

```cmake
# 传统风格
add_executable(my_app main.cpp utils.cpp network/tcp.cpp network/udp.cpp ...)
```

Modern CMake 推荐将声明和源文件分开：

```cmake
# Modern 风格
add_executable(my_app)
target_sources(my_app
  PRIVATE
    main.cpp
    utils.cpp
    network/tcp.cpp
    network/udp.cpp
)
```

#### 为什么用 target_sources？

1. **可扩展性。** 你可以在不同位置追加源文件：

```cmake
# src/CMakeLists.txt
add_executable(my_app)
target_sources(my_app PRIVATE main.cpp utils.cpp)

# src/network/CMakeLists.txt（通过 add_subdirectory 进入）
target_sources(my_app PRIVATE tcp.cpp udp.cpp)
```

2. **条件编译更清晰：**

```cmake
target_sources(my_app
  PRIVATE
    core.cpp
    $<$<PLATFORM_ID:Windows>:win32_specific.cpp>
    $<$<PLATFORM_ID:Linux>:linux_specific.cpp>
)
```

3. **职责分离。** `add_executable` 只声明"这是一个可执行文件"，`target_sources` 负责"它的源文件是这些"。这对于大型项目、跨平台项目尤其重要。

> [!tip] 最佳实践
> CMake 3.0+ 项目应该在 `add_executable` / `add_library` 中至少放一个源文件（或直接用空括号），然后用 `target_sources` 添加其余文件。CMake 3.11+ 可以用 `target_sources` 添加文件到任何目录中定义的目标。

### 1.7 include() vs add_subdirectory() — 何时用哪个

这两个命令看起来相似——都涉及引入外部 CMake 代码——但语义完全不同。

| 特性 | `include()` | `add_subdirectory()` |
|------|------------|---------------------|
| 执行位置 | 当前作用域 | 新作用域 |
| 文件类型 | `.cmake` 模块或 `CMakeLists.txt` | 只处理 `CMakeLists.txt` |
| 变量作用域 | 共享（修改跨越边界） | 隔离（修改不传回父目录） |
| 二进制目录 | 不变 | 自动创建子目录 |
| 典型用途 | 引入 CMake 模块/函数 | 添加子项目 |

```cmake
# include: 在当前作用域中执行 CMake 脚本
include(FindSomePackage)
include(cmake/MyHelpers.cmake)

# add_subdirectory: 创建新作用域，处理子项目
add_subdirectory(lib)
add_subdirectory(src)
```

#### 选择指南

- **需要构建目标？** → `add_subdirectory()`。它是为多目录项目设计的。
- **引入 CMake 函数、宏、变量定义？** → `include()`。模块代码通常不创建目标。
- **引入第三方代码？** → 优先 `FetchContent`（内部打包再用 `add_subdirectory`），或者 `find_package()`。

```cmake
# ✅ 正确：用 include 引入自定义函数模块
include(cmake/CompilerWarnings.cmake)
set_project_warnings(my_target)  # 模块中定义的函数

# ✅ 正确：用 add_subdirectory 引入子项目
add_subdirectory(external/json)  # json/ 下有完整的 CMakeLists.txt

# ❌ 错误：用 include 引入有 add_library 的 CMakeLists.txt
# include(external/json/CMakeLists.txt)  # 这会在当前作用域创建目标，可能导致意外
```

> [!warning] `include()` 的变量泄露
> 因为 `include()` 不创建新作用域，模块中 `set()` 的变量会污染调用者的作用域。这是故意的——这正是模块能工作的原因。但如果模块不小心覆盖了你的变量，调试起来会很痛苦。好的做法是在模块内用函数封装，在函数内使用局部变量。

### 1.8 message() — 日志与诊断

```cmake
message([<mode>] "消息内容" [<变量>...])
```

CMake 的 `message()` 支持以下日志级别：

| 模式 | 含义 | 是否停止配置？ |
|------|------|---------------|
| （无） | 默认：重要信息，始终显示 | 否 |
| `STATUS` | 状态信息，显示但前缀为 `--` | 否 |
| `VERBOSE` | 详细调试信息（需 `--log-level=VERBOSE`） | 否 |
| `DEBUG` | 调试信息（需 `--log-level=DEBUG`） | 否 |
| `TRACE` | 极详细跟踪（需 `--log-level=TRACE`） | 否 |
| `NOTICE` | 通知信息（CMake 3.15+，默认行为） | 否 |
| `WARNING` | 警告，继续运行 | 否 |
| `AUTHOR_WARNING` | 开发者警告（仅项目作者可见，下游用户不显示） | 否 |
| `DEPRECATION` | 弃用警告（可通过 `CMAKE_WARN_DEPRECATED` 关闭） | 否 |
| `SEND_ERROR` | 错误，继续但阻止生成 | **是** |
| `FATAL_ERROR` | 致命错误，立即停止 | **是** |

```cmake
message(STATUS "CMake version: ${CMAKE_VERSION}")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "Source dir: ${PROJECT_SOURCE_DIR}")

message(WARNING "Using experimental feature X, might break in future versions")

message(AUTHOR_WARNING "TODO: replace this workaround before release")

message(DEPRECATION "find_my_package is deprecated, use find_package(MyPackage) instead")

# 下面两个会停止配置
# message(SEND_ERROR "Required config file not found")
# message(FATAL_ERROR "Critical dependency missing")
```

> [!tip] `message()` 与变量插值
> `message()` 自动展开 `${VAR}` 引用。如果括号不平衡，CMake 会报语法错误。在 message 中想输出字面的 `${...}`，使用 `\${...}`。

#### 控制日志输出量

从 CMake 3.15 开始，可以用 `--log-level` 命令行选项控制显示哪些级别的消息：

```bash
cmake -B build --log-level=DEBUG     # 显示 DEBUG 及以上
cmake -B build --log-level=WARNING   # 只显示 WARNING 及以上
cmake -B build --log-level=ERROR     # 只显示错误
```

也可以在 `CMakeLists.txt` 中设置：

```cmake
set(CMAKE_MESSAGE_LOG_LEVEL DEBUG)  # 对当前目录及子目录生效
```

### 1.9 set() 和 unset() — 变量基础

#### set()

```cmake
set(<变量名> <值1> [<值2> ...] [CACHE <类型> <描述> [FORCE]] [PARENT_SCOPE])
```

CMake 变量是**字符串列表**——多个值用分号 `;` 分隔。

```cmake
# 普通变量（当前作用域）
set(MY_VAR "hello")
set(MY_LIST "one" "two" "three")  # 等价于 "one;two;three"
set(MY_SOURCES main.cpp utils.cpp)

# CACHE 变量（在 CMakeCache.txt 中持久化，全局可见）
set(MY_OPTION "ON" CACHE STRING "Enable feature X")
set(MY_OPTION "OFF" CACHE STRING "Enable feature X" FORCE)  # 强制覆盖

# 父作用域变量（用于从子目录传值回父目录）
set(MY_RESULT "done" PARENT_SCOPE)
```

CMake 变量的几个关键特性：

1. **一切皆字符串。** `set(VAR 1)` 设置的是字符串 `"1"`，不是整数。在 `if()` 条件中，CMake 会自动进行数值比较。

2. **变量引用。** `${VAR}` 在命令解析时被替换为变量的值。这是**展开 (expansion)** 语义。

3. **未定义变量的行为。** 引用未定义的变量 `${NO_SUCH_VAR}` 展开为空字符串，**不会报错**。这是最常见的调试陷阱。

4. **嵌套引用。** `${${OUTER}_SUFFIX}` 会先展开 `${OUTER}`，再展开结果拼接 `_SUFFIX` 后的变量。

```cmake
set(PLATFORM "LINUX")
set(LINUX_COMPILER "gcc")
set(WINDOWS_COMPILER "msvc")

message("Compiler: ${${PLATFORM}_COMPILER}")  # 输出: Compiler: gcc
```

#### unset()

```cmake
unset(<变量名> [CACHE | PARENT_SCOPE])
```

```cmake
set(TEMP_VAR "hello")
unset(TEMP_VAR)
message("TEMP_VAR = ${TEMP_VAR}")  # 输出: TEMP_VAR = （空字符串）

# 也支持 CACHE 和 PARENT_SCOPE
unset(MY_CACHE_VAR CACHE)
unset(PARENT_VAR PARENT_SCOPE)
```

> [!warning] `unset()` 不是删除，是"设为未定义"
> 未定义的变量 `${VAR}` 展开为空字符串，和 `set(VAR "")` 的字符串比较结果相同。但 `if(DEFINED VAR)` 能区分两者。

### 1.10 CMake 脚本模式 — `cmake -P`

你可以将 `CMakeLists.txt` 的语法作为独立脚本运行，无需构建任何东西。这对于系统探测、代码生成、自动化任务非常有用。

```bash
cmake -P script.cmake
```

脚本模式的特点：
- 不需要 `CMakeLists.txt`——任意 `.cmake` 文件
- 不执行配置/生成阶段——脚本直接运行
- 不能使用需要构建目标上下文（如 `target_*` 函数）的命令
- 可以使用所有条件判断、循环、文件操作、字符串操作的命令

```cmake
# check_env.cmake — 一个系统检查脚本
cmake_minimum_required(VERSION 3.24)

message(STATUS "===== System Check =====")
message(STATUS "CMake version: ${CMAKE_VERSION}")
message(STATUS "Host system: ${CMAKE_HOST_SYSTEM_NAME}")
message(STATUS "Host processor: ${CMAKE_HOST_SYSTEM_PROCESSOR}")

if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
    message(STATUS "Running on Linux — using GCC/Clang toolchain")
elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
    message(STATUS "Running on Windows — using MSVC toolchain")
elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
    message(STATUS "Running on macOS — using AppleClang toolchain")
endif()

message(STATUS "===== Done =====")
```

> [!tip] `cmake -P` 的常见用途
> - 代码生成脚本（在配置阶段之前运行）
> - 依赖下载与验证脚本
> - 构建后处理（与 `cmake -E` 结合）
> - 持续集成环境检查

### 1.11 目录作用域深度解析

我们已经看到 `add_subdirectory()` 创建新作用域。让我们更系统地理解整个作用域机制。

#### 变量查找顺序

CMake 在引用 `${VAR}` 时按以下顺序查找：

1. **当前作用域的普通变量**（用 `set(VAR ...)` 设置）
2. **父作用域的普通变量**（通过 `add_subdirectory` 继承）
3. **Cache 变量**（全局，在 `CMakeCache.txt` 中持久化）
4. **环境变量**（`$ENV{VAR}`）

#### 作用域边界示例

```
顶层 CMakeLists.txt:
  set(A "top-A")           ← 顶层作用域
  set(B "top-B")
  add_subdirectory(mid)    ← 进入 mid/

mid/CMakeLists.txt:
  message("A = ${A}")      ← "top-A" (从父作用域继承)
  set(B "mid-B")           ← 在 mid 作用域中覆盖
  set(C "mid-C")           ← mid 作用域新变量
  add_subdirectory(bot)    ← 进入 bot/

bot/CMakeLists.txt:
  message("A = ${A}")      ← "top-A" (从祖父作用域继承)
  message("B = ${B}")      ← "mid-B" (从父作用域继承)
  message("C = ${C}")      ← "mid-C" (从父作用域继承)
  set(A "bot-A")           ← 只在 bot 作用域中修改

回到 mid/:
  message("A = ${A}")      ← "top-A" (bot 的修改不影响 mid)

回到顶层:
  message("A = ${A}")      ← "top-A"
  message("B = ${B}")      ← "mid-B" ← 等等？

# 实际上 message("B = ${B}") 在顶层仍然输出 "top-B"！
# 因为 mid/CMakeLists.txt 执行完毕后，mid 的作用域被销毁，
# 顶层的 B 从未被修改——mid 修改的是自己的副本。
```

> [!tip] 心智模型
> 把每个 `add_subdirectory` 想象为一个函数调用：子目录获得父目录变量的一份**浅拷贝**。子目录修改自己的拷贝不影响父目录，但可以通过 `set(... PARENT_SCOPE)` 显式回传。

#### 目标没有作用域

**目标（target）是全局的。** 在子目录中创建的目标 (`add_executable`，`add_library`) 在顶层也可见。这是故意的——CMake 认为目标树应该在整个项目中可见。

```cmake
# lib/CMakeLists.txt
add_library(my_lib STATIC math.cpp)

# src/CMakeLists.txt
target_link_libraries(my_app PRIVATE my_lib)  # ✅ my_lib 从 lib/ 中可见
```

---

## 2. 代码示例

### 示例 1：一个完整的单目录项目

这是一个可编译、可运行的完整项目，展示 `cmake_minimum_required`、`project()`、`add_executable` 和 `target_sources` 的标准用法。

**项目结构：**
```
example1/
├── CMakeLists.txt
├── main.cpp
├── utils.h
└── utils.cpp
```

**`CMakeLists.txt`：**
```cmake
cmake_minimum_required(VERSION 3.24)
project(HelloApp
        VERSION 1.0.0
        DESCRIPTION "A simple CMake demonstration project"
        LANGUAGES CXX
)

# 要求 C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 声明目标
add_executable(hello_app)

# 使用 target_sources 添加源文件（Modern CMake 风格）
target_sources(hello_app
  PRIVATE
    main.cpp
    utils.cpp
)

# 添加私有头文件路径
target_include_directories(hello_app PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
```

**`main.cpp`：**
```cpp
#include "utils.h"
#include <iostream>

int main() {
    std::cout << "Project: " << PROJECT_NAME << std::endl;
    std::cout << "Version: " << PROJECT_VERSION << std::endl;
    std::cout << "Sum: " << add(3, 4) << std::endl;
    return 0;
}
```

**`utils.h`：**
```cpp
#pragma once
int add(int a, int b);
```

**`utils.cpp`：**
```cpp
#include "utils.h"
int add(int a, int b) {
    return a + b;
}
```

**运行方式：**
```bash
mkdir example1 && cd example1
# 创建上述四个文件
cmake -B build -DCMAKE_PROJECT_NAME=HelloApp -DPROJECT_NAME=HelloApp -DPROJECT_VERSION=1.0.0
cmake --build build
./build/hello_app           # Linux/macOS
# build\Debug\hello_app.exe  # Windows
```

> [!note] 关于宏定义
> 上述 `main.cpp` 中使用了 `PROJECT_NAME` 和 `PROJECT_VERSION`，这些需要通过 `target_compile_definitions` 传入，或使用 `configure_file` 生成头文件。此处为简化演示，实际使用时请参考 [[18-configure-file-and-code-generation]]。

**预期输出：**
```text
Project: HelloApp
Version: 1.0.0
Sum: 7
```

### 示例 2：多目录项目

展示 `add_subdirectory` 如何组织 `src/` 和 `lib/` 的分离。

**项目结构：**
```
example2/
├── CMakeLists.txt
├── lib/
│   ├── CMakeLists.txt
│   ├── math.h
│   └── math.cpp
└── src/
    ├── CMakeLists.txt
    └── main.cpp
```

**顶层 `CMakeLists.txt`：**
```cmake
cmake_minimum_required(VERSION 3.24)
project(MultiDirApp VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 先构建库，再构建可执行文件——顺序很重要
add_subdirectory(lib)
add_subdirectory(src)
```

**`lib/CMakeLists.txt`：**
```cmake
add_library(math STATIC math.cpp)

target_include_directories(math
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}   # 任何链接 math 的目标自动获得此路径
)
```

> [!note] `PUBLIC` vs `PRIVATE` 在 `target_include_directories` 中
> `PUBLIC`：此头文件路径同时用于编译 `math` 自身，以及传给任何链接 `math` 的目标。
> `INTERFACE`：仅传给使用者，不用于 `math` 自身。
> `PRIVATE`：仅用于编译 `math` 自身。详见 [[07-target-link-libraries-and-transitive-deps]]。

**`src/CMakeLists.txt`：**
```cmake
add_executable(multi_app main.cpp)

target_link_libraries(multi_app PRIVATE math)
```

**`lib/math.h`：**
```cpp
#pragma once
namespace math {
    int multiply(int a, int b);
}
```

**`lib/math.cpp`：**
```cpp
#include "math.h"
namespace math {
    int multiply(int a, int b) {
        return a * b;
    }
}
```

**`src/main.cpp`：**
```cpp
#include <iostream>
#include "math.h"

int main() {
    std::cout << "3 * 7 = " << math::multiply(3, 7) << std::endl;
    return 0;
}
```

**运行方式：**
```bash
mkdir example2 && cd example2
# 创建上述目录和文件
cmake -B build
cmake --build build
./build/src/multi_app
```

**预期输出：**
```text
3 * 7 = 21
```

#### 作用域验证

你可以在上述项目中添加 `message()` 来观察作用域行为。在顶层、`lib/`、`src/` 的 `CMakeLists.txt` 中各添加：

```cmake
# 顶层 CMakeLists.txt
set(SCOPE_VAR "top_level")
message(STATUS "[top] PROJECT_SOURCE_DIR = ${PROJECT_SOURCE_DIR}")
message(STATUS "[top] CMAKE_SOURCE_DIR   = ${CMAKE_SOURCE_DIR}")
add_subdirectory(lib)
add_subdirectory(src)
message(STATUS "[top] After subdirs, SCOPE_VAR = ${SCOPE_VAR}")  # 仍然是 top_level
```

```cmake
# lib/CMakeLists.txt
message(STATUS "[lib] PROJECT_SOURCE_DIR = ${PROJECT_SOURCE_DIR}")
message(STATUS "[lib] CMAKE_SOURCE_DIR   = ${CMAKE_SOURCE_DIR}")
message(STATUS "[lib] SCOPE_VAR = ${SCOPE_VAR}")  # top_level (继承的)
set(SCOPE_VAR "modified_in_lib" PARENT_SCOPE)       # 回传给顶层
```

```cmake
# src/CMakeLists.txt
message(STATUS "[src] PROJECT_SOURCE_DIR = ${PROJECT_SOURCE_DIR}")
message(STATUS "[src] SCOPE_VAR = ${SCOPE_VAR}")  # top_level (继承自顶层，而非 lib 的修改)
```

**预期输出（部分）：**
```text
-- [top] PROJECT_SOURCE_DIR = /path/to/example2
-- [top] CMAKE_SOURCE_DIR   = /path/to/example2
-- [lib] PROJECT_SOURCE_DIR = /path/to/example2/lib
-- [lib] CMAKE_SOURCE_DIR   = /path/to/example2
-- [lib] SCOPE_VAR = top_level
-- [src] PROJECT_SOURCE_DIR = /path/to/example2/src
-- [src] SCOPE_VAR = top_level
-- [top] After subdirs, SCOPE_VAR = modified_in_lib
```

### 示例 3：message() 日志级别演示 + 脚本模式

**Part A — 在项目构建中演示不同日志级别**

**`CMakeLists.txt`：**
```cmake
cmake_minimum_required(VERSION 3.24)
project(LogDemo LANGUAGES CXX)

# 各级别消息
message(STATUS       "1. STATUS: 正常状态信息")
message(NOTICE       "2. NOTICE: 通知信息（CMake 3.15+，默认模式）")
message(VERBOSE      "3. VERBOSE: 详细信息（需 --log-level=VERBOSE）")
message(DEBUG        "4. DEBUG: 调试信息（需 --log-level=DEBUG）")
message(TRACE        "5. TRACE: 跟踪信息（需 --log-level=TRACE）")
message(WARNING      "6. WARNING: 警告但继续运行")
message(AUTHOR_WARNING "7. AUTHOR_WARNING: 仅项目作者可见")
message(DEPRECATION  "8. DEPRECATION: 弃用警告")

# 下面两行被注释掉，因为它们会停止配置
# message(SEND_ERROR   "9. SEND_ERROR: 出错但继续处理剩余代码")
# message(FATAL_ERROR  "10. FATAL_ERROR: 致命错误，立即终止")
```

**运行方式：**
```bash
# 默认级别（显示 STATUS、NOTICE、WARNING、AUTHOR_WARNING、DEPRECATION）
cmake -B build

# 显示 DEBUG 及以上
cmake -B build --log-level=DEBUG

# 只显示 WARNING 及以上
cmake -B build --log-level=WARNING

# 显示所有，包括 TRACE
cmake -B build --log-level=TRACE
```

**预期输出（默认 `--log-level=STATUS`）：**
```text
-- 1. STATUS: 正常状态信息
-- 2. NOTICE: 通知信息（CMake 3.15+，默认模式）
CMake Warning at CMakeLists.txt:11 (message):
  6. WARNING: 警告但继续运行
CMake Warning (dev) at CMakeLists.txt:12 (message):
  7. AUTHOR_WARNING: 仅项目作者可见
This warning is for project developers.  Use -Wno-dev to suppress it.
CMake Deprecation Warning at CMakeLists.txt:13 (message):
  8. DEPRECATION: 弃用警告
```

> [!note] 观察
> - `VERBOSE`、`DEBUG`、`TRACE` 级别的消息未出现——需要提高日志级别
> - `WARNING` 消息自带 `CMake Warning` 前缀
> - `AUTHOR_WARNING` 额外带有 `(dev)` 标记和提示文本（可通过 `-Wno-dev` 抑制）
> - `DEPRECATION` 额外带有 `Deprecation Warning` 前缀

**Part B — 脚本模式**

**`check_system.cmake`：**
```cmake
# check_system.cmake — 独立运行的 CMake 脚本
cmake_minimum_required(VERSION 3.24)

message(STATUS "=== 系统信息 ===")
message(STATUS "CMake 版本:    ${CMAKE_VERSION}")
message(STATUS "主机系统:      ${CMAKE_HOST_SYSTEM_NAME}")
message(STATUS "主机处理器:    ${CMAKE_HOST_SYSTEM_PROCESSOR}")
message(STATUS "主机系统版本:  ${CMAKE_HOST_SYSTEM_VERSION}")

math(EXPR RESULT "2 * 21 + 3")
message(STATUS "CMake 也能做数学: 2 * 21 + 3 = ${RESULT}")

# 检测操作系统
if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
    message(STATUS "✓ 运行在 Linux 上")
    set(PLATFORM "linux")
elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
    message(STATUS "✓ 运行在 Windows 上")
    set(PLATFORM "windows")
elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
    message(STATUS "✓ 运行在 macOS 上")
    set(PLATFORM "macos")
else()
    message(WARNING "未知平台: ${CMAKE_HOST_SYSTEM_NAME}")
    set(PLATFORM "unknown")
endif()

message(STATUS "检测到平台变量: PLATFORM = ${PLATFORM}")
message(STATUS "=== 完成 ===")
```

**运行方式：**
```bash
cmake -P check_system.cmake
```

**预期输出（Linux 示例）：**
```text
-- === 系统信息 ===
-- CMake 版本:    3.28.1
-- 主机系统:      Linux
-- 主机处理器:    x86_64
-- 主机系统版本:  6.5.0-14-generic
-- CMake 也能做数学: 2 * 21 + 3 = 45
-- ✓ 运行在 Linux 上
-- 检测到平台变量: PLATFORM = linux
-- === 完成 ===
```

**Part C — 用脚本模式的 SEND_ERROR 和 FATAL_ERROR 验证停止行为**

**`test_error_levels.cmake`：**
```cmake
cmake_minimum_required(VERSION 3.24)

message(STATUS "1. 开始测试")
message(STATUS "2. 这条正常显示")

# 取消下面某一行注释来观察效果
# message(SEND_ERROR "3a. SEND_ERROR: 继续执行后面的代码，但最终阻止生成")
# message(FATAL_ERROR "3b. FATAL_ERROR: 立即停止，后面的代码不会执行")

message(STATUS "4. 如果上面是 SEND_ERROR，这条仍然会打印")
message(STATUS "5. 如果上面是 FATAL_ERROR，这条永远不会执行")
```

**运行方式：**
```bash
# 测试 SEND_ERROR（先取消注释第7行）
cmake -P test_error_levels.cmake

# 测试 FATAL_ERROR（先取消注释第8行）
cmake -P test_error_levels.cmake
```

**预期输出 — SEND_ERROR：**
```text
-- 1. 开始测试
-- 2. 这条正常显示
CMake Error at test_error_levels.cmake:7 (message):
  3a. SEND_ERROR: 继续执行后面的代码，但最终阻止生成

-- 4. 如果上面是 SEND_ERROR，这条仍然会打印
-- 5. 如果上面是 FATAL_ERROR，这条永远不会执行
```

**预期输出 — FATAL_ERROR：**
```text
-- 1. 开始测试
-- 2. 这条正常显示
CMake Error at test_error_levels.cmake:8 (message):
  3b. FATAL_ERROR: 立即停止，后面的代码不会执行

(第4、5行不会出现)
```

> [!tip] `SEND_ERROR` vs `FATAL_ERROR` 的选择
> `SEND_ERROR` 用于"我想知道所有错误再一起修复"的场景——例如 CI 中收集所有问题。
> `FATAL_ERROR` 用于"继续已经没有意义"的场景——例如缺少必需的工具或文件。
> 在项目构建中，`SEND_ERROR` 会阻止生成阶段，所以最终构建不会运行，但你看到了完整的错误列表。

---

## 3. 练习

### 练习 1：创建多目录项目（基础）

在本地创建一个项目，目录结构如下：

```
my_project/
├── CMakeLists.txt
├── lib/
│   ├── CMakeLists.txt
│   ├── string_utils.h
│   └── string_utils.cpp
└── src/
    ├── CMakeLists.txt
    └── main.cpp
```

要求：
- 使用 CMake 3.24+
- `lib/` 编译为静态库 `string_utils`，提供一个函数 `std::string reverse(const std::string& input)`
- `src/` 编译为可执行文件 `my_app`，调用 `reverse` 并打印结果
- 使用 `target_sources` 添加源文件（不要把所有文件写在 `add_library`/`add_executable` 里）
- 使用 `target_include_directories` 的 `PUBLIC` 可见性
- 在顶层、`lib/`、`src/` 中各添加一条 `message(STATUS ...)`，输出当前 `PROJECT_SOURCE_DIR`

### 练习 2：编写 CMake 系统探测脚本（进阶）

创建一个 `sysinfo.cmake` 脚本（用 `cmake -P` 运行），输出以下信息：

- CMake 版本号
- 主机系统名称和版本
- 主机处理器架构
- 当前日期（提示：`string(TIMESTAMP ...)`）
- 检测是否存在 `/usr/bin/gcc` 或 `C:\MinGW\bin\gcc.exe`（提示：`if(EXISTS ...)`）
- 使用 `math(EXPR ...)` 计算 1 到 100 的和（用等差数列公式）

### 练习 3：message() 日志级别实验（挑战）

创建一个项目，系统性地测试每个 `message()` 模式在**项目模式**（`cmake -B build`）和**脚本模式**（`cmake -P`）下的行为差异。

具体要求：
1. 在 `CMakeLists.txt` 中使用所有 8 个不停止的级别 + `SEND_ERROR` + `FATAL_ERROR`（后两个用条件控制）
2. 用三个不同的 `--log-level` 值运行，记录哪些消息出现
3. 在脚本模式中同样测试，观察 `AUTHOR_WARNING` 在脚本模式下的行为（提示：脚本模式不是"项目"）
4. 制作一个表格，总结每个级别在什么条件下可见、是否停止执行


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **顶层 `CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(MyProject VERSION 1.0 LANGUAGES CXX)
>
> message(STATUS "Top-level PROJECT_SOURCE_DIR = ${PROJECT_SOURCE_DIR}")
>
> add_subdirectory(lib)
> add_subdirectory(src)
> ```
>
> **`lib/CMakeLists.txt`：**
> ```cmake
> message(STATUS "lib/ PROJECT_SOURCE_DIR = ${PROJECT_SOURCE_DIR}")
>
> add_library(string_utils)
> target_sources(string_utils PRIVATE string_utils.cpp)
> target_include_directories(string_utils
>     PUBLIC
>         ${CMAKE_CURRENT_SOURCE_DIR}
> )
> ```
>
> **`lib/string_utils.h`：**
> ```cpp
> #pragma once
> #include <string>
> std::string reverse(const std::string& input);
> ```
>
> **`lib/string_utils.cpp`：**
> ```cpp
> #include "string_utils.h"
> #include <algorithm>
>
> std::string reverse(const std::string& input) {
>     std::string result = input;
>     std::reverse(result.begin(), result.end());
>     return result;
> }
> ```
>
> **`src/CMakeLists.txt`：**
> ```cmake
> message(STATUS "src/ PROJECT_SOURCE_DIR = ${PROJECT_SOURCE_DIR}")
>
> add_executable(my_app)
> target_sources(my_app PRIVATE main.cpp)
> target_link_libraries(my_app PRIVATE string_utils)
> ```
>
> **`src/main.cpp`：**
> ```cpp
> #include "string_utils.h"
> #include <iostream>
>
> int main() {
>     std::string s = "Hello CMake!";
>     std::cout << "Original: " << s << "\n";
>     std::cout << "Reversed: " << reverse(s) << "\n";
>     return 0;
> }
> ```
>
> **关键点：** 各子目录中 `PROJECT_SOURCE_DIR` 的值相同（都指向顶层 `CMakeLists.txt` 所在目录），因为只有一个 `project()` 调用。`target_sources` 将源文件声明从 `add_library`/`add_executable` 中分离，使得子目录可以追加源文件。

> [!tip]- 练习 2 参考答案
> **`sysinfo.cmake`（用 `cmake -P sysinfo.cmake` 运行）：**
> ```cmake
> # sysinfo.cmake — 系统探测脚本
> cmake_minimum_required(VERSION 3.24)
>
> message("=== System Information ===")
> message("CMake version:    ${CMAKE_VERSION}")
> message("Host system:      ${CMAKE_HOST_SYSTEM_NAME}")
> message("Host version:     ${CMAKE_HOST_SYSTEM_VERSION}")
> message("Host processor:   ${CMAKE_HOST_SYSTEM_PROCESSOR}")
>
> # 当前日期
> string(TIMESTAMP TODAY "%Y-%m-%d %H:%M:%S")
> message("Current time:     ${TODAY}")
>
> # 检测 gcc
> if(WIN32)
>     if(EXISTS "C:/MinGW/bin/gcc.exe")
>         message("gcc found:        C:/MinGW/bin/gcc.exe")
>     else()
>         message("gcc:              not found")
>     endif()
> else()
>     if(EXISTS "/usr/bin/gcc")
>         message("gcc found:        /usr/bin/gcc")
>     else()
>         message("gcc:              not found")
>     endif()
> endif()
>
> # 等差数列求和 1+2+...+100 = n*(n+1)/2
> math(EXPR SUM "100 * (100 + 1) / 2")
> message("Sum 1..100:       ${SUM}")  # 5050
> ```
>
> **运行：** `cmake -P sysinfo.cmake`

> [!tip]- 练习 3 参考答案
> **`CMakeLists.txt`（项目模式测试）：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(LogLevelTest LANGUAGES NONE)
>
> message(TRACE        "1. TRACE message")
> message(DEBUG        "2. DEBUG message")
> message(VERBOSE      "3. VERBOSE message")
> message(STATUS       "4. STATUS message")
> message(DEPRECATION  "5. DEPRECATION message")
> message(NOTICE       "6. NOTICE message")
> message(AUTHOR_WARNING "7. AUTHOR_WARNING message")
> message(WARNING      "8. WARNING message")
>
> # 条件控制：只在 DEBUG_MODE=ON 时触发
> option(DEBUG_MODE "Enable error demo" OFF)
> if(DEBUG_MODE)
>     message(SEND_ERROR  "9. SEND_ERROR: config will fail after this file")
>     message(FATAL_ERROR "10. FATAL_ERROR: stops immediately")
> endif()
> ```
>
> **`script_mode.cmake`（脚本模式测试）：**
> ```cmake
> message(TRACE        "Script: TRACE")
> message(DEBUG        "Script: DEBUG")
> message(STATUS       "Script: STATUS")
> message(AUTHOR_WARNING "Script: AUTHOR_WARNING (non-project)")
> message(WARNING      "Script: WARNING")
> ```
>
> **运行方式：**
> ```bash
> # 项目模式，不同日志级别
> cmake -B build --log-level=TRACE
> cmake -B build --log-level=NOTICE
> cmake -B build --log-level=ERROR
>
> # 脚本模式
> cmake -P script_mode.cmake
> ```
>
> **结果表格：**
>
> | 级别 | `--log-level=TRACE` | `--log-level=NOTICE` | `--log-level=ERROR` | 脚本模式 | 停止执行？ |
> |------|:---:|:---:|:---:|:---:|:---:|
> | TRACE | ✓ | ✗ | ✗ | ✗ | 否 |
> | DEBUG | ✓ | ✗ | ✗ | ✗ | 否 |
> | VERBOSE | ✓ | ✓ | ✗ | ✗ | 否 |
> | STATUS | ✓ | ✓ | ✗ | ✓ | 否 |
> | DEPRECATION | ✓ | ✓ | 仅ERROR级别 | 仅ERROR | 否 |
> | NOTICE | ✓ | ✓ | ✗ | ✓ | 否 |
> | AUTHOR_WARNING | ✓ | ✓ | ✓ | ✓ (status only) | 否 |
> | WARNING | ✓ | ✓ | ✓ | ✓ | 否 |
> | SEND_ERROR | 显示为ERROR | 显示为ERROR | 显示为ERROR | 显示+阻止生成 | 阻止生成，不停止脚本 |
> | FATAL_ERROR | 立即终止 | 立即终止 | 立即终止 | 立即终止 | 立即停止 |
>
> **关键观察：** `AUTHOR_WARNING` 在脚本模式下表现为普通 STATUS 消息——因为脚本模式没有"作者"概念。`SEND_ERROR` 不停止当前脚本，但阻止生成阶段。`FATAL_ERROR` 在所有模式下都立即终止。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方文档：cmake_minimum_required](https://cmake.org/cmake/help/latest/command/cmake_minimum_required.html)
- [CMake 官方文档：project](https://cmake.org/cmake/help/latest/command/project.html)
- [CMake 官方文档：add_executable](https://cmake.org/cmake/help/latest/command/add_executable.html)
- [CMake 官方文档：add_library](https://cmake.org/cmake/help/latest/command/add_library.html)
- [CMake 官方文档：add_subdirectory](https://cmake.org/cmake/help/latest/command/add_subdirectory.html)
- [CMake 官方文档：target_sources](https://cmake.org/cmake/help/latest/command/target_sources.html)
- [CMake 官方文档：message](https://cmake.org/cmake/help/latest/command/message.html)
- [CMake 官方文档：set](https://cmake.org/cmake/help/latest/command/set.html)
- [CMake 官方文档：cmake -P 脚本模式](https://cmake.org/cmake/help/latest/manual/cmake.1.html#run-a-script)
- [CMake Policies 完整列表](https://cmake.org/cmake/help/latest/manual/cmake-policies.7.html)
- [Modern CMake 入门 — An Introduction to Modern CMake (Henry Schreiner)](https://cliutils.gitlab.io/modern-cmake/)
- [Effective Modern CMake (Manuel Binna)](https://gist.github.com/mbinna/c61dbb39bca0e4fb7d1f73b0d66a4fd1)

---

## 常见陷阱

### ❌ 忘记 cmake_minimum_required

**症状**：CMake 报错 `CMake Error: CMake can not determine linker language for target: ...` 或更模糊的错误。

**原因**：CMake 3.x 在没有 `cmake_minimum_required` 时以兼容模式运行，许多现代策略未启用。

**修复**：总是在 `CMakeLists.txt` 第一行（注释除外）添加：
```cmake
cmake_minimum_required(VERSION 3.24)
```

### ❌ 设置最低版本太低

**症状**：项目可以用 CMake 2.8 构建，但无法使用 `target_sources`、`target_include_directories` 等 Modern CMake 特性。

**原因**：`cmake_minimum_required(VERSION 2.8.12)` 保留了 2.8 时代的兼容行为。CMake 不会报错，但也不会启用 `CMP0020` 之后的策略。

**修复**：选择一个合理的现代版本（3.16+），即使这意味着部分老旧系统需要升级 CMake。
```cmake
cmake_minimum_required(VERSION 3.16)
```

### ❌ 在 add_executable 中放置所有源文件

**症状**：`add_executable(my_app main.cpp src/a.cpp src/b.cpp lib/c.cpp tests/d.cpp)` —— 单一长列表，难以维护。

**原因**：传统 CMake (2.x) 习惯将所有源文件写在一个命令中。

**修复**：使用 `target_sources()` 将源文件分散到相关子目录：
```cmake
add_executable(my_app)
target_sources(my_app PRIVATE main.cpp)
# 在子目录中追加:
target_sources(my_app PRIVATE a.cpp b.cpp)
```

### ❌ 混淆 include() 与 add_subdirectory()

**症状**：用 `include(subdir/CMakeLists.txt)` 引入子目录，导致变量污染和目标命名冲突。

**原因**：`include()` 在当前作用域执行，不创建新作用域。

**修复**：引入子项目用 `add_subdirectory()`，引入 CMake 模块用 `include()`。

```cmake
# ✅ 正确
add_subdirectory(lib)          # 子项目
include(cmake/helpers.cmake)   # 模块
# ❌ 错误
include(lib/CMakeLists.txt)    # 会把 lib 的变量泄露到当前作用域
```

### ❌ 在 project() 之前调用涉及编译器的命令

**症状**：`enable_language` 在 `project()` 之前调用时行为不确定。

**原因**：`project()` 负责初始化编译器。很多与编译相关的变量（`CMAKE_CXX_COMPILER` 等）在 `project()` 之后才被设置。

**修复**：`cmake_minimum_required` → `project()` → 其他一切。这是 CMake 的铁律。

### ❌ 子目录中修改变量期望影响父目录

**症状**：在子目录 `set(MY_VAR "new_value")`，回到父目录后 `MY_VAR` 仍是旧值。

**原因**：`add_subdirectory()` 创建新作用域，变量修改不传回。

**修复**：使用 `set(MY_VAR "new_value" PARENT_SCOPE)` 显式传回。

```cmake
# lib/CMakeLists.txt
set(MY_RESULT "lib_built_successfully" PARENT_SCOPE)
```

### ❌ 假设 ${VAR} 未定义时会报错

**症状**：构建行为异常，没有错误消息，但路径为 `/include`（少了一段）或变量为空。

**原因**：`${UNDEFINED_VAR}` 展开为空字符串，CMake 不报错。

**修复**：使用 `if(DEFINED VAR)` 检查。打印变量值时用引号包裹，让空值可见：
```cmake
message(STATUS "VAR = '${VAR}'")          # 空值显示为 ''
message(STATUS "VAR defined: ${DEFINED}") # 使用 if(DEFINED VAR)
```

### ❌ 高估 SEND_ERROR 的阻断能力

**症状**：写了 `message(SEND_ERROR ...)` 以为构建会立即失败，但 CMake 继续执行后续命令。

**原因**：`SEND_ERROR` 阻止的是**生成阶段**，不阻止当前脚本的继续执行。

**修复**：如果需要立即终止，使用 `message(FATAL_ERROR ...)`。如果需要收集所有错误，使用 `SEND_ERROR` 但知道后续代码仍会运行——做好防护。
