---
title: "05 — 按键映射完全指南"
updated: 2026-06-18
---

# 05 — 按键映射完全指南

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 55 分钟
> 前置知识: [[04-init-lua-structure]]（init.lua 结构、vim.g）

---

## 1. 概念讲解

### 为什么按键映射是配置的核心？

编辑器效率取决于手指不离开键盘。按键映射让你：
- 缩短常用操作（如 `<leader>ff` 查找文件）
- 统一跨插件的快捷键习惯
- 为自定义功能分配快捷键

### `vim.keymap.set`（Neovim 0.7+）

这是配置按键映射的唯一推荐方式。它统一了之前混乱的 `vim.api.nvim_set_keymap` 和 Vimscript 的 `nmap`/`imap` 等：

```lua
vim.keymap.set(mode, lhs, rhs, opts)
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `mode` | 模式字符串或 table | `'n'` 普通, `{'n', 'v'}` 多模式 |
| `lhs` | 按键序列 | `"<leader>ff"`, `"<C-p>"` |
| `rhs` | 目标：命令字符串或 Lua 函数 | `"<cmd>w<CR>"`, `function() ... end` |
| `opts` | 选项 table | `{ desc = "...", silent = true }` |

### 完整 `opts` 参数深度

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `desc` | `string` | `nil` | 描述，出现在 which-key 等插件中 |
| `silent` | `boolean` | `false` | 不回显执行的命令 |
| `noremap` | `boolean` | `true` | 非递归映射（对函数 rhs 无效） |
| `expr` | `boolean` | `false` | rhs 是表达式，按键时求值 |
| `replace_keycodes` | `boolean` | `true`（expr 时） | expr 模式下替换 `<Tab>` 等 keycode |
| `buffer` | `number/boolean` | `nil` | buffer-local，`0` 或 `true` 表示当前 buffer |
| `nowait` | `boolean` | `false` | 立即触发，不等后续按键超时 |
| `unique` | `boolean` | `false` | 如果该 lhs 已有映射则报错 |
| `script` | `boolean` | `false` | 仅 remap 到 `<SID>` 脚本局部映射 |

```lua
vim.keymap.set('n', '<leader>w', '<cmd>write<CR>', {
    desc = '保存文件',        -- which-key 显示
    silent = true,             -- 不显示 :write
    noremap = true,            -- 不递归（默认 true）
    buffer = 0,                -- 仅当前缓冲区
    nowait = false,            -- 等待可能的后续按键
    unique = false,            -- 允许覆盖
})
```

> [!IMPORTANT]
> `noremap` 的默认值在 `vim.keymap.set` 中是 `true`，这与 Vimscript 的 `map` 命令（默认递归）相反。除非你明确需要递归映射，否则不需要显式写 `noremap = true`。

### 模式字符串详解

| 字符串 | 模式 | 说明 |
|--------|------|------|
| `'n'` | Normal | 普通模式 |
| `'i'` | Insert | 插入模式 |
| `'v'` | Visual | 可视模式（字符 + 行） |
| `'x'` | Visual-only | 仅字符可视模式 |
| `'s'` | Select | 选择模式（如 snippet 占位符） |
| `'t'` | Terminal | 终端模式 |
| `'c'` | Command-line | 命令行模式 |
| `'o'` | Operator-pending | 操作符待决模式（如 `d` 之后） |
| `'l'` | Langmap | 语言映射模式 |
| `'!'` | Insert + Command-line | 插入和命令行模式 |

多模式用 table：

```lua
vim.keymap.set({ 'n', 'v' }, '<leader>y', '"+y', { desc = '复制到系统剪贴板' })
```

> [!NOTE]
> 可视模式通常用 `'v'` 就够了，因为它同时覆盖 `'x'`（字符可视）和 `'V'`（行可视）。只有需要排除行可视时才用 `'x'`。

### leader 与 localleader

```lua
-- 必须在任何 keymap 和多数插件之前设置
vim.g.mapleader = ' '       -- 空格键作为 leader
vim.g.maplocalleader = '\\' -- 反斜杠作为 localleader（常用于文件类型局部插件）
```

> [!WARNING]
> `vim.g.mapleader` 必须在所有 `vim.keymap.set` 调用之前设置。keymap 在定义时就会解析 `<leader>` 为当前 leader 值。如果插件在 leader 设置前读取它，插件会 fallback 到默认的 `\`。

社区约定：

| 前缀 | 用途 |
|------|------|
| `<leader>` + 单键 | 高频操作（如 `<leader>w` 保存） |
| `<leader>f*` | 文件/查找 |
| `<leader>g*` | Git |
| `<leader>c*` | 代码/LSP |
| `<leader>l*` | LSP（legacy） |
| `<leader>s*` | 搜索 |
| `<leader>x*` | 诊断/问题 |
| `<leader>t*` | 切换/终端 |
| `<leader>h*` | 帮助 |
| `<leader>u*` | UI |

### 常见 rhs 模式对比

| 写法 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| `<cmd>...<CR>` | 不离开当前模式，不触发 `InsertLeave` | 不能动态计算 | ⭐⭐⭐⭐⭐ |
| `:` | 兼容旧习惯 | 进入命令行再返回，触发模式事件 | ⭐⭐⭐ |
| `<cmd>lua ...<CR>` | 可直接调用 Lua | 字符串形式无语法高亮/补全 | ⭐⭐⭐ |
| Lua 函数 | 最灵活，可访问闭包 | 不能用原生录制宏 | ⭐⭐⭐⭐⭐ |

```lua
-- <cmd> 方式：推荐用于简单命令
vim.keymap.set('n', '<leader>w', '<cmd>write<CR>')

-- : 方式：进入命令行模式
vim.keymap.set('n', '<leader>w', ':write<CR>')

-- <cmd>lua 方式：直接执行 Lua 字符串
vim.keymap.set('n', '<leader>x', '<cmd>lua print("hello")<CR>')

-- Lua 函数方式：最灵活，可访问局部变量
vim.keymap.set('n', '<leader>w', function()
    vim.cmd.write()
    print('文件已保存')
end)
```

> [!TIP]
> 推荐用 `<cmd>` 或 Lua 函数。`<cmd>` 不需要离开当前模式，不会触发 `InsertLeave` 等事件；Lua 函数可以访问闭包变量，适合复杂逻辑。

### 递归与非递归映射

- **递归映射（remap）**：rhs 中如果包含其他映射，会再次展开。例如 `nmap j gj` 后 `nmap <Down> j`，按 `<Down>` 最终会执行 `gj`。
- **非递归映射（noremap）**：rhs 中的按键按原始功能解释，不会继续展开。

```lua
-- 递归示例（不推荐，除非你知道在做什么）
vim.keymap.set('n', 'a', 'b', { noremap = false })   -- 按 a 会触发 b 的映射

-- 非递归示例（默认行为）
vim.keymap.set('n', 'a', 'b')                        -- 按 a 执行 b 的原始功能
```

> [!WARNING]
> 递归映射容易导致“映射链”失控。90% 的场景用非递归即可。`vim.keymap.set` 默认就是非递归，这是现代 API 比 Vimscript 更安全的体现。

### `vim.keymap.del`：删除映射

```lua
-- 删除全局映射
vim.keymap.del('n', '<leader>w')

-- 删除 buffer-local 映射
vim.keymap.del('n', 'K', { buffer = 0 })

-- 删除指定 buffer 的映射
vim.keymap.del('n', 'K', { buffer = bufnr })
```

> [!IMPORTANT]
> 删除 buffer-local 映射时，`buffer` 选项必须和创建时一致。在 `LspDetach` 等回调中清理 LSP 映射时特别有用。

### Neovim 0.12 默认 LSP 按键提醒

Neovim 0.12 在启动时无条件创建了以下全局 LSP 映射（详见 [[09-modern-lsp]]）：

| 按键 | 模式 | 功能 |
|------|------|------|
| `gra` | n, x | `vim.lsp.buf.code_action()` |
| `gri` | n | `vim.lsp.buf.implementation()` |
| `grn` | n | `vim.lsp.buf.rename()` |
| `grr` | n | `vim.lsp.buf.references()` |
| `grt` | n | `vim.lsp.buf.type_definition()` |
| `grx` | n | `vim.lsp.codelens.run()` |
| `gO` | n | `vim.lsp.buf.document_symbol()` |
| `<C-s>` | i | `vim.lsp.buf.signature_help()` |

> [!WARNING]
> 自定义 LSP 映射时避免与上述默认键冲突。例如不要再手动 `map('n', 'grn', vim.lsp.buf.rename)`，它已经内置。可以用 `:verbose map grn` 验证默认映射是否存在。

---

## 2. 代码示例

完整的 `lua/config/keymaps.lua`：

```lua
-- lua/config/keymaps.lua
-- 要求: Neovim 0.12.3+
local M = {}

function M.setup()
    local map = vim.keymap.set
    local opts = { noremap = true, silent = true }

    -- ====== 基础操作 ======
    -- 保存
    map('n', '<leader>w', '<cmd>write<CR>', vim.tbl_extend('force', opts, { desc = '保存' }))

    -- 退出
    map('n', '<leader>q', '<cmd>quit<CR>', vim.tbl_extend('force', opts, { desc = '退出' }))

    -- 用 ESC 清除搜索高亮
    map('n', '<Esc>', '<cmd>nohlsearch<CR>', opts)

    -- ====== 窗口导航 ======
    -- Ctrl + hjkl 在窗口间跳转
    map('n', '<C-h>', '<C-w>h', vim.tbl_extend('force', opts, { desc = '跳转到左侧窗口' }))
    map('n', '<C-j>', '<C-w>j', vim.tbl_extend('force', opts, { desc = '跳转到下方窗口' }))
    map('n', '<C-k>', '<C-w>k', vim.tbl_extend('force', opts, { desc = '跳转到上方窗口' }))
    map('n', '<C-l>', '<C-w>l', vim.tbl_extend('force', opts, { desc = '跳转到右侧窗口' }))

    -- ====== 缓冲区操作 ======
    -- Tab 切换缓冲区
    map('n', '<Tab>', '<cmd>bnext<CR>', vim.tbl_extend('force', opts, { desc = '下一个缓冲区' }))
    map('n', '<S-Tab>', '<cmd>bprevious<CR>', vim.tbl_extend('force', opts, { desc = '上一个缓冲区' }))

    -- 关闭缓冲区
    map('n', '<leader>bd', '<cmd>bdelete<CR>', vim.tbl_extend('force', opts, { desc = '关闭缓冲区' }))

    -- ====== 文本操作 ======
    -- 可视模式下保持缩进后不丢失选择
    map('v', '<', '<gv', opts)
    map('v', '>', '>gv', opts)

    -- 上下移动选中的行
    map('v', 'J', ":m '>+1<CR>gv=gv", opts)
    map('v', 'K', ":m '<-2<CR>gv=gv", opts)

    -- ====== 终端模式 ======
    -- ESC 退出终端模式
    map('t', '<Esc>', '<C-\\><C-n>', vim.tbl_extend('force', opts, { desc = '退出终端模式' }))

    -- ====== expr 示例：智能 Home 键 ======
    -- 按 Home 在行首第一个非空字符和绝对行首之间切换
    map('n', '<Home>', function()
        local col = vim.api.nvim_win_get_cursor(0)[2]
        local line = vim.api.nvim_get_current_line()
        local first_non_blank = line:find('[^%s]') or 1
        -- Lua 字符串索引从 1 开始，光标列从 0 开始
        if col == first_non_blank - 1 then
            vim.api.nvim_win_set_cursor(0, { vim.api.nvim_win_get_cursor(0)[1], 0 })
        else
            vim.api.nvim_win_set_cursor(0, { vim.api.nvim_win_get_cursor(0)[1], first_non_blank - 1 })
        end
    end, { desc = '智能 Home 键' })
end

return M
```

**关于 `vim.tbl_extend`：**

```lua
-- 不用 tbl_extend 的啰嗦写法：
map('n', '<leader>w', '<cmd>write<CR>', { noremap = true, silent = true, desc = '保存' })

-- 用 tbl_extend 提取公共选项：
local opts = { noremap = true, silent = true }
map('n', '<leader>w', '<cmd>write<CR>', vim.tbl_extend('force', opts, { desc = '保存' }))
```

### 局部映射（用于 LSP）

```lua
-- 在 LSP 附着回调中设置仅对该缓冲区生效的映射
vim.api.nvim_create_autocmd('LspAttach', {
    callback = function(args)
        local bufnr = args.buf
        local map = function(lhs, rhs, desc)
            vim.keymap.set('n', lhs, rhs, { buffer = bufnr, desc = desc })
        end

        -- 0.12 默认已经提供 grn/gra/grr 等，这里只补充默认没有的
        map('gd', vim.lsp.buf.definition, '跳转到定义')
        map('grD', vim.lsp.buf.declaration, '跳转到声明')
        map('K', vim.lsp.buf.hover, '查看文档')
    end,
})
```

### 删除映射示例

```lua
-- 假设某插件全局映射了 <leader>x，你想禁用它
vim.keymap.del('n', '<leader>x')

-- 在 LspDetach 中清理局部映射
vim.api.nvim_create_autocmd('LspDetach', {
    callback = function(args)
        vim.keymap.del('n', 'gd', { buffer = args.buf })
        vim.keymap.del('n', 'grD', { buffer = args.buf })
        vim.keymap.del('n', 'K', { buffer = args.buf })
    end,
})
```

### 调试映射

当某个按键行为异常时，先检查它到底被映射到了哪里：

```vim
" 查看普通模式下 <leader>w 的映射来源
:verbose nmap <leader>w

" 查看所有普通模式映射
:nmap

" 用 Lua 查看更详细的元数据
:lua print(vim.inspect(vim.api.nvim_get_keymap('n')))
```

`:verbose map` 会显示映射最后一次被定义的位置（文件和行号），是排查“哪个插件覆盖了我的映射”的利器。

```lua
-- 打印所有以 <leader> 开头的普通模式映射
for _, m in ipairs(vim.api.nvim_get_keymap('n')) do
    if m.lhs:match('^<leader>') then
        print(m.lhs .. ' → ' .. (m.desc or m.rhs))
    end
end
```

---

## 3. 练习

### 练习 1: 基础映射

创建以下按键映射：
- `<leader>h` — 取消搜索高亮
- `<leader>sv` — 垂直分割窗口
- `<leader>sh` — 水平分割窗口

### 练习 2: 映射 Lua 函数

创建一个按键 `<leader>t`，切换 `vim.opt.relativenumber` 的开/关状态。提示：`vim.opt.relativenumber:get()` 获取当前值。

### 练习 3: 用 expr 实现智能 Home 键

实现一个插入模式下的 `<Home>` 映射：按一次跳到行首第一个非空字符，再按一次跳到绝对行首。要求使用 `expr = true`。

提示：插入模式下光标位置可用 `vim.fn.col('.')`，行首非空位置可用 `vim.fn.match(line, '\\S') + 1`。

### 练习 4: 查看与删除当前映射（可选）

在 Neovim 中运行以下命令查看所有映射：
```vim
:lua print(vim.inspect(vim.api.nvim_get_keymap('n')))
```

然后用 `vim.keymap.del` 删除练习 1 中创建的某个映射，再用 `:nmap <leader>h` 验证已删除。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> -- 练习 1: 基础按键映射
> -- 将以下代码放入 init.lua 或 keymaps 模块中
>
> vim.g.mapleader = ' '  -- 确保在映射之前设置
>
> local map = vim.keymap.set
> local opts = { noremap = true, silent = true }
>
> -- <leader>h — 取消搜索高亮
> map('n', '<leader>h', '<cmd>nohlsearch<CR>', vim.tbl_extend('force', opts, { desc = '取消搜索高亮' }))
>
> -- <leader>sv — 垂直分割窗口
> map('n', '<leader>sv', '<cmd>vsplit<CR>', vim.tbl_extend('force', opts, { desc = '垂直分割' }))
>
> -- <leader>sh — 水平分割窗口
> map('n', '<leader>sh', '<cmd>split<CR>', vim.tbl_extend('force', opts, { desc = '水平分割' }))
> ```
>
> **验证方式：** 在 Neovim 中按 `<leader>h`（默认空格+h）看搜索高亮是否清除；按 `<leader>sv` 和 `<leader>sh` 检查窗口是否分割。`:map <leader>h` 可查看已注册的映射。

> [!tip]- 练习 2 参考答案
> ```lua
> -- 练习 2: 映射到 Lua 函数——切换相对行号
> vim.keymap.set('n', '<leader>t', function()
>     local current = vim.opt.relativenumber:get()
>     vim.opt.relativenumber = not current
>     -- 打印提示，让用户知道切换结果
>     if not current then
>         print('相对行号: 开启')
>     else
>         print('相对行号: 关闭')
>     end
> end, { desc = '切换相对行号' })
> ```
>
> **关键点：**
> - `vim.opt.relativenumber:get()` 返回当前布尔值，`not` 取反后赋值回去实现 toggle 效果。
> - `rhs` 是一个 Lua 函数而非字符串，这是 `vim.keymap.set` 最强大的特性——可以在回调中做任意逻辑。
> - 添加 `print()` 或 `vim.notify()` 给用户反馈，提升使用体验。

> [!tip]- 练习 3 参考答案
> ```lua
> -- 练习 3: 插入模式智能 Home 键（expr 版本）
> vim.keymap.set('i', '<Home>', function()
>     local col = vim.fn.col('.')
>     local line = vim.fn.getline('.')
>     local first_non_blank = vim.fn.match(line, '\\S') + 1
>
>     if first_non_blank == 0 then
>         -- 空行或只有空白，直接回绝对行首
>         return '<Home>'
>     end
>
>     if col == first_non_blank then
>         -- 已经在第一个非空字符，跳到绝对行首
>         return '<Home>'
>     else
>         -- 跳到第一个非空字符
>         return '<C-o>^'
>     end
> end, { expr = true, desc = '智能 Home 键' })
> ```
>
> **关键点：**
> - `expr = true` 表示 rhs 函数返回值会被当作按键序列再次解析。
> - `<C-o>^` 在插入模式下执行一次普通模式的 `^`（跳到行首非空字符）。
> - 返回值中的 `<Home>`、`<C-o>` 等会被自动替换为真实 keycode（`replace_keycodes` 默认开启）。
> - 如果函数返回普通字符串，也会被当作按键序列处理。

> [!tip]- 练习 4 参考答案（可选）
> 在 Neovim 中逐步操作：
>
> ```vim
> " 查看所有普通模式映射（JSON-like 输出）
> :lua print(vim.inspect(vim.api.nvim_get_keymap('n')))
>
> " 只看以 <leader> 开头的映射
> :lua for _, m in ipairs(vim.api.nvim_get_keymap('n')) do if m.lhs:match('^<leader>') then print(m.lhs .. ' → ' .. (m.desc or m.rhs)) end end
>
> " 删除练习 1 的 <leader>h 映射
> :lua vim.keymap.del('n', '<leader>h')
>
> " 验证已删除（应无输出或显示原始功能）
> :nmap <leader>h
> ```
>
> **理解：** `vim.api.nvim_get_keymap('n')` 返回一个 table 数组，每个元素包含 `lhs`（按键）、`rhs`（目标）、`desc`（描述）、`mode`、`noremap` 等字段。`vim.keymap.del` 删除时如果映射是 buffer-local 的，必须传 `{ buffer = bufnr }`。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [`:help vim.keymap.set`](https://neovim.io/doc/user/lua.html#vim.keymap.set)
- [`:help vim.keymap.del`](https://neovim.io/doc/user/lua.html#vim.keymap.del)
- [`:help map-modes`](https://neovim.io/doc/user/map.html#map-overview)
- [Neovim Lua Guide — Keymaps](https://neovim.io/doc/user/lua-guide.html#lua-guide-keymaps)
- [`:help gr-default-mappings`](https://neovim.io/doc/user/lsp.html#gr-default-mappings) — 0.12 默认 LSP 映射

---

## 常见陷阱

- **忘记 `silent = true`**：没有它，按键映射执行的命令会打印到命令行，很干扰。
- **`<leader>` 需要先定义**：`vim.g.mapleader` 必须在所有映射之前设置。
- **可视模式映射用 `v` 还是 `x`**：`v` 是字符可视，`x` 是行可视。通常用 `'v'` 就够了，行可视会自动继承。
- **LSP 映射忘记 `buffer`**：不加 `buffer` 选项，映射会全局生效，污染其他缓冲区。
- **用 `:` 而非 `<cmd>` 可能触发副作用**：`:` 会进入命令行模式再返回，触发 `ModeChanged` 等事件。
- **Mac 上 `Cmd` 键**：Neovim 在终端中通常无法识别 `Cmd`（`<D-...>`），要用 GUI 客户端（如 Neovide）才能捕获。
- **`expr` 函数返回字符串时的转义**：返回的字符串会被解析为按键序列。如果返回普通文本，会被逐个字符输入。需要按键语义时确保 `replace_keycodes` 开启。
- **误删 0.12 默认 LSP 映射**：`grn`/`gra` 等已经是全局默认，再定义一次会覆盖，容易让学习者困惑。用 `:verbose map grn` 检查后再决定。
- **`nowait` 的副作用**：设置 `nowait = true` 后，以该 lhs 为前缀的其他长映射将永远没有机会触发。
