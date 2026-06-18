---
title: "15 — 模块化配置架构：多文件组织与迁移策略"
updated: 2026-06-18
---

# 15 — 模块化配置架构：多文件组织与迁移策略

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 55 分钟
> 前置知识: [[14-kickstart-architecture]]、[[07-vim-pack]]、[[09-modern-lsp]]

---

## 1. 概念讲解

### 为什么需要模块化？

kickstart.nvim 的单文件设计是极佳的学习起点，但当配置增长时会出现痛点：

| 规模 | 单文件体验 | 痛点 |
|------|----------|------|
| < 500 行 | ★★★★★ | 无 |
| 500-1000 行 | ★★★★ | 滚动稍多，但 `do` 块提供足够结构 |
| 1000-2000 行 | ★★★ | 查找特定配置项依赖搜索 |
| > 2000 行 | ★★ | 难以快速定位；多人协作困难 |

模块化的核心价值：**按关注点切分 → 按需加载 → 独立修改 → 独立测试**。

### 两种风格的正面对比

| 维度 | 单文件 (kickstart) | 多文件模块化 |
|------|-------------------|------------|
| 学习曲线 | 低 — 一屏看全 | 中 — 需要理解 `require()` 的模块解析规则 |
| 发现性 | 高 — `grep` 一下就能找到所有相关代码 | 中 — 需要知道哪个文件管什么事 |
| 维护性 | 中 — 修改时要小心不碰相邻 section | 高 — 每文件职责单一 |
| 启动速度 | 几乎相同 | 几乎相同（Lua 模块有缓存） |
| 团队协作 | 低 — 多人改同一个文件易冲突 | 高 — 每人只管自己负责的模块 |
| 调试 | 简单 — 注释掉一个 `do` 块 | 简单 — 注释掉一个 `require()` |

**结论**：二者不是对立关系，而是**演进关系**。从 kickstart 单文件开始，配置变复杂时自然拆分。

### Neovim 的三种官方模块化约定

现代 Neovim 配置有三个被官方文档明确支持的约定目录：

| 目录 | 用途 | 加载时机 |
|------|------|---------|
| `lua/` | 自定义 Lua 模块 | `require('模块名')` 时按需加载 |
| `plugin/` | 启动时自动 source 的 Lua 脚本 | 启动时按字母序自动加载 |
| `lsp/` | LSP 服务器配置文件 | `vim.lsp.enable()` 时自动解析 |
| `after/` | 最后加载的覆盖配置 | 在所有 `plugin/` 之后加载 |

这三种约定是模块化配置的基石，不需要第三方插件管理器支持。

---

## 2. 代码示例

### 模式 1: `lsp/<name>.lua` 配置 LSP

这是 Neovim 0.12 官方推荐的模块化 LSP 配置方式。每个 LSP 一个文件，返回一个 config table：

```lua
-- ~/.config/nvim/lsp/lua_ls.lua
return {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.git' },
  settings = {
    Lua = {
      runtime = { version = 'LuaJIT' },
      completion = { callSnippet = 'Replace' },
      format = { enable = false },
    },
  },
}
```

```lua
-- ~/.config/nvim/lsp/rust_analyzer.lua
return {
  cmd = { 'rust-analyzer' },
  filetypes = { 'rust' },
  root_markers = { 'Cargo.toml' },
  settings = {
    ['rust-analyzer'] = {
      check = { command = 'clippy' },
    },
  },
}
```

```lua
-- init.lua
vim.lsp.enable({ 'lua_ls', 'rust_analyzer' })
```

> [!IMPORTANT]
> `lsp/<name>.lua` 文件必须返回一个 table。`vim.lsp.enable('name')` 会自动在 `runtimepath` 上查找该文件并合并配置。

### 模式 2: `plugin/<name>.lua` 配置插件

`plugin/*.lua` 文件在 Neovim 启动时按字母序自动 source。每个文件通常包含 `vim.pack.add()` + `require(...).setup()`：

```lua
-- ~/.config/nvim/plugin/20-telescope.lua
local gh = function(repo) return 'https://github.com/' .. repo end

vim.pack.add { gh 'nvim-lua/plenary.nvim' }
vim.pack.add { gh 'nvim-telescope/telescope.nvim' }

require('telescope').setup {
  pickers = {
    find_files = { hidden = true },
  },
}

vim.keymap.set('n', '<leader>ff', require('telescope.builtin').find_files, { desc = 'Find files' })
```

```lua
-- ~/.config/nvim/plugin/30-mini.lua
local gh = function(repo) return 'https://github.com/' .. repo end

vim.pack.add { gh 'nvim-mini/mini.nvim' }

require('mini.ai').setup { n_lines = 500 }
require('mini.surround').setup()
require('mini.statusline').setup { use_icons = vim.g.have_nerd_font }
```

**文件名前缀数字控制加载顺序**：`10-options.lua` 在 `20-telescope.lua` 之前加载。这是 Neovim 原生的按字母序 source 行为。

### 模式 3: `lua/` 自定义工具模块

`lua/` 放自己的纯工具函数库，通过 `require()` 使用：

```lua
-- ~/.config/nvim/lua/utils/gh.lua
return function(repo)
  return 'https://github.com/' .. repo
end
```

```lua
-- ~/.config/nvim/lua/utils/helpers.lua
local M = {}

function M.run_build(name, cmd, cwd)
  local result = vim.system(cmd, { cwd = cwd }):wait()
  if result.code ~= 0 then
    vim.notify(
      ('Build failed for %s:\n%s'):format(name, result.stderr or result.stdout or 'No output'),
      vim.log.levels.ERROR
    )
  end
end

function M.map(buf, mode, keys, func, desc)
  vim.keymap.set(mode, keys, func, { buffer = buf, desc = desc })
end

return M
```

```lua
-- ~/.config/nvim/lua/utils/init.lua
return {
  gh = require 'utils.gh',
  helpers = require 'utils.helpers',
}
```

### 模式 4: `after/` 覆盖默认配置

`after/` 目录中的文件在所有 `plugin/` 文件 source 之后加载，适合覆盖插件或 lspconfig 的默认配置：

```lua
-- ~/.config/nvim/after/lsp/lua_ls.lua
return {
  settings = {
    Lua = {
      diagnostics = { globals = { 'vim' } },
    },
  },
}
```

```lua
-- ~/.config/nvim/after/plugin/mini-statusline.lua
local statusline = require 'mini.statusline'
---@diagnostic disable-next-line: duplicate-set-field
statusline.section_location = function()
  return os.date '%H:%M'
end
```

> [!IMPORTANT]
> `after/lsp/lua_ls.lua` 会覆盖 `lsp/lua_ls.lua` 和 lspconfig 提供的默认配置。合并规则是 `vim.tbl_deep_extend('force', ...)`，高优先级覆盖低优先级。

---

## 3. 完整模块化目录结构

```
~/.config/nvim/
├── init.lua                        ← 轻量入口
├── nvim-pack-lock.json             ← vim.pack 锁文件（提交到 Git）
│
├── plugin/                         ← 启动时自动 source
│   ├── 00-globals.lua              ← 全局变量、leader
│   ├── 01-options.lua              ← vim.o / vim.opt
│   ├── 02-keymaps.lua              ← 全局 keymaps
│   ├── 03-autocmds.lua             ← 全局 autocmds
│   ├── 04-diagnostics.lua          ← vim.diagnostic.config
│   ├── 05-pack-hooks.lua           ← PackChanged autocmd
│   ├── 10-ui.lua                   ← colorscheme, gitsigns, which-key, mini.*
│   ├── 20-telescope.lua            ← Telescope + 扩展
│   ├── 30-lsp.lua                  ← mason + vim.lsp.enable 循环
│   ├── 40-formatting.lua           ← conform.nvim
│   ├── 50-completion.lua           ← blink.cmp + LuaSnip
│   └── 60-treesitter.lua           ← nvim-treesitter
│
├── lsp/                            ← LSP 服务器配置（每个 server 一个文件）
│   ├── lua_ls.lua
│   ├── rust_analyzer.lua
│   └── pyright.lua
│
├── lua/                            ← 自定义 Lua 模块
│   └── utils/
│       ├── init.lua
│       ├── gh.lua
│       └── helpers.lua
│
├── after/                          ← 覆盖配置
│   ├── lsp/
│   │   └── lua_ls.lua              ← 覆盖 lua_ls 默认
│   └── plugin/
│       └── mini-statusline.lua     ← 覆盖 statusline 组件
│
└── snippets/                       ← 自定义 snippets（可选）
    └── lua.json
```

**加载顺序**：`init.lua` → `plugin/*.lua`（按字母序） → `lsp/*.lua`（按需） → `after/plugin/*.lua` / `after/lsp/*.lua`。

---

## 4. 从 kickstart 单文件迁移到模块化（实战）

### 迁移规则

```
kickstart 单文件                    模块化
─────────────────────────────────────────────
do                                  文件
  -- Section 1: OPTIONS             ├── plugin/01-options.lua
  vim.o.number = true               ├── plugin/02-keymaps.lua
  vim.keymap.set(...)               ├── plugin/03-autocmds.lua
  ...                               ├── plugin/04-diagnostics.lua
end                                 └── plugin/00-globals.lua

do                                  plugin/05-pack-hooks.lua
  -- Section 2: BUILD HOOKS         lua/utils/helpers.lua
  ...                               lua/utils/gh.lua
end

do                                  plugin/10-ui.lua
  -- Section 3: UI                  plugin/20-telescope.lua
  ...                               plugin/30-lsp.lua
end                                 plugin/40-formatting.lua
...（类推）                          plugin/50-completion.lua
                                    plugin/60-treesitter.lua
                                    lsp/lua_ls.lua
                                    lsp/rust_analyzer.lua
```

### 步骤 1: 创建 `plugin/01-options.lua`

从 kickstart Section 1 中提取所有 `vim.o` / `vim.opt` 赋值：

```lua
-- ~/.config/nvim/plugin/01-options.lua
vim.o.number = true
vim.o.mouse = 'a'
vim.o.showmode = false
vim.o.cursorline = true
vim.o.signcolumn = 'yes'
vim.o.scrolloff = 10
vim.o.breakindent = true
vim.o.undofile = true
vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.splitright = true
vim.o.splitbelow = true
vim.o.inccommand = 'split'
vim.o.updatetime = 250
vim.o.timeoutlen = 300
vim.o.confirm = true
vim.o.list = true
vim.opt.listchars = { tab = '» ', trail = '·', nbsp = '␣' }

vim.schedule(function()
  vim.o.clipboard = 'unnamedplus'
end)
```

### 步骤 2: 创建 `plugin/02-keymaps.lua`

```lua
-- ~/.config/nvim/plugin/02-keymaps.lua
vim.keymap.set('n', '<Esc>', '<cmd>nohlsearch<cr>')
vim.keymap.set('n', '<C-h>', '<C-w><C-h>', { desc = 'Left window' })
vim.keymap.set('n', '<C-l>', '<C-w><C-l>', { desc = 'Right window' })
vim.keymap.set('n', '<C-j>', '<C-w><C-j>', { desc = 'Lower window' })
vim.keymap.set('n', '<C-k>', '<C-w><C-k>', { desc = 'Upper window' })
vim.keymap.set('t', '<Esc><Esc>', '<C-\\><C-n>', { desc = 'Exit terminal mode' })
vim.keymap.set('n', '<leader>q', vim.diagnostic.setloclist, { desc = 'Diagnostic quickfix' })
```

### 步骤 3: 创建 `plugin/03-autocmds.lua`

```lua
-- ~/.config/nvim/plugin/03-autocmds.lua
vim.api.nvim_create_autocmd('TextYankPost', {
  desc = 'Highlight on yank',
  group = vim.api.nvim_create_augroup('highlight-yank', { clear = true }),
  callback = function() vim.hl.on_yank() end,
})
```

### 步骤 4: 创建 `plugin/04-diagnostics.lua`

```lua
-- ~/.config/nvim/plugin/04-diagnostics.lua
vim.diagnostic.config {
  update_in_insert = false,
  severity_sort = true,
  float = { border = 'rounded', source = 'if_many' },
  underline = { severity = { min = vim.diagnostic.severity.WARN } },
  virtual_text = true,
  virtual_lines = false,
  jump = {
    on_jump = function(_, bufnr)
      vim.diagnostic.open_float { bufnr = bufnr, scope = 'cursor', focus = false }
    end,
  },
}
```

### 步骤 5: 创建 `plugin/05-pack-hooks.lua`

```lua
-- ~/.config/nvim/plugin/05-pack-hooks.lua
local function run_build(name, cmd, cwd)
  local result = vim.system(cmd, { cwd = cwd }):wait()
  if result.code ~= 0 then
    vim.notify(
      ('Build failed for %s:\n%s'):format(name, result.stderr or result.stdout or 'No output'),
      vim.log.levels.ERROR
    )
  end
end

vim.api.nvim_create_autocmd('PackChanged', {
  callback = function(ev)
    local name, kind, path = ev.data.spec.name, ev.data.kind, ev.data.path
    if kind ~= 'install' and kind ~= 'update' then return end

    if name == 'telescope-fzf-native.nvim' and vim.fn.executable 'make' == 1 then
      run_build(name, { 'make' }, path)
    elseif name == 'LuaSnip' and vim.fn.has 'win32' ~= 1 and vim.fn.executable 'make' == 1 then
      run_build(name, { 'make', 'install_jsregexp' }, path)
    elseif name == 'nvim-treesitter' then
      if not ev.data.active then vim.cmd.packadd 'nvim-treesitter' end
      vim.cmd 'TSUpdate'
    end
  end,
})
```

### 步骤 6: 创建 `plugin/20-telescope.lua`

```lua
-- ~/.config/nvim/plugin/20-telescope.lua
local gh = require('utils.gh')
local builtin = require 'telescope.builtin'

vim.pack.add { gh 'nvim-lua/plenary.nvim' }
vim.pack.add { gh 'nvim-telescope/telescope.nvim' }

require('telescope').setup {
  pickers = {
    find_files = { hidden = true },
    buffers = { sort_lastused = true, theme = 'dropdown', previewer = false },
  },
}

if vim.fn.executable 'make' == 1 then
  vim.pack.add { gh 'nvim-telescope/telescope-fzf-native.nvim' }
  pcall(require('telescope').load_extension, 'fzf')
end

vim.pack.add { gh 'nvim-telescope/telescope-ui-select.nvim' }
pcall(require('telescope').load_extension, 'ui-select')

vim.keymap.set('n', '<leader>ff', builtin.find_files, { desc = 'Find files' })
vim.keymap.set('n', '<leader>fg', builtin.live_grep, { desc = 'Live grep' })
vim.keymap.set('n', '<leader>fb', builtin.buffers, { desc = 'Buffers' })
```

### 步骤 7: 创建 `lsp/lua_ls.lua`

```lua
-- ~/.config/nvim/lsp/lua_ls.lua
return {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.git' },
  settings = {
    Lua = {
      runtime = { version = 'LuaJIT' },
      completion = { callSnippet = 'Replace' },
      format = { enable = false },
    },
  },
}
```

### 步骤 8: 创建 `plugin/30-lsp.lua`

```lua
-- ~/.config/nvim/plugin/30-lsp.lua
local gh = require('utils.gh')

vim.pack.add {
  gh 'neovim/nvim-lspconfig',
  gh 'mason-org/mason.nvim',
  gh 'mason-org/mason-lspconfig.nvim',
  gh 'WhoIsSethDaniel/mason-tool-installer.nvim',
}

require('mason').setup {}

-- 这里列出你想通过 mason 管理的 server
local servers = { 'lua_ls' }
require('mason-tool-installer').setup { ensure_installed = servers }

-- 启用所有 lsp/*.lua 中定义的服务器
vim.lsp.enable(servers)
```

### 步骤 9: 重写 `init.lua`

```lua
-- ~/.config/nvim/init.lua
vim.loader.enable()

-- 全局变量（必须在 plugin/ 加载之前）
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '
vim.g.have_nerd_font = false

-- plugin/*.lua 会自动 source，无需手动 require
```

> [!IMPORTANT]
> `init.lua` 只保留 `vim.loader.enable()`、leader、必要的全局变量。所有配置交给 `plugin/*.lua` 自动加载。这与把配置集中放在 `lua/config/` 再手动 `require()` 的方案不同——两种方式都正确，选择其一保持统一即可。

---

## 5. 何时模块化、何时保持单文件

### 保持单文件更好

- 配置 < 1000 行；
- 主要目标是学习和快速迭代；
- 经常跟随 kickstart 上游同步；
- 只有一个人在维护。

### 模块化更好

- 配置 > 1500 行；
- 需要为多种语言维护复杂的 LSP/formatter 配置；
- 多人协作，需要减少合并冲突；
- 希望按功能独立启用/禁用模块；
- 想利用 `lsp/<name>.lua` 的官方推荐模式。

### 混合方案

最实用的做法往往是**主体模块化 + 关键入口保留简洁**：

```
init.lua              ← 50 行：loader、leader、require 核心模块
lua/config/*.lua      ← options/keymaps/autocmds/diagnostics
lua/plugins/*.lua     ← 每个 plugin 一个文件
lsp/*.lua             ← 每个 LSP 一个文件
```

这样既有模块化的维护性，又保留了显式的加载顺序控制。

---

## 6. 练习

### 练习 1: 手拆 kickstart

把 kickstart.nvim 的 `init.lua` 按上述 9 个步骤拆分为模块化结构。目标输出：

```
plugin/00-globals.lua
plugin/01-options.lua
plugin/02-keymaps.lua
plugin/03-autocmds.lua
plugin/04-diagnostics.lua
plugin/05-pack-hooks.lua
plugin/10-ui.lua
plugin/20-telescope.lua
plugin/30-lsp.lua
plugin/40-formatting.lua
plugin/50-completion.lua
plugin/60-treesitter.lua
lsp/lua_ls.lua
lua/utils/gh.lua
lua/utils/helpers.lua
```

### 练习 2: 创建 `lsp/<name>.lua`

为你常用的一种编程语言（如 Python 的 `pyright` 或 Rust 的 `rust_analyzer`）创建一个 `lsp/<name>.lua` 文件，并在 `plugin/30-lsp.lua` 中 `vim.lsp.enable()` 它。

### 练习 3: 使用 `after/` 覆盖

在 `after/lsp/lua_ls.lua` 中添加 `diagnostics.globals = { 'vim' }`，验证它确实覆盖了 `lsp/lua_ls.lua` 中的同名设置。

### 练习 4: 设计你自己的目录结构

根据你的使用习惯，设计一个不同于标准方案的目录结构：
- 你会把 LSP 配置放在 `/lsp/` 而不是 `/plugins/` 吗？
- 你会按语言拆分（`/lang/rust.lua`, `/lang/python.lua`）吗？
- 你的 `after/` 目录会放什么？为什么？

---

## 6.5 参考答案

> [!tip]- 练习 1 参考答案
> 迁移时的关键检查点：
>
> 1. **`plugin/00-globals.lua`** 必须在最前面，设置 `mapleader` / `maplocalleader` / `have_nerd_font`。
> 2. **`plugin/01-options.lua`** 只放 `vim.o` / `vim.opt` 赋值，不写 keymaps。
> 3. **`plugin/02-keymaps.lua`** 只放全局 `vim.keymap.set()`，LSP buffer-local 映射留在 `plugin/30-lsp.lua` 的 LspAttach 中。
> 4. **`plugin/05-pack-hooks.lua`** 中的 `PackChanged` autocmd 必须在第一次 `vim.pack.add()` 之前注册。
> 5. **`plugin/10-ui.lua`** 中 colorscheme 必须放在该文件最前面。
> 6. **`plugin/20-telescope.lua`** 中 `pcall(require('telescope').load_extension, 'fzf')` 确保无 fzf-native 时不报错。
> 7. **`lsp/lua_ls.lua`** 必须返回 table，不要直接调用 `vim.lsp.config()`。
> 8. **`plugin/30-lsp.lua`** 调用 `vim.lsp.enable(servers)`，而不是在每个 `lsp/*.lua` 中调用。

> [!tip]- 练习 2 参考答案
> 以 pyright 为例：
>
> ```lua
> -- ~/.config/nvim/lsp/pyright.lua
> return {
>   cmd = { 'pyright-langserver', '--stdio' },
>   filetypes = { 'python' },
>   root_markers = { 'pyproject.toml', 'setup.py', '.git' },
>   settings = {
>     python = {
>       analysis = {
>         typeCheckingMode = 'basic',
>         autoSearchPaths = true,
>       },
>     },
>   },
> }
> ```
>
> 在 `plugin/30-lsp.lua` 中：
>
> ```lua
> local servers = { 'lua_ls', 'pyright' }
> require('mason-tool-installer').setup { ensure_installed = servers }
> vim.lsp.enable(servers)
> ```

> [!tip]- 练习 3 参考答案
> 创建 `after/lsp/lua_ls.lua`：
>
> ```lua
> return {
>   settings = {
>     Lua = {
>       diagnostics = {
>         globals = { 'vim' },
>       },
>     },
>   },
> }
> ```
>
> 验证方法：打开一个 Lua 文件，检查 `vim` 不再被标记为未定义全局变量。可用 `:lua print(vim.inspect(vim.lsp.config('lua_ls')))` 查看合并后的完整配置。

> [!tip]- 练习 4 参考答案
> **方案 A: 按语言拆分（适合多语言用户）**
>
> ```
> lua/
> ├── config/
> │   ├── options.lua
> │   ├── keymaps.lua
> │   └── autocmds.lua
> ├── lang/                 ← 按语言组织
> │   ├── init.lua          ← 聚合 require
> │   ├── lua.lua
> │   ├── python.lua
> │   └── rust.lua
> └── plugins/
>     ├── ui.lua
>     ├── search.lua
>     ├── formatting.lua
>     └── completion.lua
> ```
>
> **优点**：添加新语言时只改一个文件。**缺点**：`lang/init.lua` 要负责汇总所有 server 名称传给 mason。
>
> **方案 B: 标准方案 + after/ 覆盖（适合 fork kickstart 同步上游）**
>
> ```
> lua/
> ├── config/    (标准)
> ├── plugins/   (标准)
> └── utils/     (标准)
> after/
> └── plugin/
>     ├── mini-statusline.lua
>     └── custom-keymaps.lua
> ```
>
> **优点**：核心配置与 kickstart 差异最小，方便同步上游。**缺点**：调试时需要记住 `after/` 中的覆盖。
>
> **选择建议**：
> - 频繁配置多种语言 → 方案 A
> - fork kickstart 并想同步上游 → 方案 B
> - 新手或个人配置 → 本教程标准方案

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 7. 扩展阅读

- [Neovim Lua Guide — Modules](https://neovim.io/doc/user/lua-guide.html#lua-guide-modules)
- [`:help lua-require`](https://neovim.io/doc/user/lua.html#lua-require) — `require()` 的路径解析规则
- [`:help 'rtp'`](https://neovim.io/doc/user/options.html#'rtp') — runtimepath 的加载顺序
- [`:help vim.lsp.config()`](https://neovim.io/doc/user/lsp.html#vim.lsp.config) — `lsp/*.lua` 配置模式
- [LazyVim 目录结构](https://github.com/LazyVim/LazyVim) — 大型配置的组织参考
- [NvChad 目录结构](https://github.com/NvChad/NvChad) — 另一种风格的大型配置

---

## 常见陷阱

- **`require()` 路径区分大小写**：`require('config.Options')` 在 Linux 上找不到 `options.lua`。始终用小写文件名。
- **循环 require**：`plugins.lua` require `lsp.lua`，而 `lsp.lua` 又 require `plugins.lua` → 报错。保持单向依赖。
- **模块文件中的副作用顺序**：A 模块调用 `vim.pack.add()`，B 模块立即调用 `require('某个插件').setup()`。如果 A 还没执行完，B 会失败。用文件名前缀数字或显式 `require()` 控制顺序。
- **`lsp/*.lua` 必须返回 table**：如果写成了直接 `vim.lsp.config(...)` 调用，`vim.lsp.enable()` 找不到配置。
- **`after/` 加载时机**：`after/plugin/*.lua` 在所有 `plugin/*.lua` 之后加载。用它覆盖插件设置，而不是修改插件源码。
- **过度拆分**：把一行 `vim.o.number = true` 拆成独立文件是对模块化的误解。保持每个文件至少 20-30 行有意义的配置。
- **忘记提交 `nvim-pack-lock.json`**：锁文件是配置可重现的关键，必须纳入版本控制。
