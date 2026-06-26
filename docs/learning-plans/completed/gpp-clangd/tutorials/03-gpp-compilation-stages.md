---
title: g++ 编译四阶段
updated: 2026-06-26
tags: [cpp, 编译器, g++, 编译阶段]
---

# g++ 编译四阶段

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 60min
> 前置知识: [[02-gpp-basic-compilation]]

---

## 1. 概念讲解

### 为什么需要这个？

执行 `g++ demo.cpp -o demo` 时，屏幕上可能只闪过一行命令，但 `g++` 内部已经把工作拆成了四步：展开 `#include`、把 C++ 翻译成汇编、把汇编变成机器码、最后把机器码拼成可执行文件。

理解这四个阶段的价值在于：

- **定位错误来源**：看到报错时，能判断它来自预处理、编译、汇编还是链接，修起来更有方向。
- **支撑分离编译**：大项目里每个 `.cpp` 先独立编成 `.o`，再一起链接，能避免重复编译。这是 [[05-gpp-multiple-files]] 的核心。
- **观察优化效果**：用 `-S` 看不同优化级别生成的汇编差异，是 [[06-gpp-optimization-debugging]] 的常用入口。

### 核心思想

`g++` 把「源码 → 可执行」拆成四个顺序阶段，每个阶段消费上一阶段的产物，输出新的中间文件。

```mermaid
flowchart LR
    A["demo.cpp<br/>源文件"] -->|"预处理<br/>-E"| B["demo.ii<br/>预处理后的 C++"]
    B -->|"编译<br/>-S"| C["demo.s<br/>汇编代码"]
    C -->|"汇编<br/>-c"| D["demo.o<br/>目标文件"]
    D -->|"链接<br/>无选项"| E["demo<br/>可执行文件"]
```

| 阶段 | 选项 | 输入 | 输出 | 主要工作 |
|------|------|------|------|----------|
| 预处理 | `-E` | `.cpp` | `.ii` | 展开 `#include`、替换 `#define`、处理条件编译 |
| 编译 | `-S` | `.ii` | `.s` | 将 C++ 翻译成汇编代码 |
| 汇编 | `-c` | `.s` | `.o` | 将汇编翻译成机器码目标文件 |
| 链接 | 无 | `.o` | 可执行文件 | 合并目标文件、解析符号、链接标准库 |

> [!tip] 中间产物扩展名
> `.ii` 是 C++ 预处理后的产物；C 语言对应的是 `.i`。`.s` 是汇编文件，`.o`（Windows 上常为 `.obj`）是目标文件。

---

## 2. 命令示例

先准备一个示例源文件 `demo.cpp`：

```cpp
// demo.cpp
#include <iostream>

#define GREETING "Hello, g++ stages!"

int square(int n) {
    int result = 0;
    for (int i = 0; i < n; ++i) {
        result += n;
    }
    return result;
}

void say_hello() {
    std::cout << GREETING << std::endl;
}

int main() {
    say_hello();
    std::cout << "3^2 = " << square(3) << std::endl;
    return 0;
}
```

这个文件同时用到了 `#include`、`#define` 和函数调用，适合观察每个阶段的变化。

### 1. 预处理 `-E`

```bash
g++ -E demo.cpp
```

默认输出到终端。你会看到 `iostream` 被完整展开，宏 `GREETING` 被替换成字符串，注释被去掉。

```bash
g++ -E demo.cpp -o demo.ii
```

把预处理结果保存到 `demo.ii`。这个文件通常很大（可能几千甚至上万行），因为标准头文件被全部展开了。

```bash
wc -l demo.ii
```

预期输出类似：

```text
4623 demo.ii
```

> [!warning] 不要提交 `.ii`
> `.ii` 是中间产物，体积大且包含系统头文件路径，**不要**把它提交到版本库。可以在 `.gitignore` 里忽略 `*.ii`、`*.s`、`*.o`。

### 2. 编译 `-S`

```bash
g++ -S demo.cpp -o demo.s
```

生成汇编文件 `demo.s`。你可以用 `head` 瞄一眼：

```bash
cat demo.s | head -n 20
```

预期能看到类似下面的汇编头部（平台不同会略有差异）：

```text
	.file	"demo.cpp"
	.text
	.globl	_Z6squarei
	.type	_Z6squarei, @function
_Z6squarei:
.LFB0:
	.cfi_startproc
	endbr64
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	movl	%edi, -20(%rbp)
	movl	$0, -4(%rbp)
	movl	$0, -8(%rbp)
```

#### 对比优化前后的汇编

```bash
g++ -S demo.cpp -o demo_no_opt.s
g++ -S -O2 demo.cpp -o demo_o2.s
```

再比较行数：

```bash
wc -l demo_no_opt.s demo_o2.s
```

典型结果：

```text
  142 demo_no_opt.s
   89 demo_o2.s
```

`-O2` 会删除冗余代码、把循环改成乘法、内联小函数，让汇编更短。例如 `square(3)` 里的循环可能被直接优化掉，甚至计算出常量 `9`。

### 3. 汇编 `-c`

```bash
g++ -c demo.cpp -o demo.o
```

生成目标文件 `demo.o`。它是二进制机器码，不能直接运行：

```bash
./demo.o
```

会报错：

```text
bash: ./demo.o: cannot execute binary file: Exec format error
```

`.o` 文件只包含本文件的机器码和未解析的符号引用（例如它知道要调用 `std::cout`，但还不知道 `std::cout` 具体在哪里），必须交给链接器。

你可以用 `file` 命令确认类型：

```bash
file demo.o
```

```text
demo.o: ELF 64-bit LSB relocatable, x86-64, version 1 (SYSV), not stripped
```

### 4. 链接

```bash
g++ demo.o -o demo
./demo
```

预期输出：

```text
Hello, g++ stages!
3^2 = 9
```

这一步把 `demo.o` 和 C++ 标准库（`libstdc++`）、启动代码等拼在一起，解析所有外部符号，最终生成可执行文件。

### 5. 一次走完 vs 逐步停

不带任何阶段选项时，`g++` 会一口气走完四个阶段：

```bash
g++ demo.cpp -o demo
```

带 `-E`、`-S`、`-c` 中的任意一个时，`g++` 会在对应阶段停下来：

| 命令 | 停止阶段 | 产物 |
|------|----------|------|
| `g++ -E demo.cpp` | 预处理 | 标准输出 / `.ii` |
| `g++ -S demo.cpp` | 编译 | `.s` |
| `g++ -c demo.cpp` | 汇编 | `.o` |
| `g++ demo.cpp -o demo` | 链接 | 可执行文件 |

> [!tip] 组合使用
> 阶段选项可以和 `-std`、`-Wall`、`-O2`、`-g` 等选项一起用。例如 `g++ -std=c++17 -Wall -O2 -S demo.cpp -o demo.s`。

---

## 3. 扩展阅读

- [GCC 官方在线手册 — 预处理选项](https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html)
- [GCC 官方在线手册 — 整体选项](https://gcc.gnu.org/onlinedocs/gcc/Overall-Options.html)
- [[02-gpp-basic-compilation]] —— 回顾 `g++` 基础编译命令
- [[05-gpp-multiple-files]] —— 分离编译正是 `-c` 的典型应用场景
- 继续学习：[[04-gpp-standards-warnings]]

---

## 常见陷阱

- **`-c`/`-S` 不会链接**：这两个选项只生成中间产物，不会调用链接器 → 想要可执行文件，必须再走一次无阶段选项的链接命令，如 `g++ demo.o -o demo`。
- **忘记最后还要链接 `.o`**：拿到 `.o` 后直接 `./demo.o` 会提示无法执行，必须用 `g++` 把它链接成可执行文件。
- **`.ii` 文件巨大别提交版本库**：预处理后的文件通常成千上万行，且包含系统路径，提交它没有意义。在 `.gitignore` 中忽略 `*.ii`。
- **优化后汇编可读性差**：`-O2`、`-O3` 会重排指令、内联函数、删除「看起来没用」的变量，初学者想读汇编时建议先用 `-O0`。
