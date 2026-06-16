---
title: 泛型基础
updated: 2026-06-13
tags: [typescript, generics]
---

# 泛型基础

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 75 min
> 前置知识: [[07-unions-intersections-narrowing|联合类型、交叉类型与类型收窄]]

---

## 1. 概念讲解

### 什么是泛型？

泛型让你编写**类型参数化**的代码。函数、接口、类都可以接收类型参数，在不同场景下复用同一套逻辑。

```typescript
function identity<T>(value: T): T {
  return value;
}

const n = identity<number>(42);   // T 被实例化为 number
const s = identity("hello");       // T 被推断为 string
```

C# 开发者会非常熟悉这种模式：TypeScript 的泛型语法和语义与 C# 泛型高度相似。

### 泛型约束

你可以用 `extends` 约束类型参数：

```typescript
function logLength<T extends { length: number }>(value: T): void {
  console.log(value.length);
}
```

### 多个类型参数

```typescript
function mapPair<K, V>(key: K, value: V): [K, V] {
  return [key, value];
}
```

### 泛型默认值

```typescript
function createArray<T = string>(length: number, value: T): T[] {
  return Array.from({ length }, () => value);
}
```

---

## 2. 代码示例

```typescript
// src/generics.ts
interface Repository<T> {
  find(id: string): T | undefined;
  save(item: T): void;
}

class InMemoryRepository<T extends { id: string }> implements Repository<T> {
  #items = new Map<string, T>();

  find(id: string): T | undefined {
    return this.#items.get(id);
  }

  save(item: T): void {
    this.#items.set(item.id, item);
  }

  list(): T[] {
    return [...this.#items.values()];
  }
}

interface Product {
  id: string;
  name: string;
  price: number;
}

const productRepo = new InMemoryRepository<Product>();
productRepo.save({ id: "p1", name: "Keyboard", price: 299 });
console.log(productRepo.find("p1")?.name);

function groupBy<T, K extends string | number | symbol>(
  items: T[],
  keyFn: (item: T) => K
): Record<K, T[]> {
  const result = {} as Record<K, T[]>;
  for (const item of items) {
    const key = keyFn(item);
    if (!result[key]) result[key] = [];
    result[key].push(item);
  }
  return result;
}

const products: Product[] = [
  { id: "p1", name: "Keyboard", price: 299 },
  { id: "p2", name: "Mouse", price: 199 },
  { id: "p3", name: "Monitor", price: 2999 },
];

const byPrice = groupBy(products, (p) => p.price);
console.log(Object.keys(byPrice));
```

**运行方式：**

```bash
npx tsx src/generics.ts
```

**预期输出：**

```text
Keyboard
[ '299', '199', '2999' ]
```

---

## 3. 练习

### 练习 1: 泛型缓存函数

实现 `memoize<TArgs extends unknown[], TReturn>(fn)`：接收一个函数，返回带缓存的版本。相同参数再次调用时直接返回缓存结果。要求用泛型保持原函数签名。

### 练习 2: 泛型栈

实现一个 `Stack<T>` 类，支持 `push`、`pop`、`peek`、`isEmpty`。`pop` 在栈空时返回 `undefined`。

### 练习 3: 泛型事件发射器（可选）

实现 `EventEmitter<TEventMap>`，其中 `TEventMap` 是一个对象，键为事件名，值为事件参数类型。支持 `on(event, listener)` 和 `emit(event, payload)`，并保证类型安全。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> function memoize<TArgs extends unknown[], TReturn>(
>   fn: (...args: TArgs) => TReturn
> ): (...args: TArgs) => TReturn {
>   const cache = new Map<string, TReturn>();
>   return (...args) => {
>     const key = JSON.stringify(args);
>     if (cache.has(key)) return cache.get(key)!;
>     const result = fn(...args);
>     cache.set(key, result);
>     return result;
>   };
> }
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> class Stack<T> {
>   #items: T[] = [];
>
>   push(item: T): void {
>     this.#items.push(item);
>   }
>
>   pop(): T | undefined {
>     return this.#items.pop();
>   }
>
>   peek(): T | undefined {
>     return this.#items.at(-1);
>   }
>
>   isEmpty(): boolean {
>     return this.#items.length === 0;
>   }
> }
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> type EventListener<T> = (payload: T) => void;
>
> class EventEmitter<TEventMap extends Record<string, unknown>> {
>   #listeners: {
>     [K in keyof TEventMap]?: EventListener<TEventMap[K]>[];
>   } = {};
>
>   on<K extends keyof TEventMap>(
>     event: K,
>     listener: EventListener<TEventMap[K]>
>   ): void {
>     if (!this.#listeners[event]) this.#listeners[event] = [];
>     this.#listeners[event]!.push(listener);
>   }
>
>   emit<K extends keyof TEventMap>(event: K, payload: TEventMap[K]): void {
>     this.#listeners[event]?.forEach((listener) => listener(payload));
>   }
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Generics](https://www.typescriptlang.org/docs/handbook/2/generics.html)
- [type-challenges/type-challenges](https://github.com/type-challenges/type-challenges) — 练习泛型和类型体操的优质题库。

---

## 常见陷阱

- **泛型约束写得太宽**：`T extends unknown` 或不写约束等于没有约束，应尽量精确。
- **在泛型函数内部调用联合类型的方法**：类型参数未收窄前，只能访问约束声明的方法。
- **`as` 断言绕过类型检查**：`value as T` 会关闭检查，只在确信类型正确时使用。
