---
title: "02 — Lua 核心：table — 唯一的数据结构"
updated: 2026-06-05
---

# 02 — Lua 核心：table — 唯一的数据结构

> 所属计划: Neovim + Lua 配置实战
> 预计耗时: 50 分钟
> 前置知识: 01-lua-basics（类型、控制流）

---

## 1. 概念讲解

### 为什么 table 这么重要？

Lua 只有一种复合数据结构——**table**。它同时扮演了三个角色：
- **数组**（Array）—— 按数字索引的序列
- **字典**（Dictionary / HashMap）—— 按任意键索引的映射
- **对象**（Object）—— 方法 + 状态的封装

在 Neovim 配置中，你几乎每行代码都在操作 table：
- 插件配置用 table 传递选项
- 按键映射用 table 描述
- LSP 设置用嵌套 table 组织

### Table 作为数组

```lua
-- 数组：索引从 1 开始
local plugins = { "telescope", "treesitter", "lsp" }

-- 访问
print(plugins[1])     -- "telescope"
print(plugins[2])     -- "treesitter"
print(#plugins)       -- 3（长度运算符）

-- 遍历数组
for i, name in ipairs(plugins) do
    print(i .. ": " .. name)
end

-- 追加元素
table.insert(plugins, "cmp")
plugins[#plugins + 1] = "which-key"  -- 等价写法
```

> [!IMPORTANT]
> Lua 数组索引从 **1** 开始，不是 0。`ipairs` 从索引 1 遍历到第一个 `nil`。

### Table 作为字典

```lua
-- 字典：用任意键（通常是字符串）
local opts = {
    number = true,
    relativenumber = true,
    tabstop = 4,
    shiftwidth = 4,
}

-- 访问（两种等价写法）
print(opts.number)           -- true
print(opts["number"])        -- true（键包含特殊字符时必须用这种）

-- 设置新键
opts.expandtab = true
opts["softtabstop"] = 4

-- 遍历字典
for key, value in pairs(opts) do
    print(key .. " = " .. tostring(value))
end
```

**`ipairs` vs `pairs`：**

| 函数 | 遍历范围 | 顺序 | 用途 |
|------|---------|------|------|
| `ipairs(t)` | 只有连续数字索引（`1, 2, 3, ...`） | 保证有序 | 数组 |
| `pairs(t)` | 所有键值对 | 不保证顺序 | 字典 / 混合 table |

### Table 嵌套

Neovim 配置中大量使用嵌套 table 描述复杂选项：

```lua
-- 典型的插件配置结构
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
        rust_analyzer = {},
    },
}

-- 链式访问
print(lsp_config.servers.lua_ls.settings.Lua.runtime.version)  -- "LuaJIT"
```

### 常用 Table 操作

```lua
local t = { "a", "b", "c" }

-- 拼接成字符串
local s = table.concat(t, ", ")  -- "a, b, c"

-- 删除最后一个元素
table.remove(t)  -- t = {"a", "b"}

-- 删除指定位置
table.remove(t, 1)  -- t = {"b"}

-- 数组长度（遇到 nil 会中断，不可靠于稀疏数组）
print(#t)
```

---

## 2. 代码示例

```lua
-- table_demo.lua

-- ====== 数组用法 ======
local fruits = { "apple", "banana", "cherry" }
print("水果列表（ipairs）:")
for i, fruit in ipairs(fruits) do
    print(string.format("  %d: %s", i, fruit))
end

-- ====== 字典用法 ======
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

-- ====== 嵌套访问 ======
print("\n启用的功能:")
for _, feat in ipairs(config.features) do
    print("  - " .. feat)
end

-- ====== 模拟 Neovim 插件配置风格 ======
local lazy_plugins = {
    {
        "folke/tokyonight.nvim",
        priority = 1000,
        opts = {
            style = "night",
            transparent = false,
        },
    },
    {
        "nvim-telescope/telescope.nvim",
        dependencies = { "nvim-lua/plenary.nvim" },
        keys = { "<leader>ff", "<leader>fg" },
    },
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

启用的功能:
  - lsp
  - treesitter
  - telescope

插件列表:
  folke/tokyonight.nvim
  nvim-telescope/telescope.nvim
```

---

## 3. 练习

### 练习 1: 数组操作
创建一个包含 5 个数字的 table。用 `table.insert` 追加 2 个新数字，用 `table.remove` 删除第 3 个元素。最后用 `ipairs` 打印所有元素和当前长度。

### 练习 2: 配置字典
创建以下 table，表示 Neovim 的一个插件配置，然后用 `pairs` 遍历打印：

```lua
-- 目标结构
{
    name = "nvim-cmp",
    lazy = false,
    dependencies = { "hrsh7th/cmp-nvim-lsp", "hrsh7th/cmp-buffer" },
    opts = {
        mapping = { ["<CR>"] = "confirm", ["<Tab>"] = "select_next" },
    },
}
```

### 练习 3: 统计词频（可选）
写一个函数，接受一个字符串数组，返回一个 table，key 是单词，value 是出现次数。用 `pairs` 打印结果。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> -- exercise1_array.lua
> local nums = { 10, 20, 30, 40, 50 }
>
> -- 追加两个新数字
> table.insert(nums, 60)
> table.insert(nums, 70)
>
> -- 删除第 3 个元素（索引为 3，值为 30）
> table.remove(nums, 3)
>
> -- 打印所有元素和长度
> print("当前数组内容:")
> for i, v in ipairs(nums) do
>     print("  nums[" .. i .. "] = " .. v)
> end
> print("数组长度: " .. #nums)  -- 应为 6
> ```
>
> **预期结果：** 删除 30 后数组变为 `{10, 20, 40, 50, 60, 70}`，长度 6。`table.remove` 会压缩数组，后续元素自动前移。

> [!tip]- 练习 2 参考答案
> ```lua
> -- exercise2_plugin_config.lua
> local plugin_config = {
>     name = "nvim-cmp",
>     lazy = false,
>     dependencies = { "hrsh7th/cmp-nvim-lsp", "hrsh7th/cmp-buffer" },
>     opts = {
>         mapping = { ["<CR>"] = "confirm", ["<Tab>"] = "select_next" },
>     },
> }
>
> print("插件配置:")
> for key, value in pairs(plugin_config) do
>     if type(value) == "table" then
>         -- 递归打印嵌套 table
>         print("  " .. key .. ":")
>         for k2, v2 in pairs(value) do
>             if type(v2) == "table" then
>                 print("    " .. k2 .. ":")
>                 for k3, v3 in pairs(v2) do
>                     print("      " .. k3 .. " = " .. v3)
>                 end
>             else
>                 print("    " .. k2 .. " = " .. tostring(v2))
>             end
>         end
>     else
>         print("  " .. key .. " = " .. tostring(value))
>     end
> end
> ```
>
> **关键点：** 键含特殊字符（如 `<CR>`）时必须用 `["<CR>"]` 方括号语法，不能用 `.` 语法。遍历嵌套 table 时需要判断 `type(value) == "table"` 来决定是否继续深入。

> [!tip]- 练习 3 参考答案（可选）
> ```lua
> -- exercise3_wordcount.lua
> local function word_count(words)
>     local counts = {}
>     for _, word in ipairs(words) do
>         if counts[word] then
>             counts[word] = counts[word] + 1
>         else
>             counts[word] = 1
>         end
>     end
>     return counts
> end
>
> -- 测试
> local sample = { "lua", "neovim", "lua", "vim", "neovim", "lua" }
> local result = word_count(sample)
>
> print("词频统计:")
> for word, count in pairs(result) do
>     print("  " .. word .. ": " .. count .. " 次")
> end
> -- 预期: lua: 3, neovim: 2, vim: 1
> ```
>
> **技巧：** `counts[word]` 初值为 `nil`（等价于 `false`），所以 `if counts[word]` 可判断是否已存在该键。也可以写成 `counts[word] = (counts[word] or 0) + 1` 一行搞定。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [Programming in Lua — Tables](https://www.lua.org/pil/2.5.html)
- [Lua 5.1 参考手册 — Table Manipulation](https://www.lua.org/manual/5.1/manual.html#5.5)
- [Lua table 的实现原理（数组部分 + 哈希部分）](https://www.lua.org/gems/sample.pdf)

---

## 常见陷阱

- **`#` 对稀疏 table 不可靠**：如果数组中有 `nil` 洞，`#` 返回的值是不确定的。配置中通常用 `ipairs` 或 `table.insert` 保持数组连续。
- **`ipairs` 遇到 `nil` 就停止**：即使后面还有元素，也不继续遍历。
- **键为数字的 table 既是数组也是字典**：`t = {10, 20, name = "test"}` —— `t[1]` 和 `t.name` 都存在，但 `#t` 可能不是 2。
- **字典 key 不能是 nil**：`t[nil] = 1` 会报错。
- **table 是引用类型**：`local a = {1}; local b = a; b[1] = 99` 后 `a[1]` 也是 99。需要拷贝时用 `vim.deepcopy`（Neovim）或手动递归。
