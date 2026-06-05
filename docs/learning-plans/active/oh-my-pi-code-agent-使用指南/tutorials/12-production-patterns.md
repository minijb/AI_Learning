---
title: "12 — 生产最佳实践"
updated: 2026-06-05
---

# 12 — 生产最佳实践

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 10 — 自定义工具与扩展, 11 — MCP 服务器与外部集成

---

## 1. 概念讲解

### 本章覆盖什么？

前 11 节覆盖了 OMP 的各种功能和定制方式。本节聚焦于**如何在实际项目中可靠、安全、高效地使用 OMP**。

### 核心原则

1. **上下文工程** — 给 Agent 足够但不过量的上下文
2. **安全第一** — 防止敏感信息泄露
3. **可重复** — 确保一致的行为
4. **可审计** — 知道 Agent 做了什么

---

## 2. 实践指南

### 2.1 上下文工程

#### AGENTS.md 和 CLAUDE.md

这些是项目级的 Agent 指令文件，OMP 在启动时自动发现:

```markdown
<!-- AGENTS.md — 项目根目录 -->
# AGENTS.md

## 项目架构
- 这是一个 Next.js 14 项目，使用 App Router
- 数据库: PostgreSQL，通过 Prisma ORM 访问
- 状态管理: Zustand

## 编码规范
- 所有组件使用 TypeScript 严格模式
- API 路由使用 Zod 验证输入
- 测试使用 Vitest + Testing Library

## 常见工作流
- 添加新页面: 在 `app/(routes)/` 下创建目录
- 添加 API: 在 `app/api/` 下创建 `route.ts`
```

OMP 会从 cwd 向上遍历目录树，发现所有 AGENTS.md 文件。

#### 系统提示 (SYSTEM.md)

```markdown
<!-- .omp/SYSTEM.md -->
# 系统提示

你是本项目的主要开发者。你遵循以下原则:
- 代码优先于注释（好的命名胜过注释）
- 修改前先理解（阅读相关文件再编辑）
- 批量操作时使用子代理并行
```

#### 规则文件 (Rules)

```markdown
<!-- .omp/rules/security.md -->
# 安全规则

- 永远不要在代码中硬编码 API Key 或密码
- 使用环境变量存储所有 secret
- npm 包使用前检查已知漏洞
```

### 2.2 安全实践

#### Secrets 混淆

启用 `secrets.enabled` 后，OMP 会自动:
1. 从环境变量收集 secret（匹配 KEY/SECRET/TOKEN 等模式）
2. 在发送给 LLM 前替换为占位符 `#AB12#`
3. 在工具调用参数中恢复原始值

```yaml
# ~/.omp/agent/config.yml
secrets:
  enabled: true
```

```yaml
# .omp/secrets.yml — 手动定义 secret
- type: regex
  content: "AKIA[0-9A-Z]{16}"
- type: plain
  content: "my-db-password"
  mode: replace
  replacement: "********"
```

#### Auth Broker

Auth Broker 将 OAuth token 保存在远程服务器上:

```bash
# 配置 auth broker URL
export OMP_AUTH_BROKER_URL="https://broker.internal:8765"
export OMP_AUTH_BROKER_TOKEN="broker-access-token"
```

### 2.3 会话管理策略

#### 何时创建新会话？

- 切换到不同的任务/功能时: `Ctrl+N`
- 当前会话上下文太杂乱时
- 需要与他人分享会话时

#### 何时使用分支？

- 想尝试替代方案但不确定哪个更好
- 需要回溯到之前的状态但不丢弃当前工作

#### 会话分享

OMP 支持导出/分享会话文件:

```bash
# 导出会话（包含所有分支）
# 通过 UI 或 API 操作
```

### 2.4 内存系统

启用自动记忆后，OMP 在项目范围内跨会话积累知识:

```yaml
memories:
  enabled: true
  maxRolloutAgeDays: 30
```

使用 `/memory view` 查看当前记忆，`/memory rebuild` 手动重建。

### 2.5 实际工作流

#### 工作流 1: 新功能开发

```text
1. "用 explore agent 分析相关模块的结构"
2. "用 plan agent 设计实现方案"
3. "用 task agent 并行实现各模块"
4. "用 reviewer agent 审查全部变更"
5. 手动确认后合并
```

#### 工作流 2: Bug 修复

```text
1. "读取错误日志，定位相关代码"
2. "用 LSP 追踪调用链，找到根因"
3. "用 edit 工具修复"
4. "用 lsp diagnostics 确认无新错误"
5. "运行测试验证"
```

#### 工作流 3: 代码迁移

```text
1. "用 search 找出所有使用旧 API 的地方"
2. "用 task agent 批量迁移（每个模块一个子代理）"
3. "用 LSP rename + diagnostics 验证"
4. "运行完整测试套件"
```

**运行方式:**
```bash
# 按照工作流描述，在 OMP 中逐条执行
# 根据实际情况调整 prompt 的详细程度
```

---

## 3. 练习

### 练习 1: 为你的项目创建 AGENTS.md

1. 在项目根目录创建 `AGENTS.md`
2. 包含: 项目架构概述、技术栈、编码规范、常用工作流
3. 在 OMP 中验证: 询问关于项目的问题，确认它使用了 AGENTS.md 的信息

### 练习 2: 配置安全措施

1. 启用 secrets 混淆
2. 创建一个包含 API Key 的测试文件
3. 让 OMP 读取该文件，验证输出中 Key 已被替换
4. 配置扩展拦截危险 bash 命令

### 练习 3: 完整的开发工作流

1. 选择项目中的一个小功能
2. 按 2.5 节的工作流 1 完成完整开发周期
3. 记录每个步骤的实际效果和用时
4. 总结哪些部分最有效率，哪些需要改进

---

## 4. 扩展阅读

- [[omp://secrets|秘密混淆]] — 完整的 secrets 系统
- [[omp://auth-broker-gateway|Auth Broker Gateway]] — 远程凭证保管
- [[omp://memory|自主记忆]] — 跨会话知识积累
- [[omp://session-operations-export-share-fork-resume|会话操作]]
- [[omp://sdk|SDK 嵌入指南]] — 以编程方式使用 OMP
- [OMP 官方文档](omp://)

---

## 常见陷阱

- **上下文过长**: 如果 AGENTS.md 太长，会挤占 LLM 上下文窗口。保持精简，放在项目根目录
- **Secrets 混淆不是加密**: 混淆是确定性替换，不是加密。不要依赖它作为唯一的安全措施
- **内存不是权威**: 记忆是启发式的，可能包含过期信息。以当前代码状态和用户指令为准
- **子代理成本**: 每个子代理都会消耗 API token。合理评估是否需要并行
- **分支混淆**: 在多个分支间频繁切换可能导致代码状态混淆。确认当前分支后再操作
