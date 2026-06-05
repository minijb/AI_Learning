---
title: "Docs — AI 程序员自我提升工作区"
updated: 2026-06-05
---

# Docs — AI 程序员自我提升工作区

> docs 系统是工作区的记录系统（Record System）。所有学习产出存储在这里，
> 版本控制，按领域分类索引。

---

## 目录导航

| 目录 | 用途 | 入口 |
|------|------|------|
| `learning-plans/` | 结构化学习计划（一流工件） | [[learning-plans/INDEX]] |
| `knowledge-notes/` | 简略知识笔记，按领域分类 | [[knowledge-notes/INDEX]] |
| `deep-dives/` | 知识点深度探索记录 | [[deep-dives/INDEX]] |

---

## 学习计划生命周期

```text
创建 ──→ 学习中 ──→ 完成 ──→ 归档
         (active/)          (completed/)
```

1. **创建**: 由 `learning-plans` Skill 在 `active/` 下创建计划目录
2. **学习**: 按 `progress.md` 逐节完成，更新进度
3. **完成**: 所有节标记完成
4. **归档**: 由 `docs-manager` Skill 将目录移到 `completed/`

---

## 文件命名规范

- 学习计划目录: 英文 slug，小写 + 连字符（如 `rust-async-programming`）
- 教程文件: `NN-slug.md`（如 `01-ownership-basics.md`）
- 知识笔记: 按类别子目录 + 描述性文件名
- 深度探索: `<topic-slug>.md`

---

## 索引维护

所有 INDEX.md 由 `docs-manager` Skill 的脚本自动生成。
手动编辑 INDEX.md 会被下次脚本运行覆盖。

```bash
# 更新全部索引
python .omp/skills/docs-manager/scripts/update-index.py --all
```

---

## 扩展

如需添加新的文档类型（如学习日记、周报总结），在 `docs/` 下创建新目录，
并更新 `docs-manager` Skill 的脚本增加对应的索引更新逻辑。
