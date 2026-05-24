# Exec Plan: 学习工作区前端展示面板

> 完整执行计划 — 跨模块改动、新功能开发。
> **⚡ 零占位符：禁止 TBD / TODO / implement later / add error handling 等模糊描述。**
> **For agentic workers:** 使用 `executing-plans` skill 按 Task 逐个执行。

---

**Goal:** 使用 git worktree 在 `Src/` 目录下创建基于 TypeScript + React + Vite 的前端项目，可视化展示 AI_Learning 工作区中的学习计划、教程内容、执行计划状态和知识笔记，提供学习进度标记、笔记标注和全文搜索功能。

**Architecture:** 前端使用 React 18 + TypeScript + Vite 构建 SPA。构建时扫描 `docs/` 生成 JSON 数据索引和搜索倒排索引。运行时加载静态索引渲染页面。用户状态（进度、笔记）持久化到 `localStorage`。搜索基于预构建倒排索引在客户端完成。

**Tech Stack:** TypeScript 5.4 / React 18 / Vite 5 / react-router-dom / react-markdown / remark-gfm / CSS Modules

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
│  │  (构建时生成静态索引)    │  │  progress / notes      │                │
│  └────────────────────────┘  └────────────────────────┘                │
├─────────────────────────────────────────────────────────────────────────┤
│  Build Pipeline                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  scan-learning-data.ts  →  扫描 docs/  →  JSON                      │  │
│  │  build-search-index.ts  →  分词 + 倒排索引  →  search-index.json │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**数据流：**
1. 构建时：`scan-learning-data.ts` 扫描 Markdown 源 → `public/data/learning-data.json`
2. 构建时：`build-search-index.ts` 对内容分词 → `public/data/search-index.json`
3. 运行时：`useLearningData` Hook 加载 `learning-data.json` → 各页面渲染
4. 用户操作：`useProgress` / `useNotes` 更新状态 → 同步到 `localStorage`
5. 搜索：`useSearch` 读取 `search-index.json` → 客户端匹配 → 结果列表

---

## Task 1: 项目骨架初始化 → 拆分

> 此 Task 较复杂（17 步、11 个文件），详细步骤见 [tasks/task-01-project-scaffold.md](tasks/task-01-project-scaffold.md)

**Files (概要):**
- Create: `Src/package.json`, `Src/tsconfig.json`, `Src/tsconfig.node.json`, `Src/vite.config.ts`, `Src/index.html`
- Create: `Src/src/main.tsx`, `Src/src/App.tsx`, `Src/src/App.css`, `Src/src/vite-env.d.ts`
- Create: `Src/.gitignore`
- Modify: `.gitignore`（追加 `Src/node_modules/` 和 `Src/dist/`）

执行时请读取 [tasks/task-01-project-scaffold.md](tasks/task-01-project-scaffold.md) 获取完整步骤和验证命令。

---

## Task 2: 构建数据扫描与搜索索引脚本 → 拆分

> 脚本代码较长（~190 行），详细步骤见 [tasks/task-02-data-scripts.md](tasks/task-02-data-scripts.md)

**Files (概要):**
- Create: `Src/src/types/index.ts`
- Create: `Src/scripts/scan-learning-data.ts`
- Create: `Src/scripts/build-search-index.ts`
- Modify: `Src/package.json`（添加 scripts）

### 内联步骤：TypeScript 类型定义

> 类型定义即接口契约，保留完整内容。

- [ ] **Step 1: 定义 TypeScript 类型**
  创建 `Src/src/types/index.ts`：

  ```typescript
  export interface Tutorial {
    id: string;
    title: string;
    filename: string;
    order: number;
  }

  export interface LearningPlan {
    id: string;
    name: string;
    description: string;
    createdDate: string;
    totalHours: number;
    targetLevel: string;
    progress: number;
    tutorials: Tutorial[];
    planPath: string;
  }

  export interface ExecPlan {
    id: string;
    name: string;
    summary: string;
    status: 'active' | 'completed';
    createdDate: string;
    path: string;
  }

  export interface DeepDive {
    id: string;
    title: string;
    path: string;
  }

  export interface KnowledgeNote {
    id: string;
    title: string;
    path: string;
  }

  export interface LearningData {
    learningPlans: LearningPlan[];
    execPlans: ExecPlan[];
    deepDives: DeepDive[];
    knowledgeNotes: KnowledgeNote[];
  }

  export interface SearchDocument {
    path: string;
    title: string;
    preview: string;
  }

  export interface SearchIndex {
    terms: Record<string, Array<{ path: string; positions: number[] }>>;
    documents: SearchDocument[];
  }

  export interface UserProgress {
    [planId: string]: {
      completedTutorialIds: string[];
      lastAccessed: string;
    };
  }

  export interface Note {
    id: string;
    text: string;
    quote: string;
    createdAt: string;
    updatedAt: string;
  }

  export type UserNotes = Record<string, Note[]>;
  ```
  - 验证：`npx tsc --noEmit` → 预期：退出码 0，无类型错误

> 后续步骤（扫描脚本、搜索索引脚本、npm scripts 配置、验证）见 [tasks/task-02-data-scripts.md](tasks/task-02-data-scripts.md)

---

## Task 3: 实现布局与导航系统

> 应用代码 Task——组件和页面按规格实现，CSS 按视觉规格描述。

**Files:**
- Create: `Src/src/components/Layout.tsx`
- Create: `Src/src/components/Sidebar.tsx`
- Create: `Src/src/components/Sidebar.css`
- Create: `Src/src/components/SearchBar.tsx`
- Create: `Src/src/components/SearchBar.css`
- Create: `Src/src/pages/Dashboard.tsx`（占位）
- Create: `Src/src/pages/LearningPlans.tsx`（占位）
- Create: `Src/src/pages/PlanDetail.tsx`（占位）
- Create: `Src/src/pages/ExecPlans.tsx`（占位）
- Create: `Src/src/pages/DeepDives.tsx`（占位）
- Create: `Src/src/pages/KnowledgeNotes.tsx`（占位）
- Create: `Src/src/pages/MarkdownViewer.tsx`（占位）
- Modify: `Src/src/App.tsx`（替换为路由版本）

- [ ] **Step 1: 实现 Layout 组件**
  - 文件：`Src/src/components/Layout.tsx`
  - 签名：`export default function Layout()`
  - 关键 import：`Outlet` from `'react-router-dom'`；`Sidebar` from `'./Sidebar'`
  - 行为：渲染左侧 `<Sidebar />` + 右侧 `<main className="app-main"><Outlet /></main>`，包裹在 `div.app-layout` 中
  - 约束：无额外 props；纯布局组件，不含业务逻辑
  - 验证：`test -f Src/src/components/Layout.tsx` → 预期：文件存在

- [ ] **Step 2: 实现 Sidebar 导航组件**
  - 文件：`Src/src/components/Sidebar.tsx` + `Src/src/components/Sidebar.css`
  - 签名：`export default function Sidebar()`
  - 关键 import：`NavLink` from `'react-router-dom'`；`SearchBar` from `'./SearchBar'`
  - 行为：
    - 顶部显示 "AI Learning" 标题（`.sidebar-logo`）
    - 中间渲染 5 个 `<NavLink>` 导航项：仪表盘(`/`, end)、学习计划(`/plans`)、执行计划(`/exec-plans`)、深度探索(`/deep-dives`)、知识笔记(`/knowledge-notes`)
    - 底部嵌入 `<SearchBar />`
    - NavLink 使用 `className` callback：`isActive` 时添加 `.active` class
  - 约束：导航项定义在组件内常量数组 `NAV_ITEMS: Array<{to, label, end}>`

  创建 `Src/src/components/Sidebar.css`，视觉规格：

  - `.sidebar-logo`：下边框分隔（1px solid #333），下 margin 16px；h1 字号 1.1rem，白色
  - `.sidebar-nav`：纵向 flex 列，gap 4px
  - `.nav-item`：block 显示，padding 10/12，圆角 6px，字号 0.9rem；默认文字 #a0a0b8，hover 背景 #2a2a4a + 文字 #e0e0f0，active 背景 #3a3a6a + 文字白色；0.15s transition
  - 验证：`test -f Src/src/components/Sidebar.tsx && test -f Src/src/components/Sidebar.css` → 预期：两个文件均存在

- [ ] **Step 3: 更新 App.tsx 为完整路由版本**
  - 文件：`Src/src/App.tsx`
  - 签名：`export default function App()`
  - 关键 import：`Routes`, `Route` from `'react-router-dom'`；`Layout` from `'./components/Layout'`；7 个页面组件 from `'./pages/<Name>'`
  - 行为：渲染 `<Routes>` 包裹的 7 条路由，均以 `<Layout />` 为父路由：
    - `/` → `<Dashboard />`（index）
    - `/plans` → `<LearningPlans />`
    - `/plans/:planId` → `<PlanDetail />`
    - `/exec-plans` → `<ExecPlans />`
    - `/deep-dives` → `<DeepDives />`
    - `/knowledge-notes` → `<KnowledgeNotes />`
    - `/view` → `<MarkdownViewer />`
  - 约束：使用 `react-router-dom` v6 `<Routes>/<Route>` API；Layout 路由包裹所有子路由
  - 验证：`grep 'import.*Layout' Src/src/App.tsx` → 预期：匹配到行

- [ ] **Step 4: 创建占位页面**
  创建 `Src/src/pages/` 目录，为以下 7 个文件各创建一个最小占位组件，避免 tsc 报导入错误：
  - `Dashboard.tsx` — `export default function Dashboard() { return <div>Dashboard</div>; }`
  - `LearningPlans.tsx` — `export default function LearningPlans() { return <div>LearningPlans</div>; }`
  - `PlanDetail.tsx` — `export default function PlanDetail() { return <div>PlanDetail</div>; }`
  - `ExecPlans.tsx` — `export default function ExecPlans() { return <div>ExecPlans</div>; }`
  - `DeepDives.tsx` — `export default function DeepDives() { return <div>DeepDives</div>; }`
  - `KnowledgeNotes.tsx` — `export default function KnowledgeNotes() { return <div>KnowledgeNotes</div>; }`
  - `MarkdownViewer.tsx` — `export default function MarkdownViewer() { return <div>MarkdownViewer</div>; }`

  - 验证：`ls Src/src/pages/ | wc -l` → 预期：≥7

- [ ] **Step 5: TypeScript 类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：退出码 0，无类型错误

- [ ] **Step 6: 实现 SearchBar 组件**
  - 文件：`Src/src/components/SearchBar.tsx` + `Src/src/components/SearchBar.css`
  - 签名：`export default function SearchBar()`
  - 关键 import：`useState`, `useEffect`, `useRef` from `'react'`；`useNavigate` from `'react-router-dom'`；`SearchIndex` from `'../types'`
  - 行为：
    - 组件挂载时 `fetch('/data/search-index.json')` 加载搜索索引
    - 渲染一个 `<input>` 搜索框，`placeholder="搜索..."`，`className="searchbar-input"`
    - `onChange` 时通过 300ms debounce 触发搜索
    - 搜索逻辑：对 query 按英文单词 + 中文字 + 中文 bigram 分词，在 `index.terms` 中匹配，收集匹配文档路径，从 `index.documents` 取对应文档（最多 10 条）
    - query 长度 < 2 时不搜索，清空结果
    - 匹配结果显示在下拉列表 `.searchbar-dropdown` 中，每项显示标题和最多 120 字符预览
    - 点击结果项：`navigate('/view?path=' + encodeURIComponent(doc.path))`，关闭下拉，清空输入
    - `onFocus` 时有结果则显示下拉；`onBlur` 时 200ms 后关闭下拉（给 click 事件时间）
    - 包裹在 `div.searchbar-wrapper` 中
  - 约束：debounce 用 `useRef<ReturnType<typeof setTimeout>>` 管理；搜索索引为 `SearchIndex | null` 初始状态

  创建 `Src/src/components/SearchBar.css`，视觉规格：

  - `.searchbar-wrapper`：relative 定位，padding 0 12px 16px
  - `.searchbar-input`：全宽，padding 8/12，边框 1px #444 圆角 6px，背景 #2a2a3e 文字 #e0e0e0，字号 0.85rem；focus 时边框 #6a6aff
  - `.searchbar-dropdown`：absolute 定位，left/right 12px top 100%，背景 #1e1e32 边框 1px #444 圆角 6px，max-height 360px 可滚动，z-index 100
  - `.searchbar-result`：padding 10/12，pointer 光标，底边框 1px #2a2a3e；hover 背景 #2a2a4a
  - `.searchbar-result-title`：字号 0.85rem 文字 #e0e0f0，下 margin 4px
  - `.searchbar-result-preview`：字号 0.75rem 文字 #888，单行截断省略号
  - 验证：`test -f Src/src/components/SearchBar.tsx && test -f Src/src/components/SearchBar.css` → 预期：两个文件均存在

- [ ] **Step 7: TypeScript 类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：退出码 0，无类型错误

- [ ] **Step 8: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add sidebar navigation, layout and global search bar"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add sidebar navigation, layout and global search bar`

---

## Task 4: 实现仪表盘与学习计划页面

> 应用代码 Task——Hook 和页面按规格实现，CSS 按视觉规格描述。

**Files:**
- Create: `Src/src/hooks/useLearningData.ts`
- Modify: `Src/src/pages/Dashboard.tsx`（替换占位）
- Modify: `Src/src/pages/LearningPlans.tsx`（替换占位）
- Modify: `Src/src/pages/PlanDetail.tsx`（替换占位）
- Modify: `Src/src/App.css`（追加统计卡片、计划卡片、进度条、面包屑、教程列表样式）

- [ ] **Step 1: 实现 useLearningData Hook**
  - 文件：`Src/src/hooks/useLearningData.ts`
  - 签名：`export function useLearningData(): { data: LearningData | null; loading: boolean; error: string | null }`
  - 关键 import：`useState`, `useEffect` from `'react'`；`LearningData` from `'../types'`
  - 行为：
    - 组件挂载时 `fetch('/data/learning-data.json')` 加载数据
    - 响应非 ok 时设置 `error` 为 `'HTTP ' + status`
    - 成功时设置 `data` 为 JSON 解析结果
    - finally 设置 `loading = false`
  - 约束：空依赖数组（仅挂载时执行）；返回 `{ data, loading, error }`
  - 验证：`test -f Src/src/hooks/useLearningData.ts` → 预期：文件存在

- [ ] **Step 2: 实现 Dashboard 页面**
  - 文件：`Src/src/pages/Dashboard.tsx`
  - 签名：`export default function Dashboard()`
  - 关键 import：`useLearningData` from `'../hooks/useLearningData'`；`Link` from `'react-router-dom'`
  - 行为：
    - `loading === true` 时显示 `<div className="page-loading">加载中...</div>`
    - `error` 非空时显示 `<div className="page-error">加载失败: {error}</div>`
    - `data === null` 时返回 null
    - 计算统计指标：
      - `totalTutorials`：所有 `learningPlans` 中 `tutorials.length` 之和
      - `avgProgress`：所有 `learningPlans` 的 `progress` 平均值（四舍五入整数），无计划时为 0
    - 渲染区域 1 — 统计卡片（`.stats-grid`）：
      - 5 个 `.stat-card`：学习计划数、教程章节数、执行计划数、深度探索数、平均进度百分比
      - 每个卡片包含 `.stat-value`（数值）和 `.stat-label`（标签）
    - 渲染区域 2 — 进行中的学习计划（标题 "进行中的学习计划"）：
      - `.card-grid` 中每个计划渲染为一个 `<Link to={'/plans/' + plan.id}>` 卡片 `.plan-card`
      - 卡片内容：标题 `<h4>`、描述 `.plan-desc`（最多 2 行截断）、meta 行（章节数、预计时长）、进度条 `.progress-bar` > `.progress-fill`（width 由 `plan.progress` 决定）、进度文字 `.progress-text`
    - 渲染区域 3 — 活跃执行计划（标题 "活跃执行计划"）：
      - 同上卡片网格，每卡片显示名称、摘要、状态 badge `.status-badge.status-active`
  - 约束：无分页；所有计划一次性展示

  - 验证：`grep 'useLearningData' Src/src/pages/Dashboard.tsx` → 预期：匹配到行

- [ ] **Step 3: 更新 App.css 添加统计卡片和计划卡片样式**
  在 `Src/src/App.css` 末尾追加，视觉规格：

  - `.page-title`：字号 1.5rem，下 margin 20px，深色 `#1a1a2e`
  - `.section-title`：字号 1.1rem，margin 24px 0 12px，`#333`
  - `.stats-grid`：响应式 grid，列宽 ≥160px auto-fill，gap 16px，下 margin 24px
  - `.stat-card`：白色背景圆角 10px，padding 20px，居中文字，浅阴影 `0 1px 3px rgba(0,0,0,0.08)`
  - `.stat-value`：字号 2rem 粗体 700，`#1a1a2e`
  - `.stat-label`：字号 0.85rem，`#888`，上 margin 4px
  - `.card-grid`：响应式 grid，列宽 ≥280px auto-fill，gap 16px
  - `.plan-card`：白色背景圆角 10px，padding 20px，浅阴影；hover 阴影加深 `0 4px 12px rgba(0,0,0,0.12)`，0.15s transition；作为 Link 时无下划线，颜色继承
  - `.plan-card h4`：字号 1rem，`#1a1a2e`，下 margin 6px
  - `.plan-desc`：字号 0.85rem，`#666`，下 margin 10px；最多 2 行截断（`-webkit-line-clamp: 2`）
  - `.plan-meta`：横向 flex，gap 12px，字号 0.8rem，`#999`，下 margin 8px
  - `.progress-bar`：高 6px，背景 `#e8e8ef`，圆角 3px，overflow hidden，下 margin 4px
  - `.progress-fill`：高 100%，背景 `#4a4aff`，圆角 3px，width 0.3s transition
  - `.progress-text`：字号 0.75rem，`#888`，右对齐
  - `.status-badge`：inline-block，padding 3/10，圆角 12px，字号 0.75rem
  - `.status-active`：背景 `#e8f5e9`，文字 `#2e7d32`
  - `.page-loading`、`.page-error`：居中文字，padding 60px 20px，`#888`
  - 验证：`grep 'stats-grid' Src/src/App.css` → 预期：匹配到行

- [ ] **Step 4: 实现 LearningPlans 页面**
  - 文件：`Src/src/pages/LearningPlans.tsx`
  - 签名：`export default function LearningPlans()`
  - 关键 import：`Link` from `'react-router-dom'`；`useLearningData` from `'../hooks/useLearningData'`
  - 行为：
    - 与 Dashboard 相同的 loading / error / null 处理
    - 标题 "学习计划"（`.page-title`）
    - `.card-grid` 中每个计划渲染为 `<Link to={'/plans/' + plan.id}>` 卡片
    - 卡片内容：标题、描述、meta（章节数、预计时长、目标级别）、进度条 + 进度百分比
  - 约束：布局与 Dashboard 的计划卡片区域一致，复用相同 CSS class

  - 验证：`grep 'useLearningData' Src/src/pages/LearningPlans.tsx` → 预期：匹配到行

- [ ] **Step 5: 实现 PlanDetail 页面**
  - 文件：`Src/src/pages/PlanDetail.tsx`
  - 签名：`export default function PlanDetail()`
  - 关键 import：`useParams`, `Link`, `useNavigate` from `'react-router-dom'`；`useLearningData` from `'../hooks/useLearningData'`
  - 行为：
    - 从 `useParams<{ planId: string }>()` 获取 `planId`
    - 在 `data.learningPlans` 中查找 `p.id === planId` 的计划
    - 计划不存在时显示 `<div className="page-error">计划未找到: {planId}</div>`
    - 渲染面包屑：`<Link to="/plans">学习计划</Link>` + 分隔符 + 计划名称（`.breadcrumb`）
    - 渲染计划信息：标题、描述、meta（预计时长、创建日期、目标级别）
    - 渲染进度条和进度百分比
    - 渲染教程目录列表（`.tutorial-list`）：每个教程一个 `.tutorial-item`，包含序号圆标（`.tutorial-order`）和标题（`.tutorial-title`）
    - 点击教程项：`navigate('/view?path=' + encodeURIComponent(plan.planPath + 'tutorials/' + tut.filename))`
  - 约束：教程列表按 `tut.order` 排序（已在数据层排序）

  - 验证：`grep 'tutorial-list' Src/src/pages/PlanDetail.tsx` → 预期：匹配到行（或者 CSS 中有对应样式）

- [ ] **Step 6: 追加教程列表和面包屑样式到 App.css**
  在 `Src/src/App.css` 末尾追加，视觉规格：

  - `.breadcrumb`：字号 0.85rem，`#888`，下 margin 12px；内链 `#4a4aff` 无下划线，hover 加下划线
  - `.breadcrumb-sep`：左右 margin 8px
  - `.tutorial-list`：纵向 flex 列，gap 2px
  - `.tutorial-item`：横向 flex 居中对齐，gap 12px，padding 12/16，白色背景圆角 8px，pointer 光标；hover 背景 `#f0f0ff`，0.15s transition
  - `.tutorial-order`：28×28px 圆形（`#4a4aff` 背景白色文字），flex 居中，字号 0.8rem，flex-shrink: 0
  - `.tutorial-title`：字号 0.9rem，`#333`
  - 验证：`grep 'tutorial-list' Src/src/App.css` → 预期：匹配到行

- [ ] **Step 7: TypeScript 类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：退出码 0

- [ ] **Step 8: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add Dashboard, LearningPlans and PlanDetail pages"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add Dashboard, LearningPlans and PlanDetail pages`

---

## Task 5: 实现进度标记系统

> 应用代码 Task——Hook 和页面修改按规格实现。

**Files:**
- Create: `Src/src/hooks/useProgress.ts`
- Modify: `Src/src/pages/PlanDetail.tsx`（添加 checkbox 和进度联动）
- Modify: `Src/src/pages/Dashboard.tsx`（使用用户实际进度）
- Modify: `Src/src/pages/LearningPlans.tsx`（使用用户实际进度）
- Modify: `Src/src/App.css`（追加 checkbox 样式）

- [ ] **Step 1: 实现 useProgress Hook**
  - 文件：`Src/src/hooks/useProgress.ts`
  - 签名：
    ```
    export function useProgress(): {
      progress: UserProgress;
      toggleTutorial: (planId: string, tutorialId: string) => void;
      getPlanProgress: (planId: string, totalTutorials: number) => number;
      isCompleted: (planId: string, tutorialId: string) => boolean;
    }
    ```
  - 关键 import：`useState`, `useCallback` from `'react'`；`UserProgress` from `'../types'`
  - 行为：
    - 初始化时从 `localStorage.getItem('ai-learning-progress')` 读取进度，JSON 解析失败返回 `{}`
    - `toggleTutorial(planId, tutorialId)`：读取最新 localStorage 数据，取 `planId` 对应的记录（无则初始化为 `{completedTutorialIds: [], lastAccessed: ''}`），若 `tutorialId` 已存在则移除，否则追加；更新 `lastAccessed` 为当前 ISO 时间；写回 localStorage 并更新 state
    - `getPlanProgress(planId, totalTutorials)`：`totalTutorials === 0` 返回 0；否则返回 `Math.round(completedTutorialIds.length / totalTutorials * 100)`
    - `isCompleted(planId, tutorialId)`：返回 `progress[planId]?.completedTutorialIds.includes(tutorialId) ?? false`
  - 约束：每次写入前重新从 localStorage 读取最新值（避免闭包陷阱）；localStorage key 为 `'ai-learning-progress'`
  - 验证：`grep 'localStorage' Src/src/hooks/useProgress.ts` → 预期：匹配到行

- [ ] **Step 2: 在 PlanDetail 页面添加教程勾选框**
  修改 `Src/src/pages/PlanDetail.tsx`：
  - 添加 import：`import { useProgress } from '../hooks/useProgress';`
  - 在组件内调用：`const { toggleTutorial, getPlanProgress, isCompleted } = useProgress();`
  - 计算用户进度：`const userProgress = getPlanProgress(plan.id, plan.tutorials.length);`
  - 将页面中的进度条和百分比从 `plan.progress` 改为使用 `userProgress`
  - 将教程列表中每个 `.tutorial-item` 改为以下结构（伪代码）：
    ```
    <div className="tutorial-item">
      <input type="checkbox"
        checked={isCompleted(plan.id, tut.id)}
        onChange={() => toggleTutorial(plan.id, tut.id)}
        className="tutorial-checkbox" />
      <span className="tutorial-order">{idx + 1}</span>
      <span className="tutorial-title"
        style={{ textDecoration: isCompleted(plan.id, tut.id) ? 'line-through' : 'none' }}
        onClick={() => navigate('/view?path=...')}>
        {tut.title}
      </span>
    </div>
    ```
  - 约束：checkbox 在序号圆标左侧；完成项标题加删除线；点击标题仍可跳转阅读
  - 验证：`grep 'useProgress' Src/src/pages/PlanDetail.tsx` → 预期：匹配到行

- [ ] **Step 3: 更新 Dashboard 和 LearningPlans 使用实时进度**
  修改 `Src/src/pages/Dashboard.tsx`：
  - 添加 import：`import { useProgress } from '../hooks/useProgress';`
  - 调用 `const { getPlanProgress } = useProgress();`
  - 每个计划卡片的进度百分比优先使用 `getPlanProgress(plan.id, plan.tutorials.length)`，仅当返回 0 且 `plan.progress > 0` 时 fallback 到 `plan.progress`
  - 统计卡片中的平均进度优先使用用户实际进度的平均值（无用户进度时 fallback 到静态进度）

  修改 `Src/src/pages/LearningPlans.tsx`：
  - 同上逻辑：进度优先 `getPlanProgress`，fallback 到 `plan.progress`
  - 验证：`grep 'useProgress' Src/src/pages/Dashboard.tsx && grep 'useProgress' Src/src/pages/LearningPlans.tsx` → 预期：两文件均匹配到

- [ ] **Step 4: 追加 checkbox 样式到 App.css**
  在 `Src/src/App.css` 末尾追加，视觉规格：

  - `.tutorial-checkbox`：18×18px，pointer 光标，accent-color `#4a4aff`，flex-shrink: 0
  - 验证：`grep 'tutorial-checkbox' Src/src/App.css` → 预期：匹配到行

- [ ] **Step 5: TypeScript 类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：退出码 0

- [ ] **Step 6: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add tutorial progress tracking with localStorage persistence"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add tutorial progress tracking with localStorage persistence`

---

## Task 6: 实现笔记标注系统

> 应用代码 Task——Hook、组件和页面按规格实现。CSS 为配置类，写完整内容。

**Files:**
- Create: `Src/src/hooks/useNotes.ts`
- Create: `Src/src/components/NoteEditor.tsx`
- Create: `Src/src/components/NoteEditor.css`
- Modify: `Src/src/pages/MarkdownViewer.tsx`（替换占位为功能实现）
- Modify: `Src/src/App.css`（追加 Markdown 布局和笔记面板样式）

- [ ] **Step 1: 实现 useNotes Hook**
  - 文件：`Src/src/hooks/useNotes.ts`
  - 签名：
    ```
    export function useNotes(): {
      notes: UserNotes;
      addNote: (documentPath: string, text: string, quote?: string) => void;
      updateNote: (documentPath: string, noteId: string, text: string) => void;
      deleteNote: (documentPath: string, noteId: string) => void;
      getNotes: (documentPath: string) => Note[];
    }
    ```
  - 关键 import：`useState`, `useCallback` from `'react'`；`Note`, `UserNotes` from `'../types'`
  - 行为：
    - 初始化从 `localStorage.getItem('ai-learning-notes')` 读取，解析失败返回 `{}`
    - `addNote(documentPath, text, quote)`：读取最新 localStorage，生成 note id（`Date.now().toString(36) + Math.random().toString(36).slice(2, 8)`），创建 `Note` 对象（含 id, text, quote, createdAt, updatedAt），追加到对应 documentPath 的数组，写回 localStorage
    - `updateNote(documentPath, noteId, text)`：查找并更新 text 和 updatedAt，写回
    - `deleteNote(documentPath, noteId)`：过滤掉对应 noteId，写回
    - `getNotes(documentPath)`：返回 `notes[documentPath] || []`
  - 约束：每次写入前重新从 localStorage 读取最新值；localStorage key 为 `'ai-learning-notes'`
  - 验证：`grep 'localStorage' Src/src/hooks/useNotes.ts` → 预期：匹配到行

- [ ] **Step 2: 实现 NoteEditor 组件**
  - 文件：`Src/src/components/NoteEditor.tsx` + `Src/src/components/NoteEditor.css`
  - 签名：`export default function NoteEditor({ documentPath, notes, onAdd, onUpdate, onDelete }: Props)`
  - Props 类型：
    ```typescript
    interface Props {
      documentPath: string;
      notes: Note[];
      onAdd: (documentPath: string, text: string) => void;
      onUpdate: (documentPath: string, noteId: string, text: string) => void;
      onDelete: (documentPath: string, noteId: string) => void;
    }
    ```
  - 关键 import：`useState` from `'react'`；`Note` from `'../types'`
  - 行为：
    - 状态管理：`newText`（新笔记文本）、`editingId`（正在编辑的笔记 id，null 表示不在编辑）、`editText`（编辑中的文本）
    - 顶部标题 "笔记"（`.note-editor-title`）
    - 新增区域 `.note-add`：`<textarea>`（placeholder="写笔记..."，rows=3，className="note-textarea"）+ "保存" 按钮（`.note-btn.note-btn-add`）
      - 点保存：若 `newText.trim()` 非空，调 `onAdd(documentPath, newText.trim())`，清空 `newText`
    - 笔记列表 `.note-list`：notes 为空时显示 "暂无笔记"（`.note-empty`）
    - 每条笔记 `.note-item`：
      - 显示创建日期（`new Date(note.createdAt).toLocaleDateString('zh-CN')`，`.note-meta`）
      - 非编辑态：显示 `note.text`（`.note-text`）+ "编辑"/"删除" 按钮
        - 点编辑：`setEditingId(note.id); setEditText(note.text);`
        - 点删除：`onDelete(documentPath, note.id)`
      - 编辑态：显示 `<textarea>`（value=editText）+ "保存"/"取消" 按钮
        - 点保存：若 `editText.trim()` 非空，调 `onUpdate(documentPath, noteId, editText.trim())`，退出编辑态
        - 点取消：`setEditingId(null); setEditText('');`
  - 约束：所有按钮使用 `.note-btn` + 语义变体 class（`.note-btn-add`, `.note-btn-save`, `.note-btn-cancel`, `.note-btn-edit`, `.note-btn-delete`）

  创建 `Src/src/components/NoteEditor.css`，视觉规格：

  - `.note-editor`：padding 16px
  - `.note-editor-title`：字号 1rem，下 margin 12px，`#333`
  - `.note-add`：下 margin 16px
  - `.note-textarea`：全宽，padding 8/10，边框 1px `#ddd` 圆角 6px，字号 0.85rem，可纵向 resize；focus 边框 `#4a4aff`
  - `.note-btn`：padding 4/12，无边框圆角 4px，字号 0.8rem，pointer 光标，上 margin 6px 右 margin 6px
  - `.note-btn-add`、`.note-btn-save`：背景 `#4a4aff` 白色文字
  - `.note-btn-cancel`：背景 `#e0e0e0`，`#333`
  - `.note-btn-edit`：背景 `#e8e8ff`，`#4a4aff`
  - `.note-btn-delete`：背景 `#ffe8e8`，`#d32f2f`
  - `.note-list`：纵向 flex 列，gap 10px
  - `.note-empty`：`#aaa` 字号 0.85rem，居中，padding 20px
  - `.note-item`：padding 10px，背景 `#f8f8ff` 圆角 6px，边框 1px `#e8e8f0`
  - `.note-meta`：字号 0.7rem，`#aaa`，下 margin 4px
  - `.note-text`：字号 0.85rem，`#333`，行高 1.5，pre-wrap
  - `.note-actions`：上 margin 4px
  - 验证：`test -f Src/src/components/NoteEditor.tsx && test -f Src/src/components/NoteEditor.css` → 预期：两个文件均存在

- [ ] **Step 3: 实现 MarkdownViewer 页面（替换占位）**
  - 文件：`Src/src/pages/MarkdownViewer.tsx`
  - 签名：`export default function MarkdownViewer()`
  - 关键 import：`useState`, `useEffect` from `'react'`；`useSearchParams` from `'react-router-dom'`；`ReactMarkdown` from `'react-markdown'`；`remarkGfm` from `'remark-gfm'`；`useNotes` from `'../hooks/useNotes'`；`NoteEditor` from `'../components/NoteEditor'`
  - 行为：
    - 从 `useSearchParams()` 获取 `path` 参数作为 `docPath`
    - 状态：`content`（Markdown 文本）、`loading`、`error`、`notesPanelOpen`（默认 true）
    - 挂载时：若 `docPath` 非空，`fetch('/api/markdown?path=' + encodeURIComponent(docPath))` 获取 Markdown 内容；非 ok 响应的 status 设为 error
    - 调用 `useNotes()` 获取 `{ addNote, updateNote, deleteNote, getNotes }`
    - `docNotes = getNotes(docPath)`
    - 布局为 `.markdown-layout`：
      - 左侧 `.markdown-content`：loading/error 状态展示，否则 `<ReactMarkdown remarkPlugins={[remarkGfm]}>`
      - 右侧 `.markdown-notes-panel`（open/closed 切换）：toggle 按钮 + `notesPanelOpen` 时渲染 `<NoteEditor>`
    - toggle 按钮文字：`notesPanelOpen ? '收起' : '笔记'`
  - 约束：`ReactMarkdown` 的 `remarkPlugins` 必须包含 `remarkGfm`

- [ ] **Step 4: 追加 Markdown 阅读页和笔记面板样式到 App.css**
  在 `Src/src/App.css` 末尾追加，视觉规格：

  - `.markdown-layout`：横向 flex，高度 `calc(100vh - 48px)`
  - `.markdown-content`：flex: 1，可滚动，padding 24px，白色背景圆角 10px
  - `.markdown-content h1`：字号 1.6rem，下 margin 16px，`#1a1a2e`
  - `.markdown-content h2`：字号 1.3rem，margin 24/0/12，`#1a1a2e`
  - `.markdown-content h3`：字号 1.1rem，margin 20/0/8，`#333`
  - `.markdown-content p`：行高 1.7，margin 8/0，`#444`
  - `.markdown-content pre`：背景 `#1e1e2e` 文字 `#e0e0e0`，padding 16px，圆角 8px，可横向滚动，字号 0.85rem，margin 12/0
  - `.markdown-content code`（内联）：背景 `#f0f0f5`，padding 2/6，圆角 4px，字号 0.85rem
  - `.markdown-content pre code`：无背景无 padding
  - `.markdown-content table`：全宽，折叠边框，margin 12/0；th/td padding 8/12，字号 0.9rem；th 背景 `#f5f5f8`
  - `.markdown-content blockquote`：左边框 4px `#4a4aff`，padding 8/16，背景 `#f8f8ff`，`#555`
  - `.markdown-notes-panel`：宽 320px flex-shrink 0，白色背景，左边框 1px `#e8e8ef`，可滚动，width 0.2s transition；`.closed` 时宽 50px
  - `.notes-toggle`：全宽，padding 8px，无边框，背景 `#f5f5f8`，pointer 光标，字号 0.85rem，`#4a4aff`；hover 背景 `#e8e8ff`
  - 验证：`grep 'markdown-layout' Src/src/App.css` → 预期：匹配到行

- [ ] **Step 5: TypeScript 类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：退出码 0

- [ ] **Step 6: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add note annotation system with localStorage persistence"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add note annotation system with localStorage persistence`

---

## Task 7: 实现内容渲染与辅助页面

> 混合 Task——配置文件和中间件写完整内容；页面组件写规格。

**Files:**
- Create: `Src/src/utils/fetchMarkdown.ts`
- Modify: `Src/vite.config.ts`（添加 Markdown API 中间件）
- Modify: `Src/src/pages/ExecPlans.tsx`（替换占位）
- Modify: `Src/src/pages/DeepDives.tsx`（替换占位）
- Modify: `Src/src/pages/KnowledgeNotes.tsx`（替换占位）

- [ ] **Step 1: 实现 Markdown 获取工具**
  - 文件：`Src/src/utils/fetchMarkdown.ts`
  - 签名：`export async function fetchMarkdownContent(relativePath: string): Promise<string>`
  - 行为：`fetch('/api/markdown?path=' + encodeURIComponent(relativePath))`，非 ok 响应抛 `Error('Failed to load: ' + status)`，否则返回 `resp.text()`
  - 约束：调用方负责 try-catch
  - 验证：`test -f Src/src/utils/fetchMarkdown.ts` → 预期：文件存在

- [ ] **Step 2: 添加 Vite 中间件代理 Markdown 文件读取**
  覆盖写入 `Src/vite.config.ts`：

  ```typescript
  import { defineConfig } from 'vite';
  import react from '@vitejs/plugin-react';
  import * as fs from 'fs';
  import * as path from 'path';
  import type { Connect } from 'vite';

  function markdownApi(): Connect.NextHandleFunction {
    return (req, res, next) => {
      if (!req.url || !req.url.startsWith('/api/markdown')) {
        next();
        return;
      }
      const url = new URL(req.url, 'http://localhost');
      const filePath = url.searchParams.get('path');
      if (!filePath) {
        res.statusCode = 400;
        res.end('Missing path parameter');
        return;
      }
      const fullPath = path.resolve(__dirname, '..', '..', filePath);
      if (!fs.existsSync(fullPath)) {
        res.statusCode = 404;
        res.end('File not found');
        return;
      }
      const content = fs.readFileSync(fullPath, 'utf-8');
      res.setHeader('Content-Type', 'text/plain; charset=utf-8');
      res.statusCode = 200;
      res.end(content);
    };
  }

  export default defineConfig({
    plugins: [
      react(),
      {
        name: 'markdown-api',
        configureServer(server) {
          server.middlewares.use(markdownApi());
        },
        configurePreviewServer(server) {
          server.middlewares.use(markdownApi());
        }
      }
    ],
    base: './',
    server: {
      fs: { allow: ['..'] }
    }
  });
  ```
  - 验证：`grep 'markdown-api' Src/vite.config.ts` → 预期：匹配到行

- [ ] **Step 3: 实现 ExecPlans 页面**
  - 文件：`Src/src/pages/ExecPlans.tsx`
  - 签名：`export default function ExecPlans()`
  - 关键 import：`useLearningData` from `'../hooks/useLearningData'`
  - 行为：
    - loading/error/null 处理同前
    - 将 `data.execPlans` 分为 `active`（status === 'active'）和 `completed`（status !== 'active'）
    - 标题 "执行计划"
    - "进行中" 区域：`.card-grid` 中每项渲染 `.plan-card`，包含名称、摘要、`<span className="status-badge status-active">active</span>`
    - 若 `completed.length > 0`，"已完成" 区域：同上结构，badge 使用 `.status-badge.status-completed`，文字为 `ep.status`
  - 约束：`.status-completed` 样式需在 App.css 中有定义（灰色背景）
  - 验证：`grep 'status-badge' Src/src/pages/ExecPlans.tsx` → 预期：匹配到行

- [ ] **Step 4: 实现 DeepDives 页面**
  - 文件：`Src/src/pages/DeepDives.tsx`
  - 签名：`export default function DeepDives()`
  - 关键 import：`useNavigate` from `'react-router-dom'`；`useLearningData` from `'../hooks/useLearningData'`
  - 行为：
    - loading/error/null 处理同前
    - 标题 "深度探索"
    - `.card-grid` 中每项渲染 `.plan-card`（可点击），点击跳转 `/view?path=<dd.path>`
    - 每卡片显示标题
  - 约束：卡片 `style={{ cursor: 'pointer' }}`
  - 验证：`grep 'useNavigate' Src/src/pages/DeepDives.tsx` → 预期：匹配到行

- [ ] **Step 5: 实现 KnowledgeNotes 页面**
  - 文件：`Src/src/pages/KnowledgeNotes.tsx`
  - 签名：`export default function KnowledgeNotes()`
  - 关键 import：`useNavigate` from `'react-router-dom'`；`useLearningData` from `'../hooks/useLearningData'`
  - 行为：
    - loading/error/null 处理同前
    - 标题 "知识笔记"
    - `.card-grid` 中每项渲染 `.plan-card`（可点击），点击跳转 `/view?path=<kn.path>`
    - 每卡片显示标题
  - 约束：卡片 `style={{ cursor: 'pointer' }}`
  - 验证：`grep 'KnowledgeNotes' Src/src/pages/KnowledgeNotes.tsx` → 预期：匹配到行

- [ ] **Step 6: TypeScript 类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：退出码 0

- [ ] **Step 7: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add Markdown viewer API, ExecPlans, DeepDives and KnowledgeNotes pages"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add Markdown viewer API, ExecPlans, DeepDives and KnowledgeNotes pages`

---

## Task 8: 构建生产版本并验证

> 验证类 Task——命令序列，完整内容。

**Files:**
- Modify: `Src/package.json`（确认 scripts 完整）

- [ ] **Step 1: 运行数据扫描和索引构建**
  ```bash
  cd Src && npm run scan && npm run index
  ```
  - 验证：`test -f Src/public/data/learning-data.json && test -f Src/public/data/search-index.json` → 预期：两个文件均存在

- [ ] **Step 2: TypeScript 全面类型检查**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：退出码 0，无类型错误

- [ ] **Step 3: 生产构建**
  ```bash
  cd Src && npm run build
  ```
  - 验证：`test -d Src/dist && test -f Src/dist/index.html` → 预期：dist 目录和 index.html 存在

- [ ] **Step 4: 预览验证**
  ```bash
  cd Src && npx vite preview --host 0.0.0.0 --port 4173 &
  sleep 3
  curl -s http://localhost:4173 | grep '<div id="root">'
  kill %1
  ```
  - 验证：curl 输出包含 `<div id="root">`

- [ ] **Step 5: Commit**
  ```bash
  cd Src && git add -A && git commit -m "chore: verify production build and type checking"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`chore: verify production build and type checking`

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| git worktree 创建失败（Src 目录已存在） | 中 | 高 | 创建前检查 `Src` 是否存在；若存在则 `git worktree remove Src` 后重试 |
| 跨 worktree 读取 Markdown 文件路径问题 | 中 | 高 | Vite dev server 通过自定义中间件 `/api/markdown` 代理读取父仓库文件；`server.fs.allow` 配置 `['..']` |
| react-markdown 包体积过大 | 低 | 中 | 接受当前方案；后期可按需动态 import |
| localStorage 数据丢失 | 低 | 中 | 笔记/进度数据可接受丢失风险；后期可加 JSON 导出/恢复 |
| 中文分词效果不佳 | 中 | 低 | 按字分词 + 二字组合 + 英文单词分词；满足基本搜索需求 |

---

## 验收标准

- [ ] `git worktree list` 显示 `Src` 是有效 worktree
- [ ] `cd Src && npm run dev` 成功启动，访问 `http://localhost:5173` 显示仪表盘
- [ ] 仪表盘显示正确的统计数字（学习计划数 >=1、教程数 >=18、执行计划数 >=1）
- [ ] 学习计划列表页显示所有计划卡片，含进度条
- [ ] 点击计划卡片进入详情页，显示该计划的全部教程列表
- [ ] 教程项可勾选完成，勾选后进度条实时更新，刷新页面状态保留（localStorage）
- [ ] 点击教程正确渲染 Markdown 内容（react-markdown + remark-gfm）
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
| 2026-05-22 | 计划重写（v2 — 采用 spec-vs-implementation 新标准：配置/脚本完整内容，应用代码规格化） | — |
