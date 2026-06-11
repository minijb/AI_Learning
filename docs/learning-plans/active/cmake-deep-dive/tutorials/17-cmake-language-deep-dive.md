---
title: "CMake 语言深入——函数、宏、模块"
updated: 2026-06-10
tags: [cmake, language, function, macro, module]
---

# CMake 语言深入——函数、宏、模块

> 所属计划: [[INDEX|CMake 深度学习]]
> 预计耗时: 60 分钟
> 前置知识: [[04-variables-cache-and-scope|04 变量、缓存与作用域]]
---

## 1. 概念讲解

CMake 不仅仅是一套构建描述语言——它本身是一门图灵完备的命令式编程语言。在自动化构建任务的背后，函数、宏、模块、循环、条件判断构成了 CMake 脚本的骨架。本章深入剖析 CMake 语言的运行机制，让你从"会用 command"升级到"能写 CMake 框架"。

### 1.1 `function()` vs `macro()` —— 核心差异

这是 CMake 中最容易被误解的设计之一。虽然两者都支持参数传递和命令封装，但它们的执行模型有本质区别。

#### 宏：文本替换

`macro()` 在**被调用时**进行文本替换——宏体内的内容被原地展开到调用点，就像 C 语言预处理器宏。这意味着：

- **没有新作用域**：宏内部定义的变量污染调用者作用域。
- **参数是字符串字面替换**：`${ARGN}` 是调用者传入的原始文本，在宏展开时替换。
- **`return()` 从调用者返回**：宏内调用 `return()` 会提前结束**调用者**的 CMakeLists.txt 处理。

```cmake
macro(my_macro arg1)
    message("Inside macro: ${arg1}")
    set(modified "YES")
endmacro()

set(modified "NO")
my_macro(hello)
message("After macro: ${modified}")   # 输出 YES——调用者的变量被修改了
```

#### 函数：新作用域

`function()` 在被调用时创建一个**新的变量作用域**——就像常规编程语言中的函数调用：

- **独立作用域**：函数内 `set()` 的变量默认不会泄漏到调用者。
- **`PARENT_SCOPE` 可写回**：`set(var value PARENT_SCOPE)` 仍然可以修改调用者的变量。
- **`return()` 仅退出函数**：不影响调用者的控制流。
- **参数是真实的值传递**：`${ARGV0}` 拿到的是调用者实参**展开后的值**，不是原始文本。

```cmake
function(my_func arg1)
    message("Inside func: ${arg1}")
    set(modified "YES")
endfunction()

set(modified "NO")
my_func(hello)
message("After func: ${modified}")    # 输出 NO——函数作用域隔离生效
```

> [!IMPORTANT]
> **选择原则：永远优先使用 `function()`。** 只有当你的封装**必须**修改调用者作用域中的多个变量且采用函数+PARENT_SCOPE 组合过于笨重时，才考虑 `macro()`。Text substitution 带来的隐式副作用是 CMake 调试中最令人头疼的问题之一。

#### 行为对照表

| 特性 | `function()` | `macro()` |
|------|-------------|-----------|
| 变量作用域 | 新作用域 | 调用者作用域 |
| 参数传递 | 值传递（展开后） | 文本替换（原始字符串） |
| `return()` | 退出函数 | 退出调用者 |
| `ARGN` 内容 | 展开后的参数值 | 原始参数字符串 |
| `break()`/`continue()` | 仅影响函数内循环 | 影响调用者中的循环 |
| 递归调用 | 支持 | 支持（但不推荐，容易栈溢出） |

### 1.2 参数处理：`ARGC`、`ARGV`、`ARGN`

CMake 的函数和宏都支持零个或任意多个参数，无需声明形参即可使用。内部使用以下特殊变量：

| 变量 | 含义 |
|------|------|
| `ARGC` | 实参总数（不含命名形参） |
| `ARGV` | 保存所有实参的列表 |
| `ARGV0`...`ARGVN` | 第 0 到第 N 个实参（0-indexed） |
| `ARGN` | 超过命名形参的额外实参列表 |

`ARGN` 是最常用的——它让你在`cmake_parse_arguments`出现之前处理变长参数：

```cmake
function(debug_print message)
    # message 会被第一个实参绑定
    # ARGN 包含剩余的所有实参（可用于前缀、标签等）
    if(ARGC GREATER 1)
        foreach(prefix IN LISTS ARGN)
            message(STATUS "[${prefix}] ${message}")
        endforeach()
    else()
        message(STATUS "${message}")
    endif()
endfunction()

debug_print("Build started" "INFO" "CMAKE")
# 输出：
# -- [DEBUG] Build started
# -- [INFO] Build started
# -- [CMAKE] Build started
```

> [!WARNING]
> `ARGV0` 是**展开后的值**（对于函数），不是原始文本。这意味着如果实参是 `${some_var}`，且 `some_var` 的值在调用前是 `"a;b;c"`，那么 `ARGV0` 将是 `a;b;c`——一个列表，而不是字符串 `"a;b;c"`。这是 CMake 字符串即列表机制的一个常见陷阱。

### 1.3 `cmake_parse_arguments()` —— Modern CMake 风格的参数解析

`cmake_parse_arguments()`（CMake 3.5+ 内置）是构建用户友好 API 的核心工具。它让你定义：

- **选项**（`OPTIONS`）：布尔开关，如 `VERBOSE`、`REQUIRED`
- **单值参数**（`ONE_VALUE_KEYWORDS`）：`NAME foo`、`VERSION 1.0`
- **多值参数**（`MULTI_VALUE_KEYWORDS`）：`SOURCES a.cpp b.cpp`、`LIBRARIES pthread dl`

```cmake
include_guard(GLOBAL)

function(add_my_library)
    set(options   STATIC SHARED HEADER_ONLY)
    set(oneValue  NAME VERSION)
    set(multiValue SOURCES LIBRARIES INCLUDES)

    cmake_parse_arguments(
        PARSE_ARGV 0          # CMake 3.5+: 从 ARGV0 开始解析，推荐方式
        ARG
        "${options}"
        "${oneValue}"
        "${multiValue}"
    )

    # 解析结果：
    # ARG_STATIC, ARG_SHARED, ARG_HEADER_ONLY — TRUE/FALSE
    # ARG_NAME, ARG_VERSION               — 字符串值
    # ARG_SOURCES, ARG_LIBRARIES, ARG_INCLUDES — 列表值
    # ARG_UNPARSED_ARGUMENTS              — 未能识别的参数
    # ARG_KEYWORDS_MISSING_VALUES         — 有键无值的参数

    if(ARG_UNPARSED_ARGUMENTS)
        message(FATAL_ERROR "Unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
    endif()

    if(NOT ARG_NAME)
        message(FATAL_ERROR "NAME is required")
    endif()

    # ... 使用解析结果创建 target
endfunction()
```

**`PARSE_ARGV N` vs 传统方式**：`PARSE_ARGV 0` 是推荐的新写法，它直接从 `ARGV<N>` 开始解析。旧写法需要手动传递 `${ARGN}`，且无法正确处理参数值中带分号的情况。

> [!TIP]
> 始终检查 `${prefix}_UNPARSED_ARGUMENTS`。如果非空，说明调用者提供了未知参数（可能是拼写错误），直接 `FATAL_ERROR` 报错比静默忽略更友好。

### 1.4 函数相关特殊变量

CMake 在函数内部提供了一些上下文变量：

| 变量 | 含义 | CMake 版本 |
|------|------|-----------|
| `CMAKE_CURRENT_FUNCTION` | 当前函数名 | 3.8+ |
| `CMAKE_CURRENT_FUNCTION_LIST_DIR` | 当前函数所在文件的**目录**（绝对路径） | 3.8+ |
| `CMAKE_CURRENT_FUNCTION_LIST_FILE` | 当前函数所在文件的完整路径 | 3.8+ |
| `CMAKE_CURRENT_FUNCTION_LIST_LINE` | 当前函数定义所在文件的行号 | 3.8+ |

这些变量尤其重要在编写 `.cmake` 模块时——`CMAKE_CURRENT_FUNCTION_LIST_DIR` 让你引用模块文件**旁边**的资源文件：

```cmake
# my_module.cmake
function(my_module_do_thing target)
    # 找到模块所在目录下的资源
    set(resource_dir "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/resources")
    target_sources(${target} PRIVATE "${resource_dir}/impl.cpp")
endfunction()
```

`CMAKE_CURRENT_FUNCTION_LIST_DIR` 始终指向**模块文件**所在的目录，无论 `include()` 发生在哪个目录。这确保了模块的可移植性。

### 1.5 `include()` —— 在配置时引入 CMake 模块

`include()` 在 CMake 配置阶段（configure time）将指定文件的 CMake 代码读入并执行。它的行为取决于参数形式：

```cmake
# 形式一：包含已知模块（搜索 CMAKE_MODULE_PATH）
include(CMakeDependentOption)        # 标量参数：搜索内置模块 + CMAKE_MODULE_PATH

# 形式二：包含指定文件
include(cmake/my_helpers.cmake)       # 相对路径（相对 CMAKE_CURRENT_SOURCE_DIR）
include(/absolute/path/tools.cmake)   # 绝对路径

# 形式三：可选包含
include(OptionalModule OPTIONAL)      # 找不到不报错
include(RequiredModule)               # 找不到立即 FATAL_ERROR
```

**常用内置模块**：

| 模块 | 功能 |
|------|------|
| `GNUInstallDirs` | 定义 `CMAKE_INSTALL_BINDIR`、`CMAKE_INSTALL_LIBDIR` 等变量 |
| `CMakeDependentOption` | 提供 `cmake_dependent_option()`——依赖其他选项才显示的配置开关 |
| `FeatureSummary` | 提供 `feature_summary()`——在配置结束时打印各选项的启用/禁用状态 |
| `CheckCXXCompilerFlag` | 检测编译器是否支持某个 flag |
| `TestBigEndian` | 检测目标平台的字节序 |

```cmake
# CMakeDependentOption 示例
include(CMakeDependentOption)
cmake_dependent_option(BUILD_TESTS "Build tests" ON "BUILD_SHARED_LIBS" OFF)
# BUILD_TESTS 只有在 BUILD_SHARED_LIBS 为 ON 时才可见/可配置
```

> [!IMPORTANT]
> `include()` 和 `find_package()` 的区别：`include()` 直接执行 `.cmake` 文件中的 CMake 代码（通常是定义函数和宏）；`find_package()` 按照查找协议执行 `Find<Package>.cmake` 或 `<Package>Config.cmake`，它返回一个是否找到的结果，并设置相关变量。

### 1.6 `CMAKE_MODULE_PATH` —— 自定义模块路径

`CMAKE_MODULE_PATH` 是一个分号分隔的**目录列表**。当 `include()` 或 `find_package()` 接收一个不带路径分隔符的模块名时，CMake 会依次在这些目录中查找：

```cmake
# 模块搜索顺序：
# 1. CMAKE_MODULE_PATH 中的目录（按声明的先后顺序）
# 2. CMake 内置模块目录（如 /usr/share/cmake-3.24/Modules）

list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake/platform")

# 现在 include(MyHelpers) 会依次尝试：
# ${CMAKE_SOURCE_DIR}/cmake/MyHelpers.cmake
# ${CMAKE_SOURCE_DIR}/cmake/platform/MyHelpers.cmake
# <cmake-install>/Modules/MyHelpers.cmake
```

> [!WARNING]
> 模块文件名**必须**是 `<ModuleName>.cmake`——CMake 不会尝试其他扩展名。另外，`include()` 是大小写敏感的，`include(Foo)` 和 `include(foo)` 在文件系统中可能解析到不同文件。

### 1.7 编写可复用的 CMake 模块

一个典型的 CMake 模块是一个 `.cmake` 文件，包含：

1. **`include_guard(GLOBAL)`** —— 防止重复包含
2. **函数定义** —— 提供对外的 API
3. **内部辅助函数/宏** —— 以 `_` 开头表示私有
4. **可能有初始化代码** —— 比如设置默认变量

```cmake
# cmake/SanitizerHelpers.cmake — 一个可复用模块
include_guard(GLOBAL)

function(enable_sanitizers target)
    cmake_parse_arguments(SAN "ADDRESS;UNDEFINED;THREAD;MEMORY" "" "" ${ARGN})

    if(SAN_ADDRESS)
        target_compile_options(${target} PRIVATE -fsanitize=address -fno-omit-frame-pointer)
        target_link_options(${target} PRIVATE -fsanitize=address)
    endif()

    if(SAN_UNDEFINED)
        target_compile_options(${target} PRIVATE -fsanitize=undefined)
        target_link_options(${target} PRIVATE -fsanitize=undefined)
    endif()

    # ... (THREAD, MEMORY 类似)
endfunction()
```

```cmake
# CMakeLists.txt — 使用模块
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")
include(SanitizerHelpers)

add_executable(my_app main.cpp)
enable_sanitizers(my_app ADDRESS UNDEFINED)
```

**模块设计原则**：

- **用 `function()` 而非 `macro()`**——函数的作用域隔离使得模块可以安全地在任何上下文中使用。
- **避免在顶层设置变量**（除了 `list(APPEND CMAKE_MODULE_PATH …)` 这样的元数据）。模块的顶层代码在 `include()` 时立即执行，可能在用户设置完选项之前。
- **使用 `CMAKE_CURRENT_FUNCTION_LIST_DIR`** 引用模块文件旁的数据，保持模块可移植。
- **命名前缀**：所有公开函数名使用模块名作为前缀（如 `sanitizer_enable()`），避免命名冲突。

### 1.8 `cmake_language()` —— 元编程与延迟执行 (CMake 3.18+)

`cmake_language()` 是 CMake 元编程的瑞士军刀，支持延迟调用、动态求值和脚本执行。

#### `cmake_language(CALL ...)` —— 动态调用

```cmake
set(func_name "my_custom_function")
cmake_language(CALL ${func_name} arg1 arg2)
# 等价于: my_custom_function(arg1 arg2)
```

与直接 `${func_name}(arg1 arg2)` 的区别在于：`cmake_language(CALL …)` 能正确处理 `func_name` 中包含的嵌套命令展开和各种边界情况。但对于简单情况两者等价。

#### `cmake_language(EVAL CODE ...)` —— 从字符串执行 CMake 代码

这是 CMake 的 `eval`——将字符串作为 CMake 代码执行：

```cmake
set(code [[
    message("Generated at configure time: ${CMAKE_CURRENT_LIST_DIR}")
    foreach(i RANGE 1 5)
        message("  i = ${i}")
    endforeach()
]])

message("=== About to EVAL ===")
cmake_language(EVAL CODE "${code}")
message("=== EVAL done ===")
```

**EVAL 的典型用途**：
- 根据配置动态构建 CMake 代码
- 循环内动态调用不同函数
- 实现简单的模板/代码生成逻辑

```cmake
# 动态调用多个函数
set(targets "core;network;ui")
foreach(t IN LISTS targets)
    set(call_str "configure_${t}(VERBOSE)")
    cmake_language(EVAL CODE "${call_str}")
endforeach()
```

#### `cmake_language(DEFER ...)` —— 延迟执行 (CMake 3.19+)

这可能是 `cmake_language` 最强大的子命令。它允许你在**当前目录作用域处理完毕之后**才执行指定的命令：

```cmake
cmake_language(DEFER CALL message "This runs AFTER the current directory scope ends.")

# DEFER 可以指定延迟到哪个目录作用域结束
cmake_language(DEFER DIRECTORY ${CMAKE_SOURCE_DIR}
    CALL message "Ran at the very end of the top-level scope"
)

# 多个 DEFER 调用按 LIFO（栈）顺序执行
cmake_language(DEFER CALL message "Third (last deferred)")
cmake_language(DEFER CALL message "Second")
cmake_language(DEFER CALL message "First (deferred last)")
# 执行顺序: First -> Second -> Third
```

**DEFER 的最佳实践场景**：

1. **延迟 target 属性设置**：等所有 target 都定义好后再批量操作
2. **收集期延迟到处理完毕**：如同垃圾回收中的 finalizer
3. **解耦模块间的初始化顺序**：确保 A 模块的收尾工作发生在 B 模块完成之后

```cmake
# 实用模式：收集所有需要链接 pthread 的 target，最后统一处理
macro(need_pthread target)
    set_property(GLOBAL APPEND PROPERTY _pthread_targets ${target})
endmacro()

# 在顶层的 CMakeLists.txt 中：
cmake_language(DEFER DIRECTORY ${CMAKE_SOURCE_DIR} CALL _link_pthread_all)
# _link_pthread_all 会在所有子目录处理完之后被调用，
# 届时 _pthread_targets 属性中已经收集了全部需要 pthread 的 target
```

#### `cmake_language(GET_LOG_LEVEL / SET_LOG_LEVEL)` (CMake 3.25+)

查询和设置当前以空格分隔的 `--log-level` 追踪域：

```cmake
cmake_language(GET_LOG_LEVEL current_level)
message("Current log level: ${current_level}")

# 临时降低日志级别以减少输出噪音
cmake_language(SET_LOG_LEVEL WARNING)
# ... 执行一些噪音操作 ...
cmake_language(SET_LOG_LEVEL "${current_level}")  # 恢复
```

### 1.9 循环结构

CMake 提供了两种循环：`foreach()` 和 `while()`。

#### `foreach()` 的四种形式

```cmake
# 形式一：遍历显式列表
foreach(item IN ITEMS apple banana cherry)
    message("Item: ${item}")
endforeach()

# 形式二：遍历变量中的列表
set(my_list "alpha;beta;gamma")
foreach(item IN LISTS my_list)
    message("List item: ${item}")
endforeach()

# 形式三：数值范围
foreach(i RANGE 0 10 2)   # start stop [step]，默认 step=1
    message("i = ${i}")   # 0, 2, 4, 6, 8, 10
endforeach()

# RANGE 也可以只用 stop（从 0 开始）
foreach(i RANGE 5)
    message("i = ${i}")   # 0, 1, 2, 3, 4, 5
endforeach()

# 形式四：ZIP_LISTS (CMake 3.17+) —— 并行遍历多个列表
set(names   "Alice;Bob;Charlie")
set(scores  "95;87;92")
foreach(name score IN ZIP_LISTS names scores)
    message("${name} scored ${score}")
endforeach()
# 输出：
# Alice scored 95
# Bob scored 87
# Charlie scored 92
```

`ZIP_LISTS` 在处理平行数据时比手动索引访问更清晰、更不容易出错。

#### `while()` 循环

```cmake
set(counter 5)
while(counter GREATER 0)
    message("Countdown: ${counter}")
    math(EXPR counter "${counter} - 1")
endwhile()
```

#### `break()` 和 `continue()`

两个控制流命令行为与大多数语言一致，但在 `macro()` 和 `function()` 中有不同语义：

```cmake
macro(demo_break_in_macro)
    foreach(i RANGE 10)
        if(i EQUAL 3)
            break()    # 退出调用者作用域中的 foreach！
        endif()
        message("macro i = ${i}")
    endforeach()
endmacro()

foreach(i RANGE 10)
    demo_break_in_macro()
    message("outer i = ${i}")
endforeach()
# 上面这个循环只会打印 i=0：第一次调用 macro 时 break() 直接退出了外层的 foreach！
```

> [!DANGER]
> 在 `macro()` 中使用 `break()` 和 `continue()` 会穿透宏边界，直接作用于调用者所在的循环。这是宏文本替换机制的直接后果。**永远不要在宏中使用 `break()`/`continue()`，除非你确切知道调用者的控制流结构。**

### 1.10 条件判断：`if()`/`elseif()`/`else()`

CMake 的 `if()` 命令功能极其丰富，以下是最常用的分类：

#### 变量检查

```cmake
if(DEFINED VAR_NAME)        # 变量是否已定义（包括空字符串）
if(NOT DEFINED VAR_NAME)    # 未定义
if(VAR_NAME)                # 变量值非空、非 0、非 OFF、非 NO、非 FALSE、非 N、非 IGNORE、非 NOTFOUND
if(NOT VAR_NAME)            # 假值
```

#### 比较操作

```cmake
# 数字比较
if(value EQUAL 42)          # EQUAL, LESS, GREATER, LESS_EQUAL, GREATER_EQUAL

# 字符串比较
if(str STREQUAL "hello")    # STREQUAL, STRLESS, STRGREATER, STRLESS_EQUAL, STRGREATER_EQUAL

# 版本比较 (CMake 3.7+)
if(CMAKE_VERSION VERSION_GREATER_EQUAL "3.20")
if(CMAKE_VERSION VERSION_LESS "4.0")
```

#### 文件/路径判断

```cmake
if(EXISTS "/path/to/file")       # 文件或目录存在
if(IS_DIRECTORY "/path")         # 是目录
if(IS_SYMLINK "/path")           # 是符号链接
if(IS_ABSOLUTE "relative/path")  # 是绝对路径
```

#### 组合条件

```cmake
if((A AND B) OR (NOT C))
if(A STREQUAL "x" AND (B EQUAL 1 OR C EQUAL 2))
```

#### 逻辑真值表

这些值被视为假（false）：`0`、`OFF`、`NO`、`FALSE`、`N`、`IGNORE`、`NOTFOUND`、空字符串、以 `-NOTFOUND` 结尾的字符串。其他所有值被视为真。

> [!WARNING]
> `${未定义的变量}` 展开为空字符串，而空字符串是假值。因此 `if(MY_VAR)` 和 `if(NOT MY_VAR)` 对未定义变量都会给出**看似正确**的结果。但这是一种危险的默认行为——推荐使用 `if(DEFINED MY_VAR)` 先确认变量存在性，再判断真假。

### 1.11 `string()` 命令详解

`string()` 是 CMake 中功能最丰富的命令之一，提供了一套完整的字符串处理工具集。

#### 查找与替换

```cmake
# FIND：查找子串位置（返回索引，-1 表示未找到）
string(FIND "hello world" "world" pos)
# pos = 6

# REPLACE：替换所有匹配
string(REPLACE "foo" "bar" "foo.txt foo.c foo.h" result)
# result = "bar.txt bar.c bar.h"

# REGEX REPLACE：正则替换
string(REGEX REPLACE "([a-z]+)\\.([a-z]+)" "\\1_v2.\\2" "foo.txt bar.c" result)
# result = "foo_v2.txt bar_v2.c"

# REGEX MATCH：提取第一个匹配
string(REGEX MATCH "[0-9]+" "abc123def456" result)
# result = "123"

# REGEX MATCHALL：提取所有匹配（返回列表）
string(REGEX MATCHALL "[0-9]+" "abc123def456" result)
# result = "123;456"
```

#### 大小写与修剪

```cmake
string(TOUPPER "Hello World" result)    # "HELLO WORLD"
string(TOLOWER "Hello World" result)    # "hello world"
string(STRIP "  hello  " result)        # "hello"
```

#### 长度、子串与拼接

```cmake
string(LENGTH "hello" len)              # len = 5

# SUBSTRING：<input> <begin> <length>
string(SUBSTRING "abcdef" 2 3 result)   # result = "cde"
string(SUBSTRING "abcdef" 2 -1 result)  # result = "cdef"  (到末尾)

# CONCAT：连接多个字符串（CMake 3.12+）
string(CONCAT result "a" "b" "c")       # result = "abc"

# JOIN：用分隔符连接列表（CMake 3.12+）
string(JOIN "," "a;b;c" result)         # result = "a,b,c"
```

#### 比较

```cmake
string(COMPARE EQUAL "abc" "abc" result)  # result = TRUE
string(COMPARE LESS "abc" "abd" result)   # result = TRUE
# 操作符：EQUAL, NOTEQUAL, LESS, GREATER, LESS_EQUAL, GREATER_EQUAL
```

#### 其他实用操作

```cmake
# TIMESTAMP：获取格式化的时间戳（内置格式或自定义）
string(TIMESTAMP now "%Y-%m-%d %H:%M:%S")  # "2026-06-10 14:30:00"
string(TIMESTAMP now UTC)                    # UTC 时间

# JSON (CMake 3.19+)：JSON 字符串的获取、设置和验证
string(JSON data SET "address" "city" "\"Beijing\"")

# GENEX_STRIP：移除生成器表达式
string(GENEX_STRIP "$<1:hello>" result)
# result = "hello"（在非生成阶段上下文为空）
```

### 1.12 `list()` 命令详解

`list()` 操作分号分隔的列表。由于 CMake 中字符串本质上也是列表（分号分隔），理解 `list()` 对健壮的脚本至关重要。

#### 读取与长度

```cmake
list(LENGTH "a;b;c;d" len)              # len = 4
list(GET "a;b;c;d" 2 item)              # item = "c"
list(GET "a;b;c;d" 0 2 items)           # items = "a;c" （多索引）
```

#### 修改

```cmake
set(my_list "a;b;c")

list(APPEND my_list "d" "e")            # a;b;c;d;e
list(INSERT my_list 1 "x")              # a;x;b;c;d;e
list(PREPEND my_list "first")           # first;a;x;...     (CMake 3.15+)
list(POP_BACK my_list last)             # last = "e",       my_list = first;a;x;b;c;d
list(POP_FRONT my_list first)           # first = "first",  my_list = a;x;b;c;d
```

#### 删除

```cmake
list(REMOVE_ITEM my_list "b" "d")       # 按值删除所有匹配项
list(REMOVE_AT my_list 1)               # 按索引删除
list(REMOVE_DUPLICATES my_list)         # 去重（保留第一次出现）
```

#### 重排

```cmake
list(REVERSE my_list)                   # 反转
list(SORT my_list)                      # 字母/数字排序
# SORT 比较模式 (CMake 3.18+):
list(SORT my_list COMPARE NATURAL)      # 自然排序：file1, file2, file10
list(SORT my_list COMPARE CASE INSENSITIVE ORDER DESCENDING)
```

#### 过滤与转换

```cmake
# FILTER：包含/排除匹配正则的项 (CMake 3.6+)
list(FILTER my_list INCLUDE REGEX "^[A-Z]")     # 保留大写开头
list(FILTER my_list EXCLUDE REGEX "test")        # 排除包含 test 的项

# TRANSFORM：对每个元素执行操作 (CMake 3.12+)
list(TRANSFORM my_list APPEND ".cpp")             # 每项加后缀
list(TRANSFORM my_list PREPEND "src/")            # 每项加前缀
list(TRANSFORM my_list TOLOWER)                   # 每项转小写
list(TRANSFORM my_list STRIP)                     # 每项去除空白
list(TRANSFORM my_list REPLACE "legacy" "modern") # 每项替换
list(TRANSFORM my_list GENEX_STRIP)               # 每项剥除生成器表达式

# TRANSFORM 配合 AT 索引：
list(TRANSFORM my_list APPEND "_v2" AT 0 1)       # 仅第 0 和 1 项
```

> [!TIP]
> `list(TRANSFORM … PREPEND/APPEND)` 是替代循环手动构建路径的简洁方式。例如 `list(TRANSFORM sources PREPEND "${CMAKE_CURRENT_SOURCE_DIR}/")` 比 `foreach` 循环更清晰高效。

#### JOIN 与查找

```cmake
list(JOIN "a;b;c" " -- " result)        # result = "a -- b -- c"  (CMake 3.12+)
list(FIND "a;b;c" "b" idx)              # idx = 1（-1 表示未找到）
```

### 1.13 `file()` 命令详解

`file()` 提供文件系统操作——读取、写入、目录操作、文件搜索等。

#### 读取与写入

```cmake
# 读取文件全部内容到变量
file(READ "config.json" content)

# 读取为字符串（可限制长度和偏移）
file(READ "data.bin" binary_content HEX)           # 十六进制输出

# 写入内容（覆盖）
file(WRITE "output.txt" "Hello world\n")

# 追加内容
file(APPEND "log.txt" "[${now}] Build started\n")

# 读取文件为行列表
file(STRINGS "input.txt" lines)                     # 每行一个元素
file(STRINGS "input.txt" lines LENGTH_MINIMUM 1)    # 跳过空行
file(STRINGS "input.txt" lines REGEX "^#")          # 仅匹配正则的行
file(STRINGS "input.txt" lines ENCODING UTF-8)      # 指定编码
```

#### 文件搜索

```cmake
# GLOB：匹配文件（不递归）
file(GLOB sources "src/*.cpp" "src/*.h")

# GLOB_RECURSE：递归匹配
file(GLOB_RECURSE all_sources "src/**/*.cpp")

# GLOB 支持 CONFIGURE_DEPENDS (CMake 3.12+)：文件变化时自动重新配置
file(GLOB_RECURSE sources CONFIGURE_DEPENDS "src/*.cpp" "src/*.h")
```

> [!WARNING]
> `file(GLOB …)` 传统上被视为反模式，因为新增/删除源文件时 CMake 不会自动重新运行。但 `CONFIGURE_DEPENDS`（CMake 3.12+）缓解了这一问题——它让 CMake 在构建系统本身重新运行时（如 `make` 检测到需要重新配置）自动重新扫描文件。不过 Kitware 仍然建议显式列出源文件以确保可重复构建。

#### 目录操作

```cmake
file(MAKE_DIRECTORY "build/artifacts" "build/logs")

# 复制文件/目录
file(COPY "config/" DESTINATION "${CMAKE_BINARY_DIR}/config"
     FILES_MATCHING PATTERN "*.json" PATTERN "*.yaml"
     PATTERN "*.secret" EXCLUDE)

# 安装文件（类似 install()，但作用于配置阶段而非安装阶段）
file(INSTALL DESTINATION "${CMAKE_BINARY_DIR}/share"
     TYPE DATA
     FILES "README.md" "LICENSE")

# 重命名
file(RENAME "old_name.txt" "new_name.txt")

# 删除
file(REMOVE "temp.txt")
file(REMOVE_RECURSE "build/tmp")
```

#### 下载与时间

```cmake
# 下载文件 (CMake 3.12+)
file(DOWNLOAD "https://example.com/data.zip"
     "${CMAKE_BINARY_DIR}/data.zip"
     SHOW_PROGRESS
     EXPECTED_HASH SHA256=abc123...
     TIMEOUT 30)

# 获取文件时间戳
file(TIMESTAMP "main.cpp" mtime "%Y-%m-%d %H:%M:%S")

# TOUCH：创建空文件或更新时间戳
file(TOUCH "${CMAKE_BINARY_DIR}/.configured")
```

#### 其他实用操作

```cmake
# 获取文件大小
file(SIZE "data.bin" size_bytes)

# 计算文件的哈希值 (CMake 3.12+)
file(SHA256 "download.zip" hash)

# 读取符号链接目标
file(READ_SYMLINK "/usr/bin/python3" target)

# 获取运行时依赖 (Windows DLL 等)
file(GET_RUNTIME_DEPENDENCIES ...)  # 高级用法，见官方文档
```

### 1.14 `math()` —— 算术运算

CMake 支持整数算术。`math(EXPR …)` 是唯一的计算方式：

```cmake
set(a 10)
set(b 3)

math(EXPR sum "${a} + ${b}")            # sum = "13"
math(EXPR diff "${a} - ${b}")           # diff = "7"
math(EXPR prod "${a} * ${b}")           # prod = "30"
math(EXPR quot "${a} / ${b}")           # quot = "3"  （整数除法）
math(EXPR rem "${a} % ${b}")            # rem  = "1"

# 位运算
math(EXPR shifted "${a} << 2")          # 40 （左移）
math(EXPR masked "${a} & 3")            # 2  （按位与）

# 组合表达式
math(EXPR complex "(${a} + ${b}) * 2")  # 26

# 十六进制输入 (CMake 3.13+)
math(EXPR hex_sum "0xA + 0xB")          # 21

# 仅支持整数。所有运算结果也是整数。
```

> [!NOTE]
> CMake 没有原生浮点支持。需要浮点计算的场景，要么在生成阶段用生成器表达式，要么委托给外部脚本（Python/Shell）。

### 1.15 脚本模式：`cmake -P`

CMake 不仅是一个构建系统生成器——它还可以作为独立的脚本解释器运行：

```bash
cmake -P myscript.cmake
```

脚本模式下：

- **没有配置/生成阶段**：不执行 `project()`、不生成构建文件
- **`CMAKE_SOURCE_DIR` 和 `CMAKE_BINARY_DIR` 均为当前工作目录**
- **所有指令（`message()`、`file()`、`execute_process()` 等）仍然可用**
- **没有 target 相关命令**：`add_executable()`、`target_link_libraries()` 等在脚本模式下不可用

```cmake
# deploy.cmake — 一个部署脚本，通过 cmake -P deploy.cmake 运行
if(NOT DEFINED BUILD_DIR)
    message(FATAL_ERROR "BUILD_DIR is required: cmake -DBUILD_DIR=/path -P deploy.cmake")
endif()

message(STATUS "Deploying from ${BUILD_DIR}...")

file(COPY "${BUILD_DIR}/bin/" DESTINATION "/opt/myapp/bin/"
     FILES_MATCHING PATTERN "*.exe" PATTERN "*.dll")

file(INSTALL DESTINATION "/opt/myapp/etc/"
     TYPE DATA
     FILES "config/production.json")

message(STATUS "Deploy complete.")
```

脚本模式常用于：
- 构建后的部署/打包脚本
- 代码生成工具链
- 跨平台的自动化任务（替代 bash/batch 脚本）

---

## 2. 代码示例

### 2.1 函数 + `cmake_parse_arguments`：关键字风格 API

本示例展示如何封装一个具有清晰关键字接口的 target 配置函数。

**目录结构**：
```
example01/
  CMakeLists.txt
  main.cpp
```

**`main.cpp`**:
```cpp
#include <iostream>

int main() {
#ifdef MYLIB_STATIC
    std::cout << "Static build" << std::endl;
#endif
#ifdef MYLIB_HEADER_ONLY
    std::cout << "Header-only build" << std::endl;
#endif
    std::cout << "Version: " << MYLIB_VERSION << std::endl;
    return 0;
}
```

**`CMakeLists.txt`**:
```cmake
cmake_minimum_required(VERSION 3.24)
project(CMakeLanguageExample01 LANGUAGES CXX)

# ============================================================
# 定义一个带 cmake_parse_arguments 的函数
# ============================================================
function(add_versioned_library)
    set(options   STATIC HEADER_ONLY)
    set(oneValue  NAME VERSION NAMESPACE)
    set(multiValue PUBLIC_HEADERS PRIVATE_HEADERS SOURCES)

    cmake_parse_arguments(
        PARSE_ARGV 0
        LIB
        "${options}"
        "${oneValue}"
        "${multiValue}"
    )

    # 参数校验
    if(LIB_UNPARSED_ARGUMENTS)
        message(FATAL_ERROR "Unknown arguments: ${LIB_UNPARSED_ARGUMENTS}")
    endif()
    if(NOT LIB_NAME)
        message(FATAL_ERROR "NAME is required")
    endif()
    if(NOT LIB_VERSION)
        message(FATAL_ERROR "VERSION is required")
    endif()
    if(LIB_STATIC AND LIB_HEADER_ONLY)
        message(FATAL_ERROR "STATIC and HEADER_ONLY are mutually exclusive")
    endif()

    # 根据选项创建不同类型的 target
    if(LIB_HEADER_ONLY)
        add_library(${LIB_NAME} INTERFACE)
        target_compile_definitions(${LIB_NAME} INTERFACE MYLIB_HEADER_ONLY)
    elseif(LIB_STATIC)
        add_library(${LIB_NAME} STATIC ${LIB_SOURCES})
        target_compile_definitions(${LIB_NAME} PRIVATE MYLIB_STATIC)
    else()
        message(FATAL_ERROR "Must specify STATIC or HEADER_ONLY")
    endif()

    # 设置版本信息
    target_compile_definitions(${LIB_NAME} PRIVATE
        MYLIB_VERSION="${LIB_VERSION}"
    )

    # 设置别名
    if(LIB_NAMESPACE)
        add_library(${LIB_NAMESPACE}::${LIB_NAME} ALIAS ${LIB_NAME})
    endif()

    # 安装头文件
    if(LIB_PUBLIC_HEADERS)
        target_include_directories(${LIB_NAME} PUBLIC
            $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
            $<INSTALL_INTERFACE:include>
        )
    endif()

    message(STATUS "Library '${LIB_NAME}' v${LIB_VERSION} configured")
endfunction()

# ============================================================
# 使用示例
# ============================================================
add_versioned_library(
    NAME             mylib
    VERSION          1.2.3
    NAMESPACE        myorg
    HEADER_ONLY
    PUBLIC_HEADERS   include/mylib.h
    SOURCES          main.cpp
)

# 验证：HEADER_ONLY + SOURCES 实际上不会编译 SOURCES
# 但我们额外创建一个可执行文件来测试
add_executable(demo main.cpp)
target_link_libraries(demo PRIVATE mylib)
target_compile_definitions(demo PRIVATE MYLIB_VERSION="1.2.3" MYLIB_HEADER_ONLY)
```

**运行方式**：
```bash
mkdir build && cd build
cmake ..
cmake --build .
./demo
# 输出：
# Header-only build
# Version: 1.2.3
```

### 2.2 自定义 CMake 模块：Warnings 配置模块

本示例创建一个可复用的 `.cmake` 模块，用于根据编译器类型自动添加警告标志。

**目录结构**：
```
example02/
  CMakeLists.txt
  cmake/
    WarningHelpers.cmake
  main.cpp
```

**`main.cpp`**:
```cpp
#include <iostream>

int main() {
    int x = 1;
    int y = 2;
    // 如果有 -Wunused-variable，这里会触发警告
    int unused = x + y;
    std::cout << "x = " << x << std::endl;
    return 0;
}
```

**`cmake/WarningHelpers.cmake`**:
```cmake
# ============================================================
# WarningHelpers.cmake
# 提供跨编译器的警告标志管理
# ============================================================
include_guard(GLOBAL)

# -------------------------------------------------------------------
# 内部辅助：检测编译器类型并返回对应的警告标志
# -------------------------------------------------------------------
function(_get_compiler_warning_flags out_var)
    # MSVC 风格标志
    set(msvc_flags
        /W4          # 高警告级别
        /w14242      # 符号转换
        /w14254      # 无符号比较
        /w14263      # 成员函数隐藏
        /w14265      # 类大小比较
        /w14928      # 非法复制初始化
    )

    # GCC / Clang 风格标志
    set(gcc_flags
        -Wall
        -Wextra
        -Wpedantic
        -Wshadow
        -Wconversion
        -Wsign-conversion
        -Wnull-dereference
        -Wdouble-promotion
        -Wformat=2
        -Wimplicit-fallthrough
    )

    if(CMAKE_CXX_COMPILER_ID MATCHES "MSVC")
        set(${out_var} "${msvc_flags}" PARENT_SCOPE)
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
        set(${out_var} "${gcc_flags}" PARENT_SCOPE)
    else()
        message(WARNING "Unknown compiler: ${CMAKE_CXX_COMPILER_ID}. No warnings configured.")
        set(${out_var} "" PARENT_SCOPE)
    endif()
endfunction()

# -------------------------------------------------------------------
# 公开 API: enable_warnings(target [AS_ERRORS])
#
# 为目标添加推荐的警告标志。
# 如果指定 AS_ERRORS，则警告视为错误。
# -------------------------------------------------------------------
function(enable_warnings target)
    cmake_parse_arguments(WARN "AS_ERRORS" "" "" ${ARGN})

    _get_compiler_warning_flags(flags)

    if(NOT flags)
        return()
    endif()

    target_compile_options(${target} PRIVATE ${flags})

    if(WARN_AS_ERRORS)
        if(CMAKE_CXX_COMPILER_ID MATCHES "MSVC")
            target_compile_options(${target} PRIVATE /WX)
        else()
            target_compile_options(${target} PRIVATE -Werror)
        endif()
    endif()

    message(VERBOSE "Warnings enabled for ${target} (compiler: ${CMAKE_CXX_COMPILER_ID})")
endfunction()

# -------------------------------------------------------------------
# 公开 API: enable_warnings_for_all_targets()
#
# 遍历所有已定义的 target 并为其添加警告标志。
# 使用 cmake_language(DEFER) 确保在 directory scope 结束时执行。
# -------------------------------------------------------------------
macro(enable_warnings_for_all_targets)
    # DEFER 到目录作用域结束时才执行，确保所有 target 都已添加
    cmake_language(DEFER CALL _enable_warnings_deferred "${CMAKE_CURRENT_SOURCE_DIR}")
endmacro()

function(_enable_warnings_deferred scope_dir)
    message(STATUS "Configuring warnings for all targets in ${scope_dir}")

    # 遍历当前目录下所有 target
    # 使用 BUILDSYSTEM_TARGETS 属性 (CMake 3.7+)
    get_property(all_targets DIRECTORY "${scope_dir}" PROPERTY BUILDSYSTEM_TARGETS)

    foreach(t IN LISTS all_targets)
        # 跳过 IMPORTED 和 INTERFACE 库
        get_target_property(type ${t} TYPE)
        if(type STREQUAL "INTERFACE_LIBRARY" OR type STREQUAL "IMPORTED_LIBRARY")
            continue()
        endif()
        enable_warnings(${t})
    endforeach()
endfunction()
```

**`CMakeLists.txt`**:
```cmake
cmake_minimum_required(VERSION 3.24)
project(CMakeLanguageExample02 LANGUAGES CXX)

# 添加模块搜索路径
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")

# 包含自定义模块
include(WarningHelpers)

add_executable(demo main.cpp)
add_library(mylib STATIC main.cpp)

# 为单个 target 启用警告
enable_warnings(demo AS_ERRORS)

# 为所有 target 批量启用警告（使用 DEFER）
enable_warnings_for_all_targets()
```

**运行方式**：
```bash
mkdir build && cd build
cmake ..
cmake --build .
# 你应该能看到编译器产生的警告（如果 main.cpp 中有未使用变量等）
```

### 2.3 `cmake_language(DEFER)` + `cmake_language(EVAL)`

本示例演示延迟执行和动态代码求值的组合使用。

**目录结构**：
```
example03/
  CMakeLists.txt
  modules/
    alpha.cmake
    beta.cmake
    gamma.cmake
```

**`modules/alpha.cmake`**:
```cmake
include_guard(GLOBAL)
message(STATUS "  module alpha loaded")
function(configure_alpha)
    message(STATUS "    -> configuring alpha")
endfunction()
```

**`modules/beta.cmake`**:
```cmake
include_guard(GLOBAL)
message(STATUS "  module beta loaded")
function(configure_beta)
    message(STATUS "    -> configuring beta")
endfunction()
```

**`modules/gamma.cmake`**:
```cmake
include_guard(GLOBAL)
message(STATUS "  module gamma loaded")
function(configure_gamma)
    message(STATUS "    -> configuring gamma")
endfunction()
```

**`CMakeLists.txt`**:
```cmake
cmake_minimum_required(VERSION 3.24)
project(CMakeLanguageExample03 LANGUAGES NONE)

message(STATUS "=== Phase 1: Loading modules ===")

# 用于记录加载了哪些模块
set(_loaded_modules "")

set(module_dir "${CMAKE_SOURCE_DIR}/modules")

# 扫描并自动加载所有 .cmake 模块
file(GLOB module_files "${module_dir}/*.cmake")
foreach(mf IN LISTS module_files)
    get_filename_component(mod_name "${mf}" NAME_WLE)
    list(APPEND _loaded_modules "${mod_name}")
    include("${mf}")
endforeach()

message(STATUS "=== Phase 2: Scheduling deferred configuration ===")
message(STATUS "  Loaded modules: ${_loaded_modules}")

# ============================================================
# 核心技巧：使用 EVAL + DEFER 实现"模块感知"的延迟配置
# ============================================================
# 每个模块都有一个 configure_<name>() 函数。
# 我们在目录作用域结束时按需调用它们。

# 方案 A：逐个 DEFER（展示多个 DEFER 的 LIFO 顺序）
foreach(mod IN LISTS _loaded_modules)
    set(code "configure_${mod}()")
    message(STATUS "  Scheduling: ${code}")
    # 动态生成调用代码并通过 DEFER 延迟到目录结束时执行
    cmake_language(DEFER CALL _deferred_wrapper "${mod}" "${code}")
endforeach()

message(STATUS "=== Phase 3: Directory scope closing ===")
message(STATUS "  (DEFER calls will execute after this line)")

# -------------------------------------------------------------------
# DEFER 会调用的包装函数
# -------------------------------------------------------------------
function(_deferred_wrapper mod_name eval_code)
    message(STATUS "  [DEFERRED] Running config for ${mod_name}...")
    # 使用 EVAL 执行动态生成的代码
    cmake_language(EVAL CODE "${eval_code}")
    message(STATUS "  [DEFERRED] ${mod_name} config complete.")
endfunction()

# ============================================================
# 方案 B：直接使用 EVAL 在配置阶段动态调用
# ============================================================
message(STATUS "=== Bonus: Direct EVAL at configure time ===")
set(dynamic_target "beta")
cmake_language(EVAL CODE "configure_${dynamic_target}()")
```

**运行方式**：
```bash
mkdir build && cd build
cmake ..
```

**预期输出**（LIFO 顺序）:
```
=== Phase 1: Loading modules ===
  module alpha loaded
  module beta loaded
  module gamma loaded
=== Phase 2: Scheduling deferred configuration ===
  Loaded modules: alpha;beta;gamma
  Scheduling: configure_alpha()
  Scheduling: configure_beta()
  Scheduling: configure_gamma()
=== Phase 3: Directory scope closing ===
  (DEFER calls will execute after this line)
=== Bonus: Direct EVAL at configure time ===
    -> configuring beta
  [DEFERRED] Running config for gamma...
    -> configuring gamma
  [DEFERRED] gamma config complete.
  [DEFERRED] Running config for beta...
    -> configuring beta
  [DEFERRED] beta config complete.
  [DEFERRED] Running config for alpha...
    -> configuring alpha
  [DEFERRED] alpha config complete.
```

注意 DEFER 调用的执行顺序（gamma → beta → alpha）——这是因为多个 `cmake_language(DEFER CALL ...)` 按 **LIFO**（后进先出）顺序执行，而 Bonus 部分的直接 EVAL 在配置阶段即时执行（出现在 DEFER 之前）。

---

## 3. 练习

### 练习 1：编写带关键字参数的编译选项函数

编写一个函数 `add_compile_options_wrapper()`，使其支持如下调用方式：

```cmake
add_compile_options_wrapper(
    TARGETS           myapp mylib
    CXX_STANDARD      20
    OPTIMIZATION      O2
    WARNINGS_AS_ERRORS
    DEFINES           MY_DEBUG MY_TRACE=2
)
```

**要求**：
- 使用 `cmake_parse_arguments` 实现
- `TARGETS` 为必选参数，缺失时报错
- `CXX_STANDARD` 默认 17
- `OPTIMIZATION` 支持 `O0`/`O1`/`O2`/`O3`/`Os`/`Oz`，非法值时警告并跳过
- 处理 `_UNPARSED_ARGUMENTS` 未知参数

> [!TIP]- 参考实现思路
> 1. 定义 options / oneValue / multiValue
> 2. `cmake_parse_arguments(PARSE_ARGV 0 OPT …)` 解析
> 3. 检查 `OPT_UNPARSED_ARGUMENTS`
> 4. 遍历 `OPT_TARGETS`，对每个 target 调用 `target_compile_options` / `target_compile_features` / `target_compile_definitions`

### 练习 2：编写一个 `.cmake` 模块，根据编译器添加警告标志

创建一个 `cmake/CompilerWarnings.cmake` 模块，提供：

- `target_set_warnings(target <level>)` —— `level` 支持 `LOW`、`NORMAL`、`STRICT`、`PEDANTIC`
- 自动检测 MSVC / GCC / Clang
- 支持 `target_set_warnings(myapp NORMAL AS_ERRORS)` 将警告视为错误

**要求**：
- 使用 `include_guard(GLOBAL)`
- 在另一个 `CMakeLists.txt` 中通过 `include(CompilerWarnings)` 加载
- 最低需处理三个级别的警告标志

> [!TIP]- 参考实现思路
> 1. 在模块中定义 `target_set_warnings(target level)` 函数
> 2. 根据 `CMAKE_CXX_COMPILER_ID` 分支到不同编译器
> 3. 每个 level 维护独立的 flag 列表
> 4. 使用 `target_compile_options()` PRIVATE 设置

### 练习 3：使用 `cmake_language(EVAL)` 动态调用函数

假设有多个配置函数：`configure_core()`、`configure_network()`、`configure_ui()`。编写 CMake 代码实现：

- 从变量 `ENABLED_MODULES`（值为 `"core;network;ui"` 或子集）读取启用的模块列表
- 对每个启用的模块，动态调用对应的 `configure_<module>()` 函数
- 如果模块名对应的函数不存在（如尝试调用 `configure_unknown()`），使用 `if(COMMAND …)` 检查并跳过

**要求**：
- 使用 `cmake_language(EVAL CODE …)` 实现动态调用
- 使用 `if(COMMAND …)` 验证函数存在性
- 处理空 `ENABLED_MODULES` 的情况

> [!TIP]- 参考实现思路
> ```cmake
> foreach(mod IN LISTS ENABLED_MODULES)
>     set(func_name "configure_${mod}")
>     if(COMMAND ${func_name})
>         cmake_language(EVAL CODE "${func_name}()")
>     else()
>         message(WARNING "No such function: ${func_name}()")
>     endif()
> endforeach()
> ```


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **完整的 `add_compile_options_wrapper()` 函数：**
> ```cmake
> include_guard(GLOBAL)
>
> function(add_compile_options_wrapper)
>     set(options   WARNINGS_AS_ERRORS)
>     set(oneValue  CXX_STANDARD OPTIMIZATION)
>     set(multiValue TARGETS DEFINES)
>
>     cmake_parse_arguments(
>         PARSE_ARGV 0
>         OPT
>         "${options}"
>         "${oneValue}"
>         "${multiValue}"
>     )
>
>     # 检查必选参数
>     if(NOT OPT_TARGETS)
>         message(FATAL_ERROR "TARGETS is required")
>     endif()
>
>     # 检查未知参数
>     if(OPT_UNPARSED_ARGUMENTS)
>         message(FATAL_ERROR
>             "Unknown arguments: ${OPT_UNPARSED_ARGUMENTS}")
>     endif()
>
>     # 默认值
>     if(NOT OPT_CXX_STANDARD)
>         set(OPT_CXX_STANDARD 17)
>     endif()
>
>     # 验证 OPTIMIZATION
>     set(VALID_OPTS O0 O1 O2 O3 Os Oz)
>     if(OPT_OPTIMIZATION)
>         if(NOT OPT_OPTIMIZATION IN_LIST VALID_OPTS)
>             message(WARNING
>                 "Invalid OPTIMIZATION '${OPT_OPTIMIZATION}'. "
>                 "Valid: ${VALID_OPTS}. Skipping optimization flag.")
>             set(OPT_OPTIMIZATION "")
>         endif()
>     endif()
>
>     # 对每个 target 应用设置
>     foreach(target IN LISTS OPT_TARGETS)
>         if(NOT TARGET ${target})
>             message(WARNING "Target '${target}' does not exist, skipping")
>             continue()
>         endif()
>
>         # C++ 标准
>         target_compile_features(${target} PRIVATE cxx_std_${OPT_CXX_STANDARD})
>
>         # 优化级别
>         if(OPT_OPTIMIZATION)
>             target_compile_options(${target} PRIVATE -${OPT_OPTIMIZATION})
>         endif()
>
>         # 警告即错误
>         if(OPT_WARNINGS_AS_ERRORS)
>             target_compile_options(${target} PRIVATE
>                 $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Werror>
>                 $<$<CXX_COMPILER_ID:MSVC>:/WX>
>             )
>         endif()
>
>         # 宏定义
>         if(OPT_DEFINES)
>             target_compile_definitions(${target} PRIVATE ${OPT_DEFINES})
>         endif()
>     endforeach()
> endfunction()
> ```
>
> **使用示例：**
> ```cmake
> add_compile_options_wrapper(
>     TARGETS           myapp mylib
>     CXX_STANDARD      20
>     OPTIMIZATION      O2
>     WARNINGS_AS_ERRORS
>     DEFINES           MY_DEBUG MY_TRACE=2
> )
> ```

> [!tip]- 练习 2 参考答案
> **`cmake/CompilerWarnings.cmake`：**
> ```cmake
> include_guard(GLOBAL)
>
> function(target_set_warnings target level)
>     # 解析可选 AS_ERRORS 参数
>     set(options AS_ERRORS)
>     cmake_parse_arguments(PARSE_ARGV 1 WARN "${options}" "" "")
>     # Note: PARSE_ARGV 1 because target is ARGV0
>
>     if(WARN_UNPARSED_ARGUMENTS)
>         message(FATAL_ERROR
>             "Unknown arguments: ${WARN_UNPARSED_ARGUMENTS}")
>     endif()
>
>     # GCC/Clang 警告标志
>     set(GCC_LOW      -Wall)
>     set(GCC_NORMAL   -Wall -Wextra)
>     set(GCC_STRICT   -Wall -Wextra -Wpedantic -Wshadow -Wconversion)
>     set(GCC_PEDANTIC -Wall -Wextra -Wpedantic -Wshadow -Wconversion
>                      -Wsign-conversion -Wnull-dereference -Wdouble-promotion
>                      -Wformat=2 -Wimplicit-fallthrough)
>
>     # MSVC 警告标志
>     set(MSVC_LOW      /W3)
>     set(MSVC_NORMAL   /W4)
>     set(MSVC_STRICT   /W4 /permissive-)
>     set(MSVC_PEDANTIC /Wall /permissive-)
>
>     # 根据编译器选择标志
>     if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
>         set(_warnings ${GCC_${level}})
>         if(WARN_AS_ERRORS)
>             list(APPEND _warnings -Werror)
>         endif()
>     elseif(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
>         set(_warnings ${MSVC_${level}})
>         if(WARN_AS_ERRORS)
>             list(APPEND _warnings /WX)
>         endif()
>     else()
>         message(WARNING
>             "target_set_warnings: Unsupported compiler ${CMAKE_CXX_COMPILER_ID}")
>         return()
>     endif()
>
>     if(NOT _warnings)
>         message(WARNING "target_set_warnings: Unknown level '${level}'")
>         return()
>     endif()
>
>     target_compile_options(${target} PRIVATE ${_warnings})
>     message(STATUS "Warnings for ${target}: ${level} (${_warnings})")
> endfunction()
> ```
>
> **`CMakeLists.txt` 中使用：**
> ```cmake
> list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")
> include(CompilerWarnings)
>
> add_executable(my_app main.cpp)
> target_set_warnings(my_app NORMAL)
> target_set_warnings(my_app STRICT AS_ERRORS)
> ```

> [!tip]- 练习 3 参考答案
> **完整实现：**
> ```cmake
> # 模拟配置函数
> function(configure_core)
>     message(STATUS "Configuring core module...")
> endfunction()
>
> function(configure_network)
>     message(STATUS "Configuring network module...")
> endfunction()
>
> function(configure_ui)
>     message(STATUS "Configuring UI module...")
> endfunction()
>
> # 启用模块列表
> set(ENABLED_MODULES "core;network;ui")
> # 可以改为子集测试：set(ENABLED_MODULES "core;unknown;ui")
>
> # 动态调度
> if(NOT ENABLED_MODULES)
>     message(WARNING "ENABLED_MODULES is empty, nothing to configure")
> endif()
>
> foreach(mod IN LISTS ENABLED_MODULES)
>     set(func_name "configure_${mod}")
>     if(COMMAND ${func_name})
>         message(STATUS "Calling ${func_name}()")
>         cmake_language(EVAL CODE "${func_name}()")
>     else()
>         message(WARNING "No such function: ${func_name}()")
>     endif()
> endforeach()
> ```
>
> **预期输出：**
> ```
> -- Calling configure_core()
> -- Configuring core module...
> -- Calling configure_network()
> -- Configuring network module...
> -- Calling configure_ui()
> -- Configuring UI module...
> ```
>
> **换成 `set(ENABLED_MODULES "core;unknown;ui")` 后：**
> ```
> -- Calling configure_core()
> -- Configuring core module...
> CMake Warning: No such function: configure_unknown()
> -- Calling configure_ui()
> -- Configuring UI module...
> ```
>
> **关键点：** `if(COMMAND ...)` 在动态调用前验证函数存在性；`cmake_language(EVAL CODE ...)` 安全地执行动态构造的调用代码。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方文档: `cmake_language`](https://cmake.org/cmake/help/latest/command/cmake_language.html) —— 完整子命令列表与示例
- [CMake 官方文档: `cmake_parse_arguments`](https://cmake.org/cmake/help/latest/command/cmake_parse_arguments.html) —— 参数解析的完整语法
- [CMake 官方文档: `string`](https://cmake.org/cmake/help/latest/command/string.html) —— 全部 20+ 个子命令
- [Craig Scott: *Professional CMake* (第 14-17 章)](https://crascit.com/professional-cmake/) —— 函数、宏、模块的权威参考
- [[04-variables-cache-and-scope|04 变量、缓存与作用域]] —— 深入理解函数作用域
- [[09-find-package-and-find-modules|09 find_package 与 Find 模块]] —— 模块搜索的高级用法

---

## 5. 常见陷阱

### 陷阱 1：在需要作用域隔离时使用 `macro()`

```cmake
macro(bad_helper target)
    set(sources "main.cpp" "util.cpp")   # 污染调用者！
    target_sources(${target} PRIVATE ${sources})
endmacro()

set(sources "core.cpp")                  # 期望这只是 core
bad_helper(myapp)
# sources 现在是 "main.cpp;util.cpp" —— core.cpp 丢失了！
```

**修复**：使用 `function()` 替代，或至少给内部变量起独特的名字：

```cmake
function(good_helper target)
    set(_helper_sources "main.cpp" "util.cpp")  # 函数作用域，不泄漏
    target_sources(${target} PRIVATE ${_helper_sources})
endfunction()
```

### 陷阱 2：`cmake_parse_arguments` 不检查未知参数

```cmake
function(do_thing)
    set(oneValue NAME)
    cmake_parse_arguments(DO "" "${oneValue}" "" ${ARGN})
    # 调用者拼写错误: do_thing(NAEM "foo") → DO_NAME 为空，静默失败
endfunction()
```

**修复**：始终检查 `${prefix}_UNPARSED_ARGUMENTS`：

```cmake
if(DO_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "Unknown arguments: ${DO_UNPARSED_ARGUMENTS}")
endif()
```

### 陷阱 3：`file(GLOB ...)` 用于源文件列表

```cmake
file(GLOB sources "src/*.cpp")
add_executable(myapp ${sources})
# 问题：新增 .cpp 文件后，构建系统不会自动重新配置
```

**修复**：要么显式列出源文件，要么使用 `CONFIGURE_DEPENDS`：

```cmake
file(GLOB sources CONFIGURE_DEPENDS "src/*.cpp")
# 注意：CONFIGURE_DEPENDS 在 CMake 3.12+ 可用，
# 但 Kitware 仍建议显式列出源文件以保证可重现构建
```

### 陷阱 4：在 `macro()` 中使用 `break()`/`continue()`

```cmake
macro(find_and_break items)
    foreach(item IN LISTS items)
        if(item STREQUAL "target")
            message("Found: ${item}")
            break()   # ⚠️ 退出调用者中的 foreach，不仅是宏内的！
        endif()
    endforeach()
endmacro()

foreach(i RANGE 1 10)
    set(data "a;b;target;c")
    find_and_break("${data}")
    message("i = ${i}")
endforeach()
# 只输出 i = 0 —— 第一次调用 macro 时 break() 杀死了外部循环
```

### 陷阱 5：函数中 `${ARGN}` 被展开为列表

```cmake
function(broken)
    message("ARGN = ${ARGN}")       # 如果 ARGN 包含分号会丢失
    list(LENGTH ARGN len)           # 正确——但注意 ARGN 已展开
    foreach(arg IN LISTS ARGN)       # 正确方式
        message("  arg: ${arg}")
    endforeach()
endfunction()

broken("hello world" "foo;bar")
# ARGV0 = "hello world"
# ARGV1 = "foo"    ← "foo;bar" 被当作两个参数！
```

**修复**：传递带分号的值时必须使用双引号保护，或改用 bracket 参数。

### 陷阱 6：`cmake_parse_arguments` 使用 `PARSE_ARGV` 时忽略命名形参

```cmake
function(broken_func target)       # target 绑定了第一个实参
    cmake_parse_arguments(PARSE_ARGV 0 OPT ...)
    # PARSE_ARGV 0 从 ARGV0 开始解析
    # 但 target 形参已经消费了 ARGV0！此时 ARGV0 不存在！
endfunction()

broken_func(my_target OPTION_A)
# ARGV0 = "OPTION_A"（my_target 被 target 形参绑定了）
# cmake_parse_arguments 看到的是 "OPTION_A"，丢失了原来的 my_target
```

**修复**：如果使用命名形参，`PARSE_ARGV` 的偏移量必须相应调整；或者直接在函数体中使用 `ARGV` 变量而不是命名形参：

```cmake
function(fixed_func)               # 不声明命名形参
    cmake_parse_arguments(PARSE_ARGV 0 OPT ...)
    # 所有参数都在 ARGV0, ARGV1, ...
endfunction()
```

---

> **下一课**: [[18-configure-file-and-code-generation|18 configure_file 与代码生成]] —— 用 CMake 在构建前生成代码
