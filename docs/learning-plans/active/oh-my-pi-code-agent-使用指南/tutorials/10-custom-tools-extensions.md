---
title: "10 — 自定义工具与扩展"
updated: 2026-06-05
---

# 10 — 自定义工具与扩展

> 所属计划: Oh My Pi Code Agent 使用指南
> 预计耗时: 60min
> 前置知识: 09 — 构建技能（Skills）

---

## 1. 概念讲解

### 自定义工具 (Custom Tools)

自定义工具是**模型可直接调用的函数**。它们通过 TypeScript/JavaScript 模块导出，OMP 加载后注入到工具注册表中。

### 扩展 (Extensions)

扩展是更全面的定制方式，能同时做:
- 注册自定义工具
- 拦截生命周期事件（`session_start`、`tool_call`、`turn_end` 等）
- 注册斜杠命令（`/my-command`）
- 自定义消息渲染

### 三者对比

| 能力 | Custom Tool | Extension | Hook |
|------|:-----------:|:---------:|:----:|
| 模型可调用 | ✓ | ✓ | ✗ |
| 拦截工具调用 | ✗ | ✓ | ✓ |
| 生命周期事件 | ✗ | ✓ | ✓ |
| 斜杠命令 | ✗ | ✓ | ✓ |
| 修改工具输出 | ✗ | ✓ | ✓ |
| API 复杂度 | 低 | 中 | 低 |

---

## 2. 代码示例

### 自定义工具

```typescript
// .omp/tools/repo-stats.ts
import type { CustomToolFactory } from "@oh-my-pi/pi-coding-agent";

const factory: CustomToolFactory = (pi) => ({
  name: "repo_stats",
  label: "Repo Stats",
  description: "统计项目的文件分布",
  parameters: pi.zod.object({
    glob: pi.zod.string().optional().default("**/*"),
  }),

  async execute(toolCallId, params, onUpdate, ctx, signal) {
    onUpdate?.({
      content: [{ type: "text", text: "正在扫描文件..." }],
    });

    const result = await pi.exec("git", [
      "ls-files", params.glob ?? "**/*",
    ], { signal, cwd: pi.cwd });

    if (result.code !== 0) {
      throw new Error(result.stderr || "git ls-files 失败");
    }

    const files = result.stdout.split("\n").filter(Boolean);
    const extCounts: Record<string, number> = {};
    for (const f of files) {
      const ext = f.includes(".") ? f.split(".").pop()! : "(无扩展名)";
      extCounts[ext] = (extCounts[ext] || 0) + 1;
    }

    const summary = Object.entries(extCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([ext, count]) => `  .${ext}: ${count} 个文件`)
      .join("\n");

    return {
      content: [{
        type: "text",
        text: `共 ${files.length} 个文件:\n${summary}`,
      }],
      details: { totalFiles: files.length, extCounts },
    };
  },
});

export default factory;
```

### 扩展

```typescript
// .omp/extensions/safety-guard.ts
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

export default function safetyGuard(pi: ExtensionAPI) {
  // 1. 拦截危险命令
  pi.on("tool_call", async (event) => {
    if (event.toolName === "bash") {
      const cmd = String(event.input.command ?? "");
      if (cmd.includes("rm -rf") || cmd.includes("DROP TABLE")) {
        if (pi.hasUI) {
          const ok = await pi.ui.confirm(
            "危险操作",
            `确认执行: ${cmd}？`,
          );
          if (!ok) return { block: true, reason: "用户取消" };
        } else {
          return { block: true, reason: "危险命令被阻止（无 UI 确认）" };
        }
      }
    }
  });

  // 2. 注册自定义工具
  const { z } = pi.zod;
  pi.registerTool({
    name: "check_security",
    label: "安全检查",
    description: "扫描代码中的安全问题",
    parameters: z.object({ path: z.string() }),
    async execute(_id, params, _signal) {
      // 实现安全检查逻辑
      return {
        content: [{ type: "text", text: `已扫描 ${params.path}` }],
      };
    },
  });

  // 3. 注册斜杠命令
  pi.registerCommand("audit", {
    description: "运行安全审计",
    handler: async (_args, ctx) => {
      ctx.ui.notify("开始安全审计...", "info");
      // 触发 agent 执行审计
    },
  });
}
```

### 钩子 (Hooks)

```typescript
// .omp/hooks/pre/redact-secrets.ts
import type { HookAPI } from "@oh-my-pi/pi-coding-agent/extensibility/hooks";

export default function redactSecrets(pi: HookAPI) {
  pi.on("tool_result", async (event) => {
    if (event.toolName !== "read" || event.isError) return;

    const redacted = event.content.map((chunk) => {
      if (chunk.type !== "text") return chunk;
      return {
        ...chunk,
        text: chunk.text.replaceAll(
          /(?:API[_-]?KEY|SECRET|TOKEN)\s*=\s*\S+/gi,
          "$1=[已隐藏]",
        ),
      };
    });

    return { content: redacted };
  });
}
```

**运行方式:**
```bash
# 自定义工具: 放在 .omp/tools/ 目录
# 扩展: 放在 .omp/extensions/ 目录
# 钩子: 放在 .omp/hooks/pre/ 或 .omp/hooks/post/

# 重启 OMP 或使用 /reload 加载
```

---

## 3. 练习

### 练习 1: 创建一个自定义工具

1. 选择你项目中反复执行的操作（如运行测试、检查代码风格）
2. 编写自定义工具封装该操作
3. 在 OMP 中验证: "使用我的工具执行 X"

### 练习 2: 创建一个安全扩展

1. 编写扩展，拦截 `bash` 工具调用
2. 黑名单特定的危险命令
3. 对有 UI 的场景要求用户确认
4. 测试: 要求 OMP 执行一个危险命令，验证扩展是否阻止

### 练习 3: 消息过滤钩子

1. 编写 `tool_result` 钩子
2. 自动隐藏输出中的 API Key 或密码
3. 测试 OMP 读取包含敏感信息的文件后的输出


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 封装"运行测试"为自定义工具：
>
> ```typescript
> // .omp/tools/run-tests.ts
> import type { CustomToolFactory } from "@oh-my-pi/pi-coding-agent";
>
> const factory: CustomToolFactory = (pi) => ({
>   name: "run_tests",
>   label: "运行测试",
>   description:
>     "运行项目测试。默认运行所有测试，可指定文件路径。返回测试结果摘要。",
>   parameters: pi.zod.object({
>     file: pi.zod.string().optional()
>       .describe("单个测试文件路径，不指定则运行所有测试"),
>     watch: pi.zod.boolean().optional().default(false)
>       .describe("是否以 watch 模式运行"),
>   }),
>
>   async execute(_toolCallId, params, onUpdate, ctx, signal) {
>     onUpdate?.({
>       content: [{ type: "text", text: "正在运行测试..." }],
>     });
>
>     const args = ["test"];
>     if (params.file) args.push(params.file);
>     if (params.watch) args.push("--watch");
>
>     // 自动检测包管理器
>     const hasBun = await pi.fs.exists("bun.lockb").catch(() => false);
>     const cmd = hasBun ? "bun" : "npm";
>
>     const result = await pi.exec(cmd, args, {
>       cwd: pi.cwd,
>       signal,
>       env: { ...process.env, CI: "true" },
>     });
>
>     if (result.code !== 0) {
>       return {
>         content: [{
>           type: "text",
>           text: `测试失败 (exit code: ${result.code}):\n${result.stderr || result.stdout}`,
>         }],
>         details: { passed: false, exitCode: result.code },
>       };
>     }
>
>     return {
>       content: [{ type: "text", text: result.stdout }],
>       details: { passed: true },
>     };
>   },
> });
>
> export default factory;
> ```
>
> 在 OMP 中使用：
>
> ```text
> "使用 run_tests 工具运行 src/utils/ 相关的测试"
> → OMP 调用 run_tests({ file: "src/utils/" })
> ```

> [!tip]- 练习 2 参考答案
> 安全扩展——拦截危险命令：
>
> ```typescript
> // .omp/extensions/safety-guard.ts
> import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
>
> export default function safetyGuard(pi: ExtensionAPI) {
>   // 危险命令黑名单（正则匹配）
>   const DANGEROUS_PATTERNS = [
>     /\brm\s+-rf\b/,
>     /\bgit\s+push\s+--force\b/,
>     /\bDROP\s+(TABLE|DATABASE)\b/i,
>     /\bDELETE\s+FROM\b/i,
>     /\bchmod\s+777\b/,
>     /\bcurl.*\|\s*(ba)?sh\b/,
>   ];
>
>   pi.on("tool_call", async (event) => {
>     if (event.toolName !== "bash") return;
>
>     const cmd = String(event.input.command ?? "");
>     const dangerous = DANGEROUS_PATTERNS.find((p) => p.test(cmd));
>
>     if (!dangerous) return;
>
>     if (pi.hasUI) {
>       const ok = await pi.ui.confirm(
>         "⚠️ 危险命令检测",
>         `以下命令可能造成不可逆的影响:\n\n  ${cmd}\n\n确认执行？`,
>       );
>       if (!ok) {
>         return {
>           block: true,
>           reason: "用户在安全确认中取消了危险命令",
>         };
>       }
>     } else {
>       // 无 UI 环境（如 CI/CD）直接阻止
>       return {
>         block: true,
>         reason: `危险命令被阻止（无 UI 确认）: ${cmd}`,
>       };
>     }
>   });
>
>   // 额外：记录所有被阻止的命令
>   pi.on("tool_result", async (event) => {
>     if (event.toolName === "bash" && event.isError) {
>       console.warn(`[SafetyGuard] bash 执行失败: ${event.content}`);
>     }
>   });
> }
> ```
>
> 测试方法：
>
> ```text
> 在 OMP 中尝试：
> "执行 rm -rf /tmp/test/"
> → 预期：安全扩展弹窗确认（有 UI）或直接阻止（无 UI）
>
> "执行 ls -la"（安全命令）
> → 预期：正常执行，不受影响
> ```

> [!tip]- 练习 3 参考答案
> 消息过滤钩子——自动隐藏密钥：
>
> ```typescript
> // .omp/hooks/pre/redact-secrets.ts
> import type { HookAPI } from "@oh-my-pi/pi-coding-agent/extensibility/hooks";
>
> export default function redactSecrets(pi: HookAPI) {
>   pi.on("tool_result", async (event) => {
>     // 只处理 read 工具的输出
>     if (event.toolName !== "read" || event.isError) return;
>
>     let changed = false;
>     const redacted = event.content.map((chunk) => {
>       if (chunk.type !== "text") return chunk;
>
>       let text = chunk.text;
>
>       // 模式 1：环境变量定义 KEY=value
>       text = text.replaceAll(
>         /(\b[A-Z][A-Z0-9_]*_(?:KEY|SECRET|TOKEN|PASSWORD))\s*=\s*[^\s\n]+/gi,
>         "$1=[已隐藏]",
>       );
>
>       // 模式 2：JSON/YAML 中的 secret 字段
>       text = text.replaceAll(
>         /"(apiKey|secretKey|password|token)"\s*:\s*"[^"]+"/gi,
>         '"$1":"[已隐藏]"',
>       );
>
>       // 模式 3：AWS Access Key ID
>       text = text.replaceAll(
>         /\bAKIA[0-9A-Z]{16}\b/g,
>         "AKIA[HIDDEN]",
>       );
>
>       if (text !== chunk.text) changed = true;
>       return { ...chunk, text };
>     });
>
>     if (changed) {
>       return { content: redacted };
>     }
>     // 无变更则不返回，让原始输出通过
>   });
> }
> ```
>
> 测试方法：
>
> ```bash
> # 创建一个测试文件含假密钥
> echo 'API_KEY=sk-test-1234567890' > test-secrets.txt
> echo 'DATABASE_PASSWORD=super-secret' >> test-secrets.txt
>
> # 在 OMP 中: "读取 test-secrets.txt"
> # 预期输出中密钥被替换为 "[已隐藏]"
> ```
>
> **思考题答案：** Hook 运行在"模型看到结果之前"——`tool_result` 钩子拦截的是工具执行结果 → 传给 LLM 的中间环节。这比在 LLM 提示中告诉它"不要输出密钥"可靠得多，因为钩子是确定性代码而非概率性提示。但钩子不能替代 secrets 系统——secrets 系统在发送给 LLM 前就完成了替换，而钩子只在特定工具结果中生效。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [[omp://custom-tools|自定义工具文档]] — 完整的 API 和加载规则
- [[omp://extensions|扩展文档]] — 事件、工具、命令注册
- [[omp://hooks|钩子文档]] — pre/post 拦截
- [[omp://extension-loading|Extensibility 加载]]

---

## 常见陷阱

- **加载时才注册**: 注册方法（`registerTool`、`registerCommand`）只在扩展加载阶段有效；运行时操作（`sendMessage`）在加载阶段不可用
- **工具名称必须唯一**: 自定义工具名不能与内置工具或其他自定义工具冲突
- **`tool_call` 错误会导致阻塞**: 如果 `tool_call` 处理器抛出异常，工具调用会被阻止（fail-closed）
- **`.md`/`.json` 文件在 tools 目录**: 这些是元数据文件，不是可执行模块，会被跳过
- **TypeScript 需要编译**: 如果使用 TypeScript 写工具/扩展，需要先编译为 JavaScript 或依赖 Bun 的 TS 支持
