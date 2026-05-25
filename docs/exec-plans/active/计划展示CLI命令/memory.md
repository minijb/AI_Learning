# Plan Memory: 计划展示CLI命令

> 执行记忆 — 记录计划执行过程中产生的关键工件和决策。
> 跨会话保持上下文，恢复时优先读取此文件快速了解当前状态。

---

## 文件产出

| 文件路径 | 操作(新增/修改/删除) | 关联步骤 | 说明 |
|---------|-------------------|---------|------|
| `.omp/skills/executing-plans/scripts/plan-active.py` | 新增 | Task 1 | 活跃计划展示脚本，Unicode box-drawing 卡片格式 |
| `.omp/skills/executing-plans/scripts/plan-completed.py` | 新增 | Task 2 | 已完成计划展示脚本，合并 completed_dir 和 PLAN_COMPLETED.md 数据源 |
| `.omp/skills/executing-plans/scripts/plan-detail.py` | 新增 | Task 3 | 单计划详细状态查看，5 段信息展示，模糊搜索支持 |
| — | — | — | 端到端验证通过：plan-active.py / plan-completed.py / plan-detail.py 三个脚本所有验收标准均满足。plan-status.py re import bug 已存在修复（import re 位于文件顶部 line 7）。 |

## 关键函数 / 类

| 名称 | 所在文件 | 签名/定义 | 用途 |
|------|---------|----------|------|
| `main` | `plan-active.py` | `def main():` | 扫描 active_dir 下所有计划，渲染 Unicode box-drawing 多行卡片 |

## 变量 / 常量

| 名称 | 值 / 类型 | 作用域 | 说明 |
|------|----------|--------|------|
| — | — | — | — |

## 关键决策

| 日期 | 决策 | 理由 | 替代方案 |
|------|------|------|---------|
| 2026-05-25 | plan-active.py 任务状态来源优先级：tasks/ 目录 > exec-plan.md + progress.txt 交叉解析 | plan 规格指定 | 仅依赖 exec-plan.md 标题解析 |

## 内容 / 配置

| 键 / 路径 | 内容摘要 | 关联 |
|-----------|---------|------|
| — | — | — |
