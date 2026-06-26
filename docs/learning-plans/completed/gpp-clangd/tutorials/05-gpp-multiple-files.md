---
title: g++ 多文件与头文件
updated: 2026-06-26
tags: [cpp, 编译器, 多文件编译, 头文件]
aliases: [g++ 多文件编译]
---

# g++ 多文件与头文件

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 60min
> 前置知识: [[03-gpp-compilation-stages]]

---

## 1. 概念讲解

### 为什么需要这个？

当程序只有几十行时，把所有代码塞进一个 `main.cpp` 没问题。但随着项目变大，单文件会带来两个问题：

1. **编译时间爆炸**：改动一行代码就要重新编译整个项目。
2. **代码组织混乱**：函数、类、全局变量挤在一起，难以维护和复用。

把程序拆成多个 `.cpp` 文件，并用头文件 `.h` / `.hpp` 共享接口，是解决这两个问题的标准做法。

### 核心思想

C++ 采用**分离编译模型（separate compilation）**：

- 每个 `.cpp` 源文件被编译器独立翻译成 `.o` / `.obj` 目标文件。
- 链接器把所有目标文件拼起来，生成最终可执行文件。
- 头文件只放**声明（declaration）**，告诉编译器「某个符号存在、签名是什么」；源文件才放**定义（definition）**，真正分配存储和实现逻辑。

这样，修改 `math.cpp` 时，只需重新编译 `math.cpp` → `math.o`，再链接一次即可，不需要碰 `main.cpp`。

> [!tip] 声明 vs 定义
> - **声明**：`int add(int, int);` —— 只说明函数名、参数、返回值。
> - **定义**：`int add(int a, int b) { return a + b; }` —— 包含函数体，是真正实现。
> 一个符号可以被多次声明，但只能有一处定义（`inline`、模板等例外先不展开）。

---

## 2. 命令示例

下面用一个三文件小项目演示。项目结构如下：

```text
project/
├── math.hpp      # 声明 add 函数
├── math.cpp      # 定义 add 函数
└── main.cpp      # 调用 add 函数
```

### 2.1 源文件内容

`math.hpp`：

```cpp
#pragma once

int add(int a, int b);
```

`math.cpp`：

```cpp
#include "math.hpp"

int add(int a, int b) {
    return a + b;
}
```

`main.cpp`：

```cpp
#include "math.hpp"
#include <iostream>

int main() {
    int result = add(2, 3);
    std::cout << "2 + 3 = " << result << std::endl;
    return 0;
}
```

> [!warning] 头文件不要写进命令行
> 头文件通过 `#include` 在预处理阶段被展开，**不**应该出现在 `g++` 命令行里。下面所有命令都只有 `.cpp` 或 `.o` 文件。

### 2.2 一次编译多个源文件

最简单的方式是把所有 `.cpp` 一起传给 `g++`：

```bash
g++ main.cpp math.cpp -o prog
./prog
```

预期输出：

```text
2 + 3 = 5
```

这种方式适合快速验证小项目。它内部其实仍然先编译每个 `.cpp` 再链接，只是被 `g++` 自动串起来了。

### 2.3 分离编译 + 链接

大项目里更常见的做法是两步走：先各自编译成目标文件，再链接。

```bash
# 第一步：把 math.cpp 编译成 math.o
g++ -c math.cpp -o math.o

# 第二步：把 main.cpp 编译成 main.o
g++ -c main.cpp -o main.o

# 第三步：把两个目标文件链接成可执行文件 prog
g++ main.o math.o -o prog
```

运行：

```bash
./prog
```

预期输出：

```text
2 + 3 = 5
```

现在假设你发现 `add` 的实现有 bug，只要改 `math.cpp`，然后只需要重跑第一步和第三步：

```bash
g++ -c math.cpp -o math.o
g++ main.o math.o -o prog
```

`main.o` 完全不需要重新生成，这就是分离编译省时间的本质。

> [!tip] 真实项目怎么做
> 手写这些命令容易漏文件，所以真实项目会用 `make`、`ninja` 或 `cmake`。但理解 `g++ -c` 和链接的区别，是看懂任何构建系统的基础。

### 2.4 头文件搜索路径 `-I`

项目变大后，头文件通常会集中到 `include/` 目录，源文件放到 `src/` 目录。例如：

```text
project/
├── include/
│   └── math.hpp
├── src/
│   └── math.cpp
└── main.cpp
```

此时 `main.cpp` 里仍然写 `#include "math.hpp"`，但需要告诉 `g++` 去 `include/` 目录里找：

```bash
g++ -I./include main.cpp src/math.cpp -o prog
```

`-I` 后面紧跟目录路径，中间可以有空格也可以没有（`-I./include` 和 `-I ./include` 等价）。

`-I` 可以写多次：

```bash
g++ -I./include -I./third_party main.cpp src/math.cpp -o prog
```

多次 `-I` 的顺序**影响搜索优先级**：编译器按从左到右的顺序在各个目录里查找，先找到就用。

> [!info] `include "..."` 与 `include <...>` 的区别
> - `#include "math.hpp"`：先在源文件所在目录找，再按 `-I` 指定的路径找，最后找系统目录。
> - `#include <iostream>`：只在 `-I` 路径和系统默认目录（如 `/usr/include`）里找，不先搜当前目录。
> 对于自己写的头文件，统一用 `"..."`。

### 2.5 头文件守卫 / `#pragma once`

头文件可能被多个 `.cpp` 间接包含。如果同一份声明被展开两次，编译器会报「重定义」错误。防止重复包含有两种写法。

#### 传统写法：包含守卫（include guard）

```cpp
#ifndef MATH_HPP
#define MATH_HPP

int add(int a, int b);

#endif // MATH_HPP
```

宏名 `MATH_HPP` 通常用文件名的大写形式，确保全局唯一。预处理器第一次读到这个文件时，`MATH_HPP` 未定义，于是定义它并保留中间内容；后续再读到同一文件时，`#ifndef` 为假，中间内容被跳过。

#### 现代写法：`#pragma once`

```cpp
#pragma once

int add(int a, int b);
```

`#pragma once` 是编译器层面的约定：同一个物理文件只被包含一次。它更短、更不容易写错宏名，是现代项目的主流选择。本教程的示例统一使用 `#pragma once`。

> [!tip] 两种写法哪个好
> - `#pragma once` 简洁，99% 的场景够用。
> - 包含守卫是标准 C++，在极少数特殊文件系统或拷贝头文件的场景更可靠。
> - 两者不要混用，选一个即可。

### 2.6 静态库（可选进阶）

当某个模块很稳定、被很多程序复用时，可以把它打包成**静态库**（`.a` 文件）。

继续上面的项目，先把 `math.o` 打包：

```bash
ar rcs libmath.a math.o
```

- `ar`：归档工具。
- `r`：替换已存在的成员。
- `c`：创建库文件（如果不存在）。
- `s`：写入符号索引，加快链接速度。

编译 `main.cpp` 时使用这个库：

```bash
g++ main.cpp -L. -lmath -o prog
```

- `-L.`：告诉链接器在当前目录（`.`）找库。
- `-lmath`：链接名为 `math` 的库。链接器会自动补全为 `libmath.a`（去掉 `lib` 前缀和 `.a` 后缀）。

运行效果与之前完全相同。

> [!info] 库命名规则
> `-lxxx` 对应文件 `libxxx.a`（静态库）或 `libxxx.so` / `libxxx.dll`（动态库）。`-L` 指定库所在目录，`-l` 指定库名。

---

## 3. 扩展阅读

- [GCC 目录选项手册（-I / -L）](https://gcc.gnu.org/onlinedocs/gcc/Directory-Options.html)
- [GCC 链接选项手册（-l / -L / -static）](https://gcc.gnu.org/onlinedocs/gcc/Link-Options.html)
- [[06-gpp-optimization-debugging|继续学习：g++ 优化与调试]]

---

## 常见陷阱

- **把 `.h` 写进编译命令**：头文件由 `#include` 展开，不需要传给 `g++`。写成 `g++ main.cpp math.hpp` 会报错。

- **声明与定义签名不一致**：
  - `math.hpp` 写 `int add(int, int);`
  - `math.cpp` 写 `double add(int a, int b)`
  - 编译 `math.cpp` 可能通过，但链接 `main.o` 时会报 `undefined reference to add(int, int)`。

- **忘记头文件守卫或 `#pragma once`**：多个 `.cpp` 都包含同一个头文件时，会出现「重定义」编译错误。

- **`undefined reference` 误当成编译错误**：这句话出现在链接阶段，说明编译器已经通过了，但链接器找不到某个函数或变量的定义。常见原因是漏写源文件、漏链库、或声明定义签名不匹配。

- **`-l` 的命名规则混淆**：`libmath.a` 对应 `-lmath`，不是 `-llibmath` 也不是 `-lmath.a`。`-L` 指定目录，`-l` 指定库名。

- **修改 `.cpp` 后没重新链接**：分离编译时，如果只编译了 `.cpp` → `.o` 但没执行最后的链接命令，运行的仍然是旧的可执行文件。

- **`#include <>` 与 `#include ""` 用反**：自己的头文件用 `<>` 时，如果目录没通过 `-I` 指定，会找不到；系统头文件用 `""` 通常也能工作，但语义不标准。
