---
title: "06 — 自动命令与事件系统"
updated: 2026-06-05
---

# 06 — 自动命令与事件系统

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 50 分钟
> 前置知识: 04-init-lua-structure（vim.api 基本用法）

---

## 1. 概念讲解

### 什么是自动命令（Autocommand）？

自动命令让你在特定事件发生时自动执行代码。例如：

- 打开 `.lua` 文件时设置缩进为 2 空格
- 保存文件时自动格式化
- LSP 服务器附着时设置快捷键
- 离开插入模式时自动重载配置

### vim.api.nvim_create_autocmd（推荐方式）

```lua
vim.api.nvim_create_autocmd(events, opts)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `events` | `string` 或 `string[]` | 事件名，如 `"BufWritePre"`、`{ "BufRead", "BufNewFile" }` |
| `opts` | `table` | 选项表（pattern、callback、group 等） |

### 常用事件

| 事件 | 触发时机 |
|------|---------|
| `BufRead` | 文件读取后 |
| `BufWritePre` | 文件保存前 |
| `BufWritePost` | 文件保存后 |
| `BufEnter` | 进入缓冲区 |
| `InsertLeave` | 离开插入模式 |
| `TextYankPost` | 复制/剪切文本后 |
| `CursorHold` | 光标停留一段时间后 |
| `LspAttach` | LSP 服务器附着到缓冲区 |
| `DiagnosticChanged` | 诊断信息变化 |
| `VimResized` | 窗口大小变化 |
| `ColorScheme` | 配色方案变化 |
| `FileType` | 文件类型确定后 |

完整列表：`:help autocmd-events`

### 自动命令组（augroup）

用组来组织关联的自动命令，便于管理和清除：

```lua
local my_group = vim.api.nvim_create_augroup("MyConfigGroup", { clear = true })

-- 之后创建的自动命令属于这个组
vim.api.nvim_create_autocmd("BufWritePre", {
    group = my_group,
    pattern = "*.lua",
    callback = function()
        vim.lsp.buf.format()
    end,
})

-- 一次性清除所有
-- vim.api.nvim_del_augroup_by_name("MyConfigGroup")
```

`clear = true` 确保重新加载配置文件时旧的自动命令被清除，避免重复堆积。

### pattern 匹配

```lua
-- 单个模式
pattern = "*.lua"

-- 多个模式
pattern = { "*.lua", "*.vim" }

-- 目录模式（Neovim 0.9+）
pattern = "/home/user/projects/*"

-- 所有缓冲区（不设置 pattern）
-- 省略 pattern 字段即可
```

### 用 callback 替代 command

```lua
-- ❌ 旧式（Vimscript 风格）
vim.api.nvim_create_autocmd("BufWritePre", {
    pattern = "*.lua",
    command = "echo '保存 .lua 文件'",
})

-- ✅ 新式（Lua 回调）
vim.api.nvim_create_autocmd("BufWritePre", {
    pattern = "*.lua",
    callback = function(args)
        vim.notify("保存 " .. args.file)
    end,
})
```

### 一次性自动命令（once）

```lua
vim.api.nvim_create_autocmd("BufRead", {
    pattern = "*.md",
    once = true,  -- 触发一次后自动删除
    callback = function()
        vim.notify("首次打开 Markdown 文件！")
    end,
})
```

---

## 2. 代码示例

完整的 `lua/config/autocmds.lua`：

```lua
-- lua/config/autocmds.lua
local M = {}

function M.setup()
    local augroup = vim.api.nvim_create_augroup
    local autocmd = vim.api.nvim_create_autocmd

    -- ====== 通用组 ======
    local general = augroup("GeneralSettings", { clear = true })

    -- 保存时自动删除行尾空格
    autocmd("BufWritePre", {
        group = general,
        pattern = "*",
        callback = function()
            local save_cursor = vim.fn.getpos(".")
            vim.cmd([[%s/\s\+$//e]])  -- e 标志：没有匹配时不报错
            vim.fn.setpos(".", save_cursor)
        end,
    })

    -- 复制后高亮复制区域
    autocmd("TextYankPost", {
        group = general,
        callback = function()
            vim.highlight.on_yank({ higroup = "IncSearch", timeout = 150 })
        end,
    })

    -- 离开插入模式时自动保存
    autocmd("InsertLeave", {
        group = general,
        pattern = "*",
        callback = function()
            if vim.bo.modified and vim.bo.buftype == "" then
                vim.cmd("silent! write")
            end
        end,
    })

    -- ====== 文件类型特定设置 ======
    local filetype_group = augroup("FileTypeSettings", { clear = true })

    -- Makefile 必须用 Tab 缩进
    autocmd("FileType", {
        group = filetype_group,
        pattern = "make",
        callback = function()
            vim.opt_local.expandtab = false
            vim.opt_local.tabstop = 8
        end,
    })

    -- Lua/JSON/YAML 缩进为 2 空格
    autocmd("FileType", {
        group = filetype_group,
        pattern = { "lua", "json", "yaml", "yml" },
        callback = function()
            vim.opt_local.tabstop = 2
            vim.opt_local.shiftwidth = 2
        end,
    })

    -- Markdown 自动换行
    autocmd("FileType", {
        group = filetype_group,
        pattern = "markdown",
        callback = function()
            vim.opt_local.wrap = true
            vim.opt_local.spell = true
        end,
    })

    -- ====== 终端窗口设置 ======
    autocmd("TermOpen", {
        group = general,
        callback = function()
            vim.opt_local.number = false
            vim.opt_local.relativenumber = false
            vim.cmd("startinsert")  -- 自动进入插入模式
        end,
    })

    -- ====== 窗口大小改变时调整 ======
    autocmd("VimResized", {
        group = general,
        callback = function()
            vim.cmd("wincmd =")  -- 均分窗口
        end,
    })
end

return M
```

**运行方式:**
1. 将上述代码保存为 `lua/config/autocmds.lua`
2. 在 `init.lua` 中添加 `require("config.autocmds").setup()`
3. 打开不同类型的文件观察行为变化

---

## 3. 练习

### 练习 1: 创建文件类型自动命令
创建一个自动命令：打开 C/C++ 文件（`*.c`、`*.h`、`*.cpp`、`*.hpp`）时，设置缩进为 4 空格，并启用 `cindent`。

```lua
vim.opt_local.cindent = true  -- C 风格自动缩进
```

### 练习 2: 高亮复制区域
实现复制后短暂高亮效果。这是 `TextYankPost` 事件的经典用例。自己写一遍，不要抄示例。

### 练习 3: 诊断自动命令调试（可选）
在 Neovim 中运行：
```vim
:lua vim.api.nvim_create_autocmd("BufEnter", { callback = function() print("进入: " .. vim.fn.expand("%")) end, })
```
然后用 `:messages` 查看打印的日志。再运行 `:autocmd BufEnter` 查看所有注册的自动命令。理解 `clear = true` 的重要性后，用 `:lua vim.api.nvim_del_augroup_by_name("GeneralSettings")` 清除示例中的组。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> -- 练习 1: C/C++ 文件类型自动命令
> -- 放在 autocmds 模块中，或直接放在 init.lua
>
> local augroup = vim.api.nvim_create_augroup
> local autocmd = vim.api.nvim_create_autocmd
>
> local cpp_group = augroup("CppSettings", { clear = true })
>
> autocmd("FileType", {
>     group = cpp_group,
>     pattern = { "c", "cpp", "h", "hpp" },
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
> - `pattern` 是 table 时匹配多个文件扩展名。Neovim 的 `FileType` 事件使用文件类型名（不含 `.`），即 `"c"` 而非 `"*.c"`。

> [!tip]- 练习 2 参考答案
> ```lua
> -- 练习 2: 复制后高亮复制区域（TextYankPost 事件）
> local yank_group = vim.api.nvim_create_augroup("YankHighlight", { clear = true })
>
> vim.api.nvim_create_autocmd("TextYankPost", {
>     group = yank_group,
>     callback = function()
>         -- vim.highlight.on_yank 是高亮 yank 区域的便捷函数
>         -- higroup: 使用哪个高亮组（IncSearch 是内置的反色高亮）
>         -- timeout: 高亮持续时间（毫秒），150ms 足够亮一下
>         -- on_macro: 宏执行时是否也触发（false 避免宏播放时干扰）
>         vim.highlight.on_yank({
>             higroup = "IncSearch",
>             timeout = 150,
>             on_macro = false,
>         })
>     end,
> })
> ```
>
> **核心 API：** `vim.highlight.on_yank()` 是 Neovim 0.10+ 提供的一站式方案，内部使用 `vim.highlight.range()` 在 yank 区域创建临时高亮。无需手动保存/恢复光标，也无需手动清除——`timeout` 到期后自动消失。

> [!tip]- 练习 3 参考答案（可选）
> 在 Neovim 中逐步操作：
>
> ```vim
> " 步骤 1: 创建一个简单的调试自动命令
> :lua vim.api.nvim_create_autocmd("BufEnter", { callback = function() print("进入: " .. vim.fn.expand("%")) end })
>
> " 步骤 2: 切换几次缓冲区，然后查看输出
> :messages
>
> " 步骤 3: 查看所有 BufEnter 自动命令（会看到刚才创建的匿名 autocmd）
> :autocmd BufEnter
>
> " 步骤 4: 如果之前按照示例创建了 GeneralSettings，清除它
> :lua vim.api.nvim_del_augroup_by_name("GeneralSettings")
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

---

## 常见陷阱

- **忘记 `clear = true`**：重载配置时旧的自动命令不会被清除，导致累积执行。这是最难排查的配置 bug 之一。**每个 augroup 都加 `clear = true`**。
- **在自动命令中修改缓冲区选项用 `vim.bo` 而非 `vim.opt`**：`vim.opt_local` 或 `vim.bo[args.buf]` 只影响当前缓冲区，不会意外修改全局设置。
- **`TextYankPost` 在每次 yank 时触发**：注意性能，回调应该轻量。
- **`BufWritePre` 中使用 `vim.lsp.buf.format()` 需要先确保 LSP 已附着**：否则静默失败。
- **自动命令回调中的 `args` 参数**：`args.buf`（缓冲区编号）、`args.file`（文件名）、`args.match`（匹配的模式）等信息很实用。
- **`InsertLeave` 触发保存可能导致意外写入**：检查 `vim.bo.buftype == ""` 排除特殊缓冲区（如文件树、终端）。
