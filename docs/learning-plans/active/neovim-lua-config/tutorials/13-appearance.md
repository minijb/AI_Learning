# 13 — 外观定制：colorscheme 与 statusline

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 40 分钟
> 前置知识: 04-init-lua-structure（vim.opt 基本配置）

---

## 1. 概念讲解

### 外观配置的层次

Neovim 的外观由多个层次叠加而成：

```
┌────────────────────────────────────┐
│           statusline               │  ← 状态栏（lualine / heirline）
├────────────────────────────────────┤
│           tabline                  │  ← 标签栏（bufferline）
├────────────────────────────────────┤
│                                    │
│           编辑区                    │  ← colorscheme + Treesitter 高亮
│     (语法高亮 / 背景色 / 字体)      │
│                                    │
├────────────────────────────────────┤
│           cmdline                  │  ← 命令行（noice.nvim 可美化）
└────────────────────────────────────┘
```

### colorscheme（配色方案）

配色方案定义了所有语法元素、UI 组件的颜色。现代 Neovim 配色方案通常支持：
- **Treesitter 高亮组** — 更细粒度的语法着色
- **LSP 诊断颜色** — 错误/警告/提示的标记色
- **插件高亮组** — Telescope、nvim-cmp、gitsigns 等

```lua
-- 设置 colorscheme
vim.cmd.colorscheme("tokyonight")

-- 或通过 lazy.nvim 配置（推荐，因为可以懒加载其他 UI 元素）
{
    "folke/tokyonight.nvim",
    lazy = false,      -- 启动时加载
    priority = 1000,   -- 在其他 UI 插件之前
    opts = {
        style = "night",
        transparent = false,
        -- 自定义某些高亮组
        on_highlights = function(hl, c)
            hl.Comment = { fg = c.blue, italic = true }
        end,
    },
    config = function(_, opts)
        require("tokyonight").setup(opts)
        vim.cmd.colorscheme("tokyonight")
    end,
}
```

### 热门配色方案推荐

| 配色方案 | 风格 | 特点 |
|---------|------|------|
| [tokyonight.nvim](https://github.com/folke/tokyonight.nvim) | 暗色 | 三种变体 (night / storm / day) |
| [catppuccin](https://github.com/catppuccin/nvim) | 暗/亮 | 四种风味，大量插件集成 |
| [rose-pine](https://github.com/rose-pine/neovim) | 暖色暗 | 低对比度，护眼 |
| [onedark.nvim](https://github.com/navarasu/onedark.nvim) | 暗色 | Atom 风格 |
| [gruvbox.nvim](https://github.com/ellisonleao/gruvbox.nvim) | 复古暖 | 高可读性，经典方案 |
| [kanagawa.nvim](https://github.com/rebelot/kanagawa.nvim) | 暖色暗 | 浮世绘灵感 |
| [nightfox.nvim](https://github.com/EdenEast/nightfox.nvim) | 暗色 | 多种变体，高对比度 |

### lualine.nvim（状态栏）

状态栏显示模式、文件名、诊断数、Git 分支、光标位置等信息：

```lua
{
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    opts = {
        options = {
            theme = "tokyonight",
            component_separators = { left = "", right = "" },
            section_separators = { left = "", right = "" },
        },
        sections = {
            lualine_a = { "mode" },
            lualine_b = { "branch", "diff", "diagnostics" },
            lualine_c = { "filename" },
            lualine_x = { "encoding", "fileformat", "filetype" },
            lualine_y = { "progress" },
            lualine_z = { "location" },
        },
    },
}
```

### bufferline（标签栏）

类似 VS Code 的标签页，显示打开的文件：

```lua
{
    "akinsho/bufferline.nvim",
    event = "VeryLazy",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    opts = {
        options = {
            mode = "buffers",
            numbers = "none",
            close_command = "bdelete! %d",
            -- 右侧显示 LSP 诊断数量
            diagnostics = "nvim_lsp",
            diagnostics_indicator = function(_, _, diag)
                local icons = { error = "✘ ", warn = "⚠ ", info = "ⓘ ", hint = "ⓗ " }
                local ret = {}
                for _, d in ipairs(diag) do
                    table.insert(ret, icons[d.severity])
                end
                return table.concat(ret, "")
            end,
        },
    },
}
```

---

## 2. 代码示例

完整的 `lua/plugins/ui.lua`（合并 colorscheme + lualine + bufferline + 其他 UI 插件）：

```lua
-- lua/plugins/ui.lua
return {
    -- ====== 配色方案 ======
    {
        "folke/tokyonight.nvim",
        lazy = false,
        priority = 1000,
        opts = {
            style = "night",
            transparent = false,
            styles = {
                comments = { italic = true },
                keywords = { italic = true },
            },
        },
        config = function(_, opts)
            require("tokyonight").setup(opts)
            vim.cmd.colorscheme("tokyonight")
        end,
    },

    -- ====== 状态栏 ======
    {
        "nvim-lualine/lualine.nvim",
        event = "VeryLazy",
        dependencies = { "nvim-tree/nvim-web-devicons" },
        opts = {
            options = {
                theme = "tokyonight",
                globalstatus = true,  -- 所有窗口共享一条状态栏
                component_separators = { left = "", right = "" },
                section_separators = { left = "", right = "" },
            },
            sections = {
                lualine_a = {
                    {
                        "mode",
                        fmt = function(str)
                            return str:sub(1, 1)  -- 只显示首字母
                        end,
                    },
                },
                lualine_b = { "branch", "diff", "diagnostics" },
                lualine_c = {
                    {
                        "filename",
                        path = 1,  -- 0 = 仅文件名, 1 = 相对路径, 2 = 绝对路径
                    },
                },
                lualine_x = { "encoding", "fileformat", "filetype" },
                lualine_y = { "progress" },
                lualine_z = { "location" },
            },
        },
    },

    -- ====== 标签栏 ======
    {
        "akinsho/bufferline.nvim",
        event = "VeryLazy",
        dependencies = { "nvim-tree/nvim-web-devicons" },
        opts = {
            options = {
                mode = "buffers",
                numbers = "ordinal",
                close_command = "bdelete! %d",
                diagnostics = "nvim_lsp",
                offsets = {
                    {
                        filetype = "NvimTree",
                        text = "文件树",
                        padding = 1,
                    },
                },
            },
        },
    },

    -- ====== 行号列诊断图标 ======
    {
        "folke/trouble.nvim",
        cmd = "Trouble",
        keys = {
            { "<leader>xx", "<cmd>Trouble diagnostics toggle<CR>", desc = "诊断面板" },
            { "<leader>xL", "<cmd>Trouble loclist toggle<CR>",  desc = "位置列表" },
        },
        opts = {},
    },

    -- ====== 启动界面 ======
    {
        "goolord/alpha-nvim",
        cmd = "Alpha",
        opts = function()
            local dashboard = require("alpha.themes.dashboard")
            dashboard.section.header.val = {
                [[                                     ]],
                [[  ███╗   ██╗███████╗ ██████╗ ██╗   ██╗██╗███╗   ███╗ ]],
                [[  ████╗  ██║██╔════╝██╔═══██╗██║   ██║██║████╗ ████║ ]],
                [[  ██╔██╗ ██║█████╗  ██║   ██║██║   ██║██║██╔████╔██║ ]],
                [[  ██║╚██╗██║██╔══╝  ██║   ██║╚██╗ ██╔╝██║██║╚██╔╝██║ ]],
                [[  ██║ ╚████║███████╗╚██████╔╝ ╚████╔╝ ██║██║ ╚═╝ ██║ ]],
                [[  ╚═╝  ╚═══╝╚══════╝ ╚═════╝   ╚═══╝  ╚═╝╚═╝     ╚═╝ ]],
                [[                                     ]],
            }
            dashboard.section.buttons.val = {
                dashboard.button("f", " 查找文件", ":Telescope find_files<CR>"),
                dashboard.button("r", " 最近文件", ":Telescope oldfiles<CR>"),
                dashboard.button("g", " 搜索文本", ":Telescope live_grep<CR>"),
                dashboard.button("c", " 配置", ":e ~/.config/nvim/init.lua<CR>"),
                dashboard.button("q", " 退出", ":qa<CR>"),
            }
            return dashboard.opts
        end,
    },
}
```

**运行方式:**
1. 将上述内容保存为 `lua/plugins/ui.lua`
2. 重启 Neovim，观察启动界面、状态栏、标签栏的变化

---

## 3. 练习

### 练习 1: 更换 colorscheme
从推荐列表中选一个你喜欢的 colorscheme，按照 lazy.nvim 的 spec 格式安装并启用。验证：
- 语法高亮正确（打开一个 Lua 文件查看）
- LSP 诊断颜色正常（写错代码看红色标记）
- 补全菜单颜色协调

### 练习 2: 配置 lualine
修改 lualine 的 `sections` 配置，在状态栏中添加当前时间的显示。提示：lualine 支持自定义组件：
```lua
lualine_z = {
    { "datetime", style = "%H:%M" },
    "location",
},
```

### 练习 3: 隐藏 UI 元素（可选）
在 Neovim 中，有时需要完全沉浸。创建一个按键 `<leader>ui`，一键切换以下元素：
- `vim.opt.number`
- `vim.opt.relativenumber`
- `vim.opt.signcolumn`（在 "yes" 和 "no" 之间切换）
- lualine 的显示/隐藏（`vim.opt.laststatus = 0 / 3`）
- bufferline 的隐藏（`:BufferLineToggle` 命令如果有的话）

---

## 4. 扩展阅读

- [Neovim 配色方案集合](https://github.com/rockerBOO/awesome-neovim#colorscheme)
- [lualine.nvim 文档](https://github.com/nvim-lualine/lualine.nvim)
- [bufferline.nvim 文档](https://github.com/akinsho/bufferline.nvim)
- [`:help hl-groups`](https://neovim.io/doc/user/syntax.html#highlight-groups) — 所有可用高亮组

---

## 常见陷阱

- **colorscheme 未生效时先检查 `termguicolors`**：`vim.opt.termguicolors = true` 必须开启。
- **颜色不对可能是终端不支持 true color**：检查 `$COLORTERM` 是否包含 `truecolor`。
- **lualine 主题名需要与 colorscheme 匹配**：如果不匹配，手动指定 `options.theme = "auto"` 让 lualine 自动提取颜色，或选择一个兼容的主题名。
- **bufferline 和 nvim-tree 同时显示可能重叠**：在 bufferline 的 `offsets` 中为 nvim-tree 预留空间。
- **过多 UI 插件影响启动速度**：所有 UI 都用 `event = "VeryLazy"`，只让 colorscheme 设为 `lazy = false`。
