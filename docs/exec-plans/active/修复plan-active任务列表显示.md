# Quick Plan: 修复plan-active任务列表显示

> 轻量计划 — 适合 ≤5 步的单文件改动。
> **⚡ 零占位符：禁止 TBD / TODO / implement later / add error handling 等模糊描述。**

---

## 目标

将 `plan-active.py` 中任务列表从水平拼接（一行超长）改为垂直显示（每个任务独立一行，缩进对齐）。

---

## 验收标准

- [ ] 运行 `python .omp/skills/executing-plans/scripts/plan-active.py`，含 ≥3 个任务的计划面板中，任务垂直排列而非挤在一行
- [ ] "任务:" 标签保留，每个任务以 `  图标 任务名` 格式缩进显示在标签下方
- [ ] 阻塞信息、进度条、汇总面板等其他区域不受影响
- [ ] 无 Rich markup 渲染错误（`✓`/`✗`/`?` 图标使用 `[success]`/`[muted]` 标签包裹）

---

## 影响文件

- `.omp/skills/executing-plans/scripts/plan-active.py` — 修改任务列表渲染逻辑（约第 147-149 行）

---

## 步骤（≤5 步）

- [ ] **Step 1** — 修改任务列表渲染：将水平 `"  ".join(task_parts)` 改为垂直逐行输出
  - 文件：`.omp/skills/executing-plans/scripts/plan-active.py`，定位到 `if task_parts:` 块内的 `content_lines.append` 行
  - 变更：将单行 `Text("任务: ", ...) + Text.from_markup("  ".join(task_parts))` 替换为：
    ```python
    content_lines.append(Text("任务:", style="muted"))
    for part in task_parts:
        content_lines.append(Text.from_markup(f"  {part}"))
    ```
  - 验证：`python .omp/skills/executing-plans/scripts/plan-active.py` → 任务垂直排列，每个任务前有两个空格缩进

- [ ] **Step 2** — 确认阻塞信息、进度条、汇总面板仍然完整显示
  - 验证：`python .omp/skills/executing-plans/scripts/plan-active.py` → 面板完整，"阻塞:" 行存在，汇总表格正常

- [ ] **Step 3** — 运行 plan-validate 确认计划本身通过校验
  - 验证：`python .omp/skills/writing-plans/scripts/plan-validate.py docs/exec-plans/active/修复plan-active任务列表显示.md` → 预期 PASS

---

## 回滚方案

`git checkout .omp/skills/executing-plans/scripts/plan-active.py`

---

## 执行记忆

| 文件产出 | 函数/类 | 变量/常量 | 关键决策 |
|---------|---------|----------|---------|
| — | — | — | — |

---

## 进度

| 状态 | 时间 |
|------|------|
| 计划创建 | 2026-05-25 |
| 计划完成 | [待填写] |
