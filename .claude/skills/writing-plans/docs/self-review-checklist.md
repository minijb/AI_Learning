# Self-Review Checklist

> 计划写完后，逐项检查。发现问题直接修复——不需要重审。

---

## 1. Spec Coverage（需求覆盖）

对照原始需求，逐个过：

- [ ] 每个需求/用户故事都能指到一个 Task？
- [ ] 有没有需求被遗漏？
- [ ] 有没有 Task 实现了需求之外的东西？→ 删除

---

## 2. Placeholder Scan（占位符扫描）

搜索以下模式——**一个都不能有**：

- [ ] `TBD`
- [ ] `TODO`
- [ ] `FIXME`
- [ ] `implement later`
- [ ] `fill in details`
- [ ] `add appropriate error handling`
- [ ] `handle edge cases`（除非列出具体 case 和处理方式）
- [ ] `write tests for the above`
- [ ] `similar to Task N`（应重复完整代码）

> `plan-validate` 也会自动执行此检查。但人工预审更快。

---

## 3. Type Consistency（类型一致性）

- [ ] Task 3 引用的函数名和 Task 1 定义的完全一致？
- [ ] 方法签名、属性名在整个计划中前后一致？
- [ ] `clearLayers()` ≠ `clearFullLayers()` → 必须统一

---

## 4. Path Precision（路径精确性）

- [ ] 所有 `Files:` 中的路径是项目内的真实路径？
- [ ] 不是占位符（如 `src/module/file.py` 应写具体模块名）
- [ ] 行号引用（`:123-145`）正确？

---

## 5. Verifiability（可验证性）

- [ ] 每个 Step 都有 `验证：` 字段？
- [ ] 验证命令是精确可执行的（含 flag、路径、预期输出）？
- [ ] 没有模糊验证如"确认功能正常"？

---

## 6. Executability（可执行性）

> 假想：你是一个没见过这个项目的工程师，只看这份计划。你能根据规格写出正确实现吗？

- [ ] 每个应用代码 Step 提供了：接口契约（签名/props）、行为描述、关键约束？
- [ ] 每个配置文件 Step 提供了完整内容？
- [ ] 依赖引入（import）明确？
- [ ] 配置/环境变量有说明？

---

**发现问题？→ 直接修，不拖延。**

---

## 7. Task 拆分合理性

- [ ] 复杂 Task（>5 步 / >50 行代码 / 跨 3+ 文件）已拆分到 tasks/ 目录？
- [ ] 拆分出的 Task 文件使用 task-template.md 模板格式？
- [ ] exec-plan.md 中对应的 Task 节包含指向 tasks/ 的引用链接？
- [ ] 简单 Task（≤5 步）保持内联，未过度拆分？
