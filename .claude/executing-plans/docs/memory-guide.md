# Memory Guide — 执行记忆系统

> 跨会话保持上下文。让智能体在下次启动时，5 秒内了解当前已有产出。

---

## 为什么需要 Memory

计划执行往往跨越多个会话：
- 用户说"先做到这里，下次继续"
- 会话意外中断
- 复杂计划需要多天完成

**没有 memory 的后果：**
- 每次启动都重新阅读全部代码
- 重复实现已完成的函数
- 忘记之前的关键决策和理由
- 上下文窗口浪费在已知的产出上

**Memory 的作用：**
- 快速恢复：新会话优先读 memory，5 秒了解现状
- 避免重复：已创建的函数、文件一目了然
- 决策可追溯：为什么选方案 A 而非 B，记录在案

---

## Memory 追踪的 5 类工件

| 分类 | 记录内容 | 示例 |
|------|---------|------|
| **文件产出** | 创建/修改/删除的文件路径 + 操作类型 | `src/auth/login.ts` (新增) |
| **关键函数/类** | 函数名、所在文件、签名 | `AuthService` — `class AuthService` |
| **变量/常量** | 变量名、值/类型、作用域 | `MAX_RETRY = 3` (全局常量) |
| **关键决策** | 日期、决策内容、理由、替代方案 | 用 JWT 而非 Session |
| **内容/配置** | 环境变量、配置键、内容摘要 | `JWT_SECRET` — JWT 签名密钥 |

---

## 存储位置

| 计划模式 | Memory 位置 | 格式 |
|---------|------------|------|
| **Full Plan** | `<plan-dir>/memory.md` | 独立文件，含 5 个分类表格 |
| **Quick Plan** | 计划 `.md` 文件中 `## 执行记忆` 节 | 内联单行表格 |

---

## 何时更新 Memory

**必须更新：**
- 创建了新文件或模块
- 新增了关键函数/类/接口
- 做出了影响后续步骤的技术决策
- 添加了重要的环境变量或配置

**不需要更新：**
- 临时变量、调试代码
- 纯格式化改动
- 已记录在计划步骤中的常规操作

**更新时机：** 每完成一个步骤后，或产生重要工件后立即更新。

---

## 更新示例

### 文件产出

```markdown
## 文件产出

| 文件路径 | 操作(新增/修改/删除) | 关联步骤 | 说明 |
|---------|-------------------|---------|------|
| `src/auth/service.ts` | 新增 | Step 1 | 认证服务核心逻辑 |
| `src/auth/controller.ts` | 新增 | Step 2 | REST API 控制器 |
| `tests/auth.test.ts` | 新增 | Step 3 | 单元测试覆盖 90%+ |
```

### 关键函数 / 类

```markdown
## 关键函数 / 类

| 名称 | 所在文件 | 签名/定义 | 用途 |
|------|---------|----------|------|
| `AuthService` | `src/auth/service.ts` | `class AuthService` | 用户认证业务逻辑 |
| `hashPassword` | `src/auth/utils.ts` | `async function hashPassword(pwd: string): Promise<string>` | bcrypt 密码哈希 |
| `validateToken` | `src/auth/jwt.ts` | `function validateToken(token: string): Payload` | JWT 验证中间件 |
```

### 变量 / 常量

```markdown
## 变量 / 常量

| 名称 | 值 / 类型 | 作用域 | 说明 |
|------|----------|--------|------|
| `JWT_SECRET` | `string` | 环境变量 | 从 `process.env.JWT_SECRET` 读取 |
| `MAX_RETRY` | `3` (number) | 全局常量 | 登录失败重试次数 |
| `TOKEN_EXPIRY` | `24h` (string) | 模块常量 | JWT 默认有效期 |
```

### 关键决策

```markdown
## 关键决策

| 日期 | 决策 | 理由 | 替代方案 |
|------|------|------|---------|
| 2024-01-15 | 用 JWT 而非 Session | 无状态、易水平扩展、适合移动端 | Session + Redis |
| 2024-01-16 | bcrypt cost factor = 12 | 安全与性能平衡（~250ms/hash） | cost=10（更快但较弱） |
```

### 内容 / 配置

```markdown
## 内容 / 配置

| 键 / 路径 | 内容摘要 | 关联 |
|-----------|---------|------|
| `.env.example` | `JWT_SECRET=`, `DB_URL=` | 新增认证相关环境变量 |
| `docker-compose.yml` | 未添加新服务 | 认证逻辑在应用层，不依赖新容器 |
```

---

## 跨会话恢复流程

```
1. 启动 → 运行 plan-status（查看活跃计划）
2. 读取 exec-plan.md / quick-plan.md（了解目标和步骤）
3. 读取 memory.md（快速了解当前产出）
4. 读取 progress.txt（查看上次执行到哪）
5. 决定：从哪一步继续
```

**优先查看 memory，再决定是否需要深入阅读代码。**

例如：memory 中已记录 `AuthService` 类在 `src/auth/service.ts` 中实现，新会话可以直接从集成步骤开始，不必重新阅读 `AuthService` 的源码。

---

## Memory 质量检查清单

好的 memory 应该能回答这些问题：

- [ ] 如果一个新开发者加入，能否通过 memory 快速了解已有产出？
- [ ] 能否在不阅读源码的情况下，知道关键函数的名称和位置？
- [ ] 能否理解之前做出的关键决策及其理由？
- [ ] 配置和环境变量是否都已记录？

如果答案是"否"，补充 memory 后再继续执行。
