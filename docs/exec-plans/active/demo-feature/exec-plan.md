---
title: "Exec Plan: demo-feature"
updated: 2026-06-05
---

# Exec Plan: demo-feature

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

- [ ] **Step 2: 按规格实现**
  - 文件：`exact/path/to/new_file.py`
  - 签名：`def function_name(input_value: str) -> dict:`
  - 行为：接收 X，校验 Y 不为空，调用 Z 获取数据，返回 `{id, name, status}`
  - 关键约束：Y 为空时抛 `ValueError("Y is required")`；Z 超时 3s
  - 验证：`pytest tests/path/test_file.py::test_specific_behavior -v` → 预期 **PASS**
  
  > 配置文件/脚本类 Step 写完整内容。应用代码类 Step 写上述规格——执行者根据规格自主实现。

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

<!--
当某个 Task 特别复杂（步骤 >5、代码块 >50 行、跨多个文件）时，可将其拆分为独立文件：

1. 在计划目录下创建 tasks/ 子目录
2. 复制 templates/task-template.md 到 tasks/task-NN-<name>.md 并填充
3. 在 exec-plan.md 中将该 Task 的内联内容替换为引用链接：

## Task 2: [复杂组件名] → 拆分

> 此 Task 较复杂，详细步骤见 [[tasks/task-02-xxx]]

**Files (概要):**
- Create: `path/to/file.py`
- Modify: `path/to/other.py`

执行时请读取对应的 Task 文件获取完整步骤和验证命令。
-->

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
| 2026-06-03 | 计划创建 | — |
