---
title: Bash 变量、输入输出与引号
updated: 2026-06-15
---

# Bash 变量、输入输出与引号

> 所属计划: [[plan|Shell 脚本编程：Bash、Zsh 与 Fish]]
> 预计耗时: 60 分钟
> 前置知识: [[01-bash-first-script|Bash 第一个脚本与运行方式]]

---

## 1. 概念讲解

### 变量：给数据起个名字

Bash 变量**无类型**——所有值都以字符串形式存储。定义变量时 `=` 两侧**不能有空格**，这是初学者最常犯的错误。

```bash
name="Alice"   # 正确
name = "Alice" # 错误！Bash 会把 name 当作命令执行
```

使用变量时，用 `$` 前缀或 `${}` 包裹：

```bash
echo $name      # 简单情况
echo ${name}    # 推荐：明确变量边界
echo "${name}"  # 最佳实践：永远加双引号
```

### 三种引号：单引号、双引号、反引号

这是 Bash 最重要的概念之一。三种引号行为完全不同：

| 引号类型 | 语法 | 变量展开 | 命令替换 | 转义 |
|----------|------|---------|---------|------|
| 双引号 | `"..."` | 是 | 是 | `\$` `\"` `\\` |
| 单引号 | `'...'` | 否 | 否 | 无（全部原样） |
| 无引号 | 裸词 | 是 | 是 | 是，且会分词 |

**关键规则**：有变量或空格的地方，用双引号包裹。否则 Bash 会对值进行**单词分割**和**通配符展开**，导致 bug。

```bash
file="my document.txt"
ls $file     # 危险！等同于 ls my document.txt（两个文件）
ls "$file"   # 正确：ls "my document.txt"（一个文件）
```

### 输入输出

| 命令       | 用途          | 示例                            |
| -------- | ----------- | ----------------------------- |
| `echo`   | 输出文本（简单）    | `echo "Hello"`                |
| `printf` | 格式化输出（精确控制） | `printf "Name: %s\n" "$name"` |
| `read`   | 读取用户输入      | `read -p "Name: " name`       |
| `cat`    | 输出文件内容      | `cat file.txt`                |
| 重定向 `>`  | 输出到文件（覆盖）   | `echo "hi" > file.txt`        |
| 重定向 `>>` | 输出到文件（追加）   | `echo "hi" >> file.txt`       |
| 管道 `\|`  | 将输出传给下一个命令  | `cat file.txt \| wc -l`       |

### 命令替换

`$(command)` 执行括号中的命令，把输出替换到当前位置。旧语法是 `` `command` ``，但现在推荐 `$()`，因为它可以嵌套：

```bash
echo "今天是 $(date +%Y-%m-%d)"
files_count=$(ls | wc -l)  # 当前目录文件数
```

---

## 2. 代码示例

### 示例 1：变量基础与引号对比

```bash
#!/usr/bin/env bash

name="Alice"
greeting="Hello, ${name}"

# 双引号：展开变量
echo "双引号: ${greeting}"

# 单引号：不展开
echo '单引号: ${greeting}'

# 无引号会怎样？
sentence="Hello   World"   # 多个空格
echo "有引号: [${sentence}]"
echo "无引号: [${sentence}]"  # 此处实际有引号，展示差异
echo "无引号: ["${sentence}"]"  # 错误示范！
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash quoting-demo.sh
```

**预期输出：**

```text
双引号: Hello, Alice
单引号: ${greeting}
有引号: [Hello   World]
无引号: [Hello World]
无引号: [Hello World]
```

### 示例 2：用户输入与格式化输出

```bash
#!/usr/bin/env bash

# 使用 read 读取用户输入
read -p "请输入你的名字: " username
read -p "请输入你的年龄: " age
read -sp "请输入密码: " password  # -s 隐藏输入

echo ""  # -s 不会自动换行，补一个换行
echo ""

# printf 格式化输出
printf "====================\n"
printf "姓名: %-10s 年龄: %3d\n" "$username" "$age"
printf "密码: %s\n" "$(echo "$password" | sed 's/./*/g')"
printf "====================\n"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash user-input.sh
```

**预期输出（交互式）：**

```text
请输入你的名字: Alice
请输入你的年龄: 25
请输入密码:
====================
姓名: Alice       年龄:  25
密码: ****
====================
```

### 示例 3：命令替换与算术

```bash
#!/usr/bin/env bash

# 命令替换
current_date=$(date +%Y-%m-%d)
current_user=$(whoami)
file_count=$(ls -1 | wc -l)

echo "日期:     ${current_date}"
echo "用户:     ${current_user}"
echo "文件数:   ${file_count}"

# 算术运算
a=10
b=3
sum=$((a + b))
diff=$((a - b))
prod=$((a * b))
div=$((a / b))      # 整数除法
mod=$((a % b))

printf "算术: %d + %d = %d\n" "$a" "$b" "$sum"
printf "算术: %d - %d = %d\n" "$a" "$b" "$diff"
printf "算术: %d * %d = %d\n" "$a" "$b" "$prod"
printf "算术: %d / %d = %d\n" "$a" "$b" "$div"
printf "算术: %d %% %d = %d\n" "$a" "$b" "$mod"
```

> **运行环境要求**: Bash 4.x+

**运行方式：**

```bash
bash substitution-demo.sh
```

**预期输出：**

```text
日期:     2026-06-15
用户:     alice
文件数:   5
算术: 10 + 3 = 13
算术: 10 - 3 = 7
算术: 10 * 3 = 30
算术: 10 / 3 = 3
算术: 10 % 3 = 1
```

---

## 3. 练习

### 练习 1: 个人信息收集器

编写脚本 `collect-info.sh`：
1. 提示用户输入姓名、年龄、城市（用 `read -p`）
2. 用 `printf` 格式化输出一张信息卡片：

```text
====================
  个人信息卡片
====================
姓名:    Alice
年龄:    25
城市:    Beijing
当前时间: 2026-06-15 14:30
====================
```

### 练习 2: 文件名安全处理

编写脚本 `safe-file.sh`，读取用户输入的文件名，然后安全地操作它：

1. 提示用户输入一个文件名（可以包含空格，如 `my report.txt`）
2. 用变量存储这个文件名
3. 分别用**不加引号**和**加双引号**的方式 `touch` 创建文件
4. 用 `ls -l` 展示两种方式创建的文件有什么不同
5. 分析为什么加引号是必要的

### 练习 3: 简单计算器（可选）

编写脚本 `calc.sh`：
1. 提示用户输入两个整数
2. 输出它们的和、差、积、商（浮点数，用 `bc` 命令）
3. 用 `printf` 格式化输出，小数点保留 2 位

> 提示：`echo "scale=2; 10 / 3" | bc` 输出 `3.33`。

---

## 4. 参考答案

> [!tip]- 练习 1 参考答案
> ```bash
> #!/usr/bin/env bash
>
> read -p "请输入姓名: " name
> read -p "请输入年龄: " age
> read -p "请输入城市: " city
>
> current_time=$(date "+%Y-%m-%d %H:%M")
>
> printf "====================\n"
> printf "  个人信息卡片\n"
> printf "====================\n"
> printf "姓名:    %s\n" "$name"
> printf "年龄:    %s\n" "$age"
> printf "城市:    %s\n" "$city"
> printf "当前时间: %s\n" "$current_time"
> printf "====================\n"
> ```
>
> 关键在于用双引号包裹所有变量，用 `printf` 精确控制格式。

> [!tip]- 练习 2 参考答案
> ```bash
> #!/usr/bin/env bash
>
> read -p "请输入文件名（可含空格）: " filename
>
> # 不加引号：Bash 会把空格当做分隔符
> # touch $filename   # 这会创建多个文件！
>
> # 加引号：安全地作为一个整体
> touch "$filename"
>
> echo "创建的文件:"
> ls -l "$filename"
> ```
>
> 不加引号时，如果输入 `my report.txt`，`touch $filename` 等同于 `touch my report.txt`，会创建 `my` 和 `report.txt` 两个文件。加引号后 `touch "$filename"` 只会创建一个文件 `my report.txt`（含空格）。
>
> 这是 Bash 最常见也最危险的陷阱之一。

> [!tip]- 练习 3 参考答案
> ```bash
> #!/usr/bin/env bash
>
> read -p "请输入第一个整数: " a
> read -p "请输入第二个整数: " b
>
> # 整数运算
> sum=$((a + b))
> diff=$((a - b))
> prod=$((a * b))
>
> # 浮点除法：用 bc
> quot=$(echo "scale=2; $a / $b" | bc)
>
> printf "============\n"
> printf "和:   %d\n" "$sum"
> printf "差:   %d\n" "$diff"
> printf "积:   %d\n" "$prod"
> printf "商:   %.2f\n" "$quot"
> printf "============\n"
> ```
>
> Bash 原生只支持整数。浮点运算需要借助 `bc` 或 `awk`。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 5. 扩展阅读

- [Bash 手册 - Quoting](https://www.gnu.org/software/bash/manual/html_node/Quoting.html)
- [Bash 手册 - Shell Parameter Expansion](https://www.gnu.org/software/bash/manual/html_node/Shell-Parameter-Expansion.html)
- [ShellCheck 规则 SC2086: Double quote to prevent globbing and word splitting](https://www.shellcheck.net/wiki/SC2086)
- [[01-bash-first-script|上一节: Bash 第一个脚本]]
- [[03-bash-conditions|下一节: Bash 条件判断与流程控制]]

---

## 常见陷阱

- **变量赋值 `=` 两侧有空格**：`name = "Alice"` 会被 Bash 解析为"执行 `name` 命令，参数是 `=` 和 `Alice`"。正确写法：`name="Alice"`。
- **不加引号导致单词分割**：`rm $filename` 若 `filename="my file.txt"`，等同于 `rm my file.txt`，可能误删文件。永远写 `rm "$filename"`。
- **单引号内无法展开变量**：`echo 'Hello, $USER'` 输出字面的 `Hello, $USER`，不展开。用双引号。
- **反引号嵌套混乱**：`` `cmd1 \`cmd2\`\` `` 难以阅读和调试。用 `$(cmd1 $(cmd2))` 代替。
- **`read` 不限制输入**：用户可能输入空值或非预期内容。在生产脚本中应验证输入。后续课程会深入讨论。
- **整数除法截断**：`$((5 / 2))` 结果是 `2`，不是 `2.5`。Bash 只做整数运算，需要浮点用 `bc` 或 `awk`。
- **`echo` 与特殊字符**：`echo` 处理 `-n`、`-e`、反斜杠等行为因系统而异。需要精确控制时用 `printf`。
