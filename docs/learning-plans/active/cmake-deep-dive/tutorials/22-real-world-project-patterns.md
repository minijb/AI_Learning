---
title: 真实项目模式与最佳实践
updated: 2026-06-10
tags: [cmake, best-practices, project-structure, ci-cd]
---

# 真实项目模式与最佳实践

> 前置教程: [[07-target-link-libraries-and-transitive-deps]] | [[10-fetchcontent-dependency-management]] | [[11-install-and-export-targets]]
> 预计时间: 60min
> 目标水平: 精通 — 能设计生产级 CMake 构建系统

---

## 概念

### 为什么需要"真实项目模式"？

单个 `CMakeLists.txt` 文件可以应付几十个源文件的小项目。但当项目发展到：
- 多个可执行目标和库
- 第三方依赖
- 安装/打包需求
- CI/CD 自动化构建
- 多平台/多编译器支持
- 团队协作

时，**结构化的项目布局**和**一致的构建模式**就从"可选"变成"必需"。

本教程总结的是社区在 CMake 3.x 时代经过大量实践沉淀下来的最佳模式——**Modern CMake + 结构化项目布局**。这不是某个人的偏好，而是 `fmt`、`spdlog`、`LLVM`、`grpc` 等数千个 C++ 项目的共同收敛点。

### Modern CMake 的三个核心思想

1. **Target-First（目标优先）**：一切操作绑定到 target（`target_*` 命令），不用目录级命令（`include_directories`、`add_definitions`）。Target 是 CMake 中的一等公民。

2. **Public/Private/Interface 三层接口隔离**：用 `PUBLIC`/`PRIVATE`/`INTERFACE` 精确控制属性和依赖的传递范围。使用者只看 `PUBLIC` 和 `INTERFACE`，内部只关心 `PRIVATE`。

3. **配置时间与构建时间分离**：`configure` 阶段做决策（哪些源文件？选哪个后端？），`generate` 阶段生成 buildsystem，`build` 阶段执行实际的编译链接。绝不把构建时间的操作混入配置时间。

> [!tip] CMake 3.24+ 是基准线
> 本教程所有示例假设 CMake 3.24 或更高版本。这个版本的 CMake 包含了 `FetchContent` 的成熟接口、完整的 preset 支持、`CMAKE_CXX_STANDARD` 的正确传播等关键特性。

---

## 项目目录结构

### 标准布局

```text
project-root/
├── CMakeLists.txt                  ← 顶层：project()、option()、add_subdirectory()
├── CMakePresets.json               ← CI/团队 构建预设
├── cmake/                          ← 自定义 Find 模块、工具链、函数
│   ├── FindMyDep.cmake
│   └── MyProjectFunctions.cmake
├── include/                        ← 公共头文件（安装后对外可见）
│   └── myproject/
│       ├── core.h
│       ├── util.h
│       └── version.h.in           ← configure_file 模板
├── src/                            ← 私有源文件
│   ├── CMakeLists.txt              ← 定义 myproject 库 target
│   ├── core.cpp
│   ├── util.cpp
│   └── internal/
│       └── impl.h                  ← 私有头文件，
│                                   ← 不安装
├── apps/                           ← 可执行文件
│   ├── CMakeLists.txt
│   └── main.cpp
├── tests/                          ← 测试
│   ├── CMakeLists.txt
│   └── test_core.cpp
├── examples/                       ← 示例代码
│   ├── CMakeLists.txt
│   └── example_basic.cpp
├── extern/                         ← 第三方依赖（submodule / FetchContent 落地）
│   └── CMakeLists.txt
├── docs/
│   └── CMakeLists.txt              ← 文档构建（可选，如 Doxygen）
└── .github/workflows/              ← CI 配置
    └── build.yml
```

### 关键分工

| 目录 | 职责 | 是否安装 |
|------|------|---------|
| `include/myproject/` | 公共 API 头文件 | 是 |
| `src/` | 库的实现（含私有头文件） | 仅编译产物 |
| `apps/` | 可执行文件入口 | 可选 |
| `tests/` | 测试代码 | 否 |
| `examples/` | 示例代码 | 否 |
| `extern/` | 第三方源码 | 否 |
| `cmake/` | 构建辅助脚本 | 否 |

> [!important] 命名空间的物理隔离
> 注意 `include/myproject/` 而不是 `include/`。这种嵌套目录在消费者 `#include <myproject/core.h>` 时提供命名空间隔离，避免 `core.h` 这种通用文件名冲突。

---

## 顶层 CMakeLists.txt 模式

这是整个构建系统的入口。一个良好的顶层文件应该是**声明式的**——只做顶层决策，不做具体编译细节。

### 完整模板

```cmake
# ============================================================
# 顶层 CMakeLists.txt - myproject
# ============================================================

# 1. 版本策略锁定
cmake_minimum_required(VERSION 3.24...3.31)

# 2. 项目声明
project(myproject
    VERSION 1.2.3
    DESCRIPTION "A Modern CMake project template"
    HOMEPAGE_URL "https://github.com/user/myproject"
    LANGUAGES CXX
)

# 3. 全局默认值（仅设置影响所有 target 的通用属性）
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 4. 导出 compile_commands.json 供 clangd/clang-tidy 等工具使用
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# 5. 构建选项
option(BUILD_TESTING "Build tests" ON)
option(BUILD_EXAMPLES "Build example programs" OFF)
option(BUILD_SHARED_LIBS "Build shared libraries" OFF)
option(ENABLE_COVERAGE "Enable code coverage instrumentation" OFF)

# 依赖选项
option(USE_SYSTEM_FMT "Use system-installed fmt library" OFF)

# 6. 自定义 CMake 模块路径
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

# 7. 包含常用模块
include(GNUInstallDirs)
include(CTest)                    # 启用测试
include(CMakePackageConfigHelpers)

# 8. 决定库的类型
if(BUILD_SHARED_LIBS)
    set(MYPROJECT_LIB_TYPE SHARED)
else()
    set(MYPROJECT_LIB_TYPE STATIC)
endif()

# 9. 添加子目录
add_subdirectory(src)             # 核心库
add_subdirectory(apps)            # 可执行文件
add_subdirectory(extern)          # 第三方依赖

if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()

if(BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# 10. 特性摘要
include(FeatureSummary)
feature_summary(WHAT ALL
    DESCRIPTION "Build configuration:"
    FATAL_ON_MISSING_REQUIRED_PACKAGES
)

# 11. 安装
include(cmake/InstallRules.cmake)
```

### 逐行解读

**`cmake_minimum_required(VERSION 3.24...3.31)`**

范围语法 `A...B` 表示"至少需要 A，已知兼容到 B"。这比单一版本更精确：它告诉 CMake 你已测试过直到 B 版本的兼容性，CMake 可以为这个范围启用更精确的策略行为。

**`project()` 命令**

CMake 3.x 的 `project()` 可以做多重工作：
- `VERSION` 会设置 `PROJECT_VERSION`、`PROJECT_VERSION_MAJOR`、`PROJECT_VERSION_MINOR`、`PROJECT_VERSION_PATCH` 变量
- `DESCRIPTION` 设置 `PROJECT_DESCRIPTION`
- `HOMEPAGE_URL` 设置 `PROJECT_HOMEPAGE_URL`
- `LANGUAGES CXX` 启用 C++ 编译器（跳过 C 编译器检测，加速配置）

**`CMAKE_CXX_STANDARD` vs `target_compile_features`**

> [!warning] 不推荐的写法
>
> ```cmake
> # ❌ 不要用目录级别的变量控制标准
> set(CMAKE_CXX_STANDARD 20)
> ```
>
> 更好的方式是按 target 指定：
>
> ```cmake
> target_compile_features(myproject PUBLIC cxx_std_20)
> ```

但实践中，顶层 `CMAKE_CXX_STANDARD` 作为**项目级默认值**是可接受的——只要每个子目录的 target 没有更高要求。如果某个 target 需要 C++23，它应该显式设置自己的 `target_compile_features`。

---

## `add_subdirectory` 组织模式

### 原则：每个目录一个 `CMakeLists.txt`

每个 `add_subdirectory(dir)` 调用会进入 `dir/CMakeLists.txt`，在该文件中定义该目录的 target。这使得**文件系统的目录结构**和**构建系统的模块边界**保持一致。

### `src/CMakeLists.txt` — 核心库

```cmake
# src/CMakeLists.txt

# 收集源文件 —— 显式列出，不用 GLOB
set(MYPROJECT_SOURCES
    core.cpp
    util.cpp
    internal/impl.cpp
)

# 公共头文件（需要安装的）
set(MYPROJECT_PUBLIC_HEADERS
    ${PROJECT_SOURCE_DIR}/include/myproject/core.h
    ${PROJECT_SOURCE_DIR}/include/myproject/util.h
)

# 定义库 target
add_library(myproject ${MYPROJECT_LIB_TYPE})
target_sources(myproject
    PRIVATE ${MYPROJECT_SOURCES}
    PUBLIC  FILE_SET HEADERS
            BASE_DIRS ${PROJECT_SOURCE_DIR}/include
            FILES ${MYPROJECT_PUBLIC_HEADERS}
)

# 包含目录 —— 依赖者通过 myproject 的 PUBLIC 属性自动获取 include/
target_include_directories(myproject
    PUBLIC
        $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}      # 内部实现可以 #include "internal/impl.h"
)

# 编译特性
target_compile_features(myproject PUBLIC cxx_std_20)

# 链接依赖
target_link_libraries(myproject
    PUBLIC
        fmt::fmt             # 公共头文件里用了 fmt
    PRIVATE
        myproject::internal  # 内部辅助库
)

# 别名 —— 方便 find_package 消费者
add_library(myproject::myproject ALIAS myproject)
```

### `apps/CMakeLists.txt` — 可执行文件

```cmake
# apps/CMakeLists.txt

add_executable(myapp main.cpp)
target_link_libraries(myapp PRIVATE myproject::myproject)

# 将可执行文件安装到 bin/
install(TARGETS myapp
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
```

### `tests/CMakeLists.txt` — 测试

```cmake
# tests/CMakeLists.txt

# 假设项目使用 Catch2
find_package(Catch2 3 REQUIRED)

add_executable(test_core test_core.cpp)
target_link_libraries(test_core PRIVATE myproject::myproject Catch2::Catch2)

include(Catch)
catch_discover_tests(test_core)

add_executable(test_util test_util.cpp)
target_link_libraries(test_util PRIVATE myproject::myproject Catch2::Catch2)
catch_discover_tests(test_util)
```

### `extern/CMakeLists.txt` — 第三方依赖

```cmake
# extern/CMakeLists.txt

include(FetchContent)

# --- fmt ---
FetchContent_Declare(fmt
    GIT_REPOSITORY  https://github.com/fmtlib/fmt.git
    GIT_TAG         11.1.4
    GIT_SHALLOW     TRUE
)
FetchContent_MakeAvailable(fmt)

# --- spdlog ---
FetchContent_Declare(spdlog
    GIT_REPOSITORY  https://github.com/gabime/spdlog.git
    GIT_TAG         v1.15.1
    GIT_SHALLOW     TRUE
)
set(SPDLOG_FMT_EXTERNAL ON CACHE BOOL "" FORCE)  # 使用 FetchContent 的 fmt
FetchContent_MakeAvailable(spdlog)
```

---

## `option()` 与构建开关

### 标准模式

```cmake
# 建议：BUILD_TESTING 总是默认 ON
option(BUILD_TESTING "Build the test suite" ON)

# 示例和 benchmark 默认 OFF —— 外部使用者不关心
option(BUILD_EXAMPLES "Build example programs" OFF)
option(BUILD_BENCHMARKS "Build benchmark programs" OFF)

# 库的类型切换
option(BUILD_SHARED_LIBS "Build shared libraries instead of static" OFF)

# 可选特性
option(ENABLE_IPO "Enable interprocedural optimization (LTO)" OFF)
option(ENABLE_SANITIZERS "Enable address/undefined behavior sanitizers" OFF)
```

### 在代码中使用选项

```cmake
if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()

if(ENABLE_IPO)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT ipo_supported OUTPUT ipo_output)
    if(ipo_supported)
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)
    else()
        message(WARNING "IPO not supported: ${ipo_output}")
    endif()
endif()
```

### `CMakeDependentOption` — 条件选项

有些选项只有在另一个选项启用时才有意义：

```cmake
include(CMakeDependentOption)

cmake_dependent_option(BUILD_TEST_COVERAGE
    "Enable code coverage for tests" OFF
    "BUILD_TESTING" OFF
)
# 语义：只有当 BUILD_TESTING=ON 时，BUILD_TEST_COVERAGE 才可配置；
#       否则强制为 OFF

cmake_dependent_option(ENABLE_TLS
    "Enable TLS support (requires OpenSSL)" ON
    "OPENSSL_FOUND" OFF
)
```

---

## 安装系统

### `GNUInstallDirs` 标准路径

```cmake
include(GNUInstallDirs)

# 这些变量被自动定义：
# CMAKE_INSTALL_BINDIR       → bin/
# CMAKE_INSTALL_LIBDIR       → lib/ (或 lib64/)
# CMAKE_INSTALL_INCLUDEDIR   → include/
# CMAKE_INSTALL_DATADIR      → share/
# CMAKE_INSTALL_DOCDIR       → share/doc/
# ...
```

> [!tip] 跨平台的 `LIBDIR`
> 在 Debian 系系统上 `GNUInstallDirs` 会将 `CMAKE_INSTALL_LIBDIR` 设为 `lib/x86_64-linux-gnu/`，这符合 Multiarch 规范。如果你的包不使用 Multiarch，可以在 `include(GNUInstallDirs)` 之前设置 `set(CMAKE_INSTALL_LIBDIR lib)` 覆盖它。

### `cmake/InstallRules.cmake` — 集中安装规则

```cmake
# cmake/InstallRules.cmake

# --- 安装 target ---
install(TARGETS myproject myapp
    EXPORT  myprojectTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    FILE_SET HEADERS
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/myproject
)

# --- 生成并安装 CMake 配置文件 ---
include(CMakePackageConfigHelpers)

# 版本文件（兼容性检查）
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/myprojectConfigVersion.cmake"
    VERSION       ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion   # 主版本相同 → 兼容
)

# 配置模板
configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/myprojectConfig.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/myprojectConfig.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_DATADIR}/myproject/cmake"
)

# 安装 target 导出文件
install(EXPORT myprojectTargets
    FILE      myprojectTargets.cmake
    NAMESPACE myproject::
    DESTINATION "${CMAKE_INSTALL_DATADIR}/myproject/cmake"
)

# 安装版本文件和配置文件
install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/myprojectConfigVersion.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/myprojectConfig.cmake"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/myproject/cmake"
)

# --- 安装附加文件 ---
install(FILES LICENSE
    DESTINATION ${CMAKE_INSTALL_DOCDIR}
    RENAME LICENSE-myproject.txt
)
```

### `cmake/myprojectConfig.cmake.in` — 配置文件模板

```cmake
# cmake/myprojectConfig.cmake.in

@PACKAGE_INIT@

# 引入依赖
include(CMakeFindDependencyMacro)
find_dependency(fmt)

# 加载 target 定义
include("${CMAKE_CURRENT_LIST_DIR}/myprojectTargets.cmake")

# 检查组件
check_required_components(myproject)
```

消费者使用：

```cmake
find_package(myproject 1.2 REQUIRED)
target_link_libraries(myapp PRIVATE myproject::myproject)
```

一切都透明。

---

## 依赖管理策略

### 选择矩阵

| 依赖类型 | 策略 | 命令 |
|---------|------|------|
| 系统级库（OpenSSL、ZLIB） | `find_package` | `find_package(OpenSSL REQUIRED)` |
| 项目内子模块 | `add_subdirectory` | `add_subdirectory(libs/myutil)` |
| 可内嵌的第三方库 | `FetchContent` | `FetchContent_Declare` + `FetchContent_MakeAvailable` |
| 预编译的二进制包 | `find_package` + 手动路径 | `find_package(Pkg PATHS /opt/pkg)` |
| 可选依赖 | `find_package` + `OPTIONAL_COMPONENTS` | `find_package(Qt6 OPTIONAL_COMPONENTS Widgets)` |

### `FetchContent` 的最佳实践

```cmake
# 用 FetchContent 声明，但不立即下载
FetchContent_Declare(fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG        11.1.4
    GIT_SHALLOW    TRUE
    GIT_PROGRESS   TRUE     # 显示下载进度
    SYSTEM          # CMake 3.25+: 标记为系统依赖，抑制警告
)

# 控制第三方库的特性
set(FMT_DOC OFF CACHE BOOL "" FORCE)
set(FMT_TEST OFF CACHE BOOL "" FORCE)
set(FMT_INSTALL OFF CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(fmt)
```

> [!warning] `FetchContent` 的陷阱
> `FetchContent_MakeAvailable` 将第三方库的 `CMakeLists.txt` 合并到你的构建中。这意味着：
> - 它们的 `option()` 会污染你的缓存
> - 它们的 `install()` 规则会包含在你的安装中（除非你用 `SYSTEM` 关键字或手动置顶 `*_INSTALL OFF`）
> - 如果两个依赖都声明了相同的库，CMake 会使用先声明的版本
>
> 如果这是问题，考虑使用 `find_package` + 包管理器（vcpkg、Conan）的组合策略。

### `find_package` 的系统级使用

```cmake
# 先尝试系统安装的版本
find_package(fmt 11 QUIET)

if(NOT fmt_FOUND)
    message(STATUS "fmt not found via find_package, using FetchContent")
    include(FetchContent)
    FetchContent_Declare(fmt ...)
    FetchContent_MakeAvailable(fmt)
endif()
```

---

## 编译性能优化

### 预编译头（Precompiled Headers）

从 CMake 3.16 开始支持，适用于编译时间受头文件解析主导的项目。

```cmake
target_precompile_headers(myproject
    PRIVATE
        <vector>
        <string>
        <memory>
        <fmt/core.h>
        <fmt/format.h>
)

# 可复用预编译头列表
set(MYPROJECT_PCH_HEADERS
    <vector>
    <string>
    <map>
    <memory>
    <optional>
    <fmt/core.h>
)

target_precompile_headers(myproject PRIVATE ${MYPROJECT_PCH_HEADERS})
target_precompile_headers(myapp      PRIVATE ${MYPROJECT_PCH_HEADERS})
```

> [!tip] PCH 适用性
> 预编译头适合**包含大量通用头文件、且源文件之间共享这些头文件**的项目。如果你的项目极度模块化（每个 `.cpp` 有独特的一组 `#include`），PCH 收益有限，甚至可能更慢。

### Unity Build（联合编译）

从 CMake 3.16 开始原生支持。

```cmake
# 在 CMakeLists.txt 或 preset 中设置
set(CMAKE_UNITY_BUILD ON)
set(CMAKE_UNITY_BUILD_BATCH_SIZE 16)  # 每 16 个源文件合并为一个翻译单元
```

或者按 target 控制：

```cmake
set_target_properties(myproject PROPERTIES
    UNITY_BUILD ON
    UNITY_BUILD_BATCH_SIZE 8
)
```

> [!warning] Unity Build 的副作用
> Unity Build 将多个 `.cpp` 合并为一个编译单元。这意味着：
> - 匿名命名空间、文件级 `static` 函数可能冲突
> - `#define` 宏可能意外"泄漏"到相邻文件
> - 包含顺序变得敏感
>
> **建议**：日常开发不用 Unity Build；CI 中用 Unity Build 加快干净构建；用非 Unity Build 做最终验证。

### `compile_commands.json`

```cmake
# 顶层 CMakeLists.txt
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
```

这会在构建目录生成 `compile_commands.json`，供以下工具使用：

| 工具 | 用途 |
|------|------|
| `clangd` | LSP 服务器（代码补全、跳转、诊断） |
| `clang-tidy` | 静态分析 |
| `clang-check` | 快速语法检查 |
| `include-what-you-use` | 头文件包含分析 |
| `cppcheck` | 静态分析（CMake 集成） |

---

## 静态分析器集成

### `clang-tidy`

```cmake
# 顶层 CMakeLists.txt
set(CMAKE_CXX_CLANG_TIDY
    clang-tidy;
    -header-filter=${CMAKE_SOURCE_DIR}/include/;
    -checks=*,-fuchsia-*,-llvmlibc-*,-modernize-use-trailing-return-type;
    -warnings-as-errors=*
)
```

也可以在 preset 中设置，避免硬编码到 `CMakeLists.txt`：

```json
{
    "cacheVariables": {
        "CMAKE_CXX_CLANG_TIDY": "clang-tidy;-header-filter=${sourceDir}/include/;-checks=bugprone-*,performance-*,readability-*"
    }
}
```

### `cppcheck`

```cmake
set(CMAKE_CXX_CPPCHECK
    cppcheck;
    --enable=all;
    --suppress=missingIncludeSystem;
    --error-exitcode=1
)
```

### `include-what-you-use` (IWYU)

```cmake
set(CMAKE_CXX_INCLUDE_WHAT_YOU_USE
    include-what-you-use;
    -Xiwyu;--mapping_file=${CMAKE_SOURCE_DIR}/cmake/iwyu.imp
)
```

> [!important] 静态分析器的性能影响
> `CMAKE_CXX_CLANG_TIDY` 等变量会让编译器在每次编译后调用分析工具，显著增加构建时间。建议只在 CI 或专门的 `--preset lint` 中启用，不要在日常开发构建中开启。

---

## 版本管理

### 从 `project(VERSION ...)` 生成版本头文件

```cmake
# cmake/GenerateVersionHeader.cmake

function(generate_version_header TARGET)
    # 从 project() 命令获取版本
    set(VERSION_MAJOR ${PROJECT_VERSION_MAJOR})
    set(VERSION_MINOR ${PROJECT_VERSION_MINOR})
    set(VERSION_PATCH ${PROJECT_VERSION_PATCH})
    set(VERSION_TWEAK ${PROJECT_VERSION_TWEAK})

    # Git 信息
    execute_process(
        COMMAND git rev-parse --short HEAD
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        OUTPUT_VARIABLE GIT_COMMIT_HASH
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )

    execute_process(
        COMMAND git rev-parse --abbrev-ref HEAD
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        OUTPUT_VARIABLE GIT_BRANCH
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )

    if(NOT GIT_COMMIT_HASH)
        set(GIT_COMMIT_HASH "unknown")
        set(GIT_BRANCH "unknown")
    endif()

    configure_file(
        ${CMAKE_SOURCE_DIR}/include/myproject/version.h.in
        ${CMAKE_BINARY_DIR}/generated/myproject/version.h
        @ONLY
    )

    target_include_directories(${TARGET}
        PUBLIC ${CMAKE_BINARY_DIR}/generated
    )
endfunction()
```

模板 `include/myproject/version.h.in`：

```c
// include/myproject/version.h.in
#pragma once

#define MYPROJECT_VERSION_MAJOR @VERSION_MAJOR@
#define MYPROJECT_VERSION_MINOR @VERSION_MINOR@
#define MYPROJECT_VERSION_PATCH @VERSION_PATCH@
#define MYPROJECT_VERSION       "@PROJECT_VERSION@"
#define MYPROJECT_GIT_HASH      "@GIT_COMMIT_HASH@"
#define MYPROJECT_GIT_BRANCH    "@GIT_BRANCH@"
```

---

## 可视化依赖图

```bash
# 生成 Graphviz DOT 文件
cmake -B build --graphviz=build/deps.dot
# 渲染为 PNG（需要安装 Graphviz）
dot -Tpng build/deps.dot -o deps.png
```

也可以指定特定的 target：

```bash
cmake -B build --graphviz=build/deps.dot --graphviz=myproject
```

CMake 生成的 DOT 文件包含节点（target）和边（依赖关系），对理解大型项目的依赖拓扑非常有帮助。

---

## 源文件组织

### 为什么不用 `file(GLOB)`？

```cmake
# ❌ 不要这样做
file(GLOB_RECURSE MYPROJECT_SOURCES "src/*.cpp")
add_library(myproject ${MYPROJECT_SOURCES})
```

问题：
1. **新增/删除文件不会触发重新配置** —— CMake 不知道 glob 的结果变了，需要手动 `cmake --build . --target rebuild_cache`
2. **不可复现** —— 两个开发者可能看到不完全相同的源文件列表
3. **IDE 集成差** —— IDE 的 CMake 集成依赖于显式的源文件列表来展示项目树

```cmake
# ✅ 显式列出
set(MYPROJECT_SOURCES
    src/core.cpp
    src/util.cpp
    src/internal/impl.cpp
)
target_sources(myproject PRIVATE ${MYPROJECT_SOURCES})
```

> [!tip] 大量文件的折中方案
> 如果你的项目有数百个源文件且你确定不会用 glob，可以使用 `target_sources` 的 `FILE_SET` 来组织：
>
> ```cmake
> target_sources(myproject
>     PRIVATE
>         src/core.cpp
>         src/util.cpp
>         # ... more files
> )
> ```
>
> 也可以用脚本生成源文件列表（如 `ls src/*.cpp > sources.txt`），将生成过程从 CMake 中解耦。

---

## 依赖图的正确传递

### Target-Based 命令对照

| 旧命令（目录级） | 新命令（target 级） | 说明 |
|------------------|---------------------|------|
| `include_directories(dir)` | `target_include_directories(tgt ...)` | 每个 target 独立管理 include |
| `add_definitions(-DFOO)` | `target_compile_definitions(tgt ...)` | 编译宏绑定到 target |
| `link_libraries(lib)` | `target_link_libraries(tgt ...)` | 链接绑定到 target |
| `add_compile_options(-Wall)` | `target_compile_options(tgt ...)` | 编译选项绑定到 target |
| `set(CMAKE_CXX_STANDARD 17)` | `target_compile_features(tgt ...)` | C++ 标准绑定到 target |

> [!danger] 目录级命令的全局污染
> `include_directories()` 作用于**整个目录及其子目录**中的所有 target。这在大型项目中是 bug 工厂——一个目录加上去的 include path 会泄漏到完全无关的 target，导致本应编译失败的头文件冲突被悄悄掩盖。

### 正确的传递依赖

```cmake
# libA: 实现用 <vector>，头文件暴露 <string>
target_include_directories(libA
    PUBLIC  ${CMAKE_CURRENT_SOURCE_DIR}/include  # 头文件路径
)
target_link_libraries(libA
    PRIVATE vector_only_impl_lib   # 实现细节，不传递
    PUBLIC  fmt::fmt               # 头文件中用了 fmt，需要传递
)

# libB: 依赖 libA
target_link_libraries(libB
    PUBLIC libA                     # 自动获得 fmt::fmt 和 libA 的头文件路径
)

# myapp: 只链接 libB
target_link_libraries(myapp
    PRIVATE libB                    # 间接获得 libA、fmt、头文件路径 —— 全部自动
)
```

这就是 Modern CMake 最强大的特性：**传递依赖自动传播**。你只需要声明直接依赖，间接依赖自动到位。

---

## 配置时间 vs 构建时间

> [!important] 核心原则
> **配置阶段只做决策，构建阶段只做编译。**

### 正确的做法

```cmake
# ✅ 配置时间：决定用哪个源文件
if(WIN32)
    target_sources(myproject PRIVATE platform_win.cpp)
else()
    target_sources(myproject PRIVATE platform_unix.cpp)
endif()

# ✅ 构建时间：通过生成器表达式延迟到构建时
target_compile_definitions(myproject PRIVATE
    $<$<CONFIG:Debug>:DEBUG_ENABLED>
)
```

### 错误的做法

```cmake
# ❌ 在配置时间执行编译相关操作
execute_process(COMMAND ${CMAKE_CXX_COMPILER} ...)   # 这是配置时间！
```

配置时间的 `execute_process` 开销会在每次 CMake 配置时支付，而不是在 `cmake --build` 时。对于编译器探测、版本检测这类一次性操作可以接受，但绝不能用它做实际的编译工作。

---

## 代码示例

### 示例 1：完整的多目录项目

本示例演示一个完整的项目结构，包含核心库、命令行工具、测试，以及 `option()` 开关。

#### 目录结构

```text
ex01-myapp/
├── CMakeLists.txt
├── CMakePresets.json
├── cmake/
│   └── InstallRules.cmake
├── include/myapp/
│   ├── calc.h
│   └── version.h.in
├── src/
│   ├── CMakeLists.txt
│   └── calc.cpp
├── app/
│   ├── CMakeLists.txt
│   └── main.cpp
├── tests/
│   ├── CMakeLists.txt
│   └── test_calc.cpp
└── .gitignore
```

#### `CMakeLists.txt`（顶层）

```cmake
cmake_minimum_required(VERSION 3.24...3.31)

project(myapp
    VERSION 0.1.0
    DESCRIPTION "Demo: multi-directory Modern CMake project"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(BUILD_TESTING "Build the test suite" ON)
option(BUILD_SHARED_LIBS "Build shared libraries" OFF)
option(ENABLE_IPO "Enable LTO" OFF)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")

include(GNUInstallDirs)
include(CTest)
include(CMakePackageConfigHelpers)

if(ENABLE_IPO)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT ipo_supported)
    if(ipo_supported)
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)
    endif()
endif()

add_subdirectory(src)

add_subdirectory(app)

if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()

# 版本头文件
set(VERSION_HEADER_IN  "${CMAKE_SOURCE_DIR}/include/myapp/version.h.in")
set(VERSION_HEADER_OUT "${CMAKE_BINARY_DIR}/generated/myapp/version.h")

configure_file(${VERSION_HEADER_IN} ${VERSION_HEADER_OUT} @ONLY)

target_include_directories(myapp
    PUBLIC $<BUILD_INTERFACE:${CMAKE_BINARY_DIR}/generated>
)

include(FeatureSummary)
feature_summary(WHAT ALL FATAL_ON_MISSING_REQUIRED_PACKAGES)

include(cmake/InstallRules.cmake)
```

#### `include/myapp/calc.h`

```cpp
#pragma once

namespace myapp {

/// 计算 a + b
auto add(int a, int b) -> int;

/// 计算 a * b
auto multiply(int a, int b) -> int;

} // namespace myapp
```

#### `include/myapp/version.h.in`

```cpp
#pragma once

#define MYAPP_VERSION       "@PROJECT_VERSION@"
#define MYAPP_VERSION_MAJOR @PROJECT_VERSION_MAJOR@
#define MYAPP_VERSION_MINOR @PROJECT_VERSION_MINOR@
#define MYAPP_VERSION_PATCH @PROJECT_VERSION_PATCH@
```

#### `src/CMakeLists.txt`

```cmake
add_library(myapp)
add_library(myapp::myapp ALIAS myapp)

target_sources(myapp
    PRIVATE calc.cpp
)

target_include_directories(myapp
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

target_compile_features(myapp PUBLIC cxx_std_20)
```

#### `src/calc.cpp`

```cpp
#include "myapp/calc.h"

namespace myapp {

auto add(int a, int b) -> int {
    return a + b;
}

auto multiply(int a, int b) -> int {
    return a * b;
}

} // namespace myapp
```

#### `app/CMakeLists.txt`

```cmake
add_executable(myapp_cli main.cpp)
target_link_libraries(myapp_cli PRIVATE myapp::myapp)

install(TARGETS myapp_cli
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
```

#### `app/main.cpp`

```cpp
#include "myapp/calc.h"
#include "myapp/version.h"
#include <iostream>

int main() {
    std::cout << "myapp v" << MYAPP_VERSION << "\n";
    std::cout << "add(3, 4) = " << myapp::add(3, 4) << "\n";
    std::cout << "multiply(3, 4) = " << myapp::multiply(3, 4) << "\n";
    return 0;
}
```

#### `tests/CMakeLists.txt`

```cmake
enable_testing()

add_executable(test_calc test_calc.cpp)
target_link_libraries(test_calc PRIVATE myapp::myapp)

add_test(NAME test_calc COMMAND test_calc)
```

#### `tests/test_calc.cpp`

```cpp
#include "myapp/calc.h"
#include <cassert>
#include <iostream>

int main() {
    assert(myapp::add(2, 3) == 5);
    assert(myapp::add(-1, 1) == 0);
    assert(myapp::multiply(3, 4) == 12);
    assert(myapp::multiply(0, 5) == 0);

    std::cout << "All tests passed!\n";
    return 0;
}
```

#### `cmake/InstallRules.cmake`

```cmake
install(TARGETS myapp myapp_cli
    EXPORT  myappTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/myapp
)

set_target_properties(myapp PROPERTIES
    PUBLIC_HEADER "${CMAKE_SOURCE_DIR}/include/myapp/calc.h"
)

include(CMakePackageConfigHelpers)

write_basic_package_version_file(
    "${CMAKE_BINARY_DIR}/myappConfigVersion.cmake"
    VERSION       ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

configure_package_config_file(
    "${CMAKE_SOURCE_DIR}/cmake/myappConfig.cmake.in"
    "${CMAKE_BINARY_DIR}/myappConfig.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_DATADIR}/myapp/cmake"
)

install(EXPORT myappTargets
    FILE      myappTargets.cmake
    NAMESPACE myapp::
    DESTINATION "${CMAKE_INSTALL_DATADIR}/myapp/cmake"
)

install(FILES
    "${CMAKE_BINARY_DIR}/myappConfigVersion.cmake"
    "${CMAKE_BINARY_DIR}/myappConfig.cmake"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/myapp/cmake"
)
```

#### `CMakePresets.json`

```json
{
    "version": 6,
    "cmakeMinimumRequired": {
        "major": 3,
        "minor": 24,
        "patch": 0
    },
    "configurePresets": [
        {
            "name": "default",
            "displayName": "Default (Debug)",
            "binaryDir": "${sourceDir}/build/default",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Debug",
                "BUILD_TESTING": "ON"
            }
        },
        {
            "name": "release",
            "displayName": "Release with LTO",
            "binaryDir": "${sourceDir}/build/release",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Release",
                "ENABLE_IPO": "ON",
                "BUILD_TESTING": "OFF"
            }
        }
    ],
    "buildPresets": [
        {
            "name": "default",
            "configurePreset": "default"
        },
        {
            "name": "release",
            "configurePreset": "release"
        }
    ],
    "testPresets": [
        {
            "name": "default",
            "configurePreset": "default",
            "output": { "outputOnFailure": true }
        }
    ]
}
```

#### 构建和运行

```bash
# 配置
cmake --preset default

# 构建
cmake --build --preset default

# 运行测试
ctest --preset default

# 安装到本地目录
cmake --install build/default --prefix ./install

# Release 构建
cmake --preset release
cmake --build --preset release
```

> [!tip] 可运行性验证
> 上述所有代码可以直接复制到对应文件中，在安装有 CMake 3.24+ 和 C++20 编译器的系统上运行。无需任何外部依赖。

---

### 示例 2：FetchContent 依赖 + 安装 + CPack

本示例演示一个使用 `FetchContent` 下载 `fmt` 和 `spdlog`、配置安装规则、并生成 `.deb`/`.rpm` 包的项目。

#### `CMakeLists.txt`（顶层）

```cmake
cmake_minimum_required(VERSION 3.24...3.31)

project(logtool
    VERSION 1.0.0
    DESCRIPTION "Demo: FetchContent + Install + CPack"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

# --- 第三方依赖 via FetchContent ---
include(FetchContent)

set(FMT_DOC OFF CACHE BOOL "" FORCE)
set(FMT_TEST OFF CACHE BOOL "" FORCE)
set(FMT_INSTALL OFF CACHE BOOL "" FORCE)
FetchContent_Declare(fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG        11.1.4
    GIT_SHALLOW    TRUE
    SYSTEM
)
FetchContent_MakeAvailable(fmt)

set(SPDLOG_FMT_EXTERNAL ON CACHE BOOL "" FORCE)
set(SPDLOG_BUILD_EXAMPLE OFF CACHE BOOL "" FORCE)
set(SPDLOG_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(SPDLOG_INSTALL OFF CACHE BOOL "" FORCE)
FetchContent_Declare(spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG        v1.15.1
    GIT_SHALLOW    TRUE
    SYSTEM
)
FetchContent_MakeAvailable(spdlog)

# --- 项目 target ---
add_library(logtool)
add_library(logtool::logtool ALIAS logtool)

target_sources(logtool PRIVATE src/logger.cpp)

target_include_directories(logtool
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(logtool
    PUBLIC  fmt::fmt
    PRIVATE spdlog::spdlog
)

target_compile_features(logtool PUBLIC cxx_std_20)

# --- 可执行文件 ---
add_executable(logtool_cli app/main.cpp)
target_link_libraries(logtool_cli PRIVATE logtool::logtool)

# --- 安装规则 ---
install(TARGETS logtool logtool_cli
    EXPORT  logtoolTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

install(DIRECTORY include/
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)

write_basic_package_version_file(
    "${CMAKE_BINARY_DIR}/logtoolConfigVersion.cmake"
    VERSION       ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

configure_package_config_file(
    "${CMAKE_SOURCE_DIR}/cmake/logtoolConfig.cmake.in"
    "${CMAKE_BINARY_DIR}/logtoolConfig.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_DATADIR}/logtool/cmake"
)

install(EXPORT logtoolTargets
    FILE      logtoolTargets.cmake
    NAMESPACE logtool::
    DESTINATION "${CMAKE_INSTALL_DATADIR}/logtool/cmake"
)

install(FILES
    "${CMAKE_BINARY_DIR}/logtoolConfigVersion.cmake"
    "${CMAKE_BINARY_DIR}/logtoolConfig.cmake"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/logtool/cmake"
)

# --- CPack 打包 ---
set(CPACK_PACKAGE_NAME "logtool")
set(CPACK_PACKAGE_VERSION ${PROJECT_VERSION})
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "A logging utility tool")
set(CPACK_PACKAGE_VENDOR "Example Corp")
set(CPACK_PACKAGE_CONTACT "dev@example.com")
set(CPACK_DEBIAN_PACKAGE_SECTION "devel")
set(CPACK_RPM_PACKAGE_LICENSE "MIT")

include(CPack)

# --- 特性摘要 ---
include(FeatureSummary)
feature_summary(WHAT ALL FATAL_ON_MISSING_REQUIRED_PACKAGES)
```

#### `include/logtool/logger.h`

```cpp
#pragma once

#include <string>
#include <string_view>

namespace logtool {

void init_logger(std::string_view app_name);
void info(std::string_view message);
void warn(std::string_view message);
void error(std::string_view message);

} // namespace logtool
```

#### `src/logger.cpp`

```cpp
#include "logtool/logger.h"
#include "logger_impl.h"

#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/spdlog.h>

namespace logtool {

void init_logger(std::string_view app_name) {
    auto sink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    auto logger = std::make_shared<spdlog::logger>(std::string{app_name}, sink);
    spdlog::set_default_logger(logger);
    spdlog::set_level(spdlog::level::info);
}

void info(std::string_view message) {
    spdlog::info(message);
}

void warn(std::string_view message) {
    spdlog::warn(message);
}

void error(std::string_view message) {
    spdlog::error(message);
}

} // namespace logtool
```

#### `src/logger_impl.h`

```cpp
#pragma once

// Private implementation details not exposed in public API.
// Source files in src/ can include this via target_include_directories(PRIVATE).
```

#### `app/main.cpp`

```cpp
#include "logtool/logger.h"

int main() {
    logtool::init_logger("logtool");

    logtool::info("Application started");
    logtool::warn("This is a warning");
    logtool::error("This is an error");
    logtool::info("Application finished");

    return 0;
}
```

#### `cmake/logtoolConfig.cmake.in`

```cmake
@PACKAGE_INIT@

include(CMakeFindDependencyMacro)
find_dependency(fmt)

include("${CMAKE_CURRENT_LIST_DIR}/logtoolTargets.cmake")
check_required_components(logtool)
```

#### `CMakePresets.json`

```json
{
    "version": 6,
    "cmakeMinimumRequired": { "major": 3, "minor": 24, "patch": 0 },
    "configurePresets": [
        {
            "name": "default",
            "binaryDir": "${sourceDir}/build/default",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Debug"
            }
        },
        {
            "name": "release",
            "binaryDir": "${sourceDir}/build/release",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Release"
            }
        }
    ]
}
```

#### 构建、安装、打包

```bash
# 配置和构建
cmake --preset release
cmake --build --preset release

# 安装
cmake --install build/release --prefix ./install

# 生成 .deb 包（Linux）
cd build/release
cpack -G DEB

# 生成 .tar.gz
cpack -G TGZ

# 列出所有可用生成器
cpack --help
```

---

### 示例 3：CI 配置（GitHub Actions + CMakePresets.json）

#### `CMakePresets.json`

```json
{
    "version": 6,
    "cmakeMinimumRequired": { "major": 3, "minor": 24, "patch": 0 },
    "configurePresets": [
        {
            "name": "ci-debug",
            "displayName": "CI Debug",
            "description": "Debug build for CI with sanitizers",
            "binaryDir": "${sourceDir}/build/ci-debug",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Debug",
                "CMAKE_CXX_STANDARD": "20",
                "BUILD_TESTING": "ON",
                "ENABLE_SANITIZERS": "ON"
            }
        },
        {
            "name": "ci-release",
            "displayName": "CI Release",
            "description": "Release build for CI with LTO",
            "binaryDir": "${sourceDir}/build/ci-release",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Release",
                "CMAKE_CXX_STANDARD": "20",
                "BUILD_TESTING": "ON",
                "ENABLE_IPO": "ON"
            }
        },
        {
            "name": "ci-lint",
            "displayName": "CI Lint",
            "description": "Build with clang-tidy checks",
            "binaryDir": "${sourceDir}/build/ci-lint",
            "cacheVariables": {
                "CMAKE_BUILD_TYPE": "Debug",
                "CMAKE_CXX_CLANG_TIDY": "clang-tidy;-header-filter=${sourceDir}/include/;-checks=bugprone-*,performance-*,readability-*",
                "BUILD_TESTING": "OFF"
            }
        }
    ],
    "buildPresets": [
        {
            "name": "ci-debug",
            "configurePreset": "ci-debug",
            "jobs": 0
        },
        {
            "name": "ci-release",
            "configurePreset": "ci-release",
            "jobs": 0
        },
        {
            "name": "ci-lint",
            "configurePreset": "ci-lint",
            "jobs": 0
        }
    ],
    "testPresets": [
        {
            "name": "ci-debug",
            "configurePreset": "ci-debug",
            "output": { "outputOnFailure": true }
        },
        {
            "name": "ci-release",
            "configurePreset": "ci-release",
            "output": { "outputOnFailure": true }
        }
    ],
    "workflowPresets": [
        {
            "name": "ci-full",
            "displayName": "Full CI Workflow",
            "steps": [
                { "type": "configure", "name": "ci-debug" },
                { "type": "build", "name": "ci-debug" },
                { "type": "test", "name": "ci-debug" },
                { "type": "configure", "name": "ci-release" },
                { "type": "build", "name": "ci-release" },
                { "type": "test", "name": "ci-release" }
            ]
        }
    ]
}
```

#### `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

env:
  CMAKE_VERSION: "3.31.6"

jobs:
  # ─── Linux: GCC + Clang ────────────────────────────
  linux:
    strategy:
      fail-fast: false
      matrix:
        compiler: [gcc, clang]
        build-type: [Debug, Release]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - name: Setup CMake
        uses: jwlawson/actions-setup-cmake@v2
        with:
          cmake-version: ${{ env.CMAKE_VERSION }}

      - name: Setup Ninja
        uses: asears/setup-ninja@main

      - name: Select compiler
        id: compiler
        run: |
          if [ "${{ matrix.compiler }}" = "clang" ]; then
            echo "cc=clang" >> $GITHUB_OUTPUT
            echo "cxx=clang++" >> $GITHUB_OUTPUT
          else
            echo "cc=gcc" >> $GITHUB_OUTPUT
            echo "cxx=g++" >> $GITHUB_OUTPUT
          fi

      - name: Configure
        run: >
          cmake --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}
          -DCMAKE_C_COMPILER=${{ steps.compiler.outputs.cc }}
          -DCMAKE_CXX_COMPILER=${{ steps.compiler.outputs.cxx }}
          -G Ninja

      - name: Build
        run: cmake --build --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}

      - name: Test
        run: ctest --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}

  # ─── macOS ──────────────────────────────────────────
  macos:
    strategy:
      matrix:
        build-type: [Debug, Release]
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4

      - name: Setup CMake
        uses: jwlawson/actions-setup-cmake@v2
        with:
          cmake-version: ${{ env.CMAKE_VERSION }}

      - name: Setup Ninja
        uses: asears/setup-ninja@main

      - name: Configure
        run: >
          cmake --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}
          -G Ninja

      - name: Build
        run: cmake --build --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}

      - name: Test
        run: ctest --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}

  # ─── Windows ────────────────────────────────────────
  windows:
    strategy:
      matrix:
        build-type: [Debug, Release]
    runs-on: windows-2022
    steps:
      - uses: actions/checkout@v4

      - name: Setup CMake
        uses: jwlawson/actions-setup-cmake@v2
        with:
          cmake-version: ${{ env.CMAKE_VERSION }}

      - name: Setup Ninja
        uses: asears/setup-ninja@main

      - name: Setup MSVC
        uses: ilammy/msvc-dev-cmd@v1

      - name: Configure
        run: >
          cmake --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}
          -G Ninja

      - name: Build
        run: cmake --build --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}

      - name: Test
        run: ctest --preset ci-${{ matrix.build-type == 'Debug' && 'debug' || 'release' }}

  # ─── Static Analysis ────────────────────────────────
  lint:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - name: Setup CMake
        uses: jwlawson/actions-setup-cmake@v2
        with:
          cmake-version: ${{ env.CMAKE_VERSION }}

      - name: Setup Ninja
        uses: asears/setup-ninja@main

      - name: Install clang-tidy
        run: sudo apt-get install -y clang-tidy

      - name: Configure with clang-tidy
        run: >
          cmake --preset ci-lint
          -DCMAKE_C_COMPILER=clang
          -DCMAKE_CXX_COMPILER=clang++
          -G Ninja

      - name: Build (triggers clang-tidy)
        run: cmake --build --preset ci-lint

  # ─── Sanitizers ─────────────────────────────────────
  sanitizers:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - name: Setup CMake
        uses: jwlawson/actions-setup-cmake@v2
        with:
          cmake-version: ${{ env.CMAKE_VERSION }}

      - name: Setup Ninja
        uses: asears/setup-ninja@main

      - name: Configure with sanitizers
        run: >
          cmake --preset ci-debug
          -DCMAKE_C_COMPILER=clang
          -DCMAKE_CXX_COMPILER=clang++
          -G Ninja

      - name: Build
        run: cmake --build --preset ci-debug

      - name: Test
        run: ctest --preset ci-debug
```

#### GitLab CI `.gitlab-ci.yml`（等效）

```yaml
stages:
  - build
  - test
  - lint

variables:
  CMAKE_VERSION: "3.31.6"

.build-template: &build_definition
  before_script:
    - pip install cmake==${CMAKE_VERSION}
    - cmake --version
  script:
    - cmake --preset $PRESET -G Ninja
    - cmake --build --preset $PRESET
  artifacts:
    paths:
      - build/$PRESET/

.test-template: &test_definition
  script:
    - ctest --preset $PRESET

linux-gcc-debug:
  stage: build
  image: gcc:14
  variables:
    PRESET: ci-debug
    CC: gcc
    CXX: g++
  <<: *build_definition

linux-clang-debug:
  stage: build
  image: silkeh/clang:18
  variables:
    PRESET: ci-debug
    CC: clang
    CXX: clang++
  <<: *build_definition

test-debug:
  stage: test
  image: gcc:14
  needs: [linux-gcc-debug]
  variables:
    PRESET: ci-debug
  <<: *test_definition

lint:
  stage: lint
  image: silkeh/clang:18
  variables:
    PRESET: ci-lint
    CC: clang
    CXX: clang++
  script:
    - apt-get update && apt-get install -y clang-tidy
    - cmake --preset ci-lint -G Ninja
    - cmake --build --preset ci-lint
```

---

## 练习

### 练习 1：重构扁平项目为 Modern CMake 多目录布局

**初始项目**（单文件 `CMakeLists.txt`，所有源文件在一个目录）：

```text
flat-project/
├── CMakeLists.txt
├── main.cpp
├── core.cpp
├── core.h
├── util.cpp
├── util.h
├── test_core.cpp
└── test_util.cpp
```

**原始 `CMakeLists.txt`**：

```cmake
cmake_minimum_required(VERSION 3.16)
project(flat LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

include_directories(${CMAKE_SOURCE_DIR})

add_executable(myapp main.cpp core.cpp util.cpp)

add_executable(test_core test_core.cpp)
add_executable(test_util test_util.cpp)
```

**任务**：重构为以下 Modern CMake 结构，要求：

1. 将 `core.cpp` + `core.h` 变为 `mycore` 静态库 target
2. 将 `util.cpp` + `util.h` 变为 `myutil` 静态库 target，依赖 `mycore`
3. 将 `main.cpp` 变为 `myapp` 可执行文件，依赖 `myutil`
4. 测试按 target 拆分到 `tests/` 目录
5. 所有 include 路径用 `target_include_directories`，所有链接用 `target_link_libraries`
6. 使用 `option(BUILD_TESTING ON)` 控制测试编译

**目标目录结构**：

```text
flat-project-refactored/
├── CMakeLists.txt
├── include/
│   ├── mycore.h
│   └── myutil.h
├── src/
│   ├── CMakeLists.txt
│   ├── core.cpp
│   └── util.cpp
├── app/
│   ├── CMakeLists.txt
│   └── main.cpp
└── tests/
    ├── CMakeLists.txt
    ├── test_core.cpp
    └── test_util.cpp
```

**验证**：

```bash
cmake -B build -DBUILD_TESTING=ON
cmake --build build
ctest --test-dir build --output-on-failure
```

### 练习 2：为现有项目添加静态分析器集成

基于练习 1 重构后的项目，添加：

1. 在 `CMakePresets.json` 中创建 `lint` preset，启用 `clang-tidy`
2. 配置 `clang-tidy` 检查项：`bugprone-*`、`performance-*`、`modernize-*`（排除 `modernize-use-trailing-return-type`）
3. 创建 `ci-lint` preset，配置 `-warnings-as-errors=*`
4. 在 `CMakeLists.txt` 中启用 `CMAKE_EXPORT_COMPILE_COMMANDS`
5. 编写 `.github/workflows/lint.yml` 文件，在 CI 中运行 lint

**验证**：

```bash
# 本地验证（需要安装 clang-tidy）
cmake --preset lint
cmake --build --preset lint
# 检查是否有 lint 警告被当作错误
```

### 练习 3：创建完整的 CI 流水线

基于练习 1 和练习 2 的项目，创建完整的 CI 配置：

**要求**：

1. `CMakePresets.json` 中创建至少 4 个 configure preset：
   - `ci-debug`（Debug + 测试）
   - `ci-release`（Release + LTO）
   - `ci-lint`（clang-tidy）
   - `ci-asan`（AddressSanitizer）
2. 创建 `workflowPreset` `ci-full` 自动执行 configure → build → test
3. 编写 `.github/workflows/ci.yml`，包含以下 job：
   - `build-and-test`（matrix: ubuntu-latest × [Debug, Release] × [gcc, clang]）
   - `lint`（clang-tidy，ubuntu-latest）
   - `sanitizers`（AddressSanitizer + UndefinedBehaviorSanitizer）
4. GitLab CI 等效配置（`.gitlab-ci.yml`）

**验证**：

```bash
# 本地运行 workflow preset
cmake --workflow --preset ci-full
# 检查所有步骤通过
```

---

## 常见陷阱

### 1. 使用 `file(GLOB)` 收集源文件

```cmake
# ❌ 陷阱
file(GLOB_RECURSE SOURCES "src/*.cpp")
add_library(mylib ${SOURCES})
```

**问题**：
- 新增 `.cpp` 后不会自动触发重新配置——编译结果可能是旧的
- 删除 `.cpp` 后不会从构建中移除
- `git checkout` 到不同分支后，构建可能包含不应存在的文件

**修复**：

```cmake
# ✅ 显式列出
target_sources(mylib PRIVATE
    src/core.cpp
    src/util.cpp
    src/io.cpp
)
```

### 2. 使用目录级命令

```cmake
# ❌ 陷阱：全局污染
include_directories(include)
add_definitions(-DENABLE_FEATURE_X)
```

**问题**：
- `include_directories` 作用于当前目录及所有子目录的全部 target
- 一个 target 的内部依赖泄漏到无关 target
- 头文件冲突被掩盖，调试极其困难

**修复**：

```cmake
# ✅ target 绑定
target_include_directories(mylib PUBLIC include)
target_compile_definitions(mylib PRIVATE ENABLE_FEATURE_X)
```

### 3. 混淆配置时间和构建时间

```cmake
# ❌ 陷阱：在配置时间做构建操作
execute_process(COMMAND python generate_code.py
    OUTPUT_VARIABLE generated
)
file(WRITE "${CMAKE_BINARY_DIR}/code.cpp" "${generated}")
```

**问题**：
- 代码生成发生在配置阶段，脚本修改后不会自动重新运行
- `cmake --build` 不会触发这个操作
- 增量构建时，生成代码可能过期而不自知

**修复**：

```cmake
# ✅ 用 add_custom_command 绑定到构建阶段
add_custom_command(
    OUTPUT  ${CMAKE_BINARY_DIR}/code.cpp
    COMMAND python ${CMAKE_SOURCE_DIR}/scripts/generate_code.py
            -o ${CMAKE_BINARY_DIR}/code.cpp
    DEPENDS ${CMAKE_SOURCE_DIR}/scripts/generate_code.py
            ${CMAKE_SOURCE_DIR}/templates/code.tmpl
)
```

### 4. 忘记安装 PUBLIC_HEADER

```cmake
# ❌ 陷阱：只安装了 target，没安装头文件
install(TARGETS mylib
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
```

**问题**：使用者 `find_package(mylib)` 后找不到头文件，链接成功但编译失败。

**修复**：

```cmake
# ✅ 显式安装头文件（FILE_SET 方式，CMake 3.23+）
target_sources(mylib
    PUBLIC FILE_SET HEADERS
        BASE_DIRS ${CMAKE_SOURCE_DIR}/include
        FILES ${MYLIB_PUBLIC_HEADERS}
)
install(TARGETS mylib
    FILE_SET HEADERS DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
```

### 5. 在 `find_package` 和 `FetchContent` 之间不兼容

```cmake
# ❌ 陷阱：选项始终固定为 FetchContent
FetchContent_Declare(fmt ...)
FetchContent_MakeAvailable(fmt)
```

**问题**：使用者可能已经通过包管理器安装了 `fmt`，但你的项目强制重新下载一个。两个版本可能冲突。

**修复**：

```cmake
# ✅ 提供选择
option(USE_SYSTEM_FMT "Use system-installed fmt" OFF)

if(USE_SYSTEM_FMT)
    find_package(fmt 11 REQUIRED)
else()
    FetchContent_Declare(fmt ...)
    set(FMT_INSTALL OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(fmt)
endif()
```

### 6. 忽略 `target_link_libraries` 的传递作用域

```cmake
# ❌ 陷阱：全部用 PUBLIC
target_link_libraries(mylib
    PUBLIC pthread
    PUBLIC dl
    PUBLIC some_internal_lib
)
```

**问题**：`pthread` 和 `dl` 是 `mylib` 的内部实现细节，消费者不需要知道。把它们标记为 `PUBLIC` 会污染消费者的链接行，导致不必要的依赖传播和潜在的符号冲突。

**修复**：

```cmake
# ✅ 精确控制作用域
target_link_libraries(mylib
    PUBLIC  fmt::fmt               # 头文件暴露了 fmt
    PRIVATE pthread                # 只在 .cpp 里用了 pthread
    PRIVATE dl                     # 只在 .cpp 里用了 dlopen
    PRIVATE some_internal_lib      # 内部实现
)
```

### 7. `CMAKE_BUILD_TYPE` 硬编码

```cmake
# ❌ 陷阱
set(CMAKE_BUILD_TYPE Debug)
```

**问题**：覆盖了用户在命令行或 preset 中的设置。尤其是多配置生成器（Xcode、Visual Studio）中，`CMAKE_BUILD_TYPE` 是无意义的——构建类型在构建时选择。

**修复**：

```cmake
# ✅ 仅在单配置生成器且用户未设置时提供默认值
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Debug
        CACHE STRING "Build type" FORCE
    )
    set_property(CACHE CMAKE_BUILD_TYPE
        PROPERTY STRINGS Debug Release RelWithDebInfo MinSizeRel
    )
endif()
```

---

## 扩展阅读

- [[11-install-and-export-targets]] — 安装与导出的深入讨论
- [[13-ctest-and-testing]] — CTest 测试框架集成
- [[14-cmake-presets]] — CMakePresets.json 的完整语法
- [[10-fetchcontent-dependency-management]] — FetchContent 的所有用法与陷阱
- [[15-toolchain-files-and-cross-compiling]] — 工具链文件与交叉编译
- [[21-ide-integration-and-debugging]] — IDE 集成与调试技巧
- [CMake 官方文档: cmake-buildsystem(7)](https://cmake.org/cmake/help/latest/manual/cmake-buildsystem.7.html)
- [Modern CMake 在线书](https://cliutils.gitlab.io/modern-cmake/)
- [Effective Modern CMake (视频)](https://www.youtube.com/watch?v=y7ndUhdQuU8)
- [Professional CMake: A Practical Guide](https://crascit.com/professional-cmake/)
- [GitHub Actions: CMake 示例](https://github.com/actions/setup-cmake)
