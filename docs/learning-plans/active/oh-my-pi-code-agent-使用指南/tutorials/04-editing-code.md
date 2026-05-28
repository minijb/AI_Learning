# 04 — 精确编辑代码

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 03 — 阅读与浏览代码

---

## 1. 概念讲解

### Hashline 补丁语言

OMP 的 `edit` 工具默认使用 **hashline** 模式——一种基于行锚点的补丁语言。它的核心思想是:

1. `read` 工具输出时，每行带有 `LINEhh|` 锚点（例如 `41th|def alpha():`）
2. `edit` 工具使用这些锚点精确定位要修改的行
3. 如果文件在读取后发生了改变，锚点哈希会不匹配，OMP 会尝试从缓存恢复

### 为什么不用行号？

直接使用行号有致命缺陷: 如果你在文件开头插入一行，所有后续行号都会偏移。Hashline 使用内容哈希验证行内容是否匹配，即使行号变了也能正确恢复。

### 五个基本操作

| 操作 | 符号 | 含义 | 示例 |
|------|------|------|------|
| 替换范围 | `≔A..B` | 替换第 A 行到第 B 行 | `≔41th..43ab` |
| 替换单行 | `≔A` | 替换第 A 行（等于 `≔A..A`） | `≔41th` |
| 在某行后插入 | `»ANCHOR` | 在指定行**之后**插入 | `»41th` |
| 在某行前插入 | `«ANCHOR` | 在指定行**之前**插入 | `«41th` |
| 删除范围 | `≔A..B` | 替换为空 = 删除 | `≔41th..43ab` |

特殊锚点: `BOF`（文件开头）、`EOF`（文件末尾）。

### 编辑的安全性

Hashline 有双层安全保障:
1. **锚点验证**: 编辑前验证每行哈希，不匹配则拒绝
2. **缓存恢复**: 如果文件被外部修改，从 `read` 缓存中恢复并做 3-way merge

---

## 2. 代码示例

### 基本操作示例

假设文件 `src/greet.ts`:
```typescript
1df|const TITLE = "Mr";
2ej|export function greet(name) {
3oa|  return [
4sx|    TITLE,
5as|    name?.trim() || "guest",
6ac|  ].join(" ");
7rk|}
```

**替换一行:**
```text
§src/greet.ts
≔1df
const TITLE = "Mrs";
```

**替换多行:**
```text
§src/greet.ts
≔2ej..7rk
export function greet(name: string): string {
  return `Mrs ${name?.trim() ?? "guest"}`;
}
```

**在中间插入:**
```text
§src/greet.ts
«4sx
  "Dr",
```

**在文件末尾追加:**
```text
§src/greet.ts
»EOF
export const version = "1.0.0";
```

**删除一行:**
```text
§src/greet.ts
≔4sx
```

**清空一行（保留空行）:**
```text
§src/greet.ts
≔4sx

»EOF
```

### 多文件编辑

OMP 可以在一次 `edit` 调用中修改多个文件:

```text
§src/a.ts
»EOF
export const done = true;

§src/b.ts
≔10ab..12cd
const updated = processData(input);
return validatedResult(updated);
```

### `write` 工具 — 创建/覆盖文件

对于新文件和完整重写，使用 `write`:

```text
write src/new-file.ts
内容:
export function createLogger(name: string) {
  return {
    info: (msg: string) => console.log(`[${name}] ${msg}`),
  };
}
```

**运行方式:**
```bash
# 在 OMP 交互会话中，只需用自然语言描述修改:
"把 greet 函数的 TITLE 从 'Mr' 改成 'Mrs'，并用模板字符串重写函数体"
```

**预期输出:**
OMP 会展示精确的 diff 预览，让你确认修改内容。

---

## 3. 练习

### 练习 1: 单文件修改

在一个 TypeScript 文件中:
1. 让 OMP 修改变量名（如 `TITLE` → `PREFIX`）
2. 让 OMP 在某个函数前插入新函数
3. 让 OMP 删除一个不需要的注释块

### 练习 2: 跨文件重构

1. 创建一个包含 3 个文件的模块
2. 让 OMP 在一个文件中重命名导出的函数，并更新所有引用文件的 import
3. 观察 OMP 如何使用 `search` + `ast_grep` 找到所有调用点，再逐一编辑

### 练习 3: 理解锚点（可选）

1. 用 `read` 读取一个文件，观察每行的 `XXxx|` 锚点前缀
2. 手动构造一个 hashline 编辑请求（在 OMP 提示符中直接粘贴 patch）
3. 故意写一个错误的锚点，观察 OMP 如何报错

---

## 4. 扩展阅读

- [`edit` 工具完整文档](omp://tools/edit.md) — hashline 语法、多模式、恢复机制
- [`write` 工具文档](omp://tools/write.md)
- [Hashline 补丁语言规范](omp://tools/edit.md) — 完整的语法规则和边界情况

---

## 常见陷阱

- **锚点只拷贝 `LINEhh` 部分**: 不要拷贝 `|TEXT` 后缀——`»41th|def alpha():` 是错误用法
- **多操作使用原始文件快照**: 所有编辑基于同一快照计算，不要在前一个编辑后重新编号行号
- **`≔A..B` 无 payload = 删除**: 要保留空行，必须在 `≔` 后跟一个空行
- **不要用 `≔` 做插入**: `≔` 是替换，用 `»`/`«` 做插入更安全
- **编辑自动触发 LSP 格式化**: 如果你配置了 `lsp.diagnosticsOnWrite`，编辑后会自动运行格式化器
