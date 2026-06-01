# 07 — lazy.nvim 插件管理

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 60 分钟
> 前置知识: 04-init-lua-structure（模块化配置结构）

---

## 1. 概念讲解

### 为什么需要插件管理器？

Neovim 原生支持通过 `packpath` 加载插件，但缺少：
- 自动安装和更新
- 懒加载（按需加载，加速启动）
- 依赖管理
- 插件状态/健康检查

**lazy.nvim**（作者 folke）是目前最流行的插件管理器，它统一解决了这些问题。

### lazy.nvim 核心概念

```lua
{
    "owner/repo",             -- GitHub 仓库简写
    -- 完整配置:
    --   "url",               -- 完整 Git URL
    --   dir = "...",         -- 本地路径
    --   name = "...",        -- 自定义插件名

    lazy = true,              -- 是否懒加载（默认 true）

    -- 加载触发器（任一个满足就加载）:
    event = "VeryLazy",       -- 事件触发后加载
    cmd = "Telescope",        -- 命令被调用时加载
    keys = "<leader>ff",      -- 按键被按下时加载
    ft = "lua",               -- 文件类型匹配时加载

    dependencies = { ... },   -- 依赖的其他插件

    -- 配置方式三选一：
    opts = {},                -- 方式 1: 传给 setup() 的选项表
    config = function() end,  -- 方式 2: 自定义配置函数
    -- 都不提供则默认调用 require("plugin-name").setup({})
}
```

### 懒加载策略

| 触发器 | 适用场景 | 示例 |
|--------|---------|------|
| `event = "VeryLazy"` | 在 UI 加载完成后才需要的插件 | colorscheme, statusline |
| `cmd = "..."` | 通过命令调用的插件 | Telescope, LazyGit |
| `keys = "..."` | 通过按键调用的插件 | Telescope, which-key |
| `ft = "..."` | 特定文件类型需要的插件 | 语言特定的 LSP |
| `event = "..."` | 特定事件触发 | `BufReadPre` |
| 不设触发器 (`lazy = false`) | 启动时必须加载 | lazy.nvim 本身 |

### 目录结构（推荐）

```
~/.config/nvim/
├── init.lua
├── lua/
│   ├── config/
│   │   ├── lazy.lua          ← lazy.nvim 自身初始化
│   │   └── ...
│   └── plugins/
│       ├── ui.lua            ← 外观相关插件
│       ├── editor.lua        ← 编辑器增强插件
│       ├── lsp.lua           ← LSP 相关
│       ├── coding.lua        ← 补全/Treesitter
│       └── tools.lua         ← Telescope 等工具
└── lazy-lock.json            ← 版本锁定文件（自动生成，提交到 Git）
```

---

## 2. 代码示例

### 步骤 1: 初始化 lazy.nvim

```lua
-- lua/config/lazy.lua
local M = {}

function M.setup()
    local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"

    -- 自动安装 lazy.nvim
    if not vim.loop.fs_stat(lazypath) then
        vim.fn.system({
            "git",
            "clone",
            "--filter=blob:none",
            "https://github.com/folke/lazy.nvim.git",
            "--branch=stable",
            lazypath,
        })
    end
    vim.opt.rtp:prepend(lazypath)

    -- 加载插件列表并初始化
    local plugins = {
        -- 在此处直接写，或从各文件合并：
    }

    require("lazy").setup(plugins, {
        -- lazy.nvim 自身配置
        root = vim.fn.stdpath("data") .. "/lazy",  -- 插件安装路径
        defaults = { lazy = true },                 -- 默认懒加载
        performance = {
            rtp = {
                disabled_plugins = { "gzip", "matchit", "matchparen", "netrw" },
            },
        },
    })
end

return M
```

### 步骤 2: 模块化插件列表

```lua
-- lua/config/lazy.lua 中的改进版 plugins 加载
function M.setup()
    -- ... lazy.nvim 自安装代码 ...

    require("lazy").setup({
        { import = "plugins" },  -- 自动加载 lua/plugins/ 下所有模块
    }, {
        defaults = { lazy = true },
        -- 安装时自动检查
        checker = { enabled = true, notify = false },
        change_detection = { notify = false },
        performance = {
            rtp = { disabled_plugins = { "gzip", "matchit", "matchparen", "netrw" } },
        },
    })
end
```

### 步骤 3: 各插件模块

```lua
-- lua/plugins/ui.lua
return {
    -- 配色方案（不懒加载，因为启动就需要）
    {
        "folke/tokyonight.nvim",
        lazy = false,
        priority = 1000,
        opts = {
            style = "night",
            transparent = false,
        },
    },

    -- 状态栏（VeryLazy 事件触发即可）
    {
        "nvim-lualine/lualine.nvim",
        event = "VeryLazy",
        opts = {
            options = { theme = "tokyonight" },
        },
    },
}
```

```lua
-- lua/plugins/tools.lua
return {
    -- Telescope: 通过命令加载
    {
        "nvim-telescope/telescope.nvim",
        cmd = "Telescope",
        keys = {
            { "<leader>ff", "<cmd>Telescope find_files<CR>", desc = "查找文件" },
            { "<leader>fg", "<cmd>Telescope live_grep<CR>", desc = "搜索文本" },
            { "<leader>fb", "<cmd>Telescope buffers<CR>", desc = "缓冲区" },
        },
        dependencies = { "nvim-lua/plenary.nvim" },
        opts = {
            defaults = {
                layout_strategy = "horizontal",
                layout_config = { prompt_position = "top" },
                sorting_strategy = "ascending",
            },
        },
    },

    -- which-key: 显示按键提示
    {
        "folke/which-key.nvim",
        event = "VeryLazy",
        opts = {},
    },
}
```

### 步骤 4: 完整 init.lua

```lua
-- ~/.config/nvim/init.lua

vim.g.mapleader = " "
vim.g.maplocalleader = " "

require("config.options").setup()
require("config.keymaps").setup()
require("config.autocmds").setup()
require("config.lazy").setup()  -- 放在最后，因为插件可能依赖基础配置
```

### 启动后使用

```vim
:Lazy          " 打开管理界面
:Lazy sync     " 同步所有插件
:Lazy update   " 更新所有插件
:Lazy clean    " 清理未引用的插件
:Lazy health   " 健康检查
```

---

## 3. 练习

### 练习 1: 安装第一个插件
在 `lua/plugins/` 下创建 `ui.lua`，安装 `tokyonight.nvim`，设置 `lazy = false` 和 `priority = 1000`。在 `options.lua` 中启用 `termguicolors`，然后设置 colorscheme：

```lua
-- 在 options.lua 末尾
vim.cmd.colorscheme("tokyonight")
```

重启 Neovim，看到新配色即成功。

### 练习 2: 懒加载插件
安装 `nvim-treesitter`（只需安装，配置见第 11 节），设置触发条件为 `event = { "BufReadPost", "BufNewFile" }`。打开 `:Lazy` 界面，检查状态栏中该插件是否显示已加载（loaded）。

### 练习 3: 锁定版本（可选）
运行 `:Lazy restore` 和 `:Lazy lock`，查看生成的 `lazy-lock.json` 内容。理解这个文件的作用：它锁定每个插件的 commit hash，确保不同机器上安装的插件版本完全一致。

---

## 4. 扩展阅读

- [lazy.nvim 官方文档](https://github.com/folke/lazy.nvim)
- [lazy.nvim 结构化配置指南](https://github.com/folke/lazy.nvim#-structuring-your-plugins)
- [`:help lazy.nvim`](https://github.com/folke/lazy.nvim/blob/main/doc/lazy.nvim.txt)

---

## 常见陷阱

- **`VeryLazy` vs `UIEnter`**：`VeryLazy` 是 `UIEnter` 之后的一个事件，用于需要 UI 但不急于启动的插件。多数字段用 `event = "VeryLazy"` 即可。
- **忘记 `lazy = false` 给 colorscheme**：colorscheme 在启动时就需加载。同时设 `priority = 1000` 确保它在其他 UI 插件之前加载。
- **循环依赖**：插件 A 依赖 B，B 又（间接）依赖 A。避免在 `config` 回调中 `require` 其他插件的模块。
- **多次触发加载**：同时设置 `cmd`、`keys`、`ft` 可能导致插件被多次加载。lazy.nvim 有保护机制，但最好保持触发条件简洁。
- **Windows 上 `vim.fn.system` 调用 Git 可能因路径问题失败**：确保 Git 在 PATH 中。
- **lock 文件不提交**：`lazy-lock.json` 应该提交到版本控制，用于可复现的安装。
