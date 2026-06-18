---
title: "教程目录索引: Neovim + Lua 配置实战 (现代深化版)"
updated: 2026-06-18
---

# 教程目录索引: Neovim + Lua 配置实战 (现代深化版)

> Neovim 版本: 0.12.3+
> 深化日期: 2026-06-18
> 权威事实源: [[research-brief]]

## 阶段一：Lua 够用（深化版）

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[01-lua-basics]] | Lua 快速入门：类型、控制流、LuaJIT 扩展 | 60min | 无 |
| [[02-lua-tables]] | Lua 核心：table 与 metatable（OOP） | 75min | 1 |
| [[03-lua-functions-modules]] | Lua 函数、闭包与模块系统 | 70min | 2 |

## 阶段二：Neovim 配置基础（深化版）

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[04-init-lua-structure]] | init.lua 结构、vim.loader、选项体系 | 55min | 3 |
| [[05-keymaps]] | 按键映射完全指南（vim.keymap 深度） | 50min | 4 |
| [[06-autocmds]] | 自动命令与事件系统 | 50min | 4 |

## 阶段三：现代插件管理（深化版）

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[07-vim-pack]] | **vim.pack 完全指南：lockfile/hooks/del/三种组织** | 70min | 4 |
| [[08-modern-plugin-patterns]] | **现代插件配置模式：hook 范式与懒加载** | 60min | 7 |

## 阶段四：开发环境核心（深化版）

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[09-modern-lsp]] | **现代 LSP：config/enable/默认按键/lsp 文件** | 80min | 7 |
| [[10-blink-cmp]] | **blink.cmp（V1/V2/cmdline/terminal）** | 65min | 9 |
| [[11-treesitter]] | Treesitter：现代 API（main 分支、内置文本对象） | 60min | 7 |

## 阶段五：UI 与导航

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[12-telescope]] | Telescope：模糊查找一切（含 LSP picker） | 50min | 7 |
| [[13-appearance]] | 外观定制：colorscheme 与 statusline | 45min | 4 |

## 阶段六：架构深度理解

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[14-kickstart-architecture]] | **kickstart.nvim master 架构深度解析** | 75min | 7-11 |
| [[15-modular-config]] | **模块化配置架构：lsp/*.lua + plugin/*.lua** | 60min | 14 |

## 阶段七：进阶工具链（深化版新增）

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[17-native-completion]] | **原生补全：vim.lsp.completion（零依赖方案）** | 50min | 9 |
| [[18-diagnostics-deep]] | **Diagnostic 系统深度：virtual_lines/jump/severity** | 55min | 9 |
| [[19-formatting-linting]] | **格式化与 Linter：conform.nvim + nvim-lint** | 60min | 9 |
| [[20-dap-debugging]] | **调试器：DAP (nvim-dap + nvim-dap-ui) 实战** | 75min | 9 |
| [[21-performance-troubleshooting]] | **性能优化与故障排查** | 55min | 4 |

## 阶段八：实战

| 文件 | 标题 | 预计耗时 | 前置 |
|------|------|---------|------|
| [[16-project]] | **综合实战：单文件 + 模块化双版本** | 150min | 1-15, 17-21 |
