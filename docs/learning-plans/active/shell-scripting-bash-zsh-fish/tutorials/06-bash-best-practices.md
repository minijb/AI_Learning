---
title: Bash 最佳实践：严格模式、错误处理与 ShellCheck
updated: 2026-06-15
tags: [shell, bash, best-practices, robustness]
---

# Bash 最佳实践：严格模式、错误处理与 ShellCheck

> 所属计划: Shell 脚本编程：Bash、Zsh 与 Fish
> 预计耗时: 60min
> 前置知识: [[02-bash-variables-io|Bash 变量与 I/O]]、[[03-bash-conditions|Bash 条件判断]]、[[04-bash-loops-functions|Bash 循环与函数]]、[[05-bash-arrays-strings-files|数组、字符串与文件操作]]

---

## 1. 概念讲解

能写出"跑得起来"的 Bash 脚本很容易，但写出"不出错、出错了能发现、发现了能处理"的脚本需要一套纪律。本节聚焦于生产级 Bash 脚本的核心实践。

### 为什么需要这个？

假设你写了一个备份脚本，某条 `rm` 命令因为路径变量为空变成了 `rm -rf /`——如果脚本没有严格模式，它会默默执行。或者一个关键命令失败了，但脚本继续执行后续步骤，把半成品当成品。这些都不是罕见场景。Bash 的默认行为是"宽容"的，这意味着**你必须在每份脚本中主动收紧约束**。

### 核心思想

- **严格模式** (`set -euo pipefail`)：让 Bash 在错误发生时立即停止，而不是默默继续。
- **trap**：在脚本退出或出错时执行清理逻辑，类似其他语言的 `finally` 块。
- **引号纪律**：永远给变量加引号，除非你明确需要单词拆分。
- **ShellCheck**：静态分析工具，能发现数百种常见错误和反模式。
- **幂等性**：脚本可以安全地重复执行，不会因为"已存在"而报错。

---

## 2. 代码示例

### 2.1 严格模式详解

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# strict_mode_demo.sh — 严格模式的各项含义

# === 严格模式三件套 ===
set -euo pipefail
# 可选：将 IFS 设为换行和制表符，避免空格引起的意外分词
IFS=$'\n\t'

# -e: 任何命令以非零状态退出时，脚本立即退出
echo "=== set -e 演示 ==="
# 下面的命令在 set -e 下会让脚本退出，注释掉以确保示例完整
# false
# echo "This line will NOT be printed if false is above"

# -u: 引用未定义变量时退出
echo "=== set -u 演示 ==="
# echo "$UNDEFINED_VAR"   # 取消注释会触发错误
echo "Using default: ${UNDEFINED_VAR:-safe}"

# -o pipefail: 管道中任一命令失败，整个管道失败
echo "=== set -o pipefail 演示 ==="
if echo "hello" | grep -q "world"; then
    echo "Found world"
else
    echo "Not found (pipefail captured the grep exit code)"
fi

# 如何临时允许命令失败
echo "=== 临时绕过 set -e ==="
set +e
false  # 这条命令失败不会退出
echo "Still running after false (set +e)"
set -e
# 更推荐的单条命令绕过：
false || true  # 明确允许失败
```

**运行方式:**
```bash
chmod u+x strict_mode_demo.sh && ./strict_mode_demo.sh
```

**预期输出:**
```text
=== set -e 演示 ===
=== set -u 演示 ===
Using default: safe
=== set -o pipefail 演示 ===
Not found (pipefail captured the grep exit code)
=== 临时绕过 set -e ===
Still running after false (set +e)
```

### 2.2 trap 错误处理与清理

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# trap_demo.sh — 使用 trap 处理错误和清理

set -euo pipefail

# === 定义清理函数 ===
cleanup() {
    local exit_code=$?
    echo "=== CLEANUP ==="
    echo "  Script exiting with code: $exit_code"
    # 清理临时文件
    rm -f /tmp/demo_temp_*
    echo "  Temporary files removed."
}
# trap EXIT：无论正常退出还是异常退出都执行
trap cleanup EXIT

# === 错误处理函数 ===
on_error() {
    local lineno="$1"
    local cmd="$2"
    echo "=== ERROR on line $lineno ===" >&2
    echo "  Command: $cmd" >&2
}
# trap ERR：只在命令失败时触发
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

# === 创建一些临时文件 ===
echo "Creating temporary files..."
touch /tmp/demo_temp_config
touch /tmp/demo_temp_data
echo "Working..."

# === 模拟命令错误（注释掉以正常完成）===
# false  # 触发 on_error

echo "Script completed successfully."
# 此时 cleanup 会被自动调用
```

**运行方式:**
```bash
chmod u+x trap_demo.sh && ./trap_demo.sh
```

**预期输出:**
```text
Creating temporary files...
Working...
Script completed successfully.
=== CLEANUP ===
  Script exiting with code: 0
  Temporary files removed.
```

### 2.3 引号纪律

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# quoting_demo.sh — 何时间引号，何时不加

set -euo pipefail

filename="my document.txt"
dir="some path"

# === 始终加引号的场景 ===

# 变量展开
echo "Safe: $filename"
cat "$filename" 2>/dev/null || echo "(file not found — expected)"

# 命令替换
current_dir="$(pwd)"
echo "Current dir: $current_dir"

# 在 [[ ]] 内部，变量可以不加引号（[[ ]] 不分词）
# 但在 [ ] 中必须加引号
if [[ -f $filename ]]; then   # OK in [[ ]]
    echo "File found"
fi
if [ -f "$filename" ]; then   # 必须加引号在 [ ] 中
    echo "File found"
fi

# === 何时不加引号 ===

# 模式匹配（在 [[ ]] 的 == 右侧）
if [[ "$filename" == *.txt ]]; then
    echo "It's a text file"
fi

# 需要单词拆分时（用数组代替更安全）
# 如果必须：在 set -euo 下，只有刻意这么做
# flags="-l -a"
# ls $flags  # 需要拆分 -l 和 -a，但这不太安全

# === 常见错误示范 ===

# ❌ 未加引号的变量在 [ ] 中可能出错
if [ -f $filename ]; then
    # 如果 filename 包含空格，这行会报错 "too many arguments"
    echo "This is broken when filename has spaces"
fi

# ❌ 未加引号的命令替换包含空格
# result=$(ls $dir)  # dir 含有空格时出错

# ✅ 正确
result="$(ls "$dir")"
echo "Result: $result"
```

**运行方式:**
```bash
chmod u+x quoting_demo.sh && ./quoting_demo.sh
```

### 2.4 幂等性设计

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# idempotent_demo.sh — 可重复安全执行的脚本模式

set -euo pipefail

echo "=== 幂等性设计模式 ==="

# 模式 1: mkdir -p（目录不存在才创建，已存在不报错）
mkdir -p ./output/logs
mkdir -p ./output/data
echo "Directories ensured."

# 模式 2: 使用标志文件避免重复操作
INIT_FLAG="./output/.initialized"

if [[ -f "$INIT_FLAG" ]]; then
    echo "Already initialized, skipping setup."
else
    echo "Running first-time setup..."
    echo "setup-complete" > "$INIT_FLAG"
fi

# 模式 3: 条件化符号链接
link_target="./config/production.conf"
link_name="./config/current.conf"

if [[ -L "$link_name" && $(readlink "$link_name") == "$link_target" ]]; then
    echo "Symlink already correct, skipping."
else
    rm -f "$link_name"
    ln -sf "$link_target" "$link_name"
    echo "Symlink updated."
fi

# 模式 4: 安全写入（先写临时文件，再原子 mv）
config_file="./output/config.txt"
tmp_file="${config_file}.tmp.$$"

echo "host=localhost" > "$tmp_file"
echo "port=3306" >> "$tmp_file"
mv "$tmp_file" "$config_file"
echo "Config written atomically."

# 模式 5: 条件化包安装（需要 apt-get/pacman 等，这里只是演示模式）
ensure_package() {
    local pkg="$1"
    if command -v "$pkg" &>/dev/null; then
        echo "Package '$pkg' already installed."
        return 0
    fi
    echo "Would install $pkg (uncomment the install line to actually do it)"
    # sudo apt-get install -y "$pkg"
}

ensure_package "curl"
ensure_package "jq"

echo ""
echo "Run this script multiple times — it won't fail or duplicate work."
```

**运行方式:**
```bash
chmod u+x idempotent_demo.sh && ./idempotent_demo.sh
```

### 2.5 输入验证范式

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# input_validation.sh — 输入验证的标准写法

set -euo pipefail

# === 参数数量检查 ===
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <name> <age> [city]" >&2
    exit 1
fi

name="$1"
age="$2"
city="${3:-Unknown}"

# === 类型/格式验证 ===

# 验证年龄是正整数
if [[ ! "$age" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: age must be a positive integer, got '$age'" >&2
    exit 2
fi

if ((age > 150)); then
    echo "Error: age seems unrealistic ($age)" >&2
    exit 2
fi

# 验证名字只含字母、空格和连字符
if [[ ! "$name" =~ ^[a-zA-Z[:space:]-]+$ ]]; then
    echo "Error: name contains invalid characters: $name" >&2
    exit 2
fi

# === 验证文件/路径 ===
config_file="${CONFIG_FILE:-./config.ini}"

if [[ ! -f "$config_file" ]]; then
    echo "Warning: config file not found at $config_file, using defaults." >&2
    # 使用默认值继续
fi

# === 验证依赖项 ===
for cmd in curl jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: required command '$cmd' not found in PATH." >&2
        exit 3
    fi
done

echo "=== Validated Input ==="
echo "  Name:   $name"
echo "  Age:    $age"
echo "  City:   $city"
echo "  Config: ${config_file:-<none>}"
echo ""
echo "All validations passed!"
```

**运行方式:**
```bash
chmod u+x input_validation.sh && ./input_validation.sh "Alice" 30 "Beijing"
```

**预期输出:**
```text
=== Validated Input ===
  Name:   Alice
  Age:    30
  City:   Beijing
  Config: ./config.ini

All validations passed!
```

### 2.6 ShellCheck 使用指南

**运行环境要求**: 已安装 [ShellCheck](https://www.shellcheck.net/)，可通过 `apt install shellcheck` 或 `brew install shellcheck` 安装。

```bash
#!/usr/bin/env bash
# shellcheck_demo.sh — ShellCheck 能捕获的常见问题

# SC2034: 声明但未使用的变量
unused_var="hello"

# SC2086: 未加引号的变量
# shellcheck disable=SC2086
echo $unused_var

# SC2164: cd 未检查失败
# cd /nonexistent

# SC2046: 命令替换在单词拆分位置
# for f in $(ls *.txt); do echo "$f"; done

# SC2236: 缺少 -n 检查
# if [ ! -z "$var" ]; then echo "has value"; fi

# SC2068: 数组未正确引用
arr=("a" "b c")
# shellcheck disable=SC2068
echo ${arr[@]}  # 应该是 "${arr[@]}"

# 正确写法
echo "${arr[@]}"
```

**运行方式:**
```bash
shellcheck shellcheck_demo.sh
# 或者在线检查: https://www.shellcheck.net/
```

---

## 3. 练习

### 练习 1: 加固现有脚本
以下脚本有至少 5 个安全问题。找出并修复它们，使其通过 ShellCheck 检查。

```bash
#!/bin/bash
# original backup script with issues
BACKUP_DIR=./backups
mkdir $BACKUP_DIR
for f in $(ls *.conf); do
cp $f $BACKUP_DIR/$f.bak
done
cd $BACKUP_DIR
tar -czf backup.tar.gz *.bak
rm *.bak
```

### 练习 2: 写一个带 trap 的安全临时文件脚本
写一个脚本，它：
- 创建临时目录 `/tmp/myapp_$$`
- 在临时目录中创建若干文件
- 模拟一些处理（sleep）
- 使用 trap 确保脚本退出（正常或异常）时自动清理临时目录
- 处理 `SIGINT`（Ctrl+C）信号，打印 "Interrupted!" 再退出
- 运行期间用 Ctrl+C 中断测试清理是否生效

### 练习 3: 写一个幂等的系统初始化脚本（可选）
写一个脚本 `init_env.sh`，它能在 Linux 系统上安全地多次执行：
- 创建目录 `~/projects`、`~/bin`、`~/logs`
- 如果 `~/bin` 不在 PATH 中，追加到 `~/.bashrc`
- 安装 `curl`、`git`、`jq`（如果未安装，用 apt-get）
- 克隆一个 Git 仓库到 `~/projects/dotfiles`，如果已存在则 `git pull`

---

## 3.5 参考答案

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

> [!tip]- 练习 1 参考答案
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> ```bash
> #!/usr/bin/env bash
> # fixed_backup.sh — 加固后的备份脚本
>
> set -euo pipefail
>
> BACKUP_DIR="./backups"
> mkdir -p "$BACKUP_DIR"
>
> shopt -s nullglob
> for f in *.conf; do
>     [[ -f "$f" ]] || continue
>     cp "$f" "$BACKUP_DIR/${f}.bak"
> done
>
> cd "$BACKUP_DIR"
> tar -czf backup.tar.gz *.bak
> rm *.bak
>
> echo "Backup completed: $BACKUP_DIR/backup.tar.gz"
> ```
>
> 修复点：
> 1. Shebang 改为 `#!/usr/bin/env bash`
> 2. 添加 `set -euo pipefail`
> 3. `mkdir` 改为 `mkdir -p`
> 4. 不用 `$(ls)` 解析文件，改用 glob `*.conf`
> 5. 所有变量加引号
> 6. 添加 `shopt -s nullglob` 防止无匹配时展开为字面 `*.bak`

> [!tip]- 练习 2 参考答案
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> ```bash
> #!/usr/bin/env bash
> # safe_temp.sh — 自动清理的临时文件脚本
>
> set -euo pipefail
>
> TMPDIR="/tmp/myapp_$$"
> INTERRUPTED=0
>
> cleanup() {
>     local exit_code=$?
>     echo ""
>     if [[ -d "$TMPDIR" ]]; then
>         rm -rf "$TMPDIR"
>         echo "Cleaned up: $TMPDIR"
>     fi
>     if [[ $INTERRUPTED -eq 1 ]]; then
>         exit 130  # 128 + SIGINT(2)
>     fi
>     exit $exit_code
> }
>
> on_sigint() {
>     echo ""
>     echo "Interrupted!"
>     INTERRUPTED=1
>     exit 130
> }
>
> trap cleanup EXIT
> trap on_sigint SIGINT
>
> echo "PID: $$ — Press Ctrl+C to test interrupt handling"
> echo "Temp dir: $TMPDIR"
>
> mkdir -p "$TMPDIR"
>
> # 创建一些临时文件
> for i in 1 2 3; do
>     echo "Content $i" > "$TMPDIR/file_$i.txt"
> done
>
> echo "Created 3 temp files. Doing work..."
> sleep 10
> echo "Work completed normally."
> ```
>
> **运行**: `./safe_temp.sh`，然后按 Ctrl+C 测试中断清理。

> [!tip]- 练习 3 参考答案（可选）
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> ```bash
> #!/usr/bin/env bash
> # init_env.sh — 幂等的系统初始化脚本
>
> set -euo pipefail
>
> echo "=== Environment Initialization ==="
>
> # — 目录 —
> for d in "$HOME/projects" "$HOME/bin" "$HOME/logs"; do
>     mkdir -p "$d"
>     echo "Directory ensured: $d"
> done
>
> # — PATH —
> if [[ ":$PATH:" != *":$HOME/bin:"* ]]; then
>     echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
>     echo "Added ~/bin to PATH in .bashrc (restart shell to apply)"
> else
>     echo "~/bin already in PATH, skipping."
> fi
>
> # — 包安装 —
> ensure_pkg() {
>     if dpkg -s "$1" &>/dev/null; then
>         echo "Package '$1' already installed."
>         return 0
>     fi
>     echo "Installing $1..."
>     sudo apt-get update -qq
>     sudo apt-get install -y "$1"
> }
>
> ensure_pkg curl
> ensure_pkg git
> ensure_pkg jq
>
> # — Git 仓库 —
> repo_dir="$HOME/projects/dotfiles"
> repo_url="https://github.com/example/dotfiles.git"
>
> if [[ -d "$repo_dir/.git" ]]; then
>     echo "Repository exists, pulling latest..."
>     git -C "$repo_dir" pull --ff-only
> else
>     echo "Cloning repository..."
>     git clone "$repo_url" "$repo_dir"
> fi
>
> echo ""
> echo "=== Initialization complete ==="
> ```
>
> **运行**: `./init_env.sh`，可多次执行验证幂等性。

---

## 4. 扩展阅读

- [Bash 严格模式详解](http://redsymbol.net/articles/unofficial-bash-strict-mode/)
- [ShellCheck Wiki — 所有规则的详细说明](https://www.shellcheck.net/wiki/)
- [Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html)
- [Greg's Wiki: Bash Pitfalls](https://mywiki.wooledge.org/BashPitfalls)
- [Better Bash Scripting in 15 Minutes](http://robertmuth.blogspot.com/2012/08/better-bash-scripting-in-15-minutes.html)

---

## 常见陷阱

- **只用 `set -e` 但忘记 `pipefail`**：管道左侧的命令失败被掩盖。`set -o pipefail` 确保管道中任一命令失败都导致退出。
- **在函数内改变 IFS 未恢复**：在函数内修改 `IFS` 后应在子 shell 中执行或不忘记恢复。推荐用 `local IFS=...`。
- **trap 不捕获 SIGINT 时 Ctrl+C 不清理**：默认 `trap EXIT` 会在 SIGINT 导致退出时触发，但如果你自定义了 SIGINT 处理，务必在清理函数中 exit。
- **`[[ ]]` 内字符串比较用 `>` 而非 `-gt`**：`>` 是字典序字符串比较，`-gt` 是整数比较。用混会导致意外。
- **ShellCheck 的 `disable` 注释滥用**：`# shellcheck disable=SC2086` 应该只是临时方案，修复根本问题而不是抑制警告。
- **`set -u` 下用 `${arr[@]}` 检查空数组**：空数组展开时 `-u` 不会触发（它展开为空，不是未定义）。但 `${arr}` 会触发。
- **在 `set -e` 下忽略命令失败的正确方式**：使用 `cmd || true` 而不是 `cmd; true`。后者不会阻止退出。
