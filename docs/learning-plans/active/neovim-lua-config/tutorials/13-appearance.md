---
title: "13 — 外观定制：colorscheme 与 statusline"
updated: 2026-06-18
---

# 13 — 外观定制：colorscheme 与 statusline

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 40 分钟
> 前置知识: [[04-init-lua-structure]]、[[07-vim-pack]]、[[08-modern-plugin-patterns]]

---

## 1. 概念讲解

### 外观配置的设计哲学

Neovim 的外观 = colorscheme + 状态栏 + 图标 + 空白字符显示 + 一系列窗口/光标选项。好的外观配置应当：

1. **先加载 colorscheme**：所有 UI 插件都依赖高亮组（highlight groups）已定义；
2. **保持极简**：kickstart 不装 bufferline、dashboard，避免视觉噪音；
3. **图标可降级**：通过 `vim.g.have_nerd_font` 控制，无 Nerd Font 时自动用文本替代；
4. **一致性优先**：colorscheme、Telescope、statusline、diagnostics 使用同一套调色板。

### colorscheme 加载顺序

**colorscheme 必须在 statusline、Telescope、which-key 等 UI 插件之前加载。** 否则你会看到：

- 启动瞬间一闪默认配色（"flash of unstyled content"）；
- statusline 颜色错误；
- 某些插件窗口使用旧的高亮组。

推荐顺序：

```
1. vim.loader.enable() / leader / 全局变量
2. colorscheme 的 vim.pack.add() + setup() + vim.cmd.colorscheme()
3. 其他 UI 插件（gitsigns / which-key / mini.statusline / Telescope …）
```

### mini.statusline 自定义

`mini.statusline` 是 mini.nvim 模块之一。kickstart 选择它而不是 `lualine`，因为：

- 单一模块，零依赖；
- 代码极小；
- 完全可定制，又不失开箱即用。

核心 API：

```lua
local statusline = require 'mini.statusline'
statusline.setup { use_icons = vim.g.have_nerd_font }

-- 自定义光标位置格式：LINE:COLUMN
---@diagnostic disable-next-line: duplicate-set-field
statusline.section_location = function()
  return '%2l:%-2v'
end
```

### mini.icons 与 mock_nvim_web_devicons

Neovim 生态中很多插件依赖 `nvim-web-devicons` 提供文件类型图标。mini.nvim 提供两个相关模块：

- `mini.icons`：新的图标实现，更轻量；
- `mock_nvim_web_devicons`：让只认识 `nvim-web-devicons` 的老插件也能工作。

```lua
vim.pack.add { gh 'nvim-mini/mini.nvim' }

require('mini.icons').setup { style = 'glyph' }

-- 如果老插件仍然 require('nvim-web-devicons')，启用 mock
MiniIcons.mock_nvim_web_devicons()
```

### listchars 与空白字符显示

`vim.opt.listchars` 控制 `vim.o.list = true` 时如何渲染不可见字符。这是代码可读性的重要细节。

```lua
vim.o.list = true
vim.opt.listchars = {
  tab = '» ',
  trail = '·',
  nbsp = '␣',
}
```

| 键 | 含义 | 示例 |
|---|------|------|
| `tab` | Tab 字符显示 | `» `（右双尖括号 + 空格） |
| `trail` | 行尾空格 | `·`（中点） |
| `nbsp` | 不间断空格 | `␣`（空格符号） |
| `eol` | 换行符 | `↴`（可选开启） |
| `extends` | 行末溢出 | `›` |
| `precedes` | 行首溢出 | `‹` |

### 常用 UI 选项

| 选项 | 作用 | kickstart 典型值 |
|------|------|-----------------|
| `vim.o.number` | 显示行号 | `true` |
| `vim.o.relativenumber` | 相对行号 | `false`（kickstart 默认关闭） |
| `vim.o.cursorline` | 高亮当前行 | `true` |
| `vim.o.signcolumn` | 左侧标记列 | `'yes'`（诊断/git 标记预留空间） |
| `vim.o.scrolloff` | 光标上下最小保留行数 | `10` |
| `vim.o.showmode` | 显示 -- INSERT -- 等模式 | `false`（statusline 已显示） |
| `vim.o.colorcolumn` | 高亮某列（如 80/120） | `''`（默认不启用） |
| `vim.o.termguicolors` | 真彩色 | 0.12 默认 `true` |

---

## 2. 代码示例

### kickstart 风格的完整 UI section

```lua
-- init.lua Section: UI / CORE UX（Neovim 0.12.3+）
do
  local gh = function(repo) return 'https://github.com/' .. repo end

  -- ====== 1. colorscheme 必须最先加载 ======
  vim.pack.add { gh 'folke/tokyonight.nvim' }
  require('tokyonight').setup {
    styles = {
      comments = { italic = false },
      keywords = { italic = false },
    },
  }
  vim.cmd.colorscheme 'tokyonight-night'

  -- ====== 2. 图标（条件安装） ======
  -- 现代 kickstart 用 mini.icons + mock；
  -- 老插件若直接依赖 nvim-web-devicons，可保留兼容。
  require('mini.icons').setup { style = 'glyph' }
  MiniIcons.mock_nvim_web_devicons()

  -- ====== 3. Git 标记 ======
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

  -- ====== 4. 按键提示 ======
  vim.pack.add { gh 'folke/which-key.nvim' }
  require('which-key').setup {
    delay = 0,
    icons = {
      mappings = vim.g.have_nerd_font,
    },
    spec = {
      { '<leader>s', group = '[S]earch', mode = { 'n', 'v' } },
      { '<leader>t', group = '[T]oggle' },
    },
  }

  -- ====== 5. TODO 注释高亮 ======
  vim.pack.add { gh 'folke/todo-comments.nvim' }
  require('todo-comments').setup { signs = false }

  -- ====== 6. mini.nvim 工具集 ======
  vim.pack.add { gh 'nvim-mini/mini.nvim' }

  -- 智能文本对象：注意 0.12 内置 an/in，所以 kickstart 用 aa/ii
  require('mini.ai').setup {
    mappings = { around_next = 'aa', inside_next = 'ii' },
    n_lines = 500,
  }

  -- 环绕操作
  require('mini.surround').setup()

  -- 状态栏
  local statusline = require 'mini.statusline'
  statusline.setup { use_icons = vim.g.have_nerd_font }

  ---@diagnostic disable-next-line: duplicate-set-field
  statusline.section_location = function()
    return '%2l:%-2v'
  end

  -- ====== 7. 全局 UI 选项 ======
  vim.o.cursorline = true
  vim.o.signcolumn = 'yes'
  vim.o.scrolloff = 10
  vim.o.showmode = false
  vim.o.list = true
  vim.opt.listchars = { tab = '» ', trail = '·', nbsp = '␣' }
end
```

### 常用 colorscheme 推荐

| 配色方案 | 风格 | 安装命令 | 激活 |
|----------|------|---------|------|
| [tokyonight.nvim](https://github.com/folke/tokyonight.nvim) | 暗色 / 现代 | `gh 'folke/tokyonight.nvim'` | `tokyonight-night` / `tokyonight-storm` |
| [catppuccin](https://github.com/catppuccin/nvim) | 柔和 / 多风味 | `gh 'catppuccin/nvim'` | `catppuccin-mocha` / `catppuccin-macchiato` |
| [gruvbox.nvim](https://github.com/ellisonleao/gruvbox.nvim) | 复古暖 | `gh 'ellisonleao/gruvbox.nvim'` | `gruvbox` |
| [rose-pine](https://github.com/rose-pine/neovim) | 暖色暗 | `gh 'rose-pine/neovim'` | `rose-pine` / `rose-pine-moon` |
| [kanagawa.nvim](https://github.com/rebelot/kanagawa.nvim) | 复古和风 | `gh 'rebelot/kanagawa.nvim'` | `kanagawa` |
| [mini.hues](https://github.com/nvim-mini/mini.nvim) | 自定义 | `gh 'nvim-mini/mini.nvim'` | `minicyan` / `miniwinter` |

> [!TIP]
> `mini.hues` 是 mini.nvim 内置的 colorscheme 生成器，可通过 `require('mini.hues').setup()` 用少量参数生成整套配色。适合想自定义又懒得维护 colorscheme 的用户。

### 用 mini.hues 自定义 colorscheme

```lua
vim.pack.add { gh 'nvim-mini/mini.nvim' }

-- 基于一个主色生成完整 colorscheme
require('mini.hues').setup {
  background = '#112233',  -- 深蓝灰背景
  foreground = '#c8d0e0',  -- 浅灰前景
  saturation = 'medium',
  accent = 'azure',        -- 强调色
}

vim.cmd.colorscheme 'minihues'  -- 生成的主题名为 minihues
```

### 完整 UI 选项模板

```lua
-- lua/config/options.lua 的外观部分
vim.o.number = true
vim.o.relativenumber = false
vim.o.mouse = 'a'

vim.o.cursorline = true       -- 高亮当前行
vim.o.signcolumn = 'yes'      -- 始终显示标记列，避免窗口跳动
vim.o.scrolloff = 10          -- 光标距离屏幕边缘最小 10 行
vim.o.sidescrolloff = 8       -- 水平滚动时保留 8 列
vim.o.showmode = false        -- 模式显示交给 statusline
vim.o.colorcolumn = ''        -- 不显示列边界；可设为 '120' 提示行长

vim.o.list = true
vim.opt.listchars = {
  tab = '» ',
  trail = '·',
  nbsp = '␣',
}

-- 真彩色在 0.12 默认开启；旧终端可显式确认
-- vim.o.termguicolors = true
```

### 更多 UI 选项与透明效果

```lua
-- 状态栏：0=不显示，2=始终显示（推荐）
vim.o.laststatus = 2

-- 命令行高度（0 会在需要时弹出）
vim.o.cmdheight = 1

-- 补全菜单与浮动窗口透明度（0-255，值越大越透明）
vim.o.pumblend = 10
vim.o.winblend = 10

-- 分隔符样式
vim.opt.fillchars = {
  vert = '│',
  horiz = '─',
  eob = ' ',  -- 文件末尾空行不显示 ~
}

-- 列边界提示（常用于 80/100/120 字符规范）
-- vim.o.colorcolumn = '120'
```

### 自定义 mini.statusline 组件

除了 `section_location`，mini.statusline 还允许覆盖 `section_mode`、`section_searchcount` 等组件。下面示例在状态栏右侧同时显示行号、列号和 Git 分支（只读）：

```lua
local statusline = require 'mini.statusline'
statusline.setup { use_icons = vim.g.have_nerd_font }

---@diagnostic disable-next-line: duplicate-set-field
statusline.section_location = function()
  return '%2l:%-2v'
end

---@diagnostic disable-next-line: duplicate-set-field
statusline.section_git = function()
  local summary = vim.b.minidiff_summary
  if summary == nil then return '' end
  return summary.head or ''
end
```

---

## 3. 练习

### 练习 1: 更换 colorscheme

从推荐列表中选择一个 colorscheme（如 catppuccin），替换默认的 tokyonight。验证：
- LSP 诊断颜色是否清晰；
- Treesitter 高亮是否协调；
- Telescope 窗口是否自动适配。

### 练习 2: 自定义 mini.statusline

在 `mini.statusline` 中自定义一个组件：显示当前时间 `HH:MM`，同时保留行号:列号。

### 练习 3: 配置 listchars

添加 `eol` 显示，使换行符显示为 `↴`。观察代码中是否存在 trailing whitespace。

### 练习 4: 切换 Nerd Font 降级（可选）

把 `vim.g.have_nerd_font` 改成 `false`，重启 Neovim，观察 statusline、which-key、Telescope 是否仍可用纯文本渲染。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 以 catppuccin 为例，替换 UI section 中的 colorscheme 部分：
>
> ```lua
> vim.pack.add { gh 'catppuccin/nvim' }
> require('catppuccin').setup { flavour = 'mocha' }
> vim.cmd.colorscheme 'catppuccin-mocha'
> ```
>
> 其他选择：
>
> ```lua
> -- gruvbox
> vim.pack.add { gh 'ellisonleao/gruvbox.nvim' }
> require('gruvbox').setup {}
> vim.cmd.colorscheme 'gruvbox'
>
> -- rose-pine
> vim.pack.add { gh 'rose-pine/neovim' }
> vim.cmd.colorscheme 'rose-pine'
>
> -- kanagawa
> vim.pack.add { gh 'rebelot/kanagawa.nvim' }
> vim.cmd.colorscheme 'kanagawa'
> ```
>
> **验证清单**：
> - 故意写错代码，确认 Error/Warning/Hint 颜色清晰可辨；
> - 打开 Lua 文件，确认函数名、参数、关键字各有区别色；
> - 按 `<leader>sf` 打开 Telescope，确认边框/高亮跟随新配色；
> - 看 statusline，确认背景/前景色与 colorscheme 一致。
>
> **关键原则**：高质量 colorscheme 都会正确设置 treesitter 和 LSP 诊断高亮组。如果 LSP 诊断颜色"消失"，说明 colorscheme 覆盖不全——考虑换回主流方案。

> [!tip]- 练习 2 参考答案
> 在 statusline 中同时显示行号:列号和时间：
>
> ```lua
> local statusline = require 'mini.statusline'
> statusline.setup { use_icons = vim.g.have_nerd_font }
>
> ---@diagnostic disable-next-line: duplicate-set-field
> statusline.section_location = function()
>   local line_col = '%2l:%-2v'
>   local time = os.date '%H:%M'
>   return line_col .. '  ' .. time
> end
> ```
>
> `section_location` 每次状态栏刷新都会调用，不要做昂贵操作（如 Git 命令、文件 I/O）。`os.date` 开销极小，可接受。

> [!tip]- 练习 3 参考答案
> 在 `listchars` 中加入 `eol`：
>
> ```lua
> vim.o.list = true
> vim.opt.listchars = {
>   tab = '» ',
>   trail = '·',>   nbsp = '␣',>   eol = '↴',
> }
> ```
>
> **注意**：开启 `eol` 后代码会显得更"拥挤"，因为每行末尾都有 `↴`。很多人只开启 `tab` + `trail` + `nbsp`，`eol` 按需启用。

> [!tip]- 练习 4 参考答案（可选）> 在 `init.lua` 顶部设置：
>
> ```lua
> vim.g.have_nerd_font = false
> ```>
> 重启后观察：
> - `mini.statusline` 的 Git/诊断图标变成纯文本或空白；> - `which-key` 不再显示 Nerd Font 图标；> - `mini.icons` / `mock_nvim_web_devicons` 返回文本 fallback；> - Telescope 文件图标退化为文件类型字母。
>
> 这说明 kickstart 的图标支持是**条件式**的，无 Nerd Font 也能正常工作。重新设为 `true` 即可恢复图标。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Neovim 配色方案集合](https://github.com/rockerBOO/awesome-neovim#colorscheme)
- [mini.statusline 文档](https://github.com/nvim-mini/mini.nvim/blob/main/doc/mini-statusline.txt)
- [mini.icons 文档](https://github.com/nvim-mini/mini.nvim/blob/main/doc/mini-icons.txt)
- [tokyonight.nvim 文档](https://github.com/folke/tokyonight.nvim)
- [`:help hl-groups`](https://neovim.io/doc/user/syntax.html#highlight-groups) — 所有可用高亮组

---

## 常见陷阱

- **`termguicolors` 在 Neovim 0.12 中默认开启**：如果颜色不对，检查终端是否支持 true color（`$COLORTERM` 应包含 `truecolor`）。
- **colorscheme 必须在其他 UI 插件之前加载**：把 `vim.pack.add()` + `vim.cmd.colorscheme()` 放在 UI section 最前面。
- **mini.statusline 替代了 lualine**：mini.statusline 更轻量，功能也精简。需要 Git 分支、LSP 诊断计数等高级显示可切换到 lualine。
- **Nerd Font 不是必须的**：通过 `vim.g.have_nerd_font` 控制图标显示。无 Nerd Font 也能正常使用。
- **mini.ai 与 0.12 内置 an/in 冲突**：kickstart 把 `around_next` / `inside_next` 改为 `aa` / `ii`，避免与内置 treesitter 文本对象冲突。
- **`eol` 开启后视觉噪音大**：建议只开启 `tab` / `trail` / `nbsp`，`eol` 根据个人喜好启用。
- **`showmode = false` 的前提是 statusline 能显示模式**：如果 statusline 没有模式组件，可能不知道自己当前在什么模式。
