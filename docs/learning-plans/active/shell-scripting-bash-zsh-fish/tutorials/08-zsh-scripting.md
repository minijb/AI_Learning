---
title: Zsh 脚本：Bash 超集与增强特性
updated: 2026-06-15
---

# Zsh 脚本：Bash 超集与增强特性

> 所属计划: Shell 脚本编程：Bash、Zsh 与 Fish
> 预计耗时: 60min
> 前置知识: [[01-bash-first-script|Bash 第一个脚本]]、[[02-bash-variables-io|变量与 IO]]、[[03-bash-conditions|条件判断]]、[[04-bash-loops-functions|循环与函数]]、[[05-bash-arrays-strings-files|数组与文件操作]]

---

## 1. 概念讲解

### 为什么需要 Zsh 脚本？

Bash 是 Linux 世界的通用语言，但 macOS 从 Catalina（10.15）开始已将默认 shell 从 Bash 切换为 Zsh。这意味着：

- 你在 macOS 上写的 "Bash 脚本" 实际运行在 Zsh 上（`/bin/sh` 仍指向 Bash，但交互 shell 是 Zsh）。
- Zsh **向後兼容绝大多数 Bash 语法**，但提供了一系列增强特性，值得特意学习。
- 如果你的脚本只在 macOS 或安装了 Zsh 的环境运行，利用 Zsh 特性可以让代码更简洁、更安全。

把 Zsh 理解为 "Bash 的现代化版本"：它继承了 Bash 的生态，同时修复了一些历史包袱，并加入了现代化 shell 的特性。

### Zsh 与 Bash 的核心差异概览

| 特性 | Bash 5.x | Zsh 5.x |
|------|----------|---------|
| 数组索引 | 从 `0` 开始 | 从 `1` 开始（默认） |
| 关联数组 | 支持 | 原生支持，语法更简洁 |
| 浮点数运算 | 不支持（需 `bc`/`awk`） | 内置支持 `$(( 3.14 * 2 ))` |
| 通配符展开 | 基本 glob | 扩展 glob（`**`、限定符） |
| 变量作用域 | `local`（函数内） | `typeset`/`local` |
| 右提示符 | 不支持 | `RPROMPT` |
| 自动补全 | 需配置 | 内置强大补全系统 |
| 拼写纠正 | 不支持 | 内置 `setopt CORRECT` |
| 路径替换 | 不支持 | `cd old new` 替换路径中字符串 |

### .sh vs .zsh 文件约定

这是一个容易混淆的话题，Zsh 社区有明确的约定：

- **`.sh` 文件**：可独立执行的脚本。Shebang 指定解释器：`#!/usr/bin/env zsh`。文件有执行权限，用户直接 `./script.sh` 运行。
- **`.zsh` 文件**：被 `source`（或 `.`）加载的库/模块文件。例如 `source ./lib.zsh` 加载函数和变量定义。这些文件不应有 shebang，也不应有执行权限。

实践中，如果你写的是 Zsh 专属脚本且不介意可移植性，直接用 `.zsh` 也无妨。关键是 Shebang 行明确指定解释器。

### `typeset`：变量管理利器

`typeset` 是 Zsh 提供的变量声明和管理命令，比 Bash 的 `declare` 更强大：

```zsh
typeset varname           # 声明（同 declare）
typeset -i age=25         # 整数变量
typeset -F pi=3.14        # 浮点数变量
typeset -a arr=(a b c)    # 数组
typeset -A map=([key]=val)# 关联数组
typeset -r readonly=42    # 只读
typeset -x export_var     # 导出为环境变量
typeset -l lower          # 值自动转小写
typeset -u upper          # 值自动转大写
typeset -H hidden         # 隐藏变量（不传给子进程）
```

在函数内，`typeset` 默认创建**局部变量**（不需要像 Bash 那样额外加 `-g` 才创建全局变量）。这从根本上避免了 Bash 中常见的变量污染问题。

### Zsh 数组

Zsh 数组比 Bash 更灵活，但有一个重要差异：**默认索引从 `1` 开始**。

```zsh
# 定义数组
arr=(first second third)
echo $arr[1]       # => first（不是 "second"！）
echo $arr[2]       # => second
echo $arr[3]       # => third
echo $arr[-1]      # => third（负数索引从末尾取）
echo $arr[2,-1]    # => second third（范围切片）
echo $#arr         # => 3（数组长度）
```

如果习惯 Bash 的 `0` 索引，可以设置 `setopt KSH_ARRAYS` 切换到 0 索引模式——但会让脚本对 Zsh 用户不可预期，一般不推荐。

### 关联数组

Zsh 的关联数组语法比 Bash 更自然：

```zsh
typeset -A config
config=(
  host    localhost
  port    8080
  debug   true
)

echo $config[host]    # => localhost
echo ${(k)config}     # => host port debug（所有 key）
echo ${(v)config}     # => localhost 8080 true（所有 value）

# 遍历
for key val in ${(kv)config}; do
  echo "$key = $val"
done
```

### 函数：局部变量默认

Zsh 中函数的变量作用域与 Bash 不同：

```zsh
# Zsh：typeset 在函数内默认创建局部变量
myfunc() {
  typeset foo="local"       # 局部变量，不影响外层
  bar="global"              # 仍然是全局！和 Bash 一样
  echo $foo
}

# 推荐始终使用 typeset/local 声明局部变量
clean_func() {
  local tmp_file="/tmp/$$.tmp"
  # ... 使用 tmp_file
  rm -f "$tmp_file"
}
```

与 Bash 的关键区别：Zsh 函数不需要 `function` 关键字（虽然支持），且内部使用 `typeset` 等价于 Bash 的 `local`。

### Zsh 扩展通配符

Zsh 的通配符 (globbing) 远比 Bash 强大：

```zsh
# 递归通配符
ls **/*.txt       # 递归查找所有 .txt 文件（Bash 5+ 需要 shopt -s globstar）

# 通配符限定符
ls *.txt(.)       # 只匹配普通文件（不含目录）
ls *(/)            # 只匹配目录
ls *(.m-1)         # 最近 1 天内修改的文件
ls *(.L+1M)        # 大于 1MB 的文件
ls *(.Lk-100)      # 小于 100KB 的文件
ls *(.*)           # 只匹配隐藏文件

# 模式分组
ls (foo|bar).txt   # 匹配 foo.txt 或 bar.txt
ls <1-100>.log     # 匹配 1.log 到 100.log
```

---

## 2. 代码示例

> **运行环境要求**：Zsh 5.0+（macOS 自带 Zsh 5.8+，Linux 需 `apt install zsh` / `dnf install zsh`）。

### 示例 1：typeset 类型声明

```zsh
#!/usr/bin/env zsh
# typeset 演示

# 整数运算
typeset -i count=10
count+=5              # 算术加法：count 变成 15
echo "count = $count" # => count = 15

# 浮点数运算（Zsh 独有）
typeset -F price=9.99
typeset -F tax_rate=0.08
typeset -F total=price * (1.0 + tax_rate)
echo "total = $total" # => total ≈ 10.7892

# 自动大小写
typeset -l lowercase="HELLO World"
typeset -u uppercase="hello WORLD"
echo "$lowercase $uppercase" # => hello world HELLO WORLD
```

### 示例 2：关联数组实战——配置文件解析器

```zsh
#!/usr/bin/env zsh
# 模拟加载一个 ini-like 配置文件

typeset -A settings

# 模拟从文件读取（实际场景中从文件逐行解析）
settings=(
  app_name    "MyZshTool"
  version     "2.1.0"
  log_level   "debug"
  max_retries 3
  timeout     30.0
)

# 读取配置
echo "Application: $settings[app_name]"
echo "Version:     $settings[version]"

# 检查 key 是否存在
if [[ -v settings[log_level] ]]; then
  echo "Log level:   $settings[log_level]"
fi

# 遍历所有配置
echo ""
echo "--- All settings ---"
for key val in ${(kv)settings}; do
  printf "  %-15s = %s\n" "$key" "$val"
done
```

**预期输出：**

```text
Application: MyZshTool
Version:     2.1.0
Log level:   debug

--- All settings ---
  app_name         = MyZshTool
  version          = 2.1.0
  log_level        = debug
  max_retries      = 3
  timeout          = 30.0
```

### 示例 3：Zsh 扩展通配符实战

```zsh
#!/usr/bin/env zsh
# Zsh 通配符限定符演示

# 列出当前目录最近 7 天修改的 .md 文件
echo "=== Recent .md files (last 7 days) ==="
ls -lh *.md(.m-7) 2>/dev/null || echo "  (none found)"

# 列出大于 10KB 的 .log 文件
echo ""
echo "=== Large log files (> 10KB) ==="
ls -lh *.log(.L+10240) 2>/dev/null || echo "  (none found)"

# 递归查找所有空目录
echo ""
echo "=== Empty directories ==="
ls -d **/*(/^F) 2>/dev/null || echo "  (none found)"

# 解释: **/* 递归, (/) 只要目录, (^F) 只要非满的（即空的）
echo ""
echo "=== All subdirectories (recursive) ==="
print -l **/*(/)
```

### 示例 4：Zsh 风格的健壮函数

```zsh
#!/usr/bin/env zsh
# 使用 Zsh 特性编写健壮函数

# 模拟 API 调用，带重试和超时
Api_Fetch() {
  # Zsh 允许在函数内设置局部选项
  setopt local_options err_return

  local url="$1"
  local max_retries="${2:-3}"

  for ((i = 1; i <= max_retries; i++)); do
    if response=$(curl -sS --connect-timeout 5 "$url" 2>&1); then
      echo "$response"
      return 0
    fi
    echo "Retry $i/$max_retries..." >&2
    sleep 1
  done

  echo "ERROR: Failed after $max_retries attempts" >&2
  return 1
}

# 使用
# Api_Fetch "https://api.example.com/data"
```

### 示例 5：Zsh 条件表达式增强

```zsh
#!/usr/bin/env zsh
# Zsh 独有的条件测试

filename="/etc/hosts"

# Zsh 支持更多文件测试操作符（Bash 不支持）
[[ -r "$filename" ]] && echo "readable"   # 都可读
[[ -w "$filename" ]] && echo "writable"   # 都可写
[[ -x "$filename" ]] && echo "executable" # 都可执行

# Zsh 独有的条件
[[ -o INTERACTIVE ]] && echo "running interactively"
[[ -t 0 ]] && echo "stdin is a terminal"

# 正则匹配（Bash 3.0+ 也支持 =~，但 Zsh 更稳定）
version="v2.13.0-alpha"
if [[ "$version" =~ '^v[0-9]+\.[0-9]+\.[0-9]+' ]]; then
  echo "Valid semver-like version"
fi

# 模式匹配（等价于 [[ $var == pattern ]]，但更清晰）
if [[ "$OSTYPE" == darwin* ]]; then
  echo "Running on macOS"
elif [[ "$OSTYPE" == linux* ]]; then
  echo "Running on Linux"
fi
```

---

## 3. 练习

### 练习 1：typeset 类型转换

编写一个 Zsh 脚本 `temp-convert.zsh`，定义一个浮点数变量 `celsius` 并将其转换为华氏度（公式：`F = C × 9/5 + 32`），使用 `typeset -F` 声明变量。再定义一个整数变量，测试将浮点数赋值给整数变量时 Zsh 的自动截断行为。

### 练习 2：文件批量查找

编写一个 Zsh 脚本 `find-large-files.zsh`，接受一个目录路径和一个大小阈值（单位 MB）作为参数，使用 Zsh 通配符限定符递归查找所有超过阈值大小的文件，按大小降序排列输出。

### 练习 3：配置管理函数库（可选）

编写一个 Zsh 函数库文件 `config.zsh`（使用 `.zsh` 扩展名），提供以下函数：

- `Config_Load`：从文件读取 key=value 配置到关联数组
- `Config_Get`：从关联数组取值，支持默认值
- `Config_List`：列出所有配置项

然后写一个脚本 `app.sh` 来 source 这个库并使用它。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```zsh
> #!/usr/bin/env zsh
> # temp-convert.zsh
>
> typeset -F celsius=36.5
> typeset -F fahrenheit=celsius * 9.0 / 5.0 + 32.0
> echo "$celsius °C = $fahrenheit °F"
>
> # 浮点数赋值给整数变量——Zsh 自动截断（向零取整）
> typeset -i truncated=celsius
> echo "Truncated to int: $truncated"   # => 36
>
> # 浮点数赋值给未类型声明的变量——保持字符串
> a=3.14
> echo "a = $a"  # 作为字符串保留
> ```

> [!tip]- 练习 2 参考答案
> ```zsh
> #!/usr/bin/env zsh
> # find-large-files.zsh
>
> if [[ $# -lt 2 ]]; then
>   echo "Usage: $0 <directory> <size_mb>" >&2
>   exit 1
> fi
>
> target_dir="$1"
> size_mb="$2"
> size_bytes=$(( size_mb * 1024 * 1024 ))
>
> cd "$target_dir" || exit 1
>
> print -l -- **/*(.OL+${size_bytes}) | while read -r f; do
>   size_kb=$(stat -f '%z' "$f" 2>/dev/null || stat -c '%s' "$f" 2>/dev/null)
>   size_kb=$(( size_kb / 1024 ))
>   echo "${size_kb}KB  $f"
> done
> ```
>
> **说明**：`OL` 限定符让结果按大小（Length）降序（descending Order）排列；`+${size_bytes}` 匹配大于指定字节数。

> [!tip]- 练习 3 参考答案
> **config.zsh**（库文件，无 shebang，无执行权限）：
> ```zsh
> # config.zsh — configuration manager library
> typeset -A _CONFIG_MAP
>
> Config_Load() {
>   local file="$1"
>   if [[ ! -r "$file" ]]; then
>     echo "ERROR: Cannot read config file: $file" >&2
>     return 1
>   fi
>
>   while IFS='=' read -r key value; do
>     # 跳过空行和注释
>     [[ -z "$key" || "$key" == \#* ]] && continue
>     # 去除首尾空白
>     key="${key## }"; key="${key%% }"
>     value="${value## }"; value="${value%% }"
>     _CONFIG_MAP[$key]="$value"
>   done < "$file"
> }
>
> Config_Get() {
>   local key="$1"
>   local default="${2:-}"
>   if [[ -v _CONFIG_MAP[$key] ]]; then
>     echo "${_CONFIG_MAP[$key]}"
>   else
>     echo "$default"
>   fi
> }
>
> Config_List() {
>   for key val in ${(kv)_CONFIG_MAP}; do
>     printf "  %-20s = %s\n" "$key" "$val"
>   done
> }
> ```
>
> **app.sh**（可执行脚本）：
> ```zsh
> #!/usr/bin/env zsh
> # app.sh — demonstrates config library usage
>
> source "${0:A:h}/config.zsh"
>
> Config_Load "settings.conf"
>
> echo "app_name = $(Config_Get app_name 'Unknown')"
> echo "debug    = $(Config_Get debug 'false')"
> echo ""
> echo "All settings:"
> Config_List
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Zsh 官方文档 — Zsh Manual](https://zsh.sourceforge.io/Doc/Release/)
- [Zsh 用户指南 — A User's Guide to the Z-Shell](https://zsh.sourceforge.io/Guide/)
- [Zsh 与 Bash 差异详解](https://www.bash2zsh.com/)
- [Oh My Zsh — 最流行的 Zsh 插件框架](https://ohmyz.sh/)
- [Zsh 扩展通配符完整参考](https://zsh.sourceforge.io/Doc/Release/Expansion.html#Glob-Qualifiers)
- [macOS 切换到 Zsh 的官方说明](https://support.apple.com/en-us/HT208050)

---

## 常见陷阱

- **数组索引混乱**：Zsh 默认索引从 `1` 开始，而非 Bash 的 `0`。`$arr[0]` 在 Zsh 中是空值。如果从 Bash 迁移，这是最容易踩的坑。避免使用 `KSH_ARRAYS` 选项——它会让脚本行为难以预测。
- **函数内局部变量**：`typeset` 在函数内声明的是局部变量，但**裸赋值 `var=value` 仍然是全局的**。养成在函数内始终使用 `typeset` 或 `local` 的习惯。
- **Shebang 指定错误**：写 Zsh 脚本必须用 `#!/usr/bin/env zsh`，不能用 `#!/bin/bash`——后者会以 Bash 兼容模式运行，丢失 Zsh 特性。
- **通配符在无匹配时行为不同**：Bash 中无匹配的 glob 会原样返回模式字符串；Zsh 默认会报错 `no matches found`。可以在脚本中使用 `setopt nonomatch` 或使用 `(N)` 限定符来改变行为：`*.txt(N)`。
- **变量展开的分词行为**：Zsh 默认不对未引用的变量展开进行分词（更像其他编程语言）。这减少了 Bash 中常见的引号错误，但如果你的脚本需要 Bash 兼容的分词行为，需要显式使用 `$=var` 或设置 `SH_WORD_SPLIT` 选项。
- **`.sh` vs `.zsh` 混淆**：把函数库文件写成 `.sh` 并添加执行权限是常见做法，但会让意图不清。遵循约定：可执行脚本用 `.sh` + 执行权限，库文件用 `.zsh` + 无执行权限。
