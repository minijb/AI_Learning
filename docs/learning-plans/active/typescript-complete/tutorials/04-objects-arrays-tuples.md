---
title: 对象、数组与元组
updated: 2026-06-13
tags: [typescript, objects, arrays, tuples]
---

# 对象、数组与元组

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 60 min
> 前置知识: [[02-basic-types-and-variables|基础类型与变量声明]]

---

## 1. 概念讲解

### 对象类型

在 TypeScript 中，对象类型用花括号描述其属性：

```typescript
function printPoint(p: { x: number; y: number }): void {
  console.log(`(${p.x}, ${p.y})`);
}
```

与 C# 不同，TypeScript 是**结构类型系统**：只要对象形状匹配，就可以传入，不需要显式声明实现某个接口。

### 数组

数组类型有两种写法：

```typescript
const nums: number[] = [1, 2, 3];
const names: Array<string> = ["Alice", "Bob"];
```

推荐 `T[]` 写法，除非类型复杂（如 `Array<string | number>`）。

### 元组（Tuple）

元组是长度和类型都固定的数组：

```typescript
const point: [number, number] = [10, 20];
const user: [string, number] = ["Alice", 30];
```

元组非常适合表示坐标、键值对、函数返回的多值结果。

### 只读

```typescript
const readonlyNums: readonly number[] = [1, 2, 3];
// readonlyNums.push(4); // 报错

const readonlyPoint: readonly [number, number] = [1, 2];
```

---

## 2. 代码示例

```typescript
// src/collections.ts
type RGB = [number, number, number];

function hexToRgb(hex: string): RGB | null {
  const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!match) return null;
  return [
    parseInt(match[1]!, 16),
    parseInt(match[2]!, 16),
    parseInt(match[3]!, 16),
  ];
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

const rgb = hexToRgb("#ff5733");
if (rgb) {
  const [r, g, b] = rgb;
  console.log(`R=${r}, G=${g}, B=${b}`);
}

console.log(average([10, 20, 30]));
```

**运行方式：**

```bash
npx tsx src/collections.ts
```

**预期输出：**

```text
R=255, G=87, B=51
20
```

---

## 3. 练习

### 练习 1: 配置对象类型化

定义一个 `ServerConfig` 类型，包含：

- `host: string`
- `port: number`
- `debug?: boolean`（可选）

然后写一个 `startServer(config)` 函数，打印 `"Starting server at host:port"`，如果 `debug` 为 `true` 再打印 `"Debug mode enabled"`。

### 练习 2: 矩阵转置

实现 `transpose(matrix: number[][]): number[][]`，返回转置后的矩阵。注意 `noUncheckedIndexedAccess` 可能要求你处理 `undefined`。

### 练习 3: 安全获取 CSV 字段（可选）

定义类型 `Row = [string, number, boolean]` 表示 CSV 的一行（姓名、年龄、是否激活）。写一个 `parseRow(fields: string[]): Row | null`，将字符串数组解析为该元组；如果解析失败返回 `null`。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> type ServerConfig = {
>   host: string;
>   port: number;
>   debug?: boolean;
> };
>
> function startServer(config: ServerConfig): void {
>   console.log(`Starting server at ${config.host}:${config.port}`);
>   if (config.debug) {
>     console.log("Debug mode enabled");
>   }
> }
>
> startServer({ host: "localhost", port: 3000 });
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> function transpose(matrix: number[][]): number[][] {
>   if (matrix.length === 0) return [];
>   const colCount = matrix[0]?.length ?? 0;
>   const result: number[][] = [];
>   for (let c = 0; c < colCount; c++) {
>     const row: number[] = [];
>     for (let r = 0; r < matrix.length; r++) {
>       const value = matrix[r]?.[c];
>       if (value === undefined) continue;
>       row.push(value);
>     }
>     result.push(row);
>   }
>   return result;
> }
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> type Row = [string, number, boolean];
>
> function parseRow(fields: string[]): Row | null {
>   if (fields.length !== 3) return null;
>   const [name, ageStr, activeStr] = fields;
>   if (!name || !ageStr || !activeStr) return null;
>   const age = Number(ageStr);
>   if (Number.isNaN(age)) return null;
>   if (activeStr !== "true" && activeStr !== "false") return null;
>   return [name, age, activeStr === "true"];
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Object Types](https://www.typescriptlang.org/docs/handbook/2/objects.html)
- [TypeScript Handbook: Tuples](https://www.typescriptlang.org/docs/handbook/2/objects.html#tuple-types)

---

## 常见陷阱

- **数组越界返回 `undefined`**：开启 `noUncheckedIndexedAccess` 后，`arr[i]` 的类型是 `T | undefined`，必须处理。
- **元组可变长**：`[number, number]` 不允许 `push` 第三个元素，但 `.push()` 在运行时仍可执行，TypeScript 只在编译期阻止。
- **对象类型默认允许额外属性**：赋值字面量时 TypeScript 会检查多余属性；但通过变量传入时不会（结构类型兼容）。
