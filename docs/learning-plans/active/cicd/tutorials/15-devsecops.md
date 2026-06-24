---
title: DevSecOps：流水线中的安全
updated: 2026-06-23
tags: [cicd, security, devsecops, scanning]
---

# DevSecOps：流水线中的安全

> 所属计划: [[plan|CI/CD 完整学习计划]]
> 预计耗时: 75min
> 前置知识: [[08-cache-artifacts-deps]]

---

## 1. 概念讲解

### 为什么需要 DevSecOps？

在传统的软件交付流程里，安全往往是一道“期末考”：功能开发完了，测试通过了，最后才交给安全团队做渗透测试或代码审计。如果这时发现严重漏洞，要么硬着头皮延期上线，要么带着风险发布，再打一个补丁。两种方式都很痛苦。

DevSecOps 的核心主张是：**安全不是某个团队的专属职责，而是贯穿整个软件生命周期的工程实践**。它把安全活动嵌入到开发（Dev）和运维（Ops）的日常工作流中，让安全检查和修复像单元测试一样自动化、常态化。

对 `quote-api` 这样的小项目来说，DevSecOps 并不意味着采购昂贵的商业安全套件。借助 GitHub 原生能力和几款开源工具，我们就能在每次提交、每次 PR、每次构建镜像时自动发现风险。

### 安全左移（Shift Left）

“左移”是 DevSecOps 里最常见的词。它指的是把安全活动从发布链的右侧（上线后）移到左侧（编码和构建阶段）。

```mermaid
flowchart LR
    A[需求/设计] --> B[编码]
    B --> C[构建/测试]
    C --> D[部署]
    D --> E[运行]
    subgraph 传统安全测试
        F[渗透测试/审计]
    end
    E --> F
    subgraph 安全左移
        G[SAST/依赖/密钥扫描]
    end
    B -.->|每次提交| G
    C -.->|每次构建| H[镜像扫描]
```

左移的好处很直接：

- **早发现早修复**：在代码刚提交时发现 SQL 注入，改起来只需几分钟；上线后再发现，可能涉及回滚、热修复、用户通知。
- **成本低**：NIST 的研究表明，设计阶段修复漏洞的成本远低于生产阶段。
- **反馈快**：把安全扫描放进 CI，开发者能在 PR 里立刻看到结果，不需要等待安全团队排期。

左移不是“让开发者取代安全专家”，而是让工具先跑起来，把明显、重复的问题自动化过滤掉，让人类专家专注于更复杂的威胁建模和架构安全。

### 流水线里的安全检查类型

下面这张表整理了 CI/CD 流水线里常见的安全检查类型、典型工具和适合的执行阶段。

| 检查类型 | 扫描对象 | 典型工具 | 常用阶段 | 说明 |
|---------|---------|---------|---------|------|
| SAST | 源代码 | GitHub CodeQL、SonarQube、Semgrep | 构建/测试 | 不运行程序，直接分析源码中的漏洞模式 |
| DAST | 运行中的服务 | OWASP ZAP、Burp Suite | 部署后/预发布 | 对真实运行的应用做攻击测试 |
| 依赖/SCA 扫描 | 第三方依赖 | Dependabot、`npm audit`、Trivy fs、Snyk | 构建 | 检查依赖库是否包含已知 CVE |
| 密钥/Secret 扫描 | 代码和提交历史 | GitHub secret scanning、gitleaks、trufflehog | 提交/PR | 防止密钥、Token、密码进入仓库 |
| 镜像扫描 | Docker 镜像 | Trivy image、Grype | 构建镜像后 | 检查镜像 OS 和软件包漏洞 |
| SBOM | 所有依赖清单 | Syft、Trivy、CycloneDX、SPDX | 发布前 | 生成软件物料清单，提升供应链透明度 |

#### SAST：静态应用安全测试

SAST 在**不运行程序**的情况下分析源代码，寻找常见的漏洞模式。例如：

- SQL 注入：把用户输入直接拼进 SQL 字符串。
- 硬编码密钥：把 API Key 或密码写在代码里。
- 不安全的反序列化、XSS、路径遍历等。

GitHub 提供的 **CodeQL** 是免费的 SAST 工具（公开仓库免费，私有仓库需 GitHub Advanced Security 许可）。它通过把代码编译成中间表示，再跑查询规则来发现漏洞。SonarQube 和 Semgrep 则覆盖更多语言规则和商业/社区规则集。

#### DAST：动态应用安全测试

DAST 与 SAST 相反，它需要**应用真正运行起来**。DAST 工具会像攻击者一样向服务发送请求，探测反射型 XSS、SQL 注入、未授权访问等问题。

DAST 通常放在预发布或测试环境，而不是每次本地提交都跑。对于 `quote-api` 这种简单 API，DAST 可以作为可选的高级检查，本节暂不深入配置。

#### 依赖/SCA 扫描

现代项目很少从零开始写所有代码。`quote-api` 也会依赖 Express、Vitest、`@types/node` 等第三方库。这些依赖一旦曝出漏洞（CVE），你的应用即使自身代码没问题，也会暴露在风险中。

SCA（Software Composition Analysis，软件成分分析）就是扫描这些依赖。GitHub 的 **Dependabot** 会自动检测依赖漏洞并发起更新 PR；`npm audit` 可以本地或 CI 中运行；**Trivy** 和 **Snyk** 支持多种语言生态。

#### 密钥/Secret 扫描

把密钥提交到 Git 仓库是非常常见的事故。AWS 密钥、GitHub Token、数据库密码一旦泄露，可能被恶意利用并产生巨额账单。

GitHub 的 **secret scanning** 会在推送时自动检测常见密钥格式并告警。本地还可以用 **gitleaks** 或 **trufflehog** 做提交前钩子（pre-commit hook），在代码进入仓库之前就拦截。

#### 镜像扫描

我们在 [[09-docker-containerization]] 给 `quote-api` 写了 Dockerfile，在 [[10-container-registry]] 把镜像推送到镜像仓库。镜像里除了你的应用代码，还有 Node.js 运行时、基础操作系统、npm 依赖等，这些都可能包含 CVE。

**Trivy image** 和 **Grype** 可以扫描镜像里的漏洞，并在 CI 中根据严重程度决定是否阻断构建。

#### SBOM：软件物料清单

SBOM（Software Bill of Materials）是一份列出软件所有组成部分的清单，包括直接依赖、间接依赖、操作系统包、许可证等。它回答的问题是：“如果某个依赖曝出漏洞，我到底受不受影响？”

常见 SBOM 标准有两个：

- **SPDX**：由 Linux 基金会维护，强调许可证和供应链。
- **CycloneDX**：由 OWASP 维护，强调安全漏洞和组件元数据。

在发布前生成 SBOM，已经成为很多合规场景（如 FedRAMP、医疗器械软件）和供应链安全实践的标准动作。

### GitHub 原生安全能力

GitHub 为开源仓库提供了几套开箱即用的安全工具，把它们配进 CI 几乎没有额外成本：

- **Dependabot**：自动生成依赖更新 PR，包括安全更新。配置文件是 `.github/dependabot.yml`。
- **CodeQL**：GitHub 官方 SAST 工具，通过 `github/codeql-action` 集成到 workflow。
- **Secret scanning**：在仓库设置里开启后，推送敏感内容会自动告警或阻止（公开仓库默认可用）。

私有仓库需要确认 GitHub Advanced Security 许可，但本节示例主要面向公开仓库或学习场景。

### 门禁策略：阻断还是告警？

安全扫描发现了问题，接下来怎么办？常见的策略有三种：

1. **阻断式（Blocking）**：任何 HIGH/CRITICAL 漏洞都阻止 PR 合并。适合安全要求高的项目。
2. **告警式（Warning）**：只生成报告和通知，不阻止合并。适合初期上线、需要观察误报率的阶段。
3. **分级式**：高危阻断，中危告警，低危记录。这是最常用的折中方案。

门禁太松，漏洞会累积成“技术债务”；门禁太严，开发者可能为了赶进度关掉扫描、批量加 ignore，或者把安全审查变成“形式主义”。

推荐的演进路线：

```mermaid
flowchart LR
    A[阶段1: 仅告警<br/>收集数据] --> B[阶段2: HIGH阻断<br/>LOW记录]
    B --> C[阶段3: 分级策略<br/>按业务风险调整]
```

### 螺旋上升：供应链安全

还记得 [[06-reusable-composite-actions]] 里强调的“别用未维护的第三方 action”吗？那就是供应链安全的一部分。你引用的每一个 GitHub Action、每一个 npm 包、每一个 Docker 基础镜像，都是供应链的一环。

DevSecOps 不是只扫自己的代码，还要回答：

- 这个 action 是谁维护的？最后一次更新是什么时候？
- 这个 npm 包的下载量、维护状态、许可证是什么？
- 基础镜像是不是官方镜像？有没有定期更新？

把 [[06-reusable-composite-actions]] 的“固定 action 版本、审查第三方 action”和本节的“依赖扫描、镜像扫描、SBOM”结合起来，才是完整的供应链安全视角。

---

## 2. 代码示例

下面的示例围绕 `quote-api` 项目展开。我们会先配置 Dependabot，再创建一份独立的安全扫描 workflow。

### 2.1 开启 Dependabot

在仓库根目录创建 `.github/dependabot.yml`：

```yaml
# .github/dependabot.yml
version: 2
updates:
  # npm 依赖：每周一检查一次
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
    # 同时允许安全更新和普通版本更新
    open-pull-requests-limit: 10
    # 给 PR 打标签，方便筛选
    labels:
      - "dependencies"
      - "security"
    # 提交信息格式
    commit-message:
      prefix: "chore(deps)"

  # GitHub Actions：检查 workflow 里引用的 action 版本
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "github-actions"
```

把文件提交到 main 分支后，GitHub 会在后台自动运行 Dependabot。如果 `quote-api` 的某个依赖存在 CVE，Dependabot 会创建一个类似 `Bump lodash from 4.17.20 to 4.17.21` 的 PR，并标注安全影响。

### 2.2 安全扫描 workflow

在 `.github/workflows/security.yml` 中定义三个 job：CodeQL SAST、Trivy 文件系统扫描、Trivy 镜像扫描。

```yaml
# .github/workflows/security.yml
name: Security Scans

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  # 允许手动触发，方便调试
  workflow_dispatch:

permissions:
  actions: read
  contents: read
  security-events: write

jobs:
  sast:
    name: CodeQL SAST
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: javascript-typescript
          # 可选：指定查询套件，初期用默认即可
          # queries: security-extended

      - name: Autobuild
        uses: github/codeql-action/autobuild@v3

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3

  dependency-scan:
    name: Dependency / SCA Scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Run Trivy filesystem scan
        uses: aquasecurity/trivy-action@0.29.0
        with:
          scan-type: "fs"
          scan-ref: "."
          format: "sarif"
          output: "trivy-fs.sarif"
          severity: "CRITICAL,HIGH"
          # 先不上传 SARIF，避免误报阻塞 PR；稳定后再开启
          # exit-code: "1"

      - name: Upload Trivy FS scan results
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: "trivy-fs.sarif"
          category: "trivy-fs"

  image-scan:
    name: Docker Image Scan
    runs-on: ubuntu-latest
    needs: dependency-scan
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build image for scanning
        run: |
          docker build -t quote-api:scan .

      - name: Run Trivy image scan
        uses: aquasecurity/trivy-action@0.29.0
        with:
          image-ref: "quote-api:scan"
          format: "sarif"
          output: "trivy-image.sarif"
          severity: "CRITICAL,HIGH"
          # 发现 HIGH 时失败，阻断后续步骤
          exit-code: "1"

      - name: Upload Trivy image scan results
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: "trivy-image.sarif"
          category: "trivy-image"
```

### 2.3 本地预览：Trivy 文件系统扫描

在把 Trivy 写进 CI 之前，你可以在本地先跑一遍，看看 `quote-api` 的依赖是否存在已知漏洞。

**运行方式：**

```bash
# 安装 Trivy（以 macOS 为例，其他系统参考官方文档）
brew install trivy

# 在 quote-api 根目录执行文件系统扫描
trivy fs --severity HIGH,CRITICAL .
```

**预期输出（无漏洞时）：**

```text
2026-06-23T09:00:00.000+0800	INFO	Need to update DB
2026-06-23T09:00:05.000+0800	INFO	Vulnerability scanning is enabled
2026-06-23T09:00:06.000+0800	INFO	Number of language-specific files: 1

package-lock.json (npm)
=======================
Total: 0 (HIGH: 0, CRITICAL: 0)
```

**预期输出（存在漏洞时）：**

```text
package-lock.json (npm)
=======================
Total: 1 (HIGH: 1, CRITICAL: 0)

┌─────────┬────────────────┬──────────┬────────┬───────────────────┐
│ Library │ Vulnerability  │ Severity │ Status │ Installed Version │
├─────────┼────────────────┼──────────┼────────┼───────────────────┤
│ express │ CVE-2024-XXXXX │ HIGH     │ fixed  │ 4.18.0            │
└─────────┴────────────────┴──────────┴────────┴───────────────────┘
```

本地预览的好处是：你可以先判断哪些是真正的风险、哪些是误报，再决定 CI 里的 `severity` 和 `exit-code` 策略。

### 2.4 在 GitHub 上查看结果

- CodeQL 结果会显示在仓库的 **Security → Code scanning alerts** 页面。
- Trivy 通过 `upload-sarif` 上传后，也会出现在同一个 Code scanning 列表中，按 `category` 区分。
- Dependabot 的 PR 会出现在 **Pull requests** 页面，并附带安全标签。

---

## 3. 练习

### 练习 1: [基础] 给 quote-api 开启 Dependabot

为 `quote-api` 创建 `.github/dependabot.yml`，让它每周检查 npm 依赖和 GitHub Actions 版本更新。提交后解释：如果 Dependabot 创建了一个标注为 `security` 的 PR，你应该按什么顺序检查它？

### 练习 2: [进阶] 在 CI 中增加 Trivy 镜像扫描门禁

在上面的 `security.yml` 基础上，新增一个 job：在构建 `quote-api` 镜像后，用 Trivy 扫描镜像，要求发现任何 HIGH 或 CRITICAL 漏洞时直接失败（`exit-code: "1"`）。写出完整的 job YAML。

### 练习 3: [挑战]（可选）验证 secret scanning 的拦截效果

创建一个临时分支，故意提交一个“假密钥”（例如格式正确的 GitHub personal access token），然后 push 到远程。观察 GitHub 是否会发送告警邮件或在仓库 Security 页面生成 alert。说明你的操作步骤和预期结果。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
>
> `quote-api/.github/dependabot.yml`：
>
> ```yaml
> version: 2
> updates:
>   - package-ecosystem: "npm"
>     directory: "/"
>     schedule:
>       interval: "weekly"
>       day: "monday"
>     open-pull-requests-limit: 10
>     labels:
>       - "dependencies"
>       - "security"
>     commit-message:
>       prefix: "chore(deps)"
>
>   - package-ecosystem: "github-actions"
>     directory: "/"
>     schedule:
>       interval: "weekly"
>     labels:
>       - "dependencies"
>       - "github-actions"
> ```
>
> 收到 Dependabot 安全更新 PR 后的检查顺序：
>
> 1. 先看 PR 描述里的 CVE 编号和严重程度，判断对 `quote-api` 是否可复现。
> 2. 让 CI 跑一遍（lint + test + 安全扫描），确认升级没有破坏现有功能。
> 3. 查看变更范围：是主版本升级还是补丁版本？如果是主版本，需要检查 breaking changes。
> 4. 合并到 main，并观察部署后的行为。

> [!tip]- 练习 2 参考答案
>
> 在 `.github/workflows/security.yml` 中新增 `image-scan` job：
>
> ```yaml
>   image-scan:
>     name: Docker Image Scan
>     runs-on: ubuntu-latest
>     needs: dependency-scan
>     steps:
>       - name: Checkout repository
>         uses: actions/checkout@v4
>
>       - name: Set up Docker Buildx
>         uses: docker/setup-buildx-action@v3
>
>       - name: Build image for scanning
>         run: docker build -t quote-api:scan .
>
>       - name: Run Trivy image scan
>         uses: aquasecurity/trivy-action@0.29.0
>         with:
>           image-ref: "quote-api:scan"
>           format: "sarif"
>           output: "trivy-image.sarif"
>           severity: "CRITICAL,HIGH"
>           exit-code: "1"
>
>       - name: Upload Trivy image scan results
>         uses: github/codeql-action/upload-sarif@v3
>         if: always()
>         with:
>           sarif_file: "trivy-image.sarif"
>           category: "trivy-image"
> ```
>
> 关键点：
> - `severity: "CRITICAL,HIGH"` 只关注高风险漏洞，避免 LOW/MEDIUM 的噪音拖慢节奏。
> - `exit-code: "1"` 让 job 失败，从而阻止 PR 合并（如果你设置了分支保护规则要求该 job 通过）。
> - `if: always()` 保证即使扫描失败，SARIF 报告也会被上传，方便在 GitHub Security 页面查看详情。

> [!tip]- 练习 3 参考答案（可选）
>
> 操作步骤：
>
> 1. 在本地创建一个临时分支：`git checkout -b test-secret-scanning`。
> 2. 在仓库中新建一个文件 `dummy-config.json`，内容包含一个格式正确的 GitHub personal access token：
>
>    ```json
>    {
>      "github_token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
>    }
>    ```
>
>    注意：`ghp_` 后面需要 36 个字符的 base64 字符串，GitHub 才能识别为 token 格式。可以用随机字符凑足长度，**不要用真实 token**。
>
> 3. 提交并推送到远程：
>
>    ```bash
>    git add dummy-config.json
>    git commit -m "test: verify secret scanning alert"
>    git push origin test-secret-scanning
>    ```
>
> 4. 预期结果：
>    - 如果你开启了 GitHub secret scanning，GitHub 会立即向仓库管理员发送邮件告警，或在仓库 **Security → Secret scanning alerts** 页面生成一条 alert。
>    - 对于公开仓库，GitHub 通常会先显示 alert，不会自动撤销 token（因为 token 是假的）。
>    - 完成后请删除该测试分支和文件，避免污染仓库历史。
>
> 如果想在本地就拦截，可以安装 [gitleaks](https://github.com/gitleaks/gitleaks) 并配置 pre-commit hook。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [OWASP DevSecOps Guideline](https://owasp.org/www-project-devsecops-guideline/)
- [GitHub Security 文档：配置代码扫描](https://docs.github.com/en/code-security/code-scanning/enabling-code-scanning/configuring-default-setup-for-code-scanning)
- [GitHub Dependabot 文档](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
- [Trivy 官方文档](https://aquasecurity.github.io/trivy/)
- [CycloneDX 官网](https://cyclonedx.org/)
- [SPDX 规范](https://spdx.dev/)
- [NIST：在软件开发生命周期中修复漏洞的成本](https://www.nist.gov/itl/ssd/software-quality-group/research/relative-cost-repair-software-defects)

---

## 常见陷阱

- **扫描只装不用**：把 Trivy、CodeQL 配进 CI 后就不再关注告警，漏洞列表越积越长。正确做法是：指定 owner 定期清理告警，把未处理的高危漏洞列进迭代 backlog。
- **门禁太严，开发绕过**：一开始就把所有 severity 都设为阻断，导致开发者频繁被误报卡住，最后选择关闭扫描或批量加 ignore。正确做法是：先用“告警模式”跑 1-2 周，根据误报率调整 severity 阈值，再逐步加门禁。
- **忽略供应链**：只扫描自己的源码，不审查第三方 action 和 npm 包。正确做法是：结合 [[06-reusable-composite-actions]] 的行动建议，固定 action 版本、查看维护状态、定期更新依赖，并把镜像扫描纳入构建流程。
- **把密钥写进代码然后删除就觉得安全**：Git 历史里仍然能找回被删除的密钥。正确做法是：一旦泄露真实密钥，立即在对应平台撤销并重新生成，不要只依赖 `git rm`。
- **只依赖 GitHub 原生工具**：Dependabot 和 CodeQL 很方便，但它们不能覆盖所有场景（例如镜像扫描、DAST、SBOM 生成）。正确做法是：根据项目风险选择合适的工具组合，不要把“免费”当成“足够”。

---

交叉引用：缓存/制品 [[08-cache-artifacts-deps]]；Docker [[09-docker-containerization]]；镜像仓库 [[10-container-registry]]；综合项目会集成安全 [[17-capstone-project]]。
