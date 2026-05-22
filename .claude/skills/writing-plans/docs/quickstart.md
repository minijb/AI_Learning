# Quick Start — 快速上手（writing-plans）

> 第一次写可执行计划？5 分钟创建你的第一个计划。

---

## 1. 判断模式

简单判断：步骤 ≤5 且文件 ≤3 → Quick Plan；否则 → Exec Plan。**不确定时，选 Exec Plan。**

> 完整决策表见 [`workflow.md`](./workflow.md)。

---

## 2. 创建 Quick Plan

适合：小 bug 修复、单文件修改、简单重构。

```bash
python scripts/plan-new.py --quick '修复导航栏样式'
```

填充 `.md` 文件时，**每步都要写验证命令**：

```markdown
- [ ] **Step 1** — 修改 flexbox 属性
  - 验证：`open index.html` in Safari → 导航栏居中显示
```

---

## 3. 创建 Exec Plan

适合：新功能开发、跨模块改动、架构调整。

```bash
python scripts/plan-new.py --full '订单模块缓存层'
```

这会创建 `docs/exec-plans/active/订单模块缓存层/` 目录。

**填充 exec-plan.md 时遵循 TDD 节奏（配置文件写完整内容，应用代码写规格）：**

```markdown
## Task 1: Redis 连接管理

**Files:**
- Create: `src/cache/redis_client.py`
- Test: `tests/cache/test_redis_client.py`

- [ ] **Step 1: 写测试**
  ```python
  def test_connect_to_redis():
      client = RedisClient(host='localhost', port=6379)
      assert client.ping() is True
  ```
  - 验证：`pytest tests/cache/test_redis_client.py::test_connect_to_redis -v` → 预期 FAIL

- [ ] **Step 2: 实现 RedisClient**
  - 文件：`src/cache/redis_client.py`
  - 签名：`class RedisClient(host: str, port: int)`
  - 行为：构造时连接 Redis，`ping()` 返回 `True` 表示连通
  - 关键约束：连接失败抛 `ConnectionError`；支持 context manager 自动关闭
  - 验证：`pytest tests/cache/test_redis_client.py::test_connect_to_redis -v` → 预期 PASS

- [ ] **Step 3: Commit**
  ```bash
  git add tests/cache/ src/cache/
  git commit -m "feat: add Redis client connection"
  ```
```

> 完整模板在 `templates/exec-plan.md`。

---

## 4. Self-Review（计划写完后必做）

1. 搜索 `TBD\|TODO\|implement later\|add error handling` → 全部删除
2. 检查每个 Step 是否有验证命令（`- 验证：` 字段）
3. 检查文件路径是否真实存在（不是占位符）

---

## 5. 验证计划

```bash
python scripts/plan-validate.py docs/exec-plans/active/<计划名称>
```

零占位符检查会自动拒绝含 TBD/TODO 的计划。

---

## 6. 交接给执行

> "计划已保存。使用 `executing-plans` skill 执行。"

---

## 下一步

- 完整创建流程 → [`workflow.md`](./workflow.md)
- 计划系统哲学 → [`planning-principles.md`](./planning-principles.md)
- Script 参数速查 → [`script-reference.md`](./script-reference.md)
- 自审清单 → [`self-review-checklist.md`](./self-review-checklist.md)
