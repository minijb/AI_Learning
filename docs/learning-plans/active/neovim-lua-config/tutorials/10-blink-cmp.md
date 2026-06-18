---
title: "10 — blink.cmp 补全系统"
updated: 2026-06-18
---

# 10 — blink.cmp 补全系统

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 55 分钟
> 前置知识: [[09-modern-lsp]]

---

## 1. 概念讲解

### blink.cmp vs nvim-cmp

blink.cmp 是 2025 年出现的现代补全引擎，正迅速成为 Neovim 生态的新标准（kickstart.nvim 已默认采用）：

| 特性 | blink.cmp | nvim-cmp (旧) |
|---|---|---|
| 实现语言 | Rust + Lua | 纯 Lua |
| 性能 | 极快（Rust 实现的核心） | 中等 |
| 配置方式 | 单一 `setup()` 调用，结构清晰 | 多个 `cmp.setup()` 调用 + 多文件 |
| 内置源 | lsp + path + buffer + snippets | 需要额外安装 cmp-nvim-lsp 等 |
| 模糊匹配 | 内置 Rust 实现 | 依赖外部源 |
| 签名帮助 | 内置 | 需要额外插件 |
| snippet 集成 | 原生支持 | 需要 cmp_luasnip |
| cmdline 补全 | 内置 | 需额外配置 |
| 维护状态 | 活跃开发中 | 稳定但渐被取代 |

### 架构对比

```text
nvim-cmp 架构:                blink.cmp 架构:
┌──────────────┐              ┌──────────────┐
│   nvim-cmp   │              │  blink.cmp   │
│   (核心引擎)  │              │  (Rust 引擎)  │
├──────────────┤              ├──────────────┤
│ cmp-nvim-lsp │← LSP        │ built-in lsp │← LSP
│ cmp-buffer   │← Buffer     │ built-in     │← Buffer
│ cmp-path     │← Path       │ built-in     │← Path
│ cmp_luasnip  │← Snippets   │ luasnip      │← Snippets (preset)
│ (分别安装)    │              │ (内建集成)    │
└──────────────┘              └──────────────┘
```

### V1 vs V2 状态说明（重要）

> [!IMPORTANT]
> blink.cmp 目前有两个并存的主要版本，选错版本会导致配置异常或锁死依赖。

| 版本 | 写法 | 状态 | 推荐场景 |
|---|---|---|---|
| V1 | `version = vim.version.range '1.*'` | 稳定，kickstart 默认 | **生产配置** |
| V2 | `version = 'main'` | 积极开发中，**有破坏性变更** | 尝鲜/学习专用配置 |

V2 的关键变化：
- 需要额外安装 `saghen/blink.lib` 作为依赖
- 配置结构、部分字段名称与 V1 不兼容
- 文档和社区配置仍以 V1 为主

**学习 V2 的安全方式**：用独立 `NVIM_APPNAME` 启动一份隔离配置，避免污染主配置：

```bash
# Linux/macOS
NVIM_APPNAME=nvim-blink-v2 nvim

# Windows (PowerShell)
$env:NVIM_APPNAME='nvim-blink-v2'; nvim
```

本教程所有示例均基于 **V1（`1.*`）**，这也是 kickstart.nvim 的默认选择。

### 核心配置

```lua
require('blink.cmp').setup({
  keymap = {
    preset = 'default',  -- 推荐：接近 Vim 原生补全的按键
    -- 'super-tab': Tab 补全
    -- 'enter': Enter 补全
    -- 'none': 完全自定义
  },
  sources = {
    default = { 'lsp', 'path', 'snippets' },  -- buffer 可选添加
  },
  snippets = { preset = 'luasnip' },  -- 使用 LuaSnip
  fuzzy = { implementation = 'lua' },  -- 'prefer_rust_with_warning' 启用 Rust 引擎
  signature = { enabled = true },     -- 函数签名帮助
  completion = {
    documentation = { auto_show = false, auto_show_delay_ms = 500 },
  },
  appearance = {
    nerd_font_variant = 'mono',  -- 或 'normal'
  },
})
```

### snippet 后端三选项对比

blink.cmp 支持三种 snippet 后端，按需求选择：

| 后端 | 写法 | 依赖 | 功能 | 推荐 |
|---|---|---|---|---|
| `'native'` | `snippets = { preset = 'native' }` | 无（0.10+ 内置） | 基本 tabstop 展开 | 极简配置 |
| `'luasnip'` | `snippets = { preset = 'luasnip' }` | `L3MON4D3/LuaSnip` | 动态 snippet、条件触发、函数节点 | **kickstart 默认** |
| `'mini_snippets'` | `snippets = { preset = 'mini_snippets' }` | `echasnovski/mini.snippets` | mini.nvim 生态 | 已用 mini.nvim 的用户 |

### vim.snippet 原生 API 简介

Neovim 0.10+ 内置 `vim.snippet`，无需任何插件：

```lua
-- 直接展开一个 snippet
vim.snippet.expand('for ${1:i}, ${2:limit} do\n  $0\nend')

-- 常用语法
-- ${1}      第 1 个跳转位
-- ${1:default}  第 1 个跳转位带默认值
-- $0        终点（最后一个位置）
-- $VISUAL   替换选中的文本
```

与 LuaSnip 相比，`vim.snippet` 适合"临时写几个小片段"，不适合复杂 snippet 集合。

### fuzzy 实现选择

| 值 | 说明 | 推荐场景 |
|---|---|---|
| `'lua'` | 纯 Lua 实现，跨平台，无需下载 | **默认推荐** |
| `'prefer_rust_with_warning'` | 优先 Rust，首次需下载二进制；不可用时回退 Lua 并提示 | 追求性能 |
| `'prefer_rust'` | 优先 Rust，不可用时报错 | 已验证环境可用 |

> [!WARNING]
> `'prefer_rust_with_warning'` 首次使用时会尝试下载预编译的 Rust 二进制。在离线环境或某些企业网络中可能失败，此时回退到 `'lua'`。

### frecency + proximity bonus

blink.cmp 的排序不仅是"字符串相似度"，还结合了：

- **frecency**（frequency + recency）：最近常用、且经常用的词条排名更高
- **proximity bonus**：离光标更近的局部变量、参数优先

这些机制默认生效，无需额外配置。如果你发现某个 LSP 的补全顺序不理想，通常是 LSP 的 `sortText` 权重较高，可以通过 `completion.list.selection = 'auto_insert'` 或 `sources.providers.lsp.score_offset` 微调。

### 自动括号（auto-brackets）

blink.cmp 基于 LSP 的 **semantic tokens** 自动补全函数/方法调用后的括号：

```lua
completion = {
  accept = { auto_brackets = { enabled = true } },
}
```

当确认 `print` 这类函数时，会自动展开为 `print(|)`（光标在括号内）。默认开启。

---

## 2. 代码示例

### 完整的 blink.cmp + LuaSnip 配置

```lua
-- init.lua Section: Autocomplete & Snippets
-- 要求: Neovim 0.12.3+
do
  -- Snippet 引擎
  vim.pack.add { { src = gh 'L3MON4D3/LuaSnip', version = vim.version.range '2.*' } }
  require('luasnip').setup {}

  -- 可选：预制 snippet 集合
  -- vim.pack.add { gh 'rafamadriz/friendly-snippets' }
  -- require('luasnip.loaders.from_vscode').lazy_load()

  -- 补全引擎（版本锁定 V1）
  vim.pack.add { { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' } }
  require('blink.cmp').setup {
    keymap = {
      preset = 'default',
      -- 'default' 预设包含的映射:
      --   <C-y>    确认补全
      --   <C-n>/<C-p> 选择下一项/上一项
      --   <C-space> 打开菜单 / 打开文档
      --   <C-e>    关闭菜单
      --   <C-k>    切换签名帮助
      --   <Tab>/<S-Tab> 在 snippet 占位符间跳转
    },

    appearance = {
      nerd_font_variant = 'mono',
    },

    completion = {
      documentation = {
        auto_show = false,
        auto_show_delay_ms = 500,
      },
      accept = {
        auto_brackets = { enabled = true },
      },
    },

    -- 补全来源及顺序
    sources = {
      default = { 'lsp', 'path', 'snippets' },
      -- 可选: 添加 buffer 源 (当前文件中的词)
      -- default = { 'lsp', 'path', 'snippets', 'buffer' },
      providers = {
        lsp = { score_offset = 0 },
        path = { score_offset = 3 },
        snippets = { score_offset = -3 },
      },
    },

    -- 使用 LuaSnip 作为 snippet 后端
    snippets = { preset = 'luasnip' },

    -- 模糊匹配实现
    fuzzy = {
      implementation = 'lua',  -- 跨平台安全选择
      -- 如需性能，启用 Rust 引擎（首次需下载预编译二进制）
      -- implementation = 'prefer_rust_with_warning',
    },

    -- 函数参数签名帮助
    signature = { enabled = true },

    -- 命令行补全
    cmdline = {
      enabled = true,
      sources = function()
        local type = vim.fn.getcmdtype()
        if type == '/' or type == '?' then return { 'buffer' } end
        if type == ':' then return { 'cmdline' } end
        return {}
      end,
    },

    -- 终端补全（Neovim 0.11+）
    term = { enabled = true },
  }
end
```

**运行方式:**
1. 将上述代码放入 `init.lua`
2. 确保 LSP 已配置（第 09 节）
3. 启动 Neovim，打开一个 Lua 文件
4. 输入 `vim.key` 等待补全弹出（约 250ms 内）
5. 按 `<C-n>` / `<C-p>` 选择，`<C-y>` 确认
### 调整补全菜单的预选行为

`completion.list.selection` 控制菜单弹出时是否预选第一项：

```lua
completion = {
  list = {
    selection = {
      preselect = true,   -- 默认预选第一项
      auto_insert = true, -- 自动把预选内容插入到 buffer
    },
  },
}
```

| 组合 | 行为 |
|---|---|
| `preselect = true, auto_insert = false` | 高亮第一项，但不插入文本（推荐） |
| `preselect = true, auto_insert = true` | 高亮并自动插入，按 `<C-y>` 确认 |
| `preselect = false` | 不预选，需手动按 `<C-n>` 选择 |

kickstart 默认用 `preselect = true, auto_insert = false`，避免还没确认就把候选内容写进文件。

### 终端模式补全（term）

Neovim 0.11+ 在终端缓冲区也支持补全。启用后，在 `:terminal` 中输入命令时可以像普通 buffer 一样触发 blink.cmp：

```lua
term = {
  enabled = true,
  keymap = { preset = 'default' },
  sources = { 'path', 'buffer' },
}
```

终端补全的触发逻辑与普通 buffer 类似，但通常不需要 LSP 和 snippet 源。

### 自定义外观（appearance）

```lua
appearance = {
  nerd_font_variant = 'mono',  -- 'mono' 或 'normal'
  kind_icons = {
    Text = '󰉿',
    Method = '󰆧',
    Function = '󰊕',
    Constructor = '󰒓',
  },
}
```

`nerd_font_variant = 'mono'` 让图标占一个等宽单元格，避免菜单列对不齐。

### 自定义 `<CR>` 智能确认（非 preset）

如果你想保留 `default` 预设，但让 `<CR>` 在"有补全菜单时确认、无菜单时换行"：

```lua
require('blink.cmp').setup {
  keymap = {
    preset = 'default',
    ['<CR>'] = { 'accept', 'fallback' },
  },
}
```

这个食谱的意思是：
- 如果补全菜单打开，`accept` 确认当前项
- 否则 `fallback` 退回到默认的 `<CR>` 换行

> [!WARNING]
> 这种映射容易在补全菜单"你以为会换行"的时候确认补全。建议只在熟悉了 blink.cmp 行为后使用。

### 社区源与 blink.compat

blink.cmp 内置源有限，但可以通过 `blink.compat` 复用大量 nvim-cmp 社区源：

```lua
vim.pack.add {
  { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' },
  { src = gh 'saghen/blink.compat', version = vim.version.range '1.*' },
  { src = gh 'rafamadriz/friendly-snippets' },
  { src = gh 'hrsh7th/cmp-nvim-lua' },  -- 一个 nvim-cmp 源示例
}

require('blink.cmp').setup {
  sources = {
    default = { 'lsp', 'path', 'snippets', 'nvim_lua' },
    providers = {
      nvim_lua = {
        name = 'nvim_lua',
        module = 'blink.compat.source',
        score_offset = -3,
      },
    },
  },
}
```

> [!NOTE]
> 不是所有 nvim-cmp 源都能完美兼容。使用前查看 blink.compat 的 README 中的已知兼容列表。

### 使用原生 vim.snippet 的最简配置

如果你不想依赖 LuaSnip，可以用 `'native'`：

```lua
vim.pack.add { { src = gh 'saghen/blink.cmp', version = vim.version.range '1.*' } }
require('blink.cmp').setup {
  snippets = { preset = 'native' },
  sources = { default = { 'lsp', 'path', 'snippets' } },
}
```

---

## 3. 练习

### 练习 1: 验证补全来源

打开一个 Lua 文件：
- 输入 `vim.key` — 确认有 LSP 补全（来自 lua_ls）
- 输入 `./` — 确认有路径补全（来自 path）
- 在代码中输入 `for` 后按 Tab（LuaSnip snippet 可能展开或选择）
- 输入当前文件中已存在的词——如果启用了 `buffer` 源，确认能看到

### 练习 2: 切换 keymap 预设

将 `keymap.preset` 改为 `'super-tab'`，重启后体验 Tab 键补全的行为。再改为 `'enter'` 体验。最后恢复为 `'default'`。

理解不同预设的 trade-off：
- `'default'`: `<C-y>` 确认，不干扰 `<CR>` 换行
- `'super-tab'`: Tab 确认，适合习惯 Tab 补全的用户
- `'enter'`: Enter 确认，最接近 IDE 体验

### 练习 3: 添加自定义 snippet

使用 LuaSnip 创建一个简单的 Lua snippet：

```lua
require('luasnip').add_snippets('lua', {
  require('luasnip').snippet('fn', {
    require('luasnip').text_node('function '),
    require('luasnip').insert_node(1, 'name'),
    require('luasnip').text_node('('),
    require('luasnip').insert_node(2),
    require('luasnip').text_node({ ')', '\t', '' }),
    require('luasnip').insert_node(0),
    require('luasnip').text_node({ '', 'end' }),
  })
})
```

在 Lua 文件中输入 `fn` + `<C-y>`，观察 snippet 展开。

### 练习 4: 启用命令行补全

在现有 blink.cmp 配置中加入 `cmdline = { enabled = true }`，然后：
- 按 `:` 输入 `:wri`，确认能否补全到 `:write`
- 按 `/` 搜索当前 buffer 中的词，确认 buffer 源补全

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 验证各补全来源的步骤与预期结果：
>
> - **LSP 补全** (`'lsp'`)：输入 `vim.key` → 应弹出来自 lua_ls 的补全列表，每项带有类型标注和文档。LSP 补全的特点是包含函数签名、类型信息和来自语言服务器的精确建议。
> - **路径补全** (`'path'`)：输入 `./` 或 `require('` → 应弹出文件系统路径的补全列表（目录和文件名）。路径补全触发于路径分隔符 `/` 或字符串上下文。
> - **Snippet 补全** (`'snippets'`)：在 Lua 文件中输入 `for` → 补全弹出后按 `Tab`（或 `<C-n>` 选中 + `<C-y>` 确认），LuaSnip 应展开 `for` snippet 为完整的循环模板。snippet 条目在补全菜单中有特殊图标标记。
> - **Buffer 补全** (`'buffer'`)：如果已将 `'buffer'` 加入 `sources.default`，输入当前文件已存在的变量名 → 应看到来自当前 buffer 的词条补全。注意 buffer 源会产生较多噪音（文件中所有词都成为候选），kickstart 默认不含它。
>
> **如何确认补全来源**：blink.cmp 在补全菜单中为不同来源显示不同图标——LSP 显示服务器图标，path 显示文件夹图标，snippet 显示剪刀图标。你也可以临时修改 `sources.default` 只保留一个来源来隔离测试。

> [!tip]- 练习 2 参考答案
> 三种 keymap 预设的行为差异：
>
> | 预设 | 确认补全 | 选择上一项/下一项 | 关闭菜单 | 换行行为 |
> |---|---|---|---|---|
> | `'default'` | `<C-y>` | `<C-n>` / `<C-p>` | `<C-e>` | `<CR>` 正常换行，不确认补全 |
> | `'super-tab'` | `<Tab>` | `<Tab>` / `<S-Tab>` | `<C-e>` | `<CR>` 正常换行 |
> | `'enter'` | `<CR>` (Enter) | `<C-n>` / `<C-p>` | `<C-e>` | 无直接换行——需先 `<C-e>` 关闭菜单再按 Enter |
>
> **default 预设** 是最安全的选择——确认补全（`<C-y>`）和换行（`<CR>`）是独立按键，不会因为想换行而意外确认补全。
>
> **super-tab 预设** 适合从 VSCode 迁移的用户——Tab 既是导航也是确认，减少按键种类。代价是如果想在补全菜单中插入 Tab 字符（如在 Markdown 中）就不方便。
>
> **enter 预设** 最接近 IDE 体验但风险最大——如果你习惯看补全菜单的同时按 Enter 换行，你就意外确认了补全。只有当你确定自己习惯用其他方式换行（如 `<C-j>` mapped to `<CR>`）时才选择它。

> [!tip]- 练习 3 参考答案
> 完整可运行的 Lua function snippet 配置：
>
> ```lua
> -- 在 init.lua 的 Autocomplete & Snippets section 中，
> -- 在 require('luasnip').setup {} 之后添加：
>
> local ls = require 'luasnip'
>
> ls.add_snippets('lua', {
>   ls.snippet('fn', {
>     ls.text_node('function '),       -- 静态文本 "function "
>     ls.insert_node(1, 'name'),       -- 第一个跳转位（函数名）
>     ls.text_node('('),                -- 左括号
>     ls.insert_node(2, 'args'),       -- 第二个跳转位（参数列表）
>     ls.text_node({ ')', '' }),       -- 右括号 + 换行
>     ls.insert_node(0, '  -- body'),  -- 第 0 个跳转位（函数体，0 = 最后一个）
>     ls.text_node({ '', 'end' }),     -- 换行 + end
>   }),
> })
> ```
>
> 使用方法：
> 1. 在 Lua 文件中输入 `fn`（插入模式）
> 2. blink.cmp 弹出补全菜单，snippet 条目显示 `fn` 带 snippet 图标
> 3. 按 `<C-y>` 确认后，LuaSnip 展开为模板
> 4. 光标首先在 `name` 位置（insert_node 1），输入函数名后按 `<Tab>` 跳到 `args`（insert_node 2）
> 5. 输入参数后按 `<Tab>` 跳到 `-- body`（insert_node 0），编辑函数体后按 `<Tab>` 跳出 snippet
>
> **关键概念**：`insert_node(0)` 是"出口节点"——所有跳转最终结束于 0 号节点。`text_node` 是不可编辑的静态文本。`insert_node(N)` 按 N 升序跳转（1 → 2 → ... → 0）。

> [!tip]- 练习 4 参考答案
> 命令行补全的最小工作配置：
>
> ```lua
> require('blink.cmp').setup {
>   cmdline = {
>     enabled = true,
>     sources = function()
>       local type = vim.fn.getcmdtype()
>       if type == '/' or type == '?' then return { 'buffer' } end
>       if type == ':' then return { 'cmdline' } end
>       return {}
>     end,
>   },
> }
> ```
>
> 验证步骤：
> 1. 保存后重启 Neovim
> 2. 按 `:` 进入命令行，输入 `:wri`
> 3. 按 `<C-n>` 或 `<Tab>`，应看到 `:write`、`:write!` 等候选
> 4. 按 `/` 进入搜索，输入文件中已有的词的前几个字母，按 `<C-n>` 应能补全
>
> **注意**：命令行补全的确认键仍然是 `<C-y>`（default 预设下）。如果你用 `'enter'` 预设，`<CR>` 会直接执行命令。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [blink.cmp 官方文档](https://github.com/saghen/blink.cmp)
- [blink.compat 兼容层](https://github.com/saghen/blink.compat) — 复用 nvim-cmp 社区源
- [LuaSnip 文档](https://github.com/L3MON4D3/LuaSnip/blob/master/DOC.md)
- [friendly-snippets](https://github.com/rafamadriz/friendly-snippets) — 预置 snippet 集合
- [`:help ins-completion`](https://neovim.io/doc/user/insert.html#ins-completion) — Neovim 内置补全机制
- [`:help vim.snippet`](https://neovim.io/doc/user/lua.html#vim.snippet) — 原生 snippet API

---

## 常见陷阱

- **blink.cmp 和 nvim-cmp 不能共存**：如果从旧配置迁移，必须先删除 nvim-cmp 及其所有依赖（cmp-nvim-lsp, cmp-buffer, cmp-path, cmp_luasnip 等）。
- **V1 与 V2 混用会报错**：`1.*` 和 `main` 的配置字段不兼容，且 V2 需要 `blink.lib`。
- **LSP 补全不工作**：检查 LSP 服务器是否正常附着（`:checkhealth vim.lsp` 或 `:LspInfo`，注意 0.12 中 `:LspInfo` 已移除）。
- **Rust fuzzy 匹配器需要网络**：`implementation = 'prefer_rust_with_warning'` 首次使用时需要下载预编译二进制。如果离线，用 `'lua'`。
- **LuaSnip 跳转按键**：blink.cmp 接管了 `<Tab>` 和 `<S-Tab>` 用于 snippet 跳转。如果同时配置了 `cmp` 和 `blink.cmp` 的映射，会产生冲突。
- **`friendly-snippets` 需要手动加载**：安装后必须调用 `require('luasnip.loaders.from_vscode').lazy_load()` 才能使用。
- **blink.cmp 版本锁定很重要**：该插件正在快速迭代，用 `vim.version.range '1.*'` 锁定主版本。
- **命令行补全与预设绑定**：如果 keymap preset 是 `'enter'`，命令行中 `<CR>` 会直接执行命令，而不是确认补全。
