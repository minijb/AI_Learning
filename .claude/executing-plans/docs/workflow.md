# Workflow — 执行计划全流程（executing-plans）

> 从加载计划到完成归档的完整执行流程。

---

## 总览

```
加载计划 → 批判性审阅 → 逐 Task 执行 → 验证 → 更新进度/memory → 全部完成 → 归档(plan-complete)
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

1. **读取完整 Task**（所有 Step + 代码）
2. **逐 Step 执行**：
   - 严格按照代码写——不"优化"
   - 运行验证命令——核对预期输出
   - 验证不通过 → **停**
3. **Commit**（按计划指示）
4. **更新进度**

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

## 阶段 3：Subagent 模式（推荐，若平台支持）

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

## 阶段 4：完成归档

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
