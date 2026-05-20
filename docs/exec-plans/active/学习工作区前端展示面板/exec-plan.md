# Exec Plan: 学习工作区前端展示面板

> 完整执行计划 — 跨模块改动、新功能开发。
> **⚡ 零占位符：禁止 TBD / TODO / implement later / add error handling 等模糊描述。**
> **For agentic workers:** 使用 `executing-plans` skill 按 Task 逐个执行。

---

**Goal:** 使用 git worktree 在 `Src/` 目录下创建基于 TypeScript + React + Vite 的前端项目，可视化展示 AI_Learning 工作区中的学习计划、教程内容、执行计划状态和知识笔记，提供学习进度标记、笔记标注和全文搜索功能。

**Architecture:** 前端使用 React + TypeScript + Vite 构建 SPA。构建时扫描 `docs/` 和 `temp/docs/` 生成 JSON 索引。运行时加载索引并渲染。用户状态（进度、笔记）持久化到 `localStorage`。搜索基于预构建的反向索引在客户端完成。

**Tech Stack:** TypeScript 5.4 / React 18 / Vite 5 / react-markdown / react-router-dom / CSS Modules

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              AI Learning Dashboard                       │
│                         (React 18 + TypeScript + Vite)                  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   Dashboard  │  │ LearningPlan │  │ PlanDetail   │  │MarkdownView │ │
│  │   (仪表盘)    │  │  (计划列表)   │  │  (计划详情)   │  │ (内容阅读)   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   ExecPlans  │  │  DeepDives   │  │KnowledgeNotes│                  │
│  │  (执行计划)   │  │  (深度探索)   │  │  (知识笔记)   │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   SearchBar  │  │ ProgressBar  │  │  NoteEditor  │                  │
│  │   (搜索栏)    │  │   (进度条)    │  │  (笔记标注)   │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Data Layer                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │useLearningData│  │ useProgress  │  │  useNotes    │  │ useSearch   │ │
│  │  (加载索引)   │  │(进度状态管理) │  │ (笔记状态管理)│  │(搜索索引管理)│ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│  Persistence                                                             │
│  ┌────────────────────────┐  ┌────────────────────────┐                │
│  │  learning-data.json    │  │     localStorage       │                │
│  │  (构建时生成静态索引)    │  │  progress / notes /    │                │
│  │                        │  │  search-index          │                │
│  └────────────────────────┘  └────────────────────────┘                │
├─────────────────────────────────────────────────────────────────────────┤
│  Build Pipeline                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  scan-learning-data.ts  →  扫描 docs/ & temp/docs/  →  JSON      │  │
│  │  build-search-index.ts  →  分词 + 倒排索引  →  search-index.json │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**数据流：**
1. 构建时：`scan-learning-data.ts` 扫描 Markdown → `public/data/learning-data.json`
2. 构建时：`build-search-index.ts` 对 Markdown 内容分词 → `public/data/search-index.json`
3. 运行时：`useLearningData` 加载 `learning-data.json` → 各页面渲染
4. 用户操作：`useProgress` / `useNotes` 更新状态 → 同步到 `localStorage`
5. 搜索：`useSearch` 读取 `search-index.json` → 客户端匹配 → 结果列表

---

## Task 1: 使用 git worktree 创建前端项目骨架

**Files:**
- Create: `Src/package.json`
- Create: `Src/tsconfig.json`
- Create: `Src/tsconfig.node.json`
- Create: `Src/vite.config.ts`
- Create: `Src/index.html`
- Create: `Src/src/main.tsx`
- Create: `Src/src/App.tsx`
- Create: `Src/src/App.css`
- Create: `Src/src/vite-env.d.ts`
- Create: `Src/.gitignore`
- Modify: `.gitignore`（追加 `Src/node_modules/` 和 `Src/dist/`）

- [ ] **Step 1: 创建 git worktree**
  ```bash
  git worktree add Src
  ```
  - 验证：`git worktree list` → 预期输出包含 `Src` 路径

- [ ] **Step 2: 初始化 Node.js 项目并安装依赖**
  ```bash
  cd Src && npm init -y
  npm install react react-dom react-router-dom react-markdown remark-gfm
  npm install -D typescript @types/react @types/react-dom @types/node vite @vitejs/plugin-react
  ```
  - 验证：`ls Src/node_modules/react/package.json` → 预期：文件存在

- [ ] **Step 3: 配置 TypeScript + Vite + React 入口文件**
  配置项：
  - `tsconfig.json`: target ES2020, module ESNext, jsx react-jsx, strict true
  - `vite.config.ts`: plugin-react, base: './'
  - `index.html`: 引入 `/src/main.tsx`
  - `main.tsx`: ReactDOM.createRoot + BrowserRouter + App
  - `App.tsx`: Routes 配置（Layout + 各页面路由）
  - `App.css`: 全局布局样式（侧边栏 220px + 主内容区、卡片网格、进度条、统计卡片）
  - 验证：`test -f Src/vite.config.ts && test -f Src/src/main.tsx && test -f Src/src/App.tsx` → 预期：全部存在

- [ ] **Step 4: 更新根 .gitignore 排除 worktree 构建产物**
  追加 `Src/node_modules/` 和 `Src/dist/` 到根 `.gitignore`
  - 验证：`grep "Src/node_modules" .gitignore` → 预期：匹配到行

- [ ] **Step 5: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: init TypeScript React frontend with Vite"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: init TypeScript React frontend with Vite`

---

## Task 2: 构建数据扫描与搜索索引脚本

**Files:**
- Create: `Src/scripts/scan-learning-data.ts`
- Create: `Src/scripts/build-search-index.ts`
- Modify: `Src/package.json`（添加 scripts 字段：dev/build/preview/scan/index）
- Create: `Src/src/types/index.ts`

- [ ] **Step 1: 定义 TypeScript 类型**
  类型定义（`Src/src/types/index.ts`）：
  - `Tutorial`: { id, title, filename, order }
  - `LearningPlan`: { id, name, description, createdDate, totalHours, targetLevel, progress, tutorials[], planPath, progressPath }
  - `ExecPlan`: { id, name, summary, status, createdDate, path }
  - `DeepDive`: { id, title, path }
  - `KnowledgeNote`: { id, title, path }
  - `LearningData`: 以上所有数组的集合
  - `SearchIndex`: { terms: Record<term, Array<{path, positions}>>, documents: Array<{path, title, preview}> }
  - `UserProgress`: Record<planId, { completedTutorialIds: string[], lastAccessed: string }>
  - `UserNotes`: Record<documentPath, Array<{id, text, quote, createdAt, updatedAt}>>
  - 验证：`test -f Src/src/types/index.ts` → 预期：文件存在

- [ ] **Step 2: 实现数据扫描脚本**
  `scan-learning-data.ts` 功能：
  - 扫描 `../../docs/learning-plans/active/` 下的子目录
  - 解析每个计划的 `plan.md`（提取 frontmatter + 一级标题）
  - 解析 `progress.md`（提取总进度百分比）
  - 扫描 `tutorials/` 子目录，提取每个教程的标题和文件名
  - 扫描 `../../docs/exec-plans/active/` 提取活跃执行计划
  - 扫描 `../../docs/deep-dives/` 和 `../../docs/knowledge-notes/` 提取文章
  - 输出到 `public/data/learning-data.json`
  - 验证：`npm run scan` → 预期：`public/data/learning-data.json` 存在且非空

- [ ] **Step 3: 实现搜索索引构建脚本**
  `build-search-index.ts` 功能：
  - 读取所有被 `scan-learning-data.ts` 扫描到的 Markdown 文件
  - 对每个文件进行中文+英文分词（中文按字/词，英文按空格+标点）
  - 构建倒排索引：term → [{documentPath, positions[]}]
  - 为每个文档提取 200 字预览文本
  - 输出到 `public/data/search-index.json`
  - 验证：`npm run index` → 预期：`public/data/search-index.json` 存在且 size > 1KB

- [ ] **Step 4: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add data scanner and search index builder"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add data scanner and search index builder`

---

## Task 3: 实现布局与导航系统

**Files:**
- Create: `Src/src/components/Layout.tsx`
- Create: `Src/src/components/Sidebar.tsx`
- Create: `Src/src/components/Sidebar.css`
- Create: `Src/src/components/SearchBar.tsx`
- Create: `Src/src/components/SearchBar.css`
- Modify: `Src/src/App.tsx`

- [ ] **Step 1: 实现侧边栏导航**
  `Sidebar.tsx` 功能：
  - 固定左侧 220px，深色背景
  - 显示 "AI Learning" logo
  - 导航项：仪表盘、学习计划、执行计划、深度探索、知识笔记
  - 使用 NavLink 实现 active 状态高亮
  - 验证：访问 `http://localhost:5173` → 预期：侧边栏可见，点击导航项切换路由

- [ ] **Step 2: 实现全局搜索栏**
  `SearchBar.tsx` 功能：
  - 置于侧边栏顶部或主内容区顶部（推荐：侧边栏底部或顶部独立区域）
  - 输入时实时搜索（debounce 300ms）
  - 搜索 `search-index.json`，匹配标题 + 内容
  - 下拉结果列表显示：标题 + 预览高亮片段 + 来源类型标签
  - 点击结果跳转 `/view?path=...`
  - 验证：在搜索框输入 "ECS" → 预期：下拉显示包含 ECS 的教程/文章列表

- [ ] **Step 3: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add sidebar navigation and global search"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add sidebar navigation and global search`

---

## Task 4: 实现仪表盘与学习计划页面

**Files:**
- Create: `Src/src/pages/Dashboard.tsx`
- Create: `Src/src/pages/LearningPlans.tsx`
- Create: `Src/src/pages/PlanDetail.tsx`
- Create: `Src/src/hooks/useLearningData.ts`

- [ ] **Step 1: 实现数据加载 Hook**
  `useLearningData.ts` 功能：
  - fetch `/data/learning-data.json`
  - 返回 `{ data: LearningData | null, loading: boolean, error: string | null }`
  - 验证：`grep "fetch('/data/learning-data.json')" Src/src/hooks/useLearningData.ts` → 预期：匹配

- [ ] **Step 2: 实现仪表盘页面**
  `Dashboard.tsx` 功能：
  - 统计卡片行：学习计划数、教程章节数、执行计划数、深度探索数、平均进度
  - 进行中的学习计划卡片网格（含进度条）
  - 活跃执行计划列表
  - 验证：页面显示至少 1 个学习计划（game-engine-dev）和统计数字

- [ ] **Step 3: 实现学习计划列表页**
  `LearningPlans.tsx` 功能：
  - 卡片网格展示所有学习计划
  - 每张卡片显示：名称、描述、目标、预计耗时、教程数、进度条
  - 点击卡片进入详情
  - 验证：点击卡片 URL 变为 `/plans/{planId}`

- [ ] **Step 4: 实现计划详情页**
  `PlanDetail.tsx` 功能：
  - 面包屑导航：学习计划 / {计划名}
  - 计划信息：名称、目标、预计耗时、创建日期、总进度条
  - 教程列表：按 order 排序，每项显示序号圆标 + 标题
  - 点击教程跳转 `/view?path={planId}/tutorials/{filename}`
  - 验证：教程列表数量与 `game-engine-dev/tutorials/` 下文件数一致

- [ ] **Step 5: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add Dashboard, LearningPlans and PlanDetail pages"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add Dashboard, LearningPlans and PlanDetail pages`

---

## Task 5: 实现进度标记系统

**Files:**
- Create: `Src/src/hooks/useProgress.ts`
- Modify: `Src/src/pages/PlanDetail.tsx`
- Modify: `Src/src/pages/Dashboard.tsx`
- Modify: `Src/src/pages/LearningPlans.tsx`

- [ ] **Step 1: 实现进度状态管理 Hook**
  `useProgress.ts` 功能：
  - 内部状态：`Record<planId, { completedTutorialIds: string[], lastAccessed: string }>`
  - 初始化时从 `localStorage` key `ai-learning-progress` 读取
  - 提供方法：
    - `toggleTutorial(planId, tutorialId)` — 切换完成状态
    - `getPlanProgress(planId)` — 返回完成百分比（基于已勾选教程数 / 总教程数）
    - `isCompleted(planId, tutorialId)` — 返回布尔值
  - 任何修改后同步到 `localStorage`
  - 验证：`grep "localStorage" Src/src/hooks/useProgress.ts` → 预期：匹配

- [ ] **Step 2: 在计划详情页添加教程勾选框**
  `PlanDetail.tsx` 修改：
  - 每个教程项左侧添加 checkbox
  - checkbox 状态绑定 `useProgress` 的 `isCompleted`
  - 点击切换完成状态
  - 页面顶部进度条实时反映当前计划的完成百分比（来自 useProgress，而非静态 JSON）
  - 验证：勾选两个教程后，进度条从 0% 变为对应百分比，刷新页面后状态保留

- [ ] **Step 3: 在列表页和仪表盘反映进度**
  `LearningPlans.tsx` + `Dashboard.tsx` 修改：
  - 卡片上的进度条优先显示用户实际进度（useProgress），无用户数据时 fallback 到 JSON 中的静态进度
  - 验证：仪表盘平均进度统计包含用户实际完成数据

- [ ] **Step 4: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add tutorial progress tracking with localStorage persistence"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add tutorial progress tracking with localStorage persistence`

---

## Task 6: 实现笔记标注系统

**Files:**
- Create: `Src/src/hooks/useNotes.ts`
- Create: `Src/src/components/NoteEditor.tsx`
- Create: `Src/src/components/NoteEditor.css`
- Modify: `Src/src/pages/MarkdownViewer.tsx`

- [ ] **Step 1: 实现笔记状态管理 Hook**
  `useNotes.ts` 功能：
  - 内部状态：`Record<documentPath, Array<{id: string, text: string, quote: string, createdAt: string, updatedAt: string}>>`
  - 初始化时从 `localStorage` key `ai-learning-notes` 读取
  - 提供方法：
    - `addNote(documentPath, text, quote)` — 添加新笔记
    - `updateNote(documentPath, noteId, text)` — 更新笔记内容
    - `deleteNote(documentPath, noteId)` — 删除笔记
    - `getNotes(documentPath)` — 获取某文档的所有笔记
  - 验证：`grep "localStorage" Src/src/hooks/useNotes.ts` → 预期：匹配

- [ ] **Step 2: 实现笔记编辑器组件**
  `NoteEditor.tsx` 功能：
  - 浮层/侧边面板形式，在阅读页面右侧展开
  - 显示当前文档的所有已有笔记列表
  - 每条笔记显示：引文片段（灰色引用块）+ 笔记文本 + 创建时间 + 编辑/删除按钮
  - 新增笔记表单：文本框（支持多行）+ "保存"按钮
  - 验证：`test -f Src/src/components/NoteEditor.tsx` → 预期：文件存在

- [ ] **Step 3: 集成笔记到 Markdown 阅读页**
  `MarkdownViewer.tsx` 修改：
  - 页面布局改为左侧 Markdown 内容（~65%）+ 右侧笔记面板（~35%，可折叠）
  - 笔记面板显示当前文档的所有笔记
  - 笔记面板顶部有 "添加笔记" 按钮，展开文本框
  - 验证：打开任意教程页面 → 右侧显示笔记面板 → 添加笔记 → 刷新页面 → 笔记保留

- [ ] **Step 4: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add note annotation system with localStorage persistence"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add note annotation system with localStorage persistence`

---

## Task 7: 实现内容渲染与辅助页面

**Files:**
- Create: `Src/src/pages/MarkdownViewer.tsx`
- Create: `Src/src/pages/ExecPlans.tsx`
- Create: `Src/src/pages/DeepDives.tsx`
- Create: `Src/src/pages/KnowledgeNotes.tsx`
- Create: `Src/src/utils/fetchMarkdown.ts`

- [ ] **Step 1: 实现 Markdown 获取工具**
  `fetchMarkdown.ts` 功能：
  - `fetchMarkdownContent(relativePath: string): Promise<string>`
  - 从父仓库加载：`fetch('../docs/${relativePath}')`
  - 验证：`test -f Src/src/utils/fetchMarkdown.ts` → 预期：文件存在

- [ ] **Step 2: 实现 Markdown 渲染页面**
  `MarkdownViewer.tsx` 功能：
  - 从 URL query param `path` 获取文档路径
  - 调用 `fetchMarkdownContent` 加载内容
  - 使用 `react-markdown` + `remark-gfm` 渲染
  - 样式：`markdown-content` 类，包含 h1-h3、p、pre、code、table、blockquote 样式
  - 验证：访问 `/view?path=game-engine-dev/tutorials/00-cpp-for-game-engines.md` → 预期：正确渲染 Markdown 内容

- [ ] **Step 3: 实现执行计划、深度探索、知识笔记页面**
  - `ExecPlans.tsx`: 按状态（进行中/已完成）分组展示执行计划卡片
  - `DeepDives.tsx`: 深度探索文章卡片网格，点击进入 MarkdownViewer
  - `KnowledgeNotes.tsx`: 知识笔记卡片网格，点击进入 MarkdownViewer
  - 验证：三个页面均正确加载数据并渲染

- [ ] **Step 4: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add Markdown viewer and auxiliary pages"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add Markdown viewer and auxiliary pages`

---

## Task 8: 构建生产版本并验证

**Files:**
- Modify: `Src/vite.config.ts`
- Modify: `Src/package.json`

- [ ] **Step 1: 更新 Vite 配置**
  `vite.config.ts` 修改：
  - `server.fs.allow` 包含父仓库 `../docs` 路径（dev 模式读取 Markdown）
  - `base: './'`（相对路径部署）
  - 验证：`grep "allow" Src/vite.config.ts` → 预期：匹配

- [ ] **Step 2: 执行扫描脚本确保数据最新**
  ```bash
  cd Src && npm run scan && npm run index
  ```
  - 验证：`test -f Src/public/data/learning-data.json && test -f Src/public/data/search-index.json` → 预期：两个文件均存在

- [ ] **Step 3: 生产构建**
  ```bash
  cd Src && npm run build
  ```
  - 验证：`test -d Src/dist && test -f Src/dist/index.html` → 预期：dist 目录和 index.html 存在

- [ ] **Step 4: TypeScript 类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：命令退出码为 0，无类型错误输出

- [ ] **Step 5: Commit**
  ```bash
  cd Src && git add -A && git commit -m "chore: configure build and verify production build"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`chore: configure build and verify production build`

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| git worktree 创建失败（Src 目录已存在） | 中 | 高 | 创建前检查 `Src` 是否存在；若存在则 `git worktree remove Src` 后重试 |
| 跨 worktree 读取 Markdown 文件 CORS/路径问题 | 中 | 高 | Vite dev server 配置 `server.fs.allow`；生产构建时将 docs 复制到 dist 或确保相对路径正确 |
| react-markdown 包体积过大 | 低 | 中 | 当前方案接受；如需优化可后期拆分为动态 import 或替换为轻量解析器 |
| localStorage 数据丢失 | 低 | 中 | 笔记/进度数据可接受丢失风险；后期可导出 JSON 备份/恢复 |
| 中文分词效果不佳 | 中 | 低 | 搜索索引使用简单按字分词 + 按空格分词；足够满足基本搜索需求 |

---

## 验收标准

- [ ] `git worktree list` 显示 `Src` 是有效 worktree
- [ ] `cd Src && npm run dev` 成功启动，访问 `http://localhost:5173` 显示仪表盘
- [ ] 仪表盘显示正确的统计数字（学习计划数 ≥1、教程数 ≥18、执行计划数 ≥1）
- [ ] 学习计划列表页显示所有计划卡片，含进度条
- [ ] 点击计划卡片进入详情页，显示该计划的全部教程列表
- [ ] 教程项可勾选完成，勾选后进度条实时更新，刷新页面状态保留（localStorage）
- [ ] 点击教程可正确渲染 Markdown 内容
- [ ] Markdown 阅读页右侧显示笔记面板，可添加/编辑/删除笔记，刷新后保留
- [ ] 全局搜索可搜索到教程和文章内容，点击结果正确跳转
- [ ] 执行计划、深度探索、知识笔记页面正确列出内容
- [ ] `npm run build` 成功生成 `dist/`，`npx tsc --noEmit` 无错误
- [ ] 所有 feature-list.json 中 `passes` 为 `true`

---

## 执行记忆

> 详见 `memory.md` — 执行过程中由 `executing-plans` skill 填充。
> 跨会话恢复时优先读取此文件了解当前状态。

## 进度日志

| 日期 | 事件 | 操作者 |
|------|------|--------|
| 2026-05-20 | 计划创建 | — |
