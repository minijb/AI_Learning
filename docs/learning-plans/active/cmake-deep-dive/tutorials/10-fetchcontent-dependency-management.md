---
title: FetchContent 依赖管理
updated: 2026-06-10
tags: [cmake, dependency-management, fetchcontent]
---

# FetchContent 依赖管理

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 50min
> 前置知识: [[09-find-package-and-find-modules]]

---

## 1. 概念讲解

### 为什么需要这个？

C++ 项目长期面临依赖管理的痛点。传统方案各有缺陷：

- **系统包管理器**（apt、brew、vcpkg、Conan）：要求用户预先安装依赖，增加环境配置成本，版本一致性难以保证。
- **Git Submodule**：需要手动初始化和更新，嵌套 submodule 管理繁琐，CI 中容易遗漏 `--recursive`。
- **ExternalProject_Add**：在构建阶段下载和编译，依赖的 target 在 configure 阶段不可见，无法直接用 `target_link_libraries` 链接——必须手动指定 include 路径和库文件位置。
- **vendor 目录**：直接把依赖源码拷贝到仓库中，仓库体积膨胀，版本更新困难。

`FetchContent` 是 CMake 3.11 引入的模块，**在 configure 阶段下载依赖的源码并将其作为当前项目的一部分参与构建**。它兼具 submodule 的简单和包管理器的自动化，是 "Modern CMake" 推荐的一等公民方案。

> [!info] 历史沿革
> CMake 3.11 引入 `FetchContent` 基础 API；3.14 加入 `FetchContent_MakeAvailable()` 简化流程；3.24 引入 `FETCHCONTENT_TRY_FIND_PACKAGE_MODE` 和 `FIND_PACKAGE_ARGS`，让 FetchContent 与系统包可以共存。

### 核心思想

FetchContent 的工作流程分为三步：

1. **声明 (Declare)**：用 `FetchContent_Declare()` 描述"这个依赖从哪里获取"——Git 仓库、URL 下载、甚至本地路径。
2. **可用化 (MakeAvailable)**：用 `FetchContent_MakeAvailable()` 执行"下载 + 添加子目录"。CMake 会检查是否已下载，没有则下载；然后将依赖的 `CMakeLists.txt` 通过 `add_subdirectory()` 加入当前构建。
3. **链接 (Link)**：依赖的 target 已经存在于当前项目中，直接用 `target_link_libraries()` 链接即可。

关键区别：**FetchContent 在配置阶段完成一切**，依赖的 target 与你自己的 target 在同一个构建图中，传递依赖、编译选项、安装规则都能自然生效。

```
┌─────────────────────────────────────────────────────┐
│  CMake 配置阶段                                       │
│                                                      │
│  FetchContent_Declare(A)  ← 声明依赖 A               │
│  FetchContent_Declare(B)  ← 声明依赖 B               │
│  FetchContent_MakeAvailable(A) ← 下载 + add_subdir   │
│  FetchContent_MakeAvailable(B) ← 下载 + add_subdir   │
│                                                      │
│  add_executable(my_app ...)   ← 你自己的 target       │
│  target_link_libraries(my_app PRIVATE A B) ← 直接链接 │
└─────────────────────────────────────────────────────┘
```

#### FetchContent vs ExternalProject_Add

| 特性 | FetchContent | ExternalProject_Add |
|------|-------------|---------------------|
| 下载时机 | configure 阶段 | build 阶段 |
| Target 可见性 | 配置完成后立即可用 | 构建时才存在，需手动处理依赖 |
| `target_link_libraries` | 直接使用 | 不能直接用，需 `add_dependencies` + 手动指定路径 |
| 适合场景 | 库/框架作为项目一部分编译 | 外部工具、可选依赖、超大项目 |
| 构建隔离 | 共享构建图，选项可能冲突 | 完全隔离的构建 |

> [!tip] 选择建议
> 大多数情况下优先用 FetchContent。仅当依赖构建时间极长、有冲突的编译选项、或者是可执行工具（如代码生成器）而非库时，才考虑 ExternalProject_Add。

#### FetchContent vs Git Submodule

| 特性 | FetchContent | Git Submodule |
|------|-------------|---------------|
| 版本锁定 | CMakeLists.txt 中的 GIT_TAG | `.gitmodules` + commit 引用 |
| 初始化 | 自动（configure 时） | 手动 `git submodule update --init` |
| CI 友好 | 无需额外步骤 | 需要 `--recursive` clone |
| 离线支持 | `FETCHCONTENT_UPDATES_DISCONNECTED` | 天然支持（已 clone） |
| 依赖发现 | 阅读 CMakeLists.txt 即可 | 需要检查 `.gitmodules` 和目录结构 |

> [!tip] 选择建议
> 新项目推荐 FetchContent。Submodule 适合需要频繁修改依赖源码、或依赖本身也使用 submodule 的复杂场景。两者可以共存。

---

### 核心 API 详解

#### FetchContent_Declare() — 声明依赖来源

```cmake
include(FetchContent)

FetchContent_Declare(
  <name>
  <source-options>...
)
```

`<name>` 是依赖的逻辑名称，也用于生成内部变量前缀。常用 `<source-options>`：

| 选项 | 说明 | 示例 |
|------|------|------|
| `GIT_REPOSITORY <url>` | Git 仓库地址 | `https://github.com/google/googletest.git` |
| `GIT_TAG <tag>` | Git 标签/分支/commit hash | `v1.15.2` 或 `e23cdb7` |
| `GIT_SHALLOW TRUE` | 浅克隆（节省带宽） | `TRUE` |
| `URL <url>` | 下载压缩包 | `https://github.com/.../v3.11.3.tar.xz` |
| `URL_HASH <algo=hash>` | 校验下载文件完整性 | `SHA256=abc123...` |
| `SOURCE_DIR <path>` | 指定源码存放路径 | `${CMAKE_BINARY_DIR}/_deps/mylib-src` |
| `SOURCE_SUBDIR <subdir>` | CMakeLists.txt 所在子目录 | `cpp` (当根目录没有 CMakeLists.txt 时) |
| `FIND_PACKAGE_ARGS` | 传递给 `find_package` 的参数 | 见下文 |

#### GIT_TAG 最佳实践

```cmake
# ❌ 坏 — 分支名称会移动，不同时间 clone 得到不同代码
FetchContent_Declare(
  mylib
  GIT_REPOSITORY https://github.com/example/mylib.git
  GIT_TAG        main
)

# ✅ 好 — 使用 tag（不可变引用）
FetchContent_Declare(
  mylib
  GIT_REPOSITORY https://github.com/example/mylib.git
  GIT_TAG        v2.1.0
)

# ✅ 最好 — 使用 commit hash（绝对不可变）
FetchContent_Declare(
  mylib
  GIT_REPOSITORY https://github.com/example/mylib.git
  GIT_TAG        a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0
)
```

> [!warning] 为什么不能用分支名
> `GIT_TAG main` 意味着每次 CMake 重新配置时，如果 `FETCHCONTENT_UPDATES_DISCONNECTED` 未设置，CMake 会 `git fetch` 该分支的最新 commit。今天的构建和一个月后的构建可能链接到完全不同的代码——这是**可重复构建的毒药**。

#### URL_HASH — 下载校验

从 URL 下载压缩包时，**强烈建议**同时提供 hash 校验：

```cmake
FetchContent_Declare(
  json
  URL      https://github.com/nlohmann/json/releases/download/v3.11.3/include.zip
  URL_HASH SHA256=a22461d13119ac5c78f205d3df1db13403e58ce1bb1794edc9313677313f4a9d
)
```

支持的算法：`MD5`、`SHA1`、`SHA224`、`SHA256`、`SHA384`、`SHA512`、`SHA3_224`、`SHA3_256`、`SHA3_384`、`SHA3_512`。

> [!tip] 如何获取 SHA256
> ```bash
> # Linux/macOS
> curl -sL <url> | sha256sum
>
> # Windows PowerShell
> (Invoke-WebRequest -Uri <url>).Content | Get-FileHash -Algorithm SHA256
> ```

#### FetchContent_MakeAvailable() — 下载并加入构建

```cmake
FetchContent_MakeAvailable(<name1> [<name2> ...])
```

这一步做两件事：
1. 调用内部的 `FetchContent_Populate()` 下载源码到 `CMAKE_BINARY_DIR/_deps/<name>-src/`
2. 调用 `add_subdirectory()` 将依赖的 CMakeLists.txt 加入当前构建

> [!warning] 声明顺序规则
> **必须先声明所有依赖，再依次 MakeAvailable。** 理由见下文"分层项目"一节。

#### FETCHCONTENT_SOURCE_DIR_<name> — 覆盖为本地路径

在开发阶段，你可能已经将依赖 clone 到本地并做了修改。通过设置缓存变量可以跳过下载，直接使用本地副本：

```bash
cmake -B build -DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=/home/me/projects/googletest
```

或在 CMakeLists.txt 中：

```cmake
set(FETCHCONTENT_SOURCE_DIR_GOOGLETEST "/home/me/projects/googletest"
    CACHE PATH "Local googletest source override")
```

当此变量指向已存在的目录时，`FetchContent_MakeAvailable()` 跳过下载，直接用该目录执行 `add_subdirectory()`。

#### FETCHCONTENT_UPDATES_DISCONNECTED — 离线构建

```cmake
# 在 CMakeLists.txt 顶层设置
set(FETCHCONTENT_UPDATES_DISCONNECTED ON CACHE BOOL "Disable FetchContent updates")
```

或在命令行：

```bash
cmake -B build -DFETCHCONTENT_UPDATES_DISCONNECTED=ON
```

效果：**跳过所有 `git fetch` 和 URL 下载**。如果 `_deps/` 中已有之前下载的源码，直接使用。这对 CI 构建和离线环境至关重要——你可以在第一次 configure 后提交 `_deps/` 到缓存，之后全部用 `DISCONNECTED=ON` 跳过网络请求。

#### SOURCE_SUBDIR — 指定 CMakeLists.txt 位置

部分项目的根目录没有 `CMakeLists.txt`，构建入口在子目录中：

```cmake
FetchContent_Declare(
  catch2
  GIT_REPOSITORY https://github.com/catchorg/Catch2.git
  GIT_TAG        v3.7.1
  SOURCE_SUBDIR  src/catch2   # CMakeLists.txt 在 src/catch2/ 下
)
```

> [!note] 何时需要 SOURCE_SUBDIR
> - 项目根目录是 README 和配置文件，源码在 `src/` 下
> - 项目包含多个子项目，你需要的是其中一个
> - Header-only 库有时没有 CMakeLists.txt——此时无法直接使用 FetchContent_MakeAvailable()，需要手动处理（见下方练习 2）

#### FIND_PACKAGE_ARGS — 与系统包共存

```cmake
FetchContent_Declare(
  fmt
  GIT_REPOSITORY https://github.com/fmtlib/fmt.git
  GIT_TAG        11.0.2
  FIND_PACKAGE_ARGS 11.0 CONFIG   # 等效于 find_package(fmt 11.0 CONFIG)
)
```

当设置 `FIND_PACKAGE_ARGS` 时，CMake 的行为取决于 `FETCHCONTENT_TRY_FIND_PACKAGE_MODE`：

| 模式 | 行为 |
|------|------|
| `OPT_IN` (CMake < 3.28 默认) | 仅在用户显式设置 `-DFETCHCONTENT_TRY_FIND_PACKAGE_MODE=OPT_IN` 时尝试 `find_package` |
| `ALWAYS` (CMake ≥ 3.28 默认) | 先尝试 `find_package`，找不到再 FetchContent |
| `NEVER` | 永远不尝试 `find_package`，直接用 FetchContent |

```cmake
# 在顶层 CMakeLists.txt 设置全局策略
set(FETCHCONTENT_TRY_FIND_PACKAGE_MODE ALWAYS CACHE STRING
    "Prefer system packages over FetchContent")
```

> [!tip] 实际应用
> 在 Docker 镜像或开发者机器上预装 `libfmt-dev`，设置 `ALWAYS` 模式，CMake 会优先使用系统包（避免重复编译）。在干净环境中自动 fallback 到 FetchContent。一套 CMakeLists.txt 适配两种场景。

#### FetchContent_Populate() — 只下载不加入构建（高级）

```cmake
FetchContent_Declare(
  mylib
  GIT_REPOSITORY https://github.com/example/mylib.git
  GIT_TAG        v2.1.0
)

FetchContent_GetProperties(mylib)
if(NOT mylib_POPULATED)
  FetchContent_Populate(mylib)
endif()

# 源码在 ${mylib_SOURCE_DIR}，二进制在 ${mylib_BINARY_DIR}
# 你需要手动 add_subdirectory 或手动构建
```

`FetchContent_Populate()` 只下载，不调用 `add_subdirectory()`。适用于：
- 你不想要依赖的 CMake target，只需要它的源文件列表
- 依赖的 CMakeLists.txt 有冲突的全局设置，你需要以不同方式编译
- 你要对下载后的源码做预处理再 `add_subdirectory`

### 分层项目：先声明后可用

FetchContent 有一个关键规则：**首次声明获胜**。

```cmake
# 顶层 CMakeLists.txt
FetchContent_Declare(fmt GIT_TAG 11.0.2 ...)  # ← 首次声明，获胜
FetchContent_Declare(json GIT_TAG v3.11.3 ...)

FetchContent_MakeAvailable(fmt)   # 下载 fmt
FetchContent_MakeAvailable(json)  # 下载 json（json 可能内部也依赖 fmt）
```

如果 `json` 内部也声明了 `fmt`（比如依赖 10.0.0），**首次声明（你的 11.0.2）会覆盖它**。这保证了父项目对依赖版本的完全控制。

> [!warning] 声明在 MakeAvailable 之后会失效
> 如果你先调用了 `FetchContent_MakeAvailable(json)`，而 `json` 内部声明了 `fmt`，那么 `json` 的 `fmt` 声明会先生效。你后续的 `FetchContent_Declare(fmt ...)` 会被忽略——这就是为什么**必须先声明所有依赖，再依次 MakeAvailable**。

## 2. 代码示例

### 示例 1：Fetch Google Test 并编写测试

本示例演示最常用的 FetchContent 场景：下载 googletest 作为测试框架。

**项目结构:**
```
example1/
├── CMakeLists.txt
├── src/
│   ├── CMakeLists.txt
│   └── math_utils.cpp
└── tests/
    ├── CMakeLists.txt
    └── test_math.cpp
```

**顶层 CMakeLists.txt:**

```cmake
cmake_minimum_required(VERSION 3.24)
project(FetchGTestExample VERSION 1.0.0 LANGUAGES CXX)

# ---- FetchContent 配置 ----
include(FetchContent)

# 声明依赖：必须在任何 MakeAvailable 之前
FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        v1.15.2
  GIT_SHALLOW    TRUE          # 只 clone 最新 commit，节省带宽和时间
)

# 离线构建支持：设置后跳过网络请求
set(FETCHCONTENT_UPDATES_DISCONNECTED OFF CACHE BOOL
    "Disable network during FetchContent")

# 可用化所有依赖
FetchContent_MakeAvailable(googletest)

# ---- 项目 target ----
add_subdirectory(src)

# ---- 测试 ----
enable_testing()
add_subdirectory(tests)
```

**src/CMakeLists.txt:**

```cmake
add_library(math_utils STATIC
  math_utils.cpp
)

target_include_directories(math_utils PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}
)

target_compile_features(math_utils PUBLIC cxx_std_17)
```

**src/math_utils.cpp:**

```cpp
#include <vector>
#include <numeric>

namespace math_utils {

    int factorial(int n) {
        if (n < 0) return -1;  // 错误处理
        if (n <= 1) return 1;
        int result = 1;
        for (int i = 2; i <= n; ++i) result *= i;
        return result;
    }

    double average(const std::vector<int>& values) {
        if (values.empty()) return 0.0;
        return std::accumulate(values.begin(), values.end(), 0.0) / values.size();
    }
}
```

**tests/CMakeLists.txt:**

```cmake
add_executable(test_math
  test_math.cpp
)

# 链接 gtest_main：自动提供 main() 函数
target_link_libraries(test_math PRIVATE
  math_utils
  gtest_main          # googletest 的 target（含 main）
)

target_compile_features(test_math PRIVATE cxx_std_17)

# 自动发现并注册所有测试
include(GoogleTest)
gtest_discover_tests(test_math)
```

**tests/test_math.cpp:**

```cpp
#include <gtest/gtest.h>
#include "math_utils.hpp"

TEST(FactorialTest, HandlesZero) {
    EXPECT_EQ(math_utils::factorial(0), 1);
}

TEST(FactorialTest, HandlesOne) {
    EXPECT_EQ(math_utils::factorial(1), 1);
}

TEST(FactorialTest, HandlesPositive) {
    EXPECT_EQ(math_utils::factorial(5), 120);
    EXPECT_EQ(math_utils::factorial(10), 3'628'800);
}

TEST(FactorialTest, HandlesNegative) {
    EXPECT_EQ(math_utils::factorial(-3), -1);
}

TEST(AverageTest, HandlesEmpty) {
    EXPECT_DOUBLE_EQ(math_utils::average({}), 0.0);
}

TEST(AverageTest, ComputesCorrectly) {
    EXPECT_DOUBLE_EQ(math_utils::average({1, 2, 3, 4, 5}), 3.0);
    EXPECT_DOUBLE_EQ(math_utils::average({100}), 100.0);
}
```

**运行方式:**
```bash
mkdir build && cd build
cmake ..
cmake --build .
ctest --output-on-failure
```

**预期输出:**
```
Test project .../example1/build
    Start 1: FactorialTest.HandlesZero
1/6 Test #1: FactorialTest.HandlesZero .........   Passed
    Start 2: FactorialTest.HandlesOne
2/6 Test #2: FactorialTest.HandlesOne ..........   Passed
    Start 3: FactorialTest.HandlesPositive
3/6 Test #3: FactorialTest.HandlesPositive .....   Passed
    Start 4: FactorialTest.HandlesNegative
4/6 Test #4: FactorialTest.HandlesNegative .....   Passed
    Start 5: AverageTest.HandlesEmpty
5/6 Test #5: AverageTest.HandlesEmpty ..........   Passed
    Start 6: AverageTest.ComputesCorrectly
6/6 Test #6: AverageTest.ComputesCorrectly .....   Passed

100% tests passed, 0 tests failed out of 6
```

> [!note] 离线运行
> 第一次 configure 后，`_deps/` 中已有 googletest 源码。再次 configure 时设置 `FETCHCONTENT_UPDATES_DISCONNECTED=ON`：
> ```bash
> cmake -B build -DFETCHCONTENT_UPDATES_DISCONNECTED=ON
> ```
> 将跳过 `git fetch`，直接使用已有源码。

---

### 示例 2：Fetch Header-Only 库（nlohmann/json）

本示例演示通过 URL 下载 header-only 库，适合不需要编译的场景。

**项目结构:**
```
example2/
├── CMakeLists.txt
└── src/
    ├── CMakeLists.txt
    └── main.cpp
```

**顶层 CMakeLists.txt:**

```cmake
cmake_minimum_required(VERSION 3.24)
project(FetchHeaderOnlyExample VERSION 1.0.0 LANGUAGES CXX)

include(FetchContent)

# 下载 nlohmann/json 的 include-only 压缩包
# include.zip 只包含 single_include/ 目录，非常适合 FetchContent
FetchContent_Declare(
  json
  URL      https://github.com/nlohmann/json/releases/download/v3.11.3/include.zip
  URL_HASH SHA256=a22461d13119ac5c78f205d3df1db13403e58ce1bb1794edc9313677313f4a9d
)

# 注意：nlohmann/json 的 include.zip 没有 CMakeLists.txt
# 不能直接用 FetchContent_MakeAvailable() — 需要手动创建 target

FetchContent_GetProperties(json)
if(NOT json_POPULATED)
  FetchContent_Populate(json)
endif()

# 为 header-only 库手动创建 INTERFACE target
add_library(nlohmann_json INTERFACE)
target_include_directories(nlohmann_json INTERFACE
  ${json_SOURCE_DIR}/include
)
# 传播编译特性
target_compile_features(nlohmann_json INTERFACE cxx_std_17)

# 添加别名，方便使用者
add_library(nlohmann_json::nlohmann_json ALIAS nlohmann_json)

add_subdirectory(src)
```

**src/CMakeLists.txt:**

```cmake
add_executable(json_demo
  main.cpp
)

target_link_libraries(json_demo PRIVATE
  nlohmann_json
)
```

**src/main.cpp:**

```cpp
#include <nlohmann/json.hpp>
#include <iostream>
#include <string>

using json = nlohmann::json;

int main() {
    // 解析 JSON 字符串
    std::string raw = R"({
        "name": "CMake FetchContent",
        "awesome": true,
        "topics": ["build systems", "C++", "dependency management"],
        "version": {"major": 3, "minor": 24}
    })";

    auto data = json::parse(raw);

    // 访问字段
    std::cout << "Project: " << data["name"] << '\n';
    std::cout << "Awesome: " << std::boolalpha << data["awesome"] << '\n';

    // 遍历数组
    std::cout << "Topics: ";
    for (const auto& t : data["topics"]) {
        std::cout << t << "  ";
    }
    std::cout << '\n';

    // 序列化
    std::cout << "Version: " << data["version"].dump() << '\n';

    return 0;
}
```

**运行方式:**
```bash
mkdir build && cd build
cmake ..
cmake --build .
./src/json_demo     # 或 src\Debug\json_demo.exe (Windows)
```

**预期输出:**
```
Project: CMake FetchContent
Awesome: true
Topics: build systems  C++  dependency management
Version: {"major":3,"minor":24}
```

> [!warning] Header-Only 库没有 CMakeLists.txt 时
> `FetchContent_MakeAvailable()` 内部调用 `add_subdirectory()`，但如果依赖的根目录没有 `CMakeLists.txt`，调用会失败。此时需要降级使用 `FetchContent_Populate()` 只下载，然后手动创建 `INTERFACE` target。
>
> 有些 header-only 库（如 `fmt`）提供了完整的 CMakeLists.txt，可以直接用 `FetchContent_MakeAvailable()`。优先使用后者。

---

### 示例 3：FetchContent 与 find_package 共存

本示例演示如何让同一个 CMakeLists.txt 适配两种场景：
- 开发者机器已安装 `libfmt-dev` → 使用系统包
- CI 环境或新机器没有安装 → 自动 FetchContent 下载

**项目结构:**
```
example3/
├── CMakeLists.txt
└── src/
    ├── CMakeLists.txt
    └── main.cpp
```

**顶层 CMakeLists.txt:**

```cmake
cmake_minimum_required(VERSION 3.24)
project(FetchOrFindExample VERSION 1.0.0 LANGUAGES CXX)

include(FetchContent)

# ---- 全局策略：优先使用系统包 ----
set(FETCHCONTENT_TRY_FIND_PACKAGE_MODE ALWAYS CACHE STRING
    "Prefer system packages: ALWAYS | OPT_IN | NEVER")

# ---- 声明 fmt，带 find_package 回退 ----
FetchContent_Declare(
  fmt
  GIT_REPOSITORY https://github.com/fmtlib/fmt.git
  GIT_TAG        11.0.2
  GIT_SHALLOW    TRUE
  FIND_PACKAGE_ARGS 9.0 CONFIG   # find_package(fmt 9.0 CONFIG)
)

# MakeAvailable 会先尝试 find_package(fmt 9.0 CONFIG)
# 找不到则下载 + add_subdirectory
FetchContent_MakeAvailable(fmt)

add_subdirectory(src)
```

**src/CMakeLists.txt:**

```cmake
add_executable(fmt_demo
  main.cpp
)

# fmt::fmt 是 fmt 库导出的 target
# 无论走 find_package 还是 FetchContent，这个 target 都存在
target_link_libraries(fmt_demo PRIVATE
  fmt::fmt
)
```

**src/main.cpp:**

```cpp
#include <fmt/core.h>
#include <fmt/chrono.h>
#include <vector>
#include <string>

int main() {
    // fmt::format 示例
    std::string msg = fmt::format("Hello, {}! You have {} new messages.",
                                   "Alice", 7);
    fmt::print("{}\n", msg);

    // 格式化数字
    double pi = 3.14159265358979;
    fmt::print("pi ≈ {:.3f}\n", pi);

    // 格式化容器（需要 include <fmt/ranges.h>，fmt 10+）
    std::vector<int> values = {1, 2, 3, 4, 5};
    fmt::print("values = {}\n", values);

    // fmt::print 直接输出到 stderr
    fmt::print(stderr, "Debug: processed {} items\n", values.size());

    return 0;
}
```

**运行方式:**
```bash
# 场景 A：不安装 fmt，让 FetchContent 自动下载
mkdir build && cd build
cmake ..
cmake --build .
./src/fmt_demo

# 场景 B：预先安装 fmt（Ubuntu/Debian 示例）
sudo apt install libfmt-dev
cmake -B build
cmake --build build
./build/src/fmt_demo
# 输出相同，但 fmt 来自系统包而非下载

# 场景 C：强制 FetchContent（即使系统已安装）
cmake -B build -DFETCHCONTENT_TRY_FIND_PACKAGE_MODE=NEVER
cmake --build build
```

**预期输出:**
```
Hello, Alice! You have 7 new messages.
pi ≈ 3.142
values = [1, 2, 3, 4, 5]
Debug: processed 5 items
```

> [!note] CMake 配置输出差异
> 场景 A 的 CMake 输出中你会看到：
> ```
> -- Populating fmt
> -- Configuring done (fmt)
> ```
> 场景 B 中你会看到：
> ```
> -- Found fmt: /usr/lib/cmake/fmt/fmt-config.cmake (found version "10.2.1")
> ```

---

## 3. 练习

### 练习 1：添加 googletest 并编写测试

**目标**：创建一个使用 FetchContent 下载 googletest 的项目，并编写完整测试。

**要求**：
1. 创建一个项目，包含一个 `string_utils` 库，提供以下函数：
   - `std::string trim(const std::string& s)` — 去除首尾空格
   - `std::vector<std::string> split(const std::string& s, char delim)` — 按分隔符拆分
   - `bool starts_with(const std::string& s, const std::string& prefix)` — 前缀匹配
2. 使用 FetchContent 下载 googletest（版本 v1.15.2 或更新）
3. 为每个函数编写至少 3 个测试用例（含边界情况）
4. 使用 `gtest_discover_tests` 自动注册测试
5. 支持 `FETCHCONTENT_UPDATES_DISCONNECTED` 离线模式

**验证**：`ctest --output-on-failure` 全部通过。

> [!tip]- 参考实现思路
> - 声明 googletest 在最顶层，MakeAvailable 之前完成所有声明
> - `string_utils` 使用 `STATIC` 库，`cxx_std_17`
> - 测试 target 链接 `string_utils` 和 `gtest_main`
> - `trim("  hello  ")` → `"hello"`
> - `trim("")` → `""`
> - `split("a,b,c", ',')` → `{"a", "b", "c"}`
> - `split("single", ',')` → `{"single"}`
> - `starts_with("hello world", "hello")` → `true`
> - `starts_with("hello world", "world")` → `false`

---

### 练习 2：通过 URL 下载库并使用 SHA256 校验

**目标**：使用 URL 方式下载一个库，提供 SHA256 hash 校验，并集成到项目中。

**要求**：
1. 选择以下 header-only 库之一，通过 URL 下载：
   - `nlohmann/json` (`include.zip`)
   - `doctest` (`doctest.h` 单头文件)
2. 计算并提供正确的 SHA256 hash
3. 如果库没有 CMakeLists.txt，手动创建 `INTERFACE` target
4. 编写使用该库的示例程序
5. 故意修改 hash 为错误值，验证 CMake 会在 configure 时报告 `hash mismatch` 错误

**验证**：
- 正确的 hash 时 configure 和 build 成功
- 错误的 hash 时 configure 失败并显示 `hash mismatch`

> [!tip]- 提示：doctest 集成示例
> ```cmake
> FetchContent_Declare(
>   doctest
>   URL      https://raw.githubusercontent.com/doctest/doctest/v2.4.11/doctest/doctest.h
>   URL_HASH SHA256=<计算实际 hash>
>   DOWNLOAD_NO_EXTRACT TRUE  # .h 文件不需要解压
> )
>
> FetchContent_GetProperties(doctest)
> if(NOT doctest_POPULATED)
>   FetchContent_Populate(doctest)
> endif()
>
> add_library(doctest INTERFACE)
> target_include_directories(doctest INTERFACE ${doctest_SOURCE_DIR})
> ```

**目标**：创建一个项目，使用 `FIND_PACKAGE_ARGS` 让依赖在系统包和 FetchContent 之间自动切换。

**要求**：
1. 使用 `fmt` 库（或 `spdlog`），带 `FIND_PACKAGE_ARGS`
2. 设置 `FETCHCONTENT_TRY_FIND_PACKAGE_MODE` 为 `ALWAYS`
3. 实现三种验证场景：
   - **场景 A**：未安装系统包 → 自动 FetchContent 下载
   - **场景 B**：安装系统包 → 使用系统包
   - **场景 C**：安装系统包但设置 `FETCHCONTENT_TRY_FIND_PACKAGE_MODE=NEVER` → 忽略系统包，强制 FetchContent
4. 在 `CMakeLists.txt` 中用 `message()` 输出实际使用了哪种方式（提示：检查 `<name>_POPULATED` 变量）

> [!tip]- 提示：检测来源
> ```cmake
> FetchContent_MakeAvailable(fmt)
>
> if(fmt_POPULATED)
>   message(STATUS "fmt: fetched from source (v11.0.2)")
> else()
>   message(STATUS "fmt: found system package")
> endif()
> ```


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **顶层 `CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(StringUtilsTest VERSION 1.0 LANGUAGES CXX)
>
> include(FetchContent)
>
> # ---- FetchContent Declarations ----
> FetchContent_Declare(
>     googletest
>     GIT_REPOSITORY https://github.com/google/googletest.git
>     GIT_TAG        v1.15.2
>     GIT_SHALLOW    TRUE
> )
>
> # ---- FetchContent MakeAvailable ----
> FetchContent_MakeAvailable(googletest)
>
> enable_testing()
>
> add_subdirectory(src)
> add_subdirectory(tests)
> ```
>
> **`src/CMakeLists.txt`：**
> ```cmake
> add_library(string_utils STATIC
>     string_utils.cpp
> )
> target_include_directories(string_utils PUBLIC include)
> target_compile_features(string_utils PUBLIC cxx_std_17)
> ```
>
> **`src/include/string_utils.h`：**
> ```cpp
> #pragma once
> #include <string>
> #include <vector>
>
> std::string trim(const std::string& s);
> std::vector<std::string> split(const std::string& s, char delim);
> bool starts_with(const std::string& s, const std::string& prefix);
> ```
>
> **`src/string_utils.cpp`：**
> ```cpp
> #include "string_utils.h"
> #include <algorithm>
> #include <sstream>
>
> std::string trim(const std::string& s) {
>     auto start = std::find_if_not(s.begin(), s.end(), ::isspace);
>     auto end   = std::find_if_not(s.rbegin(), s.rend(), ::isspace).base();
>     return (start < end) ? std::string(start, end) : "";
> }
>
> std::vector<std::string> split(const std::string& s, char delim) {
>     std::vector<std::string> result;
>     std::istringstream iss(s);
>     std::string token;
>     while (std::getline(iss, token, delim))
>         result.push_back(token);
>     if (!s.empty() && s.back() == delim)
>         result.push_back("");
>     return result;
> }
>
> bool starts_with(const std::string& s, const std::string& prefix) {
>     return s.size() >= prefix.size() &&
>            s.compare(0, prefix.size(), prefix) == 0;
> }
> ```
>
> **`tests/CMakeLists.txt`：**
> ```cmake
> add_executable(test_string_utils test_string_utils.cpp)
> target_link_libraries(test_string_utils PRIVATE string_utils gtest_main)
>
> include(GoogleTest)
> gtest_discover_tests(test_string_utils)
> ```
>
> **`tests/test_string_utils.cpp`：**
> ```cpp
> #include <gtest/gtest.h>
> #include "string_utils.h"
>
> TEST(TrimTest, Basic)       { EXPECT_EQ(trim("  hello  "), "hello"); }
> TEST(TrimTest, Empty)       { EXPECT_EQ(trim(""), ""); }
> TEST(TrimTest, NoWhitespace){ EXPECT_EQ(trim("abc"), "abc"); }
>
> TEST(SplitTest, Normal)     { EXPECT_EQ(split("a,b,c", ','), (std::vector<std::string>{"a","b","c"})); }
> TEST(SplitTest, Single)     { EXPECT_EQ(split("single", ','), (std::vector<std::string>{"single"})); }
> TEST(SplitTest, Trailing)   { EXPECT_EQ(split("a,b,", ','), (std::vector<std::string>{"a","b",""})); }
>
> TEST(StartsWithTest, Match)       { EXPECT_TRUE(starts_with("hello world", "hello")); }
> TEST(StartsWithTest, NoMatch)     { EXPECT_FALSE(starts_with("hello world", "world")); }
> TEST(StartsWithTest, Longer)      { EXPECT_FALSE(starts_with("hi", "hello")); }
> ```
>
> **离线模式：**
> ```bash
> cmake -B build -DFETCHCONTENT_UPDATES_DISCONNECTED=ON
> cmake --build build
> ctest --test-dir build --output-on-failure
> ```

> [!tip]- 练习 2 参考答案
> **采用 `nlohmann/json`（有 CMakeLists.txt 的 header-only 库）：**
> ```cmake
> include(FetchContent)
> FetchContent_Declare(
>     json
>     URL      https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
>     URL_HASH SHA256=d5c65a8f12ccfe2783714c7a2af2cf1b5400e853e420b4a5b38aca9adfe98e09
> )
> FetchContent_MakeAvailable(json)
>
> add_executable(json_demo main.cpp)
> target_link_libraries(json_demo PRIVATE nlohmann_json::nlohmann_json)
> ```
>
> **采用 `doctest`（单头文件，无 CMakeLists.txt）：**
> ```cmake
> include(FetchContent)
> FetchContent_Declare(
>     doctest
>     URL      https://raw.githubusercontent.com/doctest/doctest/v2.4.11/doctest/doctest.h
>     URL_HASH SHA256=632ed61c05b2b2a9987cd0ae370a760e0b4eef3f6f2be67f42ebd6f1c6e99f82
>     DOWNLOAD_NO_EXTRACT TRUE
> )
> FetchContent_GetProperties(doctest)
> if(NOT doctest_POPULATED)
>     FetchContent_Populate(doctest)
> endif()
>
> add_library(doctest INTERFACE)
> target_include_directories(doctest INTERFACE ${doctest_SOURCE_DIR})
>
> # 使用
> add_executable(test_runner test.cpp)
> target_link_libraries(test_runner PRIVATE doctest)
> ```
>
> **获取 SHA256：**
> ```bash
> curl -sL <URL> | sha256sum
> ```
>
> **验证 hash 错误时配置失败：** 故意改错 hash 值，`cmake -B build` 会报 `hash mismatch`。

> [!tip]- 练习 3 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(FetchOrFind VERSION 1.0 LANGUAGES CXX)
>
> set(FETCHCONTENT_TRY_FIND_PACKAGE_MODE ALWAYS CACHE STRING
>     "Prefer system packages over FetchContent")
>
> include(FetchContent)
>
> FetchContent_Declare(
>     fmt
>     GIT_REPOSITORY https://github.com/fmtlib/fmt.git
>     GIT_TAG        11.0.2
>     GIT_SHALLOW    TRUE
>     FIND_PACKAGE_ARGS 9.0 CONFIG
> )
>
> FetchContent_MakeAvailable(fmt)
>
> if(fmt_POPULATED)
>     message(STATUS "fmt: fetched from source (v11.0.2)")
> else()
>     message(STATUS "fmt: found system package")
> endif()
>
> add_executable(demo main.cpp)
> target_link_libraries(demo PRIVATE fmt::fmt)
> ```
>
> **三种场景验证：**
>
> **场景 A（无系统包）：**
> ```bash
> cmake -B build
> # 输出: fmt: fetched from source (v11.0.2)
> ```
>
> **场景 B（安装系统包后）：**
> ```bash
> sudo apt install libfmt-dev   # 或 brew install fmt
> cmake -B build
> # 输出: fmt: found system package
> ```
>
> **场景 C（强制 FetchContent）：**
> ```bash
> cmake -B build -DFETCHCONTENT_TRY_FIND_PACKAGE_MODE=NEVER
> # 输出: fmt: fetched from source (v11.0.2)
> # 即使系统包已安装，也忽略它
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [[CMake 官方文档 — FetchContent|https://cmake.org/cmake/help/latest/module/FetchContent.html]] — 完整 API 参考
- [[CMake 官方文档 — ExternalProject|https://cmake.org/cmake/help/latest/module/ExternalProject.html]] — 了解 FetchContent 的"表亲"
- [[cmake-init — 项目模板|https://github.com/friendlyanon/cmake-init]] — 社区推崇的 Modern CMake 项目生成器，使用 FetchContent 管理所有依赖
- [[CGold: The Hitchhiker's Guide to the CMake|https://cgold.readthedocs.io/]] — 社区维护的 CMake 最佳实践指南，含 FetchContent 深入讨论
- [[11-install-and-export-targets]] — 理解依赖的 target 导出机制
- [[12-cpack-packaging]] — 将 FetchContent 获取的依赖打包分发

> [!note] CMake 4.0 展望
> CMake 4.0 计划引入 `Dependency Providers` 机制，允许项目注册自定义依赖解析器。FetchContent 将成为内置 provider 之一，与 vcpkg、Conan 等外部 package manager 在同一优先级上协同工作。详见 [[23-cmake-4-and-future]]。

---

## 常见陷阱

### 1. 使用分支名而非 commit hash 作为 GIT_TAG

```cmake
# ❌ 危险 — main 分支内容随时会变
FetchContent_Declare(mylib GIT_TAG main ...)

# ✅ 安全 — commit hash 不可变
FetchContent_Declare(mylib GIT_TAG a1b2c3d4e5f6... ...)
```

**后果**：昨天的 CI 构建和今天的 CI 构建可能链接到不同的源码，导致 bug 不可重现、难以调试。

**解决**：永远使用 commit hash 或 release tag。tag 通常是不可变的（约定俗成），但 commit hash 是绝对保证。如果必须使用分支名（如内部库的 nightly 构建），请确保在 CI 中同时记录实际使用的 commit hash。

### 2. 在声明完成前调用 FetchContent_MakeAvailable

```cmake
# ❌ 错误 — 先 MakeAvailable 后声明 fmt
FetchContent_Declare(json GIT_TAG ... ...)
FetchContent_MakeAvailable(json)  # json 内部依赖 fmt → 此时 json 的 fmt 声明生效

FetchContent_Declare(fmt GIT_TAG ... ...)  # ← 这个声明被忽略！
FetchContent_MakeAvailable(fmt)

# ✅ 正确 — 所有声明在前
FetchContent_Declare(json GIT_TAG ... ...)
FetchContent_Declare(fmt GIT_TAG ... ...)
FetchContent_MakeAvailable(json)
FetchContent_MakeAvailable(fmt)
```

**后果**：如果 `json` 内部声明了 `fmt` 的旧版本，你的 `fmt` 声明会被忽略，导致版本冲突或链接错误。

**解决**：严格遵循"声明全部在前，MakeAvailable 全部在后"的规则。可添加注释 `# ---- FetchContent Declarations ----` 和 `# ---- FetchContent MakeAvailable ----` 作为视觉分隔。

### 3. 不使用 FIND_PACKAGE_ARGS 导致重复编译

```cmake
# ❌ 浪费 — 即使系统已安装也重新下载编译
FetchContent_Declare(fmt GIT_TAG 11.0.2 ...)
FetchContent_MakeAvailable(fmt)

# ✅ 高效 — 系统有就用系统的
FetchContent_Declare(
  fmt
  GIT_REPOSITORY https://github.com/fmtlib/fmt.git
  GIT_TAG        11.0.2
  FIND_PACKAGE_ARGS 9.0 CONFIG
)
FetchContent_MakeAvailable(fmt)
```

**后果**：在 Docker 镜像或开发者机器上重复编译常见库（fmt、spdlog、nlohmann/json），浪费时间和计算资源。

**解决**：为所有主流库添加 `FIND_PACKAGE_ARGS`，并设置 `FETCHCONTENT_TRY_FIND_PACKAGE_MODE=ALWAYS`。这保证系统包优先，FetchContent 作为 fallback。

### 4. Header-Only 库使用 FetchContent_MakeAvailable 失败

```cmake
# ❌ 错误 — include.zip 没有 CMakeLists.txt
FetchContent_Declare(json URL ... URL_HASH ...)
FetchContent_MakeAvailable(json)
# CMake Error: .../json-src/CMakeLists.txt not found

# ✅ 正确 — 手动 Populate + 创建 INTERFACE target
FetchContent_GetProperties(json)
if(NOT json_POPULATED)
  FetchContent_Populate(json)
endif()
add_library(nlohmann_json INTERFACE)
target_include_directories(nlohmann_json INTERFACE ${json_SOURCE_DIR}/include)
```

**解决**：检查依赖是否有 `CMakeLists.txt`。如果没有（如纯 header-only 的单文件分发），使用 `FetchContent_Populate()` 只下载，然后手动创建 target。

### 5. 忘记处理传递依赖的版本冲突

```cmake
FetchContent_Declare(libA GIT_TAG v1.0 ...)
FetchContent_Declare(libB GIT_TAG v2.0 ...)
FetchContent_MakeAvailable(libA)
FetchContent_MakeAvailable(libB)
```

如果 `libA` 和 `libB` 都依赖 `fmt`，但版本不同（如 `libA` 要 9.0，`libB` 要 10.0），首次声明获胜规则会选第一个遇到的版本。这可能导致 `libB` 编译失败。

**解决**：
1. 在顶层显式声明共享依赖的版本，确保版本统一
2. 使用 `FIND_PACKAGE_ARGS` 让系统包管理版本
3. 如果无法统一版本，考虑用 ExternalProject_Add 隔离构建

### 6. 超大仓库未使用 GIT_SHALLOW

```cmake
# ❌ 缓慢 — clone 完整历史（boost 仓库可能有数 GB）
FetchContent_Declare(boost GIT_REPOSITORY ... GIT_TAG boost-1.85.0)

# ✅ 快速 — 只 clone 指定 tag 的最新 commit
FetchContent_Declare(
  boost
  GIT_REPOSITORY https://github.com/boostorg/boost.git
  GIT_TAG        boost-1.85.0
  GIT_SHALLOW    TRUE
  GIT_PROGRESS   TRUE    # 显示 clone 进度
)
```

**解决**：除非你需要完整 git 历史（极少数情况），始终添加 `GIT_SHALLOW TRUE`。对于 GitHub 仓库，`SOURCE_SUBDIR` 常与 `GIT_SHALLOW TRUE` 配合使用。

### 7. 在库项目中使用 FetchContent 污染使用者配置

如果你的项目是一个库（而非最终可执行文件），在 `CMakeLists.txt` 中使用 `FetchContent_MakeAvailable()` 会强制所有使用你库的项目也下载这些依赖——即使它们想用自己的版本。

**解决**：
- 在库项目中，用 `FetchContent_Declare()` + `FetchContent_Populate()`，然后手动 `add_library` 并设置为 `EXCLUDE_FROM_ALL`
- 或者使用 `find_dependency` 宏让使用者决定依赖来源
- 将 FetchContent 逻辑放在 `if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)` 保护中（即只在作为顶层项目时启用）
