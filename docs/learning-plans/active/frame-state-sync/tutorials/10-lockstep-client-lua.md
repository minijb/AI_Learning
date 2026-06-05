---
title: "帧同步客户端实现（Lua + C 引擎绑定）"
updated: 2026-06-05
---

# 帧同步客户端实现（Lua + C 引擎绑定）

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [[07-lockstep-protocol-design|07-帧同步协议设计：帧指令、冗余发包、丢包处理]]

---

## 1. 概念讲解

### 1.1 为什么大厂用 Lua 写战斗逻辑？

如果你翻过《王者荣耀》《和平精英》《崩坏3》的安装包，会发现大量 `.lua` 或 `.luac`（Lua 字节码）文件。这些不是配置表——它们就是运行中的游戏逻辑。

大厂选择 Lua 写战斗逻辑，不是因为 Lua 快（它不快），而是因为三个字：**热更新**。

```
┌─────────────────────────────────────────────────────┐
│                 游戏客户端架构                        │
├─────────────────────────┬───────────────────────────┤
│       C/C++ 引擎层       │       Lua 逻辑层           │
│  ┌──────────┬──────────┐│  ┌──────────┬───────────┐ │
│  │ 渲染引擎  │ 物理引擎  ││  │ UI 逻辑   │ 战斗逻辑    │ │
│  │ (OpenGL) │ (Bullet) ││  │ (框架层) │ (帧同步层) │ │
│  ├──────────┼──────────┤│  ├──────────┼───────────┤ │
│  │ 网络层   │ 资源管理  ││  │ 技能系统  │ AI 系统    │ │
│  │ (KCP/ENet)│ (Asset)  ││  │ (Lua)    │ (Lua)     │ │
│  ├──────────┼──────────┤│  ├──────────┼───────────┤ │
│  │ 音频引擎  │ 输入系统  ││  │ 任务系统  │ 数据绑定   │ │
│  │ (FMOD)   │ (Touch)  ││  │ (Lua)    │ (Lua)     │ │
│  └──────────┴──────────┘│  └──────────┴───────────┘ │
│     ← C 绑定接口 →       │     ← 纯 Lua / LuaJIT →   │
└─────────────────────────┴───────────────────────────┘
```

#### 热更新：绕过 App Store 审核

移动端最大的运维痛点是**发版周期**。iOS App Store 审核通常 1-3 天，Android 渠道审核也需数小时。如果线上出现严重 Bug（比如某个英雄技能导致 crash），等审核再发版意味着数天的营收损失。

Lua 的热更新机制解决了这个问题：

```
┌──────────┐     ┌─────────────┐     ┌──────────┐
│  CDN/OSS  │────►│ 客户端下载   │────►│ 替换本地   │
│ 新 .luac  │     │ 增量 Lua 包  │     │ Lua 文件  │
└──────────┘     └─────────────┘     └──────────┘
                                           │
                                     ┌─────▼──────┐
                                     │ reload()   │
                                     │ 热加载模块  │
                                     └────────────┘
```

流程：
1. 服务器下发新版本号，客户端对比后发现需要更新
2. 客户端从 CDN 下载差分 Lua 包（通常几十到几百 KB）
3. 替换本地 Lua 文件，执行 `package.loaded[name] = nil; require(name)` 重载
4. **无需重启进程，无需重新登录**

代价：C/C++ 引擎层无法热更新（编译产物），这就是为什么引擎层需要非常稳定——它只做底层服务，不包含易变的业务逻辑。

#### 快速迭代：策划驱动开发

在 AAA 项目中，战斗策划和数值策划占了开发团队的 30-50%。如果每次调整技能数值、修改 Buff 逻辑都需要等程序员编译部署，效率是灾难性的。

Lua 方案下：
- 策划用内部编辑器调整技能参数，导出为 Lua 配置
- 战斗逻辑用 Lua 编写，策划可以直接修改测试
- 一天可以迭代 10+ 个版本，而 C++ 方案可能只能迭代 1-2 个

#### 反外挂：混淆与字节码

Lua 的另一个优势是**容易被混淆**。虽然 "security through obscurity" 不是真正的安全，但对于帧同步游戏，Lua 层的混淆能显著提高外挂制作门槛：

1. **字节码加密**：`.luac` 文件在打包时用自定义密钥加密，运行时在内存中解密执行
2. **变量名混淆**：`hero_attack_damage` → `a1`、`b_2`，让逆向者难以理解逻辑
3. **控制流平坦化**：将 `if-else` 转为 `while-switch-case` 结构
4. **C 层关键校验**：真正敏感的逻辑（如伤害校验、Hash 比对）放在 C 层，Lua 层即使被破解也无法绕过

#### 跨平台一致性

帧同步要求**逐位确定性**。Lua 5.1/5.3 的数值类型是双精度浮点（`double`），在不同平台上行为一致。配合 LuaJIT 的 FFI 模块调用 C 层定点数库，Lua 层只需做"调度"，核心计算放在 C 层定点数实现中——天然避开了浮点非确定性陷阱。

### 1.2 Lua 在游戏客户端中的角色分层

```
渲染帧循环 (60fps, 由引擎主循环驱动)
│
├─ C/C++ 层 ─────────────────────────────
│  ├─ 输入轮询 (Touch/Keyboard → 事件队列)
│  ├─ 场景渲染 (Draw Calls)
│  ├─ 物理步进 (FixedUpdate, 50Hz)
│  └─ 音频播放
│
├─ Lua 层 ──────────────────────────────
│  ├─ UI 模块 (UIView 生命周期)
│  │   └─ 按钮事件 → input_collector:on_touch(event)
│  ├─ 战斗逻辑模块 (LogicEngine)
│  │   └─ logic_engine:update(frame_inputs)  ← 每逻辑帧调用
│  ├─ 帧同步模块 (LockstepMgr)
│  │   └─ 管理 buffer/网络/帧推进
│  └─ 表现层模块
│      └─ 根据逻辑状态驱动动画、特效、音效
│
└─ C → Lua 绑定层 ───────────────────────
   ├─ Socket: connect/send/recv/close
   ├─ Timer: add_timer/remove_timer
   ├─ Entity: create/set_position/play_animation/destroy
   └─ Log: 日志输出 (帧日志、desync 检测)
```

关键原则：**Lua 做调度，C 做执行；Lua 做逻辑，C 做渲染**。

### 1.3 C 引擎绑定接口设计

Lua 本身不提供网络、定时器、渲染能力。C 引擎通过 **Lua C API**（或 LuaJIT FFI）将这些能力暴露给 Lua 层。下面是一个简化但完整的绑定接口头文件：

```c
// ============================================
// engine_bindings.h — C 引擎暴露给 Lua 的接口
// ============================================
#ifndef ENGINE_BINDINGS_H
#define ENGINE_BINDINGS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ─── Socket 绑定 ───────────────────────────────────
// 底层使用 KCP (可靠 UDP) 或 TCP

// 创建一个非阻塞 socket 连接到指定地址
// 返回 socket_handle (>=0 成功, -1 失败)
// Lua: local sock = engine.socket_connect("127.0.0.1", 9000)
int32_t engine_socket_connect(const char* host, uint16_t port);

// 发送数据 (非阻塞, 放入发送队列)
// 返回实际入队字节数 (>=0), -1 表示队列满
// Lua: local sent = engine.socket_send(sock, data, #data)
int32_t engine_socket_send(int32_t handle, const uint8_t* data, int32_t len);

// 接收数据 (非阻塞, 从接收队列取)
// 返回实际接收字节数到 buf, 最大 max_len
// 返回 0 表示无数据, -1 表示连接断开
// Lua: local buf = engine.socket_recv(sock, 4096)
int32_t engine_socket_recv(int32_t handle, uint8_t* buf, int32_t max_len);

// 关闭 socket
void engine_socket_close(int32_t handle);

// ─── 定时器绑定 ────────────────────────────────────
// 引擎主循环驱动的定时器, 精度取决于引擎 tick 频率

typedef int32_t timer_handle;

// 添加一次性定时器: delay_ms 毫秒后回调 Lua 函数
// Lua: engine.timer_add_once(500, function() print("fired") end)
timer_handle engine_timer_add_once(int32_t delay_ms,
    void (*callback)(void* ud), void* ud);

// 添加重复定时器: 每 interval_ms 毫秒回调一次
// Lua: engine.timer_add_repeat(100, function() on_tick() end)
timer_handle engine_timer_add_repeat(int32_t interval_ms,
    void (*callback)(void* ud), void* ud);

// 移除定时器
void engine_timer_remove(timer_handle handle);

// ─── 实体 API ──────────────────────────────────────
// 注意: 这些 API 是**表现层**操作，不参与确定性计算
// 帧同步逻辑层应使用自己维护的实体数据结构

typedef int32_t entity_handle;

// 创建一个渲染实体 (加载模型/精灵)
// Lua: local ent = engine.entity_create("hero_warrior", x, y, z)
entity_handle engine_entity_create(const char* prefab,
    float x, float y, float z);

// 设置实体位置 (用于逻辑帧之间的渲染插值)
void engine_entity_set_position(entity_handle ent,
    float x, float y, float z);

// 播放动画 (Attack, Idle, Walk, Hurt, Dead...)
void engine_entity_play_animation(entity_handle ent,
    const char* anim_name, int32_t loop);

// 销毁实体
void engine_entity_destroy(entity_handle ent);

// ─── 日志 / 调试 ──────────────────────────────────

// 写帧日志 (带帧号、时间戳, 用于 desync 排查)
void engine_frame_log(int32_t frame_no, const char* tag,
    const char* fmt, ...);

// 获取当前逻辑帧号 (由 LockstepMgr 设置)
int32_t engine_get_current_frame(void);
void    engine_set_current_frame(int32_t frame_no);

// 获取精确时间戳 (毫秒, 用于统计)
int64_t engine_get_timestamp_ms(void);

// ─── 随机数 ───────────────────────────────────────
// 确定性伪随机数 (基于帧号和种子, 纯 C 实现)

void engine_random_seed(uint32_t seed);

// 返回 [0, max_val) 范围内的确定性随机整数
uint32_t engine_random_int(uint32_t max_val);

#ifdef __cplusplus
}
#endif

#endif // ENGINE_BINDINGS_H
```

**绑定到 Lua 的方式**（两种主流方案）：

方案 A — Lua C API（`lua_register`）：

```c
// 在引擎初始化时注册全局函数
lua_register(L, "engine_socket_connect", l_engine_socket_connect);
lua_register(L, "engine_socket_send",    l_engine_socket_send);
// ... 或注册到一个 engine 表
lua_newtable(L);
lua_pushcfunction(L, l_engine_socket_connect);
lua_setfield(L, -2, "socket_connect");
lua_setglobal(L, "engine");
```

方案 B — LuaJIT FFI（性能更高）：

```lua
-- 直接用 FFI 声明 C 函数签名
local ffi = require("ffi")
ffi.cdef([[
    int32_t engine_socket_connect(const char* host, uint16_t port);
    int32_t engine_socket_send(int32_t handle, const uint8_t* data, int32_t len);
    int32_t engine_socket_recv(int32_t handle, uint8_t* buf, int32_t max_len);
    void engine_socket_close(int32_t handle);
]])

local C = ffi.C -- 直接调用, 几乎零开销

local engine = {}
function engine.socket_connect(host, port)
    return C.engine_socket_connect(host, port)
end
```

FFI 方案的好处是：调用 C 函数无需经过 `lua_CFunction` 的参数栈操作，JIT 编译器可以直接生成 `call` 指令。在热点路径上（如每帧遍历实体），性能差异可达 5-10 倍。

---

## 2. 代码示例

下面给出完整的 Lua 端帧同步框架实现。所有代码均为可运行的 Lua 5.1+ / LuaJIT 兼容代码。

### 2.1 FrameBuffer — 环形缓冲区（~80 行）

帧缓冲区是帧同步客户端的核心数据结构。客户端不是"到了帧 N 才发送帧 N 的输入"，而是**提前发送未来 N 帧的输入**，以容忍网络抖动。

```lua
-- ============================================
-- frame_buffer.lua — 环形缓冲区
-- ============================================
-- 功能: 缓存已收到的服务端帧数据, 以固定容量循环使用
-- 核心数据结构: 一个固定大小的 Lua table + head/tail 指针
-- 用途:
--   1. 缓冲服务端下发的帧数据, 平滑网络抖动
--   2. 断线重连时快速定位需要补发的帧范围
--   3. 为渲染层提供数据 (插值所需的当前帧和下一帧)
--
-- 环形缓冲区示意图 (容量=8):
--   tail=2 ────┐          ┌── head=6
--              ▼          ▼
--   [ ] [F2] [F3] [F4] [F5] [ ] [ ] [ ]
--    ↑                       ↑
--   已消费                 最新收到
--   可被覆盖
-- ============================================

local FrameBuffer = {}
FrameBuffer.__index = FrameBuffer

--- 创建帧缓冲区
--- @param capacity number 最大缓存帧数 (通常 64-256, 约等于 4-17 秒 @15fps)
--- @param player_count number 玩家数量 (用于初始化空输入)
function FrameBuffer.new(capacity, player_count)
    local self = setmetatable({}, FrameBuffer)
    self.capacity = capacity
    self.player_count = player_count
    -- 环形存储: slot[i] = { frame_no = N, inputs = {[pid]=input, ...} }
    self.slots = {}
    for i = 1, capacity do
        self.slots[i] = nil  -- 初始为空, 占位
    end
    -- head: 下一个要消费的帧在 slots 中的索引
    -- tail: 下一个要写入的帧在 slots 中的索引
    self.head = 1
    self.tail = 1
    -- 当前已经写入过的最小和最大帧号 (用于范围查询)
    self.min_frame = nil
    self.max_frame = nil
    return self
end

--- 将服务端下发的一帧数据写入缓冲区
--- @param frame_no number 帧号
--- @param inputs table   { [player_id] = input_data, ... }
--- @return boolean 是否成功写入 (帧号过旧或缓冲区满则返回 false)
function FrameBuffer:push(frame_no, inputs)
    -- 帧号过旧, 丢弃
    if self.min_frame and frame_no < self.min_frame then
        return false
    end

    -- 检查是否已经存在该帧号 (冗余包)
    if self.max_frame and frame_no <= self.max_frame then
        -- 遍历查找是否已有
        local idx = self:find_slot(frame_no)
        if idx then
            -- 已存在, 合并输入 (某些实现会选择忽略冗余包)
            return true
        end
    end

    -- 检查缓冲区是否满 (tail 追上了 head)
    local next_tail = self:_next_index(self.tail)
    if next_tail == self.head then
        -- 缓冲区满, 丢弃最旧的一帧
        self.slots[self.head] = nil
        self.head = self:_next_index(self.head)
        if self.min_frame then
            self.min_frame = self.min_frame + 1
        end
    end

    -- 写入
    self.slots[self.tail] = {
        frame_no = frame_no,
        inputs = inputs,
    }
    self.tail = next_tail

    -- 更新范围
    if not self.min_frame or frame_no < self.min_frame then
        self.min_frame = frame_no
    end
    if not self.max_frame or frame_no > self.max_frame then
        self.max_frame = frame_no
    end

    return true
end

--- 从缓冲区取出一帧数据 (消费)
--- @param frame_no number 帧号
--- @return table|nil inputs, 或 nil 表示该帧尚未到达
function FrameBuffer:pop(frame_no)
    local idx = self:find_slot(frame_no)
    if not idx then
        return nil  -- 帧数据未到
    end
    local slot = self.slots[idx]
    self.slots[idx] = nil
    -- 如果 pop 的是 head, 推进 head
    if idx == self.head then
        self.head = self:_next_index(self.head)
    end
    -- 更新 min_frame
    if self.min_frame == frame_no then
        self:_recalc_min_frame()
    end
    return slot.inputs
end

--- 查询某帧是否已到达 (不消费)
--- @param frame_no number 帧号
--- @return boolean
function FrameBuffer:has_frame(frame_no)
    return self:find_slot(frame_no) ~= nil
end

--- 获取缓冲区内连续的帧范围 (用于断线重连判断缺帧)
--- @return number|nil min_frame, number|nil max_frame
function FrameBuffer:get_frame_range()
    return self.min_frame, self.max_frame
end

--- 获取缓冲区中的帧数量
--- @return number
function FrameBuffer:size()
    if self.tail >= self.head then
        return self.tail - self.head
    else
        return self.capacity - self.head + self.tail
    end
end

--- 查找帧号对应的 slot 索引, 未找到返回 nil
function FrameBuffer:find_slot(frame_no)
    -- 快速范围检查
    if self.min_frame and self.max_frame then
        if frame_no < self.min_frame or frame_no > self.max_frame then
            return nil
        end
    end

    -- 线性扫描 (环形缓冲区容量小, O(n) 可接受)
    -- 生产级代码可以用 frame_no 直接计算索引:
    --   idx = (frame_no - base_frame) % capacity + 1
    -- 但需要对不连续的帧号做更复杂的追踪
    for i = 1, self.capacity do
        local slot = self.slots[i]
        if slot and slot.frame_no == frame_no then
            return i
        end
    end
    return nil
end

--- 清空缓冲区 (用于断线重连后重新开始)
function FrameBuffer:clear()
    for i = 1, self.capacity do
        self.slots[i] = nil
    end
    self.head = 1
    self.tail = 1
    self.min_frame = nil
    self.max_frame = nil
end

-- ─── 内部方法 ──────────────────────────────────────

function FrameBuffer:_next_index(idx)
    local nxt = idx + 1
    if nxt > self.capacity then
        nxt = 1
    end
    return nxt
end

function FrameBuffer:_recalc_min_frame()
    self.min_frame = nil
    for i = 1, self.capacity do
        local slot = self.slots[i]
        if slot then
            if not self.min_frame or slot.frame_no < self.min_frame then
                self.min_frame = slot.frame_no
            end
        end
    end
    -- 如果缓冲区为空
    if not self.min_frame then
        self.max_frame = nil
    end
end

return FrameBuffer
```

### 2.2 InputCollector — 输入收集器（~60 行）

```lua
-- ============================================
-- input_collector.lua — 输入收集器
-- ============================================
-- 功能: 将触屏/键盘事件转换为标准化的帧同步指令
-- 核心职责:
--   1. 监听 C 引擎传入的输入事件 (touch, key)
--   2. 在一帧内收集所有操作 (支持多点触控/组合键)
--   3. Bucket 结束时打包为标准 FrameInput
--   4. 处理摇杆死区 (避免静止时抖动产生微小移动)
-- ============================================

local InputCollector = {}
InputCollector.__index = InputCollector

-- 输入类型枚举
InputCollector.INPUT_TYPE = {
    NONE    = 0,   -- 空操作
    MOVE    = 1,   -- 移动 (摇杆/点击)
    ATTACK  = 2,   -- 普通攻击
    SKILL_1 = 3,   -- 技能1
    SKILL_2 = 4,   -- 技能2
    SKILL_3 = 5,   -- 技能3
    DODGE   = 6,   -- 闪避/翻滚
}

-- 输入标志位 (用于位掩码组合)
InputCollector.INPUT_FLAG = {
    NONE       = 0x0000,
    MOVE       = 0x0001,
    ATTACK     = 0x0002,
    SKILL_1    = 0x0004,
    SKILL_2    = 0x0008,
    SKILL_3    = 0x0010,
    DODGE      = 0x0020,
    DIR_LEFT   = 0x0100,
    DIR_RIGHT  = 0x0200,
    DIR_UP     = 0x0400,
    DIR_DOWN   = 0x0800,
}

--- 创建输入收集器
--- @param player_id number 本地玩家 ID
--- @param joystick_deadzone number 摇杆死区 (0~1), 低于此值的操作被忽略
function InputCollector.new(player_id, joystick_deadzone)
    local self = setmetatable({}, InputCollector)
    self.player_id = player_id
    self.deadzone = joystick_deadzone or 0.15

    -- 当前帧累积的操作
    self.current_actions = {}      -- { action1, action2, ... }
    -- 当前摇杆状态 (持续输入)
    self.joystick_x = 0
    self.joystick_y = 0
    self.joystick_active = false

    -- 按键状态 (用于检测按下/抬起)
    self.key_states = {}

    return self
end

--- 处理触摸事件 (由 C 引擎回调)
--- @param event_type string "began" | "moved" | "ended"
--- @param x number 触摸点 X (0~1 归一化坐标)
--- @param y number 触摸点 Y
--- @param touch_id number 多点触控 ID
function InputCollector:on_touch(event_type, x, y, touch_id)
    if event_type == "began" then
        -- 记录起始点, 在 moved 中判断是摇杆还是点击
        self._touch_start = { x = x, y = y, id = touch_id }
    elseif event_type == "moved" then
        if self._touch_start and self._touch_start.id == touch_id then
            local dx = x - self._touch_start.x
            local dy = y - self._touch_start.y
            local dist = math.sqrt(dx * dx + dy * dy)

            if dist > self.deadzone then
                -- 摇杆操作: 移动
                self.joystick_x = dx
                self.joystick_y = dy
                self.joystick_active = true
            end
        end
    elseif event_type == "ended" then
        if self._touch_start and self._touch_start.id == touch_id then
            local dx = x - self._touch_start.x
            local dy = y - self._touch_start.y
            local dist = math.sqrt(dx * dx + dy * dy)

            if dist <= self.deadzone then
                -- 点击: 攻击
                table.insert(self.current_actions, {
                    type = self.INPUT_TYPE.ATTACK,
                    target_x = x,
                    target_y = y,
                })
            end
            self._touch_start = nil
        end
        -- 摇杆归零
        self.joystick_x = 0
        self.joystick_y = 0
        self.joystick_active = false
    end
end

--- 处理技能按钮 (由 UI 层回调)
--- @param skill_index number 1-3
function InputCollector:on_skill_button(skill_index)
    local skill_types = {
        self.INPUT_TYPE.SKILL_1,
        self.INPUT_TYPE.SKILL_2,
        self.INPUT_TYPE.SKILL_3,
    }
    if skill_types[skill_index] then
        table.insert(self.current_actions, {
            type = skill_types[skill_index],
        })
    end
end

--- 处理闪避按钮
function InputCollector:on_dodge_button()
    table.insert(self.current_actions, {
        type = self.INPUT_TYPE.DODGE,
    })
end

--- 收集本帧的最终输入 (Bucket 结束时调用)
--- 采用 Last Wins 策略: 如果既有移动又有技能, 优先级为 技能 > 攻击 > 移动
--- @return table frame_input { type, args = {...}, flags }
function InputCollector:collect()
    local input = {
        type = self.INPUT_TYPE.NONE,
        args = {},
        flags = self.INPUT_FLAG.NONE,
    }

    -- 优先级排序: 技能 > 闪避 > 攻击 > 移动
    -- 这模拟了"技能打断普攻, 普攻覆盖移动"的格斗游戏规则

    -- 最高优先级: 检查技能按钮
    for _, action in ipairs(self.current_actions) do
        if action.type >= self.INPUT_TYPE.SKILL_1
           and action.type <= self.INPUT_TYPE.SKILL_3 then
            input.type = action.type
            input.flags = self.INPUT_FLAG.SKILL_1  -- 简化, 实际应映射
            break
        end
    end

    -- 次优先级: 闪避
    if input.type == self.INPUT_TYPE.NONE then
        for _, action in ipairs(self.current_actions) do
            if action.type == self.INPUT_TYPE.DODGE then
                input.type = action.type
                input.flags = self.INPUT_FLAG.DODGE
                break
            end
        end
    end

    -- 再次: 攻击
    if input.type == self.INPUT_TYPE.NONE then
        for _, action in ipairs(self.current_actions) do
            if action.type == self.INPUT_TYPE.ATTACK then
                input.type = action.type
                input.args = { action.target_x or 0, action.target_y or 0 }
                input.flags = self.INPUT_FLAG.ATTACK
                break
            end
        end
    end

    -- 最低优先级: 移动 (摇杆持续输入)
    if input.type == self.INPUT_TYPE.NONE and self.joystick_active then
        input.type = self.INPUT_TYPE.MOVE
        input.args = { self.joystick_x, self.joystick_y }
        input.flags = self.INPUT_FLAG.MOVE
        -- 添加方向标志
        if math.abs(self.joystick_x) > math.abs(self.joystick_y) then
            if self.joystick_x > 0 then
                input.flags = input.flags | self.INPUT_FLAG.DIR_RIGHT
            else
                input.flags = input.flags | self.INPUT_FLAG.DIR_LEFT
            end
        else
            if self.joystick_y > 0 then
                input.flags = input.flags | self.INPUT_FLAG.DIR_UP
            else
                input.flags = input.flags | self.INPUT_FLAG.DIR_DOWN
            end
        end
    end

    -- 重置当前帧缓存
    self.current_actions = {}

    return input
end

--- 生成空输入 (用于帧缓冲区初始化、超时填充)
function InputCollector.empty_input()
    return {
        type  = InputCollector.INPUT_TYPE.NONE,
        args  = {},
        flags = InputCollector.INPUT_FLAG.NONE,
    }
end

return InputCollector
```

### 2.3 NetworkAdapter — 网络适配器（~100 行）

```lua
-- ============================================
-- network_adapter.lua — 网络适配器
-- ============================================
-- 功能: 封装 C 引擎的 Socket 绑定, 提供帧同步专用的收发接口
-- 职责:
--   1. 管理 UDP/KCP socket 生命周期
--   2. 序列化/反序列化帧数据 (protobuf / 自定义二进制)
--   3. 冗余发送: 每次发包连带发送最近 N 帧的输入
--   4. 接收队列: 非阻塞收包, 解析后送至 LockstepMgr
-- ============================================

local NetworkAdapter = {}
NetworkAdapter.__index = NetworkAdapter

-- 简化的二进制序列化 (生产代码应使用 protobuf 或 flatbuffers)
-- 帧数据包格式:
--   [1B 包类型] [4B 帧号] [1B 玩家数] [N × (1B 玩家ID + 1B 输入类型 + 4B flags + 8B args)]
--   总计: ~7 + N*14 字节, 远小于状态同步

local PACKET_TYPE = {
    CLIENT_INPUT = 0x01,  -- 客户端 → 服务器: 上传输入
    SERVER_FRAME = 0x02,  -- 服务器 → 客户端: 下发帧数据
    HEARTBEAT    = 0x03,  -- 心跳
    RECONNECT    = 0x04,  -- 重连请求/响应
}

--- 创建网络适配器
--- @param host string 服务器地址
--- @param port number 服务器端口
function NetworkAdapter.new(host, port)
    local self = setmetatable({}, NetworkAdapter)
    self.host = host
    self.port = port
    self.socket = nil
    self.connected = false

    -- 发送缓冲区: 存储最近 N 帧的已发送输入 (用于冗余发送)
    self.sent_inputs = {}   -- { [frame_no] = serialized_data }
    self.redundant_frames = 3  -- 冗余发送前 3 帧

    -- 接收缓冲区
    self.recv_buffer = ""   -- 粘包/半包处理

    return self
end

--- 连接到服务器
--- @return boolean
function NetworkAdapter:connect()
    self.socket = engine.socket_connect(self.host, self.port)
    if self.socket < 0 then
        print("[NetworkAdapter] 连接失败: " .. self.host .. ":" .. self.port)
        return false
    end
    self.connected = true
    print("[NetworkAdapter] 连接成功, socket=" .. self.socket)
    return true
end

--- 发送客户端输入到服务器
--- @param frame_no number 当前帧号
--- @param input table 输入数据 { type, args, flags }
function NetworkAdapter:send_input(frame_no, input)
    if not self.connected then return end

    -- 序列化
    local data = self:_serialize_input(frame_no, input)

    -- 冗余发送: 连带发送最近几帧的输入
    -- 这样即使某个 UDP 包丢失, 后续包中的冗余数据可以补上
    local full_data = data
    for fno = frame_no - self.redundant_frames, frame_no - 1 do
        local prev_data = self.sent_inputs[fno]
        if prev_data then
            full_data = full_data .. prev_data  -- 追加冗余帧
        end
    end

    -- 通过 C 引擎 socket 发送
    local sent = engine.socket_send(self.socket, full_data, #full_data)
    if sent < 0 then
        print("[NetworkAdapter] 发送失败")
    end

    -- 缓存当前帧数据, 供后续冗余使用
    self.sent_inputs[frame_no] = data

    -- 清理过旧的缓存
    local oldest_to_keep = frame_no - self.redundant_frames * 2
    for fno, _ in pairs(self.sent_inputs) do
        if fno < oldest_to_keep then
            self.sent_inputs[fno] = nil
        end
    end
end

--- 接收服务器数据 (非阻塞, 每帧调用)
--- @return table|nil 解析后的帧数据, 或 nil 表示无新数据
function NetworkAdapter:recv()
    if not self.connected then return nil end

    -- 从 C 引擎 socket 读取 (最大 4KB, 帧同步数据包很小)
    local buf = engine.socket_recv(self.socket, 4096)
    if not buf or #buf == 0 then
        return nil
    end

    self.recv_buffer = self.recv_buffer .. buf

    -- 粘包处理: 循环解析完整包
    local results = {}
    while #self.recv_buffer >= 7 do  -- 最小包大小: 1+4+1+1 = 7
        local pkt_type = string.byte(self.recv_buffer, 1)

        if pkt_type == PACKET_TYPE.SERVER_FRAME then
            -- 解析帧数据
            local frame_no, inputs, consumed = self:_deserialize_frame(self.recv_buffer)
            if not frame_no then
                break  -- 半包, 等待更多数据
            end
            table.insert(results, { frame_no = frame_no, inputs = inputs })
            self.recv_buffer = self.recv_buffer:sub(consumed + 1)
        elseif pkt_type == PACKET_TYPE.HEARTBEAT then
            -- 心跳包, 直接消费
            self.recv_buffer = self.recv_buffer:sub(2)
        else
            -- 未知包类型, 跳过
            print("[NetworkAdapter] 未知包类型: " .. pkt_type)
            self.recv_buffer = ""
            break
        end
    end

    if #results > 0 then
        -- 返回最后一个完整帧 (也可以返回全部, 由上层逐个处理)
        return results
    end
    return nil
end

--- 断开连接
function NetworkAdapter:disconnect()
    if self.socket then
        engine.socket_close(self.socket)
    end
    self.connected = false
    self.socket = nil
end

-- ─── 内部序列化方法 ────────────────────────────────
-- 注意: 以下为简化实现, 生产代码应使用 protobuf

function NetworkAdapter:_serialize_input(frame_no, input)
    -- 格式: [1B type=0x01] [4B LE frame_no] [1B input_type] [4B LE flags] [8B args]
    local data = string.char(PACKET_TYPE.CLIENT_INPUT)
    -- 帧号: 32-bit little-endian
    data = data .. string.char(
        frame_no & 0xFF,
        (frame_no >> 8) & 0xFF,
        (frame_no >> 16) & 0xFF,
        (frame_no >> 24) & 0xFF
    )
    -- 输入类型
    data = data .. string.char(input.type or 0)
    -- flags: 32-bit LE
    local flags = input.flags or 0
    data = data .. string.char(
        flags & 0xFF,
        (flags >> 8) & 0xFF,
        (flags >> 16) & 0xFF,
        (flags >> 24) & 0xFF
    )
    -- args: 最多 2 个参数, 每个 4B float (生产环境应使用定点数)
    local args = input.args or {}
    local arg1 = args[1] or 0
    local arg2 = args[2] or 0
    -- 简化: 直接写 8 字节 (生产环境应使用 IEEE 754 编码或定点数)
    data = data .. string.char(0, 0, 0, 0, 0, 0, 0, 0) -- placeholder
    return data
end

function NetworkAdapter:_deserialize_frame(raw_data)
    if #raw_data < 7 then return nil end

    local pkt_type = string.byte(raw_data, 1)
    if pkt_type ~= PACKET_TYPE.SERVER_FRAME then
        return nil
    end

    -- 帧号 (bytes 2-5)
    local frame_no = string.byte(raw_data, 2)
        + string.byte(raw_data, 3) * 256
        + string.byte(raw_data, 4) * 65536
        + string.byte(raw_data, 5) * 16777216

    -- 玩家数 (byte 6)
    local player_count = string.byte(raw_data, 6)
    if player_count == 0 then return nil end

    -- 计算总长度
    -- 每个玩家: 1B player_id + 1B input_type + 4B flags + 8B args = 14B
    local total_len = 6 + player_count * 14
    if #raw_data < total_len then
        return nil  -- 半包
    end

    local pos = 7
    local inputs = {}
    for i = 1, player_count do
        local pid = string.byte(raw_data, pos)
        local input_type = string.byte(raw_data, pos + 1)
        local flags = string.byte(raw_data, pos + 2)
            + string.byte(raw_data, pos + 3) * 256
            + string.byte(raw_data, pos + 4) * 65536
            + string.byte(raw_data, pos + 5) * 16777216
        -- 简化: 忽略 args 解析
        inputs[pid] = {
            type = input_type,
            flags = flags,
        }
        pos = pos + 14
    end

    return frame_no, inputs, total_len
end

return NetworkAdapter
```

### 2.4 LogicEngine — 确定性逻辑引擎（~120 行）

```lua
-- ============================================
-- logic_engine.lua — 确定性游戏逻辑引擎
-- ============================================
-- 核心原则: 纯函数, 无副作用, 不依赖外部状态
-- 相同输入 + 相同初始状态 → 相同输出 (必须逐位一致!)
--
-- 警告:
--   1. 禁止使用 math.random() — 用确定性 PRNG
--   2. 禁止依赖 os.clock() / os.time() — 时间由帧号推导
--   3. 禁止使用 pairs() 遍历需排序的集合 — 用 ipairs 或排序后遍历
--   4. 浮点运算需谨慎 — 关键计算使用定点数 (由 C 层提供)
-- ============================================

local LogicEngine = {}
LogicEngine.__index = LogicEngine

-- 确定性伪随机数生成器 (xorshift32, 跨平台一致)
-- 参考: https://en.wikipedia.org/wiki/Xorshift
local function xorshift32(state)
    state = state ~ (state << 13)
    state = state ~ (state >> 17)
    state = state ~ (state << 5)
    -- 确保返回正数 (Lua 5.3+ bitwise 操作返回有符号整数)
    return state & 0x7FFFFFFF, state
end

--- 创建逻辑引擎
--- @param random_seed number 初始随机种子 (所有客户端必须相同)
function LogicEngine.new(random_seed)
    local self = setmetatable({}, LogicEngine)

    -- PRNG 状态
    self.prng_state = random_seed & 0xFFFFFFFF
    self.prng_call_count = 0

    -- 游戏全局状态 (帧同步中所有客户端共享的确定性状态)
    self.frame_no = 0          -- 当前逻辑帧号
    self.game_time = 0         -- 游戏时间 (帧号 × 固定步长)
    self.logic_dt = 1 / 15     -- 逻辑帧时间步长 (15Hz = 66.67ms)

    -- 实体表: { [entity_id] = entity_data }
    self.entities = {}

    return self
end

--- 初始化实体 (在首帧调用, 所有客户端必须用同样的初始化数据)
--- @param init_data table 包含所有初始实体信息
function LogicEngine:init_entities(init_data)
    self.entities = {}
    -- 按 entity_id 排序后初始化, 确保遍历顺序确定
    local sorted_ids = {}
    for eid, _ in pairs(init_data) do
        table.insert(sorted_ids, eid)
    end
    table.sort(sorted_ids)

    for _, eid in ipairs(sorted_ids) do
        local data = init_data[eid]
        self.entities[eid] = {
            id       = eid,
            player_id = data.player_id,
            type     = data.type,       -- "warrior", "mage", "archer"
            x        = data.x or 0,     -- 位置 X (应使用定点数, 此处简化为整数)
            y        = data.y or 0,     -- 位置 Y
            z        = data.z or 0,
            vx       = 0,               -- 速度 X
            vy       = 0,
            facing   = data.facing or 1, -- 朝向: 1=右, -1=左
            hp       = data.hp or 100,
            max_hp   = data.max_hp or 100,
            state    = "idle",          -- idle, moving, attacking, hurt, dead
            state_timer = 0,            -- 当前状态剩余时间 (帧数)
            attack_cooldown = 0,        -- 攻击冷却 (帧数)
        }
    end
end

--- 执行一帧逻辑 (确定性)
--- @param inputs table { [player_id] = input_data }
--- @return table 本帧产生的表现层事件 (用于渲染层播放动画/特效)
function LogicEngine:update(inputs)
    self.frame_no = self.frame_no + 1
    self.game_time = self.frame_no * self.logic_dt

    local events = {}  -- 本帧产生的渲染事件

    -- 确保遍历顺序确定: 按 entity_id 排序
    local sorted_ids = {}
    for eid, _ in pairs(self.entities) do
        table.insert(sorted_ids, eid)
    end
    table.sort(sorted_ids)

    for _, eid in ipairs(sorted_ids) do
        local ent = self.entities[eid]
        if ent.hp > 0 then  -- 跳过已死亡实体
            local input = inputs[ent.player_id]
            self:_process_entity(ent, input, events)
        end
    end

    -- 清理死亡实体 (遍历顺序确定)
    local dead_list = {}
    for _, eid in ipairs(sorted_ids) do
        if self.entities[eid].hp <= 0 then
            table.insert(dead_list, eid)
        end
    end
    for _, eid in ipairs(dead_list) do
        self.entities[eid] = nil
    end

    return events
end

-- ─── 内部: 处理单个实体的逻辑 ──────────────────────

local MOVE_SPEED = 3     -- 每帧移动像素 (应使用定点数, 此处简化)
local ATTACK_RANGE = 40
local ATTACK_DAMAGE = 15
local ATTACK_COOLDOWN = 10   -- 帧数

function LogicEngine:_process_entity(ent, input, events)
    -- 减少冷却
    if ent.attack_cooldown > 0 then
        ent.attack_cooldown = ent.attack_cooldown - 1
    end
    -- 减少状态计时器
    if ent.state_timer > 0 then
        ent.state_timer = ent.state_timer - 1
    end

    -- 处理输入 (来自本地或远程玩家)
    if input and input.type ~= 0 then
        if input.type == 1 then  -- MOVE
            local dx = input.args and input.args[1] or 0
            local dy = input.args and input.args[2] or 0

            if dx ~= 0 or dy ~= 0 then
                -- 归一化方向 (避免斜向移动更快)
                local len = math.sqrt(dx * dx + dy * dy)
                if len > 0 then
                    dx = dx / len
                    dy = dy / len
                end

                ent.x = ent.x + dx * MOVE_SPEED
                ent.y = ent.y + dy * MOVE_SPEED
                ent.state = "moving"
                -- 更新朝向
                if dx ~= 0 then
                    ent.facing = (dx > 0) and 1 or -1
                end

                table.insert(events, {
                    type = "move",
                    entity_id = ent.id,
                    x = ent.x,
                    y = ent.y,
                    facing = ent.facing,
                })
            end

        elseif input.type == 2 then  -- ATTACK
            if ent.attack_cooldown <= 0 then
                ent.state = "attacking"
                ent.attack_cooldown = ATTACK_COOLDOWN
                ent.state_timer = 6  -- 攻击动画持续 6 帧

                -- 查找攻击范围内的目标
                local target = self:_find_nearest_enemy(ent)
                if target then
                    -- 伤害计算 (确定性!)
                    target.hp = target.hp - ATTACK_DAMAGE
                    if target.hp < 0 then target.hp = 0 end

                    table.insert(events, {
                        type = "attack",
                        entity_id = ent.id,
                        target_id = target.id,
                        damage = ATTACK_DAMAGE,
                    })
                    table.insert(events, {
                        type = "hurt",
                        entity_id = target.id,
                        damage = ATTACK_DAMAGE,
                        hp = target.hp,
                    })

                    -- 如果目标死亡
                    if target.hp <= 0 then
                        table.insert(events, {
                            type = "death",
                            entity_id = target.id,
                        })
                    end
                end
            end

        elseif input.type == 6 then  -- DODGE
            -- 闪避: 短暂无敌 + 位移
            ent.state = "dodging"
            ent.state_timer = 8
            ent.x = ent.x + ent.facing * MOVE_SPEED * 4
            table.insert(events, {
                type = "dodge",
                entity_id = ent.id,
                x = ent.x,
                y = ent.y,
            })
        end
    end

    -- 状态恢复 (状态计时器归零后回到 idle)
    if ent.state_timer <= 0 and ent.state ~= "moving" and ent.state ~= "idle" then
        -- 注意: moving 状态需要等摇杆松手才变 idle
        -- 这里简化: 技能/攻击状态结束后回到 idle
        if input == nil or input.type == 0 or input.type == 1 then
            ent.state = "idle"
        end
    end
end

--- 查找最近的敌对实体 (遍历顺序确定)
function LogicEngine:_find_nearest_enemy(ent)
    local nearest = nil
    local min_dist = ATTACK_RANGE

    -- 按 entity_id 排序遍历, 确保确定性
    local sorted_ids = {}
    for eid, _ in pairs(self.entities) do
        table.insert(sorted_ids, eid)
    end
    table.sort(sorted_ids)

    for _, eid in ipairs(sorted_ids) do
        local other = self.entities[eid]
        if other.id ~= ent.id
           and other.player_id ~= ent.player_id
           and other.hp > 0 then
            local dx = other.x - ent.x
            local dy = other.y - ent.y
            local dist = math.sqrt(dx * dx + dy * dy)
            if dist <= min_dist then
                nearest = other
                min_dist = dist
            end
        end
    end

    return nearest
end

--- 获取确定性随机数
function LogicEngine:random(max_val)
    self.prng_call_count = self.prng_call_count + 1
    -- 种子混合帧号, 确保同一帧号得到相同随机序列
    local seed = self.prng_state
        ~ (self.frame_no * 2654435761)
        ~ (self.prng_call_count * 0x9E3779B9)
    local val, _ = xorshift32(seed)
    return val % max_val
end

--- 计算当前状态的 Hash (用于 desync 检测)
function LogicEngine:compute_state_hash()
    -- 简单 XOR hash, 生产环境使用 CRC32 或 MD5
    local h = self.frame_no
    local sorted_ids = {}
    for eid, _ in pairs(self.entities) do
        table.insert(sorted_ids, eid)
    end
    table.sort(sorted_ids)

    for _, eid in ipairs(sorted_ids) do
        local ent = self.entities[eid]
        h = h ~ (ent.id * 0x9E3779B1)
        h = h ~ (math.floor(ent.x) * 0x85EBCA77)
        h = h ~ (math.floor(ent.y) * 0xC2B2AE35)
        h = h ~ (ent.hp * 0x27D4EB2F)
    end
    return h & 0xFFFFFFFF
end

return LogicEngine
```

### 2.5 LockstepMgr — 帧同步管理器（~200 行）

```lua
-- ============================================
-- lockstep_mgr.lua — 帧同步管理器 (主控模块)
-- ============================================
-- 功能: 协调 FrameBuffer / InputCollector / NetworkAdapter / LogicEngine
-- 对应 Unity 版本中的 LockstepManager
--
-- 主循环流程:
--   每个渲染帧 (60fps):
--     1. 接收网络数据 → 写入 FrameBuffer
--     2. 检查 FrameBuffer 是否有可执行的逻辑帧
--     3. 如果有, 执行 logic_engine:update(inputs)
--     4. 收集本地输入 → 发送到服务器
--     5. 驱动表现层 (动画/特效/音效)
-- ============================================

local FrameBuffer = require("frame_buffer")
local InputCollector = require("input_collector")
local LogicEngine = require("logic_engine")
local NetworkAdapter = require("network_adapter")

local LockstepMgr = {}
LockstepMgr.__index = LockstepMgr

-- 状态枚举
LockstepMgr.STATE = {
    DISCONNECTED = 0,
    CONNECTING   = 1,
    CONNECTED    = 2,    -- 已连接, 等待开始
    RUNNING      = 3,    -- 游戏运行中
    CATCHING_UP  = 4,    -- 断线重连追赶中
    PAUSED       = 5,    -- 暂停 (缺帧等待)
    ENDED        = 6,
}

--- 创建帧同步管理器
--- @param config table 配置参数
---   .player_id: 本地玩家 ID
---   .player_count: 总玩家数
---   .logic_frame_rate: 逻辑帧率 (默认 15)
---   .buffer_size: 帧缓冲区大小 (默认 128)
---   .max_frames_behind: 允许落后的最大帧数 (超过则触发追赶)
---   .random_seed: 随机种子
function LockstepMgr.new(config)
    local self = setmetatable({}, LockstepMgr)

    self.player_id    = config.player_id or 0
    self.player_count = config.player_count or 2
    self.logic_frame_rate = config.logic_frame_rate or 15
    self.logic_dt_sec = 1.0 / self.logic_frame_rate  -- 逻辑帧间隔 (秒)

    -- 子模块
    self.frame_buffer   = FrameBuffer.new(config.buffer_size or 128, self.player_count)
    self.input_collector = InputCollector.new(self.player_id, 0.15)
    self.logic_engine   = LogicEngine.new(config.random_seed or 12345)
    self.network        = NetworkAdapter.new(config.server_host or "127.0.0.1",
                                              config.server_port or 9000)

    -- 帧管理状态
    self.state = self.STATE.DISCONNECTED
    self.current_frame = 0          -- 当前已执行的逻辑帧号
    self.server_frame = 0           -- 服务器告知的最新帧号

    -- 提前发送: 客户端发送"未来帧"的输入
    -- 当前帧 = 100, 则发送帧 100+ADVANCE_SEND_FRAMES 的输入
    self.advance_send_frames = 3    -- 提前 3 帧发送 (约 200ms 缓冲)

    -- 断线重连
    self.max_frames_behind = config.max_frames_behind or 30

    -- 统计
    self.stats = {
        total_frames_executed = 0,
        total_frames_waited   = 0,   -- 因缺帧而等待的次数
        total_inputs_sent     = 0,
        catch_up_count        = 0,
    }

    -- 帧日志 (最近 N 帧的 Hash, 用于 desync 排查)
    self.frame_log = {}
    self.frame_log_max = 300  -- 保留最近 300 帧的 hash

    -- 表现层事件队列 (逻辑帧产生, 渲染帧消费)
    self.render_events = {}

    -- 回调函数 (由上层注册)
    self.on_render_event = nil  -- function(event)
    self.on_state_change = nil  -- function(old_state, new_state)
    self.on_desync       = nil  -- function(frame_no, local_hash, expected_hash)

    return self
end

--- 连接到服务器
--- @return boolean
function LockstepMgr:connect()
    self:_change_state(self.STATE.CONNECTING)
    local ok = self.network:connect()
    if ok then
        self:_change_state(self.STATE.CONNECTED)
    else
        self:_change_state(self.STATE.DISCONNECTED)
    end
    return ok
end

--- 开始游戏 (收到服务器的 game_start 消息后调用)
--- @param init_data table 初始实体数据
function LockstepMgr:start_game(init_data)
    self.logic_engine:init_entities(init_data)
    self.current_frame = 0
    self.server_frame = 0
    self:_change_state(self.STATE.RUNNING)
end

--- 每渲染帧调用一次 (由引擎主循环驱动)
--- @param dt number 渲染帧时间间隔 (秒)
function LockstepMgr:update(dt)
    if self.state ~= self.STATE.RUNNING
       and self.state ~= self.STATE.CATCHING_UP then
        return
    end

    -- ─── 第 1 步: 处理网络接收 ──────────────────────
    local packets = self.network:recv()
    if packets then
        for _, pkt in ipairs(packets) do
            self.frame_buffer:push(pkt.frame_no, pkt.inputs)
            if pkt.frame_no > self.server_frame then
                self.server_frame = pkt.frame_no
            end
        end
    end

    -- ─── 第 2 步: 断线检测 ──────────────────────────
    local frames_behind = self.server_frame - self.current_frame
    if frames_behind > self.max_frames_behind
       and self.state == self.STATE.RUNNING then
        print(string.format(
            "[LockstepMgr] 落后 %d 帧, 触发追赶模式", frames_behind))
        self:_change_state(self.STATE.CATCHING_UP)
    end

    -- ─── 第 3 步: 执行逻辑帧 ────────────────────────
    if self.state == self.STATE.RUNNING then
        self:_execute_normal_frame()
    elseif self.state == self.STATE.CATCHING_UP then
        self:_execute_catch_up_frame()
    end

    -- ─── 第 4 步: 发送本地输入 ──────────────────────
    self:_send_local_input()

    -- ─── 第 5 步: 消费渲染事件 ──────────────────────
    self:_flush_render_events()
end

-- ─── 内部: 正常帧执行 ──────────────────────────────

function LockstepMgr:_execute_normal_frame()
    local next_frame = self.current_frame + 1

    -- 检查帧缓冲区是否有下一帧数据
    if self.frame_buffer:has_frame(next_frame) then
        local inputs = self.frame_buffer:pop(next_frame)
        if inputs then
            -- 执行确定性逻辑
            local events = self.logic_engine:update(inputs)
            self.current_frame = next_frame

            -- 记录帧 Hash (desync 检测)
            self:_log_frame_hash(next_frame)

            -- 将事件加入渲染队列
            for _, evt in ipairs(events) do
                table.insert(self.render_events, evt)
            end

            self.stats.total_frames_executed = self.stats.total_frames_executed + 1

            -- 如果缓冲区中还有多帧, 连续执行 (追赶微小延迟)
            -- 但最多连续执行 5 帧, 避免单渲染帧占用过长时间
            local max_consume = 5
            local consumed = 1
            while consumed < max_consume do
                local nf = self.current_frame + 1
                if self.frame_buffer:has_frame(nf) then
                    local nf_inputs = self.frame_buffer:pop(nf)
                    if nf_inputs then
                        local more_events = self.logic_engine:update(nf_inputs)
                        self.current_frame = nf
                        self:_log_frame_hash(nf)
                        for _, evt in ipairs(more_events) do
                            table.insert(self.render_events, evt)
                        end
                        self.stats.total_frames_executed = self.stats.total_frames_executed + 1
                    end
                else
                    break
                end
                consumed = consumed + 1
            end
        end
    else
        -- 缺帧: 等待
        self.stats.total_frames_waited = self.stats.total_frames_waited + 1
    end
end

-- ─── 内部: 追赶模式帧执行 (断线重连) ───────────────

function LockstepMgr:_execute_catch_up_frame()
    -- 追赶模式: 每渲染帧执行尽可能多的逻辑帧 (不等待)
    -- 目标: 追上 self.server_frame
    local target = self.server_frame
    local max_per_frame = 20  -- 每渲染帧最多执行 20 逻辑帧

    local executed = 0
    while executed < max_per_frame and self.current_frame < target do
        local next_frame = self.current_frame + 1
        if self.frame_buffer:has_frame(next_frame) then
            local inputs = self.frame_buffer:pop(next_frame)
            if inputs then
                self.logic_engine:update(inputs)
                self.current_frame = next_frame
                self:_log_frame_hash(next_frame)
                self.stats.total_frames_executed = self.stats.total_frames_executed + 1
                executed = executed + 1
            else
                break
            end
        else
            -- 缺帧: 向服务器请求补发
            -- (实际实现中应使用 dedicated 补帧协议)
            print(string.format("[LockstepMgr] 追赶模式缺帧: %d", next_frame))
            break
        end
    end

    -- 检查是否追上了
    if self.current_frame >= target - 2 then  -- 允许 2 帧容差
        print("[LockstepMgr] 追赶完成")
        self:_change_state(self.STATE.RUNNING)
        self.stats.catch_up_count = self.stats.catch_up_count + 1
    end
end

-- ─── 内部: 发送本地输入 ────────────────────────────

function LockstepMgr:_send_local_input()
    -- 收集本 Bucket 的输入
    local input = self.input_collector:collect()

    -- 提前发送: 发送的是 future_frame 的输入
    local future_frame = self.current_frame + self.advance_send_frames

    self.network:send_input(future_frame, input)
    self.stats.total_inputs_sent = self.stats.total_inputs_sent + 1
end

-- ─── 内部: 帧 Hash 日志 ────────────────────────────

function LockstepMgr:_log_frame_hash(frame_no)
    local hash = self.logic_engine:compute_state_hash()

    -- 写入环形帧日志
    table.insert(self.frame_log, {
        frame_no = frame_no,
        hash = hash,
        time = os.clock(),  -- 仅用于调试, 不参与逻辑
    })
    -- 限制日志大小
    while #self.frame_log > self.frame_log_max do
        table.remove(self.frame_log, 1)
    end

    -- 通过 C 引擎输出帧日志 (用于远程 desync 排查)
    engine.frame_log(frame_no, "HASH", "frame=%d hash=0x%08X",
        frame_no, hash)
end

-- ─── 内部: 状态切换 ────────────────────────────────

function LockstepMgr:_change_state(new_state)
    local old = self.state
    if old ~= new_state then
        self.state = new_state
        if self.on_state_change then
            self.on_state_change(old, new_state)
        end
        print(string.format("[LockstepMgr] 状态: %d → %d", old or 0, new_state))
    end
end

-- ─── 内部: 消费渲染事件 ────────────────────────────

function LockstepMgr:_flush_render_events()
    -- 将逻辑层产生的事件传递给表现层
    -- 注意: 表现层的实体操作会涉及 C 引擎绑定
    for _, evt in ipairs(self.render_events) do
        if evt.type == "move" then
            -- 更新渲染实体位置
            engine.entity_set_position(evt.entity_id, evt.x, evt.y, 0)
            -- 播放移动动画 (如果是首次移动)
            -- engine.entity_play_animation(evt.entity_id, "walk", 1)

        elseif evt.type == "attack" then
            engine.entity_play_animation(evt.entity_id, "attack", 0)

        elseif evt.type == "hurt" then
            engine.entity_play_animation(evt.entity_id, "hurt", 0)

        elseif evt.type == "death" then
            engine.entity_play_animation(evt.entity_id, "dead", 0)
        end

        if self.on_render_event then
            self.on_render_event(evt)
        end
    end

    -- 清空事件队列
    self.render_events = {}
end

-- ─── 公共接口 ──────────────────────────────────────

--- 处理触屏事件 (转发给 InputCollector)
function LockstepMgr:on_touch(event_type, x, y, touch_id)
    self.input_collector:on_touch(event_type, x, y, touch_id)
end

--- 处理技能按钮
function LockstepMgr:on_skill_button(skill_index)
    self.input_collector:on_skill_button(skill_index)
end

--- 处理闪避按钮
function LockstepMgr:on_dodge_button()
    self.input_collector:on_dodge_button()
end

--- 获取当前帧号
function LockstepMgr:get_current_frame()
    return self.current_frame
end

--- 获取统计信息
function LockstepMgr:get_stats()
    return self.stats
end

--- 断开连接
function LockstepMgr:disconnect()
    self.network:disconnect()
    self:_change_state(self.STATE.DISCONNECTED)
end

return LockstepMgr
```

---

## 3. 完整 Demo：横版格斗/ARPG 2人对战

### 3.1 场景设定

```
┌─────────────────────────────────────────────┐
│                  横版格斗场景                  │
│                                              │
│   [P1 战士]              [P2 弓手]            │
│   HP: 100                HP: 80              │
│   ATK: 15                ATK: 12             │
│   SPD: 3                 SPD: 4              │
│   RNG: 近战               RNG: 远程           │
│                                              │
│   ←──────── 战场宽度 800 ──────────→          │
└─────────────────────────────────────────────┘
```

### 3.2 主入口文件 (main.lua)

```lua
-- ============================================
-- main.lua — 横版格斗 Demo 入口
-- ============================================
-- 运行方式:
--   1. 启动帧同步服务器 (略, 见第 11 节)
--   2. 启动客户端 A: lua main.lua --player_id=0 --server=127.0.0.1:9000
--   3. 启动客户端 B: lua main.lua --player_id=1 --server=127.0.0.1:9000
-- ============================================

local LockstepMgr = require("lockstep_mgr")

-- ─── 解析命令行参数 ────────────────────────────────
local player_id = 0
local server_host = "127.0.0.1"
local server_port = 9000

-- 在真实环境中, 这些参数由 C 引擎传入
-- player_id = tonumber(arg[1]) or 0

print(string.format("[Demo] 帧同步格斗 Demo — Player %d", player_id))

-- ─── 创建 Lockstep 管理器 ──────────────────────────
local mgr = LockstepMgr.new({
    player_id       = player_id,
    player_count    = 2,
    logic_frame_rate = 15,        -- 15Hz 逻辑帧
    buffer_size     = 128,        -- 缓冲 128 帧 (~8.5 秒)
    max_frames_behind = 30,       -- 落后 30 帧触发追赶
    random_seed     = 0xDEADBEEF, -- 所有客户端相同的种子
    server_host     = server_host,
    server_port     = server_port,
})

-- ─── 注册回调 ─────────────────────────────────────

-- 渲染事件回调: 驱动表现层
mgr.on_render_event = function(event)
    -- 在真实引擎中, 这里会调用引擎 API
    -- 此处仅打印到控制台
    if event.type == "move" then
        -- print(string.format("  → 移动: E%d → (%.1f, %.1f)",
        --     event.entity_id, event.x, event.y))
    elseif event.type == "attack" then
        print(string.format("  ⚔ 攻击: E%d → E%d (伤害: %d)",
            event.entity_id, event.target_id, event.damage))
    elseif event.type == "hurt" then
        print(string.format("  💥 受伤: E%d -%d HP (剩余: %d)",
            event.entity_id, event.damage, event.hp))
    elseif event.type == "death" then
        print(string.format("  ☠ 死亡: E%d", event.entity_id))
    end
end

-- 状态变化回调
mgr.on_state_change = function(old_state, new_state)
    local state_names = {
        [0] = "DISCONNECTED", [1] = "CONNECTING", [2] = "CONNECTED",
        [3] = "RUNNING",       [4] = "CATCHING_UP", [5] = "PAUSED", [6] = "ENDED"
    }
    print(string.format("[状态] %s → %s",
        state_names[old_state] or "?",
        state_names[new_state] or "?"))
end

-- ─── 模拟输入 (因为没有真实触屏, 用随机输入代替) ──
local input_timer = 0
local function simulate_input(dt)
    input_timer = input_timer + dt
    -- 每 0.5 秒生成一次随机输入
    if input_timer >= 0.5 then
        input_timer = 0
        local r = math.random()
        if r < 0.4 then
            -- 随机移动方向
            local dx = (math.random() - 0.5) * 2
            local dy = (math.random() - 0.5) * 2
            mgr.input_collector.joystick_x = dx
            mgr.input_collector.joystick_y = dy
            mgr.input_collector.joystick_active = true
            -- 1 秒后停止移动 (下一次 tick 归零)
        elseif r < 0.7 then
            -- 攻击
            mgr:on_touch("began", 0.5, 0.5, 1)
            mgr:on_touch("ended", 0.5, 0.5, 1)
        elseif r < 0.9 then
            -- 技能
            mgr:on_skill_button(math.random(1, 3))
        else
            -- 闪避
            mgr:on_dodge_button()
        end
    end
end

-- ─── 初始化实体数据 ────────────────────────────────
-- 所有客户端必须使用完全相同的初始数据!
local init_data = {
    [100] = {
        player_id = 0,
        type = "warrior",
        x = 200, y = 50, z = 0,
        facing = 1,
        hp = 100, max_hp = 100,
    },
    [200] = {
        player_id = 1,
        type = "archer",
        x = 600, y = 50, z = 0,
        facing = -1,
        hp = 80, max_hp = 80,
    },
}

-- ─── 模拟帧循环 ────────────────────────────────────
local function run_simulation(total_seconds)
    local dt = 1.0 / 60  -- 渲染帧间隔 (60fps)
    local total_frames = math.floor(total_seconds * 60)

    -- 连接
    local ok = mgr:connect()
    if not ok then
        print("[Demo] 连接失败, 将使用本地模拟模式")
        -- 本地模拟: 手动填充帧缓冲区
        mgr:_change_state(3)  -- 直接进入 RUNNING
    end

    -- 初始实体
    mgr:start_game(init_data)

    print(string.format("[Demo] 开始模拟 %d 秒 (%d 渲染帧)", total_seconds, total_frames))
    local start_time = os.clock()

    for i = 1, total_frames do
        -- 模拟输入
        simulate_input(dt)

        -- 在本地模拟模式下, 手动填充帧缓冲 (模拟服务器下发)
        if not mgr.network.connected then
            -- 构造一个包含空输入的帧, 让 Demo 能跑起来
            local frame_no = mgr:get_current_frame() + 1
            local inputs = {}
            inputs[0] = mgr.input_collector:collect()  -- P0 的输入
            inputs[1] = { type = 0, args = {}, flags = 0 } -- P1 空输入
            mgr.frame_buffer:push(frame_no, inputs)
            mgr.server_frame = frame_no + 5  -- 模拟服务器领先 5 帧
        end

        -- 主循环更新
        mgr:update(dt)

        -- 每 60 渲染帧 (1 秒) 打印一次统计
        if i % 60 == 0 then
            local stats = mgr:get_stats()
            print(string.format(
                "[%5.1fs] 逻辑帧=%d, 执行=%d, 等待=%d, 发送=%d",
                i * dt,
                mgr:get_current_frame(),
                stats.total_frames_executed,
                stats.total_frames_waited,
                stats.total_inputs_sent
            ))
        end
    end

    local elapsed = os.clock() - start_time
    local stats = mgr:get_stats()
    print("\n===== 模拟结束 =====")
    print(string.format("耗时: %.2f 秒", elapsed))
    print(string.format("执行逻辑帧: %d", stats.total_frames_executed))
    print(string.format("缺帧等待: %d", stats.total_frames_waited))
    print(string.format("追赶次数: %d", stats.catch_up_count))
    print(string.format("最终帧号: %d", mgr:get_current_frame()))
    print(string.format("最终状态 Hash: 0x%08X", mgr.logic_engine:compute_state_hash()))

    -- 断开
    mgr:disconnect()
end

-- ─── 启动模拟 ──────────────────────────────────────
run_simulation(5)  -- 运行 5 秒
```

---

## 4. 性能优化：LuaJIT、FFI 与热点下沉

### 4.1 LuaJIT 的关键优化

LuaJIT 的 JIT 编译器可以将热点 Lua 代码编译为原生机器码，性能接近 C。但前提是代码满足 JIT 的"可编译"条件：

**① 避免 NYI (Not Yet Implemented) 操作**

以下 Lua 标准库函数在 LuaJIT 中**不会**被 JIT 编译：
- `string.format()` — 用 `..` 拼接代替
- `table.insert()` / `table.remove()` — 用 `t[#t+1] = v` 代替
- `pairs()` — 用 `for i=1,#t do` 代替 (如果 key 是连续整数)
- `math.random()` — 帧同步中本来就不该用

**② 保持类型稳定**

JIT 编译器会追踪变量类型。如果同一个变量在不同时刻是 `number` 和 `table`，JIT 会生成守卫代码并频繁回退到解释器：

```lua
-- 差: 类型不稳定, JIT 无法优化
local x = 0
for i = 1, 1000 do
    if i % 2 == 0 then
        x = x + 1       -- x 是 number
    else
        x = { val = i } -- x 是 table → JIT 回退!
    end
end

-- 好: 类型始终是 number
local x = 0
for i = 1, 1000 do
    x = x + 1  -- JIT 生成高效的整数运算
end
```

**③ 使用 `ffi.new` 而非 Lua Table 存热点数据**

Lua table 的灵活性代价是每次访问都有 hash 查找。对于帧同步中频繁访问的实体数据，用 FFI 的 C struct 可以消除 hash 开销：

```lua
local ffi = require("ffi")
ffi.cdef([[
    typedef struct {
        int32_t id;
        int32_t player_id;
        int32_t x, y, z;
        int32_t vx, vy;
        int32_t hp, max_hp;
        int32_t state;
        int32_t state_timer;
        int32_t attack_cooldown;
    } LogicEntity;
]])

-- 预分配实体数组 (arena 风格, 避免逐次分配)
local MAX_ENTITIES = 200
local entities = ffi.new("LogicEntity[?]", MAX_ENTITIES)
local entity_count = 0

-- 访问: entities[i].x, entities[i].hp 等
-- 这会被编译为直接的 C 结构体偏移访问
```

### 4.2 热点代码下沉到 C

Lua 层的核心原则：**Lua 做调度和组合，C 做密集计算**。

哪些代码应该下沉到 C 层？

| 操作 | Lua 性能 | C 性能 | 下沉建议 |
|------|---------|--------|---------|
| 定点数乘除 (每帧数千次) | ~100ns | ~1ns | **必须下沉** |
| AABB 碰撞检测 (100 实体 O(n²)) | ~50μs | ~5μs | **强烈建议** |
| 距离计算 (sqrt) | ~30ns | ~5ns | 建议 (配合定点数) |
| 实体遍历调度 | ~1μs | ~1μs | 没必要, Lua 够快 |
| 输入收集 | ~1μs | ~1μs | 没必要 |
| 状态 Hash 计算 | ~5μs | ~500ns | 可下沉 (如果每帧计算) |

### 4.3 FFI 调用 C 定点数库示例

```lua
-- fixed_math_ffi.lua — LuaJIT FFI 调用 C 定点数库
local ffi = require("ffi")

ffi.cdef([[
    typedef int32_t fixed_t;

    fixed_t fixed_from_float(float val);
    float   fixed_to_float(fixed_t val);
    fixed_t fixed_add(fixed_t a, fixed_t b);
    fixed_t fixed_sub(fixed_t a, fixed_t b);
    fixed_t fixed_mul(fixed_t a, fixed_t b);
    fixed_t fixed_div(fixed_t a, fixed_t b);
    fixed_t fixed_sqrt(fixed_t a);
    fixed_t fixed_sin(fixed_t angle);
    fixed_t fixed_cos(fixed_t angle);
]])

local C = ffi.C

local FixedMath = {}

function FixedMath.from_float(val)
    return tonumber(C.fixed_from_float(val))
end

function FixedMath.to_float(val)
    return tonumber(C.fixed_to_float(val))
end

function FixedMath.add(a, b)
    return tonumber(C.fixed_add(a, b))
end

function FixedMath.mul(a, b)
    return tonumber(C.fixed_mul(a, b))
end

-- 在 LogicEngine 中使用:
-- local fx, fy = FixedMath.add(ent.x, FixedMath.mul(dx, MOVE_SPEED_FP))
```

---

## 5. 调试与测试

### 5.1 Lua 单元测试 (busted)

```lua
-- ============================================
-- test_frame_buffer.lua — FrameBuffer 单元测试
-- 运行: busted test_frame_buffer.lua
-- ============================================
local FrameBuffer = require("frame_buffer")

describe("FrameBuffer", function()
    local fb

    before_each(function()
        fb = FrameBuffer.new(8, 2)
    end)

    it("初始状态为空", function()
        assert.are.equal(0, fb:size())
        assert.is_nil(fb:get_frame_range())
    end)

    it("push 和 pop 正常", function()
        local inputs = { [0] = { type = 1 }, [1] = { type = 0 } }
        fb:push(1, inputs)
        assert.are.equal(true, fb:has_frame(1))
        assert.are.equal(1, fb:size())

        local popped = fb:pop(1)
        assert.are.same(inputs, popped)
        assert.are.equal(0, fb:size())
        assert.are.equal(false, fb:has_frame(1))
    end)

    it("缓冲区满时覆盖最旧帧", function()
        for i = 1, 8 do
            fb:push(i, {})
        end
        assert.are.equal(8, fb:size())

        -- 第 9 帧应该覆盖第 1 帧
        fb:push(9, {})
        assert.are.equal(8, fb:size())
        assert.are.equal(false, fb:has_frame(1))
        assert.are.equal(true, fb:has_frame(9))
    end)

    it("帧号过旧时丢弃", function()
        fb:push(10, {})
        fb:push(11, {})
        fb:pop(10)
        -- 帧 10 已被消费, push 9 应该被拒绝
        local ok = fb:push(9, {})
        assert.are.equal(false, ok)
    end)

    it("get_frame_range 正确返回范围", function()
        fb:push(5, {})
        fb:push(8, {})
        fb:push(3, {})
        local min_f, max_f = fb:get_frame_range()
        assert.are.equal(3, min_f)
        assert.are.equal(8, max_f)
    end)
end)
```

```lua
-- ============================================
-- test_logic_engine.lua — 确定性逻辑测试
-- ============================================
local LogicEngine = require("logic_engine")

describe("LogicEngine", function()
    local engine1, engine2
    local init_data = {
        [100] = { player_id = 0, type = "warrior", x = 0, y = 0, hp = 100 },
        [200] = { player_id = 1, type = "warrior", x = 50, y = 0, hp = 100 },
    }

    before_each(function()
        engine1 = LogicEngine.new(12345)
        engine1:init_entities(init_data)
        engine2 = LogicEngine.new(12345)
        engine2:init_entities(init_data)
    end)

    it("相同输入产生相同 Hash", function()
        local inputs = {
            [0] = { type = 2, args = {}, flags = 0 },  -- P0 攻击
            [1] = { type = 0, args = {}, flags = 0 },  -- P1 空操作
        }

        engine1:update(inputs)
        engine2:update(inputs)

        local hash1 = engine1:compute_state_hash()
        local hash2 = engine2:compute_state_hash()
        assert.are.equal(hash1, hash2)
    end)

    it("不同输入产生不同 Hash (desync 检测)", function()
        engine1:update({ [0] = { type = 2 } })  -- P0 攻击
        engine2:update({ [0] = { type = 0 } })  -- P0 空操作

        local hash1 = engine1:compute_state_hash()
        local hash2 = engine2:compute_state_hash()
        assert.are_not.equal(hash1, hash2)
    end)

    it("攻击命中伤害对方 HP", function()
        -- P0 (x=0) 和 P1 (x=50) 距离 50 > 40 (攻击范围)
        -- 所以第一帧攻击应该 miss
        engine1:update({ [0] = { type = 2 }, [1] = { type = 0 } })

        local ent_p1 = engine1.entities[200]
        assert.are.equal(100, ent_p1.hp)  -- 距离太远, 不受伤害

        -- 让 P0 靠近 P1: 移动 3 帧 (每帧 3px)
        for i = 1, 3 do
            engine1:update({
                [0] = { type = 1, args = { 1, 0 } },  -- 向右移动
                [1] = { type = 0 },
            })
        end
        -- P0.x = 9, P1.x = 50, 距离 = 41 > 40, 仍然太远

        engine1:update({
            [0] = { type = 1, args = { 1, 0 } },
            [1] = { type = 0 },
        })
        -- P0.x = 12, P1.x = 50, 距离 = 38 < 40

        -- 现在攻击
        engine1:update({
            [0] = { type = 2 },  -- P0 攻击
            [1] = { type = 0 },
        })
        -- 检查冷却, 不能连续攻击
        ent_p1 = engine1.entities[200]
        -- 此时 P0 刚攻击完, 还在冷却中
    end)
end)
```

### 5.2 帧日志与 Desync 排查

帧日志是帧同步调试的核心手段。当 QA 报告 "两个玩家看到的结果不同" 时，开发者需要对比两边的帧日志。

典型的帧日志输出：

```
[Frame  100] HASH: frame=100 hash=0x3A7B2C1F
[Frame  101] HASH: frame=101 hash=0x3A7B3D5E
[Frame  102] HASH: frame=102 hash=0x3A7B4E9D
[Frame  103] HASH: frame=103 hash=0x3A8B1C2F  ← 不一致! (玩家A)
[Frame  103] HASH: frame=103 hash=0x3A7B5FDC  ← 不一致! (玩家B)
```

排查流程：
1. 找到 Hash 首次出现分歧的帧号 (本例为 Frame 103)
2. 对比 Frame 102 两边各自的输入是否一致
3. 如果输入一致 → 逻辑代码有非确定性行为
4. 如果输入不一致 → 网络层丢包或序列化错误
5. 二分法定位：在可疑帧前后插入更细粒度的日志 (每个实体操作后记录 hash)

---

## 6. 练习

### 练习 1: 基础 — 补全 FrameBuffer 与基础流程（30min）

基于 2.1 节的 `frame_buffer.lua`，完成以下任务：

1. **实现按帧号直接索引**：修改 `find_slot` 方法，使用 `(frame_no - base_frame) % capacity + 1` 实现 O(1) 查找，而非当前的 O(n) 线性扫描。维护 `base_frame` 变量，在 `pop` 时更新它。

2. **编写完整的 busted 测试**：覆盖以下场景：
   - 边界：缓冲区满时 push 的行为
   - 边界：pop 不存在的帧号返回 nil
   - 边界：push 帧号跳跃 (如 push(1), push(100))，缓冲区如何处理
   - 边界：clear 后 size 为 0, range 为 nil

3. **压力测试**：创建一个 FrameBuffer(256, 10)，循环 push 10000 帧后检查 size 是否仍 ≤ 256，内存是否有泄漏。

### 练习 2: 进阶 — 实现去中心化的 P2P Lockstep（45min）

修改整个框架，从 Server-Relayed 模型切换到 **P2P Lockstep** 模型：

1. **去除服务器依赖**：修改 `NetworkAdapter`，不再连接服务器，改为 P2P 直连（假设已有 NAT 穿透）。
2. **输入广播**：每个客户端将自己的输入直接发送给其他所有玩家，而非经由服务器中转。
3. **等待屏障**：每个客户端必须收到**所有其他玩家**的输入后才能执行逻辑帧。如果某个玩家延迟，其他玩家应暂停等待（通过 `FrameBuffer` 缺帧自然实现）。
4. **测试**：模拟 2 个客户端，一个正常 50ms 延迟，另一个 500ms 延迟——观察延迟玩家如何拖慢整体游戏。

### 练习 3: 挑战 — 重新实现 LogicEngine 使用纯 C 定点数（60min）

将 2.4 节的 `logic_engine.lua` 中所有浮点运算替换为 C 定点数：

1. **编写 C 定点数库**：基于第 6 节的知识，实现 Q16.16 格式的定点数加减乘除、sqrt、sin/cos (CORDIC)，编译为动态链接库。
2. **LuaJIT FFI 绑定**：编写 FFI 包装层，让 `logic_engine.lua` 通过 FFI 调用 C 定点数函数。
3. **验证确定性**：在两个不同的 Lua 环境（Lua 5.1 + LuaJIT）下运行相同的输入序列，验证每帧 Hash 一致。
4. **性能对比**：Benchmark 相同逻辑在纯 Lua table 实现 vs FFI struct 实现 vs FFI 定点数实现下的性能差异（帧执行时间）。

要求：提供完整的 benchmark 脚本和结果分析。

---

## 7. 扩展阅读

### 必读文章
- **云风 — Lua 在游戏开发中的应用**：中国游戏行业 Lua 应用的先驱
  https://blog.codingnow.com/
- **LuaJIT 官方文档 — FFI Tutorial**：直接调用 C 函数的完整指南
  https://luajit.org/ext_ffi_tutorial.html
- **Gaffer On Games — Deterministic Lockstep**：帧同步理论基础
  https://gafferongames.com/post/deterministic_lockstep/

### 开源项目
- **skynet (GitHub: cloudwu/skynet)**：云风开发的基于 Lua 的游戏服务器框架，大量使用 C + Lua 混合架构
- **ET (GitHub: egametang/ET)**：Unity+C# 的 ECS 框架，其中 ILRuntime 热更方案的思想与 Lua 热更类似
- **LuaLockstep (GitHub 搜索)**：多个基于 Lua 的帧同步开源 Demo

### 大厂实践
- **王者荣耀 Lua 架构**：C++ 引擎 + Lua 战斗逻辑 + Lua 帧同步，热更新周期 < 1 天
- **和平精英 Lua 架构**：Unreal 引擎 + slua/unlua 绑定 + Lua 逻辑层，支持 Android/iOS/PC 多平台
- **崩坏3 / 原神**：Unity + xLua + C#，Lua 负责战斗和任务逻辑

### 本计划相关
- 第 6 节：**确定性游戏逻辑：定点数与跨平台一致性**
- 第 7 节：**帧同步协议设计：帧指令、冗余发包、丢包处理**
- 第 11 节：**帧同步服务端设计：帧对齐与乐观帧锁定**

---

## 常见陷阱

### 陷阱 1: 在 Lua 层使用 `math.random()`

**错误**：用 `math.random()` 生成暴击判定、掉落等随机结果。

**为什么错**：`math.random()` 的实现在不同操作系统/不同 Lua 版本中不同，种子机制也不一致。即使相同代码，两个平台从同一帧开始调用 `math.random()` 也会产生不同的序列。

**正确做法**：使用确定性 PRNG（如 xorshift32/64, PCG），将帧号和事件序数作为种子参数，而非依赖全局状态。Lua 的 `bit` 或 `bit32` 库提供的位运算可以保证跨平台一致性（Lua 5.2+ 或 LuaJIT）。

### 陷阱 2: 用 `pairs()` 遍历需要顺序的集合

**错误**：
```lua
for eid, ent in pairs(self.entities) do
    ent.x = ent.x + ent.vx  -- 遍历顺序不确定!
end
```

**为什么错**：`pairs()` 遍历 table 的顺序是**未定义**的，本质上是 hash 表的内存布局顺序。不同 Lua 版本/JIT 模式下，相同数据可能产生不同的遍历顺序。如果实体更新顺序影响结果（例如 A 推开 B，同时 B 推开 A），遍历顺序不同 → desync。

**正确做法**：收集 key 到数组，排序后按序访问：
```lua
local sorted_ids = {}
for eid in pairs(self.entities) do
    table.insert(sorted_ids, eid)
end
table.sort(sorted_ids)
for _, eid in ipairs(sorted_ids) do
    local ent = self.entities[eid]
    -- 处理...
end
```

### 陷阱 3: 依赖 `os.clock()` 或 `os.time()` 做逻辑决策

**错误**：
```lua
local current_time = os.clock()
if current_time - self.last_attack_time > 1.0 then
    -- 允许攻击
end
```

**为什么错**：`os.clock()` 返回的是 CPU 时间，不同设备的时钟精度和偏移不同。依赖真实时间会导致不同客户端在相同帧号下看到不同的时间值 → 不同的逻辑分支 → desync。

**正确做法**：用逻辑帧数计时：
```lua
-- 攻击冷却 = 15 逻辑帧 (15fps = 1 秒)
self.attack_cooldown = 15
-- 每逻辑帧递减
if self.attack_cooldown > 0 then
    self.attack_cooldown = self.attack_cooldown - 1
end
```

### 陷阱 4: 忘记限制逻辑帧追赶速度

**错误**：断线重连后，追赶模式下无限制地执行逻辑帧。

**为什么错**：如果落后 1000 帧，一次性执行完会导致客户端卡死数秒。而且渲染层来不及消费逻辑层产生的海量事件。

**正确做法**：追赶模式下每渲染帧最多执行 N 帧（通常 15-30），确保渲染层至少能以 1fps 以上的速度响应。同时跳过非关键的渲染事件（如移动过程中的中间位置），只保留关键的最终事件（伤害、死亡）。

### 陷阱 5: C 绑定层的线程安全问题

**错误**：在 Lua 层的逻辑帧执行过程中，C 引擎的渲染线程同时调用 `engine.entity_set_position` 修改实体位置。

**为什么错**：Lua 不是线程安全的。如果 C 引擎在渲染线程中直接操作 Lua state，会导致内存损坏、crash 或不可预期的行为。

**正确做法**：
- 逻辑帧执行和渲染更新在**同一线程**中进行
- 或者使用双缓冲：逻辑层更新 "影子" entity 表，渲染线程在安全时机交换缓冲
- 更常见的做法：Lua 虚拟机只运行在主线程中，渲染通过事件队列异步通知 C 层

### 陷阱 6: FFI 指针的生命周期管理

**错误**：
```lua
local function create_entity(x, y)
    local ent = ffi.new("Entity")  -- 在栈上分配
    ent.x = x
    ent.y = y
    return ent  -- 返回后可能被 GC 回收!
end
```

**为什么错**：`ffi.new` 分配的 cdata 对象可以由 Lua GC 自动回收，但如果 C 层持有了该指针（比如存入了链表），GC 回收后 C 层出现悬垂指针 → crash。

**正确做法**：
- 使用 `ffi.gc(obj, destructor)` 注册析构回调
- 或者在 Lua 层维护一个锚定 table，确保指针在 C 层使用期间不被 GC
- 对于长生命周期的实体，使用 `ffi.new` 的数组形式 (`ffi.new("Entity[?]", count)`) 并手动管理索引

### 陷阱 7: Lua 5.1/5.2/5.3 的位运算差异

**错误**：在 Lua 5.1 中使用 `&`, `|`, `<<`, `>>` 运算符。

**为什么错**：Lua 5.1 **没有**位运算符。这些运算符在 Lua 5.3 中才被引入。王者荣耀早期版本使用的 Lua 5.1 需要通过 `bit` 库 (`require("bit")`) 或 `bit32` 库进行位运算。LuaJIT 则内置了 `bit` 扩展。

**正确做法**：
- 统一使用兼容层:
```lua
local bit = require("bit32") or require("bit") or _G.bit
-- 如果 Lua 5.3+, 直接使用原生运算符
if _VERSION == "Lua 5.3" or _VERSION == "Lua 5.4" then
    band = load("return function(a,b) return a & b end")()
end
```
- 或者统一在 C 层完成所有位运算，Lua 层只传整数并拿回结果
