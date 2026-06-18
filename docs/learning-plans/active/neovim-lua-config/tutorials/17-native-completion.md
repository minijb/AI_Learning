---
title: "17 — 原生补全：vim.lsp.completion（零依赖方案）"
updated: 2026-06-18
---

# 17 — 原生补全：vim.lsp.completion（零依赖方案）

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 40 分钟
> 前置知识: [[09-modern-lsp]]、[[10-blink-cmp]]

---

## 1. 概念讲解

### 1.1 什么是 `vim.lsp.completion`

Neovim 0.10+ 在核心中提供了 `vim.lsp.completion` 模块，0.12 进一步稳定了它的行为。它把 LSP 的 `textDocument/completion` 响应直接桥接到 Vim 的插入模式补全菜单，**不需要安装 blink.cmp、nvim-cmp 或任何第三方补全插件**。

它的工作链路非常简单：

1. LSP server（如 `lua_ls`）附着到当前 buffer。
2. 你输入代码时，Neovim 向 server 请求 completion items。
3. `vim.lsp.completion` 把 items 转换成 Vim 认识的 `complete-items`。
4. 弹出补全菜单，按 `<C-y>` 确认。

> [!note]
> 这里的"原生"指的是"Neovim 核心自带"，不是 Vim 传统 omnifunc。原生补全底层仍然复用了 `omnifunc` 机制，但会自动触发、自动解析 LSP 响应。

### 1.2 何时选择原生补全

如果你满足以下任意场景，原生补全值得优先考虑：

- 你希望配置**尽可能少**，越少越安心。
- 你只在 LSP 项目中工作，不需要 path / buffer / cmdline 等多源补全。
- 你对**模糊匹配**要求不高，LSP server 返回的前缀/近似匹配已够用。
- 你想**减少插件依赖**，降低更新和维护负担。

相对的，如果你需要 IDE 级体验，仍然建议使用 [[10-blink-cmp]]。

### 1.3 blink.cmp vs 原生补全对比

下面是核心差异一览表：

| 维度 | blink.cmp | `vim.lsp.completion` |
|------|-----------|----------------------|
| 插件依赖 | 需要 blink.cmp（+ 可选 LuaSnip） | 零插件 |
| 补全来源 | LSP、path、buffer、snippets、cmdline、terminal | 仅 LSP（当前 buffer 的 attached client） |
| 性能 | Rust 核心，极快 | 纯 Lua + LSP 往返，中等 |
| 配置复杂度 | 一个 `setup()`，中等 | 一个 autocmd，极简 |
| 模糊匹配 | 内置 Rust / Lua 模糊算法 | 依赖 LSP server 的过滤/排序 |
| snippet 支持 | 原生，支持多种后端 | 配合 `vim.snippet`，无需插件 |
| 菜单 UI | 图标、文档浮动窗、签名帮助 | 原生菜单，简洁 |
| cmdline 补全 | 支持 | 不支持 |
| 版本要求 | 0.10+ | 0.10+ 可用，0.12+ 推荐 |

> [!warning]
> 原生补全目前**不能**像 blink.cmp 那样合并 `path`、`buffer` 等外部源。如果你写 Markdown、Shell 或配置文件时也需要非 LSP 补全，原生方案会力不从心。

### 1.4 触发方式

原生补全有三种触发方式：

1. **自动触发（autotrigger）**
   在 `vim.lsp.completion.enable()` 的 opts 中设置 `{ autotrigger = true }`。输入字符时如果 LSP 返回候选，菜单自动弹出。

2. **手动 omnifunc**
   Neovim 0.12 在 `LspAttach` 时默认把 `'omnifunc'` 设为 `vim.lsp.omnifunc`。插入模式下按 `<C-x><C-o>` 即可手动请求 LSP 补全。

3. **自定义 completefunc**
   你可以写自己的 `completefunc`，在其中调用 `vim.lsp.completion.get()` 并混合其他候选。

> [!tip]
> 自动触发最像现代 IDE，但可能在注释或字符串中频繁弹出。可以结合 `completeopt` 的 `noselect` 避免自动插入第一项。

### 1.5 确认与导航

原生补全使用 Vim 默认的插入模式补全按键：

- `<C-n>` / `<C-p>`：下一项 / 上一项。
- `<C-y>`：确认当前项。
- `<C-e>`：取消并关闭菜单。

> [!important]
> `<CR>`（回车）**不会**确认原生补全。这和 blink.cmp 的 `'enter'` 预设不同。如果你习惯回车确认，需要自己映射。

### 1.6 `completeopt` 配置

`completeopt` 控制补全菜单的行为。推荐设置：

```lua
vim.o.completeopt = 'menuone,noselect'
```

含义：

- `menuone`：即使只有一项候选也显示菜单。
- `noselect`：默认不选中第一项，避免意外插入。
- 可选 `noinsert`：不自动插入任何文本，直到你确认。

### 1.7 Snippet 处理

Neovim 0.10+ 内置了 `vim.snippet` 模块，原生补全的 snippet 项可以直接展开，**不需要 LuaSnip**。

基本 snippet 跳转映射：

```lua
vim.keymap.set({ 'i', 's' }, '<Tab>', function()
  if vim.snippet.active({ direction = 1 }) then
    vim.snippet.jump(1)
  else
    vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes('<Tab>', true, false, true), 'n', false)
  end
end, { desc = 'Snippet jump forward' })

vim.keymap.set({ 'i', 's' }, '<S-Tab>', function()
  if vim.snippet.active({ direction = -1 }) then
    vim.snippet.jump(-1)
  else
    vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes('<S-Tab>', true, false, true), 'n', false)
  end
end, { desc = 'Snippet jump backward' })
```

> [!important]
> `vim.snippet` 的占位符语法与 VSCode snippet 一致：`$1`、`$2`、`${1:default}`、`$0` 表示最终落点。

### 1.8 进阶：`convert` 与自定义 `completefunc`

`vim.lsp.completion.enable()` 支持 `convert` 选项，用于在显示前修改每个 completion item：

```lua
vim.lsp.completion.enable(true, client.id, ev.buf, {
  autotrigger = true,
  convert = function(item)
    -- 在菜单文本前加前缀
    item.abbr = '[LSP] ' .. (item.abbr or item.word)
    return item
  end,
})
```

自定义 `completefunc` 可以混合 LSP 与其他候选（本示例为演示 API，请按实际项目调整）：

```lua
vim.o.completefunc = 'v:lua._G.my_complete'

function _G.my_complete(findstart, base)
  if findstart == 1 then
    -- 返回补全起始列
    return vim.fn.col('.') - #base
  end

  -- 获取当前 LSP 候选
  local lsp_items = vim.lsp.completion.get() or {}

  -- 混入自定义静态候选
  for _, word in ipairs({ 'TODO', 'FIXME', 'HACK' }) do
    if word:lower():find(base:lower(), 1, true) then
      table.insert(lsp_items, {
        word = word,
        abbr = word,
        kind = 'Text',
        icase = 1,
      })
    end
  end

  return lsp_items
end
```

> [!warning]
> `vim.lsp.completion.get()` 是较底层的 API，签名在不同版本可能微调。使用前请用 `:help vim.lsp.completion.get()` 核对当前 Neovim 版本的帮助文档。

---

## 2. 代码示例

### 2.1 最小启用配置

把下面代码加入 `init.lua` 即可启用原生 LSP 补全：

```lua
-- init.lua (最小配置)
vim.o.completeopt = 'menuone,noselect'

vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if client and client:supports_method('textDocument/completion', ev.buf) then
      vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
    end
  end,
})
```

> [!note]
> 这段代码本身不安装任何插件，但你需要 LSP server 已经配置好并附着到 buffer。参考 [[09-modern-lsp]] 配置 `vim.lsp.config()` / `vim.lsp.enable()`。

### 2.2 完整可运行配置

下面是一份自包含的 `init.lua` 片段，包含 `vim.loader.enable`、LSP 配置、`vim.snippet` 跳转和原生补全启用：

```lua
-- init.lua Section: Native LSP Completion
-- 要求: Neovim 0.12.3+

vim.loader.enable()

vim.o.completeopt = 'menuone,noselect'

-- Snippet 跳转
vim.keymap.set({ 'i', 's' }, '<Tab>', function()
  if vim.snippet.active({ direction = 1 }) then
    vim.snippet.jump(1)
  else
    vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes('<Tab>', true, false, true), 'n', false)
  end
end, { desc = 'Snippet jump forward' })

vim.keymap.set({ 'i', 's' }, '<S-Tab>', function()
  if vim.snippet.active({ direction = -1 }) then
    vim.snippet.jump(-1)
  else
    vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes('<S-Tab>', true, false, true), 'n', false)
  end
end, { desc = 'Snippet jump backward' })

-- 配置 lua_ls
vim.lsp.config('lua_ls', {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.git' },
  settings = {
    Lua = {
      runtime = { version = 'LuaJIT' },
      diagnostics = { globals = { 'vim' } },
    },
  },
})
vim.lsp.enable('lua_ls')

-- 原生 LSP 补全
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if client and client:supports_method('textDocument/completion', ev.buf) then
      vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
    end
  end,
})
```

**运行方式：**

1. 确保已安装 `lua-language-server` 并在 PATH 中。
2. 把上述代码放入 `init.lua`。
3. 启动 Neovim，打开任意 Lua 文件（如 `init.lua` 自身）。
4. 输入 `vim.key`，等待约 100–300ms，应看到来自 lua_ls 的补全菜单。
5. 用 `<C-n>` / `<C-p>` 选择，`<C-y>` 确认。

### 2.3 手动触发 omnifunc

如果你不想自动触发，可以关闭 `autotrigger`，改用手动：

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if client and client:supports_method('textDocument/completion', ev.buf) then
      -- 只注册 omnifunc，不自动触发
      vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = false })
    end
  end,
})
```

然后在插入模式下按 `<C-x><C-o>` 即可弹出菜单。

验证当前 omnifunc：

```vim
:set omnifunc?
" 期望输出: omnifunc=vim.lsp.omnifunc
```

### 2.4 关闭原生补全并回退到 blink.cmp

如果你在体验后想切回 blink.cmp，只需注释掉 `LspAttach` 中的 `vim.lsp.completion.enable(...)` 调用，并安装 [[10-blink-cmp]]。两者不应同时启用，否则可能出现双重补全或按键冲突。

---

## 3. 练习

### 练习 1: 启用原生补全

使用 2.2 节的完整配置，在 Lua 文件中输入 `vim.key`、`vim.api.`、`vim.fn.` 等前缀，观察补全菜单。

### 练习 2: 测试 omnifunc 手动触发

把 `autotrigger` 改为 `false`，重启 Neovim。在 Lua 文件中输入 `vim.tbl` 后按 `<C-x><C-o>`，确认菜单弹出。

### 练习 3: 对比 blink.cmp 与原生补全

在同一台机器上分别用 [[10-blink-cmp]] 配置和本节的 `vim.lsp.completion` 配置打开同一个项目文件，从以下维度记录差异：

- 触发速度
- 候选数量与来源
- 路径/缓冲区/命令行补全是否可用
- snippet 展开方式
- 菜单 UI 与图标

### 练习 4: 调整 `completeopt`

分别尝试以下设置，观察菜单行为差异：

```lua
vim.o.completeopt = 'menuone,noselect'
vim.o.completeopt = 'menuone,noinsert'
vim.o.completeopt = 'menu,preview'
```

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 完整启用步骤：
>
> ```lua
> -- init.lua
> vim.loader.enable()
> vim.o.completeopt = 'menuone,noselect'
>
> vim.lsp.config('lua_ls', {
>   cmd = { 'lua-language-server' },
>   filetypes = { 'lua' },
>   root_markers = { '.luarc.json', '.git' },
>   settings = {
>     Lua = {
>       runtime = { version = 'LuaJIT' },
>       diagnostics = { globals = { 'vim' } },
>     },
>   },
> })
> vim.lsp.enable('lua_ls')
>
> vim.api.nvim_create_autocmd('LspAttach', {
>   callback = function(ev)
>     local client = vim.lsp.get_client_by_id(ev.data.client_id)
>     if client and client:supports_method('textDocument/completion', ev.buf) then
>       vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = true })
>     end
>   end,
> })
> ```
>
> 预期结果：
>
> - 输入 `vim.key` 后弹出菜单，包含 `vim.keymap.set` 等。
> - 每项通常显示函数签名或类型提示。
> - 按 `<C-y>` 确认后，如果该项是 snippet，会自动展开参数占位符。

> [!tip]- 练习 2 参考答案
> 关闭自动触发的配置片段：
>
> ```lua
> vim.api.nvim_create_autocmd('LspAttach', {
>   callback = function(ev)
>     local client = vim.lsp.get_client_by_id(ev.data.client_id)
>     if client and client:supports_method('textDocument/completion', ev.buf) then
>       vim.lsp.completion.enable(true, client.id, ev.buf, { autotrigger = false })
>     end
>   end,
> })
> ```
>
> 使用方式：
>
> 1. 输入 `vim.tbl`。
> 2. 按 `<C-x><C-o>`。
> 3. 菜单出现后按 `<C-n>` / `<C-p>` 选择，`<C-y>` 确认。
>
> **关键点**：`autotrigger = false` 适合在低速机器或大型单文件中减少 LSP 请求频率；代价是多按一次组合键。

> [!tip]- 练习 3 参考答案
> 对比维度与典型结论：
>
> | 维度 | blink.cmp | `vim.lsp.completion` |
> |------|-----------|----------------------|
> | 触发速度 | 通常更快（本地 Rust/Lua 过滤） | 依赖 LSP server 响应 |
> | 候选来源 | LSP、path、buffer、snippets、cmdline | 仅 LSP |
> | 路径补全 | `./` 触发 | 不支持 |
> | 命令行补全 | 支持 | 不支持 |
> | 模糊匹配 | Rust 算法 | 通常只有前缀匹配 |
> | snippet 后端 | LuaSnip / mini_snippets / native | `vim.snippet` |
> | UI | 图标、文档窗、签名帮助 | 简洁原生菜单 |
>
> **选择建议**：
>
> - 项目代码 + 想零依赖 → 原生补全。
> - 多语言、需要 path/buffer/cmdline、喜欢丰富 UI → blink.cmp。

> [!tip]- 练习 4 参考答案
> 三种 `completeopt` 的行为差异：
>
> ```lua
> -- 默认推荐：菜单始终显示，但不自动选中/插入
> vim.o.completeopt = 'menuone,noselect'
>
> -- 不自动插入文本，必须按 <C-y> 才会写入
> vim.o.completeopt = 'menuone,noinsert'
>
> -- 老派设置：显示菜单 + 预览窗口（右侧显示文档）
> vim.o.completeopt = 'menu,preview'
> ```
>
> **关键点**：`noselect` 与 `noinsert` 组合（`menuone,noselect,noinsert`）能最大程度避免误触。建议根据个人习惯保留 `noselect` 或额外加 `noinsert`。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [`:help vim.lsp.completion`](https://neovim.io/doc/user/lsp.html#vim.lsp.completion) — 官方 API 文档
- [`:help ins-completion`](https://neovim.io/doc/user/insert.html#ins-completion) — 插入模式补全机制
- [`:help vim.snippet`](https://neovim.io/doc/user/lua.html#vim.snippet) — 原生 snippet 模块
- [blink.cmp 官方仓库](https://github.com/saghen/blink.cmp)
- [[10-blink-cmp]] — 本计划的 blink.cmp 教程

---

## 常见陷阱

- **与 blink.cmp 同时启用**：两者都会响应 LSP completion，导致菜单重复或按键冲突。二选一。
- **LSP server 未启动**：原生补全不工作最常见原因是 server 没 attach。用 `:lsp list` 检查。
- **`<CR>` 不确认补全**：原生补全默认用 `<C-y>`，`<CR>` 只是换行。不要按错。
- **`completeopt` 未设置**：默认 `completeopt` 可能不包含 `menuone`，导致只有一项时不显示菜单。
- **snippet 不跳转**：确认你映射了 `<Tab>` / `<S-Tab>` 到 `vim.snippet.jump`，否则 snippet 插入后无法离开占位符。
- **convert 函数返回 nil**：`convert` 必须返回修改后的 item；返回 nil 会导致菜单项丢失。
- **把 `autotrigger` 误写为 `autotrigger = false` 又想自动弹出**：检查选项名与布尔值。
