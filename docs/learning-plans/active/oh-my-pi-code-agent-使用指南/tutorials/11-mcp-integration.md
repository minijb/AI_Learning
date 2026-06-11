---
title: "11 — MCP 服务器与外部集成"
updated: 2026-06-05
---

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


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 配置文件系统 MCP 服务器：
>
> ```json
> // .omp/mcp.json
> {
>   "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/packages/coding-agent/src/config/mcp-schema.json",
>   "mcpServers": {
>     "filesystem": {
>       "command": "npx",
>       "args": [
>         "-y",
>         "@modelcontextprotocol/server-filesystem",
>         "/path/to/allowed/directory"
>       ]
>     }
>   }
> }
> ```
>
> 在 OMP 中使用：
> ```text
> 1. 重启 OMP 或 /mcp reload
> 2. /mcp list → 确认 filesystem 已连接
> 3. "通过 MCP 的 filesystem 工具列出 /path/to/allowed/directory 的内容"
> ```
>
> MCP 文件工具 vs OMP 内置工具对比：
>
> | 维度 | MCP filesystem | OMP 内置 (read/write/edit) |
> |------|---------------|---------------------------|
> | 路径范围 | 仅限配置时指定的目录 | 整个文件系统（项目范围内） |
> | 操作粒度 | 文件级读写、目录列表 | 行级编辑、行范围、结构摘要 |
> | 安全模型 | 白名单目录访问 | 信任 Agent 判断 |
> | 额外能力 | 文件移动/复制/搜索 | SQLite 读取、压缩包、URL |
> | 适用场景 | 外部数据共享、sandboxed 访问 | 项目代码编辑 |
>
> **思考题答案：** MCP filesystem 适合"让 Agent 访问项目外的受限文件系统区域"（如共享数据目录、配置文件仓库），而 OMP 内置工具适合"在项目内做精确编辑"。MCP 服务器跑在独立进程中，崩溃不影响 OMP 主进程。两者可以共存——Agent 根据路径选择用哪个工具。

> [!tip]- 练习 2 参考答案
> GitHub MCP 集成：
>
> ```json
> // .omp/mcp.json（或 ~/.omp/agent/mcp.json）
> {
>   "$schema": "...",
>   "mcpServers": {
>     "github": {
>       "type": "http",
>       "url": "https://api.githubcopilot.com/mcp/",
>       "headers": {
>         "Authorization": "Bearer GITHUB_TOKEN"
>       }
>     }
>   },
>   "env": {
>     "GITHUB_TOKEN": "GITHUB_PERSONAL_ACCESS_TOKEN"
>   }
> }
> ```
>
> 环境变量配置：
> ```bash
> # 在 GitHub Settings → Developer settings → Personal access tokens 创建 token
> # 需要 repo、issues、pull_requests 权限
> export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_xxxxxxxxxxxx"
> ```
>
> 在 OMP 中使用：
> ```text
> "查询本仓库的 open Issues"
> "列出最近的 5 个 PR"
> "创建一个 Issue：标题 'Refactor auth module'，描述 '将认证逻辑从 JWT 迁移到 session-based'"
> "审查 PR #42 的代码变更并给出 review 意见"
> ```
>
> **思考题答案：** GitHub MCP 使用 HTTP 传输而非 stdio——这是因为它连接的是远程 API 而非本地进程。HTTP 模式支持流式响应和 OAuth 认证流程。`env` 字段中的 `GITHUB_TOKEN` 映射让 OMP 从进程环境变量中读取实际的 token 值，避免在配置文件中硬编码密钥。

> [!tip]- 练习 3 参考答案
> 自定义 MCP 服务器（Python 示例，使用 `mcp` SDK）：
>
> ```python
> # my-mcp-server/server.py
> import asyncio
> import json
> from mcp.server import Server, NotificationOptions
> from mcp.server.models import InitializationCapabilities
> from mcp.server.stdio import stdio_server
>
> server = Server("internal-api-server")
>
> @server.list_tools()
> async def list_tools():
>     return [
>         {
>             "name": "query_internal_api",
>             "description": "查询内部 API。参数: endpoint (路径), method (GET/POST)",
>             "inputSchema": {
>                 "type": "object",
>                 "properties": {
>                     "endpoint": {"type": "string", "description": "API 路径，如 /users"},
>                     "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
>                 },
>                 "required": ["endpoint"],
>             },
>         }
>     ]
>
> @server.call_tool()
> async def call_tool(name: str, arguments: dict):
>     if name == "query_internal_api":
>         endpoint = arguments["endpoint"]
>         method = arguments.get("method", "GET")
>         # 模拟：实际应调用内部 HTTP API
>         result = {
>             "status": "ok",
>             "endpoint": endpoint,
>             "method": method,
>             "data": {"message": f"Response from {endpoint}"},
>         }
>         return [{"type": "text", "text": json.dumps(result, indent=2)}]
>     raise ValueError(f"Unknown tool: {name}")
>
> async def main():
>     async with stdio_server() as (read_stream, write_stream):
>         await server.run(
>             read_stream,
>             write_stream,
>             InitializationCapabilities(
>                 sampling={}, experimental={}, tools={}
>             ),
>         )
>
> if __name__ == "__main__":
>     asyncio.run(main())
> ```
>
> MCP 配置：
> ```json
> {
>   "mcpServers": {
>     "internal-api": {
>       "command": "python",
>       "args": ["my-mcp-server/server.py"]
>     }
>   }
> }
> ```
>
> 在 OMP 中：
> ```text
> "/mcp list" → 确认 internal-api 已连接
> "使用 internal-api 的 query_internal_api 工具查询 /users 端点"
> ```
>
> **思考题答案：** MCP 使用 stdio 作为默认传输方式——OMP 启动子进程，通过 stdin/stdout 进行 JSON-RPC 通信。这个设计的优势是：服务器可以用任何语言编写（Python、Go、Rust...），只需能读写 stdin/stdout 并实现 JSON-RPC 协议。服务器崩溃时 OMP 检测到进程退出，可以自动重启——进程隔离保证了故障不会波及 OMP 主进程。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [[omp://mcp-config|MCP 配置指南]] — 完整的配置格式、验证规则、排错
- [[omp://mcp-protocol-transports|MCP 协议传输]]
- [[omp://mcp-runtime-lifecycle|MCP 运行时生命周期]]
- [[omp://mcp-server-tool-authoring|MCP 服务器工具编写]]
- [MCP 官方规范](https://modelcontextprotocol.io/)

---

## 常见陷阱

- **`type` 字段**: 省略 `type` 默认是 `stdio`。远程服务器必须显式设置 `"type": "http"`，否则会报 "requires command field"
- **不能同时设置 `command` 和 `url`**: 它们是互斥的——stdio 用 `command`，http/sse 用 `url`
- **环境变量解析**: 在 `.omp/mcp.json` 中，使用 `"VAR_NAME": "VAR_NAME"` 引用环境变量，使用 `"!command"` 执行命令
- **服务器名称**: 必须匹配 `^[a-zA-Z0-9_.-]{1,100}$`
- **OAuth 配置**: 像 Slack 这样的服务器需要额外的 `oauth` 和 `auth` 字段来管理 OAuth 流程
