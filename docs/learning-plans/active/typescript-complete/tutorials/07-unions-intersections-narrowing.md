---
title: 联合类型、交叉类型与类型收窄
updated: 2026-06-13
tags: [typescript, unions, intersections, narrowing]
---

# 联合类型、交叉类型与类型收窄

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 75 min
> 前置知识: [[03-functions-and-inference|函数与类型推断]]、[[04-objects-arrays-tuples|对象、数组与元组]]

---

## 1. 概念讲解

### 联合类型

联合类型表示“值可以是 A，也可以是 B”：

```typescript
type Result = string | number;
type Status = "idle" | "loading" | "done";
```

使用联合类型的值时，TypeScript 只允许访问所有成员共有的属性和方法。

### 交叉类型

交叉类型表示“同时满足 A 和 B”：

```typescript
type HasName = { name: string };
type HasAge = { age: number };
type Person = HasName & HasAge;
```

这与 C# 的接口多实现类似。

### 类型收窄

联合类型需要通过类型守卫收窄后才能安全使用：

```typescript
function printId(id: string | number): void {
  if (typeof id === "string") {
    console.log(id.toUpperCase()); // 此处 id 被收窄为 string
  } else {
    console.log(id.toFixed(2)); // 此处 id 被收窄为 number
  }
}
```

常用收窄方式：

- `typeof`
- `instanceof`
- `in` 操作符
- 自定义类型谓词 `value is Type`
- 等值收窄、真值收窄

### 可辨识联合

当联合的每个成员都有一个共同的字面量字段时，TypeScript 可以通过 `switch` 完美收窄：

```typescript
type Circle = { kind: "circle"; radius: number };
type Square = { kind: "square"; side: number };
type Shape = Circle | Square;

function area(shape: Shape): number {
  switch (shape.kind) {
    case "circle": return Math.PI * shape.radius ** 2;
    case "square": return shape.side ** 2;
  }
}
```

---

## 2. 代码示例

```typescript
// src/narrowing.ts
type LoadingState = { status: "loading" };
type SuccessState = { status: "success"; data: string };
type ErrorState = { status: "error"; error: string };

type AsyncState = LoadingState | SuccessState | ErrorState;

function render(state: AsyncState): string {
  switch (state.status) {
    case "loading":
      return "加载中...";
    case "success":
      return `数据: ${state.data}`;
    case "error":
      return `错误: ${state.error}`;
  }
}

const states: AsyncState[] = [
  { status: "loading" },
  { status: "success", data: "hello" },
  { status: "error", error: "timeout" },
];

for (const s of states) {
  console.log(render(s));
}

interface Bird {
  kind: "bird";
  fly(): void;
}

interface Fish {
  kind: "fish";
  swim(): void;
}

type Animal = Bird | Fish;

function move(animal: Animal): void {
  if (animal.kind === "bird") {
    animal.fly();
  } else {
    animal.swim();
  }
}
```

**运行方式：**

```bash
npx tsx src/narrowing.ts
```

**预期输出：**

```text
加载中...
数据: hello
错误: timeout
```

---

## 3. 练习

### 练习 1: 类型谓词

实现 `isStringArray(value: unknown): value is string[]`，判断未知值是否为字符串数组。并在主函数中使用它。

### 练习 2: 可辨识联合实现事件处理

定义类型：

- `ClickEvent = { type: "click"; x: number; y: number }`
- `KeyEvent = { type: "key"; key: string }`
- `ScrollEvent = { type: "scroll"; delta: number }`

实现 `handleEvent(event)`，根据事件类型打印不同信息。

### 练习 3: 交叉类型建模（可选）

定义 `Timestamped` 和 `Identifiable` 两个类型，然后用交叉类型创建 `TimestampedUser = User & Timestamped & Identifiable`，并实现一个工厂函数。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> function isStringArray(value: unknown): value is string[] {
>   return Array.isArray(value) && value.every((item) => typeof item === "string");
> }
>
> function process(input: unknown): void {
>   if (isStringArray(input)) {
>     console.log(input.join(", "));
>   } else {
>     console.log("不是字符串数组");
>   }
> }
>
> process(["a", "b", "c"]);
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> type ClickEvent = { type: "click"; x: number; y: number };
> type KeyEvent = { type: "key"; key: string };
> type ScrollEvent = { type: "scroll"; delta: number };
> type AppEvent = ClickEvent | KeyEvent | ScrollEvent;
>
> function handleEvent(event: AppEvent): void {
>   switch (event.type) {
>     case "click":
>       console.log(`点击坐标: (${event.x}, ${event.y})`);
>       break;
>     case "key":
>       console.log(`按键: ${event.key}`);
>       break;
>     case "scroll":
>       console.log(`滚动: ${event.delta}`);
>       break;
>   }
> }
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> type User = { name: string; email: string };
> type Timestamped = { createdAt: Date };
> type Identifiable = { id: string };
> type TimestampedUser = User & Timestamped & Identifiable;
>
> function createUser(name: string, email: string): TimestampedUser {
>   return {
>     id: crypto.randomUUID(),
>     name,
>     email,
>     createdAt: new Date(),
>   };
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Unions and Intersections](https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#union-types)
- [TypeScript Handbook: Narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html)

---

## 常见陷阱

- **访问联合类型不共有的属性**：在收窄前只能访问共有成员。
- **`in` 收窄的对象可能是 null**：先判断 `value && typeof value === "object"` 再使用 `in`。
- **交叉类型产生 `never`**：`string & number` 是 `never`，表示无值。
