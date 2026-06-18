---
title: "20 — 调试器：DAP (nvim-dap + nvim-dap-ui) 实战"
updated: 2026-06-18
---

# 20 — 调试器：DAP (nvim-dap + nvim-dap-ui) 实战

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 60 分钟
> 前置知识: [[16-project]]、[[09-modern-lsp]]、[[08-modern-plugin-patterns]]

---

## 1. 概念讲解

### 1.1 什么是 DAP

DAP（Debug Adapter Protocol，调试适配器协议）是调试领域的"LSP"：

- **LSP** 把编辑器的编辑/跳转/补全请求转发给语言服务器。
- **DAP** 把 Neovim 的断点/单步/变量查看请求转发给语言专属的调试适配器（Debug Adapter）。

```text
┌─────────────┐      DAP      ┌─────────────────┐      语言调试器      ┌──────────┐
│   Neovim    │  ───────────▶  │  Debug Adapter  │  ───────────────▶  │  debugee │
│  (nvim-dap) │  ◀───────────  │ (debugpy/codelldb/node2) │  ◀───────────────  │  你的程序  │
└─────────────┘               └─────────────────┘                    └──────────┘
```

Neovim 本身不内置任何语言调试器，它只提供 DAP 客户端框架。因此：

1. 安装 `nvim-dap`（客户端）。
2. 安装对应语言的 Debug Adapter（如 `debugpy`、`codelldb`）。
3. 在 Lua 里把 Adapter + 启动配置注册给 `nvim-dap`。

### 1.2 与 LSP 的类比

| 维度 | LSP | DAP |
|---|---|---|
| 协议 | Language Server Protocol | Debug Adapter Protocol |
| Neovim 角色 | 客户端 (`vim.lsp`) | 客户端 (`nvim-dap`) |
| 外部进程 | `lua-language-server`、`pyright` | `debugpy.adapter`、`codelldb` |
| 触发时机 | 打开文件自动 attach | 手动 `<F5>` / 断点触发 |
| 核心操作 | goto definition / rename / hover | continue / step / breakpoint / evaluate |
| 配置 API | `vim.lsp.config()` / `vim.lsp.enable()` | `dap.adapters.<name>` / `dap.configurations.<ft>` |

> [!IMPORTANT]
> `nvim-dap` 只负责协议通信，真正的断点解析、变量求值由 Debug Adapter 完成。如果 Adapter 没有正确安装或路径不对，调试会话会启动失败。

### 1.3 核心插件

| 插件 | 作用 | 是否必需 |
|---|---|---|
| `mfussenegger/nvim-dap` | DAP 客户端核心 | 是 |
| `rcarriga/nvim-dap-ui` | 变量/堆栈/断点/REPL/watch 的 UI 面板 | 强烈推荐 |
| `nvim-neotest/nvim-nio` | `nvim-dap-ui` 的异步依赖 | 是（安装） |
| `jay-babu/mason-nvim-dap.nvim` | 通过 Mason 自动安装 Debug Adapter | 推荐 |
| `theHamsta/nvim-dap-virtual-text` | 在当前行右侧虚拟文本显示变量值 | 可选 |

> [!NOTE]
> `nvim-dap-ui` 依赖 `nvim-nio`，所以 `vim.pack.add()` 时务必将它一起加入，否则 `require('dapui')` 会报错。

---

## 2. 代码示例

下面所有代码均要求 **Neovim 0.12.3+**。建议把它们作为一个新的 `do ... end` 块追加到 [[16-project]] 的单文件 `init.lua` 末尾，或拆分为 `lua/plugins/dap.lua`。

### 2.1 安装与基础配置

```lua
-- ==================================================================
-- DAP
-- ==================================================================
do
  local function gh(repo) return 'https://github.com/' .. repo end

  -- 1) 安装插件：nvim-nio 是 dap-ui 的依赖，不能漏
  vim.pack.add {
    gh 'mfussenegger/nvim-dap',
    gh 'rcarriga/nvim-dap-ui',
    gh 'nvim-neotest/nvim-nio',
    gh 'jay-babu/mason-nvim-dap.nvim',
    gh 'theHamsta/nvim-dap-virtual-text',
  }

  local dap = require 'dap'
  local dapui = require 'dapui'

  -- 2) 设置 UI 面板
  dapui.setup()

  -- 3) 通过 Mason 自动安装 debug adapters
  --    handlers = {} 表示对列出的 adapter 使用 mason-nvim-dap 的默认配置
  require('mason-nvim-dap').setup {
    ensure_installed = { 'python', 'codelldb', 'node2' },
    automatic_installation = true,
    handlers = {},
  }

  -- 4) 虚拟文本显示变量值
  require('nvim-dap-virtual-text').setup()

  -- 5) 自动开关 UI
  dap.listeners.before.attach.dapui_config = function() dapui.open() end
  dap.listeners.before.launch.dapui_config = function() dapui.open() end
  dap.listeners.before.event_terminated.dapui_config = function() dapui.close() end
  dap.listeners.before.event_exited.dapui_config = function() dapui.close() end
end
```

**运行方式：**

1. 把代码加入 `init.lua`。
2. 重启 Neovim，`vim.pack.add()` 会弹出确认安装对话框 → 按 `a` 允许全部。
3. 等待 `mason-nvim-dap` 自动下载 `debugpy`、`codelldb`、`node-debug2-adapter`。
4. 执行 `:checkhealth dap` 和 `:checkhealth dap-ui` 确认无报错。

### 2.2 按键映射

```lua
-- 在 DAP 块内部继续追加
local dap = require 'dap'
local dapui = require 'dapui'

-- 标准调试键位（与 VSCode 一致）
vim.keymap.set('n', '<F5>', dap.continue, { desc = 'Debug: Continue' })
vim.keymap.set('n', '<F10>', dap.step_over, { desc = 'Debug: Step over' })
vim.keymap.set('n', '<F11>', dap.step_into, { desc = 'Debug: Step into' })
vim.keymap.set('n', '<F12>', dap.step_out, { desc = 'Debug: Step out' })

-- 断点
vim.keymap.set('n', '<leader>b', dap.toggle_breakpoint, { desc = 'Debug: Toggle breakpoint' })
vim.keymap.set('n', '<leader>B', function()
  dap.set_breakpoint(vim.fn.input 'Breakpoint condition: ')
end, { desc = 'Debug: Conditional breakpoint' })

-- REPL / 求值
vim.keymap.set('n', '<leader>dr', dap.repl.toggle, { desc = 'Debug: Toggle REPL' })
vim.keymap.set('n', '<leader>de', function()
  dapui.eval(vim.fn.input 'Expression: ')
end, { desc = 'Debug: Evaluate expression' })
```

> [!TIP]
> 条件断点在循环或递归中非常有用，例如输入 `i > 10`，调试器只会在变量 `i` 大于 10 时停下。

### 2.3 语言适配器配置

#### Python（debugpy）

```lua
local dap = require 'dap'

dap.adapters.python = function(cb, config)
  if config.request == 'attach' then
    local port = (config.connect or config).port
    local host = (config.connect or config).host or '127.0.0.1'
    cb {
      type = 'server',
      port = assert(port, '`connect.port` is required'),
      host = host,
      options = { source_filetype = 'python' },
    }
  else
    cb {
      type = 'executable',
      command = 'python', -- 或 'python3'，需保证 debugpy 已安装
      args = { '-m', 'debugpy.adapter' },
      options = { source_filetype = 'python' },
    }
  end
end

dap.configurations.python = {
  {
    type = 'python',
    request = 'launch',
    name = 'Python: Launch file',
    program = '${file}',
    pythonPath = function()
      local cwd = vim.fn.getcwd()
      if vim.fn.executable(cwd .. '/.venv/bin/python') == 1 then
        return cwd .. '/.venv/bin/python'
      elseif vim.fn.executable(cwd .. '/venv/bin/python') == 1 then
        return cwd .. '/venv/bin/python'
      elseif vim.env.VIRTUAL_ENV then
        return vim.env.VIRTUAL_ENV .. '/bin/python'
      else
        return 'python3'
      end
    end,
    console = 'integratedTerminal',
  },
}
```

#### C/C++（codelldb）

```lua
local dap = require 'dap'

-- codelldb 1.11.0+ 支持 stdio，命令名为 codelldb（Mason 会把它加入 PATH）
dap.adapters.codelldb = {
  type = 'executable',
  command = 'codelldb',
}

dap.configurations.cpp = {
  {
    name = 'LLDB: Launch file',
    type = 'codelldb',
    request = 'launch',
    program = function()
      return vim.fn.input('Path to executable: ', vim.fn.getcwd() .. '/', 'file')
    end,
    cwd = '${workspaceFolder}',
    stopOnEntry = false,
  },
}

-- 让 c 和 rust 复用同一套配置
dap.configurations.c = dap.configurations.cpp
dap.configurations.rust = dap.configurations.cpp
```

> [!NOTE]
> Windows 下如果 codelldb 闪退，尝试在 adapter 里加 `detached = false`。

#### JavaScript / TypeScript（node2）

`mason-nvim-dap` 已经自动注册了 `node2` adapter，所以这里只需要写启动配置：

```lua
local dap = require 'dap'

dap.configurations.javascript = {
  {
    name = 'Node2: Launch file',
    type = 'node2',
    request = 'launch',
    program = '${file}',
    cwd = '${workspaceFolder}',
    sourceMaps = true,
    protocol = 'inspector',
    console = 'integratedTerminal',
  },
  {
    name = 'Node2: Attach to process',
    type = 'node2',
    request = 'attach',
    processId = require('dap.utils').pick_process,
  },
}

-- TypeScript 复用 JavaScript 配置
dap.configurations.typescript = dap.configurations.javascript
```

> [!WARNING]
> `node2` 是较老的 Node 调试器。对于现代 Node 项目，推荐使用 `pwa-node`（`vscode-js-debug`），但需要手动指定 `dapDebugServer.js` 的路径。可以通过 `:Mason` 查看 `js-debug-adapter` 的实际安装路径。

### 2.4 launch.json 支持

`nvim-dap` 内置了 `.vscode/launch.json` 配置提供器。只要项目根目录存在 `.vscode/launch.json`，按 `<F5>` 时就会自动列出其中的配置。

示例 `.vscode/launch.json`：

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal"
    }
  ]
}
```

如果需要从非标准路径加载，可以在配置里显式调用：

```lua
require('dap.ext.vscode').load_launchjs('/path/to/launch.json')
```

### 2.5 调试流程

1. **打开源码**（如 `main.py`）。
2. **设断点**：光标移到目标行，按 `<leader>b`。
3. **启动调试**：按 `<F5>`，`dap-ui` 自动打开。
4. **查看状态**：左侧 `scopes` 看变量，`stacks` 看调用栈，`watches` 添加表达式。
5. **单步**：`<F10>` step over、`<F11>` step into、`<F12>` step out。
6. **继续/停止**：`<F5>` 继续运行，或 `:lua require('dap').terminate()` 终止。
7. **REPL 求值**：按 `<leader>dr` 打开 REPL，输入 Python/JS 表达式求值。

> [!TIP]
> 如果 UI 意外关闭，可以用 `:lua require('dapui').open()` 手动打开；想临时隐藏用 `:lua require('dapui').toggle()`。

---

## 3. 练习

### 练习 1: 为 Python 配置 debugpy

在 DAP 配置块里补全 `dap.adapters.python` 和 `dap.configurations.python`，确保 `python -m debugpy.adapter` 可以在终端正常运行。

### 练习 2: 调试一个简单脚本

创建一个 `test_debug.py`：

```python
x = 1
y = 2
z = x + y
print(z)
```

在第 3 行设断点，按 `<F5>` 启动，验证：

- 程序在断点处停下。
- `scopes` 面板显示 `x = 1`、`y = 2`。
- 按 `<F10>` 后 `z` 变为 `3`。

### 练习 3: 为 C/C++ 或 JavaScript 添加 launch 配置

任选一种语言，在 `dap.configurations` 里新增一个配置：

- C/C++：调试一个已编译好的可执行文件（需要 `-g` 编译出 debug symbols）。
- JavaScript：调试一个 `index.js`，并尝试附加到已经运行的 Node 进程。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```lua
> local dap = require 'dap'
>
> dap.adapters.python = function(cb, config)
>   if config.request == 'attach' then
>     local port = (config.connect or config).port
>     local host = (config.connect or config).host or '127.0.0.1'
>     cb { type = 'server', port = port, host = host, options = { source_filetype = 'python' } }
>   else
>     cb {
>       type = 'executable',
>       command = 'python3',
>       args = { '-m', 'debugpy.adapter' },
>       options = { source_filetype = 'python' },
>     }
>   end
> end
>
> dap.configurations.python = {
>   {
>     type = 'python',
>     request = 'launch',
>     name = 'Python: Launch file',
>     program = '${file}',
>     pythonPath = function()
>       local cwd = vim.fn.getcwd()
>       for _, p in ipairs { cwd .. '/.venv/bin/python', cwd .. '/venv/bin/python', 'python3' } do
>         if vim.fn.executable(p) == 1 then return p end
>       end
>       return 'python3'
>     end,
>     console = 'integratedTerminal',
>   },
> }
> ```
>
> **关键点：**
> - `command` 必须是带 `debugpy` 的 Python 解释器；如果系统 Python 没有安装 `debugpy`，可以先执行 `python3 -m pip install debugpy`。
> - `program = '${file}'` 表示调试当前文件。
> - 使用 `pythonPath` 函数自动优先使用项目虚拟环境。

> [!tip]- 练习 2 参考答案
> 1. 创建 `test_debug.py` 并写入题目中的代码。
> 2. 在 Neovim 中打开它，把光标移到 `z = x + y` 这一行，按 `<leader>b`。
> 3. 按 `<F5>`，Neovim 会弹出配置选择（如果只有一个 Python 配置则直接启动）。
> 4. 观察左侧 `scopes` 面板：展开 `Locals` 应能看到 `x = 1`、`y = 2`。
> 5. 按 `<F10>` 执行 `z = x + y`，`Locals` 中应出现 `z = 3`。
> 6. 再按 `<F5>`，程序继续运行，终端输出 `3`。
>
> **排错提示：**
> - 如果断点显示为灰色 "unverified"，说明 debugpy 没有正确映射源码路径，检查 `program` 是否指向当前文件。
> - 如果 `<F5>` 后没反应，执行 `:lua require('dap').set_log_level('TRACE')`，然后在 `:lua print(vim.fn.stdpath('cache'))` 对应目录下查看 `dap.log`。

> [!tip]- 练习 3 参考答案
> **C/C++ 示例（codelldb）：**
>
> ```lua
> dap.configurations.cpp = {
>   {
>     name = 'LLDB: Launch file',
>     type = 'codelldb',
>     request = 'launch',
>     program = function()
>       return vim.fn.input('Path to executable: ', vim.fn.getcwd() .. '/', 'file')
>     end,
>     cwd = '${workspaceFolder}',
>     stopOnEntry = false,
>   },
> }
> dap.configurations.c = dap.configurations.cpp
> dap.configurations.rust = dap.configurations.cpp
> ```
>
> 编译测试程序时要带 debug symbols：
>
> ```bash
> gcc -g -o hello hello.c
> ```
>
> **JavaScript 示例（node2）：**
>
> ```lua
> dap.configurations.javascript = {
>   {
>     name = 'Node2: Launch file',
>     type = 'node2',
>     request = 'launch',
>     program = '${file}',
>     cwd = '${workspaceFolder}',
>     sourceMaps = true,
>     protocol = 'inspector',
>     console = 'integratedTerminal',
>   },
>   {
>     name = 'Node2: Attach',
>     type = 'node2',
>     request = 'attach',
>     processId = require('dap.utils').pick_process,
>   },
> }
> ```
>
> 附加调试前需要先用 `--inspect` 启动目标进程：
>
> ```bash
> node --inspect-brk index.js
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [nvim-dap 官方文档](https://github.com/mfussenegger/nvim-dap/blob/master/doc/dap.txt) — 完整的 API 与事件说明
- [nvim-dap-ui README](https://github.com/rcarriga/nvim-dap-ui) — UI 面板与默认快捷键
- [Debug Adapter 安装指南](https://codeberg.org/mfussenegger/nvim-dap/wiki/Debug-Adapter-installation) — 各语言适配器配置
- [mason-nvim-dap.nvim](https://github.com/jay-babu/mason-nvim-dap.nvim) — Mason 与 DAP 的桥接插件
- [DAP 协议规范](https://microsoft.github.io/debug-adapter-protocol/) — 理解底层请求与事件

---

## 常见陷阱

- **忘记安装 `nvim-nio`**：`nvim-dap-ui` 需要它作为依赖，缺少时会报模块找不到。
- **adapter 名称与配置 `type` 不匹配**：例如 adapter 叫 `python`，配置的 `type` 也必须是 `python`。
- **codelldb 在 Windows 下 detached 默认 true 导致闪退**：加上 `detached = false` 试试。
- **JS/TS 断点不生效**：`sourceMaps` 需要正确配置；TypeScript 需要先编译并保留 source map。
- **`.vscode/launch.json` 没被读取**：确保文件在项目根目录，且 JSON 没有语法错误；也可用 `:lua require('dap.ext.vscode').load_launchjs()` 手动加载。
- **mason-nvim-dap 没触发默认 setup**：`handlers = {}` 表示启用默认 handler；如果设为 `nil`，需要手动写 `dap.adapters`。
