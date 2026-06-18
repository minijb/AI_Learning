---
title: "14 — kickstart.nvim 架构深度解析"
updated: 2026-06-18
---

# 14 — kickstart.nvim 架构深度解析

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 65 分钟
> 前置知识: [[07-vim-pack]]、[[08-modern-plugin-patterns]]、[[09-modern-lsp]]、[[10-blink-cmp]]、[[11-treesitter]]

---

## 1. 概念讲解

### kickstart.nvim 是什么

kickstart.nvim 是 Neovim 核心开发者 TJ DeVries 维护的**单文件配置模板**。它不是发行版（distribution），而是一个"启动点"——你可以从头到尾读懂每一行代码，然后在此基础上构建自己的配置。

> "The goal is that you can read every line of code, top-to-bottom, understand what your configuration is doing, and modify it to suit your needs."

### 设计哲学

1. **单文件优先** — 整个配置在 `init.lua` 中，约 1000 行，完全可读；
2. **注释即文档** — 注释数量远超一般配置，解释每个选择的原因；
3. **零魔法** — `vim.pack.add()` 后直接 `.setup()`，没有隐式依赖；
4. **`do ... end` 分区** — 10 个 `do` 块，职责边界清晰；
5. **渐进式揭示** — 每个 section 既可独立理解，组合起来又完整；
6. **可扩展** — 内置 `kickstart.plugins.*` 和 `custom.plugins` 扩展机制。

### 2026-06 master 分支的 10 个 section

```
init.lua (~1000 行，10 个 section)

SECTION 1: OPTIONS
  ├── vim.loader.enable()           ← 缓存 Lua 模块，加速启动
  ├── leader 设置                    ← 必须在插件之前
  └── vim.o / vim.opt 选项体系       ← number, mouse, clipboard, listchars

SECTION 2: KEYMAPS
  ├── vim.diagnostic.config()       ← 全局诊断配置
  ├── <Esc> 清搜索高亮
  ├── <C-hjkl> 窗口导航
  ├── 终端 <Esc><Esc> 退出
  └── TextYankPost → vim.hl.on_yank()

SECTION 3: PLUGIN MANAGER INTRO
  ├── run_build() 辅助函数           ← vim.system() 同步执行构建
  └── PackChanged autocmd           ← 安装/更新后自动编译

SECTION 4: UI / CORE UX
  ├── guess-indent.nvim             ← 自动检测缩进
  ├── gitsigns.nvim                 ← Git 标记
  ├── which-key.nvim                ← 按键提示
  ├── tokyonight.nvim               ← colorscheme
  ├── todo-comments.nvim            ← TODO 高亮
  └── mini.nvim 模块                ← ai, surround, statusline, icons

SECTION 5: SEARCH & NAVIGATION
  ├── telescope.nvim                ← 模糊查找器
  ├── telescope-fzf-native          ← 可选 fzf 后端
  ├── telescope-ui-select           ← 接管 vim.ui.select
  └── LSP picker 覆盖 grr/gri/gO/grd/grt

SECTION 6: LSP
  ├── fidget.nvim                   ← LSP 状态通知
  ├── LspAttach autocmd             ← 手动映射（部分与默认重叠）
  ├── servers 配置表                ← lua_ls, stylua, ...
  ├── mason 工具链                  ← mason-org 组织
  └── vim.lsp.config() + vim.lsp.enable()

SECTION 7: FORMATTING
  ├── conform.nvim                  ← 格式化引擎
  └── <leader>f 键位

SECTION 8: AUTOCOMPLETE & SNIPPETS
  ├── LuaSnip                       ← Snippet 引擎
  └── blink.cmp (V1)                ← 补全引擎

SECTION 9: TREESITTER
  ├── nvim-treesitter (main 分支)    ← 语法引擎
  ├── parsers 列表                  ← 预装基础解析器
  ├── treesitter_try_attach         ← 条件启用
  └── foldexpr

SECTION 10: OPTIONAL EXAMPLES
  └── kickstart.plugins.* / custom.plugins
```

### 关键设计决策

#### 决策 1: 为什么是单文件？

| | 单文件 | 模块化 |
|---|--------|--------|
| 学习成本 | 低——从上读到下 | 高——需要在文件间跳转 |
| 发现性 | 高——所有配置可见 | 中——需要知道文件结构 |
| 维护性 | 适中——文件长度可控 | 高——职责清晰 |
| 启动速度 | 相当 | 相当 |
| 团队协作 | 低 | 高 |

kickstart 选择单文件，因为它首先是**教学工具**。理解后可随时拆成多文件，详见 [[15-modular-config]]。

#### 决策 2: 显式 `.setup()` 与 `do ... end`

```lua
vim.pack.add { gh 'folke/which-key.nvim' }
require('which-key').setup {
  delay = 0,
  icons = { mappings = vim.g.have_nerd_font },
}
```

显式调用让你看到哪个函数被调用、在前后添加任意逻辑、在 `setup()` 参数中使用变量和条件。每个 `do ... end` 块创建局部作用域，section 之间的变量不会互相干扰，也不需要 `local M = {}` 的模块样板。

---

## 2. 代码精读：十个 section

### SECTION 1: OPTIONS

```lua
vim.loader.enable()  -- 缓存编译后的 Lua 模块，加速启动

vim.g.mapleader = ' '
vim.g.maplocalleader = ' '
vim.g.have_nerd_font = false

vim.o.number = true
vim.o.relativenumber = false
vim.o.mouse = 'a'

vim.schedule(function()
  vim.o.clipboard = 'unnamedplus'
end)

vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.hlsearch = true
vim.o.breakindent = true
vim.o.undofile = true

vim.o.signcolumn = 'yes'
vim.o.cursorline = true
vim.o.scrolloff = 10
vim.o.showmode = false
vim.o.inccommand = 'split'
vim.o.confirm = true

vim.o.list = true
vim.opt.listchars = { tab = '» ', trail = '·', nbsp = '␣' }

vim.o.splitright = true
vim.o.splitbelow = true

vim.o.updatetime = 250
vim.o.timeoutlen = 300
```

**设计要点**：
- `vim.loader.enable()` 放在**第一行**，这是 kickstart master 的现代做法；
- `vim.schedule` 延迟 clipboard 设置，避免启动时立即与系统剪贴板同步；
- `vim.opt.listchars` 用表赋值，`tab = '» '` 中的空格也是显示内容。

### SECTION 2: KEYMAPS

```lua
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

vim.keymap.set('n', '\u003cleader\u003eq', vim.diagnostic.setloclist, { desc = 'Open diagnostic [Q]uickfix list' })
vim.keymap.set('n', '\u003cEsc\u003e', '\u003ccmd\u003enohlsearch\u003ccr\u003e')

vim.keymap.set('n', '\u003cC-h\u003e', '\u003cC-w\u003e\u003cC-h\u003e', { desc = 'Move focus to the left window' })
vim.keymap.set('n', '\u003cC-l\u003e', '\u003cC-w\u003e\u003cC-l\u003e', { desc = 'Move focus to the right window' })
vim.keymap.set('n', '\u003cC-j\u003e', '\u003cC-w\u003e\u003cC-j\u003e', { desc = 'Move focus to the lower window' })
vim.keymap.set('n', '\u003cC-k\u003e', '\u003cC-w\u003e\u003cC-k\u003e', { desc = 'Move focus to the upper window' })

vim.keymap.set('t', '\u003cEsc\u003e\u003cEsc\u003e', '\u003cC-\\\\\u003e\u003cC-n\u003e', { desc = 'Exit terminal mode' })

vim.api.nvim_create_autocmd('TextYankPost', {
  desc = 'Highlight when yanking (copying) text',
  group = vim.api.nvim_create_augroup('kickstart-highlight-yank', { clear = true }),
  callback = function()
    vim.hl.on_yank()
  end,
})
```

**现代要点**：
- `vim.hl.on_yank()` 是 0.11+ 的 API（旧名 `vim.highlight.on_yank`）；
- `vim.diagnostic.config.jump.on_jump` 让 `[d` / `]d` 跳转诊断时自动打开浮动窗口；
- `virtual_lines` 是 0.11+ 新选项，默认关闭以节省空间。

### SECTION 3: PLUGIN MANAGER INTRO

```lua
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

**设计要点**：
- `run_build` + `vim.system()` 是 kickstart 的统一构建范式；
- `PackChanged` 在首次安装/更新时触发，自动编译需要 native 扩展的插件；
- 该 autocmd 必须放在 `vim.pack.add()` 之前，否则首次安装 hook 不生效。

### SECTION 4: UI / CORE UX

```lua
do
  local gh = function(repo) return 'https://github.com/' .. repo end

  vim.pack.add { gh 'nmac427/guess-indent.nvim' }
  require('guess-indent').setup {}

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

  vim.pack.add { gh 'folke/which-key.nvim' }
  require('which-key').setup {
    delay = 0,
    icons = {
      mappings = vim.g.have_nerd_font,
    },
    spec = {
      { '\u003cleader\u003ec', group = '[C]ode', mode = { 'n', 'x' } },
      { '\u003cleader\u003ed', group = '[D]ocument' },
      { '\u003cleader\u003er', group = '[R]ename' },
      { '\u003cleader\u003es', group = '[S]earch', mode = { 'n', 'x' } },
      { '\u003cleader\u003ew', group = '[W]orkspace' },
      { '\u003cleader\u003et', group = '[T]oggle' },
      { '\u003cleader\u003eh', group = 'Git [H]unk', mode = { 'n', 'v' } },
    },
  }

  vim.pack.add { gh 'folke/tokyonight.nvim' }
  require('tokyonight').setup {
    styles = {
      comments = { italic = false },
    },
  }
  vim.cmd.colorscheme 'tokyonight-night'

  vim.pack.add { gh 'folke/todo-comments.nvim' }
  require('todo-comments').setup { signs = false }

  vim.pack.add { gh 'nvim-mini/mini.nvim' }

  require('mini.ai').setup {
    mappings = { around_next = 'aa', inside_next = 'ii' },
    n_lines = 500,
  }

  require('mini.surround').setup()

  local statusline = require 'mini.statusline'
  statusline.setup { use_icons = vim.g.have_nerd_font }
  ---@diagnostic disable-next-line: duplicate-set-field
  statusline.section_location = function()
    return '%2l:%-2v'
  end

  require('mini.icons').setup { style = 'glyph' }
  MiniIcons.mock_nvim_web_devicons()
end
```

**现代要点**：
- `mini.ai` 的 `around_next` / `inside_next` 改为 `aa` / `ii`，因为 Neovim 0.12 内置了 `an` / `in` treesitter 文本对象，避免冲突；
- colorscheme 放在 UI section 最前面，确保后续插件高亮组正确；
- `mini.icons` + `mock_nvim_web_devicons()` 提供对老图插件的兼容。

### SECTION 5: SEARCH & NAVIGATION

```lua
do
  local gh = function(repo) return 'https://github.com/' .. repo end
  local builtin = require 'telescope.builtin'

  vim.pack.add { gh 'nvim-lua/plenary.nvim' }
  vim.pack.add { gh 'nvim-telescope/telescope.nvim' }

  require('telescope').setup {
    extensions = {
      ['ui-select'] = {
        require('telescope.themes').get_dropdown {},
      },
    },
  }

  -- 可选 fzf-native
  if vim.fn.executable 'make' == 1 then
    vim.pack.add { gh 'nvim-telescope/telescope-fzf-native.nvim' }
    pcall(require('telescope').load_extension, 'fzf')
  end

  -- ui-select 扩展
  vim.pack.add { gh 'nvim-telescope/telescope-ui-select.nvim' }
  pcall(require('telescope').load_extension, 'ui-select')

  -- 全局搜索映射
  vim.keymap.set('n', '<leader>sh', builtin.help_tags, { desc = '[S]earch [H]elp' })
  vim.keymap.set('n', '<leader>sk', builtin.keymaps, { desc = '[S]earch [K]eymaps' })
  vim.keymap.set('n', '<leader>sf', builtin.find_files, { desc = '[S]earch [F]iles' })
  vim.keymap.set('n', '<leader>ss', builtin.builtin, { desc = '[S]earch [S]elect Telescope' })
  vim.keymap.set('n', '<leader>sw', builtin.grep_string, { desc = '[S]earch current [W]ord' })
  vim.keymap.set('n', '<leader>sg', builtin.live_grep, { desc = '[S]earch by [G]rep' })
  vim.keymap.set('n', '<leader>sd', builtin.diagnostics, { desc = '[S]earch [D]iagnostics' })
  vim.keymap.set('n', '<leader>sr', builtin.resume, { desc = '[S]earch [R]esume' })
  vim.keymap.set('n', '<leader>s.', builtin.oldfiles, { desc = '[S]earch Recent Files' })
  vim.keymap.set('n', '<leader><leader>', builtin.buffers, { desc = '[ ] Find existing buffers' })
end
```

**LSP picker 覆盖**在 SECTION 6 的 `LspAttach` 中完成。

### SECTION 6: LSP

```lua
do
  local gh = function(repo) return 'https://github.com/' .. repo end

  vim.pack.add { gh 'j-hui/fidget.nvim' }
  require('fidget').setup {}

  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('kickstart-lsp-attach', { clear = true }),
    callback = function(ev)
      local map = function(keys, func, desc, mode)
        mode = mode or 'n'
        vim.keymap.set(mode, keys, func, { buffer = ev.buf, desc = 'LSP: ' .. desc })
      end

      local builtin = require 'telescope.builtin'
      local client = vim.lsp.get_client_by_id(ev.data.client_id)

      -- 0.12 默认已有 grn/gra/gri/grr/gO/grt；kickstart 仍显式保留部分映射
      map('grn', vim.lsp.buf.rename, '[R]e[n]ame')
      map('gra', vim.lsp.buf.code_action, '[G]oto Code [A]ction', { 'n', 'x' })
      map('grD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')

      -- 用 Telescope picker 覆盖默认的引用/实现/符号/类型定义
      map('grr', builtin.lsp_references, '[G]oto [R]eferences')
      map('gri', builtin.lsp_implementations, '[G]oto [I]mplementation')
      map('gO', builtin.lsp_document_symbols, 'Open Document Symbols')
      map('grt', builtin.lsp_type_definitions, '[G]oto [T]ype Definition')

      if client:supports_method('textDocument/inlayHint', ev.buf) then
        map('\u003cleader\u003eth', function()
          vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = ev.buf })
        end, '[T]oggle Inlay [H]ints')
      end
    end,
  })

  local servers = {
    lua_ls = {
      settings = {
        Lua = {
          completion = { callSnippet = 'Replace' },
          format = { enable = false },
          runtime = { version = 'LuaJIT' },
        },
      },
    },
  }

  vim.pack.add {
    gh 'neovim/nvim-lspconfig',
    gh 'mason-org/mason.nvim',
    gh 'mason-org/mason-lspconfig.nvim',
    gh 'WhoIsSethDaniel/mason-tool-installer.nvim',
  }

  require('mason').setup {}

  local ensure_installed = vim.tbl_keys(servers or {})
  require('mason-tool-installer').setup { ensure_installed = ensure_installed }

  for name, server in pairs(servers) do
    vim.lsp.config(name, server)
    vim.lsp.enable(name)
  end
end
```

**现代要点**：
- Neovim 0.12 已内置 `grn`/`gra`/`gri`/`grr`/`gO`/`grt` 等默认映射；kickstart 保留 `grn`/`gra`/`grD` 与默认重叠但不报错；
- `grr`/`gri`/`gO`/`grt` 被 Telescope picker 覆盖，`lua_ls.format.enable = false` 把格式化交给 conform；
- mason 已迁移到 `mason-org` 组织；`vim.lsp.config()` 注册配置，`vim.lsp.enable()` 根据 filetypes 自动启动。

### SECTION 7: FORMATTING

```lua
do
  local gh = function(repo) return 'https://github.com/' .. repo end

  vim.pack.add { gh 'stevearc/conform.nvim' }
  require('conform').setup {
    notify_on_error = false,
    format_on_save = function(bufnr)
      local enabled = { lua = true }  -- 按需启用
      return enabled[vim.bo[bufnr].filetype] and { timeout_ms = 500 } or nil
    end,
    default_format_opts = {
      lsp_format = 'fallback',  -- 优先外部 formatter，回退 LSP
    },
    formatters_by_ft = {
      lua = { 'stylua' },
      -- python = { 'isort', 'black' },
      -- javascript = { 'prettierd', 'prettier', stop_after_first = true },
    },
  }

  vim.keymap.set({ 'n', 'v' }, '<leader>f', function()
    require('conform').format { async = true }
  end, { desc = '[F]ormat' })
end
```

**设计要点**：
- `lsp_format = 'fallback'` 表示优先使用外部 formatter，没有时再回退到 LSP；
- `format_on_save` 用函数按文件类型动态启用，避免所有文件都触发格式化。

### SECTION 8: AUTOCOMPLETE & SNIPPETS

```lua
do
  local gh = function(repo) return 'https://github.com/' .. repo end

  vim.pack.add {
    { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' },
    { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' },
  }

  require('luasnip').setup {}

  require('blink.cmp').setup {
    keymap = { preset = 'default' },
    appearance = {
      nerd_font_variant = 'mono',
    },
    completion = {
      documentation = { auto_show = false, auto_show_delay_ms = 500 },
    },
    sources = {
      default = { 'lsp', 'path', 'snippets' },
    },
    snippets = { preset = 'luasnip' },
    fuzzy = { implementation = 'lua' },
    signature = { enabled = true },
  }
end
```

**现代要点**：
- blink.cmp V1 通过 `version = vim.version.range '1.*'` 锁定，避免 V2 的破坏性变更；
- `keymap = { preset = 'default' }` 使用 `<C-y>` 确认、`<C-n>`/`<C-p>` 上下选择；
- `fuzzy.implementation = 'lua'` 是纯 Lua 实现，也可选 `'prefer_rust_with_warning'` 使用 Rust 后端。

### SECTION 9: TREESITTER

```lua
do
  local gh = function(repo) return 'https://github.com/' .. repo end

  -- main 分支：现代 nvim-treesitter API
  vim.pack.add { { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' } }

  local available_parsers = require('nvim-treesitter').get_available 'parsers'

  -- 预装基础解析器
  local base_parsers = { 'bash', 'c', 'lua', 'markdown', 'markdown_inline', 'vim', 'vimdoc', 'query' }
  require('nvim-treesitter').install(base_parsers):await(function()
    for _, lang in ipairs(base_parsers) do
      vim.treesitter.language.add(lang)
    end
  end)

  local function treesitter_try_attach(bufnr, lang)
    if vim.treesitter.language.add(lang) then
      vim.treesitter.start(bufnr, lang)
      vim.wo[0].foldexpr = 'v:lua.vim.treesitter.foldexpr()'
    end
  end

  vim.api.nvim_create_autocmd('FileType', {
    callback = function(args)
      local language = vim.treesitter.language.get_lang(args.match)
      local installed = require('nvim-treesitter').get_installed 'parsers'

      if vim.tbl_contains(installed, language) then
        treesitter_try_attach(args.buf, language)
      elseif vim.tbl_contains(available_parsers, language) then
        require('nvim-treesitter').install(language):await(function()
          treesitter_try_attach(args.buf, language)
        end)
      end
    end,
  })
end
```

**现代要点**：
- 使用 `nvim-treesitter` 的 `main` 分支，不再用 `:TSInstall` 或 `ensure_installed`；
- `install():await()` 异步安装 parser；`vim.treesitter.start()` 启用高亮，`vim.treesitter.language.add()` 注册 parser；
- `foldexpr` 使用 treesitter 折叠表达式。

### SECTION 10: OPTIONAL EXAMPLES

```lua
-- 在 init.lua 末尾按需取消注释启用
-- require 'kickstart.plugins.debug'
-- require 'kickstart.plugins.indent_line'
-- require 'kickstart.plugins.lint'
-- require 'kickstart.plugins.autopairs'
-- require 'kickstart.plugins.neo-tree'
-- require 'kickstart.plugins.gitsigns'

-- 用户自定义插件
-- require 'custom.plugins'
```
---

## 3. 扩展路径

### 阶段 1: 直接用（初学者）
直接使用 `init.lua`，逐步阅读注释理解每个 section。

### 阶段 2: 微调（熟悉后）
修改 `servers` 表添加语言，修改 keymaps，更换 colorscheme。

### 阶段 3: 启用可选模块
取消 SECTION 10 的注释，启用 debug、indent_line、lint、autopairs、neo-tree 等。

### 阶段 4: 自定义插件
在 `lua/custom/plugins/` 下创建文件，然后 `require 'custom.plugins'`。

### 阶段 5: 完全模块化
当 `init.lua` 太长时，按 section 拆成多个文件。详见 [[15-modular-config]]。

---

## 4. 练习

### 练习 1: 逐 section 阅读 init.lua

在浏览器打开 [kickstart.nvim 的 init.lua](https://github.com/nvim-lua/kickstart.nvim/blob/master/init.lua)，从 Section 1 开始：
1. 用一句话总结每个 section 做了什么；
2. 找出一个不理解的配置项，用 `:help` 查阅；
3. 记下至少一个想修改的地方。

### 练习 2: 验证默认 LSP 按键

用 `:verbose map grr`、`:verbose map gri`、`:verbose map gO` 分别验证：
- 默认状态绑定的是原生 `vim.lsp.buf.*` 还是 Telescope picker；
- 在 LspAttach 覆盖后，这些按键指向哪里。

### 练习 3: 设计模块化拆分方案

假设要把 kickstart 拆成模块化结构，设计一个文件划分方案：
- 哪些 section 应该合并到一个文件？
- 哪些需要拆分得更细？
- 如何在拆分后保持"按执行顺序可理解"？

---

## 4.5 参考答案

> [!tip]- 练习 1 参考答案
> kickstart.nvim master 的 10 个 section 总结：
>
> | Section | 内容 | 关键配置项 |
> |---------|------|-----------|
> | 1. OPTIONS | 核心选项（vim.loader/leader/vim.o/listchars） | `vim.loader.enable()` |
> | 2. KEYMAPS | 诊断配置、基础 keymaps、yank 高亮 | `vim.hl.on_yank()`；`vim.diagnostic.config.jump.on_jump` |
> | 3. PLUGIN MANAGER | `run_build()` + `PackChanged` autocmd | `vim.system()` 构建；treesitter/fzf-native/LuaSnip 钩子 |
> | 4. UI / CORE UX | guess-indent, gitsigns, which-key, tokyonight, todo-comments, mini.* | `mini.ai` 用 `aa`/`ii`；`mini.statusline.section_location` |
> | 5. SEARCH & NAVIGATION | Telescope + fzf-native + ui-select + `<leader>s` 映射 | `pcall(load_extension, 'fzf')` |
> | 6. LSP | fidget, LspAttach, servers, mason, vim.lsp.config/enable | `lua_ls.format.enable = false`；mason-org |
> | 7. FORMATTING | conform.nvim | `lsp_format = 'fallback'` |
> | 8. AUTOCOMPLETE | LuaSnip + blink.cmp V1 | `version = vim.version.range '1.*'` |
> | 9. TREESITTER | nvim-treesitter main 分支 | `install():await()`；`treesitter_try_attach()` |
> | 10. OPTIONAL | kickstart.plugins.* / custom.plugins | 按需启用 |
>
> 容易困惑的 `:help` 入口：
> - `vim.loader.enable()` → `:help vim.loader`
> - `vim.hl.on_yank()` → `:help vim.hl`
> - `vim.diagnostic.config.jump.on_jump` → `:help vim.diagnostic.config`
> - `vim.lsp.config()` / `vim.lsp.enable()` → `:help vim.lsp.config`

> [!tip]- 练习 2 参考答案
> 在没有任何 LSP buffer 打开时，`:verbose map grr` 会显示：
>
> ```
> n  grr         *@* Lua vim.lsp.buf.references()
>         Last set from Lua (run Nvim with -V1 for more details)
> ```
>
> 这表示 0.12 内置默认映射。打开一个 LSP 附着的 buffer 后，`:verbose map grr` 会显示：
>
> ```
> n  grr         *@* <Lua function 42>
>         Last set from Lua
> ```
>
> 说明 LspAttach 中的 `vim.keymap.set('n', 'grr', builtin.lsp_references, ...)` 覆盖了默认映射。同理可验证 `gri` / `gO` / `grt`。`grn` / `gra` 在 kickstart 中仍手动映射，与默认重叠（不会报错，后定义覆盖）。

> [!tip]- 练习 3 参考答案
> 一个实际可操作的模块化拆分方案：
>
> ```
> lua/
> ├── config/
> │   ├── options.lua      ← Section 1 的 vim.o/vim.opt
> │   ├── keymaps.lua      ← Section 2 的全局 keymaps
> │   ├── autocmds.lua     ← Section 2 的 TextYankPost 等 autocmd
> │   └── diagnostics.lua  ← Section 2 的 vim.diagnostic.config
> ├── utils/
> │   ├── helpers.lua      ← gh(), run_build(), map()
> │   └── init.lua         ← 聚合导出
> └── plugins/
>     ├── init.lua         ← PackChanged + require 子模块
>     ├── ui.lua           ← Section 4
>     ├── search.lua       ← Section 5
>     ├── lsp.lua          ← Section 6
>     ├── formatting.lua   ← Section 7
>     ├── completion.lua   ← Section 8
>     ├── treesitter.lua   ← Section 9
>     └── optional.lua     ← Section 10
> ```
>
> **设计决策**：
> - Section 1 拆成 `options.lua`；Section 2 拆成 `keymaps.lua` / `autocmds.lua` / `diagnostics.lua`；
> - Section 3 的 `gh()` / `run_build()` 放入 `utils/helpers.lua`，`PackChanged` 注册放入 `plugins/init.lua`；
> - `plugins/init.lua` 按 Section 4→10 顺序 require，保持可读性；
> - 不把 `mini.ai` / `mini.surround` 分别拆成独立文件——它们在 UI section 内是紧凑的 mini.nvim 统一加载。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 5. 扩展阅读

- [kickstart.nvim 源码](https://github.com/nvim-lua/kickstart.nvim) — 完整仓库
- [kickstart.nvim README](https://github.com/nvim-lua/kickstart.nvim/blob/master/README.md) — 安装和使用指南
- [A Guide to vim.pack](https://echasnovski.com/blog/2026-03-13-a-guide-to-vim-pack) — 深入理解 kickstart 使用的插件管理器
- [mason.nvim 文档](https://github.com/mason-org/mason.nvim)
- [blink.cmp 文档](https://github.com/Saghen/blink.cmp)

---

## 常见陷阱

- **不要直接复制整个 init.lua 而不理解**：kickstart 是起点，不是终点。
- **lockfile 应纳入版本控制**：kickstart 仓库的 `.gitignore` 可能忽略了 `nvim-pack-lock.json`（方便维护），但你的 fork 应该提交它。
- **v0.11 vs v0.12 差异巨大**：看到 `lazy.setup()` 或 `cmp.setup()` 的教程针对的是旧版本。kickstart master 始终跟随最新 Neovim。
- **`vim.highlight` 已重命名为 `vim.hl`**：旧配置需要更新。
- **mason 已迁移到 `mason-org` 组织**：旧地址 `williamboman/mason.nvim` 仍重定向，但新配置应写 `mason-org/mason.nvim`。
- **mini.ai 默认 `an`/`in` 与 0.12 内置冲突**：必须改为 `aa`/`ii`。
- **nvim-treesitter 使用 main 分支 API**：旧教程中的 `:TSInstall` 和 `ensure_installed` 配置已过时。
- **fork 后需要定期同步上游**：kickstart 会持续更新。建议添加 upstream remote 定期 merge。
