---
title: CTest 与测试集成
updated: 2026-06-10
tags: [cmake, ctest, testing, gtest, catch2, fixtures, cpp]
---

# CTest 与测试集成

> 前置知识：[[02-cmakelists-structure-and-commands]] | 预计耗时：50min

## 概念介绍

CTest 是 CMake 内置的测试驱动工具。它在 CMake 的构建-测试-打包三件套中承担"测试"角色（另外两个是 CMake 本身负责构建，CPack 负责打包）。CTest 的设计哲学是**测试执行调度器**而非测试框架——它不关心你的测试是用什么写的，只负责运行它们、收集结果、汇总报告。

CTest 的核心价值：

- **与构建系统无缝集成**：`ctest` 命令直接读取 CMake 生成的测试清单（`CTestTestfile.cmake`）
- **框架无关**：可运行任意命令行程序——bash 脚本、Python 测试套件、Google Test、Catch2、boost.test 均可
- **并行执行**：`-j` 参数支持多测试并发，大幅缩短回归测试时间
- **CI/CD 友好**：Dashboard 模式可向 CDash 提交测试、覆盖率、内存检查报告
- **资源管理**：Fixtures 和 `RESOURCE_LOCK` 提供了测试间的依赖和并发控制

> [!tip] CTest vs 测试框架
> CTest 是**运行测试的工具**，不是**编写测试的框架**。你仍需要 Google Test、Catch2、doctest 等在 C++ 代码中写断言。CTest 负责的是：发现有哪些测试、按什么顺序运行、用多少并行度、收集哪些输出。

### CTest 的工作流程

```
cmake --build .          # 1. 构建项目（含测试可执行文件）
ctest                    # 2. CTest 读取 CTestTestfile.cmake，获得测试列表
                         # 3. 依次（或并行）运行每个测试
                         # 4. 收集 stdout/stderr、退出码、耗时
                         # 5. 汇总并输出报告
```

## 核心命令详解

### `enable_testing()` 和 `add_test()`

这是 CTest 的两个基石命令。`enable_testing()` 启用当前目录及子目录的测试功能；`add_test()` 注册一个测试。

```cmake
# 必须在 add_test 之前调用
enable_testing()

# 基本形式：add_test(NAME <name> COMMAND <command> [<arg>...])
add_test(NAME my_test COMMAND my_program arg1 arg2)

# 旧式简短形式（不推荐）
add_test(my_test my_program arg1 arg2)
```

> [!warning] `enable_testing()` 的位置
> `enable_testing()` 必须在当前目录（或父目录）中、所有 `add_test()` 调用之前出现。通常放在顶层 `CMakeLists.txt` 的 `project()` 之后。在子目录中调用 `add_test()` 之前，该子目录也需要 `enable_testing()`（或父目录已调用过且当前目录会被处理）。

`add_test()` 生成的测试会被写入构建目录下的 `CTestTestfile.cmake` 文件。CMake 的配置阶段会为每个包含测试的目录生成一个该文件，CTest 运行时读取它们构建测试清单。

**COMMAND 参数的两种模式：**

```cmake
# 模式 1：直接执行可执行文件
add_test(NAME unit_tests COMMAND unit_tests)

# 模式 2：通过解释器运行脚本
add_test(NAME py_test COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/test_runner.py)

# 模式 3：复杂命令行
add_test(NAME integration_test
    COMMAND ${CMAKE_BINARY_DIR}/bin/run_test
    --config ${CMAKE_BUILD_TYPE}
    --data-dir ${CMAKE_CURRENT_SOURCE_DIR}/data
)
```

> [!important] `add_test` 的命令行参数
> `COMMAND` 后的每个参数都是独立的 CMake 参数，会被正确地转义和传递给子进程。不会经过 shell 解析——这意味着 shell 通配符、重定向、管道等语法不可用。如需这些功能，显式调用 shell：
> ```cmake
> add_test(NAME shell_test COMMAND sh -c "my_program | grep ERROR")
> ```

### `set_tests_properties()` 和 `get_test_property()`

`set_tests_properties()` 为一个或多个测试设置属性，是精细化控制测试行为的核心接口。

```cmake
set_tests_properties(<test1> <test2> ...
    PROPERTIES
        <prop1> <value1>
        <prop2> <value2>
)
```

`get_test_property()` 用于在 CMake 脚本中读取测试属性（调试、条件判断等）。

```cmake
get_test_property(my_test WILL_FAIL result)
message("my_test WILL_FAIL = ${result}")
```

### 测试属性全解

CTest 提供了丰富的测试属性来控制行为。以下是核心属性的详解：

#### `WILL_FAIL`

标记测试**预期会失败**。当一个测试的退出码非零但被标记为 `WILL_FAIL` 时，CTest 会反转判定——失败变成功，成功变失败。常用于验证错误处理路径或回归测试已知 bug。

```cmake
add_test(NAME expect_error COMMAND my_app --bad-input)
set_tests_properties(expect_error PROPERTIES WILL_FAIL TRUE)
```

> [!tip] `WILL_FAIL` 的精妙之处
> 如果将来你修复了 bug 导致原本"应该失败"的测试突然成功了，CTest 会报告这个测试**失败**——因为 `WILL_FAIL` 反转了判定。这完美地将已知失败的回归用例转化为"记得修复后去掉此标记"的提醒。

#### `TIMEOUT` 和 `TIMEOUT_AFTER_MATCH`

防止测试挂死。

```cmake
set_tests_properties(slow_test PROPERTIES TIMEOUT 30)  # 30 秒超时
```

`TIMEOUT_AFTER_MATCH` 更智能——允许测试运行任意长时间，但如果 stdout/stderr 中匹配到指定正则表达式后超过 N 秒无新输出，则判定超时。

```cmake
set_tests_properties(network_test PROPERTIES
    TIMEOUT_AFTER_MATCH "Waiting for server" 10
)
```

#### `LABELS`

给测试打标签，配合 `ctest -L <label>` 或 `ctest -LE <label>` 按标签筛选运行。

```cmake
set_tests_properties(slow_test1 slow_test2 PROPERTIES
    LABELS "slow;integration"
)
set_tests_properties(unit_test PROPERTIES
    LABELS "unit;fast"
)
```

标签的值是分号分隔的列表，多个标签用 `;` 分隔。

#### `ENVIRONMENT`

为测试设置环境变量。这在需要隔离测试环境或传递配置参数时非常有用。

```cmake
set_tests_properties(db_test PROPERTIES
    ENVIRONMENT
        "DB_HOST=localhost;DB_PORT=5433;LOG_LEVEL=debug"
)
```

也可以使用 `ENVIRONMENT_MODIFICATION` 属性进行更精细的控制（追加、前置、路径列表操作等）。

#### `WORKING_DIRECTORY`

指定测试的工作目录。当测试需要读取相对路径的文件时，**必须**设置此属性。

```cmake
set_tests_properties(file_test PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/test_data"
)
```

> [!warning] 最容易忘记的属性
> `WORKING_DIRECTORY` 是 CTest 最常见的问题来源之一。测试程序默认在构建目录运行，而测试数据文件通常在源码目录。不设置 `WORKING_DIRECTORY` 会导致 `fopen("test_data.json")` 失败。

#### `PASS_REGULAR_EXPRESSION` 和 `FAIL_REGULAR_EXPRESSION`

通过检查输出来判定测试成败，而非仅依赖退出码。

```cmake
# 必须输出 "All tests passed"
set_tests_properties(check_output PROPERTIES
    PASS_REGULAR_EXPRESSION "All tests passed"
)

# 不允许输出 "ERROR"
set_tests_properties(sanity_test PROPERTIES
    FAIL_REGULAR_EXPRESSION "ERROR"
)
```

可以设置多个正则——所有 `PASS_REGULAR_EXPRESSION` 都必须匹配才算通过；任何一个 `FAIL_REGULAR_EXPRESSION` 匹配就算失败。

#### `RESOURCE_LOCK`

限制哪些测试可以并行执行。当多个测试竞争同一独占资源（串口、GPU、数据库、临时文件）时使用。

```cmake
set_tests_properties(gpu_test1 gpu_test2 PROPERTIES
    RESOURCE_LOCK gpu
)
```

持有相同 `RESOURCE_LOCK` 值的测试**不会**同时运行——即使在 `ctest -j 8` 并行模式下，它们也会串行。持有不同锁的测试仍可并行。

#### `FIXTURES_SETUP`、`FIXTURES_CLEANUP`、`FIXTURES_REQUIRED`

测试夹具系统——见下方[[#测试夹具 Test Fixtures]]章节。

#### `RUN_SERIAL`

强制测试串行执行，不与任何其他测试并行。

```cmake
set_tests_properties(critical_test PROPERTIES RUN_SERIAL TRUE)
```

#### `COST`

引导并行调度的相对开销权重。CTest 会优先调度 COST 高的测试，以优化整体完成时间。

```cmake
set_tests_properties(heavy_test PROPERTIES COST 10)    # 高开销，优先跑
set_tests_properties(light_test PROPERTIES COST 1)     # 低开销，填充空闲 slot
```

#### `DEPENDS`

声明测试间的依赖关系——只有依赖的测试全部通过后，当前测试才会运行。

```cmake
set_tests_properties(integration_test PROPERTIES
    DEPENDS "unit_test1;unit_test2"
)
```

> [!important] `DEPENDS` vs Fixtures
> `DEPENDS` 使一个测试依赖于另一个测试的**通过**状态。Fixtures 处理的是**环境依赖**（测试需要共享的 setup/cleanup 动作）。两者解决不同层面的问题。

## CTest 可执行文件

`ctest` 是命令行测试驱动。它必须在构建目录中运行（或通过 `--test-dir` 指定构建目录）。

### 基本用法

```bash
# 进入构建目录
cd build

# 运行所有测试
ctest

# 指定构建目录（CMake 3.20+）
ctest --test-dir build

# 先构建再测试
ctest --build-and-test <src-dir> <build-dir> --build-generator "Ninja"

# 详细输出（显示每个测试的 stdout/stderr）
ctest --verbose
# 或简写
ctest -V

# 更紧凑但仍有测试名
ctest --output-on-failure
```

### 并行执行

```bash
# 最多 8 个测试并行
ctest -j 8

# 使用所有可用 CPU 核心
ctest -j $(nproc)    # Linux
ctest -j %NUMBER_OF_PROCESSORS%   # Windows cmd

# 顺序执行（默认）
ctest -j 1
```

并行模式下，RESOURCE_LOCK 和 RUN_SERIAL 依然会被遵守。

### 测试筛选

```bash
# 按名称正则筛选
ctest -R "unit"           # 只运行名称含 "unit" 的测试
ctest -E "slow"           # 排除名称含 "slow" 的测试

# 按标签筛选
ctest -L "unit"           # 只运行标签含 "unit" 的测试
ctest -LE "integration"   # 排除标签含 "integration" 的测试

# 按索引运行
ctest -I 3,7              # 运行第 3~7 个测试（1-indexed）
ctest -I 3,7,2            # 运行 3,5,7（步长 2）

# 组合筛选
ctest -R "math" -L "fast" -j 4
```

### 列出和检查测试

```bash
# 列出所有测试（不运行）
ctest -N

# 列出测试并显示标签
ctest -N --print-labels

# 显示详细测试信息
ctest --show-only=json-v1   # JSON 格式输出（脚本友好）
```

### 输出控制

```bash
# 仅失败时显示输出
ctest --output-on-failure

# 将输出写入文件
ctest --output-log test_results.log

# 更详细的错误日志
ctest --output-on-failure --test-output-size-passed 1024
```

#### `CTEST_OUTPUT_ON_FAILURE` 环境变量

设置此环境变量等同于每次执行 `ctest --output-on-failure`：

```bash
# Linux/macOS
export CTEST_OUTPUT_ON_FAILURE=1
ctest

# Windows PowerShell
$env:CTEST_OUTPUT_ON_FAILURE=1
ctest
```

也可以在 `CMakeLists.txt` 中通过属性控制，或在 `CTestConfig.cmake` / `CMakePresets.json` 中设置。

### 重复运行与调试

```bash
# 重复运行直到失败（排查 flaky test）
ctest --repeat until-fail:5     # 最多重复 5 次，第一次失败即停止

# 重复运行 N 次
ctest --repeat until-pass:3     # 最多重复 3 次直到通过

# 失败后停止
ctest --stop-on-failure
```

### 测试调度策略

```bash
# 按测试名称字母序运行
ctest --schedule-random

# 测试超时（覆盖个别测试的 TIMEOUT 属性）
ctest --timeout 60
```

## 测试夹具 (Test Fixtures)

测试夹具解决的是**测试之间的环境依赖**：某些测试需要在特定环境准备好之后才能运行，某些测试完成后需要清理。CTest 的 Fixtures 机制优雅地处理了这类需求——不需要在测试代码中写 setup/teardown，由 CTest 在进程级别编排。

### 核心概念

四个属性协同工作：

| 属性 | 作用 |
|------|------|
| `FIXTURES_SETUP` | 声明本测试**设置**了哪些 fixture |
| `FIXTURES_CLEANUP` | 声明本测试**清理**了哪些 fixture |
| `FIXTURES_REQUIRED` | 声明本测试**需要**哪些 fixture |

一个 fixture 的名称是任意字符串，用于关联 setup 测试和 consumer 测试。

### 工作原理

1. 当测试 A 声明 `FIXTURES_REQUIRED my_fixture` 时，CTest 会查找声明了 `FIXTURES_SETUP my_fixture` 的测试 B
2. 测试 B 会在测试 A **之前**运行
3. 如果测试 B 失败了，所有依赖 `my_fixture` 的测试都会被跳过
4. 声明了 `FIXTURES_CLEANUP my_fixture` 的测试 C 会在所有依赖该 fixture 的测试**之后**运行
5. Cleanup 测试总是会运行——即使 setup 或 consumer 测试失败了

```cmake
# Setup 测试：创建临时数据库
add_test(NAME setup_db
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_BINARY_DIR}/test_db
    COMMAND init_db --dir ${CMAKE_BINARY_DIR}/test_db
)
set_tests_properties(setup_db PROPERTIES
    FIXTURES_SETUP db_ready
)

# Consumer 测试：使用数据库
add_test(NAME db_read_test
    COMMAND db_reader --dir ${CMAKE_BINARY_DIR}/test_db
)
set_tests_properties(db_read_test PROPERTIES
    FIXTURES_REQUIRED db_ready
)

add_test(NAME db_write_test
    COMMAND db_writer --dir ${CMAKE_BINARY_DIR}/test_db
)
set_tests_properties(db_write_test PROPERTIES
    FIXTURES_REQUIRED db_ready
)

# Cleanup 测试：删除数据库
add_test(NAME cleanup_db
    COMMAND ${CMAKE_COMMAND} -E remove_directory ${CMAKE_BINARY_DIR}/test_db
)
set_tests_properties(cleanup_db PROPERTIES
    FIXTURES_CLEANUP db_ready
)
```

### 执行顺序

```
setup_db  ─────────────────────────────────────────> cleanup_db
   │                                                     │
   ├──> db_read_test ──┐                                 │
   │                   ├── (任何顺序，取决于 -j)         │
   └──> db_write_test ─┘                                 │
```

- `setup_db` **一定**最先运行
- `db_read_test` 和 `db_write_test` 在 setup 之后、cleanup 之前运行；它们之间的顺序不保证
- `cleanup_db` **一定**最后运行，且无论前面的测试成功与否

### 一个 Fixture 多个 Setup/Cleanup

```cmake
# 场景：集成测试需要同时 setup 数据库和消息队列
set_tests_properties(setup_db PROPERTIES FIXTURES_SETUP "db;infra")
set_tests_properties(setup_mq PROPERTIES FIXTURES_SETUP "mq;infra")

set_tests_properties(integration_test PROPERTIES
    FIXTURES_REQUIRED "infra"           # 同时需要 db 和 mq
)

set_tests_properties(cleanup_db PROPERTIES FIXTURES_CLEANUP "db;infra")
set_tests_properties(cleanup_mq PROPERTIES FIXTURES_CLEANUP "mq;infra")
```

### Setup 测试的命令限制

Setup 测试中 `add_test(NAME ... COMMAND ...)` 支持多个 `COMMAND`（CMake 3.31+），老版本需要将多条命令放在脚本中。注意：`COMMAND` 参数不是 shell，多命令需要用 `&&` 包裹在 `sh -c` 中或使用 CMake 脚本：

```cmake
# 方法 1：多个 COMMAND（CMake 3.31+）
add_test(NAME setup_env
    COMMAND ${CMAKE_COMMAND} -E make_directory /tmp/test_work
    COMMAND ${CMAKE_COMMAND} -E copy ${SRC}/config.json /tmp/test_work/
)

# 方法 2：CMake 脚本（所有版本通用）
# 创建一个 setup.cmake 脚本
# 然后在 add_test 中执行它
add_test(NAME setup_env
    COMMAND ${CMAKE_COMMAND} -P ${CMAKE_CURRENT_SOURCE_DIR}/setup.cmake
)
```

## 测试框架集成

### Google Test (GTest)

Google Test 是最流行的 C++ 测试框架之一。CMake 通过 `GoogleTest` 模块提供了深度集成——不仅编译 GTest，还能**自动发现**测试用例并逐条注册给 CTest。

#### 传统方式：手动注册

```cmake
enable_testing()
add_executable(my_tests test_main.cpp test_math.cpp)
target_link_libraries(my_tests PRIVATE GTest::gtest_main)
add_test(NAME my_tests COMMAND my_tests)
```

这种方式的缺点是 CTest 只能看到一个大的 `my_tests` 测试——GTest 内部的 20 个测试用例对 CTest 来说是一个测试。一个 `TEST` 宏失败，整个 `my_tests` 就失败了，无法精确定位。

#### 现代方式：`gtest_discover_tests()`

```cmake
include(GoogleTest)
gtest_discover_tests(my_tests)
```

这个函数会：

1. 在构建阶段运行一次测试可执行文件，加上 `--gtest_list_tests` 参数
2. 解析输出，获得所有 `TEST()` 和 `TEST_F()` 用例的完整名称
3. 在构建目录生成 `CTestTestfile.cmake`，为**每一个** GTest 用例创建一个 CTest 测试条目

效果：

```bash
$ ctest -N
Test #1: MathTests.Add
Test #2: MathTests.Subtract
Test #3: MathTests.Multiply
Test #4: StringTests.Empty
Test #5: StringTests.Compare
...
```

每个测试可以独立运行、独立筛选、独立显示通过/失败。你可以 `ctest -R "MathTests"` 只跑数学相关的测试。

#### `gtest_discover_tests()` 的高级选项

```cmake
gtest_discover_tests(my_tests
    # 额外参数传递给测试可执行文件
    EXTRA_ARGS --gtest_shuffle

    # 指定工作目录
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/test_data

    # 自定义属性应用于每个被发现的测试
    PROPERTIES
        TIMEOUT 10
        LABELS "unit"
        ENVIRONMENT "GTEST_COLOR=1"

    # 自定义发现模式
    DISCOVERY_MODE PRE_TEST   # CMake 3.10+: 构建时发现
                              # POST_BUILD: 构建后运行测试发现（默认）
                              # 注意：CMake 4.0 中 PRE_TEST 可能成为默认值

    # 过滤要发现的测试
    TEST_FILTER "MathTests.*"

    # 每个测试单独的参数
    TEST_PREFIX "gtest."
    TEST_SUFFIX ".quick"

    # 测试发现时的超时
    DISCOVERY_TIMEOUT 30

    # XML 输出（用于 CI 报告）
    XML_OUTPUT_DIR ${CMAKE_BINARY_DIR}/test_results
)
```

> [!important] `DISCOVERY_MODE`
> - `POST_BUILD`（默认）：在 `cmake --build` 完成后运行发现。简单可靠，但构建完成后测试可执行文件必须能运行。交叉编译时会失败（目标平台的二进制无法在宿主机运行）。
> - `PRE_TEST`：在 `ctest` 运行前的最后一刻发现。这允许交叉编译场景——你可以在构建后传输二进制到目标设备，然后 CTest 通过自定义脚本在目标上运行发现。

#### `TEST_FILTER` — 细粒度控制

```cmake
# 只发现 FooTest 开头的测试
gtest_discover_tests(my_tests TEST_FILTER "FooTest.*")

# 排除特定 fixture 中的测试
gtest_discover_tests(my_tests TEST_FILTER "FooTest.*-FooTest.Bar")
```

`TEST_FILTER` 使用 GTest 自己的过滤器语法：`positive_patterns-negative_patterns`，用 `:` 分隔多个模式。

#### `TEST_FIXTURES` — 将 GTest 的 fixture 映射到 CTest fixtures

GTest 的 test fixture（类继承 `::testing::Test`）提供的是**进程内**的 setup/teardown。当需要**进程间**的 setup（如启动外部服务），可以将其映射到 CTest fixtures：

```cmake
add_test(NAME start_service COMMAND start_test_service)
set_tests_properties(start_service PROPERTIES FIXTURES_SETUP test_service)

gtest_discover_tests(my_tests
    TEST_FIXTURES "TestServiceFixture:test_service"
)
```

### Catch2

Catch2 自带 CMake 集成。从 Catch2 v3 开始，你可以通过 `catch_discover_tests()` 实现与 `gtest_discover_tests()` 相同的自动测试发现。

```cmake
include(FetchContent)
FetchContent_Declare(
    Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG v3.6.0
)
FetchContent_MakeAvailable(Catch2)

add_executable(my_catch_tests test_main.cpp test_math.cpp)
target_link_libraries(my_catch_tests PRIVATE Catch2::Catch2WithMain)

# 关键：自动发现 Catch2 测试用例
include(Catch)
catch_discover_tests(my_catch_tests)
```

> [!tip] Catch2 vs Google Test 集成差异
> Catch2 的 CMake 集成不是 CMake 内置模块——它由 Catch2 项目自己提供（`CatchConfig.cmake` 或 `Catch2Config.cmake`）。因此使用 `find_package(Catch2)` 或 `FetchContent` 后，`include(Catch)` 才能正常工作。而 GTest 的 `GoogleTest` 模块是 CMake 内置的。

Catch2 也支持使用 CMake 的 `ctest` fixture 系统：

```cmake
# Catch2 测试夹具映射
catch_discover_tests(my_catch_tests
    TEST_SPEC "math_*"
    EXTRA_ARGS --order rand
    PROPERTIES TIMEOUT 30
)
```

### doctest

doctest 也提供了与 CTest 集成的模块：

```cmake
include(FetchContent)
FetchContent_Declare(doctest
    GIT_REPOSITORY https://github.com/doctest/doctest.git
    GIT_TAG v2.4.11
)
FetchContent_MakeAvailable(doctest)

add_executable(my_doctest_tests test_runner.cpp)
target_link_libraries(my_doctest_tests PRIVATE doctest::doctest)

include(CTest)
doctest_discover_tests(my_doctest_tests)
```

## Dashboard 与 CDash

CTest 的 Dashboard 模式可将测试结果提交到 [CDash](https://www.cdash.org/) 仪表板，用于持续集成中的测试监控和趋势分析。

### 配置 `CTestConfig.cmake`

在项目顶层创建此文件：

```cmake
set(CTEST_PROJECT_NAME "MyProject")
set(CTEST_NIGHTLY_START_TIME "03:00:00 UTC")
set(CTEST_DROP_METHOD "https")
set(CTEST_DROP_SITE "my.cdash.server")
set(CTEST_DROP_LOCATION "/submit.php?project=MyProject")
set(CTEST_DROP_SITE_CDASH TRUE)
```

### Dashboard 模式

```bash
# 实验模式 (-M Experimental)：测试当前代码并提交
ctest -D Experimental

# 每晚构建模式 (-M Nightly)：在指定时间自动构建测试
ctest -D Nightly

# 持续集成模式 (-M Continuous)：检测到代码变更时触发
ctest -D Continuous

# 指定单个步骤（而非全流程：update/configure/build/test/submit）
ctest -T Start      # 开始一个新的 dashboard 提交
ctest -T Update     # 更新源码
ctest -T Configure  # 配置
ctest -T Build      # 构建
ctest -T Test       # 测试
ctest -T Submit     # 提交到 CDash

# 通常全部一起做：
ctest -D Experimental -T Start -T Configure -T Build -T Test -T Submit

# 在多处理器上并行构建
ctest -D Nightly -j 4
```

### `CTEST_CUSTOM_*` 变量

在 `CTestCustom.cmake`（或 `CTestCustom.ctest`）文件中设置这些变量，可以自定义 Dashboard 提交行为：

```cmake
# CTestCustom.cmake

# 排除某些警告/错误不报告给 CDash
set(CTEST_CUSTOM_WARNING_EXCEPTION
    "deprecated"
    "unused variable"
)

set(CTEST_CUSTOM_ERROR_EXCEPTION
    "known_spurious_error"
)

# 提交前/后执行的命令
set(CTEST_CUSTOM_PRE_TEST "echo Running pre-test setup...")
set(CTEST_CUSTOM_POST_TEST "echo Tests complete at %DATE% %TIME%")

# 内存检查的额外选项
set(CTEST_CUSTOM_MEMCHECK_IGNORE
    "still reachable"
    "possibly lost: 0"
)

# 覆盖率的排除模式
set(CTEST_CUSTOM_COVERAGE_EXCLUDE
    ".*/third_party/.*"
    ".*/tests/.*"
    ".*/generated/.*"
)
```

## 内存检查

CTest 可以集成 Valgrind（Linux/macOS）进行内存泄漏和错误检查。

```bash
# 运行 Valgrind memcheck
ctest -T memcheck

# 指定 Valgrind 选项
ctest -T memcheck --overwrite MemoryCheckCommandOptions="--leak-check=full --show-leak-kinds=all"

# 与 dashboard 结合
ctest -D Nightly -T memcheck
```

**前提条件：**
- 系统安装了 Valgrind
- 测试可执行文件包含调试符号（`-g`，推荐 `-O0` 或 `-O1` 以获得可读的栈追踪）

在 `CMakeLists.txt` 中，可以通过 `MEMORYCHECK_COMMAND_OPTIONS` 变量预设 Valgrind 参数：

```cmake
set(MEMORYCHECK_COMMAND_OPTIONS
    "--leak-check=full;--show-leak-kinds=all;--track-origins=yes"
    CACHE STRING "Valgrind options for memcheck"
)
```

> [!warning] Valgrind 性能
> Valgrind memcheck 会使被测程序慢 10-30 倍。确保测试有足够的 `TIMEOUT`。在 CI 中按需运行 memcheck（如 Nightly 模式），不在每次提交时运行。

### 其他内存检查工具

除了 Valgrind，CTest 也支持通过 `MEMORYCHECK_TYPE` 指定其他工具：

```cmake
# AddressSanitizer（需在编译时启用 -fsanitize=address）
set(MEMORYCHECK_TYPE "AddressSanitizer")

# MemorySanitizer
set(MEMORYCHECK_TYPE "MemorySanitizer")

# ThreadSanitizer
set(MEMORYCHECK_TYPE "ThreadSanitizer")
```

## 覆盖率

CTest 可以收集和提交代码覆盖率数据。

```bash
# 收集覆盖率
ctest -T coverage

# 结合 dashboard
ctest -D Nightly -T coverage
```

覆盖率收集需要编译器支持。常用方案：

**GCC + gcov/lcov:**

```cmake
# CMakeLists.txt
if(CMAKE_COMPILER_IS_GNUCC OR CMAKE_C_COMPILER_ID MATCHES "Clang")
    add_compile_options(--coverage)
    add_link_options(--coverage)
endif()
```

**Clang + source-based coverage:**

```cmake
if(CMAKE_C_COMPILER_ID MATCHES "Clang")
    add_compile_options(-fprofile-instr-generate -fcoverage-mapping)
    add_link_options(-fprofile-instr-generate)
endif()
```

CTest 会查找 `gcov` 或 `llvm-cov` 来收集数据，生成覆盖率报告并可选提交到 CDash。

## `CMakePresets.json` 测试预设

测试预设是 `CMakePresets.json` 的第三类预设（前两类是 configure 和 build）。它标准化了 `ctest` 的调用方式。

```json
{
  "version": 6,
  "configurePresets": [
    {
      "name": "default",
      "binaryDir": "${sourceDir}/build"
    }
  ],
  "testPresets": [
    {
      "name": "default",
      "configurePreset": "default",
      "output": {
        "outputOnFailure": true,
        "verbosity": "default"
      },
      "execution": {
        "jobs": 4,
        "stopOnFailure": false,
        "repeat": {
          "mode": "until-fail",
          "count": 3
        }
      },
      "filter": {
        "include": {
          "name": "unit"
        },
        "exclude": {
          "label": "slow"
        }
      }
    },
    {
      "name": "ci-coverage",
      "configurePreset": "default",
      "output": {
        "outputOnFailure": true,
        "verbosity": "verbose"
      },
      "execution": {
        "jobs": 8,
        "timeout": 300
      },
      "filter": {
        "exclude": {
          "label": "manual"
        }
      }
    }
  ]
}
```

使用：

```bash
# 按预设运行测试
ctest --preset default

# CI 模式
ctest --preset ci-coverage
```

## `BUILD_TESTING` 约定

`BUILD_TESTING` 是一个 CMake 社区约定：顶层 `CMakeLists.txt` 通过此变量控制是否构建测试目标。

```cmake
# 顶层 CMakeLists.txt
include(CTest)  # 自动创建 BUILD_TESTING 选项，默认 ON

# 如果 BUILD_TESTING 为 OFF，跳过子目录中的测试
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
```

`include(CTest)` 会自动创建 `BUILD_TESTING` 缓存变量，并调用 `enable_testing()`。下游用户可以通过 `-DBUILD_TESTING=OFF` 跳过测试构建（适用于快速迭代或构建环境受限的场景）。

```bash
# 跳过测试
cmake -B build -DBUILD_TESTING=OFF
cmake --build build
```

> [!info] `include(CTest)` vs `enable_testing()`
> `include(CTest)` 包含了 `enable_testing()` 的功能，此外还会：
> - 定义 `BUILD_TESTING` 选项（默认 ON）
> - 加载 `CTest` 模块，提供 `CTEST_*` 变量和 dashboard 支持
> - 如果存在 `CTestConfig.cmake`，读取其配置
>
> 对于只需要简单 `add_test()` 的项目，单独用 `enable_testing()` 即可。需要 CDash 提交或标准化 CI 集成的项目，使用 `include(CTest)`。

## 代码示例

### 示例 1：简易测试 — `add_test()` + `enable_testing()`

这个示例演示最基础的 CTest 集成：编写一个 C 程序、用 `add_test()` 注册测试、通过返回码判定通过/失败。

**项目结构：**

```
example1/
├── CMakeLists.txt
├── src/
│   ├── math.h
│   └── math.c
└── tests/
    ├── CMakeLists.txt
    ├── test_add.c
    ├── test_sub.c
    └── test_div.c
```

**`CMakeLists.txt`（顶层）：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(Example1 VERSION 1.0 LANGUAGES C)

# 构建数学库
add_library(math src/math.c)
target_include_directories(math PUBLIC src)

# 启用测试
enable_testing()
add_subdirectory(tests)
```

**`src/math.h`：**

```c
#ifndef MATH_H
#define MATH_H

int add(int a, int b);
int sub(int a, int b);
int divide(int a, int b);

#endif
```

**`src/math.c`：**

```c
#include "math.h"

int add(int a, int b) { return a + b; }

int sub(int a, int b) { return a - b; }

int divide(int a, int b) {
    if (b == 0) return 0;
    return a / b;
}
```

**`tests/CMakeLists.txt`：**

```cmake
# test_add
add_executable(test_add test_add.c)
target_link_libraries(test_add PRIVATE math)
add_test(NAME add.positive    COMMAND test_add 3 4 7)
add_test(NAME add.negative    COMMAND test_add -2 -3 -5)
add_test(NAME add.zero        COMMAND test_add 0 5 5)

# test_sub
add_executable(test_sub test_sub.c)
target_link_libraries(test_sub PRIVATE math)
add_test(NAME sub.positive    COMMAND test_sub 10 3 7)
add_test(NAME sub.zero_result COMMAND test_sub 5 5 0)

# test_div
add_executable(test_div test_div.c)
target_link_libraries(test_div PRIVATE math)
add_test(NAME div.normal      COMMAND test_div 10 2 5)
add_test(NAME div.by_zero     COMMAND test_div 10 0 0)
set_tests_properties(div.by_zero PROPERTIES WILL_FAIL TRUE)
```

**`tests/test_add.c`：**

```c
#include <stdio.h>
#include <stdlib.h>

int add(int a, int b);

int main(int argc, char *argv[]) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <a> <b> <expected>\n", argv[0]);
        return 1;
    }
    int a = atoi(argv[1]);
    int b = atoi(argv[2]);
    int expected = atoi(argv[3]);
    int result = add(a, b);
    if (result != expected) {
        fprintf(stderr, "FAIL: add(%d, %d) = %d, expected %d\n",
                a, b, result, expected);
        return 1;
    }
    printf("PASS: add(%d, %d) = %d\n", a, b, result);
    return 0;
}
```

**`tests/test_sub.c`：**

```c
#include <stdio.h>
#include <stdlib.h>

int sub(int a, int b);

int main(int argc, char *argv[]) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <a> <b> <expected>\n", argv[0]);
        return 1;
    }
    int a = atoi(argv[1]);
    int b = atoi(argv[2]);
    int expected = atoi(argv[3]);
    int result = sub(a, b);
    if (result != expected) {
        fprintf(stderr, "FAIL: sub(%d, %d) = %d, expected %d\n",
                a, b, result, expected);
        return 1;
    }
    printf("PASS: sub(%d, %d) = %d\n", a, b, result);
    return 0;
}
```

**`tests/test_div.c`：**

```c
#include <stdio.h>
#include <stdlib.h>

int divide(int a, int b);

int main(int argc, char *argv[]) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <a> <b> <expected>\n", argv[0]);
        return 1;
    }
    int a = atoi(argv[1]);
    int b = atoi(argv[2]);
    int expected = atoi(argv[3]);
    int result = divide(a, b);
    if (result != expected) {
        fprintf(stderr, "FAIL: divide(%d, %d) = %d, expected %d\n",
                a, b, result, expected);
        return 1;
    }
    printf("PASS: divide(%d, %d) = %d\n", a, b, result);
    return 0;
}
```

**构建与运行：**

```bash
cd example1
cmake -B build
cmake --build build
cd build
ctest --output-on-failure
```

**预期输出：**

```
Test project .../example1/build
    Start 1: add.positive
1/8 Test #1: add.positive ....................   Passed    0.01s
    Start 2: add.negative
2/8 Test #2: add.negative ....................   Passed    0.01s
    Start 3: add.zero
3/8 Test #3: add.zero ........................   Passed    0.01s
    Start 4: sub.positive
4/8 Test #4: sub.positive ....................   Passed    0.01s
    Start 5: sub.zero_result
5/8 Test #5: sub.zero_result .................   Passed    0.01s
    Start 6: div.normal
6/8 Test #6: div.normal ......................   Passed    0.01s
    Start 7: div.by_zero
7/8 Test #7: div.by_zero .....................   Passed    0.01s
    Start 8: add.flaky
8/8 Test #8: add.flaky .......................***Failed    0.01s

100% tests passed, 0 tests failed out of 8
```

### 示例 2：Google Test 集成 + `gtest_discover_tests()`

这个示例展示通过 `FetchContent` 获取 Google Test，并使用 `gtest_discover_tests()` 自动发现所有测试用例。

**项目结构：**

```
example2/
├── CMakeLists.txt
├── src/
│   ├── calculator.h
│   └── calculator.cpp
└── tests/
    ├── CMakeLists.txt
    └── test_calculator.cpp
```

**`CMakeLists.txt`（顶层）：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(Example2 VERSION 1.0 LANGUAGES CXX)

# 使用 CTest（同时定义 BUILD_TESTING 选项并 enable_testing）
include(CTest)

# 构建被测库
add_library(calculator src/calculator.cpp)
target_include_directories(calculator PUBLIC src)

# 条件编译测试
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
```

**`src/calculator.h`：**

```c++
#ifndef CALCULATOR_H
#define CALCULATOR_H

#include <string>
#include <vector>

class Calculator {
public:
    static int add(int a, int b);
    static int subtract(int a, int b);
    static int multiply(int a, int b);
    static double divide(int a, int b);

    static std::vector<int> fibonacci(int n);
    static bool isPrime(int n);
};

#endif
```

**`src/calculator.cpp`：**

```c++
#include "calculator.h"
#include <cmath>
#include <stdexcept>

int Calculator::add(int a, int b) { return a + b; }
int Calculator::subtract(int a, int b) { return a - b; }
int Calculator::multiply(int a, int b) { return a * b; }

double Calculator::divide(int a, int b) {
    if (b == 0) throw std::invalid_argument("division by zero");
    return static_cast<double>(a) / b;
}

std::vector<int> Calculator::fibonacci(int n) {
    if (n <= 0) return {};
    if (n == 1) return {0};
    std::vector<int> result{0, 1};
    for (int i = 2; i < n; ++i)
        result.push_back(result[i-1] + result[i-2]);
    return result;
}

bool Calculator::isPrime(int n) {
    if (n < 2) return false;
    if (n == 2) return true;
    if (n % 2 == 0) return false;
    int limit = static_cast<int>(std::sqrt(n));
    for (int i = 3; i <= limit; i += 2)
        if (n % i == 0) return false;
    return true;
}
```

**`tests/CMakeLists.txt`：**

```cmake
# ---- 获取 Google Test ----
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.15.2
)
# 避免 gtest 安装到系统
set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# ---- 构建测试可执行文件 ----
add_executable(test_calculator test_calculator.cpp)
target_link_libraries(test_calculator PRIVATE calculator GTest::gtest_main)

# ---- 为 GTest 的每个 TEST/TEST_F 创建 CTest 条目 ----
include(GoogleTest)
gtest_discover_tests(test_calculator
    PROPERTIES
        TIMEOUT 10
        LABELS "unit;calculator"
    TEST_PREFIX "calc."
    DISCOVERY_TIMEOUT 15
)
```

**`tests/test_calculator.cpp`：**

```c++
#include <gtest/gtest.h>
#include "calculator.h"

// ========== 加法测试 ==========
TEST(CalculatorTest, AddPositive) {
    EXPECT_EQ(Calculator::add(2, 3), 5);
    EXPECT_EQ(Calculator::add(100, 200), 300);
}

TEST(CalculatorTest, AddNegative) {
    EXPECT_EQ(Calculator::add(-2, -3), -5);
    EXPECT_EQ(Calculator::add(-10, 5), -5);
}

TEST(CalculatorTest, AddZero) {
    EXPECT_EQ(Calculator::add(0, 5), 5);
    EXPECT_EQ(Calculator::add(5, 0), 5);
}

// ========== 减法测试 ==========
TEST(CalculatorTest, SubtractNormal) {
    EXPECT_EQ(Calculator::subtract(10, 3), 7);
    EXPECT_EQ(Calculator::subtract(3, 10), -7);
}

// ========== 乘法测试 ==========
TEST(CalculatorTest, MultiplyNormal) {
    EXPECT_EQ(Calculator::multiply(3, 4), 12);
    EXPECT_EQ(Calculator::multiply(-3, 4), -12);
    EXPECT_EQ(Calculator::multiply(0, 100), 0);
}

// ========== 除法测试 ==========
TEST(CalculatorTest, DivideNormal) {
    EXPECT_DOUBLE_EQ(Calculator::divide(10, 4), 2.5);
    EXPECT_DOUBLE_EQ(Calculator::divide(7, 2), 3.5);
}

TEST(CalculatorTest, DivideByZeroThrows) {
    EXPECT_THROW(Calculator::divide(10, 0), std::invalid_argument);
}

// ========== Fibonacci 测试 ==========
TEST(CalculatorTest, FibonacciZero) {
    EXPECT_TRUE(Calculator::fibonacci(0).empty());
}

TEST(CalculatorTest, FibonacciFirst) {
    auto result = Calculator::fibonacci(1);
    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result[0], 0);
}

TEST(CalculatorTest, FibonacciFive) {
    auto result = Calculator::fibonacci(5);
    std::vector<int> expected{0, 1, 1, 2, 3};
    EXPECT_EQ(result, expected);
}

// ========== 素数测试 ==========
TEST(CalculatorTest, IsPrimeEdgeCases) {
    EXPECT_FALSE(Calculator::isPrime(0));
    EXPECT_FALSE(Calculator::isPrime(1));
    EXPECT_TRUE(Calculator::isPrime(2));
    EXPECT_TRUE(Calculator::isPrime(3));
}

TEST(CalculatorTest, IsPrimeTypical) {
    EXPECT_FALSE(Calculator::isPrime(4));
    EXPECT_TRUE(Calculator::isPrime(17));
    EXPECT_FALSE(Calculator::isPrime(100));
    EXPECT_TRUE(Calculator::isPrime(97));
}
```

**构建与运行：**

```bash
cd example2
cmake -B build
cmake --build build
cd build

# 列出所有测试
ctest -N

# 运行所有测试
ctest --output-on-failure

# 只运行 Fibonacci 相关测试
ctest -R "Fibonacci"

# 并行运行
ctest -j 4
```

**预期 `ctest -N` 输出：**

```
Test #1: calc.CalculatorTest.AddPositive
Test #2: calc.CalculatorTest.AddNegative
Test #3: calc.CalculatorTest.AddZero
Test #4: calc.CalculatorTest.SubtractNormal
Test #5: calc.CalculatorTest.MultiplyNormal
Test #6: calc.CalculatorTest.DivideNormal
Test #7: calc.CalculatorTest.DivideByZeroThrows
Test #8: calc.CalculatorTest.FibonacciZero
Test #9: calc.CalculatorTest.FibonacciFirst
Test #10: calc.CalculatorTest.FibonacciFive
Test #11: calc.CalculatorTest.IsPrimeEdgeCases
Test #12: calc.CalculatorTest.IsPrimeTypical

Total Tests: 12
```

### 示例 3：测试夹具 — Setup / Cleanup 依赖

这个示例模拟集成测试场景：测试需要临时目录、数据库文件和网络模拟。通过 CTest fixtures 编排 setup → test → cleanup 的顺序。

**项目结构：**

```
example3/
├── CMakeLists.txt
├── scripts/
│   ├── setup_env.cmake
│   └── cleanup_env.cmake
└── tests/
    ├── CMakeLists.txt
    ├── write_test.c
    └── read_test.c
```

**`CMakeLists.txt`（顶层）：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(Example3 VERSION 1.0 LANGUAGES C)

enable_testing()
add_subdirectory(tests)
```

**`tests/CMakeLists.txt`：**

```cmake
# ===================================================
# 测试夹具设计:
#   fixture "test_env" (setup)    → 创建临时目录 + 写入配置文件
#   fixture "test_env" (cleanup)  → 删除临时目录
#
#   write_test  需要 "test_env"
#   read_test   需要 "test_env"
# ===================================================

set(TEST_WORK_DIR "${CMAKE_BINARY_DIR}/test_workspace")

# ---- Setup 测试：准备测试环境 ----
add_test(NAME setup_test_env
    COMMAND ${CMAKE_COMMAND}
        -DTEST_WORK_DIR=${TEST_WORK_DIR}
        -P ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/setup_env.cmake
)
set_tests_properties(setup_test_env PROPERTIES
    FIXTURES_SETUP test_env
    LABELS "setup"
)

# ---- 测试：写入文件 ----
add_executable(write_test write_test.c)
add_test(NAME write_test
    COMMAND write_test "${TEST_WORK_DIR}/data.txt" "Hello CTest Fixtures!"
)
set_tests_properties(write_test PROPERTIES
    FIXTURES_REQUIRED test_env
    WORKING_DIRECTORY "${TEST_WORK_DIR}"
    LABELS "integration"
)

# ---- 测试：读取并验证文件 ----
add_executable(read_test read_test.c)
add_test(NAME read_test
    COMMAND read_test "${TEST_WORK_DIR}/data.txt" "Hello CTest Fixtures!"
)
set_tests_properties(read_test PROPERTIES
    FIXTURES_REQUIRED test_env
    WORKING_DIRECTORY "${TEST_WORK_DIR}"
    LABELS "integration"
)

# ---- Cleanup 测试：清理环境 ----
add_test(NAME cleanup_test_env
    COMMAND ${CMAKE_COMMAND}
        -DTEST_WORK_DIR=${TEST_WORK_DIR}
        -P ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/cleanup_env.cmake
)
set_tests_properties(cleanup_test_env PROPERTIES
    FIXTURES_CLEANUP test_env
    LABELS "cleanup"
)
```

**`scripts/setup_env.cmake`：**

```cmake
# setup_env.cmake — 创建测试隔离环境
# 用法: cmake -DTEST_WORK_DIR=<dir> -P setup_env.cmake

if(NOT TEST_WORK_DIR)
    message(FATAL_ERROR "TEST_WORK_DIR must be specified via -D")
endif()

# 创建临时目录
file(MAKE_DIRECTORY "${TEST_WORK_DIR}")

# 写入配置文件
file(WRITE "${TEST_WORK_DIR}/config.ini"
    "[test]\n"
    "db_path=${TEST_WORK_DIR}/test.db\n"
    "log_level=debug\n"
    "timeout=5\n"
)

# 创建一个空数据文件供操作
file(WRITE "${TEST_WORK_DIR}/data.txt" "")

message(STATUS "Test environment created at ${TEST_WORK_DIR}")
```

**`scripts/cleanup_env.cmake`：**

```cmake
# cleanup_env.cmake — 清理测试环境
# 用法: cmake -DTEST_WORK_DIR=<dir> -P cleanup_env.cmake

if(NOT TEST_WORK_DIR)
    message(FATAL_ERROR "TEST_WORK_DIR must be specified via -D")
endif()

if(EXISTS "${TEST_WORK_DIR}")
    file(REMOVE_RECURSE "${TEST_WORK_DIR}")
    message(STATUS "Test environment cleaned: ${TEST_WORK_DIR}")
else()
    message(STATUS "Nothing to clean: ${TEST_WORK_DIR} does not exist")
endif()
```

**`tests/write_test.c`：**

```c
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: write_test <file> <content>\n");
        return 1;
    }

    const char *filepath = argv[1];
    const char *content = argv[2];

    FILE *f = fopen(filepath, "w");
    if (!f) {
        fprintf(stderr, "FAIL: Cannot open %s for writing\n", filepath);
        return 1;
    }

    if (fprintf(f, "%s", content) < 0) {
        fprintf(stderr, "FAIL: Write error\n");
        fclose(f);
        return 1;
    }

    fclose(f);
    printf("PASS: Wrote %zu bytes to %s\n",
           (size_t)(content ? 1 : 0) * 100, filepath);  /* simplified */
    return 0;
}
```

**`tests/read_test.c`：**

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: read_test <file> <expected_content>\n");
        return 1;
    }

    const char *filepath = argv[1];
    const char *expected = argv[2];

    FILE *f = fopen(filepath, "r");
    if (!f) {
        fprintf(stderr, "FAIL: Cannot open %s for reading\n", filepath);
        return 1;
    }

    char buffer[4096] = {0};
    size_t bytes_read = fread(buffer, 1, sizeof(buffer) - 1, f);
    fclose(f);

    buffer[bytes_read] = '\0';

    if (strcmp(buffer, expected) != 0) {
        fprintf(stderr, "FAIL: Content mismatch\n");
        fprintf(stderr, "  Expected: \"%s\"\n", expected);
        fprintf(stderr, "  Got:      \"%s\"\n", buffer);
        return 1;
    }

    printf("PASS: File %s contains expected content\n", filepath);
    return 0;
}
```

**构建与运行：**

```bash
cd example3
cmake -B build
cmake --build build
cd build

# 观察测试顺序：setup 一定最先，cleanup 一定最后
ctest --output-on-failure -V

# 验证：如果 write_test 失败，read_test 应该被跳过
# （因为 read_test 依赖 write_test 创建的文件）
```

> [!tip] 验证执行顺序
> 带 `-V` (verbose) 运行 CTest，观察测试的 Start/End 时间戳，确认 setup 最先运行、cleanup 最后运行。你也可以故意让 setup 失败（修改 `setup_env.cmake` 让它 `message(FATAL_ERROR ...)`），看看依赖它的测试是否被正确跳过。

## 练习

### 练习 1：用 `add_test` 为数学库写 3 个测试

创建一个项目，包含一个简单的数学库（至少 `add`、`multiply`、`factorial` 三个函数）。

- 编写 3 个独立的测试可执行文件（如 `test_add.c`、`test_multiply.c`、`test_factorial.c`）
- 每个测试可执行文件接受命令行参数（输入值和期望值），返回 0 表示通过、非 0 表示失败
- 用 `add_test()` 为每个函数注册至少 2 个测试用例
- 使用 `set_tests_properties()` 设置以下属性：
  - 所有测试设置 `LABELS "math;simple"`
  - `test_factorial` 中的一个大数据量测试设置 `TIMEOUT 5`
  - 为除零等边界情况测试设置 `WILL_FAIL TRUE`
- 运行 `ctest --output-on-failure` 验证所有测试通过
- 运行 `ctest -N` 列出所有测试
- 运行 `ctest -L math -V` 只运行 math 标签的测试

### 练习 2：集成 Google Test 并测试一个函数

继续扩展数学库，使用 Google Test 编写测试：

- 使用 `FetchContent` 获取 Google Test（参考示例 2）
- 编写 `test_calculator.cpp`，包含至少 3 个 `TEST` 用例（覆盖加法、乘法、阶乘）
- 使用 `gtest_discover_tests()` 自动发现，设置 `TEST_PREFIX "mylib."`
- 每个测试设置 `TIMEOUT 10` 和 `LABELS "gtest;math"`
- 使用 `ctest -R "factorial"` 只运行 factorial 相关的测试
- 使用 `ctest --repeat until-fail:10` 重复运行 10 次验证稳定性
- 尝试修改被测代码引入一个 bug，观察 `ctest --output-on-failure` 的输出

### 练习 3：创建带 Setup/Cleanup 的测试夹具

模拟一个需要文件系统隔离的测试场景：

- 编写一个 C 程序 `file_sorter`：读取输入文件的所有行，排序后写入输出文件
- 创建两个 CMake 脚本：`create_test_files.cmake` 和 `cleanup_test_files.cmake`
  - `create_test_files.cmake`：创建临时目录，写入一个包含多行乱序文本的输入文件，以及一个期望结果文件
  - `cleanup_test_files.cmake`：删除临时目录
- 用 `add_test` + `FIXTURES_SETUP` / `FIXTURES_CLEANUP` / `FIXTURES_REQUIRED` 编排测试：
  - Setup 测试 → 准备测试文件
  - `test_file_sorter` → 运行 `file_sorter`，比较输出与期望
  - Cleanup 测试 → 删除临时文件
- 运行 `ctest -V` 观察执行顺序
- 运行 `ctest --schedule-random` 多次验证 fixture 的顺序一致性（setup 始终第一，cleanup 始终最后）

## 常见陷阱

### 忘记 `enable_testing()`

**症状**：`ctest` 报 `No tests were found!!!`，尽管你在 `CMakeLists.txt` 中写了 `add_test()`。

**原因**：`enable_testing()` 未在调用 `add_test()` 的目录（或父目录）中调用。CMake 不会为没有 `enable_testing()` 的目录生成 `CTestTestfile.cmake`。

**修复**：在顶层 `CMakeLists.txt` 的 `project()` 之后、任何 `add_subdirectory()` 之前调用 `enable_testing()`（或 `include(CTest)`）。

### 没有设置 `WORKING_DIRECTORY`

**症状**：测试程序运行时报 `No such file or directory` 或 `fopen failed`，但文件明明存在。

**原因**：`add_test(NAME ... COMMAND ...)` 启动的进程默认的工作目录是**构建目录**（`CMAKE_BINARY_DIR`），而非源码目录或测试文件所在目录。如果你的测试代码使用相对路径打开文件（如 `fopen("test_data.json", "r")`），查找路径是构建目录。

**修复**：

```cmake
set_tests_properties(my_test PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
```

或让测试代码接收文件路径作为命令行参数，在 `add_test` 中传入绝对路径。

### 运行测试前忘记构建

**症状**：修改了测试代码后运行 `ctest`，但运行的是旧版本。

**原因**：`ctest` 不自动执行构建——它只运行已经构建好的测试可执行文件。

**修复**：养成先构建再测试的习惯：

```bash
cmake --build build && ctest --test-dir build
```

或使用 `ctest --build-and-test`（但通常不如上述方式灵活）。

### 误用 `WILL_FAIL` 导致误判

**症状**：修复了 bug 后 `ctest` 报告某个测试"失败"，但手动运行确实通过。

**原因**：你之前为这个 bug 的回归测试设置了 `WILL_FAIL TRUE`。修复后测试通过了（返回 0），但 `WILL_FAIL` 反转了判定——"通过"变成了"失败"。

**修复**：修复 bug 后移除对应的 `WILL_FAIL` 属性。这是 `WILL_FAIL` 的设计意图——提醒你"这个标记还在这里，记得处理"。

### 并行测试中的竞态条件

**症状**：测试在 `ctest -j 1` 时全部通过，但在 `ctest -j 8` 时随机失败。

**原因**：多个测试共享了资源（文件、端口、环境变量、全局状态），但没有使用 `RESOURCE_LOCK` 或 fixtures 做隔离。

**修复策略**：

1. **如果资源是测试独有的**（如临时文件），确保每个测试使用唯一的工作目录或文件名（如使用 `$$` PID）
2. **如果资源是共享的**（如数据库、端口），使用 `RESOURCE_LOCK`：
   ```cmake
   set_tests_properties(db_test1 db_test2 PROPERTIES
       RESOURCE_LOCK database
   )
   ```
3. **如果有严格的顺序依赖**，使用 fixtures：
   ```cmake
   set_tests_properties(setup_db PROPERTIES FIXTURES_SETUP db)
   set_tests_properties(db_tests PROPERTIES FIXTURES_REQUIRED db)
   ```

### `gtest_discover_tests()` 在交叉编译时失败

**症状**：`cmake --build` 在交叉编译环境下报错，提示无法运行测试可执行文件。

**原因**：`DISCOVERY_MODE POST_BUILD`（默认）在构建后立即在**宿主机**上运行测试可执行文件以发现测试用例。交叉编译的目标二进制无法在宿主机运行。

**修复**：改用 `DISCOVERY_MODE PRE_TEST`：

```cmake
gtest_discover_tests(my_tests DISCOVERY_MODE PRE_TEST)
```

`PRE_TEST` 模式将发现推迟到 `ctest` 运行前。结合自定义的 CTest 脚本，可以在目标设备上执行发现。

### CTest 找不到测试（子目录遗漏）

**症状**：顶层有 `enable_testing()`，但子目录的测试没有被 CTest 发现。

**原因**：`add_subdirectory()` 需要在 `enable_testing()` 之后调用。CMake 的测试注册是基于目录树的——如果在 `enable_testing()` 之前 `add_subdirectory()`，该子目录不会创建测试。

**修复**：确保 `enable_testing()` 在顶层 `CMakeLists.txt` 中、所有 `add_subdirectory()` 之前调用。

### `CTEST_OUTPUT_ON_FAILURE` 不生效

**症状**：设置了 `CTEST_OUTPUT_ON_FAILURE=1`，但失败测试的输出仍然不显示。

**原因**：这通常发生在使用 IDE 插件或包装脚本时，它们可能清除了环境变量，或使用了 `ctest` 的 `-Q` (quiet) 模式覆盖了输出设置。

**修复**：直接在命令行使用 `ctest --output-on-failure`，或在 `CMakePresets.json` 的 test presets 中设置 `"outputOnFailure": true`。后者更可靠，因为它不依赖 shell 环境变量。

## 扩展阅读

- [[03-targets-and-properties]] — 理解 Target 属性系统，许多测试属性共享相同的设计模式
- [[10-fetchcontent-dependency-management]] — `FetchContent` 机制详解，用于获取 GTest/Catch2
- [[14-cmake-presets]] — `CMakePresets.json` 完整指南，包括 configure、build、test 三种预设
- [[11-install-and-export-targets]] — 安装与导出，包含测试的安装策略
- [CMake 官方 CTest 文档](https://cmake.org/cmake/help/latest/manual/ctest.1.html)
- [GoogleTest CMake 集成指南](https://google.github.io/googletest/quickstart-cmake.html)
- [Catch2 CMake 集成](https://github.com/catchorg/Catch2/blob/devel/docs/cmake-integration.md)
- [CDash 用户手册](https://www.cdash.org/documentation/)
- [CTest fixtures 设计文档](https://cmake.org/cmake/help/latest/prop_test/FIXTURES_REQUIRED.html)
