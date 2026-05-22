---
name: executing-plans
description: >
  执行已写好的计划。用户提到"执行计划"、"按计划做"、"落实计划"、
  "实施计划"、"按步骤执行"、"照计划来"时触发。
  加载计划 → 批判性审阅 → 逐任务执行（含内联和拆分 Task） → 逐 Task 闭环 → 完成后归档。
  假设执行者不参与计划制定——严格照做，不擅自偏离。
---

# Executing Plans — 执行已写好的计划

> 你是"零上下文熟练工"——严格照计划做，不猜、不跳过、不"优化"。偏离时停+问。

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

---

## 核心定位

本 skill 只负责**执行计划**。计划应该已由 `writing-plans` skill 创建好。

**核心假设：**
- 执行者没有参与计划制定
- 执行者对代码库的了解为零
- 计划是唯一的真实来源——所有所需信息都在计划中

---

## 5 秒速查

| 我想... | 命令/操作 | 详细指南 |
|---------|----------|----------|
| 查看活跃计划 | `python scripts/plan-status.py` | `docs/managing-plans.md` |
| 完成归档 | `python scripts/plan-complete.py '名称'` | `docs/workflow.md` |
| 清理旧计划 | `python scripts/plan-cleanup.py --all --what-if` | `docs/managing-plans.md` |
| 完整命令参考 | 读取 `docs/script-reference.md` | `docs/script-reference.md` |

---

## 执行协议

### 阶段 1：加载与审阅

1. **加载计划** — 读取 `docs/exec-plans/active/<name>/exec-plan.md`
2. **批判性审阅** — 检查计划是否有缺口、模糊处、不可执行的步骤。执行者有权提出问题。
3. **如果计划有缺陷** → 停止，列出问题让用户确认/修正
4. **如果计划可执行** → 进入执行阶段

### 阶段 2：逐任务执行

对于每个 Task：

1. **判断 Task 类型**：
   - 内联 Task → 直接读取 exec-plan.md 中该 Task 的内容
   - 拆分 Task（含 `→ 拆分` 标记和文件链接）→ 按链接读取 `tasks/task-NN-xxx.md`
2. **逐 Step 执行**：
   - **配置文件/脚本** → 照计划中的完整代码写，运行验证，核对预期
   - **应用代码** → 读计划中的规格（接口契约 + 行为描述 + 约束），自主实现，运行验证，核对预期
   - 不自行添加规格之外的功能；验证不通过 → 停
3. **Commit**（按计划指示）

**该 Task 的所有 Step 完成后，必须立即执行以下闭环操作，完成后方可开始下一个 Task：**

4. **验证** — 运行该 Task 的验证命令，确认通过
5. **勾选** — 将该 Task 的所有 Step checkbox 从 `- [ ]` 改为 `- [x]`（若为拆分 Task，在 tasks/ 文件中勾选；若为内联 Task，在 exec-plan.md 中勾选）
6. **更新 feature-list.json** — 将对应 feature 的 `"passes"` 设为 `true`
7. **更新 memory.md** — 记录该 Task 产生的文件路径、关键决策
8. **更新 progress.txt** — 将该 Task 标记为 `[DONE]`

**以上 5 步（验证→勾选→feature-list→memory→progress）全部完成前，禁止开始下一个 Task。禁止积攒多个 Task 后批量修改这些文件。**

### 阶段 3：完成后归档

所有 Task 完成且验证通过后：

```bash
python scripts/plan-complete.py '<计划名称>'
```

---

## 不偏离原则

> **偏离计划的第一步就是走向失败的开始。**

计划是执行者唯一的行为指南。任何时候想偏离：

| 情况 | 正确做法 | 错误做法 |
|------|---------|---------|
| 计划步骤有歧义 | **停+问**用户澄清 | 猜一个解释 |
| 发现计划遗漏了边界情况 | **停+问**是否更新计划 | 自行补充 |
| 想要修改计划的接口/行为定义 | **停+问**是否更新计划 | 擅自改规格 |
| 实现方式（HOW）有更好选择 | **可以做**——只要不改变规格（WHAT） | 改了接口签名却不停止 |
| 验证失败 | **停+问**是计划有误还是环境问题 | 跳过验证继续 |
| 测试跑不过 | **停**——计划可能有误 | 改测试而非改代码 |

**禁止：**
- ❌ "我有个更好的做法……"（改变接口/行为的 → 不是来改规格的；改变实现细节的 → 可以做）
- ❌ "这一步应该也处理一下 X……"（不在规格里就不要做）
- ❌ "验证失败了但应该没关系……"（有关系——停下来）
- ❌ "这个文件路径不对，我猜应该是……"（停+问，不要猜）
- ❌ "这几个 Task 都很简单，一起做完再统一更新进度……"（每个 Task 必须独立闭环，禁止批量处理）

详见 `docs/deviation-protocol.md`。

---

## Subagent 模式（推荐，需平台支持）

当平台支持 subagent 时，使用此模式获得最高质量：

### 工作流

```
读计划 → 提取全部 Task → 创建 TodoWrite
  │
  └─→ 对每个 Task:
       1. Dispatch implementer subagent（./subagent/implementer-prompt.md）
       2. Implementer 实现→测试→commit→自审
       3. Dispatch spec reviewer subagent（./subagent/spec-reviewer-prompt.md）
       4. 不通过？→ Implementer 修复 → 重审
       5. Dispatch code quality reviewer（./subagent/code-quality-reviewer-prompt.md）
       6. 不通过？→ Implementer 修复 → 重审
       7. 标记 Task 完成
```

### 实现者状态处理

Implementer subagent 返回四种状态：

| 状态 | 处理方式 |
|------|---------|
| **DONE** | 进入 spec 审查 |
| **DONE_WITH_CONCERNS** | 阅读 concerns → 如果影响正确性则修复 → 否则记录并进入审查 |
| **NEEDS_CONTEXT** | 提供缺失上下文 → 重新 dispatch |
| **BLOCKED** | 评估：上下文不足？→ 补充后重试；任务太大？→ 拆分；计划有误？→ 升级给用户 |

**不要**忽略 escalation。不要用同一个模型无变化重试。

### 模型选择

- **机械任务**（1-2 文件，明确 spec）→ 快速廉价模型
- **集成任务**（多文件协调）→ 标准模型
- **架构/设计/审查** → 最强模型

### 优势

| 维度 | Subagent 模式 | Inline 模式 |
|------|:---:|:---:|
| 上下文隔离 | ✅ 每个 Task 独立上下文 | ❌ 累计污染 |
| 双重审查 | ✅ Spec + Code Quality | ❌ 无 |
| 速度 | ✅ 可部分并行 | 串行 |
| 质量 | ✅ TDD + 两轮修复循环 | 依赖执行者自律 |

---

## 进度追踪

执行中维护以下文件：

| 文件 | 内容 | 更新时机 |
|------|------|---------|
| `progress.txt` | 步骤状态（IN_PROGRESS/DONE/BLOCKED） | 每个 Task 闭环时立即更新 |
| `memory.md` | 文件产出、关键决策、配置 | 每个 Task 闭环时立即更新 |
| `feature-list.json` | 功能点 passes 状态 | 每个 Task 闭环时立即更新 |

### progress.txt 示例

```markdown
# Progress: 订单模块缓存层

状态: IN_PROGRESS
最后更新: 2026-05-15

步骤进度:
- [x] Task 1 — Redis 连接管理 [DONE]
- [ ] Task 2 — 缓存查询接口
- [ ] Task 3 — 缓存失效策略
- [BLOCKED] Task 4 — 性能测试 — 等待 Redis 实例就绪

阻塞项: Redis 测试实例预计明天就绪
```

---

## 停止条件

**以下情况立即停止，不要继续：**

1. 计划有缺口无法开始 → 列出问题
2. 验证反复失败 → 计划可能有误
3. 遇到阻塞（缺少依赖、权限不足）→ 标记 BLOCKED + 原因
4. 发现偏离计划的冲动 → 停，问用户
5. 不确定某步的含义 → 停，问用户

**不要强行推进。** 每次强行推进都会累积技术债务。

---

## 会话启动协议

```bash
# 1. 查看活跃计划
python scripts/plan-status.py

# 2. 读取 memory.md 恢复上下文
# 3. 从上次中断处继续
```

---

## 护栏规则

1. **不偏离原则** — 严格照计划执行，偏差时停+问。
   *为什么：* 计划是执行者唯一的真实来源。擅自偏离意味着执行者和制定者各自有不同的"真理"。

2. **零猜测** — 遇到模糊指令，停+问，不猜。
   *为什么：* 猜错的返工成本远超问一句的时间。

3. **验证不跳过** — 计划的验证命令必须运行并通过。
   *为什么：* 跳过验证 = 放弃质量门。累积的未验证步骤会导致后期大规模返工。

4. **进度实时更新** — 每个 Task 闭环时立即更新 progress.txt、memory.md 和 feature-list.json。
   *为什么：* 跨会话恢复时，进度是唯一的路标。延迟更新会导致状态不一致。

5. **成功沉默** — 验证通过不输出；失败才输出含修复指令。
   *为什么：* 噪声淹没信号。

6. **逐 Task 闭环** — 每个 Task 完成后立即：验证 → 勾选 checkbox → 更新 feature-list.json → 更新 memory.md → 更新 progress.txt。禁止积攒多个 Task 后批量处理。
   *为什么：* 批量处理导致进度文件与实际状态不符、feature-list 滞后于实际完成情况、跨会话恢复时状态混乱。Task 完成和记录之间零延迟。

---

## 关键文件索引

| 文件 | 用途 | 何时加载 |
|------|------|---------|
| `SKILL.md` | 入口文档 | 触发 executing-plans 时 |
| `docs/workflow.md` | 完整执行流程 | 需要理解全流程 |
| `docs/deviation-protocol.md` | 偏离处理细则 | 想偏离计划时 |
| `docs/memory-guide.md` | Memory 系统指南 | 跨会话恢复 |
| `docs/managing-plans.md` | 管理计划 | 查看/修改/放弃 |
| `docs/script-reference.md` | 脚本参数速查 | 精确调用脚本 |
| `subagent/implementer-prompt.md` | 实现者 prompt | Subagent 模式 |
| `subagent/spec-reviewer-prompt.md` | Spec 审查 prompt | Subagent 模式 |
| `subagent/code-quality-reviewer-prompt.md` | 代码质量审查 prompt | Subagent 模式 |

---

## 场景示例

**场景：执行"订单模块缓存层"计划**

```
[Announce] I'm using the executing-plans skill to implement this plan.

[Step 1: 加载计划]
  → 读取 docs/exec-plans/active/订单模块缓存层/exec-plan.md
  → 批判性审阅：Task 2 的 Redis 端口写的是 6379，但配置文件用的是 6380？
  → 停+问用户：「计划中 Redis 端口是 6379，但 config 显示 6380。用哪个？」

[用户确认：用 6380，更新计划]

[Step 2: 执行 Task 1 — Redis 连接管理]
  → Step 1.1: 写 redis_connection_test.py（测试代码照计划写）
  → Step 1.2: pytest → FAIL (expected) ✅
  → Step 1.3: 按规格实现 RedisClient 类（读接口契约 + 行为描述 → 自主实现）
  → Step 1.4: pytest → PASS ✅
  → Step 1.5: git commit ✅
  → [闭环] 勾选 Task 1 所有 Step checkbox
  → [闭环] feature-list.json: F1.passes = true
  → [闭环] memory.md: 记录 RedisClient 类
  → [闭环] progress.txt: Task 1 [DONE]
  → ⬆️ 闭环完成，方可开始 Task 2

[Step 3: 执行 Task 2]
  → Task 2 标记为 "→ 拆分"，按链接读取 tasks/task-02-cache-query.md
  → Step 2.1: 写 cache_query_test.py
  → Step 2.2: pytest → FAIL (expected) ✅
  → Step 2.3: 按规格实现 get_cached_query()（签名 + 行为 + 约束 → 自主编码）
  → Step 2.4: pytest → PASS ✅
  → Step 2.5: git commit ✅
  → [闭环] 在 tasks/task-02-cache-query.md 中勾选所有 Step checkbox
  → [闭环] feature-list.json: F2.passes = true
  → [闭环] memory.md: 记录 get_cached_query 函数
  → [闭环] progress.txt: Task 2 [DONE]
  → ⬆️ 闭环完成，方可开始 Task 3

[Step 4: 执行 Task 3]
  → ... (按 Task 1 相同模式：执行 → 闭环 → 下一个)

[全部完成]
  → plan-complete.py '订单模块缓存层'
  → 计划归档到 completed/
```

---

## 平台支持

| 操作系统 | 运行方式 | 依赖 |
|---------|---------|------|
| Linux/macOS | `python scripts/plan-xxx.py` | Python 3.8+ |
| Windows | `python scripts\plan-xxx.py` | Python 3.8+ |

Subagent 模式需平台支持（Claude Code / Codex / pi 均可）。

所有脚本使用 Python 标准库。
