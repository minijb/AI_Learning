# Exec Plan: [计划名称]

> 完整执行计划 — 跨模块改动、新功能开发。
> **⚡ 零占位符：禁止 TBD / TODO / implement later / add error handling 等模糊描述。**
> **For agentic workers:** 使用 `executing-plans` skill 按 Task 逐个执行。

---

**Goal:** [一句话描述此计划要达成的最终状态]

**Architecture:** [2-3 句技术实现思路]

**Tech Stack:** [关键技术栈，如 Python 3.10 / FastAPI / Redis]

---

## Task 1: [组件名称]

**Files:**
- Create: `exact/path/to/new_file.py`
- Modify: `exact/path/to/existing.py:123-145`（如适用）
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

---

## Task 2: [组件名称]

**Files:**
- Create: `exact/path/to/file.py`

- [ ] **Step 1: 写测试**
  ...
  - 验证：`pytest tests/path/ -v` → 预期 **FAIL**

- [ ] **Step 2: 实现**
  ...
  - 验证：`pytest tests/path/ -v` → 预期 **PASS**

- [ ] **Step 3: Commit**
  ...

---

<!-- 根据实际需要增减 Task -->

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| [具体风险描述] | 高/中/低 | 高/中/低 | [具体应对方案] |

---

## 验收标准

- [ ] [可验证的标准 1 — 能跑命令/脚本确认]
- [ ] [可验证的标准 2]
- [ ] [可验证的标准 3]
- [ ] 所有 tests 通过
- [ ] 所有 feature-list.json 中 `passes` 为 `true`

---

## 执行记忆

> 详见 `memory.md` — 执行过程中由 `executing-plans` skill 填充。
> 跨会话恢复时优先读取此文件了解当前状态。

## 进度日志

| 日期 | 事件 | 操作者 |
|------|------|--------|
| [日期] | 计划创建 | — |
