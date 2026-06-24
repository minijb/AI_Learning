---
title: CI/CD 教程索引
updated: 2026-06-23
tags: [cicd, tutorials]
---

# 教程索引

> 教程文件按知识依赖关系排序。建议按序号依次学习，但已掌握的部分可跳过。所有实战节围绕示例项目 `quote-api`（TypeScript + Node.js 极简 HTTP API）展开。

## 第一阶段 · 建立全景认知

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 1 | CI/CD 与 DevOps 全景 | [[01-ci-cd-devops-overview]] | 60min |
| 2 | 版本控制与分支策略 | [[02-version-control-branching]] | 60min |
| 3 | 流水线核心概念 | [[03-pipeline-core-concepts]] | 60min |

## 第二阶段 · 用 GitHub Actions 跑通 CI

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 4 | GitHub Actions 入门 | [[04-github-actions-intro]] | 75min |
| 5 | 变量、Secrets、条件与矩阵 | [[05-secrets-conditions-matrix]] | 75min |
| 6 | 可复用工作流与 Composite Actions | [[06-reusable-composite-actions]] | 75min |
| 7 | CI 中的测试策略 | [[07-testing-in-ci]] | 75min |
| 8 | 缓存、制品与依赖管理 | [[08-cache-artifacts-deps]] | 60min |

## 第三阶段 · 容器化与部署

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 9 | Docker 与容器化 | [[09-docker-containerization]] | 90min |
| 10 | 容器镜像与镜像仓库 | [[10-container-registry]] | 60min |
| 11 | 部署策略：蓝绿、金丝雀、滚动 | [[11-deployment-strategies]] | 75min |
| 12 | 渐进式交付与特性开关 | [[12-progressive-delivery-flags]] | 60min |

## 第四阶段 · 工程化与安全

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 13 | GitLab CI/CD | [[13-gitlab-cicd]] | 75min |
| 14 | 发布管理与语义化版本 | [[14-release-semver]] | 60min |
| 15 | DevSecOps：流水线中的安全 | [[15-devsecops]] | 75min |
| 16 | 可观测性与 DORA 指标 | [[16-observability-dora]] | 60min |

## 最终项目

| 序号 | 知识点 | 文件 | 耗时 |
|------|--------|------|------|
| 17 | 综合项目：端到端流水线 | [[17-capstone-project]] | 150min |

---

> [!info] 学习路径图
> ```mermaid
> flowchart TD
>     S1["01 CI/CD 全景"] --> S2["02 版本控制与分支"]
>     S1 --> S3["03 流水线核心概念"]
>     S3 --> S4["04 GitHub Actions 入门"]
>     S2 --> S4
>     S4 --> S5["05 Secrets/条件/矩阵"]
>     S5 --> S6["06 可复用工作流"]
>     S4 --> S7["07 测试策略"]
>     S4 --> S8["08 缓存/制品"]
>     S3 --> S9["09 Docker"]
>     S9 --> S10["10 镜像仓库"]
>     S8 --> S11["11 部署策略"]
>     S11 --> S12["12 渐进式交付"]
>     S4 --> S13["13 GitLab CI"]
>     S6 --> S14["14 发布与版本"]
>     S8 --> S15["15 DevSecOps"]
>     S11 --> S16["16 可观测性/DORA"]
>     S6 & S8 & S10 & S15 --> S17["17 综合项目"]
> ```
