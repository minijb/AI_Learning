# 09 — LSP 配置：代码智能

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 60 分钟
> 前置知识: 07-lazy-nvim（插件的安装与懒加载）

---

## 1. 概念讲解

### 什么是 LSP？

**Language Server Protocol（LSP）** 是微软定义的一个协议，让编辑器与语言服务器通信：
- **跳转到定义** `gd`
- **查找引用** `gr`
- **悬停文档** `K`
- **代码补全** → 见第 10 节
- **诊断/错误提示**
- **代码格式化**
- **重命名** `<leader>rn`

一个编辑器 + N 种语言的 N 个 LSP 服务器 = 一致体验。

### 涉及的关键插件

| 插件 | 作用 |
|------|------|
| `nvim-lspconfig` | Neovim 内置 LSP 客户端的配置集合，简化服务器启动 |
| `mason.nvim` | 管理 LSP/DAP/Linter/Formatter 的安装（替代手动 pip/npm/go install） |
| `mason-lspconfig.nvim` | 桥接 mason 和 lspconfig，自动安装 + 配置联动 |

### 数据流

```
mason.nvim (安装)
    ↓
mason-lspconfig.nvim (确保安装 + 映射到 lspconfig)
    ↓
nvim-lspconfig (启动服务器)
    ↓
Neovim 内置 LSP 客户端 (与服务器通信)
    ↓
LspAttach 自动命令 (设置按键映射 + 功能)
```

### LspAttach 事件

每个 LSP 服务器附着到缓冲区时触发 `LspAttach`。这是设置局部按键映射的最佳时机：

```lua
vim.api.nvim_create_autocmd("LspAttach", {
    callback = function(args)
        local client = vim.lsp.get_client_by_id(args.data.client_id)
        local bufnr = args.buf

        -- 只对支持的方法设置映射
        if client.supports_method("textDocument/definition") then
            vim.keymap.set("n", "gd", vim.lsp.buf.definition, { buffer = bufnr, desc = "跳转到定义" })
        end
        -- ... 更多映射 ...
    end,
})
```

### 常用 LSP 函数

| 函数 | 描述 | 典型映射 |
|------|------|---------|
| `vim.lsp.buf.definition` | 跳转到定义 | `gd` |
| `vim.lsp.buf.references` | 查找引用 | `gr` |
| `vim.lsp.buf.hover` | 悬停文档 | `K` |
| `vim.lsp.buf.signature_help` | 函数签名 | `<C-k>` |
| `vim.lsp.buf.rename` | 重命名 | `<leader>rn` |
| `vim.lsp.buf.code_action` | 代码操作 | `<leader>ca` |
| `vim.lsp.buf.format` | 格式化 | `<leader>f` |
| `vim.diagnostic.open_float` | 浮动诊断窗口 | `<leader>e` |
| `vim.diagnostic.goto_next` | 下一个诊断 | `]d` |
| `vim.diagnostic.goto_prev` | 上一个诊断 | `[d` |

---

## 2. 代码示例

### lua/plugins/lsp.lua

```lua
-- lua/plugins/lsp.lua
return {
    -- mason: 管理 LSP 安装
    {
        "williamboman/mason.nvim",
        cmd = "Mason",
        build = ":MasonUpdate",  -- 安装后自动更新注册表
        opts = {},
    },

    -- mason-lspconfig: 桥接
    {
        "williamboman/mason-lspconfig.nvim",
        event = "VeryLazy",
        dependencies = { "williamboman/mason.nvim" },
        opts = {
            -- 自动安装这些 LSP 服务器
            ensure_installed = {
                "lua_ls",        -- Lua
                "rust_analyzer", -- Rust
                "pyright",       -- Python
                "ts_ls",         -- TypeScript/JavaScript
                "gopls",         -- Go
            },
        },
    },

    -- nvim-lspconfig: 配置服务器
    {
        "neovim/nvim-lspconfig",
        event = { "BufReadPre", "BufNewFile" },
        dependencies = {
            "williamboman/mason.nvim",
            "williamboman/mason-lspconfig.nvim",
        },
        config = function()
            -- LSP 按键映射（在 LspAttach 事件中设置）
            vim.api.nvim_create_autocmd("LspAttach", {
                group = vim.api.nvim_create_augroup("UserLspConfig", { clear = true }),
                callback = function(args)
                    local bufnr = args.buf
                    local client = vim.lsp.get_client_by_id(args.data.client_id)

                    -- 通用的 LSP 映射
                    local function map(lhs, rhs, desc)
                        vim.keymap.set("n", lhs, rhs, { buffer = bufnr, desc = desc })
                    end

                    -- 导航
                    map("gd", vim.lsp.buf.definition, "跳转到定义")
                    map("gD", vim.lsp.buf.declaration, "跳转到声明")
                    map("gr", vim.lsp.buf.references, "查找引用")
                    map("gi", vim.lsp.buf.implementation, "跳转到实现")
                    map("gT", vim.lsp.buf.type_definition, "跳转到类型定义")

                    -- 信息
                    map("K", vim.lsp.buf.hover, "悬停文档")
                    map("<C-k>", vim.lsp.buf.signature_help, "函数签名")

                    -- 操作
                    map("<leader>rn", vim.lsp.buf.rename, "重命名")
                    map("<leader>ca", vim.lsp.buf.code_action, "代码操作")
                    map("<leader>f", function()
                        vim.lsp.buf.format({ async = true })
                    end, "格式化")

                    -- 诊断
                    map("<leader>e", vim.diagnostic.open_float, "查看诊断")
                    map("[d", vim.diagnostic.goto_prev, "上一个诊断")
                    map("]d", vim.diagnostic.goto_next, "下一个诊断")

                    -- 如果服务器支持，启用文档高亮
                    if client.supports_method("textDocument/documentHighlight") then
                        vim.api.nvim_create_autocmd({ "CursorHold", "CursorHoldI" }, {
                            buffer = bufnr,
                            callback = vim.lsp.buf.document_highlight,
                        })
                        vim.api.nvim_create_autocmd("CursorMoved", {
                            buffer = bufnr,
                            callback = vim.lsp.buf.clear_references,
                        })
                    end
                end,
            })

            -- 服务器配置函数（在 mason-lspconfig 确保安装后调用）
            local lspconfig = require("lspconfig")
            local capabilities = require("cmp_nvim_lsp").default_capabilities()
            -- ↑ 见第 10 节；暂无 cmp 时可临时用:
            -- local capabilities = vim.lsp.protocol.make_client_capabilities()

            -- 每个服务器可以用默认配置，也可以在 setup 中覆盖选项
            local servers = {
                lua_ls = {
                    settings = {
                        Lua = {
                            runtime = { version = "LuaJIT" },
                            diagnostics = { globals = { "vim" } },
                            workspace = { checkThirdParty = false },
                            telemetry = { enable = false },
                        },
                    },
                },
                rust_analyzer = {},
                pyright = {},
                ts_ls = {},
                gopls = {},
            }

            -- 注册服务器启动
            for server, config in pairs(servers) do
                lspconfig[server].setup(vim.tbl_extend("force", {
                    capabilities = capabilities,
                }, config))
            end
        end,
    },
}
```

### 关于 capabilities

```lua
-- 不带 cmp 的简化版（本节用这个）：
local capabilities = vim.lsp.protocol.make_client_capabilities()

-- 带 cmp 的完整版（第 10 节引入）：
-- local capabilities = require("cmp_nvim_lsp").default_capabilities()
```

**运行方式:**
1. 将上述内容保存为 `lua/plugins/lsp.lua`
2. 在 `lua/config/lazy.lua` 中确保有 `{ import = "plugins" }`
3. 重启 Neovim，运行 `:Lazy` 确认插件已安装
4. 运行 `:Mason` 确认 LSP 服务器状态
5. 打开一个 Lua 文件，`:LspInfo` 查看附着状态

---

## 3. 练习

### 练习 1: 安装并配置一个 LSP
按上面示例配置 `lua_ls`（Lua 语言服务器）。验证：
- 打开 `init.lua`，`:LspInfo` 显示 `lua_ls` 已附着
- 将光标放在 `vim.keymap.set` 上，按 `K` 查看文档
- 在某个变量上按 `gd`，验证跳转到定义

### 练习 2: 添加你常用语言的 LSP
从 [mason 可用服务器列表](https://github.com/williamboman/mason.nvim#packages) 找到你需要的语言服务器，添加到 `ensure_installed` 和 `servers` 表中。

### 练习 3: 诊断导航（可选）
故意写一段有错误的代码（如未定义的变量），观察 Neovim 行号旁的红色标记。用 `[d` 和 `]d` 在错误间跳转，用 `<leader>e` 查看浮动诊断。

---

## 4. 扩展阅读

- [Neovim LSP 官方文档](https://neovim.io/doc/user/lsp.html)
- [nvim-lspconfig 支持的服务器列表](https://github.com/neovim/nvim-lspconfig/blob/master/doc/server_configurations.md)
- [mason.nvim 包列表](https://github.com/williamboman/mason.nvim#packages)
- [LSP 协议规范](https://microsoft.github.io/language-server-protocol/)

---

## 常见陷阱

- **LSP 服务器需要单独安装**：`nvim-lspconfig` 只负责配置和启动，不负责安装。用 `mason.nvim` 解决安装问题。
- **忘记 `capabilities`**：没有正确传递 capabilities，会导致某些功能（如补全、格式化）不工作。即使暂时没有 cmp，也要用 `vim.lsp.protocol.make_client_capabilities()`。
- **`tailwindcss` 等在大型项目中可能很慢**：对不需要的语言，不要放入 `ensure_installed`。
- **Lua 诊断提示 `vim` 为未定义**：在 `lua_ls` 配置中添加 `diagnostics.globals = { "vim" }`。
- **`LspAttach` 可能触发多次**：一个缓冲区可以附着多个 LSP 服务器。用 `args.data.client_id` 区分。
