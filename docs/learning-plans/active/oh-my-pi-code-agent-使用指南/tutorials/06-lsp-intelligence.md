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

---

## 4. 扩展阅读

- [`lsp` 工具完整文档](omp://tools/lsp.md)
- [LSP 配置](omp://lsp-config.md)
- [LSP 协议规范](https://microsoft.github.io/language-server-protocol/)

---

## 常见陷阱

- **LSP 服务器未安装**: OMP 不会自动安装 LSP 服务器。确保项目中有对应的 LSP 二进制可用（全局安装或在 `node_modules/.bin` 中）
- **项目未正确配置**: TypeScript 需要 `tsconfig.json`，Python 需要 `pyproject.toml`/`setup.cfg` 等
- **大项目初始化慢**: 首次打开大项目时，LSP 服务器需要索引整个代码库，可能需要几十秒
- **LSP 服务器崩溃**: 如果服务器挂掉，OMP 会尝试重启。检查 `lsp status` 可查看服务器状态
- **跨仓库引用**: 如果你的代码引用了外部包的类型，需要 LSP 能解析 `node_modules` 或其他依赖
