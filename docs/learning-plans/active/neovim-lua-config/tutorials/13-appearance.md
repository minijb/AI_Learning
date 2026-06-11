---
title: "13 — 外观定制：colorscheme 与 statusline"
updated: 2026-06-05
---

# 13 — 外观定制：colorscheme 与 statusline

> 所属计划: Neovim + Lua 配置实战 (现代版)
> 预计耗时: 35 分钟
> 前置知识: 04-init-lua-structure（vim.opt 基本配置）

---

## 1. 概念讲解

### kickstart 的外观选择

kickstart.nvim 选择了极简的外观配置：

- **Colorscheme**: `tokyonight.nvim`（默认 night 变体）
- **Statusline**: `mini.statusline`（mini.nvim 的一部分）
- **No bufferline**: kickstart 不安装 bufferline，用 Telescope 或 `<C-^>` 切换 buffer
- **No dashboard**: 默认不装启动界面（可在 `kickstart.plugins` 中找到示例）

设计原则：**minimal, boring, functional**——外观不应该是你花大量时间调试的部分。

### colorscheme 配置（kickstart 风格）

```lua
vim.pack.add { gh 'folke/tokyonight.nvim' }
require('tokyonight').setup {
  styles = {
    comments = { italic = false },
  },
}
vim.cmd.colorscheme 'tokyonight-night'
```

关键点：
- `vim.pack.add()` 后直接 `.setup()` + `colorscheme`，不放在任何 lazy loading 逻辑中
- 因为 colorscheme 必须在启动时就加载（否则会看到默认的高亮闪烁）

### mini.statusline（内置状态栏）

kickstart 使用 `mini.statusline` 而不是 `lualine`：
- 零配置开箱即用
- 代码量极小（单一模块）
- 完全可定制

```lua
local statusline = require 'mini.statusline'
statusline.setup { use_icons = vim.g.have_nerd_font }

-- 自定义光标位置格式：LINE:COLUMN
---@diagnostic disable-next-line: duplicate-set-field
statusline.section_location = function()
  return '%2l:%-2v'
end
```

### 热门配色方案

| 配色方案 | 风格 | vim.pack 安装 |
|---------|------|--------------|
| [tokyonight.nvim](https://github.com/folke/tokyonight.nvim) | 暗色 | `gh 'folke/tokyonight.nvim'` |
| [catppuccin](https://github.com/catppuccin/nvim) | 多风味 | `gh 'catppuccin/nvim'` |
| [rose-pine](https://github.com/rose-pine/neovim) | 暖色暗 | `gh 'rose-pine/neovim'` |
| [kanagawa.nvim](https://github.com/rebelot/kanagawa.nvim) | 复古暖 | `gh 'rebelot/kanagawa.nvim'` |

---

## 2. 代码示例

### kickstart 风格的完整 UI section

```lua
-- init.lua Section: UI
do
  -- ====== 配色方案 ======
  vim.pack.add { gh 'folke/tokyonight.nvim' }
  require('tokyonight').setup {
    styles = {
      comments = { italic = false },  -- 注释不斜体
    },
  }
  vim.cmd.colorscheme 'tokyonight-night'

  -- ====== 图标（条件安装） ======
  if vim.g.have_nerd_font then
    vim.pack.add { gh 'nvim-tree/nvim-web-devicons' }
  end

  -- ====== Git 标记 ======
  vim.pack.add { gh 'lewis6991/gitsigns.nvim' }
  require('gitsigns').setup {
    signs = {
      add = { text = '+' },
      change = { text = '~' },
      delete = { text = '_' },
      topdelete = { text = '‾' },
      changedelete = { text = '~' },
    },
  }

  -- ====== TODO 注释高亮 ======
  vim.pack.add { gh 'folke/todo-comments.nvim' }
  require('todo-comments').setup { signs = false }

  -- ====== mini.nvim 工具集 ======
  vim.pack.add { gh 'nvim-mini/mini.nvim' }

  -- 智能文本对象
  require('mini.ai').setup {
    n_lines = 500,
  }

  -- 环绕操作（类似 vim-surround）
  require('mini.surround').setup()

  -- 状态栏
  local statusline = require 'mini.statusline'
  statusline.setup { use_icons = vim.g.have_nerd_font }

  -- 自定义光标位置
  ---@diagnostic disable-next-line: duplicate-set-field
  statusline.section_location = function()
    return '%2l:%-2v'
  end
end
```

---

## 3. 练习

### 练习 1: 更换 colorscheme

从推荐列表中选择一个你喜欢的 colorscheme：

```lua
-- 以 catppuccin 为例
vim.pack.add { gh 'catppuccin/nvim' }
require('catppuccin').setup { flavour = 'mocha' }
vim.cmd.colorscheme 'catppuccin-mocha'
```

重启 Neovim，观察变化。验证 LSP 诊断颜色、Treesitter 高亮是否协调。

### 练习 2: 自定义 statusline 组件

在 `mini.statusline` 中添加当前时间：

```lua
statusline.section_location = function()
  return os.date '%H:%M'
end
```

### 练习 3: 调整透明度（可选）

如果你是透明终端背景的爱好者，在 colorscheme 配置中：
```lua
require('tokyonight').setup {
  transparent = true,
  styles = { sidebars = "transparent", floats = "transparent" },
}
```


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 更换 colorscheme 的完整步骤（以 catppuccin 为例）：
>
> 1. 将 UI section 中的 tokyonight 相关三行替换为：
>
> ```lua
> vim.pack.add { gh 'catppuccin/nvim' }
> require('catppuccin').setup { flavour = 'mocha' }  -- 或 'latte', 'frappe', 'macchiato'
> vim.cmd.colorscheme 'catppuccin-mocha'
> ```
>
> 2. 重启 Neovim，验证核心元素是否协调：
>    - **LSP 诊断**：故意写错代码，确认 Error/Warning/Hint 颜色依然清晰可辨
>    - **Treesitter 高亮**：打开一个 Lua 文件，确认函数名、参数、关键字各有区别色
>    - **Telescope 窗口**：按 `<leader>ff`，确认 Telescope UI 自动适配了新的配色
>    - **Statusline**：确认 mini.statusline 的颜色跟随了新 colorscheme
> 3. 其他热门选择的等效代码：
>
> ```lua
> -- rose-pine（暖色暗）
> vim.pack.add { gh 'rose-pine/neovim' }
> vim.cmd.colorscheme 'rose-pine'
>
> -- kanagawa（复古暖）
> vim.pack.add { gh 'rebelot/kanagawa.nvim' }
> vim.cmd.colorscheme 'kanagawa'
> ```
>
> **关键原则**：高质量的 colorscheme（tokyonight、catppuccin、rose-pine 等）都会正确设置 treesitter 和 LSP 高亮组。如果你的 LSP 诊断颜色在更换 colorscheme 后"消失"了，说明 colorscheme 没有覆盖诊断高亮组——考虑换回主流方案。

> [!tip]- 练习 2 参考答案
> 自定义 statusline 组件显示当前时间：
>
> ```lua
> -- 在 mini.statusline 部分，替换 section_location：
> local statusline = require 'mini.statusline'
> statusline.setup { use_icons = vim.g.have_nerd_font }
>
> ---@diagnostic disable-next-line: duplicate-set-field
> statusline.section_location = function()
>   return os.date '%H:%M'  -- 24 小时制时间，如 "14:35"
> end
> ```
>
> mini.statusline 的 `section_location` 返回值是直接渲染在状态栏右侧的字符串。原来的 `'%2l:%-2v'` 是 Vim 的 statusline 格式化语法（LINE:COLUMN）。`os.date` 是 Lua 标准库函数，接受 strftime 格式串。
>
> 更丰富的自定义示例——同时显示行号和当前 Git 分支：
>
> ```lua
> statusline.section_location = function()
>   local line_col = '%2l:%-2v'
>   local time = os.date '%H:%M'
>   return line_col .. '  ' .. time
> end
> ```
>
> **关键点**：`section_location` 在每次状态栏刷新时调用（频繁！），所以不要在函数内做昂贵的操作（如 Git 命令、文件 I/O）。

> [!tip]- 练习 3 参考答案（可选）
> 配置透明背景的完整设置：
>
> ```lua
> require('tokyonight').setup {
>   transparent = true,      -- 主编辑器背景透明
>   styles = {
>     sidebars = "transparent",  -- 侧边栏（如 neo-tree）背景透明
>     floats = "transparent",    -- 浮动窗口（Telescope、诊断浮动窗）背景透明
>   },
> }
> ```
>
> **前置要求**：
> - 你的**终端模拟器**必须支持透明背景。在 Windows Terminal 中：Settings → Profiles → Appearance → "Enable acrylic" 或设置背景透明度
> - 如果你的终端背景是不透明的纯色，Neovim 的"透明"实际上是显示终端背景色——视觉效果和设 `transparent = false` 没有区别
>
> **视觉效果**：
> - `transparent = true`：编辑器区域可以透过看到终端背景（可能是一张壁纸或其他窗口）
> - `sidebars = "transparent"`：neo-tree 等侧边栏也透明
> - `floats = "transparent"`：Telescope 的一个副作用——预览窗口变透明后文字可能难以阅读，尤其是预览内容背景也是深色时
>
> **注意**：`transparent` 和某些终端多路复用器（如 tmux）配合时可能显示异常。如果遇到颜色问题，先关闭透明度排查。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [Neovim 配色方案集合](https://github.com/rockerBOO/awesome-neovim#colorscheme)
- [mini.statusline 文档](https://github.com/nvim-mini/mini.nvim/blob/main/doc/mini-statusline.txt)
- [tokyonight.nvim 文档](https://github.com/folke/tokyonight.nvim)
- [`:help hl-groups`](https://neovim.io/doc/user/syntax.html#highlight-groups) — 所有可用高亮组

---

## 常见陷阱

- **`termguicolors` 在 Neovim 0.12 中默认开启**：如果颜色不对，检查终端是否支持 true color（`$COLORTERM` 应包含 `truecolor`）。
- **mini.statusline 替代了 lualine**：mini.statusline 更轻量，功能也精简。如果你需要 Git 分支、LSP 诊断计数等高级显示，可以切换到 lualine。
- **Nerd Font 不是必须的**：kickstart 通过 `vim.g.have_nerd_font` 变量控制图标显示。没有 Nerd Font 也能正常使用，只是某些插件会显示空白或问号。
- **colorscheme 必须在其他 UI 插件之前加载**：在 do 块中把 colorscheme 相关的 `vim.pack.add()` 和 `vim.cmd.colorscheme()` 放在最前面。
