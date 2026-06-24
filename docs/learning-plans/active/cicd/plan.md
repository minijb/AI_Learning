---
title: CI/CD 完整学习计划
created: 2026-06-23
updated: 2026-06-23
tags: [cicd, devops, learning-plan, active]
aliases: [CI/CD 学习路线, 持续集成学习计划]
---

# 学习计划: CI/CD 完整学习

> 创建日期: 2026-06-23
> 预计总耗时: 19-21 小时（含最终项目）
> 目标水平: 进阶 —— 能独立设计并实现端到端的 CI/CD 流水线

---

## 学习目标

完成本计划后，你能够：

- 用准确的语言辨析 **持续集成（CI）**、**持续交付（CD）**、**持续部署（CD）** 三者的边界与关系，并向团队讲清 DevOps 文化的价值。
- 选择合适的分支策略（trunk-based / GitFlow）并落地约定式提交，让 `main` 分支始终可发布。
- 用 **GitHub Actions** 从零写出多阶段流水线：触发、构建、测试、缓存、制品、矩阵、条件、可复用工作流与 composite action。
- 在 CI 中组织测试金字塔，配置并行、覆盖率门槛与失败快策略，把测试产物作为 artifact 归档。
- 用 **Docker** 容器化应用（多阶段构建），把镜像推送到 GHCR/Docker Hub，并设计镜像标签策略。
- 说出 **蓝绿 / 金丝雀 / 滚动** 等部署策略的取舍，用特性开关做灰度与渐进式交付。
- 阅读 **GitLab CI/CD** 的 `.gitlab-ci.yml`，在概念上与 GitHub Actions 双向映射。
- 用语义化版本 + 自动化工具管理发布，把变更日志和 Git tag 串进流水线。
- 把安全"左移"进流水线：SAST、依赖扫描、密钥扫描、镜像扫描、SBOM（DevSecOps 基础）。
- 用 **DORA 四指标** 衡量交付效能，建立部署后的可观测性（日志/指标/链路追踪）。
- 独立完成一个端到端综合项目：PR 触发 CI → 安全扫描 → 构建 Docker → 推镜像 → 部署 → 发布 Release。

> [!note] 学习背景假设
> 你已具备 C# / Lua / TypeScript 编程经验，会用 Git 基础操作和命令行，但对 DevOps / CI/CD 几乎零基础。本计划从概念全景讲起，以 **GitHub Actions** 为主力工具（最易上手、免费额度充足、与 Git 仓库原生集成），辅以 Docker、GitLab CI、DevSecOps 拓宽视野。全程围绕一个示例项目 `quote-api`（TypeScript + Node.js 的极简 HTTP API）展开，确保每节都能动手实践。

---

## 前置要求

- [ ] 会用命令行创建目录、运行命令，有 VS Code 或等效编辑器。
- [ ] 了解 Git 基础：`commit`、`push`、`branch`、`merge`、`pull request`。
- [ ] 有任意一门编程语言的基础（C# / TS / Python 均可），能读懂简单的 JavaScript/TypeScript。
- [ ] 有一个 GitHub 账号（免费即可，本计划的实战都跑在 GitHub Actions 上）。
- [ ] （可选）了解 HTTP API 的基本概念（请求、响应、状态码）。

> [!tip] 没有 Node.js 经验？
> 示例项目用 TypeScript + Node.js，但你**不需要精通 Node**。每节会给出可直接复制的配置和命令。如果你完成了 [[typescript-complete|TypeScript 完整学习计划]]，会更轻松，但这不是硬性要求。

---

## 学习路径

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 1 | [[01-ci-cd-devops-overview\|CI/CD 与 DevOps 全景]] | 60 min | 基础 | 无 |
| 2 | [[02-version-control-branching\|版本控制与分支策略]] | 60 min | 基础 | 1 |
| 3 | [[03-pipeline-core-concepts\|流水线核心概念]] | 60 min | 基础 | 1 |
| 4 | [[04-github-actions-intro\|GitHub Actions 入门]] | 75 min | 基础 | 3 |
| 5 | [[05-secrets-conditions-matrix\|变量、Secrets、条件与矩阵]] | 75 min | 进阶 | 4 |
| 6 | [[06-reusable-composite-actions\|可复用工作流与 Composite Actions]] | 75 min | 进阶 | 5 |
| 7 | [[07-testing-in-ci\|CI 中的测试策略]] | 75 min | 进阶 | 4 |
| 8 | [[08-cache-artifacts-deps\|缓存、制品与依赖管理]] | 60 min | 进阶 | 4 |
| 9 | [[09-docker-containerization\|Docker 与容器化]] | 90 min | 进阶 | 3 |
| 10 | [[10-container-registry\|容器镜像与镜像仓库]] | 60 min | 进阶 | 9 |
| 11 | [[11-deployment-strategies\|部署策略：蓝绿、金丝雀、滚动]] | 75 min | 进阶 | 8 |
| 12 | [[12-progressive-delivery-flags\|渐进式交付与特性开关]] | 60 min | 进阶 | 11 |
| 13 | [[13-gitlab-cicd\|GitLab CI/CD]] | 75 min | 进阶 | 4 |
| 14 | [[14-release-semver\|发布管理与语义化版本]] | 60 min | 工程 | 6 |
| 15 | [[15-devsecops\|DevSecOps：流水线中的安全]] | 75 min | 工程 | 8 |
| 16 | [[16-observability-dora\|可观测性与 DORA 指标]] | 60 min | 工程 | 11 |
| 17 | [[17-capstone-project\|综合项目：端到端流水线]] | 150 min | 项目 | 全部 |

---

## 里程碑

- [ ] **第一阶段 · 建立全景认知**（完成 01-03）
  - 能讲清 CI/CD/CD 三个概念，会选择分支策略，理解流水线的四阶段模型与"流水线即代码"。
- [ ] **第二阶段 · 用 GitHub Actions 跑通 CI**（完成 04-08）
  - 能为真实项目写出多阶段 CI：触发、测试、缓存、制品、矩阵、条件、可复用工作流，让 PR 自动化验证。
- [ ] **第三阶段 · 容器化与部署**（完成 09-12）
  - 能用 Docker 打包应用、推镜像、选择部署策略、用特性开关做灰度发布。
- [ ] **第四阶段 · 工程化与安全**（完成 13-16）
  - 读懂 GitLab CI，管理版本与发布，把安全扫描嵌入流水线，用 DORA 指标衡量效能。
- [ ] **最终项目 · 端到端流水线**（完成 17）
  - 串联全部知识，独立交付一条从 PR 到生产部署与发布通知的完整流水线。

---

## 工具链一览

本计划涉及的工具及其定位：

| 工具 | 角色 | 出现于 |
|------|------|--------|
| Git + GitHub | 版本控制与协作底座 | 02 起 |
| GitHub Actions | 主力 CI/CD 引擎 | 04-08、14-17 |
| Docker | 容器化与镜像构建 | 09-10、15、17 |
| GitHub Container Registry (GHCR) | 镜像仓库 | 10、17 |
| GitLab CI/CD | 第二 CI/CD 引擎（对比学习） | 13 |
| Dependabot / CodeQL / Trivy | 安全扫描 | 15 |
| release-please / changesets | 发布自动化 | 14 |

> [!info] 为什么以 GitHub Actions 为主力？
> 在主流 CI/CD 工具中，GitHub Actions 与 Git 仓库原生集成、免费额度对个人和小团队充足、YAML 语法直观、生态（Actions Marketplace）庞大。掌握它后，迁移到 GitLab CI、Jenkins、CircleCI 等只是概念映射问题——第 13 节会专门做这种映射。

---

## 与既有知识的迁移提示

| 你已熟悉的 | CI/CD 中的对应 | 关键差异 |
|-----------|---------------|----------|
| 写脚本自动化重复操作 | CI/CD 流水线 | 流水线在**远端运行器**上按事件触发执行，不是本地手动跑 |
| Git commit / push | 流水线触发器 | push、PR、tag、定时都能触发流水线 |
| 本地跑测试 | CI 测试阶段 | CI 里测试必须无外部依赖、可重复、可并行 |
| 手动部署到服务器 | CD 部署阶段 | CD 把"手动 SSH 部署"变成**可审计、可回滚的自动化** |
| `npm install` | 依赖恢复 + 缓存 | CI 每次都是干净环境，缓存是提速关键 |

---

## 学习节奏建议

- **每天 1-2 节**：每节 45-90 分钟，含阅读 + 动手。不要一次塞太多。
- **边学边建仓库**：从第 4 节起，建议在自己的 GitHub 上建一个真实的 `quote-api` 仓库，跟着推代码、看 Actions 跑起来。
- **失败了就停下来**：CI 失败是常态。读懂红色日志、改对配置，比赶进度更重要。
- **项目节留足时间**：第 17 节是综合实战，预留 2-3 小时 uninterrupted 时间。
