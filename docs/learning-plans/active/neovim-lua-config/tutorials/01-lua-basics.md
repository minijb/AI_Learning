---
title: "01 — Lua 快速入门：类型、控制流与 LuaJIT 扩展"
updated: 2026-06-18
---

# 01 — Lua 快速入门：类型、控制流与 LuaJIT 扩展

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 55 分钟
> 前置知识: 任意编程语言基础（变量、函数、控制流）

---

## 1. 概念讲解

### 为什么需要 Lua？

Neovim 从 0.5 版本起将 Lua 作为一等配置语言。与旧式的 Vimscript 相比，Lua 配置：
- 结构清晰，支持真正的模块化
- 性能更好（LuaJIT 执行速度远超 Vimscript）
- 生态活跃，几乎所有新插件都用 Lua 编写

你不需要成为 Lua 专家——**掌握 Neovim 配置中常用的 20% Lua 语法就够用**。

### Lua 的基本类型

Lua 有 8 种基本类型，Neovim 配置中最常用的是这几种：

| 类型 | 说明 | 示例 |
|------|------|------|
| `nil` | 空值，表示"无" | `nil` |
| `boolean` | 布尔值 | `true`, `false` |
| `number` | 数字（LuaJIT 中为双精度浮点） | `42`, `3.14` |
| `string` | 字符串 | `"hello"`, `'world'` |
| `table` | 唯一的复合数据结构 | `{1, 2, 3}`, `{a = 1}` |
| `function` | 函数是一等值 | `function() end` |

### 变量与赋值

```lua
-- 默认全局变量（在 Neovim 配置中避免使用）
name = "Neovim"

-- local 声明局部变量（永远在配置文件中用 local）
local version = "0.10"
local is_awesome = true
local count = 42

-- 多重赋值（常用于交换）
local a, b = 1, 2
a, b = b, a  -- a=2, b=1
```

> [!IMPORTANT]
> Neovim 配置文件中**永远使用 `local`**。全局变量会污染 Neovim 的全局命名空间，可能导致难以排查的 bug。

### 字符串

```lua
local s1 = "hello"
local s2 = 'world'

-- 多行字符串用 [[ ]]
local multiline = [[
第一行
第二行
第三行
]]

-- 字符串拼接用 ..
local greeting = s1 .. " " .. s2  -- "hello world"

-- 字符串长度用 #
local len = #greeting  -- 11
```

### 控制流

```lua
-- if/elseif/else（注意 then 关键字）
local x = 10
if x > 5 then
    print("大")
elseif x > 0 then
    print("中")
else
    print("小")
end

-- Lua 中只有 nil 和 false 为假，0 和空字符串 "" 都为真
if 0 then print("0 是真") end      -- 会打印
if "" then print("空字符串是真") end -- 会打印

-- for 循环：数值型
for i = 1, 5 do
    print(i)  -- 1 2 3 4 5
end

-- for 循环：带步长
for i = 1, 10, 2 do
    print(i)  -- 1 3 5 7 9
end

-- while 循环
local n = 3
while n > 0 do
    print(n)
    n = n - 1
end
```

### 注释

```lua
-- 单行注释

--[[
多行注释
可以跨越多行
--]]
```

### LuaJIT 扩展语法（Neovim 0.12+ 默认运行时）

Neovim 0.12 的 Lua 运行时是 **LuaJIT 2.1**，它在兼容 Lua 5.1 的基础上增加了若干扩展。这些扩展在配置中经常用到。

#### 整数除法 `//`

Lua 5.1 只有 `/` 浮点除法；LuaJIT 支持 5.3 的整数除法 `//`。

```lua
local a = 17
local b = 5

print(a / b)   -- 3.4（普通除法，浮点结果）
print(a // b)  -- 3（整数除法，向下取整）
print(a % b)   -- 2（取余）
```

> [!NOTE]
> 与 Lua 5.3+ 不同，LuaJIT **没有独立的整数类型**，所有 number 都是 IEEE-754 double。因此 `//` 的结果仍然是 double，只是小数部分已被截断。

#### `goto` / `::label::` 实现 `continue`

Lua 5.1 / LuaJIT 原生没有 `continue` 关键字，但 LuaJIT 支持 `goto` 和标签。这是 Neovim 配置中实现 `continue` 语义的标准写法。

```lua
for i = 1, 10 do
    if i % 2 == 0 then
        goto continue  -- 跳过偶数
    end
    print(i)  -- 只打印奇数: 1 3 5 7 9
    ::continue::
end
```

使用约定：
- 标签名通常就叫 `continue`，一看就懂
- `goto` 不能跳出或跳入函数
- `goto` 不能跳入局部变量的作用域

#### `bit` 模块位运算

LuaJIT 提供 `bit` 模块做位运算。这与 Lua 5.3+ 的 `&`、`|`、`~`、`<<` 位运算符**不兼容**——LuaJIT 不支持那些符号运算符。

```lua
local bit = require("bit")

local x = 0b1100  -- 12
local y = 0b1010  -- 10

print(bit.band(x, y))  -- 8  (0b1000，按位与)
print(bit.bor(x, y))   -- 14 (0b1110，按位或)
print(bit.bxor(x, y))  -- 6  (0b0110，按位异或)
print(bit.lshift(x, 2)) -- 48 (0b110000，左移 2 位)
print(bit.rshift(x, 2)) -- 3  (0b11，右移 2 位)
print(bit.bnot(x))     -- -13（按位非）
```

> [!IMPORTANT]
> 在 Neovim 配置里写位运算时，必须写 `bit.band(...)` 这类形式。直接用 `x & y` 在 LuaJIT 下会报语法错误。

### 数字与字符串进阶

#### `tonumber` / `tostring`

```lua
local n = tonumber("42")       -- 42（number）
local fail = tonumber("hello") -- nil（无法转换）
local hex = tonumber("FF", 16) -- 255（指定进制）

local s = tostring(42)         -- "42"
local b = tostring(true)       -- "true"
```

#### 字符串格式化 `string.format`

`string.format` 是 Neovim 配置中拼接字符串的利器，比反复用 `..` 更清晰。

```lua
local name = "Neovim"
local version = 0.12
local plugins = 42

print(string.format("%s v%.2f with %d plugins", name, version, plugins))
-- 输出: Neovim v0.12 with 42 plugins

-- 常用占位符
-- %s  字符串
-- %d  整数
-- %f  浮点数（%.2f 保留两位小数）
-- %x  十六进制
-- %q  自动加引号并转义
```

#### 模式匹配 `string.match` / `string.gmatch`

Lua 的模式匹配不是完整的正则表达式，但非常轻量，足以处理配置文件中的常见提取任务。

```lua
local path = "nvim/lua/config/options.lua"

-- 提取文件名
local filename = string.match(path, "([^/]+)$")
print(filename)  -- options.lua

-- 提取扩展名
local ext = string.match(path, "%.([^%.]+)$")
print(ext)       -- lua

-- gmatch：全局匹配，可迭代
local text = "foo=1, bar=2, baz=3"
for key, val in string.gmatch(text, "(%w+)=(%d+)") do
    print(key, val)
end
-- 输出:
-- foo 1
-- bar 2
-- baz 3
```

> [!TIP]
> 常见模式字符：
> - `.` 任意字符
> - `%d` 数字，`%w` 字母数字，`%s` 空白
> - `+` 1 个或多个，`*` 0 个或多个，`?` 0 或 1 个
> - `^` 开头，`$` 结尾
> - 用 `()` 捕获分组

### 多返回值与变长参数

#### 多返回值

Lua 函数可以自然返回多个值，调用处用多重赋值接收。

```lua
local function split_name(fullname)
    local first, last = string.match(fullname, "(%S+)%s+(%S+)")
    return first, last
end

local first, last = split_name("John Doe")
print(first, last)  -- John  Doe

-- 只取第一个返回值
local only_first = split_name("Jane Doe")
print(only_first)   -- Jane
```

> [!WARNING]
> 当函数调用位于表达式中间时，只有第一个返回值会被使用。例如 `print(split_name("A B"))` 只输出 `A`。

#### 变长参数 `...`

```lua
local function sum(...)
    local total = 0
    for _, v in ipairs({ ... }) do
        total = total + v
    end
    return total
end

print(sum(1, 2, 3, 4))  -- 10

-- 用 select 获取参数个数
local function count_args(...)
    return select("#", ...)
end

print(count_args("a", "b", "c"))  -- 3
```

`select` 的另一个用法是按索引取参数：

```lua
local function first_and_rest(...)
    local first = select(1, ...)
    local n = select("#", ...)
    return first, n - 1
end

print(first_and_rest("x", "y", "z"))  -- x  2
```

---

## 2. 代码示例

创建文件 `test_basics.lua`，用 `lua` 命令运行：

```lua
-- test_basics.lua
local name = "Neovim User"
local count = 3

-- 字符串拼接
local message = "Hello, " .. name .. "! You have " .. count .. " messages."

print(message)

-- 条件判断
if count > 5 then
    print("很多消息")
elseif count > 0 then
    print("有一些消息")
else
    print("没有消息")
end

-- for 循环
print("计数:")
for i = 1, count do
    print("  " .. i)
end

-- 验证 0 和 "" 的真值
print("0 是:", 0 and "真" or "假")
print("空字符串是:", "" and "真" or "假")

-- LuaJIT 扩展：goto 实现 continue
print("奇数:")
for i = 1, 10 do
    if i % 2 == 0 then goto continue end
    print("  " .. i)
    ::continue::
end

-- 整数除法
print("17 // 5 =", 17 // 5)

-- bit 位运算
local bit = require("bit")
print("bit.band(12, 10) =", bit.band(12, 10))

-- string.format
print(string.format("格式化: %s 有 %d 条消息", name, count))

-- 多返回值
local function bounds(t)
    local min, max = t[1], t[1]
    for i = 2, #t do
        if t[i] < min then min = t[i] end
        if t[i] > max then max = t[i] end
    end
    return min, max
end

local lo, hi = bounds({ 4, 1, 7, 3, 9 })
print("最小值:", lo, "最大值:", hi)
```

**运行方式:**
```bash
# 独立 Lua 解释器（假设 LuaJIT 或 Lua 5.2+）
lua test_basics.lua

# 或直接在 Neovim 中运行（推荐，验证 Neovim 环境）
nvim -l test_basics.lua
```

> [!NOTE]
> 本教程代码需要 **Neovim 0.12.3+** 的 LuaJIT 运行时，或兼容 LuaJIT 扩展的独立解释器。

**预期输出:**
```text
Hello, Neovim User! You have 3 messages.
有一些消息
计数:
  1
  2
  3
0 是: 真
空字符串是: 真
奇数:
  1
  3
  5
  7
  9
17 // 5 = 3
bit.band(12, 10) = 8
格式化: Neovim User 有 3 条消息
最小值: 1 最大值: 9
```

---

## 3. 练习

### 练习 1: 变量与控制流
写一个 Lua 脚本，声明一个数字变量 `score`，然后：
- 如果 `score >= 90`，输出 "优秀"
- 如果 `score >= 60`，输出 "及格"
- 否则输出 "不及格"

### 练习 2: 字符串操作
写一个脚本，声明三个字符串变量 `first`、`middle`、`last`，用 `..` 拼接成完整姓名（中间用空格分隔），并打印其长度。

### 练习 3: 用 `goto` 实现 continue
写一个 `for i = 1, 20` 的循环，跳过所有 3 的倍数，打印其余数字。

### 练习 4: 字符串格式化（可选）
给定一个文件路径列表，用 `string.format` 和 `string.match` 打印每个文件的扩展名，格式为 `"file: <name>, ext: <ext>"`。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> -- exercise1_score.lua
> local score = 85  -- 可修改此值测试不同分支
>
> if score >= 90 then
>     print("优秀")
> elseif score >= 60 then
>     print("及格")
> else
>     print("不及格")
> end
> ```
>
> **关键点：** Lua 中 `elseif` 是一个单词（不是 `else if`），每个条件分支都需要 `then`。

> [!tip]- 练习 2 参考答案
> ```lua
> -- exercise2_name.lua
> local first = "张"
> local middle = "伟"
> local last = "明"
>
> -- 拼接：用 .. 运算符，中间加空格
> local full_name = first .. " " .. middle .. " " .. last
> print("完整姓名: " .. full_name)
> print("长度: " .. #full_name)
> -- #full_name 计算的是字节数，中文字符在 UTF-8 下每个占 3 字节
> ```
>
> **注意：** `#` 运算符对 UTF-8 中文字符串返回的是**字节数**而非字符数，这是 Lua 字符串的已知限制。如需正确计算 Unicode 字符数，在 Neovim 中可使用 `vim.fn.strchars()`。

> [!tip]- 练习 3 参考答案
> ```lua
> -- exercise3_goto_continue.lua
> for i = 1, 20 do
>     if i % 3 == 0 then
>         goto continue
>     end
>     print(i)
>     ::continue::
> end
> ```
>
> **关键点：** `goto` 跳转到 `::continue::` 标签后，循环继续下一次迭代。标签必须写在循环体内、且在 `goto` 之后（Lua 不允许向前跳入局部变量作用域）。

> [!tip]- 练习 4 参考答案（可选）
> ```lua
> -- exercise4_file_ext.lua
> local paths = {
>     "init.lua",
>     "config/options.lua",
>     "README.md",
>     "plugin/test.vim",
> }
>
> for _, path in ipairs(paths) do
>     local name = string.match(path, "([^/]+)$")
>     local ext = string.match(name, "%.([^%.]+)$") or "none"
>     print(string.format("file: %s, ext: %s", name, ext))
> end
> ```
>
> **关键点：** 先用 `([^/]+)$` 提取最后一个斜杠后的文件名，再用 `%.([^%.]+)$` 提取扩展名。`%.` 匹配字面量点号，因为 `.` 在 Lua 模式中是特殊字符。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Lua 5.1 参考手册 — 类型与值](https://www.lua.org/manual/5.1/manual.html#2)
- [Programming in Lua — 类型与值](https://www.lua.org/pil/2.html)
- [LuaJIT 扩展语法文档](https://luajit.org/extensions.html)
- [LuaJIT 位运算模块 bit](https://luajit.org/ext_bit.html)
- [Programming in Lua — 模式匹配](https://www.lua.org/pil/20.2.html)

---

## 常见陷阱

- **忘记 `then`**：Lua 的 `if` 语句必须写 `then`，`elseif` 也必须有 `then`。
- **0 和空字符串为真**：与 C/Python/JS 不同，Lua 只有 `nil` 和 `false` 是假。如果来自 C 语言背景，这点最容易踩坑。
- **全局变量污染**：忘记写 `local` 会创建全局变量。在 Neovim 配置中这是严重的错误。
- **`~=` 是不等号**：不是 `!=`。
- **没有 `++` / `+=`**：Lua 没有自增/自减运算符，必须写 `x = x + 1`。
- **数组索引从 1 开始**：`table[1]` 是第一个元素，`table[0]` 不会自动获取最后一个。
- **LuaJIT 没有 `&` / `|` 位运算符**：位运算必须走 `bit` 模块。
- **`goto` 不能跳入局部变量作用域**：如果标签后面定义了新的 `local` 变量，`goto` 跳到该标签前必须确保不会跨越那个局部变量。
- **表达式中多返回值被截断**：`local x = f()` 只取第一个返回值；要完整接收必须写成 `local a, b, c = f()`。
