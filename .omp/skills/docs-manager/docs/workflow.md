# Docs Manager 工作流

## 添加新学习计划

1. 在 `docs/learning-plans/active/<plan-name>/` 创建计划目录
2. 运行 `python scripts/update-index.py learning-plans`

## 归档学习计划

1. 确认 plan 目录下所有内容完整
2. 运行 `python scripts/archive-plan.py <plan-name>`
3. 脚本自动更新索引

## 添加知识笔记

1. 在 `docs/knowledge-notes/<category>/` 下创建 .md 文件
2. 运行 `python scripts/update-index.py knowledge-notes`

## 添加深度探索

1. 在 `docs/deep-dives/` 下创建 .md 文件
2. 运行 `python scripts/update-index.py deep-dives`
