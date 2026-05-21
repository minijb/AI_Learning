# Script Reference — executing-plans

> 本 skill 拥有以下 CLI 脚本。所有脚本使用 Python 3，跨平台。

---

## plan-status.py — 查看活跃计划状态

```bash
python scripts/plan-status.py
```

输出所有活跃计划的类型、状态、完成百分比。

---

## plan-complete.py — 完成归档

```bash
python scripts/plan-complete.py '<计划名称>'
python scripts/plan-complete.py '<计划名称>' --force  # 跳过确认
```

计划移动到 `docs/exec-plans/completed/`，更新 PLAN_COMPLETED.md。

---

## plan-cleanup.py — 清理旧计划

```bash
python scripts/plan-cleanup.py --all --what-if      # 预览
python scripts/plan-cleanup.py --completed --days 30 # 清理 30 天前归档
python scripts/plan-cleanup.py --orphaned            # 清理孤立文件
python scripts/plan-cleanup.py --empty               # 清理空计划
python scripts/plan-cleanup.py --all --force         # 强制清理
```

---

## 平台支持

| 操作系统 | 运行方式 | 依赖 |
|---------|---------|------|
| Linux/macOS | `python scripts/plan-xxx.py` | Python 3.8+ |
| Windows | `python scripts\plan-xxx.py` | Python 3.8+ |
