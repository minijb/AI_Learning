---
title: "06 — LSP 代码智能"
updated: 2026-06-05
---

# 06 — LSP 代码智能

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 50min
> 前置知识: 05 — 搜索与导航代码库

---

## 1. 概念讲解

### LSP 集成是什么？

OMP 内置了 Language Server Protocol (LSP) 客户端，可以直接与语言服务器通信。这意味着 OMP 不只是"看文本"——它**理解代码结构**。

### 可用的 LSP 操作

| 操作 | 功能 | 使用场景 |
|------|------|---------|
| `definition` | 跳转到定义 | "这个函数定义在哪里？" |
| `type_definition` | 跳转到类型定义 | "这个变量的类型是什么？" |
| `implementation` | 查找实现 | "这个接口有哪些实现？" |
| `references` | 查找所有引用 | "这个函数被哪些地方调用？" |
| `hover` | 查看类型/文档 | "这个符号的类型是什么？" |
| `symbols` | 文件/工作区符号 | "文件中有哪些函数？" |
| `rename` | 安全重命名 | "把这个变量重命名为 X" |
| `code_actions` | 快速修复/重构 | "修复这个类型错误" |
| `diagnostics` | 获取诊断信息 | "这个文件有什么问题？" |

### 支持的 LSP 服务器

OMP 自动发现并启动语言服务器:
- TypeScript/JavaScript: `typescript-language-server`
- Python: `pyright` / `pylsp`
- Rust: `rust-analyzer`
- Go: `gopls`
- ...以及任何实现 LSP 的服务器

---

## 2. 代码示例

### 定义跳转

```bash
# 在 OMP 中:
"main 函数定义在哪里？"
"UserService.create 方法的实现在哪个文件？"
```

OMP 会调用 `lsp definition` 定位到精确位置。

### 查找引用

```bash
"找出所有调用 parseConfig 的地方"
"这个 interface 被哪些类实现了？"
```

OMP 会调用 `lsp references`，返回前 50 个引用位置，支持跨文件。

### 安全重命名

```bash
"把这个模块的 export default function oldName 重命名为 newName"
```

OMP 会调用 `lsp rename`，自动更新:
- 定义处
- 所有 `import` 语句
- 所有调用点
- 所有类型引用

这比 `search` + `edit` 手动重命名**安全得多**，因为 LSP 理解作用域和符号解析规则。

### 诊断信息

```bash
"检查 src/api/ 目录下所有文件的类型错误"
```

OMP 会调用 `lsp diagnostics` 获取编译器/类型检查器的错误和警告。

### Code Actions

```bash
"修复 src/utils.ts 中的所有 ESLint 警告"
"给这个函数补充缺失的 import"
```

`lsp code_actions` 提供自动修复、导入补全等操作。

**运行方式:**
```bash
# 需要项目中存在对应语言的 LSP 服务器。
# TypeScript 项目通常已经配置好 tsconfig.json。
# 其他语言可能需要安装对应的 LSP 二进制:
npm install -g typescript-language-server typescript
```

---

## 3. 练习

### 练习 1: 符号导航

在一个多文件的 TypeScript 项目中:
1. 让 OMP 列出当前文件的所有导出符号
2. 跳转到某个关键函数的定义
3. 查找该函数的所有调用点
4. 查看调用链（从入口函数到深层实现）

### 练习 2: 安全重命名

1. 在一个函数名不规范的模块中
2. 让 OMP 用 LSP rename 重命名该函数
3. 验证所有引用都已更新
4. 对比手动 `search + edit` 和 LSP rename 的差异（后者不会误伤同名但不同作用域的符号）

### 练习 3: 诊断驱动修复

1. 故意制造一个类型错误（如传入错误类型的参数）
2. 让 OMP 检查诊断
3. 应用 code action 修复
4. 验证修复后诊断清零


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 在多文件的 TypeScript 项目中执行符号导航：
>
> ```text
> 1. "列出当前文件的所有导出符号"
>    → OMP 调用 lsp: action="symbols" 获取文件级符号表
>    → 返回函数、类、接口、类型别名的列表，含名称和位置
>
> 2. "跳转到 main 函数的定义"
>    → OMP 调用 lsp: action="definition"
>    → 返回定义所在的文件和精确行列号
>    → OMP 然后用 read 打开该位置展示定义
>
> 3. "查找 parseConfig 函数的所有调用点"
>    → OMP 调用 lsp: action="references"
>    → 返回前 50 个引用位置（文件 + 行列号）
>    → 包含：import 语句中的引用、直接调用、类型引用等
>
> 4. "追踪从 app.ts 的 main() 到 database.ts 的 connect() 的调用链"
>    → OMP 会迭代使用 lsp definition 和 references
>    → 从 main → 中间调用 → 中间调用 → ... → connect()
>    → 每一步确认后继续下一跳
> ```
>
> **思考题答案：** LSP 符号导航 vs 文本搜索的关键区别：LSP 理解作用域。`lsp references` 只会返回真正指向同一符号的引用（不会误报同名但不同作用域的变量），而 `search "main"` 会匹配注释、字符串、不同作用域的同名符号。

> [!tip]- 练习 2 参考答案
> 安全重命名实践：
>
> ```text
> 1. 假设 src/utils.ts 中有一个命名不规范的工具函数：
>    export function calc_tax(amount: number) { ... }
>
> 2. "用 LSP 把 calc_tax 重命名为 calculateTax"
>    → OMP 调用 lsp: action="rename" newName="calculateTax"
>    → LSP 自动更新：
>      - src/utils.ts 中的定义
>      - 所有 import { calc_tax } from "./utils" → calculateTax
>      - 所有调用点 calc_tax(...) → calculateTax(...)
>      - 类型引用 type CalcFn = typeof calc_tax → calculateTax
>
> 3. 验证：search "calc_tax" → 不应返回任何结果
>
> 4. 对比实验 — 如果用 search + edit 手动重命名：
>    → search "calc_tax" 会匹配所有包含该字符串的行
>    → 包括：注释中的 "// calc_tax is used for..." 
>    → 包括：其他文件中的局部变量 calc_tax（完全不同作用域）
>    → 包括：字符串字面量 "calc_tax"
>    → LSP 不会误伤——它只重命名真正的符号引用
> ```
>
> **关键理解：** LSP rename 的"安全"体现在语义层面——它基于编译器的符号解析结果做重命名，而不是文本替换。这在以下场景尤其重要：不同模块中有同名但无关的符号、字符串中包含函数名、注释中引用了旧名称。

> [!tip]- 练习 3 参考答案
> 诊断驱动修复：
>
> ```text
> 1. 制造类型错误：
>    // src/example.ts
>    function greet(name: string): string {
>      return name.length;  // 正常
>    }
>    greet(42);  // 类型错误：number 不能赋给 string
>
> 2. "检查 src/example.ts 的诊断信息"
>    → OMP 调用 lsp: action="diagnostics" paths=["src/example.ts"]
>    → 返回：
>      [ERROR] Line 5: Argument of type 'number' is not assignable 
>               to parameter of type 'string'. (ts:2345)
>
> 3. "应用 code action 修复这个类型错误"
>    → OMP 调用 lsp: action="code_actions" 获取可用的快速修复
>    → 可能的 code actions：
>      - 将 42 改为字符串 "42"
>      - 修改 greet 的参数类型为 number | string
>      - 添加类型断言 greet(42 as unknown as string)
>    → OMP 选择最合适的修复方案（通常最简单的一个）
>
> 4. "再次检查诊断，确认错误已清零"
>    → OMP 重新调用 lsp diagnostics
>    → 预期：无新的类型错误
> ```
>
> **思考题答案：** LSP diagnostics 提供的是"编译器/类型检查器视角"的错误，比运行时错误更早发现。Code actions 将这些诊断映射到修复方案——但修复方案的质量取决于 LSP 服务器的实现。TypeScript 的 code actions 通常很可靠；其他语言可能参差不齐。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [[omp://tools/lsp|`lsp` 工具完整文档]]
- [[omp://lsp-config|LSP 配置]]
- [LSP 协议规范](https://microsoft.github.io/language-server-protocol/)

---

## 常见陷阱

- **LSP 服务器未安装**: OMP 不会自动安装 LSP 服务器。确保项目中有对应的 LSP 二进制可用（全局安装或在 `node_modules/.bin` 中）
- **项目未正确配置**: TypeScript 需要 `tsconfig.json`，Python 需要 `pyproject.toml`/`setup.cfg` 等
- **大项目初始化慢**: 首次打开大项目时，LSP 服务器需要索引整个代码库，可能需要几十秒
- **LSP 服务器崩溃**: 如果服务器挂掉，OMP 会尝试重启。检查 `lsp status` 可查看服务器状态
- **跨仓库引用**: 如果你的代码引用了外部包的类型，需要 LSP 能解析 `node_modules` 或其他依赖
