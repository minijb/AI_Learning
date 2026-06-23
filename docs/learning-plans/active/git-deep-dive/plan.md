---
title: 学习计划 - Git 进阶：从日常使用到底层原理
updated: 2026-06-23
tags: [git, version-control, vcs, devops, workflow]
---

# 学习计划: Git 进阶——从日常使用到底层原理

> 创建日期: 2026-06-23
> 预计总耗时: 13-15 小时
> 目标水平: 中级到高级

---

## 适用人群

你已经能熟练使用 `add` / `commit` / `push` / `pull` / `clone` 完成日常工作，但遇到 rebase、冲突、`reflog`、submodule 等场景就发怵。本计划带你从"会用"走向"真懂"——建立 Git 的心智模型，掌握历史改写与撤销，理解底层对象模型，最终能自信地处理任意 Git 事故。

## 学习目标

完成本计划后，你将能够：

- 用"快照 + DAG"的模型解释 Git 的工作方式，而不是停留在"保存差异"的误解上
- 精细化使用暂存区（`add -p`、`restore --staged`、三种 `reset` 模式）
- 自信地用交互式 rebase 整理历史（squash、reorder、edit、`--onto`）
- 用 `reflog` 找回"丢失"的提交，理解为什么 rebase 在 Git 里是安全操作
- 用 `cherry-pick`、`format-patch`/`am` 做外科手术式的提交迁移
- 解释 blob/tree/commit/tag 四种对象，用 `git cat-file` 等 Plumbing 命令直接观察仓库
- 用 `bisect` 二分定位回归 bug，用 hooks 自动化工作流
- 在 Git Flow / GitHub Flow / Trunk-based 之间做出合理选型
- 熟练配置 `.gitconfig`、别名、条件包含

## 前置要求

- [x] 会使用 `git add`、`git commit`、`git push`、`git pull`、`git clone`
- [x] 理解分支的基本概念（`git branch`、`git checkout`/`git switch`）
- [x] 有一个可用的 Git 环境（本地 `git --version` ≥ 2.30 推荐 2.40+）
- [ ] 如果命令行基础薄弱，建议先完成 [[shell-scripting-bash-zsh-fish|Shell 脚本学习计划]]

## 学习路径

> [!note] 阶段划分
> 全计划分五个阶段。阶段一重构心智模型是后续一切的基础，**必须最先学**；阶段五是综合实战，建议放最后。

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 1 | [[01-git-mental-model\|Git 心智模型：快照而非差异]] | 45min | 基础 | 无 |
| 2 | [[02-staging-area-mastery\|暂存区精通：精细化提交]] | 45min | 基础 | 1 |
| 3 | [[03-diff-log-history\|diff、log 与历史导航]] | 60min | 基础 | 1 |
| 4 | [[04-branch-merge-deep\|分支与合并深入]] | 60min | 基础 | 1 |
| 5 | [[05-rebase-core\|Rebase 核心技能]] | 75min | 进阶 | 3, 4 |
| 6 | [[06-reflog-undo\|Reflog 与撤销的艺术]] | 60min | 进阶 | 5 |
| 7 | [[07-cherry-pick-patches\|Cherry-pick 与补丁]] | 45min | 进阶 | 4 |
| 8 | [[08-stash-worktree\|stash 与 worktree]] | 45min | 进阶 | 2, 4 |
| 9 | [[09-git-object-model\|Git 对象模型：blob、tree、commit]] | 60min | 进阶 | 1 |
| 10 | [[10-refs-dag-internals\|引用与 DAG：分支的真相]] | 45min | 进阶 | 9 |
| 11 | [[11-bisect-regression\|bisect：二分查找回归]] | 30min | 进阶 | 3 |
| 12 | [[12-tags-submodules-sparse\|Tags、子模块与稀疏检出]] | 45min | 进阶 | 10 |
| 13 | [[13-remote-collaboration\|远程协作进阶]] | 60min | 进阶 | 4, 5 |
| 14 | [[14-hooks-automation\|Hooks 与自动化]] | 60min | 进阶 | 无 |
| 15 | [[15-workflows-config\|工作流策略与配置精通]] | 60min | 综合 | 5, 13 |
| 16 | [[16-capstone-rescue-history\|综合实战：拯救混乱的历史]] | 90min | 项目 | 1-12 |

## 里程碑

- [ ] 第一阶段·重构心智（第 `#1`–`#4` 节）: 建立 Git 的快照/DAG 模型，精通暂存区与历史查看，理解分支与合并的底层机制
- [ ] 第二阶段·掌控历史（第 `#5`–`#8` 节）: 掌握 rebase、reflog、cherry-pick、stash/worktree，能自信地改写、撤销、迁移提交
- [ ] 第三阶段·理解底层（第 `#9`–`#12` 节）: 读懂 Git 对象模型与引用系统，会用 Plumbing 命令、bisect、submodule
- [ ] 第四阶段·协作与自动化（第 `#13`–`#15` 节）: 精通远程协作、`--force-with-lease`、hooks 自动化、工作流选型与配置
- [ ] 最终项目（第 `#16` 节）: 在一个刻意制造混乱的仓库里，综合运用 rebase/reflog/cherry-pick/bisect 完成历史拯救任务

## 学习建议

> [!tip] 实践优先
> 每节都配有可在本地即时运行的练习。**强烈建议建一个专门的练习仓库**：
>
> ```bash
> mkdir git-playground && cd git-playground && git init
> ```
>
> 在练习仓库里随意实验，不用担心搞坏——这正是本计划要教你的：Git 里几乎一切都能撤销。

> [!warning] 不要在生产仓库练习
> rebase、`reset --hard`、`filter-branch`、`push --force` 等命令在共享分支上可能造成灾难。**所有练习请在练习仓库或个人分支完成**，等阶段四彻底理解 `--force-with-lease` 后再触碰共享历史。
