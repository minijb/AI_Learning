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


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 并行探索工作流：
>
> ```text
> "同时分析 src/api/、src/db/ 和 src/ui/ 三个子目录各自的模块结构"
> ```
>
> OMP 的执行流程：
> 1. 创建 3 个 explore 子代理，分别分配任务：
>    - 子代理 1: explore src/api/ — 列出所有文件、入口点、导出
>    - 子代理 2: explore src/db/ — 表结构、repository 模式
>    - 子代理 3: explore src/ui/ — 组件树、路由结构
> 2. 三个子代理并行执行（受 maxConcurrency 限制）
> 3. 完成后 OMP 读取各 agent:// 输出
> 4. OMP 汇总成综合报告
>
> **观察要点：**
> - TUI 中可以看到 3 个子任务同时进行的状态
> - 总耗时 ≈ 最慢子代理的耗时（而非三者之和）——这就是并行的威力
> - 每个子代理有独立的 `agent://<id>` URL，可单独查看详细输出
> - 如果 3 个目录大小差异很大，小目录的子代理先完成，大目录的继续运行
>
> **思考题答案：** 串行执行：子代理 1→2→3 依次执行，总耗时 = T1+T2+T3。并行执行：三者同时运行，总耗时 ≈ max(T1,T2,T3)。在分析 3 个独立目录时，并行比串行快约 2-3 倍。但如果子代理之间有依赖（如需要先分析 api 再分析依赖 api 的 ui），则不能并行。

> [!tip]- 练习 2 参考答案
> 探索-计划-执行-审查流水线：
>
> ```text
> 步骤 1 — 探索：
> "用 explore agent 分析 src/legacy/ 模块的结构和依赖关系"
> → 返回：模块文件列表、导出/导入关系图、代码行数统计
>
> 步骤 2 — 计划：
> "用 plan agent 设计 src/legacy/ 的重构方案：把回调模式改成 async/await"
> → 返回：
>   - 影响范围：12 个文件，47 个回调函数
>   - 迁移顺序：先改最底层的工具函数，再改中间层，最后改入口
>   - 风险点：3 个地方用了自定义 callback 类型，需要引入 Promise 包装
>   - 测试策略：每个文件改完后运行对应测试
>
> 步骤 3 — 执行：
> "用 task agent 按照方案执行重构"
> → task agent 按计划逐步修改文件
>
> 步骤 4 — 审查：
> "用 reviewer agent 审查本次重构的所有变更"
> → 返回：
>   - 检查 async/await 是否正确处理了错误
>   - 检查是否有遗漏的回调没有转换
>   - 检查 Promise.all 的使用是否合理
> ```
>
> **关键观察：** 这个流水线体现了"关注点分离"——每个 agent 类型专精一件事。explore 只读不改，plan 只设计不执行，task 按指令修改，reviewer 事后检查。专精化的 agent 比通用 agent 在各自领域做得更好。

> [!tip]- 练习 3 参考答案（可选）
> 创建自定义子代理：
>
> ```markdown
> <!-- .omp/agents/code-reviewer.md -->
> ---
> name: code-reviewer
> description: >
>   代码审查专家，检查代码的安全性、性能和可维护性。
>   当需要审查 PR 或提交前检查时使用。
> model: anthropic/claude-sonnet-4-5
> tools:
>   - read
>   - search
>   - find
>   - lsp
> ---
>
> # Code Reviewer Agent
>
> 你是代码审查专家。审查时遵循以下检查清单:
>
> ## 安全检查
> - 是否有 SQL 注入风险？
> - 敏感信息是否硬编码？
> - 输入验证是否充分？
>
> ## 性能检查
> - 是否有不必要的循环嵌套？
> - 大对象是否被不必要地复制？
> - 异步操作是否正确并行？
>
> ## 可维护性检查
> - 函数是否过长（>30 行）？
> - 是否有魔法数字？
> - 错误处理是否完整？
>
> ## 输出格式
> 返回结构化的审查报告:
> { issues: [{ severity, file, line, description, suggestion }] }
> ```
>
> 在 OMP 中调用：
>
> ```text
> "用 code-reviewer agent 审查 src/api/ 目录下的所有文件"
> ```
>
> **观察要点：**
> - 自定义 agent 从 `.omp/agents/<name>.md` 加载
> - frontmatter 中的 `tools` 字段限制子代理可用的工具（安全机制）
> - 自定义 agent 可以和内置 agent 并排使用
> - agent 的 `description` 字段帮助 OMP 选择最合适的 agent

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
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
