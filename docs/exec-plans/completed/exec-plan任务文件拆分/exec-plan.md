# Exec Plan: exec-plan任务文件拆分

> 完整执行计划 — 支持将复杂 Task 拆分为独立 markdown 文件。
> **For agentic workers:** 使用 `executing-plans` skill 按 Task 逐个执行。

---

**Goal:** 支持两种 Task 定义模式：简单 Task 内联在 `exec-plan.md` 中（现状），复杂 Task 拆分到 `tasks/` 子目录下的独立 `.md` 文件。`exec-plan.md` 通过引用链接指向拆分出的 Task 文件。同时更新 writing-plans 和 executing-plans 两个 skill 以支持双模式。

**Architecture:** `tasks/` 目录为可选——仅在计划包含复杂 Task 时由计划作者手动创建。`exec-plan.md` 模板保留内联 Task 格式，同时增加"拆分 Task"的写法和引用约定。`plan-new.py` 不变（不强制创建 tasks/）。`plan-validate.py` 增加对 tasks/ 目录的检查但仅作为 warning（若存在 tasks/ 则验证其结构，不存在也不报错）。`plan-status.py` 和 `common.py` 增加从 tasks/ 统计进度的能力，无 tasks/ 时回退到现有逻辑。两个 skill 的 SKILL.md 和 docs/ 同步更新，说明何时拆分、如何拆分。

**Tech Stack:** Python 3.8+ (标准库), Markdown

---

## Task 索引

| 编号 | Task 名称 | 类型 | 文件 | 状态 |
|------|----------|------|------|------|
| 01 | 新增 task-template.md 模板 | 简单(内联) | — | ⬜ 待执行 |
| 02 | 修改 exec-plan.md 模板支持双模式 | 简单(内联) | — | ⬜ 待执行 |
| 03 | 修改 plan-validate.py 可选验证 tasks/ | 简单(内联) | — | ⬜ 待执行 |
| 04 | 修改 plan-status.py 统计 tasks/ | 简单(内联) | — | ⬜ 待执行 |
| 05 | 修改两个 common.py 同步进度逻辑 | 简单(内联) | — | ⬜ 待执行 |
| 06 | 修改 writing-plans SKILL.md + docs | 简单(内联) | — | ⬜ 待执行 |
| 07 | 修改 executing-plans SKILL.md + docs | 简单(内联) | — | ⬜ 待执行 |

---

## Task 1: 新增 task-template.md 模板

**Files:**
- Create: `.omp/skills/writing-plans/templates/task-template.md`

- [ ] **Step 1: 创建 Task 模板文件**
  ```markdown
  # Task [NN]: [组件名称]

  > 所属计划: [计划名称] | 执行顺序: 第 [NN] 步

  **Files:**
  - Create: `exact/path/to/new_file.py`
  - Modify: `exact/path/to/existing.py:123-145`
  - Test: `tests/exact/path/to/test_file.py`

  - [ ] **Step 1: 写测试**
    ```python
    # [写出具体测试代码]
    def test_specific_behavior():
        result = function_name(input_value)
        assert result == expected_value
    ```
    - 验证：`pytest tests/path/test_file.py::test_specific_behavior -v` → 预期 **FAIL**（功能未实现）

  - [ ] **Step 2: 实现最小代码**
    ```python
    # [写出完整实现代码，含 import]
    def function_name(input_value):
        return expected_value
    ```
    - 验证：`pytest tests/path/test_file.py::test_specific_behavior -v` → 预期 **PASS**

  - [ ] **Step 3: Commit**
    ```bash
    git add tests/path/ src/path/
    git commit -m "feat: [简短描述]"
    ```
    - 验证：`git log -1 --oneline` → 预期：`feat: [简短描述]`
  ```
  - 验证：`python -c "from pathlib import Path; p = Path('.omp/skills/writing-plans/templates/task-template.md'); print('OK' if p.exists() else 'FAIL')"` → 预期 **OK**

---

## Task 2: 修改 exec-plan.md 模板支持双模式

**Files:**
- Modify: `.omp/skills/writing-plans/templates/exec-plan.md`

- [ ] **Step 1: 在模板中增加拆分 Task 引用写法**
  在现有 exec-plan.md 模板末尾（`<!-- 根据实际需要增减 Task -->` 注释之后）追加一段说明和示例：
  ````markdown
  <!--
  当某个 Task 特别复杂（步骤 >5、代码块 >50 行、跨多个文件）时，可将其拆分为独立文件：

  1. 在计划目录下创建 tasks/ 子目录
  2. 复制 templates/task-template.md 到 tasks/task-NN-<name>.md 并填充
  3. 在 exec-plan.md 中将该 Task 的内联内容替换为引用链接：

  ## Task 2: [复杂组件名] → 拆分

  > 此 Task 较复杂，详细步骤见 [tasks/task-02-xxx.md](tasks/task-02-xxx.md)

  **Files (概要):**
  - Create: `path/to/file.py`
  - Modify: `path/to/other.py`

  执行时请读取对应的 Task 文件获取完整步骤和验证命令。
  -->
  ````
  - 验证：`python -c "from pathlib import Path; c = Path('.omp/skills/writing-plans/templates/exec-plan.md').read_text(encoding='utf-8'); assert 'tasks/' in c; assert 'task-template.md' in c; print('OK')"` → 预期 **OK**

---

## Task 3: 修改 plan-validate.py 可选验证 tasks/

**Files:**
- Modify: `.omp/skills/writing-plans/scripts/plan-validate.py`

- [ ] **Step 1: 在 validate_full_plan() 中添加 tasks/ 的温和检查**
  在 `validate_full_plan` 函数的 `required_files` 检查之后添加：
  ```python
  # tasks/ 目录为可选——存在时验证结构，不存在不报错
  tasks_dir = plan_dir / "tasks"
  if tasks_dir.is_dir():
      task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == '.md'])
      if not task_files:
          add_warn("tasks/ 目录存在但为空，建议添加 Task 文件或删除空目录")
      else:
          for tf in task_files:
              tcontent = tf.read_text(encoding="utf-8")
              if not re.search(r'# Task\s+\d+:', tcontent):
                  add_error(f"tasks/{tf.name} 缺少 '# Task NN:' 标题", "按 task-template.md 格式添加标题。")
              # 零占位符检查
              check_no_placeholders(tcontent, f"{plan_dir.name}/tasks/{tf.name}")
  ```
  注意：不检查 "缺少 tasks/ 目录"——它是可选的。
  - 验证：`python .omp/skills/writing-plans/scripts/plan-validate.py docs/exec-plans/active/exec-plan任务文件拆分` → 预期 **PASS**

---

## Task 4: 修改 executing-plans plan-status.py 统计 tasks/

**Files:**
- Modify: `.omp/skills/executing-plans/scripts/plan-status.py`

- [ ] **Step 1: 在 is_dir 分支中增加 tasks/ 统计**
  在 `if item.is_dir():` 分支的进度统计中，增加检测 tasks/ 目录的逻辑：
  ```python
  # 若存在 tasks/ 目录，统计 Task 文件完成情况
  tasks_dir = item / "tasks"
  if tasks_dir.is_dir():
      task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == '.md'])
      if task_files:
          task_total = len(task_files)
          task_done = 0
          for tf in task_files:
              tcontent = tf.read_text(encoding="utf-8")
              all_cb = len(re.findall(r'- \[.\]', tcontent))
              done_cb = len(re.findall(r'- \[x\]', tcontent))
              if all_cb > 0 and done_cb >= all_cb:
                  task_done += 1
          # 用 tasks/ 统计补充显示（不替代 feature-list.json 统计，两者并存）
          print(f"  Tasks: {task_done}/{task_total} 完成")
  ```
  - 验证：`python .omp/skills/executing-plans/scripts/plan-status.py` → 预期 输出含本计划信息

---

## Task 5: 修改两个 common.py 同步进度逻辑

**Files:**
- Modify: `.omp/skills/writing-plans/scripts/common.py`
- Modify: `.omp/skills/executing-plans/scripts/common.py`

- [ ] **Step 1: 在 get_progress_summary() 中添加 tasks/ 统计字段**
  在两个 common.py 的 `get_progress_summary` 函数末尾（return 之前）添加：
  ```python
  # 可选 tasks/ 目录统计
  tasks_dir = plan_dir / "tasks"
  if tasks_dir.is_dir():
      import re as _re
      task_files = sorted([f for f in tasks_dir.iterdir() if f.suffix == '.md'])
      if task_files:
          summary["task_total"] = len(task_files)
          task_done = 0
          for tf in task_files:
              tcontent = tf.read_text(encoding="utf-8")
              all_cb = len(_re.findall(r'- \[.\]', tcontent))
              done_cb = len(_re.findall(r'- \[x\]', tcontent))
              if all_cb > 0 and done_cb >= all_cb:
                  task_done += 1
          summary["task_done"] = task_done
  ```
  两份 common.py 做**完全相同**的修改。
  - 验证：`diff .omp/skills/writing-plans/scripts/common.py .omp/skills/executing-plans/scripts/common.py` → 预期 无差异

---

## Task 6: 修改 writing-plans SKILL.md + docs

**Files:**
- Modify: `.omp/skills/writing-plans/SKILL.md`
- Modify: `.omp/skills/writing-plans/docs/self-review-checklist.md`

- [ ] **Step 1: 更新 SKILL.md 中的 Exec Plan 模板**
  在 SKILL.md 的 Exec Plan 模板最后，追加说明：
  ````markdown
  <!-- 复杂 Task 拆分 -->
  当 Task 满足以下任一条件时，建议拆分为独立文件（`tasks/task-NN-<name>.md`）：
  - 步骤数 >5
  - 代码块总行数 >50
  - 跨 3 个以上文件
  - 需要独立 subagent 执行

  拆分方法：复制 `templates/task-template.md` → `tasks/` 目录 → 填充内容 →
  在 exec-plan.md 中替换该 Task 的内联内容为引用链接。
  ````
  - 验证：手动检查 SKILL.md 包含上述内容

- [ ] **Step 2: 更新 self-review-checklist.md**
  在 self-review-checklist.md 末尾添加一项：
  ```markdown
  ## 7. Task 拆分合理性

  - [ ] 复杂 Task（>5 步 / >50 行代码 / 跨 3+ 文件）已拆分到 tasks/ 目录？
  - [ ] 拆分出的 Task 文件使用 task-template.md 模板格式？
  - [ ] exec-plan.md 中对应的 Task 节包含指向 tasks/ 的引用链接？
  - [ ] 简单 Task（≤5 步）保持内联，未过度拆分？
  ```
  - 验证：手动检查

---

## Task 7: 修改 executing-plans SKILL.md + docs

**Files:**
- Modify: `.omp/skills/executing-plans/SKILL.md`
- Modify: `.omp/skills/executing-plans/docs/workflow.md`

- [ ] **Step 1: 更新 SKILL.md 执行协议**
  在 SKILL.md 的「阶段 2：逐任务执行」部分，在现有描述前添加：
  ```markdown
  ### 阶段 2：逐任务执行

  对于每个 Task：

  1. **判断 Task 类型**：
     - 内联 Task → 直接读取 exec-plan.md 中该 Task 的内容
     - 拆分 Task（含 `→ 拆分` 标记和文件链接）→ 按链接读取 `tasks/task-NN-xxx.md`
  2. **逐 Step 执行**：照代码写 → 运行验证 → 核对预期
  3. **Commit**（按计划指示）
  4. **更新进度** → `progress.txt`
  ```
  - 验证：手动检查

- [ ] **Step 2: 更新 docs/workflow.md**
  在「阶段 2：逐 Task 执行」的每个 Task 流程中，将「读取完整 Task」改为：
  ```markdown
  1. **确定 Task 位置** — 内联在 exec-plan.md 或拆分到 tasks/task-NN-xxx.md
  2. **读取 Task 完整内容** — 所有 Step + 代码 + 验证命令
  3. **逐 Step 执行**
  ...
  ```
  - 验证：手动检查

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 两个 common.py 不同步 | 中 | 高 | Task 5 明确要求同时修改两份文件，验证 diff 一致 |
| 拆分判断标准模糊导致使用混乱 | 低 | 低 | SKILL.md 明确给出 4 条量化标准（>5步/>50行/跨3文件/需独立subagent） |
| tasks/ 目录存在但为空 | 低 | 低 | plan-validate 给出 warning 提示 |

---

## 验收标准

- [ ] `task-template.md` 模板存在且格式正确
- [ ] `exec-plan.md` 模板保留内联 Task 格式，追加拆分 Task 的写法和引用约定
- [ ] `plan-validate.py` 在 tasks/ 存在时验证其结构，不存在时不报错
- [ ] `plan-status.py` 在 tasks/ 存在时统计 Task 文件完成情况
- [ ] 两个 `common.py` 的 `get_progress_summary` 包含 tasks/ 统计字段且内容一致
- [ ] writing-plans SKILL.md 说明"何时拆分"的 4 条标准
- [ ] executing-plans SKILL.md 说明执行时如何判断 Task 类型（内联 vs 拆分）
- [ ] 所有 feature-list.json 中 `passes` 为 `true`

---

## 执行记忆

> 详见 `memory.md`

## 进度日志

| 日期 | 事件 | 操作者 |
|------|------|--------|
| 2026-05-21 | 计划创建 | — |
