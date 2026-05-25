---
name: textual-output
description: >
  使用 Textual 框架构建 Python 终端 UI 应用 — 交互式表格、菜单、表单、数据展示面板、
  仪表盘、终端应用等。当用户要"做终端交互界面"、"终端菜单选择"、"终端表单"、
  "终端仪表盘"、"TUI 应用"、"终端里的 App"、"交互式终端程序"时触发。
  即使没有明确提到 Textual 库名，只要涉及构建有交互的终端界面就应使用此 skill。
compatibility: Python 3.8+, `pip install textual`, Linux/macOS 全功能支持，Windows 部分功能受限
---

# Textual Output — Python 终端 UI 框架

> 把终端当作"浏览器"：用 Python 写组件、用 CSS 做布局、靠事件系统驱动交互。

---

## 核心定位

Textual 是一个 **TUI 框架**（Text User Interface），不是美化库。它和 Rich 的关系是：Textual 内部使用 Rich 作为渲染引擎，但 Textual 提供的是完整的应用框架——组件树、CSS 布局、事件系统、异步支持。

**关键心智模型**：Textual 就像一个运行在终端里的前端框架。你有组件（Widget）、样式（CSS）、事件处理（on_* 方法）、状态管理（reactive 属性），所有这些都是 Python 代码，不需要 HTML/JS。

---

## 场景判断：用 Rich 还是 Textual？

这是最重要的决策。选错工具会浪费大量精力：

| 你需要的 | 用 Rich | 用 Textual |
|----------|---------|------------|
| 彩色 `print()` 输出 | ✅ | 杀鸡用牛刀 |
| 终端表格、进度条（一次性输出） | ✅ | — |
| 美化异常、日志、高亮代码 | ✅ | — |
| 用户可以选择/点击的交互菜单 | — | ✅ |
| 实时更新的数据面板/仪表盘 | — | ✅ |
| 带输入框的表单 | — | ✅ |
| 文件浏览器、设置界面 | — | ✅ |
| 终端里的 Todo App、聊天工具 | — | ✅ |
| Markdown/JSON 内容的只读展示 | ✅ 或 Textual.App | ✅ 用于交互浏览 |

**简记**：一次性显示 → Rich；需要用户交互（键盘/鼠标）→ Textual。

---

## 场景一：轻量美化 — 简单交互应用

当需求是"让数据展示更好看，同时允许简单交互"时，使用最小化的 Textual App 结构。

### 最简应用骨架

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static

class MyApp(App):
    """最简应用：Header + 内容 + Footer"""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Hello, [bold]Textual[/bold]!")
        yield Footer()

if __name__ == "__main__":
    app = MyApp()
    app.run()
```

`Ctrl+Q` 退出。Header/Footer 自动显示快捷键提示。

### 数据展示面板

用 `DataTable` 替代 Rich 的 Table（DataTable 支持排序、滚动、光标导航）：

```python
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer

ROWS = [
    ("1", "张三", "zhang@example.com", "活跃"),
    ("2", "李四", "li@example.com", "禁用"),
]

class TableApp(App):
    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("ID", "姓名", "邮箱", "状态")
        table.add_rows(ROWS)
```

### 选择菜单

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, ListView, ListItem, Footer

class MenuApp(App[str]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(
            ListItem(Static("查看数据")),
            ListItem(Static("导出报告")),
            ListItem(Static("退出")),
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.exit(str(event.item.query_one(Static).renderable))

if __name__ == "__main__":
    result = MenuApp().run()
    print(f"选择了: {result}")
```

### Markdown 查看器

```python
from textual.app import App, ComposeResult
from textual.widgets import MarkdownViewer

class DocViewer(App):
    def compose(self) -> ComposeResult:
        yield MarkdownViewer()
```

---

## 场景二：完整 TUI — 构建终端应用

当需要完整的应用架构时（多页面、复杂交互、后台任务），使用 Textual 的全部能力。

### 应用架构模式

```
App
├── Screen 1 (如: 主界面)
│   ├── Header
│   ├── Widget A (Container)
│   │   ├── Widget B
│   │   └── Widget C
│   └── Footer
├── Screen 2 (如: 设置页面)
│   └── ...
└── Screen 3 (如: 帮助页面)
```

### CSS 布局

Textual 使用类 CSS 语法做布局。CSS 可以写在独立的 `.tcss` 文件中，或通过 Python 的 `DEFAULT_CSS` 类变量嵌入：

```python
class LayoutApp(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;        /* 2 列 */
        grid-columns: 1fr 2fr;
    }
    #sidebar {
        background: $surface;
        border-right: solid $accent;
    }
    #main {
        padding: 1;
    }
    """
```

**核心布局模式**：

| 模式 | CSS | 适用场景 |
|------|-----|---------|
| **Grid** | `layout: grid; grid-size: 2; grid-columns: 1fr 2fr;` | 侧边栏+主区域 |
| **Horizontal** | `layout: horizontal;` | 工具栏、按钮组 |
| **Vertical** | `layout: vertical;` | 表单、设置页面 |
| **Dock** | `dock: top;` / `dock: bottom;` | Header/Footer 固定 |

### 状态管理 — Reactive

`reactive` 属性是 Textual 的核心状态管理机制。当属性变化时自动触发 UI 更新：

```python
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

class CounterApp(App):
    count = reactive(0)  # 响应式属性

    def compose(self) -> ComposeResult:
        yield Static(f"计数: {self.count}", id="display")

    def watch_count(self, old: int, new: int) -> None:
        """count 变化时自动调用"""
        self.query_one("#display", Static).update(f"计数: {new}")

    def on_key(self) -> None:
        self.count += 1
```

`reactive` 的 `always_update=True` 参数（即使值没变也触发）、`init=False`（延迟初始化）、`compute_` 方法（计算属性）是常用进阶模式。

### 常用 Widget 速查

| Widget | 用途 | 关键事件 |
|--------|------|---------|
| `Static` | 显示文本/Rich Renderable | `mount`, `click` |
| `Button` | 按钮 | `Button.Pressed` |
| `Input` | 单行文本输入 | `Input.Changed`, `Input.Submitted` |
| `TextArea` | 多行文本编辑 | `TextArea.Changed` |
| `DataTable` | 可交互表格（排序/光标） | `DataTable.CellSelected` |
| `ListView` / `OptionList` | 列表选择 | `ListView.Selected` / `OptionList.OptionSelected` |
| `Select` | 下拉选择 | `Select.Changed` |
| `Switch` / `Checkbox` | 开关/复选框 | `Changed` |
| `ProgressBar` | 进度条 | `mount` |
| `Tree` | 树形结构 | `Tree.NodeSelected` |
| `TabbedContent` / `Tabs` | 标签页 | `TabbedContent.TabActivated` |
| `MarkdownViewer` | Markdown 浏览（带 TOC） | — |
| `RichLog` | 流式日志输出 | — |
| `Footer` / `Header` | 快捷键提示栏 | — |

### 事件系统

Textual 的事件处理通过 `on_<event_name>` 方法名约定：

```python
# Widget 事件
def on_button_pressed(self, event: Button.Pressed) -> None: ...
def on_input_changed(self, event: Input.Changed) -> None: ...
def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None: ...

# 系统事件
def on_mount(self) -> None: ...       # 组件挂载完成
def on_key(self, event: events.Key) -> None: ...  # 按键
def on_click(self, event: events.Click) -> None: ...  # 鼠标点击
```

**自定义消息**：Widget 间通信通过 `Message` 子类：

```python
class MyWidget(Widget):
    class Selected(Message):
        """携带选中值的消息"""
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def action_select(self) -> None:
        self.post_message(self.Selected("some value"))
```

### 多页面 (Screen)

App 可以有多个 Screen，用 `push_screen` / `pop_screen` / `switch_screen` 导航：

```python
class SettingsScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Label("设置页面")

# 在主 App 中
self.push_screen(SettingsScreen())      # 推入（可返回）
self.switch_screen(SettingsScreen())    # 切换（替换当前）
```

### 后台任务 (Workers)

长时间操作不应阻塞 UI，使用 `@work` 装饰器：

```python
from textual import work

@work(exclusive=True)
async def fetch_data(self) -> None:
    data = await some_async_api_call()
    self.call_from_thread(self.update_ui, data)  # 线程安全更新 UI
```

---

## 最佳实践

### 1. CSS 用独立文件

当 CSS 超过 10 行时，提取到 `.tcss` 文件：

```python
class MyApp(App):
    CSS_PATH = "myapp.tcss"
```

这样可以利用 Textual 的热重载（`textual run --dev myapp.py`）和 CSS 编辑的即时反馈。

### 2. 用 `id` 查询 Widget

```python
# 在 compose 中设置 id
yield Button("确认", id="confirm-btn")

# 在其他方法中查询
btn = self.query_one("#confirm-btn", Button)
```

`query_one` 只找一个；`query` 返回所有匹配的；CSS 选择器语法完整可用（`".class"`, `"#id"`, `"WidgetType"`, 组合选择器）。

### 3. 开发模式

```bash
# 安装开发工具
pip install textual-dev

# 热重载 + 终端内控制台
textual run --dev myapp.py

# 在浏览器中调试（CSS 检查器、DOM 树）
textual serve myapp.py
```

### 4. 跨平台注意事项

- Windows 终端需要 **Windows Terminal**（非 cmd.exe），支持 true color
- Windows **不支持** `inline` 模式和 `textual serve` 的某些功能
- 开发时优先在 `textual run --dev` 下测试，它会自动检测终端能力

### 5. 测试

Textual 提供 `pilot` 用于自动化测试：

```python
async def test_counter():
    async with CounterApp().run_test() as pilot:
        await pilot.press("space")
        assert pilot.app.count == 1
```

---

## 进阶能力（按需深入）

以下不在此文档展开，需要时查阅官方文档：

| 功能 | 用途 | 文档链接 |
|------|------|---------|
| **自定义 Widget** | 创建可复用组件 | [Widget Guide](https://textual.textualize.io/guide/widgets/) |
| **动画** | CSS transition/animation | [Animation Guide](https://textual.textualize.io/guide/animation/) |
| **主题/设计** | 全局颜色变量 `$primary`, `$accent` | [Design Guide](https://textual.textualize.io/guide/design/) |
| **DataTable 高级** | 单元格自定义渲染、排序回调 | [DataTable](https://textual.textualize.io/widgets/data_table/) |
| **Screen 管理** | Modal screen、结果回传 | [Screens Guide](https://textual.textualize.io/guide/screens/) |
| **@on 装饰器** | 替代 `on_` 命名约定的显式事件绑定 | [Events Guide](https://textual.textualize.io/guide/events/) |
| **文本输入验证** | `Input` 的 `validators` 参数 | [Input Widget](https://textual.textualize.io/widgets/input/) |
| **Command Palette** | 命令面板 | [Command Palette](https://textual.textualize.io/guide/command_palette/) |

查阅完整 API：[Textual 官方文档](https://textual.textualize.io/)

---

## Rich + Textual 协作

Textual 内部使用 Rich，两者可以配合：

- **在 Static Widget 中显示 Rich 的 Renderable**：`Static(Panel("内容"))`、`Static(Table(...))` 等
- **RichLog Widget** 支持 Rich 的 `console.log()` 风格的输出
- **Markdown Widget** 内部用 Rich 的 Markdown 渲染

但大部分情况下，Textual 自己的 Widget（DataTable、Tree、Markdown 等）已经足够，不需要手动嵌套 Rich 对象。

---

## 护栏规则

1. **场景判断优先** — 生成代码前先判断：是一次性输出（用 Rich）还是交互式应用（用 Textual）
2. **安装检查** — 提醒用户 `pip install textual`（如尚未安装）
3. **最简起步** — 从最小 App 骨架开始，逐步添加 Widget，不要上来就构造复杂架构
4. **不要滥用 Textual** — 对于纯数据展示（无交互），用 Rich 的 Table/Panel/Markdown 更简单
5. **asyncio 意识** — `await self.mount()` 保证 Widget 挂载完成；`@work` 装饰器处理后台任务
6. **Windows 兼容** — 提醒用户使用 Windows Terminal，而非 cmd.exe
7. **文档规范** — 生成的 Python 代码和输出的 Markdown 文件遵循 `.omp/skills/markdown/SKILL.md`
