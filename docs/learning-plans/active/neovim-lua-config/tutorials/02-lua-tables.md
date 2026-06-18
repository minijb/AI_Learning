---
title: "02 — Lua 核心：table、metatable 与 OOP"
updated: 2026-06-18
---

# 02 — Lua 核心：table、metatable 与 OOP

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 70 分钟
> 前置知识: [[01-lua-basics]]

---

## 1. Table 基础

### 为什么 table 这么重要？

Lua 只有一种复合数据结构——**table**。它同时扮演数组、字典、对象三个角色。Neovim 配置中每行代码几乎都在操作 table。

### Table 作为数组

```lua
local plugins = { "telescope", "treesitter", "lsp" }
print(plugins[1])     -- "telescope"
print(#plugins)       -- 3

for i, name in ipairs(plugins) do
    print(i .. ": " .. name)
end

table.insert(plugins, "cmp")
plugins[#plugins + 1] = "which-key"
```

> [!IMPORTANT]
> Lua 数组索引从 **1** 开始。`ipairs` 从 1 遍历到第一个 `nil`。

### Table 作为字典

```lua
local opts = { number = true, tabstop = 4 }
print(opts.number)      -- true
print(opts["number"])   -- true
opts.expandtab = true

for key, value in pairs(opts) do
    print(key .. " = " .. tostring(value))
end
```

**`ipairs` vs `pairs`：**

| 函数 | 遍历范围 | 顺序 | 用途 |
|------|---------|------|------|
| `ipairs(t)` | 连续数字索引 | 有序 | 数组 |
| `pairs(t)` | 所有键值对 | 无序 | 字典 / 混合 table |

### Table 嵌套与常用操作

```lua
local lsp_config = {
    servers = {
        lua_ls = {
            settings = {
                Lua = {
                    runtime = { version = "LuaJIT" },
                    diagnostics = { globals = { "vim" } },
                },
            },
        },
    },
}

print(lsp_config.servers.lua_ls.settings.Lua.runtime.version)  -- "LuaJIT"

local t = { "a", "b", "c" }
local s = table.concat(t, ", ")  -- "a, b, c"
table.remove(t)                  -- 删除末尾
table.remove(t, 1)               -- 删除首位
```

---

## 2. metatable：table 的行为控制器

metatable 让你自定义 table 行为：访问不存在的键、table 相加、打印显示等。

```lua
local t = setmetatable({}, {
    __tostring = function() return "custom table" end
})
print(t)  -- custom table
```

### `setmetatable` / `getmetatable`

```lua
local mt = { __index = { name = "default" } }
local t = setmetatable({}, mt)
print(t.name)                 -- "default"
print(getmetatable(t) == mt)  -- true
```

### 核心元方法

#### `__index`：默认值与继承

```lua
local defaults = { theme = "tokyonight", font_size = 14 }
local user_config = setmetatable({ font_size = 16 }, { __index = defaults })
print(user_config.theme)      -- "tokyonight"
print(user_config.font_size)  -- 16
```

也可以是函数：

```lua
local t = setmetatable({}, {
    __index = function(_, key)
        print("missing: " .. tostring(key))
        return nil
    end
})
print(t.foo)  -- missing: foo / nil
```

#### `__newindex`：拦截赋值

```lua
local proxy = setmetatable({}, {
    __newindex = function(_, key)
        error("readonly: " .. tostring(key))
    end
})
proxy.name = "x"  -- 报错
```

#### `__call`：让 table 可调用

```lua
local Animal = {}
Animal.__index = Animal

function Animal.new(name)
    return setmetatable({ name = name }, Animal)
end

setmetatable(Animal, {
    __call = function(_, ...) return Animal.new(...) end
})

local a = Animal("Rex")
print(a.name)  -- Rex
```

#### `__tostring`：控制打印

```lua
local Point = {}
Point.__index = Point
function Point.new(x, y)
    return setmetatable({ x = x, y = y }, Point)
end
function Point.__tostring(p)
    return string.format("Point(%d, %d)", p.x, p.y)
end
print(Point.new(3, 4))  -- Point(3, 4)
```

#### `__eq` / `__lt` / `__le`：比较

```lua
local Vec2D = {}
Vec2D.__index = Vec2D
function Vec2D.new(x, y)
    return setmetatable({ x = x, y = y }, Vec2D)
end
function Vec2D.__eq(a, b)
    return a.x == b.x and a.y == b.y
end
function Vec2D.__lt(a, b)
    return a.x * a.x + a.y * a.y < b.x * b.x + b.y * b.y
end

print(Vec2D.new(1, 2) == Vec2D.new(1, 2))  -- true
print(Vec2D.new(1, 2) < Vec2D.new(3, 4))   -- true
```

> [!WARNING]
> `__eq` 要求两个操作数 metatable 相同，否则直接返回 `false`。

#### `__add` / `__sub` / `__mul`：算术运算

```lua
local Vec2D = {}
Vec2D.__index = Vec2D
function Vec2D.new(x, y)
    return setmetatable({ x = x or 0, y = y or 0 }, Vec2D)
end
function Vec2D.__add(a, b)
    return Vec2D.new(a.x + b.x, a.y + b.y)
end
function Vec2D.__sub(a, b)
    return Vec2D.new(a.x - b.x, a.y - b.y)
end
function Vec2D.__mul(v, s)
    return Vec2D.new(v.x * s, v.y * s)
end
function Vec2D.__tostring(v)
    return string.format("Vec2D(%g, %g)", v.x, v.y)
end

local a = Vec2D.new(1, 2)
local b = Vec2D.new(3, 4)
print(a + b)   -- Vec2D(4, 6)
print(a - b)   -- Vec2D(-2, -2)
print(a * 2)   -- Vec2D(2, 4)
```

#### `__len`：自定义 `#`

```lua
local Counter = {}
Counter.__index = Counter
function Counter.new()
    return setmetatable({ _count = 0 }, Counter)
end
function Counter:inc()
    self._count = self._count + 1
end
function Counter.__len(t)
    return t._count
end

local c = Counter.new()
c:inc(); c:inc(); c:inc()
print(#c)  -- 3
```

#### `__pairs` / `__ipairs`：自定义迭代

```lua
local OrderedSet = {}
OrderedSet.__index = OrderedSet
function OrderedSet.new(...)
    local self = { keys = {} }
    for _, v in ipairs({ ... }) do
        self.keys[#self.keys + 1] = v
    end
    return setmetatable(self, OrderedSet)
end
function OrderedSet.__pairs(self)
    local i = 0
    return function()
        i = i + 1
        return self.keys[i], true
    end
end

for k in pairs(OrderedSet.new("lua", "neovim", "vim")) do
    print(k)  -- lua, neovim, vim
end
```

---

## 3. OOP 模式完整范式

### 类、构造函数、冒号语法糖

```lua
local Stack = {}
Stack.__index = Stack  -- 关键：实例查找类方法

function Stack.new()
    return setmetatable({ _items = {} }, Stack)
end

function Stack:push(item)
    table.insert(self._items, item)
end

-- 冒号等价于显式 self
function Stack.pop(self)
    return table.remove(self._items)
end

local s = Stack.new()
s:push("hello")     -- 推荐
s.push(s, "world")  -- 等价
```

### 完整示例：Stack 类

```lua
local Stack = {}
Stack.__index = Stack

function Stack.new()
    return setmetatable({ _items = {} }, Stack)
end
function Stack:push(item)
    table.insert(self._items, item)
end
function Stack:pop()
    return table.remove(self._items)
end
function Stack:peek()
    return self._items[#self._items]
end
function Stack:size()
    return #self._items
end
function Stack.__tostring(s)
    return "Stack[" .. table.concat(s._items, ", ") .. "]"
end

local s = Stack.new()
s:push("a"); s:push("b"); s:push("c")
print(s)           -- Stack[a, b, c]
print(s:pop())     -- c
print(s:peek())    -- b
print(s:size())    -- 2
```

### 继承

```lua
local Animal = {}
Animal.__index = Animal
function Animal.new(name)
    return setmetatable({ name = name }, Animal)
end
function Animal:speak()
    return self.name .. " makes a sound"
end

local Dog = {}
Dog.__index = Dog
setmetatable(Dog, { __index = Animal })  -- Dog 继承 Animal

function Dog.new(name)
    return setmetatable(Animal.new(name), Dog)
end
function Dog:speak()
    return self.name .. " barks"
end

print(Dog.new("Rex"):speak())  -- Rex barks
```

### 完整示例：Vector2D 类

```lua
local Vector2D = {}
Vector2D.__index = Vector2D

function Vector2D.new(x, y)
    return setmetatable({ x = x or 0, y = y or 0 }, Vector2D)
end

function Vector2D.__add(a, b)
    return Vector2D.new(a.x + b.x, a.y + b.y)
end

function Vector2D.__sub(a, b)
    return Vector2D.new(a.x - b.x, a.y - b.y)
end

function Vector2D.__mul(v, s)
    return Vector2D.new(v.x * s, v.y * s)
end

function Vector2D.__eq(a, b)
    return a.x == b.x and a.y == b.y
end

function Vector2D:magnitude()
    return math.sqrt(self.x * self.x + self.y * self.y)
end

function Vector2D:normalize()
    local mag = self:magnitude()
    if mag == 0 then return Vector2D.new(0, 0) end
    return self * (1 / mag)
end

function Vector2D.__tostring(v)
    return string.format("Vector2D(%g, %g)", v.x, v.y)
end

local a = Vector2D.new(3, 4)
local b = Vector2D.new(1, 2)
print(a + b)                   -- Vector2D(4, 6)
print(a - b)                   -- Vector2D(2, 2)
print(a * 2)                   -- Vector2D(6, 8)
print(a:magnitude())           -- 5
print(a:normalize())           -- Vector2D(0.6, 0.8)
print(a == Vector2D.new(3, 4)) -- true
```

---

## 4. 弱表（weak table）简介

弱表通过 metatable 的 `__mode` 控制键/值是否被垃圾回收。

| `__mode` | 含义 |
|----------|------|
| `"k"` | key 弱引用 |
| `"v"` | value 弱引用 |
| `"kv"` | key 和 value 都弱引用 |

```lua
local cache = setmetatable({}, { __mode = "v" })

local function get_data(key)
    if cache[key] then return cache[key] end
    local value = { data = "computed " .. key }
    cache[key] = value
    return value
end

local a = get_data("foo")
print(a.data)
-- 当外部不再引用 a 时，cache["foo"] 可能被回收
```

> [!WARNING]
> 弱表的 key/value 必须是对象类型。字符串和数字没有弱引用语义。

---

## 5. 代码示例

```lua
-- table_demo.lua
local fruits = { "apple", "banana", "cherry" }
print("水果列表（ipairs）:")
for i, fruit in ipairs(fruits) do
    print(string.format("  %d: %s", i, fruit))
end

local config = {
    theme = "tokyonight",
    font_size = 14,
    features = { "lsp", "treesitter", "telescope" },
}

print("\n配置项（pairs）:")
for key, value in pairs(config) do
    if type(value) == "table" then
        print(string.format("  %s = {%s}", key, table.concat(value, ", ")))
    else
        print(string.format("  %s = %s", key, tostring(value)))
    end
end

local defaults = { timeout = 30, retries = 3 }
local user_opts = setmetatable({ timeout = 60 }, { __index = defaults })
print("\n合并后选项:")
print("  timeout =", user_opts.timeout)
print("  retries =", user_opts.retries)

local Vector2D = {}
Vector2D.__index = Vector2D
function Vector2D.new(x, y)
    return setmetatable({ x = x or 0, y = y or 0 }, Vector2D)
end
function Vector2D.__add(a, b)
    return Vector2D.new(a.x + b.x, a.y + b.y)
end
function Vector2D:magnitude()
    return math.sqrt(self.x * self.x + self.y * self.y)
end
function Vector2D.__tostring(v)
    return string.format("Vector2D(%g, %g)", v.x, v.y)
end

local v1 = Vector2D.new(1, 2)
local v2 = Vector2D.new(3, 4)
print("\n向量运算:")
print("  v1 + v2 =", v1 + v2)
print("  |v1| =", v1:magnitude())

local lazy_plugins = {
    { "folke/tokyonight.nvim", priority = 1000, opts = { style = "night" } },
    { "nvim-telescope/telescope.nvim", dependencies = { "nvim-lua/plenary.nvim" } },
}

print("\n插件列表:")
for _, plugin in ipairs(lazy_plugins) do
    print("  " .. plugin[1])
end
```

**运行方式:**
```bash
lua table_demo.lua
```

**预期输出:**
```text
水果列表（ipairs）:
  1: apple
  2: banana
  3: cherry

配置项（pairs）:
  theme = tokyonight
  font_size = 14
  features = {lsp, treesitter, telescope}

合并后选项:
  timeout = 60
  retries = 3

向量运算:
  v1 + v2 = Vector2D(4, 6)
  |v1| = 2.23607

插件列表:
  folke/tokyonight.nvim
  nvim-telescope/telescope.nvim
```

---

## 6. 练习

### 练习 1: 数组操作
创建包含 5 个数字的 table。追加 2 个数字，删除第 3 个元素。用 `ipairs` 打印所有元素和长度。

### 练习 2: 配置字典
创建以下 table，用 `pairs` 遍历打印：

```lua
{
    name = "nvim-cmp",
    lazy = false,
    dependencies = { "hrsh7th/cmp-nvim-lsp", "hrsh7th/cmp-buffer" },
    opts = {
        mapping = { ["<CR>"] = "confirm", ["<Tab>"] = "select_next" },
    },
}
```

### 练习 3: 实现 Queue 类
用 OOP 实现 `Queue`，支持 `new`、`enqueue`、`dequeue`、`peek`、`size`、`__tostring`。

### 练习 4: 用 __add 实现向量加法
定义 `Point` 类，实现 `__add` 和 `__eq`。打印 `Point.new(1,2) + Point.new(3,4)` 和 `Point.new(1,2) == Point.new(1,2)`。

### 练习 5: 统计词频（可选）
写一个函数，接受字符串数组，返回词频 table。

## 6.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> local nums = { 10, 20, 30, 40, 50 }
> table.insert(nums, 60)
> table.insert(nums, 70)
> table.remove(nums, 3)
> for i, v in ipairs(nums) do
>     print("nums[" .. i .. "] = " .. v)
> end
> print("长度: " .. #nums)
> ```

> [!tip]- 练习 2 参考答案
> ```lua
> local plugin_config = {
>     name = "nvim-cmp",
>     lazy = false,
>     dependencies = { "hrsh7th/cmp-nvim-lsp", "hrsh7th/cmp-buffer" },
>     opts = { mapping = { ["<CR>"] = "confirm", ["<Tab>"] = "select_next" } },
> }
>
> for key, value in pairs(plugin_config) do
>     if type(value) == "table" then
>         print(key .. ":")
>         for k2, v2 in pairs(value) do
>             if type(v2) == "table" then
>                 print("  " .. k2 .. ":")
>                 for k3, v3 in pairs(v2) do print("    " .. k3 .. " = " .. v3) end
>             else
>                 print("  " .. k2 .. " = " .. tostring(v2))
>             end
>         end
>     else
>         print(key .. " = " .. tostring(value))
>     end
> end
> ```

> [!tip]- 练习 3 参考答案
> ```lua
> local Queue = {}
> Queue.__index = Queue
> function Queue.new()
>     return setmetatable({ _items = {} }, Queue)
> end
> function Queue:enqueue(item)
>     table.insert(self._items, item)
> end
> function Queue:dequeue()
>     return table.remove(self._items, 1)
> end
> function Queue:peek()
>     return self._items[1]
> end
> function Queue:size()
>     return #self._items
> end
> function Queue.__tostring(q)
>     return "Queue[" .. table.concat(q._items, ", ") .. "]"
> end
>
> local q = Queue.new()
> q:enqueue("a"); q:enqueue("b"); q:enqueue("c")
> print(q)
> print(q:peek())
> print(q:dequeue())
> print(q:size())
> ```

> [!tip]- 练习 4 参考答案
> ```lua
> local Point = {}
> Point.__index = Point
> function Point.new(x, y)
>     return setmetatable({ x = x, y = y }, Point)
> end
> function Point.__add(a, b)
>     return Point.new(a.x + b.x, a.y + b.y)
> end
> function Point.__eq(a, b)
>     return a.x == b.x and a.y == b.y
> end
> function Point.__tostring(p)
>     return string.format("Point(%d, %d)", p.x, p.y)
> end
>
> print(Point.new(1, 2) + Point.new(3, 4))
> print(Point.new(1, 2) == Point.new(1, 2))
> ```

> [!tip]- 练习 5 参考答案（可选）
> ```lua
> local function word_count(words)
>     local counts = {}
>     for _, word in ipairs(words) do
>         counts[word] = (counts[word] or 0) + 1
>     end
>     return counts
> end
>
> for word, count in pairs(word_count({ "lua", "neovim", "lua", "vim", "neovim", "lua" })) do
>     print(word .. ": " .. count)
> end
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 7. 扩展阅读

- [Programming in Lua — Tables](https://www.lua.org/pil/2.5.html)
- [Programming in Lua — Metatables and Metamethods](https://www.lua.org/pil/13.html)
- [Lua 5.1 参考手册 — Table Manipulation](https://www.lua.org/manual/5.1/manual.html#5.5)
- [Lua 5.1 参考手册 — Metatables](https://www.lua.org/manual/5.1/manual.html#2.8)

---

## 常见陷阱

- **`#` 对稀疏 table 不可靠**：数组中有 `nil` 洞时结果不确定。
- **`ipairs` 遇到 `nil` 就停止**：即使后面还有元素。
- **table 是引用类型**：`local b = a; b[1] = 99` 会改变 `a`。
- **忘记设置 `__index`**：OOP 中类的 `__index` 必须指向自己。
- **`__eq` 要求 metatable 相同**：不同 metatable 的对象比较直接返回 `false`。
- **`__call` 放错 metatable**：想让 `Class(...)` 工作，要把 `__call` 放在 `Class` 自己的 metatable 里。
- **弱表只能弱引用对象类型**：字符串/数字作为 key 不会被弱引用。
