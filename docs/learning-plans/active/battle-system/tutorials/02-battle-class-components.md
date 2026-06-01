# 02 — Battle 核心类与组件系统

**前置依赖**：[01 — 架构总览与入口](01-architecture-entry.md)

---

## 目录

1. [Class 系统简介](#1-class-系统简介)
2. [class.Class() 与 class.Component()](#2-classclass-与-classcomponent)
3. [Battle 类字段总览](#3-battle-类字段总览)
4. [组件机制：AddComponents](#4-组件机制addcomponents)
5. [Battle 生命周期](#5-battle-生命周期)
6. [多随机数隔离设计](#6-多随机数隔离设计)
7. [代码示例：ctor 与 Update](#7-代码示例ctor-与-update)
8. [练习题](#8-练习题)
9. [常见陷阱](#9-常见陷阱)
10. [扩展阅读](#10-扩展阅读)

---

## 1. Class 系统简介

项目使用 `Common/Class.lua` 实现了一套 Lua OOP 框架。设计的核心出发点是：

- **单继承类（Class）**：提供构造、初始化、销毁等标准生命周期，支持 `super` 调用链。
- **组件（Component）**：通过方法拷贝（mixin trick）把一个 Component 表的方法"注入"到类中，实现横向能力聚合，而不引入继承网状结构。

框架头部的注释明确说明了这个设计动机（`Class.lua` 第 4–31 行）：

> Component 如果支持继承，当把一个 Component 加到 Entity 上的时候，需要额外再 Entity 的 table 里维护 Component 的继承链……当你调用 `ent:test()` 方法，很难知道这个 test 来自于哪里，是 ent 本身的继承链，还是 component trick 来的方法……尤其是调用 `super.Test(ent, xxx)` super 到了哪里呢？

因此：**Component 不支持继承，只支持平铺方法集合**。

---

## 2. class.Class() 与 class.Component()

### 2.1 class.Class()

```lua
-- 签名
-- typeName:    类名字符串（全局唯一）
-- superType:   父类，可为 nil
-- isSingleton: 是否单例，可为 nil（默认 false）
function Class.Class(typeName, superType, isSingleton)
```

EmmyLua 注解形式：

```lua
---@generic T, P
---@class Class
---@overload fun(typeName:T, superType:P?, isSingleton:boolean?):T
```

**内置生命周期方法**（框架在 `__defaultMethods` 中声明）：

| 方法 | 调用时机 | 返回值要求 |
|---|---|---|
| `ctor` | `new()` 时立即调用 | 无 |
| `init` | 显式外部调用，初始化依赖资源 | 必须返回 `true`/`false` |
| `clear` | 重置，不销毁对象 | 可选 |
| `start` | 业务启动 | 可选 |
| `stop` | 业务暂停 | 必须返回 `true`/`false` |
| `destroy` | 彻底销毁，释放所有引用 | 可选 |

> `init` 是唯一被标记为 `__retValueMethods` 的方法——框架会检查其返回值；其他方法不校验返回值。

### 2.2 class.Component()

```lua
-- 签名
-- typeName: 组件名字符串（全局唯一）
function Class.Component(typeName)
```

Component 本质是一个携带方法的普通 table，通过 `Class.AddComponents` 把其中的方法"拷贝"进目标类的虚表（vtbl）。Component 自身没有实例，没有 `new`，也没有继承链。

---

## 3. Battle 类字段总览

`Battle.lua` 第 26–60 行通过 EmmyLua `---@class (partial) Battle` 声明了 Battle 的所有公开字段。`(partial)` 关键字表示这个类定义是**分片声明**——Battle 继承自 `EventCenter`，同时挂载了十余个 Component，每个 Component 内部也可以补充字段注解，最终由 IDE 合并成完整类型视图。

### 核心字段分类

#### 状态与配置

| 字段 | 类型 | 说明 |
|---|---|---|
| `battleState` | `Enum.BattleState` | 当前战斗状态（None/Arrange/Field/Fight） |
| `gameFuncType` | `GameFuncType` | 游戏功能类型（PVE/PVP等） |
| `levelId` | `integer` | 关卡 ID |
| `isPvp` | `boolean` | 是否 PVP 战斗 |
| `isClient` | `boolean` | 是否客户端正常战斗（悔棋时为 false） |
| `isPlayPerform` | `boolean` | 当前是否在播放剧情 |
| `timeRate` | `integer` | 时间倍率（加速战斗） |
| `accumulatedTime` | `number` | 帧累积时间，用于驱动固定步长逻辑帧 |

#### 核心对象

| 字段 | 类型 | 说明 |
|---|---|---|
| `teams` | `OrderedMap<Enum.Team, BattleTeam>` | 所有阵营（None/Self/Friend/Enemy/Hide） |
| `mainStateMgr` | `StateManager` | 战斗主状态机（驱动 None→Arrange→Field→Fight） |
| `timerMgr` | `TimeManager` | 定时器管理器 |
| `dataMgr` | `GameDataManager` | 策划配置表（所有 Excel 数据） |
| `battleInfo` | `BattleInfo\|ArenaBattleInfo` | 战斗描述数据（PVE 与 PVP 结构完全不同） |
| `scWorldHeroManager` | `SCWorldHeroManager` | 开战前的世界将领管理器 |
| `EntityOperationSign` | `table<Enum.Team, boolean>` | 各阵营是否可操作的标志位 |

#### ID 生成器

| 字段 | 类型 | 说明 |
|---|---|---|
| `entityIdCreator` | `EntityIdCreator` | 实体 ID 生成器（每场战斗独立，避免服务器多战斗并发 ID 冲突） |
| `skillIdCreator` | `SkillIdCreator` | 技能实例 ID 生成器 |
| `triggerIdCreator` | `TriggerIdCreator` | 触发器实例 ID 生成器 |

#### 随机数（详见第 6 节）

| 字段 | 类型 | 说明 |
|---|---|---|
| `battleInitRandomSeed` | `integer` | 初始随机种子 |
| `battleRandom` | `Random` | 战斗逻辑随机数 |
| `aiRandom` | `Random` | AI 逻辑随机数 |
| `autoBattleRandom` | `Random` | 托管表现随机数 |
| `combatRandom` | `Random` | 对冲战斗表现随机数 |
| `bfRandom` | `Random` | 战场表现随机数 |

---

## 4. 组件机制：AddComponents

### 4.1 注册方式

`Battle.lua` 第 61–76 行：

```lua
local Battle = class.Class("Battle", EventCenter, false)

class.AddComponents(Battle, {
    BattleMapComp,       -- 地图管理
    BattleTriggerComp,   -- 触发器系统
    BattleTurnComp,      -- 回合管理
    BattleBuffComp,      -- Buff 系统
    BattleFightComp,     -- 战斗核心逻辑
    BattleReportComp,    -- 战报记录
    BattleLogicComp,     -- 战斗逻辑杂项
    BattleLoadComp,      -- 战斗加载
    BattleAIGroupComp,   -- AI 组管理
    BattleRegretComp,    -- 悔棋系统
    BattleAchievementComp, -- 成就系统
    BattleDebugComp,     -- 调试工具
})
```

共 **12 个 Component**，每个负责一个战斗子系统的方法集合。

### 4.2 AddComponents 的执行过程

`Class.lua` 第 731–749 行：

```lua
local function _addComponent(cls, component)
    assert(component.__IsComponent, "must be a component")
    assert(component.typeName ~= nil, "component must have a name")
    assert(ComponentNames[component.typeName] ~= nil, "component must register")
    assert(cls.componentNames[component.typeName] == nil,
           "class already has same component " .. component.typeName)

    cls.componentNames[component.typeName] = true
    cls.components[#cls.components + 1] = component
    _addComponentProperties(cls, component)
    _addComponentPropertyCallbacks(cls, component)
    _addComponentSyncModeCallbacks(cls, component)
    _addComponentAttr(cls, component)   -- 方法拷贝发生在这里
end

function Class.AddComponents(cls, components)
    for i = 1, #components do
        _addComponent(cls, component)
    end
end
```

`_addComponentAttr` 遍历 Component 虚表（vtbl），把所有方法写入 `cls` 的虚表。最终效果：Battle 实例可以直接调用 `self:UpdateFight(dt)`（来自 BattleFightComp）、`self:UpdateTurn()`（来自 BattleTurnComp）等，无需持有组件实例引用。

### 4.3 `(partial)` 注解的意义

```lua
---@class (partial) Battle:EventCenter
```

EmmyLua 的 `(partial)` 修饰词告诉 IDE：**这个 `@class` 声明只是完整类型的一部分**，不要覆盖同名的其他声明。

由于 Battle 的字段分散在：
- `Battle.lua` 自身的 `---@class (partial) Battle` 块
- 各个 Component 文件内的补充注解

IDE（如 EmmyLuaAnalyzer）会把所有 `(partial)` 片段合并，得到完整的 Battle 类型信息。没有 `(partial)` 时，后出现的 `@class Battle` 声明会覆盖前一个，导致类型丢失。

---

## 5. Battle 生命周期

```
new()
  └─ ctor()          # 零依赖初始化，只分配基础对象
       |
  init()             # 创建 teams、注册状态机状态，返回 true/false
       |
  Update(dt)         # 每帧由 C# 调用，驱动固定逻辑帧
  FixedUpdate30Hz(dt)# 固定 30Hz 逻辑帧（FIXED_TIME_STEP = 0.03）
  LateUpdate()       # 帧末：清理延迟增删的实体
       |
  destroy()          # 释放所有引用，调用 super.destroy
```

### 5.1 FIXED_TIME_STEP = 0.03

`Battle.lua` 第 494 行（局部变量，模块私有）：

```lua
local FIXED_TIME_STEP = 0.03
```

0.03 秒 = 1/33.3 Hz，**近似 30Hz** 固定逻辑帧率。注意代码注释标记了一个待优化项：

```lua
-- wrt todo 1 : 这个考虑改成 333 这种整型, 避免浮点数计算误差问题
```

当前实现使用浮点数累积，长时间运行存在微小误差积累风险，但对于单场有限时长的战斗，实际影响可忽略。

### 5.2 init() 的关键初始化

```lua
function Battle:init()
    self.timerMgr = TimeManager("Battle")          -- 定时器在 init 才创建（ctor 时为 nil）

    require("Logic.Battle.BattleEventID")          -- 懒加载事件 ID 表

    -- 建立 5 个阵营
    self.teams:set(Enum.Team.None,   BattleTeam(Enum.Team.None,   self))
    self.teams:set(Enum.Team.Self,   BattleTeam(Enum.Team.Self,   self))
    self.teams:set(Enum.Team.Friend, BattleTeam(Enum.Team.Friend, self))
    self.teams:set(Enum.Team.Enemy,  BattleTeam(Enum.Team.Enemy,  self))
    self.teams:set(Enum.Team.Hide,   BattleTeam(Enum.Team.Hide,   self))

    -- 注册状态机的 4 个状态
    self.mainStateMgr:AddState("StateNone",    ...)
    self.mainStateMgr:AddState("ArrangeState", ...)
    self.mainStateMgr:AddState("FieldState",   ...)
    self.mainStateMgr:AddState("FightState",   ...)

    -- 初始仅 Self 阵营可操作
    self.EntityOperationSign[Enum.Team.Self]   = true
    self.EntityOperationSign[Enum.Team.Friend] = false
    self.EntityOperationSign[Enum.Team.Enemy]  = false

    return true
end
```

`ctor` 与 `init` 的分工很明确：**ctor 只做零依赖的字段赋值**（`timerMgr = nil`、`teams = OrderedMap.new()`），**init 才真正构建依赖关系**（创建 TimeManager、创建各 BattleTeam）。这样设计允许框架在创建对象后、注入外部依赖之前，有一个干净的窗口期。

---

## 6. 多随机数隔离设计

战斗中存在 **5 个独立的 Random 对象**，每个有明确的使用边界：

| 字段 | 层次 | 悔棋/服务器可用 | 记录调试日志 | 职责 |
|---|---|---|---|---|
| `battleRandom` | 逻辑层 | ✅ | ✅ | 不涉及 AI 的战斗逻辑（伤害计算、技能命中等） |
| `aiRandom` | 逻辑层 | ✅ | ✅ | 机器人生成操作指令的 AI 决策 |
| `autoBattleRandom` | 表现层（有 AI 代码） | ❌ | ❌ | 客户端 UI 生成玩家托管操作指令 |
| `combatRandom` | 表现层 | ❌ | ❌ | 对冲战斗表现（如跳字位置） |
| `bfRandom` | 表现层 | ❌ | ❌ | 战场表现（如特效位置） |

> `combatRandom` 和 `bfRandom` 在 ctor 中被注释掉（`--self.combatRandom = ...`），说明它们仍在规划或按需启用中。

### 种子派生策略

`InitRandom(seed)` 用同一个初始种子派生三个逻辑层随机数，通过不同的线性变换保证序列独立：

```lua
function Battle:InitRandom(seed)
    self.battleRandom:SetSeed(seed)
    self.aiRandom:SetSeed(seed * 97531 + 33333)
    self.autoBattleRandom:SetSeed(seed * 13579 + 11111)
end
```

三条序列从相同初始熵出发，但因乘数和偏移不同，产生完全不相关的随机序列。

### 隔离的必要性

```
场景：玩家开启托管（autoBattle）时

客户端运行：battleRandom → 逻辑帧确定性
            autoBattleRandom → 托管 AI 每帧操作，非确定性，不上传服务器
            aiRandom → 机器人 AI

服务器/悔棋：battleRandom → 相同种子，完全重演
             aiRandom     → 相同种子，完全重演
             autoBattleRandom → 不运行（避免污染确定性）
```

如果 `autoBattleRandom` 与 `battleRandom` 共享同一个对象，托管时消耗的随机数会改变后续逻辑帧的随机序列，导致服务器与客户端结果不一致（去同步/desync）。

---

## 7. 代码示例：ctor 与 Update

### 7.1 ctor —— 零依赖字段初始化

```lua
-- Battle.lua 第 79-122 行
function Battle:ctor()
    Battle.super.ctor(self)           -- 调用 EventCenter.ctor

    self.debug = true
    if macroIsClient then
        self.detailDebug = true
    else
        self.detailDebug = false      -- 服务器端不打印详细日志（避免影响性能）
    end

    self.isClient = false
    self.teams = OrderedMap.new()     -- 空有序表，teams 在 init() 中填充
    self.battleInfo = nil
    self.timerMgr = nil               -- 注意：init() 时才创建
    self.levelId = 0
    self.gameFuncType = nil
    self.battleState = Enum.BattleState.None
    self.dataMgr = nil
    self.isPlayPerform = false
    self.isPvp = false
    self.timeRate = 1
    self.accumulatedTime = 0
    self.mainStateMgr = StateManager()

    self.battleInitRandomSeed = 0
    self.battleRandom = Random("battleRandom", self, true)   -- 第三参数 true：记录调试日志
    self.aiRandom     = Random("aiRandom",     self, true)
    self.autoBattleRandom = Random("autoBattleRandom", self, false)  -- false：不记录调试日志

    self.entityIdCreator  = EntityIdCreator()
    self.skillIdCreator   = SkillIdCreator()
    self.triggerIdCreator = TriggerIdCreator()

    self.actionBuffRecordMap   = {}
    self.completeActionRecordMap = {}
    self.StartSelfActionIndex = 0
end
```

### 7.2 Update / FixedUpdate30Hz —— 固定步长驱动

```lua
-- Battle.lua 第 494-528 行
local FIXED_TIME_STEP = 0.03  -- 约 30Hz 固定逻辑帧步长

function Battle:Update(dt)
    self.accumulatedTime = self.accumulatedTime + self.timeRate * dt
    -- 累积时间超过阈值时，以固定步长驱动逻辑帧（可能一帧驱动多次）
    while (self.accumulatedTime >= FIXED_TIME_STEP) do
        self:FixedUpdate30Hz(FIXED_TIME_STEP)
        self.accumulatedTime = self.accumulatedTime - FIXED_TIME_STEP
    end
end

function Battle:FixedUpdate30Hz(dt)
    if nil ~= self.timerMgr then
        self.timerMgr:Update(dt)     -- 1. 定时器推进
    end
    self:UpdateFight(dt)             -- 2. 战斗核心（BattleFightComp 注入）
    self:UpdateTrigger()             -- 3. 触发器（BattleTriggerComp 注入）
    self:UpdateTurn()                -- 4. 回合（BattleTurnComp 注入）

    if nil ~= self.performMgr then
        self.performMgr:Update(dt)   -- 5. 表现管理器（仅客户端）
    end

    if self.teams ~= nil then
        for _, team in OrderedMap.pairs3(self.teams) do
            team:Update()            -- 6. 各阵营内实体 Update
        end
    end

    if self.mainStateMgr ~= nil then
        self.mainStateMgr:Update()   -- 7. 主状态机 tick
    end
end
```

`FixedUpdate30Hz` 的调用顺序是确定性的：定时器 → 战斗逻辑 → 触发器 → 回合 → 表现 → 各 team → 状态机。理解这个顺序对调试"为什么某个效果在这帧没有生效"至关重要。

---

## 8. 练习题

**题 1**：`FIXED_TIME_STEP = 0.03` 时，若某帧 `dt = 0.1`（卡顿帧），`FixedUpdate30Hz` 会被调用几次？`accumulatedTime` 最终剩余多少？请手动模拟 `Update` 的 while 循环。

**题 2**：在 `Battle:ctor()` 中，`combatRandom` 和 `bfRandom` 被注释掉了，但 `---@field` 注解依然保留。如果某个 Component 在这两个字段为 `nil` 时直接调用 `self.combatRandom:Next()`，会发生什么？应如何防御性地处理？

**题 3**：假设需要新增一个 `BattleReplayComp`（战斗回放组件），需要在 `Battle.lua` 中做哪些修改？仅修改 `Battle.lua`，不修改 Class 框架，写出完整的修改位置和内容。

---

## 9. 常见陷阱

### 陷阱 1：在 ctor 中访问 timerMgr

`timerMgr` 在 `ctor` 里被初始化为 `nil`，在 `init()` 里才创建。如果某个 Component 的 `ctor` 方法中访问 `self.timerMgr`，会得到 `nil` 而不是异常。**必须确认访问 timerMgr 的代码路径是在 init() 之后才执行**。

### 陷阱 2：Component 方法重名覆盖

`_addComponentAttr`（`Class.lua` 第 675 行）把 Component 的方法写入类的虚表。如果 Battle 自身（或其父类 EventCenter）有同名方法，且 Component 中存在同名方法，会**静默覆盖**。框架通过 `assert(cls.componentNames[component.typeName] == nil, ...)` 防止同一组件注册两次，但不检测方法名冲突。新增 Component 时必须搜索全表确认无重名。

### 陷阱 3：误用 autoBattleRandom 写逻辑代码

`autoBattleRandom` 的第三参数为 `false`（不记录调试日志），是专为**客户端托管 AI** 设计的。在悔棋流程和服务器端，这个 Random 不应被调用。如果在逻辑层代码中误用了 `autoBattleRandom` 而不是 `battleRandom`，服务器与客户端的随机序列会不同步，产生难以复现的 desync bug。

### 陷阱 4：`(partial)` 注解缺失导致类型不完整

在为 Battle 添加新字段注解时，必须使用：

```lua
---@class (partial) Battle
---@field public newField SomeType 新字段说明
```

如果漏写 `(partial)`，IDE 会将其视为完整的类型重定义，覆盖之前所有的字段声明，导致类型检查失效。

### 陷阱 5：Update 调用顺序依赖

`FixedUpdate30Hz` 内部的调用顺序（定时器 → 战斗 → 触发器 → 回合 → team）是经过设计的，依赖关系存在于相邻步骤之间。不要随意调整这个顺序，触发器的计算依赖战斗结果，回合推进依赖触发器的处理完成。

---

## 10. 扩展阅读

- `Client/Assets/Script/Lua/Common/Class.lua`：完整 Class 框架实现，重点阅读第 117–582 行（`Class.Class` 函数体）和第 618–672 行（`Class.Component`）。
- `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleTurnComp.lua`：了解一个真实 Component 的结构，以及它如何声明 `---@class (partial) Battle` 来扩展字段注解。
- `Client/Assets/Script/Lua/Common/StateManager.lua`：主状态机 `mainStateMgr` 的实现，理解 `AddState` / `Update` 的工作方式。
- `Client/Assets/Script/Lua/Common/Random.lua`：随机数封装，理解第三参数（是否记录调试日志）对确定性回放的影响。
- `Client/Assets/Script/Lua/Logic/Battle/BattleTeam.lua`：BattleTeam 的结构，理解 `teams:pairs()` 遍历时各阵营的处理逻辑。
