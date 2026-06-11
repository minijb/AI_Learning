---
title: 静态库、动态库与对象库
updated: 2026-06-10
tags: [cmake, static-library, shared-library, object-library, rpath]
---

# 静态库、动态库与对象库

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 60min
> 前置知识: [[03-targets-and-properties]], [[05-project-and-compiler-detection]]

---

## 1. 概念讲解

### 为什么需要这个？

C/C++ 项目从单文件到多文件再到多目标的过程中，代码复用是核心需求。把几十个 `.cpp` 文件直接编译进每个可执行文件不仅慢，而且浪费磁盘空间。**库**将编译后的目标文件打包，让多个可执行文件共享同一套编译产物。

CMake 提供了四种库类型，每种对应不同的链接和分发策略。理解它们的差异是构建可维护、可分发项目的基石。

### 核心思想

**静态库 (STATIC)** — 编译期嵌入。`.a` (Unix) / `.lib` (Windows) 在链接时被完整拷贝进可执行文件。最终二进制自包含，不需要额外文件，但可执行文件体积大，库更新需要重新链接。

**共享库 (SHARED)** — 运行时加载。`.so` (Linux) / `.dll` (Windows) / `.dylib` (macOS) 在程序启动时（或 `dlopen` 时）由动态链接器加载。多个进程可共享同一份物理内存页，可执行文件小，库可以独立更新，但需要处理运行时查找路径 (RPATH)。

**对象库 (OBJECT)** — 仅编译，不打包。输出 `.o` / `.obj` 文件，不做 `ar`/`link` 归档。用于在多个目标之间共享同一批源文件的编译结果，避免重复编译。对象库本身不产生 `.a` 或 `.so`。

**模块库 (MODULE)** — 插件专用。类似 SHARED 但不自动链接到可执行文件，只能通过 `dlopen`/`LoadLibrary` 动态加载。常用于插件系统。

### add_library() 变体

```cmake
add_library(my_lib STATIC  src/foo.cpp src/bar.cpp)   # 静态库
add_library(my_lib SHARED  src/foo.cpp src/bar.cpp)   # 共享库
add_library(my_lib OBJECT  src/foo.cpp src/bar.cpp)   # 对象库
add_library(my_lib MODULE  src/plugin.cpp)             # 模块库（插件）
```

如果不指定类型，CMake 使用 `BUILD_SHARED_LIBS` 变量的当前值决定：`ON` → SHARED，`OFF` → STATIC。

> [!tip] 用变量控制库类型
> 常见模式是让用户通过 `BUILD_SHARED_LIBS` 选择默认类型，特殊库显式指定类型。这样顶层项目可以统一切换而内部细节不受影响。

### 静态库深入

静态库本质是一个 `.ar` 归档文件（Unix）或 `.lib` 文件（Windows）。链接器从归档中提取被引用的目标文件并嵌入最终可执行文件。

**关键特性：**

- **全量嵌入**：链接器只提取实际引用的符号所在的目标文件，不是整个 `.a`
- **编译期解析**：所有符号在链接时确定地址，无运行时开销
- **无独立更新**：库更新 → 重新链接所有使用它的可执行文件
- **无 ABI 隔离**：库和使用者的编译器版本、标志必须兼容

**Unix 下 `.a` 文件内部结构：**

```
libfoo.a
├── foo.o          # ar 归档的第一个目标文件
├── bar.o          # 第二个
└── __.SYMDEF      # ranlib 生成的符号索引（加速链接器查找）
```

静态库用 `ar` 创建，用 `ranlib` 建立索引。CMake 自动调用这些工具。

**Windows 下 `.lib` 文件：**

Windows 的 `.lib` 有两种语义：
- **静态库** — 目标文件归档（等同于 Unix `.a`），链接时嵌入
- **导入库** — 配合 DLL 使用的存根，包含导出符号的跳转地址，链接时使用但运行时实际调用 DLL

CMake 中 `add_library(foo STATIC ...)` 总是产生第一种。

### 共享库深入

共享库在编译时**不嵌入**可执行文件。可执行文件中只记录"需要 `libfoo.so`"的标记。运行时，动态链接器 (`ld.so` / `dyld` / `ntdll.dll`) 负责找到并加载它。

**关键特性：**

- **共享物理内存**：操作系统将同一 `.so` 的只读段（`.text`）映射到多个进程的同一物理页
- **懒加载**：Linux 默认使用 lazy binding，函数地址在首次调用时才解析（通过 PLT/GOT 机制）
- **ABI 契约**：接口不变时可以独立替换库文件，不需要重新链接使用者
- **符号可见性**：默认所有符号导出，可通过 `-fvisibility=hidden` + `__attribute__((visibility("default")))` 控制

#### PIC (Position Independent Code)

共享库代码必须能加载到任意内存地址。在 x86-64 上，默认的代码生成依赖绝对地址（适合可执行文件的主程序）。共享库需要 **-fPIC** 编译选项生成位置无关代码。

> [!warning] 静态库编译为共享库时的 -fPIC 陷阱
> 如果你用 `add_library(foo STATIC ...)` 编译了一批 `.o` 文件（无 `-fPIC`），然后将同一个源文件用 `add_library(foo_shared SHARED ...)` 再编译一次，CMake 会**重新编译**这些源文件加上 `-fPIC`。但如果通过 OBJECT 库共享编译产物，OBJECT 库必须自己设置 `POSITION_INDEPENDENT_CODE` 属性。

```cmake
# 方式一：让 CMake 自动处理（推荐）
add_library(foo_shared SHARED src/foo.cpp)  # CMake 自动加 -fPIC

# 方式二：显式设置
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
add_library(foo_shared SHARED src/foo.cpp)

# 方式三：按目标设置（最精确）
set_target_properties(foo_shared PROPERTIES POSITION_INDEPENDENT_CODE ON)
```

`CMAKE_POSITION_INDEPENDENT_CODE` 会转化为编译器的 `-fPIC` (GCC/Clang) 或等价标志。

#### 版本化共享库 (SOVERSION)

Linux 共享库有三层版本号：

```
libfoo.so                    → 链接器使用的 symlink（无版本后缀）
libfoo.so.1                  → SO-name symlink → libfoo.so.1.2.3
libfoo.so.1.2.3              → 实际文件
```

- **VERSION** — 完整的 `<major>.<minor>.<patch>`，决定实际文件名
- **SOVERSION** — 仅主版本号 `<major>`，决定 soname (`libfoo.so.1`)
- 运行时链接器查找的是 soname，ABI 兼容的次版本可以透明替换

CMake 配置：

```cmake
set_target_properties(my_shared PROPERTIES
    VERSION    "1.2.3"    # 实际文件: libmy_shared.so.1.2.3
    SOVERSION  "1"        # soname:    libmy_shared.so.1
)
```

> [!tip] SOVERSION 变更意味着 ABI 不兼容
> 主版本号变更 = ABI 破坏。当你删除/修改了公共 API 中的函数签名、类布局、或改变了 `sizeof` 对外暴露的类型时，必须递增 SOVERSION。

### OBJECT 库深入

对象库只做**编译**，不调用 `ar`（归档器）或 linker。产物是裸的目标文件（`.o` / `.obj`）。

**为什么 OBJECT 库存在？**

假设两个可执行文件 `app_a` 和 `app_b` 都需要编译 `common/parser.cpp`。如果用 STATIC 库：

```cmake
add_library(common STATIC common/parser.cpp common/utils.cpp)
target_link_libraries(app_a PRIVATE common)
target_link_libraries(app_b PRIVATE common)
```

这没问题，但 `parser.cpp.o` 只在 `common` 中编译一次，然后 `app_a` 链接时提取它，`app_b` 链接时也提取它——编译是一次，归档是一次，链接是两次。对大多数项目足够好。

但有时你**不想**产生 `.a` 文件，或者你需要同一批 `.o` 文件既用于一个 STATIC 库又用于一个 SHARED 库，而且不想编译两次。OBJECT 库就是干这个的：

```cmake
add_library(common_obj OBJECT common/parser.cpp common/utils.cpp)

# 两个目标共享同一批 .o — 只编译一次
add_library(common_static STATIC $<TARGET_OBJECTS:common_obj>)
add_library(common_shared SHARED  $<TARGET_OBJECTS:common_obj>)
```

`$<TARGET_OBJECTS:common_obj>` 生成器表达式在构建时展开为该 OBJECT 库编译出的所有 `.o` 文件的完整路径列表。

**OBJECT 库的限制：**

- OBJECT 库不链接任何东西。对其调用 `target_link_libraries` 只传递使用要求（include 目录、编译定义等），不传递链接依赖
- OBJECT 库不能直接作为 `target_link_libraries` 的链接参数（CMake 3.12+ 允许但只是传递使用要求）
- 消费者必须用 `$<TARGET_OBJECTS:...>` 将对象文件引入自己的编译

**性能意义：**

| 场景 | 编译次数 | 归档次数 | 链接次数 |
|------|---------|---------|---------|
| STATIC 库被两个 exe 使用 | 1 | 1 | 2 |
| OBJECT 库 + 两个 exe 用 `$<TARGET_OBJECTS:...>` | 1 | 0 | 2 |
| 同一批源文件编两次（一个 .a 一个 .so） | 2 | 1 | 2 |
| OBJECT 库 → .a 和 .so（只编一次） | 1 | 1 | 2 |

OBJECT 库的核心价值是**避免重复编译同一批源文件**（通常是为了同时产出 STATIC 和 SHARED 变体）。

> [!note] OBJECT 库 vs INTERFACE 库
> OBJECT 库有实际编译产物（`.o` 文件）；INTERFACE 库完全没有编译产物，只携带使用要求（头文件路径、编译定义、链接库）。不要把两者混淆。

### MODULE 库深入

MODULE 库编译为可动态加载的共享对象（`.so`/`.dll`），但**不链接到任何可执行文件**。它只能被 `dlopen`/`LoadLibrary` 运行时加载。

```cmake
add_library(my_plugin MODULE src/plugin.cpp)
```

MODULE 库与 SHARED 库的区别：
- MODULE **不会被 `target_link_libraries` 链接**——尝试这样做会报错
- MODULE 通常是一个**独立的编译单元**，完全自包含
- 适合实现插件架构：主程序在运行时遍历插件目录，`dlopen` 每个 `.so`

### Windows DLL 专属细节

#### `__declspec(dllexport)` 和 `__declspec(dllimport)`

Windows DLL 与 Unix `.so` 最大的不同：符号必须**显式导出**才能被外部使用。

```cpp
// 传统方式：每个要导出的符号前加 __declspec(dllexport)
#ifdef BUILDING_MYLIB
  #define MYLIB_API __declspec(dllexport)
#else
  #define MYLIB_API __declspec(dllimport)
#endif

class MYLIB_API Calculator {
public:
    int add(int a, int b);
};
```

构建库时定义 `BUILDING_MYLIB`（用 CMake 的 `target_compile_definitions` 传递 `PRIVATE` 宏），使用者自动获得 `dllimport`。

#### `CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS`

在 CMake 3.4+ 中，你可以跳过手写导出宏：

```cmake
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
```

CMake 自动生成一个 `.def` 文件，列举所有符号并指示链接器全部导出。这对快速原型或内部库很实用，但生产项目通常仍用手动导出以获得更精细的控制。

> [!warning] 导出所有符号的性能代价
> 导出全部符号增加 DLL 体积、符号表大小、链接时间，并泄露实现细节。库的公共 API 应精心设计，内部函数不应暴露。

#### `.def` 文件

`.def` (Module Definition File) 是 MSVC 链接器的传统符号导出方式：

```
LIBRARY mylib
EXPORTS
    add        @1
    subtract   @2
```

在 CMake 中指定：

```cmake
add_library(mylib SHARED src/foo.cpp src/mylib.def)
```

`.def` 文件作为源文件之一加入 `add_library`。

### RPATH — 运行时库查找路径

可执行文件在运行时如何找到它依赖的共享库？

**Unix 查找顺序** (简化)：
1. `LD_LIBRARY_PATH` 环境变量（Linux）/ `DYLD_LIBRARY_PATH`（macOS）
2. 可执行文件中嵌入的 **RPATH** / **RUNPATH**
3. 系统默认路径：`/lib`, `/usr/lib`；由 `/etc/ld.so.conf` 指定
4. `LD_LIBRARY_PATH`（如果使用 RUNPATH，再次检查）

**CMake RPATH 相关变量和属性：**

| 变量/属性 | 作用 |
|-----------|------|
| `CMAKE_INSTALL_RPATH` | 安装后目标中的 RPATH（分号分隔的路径列表） |
| `CMAKE_BUILD_RPATH` | 构建树中目标的 RPATH（CMake 通常自动设为构建输出目录） |
| `CMAKE_INSTALL_RPATH_USE_LINK_PATH` | 为 `ON` 时将链接时使用的库路径追加到安装 RPATH |
| `CMAKE_SKIP_RPATH` | 全局禁用 RPATH 设置 |
| `CMAKE_SKIP_BUILD_RPATH` | 不在构建树中设置 RPATH |
| `CMAKE_BUILD_WITH_INSTALL_RPATH` | 构建树也使用安装 RPATH（不是构建目录） |

**典型配置：**

```cmake
# 安装后，可执行文件在 ../lib 找库
set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib")

# 同时保留链接时找到的路径（主要用于系统库）
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
```

> [!tip] `$ORIGIN` 的含义
> `$ORIGIN` 是动态链接器在运行时解析的特殊变量，指向**可执行文件自身所在的目录**。`$ORIGIN/../lib` 表示"从可执行文件所在目录向上一级，然后进入 `lib` 目录"。这让你的应用可以**完全可重定位**——把整个目录树挪到任何地方都能正常运行。

**macOS 的 `@rpath` / `@loader_path` / `@executable_path`：**

macOS 使用不同的机制。CMake 透明处理，但需要了解：
- `@executable_path` ≈ Unix `$ORIGIN`
- `@loader_path` — 加载者（可能是可执行文件或另一个 dylib）所在目录
- `@rpath` — 编译时嵌入的查找路径列表

```cmake
set(CMAKE_INSTALL_RPATH "@executable_path/../Frameworks")
```

### 输出目录控制

CMake 默认将不同产物放到构建树的对应目录，但可以自定义：

```cmake
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY  ${CMAKE_BINARY_DIR}/lib)   # .a / .lib (STATIC)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY  ${CMAKE_BINARY_DIR}/lib)   # .so / .dylib (SHARED/MODULE)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY  ${CMAKE_BINARY_DIR}/bin)   # .exe / .dll on Windows
```

> [!warning] Windows DLL 进入 RUNTIME 目录
> 在 Windows 上，DLL 被视为"运行时"产物（因为必须与 `.exe` 在同一目录或 PATH 中才能被找到），所以 `.dll` 文件默认进入 `CMAKE_RUNTIME_OUTPUT_DIRECTORY`，而不是 `CMAKE_LIBRARY_OUTPUT_DIRECTORY`。导入库 `.lib` 则进入 `CMAKE_ARCHIVE_OUTPUT_DIRECTORY`。这与 Linux 的行为不同（`.so` 始终进入 `CMAKE_LIBRARY_OUTPUT_DIRECTORY`）。

也可以按目标设置：

```cmake
set_target_properties(mylib PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/static"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/shared"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
```

### 输出命名控制

**基础名称：**

```cmake
set_target_properties(mylib PROPERTIES OUTPUT_NAME "custom_name")
# 产物从 libmylib.a → libcustom_name.a
```

**Debug/Release 后缀：**

```cmake
set(CMAKE_DEBUG_POSTFIX "d")
# Debug 构建输出: libmylibd.a, libmylibd.so
```

也可以按配置设置：

```cmake
set_target_properties(mylib PROPERTIES DEBUG_POSTFIX "_debug")
```

**完整版本化命名（SHARED 专用）：**

```cmake
set_target_properties(mylib PROPERTIES
    VERSION     "2.1.0"
    SOVERSION   "2"
    OUTPUT_NAME "mylib"
)
# 产物:
#   libmylib.so        → symlink
#   libmylib.so.2      → symlink (soname)
#   libmylib.so.2.1.0  → 真实文件
```

### 静态库 vs 共享库：选择指南

| 考量维度 | STATIC | SHARED |
|----------|--------|--------|
| 部署复杂度 | 低——单个可执行文件 | 高——需要随附 `.so`/`.dll` 文件 |
| 可执行文件大小 | 大——库代码嵌入 | 小——只有引用 |
| 启动时间 | 快——无动态加载开销 | 慢——运行时符号解析 |
| 更新灵活性 | 低——需要重新链接 | 高——替换 `.so` 即可（ABI 兼容时） |
| 磁盘占用 | 高——每份可执行文件各自携带 | 低——多程序共享同一物理页 |
| 内存占用 | 高——每进程独立加载 | 低——只读段跨进程共享 |
| 符号冲突风险 | 低——静态链接作用域 | 高——全局符号表可能冲突 |
| 跨编译器兼容 | 差——必须同一编译器 | 中等——C ABI 跨编译器兼容 |
| ODR 违规 | 各副本独立，不冲突 | 符号冲突，未定义行为 |
| LGPL 合规 | 需要提供可重链接的目标文件 | 直接合规 |

**经验法则：**

- **内部项目/单可执行文件** → STATIC，简单省事
- **多个可执行文件共享代码** → SHARED，减少磁盘和内存
- **插件系统** → MODULE
- **需要热更新** → SHARED + `dlopen`
- **分发库给第三方** → 同时提供 STATIC 和 SHARED（让用户选择）
- **嵌入式/无操作系统** → STATIC

---

## 2. 代码示例

### 示例 1：同一库的 STATIC 和 SHARED 版本

**项目结构：**

```
example1/
├── CMakeLists.txt
├── include/
│   └── math/
│       └── math.h
└── src/
    └── math.cpp
```

**`include/math/math.h`：**

```cpp
#ifndef MATH_H
#define MATH_H

#ifdef _WIN32
  #ifdef MATH_BUILD_SHARED
    #define MATH_API __declspec(dllexport)
  #elif defined(MATH_USE_SHARED)
    #define MATH_API __declspec(dllimport)
  #else
    #define MATH_API
  #endif
#else
  #define MATH_API
#endif

class MATH_API Calculator {
public:
    static int add(int a, int b);
    static int multiply(int a, int b);
};

#endif
```

**`src/math.cpp`：**

```cpp
#include "math/math.h"

int Calculator::add(int a, int b) {
    return a + b;
}

int Calculator::multiply(int a, int b) {
    return a * b;
}
```

**`CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(MathExample VERSION 1.0.0 LANGUAGES CXX)

# 选项：默认构建静态库
option(BUILD_SHARED_LIBS "Build shared libraries" OFF)

# 静态库版本
add_library(math_static STATIC
    src/math.cpp
)
target_include_directories(math_static PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# 共享库版本
add_library(math_shared SHARED
    src/math.cpp
)
target_include_directories(math_shared PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_compile_definitions(math_shared PRIVATE MATH_BUILD_SHARED)
set_target_properties(math_shared PROPERTIES
    OUTPUT_NAME "math"
    VERSION      "1.0.0"
    SOVERSION    "1"
)
# 使用者需要 MATH_USE_SHARED 宏（通过传递使用要求）
target_compile_definitions(math_shared INTERFACE MATH_USE_SHARED)

# 输出目录配置
set_target_properties(math_static math_shared PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

# 可执行文件 — 静态链接版本
add_executable(calc_static main.cpp)
target_link_libraries(calc_static PRIVATE math_static)

# 可执行文件 — 动态链接版本
add_executable(calc_shared main.cpp)
target_link_libraries(calc_shared PRIVATE math_shared)

# macOS 需要显式 RPATH 才能在构建树中找到共享库
if(APPLE)
    set_target_properties(calc_shared PROPERTIES
        BUILD_RPATH "${CMAKE_BINARY_DIR}/lib"
    )
endif()
```

**`main.cpp`：**

```cpp
#include "math/math.h"
#include <iostream>

int main() {
    std::cout << "2 + 3 = " << Calculator::add(2, 3) << std::endl;
    std::cout << "4 * 5 = " << Calculator::multiply(4, 5) << std::endl;
    return 0;
}
```

**运行方式：**

```bash
cd example1
cmake -B build
cmake --build build
./build/calc_static      # 静态链接 — 独立运行
./build/calc_shared      # 动态链接 — 需要 .so/.dylib 可被找到
```

**预期输出：**

```
2 + 3 = 5
4 * 5 = 20
```

> [!note] macOS 注意
> 在 macOS 上，如果 `calc_shared` 运行时找不到 `libmath.dylib`，使用 `install_name_tool -add_rpath` 或在 CMake 中设置 `CMAKE_BUILD_RPATH`。

---

### 示例 2：OBJECT 库共享于两个可执行文件

**项目结构：**

```
example2/
├── CMakeLists.txt
├── common/
│   ├── logger.h
│   └── logger.cpp
├── app_a/
│   └── main_a.cpp
└── app_b/
│   └── main_b.cpp
```

**`CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(ObjectLibraryExample VERSION 1.0.0 LANGUAGES CXX)

# 对象库 — 只编译，不归档
add_library(common_obj OBJECT
    common/logger.cpp
)
target_include_directories(common_obj PUBLIC common)

# 如果 common_obj 需要被 SHARED 库使用，设置 PIC
set_target_properties(common_obj PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

# 可执行文件 A — 直接使用 .o 文件链接
add_executable(app_a
    app_a/main_a.cpp
    $<TARGET_OBJECTS:common_obj>
)

# 可执行文件 B — 也使用同一批 .o 文件
add_executable(app_b
    app_b/main_b.cpp
    $<TARGET_OBJECTS:common_obj>
)
```

**`common/logger.h`：**

```cpp
#ifndef LOGGER_H
#define LOGGER_H

#include <string>

void log_message(const std::string& tag, const std::string& msg);

#endif
```

**`common/logger.cpp`：**

```cpp
#include "logger.h"
#include <iostream>
#include <ctime>
#include <iomanip>

void log_message(const std::string& tag, const std::string& msg) {
    auto t = std::time(nullptr);
    auto tm = *std::localtime(&t);
    std::cout << std::put_time(&tm, "[%H:%M:%S] ")
              << "[" << tag << "] " << msg << std::endl;
}
```

**`app_a/main_a.cpp`：**

```cpp
#include "logger.h"

int main() {
    log_message("APP_A", "Starting application A");
    log_message("APP_A", "Doing work...");
    log_message("APP_A", "Done.");
    return 0;
}
```

**`app_b/main_b.cpp`：**

```cpp
#include "logger.h"

int main() {
    log_message("APP_B", "Application B initialized");
    for (int i = 0; i < 3; ++i) {
        log_message("APP_B", "Processing item " + std::to_string(i));
    }
    log_message("APP_B", "Shutdown complete");
    return 0;
}
```

**运行方式：**

```bash
cd example2
cmake -B build
cmake --build build -j
./build/app_a
./build/app_b
```

**预期输出：**

```
# app_a:
[HH:MM:SS] [APP_A] Starting application A
[HH:MM:SS] [APP_A] Doing work...
[HH:MM:SS] [APP_A] Done.

# app_b:
[HH:MM:SS] [APP_B] Application B initialized
[HH:MM:SS] [APP_B] Processing item 0
[HH:MM:SS] [APP_B] Processing item 1
[HH:MM:SS] [APP_B] Processing item 2
[HH:MM:SS] [APP_B] Shutdown complete
```

> [!tip] 验证只编译一次
> 在构建日志中，你会看到 `logger.cpp` 只被编译一次（产生一个 `.o` 文件），然后分别与 `main_a.o` 和 `main_b.o` 链接。如果用 STATIC 库，编译也是一次（归档多一步）。OBJECT 库在此场景中的优势不是性能，而是暴露了对象文件的直接访问权——真正的性能收益出现在同一批 `.o` 需要同时编入 STATIC 和 SHARED 库时。

---

### 示例 3：共享库版本化 + RPATH 配置

**项目结构：**

```
example3/
├── CMakeLists.txt
├── include/
│   └── stringutil/
│       └── stringutil.h
├── src/
│   └── stringutil.cpp
└── app/
    └── main.cpp
```

**`CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(RpathExample VERSION 1.0.0 LANGUAGES CXX)

# ============================================================
# 共享库 — 带版本号
# ============================================================
add_library(stringutil SHARED
    src/stringutil.cpp
)
target_include_directories(stringutil PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
set_target_properties(stringutil PROPERTIES
    VERSION    "2.3.1"
    SOVERSION  "2"
    OUTPUT_NAME "stringutil"
)

# ============================================================
# RPATH 配置
# ============================================================
# 构建时：在构建树中能找到 lib（CMake 自动处理）
# 安装时：使用 $ORIGIN 实现可重定位

set(CMAKE_INSTALL_PREFIX "${CMAKE_BINARY_DIR}/install")

if(APPLE)
    set(CMAKE_INSTALL_RPATH "@executable_path/../lib")
    set(CMAKE_BUILD_RPATH "${CMAKE_BINARY_DIR}")
elseif(WIN32)
    # Windows: DLL 和 exe 放同一目录，一般不需要 RPATH
    set(CMAKE_INSTALL_RPATH "")
else()
    # Linux: $ORIGIN 使应用可重定位
    set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib")
    # 同时保留链接路径（用于系统库）
    set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
endif()

# ============================================================
# 可执行文件
# ============================================================
add_executable(str_app app/main.cpp)
target_link_libraries(str_app PRIVATE stringutil)

# ============================================================
# Debug 后缀
# ============================================================
set(CMAKE_DEBUG_POSTFIX "d")

# ============================================================
# 安装规则
# ============================================================
install(TARGETS stringutil str_app
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)
```

**`include/stringutil/stringutil.h`：**

```cpp
#ifndef STRINGUTIL_H
#define STRINGUTIL_H

#include <string>
#include <vector>
#include <string_view>

namespace stringutil {

std::vector<std::string> split(std::string_view input, char delimiter);

std::string join(const std::vector<std::string>& parts, std::string_view separator);

} // namespace stringutil

#endif
```

**`src/stringutil.cpp`：**

```cpp
#include "stringutil/stringutil.h"
#include <sstream>

namespace stringutil {

std::vector<std::string> split(std::string_view input, char delimiter) {
    std::vector<std::string> result;
    std::string token;
    for (char ch : input) {
        if (ch == delimiter) {
            if (!token.empty()) {
                result.push_back(std::move(token));
                token.clear();
            }
        } else {
            token += ch;
        }
    }
    if (!token.empty()) {
        result.push_back(std::move(token));
    }
    return result;
}

std::string join(const std::vector<std::string>& parts, std::string_view separator) {
    if (parts.empty()) return {};
    std::string result = parts[0];
    for (size_t i = 1; i < parts.size(); ++i) {
        result += separator;
        result += parts[i];
    }
    return result;
}

} // namespace stringutil
```

**`app/main.cpp`：**

```cpp
#include "stringutil/stringutil.h"
#include <iostream>

int main() {
    auto parts = stringutil::split("hello,world,cmake", ',');
    std::cout << "Split result (" << parts.size() << " parts):" << std::endl;
    for (const auto& p : parts) {
        std::cout << "  - " << p << std::endl;
    }

    auto joined = stringutil::join(parts, " | ");
    std::cout << "\nJoined: " << joined << std::endl;

    return 0;
}
```

**运行方式：**

```bash
cd example3

# 构建 Debug 版本（共享库带 "d" 后缀）
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build

# 在构建树中运行（CMake 自动设置了构建 RPATH）
./build/str_app

# 安装
cmake --install build

# 验证安装的 RPATH（Linux）
readelf -d install/bin/str_app | grep -E 'RPATH|RUNPATH'
# 预期输出: $ORIGIN/../lib

# 验证共享库版本号（Linux）
ls -la install/lib/
# 预期: libstringutild.so -> libstringutild.so.2
#       libstringutild.so.2 -> libstringutild.so.2.3.1
#       libstringutild.so.2.3.1

# 验证安装后可运行
./install/bin/str_app
```

**预期输出：**

```
Split result (3 parts):
  - hello
  - world
  - cmake

Joined: hello | world | cmake
```

> [!tip] 验证 RPATH 在工作
> 把安装目录移动到任意位置，直接运行 `str_app`——只要 `lib/` 目录的相对位置不变，程序就能找到 `libstringutil.so`。这就是 `$ORIGIN/../lib` 的威力。

---

## 3. 练习

### 练习 1：用变量切换库类型

**目标：** 创建一个库，通过 CMake 变量 `USE_SHARED` 控制编译为 STATIC 还是 SHARED。同一个 CMakeLists.txt 用 `if()` 分支实现。

**要求：**
- 库名：`configurable`，包含一个函数 `int square(int x)`
- 当 `cmake -DUSE_SHARED=ON` 时生成共享库
- 当 `cmake -DUSE_SHARED=OFF` 时生成静态库
- 共享库版本必须设置 VERSION `1.0.0` 和 SOVERSION `1`
- 使用 `set_target_properties` 设置库的输出名称为 `cfg`

**提示：**

```cmake
option(USE_SHARED "Build as shared library" OFF)

if(USE_SHARED)
    add_library(configurable SHARED src/configurable.cpp)
    # ...共享库专属属性
else()
    add_library(configurable STATIC src/configurable.cpp)
    # ...静态库专属属性
endif()
```

**验证：** 分别用 `USE_SHARED=ON` 和 `USE_SHARED=OFF` 构建两次，用 `file` 命令（Linux/macOS）或查看产物文件名确认类型正确，且共享库带版本号。

---

### 练习 2：OBJECT 库避免重复编译

**目标：** 创建一个 OBJECT 库，包含两个源文件。使用该 OBJECT 库构建一个 STATIC 库和一个 SHARED 库，确保源文件只编译一次。

**要求：**
- OBJECT 库名：`core_obj`，源文件：`core/a.cpp` 和 `core/b.cpp`
- STATIC 库：`core_static`，使用 `$<TARGET_OBJECTS:core_obj>` 构建
- SHARED 库：`core_shared`，也使用 `$<TARGET_OBJECTS:core_obj>` 构建
- 使用 `cmake --build build -j1` 单线程构建（或 `-j1`），观察编译日志确认每个 `.cpp` 只编译一次，而不是两次
- 设置 `POSITION_INDEPENDENT_CODE` 属性使 OBJECT 库的 `.o` 文件同时适用于 STATIC 和 SHARED

**提示：**

```cmake
add_library(core_obj OBJECT core/a.cpp core/b.cpp)
set_target_properties(core_obj PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(core_static STATIC $<TARGET_OBJECTS:core_obj>)
add_library(core_shared SHARED  $<TARGET_OBJECTS:core_obj>)
```

**验证：** 构建日志中每个源文件只出现一次编译命令。产物中有 `libcore_static.a` 和 `libcore_shared.so`（或对应平台后缀）。

---

### 练习 3：配置 RPATH，验证运行时库查找

**目标：** 构建一个共享库和一个可执行文件，配置 RPATH 使安装后的可执行文件能在相对路径找到共享库。验证移除构建树后程序仍可运行。

**要求：**
- 共享库：`greeter`，导出函数 `void greet(const std::string& name)`
- 可执行文件：`hello`
- 安装布局：

```
install/
├── bin/
│   └── hello          # RPATH 设为 $ORIGIN/../lib（Linux）或 @executable_path/../lib（macOS）
└── lib/
    └── libgreeter.so  # VERSION 1.0.0, SOVERSION 1
```

- 安装后将整个 `install/` 目录移动到 `/tmp/test_rpath/` 下，验证 `hello` 仍能运行
- 在 Linux/macOS 上使用 `readelf -d` 或 `otool -l` 验证嵌入的 RPATH 值

**提示：**

```cmake
set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib")
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

install(TARGETS greeter hello
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
)
```

**验证命令（Linux）：**

```bash
# 检查 RPATH
readelf -d install/bin/hello | grep RPATH

# 移动并测试
mv install /tmp/test_rpath
/tmp/test_rpath/bin/hello
# 应正常输出 greet 消息，无 "library not found" 错误
```


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(ConfigurableLib VERSION 1.0 LANGUAGES CXX)
>
> option(USE_SHARED "Build as shared library" OFF)
>
> if(USE_SHARED)
>     add_library(configurable SHARED src/configurable.cpp)
>     set_target_properties(configurable PROPERTIES
>         VERSION    "1.0.0"
>         SOVERSION  "1"
>         OUTPUT_NAME "cfg"
>     )
> else()
>     add_library(configurable STATIC src/configurable.cpp)
>     set_target_properties(configurable PROPERTIES
>         OUTPUT_NAME "cfg"
>     )
> endif()
>
> target_include_directories(configurable PUBLIC
>     $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
> )
> ```
>
> **`include/configurable.h`：**
> ```cpp
> #pragma once
> int square(int x);
> ```
>
> **`src/configurable.cpp`：**
> ```cpp
> #include "configurable.h"
> int square(int x) { return x * x; }
> ```
>
> **验证：**
> ```bash
> # 静态库
> cmake -B build-static -DUSE_SHARED=OFF
> cmake --build build-static
> file build-static/libcfg.a    # 或 .lib on Windows
>
> # 共享库
> cmake -B build-shared -DUSE_SHARED=ON
> cmake --build build-shared
> file build-shared/libcfg.so   # → libcfg.so.1.0.0, symlink: libcfg.so.1 → libcfg.so.1.0.0
> ```

> [!tip]- 练习 2 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(ObjectLibDemo VERSION 1.0 LANGUAGES CXX)
>
> # OBJECT 库：只编译不链接
> add_library(core_obj OBJECT core/a.cpp core/b.cpp)
> set_target_properties(core_obj PROPERTIES
>     POSITION_INDEPENDENT_CODE ON  # 使 .o 同时适用于 STATIC 和 SHARED
> )
>
> # 同一批 .o 用于两种库
> add_library(core_static STATIC $<TARGET_OBJECTS:core_obj>)
> add_library(core_shared SHARED  $<TARGET_OBJECTS:core_obj>)
> ```
>
> **`core/a.cpp`：**
> ```cpp
> #include <iostream>
> void a_func() { std::cout << "a_func()\n"; }
> ```
>
> **`core/b.cpp`：**
> ```cpp
> #include <iostream>
> void b_func() { std::cout << "b_func()\n"; }
> ```
>
> **验证（`-j1` 单线程观察编译日志）：**
> ```bash
> cmake -B build
> cmake --build build -j1
> ```
> 日志中 `a.cpp` 和 `b.cpp` 各出现一次编译命令，而非两次。产物包含 `libcore_static.a` 和 `libcore_shared.so`（或对应平台后缀）。
>
> **关键点：** `POSITION_INDEPENDENT_CODE ON` 至关重要——没有它，OBJECT 库的 `.o` 文件编译为位置相关代码，SHARED 库链接时会报 `recompile with -fPIC` 错误。

> [!tip]- 练习 3 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(RPathDemo VERSION 1.0 LANGUAGES CXX)
>
> add_library(greeter SHARED src/greeter.cpp)
> set_target_properties(greeter PROPERTIES
>     VERSION    "1.0.0"
>     SOVERSION  "1"
> )
> target_include_directories(greeter PUBLIC include)
>
> add_executable(hello src/hello.cpp)
> target_link_libraries(hello PRIVATE greeter)
>
> # RPATH 配置
> set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib")
> set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
>
> install(TARGETS greeter hello
>     RUNTIME DESTINATION bin
>     LIBRARY DESTINATION lib
> )
> ```
>
> **`include/greeter.h`：**
> ```cpp
> #pragma once
> #include <string>
> void greet(const std::string& name);
> ```
>
> **`src/greeter.cpp`：**
> ```cpp
> #include "greeter.h"
> #include <iostream>
> void greet(const std::string& name) {
>     std::cout << "Hello, " << name << "!" << std::endl;
> }
> ```
>
> **`src/hello.cpp`：**
> ```cpp
> #include "greeter.h"
> int main() {
>     greet("World from RPATH demo");
>     return 0;
> }
> ```
>
> **验证：**
> ```bash
> cmake -B build -DCMAKE_INSTALL_PREFIX=install
> cmake --build build
> cmake --install build
>
> # 检查 RPATH
> readelf -d install/bin/hello | grep -E 'RPATH|RUNPATH'
> # 预期输出: 0x... (RUNPATH) Library runpath: [$ORIGIN/../lib]
>
> # 移动并验证可重定位
> mv install /tmp/test_rpath
> /tmp/test_rpath/bin/hello
> # 正常输出 "Hello, World from RPATH demo!"，无 "library not found" 错误
> ```
>
> **macOS 用户用 `@executable_path/../lib` 替代 `$ORIGIN/../lib`，验证用 `otool -l`。**

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方文档: add_library](https://cmake.org/cmake/help/latest/command/add_library.html) — 所有库类型的完整参数列表
- [CMake 官方文档: RPATH handling](https://cmake.org/cmake/help/latest/prop_tgt/INSTALL_RPATH.html) — RPATH 属性的详细说明
- [CMake 官方文档: Object Libraries](https://cmake.org/cmake/help/latest/command/add_library.html#object-libraries) — OBJECT 库的语义和限制
- [Ulrich Drepper: How To Write Shared Libraries](https://akkadia.org/drepper/dsohowto.pdf) — 共享库设计的经典长文，涵盖 ELF、PLT、GOT 等底层细节
- [Microsoft Docs: Exporting from a DLL](https://docs.microsoft.com/en-us/cpp/build/exporting-from-a-dll-using-declspec-dllexport) — `__declspec(dllexport/dllimport)` 官方文档
- [Linux man: ld.so(8)](https://man7.org/linux/man-pages/man8/ld.so.8.html) — 动态链接器的完整行为文档，R（U）PATH 查找顺序

### 关联知识

- [[07-target-link-libraries-and-transitive-deps]] — PUBLIC/PRIVATE/INTERFACE 对库传递的影响
- [[11-install-and-export-targets]] — 库的安装与导出，使库可被 `find_package` 消费
- [[15-toolchain-files-and-cross-compiling]] — 交叉编译中的库类型选择与 PIC
- [[22-real-world-project-patterns]] — 真实项目中 STATIC + SHARED 并行的目录结构

---

## 常见陷阱

### 1. 静态库对象用于共享库时缺少 -fPIC

**症状：** 链接 SHARED 库时出现类似错误：

```
relocation R_X86_64_32 against `.rodata' can not be used when making a shared object;
recompile with -fPIC
```

**原因：** 静态库的 `.o` 文件编译时没有 `-fPIC` 标志（位置相关代码），不能直接用于共享库。

**修复：**

```cmake
# 错误做法 — OBJECT 库没开 PIC，后面的 SHARED 库会链接失败
add_library(common_obj OBJECT src/foo.cpp)
add_library(common_shared SHARED $<TARGET_OBJECTS:common_obj>)  # 链接错误！

# 正确做法
add_library(common_obj OBJECT src/foo.cpp)
set_target_properties(common_obj PROPERTIES POSITION_INDEPENDENT_CODE ON)
add_library(common_shared SHARED $<TARGET_OBJECTS:common_obj>)  # OK
```

**或者，直接用 SHARED 库的源文件列表让 CMake 自动加 `-fPIC`，避免 OBJECT 库的手动 PIC 配置。**

### 2. Windows DLL 符号不可见

**症状：** 链接使用 DLL 的可执行文件时出现 `unresolved external symbol` 链接错误。

**原因：** Windows 上 DLL 的符号默认不导出。Unix 上默认导出全部符号。

**修复（四选一）：**

```cmake
# 方案 A — 全局自动导出（CMake 3.4+，适合快速原型）
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)

# 方案 B — 使用生成器表达式传递宏
target_compile_definitions(mylib PRIVATE MYLIB_EXPORTS)
target_compile_definitions(mylib INTERFACE MYLIB_IMPORTS)
# 配合头文件中的 __declspec(dllexport)/__declspec(dllimport) 条件编译

# 方案 C — .def 文件
add_library(mylib SHARED src/foo.cpp mylib.def)

# 方案 D — MSVC 的 /EXPORT 链接器选项
target_link_options(mylib PRIVATE "/EXPORT:MyFunction")
```

### 3. 运行时找不到共享库

**症状：**

```
# Linux:
./myapp: error while loading shared libraries: libmylib.so: cannot open shared object file

# macOS:
dyld: Library not loaded: libmylib.dylib
  Reason: image not found

# Windows:
The program can't start because mylib.dll is missing from your computer.
```

**原因：** 可执行文件在运行时不知道去哪里找共享库。

**修复策略因平台而异：**

```cmake
# Linux/macOS — 配置安装 RPATH
# 典型可重定位方案：库放在可执行文件旁边的 ../lib
set(CMAKE_INSTALL_RPATH "$ORIGIN/../lib")        # Linux
set(CMAKE_INSTALL_RPATH "@executable_path/../lib") # macOS
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

# 构建树中 CMake 默认自动设置 BUILD_RPATH，
# 但如果你覆盖了 CMAKE_INSTALL_RPATH 且构建时出问题，
# 确保 BUILD_RPATH 仍正确：
if(APPLE)
    set_target_properties(myapp PROPERTIES
        BUILD_RPATH "${CMAKE_BINARY_DIR}"
    )
endif()

# Windows — 最简单：DLL 和 .exe 同目录
set_target_properties(mylib PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
set_target_properties(myapp PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
```

**诊断命令：**

```bash
# Linux — 查看可执行文件需要的共享库和查找路径
readelf -d ./myapp | grep -E 'NEEDED|RPATH|RUNPATH'
ldd ./myapp       # 显示实际加载了哪些库
patchelf --print-rpath ./myapp  # 打印 RPATH

# macOS — 查看动态库依赖和 RPATH
otool -L ./myapp
otool -l ./myapp | grep -A2 LC_RPATH
install_name_tool -add_rpath @executable_path/../lib ./myapp

# Windows — 可以用 Dependency Walker 或 Dependencies
# 或者简单地把 DLL 放 .exe 同目录
```

### 4. 混淆 CMAKE_LIBRARY_OUTPUT_DIRECTORY 和 CMAKE_RUNTIME_OUTPUT_DIRECTORY

**症状：** 在 Windows 上设置 `CMAKE_LIBRARY_OUTPUT_DIRECTORY` 后，DLL 仍然出现在默认目录。

**原因：** Windows 将 DLL 归类为运行时产物（需要与 `.exe` 在一起），输出到 `CMAKE_RUNTIME_OUTPUT_DIRECTORY`。导入库 `.lib` 才进入 `CMAKE_LIBRARY_OUTPUT_DIRECTORY`。

**修复：**

```cmake
# 跨平台一致的输出配置
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")  # .a / .lib (static, import)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")  # .so / .dylib
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")  # .exe / .dll
```

### 5. VERSION 和 SOVERSION 对静态库无效

**症状：** 给 STATIC 库设置 `VERSION` 属性后产物文件名没有任何变化。

**原因：** `VERSION` 和 `SOVERSION` 属性仅对 SHARED 库和可执行文件生效。静态库的文件名固定为 `lib<name>.a`，没有版本化机制。

**修复：** 不需要修复——这不是问题，只是理解 CMake 属性适用范围。如果你需要静态库文件名带版本号，使用 `OUTPUT_NAME`：

```cmake
set_target_properties(mylib PROPERTIES OUTPUT_NAME "mylib-1.2.3")
# 产物: libmylib-1.2.3.a
```

### 6. OBJECT 库链接依赖被忽略

**症状：** 当 OBJECT 库有 `target_link_libraries(obj PRIVATE dep)` 时，使用 `$<TARGET_OBJECTS:obj>` 的目标没有获得 `dep` 的链接依赖。

**原因：** OBJECT 库不参与最终的链接。`target_link_libraries` 对 OBJECT 库的作用仅仅是传递使用要求（include 目录、编译定义），不传递链接依赖。

**修复：** 消费者必须自己链接所需依赖：

```cmake
add_library(common_obj OBJECT src/parser.cpp)
target_link_libraries(common_obj PUBLIC some_dep)  # 只传递使用要求

add_library(common_static STATIC $<TARGET_OBJECTS:common_obj>)
target_link_libraries(common_static PUBLIC some_dep)  # 实际链接依赖在这里设置！
```

### 7. macOS 构建树共享库找不到

**症状：** `cmake --build build` 成功后，执行构建树中的可执行文件报 `dyld: Library not loaded`。

**原因：** macOS 在构建树中不会自动使用 CMake 设置的 RPATH，因为 Xcode 生成器与 Makefile 生成器行为不同。需要显式设置 `BUILD_RPATH` 或使用 `CMAKE_BUILD_RPATH`。

**修复：**

```cmake
# 方法一：全局构建 RPATH
set(CMAKE_BUILD_RPATH "${CMAKE_BINARY_DIR}")

# 方法二：按目标设置
set_target_properties(myapp PROPERTIES
    BUILD_RPATH "${CMAKE_BINARY_DIR}"
    BUILD_WITH_INSTALL_RPATH FALSE
)
```

### 8. 调试版和发布版库混用

**症状：** 运行时崩溃、奇怪的堆损坏、或 ABI 不匹配。

**原因：** Debug 和 Release 版本的标准库布局可能不同（如 MSVC 的 `_ITERATOR_DEBUG_LEVEL`），混用会导致未定义行为。

**修复：**

```cmake
# 使用 CMAKE_DEBUG_POSTFIX 区分 Debug 和 Release 产物
set(CMAKE_DEBUG_POSTFIX "d")
# 产物: libmylib.a (Release) / libmylibd.a (Debug)

# 确保 Debug 可执行文件链接 Debug 库，Release 链接 Release
# CMake 自动处理——只要你通过 target_link_libraries 引用目标名而非文件名
```
