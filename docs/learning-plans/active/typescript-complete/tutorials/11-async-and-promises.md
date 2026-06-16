---
title: 异步编程与 Promise
updated: 2026-06-13
tags: [typescript, async, promise]
---

# 异步编程与 Promise

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 75 min
> 前置知识: [[03-functions-and-inference|函数与类型推断]]、[[10-declarations-and-modules|类型声明与模块系统]]

---

## 1. 概念讲解

### JavaScript 的异步模型

TypeScript 最终运行在 JavaScript 引擎上，异步机制与 JS 完全一致：

- `Promise<T>` 表示一个未来会完成的值。
- `async` 函数自动返回 `Promise<T>`。
- `await` 会暂停当前 `async` 函数的执行，等待 Promise 解决。

与 C# 的 `Task<T>` / `async` / `await` 非常相似，但底层不是线程池，而是**事件循环**。

### Promise 状态

一个 `Promise` 有三种状态：

- `pending`：进行中
- `fulfilled`：已完成
- `rejected`：已拒绝

### 常用静态方法

```typescript
const [a, b] = await Promise.all([fetchA(), fetchB()]);
const first = await Promise.race([fetchA(), timeout(1000)]);
```

---

## 2. 代码示例

```typescript
// src/async.ts
function delay(ms: number): Promise<void> {
  const { promise, resolve } = Promise.withResolvers<void>();
  setTimeout(resolve, ms);
  return promise;
}
```

> [!note] Node.js 版本
> 本节示例使用 `Promise.withResolvers()`，需要 Node.js v22+。旧版本可手动 polyfill 或使用等价的 `new Promise` 实现。

```typescript
// src/async.ts (continued)
async function fetchUser(id: number): Promise<{ id: number; name: string }> {
  await delay(100);
  if (id <= 0) throw new Error("Invalid user id");
  return { id, name: `User-${id}` };
}

async function main(): Promise<void> {
  try {
    const users = await Promise.all([
      fetchUser(1),
      fetchUser(2),
      fetchUser(3),
    ]);
    console.log(users);
  } catch (error) {
    console.error("获取用户失败:", error);
  }
}

main();
```

**运行方式：**

```bash
npx tsx src/async.ts
```

**预期输出：**

```text
[ { id: 1, name: 'User-1' }, { id: 2, name: 'User-2' }, { id: 3, name: 'User-3' } ]
```

### 带重试的异步函数

```typescript
async function withRetry<T>(
  fn: () => Promise<T>,
  retries: number,
  delayMs: number
): Promise<T> {
  let lastError: unknown;
  for (let i = 0; i <= retries; i++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (i < retries) await delay(delayMs);
    }
  }
  throw lastError;
}
```

---

## 3. 练习

### 练习 1: 串行执行

实现 `runSequentially<T>(tasks)`：接收一个返回 `Promise<T>` 的函数数组，按顺序执行，返回所有结果的数组。

### 练习 2: 超时包装

实现 `withTimeout<T>(promise, ms)`：如果 Promise 在 `ms` 毫秒内未完成，则抛出一个 `TimeoutError`。

### 练习 3: 限制并发（可选）

实现 `runWithConcurrency<T>(tasks, maxConcurrency)`：同时最多运行 `maxConcurrency` 个任务，返回所有结果。注意保持结果顺序。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> async function runSequentially<T>(tasks: (() => Promise<T>)[]): Promise<T[]> {
>   const results: T[] = [];
>   for (const task of tasks) {
>     results.push(await task());
>   }
>   return results;
> }
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> class TimeoutError extends Error {
>   constructor(message = "Operation timed out") {
>     super(message);
>     this.name = "TimeoutError";
> }
>
> function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
>   const { promise: timeout, reject: rejectTimeout } = Promise.withResolvers<never>();
>   setTimeout(() => rejectTimeout(new TimeoutError()), ms);
>   return Promise.race([promise, timeout]);
> }
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> async function runWithConcurrency<T>(
>   tasks: (() => Promise<T>)[],
>   maxConcurrency: number
> ): Promise<T[]> {
>   const results = new Array<T>(tasks.length);
>   const iterator = tasks.entries();
>
>   async function worker(): Promise<void> {
>     for (const [index, task] of iterator) {
>       results[index] = await task();
>     }
>   }
>
>   await Promise.all(Array.from({ length: maxConcurrency }, worker));
>   return results;
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [MDN: Promise](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise)
- [Node.js: Event Loop](https://nodejs.org/en/learn/asynchronous-work/event-loop-timers-and-nexttick)

---

## 常见陷阱

- **忘记 `await`**：`async` 函数返回 Promise，调用时如果忘记 `await` 会得到 Promise 对象而不是结果。
- **并行任务错误处理**：`Promise.all` 中一个失败会导致全部失败，必要时用 `Promise.allSettled`。
- **try/catch 中的 `error` 类型**：默认是 `unknown`，需要收窄或断言。
