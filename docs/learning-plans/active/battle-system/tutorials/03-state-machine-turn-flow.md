---
title: "03 战斗状态机与回合流程"
updated: 2026-06-05
---

# 03 战斗状态机与回合流程

## 前置依赖

- [[./01-architecture-entry|01 架构入口与 Stage 状态机]]
- [[./02-battle-class-components|02 Battle 类与组件系统]]
- 理解 `Enum.lua` 中的枚举定义
- 了解 Lua 的闭包与回调模式

---

## 1. 战斗主状态机（mainStateMgr）

`Battle` 对象持有一个 `StateManager` 实例 `mainStateMgr`，管理整场战斗的宏观生命周期。它在 `Battle:init()` 中注册四个状态：

```lua
-- Client/Assets/Script/Lua/Logic/Battle/Battle.lua:136-139
-- 注册四个主状态到 mainStateMgr 状态机，每个状态绑定 Enter/Running/Leave 三个生命周期回调
self.mainStateMgr:AddState("StateNone",
    CallbackHandler(self,"onStateNoneEnter"),
    CallbackHandler(self,"onStateNoneRunning"),
    CallbackHandler(self,"onStateNoneLeave"))  -- 初始/结束态：战斗未激活
self.mainStateMgr:AddState("ArrangeState",
    CallbackHandler(self,"onArrangeStateEnter"),
    CallbackHandler(self,"onArrangeStateRunning"),
    CallbackHandler(self,"onArrangeStateLeave"))  -- 布阵阶段：玩家摆放将领、调整阵型
self.mainStateMgr:AddState("FieldState",
    CallbackHandler(self,"onFieldStateEnter"),
    CallbackHandler(self,"onFieldStateRunning"),
    CallbackHandler(self,"onFieldStateLeave"))  -- 上场阶段：将领就位，回合推进入口
self.mainStateMgr:AddState("FightState",
    CallbackHandler(self,"onFightStateEnter"),
    CallbackHandler(self,"onFightStateRunning"),
    CallbackHandler(self,"onFightStateLeave"))  -- 战斗阶段：每帧驱动回合逻辑
```

每个状态对应 `Enum.BattleState` 的一个值：

| 状态名 | BattleState 枚举值 | 含义 |
|---|---|---|
| `StateNone` | `None = 0` | 战斗未激活，初始/结束态 |
| `ArrangeState` | `Arrange = 1` | 布阵阶段：玩家摆放将领、调整阵型 |
| `FieldState` | `Field = 2` | 上场阶段：将领就位，战斗前的回合推进入口 |
| `FightState` | `Fight = 3` | 战斗中：每帧驱动 `UpdateFightState()` |

### 切换时机

```
StateNone
    ↓  BattleStage 加载完毕后，isSkipArray=false 时进入布阵
ArrangeState
    ↓  玩家确认布阵，或 isSkipArray=true 时直接跳过
FieldState         ← PrepareBattle() 中 mainStateMgr:SetCurState("FieldState")
    ↓  StartBattle() 之后，FightState 负责实际回合驱动
FightState
    ↓  StopBattle() 时（胜/败/中止）
StateNone
```

`onFightStateRunning` 每帧调用 `self:UpdateFightState()`，这是整个回合机器的心跳。`ArrangeState` 与 `FieldState` 的 Running 回调目前为空，逻辑由上层 Stage 驱动。

进入 `ArrangeState` 时会重置所有战场属性：

```lua
-- Battle.lua:595-596
function Battle:onArrangeStateEnter()
    self.battleState = Enum.BattleState.Arrange  -- 同步本地状态标记
    self:SwitchFriendToSelfWhenNoAiConfig()  -- 无 AI 配置时将友方转为己方控制
    self:ResetAttr() -- 重置所有战场属性，将领/士兵的 buff 属性在此计算
    self:NotifyClient(LogicEventID.SetBattleState, false, self.battleState)  -- 通知客户端状态变更
end
```

---

## 2. 回合管理（BattleTurnComp）

`BattleTurnComp` 是 `Battle` 挂载的核心组件，负责所有回合逻辑。相关字段与枚举集中在文件头部。

### 2.1 TurnState — 整体回合状态

```lua
-- BattleTurnComp.lua:41-46
-- 整体回合状态机：采用单帧触发器模式，StartTurn/StopTurn 是"下一帧执行"的指令而非持续性状态
---@enum TurnState
local TurnState = {
    None       = 0,  -- 无状态 / 已被消费
    StartTurn  = 1,  -- 触发器：下一帧执行 StartTurn()
    InTurn     = 2,  -- 当前回合进行中（持续性状态）
    StopTurn   = 3,  -- 触发器：下一帧执行 StopTurn()
}
```

这是一个**单帧触发器**模式：设置为 `StartTurn` 或 `StopTurn` 后，`UpdateBattleTurn()` 在下一帧检测到它，调用对应函数，再将状态推进到 `InTurn` 或回到 `StartTurn`。

### 2.2 TeamTurnState — 阵营回合状态

```lua
-- BattleTurnComp.lua:49-54
-- 阵营回合状态机：嵌套在 TurnState.InTurn 内部，三个阵营依次经历 Start→In→Stop 的轮转
---@enum TeamTurnState
local TeamTurnState = {
    None           = 0,  -- 无状态 / 已被消费
    StartTeamTurn  = 1,  -- 触发器：下一帧开始该阵营行动
    InTeamTurn     = 2,  -- 该阵营正在行动（持续性状态）
    StopTeamTurn   = 3,  -- 触发器：下一帧结束该阵营行动
}
```

同样是触发器模式，与 `TurnState` 嵌套：每个回合内，三个阵营依次经历 `Start → In → Stop`。

### 2.3 关键字段

```lua
-- BattleTurnComp.lua:56, 77-92（注解摘录）
-- BattleTurnComp 的核心字段，驱动回合与阵营轮转的完整状态
local DefaultMaxTurn = 99      -- 默认最大回合数，超出则判负

---@field public turnId        integer          -- 当前回合编号（从 1 开始递增）
---@field public MaxTurn       integer          -- 最大回合数，默认 99，可被关卡配置覆盖
---@field public orderList     table            -- 回合内阵营行动顺序（Self→Friend→Enemy）
---@field public curOrderIndex integer          -- 当前正在行动的阵营在 orderList 中的索引
---@field public curActionTeamType Enum.Team    -- 当前行动阵营
---@field public curActionHero BattleHero       -- 当前行动英雄
---@field public turnState     TurnState        -- 整体回合状态（触发器模式）
---@field public teamTurnState TeamTurnState    -- 阵营回合状态（触发器模式，嵌套在 InTurn 内）
---@field public operationStep integer          -- 当前回合操作序号（每次英雄行动递增）
---@field public heroActionRecord table         -- 记录每回合每英雄是否已行动（用于去重和完成检测）
```

### 2.4 orderList — 阵营行动顺序

`orderList` 在 `ctor` 中初始化，决定每个回合内三个阵营的出手顺序：

```lua
-- BattleTurnComp.lua:114-118
-- 阵营行动顺序表：每个回合内按 Self → Friend → Enemy 的顺序依次执行
self.orderList = {
    { teamType = Enum.Team.Self,    isCompleted = false },  -- 我方先动
    { teamType = Enum.Team.Friend,  isCompleted = false },  -- 友方次之
    { teamType = Enum.Team.Enemy,   isCompleted = false }   -- 敌方最后
}
```

顺序固定为：**我方 → 友方 → 敌方**。`curOrderIndex` 从 0 开始，每次进入 `StartTeamTurn` 时自增 1，取 `orderList[curOrderIndex]` 决定当前行动阵营。

同文件顶部还定义了一个 `teamList`，用于遍历所有参战阵营时的排列顺序：

```lua
-- BattleTurnComp.lua:71
-- 用于遍历全部阵营的排列（如回合 Buff 触发、快照保存），与 orderList 顺序一致但职责不同
---@type Enum.Team[]
local teamList = { Enum.Team.Self, Enum.Team.Friend, Enum.Team.Enemy }
```

---

## 3. 英雄行动状态机（HeroTurnState）

每个 `BattleHero` 持有 `turnState`（类型 `Enum.HeroTurnState`），由 `HeroTurnComp` 驱动。

```lua
-- Enum.lua:70-82
-- 英雄行动状态机：每个英雄独立持有，驱动单次行动从开始到结束的完整生命周期
-- 触发器值（Continue=3, NewMove=6, NewTurn=9）在 StopTurnAction 中设置，由 UpdateTurnAction 在下一帧消费
---@enum Enum.HeroTurnState
HeroTurnState = {
    None          = 0,  -- 未激活 / 已结束
    Start         = 1,  -- 英雄被选中，准备开始行动
    InProgress    = 2,  -- 正在执行主行动（移动/使用技能）
    Continue      = 3,  -- 触发器：即将进入"继续行动"阶段
    StartContinue = 4,  -- 继续行动开始（等效于第二次 Start）
    InContinue    = 5,  -- 继续行动执行中
    NewMove       = 6,  -- 触发器：即将进入"再动"阶段
    StartNewMove  = 7,  -- 再动开始
    InNewMove     = 8,  -- 再动执行中
    NewTurn       = 9,  -- 触发器：即将进入"再行动"阶段（完整的第二次行动）
    Stop          = 10, -- 行动彻底结束，等待 UpdateHeroTurn 回收（下一帧由 UpdateHeroTurn 重置为 None）
}
```

三个扩展行动标志（字段而非枚举值）决定 `StopTurnAction` 走哪条分支：

| 字段 | 含义 |
|---|---|
| `hasNewMove` | 获得**再动**：本次行动结束后，还可以额外移动一次（不可放主公技） |
| `hasContinue` | 获得**继续行动**：移动一次后，再获得一次移动资格 |
| `hasNewTurn` | 获得**再行动**：完整的第二次行动机会（可使用技能） |

注意：`hasNewTurn` 与 `hasContinue` 不能同时为 `true`，代码有断言保护：

```lua
-- HeroSkillComp.lua:350-351
-- 运行时断言：hasNewTurn 与 hasContinue 语义互斥，同时为 true 属于技能配置错误
if self.hasNewTurn == true and self.hasContinue == true then
    logError("cannot self.hasNewTurn == true and self.hasContinue == true,only one exist")
end
```

### 再动（NewMove）流程

```
InProgress
    ↓ StopTurnAction() 检测到 hasNewMove == true
NewMove          ← UpdateTurnAction 检测到此状态，触发再动
    ↓ StartTurnAction()
StartNewMove
    ↓ BeforeStartTurnAction() → TryStartAction() 回调
InNewMove        ← 正在执行再动的移动
    ↓ StopTurnAction()（hasNewMove 已消耗）
Stop
```

### 继续行动（Continue）流程

```
InProgress
    ↓ StopTurnAction() 检测到 hasContinue == true
Continue         ← 触发器
    ↓ StartTurnAction()
StartContinue
    ↓ TryStartAction() 回调
InContinue
    ↓ StopTurnAction()（正常分支）
Stop
```

### 再行动（NewTurn）流程

```
InProgress
    ↓ StopTurnAction() 检测到 hasNewTurn == true
（执行 _stopTurnAction，afterStopTurnAction）
NewTurn          ← 触发器，inNewTurn = true
    ↓ UpdateTurnAction 检测到此状态
None / 重新进入 Start 开始完整第二次行动
    ↓ 最终 StopTurnAction()（hasNewTurn 已消耗）
Stop
```

AI 阵营的状态切换在 `AIAction:SetHeroTurnState()` 中统一处理：

```lua
-- AIAction.lua:34-43
-- AI 阵营统一消费触发器状态：将 NewMove/Continue/NewTurn 触发器转为实际执行状态
function AIAction:SetHeroTurnState()
    local hero = self.owner
    if hero.turnState == Enum.HeroTurnState.NewMove then
        hero.turnState = Enum.HeroTurnState.StartNewMove  -- 触发器 → 再动开始
    elseif hero.turnState == Enum.HeroTurnState.Continue then
        hero.turnState = Enum.HeroTurnState.StartContinue  -- 触发器 → 继续行动开始
    elseif hero.turnState == Enum.HeroTurnState.NewTurn then
        hero.turnState = Enum.HeroTurnState.None  -- 再行动触发器 → 重置为 None，下一轮重新 Start
    end
end
```

---

## 4. 完整回合执行流程

以下伪代码对应 `BattleTurnComp:UpdateBattleTurn()` 与 `UpdateHeroTurn()` 的每帧驱动逻辑。

```
-- 每帧调用（由 Battle:onFightStateRunning → UpdateFightState → UpdateTurn 驱动）
UpdateBattleTurn():

    if turnState == StartTurn:
        teamTurnState = None
        StartTurn(turnId + 1)
            -- turnId 递增
            -- 清除 heroActionRecord[turnId]（新回合行动记录）
            -- 检查地形效果 CheckTerrainEffect
            -- 通知客户端 StartTurn 事件
            -- curOrderIndex = 0
            -- teamTurnState = StartTeamTurn
            -- turnState = InTurn

    if turnState == StopTurn:
        teamTurnState = None
        StopTurn()
            -- 触发 OnStopTurnTrigger
            -- 通知客户端 StopTurn 事件
            -- 检查胜利条件 CheckBattleResultWithTargetTurn
            --   胜利 → StopBattle(Win)
            -- turnId >= MaxTurn(99) → StopBattle(Lost)
            -- 否则 turnState = StartTurn（开启下一回合）

    ---- 阵营轮转 ----
    if teamTurnState == StartTeamTurn:
        teamTurnState = None
        curOrderIndex += 1
        nextTeamType = orderList[curOrderIndex].teamType   -- Self→Friend→Enemy
        StartTeamAction(turnId, nextTeamType)
            -- 延迟 1 帧（客户端延迟 1500ms 等待 UI）
            -- 触发回合开始 Buff：TriggerStartTurnBuffs
            -- 找到该阵营第一个可行动英雄 getNextActionHero
            --   有英雄 → doStartHeroAction → teamTurnState = InTeamTurn
            --   无英雄 → teamTurnState = StopTeamTurn

    if teamTurnState == StopTeamTurn:
        teamTurnState = None
        StopTeamAction(turnId, curActionTeamType)
            -- 触发回合结束 Buff：TriggerStopTurnBuffs
            -- 通知所有该阵营英雄 OnStopTeamAction
            -- orderList[curOrderIndex].isCompleted = true
            -- 若 curOrderIndex < #orderList（还有下一阵营）
            --     teamTurnState = StartTeamTurn  →  进入下一阵营
            -- 若 curOrderIndex == #orderList（三个阵营都完成）
            --     turnState = StopTurn  →  结束本回合


UpdateHeroTurn():
    -- 仅在 turnState == InTurn 且 teamTurnState == InTeamTurn 时运行

    if curActionHero.turnState == Stop:
        curActionHero.turnState = None
        if checkTeamIsCompleted(turnId, teamType):
            teamTurnState = StopTeamTurn    -- 本阵营所有英雄已行动
        else:
            obj = getNextActionHero(turnId, teamType)
            doStartHeroAction(turnId, teamType, obj)  -- 下一个英雄开始行动

    curActionHero:UpdateTurnAction()  -- 驱动当前英雄的行动状态机
```

### 一回合完整时序

```
回合 N 开始
│
├─ [我方] StartTeamAction
│   ├─ TriggerStartTurnBuffs（按 actionValue 升序）
│   ├─ 英雄 A: None→Start→InProgress→[NewMove?]→Stop
│   ├─ 英雄 B: None→Start→InProgress→Stop
│   └─ StopTeamAction → TriggerStopTurnBuffs
│
├─ [友方] StartTeamAction
│   └─ ... (同上)
│
├─ [敌方] StartTeamAction
│   └─ ... (同上)
│
└─ StopTurn → 检查胜负 → 回合 N+1 或 结束战斗
```

---

## 5. 代码示例

### UpdateBattleTurn（核心调度器）

```lua
-- BattleTurnComp.lua:1767-1790
-- 核心调度器：每帧被 UpdateFightState 调用，负责回合级和阵营级状态机的消费与推进
function BattleTurnComp:UpdateBattleTurn()
    if not self.isInBattle then
        return  -- 战斗已结束，停止调度
    end

    -- 第一层：回合级状态机（StartTurn / StopTurn 触发器消费）
    if self.turnState == TurnState.StartTurn then
        self.teamTurnState = TurnState.None  -- 清零阵营状态，进入新回合
        self:StartTurn(self.turnId + 1)  -- turnId 递增，重置行动记录，触发地形检查
    elseif self.turnState == TurnState.StopTurn then
        self.teamTurnState = TurnState.None  -- 清零阵营状态
        self:StopTurn()  -- 触发回合结束 Buff，检查胜负，决定是否进入下一回合
    end

    -- 第二层：阵营级状态机（StartTeamTurn / StopTeamTurn 触发器消费）
    if self.teamTurnState == TeamTurnState.StartTeamTurn then
        self.teamTurnState = TeamTurnState.None  -- 立即消费触发器，避免重复处理
        self.curOrderIndex = self.curOrderIndex + 1  -- 推进到下一个阵营
        local order = self.orderList[self.curOrderIndex]
        local nextTeamType = order.teamType
        self:StartTeamAction(self.turnId, nextTeamType)  -- 触发回合开始 Buff，找第一个英雄行动
    elseif self.teamTurnState == TeamTurnState.StopTeamTurn then
        self.teamTurnState = TeamTurnState.None  -- 立即消费触发器
        self:StopTeamAction(self.turnId, self.curActionTeamType)  -- 触发回合结束 Buff，标记阵营完成
    end
end
```

### StopTurn（回合结束与上限判断）

```lua
-- BattleTurnComp.lua:1057-1083
function BattleTurnComp:StopTurn()
    self:OnStopTurnTrigger()  -- 触发回合结束时点（Buff 结算等）

    if self.isClient then
        self:NotifyClient(LogicEventID.StopTurn, true, self.turnId)  -- 通知客户端渲染回合结束
    end

    -- 优先检查目标回合胜利条件（关卡配置的特定回合胜负判定）
    if self:CheckBattleResultWithTargetTurn() then
        self:StopBattle(Enum.BattleResult.Win)
        return  -- 胜利则不再继续
    end

    -- 回合数达到上限（默认 99）则判负，否则开启下一回合
    if self.turnId >= self.MaxTurn then
        self:StopBattle(Enum.BattleResult.Lost)
    else
        self.turnState = TurnState.StartTurn  -- 设置触发器，下一帧 StartTurn
    end
end
```

### UpdateHeroTurn（英雄轮转）

```lua
-- BattleTurnComp.lua:1553-1607（精简）
-- 英雄行动轮转：在同一阵营内依次调度英雄行动，英雄结束则推进到下一个
function BattleTurnComp:UpdateHeroTurn()
    if self.turnState ~= TurnState.InTurn then return end  -- 仅在回合进行中调度
    if self.teamTurnState ~= TeamTurnState.InTeamTurn then return end  -- 仅在阵营行动中调度

    -- 当前英雄仍在行动中，等待其完成
    if self.curActionHero ~= nil and self.curActionHero:IsTurnActing() then
        return  -- 英雄未完成行动，本帧不做轮转
    end

    if self.curActionHero ~= nil then
        -- 英雄 turnState == Stop：行动彻底结束，回收并决定下一个英雄
        if self.curActionHero.turnState == HeroTurnState_Stop then
            self.curActionHero.turnState = HeroTurnState_None  -- 重置为 None，以便下一回合复用

            -- 检查战斗是否已分出胜负
            if not self:CheckBattleResult() then
                -- 当前阵营所有英雄是否都已完成行动
                if self:checkTeamIsCompleted(self.turnId, self.curActionHero.teamType) then
                    self.teamTurnState = TeamTurnState.StopTeamTurn  -- 阵营结束，触发 StopTeamTurn
                else
                    local obj = self:getNextActionHero(self.turnId, self.curActionHero.teamType)
                    if obj ~= nil then
                        self:doStartHeroAction(self.turnId, self.curActionHero.teamType, obj)  -- 启动下一个英雄
                    end
                end
            end
        end
        self.curActionHero:UpdateTurnAction()  -- 驱动英雄自身行动状态机（无论是否 Stop）
    end
end
```

### StopTurnAction 中的"再动"分支

```lua
-- HeroTurnComp.lua:463-499（精简）
-- StopTurnAction 内部：根据三个互斥标志决定行动结束后的分支走向
-- 优先级：hasNewMove > hasNewTurn > 正常结束（hasContinue 在上层已处理为 Continue 触发器）
if self.hasNewMove then
    -- 消耗 hasNewMove，保留行动记录，进入 NewMove 阶段（仅额外移动，不可使用技能）
    self.battle:SetHeroActionFlag(curTurnID, self.id, true)
    self.hasNewMove = false
    -- → turnState = NewMove（触发器，下一帧由 UpdateTurnAction 消费）
elseif self.hasNewTurn then
    -- 进入再行动，inNewTurn = true，不消耗行动记录（允许完整的第二次行动）
    self.inNewTurn = true
    self.hasNewTurn = false
    -- → turnState = NewTurn（触发器，下一帧重置为 None 后重新 Start）
else
    -- 正常结束：标记已行动，进入 Stop 等待回收
    self.battle:SetHeroActionFlag(curTurnID, self.id, true)
    -- → turnState = Stop
end
```

---

## 6. 练习题

**题 1（理解）**

当 `turnId` 达到 99 时，战斗不会立刻结束，而是在 `StopTurn()` 时结束。请解释：为什么需要先走完最后一个回合的 `StopTeamAction`，而不是在 `StartTurn` 时直接判断 `turnId > MaxTurn` 并结束？

提示：思考最后一回合的回合结束 Buff（TriggerStopTurnBuffs）和成就检查的触发时机。

---

**题 2（分析）**

假设我方某英雄在技能结算后同时获得了 `hasNewTurn = true`，且此时 `hasContinue` 也意外被设为 `true`，代码中有哪个保护机制会捕获这个错误？这条保护位于哪个文件的哪个函数中？

---

**题 3（追踪）**

`isAutoNext` 字段在 `BattleTurnComp:ctor()` 中初始化为 `true`。请在代码中找出：哪个场景会导致 `isAutoNext` 被设为 `false`？这会对 `getNextActionHero` 的行为产生什么影响？

提示：搜索 `isAutoNext` 的赋值点。

---

## 7. 常见陷阱

### 陷阱 1：状态值是触发器，不是当前状态

`TurnState.StartTurn` 和 `TeamTurnState.StartTeamTurn` 并不代表"正在开始"，而是**单帧触发信号**。`UpdateBattleTurn` 检测到后立刻将其清零（置为 `None`），然后调用对应函数。

错误理解：把 `turnState == StartTurn` 当作"当前处于回合开始阶段"来做持续性检查。

正确理解：这是一个"下一帧执行"的指令，检测到后必须立即消费。

### 陷阱 2：DefaultMaxTurn 是 99，不是 100

`MaxTurn = 99`，`StopTurn()` 中判断的是 `self.turnId >= self.MaxTurn`，即第 99 回合结束后判负。第 99 回合本身是最后一个正常执行的回合。

### 陷阱 3：orderList 决定阵营顺序，teamList 用于遍历

`orderList` 控制回合内三个阵营的行动顺序（Self→Friend→Enemy）；  
`teamList` 是一个本地变量，仅用于回合 Buff 触发、快照保存等需要遍历全部阵营的场合。  
两者顺序相同，但职责不同，不要混淆。

### 陷阱 4：hasNewTurn 与 hasContinue 互斥

这两个标志只能同时存在一个。如果技能逻辑同时触发两者，`HeroSkillComp` 和 `HeroBFSkillComp` 中的 `logError` 会捕获，但不会中断执行，可能导致回合流程异常。排查时优先检查技能配置与 Buff 的互斥条件。

### 陷阱 5：客户端延迟与逻辑帧不一致

`StartTeamAction` 在客户端会等待 1500ms 后才触发回合开始 Buff（等待 UI 展示）：

```lua
-- BattleTurnComp.lua:1294-1305
-- 服务端与客户端延迟差异：客户端额外等待 1.5s 以配合 UI 动画展示，服务端仅延迟 1ms（近乎即时）
local delayTime = 1  -- 服务端/快进模式：1ms，几乎无延迟
if self.isClient then
    delayTime = 1500  -- 客户端：延迟 1.5s 等待 UI 展示回合开始动画
end
self.timerMgr:AddTimerCallback(delayTime, function()
    self:TriggerStartTurnBuffs(turnID, teamType, ...)  -- 延迟后触发回合开始 Buff
end)
```

在服务端/快进模式下 `delayTime = 1`（1ms，接近无延迟）。如果在调试时对比客户端与服务端的逻辑帧序列，这段延迟会导致事件顺序看起来不同，但结果是一致的。

---

## 8. 扩展阅读

- `Client/Assets/Script/Lua/Logic/Battle/Comp/HeroTurnComp.lua` — 英雄行动状态机完整实现，包括 `StartTurnAction`、`StopTurnAction`、`UpdateTurnAction`
- `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/AIBehaviorComp.lua` — AI 阵营如何响应 `HeroTurnState` 并自动执行行动
- `Client/Assets/Script/Lua/Logic/Battle/TeamGroupAction.lua` — 集群行动（多单位联合出手）如何嵌入回合流程
- `Client/Assets/Script/Lua/Common/StateManager.lua` — `mainStateMgr` 底层状态机实现
- `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleRegretComp.lua` — 悔棋模式下 `UpdateHeroTurnInRegretMode` 如何在回放中重演操作序列
