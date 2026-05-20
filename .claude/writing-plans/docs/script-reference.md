# Script Reference — writing-plans

> 本 skill 拥有以下 CLI 脚本。所有脚本使用 Python 3，跨平台。

---

## plan-new.py — 创建新计划

```bash
python scripts/plan-new.py --quick '名称'              # 轻量计划
python scripts/plan-new.py --full '名称'               # 完整计划
python scripts/plan-new.py --full '名称' --summary '摘要'  # 含摘要
python scripts/plan-new.py --full '名称' --depends '依赖名' # 含依赖
```

---

## plan-validate.py — 验证计划

```bash
python scripts/plan-validate.py docs/exec-plans/active/<名称>
python scripts/plan-validate.py docs/exec-plans/active/<名称>.md
```

**验证内容：**
- 必填节是否存在
- JSON schema 是否正确
- `passes` 初始值是否为 `false`
- **零占位符检查**：拒绝 TBD/TODO/implement later 等

---

## plan-search.py — 搜索已有计划

```bash
python scripts/plan-search.py "<关键词>"
python scripts/plan-search.py --all
```

---

## 平台支持

| 操作系统 | 运行方式 | 依赖 |
|---------|---------|------|
| Linux/macOS | `python scripts/plan-xxx.py` | Python 3.8+ |
| Windows | `python scripts\plan-xxx.py` | Python 3.8+ |
