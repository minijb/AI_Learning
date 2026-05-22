---
name: writing-plans
description: >
  创建可执行计划。用户提到"写计划"、"创建计划"、"制定计划"、"规划"、
  "分步骤"、"拆解任务"、"拆分Task"、"roadmap"、"实现步骤"时触发。
  适用于所有多步骤工作：实现功能、构建新模块、跨模块改动、重构、
  修复跨文件 bug、添加测试、架构变更。支持内联 Task 和拆分 Task 到独立文件。
  写任何非 trivial 代码前，必须先创建计划。当无活跃计划且任务超出一行修复时，主动建议。
---

# Writing Plans — 创建可执行计划

> 写计划，不写代码。产出一份**零上下文工程师**可以直接照做的施工图纸。

---

## 核心定位

本 skill 只负责**创建计划**。计划的执行由 `executing-plans` skill 负责。

两种模式：

| 模式 | 适用场景 | 预计耗时 |
|------|---------|---------|
| **Quick Plan** | 小改动、bug 修复、单文件修改（≤5 步） | <30 分钟 |
| **Exec Plan** | 复杂功能、跨模块改动、多步骤任务 | >30 分钟 |

**判断标准：** 步骤数、影响文件数、预计耗时、复杂度。不确定时，选 Exec Plan。

---

## 5 秒速查

| 我想... | 命令/操作 | 详细指南 |
|---------|----------|----------|
| 创建计划 | `python scripts/plan-new.py --quick\|--full '名称'` | `docs/quickstart.md` |
| 搜索已有计划 | `python scripts/plan-search.py <关键词>` | `docs/managing-plans.md` |
| 验证计划 | `python scripts/plan-validate.py <路径>` | `docs/workflow.md` |
| 完整命令参考 | 读取 `docs/script-reference.md` | `docs/script-reference.md` |

---

## 何时必须使用

只要满足以下任一条件，就必须先创建计划：

- 用户明确提到创建计划
- 涉及多个文件的任何改动
- 新增功能、模块、API 或组件
- 重构现有代码
- 修复跨多个文件的 bug
- 需要估算工作量或时间
- 任何不确定一步能做完的任务

---

## 计划哲学：写给另一个 Agent 看

**核心假设：执行者不了解你的代码库，不参与计划制定，完全是"零上下文熟练工"。**

因此计划必须：
- **自包含**——不依赖外部知识或"大家都知道"的约定
- **精确到行**——文件路径、命令、验证，不写"大致思路"
- **零占位符**——绝对禁止 TBD、TODO、implement later、add error handling 等

### 规格 vs 实现

计划对不同类型文件采用不同精度：

| 文件类型 | 在计划中写什么 | 原因 |
|---------|-------------|------|
| **配置文件** (.json, .config, .gitignore, package.json scripts) | 完整内容 | 内容即规格，无需设计决策 |
| **应用代码** (.tsx, .ts, .py, 组件/Hook/页面) | 接口契约 + 行为描述 + 验证命令 | 熟练工根据规格自主实现 |

应用代码步骤必须包含：
- **接口契约**：文件路径、导出函数/组件签名、props/参数类型、关键 import
- **行为描述**：做什么（what），不写怎么做（how）——留给执行者
- **关键约束**：必须处理的边界条件（具体列出，不写 "handle edge cases"）
- **验证命令**：精确到 flag 和预期输出

**执行者不是来抄代码的，是来根据规格写代码的。**

---

## 任务精细粒度

**每个 Step 是 2-5 分钟的一个原子操作。** 以 TDD 节奏组织：

```
Step N — 实现某功能
  - [ ] 写好失败测试（完整测试代码） → `pytest test_xxx.py -v` → 预期 FAIL
  - [ ] 按规格实现：
    - 文件：`src/module/file.py`
    - 签名：`def function_name(x: str) -> dict:`
    - 行为：接收 X，校验非空，调 Z API，返回 `{id, name}`
    - 约束：X 为空抛 `ValueError`；Z 超时 3s
    - 验证：`pytest test_xxx.py -v` → 预期 PASS
  - [ ] Commit → `git add ... && git commit -m "feat: ..."`
```

**不是**这样的 coarse 步骤：
- ❌ "实现用户登录功能"（太粗——不可验证）
- ✅ "写登录测试 → 跑测试 → 实现 validatePassword → 验证 → commit"（可逐行照做）

---

## 零占位符原则

以下模式在计划中**绝对禁止**。`plan-validate` 会拒绝含它们的计划：

| 禁止模式 | 原因 |
|---------|------|
| `TBD`、`TODO`、`FIXME` | 计划是最终产物，不是草稿 |
| `implement later`、`fill in details` | 执行者无法"稍后实现"未定义的东西 |
| `add appropriate error handling` | "适当"不可执行——写具体代码 |
| `handle edge cases` | 列出具体 edge case 和处理方式 |
| `write tests for the above` | 写出具体测试代码 |
| `similar to Task N` | 重复完整代码——执行者可能按乱序读 |

**原则：如果执行者看到这句话不知道该敲什么键盘，这句话就不该在计划里。**

> **注意：** "零占位符"要求写入计划的内容必须精确可执行，但这不意味着"把所有实现代码写进计划"。计划是蓝图，不是源码——对应用代码，写清楚接口契约和行为约束即可，不必逐行写入完整实现。配置文件（内容即规格）和测试代码（验证即规格）不受此限。

---

## 计划模板

### Quick Plan 模板

```markdown
# Quick Plan: [一行描述]

## 目标
[一句话]

## 验收标准
- [ ] [可验证的条件]

## 影响文件
- `path/to/file.ext` — [改动说明]

## 步骤（≤5 步）
- [ ] **Step 1** — [步骤描述]
  - 验证：`[精确命令]` → 预期：[输出]

## 回滚方案
[如何撤销]

## 进度
| 状态 | 时间 |
|------|------|
| 计划创建 | [日期] |
```

### Exec Plan 模板

````markdown
# Exec Plan: [计划名称]

> **For agentic workers:** 使用 executing-plans skill 按任务逐个执行。

**Goal:** [一句话目标]

**Architecture:** [2-3 句技术方案]

**Tech Stack:** [关键技术栈]

---

## Task 1: [组件名]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`

- [ ] **Step 1: 写测试**
  ```python
  def test_xxx():
      assert function(input) == expected
  ```
  - 验证：`pytest tests/test_xxx.py::test_xxx -v` → 预期 FAIL

- [ ] **Step 2: 按规格实现**
  - 文件：`exact/path/to/new_file.py`
  - 签名：`def function_name(input_value: str) -> dict:`
  - 行为：接收 X，校验 Y 不为空，调用 Z 获取数据，返回 `{id, name, status}`
  - 关键约束：Y 为空时抛 `ValueError("Y is required")`；Z 超时 3s
  - 验证：`pytest tests/test_xxx.py::test_xxx -v` → 预期 PASS
  
  > 配置文件/脚本类 Step 写完整内容。应用代码类 Step 写上述规格。

- [ ] **Step 3: Commit**
  ```bash
  git add tests/ src/
  git commit -m "feat: [描述]"
  ```

## Task 2: [下一个组件]
...

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| [风险] | 高/中/低 | 高/中/低 | [措施] |

## 验收标准

- [ ] [可验证的标准]
````

<!-- 复杂 Task 拆分 -->
当 Task 满足以下任一条件时，建议拆分为独立文件（`tasks/task-NN-<name>.md`）：
- 步骤数 >5
- 代码块总行数 >50
- 跨 3 个以上文件
- 需要独立 subagent 执行

拆分方法：复制 `templates/task-template.md` → `tasks/` 目录 → 填充内容 →
在 exec-plan.md 中替换该 Task 的内联内容为引用链接。

> 完整模板在 `templates/quick-plan.md` 和 `templates/exec-plan.md`。`plan-new.py` 会自动复制它们。

---

## Self-Review（自审检查清单）

计划写完后，对照检查（详见 `docs/self-review-checklist.md`）：

1. **Spec 覆盖**：每个需求都能指到对应的 Task？
2. **占位符扫描**：搜索 TBD/TODO/implement later/add error handling——全删除
3. **类型一致性**：Task 3 引用的函数名和 Task 1 定义的一致？
4. **路径精确性**：所有文件路径是真实项目路径，不是占位符？
5. **可验证性**：每一步都有精确命令和预期输出？
6. **可执行性**：零上下文工程师能根据规格写出正确实现？
7. **Task 拆分合理性**：复杂 Task（>5 步 / >50 行 / 跨 3+ 文件）已拆分？简单 Task 未过度拆分？

发现问题 → 直接修复，不重审。

---

## Execution Handoff（执行交接）

计划写完后，告知用户执行选项：

> "计划已保存到 `docs/exec-plans/active/<name>/`。两种执行方式：
>
> **1. Subagent 模式（推荐）** — 使用 `executing-plans` skill，每任务独立 subagent + 双重审查
>
> **2. Inline 模式** — 在当前会话中使用 `executing-plans` skill，逐任务执行 + 进度追踪
>
> 选择哪种？"

---

## 护栏规则

1. **计划优先** — 无书面计划，不写代码。
   *为什么：* 需求理解偏差的返工成本远高于计划成本。

2. **需求澄清优先** — 用户指令模糊时，**禁止直接创建计划**。先提问让用户选择，直到需求完整。
   *为什么：* 模糊指令必然导致方向错误——一次澄清可省十次返工。

3. **零占位符** — 计划中禁止 TBD/TODO/implement later 等模式。`plan-validate` 强制执行。
   *为什么：* 执行者无法对模糊指令做出精确动作。

4. **计划版本化** — 计划文件存储在项目内，随代码版本控制。
   *为什么：* 不在项目本地的内容等于不存在。

5. **成功沉默** — 验证通过不输出；失败才输出含修复指令的错误。
   *为什么：* 噪声淹没信号。

---

## 关键文件索引

| 文件 | 用途 | 何时加载 |
|------|------|---------|
| `SKILL.md` | 入口文档 | 触发 writing-plans 时 |
| `docs/quickstart.md` | 5 分钟快速上手 | 首次创建计划 |
| `docs/workflow.md` | 完整创建流程 | 需要理解全流程 |
| `docs/planning-principles.md` | 计划系统核心理念 | 需要深入理解 |
| `docs/script-reference.md` | 脚本参数速查表 | 精确调用脚本 |
| `docs/self-review-checklist.md` | 自审清单 | 计划写完后 |
| `templates/quick-plan.md` | Quick Plan 模板 | 创建 Quick Plan |
| `templates/exec-plan.md` | Exec Plan 模板 | 创建 Exec Plan |
| `templates/task-template.md` | 拆分 Task 模板 | 复杂 Task 需拆分到独立文件时 |
| `docs/exec-plans/tech-debt-tracker.md` | 技术债务追踪 | 记录计划执行中发现的技术债务 |

---

## 场景示例

**场景 1：跨模块新功能 → Exec Plan**

> 用户说："给订单模块加 Redis 缓存"

1. 查重：`python scripts/plan-search.py "订单 缓存"` → 无匹配
2. 判断：多文件（controller/service/config），步骤 >5 → Exec Plan
3. 创建：`python scripts/plan-new.py --full "订单模块缓存层" --summary "Redis 缓存订单查询结果"`
4. 填充 exec-plan.md：Task 1 写缓存接口测试 → Task 2 实现 Redis 连接 → Task 3 集成到 service → ...
5. Self-review：扫描 TBD → 无占位符 → 路径精确 → 每步有验证命令
6. 交接：告知用户执行选项

**场景 2：单文件修复 → Quick Plan**

> 用户说："修复导航栏 Safari 样式偏移"

1. 查重：`python scripts/plan-search.py "导航栏"` → 无匹配
2. 判断：单文件 CSS，步骤 ≤3 → Quick Plan
3. 创建：`python scripts/plan-new.py --quick "修复导航栏Safari样式"`
4. 填充：验收标准（Safari 14+ 导航居中）+ 每步验证命令
5. Self-review：通过
6. 交接

**场景 3：需求模糊 → 主动澄清**

> 用户说："优化用户模块"

1. 识别范围不清：是查询性能？重构？缓存？
2. 提问让用户选择 → 用户选"加缓存"
3. 回到场景 1 流程

---

## 平台支持

| 操作系统 | 运行方式 | 依赖 |
|---------|---------|------|
| Linux/macOS | `python scripts/plan-xxx.py` | Python 3.8+ |
| Windows | `python scripts\plan-xxx.py` | Python 3.8+ |

所有脚本使用 Python 标准库，功能完全跨平台。
