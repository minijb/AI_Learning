---
title: "install() 与 export() 目标导出"
updated: 2026-06-10
---
前置：[[07-target-link-libraries-and-transitive-deps]]、[[09-find-package-and-find-modules]]

# `install()` 与 `export()` 目标导出

> CMake 三阶段模型：配置(configuration) → 生成(generation) → 构建(build)。但工程最终要**交付**——部署到系统、分发给其他项目引用。这是第四阶段：`cmake --install`。

CMake 的 `install()` 命令是"在配置时声明意图，在安装时执行动作"的声明式指令。它不像 Makefile 的 `make install` 那样手写 raw 命令——CMake 自动处理平台差异、RPATH 修剪、符号链接等细节。而 `export()` 和 install-export 则让下游项目可以 `find_package` 你的库，像使用 `fmt::fmt` 或 `Boost::filesystem` 一样使用你的构建产物。

---

## 概念

### 安装 vs 构建 — 两棵树、两套世界

CMake 管理两棵目录树：

| | 构建树 (Build Tree) | 安装树 (Install Tree) |
|---|---|---|
| 位置 | `CMAKE_BINARY_DIR` | `CMAKE_INSTALL_PREFIX` |
| 二进制文件 | `lib/Debug/mylib.so` | `lib/mylib.so` |
| 包含头文件 | 源目录（或通过 `$<BUILD_INTERFACE:...>`） | `include/mylib/` |
| 生成文件路径 | `$<BUILD_INTERFACE:...>` 生效 | `$<INSTALL_INTERFACE:...>` 生效 |
| 导入目标配置 | `export()` → Targets.cmake | `install(EXPORT)` → Targets.cmake |
| 包配置 | 手动生成或跳过 | `configure_package_config_file()` → Config.cmake |

关键认知：**构建树的路径不应该进入安装产物**。`target_include_directories` 中使用 `BUILD_INTERFACE` 和 `INSTALL_INTERFACE` 生成器表达式就是为了让同一目标在两棵树中有不同的 include 路径。

### 为什么需要 install-export

假设你写了一个库 `myapp-core`，被团队三个项目依赖。方案一：每个项目 `add_subdirectory` 拉取源码——耦合、慢、依赖 CMake 结构。方案二：构建后 `find_package(myapp-core)` ——解耦、快、只需要 .so/.a + 头文件 + cmake 配置文件。

`install(EXPORT)` 做的事情就是**在安装时自动生成**那个 cmake 配置文件：一个 `-targets.cmake` 文件，里面是 `add_library(myapp::core IMPORTED)` 加上所有属性（include 路径、链接依赖、编译选项等），下游 `find_package` 时由 Config.cmake `include()` 进来。

---

## `install()` 命令全面剖析

### 签名分类

CMake 的 `install()` 有六种签名——通过第一个参数区分：

```cmake
install(TARGETS <target>... [...])
install(FILES <file>... [...])
install(DIRECTORY <dir>... [...])
install(SCRIPT <file> [...])
install(CODE <code> [...])
install(EXPORT <export-name> [...])
```

这六种签名的**公共参数**都相同：

- `DESTINATION <dir>` — 安装目标目录（相对于 `CMAKE_INSTALL_PREFIX`）
- `PERMISSIONS <perm>...` — 文件权限（仅 `FILES` / `DIRECTORY` / `PROGRAMS` 有效）
- `CONFIGURATIONS <cfg>...` — 限定构建配置（`Debug`、`Release` 等）
- `COMPONENT <name>` — 归属到指定组件（用于分拆安装包）
- `EXCLUDE_FROM_ALL` — 不包含在默认安装中
- `OPTIONAL` — 文件不存在也不报错

### `install(TARGETS ...)` — 核心签名

```cmake
install(TARGETS <target>...
    [EXPORT <export-name>]
    [RUNTIME_DEPENDENCIES <arg>... |
     RUNTIME_DEPENDENCY_SET <set-name>]
    [[ARCHIVE|LIBRARY|RUNTIME|OBJECTS|FRAMEWORK|BUNDLE|
      PRIVATE_HEADER|PUBLIC_HEADER|RESOURCE|FILE_SET <set-name>]
     [DESTINATION <dir>]
     [PERMISSIONS <perm>...]
     [CONFIGURATIONS <cfg>...]
     [COMPONENT <comp>]
     [NAMELINK_COMPONENT <comp>]
     [OPTIONAL] [EXCLUDE_FROM_ALL]
     [NAMELINK_ONLY|NAMELINK_SKIP]
    ]...
)
```

每类构建产物可以有不同的安装目的地。产物类型对照表：

| 产物类型 | 平台 | 对应文件 | 默认目的地 |
|---|---|---|---|
| `ARCHIVE` | 所有 | 静态库 `.a` / `.lib` | `${CMAKE_INSTALL_LIBDIR}` |
| `LIBRARY` | 所有 | 动态库 `.so` / `.dylib` (非 DLL) | `${CMAKE_INSTALL_LIBDIR}` |
| `RUNTIME` | 所有 | 可执行文件，Windows 的 `.dll` | `${CMAKE_INSTALL_BINDIR}` |
| `OBJECTS` | 所有 | 对象库 `.o` / `.obj` | `${CMAKE_INSTALL_LIBDIR}` |
| `FRAMEWORK` | macOS | `.framework` 包 | `${CMAKE_INSTALL_FRAMEWORKDIR}` |
| `BUNDLE` | macOS | `.app` 包 | `${CMAKE_INSTALL_BINDIR}` |
| `PUBLIC_HEADER` | 所有 | `PUBLIC_HEADER` 属性指定的头文件 | `${CMAKE_INSTALL_INCLUDEDIR}` |
| `PRIVATE_HEADER` | 所有 | `PRIVATE_HEADER` 属性指定的头文件 | `${CMAKE_INSTALL_INCLUDEDIR}` |
| `RESOURCE` | 所有 | `RESOURCE` 属性指定的文件 | `${CMAKE_INSTALL_DATADIR}` |
| `FILE_SET` | 所有 | CMake 3.23+ 的 `target_sources(FILE_SET ...)` | 由文件集类型决定 |

**典型用法：**

```cmake
# 同时安装静态库(.a) + 动态库(.so) + 可执行(.exe) + 头文件
install(TARGETS mylib myapp
    EXPORT mylib-targets
    ARCHIVE  DESTINATION lib
    LIBRARY  DESTINATION lib
    RUNTIME  DESTINATION bin
    PUBLIC_HEADER DESTINATION include/mylib
)
```

### `EXPORT` — 告诉 `install(TARGETS)` "记录我"

`EXPORT <export-name>` 不是安装动作，而是**注册**：把当前 target 的信息记录到导出集 `<export-name>`。之后 `install(EXPORT <export-name> ...)` 将该集写入 cmake 配置文件。同一个导出集可以聚集多个 `install(TARGETS ... EXPORT <export-name>)` 调用。

### `install(EXPORT ...)` — 写出 targets 文件

```cmake
install(EXPORT <export-name>
    DESTINATION <dir>
    [NAMESPACE <ns>]
    [FILE <filename>]
    [EXPORT_LINK_INTERFACE_LIBRARIES]
    [COMPONENT <comp>]
    [EXCLUDE_FROM_ALL]
)
```

- `NAMESPACE` — 给所有导入目标加前缀，如 `mylib::` → 下游用 `mylib::core`
- `FILE` — 目标文件名，默认 `<export-name>.cmake`，通常约定为 `<export-name>Targets.cmake`

### `install(FILES ...)` 和 `install(DIRECTORY ...)`

```cmake
# 安装单个文件
install(FILES config.json README.md
    DESTINATION share/myapp
)

# 安装整个目录（递归）
install(DIRECTORY headers/
    DESTINATION include/myapp
    FILES_MATCHING PATTERN "*.h" PATTERN "*.hpp"
    PATTERN "internal" EXCLUDE
)
```

`DIRECTORY` 签名支持 `PATTERN` 和 `REGEX` 过滤，用途远超文件复制——它是头文件安装的主力。

### `install(SCRIPT ...)` 和 `install(CODE ...)`

`SCRIPT` 在安装时运行一个 CMake 脚本文件。`CODE` 在安装时执行一段 inline CMake 代码。两者运行在**安装阶段**，访问的是安装树变量（`CMAKE_INSTALL_PREFIX` 等）。

```cmake
install(CODE [[
    message(STATUS "Installing to ${CMAKE_INSTALL_PREFIX}")
    execute_process(COMMAND ${CMAKE_COMMAND} -E echo "Post-install hook")
]])
```

---

## 导出：构建树 vs 安装树

CMake 提供两种导出方式，解决"开发时"和"部署后"两个场景：

### 构建树导出：`export()`

```cmake
export(TARGETS <target>... 
    [NAMESPACE <ns>]
    [FILE <path>]
    [APPEND]
)
export(EXPORT <export-name>
    [NAMESPACE <ns>]
    [FILE <path>]
)
```

`export(TARGETS ...)` 在 **build tree** 中写 targets 文件。场景：其他项目通过 `add_subdirectory` 或手动 `include()` 导入你还没安装的构建产物。

构建树导出的 targets 文件**引用构建目录中的二进制**（通常是 `$<CONFIG>` 子目录），路径是构建系统的绝对路径。

### 安装树导出：`install(EXPORT ...)`

`install(EXPORT ...)` 在**安装时**将导出集写入 `${CMAKE_INSTALL_PREFIX}/<DESTINATION>/<file>`。生成的 targets 文件引用安装目录中的二进制，路径**必须是 relocatable 的**——这让安装包可以移动到任意位置。

安装树导出是生产分发方式。

### 构建树 vs 安装树的 RPATH 问题

`RPATH` 是嵌入在可执行文件和共享库中的运行时库搜索路径。CMake 对此有精细控制：

- **构建树**：可执行文件的 RPATH 包含构建目录中的库路径，因此可以不设置 `LD_LIBRARY_PATH` 直接运行
- **安装时**：`cmake --install` 默认**修剪 RPATH**：移除构建目录路径，只保留安装目录路径
- **macOS**：CMake 在安装时自动调用 `install_name_tool` 修改动态库的 `install_name`，将构建树路径改为安装树路径

相关变量/属性：

| 变量/属性 | 作用 |
|---|---|
| `CMAKE_INSTALL_RPATH` | 安装后的默认 RPATH |
| `CMAKE_BUILD_RPATH` | 构建时使用的 RPATH |
| `CMAKE_SKIP_INSTALL_RPATH` | 设为 `TRUE` 则跳过 RPATH 修剪 |
| `CMAKE_INSTALL_RPATH_USE_LINK_PATH` | 将 link 路径追加到安装 RPATH |
| `MACOSX_RPATH` | target 属性，是否使用 `@rpath` |
| `INSTALL_NAME_DIR` | macOS `install_name` 的目录部分 |

---

## CMake 包配置系统

`find_package()` 有两种模式：Module 模式（找 `Find<Name>.cmake`）和 Config 模式（找 `<Name>Config.cmake`）。现代 CMake 推崇 Config 模式——由库作者提供配置，而非让使用者写 Find 模块。

### 完整的包配置需要两个文件

| 文件 | 作用 | 生成工具 |
|---|---|---|
| `<Name>Config.cmake` | 包入口：include targets 文件、检查依赖 | `configure_package_config_file()` |
| `<Name>ConfigVersion.cmake` | 版本兼容性检查 | `write_basic_package_version_file()` |
| `<Name>Targets.cmake` | 导入目标定义（`IMPORTED` 库/可执行文件） | `install(EXPORT ...)` 自动生成 |
| `<Name>Targets-<config>.cmake` | 特定配置的导入目标位置（多配置生成器） | `install(EXPORT ...)` 自动生成 |

`find_package(<Name> REQUIRED)` 的查找顺序：
1. `${<Name>_DIR}` / `CMAKE_PREFIX_PATH` / `<Name>_ROOT` 等提示
2. 系统默认路径（`/usr/lib/cmake/<Name>`、`/usr/local/lib/cmake/<Name>` 等）
3. 找到 `<Name>Config.cmake` → include → include `<Name>Targets.cmake` → include `<Name>Targets-<config>.cmake`

### `write_basic_package_version_file()`

来自 `CMakePackageConfigHelpers` 模块（CMake 3.13+ 内置）：

```cmake
include(CMakePackageConfigHelpers)

write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/MyLibConfigVersion.cmake"
    VERSION 1.2.3
    COMPATIBILITY SameMajorVersion
)
```

版本兼容模式（`COMPATIBILITY` 参数）：

| 模式 | 说明 | 2.0 的用户能否用 1.2.3？ |
|---|---|---|
| `AnyNewerVersion` | 安装版本 ≥ 请求版本即兼容 | ✅（1.2.3 ≥ 2.0 = false → ❌） |
| `SameMajorVersion` | 主版本号相同，安装版本 ≥ 请求版本 | ❌（主版本不同） |
| `SameMinorVersion` | 主+次版本相同，安装版本 ≥ 请求版本 | ❌ |
| `ExactVersion` | 完全匹配 | ❌ |

> [!tip] 选择版本兼容策略
> SemVer 语义下，MAJOR 变化 = 不兼容。选 `SameMajorVersion` 最安全。内部工具链或 tightly coupled 的项目可用 `ExactVersion`。

### `configure_package_config_file()`

核心功能是**生成 relocatable 的 Config 文件**——通过计算配置文件的安装位置和 package 安装前缀之间的相对路径。

```cmake
include(CMakePackageConfigHelpers)

configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/MyLibConfig.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/MyLibConfig.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/MyLib"
    PATH_VARS INCLUDE_INSTALL_DIR
)
```

它生成一个 `PACKAGE_PREFIX_DIR` 变量，使用者可以用它构建相对于 package 安装前缀的路径，从而包可以整体移动（打包为 `.tar.gz` 或安装到任意 prefix）。

**模板文件 `.cmake.in` 示例：**

```cmake
@PACKAGE_INIT@

include("${CMAKE_CURRENT_LIST_DIR}/MyLibTargets.cmake")

# 检查依赖
include(CMakeFindDependencyMacro)
find_dependency(fmt REQUIRED)

# 计算路径（由 configure_package_config_file 的 PATH_VARS 处理）
set_and_check(MyLib_INCLUDE_DIR "${PACKAGE_PREFIX_DIR}/@INCLUDE_INSTALL_DIR@")
```

`@PACKAGE_INIT@` 是占位符，`configure_package_config_file()` 将其替换为 `PACKAGE_PREFIX_DIR` 的计算逻辑（基于 `CMAKE_CURRENT_LIST_DIR` 和 `INSTALL_DESTINATION` 反推）。

---

## `GNUInstallDirs` 模块 — 平台正确的安装路径

```cmake
include(GNUInstallDirs)
```

这个模块定义了一组遵循 GNU 编码标准（和平台惯例）的安装目录变量：

| 变量 | Linux 默认值 | Windows 默认值 | macOS 默认值 |
|---|---|---|---|
| `CMAKE_INSTALL_BINDIR` | `bin` | `bin` | `bin` |
| `CMAKE_INSTALL_LIBDIR` | `lib` 或 `lib/<multiarch>` | `lib` | `lib` |
| `CMAKE_INSTALL_INCLUDEDIR` | `include` | `include` | `include` |
| `CMAKE_INSTALL_DATADIR` | `share` | `share` | `share` |
| `CMAKE_INSTALL_DOCDIR` | `share/doc` | `doc` | `share/doc` |
| `CMAKE_INSTALL_MANDIR` | `share/man` | `man` | `share/man` |
| `CMAKE_INSTALL_SYSCONFDIR` | `etc` | `etc` | `etc` |

> [!warning] 不要硬编码安装路径
> 使用 `${CMAKE_INSTALL_LIBDIR}` 而非 `lib`。在 64 位多架构 Linux（如 Debian multiarch `lib/x86_64-linux-gnu`）上 `LIBDIR` 自动适配。

### `CMAKE_INSTALL_PREFIX` 和 `DESTDIR`

- **`CMAKE_INSTALL_PREFIX`** — 编译时嵌入到二进制中的安装前缀（RPATH、`install_name` 等）。Linux 默认 `/usr/local`，Windows 默认 `C:/Program Files/<ProjectName>`。
- **`DESTDIR`** — 在做 `cmake --install . --prefix /tmp/staging` 或 `DESTDIR=/tmp/staging cmake --install .` 时，实际安装路径 = `$DESTDIR/$CMAKE_INSTALL_PREFIX`。包管理器（RPM、Deb）用 `DESTDIR` 隔离安装到临时目录再打包。`DESTDIR` **不影响**编译时嵌入的路径——这是 staging 机制。

---

## `install_name_tool` 与 macOS RPATH

macOS 上的动态库使用 `install_name`（而非 SONAME）标识自己。可执行文件用 `@rpath`（Runpath Search Path）定位依赖。

CMake 在安装时自动调用 `install_name_tool` 完成以下操作：

1. **修改动态库 id**：从 `$<BUILD_DIR>/lib/libfoo.dylib` → `@rpath/libfoo.dylib`
2. **修改可执行文件的依赖引用**：将构建树路径替换为 `@rpath/libfoo.dylib`
3. **添加 RPATH 条目**：确保 `@rpath` 能解析

变量控制：

```cmake
set(CMAKE_INSTALL_RPATH "@loader_path/../lib")  # macOS 特殊 RPATH
set(CMAKE_MACOSX_RPATH ON)                      # 默认已开启
```

`@loader_path` 是 macOS 特有的 RPATH 占位符，相对于**加载者**的位置。效果：可执行文件在 `bin/`，库在 `lib/`，RPATH `@loader_path/../lib` 让可执行文件总能找到旁边的库——这被称为"bundle-style layout"。

---

## 代码示例

### 示例 1：安装库 + 头文件 + 创建导出集

**项目结构：**

```
example1/
├── CMakeLists.txt
├── include/
│   └── mathlib/
│       └── mathlib.h
└── src/
    └── mathlib.cpp
```

```cmake
# example1/CMakeLists.txt
cmake_minimum_required(VERSION 3.24)
project(MathLib VERSION 1.0.0 LANGUAGES CXX)

include(GNUInstallDirs)

# 构建目标
add_library(mathlib SHARED
    src/mathlib.cpp
)

target_include_directories(mathlib
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

set_target_properties(mathlib PROPERTIES
    PUBLIC_HEADER "include/mathlib/mathlib.h"
    VERSION ${PROJECT_VERSION}
    SOVERSION 1
)

# 安装目标 — 同时注册到导出集
install(TARGETS mathlib
    EXPORT MathLibTargets
    ARCHIVE  DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY  DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME  DESTINATION ${CMAKE_INSTALL_BINDIR}
    PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/mathlib
)

# 将导出集写入 cmake 配置文件
install(EXPORT MathLibTargets
    FILE MathLibTargets.cmake
    NAMESPACE MathLib::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib
)
```

```cpp
// include/mathlib/mathlib.h
#pragma once

namespace mathlib {
    int add(int a, int b);
}
```

```cpp
// src/mathlib.cpp
#include "mathlib/mathlib.h"

namespace mathlib {
    int add(int a, int b) {
        return a + b;
    }
}
```

**构建和安装：**

```bash
cmake -B build -DCMAKE_INSTALL_PREFIX=/tmp/mathlib-install
cmake --build build
cmake --install build
# 查看安装树
tree /tmp/mathlib-install
```

预期输出：

```
/tmp/mathlib-install/
├── include/
│   └── mathlib/
│       └── mathlib.h
├── lib/
│   ├── libmathlib.so -> libmathlib.so.1
│   ├── libmathlib.so.1 -> libmathlib.so.1.0.0
│   ├── libmathlib.so.1.0.0
│   └── cmake/
│       └── MathLib/
│           ├── MathLibTargets.cmake
│           └── MathLibTargets-release.cmake
```

检查生成的 `MathLibTargets.cmake`：

```cmake
# 关键内容（自动生成）
add_library(MathLib::mathlib SHARED IMPORTED)
set_target_properties(MathLib::mathlib PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${_IMPORT_PREFIX}/include"
)
```

### 示例 2：生成完整包配置文件

**项目结构（扩展示例 1）：**

```
example2/
├── CMakeLists.txt
├── MathLibConfig.cmake.in
├── include/
│   └── mathlib/
│       └── mathlib.h
└── src/
    └── mathlib.cpp
```

```cmake
# example2/CMakeLists.txt
cmake_minimum_required(VERSION 3.24)
project(MathLib VERSION 1.2.3 LANGUAGES CXX)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

# ---- 库目标 ----
add_library(mathlib SHARED src/mathlib.cpp)

target_include_directories(mathlib
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

set_target_properties(mathlib PROPERTIES
    PUBLIC_HEADER "include/mathlib/mathlib.h"
    VERSION ${PROJECT_VERSION}
    SOVERSION 1
)

# ---- 安装目标 ----
install(TARGETS mathlib
    EXPORT MathLibTargets
    ARCHIVE  DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY  DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME  DESTINATION ${CMAKE_INSTALL_BINDIR}
    PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/mathlib
)

# ---- 安装导出 targets 文件 ----
install(EXPORT MathLibTargets
    FILE MathLibTargets.cmake
    NAMESPACE MathLib::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib
)

# ---- 生成版本文件 ----
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfigVersion.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)

install(FILES "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfigVersion.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib
)

# ---- 生成 Config 文件 ----
configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/MathLibConfig.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfig.cmake"
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib
)

install(FILES "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfig.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib
)
```

**Config 模板文件 `MathLibConfig.cmake.in`：**

```cmake
# MathLibConfig.cmake.in

@PACKAGE_INIT@

include("${CMAKE_CURRENT_LIST_DIR}/MathLibTargets.cmake")

check_required_components(MathLib)
```

> [!note] `@PACKAGE_INIT@` 展开内容
> `configure_package_config_file()` 将 `@PACKAGE_INIT@` 替换为一组宏定义：`set_and_check()`、`check_required_components()`，以及最重要的 `PACKAGE_PREFIX_DIR` 变量——它是从 `CMAKE_CURRENT_LIST_DIR`（cmake 文件所在位置）反向计算出的安装前缀。这样即使整个安装树被移动到其他目录，包也能正常工作。

**构建和安装：**

```bash
cmake -B build -DCMAKE_INSTALL_PREFIX=/tmp/mathlib-v2
cmake --build build
cmake --install build
```

安装树内容：

```
/tmp/mathlib-v2/
├── include/mathlib/mathlib.h
├── lib/
│   ├── libmathlib.so -> libmathlib.so.1
│   ├── libmathlib.so.1 -> libmathlib.so.1.0.0
│   ├── libmathlib.so.1.0.0
│   └── cmake/MathLib/
│       ├── MathLibConfig.cmake              ← 入口
│       ├── MathLibConfigVersion.cmake       ← 版本检查
│       ├── MathLibTargets.cmake             ← IMPORTED 目标
│       └── MathLibTargets-release.cmake     ← release 配置的位置
```

### 示例 3：完整工作流 — 构建、安装、消费者项目

这个示例展示两端：生产者（Library）和消费者（Application）。

**项目结构：**

```
example3/
├── mathlib/                          # ← 生产者
│   ├── CMakeLists.txt
│   ├── MathLibConfig.cmake.in
│   ├── include/mathlib/mathlib.h
│   └── src/mathlib.cpp
└── app/                              # ← 消费者
    ├── CMakeLists.txt
    └── main.cpp
```

**生产者 `mathlib/CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(MathLib VERSION 2.0.0 LANGUAGES CXX)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

add_library(mathlib SHARED src/mathlib.cpp)

target_include_directories(mathlib
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

set_target_properties(mathlib PROPERTIES
    PUBLIC_HEADER "include/mathlib/mathlib.h"
    VERSION ${PROJECT_VERSION}
    SOVERSION 2
)

install(TARGETS mathlib
    EXPORT MathLibTargets
    ARCHIVE  DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY  DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME  DESTINATION ${CMAKE_INSTALL_BINDIR}
    PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/mathlib
)

install(EXPORT MathLibTargets
    FILE MathLibTargets.cmake
    NAMESPACE MathLib::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib
)

write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfigVersion.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfigVersion.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib)

configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/MathLibConfig.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfig.cmake"
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib
)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/MathLibConfig.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/MathLib)
```

**生产者 `mathlib/MathLibConfig.cmake.in`：**

```cmake
@PACKAGE_INIT@

include("${CMAKE_CURRENT_LIST_DIR}/MathLibTargets.cmake")

check_required_components(MathLib)
```

**消费者 `app/CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(MathApp VERSION 1.0.0 LANGUAGES CXX)

# 告诉 CMake 去哪里找 MathLib
list(APPEND CMAKE_PREFIX_PATH "/tmp/mathlib-install")

find_package(MathLib 2.0 REQUIRED)

add_executable(mathapp main.cpp)
target_link_libraries(mathapp PRIVATE MathLib::mathlib)
```

```cpp
// app/main.cpp
#include <iostream>
#include <mathlib/mathlib.h>

int main() {
    std::cout << "3 + 4 = " << mathlib::add(3, 4) << std::endl;
    return 0;
}
```

**完整工作流：**

```bash
# 1. 构建并安装库
cd example3/mathlib
cmake -B build -DCMAKE_INSTALL_PREFIX=/tmp/mathlib-install
cmake --build build
cmake --install build

# 2. 验证安装产物
ls /tmp/mathlib-install/lib/cmake/MathLib/
# MathLibConfig.cmake  MathLibConfigVersion.cmake
# MathLibTargets.cmake MathLibTargets-release.cmake

# 3. 构建消费者
cd example3/app
cmake -B build
cmake --build build

# 4. 运行
./build/mathapp
# 输出: 3 + 4 = 7
```

如果 MathLib 版本不匹配（如请求 3.0 但安装的是 2.0），`find_package` 会报错：

```bash
cmake -B build ..
# CMake Error: Could not find a configuration file for package "MathLib"
# that is compatible with requested version "3.0".
```

---

## 练习

### 练习 1：编写可安装的库项目

创建一个 `StringUtils` 库项目：
- 静态库，提供 `to_upper(std::string)` 和 `to_lower(std::string)` 函数
- 头文件位于 `include/stringutils/` 目录
- 安装到 `/tmp/stringutils-install`
- 导出集命名为 `StringUtilsTargets`，命名空间 `StringUtils::`
- 安装后发现 `/tmp/stringutils-install/lib/cmake/StringUtils/` 目录为空——请补全

**参考步骤：**

1. `add_library(stringutils STATIC ...)`
2. 使用 `BUILD_INTERFACE` / `INSTALL_INTERFACE` 设置 include 目录
3. `set_target_properties` 设置 `PUBLIC_HEADER`
4. `install(TARGETS ... EXPORT ...)` — 注意 `ARCHIVE` 对应静态库
5. `install(EXPORT ...)` 写出 targets 文件

### 练习 2：生成版本文件

为练习 1 的 `StringUtils` 库添加版本检查：
- 版本 `2.5.1`，兼容策略 `SameMajorVersion`
- 生成 `StringUtilsConfigVersion.cmake` 到正确的安装位置
- 测试：消费者请求 `find_package(StringUtils 2.3)` → 成功；请求 `3.0` → 失败

**参考步骤：**

1. `include(CMakePackageConfigHelpers)`
2. `write_basic_package_version_file(...)`
3. `install(FILES ...)` 放到 `cmake/StringUtils/`
4. 创建简单的 `StringUtilsConfig.cmake.in` 模板

### 练习 3：组件化安装

将练习 1 的库拆分为两个组件：
- `Runtime` 组件 — `.so` / `.dll`（库二进制）
- `Development` 组件 — 头文件 + cmake 配置 + 静态库 `.a`

安装时分别指定 `COMPONENT` 参数。测试：

```bash
# 只安装运行时
cmake --install build --component Runtime
# 只安装开发文件
cmake --install build --component Development
```

**参考步骤：**

1. 将 `install(TARGETS ...)` 拆为两份：`LIBRARY` / `RUNTIME` 用 `COMPONENT Runtime`；`ARCHIVE` / `PUBLIC_HEADER` 用 `COMPONENT Development`
2. `install(EXPORT ...)` 也归属到 `Development`
3. 版本文件和 Config 文件也归属到 `Development`

---

## 延伸阅读

- CMake 官方文档：`install()` — [Installing Files](https://cmake.org/cmake/help/latest/command/install.html)
- CMake 官方文档：`export()` — [Exporting Targets](https://cmake.org/cmake/help/latest/command/export.html)
- CMake 官方文档：`CMakePackageConfigHelpers` — [Package Config Helpers](https://cmake.org/cmake/help/latest/module/CMakePackageConfigHelpers.html)
- CMake 官方文档：`GNUInstallDirs` — [GNUInstallDirs](https://cmake.org/cmake/help/latest/module/GNUInstallDirs.html)
- Craig Scott, *Professional CMake: A Practical Guide* — 第 26–30 章详述安装和包系统
- Daniel Pfeifer, "Effective CMake" — C++Now 2017 演讲，RPATH 与包设计的最佳实践
- F-ES Sitecore, "Understanding RPATH" — [博客](https://dev.my-gate.net/2021/08/04/understanding-rpath-with-cmake/)
- Kitware GitLab: `cmake-developer(7)` — [Find Modules vs Config Files](https://cmake.org/cmake/help/latest/manual/cmake-developer.7.html)

---

## 常见陷阱

### 1. Config 文件中使用绝对路径（包不可重定位）

```cmake
# ❌ 错误 — 安装后移动目录即失效
set(MYLIB_INCLUDE_DIR "/usr/local/include/mylib")

# ✅ 正确 — 使用 PACKAGE_PREFIX_DIR 计算相对路径
set_and_check(MYLIB_INCLUDE_DIR "${PACKAGE_PREFIX_DIR}/include/mylib")
```

> [!warning] 根源
> `configure_package_config_file()` 的核心价值就是自动注入 `PACKAGE_PREFIX_DIR` 计算逻辑，确保路径是相对的。绕过它直接写绝对路径是最常见的安装陷阱。

### 2. 忘记安装头文件

```cmake
# ❌ 错误 — 库安装了，但 include/ 是空的
install(TARGETS mylib
    EXPORT MyLibTargets
    LIBRARY DESTINATION lib
)

# ✅ 正确 — 显式安装 PUBLIC_HEADER
set_target_properties(mylib PROPERTIES
    PUBLIC_HEADER "include/mylib/mylib.h"
)
install(TARGETS mylib
    EXPORT MyLibTargets
    LIBRARY        DESTINATION lib
    PUBLIC_HEADER  DESTINATION include/mylib
)
```

`target_include_directories` 的 `INSTALL_INTERFACE` 指定的是**消费者编译时**的 include 路径，但**不负责把文件复制过去**。头文件的物理安装需要 `PUBLIC_HEADER` + `install(TARGETS ... PUBLIC_HEADER ...)` 或单独的 `install(FILES ...)` / `install(DIRECTORY ...)`。

### 3. 不使用 `GNUInstallDirs` 导致跨平台路径错误

```cmake
# ❌ 错误 — 64 位多架构 Linux 上装到 /usr/lib 而非 /usr/lib/x86_64-linux-gnu
install(TARGETS mylib LIBRARY DESTINATION lib)

# ✅ 正确
include(GNUInstallDirs)
install(TARGETS mylib LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
```

### 4. 导出集 NAMESPACE 不一致

```cmake
# ❌ 错误 — install(TARGETS) 没写 NAMESPACE，
#          但 install(EXPORT) 指定了 namespace
install(TARGETS mylib EXPORT MyLibTargets ...)
install(EXPORT MyLibTargets NAMESPACE MyLib:: ...)
# 这没问题——NAMESPACE 不需要在 TARGETS 阶段指定
# 真正的问题是下游代码使用不一致

# ❌ 错误 — 导出集用了 MyLib::，但消费者写错了
target_link_libraries(app PRIVATE mylib)  # 应该是 MyLib::mylib
```

### 5. CMake 版本文件兼容模式选错

```cmake
# 对于 SemVer 库
write_basic_package_version_file(... COMPATIBILITY SameMajorVersion)

# ❌ 用了 AnyNewerVersion 导致破坏性变更被接受
# 1.0 的消费者接受 2.0（主版本已变）
```

### 6. 安装后没有修剪 RPATH

安装到系统路径（`/usr/lib`）时，RPATH 中残留构建目录路径可能导致加载错误的库。默认情况下 CMake 会修剪 RPATH，但如果设置了 `CMAKE_SKIP_INSTALL_RPATH`、`CMAKE_SKIP_RPATH` 或 `BUILD_WITH_INSTALL_RPATH` 导致行为偏离预期，需要检查：

```bash
# Linux — 检查 RPATH
readelf -d libmylib.so | grep RPATH
objdump -x libmylib.so | grep RPATH

# macOS — 检查 install_name
otool -L libmylib.dylib
otool -l libmylib.dylib | grep -A2 LC_RPATH
```

### 7. `export()` 和 `install(EXPORT)` 混淆

- `export(TARGETS ...)` → 写构建树中的 targets 文件，**不参与安装**。场景：开发时 `add_subdirectory` 工作流
- `install(EXPORT ...)` → 安装时生成 targets 文件到安装树。场景：生产分发

两者**不是**同一事物的两种写法。在同一个项目中同时使用两者也是常见的——构建树导出供 CI 测试，安装树导出供发布。
