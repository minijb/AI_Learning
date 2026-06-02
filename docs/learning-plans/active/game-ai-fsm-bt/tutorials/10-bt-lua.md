# 行为树在 Lua 中的实现

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 90min
> 前置知识: [06-bt-fundamentals](06-bt-fundamentals.md), [07-bt-node-types](07-bt-node-types.md)

---

## 1. 概念讲解

### 为什么用 Lua 实现行为树？

如果你已经用 C++（Tutorial 07-09）或 C#（Tutorial 08）实现过行为树引擎，你可能会对 Lua 版本产生疑问：Lua 不是更慢吗？没有类型检查不是更容易出错吗？

这些顾虑合理，但忽略了 Lua 在行为树领域独有的三个优势。

**第一，table 是最轻量的节点载体。** 在 C++ 中，一个 `BTSelector` 需要继承 `BTComposite`，后者继承 `BTNode`，加上虚函数表、动态分配和内存碎片。在 Lua 中，一个 Selector 节点就是一个 table——四个字段，无虚表，无继承链：

```lua
{ type = "selector", children = { ... }, run = function(agent) ... end }
```

当你需要为 200 个 NPC 各自实例化一棵行为树时，table 的零开销抽象意味着更少的 GC 压力和更快的创建速度。

**第二，闭包天然是 Action 和 Condition。** 行为树的叶子节点本质上就是"在特定时刻执行特定逻辑的函数"。在 C++ 中，你需要为每种行为写一个新类（`BTTask_Patrol`、`BTTask_Attack`、`BTTask_UseItem`……），类爆炸是真实存在的生产效率问题。在 Lua 中，行为就是闭包——三行代码定义一个叶子节点：

```lua
local patrol_action = function(agent)
    move_toward(agent, agent.next_waypoint)
    if arrived(agent) then return "success" else return "running" end
end
```

不需要声明类，不需要注册工厂，不需要写序列化宏。**代码即节点。**

**第三，热更新是行为树迭代的刚需。** 游戏 AI 的行为调整是高频操作——设计师说"Boss 第三阶段应该先放 AOE 再召唤小怪，而不是反过来"，修改发生在 Lua 脚本中，不需要重新编译引擎。在 C++ 中，重新链接可能耗时 5-30 分钟；在 Lua 中，`dofile` 或 `loadfile` 实现的运行时重载在几十毫秒内完成。这个速度差异直接决定了 AI 的迭代周期——你能在一天内调试 50 次行为逻辑，还是只能调试 3 次。

当然，Lua 不是银弹。对于需要极限性能的底层 BT 引擎（自 tick 调度、Blackboard 查询优化、节点池化），C++ 仍然是正确选择。Lua 在行为树中的最佳角色是**行为定义层**——树结构和叶子逻辑用 Lua 编写，引擎调度和基础设施用 C++ 提供。这也是 AAA 工作室的主流模式。

### Table-based vs Class-based：两种风格的权衡

Lua 实现行为树有两种主流风格，它们不是对错问题，而是**场景适配**问题。

#### Table-based 风格

Table-based 风格将节点建模为**纯数据 table + 外部函数**。节点本身不携带方法，树的 `tick` 逻辑由一套独立的引擎函数根据节点的 `type` 字段分发：

```lua
-- 树定义：纯数据
local patrol_tree = {
    type = "selector",
    children = {
        { type = "sequence", children = {
            { type = "condition", check = function(a) return a.health < 30 end },
            { type = "action", run = function(a) flee_from(a, a.player) end },
        }},
        { type = "action", run = function(a) patrol_waypoints(a) end },
    },
}
```

**优势**：
- **可序列化**。纯数据 table 可以直接用 JSON 或 Lua 自带的序列化方案持久化。你可以把行为树存成 `.json` 或 `.lua` 文件，运行时加载——数据驱动 AI 的基础。
- **可读性极高**。嵌套 table 字面量本身就是一棵树的文本表示。非程序员（设计师、策划）经过简单培训就能阅读和修改。
- **易于验证**。因为树结构是纯数据，你可以在不运行游戏的情况下做静态检查：是否存在循环引用？是否有孤儿节点？Composite 的子节点列表是否为空？
- **GC 友好**。节点 table 不携带方法引用，所有节点共享同一套引擎函数。200 个实例共享一套行为树时，只创建一份节点 table 并深拷贝。

**劣势**：类型分发在运行时通过字符串比较完成（`if node.type == "selector"`），比直接方法调用慢。对于深度嵌套的行为树，分发开销不可忽略——不过实践中，AI 系统的瓶颈极少在 tick 循环的分发上，通常在感知计算和路径规划。

#### Class-based 风格

Class-based 风格使用 metatable 模拟面向对象。每个节点类型有自己的"类"（实际上是一个原型 table + `__index`），节点实例通过 metatable 回退到原型方法：

```lua
local BTSelector = { children = {} }
BTSelector.__index = BTSelector

function BTSelector:new(children)
    return setmetatable({ children = children }, self)
end

function BTSelector:tick(agent)
    for _, child in ipairs(self.children) do
        local status = child:tick(agent)
        if status ~= "failure" then return status end
    end
    return "failure"
end
```

**优势**：
- **方法调用语义自然**。`child:tick(agent)` 比 `engine.tickNode(node, agent)` 更接近 C++/C# 程序员的直觉。
- **扩展容易**。通过 metatable 链可以构建 Decorator → Condition → Action 的继承层次，复用公共逻辑。
- **内省友好**。每个节点实例可以直接调用 `getmetatable(node)` 查看其类型链。这对于调试和可视化工具很有用。

**劣势**：每个节点实例的 metatable 链引入了额外的指针间接和内存开销。序列化也不如纯 table 方便——你需要处理函数引用和 metatable 的持久化问题。

**选择指南**：
- 如果你的行为树需要**序列化到磁盘、网络传输、或者由非程序员编辑**，选择 table-based 风格。
- 如果你在构建一个**完整的 BT 引擎**，需要 Decorator、Service、Parallel 等复杂节点类型，选择 class-based 风格——方法调用的多态性会减少大量 `if/elseif` 分支。
- 对于**快速原型和游戏 jam**，两种都可以——但 table-based 风格通常更快出活，因为它的样板代码为零。

### Lua 作为脚本层：AAA 的混合架构

在工业级游戏引擎（Unreal Engine、CryEngine、自研引擎）中，行为树的架构通常是这样的：

```
┌──────────────────────────────────────────┐
│          C++ BT Engine (核心层)           │
│  - Tick 调度 (每帧遍历活跃节点)            │
│  - Blackboard 存储与查询                  │
│  - 内存管理 (节点池、arena allocator)      │
│  - 可视化调试 (运行时树状态序列化)          │
│  - 并行执行与 Service 定时器               │
├──────────────────────────────────────────┤
│          Lua Bridge (桥接层)               │
│  - C++ BTNode 虚函数 → Lua 闭包映射        │
│  - Blackboard 值的跨语言读写               │
│  - Lua 状态隔离 (每个 AI agent 独立 lua_State) │
├──────────────────────────────────────────┤
│          Lua Scripts (行为定义层)           │
│  - 树结构定义 (table literal)               │
│  - 叶子节点逻辑 (Action/Condition 闭包)     │
│  - 运行时热重载                            │
└──────────────────────────────────────────┘
```

这种架构的核心思想是：**C++ 做它擅长的事（性能、内存管理、并发），Lua 做它擅长的事（灵活性、可热更、可读性）**。C++ 层的 `BTTask_LuaScript` 节点持有一个 Lua 函数引用（`luaL_ref`），在 `ExecuteTask` 被调用时，将该引用推入 Lua 栈并调用，将返回值映射回 `EBTNodeResult`。

一个 C++ 侧的关键设计是 **Blackboard 跨语言共享**。Blackboard 本身在 C++ 中实现（`TMap<FName, FBlackboardEntry>`），但通过 `userdata` 暴露给 Lua。Lua 侧通过 `__index` / `__newindex` 元方法拦截 table 访问，转发到 C++ 的 Blackboard API：

```lua
-- Lua 侧访问 Blackboard，实际调用 C++ 的 GetValue / SetValue
local target = bb.TargetActor     -- → C++ GetValue<AActor*>("TargetActor")
bb.AlertLevel = 3                 -- → C++ SetValue<int>("AlertLevel", 3)
```

这不是本教程的重点（详见 Tutorial 11: Blackboard 系统），但你应该知道这种模式的存在——它会在面试系统设计题中被问到。

### Tree Construction：Lua Table 字面量作为 DSL

Lua 的 table 字面量语法让行为树定义看起来几乎像一门 DSL。比较 C++ 和 Lua 的同一棵树：

**C++（Unreal 风格，蓝图或 C++ 构造）**：
```cpp
UBehaviorTree* Tree = NewObject<UBehaviorTree>();
UBTCompositeNode* Root = NewObject<UBTCompositeNode>(Tree, UBTSelectorNode::StaticClass());
UBTCompositeNode* Seq1  = NewObject<UBTCompositeNode>(Tree, UBTSequenceNode::StaticClass());
Seq1->Children.Add(NewObject<UBTTaskNode>(Tree, UBTTask_FindEnemy::StaticClass()));
Seq1->Children.Add(NewObject<UBTTaskNode>(Tree, UBTTask_MoveTo::StaticClass()));
Root->Children.Add(Seq1);
Root->Children.Add(NewObject<UBTTaskNode>(Tree, UBTTask_Patrol::StaticClass()));
Tree->RootNode = Root;
```

**Lua（table literal）**：
```lua
local tree = {
    type = "selector",
    children = {
        { type = "sequence", children = {
            { type = "action", run = find_enemy },
            { type = "action", run = move_to_target },
        }},
        { type = "action", run = patrol },
    },
}
```

差一个数量级的代码量，且 Lua 版本一眼可见树的结构——树形状直接由缩进反映。这种表达能力来自两个语言特性：

1. **Table 字面量可以嵌套**。不需要单独命名每个节点，不需要显式调用 `AddChild`。
2. **函数是一等值**。`find_enemy` 是一个变量引用——如果它指向一个闭包，捕获的变量在定义处就已经绑定好。

### Tick 集成：从游戏循环到行为树

行为树不会自己跑。它需要每帧被"tick"一次——从根节点开始，递归地在当前活跃路径上执行。Tick 的触发方式取决于你的架构：

| 触发方式 | 适用场景 | 关键考量 |
|---------|---------|---------|
| **C++ 主机每帧调用** | C++ 游戏循环，Lua 作为脚本层 | C++ 侧持有 `lua_State*`，每帧压入 tick 函数并 `lua_pcall`。需要管理跨帧的 Running 节点状态。 |
| **Lua 游戏循环** | LÖVE2D、Defold、纯 Lua 引擎 | 直接在 `love.update(dt)` 或 `update(dt)` 中调用 `behaviortree:tick(agent)`。最简单，没有跨语言开销。 |
| **事件驱动 Tick** | 带 Service/Decorator 的复杂 BT | 不是每帧 tick 整棵树，而是只 tick 自上一个 Running 节点起、沿树向下的活跃路径。减少不必要的条件重新评估。 |

**关键原则**：无论哪种触发方式，行为树的 tick 是**同步的**——一次 `tick()` 调用从根节点递归到叶子节点并返回，中间不会挂起（除非使用协程——但这引入了新的复杂度，见"常见陷阱"）。这意味着一次 tick 的执行时间必须严格控制在帧预算内（通常 <1ms）。如果你的 Action 需要执行耗时操作（如路径搜索），应该将其拆分为多帧——返回 `"running"` 并在下一帧继续。

---

## 2. 代码示例

### 示例 A：纯 Table-based BT 框架

这是最简约、最富 Lua 风格的行为树实现。核心思路：**节点是 table，引擎是函数**。树结构由嵌套 table 字面量定义，tick 逻辑由 `bt.run()` 根据 `type` 字段分发。

```lua
-- ============================================================
-- Table-based BT Engine — ~80 lines of pure Lua
-- ============================================================

local BT = {}

-- Main tick entry point
function BT.tick(node, agent, blackboard)
    local node_type = node.type
    if node_type == "selector" then
        return BT._tickSelector(node, agent, blackboard)
    elseif node_type == "sequence" then
        return BT._tickSequence(node, agent, blackboard)
    elseif node_type == "condition" then
        return BT._tickCondition(node, agent, blackboard)
    elseif node_type == "action" then
        return BT._tickAction(node, agent, blackboard)
    elseif node_type == "inverter" then
        return BT._tickInverter(node, agent, blackboard)
    else
        error("Unknown node type: " .. tostring(node_type))
    end
end

-- Selector: succeed on first child that doesn't fail
function BT._tickSelector(node, agent, bb)
    -- Resume from last running child (avoids re-evaluating earlier children)
    local start_index = node._last_running or 1
    for i = start_index, #node.children do
        local child = node.children[i]
        local status = BT.tick(child, agent, bb)
        if status == "running" then
            node._last_running = i
            return "running"
        elseif status == "success" then
            node._last_running = nil
            return "success"
        end
        -- failure → try next child
    end
    node._last_running = nil
    return "failure"
end

-- Sequence: fail on first child that doesn't succeed
function BT._tickSequence(node, agent, bb)
    local start_index = node._last_running or 1
    for i = start_index, #node.children do
        local child = node.children[i]
        local status = BT.tick(child, agent, bb)
        if status == "running" then
            node._last_running = i
            return "running"
        elseif status == "failure" then
            node._last_running = nil
            return "failure"
        end
        -- success → continue to next child
    end
    node._last_running = nil
    return "success"
end

-- Condition: delegate to the check function
function BT._tickCondition(node, agent, bb)
    if node.check(agent, bb) then
        return "success"
    else
        return "failure"
    end
end

-- Action: delegate to the run function, wrapping return values
function BT._tickAction(node, agent, bb)
    local result = node.run(agent, bb)
    -- run() can return a string directly, or true/false/nil
    if result == "success" or result == true then
        return "success"
    elseif result == "failure" or result == false then
        return "failure"
    elseif result == "running" then
        return "running"
    else
        -- nil or unrecognized → treat as success for convenience
        return "success"
    end
end

-- Inverter (Decorator): flip success↔failure, pass through running
function BT._tickInverter(node, agent, bb)
    local status = BT.tick(node.child, agent, bb)
    if status == "success" then return "failure"
    elseif status == "failure" then return "success"
    else return status end
end

-- Helper: reset _last_running state before a fresh tick
function BT.reset(node)
    node._last_running = nil
    if node.children then
        for _, child in ipairs(node.children) do
            BT.reset(child)
        end
    end
    if node.child then
        BT.reset(node.child)
    end
end

-- ============================================================
-- Tree definition: a patrol/flee behavior
-- ============================================================

local function distance(a, b)
    local dx, dy = a.x - b.x, a.y - b.y
    return math.sqrt(dx * dx + dy * dy)
end

local patrol_tree = {
    type = "selector",
    children = {
        -- Priority 1: flee if low health
        {
            type = "sequence",
            children = {
                {
                    type = "condition",
                    check = function(agent, bb)
                        return agent.health < 30
                    end,
                },
                {
                    type = "action",
                    run = function(agent, bb)
                        -- Move away from nearest enemy
                        local enemy = bb.nearest_enemy
                        if not enemy then return "failure" end
                        local dx = agent.x - enemy.x
                        local dy = agent.y - enemy.y
                        local dist = math.sqrt(dx * dx + dy * dy)
                        if dist < 5 then return "success" end  -- far enough
                        agent.x = agent.x + (dx / dist) * agent.speed * bb.dt
                        agent.y = agent.y + (dy / dist) * agent.speed * bb.dt
                        return "running"
                    end,
                },
            },
        },
        -- Priority 2: patrol waypoints (default behavior)
        {
            type = "action",
            run = function(agent, bb)
                local wp = agent.waypoints[agent.wp_index]
                if not wp then return "failure" end
                local d = distance(agent, wp)
                if d < 2 then
                    agent.wp_index = (agent.wp_index % #agent.waypoints) + 1
                    return "success"
                end
                agent.x = agent.x + (wp.x - agent.x) / d * agent.speed * bb.dt
                agent.y = agent.y + (wp.y - agent.y) / d * agent.speed * bb.dt
                return "running"
            end,
        },
    },
}

-- ============================================================
-- Usage (called every frame from the game loop)
-- ============================================================

--[[
    local agent = {
        x = 100, y = 100, speed = 50, health = 100,
        waypoints = {{x=100,y=100}, {x=300,y=100}, {x=300,y=300}},
        wp_index = 1,
    }
    local blackboard = { dt = 0.016, nearest_enemy = enemy }

    function love.update(dt)   -- LÖVE2D example
        blackboard.dt = dt
        blackboard.nearest_enemy = find_nearest_enemy(agent)
        local status = BT.tick(patrol_tree, agent, blackboard)
        -- status = "running" | "success" | "failure"
    end
]]
```

**关键设计决策**：

1. **`_last_running`**：Selector 和 Sequence 记住上次返回 `"running"` 的子节点索引。下次 tick 时从该索引继续，不重新评估之前的兄弟节点。这实现了标准行为树的"有状态 tick"——避免每帧都从第一个子节点重新开始，也防止了前面的 Condition 在"逃跑"过程中重新评估（如果 Selector 每次都从第一个子节点开始，"低血量"会被重复检查——虽然这里无害，但在更复杂的树中可能影响正确性）。

2. **`BT.reset()`**：当树从根节点重新开始时（上一次 tick 返回了 `"success"` 或 `"failure"`），需要清除所有节点的 `_last_running` 缓存。否则下次 tick 会从错误的位置继续。

3. **`blackboard` 作为显式参数**：不把 Blackboard 挂在 agent 上。分离两个概念——agent 是"这个 AI 控制谁"，blackboard 是"AI 当前知道什么"。这允许你在同一个 agent 上运行多棵树，每棵树的 blackboard 不同。

### 示例 B：Class-based BT 框架（Metatable 实现）

这套实现使用 metatable 模拟面向对象的继承体系，适合需要构建完整 BT 引擎（多节点类型、Decorator 链、Service 支持）的场景。

```lua
-- ============================================================
-- Class-based BT Framework using metatables
-- ============================================================

-- ---- Base Node ----
local BTNode = {}
BTNode.__index = BTNode

function BTNode:new()
    local node = { _last_running = nil }
    return setmetatable(node, self)
end

function BTNode:tick(agent, blackboard)
    error("BTNode:tick() must be overridden by subclass")
end

function BTNode:reset()
    self._last_running = nil
end

-- ---- Composite (base for Selector & Sequence) ----
local BTComposite = setmetatable({ children = {} }, { __index = BTNode })
BTComposite.__index = BTComposite

function BTComposite:new(children)
    local node = BTNode.new(self)
    node.children = children or {}
    return node
end

function BTComposite:reset()
    BTNode.reset(self)
    for _, child in ipairs(self.children) do
        child:reset()
    end
end

-- ---- Selector ----
local BTSelector = setmetatable({}, { __index = BTComposite })
BTSelector.__index = BTSelector

function BTSelector:tick(agent, bb)
    local start = self._last_running or 1
    for i = start, #self.children do
        local status = self.children[i]:tick(agent, bb)
        if status == "running" then
            self._last_running = i
            return "running"
        elseif status == "success" then
            self._last_running = nil
            return "success"
        end
    end
    self._last_running = nil
    return "failure"
end

-- ---- Sequence ----
local BTSequence = setmetatable({}, { __index = BTComposite })
BTSequence.__index = BTSequence

function BTSequence:tick(agent, bb)
    local start = self._last_running or 1
    for i = start, #self.children do
        local status = self.children[i]:tick(agent, bb)
        if status == "running" then
            self._last_running = i
            return "running"
        elseif status == "failure" then
            self._last_running = nil
            return "failure"
        end
    end
    self._last_running = nil
    return "success"
end

-- ---- Decorator (base for Condition, Inverter, etc.) ----
local BTDecorator = setmetatable({ child = nil }, { __index = BTNode })
BTDecorator.__index = BTDecorator

function BTDecorator:new(child)
    local node = BTNode.new(self)
    node.child = child
    return node
end

function BTDecorator:reset()
    BTNode.reset(self)
    if self.child then self.child:reset() end
end

-- ---- Action ----
local BTAction = setmetatable({}, { __index = BTNode })
BTAction.__index = BTAction

function BTAction:new(func)
    local node = BTNode.new(self)
    node.func = func
    return node
end

function BTAction:tick(agent, bb)
    local result = self.func(agent, bb)
    if result == "success" or result == true then return "success"
    elseif result == "failure" or result == false then return "failure"
    elseif result == "running" then return "running"
    else return "success" end
end

-- ---- Condition ----
local BTCondition = setmetatable({}, { __index = BTNode })
BTCondition.__index = BTCondition

function BTCondition:new(check)
    local node = BTNode.new(self)
    node.check = check
    return node
end

function BTCondition:tick(agent, bb)
    return self.check(agent, bb) and "success" or "failure"
end

-- ---- Inverter (Decorator) ----
local BTInverter = setmetatable({}, { __index = BTDecorator })
BTInverter.__index = BTInverter

function BTInverter:tick(agent, bb)
    local status = self.child:tick(agent, bb)
    if status == "success" then return "failure"
    elseif status == "failure" then return "success"
    end
    return status
end

-- ---- Behavior Tree (top-level wrapper) ----
local BTree = {}
BTree.__index = BTree

function BTree:new(root)
    return setmetatable({ root = root }, self)
end

function BTree:tick(agent, blackboard)
    return self.root:tick(agent, blackboard)
end

function BTree:reset()
    self.root:reset()
end

-- ============================================================
-- Tree construction using the class-based API
-- ============================================================

local enemy_tree = BTree:new(
    BTSelector:new({
        -- Flee sequence
        BTSequence:new({
            BTCondition:new(function(agent, bb)
                return agent.health < 30
            end),
            BTAction:new(function(agent, bb)
                local e = bb.nearest_enemy
                if not e then return "failure" end
                local dx, dy = agent.x - e.x, agent.y - e.y
                local dist = math.sqrt(dx * dx + dy * dy)
                if dist > 100 then return "success" end
                agent.x = agent.x + (dx / dist) * agent.speed * bb.dt
                agent.y = agent.y + (dy / dist) * agent.speed * bb.dt
                return "running"
            end),
        }),
        -- Attack sequence
        BTSequence:new({
            BTCondition:new(function(agent, bb)
                local e = bb.nearest_enemy
                return e and math.sqrt((agent.x-e.x)^2 + (agent.y-e.y)^2) < 10
            end),
            BTAction:new(function(agent, bb)
                bb.nearest_enemy.health = bb.nearest_enemy.health - 10
                return "success"
            end),
        }),
        -- Patrol (default)
        BTAction:new(function(agent, bb)
            local wp = agent.waypoints[agent.wp_index]
            if not wp then return "failure" end
            local d = math.sqrt((agent.x-wp.x)^2 + (agent.y-wp.y)^2)
            if d < 2 then
                agent.wp_index = (agent.wp_index % #agent.waypoints) + 1
                return "success"
            end
            agent.x = agent.x + (wp.x - agent.x) / d * agent.speed * bb.dt
            agent.y = agent.y + (wp.y - agent.y) / d * agent.speed * bb.dt
            return "running"
        end),
    })
)

-- Usage: enemy_tree:tick(agent, blackboard)  -- called every frame
```

**关键设计决策**：

1. **Metatable 继承链**：`BTSelector → BTComposite → BTNode`。每个级别通过 `setmetatable({}, { __index = Parent })` 实现原型继承。调用 `child:tick()` 时，Lua 先在实例 table 中查找 `tick`，找不到则沿 `__index` 链向上到 `BTSelector`，再到 `BTComposite`，最后到 `BTNode`。

2. **工厂方法 `:new()`**：每个类通过 `BTNode.new(self)` 创建实例——`self` 是调用 `new` 时冒号语法传入的原型 table。这确保了新实例的 metatable 指向正确的类原型，而非硬编码的 `BTNode`。如果写成 `setmetatable({}, BTNode)`，所有子类的实例都会指向 `BTNode`，失去类层次。

3. **`BTDecorator` 作为 Condition/Inverter 的基础**：Decorator 类维护单个 `child` 引用，提供 `reset()` 递归。这比直接继承 `BTNode` 更内聚——Condition 不需要关心"我有几个子节点"，由 Decorator 统一处理。

### 示例 C：完整 NPC AI——巡逻/游荡/逃跑

这个示例展示如何将示例 A 的 table-based 框架应用于一个真实 NPC，包含三个核心行为以及 Blackboard 的状态管理。

```lua
-- ============================================================
-- NPC AI: Patrol → Wander → Flee
-- Uses the table-based engine from Example A.
-- Blackboard is a plain Lua table shared across nodes.
-- ============================================================

-- ---- NPC factory ----
local function create_npc(x, y, waypoints)
    return {
        x = x, y = y,
        speed = 80,
        health = 100,
        max_health = 100,
        waypoints = waypoints,
        wp_index = 1,
        -- Wander state
        wander_target = nil,
        wander_timer = 0,
    }
end

-- ---- Helper functions ----
local function dist(a, b)
    return math.sqrt((a.x - b.x)^2 + (a.y - b.y)^2)
end

local function move_toward(agent, tx, ty, dt)
    local d = math.sqrt((tx - agent.x)^2 + (ty - agent.y)^2)
    if d < 1 then return true end  -- arrived
    agent.x = agent.x + (tx - agent.x) / d * agent.speed * dt
    agent.y = agent.y + (ty - agent.y) / d * agent.speed * dt
    return false
end

-- ---- NPC behavior tree ----
local npc_tree = {
    type = "selector",
    children = {
        -- Branch 1: Dead check (stop everything)
        {
            type = "sequence",
            children = {
                {
                    type = "condition",
                    check = function(agent, bb) return agent.health <= 0 end,
                },
                {
                    type = "action",
                    run = function(agent, bb)
                        -- Dead agent does nothing; tree returns success once
                        return "success"
                    end,
                },
            },
        },
        -- Branch 2: Flee when health low
        {
            type = "sequence",
            children = {
                {
                    type = "condition",
                    check = function(agent, bb)
                        return agent.health < agent.max_health * 0.3
                            and bb.nearest_threat ~= nil
                    end,
                },
                {
                    type = "action",
                    run = function(agent, bb)
                        local threat = bb.nearest_threat
                        local dx, dy = agent.x - threat.x, agent.y - threat.y
                        local d = math.sqrt(dx * dx + dy * dy)
                        -- Flee 150 units away from threat
                        local flee_x = agent.x + (dx / d) * 150
                        local flee_y = agent.y + (dy / d) * 150
                        local arrived = move_toward(agent, flee_x, flee_y, bb.dt)
                        if arrived then return "success" end
                        return "running"
                    end,
                },
            },
        },
        -- Branch 3: Patrol waypoints
        {
            type = "sequence",
            children = {
                {
                    type = "condition",
                    check = function(agent, bb)
                        return #agent.waypoints > 0
                    end,
                },
                {
                    type = "action",
                    run = function(agent, bb)
                        local wp = agent.waypoints[agent.wp_index]
                        local arrived = move_toward(agent, wp.x, wp.y, bb.dt)
                        if arrived then
                            agent.wp_index = (agent.wp_index % #agent.waypoints) + 1
                            return "success"
                        end
                        return "running"
                    end,
                },
            },
        },
        -- Branch 4: Wander randomly (fallback)
        {
            type = "action",
            run = function(agent, bb)
                -- Pick a random wander target every 2 seconds
                agent.wander_timer = agent.wander_timer - bb.dt
                if agent.wander_timer <= 0 or not agent.wander_target then
                    agent.wander_target = {
                        x = agent.x + math.random(-80, 80),
                        y = agent.y + math.random(-80, 80),
                    }
                    agent.wander_timer = 2.0
                end
                local t = agent.wander_target
                local arrived = move_toward(agent, t.x, t.y, bb.dt)
                if arrived then
                    agent.wander_timer = 0  -- force new target next tick
                    return "success"
                end
                return "running"
            end,
        },
    },
}

-- ============================================================
-- Simulation loop
-- ============================================================

local npc = create_npc(50, 50, {
    {x=100, y=50}, {x=200, y=150}, {x=100, y=250},
})

local blackboard = {
    dt = 0,
    nearest_threat = nil,
}

-- Simulate 60 frames
for frame = 1, 60 do
    blackboard.dt = 1/60
    -- Mock threat: appears at frame 30 at (150, 150)
    if frame >= 30 then
        blackboard.nearest_threat = { x = 150, y = 150 }
    else
        blackboard.nearest_threat = nil
    end
    local status = BT.tick(npc_tree, npc, blackboard)
    -- print(string.format("Frame %d: status=%s, pos=(%.0f,%.0f), hp=%d",
    --     frame, status, npc.x, npc.y, npc.health))
end
```

**设计要点**：

1. **Selector 优先级排序**：`Dead > Flee > Patrol > Wander`。高优先级行为放在 Selector 前面——Selector 按子节点顺序尝试，第一个不返回 `"failure"` 的获胜。

2. **`move_toward` 抽离为工具函数**：保持 Action 闭包短小。如果移动逻辑内联在每个 Action 中，代码会迅速膨胀。工具函数还提供了统一的"到达判定"语义——距离小于 1 时返回 `true`。

3. **Blackboard 作为状态共享层**：`nearest_threat` 由外部感知系统每帧写入 blackboard，行为树只读不写（除了 agent 自身状态）。这是标准做法——感知系统负责填充 blackboard，行为树负责基于 blackboard 做决策。

---

## 3. 练习

### 练习 1：守卫 AI 行为树

使用示例 A 的 table-based 引擎，构建一个守卫的行为树，满足以下需求：

- **巡逻 3 个路径点**：守卫按顺序在路径点 A → B → C → A 之间移动，到达每个路径点后停顿 1 秒。
- **调查噪音**：当 blackboard 中存在 `noise_position` 时（由外部感知系统设置），暂停巡逻，移动到噪音位置，到达后"观察"2 秒（停住不动），然后清除 `bb.noise_position` 并恢复巡逻。
- **低血量逃跑**：当 `health < 30%` 且 `nearest_threat` 存在时，向远离威胁的方向移动，直到距离 > 200 单位。

**验收标准**：
- 无威胁、无噪音时，守卫在 3 个路径点之间循环巡逻（含停顿）。
- 出现噪音时，守卫中断巡逻前往噪音位置，观察后恢复巡逻。
- 血量低于 30% 时，任何行为被逃跑覆盖——守卫不会继续巡逻或调查噪音。
- 用至少 90 帧的模拟来验证三个行为的优先级和切换逻辑。

### 练习 2：热更新支持

为示例 A 的 table-based 引擎添加热更新能力：

1. 将树定义从代码中抽取到一个独立的 `.lua` 文件（如 `guard_tree.lua`），该文件返回一个 tree table。
2. 实现 `load_tree(filepath)` 函数——用 `loadfile()` 加载树定义，捕获语法错误并打印。
3. 实现 `reload_tree(bt_engine, filepath)` 函数——重新加载树文件，替换 `bt_engine` 内部的 `root` 引用，同时保留 agent 和 blackboard 引用不变。
4. 在模拟循环中，按下某个虚拟按键（或每隔 N 帧）触发 `reload_tree`，验证新行为立即生效。

**提示**：`loadfile()` 返回一个函数，调用该函数获得 tree table。热更新期间 agent 状态（位置、血量）和 blackboard 内容应保持不变。

### 练习 3（可选）：设计 Lua-C++ 混合 BT 架构

不写代码，绘制架构图并回答以下问题：

- C++ 侧需要暴露哪些接口给 Lua？（至少列出 5 个）
- Blackboard 的跨语言访问如何实现？`userdata` + `__index`/`__newindex` 的方案有哪些边界情况需要处理？（提示：类型转换、生命周期、线程安全）
- 如果一棵行为树中有 80% 的节点在 C++ 中（性能关键路径），20% 在 Lua 中（设计师可修改），tick 循环应该如何设计以避免频繁的跨语言调用？
- 当 Lua 脚本中的 Action 返回 `"running"` 时，C++ 引擎需要维护什么状态？节点索引？还是 `lua_State` 的执行位置？

---

## 4. 扩展阅读

### LÖVE2D 行为树库

LÖVE2D 社区有几个开源的 Lua 行为树库，是学习工程化 BT 实现的优秀参考：

- **[hump.behaviortree](https://github.com/vrld/hump/blob/master/behaviortree.lua)**：hump 工具包的一部分，~150 行的极简实现。展示了如何在最少的代码中覆盖 Selector、Sequence、Decorator、Action。适合学习"BT 引擎的最小可行产品"是什么。
- **[lovetoys BehaviorTree](https://github.com/lovetoys/lovetoys)**：一个更完整的 ECS + BT 框架。重点看它如何将行为树节点注册为 ECS System，实现行为树与实体系统的无缝集成。
- **[behaviortree.lua](https://github.com/tanema/behaviortree.lua)**：独立的 Lua 行为树实现，支持 Decorator、Service 节点。代码风格清晰，注释完善，适合二次开发。

### World of Warcraft Lua AI 模式

WoW 的 UI 和部分脚本系统使用 Lua（WoW Lua，一个定制版 Lua 5.1）。虽然 Blizzard 从未公开其内部 AI 系统的完整实现，但从公开的插件 API 和玩家逆向分析中，可以观察到几个值得学习的模式：

- **事件驱动而非帧驱动**：WoW 的 AI 事件（`COMBAT_LOG_EVENT`、`UNIT_HEALTH`、`UNIT_SPELLCAST_SUCCEEDED`）驱动行为切换，而非每帧 tick。事件驱动的行为树在 MMO 服务器端（通常运行在较低频率的更新循环中）尤为重要——你不需要每帧检查条件，而是在条件变化时收到通知。
- **Secure Execution**：WoW 的战斗相关脚本运行在安全执行环境中，限制了某些 API 的调用。这类似于 C++ BT 引擎中的"沙盒"概念——确保 AI 脚本不能执行破坏性操作。
- **资源文件中的行为定义**：Boss 的 AI 行为定义通常存在于 `.xml` 或数据库记录中，Lua 脚本负责解释这些数据。这是一种"数据定义行为，脚本执行行为"的模式——策划配置数据表，脚本读取并执行。

### Roblox 行为树社区资源

Roblox 使用 Luau（Lua 的类型标注超集），拥有丰富的 AI 开发社区：

- **[Roblox Developer Hub: NPC Behavior](https://create.roblox.com/docs/npcs-and-bots)**：官方文档，涵盖 NPC 寻路、感知、状态管理的基础 API。
- **Community BT Implementations**：在 Roblox Toolbox 中搜索 "Behavior Tree"，可以找到多个社区实现。观察它们如何处理 Roblox 特有的并发模型（服务端 Authority vs 客户端预测）。
- **Luau Type Annotations for BT**：Luau 支持渐进类型标注，可以为核心 BT 节点 API 提供类型注解——这对于团队协作尤为重要，因为类型标注防止了"这个函数应该返回 string 还是 boolean"的歧义。如果你的 Lua BT 引擎会被多人使用，考虑加入类型注解。

---

## 常见陷阱

### 1. 闭包捕获的变量是引用，不是值

这是 Lua BT 中最常见的错误，也是最难调试的。当你用闭包定义 Action 时，闭包捕获的是**变量**而非变量的**当前值**：

```lua
-- ❌ WRONG: 所有 Action 引用同一个循环变量 i
local children = {}
for i = 1, 3 do
    children[i] = {
        type = "action",
        run = function(agent, bb)
            print("Processing waypoint " .. i)   -- always prints 4
        end,
    }
end

-- ✅ RIGHT: 在每次迭代中创建新的变量绑定
local children = {}
for i = 1, 3 do
    local wp_index = i   -- new binding per iteration
    children[i] = {
        type = "action",
        run = function(agent, bb)
            print("Processing waypoint " .. wp_index)
        end,
    }
end
```

在 Lua 5.2+ 中，`for` 循环的迭代变量本身在每次迭代中已经创建了新绑定——但只有当你**在循环体内不使用变量别名**时才安全。最保守的做法：**任何被闭包捕获的外部变量，都在闭包定义之前显式 `local` 绑定一次**。

### 2. 树定义的浅拷贝 vs 深拷贝

当你用同一个 tree table 为多个 agent 实例化时，它们共享同一个 table 引用。这会导致 `_last_running` 字段被多个 agent 互相覆盖：

```lua
-- ❌ WRONG: 两个 agent 共享同一棵树的 _last_running 状态
local agent1, agent2 = create_agent(), create_agent()
local shared_tree = { type = "selector", children = { ... } }
-- BT.tick(shared_tree, agent1, bb)  和  BT.tick(shared_tree, agent2, bb)
-- 互相破坏对方的 _last_running

-- ✅ RIGHT: 每个 agent 拥有树的独立深拷贝
local function deepcopy(orig)
    local copy = {}
    for k, v in pairs(orig) do
        if type(v) == "table" then
            copy[k] = deepcopy(v)
        else
            copy[k] = v
        end
    end
    return setmetatable(copy, getmetatable(orig))
end
```

注意：深拷贝会复制闭包引用——这是正确的行为，因为 Action/Condition 闭包应该是无状态的（状态在 agent 或 blackboard 上）。如果你的闭包内部有 `upvalue` 缓存（比如计时器），重构为将状态存储在 agent 或 blackboard 上。

### 3. 协程作为 Action 的陷阱

Lua 的协程看起来很适合"跨帧执行的顺序 Action"——你可以 `coroutine.yield()` 等待条件，避免显式的 `"running"` 返回。但实现中存在一个微妙的陷阱：

```lua
-- ❌ RISKY: 协程在 BT 引擎中隐藏了控制流
local function chase_action(agent, bb)
    while not near_target(agent, bb.target) do
        move_toward_target(agent, bb.target)
        coroutine.yield("running")
    end
    attack(agent, bb.target)
    return "success"
end
```

问题出在**条件重评估**上。假设这棵树的 Selector 是：
```
Selector:
  Sequence [Flee]:
    Condition: health < 30%  →  ← 跑路中不应该重新检查！
    Action: chase_action (coroutine)
```
当协程 `yield` 后，框架从根节点重新 tick。如果 Selector 的 `_last_running` 实现不当（每次都从第一个子节点重新开始），`health < 30%` 的条件会在协程恢复前被重新评估——如果血量在此期间恢复到 30% 以上，Condition 返回 `failure`，整个 Flee Sequence 失败，协程被丢弃。

**根本原因**：行为树的条件评估是"抢占式"的——每次 tick 都可以重新评估条件。协程的"阻塞直到完成"语义与行为树的"每帧重新评估"语义存在根本冲突。

**解决方案（选一）**：
- **不用协程**。使用 `"running"` 返回 + 状态存储在 agent/blackboard 上——这是最安全的做法。
- **在 Selector/Sequence 中正确实现 `_last_running`**，确保协程被暂停期间不重新评估前面的兄弟节点（如示例 A 所示）。
- **将协程的 resume 封装在专门的 `BTCoroutineAction` 节点中**，该节点管理协程的生命周期、处理 `yield` 返回值、并在节点被中断时（兄弟 Condition 失败）调用 `coroutine.close()`。

### 4. 每帧创建 table 导致的 GC 压力

Lua 的 GC 是增量的，但仍然可能在高频 tick 循环中造成帧率波动。最常见的 GC 压力源：

```lua
-- ❌ BAD: 每帧创建新的临时 table
local function patrol_action(agent, bb)
    local pos = { x = agent.x, y = agent.y }  -- per-frame allocation
    local nearest = find_nearest_enemy(pos)     -- if fn also allocates...
    -- ...
end
```

对于 200 个 NPC × 60fps = 每秒 12,000 个临时 table。即使在现代 LuaJIT 上，这也会产生可测量的 GC 压力。

**解决方案**：
- **复用临时 table**：在 blackboard 中预分配临时存储，每次 tick 时原地更新字段值。
- **用多个标量代替 table**：`local ax, ay = agent.x, agent.y` 比 `{x=agent.x, y=agent.y}` 更高效。
- **关闭 GC 分步**：在 tick 循环期间临时设置 `collectgarbage("stop")`，在每帧末尾允许 GC 执行一步 `collectgarbage("step", 10)`。注意：这需要在你的具体场景中测量——不当使用可能导致内存泄漏。
- **使用 LuaJIT**：LuaJIT 的 allocation sinking 优化可以将许多临时对象消除在编译时。对于分配敏感的行为树场景，LuaJIT 相比标准 Lua 5.1/5.2 有 2-5 倍的性能优势。

### 5. `_last_running` 没有在树完成时清除

当树从根节点返回 `"success"` 或 `"failure"` 时，Composite 节点内部的 `_last_running` 标记必须被清除。否则下一次 tick 会从上次的索引继续，而不是从头评估：

```lua
-- ❌ WRONG: 上一帧 Selector 在 children[2] 上返回了 success
--   下一帧，_last_running 还指向 2，跳过了 children[1]
--   如果 children[1] 是新出现的更高优先级行为，它被错误忽略了

-- ✅ RIGHT: 在 _tickSelector 和 _tickSequence 中，
--   当子节点返回 success 或 failure 时，设置 _last_running = nil
--   只有返回 "running" 时才保留 _last_running
```

这个 bug 的特点是在 AI 运行数分钟后才开始出现——因为 `_last_running` 的残留只在特定条件下暴露。单元测试中一定要覆盖"树完成 → 新条件出现 → 旧条件不满足"的场景。
