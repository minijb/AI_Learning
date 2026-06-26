---
title: g++ 基础编译
updated: 2026-06-26
tags: [cpp, 编译器, g++, 基础编译]
---

# g++ 基础编译

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 45min
> 前置知识: [[01-environment-setup]]

---

## 1. 概念讲解

### 为什么需要这个？

安装好 [[01-environment-setup|g++ 环境]] 后，下一步就是学会把 `.cpp` 源文件变成可运行程序。`g++` 是 GCC 的 C++ 前端，负责读取源代码、检查语法和类型，最终生成可执行文件。本节聚焦最精简的用法：`g++ 源文件 -o 输出名`。

### 核心思想

`g++` 把「源码 → 可执行」自动化，默认会走完预处理、编译、汇编、链接四个阶段。

初学者最容易忽略的两点：

1. **编译期错误**：运行前被 `g++` 拦截，例如漏写分号、变量未声明。必须修掉才能生成可执行文件。
2. **运行期错误**：能编译通过，但执行时才暴露，例如除以零、数组越界。`g++` 无法在编译时捕获所有逻辑错误。

学会读 `g++` 报错格式——`文件:行号:列: error: 信息`——是本章最重要的目标之一。

---

## 2. 命令示例

### 2.1 最简编译与默认输出

假设当前目录已有 `hello.cpp`：

```cpp
// hello.cpp
#include <iostream>

int main() {
    std::cout << "Hello, g++!" << std::endl;
    return 0;
}
```

直接编译：

```bash
g++ hello.cpp
```

默认输出名：Windows 为 `a.exe`，Linux / macOS 为 `a.out`。默认名容易被下一次编译覆盖，建议用 `-o` 显式命名：

```bash
g++ hello.cpp -o hello
```

运行方式：

```bash
# Linux / macOS
./hello

# Windows
.\hello
```

> [!tip] `-o` 的用法
> `-o` 是选项，后面紧跟输出文件名。顺序也可以写成 `g++ -o hello hello.cpp`，但初学者建议 `g++ hello.cpp -o hello`，可读性更好。

---

### 2.2 查看 g++ 信息

```bash
g++ --version
```

输出类似：

```text
g++ (UCRT64, Built by MSYS2 project) 14.2.0
Copyright (C) 2024 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
```

常用信息命令汇总：

| 命令 | 作用 |
|------|------|
| `g++ --version` | 完整版本与版权信息 |
| `g++ -dumpversion` | 简短主版本号，例如 `14` |
| `g++ -dumpfullversion` | 完整版本号，例如 `14.2.0` |
| `g++ -v` | 详细配置、搜索路径、启动过程 |

> [!warning] `-v` 不是 `--version`
> `g++ -v` 会输出大量内部配置信息，包括头文件搜索路径、驱动程序版本等，排查环境问题时很有用；如果只是想知道版本号，用 `--version` 更清爽。

---

### 2.3 读取命令行参数

```cpp
// args.cpp
#include <iostream>

int main(int argc, char* argv[]) {
    std::cout << "参数个数: " << argc << std::endl;
    for (int i = 0; i < argc; ++i) {
        std::cout << "argv[" << i << "] = " << argv[i] << std::endl;
    }
    return 0;
}
```

编译运行：

```bash
g++ args.cpp -o args
./args foo bar
```

输出：

```text
参数个数: 3
argv[0] = ./args
argv[1] = foo
argv[2] = bar
```

`argv[0]` 是程序自身路径，真正的用户参数从 `argv[1]` 开始。

---

### 2.4 编译错误 vs 运行时错误

#### 编译错误示例

`bad_compile.cpp` 故意漏掉分号：

```cpp
// bad_compile.cpp
#include <iostream>

int main() {
    std::cout << "missing semicolon" << std::endl
    return 0;
}
```

执行：

```bash
g++ bad_compile.cpp -o bad_compile
```

`g++` 会报错：

```text
bad_compile.cpp: In function 'int main()':
bad_compile.cpp:6:12: error: expected ';' before 'return'
    6 |     return 0;
      |            ^
      |            ;
```

报错格式即 `文件:行号:列: error: 信息`。从第一个 `error:` 开始修，后续报错往往是它的连锁反应。

修掉错误——在 `std::endl` 后补分号——才能重新编译成功。

---

#### 运行时错误示例

`bad_run.cpp` 越界访问数组：

```cpp
// bad_run.cpp
#include <iostream>

int main() {
    int arr[3] = {1, 2, 3};
    std::cout << arr[100] << std::endl;  // 越界，行为未定义
    return 0;
}
```

执行：

```bash
g++ bad_run.cpp -o bad_run
./bad_run
```

它通常能编译通过，但运行时可能崩溃、输出垃圾值，或者看起来「正常」——这正是未定义行为的危险之处。排查这类问题需要调试器、消毒器等工具，详见 [[06-gpp-optimization-debugging]]。

---

### 2.5 认可的源文件扩展名

`g++` 通过扩展名判断文件类型。下面这些都会被当作 C++ 源文件处理：

| 扩展名 | 说明 |
|--------|------|
| `.cpp` | 最常用 |
| `.cc` | Linux 项目常见 |
| `.cxx` | 跨平台兼容 |
| `.C` | 大写 C，Unix 传统 |

注意 `.c` 是 C 语言源文件，`g++` 虽然也能编译它，但会按 C 规则而不是 C++ 规则处理。如果你确实需要把 `.c` 文件强制按 C++ 编译，可以加 `-x c++`：

```bash
g++ -x c++ hello.c -o hello
```

但初学者最安全的做法是：C++ 文件就用 `.cpp`。

---

## 3. 扩展阅读

- [GCC 官方在线手册 — C++ 方言选项](https://gcc.gnu.org/onlinedocs/gcc/C_002b_002b-Dialect-Options.html)
- [GCC 官方在线手册 — 整体选项](https://gcc.gnu.org/onlinedocs/gcc/Overall-Options.html)
- 继续学习：[[03-gpp-compilation-stages]]

---

## 常见陷阱

- **陷阱**：反复运行 `g++ hello.cpp`，每次都生成 `a.exe` / `a.out`，把上一次的程序覆盖掉。
  - 正确做法：养成 `g++ hello.cpp -o hello` 的习惯，显式命名输出文件。
- **陷阱**：Windows 下写 `./hello` 没反应，因为实际可执行文件是 `hello.exe`。
  - 正确做法：PowerShell / CMD 中运行 `.\hello`，系统会自动补全 `.exe`。
- **陷阱**：`-o` 后面漏写文件名，例如 `g++ hello.cpp -o`。
  - 正确做法：`g++` 会把下一个参数当作输出名，漏写会导致报错；始终把 `-o` 和名字成对使用。
- **陷阱**：把 C 代码文件命名为 `.c`，却期望 `g++` 按 C++ 编译。
  - 正确做法：C++ 项目统一使用 `.cpp`、`.cc`、`.cxx` 或 `.C` 扩展名；如果必须混用，显式加 `-x c++`。
- **陷阱**：看到 `g++` 报了很多 `error` 就慌，没注意它指出了行号和列号。
  - 正确做法：从第一个 `error:` 开始修，因为后续报错常常是第一个错误的连锁反应。
