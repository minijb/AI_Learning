# 16 — 综合实战：从零搭建 Neovim 0.12 配置 (单文件 + 模块化)

> 所属计划: Neovim + Lua 配置实战 (现代版)
> 预计耗时: 120 分钟（含 90 分钟单文件 + 30 分钟拆分为模块化）
> 前置知识: 14-kickstart-architecture（单文件架构）、**15-modular-config（模块化架构）**

---

## 1. 目标

在本节中，你将**从零开始**，搭建一套完整的 Neovim 配置，并掌握两种组织方式：

- **阶段 A: 单文件 init.lua**（kickstart 风格，~300 行精华版）
- **阶段 B: 模块化拆分**（把单文件拆成 `lua/config/` + `lua/plugins/` 的标准结构）

内容包括：

- 单文件 init.lua 骨架（do 块分区）→ 模块化 `lua/config/` + `lua/plugins/` 目录
- `vim.pack` 插件管理（含 `PackChanged` 构建钩子）
- 基础选项 + 按键映射 + 自动命令
- LSP（`vim.lsp.config` / `vim.lsp.enable`） + Mason 自动安装
- blink.cmp 补全 + LuaSnip
- Treesitter 按需安装
- Telescope 模糊查找
- 配色方案 + mini.statusline
- Telescope 模糊查找
- 配色方案 + mini.statusline

> [!NOTE]
> 下面的完整代码**不是让你复制粘贴的**——是参考目标。建议先尝试自己写，遇到困难再看参考。

---

## 2. 参考架构

```
~/.config/nvim/
├── init.lua                  ← 单一入口文件（~300 行精华版）
└── nvim-pack-lock.json       ← vim.pack 锁文件（自动生成，提交到 Git）
```

---

## 3. 参考实现

### init.lua（kicksart 精华版，~300 行）

```lua
-- ==================================================================
-- FOUNDATION
-- ==================================================================
do
  vim.loader.enable()
  vim.g.mapleader = ' '
  vim.g.maplocalleader = ' '
  vim.g.have_nerd_font = false

  -- Options
  vim.o.number = true
  vim.o.mouse = 'a'
  vim.o.showmode = false
  vim.schedule(function() vim.o.clipboard = 'unnamedplus' end)
  vim.o.breakindent = true
  vim.o.undofile = true
  vim.o.ignorecase = true
  vim.o.smartcase = true
  vim.o.signcolumn = 'yes'
  vim.o.updatetime = 250
  vim.o.timeoutlen = 300
  vim.o.splitright = true
  vim.o.splitbelow = true
  vim.o.inccommand = 'split'
  vim.o.cursorline = true
  vim.o.scrolloff = 10
  vim.o.confirm = true

  -- Keymaps
  vim.keymap.set('n', '<Esc>', '<cmd>nohlsearch<CR>')
  vim.keymap.set('n', '<C-h>', '<C-w><C-h>', { desc = 'Left window' })
  vim.keymap.set('n', '<C-l>', '<C-w><C-l>', { desc = 'Right window' })
  vim.keymap.set('n', '<C-j>', '<C-w><C-j>', { desc = 'Lower window' })
  vim.keymap.set('n', '<C-k>', '<C-w><C-k>', { desc = 'Upper window' })
  vim.keymap.set('t', '<Esc><Esc>', '<C-\\><C-n>', { desc = 'Exit terminal mode' })

  -- Diagnostics
  vim.diagnostic.config {
    update_in_insert = false,
    severity_sort = true,
    float = { border = 'rounded', source = 'if_many' },
    virtual_text = true,
    jump = {
      on_jump = function(_, bufnr)
        vim.diagnostic.open_float { bufnr = bufnr, scope = 'cursor', focus = false }
      end,
    },
  }
  vim.keymap.set('n', '<leader>q', vim.diagnostic.setloclist, { desc = 'Diagnostic quickfix' })

  -- Yank highlight
  vim.api.nvim_create_autocmd('TextYankPost', {
    desc = 'Highlight on yank',
    group = vim.api.nvim_create_augroup('highlight-yank', { clear = true }),
    callback = function() vim.hl.on_yank() end,
  })
end

-- ==================================================================
-- HELPERS
-- ==================================================================
local function gh(repo) return 'https://github.com/' .. repo end

local function run_build(name, cmd, cwd)
  local result = vim.system(cmd, { cwd = cwd }):wait()
  if result.code ~= 0 then
    vim.notify(('Build failed for %s: %s'):format(name, result.stderr or ''), vim.log.levels.ERROR)
  end
end

do
  vim.api.nvim_create_autocmd('PackChanged', {
    callback = function(ev)
      local name = ev.data.spec.name
      if ev.data.kind ~= 'install' and ev.data.kind ~= 'update' then return end
      if name == 'telescope-fzf-native.nvim' and vim.fn.executable 'make' == 1 then
        run_build(name, { 'make' }, ev.data.path)
      elseif name == 'nvim-treesitter' then
        if not ev.data.active then vim.cmd.packadd 'nvim-treesitter' end
        vim.cmd 'TSUpdate'
      end
    end,
  })
end

-- ==================================================================
-- UI
-- ==================================================================
do
  -- Colorscheme
  vim.pack.add { gh 'folke/tokyonight.nvim' }
  require('tokyonight').setup { styles = { comments = { italic = false } } }
  vim.cmd.colorscheme 'tokyonight-night'

  -- Gitsigns
  vim.pack.add { gh 'lewis6991/gitsigns.nvim' }
  require('gitsigns').setup {
    signs = { add = { text = '+' }, change = { text = '~' }, delete = { text = '_' } },
  }

  -- which-key
  vim.pack.add { gh 'folke/which-key.nvim' }
  require('which-key').setup {
    delay = 0,
    spec = {
      { '<leader>s', group = '[S]earch', mode = { 'n', 'v' } },
      { '<leader>t', group = '[T]oggle' },
    },
  }

  -- mini.nvim: ai, surround, statusline
  vim.pack.add { gh 'nvim-mini/mini.nvim' }
  require('mini.ai').setup { n_lines = 500 }
  require('mini.surround').setup()
  local statusline = require 'mini.statusline'
  statusline.setup { use_icons = vim.g.have_nerd_font }
  ---@diagnostic disable-next-line: duplicate-set-field
  statusline.section_location = function() return '%2l:%-2v' end
end

-- ==================================================================
-- SEARCH & NAVIGATION
-- ==================================================================
do
  vim.pack.add { gh 'nvim-lua/plenary.nvim', gh 'nvim-telescope/telescope.nvim', gh 'nvim-telescope/telescope-ui-select.nvim' }
  require('telescope').setup {
    extensions = { ['ui-select'] = { require('telescope.themes').get_dropdown() } },
  }
  pcall(require('telescope').load_extension, 'ui-select')

  local builtin = require 'telescope.builtin'
  vim.keymap.set('n', '<leader>sh', builtin.help_tags, { desc = '[S]earch [H]elp' })
  vim.keymap.set('n', '<leader>sf', builtin.find_files, { desc = '[S]earch [F]iles' })
  vim.keymap.set('n', '<leader>sg', builtin.live_grep, { desc = '[S]earch by [G]rep' })
  vim.keymap.set('n', '<leader>sd', builtin.diagnostics, { desc = '[S]earch [D]iagnostics' })
  vim.keymap.set('n', '<leader><leader>', builtin.buffers, { desc = 'Find buffers' })

  -- LSP pickers
  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('telescope-lsp', { clear = true }),
    callback = function(ev)
      local b = ev.buf
      vim.keymap.set('n', 'grr', builtin.lsp_references, { buffer = b, desc = 'References' })
      vim.keymap.set('n', 'gri', builtin.lsp_implementations, { buffer = b, desc = 'Implementation' })
      vim.keymap.set('n', 'grd', builtin.lsp_definitions, { buffer = b, desc = 'Definition' })
    end,
  })
end

-- ==================================================================
-- LSP
-- ==================================================================
do
  vim.pack.add { gh 'j-hui/fidget.nvim' }
  require('fidget').setup {}

  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('lsp-attach', { clear = true }),
    callback = function(ev)
      local map = function(keys, func, desc, mode)
        vim.keymap.set(mode or 'n', keys, func, { buffer = ev.buf, desc = 'LSP: ' .. desc })
      end
      map('grn', vim.lsp.buf.rename, '[R]e[n]ame')
      map('gra', vim.lsp.buf.code_action, 'Code [A]ction', { 'n', 'x' })
      map('grD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')

      local client = vim.lsp.get_client_by_id(ev.data.client_id)
      if client and client:supports_method('textDocument/documentHighlight', ev.buf) then
        local aug = vim.api.nvim_create_augroup('lsp-highlight-' .. ev.buf, { clear = true })
        vim.api.nvim_create_autocmd({ 'CursorHold', 'CursorHoldI' }, { buffer = ev.buf, group = aug, callback = vim.lsp.buf.document_highlight })
        vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, { buffer = ev.buf, group = aug, callback = vim.lsp.buf.clear_references })
      end

      if client and client:supports_method('textDocument/inlayHint', ev.buf) then
        map('<leader>th', function() vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = ev.buf }) end, '[T]oggle Inlay [H]ints')
      end
    end,
  })

  local servers = {
    stylua = {},
    lua_ls = {
      on_init = function(client)
        client.server_capabilities.documentFormattingProvider = false
      end,
      settings = { Lua = { format = { enable = false } } },
    },
    -- 添加你的语言:
    -- clangd = {},
    -- pyright = {},
    -- rust_analyzer = {},
  }

  vim.pack.add { gh 'neovim/nvim-lspconfig', gh 'mason-org/mason.nvim', gh 'mason-org/mason-lspconfig.nvim', gh 'WhoIsSethDaniel/mason-tool-installer.nvim' }
  require('mason').setup {}
  local ensure_installed = vim.tbl_keys(servers or {})
  require('mason-tool-installer').setup { ensure_installed = ensure_installed }

  for name, server in pairs(servers) do
    vim.lsp.config(name, server)
    vim.lsp.enable(name)
  end
end

-- ==================================================================
-- FORMATTING
-- ==================================================================
do
  vim.pack.add { gh 'stevearc/conform.nvim' }
  require('conform').setup {
    notify_on_error = false,
    default_format_opts = { lsp_format = 'fallback' },
  }
  vim.keymap.set({ 'n', 'v' }, '<leader>f', function() require('conform').format { async = true } end, { desc = '[F]ormat buffer' })
end

-- ==================================================================
-- AUTOCOMPLETE & SNIPPETS
-- ==================================================================
do
  vim.pack.add { { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' } }
  require('luasnip').setup {}

  vim.pack.add { { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' } }
  require('blink.cmp').setup {
    keymap = { preset = 'default' },
    appearance = { nerd_font_variant = 'mono' },
    completion = { documentation = { auto_show = false } },
    sources = { default = { 'lsp', 'path', 'snippets' } },
    snippets = { preset = 'luasnip' },
    fuzzy = { implementation = 'lua' },
    signature = { enabled = true },
  }
end

-- ==================================================================
-- TREESITTER
-- ==================================================================
do
  vim.pack.add { { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' } }

  local parsers = { 'bash', 'c', 'diff', 'html', 'lua', 'luadoc', 'markdown', 'markdown_inline', 'query', 'vim', 'vimdoc' }
  require('nvim-treesitter').install(parsers)

  local function treesitter_try_attach(buf, language)
    if not vim.treesitter.language.add(language) then return end
    vim.treesitter.start(buf, language)
    local has_indent_query = vim.treesitter.query.get(language, 'indents') ~= nil
    if has_indent_query then vim.bo.indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()" end
  end

  local available = require('nvim-treesitter').get_available()
  vim.api.nvim_create_autocmd('FileType', {
    callback = function(args)
      local language = vim.treesitter.language.get_lang(args.match)
      if not language then return end
      local installed = require('nvim-treesitter').get_installed 'parsers'
      if vim.tbl_contains(installed, language) then
        treesitter_try_attach(args.buf, language)
      elseif vim.tbl_contains(available, language) then
        require('nvim-treesitter').install(language):await(function()
          treesitter_try_attach(args.buf, language)
        end)
      end
    end,
  })
end

-- vim: ts=2 sts=2 sw=2 et
```

---

## 4. 操作步骤

### 第一步：备份并清空

```bash
mv ~/.config/nvim ~/.config/nvim.bak
mkdir ~/.config/nvim
```

### 第二步：创建 init.lua

将上述参考实现写入 `~/.config/nvim/init.lua`。

### 第三步：启动 Neovim

```bash
nvim
```

首次启动：
1. `vim.pack.add()` 弹出确认对话框 → 按 `a` 允许全部
2. 插件自动下载到 `~/.local/share/nvim/site/pack/core/opt/`
3. `PackChanged` 触发 treesitter parser 编译
4. mason 异步安装 `lua_ls` 和 `stylua`

### 第四步：验证核心功能

启动完成后，逐个验证：

| 功能 | 验证方式 |
|------|---------|
| Colorscheme | 应该看到 tokyonight-night 配色 |
| Statusline | 底部有 LINE:COLUMN 显示 |
| 按键提示 | 按 `<leader>` 等待，应出现 which-key 弹出 |
| Telescope | `<leader>sf` → 打开文件查找器 |
| LSP | 打开 `.lua` 文件，`:checkhealth vim.lsp` |
| 补全 | 输入 `vim.` 等待 blink.cmp 弹出 |
| Treesitter | 打开 `.lua` 文件，观察语法高亮的细粒度 |
| Git 标记 | 在 Git 仓库中修改文件，观察 gutter 标记 |

### 第五步：个性化

1. 在 `servers` 表中添加你常用语言的 LSP
2. 在 `parsers` 表中添加你需要的 treesitter parser
3. 修改 keymaps 适配你的习惯
4. 如果你有 Nerd Font，设置 `vim.g.have_nerd_font = true`
5. 将 `nvim-pack-lock.json` 添加到 Git

---

## 5. 练习

### 练习 1: 添加一个自定义插件

在 UI section 中添加 `todo-comments.nvim`：

```lua
vim.pack.add { gh 'folke/todo-comments.nvim' }
require('todo-comments').setup { signs = false }
```

重启后在一个文件中写下 `TODO: 完成这个函数`（大写 TODO），观察高亮效果。

### 练习 2: 配置 formatter

在 conform setup 中添加自动格式化：

```lua
format_on_save = function(bufnr)
  if vim.bo[bufnr].filetype == 'lua' then
    return { timeout_ms = 500 }
  end
end,
```

保存一个 Lua 文件，观察是否自动格式化。

### 练习 3: 将配置拆分为模块化

当 `init.lua` 超过 500 行时，尝试拆分。例如把 LSP section 提取为 `lua/config/lsp.lua`：

```lua
-- init.lua 中:
require 'config.lsp'

-- lua/config/lsp.lua:
return (function()
  -- ... 所有 LSP 相关代码 ...
end)()
```

---

## 6. 扩展阅读

- [kickstart.nvim 完整仓库](https://github.com/nvim-lua/kickstart.nvim)
- [A Guide to vim.pack](https://echasnovski.com/blog/2026-03-13-a-guide-to-vim-pack)
- [Neovim 0.12 更新日志](https://neovim.io/doc/user/news-0.12/)
