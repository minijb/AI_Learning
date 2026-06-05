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
