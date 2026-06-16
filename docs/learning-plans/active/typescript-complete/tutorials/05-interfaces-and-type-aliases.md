---
title: 接口与类型别名
updated: 2026-06-13
tags: [typescript, interfaces, type-aliases]
---

# 接口与类型别名

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 60 min
> 前置知识: [[04-objects-arrays-tuples|对象、数组与元组]]

---

## 1. 概念讲解

### `interface` 与 `type` 的区别

两者都可以描述对象形状，但有一些关键差异：

| 特性 | `interface` | `type` |
|------|-------------|--------|
| 扩展 | 用 `extends` | 用 `&`（交叉类型） |
| 合并声明 | 同名接口会自动合并 | 同名类型会报错 |
| 适用场景 | 对象、类实现 | 联合类型、元组、映射类型等 |

在通用工具开发中，**优先使用 `interface` 描述对象和 API 形状**，用 `type` 描述联合类型、条件类型等。

### 声明合并

```typescript
interface User {
  name: string;
}

interface User {
  age: number;
}

// 实际效果：User 同时有 name 和 age
```

这在扩展第三方库的类型时非常有用。

### 可选属性、只读属性、索引签名

```typescript
interface Config {
  readonly id: string;
  host: string;
  port?: number;
  [key: string]: unknown; // 允许任意额外属性
}
```

### 类型别名用于联合类型

```typescript
type Status = "idle" | "loading" | "success" | "error";
type Result = { ok: true; data: string } | { ok: false; error: string };
```

---

## 2. 代码示例

```typescript
// src/interfaces.ts
interface Logger {
  debug(msg: string): void;
  info(msg: string): void;
  warn(msg: string): void;
  error(msg: string): void;
}

class ConsoleLogger implements Logger {
  debug(msg: string): void {
    console.log(`[DEBUG] ${msg}`);
  }
  info(msg: string): void {
    console.log(`[INFO] ${msg}`);
  }
  warn(msg: string): void {
    console.warn(`[WARN] ${msg}`);
  }
  error(msg: string): void {
    console.error(`[ERROR] ${msg}`);
  }
}

const logger: Logger = new ConsoleLogger();
logger.info("服务启动");

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

function handleResponse<T>(res: ApiResponse<T>): T {
  if (!res.success || res.data === undefined) {
    throw new Error(res.error ?? "Unknown error");
  }
  return res.data;
}

const userRes: ApiResponse<{ name: string }> = {
  success: true,
  data: { name: "Alice" },
};

console.log(handleResponse(userRes));
```

**运行方式：**

```bash
npx tsx src/interfaces.ts
```

**预期输出：**

```text
[INFO] 服务启动
{ name: 'Alice' }
```

---

## 3. 练习

### 练习 1: 设计插件接口

定义一个 `Plugin` 接口，要求插件必须有 `name: string` 和 `execute(input: string): string`。然后写一个 `loadPlugins` 函数，接收 `Plugin[]`，依次调用每个插件并打印结果。

### 练习 2: 递归 JSON 类型

用 `type` 定义一个 `JsonValue` 类型，能够表示任意合法的 JSON 值（`string`、`number`、`boolean`、`null`、对象、数组）。并写一个 `isJsonObject` 类型守卫函数，判断值是否为 JSON 对象。

### 练习 3: 扩展第三方接口（可选）

假设第三方库定义了：

```typescript
interface RequestOptions {
  url: string;
  method: "GET" | "POST";
}
```

在不修改原文件的前提下，通过**声明合并**为它添加 `timeout?: number` 属性，并写一个使用该属性的函数。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> interface Plugin {
>   name: string;
>   execute(input: string): string;
> }
>
> function loadPlugins(plugins: Plugin[]): void {
>   for (const plugin of plugins) {
>     console.log(`[${plugin.name}] ${plugin.execute("hello")}`);
>   }
> }
>
> loadPlugins([
>   { name: "upper", execute: (s) => s.toUpperCase() },
>   { name: "reverse", execute: (s) => s.split("").reverse().join("") },
> ]);
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> type JsonValue =
>   | string
>   | number
>   | boolean
>   | null
>   | JsonObject
>   | JsonArray;
>
> interface JsonObject {
>   [key: string]: JsonValue;
> }
>
> interface JsonArray extends Array<JsonValue> {}
>
> function isJsonObject(value: JsonValue): value is JsonObject {
>   return typeof value === "object" && value !== null && !Array.isArray(value);
> }
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> // 在单独的 .d.ts 文件或模块顶部
> interface RequestOptions {
>   timeout?: number;
> }
>
> function send(options: RequestOptions): void {
>   console.log(`Sending ${options.method} ${options.url} timeout=${options.timeout ?? 5000}`);
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Interfaces](https://www.typescriptlang.org/docs/handbook/2/objects.html#interfaces)
- [TypeScript Handbook: Type Aliases](https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#type-aliases)

---

## 常见陷阱

- **用 `type` 描述对象时无法声明合并**：如果你预计未来会扩展，优先用 `interface`。
- **接口实现不检查字段类型之外的约束**：`implements` 只检查形状，不检查运行时行为。
- **`[key: string]: unknown` 会放宽所有属性检查**：使用索引签名时要权衡类型安全性。
