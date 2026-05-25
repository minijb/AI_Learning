---
name: rich-output
description: >
  使用 Rich 库美化 Python 终端输出 — 彩色文本、表格、进度条、Markdown 渲染、语法高亮、
  Panel/Layout、Tree、Traceback 美化等。当用户要求"美化输出"、"让终端输出更好看"、
  "加个进度条"、"用表格展示数据"、"高亮代码"、"美化日志"、"做个好看的 CLI 界面"时触发。
  即使没有明确提到 Rich 库名，只要涉及终端输出美化就应该使用此 skill。
compatibility: Python 3.8+, `pip install rich`
---

# Rich Output — Python 终端输出美化

> 用 Rich 替代裸 `print()`，让终端输出可读、可维护、甚至让人觉得"好看"。

---

## 核心定位

Rich 是一个"终端渲染引擎"——它不只是一个美化库，而是提供了一整套**可渲染对象（Renderable）**生态。理解这个模型比记忆 API 更重要：

- 一切可渲染对象都可以传给 `console.print()` 或 `rich.print()`
- 渲染结果是终端 ANSI 转义序列，Rich 自动处理宽度自适应、颜色降级、交互式检测
- 你需要做的只是**构造正确的 Renderable**，Rich 负责把它变成漂亮的终端输出

---

## 快速决策：该用什么 API

| 场景 | 方案 | 何时用 |
|------|------|--------|
| 替换 `print()` | `from rich import print` | 大部分情况，一行改完 |
| 精细控制输出 | `Console().print()` | 需要设置宽度、颜色系统、文件输出 |
| 调试变量 | `from rich import print` + `locals()` | 一行调试 |
| 调试对象详情 | `from rich import inspect` | 看类/实例/内置对象的内部 |
| 日志输出 | `Console().log()` | 自动加时间+调用位置 |
| 美化异常 | `from rich.traceback import install; install()` | 全局替换 traceback |
| 美化 REPL | `from rich import pretty; pretty.install()` | 交互式探索数据 |

---

## 核心 API 速查

### 1. 彩色文本和样式

Rich 的文本样式通过 **Console Markup** 实现，语法类似 BBCode：

```python
from rich import print

# 基础样式
print("[bold red]错误:[/bold red] 文件未找到")
print("[bold]粗体[/bold] [italic]斜体[/italic] [underline]下划线[/underline]")
print("[red on white]红字白底[/red on white]")

# 16M 真彩色
print("[#ff6600]自定义橙色文字[/#ff6600]")
print("[rgb(255,100,0)]RGB 橙色[/rgb(255,100,0)]")

# 样式链接（用空格分隔多种样式）
print("[bold italic underline red]重要通知！[/bold italic underline red]")
```

**内置颜色常量**：`red`, `green`, `blue`, `yellow`, `magenta`, `cyan`, `white`, `black`, `bright_*`（如 `bright_red`），以及 `grey0` 到 `grey100` 的灰度。

文本中显示 `[` 或 `]` 时用 `\[` 和 `\]` 转义，或在 `Console()` 构造时设置 `markup=False` 禁用 markup。

### 2. 表格（Table）

表格用于结构化数据展示，支持标题、列对齐、边框样式：

```python
from rich.table import Table
from rich.console import Console

console = Console()
table = Table(title="用户列表", show_header=True, header_style="bold magenta")

table.add_column("ID", style="dim", width=6)
table.add_column("姓名", min_width=12)
table.add_column("邮箱", justify="right")
table.add_column("状态")

table.add_row("1", "张三", "zhang@example.com", "[green]活跃[/green]")
table.add_row("2", "李四", "li@example.com", "[red]禁用[/red]")

console.print(table)
```

**常用 Table 参数**：`show_lines=True`（行间分隔线）、`row_styles=["none", "dim"]`（斑马纹）、`box=box.SIMPLE`（简洁边框）、`expand=True`（撑满终端）。

### 3. 进度条（Progress）

```python
import time
from rich.progress import Progress

with Progress() as progress:
    task = progress.add_task("[cyan]处理中...", total=100)
    while not progress.finished:
        time.sleep(0.02)
        progress.update(task, advance=1)
```

多任务并发、自定义列、文件下载进度等高级模式见 [Rich Progress 文档](https://rich.readthedocs.io/en/stable/progress.html)。

### 4. 面板和布局

```python
from rich.panel import Panel
from rich.columns import Columns

# Panel — 给内容加边框
console.print(Panel("这是重要信息", title="提示", border_style="green"))

# Columns — 多列并排
console.print(Columns([
    Panel("列 1 内容"),
    Panel("列 2 内容"),
    Panel("列 3 内容"),
]))
```

`Panel` 支持 `expand=False`（内容宽度自适应）、`padding` 内边距、`subtitle` 副标题。

### 5. Markdown 渲染

```python
from rich.markdown import Markdown

markdown = """
# 标题
- 列表项 1
- 列表项 2

```python
print("hello")
```
"""
console.print(Markdown(markdown))
```

### 6. 语法高亮

```python
from rich.syntax import Syntax

code = '''def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"
'''
console.print(Syntax(code, "python", theme="monokai", line_numbers=True))
```

### 7. 树形结构

```python
from rich.tree import Tree

tree = Tree("项目根目录")
src = tree.add("src")
src.add("main.py")
src.add("utils.py")
tests = tree.add("tests")
tests.add("test_main.py")
console.print(tree)
```

### 8. Console.log — 带上下文的调试日志

```python
console.log("用户登录", user="admin", ip="192.168.1.1")
# 输出自动包含时间戳、调用位置、变量表格
```

### 9. 美化异常 Traceback

```python
from rich.traceback import install
install(show_locals=True)  # 全局生效，一行搞定
```

可以在 `install()` 中设置 `width`、`theme`、`word_wrap` 等参数。

---

## 最佳实践

### 何时用 `rich.print` vs `Console().print`

- **`rich.print`**：快速替换内置 `print`，90% 场景够用
- **`Console().print`**：需要自定义输出目标（文件/stderr）、终端宽度、颜色系统时使用
- 一个脚本中创建一次 `Console()` 实例并复用，避免重复构造

### 样式标记的性能

Console Markup 解析有开销。对于纯文本的大量输出（如日志流），构造 `Console(markup=False)` 可以跳过解析。

### 输出目标不是终端时

当 stdout 被重定向到文件或管道时，Rich 会自动去除颜色代码。如果需要强制保留（如输出到 CI 日志），设置 `force_terminal=True`：

```python
console = Console(force_terminal=True)
```

### 自定义 Theme

通过 `Theme` 类定义自定义样式名，避免每次都写颜色代码：

```python
from rich.theme import Theme
from rich.console import Console

custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "danger": "bold red",
})
console = Console(theme=custom_theme)
console.print("[info]这是一条消息[/info]")
console.print("[danger]这是一条警告[/danger]")
```

---

## 进阶能力（按需深入）

Rich 的能力不止于此。以下功能不在此文档展开，当需要时查阅官方文档：

| 功能 | 用途 | 文档链接 |
|------|------|---------|
| **Live Display** | 动态更新的终端区域（替代进度条） | `rich.live.Live` |
| **Layout** | 终端区域分割（上下、左右） | `rich.layout.Layout` |
| **Prompt** | 终端交互输入 | `rich.prompt.Prompt` |
| **Status** | 带旋转图标的临时状态 | `rich.status.Status` |
| **JSON** | JSON 美化输出 | `rich.json` |
| **Rule** | 水平分割线 | `rich.rule.Rule` |
| **Emoji** | 跨平台 emoji 支持 | 直接在 markup 中使用 `:smile:` |
| **自定义 Renderable** | 实现 `__rich_console__` 协议 | 创建自己的可渲染对象 |

查阅完整 API：[Rich 官方文档](https://rich.readthedocs.io/en/stable/)

---

## 护栏规则

1. **安装检查** — 在生成代码前，提醒用户 `pip install rich`（如尚未安装）
2. **单 Console 实例** — 每个脚本只创建一个 `Console()` 实例，避免重复初始化
3. **Markup 转义** — 用户数据中包含 `[` `]` 时，用 `escape()` 函数或 `markup=False` 处理，防止误解析
4. **不要过度美化** — 数据管道、纯文本日志等场景下，保留纯文本输出即可。美化的目的是提升人类可读性
5. **Python 版本** — Rich 要求 Python 3.8+，注意兼容性
6. **文档规范** — 生成的 Python 代码中的文档字符串、注释和输出的 Markdown 文件遵循 `.omp/skills/markdown/SKILL.md`
