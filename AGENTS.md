# AGENTS.md — AI 程序员自我提升工作区 (pi)

> pi agent 入口文件。每个会话启动时注入，指向更深层的信息源。

---

## 工作区结构

```
.
├── AGENTS.md                  ← 本文件（pi 入口）
├── CLAUDE.md                  ← claude 入口
├── .pi/
│   └── skills/                ← pi 可复用 Skill
│       ├── learning-plans/    ← 创建结构化学习计划
│       ├── tutorial-deepener/ ← 深化扩展已有教程
│       ├── knowledge-point-deepener/ ← 知识点深入
│       ├── web-researcher/    ← 联网搜索学习资源
│       ├── docs-manager/      ← 管理 docs 系统
│       └── skill-creator/     ← 创建/改进/评测 Skill
├── docs/
│   ├── README.md              ← docs 系统总览
│   ├── learning-plans/        ← 学习计划（一流工件）
│   │   ├── INDEX.md           ← 所有学习计划索引
│   │   ├── active/            ← 进行中的学习计划
│   │   └── completed/         ← 已完成的学习计划
│   ├── knowledge-notes/       ← 简略知识笔记
│   │   └── INDEX.md           ← 知识笔记索引
│   └── deep-dives/            ← 知识点深度探索记录
│       └── INDEX.md           ← 深度探索索引
```

---

## Skill 索引

### Learning Plans (`.pi/skills/learning-plans/`)

**何时激活：** 用户指定一个学习领域（如"我想学 Rust"、"学分布式系统"、"掌握 K8s"），需要创建完整学习计划 + 详细教程。

**功能：**
- 根据领域生成结构化学习路径
- 教程自动按知识点拆分为多个文件
- 每个知识点包含：概念讲解 → 代码示例 → 练习 → 扩展阅读

详见 `.pi/skills/learning-plans/SKILL.md`

---

### Tutorial Deepener (`.pi/skills/tutorial-deepener/`)

**何时激活：** 用户提供已有教程（链接或文本），要求"深化"、"扩展"、"补充"该教程。

**功能：**
- 分析教程结构，识别可深化点
- 补充前置知识、原理推导、边界情况
- 添加实战案例和常见陷阱

详见 `.pi/skills/tutorial-deepener/SKILL.md`

---

### Knowledge Point Deepener (`.pi/skills/knowledge-point-deepener/`)

**何时激活：** 用户针对教程中某个具体知识点要求"深入"、"详细讲"、"底层原理"。

**功能：**
- 从表层用法到底层实现逐层剖析
- 对比同类技术方案的优劣
- 提供源码级分析和性能特征

详见 `.pi/skills/knowledge-point-deepener/SKILL.md`

---

### Web Researcher (`.pi/skills/web-researcher/`)

**何时激活：** 需要联网搜索学习资源、最新文档、社区讨论、论文等。

**功能：**
- 搜索最新教程和文档
- 查找官方文档和 RFC
- 发现社区最佳实践和开源项目

详见 `.pi/skills/web-researcher/SKILL.md`

---

### Docs Manager (`.pi/skills/docs-manager/`)

**何时激活：** 需要管理 docs 系统：创建/更新索引、整理知识笔记、归档学习计划、跨计划搜索。

**功能：**
- 自动维护 INDEX.md 索引
- 知识笔记增删改查
- 学习计划归档和状态管理

详见 `.pi/skills/docs-manager/SKILL.md`

---

### Skill Creator (`.pi/skills/skill-creator/`)

**何时激活：** 需要创建新 Skill、改进已有 Skill、评测 Skill 性能、优化 Skill 触发描述时。

**功能：**
- 从零创建符合规范的 Skill（SKILL.md + scripts + templates + docs）
- 运行测试用例 + 对比基准，生成评测报告
- 迭代改进 Skill 内容
- 优化 Skill 的 description 触发准确率

详见 `.pi/skills/skill-creator/SKILL.md`

---

## 学习模式

| 模式 | 触发方式 | 对应 Skill |
|------|---------|-----------|
| 领域学习 | 用户指定领域 | learning-plans |
| 教程深化 | 用户提供教程 | tutorial-deepener |
| 知识点深入 | 用户指定知识点 | knowledge-point-deepener |
| 自主探索 | AI 建议 + 联网搜索 | web-researcher |
| 文档管理 | 整理/索引/归档 | docs-manager |

---

## 核心原则

1. **计划优先** — 学习计划是 docs 中的一流工件，版本控制
2. **渐进式披露** — 本文件是地图，按需加载子文档
3. **知识点分割** — 单个教程不限制总字数，但按知识点拆分为独立文件
4. **成功沉默，失败输出** — 验证通过不产生噪声
5. **分类索引** — 所有学习内容按领域分类，INDEX.md 始终可导航
