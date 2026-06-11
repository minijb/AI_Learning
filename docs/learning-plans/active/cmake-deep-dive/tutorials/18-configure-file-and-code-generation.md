---
title: "configure_file 与代码生成"
updated: 2026-06-10
tags: [cmake, code-generation, configure-file, cmakedefine, build-system]
---

# `configure_file` 与代码生成

> 预计耗时: 45min
> 前置: [[16-custom-commands-and-generated-files]]
> 深度等级: 第四阶段——深入

---

## 概念

`configure_file()` 是 CMake 中最古老的代码生成机制之一。它的核心工作流是：

```
模板文件 (.h.in / .c.in)  +  CMake 变量
         ↓
    configure_file()
         ↓
输出文件 (替换后的 .h / .c)
```

在**配置阶段**（configure time），CMake 读取模板文件，将其中的 CMake 变量占位符替换为实际值，然后把结果写入输出文件。这个输出文件随后可以被 `#include` 或编译进你的 target。

为什么需要 configure_file? 两个经典场景：

1. **将 CMake 变量嵌入 C/C++ 代码** — 比如项目版本号、构建时间、Git commit hash
2. **条件编译开关** — 检测到的平台特性（`HAVE_PTHREADS`、`HAVE_STD_FILESYSTEM` 等）通过 `#cmakedefine` 变成 C 预处理器宏

---

## `configure_file()` 深度剖析

### 完整签名

```cmake
configure_file(<input> <output>
               [COPYONLY] [ESCAPE_QUOTES] [@ONLY]
               [NEWLINE_STYLE [UNIX|DOS|WIN32|LF|CRLF] ]
               [NO_SOURCE_PERMISSIONS] [USE_SOURCE_PERMISSIONS]
               [FILE_PERMISSIONS <permissions>...]
               [DIRECTORY_PERMISSIONS <permissions>...]
               [TARGET <target>]
)
```

### 核心参数详解

#### INPUT 与 OUTPUT

- **`<input>`**: 模板文件路径。如果是相对路径，相对于 `CMAKE_CURRENT_SOURCE_DIR`
- **`<output>`**: 输出文件路径。如果是相对路径，相对于 `CMAKE_CURRENT_BINARY_DIR`

> [!tip] 输出路径惯例
> 绝不要把输出写在 source dir——那是生成的文件，不属于版本控制。输出路径始终指向 binary dir。

```cmake
# 典型用法
configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/version.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/version.h
)
```

#### COPYONLY

不做任何变量替换，单纯拷贝文件。当模板中的 `${...}` 是字面内容（比如 shell 脚本中的变量引用）时使用。

```cmake
# 拷贝文件，不展开任何变量
configure_file(script.sh.in script.sh COPYONLY)
```

#### ESCAPE_QUOTES

将替换值中的双引号 `"` 转义为 `\"`。在生成 C 字符串字面量时有用：

```cmake
# CMakeLists.txt
set(PROJECT_DESCRIPTION "My "Awesome" Project")

# config.h.in
#define PROJECT_DESC "@PROJECT_DESCRIPTION@"

# 不使用 ESCAPE_QUOTES → 输出: #define PROJECT_DESC "My "Awesome" Project"  (语法错误)
# 使用 ESCAPE_QUOTES   → 输出: #define PROJECT_DESC "My \"Awesome\" Project"  (正确)
```

#### @ONLY

**只替换 `@VAR@` 形式的占位符，不替换 `${VAR}` 形式。**这是非常重要的参数，后面会详细解释。

#### NEWLINE_STYLE

控制输出文件的换行符风格：

- `UNIX` / `LF` — `\n` (Linux/macOS)
- `WIN32` / `DOS` / `CRLF` — `\r\n` (Windows)

```cmake
configure_file(version.h.in version.h NEWLINE_STYLE LF)
```

---

## 变量替换语法：`@VAR@` vs `${VAR}`

在模板文件中，CMake 支持两种占位符语法：

| 语法 | 示例 | 替换内容 |
|------|------|---------|
| `@VAR@` | `@PROJECT_VERSION@` | 变量 `PROJECT_VERSION` 的值 |
| `${VAR}` | `${PROJECT_VERSION}` | 变量 `PROJECT_VERSION` 的值 |

### 为什么需要两种？

**C/C++ 代码本身就在使用 `{}` 和 `()`。** 如果你的模板文件是 `.h.in` 或 `.c.in`，其中可能包含这样的代码：

```c
// 这是合法的 C 代码——字符串化宏
#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)

// 这也行—— brace initialization
int arr[] = {1, 2, 3};
std::vector<int> v = {1, 2, 3};
```

如果模板中同时出现 `${CMAKE_VAR}` 和 `{1, 2, 3}`，CMake 不会混淆——`${}` 必须是合法的变量名。但为了避免任何潜在冲突，**推荐在 C/C++ 模板中使用 `@ONLY` 模式**，这样只有 `@VAR@` 被替换，`${...}` 原样保留。

### @ONLY 标志

```cmake
configure_file(config.h.in config.h @ONLY)
```

模板 `config.h.in` 中：

```c
// @ONLY 模式下:
#define VERSION "@PROJECT_VERSION@"         // ✅ 被替换
#define VERSION "${PROJECT_VERSION}"         // ❌ 不被替换，输出就是 ${PROJECT_VERSION}

// 不使用 @ONLY：
#define VERSION "@PROJECT_VERSION@"         // ✅ 被替换
#define VERSION "${PROJECT_VERSION}"         // ✅ 也被替换
```

> [!warning] 何时必须用 @ONLY
> 当模板文件中包含 `${}` 作为 C/C++ 代码的字面内容（比如字符串插值、shell 变量引用、或模板引擎语法）时，必须用 `@ONLY` 防止 CMake 误替换。一个典型场景：生成包含 JavaScript 模板字面量的文件。

---

## `#cmakedefine` — 定义 C 预处理器宏

这是 `configure_file` 最强大的功能之一。它在模板文件中以 C 预处理指令的形式出现，但行为由 CMake 变量控制。

### `#cmakedefine VAR`

如果 CMake 变量 `VAR` 为真值（非空、非 `0`、非 `OFF`、非 `FALSE`、非 `NO`、非空字符串），则输出 `#define VAR`；否则输出 `/* #undef VAR */`。

```c
// config.h.in 模板
#cmakedefine HAVE_UNISTD_H
#cmakedefine ENABLE_LOGGING
```

```cmake
# CMakeLists.txt
set(HAVE_UNISTD_H ON)    # 为真
set(ENABLE_LOGGING OFF)  # 为假
```

输出 `config.h`：

```c
#define HAVE_UNISTD_H
/* #undef ENABLE_LOGGING */
```

### `#cmakedefine VAR value`

如果 `VAR` 为真，输出 `#define VAR value`（value 是字面文本，不做变量展开）：

```c
// config.h.in
#cmakedefine MAX_CONNECTIONS @MAX_CONNS@
```

```cmake
set(MAX_CONNS 1024)
```

```c
// 输出
#define MAX_CONNECTIONS 1024
```

### `#cmakedefine01 VAR`

无论 `VAR` 为真还是为假，都输出一个 `#define`：真 → `1`，假 → `0`。**总是定义，从不 undef。**

```c
// config.h.in
#cmakedefine01 HAVE_PTHREADS
#cmakedefine01 USE_OPENMP
```

```cmake
set(HAVE_PTHREADS ON)
set(USE_OPENMP OFF)
```

输出：

```c
#define HAVE_PTHREADS 1
#define USE_OPENMP 0
```

> [!tip] cmakedefine01 的优势
> `#cmakedefine01` 确保宏总是被定义。C 代码中可以直接使用 `#if HAVE_PTHREADS` 而不用担心 `#ifdef` vs `#if` 的区别。如果使用 `#cmakedefine`，假值时输出 `/* #undef */`，只能用 `#ifdef` 检测；而 `#cmakedefine01` 输出 `0`，可以用 `#if` 检测，与 `bool` 语义一致。

### 三种形式速查

| 模板写法 | `VAR=ON` 的输出 | `VAR=OFF` 的输出 |
|----------|----------------|-------------------|
| `#cmakedefine VAR` | `#define VAR` | `/* #undef VAR */` |
| `#cmakedefine VAR val` | `#define VAR val` | `/* #undef VAR */` |
| `#cmakedefine01 VAR` | `#define VAR 1` | `#define VAR 0` |

---

## 常见模式

### 模式 1: `version.h.in` — 版本号嵌入

```c
// version.h.in
#ifndef MYLIB_VERSION_H
#define MYLIB_VERSION_H

#define MYLIB_VERSION_MAJOR @PROJECT_VERSION_MAJOR@
#define MYLIB_VERSION_MINOR @PROJECT_VERSION_MINOR@
#define MYLIB_VERSION_PATCH @PROJECT_VERSION_PATCH@
#define MYLIB_VERSION_TWEAK @PROJECT_VERSION_TWEAK@

#define MYLIB_VERSION_STRING "@PROJECT_VERSION@"

#endif // MYLIB_VERSION_H
```

```cmake
# CMakeLists.txt
project(MyLib VERSION 2.7.3.1)
configure_file(version.h.in ${CMAKE_CURRENT_BINARY_DIR}/version.h @ONLY)
```

### 模式 2: `config.h.in` — 平台检测结果

```c
// config.h.in
#ifndef MYLIB_CONFIG_H
#define MYLIB_CONFIG_H

// 头文件可用性
#cmakedefine HAVE_UNISTD_H
#cmakedefine HAVE_STDINT_H
#cmakedefine HAVE_SYS_TYPES_H

// 标准库特性
#cmakedefine01 HAVE_STD_FILESYSTEM
#cmakedefine01 HAVE_STD_OPTIONAL
#cmakedefine01 HAVE_STD_VARIANT

// 编译选项
#cmakedefine ENABLE_ASSERT
#cmakedefine01 USE_OPENMP
#cmakedefine MAX_BUFFER_SIZE @BUFFER_SIZE@

// 平台标识
#define MYLIB_PLATFORM "@CMAKE_SYSTEM_NAME@"
#define MYLIB_COMPILER "@CMAKE_CXX_COMPILER_ID@"

#endif // MYLIB_CONFIG_H
```

### 模式 3: `options.h.in` — 用户可配置开关

```c
// options.h.in
#ifndef MYLIB_OPTIONS_H
#define MYLIB_OPTIONS_H

#cmakedefine01 MYLIB_USE_SSE4_2
#cmakedefine01 MYLIB_USE_AVX2
#cmakedefine01 MYLIB_ENABLE_PROFILING
#cmakedefine MYLIB_DEFAULT_BACKEND "@MYLIB_BACKEND@"

#endif // MYLIB_OPTIONS_H
```

```cmake
# CMakeLists.txt
option(MYLIB_USE_SSE4_2 "Enable SSE4.2 optimizations" ON)
option(MYLIB_USE_AVX2 "Enable AVX2 optimizations" OFF)
option(MYLIB_ENABLE_PROFILING "Enable profiling" OFF)
set(MYLIB_BACKEND "posix" CACHE STRING "Default backend")
configure_file(options.h.in ${CMAKE_CURRENT_BINARY_DIR}/options.h @ONLY)
```

---

## 生成器表达式在 `configure_file` 中

`configure_file` **运行在配置阶段**，而生成器表达式（generator expressions）通常在生成阶段求值。但有一个重要例外：

**`configure_file` 的 `INPUT` 和 `OUTPUT` 参数支持生成器表达式。**

```cmake
# 根据配置输出不同文件
configure_file(
    debug_config.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>_config.h
)
```

在 Debug 配置下输出 `Debug_config.h`，在 Release 下输出 `Release_config.h`。

> [!warning] 限制
> 模板**内容**中的 CMake 变量（`@VAR@`、`${VAR}`）在配置阶段替换，不能使用生成器表达式。如果需要生成阶段求值的内容，使用 `file(GENERATE)`。

---

## `configure_file` vs `file(GENERATE)` vs `add_custom_command`

这三种机制都能生成文件，但运行时机和适用场景完全不同。

| 特性 | `configure_file` | `file(GENERATE)` | `add_custom_command` |
|------|-----------------|-------------------|---------------------|
| 运行时机 | 配置阶段 | 生成阶段 | 构建阶段 |
| 变量替换 | `@VAR@` / `${VAR}` | 生成器表达式 `$<...>` | 无（需外部脚本） |
| `#cmakedefine` | 支持 | 不支持 | 不支持 |
| 多配置感知 | 否（需生成器表达式辅助） | 支持 `$<CONFIG>` | 支持 |
| 典型用途 | 嵌入版本号、配置开关 | 配置相关的文件内容 | 代码生成器、协议编译 |

### 运行时机示意

```
CMake 执行流程:
─────────────────────────────────────────────────────────────────
  cmake -B build
      │
      ├── 配置阶段 (configure time)        ← configure_file 运行
      │   ├── 读取 CMakeLists.txt
      │   ├── 执行命令 (message, set, find_package, ...)
      │   └── configure_file() 执行并生成输出
      │
      ├── 生成阶段 (generate time)          ← file(GENERATE) 运行
      │   ├── 求值生成器表达式
      │   ├── 生成构建系统文件 (Makefile, ninja.build, ...)
      │   └── file(GENERATE) 执行并生成输出
      │
      └── 构建阶段 (build time)             ← add_custom_command 运行
          ├── 编译源文件
          ├── 链接目标
          └── 执行 add_custom_command (代码生成器、脚本)
─────────────────────────────────────────────────────────────────
```

### 选择决策树

```
你需要生成文件吗？
├─ 内容依赖 CMake 变量的值（版本号、选项开关）
│   └─ → configure_file()  (配置阶段，最简单)
├─ 内容依赖构建配置 (Debug/Release)
│   └─ → file(GENERATE)  (生成阶段，支持 $<CONFIG>)
├─ 内容由外部工具/脚本产生
│   └─ → add_custom_command()  (构建阶段，完全自由)
└─ 需要 #cmakedefine 语义
    └─ → configure_file()  (唯一支持)
```

---

## 平台检测：`CheckCXXSourceCompiles` 等

CMake 的 `CheckCXXSourceCompiles`、`CheckIncludeFileCXX`、`CheckCXXSymbolExists` 等模块在配置阶段探测编译器/平台能力，结果通常写入 `configure_file` 生成的 config header。

### 常用检测模块

| 模块 | 功能 |
|------|------|
| `CheckIncludeFileCXX` | 检测 C++ 头文件是否可用 |
| `CheckCXXSourceCompiles` | 检测一段 C++ 代码能否编译 |
| `CheckCXXSourceRuns` | 检测一段 C++ 代码能否编译并运行（交叉编译时需特殊处理） |
| `CheckCXXSymbolExists` | 检测符号（函数/变量）是否存在 |
| `CheckTypeSize` | 检测类型大小 |
| `CheckStructHasMember` | 检测结构体是否有某成员 |

### 典型工作流

```cmake
include(CheckIncludeFileCXX)
include(CheckCXXSourceCompiles)
include(CheckCXXSymbolExists)

# 检测头文件
check_include_file_cxx("filesystem" HAVE_STD_FILESYSTEM_HEADER)
check_include_file_cxx("optional"   HAVE_STD_OPTIONAL_HEADER)

# 检测代码能否编译
check_cxx_source_compiles("
    #include <type_traits>
    static_assert(std::is_trivially_copyable_v<int>, \"\");
    int main() { return 0; }
" HAVE_IS_TRIVIALLY_COPYABLE)

# 检测符号
check_cxx_symbol_exists(strerror_r "string.h" HAVE_STRERROR_R)

# 生成 config.h
configure_file(config.h.in ${CMAKE_CURRENT_BINARY_DIR}/config.h)
```

### 模板设计

```c
// config.h.in
#cmakedefine01 HAVE_STD_FILESYSTEM_HEADER
#cmakedefine01 HAVE_STD_OPTIONAL_HEADER
#cmakedefine01 HAVE_IS_TRIVIALLY_COPYABLE
#cmakedefine01 HAVE_STRERROR_R
```

---

## 编写既是有效 C 又是有效模板的 `.h.in` 文件

模板文件需要同时满足两个约束：

1. **作为 CMake 模板时**：`@VAR@` / `${VAR}` 和 `#cmakedefine` 能被正确解析
2. **作为 C 头文件时**：IDE 的语法高亮、自动补全、静态分析工具能正常工作

### 最佳实践

**1. 使用 `@ONLY` + `@VAR@` 避免 `${}` 冲突**

```c
// ✅ 好：@ONLY 模式，C 代码中的 {} 永远不会冲突
#define VERSION_MAJOR @PROJECT_VERSION_MAJOR@
int arr[] = {1, 2, 3};  // 安全，CMake 不碰 ${}
```

**2. 保留有效的 C 语法作为占位符**

```c
// ✅ 好：即使未被替换，仍然是可编译的 C 代码（虽然无意义）
#define VERSION_MAJOR 0    // 0 作为默认占位符
#define VERSION_STRING "0.0.0"
```

**3. `#cmakedefine` 用注释包围，使得未展开时也是有效 C**

```c
// ✅ 好：未被替换时 => /* #undef HAVE_FOO */，是 C 注释，无害
#cmakedefine HAVE_FOO
```

**4. 使用 include guard 保护头文件**

```c
// ✅ 好：标准的 include guard
#ifndef MYLIB_CONFIG_H
#define MYLIB_CONFIG_H
// ... 模板内容 ...
#endif
```

**5. 对于可选值，提供合理的 fallback**

```c
// ✅ 好：未被定义时有 fallback
#ifndef MAX_BUFFER_SIZE
#define MAX_BUFFER_SIZE 4096
#endif
```

---

## `NEWLINE_STYLE` — 换行符控制

CMake 在输出文件时默认保持模板文件的换行风格。通过 `NEWLINE_STYLE` 可以强制覆盖：

```cmake
# 始终输出 LF 换行（Linux/macOS 标准）
configure_file(version.h.in version.h NEWLINE_STYLE LF)

# 始终输出 CRLF 换行（Windows 标准）
configure_file(version.h.in version.h NEWLINE_STYLE CRLF)
```

> [!warning] 换行符不匹配的陷阱
> 在 Windows 上使用 Git 时，如果 `core.autocrlf` 设置为 `true`，模板文件（`.h.in`）可能被自动转换为 CRLF。但生成的 `.h` 文件是 binary dir 中的构建产物，不受 Git 换行策略影响。如果某些工具（如 Unix 交叉编译器）对 CRLF 敏感，使用 `NEWLINE_STYLE LF` 确保输出始终是 LF。

---

## 多次 `configure_file` 调用

一个项目中可以有任意多次 `configure_file` 调用，生成多个不同的输出文件：

```cmake
# 生成版本信息
configure_file(version.h.in   ${CMAKE_CURRENT_BINARY_DIR}/gen/version.h   @ONLY)

# 生成平台配置
configure_file(config.h.in    ${CMAKE_CURRENT_BINARY_DIR}/gen/config.h    @ONLY)

# 生成用户选项
configure_file(options.h.in   ${CMAKE_CURRENT_BINARY_DIR}/gen/options.h   @ONLY)

# 生成构建信息（时间戳、Git hash）
configure_file(build_info.h.in ${CMAKE_CURRENT_BINARY_DIR}/gen/build_info.h @ONLY)

# 统一 include 路径
target_include_directories(mylib PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/gen)
```

> [!tip] 输出目录组织
> 将多个 configure_file 的输出放在一个统一的 `gen/` 子目录中，然后只添加这一个路径到 include directories，保持整洁。

---

## 代码示例 (可运行)

### 示例 1: 生成 `version.h`

完整的 CMake 项目，将项目版本号嵌入到头文件中。

**目录结构:**

```
example1/
├── CMakeLists.txt
├── version.h.in
└── main.cpp
```

**CMakeLists.txt:**

```cmake
cmake_minimum_required(VERSION 3.24)
project(VersionDemo VERSION 3.7.2.1
        DESCRIPTION "A version embedding demo"
        LANGUAGES CXX)

# 生成版本头文件
configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/version.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/version.h
    @ONLY
)

add_executable(version_demo main.cpp)
target_include_directories(version_demo PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
```

**version.h.in:**

```c
#ifndef VERSION_DEMO_VERSION_H
#define VERSION_DEMO_VERSION_H

#define VERSION_MAJOR @PROJECT_VERSION_MAJOR@
#define VERSION_MINOR @PROJECT_VERSION_MINOR@
#define VERSION_PATCH @PROJECT_VERSION_PATCH@
#define VERSION_TWEAK @PROJECT_VERSION_TWEAK@

#define VERSION_STRING "@PROJECT_VERSION@"
#define PROJECT_NAME "@CMAKE_PROJECT_NAME@"
#define PROJECT_DESCRIPTION "@CMAKE_PROJECT_DESCRIPTION@"

#endif // VERSION_DEMO_VERSION_H
```

**main.cpp:**

```cpp
#include <iostream>
#include "version.h"

int main() {
    std::cout << "Project: " << PROJECT_NAME << std::endl;
    std::cout << "Description: " << PROJECT_DESCRIPTION << std::endl;
    std::cout << "Version: " << VERSION_STRING << std::endl;
    std::cout << "Major: " << VERSION_MAJOR << std::endl;
    std::cout << "Minor: " << VERSION_MINOR << std::endl;
    std::cout << "Patch: " << VERSION_PATCH << std::endl;
    std::cout << "Tweak: " << VERSION_TWEAK << std::endl;
    return 0;
}
```

**运行:**

```bash
cmake -B build
cmake --build build
./build/version_demo
```

**预期输出:**

```
Project: VersionDemo
Description: A version embedding demo
Version: 3.7.2.1
Major: 3
Minor: 7
Patch: 2
Tweak: 1
```

---

### 示例 2: 生成 `config.h` 带平台检测

使用 `#cmakedefine` 和 `#cmakedefine01` 进行特征检测。

**目录结构:**

```
example2/
├── CMakeLists.txt
├── config.h.in
└── main.cpp
```

**CMakeLists.txt:**

```cmake
cmake_minimum_required(VERSION 3.24)
project(FeatureDetectDemo VERSION 1.0.0 LANGUAGES CXX)

include(CheckIncludeFileCXX)
include(CheckCXXSourceCompiles)
include(CheckCXXSymbolExists)
include(CheckTypeSize)

# -- 检测头文件 --
check_include_file_cxx("filesystem"  HAVE_STD_FILESYSTEM_HEADER)
check_include_file_cxx("optional"    HAVE_STD_OPTIONAL_HEADER)
check_include_file_cxx("variant"     HAVE_STD_VARIANT_HEADER)
check_include_file_cxx("unistd.h"    HAVE_UNISTD_H)
check_include_file_cxx("sched.h"     HAVE_SCHED_H)

# -- 检测代码能否编译 --
check_cxx_source_compiles("
    #include <type_traits>
    static_assert(std::is_trivially_copyable_v<int>, \"not trivially copyable\");
    int main() { return 0; }
" HAVE_IS_TRIVIALLY_COPYABLE)

check_cxx_source_compiles("
    #include <filesystem>
    int main() {
        auto p = std::filesystem::path{\"/tmp\"};
        return 0;
    }
" HAVE_STD_FILESYSTEM)

# -- 检测符号 --
check_cxx_symbol_exists(clock_gettime "time.h" HAVE_CLOCK_GETTIME)

# -- 检测类型大小 --
check_type_size("void*" SIZEOF_VOID_P)

# -- 用户选项 --
option(ENABLE_LOGGING "Enable detailed logging" ON)

# 生成 config.h
configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/config.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/config.h
    @ONLY
)

add_executable(feature_demo main.cpp)
target_include_directories(feature_demo PRIVATE ${CMAKE_CURRENT_BINARY_DIR})

# C++17 是必须的 (filesystem)
target_compile_features(feature_demo PRIVATE cxx_std_17)
```

**config.h.in:**

```c
#ifndef FEATURE_DEMO_CONFIG_H
#define FEATURE_DEMO_CONFIG_H

// ==========================================
// 头文件可用性
// ==========================================
#cmakedefine HAVE_STD_FILESYSTEM_HEADER
#cmakedefine HAVE_STD_OPTIONAL_HEADER
#cmakedefine HAVE_STD_VARIANT_HEADER
#cmakedefine HAVE_UNISTD_H
#cmakedefine HAVE_SCHED_H

// ==========================================
// 功能可用性 (@cmakedefine01: 总是 0 或 1)
// ==========================================
#cmakedefine01 HAVE_STD_FILESYSTEM
#cmakedefine01 HAVE_IS_TRIVIALLY_COPYABLE
#cmakedefine01 HAVE_CLOCK_GETTIME

// ==========================================
// 编译期常量
// ==========================================
#define SIZEOF_VOID_P @SIZEOF_VOID_P@

// ==========================================
// 编译开关
// ==========================================
#cmakedefine ENABLE_LOGGING

// ==========================================
// 平台标识
// ==========================================
#define BUILD_PLATFORM "@CMAKE_SYSTEM_NAME@"
#define BUILD_COMPILER "@CMAKE_CXX_COMPILER_ID@"
#define BUILD_COMPILER_VERSION "@CMAKE_CXX_COMPILER_VERSION@"

#endif // FEATURE_DEMO_CONFIG_H
```

**main.cpp:**

```cpp
#include <iostream>
#include "config.h"

int main() {
    std::cout << "=== Feature Detection Report ===" << std::endl;
    std::cout << "Platform:    " << BUILD_PLATFORM << std::endl;
    std::cout << "Compiler:    " << BUILD_COMPILER << " "
              << BUILD_COMPILER_VERSION << std::endl;
    std::cout << std::endl;

    std::cout << "--- Headers ---" << std::endl;
#ifdef HAVE_STD_FILESYSTEM_HEADER
    std::cout << "  <filesystem> : YES" << std::endl;
#else
    std::cout << "  <filesystem> : NO" << std::endl;
#endif
#ifdef HAVE_STD_OPTIONAL_HEADER
    std::cout << "  <optional>   : YES" << std::endl;
#else
    std::cout << "  <optional>   : NO" << std::endl;
#endif
#ifdef HAVE_STD_VARIANT_HEADER
    std::cout << "  <variant>    : YES" << std::endl;
#else
    std::cout << "  <variant>    : NO" << std::endl;
#endif
#ifdef HAVE_UNISTD_H
    std::cout << "  <unistd.h>   : YES" << std::endl;
#else
    std::cout << "  <unistd.h>   : NO" << std::endl;
#endif

    std::cout << std::endl;
    std::cout << "--- Features (01 = always defined) ---" << std::endl;
#if HAVE_STD_FILESYSTEM
    std::cout << "  std::filesystem      : YES" << std::endl;
#else
    std::cout << "  std::filesystem      : NO" << std::endl;
#endif
#if HAVE_IS_TRIVIALLY_COPYABLE
    std::cout << "  is_trivially_copyable: YES" << std::endl;
#else
    std::cout << "  is_trivially_copyable: NO" << std::endl;
#endif
#if HAVE_CLOCK_GETTIME
    std::cout << "  clock_gettime        : YES" << std::endl;
#else
    std::cout << "  clock_gettime        : NO" << std::endl;
#endif

    std::cout << std::endl;
    std::cout << "--- Constants ---" << std::endl;
    std::cout << "  sizeof(void*) : " << SIZEOF_VOID_P << std::endl;

    std::cout << std::endl;
    std::cout << "--- Options ---" << std::endl;
#ifdef ENABLE_LOGGING
    std::cout << "  Logging       : ENABLED" << std::endl;
#else
    std::cout << "  Logging       : DISABLED" << std::endl;
#endif

    return 0;
}
```

**运行:**

```bash
cmake -B build
cmake --build build
./build/feature_demo
```

---

### 示例 3: 比较三种代码生成方式的执行时机

此示例用 `message()` 来证明 `configure_file`、`file(GENERATE)` 和 `add_custom_command` 的运行时机差异。

**目录结构:**

```
example3/
├── CMakeLists.txt
├── template.h.in
└── main.cpp
```

**CMakeLists.txt:**

```cmake
cmake_minimum_required(VERSION 3.24)
project(TimingDemo VERSION 1.0.0 LANGUAGES CXX)

# ============================================================
# 1. configure_file — 配置阶段运行
# ============================================================
message(STATUS "[configure time] About to call configure_file...")
configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/template.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/gen_configure.h
    @ONLY
)
message(STATUS "[configure time] configure_file done. gen_configure.h created.")

# ============================================================
# 2. file(GENERATE) — 生成阶段运行
# ============================================================
# 注意: message() 中的内容不能被 file(GENERATE) 延迟执行，
# 所以我们用 file(GENERATE) 生成一个包含构建信息的头文件。
set(DESCRIPTION_TEXT "Generated at generate time")
file(GENERATE
    OUTPUT  ${CMAKE_CURRENT_BINARY_DIR}/gen_generate.h
    CONTENT "#pragma once\n#define GEN_TIME_DESC \"${DESCRIPTION_TEXT}\"\n#define CONFIG \"$<CONFIG>\"\n"
)
message(STATUS "[configure time] file(GENERATE) registered (runs at generate time).")

# ============================================================
# 3. add_custom_command — 构建阶段运行
# ============================================================
# 生成一个包含构建时间戳的头文件
add_custom_command(
    OUTPUT  ${CMAKE_CURRENT_BINARY_DIR}/gen_buildtime.h
    COMMAND ${CMAKE_COMMAND} -E echo "#pragma once" > ${CMAKE_CURRENT_BINARY_DIR}/gen_buildtime.h
    COMMAND ${CMAKE_COMMAND} -E echo "#define BUILD_TIMESTAMP \"generated during build\"" >> ${CMAKE_CURRENT_BINARY_DIR}/gen_buildtime.h
    COMMENT "[build time] Generating gen_buildtime.h via add_custom_command"
)
message(STATUS "[configure time] add_custom_command registered (runs at build time).")

# ============================================================
# 自定义 target 确保 add_custom_command 被触发
# ============================================================
add_custom_target(gen_buildtime_header DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/gen_buildtime.h)

# ============================================================
# 可执行文件
# ============================================================
add_executable(timing_demo main.cpp
    ${CMAKE_CURRENT_BINARY_DIR}/gen_buildtime.h
)
add_dependencies(timing_demo gen_buildtime_header)
target_include_directories(timing_demo PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
```

**template.h.in:**

```c
#pragma once
#define CONFIG_TIME_DESC "Generated at configure time by configure_file"
```

**main.cpp:**

```cpp
#include <iostream>

// 配置阶段生成
#include "gen_configure.h"

// 生成阶段生成
#include "gen_generate.h"

// 构建阶段生成
#include "gen_buildtime.h"

int main() {
    std::cout << "=== Code Generation Timing Demo ===" << std::endl;
    std::cout << "1. configure_file  : " << CONFIG_TIME_DESC << std::endl;
    std::cout << "2. file(GENERATE)  : " << GEN_TIME_DESC << std::endl;
    std::cout << "   Build config    : " << CONFIG << std::endl;
    std::cout << "3. custom_command  : " << BUILD_TIMESTAMP << std::endl;
    return 0;
}
```

**运行:**

```bash
# 配置阶段 — 观察 configure_file 和 file(GENERATE) 注册信息
cmake -B build

# 构建阶段 — 观察 add_custom_command 的执行
cmake --build build

# 运行
./build/timing_demo
```

**观察 CMake 输出中不同阶段的 message:**

```
-- [configure time] About to call configure_file...
-- [configure time] configure_file done. gen_configure.h created.
-- [configure time] file(GENERATE) registered (runs at generate time).
-- [configure time] add_custom_command registered (runs at build time).
-- Configuring done
-- Generating done           ← file(GENERATE) 在这里执行
-- Build files have been written to: .../build
[build time] Generating gen_buildtime.h via add_custom_command   ← 构建时执行
```

---

## 练习

### 练习 1: 创建项目版本头文件

创建一个 CMake 项目，将 `PROJECT_VERSION_MAJOR`、`PROJECT_VERSION_MINOR`、`PROJECT_VERSION_PATCH`、`PROJECT_VERSION_TWEAK` 嵌入到头文件中，并在 main 中打印格式化的版本字符串 `"vMAJOR.MINOR.PATCH (build TWEAK)"`。

**要求:**

- 使用 `@ONLY` 模式
- 使用 `project()` 设置版本号为 `2.1.4.8`
- 头文件包含 version string、各个 component 的宏、以及 project name

> [!tip]- 参考方案
> ```cmake
> # CMakeLists.txt
> cmake_minimum_required(VERSION 3.24)
> project(VersionExercise VERSION 2.1.4.8 LANGUAGES CXX)
>
> configure_file(version.h.in ${CMAKE_CURRENT_BINARY_DIR}/version.h @ONLY)
> add_executable(ver main.cpp)
> target_include_directories(ver PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
> ```
>
> ```c
> // version.h.in
> #ifndef VERSION_H
> #define VERSION_H
> #define VER_MAJOR @PROJECT_VERSION_MAJOR@
> #define VER_MINOR @PROJECT_VERSION_MINOR@
> #define VER_PATCH @PROJECT_VERSION_PATCH@
> #define VER_TWEAK @PROJECT_VERSION_TWEAK@
> #define VER_STRING "@PROJECT_VERSION@"
> #define VER_NAME "@PROJECT_NAME@"
> #endif
> ```
>
> ```cpp
> // main.cpp
> #include <iostream>
> #include "version.h"
>
> int main() {
>     std::cout << VER_NAME << " v" << VER_MAJOR << "."
>               << VER_MINOR << "." << VER_PATCH
>               << " (build " << VER_TWEAK << ")" << std::endl;
>     return 0;
> }
> ```

### 练习 2: 编写包含平台检测的 `config.h.in`

编写一个 `config.h.in` 模板，检测以下内容并使用合适的 `#cmakedefine` / `#cmakedefine01`：

1. `HAVE_UNISTD_H` — 使用 `#cmakedefine`（传统风格，兼容 autotools）
2. `HAVE_STD_THREAD` — 使用 `#cmakedefine01`（bool 语义）
3. `ENABLE_DEBUG_TRACE` — 使用 `#cmakedefine`（可选开关）
4. 嵌入 `CMAKE_SYSTEM_PROCESSOR` 作为字符串宏
5. 定义一个 `DEFAULT_THREAD_COUNT` 宏，值来自 CMake 变量 `DEFAULT_THREADS`（默认 4）

**要求:**

- 使用 `@ONLY` 模式
- include guard 命名为 `MYAPP_CONFIG_H`
- 在 `CMakeLists.txt` 中设置所有变量并调用 `configure_file`

> [!tip]- 参考方案
> ```c
> // config.h.in
> #ifndef MYAPP_CONFIG_H
> #define MYAPP_CONFIG_H
>
> // 头文件可用性
> #cmakedefine HAVE_UNISTD_H
>
> // 功能可用性 (0/1)
> #cmakedefine01 HAVE_STD_THREAD
>
> // 编译开关
> #cmakedefine ENABLE_DEBUG_TRACE
>
> // 平台信息
> #define MYAPP_ARCH "@CMAKE_SYSTEM_PROCESSOR@"
>
> // 配置常量
> #define DEFAULT_THREAD_COUNT @DEFAULT_THREADS@
>
> #endif // MYAPP_CONFIG_H
> ```
>
> ```cmake
> # CMakeLists.txt
> cmake_minimum_required(VERSION 3.24)
> project(ConfigExercise LANGUAGES CXX)
>
> include(CheckIncludeFileCXX)
> include(CheckCXXSourceCompiles)
>
> check_include_file_cxx("unistd.h" HAVE_UNISTD_H)
>
> check_cxx_source_compiles("
>     #include <thread>
>     int main() {
>         std::thread t([]{});
>         t.join();
>         return 0;
>     }
> " HAVE_STD_THREAD)
>
> option(ENABLE_DEBUG_TRACE "Enable debug tracing" OFF)
> set(DEFAULT_THREADS 4)
>
> configure_file(config.h.in ${CMAKE_CURRENT_BINARY_DIR}/config.h @ONLY)
>
> add_executable(config_exe main.cpp)
> target_include_directories(config_exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
> ```

### 练习 3: 使用 `CheckCXXSourceCompiles` 检测特性

编写一个 CMake 项目，使用 `CheckCXXSourceCompiles` 检测以下 C++ 特性：

1. `__builtin_expect` (GCC/Clang branch prediction hint)
2. `[[nodiscard]]` 属性 (C++17)
3. `__has_include` (C++17)

将检测结果写入 `feature_config.h`（通过 `configure_file`），并在 `main.cpp` 中打印检测结果。

**要求:**

- 对三个特性使用 `#cmakedefine01`
- 在 `main.cpp` 中使用 `#if FEATURE_NAME` 分支打印结果
- 如果检测失败（交叉编译等场景），`check_cxx_source_compiles` 的 `RESULT_VARIABLE` 应保持为 falsy

> [!tip]- 参考方案
> ```cmake
> # CMakeLists.txt
> cmake_minimum_required(VERSION 3.24)
> project(FeatureExercise LANGUAGES CXX)
>
> include(CheckCXXSourceCompiles)
>
> check_cxx_source_compiles("
>     int main() {
>         int x = 0;
>         if (__builtin_expect(x == 0, 1)) { return 0; }
>         return 1;
>     }
> " HAVE_BUILTIN_EXPECT)
>
> check_cxx_source_compiles("
>     struct [[nodiscard]] Foo { int v; };
>     int main() {
>         Foo f{42};
>         return f.v;
>     }
> " HAVE_NODISCARD)
>
> check_cxx_source_compiles("
>     #if __has_include(<optional>)
>     int main() { return 0; }
>     #else
>     #error \"no __has_include\"
>     #endif
> " HAVE_HAS_INCLUDE)
>
> configure_file(feature_config.h.in ${CMAKE_CURRENT_BINARY_DIR}/feature_config.h @ONLY)
>
> add_executable(feat_test main.cpp)
> target_include_directories(feat_test PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
> target_compile_features(feat_test PRIVATE cxx_std_17)
> ```
>
> ```c
> // feature_config.h.in
> #ifndef FEATURE_CONFIG_H
> #define FEATURE_CONFIG_H
> #cmakedefine01 HAVE_BUILTIN_EXPECT
> #cmakedefine01 HAVE_NODISCARD
> #cmakedefine01 HAVE_HAS_INCLUDE
> #endif
> ```
>
> ```cpp
> // main.cpp
> #include <iostream>
> #include "feature_config.h"
>
> int main() {
> #if HAVE_BUILTIN_EXPECT
>     std::cout << "__builtin_expect  : YES" << std::endl;
> #else
>     std::cout << "__builtin_expect  : NO" << std::endl;
> #endif
> #if HAVE_NODISCARD
>     std::cout << "[[nodiscard]]     : YES" << std::endl;
> #else
>     std::cout << "[[nodiscard]]     : NO" << std::endl;
> #endif
> #if HAVE_HAS_INCLUDE
>     std::cout << "__has_include     : YES" << std::endl;
> #else
>     std::cout << "__has_include     : NO" << std::endl;
> #endif
>     return 0;
> }
> ```

- [[08-generator-expressions]] — 生成器表达式深入，理解 `$<...>` 的求值时机
- [[16-custom-commands-and-generated-files]] — `add_custom_command` / `add_custom_target` 的完整用法
- [[19-cmake-internal-architecture]] — 配置/生成/构建三阶段内部机制
- CMake 官方文档: [`configure_file`](https://cmake.org/cmake/help/latest/command/configure_file.html)
- CMake 官方文档: [`CheckCXXSourceCompiles`](https://cmake.org/cmake/help/latest/module/CheckCXXSourceCompiles.html)
- CMake 官方文档: [`file(GENERATE)`](https://cmake.org/cmake/help/latest/command/file.html#generate)
- [GNU Autoconf `#define` 惯例](https://www.gnu.org/software/autoconf/manual/autoconf.html#Defining-Symbols) — `#cmakedefine` 的前身参考

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 参考上方练习 1 的「参考方案」callout。核心要点：
> - 使用 `project()` 设置 `VERSION 2.1.4.8`，CMake 自动拆分 `PROJECT_VERSION_MAJOR/MINOR/PATCH/TWEAK`
> - `version.h.in` 使用 `@VAR@` 语法 + `@ONLY` 模式
> - 必须将 `${CMAKE_CURRENT_BINARY_DIR}` 加入 include 路径

> [!tip]- 练习 2 参考答案
> 参考上方练习 2 的「参考方案」callout。核心要点：
> - `HAVE_UNISTD_H` 用 `#cmakedefine`（传统 on/off），`HAVE_STD_THREAD` 用 `#cmakedefine01`（0/1）
> - `ENABLE_DEBUG_TRACE` 用 `option()` 定义用户可配置开关
> - `CMAKE_SYSTEM_PROCESSOR` 通过 `@CMAKE_SYSTEM_PROCESSOR@` 嵌入
> - `DEFAULT_THREADS` 在 CMakeLists.txt 中 `set()`，模板中 `@DEFAULT_THREADS@`

> [!tip]- 练习 3 参考答案
> 参考上方练习 3 的「参考方案」callout。核心要点：
> - `CheckCXXSourceCompiles` 的三个检测各自独立，失败时变量为 falsy
> - `feature_config.h.in` 中统一使用 `#cmakedefine01`（always-0-or-1 语义）
> - `main.cpp` 用 `#if` 而非 `#ifdef` 检测（因为 `#cmakedefine01` 保证宏一定被定义）

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 常见陷阱

### 陷阱 1: 在 C/C++ 模板中使用 `${VAR}` 导致意外替换

**问题:** 模板文件中包含合法的 C 代码如 `std::vector<int> v = {1, 2, 3}` 与合法的 CMake 变量替换 `${SOME_VAR}` 看起来相似。虽然 CMake 不会把 `{1, 2, 3}` 误认为变量引用，但阅读和维护时容易混淆。

**更严重的情况:** 你的模板文件恰好定义了一个与 CMake 变量同名的变量：

```c
// template.c.in
#define STREAMS 4
// ...
char buf[${STREAMS}];  // 如果 CMake 中有变量 STREAMS，这里会被替换！
```

**解决:** 始终在 C/C++ 模板中使用 `@ONLY` 和 `@VAR@` 语法。

```cmake
configure_file(template.c.in output.c @ONLY)
```

```c
// template.c.in — 安全
char buf[@STREAMS@];  // 只有 @STREAMS@ 被替换，${anything} 原样保留
```

### 陷阱 2: 输出路径相对于 binary dir，include 路径不匹配

**问题:**

```cmake
# configure_file 的输出默认相对于 CMAKE_CURRENT_BINARY_DIR
configure_file(src/config.h.in config.h)

# 但是 include 路径没加 binary dir
target_include_directories(myapp PRIVATE src/)
```

这会导致 `#include "config.h"` 找不到文件——`config.h` 生成在 `build/config.h`，而 include path 指向 `src/`。

**解决:** 两种方案：

```cmake
# 方案 A: include 路径加入 binary dir
target_include_directories(myapp PRIVATE ${CMAKE_CURRENT_BINARY_DIR})

# 方案 B: configure_file 输出到 source 子目录（不推荐——生成的文件不应在 source dir）
# 不推荐！
```

### 陷阱 3: `configure_file` 在变量设置之前执行

**问题:**

```cmake
configure_file(config.h.in config.h)  # ← 在这一行，MY_FEATURE 可能还未设置

set(MY_FEATURE ON)  # ← 太晚了
```

产出：

```c
/* #undef MY_FEATURE */  // 错误：应该 #define MY_FEATURE
```

**解决:** 确保所有变量在调用 `configure_file` **之前**定义。对于复杂项目，建议把所有检测逻辑放在 `configure_file` 之前的一个 block 或单独的 `.cmake` 模块中。

```cmake
# ✅ 正确顺序
include(CheckCXXSourceCompiles)
check_cxx_source_compiles("..." MY_FEATURE)
option(ENABLE_X "Enable X" ON)

# 现在所有变量都设置好了
configure_file(config.h.in config.h)
```

### 陷阱 4: 修改模板后不重新配置

**问题:** 你修改了 `version.h.in` 模板（增加了一个 `#cmakedefine`），然后直接执行 `cmake --build build`。CMake **不会**自动重新运行 configure —— 因为 `CMakeLists.txt` 没有变化，所以配置阶段被跳过。

**解决:**

```bash
# 方案 A: 显式重新配置
cmake -B build

# 方案 B: 在 CMakeLists.txt 中设置 CMAKE_CONFIGURE_DEPENDS
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/version.h.in)
```

> [!tip] CMAKE_CONFIGURE_DEPENDS
> 这个目录属性告诉 CMake：如果指定的文件发生变化，应该重新运行配置阶段。适合模板文件、工具链文件等。

### 陷阱 5: `NEWLINE_STYLE` 不处理已经存在的 CRLF 模板

**问题:** 如果你的模板文件已经在磁盘上保存为 CRLF（比如 Windows Git autocrlf 转换后），即使设置了 `NEWLINE_STYLE LF`，输出的 `\r\n` 也可能没有被完全转换为 `\n`——因为 CMake 读取文件后，`\r\n` 可能已经被 C 运行时库转换为 `\n`，然后 `NEWLINE_STYLE LF` 只是确保写入时用 `\n`。

**真正需要小心的是:** 二进制模式或精确字节控制的场景。对于大多数文本头文件，这不是问题。

### 陷阱 6: 多次 configure 造成陈旧的生成文件

**问题:** 你从 `CMakeLists.txt` 中删除了一个 `configure_file` 调用，但之前生成的文件仍然留在 binary dir。后续的 `#include` 可能捡到旧文件。

**解决:**

```bash
# 清理 binary dir 后重新配置
rm -rf build
cmake -B build
```

或者在开发时使用 `cmake --fresh` (CMake 3.24+) 强制从干净状态开始。

### 陷阱 7: `@ONLY` 模式下忘记 `@` 包裹

**问题:**

```c
// config.h.in — 使用 @ONLY 但忘记 @ 包裹
#define VERSION PROJECT_VERSION  // 不会被替换！输出就是 "PROJECT_VERSION"
```

**解决:**

```c
// ✅ 正确
#define VERSION @PROJECT_VERSION@
```

---

## 总结

| 概念 | 要点 |
|------|------|
| `configure_file` | 配置阶段运行，替换 `@VAR@` / `${VAR}`，支持 `#cmakedefine` |
| `@ONLY` | 只替换 `@VAR@`，防止与 C/C++ 中的 `${}` 冲突 |
| `#cmakedefine` | 真值 → `#define`，假值 → `/* #undef */` |
| `#cmakedefine01` | 真值 → `#define VAR 1`，假值 → `#define VAR 0`，始终定义 |
| `file(GENERATE)` | 生成阶段运行，支持生成器表达式，无 `#cmakedefine` |
| `add_custom_command` | 构建阶段运行，任意脚本/工具，最灵活 |
| 检测模块 | `CheckCXXSourceCompiles` 等在配置阶段探测，结果交给 `configure_file` |
| 平台 config | 经典模式：`config.h.in` + `Check*` 模块 + `configure_file` |
