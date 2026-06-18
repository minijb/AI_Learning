---
title: "12 — Telescope：模糊查找一切"
updated: 2026-06-18
---

# 12 — Telescope：模糊查找一切

> 所属计划: Neovim + Lua 配置实战 (现代深化版)
> 预计耗时: 50 分钟
> 前置知识: [[07-vim-pack]]、[[08-modern-plugin-patterns]]、[[09-modern-lsp]]

---

## 1. 概念讲解

### Telescope 能做什么？

Telescope 是 Neovim 的通用模糊查找界面。它把 "找文件 / 搜文本 / 查符号 / 看诊断" 等需求统一到一个可交互的浮动窗口中：输入过滤字符串，实时看到结果，按 `<CR>` 打开。

| 需求 | 对应 picker | 常用映射 |
|------|------------|---------|
| 查找文件 | `find_files` | `<leader>ff` |
| 实时 grep | `live_grep` | `<leader>fg` |
| 查找字符串（光标下） | `grep_string` | `<leader>fW` |
| 查找缓冲区 | `buffers` | `<leader>fb` |
| 最近文件 | `oldfiles` | `<leader>fr` |
| 帮助标签 | `help_tags` | `<leader>fh` |
| 按键映射 | `keymaps` | `<leader>fk` |
| 命令历史 | `commands` / `command_history` | `<leader>:` |
| 恢复上次 picker | `resume` | `<leader>f.` |
| 内置 picker 列表 | `builtin` | `<leader>sb` |
| Git 文件 | `git_files` | `<leader>gf` |
| Git 分支 / commit | `git_branches` / `git_commits` | `<leader>gB` / `<leader>gc` |
| LSP 引用 / 实现 | `lsp_references` / `lsp_implementations` | `grr` / `gri` |
| LSP 文档符号 | `lsp_document_symbols` | `gO` / `<leader>fs` |
| LSP 工作区符号 | `lsp_workspace_symbols` | `<leader>fS` |
| LSP 类型定义 | `lsp_type_definitions` | `grt` |
| LSP 诊断 | `diagnostics` | `<leader>fd` |

### 工作原理

```
用户输入的模糊串
        ↓
Picker（选择器：find_files / live_grep / ...）
        ↓
Sorter（排序器：fzf-native / fzy / 内置）
        ↓
Previewer（预览窗口：内置 / delta / bat）
        ↓
Action（打开 / 分割 / 删除 / 复制路径 …）
```

- **Picker** 决定数据来源；
- **Sorter** 决定结果排序质量；
- **Previewer** 在右侧/下方实时预览文件内容；
- **Action** 把选中项映射到编辑器操作。

### 布局策略与主题

Telescope 提供多种布局策略（`layout_strategy`）和主题（`themes`）：

| 策略/主题 | 特点 | 适用场景 |
|----------|------|---------|
| `horizontal`（默认） | 左侧列表 + 右侧预览 | 宽屏 |
| `vertical` | 上中下：输入 / 列表 / 预览 | 窄屏、类 VS Code |
| `center` | 居中一个小窗口 | 快速切换 |
| `dropdown`（主题） | 紧凑居中下拉 | `buffers`、`colorscheme` |
| `cursor`（主题） | 跟随光标位置 | 小范围选择 |
| `ivy`（主题） | 底部全宽条带 | 类似 Emacs ivy |

主题通过 `require('telescope.themes').get_xxx()` 生成一个 options table，再传给 `pickers.xxx` 或 `setup()`。

### 窗口内快捷键

在 Telescope 窗口中，默认按键如下：

| 按键 | 操作 |
|------|------|
| `<C-n>` / `<C-p>` | 下 / 上一个结果 |
| `<CR>` | 打开 |
| `<C-v>` | 垂直分割打开 |
| `<C-x>` | 水平分割打开 |
| `<C-t>` | 新 Tab 打开 |
| `<C-u>` / `<C-d>` | 预览窗口向上 / 向下滚动 |
| `<C-/>`（插入模式） | 显示 picker 内可用按键帮助 |
| `?`（普通模式） | 显示 picker 内可用按键帮助 |
| `<C-c>` | 关闭 picker |

> [!TIP]
> 在 picker 窗口里按 `<C-/>` 或 `?` 是**学习 Telescope 最快的方式**。不同 picker 的可用动作不同，帮助页会列出当前 picker 支持的所有动作。

---

## 2. 代码示例

### 完整 kickstart 风格 Telescope 配置

```lua
-- init.lua 的 Search & Navigation section（Neovim 0.12.3+）
do
  local gh = function(repo) return 'https://github.com/' .. repo end
  local builtin = require 'telescope.builtin'

  -- ====== 核心依赖 ======
  vim.pack.add { gh 'nvim-lua/plenary.nvim' }

  -- ====== Telescope 本体 ======
  vim.pack.add { gh 'nvim-telescope/telescope.nvim' }
  require('telescope').setup {
    defaults = {
      -- 窗口内按键（插入模式）
      mappings = {
        i = {
          ['<C-j>'] = 'move_selection_next',
          ['<C-k>'] = 'move_selection_previous',
          ['<C-u>'] = 'preview_scrolling_up',
          ['<C-d>'] = 'preview_scrolling_down',
          ['<Esc>'] = 'close',
        },
        n = {
          ['q'] = 'close',
        },
      },

      -- 布局：水平（宽屏）
      layout_strategy = 'horizontal',
      layout_config = {
        horizontal = {
          preview_width = 0.55,
          prompt_position = 'top',
        },
      },

      -- 排序：先按得分，再按索引
      sorting_strategy = 'ascending',

      -- 文件忽略
      file_ignore_patterns = {
        'node_modules/',
        '.git/',
        'target/',
        'build/',
        'dist/',
        '%.pyc',
      },

      -- 预览限制
      preview = {
        filesize_limit = 0.5,  -- 超过 0.5 MB 不预览
        timeout = 250,         -- 预览超时 ms
      },
    },

    -- 各 picker 默认参数
    pickers = {
      find_files = {
        hidden = true,
        find_command = { 'rg', '--files', '--hidden', '--glob', '!**/.git/*' },
      },
      live_grep = {
        additional_args = function() return { '--hidden' } end,
      },
      buffers = {
        sort_lastused = true,
        theme = 'dropdown',
        previewer = false,
      },
      help_tags = {
        theme = 'ivy',
      },
      diagnostics = {
        theme = 'ivy',
        initial_mode = 'normal',
      },
    },

    -- 扩展配置
    extensions = {
      ['ui-select'] = {
        require('telescope.themes').get_dropdown {},
      },
    },
  }

  -- ====== fzf-native：更快的排序 ======
  -- 注意：本插件需要 make 编译；通过 PackChanged hook 构建
  if vim.fn.executable 'make' == 1 then
    vim.pack.add { gh 'nvim-telescope/telescope-fzf-native.nvim' }
    pcall(require('telescope').load_extension, 'fzf')
  end

  -- ====== ui-select：接管 vim.ui.select ======
  vim.pack.add { gh 'nvim-telescope/telescope-ui-select.nvim' }
  pcall(require('telescope').load_extension, 'ui-select')

  -- ====== 全局查找映射（<leader>s 前缀） ======
  vim.keymap.set('n', '<leader>sh', builtin.help_tags, { desc = '[S]earch [H]elp' })
  vim.keymap.set('n', '<leader>sk', builtin.keymaps, { desc = '[S]earch [K]eymaps' })
  vim.keymap.set('n', '<leader>sf', builtin.find_files, { desc = '[S]earch [F]iles' })
  vim.keymap.set('n', '<leader>ss', builtin.builtin, { desc = '[S]earch [S]elect Telescope' })
  vim.keymap.set('n', '<leader>sw', builtin.grep_string, { desc = '[S]earch current [W]ord' })
  vim.keymap.set('n', '<leader>sg', builtin.live_grep, { desc = '[S]earch by [G]rep' })
  vim.keymap.set('n', '<leader>sd', builtin.diagnostics, { desc = '[S]earch [D]iagnostics' })
  vim.keymap.set('n', '<leader>sr', builtin.resume, { desc = '[S]earch [R]esume' })
  vim.keymap.set('n', '<leader>s.', builtin.oldfiles, { desc = '[S]earch Recent Files ("." for repeat)' })
  vim.keymap.set('n', '<leader><leader>', builtin.buffers, { desc = '[ ] Find existing buffers' })

  -- ====== 高级：搜索选中的文本 ======
  vim.keymap.set('v', '<leader>sw', function()
    vim.cmd 'noau normal! "vy"'
    local text = vim.fn.getreg 'v'
    builtin.grep_string { search = text }
  end, { desc = '[S]earch selected [W]ord' })

  -- ====== 当前缓冲区模糊查找 ======
  vim.keymap.set('n', '<leader>s/', function()
    builtin.current_buffer_fuzzy_find(require('telescope.themes').get_dropdown {
      winblend = 10,
      previewer = false,
    })
  end, { desc = '[/] Fuzzily search in current buffer' })
end
```

### PackChanged 中编译 fzf-native

```lua
-- 必须在 vim.pack.add() 之前注册，install hook 才能在首次安装时触发
local function run_build(name, cmd, cwd)
  local result = vim.system(cmd, { cwd = cwd }):wait()
  if result.code ~= 0 then
    vim.notify(
      ('Build failed for %s:\n%s'):format(name, result.stderr or result.stdout or 'No output'),
      vim.log.levels.ERROR
    )
  end
end

vim.api.nvim_create_autocmd('PackChanged', {
  callback = function(ev)
    local name, kind, path = ev.data.spec.name, ev.data.kind, ev.data.path
    if kind ~= 'install' and kind ~= 'update' then return end

    if name == 'telescope-fzf-native.nvim' and vim.fn.executable 'make' == 1 then
      run_build(name, { 'make' }, path)
    end
  end,
})
```

> [!IMPORTANT]
> `telescope-fzf-native.nvim` 是 C 扩展，首次安装后必须执行 `make` 才能生效。上面的 `run_build` + `vim.system()` 范式与 [[08-modern-plugin-patterns]] 中 treesitter / LuaSnip 的构建钩子完全一致。

### 用 Telescope 覆盖默认 LSP 按键

Neovim 0.12 内置了 `grr` / `gri` / `gO` / `grt` 等默认 LSP 映射，但 kickstart 选择用 Telescope picker 替代它们，以获得统一的模糊查找体验：

```lua
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(ev)
    local buf = ev.buf
    local builtin = require 'telescope.builtin'

    vim.keymap.set('n', 'grr', builtin.lsp_references,
      { buffer = buf, desc = '[G]oto [R]eferences (Telescope)' })
    vim.keymap.set('n', 'gri', builtin.lsp_implementations,
      { buffer = buf, desc = '[G]oto [I]mplementation (Telescope)' })
    vim.keymap.set('n', 'gO', builtin.lsp_document_symbols,
      { buffer = buf, desc = 'Open Document Symbols (Telescope)' })
    vim.keymap.set('n', 'grt', builtin.lsp_type_definitions,
      { buffer = buf, desc = '[G]oto [T]ype Definition (Telescope)' })

    -- grd 是 goto definition，0.12 由 tagfunc 提供；也可用 Telescope 覆盖
    vim.keymap.set('n', 'grd', builtin.lsp_definitions,
      { buffer = buf, desc = '[G]oto [D]efinition (Telescope)' })
  end,
})
```

> [!IMPORTANT]
> 这里覆盖了 0.12 的默认映射。用 `:verbose map grr` 可以验证当前生效的是 Telescope picker 还是原生 `vim.lsp.buf.references()`。

### 主题使用示例

```lua
local themes = require 'telescope.themes'

-- dropdown：紧凑居中，适合 buffers / colorscheme
require('telescope').setup {
  pickers = {
    colorscheme = {
      enable_preview = true,
      theme = 'dropdown',
    },
  },
}

-- 也可在调用时动态指定
vim.keymap.set('n', '<leader>sc', function()
  require('telescope.builtin').colorscheme(
    themes.get_dropdown { enable_preview = true }
  )
end, { desc = '[S]earch [C]olorscheme' })

-- ivy：底部全宽条带，适合 help_tags / diagnostics
vim.keymap.set('n', '<leader>fh', function()
  require('telescope.builtin').help_tags(themes.get_ivy {})
end, { desc = '[F]ind [H]elp' })

-- cursor：跟随光标，适合代码操作菜单
vim.keymap.set('n', '<leader>ca', function()
  vim.lsp.buf.code_action(themes.get_cursor {})
end, { desc = '[C]ode [A]ction' })
```

### `vim.ui.select` 转交 Telescope

安装 `telescope-ui-select.nvim` 后，所有调用 `vim.ui.select()` 的地方（包括代码操作菜单、LSP 选择等）都会变成 Telescope 下拉框：

```lua
vim.pack.add { gh 'nvim-telescope/telescope-ui-select.nvim' }
require('telescope').setup {
  extensions = {
    ['ui-select'] = {
      require('telescope.themes').get_dropdown {},
    },
  },
}
require('telescope').load_extension 'ui-select'

-- 测试：弹出一个 Telescope 下拉选择框
vim.keymap.set('n', '<leader>ut', function()
  vim.ui.select({ 'lua', 'python', 'rust' }, {
    prompt = 'Select language:',
  }, function(choice)
    print('You chose: ' .. (choice or 'nothing'))
  end)
end, { desc = '[U]I-select [T]est' })
```

**运行方式：**
1. 将上述代码放入 `init.lua` 或拆分到 `lua/plugins/telescope.lua`；
2. 重启 Neovim；
3. 按 `<leader>ff` 查找文件，输入部分文件名测试模糊匹配；
4. 按 `<leader>fg` 搜索文本；
5. 打开一个代码文件，按 `grr` 查看 Telescope 风格的引用列表。

---

## 3. 练习

### 练习 1: 基础查找

- 用 `<leader>sf` 查找到 `init.lua` 并打开；
- 用 `<leader>sg` 搜索 `vim.opt`，观察实时结果；
- 用 `<leader><leader>` 在打开的文件间切换。

### 练习 2: 自定义 picker 映射

添加以下两个映射：
- `<leader>fs` — 查找当前文件的 LSP 符号（`lsp_document_symbols`）；
- `<leader>fS` — 查找工作区符号（`lsp_workspace_symbols`）。

### 练习 3: 安装并验证 fzf-native

确保系统有 `make`，启用 `telescope-fzf-native.nvim`，并通过 PackChanged hook 自动编译。验证：
1. `:checkhealth telescope` 中显示 `fzf` extension OK；
2. 在大型项目中用 `<leader>sf` 测试排序速度。

### 练习 4: 用 dropdown 主题改造 buffers picker（可选）

让 `<leader><leader>` 打开时使用 `get_dropdown` 主题，并且不显示预览窗口。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> - **`<leader>sf` 查找文件**：输入 `init` → Telescope 实时过滤，显示所有路径包含 `init` 的文件。按 `<C-n>`/`<C-p>` 移动，`<CR>` 打开，`<C-v>` 垂直分割。
> - **`<leader>sg` 搜索文本**（`live_grep`）：输入 `vim.opt` → 执行 ripgrep 搜索并实时更新结果。结果列出 `文件名:行号:匹配行`。需要 `rg` 在 PATH 中。
> - **`<leader><leader>` 切换 buffers**：显示所有已打开的 buffer，按最近使用排序。选择后 `<CR>` 跳转。
>
> **关键技巧**：在 Telescope 窗口中按 `<C-/>`（插入模式）或 `?`（普通模式）查看所有可用按键映射。

> [!tip]- 练习 2 参考答案
> 在 LspAttach 回调中添加 buffer-local 映射：
>
> ```lua
> vim.api.nvim_create_autocmd('LspAttach', {
>   callback = function(ev)
>     local builtin = require 'telescope.builtin'
>     local buf = ev.buf
>     vim.keymap.set('n', '<leader>fs', builtin.lsp_document_symbols,
>       { buffer = buf, desc = 'Document [S]ymbols' })
>     vim.keymap.set('n', '<leader>fS', builtin.lsp_workspace_symbols,
>       { buffer = buf, desc = 'Workspace [S]ymbols' })
>   end,
> })
> ```
>
> 也可以在全局映射中直接写（不需要 LSP 附着）：
>
> ```lua
> vim.keymap.set('n', '<leader>fs', '<cmd>Telescope lsp_document_symbols<cr>',
>   { desc = 'Document [S]ymbols' })
> vim.keymap.set('n', '<leader>fS', '<cmd>Telescope lsp_workspace_symbols<cr>',
>   { desc = 'Workspace [S]ymbols' })
> ```
>
> **注意**：`lsp_workspace_symbols` 需要 LSP 服务器支持 `workspace/symbol` 方法。某些服务器（如基于 pyright 的配置）可能响应较慢。

> [!tip]- 练习 3 参考答案
> 1. 确认 `make` 可用：`:echo executable('make')` 应返回 `1`。
> 2. 在 `vim.pack.add()` 前注册 `PackChanged` hook：
>
> ```lua
> local function run_build(name, cmd, cwd)
>   local result = vim.system(cmd, { cwd = cwd }):wait()
>   if result.code ~= 0 then
>     vim.notify('Build failed for ' .. name, vim.log.levels.ERROR)
>   end
> end
>
> vim.api.nvim_create_autocmd('PackChanged', {
>   callback = function(ev)
>     local name, kind, path = ev.data.spec.name, ev.data.kind, ev.data.path
>     if kind ~= 'install' and kind ~= 'update' then return end
>     if name == 'telescope-fzf-native.nvim' and vim.fn.executable 'make' == 1 then
>       run_build(name, { 'make' }, path)
>     end
>   end,
> })
> ```
>
> 3. 添加插件：
>
> ```lua
> vim.pack.add { 'https://github.com/nvim-telescope/telescope-fzf-native.nvim' }
> pcall(require('telescope').load_extension, 'fzf')
> ```
>
> 4. 验证：`:checkhealth telescope` → 查找 `fzf` extension，状态应为 OK。

> [!tip]- 练习 4 参考答案（可选）
> 在 `setup()` 的 `pickers` 中配置 buffers：
>
> ```lua
> require('telescope').setup {
>   pickers = {
>     buffers = {
>       sort_lastused = true,
>       theme = 'dropdown',
>       previewer = false,
>     },
>   },
> }
> ```
>
> 或在按键调用时动态使用主题：
>
> ```lua
> vim.keymap.set('n', '<leader><leader>', function()
>   require('telescope.builtin').buffers(
>     require('telescope.themes').get_dropdown { previewer = false }
>   )
> end, { desc = '[ ] Find existing buffers' })
> ```
>
> `previewer = false` 让窗口更紧凑；`theme = 'dropdown'` 让列表居中显示。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Telescope 官方文档](https://github.com/nvim-telescope/telescope.nvim)
- [Telescope 内置 Picker 列表](https://github.com/nvim-telescope/telescope.nvim?tab=readme-ov-file#pickers)
- [Telescope 扩展列表](https://github.com/nvim-telescope/telescope.nvim?tab=readme-ov-file#extensions)
- [telescope-fzf-native.nvim](https://github.com/nvim-telescope/telescope-fzf-native.nvim)
- [telescope-ui-select.nvim](https://github.com/nvim-telescope/telescope-ui-select.nvim)

---

## 常见陷阱

- **`live_grep` 需要 `ripgrep`**：Windows 用户需安装 `rg`（`scoop install ripgrep` 或 `winget install BurntSushi.ripgrep.MSVC`）。
- **大仓库中 `find_files` 慢**：用 `git_files` 代替（仅 Git 追踪的文件），或安装 `telescope-fzf-native.nvim`。
- **隐藏文件不显示**：设置 `find_files = { hidden = true }` 并传入 `--hidden` 给 `rg`。
- **fzf-native 需要 `make` 编译**：Windows 上若没有 `make`，跳过即可；默认排序器在小型项目中足够。
- **LSP picker 覆盖后 `:verbose map grr` 应显示 Telescope**：如果仍显示原生 `vim.lsp.buf.references`，说明 LspAttach 回调未触发或按键设置位置不对。
- **Telescope 窗口中的按键不是普通 buffer 按键**：修改映射要到 `opts.defaults.mappings` 中，而不是用 `vim.keymap.set`。
