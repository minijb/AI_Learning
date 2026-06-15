---
title: Bash 实战：批量文件重命名工具
updated: 2026-06-15
tags: [shell, bash, project, file-renamer]
---

# Bash 实战：批量文件重命名工具

> 所属计划: Shell 脚本编程：Bash、Zsh 与 Fish
> 预计耗时: 90min
> 前置知识: [[01-bash-first-script|Bash 第一个脚本]]、[[02-bash-variables-io|变量与 I/O]]、[[03-bash-conditions|条件判断]]、[[04-bash-loops-functions|循环与函数]]、[[05-bash-arrays-strings-files|数组、字符串与文件]]、[[06-bash-best-practices|最佳实践]]

---

## 1. 概念讲解

这是本学习计划 Bash 部分的首个综合性项目。你将从头构建一个生产可用的批量文件重命名工具，它整合了前六个教程的所有知识点。

### 为什么需要这个？

无论是整理照片（`IMG_0001.JPG` → `2024-tokyo-trip-001.jpg`）、清理下载文件（`document (1).pdf` → `invoice-2024.pdf`）、还是给代码文件加统一前缀，批量重命名都是最频繁的 shell 自动化需求。手写一个工具不仅能解决实际需求，更能让你在真实场景中理解 Bash 脚本设计。

### 核心设计

- **三个重命名模式**：替换、正则替换、编号重命名。
- **安全第一**：默认 dry-run 模式，用 `--execute` 才真正改名。
- **幂等性**：重复执行不会造成损坏（检查冲突、不覆盖已有文件）。
- **自文档化**：`--help` 输出完整用法。
- **严格模式 + trap**：所有错误被捕获，临时文件自动清理。

---

## 2. 完整脚本

### 2.1 脚本源码

**运行环境要求**: Bash 4.0+（使用关联数组和 `readarray`）

将以下内容保存为 `batch-rename.sh`：

```bash
#!/usr/bin/env bash
# ============================================================
# batch-rename.sh — 批量文件重命名工具
#
# 模式:
#   replace  OLD NEW      将文件名中的 OLD 替换为 NEW
#   regex    PATTERN REPL  用正则 PATTERN 匹配，替换为 REPL
#   number   PREFIX [EXT]  将匹配文件按编号重命名为 PREFIX_001.EXT
#
# 用法:
#   ./batch-rename.sh [选项] replace <OLD> <NEW> <文件模式>
#   ./batch-rename.sh [选项] regex <PATTERN> <REPL> <文件模式>
#   ./batch-rename.sh [选项] number <PREFIX> <文件模式> [扩展名]
#
# 选项:
#   -x, --execute   执行重命名（默认 dry-run）
#   -r, --recursive 递归处理子目录
#   -f, --force     覆盖已存在的目标文件
#   -q, --quiet     减少输出
#   -h, --help      显示帮助
# ============================================================

set -euo pipefail
IFS=$'\n\t'

# === 全局变量 ===
DRY_RUN=true
RECURSIVE=false
FORCE=false
QUIET=false
RENAMED=0
SKIPPED=0
ERRORS=0
TMP_LOG=""

# === 颜色输出（如果终端支持） ===
if [[ -t 1 ]]; then
    COLOR_RESET='\033[0m'
    COLOR_GREEN='\033[0;32m'
    COLOR_YELLOW='\033[1;33m'
    COLOR_RED='\033[0;31m'
    COLOR_CYAN='\033[0;36m'
else
    COLOR_RESET=''
    COLOR_GREEN=''
    COLOR_YELLOW=''
    COLOR_RED=''
    COLOR_CYAN=''
fi

# === 清理函数 ===
cleanup() {
    local exit_code=$?
    if [[ -n "$TMP_LOG" && -f "$TMP_LOG" ]]; then
        rm -f "$TMP_LOG"
    fi
    exit $exit_code
}
trap cleanup EXIT

on_error() {
    local lineno="$1"
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} Unexpected error at line $lineno" >&2
}
trap 'on_error "$LINENO"' ERR

# === 帮助信息 ===
show_help() {
    cat << 'EOF'
batch-rename.sh — 批量文件重命名工具

用法:
  ./batch-rename.sh [OPTIONS] MODE ARGS... FILE_PATTERN

模式:
  replace  OLD NEW      将文件名中的 OLD 替换为 NEW
  regex    PATTERN REPL  用正则匹配，替换为 REPL
  number   PREFIX [EXT]  按编号重命名为 PREFIX_001.EXT

选项:
  -x, --execute   执行重命名（默认 dry-run 预览模式）
  -r, --recursive 递归处理子目录
  -f, --force     覆盖已存在的目标文件
  -q, --quiet     减少输出，只显示摘要
  -h, --help      显示此帮助

示例:
  # 将所有 .txt 中的 "old" 替换为 "new"（预览）
  ./batch-rename.sh replace old new *.txt

  # 递归重命名所有 .jpg，将空格替换为下划线
  ./batch-rename.sh -xrf replace ' ' '_' '*.jpg'

  # 用正则去掉文件名中的 "(1)" 之类后缀
  ./batch-rename.sh -x regex ' \([0-9]+\)' '' *.pdf

  # 将照片按顺序编号
  ./batch-rename.sh -x number photo *.jpg jpg

  # 替换并递归
  ./batch-rename.sh -xr replace '%20' '-' '**/*.md'
EOF
}

# === 日志函数 ===
log_info() {
    $QUIET || echo -e "${COLOR_GREEN}[INFO]${COLOR_RESET} $*"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*" >&2
}

log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $*" >&2
}

log_rename() {
    local src="$1"
    local dst="$2"
    if $DRY_RUN; then
        echo -e "  ${COLOR_CYAN}[DRY-RUN]${COLOR_RESET} $src -> $dst"
    else
        echo -e "  ${COLOR_GREEN}[OK]${COLOR_RESET} $src -> $dst"
    fi
}

# === 安全重命名函数 ===
# 参数: 源文件路径, 目标文件路径
# 返回: 0=成功, 1=跳过, 2=错误
safe_rename() {
    local src="$1"
    local dst="$2"

    # 源文件存在性检查
    if [[ ! -e "$src" ]]; then
        log_error "Source not found: $src"
        ((ERRORS++))
        return 2
    fi

    # 目标与源相同，跳过
    if [[ "$src" == "$dst" ]]; then
        $QUIET || log_warn "Skipping (same name): $src"
        ((SKIPPED++))
        return 1
    fi

    # 目标已存在且非 force 模式
    if [[ -e "$dst" && "$FORCE" != true ]]; then
        log_warn "Skipping (target exists): $dst"
        ((SKIPPED++))
        return 1
    fi

    # 目标已存在且 force 模式
    if [[ -e "$dst" && "$FORCE" == true ]]; then
        log_warn "Overwriting: $dst"
        rm -f "$dst"
    fi

    # 目标目录存在性（处理路径中包含子目录的情况）
    local dst_dir
    dst_dir="$(dirname "$dst")"
    if [[ ! -d "$dst_dir" ]]; then
        mkdir -p "$dst_dir"
    fi

    if $DRY_RUN; then
        log_rename "$src" "$dst"
        ((RENAMED++))
        return 0
    fi

    # 执行重命名
    if mv -- "$src" "$dst"; then
        log_rename "$src" "$dst"
        ((RENAMED++))
        return 0
    else
        log_error "Failed to rename: $src -> $dst"
        ((ERRORS++))
        return 2
    fi
}

# === 生成新文件名 ===
# replace 模式
do_replace() {
    local old_str="$1"
    local new_str="$2"
    local filepath="$3"

    local dirname filename newname
    dirname="$(dirname "$filepath")"
    filename="$(basename "$filepath")"

    # 仅替换文件名中的部分（不碰目录名）
    newname="${filename//$old_str/$new_str}"

    if [[ "$dirname" == "." ]]; then
        echo "$newname"
    else
        echo "$dirname/$newname"
    fi
}

# regex 模式
do_regex() {
    local pattern="$1"
    local replacement="$2"
    local filepath="$3"

    local dirname filename newname
    dirname="$(dirname "$filepath")"
    filename="$(basename "$filepath")"

    # 使用 Bash 参数展开做正则替换（Bash 4.0+ 支持 ${var/pat/repl}）
    # 注意：Bash 的参数展开不支持完整的正则语法，这里简化为 glob 模式替换
    # 真正的正则替换需要 sed
    newname="$(echo "$filename" | sed -E "s/$pattern/$replacement/g")"

    if [[ "$dirname" == "." ]]; then
        echo "$newname"
    else
        echo "$dirname/$newname"
    fi
}

# number 模式
do_number() {
    local prefix="$1"
    local ext="$2"
    local index="$3"
    local dirname="$4"

    printf "%s/%s_%03d.%s" "$dirname" "$prefix" "$index" "$ext"
}

# === 收集文件列表 ===
# 使用 glob 或 find 收集文件，返回通过标准输出
collect_files() {
    local pattern="$1"

    if $RECURSIVE; then
        shopt -s globstar nullglob dotglob 2>/dev/null || true
        # 使用 find 以更好控制
        local search_dir
        search_dir="$(dirname "$pattern")"
        local search_pat
        search_pat="$(basename "$pattern")"

        if [[ "$search_dir" == "." ]]; then
            find . -type f -name "$search_pat" -print0
        else
            find "$search_dir" -type f -name "$search_pat" -print0
        fi
    else
        shopt -s nullglob
        for f in $pattern; do
            [[ -f "$f" ]] || continue
            printf '%s\0' "$f"
        done
    fi
}

# === 模式处理入口 ===
run_replace() {
    local old_str="$1"
    local new_str="$2"
    local pattern="$3"

    log_info "Mode: replace  |  '$old_str' -> '$new_str'  |  Pattern: $pattern"
    log_info "Recursive: $RECURSIVE  |  Force: $FORCE  |  Dry-run: $DRY_RUN"
    echo ""

    while IFS= read -r -d '' filepath; do
        local newpath
        newpath="$(do_replace "$old_str" "$new_str" "$filepath")"
        safe_rename "$filepath" "$newpath"
    done < <(collect_files "$pattern")
}

run_regex() {
    local pattern_re="$1"
    local replacement="$2"
    local file_pat="$3"

    log_info "Mode: regex    |  Pattern: '$pattern_re' -> '$replacement'  |  Files: $file_pat"
    log_info "Recursive: $RECURSIVE  |  Force: $FORCE  |  Dry-run: $DRY_RUN"
    echo ""

    while IFS= read -r -d '' filepath; do
        local newpath
        newpath="$(do_regex "$pattern_re" "$replacement" "$filepath")"
        safe_rename "$filepath" "$newpath"
    done < <(collect_files "$file_pat")
}

run_number() {
    local prefix="$1"
    local file_pat="$2"
    local ext="${3:-}"

    log_info "Mode: number   |  Prefix: '$prefix'  |  Pattern: $file_pat"
    log_info "Recursive: $RECURSIVE  |  Force: $FORCE  |  Dry-run: $DRY_RUN"
    echo ""

    # 先收集文件
    local files=()
    while IFS= read -r -d '' filepath; do
        files+=("$filepath")
    done < <(collect_files "$file_pat")

    if [[ ${#files[@]} -eq 0 ]]; then
        log_warn "No files matched pattern: $file_pat"
        return
    fi

    # 排序文件列表以保证编号可预测
    local sorted=()
    while IFS= read -r -d '' line; do
        sorted+=("$line")
    done < <(printf '%s\0' "${files[@]}" | sort -z)

    local index=1
    for filepath in "${sorted[@]}"; do
        local dirname
        dirname="$(dirname "$filepath")"

        # 自动检测扩展名
        local file_ext="$ext"
        if [[ -z "$file_ext" ]]; then
            file_ext="${filepath##*.}"
            # 如果没有扩展名，用原样
            [[ "$file_ext" == "$filepath" ]] && file_ext=""
        fi

        local newpath
        if [[ -n "$file_ext" ]]; then
            newpath="$(do_number "$prefix" "$file_ext" "$index" "$dirname")"
        else
            newpath="$(printf "%s/%s_%03d" "$dirname" "$prefix" "$index")"
        fi

        safe_rename "$filepath" "$newpath"
        ((index++))
    done
}

# === 参数解析 ===
parse_args() {
    local positional=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -x|--execute)
                DRY_RUN=false
                shift
                ;;
            -r|--recursive)
                RECURSIVE=true
                shift
                ;;
            -f|--force)
                FORCE=true
                shift
                ;;
            -q|--quiet)
                QUIET=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            --)
                shift
                positional+=("$@")
                break
                ;;
            -*)
                log_error "Unknown option: $1"
                echo "Use -h for help." >&2
                exit 1
                ;;
            *)
                positional+=("$1")
                shift
                ;;
        esac
    done

    set -- "${positional[@]}"

    # 检查最小参数数量
    if [[ $# -lt 3 ]]; then
        log_error "Insufficient arguments. Use -h for help."
        exit 1
    fi

    MODE="$1"
    shift

    case "$MODE" in
        replace)
            if [[ $# -lt 3 ]]; then
                log_error "replace mode requires: OLD NEW FILE_PATTERN"
                exit 1
            fi
            run_replace "$1" "$2" "$3"
            ;;
        regex)
            if [[ $# -lt 3 ]]; then
                log_error "regex mode requires: PATTERN REPLACEMENT FILE_PATTERN"
                exit 1
            fi
            run_regex "$1" "$2" "$3"
            ;;
        number)
            if [[ $# -lt 2 ]]; then
                log_error "number mode requires: PREFIX FILE_PATTERN [EXT]"
                exit 1
            fi
            run_number "$1" "$2" "${3:-}"
            ;;
        *)
            log_error "Unknown mode: $MODE (use replace, regex, or number)"
            exit 1
            ;;
    esac
}

# === 主函数 ===
main() {
    parse_args "$@"

    # 输出摘要
    echo ""
    echo "=========================================="
    if $DRY_RUN; then
        echo -e "  ${COLOR_CYAN}DRY-RUN COMPLETE${COLOR_RESET} — use -x to execute"
    else
        echo -e "  ${COLOR_GREEN}EXECUTION COMPLETE${COLOR_RESET}"
    fi
    echo "=========================================="
    echo "  Renamed:  $RENAMED"
    echo "  Skipped:  $SKIPPED"
    echo "  Errors:   $ERRORS"
    echo "=========================================="

    if [[ $ERRORS -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
```

### 2.2 使用示例

**运行方式:**

```bash
# 1. 赋予执行权限
chmod u+x batch-rename.sh

# 2. 创建测试文件
mkdir -p /tmp/rename_test
cd /tmp/rename_test
touch "old_file_a.txt" "old_file_b.txt" "old_file_c.txt" "keep_me.log"

# 3. Dry-run 预览
./batch-rename.sh replace old_file new_file *.txt

# 4. 真正执行
./batch-rename.sh -x replace old_file new_file *.txt

# 5. 编号重命名
touch a.jpg b.jpg c.jpg
./batch-rename.sh -x number photo *.jpg jpg

# 6. 帮助信息
./batch-rename.sh -h
```

---

## 3. 代码走读

### 3.1 架构概览

```
main()
  └── parse_args()          参数解析（选项 + 模式分发）
        ├── run_replace()   替换模式
        │     └── do_replace()  生成新文件名
        │     └── collect_files() 收集文件列表
        │     └── safe_rename()   安全重命名
        ├── run_regex()     正则模式
        │     └── do_regex()
        │     └── collect_files()
        │     └── safe_rename()
        └── run_number()    编号模式
              └── do_number()
              └── collect_files()
              └── safe_rename()
```

### 3.2 关键设计决策

| 设计点 | 决策 | 原因 |
|--------|------|------|
| 默认行为 | dry-run（预览） | 安全第一，避免意外重命名 |
| 文件收集 | `find -print0` + `read -d ''` | 正确处理文件名中的空格、换行等特殊字符 |
| 错误处理 | `set -euo pipefail` + `trap ERR` | 任何意外错误立即暴露，不默默失败 |
| 重命名 | `mv --` 加双破折号 | 防止以 `-` 开头的文件名被当作选项 |
| 冲突处理 | 默认跳过，`-f` 覆盖 | 默认不丢数据，需要覆盖时明确告知 |
| 编号模式排序 | `sort -z` | 利用 NUL 分隔符排序，保证编号可预测 |
| 输出着色 | 自动检测终端 | 管道/重定向时自动关闭颜色，输出干净 |

### 3.3 safe_rename 的安全层次

`safe_rename` 是脚本的安全核心，它在真正 `mv` 之前依次检查：

1. 源文件是否存在
2. 新旧名称是否相同（避免无意义操作）
3. 目标文件是否已存在（默认跳过）
4. 目标目录是否存在（自动 `mkdir -p`）
5. `mv` 的返回值（捕获真正失败）

---

## 4. 练习

### 练习 1: 添加大小写不敏感模式
为 `batch-rename.sh` 添加一个 `lower` 模式：将所有匹配文件的文件名转为小写。要求：
- 正确处理扩展名（可选保留扩展名原样或一起转换，用选项控制）
- 处理目录名（只转换文件名，不转换目录部分）

### 练习 2: 添加日志功能
为脚本添加 `--log FILE` 选项，将每次重命名的详细信息写入日志文件，格式为：
```
[2026-06-15 10:30:00] RENAMED  old_file.txt -> new_file.txt
[2026-06-15 10:30:00] SKIPPED  existing_file.txt
[2026-06-15 10:30:01] ERROR    source not found: missing.txt
```

### 练习 3: 添加撤销功能（可选）
在 `safe_rename` 中记录每次重命名操作，然后添加 `--undo` 选项，读取记录并逆向执行重命名操作。

---

## 4.5 参考答案

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

> [!tip]- 练习 1 参考答案
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> 在 `parse_args` 的 case 分支中添加 `lower` 模式：
>
> ```bash
> # === lower 模式处理函数 ===
> run_lower() {
>     local file_pat="$1"
>     local keep_ext="${2:-yes}"
>
>     log_info "Mode: lower    |  Pattern: $file_pat  |  Keep extension: $keep_ext"
>     echo ""
>
>     while IFS= read -r -d '' filepath; do
>         local dirname filename base ext newname
>         dirname="$(dirname "$filepath")"
>         filename="$(basename "$filepath")"
>
>         if [[ "$keep_ext" == "yes" && "$filename" == *.* ]]; then
>             ext=".${filename##*.}"
>             base="${filename%.*}"
>             newname="${base,,}${ext}"
>         else
>             newname="${filename,,}"
>         fi
>
>         if [[ "$dirname" == "." ]]; then
>             safe_rename "$filepath" "$newname"
>         else
>             safe_rename "$filepath" "$dirname/$newname"
>         fi
>     done < <(collect_files "$file_pat")
> }
> ```
>
> 然后在 `parse_args` 中的 `case "$MODE"` 分支添加：
>
> ```bash
> lower)
>     run_lower "$1" "${2:-yes}"
>     ;;
> ```
>
> 并在帮助信息中添加：
>
> ```
>   lower   [KEEP_EXT]   将文件名转为小写。KEEP_EXT=yes 保留扩展名大小写
> ```

> [!tip]- 练习 2 参考答案
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> 修改全局变量区：
>
> ```bash
> LOG_FILE=""
> ```
>
> 修改 `safe_rename` 函数，在关键分支添加日志：
>
> ```bash
> safe_rename() {
>     local src="$1"
>     local dst="$2"
>     local timestamp
>     timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
>
>     # ... 原有检查代码 ...
>
>     # 在每个分支中添加日志记录
>     if [[ "$src" == "$dst" ]]; then
>         [[ -n "$LOG_FILE" ]] && echo "[$timestamp] SKIPPED  (same name) $src" >> "$LOG_FILE"
>         # ... rest ...
>     fi
> }
> ```
>
> 添加 `--log` 选项解析：
>
> ```bash
> --log)
>     LOG_FILE="$2"
>     shift 2
>     ;;
> --log=*)
>     LOG_FILE="${1#*=}"
>     shift
>     ;;
> ```
>
> 完整实现需要在整个 `safe_rename` 的每个 `return` 前记录相应日志。

> [!tip]- 练习 3 参考答案（可选）
> 如果你的实现通过了测试或达到了题目要求，就是正确的。
>
> 添加撤销日志路径和记录函数：
>
> ```bash
> UNDO_LOG=""
>
> record_undo() {
>     local src="$1"
>     local dst="$2"
>     [[ -n "$UNDO_LOG" ]] && echo "$dst"$'\t'"$src" >> "$UNDO_LOG"
> }
> ```
>
> 在 `safe_rename` 中成功后调用 `record_undo "$src" "$dst"`。
>
> `--undo` 选项的 `run_undo` 函数：
>
> ```bash
> run_undo() {
>     local undo_file="$1"
>     if [[ ! -f "$undo_file" ]]; then
>         log_error "Undo file not found: $undo_file"
>         exit 1
>     fi
>     local count=0
>     # 反向读取（tac 将文件行反转）
>     while IFS=$'\t' read -r dst src; do
>         if [[ -e "$dst" ]]; then
>             mv -- "$dst" "$src"
>             echo "UNDONE: $dst -> $src"
>             ((count++))
>         else
>             log_warn "Cannot undo (file missing): $dst"
>         fi
>     done < <(tac "$undo_file")
>     echo "Undone $count operations."
> }
> ```
>
> 选项添加 `--undo-file FILE` 在重命名时记录，`--undo FILE` 执行撤销。

---

## 5. 扩展阅读

- [Bash Reference Manual](https://www.gnu.org/software/bash/manual/)
- [Greg's Wiki: Bash FAQ](https://mywiki.wooledge.org/BashFAQ)
- [Bash Hackers Wiki](https://wiki.bash-hackers.org/)
- [rename 命令 (util-linux)](https://man7.org/linux/man-pages/man1/rename.1.html) — Linux 自带的批量重命名工具
- [mmv — 另一种批量重命名工具](https://github.com/rrthomas/mmv)

---

## 常见陷阱

- **忘记 `--` 分隔符**：`mv "$src" "$dst"` 在文件名以 `-` 开头时会被当作选项。始终使用 `mv -- "$src" "$dst"`。
- **`find -name` 的引号**：`find . -name $pattern` 中的 `$pattern` 如果含通配符且未加引号，会被 shell 提前展开。始终写为 `find . -name "$pattern"`。
- **Dry-run 与递归组合**：`collect_files` 中的 `globstar` 在 dry-run 下的行为与实际执行一致，但记得在 `set -euo` 下使用 `shopt -s nullglob`。
- **编号模式的零填充宽度**：如果文件数超过 999，`%03d` 会导致编号溢出。可以在收集完成后根据文件数量动态决定宽度。
- **正则模式中的特殊字符**：`sed -E` 中的 `&` 是特殊字符（代表整个匹配），如果用户在替换字符串中使用了 `&`，需要先转义。
- **`mv` 跨文件系统**：`mv` 在同一文件系统内是 rename（原子操作），跨文件系统则是 copy + delete（非原子且慢）。如需跨 FS 重命名，考虑在提示中说明。
