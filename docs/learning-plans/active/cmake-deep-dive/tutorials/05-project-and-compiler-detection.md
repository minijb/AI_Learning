---
title: project() 与编译器检测
updated: 2026-06-10
tags: [cmake, project, compiler, c++-standard, platform-detection]
---

# project() 与编译器检测

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 45min
> 前置知识: [[02-cmakelists-structure-and-commands]]

---

## 1. 概念讲解

`project()` 是 CMake 中最重要的命令之一。它不仅标志着当前目录就是一个 CMake 构建树的根（或子项目），更重要的是：**它触发了 CMake 对编译器和目标平台的全面检测**。没有 `project()`，CMake 甚至不知道你在用什么编译器，更谈不上设置编译标志。

### 为什么需要 project()？

CMake 是一个跨平台构建系统，核心价值就是同一份 `CMakeLists.txt` 能在 Linux、Windows、macOS 上正确工作。但不同平台有不同的编译器（GCC、MSVC、Clang、AppleClang），不同编译器有不同的命令行参数、标准库实现、扩展语法。`project()` 的作用就是：

1. **命名项目**：给整个构建一个名字，影响生成的 IDE 解决方案文件名、输出目录等
2. **声明语言**：告诉 CMake 你需要处理哪些语言（C、C++、Fortran 等），CMake 会检测对应编译器
3. **触发器**：驱动编译器检测、平台识别、架构探测等一系列扫描
4. **建立作用域**：设置 `PROJECT_NAME`、`PROJECT_SOURCE_DIR`、`PROJECT_BINARY_DIR` 等变量
5. **版本管理**：声明项目版本号，供 `find_package`、CPack 等下游工具使用

### project() 的完整签名

```cmake
project(<PROJECT-NAME>
        [VERSION <major>[.<minor>[.<patch>[.<tweak>]]]]
        [DESCRIPTION <project-description-string>]
        [HOMEPAGE_URL <url-string>]
        [LANGUAGES <language-name>...])
```

**参数详解：**

| 参数 | 必需 | 说明 |
|------|:----:|------|
| `PROJECT-NAME` | **是** | 项目名称。必须是第一个参数，推荐使用字母、数字、下划线、连字符 |
| `VERSION` | 推荐 | 语义化版本号，如 `1.2.3`。同时拆分为 `PROJECT_VERSION_MAJOR`、`PROJECT_VERSION_MINOR`、`PROJECT_VERSION_PATCH`、`PROJECT_VERSION_TWEAK` |
| `DESCRIPTION` | 否 | 项目描述文本。CMake 3.9+ |
| `HOMEPAGE_URL` | 否 | 项目主页 URL。CMake 3.12+ |
| `LANGUAGES` | 否 | 语言列表（如 `C CXX`），不指定时默认 `C CXX`。CMake 4.0 起若无此参数且无 `enable_language()` 则报错 |

> [!tip]
> 即使你只需要 C++，显式写 `LANGUAGES CXX` 也比依赖默认更清晰。

### project() 执行时发生了什么？

当 CMake 遇到 `project()` 命令时，内部会按顺序执行以下操作：

**第 1 步：记录项目信息**
设置 `PROJECT_NAME`、`PROJECT_SOURCE_DIR`、`PROJECT_BINARY_DIR` 等变量。

**第 2 步：编译器检测**
对 `LANGUAGES` 中列出的每一种语言，CMake 会：

- 在系统路径中搜索可执行文件（`g++`、`clang++`、`cl.exe` 等）
- 从 `PATH` 环境变量中查找
- 从 `CC`、`CXX` 环境变量中读取用户指定的编译器
- 从 CMake 缓存变量 `CMAKE_<LANG>_COMPILER` 中读取之前配置的路径
- 编译一个最小的测试程序来确认编译器真的能工作
- 提取编译器标识（ID）、版本号、目标架构

**第 3 步：平台检测**
识别操作系统、内核版本、CPU 架构：

- `CMAKE_SYSTEM_NAME`：如 `Linux`、`Windows`、`Darwin`、`Android`、`iOS`
- `CMAKE_SYSTEM_VERSION`：内核/系统版本号
- `CMAKE_SYSTEM_PROCESSOR`：如 `x86_64`、`aarch64`、`AMD64`

**第 4 步：编译器特性探测**
CMake 编译器信息模块（`CMakeDetermineCompilerSupport`）会编译一系列探测源文件，确定编译器支持哪些 C++ 标准特性。这些结果存储在 `CMAKE_<LANG>_COMPILE_FEATURES` 中。

**第 5 步：默认标志设置**
CMake 自动为每种构建类型（Debug、Release 等）填充 `CMAKE_<LANG>_FLAGS_<CONFIG>_INIT` 变量。

> [!warning]
> 如果 `project()` 出现在嵌套的 `add_subdirectory()` 中（即**子目录也调用了 project()**），编译器**不会重新检测**——只更新当前作用域的 `PROJECT_*` 变量。编译器检测只在顶层 `project()` 时完整执行一次。

---

### project() 设置的变量

CMake 调用 `project()` 后，会设置两大类变量：

#### 与项目自身相关的变量

| 变量 | 含义 | 注意事项 |
|------|------|----------|
| `PROJECT_NAME` | 当前项目名 | 在子目录重设 `project(sub_project)` 后变成 `sub_project` |
| `CMAKE_PROJECT_NAME` | **顶层**项目名 | 始终是第一个 `project()` 传入的名称 |
| `PROJECT_VERSION` | 当前项目版本 | 如 `"1.2.3"` |
| `PROJECT_VERSION_MAJOR` | 主版本号 | `1` |
| `PROJECT_VERSION_MINOR` | 次版本号 | `2` |
| `PROJECT_VERSION_PATCH` | 补丁版本号 | `3` |
| `PROJECT_VERSION_TWEAK` | 修订号 | 不指定为 `""` |
| `PROJECT_SOURCE_DIR` | 当前项目的源码根目录 | 即包含当前 `project()` 调用的 `CMakeLists.txt` 所在目录 |
| `PROJECT_BINARY_DIR` | 当前项目的构建目录 | 对应源码目录在构建树中的映射 |
| `PROJECT_DESCRIPTION` | 项目描述 | CMake 3.9+ |
| `PROJECT_HOMEPAGE_URL` | 项目主页 | CMake 3.12+ |

#### 与整个构建相关的变量（全局）

| 变量 | 含义 | 谁设置的 |
|------|------|----------|
| `CMAKE_SOURCE_DIR` | 顶层源码目录 | 顶层 `CMakeLists.txt` 所在的目录 |
| `CMAKE_BINARY_DIR` | 顶层构建目录 | 用户运行 `cmake` 的目录 |
| `<PROJECT-NAME>_SOURCE_DIR` | 以项目名命名的源码目录变量 | `project(Foo)` → `Foo_SOURCE_DIR` |
| `<PROJECT-NAME>_BINARY_DIR` | 以项目名命名的构建目录变量 | `project(Foo)` → `Foo_BINARY_DIR` |

#### 编译器变量（以 C++ 为例）

| 变量 | 含义 | 示例值 |
|------|------|--------|
| `CMAKE_CXX_COMPILER` | 编译器可执行文件路径 | `/usr/bin/g++-13` |
| `CMAKE_CXX_COMPILER_ID` | 编译器标识 | `GNU`、`MSVC`、`Clang`、`AppleClang` |
| `CMAKE_CXX_COMPILER_VERSION` | 编译器版本号字符串 | `13.2.0` |
| `CMAKE_CXX_COMPILER_FRONTEND_VARIANT` | 前端变体 | `GNU`、`MSVC`、`AppleClang` |
| `CMAKE_CXX_COMPILER_ABI` | ABI 信息 | ELF 可执行文件格式等 |

> [!tip] 编译器 ID 对照表
> - **GNU**：GCC
> - **MSVC**：微软 Visual C++
> - **Clang**：LLVM Clang（Linux/macOS 自由发行版）
> - **AppleClang**：Apple 定制的 Clang（Xcode 自带）
> - **Intel**：Intel oneAPI 编译器
> - **IntelLLVM**：基于 LLVM 的新一代 Intel 编译器
> - **NVHPC**：NVIDIA HPC SDK
> - **ARMClang**：ARM 编译器

#### 平台变量

| 变量 | 含义 | 示例值 |
|------|------|--------|
| `CMAKE_SYSTEM_NAME` | 操作系统名 | `Linux`、`Windows`、`Darwin`（macOS）、`Android`、`iOS` |
| `CMAKE_SYSTEM_VERSION` | 操作系统版本 | `6.5.0`（Linux 内核版本）、`23H2`（Windows） |
| `CMAKE_SYSTEM_PROCESSOR` | 目标 CPU 架构 | `x86_64`、`aarch64`、`armv7l`、`AMD64` |
| `CMAKE_HOST_SYSTEM_NAME` | 主机操作系统 | 交叉编译时与 `CMAKE_SYSTEM_NAME` 不同 |
| `CMAKE_HOST_SYSTEM_PROCESSOR` | 主机 CPU 架构 | 交叉编译时表示构建机器的架构 |
| `CMAKE_CROSSCOMPILING` | 是否交叉编译 | `TRUE` 或 `FALSE` |

### 编译器 ID 的条件判断模式

编译器 ID 是最常用的条件分支依据之一：

```cmake
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    # GCC 特定逻辑
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
    # MSVC 特定逻辑
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    # Clang 特定逻辑（注意：macOS 上 Xcode 的 Clang 报告为 "AppleClang"）
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang")
    # Apple Clang 特定逻辑
endif()
```

也可以使用 `MATCHES` 进行模糊匹配——例如将 Clang 和 AppleClang 归为一类：

```cmake
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    # 同时匹配 Clang 和 AppleClang
endif()
```

### enable_language() —— 事后添加语言

如果你在 `project()` 中未列出某种语言，但后面又需要它（比如你的 C 项目突然要用 CUDA），`enable_language()` 可以在不重新调用 `project()` 的情况下触发编译器检测：

```cmake
project(MyApp LANGUAGES CXX)            # 只检测 C++ 编译器
# ... 之后 ...
enable_language(CUDA)                   # 现在检测 CUDA 编译器
```

这个命令也可以在顶层 `project()` 调用之前使用——如果你需要先知道编译器信息再决定项目参数：

```cmake
cmake_minimum_required(VERSION 3.24)
enable_language(CXX)
message(STATUS "Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
project(MyApp VERSION 1.0)
```

> [!warning]
> `enable_language()` 必须在 `project()` 之后或 `project()` 之前调用，不能跳过 `project()` 单独使用——因为编译器检测需要知道目标平台信息，而这些信息部分来源于 `project()` 命令。

### 顶层 project() vs 子目录 project()

一个 CMake 项目中可以存在多个 `project()` 调用：

```cmake
# 顶层 CMakeLists.txt
cmake_minimum_required(VERSION 3.24)
project(SuperApp VERSION 2.0 LANGUAGES CXX)   # 顶层 project()

add_subdirectory(core)      # core/CMakeLists.txt 里有自己的 project()
add_subdirectory(plugins)   # plugins/CMakeLists.txt 里有自己的 project()
```

```cmake
# core/CMakeLists.txt
project(CoreLib VERSION 1.5)   # 子项目
# 此时：
# CMAKE_PROJECT_NAME = SuperApp   (始终是顶层)
# PROJECT_NAME       = CoreLib    (当前子项目)
# CoreLib_SOURCE_DIR = .../SuperApp/core
```

**关键区别：**

| 项目 | 编译器检测 | 变量作用域 |
|------|:---------:|-----------|
| 顶层 `project()` | **完整执行**：编译器检测 + 平台探测 + 标志设置 | 设置全部 `CMAKE_*` 和 `PROJECT_*` 变量 |
| 子目录 `project()` | **不执行**编译器检测，仅更新 `PROJECT_*` 变量 | 只更新当前作用域的 `PROJECT_NAME`、`PROJECT_VERSION` 等 |

**何时在子目录使用 project()？**
- 子目录本身是一个独立的库，有自己的版本号
- 希望子项目可被独立 `find_package()` 导入
- 使用 `${PROJECT_NAME}` 变量在子目录中做相对引用

### C++ 标准设置：多种方式的对比

CMake 提供了几种设置 C++ 标准的方式，从老旧到现代排序：

#### 方式 1：全局变量（老旧，不推荐）

```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

影响**所有后续创建的 target**。问题是：一旦你在公共模块中设了，所有引入该模块的项目都被强制使用该标准。无法做到"项目 A 用 C++17，项目 B 用 C++20"。

#### 方式 2：目录级属性

```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# 只影响当前目录及其 add_subdirectory() 子目录中的 target
```

比全局稍好，但仍不够精细。

#### 方式 3：target 级属性（Modern CMake，推荐）

```cmake
add_executable(my_app main.cpp)
set_target_properties(my_app PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
    CXX_EXTENSIONS OFF
)
```

精确到单个 target，不影响任何其他 target。

#### 方式 4：target_compile_features()（最现代，推荐）

```cmake
add_executable(my_app main.cpp)
target_compile_features(my_app PUBLIC cxx_std_17)
```

这是 CMake 推荐的方式，因为：
- 它是 **target 级**的，精确作用域
- 它表达了 **意图**（"这个目标需要 C++17 特性"）而非强制指定标准版本
- CMake 会将 `cxx_std_17` 映射到合适的编译器标志：`-std=c++17`（GCC/Clang）或 `/std:c++17`（MSVC）
- `PUBLIC` 关键字表明使用该 target 的消费者也会被要求 C++17

#### `CMAKE_CXX_STANDARD_REQUIRED` 的重要性

```cmake
set(CMAKE_CXX_STANDARD 17)
# 没有设置 CMAKE_CXX_STANDARD_REQUIRED！
```

如果不设置 `REQUIRED`，CMake 的行为是 **尝试使用 C++17**，但如果编译器不支持，会**静默回退**到更低的默认标准（如 C++14 甚至 C++98）。你以为是 C++17，实际可能编译成 C++14——没有任何警告。

```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)   # 必须加上！
```

加上 `REQUIRED` 后，如果编译器不支持 C++17，CMake 在配置阶段就会**报错终止**。

对应的 target 级属性：

```cmake
set_target_properties(my_app PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON     # 不满足时配置失败
    CXX_EXTENSIONS OFF           # 禁止编译器扩展（如 GNU 扩展）
)
```

`CXX_EXTENSIONS OFF` 也很重要：它禁止编译器特定扩展（如 GCC 的 `__GNUC__` 相关语法），确保代码更可移植。对应 `-std=c++17`（而非 `-std=gnu++17`）。

### compile_feature 的完整取值

`target_compile_features()` 可用的元特性（meta-feature）列表：

| 元特性 | 等价的标准版本 |
|--------|:-----------:|
| `cxx_std_98` | C++98 |
| `cxx_std_11` | C++11 |
| `cxx_std_14` | C++14 |
| `cxx_std_17` | C++17 |
| `cxx_std_20` | C++20 |
| `cxx_std_23` | C++23 |
| `cxx_std_26` | C++26 |

除了元特性，还有**细粒度**的编译特性：

| 特性 | 含义 | 最低标准 |
|------|------|:------:|
| `cxx_constexpr` | `constexpr` 关键字 | C++11 |
| `cxx_auto_type` | `auto` 类型推导 | C++11 |
| `cxx_lambdas` | Lambda 表达式 | C++11 |
| `cxx_range_for` | Range-based for | C++11 |
| `cxx_generic_lambdas` | 泛型 lambda | C++14 |
| `cxx_variable_templates` | 变量模板 | C++14 |
| `cxx_fold_expressions` | 折叠表达式 | C++17 |
| `cxx_if_constexpr` | `if constexpr` | C++17 |
| `cxx_structured_bindings` | 结构化绑定 | C++17 |
| `cxx_concepts` | Concepts | C++20 |
| `cxx_coroutines` | 协程 `co_await`/`co_return` | C++20 |

用细粒度特性可以精确声明需求——例如只需 `if constexpr` 就用 `cxx_if_constexpr`，编译器会自动选用满足该特性的最低标准。

### 检查编译器是否支持特定标志

有时你需要使用编译器特有的标志（如 GCC 的 `-Wall`、MSVC 的 `/W4`），但不能假设编译器支持。CMake 提供了检查模块：

#### CheckCXXCompilerFlag

检测编译器是否接受某个编译标志：

```cmake
include(CheckCXXCompilerFlag)
check_cxx_compiler_flag("-Wall" COMPILER_SUPPORTS_WALL)
if(COMPILER_SUPPORTS_WALL)
    target_compile_options(my_app PRIVATE -Wall)
endif()
```

#### CheckCXXSymbolExists

检测特定头文件中是否存在某个符号：

```cmake
include(CheckCXXSymbolExists)
check_cxx_symbol_exists(EPOLL_CLOEXEC "sys/epoll.h" HAS_EPOLL_CLOEXEC)
```

### CMAKE_BUILD_TYPE 与构建配置

CMake 支持四种标准构建类型（仅限单配置生成器如 Make、Ninja）：

| 构建类型 | 典型标志（GCC/Clang） | 典型标志（MSVC） | 用途 |
|----------|-----------------------|-------------------|------|
| `Debug` | `-g` | `/Zi /Od` | 开发调试，无优化，含调试符号 |
| `Release` | `-O3 -DNDEBUG` | `/O2 /DNDEBUG` | 生产发布，最大优化 |
| `RelWithDebInfo` | `-O2 -g -DNDEBUG` | `/O2 /Zi /DNDEBUG` | 带调试符号的优化版本 |
| `MinSizeRel` | `-Os -DNDEBUG` | `/O1 /DNDEBUG` | 最小体积优化 |

设置方式：

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
```

在 CMakeLists.txt 中**不要硬编码** `CMAKE_BUILD_TYPE`——这是用户的选择，应在命令行指定。默认值为空字符串（无构建类型），此时编译器可能不传递任何优化/调试标志。

对于多配置生成器（Visual Studio、Xcode），使用 `CMAKE_CONFIGURATION_TYPES` 代替：

```cmake
# 这是一个列表变量，适用于 VS/Xcode
# 默认值是 "Debug;Release;MinSizeRel;RelWithDebInfo"
```

### CMAKE_CXX_FLAGS vs target_compile_options —— 根本区别

这是 CMake 中一个核心的设计分歧：

| 方式 | 作用范围 | 缺点 |
|------|:------:|------|
| `set(CMAKE_CXX_FLAGS "-Wall -Wextra")` | **全局**：影响所有 target，所有目录 | 无法精确控制；第三方库也被影响；难以调试哪个 flag 从哪来 |
| `target_compile_options(my_app PRIVATE -Wall -Wextra)` | **单 target** | **推荐**：精确、可追踪、可导出 |

```cmake
# ❌ 糟糕的做法：全局污染
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -Wpedantic")

# ✅ 正确的做法：target 级
target_compile_options(my_app PRIVATE
    $<$<CXX_COMPILER_ID:GNU>:-Wall -Wextra -Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)
```

上面的生成器表达式（`$<$<...>:...>`）语法会在[[08-generator-expressions]]中详解，这里可理解为"如果编译器是 GNU，加上这些标志"。

> [!danger] CMAKE_CXX_FLAGS 的陷阱
> `CMAKE_CXX_FLAGS` 是一个**字符串**，不是列表。对其进行追加操作时极易引入格式错误（多余空格、缺失分隔符等）。且一旦在项目中多个位置修改它，追踪哪个值来自哪个 `CMakeLists.txt` 几乎不可能。**永远优先使用 `target_compile_options()`。**

---

## 2. 代码示例

### 示例 1：项目版本、语言标准与编译器信息输出

这个示例展示一个完整的项目配置，打印编译器、平台、版本信息。

**文件结构：**
```
example1/
├── CMakeLists.txt
└── main.cpp
```

**CMakeLists.txt：**

```cmake
cmake_minimum_required(VERSION 3.24)

project(
    CompilerInfo
    VERSION 1.0.0
    DESCRIPTION "演示 project() 编译器检测能力"
    HOMEPAGE_URL "https://github.com/example/compiler-info"
    LANGUAGES CXX
)

# 编译器信息
message(STATUS "========================================")
message(STATUS "项目: ${PROJECT_NAME}")
message(STATUS "版本: ${PROJECT_VERSION}")
message(STATUS "描述: ${PROJECT_DESCRIPTION}")
message(STATUS "主页: ${PROJECT_HOMEPAGE_URL}")
message(STATUS "顶层项目: ${CMAKE_PROJECT_NAME}")
message(STATUS "----------------------------------------")
message(STATUS "编译器 ID:      ${CMAKE_CXX_COMPILER_ID}")
message(STATUS "编译器路径:     ${CMAKE_CXX_COMPILER}")
message(STATUS "编译器版本:     ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "前端变体:       ${CMAKE_CXX_COMPILER_FRONTEND_VARIANT}")
message(STATUS "----------------------------------------")
message(STATUS "系统:           ${CMAKE_SYSTEM_NAME}")
message(STATUS "系统版本:       ${CMAKE_SYSTEM_VERSION}")
message(STATUS "处理器:         ${CMAKE_SYSTEM_PROCESSOR}")
message(STATUS "主机系统:       ${CMAKE_HOST_SYSTEM_NAME}")
message(STATUS "是否交叉编译:   ${CMAKE_CROSSCOMPILING}")
message(STATUS "----------------------------------------")
message(STATUS "源码目录:       ${PROJECT_SOURCE_DIR}")
message(STATUS "构建目录:       ${PROJECT_BINARY_DIR}")
message(STATUS "========================================")

add_executable(compiler_info main.cpp)

# 使用 target 级属性设置 C++17
set_target_properties(compiler_info PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
    CXX_EXTENSIONS OFF
)
```

**main.cpp：**

```cpp
#include <iostream>
#include <string>

int main() {
    std::cout << "=== 编译器信息（来自预定义宏）===\n";

#if defined(__clang__)
    std::cout << "编译器: Clang " << __clang_major__ << "."
              << __clang_minor__ << "." << __clang_patchlevel__ << "\n";
#elif defined(__GNUC__)
    std::cout << "编译器: GCC " << __GNUC__ << "."
              << __GNUC_MINOR__ << "." << __GNUC_PATCHLEVEL__ << "\n";
#elif defined(_MSC_VER)
    std::cout << "编译器: MSVC " << _MSC_VER << "\n";
#else
    std::cout << "编译器: 未知\n";
#endif

#if __cplusplus >= 202302L
    std::cout << "C++ 标准: C++23 或更新\n";
#elif __cplusplus >= 202002L
    std::cout << "C++ 标准: C++20\n";
#elif __cplusplus >= 201703L
    std::cout << "C++ 标准: C++17\n";
#elif __cplusplus >= 201402L
    std::cout << "C++ 标准: C++14\n";
#elif __cplusplus >= 201103L
    std::cout << "C++ 标准: C++11\n";
#else
    std::cout << "C++ 标准: C++98/03\n";
#endif

    return 0;
}
```

**运行方式：**

```bash
cd example1
cmake -B build
cmake --build build
./build/compiler_info    # Linux/macOS
# .\build\Debug\compiler_info.exe  # Windows (Visual Studio)
```

**预期输出（Linux + GCC 13 环境）：**

```text
-- ========================================
-- 项目: CompilerInfo
-- 版本: 1.0.0
-- 描述: 演示 project() 编译器检测能力
-- 主页: https://github.com/example/compiler-info
-- 顶层项目: CompilerInfo
-- ----------------------------------------
-- 编译器 ID:      GNU
-- 编译器路径:     /usr/bin/c++
-- 编译器版本:     13.2.0
-- 前端变体:       GNU
-- ----------------------------------------
-- 系统:           Linux
-- 系统版本:       6.5.0
-- 处理器:         x86_64
-- 主机系统:       Linux
-- 是否交叉编译:   FALSE
-- ----------------------------------------
-- 源码目录:       /home/user/example1
-- 构建目录:       /home/user/example1/build
-- ========================================

=== 编译器信息（来自预定义宏）===
编译器: GCC 13.2.0
C++ 标准: C++17
```

---

### 示例 2：target_compile_features 与特性检测

这个示例展示使用 `target_compile_features()` 要求 C++17，并通过 `write_compiler_detection_header()` 生成编译器能力头文件。

**文件结构：**
```
example2/
├── CMakeLists.txt
├── main.cpp
├── feature_check.cpp   # 条件编译的源文件
```

**CMakeLists.txt：**

```cmake
cmake_minimum_required(VERSION 3.24)

project(FeatureDemo VERSION 1.0 LANGUAGES CXX)

# ── 检测编译器支持的特性 ──
include(CheckCXXCompilerFlag)
include(CheckCXXSymbolExists)

# 检测特定编译标志
check_cxx_compiler_flag("-Wall" SUPPORTS_WALL)
check_cxx_compiler_flag("-Wextra" SUPPORTS_WEXTRA)

# 检测标准库中的符号
check_cxx_symbol_exists(std::to_string "string" HAS_STD_TO_STRING)

# ── 生成编译器能力头文件 ──
include(WriteCompilerDetectionHeader)
write_compiler_detection_header(
    FILE "${CMAKE_CURRENT_BINARY_DIR}/compiler_features.h"
    PREFIX MYPROJ
    COMPILERS GNU MSVC Clang AppleClang
    FEATURES cxx_if_constexpr cxx_structured_bindings cxx_fold_expressions
)

message(STATUS "Wall 支持:  ${SUPPORTS_WALL}")
message(STATUS "Wextra 支持: ${SUPPORTS_WEXTRA}")
message(STATUS "std::to_string 可用: ${HAS_STD_TO_STRING}")

# ── 主目标 ──
add_executable(feature_demo main.cpp feature_check.cpp)

# 用 target_compile_features 要求 C++17
target_compile_features(feature_demo PUBLIC cxx_std_17)

# 让源文件能访问生成的头文件
target_include_directories(feature_demo PRIVATE
    "${CMAKE_CURRENT_BINARY_DIR}"
)

# 根据检测结果，有条件地添加编译选项
if(SUPPORTS_WALL)
    target_compile_options(feature_demo PRIVATE -Wall)
endif()
if(SUPPORTS_WEXTRA)
    target_compile_options(feature_demo PRIVATE -Wextra)
endif()
```

**main.cpp：**

```cpp
#include <iostream>
#include "compiler_features.h"

// 使用 compiler_features.h 中的宏进行条件编译
static void demonstrate_structured_bindings() {
#if MYPROJ_COMPILER_CXX_STRUCTURED_BINDINGS
    // C++17 结构化绑定
    struct Point { int x; int y; };
    Point p{10, 20};
    auto [a, b] = p;
    std::cout << "结构化绑定: x=" << a << ", y=" << b << "\n";
#else
    std::cout << "结构化绑定: 不支持\n";
#endif
}

static void demonstrate_if_constexpr() {
#if MYPROJ_COMPILER_CXX_IF_CONSTEXPR
    // C++17 if constexpr
    if constexpr (sizeof(int) == 4) {
        std::cout << "if constexpr: int 是 4 字节\n";
    } else {
        std::cout << "if constexpr: int 不是 4 字节\n";
    }
#else
    std::cout << "if constexpr: 不支持\n";
#endif
}

// 声明在 feature_check.cpp 中
void check_fold_expressions();

int main() {
    std::cout << "=== target_compile_features 演示 ===\n\n";
    demonstrate_structured_bindings();
    demonstrate_if_constexpr();
    check_fold_expressions();
    return 0;
}
```

**feature_check.cpp：**

```cpp
#include <iostream>
#include "compiler_features.h"

void check_fold_expressions() {
#if MYPROJ_COMPILER_CXX_FOLD_EXPRESSIONS
    // C++17 折叠表达式
    auto sum = [](auto... args) {
        return (... + args);
    };
    std::cout << "折叠表达式: 1+2+3+4+5 = "
              << sum(1, 2, 3, 4, 5) << "\n";
#else
    std::cout << "折叠表达式: 不支持\n";
#endif
}
```

**运行方式：**

```bash
cd example2
cmake -B build
cmake --build build
./build/feature_demo
```

**预期输出：**

```text
-- Wall 支持:  TRUE
-- Wextra 支持: TRUE
-- std::to_string 可用: TRUE

=== target_compile_features 演示 ===

结构化绑定: x=10, y=20
if constexpr: int 是 4 字节
折叠表达式: 1+2+3+4+5 = 15
```

---

### 示例 3：根据 CMAKE_CXX_COMPILER_ID 条件编译

展示如何在不同编译器上使用不同的编译选项和源码。

**文件结构：**
```
example3/
├── CMakeLists.txt
├── main.cpp
└── platform/
    ├── gcc_specific.cpp
    └── msvc_specific.cpp
```

**CMakeLists.txt：**

```cmake
cmake_minimum_required(VERSION 3.24)

project(CompilerConditional VERSION 1.0 LANGUAGES CXX)

# ── 根据编译器 ID 添加不同的源文件 ──
set(EXTRA_SOURCES "")

if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    message(STATUS "检测到 GCC，添加 GCC 特定代码")
    list(APPEND EXTRA_SOURCES platform/gcc_specific.cpp)

elseif(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
    message(STATUS "检测到 MSVC，添加 MSVC 特定代码")
    list(APPEND EXTRA_SOURCES platform/msvc_specific.cpp)

elseif(CMAKE_CXX_COMPILER_ID MATCHES "Clang")  # Clang 和 AppleClang
    message(STATUS "检测到 Clang 系列编译器")
    # Clang 通常可以使用 GCC 的代码
    list(APPEND EXTRA_SOURCES platform/gcc_specific.cpp)

else()
    message(WARNING "未知编译器: ${CMAKE_CXX_COMPILER_ID}，使用通用代码")
endif()

# ── 构建可执行文件 ──
add_executable(compiler_cond main.cpp ${EXTRA_SOURCES})

target_compile_features(compiler_cond PUBLIC cxx_std_17)

# ── 各编译器不同的编译选项 ──
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    target_compile_options(compiler_cond PRIVATE
        -Wall -Wextra -Wpedantic -Wshadow
        -Wnon-virtual-dtor -Wold-style-cast
    )
    # GCC 特有定义
    target_compile_definitions(compiler_cond PRIVATE
        COMPILER_NAME="GCC"
        COMPILER_GNU=1
    )

elseif(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
    target_compile_options(compiler_cond PRIVATE
        /W4           # 最高警告级别
        /permissive-  # 标准符合模式
        /Zc:__cplusplus  # 正确设置 __cplusplus 宏
    )
    target_compile_definitions(compiler_cond PRIVATE
        COMPILER_NAME="MSVC"
        COMPILER_MSVC=1
        _CRT_SECURE_NO_WARNINGS
    )

elseif(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    target_compile_options(compiler_cond PRIVATE
        -Wall -Wextra -Wpedantic
        -Weverything -Wno-c++98-compat -Wno-padded
    )
    target_compile_definitions(compiler_cond PRIVATE
        COMPILER_NAME="Clang"
        COMPILER_CLANG=1
    )
endif()

# ── 打印配置摘要 ──
message(STATUS "========================================")
message(STATUS "编译器条件编译配置")
message(STATUS "  编译器:       ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "  源文件:       main.cpp ${EXTRA_SOURCES}")
message(STATUS "  C++ 标准:     C++17 (target_compile_features)")
message(STATUS "========================================")
```

**main.cpp：**

```cpp
#include <iostream>
#include <string>

// 这些宏由 CMake 的 target_compile_definitions 设置
#ifndef COMPILER_NAME
#define COMPILER_NAME "Unknown"
#endif

int main() {
    std::cout << "=== 编译器条件编译演示 ===\n";
    std::cout << "编译器名（CMake 定义）: " << COMPILER_NAME << "\n";

#ifdef COMPILER_GNU
    std::cout << "执行 GCC 特定代码路径\n";
#endif

#ifdef COMPILER_MSVC
    std::cout << "执行 MSVC 特定代码路径\n";
#endif

#ifdef COMPILER_CLANG
    std::cout << "执行 Clang 特定代码路径\n";
#endif

    return 0;
}
```

**platform/gcc_specific.cpp：**

```cpp
#include <iostream>

// 仅在 GCC/Clang 下编译的代码
struct GccFeature {
    GccFeature() {
        std::cout << "[GCC 专属] __GNUC__ = " << __GNUC__ << "\n";
        std::cout << "[GCC 专属] __GNUC_MINOR__ = " << __GNUC_MINOR__ << "\n";
        std::cout << "[GCC 专属] __GNUC_PATCHLEVEL__ = "
                  << __GNUC_PATCHLEVEL__ << "\n";
    }
};

// 全局对象，main 之前构造
static GccFeature g_gcc_info;
```

**platform/msvc_specific.cpp：**

```cpp
#include <iostream>

// 仅在 MSVC 下编译的代码
struct MsvcFeature {
    MsvcFeature() {
        std::cout << "[MSVC 专属] _MSC_VER = " << _MSC_VER << "\n";
        std::cout << "[MSVC 专属] _MSC_FULL_VER = " << _MSC_FULL_VER << "\n";
        std::cout << "[MSVC 专属] _MSVC_LANG = " << _MSVC_LANG << "\n";
    }
};

static MsvcFeature g_msvc_info;
```

**运行方式：**

```bash
cd example3
cmake -B build
cmake --build build
./build/compiler_cond
```

**预期输出（GCC + Linux 环境）：**

```text
-- 检测到 GCC，添加 GCC 特定代码
-- ========================================
-- 编译器条件编译配置
--   编译器:       GNU 13.2.0
--   源文件:       main.cpp platform/gcc_specific.cpp
--   C++ 标准:     C++17 (target_compile_features)
-- ========================================

=== 编译器条件编译演示 ===
编译器名（CMake 定义）: GCC
[GCC 专属] __GNUC__ = 13
[GCC 专属] __GNUC_MINOR__ = 2
[GCC 专属] __GNUC_PATCHLEVEL__ = 0
执行 GCC 特定代码路径
```

---

## 3. 练习

### 练习 1：设置 C++20 项目并在旧编译器上优雅失败

**目标：** 创建一个 CMake 项目，要求 C++20 标准，且在编译器不支持时给出清晰的错误信息并终止配置，而非静默降级。

**要求：**

1. 项目名为 `Cpp20Project`，版本号 `0.1.0`
2. 使用 `target_compile_features()` 要求 `cxx_std_20`
3. 同时设置 `CXX_STANDARD_REQUIRED` 确保不降级
4. 在 `project()` 之后立即检查 `CMAKE_CXX_COMPILER_ID` 和 `CMAKE_CXX_COMPILER_VERSION`
5. 如果编译器是 GCC 且版本 < 8，用 `message(FATAL_ERROR ...)` 终止并说明原因
6. 如果编译器是 MSVC 且版本 < 19.20，同样终止
7. 编译器通过检测后，打印"编译器检查通过"

**提示：**

```cmake
# 版本比较
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND
   CMAKE_CXX_COMPILER_VERSION VERSION_LESS "8.0")
    message(FATAL_ERROR "GCC >= 8.0 是必需的，当前版本: ${CMAKE_CXX_COMPILER_VERSION}")
endif()
```

为什么 GCC 8.0？因为 GCC 8 是第一个完整支持 C++20 大部分特性的版本（虽然 Concepts 要到 GCC 10 才完整）。

---

### 练习 2：打印所有编译器和平台变量

**目标：** 在 configure 阶段输出所有与编译器、平台、构建类型相关的 CMake 变量。

**要求：**

1. 项目名为 `SystemReport`
2. 在 `project()` 之后组织输出，分 5 个板块：
   - **项目信息**：`PROJECT_NAME`、`PROJECT_VERSION`、`PROJECT_SOURCE_DIR`、`PROJECT_BINARY_DIR`、`CMAKE_PROJECT_NAME`
   - **编译器信息**：`CMAKE_CXX_COMPILER`、`CMAKE_CXX_COMPILER_ID`、`CMAKE_CXX_COMPILER_VERSION`、`CMAKE_CXX_COMPILER_FRONTEND_VARIANT`、`CMAKE_CXX_COMPILER_ABI`
   - **平台信息**：`CMAKE_SYSTEM_NAME`、`CMAKE_SYSTEM_VERSION`、`CMAKE_SYSTEM_PROCESSOR`、`CMAKE_HOST_SYSTEM_NAME`、`CMAKE_HOST_SYSTEM_PROCESSOR`、`CMAKE_CROSSCOMPILING`
   - **标准信息**：`CMAKE_CXX_STANDARD`、`CMAKE_CXX_STANDARD_REQUIRED`、`CMAKE_CXX_EXTENSIONS`（注意：`project()` 之后这些可能是空的——解释为什么）
   - **构建类型信息**：`CMAKE_BUILD_TYPE`、`CMAKE_CONFIGURATION_TYPES`、`CMAKE_GENERATOR`
3. 每个变量使用 `message(STATUS "  VAR_NAME = ${VAR_NAME}")` 格式
4. 添加一个 `add_custom_target(info)` 目标，可以用 `cmake --build build --target info` 再次打印（用 `cmake -E echo`）

**提示：** `CMAKE_CXX_STANDARD` 在 `project()` 刚结束时为空是正常的——因为此时还没有任何 target 设置了标准。这个变量本身不自动设置，需要手动 `set()` 或通过 target 属性间接生效。

---

### 练习 3：为 GCC、MSVC、Clang 分别配置编译选项

**目标：** 创建 `CompilerFlags` 项目，根据不同的编译器 ID 应用不同的警告和优化配置。

**要求：**

1. 项目名 `CompilerFlags`，只使用 C++
2. 创建一个 library target `core_lib`（`add_library(core_lib core.cpp)`）
3. 创建一个 executable target `main_app`（链接 `core_lib`）
4. 为以下编译器分别设置编译选项：

   | 编译器 | 警告标志 | 优化/调试标志 | 定义 |
   |--------|---------|---------------|------|
   | **GCC** | `-Wall -Wextra -Wpedantic -Wshadow` | Debug: `-Og -g`, Release: `-O3 -DNDEBUG -flto` | `COMPILER_IS_GCC` |
   | **MSVC** | `/W4 /permissive-` | Debug: `/Od /Zi`, Release: `/O2 /GL` | `COMPILER_IS_MSVC` |
   | **Clang** | `-Wall -Wextra -Wpedantic` | Debug: `-O0 -g`, Release: `-O3 -DNDEBUG` | `COMPILER_IS_CLANG` |

5. 使用生成器表达式 `$<CONFIG:Debug>` 和 `$<CONFIG:Release>` 区分 Debug/Release 选项
6. **不允许**使用 `CMAKE_CXX_FLAGS`——全部通过 `target_compile_options()` 和 `target_compile_definitions()`
7. 添加一个 `message` 在配置结束时打印所用编译器及应用的标志概览

**提示（生成器表达式示例）：**

```cmake
target_compile_options(core_lib PRIVATE
    $<$<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Debug>>:-Og -g>
    $<$<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Release>>:-O3 -flto>
)
```


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(Cpp20Project VERSION 0.1.0 LANGUAGES CXX)
>
> # 编译器版本检查
> if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND
>    CMAKE_CXX_COMPILER_VERSION VERSION_LESS "8.0")
>     message(FATAL_ERROR
>         "GCC >= 8.0 is required for C++20 support.\n"
>         "Current: GCC ${CMAKE_CXX_COMPILER_VERSION}")
> endif()
>
> if(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC" AND
>    CMAKE_CXX_COMPILER_VERSION VERSION_LESS "19.20")
>     message(FATAL_ERROR
>         "MSVC >= 19.20 (VS 2019 16.0) is required for C++20 support.\n"
>         "Current: MSVC ${CMAKE_CXX_COMPILER_VERSION}")
> endif()
>
> message(STATUS "编译器检查通过: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
>
> # Target 定义
> add_executable(cpp20_demo main.cpp)
> target_compile_features(cpp20_demo PRIVATE cxx_std_20)
> set_target_properties(cpp20_demo PROPERTIES
>     CXX_STANDARD_REQUIRED ON
>     CXX_EXTENSIONS OFF
> )
> ```
>
> **`main.cpp`：**
> ```cpp
> #include <iostream>
> #include <vector>
> #include <ranges>
>
> int main() {
>     auto nums = std::views::iota(1, 11)
>               | std::views::filter([](int n) { return n % 2 == 0; })
>               | std::views::transform([](int n) { return n * n; });
>     for (int n : nums)
>         std::cout << n << " ";
>     std::cout << "\n";
>     return 0;
> }
> ```
>
> **关键点：** `target_compile_features(cpp20_demo PRIVATE cxx_std_20)` 表达意图而非硬编码 `-std=c++20`——CMake 自动映射到正确的编译器标志。`CXX_STANDARD_REQUIRED ON` 确保不支持时配置失败而非静默降级。

> [!tip]- 练习 2 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(SystemReport VERSION 1.0 LANGUAGES CXX)
>
> message(STATUS "========== 项目信息 ==========")
> message(STATUS "  PROJECT_NAME           = ${PROJECT_NAME}")
> message(STATUS "  PROJECT_VERSION        = ${PROJECT_VERSION}")
> message(STATUS "  PROJECT_SOURCE_DIR     = ${PROJECT_SOURCE_DIR}")
> message(STATUS "  PROJECT_BINARY_DIR     = ${PROJECT_BINARY_DIR}")
> message(STATUS "  CMAKE_PROJECT_NAME     = ${CMAKE_PROJECT_NAME}")
>
> message(STATUS "========== 编译器信息 ==========")
> message(STATUS "  CMAKE_CXX_COMPILER              = ${CMAKE_CXX_COMPILER}")
> message(STATUS "  CMAKE_CXX_COMPILER_ID           = ${CMAKE_CXX_COMPILER_ID}")
> message(STATUS "  CMAKE_CXX_COMPILER_VERSION      = ${CMAKE_CXX_COMPILER_VERSION}")
> message(STATUS "  CMAKE_CXX_COMPILER_FRONTEND_VARIANT = ${CMAKE_CXX_COMPILER_FRONTEND_VARIANT}")
> message(STATUS "  CMAKE_CXX_COMPILER_ABI          = ${CMAKE_CXX_COMPILER_ABI}")
>
> message(STATUS "========== 平台信息 ==========")
> message(STATUS "  CMAKE_SYSTEM_NAME           = ${CMAKE_SYSTEM_NAME}")
> message(STATUS "  CMAKE_SYSTEM_VERSION        = ${CMAKE_SYSTEM_VERSION}")
> message(STATUS "  CMAKE_SYSTEM_PROCESSOR      = ${CMAKE_SYSTEM_PROCESSOR}")
> message(STATUS "  CMAKE_HOST_SYSTEM_NAME      = ${CMAKE_HOST_SYSTEM_NAME}")
> message(STATUS "  CMAKE_HOST_SYSTEM_PROCESSOR = ${CMAKE_HOST_SYSTEM_PROCESSOR}")
> message(STATUS "  CMAKE_CROSSCOMPILING        = ${CMAKE_CROSSCOMPILING}")
>
> message(STATUS "========== C++ 标准信息 ==========")
> message(STATUS "  CMAKE_CXX_STANDARD           = '${CMAKE_CXX_STANDARD}'")
> message(STATUS "  CMAKE_CXX_STANDARD_REQUIRED  = ${CMAKE_CXX_STANDARD_REQUIRED}")
> message(STATUS "  CMAKE_CXX_EXTENSIONS         = ${CMAKE_CXX_EXTENSIONS}")
> message(STATUS "  注意：project() 之后这些变量为空，因为还没有 target 设置标准。")
> message(STATUS "  CMAKE_CXX_STANDARD 不会自动设置——需要通过 set() 或 target 属性。")
>
> message(STATUS "========== 构建类型信息 ==========")
> message(STATUS "  CMAKE_BUILD_TYPE          = ${CMAKE_BUILD_TYPE}")
> message(STATUS "  CMAKE_CONFIGURATION_TYPES = ${CMAKE_CONFIGURATION_TYPES}")
> message(STATUS "  CMAKE_GENERATOR           = ${CMAKE_GENERATOR}")
>
> # 自定义 target 再次打印
> add_custom_target(info
>     COMMAND ${CMAKE_COMMAND} -E echo "=== System Report ==="
>     COMMAND ${CMAKE_COMMAND} -E echo "Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}"
>     COMMAND ${CMAKE_COMMAND} -E echo "System: ${CMAKE_SYSTEM_NAME} ${CMAKE_SYSTEM_PROCESSOR}"
>     COMMAND ${CMAKE_COMMAND} -E echo "Build type: ${CMAKE_BUILD_TYPE}"
>     VERBATIM
> )
> ```

> [!tip]- 练习 3 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(CompilerFlags VERSION 1.0 LANGUAGES CXX)
>
> add_library(core_lib core.cpp)
> add_executable(main_app main.cpp)
> target_link_libraries(main_app PRIVATE core_lib)
>
> # === GCC ===
> if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
>     target_compile_options(core_lib PRIVATE
>         -Wall -Wextra -Wpedantic -Wshadow
>         $<$<CONFIG:Debug>:-Og -g>
>         $<$<CONFIG:Release>:-O3 -DNDEBUG -flto>
>     )
>     target_compile_definitions(core_lib PRIVATE COMPILER_IS_GCC)
>     message(STATUS "Compiler: GCC — Wall Wextra Wpedantic Wshadow")
>
> # === MSVC ===
> elseif(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
>     target_compile_options(core_lib PRIVATE
>         /W4 /permissive-
>         $<$<CONFIG:Debug>:/Od /Zi>
>         $<$<CONFIG:Release>:/O2 /GL>
>     )
>     target_compile_definitions(core_lib PRIVATE COMPILER_IS_MSVC)
>     message(STATUS "Compiler: MSVC — /W4 /permissive-")
>
> # === Clang (includes AppleClang via MATCHES) ===
> elseif(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
>     target_compile_options(core_lib PRIVATE
>         -Wall -Wextra -Wpedantic
>         $<$<CONFIG:Debug>:-O0 -g>
>         $<$<CONFIG:Release>:-O3 -DNDEBUG>
>     )
>     target_compile_definitions(core_lib PRIVATE COMPILER_IS_CLANG)
>     message(STATUS "Compiler: Clang — Wall Wextra Wpedantic")
> endif()
> ```
>
> **`core.cpp`（最小化验证）：**
> ```cpp
> #include <iostream>
>
> void core_info() {
> #if defined(COMPILER_IS_GCC)
>     std::cout << "Built with GCC\n";
> #elif defined(COMPILER_IS_MSVC)
>     std::cout << "Built with MSVC\n";
> #elif defined(COMPILER_IS_CLANG)
>     std::cout << "Built with Clang\n";
> #endif
> }
> ```
>
> **`main.cpp`：**
> ```cpp
> void core_info();
> int main() { core_info(); return 0; }
> ```
>
> **关键点：** 生成器表达式 `$<$<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Debug>>:-Og -g>` 在生成阶段按配置展开，避免全局污染 `CMAKE_CXX_FLAGS`。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方文档 — project() 命令](https://cmake.org/cmake/help/latest/command/project.html)
- [CMake 官方文档 — enable_language() 命令](https://cmake.org/cmake/help/latest/command/enable_language.html)
- [CMake 官方文档 — 编译器标识变量](https://cmake.org/cmake/help/latest/variable/CMAKE_LANG_COMPILER_ID.html)
- [CMake 官方文档 — target_compile_features()](https://cmake.org/cmake/help/latest/command/target_compile_features.html)
- [CMake 官方文档 — 支持的编译特性列表](https://cmake.org/cmake/help/latest/prop_gbl/CMAKE_CXX_KNOWN_FEATURES.html)
- [CMake 官方文档 — WriteCompilerDetectionHeader 模块](https://cmake.org/cmake/help/latest/module/WriteCompilerDetectionHeader.html)
- [CMake 官方文档 — CheckCXXCompilerFlag 模块](https://cmake.org/cmake/help/latest/module/CheckCXXCompilerFlag.html)
- [It's Time To Do CMake Right — Pablo Arias](https://pabloariasal.github.io/2018/02/19/its-time-to-do-cmake-right/) — 关于 target 级属性与 C++ 标准设置的经典文章
- [Modern CMake — Henry Schreiner](https://cliutils.gitlab.io/modern-cmake/) — Modern CMake 理念的完整指南
- [C++ Standards Support in GCC](https://gcc.gnu.org/projects/cxx-status.html) — GCC 各版本 C++ 标准支持状态
- [MSVC C++ Standards Conformance](https://learn.microsoft.com/en-us/cpp/overview/visual-cpp-language-conformance) — MSVC 标准符合性
- 下一教程：[[06-static-shared-object-libraries]]——学习如何创建库

---

## 常见陷阱

### 1. 设置 CMAKE_CXX_STANDARD 全局而非 per-target

```cmake
# ❌ 这是全局变量，影响所有 target
set(CMAKE_CXX_STANDARD 17)

# ✅ 应该对每个 target 单独设置
set_target_properties(my_app PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON)
# 或更现代的方式：
target_compile_features(my_app PUBLIC cxx_std_17)
```

为什么有害？假设你的项目同时构建一个需要 C++20 的库和一个只需 C++17 的可执行文件——全局设置要么过严（强迫库降到 C++17），要么过宽（让可执行文件依赖 C++20 特性但实际不用）。per-target 设置让每个目标声明自己真正需要的标准。

### 2. 忘记设置 CMAKE_CXX_STANDARD_REQUIRED

```cmake
set(CMAKE_CXX_STANDARD 20)
# 漏掉了 CMAKE_CXX_STANDARD_REQUIRED ON
```

没有 `REQUIRED` 时，CMake 会**静默降级**到编译器能支持的最高标准。你的代码里用了 `concepts`（C++20），但编译器不支持 C++20——CMake 不会报错，而是默默用 C++17 编译。结果是**编译错误发生在源码层面**（编译器不认识 `concept` 关键字），而不是 CMake 配置阶段就阻止。

正确的做法：

```cmake
set_target_properties(my_app PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
)
```

### 3. 使用 CMAKE_CXX_FLAGS 而不是 target_compile_options

```cmake
# ❌ 字符串拼接，全局影响
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra")

# ✅ target 级 + 生成器表达式
target_compile_options(my_app PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Wall -Wextra>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)
```

`CMAKE_CXX_FLAGS` 是一个全局字符串，在大型项目中会被多个 `CMakeLists.txt` 反复追加，最终值难以追踪。使用 `target_compile_options()` 结合生成器表达式，可以精确控制每个目标、每个编译器的标志，且不污染其他 target。

### 4. 混淆 CMAKE_SOURCE_DIR 和 PROJECT_SOURCE_DIR

```cmake
# ❌ 如果你的项目作为子项目被 add_subdirectory() 引入，这个路径是别人的
include_directories(${CMAKE_SOURCE_DIR}/include)

# ✅ 始终指向你自己的项目根目录
target_include_directories(my_lib PUBLIC ${PROJECT_SOURCE_DIR}/include)
```

当你的项目被别人通过 `add_subdirectory()` 引入时（如通过 FetchContent），`CMAKE_SOURCE_DIR` 指向**顶层项目**的源码目录，而非你的。使用 `PROJECT_SOURCE_DIR` 始终指向你自己的项目根目录。

### 5. 在 project() 之前访问编译器变量

```cmake
cmake_minimum_required(VERSION 3.24)

# ❌ 此时 project() 还没调用，编译器检测未执行
message(STATUS "Compiler: ${CMAKE_CXX_COMPILER_ID}")

project(MyApp LANGUAGES CXX)
```

`project()` 之前，`CMAKE_CXX_COMPILER_ID` 等所有编译器变量都**未设置**。如果需要提前访问（比如根据编译器选择不同的 LANGUAGES 参数），可以在 `project()` 之前使用 `enable_language()`。

### 6. 子目录 project() 的版本覆盖

```cmake
# 顶层: project(MyApp VERSION 1.0)
# 子目录: project(sub_lib VERSION 3.0)
add_subdirectory(subdir)
# 此时 ${PROJECT_VERSION} 是 "1.0"，因为子 project() 只影响自己的作用域
```

子目录中 `project()` 设置的 `PROJECT_VERSION` 仅在该子目录和其 `add_subdirectory()` 子目录中有效，不会泄漏回父目录。

### 7. 不检查 CMAKE_CXX_COMPILER_ID 就假定编译器特性

```cmake
# ❌ 假设所有编译器都支持 -Wall
target_compile_options(my_app PRIVATE -Wall)

# ✅ 先检查或用生成器表达式过滤
include(CheckCXXCompilerFlag)
check_cxx_compiler_flag("-Wall" HAS_WALL)
if(HAS_WALL)
    target_compile_options(my_app PRIVATE -Wall)
endif()
```

直接写 `-Wall` 在 MSVC 上虽不会导致编译失败（MSVC 会警告未知选项），但更严谨的做法是先检查或使用生成器表达式按编译器过滤。

### 8. 忘记 project() 设置编译器语言

```cmake
cmake_minimum_required(VERSION 3.24)
# 忘记调用 project()！

add_executable(my_app main.cpp)   # 错误：CMake 不知道用什么编译器
```

在 CMake 3.x 中，缺少 `project()` 不会立即报错——CMake 会使用默认语言 `C` 和 `CXX`。但 CMake 4.0 起，缺少 `project()` 调用且没有 `enable_language()` 会导致错误。**始终在第一个 `add_executable`/`add_library` 之前调用 `project()`。**
