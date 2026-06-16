---
title: 综合项目：命令行工具开发
updated: 2026-06-13
tags: [typescript, cli, project]
---

# 综合项目：命令行工具开发

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 120 min
> 前置知识: 前面全部章节

---

## 1. 项目目标

开发一个名为 `file-renamer` 的命令行工具，功能包括：

- 递归扫描指定目录下的文件。
- 根据规则批量重命名文件（如替换空格为下划线、添加序号前缀）。
- 支持 `--dry-run` 预览模式。
- 支持 `--recursive` 递归子目录。
- 输出操作统计信息。

本项目将综合运用 TypeScript 类型系统、模块拆分、异步 IO、错误处理、测试和工程化配置。

---

## 2. 项目结构

```text
file-renamer/
├── src/
│   ├── cli.ts           # 入口，解析命令行参数
│   ├── renamer.ts       # 重命名逻辑
│   ├── rules.ts         # 重命名规则
│   ├── types.ts         # 公共类型
│   └── renamer.test.ts  # 测试
├── package.json
├── tsconfig.json
├── eslint.config.mjs
└── vitest.config.ts
```

---

## 3. 代码实现

### 3.1 `src/types.ts`

```typescript
export interface RenameRule {
  name: string;
  transform(fileName: string): string;
}

export interface RenameOptions {
  directory: string;
  recursive: boolean;
  dryRun: boolean;
  rules: RenameRule[];
}

export interface RenameResult {
  oldPath: string;
  newPath: string;
  renamed: boolean;
}
```

### 3.2 `src/rules.ts`

```typescript
import type { RenameRule } from "./types.ts";

export const replaceSpaces: RenameRule = {
  name: "replace-spaces",
  transform: (fileName) => fileName.replace(/\s+/g, "_"),
};

export const addTimestamp: RenameRule = {
  name: "add-timestamp",
  transform: (fileName) => {
    const timestamp = new Date().toISOString().slice(0, 10);
    const dotIndex = fileName.lastIndexOf(".");
    if (dotIndex === -1) return `${timestamp}_${fileName}`;
    return `${fileName.slice(0, dotIndex)}_${timestamp}${fileName.slice(dotIndex)}`;
  },
};

export const lowercase: RenameRule = {
  name: "lowercase",
  transform: (fileName) => fileName.toLowerCase(),
};
```

### 3.3 `src/renamer.ts`

```typescript
import { readdir, rename } from "node:fs/promises";
import { join, dirname, basename } from "node:path";
import type { RenameOptions, RenameResult, RenameRule } from "./types.ts";

function applyRules(fileName: string, rules: RenameRule[]): string {
  return rules.reduce((name, rule) => rule.transform(name), fileName);
}

export async function renameFiles(options: RenameOptions): Promise<RenameResult[]> {
  const results: RenameResult[] = [];
  await walk(options.directory, options, results);
  return results;
}

async function walk(
  dir: string,
  options: RenameOptions,
  results: RenameResult[]
): Promise<void> {
  const entries = await readdir(dir, { withFileTypes: true });

  for (const entry of entries) {
    const oldPath = join(dir, entry.name);

    if (entry.isDirectory()) {
      if (options.recursive) {
        await walk(oldPath, options, results);
      }
      continue;
    }

    const newName = applyRules(entry.name, options.rules);
    const newPath = join(dir, newName);
    const renamed = oldPath !== newPath;

    if (renamed && !options.dryRun) {
      await rename(oldPath, newPath);
    }

    results.push({ oldPath, newPath: renamed ? newPath : oldPath, renamed });
  }
}
```

### 3.4 `src/cli.ts`

```typescript
#!/usr/bin/env node
import { parseArgs } from "node:util";
import { renameFiles } from "./renamer.ts";
import { replaceSpaces, lowercase } from "./rules.ts";
import type { RenameOptions } from "./types.ts";

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    dir: { type: "string", short: "d", default: "." },
    recursive: { type: "boolean", short: "r", default: false },
    "dry-run": { type: "boolean", default: false },
  },
});

const options: RenameOptions = {
  directory: values.dir as string,
  recursive: values.recursive as boolean,
  dryRun: values["dry-run"] as boolean,
  rules: [replaceSpaces, lowercase],
};

async function main(): Promise<void> {
  const results = await renameFiles(options);
  const renamedCount = results.filter((r) => r.renamed).length;

  for (const r of results) {
    if (r.renamed) {
      console.log(`${options.dryRun ? "[DRY-RUN] " : ""}${r.oldPath} -> ${r.newPath}`);
    }
  }

  console.log(`\n完成: ${renamedCount}/${results.length} 个文件将被重命名`);
}

main().catch((error) => {
  console.error("运行失败:", error);
  process.exit(1);
});
```

### 3.5 `src/renamer.test.ts`

```typescript
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renameFiles } from "./renamer.ts";
import { replaceSpaces, lowercase } from "./rules.ts";

describe("renameFiles", () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), "renamer-"));
    writeFileSync(join(tempDir, "Hello World.txt"), "test");
    writeFileSync(join(tempDir, "UPPER.TXT"), "test");
  });

  afterEach(() => {
    rmSync(tempDir, { recursive: true, force: true });
  });

  it("renames files in dry-run mode without touching filesystem", async () => {
    const results = await renameFiles({
      directory: tempDir,
      recursive: false,
      dryRun: true,
      rules: [replaceSpaces, lowercase],
    });

    expect(results.some((r) => r.renamed)).toBe(true);
    const files = readdirSync(tempDir);
    expect(files).toContain("Hello World.txt");
    expect(files).toContain("UPPER.TXT");
  });

  it("actually renames files when dryRun is false", async () => {
    await renameFiles({
      directory: tempDir,
      recursive: false,
      dryRun: false,
      rules: [replaceSpaces, lowercase],
    });

    const files = readdirSync(tempDir);
    expect(files).toContain("hello_world.txt");
    expect(files).toContain("upper.txt");
  });
});
```

---

## 4. 配置清单

### 4.1 `package.json`

```json
{
  "name": "file-renamer",
  "type": "module",
  "bin": {
    "file-renamer": "./dist/cli.js"
  },
  "scripts": {
    "dev": "tsx src/cli.ts",
    "build": "tsc",
    "start": "node dist/cli.js",
    "test": "vitest run",
    "lint": "eslint src"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "eslint": "^9.0.0",
    "eslint-config-prettier": "^10.0.0",
    "prettier": "^3.5.0",
    "tsx": "^4.19.0",
    "typescript": "^5.8.0",
    "typescript-eslint": "^8.0.0",
    "vitest": "^3.0.0"
  }
}
```

### 4.2 `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2024",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2024"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "sourceMap": true,
    "rewriteRelativeImportExtensions": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

---

## 5. 练习

### 练习 1: 添加新规则

为工具添加一个 `sequentialPrefix` 规则，格式为 `001_filename.txt`。要求：

- 规则接收起始序号参数。
- 同一目录内文件按字母顺序分配序号。

### 练习 2: 支持反向操作

实现 `--undo` 选项，读取上一次操作的日志文件，将所有重命名还原。

### 练习 3: 发布到 npm（可选）

学习 `npm publish` 流程，将本项目打包并发布为可全局安装的 CLI 包。注意配置 `bin`、`files`、`keywords` 等字段。

---

## 5.5 参考答案

> [!tip]- 练习 1 参考答案
> 思路：在 `renameFiles` 中按目录维护计数器；规则改为工厂函数，接收目录当前计数：
> ```typescript
> export function sequentialPrefix(start = 1) {
>   const counters = new Map<string, number>();
>   return {
>     name: "sequential-prefix",
>     transform: (fileName: string, dir: string) => {
>       const count = counters.get(dir) ?? start;
>       counters.set(dir, count + 1);
>       const ext = fileName.lastIndexOf(".") > 0
>         ? fileName.slice(fileName.lastIndexOf("."))
>         : "";
>       const base = ext ? fileName.slice(0, -ext.length) : fileName;
>       return `${String(count).padStart(3, "0")}_${base}${ext}`;
>     },
>   };
> }
> ```
> 注意：这要求 `applyRules` 也传入目录参数，属于接口变更。

> [!tip]- 练习 2 参考答案
> 在每次执行时写入 `rename-log.jsonl`，每行记录 `{ oldPath, newPath }`。`--undo` 时读取该日志并逆序执行 `rename(newPath, oldPath)`。

> [!tip]- 练习 3 参考答案
> 发布步骤：
> 1. 登录 npm：`npm login`
> 2. 构建：`npm run build`
> 3. 更新版本号：`npm version patch`
> 4. 发布：`npm publish --access public`
> 5. 全局安装测试：`npm install -g your-package-name`

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 6. 扩展阅读

- [Node.js: parseArgs](https://nodejs.org/api/util.html#utilparseargsconfig)
- [commander.js](https://github.com/tj/commander.js) — 更强大的 CLI 参数解析库。
- [zod](https://github.com/colinhacks/zod) — 运行时 schema 验证，适合验证 CLI 参数和环境变量。

---

## 常见陷阱

- **CLI 参数类型都是字符串**：需要对数字、布尔值做转换和校验。
- **相对路径的解析基准**：CLI 工具中应使用 `path.resolve` 将相对路径转为绝对路径。
- **未处理 `fs/promises` 错误**：文件操作可能因权限、不存在等原因失败，需要 try/catch 或 Result 模式。
