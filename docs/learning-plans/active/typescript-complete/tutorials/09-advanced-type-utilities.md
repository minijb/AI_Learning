---
title: 高级类型工具
updated: 2026-06-13
tags: [typescript, advanced-types, utility-types]
---

# 高级类型工具

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 75 min
> 前置知识: [[08-generics-basics|泛型基础]]

---

## 1. 概念讲解

### keyof、typeof、索引访问类型

```typescript
interface User {
  id: number;
  name: string;
  email: string;
}

type UserKeys = keyof User; // "id" | "name" | "email"
type UserNameType = User["name"]; // string

const user = { id: 1, name: "Alice" };
type UserType = typeof user; // { id: number; name: string }
```

### 映射类型

基于现有类型生成新类型：

```typescript
type Optional<T> = {
  [K in keyof T]?: T[K];
};

type Readonly<T> = {
  readonly [K in keyof T]: T[K];
};
```

### 内置工具类型

| 工具类型 | 作用 |
|----------|------|
| `Partial<T>` | 所有属性变为可选 |
| `Required<T>` | 所有属性变为必填 |
| `Readonly<T>` | 所有属性变为只读 |
| `Pick<T, K>` | 从 T 中挑选 K |
| `Omit<T, K>` | 从 T 中排除 K |
| `Record<K, V>` | 键类型 K，值类型 V 的对象 |
| `ReturnType<T>` | 函数返回值类型 |
| `Parameters<T>` | 函数参数类型元组 |
| `Awaited<T>` | 解包 Promise 类型 |

### 条件类型

```typescript
type IsString<T> = T extends string ? true : false;

type A = IsString<"hello">; // true
type B = IsString<123>;    // false
```

### infer 提取类型

```typescript
type ReturnType<T> = T extends (...args: unknown[]) => infer R ? R : never;
```

---

## 2. 代码示例

```typescript
// src/advanced-types.ts
interface User {
  id: number;
  name: string;
  email: string;
  password: string;
}

// 只暴露给前端的用户视图
type PublicUser = Omit<User, "password">;

// 创建用户时只需要部分字段
type CreateUserDto = Pick<User, "name" | "email">;

// 配置项映射为可选
type PartialConfig = Partial<{ host: string; port: number }>;

// 条件类型：判断是否为数组
type IsArray<T> = T extends unknown[] ? true : false;

// 提取 Promise 中的值
type UnwrapPromise<T> = T extends Promise<infer R> ? R : T;

type UserPromise = Promise<PublicUser>;
type ResolvedUser = UnwrapPromise<UserPromise>; // PublicUser

// 模板字面量类型
type EventName<T extends string> = `on${Capitalize<T>}`;
type ClickEvent = EventName<"click">; // "onClick"

const publicUser: PublicUser = {
  id: 1,
  name: "Alice",
  email: "alice@example.com",
};

console.log(publicUser);
console.log(typeValue<IsArray<number[]>>());
console.log(typeValue<ClickEvent>());

// 辅助函数：仅用于在运行时打印类型别名名称（实际无类型意义）
function typeValue<T>(): string {
  return typeof ({} as T);
}
```

**运行方式：**

```bash
npx tsx src/advanced-types.ts
```

**预期输出：**

```text
{ id: 1, name: 'Alice', email: 'alice@example.com' }
boolean
string
```

---

## 3. 练习

### 练习 1: 实现 DeepReadonly

实现 `DeepReadonly<T>`，使对象的所有层级都变为只读。

```typescript
type DeepReadonly<T> = /* 你的实现 */;

interface Config {
  db: { host: string; port: number };
  features: string[];
}

type FrozenConfig = DeepReadonly<Config>;
```

### 练习 2: 实现 NullableProperties

实现 `NullableProperties<T, K>`，将 T 中指定的 K 属性变为 `T[K] | null`，其余属性保持不变。

### 练习 3: 类型安全的 HTTP 客户端路径参数（可选）

定义 `ExtractParams<T>`，从类似 `"/users/:userId/posts/:postId"` 的字符串中提取 `:userId` 和 `:postId` 作为联合类型。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> type DeepReadonly<T> = {
>   readonly [K in keyof T]: T[K] extends object
>     ? T[K] extends Function
>       ? T[K]
>       : DeepReadonly<T[K]>
>     : T[K];
> };
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> type NullableProperties<T, K extends keyof T> = Omit<T, K> & {
>   [P in K]: T[P] | null;
> };
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> type ExtractParams<T extends string> =
>   T extends `${infer _Start}:${infer Param}/${infer Rest}`
>     ? Param | ExtractParams<Rest>
>     : T extends `${infer _Start}:${infer Param}`
>     ? Param
>     : never;
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Mapped Types](https://www.typescriptlang.org/docs/handbook/2/mapped-types.html)
- [TypeScript Handbook: Conditional Types](https://www.typescriptlang.org/docs/handbook/2/conditional-types.html)
- [type-challenges/type-challenges](https://github.com/type-challenges/type-challenges)

---

## 常见陷阱

- **递归类型过深**：复杂的递归映射类型可能导致类型推断变慢或报错。
- **条件类型分发行为**：裸类型参数在条件类型中会产生分发，用 `T extends` 时需注意。
- **过度使用高级类型**：代码的可读性优先，不要为了炫技而写难以维护的类型体操。
