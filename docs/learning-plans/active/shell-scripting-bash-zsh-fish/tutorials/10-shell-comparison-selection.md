---
title: Bash / Zsh / Fish 对比与选型
updated: 2026-06-15
---

# Bash / Zsh / Fish 对比与选型

> 所属计划: Shell 脚本编程：Bash、Zsh 与 Fish
> 预计耗时: 45min
> 前置知识: 全部前 9 节

---

## 1. 概念讲解

### 为什么要学"选型"？

你已经学完了 Bash、Zsh 和 Fish 三个 Shell 的脚本语法。但实际工作中，你不会同时用它们——你需要根据场景做**选择**。

选错 Shell 的代价：
- 在只有 Bash 的 Docker 镜像里写 Fish 脚本 → 根本跑不起来
- 用 Bash 写 macOS 上的交互配置 → 错过 Zsh 的良好补全和插件生态
- 把 Bash 脚本部署到团队环境却用了 `[[ ]]` → 在 `dash`/`sh` 上崩溃
- 用 Fish 写团队 CI 脚本 → 其他成员的环境没有 Fish，必须额外安装

这一节帮你建立选型的思维模型：理解三者的定位差异，掌握选型决策树，知道在什么时候该选什么。

### 三种 Shell 的定位

#### Bash：通用脚本引擎

Bash 是 Linux 世界的**事实标准**。它的核心优势是**无处不在**：

- 每一台 Linux 发行版都预装 Bash
- 几乎所有 CI/CD 系统默认使用 Bash
- Docker 镜像的 `RUN` 指令默认用 `/bin/sh`（通常指向 Bash 或 dash）
- 绝大多数 shell 教程和 Stack Overflow 答案用 Bash 语法

Bash 的定位是"写一次，到处运行"的脚本语言。它是胶水语言中的胶水语言。

#### Zsh：交互体验优先

Zsh 在脚本兼容 Bash 的基础上，大幅提升了**交互式使用体验**：

- macOS 的默认 shell（Catalina 10.15+）
- Oh My Zsh 拥有 2000+ 插件和 150+ 主题
- 内置拼写纠正、路径替换、自动补全强化
- 脚本可以合法使用 Bash 语法，同时可选地使用 Zsh 扩展

Zsh 的定位是"日常使用的终端环境"。它的脚本能力是加分项，但**主要价值在交互侧**。

#### Fish：重新设计，告别历史

Fish 放弃了 POSIX 兼容性，从零设计了更现代的 shell 语言：

- 开箱即用的语法高亮、自动建议、Tab 补全
- 零配置即可获得良好的交互体验
- 脚本语法更一致、更安全（变量永不分词）
- 社区较小，但在 macOS 和 Linux 开发者中稳步增长

Fish 的定位是"新手的第一个 shell"和"追求现代感的老手的日常环境"。它的脚本语法自成体系，不能与他人共享。

---

## 2. 详细对比

### 兼容性对比

| 维度 | Bash | Zsh | Fish |
|------|------|-----|------|
| POSIX 兼容 | 完全（POSIX 模式） | 大部分（非 POSIX 模式） | **否** |
| 能运行 Bash 脚本 | ✅ | ✅（95%+） | **❌** |
| 能运行 POSIX sh 脚本 | ✅ | ✅ | **❌** |
| Shebang 惯例 | `#!/bin/bash` | `#!/usr/bin/env zsh` | `#!/usr/bin/env fish` |
| 默认安装位置 | 所有 Linux | macOS、需安装 | 需安装 |

> [!warning] 关于"Zsh 兼容 Bash"
> Zsh 能运行**绝大多数** Bash 脚本，但不是 100%。差异主要出现在：数组索引（0 vs 1）、未设置变量时的分词行为、某些 `shopt` 选项的行为。生产级脚本如果目标是 Zsh，建议将 Shebang 写为 `#!/usr/bin/env zsh` 并在 Zsh 下测试，而不是假设 Bash 兼容。

### 交互体验对比

| 特性 | Bash | Zsh | Fish |
|------|------|-----|------|
| 语法高亮 | 需配置 | 需插件 | **开箱即用** |
| 自动建议（基于历史） | 无 | 需插件 | **开箱即用** |
| Tab 补全 | 基本 | 强大（可编程） | 强大（带描述） |
| 拼写纠正 | 无 | 内置 `CORRECT` | **开箱即用** |
| 右提示符 | 无 | `RPROMPT` | `fish_right_prompt` |
| 多行编辑 | 基本 | 基本 | 优秀 |
| 插件生态 | 少 | **极丰富**（Oh My Zsh） | 增长中（Fisher） |
| 主题/美化 | bash-it | **Oh My Zsh** | tide/pure |
| 零配置即用 | 否 | 否 | **是** |
| 配置文件 | `.bashrc` | `.zshrc` | `config.fish` |

### 脚本语法对比

| 语法要素 | Bash | Zsh | Fish |
|----------|------|-----|------|
| 变量赋值 | `var=val` | `var=val` | `set var val` |
| 变量引用 | `"$var"`（必须引号） | `"$var"`（推荐引号） | `$var`（永不分词） |
| 变量类型 | 字符串 | 字符串/整数/浮点/数组 | 列表 |
| 数组 | 索引数组（0-based） | 索引+关联（1-based） | 列表（1-based） |
| 条件测试 | `[ ]` 或 `[[ ]]` | `[ ]` 或 `[[ ]]` | `test` 命令 |
| `if` 语法 | `if … then … fi` | `if … then … fi` | `if … end` |
| 循环语法 | `for … do … done` | `for … do … done` | `for … end` |
| 函数定义 | `f() { … }` | `f() { … }` | `function f … end` |
| 命令替换 | `$(cmd)` 或 `` `cmd` `` | `$(cmd)` | `(cmd)` |
| 算术运算 | `$((1+2))` | `$((1+2))` 含浮点 | `math "1+2"` |
| 退出码 | `$?` | `$?` | `$status` |
| 历史展开 | `!!` `!$` `!123` | `!!` `!$` `!123` | 不支持 |
| 通配符 | 基本 glob | 扩展 glob + 限定符 | 基本 glob |
| 字符串处理 | `${var#pat}` 等 | `${var#pat}` 等 | `string` 子命令 |

### 适用场景对比

| 场景 | 推荐 | 说明 |
|------|------|------|
| CI/CD 脚本（GitHub Actions, GitLab CI） | **Bash** | 默认环境，无需额外安装 |
| Docker `RUN` 脚本 | **Bash**（或 POSIX sh） | 镜像大小敏感，不装额外 shell |
| Linux 服务器管理 | **Bash** | 系统脚本默认用 Bash |
| 可移植脚本（分发他人） | **Bash** | 收件人一定有 Bash |
| macOS 日常终端 | **Zsh** | 系统默认，生态最佳 |
| 个人开发环境（Linux） | Zsh 或 Fish | 看个人偏好 |
| 交互式数据分析/探索 | **Fish** | 自动建议极大减少输入 |
| 团队共享的 shell 配置 | **Zsh**（Oh My Zsh） | 插件生态丰富，团队可共用主题 |
| 新手学习命令行的第一个 shell | **Fish** | 零配置，友好的错误提示 |
| 高性能脚本（大量循环/IO） | Bash 或 Zsh | Fish 函数调用有额外开销 |
| macOS 应用开发脚本 | **Zsh** | 与系统工具链集成最好 |
| 嵌入式 Linux / BusyBox | **POSIX sh** | 最小占用，不用 Bash/Zsh/Fish |

---

## 3. 选型决策树

下面是一个实际可用的选型流程。按顺序回答每个问题，走到叶子节点就得到结论。

```text
开始
│
├─ 脚本需要分发给不特定的人运行？
│  ├─ 是 → 目标用户一定都安装了 Zsh/Fish？
│  │  ├─ 是 → 可以用 Zsh/Fish
│  │  └─ 否 → 【选择 Bash】—— 可移植性第一
│  │
│  └─ 否 → 运行环境是你的个人/团队控制的环境？
│     │
│     ├─ 是个人本地使用，主要做交互操作？
│     │  ├─ 是 → 你愿意花时间配置吗？
│     │  │  ├─ 是 → 你是 macOS 用户？
│     │  │  │  ├─ 是 → 【选择 Zsh】—— macOS 默认，Oh My Zsh 体验最佳
│     │  │  │  └─ 否 → 两选：Zsh（生态）或 Fish（开箱即用）
│     │  │  └─ 否 → 【选择 Fish】—— 零配置即用，对新手友好
│     │  │
│     │  └─ 否 → 是团队环境？
│     │     │
│     │     ├─ 是 CI/CD 或 Docker？
│     │     │  └─ 【选择 Bash】—— 所有 CI 系统和 Docker 镜像都有 Bash
│     │     │
│     │     ├─ 是运行在只有 Bash 的服务器上？
│     │     │  └─ 【选择 Bash】—— 没有选择余地
│     │     │
│     │     └─ 是团队内部工具脚本（所有成员环境可以统一）？
│     │        ├─ 复杂度高，需要丰富语法？
│     │        │  └─ 【选择 Zsh】—— Bash 超集，表达力更强
│     │        └─ 复杂度低，追求可维护性？
│     │           └─ 【选择 Bash】—— 团队新成员上手成本最低
│     │
│     └─ 是性能敏感场景？
│        └─ 【选择 Bash】—— Fish 函数调用开销较大，Zsh 与 Bash 接近
```

### 简化版：一句话选型

| 你的情况 | 一句话建议 |
|----------|-----------|
| "我写脚本给别人用" | 用 **Bash**。可移植性压倒一切。 |
| "我用 macOS 做开发" | 交互用 **Zsh**，脚本用 **Bash**。 |
| "我刚开始学命令行" | 用 **Fish** 作为交互 shell。学 Bash 作为脚本语言。 |
| "我的 Docker/CI 脚本报错了" | 检查是否用了 Bash-only 语法。目标环境可能是 `dash`。 |
| "我要写一个复杂的构建脚本" | 考虑用 Python/Makefile 替代 shell 脚本。当 shell 脚本超过 200 行，维护成本急剧上升。 |

---

## 4. 代码示例：兼容性检测脚本

> **运行环境要求**：Bash 3.0+（所有平台都有）。

### 示例 1：检测当前 Shell 环境

```bash
#!/usr/bin/env bash
# detect-shell.sh — 检测当前运行的 Shell 并提供信息

detect_shell() {
    local shell_name="${SHELL##*/}"

    echo "=== Shell Environment Detection ==="
    echo ""

    # 当前 Shell 可执行文件
    echo "SHELL variable:  $SHELL"

    # 通过进程名检测
    local parent_shell
    parent_shell="$(ps -o comm= -p $PPID 2>/dev/null || echo 'unknown')"
    echo "Parent process:  $parent_shell"

    # 检测 capabilities
    echo ""
    echo "--- Capabilities ---"

    # 检查是否支持 [[ ]]
    if type [[ >/dev/null 2>&1 || eval '[[ "a" == "a" ]]' 2>/dev/null; then
        echo "[[ ]]:           supported"
    else
        echo "[[ ]]:           NOT supported (POSIX sh or dash)"
    fi

    # 检查是否支持数组
    if eval 'arr=(a b c)' 2>/dev/null; then
        echo "arrays:          supported"
    else
        echo "arrays:          NOT supported"
    fi

    # 检查 $BASH_VERSION
    if [[ -n "$BASH_VERSION" ]]; then
        echo "BASH_VERSION:    $BASH_VERSION"
        echo "=> You are running BASH"
    fi

    # 检查 $ZSH_VERSION
    if [[ -n "$ZSH_VERSION" ]]; then
        echo "ZSH_VERSION:     $ZSH_VERSION"
        echo "=> You are running ZSH"
    fi

    # 检查 FISH_VERSION
    if [[ -n "$FISH_VERSION" ]]; then
        echo "FISH_VERSION:    $FISH_VERSION"
        echo "=> You are running FISH"
    fi

    # POSIX 特征检测
    if [[ -z "$BASH_VERSION" && -z "$ZSH_VERSION" && -z "$FISH_VERSION" ]]; then
        echo "=> Likely a POSIX-only shell (dash, ash, sh)"
        echo "   Use POSIX-compatible syntax only."
    fi

    echo ""
    echo "--- Recommendation ---"
    if [[ -n "$BASH_VERSION" ]]; then
        echo "Full Bash scripting is safe here."
    elif [[ -n "$ZSH_VERSION" ]]; then
        echo "Bash-compatible syntax works. Zsh extensions available."
    else
        echo "Use POSIX-compatible syntax only (#!/bin/sh)."
    fi
}

detect_shell
```

### 示例 2：可移植性包装器

当必须支持多种 shell 时，可以把核心逻辑写在 POSIX sh 中，并用 wrapper 做环境适配：

```bash
#!/usr/bin/env sh
# portable-runner.sh — 在所有 POSIX shell 上运行的脚本

set -eu

main() {
    echo "This script runs on any POSIX shell"
    echo "Shell: ${SHELL:-unknown}"

    # 只在检测到 Bash 时使用 Bash 特性
    if [ -n "${BASH_VERSION:-}" ]; then
        echo "Bash extensions available: $BASH_VERSION"
        # 此处可以用 [[ ]]
        if [[ -d "/etc" ]]; then
            echo "/etc is a directory (detected via Bash [[ ]])"
        fi
    fi

    # 只在检测到 Zsh 时使用 Zsh 特性
    if [ -n "${ZSH_VERSION:-}" ]; then
        echo "Zsh extensions available: $ZSH_VERSION"
        # 此处可以用 Zsh 扩展通配符
    fi
}

main "$@"
```

---

## 5. 练习

### 练习 1：场景选型

阅读以下场景，给出你的 shell 选型建议，并说明理由：

1. 你在 GitHub Actions 中需要一个脚本来自动发布 npm 包。
2. 你是一名 macOS 上做 iOS 开发的工程师，每天大量时间在终端中操作 git、运行 xcodebuild。
3. 你在给一个开源项目贡献代码，项目需要提供一个安装脚本供用户下载后运行（用户的系统包括 Linux、macOS、WSL）。
4. 你在公司内部搭建了一个开发环境自动化脚本，所有开发者的机器由 IT 统一配置，都安装了 Zsh 5.8+ 和 Bash 5.1+。
5. 你刚开始学习命令行，听到过 `rm -rf /` 的危险，希望有一个更友好的环境来减少犯错。

### 练习 2：编写环境适配脚本

编写一个 Bash 脚本 `safe-cleanup.sh`，功能如下：
1. 检测当前运行的 Shell 类型
2. 如果是 Bash：使用 `[[ ]]` 和数组
3. 如果是 Zsh：额外使用关联数组和 `typeset`
4. 如果是其他（dash/sh）：仅用 POSIX 语法 `[ ]`
5. 脚本功能：清理指定目录下超过 30 天未修改的临时文件（`.tmp`、`.log` 文件），打印清理前后的文件数量和释放的空间。

### 练习 3：迁移计划（可选）

假设你目前使用 Bash 作为交互 shell，现在想迁移到 Fish。写一份迁移计划，列出：
1. `.bashrc` 中有哪些配置需要在 `config.fish` 中重写（至少列 5 类）
2. 哪些工作流可以简化
3. 哪些工作流必须保留 Bash（例如运行历史 Bash 脚本）

---

## 5.5 参考答案

> [!tip]- 练习 1 参考答案
> **场景 1：GitHub Actions 自动发布 npm 包**
> → **选择 Bash**。GitHub Actions 的 `ubuntu-latest` runner 默认 shell 是 Bash。直接在 workflow 中写 Bash 脚本或调用 `.sh` 文件。Zsh/Fish 需要 `apt install`，增加 CI 时间和复杂度。
>
> **场景 2：macOS iOS 开发**
> → **交互 shell 选 Zsh**。macOS 默认 Zsh，Oh My Zsh 有 `xcode` 插件提供快捷别名（如 `xcb` 打开 Xcode），`git` 插件提供简洁 prompt。脚本可以继续用 Bash 编写（兼容性）。
>
> **场景 3：开源项目安装脚本**
> → **选择 Bash（或 POSIX sh）**。不能假设用户安装了 Zsh 或 Fish。Shebang 用 `#!/usr/bin/env bash` 或 `#!/bin/sh`（POSIX 模式）。`curl … | bash` 是最低门槛的分发方式。
>
> **场景 4：内部自动化（统一环境）**
> → **可以选择 Zsh**。所有开发者都安装了 Zsh，利用关联数组、扩展通配符、`typeset` 等特性可以让脚本更安全、更简洁。但要注意：未来如果有新人加入或 CI 集成，需要确保环境一致。
>
> **场景 5：新手学习命令行**
> → **交互 shell 选 Fish**。零配置即可获得语法高亮、自动建议、友好的错误提示。同时学习 Bash 作为脚本语言（因在线教程和 Stack Overflow 答案多为 Bash）。

> [!tip]- 练习 2 参考答案
> ```bash
> #!/usr/bin/env bash
> # safe-cleanup.sh — 环境适配的临时文件清理脚本
>
> set -euo pipefail
>
> TARGET_DIR="${1:-.}"
> DAYS="${2:-30}"
> EXTENSIONS=("tmp" "log" "temp" "swp")
>
> if [[ ! -d "$TARGET_DIR" ]]; then
>     echo "ERROR: '$TARGET_DIR' is not a directory" >&2
>     exit 1
> fi
>
> echo "=== Cleanup: $TARGET_DIR (older than $DAYS days) ==="
> echo "Running on:"
>
> # 检测 Shell 类型
> if [[ -n "${ZSH_VERSION:-}" ]]; then
>     echo "  Shell: Zsh $ZSH_VERSION"
>     echo "  Using: Zsh extensions (typeset, extended glob)"
>
>     typeset -A ext_map
>     ext_map=(tmp 1 log 1 temp 1 swp 1)
>
>     # Zsh 扩展通配符
>     for ext in ${(k)ext_map}; do
>         local pattern="*.$ext(.m+$DAYS)"
>         # 收集匹配文件
>         local files=($TARGET_DIR/$~pattern(N))
>         if (( ${#files} > 0 )); then
>             echo "  Removing ${#files} .$ext files..."
>             rm -f $files
>         fi
>     done
>
> elif [[ -n "${BASH_VERSION:-}" ]]; then
>     echo "  Shell: Bash $BASH_VERSION"
>     echo "  Using: Bash [[ ]] and arrays"
>
>     for ext in "${EXTENSIONS[@]}"; do
>         # Bash 方式收集文件
>         local count=0
>         while IFS= read -r -d '' file; do
>             rm -f "$file"
>             ((count++))
>         done < <(find "$TARGET_DIR" -maxdepth 1 -name "*.$ext" -mtime +"$DAYS" -print0 2>/dev/null)
>         if (( count > 0 )); then
>             echo "  Removed $count .$ext files"
>         fi
>     done
>
> else
>     echo "  Shell: Generic POSIX"
>     echo "  Using: POSIX [ ] only"
>
>     for ext in "${EXTENSIONS[@]}"; do
>         count=0
>         # POSIX find + while read
>         find "$TARGET_DIR" -maxdepth 1 -name "*.$ext" -mtime +"$DAYS" -print 2>/dev/null \
>         | while IFS= read -r file; do
>             rm -f "$file"
>             count=$((count + 1))
>         done
>         if [ "$count" -gt 0 ]; then
>             echo "  Removed $count .$ext files"
>         fi
>     done
> fi
>
> echo "Done."
> ```
>
> **说明**：`-print0` / `read -d ''` 组合确保正确处理包含空格和换行的文件名。POSIX 分支使用 `find -print` 和普通 `read`，在极端文件名场景下不够安全，但保持了最大兼容性。

> [!tip]- 练习 3 参考答案
> **迁移计划：Bash → Fish**
>
> **1. `.bashrc` 配置迁移清单：**
>
> | Bash (`.bashrc`) | Fish (`config.fish`) |
> |---|---|
> | `export PATH="$HOME/bin:$PATH"` | `fish_add_path $HOME/bin` 或 `set -x PATH $HOME/bin $PATH` |
> | `export EDITOR=vim` | `set -x EDITOR vim` |
> | `alias ll='ls -lah'` | `alias ll='ls -lah'` 或 `abbr -a ll 'ls -lah'`（缩写） |
> | `export PS1='\u@\h:\w\$ '` | `function fish_prompt … end`（完全自定义函数） |
> | `source ~/.bash_aliases` | Fish 不能 source Bash 文件，需将别名重写为 Fish 的 `alias`/`abbr` |
> | `eval "$(pyenv init -)"` | `pyenv init - \| source`（Fish 的 `source` 可以接受管道） |
> | `shopt -s globstar` | Fish 默认不递归通配，用 `**` 需 `set -g fish_globstar 1` |
> | `set -o vi` | `fish_vi_key_bindings` |
>
> **2. 可以简化的工作流：**
> - Tab 补全不需要 `bash-completion` 包，Fish 从 man page 自动解析
> - 历史搜索不需要 `Ctrl+R` 配置，Fish 内置提示建议
> - Git 分支显示不需要额外 prompt 脚本，Fish 内置支持
> - 拼写纠正开箱即用（如 `gti` → `git`）
>
> **3. 必须保留 Bash 的场景：**
> - 运行任何现有的 `.sh` 脚本：在终端直接 `bash script.sh` 运行
> - `ssh` 到远程服务器后的环境：远程服务器可能没有 Fish，习惯 Bash 操作
> - Docker `RUN` 指令和 CI/CD 脚本：永远用 `#!/bin/bash`
> - `sudo` 执行的脚本：默认仍为 Bash
> - 团队共享的脚本：保持 Bash 以供他人使用

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 6. 扩展阅读

- [Bash vs Zsh vs Fish — 社区对比讨论](https://www.reddit.com/r/linux/comments/10qz0p7/bash_vs_zsh_vs_fish_what_do_you_use_and_why/)
- [Why Fish? — fishshell.com 官方设计理念](https://fishshell.com/docs/current/design.html)
- [Shell 兼容性表 — Hyperpolyglot](https://hyperpolyglot.org/unix-shells)
- [Oh My Zsh 官方文档](https://github.com/ohmyzsh/ohmyzsh/wiki)
- [Fisher — Fish 插件管理器](https://github.com/jorgebucaran/fisher)
- [Unix Shell 简史](https://developer.ibm.com/tutorials/l-linux-shells/)
- [Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html) — Bash 编码规范参考
- [Writing Robust Bash Shell Scripts](https://www.davidpashley.com/articles/writing-robust-shell-scripts/) — 鲁棒性指南

---

## 常见陷阱

- **"我全都要"的陷阱**：试图在同一个脚本中同时支持 Bash/Zsh/Fish 三种语法几乎不可能。Fish 的语法与其他两者完全不兼容。正确的做法是：为每种 Shell 写独立的脚本，或选择一个通用的最低公分母（Bash）。不要用 `eval` 或 `case $SHELL` 的方式在单一脚本中分支不同语法——这会使代码无法维护和理解。
- **以为 Fish 是 Bash 的替代**：Fish 是 Bash 的**替代品**（对于交互式使用），但不是 Bash 的**兼容品**。你永远不能在 Fish 中运行 `bash script.sh` 以外的 Bash 语法。`curl … | bash` 式的安装脚本在 Fish 中不工作。
- **Oh My Zsh 不等于 Zsh**：Oh My Zsh 是 Zsh 的配置框架，增加了大量插件和主题，但它**不是** Zsh 的一部分。在脚本中不能假设 Oh My Zsh 的功能可用——脚本的环境是干净的 Zsh，不会加载 `.zshrc` 或 Oh My Zsh。脚本应当自包含。
- **Docker 默认 shell 不是 Bash**：Alpine Linux 的 `/bin/sh` 是 BusyBox ash，不是 Bash。Ubuntu 的 `/bin/sh` 是 dash。如果你的 `#!/bin/sh` 脚本使用了 `[[ ]]` 或数组，会在这些环境中崩溃。解决：Shebang 明确写 `#!/bin/bash` 或 `#!/usr/bin/env bash`，避免写 `#!/bin/sh`。
- **交互配置与脚本混淆**：像 `set -x`（Fish）、`setopt`（Zsh）、`shopt`（Bash）等交互式配置选项，不应该出现在可分发脚本中。它们改变 shell 的运行时行为，可能破坏用户的期望。脚本中只使用影响脚本执行的设置（如 `set -euo pipefail`）。
- **CI 环境中的 PATH 假设**：GitHub Actions 的 macOS runner 有 Zsh，但 `$PATH` 可能不包含 `/usr/local/bin/fish`。如果你的脚本依赖 Fish，需要在 workflow 中显式 `brew install fish` 并设置正确路径。
