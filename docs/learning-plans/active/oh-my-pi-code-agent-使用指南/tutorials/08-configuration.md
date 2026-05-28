# 08 — 配置系统深度解析

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 01 — OMP 概述与首次会话

---

## 1. 概念讲解

### 配置层级

OMP 的配置分为多个层级，后层覆盖前层:

```text
Schema 默认值
  ← 全局配置 (~/.omp/agent/config.yml)
    ← 项目配置 (<cwd>/.omp/settings.json)
      ← 运行时覆盖 (API/CLI 参数)
```

### 配置文件位置

| 文件 | 层级 | 用途 |
|------|------|------|
| `~/.omp/agent/config.yml` | 全局 | 所有项目的默认设置 |
| `<cwd>/.omp/config.yml` | 项目 | 当前项目的覆盖设置 |
| `~/.omp/agent/.env` | 全局 | 环境变量（API keys 等） |
| `<cwd>/.env` | 项目 | 项目级环境变量 |
| `~/.omp/agent/mcp.json` | 全局 | MCP 服务器定义 |
| `<cwd>/.omp/mcp.json` | 项目 | 项目 MCP 服务器 |

### 配置来源优先级

OMP 在发现配置时的优先级排序:

```text
.omp (native, priority 100)
  > .claude (priority 80)
    > .codex / agents / claude marketplace (priority 70)
      > .gemini (priority 60)
```

这意味着项目 `.omp/` 下的配置优先级最高。

---

## 2. 代码示例

### 全局配置 (`config.yml`)

```yaml
# ~/.omp/agent/config.yml

# 模型设置
model: "anthropic/claude-sonnet-4-5"
thinkingLevel: "medium"

# 编辑模式
edit:
  mode: "hashline"

# 会话设置
compaction:
  enabled: true

# 重试设置
retry:
  enabled: true

# 内存
memories:
  enabled: true

# 安全
secrets:
  enabled: true

# LSP
lsp:
  diagnosticsOnWrite: true

# 子代理并发
task:
  maxConcurrency: 4
  maxRecursionDepth: 3
```

### 项目配置

```json
// <cwd>/.omp/settings.json
{
  "model": "openai/gpt-4o",
  "lsp": {
    "diagnosticsOnWrite": false
  }
}
```

（项目设置覆盖全局设置）

### 环境变量 (`.env`)

```bash
# ~/.omp/agent/.env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# 可选: 搜索引擎 API keys
BRAVE_API_KEY=BS...
EXA_API_KEY=...
```

环境变量加载顺序: 进程 env > 项目 `.env` > agent `.env` > `~/.omp/.env` > `~/.env`

### 设置命令

在 OMP 中可以使用 `/settings` 命令交互式修改配置:

```bash
# 打开设置界面
/settings

# 或直接修改配置文件后重新加载
```

**运行方式:**
```bash
# 查看当前配置
cat ~/.omp/agent/config.yml

# 编辑配置
# 使用你喜欢的编辑器修改 config.yml
# 或在 OMP 中使用 /settings 命令
```

---

## 3. 练习

### 练习 1: 配置模型

1. 查看当前 OMP 使用的模型（在 TUI 状态栏）
2. 修改 `config.yml` 切换默认模型
3. 重启 OMP 验证模型切换生效
4. 尝试在 OMP 中临时切换模型（如果运行中的会话支持）

### 练习 2: 项目级覆盖

1. 在项目 `.omp/` 目录下创建 `settings.json`
2. 设置不同的 compaction 策略或编辑模式
3. 验证项目设置覆盖了全局设置

### 练习 3: 环境变量验证

1. 在 `~/.omp/agent/.env` 中添加一个自定义环境变量
2. 在 OMP 中让 Agent 读取该环境变量（通过 bash 工具 `echo $MY_VAR`）
3. 验证多层级 `.env` 的覆盖顺序

---

## 4. 扩展阅读

- [配置发现与解析](omp://config-usage.md) — 完整的优先级、来源、迁移逻辑
- [设置 Schema 定义](omp://config-usage.md)
- [环境变量参考](omp://environment-variables.md) — 所有可用的环境变量
- [Extension 加载](omp://extension-loading.md)

---

## 常见陷阱

- **YAML vs JSON**: `config.yml` 使用 YAML 格式，`settings.json` 使用 JSON。格式混用会导致解析失败
- **配置缓存**: 修改配置文件后需要重启 OMP 或使用 `/reload` 才能生效
- **环境变量不会自动暴露**: 子代理和 bash 工具的环境变量是过滤后的——敏感变量（API keys）会被自动清除
- **`PI_*` 环境变量**: OMP 特定的环境变量以 `PI_` 为前缀。`.env` 文件中的 `OMP_*` 变量会自动映射为 `PI_*`
- **迁移行为**: 如果你从旧版 OMP 升级，`settings.json` 会自动迁移到 `config.yml`（旧文件重命名为 `.bak`）
