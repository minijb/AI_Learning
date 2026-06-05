---
title: "07 — 并行任务委托（子代理）"
updated: 2026-06-05
---

# 07 — 并行任务委托（子代理）

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 06 — LSP 代码智能

---

## 1. 概念讲解

### 子代理（Subagent）是什么？

`task` 工具允许 OMP **派生子代理**并行处理多个任务。每个子代理是一个独立的 Agent 会话，有自己的工具集、上下文和模型。

### 为什么需要子代理？

| 场景 | 不用子代理 | 用子代理 |
|------|-----------|---------|
| 分析 5 个不相关的模块 | 逐个阅读，串行，慢 | 5 个子代理并行分析 |
| 跨项目搜索 + 统计 | 上下文窗口装不下 | 每个子代理专注一个领域 |
| 探索未知代码 + 重构 | 两种模式互相干扰 | `explore` agent 探索，`task` agent 重构 |

### 内置代理类型

| 代理 | 能力 | 使用场景 |
|------|------|---------|
| `explore` | 只读侦查 | 分析代码结构、追踪调用链 |
| `plan` | 架构设计 | 多文件重构方案设计 |
| `task` | 通用全能力 | 代码修改、文件操作 |
| `quick_task` | 轻量机械化操作 | 批量重命名、格式调整 |
| `designer` | UI/UX 审查 | 前端代码审查 |
| `reviewer` | 代码审查 | 质量/安全检查 |
| `librarian` | 外部 API 研究 | 查文档、研究库用法 |
| `oracle` | 资深工程师 | 调试、架构咨询 |

### 并行执行模型

```text
父会话:
  "同时分析 src/api/, src/db/, src/ui/ 三个模块的复杂度"
     │
     ├── 子代理 1 (explore): 分析 src/api/    ─┐
     ├── 子代理 2 (explore): 分析 src/db/     ─┤ 并行
     └── 子代理 3 (explore): 分析 src/ui/     ─┘
     │
     ▼
  汇总三个 agent:// 输出 → 给父会话返回综合报告
```

---

## 2. 代码示例

### 基本任务委托

在 OMP 中:

```text
使用 explore agent 分析 src/ 目录的整体架构，
用 task agent 修复 src/utils.ts 中所有的 any 类型，
两个任务同时进行。
```

OMP 会:
1. 创建一个 `explore` 子代理来阅读和分析目录结构
2. 创建一个 `task` 子代理来修改类型
3. 并行执行，汇总结果

### 带共享上下文的任务

```text
这是一个 React + TypeScript 项目，使用 React Router v6 做路由。
请同时检查以下三个模块的代码质量，参考共享上下文:
1. src/pages/ — 页面组件的可访问性
2. src/hooks/ — 自定义 hooks 的内存泄漏风险
3. src/api/ — API 调用的错误处理
```

共享的 `context` 会被注入到每个子代理的系统提示中。

### 结构化输出

```text
使用 explore agent 扫描 src/ 目录，
返回 JSON 格式的模块依赖图:
{ modules: [{ name, imports, exports, fileCount }] }
```

OMP 会传递 output schema 给子代理，确保返回结构化数据。

### 隔离模式（需要 Git 仓库）

```text
在隔离环境中重构 src/database/ 模块:
把所有回调改成 async/await，完成后提交 patch。
```

隔离模式会:
1. 创建工作树副本
2. 子代理在副本中操作
3. 成功后生成 patch 或提交到分支

**运行方式:**
```bash
# 在 OMP 交互会话中使用自然语言即可。
# 子代理会自动创建和管理。
```

---

## 3. 练习

### 练习 1: 并行探索

在一个有多个子目录的项目中:
1. 让 3 个 `explore` 子代理同时分析不同的子目录
2. 在父会话中查看各子代理的 `agent://` 输出
3. 比较串行和并行的耗时差异

### 练习 2: 探索-计划-执行流水线

1. 用 `explore` agent 分析一个模块的结构
2. 用 `plan` agent 设计重构方案
3. 用 `task` agent 执行重构
4. 用 `reviewer` agent 审查变更

### 练习 3: 自定义子代理（可选）

1. 在项目根目录创建 `.omp/agents/code-reviewer.md`
2. 编写 frontmatter 定义代理的行为
3. 在 OMP 中调用你的自定义代理

---

## 4. 扩展阅读

- [[omp://tools/task|`task` 工具完整文档]] — 所有模式、隔离、并发控制
- [[omp://task-agent-discovery|Agent 发现与选择]] — 自定义代理的加载和优先级
- [[omp://handoff-generation-pipeline|Handoff 生成管道]] — 子代理输出持久化

---

## 常见陷阱

- **子代理不自动继承父会话历史**: 只有 `context` 字段和 `context.md` 会被传递。需要子代理知道的信息必须在 `context` 中写明
- **递归深度限制**: 嵌套子代理的层级受 `task.maxRecursionDepth` 限制（默认通常为 2-3 层）
- **子代理必须调用 `yield`**: 子代理需要使用 `yield` 工具返回结果，否则 OMP 会发送最多 3 次提醒
- **隔离模式需要 Git**: 隔离执行（`isolated: true`）需要 Git 仓库支持工作树创建
- **并行数限制**: 并发子代理数量受 `task.maxConcurrency` 设置限制
