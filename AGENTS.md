# AGENTS.md — AI 程序员自我提升工作区 (OMP)

> OMP agent 入口文件。每个会话启动时注入，指向更深层的信息源。

---

## 工作区结构

```
.
├── AGENTS.md                  ← 本文件（OMP 入口）
├── CLAUDE.md                  ← claude 入口（兼容）
├── .omp/
│   └── skills/                ← OMP 原生 Skill
│       ├── learning-plans/    ← 创建结构化学习计划
│       ├── tutorial-deepener/ ← 深化扩展已有教程
│       ├── knowledge-point-deepener/ ← 知识点深入
│       ├── web-researcher/    ← 联网搜索学习资源
│       ├── docs-manager/      ← 管理 docs 系统
│       ├── writing-plans/     ← 计划创建 Skill
│       ├── executing-plans/   ← 计划执行 Skill
│       ├── markdown/          ← Markdown 书写规范
│       └── skill-creator/     ← 创建/改进/评测 Skill
├── docs/
│   ├── README.md              ← docs 系统总览
│   ├── learning-plans/        ← 学习计划（一流工件）
│   │   ├── INDEX.md           ← 所有学习计划索引
│   │   ├── active/            ← 进行中的学习计划
│   │   └── completed/         ← 已完成的学习计划
│   ├── knowledge-notes/       ← 简略知识笔记
│   │   └── INDEX.md           ← 知识笔记索引
│   ├── exec-plans/            ← 执行计划（一流工件）
│   │   ├── PLAN.md            ← 全局活跃计划索引
│   │   ├── PLAN_COMPLETED.md  ← 已完成计划归档
│   │   ├── tech-debt-tracker.md ← 技术债务追踪
│   │   ├── active/            ← 进行中的计划
│   │   └── completed/         ← 完成的计划
│   └── deep-dives/            ← 知识点深度探索记录
│       └── INDEX.md           ← 深度探索索引
```

---

## Skill 索引

Skills 位于 `.omp/skills/`，由 OMP 原生 Skill Provider 发现（优先级 100）。

### 学习类 Skill

#### Learning Plans (`.omp/skills/learning-plans/`)

**何时激活：** 用户指定一个学习领域（如"我想学 Rust"、"学分布式系统"、"掌握 K8s"），需要创建完整学习计划 + 详细教程。

**功能：**
- 根据领域生成结构化学习路径
- 教程自动按知识点拆分为多个文件
- 每个知识点包含：概念讲解 → 代码示例 → 练习 → 扩展阅读

详见 `skill://learning-plans`

---

#### Tutorial Deepener (`.omp/skills/tutorial-deepener/`)

**何时激活：** 用户提供已有教程（链接或文本），要求"深化"、"扩展"、"补充"该教程。

**功能：**
- 分析教程结构，识别可深化点
- 补充前置知识、原理推导、边界情况
- 添加实战案例和常见陷阱

详见 `skill://tutorial-deepener`

---

#### Knowledge Point Deepener (`.omp/skills/knowledge-point-deepener/`)

**何时激活：** 用户针对教程中某个具体知识点要求"深入"、"详细讲"、"底层原理"。

**功能：**
- 从表层用法到底层实现逐层剖析
- 对比同类技术方案的优劣
- 提供源码级分析和性能特征

详见 `skill://knowledge-point-deepener`

---

#### Web Researcher (`.omp/skills/web-researcher/`)

**何时激活：** 需要联网搜索学习资源、最新文档、社区讨论、论文等。

**功能：**
- 搜索最新教程和文档
- 查找官方文档和 RFC
- 发现社区最佳实践和开源项目

详见 `skill://web-researcher`

---

#### Docs Manager (`.omp/skills/docs-manager/`)

**何时激活：** 需要管理 docs 系统：创建/更新索引、整理知识笔记、归档学习计划、跨计划搜索。

**功能：**
- 自动维护 INDEX.md 索引
- 知识笔记增删改查
- 学习计划归档和状态管理

详见 `skill://docs-manager`

---

### 计划管理类 Skill

#### Writing Plans (`.omp/skills/writing-plans/`)

**何时激活：** 用户提到"写计划"、"创建计划"、"制定计划"、"规划"、"分步骤"、"拆解任务"、"roadmap"、"实现步骤"；或任何多步骤工作（实现功能、跨模块改动、重构、添加测试等）。

**快速开始：**
```bash
# 创建完整计划（跨平台，需 Python 3.8+）
python .omp/skills/writing-plans/scripts/plan-new.py --full '计划名称'

# 创建轻量计划（≤5 步）
python .omp/skills/writing-plans/scripts/plan-new.py --quick '计划名称'

# 验证计划
python .omp/skills/writing-plans/scripts/plan-validate.py docs/exec-plans/active/<名称>

# 搜索已有计划
python .omp/skills/writing-plans/scripts/plan-search.py "<关键词>"
```

**关键规则：** 无书面计划不写代码。计划中禁止 TBD/TODO 等占位符。功能列表 JSON 只允许修改 `passes` 字段。

详见 `skill://writing-plans`

---

#### Executing Plans (`.omp/skills/executing-plans/`)

**何时激活：** 用户提到"执行计划"、"按计划做"、"落实计划"、"实施计划"、"按步骤执行"、"照计划来"。

**快速开始：**
```bash
# 查看活跃计划状态
python .omp/skills/executing-plans/scripts/plan-status.py

# 完成并归档计划
python .omp/skills/executing-plans/scripts/plan-complete.py '计划名称'

# 清理旧计划（预览模式）
python .omp/skills/executing-plans/scripts/plan-cleanup.py --all --what-if
```

**关键规则：** 严格照计划执行，不擅自偏离。验证失败立即停止。执行者假设为零上下文熟练工。

详见 `skill://executing-plans`

---

#### Markdown (`.omp/skills/markdown/`)

**何时激活：** 任何需要创建或编辑 `.md` 文件的场景——README、文档、博客、变更日志、技术说明、API 文档等。

详见 `skill://markdown`

---

### 工具类 Skill

#### Skill Creator (`.omp/skills/skill-creator/`)

**何时激活：** 需要创建新 Skill、改进已有 Skill、评测 Skill 性能、优化 Skill 触发描述时。

**功能：**
- 从零创建符合规范的 Skill（SKILL.md + scripts + templates + docs）
- 运行测试用例 + 对比基准，生成评测报告
- 迭代改进 Skill 内容
- 优化 Skill 的 description 触发准确率

详见 `skill://skill-creator`

---

## 工作流

### 学习工作流

#### 模式 A：领域学习（用户指定领域）
```
用户："我想学 Rust 异步编程"
  → learning-plans skill 创建计划
  → 生成按知识点拆分的教程（docs/learning-plans/active/rust-async/）
  → 用户逐步学习，更新 progress.md
  → 完成后归档到 completed/
```

#### 模式 B：教程深化（用户提供教程）
```
用户：提供教程链接/文本 + "帮我深化这个教程"
  → tutorial-deepener skill 分析教程
  → 补充缺失内容（前置知识、原理、案例）
  → 输出到 docs/deep-dives/ 或对应学习计划目录
```

#### 模式 C：知识点深入
```
用户："详细讲讲 Rust 的 Pin 是怎么工作的"
  → knowledge-point-deepener skill 加载相关上下文
  → 逐层剖析（使用场景 → 原理 → 源码）
  → 输出到 docs/deep-dives/
```

#### 模式 D：自主探索
```
AI 根据学习进度建议相关主题
  → web-researcher 搜索最新资源
  → 整合到学习计划或知识笔记
```

### 计划管理协作流程

```
创建计划 ──→ 填充模板 ──→ 验证 ──→ 按计划执行 ──→ 标记完成 ──→ 归档
    ↑                                                      ↓
  writing-plans                                        executing-plans
```

---

## 核心原则

1. **计划优先** — 审查过的书面计划存在之前，不写代码；学习计划与执行计划均版本控制
2. **知识点分割** — 教程按知识点拆分为独立 .md 文件，不限制总字数
3. **分类索引** — `INDEX.md` 始终可导航，按领域分类
4. **渐进式披露** — 本文件是地图，Skill `skill://<name>` 是指令；按需加载子文档
5. **文档可修改** — 学习计划和笔记随时可编辑扩展
6. **计划是一流工件** — 存储在仓库内，版本控制
7. **成功沉默，失败输出** — 验证通过不产生噪声
8. **CLI 优于抽象封装** — 工具直接可执行，输出可 grep

---

## OMP 资源

| 资源 | 路径 | 用途 |
|------|------|------|
| 项目记忆 | `memory://root` | 跨会话持久化知识 |
| Harness 文档 | `omp://` | 运行时/工具/扩展文档 |
| Skill 文件 | `skill://<name>` | 按需加载 Skill 指令 |
