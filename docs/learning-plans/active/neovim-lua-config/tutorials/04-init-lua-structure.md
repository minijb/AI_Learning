---
title: "04 — init.lua 结构与基本选项配置"
updated: 2026-06-18
---

# 04 — init.lua 结构与基本选项配置

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 55 分钟
> 前置知识: [[03-lua-functions-modules]]（模块系统）

---

## 1. 概念讲解

### init.lua 的定位

Neovim 启动时按以下顺序查找配置文件：

1. `~/.config/nvim/init.lua`（Lua 配置，推荐）
2. `~/.config/nvim/init.vim`（Vimscript 配置，兼容旧配置）

两者都存在时，Neovim **只加载 `init.lua`**，忽略 `init.vim`。

### 两种配置组织风格

**风格 A: kickstart 单文件风格（本计划推荐）**

```text
~/.config/nvim/
├── init.lua              ← 单一入口，~1000 行，9 个 do 块
├── nvim-pack-lock.json   ← vim.pack 锁文件（自动生成）
├── lua/
│   ├── kickstart/        ← kickstart 自带的扩展模块
│   │   └── plugins/      ←   可选插件（debug, lint, ...）
│   └── custom/           ← 你的自定义插件
│       └── plugins/
└── after/                ← 覆盖/补充配置（最后加载）
```

**风格 B: 模块化风格（从 kickstart 演进而来）**

```text
~/.config/nvim/
├── init.lua              ← 入口：设置 leader + require 各模块
├── nvim-pack-lock.json
├── lua/
│   └── config/
│       ├── options.lua   ← 编辑器选项
│       ├── keymaps.lua   ← 按键映射
│       ├── autocmds.lua  ← 自动命令
│       ├── plugins.lua   ← vim.pack.add() 集中管理
│       ├── lsp.lua       ← LSP 配置
│       └── completion.lua← blink.cmp 配置
└── after/
```

两种风格可以根据个人偏好选择。kickstart 单文件适合学习和快速上手；模块化适合长期维护较大配置。

### `vim.loader.enable()`：为什么放在 init.lua 第一行

`vim.loader.enable()` 是 Neovim 0.9+ 引入的模块缓存机制，kickstart.nvim 把它放在 `init.lua` 第一行。它的核心作用是：

- 把 `lua/` 下的源码模块**预编译并缓存**到 `stdpath('cache')/luac/`；
- 下次启动时直接加载字节码，减少 Lua 解析开销；
- 对大型配置（几十个模块）启动速度提升尤其明显。

```lua
-- ~/.config/nvim/init.lua
vim.loader.enable()  -- 必须放在第一行，越早越好
```

> [!IMPORTANT]
> `vim.loader.enable()` 在官方文档中仍标记为实验性，但已被 kickstart.nvim、LazyVim 等主流配置默认启用，稳定性已经过大规模验证。它只缓存模块的**字节码**，不缓存执行结果，修改配置后仍需要重启 Neovim 才能生效。

**注意事项：**

- 放在第一行是为了让后续所有 `require()` 都走缓存路径；
- 开发自己的模块时如果感觉“改了没生效”，先检查是不是 loader 缓存导致的，可临时注释后重启验证；
- 缓存目录在 `stdpath('cache')` 下，手动删除该目录可强制清缓存。

### 选项体系完整对比

Neovim 提供了多层选项访问接口，区别主要体现在**作用域**和**赋值语义**上。

| API | 作用域 | 读写对象 | 典型示例 |
|------|--------|----------|---------|
| `vim.o.xxx` | 全局 | 当前全局/局部选项的“有效值” | `vim.o.number = true` |
| `vim.go.xxx` | 仅全局 | 全局选项值；对纯局部选项会报错 | `vim.go.shell = 'bash'` |
| `vim.bo[buf].xxx` | buffer-local | 指定缓冲区的局部选项 | `vim.bo[0].filetype = 'lua'` |
| `vim.wo[win].xxx` | window-local | 指定窗口的局部选项 | `vim.wo[0].number = true` |
| `vim.opt.xxx` | 全局 | 面向对象的 `:set` 语义接口 | `vim.opt.listchars:append({ trail = '·' })` |

`vim.bo` 和 `vim.wo` 支持省略索引表示当前 buffer/window，但**推荐显式写法**，在回调中避免歧义：

```lua
vim.bo.filetype              -- 当前 buffer
vim.bo[0].filetype           -- 同上，0 代表当前 buffer
vim.bo[vim.api.nvim_get_current_buf()].filetype  -- 显式指定
```

#### `vim.opt` 的链式操作

`vim.opt` 是面向对象的选项接口，最接近 Vimscript 的 `:set` 语义，适合列表/字典类选项：

```lua
-- 用 table 赋值
vim.opt.wildignore = { '*.o', '*.a', '*.obj', '*/node_modules/*' }

-- 追加
vim.opt.listchars:append({ trail = '·', nbsp = '␣' })

-- 前置
vim.opt.path:prepend({ 'src', 'lua' })

-- 移除
vim.opt.wildignore:remove({ '*.a' })
```

> [!NOTE]
> `vim.opt` 返回的是 `Option` 对象，不是普通 Lua table。读取当前值要用 `:get()`：
> ```lua
> local list = vim.opt.listchars:get()
> print(vim.inspect(list))
> ```

#### 何时用哪个？决策表

| 场景 | 推荐 API | 原因 |
|------|---------|------|
| 简单布尔/数值/字符串全局选项 | `vim.o` | 最直观，如 `vim.o.number = true` |
| 复合选项（`listchars`、`wildignore`） | `vim.opt` | 支持 table 和 append/prepend/remove |
| 只想读/写纯全局选项，避免误碰局部值 | `vim.go` | 对纯局部选项会显式报错 |
| 在 autocmd/keymap 中设置当前 buffer | `vim.bo[buf]` / `vim.opt_local` | 不影响其他 buffer |
| 在 autocmd/keymap 中设置当前 window | `vim.wo[win]` / `vim.opt_local` | 不影响其他 window |

### `vim.g` / `vim.b` / `vim.w` / `vim.t` / `vim.v`：变量作用域

这些接口对应 Vimscript 的 `g:`、`b:`、`w:`、`t:`、`v:` 变量命名空间。

| API | 作用域 | 用途 | 示例 |
|------|--------|------|------|
| `vim.g.xxx` | 全局 | 配置插件、设置 leader | `vim.g.mapleader = ' '` |
| `vim.b[buf].xxx` | buffer-local | 每个 buffer 的临时状态 | `vim.b.my_var = 1` |
| `vim.w[win].xxx` | window-local | 每个 window 的临时状态 | `vim.w.my_var = 1` |
| `vim.t[tab].xxx` | tabpage-local | 每个 tabpage 的临时状态 | `vim.t.my_var = 1` |
| `vim.v.xxx` | 预定义变量 | Neovim 内部状态，只读为主 | `vim.v.vim_did_enter` |

```lua
-- 全局变量：所有 buffer/window 共享
vim.g.my_config_version = '1.0'

-- buffer-local：只存在于当前 buffer（0 表示当前）
vim.b[0].last_search = 'pattern'

-- window-local：只存在于当前 window
vim.w[0].is_zoomed = false

-- tabpage-local
vim.t[0].tab_label = 'main'

-- vim 内部变量（通常只读）
if vim.v.vim_did_enter == 1 then
  print('VimEnter 已经触发')
end
```

> [!WARNING]
> `vim.b.my_var` 这种省略索引的写法只在**当前 buffer** 有效。在 `LspAttach` 等异步回调中，当前 buffer 可能已经改变，建议始终使用 `vim.b[args.buf].xxx`。

### runtimepath 与标准路径

Neovim 通过 `runtimepath`（`'rtp'`）查找运行时文件。理解标准路径有助于你正确放置配置、插件数据和缓存。

```lua
print(vim.fn.stdpath('config'))   -- 配置目录：~/.config/nvim
print(vim.fn.stdpath('data'))     -- 数据目录：~/.local/share/nvim
print(vim.fn.stdpath('cache'))    -- 缓存目录：~/.cache/nvim
print(vim.fn.stdpath('log'))      -- 日志目录：~/.local/state/nvim
print(vim.fn.stdpath('state'))    -- 状态目录：~/.local/state/nvim
```

Windows 对应：

| 类型 | 路径 |
|------|------|
| config | `%LOCALAPPDATA%\nvim` |
| data | `%LOCALAPPDATA%\nvim-data` |
| cache | `%TEMP%\nvim` |
| state | `%LOCALAPPDATA%\nvim-data` |

#### 配置目录结构约定

```text
~/.config/nvim/
├── init.lua              ← 入口
├── lua/                  ← Lua 模块
│   └── config/
│       ├── options.lua
│       ├── keymaps.lua
│       └── autocmds.lua
├── plugin/               ← 启动时自动 source 的 .lua/.vim 脚本
├── after/                ← 最后加载，用于覆盖插件默认
│   ├── plugin/
│   └── ftplugin/
├── ftplugin/             ← 文件类型特定配置
├── lsp/                  ← 0.12 原生 LSP 配置文件
│   ├── lua_ls.lua
│   └── rust_analyzer.lua
└── nvim-pack-lock.json   ← vim.pack 锁文件
```

> [!TIP]
> `ftplugin/` 下的脚本按文件类型自动加载，是 `FileType` autocmd 的声明式替代。例如 `ftplugin/lua.lua` 会在所有 Lua 文件打开时执行。

### 延迟设置耗时选项

某些选项的赋值会触发外部交互或探测，放在 `vim.schedule()` 中可以让 Neovim 先完成启动流程，再异步设置，避免阻塞 UI。

```lua
-- kickstart 范式：延迟设置剪贴板，减少启动耗时
vim.schedule(function()
  vim.o.clipboard = 'unnamedplus'
end)
```

`vim.schedule(fn)` 把函数排到事件循环的下一帧执行。适合放置：

- `clipboard = 'unnamedplus'`（可能连接外部剪贴板服务）；
- 首次启动时的欢迎消息；
- 需要等待其他初始化完成的探测逻辑。

> [!NOTE]
> 如果你主要在 Neovim 内部编辑，对启动速度不敏感，也可以直接 `vim.o.clipboard = 'unnamedplus'`。`vim.schedule` 是优化，不是必需。

### 常用基础选项

```lua
-- 行号
vim.o.number = true
-- vim.o.relativenumber = true  -- 可选：相对行号

-- 缩进
vim.o.tabstop = 4
vim.o.shiftwidth = 4
vim.o.expandtab = true

-- 搜索
vim.o.ignorecase = true
vim.o.smartcase = true

-- 界面
vim.o.signcolumn = 'yes'       -- LSP 诊断标记列
vim.o.scrolloff = 10           -- 光标距边界的最小行数
vim.o.cursorline = true        -- 高亮当前行
vim.o.termguicolors = true     -- 24 位真彩色（自动启用）

-- 剪贴板
vim.schedule(function()
  vim.o.clipboard = 'unnamedplus'  -- 延迟设置，减少启动时间
end)

-- 分割窗口
vim.o.splitright = true
vim.o.splitbelow = true

-- undo
vim.o.undofile = true

-- 预览替换
vim.o.inccommand = 'split'

-- 确认退出（避免误关闭未保存文件）
vim.o.confirm = true
```

---

## 2. 代码示例

### 最小 init.lua（kickstart 风格 foundation block）

```lua
-- ~/.config/nvim/init.lua
-- 要求: Neovim 0.12.3+

-- 1. 加速模块加载（必须在第一行）
vim.loader.enable()

-- 2. leader 必须在任何 keymap 和多数插件之前设置
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '

-- 3. 基础选项
vim.o.number = true
vim.o.mouse = 'a'
vim.o.showmode = false
vim.o.breakindent = true
vim.o.undofile = true
vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.signcolumn = 'yes'
vim.o.updatetime = 250
vim.o.timeoutlen = 300
vim.o.splitright = true
vim.o.splitbelow = true
vim.o.list = true
vim.opt.listchars = { tab = '» ', trail = '·', nbsp = '␣' }
vim.o.inccommand = 'split'
vim.o.cursorline = true
vim.o.scrolloff = 10
vim.o.confirm = true

-- 4. 延迟设置可能拖慢启动的选项
vim.schedule(function()
  vim.o.clipboard = 'unnamedplus'
end)

-- 5. 标准路径探查（启动后可运行）
vim.api.nvim_create_autocmd('VimEnter', {
  once = true,
  callback = function()
    print('config: ' .. vim.fn.stdpath('config'))
    print('data:   ' .. vim.fn.stdpath('data'))
    print('cache:  ' .. vim.fn.stdpath('cache'))
  end,
})
```

**运行方式:**
1. 创建 `~/.config/nvim/init.lua`（Windows: `%LOCALAPPDATA%/nvim/init.lua`）
2. 写入上述代码
3. 启动 Neovim，`:set number?` 验证行号已开启
4. 依次检查 `:set scrolloff?`、`:set signcolumn?` 等确认选项生效
5. 启动后 `:messages` 查看 `stdpath` 输出

### 模块化 options.lua

```lua
-- lua/config/options.lua
local M = {}

function M.setup()
  -- vim.loader.enable() 仍应保留在 init.lua 第一行

  -- 简单全局选项用 vim.o
  vim.o.number = true
  vim.o.relativenumber = false
  vim.o.mouse = 'a'
  vim.o.showmode = false
  vim.o.wrap = false

  -- 复合选项用 vim.opt
  vim.opt.listchars = { tab = '» ', trail = '·', nbsp = '␣' }
  vim.opt.wildignore = { '*.o', '*.a', '*.obj', '*/node_modules/*' }

  -- 延迟设置
  vim.schedule(function()
    vim.o.clipboard = 'unnamedplus'
  end)
end

return M
```

然后在 `init.lua` 中加载：

```lua
require('config.options').setup()
```

---

## 3. 练习

### 练习 1: 迁移现有配置

如果你已有 `init.vim`，将其中的 `set` 命令翻译成 Lua：

```vim
" Vimscript                    →  Lua
set number                     →  vim.o.number = true
set tabstop=4                  →  vim.o.tabstop = 4
set mouse=a                    →  vim.o.mouse = 'a'
set listchars=tab:▸\ ,trail:·  →  vim.opt.listchars = { tab = '▸ ', trail = '·' }
```

### 练习 2: 理解 `vim.opt` 的 table 语义

在 Neovim 中执行并观察输出：

```lua
:lua vim.opt.listchars = { tab = '» ', trail = '·' }
:lua print(vim.inspect(vim.opt.listchars:get()))
:lua vim.opt.listchars:append({ extends = '>' })
:lua print(vim.inspect(vim.opt.listchars:get()))
```

### 练习 3: 按文件类型设置局部选项

创建一个 `ftplugin/lua.lua` 文件，使得所有 Lua 文件打开时：

- `tabstop = 2`
- `shiftwidth = 2`
- `expandtab = true`

提示：在 `ftplugin/` 文件中可以直接写 `vim.opt_local.xxx = ...`。

### 练习 4: 标准路径与变量作用域（可选）

在 `init.lua` 中设置一个 buffer-local 变量 `vim.b[0].initialized_at`，然后在启动后用 `:lua print(vim.b[0].initialized_at)` 读取。思考：为什么这个变量不会出现在其他 buffer 中？

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 以下是将常见 Vimscript `set` 命令翻译为 Lua 的对照表（在 Neovim 中验证）：
>
> | Vimscript | Lua |
> |---|---|
> | `set number` | `vim.o.number = true` |
> | `set relativenumber` | `vim.o.relativenumber = true` |
> | `set tabstop=4` | `vim.o.tabstop = 4` |
> | `set shiftwidth=4` | `vim.o.shiftwidth = 4` |
> | `set expandtab` | `vim.o.expandtab = true` |
> | `set mouse=a` | `vim.o.mouse = 'a'` |
> | `set ignorecase` | `vim.o.ignorecase = true` |
> | `set smartcase` | `vim.o.smartcase = true` |
> | `set cursorline` | `vim.o.cursorline = true` |
> | `set termguicolors` | `vim.o.termguicolors = true` |
> | `set scrolloff=10` | `vim.o.scrolloff = 10` |
> | `set signcolumn=yes` | `vim.o.signcolumn = 'yes'` |
> | `set undofile` | `vim.o.undofile = true` |
> | `set splitright` | `vim.o.splitright = true` |
> | `set splitbelow` | `vim.o.splitbelow = true` |
> | `set list` | `vim.o.list = true` |
> | `set listchars=tab:»\ ,trail:·` | `vim.opt.listchars = { tab = '» ', trail = '·' }` |
> | `set inccommand=split` | `vim.o.inccommand = 'split'` |
> | `set clipboard=unnamedplus` | `vim.o.clipboard = 'unnamedplus'` |
>
> **翻译规则：**
> - 布尔选项：`set X` → `vim.o.X = true`；`set noX` → `vim.o.X = false`
> - 数值/字符串选项：`set X=Y` → `vim.o.X = Y`（字符串需引号）
> - 含特殊字符的选项（如 `listchars`）：用 `vim.opt.X = { ... }` table 形式
> - `clipboard` 建议放在 `vim.schedule()` 中延迟设置以加速启动

> [!tip]- 练习 2 参考答案
> 在 Neovim 中执行以下命令并观察输出：
>
> ```lua
> -- 先设置初始值
> vim.opt.listchars = { tab = '» ', trail = '·' }
>
> -- 查看当前值（vim.inspect 格式化输出）
> :lua print(vim.inspect(vim.opt.listchars:get()))
> -- 输出类似: { tab = '» ', trail = '·' }
>
> -- 使用 append 追加
> :lua vim.opt.listchars:append({ extends = '>' })
>
> -- 再次查看
> :lua print(vim.inspect(vim.opt.listchars:get()))
> -- 输出: { tab = '» ', trail = '·', extends = '>' }
> ```
>
> **理解：** `vim.opt.listchars:get()` 返回普通 Lua table。`:append()`、`:prepend()`、`:remove()` 是 `vim.opt` 对象的方法，模拟 Vimscript 的 `set listchars+=extends:>` 语法。注意 `vim.opt.listchars` 本身不是 table，所以 `vim.inspect(vim.opt.listchars)` 不会得到预期结果。

> [!tip]- 练习 3 参考答案
> 创建 `~/.config/nvim/ftplugin/lua.lua`：
>
> ```lua
> -- ~/.config/nvim/ftplugin/lua.lua
> -- 该文件会在每个 Lua 文件的 FileType 事件后自动加载
>
> vim.opt_local.tabstop = 2
> vim.opt_local.shiftwidth = 2
> vim.opt_local.expandtab = true
> ```
>
> **验证：** 打开任意 `.lua` 文件，运行 `:setlocal tabstop? shiftwidth? expandtab?`，应显示 `tabstop=2 shiftwidth=2 expandtab`。打开其他类型文件不应受影响。
>
> **关键点：** `ftplugin/` 是 `FileType` autocmd 的声明式替代，比手写 autocmd 更干净，也更容易被 `after/ftplugin/` 覆盖。

> [!tip]- 练习 4 参考答案（可选）
> 在 `init.lua` 中：
>
> ```lua
> vim.api.nvim_create_autocmd('VimEnter', {
>   once = true,
>   callback = function()
>     vim.b[0].initialized_at = os.date('%Y-%m-%d %H:%M:%S')
>   end,
> })
> ```
>
> 启动后：
>
> ```vim
> :lua print(vim.b[0].initialized_at)
> ```
>
> **理解：** `vim.b[0]` 只访问当前 buffer（编号为 0 表示当前）。当你切换到另一个 buffer 时，`vim.b[0].initialized_at` 可能变成 `nil`，因为该变量只存在于最初那个 buffer。这正是 buffer-local 变量的语义：每个 buffer 有独立的命名空间。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Neovim 官方 Lua Guide — Options](https://neovim.io/doc/user/lua-guide.html#lua-guide-options)
- [`:help vim.opt`](https://neovim.io/doc/user/lua.html#vim.opt)
- [`:help vim.loader`](https://neovim.io/doc/user/helptag.html?tag=vim.loader) — 0.12 新增的缓存加速
- [`:help options`](https://neovim.io/doc/user/options.html) — 所有可用选项的完整列表
- [`:help standard-path`](https://neovim.io/doc/user/starting.html#standard-path) — 标准路径说明
- [Neovim Lua Guide — Variables](https://neovim.io/doc/user/lua-guide.html#lua-guide-variables)

---

## 常见陷阱

- **在 Windows 上路径分隔符**：Lua 字符串中的 `\` 需要转义。用 `[[]]` 或 `/` 代替。
- **`vim.opt.listchars` 是 Option 对象不是字符串**：`vim.opt.listchars = { tab = '▸ ' }`，不是 `vim.opt.listchars = 'tab:▸ '`。
- **`vim.g.mapleader` 必须在所有 keymap 之前设置**：因为 keymap 在定义时就会解析 leader 的值。
- **`clipboard = 'unnamedplus'` 放在 `vim.schedule` 中**：kickstart 的做法是延迟设置以加速启动。如果你有频繁用系统剪贴板的需求，可以直接设置。
- **`vim.loader.enable()` 可能跳过代码变更**：修改了 `lua/` 下的模块后，需要重启 Neovim 才能看到效果。开发自己的配置时可以暂时注释掉这行。
- **混淆 `vim.o` 和 `vim.go`**：`vim.go` 对纯局部选项会报错，`vim.o` 则会尝试读写有效值。不确定时用 `vim.o` 更安全。
- **`vim.bo`/`vim.wo` 索引 0 的歧义**：在异步回调中，当前 buffer/window 可能已经改变，建议用 `args.buf` 或显式 `vim.api.nvim_get_current_buf()`。
- **`ftplugin/` 文件命名错误**：必须是文件类型名，如 `lua.lua`、`python.lua`，不是 `*.lua.lua` 或 `.vim`。
