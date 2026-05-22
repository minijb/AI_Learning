# Task 01: 项目骨架初始化

> 所属计划: 学习工作区前端展示面板 | 执行顺序: 第 01 步

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

---

> 此 Task 全部为配置文件和项目骨架文件，按完整内容执行。

- [ ] **Step 1: 创建 git worktree**
  ```bash
  git worktree add Src
  ```
  - 验证：`git worktree list` → 预期输出包含 `Src` 路径

- [ ] **Step 2: 初始化 npm 项目**
  ```bash
  cd Src && npm init -y
  ```
  - 验证：`test -f Src/package.json` → 预期：文件存在

- [ ] **Step 3: 安装运行时依赖**
  ```bash
  cd Src && npm install react react-dom react-router-dom react-markdown remark-gfm
  ```
  - 验证：`test -f Src/node_modules/react/package.json` → 预期：文件存在

- [ ] **Step 4: 安装开发依赖**
  ```bash
  cd Src && npm install -D typescript @types/react @types/react-dom @types/node vite @vitejs/plugin-react
  ```
  - 验证：`test -f Src/node_modules/typescript/package.json` → 预期：文件存在

- [ ] **Step 5: 配置 TypeScript — tsconfig.json**
  创建 `Src/tsconfig.json`：
  ```json
  {
    "compilerOptions": {
      "target": "ES2020",
      "lib": ["ES2020", "DOM", "DOM.Iterable"],
      "module": "ESNext",
      "moduleResolution": "bundler",
      "jsx": "react-jsx",
      "strict": true,
      "esModuleInterop": true,
      "skipLibCheck": true,
      "forceConsistentCasingInFileNames": true,
      "resolveJsonModule": true,
      "isolatedModules": true,
      "noEmit": true
    },
    "include": ["src"]
  }
  ```
  - 验证：`test -f Src/tsconfig.json` → 预期：文件存在

- [ ] **Step 6: 配置 TypeScript — tsconfig.node.json**
  创建 `Src/tsconfig.node.json`：
  ```json
  {
    "compilerOptions": {
      "target": "ES2022",
      "lib": ["ES2023"],
      "module": "ESNext",
      "moduleResolution": "bundler",
      "skipLibCheck": true,
      "noEmit": true
    },
    "include": ["vite.config.ts"]
  }
  ```
  - 验证：`test -f Src/tsconfig.node.json` → 预期：文件存在

- [ ] **Step 7: 配置 Vite（初始版，后续 Task 7 会覆盖）**
  创建 `Src/vite.config.ts`：
  ```typescript
  import { defineConfig } from 'vite';
  import react from '@vitejs/plugin-react';

  export default defineConfig({
    plugins: [react()],
    base: './',
    server: {
      fs: {
        allow: ['..']
      }
    }
  });
  ```
  - 验证：`test -f Src/vite.config.ts` → 预期：文件存在

- [ ] **Step 8: 创建 HTML 入口**
  创建 `Src/index.html`：
  ```html
  <!DOCTYPE html>
  <html lang="zh-CN">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>AI Learning Dashboard</title>
    </head>
    <body>
      <div id="root"></div>
      <script type="module" src="/src/main.tsx"></script>
    </body>
  </html>
  ```
  - 验证：`test -f Src/index.html` → 预期：文件存在

- [ ] **Step 9: 创建 React 入口 — main.tsx**
  创建 `Src/src/main.tsx`：
  ```typescript
  import React from 'react';
  import ReactDOM from 'react-dom/client';
  import { BrowserRouter } from 'react-router-dom';
  import App from './App';
  import './App.css';

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>
  );
  ```
  - 验证：`test -f Src/src/main.tsx` → 预期：文件存在

- [ ] **Step 10: 创建 App.tsx（最小骨架，后续 Task 3 会覆盖）**
  创建 `Src/src/App.tsx`：
  ```typescript
  function App() {
    return (
      <div className="app-layout">
        <aside className="app-sidebar">
          <h1>AI Learning</h1>
        </aside>
        <main className="app-main">
          <h2>Dashboard</h2>
        </main>
      </div>
    );
  }

  export default App;
  ```
  - 验证：`test -f Src/src/App.tsx` → 预期：文件存在

- [ ] **Step 11: 创建基础布局样式 — App.css**
  创建 `Src/src/App.css`：
  ```css
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  html, body, #root {
    height: 100%;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  .app-layout {
    display: flex;
    height: 100vh;
  }

  .app-sidebar {
    width: 220px;
    flex-shrink: 0;
    background: #1a1a2e;
    color: #e0e0e0;
    display: flex;
    flex-direction: column;
    padding: 16px;
  }

  .app-sidebar h1 {
    font-size: 1.2rem;
    padding: 8px 0 16px;
    border-bottom: 1px solid #333;
  }

  .app-main {
    flex: 1;
    overflow-y: auto;
    background: #f5f5f5;
    padding: 24px;
  }
  ```
  - 验证：`test -f Src/src/App.css` → 预期：文件存在

- [ ] **Step 12: 创建 Vite 类型声明**
  创建 `Src/src/vite-env.d.ts`：
  ```typescript
  /// <reference types="vite/client" />
  ```
  - 验证：`test -f Src/src/vite-env.d.ts` → 预期：文件存在

- [ ] **Step 13: 创建 Src/.gitignore**
  创建 `Src/.gitignore`：
  ```
  node_modules
  dist
  ```
  - 验证：`test -f Src/.gitignore` → 预期：文件存在

- [ ] **Step 14: 更新根 .gitignore**
  在根 `.gitignore` 末尾追加两行：
  ```
  Src/node_modules/
  Src/dist/
  ```
  - 验证：`grep "Src/node_modules" .gitignore` → 预期：匹配到行

- [ ] **Step 15: 验证 TypeScript 编译**
  ```bash
  cd Src && npx tsc --noEmit
  ```
  - 验证：命令退出码为 0，无类型错误

- [ ] **Step 16: 验证 dev server 启动**
  ```bash
  cd Src && npx vite --host 0.0.0.0 &
  sleep 3
  curl -s http://localhost:5173 | head -20
  kill %1
  ```
  - 验证：curl 输出包含 `<div id="root">`

- [ ] **Step 17: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: init TypeScript React frontend with Vite"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: init TypeScript React frontend with Vite`
