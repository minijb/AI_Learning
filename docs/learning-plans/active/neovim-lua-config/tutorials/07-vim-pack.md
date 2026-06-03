# 07 — vim.pack 插件管理（内置）

> 所属计划: Neovim + Lua 配置实战 (现代版)
> 预计耗时: 50 分钟
> 前置知识: 04-init-lua-structure（模块化配置结构）
> Neovim 版本: **0.12+**

---

## 1. 概念讲解

### 为什么用 vim.pack？

Neovim 0.12 引入了内置的插件管理器 `vim.pack`。与第三方插件管理器（lazy.nvim、packer.nvim 等）相比：

| 特性 | vim.pack (0.12) | lazy.nvim (旧) |
|------|----------------|---------------|
| 安装方式 | 内置，无需自举 | 需要自举脚本安装自身 |
| API | `vim.pack.add()` | `require("lazy").setup()` |
| 更新 | `vim.pack.update()` | `:Lazy sync` |
| 锁文件 | `nvim-pack-lock.json` (JSON) | `lazy-lock.json` (Lua) |
| 懒加载 | 延迟调用 `vim.pack.add()` | `lazy = true` + 触发器字段 |
| 插件存放 | `data/site/pack/core/opt/` | `data/lazy/` |
| build 钩子 | `PackChanged` 自动命令 | `build` 字段 |

**核心设计理念**：`vim.pack.add()` 是一个普通 Lua 函数——调用即安装+加载。没有声明式的 spec、没有隐式的 magical loading。

### vim.pack 核心概念

#### 安装: vim.pack.add()

```lua
-- 最简单的用法：传入 GitHub URL
vim.pack.add { 'https://github.com/nvim-mini/mini.nvim' }

-- 多个插件一起添加
vim.pack.add {
  'https://github.com/nvim-mini/mini.nvim',
  'https://github.com/neovim/nvim-lspconfig',
  'https://github.com/nvim-treesitter/nvim-treesitter',
}

-- GitHub 简写辅助函数（kickstart 风格）
local function gh(repo) return 'https://github.com/' .. repo end
vim.pack.add { gh 'nvim-mini/mini.nvim' }
```

#### 插件规格 (Spec)

除字符串外，可以用 table 指定更多选项：

```lua
vim.pack.add {
  -- 基本形式
  gh 'nvim-mini/mini.nvim',

  -- 指定版本（跟踪 semver tag）
  { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' },

  -- 自定义名称
  { src = gh 'neovim/nvim-lspconfig', name = 'lspconfig' },

  -- 自定义数据（可存储任意信息）
  { src = gh 'folke/tokyonight.nvim', data = { priority = 1000 } },
}
```

#### 更新: vim.pack.update()

```lua
-- 查看待更新状态（只读模式）
:lua vim.pack.update(nil, { offline = true })

-- 更新所有插件（打开交互式 diff 窗口）
:lua vim.pack.update()
```

在更新窗口：`:write` 应用更新，`:quit` 取消。

#### 锁文件: nvim-pack-lock.json

`vim.pack` 在配置目录自动生成 `nvim-pack-lock.json`，记录每个插件的当前 commit 和版本信息。**应该提交到版本控制**，这样在其他机器上 `vim.pack.add()` 会自动恢复到锁定版本。

### 懒加载

`vim.pack` 没有 `lazy = true` 这样的声明式懒加载。懒加载的本质是：**"晚一点调用 `vim.pack.add()`"**。

```lua
-- 启动时加载（"不懒"）
vim.pack.add { gh 'folke/tokyonight.nvim' }

-- 懒加载：在特定事件触发时才调用 add
vim.api.nvim_create_autocmd('User', {
  pattern = 'VeryLazy',
  callback = function()
    vim.pack.add { gh 'folke/which-key.nvim' }
    require('which-key').setup {}
  end,
})
```

**kickstart.nvim 的做法**：利用 Lua 的执行顺序就是加载顺序——先执行前面的 `do ... end` 块（立即加载的插件），后面的块中的 `vim.pack.add()` 会在 Neovim 初始化过程中自然晚执行。本质上就是一个大的 `init.lua` 文件，代码从上到下执行。

### 插件存放位置

```
~/.local/share/nvim/site/pack/core/opt/
├── mini.nvim/
├── nvim-lspconfig/
├── blink.cmp/
└── ...
```

所有通过 `vim.pack.add()` 安装的插件统一放在 `core` package 的 `opt` 目录下。`vim.pack.add()` 内部调用 `:packadd` 来加载它们。

---

## 2. 代码示例

### 步骤 1: 创建 GitHub URL 辅助函数

```lua
-- init.lua 顶部
local function gh(repo)
  return 'https://github.com/' .. repo
end
```

### 步骤 2: 添加第一个插件

```lua
-- 在 init.lua 的某个 do 块中
do
  vim.pack.add { gh 'NMAC427/guess-indent.nvim' }
  require('guess-indent').setup {}
end
```

### 步骤 3: 查看插件状态

```vim
" 命令行中运行：
:lua vim.pack.update(nil, { offline = true })
```

这会打开一个类似 `:Lazy` 的界面，显示所有插件的当前状态和可用更新。

### 步骤 4: 更新插件

```vim
:lua vim.pack.update()
" 在 diff 窗口中：
" :write → 应用更新
" :quit  → 取消
```

### 完整骨架（kickstart 风格）

```lua
-- ~/.config/nvim/init.lua

-- Section 1: Foundation (settings, keymaps, autocmds)
do
  vim.g.mapleader = ' '
  vim.g.maplocalleader = ' '
  vim.o.number = true
  -- ...
end

local function gh(repo) return 'https://github.com/' .. repo end

-- Section 2: Core UI plugins (立即加载)
do
  vim.pack.add { gh 'folke/tokyonight.nvim' }
  require('tokyonight').setup { style = 'night' }
  vim.cmd.colorscheme 'tokyonight-night'
end

-- Section 3: Navigation plugins
do
  vim.pack.add { gh 'nvim-telescope/telescope.nvim', gh 'nvim-lua/plenary.nvim' }
  -- ... setup ...
end

-- Section 4: LSP (更晚加载也没问题)
do
  vim.pack.add { gh 'neovim/nvim-lspconfig' }
  -- ... configure ...
end
```

**运行方式:**
1. 将上述代码写入 `~/.config/nvim/init.lua`
2. 启动 Neovim（首次启动会自动下载插件，会有确认对话框，按 `a` 全允许）
3. 等待安装完成，观察 colorscheme 是否生效

---

## 3. 练习

### 练习 1: 首次体验 vim.pack

备份现有配置，创建一个最小 `init.lua`：

```lua
vim.g.mapleader = ' '
local function gh(r) return 'https://github.com/' .. r end
vim.pack.add { gh 'folke/tokyonight.nvim' }
require('tokyonight').setup { style = 'night' }
vim.cmd.colorscheme 'tokyonight-night'
```

启动 Neovim，观察自动安装流程。安装完成后查看 `nvim-pack-lock.json` 的内容。

### 练习 2: 查看插件状态

运行 `:lua vim.pack.update(nil, { offline = true })`，理解显示的界面：
- 左侧列表：插件名和状态
- 右侧 diff：当前 vs 待更新的 commit 差异

### 练习 3: 模拟多机同步

1. 找到自动生成的 `nvim-pack-lock.json`
2. 将插件目录删除（模拟新机器）: 删除 `~/.local/share/nvim/site/pack/core/`
3. 重新启动 Neovim —— 观察 `vim.pack.add()` 如何根据 lockfile 自动恢复到锁定版本

---

## 4. 扩展阅读

- [`:help vim.pack`](https://neovim.io/doc/user/helptag.html?tag=vim.pack) — 官方文档
- [A Guide to vim.pack](https://echasnovski.com/blog/2026-03-13-a-guide-to-vim-pack) — **必读**，`vim.pack` 作者撰写的最完整指南
- [`:help vim.pack-examples`](https://neovim.io/doc/user/helptag.html?tag=vim.pack-examples) — 常见工作流示例
- [kickstart.nvim init.lua](https://github.com/nvim-lua/kickstart.nvim/blob/master/init.lua) — 完整参考实现

---

## 常见陷阱

- **首次安装需要确认**：`vim.pack.add()` 默认弹出确认对话框。按 `a` 允许本次会话中所有后续安装。这是安全机制——防止恶意配置静默安装未知插件。
- **插件路径不同于 lazy.nvim**：旧配置中的硬编码路径（如 `data/lazy/...`）不再有效。使用 `vim.fn.stdpath('data') .. '/site/pack/core/opt'` 查找插件。
- **lockfile 应该提交到版本控制**：`nvim-pack-lock.json` 确保所有机器的插件版本一致。不要把它加入 `.gitignore`。
- **更新后可能需要重启**：`vim.pack.update()` 应用更新后，已加载的插件不会自动重载。重启 Neovim 来使用新版本。
- **`:packadd` vs `vim.pack.add()`**：`vim.pack.add()` 内部会调用 `:packadd`。不要混用——插件要么用 `vim.pack.add()` 管理，要么手动用 `:packadd`，不要同时用两种方式管理同一个插件。
- **build 步骤需要 `PackChanged` 自动命令**：不像 lazy.nvim 有 `build` 字段，vim.pack 通过 `PackChanged` 事件来执行安装后/更新后的构建步骤。见第 08 节的详细说明。
