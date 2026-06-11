---
title: "FSM 在 Lua 中的实现"
updated: 2026-06-05
---

# FSM 在 Lua 中的实现

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 90min
> 前置知识: [[01-fsm-core-concepts]]

---

## 1. 概念讲解

### 为什么 Lua 是 FSM 的天然良配？

Lua 不是为游戏 AI 设计的语言——但它拥有的几个语言特性，碰巧让它在实现 FSM 时表现出超越 C++/C# 的简洁性。理解这些特性，你就能在合适的场景下用十分之一的代码量完成同样的事情。

#### 动态类型 = 零样板代码

在 C++ 中定义一个状态，你需要：写一个基类、声明虚函数、为每个具体状态创建子类、管理头文件和编译依赖。在 C# 中你需要接口、`MonoBehaviour`、序列化字段。

在 Lua 中，一个状态就是一个 table：

```lua
local PatrolState = {
    enter = function(self, enemy) enemy.speed = 2 end,
    update = function(self, enemy, dt) --[[ 巡逻逻辑 ]] end,
    exit = function(self, enemy) end,
}
```

没有类型声明，没有继承链，没有构建系统。这个 table **就是**状态的全部定义。当你需要新增一个状态时，新建一个 table 即可——不需要修改任何 switch 语句或工厂函数（尽管稍后我们会讲到，table 的灵活性也带来了必须警惕的陷阱）。

#### Table 即状态，函数即过渡

Lua 的一等函数（first-class function）意味着转移条件、状态行为和进入/退出回调都可以作为 table 的字段存储。你可以写出这样的代码：

```lua
-- 状态 table 直接包含转移规则
local PatrolState = {
    enter = function(self, enemy) end,
    update = function(self, enemy, dt) end,
    exit = function(self, enemy) end,
    -- 转移规则：{ 事件名 = { 条件, 目标状态 } }
    transitions = {
        player_detected  = { check = function(e) return distance(e, player) < 10 end, target = "Chase" },
        health_zero      = { check = function(e) return e.health <= 0 end, target = "Dead" },
    },
}
```

函数作为一等值被存储在 table 里，在运行时被遍历和调用。不需要观察者模式、事件总线或反射机制——语言本身已经给了你需要的一切。

#### first-class 函数的下游收益

一等函数还带来了一个容易被忽视的好处：**行为参数化**。你可以把行为差异作为函数注入同一个状态模板，而不是为细微差异创建新状态：

```lua
function MakePatrolState(waypoints, on_arrive_callback)
    return {
        enter = function(self, npc) npc.waypoint_index = 1 end,
        update = function(self, npc, dt)
            -- 通用巡逻逻辑...
            if reached_waypoint(npc) then
                on_arrive_callback(npc)  -- 行为差异由外部注入
            end
        end,
    }
end

-- 守卫：到达路径点后停顿 2 秒
local guard_patrol = MakePatrolState(guard_waypoints, function(npc) npc.pause_timer = 2 end)
-- 信使：到达路径点后触发对话
local messenger_patrol = MakePatrolState(messenger_waypoints, function(npc) trigger_dialogue(npc) end)
```

这种"高阶状态工厂"模式在 C++ 中需要模板 + `std::function` + 类型擦除，在 C# 中需要委托或接口，而在 Lua 中只是把一个函数放进 table——三行代码。

#### 协程：顺序逻辑的终极武器

Lua 的协程（coroutine）为 FSM 提供了一种独特的状态表示方式：**每个状态是一个协程函数，状态内部使用 `coroutine.yield()` 将控制权交还给引擎**。这意味着：

- 传统的 FSM：进入 `Chase` → 每帧调用 `Chase.update(dt)` → 在 update 里写 if/else 管理追击的各阶段 → 退出
- 协程式 FSM：`Chase` 是一个单函数，用 `yield` 让出控制权。追击分为：靠近、绕后、攻击——这些阶段写成顺序代码，用 `yield` 等待条件满足

```lua
function chase_coroutine(enemy)
    while true do
        -- 阶段 1: 靠近玩家
        while distance_to_player(enemy) > 5 do
            move_toward(enemy, player.x, player.y)
            coroutine.yield()  -- 每帧让出控制
        end
        -- 阶段 2: 绕到侧面
        while not is_flanking(enemy, player) do
            strafe_around(enemy, player)
            coroutine.yield()
        end
        -- 阶段 3: 攻击
        attack(enemy)
        coroutine.yield()
    end
end
```

这种写法把"一个状态内部的子阶段转换"从显式状态机降维成了**顺序代码 + yield 语句**。对于对话系统、过场动画、Boss 阶段切换等天然具有顺序逻辑的场景，协程式 FSM 的代码量和认知负担都会大幅降低。

#### Metatable 与状态继承

Lua 的 metatable 可以实现类似面向对象的继承，但比 class 更灵活。当多个状态共享相同的行为时，你可以将通用逻辑放在基状态中，具体状态通过 metatable 的 `__index` 回退查找：

```lua
local BaseState = {
    enter = function(self, entity) end,   -- 默认不做事
    exit  = function(self, entity) end,
}

local AttackState = setmetatable({}, { __index = BaseState })
AttackState.update = function(self, entity, dt)
    -- 只需要覆盖 update，enter/exit 自动从 BaseState 继承
end
```

这种方式没有类层次结构的刚性约束——你可以在运行时动态切换 metatable、添加或删除方法。对于需要频繁迭代和热更新的游戏 AI 系统，这种灵活性意味着你可以在不重启游戏的情况下修改敌人行为。

### Lua 在游戏工业中的位置

理解 Lua 在游戏 AI 中的实际使用场景，有助于你判断何时用 Lua 实现 FSM，何时不该。

| 引擎/框架 | 使用方式 | FSM 场景 |
|-----------|----------|----------|
| **LÖVE2D** | 纯 Lua 游戏框架 | 所有 AI 逻辑全在 Lua 中。适合 2D 独立游戏原型和完整产品。 |
| **Defold** | Lua 脚本驱动引擎 | 游戏逻辑层用 Lua 编写，引擎层用 C++。FSM 通常在 Lua 脚本中定义。 |
| **Roblox (Luau)** | Luau 是 Lua 的类型标注超集 | 大量 UGC 游戏的 AI 在客户端或服务端 Lua 中运行。Roblox 提供了丰富的 AI 相关 API。 |
| **自定义 C++ 引擎 + Lua** | Lua 作为脚本层 | **AAA 中最常见的模式**。引擎层用 C++ 实现高性能 FSM 框架，Lua 侧用 table 描述状态和转移的具体逻辑。C++ 负责调度、Lua 负责行为定义。这是下面"混合架构"部分的核心主题。 |
| **World of Warcraft** | Lua 用于 UI 和部分 AI 脚本 | WoW 的 UI 完全由 Lua 驱动，部分 Boss AI 的脚本层也使用 Lua。 |

在 AAA 工作室中，Lua 通常不是 FSM 的"主实现语言"。核心 FSM 框架（Update 循环、事件分发、Enter/Exit 调度、内存管理）在 C++ 中实现，而**具体状态的行为逻辑**由 Lua 脚本编写。这种分工的核心原因是：

1. **热更新**：设计师可以修改 Lua 脚本调整 AI 行为，无需重新编译 C++。
2. **沙盒安全**：Lua 脚本崩溃不会带垮整个引擎。
3. **迭代速度**：Lua 的 table 语法天然适合配置驱动开发——设计师写出状态转移表比填 Excel 更快。

### 从 C++ FSM 到 Lua FSM 的思维转换

如果你来自 C++/C# 背景（特别是刚完成 Tutorial 02 和 03），切换到 Lua 时需要放下几个习惯：

1. **放下类型系统**。不需要定义 `IState` 接口或 `FState` 基类。状态的"合法性"由运行时 duck-typing 保证——一个 table 只要有 `update` 字段且可调用，它就是有效的状态。
2. **拥抱 table 作为通用数据结构**。在 C++ 中，转移规则是一个 `std::unordered_map<std::pair<State, Event>, Transition>`。在 Lua 中，它是一个嵌套 table——可读性更好，修改更方便。
3. **善用闭包**。Lua 的闭包可以捕获外部变量，这是实现状态私有数据的自然方式。不需要在类里声明私有成员——闭包捕获的变量天然私有。
4. **考虑协程**。如果你的状态内部有显式的"阶段序列"，协程可以消除显式的阶段跟踪变量。但在游戏循环中混用协程需要理解 yield 的调度机制——我们将在示例 C 中详细讨论。

---

## 2. 代码示例

### 示例 A：简单 table-based FSM

这是最直接、最符合 Lua 习惯的 FSM 实现。每个状态是一个 table，状态机本身也是一个 table。适合敌人 AI、简单 NPC 行为等场景。

```lua
-- ============================================================
-- 敌人 AI: 巡逻 → 追击 → 攻击 → 死亡
-- Table-based FSM — 最简实现，无元表、无类
-- ============================================================

local EnemyFSM = {}

function EnemyFSM.new(enemy)
    local fsm = {
        enemy = enemy,          -- 持有对敌人实体的引用
        current_state = nil,    -- 当前状态名 (string)
        state_table = {},       -- 当前状态 table 的引用 (缓存)
    }
    setmetatable(fsm, { __index = EnemyFSM })
    return fsm
end

-- 设置初始状态
function EnemyFSM:setInitialState(state_name, states)
    self.state_table = states[state_name]
    self.current_state = state_name
    if self.state_table.enter then
        self.state_table.enter(self, self.enemy)
    end
end

-- 每帧调用
function EnemyFSM:update(dt)
    if not self.state_table then return end

    -- 步骤 1: 评估转移 (事件检测本身也在转移规则中)
    local new_state = self:evaluateTransitions()
    if new_state then
        self:transitionTo(new_state)
    end

    -- 步骤 2: 执行当前状态的 update
    if self.state_table.update then
        self.state_table.update(self, self.enemy, dt)
    end
end

function EnemyFSM:evaluateTransitions()
    local transitions = self.state_table.transitions
    if not transitions then return nil end

    for event_name, rule in pairs(transitions) do
        -- rule = { check = function, target = "StateName" }
        if rule.check and rule.check(self.enemy) then
            return rule.target
        end
    end
    return nil
end

function EnemyFSM:transitionTo(target_state_name, all_states)
    -- Exit 旧状态
    if self.state_table and self.state_table.exit then
        self.state_table.exit(self, self.enemy)
    end

    -- Switch
    local new_state = all_states[target_state_name]
    if not new_state then
        error("Unknown state: " .. tostring(target_state_name))
    end

    self.state_table = new_state
    self.current_state = target_state_name

    -- Enter 新状态
    if self.state_table.enter then
        self.state_table.enter(self, self.enemy)
    end
end

-- ============================================================
-- 状态定义 — 每个状态是独立的 table
-- ============================================================

local States = {}

-- ---- Patrol 状态 ----
States.Patrol = {
    enter = function(fsm, enemy)
        enemy.speed = enemy.patrol_speed
        enemy.current_waypoint = 1
        print(enemy.name .. ": 开始巡逻")
    end,

    update = function(fsm, enemy, dt)
        -- 移动到当前路径点
        local wp = enemy.waypoints[enemy.current_waypoint]
        local dx, dy = wp.x - enemy.x, wp.y - enemy.y
        local dist = math.sqrt(dx * dx + dy * dy)

        if dist < 5 then
            -- 到达路径点，切换到下一个
            enemy.current_waypoint = enemy.current_waypoint % #enemy.waypoints + 1
        else
            local norm = math.sqrt(dx * dx + dy * dy)
            enemy.x = enemy.x + (dx / norm) * enemy.speed * dt
            enemy.y = enemy.y + (dy / norm) * enemy.speed * dt
        end
    end,

    exit = function(fsm, enemy)
        print(enemy.name .. ": 停止巡逻")
    end,

    transitions = {
        player_detected = {
            check = function(enemy)
                local dx = enemy.x - enemy.player.x
                local dy = enemy.y - enemy.player.y
                return (dx * dx + dy * dy) < (enemy.detect_range * enemy.detect_range)
            end,
            target = "Chase",
        },
        health_zero = {
            check = function(enemy) return enemy.health <= 0 end,
            target = "Dead",
        },
    },
}

-- ---- Chase 状态 ----
States.Chase = {
    enter = function(fsm, enemy)
        enemy.speed = enemy.chase_speed
        print(enemy.name .. ": 发现玩家！")
    end,

    update = function(fsm, enemy, dt)
        local dx = enemy.player.x - enemy.x
        local dy = enemy.player.y - enemy.y
        local norm = math.sqrt(dx * dx + dy * dy)
        if norm > 1 then
            enemy.x = enemy.x + (dx / norm) * enemy.speed * dt
            enemy.y = enemy.y + (dy / norm) * enemy.speed * dt
        end
    end,

    transitions = {
        in_attack_range = {
            check = function(enemy)
                local dx = enemy.x - enemy.player.x
                local dy = enemy.y - enemy.player.y
                return (dx * dx + dy * dy) < (enemy.attack_range * enemy.attack_range)
            end,
            target = "Attack",
        },
        player_lost = {
            check = function(enemy)
                local dx = enemy.x - enemy.player.x
                local dy = enemy.y - enemy.player.y
                return (dx * dx + dy * dy) > (enemy.lose_range * enemy.lose_range)
            end,
            target = "Patrol",
        },
        health_zero = {
            check = function(enemy) return enemy.health <= 0 end,
            target = "Dead",
        },
    },
}

-- ---- Attack 状态 ----
States.Attack = {
    enter = function(fsm, enemy)
        enemy.speed = 0
        enemy.attack_cooldown = 0
        print(enemy.name .. ": 进入攻击范围！")
    end,

    update = function(fsm, enemy, dt)
        enemy.attack_cooldown = enemy.attack_cooldown - dt
        if enemy.attack_cooldown <= 0 then
            -- 执行攻击
            enemy.player.health = enemy.player.health - enemy.damage
            print(enemy.name .. " 造成 " .. enemy.damage .. " 点伤害！")
            enemy.attack_cooldown = enemy.attack_interval
        end
    end,

    exit = function(fsm, enemy)
        print(enemy.name .. ": 停止攻击")
    end,

    transitions = {
        out_of_attack_range = {
            check = function(enemy)
                local dx = enemy.x - enemy.player.x
                local dy = enemy.y - enemy.player.y
                return (dx * dx + dy * dy) > (enemy.attack_range * enemy.attack_range * 1.5)
            end,
            target = "Chase",
        },
        health_zero = {
            check = function(enemy) return enemy.health <= 0 end,
            target = "Dead",
        },
    },
}

-- ---- Dead 状态 (吸收态) ----
States.Dead = {
    enter = function(fsm, enemy)
        enemy.speed = 0
        enemy.collider = nil
        print(enemy.name .. ": 被击败！")
    end,

    update = function(fsm, enemy, dt)
        -- 死亡状态不做任何事
    end,

    -- Dead 状态没有 transitions —— 它是吸收态，不会再转移出去
}

-- ============================================================
-- 使用示例
-- ============================================================

-- 模拟一个敌人实体
local enemy = {
    name = "哥布林",
    x = 0, y = 0,
    health = 30,
    patrol_speed = 50, chase_speed = 120,
    detect_range = 200, lose_range = 400,
    attack_range = 40, attack_interval = 1.5, damage = 8,
    waypoints = { { x = 100, y = 0 }, { x = 100, y = 100 }, { x = 0, y = 100 } },
    current_waypoint = 1,
    player = { x = 150, y = 0, health = 100 },
}

-- 初始化并运行
local fsm = EnemyFSM.new(enemy)
fsm:setInitialState("Patrol", States)

-- 模拟游戏循环
for i = 1, 30 do
    print("--- Frame " .. i .. " | 当前状态: " .. fsm.current_state .. " ---")
    fsm:update(0.016)  -- ~60fps
end
```

**关键设计决策**：

- **转移规则放在状态 table 内部**。每个状态自己声明"我可能转移到哪些状态"。这比把转移规则集中在一个地方更内聚——修改 `Patrol` 的行为时，你只需要修改 `Patrol` table，不需要在另一个转移路由器里找对应的 case。
- **transitionTo 需要 all_states 参数**。这里有一个 API 设计折中：`transitionTo` 接收 `all_states` 参数而不是闭包捕获 `States` 全局变量。实际工程中，你可能希望把状态表传递给 FSM 构造函数，避免全局变量——但为了示例的可读性，这里保持简单。
- **转移优先级由 pairs 的迭代顺序决定**。这是这种实现的一个**已知缺陷**：Lua 的 `pairs` 不保证遍历顺序，所以同名状态下多个同时匹配的转移规则的结果是不确定的。如果你需要确定的优先级，应该用带 `priority` 字段的数组并排序遍历（参见 Tutorial 01 中转移表的讨论）。

### 示例 B：OOP 风格 FSM（基于元表）

当你需要跨多个敌人类型共享 FSM 行为、或者项目中已有面向对象的约定时，可以用 Lua 的元表模拟类继承。这种实现更接近 C++/C# 的状态模式，但保留了 Lua 的动态灵活性。

```lua
-- ============================================================
-- OOP 风格 FSM: State 基类 + StateMachine 管理器
-- 利用 metatable 实现继承和方法分发
-- ============================================================

-- ---- State 基类 ----
-- 使用 metatable 的 __index 提供默认实现（什么都不做的空方法）
local State = {}
State.__index = State

function State:new(name)
    local instance = {
        name = name or "Unknown",
    }
    setmetatable(instance, self)
    return instance
end

-- 默认方法 — 子类可以选择性覆盖
function State:enter(entity) end
function State:exit(entity) end
function State:update(entity, dt) end
function State:handleEvent(entity, event) return nil end  -- 返回新状态名或 nil

-- ---- StateMachine 类 ----
local StateMachine = {}
StateMachine.__index = StateMachine

function StateMachine:new(entity)
    local instance = {
        entity = entity,
        current_state = nil,
        states = {},        -- { name = State_instance }
        previous_state = nil,
    }
    setmetatable(instance, self)
    return instance
end

function StateMachine:addState(state)
    self.states[state.name] = state
    return self  -- 支持链式调用
end

function StateMachine:setState(state_name)
    if self.current_state and self.current_state.name == state_name then
        return  -- 相同状态，不重复进入
    end

    -- Exit 旧状态
    if self.current_state then
        self.current_state:exit(self.entity)
    end

    -- Switch
    self.previous_state = self.current_state
    self.current_state = self.states[state_name]

    if not self.current_state then
        error("StateMachine: unknown state '" .. tostring(state_name) .. "'")
    end

    -- Enter 新状态
    self.current_state:enter(self.entity)
end

function StateMachine:update(dt)
    if not self.current_state then return end

    -- 先执行状态内部逻辑
    self.current_state:update(self.entity, dt)

    -- 再评估转移 — 由状态自身的 handleEvent 返回新状态
    local new_state = self.current_state:handleEvent(self.entity)
    if new_state then
        self:setState(new_state)
    end
end

function StateMachine:sendEvent(event, ...)
    if not self.current_state then return end
    local new_state = self.current_state:handleEvent(self.entity, event, ...)
    if new_state then
        self:setState(new_state)
    end
end

-- ---- 具体状态类：使用 metatable 继承 State ----

local PatrolState = State:new("Patrol")

-- 覆盖 enter
function PatrolState:enter(entity)
    entity.speed = entity.patrol_speed
    print(entity.name .. ": 进入巡逻 | 速度=" .. entity.speed)
end

-- 覆盖 update
function PatrolState:update(entity, dt)
    local wp = entity.waypoints[entity.wp_index]
    local dx, dy = wp.x - entity.x, wp.y - entity.y
    local dist = math.sqrt(dx * dx + dy * dy)
    if dist < 5 then
        entity.wp_index = entity.wp_index % #entity.waypoints + 1
    else
        local n = math.sqrt(dx * dx + dy * dy)
        entity.x = entity.x + (dx / n) * entity.speed * dt
        entity.y = entity.y + (dy / n) * entity.speed * dt
    end
end

-- 覆盖 handleEvent — 基于事件名称驱动转移
function PatrolState:handleEvent(entity)
    local dx = entity.x - entity.player.x
    local dy = entity.y - entity.player.y
    local sq_dist = dx * dx + dy * dy

    if entity.health <= 0 then return "Dead" end
    if sq_dist < entity.detect_range * entity.detect_range then return "Chase" end
    return nil  -- 保持当前状态
end

-- ---- ChaseState ----
local ChaseState = State:new("Chase")

function ChaseState:enter(entity)
    entity.speed = entity.chase_speed
    print(entity.name .. ": 玩家进入视野，开始追击！")
end

function ChaseState:update(entity, dt)
    local dx = entity.player.x - entity.x
    local dy = entity.player.y - entity.y
    local n = math.sqrt(dx * dx + dy * dy)
    if n > 1 then
        entity.x = entity.x + (dx / n) * entity.speed * dt
        entity.y = entity.y + (dy / n) * entity.speed * dt
    end
end

function ChaseState:handleEvent(entity)
    local dx = entity.x - entity.player.x
    local dy = entity.y - entity.player.y
    local sq_dist = dx * dx + dy * dy

    if entity.health <= 0 then return "Dead" end
    if sq_dist < entity.attack_range * entity.attack_range then return "Attack" end
    if sq_dist > entity.lose_range * entity.lose_range then return "Patrol" end
    return nil
end

-- ---- AttackState ----
local AttackState = State:new("Attack")

function AttackState:enter(entity)
    entity.speed = 0
    entity.attack_cooldown = 0
    print(entity.name .. ": 进入攻击范围！")
end

function AttackState:update(entity, dt)
    entity.attack_cooldown = entity.attack_cooldown - dt
    if entity.attack_cooldown <= 0 then
        entity.player.health = entity.player.health - entity.damage
        print(entity.name .. " 造成 " .. entity.damage .. " 点伤害！ 玩家HP: " .. entity.player.health)
        entity.attack_cooldown = entity.attack_interval
    end
end

function AttackState:handleEvent(entity)
    local dx = entity.x - entity.player.x
    local dy = entity.y - entity.player.y
    local sq_dist = dx * dx + dy * dy

    if entity.health <= 0 then return "Dead" end
    if sq_dist > entity.attack_range * entity.attack_range * 1.5 then return "Chase" end
    return nil
end

-- ---- DeadState (吸收态) ----
local DeadState = State:new("Dead")

function DeadState:enter(entity)
    entity.speed = 0
    entity.collider = nil
    print(entity.name .. ": 死亡！")
end

function DeadState:handleEvent(entity)
    return nil  -- 吸收态：永远不转移
end

-- ============================================================
-- 使用
-- ============================================================

local entity = {
    name = "兽人战士",
    x = 0, y = 0, health = 50,
    patrol_speed = 40, chase_speed = 100,
    detect_range = 150, lose_range = 300, attack_range = 35,
    attack_interval = 2.0, damage = 12,
    waypoints = { { x = 80, y = 0 }, { x = 80, y = 80 }, { x = 0, y = 80 } },
    wp_index = 1,
    player = { x = 100, y = 0, health = 100 },
}

local sm = StateMachine:new(entity)
    :addState(PatrolState)
    :addState(ChaseState)
    :addState(AttackState)
    :addState(DeadState)

sm:setState("Patrol")

-- 模拟帧循环
for i = 1, 25 do
    print(string.format("[Frame %2d | %s]", i, sm.current_state.name))
    sm:update(0.016)
end
```

**与示例 A 的对比**：

| 维度 | 示例 A (table-based) | 示例 B (OOP metatable) |
|------|----------------------|------------------------|
| 代码量 | 更少 | 略多（需要 State 基类） |
| 学习成本 | 低——理解 table 即可 | 需要理解 metatable 和 `__index` |
| 扩展新状态 | 添加一个 table | 调用 `State:new()` 并覆盖方法 |
| 类型安全 | 无——全凭运行时 duck-typing | 无——但 metatable 提供了"回退到默认方法"的安全网 |
| 内存效率 | 每个状态一个裸 table | 每个状态实例有自己的 metatable 链 |
| 适合场景 | 单一敌人类型的简单 AI | 多敌人类型共享基础状态，需要方法继承 |

### 示例 C：协程式 FSM

协程（coroutine）是 Lua 最强大的特性之一，但它也是最容易被误用的。在 FSM 的语境下，协程的核心价值在于：**将状态内部的顺序逻辑用直观的"写到底"方式表达，而非用分散的 update 调用和状态变量管理。**

```lua
-- ============================================================
-- 协程式 FSM: 每个状态是一个协程函数
-- 适合: 对话序列、Boss 阶段、过场动画等顺序逻辑密集的场景
-- ============================================================

local CoroutineFSM = {}
CoroutineFSM.__index = CoroutineFSM

function CoroutineFSM.new(entity)
    local fsm = {
        entity = entity,
        states = {},               -- { name = coroutine_function }
        current_state_name = nil,
        current_coroutine = nil,   -- 当前运行中的协程
        dt = 0,                    -- 最近一次 dt，供 yield 后使用
    }
    setmetatable(fsm, self)
    return fsm
end

function CoroutineFSM:registerState(name, state_func)
    self.states[name] = state_func
    return self
end

function CoroutineFSM:startState(name)
    local state_func = self.states[name]
    if not state_func then
        error("Unknown state: " .. tostring(name))
    end

    -- 创建协程：把 fsm 和 entity 作为参数传给状态函数
    self.current_coroutine = coroutine.create(state_func)
    self.current_state_name = name

    -- 首次 resume：启动协程，传入 fsm 和 entity
    local ok, err = coroutine.resume(self.current_coroutine, self, self.entity)
    if not ok then
        error("Coroutine state '" .. name .. "' failed to start: " .. tostring(err))
    end
end

function CoroutineFSM:update(dt)
    self.dt = dt
    if not self.current_coroutine then return end

    -- 检查协程状态
    local status = coroutine.status(self.current_coroutine)
    if status == "dead" then
        self.current_coroutine = nil
        self.current_state_name = nil
        return
    end

    -- resume 协程：协程从上次 yield 的位置继续执行
    local ok, result = coroutine.resume(self.current_coroutine)
    if not ok then
        error("Coroutine state '" .. self.current_state_name .. "' error: " .. tostring(result))
    end

    -- result 可能是 "TRANSITION:NewState" 格式的转移指令
    if type(result) == "string" and result:match("^TRANSITION:") then
        local target = result:match("^TRANSITION:(.+)$")
        self:startState(target)
    end
end

-- ---- 协程辅助函数 ----
-- 在状态函数内调用这些辅助函数来与引擎交互

-- yield() — 等一帧后继续
function CoroutineFSM:yield()
    coroutine.yield()
end

-- wait(seconds) — 等待指定秒数
function CoroutineFSM:wait(seconds)
    local elapsed = 0
    while elapsed < seconds do
        elapsed = elapsed + self.dt
        coroutine.yield()
    end
end

-- waitUntil(condition_fn) — 等待条件满足
function CoroutineFSM:waitUntil(condition_fn)
    while not condition_fn(self.entity) do
        coroutine.yield()
    end
end

-- transitionTo(name) — 切换到另一个状态（包装 yield 返回值）
function CoroutineFSM:transitionTo(name)
    coroutine.yield("TRANSITION:" .. name)
end

-- ============================================================
-- 示例: Boss 战阶段序列
-- 三个阶段，每个阶段的逻辑是顺序的，用协程表达极其自然
-- ============================================================

local function boss_phase_one(fsm, boss)
    print("[Boss] 阶段一: 远程攻击")

    for i = 1, 5 do
        print("  Boss 发射火球 #" .. i)
        launch_fireball(boss)
        fsm:wait(1.5)  -- 每 1.5 秒发射一次
    end

    print("[Boss] 阶段一结束，进入阶段二...")
    fsm:yield()  -- 过渡帧
    fsm:transitionTo("PhaseTwo")
end

local function boss_phase_two(fsm, boss)
    print("[Boss] 阶段二: 近战冲锋")

    boss.phase_two_hp = boss.health * 0.5  -- 阶段二的血量阈值

    while boss.health > boss.phase_two_hp do
        print("  Boss 冲锋！")
        charge_attack(boss)

        -- 冲锋之间有冷却时间 + 随机间隔，增加不可预测感
        local cooldown = 2.0 + math.random() * 1.5
        fsm:wait(cooldown)
    end

    print("[Boss] 阶段二血量低于 50%，进入愤怒阶段！")
    fsm:wait(1.0)  -- 过渡动画
    fsm:transitionTo("PhaseThree")
end

local function boss_phase_three(fsm, boss)
    print("[Boss] 阶段三: 狂暴模式！")
    boss.attack_multiplier = 2.0
    boss.speed_multiplier = 1.5

    while boss.health > 0 do
        -- 随机选择攻击方式
        local attack_roll = math.random()

        if attack_roll < 0.4 then
            print("  Boss 使用毁灭连击！")
            devastating_combo(boss)
            fsm:wait(1.0)
        elseif attack_roll < 0.7 then
            print("  Boss 召唤陨石！")
            summon_meteor(boss)
            fsm:wait(2.5)
        else
            print("  Boss 冲锋 + 横扫！")
            charge_attack(boss)
            fsm:wait(0.3)
            sweep_attack(boss)
            fsm:wait(1.5)
        end
    end

    print("[Boss] 被击败！")
    fsm:transitionTo("Death")
end

local function boss_death(fsm, boss)
    print("[Boss] 死亡动画...")
    boss.is_dying = true
    fsm:wait(3.0)  -- 死亡动画播放 3 秒
    print("[Boss] 掉落战利品！")
    fsm:yield()    -- 协程结束，FSM 检测到 "dead" 状态后停止
end

-- 辅助函数（stub）
function launch_fireball(boss) end
function charge_attack(boss) end
function devastating_combo(boss) end
function summon_meteor(boss) end
function sweep_attack(boss) end

-- ============================================================
-- 示例: 对话系统 — 协程的天然适用场景
-- ============================================================

local function dialogue_sequence(fsm, entity)
    -- 对话是本质上的顺序逻辑：A 说 → B 说 → 选项 → 分支 → 结束
    -- 用传统 FSM 你需要 Managing/Speaking/Waiting/Choosing/End 五个状态
    -- 用协程，它就是一个函数：

    fsm:dialogue_say("NPC", "你好，冒险者。")
    fsm:wait(2.0)

    fsm:dialogue_say("NPC", "我需要你帮我找一件失落的遗物。")
    fsm:wait(2.5)

    fsm:dialogue_say("NPC", "它在北方的古老神殿里...")
    fsm:wait(2.0)

    -- 呈现选项并等待玩家选择
    local choice = fsm:dialogue_show_choices({
        "好的，我会帮你。",
        "我还要考虑一下。",
        "我拒绝。",
    })

    if choice == 1 then
        fsm:dialogue_say("Player", "好的，我会帮你。")
        fsm:wait(1.5)
        fsm:dialogue_say("NPC", "谢谢你！这是通往神殿的地图。")
        fsm:wait(2.0)
        give_item(entity, "ancient_map")
    elseif choice == 2 then
        fsm:dialogue_say("Player", "我还要考虑一下。")
        fsm:wait(1.5)
        fsm:dialogue_say("NPC", "当然，你可以随时回来找我。")
        fsm:wait(2.0)
    else
        fsm:dialogue_say("Player", "我拒绝。")
        fsm:wait(1.5)
        fsm:dialogue_say("NPC", "...好吧，我理解。")
        fsm:wait(2.0)
    end

    print("[Dialogue] 对话结束")
    fsm:transitionTo("Idle")
end

-- 对话辅助方法
function CoroutineFSM:dialogue_say(speaker, text)
    print("[" .. speaker .. "]: " .. text)
    -- 在实际游戏中，这里会触发 UI 显示文本
end

function CoroutineFSM:dialogue_show_choices(choices)
    -- 在实际游戏中，这里会弹出选项 UI 并等待输入
    -- 这里模拟选择第一个选项
    print("[System] 选项: " .. table.concat(choices, " | "))
    coroutine.yield()  -- 等待玩家输入（这里简化为直接返回 1）
    return 1
end

-- ============================================================
-- 使用协程 FSM 驱动 Boss 战
-- ============================================================

local boss = {
    name = "火焰领主",
    health = 500,
    attack_multiplier = 1.0,
    speed_multiplier = 1.0,
}

local fsm = CoroutineFSM.new(boss)
    :registerState("PhaseOne", boss_phase_one)
    :registerState("PhaseTwo", boss_phase_two)
    :registerState("PhaseThree", boss_phase_three)
    :registerState("Death", boss_death)

fsm:startState("PhaseOne")

-- 模拟游戏循环
local frame = 0
while coroutine.status(fsm.current_coroutine) ~= "dead" and frame < 100 do
    frame = frame + 1
    fsm:update(0.016)
end
```

**协程式 FSM 的关键设计决策**：

1. **yield 返回值的语义**。协程的 `coroutine.yield(X)` 将 `X` 作为 `coroutine.resume()` 的返回值传给调度方。协程式 FSM 利用这个机制：普通的 `yield()` 意味着"等一帧继续"，带 `TRANSITION:` 前缀的 yield 返回值则被解释为状态切换指令。这是一种干净的控制流协议。

2. **辅助函数封装 yield**。直接写 `coroutine.yield()` 会暴露实现细节。封装成 `fsm:wait(seconds)`、`fsm:waitUntil(condition)`、`fsm:transitionTo(name)` 让状态函数读起来像顺序代码，而不是协程调度代码。

3. **协程的生命周期管理**。当状态函数正常返回（函数末尾）时，协程进入 "dead" 状态。FSM 的 `update()` 检测到 "dead" 后清理协程引用。如果状态想要转移到另一个协程状态，必须通过 `transitionTo` 而不是直接返回——因为直接返回会让调度方误以为整个 FSM 结束。

**协程式 FSM 的适用边界**：

- ✅ 对话序列、过场动画、教程引导——这些本质上是"等一段时间 → 做一件事 → 等另一件事"。
- ✅ Boss 的阶段序列——每个阶段内部也是顺序的。
- ✅ 任务脚本——"去 A 点 → 杀 3 个怪 → 收集 5 个物品 → 回 B 点交任务"。
- ❌ 高度响应式的实时 AI（如敌人战斗 AI）——协程在 `yield` 时无法立即响应新事件，除非在 `wait`/`waitUntil` 中加入中断逻辑，但这会破坏顺序代码的简洁性。
- ❌ 需要在任意时刻被中断的 AI——协程的中断需要额外的设计（yield 时不只接受 `nil`，还要检查中断标志）。

---

## 3. 练习

### 练习 1：用 table-based FSM 实现对话系统

**目标**：用示例 A 的 table-based 模式实现一个完整的对话系统 FSM，包含 `Idle` / `Talking` / `Choice` / `End` 四个状态。

**背景**：在 RPG 中，玩家靠近 NPC 并按交互键后触发对话。对话系统需要处理：NPC 说台词、等待玩家按键继续、呈现选项、根据选项分支、对话结束回到空闲状态。

**要求**：

1. 为每个状态定义 `enter` / `update` / `exit` / `transitions`。至少三个状态的 `enter` 中有可见的副作用（如打印台词、显示 UI）。

2. `transitions` 中的规则必须覆盖以下事件：
   - `interact_pressed`：玩家按交互键，Idle → Talking
   - `dialogue_advance`：当前台词播放完毕，Talking → Talking（自转移，切换到下一句）或 Talking → Choice（如果到达选项节点）
   - `choice_selected`：玩家选择了选项，Choice → Talking（继续对话）或 Choice → End（对话结束）
   - `dialogue_end`：对话自然结束，Talking/Choice → End
   - `dialogue_timeout`：任何状态下如果超过 30 秒无输入，End（可选实现）

3. 设计至少 5 句台词 + 1 个选项节点（3 个选项，选不同选项走不同后续台词）。

4. 在转移表中标注**哪些 `(state, event)` 组合没有被处理**，以及你判断它们是"不可能发生"还是"被遗漏了"。

**提示**：对话系统是 FSM 的经典应用。思考"当前说到第几句台词"应该存储在 FSM 的什么地方——它是状态的一部分（`Talking.line_index`）还是应该作为 FSM 之外的对话数据存在？

---

### 练习 2：将对话 FSM 转换为协程式，对比可读性

**目标**：将练习 1 中实现的对话系统用示例 C 的协程模式重写，然后对比两种实现的优劣。

**要求**：

1. 用协程式 FSM 实现完全相同的对话逻辑（至少 5 句台词 + 1 个选项节点）。利用 `fsm:wait()` 和 `fsm:dialogue_say()` 辅助函数。

2. 对比两种实现：

| 对比维度 | Table-based FSM | 协程式 FSM |
|----------|----------------|------------|
| 总代码行数 | | |
| 台词与流程的可视化程度 | | |
| 添加新对话节点的改动范围 | | |
| 中断正在进行的对话的难度 | | |
| 调试时追踪"当前在第几句"的难度 | | |
| 多人协作时合并冲突的概率 | | |

3. 写一段 100-200 字的分析：在什么条件下你会选择 table-based，什么条件下选择协程式？有没有第三种更好的选择（比如数据驱动——把对话完全定义成 JSON/CSV，FSM 只是播放器）？

---

### 练习 3（可选）：为 C++ 引擎设计 Lua FSM 接口

**目标**：模拟 AAA 工作室的典型架构——C++ 引擎运行核心循环，Lua 定义状态行为。设计一个 C++ ↔ Lua 的接口协议。

**背景**：你的自制引擎用 C++ 写游戏循环和实体系统。你希望设计师能用 Lua 脚本定义敌人的 FSM 行为，而不用重新编译 C++。C++ 侧负责：
- 每帧调用 Lua 侧的 update
- 将感知结果（检测到玩家、血量变化）作为事件传给 Lua
- 执行 Lua 侧请求的动作（移动、攻击、播放动画）

**要求**：

1. 用 Lua C API 或你熟悉的绑定库（Sol2、LuaBridge、tolua++）设计以下接口。写出 **接口声明** 和 **关键调用流程**，不需要完整的 C++ 编译代码：

```cpp
// C++ 侧接口 (声明级别即可)
class LuaStateMachine {
public:
    // 加载 Lua 脚本并初始化 FSM
    bool LoadScript(const char* path);

    // 设置当前状态
    void SetState(const char* state_name);

    // 每帧调用 — Lua 会调用 C++ 注册的 API 函数
    void Update(float dt);

    // 向 Lua 发送事件
    void SendEvent(const char* event_name);
};
```

2. 写出对应的 Lua 侧约定——状态 table 的接口规范（需要哪些字段、字段的类型和语义）。这份规范应该清晰到可以交给另一个工程师实现。

3. 设计至少两个 C++ 暴露给 Lua 的 API 函数（如 `MoveTo(x, y)` 和 `PlayAnimation(name)`），并说明 Lua 如何在状态的 `update` 中调用它们。

4. 分析：在这种混合架构下，FSM 的 **转移评估** 应该放在 C++ 侧还是 Lua 侧？为什么？考虑性能、热更新便利性和调试难度。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **对话 FSM 状态定义（table-based）：**
>
> ```lua
> local DialogueStates = {}
>
> -- ---- Idle: 等待玩家交互 ----
> DialogueStates.Idle = {
>     enter = function(fsm, npc)
>         print("[FSM] 进入 Idle — NPC 空闲中")
>         npc:show_prompt("按 E 交谈")
>     end,
>     update = function(fsm, npc, dt) end,
>     exit = function(fsm, npc)
>         npc:hide_prompt()
>     end,
>     transitions = {
>         interact_pressed = {
>             check = function(npc) return npc.input.interact end,
>             target = "Talking",
>         },
>         dialogue_timeout = {
>             check = function(npc) return npc.idle_timer > 30 end,
>             target = "End",
>         },
>     },
> }
>
> -- ---- Talking: NPC 正在说台词 ----
> DialogueStates.Talking = {
>     enter = function(fsm, npc)
>         print("[FSM] 进入 Talking")
>         fsm.data.line_index = 0          -- 对话进度存在 FSM 上
>         fsm.data.lines = npc:get_dialogue_lines()  -- 从 NPC 数据加载台词
>         fsm:advance_line(npc)            -- 显示第一句
>     end,
>     update = function(fsm, npc, dt)
>         fsm.data.type_timer = (fsm.data.type_timer or 0) + dt
>         -- 打字机效果省略...
>     end,
>     exit = function(fsm, npc)
>         npc:hide_dialogue_box()
>         print("[FSM] 退出 Talking")
>     end,
>     transitions = {
>         dialogue_advance = {
>             check = function(npc)
>                 return npc.input.confirm and fsm.data.text_complete
>             end,
>             target = function(fsm, npc)
>                 fsm.data.line_index = fsm.data.line_index + 1
>                 local next_line = fsm.data.lines[fsm.data.line_index]
>                 if next_line.type == "choice" then
>                     return "Choice"
>                 elseif next_line then
>                     fsm:advance_line(npc)
>                     return "Talking"  -- 自转移
>                 else
>                     return "End"
>                 end
>             end,
>         },
>         dialogue_timeout = {
>             check = function(npc) return npc.idle_timer > 30 end,
>             target = "End",
>         },
>     },
> }
>
> -- ---- Choice: 选项分支 ----
> DialogueStates.Choice = {
>     enter = function(fsm, npc)
>         print("[FSM] 进入 Choice — 显示选项")
>         local options = fsm.data.lines[fsm.data.line_index].options
>         npc:show_choices(options)  -- 副作用：显示 3 个选项的 UI
>     end,
>     update = function(fsm, npc, dt) end,
>     exit = function(fsm, npc)
>         npc:hide_choices()
>     end,
>     transitions = {
>         choice_selected = {
>             check = function(npc) return npc.input.choice_index > 0 end,
>             target = function(fsm, npc)
>                 local idx = npc.input.choice_index
>                 npc.input.choice_index = 0  -- 消费输入
>                 local choice = fsm.data.lines[fsm.data.line_index].options[idx]
>                 if choice.branch == "end" then
>                     return "End"
>                 else
>                     -- 跳转到选择对应的分支台词
>                     fsm.data.lines = choice.follow_up_lines
>                     fsm.data.line_index = 0
>                     fsm:advance_line(npc)
>                     return "Talking"
>                 end
>             end,
>         },
>         dialogue_timeout = {
>             check = function(npc) return npc.idle_timer > 30 end,
>             target = "End",
>         },
>     },
> }
>
> -- ---- End: 对话结束 ----
> DialogueStates.End = {
>     enter = function(fsm, npc)
>         print("[FSM] 对话结束")
>         npc:hide_all_ui()
>         npc:start_cooldown(3)  -- 3 秒后才能再次对话
>     end,
>     update = function(fsm, npc, dt) end,
>     exit = function(fsm, npc) end,
>     transitions = {
>         -- 冷却结束后自动回到 Idle
>         cooldown_done = {
>             check = function(npc) return npc.dialogue_cooldown <= 0 end,
>             target = "Idle",
>         },
>     },
> }
> ```
>
> **5 句台词 + 1 个选项节点示例数据：**
>
> ```lua
> npc.dialogue_lines = {
>     { type = "text", text = "冒险者，你终于来了。" },
>     { type = "text", text = "北方森林出现了怪物，村民们很不安。" },
>     { type = "choice", options = {
>         { text = "交给我吧", branch = "accept",
>           follow_up_lines = {
>               { type = "text", text = "感谢你！请消灭 5 只狼。" },
>               { type = "text", text = "回来我会给你报酬。" },
>           }},
>         { text = "报酬多少？", branch = "negotiate",
>           follow_up_lines = {
>               { type = "text", text = "200 金币，外加这把剑。" },
>           }},
>         { text = "没兴趣", branch = "end" },
>     }},
> }
> ```
>
> **未处理组合分析：**
>
> | 状态\事件 | interact_pressed | dialogue_advance | choice_selected | dialogue_end | dialogue_timeout |
> |-----------|:---:|:---:|:---:|:---:|:---:|
> | Idle | →Talking | 忽略(不可能) | 忽略(不可能) | 忽略(未在对话) | →End |
> | Talking | 忽略(已在对话) | →Talking/Choice/End | 忽略(无选项) | →End | →End |
> | Choice | 忽略(对话中) | 忽略(等待选择) | →Talking/End | →End | →End |
> | End | 忽略(冷却中) | 忽略(已结束) | 忽略(无 UI) | 忽略 | →Idle (cooldown_done) |
>
> 标记为"忽略"的组合中，大部分是"该状态下该事件不会发生"（如 Idle 状态下不会收到 choice_selected），部分是"该状态下事件无意义"（如 End 状态下的 interact）。只有 `Talking + choice_selected` 被标记为"忽略(无选项)"——如果你的实现中对话系统可能在打字机效果播放期间收到输入，这一步需要更细粒度的处理。

> [!tip]- 练习 2 参考答案
> **协程式对话 FSM 重写（核心函数）：**
>
> ```lua
> function DialogueFSM:dialogue_coroutine(npc)
>     -- Idle 状态等价：等待玩家交互
>     npc:show_prompt("按 E 交谈")
>     self:wait_until(function() return npc.input.interact end)
>
>     -- Talking 阶段：逐句播放台词
>     npc:hide_prompt()
>     for _, line in ipairs(npc.dialogue_lines) do
>         if line.type == "text" then
>             self:dialogue_say(npc, line.text)  -- 打字机效果 + 等待确认
>         elseif line.type == "choice" then
>             -- Choice 阶段
>             local choice = self:dialogue_choice(npc, line.options)
>             if choice.branch == "end" then
>                 goto dialogue_end
>             end
>             -- 继续走分支的后续台词...
>             for _, follow_line in ipairs(choice.follow_up_lines) do
>                 self:dialogue_say(npc, follow_line.text)
>             end
>         end
>     end
>
>     ::dialogue_end::
>     npc:hide_all_ui()
>     npc:start_cooldown(3)
>     self:wait_seconds(3)
>     -- 协程结束 → FSM 自然回到 Idle
> end
> ```
>
> **对比分析表：**
>
> | 对比维度 | Table-based FSM | 协程式 FSM |
> |----------|----------------|------------|
> | 总代码行数 | ~120 行（状态定义 + 转移规则 + FSM 框架） | ~40 行（一个 coroutine 函数） |
> | 台词与流程的可视化程度 | 低——台词分散在 `enter`/`transitions` 中，需要拼接才能看到完整流程 | 高——台词按顺序写在 coroutine 中，像读剧本一样从上到下 |
> | 添加新对话节点的改动范围 | 需要在 `transitions` 中添加新事件 + 修改状态 table | 在 coroutine 中插入几行 `self:dialogue_say()` 和 `self:wait_until()` |
> | 中断正在进行的对话的难度 | 容易——FSM 从任意状态可被外部事件转移（如被攻击 → Combat） | 困难——coroutine 必须是协作式的，外部中断需要 `coroutine.close()` 或检查标志位 |
> | 调试时追踪"当前在第几句"的难度 | 需要打日志看 `fsm.data.line_index` + `fsm.current_state` | 协程停在 `coroutine.yield()` 处，堆栈信息直接告诉你当前位置 |
> | 多人协作时合并冲突的概率 | 中——不同人修改不同状态的 `transitions` 可能冲突 | 低——整个对话在一个函数里，git merge 要么全接受要么全拒绝 |
>
> **选型分析（100-200 字）：**
>
> Table-based 适合**分支多、可能被打断**的场景：如果你需要"对话中 NPC 被攻击 → 强制切换到战斗状态"，table-based 的显式转移比协程的破坏性中断更安全可控。协程式适合**线性流程为主、很少被中断**的场景：过场对话、教程提示、Boss 转阶段台词——这些天然是按顺序执行的"剧本"，协程写法更接近设计文档的表达方式，减少认知翻译负担。第三种更优选择：**数据驱动**——将对话内容定义为 JSON/CSV（节点 ID、台词文本、选项分支、跳转目标），FSM 作为纯粹的解释器逐节点播放。这样策划可以在 Excel/对话编辑器中编写剧情，程序只维护 FSM 播放器。这是 AAA 对话系统的标准做法（如《巫师3》的叙事工具）。

> [!tip]- 练习 3 参考答案（可选）
> **C++ LuaStateMachine 接口声明（使用 Sol2）：**
>
> ```cpp
> // LuaStateMachine.h
> #include <sol/sol.hpp>
>
> class LuaStateMachine {
>     sol::state m_lua;
>     sol::table m_fsm;    // Lua 侧的 FSM table
>     sol::table m_states; // Lua 侧的状态定义表
>
> public:
>     bool LoadScript(const char* path) {
>         m_lua.open_libraries(sol::lib::base, sol::lib::math, sol::lib::table);
>         // 注册 C++ API 到 Lua
>         m_lua.set_function("MoveTo", [this](float x, float y) { /* ... */ });
>         m_lua.set_function("PlayAnimation", [this](const char* name) { /* ... */ });
>         m_lua.set_function("GetDistanceToPlayer", [this]() -> float { /* ... */ });
>
>         auto result = m_lua.safe_script_file(path);
>         if (!result.valid()) return false;
>
>         m_states = m_lua["States"];
>         m_fsm = m_lua["FSMFactory"](/* entity ref */);
>         m_fsm["setInitialState"](m_fsm, "Idle", m_states);
>         return true;
>     }
>
>     void Update(float dt) {
>         m_fsm["update"](m_fsm, dt);
>     }
>
>     void SendEvent(const char* event_name) {
>         m_fsm["onEvent"](m_fsm, event_name);
>     }
> };
> ```
>
> **Lua 侧状态 table 接口规范：**
>
> ```lua
> -- 状态 table 必须字段：
> -- {
> --   enter       = function(fsm, entity)     -- 可选。进入状态时调用一次
> --   update      = function(fsm, entity, dt) -- 可选。每帧调用
> --   exit        = function(fsm, entity)     -- 可选。离开状态时调用一次
> --   transitions = {                         -- 可选。转移规则表
> --     [event_name] = {
> --       check  = function(entity) → bool,   -- 必须。转移条件
> --       target = string,                    -- 必须。(状态名) 或 function(entity) → string
> --     },
> --   },
> -- }
> --
> -- entity 字段约定（由 C++ 在创建 FSM 时注入）：
> --   entity.health, entity.x, entity.y        -- C++ 同步的属性
> --   entity.player (table)                     -- 感知数据
> --   entity:MoveTo(x, y)                       -- 调用 C++ 注册的函数
> --   entity:PlayAnimation(name)
> -->
> -- 约束：
> --   - enter/update/exit 中禁止使用 coroutine（由 C++ 每帧驱动）
> --   - check 函数必须无副作用（纯读操作）
> --   - 转移 target 为函数时，可用于"条件分支转移"
> ```
>
> **C++ 暴露的 API 示例：**
>
> ```cpp
> m_lua.set_function("MoveTo", [](float x, float y) {
>     // 调用引擎的寻路系统，驱动实体移动。由 C++ 在物理帧中执行，返回后 Lua 继续。
> });
> m_lua.set_function("PlayAnimation", [](const char* name) {
>     // 通过动画系统播放命名动画。在 C++ 侧处理动画混合和事件。
> });
> ```
>
> 在 Lua 侧的状态 `update` 中：
> ```lua
> update = function(fsm, entity, dt)
>     if not entity.is_moving then
>         entity:MoveTo(entity.patrol_points[entity.waypoint_idx].x,
>                       entity.patrol_points[entity.waypoint_idx].y)
>     end
> end
> ```
>
> **转移评估应该放在哪一侧？**
>
> **推荐放在 Lua 侧。** 原因：
> 1. **热更新便利性**：转移规则是 AI 行为的核心——设计师最需要迭代的部分。放在 Lua 侧可以在不重新编译 C++ 的情况下调整条件阈值（如"检测范围从 10 米改成 15 米"）。
> 2. **性能可接受**：转移评估是条件检查（几个 float 比较 + 距离计算），Lua 执行这些操作的开销在每帧约 0.1-1μs，对于几百个 AI 实体是可接受的。真正的性能瓶颈（寻路、物理、渲染）在 C++ 侧。
> 3. **调试难度缓解**：Lua 侧转移逻辑可以用 `print` 或调试器快速查看，比 C++ 的重新编译+断点快一个数量级。
> 4. **但要注意**：转移评估中如果有重计算（如 LineTrace 视线检测），应通过 C++ 函数暴露给 Lua 调用，而非在 Lua 中纯脚本实现。Lua 只负责**决策逻辑**（if 条件判断和组合），C++ 负责**感知查询**。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

### Lua 状态机库

以下社区库提供了比本文示例更成熟的生产级实现。在研究之前建议先手写一两个简单 FSM 理解核心概念——然后这些库的价值会清晰得多。

| 库 | 特点 | 适用场景 |
|----|------|----------|
| [hump.gamestate](https://github.com/vrld/hump/blob/master/gamestate.lua) | LÖVE2D 生态中最流行的游戏状态管理库。提供 `switch`、`push`、`pop` 的状态栈操作，适合游戏整体状态（菜单、游戏中、暂停等）。单文件实现，~200 行代码，值得完整阅读。 | LÖVE2D 游戏；学习轻量 FSM 框架的源码设计 |
| [tick](https://github.com/bjornbytes/tick) | 一个通用 FSM 库，支持 `enter`/`exit`/`update` 回调、转移规则和嵌套状态。API 设计干净——`fsm:transition("Chase")` 即切换。 | 需要在多个项目间复用的通用 FSM；独立于游戏框架 |
| [30log](https://github.com/Yonaba/30log) | 极简 (~50 行) 的 OOP 框架，常与自定义 FSM 配合使用。如果你需要 class/instance 语义但不想引入完整框架，30log 是最小代价的选择。 | 需要轻量 OOP 但又不想手写 metatable 逻辑的项目 |

### LÖVE2D AI 资源

LÖVE2D 社区产生了大量 Lua AI 实战内容：

- [LÖVE2D Wiki — AI 相关页面](https://love2d.org/wiki/Category:AI)：包括寻路、转向行为和 FSM 的基础示例。
- [Bytepath](https://github.com/adnzzzzZ/blog/issues/30) 系列博客：一个用 LÖVE2D 从头构建完整游戏的教程，包含敌人 AI 的 FSM 实现。代码质量高，推荐阅读。
- [Simple FSM example in LÖVE](https://love2d.org/forums/viewtopic.php?t=83479)：社区论坛中的 FSM 讨论，展示了一个用 Lua 闭包实现状态机的紧凑方案。

### Roblox (Luau) AI 模式

Roblox 使用 Luau（Lua 的类型标注超集），其 AI 开发模式有独特特点：

- [Roblox AI Documentation](https://create.roblox.com/docs/scripting)：官方 AI 相关文档，包括 PathfindingService 和人形 NPC 行为。
- 社区模式：Roblox 开发者社区中常见两种 AI 范式：(a) **服务端 FSM**——在 `ServerScriptService` 中运行确定性 FSM 管理敌人生成、波次和 Boss 逻辑；(b) **客户端行为脚本**——在 `LocalScript` 中处理非关键的装饰性 AI（NPC 对话、表情动画）。在实际面试中，如果你能讨论客户端/服务端 AI 的划分原则，会显著加分。

### 深入 Lua 协程

协程式 FSM 的核心是 Lua 协程。以下资源深入协程的内部机制和游戏编程中的高级用法：

- [Programming in Lua (PiL) — Chapter 9: Coroutines](https://www.lua.org/pil/9.html)：Roberto Ierusalimschy 撰写的协程章节，权威详尽。
- [Lua Coroutines vs. Unity Coroutines](https://docs.unity3d.com/Manual/Coroutines.html)：如果你来自 Unity 背景，理解 Lua 协程和 Unity 协程的关键区别很重要。Lua 协程是一个语言级特性（栈保存/恢复是 C 层面的），而 Unity 协程是通过 C# 的 `IEnumerator` + 编译器状态机实现的，本质上是**在堆上分配的迭代器对象**。Lua 协程的栈切换开销极低，但跨 C 边界 yield 有额外成本——这是下面"常见陷阱"中会详细讨论的。

---

## 常见陷阱

### 1. Table 引用泄露

**症状**：你的 FSM 运行一段时间后内存持续增长；敌人被销毁但相关 table 没有被 GC；状态机切换时旧状态的数据仍然残留。

**根因**：Lua 的 table 是引用类型。如果你在状态的 `enter` 中保存了对敌人 table 的引用，但没有在 `exit` 中清除，或者多个状态之间通过闭包共享了一组可变 table，GC 无法回收。

```lua
-- ❌ 危险：闭包无意中捕获了 enemy 引用
function make_chase_state(master_enemy)
    return {
        update = function(self, current_enemy, dt)
            -- master_enemy 被闭包捕获，即使 master_enemy 已被销毁
            follow(master_enemy, current_enemy)
        end,
    }
end
```

**解法**：
- 所有状态的 `enter`/`update`/`exit` 只通过参数（`fsm`、`entity`、`dt`）访问数据，不通过闭包捕获外部变量。
- 在 `exit` 中显式清除状态持有的引用：`self.target = nil`。
- 在 FSM 销毁时调用 `OnStateExit` 并置空所有引用。

### 2. 协程栈溢出

**症状**：协程式 FSM 运行一段时间后抛出 `"C stack overflow"` 或栈溢出错误。

**根因**：最常见的错误是在协程函数内部**递归地**调用 `startState`：

```lua
-- ❌ 致命错误：状态函数内部调用 fsm:startState，导致无限递归
function chase_state(fsm, entity)
    while true do
        if condition_met(entity) then
            fsm:startState("Attack")  -- 在协程内部又创建了新协程
        end
        coroutine.yield()
    end
end
```

`startState` 创建了一个新协程并立即调用 `coroutine.resume`——如果这个调用发生在原协程的执行栈中，栈深度会持续增长。

**解法**：
- 永远不要在协程状态函数**内部**调用 `fsm:startState`。正确的转移方式是通过 `yield` 返回转移指令：`coroutine.yield("TRANSITION:Attack")`，由外层的 `update()` 解读并启动新状态。
- 区分"状态内部切换子阶段"（用 yield 等待）和"状态之间的转移"（用 yield 返回转移指令）。

### 3. 在 C 边界 yield

**症状**：协程在某些帧抛出 `"attempt to yield across metamethod/C-call boundary"` 错误。

**根因**：Lua 不允许在 C 函数的调用栈中执行 `yield`。如果你的 FSM 的 `update` 是从 C++ 引擎通过 Lua C API 调用的，而你在状态函数中尝试 yield，就会触发这个错误。

这在实际引擎中（如 Defold、自定义 C++ 引擎 + Sol2）是一个常见的坑。

**解法**：
- 使用 `lua_callk` / `lua_pcallk`（continuation-based API）代替普通的 `lua_call`。这允许 C 函数在 Lua yield 时"记住"自己的位置，等 resume 时继续执行 C 侧逻辑。
- 或者在 C++ 侧的 Update 完成后收集 Lua 侧生成的事件和转移指令，在下一帧处理——这本质上变成了**延迟执行**模型，牺牲了协程的实时性。

### 4. nil 状态处理

**症状**：FSM 在某些边界情况（如状态初始化失败、转移目标状态不存在）下，`current_state` 变成了 `nil`，导致后续所有帧都静默跳过。

**根因**：Lua 中 table 索引不存在的 key 返回 `nil`。如果转移目标拼写错误（`"Chase"` 写成了 `"Chsae"`），`states["Chsae"]` 返回 `nil`，FSM 进入一个"幽灵状态"——没有 update、没有 exit、也没有崩溃提示（除非你在 `setState` 中加了错误检查）。

**解法**：
- 在 `setState` 中添加断言：

```lua
function StateMachine:setState(name)
    local new_state = self.states[name]
    assert(new_state, "StateMachine: unknown state '" .. tostring(name) .. "'")
    -- ... 正常切换逻辑
end
```

- 在 `update` 中检查：

```lua
function StateMachine:update(dt)
    if not self.current_state then
        error("StateMachine: no active state — forgot to call setState()?")
    end
    -- ... 正常逻辑
end
```

- 使用字符串常量和枚举风格的表来避免拼写错误：

```lua
local STATE = {
    PATROL = "Patrol",
    CHASE  = "Chase",
    ATTACK = "Attack",
    DEAD   = "Dead",
}
-- 使用: setState(STATE.CHASE) — 拼写错误会得到 nil 并触发 assert
```

### 5. metatable 的 __index 隐式行为

**症状**：修改了"基类" State 的方法后，某个子状态没有按照预期变化；或者某个子状态"意外地"共享了基类方法，而你没有意识到。

**根因**：`__index` 元方法在属性查找失败时触发回退。如果你在实例上**赋值**了一个字段（`instance.update = my_func`），它会在实例自身 table 中创建键，**遮蔽**基类的同名键。但如果你在基类上赋值，所有通过 `__index` 回退的子实例都会受影响。这两种修改路径的不同行为容易混淆。

```lua
local BaseState = { update = function() print("base") end }
local SubState = setmetatable({}, { __index = BaseState })

SubState:update()       -- → "base" (从 __index 回退)
SubState.update = function() print("sub") end
SubState:update()       -- → "sub"  (遮蔽了基类)

BaseState.update = function() print("modified base") end
SubState:update()       -- → "sub"  (仍被遮蔽，不受基类修改影响)
```

**解法**：
- 在 FSM 初始化时显式地为每个状态复制所有需要的字段，**不要依赖运行时 `__index` 回退**。这在性能上也有好处（避免每次方法调用都走 metatable 查找链）。
- 或者坚持一个明确的纪律：永远不要在实例上增量定义方法——所有方法定义在创建实例时通过 `State:new()` 完成。

### 6. 协程式 FSM 的不可中断性

**症状**：Boss 正在执行协程式 FSM 的阶段一（`wait(60)` — 等待 60 秒的剧情对话），此时玩家将 Boss 的血量打到了 0。但 Boss 没有立即进入 Death 状态——它在等那 60 秒走完。

**根因**：协程式 FSM 的顺序代码假设了**没有高优先级中断**。`fsm:wait(60)` 在循环调用 `yield()`，不会检查外部条件变化。

**解法**：

- 将 `wait` 升级为可中断版本：

```lua
function CoroutineFSM:waitInterruptible(seconds, interrupt_check)
    local elapsed = 0
    while elapsed < seconds do
        if interrupt_check and interrupt_check(self.entity) then
            coroutine.yield("TRANSITION:Death")  -- 中断并切换到 Death
            return
        end
        elapsed = elapsed + self.dt
        coroutine.yield()
    end
end
```

- 或者**不要**把长等待写在协程的单一顺序块中。将"可能被中断"的行为拆成独立的协程状态，用 `transitionTo` 链接。

**法则**：如果状态内某个步骤可能因外部条件被跳过，它就不应该是一段顺序代码——它应该是一个单独的状态。
