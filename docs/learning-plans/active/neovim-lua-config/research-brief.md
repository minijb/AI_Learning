---
title: "研究简报: Neovim 0.12+ 现代配置（深化版权威事实源）"
updated: 2026-06-18
---

# 研究简报: Neovim 0.12+ 现代配置

> **本文件是所有内容深化任务的权威事实源。** 凡是与本文件冲突的旧教程内容，以本文件为准。
> 所有事实均经过 2026-06-18 联网核实，引用 Neovim 官方文档、kickstart.nvim 主分支、echasnovski 指南、blink.cmp 官方仓库。

---

## 0. 版本基线

| 项 | 值 |
|---|---|
| Neovim 当前稳定版 | **0.12.3**（2026-06-16 发布） |
| Lua 运行时 | **LuaJIT 2.1**（兼容 Lua 5.1 语法 + 5.2 的 `goto`/整数除法等扩展） |
| 本计划目标版本 | **0.12+**（依赖 `vim.pack`、`vim.lsp.config/enable`、`vim.lsp.completion`、`vim.hl` 等新 API） |
| 核心参考实现 | [kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim) `master` 分支（2026-06 验证） |

---

## 1. vim.pack（内置插件管理器）— 权威事实

### 1.1 锁文件（lockfile）

- **文件名**: `nvim-pack-lock.json`（**不是** `lazy-lock.json`）
- **位置**: **用户配置目录** `$XDG_CONFIG_HOME/nvim/nvim-pack-lock.json`
  - Linux/macOS: `~/.config/nvim/nvim-pack-lock.json`
  - Windows: `%LOCALAPPDATA%/nvim/nvim-pack-lock.json`
- **绝不能手动编辑**。损坏时 `vim.pack` 会自动修复。
- **应纳入版本控制**——它是配置的一部分，保证多机可重现。
- 首次 `vim.pack.add()` 调用时，根据 lockfile 一次性安装所有缺失插件到锁定 commit。

> ⚠️ **修正旧教程**: 部分旧内容把 lockfile 写在 data 目录或称为 `pack-lock.json`，**错误**。正确位置是 config 目录、文件名 `nvim-pack-lock.json`。

### 1.2 插件安装位置

- 路径: **"data" 标准路径**下的 `site/pack/core/opt/` 子目录
  - Linux/macOS: `~/.local/share/nvim/site/pack/core/opt/`
  - Windows: `%LOCALAPPDATA%/nvim-data/site/pack/core/opt/`
- **所有** `vim.pack.add()` 安装的插件都放在 `core` package 的 `opt/` 下（即"可选"插件，由 `vim.pack.add()` 内部 `:packadd` 加载）。
- **没有 "start" 插件概念**——这是设计决策：注释掉 `vim.pack.add()` 中的条目即可让插件下次启动不加载。

### 1.3 vim.pack.add() 规格（Spec）

```lua
-- 字符串形式（最简）
vim.pack.add { 'https://github.com/nvim-mini/mini.nvim' }

-- table 形式
vim.pack.add {
  { src = 'https://github.com/saghen/blink.cmp', version = vim.version.range '1.*' },
  { src = 'https://github.com/neovim/nvim-lspconfig', name = 'lspconfig' },
  { src = 'https://github.com/folke/tokyonight.nvim', data = { priority = 1000 } },
}
```

- `src`（必填）：完整 Git URL
- `version`（可选）：可以是
  - `'stable'` — 跟踪 `stable` Git 引用（分支/tag/commit）
  - 字符串分支/tag/commit：如 `'main'`
  - `vim.version.range('*')` — 最新 semver tag
  - `vim.version.range('2.x')` — `>=2.0.0 <3.0.0` 的最新 semver tag
- `name`（可选）：自定义插件目录名（默认为 repo 名）
- `data`（可选）：任意用户数据，可在 hook 中通过 `ev.data.spec.data` 读取

### 1.4 第二参数 `opts`

```lua
vim.pack.add({ 'https://github.com/...' }, { load = function() end })  -- 注册但不加载
```

`opts.load`：自定义加载逻辑。返回空函数 = 只注册不加载（用于复杂懒加载场景）。

### 1.5 安装确认对话框

首次安装时弹出确认对话框：
- `y` — 确认安装当前插件
- `n` — 跳过
- `a` — 允许本会话所有 `vim.pack.add()` 确认（**最常用**）

### 1.6 vim.pack.update()

```lua
:lua vim.pack.update()                                    -- 更新全部，打开确认 buffer
:lua vim.pack.update({ 'mini.nvim' })                     -- 只更新指定插件
:lua vim.pack.update(nil, { force = true })               -- 立即应用，跳过确认（脚本用）
:lua vim.pack.update(nil, { offline = true })             -- 只读查看状态，不下载
:lua vim.pack.update(nil, { target = 'lockfile' })        -- 同步到 lockfile 状态（回滚用）
```

确认 buffer 特性：
- `:write` 应用更新；`:quit` 取消
- `]]` / `[[` 在插件段间跳转
- 内置 in-process LSP server，支持 `textDocument/hover`、`codeAction`、`documentSymbol`
- 更新日志写入 `nvim-pack.log`（"log" 标准路径下）

> ⚠️ **修正旧教程**: 旧教程称 "在 diff 窗口 :write 应用"。**不准确**。实际是"确认 buffer"，提供 LSP-powered 的交互式查看/应用/跳过/code action（删除未激活插件等）。

### 1.7 vim.pack.del()

```lua
:lua vim.pack.del({ 'nvim-lspconfig', 'nvim-treesitter' })
```

- 删除插件**必须**用 `vim.pack.del()`，不能手动删目录（否则 lockfile 不一致，下次启动会重装）。
- 删除前**必须**先从配置中移除对应的 `vim.pack.add()` 条目。

### 1.8 PackChanged / PackChangedPre 事件（hooks）

```lua
-- 必须在 vim.pack.add() 之前注册，install hook 才能在首次安装时触发
vim.api.nvim_create_autocmd('PackChanged', {
  callback = function(ev)
    local name = ev.data.spec.name
    local kind = ev.data.kind  -- 'install' | 'update' | 'delete'
    -- ev.data.path = 插件磁盘路径
    -- ev.data.active = 是否已加载
    if name == 'nvim-treesitter' and kind == 'update' then
      if not ev.data.active then vim.cmd.packadd('nvim-treesitter') end
      vim.cmd('TSUpdate')
    end
  end,
})
```

- `kind`: `install`（首次安装）、`update`（更新已安装）、`delete`（删除）
- **kickstart.nvim 的统一 build 模式**（推荐）：定义 `run_build(name, cmd, cwd)` 辅助函数用 `vim.system()` 执行构建命令：

```lua
local function run_build(name, cmd, cwd)
  local result = vim.system(cmd, { cwd = cwd }):wait()
  if result.code ~= 0 then
    vim.notify(('Build failed for %s:\n%s'):format(name, result.stderr or result.stdout or 'No output'),
      vim.log.levels.ERROR)
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

> ⚠️ **修正旧教程**: 旧教程说 vim.pack "通过 PackChanged 执行 build 钩子，没有 lazy.nvim 的 `build` 字段"——**方向正确**，但没给出 kickstart 的 `run_build + vim.system()` 实战范式。新教程应直接展示该范式。

### 1.9 配置组织方式（三种官方推荐）

1. **单一 `vim.pack.add()`**（最稳健，推荐入门）
   - 在 init.lua 顶部定义所有 PackChanged hook
   - 一个 `vim.pack.add({...})` 调用列出所有插件
   - 立即 `require('plugin').setup()` 配置
2. **多个 `vim.pack.add()` 调用**（模块化）
   - 在 `plugin/*.lua` 中分散，按字母序自动 source
   - install hook 应集中在 init.lua 顶部以覆盖 lockfile bootstrap
3. **懒加载**（按需）
   - `vim.schedule(function() vim.pack.add({...}) end)` — 启动后异步加载
   - `vim.api.nvim_create_autocmd('InsertEnter', { once = true, callback = ... })` — 事件触发加载

### 1.10 健康检查与故障排查

```vim
:checkhealth vim.pack
```
报告：lockfile 缺失/损坏、lockfile 与磁盘不一致、未激活插件（已装未加载，常为已从配置移除但未 `vim.pack.del`）。

---

## 2. vim.lsp（原生 LSP API）— 权威事实

### 2.1 0.12 的重大变化：默认全局按键映射

**Neovim 0.12 在启动时无条件创建以下全局按键映射**（不再需要手动映射！）：

| 按键 | 模式 | 功能 |
|---|---|---|
| `gra` | n, x | `vim.lsp.buf.code_action()` |
| `gri` | n | `vim.lsp.buf.implementation()` |
| `grn` | n | `vim.lsp.buf.rename()` |
| `grr` | n | `vim.lsp.buf.references()` |
| `grt` | n | `vim.lsp.buf.type_definition()` |
| `grx` | n | `vim.lsp.codelens.run()` |
| `gO` | n | `vim.lsp.buf.document_symbol()` |
| `CTRL-S` | i | `vim.lsp.buf.signature_help()` |

> ⚠️ **重大修正**: 旧教程和 kickstart 的手动 `map('grn', vim.lsp.buf.rename, ...)` 在 0.12 中**已经冗余**——核心提供默认映射。新教程应明确指出这点，并教学习者用 `:verbose map grn` 验证默认映射存在，然后**仅添加默认不提供**的映射（如 `grd` goto definition 由 `tagfunc` 提供、`grD` goto declaration、`K` hover、`grr` references 用 Telescope picker 覆盖等）。
>
> kickstart.nvim master 分支**仍保留**手动 `grn`/`gra`/`grD` 映射，但它们现在与默认映射重叠（注释说明 "LSP: [R]e[n]ame"）。教学时应解释：这不会出错（后定义的覆盖），但现代配置可省略。

### 2.2 buffer-local 默认（LSP 附着时自动设置）

当 LSP 附着到 buffer，0.12 自动设置：
- `'omnifunc'` = `vim.lsp.omnifunc` → 用 `i_CTRL-X_CTRL-O` 触发补全
- `'tagfunc'` = `vim.lsp.tagfunc` → `CTRL-]`、`:tjump`、`CTRL-W]` 等用 LSP
- `'formatexpr'` = `vim.lsp.formatexpr` → `gq` 格式化（如服务器支持）
- `K` → `vim.lsp.buf.hover()`（除非 `'keywordprg'` 已自定义或已有 `K` 映射）
- 文档颜色高亮（document color）
- 诊断（diagnostics）

**禁用 buffer-local 默认**：

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    vim.bo[ev.buf].formatexpr = nil   -- 取消 formatexpr
    vim.bo[ev.buf].omnifunc = nil     -- 取消 omnifunc
    vim.keymap.del('n', 'K', { buf = ev.buf })  -- 取消 K hover
    vim.lsp.document_color.enable(false, { bufnr = ev.buf })
  end,
})
```

### 2.3 配置 API：vim.lsp.config() / vim.lsp.enable()

```lua
-- 注册配置（不启动）
vim.lsp.config('lua_ls', {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.git' },
  settings = { Lua = { runtime = { version = 'LuaJIT' } } },
})

-- 启用（根据 filetypes 自动启动）
vim.lsp.enable('lua_ls')

-- 一次启用多个
vim.lsp.enable({ 'lua_ls', 'rust_analyzer', 'gopls' })
```

### 2.4 配置文件模式（lsp/*.lua）— 重要

可直接在 `runtimepath` 的 `lsp/<config-name>.lua` 中定义配置：

```lua
-- ~/.config/nvim/lsp/lua_ls.lua
return {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.git' },
  settings = { Lua = { runtime = { version = 'LuaJIT' } } },
}
```

然后在 init.lua 中只需 `vim.lsp.enable('lua_ls')`。**这是模块化配置的官方推荐方式**。

### 2.5 配置合并优先级（低 → 高）

1. `vim.lsp.config('*', {...})` — 通配符，对所有 server 生效（适合全局 capabilities）
2. `lsp/<config>.lua` 文件（runtimepath 上）
3. `after/lsp/<config>.lua` 文件（覆盖 lspconfig 提供的默认）
4. 任何其他位置的 `vim.lsp.config(name, {...})` 调用

合并语义：`vim.tbl_deep_extend('force', ...)`。

```lua
-- 全局 capabilities（例如关闭大项目的文件监听）
local capabilities = vim.lsp.protocol.make_client_capabilities()
if capabilities.workspace then
  capabilities.workspace.didChangeWatchedFiles = nil
end
vim.lsp.config('*', { capabilities = capabilities })
```

### 2.6 vim.lsp.completion.enable()（原生补全，零插件）

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if client:supports_method('textDocument/completion') then
      vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
    end
  end,
})
```

- 这是 Neovim **内置的** LSP 补全 API，无需 blink.cmp/nvim-cmp
- 用 `i_CTRL-X_CTRL-O`（omnifunc）或 autotrigger 触发
- 用 `CTRL-Y` 确认补全项
- 适合追求极简/零依赖配置的用户

> **新增章节必备内容**：应专门有一节对比"原生 `vim.lsp.completion` vs blink.cmp"，让学习者根据需求选择。

### 2.7 :lsp 命令族

| 命令 | 作用 |
|---|---|
| `:lsp enable <name>` | 启用配置 |
| `:lsp disable <name>` | 禁用配置（停止运行中的） |
| `:lsp restart [name]` | 重启（无参数=重启当前 buffer 所有 client） |
| `:lsp stop [name]` | 停止 |

### 2.8 capabilities / handlers（高级）

- `vim.lsp.enable()` **自动设置 capabilities**——0.12 中不再需要手动 `vim.lsp.protocol.make_client_capabilities()`
- 自定义 handler：

```lua
-- 全局
vim.lsp.handlers['textDocument/publishDiagnostics'] = my_handler

-- per-server（vim.lsp.start 时）
vim.lsp.start({ handlers = { ['textDocument/publishDiagnostics'] = my_handler } })

-- per-request
vim.lsp.buf_request_all(0, 'method', params, handler)
```

handler 签名：`function(err, result, ctx)`。

### 2.9 健康检查

```vim
:checkhealth vim.lsp
```
查看：已启用配置、附着状态、文件监听性能等。**0.12 中 `:LspInfo` 已移除**。

### 2.10 inlay hints / codelens / linked editing range

默认**禁用**，需手动启用：

```lua
-- inlay hints（LspAttach 中切换）
if client:supports_method('textDocument/inlayHint', ev.buf) then
  vim.keymap.set('n', '<leader>th', function()
    vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = ev.buf })
  end, { desc = '[T]oggle Inlay [H]ints' })
end

-- 全局默认开启
vim.lsp.inlay_hint.enable(true)
```

---

## 3. kickstart.nvim master 关键范式（2026-06 验证）

### 3.1 init.lua 第一行

```lua
vim.loader.enable()  -- 加速启动（缓存编译后的 Lua 模块）
```

> ⚠️ **新增必讲**：`vim.loader.enable()` 是 kickstart 的第一行，旧教程完全没提。它是实验性但被 Folke 本人背书、kickstart 默认启用的启动加速功能。

### 3.2 vim.hl（不是 vim.highlight）

```lua
vim.api.nvim_create_autocmd('TextYankPost', {
  callback = function() vim.hl.on_yank() end,  -- 0.11+ 重命名
})
```

> ⚠️ **修正旧教程**: 0.11+ 中 `vim.highlight` 已重命名为 `vim.hl`。还有 `vim.hl.range()` 用于范围高亮。

### 3.3 vim.diagnostic.config 现代 config

```lua
vim.diagnostic.config {
  update_in_insert = false,
  severity_sort = true,
  float = { border = 'rounded', source = 'if_many' },
  underline = { severity = { min = vim.diagnostic.severity.WARN } },
  virtual_text = true,       -- 行尾虚拟文本
  virtual_lines = false,     -- 行下虚拟线（替代/补充 virtual_text）
  jump = {
    on_jump = function(_, bufnr)
      vim.diagnostic.open_float { bufnr = bufnr, scope = 'cursor', focus = false }
    end,
  },
}
```

- `jump.on_jump`：用 `[d`/`]d` 跳转时自动弹浮动窗口
- `virtual_lines`：0.11+ 的新选项，每条诊断独占一行虚拟文本（更易读但占空间）

### 3.4 nvim-treesitter 新 API（main 分支）

```lua
-- 安装（不再用 :TSInstall，也不再用 ensure_installed 配置）
vim.pack.add { { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' } }

-- 程序化安装 parser
require('nvim-treesitter').install({ 'lua', 'c', 'bash', 'markdown', 'vim', 'vimdoc', 'query' })

-- 启用某语言的 treesitter
vim.treesitter.language.add('lua')           -- 注册 parser
vim.treesitter.start(buf, 'lua')             -- 启用高亮等
vim.wo.foldexpr = 'v:lua.vim.treesitter.foldexpr()'  -- treesitter 折叠
```

> ⚠️ **重大修正**: 旧教程可能仍讲 `:TSInstall`、`ensure_installed = { ... }`、`highlight = { enable = true }` 的**旧 master 分支配置范式**。这是 nvim-treesitter 0.x 时代的写法。**现代（main 分支）**用 `require('nvim-treesitter').install(...)` + `vim.treesitter.start()`。kickstart master 用 FileType autocmd + `get_installed('parsers')` + 自动安装的模式。

### 3.5 内置 treesitter 文本对象（0.12 新增）

Neovim 0.12 **内置** `an`（around next）和 `in`（inside next）treesitter 文本对象映射（`:help treesitter-incremental-selection`）。

**冲突警告**：mini.ai 默认用 `an`/`in`。kickstart 因此把 mini.ai 的 around_next/inside_next 改为 `aa`/`ii`：

```lua
require('mini.ai').setup {
  mappings = { around_next = 'aa', inside_next = 'ii' },
  n_lines = 500,
}
```

### 3.6 LSP picker 覆盖默认 grr/gri/gO

kickstart 在 LspAttach 中**覆盖**默认的 `grr`/`gri`/`gO` 用 Telescope：

```lua
vim.keymap.set('n', 'grr', builtin.lsp_references, { buffer = buf, desc = '[G]oto [R]eferences' })
vim.keymap.set('n', 'gri', builtin.lsp_implementations, { buffer = buf, desc = '[G]oto [I]mplementation' })
vim.keymap.set('n', 'gO', builtin.lsp_document_symbols, { buffer = buf, desc = 'Open Document Symbols' })
```

### 3.7 mason 工具安装

```lua
vim.pack.add {
  gh 'neovim/nvim-lspconfig',
  gh 'mason-org/mason.nvim',                                  -- 注意：mason-org（不是 williamboman）
  gh 'mason-org/mason-lspconfig.nvim',
  gh 'WhoIsSethDaniel/mason-tool-installer.nvim',
}
require('mason').setup {}
local ensure_installed = vim.tbl_keys(servers)
require('mason-tool-installer').setup { ensure_installed = ensure_installed }

for name, server in pairs(servers) do
  vim.lsp.config(name, server)
  vim.lsp.enable(name)
end
```

> ⚠️ **修正**: mason.nvim 已迁移到 `mason-org` GitHub 组织（`mason-org/mason.nvim`、`mason-org/mason-lspconfig.nvim`）。旧教程若写 `williamboman/mason.nvim` 需更新（虽然旧地址仍重定向）。

### 3.8 conform.nvim 格式化

```lua
vim.pack.add { gh 'stevearc/conform.nvim' }
require('conform').setup {
  notify_on_error = false,
  format_on_save = function(bufnr)
    local enabled = { lua = true, python = true }  -- 按需启用
    return enabled[vim.bo[bufnr].filetype] and { timeout_ms = 500 } or nil
  end,
  default_format_opts = { lsp_format = 'fallback' },  -- 优先用外部 formatter，回退 LSP
  formatters_by_ft = {
    -- rust = { 'rustfmt' },
    -- python = { 'isort', 'black' },
    -- javascript = { 'prettierd', 'prettier', stop_after_first = true },
  },
}
vim.keymap.set({ 'n', 'v' }, '<leader>f', function() require('conform').format { async = true } end, { desc = '[F]ormat' })
```

---

## 4. blink.cmp — 权威事实

### 4.1 V1 vs V2（重要）

- **V1**（`version = '1.*'`）：稳定，kickstart 默认采用
- **V2**（`main` 分支）：**积极开发中，有破坏性变更**，需要额外安装 `blink.lib`
- **推荐**：生产配置用 `'1.*'` 锁定；学习 V2 时用独立 NVIM_APPNAME 配置

### 4.2 完整配置（V1，kickstart 风格）

```lua
vim.pack.add {
  { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' },
  { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' },
}
require('luasnip').setup {}
require('blink.cmp').setup {
  keymap = { preset = 'default' },  -- 或 'super-tab' / 'enter' / 'none'
  appearance = { nerd_font_variant = 'mono' },
  completion = { documentation = { auto_show = false, auto_show_delay_ms = 500 } },
  sources = { default = { 'lsp', 'path', 'snippets' } },
  snippets = { preset = 'luasnip' },     -- 或 'mini_snippets' / 'native'
  fuzzy = { implementation = 'lua' },     -- 或 'prefer_rust_with_warning'
  signature = { enabled = true },
}
```

### 4.3 按键预设（keymap presets）

| preset | 确认 | 上下选 | 关闭 | 说明 |
|---|---|---|---|---|
| `'default'` | `<C-y>` | `<C-n>/<C-p>` | `<C-e>` | 推荐，确认与换行分离 |
| `'super-tab'` | `<Tab>` | `<Tab>/<S-Tab>` | `<C-e>` | 类 VSCode |
| `'enter'` | `<CR>` | `<C-n>/<C-p>` | `<C-e>` | Enter 确认（风险：误换行） |
| `'none'` | — | — | — | 全自定义 |

所有预设共有：`<C-space>` 打开菜单/文档，`<C-k>` 切换签名帮助。

### 4.4 snippet 后端三选项

- `'native'`：用 `vim.snippet`（Neovim 0.10+ 内置，最简，无第三方依赖）
- `'luasnip'`：LuaSnip（功能最全，kickstart 默认）
- `'mini_snippets'`：mini.snippets（mini.nvim 生态）

### 4.5 高级特性

- **cmdline 补全**：`cmdline = { enabled = true }` + sources 配置
- **终端补全**（0.11+）：`term = { enabled = true }`
- **auto-brackets**：基于 semantic tokens 自动补全括号（默认开启）
- **社区源**：通过 `blink.compat` 兼容 nvim-cmp 源
- ** frecency + proximity bonus**：模糊匹配的智能排序

### 4.6 vim.snippet（原生 snippet API）

```lua
-- Neovim 0.10+ 内置
vim.snippet.expand('for ${1=i}, ${2=limit} do\n  $0\nend')
```

`$1`、`$2` 是 tabstop，`$0` 是终点，`${1:default}` 带默认值。

---

## 5. Lua / LuaJIT 在 Neovim 中的关键事实

### 5.1 LuaJIT 兼容性

- **语法兼容 Lua 5.1**
- **额外支持**（LuaJIT 扩展，Neovim 中可用）：
  - `goto` / `::label::`（Lua 5.2）
  - 整数除法 `//`（Lua 5.3）
  - 位运算 `bit` 模块（LuaJIT 扩展，不是 5.3 的 `&` `|`）
  - `continue` 风格用 `goto continue`
- **不兼容** Lua 5.3+ 的：整数类型（LuaJIT 一律 double）、`&` `|` `~` 位运算符

### 5.2 元表（metatable）核心

```lua
-- OOP 模式
local Animal = {}
Animal.__index = Animal  -- 关键：让实例继承方法

function Animal.new(name)
  local self = setmetatable({}, Animal)
  self.name = name
  return self
end

function Animal:speak()  -- 注意冒号语法糖（隐式 self）
  return "I am " .. self.name
end

local a = Animal.new("Rex")
print(a:speak())  -- "I am Rex"

-- __call 元方法（让 table 像函数一样可调用）
setmetatable(Animal, { __call = function(_, ...) return Animal.new(...) end })
local b = Animal("Buddy")  -- 等价于 Animal.new("Buddy")
```

常用元方法：`__index`、`__newindex`、`__call`、`__tostring`、`__eq`、`__add`、`__len`、`__pairs`。

### 5.3 Neovim 中的 vim.fn / vim.api / vim.opt

- `vim.fn.xxx()` — 调用 Vimscript 函数（如 `vim.fn.stdpath('config')`），慢但覆盖全
- `vim.api.nvim_xxx()` — C API 的 Lua 绑定，最快，buffer/window 操作首选
- `vim.opt.xxx` — 选项设置的面向对象接口（支持表/列表操作，如 `vim.opt.listchars:append(...)`）
- `vim.o.xxx` / `vim.go.xxx` / `vim.bo.xxx` / `vim.wo.xxx` — 全局/全局 only/buffer-local/window-local 选项

### 5.4 vim.uv / vim.loop（libuv 绑定）

```lua
vim.uv.fs_stat(path)        -- 同步文件状态
vim.uv.fs_mkdir(path, 448)  -- 创建目录
vim.uv.new_timer()          -- 定时器
```

`vim.loop` 是 `vim.uv` 的旧名（已弃用但兼容）。

---

## 6. 0.12 其他值得纳入的现代 API

| API | 作用 |
|---|---|
| `vim.loader.enable()` | 缓存编译的 Lua 模块，加速启动（kickstart 第一行） |
| `vim.hl.on_yank()` / `vim.hl.range()` | 高亮（0.11+ 从 `vim.highlight` 重命名） |
| `vim.iter(iterable)` | 迭代器/函数式工具（map/filter/take/any/...） |
| `vim.snippet.expand()` | 原生 snippet 展开（0.10+） |
| `vim.lsp.completion.enable()` | 原生 LSP 补全（0.11+） |
| `vim.system(cmd, opts):wait()` | 异步/同步执行外部命令 |
| `vim.schedule(fn)` / `vim.schedule_wrap(fn)` | 在事件循环的下一轮执行 |
| `vim.deprecate(name, hint, version)` | 标记弃用 API |
| `vim.health` | `:checkhealth` 框架 |
| `vim.diagnostic.config({ virtual_lines = ... })` | 行下虚拟线诊断 |
| `vim.treesitter.language.add/start/foldexpr()` | 原生 treesitter API |
| `vim.keymap.set` / `vim.keymap.del` | 按键映射 API |
| `vim.notify(msg, level)` | 通知（可被 noice.nvim 等覆盖） |

---

## 7. 推荐插件清单（2026-06 现代化）

| 插件 | 用途 | 备注 |
|---|---|---|
| `nvim-lspconfig` | LSP server 默认配置 | 配合 `vim.lsp.config/enable` |
| `mason.nvim` (+ `mason-lspconfig`, `mason-tool-installer`) | 工具安装 | 注意 `mason-org` 组织 |
| `blink.cmp` | 补全引擎 | V1 (`'1.*'`) |
| `LuaSnip` 或 `vim.snippet` | snippet | LuaSnip 功能全；vim.snippet 零依赖 |
| `nvim-treesitter` | 高亮/解析 | `version = 'main'` |
| `telescope.nvim` (+ `plenary.nvim`, `telescope-fzf-native`, `telescope-ui-select`) | 模糊查找 | |
| `conform.nvim` | 格式化 | 推荐（替代 null-ls） |
| `nvim-lint` | linter | 推荐（替代 null-ls） |
| `nvim-dap` (+ `nvim-dap-ui`, `nvim-dap-go`/等) | 调试器 | DAP 客户端 |
| `mini.nvim` | 工具集 | ai/surround/statusline/icons |
| `which-key.nvim` | 按键提示 | |
| `gitsigns.nvim` | Git 集成 | |
| `todo-comments.nvim` | TODO 高亮 | |
| `guess-indent.nvim` | 缩进检测 | |
| `fidget.nvim` | LSP 状态通知 | |
| `tokyonight.nvim` | colorscheme | kickstart 默认 |

---

## 8. 编写护栏（所有 SMOL 子代理必须遵守）

1. **以本文件为唯一事实源**——若与旧教程冲突，以本文件为准
2. **所有代码示例必须可运行**——注明 Neovim 版本要求
3. **Obsidian Markdown 规范**：
   - frontmatter 必填（`title` + `updated`）
   - 交叉引用用 `[[文件名]]`（不带扩展名）
   - 重要提示用 callout（`> [!IMPORTANT]`、`> [!tip]-`）
   - 特殊符号（`<T>`、`[Attribute]`）用反引号包裹
4. **参考答案用可折叠 callout**：`> [!tip]- 练习 N 参考答案`，每行加 `> ` 前缀
5. **多个参考答案之间必须空一行**
6. **表格前必须空一行**
7. **禁止 HTML `<details>` 标签**，必须用 Obsidian callout
8. **禁止 TBD/TODO 占位符**
9. **每个新概念必须有可运行代码 + 至少 1 个练习 + 参考答案**
10. **单文件控制在 400-700 行**（深化版比原版长，但避免冗余）
