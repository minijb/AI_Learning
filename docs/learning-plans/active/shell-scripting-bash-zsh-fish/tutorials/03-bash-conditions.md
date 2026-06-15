---
title: Bash 条件判断与流程控制
updated: 2026-06-15
---

# Bash 条件判断与流程控制

> 所属计划: [[plan|Shell 脚本编程：Bash、Zsh 与 Fish]]
> 预计耗时: 60 分钟
> 前置知识: [[02-bash-variables-io|Bash 变量、输入输出与引号]]

---

## 1. 概念讲解

### 条件判断的本质

Bash 中的条件判断基于**命令的退出状态码**。每条命令执行后都有一个退出码：`0` 表示成功（真），**非 `0`** 表示失败（假）。

这与其他编程语言相反——大多数语言中 `0` 是假、非 `0` 是真。Bash 里记住：**成功就是真**。

```bash
ls /tmp       # 成功 → 退出码 0
echo $?        # 输出 0

ls /nonexist  # 失败 → 退出码 2
echo $?        # 输出 2
```

### `[[ ]]` vs `[ ]` vs `test`

Bash 中做条件判断有三种方式：

| 方式 | 语法 | 特点 | 推荐场景 |
|------|------|------|----------|
| `[[ ]]` | `[[ "$a" == "$b" ]]` | Bash 内置，支持 `&&` `\|\|` `<` `>` 和正则 | **Bash 脚本首选** |
| `[ ]` | `[ "$a" = "$b" ]` | POSIX 标准，实际是 `test` 命令的别名 | 需要 POSIX 兼容时 |
| `test` | `test "$a" = "$b"` | 与 `[ ]` 等价 | 极少直接使用 |

**关键规则**：用 `[[ ]]` 写 Bash 脚本最安全。它不会做单词分割，支持正则匹配 `=~`，且 `&&` `||` 可以直接写在括号内。

### if / elif / else 结构

```bash
if [[ condition ]]; then
    # 条件为真时执行
elif [[ another_condition ]]; then
    # 另一个条件为真时执行
else
    # 以上都不成立时执行
fi
```

语法要点：
- `if` 和 `then` 必须在同一行（或用分号分隔）或不同行
- 以 `fi` 结束（`if` 的反写）
- `elif` 和 `else` 是可选的

### 常用条件判断操作符

**字符串判断：**

| 操作符 | 含义 | 示例 |
|--------|------|------|
| `-z "$str"` | 字符串为空 | `[[ -z "$name" ]]` |
| `-n "$str"` | 字符串非空 | `[[ -n "$name" ]]` |
| `"$a" == "$b"` | 字符串相等 | `[[ "$a" == "$b" ]]` |
| `"$a" != "$b"` | 字符串不等 | `[[ "$a" != "$b" ]]` |
| `"$a" =~ regex` | 正则匹配（仅 `[[ ]]`） | `[[ "$email" =~ @ ]]` |

**数值判断：**

| 操作符 | 含义 | 示例 |
|--------|------|------|
| `-eq` | 等于 | `[[ $a -eq $b ]]` |
| `-ne` | 不等 | `[[ $a -ne $b ]]` |
| `-lt` | 小于 | `[[ $a -lt $b ]]` |
| `-le` | 小于等于 | `[[ $a -le $b ]]` |
| `-gt` | 大于 | `[[ $a -gt $b ]]` |
| `-ge` | 大于等于 | `[[ $a -ge $b ]]` |

**文件判断：**

| 操作符 | 含义 |
|--------|------|
| `-f "$file"` | 是普通文件 |
| `-d "$dir"` | 是目录 |
| `-e "$path"` | 存在（文件或目录） |
| `-r "$file"` | 可读 |
| `-w "$file"` | 可写 |
| `-x "$file"` | 可执行 |
| `-s "$file"` | 文件存在且非空 |
| `"$a" -nt "$b"` | a 比 b 新（newer than） |
| `"$a" -ot "$b"` | a 比 b 旧（older than） |

### 逻辑组合

```bash
# 与：两种写法都行
[[ "$a" == "yes" && "$b" == "yes" ]]
[[ "$a" == "yes" ]] && [[ "$b" == "yes" ]]

# 或
[[ "$a" == "yes" || "$b" == "yes" ]]
[[ "$a" == "yes" ]] || [[ "$b" == "yes" ]]

# 非
[[ ! "$a" == "yes" ]]
```

### case 语句：多路分支

当 `if/elif` 链太长时，`case` 更清晰：

```bash
case "$variable" in
    pattern1)
        commands
        ;;
    pattern2|pattern3)
        commands
        ;;
    *)
        # 默认分支（通配）
        commands
        ;;
esac
```

---

## 2. 代码示例

### 示例 1：文件检查与分支

```bash
#!/usr/bin/env bash

filepath="$1"  # 从命令行参数获取

if [[ -z "$filepath" ]]; then
    echo "用法: $0 <文件路径>"
    exit 1
fi

if [[ -f "$filepath" ]]; then
    echo "'${filepath}' 是一个普通文件"
    echo "大小: $(wc -c < "$filepath") 字节"

    if [[ -s "$filepath" ]]; then
        echo "文件非空"
    else
        echo "文件为空"
    fi

elif [[ -d "$filepath" ]]; then
    echo "'${filepath}' 是一个目录"
    echo "包含 $(ls -1 "$filepath" | wc -l) 个项目"

else
    echo "'${filepath}' 不存在"
    exit 1
fi
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
chmod u+x file-check.sh
./file-check.sh /etc/hosts
./file-check.sh /etc
./file-check.sh /nonexist
```

**预期输出：**

```text
# ./file-check.sh /etc/hosts
'/etc/hosts' 是一个普通文件
大小: 225 字节
文件非空

# ./file-check.sh /etc
'/etc' 是一个目录
包含 156 个项目

# ./file-check.sh /nonexist
'/nonexist' 不存在
```

### 示例 2：数值比较与成绩评级

```bash
#!/usr/bin/env bash

read -p "请输入分数 (0-100): " score

# 输入验证
if [[ ! "$score" =~ ^[0-9]+$ ]]; then
    echo "错误: 请输入整数"
    exit 1
fi

if [[ $score -lt 0 || $score -gt 100 ]]; then
    echo "错误: 分数必须在 0-100 之间"
    exit 1
fi

# 评级
if [[ $score -ge 90 ]]; then
    grade="A"
elif [[ $score -ge 80 ]]; then
    grade="B"
elif [[ $score -ge 70 ]]; then
    grade="C"
elif [[ $score -ge 60 ]]; then
    grade="D"
else
    grade="F"
fi

echo "分数: ${score} → 等级: ${grade}"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash grade.sh
```

**预期输出：**

```text
请输入分数 (0-100): 85
分数: 85 → 等级: B
```

### 示例 3：case 菜单

```bash
#!/usr/bin/env bash

echo "请选择操作:"
echo "1) 显示日期"
echo "2) 显示当前目录"
echo "3) 显示当前用户"
echo "4) 退出"
read -p "输入选项 [1-4]: " choice

case "$choice" in
    1)
        echo "日期: $(date)"
        ;;
    2)
        echo "目录: $(pwd)"
        ;;
    3)
        echo "用户: $(whoami)"
        ;;
    4)
        echo "再见!"
        exit 0
        ;;
    *)
        echo "无效选项: ${choice}"
        exit 1
        ;;
esac
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash menu.sh
```

**预期输出：**

```text
请选择操作:
1) 显示日期
2) 显示当前目录
3) 显示当前用户
4) 退出
输入选项 [1-4]: 1
日期: Sun Jun 15 14:30:00 CST 2026
```

### 示例 4：正则匹配验证

```bash
#!/usr/bin/env bash

read -p "请输入邮箱地址: " email

if [[ -z "$email" ]]; then
    echo "邮箱不能为空"
    exit 1
fi

# [[ ]] 的 =~ 运算符做正则匹配
if [[ "$email" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    echo "'${email}' 是有效的邮箱地址"
else
    echo "'${email}' 不是有效的邮箱地址"
fi
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash email-validate.sh
```

**预期输出：**

```text
请输入邮箱地址: alice@example.com
'alice@example.com' 是有效的邮箱地址

请输入邮箱地址: not-an-email
'not-an-email' 不是有效的邮箱地址
```

---

## 3. 练习

### 练习 1: 奇偶判断

编写脚本 `even-odd.sh`：
1. 读取用户输入的一个整数
2. 判断它是奇数还是偶数
3. 如果是负数，额外提示"是负数"
4. 输出格式：`数字 X 是偶数` 或 `数字 X 是奇数`

> 提示：偶数满足 `X % 2 == 0`。

### 练习 2: 文件类型分类器

编写脚本 `file-classify.sh`：
1. 接受一个命令行参数作为路径
2. 判断该路径是普通文件、目录还是符号链接（用 `-L` 判断链接）
3. 如果是普通文件，进一步判断是否可执行（`-x`）
4. 如果是目录，列出该目录下有多少个项目
5. 如果不存在，报错退出
6. **给所有变量都加上双引号**

### 练习 3: 交互式计算器（可选）

编写脚本 `interactive-calc.sh`：
1. 用 `case` 实现菜单：加、减、乘、除、求余、退出
2. 每项操作提示用户输入两个数字
3. 除法时检查除数是否为 `0`
4. 循环直到用户选择退出

> 提示：你需要用到下一节的循环知识，可以 peek 一下 `while` 的用法。

---

## 4. 参考答案

> [!tip]- 练习 1 参考答案
> ```bash
> #!/usr/bin/env bash
>
> read -p "请输入一个整数: " num
>
> # 验证输入是否为整数
> if [[ ! "$num" =~ ^-?[0-9]+$ ]]; then
>     echo "错误: 请输入整数"
>     exit 1
> fi
>
> if [[ $num -lt 0 ]]; then
>     echo -n "负数, "
> fi
>
> if (( num % 2 == 0 )); then
>     echo "数字 ${num} 是偶数"
> else
>     echo "数字 ${num} 是奇数"
> fi
> ```
>
> 这里用了 `(( ))` 算术判断，它是 `[[ ]]` 的算术版本，可以用 `>` `<` `==` 等常规符号。

> [!tip]- 练习 2 参考答案
> ```bash
> #!/usr/bin/env bash
>
> path="$1"
>
> if [[ -z "$path" ]]; then
>     echo "用法: $0 <路径>"
>     exit 1
> fi
>
> if [[ -L "$path" ]]; then
>     echo "'${path}' 是一个符号链接"
>     echo "指向: $(readlink "$path")"
> elif [[ -f "$path" ]]; then
>     echo "'${path}' 是一个普通文件"
>     echo "大小: $(wc -c < "$path") 字节"
>     if [[ -x "$path" ]]; then
>         echo "该文件可执行"
>     else
>         echo "该文件不可执行"
>     fi
> elif [[ -d "$path" ]]; then
>     echo "'${path}' 是一个目录"
>     count=$(ls -1 "$path" | wc -l)
>     echo "包含 ${count} 个项目"
> else
>     echo "错误: '${path}' 不存在"
>     exit 1
> fi
> ```
>
> 注意：符号链接的判断 `-L` 必须在 `-f` 和 `-d` 之前，因为符号链接既满足 `-L` 也满足 `-f`（如果链接指向文件）。

> [!tip]- 练习 3 参考答案
> ```bash
> #!/usr/bin/env bash
>
> while true; do
>     echo ""
>     echo "======== 计算器 ========"
>     echo "1) 加法"
>     echo "2) 减法"
>     echo "3) 乘法"
>     echo "4) 除法"
>     echo "5) 求余"
>     echo "6) 退出"
>     echo "========================"
>     read -p "请选择 [1-6]: " choice
>
>     case "$choice" in
>         1) op="+" ;;
>         2) op="-" ;;
>         3) op="*" ;;
>         4) op="/" ;;
>         5) op="%" ;;
>         6) echo "再见!"; exit 0 ;;
>         *) echo "无效选项"; continue ;;
>     esac
>
>     read -p "输入第一个数字: " a
>     read -p "输入第二个数字: " b
>
>     if [[ ! "$a" =~ ^-?[0-9]+$ ]] || [[ ! "$b" =~ ^-?[0-9]+$ ]]; then
>         echo "错误: 请输入整数"
>         continue
>     fi
>
>     if [[ "$op" == "/" && $b -eq 0 ]]; then
>         echo "错误: 除数不能为 0"
>         continue
>     fi
>
>     result=$((a "$op" b))
>     echo "结果: ${a} ${op} ${b} = ${result}"
> done
> ```
>
> 注意 `$((a "$op" b))` 中 `"$op"` 是 Bash 算术展开支持的动态运算符写法。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 5. 扩展阅读

- [Bash 手册 - Conditional Constructs](https://www.gnu.org/software/bash/manual/html_node/Conditional-Constructs.html)
- [Bash 手册 - Bash Conditional Expressions](https://www.gnu.org/software/bash/manual/html_node/Bash-Conditional-Expressions.html)
- [Why `[[ ]]` is better than `[ ]` in Bash](https://mywiki.wooledge.org/BashFAQ/031)
- [[02-bash-variables-io|上一节: Bash 变量、输入输出与引号]]
- [[04-bash-loops-functions|下一节: Bash 循环与函数]]

---

## 常见陷阱

- **`[ ]` 中忘记空格**：`[ -f "$file"]`（缺少空格）报语法错误。正确：`[ -f "$file" ]`（内侧各留一个空格）。`[[ ]]` 可以容忍，但 `[ ]` 不行。
- **字符串相等用 `=` 还是 `==`**：`[ ]` 中只用 `=`，`[[ ]]` 两者都行。推荐在 `[[ ]]` 中用 `==` 更直观。
- **比较数字用了字符串操作符**：`[[ "$a" == "$b" ]]` 比较的是字典序，`"10"` 会小于 `"2"`。数值比较用 `-eq`、`-lt` 等。
- **忘记给变量加引号**：`[[ -f $file ]]` 若 `$file` 为空，变成 `[[ -f ]]`，语法错误。正确：`[[ -f "$file" ]]`。`[[ ]]` 对右侧不需要引号，但左侧的变量仍然需要。
- **正则匹配时 `=~` 不加引号**：`[[ "$str" =~ "$pattern" ]]` 中 pattern 加引号会变成字面匹配而非正则。正确：`[[ "$str" =~ ^hello ]]`（pattern 不加引号）。
- **`case` 忘记 `;;`**：每个分支必须以 `;;` 结束，否则会"穿透"到下一个分支。
- **`exit` 与 `return` 混淆**：`exit` 退出整个脚本，`return` 从函数返回（见下一节）。在脚本顶层用 `exit`。
