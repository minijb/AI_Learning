---
title: 错误处理与工程化实践
updated: 2026-06-13
tags: [typescript, error-handling, tooling]
---

# 错误处理与工程化实践

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 60 min
> 前置知识: [[11-async-and-promises|异步编程与 Promise]]

---

## 1. 概念讲解

### 错误处理模式

TypeScript / JavaScript 中有两种主流错误处理思路：

1. **异常抛出（throw）**：与 C# 一致，失败时抛出 Error。
2. **Result 类型**：函数返回 `{ ok: true, data: T } | { ok: false, error: E }`，调用方必须处理两种结果。

对于通用工具开发，Result 模式能避免未捕获的异常破坏流程，特别适合 CLI 和库。

### 工具链

现代 TypeScript 项目至少应配置：

- **TypeScript 编译器**：`tsc`
- **代码格式化**：`prettier`
- **代码检查**：`eslint` + `@typescript-eslint`
- **测试框架**：`vitest`（推荐）或 `jest`

### ESLint + TypeScript 推荐配置

```bash
npm install --save-dev eslint @eslint/js typescript-eslint prettier eslint-config-prettier
```

```typescript
// eslint.config.mjs
import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        project: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  prettier
);
```

---

## 2. 代码示例

### 2.1 Result 类型实现

```typescript
// src/result.ts
export type Result<T, E = Error> =
  | { ok: true; data: T }
  | { ok: false; error: E };

export function ok<T>(data: T): Result<T, never> {
  return { ok: true, data };
}

export function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

export function safeParseInt(input: string): Result<number, string> {
  const value = Number(input);
  if (!Number.isInteger(value)) {
    return err(`"${input}" 不是有效整数`);
  }
  return ok(value);
}

const result = safeParseInt("42");
if (result.ok) {
  console.log(result.data + 1);
} else {
  console.error(result.error);
}
```

**运行方式：**

```bash
npx tsx src/result.ts
```

**预期输出：**

```text
43
```

### 2.2 vitest 示例

```typescript
// src/result.test.ts
import { describe, it, expect } from "vitest";
import { safeParseInt } from "./result.ts";

describe("safeParseInt", () => {
  it("parses valid integer", () => {
    const result = safeParseInt("42");
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data).toBe(42);
  });

  it("returns error for invalid input", () => {
    const result = safeParseInt("abc");
    expect(result.ok).toBe(false);
  });
});
```

运行测试：

```bash
npx vitest
```

---

## 3. 练习

### 练习 1: 实现 Result 的 map 方法

为 `Result<T, E>` 实现一个 `map` 函数：

```typescript
function map<T, U, E>(result: Result<T, E>, fn: (data: T) => U): Result<U, E>
```

### 练习 2: 类型安全的配置文件读取

实现 `loadConfig(path): Result<Config, string>`，读取 JSON 配置文件。如果文件不存在或 JSON 解析失败，返回错误；否则返回配置对象。

### 练习 3: 配置 ESLint + Prettier（可选）

按照本节工具链说明，在你的示例项目中安装并配置 ESLint、Prettier、vitest，确保 `npm run lint` 和 `npm test` 都能正常运行。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> function map<T, U, E>(
>   result: Result<T, E>,
>   fn: (data: T) => U
> ): Result<U, E> {
>   if (result.ok) {
>     return ok(fn(result.data));
>   }
>   return result;
> }
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> import { readFileSync } from "node:fs";
>
> interface Config {
>   host: string;
>   port: number;
> }
>
> function loadConfig(path: string): Result<Config, string> {
>   try {
>     const content = readFileSync(path, "utf-8");
>     const parsed = JSON.parse(content) as unknown;
>     if (
>       typeof parsed === "object" &&
>       parsed !== null &&
>       "host" in parsed &&
>       "port" in parsed &&
>       typeof (parsed as Config).host === "string" &&
>       typeof (parsed as Config).port === "number"
>     ) {
>       return ok(parsed as Config);
>     }
>     return err("配置文件格式不正确");
>   } catch (e) {
>     return err(`读取失败: ${e instanceof Error ? e.message : String(e)}`);
>   }
> }
> ```

> [!tip]- 练习 3 参考答案
> 配置步骤：
> 1. `npm install --save-dev eslint typescript-eslint prettier eslint-config-prettier vitest @types/node`
> 2. 创建 `eslint.config.mjs` 如上方示例。
> 3. 创建 `.prettierrc`：`{ "semi": true, "singleQuote": false }`。
> 4. 在 `package.json` 中添加：
>    ```json
>    "scripts": {
>      "lint": "eslint src",
>      "format": "prettier --write src",
>      "test": "vitest run"
>    }
>    ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [typescript-eslint: Getting Started](https://typescript-eslint.io/getting-started/)
- [Vitest Documentation](https://vitest.dev/guide/)
- [Prettier Documentation](https://prettier.io/docs/en/)

---

## 常见陷阱

- **`catch` 块的 `error` 是 `unknown`**：不要直接假设它是 `Error`，应先判断 `e instanceof Error`。
- **Result 模式滥用**：简单场景仍可用异常，Result 更适合边界明确、需要链式处理的函数。
- **忽略 `.prettierignore` 和 `.eslintignore`**：构建产物和锁文件应排除在格式化/检查之外。
