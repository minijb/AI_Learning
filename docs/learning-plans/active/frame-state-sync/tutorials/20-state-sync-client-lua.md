---
title: "状态同步客户端（Lua 定制框架）"
updated: 2026-06-05
---

# 状态同步客户端（Lua 定制框架）

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [[17-lag-compensation|17-延迟补偿]]

---

## 1. 概念讲解

### 1.1 为什么需要自研 Lua 状态同步框架？

第 18 节我们用 Unity NGO 构建了状态同步客户端，第 19 节用了 Unreal 的 Replication Graph。它们都是引擎强绑定的方案——NGO 是 Unity 专用，Replication Graph 是 Unreal 专用。但大厂的现实是：**同一个游戏项目可能在三个引擎上跑**。

以腾讯某 MOBA 项目为例：
- **Cocos2d-x**：海外低端 Android 设备（Cocos 的 C++ 渲染层 + Lua 脚本层）
- **Unity**：国内 Android 主流渠道（渠道 SDK 集成方便）
- **Unreal**：PC 版 / 主机版（高画质需求）

如果每一版都重写一遍状态同步代码，维护成本是天文数字。解决方案：**把状态同步的核心逻辑写在 Lua 里，让它跨引擎共用**。

```
┌───────────────────────────────────────────────────────────┐
│                  Lua 状态同步框架                           │
│  ┌──────────┬───────────┬──────────┬──────────┬────────┐ │
│  │StateSync │  Entity   │ SyncVar  │   RPC    │ Interp │ │
│  │   Mgr    │  System   │  System  │  System  │System  │ │
│  └────┬─────┴─────┬─────┴────┬─────┴────┬─────┴────┬───┘ │
│       │           │          │          │          │      │
│  ┌────┴───────────┴──────────┴──────────┴──────────┴───┐ │
│  │              引擎适配层 (Thin Adapter)                │ │
│  │  每个引擎只需实现: Socket / Timer / Log / Entity API  │ │
│  └────┬────────────────────┬────────────────────┬───────┘ │
│       ▼                    ▼                    ▼         │
│  ┌─────────┐         ┌─────────┐         ┌─────────┐     │
│  │  Cocos  │         │  Unity  │         │ Unreal  │     │
│  │ Lua VM  │         │  xLua   │         │ slua/   │     │
│  │ (built- │         │   VM    │         │ UnLua   │     │
│  │  in)    │         │         │         │   VM    │     │
│  └─────────┘         └─────────┘         └─────────┘     │
└───────────────────────────────────────────────────────────┘
```

这与第 10 节的帧同步 Lua 框架思路一致——**Lua 做调度和协议，C/C++ 引擎做渲染和平台能力**。但状态同步的 Lua 框架与帧同步的 Lua 框架有本质差异。

### 1.2 与帧同步 Lua 框架的核心差异

| 维度 | 帧同步 Lua 框架（第 10 节） | 状态同步 Lua 框架（本节） |
|------|---------------------------|--------------------------|
| **Lua 层职责** | 执行**确定性游戏逻辑**（移动/技能/伤害） | 接收状态、发送输入、做预测和插值 |
| **服务器角色** | 转发输入，不执行逻辑 | **执行所有权威逻辑**，Lua 客户端是"哑终端" |
| **确定性要求** | 极高——每帧 Hash 必须一致 | **无**——服务器计算结果就是真相 |
| **延迟处理** | 帧缓冲 + 追赶 | 客户端预测 + 服务端和解 + 实体插值 |
| **C 层绑定** | 定点数库、确定性随机数 | Socket、Timer、Render Entity API |
| **反外挂** | C 层 Hash 校验 | 服务器权威天然防作弊 |
| **热更新** | 战斗逻辑可热更 | **整个同步框架**都可以热更 |

核心差异一句话总结：

> 帧同步 Lua 框架 = **Lua 跑逻辑，C 做渲染**。状态同步 Lua 框架 = **Lua 做客户端表现和网络，服务器(C++/Go)做逻辑**。

### 1.3 状态同步 Lua 框架的运行时架构

```
客户端每帧 Tick 流程:
┌───────────────────────────────────────────────────────────┐
│  C 引擎层 (60fps 渲染循环)                                  │
│    │                                                       │
│    ├─ 1. 轮询输入 (键盘/触摸/手柄)                           │
│    │     → InputQueue:push(input)                          │
│    │                                                       │
│    ├─ 2. 调用 Lua: StateSyncMgr:tick(dt)                   │
│    │     │                                                 │
│    │     ├─ 2a. recv_packets()   — 从 Socket 收包           │
│    │     │   ├─ EntityUpdateMsg  → entity:apply_sync()     │
│    │     │   ├─ EntityCreateMsg  → entity:spawn()         │
│    │     │   ├─ EntityDestroyMsg → entity:destroy()       │
│    │     │   ├─ S2C_RPC_Msg      → rpc:dispatch()         │
│    │     │   └─ ACK_Msg          → rpc:ack()              │
│    │     │                                                 │
│    │     ├─ 2b. send_inputs()    — 上传输入（预测）          │
│    │     │   └─ InputQueue:flush() → C2S_RPC              │
│    │     │                                                 │
│    │     ├─ 2c. predict()        — 客户端本地预测            │
│    │     │   └─ PredictedState:apply_input()              │
│    │     │                                                 │
│    │     └─ 2d. interpolate()    — 远程实体插值              │
│    │         └─ Interpolator:update(dt) → 引擎渲染位置      │
│    │                                                       │
│    └─ 3. 渲染 (使用插值后的位置)                              │
└───────────────────────────────────────────────────────────┘
```

**关键设计决策**：状态同步 Lua 框架**不需要**锁步（Lockstep）中的帧缓冲区，也不需要在 Lua 层维护完整的世界状态。Lua 层只维护客户端关心的子集：
- 自己角色的预测状态
- 视野内其他实体的插值状态
- 未确认的 RPC 队列

### 1.4 引擎适配层设计

与我们第 10 节设计的绑定接口完全一致——但状态同步客户端的接口需求更简单：

```c
// engine_bindings_ss.h — 状态同步客户端需要的 C 绑定
// 比帧同步少: 不再需要 engine_random_int, engine_get_current_frame,
//             engine_frame_log（状态同步不用帧号做确定性校验）

// ─── Socket ───
int32_t engine_socket_connect(const char* host, uint16_t port);
int32_t engine_socket_send(int32_t handle, const uint8_t* data, int32_t len);
int32_t engine_socket_recv(int32_t handle, uint8_t* buf, int32_t max_len);
void    engine_socket_close(int32_t handle);

// ─── Timer ───
int64_t engine_get_timestamp_ms(void); // 高精度时间戳，用于插值

// ─── Entity API (表现层) ───
entity_handle engine_entity_create(const char* prefab, float x, float y, float z);
void engine_entity_set_position(entity_handle ent, float x, float y, float z);
void engine_entity_set_rotation(entity_handle ent, float angle);
void engine_entity_play_animation(entity_handle ent, const char* anim, int32_t loop);
void engine_entity_destroy(entity_handle ent);
void engine_entity_set_health_bar(entity_handle ent, float ratio); // UI血条
```

可以看到，状态同步不需要定点数、不需要确定性随机数、不需要帧日志——因为客户端不"计算"权威结果。

---

## 2. 代码示例

以下 7 个模块构成完整的状态同步 Lua 客户端框架。模块间依赖关系：

```
game_demo.lua  ← 最顶层: 组装所有模块，驱动游戏循环
    ├── state_sync_mgr.lua  ← 核心调度器
    │       ├── rpc_system.lua    ← RPC 收发
    │       └── input_queue.lua   ← 输入缓冲
    ├── entity.lua          ← 实体管理
    │       └── sync_var.lua     ← 属性复制
    └── interpolator.lua    ← 远程实体插值
```

所有代码为 Lua 5.1+ / LuaJIT 兼容。使用 `--- @param` / `--- @return` 注释以兼容 Lua Language Server。

### 2.1 sync_var.lua — 属性复制核心（~80 行）

`SyncVar` 是状态同步最基础的抽象：标记一个字段需要从服务器同步到客户端，并用脏标记（Dirty Flag）机制只传输变更的字段。

```lua
-- ============================================
-- sync_var.lua — SyncVar: 标记需要同步的字段
-- ============================================
-- 核心思想:
--   1. 服务器维护属性的"当前值"和"上次同步值"
--   2. 每次 Tick 结束时，比较两者，只把变更的属性打包发送
--   3. 客户端收到后直接覆盖本地值，触发 OnChanged 回调
--
-- 使用方式:
--   local health = SyncVar.new(100)          -- 初始值 100
--   health:set(80)                            -- 标记脏
--   health:is_dirty() → true
--   local changed_fields = health:collect_changes() -- 返回 {value=80}
--   health:clear_dirty()                      -- 清除脏标记
--   health:on_changed(function(old, new) end) -- 注册变更回调
-- ============================================

local SyncVar = {}
SyncVar.__index = SyncVar

--- 创建一个同步变量
--- @param initial_value any    初始值
--- @param on_changed function|nil 客户端收到更新时的回调(old_val, new_val)
function SyncVar.new(initial_value, on_changed)
    local self = setmetatable({}, SyncVar)
    self._value = initial_value           -- 当前值
    self._last_synced = initial_value     -- 上次同步给客户端的值（服务器端使用）
    self._dirty = false                   -- 脏标记
    self._on_changed = on_changed         -- 变更回调
    return self
end

--- 获取当前值
function SyncVar:get()
    return self._value
end

--- 设置新值（自动标记脏）
--- @param new_value any
function SyncVar:set(new_value)
    if self._value ~= new_value then
        local old = self._value
        self._value = new_value
        self._dirty = true
        if self._on_changed then
            self._on_changed(old, new_value)
        end
    end
end

--- 服务器端：静默设置（不触发脏标记，不触发回调）
--- 用于初始化或从数据库加载
--- @param value any
function SyncVar:set_silent(value)
    self._value = value
    self._last_synced = value
    self._dirty = false
end

--- 客户端收到服务器更新时调用
--- @param server_value any  服务器传来的权威值
function SyncVar:apply_server_update(server_value)
    local old = self._value
    self._value = server_value
    self._last_synced = server_value
    self._dirty = false                     -- 清除本地脏标记（以服务器为准）
    if old ~= server_value and self._on_changed then
        self._on_changed(old, server_value)
    end
end

--- 客户端预测更新（不改变 _last_synced，只改变 _value）
--- 用于客户端预测——预测值可能被服务器覆盖
--- @param predicted_value any
function SyncVar:predict(predicted_value)
    local old = self._value
    self._value = predicted_value
    -- 注意：不改变 _dirty 和 _last_synced
    -- 这样服务器值到达时，apply_server_update 可以正确回滚
    if old ~= predicted_value and self._on_changed then
        self._on_changed(old, predicted_value)
    end
end

--- 脏标记查询
function SyncVar:is_dirty()
    return self._dirty
end

--- 获取需要同步的变更（仅服务器端调用）
--- @return table|nil  {value = new_value} 或 nil（无变更）
function SyncVar:collect_changes()
    if not self._dirty then return nil end
    return { value = self._value }
end

--- 清除脏标记（同步完成后调用）
function SyncVar:clear_dirty()
    self._dirty = false
    self._last_synced = self._value
end

--- 注册变更回调
--- @param cb function(old_val, new_val)
function SyncVar:on_changed(cb)
    self._on_changed = cb
end

return SyncVar
```

### 2.2 entity.lua — 实体系统（~150 行）

实体管理：创建、销毁、属性变更事件分发。每个实体持有若干 SyncVar。

```lua
-- ============================================
-- entity.lua — 网络实体管理
-- ============================================
-- 实体生命周期:
--   Server: create_entity() → 设置属性 → spawn() 通知客户端
--   Client: recv EntityCreateMsg → spawn_local() → 注册到 entity_registry
--
-- 实体销毁:
--   Server: destroy_entity() → 发送 EntityDestroyMsg
--   Client: recv EntityDestroyMsg → destroy_local() → 清理表现对象
--
-- 属性更新:
--   Server: entity.sync_vars.health:set(80) → 标记脏
--           → collect_dirty_vars() 收集变更
--           → 打包成 EntityUpdateMsg 发送
--   Client: recv EntityUpdateMsg → entity:apply_update(msg)
--           → 逐个 sync_var:apply_server_update()
-- ============================================

local SyncVar = require("sync_var")

local Entity = {}
Entity.__index = Entity

--- 实体类型枚举
Entity.TYPE_PLAYER  = 1
Entity.TYPE_NPC     = 2
Entity.TYPE_PROJECTILE = 3
Entity.TYPE_ITEM    = 4

--- 创建一个网络实体（服务器端）
--- @param entity_id   number  全局唯一 ID（由服务器分配）
--- @param entity_type number  实体类型
--- @param owner_id    number  所属玩家 ID（0=无主）
function Entity.new(entity_id, entity_type, owner_id)
    local self = setmetatable({}, Entity)
    self.entity_id   = entity_id
    self.entity_type = entity_type
    self.owner_id    = owner_id or 0

    -- SyncVar 集合: 键为属性名，值为 SyncVar 对象
    self.sync_vars = {}

    -- 预定义默认属性（所有实体都有）
    self.sync_vars.x     = SyncVar.new(0)
    self.sync_vars.y     = SyncVar.new(0)
    self.sync_vars.angle = SyncVar.new(0)

    -- 表现层引用（客户端使用）
    self.render_handle = nil    -- engine_entity_create 返回的 handle

    -- 事件回调
    self._on_spawn_callbacks   = {}  -- 实体在客户端创建时触发
    self._on_destroy_callbacks = {}  -- 实体销毁时触发

    -- 存活标记
    self._alive = true

    return self
end

--- 添加一个 SyncVar
--- @param name string
--- @param initial_value any
--- @param on_changed function|nil
function Entity:add_sync_var(name, initial_value, on_changed)
    self.sync_vars[name] = SyncVar.new(initial_value, on_changed)
end

--- 获取 SyncVar 当前值
--- @param name string
function Entity:get(name)
    local sv = self.sync_vars[name]
    return sv and sv:get()
end

--- 设置 SyncVar（服务器端，标记脏）
--- @param name string
--- @param value any
function Entity:set(name, value)
    local sv = self.sync_vars[name]
    if sv then
        sv:set(value)
    end
end

--- 客户端预测设置（不标记为同步脏，但触发本地回调）
--- @param name string
--- @param value any
function Entity:predict_set(name, value)
    local sv = self.sync_vars[name]
    if sv then
        sv:predict(value)
    end
end

--- 收集所有脏属性（仅服务器端）
--- @return table  { [attr_name] = {value = new_val}, ... }
function Entity:collect_dirty_vars()
    local changes = {}
    for name, sv in pairs(self.sync_vars) do
        if sv:is_dirty() then
            changes[name] = sv:collect_changes()
        end
    end
    if next(changes) == nil then
        return nil  -- 无变更
    end
    return changes
end

--- 清除所有脏标记（同步完成后）
function Entity:clear_all_dirty()
    for _, sv in pairs(self.sync_vars) do
        sv:clear_dirty()
    end
end

--- 客户端：应用服务器下发的属性更新
--- @param update_data table  { [attr_name] = {value = val}, ... }
function Entity:apply_update(update_data)
    for name, data in pairs(update_data) do
        local sv = self.sync_vars[name]
        if sv then
            sv:apply_server_update(data.value)
        end
    end
end

--- 注册生成回调（客户端创建实体时）
--- @param cb function(entity)
function Entity:on_spawn(cb)
    table.insert(self._on_spawn_callbacks, cb)
end

--- 注册销毁回调
--- @param cb function(entity)
function Entity:on_destroy(cb)
    table.insert(self._on_destroy_callbacks, cb)
end

--- 触发生成事件
function Entity:fire_spawn()
    for _, cb in ipairs(self._on_spawn_callbacks) do
        cb(self)
    end
end

--- 触发销毁事件
function Entity:fire_destroy()
    self._alive = false
    for _, cb in ipairs(self._on_destroy_callbacks) do
        cb(self)
    end
end

--- 是否存活
function Entity:is_alive()
    return self._alive
end

--- 获取所有属性名列表
function Entity:get_sync_var_names()
    local names = {}
    for name in pairs(self.sync_vars) do
        table.insert(names, name)
    end
    return names
end

return Entity
```

### 2.3 rpc_system.lua — RPC 系统（~120 行）

RPC 系统负责客户端↔服务器的可靠事件通信。核心设计：
- **C2S_RPC**：客户端→服务器（如 `FireSkill`、`MoveTo`）
- **S2C_RPC**：服务器→客户端（如 `PlayEffect`、`ShowDamage`）
- 每个 RPC 携带**序列号 (seq)**，服务器对 C2S RPC 回复 ACK
- 客户端维护未确认 RPC 队列，收到 ACK 后移除

```lua
-- ============================================
-- rpc_system.lua — RPC 收发系统
-- ============================================
-- 协议格式 (简化，实际应使用 protobuf/flatbuffers):
--   C2S_RPC:  { type="c2s_rpc", seq=N, method="FireSkill", params={...} }
--   S2C_RPC:  { type="s2c_rpc", method="PlayEffect", params={...} }
--   ACK:      { type="ack", seq=N }
--
-- 可靠性保证:
--   1. C2S RPC 发送后进入 pending 队列，带超时重传
--   2. 服务器处理 RPC 后回复 ACK，客户端从 pending 移除
--   3. 重传最多 3 次，超时则触发 on_timeout 回调
-- ============================================

local RPCSystem = {}
RPCSystem.__index = RPCSystem

-- RPC 超时时间（毫秒）
local RPC_TIMEOUT_MS = 3000
local RPC_MAX_RETRIES = 3

function RPCSystem.new(send_fn, is_server)
    local self = setmetatable({}, RPCSystem)
    -- 发送函数: function(data_str)  — 由 StateSyncMgr 注入
    self._send_fn = send_fn

    -- 当前序列号
    self._seq_counter = 0

    -- 未确认的 C2S RPC: { [seq] = { method, params, send_time, retries, on_ack_cb, on_timeout_cb } }
    self._pending_rpcs = {}

    -- S2C RPC 处理器注册: { [method] = function(params) }
    self._s2c_handlers = {}

    -- 是否是服务器端（服务器不需要 pending 队列和重传）
    self._is_server = is_server or false

    return self
end

--- 发送 C2S RPC（客户端→服务器）
--- @param method   string   方法名，如 "MoveTo", "FireSkill"
--- @param params   table    参数表
--- @param on_ack   function|nil  收到服务器 ACK 时回调
--- @param on_timeout function|nil  超时未确认时回调
--- @return number  分配的序列号
function RPCSystem:send_c2s(method, params, on_ack, on_timeout)
    self._seq_counter = self._seq_counter + 1
    local seq = self._seq_counter

    local msg = {
        type   = "c2s_rpc",
        seq    = seq,
        method = method,
        params = params,
    }

    -- 序列化并发送
    self:_send_message(msg)

    -- 加入待确认队列
    self._pending_rpcs[seq] = {
        method        = method,
        params        = params,
        send_time     = self:_now_ms(),
        retries       = 0,
        on_ack        = on_ack,
        on_timeout    = on_timeout,
    }

    return seq
end

--- 处理收到的 ACK
--- @param seq number
function RPCSystem:handle_ack(seq)
    local pending = self._pending_rpcs[seq]
    if pending then
        if pending.on_ack then
            pending.on_ack()
        end
        self._pending_rpcs[seq] = nil
    end
end

--- 注册 S2C RPC 处理器
--- @param method  string
--- @param handler function(params)
function RPCSystem:register_s2c_handler(method, handler)
    self._s2c_handlers[method] = handler
end

--- 发送 S2C RPC（服务器→所有客户端/特定客户端）
--- 在服务器端调用此方法；在客户端，这是向服务器请求广播
--- 实际上是: 客户端 send_c2s 到服务器，服务器转发为 S2C RPC
--- 但为了完整性，我们也提供一个服务器端的便捷方法
--- @param method string
--- @param params table
function RPCSystem:send_s2c(method, params)
    local msg = {
        type   = "s2c_rpc",
        method = method,
        params = params,
    }
    self:_send_message(msg)
end

--- 分发收到的 S2C RPC
--- @param msg table  已解析的消息
function RPCSystem:dispatch_s2c(msg)
    local handler = self._s2c_handlers[msg.method]
    if handler then
        handler(msg.params)
    end
end

--- 每帧 Tick: 检查超时重传
function RPCSystem:tick()
    local now = self:_now_ms()
    for seq, pending in pairs(self._pending_rpcs) do
        if now - pending.send_time > RPC_TIMEOUT_MS then
            if pending.retries < RPC_MAX_RETRIES then
                -- 重传
                pending.retries = pending.retries + 1
                pending.send_time = now
                local msg = {
                    type   = "c2s_rpc",
                    seq    = seq,
                    method = pending.method,
                    params = pending.params,
                }
                self:_send_message(msg)
            else
                -- 超时放弃
                if pending.on_timeout then
                    pending.on_timeout()
                end
                self._pending_rpcs[seq] = nil
            end
        end
    end
end

--- 获取待确认 RPC 数量
function RPCSystem:get_pending_count()
    local count = 0
    for _ in pairs(self._pending_rpcs) do
        count = count + 1
    end
    return count
end

-- ── 内部方法 ─────────────────────────────────────────────

--- 序列化并发送消息
--- @param msg table
function RPCSystem:_send_message(msg)
    -- 简化序列化: 使用 Lua 字符串拼接
    -- 生产环境应使用 protobuf / flatbuffers / MessagePack
    local json = require("json") -- 假设有 json 库
    local data = json.encode(msg)
    self._send_fn(data)
end

--- 获取当前毫秒时间戳
function RPCSystem:_now_ms()
    -- 依赖 C 引擎绑定: engine.get_timestamp_ms()
    if engine and engine.get_timestamp_ms then
        return engine.get_timestamp_ms()
    end
    -- fallback: 使用 os.clock()（不精确但可作为本地模拟）
    return math.floor(os.clock() * 1000)
end

return RPCSystem
```

### 2.4 input_queue.lua — 输入缓冲与客户端预测（~60 行）

输入队列的设计目标：让客户端**立即**响应玩家输入（预测），同时将输入可靠地发送给服务器。

```lua
-- ============================================
-- input_queue.lua — 输入队列与预测状态
-- ============================================
-- 每个逻辑帧产生的输入进入队列
-- 帧结束时:
--   1. 将本帧输入立即应用到本地实体（客户端预测）
--   2. 将输入通过 C2S RPC 发送给服务器
--   3. 记录 (tick_id, input) 到预测历史
--   4. 服务器返回权威状态时，移除已确认的 tick，回滚不一致的状态
--
-- 数据结构:
--   self._history = {
--     [1] = { tick_id=100, input={move_dir={1,0}, actions={"attack"}}, predicted_state={...} },
--     [2] = { tick_id=101, ... },
--     ...
--   }
-- ============================================

local InputQueue = {}
InputQueue.__index = InputQueue

--- 最大保留的预测历史条目数
local MAX_HISTORY = 256

function InputQueue.new()
    local self = setmetatable({}, InputQueue)
    self._queue = {}           -- 本帧待发送的输入
    self._history = {}         -- 预测历史
    self._tick_counter = 0     -- 本地 tick 计数器
    return self
end

--- 添加一个输入动作
--- @param action table  如 { type="move", dx=1, dy=0 } 或 { type="attack", target_id=5 }
function InputQueue:push_action(action)
    table.insert(self._queue, action)
end

--- 获取本帧累计的所有输入并推进 tick
--- @return number tick_id, table inputs
function InputQueue:flush()
    if #self._queue == 0 then
        -- 空输入帧也推进 tick，保持连续性
        self._tick_counter = self._tick_counter + 1
        return self._tick_counter, {}
    end

    self._tick_counter = self._tick_counter + 1
    local tick_id = self._tick_counter
    local inputs = self._queue
    self._queue = {}  -- 清空本帧队列

    return tick_id, inputs
end

--- 记录预测状态（客户端执行输入后的结果）
--- @param tick_id   number
--- @param inputs    table    本 tick 的输入
--- @param predicted_state table  预测后的状态快照 { x, y, health, ... }
function InputQueue:record_prediction(tick_id, inputs, predicted_state)
    table.insert(self._history, {
        tick_id  = tick_id,
        inputs   = inputs,
        predicted = predicted_state,
    })

    -- 限制历史长度
    while #self._history > MAX_HISTORY do
        table.remove(self._history, 1)
    end
end

--- 服务器确认了某个 tick（通过服务器状态更新隐式确认）
--- 删除该 tick 及之前的所有预测记录
--- @param server_tick number  服务器处理到的最新 tick
function InputQueue:acknowledge(server_tick)
    while #self._history > 0 and self._history[1].tick_id <= server_tick do
        table.remove(self._history, 1)
    end
end

--- 获取从指定 tick 之后的所有未确认输入（用于和解重放）
--- @param from_tick number
--- @return table  { {tick_id, inputs}, ... }
function InputQueue:get_unacked_inputs(from_tick)
    local result = {}
    for _, entry in ipairs(self._history) do
        if entry.tick_id > from_tick then
            table.insert(result, { tick_id = entry.tick_id, inputs = entry.inputs })
        end
    end
    return result
end

--- 获取预测历史长度
function InputQueue:get_history_size()
    return #self._history
end

--- 清空所有预测历史（用于强制和解）
function InputQueue:clear_history()
    self._history = {}
end

return InputQueue
```

### 2.5 state_sync_mgr.lua — 核心状态管理器（~200 行）

这是框架的大脑：协调网络收发包、实体生命周期、RPC 分发、预测和插值。

```lua
-- ============================================
-- state_sync_mgr.lua — 核心状态同步管理器
-- ============================================
-- 单例模式，管理整个状态同步生命周期
-- 职责:
--   1. 连接服务器 / 断开连接
--   2. 接收和分发服务器消息
--   3. 管理实体注册表 (本地实体 vs 远程实体)
--   4. 驱动输入队列和 RPC 系统
--   5. 协调预测与和解
-- ============================================

local Entity      = require("entity")
local RPCSystem   = require("rpc_system")
local InputQueue  = require("input_queue")
local Interpolator = require("interpolator")

local StateSyncMgr = {}
StateSyncMgr.__index = StateSyncMgr

function StateSyncMgr.new()
    local self = setmetatable({}, StateSyncMgr)

    -- ── 连接状态 ──
    self._socket = -1
    self._connected = false
    self._client_id = 0           -- 服务器分配的客户端 ID

    -- ── 子系统 ──
    self._rpc = nil               -- RPCSystem (在 connect 时创建)
    self._input_queue = InputQueue.new()
    self._interpolator = Interpolator.new()

    -- ── 实体注册表 ──
    self._entities = {}           -- { [entity_id] = Entity }
    self._local_player_id = 0     -- 本地玩家的 entity_id

    -- ── 收包缓冲 ──
    self._recv_buffer = ""

    -- ── 回调注册 ──
    self._on_connected_cb     = nil
    self._on_disconnected_cb  = nil
    self._on_entity_spawned   = nil   -- function(entity)
    self._on_entity_destroyed = nil   -- function(entity_id)

    return self
end

-- ── 连接管理 ────────────────────────────────────────────

--- 连接到服务器
--- @param host string
--- @param port number
function StateSyncMgr:connect(host, port)
    -- 假设 engine.socket_connect 已被 C 层注册
    self._socket = engine.socket_connect(host, port)
    if self._socket < 0 then
        error("StateSyncMgr: 连接失败 " .. host .. ":" .. port)
    end

    self._connected = true
    self._rpc = RPCSystem.new(
        function(data) engine.socket_send(self._socket, data, #data) end,
        false  -- 客户端模式
    )

    -- 注册内置 RPC 处理器
    self:_register_internal_handlers()

    if self._on_connected_cb then
        self._on_connected_cb()
    end
end

--- 断开连接
function StateSyncMgr:disconnect()
    self._connected = false
    if self._socket >= 0 then
        engine.socket_close(self._socket)
        self._socket = -1
    end
    -- 清理所有实体
    for eid, ent in pairs(self._entities) do
        if ent.render_handle then
            engine.entity_destroy(ent.render_handle)
        end
    end
    self._entities = {}
    if self._on_disconnected_cb then
        self._on_disconnected_cb()
    end
end

-- ── 回调注册 ────────────────────────────────────────────

function StateSyncMgr:on_connected(cb)
    self._on_connected_cb = cb
end

function StateSyncMgr:on_disconnected(cb)
    self._on_disconnected_cb = cb
end

function StateSyncMgr:on_entity_spawned(cb)
    self._on_entity_spawned = cb
end

function StateSyncMgr:on_entity_destroyed(cb)
    self._on_entity_destroyed = cb
end

-- ── 实体查询 ────────────────────────────────────────────

function StateSyncMgr:get_entity(entity_id)
    return self._entities[entity_id]
end

function StateSyncMgr:get_local_player()
    return self._entities[self._local_player_id]
end

function StateSyncMgr:get_client_id()
    return self._client_id
end

-- ── 输入接口 ────────────────────────────────────────────

--- 添加玩家输入（由上层调用，每帧可调用多次）
--- @param action table
function StateSyncMgr:push_input(action)
    self._input_queue:push_action(action)
end

-- ── 主循环 ─────────────────────────────────────────────

--- 每帧 Tick（由 C 引擎渲染循环驱动，60fps）
--- @param dt number  帧间隔（秒）
function StateSyncMgr:tick(dt)
    if not self._connected then return end

    -- 1. 收包
    self:_receive_packets()

    -- 2. 发送本帧输入
    self:_send_inputs()

    -- 3. RPC 超时检查
    if self._rpc then
        self._rpc:tick()
    end

    -- 4. 插值更新（远程实体平滑移动）
    self._interpolator:update(dt)
end

-- ── 内部: 收包处理 ──────────────────────────────────────

function StateSyncMgr:_receive_packets()
    while true do
        local buf = engine.socket_recv(self._socket, 65536)
        if not buf or #buf == 0 then break end

        self._recv_buffer = self._recv_buffer .. buf

        -- 按换行符分割消息（简化协议：每个 JSON 消息以 \n 结尾）
        while true do
            local newline_pos = string.find(self._recv_buffer, "\n", 1, true)
            if not newline_pos then break end

            local msg_str = string.sub(self._recv_buffer, 1, newline_pos - 1)
            self._recv_buffer = string.sub(self._recv_buffer, newline_pos + 1)

            local ok, msg = pcall(self._decode_json, msg_str)
            if ok and msg then
                self:_dispatch_message(msg)
            end
        end
    end
end

--- 分发单条消息
function StateSyncMgr:_dispatch_message(msg)
    local msg_type = msg.type

    if msg_type == "handshake" then
        -- 握手响应：服务器分配 client_id 和初始世界状态
        self._client_id = msg.client_id
        self._local_player_id = msg.local_player_entity_id
        -- 创建初始实体
        if msg.entities then
            for _, ent_data in ipairs(msg.entities) do
                self:_spawn_entity(ent_data)
            end
        end

    elseif msg_type == "entity_create" then
        self:_spawn_entity(msg)

    elseif msg_type == "entity_destroy" then
        self:_destroy_entity(msg.entity_id)

    elseif msg_type == "entity_update" then
        -- 批量属性更新
        if msg.updates then
            for _, update in ipairs(msg.updates) do
                local ent = self._entities[update.entity_id]
                if ent then
                    ent:apply_update(update.changes)
                end
            end
        end

    elseif msg_type == "s2c_rpc" then
        if self._rpc then
            self._rpc:dispatch_s2c(msg)
        end

    elseif msg_type == "ack" then
        if self._rpc then
            self._rpc:handle_ack(msg.seq)
        end

    elseif msg_type == "server_state" then
        -- 服务端权威状态快照（用于和解）
        self:_handle_server_state(msg)
    end
end

--- 处理服务端权威状态（和解）
function StateSyncMgr:_handle_server_state(msg)
    local local_player = self._entities[self._local_player_id]
    if not local_player then return end

    -- 应用服务器位置（覆盖预测值）
    if msg.x then
        local_player.sync_vars.x:apply_server_update(msg.x)
    end
    if msg.y then
        local_player.sync_vars.y:apply_server_update(msg.y)
    end

    -- 确认已处理的输入
    if msg.last_processed_tick then
        self._input_queue:acknowledge(msg.last_processed_tick)
    end
end

-- ── 内部: 发送输入 ──────────────────────────────────────

function StateSyncMgr:_send_inputs()
    local tick_id, inputs = self._input_queue:flush()
    if #inputs == 0 then
        -- 空输入帧不发包（节省带宽）
        -- 但 tick_id 已经推进，保持本地预测的连续性
        return
    end

    if not self._rpc then return end

    -- 发送输入给服务器
    self._rpc:send_c2s("PlayerInput", {
        tick_id = tick_id,
        inputs  = inputs,
    })

    -- 本地预测：立即应用输入到本地玩家
    self:_apply_local_prediction(tick_id, inputs)
end

--- 本地预测：在收到服务器确认前立即表现
function StateSyncMgr:_apply_local_prediction(tick_id, inputs)
    local player = self._entities[self._local_player_id]
    if not player then return end

    -- 记录预测前的状态快照
    local snapshot = {
        x = player:get("x"),
        y = player:get("y"),
    }

    -- 应用输入（简化：只处理移动）
    for _, action in ipairs(inputs) do
        if action.type == "move" then
            local speed = 200  -- 像素/秒，假设 60 tick/s = ~3.3 像素/tick
            local new_x = (player:get("x") or 0) + (action.dx or 0) * speed / 60
            local new_y = (player:get("y") or 0) + (action.dy or 0) * speed / 60
            player:predict_set("x", new_x)
            player:predict_set("y", new_y)
        end
    end

    -- 记录预测（用于可能的重放）
    self._input_queue:record_prediction(tick_id, inputs, snapshot)
end

-- ── 内部: 实体生命周期 ──────────────────────────────────

function StateSyncMgr:_spawn_entity(ent_data)
    local ent = Entity.new(ent_data.entity_id, ent_data.entity_type, ent_data.owner_id)

    -- 应用初始属性
    if ent_data.attrs then
        for name, value in pairs(ent_data.attrs) do
            ent:add_sync_var(name, value)
        end
    end

    -- 追加自定义 SyncVar（根据实体类型）
    if ent_data.entity_type == Entity.TYPE_PLAYER then
        ent:add_sync_var("health", ent_data.attrs and ent_data.attrs.health or 100)
        ent:add_sync_var("max_health", ent_data.attrs and ent_data.attrs.max_health or 100)
        ent:add_sync_var("level", 1)
        ent:add_sync_var("name", ent_data.attrs and ent_data.attrs.name or "Unknown")
    elseif ent_data.entity_type == Entity.TYPE_NPC then
        ent:add_sync_var("health", ent_data.attrs and ent_data.attrs.health or 50)
        ent:add_sync_var("ai_state", "idle")
    end

    -- 创建表现层对象
    local prefab = self:_get_prefab_name(ent_data.entity_type)
    ent.render_handle = engine.entity_create(prefab,
        ent:get("x") or 0, ent:get("y") or 0, 0)

    -- 注册到插值器（非本地玩家的实体需要插值）
    if ent_data.entity_id ~= self._local_player_id then
        self._interpolator:register_entity(ent)
    end

    self._entities[ent_data.entity_id] = ent
    ent:fire_spawn()

    if self._on_entity_spawned then
        self._on_entity_spawned(ent)
    end
end

function StateSyncMgr:_destroy_entity(entity_id)
    local ent = self._entities[entity_id]
    if not ent then return end

    ent:fire_destroy()

    if ent.render_handle then
        engine.entity_destroy(ent.render_handle)
    end

    self._interpolator:unregister_entity(entity_id)
    self._entities[entity_id] = nil

    if self._on_entity_destroyed then
        self._on_entity_destroyed(entity_id)
    end
end

--- 根据实体类型获取表现层 prefab 名
function StateSyncMgr:_get_prefab_name(entity_type)
    local names = {
        [Entity.TYPE_PLAYER]     = "player_warrior",
        [Entity.TYPE_NPC]        = "npc_slime",
        [Entity.TYPE_PROJECTILE] = "fx_fireball",
        [Entity.TYPE_ITEM]       = "item_chest",
    }
    return names[entity_type] or "default"
end

-- ── 内部: RPC 处理器注册 ────────────────────────────────

function StateSyncMgr:_register_internal_handlers()
    if not self._rpc then return end

    -- 示例：服务器通知播放特效
    self._rpc:register_s2c_handler("PlayEffect", function(params)
        -- 在指定位置播放特效（纯客户端表现，无逻辑影响）
        local x, y = params.x, params.y
        local fx_handle = engine.entity_create(params.effect_name, x, y, 0)
        -- 特效播完后自动销毁（由 C 引擎的粒子系统管理）
    end)

    -- 示例：服务器通知显示伤害数字
    self._rpc:register_s2c_handler("ShowDamage", function(params)
        -- 假设 C 引擎有 UI 文字系统
        -- engine.ui_show_floating_text(params.target_entity_id, params.damage, params.is_critical)
    end)

    -- 示例：服务器通知实体销毁
    self._rpc:register_s2c_handler("EntityDeath", function(params)
        local ent = self._entities[params.entity_id]
        if ent then
            engine.entity_play_animation(ent.render_handle, "death", 0)
        end
    end)
end

-- ── 工具方法 ────────────────────────────────────────────

--- 发送 C2S RPC（便捷方法）
--- @param method string
--- @param params table
function StateSyncMgr:send_rpc(method, params)
    if self._rpc then
        return self._rpc:send_c2s(method, params)
    end
end

--- JSON 解码（简化实现，生产环境使用 cjson / dkjson）
function StateSyncMgr:_decode_json(str)
    -- 这里假设全局有 json.decode
    -- 如果 C 引擎没有绑定 JSON，可以用纯 Lua 的 dkjson
    if json and json.decode then
        return json.decode(str)
    end
    -- 极度简化的 fallback（仅用于演示）
    return load("return " .. str)()
end

return StateSyncMgr
```

### 2.6 interpolator.lua — 实体插值器（~100 行）

远程实体（非本地玩家）的位置不会被客户端预测——它们完全依赖服务器下发的状态更新。服务器每 50-100ms 发一次位置更新，客户端需要在两次更新之间做平滑插值，否则远程玩家会"闪现"。

```lua
-- ============================================
-- interpolator.lua — 实体插值器
-- ============================================
-- 核心思想:
--   服务器每 50~100ms 下发一次实体位置（EntityUpdateMsg）
--   客户端在两个快照之间做线性插值（Lerp），使移动平滑
--
-- 时间线:
--   Server tick:   ...100...105...110...115...120...
--   Client recv:        100       110       120
--                       │         │         │
--                       ▼         ▼         ▼
--                  snapshot[0] snapshot[1] snapshot[2]
--                               │
--                               ├─ render_time = server_time - INTERP_DELAY
--                               │  (渲染比服务器落后 INTERP_DELAY 毫秒)
--                               │
--                               ▼
--                          lerp(snapshot[0], snapshot[1], t)
--
-- INTERP_DELAY 通常设为 2 倍平均网络延迟（如 100ms → 200ms）
-- ============================================

local Interpolator = {}
Interpolator.__index = Interpolator

-- 插值延迟（毫秒）：渲染落后服务器的时间
local INTERP_DELAY_MS = 100

-- 每个实体的快照缓冲区最大长度
local MAX_SNAPSHOTS = 64

function Interpolator.new()
    local self = setmetatable({}, Interpolator)
    -- 实体快照: { [entity_id] = { {server_time, x, y, angle}, ... } }
    self._snapshots = {}
    return self
end

--- 注册一个需要插值的实体
--- @param entity Entity
function Interpolator:register_entity(entity)
    self._snapshots[entity.entity_id] = {
        entity   = entity,
        buffer   = {},  -- 快照环形缓冲区
        head     = 1,   -- 最新快照索引
        count    = 0,
    }
end

--- 注销实体
--- @param entity_id number
function Interpolator:unregister_entity(entity_id)
    self._snapshots[entity_id] = nil
end

--- 添加一个服务器快照
--- 在 state_sync_mgr 收到 entity_update 时调用
--- @param entity_id number
--- @param server_time_ms number  服务器时间戳
--- @param x number
--- @param y number
--- @param angle number
function Interpolator:add_snapshot(entity_id, server_time_ms, x, y, angle)
    local entry = self._snapshots[entity_id]
    if not entry then return end

    local snap = {
        time  = server_time_ms,
        x     = x,
        y     = y,
        angle = angle or 0,
    }

    -- 追加到缓冲区
    entry.count = entry.count + 1
    if entry.count > MAX_SNAPSHOTS then
        -- 移除最旧的快照
        entry.head = entry.head % MAX_SNAPSHOTS + 1
        entry.count = MAX_SNAPSHOTS
    end
    local idx = (entry.head + entry.count - 1) % MAX_SNAPSHOTS
    if idx == 0 then idx = MAX_SNAPSHOTS end
    entry.buffer[idx] = snap
end

--- 每帧更新：对所有注册的实体做插值
--- @param dt number  帧间隔（秒），未使用——插值基于时间戳
function Interpolator:update(dt)
    -- 渲染时间 = 当前真实时间 - 插值延迟
    -- 我们落后于服务器，所以在服务器时间轴上回退 INTERP_DELAY_MS
    local now_ms = self:_now_ms()
    local render_time = now_ms - INTERP_DELAY_MS

    for entity_id, entry in pairs(self._snapshots) do
        if entry.count >= 2 then
            local snap_from, snap_to, t = self:_find_interpolation_pair(entry, render_time)
            if snap_from and snap_to then
                -- 线性插值
                local interp_x = snap_from.x + (snap_to.x - snap_from.x) * t
                local interp_y = snap_from.y + (snap_to.y - snap_from.y) * t
                local interp_angle = snap_from.angle + (snap_to.angle - snap_from.angle) * t

                -- 更新到表现层
                local ent = entry.entity
                if ent and ent.render_handle then
                    engine.entity_set_position(ent.render_handle, interp_x, interp_y, 0)
                    engine.entity_set_rotation(ent.render_handle, interp_angle)
                end
            end
        elseif entry.count == 1 then
            -- 只有一个快照，直接使用
            local snap = entry.buffer[entry.head]
            local ent = entry.entity
            if ent and ent.render_handle then
                engine.entity_set_position(ent.render_handle, snap.x, snap.y, 0)
                engine.entity_set_rotation(ent.render_handle, snap.angle)
            end
        end
    end
end

--- 找到渲染时间点前后的两个快照
--- @param entry table
--- @param render_time number
--- @return table|nil snap_from, table|nil snap_to, number t (0~1)
function Interpolator:_find_interpolation_pair(entry, render_time)
    local buf = entry.buffer
    local max_snap = MAX_SNAPSHOTS

    -- 将环形缓冲区展平为有序数组
    local sorted = {}
    for i = 1, entry.count do
        local idx = (entry.head + i - 2) % max_snap + 1
        table.insert(sorted, buf[idx])
    end

    -- 找到 render_time 前后的两个快照
    local from, to = nil, nil
    for i = 1, #sorted - 1 do
        if sorted[i].time <= render_time and sorted[i + 1].time >= render_time then
            from = sorted[i]
            to   = sorted[i + 1]
            break
        end
    end

    if not from then
        -- render_time 在所有快照之后 → 使用最新的两个快照外推
        if #sorted >= 2 then
            from = sorted[#sorted - 1]
            to   = sorted[#sorted]
        end
    end
    if not to and #sorted >= 1 then
        -- 只有一个快照
        from = sorted[1]
        to   = sorted[1]
    end

    -- 计算插值系数 t
    local t = 0
    if from and to and from.time ~= to.time then
        t = (render_time - from.time) / (to.time - from.time)
        t = math.max(0, math.min(1, t))  -- 限制在 [0, 1]
    elseif from and to then
        t = 0
    end

    return from, to, t
end

--- 当前时间戳
function Interpolator:_now_ms()
    if engine and engine.get_timestamp_ms then
        return engine.get_timestamp_ms()
    end
    return math.floor(os.clock() * 1000)
end

return Interpolator
```

### 2.7 game_demo.lua — 完整 Demo：俯视角 ARPG（~100 行）

将以上所有模块组装成一个可运行的俯视角 ARPG Demo。玩家可以移动、攻击怪物，看到血条变化。

```lua
-- ============================================
-- game_demo.lua — 俯视角 ARPG 完整 Demo
-- ============================================
-- 功能:
--   1. 连接到服务器
--   2. WASD 移动（客户端预测 + 服务端权威）
--   3. 空格键攻击最近的怪物（C2S RPC）
--   4. 看到怪物血条随攻击减少（属性复制）
--   5. 看到远程玩家平滑移动（插值）
--   6. 怪物死亡后播放死亡动画（S2C RPC）
--
-- 运行方式:
--   1. 启动模拟服务器 (见附录)
--   2. lua game_demo.lua
--   3. 在终端使用 WASD 移动，空格攻击
-- ============================================

local StateSyncMgr = require("state_sync_mgr")

-- ── 模拟服务器 ──────────────────────────────────────────
-- 在真实项目中，这部分是 C++/Go 服务器
-- 这里用 Lua 协程模拟一个本地服务器，方便测试框架

local MockServer = {}
MockServer.__index = MockServer

function MockServer.new(mgr, tick_interval_ms)
    local self = setmetatable({}, MockServer)
    self._mgr = mgr
    self._tick_interval = tick_interval_ms or 50  -- 20 tick/s
    self._tick_count = 0
    self._monsters = {}  -- 模拟怪物的服务端状态
    self._next_entity_id = 100

    -- 生成几只怪物
    for i = 1, 3 do
        local mid = self._next_entity_id
        self._next_entity_id = self._next_entity_id + 1
        self._monsters[mid] = {
            entity_id = mid,
            x = math.random(200, 600),
            y = math.random(200, 600),
            health = 50,
            max_health = 50,
        }
    end

    return self
end

function MockServer:start()
    -- 模拟握手
    self:_send_handshake()
    -- 模拟怪物生成
    for mid, data in pairs(self._monsters) do
        self:_send_entity_create(mid, data)
    end
end

function MockServer:tick()
    self._tick_count = self._tick_count + 1

    -- 模拟发送怪物位置更新（简单的AI巡逻）
    if self._tick_count % 10 == 0 then  -- 每 500ms 更新
        local updates = {}
        for mid, data in pairs(self._monsters) do
            data.x = data.x + math.random(-5, 5)
            data.y = data.y + math.random(-5, 5)
            table.insert(updates, {
                entity_id = mid,
                changes = {
                    x = { value = data.x },
                    y = { value = data.y },
                    health = { value = data.health },
                }
            })
        end
        self:_send_msg({
            type = "entity_update",
            updates = updates,
        })
    end
end

function MockServer:_send_msg(msg)
    local json = require("json")
    local data = json.encode(msg) .. "\n"
    -- 直接注入到 StateSyncMgr 的收包缓冲区（绕过 Socket）
    local mgr = self._mgr
    mgr._recv_buffer = mgr._recv_buffer .. data
end

function MockServer:_send_handshake()
    self:_send_msg({
        type = "handshake",
        client_id = 1,
        local_player_entity_id = 1,
        entities = {
            {
                entity_id = 1,
                entity_type = 1,  -- PLAYER
                owner_id = 1,
                attrs = { x = 400, y = 300, health = 100, max_health = 100, name = "Hero" },
            },
        },
    })
end

function MockServer:_send_entity_create(entity_id, data)
    self:_send_msg({
        type = "entity_create",
        entity_id = entity_id,
        entity_type = 2,  -- NPC
        owner_id = 0,
        attrs = {
            x = data.x, y = data.y,
            health = data.health, max_health = data.max_health,
        },
    })
end

-- ── 主程序 ──────────────────────────────────────────────

-- 初始化
local mgr = StateSyncMgr.new()

-- 注册回调
mgr:on_connected(function()
    print("[Demo] 已连接到服务器！")
end)

mgr:on_entity_spawned(function(ent)
    print(string.format("[Demo] 实体生成: id=%d, type=%d, owner=%d",
        ent.entity_id, ent.entity_type, ent.owner_id))
end)

mgr:on_entity_destroyed(function(entity_id)
    print(string.format("[Demo] 实体销毁: id=%d", entity_id))
end)

-- 启动模拟服务器（真实项目中替换为 engine.socket_connect）
local server = MockServer.new(mgr, 50)
server:start()

-- ── 游戏主循环 ─────────────────────────────────────────
-- 在真实项目中，这个循环由 C 引擎的渲染循环驱动
-- 这里用简单的忙等循环模拟

local running = true
local last_tick = os.clock()

print("=== 俯视角 ARPG Demo ===")
print("操作: WASD 移动, 空格 攻击")
print("输入 'quit' 退出")
print("")

-- 简单的键盘输入模拟（读取标准输入）
local function read_input()
    -- 在真实项目中，输入由 C 引擎的输入系统采集
    -- 这里用终端输入模拟
    local f = io.stdin
    -- 非阻塞读取不可用，用协程或直接跳过
    -- 简化：假设每帧读取一行
    return nil
end

-- 模拟帧循环（60fps）
local function game_loop()
    local frame_count = 0
    while running do
        local now = os.clock()
        local dt = now - last_tick
        last_tick = now

        frame_count = frame_count + 1

        -- 模拟输入: 每 60 帧（1秒）随机移动
        -- 在实际项目中替换为真实输入
        if frame_count % 60 == 0 then
            local dx = math.random(-1, 1)
            local dy = math.random(-1, 1)
            if dx ~= 0 or dy ~= 0 then
                mgr:push_input({ type = "move", dx = dx, dy = dy })
            end
        end
        -- 每 180 帧（3秒）攻击
        if frame_count % 180 == 0 then
            mgr:push_input({ type = "attack" })
        end

        -- Tick 状态同步管理器
        mgr:tick(dt)

        -- Tick 模拟服务器
        server:tick()

        -- 显示状态
        local player = mgr:get_local_player()
        if player and frame_count % 30 == 0 then  -- 每 0.5 秒打印
            local x = player:get("x") or 0
            local y = player:get("y") or 0
            local hp = player:get("health") or 0
            print(string.format("[Tick %d] 位置: (%.0f, %.0f), 血量: %d/100",
                frame_count, x, y, hp))
        end

        -- 限制帧率
        local elapsed = os.clock() - now
        local frame_time = 1 / 60
        if elapsed < frame_time then
            -- 简单的 sleep 模拟
            local wait_until = now + frame_time
            while os.clock() < wait_until do end
        end

        -- 演示模式：运行 600 帧（10 秒）后退出
        if frame_count >= 600 then
            running = false
        end
    end
end

-- 运行
print("开始游戏循环...")
game_loop()
print("Demo 结束。")

-- 清理
mgr:disconnect()

print("\n=== 框架模块总结 ===")
print("state_sync_mgr.lua  — 核心调度器: 收发包、实体生命周期、RPC分发")
print("entity.lua         — 网络实体: SyncVar集合、生命周期事件")
print("sync_var.lua       — 属性复制: 脏标记、变更收集、预测支持")
print("rpc_system.lua     — RPC系统: C2S/S2C、序列号+ACK可靠传输")
print("input_queue.lua    — 输入队列: 预测历史、待确认输入追踪")
print("interpolator.lua   — 插值器: 快照缓冲、线性插值平滑移动")
```

### 2.8 模拟服务器完整版（补充）

为方便测试，这里给出 `MockServer` 处理攻击 RPC 的完整逻辑：

```lua
-- ============================================
-- mock_server_ext.lua — 模拟服务器扩展
-- ============================================
-- 将以下代码追加到 MockServer 类中

-- MockServer 处理 PlayerInput RPC（在 :tick() 中调用）
function MockServer:process_player_input(tick_id, inputs)
    local player_x, player_y = 400, 300  -- 简化：固定位置追踪

    for _, action in ipairs(inputs) do
        if action.type == "move" then
            player_x = player_x + (action.dx or 0) * 3
            player_y = player_y + (action.dy or 0) * 3
        elseif action.type == "attack" then
            -- 服务器处理攻击：找最近的怪物
            local closest_mid, closest_dist = nil, math.huge
            for mid, data in pairs(self._monsters) do
                if data.health > 0 then
                    local dist = math.sqrt((data.x - player_x)^2 + (data.y - player_y)^2)
                    if dist < closest_dist then
                        closest_dist = dist
                        closest_mid = mid
                    end
                end
            end
            if closest_mid and closest_dist < 100 then
                local monster = self._monsters[closest_mid]
                monster.health = math.max(0, monster.health - 15)

                -- 发送 S2C RPC: 显示飘字
                self:_send_msg({
                    type = "s2c_rpc",
                    method = "ShowDamage",
                    params = {
                        target_entity_id = closest_mid,
                        damage = 15,
                        is_critical = math.random() < 0.1,
                    },
                })

                -- 如果怪物死亡
                if monster.health <= 0 then
                    self:_send_msg({
                        type = "s2c_rpc",
                        method = "EntityDeath",
                        params = { entity_id = closest_mid },
                    })
                    -- 3秒后移除尸体
                    -- (简化：省略定时器逻辑)
                end
            end
        end
    end

    -- 发送服务端权威位置（和解用）
    self:_send_msg({
        type = "server_state",
        x = player_x,
        y = player_y,
        last_processed_tick = tick_id,
    })
end
```

---

## 3. 练习

### 练习 1: 基础 — 补全 SyncVar 的类型系统（30min）

当前 `sync_var.lua` 中的 `SyncVar:set()` 用 `~=` 做相等比较，这对于 number 和 string 是安全的，但对于 table 会始终认为不相等（table 比较的是引用）。

**任务**：
1. 为 `SyncVar` 增加 `type` 参数（`"number"`, `"string"`, `"bool"`, `"vec2"`, `"vec3"`）
2. 对 `"vec2"` 类型实现深度比较：当 `{x, y}` 的两个分量都相等时，不触发 dirty
3. 对 `"number"` 类型增加阈值比较：当 `|new - old| < epsilon` 时，不触发 dirty（避免浮点抖动导致频繁同步）
4. 编写测试用例验证：连续 set 相同 vec2 值 100 次，`is_dirty()` 只在第一次返回 true

**预期结果**：一个类型安全的 SyncVar，能正确处理复合类型和浮点阈值。

### 练习 2: 进阶 — 实现基于优先级的 RPC 合并（45min）

当前 `rpc_system.lua` 对每个 C2S RPC 单独发送一个包。在高频操作场景（如 MOBA 中每秒 10+ 次移动指令），这会产生大量小包，浪费带宽。

**任务**：
1. 为 `RPCSystem` 增加**发送队列**：不立即发送，而是每 50ms 批量发送一次
2. 为不同 RPC 方法分配优先级：
   - `MoveInput` → 低优先级（合并：连续多次移动只保留最后一次）
   - `FireSkill` → 高优先级（不合并，立即发送）
   - `ChatMessage` → 普通优先级（合并后批量发送）
3. 实现合并逻辑：对同一 `method` 的低优先级 RPC，在队列中只保留最新的一条
4. 测量优化效果：模拟客户端每秒 30 次 `MoveInput` + 3 次 `FireSkill`，对比优化前后的发包数量

**预期结果**：发包数从 33/秒降至约 23/秒（20 个合并移动包 + 3 个技能包），带宽节省 ~30%。

### 练习 3: 挑战 — 实现完整的客户端预测 + 和解（60min）

当前 `state_sync_mgr.lua` 只对位置做了简单的客户端预测，没有实现真正的**和解 (Reconciliation)**——即服务器返回权威位置后，回滚预测状态并重放未确认的输入。

**任务**：
1. 在 `StateSyncMgr` 中增加 `_predicted_moves` 表，记录每个已预测 tick 的 `{tick_id, from_x, from_y, to_x, to_y}`
2. 收到 `server_state` 消息时：
   - 比较服务器位置与预测位置，如果偏差超过阈值（如 5 像素），触发和解
   - 将本地玩家位置回滚到服务器权威位置
   - 从 `InputQueue` 获取该 tick 之后的所有未确认输入
   - 在回滚位置上重新应用这些输入（重放）
3. 增加**和解平滑**：不回滚到服务器位置后"闪现"，而是在接下来的 5 帧内平滑过渡
4. 测试场景：模拟服务器延迟从 50ms 突增到 300ms，观察和解是否正确工作

**预期结果**：延迟突增时本地移动可能出现短暂"回拉"，但随后平滑回到正确位置，无视觉跳变。

---

## 4. 扩展阅读

### 必读文章
- **Gaffer On Games — Networked Physics**: 权威服务器 + 客户端预测的经典文章
  https://gafferongames.com/post/networked_physics_2004/
- **Valve Developer Community — Source Multiplayer Networking**: CS:GO/Team Fortress 2 使用的网络架构，本框架的设计思想来源
  https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking
- **Overwatch Gameplay Architecture and Netcode (GDC 2017)**: 暴雪分享的守望先锋网络架构，客户端预测 + 服务器和解的工业级实现
- **云风 — skynet 框架**: Lua + C 的游戏服务器框架，许多设计模式可直接借鉴
  https://github.com/cloudwu/skynet

### 开源项目
- **lua-protobuf (GitHub: starwing/lua-protobuf)**: 纯 Lua 的 protobuf 实现，用于替代本教程中的 JSON 序列化
- **dkjson (GitHub: LuizHenriqueFurtado/dkjson)**: 纯 Lua 的 JSON 库，可作为 JSON 序列化的生产级替代
- **lua-enet (GitHub: leafo/lua-enet)**: ENet 可靠 UDP 的 Lua 绑定，可用于替代 TCP Socket

### 本计划相关
- 第 10 节：**帧同步客户端实现（Lua + C 引擎绑定）** — 对比两种 Lua 框架的设计差异
- 第 13 节：**状态同步核心原理：权威服务器模型** — 理解"服务器权威"的理论基础
- 第 14 节：**客户端预测** — 预测与和解的深入分析
- 第 16 节：**实体插值** — 插值算法的数学原理与优化
- 第 18 节：**状态同步客户端（Unity Netcode / NGO）** — 对比引擎内置方案与自研框架

---

## 常见陷阱

### 陷阱 1: 客户端预测中忘记区分"预测值"和"服务器值"

**错误**：
```lua
-- 客户端直接 set（标记为脏同步）
entity:set("x", predicted_x)

-- 服务器权威值到达时
entity:set("x", server_x)  -- 又标记为脏？不对！
```

**为什么错**：`set()` 会触发 `_dirty = true` 和 `_on_changed` 回调。客户端预测值不应该被当作"需要同步给服务器的变更"。而且当服务器值覆盖预测值时，`set()` 会触发回调，导致表现层产生不必要的响应（如 UI 闪烁）。

**正确做法**：使用 `predict_set()` 和 `apply_server_update()`：
```lua
-- 预测: 不影响同步状态
entity:predict_set("x", predicted_x)

-- 服务器更新: 静默覆盖（但仍触发 on_changed 供 UI 更新）
entity.sync_vars["x"]:apply_server_update(server_x)
```

### 陷阱 2: 插值延迟设置不当

**错误**：
```lua
local INTERP_DELAY_MS = 0  -- 无延迟，实时渲染
-- 或
local INTERP_DELAY_MS = 500 -- 延迟太大
```

**为什么错**：
- `INTERP_DELAY_MS = 0`：客户端收到快照后立即渲染。如果下一个快照延迟到达（网络抖动），实体在两次更新之间会"卡住"，然后突然跳到新位置。这就是"橡皮筋效应 (rubber-banding)"。
- `INTERP_DELAY_MS = 500`：延迟太大，客户端看到的远程玩家位置比服务器落后 500ms，相当于所有远程玩家都有半秒的"延迟感"。

**正确做法**：
```lua
-- 设为 2 倍平均网络延迟（RTT/2）
-- 如果平均 RTT = 80ms，设 INTERP_DELAY = 80ms
-- 如果网络不稳定，设 INTERP_DELAY = RTT_max
local INTERP_DELAY_MS = 100  -- 经验值，在 80~150ms 之间

-- 动态调整：根据实际测量的抖动值
local jitter = measure_network_jitter()
local INTERP_DELAY_MS = avg_rtt + jitter * 2
```

### 陷阱 3: 在 update() 中直接修改 SyncVar 触发同步循环

**错误**：
```lua
function Entity:update(dt)
    -- 客户端本地逻辑修改了 SyncVar
    self:set("x", self:get("x") + vx * dt)
    -- 每帧都标记为 dirty → 每帧都试图同步给服务器
    -- 但客户端不应该有"同步给服务器"的权限！
end
```

**为什么错**：状态同步客户端是"哑终端"——它不应执行权威逻辑。在客户端 `update()` 中修改 SyncVar 不仅标记了脏（浪费带宽），而且破坏了"服务器是唯一真相源"的原则。外挂可以直接在 `update()` 里写 `self:set("health", 99999)`。

**正确做法**：客户端只在以下时机修改 SyncVar：
1. `apply_server_update()` — 服务器下发的权威状态
2. `predict_set()` — 客户端预测（标记为预测值，后续可能被服务器覆盖）
3. **决不**在游戏逻辑更新中直接 `set()`

```lua
function Entity:on_client_tick(dt)
    -- 错误: self:set("x", ...)
    -- 正确: 通过 InputQueue 发送输入，让服务器决定位置
    -- 或者用 predict_set 做客户端预测
    if self.is_local_player then
        self:predict_set("x", predicted_x)  -- 仅预测，非权威
    end
end
```

### 陷阱 4: JSON 序列化的性能瓶颈

**错误**：每帧对大量 SyncVar 做完整的 JSON 序列化。

**为什么错**：Lua 的 JSON 编码（即使是 C 实现的 cjson）在每个网络 tick 序列化数百个实体属性时，CPU 开销可达数毫秒。在 60fps 的渲染循环中，每帧只有 ~16ms 预算，JSON 编码吃掉 3-5ms 是不允许的。

**正确做法**：
1. **使用二进制协议**：protobuf (via lua-protobuf) 或 flatbuffers，序列化开销比 JSON 低 5-10 倍
2. **增量序列化**：只序列化变更的属性，而非整个实体
3. **手动拼接**：对于简单类型（number, bool），手写字节序列化：
```lua
-- 手写序列化比 JSON 快 ~20 倍
local function encode_entity_update(entity_id, changes)
    local parts = { string.pack("<I2", entity_id) }  -- 2字节 entity_id
    for name, data in pairs(changes) do
        local attr_id = ATTR_IDS[name]  -- 预定义的属性 ID 映射
        table.insert(parts, string.pack("<I1", attr_id))  -- 1字节 属性ID
        table.insert(parts, string.pack("<f", data.value)) -- 4字节 float
    end
    return table.concat(parts)
end
```

### 陷阱 5: 忘记处理实体销毁时的插值器清理

**错误**：
```lua
function StateSyncMgr:_destroy_entity(entity_id)
    self._entities[entity_id] = nil
    -- 忘记从 Interpolator 中移除！
end
```

**为什么错**：`Interpolator._snapshots` 中仍然持有该实体的引用（包括 `entity` 对象和快照 buffer）。即使实体已经从 `_entities` 中移除，`Interpolator:update()` 每帧仍会尝试更新该实体的位置 → 调用 `engine.entity_set_position(nil_render_handle)` → crash 或空指针。

**正确做法**：
```lua
function StateSyncMgr:_destroy_entity(entity_id)
    local ent = self._entities[entity_id]
    if not ent then return end
    -- ... 其他清理 ...
    self._interpolator:unregister_entity(entity_id)  -- 必须！
    self._entities[entity_id] = nil
end
```

### 陷阱 6: RPC 参数中包含可变引用

**错误**：
```lua
local params = { x = 0, y = 0 }
for i = 1, 10 do
    params.x = i
    params.y = i * 2
    rpc:send_c2s("MoveInput", params)  -- 同一个 table！
end
```

**为什么错**：`send_c2s` 将 `params` 存入 `_pending_rpcs` 队列（用于超时重传）。所有 10 个 RPC 都指向**同一个** `params` table，重传时取到的值都是最后一次修改的值 `{x=10, y=20}`。

**正确做法**：每次发送时浅拷贝参数：
```lua
function RPCSystem:send_c2s(method, params, on_ack, on_timeout)
    -- 浅拷贝，避免可变引用问题
    local params_copy = {}
    for k, v in pairs(params) do
        params_copy[k] = v
    end
    -- ... 使用 params_copy ...
end
```

或者在调用处每次创建新 table：
```lua
rpc:send_c2s("MoveInput", { x = i, y = i * 2 })
```

### 陷阱 7: 客户端和服务端的时间不同步

**错误**：
```lua
-- 客户端插值使用本地时间
local render_time = os.clock() * 1000  -- 客户端本地时间

-- 服务器快照使用服务器时间
snap.time = server_tick * SERVER_TICK_MS  -- 服务器时间
```

**为什么错**：客户端和服务器的时钟**不同步**。客户端的 `os.clock()` 从进程启动开始计时，服务器的 `server_tick` 从服务启动开始计时。两者的时间原点不同，无法直接比较——`Interpolator:_find_interpolation_pair()` 会永远找不到匹配的快照对。

**正确做法**：使用相对时间偏移：
```lua
-- 握手时记录偏移
function on_handshake(server_time_ms)
    local local_time_ms = engine.get_timestamp_ms()
    self._time_offset = server_time_ms - local_time_ms
end

-- 之后任何服务器时间戳都可以转换为本地时间
function server_to_local(server_time_ms)
    return server_time_ms - self._time_offset
end

-- 插值时使用转换后的时间
local render_time = self:_now_ms() - INTERP_DELAY_MS
-- 快照的 time 字段已经通过 server_to_local 转换
```
