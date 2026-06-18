---
title: "06 — 自动命令与事件系统"
updated: 2026-06-18
---

# 06 — 自动命令与事件系统

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 60 分钟
> 前置知识: [[04-init-lua-structure]]（vim.api 基本用法）

---

## 1. 概念讲解

### 什么是自动命令（Autocommand）？

自动命令让你在特定事件发生时自动执行代码。例如：

- 打开 `.lua` 文件时设置缩进为 2 空格
- 保存文件时自动格式化
- LSP 服务器附着时设置快捷键
- 离开插入模式时自动重载配置

### `vim.api.nvim_create_autocmd` 完整参数

```lua
vim.api.nvim_create_autocmd(events, {
    pattern = '*.lua',            -- 匹配模式：string 或 string[]
    callback = function(ev) end,  -- Lua 回调函数
    command = 'echo "..."',       -- Vimscript 命令（与 callback 二选一）
    group = my_group,             -- 事件组 id 或名称
    desc = '...',                 -- 描述
    once = false,                 -- 是否只触发一次
    nested = false,               -- 是否允许嵌套触发其他 autocmd
    buffer = bufnr,               -- buffer-local autocmd
})
```

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `events` | `string`/`string[]` | 是 | 事件名，如 `'BufWritePre'` |
| `pattern` | `string`/`string[]` | 否 | 文件名/文件类型匹配模式 |
| `callback` | `function` | 与 command 二选一 | Lua 回调，接收 `ev` 参数 |
| `command` | `string` | 与 callback 二选一 | Vimscript 命令字符串 |
| `group` | `number`/`string` | 否 | 所属 autocmd 组 |
| `desc` | `string` | 否 | 描述，用于调试 |
| `once` | `boolean` | 否 | 触发一次后自动删除 |
| `nested` | `boolean` | 否 | 允许回调里的操作触发其他 autocmd |
| `buffer` | `number` | 否 | 仅对指定 buffer 生效 |

### 自动命令组（augroup）

用组来组织关联的自动命令，便于管理和清除：

```lua
local my_group = vim.api.nvim_create_augroup('MyConfigGroup', { clear = true })

-- 之后创建的自动命令属于这个组
vim.api.nvim_create_autocmd('BufWritePre', {
    group = my_group,
    pattern = '*.lua',
    callback = function()
        vim.lsp.buf.format()
    end,
})

-- 一次性清除所有
-- vim.api.nvim_del_augroup_by_name('MyConfigGroup')
```

`clear = true` 确保重新加载配置文件时旧的自动命令被清除，避免重复堆积。

> [!WARNING]
> 没有 `clear = true` 且没有 `group` 的自动命令是**匿名的**，重载配置时会**重复创建**——每次 `:source %` 或重启都会新增一份，导致回调被执行多次。这是最难排查的配置 bug 之一。**每个 augroup 都加 `clear = true`**。

### event data（`ev` 参数）

回调函数接收一个 `ev` 参数，包含触发事件的上下文信息：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ev.event` | `string` | 触发的事件名 |
| `ev.buf` | `number` | 相关缓冲区编号 |
| `ev.file` | `string` | 完整文件路径 |
| `ev.match` | `string` | 实际匹配到的 pattern |
| `ev.data` | `table` | 事件特定数据（如 LspAttach 的 client_id） |
| `ev.id` | `number` | autocmd 自身 id |

```lua
vim.api.nvim_create_autocmd('BufWritePost', {
    group = vim.api.nvim_create_augroup('DebugEvent', { clear = true }),
    callback = function(ev)
        print('event: ' .. ev.event)
        print('buf: ' .. ev.buf)
        print('file: ' .. ev.file)
        print('match: ' .. ev.match)
    end,
})
```

### pattern 匹配

```lua
-- 单个模式
pattern = '*.lua'

-- 多个模式
pattern = { '*.lua', '*.vim' }

-- 目录模式（Neovim 0.9+）
pattern = '/home/user/projects/*'

-- FileType 事件用文件类型名（不带 *）
pattern = { 'lua', 'json', 'yaml' }

-- 所有缓冲区（不设置 pattern）
-- 省略 pattern 字段即可
```

> [!IMPORTANT]
> autocmd 的 `pattern` 使用的是**文件通配符**，不是 Lua 模式，也不是正则。`*` 匹配任意字符，`?` 匹配单个字符。`FileType` 事件除外，它匹配 `filetype` 选项的值。

### 用 callback 替代 command

```lua
-- ❌ 旧式（Vimscript 风格）
vim.api.nvim_create_autocmd('BufWritePre', {
    pattern = '*.lua',
    command = "echo '保存 .lua 文件'",
})

-- ✅ 新式（Lua 回调）
vim.api.nvim_create_autocmd('BufWritePre', {
    pattern = '*.lua',
    callback = function(ev)
        vim.notify('保存 ' .. ev.file)
    end,
})
```

### `once`：一次性自动命令

```lua
vim.api.nvim_create_autocmd('BufRead', {
    pattern = '*.md',
    once = true,  -- 触发一次后自动删除
    callback = function()
        vim.notify('首次打开 Markdown 文件！')
    end,
})
```

### `nested`：嵌套 autocmd

默认情况下，autocmd 回调中执行的操作**不会**触发其他 autocmd。设置 `nested = true` 可以改变这一行为。

```lua
-- 示例：保存后触发 BufWritePost 的后续逻辑
vim.api.nvim_create_autocmd('BufWritePre', {
    pattern = '*',
    nested = true,
    callback = function()
        -- 这里的修改如果触发其他事件，会正常传播
    end,
})
```

> [!WARNING]
> `nested = true` 容易导致无限循环或意外副作用。例如 nested 的 `BufWritePre` 中再次写入会反复触发。默认关闭是安全的设计。

### buffer-local autocmd

使用 `buffer = bufnr` 可以创建只对指定 buffer 生效的自动命令，替代旧的 `BufEnter pattern` 写法：

```lua
-- 在当前 buffer 中只触发一次
vim.api.nvim_create_autocmd('BufWritePost', {
    buffer = 0,  -- 0 表示当前 buffer
    once = true,
    callback = function()
        vim.notify('当前 buffer 首次保存')
    end,
})

-- 在 LspAttach 中为指定 buffer 创建局部 autocmd
vim.api.nvim_create_autocmd('LspAttach', {
    callback = function(ev)
        vim.api.nvim_create_autocmd('BufWritePre', {
            buffer = ev.buf,
            callback = function()
                vim.lsp.buf.format()
            end,
        })
    end,
})
```

### 常用事件清单（分类）

| 类别 | 事件 | 触发时机 |
|------|------|---------|
| 启动类 | `VimEnter` | 所有初始化完成后 |
| 启动类 | `UIEnter` | UI 附加后 |
| 启动类 | `BufReadPost` | 读取已有文件后 |
| 启动类 | `BufWinEnter` | buffer 进入窗口后 |
| 编辑类 | `BufWritePre` | 文件保存前 |
| 编辑类 | `BufWritePost` | 文件保存后 |
| 编辑类 | `TextChanged` | 普通模式下文本变化后 |
| 编辑类 | `TextChangedI` | 插入模式下文本变化后 |
| 编辑类 | `InsertEnter` | 进入插入模式 |
| 编辑类 | `InsertLeave` | 离开插入模式 |
| 光标类 | `CursorHold` | 光标停留 `updatetime` 后 |
| 光标类 | `CursorMoved` | 光标移动后 |
| 光标类 | `ModeChanged` | 模式切换后 |
| LSP | `LspAttach` | LSP client 附着到 buffer |
| LSP | `LspDetach` | LSP client 脱离 buffer |
| 插件 | `PackChanged` | vim.pack 插件状态变化后 |
| 插件 | `PackChangedPre` | vim.pack 插件状态变化前 |
| 用户自定义 | `User` | 通过 `nvim_exec_autocmds` 手动触发 |

### 用户自定义事件

```lua
-- 注册自定义事件监听
vim.api.nvim_create_autocmd('User', {
    pattern = 'MyEvent',
    callback = function()
        print('MyEvent 被触发')
    end,
})

-- 触发自定义事件
vim.api.nvim_exec_autocmds('User', { pattern = 'MyEvent' })
```

### `vim.schedule` 在 autocmd 中

某些事件（如 `VimEnter`）中直接执行慢操作会阻塞启动。用 `vim.schedule` 把逻辑推到下一帧：

```lua
vim.api.nvim_create_autocmd('VimEnter', {
    callback = function()
        vim.schedule(function()
            -- 这里执行较重的初始化
            print('延迟执行的初始化')
        end)
    end,
})
```

### `vim.hl.on_yank` 实战

> [!IMPORTANT]
> 0.11+ 中 `vim.highlight` 已重命名为 `vim.hl`。新配置应使用 `vim.hl.on_yank()`。

```lua
vim.api.nvim_create_autocmd('TextYankPost', {
    group = vim.api.nvim_create_augroup('YankHighlight', { clear = true }),
    callback = function()
        vim.hl.on_yank({ higroup = 'IncSearch', timeout = 150 })
    end,
})
```

---

## 2. 代码示例

完整的 `lua/config/autocmds.lua`：

```lua
-- lua/config/autocmds.lua
-- 要求: Neovim 0.12.3+
local M = {}

function M.setup()
    local augroup = vim.api.nvim_create_augroup
    local autocmd = vim.api.nvim_create_autocmd

    -- ====== 通用组 ======
    local general = augroup('GeneralSettings', { clear = true })

    -- 保存时自动删除行尾空格
    autocmd('BufWritePre', {
        group = general,
        pattern = '*',
        callback = function()
            local save_cursor = vim.fn.getpos('.')
            vim.cmd([[%s/\s\+$//e]])  -- e 标志：没有匹配时不报错
            vim.fn.setpos('.', save_cursor)
        end,
    })

    -- 复制后高亮复制区域（0.11+ 用 vim.hl）
    autocmd('TextYankPost', {
        group = general,
        callback = function()
            vim.hl.on_yank({ higroup = 'IncSearch', timeout = 150 })
        end,
    })

    -- 离开插入模式时自动保存
    autocmd('InsertLeave', {
        group = general,
        pattern = '*',
        callback = function()
            if vim.bo.modified and vim.bo.buftype == '' then
                vim.cmd('silent! write')
            end
        end,
    })

    -- ====== 文件类型特定设置 ======
    local filetype_group = augroup('FileTypeSettings', { clear = true })

    -- Makefile 必须用 Tab 缩进
    autocmd('FileType', {
        group = filetype_group,
        pattern = 'make',
        callback = function()
            vim.opt_local.expandtab = false
            vim.opt_local.tabstop = 8
        end,
    })

    -- Lua/JSON/YAML 缩进为 2 空格
    autocmd('FileType', {
        group = filetype_group,
        pattern = { 'lua', 'json', 'yaml', 'yml' },
        callback = function()
            vim.opt_local.tabstop = 2
            vim.opt_local.shiftwidth = 2
        end,
    })

    -- Markdown 自动换行
    autocmd('FileType', {
        group = filetype_group,
        pattern = 'markdown',
        callback = function()
            vim.opt_local.wrap = true
            vim.opt_local.spell = true
        end,
    })

    -- ====== 终端窗口设置 ======
    autocmd('TermOpen', {
        group = general,
        callback = function()
            vim.opt_local.number = false
            vim.opt_local.relativenumber = false
            vim.cmd('startinsert')  -- 自动进入插入模式
        end,
    })

    -- ====== 窗口大小改变时调整 ======
    autocmd('VimResized', {
        group = general,
        callback = function()
            vim.cmd('wincmd =')  -- 均分窗口
        end,
    })

    -- ====== 自定义事件示例 ======
    local custom_group = augroup('CustomEvents', { clear = true })
    autocmd('User', {
        group = custom_group,
        pattern = 'ConfigReloaded',
        callback = function()
            vim.notify('配置已重新加载')
        end,
    })
end

return M
```

**运行方式:**
1. 将上述代码保存为 `lua/config/autocmds.lua`
2. 在 `init.lua` 中添加 `require('config.autocmds').setup()`
3. 打开不同类型的文件观察行为变化
4. 触发自定义事件：`:lua vim.api.nvim_exec_autocmds('User', { pattern = 'ConfigReloaded' })`

---

## 3. 练习

### 练习 1: 创建文件类型自动命令

创建一个自动命令：打开 C/C++ 文件（`*.c`、`*.h`、`*.cpp`、`*.hpp`）时，设置缩进为 4 空格，并启用 `cindent`。

```lua
vim.opt_local.cindent = true  -- C 风格自动缩进
```

### 练习 2: 高亮复制区域

实现复制后短暂高亮效果。这是 `TextYankPost` 事件的经典用例。自己写一遍，不要抄示例。注意使用 `vim.hl.on_yank()` 而不是旧的 `vim.highlight.on_yank()`。

### 练习 3: 自动保存

创建一个自动命令：在插入模式下停止输入 `updatetime` 毫秒后，如果当前 buffer 有修改且是普通文件，则自动保存。提示：使用 `CursorHoldI` 事件。

### 练习 4: 诊断自动命令调试（可选）

在 Neovim 中运行：
```vim
:lua vim.api.nvim_create_autocmd('BufEnter', { callback = function() print('进入: ' .. vim.fn.expand('%')) end, })
```

然后用 `:messages` 查看打印的日志。再运行 `:autocmd BufEnter` 查看所有注册的自动命令。理解 `clear = true` 的重要性后，用 `:lua vim.api.nvim_del_augroup_by_name('GeneralSettings')` 清除示例中的组。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> -- 练习 1: C/C++ 文件类型自动命令
> -- 放在 autocmds 模块中，或直接放在 init.lua
>
> local augroup = vim.api.nvim_create_augroup
> local autocmd = vim.api.nvim_create_autocmd
>
> local cpp_group = augroup('CppSettings', { clear = true })
>
> autocmd('FileType', {
>     group = cpp_group,
>     pattern = { 'c', 'cpp', 'h', 'hpp' },
>     callback = function()
>         -- 使用 opt_local 确保只影响当前缓冲区
>         vim.opt_local.tabstop = 4
>         vim.opt_local.shiftwidth = 4
>         vim.opt_local.expandtab = false  -- C 代码中通常保留 Tab
>         vim.opt_local.cindent = true     -- C 风格自动缩进
>     end,
> })
> ```
>
> **关键点：**
> - `augroup` 搭配 `clear = true` 确保重载配置时不会重复累积自动命令。
> - 使用 `vim.opt_local` 而非 `vim.opt`，避免影响其他缓冲区。
> - `pattern` 是 table 时匹配多个文件扩展名。Neovim 的 `FileType` 事件使用文件类型名（不含 `.`），即 `'c'` 而非 `'*.c'`。

> [!tip]- 练习 2 参考答案
> ```lua
> -- 练习 2: 复制后高亮复制区域（TextYankPost 事件）
> local yank_group = vim.api.nvim_create_augroup('YankHighlight', { clear = true })
>
> vim.api.nvim_create_autocmd('TextYankPost', {
>     group = yank_group,
>     callback = function()
>         -- vim.hl.on_yank 是高亮 yank 区域的便捷函数
>         -- higroup: 使用哪个高亮组（IncSearch 是内置的反色高亮）
>         -- timeout: 高亮持续时间（毫秒），150ms 足够亮一下
>         -- on_macro: 宏执行时是否也触发（false 避免宏播放时干扰）
>         vim.hl.on_yank({
>             higroup = 'IncSearch',
>             timeout = 150,
>             on_macro = false,
>         })
>     end,
> })
> ```
>
> **核心 API：** `vim.hl.on_yank()` 是 Neovim 0.11+ 提供的一站式方案，内部使用 `vim.hl.range()` 在 yank 区域创建临时高亮。无需手动保存/恢复光标，也无需手动清除——`timeout` 到期后自动消失。旧教程中的 `vim.highlight.on_yank()` 在新版本中已被重命名。

> [!tip]- 练习 3 参考答案
> ```lua
> -- 练习 3: 插入模式下停止输入后自动保存
> local auto_save_group = vim.api.nvim_create_augroup('AutoSave', { clear = true })
>
> vim.api.nvim_create_autocmd('CursorHoldI', {
>     group = auto_save_group,
>     pattern = '*',
>     callback = function()
>         if vim.bo.modified and vim.bo.buftype == '' then
>             vim.cmd('silent! write')
>         end
>     end,
> })
> ```
>
> **关键点：**
> - `CursorHoldI` 在插入模式下光标停止移动 `updatetime` 毫秒后触发。
> - `vim.bo.modified` 判断 buffer 是否有未保存修改。
> - `vim.bo.buftype == ''` 排除特殊缓冲区（如终端、文件树、浮窗）。
> - `silent!` 避免保存失败时弹出错误提示。
> - 记得 `updatetime` 默认 4000ms，可在 init.lua 中设为 `vim.o.updatetime = 1000` 让自动保存更灵敏。

> [!tip]- 练习 4 参考答案（可选）
> 在 Neovim 中逐步操作：
>
> ```vim
> " 步骤 1: 创建一个简单的调试自动命令
> :lua vim.api.nvim_create_autocmd('BufEnter', { callback = function() print('进入: ' .. vim.fn.expand('%')) end })
>
> " 步骤 2: 切换几次缓冲区，然后查看输出
> :messages
>
> " 步骤 3: 查看所有 BufEnter 自动命令（会看到刚才创建的匿名 autocmd）
> :autocmd BufEnter
>
> " 步骤 4: 如果之前按照示例创建了 GeneralSettings，清除它
> :lua vim.api.nvim_del_augroup_by_name('GeneralSettings')
>
> " 步骤 5: 验证清除——该组下的自动命令不再触发
> :autocmd BufEnter
> ```
>
> **核心理解：**
> - 没有 `clear = true` 且没有 `group` 的自动命令是**匿名的**，重载配置时会**重复创建**——每次 `:source %` 或重启都会新增一份，导致回调被执行多次。
> - `:autocmd <Event>` 可以查看所有注册的自动命令，是调试的利器。
> - `vim.api.nvim_del_augroup_by_name()` 可以按组名清除，`clear = true` 本质上就是在创建组时先调用它。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [`:help autocmd`](https://neovim.io/doc/user/autocmd.html)
- [`:help autocmd-events`](https://neovim.io/doc/user/autocmd.html#autocmd-events) — 全部事件列表
- [Neovim Lua Guide — Autocommands](https://neovim.io/doc/user/lua-guide.html#lua-guide-autocommands)
- [`:help vim.hl.on_yank()`](https://neovim.io/doc/user/lua.html#vim.hl.on_yank()) — 0.11+ 高亮 API
- [`:help PackChanged`](https://neovim.io/doc/user/lua.html#PackChanged) — vim.pack 事件

---

## 常见陷阱

- **忘记 `clear = true`**：重载配置时旧的自动命令不会被清除，导致累积执行。这是最难排查的配置 bug 之一。**每个 augroup 都加 `clear = true`**。
- **在自动命令中修改缓冲区选项用 `vim.bo` 或 `vim.opt_local`**：`vim.opt_local` 或 `vim.bo[args.buf]` 只影响当前缓冲区，不会意外修改全局设置。
- **`TextYankPost` 在每次 yank 时触发**：注意性能，回调应该轻量。
- **`BufWritePre` 中使用 `vim.lsp.buf.format()` 需要先确保 LSP 已附着**：否则静默失败。
- **自动命令回调中的 `args` 参数**：`args.buf`（缓冲区编号）、`args.file`（文件名）、`args.match`（匹配的模式）等信息很实用。
- **`InsertLeave` 触发保存可能导致意外写入**：检查 `vim.bo.buftype == ''` 排除特殊缓冲区（如文件树、终端）。
- **混淆 pattern 类型**：autocmd 的 `pattern` 是文件通配符，不是 Lua 模式。`FileType` 事件用文件类型名。
- **误用 `vim.highlight` 而不是 `vim.hl`**：0.11+ 已重命名，旧代码会触发弃用警告。
- **`nested = true` 导致循环**：在会触发同名事件的回调中开启 nested 可能造成无限循环。
- **自定义 `User` 事件忘记传 `pattern`**：`nvim_exec_autocmds('User', { pattern = 'MyEvent' })` 必须带 pattern，否则不会匹配到监听器。
