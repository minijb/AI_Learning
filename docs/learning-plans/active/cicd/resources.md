---
title: CI/CD 学习资源汇总
updated: 2026-06-23
tags: [cicd, devops, resources]
---

# CI/CD 学习资源汇总

> 本文件汇总 CI/CD 学习过程中的优质资源，按主题分类。带 ✅ 的资源为本计划**强烈推荐**的入门起点。

---

## 官方文档

- ✅ [GitHub Actions 官方文档](https://docs.github.com/en/actions) — 本计划主力工具的权威参考，含快速入门、workflow 语法、Actions 市场。
- ✅ [Docker 官方文档](https://docs.docker.com/) — 容器化核心，重点看 Get started、Dockerfile reference、multi-stage builds。
- [GitLab CI/CD 官方文档](https://docs.gitlab.com/ee/ci/) — 第 13 节对照学习。
- [GitHub Container Registry 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Semantic Versioning 2.0.0](https://semver.org/) — 语义化版本规范。

## 经典书籍与报告

- ✅ 📘《Continuous Delivery》— Jez Humble & David Farley。CD 领域奠基之作，讲透部署流水线、环境管理、发布策略。
- 📘《The DevOps Handbook》— Gene Kim 等。DevOps 实践全貌，DORA 研究的方法论基础。
- 📘《Accelerate》— Nicole Forsgren 等。用数据证明 DORA 四指标与组织效能的关系。
- 📘《Site Reliability Engineering》— Google。免费[在线版](https://sre.google/sre-book/table-of-contents/)，可观测性与可靠性圣经。
- 📘《Phoenix Project》— DevOps 小说，适合建立文化直觉。

## 互动教程与学习平台

- ✅ [GitHub Skills: Continuous Integration](https://skills.github.com/) — GitHub 官方互动课程，在真实仓库里学 Actions。
- [GitHub Actions 学习实验室](https://lab.github.com/) — 动手实验环境。
- [Play with Docker](https://labs.play-with-docker.com/) — 浏览器里的 Docker 沙箱，零安装。
- [Katakoda Docker 课程](https://www.katacoda.com/courses/docker) （存档，仍可参考）。

## 精选文章

- [Martin Fowler: Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — CI 概念的经典定义。
- [Martin Fowler: DeploymentPipeline](https://martinfowler.com/bliki/DeploymentPipeline.html)
- [DORA: Four Keys to Measure DevOps Success](https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance)
- [Trunk Based Development](https://trunkbaseddevelopment.com/) — 分支策略深度站。
- [Conventional Commits](https://www.conventionalcommits.org/) — 约定式提交规范。

## 工具速查

| 类别 | 工具 | 说明 |
|------|------|------|
| CI/CD 引擎 | GitHub Actions、GitLab CI、Jenkins、CircleCI、Azure DevOps | 本计划覆盖前两个 |
| 容器 | Docker、Podman、containerd | 本计划用 Docker |
| 镜像仓库 | GHCR、Docker Hub、Harbor、ACR/ECR | 第 10 节用 GHCR |
| 安全扫描 | Dependabot、CodeQL、Trivy、Snyk、SonarQube | 第 15 节 |
| 发布自动化 | release-please、changesets、semantic-release | 第 14 节用 release-please |
| 特性开关 | Unleash、Flagsmith、LaunchDarkly | 第 12 节 |
| 可观测性 | Prometheus、Grafana、OpenTelemetry、Loki | 第 16 节 |

## 视频资源

- [CI/CD Pipeline Explained (YouTube)](https://www.youtube.com/watch?v=EiPxyg3QhYM) — 概念入门动画讲解。
- [Docker 官方 101 系列](https://www.youtube.com/playlist?list=PLkA60AVN3ht8N5gS5X-trN7IZklM4RChA)

## 进阶方向（学完本计划后）

- Kubernetes 上的 CI/CD：ArgoCD、Flux（GitOps）
- Infrastructure as Code：Terraform、Pulumi
- 服务网格与零信任部署：Istio、Linkerd
- 平台工程与内部开发者平台（IDP）
