# Task 02: 数据扫描与搜索索引脚本

> 所属计划: 学习工作区前端展示面板 | 执行顺序: 第 02 步

**Files:**
- Create: `Src/scripts/scan-learning-data.ts`
- Create: `Src/scripts/build-search-index.ts`
- Modify: `Src/package.json`（添加 scripts）

---

> 此 Task 全部为脚本和配置文件，按完整内容执行。

- [ ] **Step 1: 实现数据扫描脚本**
  创建 `Src/scripts/scan-learning-data.ts`：

  ```typescript
  import * as fs from 'fs';
  import * as path from 'path';

  const DOCS_ROOT = path.resolve(__dirname, '..', '..', '..', 'docs');
  const TEMP_DOCS_ROOT = path.resolve(__dirname, '..', '..', '..', 'temp', 'docs');
  const OUTPUT_DIR = path.resolve(__dirname, '..', 'public', 'data');

  function getTitle(mdPath: string): string {
    if (!fs.existsSync(mdPath)) return '';
    const lines = fs.readFileSync(mdPath, 'utf-8').split('\n');
    for (const line of lines) {
      const m = line.match(/^#\s+(.+)/);
      if (m) return m[1].trim();
    }
    return '';
  }

  function parseFrontmatter(mdPath: string): Record<string, string> {
    if (!fs.existsSync(mdPath)) return {};
    const content = fs.readFileSync(mdPath, 'utf-8');
    const m = content.match(/^---\n([\s\S]*?)\n---/);
    if (!m) return {};
    const result: Record<string, string> = {};
    for (const line of m[1].split('\n')) {
      const kv = line.match(/^(\w+):\s*(.+)/);
      if (kv) result[kv[1]] = kv[2].trim();
    }
    return result;
  }

  function readProgress(progressPath: string): number {
    if (!fs.existsSync(progressPath)) return 0;
    const content = fs.readFileSync(progressPath, 'utf-8');
    const m = content.match(/总进度[:：]\s*(\d+)%/);
    return m ? parseInt(m[1]) : 0;
  }

  function scanLearningPlans(): any[] {
    const plans: any[] = [];
    const activeDir = path.join(DOCS_ROOT, 'learning-plans', 'active');
    if (!fs.existsSync(activeDir)) return plans;

    for (const dir of fs.readdirSync(activeDir)) {
      const planDir = path.join(activeDir, dir);
      if (!fs.statSync(planDir).isDirectory()) continue;
      const planMd = path.join(planDir, 'plan.md');
      if (!fs.existsSync(planMd)) continue;
      const fm = parseFrontmatter(planMd);
      const tutorials: any[] = [];
      const tutorialsDir = path.join(planDir, 'tutorials');
      if (fs.existsSync(tutorialsDir)) {
        for (const f of fs.readdirSync(tutorialsDir)) {
          if (!f.endsWith('.md')) continue;
          const tPath = path.join(tutorialsDir, f);
          const numMatch = f.match(/^(\d+)-/);
          tutorials.push({
            id: f.replace('.md', ''),
            title: getTitle(tPath) || f,
            filename: f,
            order: numMatch ? parseInt(numMatch[1]) : 999
          });
        }
      }
      tutorials.sort((a, b) => a.order - b.order);
      plans.push({
        id: dir,
        name: fm.title || dir,
        description: fm.description || '',
        createdDate: fm.created || '',
        totalHours: parseFloat(fm.total_hours || '0'),
        targetLevel: fm.level || '',
        progress: readProgress(path.join(planDir, 'progress.md')),
        tutorials,
        planPath: `docs/learning-plans/active/${dir}/`
      });
    }
    return plans;
  }

  function scanExecPlans(): any[] {
    const plans: any[] = [];
    const activeDir = path.join(DOCS_ROOT, 'exec-plans', 'active');
    if (!fs.existsSync(activeDir)) return plans;
    for (const dir of fs.readdirSync(activeDir)) {
      const planDir = path.join(activeDir, dir);
      if (!fs.statSync(planDir).isDirectory()) continue;
      const planMd = path.join(planDir, 'exec-plan.md');
      if (!fs.existsSync(planMd)) continue;
      const content = fs.readFileSync(planMd, 'utf-8');
      const goalMatch = content.match(/\*\*Goal:\*\*\s*(.+)/);
      plans.push({
        id: dir,
        name: dir,
        summary: goalMatch ? goalMatch[1] : '',
        status: 'active',
        createdDate: '',
        path: `docs/exec-plans/active/${dir}/`
      });
    }
    return plans;
  }

  function scanArticles(subdir: string): any[] {
    const articles: any[] = [];
    const d = path.join(DOCS_ROOT, subdir);
    if (!fs.existsSync(d)) return articles;
    for (const f of fs.readdirSync(d)) {
      if (!f.endsWith('.md') || f === 'INDEX.md') continue;
      const fpath = path.join(d, f);
      articles.push({
        id: f.replace('.md', ''),
        title: getTitle(fpath) || f,
        path: `docs/${subdir}/${f}`
      });
    }
    const td = path.join(TEMP_DOCS_ROOT, subdir);
    if (fs.existsSync(td)) {
      for (const f of fs.readdirSync(td)) {
        if (!f.endsWith('.md') || f === 'INDEX.md') continue;
        const fpath = path.join(td, f);
        articles.push({
          id: f.replace('.md', ''),
          title: getTitle(fpath) || f,
          path: `temp/docs/${subdir}/${f}`
        });
      }
    }
    return articles;
  }

  function main() {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    const data = {
      learningPlans: scanLearningPlans(),
      execPlans: scanExecPlans(),
      deepDives: scanArticles('deep-dives'),
      knowledgeNotes: scanArticles('knowledge-notes')
    };
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'learning-data.json'),
      JSON.stringify(data, null, 2)
    );
    console.log(`[scan] ${data.learningPlans.length} plans, ${data.execPlans.length} exec-plans, ${data.deepDives.length} deep-dives, ${data.knowledgeNotes.length} notes -> learning-data.json`);
  }

  main();
  ```
  - 验证：`npx tsx scripts/scan-learning-data.ts` → 预期：输出 `[scan] ... -> learning-data.json` 且 `test -f public/data/learning-data.json` 文件存在且非空

- [ ] **Step 2: 实现搜索索引构建脚本**
  创建 `Src/scripts/build-search-index.ts`：

  ```typescript
  import * as fs from 'fs';
  import * as path from 'path';

  const DOCS_ROOT = path.resolve(__dirname, '..', '..', '..', 'docs');
  const TEMP_DOCS_ROOT = path.resolve(__dirname, '..', '..', '..', 'temp', 'docs');
  const DATA_DIR = path.resolve(__dirname, '..', 'public', 'data');

  function tokenize(text: string): string[] {
    const tokens: string[] = [];
    const enWords = text.match(/[a-zA-Z0-9_]+/g) || [];
    tokens.push(...enWords.map(w => w.toLowerCase()));
    const cleaned = text.replace(/[a-zA-Z0-9_\s]+/g, '');
    for (let i = 0; i < cleaned.length; i++) {
      tokens.push(cleaned[i]);
      if (i + 1 < cleaned.length) {
        tokens.push(cleaned[i] + cleaned[i + 1]);
      }
    }
    return tokens;
  }

  function buildIndex() {
    const dataFile = path.join(DATA_DIR, 'learning-data.json');
    if (!fs.existsSync(dataFile)) {
      console.error('learning-data.json not found. Run scan-learning-data.ts first.');
      process.exit(1);
    }
    const data = JSON.parse(fs.readFileSync(dataFile, 'utf-8'));
    const index: Record<string, Array<{ path: string; positions: number[] }>> = {};
    const documents: Array<{ path: string; title: string; preview: string }> = [];

    const docPaths: Array<{ path: string; title: string }> = [];

    for (const plan of data.learningPlans || []) {
      const planDir = path.join(DOCS_ROOT, 'learning-plans', 'active', plan.id);
      for (const tut of plan.tutorials || []) {
        docPaths.push({
          path: path.join(planDir, 'tutorials', tut.filename),
          title: tut.title
        });
      }
      docPaths.push({
        path: path.join(planDir, 'plan.md'),
        title: plan.name
      });
    }

    for (const ep of data.execPlans || []) {
      docPaths.push({
        path: path.join(DOCS_ROOT, 'exec-plans', 'active', ep.id, 'exec-plan.md'),
        title: ep.name
      });
    }

    for (const dd of data.deepDives || []) {
      const filePath = dd.path.replace(/^docs\//, '');
      docPaths.push({
        path: path.join(DOCS_ROOT, filePath),
        title: dd.title
      });
    }

    for (const kn of data.knowledgeNotes || []) {
      const filePath = kn.path.replace(/^docs\//, '');
      const fullPath = path.join(DOCS_ROOT, filePath);
      if (!fs.existsSync(fullPath) && kn.path.startsWith('temp/')) {
        const tempPath = kn.path.replace(/^temp\/docs\//, '');
        docPaths.push({
          path: path.join(TEMP_DOCS_ROOT, tempPath),
          title: kn.title
        });
      } else {
        docPaths.push({ path: fullPath, title: kn.title });
      }
    }

    for (const doc of docPaths) {
      if (!fs.existsSync(doc.path)) continue;
      const content = fs.readFileSync(doc.path, 'utf-8');
      const preview = content.replace(/\n/g, ' ').slice(0, 200);
      documents.push({ path: doc.path, title: doc.title, preview });
      const tokens = tokenize(content);
      const positionMap: Record<string, number[]> = {};
      tokens.forEach((t, i) => {
        if (!positionMap[t]) positionMap[t] = [];
        positionMap[t].push(i);
      });
      for (const [term, positions] of Object.entries(positionMap)) {
        if (!index[term]) index[term] = [];
        index[term].push({ path: doc.path, positions });
      }
    }

    fs.writeFileSync(
      path.join(DATA_DIR, 'search-index.json'),
      JSON.stringify({ terms: index, documents }, null, 2)
    );
    console.log(`[index] ${Object.keys(index).length} terms, ${documents.length} documents -> search-index.json`);
  }

  buildIndex();
  ```
  - 验证：`npx tsx scripts/build-search-index.ts` → 预期：输出 `[index] ... terms, ... documents -> search-index.json` 且 `test -f public/data/search-index.json` 文件 > 1KB

- [ ] **Step 3: 配置 npm scripts**
  修改 `Src/package.json`，替换 `"scripts"` 字段为：

  ```json
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "scan": "npx tsx scripts/scan-learning-data.ts",
    "index": "npx tsx scripts/build-search-index.ts",
    "prebuild": "npm run scan && npm run index"
  }
  ```
  - 验证：`grep '"scan"' Src/package.json` → 预期：匹配到行

- [ ] **Step 4: 安装 tsx 并运行扫描脚本验证**
  ```bash
  cd Src && npm install -D tsx && npm run scan && npm run index
  ```
  - 验证：`test -f Src/public/data/learning-data.json && test -f Src/public/data/search-index.json` → 预期：两个文件均存在

- [ ] **Step 5: Commit**
  ```bash
  cd Src && git add -A && git commit -m "feat: add data scanner and search index builder scripts"
  ```
  - 验证：`cd Src && git log -1 --oneline` → 预期：`feat: add data scanner and search index builder scripts`
