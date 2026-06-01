# 08 — 常用插件配置模式

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 50 分钟
> 前置知识: 07-lazy-nvim（lazy.nvim 基本使用）

---

## 1. 概念讲解

### Neovim 插件的三种配置模式

绝大多数 Neovim 插件遵循以下三种配置模式之一：

#### 模式 1: `setup(opts)` — 最常见

```lua
-- 插件提供 setup() 函数，接受一个 opts table
require("plugin_name").setup({
    option1 = true,
    option2 = { ... },
})
```

这是最标准的模式。lazy.nvim 的 `opts` 字段就是为这种模式设计的糖：

```lua
-- 这三行等价于上面：
{
    "author/plugin_name.nvim",
    opts = {
        option1 = true,
        option2 = { ... },
    },
}
```

#### 模式 2: `config` 回调 — 需要自定义初始化

有些插件的配置需要执行额外步骤（如注册按键、调用多个 API）：

```lua
{
    "author/plugin.nvim",
    config = function()
        require("plugin").setup({
            -- opts
        })
        -- 额外配置
        vim.keymap.set("n", "<leader>x", "<cmd>PluginCommand<CR>")
    end,
}
```

#### 模式 3: 文件类型特定配置 — 仅对特定文件生效

对于语言相关的插件（linter、formatter）：

```lua
{
    "author/linter.nvim",
    ft = { "python", "javascript", "rust" },  -- 仅在这些文件类型打开时加载
    config = function()
        require("linter").setup({
            -- 配置
        })
    end,
}
```

### 常用的"基础设施"插件

在搭建完整配置之前，有几个几乎所有人都会用的基础插件：

#### which-key.nvim — 按键提示

如果你忘记了自己设置的按键映射，which-key 在你按下 leader 键后会弹出菜单：

```lua
{
    "folke/which-key.nvim",
    event = "VeryLazy",
    opts = {
        -- 默认配置通常就够用
    },
    config = function(_, opts)
        local wk = require("which-key")
        wk.setup(opts)

        -- 注册按键分组说明（可选，但推荐）
        wk.add({
            { "<leader>f", group = "文件查找" },
            { "<leader>g", group = "Git" },
            { "<leader>l", group = "LSP" },
            { "<leader>s", group = "搜索" },
            { "<leader>x", group = "诊断" },
        })
    end,
}
```

#### nvim-web-devicons — 文件图标

几乎所有 UI 插件都依赖它来显示文件类型图标：

```lua
{
    "nvim-tree/nvim-web-devicons",
    lazy = true,  -- 由其他插件触发加载
}
```

#### plenary.nvim — Lua 工具库

Telescope 等插件的依赖，提供文件操作、异步任务等工具：

```lua
{
    "nvim-lua/plenary.nvim",
    lazy = true,
    -- 不需要配置，只作为依赖被引用
}
```

### 常见编辑器增强插件

```lua
-- 注释插件：gc 注释/取消注释
{
    "numToStr/Comment.nvim",
    keys = { "gc", "gb" },  -- 按键触发
    opts = {},
}

-- 自动配对括号
{
    "windwp/nvim-autopairs",
    event = "InsertEnter",
    opts = {},
}

-- 缩进线
{
    "lukas-reineke/indent-blankline.nvim",
    event = "VeryLazy",
    opts = {
        char = "▏",
        show_trailing_blankline_indent = false,
    },
}

-- 更好的撤销
{
    "mbbill/undotree",
    cmd = "Undotree",
    keys = { { "<leader>u", "<cmd>UndotreeToggle<CR>", desc = "撤销树" } },
}
```

---

## 2. 代码示例

完整的 `lua/plugins/editor.lua`，包含常用编辑器增强：

```lua
-- lua/plugins/editor.lua
return {
    -- 注释
    {
        "numToStr/Comment.nvim",
        keys = {
            { "gc", mode = { "n", "v" }, desc = "注释切换" },
            { "gb", mode = { "n", "v" }, desc = "块注释切换" },
        },
        opts = {},
    },

    -- 自动配对
    {
        "windwp/nvim-autopairs",
        event = "InsertEnter",
        opts = {},
    },

    -- 缩进线
    {
        "lukas-reineke/indent-blankline.nvim",
        main = "ibl",  -- 指定入口模块（新版本改了入口）
        event = "VeryLazy",
        opts = {
            scope = { enabled = false },
        },
    },

    -- 撤销树
    {
        "mbbill/undotree",
        cmd = "Undotree",
        keys = { { "<leader>u", "<cmd>UndotreeToggle<CR>", desc = "撤销树" } },
    },

    -- 更好的终端切换
    {
        "akinsho/toggleterm.nvim",
        cmd = { "ToggleTerm", "TermExec" },
        keys = {
            { "<C-\\>", "<cmd>ToggleTerm<CR>", desc = "切换终端" },
        },
        opts = {
            size = 15,
            open_mapping = [[<C-\>]],
            direction = "horizontal",
        },
    },

    -- Git 符号（行号旁显示增删改标记）
    {
        "lewis6991/gitsigns.nvim",
        event = "VeryLazy",
        opts = {
            signs = {
                add = { text = "+" },
                change = { text = "~" },
                delete = { text = "_" },
            },
        },
    },
}
```

---

## 3. 练习

### 练习 1: 安装三个基础插件
安装 Comment.nvim、nvim-autopairs、gitsigns.nvim。验证：
- `gc` 在普通模式可以注释/取消注释当前行
- 输入 `(` 自动补全 `)`
- 打开一个 Git 仓库中的文件，行号旁显示 Git 标记

### 练习 2: 安装 which-key
安装 which-key.nvim 并配置分组。按下 `<leader>` 后等待，确认弹出菜单显示了你配置的分组。

### 练习 3: 探索插件文档（可选）
打开任意一个插件的 GitHub 仓库，阅读其 README 中的配置部分。将你看到的 `opts` 翻译成 lazy.nvim 的 spec 格式。对比官方示例和你写的是否一致。

---

## 4. 扩展阅读

- [awesome-neovim](https://github.com/rockerBOO/awesome-neovim) — Neovim 插件精选列表
- [Neovim 社区插件推荐（Reddit）](https://www.reddit.com/r/neovim/)
- [This Week in Neovim](https://this-week-in-neovim.org/) — 每周 Neovim 生态新闻

---

## 常见陷阱

- **`opts` vs `config` 不要混用**：`opts` 会自动调用 `require("plugin").setup(opts)`。如果你还写了 `config`，`config` 会替代默认行为——此时 `opts` 只作为 `config` 函数的第一个参数传入，你需要手动处理。如果你在 `config` 中又 `require().setup(opts)`，实际上等于用 `config` 包装了 `opts` 的功能——直接删掉 `config` 用纯 `opts` 即可。
- **`main` 字段用于入口模块非默认名称**：如果插件的入口不是 `lua/plugin-name/init.lua` 而是 `lua/ibl/init.lua`，需要 `main = "ibl"`。不正确的 `main` 导致 `:Lazy` 界面显示加载错误。
- **某个插件的 `setup()` 需要的参数是函数**：用 `opts` 时无法传递函数作为值。此时必须改用 `config` 回调。
- **依赖的插件也需要在 spec 中声明**：`dependencies` 列表中的插件也需要在 `lua/plugins/` 中某个文件里懒加载声明（即使 `lazy = true` 仅作依赖），否则 lazy.nvim 不会安装它们。
