# 14 — 综合实战：从零搭建完整配置

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 90 分钟
> 前置知识: 全部 1-13 节

---

## 1. 目标

在本节中，你将**从零开始**，不参考任何现有配置，搭建一套完整的 Neovim 配置。内容包括：

- 模块化的目录结构
- 基础选项、按键映射、自动命令
- lazy.nvim 插件管理（懒加载策略）
- LSP + 补全 + Treesitter 三件套
- Telescope 模糊查找
- 配色方案 + 状态栏 + 标签栏
- 常用编辑器增强（注释、自动配对、Git 标记）

> [!NOTE]
> 下面的完整代码**不是让你复制粘贴的**——是你需要逐模块写出来的目标参考。建议先尝试自己写，遇到困难再看参考。

---

## 2. 目录结构

```
~/.config/nvim/
├── init.lua
├── lua/
│   ├── config/
│   │   ├── options.lua
│   │   ├── keymaps.lua
│   │   ├── autocmds.lua
│   │   └── lazy.lua
│   └── plugins/
│       ├── ui.lua
│       ├── editor.lua
│       ├── lsp.lua
│       ├── cmp.lua
│       ├── treesitter.lua
│       └── telescope.lua
└── lazy-lock.json  (自动生成)
```

---

## 3. 参考实现

### init.lua

```lua
-- ~/.config/nvim/init.lua

vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- 诊断显示配置（虚拟文字和行号列标记）
vim.diagnostic.config({
    virtual_text = true,
    signs = true,
    underline = true,
    update_in_insert = false,
    severity_sort = true,
})

require("config.options").setup()
require("config.keymaps").setup()
require("config.autocmds").setup()
require("config.lazy").setup()
```

### lua/config/options.lua

```lua
local M = {}

function M.setup()
    -- 行号
    vim.opt.number = true
    vim.opt.relativenumber = true

    -- 缩进
    vim.opt.tabstop = 4
    vim.opt.softtabstop = 4
    vim.opt.shiftwidth = 4
    vim.opt.expandtab = true
    vim.opt.smartindent = true

    -- 搜索
    vim.opt.ignorecase = true
    vim.opt.smartcase = true
    vim.opt.hlsearch = false
    vim.opt.incsearch = true

    -- 界面
    vim.opt.termguicolors = true
    vim.opt.signcolumn = "yes"
    vim.opt.scrolloff = 8
    vim.opt.cursorline = true
    vim.opt.cmdheight = 1
    vim.opt.pumheight = 10    -- 补全菜单最大高度

    -- 剪贴板
    vim.opt.clipboard = "unnamedplus"

    -- 分割窗口
    vim.opt.splitright = true
    vim.opt.splitbelow = true

    -- 文件
    vim.opt.swapfile = false
    vim.opt.backup = false
    vim.opt.undodir = vim.fn.stdpath("data") .. "/undodir"
    vim.opt.undofile = true

    -- 性能
    vim.opt.updatetime = 50
    vim.opt.timeoutlen = 300

    -- 补全
    vim.opt.completeopt = { "menu", "menuone", "noselect" }
end

return M
```

### lua/config/keymaps.lua

```lua
local M = {}

function M.setup()
    local map = vim.keymap.set
    local opts = { noremap = true, silent = true }
    local function desc_opts(desc)
        return vim.tbl_extend("force", opts, { desc = desc })
    end

    -- 基础
    map("n", "<leader>w", "<cmd>write<CR>", desc_opts("保存"))
    map("n", "<leader>q", "<cmd>quit<CR>", desc_opts("退出"))
    map("n", "<Esc>", "<cmd>nohlsearch<CR>", opts)

    -- 窗口导航
    map("n", "<C-h>", "<C-w>h", desc_opts("左侧窗口"))
    map("n", "<C-j>", "<C-w>j", desc_opts("下方窗口"))
    map("n", "<C-k>", "<C-w>k", desc_opts("上方窗口"))
    map("n", "<C-l>", "<C-w>l", desc_opts("右侧窗口"))

    -- 缓冲区
    map("n", "<Tab>", "<cmd>bnext<CR>", desc_opts("下一缓冲区"))
    map("n", "<S-Tab>", "<cmd>bprevious<CR>", desc_opts("上一缓冲区"))
    map("n", "<leader>bd", "<cmd>bdelete<CR>", desc_opts("关闭缓冲区"))

    -- 终端
    map("t", "<Esc>", "<C-\\><C-n>", desc_opts("退出终端模式"))

    -- 可视模式缩进保留选择
    map("v", "<", "<gv", opts)
    map("v", ">", ">gv", opts)

    -- 移动选中行
    map("v", "J", ":m '>+1<CR>gv=gv", opts)
    map("v", "K", ":m '<-2<CR>gv=gv", opts)
end

return M
```

### lua/config/autocmds.lua

```lua
local M = {}

function M.setup()
    local augroup = vim.api.nvim_create_augroup
    local autocmd = vim.api.nvim_create_autocmd

    local general = augroup("UserGeneral", { clear = true })

    -- 保存时删除行尾空格
    autocmd("BufWritePre", {
        group = general,
        pattern = "*",
        callback = function()
            local pos = vim.fn.getpos(".")
            vim.cmd([[%s/\s\+$//e]])
            vim.fn.setpos(".", pos)
        end,
    })

    -- 复制高亮
    autocmd("TextYankPost", {
        group = general,
        callback = function()
            vim.highlight.on_yank({ higroup = "IncSearch", timeout = 150 })
        end,
    })

    -- 文件类型特定缩进
    local ft = augroup("UserFileType", { clear = true })

    autocmd("FileType", {
        group = ft,
        pattern = { "lua", "json", "yaml", "yml" },
        callback = function()
            vim.opt_local.tabstop = 2
            vim.opt_local.shiftwidth = 2
        end,
    })

    autocmd("FileType", {
        group = ft,
        pattern = "make",
        callback = function()
            vim.opt_local.expandtab = false
        end,
    })
end

return M
```

### lua/config/lazy.lua

```lua
local M = {}

function M.setup()
    local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"

    if not vim.loop.fs_stat(lazypath) then
        vim.fn.system({
            "git", "clone", "--filter=blob:none",
            "https://github.com/folke/lazy.nvim.git",
            "--branch=stable", lazypath,
        })
    end
    vim.opt.rtp:prepend(lazypath)

    require("lazy").setup({
        { import = "plugins" },
    }, {
        defaults = { lazy = true },
        checker = { enabled = true, notify = false },
        change_detection = { notify = false },
        performance = {
            rtp = {
                disabled_plugins = {
                    "gzip", "matchit", "matchparen",
                    "netrw", "tar", "tarPlugin",
                    "tohtml", "tutor", "zipPlugin",
                },
            },
        },
    })
end

return M
```

---

## 4. 操作步骤

### 第一步：备份现有配置

```bash
mv ~/.config/nvim ~/.config/nvim.bak
# Windows: move %LOCALAPPDATA%\nvim %LOCALAPPDATA%\nvim.bak
```

### 第二步：创建 init.lua

创建 `~/.config/nvim/init.lua`，写入上面参考实现的入口代码。

### 第三步：逐模块创建

按以下顺序创建并验证每一个文件：
1. `lua/config/options.lua` → 启动 Neovim，`:set number?` 验证
2. `lua/config/keymaps.lua` → 按 `<leader>w` 验证保存映射
3. `lua/config/autocmds.lua` → 打开文件后复制，验证高亮闪烁
4. `lua/config/lazy.lua` → 启动后 `:Lazy` 验证界面
5. `lua/plugins/ui.lua` → 启动看到配色和状态栏
6. `lua/plugins/telescope.lua` → `<leader>ff` 查找文件
7. `lua/plugins/treesitter.lua` → 打开 Lua 文件看语法高亮
8. `lua/plugins/lsp.lua` → `:LspInfo` 验证 LSP 附着
9. `lua/plugins/cmp.lua` → 输入 `vim.` 验证补全弹出
10. `lua/plugins/editor.lua` → 按 `gc` 验证注释功能

### 第四步：个性化

根据你的语言和习惯调整：
- `ensure_installed` （Treesitter 解析器）
- `ensure_installed` （LSP 服务器）
- `keymaps` （自定义映射）

### 第五步：检查健康

```vim
:checkhealth
:Lazy health
:LspInfo
:TSInstallInfo
```

---

## 5. 验证清单

完成后逐项检查：

- [ ] Neovim 启动无错误信息
- [ ] colorscheme 正确显示
- [ ] 行号显示（绝对 + 相对）
- [ ] `<leader>ff` 能打开文件查找
- [ ] `<leader>fg` 能实时搜索文本
- [ ] 打开 `.lua` 文件时 LSP 自动附着（`:LspInfo` 确认）
- [ ] 输入代码时补全菜单弹出
- [ ] `gd` 跳转到定义
- [ ] `K` 显示悬停文档
- [ ] 语法高亮正确且丰富
- [ ] `gc` 注释/取消注释
- [ ] 输入 `(` 自动补全 `)`
- [ ] `<C-h/j/k/l>` 在窗口间跳转
- [ ] `<Tab>` / `<S-Tab>` 切换缓冲区
- [ ] `:Lazy` 界面正常，无错误插件
- [ ] `:checkhealth` 无严重问题

---

## 6. 后续扩展方向

基础配置完成后，你可以按需扩展：

| 需求 | 插件 |
|------|------|
| 文件树 | `nvim-neo-tree/neo-tree.nvim` |
| Git 集成 | `NeogitOrg/neogit` 或 `sindrets/diffview.nvim` |
| 调试 | `mfussenegger/nvim-dap` + `rcarriga/nvim-dap-ui` |
| Markdown 预览 | `iamcco/markdown-preview.nvim` |
| 代码运行 | `milanglacier/minuet-ai.nvim` 或 `CRAG666/code_runner.nvim` |
| AI 补齐 | `github/copilot.vim` 或 `yetone/avante.nvim` |
| 会话管理 | `rmagatti/auto-session` |
| 书签 | `tomasky/bookmarks.nvim` |
| 彩虹括号 | `HiPhish/rainbow-delimiters.nvim` |
| 通知美化 | `rcarriga/nvim-notify` |

---

## 7. 扩展阅读

- [kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim) — 单文件的最小配置，代码中有详尽注释
- [LazyVim](https://github.com/LazyVim/LazyVim) — 学习模块化配置的最佳参考
- [Neovim 从零到一的视频教程（ThePrimeagen）](https://www.youtube.com/watch?v=w7i4amO_zaE)

---

## 常见陷阱

- **文件结构不对**：`require("config.options")` 查找的是 `lua/config/options.lua`。文件名和路径必须精确匹配。
- **模块文件忘记 `return M`**：没有返回值的 `require` 不会报错但返回 `nil`，后续调用 `setup()` 会报 nil 错误。
- **init.lua 和 init.vim 同时存在**：Neovim 只加载 `init.lua`。备份时把 `init.vim` 移走或重命名。
- **重装插件时先清缓存**：`rm -rf ~/.local/share/nvim/lazy/` 然后重启。`:Lazy sync` 会重新下载所有插件。
- **lazy-lock.json 的版本锁定**：如果某插件更新后出问题，回退 `lazy-lock.json` 到之前的版本然后 `:Lazy restore`。
- **首次启动需要网络和编译**：Treesitter 解析器和部分插件的 `build` 步骤需要网络 + C 编译器。耐心等待，不要中断。
