---
title: "09 — 现代 LSP 配置：vim.lsp.config / enable"
updated: 2026-06-05
---

# 09 — 现代 LSP 配置：vim.lsp.config / enable

> 所属计划: Neovim + Lua 配置实战 (现代版)
> 预计耗时: 55 分钟
> 前置知识: 07-vim-pack（插件管理）、08-modern-plugin-patterns（PackChanged hook）

---

## 1. 概念讲解

### Neovim 0.12 的原生 LSP API

在 0.12 之前，配置 LSP 依赖 `nvim-lspconfig` + `lspconfig.xxx.setup()`。0.12 引入了原生配置 API：

```lua
-- 旧方式 (0.11 以前):
local lspconfig = require('lspconfig')
lspconfig.lua_ls.setup({ settings = { Lua = { ... } } })

-- 新方式 (0.12+):
vim.lsp.config('lua_ls', { settings = { Lua = { ... } } })
vim.lsp.enable('lua_ls')
```

**核心变化**：
- `vim.lsp.config(name, config)` — 注册一个 LSP 服务器配置（不启动）
- `vim.lsp.enable(name)` — 启用该配置（根据文件类型自动启动服务器）
- `nvim-lspconfig` 仍是必要的——它提供了各语言服务器的默认配置（启动命令、文件类型匹配等），只是不再需要手动调用 `setup()` 了

### 涉及的关键插件

| 插件 | 作用 | 0.12 变化 |
|------|------|----------|
| `nvim-lspconfig` | 提供各 LSP 的默认配置 | 仍然需要，但使用方式变为 `vim.lsp.config()` |
| `mason.nvim` | 管理 LSP/DAP/Linter 安装 | 无变化 |
| `mason-lspconfig.nvim` | 桥接 mason 和 lspconfig | 配合新版 API |
| `mason-tool-installer.nvim` | 自动安装 mason 工具 | kickstart.nvim 推荐方式 |
| `fidget.nvim` | LSP 状态通知 | 无变化 |

### LspAttach 事件（同旧版，但更干净）

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(event)
    local client = vim.lsp.get_client_by_id(event.data.client_id)
    local buf = event.buf

    -- 设置局部按键映射
    vim.keymap.set('n', 'grn', vim.lsp.buf.rename, { buffer = buf, desc = 'LSP: Rename' })

    -- 启用文档高亮（如果服务器支持）
    if client:supports_method('textDocument/documentHighlight', buf) then
      vim.api.nvim_create_autocmd('CursorHold', {
        buffer = buf, callback = vim.lsp.buf.document_highlight,
      })
    end
  end,
})
```

### 常用 LSP 函数

| 函数 | 描述 | 典型映射 |
|------|------|---------|
| `vim.lsp.buf.definition` | 跳转到定义 | `grd` |
| `vim.lsp.buf.references` | 查找引用 | `grr` |
| `vim.lsp.buf.hover` | 悬停文档 | `K` |
| `vim.lsp.buf.rename` | 重命名 | `grn` |
| `vim.lsp.buf.code_action` | 代码操作 | `gra` |
| `vim.lsp.buf.declaration` | 跳转到声明 | `grD` |
| `vim.lsp.buf.document_highlight` | 高亮引用 | `CursorHold` |
| `vim.diagnostic.open_float` | 浮动诊断 | 自动（配置 `jump.on_jump`） |
| `vim.diagnostic.goto_next` | 下一诊断 | `]d` |
| `vim.diagnostic.goto_prev` | 上一诊断 | `[d` |

---

## 2. 代码示例

### 完整的 kickstart 风格 LSP 配置

```lua
-- init.lua Section: LSP
do
  -- LSP 状态通知
  vim.pack.add { gh 'j-hui/fidget.nvim' }
  require('fidget').setup {}

  -- LspAttach: 设置 LSP 按键映射和高亮
  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('kickstart-lsp-attach', { clear = true }),
    callback = function(event)
      local map = function(keys, func, desc, mode)
        vim.keymap.set(mode or 'n', keys, func, { buffer = event.buf, desc = 'LSP: ' .. desc })
      end

      map('grn', vim.lsp.buf.rename, '[R]e[n]ame')
      map('gra', vim.lsp.buf.code_action, 'Code [A]ction', { 'n', 'x' })
      map('grD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')

      -- 文档高亮
      local client = vim.lsp.get_client_by_id(event.data.client_id)
      if client and client:supports_method('textDocument/documentHighlight', event.buf) then
        local aug = vim.api.nvim_create_augroup('lsp-highlight-' .. event.buf, { clear = true })
        vim.api.nvim_create_autocmd({ 'CursorHold', 'CursorHoldI' }, {
          buffer = event.buf, group = aug, callback = vim.lsp.buf.document_highlight,
        })
        vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, {
          buffer = event.buf, group = aug, callback = vim.lsp.buf.clear_references,
        })
      end

      -- Inlay hints 切换
      if client and client:supports_method('textDocument/inlayHint', event.buf) then
        map('<leader>th', function()
          vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = event.buf })
        end, '[T]oggle Inlay [H]ints')
      end
    end,
  })

  -- 服务器配置（新 API）
  ---@type table<string, vim.lsp.Config>
  local servers = {
    -- clangd = {},
    -- pyright = {},

    stylua = {},  -- Lua 格式化工具

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
  }

  -- 安装所需插件
  vim.pack.add {
    gh 'neovim/nvim-lspconfig',
    gh 'mason-org/mason.nvim',
    gh 'mason-org/mason-lspconfig.nvim',
    gh 'WhoIsSethDaniel/mason-tool-installer.nvim',
  }

  require('mason').setup {}

  -- 自动安装所有 servers 中列出的 LSP
  local ensure_installed = vim.tbl_keys(servers or {})
  require('mason-tool-installer').setup { ensure_installed = ensure_installed }

  -- 注册并启用每个服务器（新版 vim.lsp.config API）
  for name, server in pairs(servers) do
    vim.lsp.config(name, server)
    vim.lsp.enable(name)
  end
end
```

**运行方式:**
1. 将上述代码放入 `init.lua` 的一个 do 块
2. 启动 Neovim，mason 会自动安装 `lua_ls` 和 `stylua`
3. 打开 `.lua` 文件，`:LspInfo` 确认 server 已附着（0.12 中 `:LspInfo` 改为 `:checkhealth vim.lsp`）
4. 悬停在 `vim.keymap.set` 上按 `K` 查看文档

---

## 3. 练习

### 练习 1: 配置你主要语言的 LSP

选择一个你常用的语言（Python/Pyright, Rust/rust-analyzer, Go/gopls），添加到 `servers` 表中：

```lua
{
  pyright = {},
  -- 或
  rust_analyzer = {},
  -- 或
  gopls = {},
}
```

重启 Neovim，验证 server 自动安装和附着。

### 练习 2: 诊断导航

故意在代码中引入错误，观察 `signcolumn` 中的诊断标记。使用：
- `[d` / `]d` 在诊断间跳转
- 观察跳转时自动弹出的浮动诊断窗口

### 练习 3: 使用 `:lsp` 命令族

Neovim 0.12 引入了统一的 `:lsp` 命令。尝试：
```vim
:lsp restart    " 重启 LSP
:lsp stop       " 停止 LSP
:lsp start      " 启动 LSP
```

---

## 4. 扩展阅读

- [`:help vim.lsp.config`](https://neovim.io/doc/user/lsp.html#vim.lsp.config) — 新 API 完整参考
- [`:help lsp`](https://neovim.io/doc/user/lsp.html) — LSP 总览
- [nvim-lspconfig 支持的服务器列表](https://github.com/neovim/nvim-lspconfig/blob/master/doc/server_configurations.md)
- [mason.nvim 可用包列表](https://github.com/williamboman/mason.nvim#packages)

---

## 常见陷阱

- **`vim.lsp.config()` 和 `vim.lsp.enable()` 是两个步骤**：只调用 `config` 不会启动服务器。必须调用 `enable`。
- **`nvim-lspconfig` 仍然需要安装**：它在 `require('lspconfig')` 后才注册各服务器的默认配置到 `vim.lsp.config()`。没有它，`vim.lsp.config('lua_ls', ...)` 会因为没有默认配置而失败。
- **mason 安装和服务器配置的顺序**：`mason-tool-installer` 异步安装工具，但 `vim.lsp.enable()` 是同步的。首次启动时，如果 mason 还没来得及安装服务器，LSP 不会附着。重启后即正常。
- **capabilities 不再需要手动管理**：0.12 中 `vim.lsp.enable()` 自动设置正确的 capabilities。
- **`:LspInfo` 命令在 0.12 中已移除**：用 `:checkhealth vim.lsp` 替代。
- **lua_ls 的 workspace 配置**：如果不配置 `checkThirdParty = false`，在大型项目中 lua_ls 会扫描 `node_modules` 等目录导致卡顿。
