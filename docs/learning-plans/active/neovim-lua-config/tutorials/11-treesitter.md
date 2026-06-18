---
title: "11 — Treesitter：语法高亮与结构化分析"
updated: 2026-06-18
---

# 11 — Treesitter：语法高亮与结构化分析

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 50 分钟
> 前置知识: [[07-vim-pack]]

---

## 1. 概念讲解

### Tree-sitter 的价值

Tree-sitter 将源代码解析成**具体语法树（CST）**。与传统的正则高亮相比：

| 特性 | 正则高亮 | Tree-sitter |
|---|---|---|
| 准确性 | 模式匹配，嵌套易出错 | 语法解析，结构准确 |
| 速度 | O(n) 扫描 | 增量解析 |
| 功能 | 高亮 | 高亮、折叠、缩进、选区扩展、代码注入、文本对象 |
| 错误恢复 | 无 | 语法错误时仍能解析剩余部分 |

### 语法高亮 vs regex syntax 对比

正则高亮"看到"的是字符序列；treesitter "理解"的是语法结构。例如：

```lua
local fn = function(x) return x + 1 end
```

正则高亮通常只能把 `local`、`function`、`return`、`end` 涂成关键字色；而 treesitter 能区分：
- `fn` → `@function`
- `x` → `@variable.parameter`
- `x + 1` → `@number`

### nvim-treesitter main 分支新 API（重要现代化）

> [!IMPORTANT]
> 旧 nvim-treesitter 用 `ensure_installed = {...}` + `highlight = { enable = true }` 配置——这是 master→main 重构前的写法。现代（main 分支）改用程序化安装 + `vim.treesitter.start()`。

现代用法：

```lua
-- 安装 nvim-treesitter（锁定 main 分支）
vim.pack.add { { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' } }

-- 程序化安装 parser（替代 :TSInstall）
require('nvim-treesitter').install({ 'lua', 'c', 'bash', 'markdown', 'vim', 'vimdoc', 'query' })

-- 查看已安装/可用的 parser
require('nvim-treesitter').get_installed('parsers')
require('nvim-treesitter').get_available()
```

关键变化：
- 不再用全局的 `configs.setup()` 开启所有功能
- 改为用 `vim.treesitter.start()` 按 buffer 精确控制
- `ensure_installed` → `require('nvim-treesitter').install()`

### 原生 treesitter API（核心）

即使没有 nvim-treesitter 插件，Neovim 0.12+ 也内置了这些 API：

```lua
-- 注册并加载 parser
vim.treesitter.language.add('lua')

-- 为当前 buffer 启用 treesitter 高亮
vim.treesitter.start(buf, 'lua')

-- filetype → language 映射
local lang = vim.treesitter.language.get_lang('lua')  -- 返回 'lua'

-- treesitter 折叠
vim.wo.foldexpr = 'v:lua.vim.treesitter.foldexpr()'
vim.wo.foldmethod = 'expr'

-- treesitter 缩进（需 nvim-treesitter 提供 indent query）
vim.bo.indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
```

### kickstart master 的 treesitter_try_attach 范式

kickstart 用 `FileType` autocmd 实现无感安装：

```lua
vim.api.nvim_create_autocmd('FileType', {
  callback = function(args)
    local language = vim.treesitter.language.get_lang(args.match)
    local installed = require('nvim-treesitter').get_installed 'parsers'
    local available = require('nvim-treesitter').get_available()

    if vim.tbl_contains(installed, language) then
      -- 已安装 → 直接启用
      treesitter_try_attach(args.buf, language)
    elseif vim.tbl_contains(available, language) then
      -- 有 parser → 自动安装后启用
      require('nvim-treesitter').install(language):await(function()
        treesitter_try_attach(args.buf, language)
      end)
    end
  end,
})
```

`treesitter_try_attach` 是一个你自己定义的辅助函数：检查 parser 是否存在，存在则 `start`；否则 `install` 后 `await` 再 `start`。

### 内置 treesitter 文本对象（0.12 新增，重要冲突警告）

Neovim 0.12 内置了 `an`（around next）和 `in`（inside next）treesitter 文本对象映射（`:help treesitter-incremental-selection`）。

**冲突警告**：mini.ai 默认也用 `an`/`in`。kickstart 因此把 mini.ai 的 around_next/inside_next 改为 `aa`/`ii`：

```lua
require('mini.ai').setup {
  mappings = { around_next = 'aa', inside_next = 'ii' },
  n_lines = 500,
}
```

否则会出现"按 `an` 不知道是 mini.ai 还是 treesitter 文本对象"的冲突。

### query 语言基础

Treesitter 用 **query** 文件描述如何高亮、缩进、折叠等。query 文件位置：

```text
queries/<lang>/highlights.scm
queries/<lang>/indents.scm
queries/<lang>/folds.scm
queries/<lang>/injections.scm
```

在 Neovim 中读取 query：

```lua
local query = vim.treesitter.query.get('lua', 'highlights')
print(query)  -- 打印 highlights query 内容
```

query 语法示例（SCM，Scheme 风格）：

```scm
(function_call
  name: (identifier) @function)
```

这行 query 表示：把函数调用的 `name` 节点捕获为 `@function` 高亮组。

### Treesitter vs LSP vs ctags 对比

| 能力 | Treesitter | LSP | ctags |
|---|---|---|---|
| 语法高亮 | ✅ 精确 | 一般不负责 | ❌ 无 |
| 跳转到定义 | ❌ 无 | ✅ | ✅ 有限 |
| 查找引用 | ❌ 无 | ✅ | ❌ 无 |
| 折叠/缩进 | ✅ | 部分支持 | ❌ 无 |
| 增量解析 | ✅ | ❌ | ❌ |
| 离线工作 | ✅ | 需要 server | ✅ |
| 启动速度 | 快 | 依赖 server | 快 |

官方 help 有更详细说明：`:help lsp-vs-treesitter`。

### 可视化工具

- `:InspectTree` — 打开当前 buffer 的语法树浏览器
- `:Inspect` — 查看光标下 token 的 highlight capture（如 `@function.call`）

---

## 2. 代码示例

### 完整的 kickstart 风格 Treesitter 配置

```lua
-- init.lua Section: Treesitter
-- 要求: Neovim 0.12.3+
do
  -- 安装 nvim-treesitter（锁定 main 分支）
  vim.pack.add { { src = gh 'nvim-treesitter/nvim-treesitter', version = 'main' } }

  -- 预装基础 parsers
  local parsers = {
    'bash', 'c', 'diff', 'html', 'lua', 'luadoc',
    'markdown', 'markdown_inline', 'query', 'vim', 'vimdoc',
  }
  require('nvim-treesitter').install(parsers)

  -- 启用 treesitter 功能的条件函数
  ---@param buf integer
  ---@param language string
  local function treesitter_try_attach(buf, language)
    if not vim.treesitter.language.add(language) then return end
    vim.treesitter.start(buf, language)

    -- 基于 treesitter 的缩进（如果有 indent query）
    local has_indent_query = vim.treesitter.query.get(language, 'indents') ~= nil
    if has_indent_query then
      vim.bo[buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
    end
  end

  -- 按需安装：首次打开某语言文件时自动安装 parser
  local available_parsers = require('nvim-treesitter').get_available()
  vim.api.nvim_create_autocmd('FileType', {
    callback = function(args)
      local buf, filetype = args.buf, args.match
      local language = vim.treesitter.language.get_lang(filetype)
      if not language then return end

      local installed_parsers = require('nvim-treesitter').get_installed 'parsers'

      if vim.tbl_contains(installed_parsers, language) then
        treesitter_try_attach(buf, language)
      elseif vim.tbl_contains(available_parsers, language) then
        require('nvim-treesitter').install(language):await(function()
          treesitter_try_attach(buf, language)
        end)
      else
        treesitter_try_attach(buf, language)
      end
    end,
  })
end
```

**运行方式:**
1. 将上述代码放入 `init.lua`
2. 启动 Neovim，首次会自动安装 parsers 列表中的解析器
3. 打开一个 `.py` 文件——如果之前没安装 Python parser，会自动下载安装
4. 观察语法高亮的细粒度（如函数参数的不同颜色）

### 启用 treesitter 折叠

```lua
-- 在 treesitter_try_attach 中加入
vim.wo[0][0].foldexpr = 'v:lua.vim.treesitter.foldexpr()'
vim.wo[0][0].foldmethod = 'expr'
```

然后可用：
- `zc` 折叠当前节点
- `zo` 展开当前节点
- `zR` 展开全部
### 代码注入（code injection）

Treesitter 可以在一种语言里高亮嵌入的另一种语言。典型场景是 Markdown 里的代码块：

````markdown
```lua
local x = 1
```
````

启用 Markdown + Lua parser 后，代码块内部的 `local x = 1` 会按 Lua 语法高亮，而不是统一按 Markdown 文本处理。

这由 `queries/markdown/injections.scm` 中的 query 控制：

```scm
((fenced_code_block
  (info_string (language) @injection.language)
  (code_fence_content) @injection.content))
```

如果你想在 Vue/Svelte 文件里高亮 `<script lang="ts">` 中的 TypeScript，也需要对应的 parser 和 injection query。

### 覆盖或扩展 query

你可以在个人配置目录下写自定义 query，覆盖插件默认值：

```text
~/.config/nvim/queries/lua/highlights.scm
```

```scm
; 把函数调用的名字强制设为红色
(function_call
  name: (identifier) @function)
```

然后在 init.lua 中：

```lua
vim.treesitter.query.set('lua', 'highlights', [[
(function_call
  name: (identifier) @function)
]])
```

### `:InspectTree` 浏览器按键

`:InspectTree` 会打开一个侧边栏显示当前 buffer 的语法树：

| 按键 | 作用 |
|---|---|
| `J` / `K` | 在兄弟节点间跳转 |
| `zo` / `zc` | 展开/折叠当前节点 |
| `<CR>` | 在主窗口跳转到对应源码位置 |
| `a` | 切换是否显示匿名节点 |
| `i` | 切换是否显示注入的子树 |

这是调试高亮问题、理解 parser 结构的最佳工具。

### 查看光标下的 capture

```vim
:Inspect
```

输出示例：

```text
Treesitter
  - @function.call links to Function
  - @variable.parameter links to Identifier
```

这告诉你当前 token 被哪个 highlight group 着色。

---
### 大文件性能保护

Treesitter 对超大文件（>1MB）可能显著变慢。推荐在 `treesitter_try_attach` 中加入大小检查：

```lua
local function treesitter_try_attach(buf, language)
  local max_size = 1024 * 1024  -- 1 MB
  local ok, stats = pcall(vim.uv.fs_stat, vim.api.nvim_buf_get_name(buf))
  if ok and stats and stats.size > max_size then
    vim.notify(('File too large for treesitter: %d bytes'):format(stats.size), vim.log.levels.WARN)
    return
  end

  if not vim.treesitter.language.add(language) then return end
  vim.treesitter.start(buf, language)
end
```

也可以对特定 filetype 禁用 treesitter（如巨大的日志文件）：

```lua
local disabled_filetypes = { 'log', 'txt', 'csv' }
if vim.tbl_contains(disabled_filetypes, vim.bo[buf].filetype) then return end
```

### 调试 parser 安装失败

1. `:checkhealth treesitter` — 查看编译器、已安装 parser、query 状态
2. `:lua print(vim.inspect(require('nvim-treesitter').get_installed('parsers')))` — 列已安装
3. `:lua require('nvim-treesitter').install('rust')` — 手动触发安装，观察错误输出
4. 检查 C 编译器是否在 PATH 中（Windows 常用 `gcc --version` 或 `cl`）

常见错误：`tree-sitter CLI not found` 表示需要安装 `tree-sitter` 命令行工具；`No C compiler found` 表示缺少 gcc/clang/MSVC。

## 3. 练习

### 练习 1: 对比高亮效果

```vim
" 临时禁用 treesitter 高亮
:lua vim.treesitter.stop()

" 重新启用
:lua vim.treesitter.start()
```

对比禁用前后的高亮差异，尤其在嵌套函数、模板字符串等场景。

### 练习 2: 手动安装一个 parser

```vim
" 查看已安装的 parsers
:lua print(vim.inspect(require('nvim-treesitter').get_installed('parsers')))

" 手动安装一个 parser
:lua require('nvim-treesitter').install('rust')

" 检查安装状态
:checkhealth treesitter
```

### 练习 3: 探索 treesitter 的增量选择

Neovim 0.12 内置了 treesitter 增量选择（不需要 nvim-treesitter 插件）：
- 在函数体内部按 `grn` → 开始选择当前节点
- 反复按 `grn` → 扩展到父节点
- 按 `grm` → 收缩到子节点

### 练习 4: 解决 mini.ai 与 treesitter 文本对象冲突

如果你同时用 `mini.ai`，尝试把 `an`/`in` 改为 `aa`/`ii`，然后测试：
- `vaa` 是否能选中下一个文本对象外侧
- `vii` 是否能选中下一个文本对象内部
- 再改回默认，观察 `van` 是否行为不一致

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 对比 treesitter 高亮开关的具体差异：
>
> 1. 打开一个包含嵌套结构的 Lua 文件（如一个带多个闭包的模块）
> 2. 执行 `:lua vim.treesitter.stop()` 后观察：
>    - 所有 tokens 退化为正则高亮——关键字、字符串、注释只有基本颜色
>    - **函数参数**失去独立颜色，全部变为默认文本色
>    - **嵌套函数**内外层函数名颜色相同，无法区分层级
>    - **模板字符串**中的插值表达式和普通字符串颜色一致
>    - `@param`、`@return` 等 LuaDoc 标签不再特殊高亮
> 3. 执行 `:lua vim.treesitter.start()` 恢复：
>    - **参数 `self`** 被高亮为特殊颜色（`@variable.builtin`）
>    - **函数调用** `foo(bar)` 中 `foo` 是 `@function` 色，参数 `bar` 是 `@variable.parameter` 色
>    - **table 构造器**中 key 和 value 可被赋予不同颜色组
>    - **代码注入**：Markdown 中的 Lua 代码块内部也有正确的 Lua 语法高亮
>
> **核心价值**：正则高亮基于文本模式匹配，"看到"的是字符序列；treesitter 基于 AST，"理解"的是语法结构。这就是为什么 treesitter 能正确高亮第 5 层嵌套的函数参数而正则高亮会"迷路"。

> [!tip]- 练习 2 参考答案
> 手动安装 parser 的详细步骤和输出解读：
>
> ```vim
> " 步骤 1: 查看已安装的 parsers
> :lua print(vim.inspect(require('nvim-treesitter').get_installed('parsers')))
> " 预期输出: { "bash", "c", "diff", "html", "lua", "luadoc", "markdown", ... }
>
> " 步骤 2: 安装 Rust parser
> :lua require('nvim-treesitter').install('rust')
> " 这将异步下载并编译 tree-sitter-rust
> " 注意：该操作需要 C 编译器（gcc/clang/MSVC）
>
> " 步骤 3: 验证
> :checkhealth treesitter
> " 检查 "Parser: rust" 行是否显示 "OK"
> ```
>
> `:checkhealth treesitter` 的关键输出行：
> - `Parser: rust ✓` — parser 已安装且可用
> - `Highlight (lua) ✓` — lua 的高亮 query 正常工作
> - `Installation` 部分会显示编译器检测结果（Windows 上常需要额外配置）
>
> **Windows 注意事项**：如果没有 C 编译器，`:checkhealth treesitter` 会报告 "No C compiler found"。需要安装 MSVC Build Tools 或 MinGW，并在 PATH 中可用。

> [!tip]- 练习 3 参考答案
> Neovim 0.12 内置增量选择的完整操作流程：
>
> | 按键 | 操作 | 效果 |
> |---|---|---|
> | `grn` | `vim.treesitter.incremental_selection('node')` | 选中光标所在的最小语法节点 |
> | `grn`（重复） | 同上 | 扩展到父节点（如：标识符 → 函数调用 → 赋值语句 → 函数体） |
> | `grm` | `vim.treesitter.incremental_selection('shrink')` | 收缩到上一级子节点 |
>
> **实践示例**（在 Lua 文件中）：
> 1. 光标放在 `local x = foo(bar(baz))` 的 `baz` 上
> 2. 按 `grn`：选中 `baz`（标识符节点）
> 3. 再按 `grn`：选中 `bar(baz)`（函数调用节点）
> 4. 再按 `grn`：选中 `foo(bar(baz))`（外层函数调用）
> 5. 再按 `grn`：选中 `foo(bar(baz))` 所属的整个赋值语句
> 6. 按 `grm`：收缩回 `foo(bar(baz))`
>
> **实用场景**：快速选中一个函数体（3 次 `grn`）然后 `y` 复制；选中一组参数（进入参数列表节点）然后 `c` 修改。
>
> **注意**：增量选择需要 treesitter parser 已附着到当前 buffer。如果按 `grn` 无反应，检查 treesitter 是否已启用（`:lua print(vim.treesitter.highlighter.active)` 应返回 true）。

> [!tip]- 练习 4 参考答案
> mini.ai 与 treesitter 内置文本对象冲突的解决方案：
>
> ```lua
> require('mini.ai').setup {
>   mappings = {
>     around_next = 'aa',
>     inside_next = 'ii',
>     -- 其余映射保持默认
>   },
>   n_lines = 500,
> }
> ```
>
> 验证：
> 1. 保存配置并重启 Neovim
> 2. 打开一个 Lua 文件，光标放在某个函数调用上
> 3. 按 `vaa`：应扩展选中"下一个文本对象"的外侧（mini.ai 行为）
> 4. 按 `vii`：应选中"下一个文本对象"的内部
> 5. 按 `van` / `vin`：现在由 Neovim 0.12 内置的 treesitter 文本对象处理，行为与 mini.ai 不同
>
> **设计意图**：Neovim 0.12 把 `an`/`in` 预留给 treesitter 文本对象，mini.ai 主动让位给 `aa`/`ii`。kickstart 采用的就是这种方案。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [nvim-treesitter 官方文档](https://github.com/nvim-treesitter/nvim-treesitter)
- [Tree-sitter 官网](https://tree-sitter.github.io/tree-sitter/)
- [`:help treesitter`](https://neovim.io/doc/user/treesitter.html)
- [`:help treesitter-incremental-selection`](https://neovim.io/doc/user/helptag.html?tag=treesitter-incremental-selection) — 0.12 内置增量选择
- [`:help lsp-vs-treesitter`](https://neovim.io/doc/user/lsp.html#lsp-vs-treesitter) — Treesitter 与 LSP 的能力边界
- [`:help treesitter-query`](https://neovim.io/doc/user/treesitter.html#treesitter-query) — query 语言

---

## 常见陷阱

- **Windows 上需要 C 编译器**：treesitter parser 需要编译。安装 MSVC 或 MinGW。`:checkhealth treesitter` 提供详细的诊断信息。
- **`require('nvim-treesitter').install()` 是异步的**：这也是为什么 kickstart 用 `:await()` 等待安装完成后再启用。
- **parser 名 ≠ filetype 名**：`.ts` 文件对应 parser `typescript`，但 `.js` 也对应 `javascript`。`vim.treesitter.language.get_lang(filetype)` 负责这个映射。
- **大文件性能**：treesitter 对超大文件（>1MB）可能变慢。可以在 `treesitter_try_attach` 中添加文件大小检查。
- **旧配置教程仍会教你 `:TSInstall`**：现代 main 分支推荐 `require('nvim-treesitter').install(...)`。
- **mini.ai 默认 `an`/`in` 与 0.12 内置文本对象冲突**：要么改 mini.ai 映射，要么禁用内置 treesitter 文本对象。
- **`vim.treesitter.start()` 只对当前 buffer 生效**：窗口切换后不会自动应用到新 buffer，需要 FileType autocmd 或手动调用。
- **query 文件位置**：自定义 query 应放在 `queries/<lang>/*.scm`，放在 plugin 目录下可能不被识别。
