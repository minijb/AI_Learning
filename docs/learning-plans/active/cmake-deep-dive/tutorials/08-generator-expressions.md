---
title: 生成器表达式
updated: 2026-06-10
tags: [cmake, generator-expressions, conditional, build-system]
---

# 生成器表达式

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 60min
> 前置知识: [[04-variables-cache-and-scope]], [[07-target-link-libraries-and-transitive-deps]]

---

## 1. 概念讲解

### 为什么需要这个？

CMake 的执行分为两个阶段：**Configure 阶段**和**Generate 阶段**。当你在 `CMakeLists.txt` 中写 `if()`、`message()`、`set()` 时，它们都在 Configure 阶段执行。但很多信息直到 Generate 阶段才确定——比如：

- 多配置生成器（Xcode、Visual Studio）下，**构建类型**（Debug/Release）在 Configure 阶段可能还未选定
- 某个 target 的**最终输出文件路径**在生成器计算出后才能确定
- 某个属性的**传递值**经过依赖链解析后才能确定

> [!warning] 关键区别
> Configure 阶段只知道"将会生成什么配置"，不知道用户最终会选哪个配置。如果你在 Configure 阶段写 `if(CMAKE_BUILD_TYPE STREQUAL "Debug")`，在多配置生成器下这段代码**永远不会生效**——因为 `CMAKE_BUILD_TYPE` 在多配置生成器下为空。

生成器表达式（Generator Expressions，简称 genex）解决了这个问题：它们**在 Generate 阶段求值**，可以访问 Configure 阶段之后才有的信息。

### 核心思想

生成器表达式是形如 `$<...>` 的字符串，CMake 在 Generate 阶段将其替换为实际值。语法规则：

| 形式 | 含义 |
|------|------|
| `$<EXPR>` | 单参数表达式 |
| `$<EXPR:arg>` | 带一个参数的表达式 |
| `$<EXPR:arg1,arg2,...>` | 带多参数的表达式，逗号分隔 |

```cmake
# 基本语法
$<BOOL:${VAR}>          # 将变量转为布尔值 0 或 1
$<CONFIG:Debug>         # 如果当前配置是 Debug，展开为 1，否则 0
$<CONFIG:Debug,3>       # 如果当前配置是 Debug，展开为 "3"，否则为空
```

> [!info] 嵌套
> 生成器表达式可以嵌套，内层先求值，外层使用内层结果。这允许构建极复杂的条件逻辑。
>
> ```cmake
> $<IF:$<AND:$<CONFIG:Debug>,$<CXX_COMPILER_ID:GCC>>,-fsanitize=address,>
> ```

### 在哪里可以使用？

生成器表达式**不是**通用的——它们只能在 CMake 明确支持的地方使用：

**可以使用的位置：**

| 上下文 | 示例 |
|--------|------|
| Target 属性 | `target_compile_definitions()`, `target_include_directories()`, `target_compile_options()`, `target_link_options()` 等 |
| `add_custom_command()` / `add_custom_target()` | `COMMAND` 参数 |
| `install()` | 大部分参数 |
| `file(GENERATE)` | `CONTENT` 和 `CONDITION` 参数 |
| `add_test()` | `COMMAND` 参数 |

**不能使用的位置：**

| 不可使用 | 原因 |
|-----------|------|
| `if()` 条件判断 | `if()` 在 Configure 阶段执行，genex 尚未求值 |
| `message()` | 同上，Configure 阶段 |
| 大多数 `set()` 赋值 | genex 不会被展开成可存储的值 |
| `list()`, `string()` 命令 | Configure 阶段命令 |

> [!warning] 常见错误
> 把 genex 放进 `if()` 是最常见的陷阱。`if()` **不会**去求值 genex，它只把 `$<...>` 当成普通字符串。

---

## 2. 生成器表达式分类详解

### 2.1 条件表达式

#### `$<condition:true_string>`

如果 `condition` 展开为 `1`，返回 `true_string`；否则返回空字符串。

```cmake
$<1:hello>          # → "hello"
$<0:hello>          # → ""
$<$<CONFIG:Debug>:DEBUG_MODE>   # Debug 配置时 → "DEBUG_MODE"
```

#### `$<IF:condition,true_string,false_string>`

三元表达式。`condition` 为 `1` 返回 `true_string`，为 `0` 返回 `false_string`。

```cmake
$<IF:$<CONFIG:Debug>,/Zi,/O2>   # Debug → "/Zi", 否则 → "/O2"
```

> [!tip] `$<IF>` vs `$<condition:...>`
> `$<condition:str>` 等价于 `$<IF:condition,str,>`。当 false 分支为空时，两者可以互换，但 `$<condition:...>` 更简洁。

#### `$<BOOL:string>` — 将字符串转为布尔值

等价于 CMake 的 `if(string)` 语义：

| 输入 | `$<BOOL:...>` 结果 |
|------|-------------------|
| `"ON"`, `"YES"`, `"TRUE"`, `"Y"`, 非零数字, `"1"` | `1` |
| `"OFF"`, `"NO"`, `"FALSE"`, `"N"`, `"IGNORE"`, `"NOTFOUND"`, `""`, 后缀 `-NOTFOUND` | `0` |

```cmake
$<BOOL:ON>        # → "1"
$<BOOL:OFF>       # → "0"
$<BOOL:>          # → "0"
$<BOOL:somevalue> # → "0"（不是识别为 true 的字符串）
```

### 2.2 配置表达式

多配置生成器（Visual Studio、Xcode）的核心工具。

```cmake
$<CONFIG>                   # 当前构建配置名（"Debug", "Release" 等）
$<CONFIG:cfg>               # 当前配置 == cfg → "1"，否则 "0"
$<CONFIG:cfg,str>           # 当前配置 == cfg → str，否则 ""
```

```cmake
# 常见用法：按配置设置编译选项
target_compile_definitions(myapp PRIVATE
    $<$<CONFIG:Debug>:DEBUG=1>
    $<$<CONFIG:Release>:NDEBUG>
)

# 等价写法
target_compile_definitions(myapp PRIVATE
    $<IF:$<CONFIG:Debug>,DEBUG=1,NDEBUG>
)
```

> [!info] 单配置生成器也能工作
> 在单配置生成器（Unix Makefiles、Ninja）下，`$<CONFIG>` 的值由 `CMAKE_BUILD_TYPE` 决定——在 Generate 阶段已经确定了配置，所以 genex 求值不受影响。

### 2.3 编译器表达式

在生成器表达式中查询编译器信息，而不需要 `if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")`。

```cmake
$<C_COMPILER_ID>              # C 编译器 ID: "GNU", "Clang", "MSVC", "AppleClang"
$<CXX_COMPILER_ID>            # C++ 编译器 ID
$<C_COMPILER_VERSION>         # C 编译器完整版本号
$<CXX_COMPILER_VERSION>       # C++ 编译器完整版本号
$<COMPILE_LANGUAGE>           # 当前源文件的编译语言: "C", "CXX", "CUDA"
$<COMPILE_LANGUAGE:lang>      # 当前语言 == lang → "1"，否则 "0"
$<COMPILE_LANGUAGE:lang,str>  # 当前语言 == lang → str
```

```cmake
# 仅对 C++ 文件启用特定选项（C 文件不受影响）
target_compile_options(mylib PRIVATE
    $<$<COMPILE_LANGUAGE:CXX>:-std=c++20>
)

# 不同编译器使用不同警告标志
target_compile_options(mylib PRIVATE
    $<$<CXX_COMPILER_ID:GNU>:-Wall -Wextra>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)

# 检查编译器版本
$<$<VERSION_GREATER:$<CXX_COMPILER_VERSION>,12.0>:has_cxx23_support>
```

> [!tip] `$<COMPILE_LANGUAGE>` 与混合语言项目
> 当 target 同时包含 `.c` 和 `.cpp` 文件，或通过 `CUDA` 编译 `.cu` 文件时，`$<COMPILE_LANGUAGE>` 会根据**每个源文件**的实际语言求值，而非整个 target。这意味着你可以一次 `target_compile_options()` 调用，为不同源文件设置不同标志。

### 2.4 功能表达式

```cmake
$<COMPILE_FEATURES:features>      # features 列表全部支持 → "1"，否则 "0"
$<COMPILE_FEATURES:features,str>  # features 列表全部支持 → str
```

```cmake
target_compile_definitions(mylib PRIVATE
    $<$<COMPILE_FEATURES:cxx_auto_type>:HAS_AUTO>
    $<$<COMPILE_FEATURES:cxx_variadic_templates>:HAS_VARIADIC_TEMPLATES>
)
```

`features` 是用分号分隔的列表（CMake 列表语法），如 `cxx_std_17;cxx_constexpr`。

### 2.5 Target 表达式

最强大的 genex 类别之一——访问 target 的属性和输出文件路径。

```cmake
$<TARGET_FILE:tgt>                 # 最终输出文件完整路径
$<TARGET_FILE_NAME:tgt>            # 最终输出文件名（不含目录）
$<TARGET_FILE_DIR:tgt>             # 最终输出文件所在目录
$<TARGET_LINKER_FILE:tgt>          # 链接时使用的文件路径
$<TARGET_SONAME_FILE:tgt>          # .so 文件路径（含 soname）
$<TARGET_PROPERTY:tgt,prop>        # target 的任意属性值
$<TARGET_PROPERTY:prop>            # 当前消费 target 的属性值（transitive）
$<TARGET_EXISTS:tgt>               # target 存在 → "1"，否则 "0"
$<TARGET_NAME_IF_EXISTS:tgt>       # target 存在 → tgt 名称，否则 ""
```

```cmake
# 复制目标输出文件到构建目录
add_custom_command(TARGET myapp POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        "$<TARGET_FILE:myapp>"
        "${CMAKE_BINARY_DIR}/bin/"
)

# 在自定义命令中引用 target 的输出
add_custom_command(
    OUTPUT generated_config.h
    COMMAND my_generator
        "$<TARGET_FILE:mylib>"
        "$<TARGET_PROPERTY:mylib,INCLUDE_DIRECTORIES>"
    DEPENDS mylib
)
```

> [!important] `$<TARGET_PROPERTY:tgt,prop>` 的语义
> 它读取的是该 target **经过 genex 求值后**的属性值，包括传递依赖贡献的值。例如 `$<TARGET_PROPERTY:mylib,INTERFACE_INCLUDE_DIRECTORIES>` 会返回所有 `INTERFACE_INCLUDE_DIRECTORIES` 合并后的完整结果。这与 `get_target_property()` 不同——后者在 Configure 阶段执行，不展开 genex。

### 2.6 字符串表达式

```cmake
$<STREQUAL:a,b>                      # a == b → "1"，否则 "0"
$<EQUAL:a,b>                         # 数值 a == b → "1"
$<VERSION_GREATER:a,b>               # 版本 a > b → "1"
$<VERSION_LESS:a,b>                  # 版本 a < b → "1"
$<VERSION_EQUAL:a,b>                 # 版本 a == b → "1"
$<IN_LIST:string,list>               # string 在 list 中 → "1"
$<LOWER_CASE:string>                 # 转小写
$<UPPER_CASE:string>                 # 转大写
$<JOIN:list,d>                       # 用分隔符 d 拼接列表
$<REMOVE_DUPLICATES:list>            # 去重
$<SHELL_PATH:path>                   # 转为 shell 兼容路径
$<GENEX_EVAL:expr>                   # 对嵌套 genex 里的字符串内容再次求值
$<TARGET_GENEX_EVAL:target,expr>     # 在 target 上下文中对 expr 求值
```

```cmake
# 仅当两个配置变量一致时启用某项特性
$<$<STREQUAL:${MY_CONFIG},special>:ENABLE_SPECIAL>

# 按版本号选择编译选项
$<$<VERSION_GREATER:$<CXX_COMPILER_VERSION>,12>:-std=c++23>
$<$<VERSION_LESS:$<CXX_COMPILER_VERSION>,12>:-std=c++20>
```

### 2.7 列表表达式

操作分号分隔的 CMake 列表。

```cmake
$<LIST:LENGTH,list>                      # 列表长度
$<LIST:GET,list,index>                   # 获取第 index 个元素（从 0 开始）
$<LIST:SUBLIST,list,begin,length>        # 子列表
$<LIST:FIND,list,value>                  # 查找值的索引，不存在 → "-1"
$<LIST:TRANSFORM,list,ACTION>            # 对列表每个元素应用操作
$<FILTER:list,INCLUDE|EXCLUDE,regex>     # 正则过滤
$<LIST:APPEND,list,item>                 # 追加元素
$<LIST:PREPEND,list,item>                # 前置元素
$<LIST:INSERT,list,index,item>           # 插入元素
$<LIST:POP_BACK,list>                    # 弹出尾部
$<LIST:POP_FRONT,list>                   # 弹出首部
$<LIST:REMOVE_ITEM,list,value>           # 删除指定值
$<LIST:REMOVE_AT,list,index>             # 删除指定索引
$<LIST:REMOVE_DUPLICATES,list>           # 去重
$<LIST:REVERSE,list>                     # 反转
$<LIST:SORT,list>                        # 排序（升序）
```

`TRANSFORM` 的 ACTION 选项：`APPEND,str`, `PREPEND,str`, `TOLOWER`, `TOUPPER`, `STRIP`, `REPLACE,regex,replace`, `GENEX_STRIP` 等。

```cmake
# 为所有 include 目录追加一个子目录
target_include_directories(mylib PRIVATE
    $<LIST:TRANSFORM,$<TARGET_PROPERTY:mylib,INCLUDE_DIRECTORIES>,APPEND,/sub>
)
```

### 2.8 路径表达式

```cmake
$<PATH:GET_FILENAME,path>           # 获取文件名
$<PATH:GET_EXTENSION,path>          # 获取扩展名
$<PATH:GET_ROOT_DIRECTORY,path>     # 获取根目录
$<PATH:GET_ROOT_NAME,path>          # 获取盘符（Windows）
$<PATH:GET_ROOT_PATH,path>          # 获取根路径
$<PATH:GET_PARENT_PATH,path>        # 获取父目录
$<PATH:HAS_EXTENSION,path>          # 有扩展名 → "1"
$<PATH:HAS_FILENAME,path>           # 有文件名 → "1"
$<PATH:HAS_PARENT_PATH,path>        # 有父目录 → "1"
$<PATH:HAS_RELATIVE_PATH,path>      # 不是绝对路径 → "1"
$<PATH:HAS_ROOT_DIRECTORY,path>     # 有根目录 → "1"
$<PATH:HAS_ROOT_NAME,path>          # 有盘符 → "1"
$<PATH:HAS_ROOT_PATH,path>          # 有根路径 → "1"
$<PATH:HAS_STEM,path>               # 有 stem（不含扩展名的文件名）→ "1"
$<PATH:IS_ABSOLUTE,path>            # 绝对路径 → "1"
$<PATH:IS_PREFIXED,path>            # 有前缀（如 C:）→ "1"
$<PATH:IS_RELATIVE,path>            # 是相对路径 → "1"
$<PATH:RELATIVE_PATH,path>          # 去掉根路径后的部分
$<PATH:STEM,path>                   # 不含扩展名的文件名
```

### 2.9 逻辑表达式

```cmake
$<AND:cond1,cond2,...>    # 全部为 1 → "1"，否则 "0"
$<OR:cond1,cond2,...>     # 任一为 1 → "1"
$<NOT:cond>               # 取反
```

```cmake
# GCC + Debug 配置时才启用 sanitizer
$<$<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Debug>>:-fsanitize=address>

# MSVC 或 Clang-cl 时使用 MSVC 风格标志
$<$<OR:$<CXX_COMPILER_ID:MSVC>,$<CXX_COMPILER_ID:Clang>>:/W4>
```

### 2.10 平台表达式

```cmake
$<PLATFORM_ID>              # 当前 target 平台 ID
$<PLATFORM_ID:id>           # 匹配 → "1"
$<PLATFORM_ID:id,str>       # 匹配 → str
```

平台 ID 值：`Windows`, `Linux`, `Darwin`, `FreeBSD`, `Android`, `iOS`, `tvOS`, `watchOS` 等。

```cmake
target_link_libraries(myapp PRIVATE
    $<$<PLATFORM_ID:Linux>:-ldl>
    $<$<PLATFORM_ID:Windows>:ws2_32>
)
```

---

## 3. 代码示例

### 示例 1：基于配置和编译器的条件编译定义与选项

**项目结构：**

```
example1/
├── CMakeLists.txt
├── main.cpp
```

**`main.cpp`：**

```cpp
#include <iostream>

int main() {
#ifdef DEBUG_MODE
    std::cout << "Debug mode active\n";
#endif
#ifdef NDEBUG_FOR_RELEASE
    std::cout << "Release optimizations\n";
#endif
#ifdef EXTRA_WARNINGS
    std::cout << "Extra warnings enabled\n";
#endif
#if defined(__GNUC__)
    std::cout << "GCC compiler, version: " << __VERSION__ << "\n";
#elif defined(_MSC_VER)
    std::cout << "MSVC compiler, version: " << _MSC_VER << "\n";
#elif defined(__clang__)
    std::cout << "Clang compiler, version: " << __clang_version__ << "\n";
#endif
    return 0;
}
```

**`CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(GenexExample1 LANGUAGES CXX)

add_executable(genex_demo main.cpp)

# 条件编译定义：基于构建类型
target_compile_definitions(genex_demo PRIVATE
    $<$<CONFIG:Debug>:DEBUG_MODE>
    $<$<CONFIG:Release>:NDEBUG_FOR_RELEASE>
)

# 条件编译选项：不同编译器使用不同警告标志
target_compile_options(genex_demo PRIVATE
    # GCC/Clang 风格
    $<$<OR:$<CXX_COMPILER_ID:GNU>,$<CXX_COMPILER_ID:Clang>>:-Wall>
    $<$<OR:$<CXX_COMPILER_ID:GNU>,$<CXX_COMPILER_ID:Clang>>:-Wextra>
    # MSVC 风格
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)

# 所有编译器在 Debug 配置下启用额外警告
target_compile_definitions(genex_demo PRIVATE
    $<$<AND:$<CONFIG:Debug>,$<OR:$<CXX_COMPILER_ID:GNU>,$<CXX_COMPILER_ID:Clang>>>:EXTRA_WARNINGS>
    $<$<AND:$<CONFIG:Debug>,$<CXX_COMPILER_ID:MSVC>>:EXTRA_WARNINGS>
)
```

**运行方式：**

```bash
# 单配置生成器（Unix Makefiles / Ninja）
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build
./build/genex_demo

cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
./build/genex_demo

# 多配置生成器（Visual Studio / Xcode）
cmake -B build -G "Visual Studio 17 2022"
cmake --build build --config Debug
./build/Debug/genex_demo.exe

cmake --build build --config Release
./build/Release/genex_demo.exe
```

**预期输出（GCC + Debug）：**

```
Debug mode active
Extra warnings enabled
GCC compiler, version: 13.2.0
```

**预期输出（GCC + Release）：**

```
Release optimizations
GCC compiler, version: 13.2.0
```

### 示例 2：`$<TARGET_FILE:...>` 和 `$<TARGET_PROPERTY:...>` 用于自定义命令

**项目结构：**

```
example2/
├── CMakeLists.txt
├── lib/
│   ├── CMakeLists.txt
│   ├── mylib.cpp
│   └── mylib.h
├── app/
│   ├── CMakeLists.txt
│   └── main.cpp
```

**`lib/mylib.h`：**

```cpp
#pragma once
const char* hello_from_lib();
```

**`lib/mylib.cpp`：**

```cpp
#include "mylib.h"
const char* hello_from_lib() { return "Hello from mylib!"; }
```

**`lib/CMakeLists.txt`：**

```cmake
add_library(mylib SHARED mylib.cpp mylib.h)
target_include_directories(mylib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
```

**`app/main.cpp`：**

```cpp
#include <iostream>
#include "mylib.h"
int main() {
    std::cout << hello_from_lib() << std::endl;
    return 0;
}
```

**`app/CMakeLists.txt`：**

```cmake
add_executable(myapp main.cpp)
target_link_libraries(myapp PRIVATE mylib)
```

**顶层 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(GenexExample2 LANGUAGES CXX)

add_subdirectory(lib)
add_subdirectory(app)

# 自定义目标：打印所有编译产物的路径
add_custom_target(show_outputs ALL
    COMMAND ${CMAKE_COMMAND} -E echo "=== Target Output Paths ==="
    COMMAND ${CMAKE_COMMAND} -E echo "myapp:  $<TARGET_FILE:myapp>"
    COMMAND ${CMAKE_COMMAND} -E echo "myapp dir: $<TARGET_FILE_DIR:myapp>"
    COMMAND ${CMAKE_COMMAND} -E echo "mylib:  $<TARGET_FILE:mylib>"
    COMMAND ${CMAKE_COMMAND} -E echo ""
    COMMAND ${CMAKE_COMMAND} -E echo "=== mylib Properties ==="
    COMMAND ${CMAKE_COMMAND} -E echo "TYPE: $<TARGET_PROPERTY:mylib,TYPE>"
    COMMAND ${CMAKE_COMMAND} -E echo "PREFIX: $<TARGET_PROPERTY:mylib,PREFIX>"
    COMMAND ${CMAKE_COMMAND} -E echo "SUFFIX: $<TARGET_PROPERTY:mylib,SUFFIX>"
    COMMAND ${CMAKE_COMMAND} -E echo ""
    COMMAND ${CMAKE_COMMAND} -E echo "=== myapp INCLUDE_DIRECTORIES ==="
    COMMAND ${CMAKE_COMMAND} -E echo "$<TARGET_PROPERTY:myapp,INCLUDE_DIRECTORIES>"
    DEPENDS myapp mylib
    COMMENT "Showing target output paths and properties"
    VERBATIM
)

# 复制 mylib 到 app 输出目录（POST_BUILD 自定义命令）
add_custom_command(TARGET myapp POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_FILE:mylib>"
        "$<TARGET_FILE_DIR:myapp>"
    COMMENT "Copying mylib to app output directory"
)
```

**运行方式：**

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

**预期输出：**

```
[build] Showing target output paths and properties
=== Target Output Paths ===
myapp:  /path/to/build/app/myapp
myapp dir: /path/to/build/app
mylib:  /path/to/build/lib/libmylib.so

=== mylib Properties ===
TYPE: SHARED_LIBRARY
PREFIX: lib
SUFFIX: .so

=== myapp INCLUDE_DIRECTORIES ===
/path/to/example2/lib
```

### 示例 3：复杂嵌套表达式——按编译器和配置选择性启用 `-Werror` / `/WX`

**项目结构：**

```
example3/
├── CMakeLists.txt
├── main.cpp
```

**`main.cpp`：**

```cpp
// 故意写一些会触发警告的代码
#include <iostream>

int main() {
    int unused_var = 42;              // 未使用变量
    double x = 10 / 3;                // 隐式转换
    if (x = 5.0) {                    // 赋值替代比较（-Wparentheses）
        std::cout << "x is " << x << std::endl;
    }
    return 0;
}
```

**`CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(GenexExample3 LANGUAGES CXX)

add_executable(werror_demo main.cpp)

# 基础警告标志
target_compile_options(werror_demo PRIVATE
    $<$<OR:$<CXX_COMPILER_ID:GNU>,$<CXX_COMPILER_ID:Clang>>:-Wall -Wextra>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)

# ============================================================
# 复杂嵌套表达式：
# - GCC Release  → -Werror（所有警告变为错误）
# - MSVC Release → /WX（所有警告变为错误）
# - 其他配置和编译器 → 不加 -Werror//WX
#
# 策略分解：
#   GCC:
#     $<IF:$<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Release>>,-Werror,>
#   MSVC:
#     $<IF:$<AND:$<CXX_COMPILER_ID:MSVC>,$<CONFIG:Release>>,/WX,>
#
# 合并为 OR（两者开其一即可）：
#   $<IF:$<OR:
#           $<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Release>>,
#           $<AND:$<CXX_COMPILER_ID:MSVC>,$<CONFIG:Release>>
#         >,
#         $<IF:$<CXX_COMPILER_ID:MSVC>,/WX,-Werror>,  ← 还要区分 GCC 和 MSVC
#         >
# ============================================================

target_compile_options(werror_demo PRIVATE
    $<IF:$<OR:
        $<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Release>>,
        $<AND:$<CXX_COMPILER_ID:Clang>,$<CONFIG:Release>>
    >,
    -Werror,
    $<$<AND:$<CXX_COMPILER_ID:MSVC>,$<CONFIG:Release>>:/WX>
    >
)
```

**运行方式：**

```bash
# GCC + Debug — 警告但不报错
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build
# 应有警告但编译通过

# GCC + Release — 警告即错误
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
# 应编译失败（unused_var, -Wparentheses 等变为错误）

# MSVC + Debug
cmake -B build -G "Visual Studio 17 2022"
cmake --build build --config Debug
# 应有警告但编译通过

# MSVC + Release
cmake --build build --config Release
# 应编译失败（/WX 将警告转为错误）
```

**预期输出（GCC + Release，编译失败）：**

```
/path/to/main.cpp: In function 'int main()':
/path/to/main.cpp:5:9: error: unused variable 'unused_var' [-Werror=unused-variable]
    5 |     int unused_var = 42;
      |         ^~~~~~~~~~
/path/to/main.cpp:7:12: error: suggest parentheses around assignment used as truth value [-Werror=parentheses]
    7 |     if (x = 5.0) {
      |         ~~^~~~~
cc1plus: all warnings being treated as errors
```

---

## 4. 练习

### 练习 1：Debug 构建下添加 `-fsanitize=address`

**目标：** 编写一个生成器表达式，仅在 Debug 配置 + GNU 或 Clang 编译器时，为目标添加 `-fsanitize=address` 编译和链接选项。

**模板：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(SanitizerExercise LANGUAGES CXX)

add_executable(sanitize_demo main.cpp)

# TODO: 在 Debug + GCC/Clang 时添加 -fsanitize=address
# 提示：sanitizer 需要同时作为编译选项和链接选项
target_compile_options(sanitize_demo PRIVATE
    # 你的 genex 在这里
)

target_link_options(sanitize_demo PRIVATE
    # 你的 genex 在这里
)
```

**验证：**

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --verbose   # 应看到编译命令中包含 -fsanitize=address

cmake -B build_release -DCMAKE_BUILD_TYPE=Release
cmake --build build_release --verbose  # 不应包含 -fsanitize=address
```

### 练习 2：创建打印目标输出路径的自定义 target

**目标：** 创建一个自定义 target `print_target_info`，构建时打印另一个目标（如 `myapp`）的输出路径、文件名和 `INCLUDE_DIRECTORIES` 属性值。

**模板：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(PrintInfoExercise LANGUAGES CXX)

add_library(mylib mylib.cpp mylib.h)
add_executable(myapp main.cpp)
target_link_libraries(myapp PRIVATE mylib)

# TODO: 创建 custom target，运行 cmake -E echo 打印信息
# 打印内容：
#   1. TARGET_FILE 路径
#   2. TARGET_FILE_NAME
#   3. TARGET_PROPERTY INCLUDE_DIRECTORIES
```

**验证：**

```bash
cmake -B build
cmake --build build --target print_target_info
# 应看到完整路径输出
```

### 练习 3：构建嵌套表达式——GCC ≥ 12 + Release → `-O3 -march=native`

**目标：** 构建一个嵌套生成器表达式：
- 如果编译器是 GCC **且**版本 ≥ 12 **且**配置为 Release → 添加 `-O3 -march=native`
- 如果编译器是 GCC **且**版本 ≥ 12 **且**配置不是 Release → 仅添加 `-O2`
- 如果是 Clang 编译器 → 添加 `-O2 -fvectorize`
- 其他编译器 → 不添加额外优化标志

**提示：** 使用 `$<VERSION_GREATER_EQUAL:$<CXX_COMPILER_VERSION>,12>` 检查版本。

```cmake
cmake_minimum_required(VERSION 3.24)
project(NestedGenexExercise LANGUAGES CXX)

add_executable(nested_demo main.cpp)

# TODO: 你的嵌套 genex
target_compile_options(nested_demo PRIVATE
    # 在这里构建
)
```

**参考思路（可作为答案对照）：**

```cmake
target_compile_options(nested_demo PRIVATE
    $<IF:$<AND:$<CXX_COMPILER_ID:GNU>,$<VERSION_GREATER_EQUAL:$<CXX_COMPILER_VERSION>,12>>,
        $<IF:$<CONFIG:Release>,-O3 -march=native,-O2>,
        $<$<CXX_COMPILER_ID:Clang>:-O2 -fvectorize>
    >
)
```

**验证：**

```bash
# GCC 12+, Release: 应看到 -O3 -march=native
cmake -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++-13
cmake --build build --verbose

# GCC 12+, Debug: 应看到 -O2
cmake -B build_dbg -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_COMPILER=g++-13
cmake --build build_dbg --verbose

# Clang: 应看到 -O2 -fvectorize
cmake -B build_clang -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=clang++
cmake --build build_clang --verbose
```

---

## 5. 扩展阅读

### CMake 官方文档

- [Generator Expressions](https://cmake.org/cmake/help/latest/manual/cmake-generator-expressions.7.html) — 完整 genex 参考，包含所有表达式类型
- [cmake-generator-expressions(7)](https://cmake.org/cmake/help/latest/manual/cmake-generator-expressions.7.html) — 官方手册页

### 调试生成器表达式

在开发过程中，有几种方法可以查看生成器表达式的求值结果：

#### 方法 1：`add_custom_target` + `cmake -E echo`

```cmake
add_custom_target(debug_genex ALL
    COMMAND ${CMAKE_COMMAND} -E echo "$<TARGET_FILE:myapp>"
    VERBATIM
)
```

> [!warning] 引号是必须的
> genex 结果可能包含空格（如 `$<TARGET_PROPERTY:tgt,INCLUDE_DIRECTORIES>`），不加引号会导致 `cmake -E echo` 将空格分隔的部分当作多个参数。

#### 方法 2：`file(GENERATE)`

```cmake
file(GENERATE
    OUTPUT debug_genex_output.txt
    CONTENT "myapp path: $<TARGET_FILE:myapp>\n"
)
```

`file(GENERATE)` 在 Generate 阶段执行，求值 genex 后将结果写入文件。构建后检查文件内容即可。

#### 方法 3：`cmake -E env` 验证

对于某些表达式（如 `$<CONFIG>`），可以直接用多配置生成器加不同 `--config` 参数验证，观察输出是否变化。

### 相关专题

- [[17-cmake-language-deep-dive]] — CMake 语言深入，理解 genex 与普通命令的边界
- [[19-cmake-internal-architecture]] — 理解 Configure/Generate/Build 三阶段模型
- [[16-custom-commands-and-generated-files]] — `add_custom_command` 的高阶用法
- [[20-multi-config-and-ninja]] — 多配置生成器的原理及 genex 为何是必需的

---

## 常见陷阱

### 陷阱 1：在 `if()` 或 `message()` 中使用 genex

```cmake
# ❌ 错误 — if() 在 configure 阶段执行，genex 不会被求值
if($<CONFIG:Debug>)
    message("This is Debug mode")
endif()
# 条件永远为 false——因为 "$<CONFIG:Debug>" 是非空字符串，
# 但 STRGREATER 比较时不会展开 genex

# ❌ 错误 — message() 不会求值 genex
message("Config: $<CONFIG>")
# 输出字面文本 "Config: $<CONFIG>"

# ✅ 正确 — 使用 CMAKE_BUILD_TYPE 变量（仅单配置生成器）
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    message("This is Debug mode")
endif()
```

### 陷阱 2：含空格的 genex 忘记加引号

```cmake
# ❌ 错误 — 不加引号时，$<LIST:JOIN,...> 结果中的空格会被当作参数分隔符
add_custom_target(debug_info
    COMMAND ${CMAKE_COMMAND} -E echo $<TARGET_PROPERTY:myapp,INCLUDE_DIRECTORIES>
)
# echo 命令可能收到多个参数而非一个字符串

# ✅ 正确 — 用引号包裹整个 genex
add_custom_target(debug_info
    COMMAND ${CMAKE_COMMAND} -E echo "$<TARGET_PROPERTY:myapp,INCLUDE_DIRECTORIES>"
    VERBATIM
)
```

### 陷阱 3：跨行拆分 genex

```cmake
# ❌ 错误 — genex 不能跨多行
target_compile_options(myapp PRIVATE
    $<IF:$<AND:
        $<CXX_COMPILER_ID:GNU>,
        $<CONFIG:Release>
    >,-O3,>
)
# CMake 会在解析时将换行和缩进视为 genex 内容的一部分

# ✅ 正确 — 保持整个 genex 在一行内
target_compile_options(myapp PRIVATE
    $<IF:$<AND:$<CXX_COMPILER_ID:GNU>,$<CONFIG:Release>>,-O3,>
)
```

### 陷阱 4：genex 中逗号的引号处理

当 genex 参数本身包含逗号时，可以视为多项（CMake 会按逗号分割），也可能需要保持原样。CMake 3.24+ 支持用 `[[` 和 `]]` 包裹含逗号的字符串：

```cmake
# 如果 target 属性值包含逗号，需要用 [[...]] 包裹
$<TARGET_PROPERTY:myapp,[[COMPILE_OPTIONS]]>
```

### 陷阱 5：假设 genex 在 `set()` 中会被求值

```cmake
# ❌ 错误 — set() 不会求值 genex
set(MY_VAR "$<TARGET_FILE:myapp>")
message("MY_VAR = ${MY_VAR}")
# 输出字面字符串 "$<TARGET_FILE:myapp>"

# ✅ 如果需要存储 genex 的结果，用 file(GENERATE)
file(GENERATE OUTPUT my_output.txt CONTENT "$<TARGET_FILE:myapp>")
```

### 陷阱 6：混淆 `$<CONFIG>` 和 `CMAKE_BUILD_TYPE`

| | `$<CONFIG>` | `CMAKE_BUILD_TYPE` |
|---|---|---|
| 求值阶段 | Generate | Configure |
| 多配置生成器 | ✅ 正确工作 | ❌ 为空字符串 |
| 单配置生成器 | ✅ 正确工作 | ✅ 正确工作 |
| 可用于 `if()` | ❌ | ✅ |

> [!important] 规则
> 在 target 属性（`target_compile_options` 等）和 `install()` 中，**始终**使用 `$<CONFIG>`。在 CMake 脚本逻辑（`if()`, `message()` 等）中，使用 `CMAKE_BUILD_TYPE` 但需注意它仅在单配置生成器下生效。

### 陷阱 7：`$<TARGET_PROPERTY:tgt,prop>` 中 prop 不是属性名

```cmake
# ❌ 常见拼写错误或使用了不存在的属性名
$<TARGET_PROPERTY:myapp,OUTPUT_NAME>   # 应该是 OUTPUT_NAME（存在）
$<TARGET_PROPERTY:myapp,OUTPUT_FILE>   # 不存在！→ 空字符串
# 正确的属性是 TARGET_FILE 通过 $<TARGET_FILE:...> 获取

# ✅ 使用 cmake --help-property-list 查看所有有效属性
```

### 陷阱 8：忘记 genex 也可返回空字符串

```cmake
# 当条件不满足时，genex 展开为空字符串，可能导致语法错误
target_compile_options(myapp PRIVATE
    -Wall
    $<$<CXX_COMPILER_ID:GNU>:-Wextra>   # 非 GCC → ""（无影响）
    ignored_flag                          # 永远生效
)
# 上例是安全的。不安全的情况：
add_custom_target(show_file
    COMMAND cat $<TARGET_FILE:nonexistent_target>   # → "cat "（空文件名）
)
```

> [!tip] 最佳实践
> 使用 `$<TARGET_EXISTS:tgt>` 在对 target 使用 `$<TARGET_FILE:...>` 之前检查其是否存在：
>
> ```cmake
> $<IF:$<TARGET_EXISTS:myapp>,$<TARGET_FILE:myapp>,target_not_found>
> ```
