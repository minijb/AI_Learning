---
title: Fish 脚本：非 POSIX 语法与交互友好设计
updated: 2026-06-15
---

# Fish 脚本：非 POSIX 语法与交互友好设计

> 所属计划: Shell 脚本编程：Bash、Zsh 与 Fish
> 预计耗时: 60min
> 前置知识: [[01-bash-first-script|Bash 第一个脚本]]、[[02-bash-variables-io|变量与 IO]]、[[03-bash-conditions|条件判断]]、[[04-bash-loops-functions|循环与函数]]

---

## 1. 概念讲解

### 为什么需要学 Fish？

Fish（**F**riendly **I**nteractive **Sh**ell）的设计哲学与 Bash/Zsh 完全不同：

- **不是 POSIX shell** — Fish 从零设计，不受 Bourne shell 历史包袱的约束。
- **交互体验优先** — 开箱即用：语法高亮、命令自动建议（基于历史）、Tab 补全（包含命令描述）。
- **脚本语法现代** — 没有 `$?`、没有 `[[` vs `[` 之争、没有复杂（且危险）的引号规则。
- **对新手友好** — 学习曲线远低于 Bash，配置只需修改 `config.fish` 和 `fish_prompt` 函数。

> [!warning] Fish **不是 POSIX shell**
> Fish 的脚本语法**与 Bash/Zsh 完全不兼容**。你不能用 Fish 运行 Bash 脚本，也不能在 Fish 中使用 `source ~/.bashrc`。如果你需要执行 POSIX shell 脚本，必须在脚本的 shebang 行指定 `#!/bin/bash` 或 `#!/bin/sh`，让内核用正确的解释器运行它——Fish 只是一个交互环境和它自己的脚本语言。

### 核心设计决策

| 特性 | Bash / Zsh | Fish |
|------|-----------|------|
| POSIX 兼容 | 是 / 大部分 | 否 |
| 变量赋值 | `var=value` | `set var value` |
| 变量引用 | 未引用时会分词 | 永不分词 |
| 变量类型 | 字符串 | 列表 |
| 数组索引 | `0` 开始 | `1` 开始 |
| 条件测试 | `[ ]` / `[[ ]]` | `test` 命令 |
| 流程控制 | `if … then … fi` | `if … end` |
| 循环 | `for i in …; do … done` | `for i in … … end` |
| 函数定义 | `func() { … }` | `function func … end` |
| 导出变量 | `export VAR=val` | `set -x VAR val` |
| 命令替换 | `` `cmd` `` / `$(cmd)` | `(cmd)` |

### `set`：Fish 的变量管理

Fish 中一切变量操作都通过 `set` 命令，没有 `=` 赋值符号：

```fish
set name "Alice"            # 创建变量
set -g name "Alice"         # 全局变量（-g = global）
set -l name "Alice"         # 局部变量（-l = local，函数内使用）
set -x PATH /usr/local/bin $PATH  # 导出为环境变量（-x = export）
set -U THEME "dark"         # 通用变量（-U = universal，跨会话持久化）
set -e name                 # 删除变量（-e = erase）
set -q name                 # 查询变量是否存在（-q = query，通过 $status 判断）
set --show name             # 显示变量的所有属性
```

Fish 的变量作用域有四种：
- **local**（`-l`）：只在当前代码块可见（函数或 `begin … end` 块）
- **global**（`-g`）：当前会话可见，不导出给子进程
- **exported**（`-x` 或 `--export`）：导出给子进程
- **universal**（`-U` 或 `--universal`）：跨所有 Fish 会话持久化，保存在 `~/.config/fish/fish_variables`

### 所有变量都是列表

在 Fish 中，**每个变量本质上都是一个列表**。"字符串"只是一个单元素列表。

```fish
set colors red green blue
echo $colors              # => red green blue
echo $colors[1]           # => red（索引从 1 开始！）
echo $colors[-1]          # => blue（负数从末尾取）
echo $colors[2..3]        # => green blue（范围切片）
echo (count $colors)      # => 3（列表长度）

# 追加元素
set -a colors yellow      # -a = append
echo $colors              # => red green blue yellow

# 构建空列表
set empty_list

# 单元素列表 = 字符串
set greeting "Hello"
echo $greeting            # => Hello
echo $greeting[1]         # => Hello（取单元素列表的第一项，还是 Hello）
```

### 列表与笛卡尔积展开

Fish 的列表展开使用**笛卡尔积语义**（cartesian product），这与 Bash 完全不同：

```fish
set bases A B
set nums 1 2

# $bases 和 $nums 的笛卡尔积
echo $bases$nums                    # => A1 A2 B1 B2
echo $bases-$nums                   # => A-1 A-2 B-1 B-2
```

这在构建文件列表时非常有用：
```fish
echo {src,test}/*.{cpp,h}           # 所有源文件和头文件
```

### 命令替换：`()` 而非 `$()`

Fish 的命令替换使用 `()`，而不是 Bash 的 `$()` 或反引号：

```fish
set files (ls *.txt)        # 将 ls 的输出捕获为列表，每行一个元素
set count (count $files)    # 命令替换可以嵌套
echo "Found $count files: $files"
```

多重命令替换示例：
```fish
set date_str (date +%Y-%m-%d)
set host (hostname)
echo "Report for $host on $date_str"

# 在字符串中内联使用
echo "Today is (date +%A)"
echo "Uptime: (uptime | string split -f5 ',')"
```

### 函数：`function … end`

Fish 的函数使用 `function … end` 块语法，不使用花括号：

```fish
function greet
    echo "Hello, $argv!"
end

greet "World"               # => Hello, World!
greet Alice Bob             # => Hello, Alice Bob!
```

**参数处理**：Fish 使用 `$argv` 获取所有参数，而非 `$1`、`$2`（这点与 POSIX shell 完全不同）：

```fish
function show_args
    echo "Total: "(count $argv)" args"
    for i in (seq (count $argv))
        echo "  arg $i = "$argv[$i]
    end
end

show_args a b c
# 输出:
# Total: 3 args
#   arg 1 = a
#   arg 2 = b
#   arg 3 = c
```

**`argparse` 参数解析**（Fish 内置的命令行参数解析器）：

```fish
function mytool --description "A sample tool"
    argparse 'h/help' 'n/name=' 'v/verbose' -- $argv
    or return

    if set -q _flag_help
        echo "Usage: mytool -n NAME [-v]"
        return
    end

    if set -q _flag_verbose
        echo "Verbose mode on"
    end

    echo "Hello, $_flag_name!"
end
```

### 条件判断：`test` + `if … end`

Fish 的条件判断不使用 `[ ]` 或 `[[ ]]`，而是使用 `test` 命令或直接检查命令的退出状态：

```fish
# 使用 test 命令（推荐）
if test -f "config.ini"
    echo "Config file exists"
end

if test "$count" -gt 10
    echo "Count > 10"
end

# 字符串比较
if test "$name" = "Alice"
    echo "Hi Alice"
end

# 直接检查命令退出状态
if grep -q "error" log.txt
    echo "Errors found!"
else
    echo "No errors"
end

# 逻辑组合
if test -f "$file" -a -r "$file"
    echo "File exists and is readable"
end

# 或者用 ; 分隔多个 test（更清晰）
if test -f "$file"; and test -r "$file"
    echo "File exists and is readable"
end

# not 关键字
if not test -d "$dir"
    echo "Not a directory"
end
```

`test` 的常见操作符：

| 操作符 | 含义 | 示例 |
|--------|------|------|
| `-f` | 是普通文件 | `test -f path` |
| `-d` | 是目录 | `test -d path` |
| `-x` | 可执行 | `test -x path` |
| `-r` | 可读 | `test -r path` |
| `-z` | 字符串为空 | `test -z "$var"` |
| `-n` | 字符串非空 | `test -n "$var"` |
| `=` | 字符串相等 | `test "$a" = "$b"` |
| `!=` | 字符串不等 | `test "$a" != "$b"` |
| `-eq` | 数字相等 | `test $n -eq 5` |
| `-gt` | 大于 | `test $n -gt 5` |
| `-lt` | 小于 | `test $n -lt 5` |

### Switch 语句

Fish 的 `switch` 语句更简洁（不需要 `;;` 或分号）：

```fish
switch $os
    case linux
        echo "Linux detected"
    case darwin
        echo "macOS detected"
    case '*bsd'
        echo "BSD variant"
    case '*'
        echo "Unknown OS: $os"
end
```

### 其他重要语法

```fish
# begin … end — 代码块（控制作用域）
begin
    set -l temp "scoped"
    echo $temp
end
echo $temp   # => 空，因为 -l 限定在 begin/end 块内

# and / or 短路求值
test -f file; and echo "exists"; or echo "missing"

# 管道中的 $status（替代 $?）
false
echo $status    # => 1
true
echo $status    # => 0

# 管道中检查每一段的退出码
false | true
echo $pipestatus # => 1 0

# string 子命令 — Fish 内置字符串处理
string length "hello"          # => 5
string upper "hello"           # => HELLO
string split '/' "/a/b/c"     # => '' 'a' 'b' 'c'
string join ',' a b c          # => a,b,c
string replace -a 'old' 'new' "old dog old cat"  # => new dog new cat
string match -r 'v(\d+)' "v2.1"  # => v2.1 2
```

### 多行编辑与脚本持久化

Fish 默认交互中按 `Alt+Enter` 可在输入多行命令，而 `fish_indent` 工具是 Fish 的自动格式化器，确保代码风格一致。

---

## 2. 代码示例

> **运行环境要求**：Fish 3.0+（`apt install fish` / `brew install fish` / `dnf install fish`）。
> 所有 `.fish` 脚本用 `fish script.fish` 运行，或加 shebang `#!/usr/bin/env fish` 并 `chmod +x` 后直接运行。

### 示例 1：基本的 Fish 脚本

```fish
#!/usr/bin/env fish
# hello.fish — 第一个 Fish 脚本

set name "World"
echo "Hello, $name!"
echo "Today is"(date +%A)
echo "Uptime: "(uptime | string match -r 'up .*,' | string trim -c ',')
```

**运行方式：**
```bash
fish hello.fish
# 或
chmod +x hello.fish && ./hello.fish
```

### 示例 2：列表操作实战

```fish
#!/usr/bin/env fish
# list-demo.fish — Fish 列表操作

# 创建列表
set colors red green blue yellow

# 列表信息
echo "Count: "(count $colors)
echo "First: $colors[1]"
echo "Last:  $colors[-1]"
echo "2..3:  $colors[2..3]"

# 追加
set -a colors purple
echo "After append: $colors"

# 删除元素
set -e colors[2]   # 删除第 2 个元素
echo "After erase[2]: $colors"

# 遍历
echo ""
echo "=== Iteration ==="
for color in $colors
    echo "  - $color"
end

# 列表包含检查（利用 contains 内置命令）
if contains "red" $colors
    echo "red is in the list"
end
```

**预期输出：**

```text
Count: 4
First: red
Last:  yellow
2..3:  green blue
After append: red green blue yellow purple
After erase[2]: red blue yellow purple

=== Iteration ===
  - red
  - blue
  - yellow
  - purple
red is in the list
```

### 示例 3：函数与参数解析

```fish
#!/usr/bin/env fish
# backup.fish — 文件备份工具

function backup_files --description "Backup files to a directory"
    argparse 'd/dest=' 'n/dry-run' 'h/help' -- $argv
    or return 1

    # 帮助信息
    if set -q _flag_help
        echo "Usage: backup.fish -d DEST [--dry-run] FILE..."
        echo ""
        echo "Options:"
        echo "  -d, --dest DIR     Backup destination directory"
        echo "  -n, --dry-run      Show what would be done"
        echo "  -h, --help         Show this help"
        return 0
    end

    # 验证目标
    if not set -q _flag_dest
        echo "ERROR: -d/--dest is required" >&2
        return 1
    end

    set dest $_flag_dest
    if not test -d "$dest"
        mkdir -p "$dest"
        echo "Created directory: $dest"
    end

    # 备份每个文件
    for file in $argv
        if test -f "$file"
            set dest_file "$dest/"(basename "$file").(date +%Y%m%d_%H%M%S)
            if set -q _flag_dry_run
                echo "[DRY RUN] Would copy: $file -> $dest_file"
            else
                cp "$file" "$dest_file"
                echo "Backed up: $file -> $dest_file"
            end
        else
            echo "WARNING: Skipping non-file: $file" >&2
        end
    end
end

# 调用函数
backup_files $argv
```

**运行方式：**
```bash
fish backup.fish -d /tmp/backups file1.txt file2.txt
fish backup.fish -d /tmp/backups --dry-run *.txt
fish backup.fish --help
```

### 示例 4：条件判断与 Switch

```fish
#!/usr/bin/env fish
# system-info.fish — 系统信息收集

set os (uname -s | string lower)

switch $os
    case linux
        set pkg_mgr "unknown"

        if test -f /etc/debian_version
            set pkg_mgr "apt"
        else if test -f /etc/redhat-release
            set pkg_mgr "dnf"
        else if test -f /etc/arch-release
            set pkg_mgr "pacman"
        end

        echo "Linux detected, package manager: $pkg_mgr"

    case darwin
        echo "macOS detected"
        if command -q brew
            echo "Homebrew is available"
        end
        echo "CPU: "(sysctl -n machdep.cpu.brand_string | string trim)

    case '*'
        echo "Unknown OS: $os"
end

# 检查 root 权限
if test (id -u) -eq 0
    echo "WARNING: Running as root"
else
    echo "Running as user: "(whoami)
end
```

### 示例 5：文件批量处理

```fish
#!/usr/bin/env fish
# rename-lowercase.fish — 批量转换文件名为小写

set target_dir $argv[1]
if test -z "$target_dir"
    echo "Usage: "(status filename)" <directory>" >&2
    exit 1
end

if not test -d "$target_dir"
    echo "ERROR: '$target_dir' is not a directory" >&2
    exit 1
end

set count 0
for file in $target_dir/*
    set basename (basename "$file")
    set lowercase_name (string lower "$basename")

    if test "$basename" != "$lowercase_name"
        set new_path "$target_dir/$lowercase_name"
        mv -n "$file" "$new_path"
        echo "Renamed: $basename -> $lowercase_name"
        set count (math $count + 1)
    end
end

echo "Done. Renamed $count files."
```

**运行方式：**
```bash
fish rename-lowercase.fish /path/to/directory
```

### 示例 6：多行编辑与数据管道

```fish
#!/usr/bin/env fish
# log-analyzer.fish — 分析日志文件

function analyze_log --argument-names logfile
    if not test -f "$logfile"
        echo "ERROR: '$logfile' not found" >&2
        return 1
    end

    echo "=== Log Analysis for $logfile ==="
    echo ""

    # 总行数
    set total_lines (wc -l < "$logfile" | string trim)
    echo "Total lines: $total_lines"

    # 错误数量
    set error_count (grep -ci 'error' "$logfile" 2>/dev/null; or echo 0)
    echo "Errors found: $error_count"

    # Top 5 IP 地址
    echo ""
    echo "Top 5 IP addresses:"
    grep -oE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}' "$logfile" \
        | sort | uniq -c | sort -rn | head -5 \
        | while read count ip
            echo "  $count  $ip"
        end

    # 每小时请求分布
    echo ""
    echo "Requests per hour:"
    grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}' "$logfile" \
        | cut -d: -f1 | sort | uniq -c | sort -k2 -n
end

analyze_log $argv
```

---

## 3. 练习

### 练习 1：变量与列表基础

编写一个 Fish 脚本 `todo.fish`，实现以下功能：
1. 使用列表存储待办事项
2. 支持 `add`、`list`、`done` 三个子命令
3. `add "message"` — 添加待办事项
4. `list` — 显示所有待办事项（带编号）
5. `done N` — 标记第 N 项为完成（删除该项）

### 练习 2：函数封装与参数解析

编写一个 Fish 脚本 `cpu-monitor.fish`，使用 `argparse` 接受选项：
- `-w, --warn PERCENT` — CPU 使用率超过此百分比时告警（默认 80）
- `-i, --interval SECONDS` — 检查间隔（默认 5）
- `-c, --count N` — 检查次数（默认 1）

每轮检查打印当前 CPU 使用率，超过阈值时打印 `WARNING:` 消息。

> 提示：使用 `top -bn1`（Linux）或 `ps -A -o %cpu`（macOS）获取 CPU 信息。

### 练习 3：文件处理流水线（可选）

编写一个 Fish 脚本 `project-stats.fish`，接受一个项目目录路径，统计：
1. 各级别子目录中的文件数量
2. 按文件扩展名统计文件数和总行数
3. 最大的 5 个文件（按大小排序）

输出格式清晰、带标题。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```fish
> #!/usr/bin/env fish
> # todo.fish — 简单的待办事项管理器
>
> set todos
>
> set subcommand $argv[1]
>
> switch "$subcommand"
>     case add
>         set -a todos "$argv[2..-1]"
>         echo "Added: $argv[2..-1]"
>
>     case list
>         if test (count $todos) -eq 0
>             echo "No todos yet."
>         else
>             for i in (seq (count $todos))
>                 echo "[$i] $todos[$i]"
>             end
>         end
>
>     case done
>         set idx $argv[2]
>         if test -z "$idx" -o "$idx" -lt 1 -o "$idx" -gt (count $todos)
>             echo "ERROR: Invalid index: $idx" >&2
>         else
>             echo "Completed: $todos[$idx]"
>             set -e todos[$idx]
>         end
>
>     case '*'
>         echo "Usage: todo.fish {add|list|done} [args]" >&2
>         exit 1
> end
> ```

> [!tip]- 练习 2 参考答案
> ```fish
> #!/usr/bin/env fish
> # cpu-monitor.fish — CPU 使用率监控
>
> function cpu_monitor
>     argparse 'w/warn=' 'i/interval=' 'c/count=' -- $argv
>     or return 1
>
>     set warn_pct (math "min(100, $_flag_warn)")
>     if test -z "$warn_pct"; set warn_pct 80; end
>     set interval (math "max(1, $_flag_interval)")
>     if test -z "$interval"; set interval 5; end
>     set checks "$_flag_count"
>     if test -z "$checks"; set checks 1; end
>
>     echo "Monitoring CPU (warn at {$warn_pct}%, every {$interval}s, {$checks} checks)"
>
>     for i in (seq $checks)
>         # 获取 CPU 使用率（100 - idle%）
>         set idle (top -bn1 2>/dev/null | grep 'Cpu' | grep -oE '[0-9.]+ id' | grep -oE '[0-9.]+')
>         if test -z "$idle"
>             set idle (top -l1 -n0 2>/dev/null | grep 'CPU usage' | grep -oE '[0-9.]+% idle' | grep -oE '[0-9.]+')
>         end
>         if test -z "$idle"; set idle 100; end
>
>         set usage (math "100 - $idle")
>         set usage_str (printf "%.1f" "$usage")
>
>         if test "$usage" -gt "$warn_pct"
>             set_color red
>             printf "[%s] WARNING: CPU %.1f%% > %d%%\n" (date +%H:%M:%S) "$usage" "$warn_pct"
>             set_color normal
>         else
>             printf "[%s] CPU: %.1f%%\n" (date +%H:%M:%S) "$usage"
>         end
>
>         if test $i -lt $checks
>             sleep $interval
>         end
>     end
> end
>
> cpu_monitor $argv
> ```

> [!tip]- 练习 3 参考答案
> ```fish
> #!/usr/bin/env fish
> # project-stats.fish — 项目统计工具
>
> set project_dir $argv[1]
> if test -z "$project_dir"
>     echo "Usage: project-stats.fish <project_directory>" >&2
>     exit 1
> end
>
> if not test -d "$project_dir"
>     echo "ERROR: '$project_dir' not found" >&2
>     exit 1
> end
>
> pushd "$project_dir"
>
> echo "=== Project Stats for "(pwd)" ==="
> echo ""
>
> # 1. 各目录文件数
> echo "--- Files per directory ---"
> for dir in */
>     set count (find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l | string trim)
>     printf "  %-40s %s files\n" "$dir" "$count"
> end
>
> # 2. 按扩展名统计
> echo ""
> echo "--- Files by extension ---"
> printf "  %-12s %8s %10s\n" "Extension" "Files" "Total Lines"
> printf "  %-12s %8s %10s\n" "---------" "-----" "-----------"
>
> for ext in (find . -type f | string match -r '\.[a-zA-Z0-9]+$' | sort -u)
>     set count (find . -type f -name "*$ext" | wc -l | string trim)
>     set lines (find . -type f -name "*$ext" -exec cat {} + 2>/dev/null | wc -l | string trim)
>     printf "  %-12s %8s %10s\n" "$ext" "$count" "$lines"
> end
>
> # 3. 最大的 5 个文件
> echo ""
> echo "--- Largest 5 files ---"
> find . -type f -exec du -h {} + 2>/dev/null | sort -hr | head -5 \
>     | while read -l size path
>         printf "  %8s  %s\n" "$size" "$path"
>     end
>
> popd
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Fish Shell 官方文档](https://fishshell.com/docs/current/)
- [Fish 教程 (fishshell.com)](https://fishshell.com/docs/current/tutorial.html)
- [Fish 语言设计文档](https://fishshell.com/docs/current/design.html)
- [Fish 与 Bash 语法对照表](https://fishshell.com/docs/current/fish_for_bash_users.html)
- [Awesome Fish — 精选插件和配置](https://github.com/jorgebucaran/awsm.fish)
- [Fish 内置 string 命令完整参考](https://fishshell.com/docs/current/cmds/string.html)
- [Fisher — Fish 插件管理器](https://github.com/jorgebucaran/fisher)

---

## 常见陷阱

- **`source` 不能加载 Bash 脚本**：Fish 的 `source` 只能加载 `.fish` 文件。尝试 `source ~/.bashrc` 会报语法错误。要在 Fish 中使用环境变量，重写为 `set -x VAR value` 或在 `~/.config/fish/config.fish` 中配置。
- **命令替换把换行转成列表**：`set files (ls)` 会将 `ls` 的每一行输出作为一个列表元素。这与 Bash 的 `$(ls)` 不同——在 Bash 中换行是空格。如果文件名为 `"my file.txt"`，Fish 会正确处理（空格不拆分），但 `ls` 本身不是可靠的文件列举方式，更推荐使用通配符 `*`。
- **变量永不分词**：`set CMD "echo hello"` 然后 `$CMD` **不会**把 `"echo hello"` 解析为命令——整个字符串被当作一个命令名执行。在 Fish 中动态构造命令需要用 `eval`：`eval $CMD`。这是安全设计，避免 Bash 中常见的命令注入问题。
- **`$?` 不存在**：Fish 用 `$status` 代替 `$?`，且 `$status` 是上一个命令的退出码——每个命令都会更新它。如果你想保留退出码，必须立即保存：`set -l last_status $status`。管道中每段的退出码用 `$pipestatus` 获取。
- **`history` 语法与 Bash 不同**：Fish 不支持 Bash 的 `!$`、`!!`、`!123` 等历史展开。Fish 的交互式历史搜索通过 `Ctrl+R` 或直接输入上一条命令的开头然后按上箭头。
- **`&&` 和 `||` 不存在**：Fish 使用 `; and` 和 `; or` 作为连接词，且它们必须紧跟在上一个命令之后（以分号或换行分隔）。`cmd1 && cmd2` 会报错，应写作 `cmd1; and cmd2`。
- **环境变量 `PATH` 是列表**：`$PATH` 在 Fish 中自动以 `:` 分隔转换为列表。如果你从 Bash 脚本复制 `export PATH="/new/path:$PATH"` 到 Fish，需要写成 `fish -c 'set -x PATH /new/path $PATH'` 或 `set -x PATH /new/path $PATH`。
- **浮点数运算**：Fish 不内置浮点数运算，用 `math` 命令：`math "3.14 * 2"`。注意 `math` 需要参数作为单个字符串传入。
