---
title: "03 — Lua 函数、闭包与模块系统"
updated: 2026-06-18
---

# 03 — Lua 函数、闭包与模块系统

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 65 分钟
> 前置知识: [[02-lua-tables]]

---

## 1. 函数基础

### 函数声明

```lua
-- 标准声明
local function add(a, b)
    return a + b
end

-- 匿名函数赋值（等价）
local add = function(a, b)
    return a + b
end

-- table 方法
local math_ops = {}
function math_ops.add(a, b)
    return a + b
end

-- 冒号语法糖（隐式 self）
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

```lua
local function get_position()
    return 10, 20, 0
end

local x, y, z = get_position()
print(x, y, z)  -- 10  20  0

local only_x = get_position()  -- only_x = 10

-- Neovim 经典例子
-- local row, col = unpack(vim.api.nvim_win_get_cursor(0))
```

### 可变参数 `...`

```lua
local function join(separator, ...)
    return table.concat({ ... }, separator)
end

print(join(", ", "a", "b", "c"))  -- "a, b, c"

-- 转发可变参数
local function wrapper(fn, ...)
    print("调用前")
    local result = fn(...)
    print("调用后")
    return result
end
```

### 回调函数

```lua
local function execute_with_log(fn, name)
    print("[开始] " .. name)
    local ok, err = pcall(fn)
    if not ok then
        print("[错误] " .. name .. ": " .. tostring(err))
    else
        print("[完成] " .. name)
    end
end

execute_with_log(function()
    print("执行中...")
end, "测试任务")
```

---

## 2. 闭包深度

### 词法作用域与 upvalue

函数可以访问定义它时所在作用域的局部变量，这些变量称为 **upvalue**。

```lua
local function make_multiplier(factor)
    return function(x)
        return x * factor
    end
end

local double = make_multiplier(2)
local triple = make_multiplier(3)

print(double(5))  -- 10
print(triple(5))  -- 15
```

### 闭包工厂

```lua
local function make_counter(start_value)
    local n = start_value or 0
    return function()
        n = n + 1
        return n
    end
end

local c1 = make_counter(0)
local c2 = make_counter(100)

print(c1())  -- 1
print(c1())  -- 2
print(c2())  -- 101
```

### 循环中的闭包陷阱

```lua
local t = {}
for i = 1, 3 do
    t[i] = function()
        return i
    end
end

print(t[1]())  -- 1
print(t[2]())  -- 2
print(t[3]())  -- 3
```

> [!IMPORTANT]
> 在 Lua 5.1 / LuaJIT 中，每个迭代都会创建新的局部变量 `i`，所以输出是 `1, 2, 3`。但为了跨版本兼容和可读性，建议显式创建副本：

```lua
local t = {}
for i = 1, 3 do
    local captured = i
    t[i] = function()
        return captured
    end
end
```

### 用闭包实现记忆化

```lua
local function memoize(fn)
    local cache = {}
    return function(...)
        local key = table.concat({ ... }, "\0")
        if cache[key] == nil then
            cache[key] = fn(...)
        end
        return cache[key]
    end
end

local fib = memoize(function(n)
    if n <= 1 then return n end
    return fib(n - 1) + fib(n - 2)
end)

print(fib(30))  -- 832040
```

---

## 3. 高阶函数

### map / filter / reduce

```lua
local function map(t, fn)
    local result = {}
    for i, v in ipairs(t) do
        result[i] = fn(v)
    end
    return result
end

local function filter(t, pred)
    local result = {}
    for _, v in ipairs(t) do
        if pred(v) then
            result[#result + 1] = v
        end
    end
    return result
end

local function reduce(t, fn, init)
    local acc = init
    for _, v in ipairs(t) do
        acc = fn(acc, v)
    end
    return acc
end

local nums = { 1, 2, 3, 4, 5 }
local doubled = map(nums, function(x) return x * 2 end)
local evens = filter(nums, function(x) return x % 2 == 0 end)
local sum = reduce(nums, function(a, b) return a + b end, 0)

print(table.concat(doubled, ", "))  -- 2, 4, 6, 8, 10
print(table.concat(evens, ", "))    -- 2, 4
print(sum)                            -- 15
```

> [!TIP]
> Neovim 中可用 `vim.iter` 完成类似操作：
> ```lua
> local doubled = vim.iter({1,2,3,4,5}):map(function(x) return x * 2 end):totable()
> ```

### `table.sort` 与比较函数

```lua
local scores = {
    { name = "Alice", score = 85 },
    { name = "Bob", score = 92 },
    { name = "Carol", score = 78 },
}

 table.sort(scores, function(a, b)
    return a.score > b.score
end)

for _, entry in ipairs(scores) do
    print(entry.name, entry.score)
end
-- Bob 92, Alice 85, Carol 78
```

---

## 4. 模块系统

### `require` 基础

```lua
-- ~/.config/nvim/
--   init.lua
--   lua/
--     config/
--       options.lua   ← require("config.options")
--       keymaps.lua   ← require("config.keymaps")

require("config.options")
require("config.keymaps")
```

模块文件返回一个 table：

```lua
-- lua/config/options.lua
local M = {}

M.setup = function()
    vim.opt.number = true
    vim.opt.tabstop = 4
end

return M
```

### 模块系统三种范式

#### 范式 1：`module(...)`（已弃用）

```lua
module("old_utils", package.seeall)

function add(a, b)
    return a + b
end
```

> [!WARNING]
> `module(...)` 会污染全局环境，已被弃用。**新代码不要用它**。

#### 范式 2：`local M = {}; return M`（推荐）

```lua
-- math_utils.lua
local M = {}

function M.add(a, b)
    return a + b
end

function M.multiply(a, b)
    return a * b
end

local function private_helper(x)
    return x * 2
end

function M.double(x)
    return private_helper(x)
end

return M
```

```lua
-- main.lua
local math_utils = require("math_utils")
print(math_utils.add(2, 3))
print(math_utils.double(5))
```

#### 范式 3：`package.path` 与 `require` 查找机制

`require("foo.bar")` 的查找规则：

1. 把点号替换为路径分隔符：`foo/bar`
2. 按 `package.path` 查找 `foo/bar.lua`、`foo/bar/init.lua`
3. 找到后加载并缓存到 `package.loaded`

```lua
print(package.path)
package.path = package.path .. ";./my_modules/?.lua"
```

### Neovim 中的 `require` 与 `runtimepath`

```text
~/.config/nvim/
  init.lua
  lua/
    myplugin.lua          ← require("myplugin")
    myplugin/
      init.lua            ← 或 require("myplugin")
```

```lua
require("myplugin")  -- 加载 lua/myplugin.lua 或 lua/myplugin/init.lua
```

---

## 5. vim.uv / vim.loop 简介

`vim.uv` 是 Neovim 对 libuv 的绑定，用于文件系统、定时器、进程等异步操作。`vim.loop` 是旧名，已弃用但兼容。

### 同步文件状态

```lua
local stat = vim.uv.fs_stat(vim.fn.stdpath("config") .. "/init.lua")
if stat then
    print("文件大小:", stat.size)
end
```

### 异步定时器

```lua
local timer = vim.uv.new_timer()
timer:start(1000, 500, vim.schedule_wrap(function()
    print("tick")
end))

-- 停止：timer:stop(); timer:close()
```

> [!IMPORTANT]
> libuv 回调在后台线程运行，调用 `vim.api` 或修改 UI 时必须用 `vim.schedule_wrap` 回到主事件循环。

### 常用操作对比

| 操作 | `vim.uv` | 替代 |
|------|---------|------|
| 文件状态 | `vim.uv.fs_stat(path)` | `vim.fn.getftime()` |
| 创建目录 | `vim.uv.fs_mkdir(path, 448)` | `vim.fn.mkdir()` |
| 定时器 | `vim.uv.new_timer()` | `vim.defer_fn()` |
| 执行命令 | `vim.system(cmd):wait()` | `vim.fn.system()` |

---

## 6. 代码示例

```lua
-- main.lua
local math_utils = require("math_utils")

print("add(3, 4) = " .. math_utils.add(3, 4))
print("double(5) = " .. math_utils.double(5))

-- 闭包计数器
local counter = (function()
    local n = 0
    return function()
        n = n + 1
        return n
    end
end)()

print("counter:", counter())
print("counter:", counter())

-- map 示例
local nums = { 1, 2, 3, 4, 5 }
local doubled = {}
for i, v in ipairs(nums) do
    doubled[i] = v * 2
end
print("doubled:", table.concat(doubled, ", "))

-- setup() 模式
local function setup_plugin(name, opts)
    print("设置插件: " .. name)
    for key, value in pairs(opts) do
        print("  " .. key .. " = " .. tostring(value))
    end
end

setup_plugin("tokyonight", {
    style = "night",
    transparent = false,
    on_colors = function(colors)
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
double(5) = 10
counter: 1
counter: 2
doubled: 2, 4, 6, 8, 10
设置插件: tokyonight
  style = night
  transparent = false
```

---

## 7. 练习

### 练习 1: 多返回值
写一个函数 `minmax(t)`，接收一个数字数组，返回最小值和最大值。

```lua
local min, max = minmax({3, 1, 4, 1, 5, 9})
print(min, max)  -- 1 9
```

### 练习 2: 模块拆分
将练习 1 的 `minmax` 函数放到模块 `stats.lua` 中，在 `test_stats.lua` 中 `require` 并使用。再添加 `average` 函数。

### 练习 3: 用闭包实现记忆化
写一个 `memoize(fn)` 函数，返回记忆化版本。测试计算阶乘 `factorial(10)`。

### 练习 4: 模拟插件配置（可选）
写一个函数 `create_autocmd(events, opts)`，模拟 `vim.api.nvim_create_autocmd`：

```lua
create_autocmd({ "BufWritePre", "BufRead" }, {
    pattern = "*.lua",
    callback = function()
        print("检测到 Lua 文件")
    end,
})
```

## 7.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> local function minmax(t)
>     local min_val, max_val = t[1], t[1]
>     for i = 2, #t do
>         local v = t[i]
>         if v < min_val then min_val = v end
>         if v > max_val then max_val = v end
>     end
>     return min_val, max_val
> end
>
> local min, max = minmax({ 3, 1, 4, 1, 5, 9 })
> print(min, max)  -- 1  9
> ```

> [!tip]- 练习 2 参考答案
> ```lua
> -- stats.lua
> local M = {}
>
> function M.minmax(t)
>     local min_val, max_val = t[1], t[1]
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
> -- test_stats.lua
> local stats = require("stats")
> local data = { 3, 1, 4, 1, 5, 9 }
> local min, max = stats.minmax(data)
> print("最小值: " .. min .. ", 最大值: " .. max)
> print("平均值: " .. stats.average(data))
> ```

> [!tip]- 练习 3 参考答案
> ```lua
> local function memoize(fn)
>     local cache = {}
>     return function(...)
>         local key = table.concat({ ... }, "\0")
>         if cache[key] == nil then
>             cache[key] = fn(...)
>         end
>         return cache[key]
>     end
> end
>
> local factorial = memoize(function(n)
>     if n <= 1 then return 1 end
>     return n * factorial(n - 1)
> end)
>
> print(factorial(10))  -- 3628800
> print(factorial(10))  -- 3628800（缓存）
> ```

> [!tip]- 练习 4 参考答案（可选）
> ```lua
> local function create_autocmd(events, opts)
>     print("[自动命令] 事件: " .. table.concat(events, ", "))
>     if opts.pattern then
>         if type(opts.pattern) == "table" then
>             print("  匹配: " .. table.concat(opts.pattern, ", "))
>         else
>             print("  匹配: " .. opts.pattern)
>         end
>     end
>     if opts.callback then
>         print("  回调: 已设置")
>     end
> end
>
> create_autocmd({ "BufWritePre", "BufRead" }, {
>     pattern = "*.lua",
>     callback = function() print("Lua file") end,
> })
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 8. 扩展阅读

- [Programming in Lua — Functions](https://www.lua.org/pil/5.html)
- [Programming in Lua — Closures](https://www.lua.org/pil/6.1.html)
- [Programming in Lua — Modules](https://www.lua.org/pil/15.html)
- [Neovim Lua Guide — require 和模块](https://neovim.io/doc/user/lua-guide.html#lua-guide-modules)
- [Neovim Lua 标准库 — vim.uv](https://neovim.io/doc/user/lua-ref.html#vim.uv)
- [Lua 5.1 参考手册 — 函数](https://www.lua.org/manual/5.1/manual.html#2.5.9)

---

## 常见陷阱

- **函数是值，注意引用**：`local gsub = string.gsub` 后不能再用冒号语法，需显式传 `self`。
- **`require` 有缓存**：同一个模块只加载一次。修改返回的 table 会影响所有引用方。
- **`pcall` 吞掉错误**：不检查返回值等于悄悄忽略错误。
- **闭包循环变量在 LuaJIT 中安全**：每个迭代有独立局部变量，但建议显式 `local captured = i`。
- **`memoize` 缓存键冲突**：用分隔符（如 `"\0"`）避免 `(1, 23)` 和 `(12, 3)` 冲突。
- **`vim.uv` 回调需要 `vim.schedule_wrap`**：否则可能触发线程安全问题。
- **不要混淆 `vim.loop` 与 `vim.uv`**：`vim.loop` 是旧名，新代码统一用 `vim.uv`。
- **回调地狱在 Neovim 配置中不存在**：配置通常只嵌套 2-3 层。
