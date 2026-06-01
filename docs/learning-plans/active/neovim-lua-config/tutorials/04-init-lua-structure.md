# 04 — init.lua 结构与基本选项配置

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 45 分钟
> 前置知识: 03-lua-functions-modules（模块系统）

---

## 1. 概念讲解

### init.lua 的定位

Neovim 启动时按以下顺序查找配置文件：

1. `~/.config/nvim/init.lua`（推荐，Lua 配置）
2. `~/.config/nvim/init.vim`（Vimscript 配置，兼容旧配置）

两者都存在时，Neovim **只加载 `init.lua`**，忽略 `init.vim`。

### 推荐的目录结构

```
~/.config/nvim/
├── init.lua              ← 入口：只负责 require 各模块
├── lua/
│   ├── config/
│   │   ├── options.lua   ← 编辑器选项
│   │   ├── keymaps.lua   ← 按键映射
│   │   ├── autocmds.lua  ← 自动命令
│   │   └── lazy.lua      ← lazy.nvim 初始化
│   └── plugins/
│       ├── lsp.lua       ← LSP 相关插件配置
│       ├── cmp.lua       ← 补全配置
│       └── telescope.lua ← Telescope 配置
└── lazy-lock.json        ← lazy.nvim 锁定文件（自动生成）
```

### init.lua 最小骨架

```lua
-- ~/.config/nvim/init.lua

-- 1. 设置 leader 键（必须在其他映射之前）
vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- 2. 加载基础配置
require("config.options")
require("config.keymaps")
require("config.autocmds")

-- 3. 初始化插件管理器
require("config.lazy")
```

### vim.o / vim.opt / vim.g / vim.bo / vim.wo

Neovim 提供了多层级的选项访问 API：

| API | 作用域 | 示例 |
|-----|--------|------|
| `vim.o` | 全局选项（字符串形式） | `vim.o.number = true` |
| `vim.opt` | 全局选项（推荐，类 Vimscript `:set`） | `vim.opt.number = true` |
| `vim.bo` | 缓冲区局部选项 | `vim.bo[0].filetype = "lua"` |
| `vim.wo` | 窗口局部选项 | `vim.wo[0].cursorline = true` |
| `vim.g` | 全局变量 | `vim.g.mapleader = " "` |
| `vim.b` | 缓冲区局部变量 | `vim.b.my_var = 1` |

**`vim.opt` 的优势：**

```lua
-- vim.o 方式：只能逐个设置
vim.o.tabstop = 4
vim.o.shiftwidth = 4
vim.o.expandtab = true

-- vim.opt 方式：支持类 Vimscript 语法
vim.opt.tabstop = 4
vim.opt.shiftwidth = 4
vim.opt.expandtab = true

-- vim.opt 支持 append/prepend/remove
vim.opt.wildignore:append({ "*/node_modules/*", "*/target/*" })
```

### 常用基础选项

```lua
-- 行号
vim.opt.number = true           -- 绝对行号
vim.opt.relativenumber = true   -- 相对行号

-- 缩进
vim.opt.tabstop = 4             -- Tab 显示宽度
vim.opt.softtabstop = 4         -- 编辑时 Tab 的实际列数
vim.opt.shiftwidth = 4          -- 自动缩进的宽度
vim.opt.expandtab = true        -- Tab 转换为空格

-- 搜索
vim.opt.ignorecase = true       -- 忽略大小写
vim.opt.smartcase = true        -- 有大写字母时不忽略
vim.opt.hlsearch = false        -- 不高亮搜索结果

-- 界面
vim.opt.termguicolors = true    -- 24 位真彩色
vim.opt.signcolumn = "yes"      -- 始终显示标记列（避免 LSP 诊断闪烁）
vim.opt.scrolloff = 8           -- 光标距上下边界的最小行数
vim.opt.cursorline = true       -- 高亮当前行

-- 剪贴板
vim.opt.clipboard = "unnamedplus"  -- 与系统剪贴板同步

-- 分割窗口
vim.opt.splitright = true       -- 垂直分割在右
vim.opt.splitbelow = true       -- 水平分割在下
```

---

## 2. 代码示例

完整的 `lua/config/options.lua`：

```lua
-- lua/config/options.lua
local M = {}

function M.setup()
    -- ====== 行号 ======
    vim.opt.number = true
    vim.opt.relativenumber = true

    -- ====== 缩进 ======
    vim.opt.tabstop = 4
    vim.opt.softtabstop = 4
    vim.opt.shiftwidth = 4
    vim.opt.expandtab = true
    vim.opt.smartindent = true

    -- ====== 搜索 ======
    vim.opt.ignorecase = true
    vim.opt.smartcase = true
    vim.opt.hlsearch = false
    vim.opt.incsearch = true

    -- ====== 界面 ======
    vim.opt.termguicolors = true
    vim.opt.signcolumn = "yes"
    vim.opt.scrolloff = 8
    vim.opt.cursorline = true
    vim.opt.colorcolumn = "80"

    -- ====== 剪贴板 ======
    vim.opt.clipboard = "unnamedplus"

    -- ====== 分割窗口 ======
    vim.opt.splitright = true
    vim.opt.splitbelow = true

    -- ====== 备份与交换文件 ======
    vim.opt.swapfile = false
    vim.opt.backup = false
    -- 将所有 undo 历史集中到一个目录
    vim.opt.undodir = vim.fn.stdpath("data") .. "/undodir"
    vim.opt.undofile = true

    -- ====== 性能 ======
    vim.opt.updatetime = 50     -- 更快触发 CursorHold 事件
    vim.opt.timeoutlen = 300    -- 按键序列超时（ms）
end

return M
```

入口 `init.lua`：

```lua
-- ~/.config/nvim/init.lua

-- leader 键
vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- 加载基础配置
require("config.options").setup()
```

**运行方式:**
1. 将上述文件放在 Neovim 配置目录
2. 启动 Neovim: `nvim`
3. 检查选项是否生效: `:set number?` 应显示 `number`

---

## 3. 练习

### 练习 1: 迁移现有配置
如果你已有 `init.vim`，请将其中的 `set` 命令翻译成 Lua 的 `vim.opt` 形式，创建 `lua/config/options.lua`。

从 Vimscript 到 Lua 的对照：
```vim
" Vimscript                    →  Lua
set number                     →  vim.opt.number = true
set tabstop=4                  →  vim.opt.tabstop = 4
set mouse=a                    →  vim.opt.mouse = "a"
set listchars=tab:▸\ ,trail:·  →  vim.opt.listchars = { tab = "▸ ", trail = "·" }
```

### 练习 2: 查看当前选项值
在 Neovim 中运行 `:lua print(vim.inspect(vim.opt.tabstop))` 查看 `vim.opt` 返回的结构。用同样方式检查 `vim.opt.listchars` —— 理解 table 形式的选项。

### 练习 3: 创建你自己的模块化配置（可选）
创建以下完整结构，每个模块只导出一个 `setup()` 函数：

```
lua/config/
├── options.lua
├── keymaps.lua   ← 先创建空 setup
├── autocmds.lua  ← 先创建空 setup
```

---

## 4. 扩展阅读

- [Neovim 官方 Lua Guide — Options](https://neovim.io/doc/user/lua-guide.html#lua-guide-options)
- [`:help vim.opt`](https://neovim.io/doc/user/lua.html#vim.opt)
- [`:help options`](https://neovim.io/doc/user/options.html) — 所有可用选项的完整列表

---

## 常见陷阱

- **在 Windows 上路径分隔符**：Lua 字符串中的 `\` 需要转义。用 `[[]]` 或 `/` 代替 `\`。
- **`vim.opt.listchars` 的特殊格式**：它是 table 而非字符串。`vim.opt.listchars = { tab = "▸ ", trail = "·" }`，不是 `vim.opt.listchars = "tab:▸ ,trail:·"`。
- **`vim.g.mapleader` 必须在所有按键映射之前设置**：因为 keymap 在定义时就会使用 leader 的值。
- **忘记调用 `setup()`**：如果模块有 `setup()` 函数但没有调用，选项不会被设置。
- **相对行号在当前行显示 0**：这是正常行为，`0` 表示这是当前行。
