---
title: CMake 4.0 与 Post-Modern CMake
updated: 2026-06-10
tags: [cmake, build-system, c++, modern-cmake, cmake-4]
---

# CMake 4.0 与 Post-Modern CMake

> 预计耗时: 45min
> 前置要求: 所有前序教程
> 深度等级: 精通

---

## 概念

### CMake 版本演进：从 3.0 到 4.0

CMake 3.0 发布于 2014 年，标志着"Modern CMake"时代的开始。核心理念是：

- **Target-based design**：不再操作全局目录属性，一切围绕 target 展开
- **Usage requirements (transitive properties)**：通过 `target_link_libraries` 自动传播编译要求
- **生成器表达式**：在配置阶段延迟求值，支持多配置生成器
- **导入目标 (IMPORTED targets)**：外部依赖的一等公民表示

CMake 3.x 历经 30+ 个小版本，逐步引入：

| 版本 | 关键特性 |
|------|---------|
| 3.1 | `target_sources()`, `CMAKE_CXX_STANDARD` |
| 3.5 | `cmake_parse_arguments` 增强 |
| 3.8 | C++17 支持, `CUDA` 语言 |
| 3.11 | `FetchContent`, `add_library(… IMPORTED INTERFACE)` |
| 3.12 | `SHELL:` 前缀用于生成器表达式 |
| 3.14 | `FILE_SET` 初步引入 |
| 3.16 | `CMAKE_UNITY_BUILD` |
| 3.19 | `CMakePresets.json` |
| 3.20 | `CXX_STANDARD` 支持 C++23, `cmake_path()` |
| 3.21 | `CXX_MODULES` 初步实验支持 |
| 3.23 | `FILE_SET` 正式化 (`HEADERS` 类型) |
| 3.25 | `CMAKE_CXX_SCAN_FOR_MODULES` |
| 3.28 | C++20 模块支持成熟化 |
| 3.30 | 预设版本 8, `cmake_build_cache` 实验 |

**CMake 4.0** 于 2025 年发布，不是革命而是清理：移除长期弃用的 API、收窄 `cmake_minimum_required` 行为、为 `target_sources` + `FILE_SET` 为主的编程模型铺路。

---

### CMake 4.0 核心变化

#### `cmake_minimum_required` 行为收紧

在 CMake 3.x 中，`cmake_minimum_required(VERSION 3.10)` 会同时：
1. 设置最低所需版本
2. 隐式将 policies 设置为该版本的行为

CMake 4.0 将这两件事解耦：

```cmake
# CMake 4.0+: 明确告知 CMake 你期望哪个版本的默认 policies
cmake_minimum_required(VERSION 4.0)

# 同时，你可以显式设置 policy 版本
cmake_policy(VERSION 3.30...4.0)
```

> [!tip] `cmake_policy(VERSION <min>...<max>)`
> 范围语法告诉 CMake：对 `<min>` 及以上引入的 policies 使用 NEW 行为，对 `<max>` 以上的使用 OLD 行为。这让你可以逐步迁移而不会一次性被所有 breaking changes 击中。

#### 移除的弃用特性

CMake 4.0 彻底移除了以下 3.x 中已标记弃用的特性：

- **裸 `add_test(NAME ... COMMAND ...)` 不带 `WORKING_DIRECTORY`** — 必须在 4.0 中使用显式的 `WORKING_DIRECTORY`
- **`get_property()` 对没有属性的目标的隐式错误** — 现在必须显式处理
- **一些内部宏和未文档化的行为**

#### `CMAKE_POLICY_VERSION_MINIMUM`

这是 CMake 4.0 引入的"逃生舱"变量。当你的项目依赖一个尚未适配 4.x 的外部 CMake 模块（比如某些上游 `Find*.cmake` 使用了废弃 API），可以设置：

```cmake
# 告诉 CMake：即使最低要求是 4.0，但兼容到 3.10 的 policy 行为
set(CMAKE_POLICY_VERSION_MINIMUM 3.10)
```

这会抑制 3.10+ 的 policy 警告，允许旧模块在 4.0 下继续工作。

> [!warning] 这仅用于第三方模块
> `CMAKE_POLICY_VERSION_MINIMUM` 是用来给未迁移的**上游依赖**喘息空间的，不要在自己的代码里依赖它来逃避迁移。每个项目应该最终移除这个设置。

---

### Post-Modern CMake 理念

"Post-Modern CMake" 概念来自 **Vito Gamberini 在 CppNow 2025 的演讲**。如果说 Modern CMake (3.x) 的核心是"一切围绕 target"，那么 Post-Modern CMake 的核心是：

#### 描述源代码树，而非描述构建标志

传统 CMake 的做法是：你告诉 CMake **如何**构建——手动列出每个编译选项、每个包含路径、每个宏定义。Post-Modern CMake 的做法是：你描述**源代码的结构**，CMake 推导出正确的构建方式。

```cmake
# Modern CMake (3.x 风格): 你描述构建方式
add_library(my_lib)
target_sources(my_lib PRIVATE src/foo.cpp src/bar.cpp)
target_include_directories(my_lib PUBLIC include/)
target_compile_features(my_lib PUBLIC cxx_std_20)

# Post-Modern CMake (4.x 风格): 你描述源代码结构
add_library(my_lib)
target_sources(my_lib
  PRIVATE
    FILE_SET PRIVATE_HEADER
      BASE_DIRS include/my_lib
      FILES include/my_lib/details/*.hpp
    FILE_SET PUBLIC_HEADER
      BASE_DIRS include
      FILES include/my_lib/*.hpp
  PRIVATE
    src/foo.cpp src/bar.cpp
)
```

第二个版本不仅声明了有哪些文件，还声明了它们在项目中的**角色**——哪些是公共头文件、哪些是私有头文件、哪些是模块文件。CMake 4.x 据此自动设置 include 路径、编译特性和模块扫描。

#### `target_sources()` 作为主要接口

在 Post-Modern CMake 中：

```cmake
# 不推荐: 在 add_executable/add_library 中直接列出源文件
add_executable(my_app main.cpp util.cpp)

# 推荐: 先创建 target，再用 target_sources 详细描述
add_executable(my_app)
target_sources(my_app PRIVATE main.cpp util.cpp)
```

这种分离的好处：
1. **可扩展性**：可以在子目录、`include()` 模块甚至外部文件中使用 `target_sources()` 向已有 target 追加源文件
2. **FILE_SET 支持**：`target_sources()` 的 `FILE_SET` 参数是描述源码树的关键入口
3. **与 IDE 的更好集成**：IDE 可以看到完整的 target 结构，包括后来追加的源文件

---

### FILE_SET：源码树的结构化描述

`FILE_SET` 是 CMake 3.23 正式引入、CMake 4.0 推崇的机制。它将 target 的源文件按**角色**分组：

| FILE_SET 类型 | 用途 | 效果 |
|---------------|------|------|
| `PUBLIC_HEADER` | target 的公共头文件 | 自动添加到 `PUBLIC` include 路径 |
| `PRIVATE_HEADER` | target 的私有头文件 | 自动添加到 `PRIVATE` include 路径 |
| `CXX_MODULES` | C++20 模块接口文件 | 启用模块扫描和编译 |
| `RESOURCES` | 资源文件（Qt `.qrc` 等） | 标记为资源，不参与编译但参与依赖跟踪 |

```cmake
add_library(geometry)

target_sources(geometry
  PUBLIC
    FILE_SET PUBLIC_HEADER
    TYPE HEADERS
    BASE_DIRS include
    FILES
      include/geometry/point.hpp
      include/geometry/vector.hpp
  PRIVATE
    FILE_SET PRIVATE_HEADER
    TYPE HEADERS
    BASE_DIRS include
    FILES
      include/geometry/detail/impl.hpp
  PRIVATE
    src/point.cpp
    src/vector.cpp
)
```

CMake 会自动：
- 将 `include/` 添加为 PUBLIC include 目录（给链接者）
- 将 `include/` 添加为 PRIVATE include 目录（给自身编译）
- 正确区分公共 API 头文件和内部实现头文件

> [!tip] `BASE_DIRS` 的作用
> CMake 用 `BASE_DIRS` 来确定 include 路径的根。上例中 `include/geometry/point.hpp` → include 根是 `include`。如果文件直接是 `include/foo.h` 而不在子目录中，可以用 `BASE_DIRS ${CMAKE_CURRENT_SOURCE_DIR}`。

---

### C++20 模块支持

CMake 3.28+ 对 C++20 模块提供了成熟支持，4.0 进一步巩固。

#### 启用模块扫描

```cmake
cmake_minimum_required(VERSION 4.0)
project(modules_example LANGUAGES CXX)

# 关键：在 project() 之后、创建任何 target 之前设置
set(CMAKE_CXX_SCAN_FOR_MODULES ON)
```

#### 声明模块文件

```cmake
add_library(math_module)

target_sources(math_module
  PUBLIC
    FILE_SET CXX_MODULES
    TYPE CXX_MODULES
    BASE_DIRS src
    FILES
      src/math.ixx          # 主模块接口
      src/math_util.ixx     # 模块分区
  PRIVATE
    src/math_impl.cpp       # 模块实现单元
)

target_compile_features(math_module PUBLIC cxx_std_20)
```

CMake 会自动：
1. 扫描 `.ixx` / `.cppm` 文件中的 `export module` 声明
2. 确定模块之间的依赖顺序
3. 生成正确的编译顺序（先编译模块接口，再编译消费者）
4. 设置编译器的模块相关标志（`-std=c++20 -fmodules-ts` 或 `/std:c++20 /experimental:module`）

#### 模块消费者

```cmake
add_executable(consumer)
target_sources(consumer PRIVATE main.cpp)
target_link_libraries(consumer PRIVATE math_module)
# CMake 自动处理模块导入——不需要额外配置
```

---

### CMakePresets.json 版本 10

CMake 4.x 引入了预设版本 10，新增了两个重要特性。

#### `$comment` 字段

预设文件现在支持注释——这在以前是个痛点多时的缺失：

```json
{
  "version": 10,
  "$comment": "项目的顶层预设配置 — 所有开发者共享",
  "configurePresets": [
    {
      "name": "default",
      "$comment": "标准 Debug 构建，使用 Ninja 生成器",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/${presetName}",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug"
      }
    }
  ]
}
```

> [!tip] 为什么 `$comment` 重要
> 之前要注释只能靠 JSON 不支持的原生注释 `//` 或 `/* */`，但那些在严格 JSON 解析器下会报错。`$comment` 是 JSON Schema 正式支持的字段，所有 CMake 工具都能正确忽略。

#### `include` 预设

版本 10 允许一个预设文件**继承**其他预设文件：

```json
{
  "version": 10,
  "include": [
    "CMakeCommonPresets.json",
    "CMakePlatformPresets.json"
  ],
  "configurePresets": [
    {
      "name": "my-project",
      "inherits": ["common-base", "platform-windows"]
    }
  ]
}
```

这解决了团队协作中的核心问题：共享预设（CI、通用配置）可以放在单独文件中被引用，开发者个人预设（本地路径、IDE 偏好）放在自己的文件中，不会产生 git 冲突。

`include` 的文件在 `CMakePresets.json` 所在目录中按数组顺序加载，后加载的覆盖先加载的同名字段（深度合并）。

---

### CMake Build Cache

CMake 4.x 引入了实验性的 **build cache** 机制，灵感来自 `ccache` / `sccache` 但运作在 CMake 层面。

```cmake
# CMakeLists.txt 中启用
set(CMAKE_BUILD_CACHE ON CACHE BOOL "Enable CMake build cache")
```

工作原理：
1. 对每个编译单元计算内容哈希（源文件 + 所有编译标志 + 依赖的头文件）
2. 如果哈希命中缓存中的条目，直接复用之前的编译产物（`.o` / `.obj`）
3. 缓存可以跨构建目录共享

> [!experiment] 实验性特性
> `cmake_build_cache` 在 CMake 4.0 中标记为实验性。生产项目应等待稳定版并在非关键构建中评估。

---

### 应该停止使用的旧模式

Post-Modern CMake 需要你**主动停止**使用以下旧 API：

| 旧 API | 替代 | 原因 |
|--------|------|------|
| `add_executable(name src1.cpp …)` | `add_executable(name)` + `target_sources()` | 分离声明和源码描述 |
| `include_directories()` | `target_include_directories()` | 全局副作用，破坏 target 隔离 |
| `link_directories()` | `target_link_directories()` 或 IMPORTED 目标 | 全局副作用 |
| `add_definitions()` | `target_compile_definitions()` | 全局 `-D` 标志 |
| `add_compile_options()` | `target_compile_options()` | 全局编译选项 |
| `link_libraries()` | `target_link_libraries()` | 过时的全局链接 |
| 裸 `set(CMAKE_CXX_FLAGS …)` | `target_compile_options()` + 生成器表达式 | 不区分 target 和配置 |

```cmake
# 旧风格 — 禁止在新项目中使用
cmake_minimum_required(VERSION 3.5)
include_directories(include)
add_definitions(-DUSE_LEGACY)
add_executable(my_app main.cpp foo.cpp)
target_link_libraries(my_app m pthread)

# Post-Modern 风格
cmake_minimum_required(VERSION 4.0)
add_executable(my_app)
target_sources(my_app PRIVATE main.cpp foo.cpp)
target_include_directories(my_app PRIVATE include)
target_compile_definitions(my_app PRIVATE USE_LEGACY)
target_link_libraries(my_app PRIVATE m pthread)
```

---

### Effective Modern CMake 原则

来自 **mbinna 的 gist**（github.com/mbinna/effective-modern-cmake），这些原则指导 Post-Modern 实践：

1. **把 CMake 当作代码**：用函数和宏消除重复，像写 C++ 一样认真对待 CMake
2. **只用 target-based 命令**：不用 `include_directories`、`link_libraries` 等全局命令
3. **不在 PARENT_SCOPE 中修改变量（函数内部除外）**：`set(var value PARENT_SCOPE)` 只在函数内部有意义；在宏或顶层使用会导致隐蔽的耦合
4. **通过 compile features 设置 C++ 标准**：

```cmake
# 正确 — 使用 compile features
target_compile_features(my_lib PUBLIC cxx_std_20)

# 错误 — 手动设置全局变量
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

> [!tip] 为什么推荐 `target_compile_features`
> `target_compile_features(my_lib PUBLIC cxx_std_20)` 不仅设置标准版本，还自动向消费者传播这个要求。如果你将 `my_lib` 链接到 `my_app`，`my_app` 也会被编译为 C++20——不需要在 `my_app` 的 CMakeLists.txt 中重复声明。

5. **避免过早抽象**：不要为了"可能的复用"把两行 CMake 包装成函数
6. **使用生成器表达式替代条件分支**：`$<CONFIG:Debug>` 比 `if(CMAKE_BUILD_TYPE STREQUAL "Debug")` 更健壮

---

### CMake 4.x 弃用时间线与迁移指南

| 阶段 | 版本 | 行为 |
|------|------|------|
| **警告期** | 3.28-3.30 | 使用废弃 API 时输出 `CMPxxxx` 警告 |
| **4.0** | 4.0 | 移除部分废弃 API；其余产生**错误**而非警告 |
| **4.x** | 4.1+ | 进一步收紧；`CMAKE_POLICY_VERSION_MINIMUM` 作为逃生舱 |
| **5.0** | 未来 | 彻底移除所有 pre-4.0 兼容性代码 |

**迁移步骤**：

1. 升级到 CMake 3.30，设置 `cmake_minimum_required(VERSION 3.30)`，修复所有 deprecation 警告
2. 将 `cmake_minimum_required` 改为 `4.0`，逐一处理 policy 冲突
3. 将源文件列表迁移到 `target_sources()` + `FILE_SET`
4. 移除 `CMAKE_POLICY_VERSION_MINIMUM`（如果需要过它）
5. 将预设文件升级到版本 10，启用 `$comment` 和 `include`

---

### 未来方向

Kitware 公开讨论中的几个方向：

- **Build Cache 成熟化**：稳定 `cmake_build_cache`，与 CI 系统深度集成
- **更好的依赖管理**：`FetchContent` 与包管理器的桥接（vcpkg / Conan 的更深集成）
- **C++ 模块全面支持**：移除 `CMAKE_CXX_SCAN_FOR_MODULES` 的需要——让模块成为默认支持
- **声明式构建描述**：向 `target_sources(FILE_SET …)` 的声明式风格继续演进，减少命令式构建描述
- **远程缓存和分布式构建**：与 `sccache`、Buildbarn 等系统的标准化接口

---

## 代码示例

### 示例 1: 使用 `target_sources()` 和 `FILE_SET` 的现代项目

**项目结构**：

```
modern_project/
├── CMakeLists.txt
├── CMakePresets.json
├── include/
│   └── geometry/
│       ├── point.hpp
│       └── details/
│           └── point_impl.hpp
├── src/
│   ├── point.cpp
│   └── main.cpp
└── tests/
    ├── CMakeLists.txt
    └── test_point.cpp
```

**顶层 `CMakeLists.txt`**：

```cmake
cmake_minimum_required(VERSION 4.0)
project(GeometryProject VERSION 1.0.0 LANGUAGES CXX)

# 全局编译特性要求
add_library(geometry)

target_sources(geometry
  PUBLIC
    FILE_SET PUBLIC_HEADER
    TYPE HEADERS
    BASE_DIRS include
    FILES
      include/geometry/point.hpp
  PRIVATE
    FILE_SET PRIVATE_HEADER
    TYPE HEADERS
    BASE_DIRS include
    FILES
      include/geometry/details/point_impl.hpp
  PRIVATE
    src/point.cpp
)

target_include_directories(geometry
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

target_compile_features(geometry PUBLIC cxx_std_20)

# 可执行目标
add_executable(geometry_demo)
target_sources(geometry_demo PRIVATE src/main.cpp)
target_link_libraries(geometry_demo PRIVATE geometry)

# 测试
enable_testing()
add_subdirectory(tests)
```

**`tests/CMakeLists.txt`**：

```cmake
add_executable(test_geometry)
target_sources(test_geometry PRIVATE test_point.cpp)
target_link_libraries(test_geometry PRIVATE geometry)

include(CTest)
add_test(NAME test_geometry COMMAND test_geometry)
```

**`CMakePresets.json`** (版本 10)：

```json
{
  "version": 10,
  "$comment": "项目预设 — 开发与 CI 共享",
  "configurePresets": [
    {
      "name": "dev",
      "$comment": "开发环境: Ninja + Debug",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/dev",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_EXPORT_COMPILE_COMMANDS": "ON"
      }
    },
    {
      "name": "release",
      "$comment": "发布构建: Ninja + Release + LTO",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/release",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_INTERPROCEDURAL_OPTIMIZATION": "ON"
      }
    }
  ],
  "buildPresets": [
    {
      "name": "dev",
      "configurePreset": "dev"
    },
    {
      "name": "release",
      "configurePreset": "release"
    }
  ],
  "testPresets": [
    {
      "name": "dev",
      "configurePreset": "dev",
      "output": {
        "outputOnFailure": true
      }
    }
  ]
}
```

**构建命令**：

```bash
# 配置
cmake --preset dev

# 构建
cmake --build --preset dev

# 运行测试
ctest --preset dev
```

---

### 示例 2: C++20 模块项目

**项目结构**：

```
module_project/
├── CMakeLists.txt
├── CMakePresets.json
├── src/
│   ├── math.ixx           # 主模块接口
│   ├── math_util.ixx      # 模块分区
│   ├── math_impl.cpp      # 模块实现单元
│   └── main.cpp           # 模块消费者
```

**`src/math.ixx`** — 主模块接口：

```cpp
export module math;

import :util;  // 导入模块分区

export namespace math {
    auto add(int a, int b) -> int;
    auto multiply(int a, int b) -> int;
}
```

**`src/math_util.ixx`** — 模块分区：

```cpp
export module math:util;

export namespace math::internal {
    auto validate_positive(int n) -> bool {
        return n >= 0;
    }
}
```

**`src/math_impl.cpp`** — 模块实现单元：

```cpp
module math;

namespace math {
    auto add(int a, int b) -> int {
        return a + b;
    }

    auto multiply(int a, int b) -> int {
        int result = 0;
        for (int i = 0; i < b; ++i) {
            result = add(result, a);
        }
        return result;
    }
}
```

**`src/main.cpp`** — 模块消费者：

```cpp
import math;

#include <iostream>

int main() {
    std::cout << "3 + 4 = " << math::add(3, 4) << '\n';
    std::cout << "3 * 4 = " << math::multiply(3, 4) << '\n';
    return 0;
}
```

**`CMakeLists.txt`**：

```cmake
cmake_minimum_required(VERSION 4.0)
project(MathModules VERSION 1.0.0 LANGUAGES CXX)

# 启用 C++20 模块扫描（在 project() 之后、创建 target 之前）
set(CMAKE_CXX_SCAN_FOR_MODULES ON)

# 库目标
add_library(math_module)

target_sources(math_module
  PUBLIC
    FILE_SET CXX_MODULES
    TYPE CXX_MODULES
    BASE_DIRS src
    FILES
      src/math.ixx
      src/math_util.ixx
  PRIVATE
    src/math_impl.cpp
)

target_compile_features(math_module PUBLIC cxx_std_20)

# 可执行目标（消费者）
add_executable(math_demo)

target_sources(math_demo PRIVATE
  src/main.cpp
)

target_link_libraries(math_demo PRIVATE math_module)
```

**`CMakePresets.json`**：

```json
{
  "version": 10,
  "$comment": "C++20 模块项目 — 需要支持模块的编译器 (GCC 14+, Clang 17+, MSVC 2022 17.8+)",
  "configurePresets": [
    {
      "name": "gcc",
      "$comment": "GCC 14+ 模块支持",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/gcc",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_C_COMPILER": "gcc",
        "CMAKE_CXX_COMPILER": "g++"
      }
    },
    {
      "name": "clang",
      "$comment": "Clang 17+ 模块支持",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/clang",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_C_COMPILER": "clang",
        "CMAKE_CXX_COMPILER": "clang++"
      }
    },
    {
      "name": "msvc",
      "$comment": "MSVC 2022 17.8+ 模块支持",
      "generator": "Visual Studio 17 2022",
      "binaryDir": "${sourceDir}/build/msvc"
    }
  ],
  "buildPresets": [
    { "name": "gcc", "configurePreset": "gcc" },
    { "name": "clang", "configurePreset": "clang" },
    { "name": "msvc", "configurePreset": "msvc" }
  ]
}
```

---

### 示例 3: 预设版本 10 的 `$comment` 和 `include`

**场景**：一个团队项目中，CI 预设、平台预设和开发者个人预设分离管理。

**`CMakeCommonPresets.json`** — 共享的通用配置：

```json
{
  "version": 10,
  "$comment": "共享预设 — 所有开发者和 CI 继承此文件中的预设",
  "configurePresets": [
    {
      "name": "common-base",
      "$comment": "所有构建的通用基础配置",
      "generator": "Ninja",
      "cacheVariables": {
        "CMAKE_EXPORT_COMPILE_COMMANDS": "ON",
        "CMAKE_CXX_STANDARD": "20",
        "CMAKE_CXX_STANDARD_REQUIRED": "ON",
        "CMAKE_CXX_EXTENSIONS": "OFF"
      }
    },
    {
      "name": "ci-base",
      "$comment": "CI 构建的额外严格设置",
      "inherits": ["common-base"],
      "cacheVariables": {
        "CMAKE_COMPILE_WARNING_AS_ERROR": "ON",
        "BUILD_TESTING": "ON"
      },
      "warnings": {
        "dev": true,
        "deprecated": true
      }
    }
  ],
  "buildPresets": [
    {
      "name": "common-build",
      "$comment": "通用构建预设模板",
      "jobs": 0
    }
  ],
  "testPresets": [
    {
      "name": "common-test",
      "$comment": "通用测试预设 — 失败时输出详细信息",
      "output": {
        "outputOnFailure": true,
        "verbosity": "default"
      }
    }
  ]
}
```

**`CMakePlatformPresets.json`** — 平台特定配置：

```json
{
  "version": 10,
  "$comment": "平台特定预设 — 根据操作系统和工具链调整",
  "configurePresets": [
    {
      "name": "platform-linux",
      "$comment": "Linux + GCC 工具链",
      "cacheVariables": {
        "CMAKE_C_COMPILER": "gcc",
        "CMAKE_CXX_COMPILER": "g++"
      }
    },
    {
      "name": "platform-windows",
      "$comment": "Windows + MSVC 工具链",
      "generator": "Visual Studio 17 2022",
      "architecture": {
        "value": "x64",
        "strategy": "set"
      }
    },
    {
      "name": "platform-macos",
      "$comment": "macOS + Apple Clang",
      "cacheVariables": {
        "CMAKE_C_COMPILER": "clang",
        "CMAKE_CXX_COMPILER": "clang++"
      }
    }
  ]
}
```

**`CMakePresets.json`** — 主入口，引用上述文件：

```json
{
  "version": 10,
  "$comment": "主预设文件 — 通过 include 组合通用配置和平台配置",
  "include": [
    "CMakeCommonPresets.json",
    "CMakePlatformPresets.json"
  ],
  "configurePresets": [
    {
      "name": "linux-debug",
      "$comment": "Linux 开发构建",
      "inherits": ["common-base", "platform-linux"],
      "binaryDir": "${sourceDir}/build/linux-debug",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Debug"
      }
    },
    {
      "name": "linux-release",
      "$comment": "Linux 发布构建 — 带 LTO",
      "inherits": ["common-base", "platform-linux"],
      "binaryDir": "${sourceDir}/build/linux-release",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_INTERPROCEDURAL_OPTIMIZATION": "ON"
      }
    },
    {
      "name": "ci-linux",
      "$comment": "CI Linux 构建 — 继承 ci-base 的严格设置",
      "inherits": ["ci-base", "platform-linux"],
      "binaryDir": "${sourceDir}/build/ci-linux",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release"
      }
    }
  ],
  "buildPresets": [
    {
      "name": "linux-debug",
      "$comment": "开发构建 — 使用所有 CPU 核心",
      "configurePreset": "linux-debug",
      "inherits": ["common-build"]
    },
    {
      "name": "ci-linux",
      "$comment": "CI 构建 — 单线程以避免资源竞争",
      "configurePreset": "ci-linux",
      "jobs": 1
    }
  ],
  "testPresets": [
    {
      "name": "ci-linux",
      "$comment": "CI 测试 — 输出所有失败详情",
      "configurePreset": "ci-linux",
      "inherits": ["common-test"]
    }
  ]
}
```

---

## 练习

### 练习 1: 将旧式 CMakeLists.txt 重构为 Post-Modern CMake

**给定的旧式项目**：

```cmake
cmake_minimum_required(VERSION 3.5)
project(OldProject)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra")

include_directories(include)
add_definitions(-DOLD_MACRO=1)

add_executable(my_app
    src/main.cpp
    src/helper.cpp
    include/helper.hpp
)

target_link_libraries(my_app pthread)
```

**任务**：

1. 将 `cmake_minimum_required` 升级到 `4.0`
2. 将所有全局命令替换为 target-based 等价命令
3. 将源文件分离：`add_executable` 只声明 target 名称，用 `target_sources()` 列出源文件
4. 用 `target_compile_features` 设置 C++ 标准
5. 为头文件使用 `FILE_SET`
6. 添加一个 `CMakePresets.json`（版本 10）用于开发构建

**参考答案要点**：

```cmake
cmake_minimum_required(VERSION 4.0)
project(NewProject VERSION 1.0.0 LANGUAGES CXX)

add_executable(my_app)

target_sources(my_app
  PRIVATE
    FILE_SET PRIVATE_HEADER
    TYPE HEADERS
    BASE_DIRS include
    FILES
      include/helper.hpp
  PRIVATE
    src/main.cpp
    src/helper.cpp
)

target_compile_features(my_app PRIVATE cxx_std_17)
target_compile_options(my_app PRIVATE -Wall -Wextra)
target_compile_definitions(my_app PRIVATE OLD_MACRO=1)
target_include_directories(my_app PRIVATE include)
target_link_libraries(my_app PRIVATE pthread)
```

---

### 练习 2: 创建 C++20 模块项目

**任务**：基于以下模块描述，编写完整的 `CMakeLists.txt` 和 `CMakePresets.json`：

- 项目名: `StringUtils`
- 一个模块 `string_utils`，提供一个导出函数 `trim(std::string_view) -> std::string_view`
- 头文件/模块文件结构自己设计
- 包含一个测试可执行文件 `test_string_utils`，链接到 `string_utils` 模块
- 使用 FILE_SET 类型 `CXX_MODULES`
- 预设版本 10，兼容 GCC 和 MSVC 两个配置

**参考设计**：

```
string_utils_project/
├── CMakeLists.txt
├── CMakePresets.json
├── src/
│   ├── string_utils.ixx
│   └── string_utils_impl.cpp
└── test/
    ├── CMakeLists.txt
    └── test_main.cpp
```

**`CMakeLists.txt`** 关键行：

```cmake
set(CMAKE_CXX_SCAN_FOR_MODULES ON)

add_library(string_utils)
target_sources(string_utils
  PUBLIC
    FILE_SET CXX_MODULES
    TYPE CXX_MODULES
    BASE_DIRS src
    FILES
      src/string_utils.ixx
  PRIVATE
    src/string_utils_impl.cpp
)
target_compile_features(string_utils PUBLIC cxx_std_20)
```

---

### 练习 3: 创建带注释和 include 的预设版本 10 配置

**任务**：

为一个有 3 个可执行目标、2 个库目标、1 个测试套件的项目设计预设层级：

1. **`CMakeCommonPresets.json`**：定义 `ci-strict` 预设——开启所有警告为错误、dev warnings、deprecation warnings
2. **`CMakeDevPresets.json`**：定义 `dev-debug` 和 `dev-release`——启用编译命令导出、地址消毒器（仅 debug）
3. **`CMakePresets.json`**：主入口，引用前两个文件，组合出 `ci-linux`、`dev-linux-debug`、`dev-linux-release` 三个预设
4. 每一个 preset 必须有有意义的 `$comment`
5. 确保 `inherits` 链正确

**参考答案结构**：

```json
{
  "version": 10,
  "$comment": "...",
  "include": ["CMakeCommonPresets.json", "CMakeDevPresets.json"],
  "configurePresets": [
    {
      "name": "ci-linux",
      "$comment": "...",
      "inherits": ["ci-strict", "platform-linux"]
    },
    {
      "name": "dev-linux-debug",
      "$comment": "...",
      "inherits": ["dev-debug", "platform-linux"]
    },
    {
      "name": "dev-linux-release",
      "$comment": "...",
      "inherits": ["dev-release", "platform-linux"]
    }
  ]
}
```

---

## 扩展阅读

- **CMake 官方文档 — CMake 4.0 Release Notes**: [https://cmake.org/cmake/help/latest/release/4.0.html](https://cmake.org/cmake/help/latest/release/4.0.html)
- **Vito Gamberini — Post-Modern CMake (CppNow 2025)**: 演讲录像和幻灯片，提出 target_sources + FILE_SET 作为源码描述的核心
- **mbinna/effective-modern-cmake**: [https://gist.github.com/mbinna](https://gist.github.com/mbinna) — Effective Modern CMake 原则的权威参考
- **CMake 官方文档 — FILE_SET**: [https://cmake.org/cmake/help/latest/command/target_sources.html#file-sets](https://cmake.org/cmake/help/latest/command/target_sources.html#file-sets)
- **CMake 官方文档 — C++ 模块支持**: [https://cmake.org/cmake/help/latest/manual/cmake-cxxmodules.7.html](https://cmake.org/cmake/help/latest/manual/cmake-cxxmodules.7.html)
- **CMake 官方文档 — CMakePresets.json**: [https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html)
- **Craig Scott — Professional CMake (第 20 版+)**: 涵盖 CMake 4.0 变化的权威书籍
- [[22-real-world-project-patterns]] — 前一教程：真实项目模式与最佳实践
- [[14-cmake-presets]] — 预设文件基础
- [[03-targets-and-properties]] — Target 与属性系统基础

---

## 常见陷阱

### 陷阱 1: 在 `add_executable` 中直接列出源文件

```cmake
# 旧习惯 — CMake 4.x 中产生 CMPxxxx 警告
add_executable(my_app main.cpp util.cpp helper.cpp)
```

> [!danger] 问题
> 将 target 声明和源文件列表耦合在一条命令中。在大型项目中，源文件可能分散在多个子目录和 `include()` 模块中时，这种方式不可扩展。CMake 4.x 明确推荐将两者分离。

**修复**：

```cmake
add_executable(my_app)
target_sources(my_app PRIVATE main.cpp util.cpp helper.cpp)
```

### 陷阱 2: 使用 CMake 4.x 特性但未更新最低版本

```cmake
# 使用了 CMake 4.0 的 FILE_SET 语法
# 但 cmake_minimum_required 还是 3.16
cmake_minimum_required(VERSION 3.16)
target_sources(my_lib PUBLIC FILE_SET PUBLIC_HEADER ...)  # 可能静默失败
```

> [!danger] 问题
> CMake 的向后兼容性保证仅在你声明的版本范围内成立。声明 `VERSION 3.16` 意味着你期望 3.16 的 policies 和特性集。新语法可能无法正确解析，或者在 4.0+ 的行为与预期不一致。

**修复**：

```cmake
cmake_minimum_required(VERSION 4.0)  # 必须匹配你使用的特性版本
```

### 陷阱 3: 忽略 deprecation 警告

```cmake
cmake_minimum_required(VERSION 4.0)
include_directories(some/path)          # 警告！
add_definitions(-DSOME_FLAG)             # 警告！
link_directories(/usr/local/lib)         # 警告！
```

> [!danger] 问题
> CMake 4.0 对废弃 API 输出的是**警告**，不是错误。很多开发者习惯性忽略警告——"构建通过了就行"。但 CMake 5.0 将把这些警告变成**错误**。现在无视它们 = 未来的构建全红。

**修复**：配置时开启严格模式，将 warning 作为错误：

```bash
cmake -B build -D CMAKE_COMPILE_WARNING_AS_ERROR=ON --warn-deprecated
```

或在 `CMakePresets.json` 中：

```json
{
  "configurePresets": [{
    "name": "strict",
    "warnings": { "deprecated": true, "dev": true },
    "errors": { "deprecated": true, "dev": true }
  }]
}
```

### 陷阱 4: `FILE_SET` 的 `BASE_DIRS` 配置错误

```cmake
target_sources(my_lib
  PUBLIC
    FILE_SET PUBLIC_HEADER
    TYPE HEADERS
    BASE_DIRS include/my_lib      # 错误！
    FILES
      include/my_lib/point.hpp
)
```

> [!danger] 问题
> `BASE_DIRS` 指向了**子目录**而非 include 根目录。这会导致 `#include <point.hpp>` 工作，但 `#include <my_lib/point.hpp>` 失败——因为 CMake 认为 `include/my_lib/` 就是根，头文件的相对路径变成了 `point.hpp` 而非 `my_lib/point.hpp`。

**修复**：

```cmake
BASE_DIRS include   # 指向 include 根，保留 my_lib/ 子目录结构
```

### 陷阱 5: 模块扫描未在 `project()` 之后立即设置

```cmake
cmake_minimum_required(VERSION 4.0)
set(CMAKE_CXX_SCAN_FOR_MODULES ON)   # 太早！project() 可能重置它
project(MyProject LANGUAGES CXX)
```

> [!danger] 问题
> `CMAKE_CXX_SCAN_FOR_MODULES` 必须在 `project()` 调用**之后**设置，因为 `project()` 可能重置它（取决于语言启用逻辑）。如果在 `project()` 之前设置，编译器检测完成后可能被清空。

**修复**：

```cmake
cmake_minimum_required(VERSION 4.0)
project(MyProject LANGUAGES CXX)
set(CMAKE_CXX_SCAN_FOR_MODULES ON)   # 必须在 project() 之后
```

### 陷阱 6: 在函数外部使用 `PARENT_SCOPE` 修改变量

```cmake
set(MY_GLOBAL ON CACHE BOOL "全局标志")

# 某处代码...
set(MY_GLOBAL OFF PARENT_SCOPE)  # 无效果或意外效果
```

> [!danger] 问题
> `PARENT_SCOPE` 在函数**内部**是合理的设计——它修改调用者的作用域。但在函数外部（顶层或宏中），"父作用域" 可能是目录作用域或全局作用域，行为难以预测。Effective Modern CMake 原则明确禁止这样做。

**修复**：在函数内部使用 `PARENT_SCOPE`，在顶层用 `set(... CACHE ...)` 或返回变量：

```cmake
function(my_func out_var)
    set(${out_var} "computed_value" PARENT_SCOPE)  # OK: 在函数内部
endfunction()
```
