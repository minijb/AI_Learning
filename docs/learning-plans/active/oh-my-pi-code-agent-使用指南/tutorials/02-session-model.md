# 02 — 掌握会话模型

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 45min
> 前置知识: 01 — OMP 概述与首次会话

---

## 1. 概念讲解

### 会话是什么？

OMP 中的**会话（Session）** 是你在一个项目中的全部对话历史。它不仅仅是聊天记录——它是一个**有向无环图（DAG）**，支持分支（branch）、分叉（fork）和恢复（resume）。

```text
会话树结构:

    root
     │
     ├── turn 1: "分析项目结构"
     │    │
     │    ├── turn 2a: "重构 API 层"     ← 默认分支
     │    │    └── turn 3a: "添加测试"
     │    │
     │    └── turn 2b: "修复 bug"        ← 分支（从 turn 1 分叉）
     │         └── turn 3b: "部署检查"
     │
     └── [另一个 fork]: "探索替代方案"
```

### 核心概念

| 概念 | 说明 |
|------|------|
| **Session File** | 存储在 `~/.omp/agent/sessions/` 下的 `.jsonl` 文件 |
| **Entry** | 会话中的每个节点——消息、分支点、模型切换等 |
| **Branch** | 从某个节点分叉出新的对话路径 |
| **Fork** | 复制整个会话到新会话 |
| **Resume** | 恢复之前的会话继续对话 |
| **Compaction** | 会话过长时自动压缩，保留关键上下文 |

### 为什么需要分支？

假设你让 OMP 重构一个模块。重构到一半，你想到另一个更好的方案。你可以:

1. **分叉**: 从当前节点创建一个新分支，探索方案 B
2. **切换**: 如果方案 B 更好，切过去继续；如果方案 A 更好，切回来
3. **不丢失工作**: 两个分支的代码都不会丢

---

## 2. 代码示例

### 会话命令

在 OMP 的 TUI 中，你可以使用以下快捷键:

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+O` | 列出所有会话 |
| `Ctrl+T` | 显示/导航会话树 |
| `Ctrl+B` | 从当前节点创建分支 |
| `Ctrl+N` | 新建会话 |
| `Ctrl+R` | 恢复最近的会话 |

### 以编程方式操作会话 (SDK)

```ts
import {
  createAgentSession,
  SessionManager,
} from "@oh-my-pi/pi-coding-agent";

// 创建一个新会话
const { session } = await createAgentSession({
  sessionManager: SessionManager.create(process.cwd()),
});

// 发起一个 prompt
await session.prompt("解释这个项目的入口文件");

// 查看会话文件路径
console.log(session.sessionFile);
// ~/.omp/agent/sessions/---home-user-projects-myapp---/20260526_abc123.jsonl

// 恢复最近的会话
const recent = await SessionManager.continueRecent(process.cwd());
if (recent) {
  console.log(`恢复到: ${recent.path}`);
}

// 列出所有会话
const sessions = await SessionManager.list(process.cwd());
for (const s of sessions) {
  console.log(`${s.title} — ${s.timestamp}`);
}

// 打开特定会话
const opened = await SessionManager.open(sessions[0].path);

// 创建内存会话（不持久化，适合测试）
const { session: memSession } = await createAgentSession({
  sessionManager: SessionManager.inMemory(),
});
```

### 会话持久化存储

会话文件使用 JSONL 格式（每行一个 JSON 对象）。文件位置:

```text
~/.omp/agent/sessions/
  └── --<cwd-encoded>--/
      ├── <timestamp>_<sessionId>.jsonl   ← 会话记录
      └── ...
```

`<cwd-encoded>` 是从工作目录路径编码而来: `/`、`\`、`:` 替换为 `-`。

**运行方式:**
```bash
# 列出 ~/.omp/agent/sessions/ 下的会话
ls ~/.omp/agent/sessions/
```

**预期输出:**
```text
---home-user-my-project---/
---opt-app---/
```

---

## 3. 练习

### 练习 1: 创建和恢复会话

1. 在项目中启动 OMP，做一个简单操作（如"列出文件"）
2. 退出 OMP (`Ctrl+C` 或 `/exit`)
3. 重新进入项目目录，使用 `omp` 恢复最近的会话
4. 验证之前的对话历史还在

### 练习 2: 创建分支

1. 让 OMP 对某个文件做一系列修改
2. 使用 `Ctrl+T` 查看会话树
3. 在某个中间节点创建分支 (`Ctrl+B`)
4. 在新分支上做不同的修改
5. 在分支之间切换，观察代码变化

### 练习 3: 嵌套任务中的会话（可选）

让 OMP 执行一个使用 `task` 工具的任务（例如"用 explore agent 分析项目结构"），观察子代理生成的新会话及其输出如何通过 `agent://` URL 返回。

---

## 4. 扩展阅读

- [OMP 会话存储与条目模型](omp://session.md) — 完整的 JSONL 格式、版本迁移、上下文重建
- [会话操作: 导出/分享/分叉/恢复](omp://session-operations-export-share-fork-resume.md)
- [会话切换与最近列表](omp://session-switching-and-recent-listing.md)
- [Compaction（自动压缩）](omp://compaction.md)

---

## 常见陷阱

- **会话文件位置**: 会话按项目目录分组，不是全局平铺。如果在不同目录启动 OMP，它们属于不同项目范围
- **分叉 vs 分支**: 分叉创建全新的独立会话；分支在同一会话内创建子树。通常用分支更轻量
- **内存模式**: `SessionManager.inMemory()` 创建的会话不会持久化，退出即丢失
- **大型会话**: 会话太长会自动触发 compaction，早期对话被压缩成摘要。如需完整历史，检查 `firstKeptEntryId` 之前的条目
