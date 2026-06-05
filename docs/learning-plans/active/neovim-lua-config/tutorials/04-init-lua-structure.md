---
title: "04 — init.lua 结构与基本选项配置"
updated: 2026-06-05
---

# 04 — init.lua 结构与基本选项配置

> 所属计划: Neovim + Lua 配置实战 (现代版)
> 预计耗时: 40 分钟
> 前置知识: 03-lua-functions-modules（模块系统）

---

## 1. 概念讲解

### init.lua 的定位

Neovim 启动时按以下顺序查找配置文件：

1. `~/.config/nvim/init.lua`（Lua 配置，推荐）
2. `~/.config/nvim/init.vim`（Vimscript 配置，兼容旧配置）

两者都存在时，Neovim **只加载 `init.lua`**，忽略 `init.vim`。

### 两种配置组织风格

**风格 A: kickstart 单文件风格（本计划推荐）**

```
~/.config/nvim/
├── init.lua              ← 单一入口，~1000 行，9 个 do 块
├── nvim-pack-lock.json   ← vim.pack 锁文件（自动生成）
├── lua/
│   ├── kickstart/        ← kickstart 自带的扩展模块
│   │   └── plugins/      ←   可选插件（debug, lint, ...）
│   └── custom/           ← 你的自定义插件
│       └── plugins/
└── after/                ← 覆盖/补充配置（最后加载）
```

**风格 B: 模块化风格（从 kickstart 演进而来）**

```
~/.config/nvim/
├── init.lua              ← 入口：设置 leader + require 各模块
├── nvim-pack-lock.json
├── lua/
│   └── config/
│       ├── options.lua   ← 编辑器选项
│       ├── keymaps.lua   ← 按键映射
│       ├── autocmds.lua  ← 自动命令
│       ├── plugins.lua   ← vim.pack.add() 集中管理
│       ├── lsp.lua       ← LSP 配置
│       └── completion.lua← blink.cmp 配置
└── after/
```

两种风格可以根据个人偏好选择。kickstart 单文件适合学习和快速上手；模块化适合长期维护较大配置。

### Neovim 0.12: vim.loader.enable()

```lua
-- 放在 init.lua 第一行，缓存编译后的 Lua 模块，显著加速启动
vim.loader.enable()
```

### vim.o / vim.opt / vim.g / vim.bo / vim.wo

| API | 作用域 | 示例 |
|-----|--------|------|
| `vim.o` | 全局选项（简单值） | `vim.o.number = true` |
| `vim.opt` | 全局选项（支持类 Vimscript `:set`） | `vim.opt.listchars = { tab = '» ' }` |
| `vim.bo` | 缓冲区局部选项 | `vim.bo[0].filetype = "lua"` |
| `vim.wo` | 窗口局部选项 | `vim.wo[0].cursorline = true` |
| `vim.g` | 全局变量 | `vim.g.mapleader = " "` |
| `vim.b` | 缓冲区局部变量 | `vim.b.my_var = 1` |

`vim.opt` 支持 append/prepend/remove：
```lua
vim.opt.wildignore:append({ "*/node_modules/*", "*/target/*" })
```

### 常用基础选项

```lua
-- 行号
vim.o.number = true
-- vim.o.relativenumber = true  -- 可选：相对行号

-- 缩进
vim.o.tabstop = 4
vim.o.shiftwidth = 4
vim.o.expandtab = true

-- 搜索
vim.o.ignorecase = true
vim.o.smartcase = true

-- 界面
vim.o.signcolumn = "yes"       -- LSP 诊断标记列
vim.o.scrolloff = 10           -- 光标距边界的最小行数
vim.o.cursorline = true        -- 高亮当前行
vim.o.termguicolors = true     -- 24 位真彩色（自动启用）

-- 剪贴板
vim.schedule(function()
  vim.o.clipboard = "unnamedplus"  -- 延迟设置，减少启动时间
end)

-- 分割窗口
vim.o.splitright = true
vim.o.splitbelow = true

-- undo
vim.o.undofile = true

-- 预览替换
vim.o.inccommand = "split"

-- 确认退出（避免误关闭未保存文件）
vim.o.confirm = true
```

---

## 2. 代码示例

### 最小 init.lua（kickstart 风格 foundation block）

```lua
-- ~/.config/nvim/init.lua
vim.loader.enable()

vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- 选项
vim.o.number = true
vim.o.mouse = "a"
vim.o.showmode = false
vim.schedule(function() vim.o.clipboard = "unnamedplus" end)
vim.o.breakindent = true
vim.o.undofile = true
vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.signcolumn = "yes"
vim.o.updatetime = 250
vim.o.timeoutlen = 300
vim.o.splitright = true
vim.o.splitbelow = true
vim.o.list = true
vim.opt.listchars = { tab = "» ", trail = "·", nbsp = "␣" }
vim.o.inccommand = "split"
vim.o.cursorline = true
vim.o.scrolloff = 10
vim.o.confirm = true
```

**运行方式:**
1. 创建 `~/.config/nvim/init.lua`（Windows: `%LOCALAPPDATA%/nvim/init.lua`）
2. 写入上述代码
3. 启动 Neovim，`:set number?` 验证行号已开启
4. 依次检查 `:set scrolloff?`、`:set signcolumn?` 等确认选项生效

---

## 3. 练习

### 练习 1: 迁移现有配置

如果你已有 `init.vim`，将其中的 `set` 命令翻译成 Lua：

```vim
" Vimscript                    →  Lua
set number                     →  vim.o.number = true
set tabstop=4                  →  vim.o.tabstop = 4
set mouse=a                    →  vim.o.mouse = "a"
set listchars=tab:▸\ ,trail:·  →  vim.opt.listchars = { tab = "▸ ", trail = "·" }
```

### 练习 2: 理解 vim.opt 的 table 语义

```lua
:lua print(vim.inspect(vim.opt.listchars))
:lua vim.opt.listchars:append({ extends = ">" })
:lua print(vim.inspect(vim.opt.listchars))
```

### 练习 3: 对比 vim.o 和 vim.opt

```lua
-- 这两个等价吗？
vim.o.listchars = "tab:» ,trail:·"
vim.opt.listchars = { tab = "» ", trail = "·" }
-- 在 Neovim 中测试，观察差异
```

---

## 4. 扩展阅读

- [Neovim 官方 Lua Guide — Options](https://neovim.io/doc/user/lua-guide.html#lua-guide-options)
- [`:help vim.opt`](https://neovim.io/doc/user/lua.html#vim.opt)
- [`:help vim.loader`](https://neovim.io/doc/user/helptag.html?tag=vim.loader) — 0.12 新增的缓存加速
- [`:help options`](https://neovim.io/doc/user/options.html) — 所有可用选项的完整列表

---

## 常见陷阱

- **在 Windows 上路径分隔符**：Lua 字符串中的 `\` 需要转义。用 `[[]]` 或 `/` 代替。
- **`vim.opt.listchars` 是 table 不是字符串**：`vim.opt.listchars = { tab = "▸ " }`，不是 `vim.opt.listchars = "tab:▸ "`。
- **`vim.g.mapleader` 必须在所有 keymap 之前设置**：因为 keymap 在定义时就会解析 leader 的值。
- **`clipboard = "unnamedplus"` 放在 `vim.schedule` 中**：kickstart 的做法是延迟设置以加速启动。如果你有频繁用系统剪贴板的需求，可以直接设置。
- **`vim.loader.enable()` 可能跳过代码变更**：修改了 `lua/` 下的模块后，需要重启 Neovim 才能看到效果。开发自己的配置时可以暂时注释掉这行。
