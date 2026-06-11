---
title: 变量、缓存与作用域
updated: 2026-06-10
tags: [cmake, variables, cache, scope]
---

# 变量、缓存与作用域

> 所属计划: [[cmake-deep-dive]]
> 预计耗时: 60min
> 前置知识: [[02-cmakelists-structure-and-commands]]

---

## 1. 概念讲解

CMake 的变量系统是整个构建系统的血管。理解变量的**类型**、**生命周期**和**可见性规则**是写出正确 CMake 脚本的前提。但 CMake 的变量模型与传统编程语言截然不同——它有一个跨构建持久化的缓存层，还有一套隐式的作用域父子关系。这些设计在 CMake 诞生的 2000 年代是合理的（为了减少重复配置），但在今天却成了最常见的困惑来源。

### 为什么需要这个？

在经典 `Makefile` 中，你每次 `make` 都会重新读取文件中的变量定义。如果要切换编译器，你需要编辑 `Makefile` 或导出环境变量。CMake 的做法不同：

- **配置阶段**（`cmake -B build`）读取所有变量、解析所有依赖关系，生成平台特定的构建文件（Ninja、Makefile、VS 解决方案）
- **构建阶段**直接使用这些生成的文件——CMake 本身不再参与

如果每次 `cmake --build build` 都要重新解析整个项目，大型 C++ 项目的配置时间将以分钟为单位增长。因此，CMake 将配置结果**持久化**到一个名为 `CMakeCache.txt` 的文件中。下次运行 `cmake` 时会先读取这个缓存，只对变化的部分重新计算。

这就引出了三类变量：普通变量、缓存变量、环境变量。它们各自有不同的生存周期和优先级。

### 核心思想

#### 三类变量

**普通变量 (Normal Variables)** — `set(MY_VAR "hello")`

- 生命周期：仅在当前作用域内有效（函数、目录或文件级别）
- 每次重新配置时都会从头计算
- 不会写入 `CMakeCache.txt`
- 用 `${MY_VAR}` 或 `"${MY_VAR}"` 取值

**缓存变量 (Cache Variables)** — `set(MY_VAR "hello" CACHE STRING "描述")`

- 生命周期：**跨构建持久化**——存储在 `CMakeCache.txt` 中，下次 `cmake` 时直接读取
- 这就是为什么你第一次配置后，再改 CMakeLists.txt 里 `set(...CACHE ...)` 的值不会生效——缓存已经存在了
- 命令行 `-DMY_VAR=VALUE` 本质上就是写缓存变量
- 用 `${MY_VAR}` 取值（和普通变量语法完全相同——这也是困惑的根源）

**环境变量 (Environment Variables)** — `$ENV{PATH}`

- 生命周期：继承自 shell 进程；仅配置阶段有效，不会持久化
- 用 `set(ENV{VAR} value)` 设置，`$ENV{VAR}` 读取
- 通常用于传递工具链路径、平台 SDK 位置

#### 缓存变量详解

缓存变量的定义语法：

```cmake
set(<variable> <value> CACHE <type> <docstring> [FORCE])
```

支持的 `<type>`：

| 类型 | 含义 | cmake-gui 表现 |
|------|------|---------------|
| `BOOL` | `ON`/`OFF` 开关 | 复选框 |
| `PATH` | 目录路径 | 目录选择器 |
| `FILEPATH` | 文件路径 | 文件选择器 |
| `STRING` | 任意字符串 | 文本输入框 |
| `INTERNAL` | 内部变量，GUI 中不可见 | 不显示 |

**缓存变量的优先级链**（从高到低）：

1. 命令行 `-DVAR=VALUE` — 最高优先级，覆盖一切
2. `CMakeCache.txt` 中已存在的值（除非用了 `FORCE`）
3. `set(VAR ... CACHE ...)` 默认值 — 仅在缓存中不存在此条目时写入
4. 同名普通变量的值 — 仅在特定读取情境中

> [!warning] 缓存变量与普通变量同名时的行为
> 当普通变量和缓存变量同名时，`${VAR}` 读到的是**普通变量**——只要普通变量存在。这是 CMake 的 "normal variable shadows cache variable" 规则。但 `$CACHE{VAR}` 总是读缓存值。详见下方陷阱部分。

**`option()` 命令**是 `set(... CACHE BOOL ...)` 的简写：

```cmake
option(ENABLE_TESTS "Build tests" ON)
# 等价于
set(ENABLE_TESTS ON CACHE BOOL "Build tests")
```

#### 作用域规则

CMake 的作用域是**基于目录的**，而不是基于词法的：

- 每个 `CMakeLists.txt` 是一个作用域
- **函数 `function()`** 创建全新的子作用域（类似大多数语言的函数作用域）
- **宏 `macro()`** 不创建新作用域——它直接在调用处展开（类似 C 预处理器宏）
- **`add_subdirectory()`** 创建子作用域——这是区别于传统语言的关键点
- **`include()`** 不创建新作用域——它在当前作用域中执行

> [!important] 关键认知
> `add_subdirectory(src)` 创建的 `src/CMakeLists.txt` 是一个**独立的子作用域**。子目录中定义的普通变量在父目录中不可见——除非使用 `set(... PARENT_SCOPE)`。

**`PARENT_SCOPE`** 把值"冒泡"到上一级作用域：

```cmake
# 在子目录 CMakeLists.txt 中
set(MY_RESULT "computed_value" PARENT_SCOPE)
# MY_RESULT 仅在父级作用域可见，当前作用域中不存在！
```

注意 `PARENT_SCOPE` 的一个微妙之处：设置了 `PARENT_SCOPE` 后，**当前作用域中并没有这个变量**。如果需要在当前作用域和父作用域中都可见，需要设置两次：

```cmake
set(MY_RESULT "value")              # 当前作用域
set(MY_RESULT "value" PARENT_SCOPE) # 父作用域
```

#### CMakeCache.txt

每次运行 `cmake -B build` 后，CMake 会在 build 目录生成 `CMakeCache.txt`。这个文件是纯文本格式，包含：

- 所有缓存变量的键值对（`VARIABLE_NAME:TYPE=value`）
- CMake 内部使用的生成器信息、编译器路径等

```text
//Build tests
ENABLE_TESTS:BOOL=ON

//C compiler
CMAKE_C_COMPILER:FILEPATH=/usr/bin/cc

//Build type
CMAKE_BUILD_TYPE:STRING=Debug
```

你可以在文本编辑器中打开它来审计当前缓存的变量。当出现诡异的配置问题时，**删除 `CMakeCache.txt`（或整个 build 目录）并重新运行 cmake 是合法且常用的调试手段**。

常用缓存操作：

- `cmake -DVAR=VALUE` — 设置/覆盖缓存变量
- `cmake -U 'pattern'` — 删除匹配 pattern 的缓存条目（glob 模式）
- `cmake -L[A][H]` — 列出缓存变量（`A`=高级变量也列出，`H`=帮助模式）

#### 生成器表达式 vs 变量

这是一个需要明确区分的概念：

| 方面 | 变量 `${VAR}` | 生成器表达式 `$<...>` |
|------|---------------|----------------------|
| 求值时机 | **配置阶段**（运行 CMake 时） | **生成阶段**（生成构建文件时） |
| 使用位置 | 几乎任何地方 | 仅特定 target 属性和命令中 |
| 能否访问 target 属性 | 不能 | 能（如 `$<TARGET_FILE:lib>`） |
| 跨配置感知 | 不能（配置阶段不知道构建配置） | 能（生成时知道 `Debug`/`Release`） |

简单原则：需要在 target 属性中引用其他 target 的信息时，用生成器表达式。其他时机优先用变量。

#### List（列表）处理

CMake 的列表是一个用分号分隔的字符串——这很"动态语言"：

```cmake
set(MY_LIST "a;b;c")    # 显式分号
set(MY_LIST a b c)       # 空格分隔，CMake 自动转成分号
```

> [!tip] 分号即分隔符
> CMake 中字符串和列表本质上是同一种类型——分号分隔的字符串。`set(VAR "a;b")` 在用 `${VAR}` 展开时会被当作列表，但双引号 `"${VAR}"` 会保留分号字面值。

`list()` 命令提供了丰富的列表操作：

- `list(APPEND lst elem...)` — 追加
- `list(PREPEND lst elem...)` — 前置（CMake 3.15+）
- `list(LENGTH lst out)` — 长度
- `list(GET lst index out)` — 按索引取值
- `list(JOIN lst glue out)` — 拼接（CMake 3.12+）
- `list(REMOVE_ITEM lst elem...)` — 移除
- `list(REMOVE_AT lst index...)` — 按索引移除
- `list(FILTER lst INCLUDE|EXCLUDE REGEX pattern)` — 过滤（CMake 3.6+）
- `list(TRANSFORM lst ...)` — 转换（CMake 3.12+）

遍历列表：

```cmake
foreach(item IN LISTS MY_LIST)
    message("${item}")
endforeach()
```

> [!warning] 引号陷阱
> `foreach(item IN LISTS MY_LIST)` 中 `MY_LIST` 不加 `${}`——这是 CMake 3.0+ 的推荐写法，避免值中有分号时的意外展开。老的 `foreach(item ${MY_LIST})` 写法在值含分号时行为正确，但 `foreach(item IN LISTS ...)` 更明确、更安全。

---

## 2. 代码示例

### 示例 1：缓存变量类型及跨运行行为

本示例演示：
- 各种缓存类型的定义与使用
- 缓存跨配置运行的持久化
- `FORCE` 覆盖已有缓存值
- `cmake -DVAR=VALUE` 命令行覆盖

**目录结构：**

```text
ex01-cache-types/
├── CMakeLists.txt
└── build/          # 构建目录（需手动创建）
```

**CMakeLists.txt：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(CacheTypeDemo VERSION 1.0)

# ---- 缓存变量定义 ----
# 这些 set(... CACHE ...) 只有缓存中不存在时才写入
set(MY_BOOL   ON  CACHE BOOL     "A boolean switch")
set(MY_PATH   "/usr/local" CACHE PATH     "An installation path")
set(MY_FILE   "notfound.txt" CACHE FILEPATH "A file location")
set(MY_STRING "default"   CACHE STRING   "A string value")
set(MY_HIDDEN "internal"  CACHE INTERNAL "Not shown in GUI")

# ---- 演示 option() 等价 ----
option(ENABLE_FEATURE "Enable the fancy feature" OFF)

# ---- 打印当前缓存值 ----
message(STATUS "========== Cache Values ==========")
message(STATUS "MY_BOOL         = ${MY_BOOL}")
message(STATUS "MY_PATH         = ${MY_PATH}")
message(STATUS "MY_FILE         = ${MY_FILE}")
message(STATUS "MY_STRING       = ${MY_STRING}")
message(STATUS "MY_HIDDEN       = ${MY_HIDDEN}")
message(STATUS "ENABLE_FEATURE  = ${ENABLE_FEATURE}")

# ---- 只有缓存未设置时才写入 ----
set(LAZY_DEFAULT "first_run_only" CACHE STRING "Only set on first configure")
message(STATUS "LAZY_DEFAULT    = ${LAZY_DEFAULT}")

# ---- FORCE 总是覆盖缓存 ----
set(FORCED_VALUE "forced_value" CACHE STRING "Always overwritten" FORCE)
message(STATUS "FORCED_VALUE    = ${FORCED_VALUE}")
```

**运行方式：**

```bash
# 第一次配置
cmake -S ex01-cache-types -B ex01-cache-types/build
# 观察输出：MY_STRING = default

# 第二次配置（不删除缓存）
cmake -S ex01-cache-types -B ex01-cache-types/build
# 观察输出：MY_STRING 仍然是 default

# 用命令行覆盖缓存
cmake -S ex01-cache-types -B ex01-cache-types/build -DMY_STRING="from_cli"
# 观察输出：MY_STRING = from_cli

# 查看所有缓存变量
cmake -S ex01-cache-types -B ex01-cache-types/build -L

# 查看高级缓存变量
cmake -S ex01-cache-types -B ex01-cache-types/build -LAH

# 删除特定缓存条目
cmake -S ex01-cache-types -B ex01-cache-types/build -U 'MY_*'

# 删除整个缓存
rm -rf ex01-cache-types/build
```

**预期输出（第一次配置）：**

```text
-- ========== Cache Values ==========
-- MY_BOOL         = ON
-- MY_PATH         = /usr/local
-- MY_FILE         = notfound.txt
-- MY_STRING       = default
-- MY_HIDDEN       = internal
-- ENABLE_FEATURE  = OFF
-- LAZY_DEFAULT    = first_run_only
-- FORCED_VALUE    = forced_value
-- Configuring done
```

**预期输出（用 -D 覆盖后再次配置）：**

```text
-- MY_STRING       = from_cli
-- LAZY_DEFAULT    = first_run_only   # 仍保留缓存中的旧值
-- FORCED_VALUE    = forced_value     # FORCE 每次都覆盖
```

---

### 示例 2：作用域演示——父子目录变量可见性

本示例演示：
- `add_subdirectory()` 创建子作用域
- 普通变量在子目录中不可见于父目录
- `PARENT_SCOPE` 向上传递变量
- 函数中的 `PARENT_SCOPE`
- 缓存变量在作用域之间共享

**目录结构：**

```text
ex02-scope/
├── CMakeLists.txt        # 父作用域
├── child/
│   └── CMakeLists.txt    # 子作用域
└── build/
```

**父 CMakeLists.txt：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(ScopeDemo VERSION 1.0)

message(STATUS "===== Parent Scope =====")

# 父作用域定义变量
set(PARENT_VAR "I am the parent")
message(STATUS "Before add_subdirectory: PARENT_VAR   = ${PARENT_VAR}")
message(STATUS "Before add_subdirectory: CHILD_VAR    = ${CHILD_VAR}")
message(STATUS "Before add_subdirectory: BUBBLED_VAR  = ${BUBBLED_VAR}")
message(STATUS "Before add_subdirectory: BOTH_VAR     = ${BOTH_VAR}")

add_subdirectory(child)

message(STATUS "===== Back in Parent Scope =====")
message(STATUS "After add_subdirectory:  PARENT_VAR   = ${PARENT_VAR}")
message(STATUS "After add_subdirectory:  CHILD_VAR    = ${CHILD_VAR}")
message(STATUS "After add_subdirectory:  BUBBLED_VAR  = ${BUBBLED_VAR}")
message(STATUS "After add_subdirectory:  BOTH_VAR     = ${BOTH_VAR}")

# 缓存变量在所有作用域可见
message(STATUS "After add_subdirectory:  SHARED_CACHE = ${SHARED_CACHE}")

# ---- 函数作用域 ----
function(inner_func)
    set(FUNC_VAR "inside function")
    message(STATUS "Inside function:         FUNC_VAR     = ${FUNC_VAR}")
    message(STATUS "Inside function:         PARENT_VAR   = ${PARENT_VAR}")
    set(RESULT "computed" PARENT_SCOPE)
    # 注意：当前函数内 RESULT 为空！
    message(STATUS "Inside function:         RESULT       = ${RESULT}")
endfunction()

inner_func()
message(STATUS "After function call:     RESULT       = ${RESULT}")
```

**子目录 child/CMakeLists.txt：**

```cmake
message(STATUS "===== Child Scope =====")

# 子作用域可以读取父作用域的变量
message(STATUS "Inside child:            PARENT_VAR   = ${PARENT_VAR}")

# 子作用域定义自己的变量
set(CHILD_VAR "I am the child")

# 设置 PARENT_SCOPE 将变量传给父作用域
set(BUBBLED_VAR "I bubbled up" PARENT_SCOPE)
# 注意：BUBBLED_VAR 在当前子作用域中不存在！
message(STATUS "Inside child:            BUBBLED_VAR  = ${BUBBLED_VAR}")

# 如果想父子都可用，需要设两次
set(BOTH_VAR "both scopes")
set(BOTH_VAR "both scopes" PARENT_SCOPE)
message(STATUS "Inside child:            BOTH_VAR     = ${BOTH_VAR}")

# 缓存变量在所有作用域共享
set(SHARED_CACHE "visible everywhere" CACHE STRING "Shared cache var")
```

**运行方式：**

```bash
cmake -S ex02-scope -B ex02-scope/build
```

**预期输出：**

```text
-- ===== Parent Scope =====
-- Before add_subdirectory: PARENT_VAR   = I am the parent
-- Before add_subdirectory: CHILD_VAR    =           # 空——还没定义
-- Before add_subdirectory: BUBBLED_VAR  =           # 空
-- Before add_subdirectory: BOTH_VAR     =           # 空
-- ===== Child Scope =====
-- Inside child:            PARENT_VAR   = I am the parent
-- Inside child:            BUBBLED_VAR  =           # 空！PARENT_SCOPE 不留在子作用域
-- Inside child:            BOTH_VAR     = both scopes  # 设了两次，子作用域也有
-- ===== Back in Parent Scope =====
-- After add_subdirectory:  PARENT_VAR   = I am the parent
-- After add_subdirectory:  CHILD_VAR    =           # 空！子作用域的变量不可见
-- After add_subdirectory:  BUBBLED_VAR  = I bubbled up  # PARENT_SCOPE 成功
-- After add_subdirectory:  BOTH_VAR     = both scopes    # 父子都有
-- After add_subdirectory:  SHARED_CACHE = visible everywhere
-- Inside function:         FUNC_VAR     = inside function
-- Inside function:         PARENT_VAR   = I am the parent
-- Inside function:         RESULT       =           # PARENT_SCOPE 不留在当前作用域
-- After function call:     RESULT       = computed
-- Configuring done
```

---

### 示例 3：列表操作——创建、追加、过滤、遍历

本示例演示：
- 列表的多种创建方式
- `list()` 命令常用子命令
- `foreach(IN LISTS)` 遍历
- 列表去重
- 列表的嵌套与展平

**目录结构：**

```text
ex03-lists/
├── CMakeLists.txt
└── build/
```

**CMakeLists.txt：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(ListDemo VERSION 1.0)

message(STATUS "===== 1. 创建列表 =====")

# 多种等价写法
set(LIST_A "a;b;c")           # 分号分隔
set(LIST_B a b c)              # 空格分隔（自动转分号）
set(LIST_C "a" "b" "c")       # 多参数
message(STATUS "LIST_A = ${LIST_A}")
message(STATUS "LIST_B = ${LIST_B}")
message(STATUS "LIST_C = ${LIST_C}")

message(STATUS "===== 2. 列表操作 =====")

set(FRUITS apple banana cherry)
list(LENGTH FRUITS len)
message(STATUS "Length: ${len}")   # 3

list(APPEND FRUITS dragonfruit elderberry)
message(STATUS "After APPEND:  ${FRUITS}")

list(PREPEND FRUITS apricot)   # CMake 3.15+
message(STATUS "After PREPEND: ${FRUITS}")

list(GET FRUITS 2 third)
message(STATUS "Index 2: ${third}")  # banana

list(JOIN FRUITS ", " joined)
message(STATUS "Joined: ${joined}")

list(REMOVE_AT FRUITS 0)
message(STATUS "After REMOVE_AT 0: ${FRUITS}")

list(REMOVE_ITEM FRUITS cherry banana)
message(STATUS "After REMOVE_ITEM: ${FRUITS}")

message(STATUS "===== 3. 过滤列表 =====")

set(MIXED aa bb_skip cc dd_skip ee)
list(FILTER MIXED EXCLUDE REGEX ".*_skip$")
message(STATUS "Filtered (no _skip): ${MIXED}")  # aa;cc;ee

message(STATUS "===== 4. 去重 =====")

set(DUP a b a c b d)
# CMake 3.15+ 可以用 REMOVE_DUPLICATES
list(REMOVE_DUPLICATES DUP)
message(STATUS "Deduplicated: ${DUP}")  # a;b;c;d

message(STATUS "===== 5. foreach 遍历 =====")

set(SOURCES main.cpp utils.cpp logger.cpp network.cpp)

foreach(src IN LISTS SOURCES)
    message(STATUS "  Compiling: ${src}")

    # 条件判断
    if(src MATCHES "network")
        message(STATUS "    -> Network module detected")
    endif()
endforeach()

message(STATUS "===== 6. foreach 带索引 =====")

set(CMAKE_LIST_INDEX_ENABLE ON)   # CMake 3.11+ 需显式开启
foreach(src IN LISTS SOURCES)
    math(EXPR idx "${CMAKE_LIST_INDEX} + 1")
    message(STATUS "  [${idx}/${len}] ${src}")
endforeach()

message(STATUS "===== 7. 列表复制与嵌套 =====")

set(ORIGINAL alpha beta gamma)
set(COPY ${ORIGINAL})            # 值拷贝
list(APPEND COPY delta)
message(STATUS "ORIGINAL: ${ORIGINAL}")  # alpha;beta;gamma（未变）
message(STATUS "COPY:     ${COPY}")      # alpha;beta;gamma;delta

# 嵌套列表——用引号保护分号
set(INNER "x;y;z")
set(OUTER "${INNER}" more items) # 引号保护 INNER 中的分号
message(STATUS "OUTER: ${OUTER}") # x;y;z;more;items
```

**运行方式：**

```bash
cmake -S ex03-lists -B ex03-lists/build
```

**预期输出：**

```text
-- ===== 1. 创建列表 =====
-- LIST_A = a;b;c
-- LIST_B = a;b;c
-- LIST_C = a;b;c
-- ===== 2. 列表操作 =====
-- Length: 3
-- After APPEND:  apple;banana;cherry;dragonfruit;elderberry
-- After PREPEND: apricot;apple;banana;cherry;dragonfruit;elderberry
-- Index 2: banana
-- Joined: apricot, apple, banana, cherry, dragonfruit, elderberry
-- After REMOVE_AT 0: apple;banana;cherry;dragonfruit;elderberry
-- After REMOVE_ITEM: apple;dragonfruit;elderberry
-- ===== 3. 过滤列表 =====
-- Filtered (no _skip): aa;cc;ee
-- ===== 4. 去重 =====
-- Deduplicated: a;b;c;d
-- ===== 5. foreach 遍历 =====
--   Compiling: main.cpp
--   Compiling: utils.cpp
--   Compiling: logger.cpp
--   Compiling: network.cpp
--     -> Network module detected
-- ===== 6. foreach 带索引 =====
--   [1/4] main.cpp
--   [2/4] utils.cpp
--   [3/4] logger.cpp
--   [4/4] network.cpp
-- ===== 7. 列表复制与嵌套 =====
-- ORIGINAL: alpha;beta;gamma
-- COPY:     alpha;beta;gamma;delta
-- OUTER: x;y;z;more;items
```

---

## 3. 练习

### 练习 1：用 `option()` 控制构建行为

创建一个项目，包含一个 `option()` 缓存变量 `ENABLE_LOGGING`（默认 `ON`）。当 `ENABLE_LOGGING=ON` 时，添加一个 `logger.cpp` 到 target，并定义编译宏 `LOGGING_ENABLED`。当 `OFF` 时，跳过 `logger.cpp` 且不定义该宏。

**要求：**

- 使用 `option()` 定义缓存变量
- 用 `target_sources()` 条件添加源文件
- 用 `target_compile_definitions()` 条件定义宏
- 写一个简单的 `main.cpp` 用 `#ifdef LOGGING_ENABLED` 打印不同消息
- 验证 `-DENABLE_LOGGING=OFF` 后重新配置，缓存持久化生效

### 练习 2：PARENT_SCOPE 向上传递计算结果

创建一个父目录和子目录结构。在子目录中扫描并统计源文件数量，用 `PARENT_SCOPE` 将计数和文件列表传回父目录，父目录打印这些信息。

**要求：**

- 子目录 `src/` 有多个 `.cpp` 文件
- 子目录用 `file(GLOB ...)` 收集源文件
- 用 `PARENT_SCOPE` 传递 `SRC_COUNT` 和 `SRC_FILES` 到父作用域
- 注意理解 `PARENT_SCOPE` 不会在当前作用域创建变量的行为
- 在子目录中验证：`${SRC_COUNT}` 是否为空（确认 PARENT_SCOPE 语义）

### 练习 3：列表操作——构建并过滤源文件列表

编写一个 CMakeLists.txt，完成以下列表操作：

1. 创建初始源文件列表：`main.cpp server.cpp client.cpp utils.cpp`
2. 追加 `logger.cpp` 和 `config.cpp`
3. 移除 `server.cpp`
4. 过滤出所有包含 `er` 的文件名
5. 为每个过滤后的文件生成一个对应的 `.o` 目标文件名（用 `string(REPLACE ...)` 或 `list(TRANSFORM ...)`）
6. 用 `foreach(IN LISTS)` 遍历并打印原始列表和最终列表

**要求：**

- 使用 `list()` 的所有必要子命令
- 使用 `foreach(IN LISTS ...)` 而非老式 `foreach(item ${LIST})`
- 使用 `message()` 在每一步后打印结果以验证正确性


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(LoggingDemo VERSION 1.0 LANGUAGES CXX)
>
> option(ENABLE_LOGGING "Enable logging support" ON)
>
> add_executable(logger_app)
> target_sources(logger_app PRIVATE main.cpp)
>
> if(ENABLE_LOGGING)
>     target_sources(logger_app PRIVATE logger.cpp)
>     target_compile_definitions(logger_app PRIVATE LOGGING_ENABLED)
>     message(STATUS "Logging: ENABLED")
> else()
>     message(STATUS "Logging: DISABLED")
> endif()
> ```
>
> **`main.cpp`：**
> ```cpp
> #include <iostream>
>
> #ifdef LOGGING_ENABLED
> void log_message(const char* msg);  // 声明在 logger.cpp 中
> #endif
>
> int main() {
> #ifdef LOGGING_ENABLED
>     log_message("Application started with logging enabled.");
>     std::cout << "[LOG] Logging is ON" << std::endl;
> #else
>     std::cout << "Logging is disabled." << std::endl;
> #endif
>     return 0;
> }
> ```
>
> **`logger.cpp`：**
> ```cpp
> #include <iostream>
>
> void log_message(const char* msg) {
>     std::cout << "[LOG] " << msg << std::endl;
> }
> ```
>
> **验证缓存持久化：**
> ```bash
> cmake -B build                          # ENABLE_LOGGING=ON
> cmake --build build && ./build/logger_app
> # 输出: [LOG] Application started with logging enabled.
>
> cmake -B build -DENABLE_LOGGING=OFF     # 覆盖缓存
> cmake --build build && ./build/logger_app
> # 输出: Logging is disabled.
>
> cmake -B build                          # 缓存保留 OFF
> cmake --build build && ./build/logger_app
> # 输出: Logging is disabled.（缓存持久化生效）
> ```

> [!tip]- 练习 2 参考答案
> **顶层 `CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(ScopeDemo VERSION 1.0 LANGUAGES CXX)
>
> add_subdirectory(src)
>
> message(STATUS "Parent: SRC_COUNT = ${SRC_COUNT}")
> message(STATUS "Parent: SRC_FILES = ${SRC_FILES}")
>
> add_executable(my_app)
> target_sources(my_app PRIVATE ${SRC_FILES})
> ```
>
> **`src/CMakeLists.txt`：**
> ```cmake
> # 扫描源文件
> file(GLOB SRC_FILES_LIST "${CMAKE_CURRENT_SOURCE_DIR}/*.cpp")
> list(LENGTH SRC_FILES_LIST SRC_COUNT_VAL)
>
> # 传回父作用域（注意：当前作用域不会创建这些变量）
> set(SRC_COUNT "${SRC_COUNT_VAL}" PARENT_SCOPE)
> set(SRC_FILES "${SRC_FILES_LIST}" PARENT_SCOPE)
>
> # 验证：当前作用域中不存在（会输出空字符串）
> message(STATUS "Child: SRC_COUNT = '${SRC_COUNT}'")
> message(STATUS "Child: SRC_FILES = '${SRC_FILES}'")
> ```
>
> **关键验证：** 子目录中 `message` 输出的 `SRC_COUNT` 为空（因为 `PARENT_SCOPE` 只影响父作用域），而父目录中输出正确的计数和文件列表。这确认了 `PARENT_SCOPE` 的语义。

> [!tip]- 练习 3 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(ListDemo VERSION 1.0 LANGUAGES NONE)
>
> # 1. 创建初始列表
> set(SRC_FILES main.cpp server.cpp client.cpp utils.cpp)
> message(STATUS "1. Initial:    ${SRC_FILES}")
>
> # 2. 追加
> list(APPEND SRC_FILES logger.cpp config.cpp)
> message(STATUS "2. After append: ${SRC_FILES}")
>
> # 3. 移除
> list(REMOVE_ITEM SRC_FILES server.cpp)
> message(STATUS "3. After remove: ${SRC_FILES}")
>
> # 4. 过滤出含 "er" 的文件
> list(FILTER SRC_FILES INCLUDE REGEX "er")
> message(STATUS "4. Filtered:    ${SRC_FILES}")
>
> # 5. 转换为 .o 目标文件名
> set(OBJ_FILES "${SRC_FILES}")  # 先拷贝
> list(TRANSFORM OBJ_FILES REPLACE "\.cpp$" ".o")
> message(STATUS "5. Object files: ${OBJ_FILES}")
>
> # 6. 遍历打印（推荐语法）
> message(STATUS "6. Source files:")
> foreach(file IN LISTS SRC_FILES)
>     message(STATUS "   - ${file}")
> endforeach()
>
> message(STATUS "6. Object files:")
> foreach(file IN LISTS OBJ_FILES)
>     message(STATUS "   - ${file}")
> endforeach()
> ```
>
> **预期输出：**
> ```
> -- 1. Initial:    main.cpp;server.cpp;client.cpp;utils.cpp
> -- 2. After append: main.cpp;server.cpp;client.cpp;utils.cpp;logger.cpp;config.cpp
> -- 3. After remove: main.cpp;client.cpp;utils.cpp;logger.cpp;config.cpp
> -- 4. Filtered:    client.cpp;logger.cpp;config.cpp
> -- 5. Object files: client.o;logger.o;config.o
> -- 6. Source files:
> --    - client.cpp
> --    - logger.cpp
> --    - config.cpp
> -- 6. Object files:
> --    - client.o
> --    - logger.o
> --    - config.o
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方文档: set()](https://cmake.org/cmake/help/latest/command/set.html) — `set()` 命令的完整参考，包括所有缓存类型
- [CMake 官方文档: list()](https://cmake.org/cmake/help/latest/command/list.html) — 所有列表子命令
- [CMake 官方文档: option()](https://cmake.org/cmake/help/latest/command/option.html) — `option()` 命令
- [CMake 官方文档: cmake-language(7) — Variables](https://cmake.org/cmake/help/latest/manual/cmake-language.7.html#variables) — CMake 语言规范中的变量章节
- [Craig Scott: Professional CMake (第 5 章: Variables)](https://crascit.com/professional-cmake/) — 本书对变量系统的深入讲解
- [Kitware CMake 教程: Variables Explained](https://gitlab.kitware.com/cmake/community/-/wikis/doc/cmake/Variables-Explained) — Kitware 社区的变量解释
- [Stack Overflow: CMake variable shadowing](https://stackoverflow.com/questions/31090821/) — 社区对变量遮蔽问题的讨论
- [[08-generator-expressions]] — 下一阶段深入生成器表达式

---

## 常见陷阱

### 陷阱 1：缓存变量遮蔽普通变量

```cmake
set(MY_VAR "normal")
set(MY_VAR "cached" CACHE STRING "doc")

message("${MY_VAR}")  # 输出: normal  — 普通变量遮蔽了缓存变量！
```

**原因：** 当普通变量存在时，`${VAR}` 优先读取普通变量。只有普通变量不存在时，才回退到缓存变量。

**解决：** 用 `$CACHE{VAR}` 显式读取缓存，或避免同名。更好的做法——用 `option()` 或明确的命名约定区分缓存变量。

### 陷阱 2：修改 CMakeLists.txt 中的缓存默认值不生效

```cmake
# 第一次配置时
set(MY_VAR "v1" CACHE STRING "doc")

# 修改 CMakeLists.txt 后第二次配置
set(MY_VAR "v2" CACHE STRING "doc")  # 仍然是 "v1"！
```

**原因：** 缓存中已有 `MY_VAR=v1`，`set(...CACHE...)` 不会覆盖已有值。

**解决：**
- 用 `set(MY_VAR "v2" CACHE STRING "doc" FORCE)` 强制覆盖
- 或者删除 `CMakeCache.txt`（或整个 build 目录）后重新配置
- 或者用 `cmake -UMY_VAR` 删除该缓存条目再配置

### 陷阱 3：忘记 `add_subdirectory()` 创建新作用域

```cmake
# 子目录 CMakeLists.txt
set(MY_LIB_SOURCES foo.cpp bar.cpp)

# 父目录 CMakeLists.txt
add_subdirectory(src)
add_library(mylib ${MY_LIB_SOURCES})  # 报错：MY_LIB_SOURCES 为空！
```

**原因：** `add_subdirectory()` 创建子作用域，子目录中定义的普通变量在父目录不可见。

**解决：** 在子目录中用 `set(MY_LIB_SOURCES ... PARENT_SCOPE)`，或把变量定义为缓存变量，或把逻辑放在父目录中。

### 陷阱 4：`PARENT_SCOPE` 不在当前作用域设值

```cmake
function(compute)
    set(RESULT "done" PARENT_SCOPE)
    message("Inside: ${RESULT}")  # 输出为空！
endfunction()

compute()
message("Outside: ${RESULT}")     # 输出: done
```

**原因：** `PARENT_SCOPE` 只影响父作用域，当前作用域不创建该变量。

**解决：** 如果需要在当前作用域中也使用，设置两次：

```cmake
set(RESULT "done")
set(RESULT "done" PARENT_SCOPE)
```

### 陷阱 5：列表中的分号被意外展开

```cmake
set(FLAGS "-Wall;-Wextra;-Werror")
add_compile_options(${FLAGS})    # 正确：分号分隔为三个选项

set(FLAGS2 "${FLAGS}")           # 引号保护，FLAGS2 = "-Wall;-Wextra;-Werror" 作为一个字符串
add_compile_options("${FLAGS2}") # 错误：整个字符串当成一个选项
```

**原因：** 双引号包裹 `"${VAR}"` 会保留分号字面值，不会展开为列表。

**解决：** 传递列表类型参数时，**不要**给变量加引号；传递字符串参数时，才用引号保护。

### 陷阱 6：cmake-gui 中 `INTERNAL` 变量不可见导致难以调试

`set(... CACHE INTERNAL ...)` 类型的变量在 cmake-gui 和 `cmake -L` 中默认不显示，只有 `-LAH` 才列出。如果过度使用 `INTERNAL`，调试时很难定位问题。

**建议：** 优先用 `STRING` 或 `BOOL`，仅在确实需要隐藏内部实现细节时使用 `INTERNAL`。可以用 `mark_as_advanced(MY_VAR)` 让 GUI 默认隐藏但调试时仍可见。

### 陷阱 7：`foreach(item ${LIST})` 中的引号行为

```cmake
set(LIST a b c)
foreach(item ${LIST})          # 正确：展开为三个元素
foreach(item "${LIST}")        # 错误：当成一个元素 "a;b;c"
foreach(item IN LISTS LIST)    # 推荐：CMake 3.0+，语义明确
```

**建议：** 始终使用 `foreach(item IN LISTS VAR_NAME)` 语法——`VAR_NAME` 不加 `${}`，这是 CMake 3.0 引入的更安全的遍历方式。
