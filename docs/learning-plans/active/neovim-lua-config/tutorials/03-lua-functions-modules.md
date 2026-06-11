---
title: "03 — Lua 函数与模块系统"
updated: 2026-06-05
---

# 03 — Lua 函数与模块系统

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 50 分钟
> 前置知识: 02-lua-tables（table 操作）

---

## 1. 概念讲解

### 函数声明

Lua 函数有多种声明方式：

```lua
-- 方式 1: 标准声明
local function add(a, b)
    return a + b
end

-- 方式 2: 匿名函数赋值（等价于方式 1）
local add = function(a, b)
    return a + b
end

-- 方式 3: 作为 table 的方法
local math_ops = {}
function math_ops.add(a, b)
    return a + b
end

-- 方式 4: 冒号语法糖（隐式传递 self）
local Counter = {}
function Counter:new(start)
    local obj = { count = start or 0 }
    setmetatable(obj, self)
    self.__index = self
    return obj
end
function Counter:increment()
    self.count = self.count + 1
    return self.count
end
```

### 多返回值

Lua 函数可以返回多个值——这是 Neovim API 中常用的模式：

```lua
local function get_position()
    return 10, 20, 0  -- x, y, z
end

local x, y, z = get_position()
print(x, y, z)  -- 10  20  0

-- 只取第一个
local only_x = get_position()  -- only_x = 10

-- Neovim API 经典例子：获取光标位置
-- local row, col = unpack(vim.api.nvim_win_get_cursor(0))
```

### 可变参数 `...`

```lua
local function join(separator, ...)
    local args = { ... }  -- 将可变参数打包成 table
    return table.concat(args, separator)
end

print(join(", ", "a", "b", "c"))  -- "a, b, c"

-- 转发可变参数
local function wrapper(fn, ...)
    print("调用前")
    local result = fn(...)  -- 原样转发所有参数
    print("调用后")
    return result
end
```

### 回调函数（在 Neovim 配置中无处不在）

```lua
-- 将函数作为参数传递
local function execute_with_log(fn, name)
    print("[开始] " .. name)
    local ok, err = pcall(fn)  -- pcall: 安全调用，捕获错误
    if not ok then
        print("[错误] " .. name .. ": " .. tostring(err))
    else
        print("[完成] " .. name)
    end
end

execute_with_log(function()
    -- 这是匿名回调
    print("执行中...")
end, "测试任务")
```

### 模块系统 `require`

Neovim 用 `require` 加载 Lua 模块：

```lua
-- Neovim 配置文件中的典型结构：
-- ~/.config/nvim/
--   init.lua          ← 入口
--   lua/
--     config/
--       options.lua   ← 定义模块 "config.options"
--       keymaps.lua   ← 定义模块 "config.keymaps"
--       plugins/
--         lsp.lua     ← 定义模块 "config.plugins.lsp"

-- 在 init.lua 中加载：
require("config.options")  -- 加载 lua/config/options.lua
require("config.keymaps")  -- 加载 lua/config/keymaps.lua
```

模块文件返回一个 table：

```lua
-- lua/config/options.lua
local M = {}  -- 惯例：M 代表 Module

M.setup = function()
    vim.opt.number = true
    vim.opt.tabstop = 4
end

return M
```

```lua
-- 在 init.lua 中使用：
local options = require("config.options")
options.setup()
```

---

## 2. 代码示例

创建以下文件结构演示模块系统：

```lua
-- math_utils.lua（模块文件）
local M = {}

function M.add(a, b)
    return a + b
end

function M.multiply(a, b)
    return a * b
end

-- 私有函数（不导出）
local function private_helper(x)
    return x * 2
end

function M.double(x)
    return private_helper(x)
end

return M
```

```lua
-- main.lua（入口文件）
local math_utils = require("math_utils")

print("add(3, 4) = " .. math_utils.add(3, 4))
print("multiply(3, 4) = " .. math_utils.multiply(3, 4))
print("double(5) = " .. math_utils.double(5))

-- 模拟 Neovim 插件配置模式
local function setup_plugin(name, opts)
    print("设置插件: " .. name)
    for key, value in pairs(opts) do
        print("  " .. key .. " = " .. tostring(value))
    end
end

-- setup() 模式：传递 opts table
setup_plugin("tokyonight", {
    style = "night",
    transparent = false,
    on_colors = function(colors)  -- 回调函数作为选项值
        colors.hint = "#ff0000"
    end,
})
```

**运行方式:**
```bash
lua main.lua
```

**预期输出:**
```text
add(3, 4) = 7
multiply(3, 4) = 12
double(5) = 10
设置插件: tokyonight
  style = night
  transparent = false
```

---

## 3. 练习

### 练习 1: 多返回值
写一个函数 `minmax(t)`，接收一个数字数组，返回最小值和最大值。练习用多返回值接收。

```lua
local min, max = minmax({3, 1, 4, 1, 5, 9})
print(min, max)  -- 应输出 1 9
```

### 练习 2: 模块拆分
将练习 1 的 `minmax` 函数放到一个模块 `stats.lua` 中，在另一个文件 `test_stats.lua` 中 `require` 并使用它。再添加一个 `average` 函数。

### 练习 3: 模拟插件配置（可选）
写一个函数 `create_autocmd(events, opts)`，接受事件列表和选项 table，打印将要创建的自动命令。这模拟了 `vim.api.nvim_create_autocmd` 的接口：

```lua
create_autocmd({ "BufWritePre", "BufRead" }, {
    pattern = "*.lua",
    callback = function()
        print("检测到 Lua 文件")
    end,
})
```


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> -- exercise1_minmax.lua
> local function minmax(t)
>     -- 用第一个元素初始化 min 和 max
>     local min_val = t[1]
>     local max_val = t[1]
>
>     for i = 2, #t do
>         local v = t[i]
>         if v < min_val then
>             min_val = v
>         end
>         if v > max_val then
>             max_val = v
>         end
>     end
>
>     return min_val, max_val  -- 多返回值
> end
>
> -- 测试：用多返回值接收
> local min, max = minmax({ 3, 1, 4, 1, 5, 9 })
> print(min, max)  -- 1  9
> ```
>
> **设计要点：** 遍历从索引 2 开始（索引 1 已用于初始化），避免无意义的自比较。多返回值在 `return` 语句中用逗号分隔，调用方也用逗号分隔的变量列表接收。

> [!tip]- 练习 2 参考答案
> ```lua
> -- stats.lua（模块文件）
> local M = {}
>
> function M.minmax(t)
>     local min_val = t[1]
>     local max_val = t[1]
>     for i = 2, #t do
>         local v = t[i]
>         if v < min_val then min_val = v end
>         if v > max_val then max_val = v end
>     end
>     return min_val, max_val
> end
>
> function M.average(t)
>     local sum = 0
>     for _, v in ipairs(t) do
>         sum = sum + v
>     end
>     return sum / #t
> end
>
> return M
> ```
>
> ```lua
> -- test_stats.lua（入口文件，与 stats.lua 同目录）
> local stats = require("stats")
>
> local data = { 3, 1, 4, 1, 5, 9 }
>
> local min, max = stats.minmax(data)
> print("最小值: " .. min .. ", 最大值: " .. max)
>
> local avg = stats.average(data)
> print("平均值: " .. avg)  -- 约 3.833
> ```
>
> **关键点：** 模块惯例用 `local M = {}` 收集导出函数，最后 `return M`。`require("stats")` 会自动查找同目录下的 `stats.lua`（Lua 的 `package.path` 默认包含当前目录）。

> [!tip]- 练习 3 参考答案（可选）
> ```lua
> -- exercise3_autocmd.lua
> local function create_autocmd(events, opts)
>     -- 将事件列表转为显示字符串
>     local event_str = table.concat(events, ", ")
>     print("[自动命令] 事件: " .. event_str)
>
>     if opts.pattern then
>         local pattern_val = opts.pattern
>         if type(pattern_val) == "table" then
>             print("  匹配: " .. table.concat(pattern_val, ", "))
>         else
>             print("  匹配: " .. pattern_val)
>         end
>     end
>
>     if opts.callback then
>         print("  回调: 已设置（函数 " .. tostring(opts.callback) .. "）")
>     end
>
>     if opts.group then
>         print("  组: " .. opts.group)
>     end
> end
>
> -- 测试
> create_autocmd({ "BufWritePre", "BufRead" }, {
>     pattern = "*.lua",
>     callback = function()
>         print("检测到 Lua 文件")
>     end,
> })
> ```
>
> **设计要点：** 这是模拟 `vim.api.nvim_create_autocmd` 的接口。真实版本还处理 `group`（自动命令组，用 `vim.api.nvim_create_augroup` 创建）、`once`（一次性触发）、`buffer`（缓冲区局部）等选项。此处简化版演示了如何用 table 传递命名参数——这是 Neovim 配置中最常见的 API 模式。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [Programming in Lua — Functions](https://www.lua.org/pil/5.html)
- [Programming in Lua — Modules](https://www.lua.org/pil/15.html)
- [Neovim Lua Guide — require 和模块](https://neovim.io/doc/user/lua-guide.html#lua-guide-modules)
- [Lua 5.1 参考手册 — 函数](https://www.lua.org/manual/5.1/manual.html#2.5.9)

---

## 常见陷阱

- **函数是值，注意引用**：`local print = vim.print` 是可以的，但 `local gsub = string.gsub` 用冒号语法会丢失 `self`。应该用 `local gsub = string.gsub` 然后显式传 `self`。
- **`require` 有缓存**：同一个模块只加载一次，返回缓存的 table。修改返回的 table 会影响所有 require 该模块的地方——有时是特性，有时是 bug。
- **模块返回值的名字是惯例**：返回 table 是惯例，不是强制。你可以返回函数、数字、任何类型。
- **`pcall` 吞掉错误**：`pcall` 返回 `true/false` + 结果/错误，不检查返回值等于悄悄忽略错误。
- **回调地狱在 Neovim 配置中不存在**：因为配置通常只嵌套 2-3 层，`setup({...})` 模式避免了深度嵌套。
