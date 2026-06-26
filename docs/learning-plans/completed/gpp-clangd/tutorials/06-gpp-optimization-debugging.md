---
title: g++ 优化与调试
updated: 2026-06-26
tags: [cpp, 编译器, 优化, 调试]
---

# g++ 优化与调试

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 50min
> 前置知识: [[04-gpp-standards-warnings]]

---

## 1. 概念讲解

### 为什么需要这个？

程序能编译通过只是第一步。真正上线前还要解决两个问题：**运行得够快/够小**，以及**出错时定位得了根因**。

`g++` 提供 `-O` 优化级别、`-g` 调试信息开关和 `-fsanitize=*` 运行时检查。理解取舍后，你能：

- 发布版本获得更好性能；
- 调试版本保留变量和行号；
- 开发阶段提前发现内存错误和未定义行为。

### 核心思想

> **优化生成更高效的机器码；调试保留源码映射。二者天然冲突，不要同时把 `-O2` 和 `-g` 当作万能组合。**

编译器优化是“用编译时间换运行时间/体积”：级别越低，编译越快、调试越方便，但运行越慢；级别越高，运行越快，调试信息越可能对不上源码。

消毒器在编译时插入检查代码，运行时监控内存访问和未定义行为，代价是运行变慢、内存增加，因此**只用于开发测试，不用于发布**。

---

## 2. 命令示例

### 2.1 优化级别对比

创建 `bench.cpp`：

```cpp
#include <iostream>

long long fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

int main() {
    const int n = 42;
    std::cout << "fib(" << n << ") = " << fib(n) << std::endl;
    return 0;
}
```

编译并计时（Windows PowerShell 用 `Measure-Command { .\bench_o0 }`；Git Bash / MSYS2 / WSL 用 `time ./bench_o0`）：

```bash
g++ -O0 bench.cpp -o bench_o0 && time ./bench_o0
g++ -O2 bench.cpp -o bench_o2 && time ./bench_o2
g++ -O3 bench.cpp -o bench_o3 && time ./bench_o3
```

典型输出：

```text
# -O0               # -O2               # -O3
fib(42) = 267914296 fib(42) = 267914296 fib(42) = 267914296
real 2.845s         real 0.975s         real 0.920s
```

#### 各级别含义

| 级别 | 含义 | 典型用途 |
|------|------|----------|
| `-O0` | 不优化（默认），编译最快，调试最友好 | 开发、调试 |
| `-O1` | 基本优化，不显著增加编译时间 | 编译时间敏感 |
| `-O2` | 常用发布优化，开启大部分安全优化 | **发布版本默认选择** |
| `-O3` | 激进优化，可能增加体积 | 计算密集型程序 |
| `-Os` | 优化目标为**减小体积** | 嵌入式、大小敏感 |
| `-Ofast` | 比 `-O3` 激进，允许破坏部分浮点语义 | 数值精度不敏感的高性能计算 |

`-Ofast` 会启用 `-ffast-math`，可能改变浮点结果。如需严格 IEEE-754 行为，不要使用 `-Ofast`。

#### 用 `-S` 看汇编差异

呼应 [[03-gpp-compilation-stages]]，停在汇编阶段：

```bash
g++ -O0 -S bench.cpp -o bench_o0.s
g++ -O2 -S bench.cpp -o bench_o2.s
wc -l bench_o0.s bench_o2.s
```

```text
  85 bench_o0.s
  45 bench_o2.s
```

优化级别越高，代码越紧凑、越不像源码的一一对应，这正是调试困难和性能提升的来源。

---

### 2.2 调试信息与 GDB

创建 `prog.cpp`：

```cpp
#include <iostream>

int add(int a, int b) { return a + b; }

int main() {
    int x = 3, y = 5;
    int sum = add(x, y);
    std::cout << "sum = " << sum << std::endl;
    return 0;
}
```

编译并启动 GDB：

```bash
g++ -g -O0 prog.cpp -o prog_dbg
gdb ./prog_dbg
```

GDB 常用命令：

| 命令 | 简写 | 作用 |
|------|------|------|
| `break main` | `b main` | 在 `main` 入口设断点 |
| `run` | `r` | 运行程序 |
| `next` | `n` | 执行下一行（不进入函数） |
| `step` | `s` | 进入函数内部 |
| `print 变量` | `p` | 查看变量值，如 `p sum` |
| `backtrace` | `bt` | 查看调用堆栈 |
| `continue` | `c` | 继续运行到下一个断点 |
| `quit` | `q` | 退出 GDB |

示例会话：

```text
(gdb) break main
Breakpoint 1 at 0x4013c0: file prog.cpp, line 6.
(gdb) run
Breakpoint 1, main () at prog.cpp:6
6           int x = 3, y = 5;
(gdb) next
7           int sum = add(x, y);
(gdb) step
add (a=3, b=5) at prog.cpp:3
3           return a + b;
(gdb) print a
$1 = 3
(gdb) continue
sum = 8
[Inferior 1 (process 12345) exited normally]
```

若用 `g++ -g -O2` 编译，GDB 里可能看到变量 `<optimized out>`、`next` 行号乱跳、断点停不到位。**需要源码级调试时，优先使用 `-O0 -g`。**

---

### 2.3 宏定义 `-D`

编译时用 `-D` 注入宏，无需改源码。创建 `main.cpp`：

```cpp
#include <iostream>

#ifdef DEBUG
    #define LOG(msg) std::cout << "[DEBUG] " << msg << std::endl
#else
    #define LOG(msg) ((void)0)
#endif

int main() {
    LOG("entering main");
    std::cout << "Hello, World!" << std::endl;
    LOG("leaving main");
    return 0;
}
```

编译运行：

```bash
g++ -DDEBUG main.cpp -o main_debug && ./main_debug
```

输出：

```text
[DEBUG] entering main
Hello, World!
[DEBUG] leaving main
```

关闭调试输出：

```bash
g++ main.cpp -o main_release && ./main_release
```

```text
Hello, World!
```

带值宏：

```bash
g++ -DITERATIONS=1000 bench.cpp -o bench
./bench
```

代码里可配合 `#ifdef` 或 `#if` 读取宏值。`<cassert>` 中的 `assert` 在定义 `NDEBUG` 时会完全消失，因此发布版本通常：`g++ -O2 -DNDEBUG main.cpp -o main_release`。

---

### 2.4 AddressSanitizer

创建故意越界的 `bug.cpp`：

```cpp
#include <iostream>

int main() {
    int arr[5] = {1, 2, 3, 4, 5};
    std::cout << "arr[10] = " << arr[10] << std::endl;
    return 0;
}
```

普通编译运行可能不会立即崩溃：

```bash
g++ bug.cpp -o bug_normal
./bug_normal
```

用 ASan 编译：

```bash
g++ -g -fsanitize=address bug.cpp -o bug
./bug
```

典型输出：

```text
==12345==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x7ffd1234abcd
READ of size 4 in thread T0
    #0 0x... in main bug.cpp:6
...
  This frame has 1 object(s):
    [32, 52) 'arr' (line 5) <== Memory access at offset 48 partially overflows this buffer
```

ASan 告诉你：错误类型 `stack-buffer-overflow`、出错位置 `bug.cpp:6`、越界对象 `'arr' (line 5)`。`-g` 让报错包含文件名和行号。

`-fsanitize=undefined`（UBSan）检测未定义行为，如整数溢出、除以零。两者可同时开启：

```bash
g++ -g -fsanitize=address,undefined bug.cpp -o bug_both
./bug_both
```

ASan/UBSan 让程序变慢、内存增加，**只用于开发测试**。发布版本用 `-O2`/`-O3`，不加 sanitizer；定位问题时先用 `-O0 -g -fsanitize=address`。

---

## 3. 扩展阅读

- [GCC 优化选项官方文档](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html)
- [GDB 用户手册](https://sourceware.org/gdb/current/onlinedocs/gdb/)
- [AddressSanitizer 官方文档](https://github.com/google/sanitizers/wiki/AddressSanitizer)
- [UndefinedBehaviorSanitizer 官方文档](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html)
- 继续学习：[[07-clangd-fundamentals]]

---

## 常见陷阱

- **陷阱：`-O2` 后变量在 GDB 里看不到**
  → 正确做法：调试版本用 `g++ -g -O0`，发布版本再用 `g++ -O2` 单独编译。

- **陷阱：发布版本忘了 `-DNDEBUG`，`assert` 留在生产代码里影响性能**
  → 正确做法：发布编译统一加 `-DNDEBUG`，或用构建工具自动区分 Debug/Release。

- **陷阱：把带 `-fsanitize=address` 的二进制直接发给用户**
  → 正确做法：sanitizer 只用于开发自测和 CI，发布版本去掉 sanitizer 并做单独测试。

- **陷阱：`-Ofast` 导致浮点结果和 `-O2` 不一致**
  → 正确做法：科学计算、金融计算等对数值精度敏感的代码避免 `-Ofast`；如需严格 IEEE-754 行为，用 `-O2` 或 `-O3`。

- **陷阱：ASan 报错后仍用 `-O2` 分析**
  → 正确做法：先用 `-O0 -g -fsanitize=address` 复现并定位，修复后再切回优化级别验证。
