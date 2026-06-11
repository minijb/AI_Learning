---
title: "05 — 搜索与导航大型代码库"
updated: 2026-06-05
---

# 05 — 搜索与导航大型代码库

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 50min
> 前置知识: 03 — 阅读与浏览代码

---

## 1. 概念讲解

### 两大搜索工具

OMP 提供两个互补的搜索工具:

| 工具 | 适用场景 | 匹配方式 |
|------|---------|---------|
| `search` | 文本内容搜索 | 正则表达式 |
| `find` | 文件名搜索 | Glob 模式 |

### `search` — 正则内容搜索

`search` 使用 Rust 正则引擎（RE2 风格），支持跨行模式。它会:
- 尊重 `.gitignore` 规则
- 返回匹配行的 `LINEhh|` 锚点（可被 `edit` 直接使用）
- 支持大小写不敏感搜索

### `find` — 文件发现

`find` 按 glob 模式匹配文件路径，返回按修改时间排序的结果。它也尊重 `.gitignore`。

### 搜索策略

在大型代码库中，高效的搜索策略是:

1. **先用 `find`** 定位相关文件
2. **再用 `search`** 在文件中查找具体内容
3. **最后用 `read`** 精确读取匹配行上下文

---

## 2. 代码示例

### `find` — 文件发现

```bash
# 在 OMP 中:
"找出所有 TypeScript 源文件"
"列出 tests/ 目录下所有 .test.ts 文件"
"搜索所有名为 config 的文件"
```

对应的工具调用:
```
find: paths=["src/**/*.ts"]
find: paths=["tests/**/*.test.ts"]
find: paths=["**/config.*"]
```

### `search` — 内容搜索

```bash
"找到所有调用 deprecatedFunction 的地方"
"搜索所有 TODO 注释"
"找出硬编码的 URL（http:// 或 https://）"
```

对应的工具调用:
```
search: pattern="deprecatedFunction", paths=["src/**/*.ts"]
search: pattern="TODO", paths=["src/**"]
search: pattern="https?://\S+", paths=["src/**/*.ts"]
```

### 组合搜索工作流

```bash
"在 src/components/ 下找所有使用 useState 但没导入 React 的文件"
```

OMP 会:
1. `find: paths=["src/components/**/*.tsx"]` — 定位组件文件
2. `search: pattern="useState", paths=["src/components/**/*.tsx"]` — 找使用处
3. `read: src/components/Button.tsx:1-10` — 检查每个文件的 import

### 跨行搜索

```bash
"找出所有 async function 后面紧跟 try 块的函数"
```

```
search: pattern="async function.*\n.*try \{", paths=["src/**/*.ts"]
```

（`\n` 在 pattern 中表示换行符）

**运行方式:**
```bash
# 这些都是 OMP 在收到自然语言 prompt 后自动执行的操作。
# 你不需要手动构造这些调用。
```

---

## 3. 练习

### 练习 1: 文件发现

在你最熟悉的项目中:
1. 让 OMP 列出所有配置文件（`*.config.*`、`.env*` 等）
2. 找到所有测试文件并统计数量
3. 定位 CI/CD 相关文件

### 练习 2: 内容搜索

1. 搜索所有使用了废弃 API 的地方
2. 找出所有包含硬编码密码或密钥的行
3. 搜索项目中某个特定错误消息的所有出现位置

### 练习 3: 搜索后编辑

1. 让 OMP 找出所有使用 `var` 声明变量的地方
2. 批量将它们改为 `const`/`let`
3. 观察 OMP 如何使用搜索结果的锚点进行编辑


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 在熟悉项目中执行文件发现：
>
> ```text
> 1. "列出所有配置文件（*.config.*, .env*, tsconfig.json 等）"
>    → OMP 会多次调用 find，如：
>      find: paths=["**/*.config.*"]        → webpack.config.js, vite.config.ts 等
>      find: paths=[".env*"], gitignore: false → .env, .env.local 等
>      find: paths=["**/tsconfig*.json"]      → tsconfig.json, tsconfig.build.json
>    → 注意 .env 文件通常被 .gitignore 排除，需要 gitignore: false
>
> 2. "找到所有测试文件并统计数量"
>    → OMP 调用 find: paths=["**/*.test.*", "**/*.spec.*"]
>    → 然后可能用 bash: find . -name "*.test.ts" | wc -l 统计行数/文件数
>
> 3. "定位 CI/CD 相关文件"
>    → OMP 调用 find: paths=[".github/**", ".gitlab-ci.yml", "Jenkinsfile", "Dockerfile*"]
>    → 返回按修改时间排序的结果
> ```
>
> **思考题答案：** `find` 返回的是文件路径列表（按 mtime 排序），不是文件内容。要获取文件内容，需要再用 `read`。`find` 尊重 `.gitignore`，所以找 `.env` 等敏感文件时要用 `gitignore: false`。

> [!tip]- 练习 2 参考答案
> 内容搜索操作：
>
> ```text
> 1. "搜索所有使用了 deprecatedFunction 的地方"
>    → OMP 调用 search: pattern="deprecatedFunction" paths=["src/**/*"]
>    → 返回每个匹配的行（附锚点），可以直接用于 edit
>
> 2. "找出所有包含硬编码密码或密钥的行"
>    → OMP 调用 search: pattern="(password|secret|api[_-]?key)\s*=\s*['\"][^'\"]+['\"]"
>    → 正则搜索硬编码的键值对。注意 RE2 不支持 lookahead
>    → 更好的方式：search 多个简单 pattern 再人工/AI 审查
>
> 3. "搜索项目中 'Connection timeout' 错误消息的所有出现位置"
>    → OMP 调用 search: pattern="Connection timeout" paths=["src/**"]
>    → 如果需要跨语言搜索，去掉路径的扩展名限制
> ```
>
> **关键技巧：** RE2 正则不支持 lookahead/lookbehind。如果 pattern 太复杂，拆成多个简单搜索，再用 `read` 检查匹配上下文。

> [!tip]- 练习 3 参考答案
> 搜索后批量编辑：
>
> ```text
> 1. "找出所有使用 var 声明变量的地方"
>    → OMP 调用 search: pattern="\bvar\s+\w+" paths=["src/**/*.ts"]
>    → 返回匹配行及其锚点
>
> 2. "批量将它们改为 const/let"
>    → OMP 分析每个匹配：
>      - 如果变量从未被重新赋值 → 改为 const
>      - 如果变量被重新赋值 → 改为 let
>    → OMP 对每个匹配行执行 edit: ≔ANCHOR（替换 var → const/let）
>
> 3. 观察搜索锚点的使用：
>    → search 返回的每一行都有 LINEhh| 锚点
>    → OMP 直接将这些锚点复制到 edit 命令中
>    → 不需要重新 read 每个文件——search 的输出就是编辑的输入
> ```
>
> **思考题答案：** `search` → `edit` 工作流的高效之处：search 返回的锚点可直接被 edit 使用，跳过了中间的 read 步骤。但要注意——search 只返回匹配行，不返回上下文；如果编辑需要了解周围代码（如判断 var 是否被重新赋值），仍需要额外 read。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [[omp://tools/search|`search` 工具文档]]
- [[omp://tools/find|`find` 工具文档]]
- [[omp://tools/search_tool_bm25|BM25 搜索引擎]] — 高级语义搜索
- [[omp://natives-text-search-pipeline|原生文本搜索管道]]

---

## 常见陷阱

- **正则语法限制**: `search` 使用 RE2 引擎，不支持 lookaround（`(?=…)`、`(?<!…)`）。用行锚点或后处理替代
- **跨行搜索的 pattern**: `\n` 必须写成 `\\n` 或直接使用字面换行符
- **Gitignore 影响**: `search` 和 `find` 默认跳过 `.gitignore` 中的文件。要搜索被忽略的文件（如 `.env`），设置 `gitignore: false`
- **结果截断**: `search` 有文件数量限制（默认 10 个文件）。如果结果不全，用 `skip` 参数翻页
- **性能**: 在大型仓库中用宽泛的 pattern 搜索可能很慢。先用 `find` 缩小范围，再用 `search`
