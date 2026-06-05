---
title: "Plan Memory: rich-optimize-plan-scripts"
updated: 2026-06-05
---

# Plan Memory: rich-optimize-plan-scripts

> 执行记忆 — 记录计划执行过程中产生的关键工件和决策。
> 跨会话保持上下文，恢复时优先读取此文件快速了解当前状态。

---

## 文件产出

| 文件路径 | 操作(新增/修改/删除) | 关联步骤 | 说明 |
|---------|-------------------|---------|------|
| `.omp/lib/_planning_common.py` | 已存在 | Task 1 | Rich Theme/Console/info/warn/error/error_exit/_read_file_safe/_extract_goal — 全量已集成 |
| `.omp/skills/executing-plans/scripts/common.py` | 已存在 | Task 1 | 薄封装，导入 _planning_common |
| `.omp/skills/writing-plans/scripts/common.py` | 已存在 | Task 1 | 同上 |
| `.omp/skills/executing-plans/scripts/plan-status.py` | 已存在 | Task 2 | rich.table.Table 表格化输出 |
| `.omp/skills/executing-plans/scripts/plan-active.py` | 已存在 | Task 3 | Panel/Tree/Table Rich 卡片 |
| `.omp/skills/executing-plans/scripts/plan-detail.py` | 已存在 | Task 4 | 分区 Panel + Table + Tree |
| `.omp/skills/executing-plans/scripts/plan-completed.py` | 已存在 | Task 5 | Panel 卡片输出 |
| `.omp/skills/executing-plans/scripts/plan-complete.py` | 已存在 | Task 6 | Rich 样式化流程 |
| `.omp/skills/executing-plans/scripts/plan-cleanup.py` | 已存在 | Task 7 | Table 清理预览 |
| `.omp/skills/writing-plans/scripts/plan-validate.py` | 已存在 | Task 8 | Panel 分区错误 |
| `.omp/skills/writing-plans/scripts/plan-search.py` | 已存在 | Task 9 | Table 搜索结果 |
| `.omp/skills/writing-plans/scripts/plan-new.py` | 已存在 | Task 10 | Rich 样式化确认 |
| `docs/exec-plans/active/rich-optimize-plan-scripts/feature-list.json` | 新增 | 补充 | 8 个功能点追踪 |
| `docs/exec-plans/active/rich-optimize-plan-scripts/memory.md` | 新增 | 补充 | 本文件 |
| `docs/exec-plans/active/rich-optimize-plan-scripts/progress.txt` | 新增 | 补充 | 进度追踪 |

## 关键函数 / 类

| 名称 | 所在文件 | 签名/定义 | 用途 |
|------|---------|----------|------|
| `get_console()` | `_planning_common.py` | `def get_console() -> Console` | 全局 Console 单例 |
| `info(msg)` | `_planning_common.py` | `def info(msg: str)` | Rich 样式信息输出 |
| `warn(msg)` | `_planning_common.py` | `def warn(msg: str)` | Rich 样式警告输出 |
| `error(msg, fix)` | `_planning_common.py` | `def error(msg: str, fix: str = "")` | Rich 样式错误输出 |
| `error_exit(msg, fix)` | `_planning_common.py` | `def error_exit(msg: str, fix: str = "")` | 错误输出+退出 |
| `read_file_safe(path)` | `_planning_common.py` | `def read_file_safe(path: Path) -> Optional[str]` | 安全读文件 |
| `extract_goal(content, max_len)` | `_planning_common.py` | `def extract_goal(content: str, max_len: int = 120) -> str` | 提取 Goal 行 |
| `render_progress_bar(done, total, width)` | `_planning_common.py` | `def render_progress_bar(done: int, total: int, width: int = 10) -> str` | Rich 进度条 |

## 变量 / 常量

| 名称 | 值 / 类型 | 作用域 | 说明 |
|------|----------|--------|------|
| `_PLAN_THEME` | `Theme` | 模块级 | 定义 info/warning/danger/success 等样式 |
| `_console` | `Optional[Console]` | 模块级 | Console 单例缓存 |

## 关键决策

| 日期 | 决策 | 理由 | 替代方案 |
|------|------|------|---------|
| 2026-05-25 | 确认计划已全部实现，直接归档 | 全部 10 个 Task 对应代码已存在且使用 Rich；搜索无残留手动 box-drawing/UTF-8 代码；10/10 脚本验证通过 | 逐 Task 重写（冗余——代码已就位） |

## 内容 / 配置

| 键 / 路径 | 内容摘要 | 关联 |
|-----------|---------|------|
| `_PLAN_THEME` | `info: dim cyan, warning: yellow, danger: bold red, success: green` | Task 1 |
