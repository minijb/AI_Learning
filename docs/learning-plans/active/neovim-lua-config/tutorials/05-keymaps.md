---
title: "05 — 按键映射完全指南"
updated: 2026-06-05
---

# 05 — 按键映射完全指南

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 40 分钟
> 前置知识: 04-init-lua-structure（init.lua 结构、vim.g）

---

## 1. 概念讲解

### 为什么按键映射是配置的核心？

编辑器效率取决于手指不离开键盘。按键映射让你：
- 缩短常用操作（如 `<leader>ff` 查找文件）
- 统一跨插件的快捷键习惯
- 为自定义功能分配快捷键

### vim.keymap.set（Neovim 0.7+）

这是配置按键映射的唯一推荐方式。它统一了之前混乱的 `vim.api.nvim_set_keymap` 和 Vimscript 的 `nmap`/`imap` 等：

```lua
vim.keymap.set(mode, lhs, rhs, opts)
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `mode` | 模式字符串 | `"n"` 普通, `"i"` 插入, `"v"` 可视, `"t"` 终端 |
| `lhs` | 按键序列 | `"<leader>ff"`, `"<C-p>"` |
| `rhs` | 目标：命令字符串或 Lua 函数 | `":w<CR>"`, `function() ... end` |
| `opts` | 选项 table | `{ desc = "...", silent = true }` |

### 模式速查

| 模式 | 字符串 | 组合示例 |
|------|--------|---------|
| 普通模式 | `"n"` | `"n"` |
| 插入模式 | `"i"` | `"i"` |
| 可视模式 | `"v"` | `"v"` |
| 可视行模式 | `"x"` | `"x"` |
| 选择模式 | `"s"` | `"s"` |
| 命令模式 | `"c"` | `"c"` |
| 终端模式 | `"t"` | `"t"` |
| 普通+可视+操作符待决 | — | `{ "n", "v", "o" }` |

### 常用选项

```lua
vim.keymap.set("n", "<leader>w", "<cmd>w<CR>", {
    desc = "保存文件",        -- 出现在 which-key 等插件中
    silent = true,             -- 不显示执行的命令
    noremap = true,            -- 不递归映射（默认 true，通常保持）
    buffer = 0,                -- 仅当前缓冲区生效（用于 LSP 等局部映射）
    expr = false,              -- rhs 是否作为表达式求值
})
```

### `<cmd>` vs `:`

```lua
-- <cmd> 方式（推荐）：不需要切换模式，支持特殊字符
vim.keymap.set("n", "<leader>w", "<cmd>write<CR>")

-- : 方式：进入命令行模式再执行
vim.keymap.set("n", "<leader>w", ":write<CR>")

-- Lua 函数方式（最灵活）
vim.keymap.set("n", "<leader>w", function()
    vim.cmd.write()
    print("文件已保存")
end)
```

**推荐用 `<cmd>` 或 Lua 函数**。`<cmd>` 不需要离开当前模式，不会触发 `InsertLeave` 等事件。

### leader 键规范

```lua
vim.g.mapleader = " "  -- 空格键作为 leader

-- 社区广泛使用的约定：
-- <leader> + 单键      → 高频操作（如 <leader>w 保存）
-- <leader> + 双键组合  → 按功能分组
--   <leader>f*         → 文件操作（find file, find grep）
--   <leader>g*         → Git 操作
--   <leader>c*         → 代码操作
--   <leader>l*         → LSP 操作
--   <leader>s*         → 搜索
--   <leader>x*         → 诊断/问题
```

---

## 2. 代码示例

完整的 `lua/config/keymaps.lua`：

```lua
-- lua/config/keymaps.lua
local M = {}

function M.setup()
    local map = vim.keymap.set
    local opts = { noremap = true, silent = true }

    -- ====== 基础操作 ======
    -- 保存
    map("n", "<leader>w", "<cmd>write<CR>", vim.tbl_extend("force", opts, { desc = "保存" }))

    -- 退出
    map("n", "<leader>q", "<cmd>quit<CR>", vim.tbl_extend("force", opts, { desc = "退出" }))

    -- 用 ESC 清除搜索高亮
    map("n", "<Esc>", "<cmd>nohlsearch<CR>", opts)

    -- ====== 窗口导航 ======
    -- Ctrl + hjkl 在窗口间跳转
    map("n", "<C-h>", "<C-w>h", vim.tbl_extend("force", opts, { desc = "跳转到左侧窗口" }))
    map("n", "<C-j>", "<C-w>j", vim.tbl_extend("force", opts, { desc = "跳转到下方窗口" }))
    map("n", "<C-k>", "<C-w>k", vim.tbl_extend("force", opts, { desc = "跳转到上方窗口" }))
    map("n", "<C-l>", "<C-w>l", vim.tbl_extend("force", opts, { desc = "跳转到右侧窗口" }))

    -- ====== 缓冲区操作 ======
    -- Tab 切换缓冲区
    map("n", "<Tab>", "<cmd>bnext<CR>", vim.tbl_extend("force", opts, { desc = "下一个缓冲区" }))
    map("n", "<S-Tab>", "<cmd>bprevious<CR>", vim.tbl_extend("force", opts, { desc = "上一个缓冲区" }))

    -- 关闭缓冲区
    map("n", "<leader>bd", "<cmd>bdelete<CR>", vim.tbl_extend("force", opts, { desc = "关闭缓冲区" }))

    -- ====== 文本操作 ======
    -- 可视模式下保持缩进后不丢失选择
    map("v", "<", "<gv", opts)
    map("v", ">", ">gv", opts)

    -- 上下移动选中的行
    map("v", "J", ":m '>+1<CR>gv=gv", opts)
    map("v", "K", ":m '<-2<CR>gv=gv", opts)

    -- ====== 终端模式 ======
    -- ESC 退出终端模式
    map("t", "<Esc>", "<C-\\><C-n>", vim.tbl_extend("force", opts, { desc = "退出终端模式" }))
end

return M
```

**关于 `vim.tbl_extend`：**

```lua
-- 不用 tbl_extend 的啰嗦写法：
map("n", "<leader>w", "<cmd>write<CR>", { noremap = true, silent = true, desc = "保存" })

-- 用 tbl_extend 提取公共选项：
local opts = { noremap = true, silent = true }
map("n", "<leader>w", "<cmd>write<CR>", vim.tbl_extend("force", opts, { desc = "保存" }))
```

### 局部映射（用于 LSP）

```lua
-- 在 LSP 附着回调中设置仅对该缓冲区生效的映射
vim.api.nvim_create_autocmd("LspAttach", {
    callback = function(args)
        local bufnr = args.buf
        local map = function(lhs, rhs, desc)
            vim.keymap.set("n", lhs, rhs, { buffer = bufnr, desc = desc })
        end

        map("gd", vim.lsp.buf.definition, "跳转到定义")
        map("gr", vim.lsp.buf.references, "查找引用")
        map("K", vim.lsp.buf.hover, "查看文档")
    end,
})
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

### 练习 3: 查看当前按键映射（可选）
在 Neovim 中运行以下命令查看所有映射：
```vim
:lua print(vim.inspect(vim.api.nvim_get_keymap("n")))
```
用 `:Telescope keymaps`（安装 Telescope 后）交互式查看。

---

## 4. 扩展阅读

- [`:help vim.keymap.set`](https://neovim.io/doc/user/lua.html#vim.keymap.set)
- [`:help map-modes`](https://neovim.io/doc/user/map.html#map-overview)
- [Neovim Lua Guide — Keymaps](https://neovim.io/doc/user/lua-guide.html#lua-guide-keymaps)

---

## 常见陷阱

- **忘记 `silent = true`**：没有它，按键映射执行的命令会打印到命令行，很干扰。
- **`<leader>` 需要先定义**：`vim.g.mapleader` 必须在所有映射之前设置。
- **可视模式映射用 `v` 还是 `x`**：`v` 是字符可视，`x` 是行可视。通常用 `"v"` 就够了，行可视会自动继承。
- **LSP 映射忘记 `buffer`**：不加 `buffer` 选项，映射会全局生效，污染其他缓冲区。
- **用 `:` 而非 `<cmd>` 可能触发副作用**：`:` 会进入命令行模式再返回，触发 `ModeChanged` 等事件。
- **Mac 上 `Cmd` 键**：Neovim 在终端中通常无法识别 `Cmd`（`<D-...>`），要用 GUI 客户端（如 Neovide）才能捕获。
