# Plan Memory: exec-plan任务文件拆分

> 执行记忆 — 记录计划执行过程中产生的关键工件和决策。
> 跨会话保持上下文，恢复时优先读取此文件快速了解当前状态。

---

## 文件产出

| 文件路径 | 操作(新增/修改/删除) | 关联步骤 | 说明 |
|---------|-------------------|---------|------|
| .claude/skills/writing-plans/templates/task-template.md | 新增 | Task 1 | 拆分 Task 文件的标准模板 |
| .claude/skills/writing-plans/templates/exec-plan.md | 修改 | Task 2 | 追加拆分 Task 引用写法说明 |
| .claude/skills/writing-plans/scripts/plan-validate.py | 修改 | Task 3 | 添加 tasks/ 可选验证逻辑 |
| .claude/skills/executing-plans/scripts/plan-status.py | 修改 | Task 4 | 添加 tasks/ 进度统计显示 |
| .claude/skills/writing-plans/scripts/common.py | 修改 | Task 5 | get_progress_summary 增加 tasks/ 统计字段 |
| .claude/skills/executing-plans/scripts/common.py | 修改 | Task 5 | 同上，两份文件保持一致 |
| .claude/skills/writing-plans/SKILL.md | 修改 | Task 6 | 追加拆分标准说明（4条量化标准） |
| .claude/skills/writing-plans/docs/self-review-checklist.md | 修改 | Task 6 | 追加 Task 拆分合理性检查项 |
| .claude/skills/executing-plans/SKILL.md | 修改 | Task 7 | 阶段2增加 Task 类型判断步骤 |
| .claude/skills/executing-plans/docs/workflow.md | 修改 | Task 7 | 逐 Task 执行增加位置确定步骤 |

## 关键决策

| 日期 | 决策 | 理由 | 替代方案 |
|------|------|------|---------|
| 2026-05-22 | tasks/ 目录为可选，不强制创建 | 简单计划不需要拆分，避免空目录污染 | 强制创建 tasks/（被否决——过度设计） |
| 2026-05-22 | tasks/ 统计作为补充信息，不替代 feature-list.json | 两者并存，互不替代，各自独立统计 | 用 tasks/ 替代 feature-list（被否决——feature-list 语义不同） |
