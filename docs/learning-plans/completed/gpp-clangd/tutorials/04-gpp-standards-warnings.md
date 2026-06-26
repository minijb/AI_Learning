---
title: g++ 标准与警告
updated: 2026-06-26
tags: [cpp, 编译器, 标准, 警告]
---

# g++ 标准与警告

> [!info] 本节信息
> 所属计划: [[plan]]
> 预计耗时: 50min
> 前置知识: [[02-gpp-basic-compilation]]

---

## 1. 概念讲解

### 为什么需要这个？

C++ 每隔几年会发布一个新的国际标准：C++11、C++14、C++17、C++20、C++23。每个版本都会引入新语法和库，同一段代码用不同标准编译，结果可能截然不同：旧标准下直接编译失败，新标准下则正常通过。

另一方面，编译器检测到可疑但不违法的代码时，会发出**警告（warning）**。警告不会阻止生成可执行文件，却往往预示着 bug，例如变量声明了却没用、有符号和无符号整数混着比较、`double` 窄化成 `int` 等。

学会显式指定标准、合理打开警告，是写出可移植、健壮 C++ 代码的第一步。

### 核心思想

- 用 `-std=` 显式锁定 C++ 标准，避免依赖编译器默认值。不同版本 `g++` 的默认标准不一样，例如 GCC 11+ 默认使用 `gnu++17`。
- `c++17` 与 `gnu++17` 的区别：
  - `c++` 前缀是**严格 ISO C++**，跨平台、跨编译器时使用更保险。
  - `gnu++` 前缀额外允许 GNU 扩展，例如 `__int128`、变长数组、某些扩展语法。
- 警告 ≠ 错误。默认情况下 `g++` 仍会生成可执行文件。`-Werror` 可以把所有警告提升为错误，强制在编译期清零警告。
- `-Wall` 只是“一组常用警告”的开关，名字容易误导，并不等于“全部警告”。更全面的组合通常是 `-Wall -Wextra -Wpedantic`。

| 标准 | 发布年份 | 部分代表性特性 |
|------|---------|--------------|
| C++11 | 2011 | `auto`、范围 `for`、lambda、智能指针 |
| C++14 | 2014 | 泛型 lambda、`auto` 返回值推导 |
| C++17 | 2017 | 结构化绑定、`if constexpr`、文件系统库 |
| C++20 | 2020 | concept、module、`std::format`、coroutine |
| C++23 | 2023 | `std::print`、缩略 lambda、`if consteval` |

---

## 2. 命令示例

### 2.1 选择标准

先创建一个使用 `std::filesystem`（C++17 特性）的示例：

```cpp
// demo.cpp
#include <iostream>
#include <filesystem>

int main() {
    std::cout << std::filesystem::current_path() << '\n';
    return 0;
}
```

用 C++14 标准编译会失败：

```bash
g++ -std=c++14 demo.cpp -o demo
```

```text
demo.cpp: In function 'int main()':
demo.cpp:5:23: error: 'std::filesystem' has not been declared
    5 |     std::cout << std::filesystem::current_path() << '\n';
      |                       ^~~~~~~~~~
```

改用 C++17 即可通过：

```bash
g++ -std=c++17 demo.cpp -o demo
./demo       # Linux/macOS；Windows 用 demo.exe
```

```text
/home/alice/project
```

更多标准选项：

```bash
g++ -std=c++17 demo.cpp -o demo      # 严格 ISO C++17
g++ -std=gnu++20 demo.cpp -o demo    # C++20 + GNU 扩展
g++ -std=c++23 demo.cpp -o demo      # 需 g++ 13 及以上
```

### 2.2 警告全家桶

创建 `warn.cpp`，包含几个典型问题：

```cpp
// warn.cpp
#include <iostream>
#include <vector>

struct Point { int x; };

void foo(int a) {              // 参数 a 未使用
    int unused = 42;           // 变量 unused 未使用
    std::vector<int> v{1, 2, 3};

    struct Point p{.x = 1};    // C++17 下的 GNU 扩展：指定初始化

    for (int i = 0; i < v.size(); ++i) {  // 有符号 vs 无符号比较
        std::cout << v[i] << '\n';
    }

    double d = 3.14;
    int n{d};                  // 窄化转换

    std::cout << p.x << ' ' << n << '\n';
}

int main() {
    foo(0);
}
```

**默认编译**（现代 GCC 已经会报 `-Wnarrowing`）：

```bash
g++ warn.cpp -o warn
```

```text
warn.cpp: In function 'void foo(int)':
warn.cpp:17:11: warning: narrowing conversion of 'd' from 'double' to 'int' [-Wnarrowing]
   17 |     int n{d};                  // 窄化转换
      |           ^
```

**打开 `-Wall`**：

```bash
g++ -Wall warn.cpp -o warn
```

```text
warn.cpp: In function 'void foo(int)':
warn.cpp:12:23: warning: comparison of integer expressions of different signedness: 'int' and 'std::vector<int>::size_type' {aka 'long unsigned int'} [-Wsign-compare]
   12 |     for (int i = 0; i < v.size(); ++i) {  // 有符号 vs 无符号比较
      |                     ~~^~~~~~~~~~
warn.cpp:17:11: warning: narrowing conversion of 'd' from 'double' to 'int' [-Wnarrowing]
   17 |     int n{d};                  // 窄化转换
      |           ^
warn.cpp:7:9: warning: unused variable 'unused' [-Wunused-variable]
    7 |     int unused = 42;           // 变量 unused 未使用
      |         ^~~~~~
```

**再加 `-Wextra`**（只多出一类常见警告）：

```bash
g++ -Wall -Wextra warn.cpp -o warn
```

```text
warn.cpp:6:14: warning: unused parameter 'a' [-Wunused-parameter]
    6 | void foo(int a) {              // 参数 a 未使用
      |          ~~~~^
```

**再加 `-Wpedantic`**（更严格地遵循标准）：

```bash
g++ -Wall -Wextra -Wpedantic warn.cpp -o warn
```

```text
warn.cpp:10:20: warning: C++ designated initializers only available with '-std=c++20' or '-std=gnu++20' [-Wc++20-extensions]
   10 |     struct Point p{.x = 1};    // C++17 下的 GNU 扩展：指定初始化
      |                    ^
```

**把警告当错误**（编译失败）：

```bash
g++ -Wall -Wextra -Werror warn.cpp -o warn
```

```text
warn.cpp:12:23: error: comparison of integer expressions of different signedness: 'int' and 'std::vector<int>::size_type' {aka 'long unsigned int'} [-Werror=sign-compare]
   ...
cc1plus: all warnings being treated as errors
```

加了 `-Werror` 后，`warn` / `warn.exe` **不会生成**。这在 CI 中很有用，但接手老项目时要小心——旧代码往往 warning 很多，一开 `-Werror` 会直接编译失败。

### 2.3 单独开关某警告

有时你想只开某一类警告，或者关闭某个太吵的警告。

**关闭未使用变量警告**：

```bash
g++ -Wall -Wno-unused-variable warn.cpp -o warn
```

`-Wno-xxx` 是 `-Wxxx` 的反面：`-Wno-unused-variable` 会抑制 `unused-variable` 警告，其他 `-Wall` 警告仍然保留。

**只开符号比较警告**：

```bash
g++ -Wsign-compare warn.cpp -o warn
```

```text
warn.cpp: In function 'void foo(int)':
warn.cpp:12:23: warning: comparison of integer expressions of different signedness: 'int' and 'std::vector<int>::size_type' {aka 'long unsigned int'} [-Wsign-compare]
   12 |     for (int i = 0; i < v.size(); ++i) {  // 有符号 vs 无符号比较
      |                     ~~^~~~~~~~~~
```

日常开发可以先用 `-Wall -Wextra`，逐步清理；提交到 CI 时再用 `-Werror` 兜底，防止新增警告。遇到旧代码库，可以用 `-Wno-xxx` 临时关闭个别噪声，而不是整体降防。

---

## 3. 扩展阅读

- [GCC 警告选项手册](https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html)
- [GCC C++ 方言选项](https://gcc.gnu.org/onlinedocs/gcc/C_002b_002b-Dialect-Options.html)
- [cppreference C++ 编译器支持](https://en.cppreference.com/w/cpp/compiler_support)
- [C++ 标准草案（公开免费）](https://open-std.org/jtc1/sc22/wg21/docs/standards)
- 继续学习：[[05-gpp-multiple-files]]

---

## 常见陷阱

- **以为 `-Wall` 是全部警告** → 它只是“一组常用警告”。要更全，加 `-Wextra`；要严格检查标准合规，再加 `-Wpedantic`。
- **`-Werror` 让旧代码无法编译** → 老项目往往有大量历史警告。建议在 CI 对新代码启用，或先清理再打开，不要一上来就全局加。
- **不同 g++ 版本默认标准不同** → GCC 9 默认 `gnu++14`，GCC 11 默认 `gnu++17`。不指定 `-std=` 时，同一段代码换台机器可能从“能编译”变“报错”。始终显式指定。
- **`gnu++` 扩展代码换到严格标准下报错** → 用 `g++ -std=gnu++17` 能过的代码，改用 `g++ -std=c++17` 可能因为禁用了 GNU 扩展而失败。跨平台项目建议以 `c++` 前缀为基准测试。
