---
title: "21 — 性能优化与故障排查：vim.loader/profiling/checkhealth"
updated: 2026-06-18
---

# 21 — 性能优化与故障排查：vim.loader/profiling/checkhealth

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 50 分钟
> 前置知识: [[16-project]]、[[20-dap-debugging]]

---

## 1. 概念讲解

### 1.1 启动性能优化的三个层次

| 层次 | 手段 | 效果 |
|---|---|---|
| 加速 Lua 模块加载 | `vim.loader.enable()` | 缓存编译后的 Lua 字节码，启动明显变快 |
| 延迟非关键初始化 | `vim.schedule()` / autocmd | 把剪贴板、插件设置推迟到启动后 |
| 减少启动时加载的插件 | 按需 `vim.pack.add()`、事件触发加载 | 降低首次启动的插件数量 |

### 1.2 `vim.loader.enable()` 为什么放在第一行

`vim.loader.enable()` 启用 Lua 模块缓存。它会把 `require()` 过的 Lua 文件编译结果缓存到磁盘，下次启动时直接加载字节码，避免重复解析。

- **位置要求**：必须放在 `init.lua` 第一行，在任何一个 `require()` 之前。
- **实验性但稳定**：Folke（Lazy.nvim 作者）与 kickstart.nvim 都默认启用，0.12 中可放心使用。
- **副作用极小**：缓存目录在 `vim.fn.stdpath('cache') .. '/luac'`，删除后自动重建。

### 1.3 延迟耗时选项示例

剪贴板同步（尤其是 `unnamedplus`）在部分系统上可能需要几百毫秒。用 `vim.schedule()` 把它放到事件循环的下一轮：

```lua
vim.schedule(function()
  vim.o.clipboard = 'unnamedplus'
end)
```

### 1.4 懒加载插件

`vim.pack` 没有 lazy.nvim 的 `event = 'VeryLazy'` 字段，但可以用同样自然的 Lua 实现：

```lua
-- 方式 1：启动后异步加载
vim.schedule(function()
  vim.pack.add { 'https://github.com/folke/which-key.nvim' }
  require('which-key').setup {}
end)

-- 方式 2：按事件触发加载（一次性）
vim.api.nvim_create_autocmd('InsertEnter', {
  once = true,
  callback = function()
    vim.pack.add { 'https://github.com/saghen/blink.cmp' }
    require('blink.cmp').setup {}
  end,
})
```

参考 [[08-modern-plugin-patterns]] 了解更完整的懒加载模式。

### 1.5 运行时性能要点

| 场景 | 问题 | 常见优化 |
|---|---|---|
| 打开大文件 | Treesitter 解析变慢 | 按 filetype 禁用 treesitter 或增大禁用阈值 |
| 大项目 LSP | 文件监听占用大量资源 | 关闭 `didChangeWatchedFiles` |
| 诊断刷新太频繁 | `updatetime` 过短 | 保持 `250` 或根据文件大小动态调整 |
| 按键序列超时 | `timeoutlen` 过短 | 默认 `300` 通常合适；使用 `<nowait>` 避免映射等待 |

### 1.6 故障排查框架

当配置出现"插件不加载"、"LSP 不附着"、"按键没反应"等问题时，按以下顺序排查：

1. `:checkhealth` 看全局健康状态。
2. `:checkhealth vim.lsp` / `:checkhealth vim.pack` / `:checkhealth vim.treesitter` 看子系统。
3. `:verbose map <key>` 查看按键映射来源。
4. `:verbose set number?` 查看选项来源。
5. `:verbose autocmd BufReadPre` 查看自动命令来源。
6. `:lua =vim.lsp.get_clients()` 查看当前附着的 LSP 客户端。
7. `:InspectTree` / `:lua =vim.treesitter.get_captures_at_pos(...)` 查看 treesitter 解析。
8. `:set runtimepath?` / `:lua =vim.api.nvim_list_runtime_paths()` 检查 runtime path。
9. `:lua =package.loaded` 查看已加载模块。

---

## 2. 代码示例

### 2.1 测量启动时间

Neovim 自带启动耗时分析：

```bash
nvim --startuptime startup.log -c 'q'
```

生成的 `startup.log` 每行格式如下：

```text
count  total(ms)   self(ms)  module
   1   12.345000   0.123000  /path/to/plugin.lua
```

- **total**：该阶段累计耗时（含子调用）。
- **self**：该文件自身执行耗时。
- 按 `self` 或 `total` 降序查找最大的几项，就是优化重点。

也可以写一个简单脚本自动排序：

```bash
nvim --startuptime /tmp/startup.log -c 'q' && \
  sort -k3 -n -r /tmp/startup.log | head -n 20
```

### 2.2 优化后的 Foundation 块

```lua
-- ~/.config/nvim/init.lua

-- 1) 第一行：启用 Lua 模块缓存
vim.loader.enable()

-- 2) 全局 leader（必须在任何按键映射之前）
vim.g.mapleader = ' '
vim.g.maplocalleader = ' '

-- 3) 核心选项
do
  vim.o.number = true
  vim.o.mouse = 'a'
  vim.o.showmode = false
  vim.o.breakindent = true
  vim.o.undofile = true
  vim.o.ignorecase = true
  vim.o.smartcase = true
  vim.o.signcolumn = 'yes'
  vim.o.updatetime = 250
  vim.o.timeoutlen = 300
  vim.o.splitright = true
  vim.o.splitbelow = true
  vim.o.inccommand = 'split'
  vim.o.cursorline = true
  vim.o.scrolloff = 10
  vim.o.confirm = true

  -- 延迟设置剪贴板，避免启动时同步阻塞
  vim.schedule(function()
    vim.o.clipboard = 'unnamedplus'
  end)
end
```

### 2.3 大项目关闭 LSP 文件监听

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local client = vim.lsp.get_client_by_id(ev.data.client_id)
    if not client then return end

    -- 关闭文件系统监听，减少大项目下的 CPU/IO 占用
    if client.capabilities.workspace and client.capabilities.workspace.didChangeWatchedFiles then
      client.capabilities.workspace.didChangeWatchedFiles = nil
    end
  end,
})
```

### 2.4 大文件禁用 Treesitter

```lua
vim.api.nvim_create_autocmd('FileType', {
  callback = function(args)
    local buf = args.buf
    local max_lines = 10000
    local line_count = vim.api.nvim_buf_line_count(buf)

    if line_count > max_lines then
      vim.notify(('File too large (%d lines); disabling treesitter'):format(line_count), vim.log.levels.WARN)
      vim.treesitter.stop(buf)
    end
  end,
})
```

### 2.5 查看按键映射与选项来源

```vim
" 查看 <leader>f 是被谁定义的
:verbose map <leader>f

" 查看 number 选项最后设置位置
:verbose set number?

" 查看 BufReadPre 上的自动命令
:verbose autocmd BufReadPre
```

### 2.6 查看 LSP 状态

```vim
" 0.12 中替代旧 :LspInfo
:checkhealth vim.lsp

" Lua 方式查看当前 buffer 的客户端
:lua =vim.lsp.get_clients({ bufnr = 0 })

" 查看某个客户端支持的方法
:lua =vim.lsp.get_client_by_id(1).server_capabilities
```

### 2.7 查看 Treesitter 捕获

```vim
" 打开当前文件的 treesitter 解析树
:InspectTree

" 查看光标位置的 capture 名称
:lua =vim.treesitter.get_captures_at_pos(0, vim.api.nvim_win_get_cursor(0)[1] - 1, vim.api.nvim_win_get_cursor(0)[2])
```

### 2.8 处理弃用 API 警告

0.12 中常见的重命名/弃用：

```lua
-- 旧 → 新
vim.highlight.on_yank()    -- ❌ 已弃用
vim.hl.on_yank()           -- ✅ 0.11+

client.request(...)        -- ❌ 旧函数调用
client:request(...)        -- ✅ 0.11+ 方法调用

-- vim.validate 旧 table 形式
vim.validate({ name = { 'foo', 'string' } }) -- ❌
vim.validate('name', 'foo', 'string')        -- ✅ 新形式
```

如果插件报 `vim.deprecate` 警告，Neovim 会提示替代方案。你也可以主动检查：

```lua
-- 打开通知历史
:messages
```

### 2.9 用 `NVIM_APPNAME` 隔离测试

想试验新插件或迁移配置，又不想破坏现有环境：

```bash
# 使用 ~/.config/nvim-test 作为独立配置目录
NVIM_APPNAME=nvim-test nvim
```

对应的目录结构：

```text
~/.config/nvim-test/
├── init.lua
└── ...
```

这相当于给 Neovim 一个"沙盒"，适合测试 `vim.pack` 升级、新 LSP 或 DAP 配置。


### 2.10 用 `:profile` 定位运行时卡顿

如果 Neovim 在使用过程中偶尔卡顿，可以用内置 profiler：

```vim
" 开始记录
:profile start /tmp/profile.log
:profile func *
:profile file *

" 执行你觉得卡的操作

" 停止并保存
:profile dump
:profile stop
```

然后查看 `/tmp/profile.log`，按 `self` 时间排序，定位耗时函数。

也可以用 Lua 简单计时某个函数：

```lua
local t0 = vim.uv.hrtime()
-- 你要测量的代码
local t1 = vim.uv.hrtime()
print(('Elapsed: %.3f ms'):format((t1 - t0) / 1e6))
```

---

## 3. 练习

### 练习 1: 测量启动时间

运行：

```bash
nvim --startuptime /tmp/startup.log -c 'q'
```

找出 `self` 耗时最高的前 5 个条目，判断它们是核心 Neovim 模块还是插件。

### 练习 2: 用 checkhealth 排查一个模拟问题

假设你打开 `.lua` 文件后发现 LSP 没有附着，按以下步骤排查并记录结果：

1. `:checkhealth vim.lsp`
2. `:lua =vim.lsp.get_clients({ bufnr = 0 })`
3. `:echo executable('lua-language-server')`
4. `:verbose autocmd LspAttach`

### 练习 3: 用 `NVIM_APPNAME` 隔离测试新插件

创建 `~/.config/nvim-minimal/init.lua`，只包含 `vim.loader.enable()` 和一个你最想测试的插件（如 `tokyonight.nvim`）。用 `NVIM_APPNAME=nvim-minimal nvim` 启动，确认它能独立工作。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 1. 执行命令：
>
> ```bash
> nvim --startuptime /tmp/startup.log -c 'q'
> ```
>
> 2. 查看前 5 行：
>
> ```bash
> sort -k3 -n -r /tmp/startup.log | head -n 5
> ```
>
> 3. 典型结果解读：
>
> | 条目 | 含义 | 优化方向 |
> |---|---|---|
> | `require('nvim-treesitter')` | treesitter 加载 | 延迟到 `FileType` 事件再加载 |
> | `require('blink.cmp')` | 补全引擎初始化 | 可延迟到 `InsertEnter` |
> | `require('telescope')` | 模糊查找 | 按需按键触发 |
> | `vim.pack.add()` 首次同步安装 | 插件下载/构建 | 首次安装后_cached，后续启动会快 |
> | 剪贴板初始化 | `vim.o.clipboard` | 用 `vim.schedule()` 延迟 |
>
> **关键点：** 先看 `self` 列，它代表该文件自身执行时间；`total` 包含子 `require` 的累计时间。优化时优先削 `self` 大的模块。

> [!tip]- 练习 2 参考答案
> 假设 LSP 没有附着，排查流程如下：
>
> 1. `:checkhealth vim.lsp` —— 检查是否有 "Configuration enabled" 与 "Active clients" 信息。如果 `lua_ls` 没有启用，说明 `vim.lsp.enable('lua_ls')` 没执行。
>
> 2. `:lua =vim.lsp.get_clients({ bufnr = 0 })` —— 返回空表 `{}` 表示当前 buffer 没有 LSP 客户端。可能原因：
>    - `vim.lsp.enable('lua_ls')` 没调用。
>    - `lua-language-server` 不在 PATH。
>    - root_markers 不匹配，导致 Neovim 认为当前文件不属于项目。
>
> 3. `:echo executable('lua-language-server')` —— 返回 `0` 说明 Mason 还没装好或 PATH 没刷新。重启 Neovim 或运行 `:Mason` 手动安装。
>
> 4. `:verbose autocmd LspAttach` —— 查看是否有 `LspAttach` 自动命令。如果有但 LSP 没附着，说明事件根本没触发，问题在 LSP 启动阶段。
>
> **修复顺序：** 确认 `vim.lsp.config('lua_ls', ...)` + `vim.lsp.enable('lua_ls')` → 确认 `lua-language-server` 已安装 → 确认文件在项目根目录（有 `.git` 或 `.luarc.json`）→ 重启 Neovim。

> [!tip]- 练习 3 参考答案
> 1. 创建目录和文件：
>
> ```bash
> mkdir -p ~/.config/nvim-minimal/lua
> cat > ~/.config/nvim-minimal/init.lua <<'EOF'
> vim.loader.enable()
> vim.g.mapleader = ' '
>
> vim.pack.add { 'https://github.com/folke/tokyonight.nvim' }
> require('tokyonight').setup {}
> vim.cmd.colorscheme 'tokyonight-night'
> EOF
> ```
>
> 2. 用沙盒启动：
>
> ```bash
> NVIM_APPNAME=nvim-minimal nvim
> ```
>
> 3. 验证：界面应显示 tokyonight 配色；执行 `:checkhealth vim.pack` 应只显示 `tokyonight.nvim`。
>
> **沙盒价值：** 你可以安全地删除 `~/.config/nvim-minimal` 或在里面尝试破坏性升级，而不影响主配置。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [`:help vim.loader`](https://neovim.io/doc/user/lua.html#vim.loader) — Lua 模块缓存机制
- [`:help startup-timing`](https://neovim.io/doc/user/starting.html#--startuptime) — `--startuptime` 说明
- [`:help checkhealth`](https://neovim.io/doc/user/pi_health.html#:checkhealth) — 健康检查框架
- [`:help vim.deprecate()`](https://neovim.io/doc/user/lua.html#vim.deprecate()) — 弃用提示 API
- [Neovim 0.12 新闻](https://neovim.io/doc/user/news-0.12.html) — 新版 API 与行为变更
- [kickstart.nvim 的选项块](https://github.com/nvim-lua/kickstart.nvim/blob/master/init.lua) — `vim.loader.enable()` 的实际位置

---

## 常见陷阱

- **`vim.loader.enable()` 不在第一行**：一旦某个 `require()` 在它之前执行，缓存对那个模块不生效。
- **盲目追求启动时间**：把核心功能（如 LSP、diagnostics）过度延迟会导致首次编辑体验变差。
- **忽略 `:checkhealth` 子命令**：`checkhealth vim.lsp` 比 `:LspInfo` 更全，0.12 已移除 `:LspInfo`。
- **用 `:verbose map` 查不到默认映射**：0.12 的默认 LSP 映射是全局的，用 `:nmap grn` 即可看到；如果看不到，说明被其他插件清除了。
- **`client.request` vs `client:request()`**：0.11+ 中 LSP 客户端是对象，方法调用用冒号。旧代码迁移时要注意。
- **大文件禁用 treesitter 后没有语法高亮**：这是预期行为——可以保留 Vim 正则高亮，或在 `FileType` 里只对超大文件禁用。
- **误删 lockfile**：`nvim-pack-lock.json` 损坏时不要手动编辑，直接删除并让 `vim.pack` 重建更安全。