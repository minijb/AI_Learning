---
title: "01 — Lua 快速入门：类型与控制流"
updated: 2026-06-05
---

# 01 — Lua 快速入门：类型与控制流

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 45 分钟
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
```

**运行方式:**
```bash
# Windows（假设 Lua 已安装）
lua test_basics.lua

# 或直接在 Neovim 中运行
nvim -l test_basics.lua
```

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

### 练习 3: 循环计算（可选）
用 for 循环计算 1 到 100 的累加和，打印结果。


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

> [!tip]- 练习 3 参考答案（可选）
> ```lua
> -- exercise3_sum.lua
> local sum = 0
> for i = 1, 100 do
>     sum = sum + i
> end
> print("1 到 100 的累加和: " .. sum)  -- 输出 5050
> ```
>
> **验证：** 等差数列求和公式 (1+100)×100/2 = 5050，与循环结果一致。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [Lua 5.1 参考手册 — 类型与值](https://www.lua.org/manual/5.1/manual.html#2)
- [Programming in Lua — 类型与值](https://www.lua.org/pil/2.html)
- [LuaJIT 性能特性](https://luajit.org/performance.html)

---

## 常见陷阱

- **忘记 `then`**：Lua 的 `if` 语句必须写 `then`，`elseif` 也必须有 `then`。
- **0 和空字符串为真**：与 C/Python/JS 不同，Lua 只有 `nil` 和 `false` 是假。如果来自 C 语言背景，这点最容易踩坑。
- **全局变量污染**：忘记写 `local` 会创建全局变量。在 Neovim 配置中这是严重的错误。
- **`~=` 是不等号**：不是 `!=`。
- **没有 `++` / `+=`**：Lua 没有自增/自减运算符，必须写 `x = x + 1`。
- **数组索引从 1 开始**：`table[1]` 是第一个元素，`table[0]` 不会自动获取最后一个。
