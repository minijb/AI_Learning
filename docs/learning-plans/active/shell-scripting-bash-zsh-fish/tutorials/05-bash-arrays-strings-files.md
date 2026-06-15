---
title: Bash 数组、字符串与文件操作
updated: 2026-06-15
tags: [shell, bash, arrays, strings, files]
---

# Bash 数组、字符串与文件操作

> 所属计划: Shell 脚本编程：Bash、Zsh 与 Fish
> 预计耗时: 60min
> 前置知识: [[04-bash-loops-functions|Bash 循环与函数]]

---

## 1. 概念讲解

本节涵盖了 Bash 脚本中三种高频出现的操作类型：数组、字符串处理与文件匹配。它们是写出实用脚本的基石——日志分析、批量文件处理、配置解析都离不开它们。

### 为什么需要这个？

纯变量只能存一个值。当你需要处理一组文件、一行 CSV 中的多个字段、或者一个配置项的多个值时，数组是唯一选择。字符串操作让你在不借助外部命令（如 `sed`、`awk`）的情况下完成子串提取、模式替换等任务，大幅提升脚本性能。文件 glob 让你用通配符精确匹配文件集合，比解析 `ls` 输出安全和高效得多。

### 核心思想

- **数组**：用数字索引或字符串键来组织一组值，支持追加、删除、遍历、切片。
- **字符串参数展开**：Bash 内置的 `${var操作}` 语法可替代许多外部命令，在循环中尤其高效。
- **文件 glob**：shell 在命令执行前将通配符展开为匹配的文件列表，这是"先展开再执行"的机制。
- **测试操作符**：`[[ ]]` 提供了丰富的文件测试、字符串比较和模式匹配能力。

---

## 2. 代码示例

### 2.1 索引数组

**运行环境要求**: Bash 4.0+

```bash
#!/usr/bin/env bash
# 索引数组基础操作

# 声明与赋值
declare -a fruits=("apple" "banana" "cherry")
# 或者省略 declare -a（Bash 默认就是索引数组）
colors=("red" "green" "blue")

# 访问元素（索引从 0 开始）
echo "First fruit: ${fruits[0]}"
echo "Second color: ${colors[1]}"

# 获取所有元素
echo "All fruits: ${fruits[@]}"

# 获取数组长度
echo "Number of fruits: ${#fruits[@]}"

# 追加元素
fruits+=("date")
echo "After append: ${fruits[@]}"

# 按索引赋值
fruits[0]="apricot"
echo "After update: ${fruits[@]}"

# 遍历数组
for fruit in "${fruits[@]}"; do
    echo "  - $fruit"
done

# 遍历索引
for i in "${!fruits[@]}"; do
    echo "  fruits[$i] = ${fruits[$i]}"
done

# 切片：${数组名[@]:起始:长度}
echo "Slice [1..2]: ${fruits[@]:1:2}"

# 删除元素（设值为空不会减少长度）
unset "fruits[1]"
echo "After unset index 1: ${fruits[@]}"
echo "Indices now: ${!fruits[@]}"
```

**运行方式:**
```bash
chmod u+x arrays_demo.sh && ./arrays_demo.sh
```

**预期输出:**
```text
First fruit: apple
Second color: green
All fruits: apple banana cherry
Number of fruits: 3
After append: apple banana cherry date
After update: apricot banana cherry date
  - apricot
  - banana
  - cherry
  - date
  fruits[0] = apricot
  fruits[1] = banana
  fruits[2] = cherry
  fruits[3] = date
Slice [1..2]: banana cherry
After unset index 1: apricot cherry date
Indices now: 0 2 3
```

### 2.2 关联数组

**运行环境要求**: Bash 4.0+

```bash
#!/usr/bin/env bash
# 关联数组（类似其他语言的 dict/map）

# 必须显式声明
declare -A user

user[name]="Alice"
user[age]=30
user[city]="Beijing"

echo "Name: ${user[name]}"
echo "Age: ${user[age]}"

# 获取所有键
echo "Keys: ${!user[@]}"

# 获取所有值
echo "Values: ${user[@]}"

# 检查键是否存在
if [[ -v user[name] ]]; then
    echo "Key 'name' exists"
fi

# 遍历关联数组
for key in "${!user[@]}"; do
    echo "  $key = ${user[$key]}"
done
```

**运行方式:**
```bash
chmod u+x assoc_demo.sh && ./assoc_demo.sh
```

**预期输出:**
```text
Name: Alice
Age: 30
Keys: name age city
Values: Alice 30 Beijing
Key 'name' exists
  name = Alice
  age = 30
  city = Beijing
```

### 2.3 字符串参数展开

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# 字符串参数展开——无需 fork 外部进程的高效操作

str="Hello, World! Welcome to Bash."

# --- 长度 ---
echo "Length: ${#str}"

# --- 子串提取 ---
echo "First 5 chars: ${str:0:5}"
echo "From position 7: ${str:7}"
echo "Last 5 chars: ${str: -5}"      # 注意冒号后的空格

# --- 大小写转换（Bash 4.0+）---
echo "Uppercase: ${str^^}"
echo "Lowercase: ${str,,}"
echo "First char upper: ${str^}"     # 仅首字符大写
echo "First char lower: ${str,}"

# --- 前缀/后缀删除 ---
path="/usr/local/bin/script.sh"
echo "Remove shortest prefix /*/: ${path#/*/}"
echo "Remove longest prefix /*/: ${path##/*/}"
echo "Remove shortest suffix /*: ${path%/*}"
echo "Remove longest suffix /*: ${path%%/*}"

# --- 替换 ---
text="foo bar baz foo"
echo "Replace first foo: ${text/foo/FOO}"
echo "Replace all foo: ${text//foo/FOO}"
echo "Replace leading #: ${text/#foo/START}"
echo "Replace trailing %: ${text/%foo/END}"

# --- 默认值 ---
unset undefined
echo "Default: ${undefined:-NOT_SET}"
echo "Assign default: ${undefined:=ASSIGNED}"
echo "Now undefined = $undefined"

# --- 间接引用（Bash 2.0+）---
varname="PATH"
echo "Indirect: ${!varname:0:50}..."
```

**运行方式:**
```bash
chmod u+x string_demo.sh && ./string_demo.sh
```

**预期输出:**
```text
Length: 32
First 5 chars: Hello
From position 7: World! Welcome to Bash.
Last 5 chars: Bash.
Uppercase: HELLO, WORLD! WELCOME TO BASH.
Lowercase: hello, world! welcome to bash.
First char upper: Hello, World! Welcome to Bash.
First char lower: hello, World! Welcome to Bash.
Remove shortest prefix /*/: local/bin/script.sh
Remove longest prefix /*/: script.sh
Remove shortest suffix /*: /usr/local/bin
Remove longest suffix /*:
Replace first foo: FOO bar baz foo
Replace all foo: FOO bar baz FOO
Replace leading #: START bar baz foo
Replace trailing %: foo bar baz END
Default: NOT_SET
Assign default: ASSIGNED
Now undefined = ASSIGNED
Indirect: /c/Users/zhouhao02/...
```

### 2.4 文件 Glob 与避免解析 ls

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# 文件 glob 的正确姿势

# --- 基本通配符 ---
# * 匹配任意字符（不含隐藏文件）
echo "=== *.sh files ==="
for f in *.sh; do
    [[ -f "$f" ]] && echo "  $f"
done

# ? 匹配单个字符
echo "=== files matching ???.txt ==="
for f in ???.txt; do
    [[ -f "$f" ]] && echo "  $f"
done

# [] 字符类
echo "=== files starting with a-c or A-C ==="
for f in [a-cA-C]*; do
    [[ -e "$f" ]] && echo "  $f"
done

# --- 扩展 Glob（需要 shopt -s extglob）---
shopt -s extglob

echo "=== all .sh and .md files ==="
for f in *.@(sh|md); do
    [[ -f "$f" ]] && echo "  $f"
done

# --- Globstar 递归匹配（Bash 4.0+）---
shopt -s globstar
echo "=== all .md files recursively (max 10) ==="
count=0
for f in **/*.md; do
    [[ -f "$f" ]] || continue
    echo "  $f"
    ((count++))
    ((count >= 10)) && break
done

# --- 处理带空格/特殊字符的文件名 ---
# 正确：使用 glob + 引号
echo "=== files with spaces (safe) ==="
for f in *; do
    [[ -f "$f" ]] && echo "  [$f]"
done

# --- ❌ 错误示例：解析 ls ---
# 这样做会在文件名包含空格或特殊字符时出错：
#
#   for f in $(ls); do
#       echo "$f"
#   done
#
# 正确做法是直接用 glob 或用 find -print0 + read -d ''

echo "=== safe way with find -print0 ==="
while IFS= read -r -d '' file; do
    echo "  $file"
done < <(find . -maxdepth 1 -name "*.sh" -print0)
```

**运行方式:**
```bash
chmod u+x glob_demo.sh && ./glob_demo.sh
```

### 2.5 文件测试操作符

**运行环境要求**: Bash 3.0+

```bash
#!/usr/bin/env bash
# 文件测试操作符一览

path="05-bash-arrays-strings-files.md"

# 存在性
[[ -e "$path" ]] && echo "exists"
[[ -f "$path" ]] && echo "is regular file"
[[ -d "$path" ]] && echo "is directory"      # 不会打印

# 可读/可写/可执行
[[ -r "$path" ]] && echo "readable"
[[ -w "$path" ]] && echo "writable"
[[ -x "$path" ]] && echo "executable"

# 非空
[[ -s "$path" ]] && echo "non-empty"

# 比较（用于判断新旧）
touch /tmp/test_ref
sleep 0.1 && touch /tmp/test_newer
[[ /tmp/test_newer -nt /tmp/test_ref ]] && echo "newer"
[[ /tmp/test_ref -ot /tmp/test_newer ]] && echo "older"

# 符号链接
ln -sf /tmp/test_ref /tmp/test_link 2>/dev/null
[[ -L /tmp/test_link ]] && echo "is symlink"

# 字符串测试
[[ -z "" ]] && echo "empty string"
[[ -n "hello" ]] && echo "non-empty string"
[[ "abc" == "abc" ]] && echo "strings equal"
[[ "abc" < "xyz" ]] && echo "lexicographically before"

# 模式匹配（[[ ]] 特有）
[[ "hello.txt" == *.txt ]] && echo "matches *.txt pattern"

# 正则匹配（Bash 3.0+）
[[ "2026-06-15" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && echo "matches date regex"

# 捕获正则分组（BASH_REMATCH）
if [[ "file_123.txt" =~ ^([a-z]+)_([0-9]+)\.txt$ ]]; then
    echo "  name: ${BASH_REMATCH[1]}"
    echo "  number: ${BASH_REMATCH[2]}"
fi
```

**运行方式:**
```bash
chmod u+x file_test_demo.sh && ./file_test_demo.sh
```

**预期输出:**
```text
exists
is regular file
readable
writable
non-empty
newer
older
is symlink
empty string
non-empty string
strings equal
lexicographically before
matches *.txt pattern
matches date regex
  name: file
  number: 123
```

---

## 3. 练习

### 练习 1: 数组统计
写一个脚本，从标准输入读取多行数字（每行一个），存入数组，然后输出：总数、最大值、最小值、平均值。

### 练习 2: 文件批量重命名（前缀）
写一个脚本，给当前目录下所有 `.txt` 文件添加前缀 `backup_`。要求：
- 使用 glob 匹配文件，不解析 `ls`
- 正确处理文件名包含空格的情况
- 使用参数展开截取文件名
- 重命名前检查目标文件是否已存在

### 练习 3: 日志分析器（可选）
写一个脚本 `analyze_log.sh`，分析一个类似 `/var/log/syslog` 格式的日志文件：
- 统计各级别（INFO、WARN、ERROR）出现的次数（用关联数组）
- 输出 Top 5 最频繁的日志来源（即日志行中 `:` 之后的第一个 token）
- 使用 `[[ =~ ]]` 正则匹配提取级别

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> ```bash
> #!/usr/bin/env bash
> # array_stats.sh — 数组统计
>
> readarray -t numbers
>
> if [[ ${#numbers[@]} -eq 0 ]]; then
>     echo "No input provided."
>     exit 1
> fi
>
> total=0
> min=${numbers[0]}
> max=${numbers[0]}
>
> for n in "${numbers[@]}"; do
>     ((total += n))
>     ((n < min)) && min=$n
>     ((n > max)) && max=$n
> done
>
> count=${#numbers[@]}
> avg=$(echo "scale=2; $total / $count" | bc)
>
> echo "Count:  $count"
> echo "Total:  $total"
> echo "Min:    $min"
> echo "Max:    $max"
> echo "Avg:    $avg"
> ```
>
> **运行**: `echo -e "3\n7\n2\n9\n5" | ./array_stats.sh`

> [!tip]- 练习 2 参考答案
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> ```bash
> #!/usr/bin/env bash
> # add_prefix.sh — 为 .txt 文件添加 backup_ 前缀
>
> prefix="backup_"
> count=0
> skipped=0
>
> shopt -s nullglob  # 无匹配时 glob 展开为空，而非原样保留
>
> for file in *.txt; do
>     [[ -f "$file" ]] || continue
>
>     # 跳过已有前缀的文件
>     if [[ "$file" == ${prefix}* ]]; then
>         echo "SKIP: $file (already has prefix)"
>         ((skipped++))
>         continue
>     fi
>
>     newname="${prefix}${file}"
>
>     if [[ -e "$newname" ]]; then
>         echo "SKIP: $newname already exists"
>         ((skipped++))
>         continue
>     fi
>
>     mv -- "$file" "$newname"
>     echo "RENAMED: $file -> $newname"
>     ((count++))
> done
>
> echo "Done: $count renamed, $skipped skipped."
> ```
>
> **运行**: 在含有 `.txt` 文件的目录中执行 `./add_prefix.sh`

> [!tip]- 练习 3 参考答案（可选）
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> ```bash
> #!/usr/bin/env bash
> # analyze_log.sh — 日志分析
>
> if [[ $# -lt 1 ]]; then
>     echo "Usage: $0 <logfile>"
>     exit 1
> fi
>
> logfile="$1"
> [[ -f "$logfile" ]] || { echo "File not found: $logfile"; exit 1; }
>
> declare -A levels
> declare -A sources
>
> while IFS= read -r line; do
>     # 用正则捕获级别
>     if [[ "$line" =~ (INFO|WARN|ERROR|DEBUG|TRACE) ]]; then
>         ((levels[${BASH_REMATCH[1]}]++))
>     fi
>
>     # 提取来源：冒号之后的第一个 token
>     # 假设格式: "Jun 15 10:00:00 hostname source[pid]: message"
>     if [[ "$line" =~ :[[:space:]]*([[:alnum:]_-]+)[\[\:] ]]; then
>         ((sources[${BASH_REMATCH[1]}]++))
>     fi
> done < "$logfile"
>
> echo "=== Log Level Counts ==="
> for level in INFO WARN ERROR DEBUG TRACE; do
>     echo "  $level: ${levels[$level]:-0}"
> done
>
> echo ""
> echo "=== Top 5 Sources ==="
> for src in "${!sources[@]}"; do
>     echo "${sources[$src]} $src"
> done | sort -rn | head -5 | while read -r count name; do
>     printf "  %-20s %d\n" "$name" "$count"
> done
> ```
>
> **运行**: `./analyze_log.sh /var/log/syslog`

---

## 4. 扩展阅读

- [Bash Reference Manual: Arrays](https://www.gnu.org/software/bash/manual/html_node/Arrays.html)
- [Bash Reference Manual: Shell Parameter Expansion](https://www.gnu.org/software/bash/manual/html_node/Shell-Parameter-Expansion.html)
- [Bash Reference Manual: Pattern Matching](https://www.gnu.org/software/bash/manual/html_node/Pattern-Matching.html)
- [Bash Hackers Wiki: Parameter Expansion](https://wiki.bash-hackers.org/syntax/pe)
- [Greg's Wiki: BashGuide/TestsAndConditionals](https://mywiki.wooledge.org/BashGuide/TestsAndConditionals)
- [Why you shouldn't parse the output of ls](https://mywiki.wooledge.org/ParsingLs)

---

## 常见陷阱

- **未加引号的数组展开**：`${arr[@]}` 不加引号会导致元素按单词拆分。始终用 `"${arr[@]}"`。
- **关联数组未声明**：忘记 `declare -A` 会导致键被当作索引数字处理。先声明再使用。
- **索引从 0 开始**：与其他语言一致，但不要与 Zsh（从 1 开始）混淆。
- **`unset` 后索引不连续**：删除元素不会重新索引。遍历用 `"${arr[@]}"` 而不是依赖索引连续性。
- **`nullglob` 的重要性**：没有匹配文件时，glob 模式本身会被原样保留。用 `shopt -s nullglob` 防止这个行为。
- **解析 `ls` 输出**：`ls` 的输出是为人类阅读设计的，不应在脚本中解析。用 glob 或 `find -print0`。
- **字符串大小写转换需要 Bash 4.0+**：`${var^^}` 和 `${var,,}` 在旧版本不可用。替代方案：`tr` 命令。
- **文件测试在符号链接上的行为**：`-f` 跟随符号链接测试目标。用 `-h` 或 `-L` 测试链接本身。
- **`readarray`（又名 `mapfile`）需要 Bash 4.0+**：旧版本用 `while read` 循环逐行读入数组。
