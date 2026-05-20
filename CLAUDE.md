# CLAUDE.md — AI 程序员自我提升工作区 (Claude)

> Claude agent 入口文件。每次会话启动时注入，指向更深层的信息源。

---

## 工作区结构

```
AI_Learning/
├── CLAUDE.md                  ← 本文件（claude 入口）
├── temp/                      ← 学习系统子目录
│   ├── AGENTS.md              ← pi 入口
│   ├── .claude/
│   │   └── skills/            ← 学习类 Skill（pi/claude 共享）
│   │       ├── learning-plans/    ← 创建结构化学习计划
│   │       ├── tutorial-deepener/ ← 深化扩展已有教程
│   │       ├── knowledge-point-deepener/ ← 知识点深入
│   │       ├── web-researcher/    ← 联网搜索学习资源
│   │       └── docs-manager/      ← 管理 docs 系统
│   └── docs/
│       ├── README.md              ← docs 系统总览
│       ├── learning-plans/        ← 学习计划（一流工件）
│       │   ├── INDEX.md           ← 所有学习计划索引
│       │   ├── active/            ← 进行中的学习计划
│       │   └── completed/         ← 已完成的学习计划
│       ├── knowledge-notes/       ← 简略知识笔记
│       │   └── INDEX.md           ← 知识笔记索引
│       └── deep-dives/            ← 知识点深度探索记录
│           └── INDEX.md           ← 深度探索索引
├── .claude/                   ← 计划管理系统（根目录）
│   └── skills/
│       ├── writing-plans/     ← 计划创建 Skill
│       │   ├── scripts/       ← 创建相关 CLI 脚本
│       │   ├── templates/     ← 计划模板
│       │   └── docs/          ← 创建指南
│       ├── executing-plans/   ← 计划执行 Skill
│       │   ├── scripts/       ← 执行相关 CLI 脚本
│       │   ├── docs/          ← 执行指南
│       │   └── subagent/      ← Subagent 提示词
│       ├── markdown/          ← Markdown 书写规范
│       └── skill-creator/     ← Skill 创建工具
└── docs/
    └── exec-plans/            ← 执行计划（一流工件）
        ├── active/            ← 进行中的计划
        ├── completed/         ← 完成的计划
        ├── PLAN.md            ← 全局活跃计划索引
        ├── PLAN_COMPLETED.md  ← 已完成计划归档
        └── tech-debt-tracker.md ← 技术债务追踪
```

---

## Skill 索引

### 学习类 Skill（`temp/.claude/skills/`）

Skills 位于 `temp/.claude/skills/`，所有 Skill 由 pi 和 Claude 共享。Claude 读取 SKILL.md 了解触发条件和指令。

#### Learning Plans — 创建结构化学习计划
- **路径：** `temp/.claude/skills/learning-plans/SKILL.md`
- **触发：** 用户指定学习领域，如"我想学 Rust"、"学分布式系统"
- **产出：** 按知识点拆分的多文件教程 + 进度追踪

#### Tutorial Deepener — 深化扩展已有教程
- **路径：** `temp/.claude/skills/tutorial-deepener/SKILL.md`
- **触发：** 用户提供教程要求"深化"、"扩展"、"补充"
- **产出：** 补充前置知识、原理推导、实战案例的增强版教程

#### Knowledge Point Deepener — 知识点深入剖析
- **路径：** `temp/.claude/skills/knowledge-point-deepener/SKILL.md`
- **触发：** 用户要求"深入讲"某个知识点、"底层原理"
- **产出：** 多层剖析：表层用法 → 原理 → 源码 → 对比分析

#### Web Researcher — 联网搜索学习资源
- **路径：** `temp/.claude/skills/web-researcher/SKILL.md`
- **触发：** 需要搜索最新文档、社区讨论、开源项目
- **产出：** 结构化的搜索结果和资源推荐

#### Docs Manager — 文档系统管理
- **路径：** `temp/.claude/skills/docs-manager/SKILL.md`
- **触发：** 整理索引、归档计划、管理知识笔记
- **产出：** 更新后的 INDEX.md、归档的学习计划、新增/修改的笔记

---

### 计划管理类 Skill（`.claude/skills/`）

#### Writing Plans (`.claude/skills/writing-plans/`)

**何时激活：** 用户提到"写计划"、"创建计划"、"制定计划"、"规划"、"分步骤"、"拆解任务"、"roadmap"、"实现步骤"；或任何多步骤工作（实现功能、跨模块改动、重构、添加测试等）。

**快速开始：**
```bash
# 创建完整计划（跨平台，需 Python 3.8+）
python .claude/skills/writing-plans/scripts/plan-new.py --full '计划名称'

# 创建轻量计划（≤5 步）
python .claude/skills/writing-plans/scripts/plan-new.py --quick '计划名称'

# 验证计划
python .claude/skills/writing-plans/scripts/plan-validate.py docs/exec-plans/active/<名称>

# 搜索已有计划
python .claude/skills/writing-plans/scripts/plan-search.py "<关键词>"
```

**关键规则：** 无书面计划不写代码。计划中禁止 TBD/TODO 等占位符。功能列表 JSON 只允许修改 `passes` 字段。

详见 `.claude/skills/writing-plans/SKILL.md`

---

#### Executing Plans (`.claude/skills/executing-plans/`)

**何时激活：** 用户提到"执行计划"、"按计划做"、"落实计划"、"实施计划"、"按步骤执行"、"照计划来"。

**快速开始：**
```bash
# 查看活跃计划状态
python .claude/skills/executing-plans/scripts/plan-status.py

# 完成并归档计划
python .claude/skills/executing-plans/scripts/plan-complete.py '计划名称'

# 清理旧计划（预览模式）
python .claude/skills/executing-plans/scripts/plan-cleanup.py --all --what-if
```

**关键规则：** 严格照计划执行，不擅自偏离。验证失败立即停止。执行者假设为零上下文熟练工。

详见 `.claude/skills/executing-plans/SKILL.md`

---

#### Markdown (`.claude/skills/markdown/`)

**何时激活：** 任何需要创建或编辑 `.md` 文件的场景——README、文档、博客、变更日志、技术说明、API 文档等。

详见 `.claude/skills/markdown/SKILL.md`

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
4. **渐进式披露** — 本文件是地图，Skill SKILL.md 是指令；按需加载子文档
5. **文档可修改** — 学习计划和笔记随时可编辑扩展
6. **计划是一流工件** — 存储在仓库内，版本控制
7. **成功沉默，失败输出** — 验证通过不产生噪声
8. **CLI 优于抽象封装** — 工具直接可执行，输出可 grep
