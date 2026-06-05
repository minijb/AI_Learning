---
title: "01 — OMP 概述与首次会话"
updated: 2026-06-05
---

# 01 — OMP 概述与首次会话

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 无

---

## 1. 概念讲解

### Oh My Pi 是什么？

Oh My Pi (OMP) 是一个 AI 编码代理（Coding Agent）运行时。它在你的终端中运行，能直接操作文件系统、执行命令、调用 LLM。你可以把它想象成"一个能写代码、读代码、改代码的 AI 助手，它住在你的终端里"。

OMP 的核心能力:

- **读取代码库**: 理解项目结构，阅读任意文件
- **精确编辑**: 通过 hashline 锚点安全地修改代码
- **智能搜索**: 正则搜索、AST 结构化搜索
- **LSP 集成**: 跳转定义、查找引用、重命名符号
- **任务委托**: 派生子代理并行处理多文件修改
- **可扩展**: Skills、自定义工具、扩展、MCP 服务器

### 类比理解

| 传统开发方式 | OMP 方式 |
|-------------|---------|
| `grep` 搜索 + 逐文件阅读 | 直接告诉 OMP "找出所有调用 `oldApi` 的地方" |
| 手动跨文件重命名 | `lsp rename` 一次完成 |
| 逐个改文件 | 子代理并行修改 5 个文件 |
| 看文档 + 写样板代码 | 描述意图，OMP 生成实现 |

### 安装

OMP 基于 Bun 运行时。安装步骤:

```bash
# 1. 安装 Bun (如果还没有)
# macOS / Linux:
curl -fsSL https://bun.sh/install | bash

# Windows:
powershell -c "irm bun.sh/install.ps1 | iex"

# 2. 安装 OMP CLI
bun add -g @oh-my-pi/pi-coding-agent

# 3. 验证安装
omp --version

# 4. 配置 API Key（以 Anthropic 为例）
export ANTHROPIC_API_KEY="sk-ant-..."

# 或者保存到 ~/.omp/agent/.env
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> ~/.omp/agent/.env
```

### 核心架构

```text
┌─────────────────────────────────────────┐
│              用户输入 (Prompt)            │
└─────────────────┬───────────────────────┘
                  ▼
┌─────────────────────────────────────────┐
│           OMP Agent 核心循环              │
│                                         │
│  System Prompt ← Skills + Context Files  │
│       │                                 │
│       ▼                                 │
│  LLM 推理 (Claude/GPT/Gemini/...)        │
│       │                                 │
│       ▼                                 │
│  工具调用 (read/edit/search/task/...)     │
│       │                                 │
│       ▼                                 │
│  文件系统 / Shell / LSP / MCP            │
└─────────────────────────────────────────┘
```

---

## 2. 代码示例

### 启动你的第一个会话

```bash
# 进入你的项目目录
cd /path/to/your/project

# 启动 OMP 交互会话
omp
```

首次启动后你会看到 TUI（终端用户界面）。OMP 会:
1. 扫描项目结构
2. 发现 Skills、AGENTS.md、配置文件
3. 加载 LSP 服务器（如果有对应语言）
4. 显示就绪提示

### 你的第一个 Prompt

在 OMP 提示符输入:

```text
分析这个项目的结构，告诉我主要模块和它们的关系。
```

OMP 会:
1. 使用 `read` 工具浏览目录
2. 读取关键文件（package.json、目录结构等）
3. 阅读源码签名
4. 返回结构化的分析结果

### 一个实际的修改任务

```text
在 src/utils/ 下创建一个 logger.ts，导出 createLogger 函数，
支持不同日志级别 (debug, info, warn, error)。
```

OMP 会:
1. 检查 `src/utils/` 是否存在
2. 创建文件并写入实现
3. 可能自动运行类型检查

**运行方式:**
```bash
# 确保 API key 已配置
echo $ANTHROPIC_API_KEY

# 进入项目启动 OMP
cd your-project
omp
```

**预期输出:**
OMP 会在 TUI 中逐步展示其操作:
- 读取目录、检查已有文件
- 创建 `src/utils/logger.ts`
- 展示写入的代码
- 报告完成状态

---

## 3. 练习

### 练习 1: 启动并探索

在你的任一项目中启动 OMP，让它:
- 列出项目的目录结构
- 找出所有配置文件
- 统计各语言的代码行数（大致）

### 练习 2: 创建文件

让 OMP 在项目中创建一个新文件（例如 `src/healthcheck.ts`），实现一个简单的 HTTP 健康检查端点。验证文件内容是否正确。

### 练习 3: 理解工具调用（可选）

仔细观察 OMP 处理你的 prompt 时调用了哪些工具。在 TUI 中可以看到工具调用的展开/折叠。记录下 OMP 处理"列出项目结构并分析"这个请求时使用的工具序列。

---

## 4. 扩展阅读

- [OMP GitHub 仓库](https://github.com/can1357/oh-my-pi)
- [[omp://sdk|OMP SDK 文档 — 嵌入 API]]
- [[omp://session|OMP 会话模型文档]]
- [OMP 博客: What I learned building a coding agent](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/)

---

## 常见陷阱

- **API Key 未设置**: OMP 启动后会检查可用模型，如果没有配置 API Key 会提示。解决方法: 设置对应提供商的 `*_API_KEY` 环境变量或保存到 `~/.omp/agent/.env`
- **Bun 版本过旧**: OMP 需要较新版本的 Bun。使用 `bun upgrade` 更新
- **首次启动慢**: 首次启动需要刷新模型注册表、发现 LSP 服务器，等待几十秒是正常的
- **中文路径/文件名**: Windows 上路径含中文时可能有编码问题，建议项目路径使用英文
