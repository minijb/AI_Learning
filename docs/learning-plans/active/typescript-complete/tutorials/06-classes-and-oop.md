---
title: 类与面向对象
updated: 2026-06-13
tags: [typescript, classes, oop]
---

# 类与面向对象

> 所属计划: [[plan|TypeScript 完整学习计划]]
> 预计耗时: 75 min
> 前置知识: [[05-interfaces-and-type-aliases|接口与类型别名]]

---

## 1. 概念讲解

### TypeScript 的类

TypeScript 的 `class` 语法与 C# 高度相似，支持：

- 构造函数
- 访问修饰符 `public`、`private`、`protected`
- `readonly` 字段
- 继承 `extends`
- 抽象类 `abstract`
- `implements` 接口

### 与 C# 的关键差异

| 特性 | C# | TypeScript |
|------|-----|------------|
| `private` | 运行时真正私有 | 仅在编译期检查，编译后仍是普通属性 |
| 真私有 | 无 | 用 `#field`（ES2022 私有字段） |
| 抽象类 | `abstract class` | `abstract class` |
| 属性初始化 | 声明时或构造函数中 | 声明时、构造函数参数属性、或字段初始化器 |

### 构造函数参数属性

```typescript
class Point {
  constructor(public x: number, public y: number) {}
}
```

这等价于：

```typescript
class Point {
  x: number;
  y: number;
  constructor(x: number, y: number) {
    this.x = x;
    this.y = y;
  }
}
```

### 真正的私有字段

```typescript
class SafeBox {
  #secret: string;
  constructor(secret: string) {
    this.#secret = secret;
  }
}
```

`#secret` 在运行时也是私有的，无法从外部访问。

---

## 2. 代码示例

```typescript
// src/oop.ts
abstract class Animal {
  constructor(protected name: string) {}

  abstract makeSound(): string;

  move(distance: number): void {
    console.log(`${this.name} moved ${distance}m`);
  }
}

class Dog extends Animal {
  makeSound(): string {
    return "Woof!";
  }
}

class Cat extends Animal {
  makeSound(): string {
    return "Meow!";
  }
}

const dog = new Dog("Buddy");
console.log(dog.makeSound());
dog.move(10);

const cat = new Cat("Kitty");
console.log(cat.makeSound());

interface Repository<T> {
  findById(id: string): T | undefined;
  save(item: T): void;
}

class InMemoryUserRepository implements Repository<{ id: string; name: string }> {
  #users = new Map<string, { id: string; name: string }>();

  findById(id: string): { id: string; name: string } | undefined {
    return this.#users.get(id);
  }

  save(item: { id: string; name: string }): void {
    this.#users.set(item.id, item);
  }
}

const repo = new InMemoryUserRepository();
repo.save({ id: "1", name: "Alice" });
console.log(repo.findById("1"));
```

**运行方式：**

```bash
npx tsx src/oop.ts
```

**预期输出：**

```text
Woof!
Buddy moved 10m
Meow!
{ id: '1', name: 'Alice' }
```

---

## 3. 练习

### 练习 1: 实现任务管理器

设计一个 `Task` 类，包含：

- `id: string`
- `title: string`
- `completed: boolean`
- `toggle(): void` 方法切换完成状态

再实现 `TaskManager` 类，支持 `add(task)`、`getById(id)`、`listCompleted()`。

### 练习 2: 银行账户类

实现 `BankAccount` 类：

- 私有字段 `#balance: number`
- `deposit(amount: number): void`
- `withdraw(amount: number): void`，余额不足时抛出错误
- `getBalance(): number`

写一个测试脚本验证其行为。

### 练习 3: 抽象类与模板方法（可选）

定义抽象类 `FileProcessor`，包含：

- 抽象方法 `parse(content: string): unknown`
- 具体方法 `process(path: string): unknown`，读取文件、调用 `parse`、返回结果

实现 `CsvProcessor` 和 `JsonProcessor` 两个子类。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```typescript
> class Task {
>   constructor(
>     public id: string,
>     public title: string,
>     public completed: boolean = false
>   ) {}
>
>   toggle(): void {
>     this.completed = !this.completed;
>   }
> }
>
> class TaskManager {
>   #tasks = new Map<string, Task>();
>
>   add(task: Task): void {
>     this.#tasks.set(task.id, task);
>   }
>
>   getById(id: string): Task | undefined {
>     return this.#tasks.get(id);
>   }
>
>   listCompleted(): Task[] {
>     return [...this.#tasks.values()].filter((t) => t.completed);
>   }
> }
> ```

> [!tip]- 练习 2 参考答案
> ```typescript
> class BankAccount {
>   #balance: number;
>
>   constructor(initialBalance: number) {
>     this.#balance = initialBalance;
>   }
>
>   deposit(amount: number): void {
>     if (amount <= 0) throw new Error("Invalid amount");
>     this.#balance += amount;
>   }
>
>   withdraw(amount: number): void {
>     if (amount <= 0) throw new Error("Invalid amount");
>     if (amount > this.#balance) throw new Error("Insufficient funds");
>     this.#balance -= amount;
>   }
>
>   getBalance(): number {
>     return this.#balance;
>   }
> }
> ```

> [!tip]- 练习 3 参考答案
> ```typescript
> import { readFileSync } from "node:fs";
>
> abstract class FileProcessor {
>   process(path: string): unknown {
>     const content = readFileSync(path, "utf-8");
>     return this.parse(content);
>   }
>
>   abstract parse(content: string): unknown;
> }
>
> class JsonProcessor extends FileProcessor {
>   parse(content: string): unknown {
>     return JSON.parse(content);
>   }
> }
>
> class CsvProcessor extends FileProcessor {
>   parse(content: string): string[][] {
>     return content.trim().split("\n").map((line) => line.split(","));
>   }
> }
> ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TypeScript Handbook: Classes](https://www.typescriptlang.org/docs/handbook/2/classes.html)
- [MDN: Private class features](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Classes/Private_properties)

---

## 常见陷阱

- **混淆 `private` 和 `#private`**：`private` 只在类型层面生效，运行时仍可访问；`#private` 是运行时私有。
- **`protected` 字段仍可被外部读取类型信息**：类型系统不阻止通过子类暴露 protected 成员。
- **忘记 `override` 关键字**：开启 `noImplicitOverride` 后，重写父类方法必须写 `override`。
