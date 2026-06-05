---
title: "10 — blink.cmp 补全系统"
updated: 2026-06-05
---

# 10 — blink.cmp 补全系统

> 所属计划: Neovim + Lua 配置实战 (现代版)
> 预计耗时: 50 分钟
> 前置知识: 09-modern-lsp（LSP 配置）

---

## 1. 概念讲解

### blink.cmp vs nvim-cmp

blink.cmp 是 2025 年出现的现代补全引擎，正迅速成为 Neovim 生态的新标准（kickstart.nvim 已默认采用）：

| 特性 | blink.cmp | nvim-cmp (旧) |
|------|-----------|-------------|
| 实现语言 | Rust + Lua | 纯 Lua |
| 性能 | 极快（Rust 实现的核心） | 中等 |
| 配置方式 | 单一 `setup()` 调用，结构清晰 | 多个 `cmp.setup()` 调用 + 多文件 |
| 内置源 | lsp + path + buffer + snippets | 需要额外安装 cmp-nvim-lsp 等 |
| 模糊匹配 | 内置 Rust 实现 | 依赖外部源 |
| 签名帮助 | 内置 | 需要额外插件 |
| snippet 集成 | 原生支持 | 需要 cmp_luasnip |
| 维护状态 | 活跃开发中 | 稳定但渐被取代 |

### 架构对比

```
nvim-cmp 架构:                blink.cmp 架构:
┌──────────────┐              ┌──────────────┐
│   nvim-cmp   │              │  blink.cmp   │
│   (核心引擎)  │              │  (Rust 引擎)  │
├──────────────┤              ├──────────────┤
│ cmp-nvim-lsp │← LSP        │ built-in lsp │← LSP
│ cmp-buffer   │← Buffer     │ built-in     │← Buffer
│ cmp-path     │← Path       │ built-in     │← Path
│ cmp_luasnip  │← Snippets   │ luasnip      │← Snippets (preset)
│ (分别安装)    │              │ (内建集成)    │
└──────────────┘              └──────────────┘
```

### 核心配置

```lua
require('blink.cmp').setup({
  keymap = {
    preset = 'default',  -- 推荐：接近 Vim 原生补全的按键
    -- 'super-tab': Tab 补全
    -- 'enter': Enter 补全
    -- 'none': 完全自定义
  },
  sources = {
    default = { 'lsp', 'path', 'snippets' },  -- buffer 可选添加
  },
  snippets = { preset = 'luasnip' },  -- 使用 LuaSnip
  fuzzy = { implementation = 'lua' },  -- 'prefer_rust_with_warning' 启用 Rust 引擎
  signature = { enabled = true },     -- 函数签名帮助
  completion = {
    documentation = { auto_show = false, auto_show_delay_ms = 500 },
  },
  appearance = {
    nerd_font_variant = 'mono',  -- 或 'normal'
  },
})
```

### 与 LuaSnip 的集成

blink.cmp 原生支持 LuaSnip 作为 snippet 后端：

```lua
vim.pack.add { { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' } }
require('luasnip').setup {}

require('blink.cmp').setup({
  snippets = { preset = 'luasnip' },
  sources = { default = { 'lsp', 'path', 'snippets' } },
})
```

---

## 2. 代码示例

### 完整的 blink.cmp + LuaSnip 配置

```lua
-- init.lua Section: Autocomplete & Snippets
do
  -- Snippet 引擎
  vim.pack.add { { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' } }
  require('luasnip').setup {}

  -- 可选：预制 snippet 集合
  -- vim.pack.add { gh 'rafamadriz/friendly-snippets' }
  -- require('luasnip.loaders.from_vscode').lazy_load()

  -- 补全引擎（版本锁定 1.x）
  vim.pack.add { { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' } }
  require('blink.cmp').setup {
    keymap = {
      preset = 'default',
      -- 'default' 预设包含的映射:
      --   <C-y>    确认补全
      --   <C-n>/<C-p> 选择下一项/上一项
      --   <C-space> 打开菜单 / 打开文档
      --   <C-e>    关闭菜单
      --   <C-k>    切换签名帮助
      --   <Tab>/<S-Tab> 在 snippet 占位符间跳转
    },

    appearance = {
      nerd_font_variant = 'mono',
    },

    completion = {
      documentation = {
        auto_show = false,
        auto_show_delay_ms = 500,
      },
    },

    -- 补全来源及顺序
    sources = {
      default = { 'lsp', 'path', 'snippets' },
      -- 可选: 添加 buffer 源 (当前文件中的词)
      -- default = { 'lsp', 'path', 'snippets', 'buffer' },
    },

    -- 使用 LuaSnip 作为 snippet 后端
    snippets = { preset = 'luasnip' },

    -- 模糊匹配实现
    fuzzy = {
      implementation = 'lua',  -- 跨平台安全选择
      -- 如需性能，启用 Rust 引擎（首次需下载预编译二进制）
      -- implementation = 'prefer_rust_with_warning',
    },

    -- 函数参数签名帮助
    signature = { enabled = true },
  }
end
```

**运行方式:**
1. 将上述代码放入 `init.lua`
2. 确保 LSP 已配置（第 09 节）
3. 启动 Neovim，打开一个 Lua 文件
4. 输入 `vim.key` 等待补全弹出（约 250ms 内）
5. 按 `<C-n>` / `<C-p>` 选择，`<C-y>` 确认

---

## 3. 练习

### 练习 1: 验证补全来源

打开一个 Lua 文件：
- 输入 `vim.key` — 确认有 LSP 补全（来自 lua_ls）
- 输入 `./` — 确认有路径补全（来自 path）
- 在代码中输入 `for` 后按 Tab（LuaSnip snippet 可能展开或选择）
- 输入当前文件中已存在的词——如果启用了 `buffer` 源，确认能看到

### 练习 2: 切换 keymap 预设

将 `keymap.preset` 改为 `'super-tab'`，重启后体验 Tab 键补全的行为。再改为 `'enter'` 体验。最后恢复为 `'default'`。

理解不同预设的 trade-off：
- `'default'`: `<C-y>` 确认，不干扰 `<CR>` 换行
- `'super-tab'`: Tab 确认，适合习惯 Tab 补全的用户
- `'enter'`: Enter 确认，最接近 IDE 体验

### 练习 3: 添加自定义 snippet

使用 LuaSnip 创建一个简单的 Lua snippet：

```lua
require('luasnip').add_snippets('lua', {
  require('luasnip').snippet('fn', {
    require('luasnip').text_node('function '),
    require('luasnip').insert_node(1, 'name'),
    require('luasnip').text_node('('),
    require('luasnip').insert_node(2),
    require('luasnip').text_node({ ')', '\t', '' }),
    require('luasnip').insert_node(0),
    require('luasnip').text_node({ '', 'end' }),
  })
})
```

在 Lua 文件中输入 `fn` + `<C-y>`，观察 snippet 展开。

---

## 4. 扩展阅读

- [blink.cmp 官方文档](https://github.com/saghen/blink.cmp)
- [LuaSnip 文档](https://github.com/L3MON4D3/LuaSnip/blob/master/DOC.md)
- [friendly-snippets](https://github.com/rafamadriz/friendly-snippets) — 预置 snippet 集合
- [`:help ins-completion`](https://neovim.io/doc/user/insert.html#ins-completion) — Neovim 内置补全机制

---

## 常见陷阱

- **blink.cmp 和 nvim-cmp 不能共存**：如果从旧配置迁移，必须先删除 nvim-cmp 及其所有依赖（cmp-nvim-lsp, cmp-buffer, cmp-path, cmp_luasnip 等）。
- **LSP 补全不工作**：检查 LSP 服务器是否正常附着（`<leader>q` 查看诊断或 `:checkhealth vim.lsp`）。
- **Rust fuzzy 匹配器需要网络**：`implementation = 'prefer_rust_with_warning'` 首次使用时需要下载预编译二进制。如果离线，用 `'lua'`。
- **LuaSnip 跳转按键**：blink.cmp 接管了 `<Tab>` 和 `<S-Tab>` 用于 snippet 跳转。如果同时配置了 `cmp` 和 `blink.cmp` 的映射，会产生冲突。
- **`friendly-snippets` 需要手动加载**：安装后必须调用 `require('luasnip.loaders.from_vscode').lazy_load()` 才能使用。
- **blink.cmp 版本锁定很重要**：该插件正在快速迭代，用 `vim.version.range '1.*'` 锁定主版本。
