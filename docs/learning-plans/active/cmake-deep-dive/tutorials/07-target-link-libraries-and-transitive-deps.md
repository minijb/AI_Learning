---
title: target_link_libraries 与传递依赖
updated: 2026-06-10
tags: [cmake, linking, dependencies, propagation]
---

# target_link_libraries 与传递依赖

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 60min
> 前置知识: [[06-static-shared-object-libraries]]

---

## 1. 概念讲解

### 为什么需要这个？

假设你有三个 target：`app`（可执行文件）依赖 `libA`（库），而 `libA` 又依赖 `libB`（库）。只写：

```cmake
target_link_libraries(app libA)
target_link_libraries(libA libB)
```

问题来了：`app` 在编译时需要 `libB` 的头文件吗？链接时需要 `libB` 吗？如果 `libA` 的头文件里 `#include` 了 `libB` 的头文件，`app` 编译时就必须能找到 `libB` 的 include 路径——这意味着 `libB` 的编译依赖必须**传递**给 `app`。

CMake 的 `target_link_libraries()` 不只是在链接行上加 `-l` 标志——它精确控制 **Usage Requirements**（使用需求）的传递：哪些头文件路径、哪些宏定义、哪些链接库会沿着依赖链向下传递，以及传递多远。

不理解这个机制，构建系统就会陷入两种失败模式：

- **编译失败**：PRIVATE 用错了，下游 target 拿不到必需的头文件路径
- **过度泄漏**：PUBLIC 用错了，不需要的实现细节泄漏到下游，拖慢编译且破坏封装

### 核心思想

`target_link_libraries()` 的第二个参数——`PUBLIC`、`PRIVATE`、`INTERFACE`——精确控制依赖在依赖图中的传播范围。

这三个关键字本质上是**集合交集模型**：

```
                  编译自身时使用      消费者使用时获得
                   (COMPILE)          (INTERFACE)
PUBLIC      =         ✓                  ✓
PRIVATE     =         ✓                  ✗
INTERFACE   =         ✗                  ✓
```

| 关键字 | 当前 target 编译时需要 | 依赖当前 target 的下游也需要 | 典型场景 |
|--------|----------------------|---------------------------|---------|
| `PUBLIC` | 是 | 是 | 当前 target 的头文件暴露了依赖的类型/函数 |
| `PRIVATE` | 是 | 否 | 依赖仅在 `.cpp` 实现文件中使用 |
| `INTERFACE` | 否 | 是 | header-only 库对下游提出编译要求 |

> [!tip] 心智模型
> 把每个 CMake target 想象成一个有两个端口的盒子：
> - **IN 端口**：它自己编译时需要的所有东西（头文件、宏定义、链接库）
> - **OUT 端口**：使用它的下游 target 需要继承的东西
>
> `PUBLIC` 同时连接 IN 和 OUT，`PRIVATE` 只连 IN，`INTERFACE` 只连 OUT。

### 传递传播规则

当 A 链接 B 时，B 的 Usage Requirements 会根据链接关键字向 A 传播。传播规则如下表：

**A `target_link_libraries(A PUBLIC B)`**：

| B 上的属性 | 传播到 A 的什么属性 |
|-----------|-------------------|
| B 的 `INTERFACE_*` | A 的 `INTERFACE_*`（继续向下游传播） |
| B 自身的库文件 | A 的 `INTERFACE_LINK_LIBRARIES` |
| B 的 `PRIVATE` 依赖 | **不传播** |

**A `target_link_libraries(A PRIVATE B)`**：

| B 上的属性 | 传播到 A 的什么属性 |
|-----------|-------------------|
| B 的 `INTERFACE_*` | A 的 **PRIVATE** 属性（到此为止，不继续传播） |
| B 自身的库文件 | A 的 `LINK_LIBRARIES`（PRIVATE） |
| B 的 `PRIVATE` 依赖 | **不传播** |

**A `target_link_libraries(A INTERFACE B)`**：

| B 上的属性 | 传播到 A 的什么属性 |
|-----------|-------------------|
| B 的 `INTERFACE_*` | A 的 `INTERFACE_*`（继续向下游传播） |
| A 自身不使用 B | A 编译时不链接 B，但 A 的下游会继承 B 的接口需求 |

> [!important] 关键洞察
> **PRIVATE 是一个防火墙**：所有上游的 INTERFACE 需求到达 PRIVATE 链接后，被吸收进当前 target 的 PRIVATE 需求中，不再向下游传播。这就是"实现细节不泄漏"的机制。

### 三层传递案例图解

假设依赖链：`app → libA → libB`，且 `libB` 有一个 PUBLIC 头文件路径 `/inc/libB`：

```
场景 1: target_link_libraries(libA PUBLIC libB)
─────────────────────────────────────────────────
libB 的 INTERFACE_INCLUDE_DIRECTORIES = /inc/libB
↓ (PUBLIC 链接：进入 libA 的 INTERFACE)
libA 的 INTERFACE_INCLUDE_DIRECTORIES = /inc/libB
↓ (app 链接 libA，无论用什么关键字，app 都会继承 libA 的 INTERFACE)
app 获得 /inc/libB ✓

场景 2: target_link_libraries(libA PRIVATE libB)
─────────────────────────────────────────────────
libB 的 INTERFACE_INCLUDE_DIRECTORIES = /inc/libB
↓ (PRIVATE 链接：进入 libA 的 PRIVATE)
libA 的 PRIVATE_INCLUDE_DIRECTORIES = /inc/libB
↓ (PRIVATE 不进入 libA 的 INTERFACE，app 看不到)
app 不会获得 /inc/libB ✗
```

### 核心接口属性

CMake 用以下 `INTERFACE_*` target 属性承载 Usage Requirements：

| 属性 | 用途 | 命令设置方式 |
|------|------|------------|
| `INTERFACE_LINK_LIBRARIES` | 下游需要链接的库列表 | `target_link_libraries(... PUBLIC ...)` |
| `INTERFACE_INCLUDE_DIRECTORIES` | 下游需要添加的头文件搜索路径 | `target_include_directories(... PUBLIC ...)` |
| `INTERFACE_COMPILE_DEFINITIONS` | 下游需要定义的预处理器宏 | `target_compile_definitions(... PUBLIC ...)` |
| `INTERFACE_COMPILE_OPTIONS` | 下游需要的编译选项 | `target_compile_options(... PUBLIC ...)` |
| `INTERFACE_COMPILE_FEATURES` | 下游需要的 C++ 标准特性 | `target_compile_features(... PUBLIC ...)` |
| `INTERFACE_SOURCES` | 下游编译时需要的源文件 | `target_sources(... PUBLIC ...)`（较少用） |

这些属性构成了 CMake 依赖传播的完整语义。`target_link_libraries()` 是其中最核心的，因为它不仅传播链接库列表，还作为载体触发其他 INTERFACE 属性的传播。

### 依赖图解析

CMake 在配置阶段构建完整的依赖图（Dependency Graph），它是有向图：

1. **节点**：每个 CMake target
2. **边**：每次 `target_link_libraries(A B)` 调用创建一条从 A 到 B 的有向边
3. **属性传播**：属性沿边从被依赖方（B）传播到依赖方（A），方向与边的方向相反

CMake 的依赖解析是**传递闭包**——A 通过 B 依赖 C，则 A 也间接依赖 C。解析完成后，每个 target 的最终编译/链接参数是其**直接需求和所有间接需求**的合并结果。

```
app ──PUBLIC──▶ libA ──PRIVATE──▶ libB ──PUBLIC──▶ libC
                                     │
                                     └── PUBLIC include dirs of libC
                                         进入 libB 的 PRIVATE
                                         但不再传给 libA 和 app
```

### 编译时 vs 链接时需求

一个依赖可能需要出现在编译阶段、链接阶段，或两者都需要：

- **编译时需要**：下游 target 的 `.cpp` 文件中 `#include` 了该依赖的头文件 → 需要 `INTERFACE_INCLUDE_DIRECTORIES`
- **链接时需要**：下游 target 调用了该依赖库中的函数 → 需要将 `.lib`/`.a`/`.so` 传给链接器
- **两者都需要**（最常见）：公用库头文件 + 调用其函数

CMake 通过 `target_link_libraries()` 一次性处理两者——库文件既出现在编译器的 include path 解析中（如果该 target 设置了 `INTERFACE_INCLUDE_DIRECTORIES`），也出现在链接器的库列表中。

> [!warning] Header-only 库
> 对于纯头文件库，创建 `INTERFACE` 库：`add_library(my_header_lib INTERFACE)`。然后只用 `target_link_libraries(consumer INTERFACE my_header_lib)`——没有 `.lib` 文件需要链接，只是传递 include 路径等接口需求。

---

## 2. 代码示例

### 示例 1: 三层依赖链——PUBLIC/PRIVATE/INTERFACE 传播

这是一个完整的可运行示例，演示 PUBLIC、PRIVATE、INTERFACE 三种链接方式在依赖链上的不同传播行为。

**项目结构：**

```
ex1-three-layer/
├── CMakeLists.txt
├── app/
│   └── main.cpp
├── libA/
│   ├── CMakeLists.txt
│   ├── include/libA/
│   │   └── libA.h
│   └── src/
│       └── libA.cpp
└── libB/
    ├── CMakeLists.txt
    ├── include/libB/
    │   └── libB.h
    └── src/
        └── libB.cpp
```

**顶层 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(ThreeLayerDeps VERSION 1.0 LANGUAGES CXX)

add_subdirectory(libB)
add_subdirectory(libA)
add_subdirectory(app)
```

**`libB/CMakeLists.txt`：**

```cmake
add_library(libB STATIC)
target_sources(libB PRIVATE src/libB.cpp)
target_include_directories(libB
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
```

**`libB/include/libB/libB.h`：**

```cpp
#pragma once

namespace libB {
    int compute(int x);
}
```

**`libB/src/libB.cpp`：**

```cpp
#include "libB/libB.h"

namespace libB {
    int compute(int x) {
        return x * 3;
    }
}
```

**`libA/CMakeLists.txt`：**

```cmake
add_library(libA STATIC)
target_sources(libA PRIVATE src/libA.cpp)
target_include_directories(libA
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
# libB 被 libA 的 PUBLIC 头文件使用 → PUBLIC 链接
target_link_libraries(libA PUBLIC libB)
```

**`libA/include/libA/libA.h`：**

```cpp
#pragma once
#include "libB/libB.h"   // 暴露了 libB 的类型 → 必须 PUBLIC

namespace libA {
    int process(int x);  // 返回 libB::compute(x) + 1
}
```

**`libA/src/libA.cpp`：**

```cpp
#include "libA/libA.h"

namespace libA {
    int process(int x) {
        return libB::compute(x) + 1;
    }
}
```

**`app/CMakeLists.txt`：**

```cmake
add_executable(app)
target_sources(app PRIVATE main.cpp)
# app 使用了 libA 的 PUBLIC API，其中暴露了 libB 的头文件
# 因为 libA 用 PUBLIC 链接了 libB，所以 app 自动获得 libB 的 include 路径
target_link_libraries(app PRIVATE libA)
```

**`app/main.cpp`：**

```cpp
#include "libA/libA.h"
#include <iostream>

int main() {
    int result = libA::process(5);
    // Expected: libB::compute(5) = 15; process = 16
    std::cout << "result = " << result << "\n";
    return (result == 16) ? 0 : 1;
}
```

**运行方式：**

```bash
cd ex1-three-layer
cmake -B build
cmake --build build
./build/app/app    # 或 build\app\Debug\app.exe 在 Windows 上
```

**预期输出：**

```
result = 16
```

**传播验证——改变一个关键字看效果：**

将 `libA/CMakeLists.txt` 中的 `PUBLIC libB` 改为 `PRIVATE libB`：

```cmake
target_link_libraries(libA PRIVATE libB)
```

重构后会**编译失败**——`app/main.cpp` 间接 include 了 `libB/libB.h`（通过 `libA/libA.h`），但 `libB` 的 include 路径没有传播到 `app`。这是因为 PRIVATE 拦截了 `INTERFACE_INCLUDE_DIRECTORIES` 的传播。

> [!tip] 传播流向总结
> - `libA PUBLIC libB` → `libB` 的 INTERFACE 需求进入 `libA` 的 INTERFACE → `app` 可见 ✓
> - `libA PRIVATE libB` → `libB` 的 INTERFACE 需求被锁在 `libA` 的 PRIVATE → `app` 不可见 ✗
> - `libA INTERFACE libB` → `libA` 自身不用 `libB`，但其下游继承 `libB` 的 INTERFACE 需求

---

### 示例 2: `$<LINK_ONLY:...>` 生成器表达式

`$<LINK_ONLY:lib>` 用于描述一个"头文件公开、但链接私密"的依赖。典型场景：你的库 A 公开了一个抽象接口（纯虚类），但实际的实现库 B 只在链接时才需要——下游不依赖 B 的头文件。

**项目结构：**

```
ex2-link-only/
├── CMakeLists.txt
├── app/
│   └── main.cpp
├── libA/
│   ├── CMakeLists.txt
│   ├── include/libA/
│   │   └── libA.h
│   └── src/
│       └── libA.cpp
└── libB/
    ├── CMakeLists.txt
    ├── include/libB/
    │   └── libB.h
    └── src/
        └── libB.cpp
```

**顶层 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(LinkOnlyDemo VERSION 1.0 LANGUAGES CXX)

add_subdirectory(libB)
add_subdirectory(libA)
add_subdirectory(app)
```

**`libB/CMakeLists.txt`：**

```cmake
add_library(libB STATIC)
target_sources(libB PRIVATE src/libB.cpp)
target_include_directories(libB
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
```

**`libB/include/libB/libB.h`：**

```cpp
#pragma once
#include <string>

namespace libB {
    std::string heavy_impl(const std::string& input);
}
```

**`libB/src/libB.cpp`：**

```cpp
#include "libB/libB.h"
#include <algorithm>

namespace libB {
    std::string heavy_impl(const std::string& input) {
        std::string result = input;
        std::reverse(result.begin(), result.end());
        return result;
    }
}
```

**`libA/CMakeLists.txt`：**

```cmake
add_library(libA STATIC)
target_sources(libA PRIVATE src/libA.cpp)
target_include_directories(libA
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
# LINK_ONLY: libA 的 PUBLIC 头文件不暴露 libB 的任何类型
# libB 只在 libA 的实现文件(.cpp)中使用
# 但是！下游 app 链接 libA 时必须同时链接 libB，否则会有未定义符号
# 所以用 LINK_ONLY：编译时不传播 libB 的 include 路径，但链接时加上 libB
target_link_libraries(libA
    PUBLIC
        $<LINK_ONLY:libB>
)
```

**`libA/include/libA/libA.h`：**

```cpp
#pragma once
#include <string>

// 注意：不 include libB 的任何头文件！
// libB 是完全隐藏的实现细节

namespace libA {
    std::string transform(const std::string& input);
}
```

**`libA/src/libA.cpp`：**

```cpp
#include "libA/libA.h"
#include "libB/libB.h"   // 只在 .cpp 中使用，外部不可见

namespace libA {
    std::string transform(const std::string& input) {
        return libB::heavy_impl(input);
    }
}
```

**`app/CMakeLists.txt`：**

```cmake
add_executable(app)
target_sources(app PRIVATE main.cpp)
# app 只需要知道 libA 的接口
# $<LINK_ONLY:libB> 保证了 app 链接时获得 libB，但编译时不需要 libB 的头文件
target_link_libraries(app PRIVATE libA)
```

**`app/main.cpp`：**

```cpp
#include "libA/libA.h"
// 不需要 include libB —— 它被完全隐藏了！
#include <iostream>

int main() {
    std::string result = libA::transform("hello");
    // libB::heavy_impl reverses → "olleh"
    std::cout << "result = " << result << "\n";
    return (result == "olleh") ? 0 : 1;
}
```

**运行方式：**

```bash
cd ex2-link-only
cmake -B build
cmake --build build
./build/app/app
```

**预期输出：**

```
result = olleh
```

> [!important] `$<LINK_ONLY:lib>` 的语义
> - 对**当前 target**（`libA`）的 PRIVATE 编译需求：正常使用 `libB`（include + link）
> - 对**下游 target**（`app`）的 INTERFACE 传递：只传递 `INTERFACE_LINK_LIBRARIES`，**不传递** `INTERFACE_INCLUDE_DIRECTORIES`
> - 这就实现了"头文件边界在 `libA`，链接边界延伸到 `app`"

**等效的旧写法（不推荐，但有助于理解）：**

```cmake
target_link_libraries(libA PRIVATE libB)
# 然后手动暴露链接需求给下游：
set_target_properties(libA PROPERTIES
    INTERFACE_LINK_LIBRARIES libB
)
```

`$<LINK_ONLY:lib>` 是这一模式的简洁表达。

---

### 示例 3: WHOLE_ARCHIVE 强制符号导出——静态插件注册模式

静态库的一个经典陷阱：如果可执行文件没有直接引用静态库中的任何符号，链接器会**丢弃整个静态库**。这对于使用"自注册"模式的插件系统是致命的——插件通过全局构造函数自我注册，但没有任何显式调用指向这些构造函数。

**WHOLE_ARCHIVE** 强制链接器包含静态库中的**所有**目标文件，无论是否有符号被引用。

**项目结构：**

```
ex3-whole-archive/
├── CMakeLists.txt
├── app/
│   └── main.cpp
├── plugin_registry/
│   ├── CMakeLists.txt
│   ├── include/plugin_registry/
│   │   └── registry.h
│   └── src/
│       └── registry.cpp
├── plugin_alpha/
│   ├── CMakeLists.txt
│   ├── include/plugin_alpha/
│   │   └── alpha.h
│   └── src/
│       └── alpha.cpp
└── plugin_beta/
    ├── CMakeLists.txt
    ├── include/plugin_beta/
    │   └── beta.h
    └── src/
        └── beta.cpp
```

**顶层 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(WholeArchiveDemo VERSION 1.0 LANGUAGES CXX)

add_subdirectory(plugin_registry)
add_subdirectory(plugin_alpha)
add_subdirectory(plugin_beta)
add_subdirectory(app)
```

**`plugin_registry/CMakeLists.txt`：**

```cmake
add_library(plugin_registry STATIC)
target_sources(plugin_registry PRIVATE src/registry.cpp)
target_include_directories(plugin_registry
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
```

**`plugin_registry/include/plugin_registry/registry.h`：**

```cpp
#pragma once
#include <string>
#include <vector>
#include <functional>
#include <iostream>

// 插件接口：每个插件提供一个名称和一个执行函数
struct Plugin {
    std::string name;
    std::function<void()> execute;
};

// 全局注册表（单例）
class Registry {
public:
    static Registry& instance() {
        static Registry reg;
        return reg;
    }

    void register_plugin(Plugin p) {
        plugins_.push_back(std::move(p));
    }

    void list_all() const {
        std::cout << "Registered plugins (" << plugins_.size() << "):\n";
        for (const auto& p : plugins_) {
            std::cout << "  - " << p.name << "\n";
        }
    }

    void run_all() const {
        for (const auto& p : plugins_) {
            std::cout << "Running " << p.name << "...\n";
            p.execute();
        }
    }

private:
    Registry() = default;
    std::vector<Plugin> plugins_;
};

// 自动注册辅助宏
#define REGISTER_PLUGIN(PluginName, PluginFunc)                          \
    namespace {                                                          \
        struct AutoRegister_##PluginName {                               \
            AutoRegister_##PluginName() {                                \
                Registry::instance().register_plugin(                    \
                    Plugin{#PluginName, PluginFunc});                    \
            }                                                            \
        };                                                               \
        static AutoRegister_##PluginName auto_register_##PluginName;     \
    }
```

**`plugin_registry/src/registry.cpp`：**

```cpp
#include "plugin_registry/registry.h"
// Registry 的实现都在头文件中（header-only 风格），此文件可能为空或包含非模板实现
```

**`plugin_alpha/CMakeLists.txt`：**

```cmake
add_library(plugin_alpha STATIC)
target_sources(plugin_alpha PRIVATE src/alpha.cpp)
target_include_directories(plugin_alpha
    PRIVATE
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
target_link_libraries(plugin_alpha PUBLIC plugin_registry)
```

**`plugin_alpha/include/plugin_alpha/alpha.h`：**

```cpp
#pragma once
// 插件 alpha 的声明（如果有公共接口的话）
// 此示例中插件是完全内部的
```

**`plugin_alpha/src/alpha.cpp`：**

```cpp
#include "plugin_registry/registry.h"

static void alpha_func() {
    std::cout << "  Alpha: Hello from plugin Alpha!\n";
}

// 通过全局构造函数自动注册
// 如果链接器丢弃了 plugin_alpha，这个构造函数永远不会运行
REGISTER_PLUGIN(AlphaPlugin, alpha_func);
```

**`plugin_beta/CMakeLists.txt`：**

```cmake
add_library(plugin_beta STATIC)
target_sources(plugin_beta PRIVATE src/beta.cpp)
target_include_directories(plugin_beta
    PRIVATE
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
target_link_libraries(plugin_beta PUBLIC plugin_registry)
```

**`plugin_beta/src/beta.cpp`：**

```cpp
#include "plugin_registry/registry.h"

static void beta_func() {
    std::cout << "  Beta: Hello from plugin Beta!\n";
}

REGISTER_PLUGIN(BetaPlugin, beta_func);
```

**`app/CMakeLists.txt`：**

```cmake
add_executable(app)
target_sources(app PRIVATE main.cpp)

# 关键：使用 WHOLE_ARCHIVE 强制链接插件静态库的所有 .obj 文件
# 否则链接器看到 app 没有直接引用 plugin_alpha 或 plugin_beta 的符号，
# 会丢弃整个 .a 文件，全局构造函数不会运行，插件不会注册

# 方案 A：使用生成器表达式（CMake 3.24+，推荐）
set(WHOLE_ARCHIVE_EXPR
    "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_alpha>"
    "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_beta>"
)

target_link_libraries(app PRIVATE
    plugin_registry
    ${WHOLE_ARCHIVE_EXPR}
)

# 方案 B：在支持该特性的链接器上使用 --whole-archive 标志
# target_link_options(app PRIVATE
#     "LINKER:--whole-archive"
#     "$<TARGET_FILE:plugin_alpha>"
#     "$<TARGET_FILE:plugin_beta>"
#     "LINKER:--no-whole-archive"
# )
# 注意：方案 B 更底层但可移植性差，优先使用方案 A
```

**`app/main.cpp`：**

```cpp
#include "plugin_registry/registry.h"

int main() {
    auto& reg = Registry::instance();
    reg.list_all();
    reg.run_all();

    // 验证：应该看到 2 个已注册插件
    // 如果没有 WHOLE_ARCHIVE，插件数量为 0
    return 0;
}
```

**运行方式：**

```bash
cd ex3-whole-archive
cmake -B build
cmake --build build
./build/app/app
```

**预期输出（使用 WHOLE_ARCHIVE 时）：**

```
Registered plugins (2):
  - AlphaPlugin
  - BetaPlugin
Running AlphaPlugin...
  Alpha: Hello from plugin Alpha!
Running BetaPlugin...
  Beta: Hello from plugin Beta!
```

**去掉 WHOLE_ARCHIVE 后的对比输出：**

```
Registered plugins (0):
```

> [!warning] WHOLE_ARCHIVE 的生成器表达式需要 CMake 3.24+
> `$<LINK_LIBRARY:WHOLE_ARCHIVE,lib>` 是 CMake 3.24 引入的跨平台写法。在更早版本中，需要手动使用 `target_link_options` 配合链接器特定标志（Linux/macOS 用 `--whole-archive`，MSVC 用 `/WHOLEARCHIVE`）。

> [!important] 什么时候必须使用 WHOLE_ARCHIVE
> 1. **静态库中的全局构造函数自注册**：如本示例的插件注册
> 2. **静态库中定义了 `[[gnu::constructor]]` 或类似属性**
> 3. **Google Test 的 `--gtest_filter` 自动发现测试**：Google Test 通过静态全局对象注册测试用例
> 4. **LLVM/Clang 的 Pass 注册**：LLVM Pass 通过静态注册表自我注册
> 5. **任何"代码即配置"而非"数据即配置"的静态初始化模式**

---

## 3. 练习

### 练习 1: 四层依赖图验证传播

**目标**：创建一个 4 个 target 的依赖链，在每个层级验证 include 和 link 的传播情况。

**要求**：

1. 创建 target：`layer0` → `layer1` → `layer2` → `layer3`，其中 `layer3` 是最底层库
2. `layer3` 提供一个函数 `int get_value()` 和一个 PUBLIC 头文件
3. 每一层链接时混合使用 PUBLIC、PRIVATE、INTERFACE
4. 在 `layer0`（可执行文件）中尝试 `#include` 每一层的头文件，**不要手动添加任何 `target_include_directories`**（只靠传递）
5. 通过编译成功/失败来验证哪些层的头文件可达
6. 对于不可达的层级，解释为什么被阻断了

**设计提示**：

- 让 `layer3` 用 PUBLIC 暴露自己
- 让 `layer2` 用 PRIVATE 链接 `layer3`，观察 `layer3` 的头文件是否能传到 `layer0`
- 让 `layer1` 用 PUBLIC 链接 `layer2`
- 让 `layer0` 用 PRIVATE 链接 `layer1`
- 预期结果：只有 `layer1` 和 `layer3` 中 PUB 传播的部分可达（但被 PRIVATE 防火墙截断的部分不可达）

**验证清单**：

- [ ] `layer3` 的函数能否在 `layer0` 中调用？
- [ ] 将某个 PRIVATE 改为 PUBLIC 后，之前不可达的头文件变为可达
- [ ] 使用 `cmake --build build --verbose` 观察实际的编译和链接命令

---

### 练习 2: 修复错误使用 PRIVATE 的构建

**背景**：Bob 写了一个库 `networking`，它内部使用 `ssl_lib` 来加密通信。Bob 认为 SSL 是内部实现细节，所以用了 PRIVATE 链接。但 `networking` 的公共头文件中有一个函数签名返回了 `ssl_lib` 中定义的类型。

**给定错误场景**：

```cpp
// networking/include/networking/connection.h
#pragma once
#include "ssl_lib/certificate.h"   // 暴露了 ssl_lib 的类型！

class Connection {
public:
    ssl_lib::Certificate get_peer_certificate() const;
    // ...
};
```

```cmake
# networking/CMakeLists.txt (有问题的版本)
target_link_libraries(networking PRIVATE ssl_lib)
```

下游 `app` 包含了 `networking/connection.h`，编译失败，提示找不到 `ssl_lib/certificate.h`。

**任务**：

1. 复现这个错误——创建一个完整的最小项目来模拟这个场景
2. 解释为什么 Bob 的 PRIVATE 用法是错误的
3. 修复构建（将 PRIVATE 改为 PUBLIC），验证编译通过
4. **进阶**：如果 Bob 想保持 PRIVATE（隐藏实现细节），应该如何修改 `connection.h` 来避免暴露 `ssl_lib` 的类型？（提示：Pimpl idiom、前向声明、不透明指针）

---

### 练习 3: 实现 WHOLE_ARCHIVE 插件注册表

**目标**：从零实现练习 3 的完整模式，并扩展到支持插件元数据。

**要求**：

1. 创建一个 `plugin_core` 库，提供：
   - `PluginInfo` 结构体：`name`、`version`、`author` 字段
   - `PluginRegistry` 单例：`register_plugin()`、`list_plugins()`、`get_plugin(name)`
   - `REGISTER_PLUGIN(name, ver, author, func)` 自动注册宏

2. 创建三个插件静态库：`plugin_json`、`plugin_xml`、`plugin_csv`，各自自注册到 registry

3. 创建一个 `app_cli` 可执行文件：
   - 列出所有已注册插件及其元数据
   - 接受到命令行参数选择要运行的插件
   - 验证所有插件都被正确注册（非空）

4. 使用 `$<LINK_LIBRARY:WHOLE_ARCHIVE,...>` 确保所有插件都被链接

5. **挑战**：如果想让用户在构建时选择性地启用/禁用插件（CMake option），如何调整 `target_link_libraries` 调用？写出对应的 CMake 代码。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **项目结构与依赖设计：**
> ```cmake
> # layer3 用 PUBLIC 暴露自己 → 下游自动获得其 include
> # layer2 用 PRIVATE 链接 layer3 → 下游拿不到 layer3 的 include
> # layer1 用 PUBLIC 链接 layer2 → layer2 的 INTERFACE 继续传播
> # layer0 用 PRIVATE 链接 layer1 → layer1 的 INTERFACE 到达但停止
> ```
>
> **预期验证结果：**
>
> | 层级 | 头文件可达？（layer0 中 `#include`） | 原因 |
> |------|:---:|------|
> | `layer1` 的 PUBLIC 头文件 | ✓ 可达 | layer1→layer0 自己的 PUBLIC 头文件通过 INTERFACE 传播 |
> | `layer2` 的 PUBLIC 头文件 | ✓ 可达 | layer1 用 PUBLIC 链接 layer2，layer2 的 INTERFACE 打包进 layer1 的 INTERFACE，继续传给 layer0 |
> | `layer3` 的 PUBLIC 头文件 | ✗ 不可达 | layer2 用 PRIVATE 链接 layer3——PRIVATE 是防火墙，layer3 的 INTERFACE 进入 layer2 的 PRIVATE，不再传播 |
>
> **如果将 layer2→layer3 的 PRIVATE 改为 PUBLIC：** layer3 的头文件立刻变为可达，证明了 PRIVATE 的阻断效果。
>
> **`CMakeLists.txt` 骨架：**
> ```cmake
> add_library(layer3 STATIC layer3.cpp)
> target_include_directories(layer3 PUBLIC include)
>
> add_library(layer2 STATIC layer2.cpp)
> target_include_directories(layer2 PUBLIC include)
> target_link_libraries(layer2 PRIVATE layer3)  # 防火墙
>
> add_library(layer1 STATIC layer1.cpp)
> target_include_directories(layer1 PUBLIC include)
> target_link_libraries(layer1 PUBLIC layer2)    # 透传
>
> add_executable(layer0 main.cpp)
> target_link_libraries(layer0 PRIVATE layer1)   # 终点
> ```
>
> **分析：** layer0 的 `main.cpp` 尝试 `#include "layer3/layer3.h"` 会编译失败，因为 layer2 的 PRIVATE 链接阻断了 layer3 的 `INTERFACE_INCLUDE_DIRECTORIES` 传播。这证明了 "PRIVATE 是传递防火墙"。

> [!tip]- 练习 2 参考答案
> **1. 复现错误的最小项目：**
> ```cmake
> # ssl_lib/CMakeLists.txt
> add_library(ssl_lib STATIC ssl.cpp)
> target_include_directories(ssl_lib PUBLIC include)
>
> # networking/CMakeLists.txt — 错误版本
> add_library(networking STATIC connection.cpp)
> target_include_directories(networking PUBLIC include)
> target_link_libraries(networking PRIVATE ssl_lib)  # 错误！
> ```
>
> **2. 为什么 Bob 的 PRIVATE 是错的：** `connection.h` 中 `#include "ssl_lib/certificate.h"` 且公开 API 返回 `ssl_lib::Certificate`，这意味着任何包含 `connection.h` 的下游代码都需要看到 `ssl_lib` 的头文件。但 PRIVATE 阻止了 `ssl_lib` 的 `INTERFACE_INCLUDE_DIRECTORIES` 传播到下游——下游编译时找不到 `ssl_lib/certificate.h`。
>
> **3. 修复（PUBLIC）：**
> ```cmake
> target_link_libraries(networking PUBLIC ssl_lib)
> ```
>
> **4. 进阶：保持 PRIVATE 的设计改进（Pimpl idiom）：**
> ```cpp
> // connection.h — 不暴露 ssl_lib 类型
> #pragma once
> #include <memory>
>
> class Connection {
> public:
>     class Impl;  // 前向声明
>     std::string get_peer_certificate() const;  // 返回 string，不返回 ssl_lib::Certificate
> private:
>     std::unique_ptr<Impl> pimpl_;
> };
> ```
>
> ```cpp
> // connection.cpp — 实现文件中使用 ssl_lib
> #include "connection.h"
> #include "ssl_lib/certificate.h"
>
> class Connection::Impl {
>     ssl_lib::Certificate cert_;
> };
>
> std::string Connection::get_peer_certificate() const {
>     return pimpl_->cert_.to_string();  // 内部转换
> }
> ```
> 这样 `ssl_lib` 只出现在 `.cpp` 中，PRIVATE 链接就完全正确了。

> [!tip]- 练习 3 参考答案
> **核心骨架：**
> ```cmake
> # plugin_core
> add_library(plugin_core STATIC plugin_core.cpp)
> target_include_directories(plugin_core PUBLIC include)
>
> # 三个插件
> add_library(plugin_json STATIC plugin_json.cpp)
> target_link_libraries(plugin_json PUBLIC plugin_core)
> add_library(plugin_xml STATIC plugin_xml.cpp)
> target_link_libraries(plugin_xml PUBLIC plugin_core)
> add_library(plugin_csv STATIC plugin_csv.cpp)
> target_link_libraries(plugin_csv PUBLIC plugin_core)
>
> # app_cli — 必须用 WHOLE_ARCHIVE 否则链接器丢弃未直接引用的插件
> add_executable(app_cli main.cpp)
> target_link_libraries(app_cli PRIVATE
>     plugin_core
>     "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_json>"
>     "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_xml>"
>     "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_csv>"
> )
> ```
>
> **`plugin_core/include/plugin_core/plugin.h`：**
> ```cpp
> #pragma once
> #include <string>
> #include <vector>
> #include <memory>
> #include <iostream>
>
> struct PluginInfo {
>     std::string name;
>     std::string version;
>     std::string author;
>     void (*func)();
> };
>
> class PluginRegistry {
> public:
>     static PluginRegistry& instance() {
>         static PluginRegistry reg;
>         return reg;
>     }
>     void register_plugin(PluginInfo info) {
>         plugins_.push_back(std::move(info));
>     }
>     void list_plugins() const {
>         for (auto& p : plugins_)
>             std::cout << p.name << " v" << p.version << " by " << p.author << "\n";
>     }
>     const PluginInfo* get_plugin(const std::string& name) const {
>         for (auto& p : plugins_)
>             if (p.name == name) return &p;
>         return nullptr;
>     }
> private:
>     std::vector<PluginInfo> plugins_;
> };
>
> #define REGISTER_PLUGIN(name, ver, author, func) \
>     static struct _AutoReg_##name { \
>         _AutoReg_##name() { \
>             PluginRegistry::instance().register_plugin({#name, ver, author, func}); \
>         } \
>     } _auto_##name;
> ```
>
> **插件示例（`plugin_json.cpp`）：**
> ```cpp
> #include "plugin_core/plugin.h"
> #include <iostream>
> void json_func() { std::cout << "Running JSON plugin\n"; }
> REGISTER_PLUGIN(json, "1.0", "Alice", json_func)
> ```
>
> **`main.cpp`：**
> ```cpp
> #include "plugin_core/plugin.h"
> #include <iostream>
> int main(int argc, char* argv[]) {
>     auto& reg = PluginRegistry::instance();
>     reg.list_plugins();
>     if (argc > 1) {
>         auto* p = reg.get_plugin(argv[1]);
>         if (p) p->func();
>         else std::cerr << "Plugin not found: " << argv[1] << "\n";
>     }
>     return 0;
> }
> ```
>
> **挑战：条件启用插件：**
> ```cmake
> option(ENABLE_PLUGIN_JSON "Build JSON plugin" ON)
> option(ENABLE_PLUGIN_XML  "Build XML plugin"  ON)
> option(ENABLE_PLUGIN_CSV  "Build CSV plugin"  ON)
>
> # 构建条件插件列表
> set(WHOLE_LIBS "")
> if(ENABLE_PLUGIN_JSON)
>     list(APPEND WHOLE_LIBS "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_json>")
> endif()
> if(ENABLE_PLUGIN_XML)
>     list(APPEND WHOLE_LIBS "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_xml>")
> endif()
> if(ENABLE_PLUGIN_CSV)
>     list(APPEND WHOLE_LIBS "$<LINK_LIBRARY:WHOLE_ARCHIVE,plugin_csv>")
> endif()
>
> target_link_libraries(app_cli PRIVATE plugin_core ${WHOLE_LIBS})
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

### `link_libraries()`——为什么几乎永远不该用

`link_libraries()` 是一个**目录级命令**——它影响当前目录及子目录中**之后定义的所有 target**。这是 CMake 2.x 时代的遗留 API：

```cmake
# 危险：会污染整个目录作用域
link_libraries(foo bar)
add_executable(my_app main.cpp)  # my_app 自动链接 foo 和 bar
add_library(my_lib src.cpp)      # my_lib 也自动链接 foo 和 bar
```

**为什么避免**：
- 隐式行为，难以追踪依赖关系
- 作用域泄漏到子目录
- 不能指定 PUBLIC/PRIVATE/INTERFACE
- 与 Modern CMake 的 target-based 理念完全相悖

**始终使用 `target_link_libraries()` 替代**。

### `target_link_directories()`——它的位置

`target_link_directories()` 添加链接器搜索路径（等价于 `-L` 标志）。在 Modern CMake 中**很少需要**直接使用它，因为：

1. 链接到一个 CMake target 时，CMake 自动使用库文件的完整路径（不依赖 `-L` 搜索）
2. 只有链接纯文件路径（如 `${CMAKE_SOURCE_DIR}/libs/libfoo.a`）时才需要 `-L` 路径
3. 更好的做法是使用 `IMPORTED` target 或设置 target 的 `LOCATION` 属性

**需要它的典型场景**：

```cmake
# 链接一个不在 CMake 管理下的外部库文件
target_link_directories(my_app PRIVATE ${CMAKE_SOURCE_DIR}/external/lib)
target_link_libraries(my_app PRIVATE foo)  # 在 external/lib 中找到 libfoo.a
```

> [!tip] 首选 target 属性
> 如果你的外部库可以指定完整路径，直接写路径更好：
> ```cmake
> target_link_libraries(my_app PRIVATE ${CMAKE_SOURCE_DIR}/external/lib/libfoo.a)
> ```

### 与 `find_package` 导入 target 的配合

`find_package()` 通常创建 IMPORTED target，这些 target 已经预设了完整的 `INTERFACE_*` 属性。你只需像对待普通 target 一样链接它们：

```cmake
find_package(Boost REQUIRED COMPONENTS filesystem system)
# Boost::filesystem 和 Boost::system 是 IMPORTED target
# 它们的 INTERFACE_INCLUDE_DIRECTORIES 和 INTERFACE_LINK_LIBRARIES 已预设
target_link_libraries(my_app PRIVATE Boost::filesystem Boost::system)
```

`Boost::filesystem` 被标记为 PRIVATE，意味着 `my_app` 的下游不会自动继承 Boost 的 include 路径——这通常是正确的，除非 `my_app` 的头文件暴露了 Boost 类型。

### `debug` / `optimized` 关键字（遗留）

在 CMake 3.x 之前，根据构建配置选择不同库的写法：

```cmake
# 遗留写法（不推荐）
target_link_libraries(my_app
    debug libfoo_debug
    optimized libfoo
)
```

现代替代方案是使用生成器表达式：

```cmake
# Modern CMake 写法
target_link_libraries(my_app PRIVATE
    $<$<CONFIG:Debug>:libfoo_debug>
    $<$<NOT:$<CONFIG:Debug>>:libfoo>
)
```

或更简洁的：

```cmake
target_link_libraries(my_app PRIVATE
    $<IF:$<CONFIG:Debug>,libfoo_debug,libfoo>
)
```

生成器表达式更灵活——可以表达更复杂的条件，且在整个 CMake 中语法统一。`debug`/`optimized` 关键字仅适用于 `target_link_libraries()`，而生成器表达式适用于所有支持生成器表达式的命令。

### 循环依赖与解决方案

当 A 依赖 B 且 B 也依赖 A 时，形成循环：

```
libA ←→ libB
```

**CMake 行为**：
- CMake 3.x 允许创建循环依赖（不会报错）
- 但链接顺序取决于链接器，可能导致未定义符号
- 静态库间的循环依赖尤其危险——链接器可能只解析一次符号

**解决方案**：

1. **提取公共接口**（推荐）：将 A 和 B 共享的类型/接口提取到第三个库 `libCommon` 中
   ```
   libA → libCommon ← libB
   ```

2. **使用 INTERFACE 打破循环**：如果 A 只使用 B 的接口（不调用实现），将 B 声明为 A 的 INTERFACE 依赖
   ```cmake
   target_link_libraries(libA INTERFACE libB)
   target_link_libraries(libB PRIVATE libA)
   ```

3. **使用对象库**：将共享的 `.cpp` 文件编译为对象库，两个 target 各自链接对象文件
   ```cmake
   add_library(shared_obj OBJECT common.cpp)
   target_link_libraries(libA PRIVATE shared_obj)
   target_link_libraries(libB PRIVATE shared_obj)
   ```

4. **链接器分组**（Linux/macOS）：使用 `--start-group` / `--end-group` 让链接器多次扫描
   ```cmake
   target_link_options(my_app PRIVATE
       "LINKER:--start-group"
   )
   target_link_libraries(my_app PRIVATE libA libB)
   target_link_options(my_app PRIVATE
       "LINKER:--end-group"
   )
   ```

> [!warning] 循环依赖通常是设计问题
> 出现循环依赖通常意味着模块边界划分有问题。优先考虑方案 1（提取公共接口），而不是用链接器技巧硬解。

### 深入研究 INTERFACE 属性

可以使用 `get_target_property()` 或 `set_target_properties()` 直接检查/修改 INTERFACE 属性。调试传递依赖时非常有用：

```cmake
# 检查 libA 向消费者暴露了什么
get_target_property(IFACE_INCLUDES libA INTERFACE_INCLUDE_DIRECTORIES)
get_target_property(IFACE_LINKS libA INTERFACE_LINK_LIBRARIES)
get_target_property(IFACE_DEFS libA INTERFACE_COMPILE_DEFINITIONS)

message(STATUS "libA INTERFACE_INCLUDE_DIRECTORIES: ${IFACE_INCLUDES}")
message(STATUS "libA INTERFACE_LINK_LIBRARIES: ${IFACE_LINKS}")
message(STATUS "libA INTERFACE_COMPILE_DEFINITIONS: ${IFACE_DEFS}")
```

**手动设置 INTERFACE 属性**（header-only 库的典型模式）：

```cmake
add_library(my_header_lib INTERFACE)
target_include_directories(my_header_lib INTERFACE include/)
target_compile_definitions(my_header_lib INTERFACE USE_FANCY_MODE=1)
# 下游自动获得 include/ 路径和 USE_FANCY_MODE 宏
```

---

## 常见陷阱

### 陷阱 1: 用 PRIVATE 但下游需要依赖的头文件

```cmake
# libA 的头文件 #include 了 libB 的类型
target_link_libraries(libA PRIVATE libB)  # 错误！

# app 包含了 libA 的头文件 → 编译失败：找不到 libB 的类型
target_link_libraries(app PRIVATE libA)   # app 得不到 libB 的 include 路径
```

**为什么错**：`libA` 在 PUBLIC 头文件中暴露了 `libB` 的类型，但用 PRIVATE 阻止了 `libB` 的传播。下游 `app` 编译 `libA` 的头文件时需要 `libB` 的 include 路径。

**修复**：将 `libB` 改为 PUBLIC 链接。

**更好的修复**：重构 `libA` 的头文件，不暴露 `libB` 的类型（使用 Pimpl、前向声明、或抽象接口）。

### 陷阱 2: 用 PUBLIC 泄漏实现细节

```cmake
# libB 只在 libA 的 .cpp 中使用
target_link_libraries(libA PUBLIC libB)  # 不必要地泄漏

# 所有下游 target 都会获得 libB 的 include 路径
# → 增加编译时间，破坏封装，下游可能意外依赖 libB
```

**修复**：改用 PRIVATE。

**经验法则**：
- 如果下游不需要 `#include` 你的依赖的头文件 → PRIVATE
- 如果你的 PUBLIC 头文件 `#include` 了依赖的头文件 → PUBLIC
- 如果你不确定 → 从 PRIVATE 开始，需要时再升级为 PUBLIC（PRIVATE → PUBLIC 是编译失败，容易发现；反过来是静默泄漏，难排查）

### 陷阱 3: 忘记 `INTERFACE` 库也需要链接

```cmake
add_library(header_only INTERFACE)
target_include_directories(header_only INTERFACE include/)
target_link_libraries(header_only INTERFACE Boost::headers)
#                                         ^^^^^^^^^ 不要忘记！
# INTERFACE 库的依赖也要用 INTERFACE 关键字传播
```

即使 `header_only` 本身不编译任何源文件，它也必须将 `Boost::headers` 传播给下游。

### 陷阱 4: 静态库 + WHOLE_ARCHIVE 配合全局构造函数

这是 C++ 构建中最隐蔽的 bug 之一：

```cpp
// my_plugin.cpp
static AutoRegister my_plugin("my_plugin");  // 期望运行时自动注册
```

```cmake
add_library(my_plugin STATIC my_plugin.cpp)
target_link_libraries(app PRIVATE my_plugin)  # 链接器可能丢弃整个库！
```

**症状**：程序运行正常但插件没注册，没有任何编译或链接错误。

**修复**：

```cmake
target_link_libraries(app PRIVATE
    "$<LINK_LIBRARY:WHOLE_ARCHIVE,my_plugin>"
)
```

### 陷阱 5: 循环依赖静默成功但运行时失败

CMake 不会阻止循环依赖，但不同链接器的行为不同：

- **GNU ld**：默认单次扫描，A 中引用 B 的符号可能无法解析
- **Apple ld64**：默认两次扫描，某些循环可以工作
- **MSVC link**：类似单次扫描

这导致同样的代码在某些平台上能链接成功，在其他平台上失败。

**最佳实践**：消除循环依赖。构建工具不该被用来弥补设计问题。

### 陷阱 6: `link_libraries()` 的隐式污染

```cmake
# 顶层 CMakeLists.txt
link_libraries(global_lib)     # 影响之后所有 target

add_subdirectory(libA)
# libA 被隐式链接了 global_lib —— 难以追踪

add_subdirectory(libB)
# libB 也被隐式链接了 global_lib
```

在大型项目中，这种作用域泄漏会让依赖关系完全不可追踪。**永远使用 `target_link_libraries()`**。

### 陷阱 7: 混淆 INTERFACE 链接的语义

```cmake
add_library(libA INTERFACE)    # header-only 库
target_link_libraries(libA INTERFACE libB)  # 正确：传播 libB 给下游

add_library(libC STATIC ...)
target_link_libraries(libC INTERFACE libB)  # 注意！libC 本身编译时不需要 libB
# libC 的 .cpp 文件中不能使用 libB，只能通过 libC 的头文件暴露 libB 的类型
```

INTERFACE 链接意味着当前 target 自身不依赖该库，只是将依赖"转发"给消费者。如果 `libC` 的实现文件中需要调用 `libB` 的函数，应该同时添加一个 PRIVATE 链接：

```cmake
target_link_libraries(libC
    PUBLIC libB     # libC 自身需要 + 消费者需要
)
```

或分开写：

```cmake
target_link_libraries(libC
    PRIVATE libB    # libC 自身 .cpp 中需要
    INTERFACE libB  # 消费者通过 libC 的头文件也需要
)
# 等价于 PUBLIC libB
```
