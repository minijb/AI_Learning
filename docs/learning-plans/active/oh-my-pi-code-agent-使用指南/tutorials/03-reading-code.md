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


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 在不熟悉的项目中启动 OMP，按以下顺序操作：
>
> ```text
> 1. "展示项目根目录结构"
>    → OMP 调用 read . （无选择器，返回按时间排序的目录列表）
>    → 观察：子目录和关键文件一目了然
>
> 2. "读取 package.json（或其他构建配置文件）"
>    → OMP 调用 read package.json 或 read Cargo.toml 等
>    → 从中了解：项目名、依赖、脚本、入口文件路径
>
> 3. "找到入口文件并读取其结构摘要"
>    → OMP 根据 package.json 的 main/exports 字段定位入口
>    → 使用 read src/index.ts 返回结构摘要（函数/类签名字段，体省略）
>    → 观察：摘要中的 `..` 和 `…` 表示省略的函数体
>
> 4. "追踪一个关键函数，使用行范围逐步阅读"
>    → 从摘要中找到目标函数签名所在行号
>    → 例如："读取 src/index.ts 中 main 函数的完整实现"
>    → OMP 会先定位函数行号，然后 read src/index.ts:42-80
> ```
>
> **思考题答案：** OMP 使用结构摘要（无选择器）作为"目录"——快速了解文件有哪些函数/类，然后通过行范围精确读取需要的部分。这种"先俯瞰、再聚焦"的策略避免了全量读取大文件。

> [!tip]- 练习 2 参考答案
> 在一个超 500 行的文件中：
>
> ```text
> 1. "只读取 src/large-file.ts 的 import 部分"
>    → OMP 通常使用 read src/large-file.ts:1-30
>    → import 一般在文件头部，所以从第 1 行起读取
>
> 2. "读取 processData 函数的完整实现"
>    → OMP 会先用无选择器 read 获取结构摘要
>    → 从摘要中找到 processData 的行号位置（如第 200 行）
>    → 然后 read src/large-file.ts:200+80 读取函数体
>
> 3. "读取文件末尾的 exports 部分"
>    → OMP 可能使用 read src/large-file.ts:450-520
>    → 或者先用 bash: wc -l 获取文件总行数，再从尾部读取
> ```
>
> **关键技巧：** 当你知道目标但不知道行号时，告诉 OMP 你要找的函数/变量/模式名——它会先用结构摘要或 search 定位，再用精确行范围读取。

> [!tip]- 练习 3 参考答案
> 如果有 SQLite 数据库（如 `app.db`）：
>
> ```text
> 1. "列出 app.db 中的所有表"
>    → OMP 调用 read app.db
>    → 返回非系统表的列表，含行数统计：
>      users     (150 rows)
>      posts     (320 rows)
>      comments  (890 rows)
>
> 2. "查看 users 表的结构和示例数据"
>    → OMP 调用 read app.db:users
>    → 返回：列定义 + 前 5 条记录作为示例
>
> 3. "查询 status='active' 的 users 记录"
>    → OMP 调用 read app.db:users?where=status='active'&limit=20
>    → 或 read app.db?q=SELECT * FROM users WHERE status='active' LIMIT 20
> ```
>
> **思考题答案：** OMP 的 SQLite 读取器支持两种模式——`表名:筛选` 的便利语法和 `?q=SELECT` 的完整 SQL。便利语法适用于简单过滤，复杂查询（JOIN、GROUP BY 等）需要用 `?q=` 模式。两种模式都是只读的，不能执行 INSERT/UPDATE/DELETE。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
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
