---
title: Bash 第一个脚本与运行方式
updated: 2026-06-15
---

# Bash 第一个脚本与运行方式

> 所属计划: [[plan|Shell 脚本编程：Bash、Zsh 与 Fish]]
> 预计耗时: 45 分钟
> 前置知识: 基本命令行操作（cd、ls、cat、mkdir 等）

---

## 1. 概念讲解

### 什么是 Bash 脚本？

Bash 脚本本质上是一个**包含一系列命令的文本文件**。你在终端里逐行敲过的命令，都可以写入文件、一次执行。这就是脚本——把重复劳动变成一键完成。

类比：你每天早上的例行公事是"烧水 → 冲咖啡 → 烤面包"。写成脚本就像一个**自动化食谱**：把每一步写下来，交给 Bash 按顺序执行。

### 为什么需要脚本？

- **可重复**：同样的操作无需每次手动敲一遍
- **可分享**：团队共用同一套脚本，保证一致性
- **可组合**：小脚本拼接成大流程
- **可维护**：修改一个文件比重新记忆一堆命令更可靠

### Shell vs Bash

"Shell" 是命令解释器的通称。Bash 是其中最通用的一种。本教程基于 **Bash 4+**，Linux 和 macOS 均默认提供（macOS 自带的可能是 Bash 3，需手动升级或使用 Zsh）。

用以下命令确认当前版本：

```bash
bash --version
```

---

## 2. 代码示例

### 示例 1：Hello World

```bash
#!/usr/bin/env bash
# 这是我的第一个脚本
echo "Hello, World!"
echo "当前时间: $(date)"
```

> **运行环境要求**: Bash 4.x+（几乎所有 Linux 发行版和通过 Homebrew 安装的 macOS Bash）

**逐行解释：**

| 行                      | 含义                          |
| ---------------------- | --------------------------- |
| `#!/usr/bin/env bash`  | Shebang：告诉操作系统用 Bash 执行此文件  |
| `# 这是我的第一个脚本`          | 注释：`#` 开头的行为注释，不执行          |
| `echo "Hello, World!"` | 输出文字到终端                     |
| `$(date)`              | 命令替换：执行 `date` 命令，将其输出嵌入字符串 |

**运行方式：**

```bash
# 方式 1：直接执行（需要执行权限）
chmod u+x hello.sh
./hello.sh

# 方式 2：显式指定解释器（不需要执行权限）
bash hello.sh

# 方式 3：在当前 shell 中执行（会影响当前环境）
source hello.sh
# 或
. hello.sh
```

**预期输出：**

```text
Hello, World!
当前时间: Sun Jun 15 14:30:00 CST 2026
```

### 示例 2：带变量的问候脚本

```bash
#!/usr/bin/env bash

name="Alice"
greeting="你好"

echo "${greeting}, ${name}!"
echo "你的主目录是: ${HOME}"
echo "当前工作目录: $(pwd)"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
chmod u+x greet.sh && ./greet.sh
```

**预期输出：**

```text
你好, Alice!
你的主目录是: /home/alice
当前工作目录: /home/alice/projects
```

### 示例 3：调试模式

```bash
#!/usr/bin/env bash
set -x  # 开启调试：每行执行前先打印
name="Bob"
echo "Hello, ${name}"
set +x  # 关闭调试
echo "调试已关闭"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
# 方式 1：脚本内置 set -x
bash debug-demo.sh

# 方式 2：命令行指定
bash -x debug-demo.sh
```

**预期输出：**

```text
+ name=Bob
+ echo 'Hello, Bob'
Hello, Bob
+ set +x
调试已关闭
```

---

## 3. 练习

### 练习 1: 创建并运行你的第一个脚本

创建一个脚本 `myinfo.sh`，输出以下信息（每行一项）：
- 当前用户名
- 当前日期和时间
- 当前工作目录
- 一条欢迎语：`欢迎来到 Shell 脚本世界, <用户名>!`

> 提示：用户名用 `whoami`，日期用 `date`，目录用 `pwd`。

### 练习 2: 注释与调试

在 `myinfo.sh` 中：
1. 给每个输出语句添加注释说明它输出什么
2. 在脚本开头添加一个多行注释，描述这个脚本的用途
3. 分别用正常模式和调试模式运行脚本，观察 `bash -x` 的输出差异

### 练习 3: Shebang 对比（可选）

1. 分别用 `#!/usr/bin/env bash`、`#!/bin/bash`、`#!/bin/sh` 作为 shebang 运行同一个脚本
2. 如果脚本里有 `echo ${BASH_VERSION}`，观察三种 shebang 下输出的版本号
3. 思考：为什么推荐 `#!/usr/bin/env bash` 而不是硬编码路径？

---

## 4. 参考答案

> [!tip]- 练习 1 参考答案
> ```bash
> #!/usr/bin/env bash
> echo "用户名: $(whoami)"
> echo "当前时间: $(date)"
> echo "工作目录: $(pwd)"
> echo "欢迎来到 Shell 脚本世界, $(whoami)!"
> ```
>
> 如果你的脚本能正确输出四项信息，就是正确的。不要求输出格式与参考答案完全一致。

> [!tip]- 练习 2 参考答案
> ```bash
> #!/usr/bin/env bash
>
> # ===========================================
> # myinfo.sh
> # 用途: 输出当前用户的系统信息摘要
> # 作者: [你的名字]
> # ===========================================
>
> # 输出当前登录用户名
> echo "用户名: $(whoami)"
>
> # 输出当前日期和时间
> echo "当前时间: $(date)"
>
> # 输出当前工作目录
> echo "工作目录: $(pwd)"
>
> # 欢迎语
> echo "欢迎来到 Shell 脚本世界, $(whoami)!"
> ```
>
> 调试模式运行（`bash -x myinfo.sh`）会看到每行命令前有 `+` 前缀，显示 Bash 实际执行的内容，包括变量展开后的结果。

> [!tip]- 练习 3 参考答案
> `#!/usr/bin/env bash` 推荐原因是**可移植性**。不同系统的 Bash 安装路径可能不同：
> - Linux: 通常在 `/bin/bash`
> - macOS (Homebrew): `/usr/local/bin/bash` 或 `/opt/homebrew/bin/bash`
> - FreeBSD: `/usr/local/bin/bash`
>
> `env` 命令会在 `PATH` 中查找 `bash`，找到第一个即可，因此脚本在不同系统上都能运行。
>
> `#!/bin/sh` 在不同系统上指向不同的 shell（在 Ubuntu 上指向 `dash`，在 CentOS 上指向 `bash`），可能导致脚本行为不一致。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 5. 扩展阅读

- [Bash 官方文档 - Getting Started](https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files.html)
- [What is the preferred Bash shebang? - Stack Overflow](https://stackoverflow.com/questions/10376206/what-is-the-preferred-bash-shebang)
- [[02-bash-variables-io|下一节: Bash 变量、输入输出与引号]]
- [[plan|返回学习计划总览]]

---

## 常见陷阱

- **忘记 `chmod +x` 直接 `./script.sh`**：报错 `Permission denied`。必须先 `chmod u+x script.sh` 授予执行权限。
- **Shebang 写错**：`#!` 不能有空格。写成 `# !/usr/bin/env bash` 会导致脚本被当前 shell（不一定是 Bash）执行。
- **用 `sh script.sh` 而非 `bash script.sh`**：如果你的脚本用了 Bash 特有语法（如 `[[ ]]`），而系统 `sh` 指向 `dash`，会报语法错误。明确用 `bash`。
- **Windows 换行符 `\r\n`**：如果脚本在 Windows 上编辑后传到 Linux，Vim 底部显示 `[dos]`，运行时报 `bash: ./script.sh: /bin/bash^M: bad interpreter`。用 `dos2unix script.sh` 或 `sed -i 's/\r$//' script.sh` 修复。
- **调试信息看不懂**：`bash -x` 会显示 `+` 前缀的执行行。`+` 多一层表示在子 shell 中执行。关注变量的实际展开值，忽略 `+` 符号本身。
