---
title: "11 — Treesitter：语法高亮与结构化分析"
updated: 2026-06-05
---

# 11 — Treesitter：语法高亮与结构化分析

> 所属计划: Neovim + Lua 配置实战 (现代版)
> 预计耗时: 45 分钟
> 前置知识: 07-vim-pack（插件管理）

---

## 1. 概念讲解

### Tree-sitter 的价值

Tree-sitter 将源代码解析成**具体语法树（CST）**。与传统的正则高亮相比：

| 特性 | 正则高亮 | Tree-sitter |
|------|---------|------------|
| 准确性 | 模式匹配，嵌套易出错 | 语法解析，100% 准确 |
| 速度 | O(n) 扫描 | 增量解析 |
| 功能 | 高亮 | 高亮、折叠、缩进、选区扩展、代码注入 |

### kickstart 的 Treesitter 策略

kickstart.nvim 采用了**按需安装**的策略，区别于旧式的 `ensure_installed` 列表：

1. **预装基础 parsers**: `bash, c, diff, html, lua, luadoc, markdown, markdown_inline, query, vim, vimdoc`
2. **按需安装**: 首次打开某语言文件时，自动安装对应的 parser
3. **构建钩子**: `PackChanged` autocmd 在安装/更新后自动运行 `:TSUpdate`

### nvim-treesitter 0.12+ API 变化

```lua
-- 旧 API (0.11-):
require('nvim-treesitter.configs').setup({
  ensure_installed = { "lua", "python", ... },
  highlight = { enable = true },
})

-- 新 API (0.12+, kickstart 风格):
require('nvim-treesitter').install { 'lua', 'bash', 'c', ... }

-- 手动启用某语言的 treesitter
vim.treesitter.start(buf, language)
```

关键变化：
- 不再用全局的 `configs.setup()` 开启所有功能
- 改为用 `vim.treesitter.start()` 按 buffer 精确控制
- `ensure_installed` → `require('nvim-treesitter').install()`

### 按需安装的自动命令

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

---

## 2. 代码示例

### 完整的 kickstart 风格 Treesitter 配置

```lua
-- init.lua Section: Treesitter
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
      vim.bo.indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
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

---

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
- `grm` → 收缩到子节点


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
> |------|------|------|
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

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [nvim-treesitter 官方文档](https://github.com/nvim-treesitter/nvim-treesitter)
- [Tree-sitter 官网](https://tree-sitter.github.io/tree-sitter/)
- [`:help treesitter`](https://neovim.io/doc/user/treesitter.html)
- [`:help treesitter-incremental-selection`](https://neovim.io/doc/user/helptag.html?tag=treesitter-incremental-selection) — 0.12 内置增量选择

---

## 常见陷阱

- **Windows 上需要 C 编译器**：treesitter parser 需要编译。安装 MSVC 或 MinGW。`:checkhealth treesitter` 提供详细的诊断信息。
- **`require('nvim-treesitter').install()` 是异步的**：这也是为什么 kickstart 用 `:await()` 等待安装完成后再启用。
- **parser 名 ≠ filetype 名**：`.ts` 文件对应 parser `typescript`，但 `.js` 也对应 `javascript`。`vim.treesitter.language.get_lang(filetype)` 负责这个映射。
- **大文件性能**：treesitter 对超大文件（>1MB）可能变慢。kickstart 没有内置大文件保护——可以在 `treesitter_try_attach` 中添加文件大小检查。
