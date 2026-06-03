# 推荐学习资源: Neovim + Lua 配置实战 (现代版)

## 官方文档（必读）

- [Neovim Lua Guide](https://neovim.io/doc/user/lua-guide.html) — 官方 Lua 配置指南，覆盖所有核心 API
- [Neovim API 文档](https://neovim.io/doc/user/api.html) — 完整 API 参考
- [Neovim 0.12 更新日志](https://neovim.io/doc/user/news-0.12/) — 新功能：`vim.pack`、`vim.lsp.config`、UI2
- [`vim.pack` 官方文档](https://neovim.io/doc/user/helptag.html?tag=vim.pack) — 内置插件管理器完整参考
- [Lua 5.1 参考手册](https://www.lua.org/manual/5.1/) — Neovim 使用的 LuaJIT 兼容 5.1 语法
- [Programming in Lua (第一版)](https://www.lua.org/pil/contents.html) — 官方 Lua 教程，免费在线阅读

## 核心参考

- **[kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim)** — **本计划的核心参考配置**。单文件、完整注释、使用 `vim.pack` + blink.cmp + 原生 LSP API。这是学习现代 Neovim 配置的最佳起点。
- [A Guide to vim.pack](https://echasnovski.com/blog/2026-03-13-a-guide-to-vim-pack) — **必读**。`vim.pack` 作者 (Evgeni Chasnovski) 撰写的最完整使用指南。

## 插件文档

- [blink.cmp](https://github.com/saghen/blink.cmp) — 现代补全引擎（替代 nvim-cmp）
- [nvim-lspconfig](https://github.com/neovim/nvim-lspconfig) — LSP 服务器配置集合（配合 `vim.lsp.config` 使用）
- [mason.nvim](https://github.com/williamboman/mason.nvim) — LSP/DAP/Linter/Formatter 安装管理
- [mason-lspconfig.nvim](https://github.com/williamboman/mason-lspconfig.nvim) — mason 与 nvim-lspconfig 桥接
- [mason-tool-installer.nvim](https://github.com/WhoIsSethDaniel/mason-tool-installer.nvim) — 自动安装 mason 管理的工具
- [nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter) — 语法高亮与结构化分析
- [telescope.nvim](https://github.com/nvim-telescope/telescope.nvim) — 模糊查找
- [which-key.nvim](https://github.com/folke/which-key.nvim) — 按键提示
- [gitsigns.nvim](https://github.com/lewis6991/gitsigns.nvim) — Git 标记
- [conform.nvim](https://github.com/stevearc/conform.nvim) — 代码格式化
- [mini.nvim](https://github.com/nvim-mini/mini.nvim) — 模块化工具集（ai、surround、statusline 等）
- [fidget.nvim](https://github.com/j-hui/fidget.nvim) — LSP 状态通知

## 优秀配置参考

- [kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim) — 本计划的参考实现，单文件、完全注释
- [LazyVim](https://github.com/LazyVim/LazyVim) — 基于 lazy.nvim 的发行版（学习对比用）
- [NvChad](https://github.com/NvChad/NvChad) — 功能齐全的发行版

## 社区与视频

- [r/neovim](https://www.reddit.com/r/neovim/) — Neovim 社区
- [Neovim 官方 Discord](https://discord.gg/neovim)
- [ThePrimeagen — Neovim 配置系列](https://www.youtube.com/@ThePrimeagen) — YouTube 实战视频
- [TJ DeVries — Neovim 核心开发者](https://www.youtube.com/@teej_dv) — 深入 Neovim 内部，kickstart.nvim 作者

## 工具

- [Neovim 版本检查](https://github.com/neovim/neovim/releases) — 确保使用 0.12+
- [Nerd Fonts](https://www.nerdfonts.com/) — 图标字体（可选，但推荐）
