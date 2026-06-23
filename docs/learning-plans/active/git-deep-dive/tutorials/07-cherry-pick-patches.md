---
title: Git 进阶 - Cherry-pick 与补丁
description: 学习如何把单个或多个提交从一条分支复制到另一条分支，以及通过 format-patch / am / apply 在邮件工作流和离线场景中传递改动。
updated: 2026-06-23
tags: [git, version-control, cherry-pick, patch, backport, email-workflow]
---

# Cherry-pick 与补丁

> 所属计划: [[git-deep-dive|Git 进阶——从日常使用到底层原理]]
> 预计耗时: 45min
> 前置知识: [[04-branch-merge-deep|分支与合并深入]]

---

## 1. 概念讲解

### 为什么需要这个？

想象你正在维护两个版本线：`main` 分支上有最新功能，而 `release/v1.2` 分支仍在给老客户提供稳定版本。突然，一位同事在 `main` 上修复了一个关键安全漏洞，你需要把这个修复**单独**拿到 `release/v1.2` 上。

如果你直接 `git merge main`，会把 `main` 上所有新功能一起合并进去，风险太大。你只想把那一个 bugfix 提交"搬"过来——这就是 `git cherry-pick` 的典型场景。

另一个常见场景是：你给某个开源项目发了邮件补丁（patch），或者在离线环境（如内网、没有共享仓库的 CI）里传递改动。这时候你需要 `git format-patch` 生成 `.patch` 文件，再用 `git am` 或 `git apply` 应用。

### 核心思想

`git cherry-pick <commit>` 的核心是：**复制一次提交引入的改动，以当前分支为基础重新做一次提交**。原提交和 cherry-pick 出来的新提交内容相同（diff 相同），但它们的 commit hash 不同，因为父提交不同、提交时间不同。

可以把提交想象成 diff 补丁 + 元信息（作者、提交信息、父提交 hash）。cherry-pick 就是把这个"补丁"揭下来，贴到当前 `HEAD` 上，然后生成一张新的"快照照片"。

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e1f5e1', 'primaryTextColor': '#1a1a1a', 'primaryBorderColor': '#4caf50', 'lineColor': '#666666'}}}%%
gitGraph
    commit id: "a1"
    branch feature
    checkout feature
    commit id: "f1"
    commit id: "f2 (bugfix)"
    checkout main
    cherry-pick id: "f2" tag: "c1 (new hash)"
    commit id: "a2"
```

上图中，`f2` 是 feature 分支上的 bugfix 提交。把它 cherry-pick 到 `main` 后，生成了 `c1`。`c1` 与 `f2` 的**改动内容**相同，但 hash 不同。

### cherry-pick vs merge vs rebase

| 操作 | 作用范围 | 是否生成新提交 | 典型场景 |
|------|----------|----------------|----------|
| `git merge` | 合并整条分支的所有提交 | 会（三方合并或 fast-forward） | 把 feature 分支完整合进 main |
| `git rebase` | 把当前分支的提交逐个接到新基点上 | 会（每个提交 hash 都变） | 整理 feature 分支历史使其线性 |
| `git cherry-pick` | 只复制一个或几个指定提交 | 每个被 pick 的提交都会生成新提交 | 把某个 bugfix 搬到 release 分支 |

简单说：merge 和 rebase 是"全量搬运"，cherry-pick 是"选择性零售"。

### 补丁工作流：format-patch / am / apply

在 Linux 内核、Git 自身以及一些邮件列表驱动的开源社区中，常见的协作方式不是 pull request，而是**邮件补丁**。

- `git format-patch <range>`：把一段历史里的每个提交转换成一个 `.patch` 文件（含提交信息、作者、diff）。
- `git am <patch>`："apply mailbox"，把 patch 文件应用到当前分支并**生成新的提交**，保留原作者和提交信息。
- `git apply <patch>`：只把 patch 的 diff 应用到**工作区**，不创建提交，也不保留作者信息。

| 命令 | 是否创建提交 | 是否保留提交信息/作者 | 适用场景 |
|------|--------------|------------------------|----------|
| `git am` | 是 | 是 | 邮件工作流、离线迁移提交 |
| `git apply` | 否 | 否 | 只想看效果、需要手动调整后再提交 |

---

## 2. 代码示例

### 环境要求

- Git ≥ 2.40（建议使用 `git switch`/`git restore` 现代命令）。
- 本示例在 bash/zsh 中运行；Windows 用户建议用 Git Bash，并注意 `core.autocrlf` 可能导致的行尾差异。
- 以下命令会创建一个临时仓库 `git-playground`，完成示例后可删除。

### 示例：cherry-pick bugfix 到 release 分支

**运行方式:**

```bash
# 1. 创建示例仓库

mkdir git-playground && cd git-playground
git init -b main

# 2. 在 main 上创建基础提交
echo "v1.0" > version.txt
git add version.txt
git commit -m "Initial release v1.0"

# 3. 基于 main 创建 release 分支
git switch -c release/v1.2

# 4. 回到 main 继续开发
git switch main
echo "feature auth" > auth.txt
git add auth.txt
git commit -m "Add auth feature"

# 5. 发现并修复一个安全漏洞（在 main 上做 bugfix）
echo "fixed: sanitize input" > fix.txt
git add fix.txt
git commit -m "fix: sanitize user input to prevent injection"

# 6. 查看当前历史
git log --oneline --graph --all
```

**预期输出:**

```text
* 9f3e2a1 (HEAD -> main) fix: sanitize user input to prevent injection
* 7b4c8d2 Add auth feature
| * 1a2b3c4 (release/v1.2) Initial release v1.0
|/
* 0d0e1f2 Initial release v1.0
```

现在要把 `main` 上的 bugfix 提交 cherry-pick 到 `release/v1.2`，但**不要把 `Add auth feature` 带过去**。

```bash
# 7. 切换到 release 分支
git switch release/v1.2

# 8. cherry-pick 那个 bugfix 提交（用实际 hash 替换 9f3e2a1）
git cherry-pick 9f3e2a1

# 9. 查看结果
git log --oneline --graph --all
```

**预期输出:**

```text
* 8c7d6e5 (HEAD -> release/v1.2) fix: sanitize user input to prevent injection
* 1a2b3c4 Initial release v1.0
| * 9f3e2a1 (main) fix: sanitize user input to prevent injection
| * 7b4c8d2 (main) Add auth feature
|/
* 0d0e1f2 Initial release v1.0
```

注意：两个分支上的 `fix: sanitize user input to prevent injection` 提交**内容相同，但 hash 不同**（`9f3e2a1` vs `8c7d6e5`）。这就是 cherry-pick 的核心特征。

### 示例：多提交 cherry-pick

如果一次需要搬多个提交，可以列出多个 hash，或用范围语法：

```bash
# 方式 A：列出多个提交
git cherry-pick <hash1> <hash2> <hash3>

# 方式 B：范围语法 A..B，表示 B 可达但 A 不可达的所有提交
# 注意：这里不包含 A 本身
git cherry-pick <hashA>..<hashB>
```

> [!important]
> `A..B` 在 cherry-pick 中表示"从 A 之后到 B 之间的提交"，不包含 A。如果你想包含 A，需要写成 `A^..B`。

### 示例：生成 patch 并用 am 应用

```bash
# 回到刚才的 git-playground 仓库

# 1. 在 main 上再产生几个提交
git switch main
echo "feature: dark mode" > darkmode.txt
git add darkmode.txt
git commit -m "feat: add dark mode"

echo "docs: update README" > readme.txt
git add readme.txt
git commit -m "docs: update README"

# 2. 查看最后两个提交的 hash
git log --oneline -2
```

**预期输出:**

```text
* a1b2c3d docs: update README
* e4f5g6h feat: add dark mode
```

```bash
# 3. 把这两个提交导出为 patch 文件（保存到 ./patches）
mkdir -p ./patches
git format-patch e4f5g6h^..a1b2c3d -o ./patches

# 4. 查看生成的 patch 文件
ls ./patches

```

**预期输出:**

```text
0001-feat-add-dark-mode.patch
0002-docs-update-README.patch
```

```bash
# 5. 切换到 release/v1.2 并创建测试分支，再应用 patch
git switch release/v1.2
git switch -c patch-test
git am ./patches/*.patch

# 6. 查看历史，原作者和提交信息都被保留
git log --oneline -2
```

**预期输出:**

```text
* x9y8z7w docs: update README
* p1q2r3s feat: add dark mode
```

### 示例：用 git apply 只改工作区

```bash
# 用 apply 预检 patch 是否能干净应用（不真正改动）
git apply --check ./patches/0001-feat-add-dark-mode.patch

# 如果没有输出，说明可以干净应用
# 真正应用到工作区（不创建提交）
git apply ./patches/0001-feat-add-dark-mode.patch

# 查看工作区变化
git status
git diff --staged
```

### 处理 cherry-pick / am 冲突

当 cherry-pick 或 `git am` 遇到冲突时，Git 会暂停并提示你解决。流程与 merge 类似：

```bash
# 解决冲突后，继续 cherry-pick
git add <resolved-files>
git cherry-pick --continue

# 或者放弃本次 cherry-pick
git cherry-pick --abort

# 对于 git am 冲突
git add <resolved-files>
git am --continue

# 或者跳过当前 patch
git am --skip

# 放弃整个 am 过程
git am --abort
```

### 记录来源：`-x` 与 `--signoff`

```bash
# -x 会在提交信息末尾追加 "(cherry picked from commit <hash>)"
git cherry-pick -x <hash>

# --signoff 会在提交信息末尾追加 "Signed-off-by: 你的名字 <邮箱>"
git cherry-pick --signoff <hash>
```

`-x` 特别适用于 backport 工作流，方便后人追溯这个修复最初来自哪个提交。

---

## 3. 练习

### 练习 1: 单次 cherry-pick 并解释新 hash

在 `git-playground` 仓库中（或新建一个练习仓库）：

1. 创建 `main` 分支，提交一个基础文件。
2. 创建 `feature` 分支，做两次提交：一次是"新增功能"，一次是"修复 typo"。
3. 切换回 `main`，只 cherry-pick "修复 typo" 这个提交。
4. 用 `git log --oneline --graph --all` 观察历史，解释为什么同一个改动会生成两个不同的 commit hash。

### 练习 2: 用 format-patch + am 离线迁移提交

1. 在分支 A 上做两个提交。
2. 用 `git format-patch` 把它们导出为 `.patch` 文件到一个临时目录。
3. 删除原仓库或切换到全新的分支 B。
4. 用 `git am` 应用这些 patch，验证提交信息和作者都被保留。
5. 用 `git log --format=fuller` 查看作者（Author）和提交者（Commit）的区别。

### 练习 3: git apply --check 预检 patch（可选）

1. 基于练习 2 生成的 patch 文件，在不改动工作区的情况下，用 `git apply --check` 预检它是否能干净应用。
2. 手动制造一个冲突场景（例如先修改目标分支上 patch 要改的那行），再次运行 `git apply --check`，观察 Git 如何报告失败。
3. 用 `git apply --reject` 应用 patch，让 Git 把无法应用的 hunk 保存为 `.rej` 文件，然后手动合并。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 参考答案不是唯一解——如果你的实现通过/达到要求就是正确的。
> 
> ```bash
> # 创建练习仓库
> mkdir cherry-pick-ex1 && cd cherry-pick-ex1
> git init -b main

> # 基础提交（故意留一个 typo）
> printf "base\nhello wrold\n" > app.txt
> git add app.txt
> git commit -m "Initial commit with typo"
> 
> # 在 main 上做两个无关提交，使 main HEAD 与 feature 的父提交不同
> echo "unrelated" > other.txt
> git add other.txt
> git commit -m "Add unrelated file"
> 
> echo "docs" > docs.txt
> git add docs.txt
> git commit -m "Update docs"
> 
> # 创建 feature 分支，只修复 typo（父提交是 "Add unrelated file"）
> git switch -c feature HEAD~1
> printf "base\nhello world\n" > app.txt
> git commit -am "Fix typo in greeting"
> 
> # 回到 main，cherry-pick 修复 typo（父提交是 "Update docs"，因此 hash 不同）
> git switch main
> # 用实际 hash 替换下面的 <hash>
> git cherry-pick <hash>
> 
> # 查看历史
> git log --oneline --graph --all
> ```
> 
> 新 hash 的原因：cherry-pick 会复制原提交的 diff，但新提交的父提交是当前分支的 `HEAD`，且提交时间不同。由于 Git 的 commit hash 是对整个提交对象（含父提交、作者、提交者、时间、提交信息、tree）做哈希，父提交和时间变了，hash 必然改变。

> [!tip]- 练习 2 参考答案
> 参考答案不是唯一解——如果你的实现通过/达到要求就是正确的。
> 
> ```bash
> # 创建练习仓库
> mkdir format-patch-ex2 && cd format-patch-ex2
> git init -b main
> git config user.email "you@example.com"
> git config user.name "Your Name"
> 
> # 基础提交中先创建目标文件
> printf "line 1\n" > a.txt
> git add a.txt
> git commit -m "Base commit"
> 
> # 在分支 A 上做两个提交，都修改 a.txt
> git switch -c branch-a
> printf "line 1\nline A\n" > a.txt
> git commit -am "Add line A"
> 
> printf "line 1\nline A\nline B\n" > a.txt
> git commit -am "Add line B"
> 
> # 导出 patch（main..branch-a 表示 branch-a 上 main 没有的提交）
> mkdir -p ./patches
> git format-patch main..branch-a -o ./patches
> 
> # 切换到新分支并应用（同一仓库即可，无需真正删除原仓库）
> git switch main
> git switch -c branch-b
> git am ./patches/*.patch
> 
> # 查看提交者和作者
> git log --format=fuller -2
> ```
> 
> 如果 `git am` 报错，通常是 patch 中的邮箱格式或行尾问题。检查 `git config user.email` 是否已设置。
> 
> [!tip]- 练习 3 参考答案（可选）
> 参考答案不是唯一解——如果你的实现通过/达到要求就是正确的。
> 
> ```bash
> # 基于练习 2 的 patch 文件做测试
> # 先用干净状态预检（假设当前在 branch-b，a.txt 已含 line A，可另开新分支）
> git switch main
> git switch -c apply-test
> 
> # 预检 patch 是否能干净应用（此时 a.txt 只有 "line 1"，应无输出）
> git apply --check ./patches/0001-Add-line-A.patch
> 
> # 制造冲突：先修改 a.txt
> printf "line 1\nline X\n" > a.txt
> git commit -am "Add line X"
> 
> # 再次预检，应该报错
> git apply --check ./patches/0001-Add-line-A.patch
> 
> # 用 --reject 应用，冲突部分保存为 .rej
> git apply --reject ./patches/0001-Add-line-A.patch
> 
> # 查看 .rej 文件内容
> cat a.txt.rej
> 
> # 手动合并：把期望的 "line A" 也加入 a.txt
> printf "line 1\nline A\nline X\n" > a.txt
> rm *.rej
> git add .
> git commit -m "Apply Add line A with manual resolution"
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [Git 官方文档：git-cherry-pick](https://git-scm.com/docs/git-cherry-pick)
- [Git 官方文档：git-format-patch](https://git-scm.com/docs/git-format-patch)
- [Git 官方文档：git-am](https://git-scm.com/docs/git-am)
- [Git 官方文档：git-apply](https://git-scm.com/docs/git-apply)
- [Pro Git：使用 Git 进行补丁提交（Email Workflow）](https://git-scm.com/book/zh/v2/Git-%E5%9C%A8%E5%85%B6%E4%BB%96%E7%8E%AF%E5%A2%83%E4%B8%AD%E7%9A%84%E4%BD%BF%E7%94%A8-%E5%85%AC%E5%BC%80%E9%A1%B9%E7%9B%AE%E4%B8%8E%E7%A7%81%E4%BA%BA%E9%A1%B9%E7%9B%AE)
- [Linux Kernel: Submitting Patches](https://www.kernel.org/doc/html/latest/process/submitting-patches.html)

---

## 常见陷阱

- **cherry-pick 后产生重复提交**: 当你把 `feature` 分支上的某个提交 cherry-pick 到 `main` 后，如果将来再执行 `git merge feature`，那个提交引入的改动会**再次出现**（因为 cherry-pick 生成了新提交，Git 不会认为它是同一个提交）。正确做法：要么 cherry-pick 后不再 merge 原分支，要么在 cherry-pick 时用 `-x` 标记来源以便人工识别。

- **`git am` 失败后不知如何处理**: `git am` 遇到冲突会暂停，此时应解决冲突、`git add` 后执行 `git am --continue`；如果想跳过当前 patch 用 `git am --skip`；想完全放弃用 `git am --abort`。不要直接用 `git commit`，那会破坏 am 的状态机。

- **混淆 `git apply` 与 `git am`**: `git apply` 只修改工作区，不创建提交，也不保留原作者信息；`git am` 会创建提交并保留 patch 中的作者和提交信息。如果你只是想临时看看 patch 效果，用 `apply`；如果你想把别人的邮件补丁完整纳入仓库历史，用 `am`。

- **范围语法写错导致漏提交**: `git cherry-pick A..B` 不包含 A。若要包含 A，请写成 `A^..B`。类似地，`git format-patch A..B` 也遵循同样规则。

- **在公共分支上 cherry-pick 已推送提交后强行推送**: cherry-pick 本身不改写历史，但如果你随后 rebase 或修改了公共分支，仍会给协作者带来困扰。公共分支上的操作仍应遵循 rebase 黄金法则（详见 [[05-rebase-core|Rebase 核心技能]]）。
