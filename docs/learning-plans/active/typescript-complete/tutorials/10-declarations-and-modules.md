---
title: 类型声明与模块系统
updated: 2026-06-13
tags: [typescript, modules, declarations]
---

# 类型声明与模块系统

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 60 min
> 前置知识: [[05-interfaces-and-type-aliases|接口与类型别名]]、[[08-generics-basics|泛型基础]]

---

## 1. 概念讲解

### 模块系统

TypeScript 支持两种模块输出：

- **ES Modules（ESM）**：使用 `import` / `export`，现代 Node.js 和浏览器推荐。
- **CommonJS（CJS）**：使用 `require` / `module.exports`，老项目常见。

在 Node.js 工具项目中，推荐：

- `package.json` 中设置 `"type": "module"`
- `tsconfig.json` 中设置 `"module": "NodeNext"` 和 `"moduleResolution": "NodeNext"`

TypeScript 5.7+ 支持 `--rewriteRelativeImportExtensions`，编译时自动将 `.ts` 扩展名改写为 `.js`。

### `.d.ts` 声明文件

当使用没有类型的 JS 库时，需要为其编写声明文件：

```typescript
// types/my-lib.d.ts
declare function greet(name: string): string;
export = greet;
```

### 环境声明

对于全局变量或第三方脚本：

```typescript
declare const API_BASE_URL: string;
```

---

## 2. 代码示例

### 2.1 项目结构

```text
src/
├── math.ts
├── string-utils.ts
└── main.ts
```

### 2.2 `src/math.ts`

```typescript
export function add(a: number, b: number): number {
  return a + b;
}

export function multiply(a: number, b: number): number {
  return a * b;
}
```

### 2.3 `src/string-utils.ts`

```typescript
export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function slugify(s: string): string {
  return s.toLowerCase().replace(/\s+/g, "-");
}
```

### 2.4 `src/main.ts`

```typescript
import { add, multiply } from "./math.ts";
import slugify, { capitalize } from "./string-utils.ts";

console.log(add(2, 3));
console.log(multiply(4, 5));
console.log(capitalize("hello"));
console.log(slugify("Hello World"));
```

### 2.5 `package.json`

```json
{
  "type": "module",
  "scripts": {
    "dev": "tsx src/main.ts",
    "build": "tsc"
  }
}
```

### 2.6 `tsconfig.json`（关键部分）

```json
{
  "compilerOptions": {
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "rewriteRelativeImportExtensions": true,
    "allowImportingTsExtensions": true,
    "strict": true
  }
}
```

**运行方式：**

```bash
npx tsx src/main.ts
```

**预期输出：**

```text
5
20
Hello
hello-world
```

### 2.7 为无类型库写声明

假设你使用了一个没有类型的 JS 库 `legacy-calc`：

```typescript
// src/types/legacy-calc.d.ts
declare module "legacy-calc" {
  export function compute(a: number, b: number): number;
  export const VERSION: string;
}
```

---

## 3. 练习

### 练习 1: 拆分模块

将上一节的 `celsiusToFahrenheit` 函数拆分到 `src/temperature.ts`，然后在 `src/main.ts` 中导入并使用。

### 练习 2: 为 JSON 文件写类型

创建一个 `src/data/user.json` 文件，并在 TypeScript 中导入它。为 `user.json` 定义一个接口，并用 `satisfies` 关键字约束 JSON 内容。

### 练习 3: 命名空间式工具模块（可选）

创建一个 `src/utils/index.ts` 文件，从多个子模块（`array.ts`、`string.ts`）聚合导出，使得外部可以通过 `import { chunk } from "./utils/index.ts"` 使用。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> // src/temperature.ts
> export function celsiusToFahrenheit(celsius: number): number {
>   return (celsius * 9) / 5 + 32;
> }
> ```
> ```typescript
> // src/main.ts
> import { celsiusToFahrenheit } from "./temperature.ts";
> console.log(celsiusToFahrenheit(25));
> ```

> [!tip]- 练习 2 参考答案
> ```json
> // src/data/user.json
> {
>   "id": 1,
>   "name": "Alice",
>   "email": "alice@example.com"
> }
> ```
> ```typescript
> // src/types/user.ts
> export interface User {
>   id: number;
>   name: string;
>   email: string;
> }
> ```
> ```typescript
> // src/main.ts
> import type { User } from "./types/user.ts";
> import userData from "./data/user.json" with { type: "json" };
> const user = userData satisfies User;
> console.log(user.name);
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> // src/utils/array.ts
> export function chunk<T>(arr: T[], size: number): T[][] {
>   const result: T[][] = [];
>   for (let i = 0; i < arr.length; i += size) {
>     result.push(arr.slice(i, i + size));
>   }
>   return result;
> }
> ```
> ```typescript
> // src/utils/index.ts
> export * from "./array.ts";
> export * from "./string.ts";
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Modules](https://www.typescriptlang.org/docs/handbook/2/modules.html)
- [TypeScript 5.7: rewriteRelativeImportExtensions](https://devblogs.microsoft.com/typescript/announcing-typescript-5-7/)
- [Node.js: ESM Interoperability](https://nodejs.org/api/esm.html#interoperability-with-commonjs)

---

## 常见陷阱

- **相对导入漏写扩展名**：在 `NodeNext` 模式下，必须写 `.ts` 扩展名（开发时）或通过 `--rewriteRelativeImportExtensions` 让 tsc 自动改写。
- **`allowImportingTsExtensions` 与 `tsc` 编译冲突**：该选项需要配合 `noEmit` 或 `rewriteRelativeImportExtensions` 使用。
- **混淆 `import` 与 `import type`**：`import type` 只导入类型，编译后会被擦除，推荐用于类型导入。
