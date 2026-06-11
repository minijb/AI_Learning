---
title: "09 — 构建技能（Skills）"
updated: 2026-06-05
---

# 09 — 构建技能（Skills）

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 08 — 配置系统深度解析

---

## 1. 概念讲解

### Skill 是什么？

Skill 是文件化的能力包——一个包含 `SKILL.md` 的目录。它们在 OMP 启动时被发现，并通过系统提示暴露给模型。模型可以使用 `read skill://<name>` 按需加载 Skill 的完整内容。

### Skill vs 其他扩展方式

| 方式 | 用途 | 何时使用 |
|------|------|---------|
| **Skill** | 知识/工作流指导 | 提供领域知识、编码规范、操作流程 |
| **Custom Tool** | 可调用的函数 | 需要模型调用代码执行操作 |
| **Extension** | 事件+工具+命令 | 需要拦截生命周期或注册 UI |
| **Hook** | 事件拦截 | 简单的 pre/post 过滤 |

### Skill 的发现

Skill 从两个来源发现:

1. **项目 Skill**: `<project>/.omp/skills/<name>/SKILL.md`
2. **用户 Skill**: `~/.omp/agent/skills/<name>/SKILL.md`

发现是非递归的——只有 `skills/<name>/SKILL.md` 这一层被扫描。

### SKILL.md 格式

```yaml
---
name: my-skill
description: >
  简短描述，帮助模型判断何时使用此 Skill。
  当用户做 X 时触发。
globs: ["src/**/*.py"]
alwaysApply: false
---

# Skill 正文
实际的指导内容...
```

---

## 2. 代码示例

### 创建一个简单的 Skill

```bash
# 创建目录结构
mkdir -p .omp/skills/python-best-practices/

# 创建 SKILL.md
cat > .omp/skills/python-best-practices/SKILL.md << 'EOF'
---
name: python-best-practices
description: >
  Python 编码最佳实践。当编写或审查 Python 代码时使用。
  覆盖: 类型注解、错误处理、测试模式、性能考量。
globs: ["**/*.py"]
---

# Python 编码最佳实践

## 类型注解

- 所有公共函数必须有类型注解
- 使用 `from __future__ import annotations` 延迟求值
- 复杂类型使用 `TypeAlias`

## 错误处理

- 不要裸 `except:`，至少捕获 `Exception`
- 自定义异常继承自项目基类
- 使用 `contextlib.suppress` 处理预期的忽略错误

## 测试

- 使用 pytest，不要用 unittest
- 测试文件命名: `test_<module>.py`
- 每个测试函数只测一个行为

## 性能

- 优先使用生成器而非列表推导处理大数据
- 使用 `functools.lru_cache` 缓存昂贵计算
EOF
```

### Skill 目录结构

一个完整的 Skill 可以包含额外资源:

```text
.omp/skills/my-skill/
├── SKILL.md           ← 主文件（必须）
├── templates/         ← 可选的模板文件
│   └── example.py
└── references/        ← 可选的参考文档
    └── api-docs.md
```

通过 `skill://my-skill/references/api-docs.md` 访问。

### 在 OMP 中使用 Skill

```bash
# 在 OMP 中:
# Skill 会被自动发现并出现在系统提示中。
# 你也可以直接引用:
"按照 python-best-practices skill 审查 src/api.py"
"用 skill://python-best-practices 的规范重构这个文件"
```

### 高级: `alwaysApply` Skill

如果设置 `alwaysApply: true`，Skill 内容会在**每个会话**的系统提示中注入。适用于核心编码规范:

```yaml
---
name: company-coding-standards
description: 公司编码标准，所有项目通用
alwaysApply: true
---
```

**运行方式:**
```bash
# 创建 Skill 后，重启 OMP 使其生效。
# 或在 OMP 中执行 /reload
```

---

## 3. 练习

### 练习 1: 创建你的第一个 Skill

1. 确定你的项目中反复出现的编码模式（如日志格式、错误处理模板）
2. 创建 `.omp/skills/my-conventions/SKILL.md`
3. 包含至少 3 条具体规则和代码示例
4. 在 OMP 中验证: 让它按照你的 Skill 规范生成代码

### 练习 2: 带资源的 Skill

1. 扩展 Skill，添加 `templates/` 目录
2. 放入一个常用代码模板（如 React 组件模板、API 端点模板）
3. 在 OMP 中引用模板: "用 skill://my-conventions/templates/component.tsx 创建新组件"

### 练习 3: 全局 Skill

1. 在 `~/.omp/agent/skills/` 下创建一个全局 Skill
2. 切换到不同项目，验证 Skill 仍然可用
3. 在项目中也创建同名 Skill，验证项目 Skill 优先级更高


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 创建 Skill 的完整示例——假设你的项目中反复出现的模式是"为 API 端点写 Zod 验证 + 错误处理"：
>
> ```markdown
> <!-- .omp/skills/api-endpoint-pattern/SKILL.md -->
> ---
> name: api-endpoint-pattern
> description: >
>   本项目的 API 端点编码规范。当创建或修改 API 路由时使用。
>   Next.js Route Handler + Zod 验证 + 统一错误响应格式。
> globs: ["app/api/**/route.ts"]
> ---
>
> # API 端点编码规范
>
> ## 1. 请求验证
>
> 每个 API 端点必须用 Zod schema 验证输入：
>
> ```ts
> import { z } from "zod";
>
> const CreateUserSchema = z.object({
>   name: z.string().min(1).max(100),
>   email: z.string().email(),
>   role: z.enum(["admin", "user"]).default("user"),
> });
> ```
>
> ## 2. 错误响应格式
>
> 使用统一错误格式：
>
> ```ts
> // app/api/_lib/errors.ts
> export function apiError(status: number, message: string) {
>   return Response.json({ error: { code: status, message } }, { status });
> }
> ```
>
> ## 3. 端点模板
>
> POST 端点必须使用以下模式：
>
> ```ts
> export async function POST(req: Request) {
>   try {
>     const body = await req.json();
>     const parsed = CreateUserSchema.safeParse(body);
>     if (!parsed.success) {
>       return apiError(400, parsed.error.message);
>     }
>     // ... 业务逻辑 ...
>     return Response.json({ data: result });
>   } catch (err) {
>     return apiError(500, "Internal Server Error");
>   }
> }
> ```
> ```
>
> 验证方式：
>
> ```text
> 在 OMP 中测试：
> "按照 api-endpoint-pattern skill 创建一个 POST /api/users 端点"
>
> → OMP 应自动使用 Zod 验证 + 统一错误格式
> → 检查生成的代码是否符合 SKILL.md 的规范
> ```

> [!tip]- 练习 2 参考答案
> 带资源的 Skill 扩展：
>
> ```text
> 目录结构：
> .omp/skills/react-component/SKILL.md
> .omp/skills/react-component/templates/component.tsx
> ```
>
> SKILL.md 注册模板：
>
> ```markdown
> <!-- .omp/skills/react-component/SKILL.md -->
> ---
> name: react-component
> description: >
>   本项目的 React 组件编写规范。使用 tailwindcss + TypeScript。
>   提供组件模板。创建新组件时使用。
> globs: ["src/components/**/*.tsx"]
> ---
>
> # React 组件规范
>
> 使用 skill://react-component/templates/component.tsx 创建新组件。
> 所有组件必须：
> - 使用 'use client' 指令（如果是有状态的）
> - Props 用 interface 定义
> - 默认导出
> ```
>
> 模板文件：
>
> ```tsx
> <!-- .omp/skills/react-component/templates/component.tsx -->
> "use client";
>
> import { type FC } from "react";
>
> interface Props {
>   className?: string;
>   children?: React.ReactNode;
> }
>
> const Component: FC<Props> = ({ className, children }) => {
>   return <div className={className}>{children}</div>;
> };
>
> export default Component;
> ```
>
> 在 OMP 中使用：
>
> ```text
> "用 react-component skill 和其中的 component.tsx 模板创建一个 UserCard 组件"
> ```
>
> OMP 会读取 `skill://react-component/templates/component.tsx` 的内容，将其作为模板，填充具体内容生成 `UserCard`。

> [!tip]- 练习 3 参考答案
> 全局 Skill 与优先级验证：
>
> 1. 创建全局 Skill：
>
> ```bash
> mkdir -p ~/.omp/agent/skills/global-logging/
> ```
>
> ```markdown
> <!-- ~/.omp/agent/skills/global-logging/SKILL.md -->
> ---
> name: logging-standards
> description: >
>   全局日志规范。所有项目都使用统一的日志格式。
> globs: ["src/**/*.ts"]
> ---
>
> # 日志规范
>
> - 使用 pino 作为日志库（不要用 console.log）
> - 日志格式：`[module] message { context }`
> - 禁止在循环中打日志
> ```
>
> 2. 切换到不同项目验证：
>
> ```text
> cd /path/to/project-a
> omp
> # 让 OMP 写代码 → 检查它是否参考了 logging-standards
> # 预期：即使 project-a 没有 .omp/skills/，OMP 仍加载全局 skill
>
> cd /path/to/project-b
> omp
> # 同样验证
> ```
>
> 3. 项目 Skill 覆盖测试：
>
> ```markdown
> <!-- project-a/.omp/skills/logging-standards/SKILL.md -->
> ---
> name: logging-standards
> description: 本项目的日志规范（覆盖全局）
> globs: ["src/**/*.ts"]
> ---
>
> # 日志规范
>
> - 使用 winston 而不是 pino（项目特定选择）
> - 保持其他规则不变
> ```
>
> ```text
> # 重启 OMP 后验证：
> # project-a 中写代码 → 使用 winston（项目 skill 覆盖了全局）
> # project-b 中写代码 → 使用 pino（全局 skill 生效）
> ```
>
> **思考题答案：** Skill 优先级由 provider 决定：`.omp` (100) > `.claude` (80) > `.gemini` (60)。同名 Skill 按 provider 优先级选择，更高优先级的完整替换低优先级的——不是字段级 merge。这意味着如果你在项目 `.omp/` 中创建了同名 Skill，必须包含全部需要的内容，不能只写差异部分。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [[omp://skills|Skills 系统文档]] — 完整的发现、优先级、过滤、URL 解析
- [[omp://skills/authoring-extensions|Skill 编写: 扩展开发指南]]
- [[omp://skills/examples/hello-extension/README|Skill 示例: Hello Extension]]

---

## 常见陷阱

- **目录结构必须正确**: Skill 必须是 `<skills-root>/<name>/SKILL.md`。嵌套目录（`skills/group/name/SKILL.md`）不会被发现
- **description 是必须的**: native provider 要求 Skill 有 `description` 字段，否则不会被加载
- **Skill 名称冲突**: 同名 Skill 按 provider 优先级选择——项目 `.omp` > 用户 `.omp` > `.claude` > ...
- **Skill 不自动执行代码**: Skill 是指导文档，不是可执行工具。需要模型"主动读取和遵守"
- **`skill://` URL 安全**: `skill://` 路径会被安全检查——不能使用 `..` 遍历到 Skill 目录之外
