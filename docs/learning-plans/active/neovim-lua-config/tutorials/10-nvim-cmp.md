# 10 — 代码补全系统 nvim-cmp

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 60 分钟
> 前置知识: 09-lsp-config（LSP 客户端配置）

---

## 1. 概念讲解

### nvim-cmp 的架构

`nvim-cmp` 是 Neovim 的补全引擎。它本身不提供补全项，而是通过**源（source）** 聚合来自不同地方的补全候选：

```
┌──────────────────────────────────────────┐
│                nvim-cmp                   │
│  (补全引擎: 排序、过滤、UI、映射)          │
├──────────────────────────────────────────┤
│  cmp-nvim-lsp  │ cmp-buffer │ cmp-path   │
│  (LSP 补全)    │ (缓冲区词)  │ (文件路径)  │
│                │             │            │
│  cmp_luasnip   │ cmp-cmdline │ ...        │
│  (代码片段)     │ (命令行)    │            │
└──────────────────────────────────────────┘
```

### 涉及的关键插件

| 插件 | 作用 |
|------|------|
| `nvim-cmp` | 补全引擎核心 |
| `cmp-nvim-lsp` | LSP 补全源 |
| `cmp-buffer` | 当前缓冲区单词补全 |
| `cmp-path` | 文件路径补全 |
| `LuaSnip` | 代码片段引擎（snippet） |
| `cmp_luasnip` | 将 LuaSnip 作为补全源 |

### 补全弹出窗口的按键

nvim-cmp 通过 `mapping` 字段定义补全菜单中的按键行为：

```lua
mapping = {
    ["<C-n>"] = cmp.mapping.select_next_item(),      -- 下一项
    ["<C-p>"] = cmp.mapping.select_prev_item(),      -- 上一项
    ["<C-y>"] = cmp.mapping.confirm({ select = true }), -- 确认
    ["<C-e>"] = cmp.mapping.abort(),                 -- 取消
    ["<CR>"] = cmp.mapping.confirm({ select = false }),  -- 回车确认
    ["<Tab>"] = cmp.mapping(function(fallback)       -- Tab 导航
        -- 自定义逻辑...
    end),
}
```

### 补全源优先级

通过 `sources` 配置补全来源的优先级和过滤：

```lua
sources = cmp.config.sources({
    { name = "nvim_lsp", priority = 1000 },  -- LSP 优先
    { name = "luasnip",  priority = 750 },   -- 代码片段次之
    { name = "buffer",   priority = 500 },   -- 缓冲区词
    { name = "path",     priority = 250 },   -- 路径补全
})
```

---

## 2. 代码示例

### lua/plugins/cmp.lua

```lua
-- lua/plugins/cmp.lua
return {
    -- LuaSnip（代码片段引擎）
    {
        "L3MON4D3/LuaSnip",
        build = "make install_jsregexp",  -- 可选：增强正则支持
        dependencies = { "rafamadriz/friendly-snippets" },  -- 预置片段库
        opts = {
            history = true,
            delete_check_visiting = true,
        },
        config = function(_, opts)
            require("luasnip").setup(opts)
            -- 加载 friendly-snippets
            require("luasnip.loaders.from_vscode").lazy_load()
        end,
    },

    -- nvim-cmp 核心
    {
        "hrsh7th/nvim-cmp",
        event = "InsertEnter",
        dependencies = {
            "hrsh7th/cmp-nvim-lsp",   -- LSP 补全源
            "hrsh7th/cmp-buffer",     -- 缓冲区词
            "hrsh7th/cmp-path",       -- 文件路径
            "L3MON4D3/LuaSnip",       -- 代码片段
            "saadparwaiz1/cmp_luasnip", -- 卢 snippet 源
        },
        config = function()
            local cmp = require("cmp")
            local luasnip = require("luasnip")

            -- 判断是否在 snippet 跳转位置
            local has_words_before = function()
                local line, col = unpack(vim.api.nvim_win_get_cursor(0))
                return col ~= 0
                    and vim.api.nvim_buf_get_lines(0, line - 1, line, true)[1]:sub(col, col):match("%s") == nil
            end

            cmp.setup({
                -- 补全菜单中的按键映射
                mapping = cmp.mapping.preset.insert({
                    -- 上下选择
                    ["<C-n>"] = cmp.mapping.select_next_item({ behavior = cmp.SelectBehavior.Insert }),
                    ["<C-p>"] = cmp.mapping.select_prev_item({ behavior = cmp.SelectBehavior.Insert }),

                    -- 确认与取消
                    ["<C-y>"] = cmp.mapping.confirm({ select = true }),
                    ["<C-e>"] = cmp.mapping.abort(),
                    ["<CR>"] = cmp.mapping.confirm({ select = false }),

                    -- Tab 智能补全：在 snippet 跳转和选择之间切换
                    ["<Tab>"] = cmp.mapping(function(fallback)
                        if cmp.visible() then
                            cmp.select_next_item()
                        elseif luasnip.expand_or_jumpable() then
                            luasnip.expand_or_jump()
                        elseif has_words_before() then
                            cmp.complete()
                        else
                            fallback()
                        end
                    end, { "i", "s" }),

                    ["<S-Tab>"] = cmp.mapping(function(fallback)
                        if cmp.visible() then
                            cmp.select_prev_item()
                        elseif luasnip.jumpable(-1) then
                            luasnip.jump(-1)
                        else
                            fallback()
                        end
                    end, { "i", "s" }),
                }),

                -- 补全来源
                sources = cmp.config.sources({
                    { name = "nvim_lsp", priority = 1000 },
                    { name = "luasnip",  priority = 750 },
                    { name = "buffer",   priority = 500 },
                    { name = "path",     priority = 250 },
                }),

                -- 补全窗口外观
                window = {
                    completion = cmp.config.window.bordered(),
                    documentation = cmp.config.window.bordered(),
                },

                -- 代码片段配置
                snippet = {
                    expand = function(args)
                        luasnip.lsp_expand(args.body)
                    end,
                },
            })

            -- 命令行模式补全（搜索 `/` 时用 buffer 源）
            cmp.setup.cmdline({ "/", "?" }, {
                mapping = cmp.mapping.preset.cmdline(),
                sources = {
                    { name = "buffer" },
                },
            })

            -- 命令行补全（`: ` 时用 cmdline 和 path 源）
            cmp.setup.cmdline(":", {
                mapping = cmp.mapping.preset.cmdline(),
                sources = cmp.config.sources({
                    { name = "path" },
                }, {
                    { name = "cmdline" },
                }),
            })
        end,
    },
}
```

### 在 LSP 配置中使用 cmp 的 capabilities

修改 `lua/plugins/lsp.lua` 中 `nvim-lspconfig` 的 `config` 函数：

```lua
-- 找到这行
-- local capabilities = vim.lsp.protocol.make_client_capabilities()

-- 替换为
local capabilities = require("cmp_nvim_lsp").default_capabilities()
```

这样 LSP 服务器就知道客户端支持补全功能。

**运行方式:**
1. 将上述内容保存为 `lua/plugins/cmp.lua`
2. 重启 Neovim，运行 `:Lazy` 确认插件已安装
3. 打开一个 Lua 文件，输入 `vim.` 等待补全弹出
4. 输入 `for` 然后按 Tab，观察 snippet 展开

---

## 3. 练习

### 练习 1: 验证补全源
打开一个 Lua 文件，输入 `vim.key` 等待补全菜单。确认能看到来自不同源的补全项（LSP、buffer、path）。在 `:Lazy` 检查 cmp 及其依赖都处于 loaded 状态。

### 练习 2: 自定义补全外观
修改 `window` 选项，尝试不同的边框样式。参考 `:help cmp-config.window`：
- `bordered()` — 带边框
- `rounded()` — 圆角边框
- `none()` — 无边框

### 练习 3: 添加 snippet（可选）
在 Neovim 中运行 `:lua require("luasnip").snip_expand(require("luasnip").parser.parse_snippet("fn", "function ${1:name}(${2:args})\n\t${0:body}\nend"))`。然后在 Lua 文件中输入 `fn` + Tab，观察展开。

---

## 4. 扩展阅读

- [nvim-cmp 官方文档](https://github.com/hrsh7th/nvim-cmp)
- [LuaSnip 文档](https://github.com/L3MON4D3/LuaSnip/blob/master/DOC.md)
- [friendly-snippets](https://github.com/rafamadriz/friendly-snippets) — 预置 snippet 集合
- [`:help ins-completion`](https://neovim.io/doc/user/insert.html#ins-completion)

---

## 常见陷阱

- **忘记传递 capabilities 给 LSP**：不传 `cmp_nvim_lsp.default_capabilities()`，LSP 补全不工作——最容易犯的错误。
- **LuaSnip 的 `build` 命令在 Windows 上可能失败**：如果 `make install_jsregexp` 失败不影响基本功能，可以注释掉这一行。
- **Tab 映射覆盖了 Neovim 默认的 `<Tab>` 行为**：`fallback()` 确保在不满足条件时回退到默认行为。
- **`friendly-snippets` 需要 `luasnip.loaders.from_vscode().lazy_load()`**：只安装依赖不够，必须手动调用加载。
- **多个源名称大小写敏感**：`nvim_lsp` 不是 `nvim-lsp`，`cmp_nvim_lsp` 是插件名但源名是 `nvim_lsp`。
