# Workflow — 写计划全流程（writing-plans）

> 从需求输入到计划交接的完整流程。

---

## 总览

```
需求输入 → 需求澄清 → 查重(plan-search) → 选择模式 → 填充模板 → Self-review → 验证(plan-validate) → 交接给 executing-plans
```

---

## 阶段 1：需求澄清

> **规则：需求不完整，不创建计划。**

模糊指令必须主动提问，直到信息完整。

**常见场景：**

| 模糊 | 提问 |
|------|------|
| "优化订单模块" | 查询性能？重构？缓存？ |
| "加个新功能" | 解决什么用户痛点？ |
| "引入缓存" | Redis？本地？哪些接口？ |

---

## 阶段 2：查重

```bash
python scripts/plan-search.py "<关键词>"
```

检查是否有类似已完成或进行中的计划。

---

## 阶段 3：创建

```bash
# Quick Plan
python scripts/plan-new.py --quick '名称' --summary '一句话摘要'

# Exec Plan
python scripts/plan-new.py --full '名称' --summary '一句话摘要' --depends '依赖计划名'
```

---

## 阶段 4：填充

**核心原则：零占位符。每步都有验证命令。**

### Quick Plan

```markdown
# Quick Plan: 修复导航栏 Safari 样式

## 目标
导航栏在 Safari 14+ 上居中显示

## 验收标准
- [ ] Safari 14 上导航栏水平居中
- [ ] Chrome/Firefox 不受影响

## 步骤
- [ ] **Step 1** — 修改 `nav.css` 第 45 行：`display: flex` → `display: -webkit-flex`
  - 验证：Safari 打开 → 导航栏居中 ✓

## 回滚方案
git checkout nav.css
```

### Exec Plan

遵循 TDD 节奏，每 Task 含完整代码 + 精确命令 + 预期输出。

> 完整格式见 `templates/exec-plan.md` 和 `docs/quickstart.md` 的示例。

---

## 阶段 5：Self-Review

按 `docs/self-review-checklist.md` 逐项检查：
1. Spec 覆盖
2. 占位符扫描（TBD/TODO/implement later → 删除）
3. 类型一致性
4. 路径精确性
5. 可验证性
6. 可执行性

---

## 阶段 6：验证

```bash
python scripts/plan-validate.py docs/exec-plans/active/<计划名称>
```

零占位符检查会自动拒绝 TBD/TODO 等模式。

**验证哲学：成功沉默，失败输出含修复指令。**

---

## 阶段 7：交接

告知用户：

> "计划已保存。使用 `executing-plans` skill 执行。"
