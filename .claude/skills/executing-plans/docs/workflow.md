# Workflow — 执行计划全流程（executing-plans）

> 从加载计划到完成归档的完整执行流程。

---

## 总览

```
加载计划 → 批判性审阅 → 逐 Task 执行 → 每个 Task 闭环(验证→勾选→feature-list→memory→progress) → 全部完成 → 归档(plan-complete)
```

---

## 阶段 1：加载与审阅

### 启动检查

```bash
python scripts/plan-status.py
```

### 加载计划

读取 `docs/exec-plans/active/<name>/exec-plan.md`

### 批判性审阅

执行者**必须**带着批判眼光审阅计划：

- 所有文件路径存在？
- 所有命令在当前环境可执行？
- 有模糊的步骤吗？
- 缺少任何依赖说明？

**发现问题 → 停+问用户。不要猜。**

---

## 阶段 2：逐 Task 执行

### 对每个 Task：

1. **确定 Task 位置** — 内联在 exec-plan.md 或拆分到 tasks/task-NN-xxx.md
2. **读取 Task 完整内容** — 所有 Step + 代码 + 验证命令
3. **逐 Step 执行**：
   - **配置文件/脚本** → 严格按照计划中的代码写，不"优化"
   - **应用代码** → 读取规格（接口契约 + 行为描述 + 约束），自主实现，不超出规格范围
   - 运行验证命令——核对预期输出
   - 验证不通过 → **停**
4. **Commit**（按计划指示）

### 每个 Task 闭环（必须立即执行，禁止积攒）

**Step 全部完成并通过验证后，必须立即按顺序执行以下 5 步，完成后方可开始下一个 Task：**

1. **验证** — 运行该 Task 的最终验证命令，确认通过
2. **勾选 checkbox** — 将该 Task 的所有 Step 从 `- [ ]` 改为 `- [x]`（内联 Task 在 exec-plan.md 中改，拆分 Task 在 tasks/ 文件中改）
3. **更新 feature-list.json** — 将对应 feature 的 `"passes"` 设为 `true`
4. **更新 memory.md** — 记录该 Task 产生的文件、关键决策
5. **更新 progress.txt** — 将该 Task 标记为 `[DONE]`

> **禁止：** 连续执行多个 Task 后再批量更新以上文件。每个 Task 必须独立闭环。

### 进度更新

```markdown
# progress.txt
- [x] Task 1 — Redis 连接管理 [DONE]
- [ ] Task 2 — 缓存查询接口
- [BLOCKED] Task 3 — 需要 Redis 6.0+
```

```markdown
# memory.md（关键工件）
| `src/cache/redis_client.py` | 新增 | Task 1 | RedisClient 类 |
```

---

## Subagent 模式（推荐，若平台支持）

当平台支持时，对每个 Task：

```
Dispatch implementer → 实现+测试+自审
    ↓
Dispatch spec reviewer → 检查 spec 合规
    ↓ (不通过 → implementer 修复 → 重审)
Dispatch code quality reviewer → 检查代码质量
    ↓ (不通过 → implementer 修复 → 重审)
标记 Task 完成
```

---

## 阶段 3：完成归档

所有 Task 完成且验证通过后：

```bash
python scripts/plan-complete.py '<计划名称>'
```

计划移动到 `docs/exec-plans/completed/`，更新 PLAN_COMPLETED.md。

---

## 偏离处理

任何时候想偏离计划 → 见 `docs/deviation-protocol.md`。

**核心规则：停+问，不猜。**

---

## 跨会话恢复

1. `python scripts/plan-status.py`
2. 读取 `memory.md`
3. 读取 `progress.txt`
4. 从上次中断处继续

> 详见 `docs/memory-guide.md`。
