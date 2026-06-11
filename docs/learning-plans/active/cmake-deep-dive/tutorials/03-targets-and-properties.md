---
title: "Target 与属性系统"
updated: 2026-06-10
tags: [cmake, target, properties, modern-cmake]
---

# Target 与属性系统

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 60min
> 前置知识: [[02-cmakelists-structure-and-commands]]

---

## 1. 概念讲解

### 为什么需要 Target？

在传统构建系统（如手写 Makefile）中，你直接指定每个文件的编译命令和链接命令。这种方式直观但脆弱：当项目增长到几十个源文件、十几个库时，"给每个目标重复相同的编译选项" 会迅速变成维护地狱。

CMake 的答案是 **Target**——一个自描述的构建产物抽象。Target 封装了三件事：

1. **它是什么**（类型：可执行文件、静态库、动态库……）
2. **它由哪些源文件构成**
3. **它需要什么才能构建**（头文件路径、编译定义、链接库、编译选项……）

关键洞察：Target 不仅描述"我怎么被构建"，还描述"使用我的人需要什么"。当你用 `target_link_libraries(consumer PRIVATE mylib)` 时，`mylib` 的 **使用需求**（usage requirements）会自动传播给 `consumer`。这就是 Modern CMake 的核心思想——**依赖即声明，构建即推导**。

> [!tip] Old CMake vs Modern CMake
> Old CMake 思维：`include_directories(path)`、`add_definitions(-DFOO)` ——全局或目录级命令，"洒"选项。
> Modern CMake 思维：`target_include_directories(tgt PRIVATE path)`、`target_compile_definitions(tgt PUBLIC FOO)` ——每个 Target 精确声明自己的需求，依赖方自动继承。

### Target 类型一览

CMake 定义了以下 Target 类型（通过 `add_library()` 或 `add_executable()` 创建）：

| 类型 | 创建方式 | 含义 |
|------|---------|------|
| Executable | `add_executable(name ...)` | 可执行文件 |
| Static Library | `add_library(name STATIC ...)` | 静态库（`.a`/`.lib`） |
| Shared Library | `add_library(name SHARED ...)` | 动态库（`.so`/`.dylib`/`.dll`） |
| Module Library | `add_library(name MODULE ...)` | 运行时加载的插件（不能直接链接） |
| Object Library | `add_library(name OBJECT ...)` | 编译但不归档——`.o` 文件集合 |
| Interface Library | `add_library(name INTERFACE)` | 无实际构建产物，纯使用需求容器 |
| Imported Library | `add_library(name IMPORTED ...)` | 外部预构建库的映射 |
| Alias Library | `add_library(name ALIAS target)` | 另一个 Target 的别名 |
| Custom Target | `add_custom_target(name ...)` | 自定义命令目标（无构建产物） |

本教程重点讲解 Executable、Static、Shared、Interface、Imported 和 Alias ——它们覆盖了日常 90% 的场景。

### 属性系统：三种作用域

CMake 的属性系统分为三个层级，形成严格的优先级链：

```
Target Properties（目标属性）
    ↓ 覆盖
Directory Properties（目录属性）
    ↓ 覆盖
Global Properties（全局属性）
```

- **Global Properties**：影响整个 CMake 进程。通过 `set_property(GLOBAL ...)` 设置，`get_property(... GLOBAL ...)` 读取。例如 `GLOBAL_DEPENDS_DEBUG_MODE`。
- **Directory Properties**：影响当前 `CMakeLists.txt` 及其子目录（除非被子目录覆盖）。通过 `set_directory_properties()` 或 `set_property(DIRECTORY ...)` 设置。例如 `CMAKE_CXX_STANDARD` 在目录级设置时影响该目录及子目录下所有 Target（除非 Target 自己覆盖）。
- **Target Properties**：影响单个 Target。通过 `set_target_properties()` 或 `target_*()` 系列命令设置。**这是 Modern CMake 的主力**。

> [!important] 属性继承与作用域不同
> 属性的"覆盖"链是关于**同一个属性名在不同层级取值时优先级**。而 Target 之间的**传递性传播**（PUBLIC/PRIVATE/INTERFACE）是另一套独立机制。两者不要混淆。

### 关键 Target 属性

| 属性 | 类型 | 含义 |
|------|------|------|
| `INCLUDE_DIRECTORIES` | `list<string>` | 头文件搜索路径（`-I`） |
| `COMPILE_DEFINITIONS` | `list<string>` | 预处理器宏（`-D`） |
| `COMPILE_OPTIONS` | `list<string>` | 编译器选项（`-Wall`, `-O2` 等） |
| `LINK_LIBRARIES` | `list<string>` | 链接依赖 |
| `LINK_OPTIONS` | `list<string>` | 链接器选项（`-Wl,xxx`, `-rpath` 等） |
| `LINK_DIRECTORIES` | `list<string>` | 库搜索路径（`-L`） |
| `SOURCES` | `list<string>` | 源文件列表 |
| `TYPE` | `string` | Target 类型（只读） |
| `NAME` | `string` | Target 的逻辑名称 |
| `OUTPUT_NAME` | `string` | 输出文件的名称（不同于逻辑名称） |
| `CXX_STANDARD` | `string` | C++ 标准版本 |
| `POSITION_INDEPENDENT_CODE` | `bool` | 是否编译为位置无关代码（`-fPIC`） |

每个属性都有对应的 `target_*()` 命令来设置。例如：

- `target_include_directories(...)` 操作 `INCLUDE_DIRECTORIES` 和 `INTERFACE_INCLUDE_DIRECTORIES`
- `target_compile_definitions(...)` 操作 `COMPILE_DEFINITIONS` 和 `INTERFACE_COMPILE_DEFINITIONS`
- `target_compile_options(...)` 操作 `COMPILE_OPTIONS` 和 `INTERFACE_COMPILE_OPTIONS`
- `target_link_libraries(...)` 操作 `LINK_LIBRARIES` 和 `INTERFACE_LINK_LIBRARIES`
- `target_link_options(...)` 操作 `LINK_OPTIONS` 和 `INTERFACE_LINK_OPTIONS`

注意到规律了吗？每个属性都有两个变体：**自身版本**和 **`INTERFACE_` 前缀版本**。这引出了下一节的核心概念。

---

## 2. PUBLIC / PRIVATE / INTERFACE —— 传递性三合一

这是理解 Modern CMake 最关键的一节。三个关键字控制属性如何传播：

```
PUBLIC    → 自己用，也让消费者用
PRIVATE   → 只有自己用，消费者看不到
INTERFACE → 自己不用，但消费者用
```

### 用头文件搜索路径来理解

假设库 `mathlib` 需要 `Eigen` 的头文件来编译自己的 `.cpp`，同时 `mathlib` 的公开头文件也 `#include <Eigen/Core>`——这意味着使用 `mathlib` 的消费者也需要 Eigen 头文件路径。

```
target_include_directories(mathlib
    PUBLIC
        ${EIGEN_INCLUDE_DIR}    # mathlib 自己需要 + 消费者需要
    PRIVATE
        ${MATHLIB_INTERNAL_DIR} # 只有 mathlib.cpp 需要
)
```

传播结果：

- `mathlib` 的 `INCLUDE_DIRECTORIES`：`${EIGEN_INCLUDE_DIR}` + `${MATHLIB_INTERNAL_DIR}`
- `mathlib` 的 `INTERFACE_INCLUDE_DIRECTORIES`：`${EIGEN_INCLUDE_DIR}`
- 当 `target_link_libraries(consumer PRIVATE mathlib)` 时，`consumer` 继承 `mathlib` 的 `INTERFACE_INCLUDE_DIRECTORIES`，即 `${EIGEN_INCLUDE_DIR}`。它看不到 `${MATHLIB_INTERNAL_DIR}`。

### 用编译定义来理解

```
target_compile_definitions(mathlib
    PUBLIC  MATHLIB_VERSION=2     # "我是版本 2"——使用者也需要知道
    PRIVATE MATHLIB_USE_AVX512    # "内部用 AVX512 优化"——使用者不关心
    INTERFACE MATHLIB_HEADER_ONLY # 自己不编译任何 .cpp，但使用者需要这个宏
)
```

- `PUBLIC` 项同时出现在 `COMPILE_DEFINITIONS`（自身编译用）和 `INTERFACE_COMPILE_DEFINITIONS`（传播给消费者）。
- `PRIVATE` 项只出现在 `COMPILE_DEFINITIONS`。
- `INTERFACE` 项只出现在 `INTERFACE_COMPILE_DEFINITIONS`。纯头文件库常用 `INTERFACE`。

### 决策速查表

| 场景 | 用哪个 |
|------|--------|
| 自己的 `.cpp` 需要头文件/宏/选项，但公开头文件不暴露 | `PRIVATE` |
| 公开头文件需要头文件/宏/选项，消费者必须继承 | `PUBLIC` |
| 自己不编译任何源文件，但消费者需要这些设置 | `INTERFACE` |

> [!warning] PRIVATE ≠ "私有包含目录"这个字面意思
> `PRIVATE` 的意思是"此依赖是内部实现细节，不暴露到公开接口"。如果你的公开头文件 `#include` 了某个路径下的头文件，那个路径必须是 `PUBLIC`（或至少 `INTERFACE`），否则消费者编译时会报头文件找不到。

---

## 3. target_*() 命令详解

### target_include_directories()

```cmake
target_include_directories(<target>
    <INTERFACE|PUBLIC|PRIVATE> [items1...]
    [<INTERFACE|PUBLIC|PRIVATE> [items2...] ...]
)
```

添加头文件搜索路径（对应 `-I` 标志）。可以同时指定多个可见性块。

System include dirs 变体（对应 `-isystem`，抑制来自这些目录的警告）：

```cmake
target_include_directories(myapp SYSTEM PRIVATE third_party/boost/include)
```

还可以用 `BEFORE` 关键字将路径插入到列表前端（优先级更高）：

```cmake
target_include_directories(myapp BEFORE PRIVATE override/include)
```

### target_compile_definitions()

```cmake
target_compile_definitions(<target>
    <INTERFACE|PUBLIC|PRIVATE> [items1...]
)
```

添加预处理器宏（`-D` 标志）。注意：CMake 会自动去重，且会自动处理转义。

```cmake
target_compile_definitions(myapp
    PRIVATE
        DEBUG_LEVEL=3
        PLATFORM=\"linux\"     # 注意：引号需要转义
    PUBLIC
        MYLIB_VERSION=4
)
```

生成的编译命令：
```
-DDEBUG_LEVEL=3 -DPLATFORM=\"linux\" -DMYLIB_VERSION=4
```

### target_compile_options()

```cmake
target_compile_options(<target>
    <INTERFACE|PUBLIC|PRIVATE> [items1...]
)
```

添加编译器标志。注意：这是**追加**，不是替换。

```cmake
target_compile_options(myapp
    PRIVATE
        -Wall -Wextra
        $<$<CONFIG:Debug>:-O0 -g>
        $<$<CONFIG:Release>:-O3>
)
```

这里出现了 `$<...>` 语法——这是**生成器表达式**（Generator Expression），在 [[08-generator-expressions]] 中深入讲解。简单理解：`$<$<CONFIG:Debug>:-O0 -g>` 等价于"当构建类型为 Debug 时，添加 `-O0 -g`"。

### target_link_options()

```cmake
target_link_options(<target>
    <INTERFACE|PUBLIC|PRIVATE> [items1...]
)
```

添加链接器标志（如 `-Wl,--as-needed`、`-rpath` 等）。注意：链接库本身用 `target_link_libraries()`，这个命令是给**链接器 flag** 用的。

```cmake
target_link_options(myapp PRIVATE -Wl,--as-needed -Wl,-z,relro)
```

---

## 4. 为什么 Target 级命令优于目录级命令

Old CMake 提供的目录/全局命令：

| 旧命令 | 问题 |
|--------|------|
| `include_directories()` | 全局污染——所有 Target 都受影响 |
| `add_definitions()` | 同上，且无法区分 PUBLIC/PRIVATE |
| `add_compile_options()` | 同上 |
| `link_directories()` | 脆弱——依赖隐式库搜索路径 |
| `link_libraries()` | 覆盖所有后续 Target 的链接 |

Modern CMake 的 Target 级命令解决的核心问题：

1. **精确控制**——每个 Target 只声明自己需要的
2. **传递性**——使用 `PUBLIC`/`PRIVATE`/`INTERFACE` 自动推导消费者的需求
3. **隔离**——Target A 的 `PRIVATE` 设置不影响 Target B
4. **自文档化**——看到 Target 就知道它的所有构建需求
5. **可组合**——多个库可以安全地共存，不需要全局协调

```cmake
# ❌ Old way — 污染全局
include_directories(include/utils include/math)
add_definitions(-DUSE_OPENMP)
add_compile_options(-Wall)

add_executable(myapp main.cpp)
add_library(mylib lib.cpp)
# myapp 和 mylib 都获得了相同的 include 路径、定义和选项——即使 myapp 不需要 utils

# ✅ Modern way — 每个 Target 精确声明
add_library(mylib lib.cpp)
target_include_directories(mylib PUBLIC include/math PRIVATE include/internal)
target_compile_definitions(mylib PRIVATE USE_OPENMP)
target_compile_options(mylib PRIVATE -Wall -Wextra)

add_executable(myapp main.cpp)
target_link_libraries(myapp PRIVATE mylib)  # 自动继承 PUBLIC 属性
# myapp 获得了 include/math 路径，但看不到 include/internal 和 USE_OPENMP
```

---

## 5. ALIAS Target

### 概念

ALIAS Target 是另一个 Target 的完全等价引用——不是拷贝，是同一个 Target 的不同名字。

```cmake
add_library(mylib::mylib ALIAS mylib)
```

之后 `mylib::mylib` 和 `mylib` 指向完全相同的 Target。对其中一个设置属性会反映到另一个上。

### 为什么需要 ALIAS？

**命名空间化**。在 CMake 生态中，命名空间化的 Target 名已经成为事实标准：

```cmake
# 不推荐——无命名空间的 Target 名容易冲突
add_library(mylib ...)

# 推荐——命名空间化，与 find_package 生成的一致
add_library(mylib::mylib ALIAS mylib)
```

主要好处：
1. 如果你的项目作为包被 `find_package(MyProject)` 发现，CMake 会自动创建带命名空间的 `MyProject::mylib` Target。在项目内部也用 `mylib::mylib` ALIAS，可以保持内外部一致的引用方式。
2. `target_link_libraries(consumer mylib)` 如果 `mylib` 不存在，CMake 会尝试去系统路径找名为 `libmylib.so` 的系统库——**这是一个隐式回退，通常不是你想要的行为**。而 `target_link_libraries(consumer mylib::mylib)` 如果 `mylib::mylib` 不存在，CMake 报错——干净失败。

> [!tip] 命名空间约定
> 通常用项目名或库名作为命名空间。例如 `fmt::fmt`、`Boost::filesystem`、`OpenSSL::SSL`。

### ALIAS Target 的限制

- ALIAS 不能作为 `install()` 的目标——安装时用真实名
- ALIAS 不能有自己的源文件——它只是一个别名
- ALIAS 不能有新的属性设置——它只是引用

---

## 6. INTERFACE_LIBRARY —— 纯头文件库

### 场景

你的库完全由头文件构成，没有任何 `.cpp` 需要编译。例如一个模板库或 C++ 20 `module` 之前的纯头文件库。

```cmake
# 不需要源文件列表！
add_library(header_lib INTERFACE)

target_include_directories(header_lib
    INTERFACE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_definitions(header_lib
    INTERFACE
        HEADER_LIB_VERSION=1
)

target_compile_features(header_lib
    INTERFACE
        cxx_std_17
)
```

关键点：

- `INTERFACE` 库**不能**有 `PRIVATE` 或 `PUBLIC` 的设置——它自己不编译任何东西，自然没有"自己"的需求。
- 所有设置都是 `INTERFACE` 可见性，纯粹为消费者声明使用需求。
- `INTERFACE` 库也不需要 `SOURCES` 参数——它不会调用编译器。

### INTERFACE 库的应用

```cmake
add_executable(myapp main.cpp)
target_link_libraries(myapp PRIVATE header_lib)
# myapp 自动获得 header_lib 的所有 INTERFACE 属性：
# include 路径、编译定义、编译特性……
```

`INTERFACE` 库可以互相链接，形成传递依赖链：

```cmake
add_library(core INTERFACE)
target_include_directories(core INTERFACE include/core)

add_library(extended INTERFACE)
target_link_libraries(extended INTERFACE core)  # extended 的使用者自动获得 core
target_include_directories(extended INTERFACE include/extended)
```

---

## 7. get_target_property() 和 set_target_properties() —— 属性自省

### 读取属性

```cmake
get_target_property(<var> <target> <property>)
```

将 `<target>` 的 `<property>` 值存入变量 `<var>`。如果属性未定义，`<var>` 会被设为 `<var>-NOTFOUND`。

```cmake
get_target_property(type mylib TYPE)
message(STATUS "mylib is a ${type}")  # STATIC_LIBRARY

get_target_property(include_dirs mylib INCLUDE_DIRECTORIES)
message(STATUS "mylib include dirs: ${include_dirs}")
```

### 设置属性

`set_target_properties()` 用于设置那些没有专用 `target_*()` 命令的属性，或者一次性设置多个属性：

```cmake
set_target_properties(mylib PROPERTIES
    OUTPUT_NAME "my_cool_lib"          # 输出文件名不同于 Target 名
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
    CXX_EXTENSIONS OFF
    POSITION_INDEPENDENT_CODE ON
    VERSION 1.2.3                       # 动态库版本
    SOVERSION 1                         # SO 版本
    DEBUG_POSTFIX "_d"                  # Debug 构建时添加 _d 后缀
)
```

### 检查属性是否已定义

```cmake
get_target_property(result mylib CXX_STANDARD)
if(result STREQUAL "result-NOTFOUND")
    message(STATUS "CXX_STANDARD is not set on mylib")
else()
    message(STATUS "mylib CXX_STANDARD = ${result}")
endif()
```

> [!tip] 用 `if(TARGET ...)` 检查 Target 存在性
> `if(TARGET mylib)` 在 `mylib` 是一个有效 Target 时为真。这在编写可复用的 CMake 模块时非常有用。

---

## 8. 代码示例

### 示例 1：PUBLIC / PRIVATE / INTERFACE 包含路径传播

本示例展示三种可见性如何影响依赖方的编译。

**项目结构：**

```
example1/
├── CMakeLists.txt
├── lib/
│   ├── CMakeLists.txt
│   ├── include/
│   │   └── lib/
│   │       ├── public.h
│   │       └── detail/
│   │           └── private.h
│   └── src/
│       └── lib.cpp
└── app/
    ├── CMakeLists.txt
    └── main.cpp
```

**顶层 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(TargetPropagationDemo VERSION 1.0)

add_subdirectory(lib)
add_subdirectory(app)
```

**`lib/CMakeLists.txt`：**

```cmake
add_library(math STATIC
    src/lib.cpp
)

target_include_directories(math
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include      # 所有使用者都需要
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src            # 只有 lib.cpp 需要
)
```

**`lib/include/lib/public.h`：**

```cpp
#pragma once
#include <string>

namespace math {
    // 公开 API——消费者需要 include/lib 路径
    std::string version();
    int add(int a, int b);
}
```

**`lib/src/lib.cpp`：**

```cpp
#include "lib/public.h"           // 来自 PUBLIC include 路径
#include "detail/private.h"       // 来自 PRIVATE include 路径——只有这里能看到

namespace math {
    std::string version() { return internal::get_version(); }
    int add(int a, int b) { return a + b; }
}
```

**`lib/src/detail/private.h`：**

```cpp
#pragma once
#include <string>

namespace math { namespace internal {
    inline std::string get_version() { return "2.0-internal-preview"; }
}}
```

**`app/CMakeLists.txt`：**

```cmake
add_executable(demo main.cpp)
target_link_libraries(demo PRIVATE math)
# demo 自动获得 math 的 PUBLIC include 路径（include/lib）
# demo 看不到 PRIVATE include 路径（lib/src）
# 如果 main.cpp #include "detail/private.h" 会编译失败
```

**`app/main.cpp`：**

```cpp
#include "lib/public.h"      // ✅ 可用——来自 PUBLIC 传递
// #include "detail/private.h"  // ❌ 找不到——PRIVATE 不传递
#include <iostream>

int main() {
    std::cout << "Version: " << math::version() << "\n";
    std::cout << "1 + 2 = " << math::add(1, 2) << "\n";
    return 0;
}
```

**运行方式：**

```bash
cd example1
cmake -S . -B build
cmake --build build
./build/app/demo
```

**预期输出：**

```text
Version: 2.0-internal-preview
1 + 2 = 3
```

> [!note] 关键观察
> `demo` 成功编译了 `<lib/public.h>`，因为它通过 `math` 的 `INTERFACE_INCLUDE_DIRECTORIES` 获得了 `include/lib` 路径。如果尝试 `#include "detail/private.h"`，编译器报 `fatal error: 'detail/private.h' file not found` ——因为 `lib/src` 是 PRIVATE 的，没有传播。

---

### 示例 2：INTERFACE_LIBRARY——纯头文件库

本示例展示如何用 `INTERFACE` 库管理纯头文件项目。

**项目结构：**

```
example2/
├── CMakeLists.txt
├── include/
│   └── geometry/
│       ├── point.hpp
│       ├── rect.hpp
│       └── circle.hpp
├── tests/
│   ├── CMakeLists.txt
│   └── test_geometry.cpp
```

**顶层 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(HeaderOnlyGeometry VERSION 1.0)

add_library(geometry INTERFACE)

target_include_directories(geometry
    INTERFACE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(geometry
    INTERFACE
        cxx_std_17
)

target_compile_definitions(geometry
    INTERFACE
        GEOMETRY_VERSION=1
)

# 可选：添加编译选项（对所有使用者生效）
target_compile_options(geometry
    INTERFACE
        $<$<CXX_COMPILER_ID:GCC>:-Wno-sign-conversion>
)

add_subdirectory(tests)
```

**`include/geometry/point.hpp`：**

```cpp
#pragma once
#include <cmath>

namespace geometry {
    struct Point {
        double x = 0.0;
        double y = 0.0;

        double distance_to(const Point& other) const {
            double dx = x - other.x;
            double dy = y - other.y;
            return std::sqrt(dx * dx + dy * dy);
        }
    };
}
```

**`include/geometry/rect.hpp`：**

```cpp
#pragma once
#include "geometry/point.hpp"

namespace geometry {
    struct Rect {
        Point origin;
        double width = 0.0;
        double height = 0.0;

        double area() const { return width * height; }
        bool contains(const Point& p) const {
            return p.x >= origin.x && p.x <= origin.x + width
                && p.y >= origin.y && p.y <= origin.y + height;
        }
    };
}
```

**`include/geometry/circle.hpp`：**

```cpp
#pragma once
#include "geometry/point.hpp"

namespace geometry {
    struct Circle {
        Point center;
        double radius = 0.0;

        double area() const {
            constexpr double PI = 3.14159265358979323846;
            return PI * radius * radius;
        }
    };
}
```

**`tests/CMakeLists.txt`：**

```cmake
add_executable(test_geometry test_geometry.cpp)
target_link_libraries(test_geometry PRIVATE geometry)
# test_geometry 自动获得：
#   - include/ 路径
#   - cxx_std_17 要求
#   - GEOMETRY_VERSION=1 宏
```

**`tests/test_geometry.cpp`：**

```cpp
#include "geometry/point.hpp"
#include "geometry/rect.hpp"
#include "geometry/circle.hpp"
#include <iostream>
#include <cassert>

int main() {
    using namespace geometry;

    // 测试 Point
    Point p1{0.0, 0.0};
    Point p2{3.0, 4.0};
    assert((p1.distance_to(p2) - 5.0) < 0.001);
    std::cout << "Point distance: OK\n";

    // 测试 Rect
    Rect r{{1.0, 1.0}, 10.0, 5.0};
    assert(r.area() == 50.0);
    assert(r.contains({5.0, 3.0}));
    std::cout << "Rect: OK\n";

    // 测试 Circle
    Circle c{{0.0, 0.0}, 5.0};
    double expected_area = 3.14159265358979323846 * 25.0;
    assert((c.area() - expected_area) < 0.001);
    std::cout << "Circle: OK\n";

    // 验证编译宏
#ifdef GEOMETRY_VERSION
    std::cout << "GEOMETRY_VERSION defined: " << GEOMETRY_VERSION << "\n";
#endif

    std::cout << "All tests passed!\n";
    return 0;
}
```

**运行方式：**

```bash
cd example2
cmake -S . -B build
cmake --build build
./build/tests/test_geometry
```

**预期输出：**

```text
Point distance: OK
Rect: OK
Circle: OK
GEOMETRY_VERSION defined: 1
All tests passed!
```

> [!note] INTERFACE 库的优势
> `geometry` 没有 `.cpp` 文件，不会产生编译产物，但所有消费者自动获得头文件路径、C++ 标准要求、宏定义。当新消费者加入时，只需 `target_link_libraries(new_target PRIVATE geometry)` 即可。

---

### 示例 3：ALIAS Target 和 get_target_property 自省

本示例展示 ALIAS Target 的使用、属性自省以及两者的结合。

**项目结构：**

```
example3/
├── CMakeLists.txt
├── src/
│   ├── CMakeLists.txt
│   ├── core.cpp
│   └── include/
│       └── core.hpp
```

**顶层 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(AliasAndIntrospectDemo VERSION 2.0.1)

add_subdirectory(src)

# ---- 创建 ALIAS（命名空间化）----
add_library(project::core ALIAS core)

# ---- 属性自省：打印所有 Target 的关键属性 ----
function(print_target_info tgt)
    message(STATUS "========================================")
    message(STATUS "Target: ${tgt}")

    # TYPE
    get_target_property(t TYPE ${tgt})
    if(TYPE)
        message(STATUS "  TYPE:               ${TYPE}")
    endif()

    # INCLUDE_DIRECTORIES
    get_target_property(dirs ${tgt} INCLUDE_DIRECTORIES)
    if(dirs)
        message(STATUS "  INCLUDE_DIRECTORIES:")
        foreach(d IN LISTS dirs)
            message(STATUS "    - ${d}")
        endforeach()
    endif()

    # INTERFACE_INCLUDE_DIRECTORIES
    get_target_property(idirs ${tgt} INTERFACE_INCLUDE_DIRECTORIES)
    if(idirs)
        message(STATUS "  INTERFACE_INCLUDE_DIRECTORIES:")
        foreach(d IN LISTS idirs)
            message(STATUS "    - ${d}")
        endforeach()
    endif()

    # COMPILE_DEFINITIONS
    get_target_property(defs ${tgt} COMPILE_DEFINITIONS)
    if(defs)
        message(STATUS "  COMPILE_DEFINITIONS:")
        foreach(d IN LISTS defs)
            message(STATUS "    - ${d}")
        endforeach()
    endif()

    # CXX_STANDARD
    get_target_property(std ${tgt} CXX_STANDARD)
    if(std)
        message(STATUS "  CXX_STANDARD:       ${std}")
    endif()

    # POSITION_INDEPENDENT_CODE
    get_target_property(pic ${tgt} POSITION_INDEPENDENT_CODE)
    if(pic)
        message(STATUS "  PIC:                ${pic}")
    endif()

    # OUTPUT_NAME
    get_target_property(oname ${tgt} OUTPUT_NAME)
    if(oname)
        message(STATUS "  OUTPUT_NAME:        ${oname}")
    endif()

    message(STATUS "========================================")
endfunction()

# 打印真实 Target 的属性
print_target_info(core)

# 打印 ALIAS Target 的属性——它会解析到同一个 Target
print_target_info(project::core)

# ---- 演示 ALIAS 的行为一致性 ----
# 对 ALIAS 使用 if(TARGET ...) 返回真
if(TARGET project::core)
    message(STATUS "ALIAS 'project::core' is recognized as a valid TARGET")
endif()

# ---- 创建消费者，使用 ALIAS ----
add_executable(consumer main.cpp)
target_link_libraries(consumer PRIVATE project::core)

function(print_consumer_info)
    get_target_property(link_libs consumer LINK_LIBRARIES)
    if(link_libs)
        message(STATUS "consumer LINK_LIBRARIES:")
        foreach(l IN LISTS link_libs)
            message(STATUS "  - ${l}")
        endforeach()
    endif()
endfunction()
print_consumer_info()
```

**`src/CMakeLists.txt`：**

```cmake
add_library(core STATIC
    core.cpp
)

target_include_directories(core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_definitions(core
    PRIVATE
        CORE_BUILDING
    PUBLIC
        CORE_VERSION_MAJOR=2
        CORE_VERSION_MINOR=0
)

set_target_properties(core PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
    POSITION_INDEPENDENT_CODE ON
    OUTPUT_NAME "my_project_core"
)
```

**`src/include/core.hpp`：**

```cpp
#pragma once
#include <string>

namespace core {
    inline std::string name() { return "Core Library v2.0"; }
}
```

**`src/core.cpp`：**

```cpp
#include "core.hpp"

#ifdef CORE_BUILDING
#include <iostream>
namespace {
    struct Initializer {
        Initializer() {
            std::cout << "[core] Initialized in build mode\n";
        }
    };
    static Initializer init;
}
#endif
```

**`main.cpp`（顶层目录）：**

```cpp
#include "core.hpp"
#include <iostream>

int main() {
    std::cout << core::name() << "\n";
    return 0;
}
```

**运行方式：**

```bash
cd example3
cmake -S . -B build
cmake --build build
./build/consumer
```

**预期输出（构建时常量根据实际路径变化，逻辑输出固定）：**

```text
[core] Initialized in build mode
Core Library v2.0
```

**预期 CMake Configure 输出（关键部分）：**

```text
-- ========================================
-- Target: core
--   TYPE:               STATIC_LIBRARY
--   INCLUDE_DIRECTORIES:
--     - /path/to/example3/src/include
--   INTERFACE_INCLUDE_DIRECTORIES:
--     - /path/to/example3/src/include
--   COMPILE_DEFINITIONS:
--     - CORE_BUILDING
--     - CORE_VERSION_MAJOR=2
--     - CORE_VERSION_MINOR=0
--   CXX_STANDARD:       20
--   PIC:                ON
--   OUTPUT_NAME:        my_project_core
-- ========================================
-- ========================================
-- Target: project::core
--   TYPE:               ALIAS_LIBRARY
--   ... (其他属性与 core 相同，因为 ALIAS 是引用) ...
-- ========================================
-- ALIAS 'project::core' is recognized as a valid TARGET
-- consumer LINK_LIBRARIES:
--   - project::core
```

> [!tip] 关于 `get_target_property` 对 ALIAS 的行为
> 对 ALIAS Target 调用 `get_target_property` 会**透明地解析到真实 Target**，所以得到的结果和直接查询真实 Target 一致。但 `TYPE` 属性会是 `ALIAS_LIBRARY`（这是 CMake 的元数据标记），而 `INCLUDE_DIRECTORIES` 等构建属性则是从真实 Target 中读取的。

---

## 9. 练习

### 练习 1：创建带混合可见性的库

创建以下项目结构：

```
ex1-library/
├── CMakeLists.txt
├── include/
│   └── mylib/
│       ├── public_api.hpp      # 公开头文件——使用者需要看到
│       └── detail/
│           └── internal.hpp    # 内部头文件——只有 .cpp 需要
├── src/
│   └── mylib.cpp
└── app/
    └── main.cpp
```

要求：
1. `mylib` 是静态库
2. `include/` 路径设为 `PUBLIC`
3. `src/` 路径设为 `PRIVATE`（如果 `.cpp` 需要 include 同目录下的头文件）
4. 添加 `PUBLIC` 编译定义 `MYLIB_VERSION=1`
5. 添加 `PRIVATE` 编译选项 `-Wall`
6. 在 `app/` 目录下创建可执行文件，链接 `mylib`

验证：在 `main.cpp` 中尝试 `#include "mylib/detail/internal.hpp"` ——应该编译失败，因为 PRIVATE 不传播。

### 练习 2：INTERFACE_LIBRARY 构建头文件库

创建纯头文件的数学工具库 `mathutil`：

```
ex2-interface/
├── CMakeLists.txt
├── include/
│   └── mathutil/
│       ├── vec3.hpp
│       └── matrix4.hpp
├── tests/
│   ├── CMakeLists.txt
│   └── test_main.cpp
```

要求：
1. `mathutil` 是 `INTERFACE` 库
2. 设置 `INTERFACE` include 路径到 `include/`
3. 设置 `INTERFACE` 编译特性 `cxx_std_17`
4. 在 `tests/` 创建可执行文件测试 `mathutil`
5. 测试代码使用 `static_assert` 或 `assert` 验证模板运算

提示：`INTERFACE` 库不能有 `PRIVATE` 或 `PUBLIC` 的设置项。

### 练习 3：属性自省脚本

在上一个练习的基础上，编写一个 CMake 函数 `dump_target_properties(target)`，打印以下所有属性：

- `TYPE`
- `SOURCES`
- `INCLUDE_DIRECTORIES`
- `INTERFACE_INCLUDE_DIRECTORIES`
- `COMPILE_DEFINITIONS`
- `INTERFACE_COMPILE_DEFINITIONS`
- `CXX_STANDARD`
- `LINK_LIBRARIES`
- `INTERFACE_LINK_LIBRARIES`

对 `mathutil` 和 `test_main` 两个 Target 调用该函数。注意处理属性未定义的情况（属性值为 `xxx-NOTFOUND` 时不打印）。

---

## 10. 扩展阅读

- [CMake 官方文档: Targets](https://cmake.org/cmake/help/latest/manual/cmake-buildsystem.7.html#targets)
- [CMake 官方文档: Target Properties](https://cmake.org/cmake/help/latest/manual/cmake-properties.7.html#properties-on-targets)
- [Modern CMake: Effective Modern CMake](https://gist.github.com/mbinna/c61dbb39bca0e4fb7d1f73b0d66a4fd1) —— 经典的 Modern CMake 概览
- [An Introduction to Modern CMake (YouTube)](https://www.youtube.com/watch?v=eC9-iRN2b04) —— Henry Schreiner 的演讲
- [[07-target-link-libraries-and-transitive-deps]] —— 下一课：传递依赖深入
- [[08-generator-expressions]] —— 生成器表达式详解

---

## 常见陷阱

### 1. 使用目录级命令而非 Target 级命令

```cmake
# ❌ 全局污染
include_directories(${PROJECT_SOURCE_DIR}/include)
add_executable(myapp main.cpp)

# ✅ Target 级精确控制
add_executable(myapp main.cpp)
target_include_directories(myapp PRIVATE ${PROJECT_SOURCE_DIR}/include)
```

目录级命令影响该目录及子目录下所有 Target，并且无法区分 PUBLIC/PRIVATE/INTERFACE。大型项目中，这种隐式传播会导致难以调试的编译选项冲突。

### 2. 用 PRIVATE 暴露了公开头文件所需的依赖

这是最常见的 Modern CMake 错误：

```cmake
# ❌ mathlib 的公开头文件 #include <eigen3/Eigen/Dense>
target_include_directories(mathlib PRIVATE ${EIGEN3_INCLUDE_DIR})
# 消费者链接 mathlib 后编译失败——找不到 Eigen 头文件

# ✅ 公开头文件依赖必须 PUBLIC 或 INTERFACE
target_include_directories(mathlib PUBLIC ${EIGEN3_INCLUDE_DIR})
```

判断规则：打开你的公开头文件，逐一检查 `#include` 语句。每个 `#include` 对应的路径必须被 `PUBLIC` 或 `INTERFACE` 暴露。

### 3. 混淆 INTERFACE 和 PUBLIC 的语义

```cmake
# INTERFACE 库只有 INTERFACE 可见性
add_library(header_only INTERFACE)
target_include_directories(header_only PRIVATE include)  # ❌ 无效
target_include_directories(header_only PUBLIC include)   # ❌ 无效
target_include_directories(header_only INTERFACE include) # ✅ 正确
```

INTERFACE 库没有编译步骤，所以 `PRIVATE`（自己用）和 `PUBLIC`（自己用 + 别人用）都无意义。只能用 `INTERFACE`。

对于普通库：

```cmake
# 如果库本身不编译任何使用了 EIGEN 的 .cpp，但公开头文件引用了 Eigen
add_library(mathlib STATIC src/math.cpp)
target_include_directories(mathlib
    INTERFACE ${EIGEN3_INCLUDE_DIR}  # ✅ math.cpp 不管 Eigen，只传递给消费者
    # 如果用 PUBLIC，会多给 math.cpp 加一个不必要的 -I 路径（无害但语义不清）
)
```

### 4. 忘记 set_target_properties 中的 CXX_STANDARD_REQUIRED

```cmake
# ❌ 只设置 CXX_STANDARD——如果编译器不支持 C++20，可能静默回退到 C++17
set_target_properties(myapp PROPERTIES CXX_STANDARD 20)

# ✅ 显式要求——不支持时配置报错
set_target_properties(myapp PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
    CXX_EXTENSIONS OFF    # 禁用编译器扩展（gcc -std=c++20 而非 -std=gnu++20）
)
```

### 5. 将 ALIAS 用于 install()

```cmake
add_library(mylib::mylib ALIAS mylib)
install(TARGETS mylib::mylib ...)  # ❌ ALIAS 不能作为 install 目标

# ✅ 安装真实 Target
install(TARGETS mylib ...)
```

`install(TARGETS ...)` 需要真实 Target，因为安装操作要处理实际构建产物。ALIAS 只是一个引用，没有自己的构建产物。

### 6. 混淆 target_include_directories 的绝对路径和相对路径

```cmake
# ❌ 相对路径是相对于 SOURCE_DIR，不是当前 CMakeLists.txt 所在目录
target_include_directories(mylib PRIVATE include)
# 实际解析为 ${CMAKE_CURRENT_SOURCE_DIR}/include而非你期望的子目录

# ✅ 明确使用 CMAKE_CURRENT_SOURCE_DIR
target_include_directories(mylib PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
```

CMake 将相对路径自动解析为 `${CMAKE_CURRENT_SOURCE_DIR}/<relative>`（或 `${CMAKE_CURRENT_BINARY_DIR}/<relative>` 对生成的头文件）。虽然方便，但显式写出完整路径更可读、更健壮。

### 7. 在 INTERFACE 库上使用 set_target_properties 设置构建相关属性

```cmake
add_library(my_headers INTERFACE)
set_target_properties(my_headers PROPERTIES
    CXX_STANDARD 20  # ❌ 无效——INTERFACE 库不编译，CXX_STANDARD 无意义
    OUTPUT_NAME "foo"  # ❌ 无效——INTERFACE 库没有输出文件
)
```

对 INTERFACE 库，应使用 `target_compile_features(my_headers INTERFACE cxx_std_20)` 来声明使用者需要的 C++ 标准，而非设置 `CXX_STANDARD`。

### 8. 忘记命令行构建时指定 `-S` 和 `-B`

```bash
# ❌ 隐式源目录——构建产物散落在源码树中
cmake . && cmake --build .

# ✅ 显式源目录和构建目录
cmake -S . -B build && cmake --build build
```

`-S` 指定源目录，`-B` 指定构建目录。使用 `-B build` 进行 out-of-source 构建是现代 CMake 的最佳实践，方便清理（`rm -rf build`），支持多个构建配置共存（`build/debug`、`build/release`）。
