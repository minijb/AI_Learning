---
title: 环境搭建与第一个 TS 程序
updated: 2026-06-13
tags: [typescript, setup, nodejs]
---

# 环境搭建与第一个 TS 程序

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 45 min
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要 TypeScript？

TypeScript 是 JavaScript 的超集，它在 JS 之上增加了一套**静态类型系统**。代码在运行之前会先经过 TypeScript 编译器（`tsc`）检查；检查通过后，类型信息被擦除，输出纯 JavaScript 交给 Node.js 或浏览器执行。

这带来三个核心收益：

1. **提前发现错误**：拼写错误、漏传参数、类型不匹配等问题在编译阶段就能暴露，而不是上线后才发现。
2. **更好的 IDE 体验**：自动补全、跳转定义、重构 rename 在类型完整时非常可靠。
3. **可维护性**：类型即文档，阅读他人代码时不需要靠猜。

从 C# 迁移过来的开发者会感觉很亲切：TypeScript 的类型系统大量借鉴了 C# / Java / C++ 的静态类型思想；但请记住，**TypeScript 的类型只在编译时存在**，运行时并不会保留类型信息。它最终还是 JavaScript 在跑。

### 核心思想

> TypeScript = JavaScript + 编译时类型检查。

你的 `.ts` 文件不能直接交给 Node.js 运行，必须先由 `tsc` 编译成 `.js`，或者使用 `tsx` 这类工具在内存中即时转换后执行。本计划推荐使用 `tsx` 作为开发时运行器，因为它零配置、支持 ESM、启动速度快。

---

## 2. 代码示例

### 2.1 创建项目

打开终端，执行以下命令：

```bash
mkdir ts-tool-starter
cd ts-tool-starter
npm init -y
npm install --save-dev typescript tsx @types/node
```

### 2.2 配置 tsconfig.json

在项目根目录创建 `tsconfig.json`，内容如下（这是 2026 年 Node.js 工具项目的推荐起点）：

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
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

> [!note] Node.js 版本
> 本计划示例使用 `Promise.withResolvers()` 等 ES2024 特性，建议 Node.js v22+。如果你仍在 Node 20，部分代码运行前需要添加 polyfill 或升级运行时。

关键配置说明：

- `strict: true`：开启所有严格类型检查，这是最重要的配置。
- `module: NodeNext`：使用 Node.js 原生 ESM/CJS 互操作规则。
- `noUncheckedIndexedAccess`：数组/对象索引访问结果可能为 `undefined`，防止越界崩溃。
- `noImplicitOverride`：重写父类方法必须写 `override` 关键字。

### 2.3 编写第一个程序

创建 `src/index.ts`：

```typescript
function greet(name: string, times: number): void {
  for (let i = 0; i < times; i++) {
    console.log(`Hello, ${name}!`);
  }
}

const user = process.argv[2] ?? "World";
greet(user, 3);
```

### 2.4 运行

开发时直接运行：

```bash
npx tsx src/index.ts TypeScript
```

**预期输出：**

```text
Hello, TypeScript!
Hello, TypeScript!
Hello, TypeScript!
```

编译并运行生产构建：

```bash
npx tsc
node dist/index.js TypeScript
```

---

## 3. 练习

### 练习 1: 温度转换工具

在 `src/index.ts` 中实现一个 `celsiusToFahrenheit(celsius: number): number` 函数，并在 `console.log` 中输出当传入 `25` 时的结果。

### 练习 2: 读取命令行参数

修改程序：当用户传入 `--help` 时，打印一段使用说明；否则调用 `greet`。

### 练习 3: 打包脚本（可选）

在 `package.json` 的 `scripts` 字段中添加 `dev`、`build`、`start` 三条脚本，使得：

- `npm run dev` 用 `tsx` 运行 `src/index.ts`
- `npm run build` 用 `tsc` 编译
- `npm run start` 用 Node.js 运行 `dist/index.js`

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> function celsiusToFahrenheit(celsius: number): number {
>   return (celsius * 9) / 5 + 32;
> }
>
> console.log(celsiusToFahrenheit(25)); // 77
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> const arg = process.argv[2];
> if (arg === "--help") {
>   console.log("用法: npx tsx src/index.ts [名字]");
> } else {
>   greet(arg ?? "World", 3);
> }
> ```

> [!tip]- 练习 3 参考答案
> ```json
> {
>   "scripts": {
>     "dev": "tsx src/index.ts",
>     "build": "tsc",
>     "start": "node dist/index.js"
>   }
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript 官方文档: The Basics](https://www.typescriptlang.org/docs/handbook/basic-types.html)
- [Robin Wieruch: TypeScript in a Node.js Project](https://www.robinwieruch.de/typescript-node-js/) — 包含 `tsx`、环境变量、ESM 配置的 2025 年实操指南。
- [TypeScript 5.8 发布说明](https://devblogs.microsoft.com/typescript/announcing-typescript-5-8/) — 了解 `--module nodenext` 对 `require()` ESM 的支持。

---

## 常见陷阱

- **全局安装 `typescript` 然后用 `tsc` 编译**：容易版本不一致。推荐每个项目本地安装，使用 `npx tsc` 或 npm scripts。
- **忘记 `tsconfig.json` 的 `strict: true`**：关闭严格模式会丢失 TypeScript 一半的价值，新项目的默认配置必须开启。
- **认为类型会在运行时保留**：`typeof x === "string"` 检查的是 JS 值，不是 TS 类型。类型只在编译时存在。
