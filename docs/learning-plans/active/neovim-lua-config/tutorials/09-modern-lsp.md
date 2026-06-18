---
title: "09 — 现代 LSP 配置：0.12 默认按键、lsp/*.lua 与模块化"
updated: 2026-06-18
---

# 09 — 现代 LSP 配置：0.12 默认按键、`lsp/*.lua` 与模块化

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 70 分钟
> 前置知识: [[07-vim-pack]]、[[08-modern-plugin-patterns]]

---

## 1. 概念讲解

### 1.1 从 `lspconfig.setup` 到 `vim.lsp.config / enable`

在 Neovim 0.12 之前，配置 LSP 几乎离不开 `nvim-lspconfig` 的 `lspconfig.xxx.setup()`。0.12 把配置与启用拆成两个原生命令：

```lua
-- 旧方式 (0.11 及更早):
local lspconfig = require('lspconfig')
lspconfig.lua_ls.setup({ settings = { Lua = { runtime = { version = 'LuaJIT' } } } })

-- 新方式 (0.12+):
vim.lsp.config('lua_ls', {
  settings = { Lua = { runtime = { version = 'LuaJIT' } } },
})
vim.lsp.enable('lua_ls')
```

- `vim.lsp.config(name, config)` —— 注册（或覆盖）某个 LSP 的配置，**不启动服务器**。
- `vim.lsp.enable(name)` —— 启用已注册的配置，Neovim 会在匹配 `filetypes` 的 buffer 上自动启动服务器。
- `nvim-lspconfig` **仍然需要安装**：它提供了各语言服务器的默认 `cmd`、`filetypes`、`root_markers` 等。只是你不再需要调用 `setup()`。

> [!IMPORTANT]
> 本教程所有代码均要求 **Neovim 0.12.3+**。旧版本可能缺少 `vim.lsp.config()`、`vim.lsp.enable()` 或默认全局按键。

### 1.2 0.12 默认全局 LSP 按键（最大变化）

Neovim 0.12 在启动时会**无条件**创建以下全局映射。你**不再需要**在 `LspAttach` 里手动绑定 `grn`、`gra`、`gri` 等。

| 按键 | 模式 | 功能 |
|---|---|---|
| `gra` | n, x | `vim.lsp.buf.code_action()` |
| `gri` | n | `vim.lsp.buf.implementation()` |
| `grn` | n | `vim.lsp.buf.rename()` |
| `grr` | n | `vim.lsp.buf.references()` |
| `grt` | n | `vim.lsp.buf.type_definition()` |
| `grx` | n | `vim.lsp.codelens.run()` |
| `gO` | n | `vim.lsp.buf.document_symbol()` |
| `<C-S>` | i | `vim.lsp.buf.signature_help()` |

验证方式：在任意已附着 LSP 的 buffer 中执行：

```vim
:verbose map grn
```

输出应包含 `<Lua function ...>`，表示该映射已由核心默认创建。

> [!NOTE]
> kickstart.nvim `master` 分支仍保留 `map('grn', ...)`、`map('gra', ...)` 等手动映射。这不会出错——后定义的 buffer-local 映射会覆盖默认映射——但本质上是历史习惯。现代配置可以直接省略，除非你希望把它改成 Telescope picker。

### 1.2.1 常用 LSP 函数与默认按键速查

| LSP 函数 | 功能 | 0.12 默认按键 |
|---|---|---|
| `vim.lsp.buf.rename` | 重命名符号 | `grn` |
| `vim.lsp.buf.code_action` | 代码操作 | `gra` |
| `vim.lsp.buf.references` | 查找引用 | `grr` |
| `vim.lsp.buf.implementation` | 跳转实现 | `gri` |
| `vim.lsp.buf.type_definition` | 跳转类型定义 | `grt` |
| `vim.lsp.buf.document_symbol` | 文档符号列表 | `gO` |
| `vim.lsp.codelens.run` | 运行 CodeLens | `grx` |
| `vim.lsp.buf.signature_help` | 函数签名帮助 | `<C-S>`（插入模式） |
| `vim.lsp.buf.hover` | 悬停文档 | `K` |
| `vim.lsp.buf.definition` | 跳转到定义 | 无（`tagfunc` 提供 `<C-]>`） |
| `vim.lsp.buf.declaration` | 跳转到声明 | 无 |
| `vim.diagnostic.goto_next` / `goto_prev` | 诊断跳转 | `]d` / `[d` |


### 1.3 Buffer-local 默认（LSP 附着时自动设置）

当 LSP client 附着到 buffer 时，0.12 还会自动设置以下 buffer-local 选项和映射：

| 设置 | 值 | 效果 |
|---|---|---|
| `'omnifunc'` | `vim.lsp.omnifunc` | 在插入模式按 `<C-X><C-O>` 触发 LSP 补全 |
| `'tagfunc'` | `vim.lsp.tagfunc` | `<C-]>`、`:tjump`、`<C-W>]` 等使用 LSP 跳转 |
| `'formatexpr'` | `vim.lsp.formatexpr` | `gq` 使用 LSP 格式化（服务器支持时） |
| `K` | `vim.lsp.buf.hover()` | 普通模式按 `K` 显示 hover 文档 |
| document color | 启用 | 文档颜色高亮（如 CSS、Tailwind 颜色） |
| diagnostics | 启用 | 诊断标记、虚拟文本、浮动窗口等 |

如果你不喜欢这些默认行为，可以在 `LspAttach` 中禁用：

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    vim.bo[ev.buf].formatexpr = nil
    vim.bo[ev.buf].omnifunc = nil
    -- 只有当 Neovim 确实创建了 K 映射时才删除
    pcall(vim.keymap.del, 'n', 'K', { buf = ev.buf })
    vim.lsp.document_color.enable(false, { bufnr = ev.buf })
  end,
})
```


### 1.4 `lsp/<name>.lua` 文件配置模式（模块化关键）

0.12 支持在 `runtimepath` 的 `lsp/` 目录下按 `<配置名>.lua` 组织配置。这是官方推荐的模块化方式。

创建文件 `~/.config/nvim/lsp/lua_ls.lua`：

```lua
return {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.luarc.jsonc', '.git' },
  settings = {
    Lua = {
      runtime = { version = 'LuaJIT' },
      workspace = { checkThirdParty = false },
      format = { enable = false },
    },
  },
}
```

然后在 `init.lua` 中只需：

```lua
vim.lsp.enable('lua_ls')
```

> [!IMPORTANT]
> 文件名必须和 `vim.lsp.enable()` 中传入的名字**完全一致**。例如 `lsp/lua_ls.lua` 对应 `vim.lsp.enable('lua_ls')`。

### 1.5 配置合并优先级（低 → 高）

同一个 LSP 的配置可能来自多个来源。0.12 按以下顺序合并（后覆盖前）：

1. `vim.lsp.config('*', {...})` —— 通配配置，对所有服务器生效，最适合放全局 `capabilities`。
2. `lsp/<config>.lua` 文件 —— runtimepath 上的配置文件。
3. `after/lsp/<config>.lua` 文件 —— 用于覆盖 `nvim-lspconfig` 提供的默认配置。
4. 任意位置的 `vim.lsp.config(name, {...})` 调用 —— 最高优先级。

合并使用 `vim.tbl_deep_extend('force', ...)`，因此表会被递归覆盖，非表值会被直接替换。

典型用法：在 `init.lua` 顶部设置全局 `capabilities`，关闭大项目的文件监听以提升性能：

```lua
local capabilities = vim.lsp.protocol.make_client_capabilities()
if capabilities.workspace then
  capabilities.workspace.didChangeWatchedFiles = nil
end
vim.lsp.config('*', { capabilities = capabilities })
```

> [!NOTE]
> 0.12 的 `vim.lsp.enable()` 已经会自动设置正确的 `capabilities`，**通常不需要**再手动调用 `make_client_capabilities()`。上面的代码只在需要修改默认 capabilities 时才写。

### 1.6 `vim.lsp.completion.enable()` 简介预告

0.11+ 提供了一套**零插件依赖**的原生 LSP 补全：

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if client and client:supports_method('textDocument/completion', ev.buf) then
      vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
    end
  end,
})
```

- `autotrigger = true`：输入时自动弹出补全菜单。
- 确认项默认用 `<C-Y>`。
- 适合追求极简、零依赖的配置。

> [!IMPORTANT]
> 本教程第 17 节会深入讲解 `vim.lsp.completion` 与 `blink.cmp` 的对比、按键预设、snippet 后端选择。这里只需知道：0.12 不装任何补全插件也能用 LSP 补全。

| 特性 | `vim.lsp.completion` | `blink.cmp` |
|---|---|---|
| 依赖 | 无 | 需安装 blink.cmp |
| 自动触发 | 支持 | 支持 |
| 非 LSP 源 | 无 | path、snippets、buffer、社区源 |
| 模糊匹配 | 基础 | 强（frecency、proximity） |
| 推荐场景 | 极简配置 | 日常主力配置 |

### 1.7 `LspAttach` 完整实战：还需要手动设什么？

既然 0.12 已经提供了 `gra`、`grn`、`grr`、`gri`、`gO`、`grt`、`grx`、`<C-S>`、`K`，`LspAttach` 里只需要补充默认**没有**的功能：

- `grd`：`vim.lsp.buf.definition()`（不过 `tagfunc` 的 `<C-]>` 已经能实现类似效果）。
- `grD`：`vim.lsp.buf.declaration()`。
- 用 Telescope 覆盖 `grr` / `gri` / `gO`（如果你安装了 telescope）。
- `CursorHold` / `CursorMoved` 文档高亮。
- inlay hints、codelens 的切换/刷新。
- 用 `client:supports_method(method, buf)` 做能力检查。

核心模板：

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  group = vim.api.nvim_create_augroup('my-lsp-attach', { clear = true }),
  callback = function(ev)
    local buf = ev.buf
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if not client then return end

    local map = function(keys, func, desc, mode)
      vim.keymap.set(mode or 'n', keys, func, { buffer = buf, desc = 'LSP: ' .. desc })
    end

    -- 默认没有的直接定义映射
    map('grd', vim.lsp.buf.definition, '[G]oto [D]efinition')
    map('grD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')

    -- 用 Telescope 覆盖默认的 grr/gri/gO（可选）
    -- map('grr', require('telescope.builtin').lsp_references, '[G]oto [R]eferences')
    -- map('gri', require('telescope.builtin').lsp_implementations, '[G]oto [I]mplementation')
    -- map('gO', require('telescope.builtin').lsp_document_symbols, 'Open Document Symbols')

    -- 文档高亮：光标停留时高亮当前符号的所有引用
    if client:supports_method('textDocument/documentHighlight', buf) then
      local aug = vim.api.nvim_create_augroup('lsp-highlight-' .. buf, { clear = true })
      vim.api.nvim_create_autocmd({ 'CursorHold', 'CursorHoldI' }, {
        buffer = buf,
        group = aug,
        callback = vim.lsp.buf.document_highlight,
      })
      vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, {
        buffer = buf,
        group = aug,
        callback = vim.lsp.buf.clear_references,
      })
    end

    -- Inlay hints 切换
    if client:supports_method('textDocument/inlayHint', buf) then
      map('<leader>th', function()
        vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = buf })
      end, '[T]oggle Inlay [H]ints')
    end

    -- Codelens 刷新（grx 已经绑定 run，这里只设一个手动刷新键）
    if client:supports_method('textDocument/codeLens', buf) then
      map('<leader>cc', vim.lsp.codelens.refresh, '[C]odelens [R]efresh')
    end
  end,
})
```

> [!NOTE]
> `client:supports_method(method, buf)` 是 0.10+ 推荐的能力检查方式。它比旧的 `client.server_capabilities` 更可靠，因为某些能力会受 buffer 或动态注册影响。

### 1.8 `:lsp` 命令族

0.12 引入了统一的 `:lsp` 命令管理 LSP 生命周期：

| 命令 | 作用 |
|---|---|
| `:lsp enable [name]` | 启用某个已注册配置；无参数则启用当前 buffer 对应配置 |
| `:lsp disable [name]` | 禁用配置并停止运行中的服务器 |
| `:lsp restart [name]` | 重启（无参数 = 重启当前 buffer 的所有 client） |
| `:lsp stop [name]` | 停止服务器（不修改启用状态） |

典型场景：

```vim
" 修改了 lua_ls 的 settings 后，让它立即生效
:lsp restart lua_ls

" 当前 buffer 所有 LSP 行为异常，先停掉排查
:lsp stop
" ... 检查 ...
:lsp enable
```

> [!TIP]
> `:lsp restart` 会触发 `LspDetach` 再触发 `LspAttach`，因此你写在 `LspAttach` 中的 buffer-local 映射和高亮 autocmd 会被重新创建。

### 1.9 Handlers 与 Capabilities 进阶（简述）

#### Handler 优先级

当同一个 LSP 方法有多处 handler 时，0.12 按以下优先级选择：

1. 直接 `client:request(method, params, handler)` 传入的 handler。
2. `vim.lsp.handlers[method]` 全局 handler。
3. `vim.lsp.start({ handlers = { ... } })` 启动时传入的 handler。
4. `vim.lsp.buf_request_all(..., handler)` 等批量请求传入的 handler。

平时配置 LSP 很少需要自定义 handler，但排查“为什么诊断/补全行为不对”时，知道这个顺序能帮你定位是哪个插件覆盖了默认行为。

#### Capabilities

- 0.12 中 `vim.lsp.enable()` 已经自动设置 `capabilities`。
- 除非你要关闭某项能力（如文件监听）或整合 `cmp-nvim-lsp` 的扩展能力，否则不需要手动构造 `make_client_capabilities()`。

### 1.10 健康检查

旧命令 `:LspInfo` 在 0.12 中已移除，取而代之的是：

```vim
:checkhealth vim.lsp
```

它会报告：

- 哪些 LSP 配置已启用
- 每个 buffer 上附着的 client
- 文件监听性能提示
- 配置冲突或缺失的 root marker

养成“LSP 行为异常时先跑 `:checkhealth vim.lsp`”的习惯。

### 1.11 Inlay Hints / Codelens / Linked Editing（默认禁用）

这三项能力默认关闭，需要在 `LspAttach` 或全局手动启用：

```lua
-- Inlay hints：全局默认开启
vim.lsp.inlay_hint.enable(true)

-- 或在 LspAttach 中按能力/按 buffer 启用
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if client and client:supports_method('textDocument/inlayHint', ev.buf) then
      vim.lsp.inlay_hint.enable(true, { bufnr = ev.buf })
    end

    if client and client:supports_method('textDocument/codeLens', ev.buf) then
      vim.lsp.codelens.refresh()
      -- 每次保存后刷新 codelens
      vim.api.nvim_create_autocmd({ 'BufEnter', 'CursorHold', 'InsertLeave' }, {
        buffer = ev.buf,
        callback = vim.lsp.codelens.refresh,
      })
    end

    if client and client:supports_method('textDocument/linkedEditingRange', ev.buf) then
      vim.bo[ev.buf].tagfunc = nil  -- linked editing 与某些旧配置冲突时可选
    end
  end,
})
```

> [!NOTE]
> Linked editing range 让重命名 HTML/XML 标签时同步修改开闭标签。Neovim 0.12 会在支持的服务器上自动处理，通常不需要额外代码。

---

## 2. 代码示例

### 2.1 最小模块化示例：`lsp/lua_ls.lua`

把你的 LSP 配置从 `init.lua` 中拆出来，每个语言一个文件。

文件 `~/.config/nvim/lsp/lua_ls.lua`：

```lua
return {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.luarc.jsonc', '.git' },
  settings = {
    Lua = {
      runtime = { version = 'LuaJIT' },
      workspace = { checkThirdParty = false },
      format = { enable = false },
    },
  },
}
```

`init.lua` 中：

```lua
-- 一行启用，无需再写 settings
vim.lsp.enable('lua_ls')
```

> [!TIP]
> 如果同时存在 `lsp/lua_ls.lua` 和 `vim.lsp.config('lua_ls', {...})`，两者会按第 1.5 节的优先级合并。通常推荐把具体语言的配置放进 `lsp/*.lua`，把全局 capabilities 放在 `vim.lsp.config('*', ...)`。

### 2.2 完整的 kickstart 风格 LSP 配置

下面的配置体现了 0.12 的推荐做法：

- 用 `vim.lsp.config('*', ...)` 放全局 capabilities。
- 用 `servers` 表 + `mason-tool-installer` 自动安装。
- `LspAttach` 中**不重复**设置 0.12 默认的 `gra`/`grn`/`grr`/`gri`/`gO`/`grt`/`grx`/`K`/`<C-S>`。
- 只补充 `grd`、`grD`、文档高亮、inlay hints 切换、codelens 刷新。

```lua
-- init.lua Section: LSP
-- 假设已有 gh(repo) -> 'https://github.com/' .. repo 的辅助函数
local function gh(repo) return 'https://github.com/' .. repo end

do
  -- LSP 状态通知
  vim.pack.add { gh 'j-hui/fidget.nvim' }
  require('fidget').setup {}

  -- 全局 capabilities：关闭文件监听，提升大项目性能
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  if capabilities.workspace then
    capabilities.workspace.didChangeWatchedFiles = nil
  end
  vim.lsp.config('*', { capabilities = capabilities })

  -- LspAttach：只补充默认没有的功能
  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('kickstart-lsp-attach', { clear = true }),
    callback = function(event)
      local buf = event.buf
      local client = vim.lsp.get_client_by_id(event.data.client_id)
      if not client then return end

      local map = function(keys, func, desc, mode)
        vim.keymap.set(mode or 'n', keys, func, { buffer = buf, desc = 'LSP: ' .. desc })
      end

      -- 0.12 默认已提供：gra grn grr gri gO grt grx K <C-S>
      -- 这里只补充默认没有的
      map('grd', vim.lsp.buf.definition, '[G]oto [D]efinition')
      map('grD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')

      -- 如果你装了 telescope，可以覆盖默认的 grr/gri/gO
      -- local builtin = require('telescope.builtin')
      -- map('grr', builtin.lsp_references, '[G]oto [R]eferences')
      -- map('gri', builtin.lsp_implementations, '[G]oto [I]mplementation')
      -- map('gO', builtin.lsp_document_symbols, 'Open Document Symbols')

      -- 文档高亮
      if client:supports_method('textDocument/documentHighlight', buf) then
        local aug = vim.api.nvim_create_augroup('lsp-highlight-' .. buf, { clear = true })
        vim.api.nvim_create_autocmd({ 'CursorHold', 'CursorHoldI' }, {
          buffer = buf,
          group = aug,
          callback = vim.lsp.buf.document_highlight,
        })
        vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, {
          buffer = buf,
          group = aug,
          callback = vim.lsp.buf.clear_references,
        })
      end

      -- Inlay hints 切换
      if client:supports_method('textDocument/inlayHint', buf) then
        map('<leader>th', function()
          vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = buf })
        end, '[T]oggle Inlay [H]ints')
      end

      -- Codelens 刷新
      if client:supports_method('textDocument/codeLens', buf) then
        map('<leader>cc', vim.lsp.codelens.refresh, '[C]odelens [R]efresh')
        vim.api.nvim_create_autocmd({ 'BufEnter', 'InsertLeave' }, {
          buffer = buf,
          callback = vim.lsp.codelens.refresh,
        })
      end
    end,
  })

  -- 服务器配置表
  ---@type table<string, vim.lsp.Config>
  local servers = {
    lua_ls = {
      on_init = function(client)
        client.server_capabilities.documentFormattingProvider = false
        if client.workspace_folders then
          local path = client.workspace_folders[1].name
          if path ~= vim.fn.stdpath('config')
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
    -- gopls = {},
  }

  -- 安装 LSP 相关插件
  vim.pack.add {
    gh 'neovim/nvim-lspconfig',
    gh 'mason-org/mason.nvim',
    gh 'mason-org/mason-lspconfig.nvim',
    gh 'WhoIsSethDaniel/mason-tool-installer.nvim',
  }

  require('mason').setup {}

  -- 自动安装 servers 表里的所有工具
  local ensure_installed = vim.tbl_keys(servers)
  -- stylua 不是 LSP，只是让 mason 一起安装的格式化工具
  table.insert(ensure_installed, 'stylua')
  require('mason-tool-installer').setup { ensure_installed = ensure_installed }

  -- 注册并启用每个服务器
  for name, server in pairs(servers) do
    vim.lsp.config(name, server)
    vim.lsp.enable(name)
  end
end
```

**运行方式：**

1. 将上述代码放入 `init.lua` 的一个 `do ... end` 块。
2. 启动 Neovim，首次会弹出 `vim.pack.add()` 安装确认，按 `a` 允许全部。
3. `mason-tool-installer` 会自动安装 `lua_ls` 和 `stylua`。
4. 打开 `.lua` 文件，执行 `:checkhealth vim.lsp` 确认 `lua_ls` 已附着。
5. 悬停在 `vim.keymap.set` 上按 `K`，应弹出 hover 文档。

---

## 3. 练习

### 练习 1: 配置你主要语言的 LSP

选择 Python、Rust 或 Go，把对应的 LSP 加入 `servers` 表，并验证自动安装与附着。

### 练习 2: 验证 0.12 默认按键存在

打开任意已附着 LSP 的文件，用 `:verbose map` 验证以下映射：

- `grn` → rename
- `gra` → code_action
- `gri` → implementation
- `grr` → references
- `gO` → document_symbol
- `<C-S>`（插入模式）→ signature_help

### 练习 3: 创建 `lsp/<lang>.lua` 配置文件

把你主要语言的 LSP 配置拆分成 `~/.config/nvim/lsp/<lang>.lua`，然后在 `init.lua` 中只保留 `vim.lsp.enable('<lang>')`。

### 练习 4: 用 `:lsp restart` 让配置变更生效

修改 `lua_ls` 的 `settings.Lua.runtime.version` 或 `pyright` 的 `python.pythonPath` 后，不重启 Neovim，直接执行 `:lsp restart` 并确认新设置生效。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 以 Python / `pyright` 为例，在 `servers` 表中添加：
>
> ```lua
> local servers = {
>   stylua = {},
>   lua_ls = { ... },
>
>   pyright = {},
> }
> ```
>
> 重启 Neovim 后，`mason-tool-installer` 会自动安装 `pyright`。验证：
>
> 1. 打开 `.py` 文件，执行 `:checkhealth vim.lsp`，应看到 `pyright` 状态为 attached。
> 2. 输入 `import os` 后悬停 `os` 按 `K`，应弹出模块文档。
> 3. 故意写 `prin("hello")`，signcolumn 应出现诊断标记。
>
> 如果需要指定虚拟环境路径：
>
> ```lua
> pyright = {
>   settings = {
>     python = { pythonPath = '.venv/bin/python' },
>   },
> }
> ```
>
> **关键点**：空表 `{}` 表示使用 `nvim-lspconfig` 提供的默认配置。`rust_analyzer` 和 `gopls` 同理，只需把名字加入 `servers` 表即可。

> [!tip]- 练习 2 参考答案
> 在已附着 LSP 的 buffer 中分别执行：
>
> ```vim
> :verbose map grn
> :verbose map gra
> :verbose map gri
> :verbose map grr
> :verbose map gO
> :verbose imap <C-S>
> ```
>
> 预期输出都包含 `<Lua function ...>`，并且功能是：
>
> | 按键 | 验证命令 | 预期功能 |
> |---|---|---|
> | `grn` | `:verbose map grn` | `vim.lsp.buf.rename()` |
> | `gra` | `:verbose map gra` | `vim.lsp.buf.code_action()` |
> | `gri` | `:verbose map gri` | `vim.lsp.buf.implementation()` |
> | `grr` | `:verbose map grr` | `vim.lsp.buf.references()` |
> | `gO` | `:verbose map gO` | `vim.lsp.buf.document_symbol()` |
> | `<C-S>` | `:verbose imap <C-S>` | `vim.lsp.buf.signature_help()` |
>
> **关键点**：如果输出为空，说明该 buffer 没有 LSP client 附着；如果输出指向你自己的 `vim.keymap.set`，说明你在 `LspAttach` 中覆盖了默认映射。

> [!tip]- 练习 3 参考答案
> 以 `pyright` 为例：
>
> 1. 创建 `~/.config/nvim/lsp/pyright.lua`：
>
> ```lua
> return {
>   settings = {
>     python = {
>       analysis = {
>         typeCheckingMode = 'basic',
>       },
>     },
>   },
> }
> ```
>
> 2. 在 `init.lua` 的 servers 表里去掉 `pyright = {}`（否则两处配置会合并，可能不是你想要的效果）。
> 3. 确保 `init.lua` 中有：
>
> ```lua
> vim.lsp.enable('pyright')
> ```
>
> 4. 打开 `.py` 文件，`:checkhealth vim.lsp` 确认 attached。
>
> **关键点**：`lsp/<name>.lua` 文件名必须和 `vim.lsp.enable('<name>')` 的参数一致；配置文件中 `return` 一个表即可。

> [!tip]- 练习 4 参考答案
> 1. 修改 `lsp/lua_ls.lua`：
>
> ```lua
> return {
>   settings = {
>     Lua = {
>       runtime = { version = 'LuaJIT' },  -- 改成 'Lua 5.1' 试试
>     },
>   },
> }
> ```
>
> 2. 不退出 Neovim，执行：
>
> ```vim
> :lsp restart lua_ls
> ```
>
> 3. 打开 `.lua` 文件，`:checkhealth vim.lsp` 查看当前 client 是否已重新启动（client id 会变化）。
> 4. 用 `:lua =vim.lsp.get_active_clients({ name = 'lua_ls' })[1].config.settings` 检查新设置已加载。
>
> **关键点**：`:lsp restart` 先 detach 再 attach，所以 `LspAttach` 回调会重新执行；如果配置来自 `lsp/*.lua`，修改保存后立即 `:lsp restart` 即可生效。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [`:help vim.lsp.config`](https://neovim.io/doc/user/lsp.html#vim.lsp.config) —— 新配置 API 完整参考
- [`:help lsp-defaults`](https://neovim.io/doc/user/lsp.html#lsp-defaults) —— 0.12 默认按键与 buffer-local 默认
- [`:help lsp-config`](https://neovim.io/doc/user/lsp.html#lsp-config) —— `lsp/*.lua` 配置模式
- [`:checkhealth vim.lsp`](https://neovim.io/doc/user/lsp.html#_health) —— LSP 健康检查
- [nvim-lspconfig 支持的服务器列表](https://github.com/neovim/nvim-lspconfig/blob/master/doc/server_configurations.md)
- [mason.nvim 可用包列表](https://github.com/mason-org/mason.nvim#packages)

---

## 常见陷阱

- **误以为 `grn`/`gra` 还需要手动设置**。0.12 已经全局默认创建，重复写只会产生冗余的覆盖。用 `:verbose map grn` 验证即可。
- **`:LspInfo` 已移除**。0.12 中请用 `:checkhealth vim.lsp` 查看 LSP 状态。
- **`vim.lsp.config()` 不等于启动**。只调用 `config` 不会启动服务器，必须再调用 `enable`。
- **`nvim-lspconfig` 仍然需要安装**。它为 `vim.lsp.config()` 提供各服务器的默认配置，但不再需要手动调用 `setup()`。
- **mason 组织已迁移**。请使用 `mason-org/mason.nvim` 和 `mason-org/mason-lspconfig.nvim`，旧地址 `williamboman/mason.nvim` 虽然会重定向，但新教程应写新组织名。
- **`lsp/*.lua` 文件名必须匹配 `enable` 参数**。`lsp/lua_ls.lua` 对应 `vim.lsp.enable('lua_ls')`，大小写和 `_` 都要一致。
- **mason 首次安装异步**。首次启动时如果 mason 还没来得及装好服务器，`vim.lsp.enable()` 会找不到命令。保存配置后重启一次 Neovim 即可。
- **capabilities 通常无需手动构造**。0.12 的 `vim.lsp.enable()` 会自动设置；只有需要修改默认能力（如关闭文件监听）时才写 `make_client_capabilities()`。
