# 11 — Treesitter：语法高亮与结构化分析

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 50 分钟
> 前置知识: 07-lazy-nvim（插件的安装与配置）

---

## 1. 概念讲解

### 什么是 Tree-sitter？

Tree-sitter 是一个增量解析库，能将源代码解析成**具体语法树（CST）**。与传统的正则高亮不同：

| 特性 | 正则高亮 | Tree-sitter |
|------|---------|------------|
| 准确性 | 基于模式匹配，复杂嵌套易出错 | 基于语法解析，100% 准确 |
| 速度 | O(n) 扫描 | 增量解析，O(log n) |
| 支持功能 | 高亮 | 高亮、折叠、缩进、选区扩展、代码注入 |

### nvim-treesitter 的功能模块

```
nvim-treesitter
├── highlight     — 语法高亮（替代 regex 高亮）
├── incremental_selection — 按语法结构扩展/缩小选区
├── indent        — 基于语法的自动缩进
├── fold          — 基于语法的代码折叠
├── textobjects   — 按函数/类等结构跳转
├── context       — 显示当前函数的上下文
└── refactor      — 智能重命名等重构功能
```

### 语言解析器（Parser）

Tree-sitter 的每种语言需要单独安装解析器：

```lua
ensure_installed = { "lua", "rust", "python", "javascript", "typescript", "go", "c", "markdown" }
```

可以通过 `:TSInstall <lang>` 手动安装，或者通过 `ensure_installed` 自动安装。

### 代码注入（Injection）

Tree-sitter 能识别一种语言中嵌入的另一种语言——如 HTML 中的 CSS/JS、Lua 中 Vim 命令字符串：

```html
<!-- Vue SFC: HTML + CSS + JavaScript — 三种高亮自动共存 -->
<template>
    <div>{{ message }}</div>  <!-- JS 表达式高亮 -->
</template>
<style>
    .title { color: red; }    <!-- CSS 高亮 -->
</style>
```

---

## 2. 代码示例

```lua
-- lua/plugins/treesitter.lua
return {
    {
        "nvim-treesitter/nvim-treesitter",
        build = ":TSUpdate",
        event = { "BufReadPost", "BufNewFile" },
        dependencies = {
            "nvim-treesitter/nvim-treesitter-textobjects", -- 结构跳转
        },
        config = function()
            require("nvim-treesitter.configs").setup({
                -- 自动安装的语言解析器
                ensure_installed = {
                    "lua",
                    "vim",
                    "vimdoc",
                    "python",
                    "rust",
                    "javascript",
                    "typescript",
                    "go",
                    "c",
                    "cpp",
                    "json",
                    "yaml",
                    "markdown",
                    "markdown_inline",
                    "bash",
                    "html",
                    "css",
                },

                -- 模块配置
                highlight = {
                    enable = true,
                    -- 禁用某些文件类型的 Tree-sitter 高亮（回退到正则）
                    disable = function(lang, bufnr)
                        local max_filesize = 100 * 1024  -- 100 KB
                        local ok, stats = pcall(vim.loop.fs_stat,
                            vim.api.nvim_buf_get_name(bufnr))
                        if ok and stats and stats.size > max_filesize then
                            return true
                        end
                    end,
                    additional_vim_regex_highlighting = false,
                },

                indent = {
                    enable = true,
                },

                -- 增量选择：按语法节点扩展选区
                incremental_selection = {
                    enable = true,
                    keymaps = {
                        init_selection = "gnn",   -- 开始选择当前节点
                        node_incremental = "grn", -- 扩展到父节点
                        scope_incremental = "grc", -- 扩展到作用域
                        node_decremental = "grm", -- 收缩到子节点
                    },
                },

                -- 基于语法的代码折叠（可选，与 nvim-ufo 冲突时禁用）
                -- fold = {
                --     enable = true,
                -- },

                -- textobjects: 按函数/类等结构跳转和选择
                textobjects = {
                    select = {
                        enable = true,
                        lookahead = true,
                        keymaps = {
                            ["af"] = "@function.outer",   -- 选择整个函数
                            ["if"] = "@function.inner",   -- 选择函数体
                            ["ac"] = "@class.outer",
                            ["ic"] = "@class.inner",
                            ["aa"] = "@parameter.outer",  -- 选择参数
                            ["ia"] = "@parameter.inner",
                        },
                    },
                    move = {
                        enable = true,
                        set_jumps = true,
                        goto_next_start = {
                            ["]f"] = "@function.outer",
                            ["]]"] = "@class.outer",
                        },
                        goto_previous_start = {
                            ["[f"] = "@function.outer",
                            ["[["] = "@class.outer",
                        },
                    },
                },
            })
        end,
    },

    -- nvim-treesitter-context: 显示当前函数的签名上下文
    {
        "nvim-treesitter/nvim-treesitter-context",
        event = "VeryLazy",
        opts = {
            max_lines = 3,
            trim_scope = "outer",
        },
    },
}
```

**运行方式:**
1. 保存为 `lua/plugins/treesitter.lua`
2. 重启 Neovim，首次启动会自动下载安装所有 `ensure_installed` 中的解析器（需要网络和 C 编译器）
3. 打开一个 Lua 文件，观察语法高亮是否比纯正则更丰富（如函数参数的区分色）
4. 在函数定义上按 `gnn`，观察增量选择

---

## 3. 练习

### 练习 1: 对比高亮效果
在 Neovim 中临时禁用 Tree-sitter 高亮：
```vim
:lua vim.treesitter.stop()
```
观察高亮变化，然后重新启用：
```vim
:lua vim.treesitter.start()
```
对比两者差异（尤其在嵌套函数、模板字符串等复杂场景）。

### 练习 2: 增量选择练习
打开一个有函数定义的 Lua 文件，在函数体内部按 `gnn`（开始选择），然后按 `grn` 反复扩展选区，再按 `grm` 收缩。理解语法节点和选区的对应关系。

### 练习 3: 添加你的语言（可选）
如果你使用 Tree-sitter 尚未覆盖的语言（如 Elixir、Zig），运行 `:TSInstallInfo` 查看可用语言列表，手动 `:TSInstall <lang>`，然后添加到 `ensure_installed` 中。

---

## 4. 扩展阅读

- [nvim-treesitter 官方文档](https://github.com/nvim-treesitter/nvim-treesitter)
- [Tree-sitter 官网](https://tree-sitter.github.io/tree-sitter/)
- [nvim-treesitter-textobjects 文档](https://github.com/nvim-treesitter/nvim-treesitter-textobjects)
- [`:help treesitter`](https://neovim.io/doc/user/treesitter.html)

---

## 常见陷阱

- **Windows 上需要 C 编译器**：Tree-sitter 解析器需要编译。安装 MSVC 或 MinGW。如果 `:TSInstall` 失败，检查 `:checkhealth treesitter`。
- **`ensure_installed` 列表中不存在的语言**：如果拼写错误或语言不受支持，安装会失败但不影响其他语言。
- **大文件禁用高亮**：打开上 MB 的日志文件时，Tree-sitter 解析可能很慢。`highlight.disable` 函数中检查文件大小是个好习惯。
- **与 `vim-regex` 高亮冲突**：设置 `additional_vim_regex_highlighting = false` 避免双重高亮导致颜色错乱。
- **`@function.inner` 等 textobjects 需要 textobjects 模块**：如果 `af` 不生效，检查 `nvim-treesitter-textobjects` 是否在 dependencies 中。
