# 11 — MCP 服务器与外部集成

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 50min
> 前置知识: 08 — 配置系统深度解析

---

## 1. 概念讲解

### MCP 是什么？

Model Context Protocol (MCP) 是一个开放协议，让 AI 代理与外部工具和数据源通信。OMP 内置了 MCP 客户端，可以连接任何 MCP 服务器。

### 三种传输方式

| 传输 | 说明 | 使用场景 |
|------|------|---------|
| `stdio` | 启动本地进程通信 | 本地工具（文件系统、数据库） |
| `http` | HTTP 流式连接 | 远程 API（GitHub、Slack） |
| `sse` | Server-Sent Events | 旧版远程服务器（仍被支持） |

### MCP 能做什么？

MCP 服务器可以提供:
- **工具 (Tools)**: 模型可调用的函数
- **资源 (Resources)**: 模型可读取的数据
- **提示模板 (Prompts)**: 预定义的提示模板

---

## 2. 代码示例

### 配置 MCP 服务器

**项目级**: `<cwd>/.omp/mcp.json`
**全局**: `~/.omp/agent/mcp.json`

```json
{
  "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/packages/coding-agent/src/config/mcp-schema.json",
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/Users/alice/projects"
      ]
    },
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer GITHUB_TOKEN"
      }
    }
  }
}
```

### Secrets 解析

OMP 的 MCP 配置支持环境变量引用:

```json
{
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_PERSONAL_ACCESS_TOKEN"
  }
}
```

当值是一个环境变量名时，OMP 会用实际的环境变量值替换。你也可以使用 `!` 前缀执行命令:

```json
{
  "headers": {
    "Authorization": "!printf 'Bearer %s' \"$GITHUB_TOKEN\""
  }
}
```

### 管理命令

在 OMP 中使用以下斜杠命令:

```bash
/mcp add         # 交互式添加服务器
/mcp list        # 列出所有服务器
/mcp test <name> # 测试特定服务器
/mcp reload      # 重新加载配置
/mcp reconnect <name>  # 重新连接
/mcp resources   # 查看资源
/mcp prompts     # 查看提示模板
```

### 禁用服务器

在 `~/.omp/agent/mcp.json` 中:

```json
{
  "disabledServers": ["github", "slack"]
}
```

**运行方式:**
```bash
# 创建 .omp/mcp.json 配置文件
# 重启 OMP 或使用 /mcp reload
# 使用 /mcp list 验证服务器已连接
```

---

## 3. 练习

### 练习 1: 连接文件系统 MCP

1. 在项目中创建 `.omp/mcp.json`
2. 配置 `@modelcontextprotocol/server-filesystem` 服务器
3. 在 OMP 中让 Agent 通过 MCP 工具操作文件
4. 对比 MCP 文件工具和 OMP 内置工具的差异

### 练习 2: GitHub MCP 集成

1. 配置 GitHub MCP 服务器（HTTP 模式）
2. 在 OMP 中查询 GitHub Issues/PRs
3. 创建 Issue 或提交 PR review

### 练习 3: 自定义 MCP 服务器

1. 使用 MCP SDK 创建一个简单的本地 MCP 服务器
2. 提供自定义工具（如查询内部 API）
3. 在 OMP 中连接并使用

---

## 4. 扩展阅读

- [MCP 配置指南](omp://mcp-config.md) — 完整的配置格式、验证规则、排错
- [MCP 协议传输](omp://mcp-protocol-transports.md)
- [MCP 运行时生命周期](omp://mcp-runtime-lifecycle.md)
- [MCP 服务器工具编写](omp://mcp-server-tool-authoring.md)
- [MCP 官方规范](https://modelcontextprotocol.io/)

---

## 常见陷阱

- **`type` 字段**: 省略 `type` 默认是 `stdio`。远程服务器必须显式设置 `"type": "http"`，否则会报 "requires command field"
- **不能同时设置 `command` 和 `url`**: 它们是互斥的——stdio 用 `command`，http/sse 用 `url`
- **环境变量解析**: 在 `.omp/mcp.json` 中，使用 `"VAR_NAME": "VAR_NAME"` 引用环境变量，使用 `"!command"` 执行命令
- **服务器名称**: 必须匹配 `^[a-zA-Z0-9_.-]{1,100}$`
- **OAuth 配置**: 像 Slack 这样的服务器需要额外的 `oauth` 和 `auth` 字段来管理 OAuth 流程
