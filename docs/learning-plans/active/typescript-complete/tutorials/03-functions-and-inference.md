---
title: 函数与类型推断
updated: 2026-06-13
tags: [typescript, functions, inference]
---

# 函数与类型推断

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 60 min
> 前置知识: [[02-basic-types-and-variables|基础类型与变量声明]]

---

## 1. 概念讲解

### TypeScript 如何描述函数？

函数类型由**参数类型**和**返回值类型**两部分组成。你可以用箭头函数类型来显式声明一个回调：

```typescript
type BinaryOp = (a: number, b: number) => number;

const add: BinaryOp = (x, y) => x + y;
```

### 类型推断：TS 会“猜”吗？

TypeScript 的类型推断能力很强，但有其边界：

```typescript
const x = 10;            // 推断为 10（字面量类型），因为 const 不可变
let y = 10;              // 推断为 number
function add(a: number, b: number) { return a + b; } // 返回 number
```

对于复杂场景（如函数参数、导出 API），建议显式标注类型，作为代码的“自文档”。

### 可选参数、默认参数、剩余参数

```typescript
function greet(name: string, greeting = "Hello"): string {
  return `${greeting}, ${name}!`;
}

function sum(...numbers: number[]): number {
  return numbers.reduce((total, n) => total + n, 0);
}

function createUser(name: string, age?: number) {
  return { name, age: age ?? 0 };
}
```

注意：`?` 表示可选，其类型实际上是 `number | undefined`。

### `void` 与 `undefined`

返回 `void` 表示“不关心返回值”。这与 C# 的 `void` 类似。如果一个函数返回 `undefined`，你可以写 `undefined`，但 `void` 更常用：

```typescript
function log(msg: string): void {
  console.log(msg);
}
```

---

## 2. 代码示例

```typescript
// src/functions.ts
type FilterFn = <T>(items: T[], predicate: (item: T) => boolean) => T[];

const filter: FilterFn = (items, predicate) => {
  const result = [];
  for (const item of items) {
    if (predicate(item)) result.push(item);
  }
  return result;
};

const numbers = [1, 2, 3, 4, 5, 6];
const evens = filter(numbers, (n) => n % 2 === 0);
console.log(evens); // [2, 4, 6]

const names = ["Alice", "Bob", "Charlie"];
const longNames = filter(names, (n) => n.length > 3);
console.log(longNames); // ["Alice", "Charlie"]
```

> [!info] 提前接触了泛型
> 这里的 `FilterFn` 用到了泛型。如果你现在觉得抽象，没关系，第 8 节会专门讲泛型。先把它当作“可以接受任意类型数组”的写法即可。

**运行方式：**

```bash
npx tsx src/functions.ts
```

**预期输出：**

```text
[ 2, 4, 6 ]
[ 'Alice', 'Charlie' ]
```

---

## 3. 练习

### 练习 1: 实现一个安全的除法函数

实现 `safeDivide(a, b)`：当 `b` 为 `0` 时返回 `null`，否则返回商。请显式写出参数类型和返回类型。

### 练习 2: 类型化的高阶函数

写一个 `withLogging` 高阶函数：接收一个函数 `fn`，返回一个新函数。新函数在调用 `fn` 前后分别打印 `"start"` 和 `"done"`，并返回 `fn` 的结果。

示例：

```typescript
const add = withLogging((a: number, b: number) => a + b);
console.log(add(2, 3)); // 先打印 start，再打印 done，最后打印 5
```

### 练习 3: 函数重载（可选）

实现一个重载函数 `formatInput`：

- 传入 `number` 时返回 `"num: 42"`
- 传入 `string` 时返回 `"str: hello"`
- 传入 `Date` 时返回 `"date: 2026-06-13"`

在实现体中用类型守卫完成分发。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> function safeDivide(a: number, b: number): number | null {
>   if (b === 0) return null;
>   return a / b;
> }
>
> const result = safeDivide(10, 0);
> if (result !== null) {
>   console.log(result);
> }
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> function withLogging<T extends (...args: unknown[]) => unknown>(fn: T): T {
>   return function (...args: Parameters<T>): ReturnType<T> {
>     console.log("start");
>     const result = fn(...args);
>     console.log("done");
>     return result;
>   } as T;
> }
> ```
> 也可以不用 `Parameters`/`ReturnType`，手动约束：`<A extends unknown[], R>(fn: (...args: A) => R) => (...args: A) => R`。

> [!tip]- 练习 3 参考答案
> ```typescript
> function formatInput(value: number): string;
> function formatInput(value: string): string;
> function formatInput(value: Date): string;
> function formatInput(value: number | string | Date): string {
>   if (typeof value === "number") return `num: ${value}`;
>   if (typeof value === "string") return `str: ${value}`;
>   return `date: ${value.toISOString().slice(0, 10)}`;
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Functions](https://www.typescriptlang.org/docs/handbook/2/functions.html)
- [TypeScript Handbook: More on Functions](https://www.typescriptlang.org/docs/handbook/2/functions.html#function-overloads)

---

## 常见陷阱

- **回调参数不写类型，依赖推断失败**：在独立的回调变量或导出 API 中，务必显式标注参数类型。
- **用 `void` 函数返回具体值**：`void` 只表示调用者不依赖返回值，你仍然可以 `return` 值，但不建议。
- **可选参数放在必填参数前面**：可选参数必须放在末尾，除非提供默认值。
