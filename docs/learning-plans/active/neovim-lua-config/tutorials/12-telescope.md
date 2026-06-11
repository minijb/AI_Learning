---
title: "12 — Telescope：模糊查找一切"
updated: 2026-06-05
---

# 12 — Telescope：模糊查找一切

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 45 分钟
> 前置知识: 07-lazy-nvim（插件安装与配置）

---

## 1. 概念讲解

### Telescope 能做什么？

Telescope 是 Neovim 的通用模糊查找界面。它统一了各类查找需求：

| 功能 | 命令 | 典型映射 |
|------|------|---------|
| 查找文件 | `find_files` | `<leader>ff` |
| 实时 grep | `live_grep` | `<leader>fg` |
| 查找缓冲区 | `buffers` | `<leader>fb` |
| 查找帮助标签 | `help_tags` | `<leader>fh` |
| 查找按键映射 | `keymaps` | `<leader>fk` |
| 查找 Git 文件 | `git_files` | `<leader>gf` |
| 查找当前文件符号 | `lsp_document_symbols` | `<leader>fs` |
| 查找工作区符号 | `lsp_workspace_symbols` | `<leader>fS` |
| 查找诊断 | `diagnostics` | `<leader>fd` |
| 查找最近文件 | `oldfiles` | `<leader>fr` |

### Telescope 的工作原理

```
用户输入 (模糊匹配字符串)
    ↓
Picker (选择器: find_files / live_grep / ...)
    ↓
Sorter (排序: fzf-native / fzy / 默认)
    ↓
Previewer (预览窗口: 内置 / delta / bat)
    ↓
Actions (动作: 打开 / 分割 / 删除 / ...)
```

### 布局策略

```lua
-- 水平布局（默认）：
-- ┌──────────────┬──────────────────┐
-- │  输入/列表    │     预览窗口      │
-- └──────────────┴──────────────────┘

-- 垂直布局：
-- ┌─────────────────────────────────┐
-- │           输入框                 │
-- ├─────────────────────────────────┤
-- │           列表                   │
-- ├─────────────────────────────────┤
-- │           预览窗口               │
-- └─────────────────────────────────┘
```

### 快捷键

在 Telescope 窗口中有默认按键：

| 按键 | 操作 |
|------|------|
| `<C-n>` / `<C-p>` | 上下移动 |
| `<CR>` | 打开选中项 |
| `<C-v>` | 垂直分割打开 |
| `<C-x>` | 水平分割打开 |
| `<C-t>` | 在新 Tab 中打开 |
| `<C-u>` | 预览窗口向上滚动 |
| `<C-d>` | 预览窗口向下滚动 |
| `?` | 显示可用按键帮助 |

---

## 2. 代码示例

```lua
-- lua/plugins/telescope.lua
return {
    {
        "nvim-telescope/telescope.nvim",
        cmd = "Telescope",
        keys = {
            { "<leader>ff", "<cmd>Telescope find_files<CR>",  desc = "查找文件" },
            { "<leader>fg", "<cmd>Telescope live_grep<CR>",   desc = "搜索文本" },
            { "<leader>fb", "<cmd>Telescope buffers<CR>",     desc = "缓冲区列表" },
            { "<leader>fh", "<cmd>Telescope help_tags<CR>",   desc = "帮助标签" },
            { "<leader>fk", "<cmd>Telescope keymaps<CR>",     desc = "按键映射" },
            { "<leader>fr", "<cmd>Telescope oldfiles<CR>",    desc = "最近文件" },
            { "<leader>f/", "<cmd>Telescope current_buffer_fuzzy_find<CR>", desc = "当前缓冲区搜索" },
        },
        dependencies = {
            "nvim-lua/plenary.nvim",
            -- 可选：更好的排序算法
            {
                "nvim-telescope/telescope-fzf-native.nvim",
                build = "make",
                cond = function()
                    return vim.fn.executable("make") == 1
                end,
            },
        },
        opts = {
            defaults = {
                -- 布局：垂直（类 VS Code 风格）
                layout_strategy = "vertical",
                layout_config = {
                    vertical = {
                        prompt_position = "top",
                        mirror = false,
                    },
                },

                -- 排序策略
                sorting_strategy = "ascending",

                -- 文件忽略规则
                file_ignore_patterns = {
                    "node_modules/",
                    ".git/",
                    "target/",
                    "build/",
                    "dist/",
                    "%.pyc",
                },

                -- 预览器
                preview = {
                    -- 文件小于该值时启用语法高亮预览
                    filesize_limit = 0.5,  -- MB
                    timeout = 250,         -- ms
                },

                -- 映射修改（Telescope 窗口内的按键）
                mappings = {
                    i = {
                        ["<C-j>"] = "move_selection_next",
                        ["<C-k>"] = "move_selection_previous",
                        -- 用 Esc 退出（替代默认的 <C-c>）
                        ["<Esc>"] = "close",
                    },
                },
            },

            -- 各 Picker 的默认选项
            pickers = {
                find_files = {
                    hidden = true,        -- 包含隐藏文件
                    find_command = {      -- 自定义查找命令（可选）
                        "rg", "--files", "--hidden",
                        "--glob", "!**/.git/*",
                        "--glob", "!**/node_modules/*",
                    },
                },
                live_grep = {
                    -- 只在当前 Git 仓库中搜索
                    -- grep_open_files = true,
                },
                buffers = {
                    sort_lastused = true,  -- 按最近使用排序
                    theme = "dropdown",     -- 紧凑下拉样式
                },
            },

            -- 扩展
            extensions = {
                -- 如果在 init.lua 中加载:
                -- require("telescope").load_extension("fzf")
            },
        },
        config = function(_, opts)
            local telescope = require("telescope")
            telescope.setup(opts)

            -- 如果 fzf-native 安装成功，加载它
            pcall(telescope.load_extension, "fzf")
        end,
    },
}
```

### 常用自定义操作

```lua
-- 在 init.lua 或 keymaps.lua 中添加自定义 Telescope 命令

-- 搜索当前 Git 仓库中的文件
vim.keymap.set("n", "<leader>gf", function()
    local ok, _ = pcall(require("telescope.builtin").git_files)
    if not ok then
        require("telescope.builtin").find_files()
    end
end, { desc = "Git 文件" })

-- 查找光标下的词
vim.keymap.set("n", "<leader>fW", function()
    require("telescope.builtin").grep_string({ search = vim.fn.expand("<cword>") })
end, { desc = "搜索光标下的词" })

-- 查找可视模式下选中的词
vim.keymap.set("v", "<leader>fW", function()
    vim.cmd('noau normal! "vy"')
    local text = vim.fn.getreg("v")
    require("telescope.builtin").grep_string({ search = text })
end, { desc = "搜索选中文本" })
```

**运行方式:**
1. 保存为 `lua/plugins/telescope.lua`
2. 重启 Neovim
3. 按 `<leader>ff` 打开文件查找，输入部分文件名测试模糊匹配
4. 按 `<leader>fg` 打开实时 grep，输入文本测试实时搜索结果

---

## 3. 练习

### 练习 1: 基础查找
- 用 `<leader>ff` 查找到 `init.lua` 并打开
- 用 `<leader>fg` 搜索 `vim.opt`，观察实时结果
- 用 `<leader>fb` 在打开的文件间切换

### 练习 2: 自定义映射
添加以下 Telescope 映射：
- `<leader>fs` — 查找当前文件的 LSP 符号（`lsp_document_symbols`）
- `<leader>fd` — 查找诊断信息（`diagnostics`）

### 练习 3: 安装 fzf-native（可选）
如果系统有 `make`，在配置中启用 `telescope-fzf-native.nvim`。对比安装前后的排序速度差异（在大型项目中用 `<leader>ff` 测试）。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 基础查找的使用方法：
>
> - **`<leader>ff` 查找文件**：输入 `init` → Telescope 实时过滤，显示所有路径包含 `init` 的文件（如 `init.lua`、`init.vim`）。按 `<C-n>`/`<C-p>` 在列表中上下移动，`<CR>` 在当前窗口打开，`<C-v>` 垂直分割打开。预览窗口实时显示当前高亮项的文件内容。
> - **`<leader>fg` 搜索文本**（live_grep）：输入 `vim.opt` → Telescope 执行 regex 搜索并实时更新结果。与 `find_files` 不同，`live_grep` 按内容匹配，结果列出文件名:行号:匹配行。需要 `ripgrep`（`rg`）已安装在 PATH 中。如果没有 rg，该命令会报错。
> - **`<leader>fb` 切换缓冲区**：显示所有已打开的 buffer 列表，按最近使用排序（`sort_lastused = true`）。选择一个 buffer 后按 `<CR>` 跳转过去。相比 `:bnext`/`:bprev`，Telescope 缓冲区列表更适合在有 10+ 个 buffer 打开时快速切换。
>
> **关键技巧**：在 Telescope 窗口中按 `?` 可以查看所有可用的按键映射——包括 `<C-t>` 新 Tab 打开、`<C-u>`/`<C-d>` 滚动预览窗口等。

> [!tip]- 练习 2 参考答案
> 在 telescope 插件 spec 中添加 LSP 符号和诊断映射：
>
> ```lua
> -- 在 lua/plugins/telescope.lua 的 keys 表中追加：
> {
>   "<leader>fs",
>   function() require("telescope.builtin").lsp_document_symbols() end,
>   desc = "查找当前文件符号"
> },
> {
>   "fd",
>   function() require("telescope.builtin").diagnostics() end,
>   desc = "查找诊断信息"
> },
> ```
>
> 或者在 LspAttach 回调中按 buffer 添加（更贴近 kickstart 风格）：
>
> ```lua
> -- 在 telescope LspAttach autocmd 的回调函数内追加：
> vim.keymap.set('n', '<leader>fs', builtin.lsp_document_symbols,
>   { buffer = b, desc = 'Document Symbols' })
> vim.keymap.set('n', '<leader>fd', builtin.diagnostics,
>   { buffer = b, desc = 'Diagnostics' })
> ```
>
> `lsp_document_symbols` 列出当前文件中的所有函数、类、变量定义——本质上是文件结构浏览器。选中后跳转到对应位置。`diagnostics` 列出所有文件中的 LSP 诊断（错误、警告、提示），支持模糊匹配错误消息。

> [!tip]- 练习 3 参考答案（可选）
> 安装 `telescope-fzf-native.nvim` 的步骤与效果：
>
> 1. **确保 `make` 可用**：终端执行 `make --version` 确认
> 2. **在 telescope 依赖中启用**：
>
> ```lua
> dependencies = {
>   "nvim-lua/plenary.nvim",
>   {
>     "nvim-telescope/telescope-fzf-native.nvim",
>     build = "make",
>     cond = function()
>       return vim.fn.executable("make") == 1
>     end,
>   },
> },
> ```
>
> 3. **在 config 中加载**：已有的 `pcall(telescope.load_extension, "fzf")` 会在 build 成功后加载 fzf 排序器
> 4. **验证**：执行 `:checkhealth telescope`，应看到 `fzf` extension OK
>
> **性能对比测试**：
> - 在一个 1000+ 文件的仓库中按 `<leader>ff` 并输入模糊串
> - 安装 fzf-native 前：排序结果可能在输入停止后还有 0.5-1s 延迟
> - 安装 fzf-native 后：排序几乎是即时的（fzf 算法对模糊匹配做了极致优化）
> - 在小型项目（< 100 文件）中差异不可感知——默认排序器足够
>
> **Windows 注意事项**：如果没有 `make`，`cond` 函数会跳过安装。可以安装 `scoop install make` 或使用 `cmake` 替代（需修改 build 命令）。不装 fzf-native 也不影响正常使用。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Telescope 官方文档](https://github.com/nvim-telescope/telescope.nvim)
- [Telescope 内置 Picker 列表](https://github.com/nvim-telescope/telescope.nvim?tab=readme-ov-file#pickers)
- [Telescope 扩展列表](https://github.com/nvim-telescope/telescope.nvim?tab=readme-ov-file#extensions)
- [telescope-fzf-native.nvim](https://github.com/nvim-telescope/telescope-fzf-native.nvim)

---

## 常见陷阱

- **`live_grep` 需要 `ripgrep`**：Windows 用户需安装 `rg`（`scoop install ripgrep` 或 `winget install BurntSushi.ripgrep.MSVC`）。
- **大仓库中 `find_files` 慢**：用 `git_files` 代替（仅 Git 追踪的文件）。或安装 `telescope-fzf-native.nvim` 使用 fzf 算法。
- **隐藏文件不显示**：设置 `find_files = { hidden = true }`。
- **`telescope-fzf-native.nvim` 的 build 需要 make**：Windows 上通常没有 `make`。跳过即可，默认排序也足够好。
- **Telescope 窗口中的按键不是 Neovim 的按键**：Telescope 窗口是特殊的浮动窗口，有自己的键绑定。修改映射要到 `opts.defaults.mappings` 中。
