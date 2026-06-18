---
title: "07 — vim.pack 插件管理（内置）"
updated: 2026-06-18
---

# 07 — vim.pack 插件管理（内置）

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 55 分钟
> 前置知识: [[04-init-lua-structure]]（模块化配置结构）
> Neovim 版本: **0.12.3+**

---

## 1. 概念讲解

### 1.1 为什么用 vim.pack？

Neovim 0.12 内置了插件管理器 `vim.pack`。与第三方插件管理器（lazy.nvim、mini.deps、packer.nvim 等）相比，它的最大特点是：**没有自举负担、没有声明式 DSL、没有隐式魔法**。

| 特性 | vim.pack (0.12.3+) | lazy.nvim（旧时代） |
|------|-------------------|-------------------|
| 安装方式 | 内置，无需自举 | 需要自举脚本安装自身 |
| API | `vim.pack.add()` | `require("lazy").setup()` |
| 更新 | `vim.pack.update()` | `:Lazy sync` |
| 锁文件 | `nvim-pack-lock.json`（config 目录） | `lazy-lock.json`（plugin 目录） |
| 懒加载 | 延迟调用 `vim.pack.add()` | `lazy = true` + 触发器字段 |
| 插件存放 | `data/site/pack/core/opt/` | `data/lazy/` |
| build 钩子 | `PackChanged` 自动命令 | `build` 字段 |
| 条件安装 | 原生 `if ... then` | `cond` 字段 |

> [!IMPORTANT]
> vim.pack 不是 lazy.nvim 的替代品，而是**官方内置的替代选择**。如果你喜欢声明式 spec 和大量自动化，lazy.nvim 仍然是好选择；如果你希望配置从上到下、一行一行都可见，`vim.pack` 更合适。

### 1.2 核心设计理念：调用即加载

```lua
vim.pack.add { 'https://github.com/nvim-mini/mini.nvim' }
```

这行代码执行时，会做三件事：

1. **检查** `nvim-pack-lock.json` 中是否有该插件的锁定记录
2. **克隆/拉取** 到 `site/pack/core/opt/mini.nvim`（首次安装会弹出确认对话框）
3. **立即加载** 该插件（内部调用 `:packadd`）

> [!NOTE]
> 没有 `lazy = true`、没有 `event = "VeryLazy"`、没有 `config = function()`。这些都需要你自己用 Lua 控制流实现。

### 1.3 安装位置

所有通过 `vim.pack.add()` 安装的插件统一放在 **data 标准路径** 的 `site/pack/core/opt/` 下：

- Linux/macOS: `~/.local/share/nvim/site/pack/core/opt/`
- Windows: `%LOCALAPPDATA%\nvim-data\site\pack\core\opt/`

```text
site/pack/core/opt/
├── mini.nvim/
├── nvim-lspconfig/
├── blink.cmp/
└── ...
```

- `core` 是 package 名称，vim.pack 固定使用这个名字
- `opt` 表示这些是"可选"插件，需要 `:packadd` 才会加载
- vim.pack 在 `add()` 内部替你完成 `:packadd`
- **没有 "start" 插件概念**——这是设计决策：想禁用插件，直接注释掉 `vim.pack.add()` 中的条目即可

### 1.4 Spec 字段完整说明

`vim.pack.add()` 接受一个插件 spec 列表。每个 spec 可以是字符串 URL，也可以是 table：

```lua
vim.pack.add {
  -- 字符串形式：只指定 src
  'https://github.com/nvim-mini/mini.nvim',

  -- table 形式：完整控制
  {
    src = 'https://github.com/saghen/blink.cmp',
    version = vim.version.range '1.*',
    name = 'blink-cmp',
    data = { priority = 100 },
  },
}
```

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `src` | 是 | string | 完整 Git URL，目前仅支持 Git |
| `version` | 否 | string / `vim.VersionRange` | `'stable'`、分支名、`'main'`、`vim.version.range('*')`、`vim.version.range('2.x')` |
| `name` | 否 | string | 自定义插件目录名，默认为仓库名（如 `blink.cmp`） |
| `data` | 否 | any | 任意用户数据，可在 `PackChanged` hook 中通过 `ev.data.spec.data` 读取 |

#### version 字段详解

```lua
-- 跟踪 stable 引用（分支/tag/commit 均可）
vim.pack.add { { src = gh 'nvim-mini/mini.nvim', version = 'stable' } }

-- 跟踪 main 分支
vim.pack.add { { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' } }

-- 跟踪最新 semver tag（任意主版本）
vim.pack.add { { src = gh 'saghen/blink.cmp', version = vim.version.range '*' } }

-- 锁定到 1.x 语义版本（>=1.0.0 <2.0.0）
vim.pack.add { { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' } }

-- 锁定到 2.x
vim.pack.add { { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' } }
```

> [!TIP]
> 生产配置建议对关键插件使用 `vim.version.range '1.*'` 这类 semver 约束。不指定 version 时，`vim.pack.update()` 会拉取默认分支的最新 commit，可能引入破坏性变更。

### 1.5 第二参数 `opts.load`

```lua
vim.pack.add(
  { 'https://github.com/folke/which-key.nvim' },
  { load = function() end }
)
```

`opts.load` 用于**自定义加载逻辑**。最常见的用法是返回一个空函数，实现"只注册不加载"——这在复杂的懒加载场景中很有用。

```lua
-- 注册插件，但暂时不 packadd
vim.pack.add(
  { gh 'folke/which-key.nvim' },
  {
    load = function()
      -- 返回空函数 = 本次不加载
      return function() end
    end,
  }
)
```

> [!NOTE]
> 对初学者来说，第二参数不是必需品。掌握了事件触发懒加载后，再回来理解它会更容易。

### 1.6 更新: vim.pack.update()

```lua
-- 更新所有插件，打开确认 buffer
:lua vim.pack.update()

-- 只更新指定插件
:lua vim.pack.update({ 'mini.nvim' })

-- 立即应用，跳过确认（脚本用）
:lua vim.pack.update(nil, { force = true })

-- 只读查看状态，不下载
:lua vim.pack.update(nil, { offline = true })

-- 同步到 lockfile 状态（回滚用）
:lua vim.pack.update(nil, { target = 'lockfile' })
```

**确认 buffer 特性**（旧教程称为"diff 窗口"不准确）：

- `:write` 应用更新；`:quit` 取消
- `]]` / `[[` 在插件段间跳转
- 内置 in-process LSP server，支持 hover、codeAction、documentSymbol
- 更新日志写入 `nvim-pack.log`（log 标准路径下）

> [!IMPORTANT]
> 旧教程说 `vim.pack.update()` 打开"diff 窗口"，这是**不准确的**。正确描述是：它打开一个**确认 buffer**，提供 LSP-powered 交互。你可以在 buffer 中查看变更、跳转、执行 code action，然后用 `:write`/`:quit` 决定应用或取消。

### 1.7 锁文件: nvim-pack-lock.json

- **文件名**: `nvim-pack-lock.json`
- **位置**: **用户配置目录** `$XDG_CONFIG_HOME/nvim/nvim-pack-lock.json`
  - Linux/macOS: `~/.config/nvim/nvim-pack-lock.json`
  - Windows: `%LOCALAPPDATA%\nvim\nvim-pack-lock.json`
- **不能手动编辑**。损坏时 `vim.pack` 会自动修复
- **应纳入版本控制**——它是配置的一部分，保证多机可重现
- 首次 `vim.pack.add()` 调用时，根据 lockfile 一次性安装所有缺失插件到锁定 commit

> [!WARNING]
> **这是必须纠正的错误**：旧教程说 lockfile 在 data 目录或含糊描述。正确位置是 **config 目录**（`stdpath('config')`），不是 data 目录。

示例 lockfile 内容：

```json
{
  "tokyonight.nvim": {
    "type": "git",
    "url": "https://github.com/folke/tokyonight.nvim",
    "commit": "a1b2c3d4e5f6...",
    "version": null
  },
  "blink.cmp": {
    "type": "git",
    "url": "https://github.com/saghen/blink.cmp",
    "commit": "b2c3d4e5f6a7...",
    "version": "^1.0.0"
  }
}
```

### 1.8 删除插件: vim.pack.del()

```lua
:lua vim.pack.del({ 'nvim-lspconfig', 'nvim-treesitter' })
```

- 删除插件**必须**用 `vim.pack.del()`，**不能手动删目录**
- 手动删目录会导致 lockfile 与磁盘状态不一致，下次启动会重新安装
- 删除前**必须**先从配置中移除对应的 `vim.pack.add()` 条目

正确删除流程：

1. 从 `init.lua` 中删除该插件的 `vim.pack.add()` 和配置代码
2. 保存并重启 Neovim（或 `:source`）
3. 运行 `:lua vim.pack.del({ 'plugin-name' })`
4. 运行 `:checkhealth vim.pack` 确认没有"未激活插件"警告

### 1.9 三种配置组织方式

echasnovski（vim.pack 作者）官方推荐的三种组织方式：

#### 方式 1: 单一 `vim.pack.add()`（最稳健，推荐入门）

```lua
-- ~/.config/nvim/init.lua

-- 所有 PackChanged hook 放在最前面
vim.api.nvim_create_autocmd('PackChanged', {
  callback = function(ev)
    -- 见 08 节的完整 run_build 范式
  end,
})

-- 一个 add() 列出所有插件
vim.pack.add {
  gh 'folke/tokyonight.nvim',
  gh 'nvim-mini/mini.nvim',
  gh 'neovim/nvim-lspconfig',
  { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' },
}

-- 立即配置
require('tokyonight').setup {}
vim.cmd.colorscheme 'tokyonight-night'
require('mini.ai').setup {}
```

优点：
- 安装/更新是原子性的，lockfile 一次写入
- 依赖顺序清晰（列表顺序 = 加载顺序）
- 最容易调试

#### 方式 2: 多个 `vim.pack.add()`（模块化）

```lua
-- ~/.config/nvim/init.lua
vim.api.nvim_create_autocmd('PackChanged', { callback = run_build_handler })

require 'plugins.ui'
require 'plugins.lsp'
require 'plugins.cmp'
```

```lua
-- ~/.config/nvim/lua/plugins/ui.lua
vim.pack.add {
  gh 'folke/tokyonight.nvim',
  gh 'nvim-mini/mini.nvim',
}
require('tokyonight').setup {}
require('mini.ai').setup {}
```

```lua
-- ~/.config/nvim/lua/plugins/lsp.lua
vim.pack.add {
  gh 'neovim/nvim-lspconfig',
  gh 'mason-org/mason.nvim',
}
require('mason').setup {}
```

```lua
-- ~/.config/nvim/lua/plugins/cmp.lua
vim.pack.add {
  { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' },
  { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' },
}
require('blink.cmp').setup {}
```

> [!NOTE]
> 使用 `plugin/*.lua` 自动 source 机制时，注意 install hook 仍应集中在 `init.lua` 顶部，否则首次安装 lockfile bootstrap 期间可能错过某些插件的 `install` 事件。

#### 方式 3: 懒加载（按需）

```lua
-- 启动后异步加载
vim.schedule(function()
  vim.pack.add { gh 'folke/which-key.nvim' }
  require('which-key').setup {}
end)

-- 事件触发加载（只触发一次）
vim.api.nvim_create_autocmd('InsertEnter', {
  once = true,
  callback = function()
    vim.pack.add { gh 'L3MON4D3/LuaSnip' }
    require('luasnip').setup {}
  end,
})
```

> [!TIP]
> 三种方式不是互斥的。推荐入门用方式 1；配置变长后迁移到方式 2；对真正重的插件再用方式 3 懒加载。

### 1.10 健康检查 `:checkhealth vim.pack`

```vim
:checkhealth vim.pack
```

报告内容：

- lockfile 缺失/损坏
- lockfile 与磁盘状态不一致
- 未激活插件（已安装但未加载，常为已从配置移除但未 `vim.pack.del`）

> [!TIP]
> 遇到"lockfile 与磁盘不一致"警告时，优先检查是否手动删过插件目录。修复方法是：先把相关 `vim.pack.add()` 条目从配置移除，重启，再 `vim.pack.del()`，最后让 vim.pack 重建 lockfile。

### 1.11 从 lazy.nvim / mini.deps 迁移

| lazy.nvim / mini.deps 概念 | vim.pack 等价 |
|---------------------------|--------------|
| `source` / `name` | `src`（完整 URL） |
| `checkout` / `version` | `version`（字符串或 `vim.version.range`） |
| `opts = {}` | 手动调用 `require('plugin').setup {}` |
| `config = function() ... end` | 直接在 `add()` 后写配置代码 |
| `build = "make"` | `PackChanged` + `run_build()`（见 [[08-modern-plugin-patterns]]） |
| `event = "VeryLazy"` | `vim.schedule()` 或自定义 `User` autocmd |
| `keys = {...}` | 用 which-key 或 `vim.keymap.set` 自己定义 |
| `dependencies = {}` | 在 `add()` 列表中前置依赖 |
| `cond` | 原生 `if ... then ... end` |

> [!IMPORTANT]
> **哲学差异**：lazy.nvim 是**声明式**的——你写 spec，lazy 决定何时/如何执行；vim.pack 是**命令式**的——你写 Lua 代码，`vim.pack.add()` 就是普通函数调用，执行顺序完全由你控制。

---

## 2. 代码示例

### 2.1 最小可运行配置

```lua
-- ~/.config/nvim/init.lua
-- Neovim 0.12.3+

vim.loader.enable()
vim.g.mapleader = ' '

local function gh(repo)
  return 'https://github.com/' .. repo
end

vim.pack.add { gh 'folke/tokyonight.nvim' }
require('tokyonight').setup { style = 'night' }
vim.cmd.colorscheme 'tokyonight-night'
```

**运行方式：**
1. 备份现有配置：`mv ~/.config/nvim ~/.config/nvim.bak`
2. 将上述代码写入 `~/.config/nvim/init.lua`
3. 启动 Neovim
4. 首次安装会弹出确认对话框，按 `a` 允许本次会话所有安装
5. 观察 colorscheme 是否生效

### 2.2 带版本锁定和自定义 name/data 的完整骨架

```lua
-- ~/.config/nvim/init.lua
-- Neovim 0.12.3+

vim.loader.enable()
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '

local function gh(repo)
  return 'https://github.com/' .. repo
end

-- ============================================================
-- Foundation
-- ============================================================
do
  vim.o.number = true
  vim.o.relativenumber = true
  vim.o.expandtab = true
  vim.o.shiftwidth = 2
  vim.o.tabstop = 2
end

-- ============================================================
-- Plugins
-- ============================================================
vim.pack.add {
  -- colorscheme：立即加载
  gh 'folke/tokyonight.nvim',

  -- 工具库： Telescope 的依赖
  gh 'nvim-lua/plenary.nvim',

  -- 模糊查找
  { src = gh 'nvim-telescope/telescope.nvim', version = vim.version.range '0.*' },

  -- LSP 配置
  { src = gh 'neovim/nvim-lspconfig', name = 'lspconfig' },

  -- 补全引擎，锁定 1.x
  { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*', data = { priority = 100 } },
}

-- ============================================================
-- Plugin Configuration
-- ============================================================
do
  require('tokyonight').setup { style = 'night' }
  vim.cmd.colorscheme 'tokyonight-night'
end

do
  require('telescope').setup {}
  vim.keymap.set('n', '<leader>ff', function()
    require('telescope.builtin').find_files {}
  end, { desc = '[F]ind [F]iles' })
end

do
  require('lspconfig').lua_ls.setup {}
end

do
  require('blink.cmp').setup {
    keymap = { preset = 'default' },
    sources = { default = { 'lsp', 'path', 'snippets' } },
  }
end
```

### 2.3 查看状态与更新

```vim
" 只读查看当前插件状态
:lua vim.pack.update(nil, { offline = true })

" 拉取远程并打开确认 buffer
:lua vim.pack.update()

" 在确认 buffer 中
" :write  → 应用更新
" :quit   → 取消
" ]] / [[ → 在插件段间跳转
" K       → hover 查看提交信息
```

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

启动 Neovim，观察自动安装流程。安装完成后查看 `nvim-pack-lock.json` 的内容，确认它的位置和文件名。

### 练习 2: 查看插件状态

运行 `:lua vim.pack.update(nil, { offline = true })`，理解确认 buffer 的界面：
- 左侧列表：插件名和状态
- 右侧：选中插件的变更信息
- 尝试用 `]]` / `[[` 跳转

### 练习 3: 模拟多机同步

1. 找到 `nvim-pack-lock.json`（注意是 config 目录，不是 data 目录）
2. 将插件目录删除（模拟新机器）: 删除 `~/.local/share/nvim/site/pack/core/`
3. 重新启动 Neovim —— 观察 `vim.pack.add()` 如何根据 lockfile 自动恢复到锁定版本
4. 检查 lockfile 是否仍然位于 config 目录且文件名正确

### 练习 4: 删除插件的正确流程

1. 从 `init.lua` 中移除 `tokyonight.nvim` 的 `vim.pack.add()` 和配置
2. 保存配置并重启 Neovim
3. 运行 `:lua vim.pack.del({ 'tokyonight.nvim' })`
4. 运行 `:checkhealth vim.pack` 确认没有残留警告
5. **错误示范**：尝试手动删除 `~/.local/share/nvim/site/pack/core/opt/tokyonight.nvim/`，观察下次启动时会发生什么

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **操作步骤与预期结果：**
>
> 1. **备份现有配置：**
>    ```bash
>    # Linux/macOS
>    mv ~/.config/nvim ~/.config/nvim.bak
>    # Windows (PowerShell)
>    Rename-Item $env:LOCALAPPDATA\nvim $env:LOCALAPPDATA\nvim.bak
>    ```
>
> 2. **创建最小 init.lua：**
>    ```lua
>    -- ~/.config/nvim/init.lua (Windows: %LOCALAPPDATA%/nvim/init.lua)
>    vim.g.mapleader = ' '
>    local function gh(r) return 'https://github.com/' .. r end
>    vim.pack.add { gh 'folke/tokyonight.nvim' }
>    require('tokyonight').setup { style = 'night' }
>    vim.cmd.colorscheme 'tokyonight-night'
>    ```
>
> 3. **启动 Neovim：** 首次启动会弹出确认对话框，按 `a` 允许安装。观察底部状态栏的下载进度。
>
> 4. **查看 lockfile：** 安装完成后，在 `~/.config/nvim/nvim-pack-lock.json`（Windows: `%LOCALAPPDATA%/nvim/nvim-pack-lock.json`）中可以看到类似内容：
>    ```json
>    {
>      "tokyonight.nvim": {
>        "type": "git",
>        "url": "https://github.com/folke/tokyonight.nvim",
>        "commit": "abc123...",
>        "version": null
>      }
>    }
>    ```
>
> **关键理解：**
> - lockfile 在 **config 目录**，不是 data 目录。
> - 文件名必须是 `nvim-pack-lock.json`。
> - 这个 JSON 文件记录了插件的精确 commit，确保在任何机器上重装都能得到完全相同的代码版本。

> [!tip]- 练习 2 参考答案
> 运行 `:lua vim.pack.update(nil, { offline = true })` 后会打开一个确认 buffer：
>
> | 区域 | 内容 |
> |---|---|
> | 左侧列表 | 每个插件的名称和状态：`ok`（已是最新）、`behind`（远程有更新）、`new`（未锁定） |
> | 右侧详情 | 选中插件的变更信息，可用 `K` hover |
>
> `offline = true` 表示**只读模式**——只检查本地状态而不拉取远程。这让你在离线时也能查看插件信息。去掉 `offline = true` 才会真正拉取远程仓库并显示可更新的变更。
>
> **操作提示：** 在确认 buffer 中使用 `j`/`k` 上下移动；按 `<Enter>` 展开某个插件的详情；`:write` 应用所有更新；`:quit` 退出。

> [!tip]- 练习 3 参考答案
> **模拟多机同步步骤：**
>
> 1. **定位 lockfile：** `~/.config/nvim/nvim-pack-lock.json`（Windows: `%LOCALAPPDATA%/nvim/nvim-pack-lock.json`）。
>
> 2. **删除插件目录（模拟新机器）：**
>    ```bash
>    # Linux/macOS
>    rm -rf ~/.local/share/nvim/site/pack/core/
>    # Windows (PowerShell)
>    Remove-Item -Recurse -Force $env:LOCALAPPDATA\nvim-data\site\pack\core\
>    ```
>
> 3. **重启 Neovim：** `vim.pack.add()` 检测到 `opt/` 下没有对应插件，但 `nvim-pack-lock.json` 中有锁定记录，因此会**自动 clone 到锁定版本**——不会弹出更新确认，因为安装的是已锁定的 commit 而非最新版。
>
> **核心机制：**
> ```
> init.lua 中的 vim.pack.add()
>          ↓
> 读取 nvim-pack-lock.json（config 目录）
>          ↓
> clone 到 data/site/pack/core/opt/<name>/
>          ↓
> 自动 checkout 到 lockfile 记录的 commit
> ```
> 这就是 lockfile 的价值：**可重现的构建**。只需要把 `init.lua` 和 `nvim-pack-lock.json` 两个文件放到版本控制中，就能在任何机器上重建完全相同的插件环境。

> [!tip]- 练习 4 参考答案
> **正确删除流程：**
>
> 1. 从 `init.lua` 中删除 `tokyonight.nvim` 的 spec：
>    ```lua
>    -- 删除这两行
>    -- vim.pack.add { gh 'folke/tokyonight.nvim' }
>    -- require('tokyonight').setup { style = 'night' }
>    ```
>
> 2. 保存并重启 Neovim。
>
> 3. 运行删除命令：
>    ```vim
>    :lua vim.pack.del({ 'tokyonight.nvim' })
>    ```
>
> 4. 检查健康状态：
>    ```vim
>    :checkhealth vim.pack
>    ```
>    应无"未激活插件"或"lockfile 不一致"警告。
>
> **错误示范的后果：**
> 如果你手动删除 `~/.local/share/nvim/site/pack/core/opt/tokyonight.nvim/`，lockfile 中仍然记录着该插件。下次启动时，vim.pack 会发现 lockfile 与磁盘不一致，可能自动重新 clone 该插件，或 `:checkhealth vim.pack` 报不一致警告。因此**必须**用 `vim.pack.del()` 来保持 lockfile 同步。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [`:help vim.pack`](https://neovim.io/doc/user/helptag.html?tag=vim.pack) — 官方文档
- [`:help vim.pack-events`](https://neovim.io/doc/user/helptag.html?tag=vim.pack-events) — PackChanged / PackChangedPre 事件
- [`:help vim.version.range()`](https://neovim.io/doc/user/helptag.html?tag=vim.version.range()) — semver 范围语法
- [echasnovski's guide to vim.pack](https://github.com/echasnovski/nvim/blob/main/pack.md) — vim.pack 作者的使用指南
- [kickstart.nvim init.lua](https://github.com/nvim-lua/kickstart.nvim/blob/master/init.lua) — 完整实战参考

---

## 常见陷阱

- **lockfile 位置错误**：`nvim-pack-lock.json` 在 **config 目录**（`stdpath('config')`），不是 data 目录。
- **手动删除插件目录**：永远不要手动删 `site/pack/core/opt/` 下的目录，应使用 `vim.pack.del()`。
- **vim.pack.update() 不是普通 diff 窗口**：它是 LSP-powered 的确认 buffer，支持 `:write`、`:quit`、跳转、hover、codeAction。
- **`vim.pack.add()` 是同步的**：如果网络很慢，首次启动会卡住。首次安装完成后，正常使用中不会重复安装。
- **不指定 version 的风险**：`vim.pack.update()` 会更新到默认分支最新 commit，可能引入破坏性变更。
- **plugin/*.lua 自动 source 的 hook 顺序**：install hook 应集中在 `init.lua` 顶部，否则 lockfile bootstrap 期间可能错过首次安装事件。
