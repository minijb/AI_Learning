---
title: Bash 循环与函数
updated: 2026-06-15
---

# Bash 循环与函数

> 所属计划: [[plan|Shell 脚本编程：Bash、Zsh 与 Fish]]
> 预计耗时: 60 分钟
> 前置知识: [[03-bash-conditions|Bash 条件判断与流程控制]]

---

## 1. 概念讲解

### 循环：重复执行

Bash 提供三种循环结构：

| 循环 | 适用场景 | 语法 |
|------|----------|------|
| `for ... in` | 遍历列表中的每个元素 | `for item in list; do ... done` |
| `for (( ))` | 类似 C 的计数循环 | `for ((i=0; i<10; i++)); do ... done` |
| `while` | 条件为真时重复 | `while [[ condition ]]; do ... done` |
| `until` | 条件为假时重复（`while` 的反面） | `until [[ condition ]]; do ... done` |

### 函数：封装可重用代码

Bash 函数有两种定义语法：

```bash
# 风格 1（推荐：更清晰）
function greet {
    echo "Hello, $1"
}

# 风格 2（POSIX 兼容）
greet() {
    echo "Hello, $1"
}
```

函数内使用**位置参数**：
- `$1`, `$2`, ... — 第 n 个参数
- `$@` — 所有参数（每个作为一个独立单词）
- `$*` — 所有参数（合并成一个字符串）
- `$#` — 参数个数

### 函数变量作用域

**默认情况下，Bash 中所有变量都是全局的。** 在函数内修改变量会影响外部。要用 `local` 关键字限制作用域：

```bash
function demo {
    local inside="函数内部"   # 只在函数内有效
    outside="全局可见"         # 全局可见！
}
```

### 函数返回值

Bash 函数不能返回字符串，只能返回**退出状态码**（`0`-`255`）。需要返回数据时，用 `echo` 输出并用命令替换捕获：

```bash
function get_greeting {
    echo "Hello, $1"
}

msg=$(get_greeting "Alice")   # msg = "Hello, Alice"
```

### break 与 continue

- `break`：跳出整个循环
- `continue`：跳过当前迭代，进入下一次
- `break N` / `continue N`：跳出/跳过 N 层循环

---

## 2. 代码示例

### 示例 1：for 循环遍历

```bash
#!/usr/bin/env bash

echo "=== for ... in 列表 ==="
for color in red green blue yellow; do
    echo "颜色: ${color}"
done

echo ""
echo "=== 遍历通配符结果 ==="
for file in *.sh; do
    echo "脚本文件: ${file}"
done

echo ""
echo "=== C 风格计数循环 ==="
for ((i = 1; i <= 5; i++)); do
    echo "第 ${i} 次循环"
done
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash for-loops.sh
```

**预期输出：**

```text
=== for ... in 列表 ===
颜色: red
颜色: green
颜色: blue
颜色: yellow

=== 遍历通配符结果 ===
脚本文件: hello.sh
脚本文件: greet.sh

=== C 风格计数循环 ===
第 1 次循环
第 2 次循环
第 3 次循环
第 4 次循环
第 5 次循环
```

### 示例 2：while 与 until

```bash
#!/usr/bin/env bash

echo "=== while 循环：倒计时 ==="
count=5
while [[ $count -gt 0 ]]; do
    echo "倒计时: ${count}"
    count=$((count - 1))
    sleep 0.5
done
echo "发射！"

echo ""
echo "=== until 循环：等待文件出现 ==="
# 创建一个临时文件，3 秒后删除来模拟
tmpfile="/tmp/test_wait_$$"
echo "创建文件后 ${tmpfile} 循环将结束..."
(sleep 2 && touch "$tmpfile") &

until [[ -f "$tmpfile" ]]; do
    echo "等待文件..."
    sleep 0.5
done
echo "文件出现了！"
rm -f "$tmpfile"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash while-loops.sh
```

**预期输出：**

```text
=== while 循环：倒计时 ===
倒计时: 5
倒计时: 4
倒计时: 3
倒计时: 2
倒计时: 1
发射！

=== until 循环：等待文件出现 ===
创建文件后 /tmp/test_wait_12345 循环将结束...
等待文件...
等待文件...
等待文件...
等待文件...
文件出现了！
```

### 示例 3：函数基础与 local 变量

```bash
#!/usr/bin/env bash

# 函数定义
function say_hello {
    local name="$1"       # local：函数内部变量
    local count="${2:-1}" # 默认值为 1
    for ((i = 0; i < count; i++)); do
        echo "Hello, ${name}!"
    done
}

function add {
    local result=$(( $1 + $2 ))
    echo "$result"        # 通过 stdout 返回数据
}

# 调用函数
say_hello "Alice"
echo "---"
say_hello "Bob" 3
echo "---"

sum=$(add 10 20)
echo "10 + 20 = ${sum}"

# local 的作用域演示
function scope_demo {
    local local_var="我是 local"
    global_var="我是 global"
    echo "函数内: local_var=${local_var}, global_var=${global_var}"
}

scope_demo
echo "函数外: local_var=${local_var:-未定义}, global_var=${global_var}"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash functions.sh
```

**预期输出：**

```text
Hello, Alice!
---
Hello, Bob!
Hello, Bob!
Hello, Bob!
---
10 + 20 = 30
函数内: local_var=我是 local, global_var=我是 global
函数外: local_var=未定义, global_var=我是 global
```

### 示例 4：综合应用 — 批量文件处理器

```bash
#!/usr/bin/env bash

# 函数：显示用法
function show_usage {
    echo "用法: $0 <目录> <扩展名>"
    echo "示例: $0 ./downloads txt"
}

# 函数：统计文件信息
function count_files {
    local dir="$1"
    local ext="$2"

    if [[ ! -d "$dir" ]]; then
        echo "错误: '${dir}' 不是有效目录" >&2
        return 1
    fi

    local count=0
    local total_size=0

    for file in "$dir"/*."$ext"; do
        # 跳过通配符未匹配到文件的情况
        [[ -f "$file" ]] || continue

        count=$((count + 1))
        local size
        size=$(wc -c < "$file")
        total_size=$((total_size + size))
        printf "  %3d. %-30s %6d 字节\n" "$count" "$(basename "$file")" "$size"
    done

    echo "=============================="
    echo "共 ${count} 个 .${ext} 文件"
    echo "总大小: ${total_size} 字节"
}

# ===== 主逻辑 =====
if [[ $# -lt 2 ]]; then
    show_usage
    exit 1
fi

count_files "$1" "$2"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
chmod u+x batch-process.sh
mkdir -p testdir
echo "hello" > testdir/a.txt
echo "world" > testdir/b.txt
./batch-process.sh testdir txt
```

**预期输出：**

```text
    1. a.txt                              6 字节
    2. b.txt                              6 字节
==============================
共 2 个 .txt 文件
总大小: 12 字节
```

### 示例 5：break 与 continue

```bash
#!/usr/bin/env bash

echo "=== continue：跳过偶数 ==="
for i in {1..10}; do
    if (( i % 2 == 0 )); then
        continue  # 跳过本次循环
    fi
    echo "奇数: ${i}"
done

echo ""
echo "=== break：找到后退出 ==="
for file in /etc/*; do
    if [[ "$(basename "$file")" == "hosts" ]]; then
        echo "找到了: ${file}"
        break  # 退出循环
    fi
    echo "跳过: $(basename "$file")"
done

echo ""
echo "=== break N：跳出嵌套循环 ==="
for i in {1..3}; do
    for j in {1..3}; do
        if [[ $i -eq 2 && $j -eq 2 ]]; then
            echo "在 (${i},${j}) 处跳出所有循环"
            break 2  # 跳出 2 层
        fi
        echo "  (${i},${j})"
    done
done
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash break-continue.sh
```

**预期输出：**

```text
=== continue：跳过偶数 ===
奇数: 1
奇数: 3
奇数: 5
奇数: 7
奇数: 9

=== break：找到后退出 ===
跳过: adjtime
...（中间的跳过）...
找到了: /etc/hosts

=== break N：跳出嵌套循环 ===
  (1,1)
  (1,2)
  (1,3)
  (2,1)
在 (2,2) 处跳出所有循环
```

---

## 3. 练习

### 练习 1: 乘法表

编写脚本 `multiplication-table.sh`：
1. 使用 `for` 循环输出 `1×1` 到 `9×9` 的乘法表
2. 用 `printf` 对齐格式，每列宽度固定
3. 用函数 `print_row N` 输出第 N 行

期望输出格式：

```text
1×1= 1  1×2= 2  1×3= 3  ...  1×9= 9
2×1= 2  2×2= 4  2×3= 6  ...  2×9=18
...
9×1= 9  9×2=18  9×3=27  ...  9×9=81
```

### 练习 2: 密码验证器

编写脚本 `password-check.sh`：
1. 定义函数 `validate_password`，接受一个参数（密码字符串）
2. 检查密码是否符合以下规则（用 `[[ ]]` 和 `=~`）：
   - 长度至少 8 个字符
   - 至少包含一个大写字母
   - 至少包含一个小写字母
   - 至少包含一个数字
3. 返回 `0`（通过）或 `1`（不通过），并通过 `echo` 输出具体失败原因
4. 主程序用 `while` 循环反复提示用户输入密码，最多 3 次尝试，直到设置成功

### 练习 3: 目录备份脚本（可选）

编写脚本 `backup.sh`：
1. 函数 `backup_dir <源目录> <目标目录>`：
   - 检查源目录是否存在
   - 在目标目录创建一个以日期命名的子目录（如 `backup_2026-06-15`）
   - 用 `for` 循环遍历源目录下所有文件
   - 跳过子目录，只复制文件
   - 统计成功复制和跳过的文件数
2. 主程序：接收两个命令行参数，调用 `backup_dir`

---

## 4. 参考答案

> [!tip]- 练习 1 参考答案
> ```bash
> #!/usr/bin/env bash
>
> function print_row {
>     local n="$1"
>     for ((i = 1; i <= 9; i++)); do
>         printf "%d×%d=%-3d" "$n" "$i" "$((n * i))"
>     done
>     echo ""  # 换行
> }
>
> for ((row = 1; row <= 9; row++)); do
>     print_row "$row"
> done
> ```
>
> 用 `printf` 的 `%-3d` 左对齐占 3 位保证对齐。9×9 最大结果 81，3 位宽度刚好。

> [!tip]- 练习 2 参考答案
> ```bash
> #!/usr/bin/env bash
>
> function validate_password {
>     local pw="$1"
>     local errors=()
>
>     if [[ ${#pw} -lt 8 ]]; then
>         errors+=("长度至少 8 个字符")
>     fi
>     if [[ ! "$pw" =~ [A-Z] ]]; then
>         errors+=("需要至少 1 个大写字母")
>     fi
>     if [[ ! "$pw" =~ [a-z] ]]; then
>         errors+=("需要至少 1 个小写字母")
>     fi
>     if [[ ! "$pw" =~ [0-9] ]]; then
>         errors+=("需要至少 1 个数字")
>     fi
>
>     if [[ ${#errors[@]} -gt 0 ]]; then
>         for err in "${errors[@]}"; do
>             echo "  - ${err}"
>         done
>         return 1
>     fi
>     return 0
> }
>
> max_attempts=3
> attempt=1
>
> while [[ $attempt -le $max_attempts ]]; do
>     read -sp "设置密码 (尝试 ${attempt}/${max_attempts}): " password
>     echo ""
>
>     if validate_password "$password"; then
>         echo "✓ 密码设置成功！"
>         exit 0
>     else
>         echo "✗ 密码不符合要求："
>         attempt=$((attempt + 1))
>         if [[ $attempt -le $max_attempts ]]; then
>             echo ""
>         fi
>     fi
> done
>
> echo "已达到最大尝试次数，密码设置失败。"
> exit 1
> ```
>
> 注意 `${#pw}` 获取字符串长度，`"${errors[@]}"` 展开数组所有元素。数组知识将在第 5 节详细介绍。

> [!tip]- 练习 3 参考答案
> ```bash
> #!/usr/bin/env bash
>
> function backup_dir {
>     local src="$1"
>     local dest="$2"
>
>     if [[ ! -d "$src" ]]; then
>         echo "错误: 源目录 '${src}' 不存在" >&2
>         return 1
>     fi
>
>     local today
>     today=$(date +%Y-%m-%d)
>     local backup_path="${dest}/backup_${today}"
>
>     mkdir -p "$backup_path"
>
>     local copied=0
>     local skipped=0
>
>     for item in "$src"/*; do
>         if [[ -f "$item" ]]; then
>             cp "$item" "$backup_path/"
>             echo "复制: $(basename "$item")"
>             copied=$((copied + 1))
>         else
>             echo "跳过: $(basename "$item") (非文件)"
>             skipped=$((skipped + 1))
>         fi
>     done
>
>     echo "========================="
>     echo "备份完成:"
>     echo "  源:      ${src}"
>     echo "  目标:    ${backup_path}"
>     echo "  已复制:  ${copied} 个文件"
>     echo "  已跳过:  ${skipped} 个项目"
> }
>
> if [[ $# -lt 2 ]]; then
>     echo "用法: $0 <源目录> <目标目录>"
>     exit 1
> fi
>
> backup_dir "$1" "$2"
> ```
>
> `>&2` 将错误输出到标准错误流。`mkdir -p` 确保父目录存在。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 5. 扩展阅读

- [Bash 手册 - Looping Constructs](https://www.gnu.org/software/bash/manual/html_node/Looping-Constructs.html)
- [Bash 手册 - Shell Functions](https://www.gnu.org/software/bash/manual/html_node/Shell-Functions.html)
- [Bash 手册 - Bourne Shell Builtins (local)](https://www.gnu.org/software/bash/manual/html_node/Bourne-Shell-Builtins.html)
- [[03-bash-conditions|上一节: Bash 条件判断与流程控制]]
- [[05-bash-arrays-strings-files|下一节: Bash 数组、字符串与文件操作]]

---

## 常见陷阱

- **`for` 遍历带空格的文件名**：`for file in $(ls)` 会将文件名按空格拆分。用通配符 `for file in *` 或 `find -print0 | while read -r -d ''`。
- **管道中的 `while` 循环在子 shell 中执行**：`cat file | while read line; do count=$((count+1)); done` 中 `count` 的修改在循环外不可见。用进程替换 `while read line; do ... done < <(cat file)` 或 `shopt -s lastpipe`（Bash 4.2+）。
- **函数内忘记 `local`**：在函数内 `name="Alice"` 会污染全局命名空间。在大型脚本中这很难调试。养成习惯：函数内的变量一律用 `local`。
- **函数返回值 `return` 只能返回 0-255**：`return "hello"` 是错误用法，试图返回非数字会导致 `return` 被当作字符串返回码（无效）。返回字符串用 `echo` + 命令替换。
- **`for ((i=0; i<10; i++))` 中 `$` 的使用**：在 `(( ))` 内部，变量前面可以省略 `$`，写成 `for ((i=0; i<10; i++))`。在双括号外则需要 `$i`。
- **`while` 无限循环检查**：`while true` 或 `while :` 是无限循环。确保循环内有退出条件（`break`、`exit` 或条件变为假）。
- **`break` 和 `continue` 在函数内**：`break` 不能跨函数边界跳出函数的调用者。只能在函数内部影响函数内的循环。
