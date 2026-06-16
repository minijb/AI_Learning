---
title: 基础类型与变量声明
updated: 2026-06-13
tags: [typescript, types, variables]
---

# 基础类型与变量声明

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 60 min
> 前置知识: [[01-setup-and-first-program|环境搭建与第一个 TS 程序]]

---

## 1. 概念讲解

### TypeScript 有哪些基础类型？

TypeScript 的基础类型与 C# 很接近，但有几个 JS 特有的类型需要适应：

| 类型 | 示例 | 说明 |
|------|------|------|
| `boolean` | `true` / `false` | 布尔值 |
| `number` | `42`, `3.14`, `NaN`, `Infinity` | 所有数字都是双精度浮点数，没有 `int`/`float` 之分 |
| `bigint` | `100n` | 任意精度整数 |
| `string` | `"hello"`, `'hello'`, `` `hi` `` | 字符串 |
| `symbol` | `Symbol("id")` | 唯一标识符 |
| `null` | `null` | 表示“没有值” |
| `undefined` | `undefined` | 表示“未初始化” |
| `any` | 任意类型 | 关闭类型检查，应尽量避免 |
| `unknown` | 未知类型 | 更安全的 `any`，使用前必须收窄 |
| `never` | 无值 | 不可能到达的分支或抛出异常的函数 |

### 为什么需要 `unknown` 和 `never`？

C# 有 `object` 可以表示任意引用类型，但 TypeScript 的 `any` 会**完全关闭**类型检查。`unknown` 则要求你在使用它之前证明它是什么类型，这样更安全。

`never` 表示“永远不会发生”的值。例如一个只抛出错误的函数，返回类型就是 `never`；在穷举所有联合类型的分支后，剩余分支的类型也是 `never`。

### 变量声明：`let` vs `const`

```typescript
let count: number = 0;        // 可变
const name = "TypeScript";    // 不可变，类型被推断为 "TypeScript"
```

优先使用 `const`。只有确实需要重新赋值时才用 `let`。这与 C# 的 `var` 类似，但 TypeScript 的类型推断能力更强。

### 字面量类型

变量不仅可以是 `string`，还可以是某个**具体的字符串**：

```typescript
type Direction = "north" | "south" | "east" | "west";
const d: Direction = "north"; // 合法
// const e: Direction = "up"; // 报错
```

这在配置项、状态机、命令名称中非常有用。

---

## 2. 代码示例

```typescript
// src/basic-types.ts
function inspect(value: unknown): string {
  if (typeof value === "string") {
    return `字符串，长度 ${value.length}`;
  }
  if (typeof value === "number") {
    return `数字 ${value.toFixed(2)}`;
  }
  if (value === null) {
    return "null";
  }
  if (value === undefined) {
    return "undefined";
  }
  return "其他类型";
}

console.log(inspect("hello"));
console.log(inspect(3.14159));
console.log(inspect(null));
console.log(inspect({ x: 1 }));
```

**运行方式：**

```bash
npx tsx src/basic-types.ts
```

**预期输出：**

```text
字符串，长度 5
数字 3.14
null
其他类型
```

### 开启 `strictNullChecks` 的效果

在 `tsconfig.json` 中开启 `strict: true` 后，`null` 和 `undefined` 不能随意赋值给其他类型：

```typescript
function findUser(id: number): string | undefined {
  if (id === 1) return "Alice";
  return undefined;
}

const user = findUser(2);
console.log(user.toUpperCase()); // 报错：user 可能为 undefined
console.log(user?.toUpperCase()); // 合法：可选链
```

---

## 3. 练习

### 练习 1: 修复类型错误

下面代码在 `strict: true` 下会报错，请修改类型标注使其通过编译：

```typescript
function parseInput(input: unknown) {
  if (typeof input === "number") {
    return input * 2;
  }
  return input;
}
```
要求：为参数和返回值添加合适的类型标注，使函数更精确。


### 练习 2: 字面量类型约束

定义一个类型 `LogLevel`，只能取 `"debug"`、`"info"`、`"warn"`、`"error"`。然后实现函数 `log(level, message)`，只对合法的 level 编译通过。

### 练习 3: 穷举检查（可选）

定义类型 `Shape = "circle" | "square" | "triangle"`，写一个 `getSides(shape)` 函数返回边数。在函数末尾写一个 `default` 分支，让 TypeScript 推断其参数类型为 `never`，从而保证所有 case 都被覆盖。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> function parseInput(input: unknown): unknown {
>   if (typeof input === "number") {
>     return input * 2;
>   }
>   return input;
> }
> ```
> 也可以返回 `number | unknown`，但 `unknown` 足够表达“未知结果”。关键是把不够精确的类型换成 `unknown`。

> [!tip]- 练习 2 参考答案
> ```typescript
> type LogLevel = "debug" | "info" | "warn" | "error";
>
> function log(level: LogLevel, message: string): void {
>   console.log(`[${level.toUpperCase()}] ${message}`);
> }
>
> log("info", "服务启动"); // 合法
> // log("trace", "..."); // 报错
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> type Shape = "circle" | "square" | "triangle";
>
> function getSides(shape: Shape): number {
>   switch (shape) {
>     case "circle": return 0;
>     case "square": return 4;
>     case "triangle": return 3;
>     default:
>       const _exhaustive: never = shape;
>       return _exhaustive;
>   }
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Everyday Types](https://www.typescriptlang.org/docs/handbook/2/everyday-types.html)
- [TypeScript Handbook: Narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html)
- [TypeScript 5.8: Granular Checks for Branches in Return Expressions](https://devblogs.microsoft.com/typescript/announcing-typescript-5-8/#granular-checks-for-branches-in-return-expressions)

---

## 常见陷阱

- **用 `any` 逃避类型检查**：一旦使用 `any`，周围的类型推断都会被破坏。应优先使用 `unknown` 或具体联合类型。
- **`null` 和 `undefined` 不区分**：在 JavaScript 中两者都有“空”的含义。开启 `strictNullChecks` 后必须明确处理。
- **认为 `number` 包含整数和浮点**：TypeScript 没有 `int` 类型，如果需要整数校验，要在运行时检查（例如用 `Number.isInteger`）。
