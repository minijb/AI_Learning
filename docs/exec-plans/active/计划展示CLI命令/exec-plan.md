# Exec Plan: 计划展示CLI命令

> 完整执行计划 — 跨模块改动、新功能开发。
> **⚡ 零占位符：禁止 TBD / TODO / implement later / add error handling 等模糊描述。**
> **For agentic workers:** 使用 `executing-plans` skill 按 Task 逐个执行。

---

**Goal:** 创建三个展示类 CLI 脚本（plan-active.py / plan-completed.py / plan-detail.py），丰富地展示活跃计划、已完成计划的内容和完成状态，复用 common.py 现有基础设施。

**Architecture:** 三个脚本均复用 `.omp/skills/executing-plans/scripts/common.py` 现有函数。`get_env()` 提供 `env.active_dir` / `env.completed_dir`；`get_progress_summary()` 返回 `{total, done, blocked, task_total?, task_done?}`（task_* 仅在 tasks/ 目录存在时出现）；`_read_index_entries()` 解析 PLAN_COMPLETED.md 表格行（内部 helper，脚本间调用可接受下划线前缀）。通过解析 exec-plan.md（正则提取 Goal/Architecture/Tech Stack 行）、feature-list.json（功能点进度）、progress.txt（任务状态和阻塞项）、PLAN_COMPLETED.md（已完成条目）提取展示信息。输出使用 Unicode box-drawing 字符的多行卡片格式。不修改现有 plan-status.py 的核心行为（仅修复一个存量 re import bug）。

**Tech Stack:** Python 3.8+ 标准库（pathlib, re, json, argparse, sys, shutil）

---

## Task 1: plan-active.py — 展示所有活跃计划

**Files:**
- Create: `.omp/skills/executing-plans/scripts/plan-active.py`

- [x] **Step 1: 实现 plan-active.py**
  - 文件：`.omp/skills/executing-plans/scripts/plan-active.py`
  - 签名：`def main():`
  - 文件末尾必须包含 `if __name__ == '__main__': main()`
  - 关键 import：`sys`, `re`, `shutil`, `Path` from `pathlib`; `get_env`, `get_progress_summary` from `common`
  - 行为：
    - 读取 `env.active_dir` 下所有目录和 `.md` 文件（排除 `.gitkeep`）
    - 无活跃计划时输出 "没有活跃计划" 并退出（退出码 0）
    - 对每个计划输出多行信息卡片：
      ```
      ┌─ 计划名 ────────────────────────────── [FULL] IN_PROGRESS ─┐
      │ 目标: <exec-plan.md 中 **Goal:** 行，截取前 120 字符>       │
      │ 进度: ████████░░ 8/10 (80%)                                 │
      │ 任务: Task 1 [✓] Task 2 [✓] Task 3 [✗] Task 4 [✗]          │
      │ 阻塞: <来自 progress.txt 的 BLOCKED 信息，无则"无">         │
      └────────────────────────────────────────────────────────────┘
      ```
    - 数据来源：
      - Goal 行：正则 `re.search(r'\*\*Goal:\*\*\s*(.+)$', content, re.M)` 从 exec-plan.md 提取；exec-plan.md 不存在时显示 "（无 exec-plan.md）"；读取失败（UnicodeDecodeError）时显示 "（编码错误）"
      - 进度：`get_progress_summary(item)` 获取 `{total, done, blocked, task_total?, task_done?}`；`total == 0` 时百分比显示 `--%` 避免除零
      - 任务列表：优先使用 `summary.get('task_total')` 和 `summary.get('task_done')`（来自 get_progress_summary 对 tasks/ 目录的统计）；若无 tasks/ 目录，从 exec-plan.md 解析 `## Task N:` 标题行 + 从 progress.txt 解析 `- [x]` / `- [ ]` 行
      - 阻塞项：从 progress.txt 中提取含 `[BLOCKED]` 的行（仅作为独立 token 匹配，避免注释行中 "fix [BLOCKED] counting" 这类误报：`re.findall(r'\[BLOCKED\]', content)` 仅在非注释行统计；或简单方案：只匹配行首以 `- [ ]` 或 `- [x]` 开头且含 `[BLOCKED]` 的行）。progress.txt 不存在时阻塞显示 "（无 progress.txt）"
      - 类型标记：[FULL]（目录）或 [QUICK]（单 .md 文件）
      - 状态标记：`[DONE]`（done>=total 且 total>0）、`[BLOCKED]`（blocked>0）、`[IN_PROGRESS]`（done>0）、`[PENDING]`（done==0）
    - 底部汇总行：
      ```
      ─── 汇总 ─────────────────────────────────────────────────────
      总进度: N/M (P%)  |  阻塞: B  |  活跃计划: A
      ```
    - 约束：
      - 仅使用 Python 标准库
      - UTF-8 处理：`try: sys.stdout.reconfigure(encoding='utf-8') except Exception: pass`（失败则 box-drawing 字符可能乱码，但不崩溃；风险表已记录 ASCII fallback 选项，但此时不强制实现）
      - 进度条：10 格 █░，按百分比取整
      - 终端宽度：`try: cols = shutil.get_terminal_size().columns except Exception: cols = 80`；box 宽度取 `min(cols, 80)`，最低不缩到 60 列以下（`max(min(cols, 80), 60)`）
      - 符号：`─` `┌` `┐` `└` `┘` `│`；check `✓` / cross `✗`
  - 验证：
    ```bash
    python .omp/skills/executing-plans/scripts/plan-active.py
    ```
    → 预期：退出码 0，显示 "学习工作区前端展示面板" 和 "计划展示CLI命令" 的卡片，含目标和进度

- [x] **Step 2: Commit**
  ```bash
  git add .omp/skills/executing-plans/scripts/plan-active.py
  git commit -m "feat: add plan-active.py — rich multi-line active plan listing"
  ```
  - 验证：`git log -1 --oneline` → 预期：以 `feat: add plan-active.py` 开头

---

## Task 2: plan-completed.py — 展示所有已完成计划

**Files:**
- Create: `.omp/skills/executing-plans/scripts/plan-completed.py`

- [x] **Step 1: 实现 plan-completed.py**
  - 文件：`.omp/skills/executing-plans/scripts/plan-completed.py`
  - 签名：`def main():`
  - 文件末尾必须包含 `if __name__ == '__main__': main()`
  - 关键 import：`sys`, `re`, `shutil`, `Path` from `pathlib`; `get_env`, `info`, `warn` from `common`; `_read_index_entries` from `common`（内部 helper，脚本间调用可接受）
  - 行为：
    - 从两个数据源收集已完成计划：
      1. `env.completed_dir` 下的目录（含 exec-plan.md 和 *-summary.txt）
      2. `PLAN_COMPLETED.md` 中的表格条目（调用 `common._read_index_entries(PLAN_COMPLETED.md 路径)`）
    - 合并去重规则：同名计划同时存在于 completed_dir 和 PLAN_COMPLETED.md 时，**优先使用 completed_dir 的数据**（目录含更丰富数据：feature-list.json、*-summary.txt）
    - 无已完成计划时输出 "没有已完成计划" 并退出（退出码 0）
    - 对每个已完成计划输出：
      ```
      ┌─ 计划名 ──────────────────── 完成: 2026-05-22 ────────────┐
      │ 类型: FULL                                                  │
      │ 摘要: <summary，优先读取 *-summary.txt 第一行，否则          │
      │        从 exec-plan.md Goal 行提取>                          │
      │ 功能点: [✓] F1 [✓] F2 [✓] F3 — 全部通过 (3/3)              │
      └────────────────────────────────────────────────────────────┘
      ```
    - 数据来源：
      - 完成日期：优先从 `*-summary.txt` 提取（正则 `re.search(r'完成日期[：:]\s*(.+)$', content)`）；fallback 到 `PLAN_COMPLETED.md` 条目的日期列；再 fallback 到目录/文件的修改时间 `datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d')`
      - 摘要：`*-summary.txt` 存在则取前 120 字符作摘要；否则从 `exec-plan.md` 提取 Goal 行；exec-plan.md 不存在时显示 "（摘要不可用）"
      - 功能点：从 `feature-list.json` 读取 features，显示每个的 pass/fail 状态（最多显示 6 个，超出显示 "还有 N 个..."）；feature-list.json 不存在或 features 为空数组时跳过此行
      - 类型标记：[FULL]（目录）或 [QUICK]（单 .md 文件归档时为 QUICK）
    - 按完成日期倒序排列（最新在前）
    - 约束：若 `completed_dir` 下无目录但 `PLAN_COMPLETED.md` 有条目，显示简表作为 fallback（仅含计划名、完成日期、类型）
    - 与 plan-active.py 视觉风格一致（同宽度逻辑：`max(min(cols, 80), 60)`）
  - 验证：
    ```bash
    python .omp/skills/executing-plans/scripts/plan-completed.py
    ```
    → 预期：退出码 0，显示 "exec-plan任务文件拆分" 及完成日期和摘要

- [x] **Step 2: Commit**
  ```bash
  git add .omp/skills/executing-plans/scripts/plan-completed.py
  git commit -m "feat: add plan-completed.py — rich multi-line completed plan listing"
  ```
  - 验证：`git log -1 --oneline` → 预期：以 `feat: add plan-completed.py` 开头

---

## Task 3: plan-detail.py — 检查具体计划状态

**Files:**
- Create: `.omp/skills/executing-plans/scripts/plan-detail.py`

- [x] **Step 1: 实现 plan-detail.py**
  - 文件：`.omp/skills/executing-plans/scripts/plan-detail.py`
  - 签名：`def main():`
  - 文件末尾必须包含 `if __name__ == '__main__': main()`
  - 关键 import：`argparse`, `sys`, `re`, `shutil`, `Path` from `pathlib`; `get_env`, `get_progress_summary`, `error_exit`, `info`, `warn` from `common`
  - 行为：
    - CLI 参数：`plan-detail.py <plan_name>`（必选位置参数）
    - 搜索逻辑：先在 `active_dir` 模糊匹配，无结果再在 `completed_dir` 搜。模糊匹配算法：case-insensitive 子串匹配于目录名或 .md 文件名（去 .md 后缀）；若多匹配，按优先级排序：(1) 完全匹配 (2) 前缀匹配 (3) 子串匹配
    - 无匹配：`error_exit(f"未找到计划: {plan_name}")`
    - 多匹配：列出候选项（编号列表，最多 5 个），输出 `error_exit(f"找到 N 个匹配: ...")`
    - 找到唯一计划目录后，分 5 段展示详细信息：
    ```
    ╔══════════════════════════════════════════════════════════════╗
    ║  计划名称 [FULL] — 状态: IN_PROGRESS                        ║
    ╚══════════════════════════════════════════════════════════════╝

    目标: <exec-plan.md Goal 行全文>
    架构: <Architecture 行全文，如有>
    技术栈: <Tech Stack 行全文，如有>

    ── 功能点 ────────────────────────────────────────────────────
    [✗] F1 核心功能: <description，截取前 100 字符>
    [✗] F2 边界处理: <description>
    [✓] F3 集成验证: <description>
    ...
    通过: N/M (P%)
    （feature-list.json 不存在或 features 为空数组时跳过整段）

    ── 任务进度 ──────────────────────────────────────────────────
    [✗] Task 1 — 项目骨架初始化
    [✓] Task 2 — 数据扫描脚本
    [✗] Task 3 — 布局与导航系统
    ...
    任务完成: N/M

    ── 阻塞项 ────────────────────────────────────────────────────
    <progress.txt 中包含 [BLOCKED] 的行，无则显示"无阻塞项">
    （progress.txt 不存在时跳过整段）

    ── 文件 ──────────────────────────────────────────────────────
    exec-plan.md    feature-list.json    progress.txt    memory.md
    tasks/task-01-xxx.md    tasks/task-02-xxx.md
    ```
    - 每段的数据来源：
      - **概览**：从 exec-plan.md 提取 Goal / Architecture / Tech Stack（正则 `\*\*(Goal|Architecture|Tech Stack):\*\*\s*(.+)$`）。exec-plan.md 不存在时显示 "（无 exec-plan.md）"；读取异常（UnicodeDecodeError）时显示 "（文件编码错误）"
      - **功能点**：从 feature-list.json 读取 features 数组，显示每项的 pass/fail + description 截断；超过 10 个时显示前 10 个 + "还有 N 个功能点，详见 feature-list.json"；feature-list.json 不存在 **或 features 为空数组** 时跳过整段；`feat_count == 0` 时进度显示 `--/0 (--%)`
      - **任务进度**：从 exec-plan.md 解析 `## Task N:` 标题行；从 progress.txt 解析 `- [x]` / `- [ ]` checkbox 状态；若存在 tasks/ 目录，读取其中 .md 文件统计子步骤 checkbox（复用 `get_progress_summary` 逻辑或独立实现）
      - **阻塞项**：从 progress.txt 提取含 `[BLOCKED]` 的行（匹配行首 `- [ ]` 或 `- [x]` 开头且含 `[BLOCKED]` 的行，避免注释行误报）
      - **文件清单**：列出计划目录下所有文件（递归），宽度允许时横向排列
    - 对于已完成计划：概览段状态显示 "COMPLETED"，日期从 `*-summary.txt`（正则 `re.search(r'完成日期[：:]\s*(.+)$', content)`）或 `PLAN_COMPLETED.md` 提取；若均不可用，使用目录修改时间
    - **PLAN_COMPLETED.md 唯一匹配 fallback**：当计划仅在 PLAN_COMPLETED.md 中存在（无文件系统目录）时，仅输出概览段（从 index 条目提取可用字段），其他段显示 "（仅索引记录，无完整数据）"
    - 约束：
      - feature-list.json 不存在 **或 features 为空数组** 时跳过 "功能点" 段
      - progress.txt 不存在时跳过 "阻塞项" 段
      - exec-plan.md 不存在时概览段显示 "（无 exec-plan.md）"，其他段仅显示可用数据
      - UTF-8：`try: sys.stdout.reconfigure(encoding='utf-8') except Exception: pass`
      - 终端宽度：`try: cols = shutil.get_terminal_size().columns except Exception: cols = 80`；双层线框宽度取 `max(min(cols, 80), 60)`
      - Unix box-drawing 双层线：`╔` `╗` `╚` `╝` `║` `═` 用于标题框
      - 段分隔线：`──` 单线 60 字符长
      - check `✓` / cross `✗`
  - 验证：
    ```bash
    python .omp/skills/executing-plans/scripts/plan-detail.py "学习工作区前端展示面板"
    ```
    → 预期：退出码 0，显示 5 段详细信息，含 8 个功能点状态和 8 个 Task 进度

- [x] **Step 2: Commit**
  ```bash
  git add .omp/skills/executing-plans/scripts/plan-detail.py
  git commit -m "feat: add plan-detail.py — detailed single-plan status view"
  ```
  - 验证：`git log -1 --oneline` → 预期：以 `feat: add plan-detail.py` 开头

---

## Task 4: 修复存量 bug + 端到端验证

- [x] **Step 0: 修复 plan-status.py 的 re import bug**
  - 文件：`.omp/skills/executing-plans/scripts/plan-status.py`
  - 问题：第 77-78 行在 `import re`（第 88 行）之前使用 `re.findall`，导致含 tasks/ 目录的 FULL 计划统计崩溃
  - 修复：在文件顶部（其他 import 之后）添加 `import re`
  - 验证：
    ```bash
    python .omp/skills/executing-plans/scripts/plan-status.py
    ```
    → 预期：退出码 0，输出与修复前一致（不再报 NameError）

- [x] **Step 1: 运行 plan-active.py**
  ```bash
  python .omp/skills/executing-plans/scripts/plan-active.py
  ```
  - 验证：退出码 0，输出包含 "学习工作区前端展示面板" 和 "计划展示CLI命令" 的卡片

- [x] **Step 2: 运行 plan-completed.py**
  ```bash
  python .omp/skills/executing-plans/scripts/plan-completed.py
  ```
  - 验证：退出码 0，输出包含 "exec-plan任务文件拆分" 的卡片

- [x] **Step 3: 运行 plan-detail.py（活跃计划 + 已完成计划）**
  ```bash
  python .omp/skills/executing-plans/scripts/plan-detail.py "学习工作区前端展示面板"
  python .omp/skills/executing-plans/scripts/plan-detail.py "exec-plan任务文件拆分"
  ```
  - 验证：两次均退出码 0，分别显示活跃和已完成计划的 5 段详细信息

- [x] **Step 4: 测试错误路径**
  ```bash
  python .omp/skills/executing-plans/scripts/plan-detail.py "不存在的计划"
  ```
  - 验证：退出码非 0，输出 "未找到计划: 不存在的计划"

- [x] **Step 5: 确认 plan-status.py 行为不变**
  ```bash
  python .omp/skills/executing-plans/scripts/plan-status.py
  ```
  - 验证：退出码 0，输出格式与修复前一致（仅不再因 re import 崩溃）

- [x] **Step 6: Commit**
  ```bash
  git add .omp/skills/executing-plans/scripts/
  git commit -m "chore: end-to-end verification of plan display scripts, fix plan-status.py re import bug"
  ```
  - 验证：`git log -1 --oneline` → 预期：包含 "verification"

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| exec-plan.md Goal 行格式不统一导致提取失败 | 低 | 低 | 宽松正则 `\*\*Goal:\*\*\s*(.+)$`；提取失败时显示 "（无目标摘要）" |
| Unicode box-drawing 字符在非 UTF-8 终端显示乱码 | 低 | 低 | try/except 包裹 `stdout.reconfigure(encoding='utf-8')`；不崩溃 |
| completed_dir 下存在非计划目录 | 低 | 中 | 只处理含 exec-plan.md 或 *-summary.txt 的目录 |
| 终端过窄导致 box 溢出换行 | 低 | 低 | 检测 `shutil.get_terminal_size()`，默认 80 列，最低 60 列 |
| progress.txt 中 `[BLOCKED]` 子串在注释行误匹配 | 低 | 低 | 仅匹配以 `- [ ]` 或 `- [x]` 开头的行 |
| exec-plan.md 编码非 UTF-8 | 低 | 低 | try/except 包裹文件读取，失败时显示 "（编码错误）" |
| feature-list.json 的 features 为空数组导致除零 | 低 | 低 | `total == 0` 时显示 `--/0 (--%)` |

## 验收标准

- [x] `plan-active.py` 输出所有活跃计划，每个卡片含目标摘要、10 格进度条、任务状态
- [x] `plan-completed.py` 输出所有已完成计划，每个卡片含完成日期和摘要
- [x] `plan-detail.py <name>` 输出指定计划的 5 段详细信息
- [x] `plan-detail.py "不存在的计划"` 返回非 0 退出码并输出错误信息
- [x] 三个脚本均在 Windows 终端正确输出 UTF-8 字符（含 box-drawing）；非 UTF-8 终端不崩溃
- [x] `plan-status.py` 修复 re import bug 后行为不变
- [x] 所有 feature-list.json 中 `passes` 为 `true`
- [x] 边界情况全部覆盖：无活跃计划、无已完成计划、空 feature-list.json、缺失 progress.txt、缺失 exec-plan.md、PLAN_COMPLETED.md-only 匹配、除零保护

---

## 执行记忆

> 详见 `memory.md` — 执行过程中由 `executing-plans` skill 填充。
> 跨会话恢复时优先读取此文件了解当前状态。

## 进度日志

| 日期 | 事件 | 操作者 |
|------|------|--------|
| 2026-05-24 | 计划创建 | — |
| 2026-05-24 | 健壮性审查修复（F1-F3, W1-W11, M1-M6） | — |
