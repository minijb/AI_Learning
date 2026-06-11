---
title: "CMake 内部架构——配置/生成/构建"
updated: 2026-06-10
---

> 所属计划: [[plan|CMake 深度学习]]
> 预计耗时: 50 分钟
> 前置知识: [[04-variables-cache-and-scope|04 变量、缓存与作用域]]、[[08-generator-expressions|08 生成器表达式]]

---

## 1. 概念讲解

### 为什么需要这个？

大多数 CMake 用户把 `cmake -B build && cmake --build build` 当作黑箱。直到有一天：

- 你改了一个 generator expression，重新 `cmake --build` 但行为没变——因为 genex 在 configure 时已经"定死"了？
- 你删了 `CMakeCache.txt`，突然所有 `find_package` 都重新搜索了——为什么？
- 你在 VS 里切换了 Debug→Release，但 CMake 单配置生成器根本不理你——这到底是谁的职责？

理解 CMake 内部三阶段架构，是区分"会用 CMake"和"能调试 CMake 问题"的分水岭。

### 核心思想

CMake 的工作分为三个**严格顺序**的阶段：

```
cmake -B build          cmake --build build
┌──────────┐           ┌──────────┐           ┌───────────┐
│CONFIGURE │ ────────→ │GENERATE  │ ────────→ │  BUILD    │
│(cmake)   │           │(cmake)   │           │(make/ninja│
│          │           │          │           │ /MSBuild) │
└──────────┘           └──────────┘           └───────────┘
     ↑                                            │
     │              cmake --build                 │
     │    (检测到 CMakeLists.txt 变更时自动        │
     │     重新 configure + generate)             │
     └────────────────────────────────────────────┘
```

**关键事实：** `cmake --build` 期间，CMake **本身不参与编译**。它只是启动原生构建工具（make/ninja/MSBuild），然后退场。如果源文件变了，原生构建工具自行决定增量编译；但如果 `CMakeLists.txt` 变了，需要重新运行 configure+generate。

> [!tip] 类比
> CMake 是"图纸设计师"，不是"施工队"。
> - Configure = 画图纸（目标图、依赖关系、变量值）
> - Generate = 把图纸翻译成施工指令（Makefile、build.ninja、.sln）
> - Build = 施工队按指令干活（make、ninja、MSBuild）

---

### 阶段 1：Configure（配置）

Configure 是 CMake 的"执行"阶段——CMake 真正运行你的 `CMakeLists.txt`。

**入口点：**
```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
# 或显式指定
cmake -B build --configure  # CMake 4.0+
```

**执行的步骤（按顺序）：**

1. **读取 `CMakeCache.txt`**（如果存在）——恢复上次 configure 的所有缓存变量
2. **设置平台信息**——检测编译器、架构、系统名（`CMAKE_SYSTEM_NAME`、`CMAKE_C_COMPILER` 等）
3. **执行顶层 `CMakeLists.txt`**——从 `cmake_minimum_required(VERSION ...)` 开始，逐行解释执行
4. **`project()` 调用**——启用语言（C/CXX），设置 `PROJECT_SOURCE_DIR`、`PROJECT_BINARY_DIR`
5. **处理子目录**——每个 `add_subdirectory()` 创建一个新的作用域，CMake 递归进入并执行其 `CMakeLists.txt`
6. **构建目标图（Target Dependency Graph）**——每遇到 `add_executable`/`add_library`，CMake 在内存中创建一个 target 节点；`target_link_libraries` 建立有向边
7. **解析 `find_package`**——搜索 Find 模块或 Config 文件，导入外部 target
8. **写入 `CMakeCache.txt`**——将所有 `set(... CACHE ...)` 变量和自动检测的值持久化

**Configure 完成后 CMake 内存中的数据结构：**

```
cmState
 ├── cmMakefile (顶层目录)
 │   ├── variables: {CMAKE_BUILD_TYPE: "Release", ...}
 │   ├── targets: {my_app, my_lib}
 │   │   ├── cmTarget "my_app" (EXECUTABLE)
 │   │   │   ├── sources: [main.cpp, util.cpp]
 │   │   │   ├── linkLibraries: [my_lib]
 │   │   │   ├── includeDirectories: [...]
 │   │   │   └── properties: {CXX_STANDARD: 17, ...}
 │   │   └── cmTarget "my_lib" (STATIC_LIBRARY)
 │   │       ├── sources: [lib.cpp]
 │   │       └── ...
 │   └── subdirectories: [src/, tests/]
 └── cmGlobalGenerator
     ├── generatorName: "Ninja" | "Unix Makefiles" | ...
     └── targets (global view of all targets)
```

> [!warning] 关键限制
> Configure 阶段**不能知道 generate 阶段的信息**。例如：
> - 你不能在 `if()` 中使用 generator expression（genex 还没被求值）
> - 你不能读取 `$<CONFIG>` 来决定 `target_link_libraries` 的走向（genex 在 generate 时才展开）
> - 文件系统操作（`file(GLOB ...)`）只在 configure 时执行一次

---

### 阶段 2：Generate（生成）

Generate 阶段将内存中的 target graph **翻译成原生构建系统的输入文件**。

**触发方式：**
```bash
cmake -B build          # configure + generate 连续执行
cmake --build build     # 如果 CMakeLists.txt 变更，自动重新 configure+generate
```

**执行的步骤：**

1. **遍历所有 target**——cmGlobalGenerator 遍历 target DAG
2. **求值 generator expressions**——这是 genex 唯一被求值的阶段。`$<CONFIG>`、`$<TARGET_FILE:...>`、`$<IF:...>` 都在此时展开
3. **计算编译规则**——每个 source file 的完整命令行（include path、compile definitions、compile options）
4. **计算链接规则**——每个 target 的链接库列表、链接目录、链接选项
5. **写出构建文件**——根据生成器类型：
   - **Makefile 生成器**: 写出 `Makefile`、`cmake.check_cache`、各子目录的 `CMakeFiles/<target>.dir/build.make`
   - **Ninja 生成器**: 写出 `build.ninja`、`build/.ninja_log`、`.ninja_deps`
   - **Visual Studio 生成器**: 写出 `.sln`、`.vcxproj`、`.vcxproj.filters`
   - **Xcode 生成器**: 写出 `.xcodeproj/project.pbxproj`
6. **写出 `cmake_install.cmake`**——每个 `install()` 命令被翻译成 CMake 脚本，供 `cmake --install` 使用
7. **写出 `CMakeCache.txt` 的最终版本**——包含生成器相关的 computed 值

**Generator expressions 的角色：**

Genex 是 configure 和 generate 之间的"信使"。在 configure 时你只写入**模板**，在 generate 时 CMake 根据实际配置展开：

```cmake
# configure 时：只记录 genex 字符串
target_link_libraries(my_app PRIVATE
    $<$<CONFIG:Debug>:debug_lib>
    $<$<CONFIG:Release>:release_lib>
)

# generate 时（Release 配置）：
# → target_link_libraries(my_app PRIVATE release_lib)
```

> [!tip] 单配置 vs 多配置
> - **单配置生成器**（Makefiles、Ninja）：`CMAKE_BUILD_TYPE` 在 configure 时确定配置。Genex `$<CONFIG>` 展开为固定值。切换配置需要重新 configure。
> - **多配置生成器**（Visual Studio、Xcode、Ninja Multi-Config）：configure 时不指定配置。Generate 时为**所有配置**展开 genex，写入条件规则（如 `.vcxproj` 中的 `<Configuration>` 条件块）。构建时通过 `--config` 选择。

---

### 阶段 3：Build（构建）

Build 阶段 **CMake 完全不参与**。

```bash
cmake --build build              # 调用默认原生工具
cmake --build build --config Release  # 多配置生成器：选择配置
cmake --build build -j 8         # 并行度
```

`cmake --build` 的实际行为是**包装器**：

| 生成器 | `cmake --build` 实际执行的命令 |
|--------|------------------------------|
| Unix Makefiles | `make -C <build_dir>` |
| Ninja | `ninja -C <build_dir>` |
| Visual Studio | `msbuild <build_dir>/<project>.sln /p:Configuration=<config>` |
| Xcode | `xcodebuild -project <build_dir>/<project>.xcodeproj` |
| Ninja Multi-Config | `ninja -C <build_dir> -f build-<config>.ninja` |

**增量构建判断**完全由原生工具负责——CMake 不管文件时间戳比较。如果 `CMakeLists.txt` 或任何 CMake 输入文件的时间戳比构建系统文件新，`cmake --build` 会**自动触发重新 configure+generate**。

---

### CMakeCache.txt：缓存的生命周期

`CMakeCache.txt` 是 CMake 的"持久化记忆"。它让 CMake 记住上次 configure 的结果，避免每次都重新检测一切。

```
生命周期：
┌─────────┐     ┌─────────┐     ┌─────────┐
│不存在/  │ →  │configure│ →  │generate │ → 写入最终版
│上次残存 │ 读取│时更新    │ 写入│后补充    │   CMakeCache.txt
└─────────┘     └─────────┘     └─────────┘
```

**读取时机：** configure 开始的第一步。CMake 解析 `CMakeCache.txt`，恢复所有 `//` 注释行中的 `VARNAME:TYPE=VALUE` 条目。

**写入时机：**
1. Configure 阶段内：每次 `set(... CACHE ...)` 立即更新内存中的 cache 并标记 dirty
2. Configure 结束时：将内存 cache 刷写到磁盘
3. Generate 结束时：追加 computed 条目（如 `CMAKE_C_COMPILER_ID` 之类自动检测的值）

**为什么删除它就能"重置"：**
```bash
rm build/CMakeCache.txt
cmake -B build   # 所有 find_package 会重新搜索，所有自动检测重新运行
```

删除 `CMakeCache.txt` 不会删除 `CMakeFiles/` 和已构建的 `.o` 文件，所以增量构建仍然可行——但 configure 会从零开始。

> [!warning] 不要手动编辑 CMakeCache.txt 然后用 `cmake --build`
> `cmake --build` 检测到源文件变更时会自动重新 configure，**覆盖**你的手动修改。正确做法是用 `-D` 传参或者用 `ccmake`/`cmake-gui`。

---

### CMakeFiles/ 目录结构

每个构建目录和每个子目录下都会生成 `CMakeFiles/`，存放 CMake 的内部产物：

```
build/
├── CMakeCache.txt
├── CMakeFiles/
│   ├── 3.28.0/                          # CMake 版本特定文件
│   │   ├── CMakeCCompiler.cmake          # C 编译器检测结果
│   │   ├── CMakeCXXCompiler.cmake        # C++ 编译器检测结果
│   │   ├── CMakeSystem.cmake             # 系统检测结果
│   │   └── CMakeDetermineCompilerABI_*.bin
│   ├── CMakeConfigureLog.yaml            # configure 日志 (CMake 3.26+)
│   ├── CMakeDirectoryInformation.cmake   # 目录级信息
│   ├── CMakeOutput.log                   # 编译器检测输出
│   ├── CMakeError.log                    # 编译器检测错误
│   ├── pkgRedirects/                     # pkg-config 重定向
│   └── <target>.dir/                     # 每个 target 一个目录
│       ├── build.make                    # Makefile 生成器用
│       ├── depend.make                   # 依赖信息
│       ├── flags.make                    # 编译标志
│       ├── link.txt                      # 链接命令
│       └── compiler_depend.make          # 编译器依赖
├── build.ninja                           # Ninja 生成器
├── build-Release.ninja                   # Ninja Multi-Config
├── cmake_install.cmake                   # 安装脚本
└── CTestTestfile.cmake                   # 测试配置
```

**`CMakeDirectoryInformation.cmake`**：记录每个目录的 include 路径、compile definitions 等全局设置。子目录可以继承并覆盖父目录的设置。

**`cmake_install.cmake`**：包含所有 `install()` 命令翻译成的 CMake 脚本代码。运行 `cmake --install` 时，CMake 再次作为**脚本解释器**执行此文件（这是构建后 CMake 唯一的"回归"场景）。

---

### 目标依赖图（Target Dependency Graph）

CMake 在 configure 时构建一个**有向无环图（DAG）**，节点是 target，边是依赖关系。

```
     my_app (EXECUTABLE)
      /  \
     /    \
my_lib   ext_lib (IMPORTED)
(SHARED)
  |
my_util (STATIC)
```

**边是如何建立的：**

| 命令 | 产生的边 |
|------|---------|
| `target_link_libraries(A PUBLIC B)` | A → B（使用要求传播给 A 的消费者） |
| `target_link_libraries(A PRIVATE B)` | A → B（使用要求不传播） |
| `target_link_libraries(A INTERFACE B)` | A → B（只有使用要求传播，A 不真正链接 B） |
| `add_dependencies(A B)` | A → B（纯构建顺序依赖，无链接关系） |
| `add_subdirectory(sub)` | 目录间的隐式顺序依赖 |

**CMake 内部表示：**

- `cmComputeTargetDepends` 类负责计算 target 的完整依赖闭包
- 对于每个 target，CMake 计算：
  - **link closure**：所有参与链接的 target（传递闭包）
  - **usage requirements closure**：所有 INTERFACE/PUBLIC 使用要求的传递闭包
  - **build order**：拓扑排序，确保依赖库先构建
- 循环依赖会被 CMake 检测并报错（`Circular dependency detected`）

> [!tip] 为什么是 DAG 而不是树
> 两个 target 可以依赖同一个库，形成菱形依赖。CMake 保证该库只被链接一次，使用要求不会重复应用。

---

### 生成器（Generator）类型详解

CMake 的生成器决定"输出什么样的构建文件"。它们在 **configure 之初**就被选定，且不可更改（一旦选定，configure 产出的数据结构就已经为特定生成器优化）。

#### 单配置生成器

| 生成器 | `-G` 名称 | 构建文件 | `-j` 支持 |
|--------|----------|---------|----------|
| Unix Makefiles | `"Unix Makefiles"` | `Makefile` | `make -jN` |
| Ninja | `"Ninja"` | `build.ninja` | 自动并行 |
| MSYS Makefiles | `"MSYS Makefiles"` | `Makefile` | `make -jN` |
| MinGW Makefiles | `"MinGW Makefiles"` | `Makefile` | `mingw32-make -jN` |

**特点：**
- `CMAKE_BUILD_TYPE` **必须在 configure 时设置**（`-DCMAKE_BUILD_TYPE=Release`），configure 之后不可更改
- 生成的文件只包含**一种配置**的规则
- 输出目录平铺：`build/` 下直接放可执行文件和库

```bash
# 单配置工作流
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
# 要切换到 Debug：必须重新 configure
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build
```

#### 多配置生成器

| 生成器 | `-G` 名称 | 构建文件 | 配置选择 |
|--------|----------|---------|---------|
| Visual Studio | `"Visual Studio 17 2022"` | `.sln`, `.vcxproj` | `--config` |
| Xcode | `"Xcode"` | `.xcodeproj` | `--config` |
| Ninja Multi-Config | `"Ninja Multi-Config"` | `build-<config>.ninja` | `--config` |

**特点：**
- configure 时**不需要**指定 `CMAKE_BUILD_TYPE`（设置也没用）
- 生成的文件包含**所有配置**的规则（如 `.vcxproj` 里 `Debug|Win32`、`Release|Win32` 等条件块）
- 输出目录按配置分层：`build/Debug/`、`build/Release/` 等
- 构建时通过 `--config` 选择配置；同一个 build tree 可以构建多个配置

```bash
# 多配置工作流
cmake -B build -G "Ninja Multi-Config"
cmake --build build --config Debug
cmake --build build --config Release   # 同一个 build tree！
```

> [!warning] Ninja vs Ninja Multi-Config
> `Ninja`（单配置）和 `Ninja Multi-Config` 是**两个不同的生成器**。前者生成 `build.ninja`，后者生成 `build-Release.ninja`、`build-Debug.ninja` 等。不能混淆。

---

### 单配置 vs 多配置：输出目录对比

**单配置（Ninja + `CMAKE_BUILD_TYPE=Release`）：**
```
build/
├── build.ninja
├── my_app        # 可执行文件直接在此
├── libmy_lib.a   # 库文件直接在此
├── CMakeFiles/
└── ...
```

**多配置（Ninja Multi-Config）：**
```
build/
├── build-Debug.ninja
├── build-Release.ninja
├── Debug/
│   ├── my_app
│   └── libmy_lib.a
├── Release/
│   ├── my_app
│   └── libmy_lib.a
├── CMakeFiles/
└── ...
```

多配置生成器的 `$<TARGET_FILE:my_app>` 在 Debug 配置下生成 `build/Debug/my_app`，在 Release 配置下生成 `build/Release/my_app`。Genex 在 generate 阶段根据目标配置展开为对应路径。

---

### Generator Expressions：为什么需要它

Generator expressions 解决的核心矛盾：

> Configure 阶段需要做出决策，但决策所需的信息（如目标文件路径、最终编译标志）要到 Generate 阶段才知道。

具体场景：

1. **`$<CONFIG>`**：configure 时你不能假设用户会选 Debug 还是 Release（多配置生成器下尤其如此）
2. **`$<TARGET_FILE:tgt>`**：configure 时你不知道最终输出文件名（可能与 target 名不同，有前缀/后缀）
3. **`$<COMPILE_LANGUAGE>`**：一个源文件可能被多种语言编译（C 和 C++ 规则不同）
4. **`$<INSTALL_INTERFACE:...>` vs `$<BUILD_INTERFACE:...>`**：同一个 target 在构建树和安装树中的 include 路径完全不同

**时间线：**

```
configure 时:
  target_include_directories(my_lib PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  # CMake 只存储这个字符串，不尝试求值

generate 时:
  # 构建 my_app（依赖 my_lib）时：
  # $<BUILD_INTERFACE:...> → /home/user/project/include
  # $<INSTALL_INTERFACE:...> → （被丢弃）
  
  # 生成 my_lib 的安装规则时：
  # $<BUILD_INTERFACE:...> → （被丢弃）  
  # $<INSTALL_INTERFACE:...> → include
```

> [!tip] Genex 的两阶段求值
> Genex 的嵌套求值发生在 generate 阶段**两次**：
> 1. 第一次：展开 `$<BUILD_INTERFACE:...>` / `$<INSTALL_INTERFACE:...>` 等"用哪个值"的 genex
> 2. 第二次：展开配置相关的 genex（`$<CONFIG>`、`$<PLATFORM_ID>` 等）
> 
> 这使得同一个 target 在不同消费者（构建树 vs 安装树）和不同配置下可以有不同的属性值。

---

### CMake Server Mode → File-API

#### Server Mode（已废弃，CMake 3.15-3.20）

CMake 曾经提供 `cmake -E server` 模式，通过 stdin/stdout 的 JSON-RPC 协议让 IDE 查询项目结构。但因以下问题被废弃：
- 协议复杂，错误恢复困难
- 阻塞式通信限制并发
- 需要 CMake 进程常驻

#### CMake File-API（CMake 3.14+，当前标准）

File-API 换了一种思路：**不为 CMake 写通信协议，而是让它把信息写到文件里**。

**工作流程：**

```
1. IDE 创建查询目录
   build/.cmake/api/v1/query/
   ├── codemodel-v2/          # 请求 codemodel
   └── cache-v2/              # 请求 cache 内容

2. 运行 cmake configure+generate
   
3. CMake 检测到查询，写入回复
   build/.cmake/api/v1/reply/
   ├── codemodel-v2-<hash>.json
   ├── cache-v2-<hash>.json
   ├── cmakeFiles-v1-<hash>.json
   ├── toolchains-v1-<hash>.json
   └── index-<hash>.json      # 列出所有回复文件的索引

4. IDE 读取 reply 文件，解析 JSON
```

**查询（query）类型：**

| 查询目录 | 返回内容 |
|---------|---------|
| `codemodel-v2` | 完整 target graph：目录、target、compile groups、link dependencies |
| `cache-v2` | CMakeCache.txt 的所有条目 |
| `cmakeFiles-v1` | 所有参与 configure 的 CMake 文件列表 |
| `toolchains-v1` | 工具链信息（编译器、链接器路径等） |
| `configureLog-v1` | Configure 日志内容 |

**回复（reply）示例（codemodel-v2 片段）：**

```json
{
  "kind": "codemodel",
  "version": { "major": 2, "minor": 7 },
  "paths": {
    "source": "/path/to/project",
    "build": "/path/to/build"
  },
  "configurations": [{
    "name": "Release",
    "directories": [{
      "source": ".",
      "build": ".",
      "targets": [{
        "name": "my_app",
        "type": "EXECUTABLE",
        "dependencies": [{ "id": "my_lib" }],
        "compileGroups": [{
          "includes": [{ "path": "/path/to/include" }],
          "defines": [{ "define": "VERSION=1" }],
          "language": "CXX"
        }]
      }]
    }]
  }]
}
```

> [!tip] File-API 的优势
> - **无状态**：不需要 CMake 进程常驻，IDE 只需读文件
> - **可缓存**：回复文件不随 CMake 版本变化而结构破坏
> - **可扩展**：新增查询类型不影响已有查询
> - **跨版本稳定**：v2 的 schema 保证向后兼容

---

### CMake 4.0+ Build Cache（`cmake_build_cache`）

CMake 4.0 引入了实验性的构建缓存机制，解决**跨构建目录共享编译产物**的问题。

**传统问题：**
```bash
cmake -B build-release -DCMAKE_BUILD_TYPE=Release
cmake --build build-release
cmake -B build-debug -DCMAKE_BUILD_TYPE=Debug
cmake --build build-debug   # 每个 target 全部重新编译！
```
两个构建目录即使编译相同的源文件（如同一个 `my_lib`），也无法共享 `.o` 文件——因为它们在不同的 build tree 中。

**Build Cache 的解决方案：**

```cmake
# CMakeLists.txt 或 preset 中启用
set(CMAKE_BUILD_CACHE_DIR "${CMAKE_SOURCE_DIR}/.cmake_build_cache")
```

```bash
# 首次构建——编译结果写入 cache
cmake -B build-release -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_BUILD_CACHE_DIR=$PWD/.cmake_build_cache
cmake --build build-release

# 第二次构建——从 cache 拉取命中项
cmake -B build-debug -DCMAKE_BUILD_TYPE=Debug \
      -DCMAKE_BUILD_CACHE_DIR=$PWD/.cmake_build_cache
cmake --build build-debug   # 相同源文件的 .o 从 cache 复用！
```

**工作原理：**

1. **构建时存储：** 原生构建工具编译完成后，CMake 计算每个 object file 的内容哈希，将匹配的 `.o` 存入 cache
2. **配置时检索：** configure 阶段，CMake 检查 cache 中是否有匹配的 object file，如果有，在 generate 阶段生成"从 cache 复制"而非"从源码编译"的规则
3. **命中条件：** 源文件内容、编译选项、编译器版本、头文件依赖完全一致

> [!warning] Build Cache 是 CMake 4.0 实验性功能
> API 可能在未来版本中变化。生产环境使用前请查阅最新文档。

---

### `cmake --build` 的并行机制

`cmake --build` 自身不管并行——它把 `-j` 原样传给原生构建工具：

```bash
cmake --build build -j 8
# 等价于:
#   make -j 8            (Makefiles)
#   ninja -j 8           (Ninja)
#   msbuild /m:8         (Visual Studio)
```

**各工具的并行行为：**

| 工具 | 默认并行度 | `-j` 行为 |
|------|-----------|----------|
| **Ninja** | **自动**（CPU 核心数 + 2） | `-j` 覆盖默认值 |
| **Make** | `-j 1`（串行！） | `-j` 设置并行数；`-j$(nproc)` 全并行 |
| **MSBuild** | `-m` 全并行 | `/m:N` 限制最大并行数 |

> [!tip] Ninja 的自动并行
> Ninja 是 CMake 推荐的生成器。它不仅自动检测 CPU 核心数并行构建，还智能管理内存使用（`ninja -l N` 限制负载）。对于大多数场景，`cmake --build build`（不加 `-j`）配合 Ninja 就是最优解。

---

## 2. 代码示例

### 示例 1：用 `--trace` 和 `--debug-output` 观察三阶段

**项目结构：**
```
trace_demo/
├── CMakeLists.txt
└── src/
    ├── CMakeLists.txt
    ├── hello.cpp
    └── hello.h
```

**顶层 `CMakeLists.txt`：**
```cmake
cmake_minimum_required(VERSION 3.24)
project(TraceDemo VERSION 1.0 LANGUAGES CXX)

set(MY_VAR "configured_value")

message(STATUS "Top-level: MY_VAR = ${MY_VAR}")
message(STATUS "Top-level: GENEX test = $<1:hello>")  # 不展开

add_subdirectory(src)
```

**`src/CMakeLists.txt`：**
```cmake
add_library(hello STATIC hello.cpp)
target_include_directories(hello PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

# Generator expression: configure 时只是字符串，generate 时才展开
target_compile_definitions(hello PRIVATE
    BUILD_INFO="$<CONFIG>:$<TARGET_FILE:hello>"
)

message(STATUS "src: hello target created")
message(STATUS "src: compile defs = BUILD_INFO=$<CONFIG>:$<TARGET_FILE:hello>")
```

**`src/hello.cpp`：**
```cpp
#include "hello.h"
const char* hello() { return "Hello from TraceDemo"; }
```

**`src/hello.h`：**
```cpp
#pragma once
const char* hello();
```

**运行命令及预期输出：**

```bash
# === 步骤 1：只用 --trace 观察 CMakeLists.txt 执行流 ===
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      --trace-source=CMakeLists.txt

# 输出示例（截取关键行）：
# /path/to/CMakeLists.txt(1): cmake_minimum_required(VERSION 3.24)
# /path/to/CMakeLists.txt(2): project(TraceDemo VERSION 1.0 LANGUAGES CXX)
# /path/to/CMakeLists.txt(4): set(MY_VAR "configured_value")
# /path/to/CMakeLists.txt(6): message(STATUS "Top-level: MY_VAR = configured_value")
# -- Top-level: MY_VAR = configured_value
# /path/to/CMakeLists.txt(7): message(STATUS "Top-level: GENEX test = $<1:hello>")
# -- Top-level: GENEX test = $<1:hello>   ← 注意：genex 没有展开！
# /path/to/CMakeLists.txt(9): add_subdirectory(src)
# /path/to/src/CMakeLists.txt(1): add_library(hello STATIC ...)
# ...

# === 步骤 2：用 --debug-output 查看 configure 阶段内部状态 ===
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      --debug-output 2>&1 | head -60

# 输出示例：
# -- The CXX compiler identification is GNU 13.2.0
# Called from: [2]     /usr/share/cmake-3.28/Modules/CMakeDetermineCXXCompiler.cmake
# Called from: [1]     CMakeLists.txt
# -- Detecting CXX compiler ABI info
# Called from: [2]     /usr/share/cmake-3.28/Modules/CMakeDetermineCompilerABI.cmake
# ...

# === 步骤 3：用 --trace-expand 可以看到 genex 在 generate 阶段的展开 ===
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      --trace-expand 2>&1 | grep "BUILD_INFO"

# 在生成 build.ninja 时的输出（trace 级别较低，可能不会直接显示 genex 展开）：
# 实际在 build.ninja 中查看：
cat build/build.ninja | grep BUILD_INFO
# -DBUILD_INFO=Release:src/libhello.a   ← genex 已展开！
```

**关键观察：**
1. `--trace-source=CMakeLists.txt` 按行号显示执行流——这**只是 configure 阶段**
2. `--debug-output` 显示每个命令的调用栈——帮助诊断"谁设置了这个变量"
3. `--trace-expand` 在 generate 阶段显示 genex 的展开结果
4. `$<1:hello>` 在 configure 时是**字面字符串**，在 generate 时展开为 `hello`
5. `$<CONFIG>:<TARGET_FILE:hello>` 在 generate 后变成 `Release:src/libhello.a`

---

### 示例 2：检查 CMakeCache.txt 和 CMakeFiles/ 内容

**项目结构：**
```
cache_demo/
├── CMakeLists.txt
└── main.cpp
```

**`CMakeLists.txt`：**
```cmake
cmake_minimum_required(VERSION 3.24)
project(CacheDemo VERSION 1.0 LANGUAGES CXX)

set(MY_STRING "hello world" CACHE STRING "A custom string")
set(MY_BOOL ON CACHE BOOL "A toggle flag")
set(MY_PATH "${CMAKE_CURRENT_SOURCE_DIR}/lib" CACHE PATH "A path")

option(ENABLE_FEATURE "Enable cool feature" ON)

add_executable(cache_demo main.cpp)
target_compile_definitions(cache_demo PRIVATE
    MY_STRING="${MY_STRING}"
)
```

**`main.cpp`：**
```cpp
#include <iostream>
int main() { std::cout << "Hello Cache" << std::endl; return 0; }
```

**运行命令：**

```bash
# === 步骤 1：生成并构建 ===
cmake -B build -G Ninja
cmake --build build

# === 步骤 2：查看 CMakeCache.txt ===
cat build/CMakeCache.txt

# 关键内容：前三行是元信息，后面是条目
# # This is the CMakeCache file.
# # For build in directory: /path/to/cache_demo/build
# # It was generated by CMake: /usr/bin/cmake
# ...
# //A custom string
# MY_STRING:STRING=hello world
#
# //A toggle flag
# MY_BOOL:BOOL=ON
#
# //A path
# MY_PATH:PATH=/path/to/cache_demo/lib
#
# //Enable cool feature
# ENABLE_FEATURE:BOOL=ON
#
# //CXX compiler
# CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++
#
# //Flags used by the CXX compiler during all build types.
# CMAKE_CXX_FLAGS:STRING=
# ...

# === 步骤 3：查看 CMakeFiles/ 关键文件 ===
tree build/CMakeFiles -L 2

# build/CMakeFiles/
# ├── 3.28.0/
# │   ├── CMakeCXXCompiler.cmake
# │   ├── CMakeSystem.cmake
# │   └── CMakeDetermineCompilerABI_CXX.bin
# ├── CMakeConfigureLog.yaml      # CMake 3.26+ 的 configure 日志
# ├── CMakeDirectoryInformation.cmake
# ├── CMakeOutput.log
# ├── CMakeError.log
# ├── CMakeScratch/               # 临时文件
# ├── TargetDirectories.txt
# └── cache_demo.dir/
#     ├── build.make              # Makefile 生成器用
#     ├── depend.make
#     ├── flags.make
#     ├── link.txt
#     ├── compiler_depend.make
#     └── ...

# === 步骤 4：查看 CMakeDirectoryInformation.cmake ===
cat build/CMakeFiles/CMakeDirectoryInformation.cmake

# 输出示例：
# set(CMAKE_RELATIVE_INCLUDE_PATHS ".")
# set(CMAKE_INCLUDE_DIRECTORIES_PROJECT_BUILD "")
# set(CMAKE_INCLUDE_CURRENT_DIR ON)

# === 步骤 5：删除 CMakeCache.txt，重新 configure ===
rm build/CMakeCache.txt
# 注意：CMakeFiles/ 目录还在！
cmake -B build -G Ninja -DMY_STRING="new value"

# 比较新旧 CMakeCache.txt：
# - MY_STRING 现在 = "new value"
# - MY_BOOL 恢复默认 = ON（因为 cache 被清空，重新初始化）
# - ENABLE_FEATURE 回到默认 = ON
# - 但 CMakeFiles/3.28.0/CMakeCXXCompiler.cmake 被复用（编译器检测不变）

# === 步骤 6：查看 cmake_install.cmake ===
cat build/cmake_install.cmake

# 因为没有 install() 规则，内容很简单：
# if(NOT DEFINED CMAKE_INSTALL_PREFIX)
#   set(CMAKE_INSTALL_PREFIX "/usr/local")
# endif()
# ...
# if(NOT CMAKE_INSTALL_LOCAL_ONLY)
#   include("/path/to/build/CMakeFiles/cache_demo.dir/cmake_install.cmake")
# endif()
```

**关键观察：**
1. `CMakeCache.txt` 格式：`//注释\n VARNAME:TYPE=VALUE`——不要手动编辑
2. `CMakeFiles/3.28.0/` 中的编译器检测结果被保留，即使 cache 被删——这是合理的，因为编译器没变
3. `CMakeConfigureLog.yaml`（CMake 3.26+）包含所有 `try_compile` 的详细日志，是调试编译器检测的首选
4. 删除 `CMakeCache.txt` 后，所有 `CACHE` 变量回到默认值，自动检测重新运行

---

### 示例 3：对比单配置（Ninja）和多配置（Ninja Multi-Config）

**项目结构：**
```
config_demo/
├── CMakeLists.txt
└── main.cpp
```

**`CMakeLists.txt`：**
```cmake
cmake_minimum_required(VERSION 3.24)
project(ConfigDemo VERSION 1.0 LANGUAGES CXX)

# 利用 genex 根据配置设置不同定义
add_executable(config_demo main.cpp)
target_compile_definitions(config_demo PRIVATE
    CONFIG_NAME="$<CONFIG>"
    $<$<CONFIG:Debug>:DEBUG_BUILD=1>
    $<$<CONFIG:Release>:NDEBUG>
)
```

**`main.cpp`：**
```cpp
#include <iostream>

int main() {
#ifdef CONFIG_NAME
    std::cout << "Config: " << CONFIG_NAME << std::endl;
#endif
#ifdef DEBUG_BUILD
    std::cout << "Debug build active" << std::endl;
#endif
#ifdef NDEBUG
    std::cout << "Release optimization active" << std::endl;
#endif
    return 0;
}
```

**运行命令：**

```bash
# ============================================================
# 实验 A：单配置 Ninja
# ============================================================

# --- A1: Release 配置 ---
mkdir -p build_single_release
cmake -B build_single_release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build_single_release

# 查看输出目录结构
tree build_single_release -L 1
# build_single_release/
# ├── build.ninja           ← 只有一种配置的构建文件
# ├── config_demo           ← 可执行文件直接在根目录
# ├── CMakeCache.txt
# └── CMakeFiles/

# 查看 build.ninja 中的编译定义（验证 genex 展开）
grep "CONFIG_NAME\|DEBUG_BUILD\|NDEBUG" build_single_release/build.ninja
# 输出：
#   FLAGS = ... -DCONFIG_NAME=Release -DNDEBUG
# 注意：DEBUG_BUILD 不在其中——genex $<$<CONFIG:Debug>:...> 在 Release 配置下被跳过了

./build_single_release/config_demo
# 输出：
# Config: Release
# Release optimization active

# --- A2: 尝试切换到 Debug ---
# 错误做法：只改 --config（单配置生成器忽略此参数！）
cmake --build build_single_release --config Debug
# 实际上还是构建 Release！因为 build.ninja 里的配置已经定了

# 正确做法：重新 configure
cmake -B build_single_release -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build_single_release
./build_single_release/config_demo
# Config: Debug
# Debug build active

# ============================================================
# 实验 B：多配置 Ninja Multi-Config
# ============================================================

cmake -B build_multi -G "Ninja Multi-Config"
# 注意：没有 -DCMAKE_BUILD_TYPE

# 查看输出目录结构
tree build_multi -L 2
# build_multi/
# ├── build-Debug.ninja      ← 每种配置独立的 .ninja 文件
# ├── build-Release.ninja
# ├── build-RelWithDebInfo.ninja
# ├── build-MinSizeRel.ninja
# ├── CMakeCache.txt
# ├── CMakeFiles/
# ├── Debug/                 ← 输出文件按配置分目录
# │   └── config_demo
# └── Release/
#     └── config_demo

# 构建 Debug——不重新 configure
cmake --build build_multi --config Debug
./build_multi/Debug/config_demo
# Config: Debug
# Debug build active

# 构建 Release——同一个 build tree！
cmake --build build_multi --config Release
./build_multi/Release/config_demo
# Config: Release
# Release optimization active

# 验证：build-Debug.ninja 和 build-Release.ninja 中的 genex 不同
grep "CONFIG_NAME" build_multi/build-Debug.ninja
#   FLAGS = ... -DCONFIG_NAME=Debug -DDEBUG_BUILD=1

grep "CONFIG_NAME" build_multi/build-Release.ninja
#   FLAGS = ... -DCONFIG_NAME=Release -DNDEBUG

# ============================================================
# 实验 C：查看 GENEX 在两种生成器中的展开差异
# ============================================================

# 用 --trace-expand 查看单配置 genex 求值
cmake -B build_single_check -G Ninja -DCMAKE_BUILD_TYPE=Release \
      --trace-expand 2>&1 | grep -i "config_demo.*compile"

# 用 --trace-expand 查看多配置 genex 求值（会展开所有配置）
cmake -B build_multi_check -G "Ninja Multi-Config" \
      --trace-expand 2>&1 | grep -i "config_demo.*compile"
```

**关键观察：**
1. 单配置：`build.ninja` 只有一套规则；切换配置必须重新 configure
2. 多配置：`build-<config>.ninja` 各一套规则；切换配置只需指定 `--config`
3. `$<CONFIG>` 在单配置下展开为**一个固定值**（configure 时决定的 `CMAKE_BUILD_TYPE`）
4. `$<CONFIG>` 在多配置下为**每种配置展开一次**，写入对应 `.ninja` 文件
5. 多配置的输出文件天然隔离（`Debug/` vs `Release/`），不同配置的中间文件不会冲突

---

## 3. 练习

### 练习 1：用 `--trace-source` 跟踪 configure 执行流

**目标：** 理解 CMake 按什么顺序处理源文件。

**任务：**
1. 创建以下项目结构：
```
ex1/
├── CMakeLists.txt      # project(), set(MY_VAR), message(), add_subdirectory()
├── lib/
│   └── CMakeLists.txt  # add_library()
└── app/
    └── CMakeLists.txt  # add_executable(), target_link_libraries()
```
2. 运行 `cmake -B build --trace-source=CMakeLists.txt`
3. 从 trace 输出中找出：
   - `project()` 调用在第几步
   - `add_subdirectory()` 导致后续 trace 的行号变为子目录的 `CMakeLists.txt`
   - `add_library()` 和 `add_executable()` 分别在哪个文件被处理
4. 在顶层 `CMakeLists.txt` 中 `set(MY_VAR "before")`，然后在 `add_subdirectory(lib)` 之后 `set(MY_VAR "after")`
   - 在 `lib/CMakeLists.txt` 中 `message(${MY_VAR})`
   - 观察输出是 "before" 还是 "after"——理解 configure 的线性执行顺序

**提示：** 注意 trace 输出的格式：
```
/path/to/file.cmake(LINE): command(args)
```

### 练习 2：删除 CMakeCache.txt 并观察重新 configure 行为

**目标：** 理解 CMakeCache.txt 的角色和删除后果。

**任务：**
1. 创建项目，使用 `find_package` 查找一个常用库（如 `find_package(Threads REQUIRED)`）
2. 首次 configure 并构建：`cmake -B build && cmake --build build`
3. 记录 configure 输出中 `find_package` 的日志（如 "Found Threads: TRUE"）
4. 删除 `CMakeCache.txt`：`rm build/CMakeCache.txt`
5. 重新 configure：注意 `find_package` 的输出**再次出现**
6. 修改 `CMakeCache.txt` 中一个值（如 `CMAKE_BUILD_TYPE` 从空改为 `Debug`）
7. 用 `-DCMAKE_BUILD_TYPE=Release` 重新 configure：观察哪个值生效

**思考题：** 如果只删除 `CMakeCache.txt` 但保留 `CMakeFiles/` 目录，重新 configure 后：
- 已编译的 `.o` 文件会怎样？
- 编译器检测会重新运行吗？
- `find_package` 的结果会改变吗？

### 练习 3：用 CMake File-API 查询构建信息

**目标：** 理解 File-API 的 query/reply 机制。

**任务：**
1. 创建任意 CMake 项目（至少有一个 executable 和一个 library target）
2. 在 configure 之前，手动创建查询目录：
```bash
mkdir -p build/.cmake/api/v1/query/codemodel-v2
mkdir -p build/.cmake/api/v1/query/cache-v2
mkdir -p build/.cmake/api/v1/query/cmakeFiles-v1
```
3. 运行 `cmake -B build`（configure + generate）
4. 查看生成的 reply 文件：
```bash
ls build/.cmake/api/v1/reply/
# 应该看到 index-*.json、codemodel-v2-*.json 等
```
5. 读取 `index-*.json` 找到所有 reply 文件的名称
6. 读取 `codemodel-v2-*.json`：
   - 列出所有 target 的名称和类型（`EXECUTABLE`、`STATIC_LIBRARY` 等）
   - 找到每个 target 的 compileGroups，查看其 `includes` 和 `defines`
   - 找到 target 之间的依赖关系（`dependencies` 数组）
7. 读取 `cache-v2-*.json`：
   - 列出所有 cache 条目的 key、type、value
   - 与 `CMakeCache.txt` 中的内容对比

**扩展（可选）：** 写一个 Python 脚本，读取 `codemodel-v2` reply，生成包含所有 target 及其依赖的 Markdown 表格。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **项目结构：**
> ```cmake
> # ex1/CMakeLists.txt
> cmake_minimum_required(VERSION 3.24)
> project(TraceDemo VERSION 1.0 LANGUAGES CXX)
>
> set(MY_VAR "before")
> add_subdirectory(lib)
> set(MY_VAR "after")
> add_subdirectory(app)
> ```
>
> ```cmake
> # ex1/lib/CMakeLists.txt
> add_library(mylib STATIC mylib.cpp)
> message(STATUS "lib: MY_VAR = ${MY_VAR}")
> ```
>
> ```cmake
> # ex1/app/CMakeLists.txt
> add_executable(myapp main.cpp)
> target_link_libraries(myapp PRIVATE mylib)
> message(STATUS "app: MY_VAR = ${MY_VAR}")
> ```
>
> **运行 trace：**
> ```bash
> cmake -B build --trace-source=CMakeLists.txt
> ```
>
> **分析 trace 输出：**
> 1. `project()` 调用通常在 trace 的前几步（在 `cmake_minimum_required` 之后）
> 2. 遇到 `add_subdirectory(lib)` 时，trace 文件路径切换为 `.../lib/CMakeLists.txt(LINE):`
> 3. `add_library()` 出现在 `lib/CMakeLists.txt` 中；`add_executable()` 出现在 `app/CMakeLists.txt` 中
> 4. `MY_VAR` 在 `lib` 中输出 `before`——因为 `add_subdirectory(lib)` 在 `set(MY_VAR "after")` 之前执行。这证明了 configure 是**线性顺序执行**：子目录 `lib/` 被完全处理完毕后才回到父目录继续执行后续命令。
>
> **输出验证：**
> ```
> -- lib: MY_VAR = before
> -- app: MY_VAR = after
> ```

> [!tip]- 练习 2 参考答案
> **项目（最小化）：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(CacheExperiment VERSION 1.0 LANGUAGES CXX)
>
> find_package(Threads REQUIRED)
> message(STATUS "Threads found: ${Threads_FOUND}")
>
> add_executable(demo main.cpp)
> target_link_libraries(demo PRIVATE Threads::Threads)
> ```
>
> **步骤与观察：**
> ```bash
> # 1. 首次 configure
> cmake -B build
> # 输出: -- Found Threads: TRUE
>
> # 2. 二次 configure（不删缓存）
> cmake -B build
> # find_package 的 "Found Threads: TRUE" 再次出现！
> # 这是因为 FindThreads 每次 configure 都重新搜索
>
> # 3. 删除 CMakeCache.txt
> rm build/CMakeCache.txt
> cmake -B build
> # 所有自动检测重新运行：
> # - 编译器检测（-- The CXX compiler identification is ...）
> # - find_package 重新搜索
> # - CMAKE_BUILD_TYPE 重置为默认值
>
> # 4. 手动修改 CMakeCache.txt
> echo 'CMAKE_BUILD_TYPE:STRING=Debug' >> build/CMakeCache.txt
>
> # 5. 用 -D 覆盖
> cmake -B build -DCMAKE_BUILD_TYPE=Release
> # Release 生效——命令行 -D 优先级最高
> ```
>
> **思考题答案：**
> - **已编译的 `.o` 文件：** 保留不删。`CMakeFiles/` 中的 `.o` 文件与 `CMakeCache.txt` 无关——它们是原生构建工具的产物。删除 `CMakeCache.txt` 只触发重新 configure+generate，不强制重新编译。
> - **编译器检测：** 会重新运行。`CMakeCache.txt` 存储了上次检测结果（如 `CMAKE_CXX_COMPILER_ID`），删除后 CMake 必须重新探测编译器。
> - **`find_package` 结果：** 会改变。`find_package` 的路径搜索结果（如 `ZLIB_INCLUDE_DIR`）存储在 cache 中。删除后重新搜索，如果系统环境变了（如安装了新库版本），结果可能不同。

> [!tip]- 练习 3 参考答案
> **步骤：**
> ```bash
> # 1. 创建项目（任意 CMake 项目，至少一个 executable + 一个 library）
> mkdir -p fileapi-demo/src fileapi-demo/lib
>
> # 2. 创建 query 目录
> mkdir -p build/.cmake/api/v1/query/codemodel-v2
> mkdir -p build/.cmake/api/v1/query/cache-v2
> mkdir -p build/.cmake/api/v1/query/cmakeFiles-v1
>
> # 3. configure + generate
> cmake -B build
>
> # 4. 查看 reply 文件
> ls build/.cmake/api/v1/reply/
> # 输出类似:
> # index-2024-06-10T12-00-00-0000.json
> # codemodel-v2-<hash>.json
> # cache-v2-<hash>.json
> # cmakeFiles-v1-<hash>.json
>
> # 5. 读取 index 找所有 reply
> cat build/.cmake/api/v1/reply/index-*.json | python3 -m json.tool
>
> # 6. 读取 codemodel-v2
> cat build/.cmake/api/v1/reply/codemodel-v2-*.json | python3 -m json.tool | less
> ```
>
> **codemodel-v2 JSON 关键结构：**
> ```json
> {
>   "configurations": [{
>     "name": "Release",
>     "targets": [
>       {
>         "name": "myapp",
>         "type": "EXECUTABLE",
>         "dependencies": [{"id": "mylib"}],
>         "compileGroups": [{
>           "includes": [{"path": "/path/to/include"}],
>           "defines": [{"define": "MY_DEFINE"}],
>           "sources": [{"path": "main.cpp", "compileGroupIndex": 0}]
>         }]
>       },
>       {
>         "name": "mylib",
>         "type": "STATIC_LIBRARY",
>         ...
>       }
>     ]
>   }]
> }
> ```
>
> **cache-v2 JSON 关键结构：**
> ```json
> {
>   "entries": [
>     { "name": "CMAKE_BUILD_TYPE", "type": "STRING", "value": "Release" },
>     { "name": "CMAKE_CXX_COMPILER", "type": "FILEPATH", "value": "/usr/bin/g++" },
>     ...
>   ]
> }
> ```
> 与 `CMakeCache.txt` 对比：cache-v2 JSON 中条目的 `name`、`type`、`value` 与 `CMakeCache.txt` 中 `VARNAME:TYPE=value` 行一一对应。
>
> **对比 `CMakeCache.txt`：** 两者内容一致——File-API 提供的是结构化的 JSON 版本，方便 IDE 和外部工具解析，无需自己解析 `CMakeCache.txt` 的文本格式。
>
> **扩展 Python 脚本示例：**
> ```python
> import json, glob
>
> index = json.load(open(glob.glob("build/.cmake/api/v1/reply/index-*.json")[0]))
> reply_file = index["reply"]["codemodel-v2"]["jsonFile"]
> codemodel = json.load(open(f"build/.cmake/api/v1/reply/{reply_file}"))
>
> for target in codemodel["configurations"][0]["targets"]:
>     print(f"| {target['name']} | {target['type']} | "
>           f"{', '.join(d['id'] for d in target.get('dependencies', []))} |")
> ```
> 输出 Markdown 表格，列出所有 target 的名称、类型和依赖关系。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方文档 — cmake(1)](https://cmake.org/cmake/help/latest/manual/cmake.1.html) — 所有命令行选项的权威参考
- [CMake 官方文档 — cmake-buildsystem(7)](https://cmake.org/cmake/help/latest/manual/cmake-buildsystem.7.html) — configure/generate 阶段内部逻辑
- [CMake 官方文档 — cmake-file-api(7)](https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html) — File-API spec，query/reply 的 JSON schema
- [CMake 官方文档 — cmake-generator-expressions(7)](https://cmake.org/cmake/help/latest/manual/cmake-generator-expressions.7.html) — 所有可用 genex 的完整列表
- [CMake 4.0 Release Notes](https://cmake.org/cmake/help/latest/release/4.0.html) — Build Cache 及其他 4.0 新特性
- 《Professional CMake》 by Craig Scott — 第 6 章 "The Configure and Generate Steps"
- [Kitware CMake Source](https://gitlab.kitware.com/cmake/cmake) — `Source/cmConfigure.cxx`、`Source/cmGlobalGenerator.cxx` 是 configure/generate 的入口

---

## 常见陷阱

- **陷阱 1：认为 `cmake --build` 期间 CMake 在运行。** 构建阶段 CMake 进程已经退出。`cmake --build` 只是包装器，启动原生构建工具后立即返回。编译错误、链接错误都不是 CMake 产生的——它们是编译器/链接器的输出。

- **陷阱 2：单配置生成器下切换 `CMAKE_BUILD_TYPE` 不重新 configure。** `CMAKE_BUILD_TYPE` 在 configure 时被"烧录"进构建文件。如果你 `cmake --build build --config Debug` 但最初 configure 的是 Release，Ninja/Make 仍然构建 Release。正确做法：重新运行 `cmake -B build -DCMAKE_BUILD_TYPE=Debug`。

- **陷阱 3：configure 时尝试用 `if()` 判断 genex。** Generator expressions 只在 generate 阶段求值。下面的代码**永远不会**进入 `if` 分支：
  ```cmake
  if("$<CONFIG>" STREQUAL "Debug")  # 永远为假！genex 未被求值
      message("This never prints")
  endif()
  ```
  正确做法：把条件逻辑放进 genex 内部，如 `$<$<CONFIG:Debug>:debug_lib>`，或使用 `target_sources` + genex。

- **陷阱 4：忘记多配置生成器下 `CMAKE_BUILD_TYPE` 被忽略。** 在 VS/Xcode/Ninja Multi-Config 下设置 `CMAKE_BUILD_TYPE=Debug` 没有任何效果。configure 时 CMake 会静默忽略它（或产生警告）。配置在构建时通过 `--config` 或 IDE 内的配置下拉菜单选择。

- **陷阱 5：手动改 `CMakeCache.txt` 后不重新 configure。** 直接编辑 `CMakeCache.txt` 后运行 `cmake --build`，CMake 可能检测到时间戳变化而自动重新 configure，**覆盖**你的修改。正确方式：`cmake -B build -D<VAR>=<value>` 或使用 `ccmake`/`cmake-gui`。

- **陷阱 6：混淆 CMake 变量和 shell 环境变量。** `-DCMAKE_BUILD_TYPE=Release` 设置的是 CMake 变量，不是环境变量。`export CC=clang` 是设置环境变量（影响编译器检测）。两者的作用域和生命周期完全不同。

- **陷阱 7：缓存生成器表达式结果。** 不要在 `set(... CACHE ...)` 的 value 中放入 genex——cache 变量在 configure 时写入，而 genex 到 generate 时才展开。cache 中存储的是未展开的 `$<...>` 字面量，下次 configure 读回时可能导致错误。
