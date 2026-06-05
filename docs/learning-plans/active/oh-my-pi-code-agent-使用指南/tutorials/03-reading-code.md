---
title: "03 — 阅读与浏览代码"
updated: 2026-06-05
---

# 03 — 阅读与浏览代码

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 01 — OMP 概述与首次会话

---

## 1. 概念讲解

### `read` 工具 — OMP 的眼睛

`read` 是 OMP 最核心的工具。它通过一个 `path` 参数统一处理:

- 本地文件（带选择器）
- 目录列表
- 压缩包内容
- SQLite 数据库
- 文档（PDF、DOCX、PPTX、XLSX、EPUB）
- Jupyter Notebook
- 图片元数据
- 内部 URL（`skill://`、`agent://`、`memory://`、`omp://`）
- 网页 URL（reader-mode）

### 选择器语法

`read` 的强大在于**选择器（Selector）**——你可以精确指定要读取的范围:

| 后缀 | 含义 | 示例 |
|------|------|------|
| _(无)_ | 结构摘要（签名保留，函数体省略） | `read src/main.ts` |
| `:raw` | 原始内容，无摘要 | `read src/main.ts:raw` |
| `:N` | 从第 N 行开始 | `read src/main.ts:50` |
| `:N-M` | 第 N 到 M 行 | `read src/main.ts:50-100` |
| `:N+M` | N 行起共 M 行 | `read src/main.ts:50+10` |

多个范围可以组合: `src/main.ts:5-16,960-973`

### 为什么需要选择器？

大型文件可能有数千行。选择器让 OMP 只读取需要的部分，节省 token 和上下文窗口。结构摘要在不指定选择器时自动生效——它会保留函数/类/类型签名，折叠方法体。

---

## 2. 代码示例

### 读取文件

```bash
# 在 OMP 中，你可以直接要求它读取文件:
"读取 src/utils/helpers.ts 的 import 部分"
```

OMP 会推断你需要文件开头，自动使用类似 `read src/utils/helpers.ts:1-30` 的选择器。

### 目录浏览

```bash
"展示 src/ 目录的结构"
```

这会触发无选择器的 `read`，返回按修改时间排序的目录树（深度 2，每目录最多 12 项）。

### 文档读取

```bash
"读取 docs/design.pdf 的内容"
```

OMP 自动将 PDF 转换为 Markdown 文本返回。

### 读取压缩包

```bash
"列出 archive.zip 的内容"
"读取 archive.zip:src/config.json"
```

### SQLite 查询

```bash
"查看 database.sqlite 有哪些表"
"查看 users 表的结构和示例数据"
"查询 users 表中 status='active' 的记录"
```

对应的内部调用:
- `read database.sqlite` → 列出非系统表
- `read database.sqlite:users` → 表结构 + 5 条示例
- `read database.sqlite:users?where=status='active'&limit=20`

### 读取网页

```bash
"读取 https://nodejs.org/api/fs.html 的文档"
```

OMP 会使用 reader-mode 提取干净的文本内容，支持行范围选择器。

### 内部 URL

```bash
# 读取 Skill 内容
read skill://learning-plans

# 读取子代理输出
read agent://0-Task

# 读取项目记忆
read memory://root
```

**运行方式:**
```bash
# 不需要手动运行——这些都是 OMP 内部调用的工具。
# 你只需要用自然语言描述需求即可。
```

---

## 3. 练习

### 练习 1: 探索陌生项目

在你不熟悉的项目中启动 OMP，依次让它:
1. 展示项目根目录结构
2. 读取 `package.json`（或其他构建配置）
3. 找到入口文件并读取其结构摘要
4. 追踪一个关键函数，使用行范围逐步阅读

### 练习 2: 精确行范围

在一个超 500 行的文件中:
1. 让 OMP 只读取 imports 部分
2. 让 OMP 读取某个特定函数（指定函数名，看它如何定位）
3. 让 OMP 读取文件末尾的 exports 部分

### 练习 3: 数据库探索

如果有 SQLite 数据库:
1. 让 OMP 列出所有表
2. 查看某个表的结构和示例数据
3. 用 where 条件过滤特定记录

---

## 4. 扩展阅读

- [[omp://tools/read|`read` 工具完整文档]] — 所有模式、限制、内部 URL 解析
- [[omp://resolve-tool-runtime|OMP 内部 URL 系统]]
- [[omp://tools/read|SQLite 读取器]] — 查询语法和限制

---

## 常见陷阱

- **结构摘要不是全文**: 不指定选择器时，`read` 可能只返回函数签名。如果需要完整实现，必须追加行范围
- **选择器语法严格**: `:0` 会报错（行号从 1 开始），`:+5` 必须 ≥ 1
- **图片默认不显示内容**: `read` 对图片只返回元数据，需要 `inspect_image` 工具进行视觉分析
- **压缩包一次性加载**: `.zip` 和 `.tar.gz` 会被完整读入内存，超大压缩包可能很慢
- **URL 缓存**: 网页读取结果会被缓存，重复读取同一 URL 不会重新请求网络
