# Managing Plans — 管理已有计划

> 查看状态、修改计划、放弃计划、清理归档。

---

## 查看计划状态

### 查看所有活跃计划

```bash
python scripts/plan-status.py
```

输出包含：
- 计划名称和类型（`[FULL]` 或 `[QUICK]`）
- 当前状态（`[IN_PROGRESS]` / `[DONE]` / `[BLOCKED]`）
- 完成数/总数和百分比
- 汇总统计（总进度、阻塞项数量、活跃计划数）

### 查看单个计划详情

直接读取计划文件：

```bash
# Full Plan
cat docs/exec-plans/active/<计划名>/exec-plan.md
cat docs/exec-plans/active/<计划名>/memory.md
cat docs/exec-plans/active/<计划名>/progress.txt

# Quick Plan
cat docs/exec-plans/active/<计划名>.md
```

---

## 全局计划索引（PLAN.md / PLAN_COMPLETED.md）

> 渐进式披露 — 先看摘要，需要时再深入具体计划文件。

### PLAN.md — 活跃计划索引

`docs/exec-plans/PLAN.md` 集中记录所有活跃计划，按**主题（domain）**分组：

```markdown
## 📁 前端
### 任务组（有先后依赖的计划链）
| 序号 | 计划名 | 类型 | 摘要 | 依赖 | 状态 |
### 独立任务（无依赖，可并行）
| 计划名 | 类型 | 摘要 | 状态 |

## 📁 后端
### 任务组 ...
### 独立任务 ...
```

每个主题下分两类：

| 分类 | 说明 | 表格列 |
|------|------|--------|
| **任务组** | 有先后依赖的计划链 | 序号、计划名、类型、摘要、依赖、状态 |
| **独立任务** | 无依赖关系，可并行执行 | 计划名、类型、摘要、状态 |

每个条目包含一句话摘要，方便快速浏览。条目按倒序排列（最新在最上面）。

### PLAN_COMPLETED.md — 已完成计划归档

`docs/exec-plans/PLAN_COMPLETED.md` 记录所有已完成和已放弃的计划，按完成日期倒序排列。

### 搜索计划

```bash
python scripts/plan-search.py "<关键词>"

# 列出所有条目
python scripts/plan-search.py --all
```

### 创建时自动维护

- **创建计划时**：`plan-new` 自动将新计划条目写入 `PLAN.md`
- **归档计划时**：`plan-complete` 自动将条目从 `PLAN.md` 迁移到 `PLAN_COMPLETED.md`
- **手动编辑**：INDEX 文件是标准 Markdown，可直接编辑表格

### 创建新计划前的工作流

```bash
# 1. 先搜索
python scripts/plan-search.py "用户认证"

# 2. 检查结果
#    - 有匹配 → 确认是否可复用或标注依赖
#    - 无匹配 → 创建新计划

# 3. 创建时提供摘要和依赖（可选）
python scripts/plan-new.py --full "api-gateway" --summary "API 网关路由和限流" --depends "user-auth" --domain "后端"
```

---

## 修改计划

计划执行过程中，有时需要调整。以下是安全修改的指南。

### 什么可以修改

| 文件 | 可修改内容 | 修改时机 |
|------|-----------|---------|
| `exec-plan.md` / `.md` | 步骤描述、依赖关系、风险、验收标准 | 发现遗漏或偏差时 |
| `progress.txt` | 步骤状态、阻塞项说明 | 每次执行后 |
| `memory.md` | 所有字段 | 产生关键工件后 |
| `feature-list.json` | 只有 `passes` 字段 | 完成功能点后 |

### 什么不可以修改

| 文件 | 禁止修改 | 原因 |
|------|---------|------|
| `feature-list.json` | `id`, `category`, `description`, `steps` | 这些是功能契约，由人类定义。智能体只能标记完成状态。 |

### 修改流程

1. **评估影响**：这个修改会影响已完成的工作吗？会改变验收标准吗？
2. **向用户说明**：在聊天中简要说明为什么需要修改计划
3. **执行修改**：编辑相关文件
4. **重新验证**：运行 `plan-validate` 确保计划仍然完整
5. **更新 memory**：在 `memory.md` 中记录"计划变更"这一决策

### 修改示例

**场景：发现需要新增一个步骤**

```markdown
# 在 exec-plan.md 中

## 三、步骤分解（Steps）
- [x] **Step 1** — 搭建数据库表
- [x] **Step 2** — 实现注册 API
- [ ] **Step 3** — 实现登录 API
- [ ] **Step 4** — 集成 JWT
- [ ] **Step 5** — 前端对接
- [ ] **Step 6** — 新增：添加 rate limiting（发现安全需求）
  - 产出：中间件代码 + 测试
  - 依赖：Step 4
  - 验证：100 req/min 限制生效
```

**场景：验收标准需要调整**

```markdown
## 五、验收标准
- [x] 用户可以通过邮箱注册
- [x] 用户可以通过邮箱登录
- [ ] JWT token 有效期为 24 小时
- [ ] 密码错误 5 次后锁定 30 分钟  ← 新增：安全加固要求
```

---

## 放弃计划

当计划不再需要执行时，应将其归档而非直接删除，以保持历史记录。

### 标准放弃流程

```bash
# 1. 更新计划状态为 ABORTED
# 在 progress.txt 或计划文件中添加：
# 状态: ABORTED
# 放弃原因: [原因说明]

# 2. 运行 plan-complete 归档（即使未完成）
python scripts/plan-complete.py '<计划名称>'
```

`plan-complete` 会检测到计划未完成，提示确认。确认后计划会被移动到 `completed/` 目录，并生成摘要。

### 手动标记放弃（不归档）

如果暂时不想归档，只想标记为放弃：

```bash
# 在 progress.txt 中
状态: ABORTED
放弃原因: 需求变更，改用 OAuth 方案

# 或在 Quick Plan 的进度表中
| 状态 | 时间 |
|------|------|
| 计划创建 | 2024-01-10 |
| 计划放弃 | 2024-01-12 — 需求变更，改用 OAuth |
```

---

## 清理旧计划

`plan-cleanup` 用于批量清理已归档的旧计划、孤立文件和空计划。

```bash
# 预览模式（推荐先预览）
python scripts/plan-cleanup.py --all --what-if

# 常用命令
python scripts/plan-cleanup.py --completed --days 30  # 清理 30 天前归档
python scripts/plan-cleanup.py --completed --days 7   # 清理 7 天前归档
python scripts/plan-cleanup.py --orphaned             # 清理孤立 summary
python scripts/plan-cleanup.py --empty                # 清理未开始的空计划
python scripts/plan-cleanup.py --all --force          # 强制清理全部
```

### 清理策略建议

| 场景 | 建议命令 |
|------|---------|
| 定期维护（每周） | `--orphaned` + `--empty` |
| 释放空间（每月） | `--completed --days 30` |
| 项目收尾 | `--all --force` |

---

## 计划目录结构速查

```
docs/exec-plans/
├── PLAN.md                    # 全局活跃计划索引（任务组 + 独立任务）
├── PLAN_COMPLETED.md          # 全局已完成计划归档
├── active/                    # 进行中的计划
│   ├── quick-plan.md          # Quick Plan
│   └── full-plan/             # Full Plan
│       ├── exec-plan.md
│       ├── feature-list.json
│       ├── memory.md
│       └── progress.txt
├── completed/                 # 已归档计划
│   ├── quick-plan.md
│   ├── full-plan/
│   └── full-plan-summary.txt  # 自动生成的摘要
└── tech-debt-tracker.md       # 技术债务追踪
```
