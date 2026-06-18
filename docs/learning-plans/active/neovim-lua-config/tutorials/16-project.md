---
title: "16 — 综合实战：从零搭建 Neovim 0.12 配置 (单文件 + 模块化)"
updated: 2026-06-18
---

# 16 — 综合实战：从零搭建 Neovim 0.12 配置 (单文件 + 模块化)

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 150 分钟（单文件 90 分钟 + 模块化拆分 60 分钟）
> 前置知识: [[14-kickstart-architecture]]、[[15-modular-config]]、[[20-dap-debugging]]、[[21-performance-troubleshooting]]

---

## 1. 目标

在本节中，你将**从零开始**搭建一套覆盖编辑、LSP、补全、格式化、lint、调试、搜索的完整 Neovim 配置，并掌握两种组织方式：

- **阶段 A：单文件 `init.lua`**（kickstart 风格，~330 行精华版）
- **阶段 B：模块化拆分**（`lua/config/` + `lua/plugins/` + `lua/utils/` 标准结构）

本节新增并整合了：

- `vim.loader.enable()` 第一行启动加速
- 完整 diagnostic 配置（`virtual_lines`、`jump.on_jump`）
- `conform.nvim` 格式化 + `format_on_save`
- `nvim-lint` 异步 linter
- `nvim-dap` + `nvim-dap-ui` 调试（F5/F10/F11/F12、`<leader>db`）
- 0.12 默认 LSP 按键意识（只补充默认不提供的映射）

> [!NOTE]
> 下面的完整代码**不是让你直接复制粘贴的**——是参考目标。建议先尝试自己写，遇到困难再看参考。

---

## 2. 两种架构对照

| 特性 | 单文件 `init.lua` | 模块化 |
|---|---|---|
| 学习曲线 | 低 | 中 |
| 定位问题 | 顺序阅读 | 按文件职责查找 |
| 适合规模 | < 800 行 | > 500 行 |
| 团队协作 | 易冲突 | 易分工 |
| 执行顺序 | 从上到下 | `init.lua` 中 `require()` 顺序 |

**结论**：从 kickstart 单文件开始，配置超过一个屏幕装不下时，自然拆成模块化。

---

## 3. 阶段 A：单文件 init.lua

### 目录结构

```text
~/.config/nvim/
├── init.lua                  ← 单一入口文件（~330 行）
└── nvim-pack-lock.json       ← vim.pack 锁文件（自动生成，提交到 Git）
```

### 完整 init.lua

```lua
-- 启动加速：必须放在第一行
vim.loader.enable()
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '
vim.g.have_nerd_font = false
-- Section: FOUNDATION
do
  vim.o.number = true
  vim.o.mouse = 'a'
  vim.o.showmode = false
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
  vim.schedule(function() vim.o.clipboard = 'unnamedplus' end)
  vim.keymap.set('n', '<Esc>', '<cmd>nohlsearch<CR>')
  vim.keymap.set('n', '<C-h>', '<C-w><C-h>')
  vim.keymap.set('n', '<C-l>', '<C-w><C-l>')
  vim.keymap.set('n', '<C-j>', '<C-w><C-j>')
  vim.keymap.set('n', '<C-k>', '<C-w><C-k>')
  vim.keymap.set('t', '<Esc><Esc>', '<C-\\><C-n>')
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
  vim.keymap.set('n', '<leader>q', vim.diagnostic.setloclist)
  vim.api.nvim_create_autocmd('TextYankPost', {
    group = vim.api.nvim_create_augroup('highlight-yank', { clear = true }),
    callback = function() vim.hl.on_yank() end,
  })
end
-- Section: HELPERS
local function gh(repo) return 'https://github.com/' .. repo end
local function run_build(name, cmd, cwd)
  local result = vim.system(cmd, { cwd = cwd }):wait()
  if result.code ~= 0 then
    vim.notify(('Build failed for %s:\n%s'):format(name, result.stderr or result.stdout or 'No output'),
      vim.log.levels.ERROR)
  end
end
vim.api.nvim_create_autocmd('PackChanged', {
  callback = function(ev)
    local name, kind = ev.data.spec.name, ev.data.kind
    if kind ~= 'install' and kind ~= 'update' then return end
    if name == 'telescope-fzf-native.nvim' and vim.fn.executable 'make' == 1 then
      run_build(name, { 'make' }, ev.data.path)
    elseif name == 'nvim-treesitter' then
      if not ev.data.active then vim.cmd.packadd 'nvim-treesitter' end
      vim.cmd 'TSUpdate'
    elseif name == 'LuaSnip' and vim.fn.has 'win32' ~= 1 and vim.fn.executable 'make' == 1 then
      run_build(name, { 'make', 'install_jsregexp' }, ev.data.path)
    end
  end,
})
-- Section: UI
do
  vim.pack.add { gh 'folke/tokyonight.nvim' }
  require('tokyonight').setup { styles = { comments = { italic = false } } }
  vim.cmd.colorscheme 'tokyonight-night'
  vim.pack.add { gh 'lewis6991/gitsigns.nvim' }
  require('gitsigns').setup {
    signs = { add = { text = '+' }, change = { text = '~' }, delete = { text = '_' } },
  }
  vim.pack.add { gh 'folke/which-key.nvim' }
  require('which-key').setup {
    delay = 0,
    spec = {
      { '<leader>s', group = '[S]earch' },
      { '<leader>t', group = '[T]oggle' },
      { '<leader>d', group = '[D]ebug' },
    },
  }
  vim.pack.add { gh 'nvim-mini/mini.nvim' }
  require('mini.ai').setup { mappings = { around_next = 'aa', inside_next = 'ii' }, n_lines = 500 }
  require('mini.surround').setup()
  local statusline = require 'mini.statusline'
  statusline.setup { use_icons = vim.g.have_nerd_font }
  statusline.section_location = function() return '%2l:%-2v' end
end
-- Section: SEARCH & NAVIGATION
do
  vim.pack.add { gh 'nvim-lua/plenary.nvim', gh 'nvim-telescope/telescope.nvim', gh 'nvim-telescope/telescope-ui-select.nvim', gh 'nvim-telescope/telescope-fzf-native.nvim' }
  require('telescope').setup {
    extensions = { ['ui-select'] = { require('telescope.themes').get_dropdown() } },
  }
  pcall(require('telescope').load_extension, 'ui-select')
  pcall(require('telescope').load_extension, 'fzf')
  local builtin = require 'telescope.builtin'
  vim.keymap.set('n', '<leader>sh', builtin.help_tags)
  vim.keymap.set('n', '<leader>sf', builtin.find_files)
  vim.keymap.set('n', '<leader>sg', builtin.live_grep)
  vim.keymap.set('n', '<leader>sd', builtin.diagnostics)
  vim.keymap.set('n', '<leader><leader>', builtin.buffers)
  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('telescope-lsp', { clear = true }),
    callback = function(ev)
      local b = ev.buf
      vim.keymap.set('n', 'grr', builtin.lsp_references, { buffer = b })
      vim.keymap.set('n', 'gri', builtin.lsp_implementations, { buffer = b })
      vim.keymap.set('n', 'grd', builtin.lsp_definitions, { buffer = b })
      vim.keymap.set('n', 'gO', builtin.lsp_document_symbols, { buffer = b })
    end,
  })
end
-- Section: LSP
do
  vim.pack.add { gh 'j-hui/fidget.nvim' }
  require('fidget').setup {}
  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('lsp-attach', { clear = true }),
    callback = function(ev)
      local map = function(keys, func, desc)
        vim.keymap.set('n', keys, func, { buffer = ev.buf, desc = 'LSP: ' .. desc })
      end
      -- 0.12 已提供 grn/gra/grr/gri/grt/grx/gO/C-S，这里只补充默认没有的
      map('grd', vim.lsp.buf.definition, '[G]oto [D]efinition')
      map('grD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')
      map('K', vim.lsp.buf.hover, 'Hover documentation')
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
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  if capabilities.workspace then capabilities.workspace.didChangeWatchedFiles = nil end
  vim.lsp.config('*', { capabilities = capabilities })
  local servers = {
    lua_ls = {
      on_init = function(client)
        client.server_capabilities.documentFormattingProvider = false
        if client.workspace_folders then
          local path = client.workspace_folders[1].name
          if path ~= vim.fn.stdpath 'config'
            and (vim.uv.fs_stat(path .. '/.luarc.json') or vim.uv.fs_stat(path .. '/.luarc.jsonc'))
          then
            return
          end
        end
        client.config.settings.Lua = vim.tbl_deep_extend('force', client.config.settings.Lua, {
          runtime = { version = 'LuaJIT', path = { 'lua/?.lua', 'lua/?/init.lua' } },
          workspace = { checkThirdParty = false },
        })
      end,
      settings = { Lua = { format = { enable = false } } },
    },
    -- pyright = {},
    -- rust_analyzer = {},
    -- clangd = {},
  }
  vim.pack.add { gh 'neovim/nvim-lspconfig', gh 'mason-org/mason.nvim', gh 'mason-org/mason-lspconfig.nvim', gh 'WhoIsSethDaniel/mason-tool-installer.nvim' }
  require('mason').setup {}
  local ensure_installed = vim.tbl_keys(servers or {})
  vim.list_extend(ensure_installed, { 'stylua', 'ruff', 'prettier', 'eslint_d', 'luacheck' })
  require('mason-tool-installer').setup { ensure_installed = ensure_installed }
  for name, server in pairs(servers) do
    vim.lsp.config(name, server)
    vim.lsp.enable(name)
  end
end
-- Section: FORMATTING
do
  vim.pack.add { gh 'stevearc/conform.nvim' }
  require('conform').setup {
    notify_on_error = false,
    default_format_opts = { lsp_format = 'fallback' },
    formatters_by_ft = {
      lua = { 'stylua' },
      python = { 'ruff_format', 'ruff_organize_imports' },
      javascript = { 'prettier' },
      typescript = { 'prettier' },
      javascriptreact = { 'prettier' },
      typescriptreact = { 'prettier' },
    },
    format_on_save = function(bufnr)
      local enabled = { lua = true, python = true, javascript = true, typescript = true }
      return enabled[vim.bo[bufnr].filetype] and { timeout_ms = 500, lsp_format = 'fallback' } or nil
    end,
  }
  vim.keymap.set({ 'n', 'v' }, '<leader>f', function() require('conform').format { async = true } end)
end
-- Section: LINTING
do
  vim.pack.add { gh 'mfussenegger/nvim-lint' }
  local lint = require 'lint'
  lint.linters_by_ft = {
    lua = { 'luacheck' },
    python = { 'ruff' },
    javascript = { 'eslint_d' },
    typescript = { 'eslint_d' },
  }
  vim.api.nvim_create_autocmd({ 'BufWritePost', 'BufReadPost', 'InsertLeave' }, {
    callback = function() lint.try_lint() end,
  })
end
-- Section: AUTOCOMPLETE & SNIPPETS
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
-- Section: TREESITTER
do
  vim.pack.add { { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' } }
  local parsers = { 'bash', 'c', 'cpp', 'diff', 'html', 'javascript', 'lua', 'luadoc', 'markdown', 'markdown_inline', 'python', 'query', 'typescript', 'vim', 'vimdoc' }
  require('nvim-treesitter').install(parsers)
  local function try_attach(buf, language)
    if not vim.treesitter.language.add(language) then return end
    vim.treesitter.start(buf, language)
    if vim.treesitter.query.get(language, 'indents') ~= nil then
      vim.bo.indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
    end
  end
  local available = require('nvim-treesitter').get_available()
  vim.api.nvim_create_autocmd('FileType', {
    callback = function(args)
      local language = vim.treesitter.language.get_lang(args.match)
      if not language then return end
      local installed = require('nvim-treesitter').get_installed 'parsers'
      if vim.tbl_contains(installed, language) then
        try_attach(args.buf, language)
      elseif vim.tbl_contains(available, language) then
        require('nvim-treesitter').install(language):await(function() try_attach(args.buf, language) end)
      end
    end,
  })
end
-- Section: DAP
do
  vim.pack.add {
    gh 'mfussenegger/nvim-dap',
    gh 'rcarriga/nvim-dap-ui',
    gh 'nvim-neotest/nvim-nio',
    gh 'jay-babu/mason-nvim-dap.nvim',
    gh 'theHamsta/nvim-dap-virtual-text',
  }
  local dap = require 'dap'
  local dapui = require 'dapui'
  dapui.setup()
  require('mason-nvim-dap').setup {
    ensure_installed = { 'python', 'codelldb', 'node2' },
    automatic_installation = true,
    handlers = {},
  }
  require('nvim-dap-virtual-text').setup()
  dap.listeners.before.attach.dapui_config = function() dapui.open() end
  dap.listeners.before.launch.dapui_config = function() dapui.open() end
  dap.listeners.before.event_terminated.dapui_config = function() dapui.close() end
  dap.listeners.before.event_exited.dapui_config = function() dapui.close() end
  vim.keymap.set('n', '<F5>', dap.continue)
  vim.keymap.set('n', '<F10>', dap.step_over)
  vim.keymap.set('n', '<F11>', dap.step_into)
  vim.keymap.set('n', '<F12>', dap.step_out)
  vim.keymap.set('n', '<leader>db', dap.toggle_breakpoint)
  vim.keymap.set('n', '<leader>dB', function() dap.set_breakpoint(vim.fn.input 'Breakpoint condition: ') end)
  vim.keymap.set('n', '<leader>dr', dap.repl.toggle)
  vim.keymap.set('n', '<leader>de', function() dapui.eval(vim.fn.input 'Expression: ') end)
  dap.adapters.python = function(cb, config)
    if config.request == 'attach' then
      local port = (config.connect or config).port
      local host = (config.connect or config).host or '127.0.0.1'
      cb { type = 'server', port = port, host = host, options = { source_filetype = 'python' } }
    else
      cb { type = 'executable', command = 'python3', args = { '-m', 'debugpy.adapter' }, options = { source_filetype = 'python' } }
    end
  end
  dap.configurations.python = {
    { type = 'python', request = 'launch', name = 'Python: Launch file', program = '${file}', console = 'integratedTerminal' },
  }
  dap.adapters.codelldb = { type = 'executable', command = 'codelldb' }
  dap.configurations.cpp = {
    { name = 'LLDB: Launch file', type = 'codelldb', request = 'launch', program = function() return vim.fn.input('Path to executable: ', vim.fn.getcwd() .. '/', 'file') end, cwd = '${workspaceFolder}', stopOnEntry = false },
  }
  dap.configurations.c = dap.configurations.cpp
  dap.configurations.rust = dap.configurations.cpp
  dap.configurations.javascript = {
    { name = 'Node2: Launch file', type = 'node2', request = 'launch', program = '${file}', cwd = '${workspaceFolder}', sourceMaps = true, protocol = 'inspector', console = 'integratedTerminal' },
  }
  dap.configurations.typescript = dap.configurations.javascript
end
-- vim: ts=2 sts=2 sw=2 et
```

---

## 4. 阶段 B：模块化拆分

### 目录结构

```text
~/.config/nvim/
├── init.lua
├── nvim-pack-lock.json
├── lua/
│   ├── config/
│   │   ├── options.lua
│   │   ├── keymaps.lua
│   │   ├── autocmds.lua
│   │   └── diagnostics.lua
│   ├── plugins/
│   │   ├── init.lua
│   │   ├── ui.lua
│   │   ├── navigation.lua
│   │   ├── lsp.lua
│   │   ├── formatting.lua
│   │   ├── lint.lua
│   │   ├── completion.lua
│   │   ├── treesitter.lua
│   │   └── dap.lua
│   └── utils/
│       ├── gh.lua
│       └── helpers.lua
```

### init.lua（入口）

```lua
vim.loader.enable()

vim.g.mapleader = ' '
vim.g.maplocalleader = ' '
vim.g.have_nerd_font = false

require('config.options')
require('config.keymaps')
require('config.autocmds')
require('config.diagnostics')

require('plugins')
```

### 拆分原则

- `config/*.lua`：编辑器基础（选项、按键、自动命令、诊断）。
- `plugins/init.lua`：集中 `vim.pack.add()` + build hooks + 加载各插件模块。
- `plugins/*.lua`：每个插件/功能一个文件；除 `dap.lua` 外，其余与阶段 A 对应 `do ... end` 块**完全相同**，直接复制即可。
- `utils/*.lua`：纯工具函数，无副作用。
- 下面以 `dap.lua` 为例展示拆分后的文件形态。

### lua/plugins/init.lua

```lua
local gh = function(repo) return 'https://github.com/' .. repo end

local function run_build(name, cmd, cwd)
  local result = vim.system(cmd, { cwd = cwd }):wait()
  if result.code ~= 0 then
    vim.notify(('Build failed for %s:\n%s'):format(name, result.stderr or result.stdout or 'No output'),
      vim.log.levels.ERROR)
  end
end

vim.api.nvim_create_autocmd('PackChanged', {
  callback = function(ev)
    local name, kind = ev.data.spec.name, ev.data.kind
    if kind ~= 'install' and kind ~= 'update' then return end
    if name == 'telescope-fzf-native.nvim' and vim.fn.executable 'make' == 1 then
      run_build(name, { 'make' }, ev.data.path)
    elseif name == 'nvim-treesitter' then
      if not ev.data.active then vim.cmd.packadd 'nvim-treesitter' end
      vim.cmd 'TSUpdate'
    elseif name == 'LuaSnip' and vim.fn.has 'win32' ~= 1 and vim.fn.executable 'make' == 1 then
      run_build(name, { 'make', 'install_jsregexp' }, ev.data.path)
    end
  end,
})

vim.pack.add {
  gh 'folke/tokyonight.nvim',
  gh 'lewis6991/gitsigns.nvim',
  gh 'folke/which-key.nvim',
  gh 'nvim-mini/mini.nvim',
  gh 'nvim-lua/plenary.nvim',
  gh 'nvim-telescope/telescope.nvim',
  gh 'nvim-telescope/telescope-ui-select.nvim',
  gh 'nvim-telescope/telescope-fzf-native.nvim',
  gh 'j-hui/fidget.nvim',
  gh 'neovim/nvim-lspconfig',
  gh 'mason-org/mason.nvim',
  gh 'mason-org/mason-lspconfig.nvim',
  gh 'WhoIsSethDaniel/mason-tool-installer.nvim',
  gh 'stevearc/conform.nvim',
  gh 'mfussenegger/nvim-lint',
  { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' },
  { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' },
  { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' },
  gh 'mfussenegger/nvim-dap',
  gh 'rcarriga/nvim-dap-ui',
  gh 'nvim-neotest/nvim-nio',
  gh 'jay-babu/mason-nvim-dap.nvim',
  gh 'theHamsta/nvim-dap-virtual-text',
}

require('plugins.ui')
require('plugins.navigation')
require('plugins.lsp')
require('plugins.formatting')
require('plugins.lint')
require('plugins.completion')
require('plugins.treesitter')
require('plugins.dap')
```


### lua/plugins/dap.lua

```lua
local dap = require 'dap'
local dapui = require 'dapui'

dapui.setup()

require('mason-nvim-dap').setup {
  ensure_installed = { 'python', 'codelldb', 'node2' },
  automatic_installation = true,
  handlers = {},
}
require('nvim-dap-virtual-text').setup()

dap.listeners.before.attach.dapui_config = function() dapui.open() end
dap.listeners.before.launch.dapui_config = function() dapui.open() end
dap.listeners.before.event_terminated.dapui_config = function() dapui.close() end
dap.listeners.before.event_exited.dapui_config = function() dapui.close() end

vim.keymap.set('n', '<F5>', dap.continue)
vim.keymap.set('n', '<F10>', dap.step_over)
vim.keymap.set('n', '<F11>', dap.step_into)
vim.keymap.set('n', '<F12>', dap.step_out)
vim.keymap.set('n', '<leader>db', dap.toggle_breakpoint)
vim.keymap.set('n', '<leader>dB', function() dap.set_breakpoint(vim.fn.input 'Breakpoint condition: ') end)
vim.keymap.set('n', '<leader>dr', dap.repl.toggle)
vim.keymap.set('n', '<leader>de', function() dapui.eval(vim.fn.input 'Expression: ') end)

dap.adapters.python = function(cb, config)
  if config.request == 'attach' then
    local port = (config.connect or config).port
    local host = (config.connect or config).host or '127.0.0.1'
    cb { type = 'server', port = port, host = host, options = { source_filetype = 'python' } }
  else
    cb { type = 'executable', command = 'python3', args = { '-m', 'debugpy.adapter' }, options = { source_filetype = 'python' } }
  end
end
dap.configurations.python = {
  { type = 'python', request = 'launch', name = 'Python: Launch file', program = '${file}', console = 'integratedTerminal' },
}

dap.adapters.codelldb = { type = 'executable', command = 'codelldb' }
dap.configurations.cpp = {
  { name = 'LLDB: Launch file', type = 'codelldb', request = 'launch', program = function() return vim.fn.input('Path to executable: ', vim.fn.getcwd() .. '/', 'file') end, cwd = '${workspaceFolder}', stopOnEntry = false },
}
dap.configurations.c = dap.configurations.cpp
dap.configurations.rust = dap.configurations.cpp

dap.configurations.javascript = {
  { name = 'Node2: Launch file', type = 'node2', request = 'launch', program = '${file}', cwd = '${workspaceFolder}', sourceMaps = true, protocol = 'inspector', console = 'integratedTerminal' },
}
dap.configurations.typescript = dap.configurations.javascript
```

---

## 5. 单文件 vs 模块化对照表

| 功能 | 单文件 init.lua | 模块化 |
|---|---|---|
| `vim.loader.enable()` | 第 1 行 | `init.lua` 第 1 行 |
| 编辑器选项 | Foundation `do` 块 | `lua/config/options.lua` |
| 按键映射 | Foundation `do` 块 | `lua/config/keymaps.lua` |
| Diagnostic 配置 | Foundation `do` 块 | `lua/config/diagnostics.lua` |
| 自动命令 | Foundation `do` 块 | `lua/config/autocmds.lua` |
| 插件管理 + build hooks | BUILD HOOKS | `lua/plugins/init.lua` |
| 配色 / Gitsigns / which-key / mini | UI `do` 块 | `lua/plugins/ui.lua` |
| Telescope | SEARCH `do` 块 | `lua/plugins/navigation.lua` |
| LSP + Mason | LSP `do` 块 | `lua/plugins/lsp.lua` |
| conform.nvim 格式化 | FORMATTING `do` 块 | `lua/plugins/formatting.lua` |
| nvim-lint | LINTING `do` 块 | `lua/plugins/lint.lua` |
| blink.cmp + LuaSnip | AUTOCOMPLETE `do` 块 | `lua/plugins/completion.lua` |
| Treesitter | TREESITTER `do` 块 | `lua/plugins/treesitter.lua` |
| nvim-dap + dap-ui | DAP `do` 块 | `lua/plugins/dap.lua` |

---

## 6. 迁移清单：从 kickstart 默认到完整工具链

1. **第一行加 `vim.loader.enable()`**。
2. **升级 diagnostics**：加入 `virtual_lines`、`underline`、`jump.on_jump`。
3. **清理 LSP 映射**：删除冗余的 `grn`/`gra`，保留 `grd`/`grD`/`K`。
4. **加入 conform.nvim**：`format_on_save`、`formatters_by_ft`、`<leader>f`。
5. **加入 nvim-lint**：`linters_by_ft`、`BufWritePost` 触发。
6. **加入 nvim-dap**：dap / dap-ui / nvim-nio / mason-nvim-dap / virtual-text，F 键 + `<leader>d*`。
7. **Mason 工具**：`ensure_installed` 补上 formatter/linter/DAP 名称。
8. **验证**：`:checkhealth vim.lsp`、`:ConformInfo`、`:lua require('lint').try_lint()`、按 `<F5>` 调试。

---

## 7. 操作步骤

### 备份并清空

```bash
mv ~/.config/nvim ~/.config/nvim.bak
mkdir ~/.config/nvim
```

### 创建配置

选择阶段 A 或阶段 B，写入 `~/.config/nvim/init.lua` 并创建相应目录。

### 启动 Neovim

```bash
nvim
```

首次启动按 `a` 允许全部安装，等待 Mason 异步安装完成。

### 验证核心功能

| 功能 | 验证方式 |
|---|---|
| 启动加速 | `nvim --startuptime /tmp/s.log -c 'q'` |
| Colorscheme | 看到 tokyonight-night 配色 |
| LSP | 打开 `.lua` 文件，`:checkhealth vim.lsp` |
| 格式化 | 保存 Lua 文件 |
| Lint | 写 `print x`（Python）保存 |
| 补全 | 输入 `vim.` 等待弹出 |
| 调试 | 打开 Python 文件设断点，按 `<F5>` |

---

## 8. 练习

### 练习 1: 调试一个 Python 程序

写一个阶乘函数，设置断点，用 `<F5>` 启动调试，验证单步与变量面板。

### 练习 2: 配置多语言 formatter

在 `formatters_by_ft` 中新增 Rust (`rustfmt`) 或 Go (`gofmt`)，测试自动格式化。

### 练习 3: 添加一个 linter

为 Markdown 文件添加 `markdownlint`，保存 `.md` 查看诊断。

### 练习 4: 把单文件拆成模块化

按阶段 B 拆分，确保 LSP/format/lint/DAP 全部正常。

---

## 8.5 参考答案

> [!tip]- 练习 1 参考答案
> `main.py` 示例：
>
> ```python
> def factorial(n):
>     if n <= 1:
>         return 1
>     return n * factorial(n - 1)
>
> result = factorial(5)
> print(result)
> ```
>
> 在 `return n * factorial(n - 1)` 行按 `<leader>db` 设断点，`<F5>` 启动，`<F11>` step into，`scopes` 面板应看到 `n` 递减。

> [!tip]- 练习 2 参考答案
> ```lua
> formatters_by_ft = {
>   lua = { 'stylua' },
>   python = { 'ruff_format', 'ruff_organize_imports' },
>   javascript = { 'prettier' },
>   typescript = { 'prettier' },
>   rust = { 'rustfmt' },
>   go = { 'gofmt' },
> }
> format_on_save = function(bufnr)
>   local enabled = { lua = true, python = true, javascript = true, typescript = true, rust = true, go = true }
>   return enabled[vim.bo[bufnr].filetype] and { timeout_ms = 500, lsp_format = 'fallback' } or nil
> end,
> ```

> [!tip]- 练习 3 参考答案
> 在 `ensure_installed` 加入 `markdownlint`，在 `linters_by_ft` 加入 `markdown = { 'markdownlint' }`。测试文件：
>
> ```markdown
> # 标题
> 这是没有空行的段落
> # 另一个标题
> ```
>
> 保存后会报 MD022。

> [!tip]- 练习 4 参考答案
> 1. 备份 `init.lua`。
> 2. `mkdir -p lua/config lua/plugins lua/utils`。
> 3. Foundation 移入 `lua/config/*.lua`。
> 4. 各 `do ... end` 块移入 `lua/plugins/*.lua`。
> 5. `gh` 和 `run_build` 移入 `lua/utils/*.lua`。
> 6. `lua/plugins/init.lua` 集中 `vim.pack.add()` 并 `require` 各模块。
> 7. 入口简化为 loader + leaders + `require('config.*')` + `require('plugins')`。
> 8. 重启后验证 `:checkhealth vim.lsp`、格式化、lint、`<F5>` 调试。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 9. 扩展阅读

- [kickstart.nvim 完整仓库](https://github.com/nvim-lua/kickstart.nvim)
- [A Guide to vim.pack](https://echasnovski.com/blog/2026-03-13-a-guide-to-vim-pack)
- [Neovim 0.12 更新日志](https://neovim.io/doc/user/news-0.12.html)
- [nvim-dap 调试指南](https://codeberg.org/mfussenegger/nvim-dap/wiki/Debug-Adapter-installation)
- [conform.nvim 文档](https://github.com/stevearc/conform.nvim)
- [nvim-lint 文档](https://github.com/mfussenegger/nvim-lint)

---

## 常见陷阱

- **`vim.loader.enable()` 不在第一行**：一旦前面有 `require()`，缓存对那个模块不生效。
- **把 formatter 当成 LSP 启用**：`stylua`、`prettier` 不是 LSP server，不能传给 `vim.lsp.enable()`。
- **mason-tool-installer 首次异步安装未完成**：首次启动时 LSP 可能不附着，重启即可。
- **nvim-dap-ui 缺少 `nvim-nio`**：安装时必须包含 `nvim-neotest/nvim-nio`。
- **DAP adapter 名称与 `type` 不一致**：adapter 叫 `python`，配置里 `type` 也必须是 `python`。
- **0.12 默认 LSP 映射重复定义**：手动再映射 `grn`/`gra` 不会报错，但冗余。
- **treesitter 与 mini.ai 的 `an`/`in` 冲突**：把 mini.ai 的 `around_next`/`inside_next` 改为 `aa`/`ii`。
- **模块化后忘记 require**：文件写了但 `init.lua` 没 `require`，插件不会加载。
- **`.luarc.json` 导致 lua_ls 配置被覆盖**：用 `on_init` 判断并跳过已存在项目配置的路径。
- **lint 工具未安装**：`nvim-lint` 只是调用外部 linter，Mason 必须先装好对应工具。
