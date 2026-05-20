---
name: docs-manager
description: >
  管理 AI 工作区的 docs 系统。当需要创建/更新索引、归档学习计划、
  管理知识笔记、跨计划搜索、整理文档结构时触发。
compatibility: Python 3.8+ (跨平台，无需额外依赖)
---

# Docs Manager — 文档系统管理

> 维护 docs/ 下的索引、分类和归档。所有 Skill 通过此 Skill 访问和修改 docs 系统。
>
> **其他 Skill 调用方式**：直接执行本 Skill 的脚本，路径相对于工作区根目录 `D:/Tur/temp/`：
> - 更新学习计划索引: `python .pi/skills/docs-manager/scripts/update-index.py learning-plans`
> - 更新深度探索索引: `python .pi/skills/docs-manager/scripts/update-index.py deep-dives`
> - 更新知识笔记索引: `python .pi/skills/docs-manager/scripts/update-index.py knowledge-notes`
> - 归档学习计划: `python .pi/skills/docs-manager/scripts/archive-plan.py <plan-name>`

---

## 核心定位

本 Skill 是 docs 系统的唯一写入入口。其他 Skill（learning-plans、tutorial-deepener 等）
通过调用本 Skill 的脚本来更新索引和归档。

---

## 命令速查

| 操作 | 命令 |
|------|------|
| 更新学习计划索引 | `python scripts/update-index.py learning-plans` |
| 更新知识笔记索引 | `python scripts/update-index.py knowledge-notes` |
| 更新深度探索索引 | `python scripts/update-index.py deep-dives` |
| 更新全部索引 | `python scripts/update-index.py --all` |
| 归档学习计划 | `python scripts/archive-plan.py <plan-name>` |
| 列出活跃计划 | `python scripts/archive-plan.py --list-active` |

---

## 索引格式规范

### 学习计划索引 (`docs/learning-plans/INDEX.md`)

> 脚本自动生成，格式为：
>
> ```markdown
> # 学习计划索引
>
> > 自动生成于 YYYY-MM-DD
>
> ## 进行中
>
> | 计划名称 | 创建日期 |
> |---------|---------|
> | Rust异步编程 | — |
>
> ## 已完成
> | 计划名称 | 完成日期 |
> |---------|---------|
> | ... | — |
> ```
>
> **注意**：索引由脚本 `update-index.py` 自动生成，不要手写编辑。表格只含「计划名称」「创建日期/完成日期」两列，领域和进度信息在各自 plan.md 中。

### 知识笔记索引 (`docs/knowledge-notes/INDEX.md`)

```markdown
# 知识笔记索引

## 编程语言
- [Rust 所有权](Rust/ownership.md)
- [Go 并发模型](Go/concurrency.md)

## 系统设计
- [CAP 定理](system-design/cap-theorem.md)
```

### 深度探索索引 (`docs/deep-dives/INDEX.md`)

> 脚本自动扫描 `deep-dives/` 下所有 .md 文件生成**扁平列表**（不按月份分组）：

```markdown
# 深度探索索引

> 自动生成于 YYYY-MM-DD

- [Rust Pin 机制深入](rust-pin.md)
- [Go 调度器剖析](go-scheduler.md)
```

---

## 归档流程

1. 确认 `docs/learning-plans/active/<name>/progress.md` 中所有步骤标记完成
2. 运行 `python scripts/archive-plan.py <name>`
3. 脚本将 plan 目录从 `active/` 移到 `completed/`
4. 更新 `docs/learning-plans/INDEX.md`

---

## 护栏规则

1. **唯一写入入口** — 所有索引更新必须通过本 Skill 的脚本，不直接编辑 INDEX.md
2. **索引一致性** — 每次增删学习计划/笔记后立即更新对应索引
3. **归档不可逆** — 归档操作有确认步骤，防止误操作
