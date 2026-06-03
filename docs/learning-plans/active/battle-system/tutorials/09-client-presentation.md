# 教程 09：客户端表现层

**系列**：战斗系统深度剖析 · 第 9 篇  
**前置依赖**：
- 教程 01：架构总览与入口
- 教程 02：Battle 类与组件系统
- 教程 03：状态机与回合流程
- 教程 05：BattleHero 实体

---

## 1. 表现层框架概述

战斗系统采用**逻辑-表现分离**架构。`Logic/Battle/Battle.lua` 是纯逻辑层，负责规则计算、AI 决策、伤害结算；`ClientBattle/ClientBattle.lua` 是其在客户端的**镜像**，负责一切可见效果：角色动画、特效、血条、跳字、音效、摄像机。

两层通过 `SetLogicBattle` 绑定：

```lua
-- ClientBattle.lua
---@param lcBattle Battle
function ClientBattle:SetLogicBattle(lcBattle)
    -- 持有逻辑层引用，表现层通过此引用读取逻辑状态（只读，禁止写入）
    self.logicBattle = lcBattle
    -- 将客户端剧情管理器注入逻辑层，使逻辑层能通过 performMgr 驱动客户端表现序列
    self.logicBattle.performMgr.clientPerformMgr = self.clientPerformMgr
    -- 注入 C# GridManager 单例，逻辑层与表现层共享同一格子状态
    self.logicBattle.gridMgr = CS.Core.GridManager.Inst
    -- 绑定完成，广播全局事件通知 UI / 音频等外部系统
    eventMgr:Send(EventID.Logic_BATTLE_CREATE, lcBattle)
end
```

绑定做了三件事：

1. 持有逻辑层引用 `self.logicBattle`，表现层可随时读取逻辑状态（**只读**）。
2. 将 `ClientPerformManager` 注入逻辑层的 `performMgr`，使逻辑层能驱动客户端剧情。
3. 将 C# 侧 `GridManager.Inst` 注入逻辑层，共享同一格子管理器实例。

绑定完成后发出全局事件 `EventID.Logic_BATTLE_CREATE`，通知 UI 层和其他系统战斗就绪。

## 2. ClientBattle 组件列表

`ClientBattle` 通过 `class.AddComponents` 混入六个组件，各司其职：

```lua
class.AddComponents(ClientBattle, {
    -- 通过 class.AddComponents 混入六个表现层组件，各自负责独立子系统
    BattleMapComp,        -- ClientBattleMapComp
    BattleFightComp,      -- ClientBattleFightComp
    BattleBFComp,         -- ClientBattleBFComp
    BattleSelectComp,     -- ClientBattleSelectComp
    BattleReceiverComp,   -- ClientBattleReceiverComp
    ClientBattleSnapShoot,
})
```

### 2.1 ClientBattleMapComp

负责战场地图的表现初始化：加载地图场景（`LoadMap`）、管理出生点（`bornPtMaps`）、地形特效（`terainEffMaps`/`terainEffPools`）、隐藏宝箱（`HideTreasure`）、格子特效（`GridEffect`）。战斗开始前由 `BeforeStartBattle → ClearBornPoint` 清理。

### 2.2 ClientBattleSelectComp

处理**玩家输入与选择逻辑**：点击英雄、拖拽换位、选中/取消、攻击确认、技能预释放。内部维护 `opStateMgr`（StateManager）状态机管理操作状态，以及 `selectedObj`（当前选中的 ClientBattleHero）、`dragHero`（拖拽中的将领）。

### 2.3 ClientBattleFightComp

驱动**战斗表现动画**：攻守双方（`attacker`/`defender`）的战斗场景搭建、士兵列阵、移动入场（`defaultMoveTime = 0.6s`）、战斗摄像机位置管理。持有 `combatSceneController` 控制战斗场景，`isFighting` 标记战斗中状态，`timeScale` 用于快进倍速。

### 2.4 ClientBattleBFComp

处理**战场技（BF Skill）相关表现**，主要职责是全屏压黑遮罩：

```lua
-- 战场技，压黑：控制全屏黑色遮罩的显隐与淡入淡出
function ClientBattleBFComp:BFSetFullScreenBlackMask(
    visible,        -- true=显示遮罩 / false=隐藏
    attarckerId,    -- 释放者 ID，用于遮罩层级归属
    isMultiTarget,  -- 是否为多目标技能（影响遮罩范围）
    target,         -- 目标对象引用
    eraseInOutTime, -- 淡入/淡出过渡时长（秒）
    callback)       -- 过渡完成回调
```

持有 `skillFullBlackMaskTrans`（GameObject 引用），仅在需要时懒加载，通过 `GameObject.Find("BattleFight")` 找到根节点后向下查找遮罩。

### 2.5 ClientBattleReceiverComp

**逻辑层消息接收器**，是表现层与逻辑层通信的核心桥梁。逻辑层将操作打包为 `LogicMessage`，由本组件的 `PumpLogicMessage` 在每帧消费，映射到具体处理函数（如 `CreateHero`、`DestroyHero`、`MoveToTarget`、`SetBattleState` 等）。这一设计保证逻辑与表现**解耦**：逻辑层不持有任何表现对象，只发消息。

### 2.6 ClientBattleSnapShoot

**快照（存档回放）支持组件**，实现 `SetSnapShoot` / `RecoverSnapShoot` / `ExitSnapShoot`。在存档回放场景下异步加载对应地图场景，恢复地形特效、实体快照状态。

## 3. ClientBattleHero：逻辑与表现的连接点

`ClientBattleHero`（`ClientEntity/Battle/ClientBattleHero.lua`）继承自 `ClientEntity`，是每个战场将领的客户端代理。它持有两个关键引用：

- `self.logicObject`（`BattleHero`）：逻辑层实体，所有数值（HP、Buff、位置）从此读取。
- `self.visEntity`（`VisActor`，由 `GraphicComp` 管理）：渲染层实体，承载 Spine 动画和特效。

```lua
-- ClientBattleHero 是每个战场将领的客户端代理，通过 logicObject 读取逻辑数据，通过 visEntity 驱动渲染
---@class (partial) ClientBattleHero:ClientEntity
---@field public logicObject BattleHero   -- 对应的逻辑层对象
---@field public battle      ClientBattle
---@field public id          integer      -- 实例 id
---@field public GeneralID   integer      -- 配置表 GeneralInfo.ID
```

逻辑层通过 `OnStartAction` / `OnStopAction` 通知表现层行动节奏：

```lua
-- 逻辑层通知本将领进入可行动状态，驱动移动动画并广播回合行动事件
function ClientBattleHero:OnStartAction()
    self.isStartAction = true
    self:OnStartAction_Move()
    self.battle:Send(ClientBattleEventID.StartTurnAction, self.id, self.teamType)
end
```

### 3.1 ClientBattleHero 的组件列表

```lua
class.AddComponents(ClientBattleHero, {
    -- 13 个组件通过组合模式扩展 ClientBattleHero 的表现能力
    GraphicComp,          -- 管理 visEntity/visBloodBar/特效
    HudComp,              -- 血条、Buff 图标、手牌特效
    HeroDamageComp,       -- 伤害数字跳字
    HeroComAttrComp,      -- 属性同步（从 logicObject 读取）
    HeroBFSkillComp,      -- 战场技表现
    HeroCombatSkillComp,  -- 战斗技表现
    HeroAIComp,           -- 客户端 AI 辅助逻辑
    ComMoveComp,          -- 移动动画驱动
    HeroBuffComp,         -- Buff 表现（特效挂载/移除）
    HeroBuffActionComp,   -- Buff 结算动画序列
    HeroBattleFightComp,  -- 战斗中角色对决动作
    HeroTurnComp,         -- 回合开始/结束动画
    HeroSoundComp,        -- 音效触发
    HeroSnapShootComp,    -- 快照状态管理
})
```

#### GraphicComp 的关键字段

`GraphicComp` 是连接 `ClientBattleHero` 与 `VisEntity` 系统的核心：

```lua
---@field public visEntity         VisActor   -- 主角色 Spine 模型
---@field public soldierVisEntities table<number, VisActor>  -- 士兵模型列表
---@field public combatVisEntity   VisActor   -- 战斗专用模型
---@field public visBloodBar       VisBloodBar
---@field public fxMaps            table<number, VisFx>  -- 挂载特效
```

所有 `VisEntity` 对象都**不直接 new**，而是通过 `VisEntityPool.GetInstance():Get(assetPath, modelType)` 获取，用完后调用 `Recycle` 归还。

## 4. VisEntity 系统

`Graphic/VisEntity/` 目录是所有可视对象的基础库，采用**组合继承**，`VisEntity` 为基类，各子类扩展特定能力：

| 类名 | 职责 |
|------|------|
| `VisEntity` | 基类：GameObject 生命周期、异步加载、位置/旋转/缩放/可见性 |
| `VisActor` | Spine 动画角色：继承 VisEntity，持有 `spineController` 和 `AnimationStateMachine` |
| `VisFx` | 特效：持有 `fxController`，支持时长、循环、延迟回收 |
| `VisBloodBar` | 血条+Buff图标：包含 `bloodBar`、`buffBar` 两个 C# 组件引用 |
| `VisWayPointBar` | 移动路径进度条 |
| `VisShootFly` | 飞行物（箭矢/投射物） |
| `VisBubble` | 对话气泡 |
| `VisBackMap` | 背景地图层 |
| `VisTextMeshPro` | 世界空间 TextMeshPro 文字 |
| `VisCharBust` | 角色半身像（技能演出） |
| `VisWorldPlayer` | 世界地图玩家图标 |
| `VisTimeline` | Timeline 动画控制器 |
| `VisBornEntity` | 出生动画实体 |

### 4.1 VisEntityPool 对象池

`VisEntityPool`（单例）是所有 `VisEntity` 的统一管理器，避免频繁创建/销毁 GameObject：

```lua
-- VisEntityPool 是所有 VisEntity 的统一对象池单例，按 assetPath 分桶管理空闲对象，避免频繁创建/销毁 GameObject
---@class VisEntityPool
---@field public poolMaps  Queue<VisEntity>  -- 按 assetPath 分桶的空闲队列
---@field public poolRoot  UnityEngine.Transform  -- 池根节点（隐藏于场景中）
local VisEntityPool = class.Class("VisEntityPool", nil, true)  -- 第三个参数 true 表示单例模式
```

**获取对象**：`VisEntityPool:Get(assetPath, modelType)`  
- 若空闲队列 `poolMaps[assetPath]` 有对象，直接取出，调用 `Reset` 复位状态。  
- 若没有，调用 `Create` 异步加载 Prefab，创建新的 `VisActor`/`VisFx` 等实例。

**归还对象**：`VisEntityPool:Recycle(visEntity, checkLoad)`  
- 将 `visEntity` 的父节点改为 `poolRoot`（对玩家不可见）。  
- 放入 `poolMaps[assetPath]` 队列，等待复用。  
- `checkLoad` 为 `true` 时等待加载完成再回收，防止回收进行中的异步加载对象。

### 4.2 VisActor：Spine 动画控制

`VisActor` 继承 `VisEntity`，是战斗单位（将领/士兵）的渲染载体：

```lua
-- VisActor 是战斗单位的渲染载体，继承 VisEntity 并扩展 Spine 动画控制能力
---@class VisActor:VisEntity
---@field public animationStateMachine AnimationStateMachine
---@field public spineController       SpineController  -- C# Spine 控制器
---@field public speed                 number
```

动画接口：

```lua
-- 播放指定动画，loop 控制循环，onCompletedCb 为非循环动画的结束回调，id 用于区分动画实例
function VisActor:Play(anim, loop, onCompletedCb, id)

-- 设置整体动画播放速率，影响 spineController 的 timeScale
function VisActor:SetAnimationSpeed(speed)

-- 渐隐消失：在 duration 秒内将 alpha 降至 0，用于死亡/退场表现
function VisActor:FadeOut(duration, callback)

-- 爆白闪烁：time 秒内将角色材质设为白色高亮，用于受击反馈
function VisActor:SetWhiteOut(time)

-- 把任意 GameObject 挂载到 Spine 骨架的指定骨骼节点上，用于装备/特效绑定
function VisActor:AttachToBone(gameObject, boneName)
```

动画状态机（`AnimationStateMachine`）封装了 Spine 的状态切换逻辑，每帧在 `VisActor:Update()` 中驱动：

```lua
-- 每帧驱动动画状态机更新；nil 检查防止 AnimationStateMachine 尚未创建时调用报错
function VisActor:Update()
    if nil ~= self.animationStateMachine then
        self.animationStateMachine:Update()
    end
end
```

### 4.3 VisFx：特效管理

`VisFx` 管理粒子/序列帧特效，关键字段：

```lua
-- VisFx 关键生命周期字段：duration=-1 表示永久特效，需业务方手动回收；isLoop 标记循环播放
self.duration = -1   -- 持续时间，-1 表示永久（需手动回收）
self.isLoop   = false
self.recycleTime = 0 -- 延迟回收时间戳，用于非循环特效播完后自动归还对象池
self.onPlayCompleted = nil  -- 非循环特效播完回调
```

特效通过 `VisEntityPool` 统一管理生命周期。**不循环特效**在 `duration` 时间后自动归还对象池；**循环特效**（`isLoop = true`）必须由业务方主动调用 `Recycle`，否则永久驻留。

## 5. 更新频率差异：逻辑 30Hz vs 表现 60Hz

逻辑层和表现层各有独立的固定步长，两者**互不干扰**：

```lua
-- Logic/Battle/Battle.lua
-- 逻辑层固定 30Hz 更新：累加 dt（受 timeRate 倍速影响），用 while 循环消费累积时间
local FIXED_TIME_STEP = 0.03   -- 30Hz
function Battle:Update(dt)
    self.accumulatedTime = self.accumulatedTime + self.timeRate*dt
    -- while 循环确保帧率波动时追赶逻辑步数，保证逻辑确定性
    while (self.accumulatedTime >= FIXED_TIME_STEP) do
        self:FixedUpdate30Hz(FIXED_TIME_STEP)
        self.accumulatedTime = self.accumulatedTime - FIXED_TIME_STEP
    end
end

-- ClientBattle/ClientBattle.lua
-- 表现层固定 60Hz 更新：dt 不经 timeRate 处理，由 FixedUpdate60Hz 内部自行应用倍速
local FIXED_TIME_STEP = 0.016666   -- 60Hz
function ClientBattle:Update(dt)
    self.accumulatedTime = self.accumulatedTime + dt
    while (self.accumulatedTime >= FIXED_TIME_STEP) do
        self:FixedUpdate60Hz(FIXED_TIME_STEP)
        self.accumulatedTime = self.accumulatedTime - FIXED_TIME_STEP
    end
end
```

| 维度 | 逻辑层 | 表现层 |
|------|--------|--------|
| 步长 | `0.03s`（30Hz） | `0.016666s`（60Hz） |
| 受 `timeRate` 影响 | 是（`self.timeRate * dt`） | 是（内部 `st = timeRate * dt`） |
| 驱动内容 | 规则计算、AI、Buff 结算 | 动画、特效、Timer、GridManager |
| 注意 | 结果确定性，可回放 | 允许插值，视觉流畅 |

`FixedUpdate60Hz` 内部每帧完成：

1. `timerMgr:Update(st)` — 驱动表现层计时器（动画延迟、特效时序）
2. 遍历所有 `team:Update(st)` — 驱动每个 `ClientBattleHero:Update`
3. `FullScreenFXManager:Update` — 全屏后处理效果
4. `clientPerformMgr:Update(dt)` — 剧情/表现序列
5. `PumpLogicMessage()` — 消费逻辑层消息队列
6. `GridManager.Inst:Update()` — 格子高亮/路径显示

## 6. ClientBattleEventID 事件系统

`ClientBattleEventID`（`ClientBattle/ClientBattleEventID.lua`）定义表现层内部通信的全部事件 ID，声明为全局枚举：

```lua
-- 声明为全局枚举，通过 GLDeclare 注册到 Lua 全局命名空间，供所有战斗组件直接引用
---@enum ClientBattleEventID
local ClientBattleEventID = {
    -- 状态变化
    BattleStateChanged = 20,
    StartBattle        = 142,
    StopBattle         = 143,
    StartTurn          = 136,
    StopTurn           = 137,
    StartTeamAction    = 140,
    StopTeamAction     = 141,

    -- 将领事件
    HeroDie            = 17,   -- 移除时及时触发
    HeroDying          = 18,   -- 血量为 0 时触发
    HeroHp             = 10,
    GeneralSkill       = 14,
    InFightDamage      = 19,

    -- 玩家操作
    SelectedHero           = 109,
    Attack                 = 106,
    CancelAttack           = 107,
    OpenAttackUIPanel      = 103,
    SkipRound              = 114,

    -- 技能/Buff 表现
    StartSkill             = 130,
    StopSkill              = 131,
    DisplaySkillTitle      = 132,
    FullScreenBlackMask    = 133,
    BuffDamageNotice       = 211,
}
-- 将枚举注册为全局变量，跨文件可通过 ClientBattleEventID.xxx 直接访问
GLDeclare("ClientBattleEventID", ClientBattleEventID)
```

`ClientBattle` 继承自 `EventCenter`（而非全局 `eventMgr`），事件在**战斗实例内部**传播，生命周期随战斗销毁而清空：

```lua
-- 战斗实例内部事件通信：通过 self.battle:Send/On 在组件间传递，随战斗实例生命周期自动管理
-- 发送事件
self.battle:Send(ClientBattleEventID.StartBattle)

-- 订阅事件（在某组件的 init 中注册）
self.battle:On(ClientBattleEventID.HeroHp, function(heroId, hp, maxHp)
    -- 刷新对应将领血条显示
end)
```

注意与全局 `eventMgr:Send(EventID.BATTLE_CREATE, self)` 的区别：全局事件给战斗**外部**系统（UI、音频）使用；`ClientBattleEventID` 仅供战斗内部各组件通信。

## 7. HUD 系统

每个 `ClientBattleHero` 通过 `HudComp` 管理其游戏内 HUD，HUD 对象同样从 `VisEntityPool` 获取：

```lua
-- HudComp 持有的字段：所有 HUD 元素通过 VisEntityPool 获取，生命周期由组件管理
self.visBloodBar = nil   -- VisBloodBar，头顶血条
self.visFIBBar   = nil   -- VisEntity，强攻进度条（ForceIntoBattle）
self.buffSlots   = { 0, 0, 0 }  -- Buff 插槽状态，0=空闲，非0=对应 Buff ID
self.baseCardFx  = {}    -- 杀/闪/桃 手牌特效
```

### 7.1 VisBloodBar 血条

`VisBloodBar` 封装了 C# `BloodBar` 和 `BuffBar` 组件，提供 Lua 侧接口：

```lua
-- 设置血条填充比例（0~1）；nil 检查确保 C# BloodBar 组件已正确绑定
function VisBloodBar:SetHpValue(v)
    if nil ~= self.bloodBar then
        self.bloodBar:SetBarRate(v)
    end
end

-- 设置头像
function VisBloodBar:SetHeadImage(imgName)

-- 设置 Buff 图标（按插槽索引），支持堆叠层数和剩余回合数显示
function VisBloodBar:SetBuffIcon(slotIdx, assetPath, isStack, buffCount, roundCount)

-- 显示/隐藏百分比文字
function VisBloodBar:SetShowPercentage(isShow)
```

血条的排序层通过 `SetSortingLayerID` 管理，确保正确的遮挡关系。

### 7.2 跳字（HurtText）

伤害/治疗数字由 C# 侧 `HurtTextManager` 统一管理，Lua 通过全局引用调用：

```lua
-- 获取 C# HurtTextManager 单例引用，Lua 侧不直接管理跳字对象
local hurtTextMgr = CS.Core.HurtTextManager.Inst

-- 战斗速率变化时同步跳字速率：倍速播放时跳字飘动速度也需等比调整
function ClientBattle:SetTimeRate(index)
    local s = AnimSpeed.GetRateByIndex(index)
    -- ...
    hurtTextMgr:SetTimeRate(s)
end
```

`HeroDamageComp` 负责触发跳字，将逻辑层的伤害结果转换为屏幕坐标上的飘字动画。

### 7.3 Buff 图标

`HudComp` 将逻辑 Buff ID 映射到血条上的插槽：

```lua
-- Buff ID 到血条插槽的映射：通过配置表 ID 确定显示位置，避免硬编码索引
local BuffSlotMap = {
    [100] = 1,  -- 杀 buff
    [200] = 2,  -- 闪 buff
    [300] = 3,  -- 桃 buff
    [400] = 4,  -- 酒 buff
}
```

更新通过 `visBloodBar:SetBuffIconWithSlot(slotIdx, ...)` 推入 C# 层渲染。

## 8. 核心代码示例

以下均为 `ClientBattle.lua` 的真实摘录。

### 8.1 ctor — 字段初始化

```lua
function ClientBattle:ctor()
    -- 调用父类 ctor 完成 EventCenter 等基础初始化
    ClientBattle.super.ctor(self)
    self.id = 0
    self.isClient = true
    self.logicBattle = nil       -- 绑定前为 nil，init 时不依赖逻辑层
    self.timerMgr = nil
    self.teams = nil
    self.battleInfo = nil
    self.trueBattleID = 0
    self.timeRate = 1            -- 默认 1x 速率，受 GameSetting.timeRate 控制
    self.isSkipArray = false     -- 是否跳过布阵
    self.isPvp = false           -- 是否为竞技场
    self.accumulatedTime = 0     -- 固定步长累加器，用于 FixedUpdate 调度
    self.battleState = Enum.BattleState.None
    self.skillActionPool = nil
    self.buffActionPool = nil
    self.clientPerformMgr = nil
    self.isVSPanelVisible = false
end
```

### 8.2 init — 子系统初始化

```lua
function ClientBattle:init()
    -- 加载事件 ID 枚举定义，触发 GLDeclare 注册为全局变量
    require("ClientBattle.ClientBattleEventID")
    self.debug = true
    self.detailDebug = true

    -- 创建表现层专用计时器管理器，用于动画延迟、特效时序等
    self.timerMgr = TimeManager("ClientBattle")

    -- 创建技能/Buff 表现动作对象池，避免频繁 GC 分配
    self.skillActionPool = SkillActionPool()
    self.buffActionPool  = BuffActionPool()
    self.clientPerformMgr = ClientPerformManager.GetInstance()

    self.skillActionPool:init()
    self.buffActionPool:init()
    self.clientPerformMgr:init(self)

    -- 初始化 C# GridManager，设置默认格子大小
    CS.Core.GridManager.Inst:Init()
    CS.Core.GridManager.Inst:SetGridSize(GridDefaultSize, GridDefaultSize)

    -- 建立五个阵营容器：本阵/友方/敌方/隐藏 各有独立 ClientBattleTeam
    self.teams = OrderedMap.new()
    self.teams:set(Enum.Team.None,   ClientBattleTeam(Enum.Team.None,   self))
    self.teams:set(Enum.Team.Self,   ClientBattleTeam(Enum.Team.Self,   self))
    self.teams:set(Enum.Team.Friend, ClientBattleTeam(Enum.Team.Friend, self))
    self.teams:set(Enum.Team.Enemy,  ClientBattleTeam(Enum.Team.Enemy,  self))
    self.teams:set(Enum.Team.Hide,   ClientBattleTeam(Enum.Team.Hide,   self))

    -- 默认开启输入，后续由 StartBattle 根据状态控制
    CS.CSharpCall.SetInputEnable(true)

    -- 发出全局事件通知外部系统（UI、音频等）战斗实例已就绪
    eventMgr:Send(EventID.BATTLE_CREATE, self)
    return true
end
```

### 8.3 SetLogicBattle — 绑定逻辑层

```lua
---@param lcBattle Battle
function ClientBattle:SetLogicBattle(lcBattle)
    -- 建立逻辑层引用；此时逻辑层所有组件已初始化完毕
    self.logicBattle = lcBattle
    -- 将客户端剧情管理器注入逻辑层，逻辑层通过 performMgr 驱动客户端表现序列
    self.logicBattle.performMgr.clientPerformMgr = self.clientPerformMgr
    -- 逻辑层与表现层共享同一 C# GridManager 实例，避免格子状态不同步
    self.logicBattle.gridMgr = CS.Core.GridManager.Inst
    -- 绑定完成后广播全局事件，依赖逻辑层数据的组件应监听此事件再初始化
    eventMgr:Send(EventID.Logic_BATTLE_CREATE, lcBattle)
end
```

### 8.4 StartBattle — 战斗开始

```lua
function ClientBattle:StartBattle(isPerform)
    -- 调试用：支持在 BattleGlobalData 中设置全局 Unity 时间缩放
    if BattleGlobalData.timeScale > 1 then
        CS.UnityEngine.Time.timeScale = BattleGlobalData.timeScale
    end

    -- 根据配置表播放战斗背景音乐
    local musicName = self.logicBattle.battleInfo.MusicBattle
    if nil ~= musicName and '' ~= musicName then
        SoundMgr.PlayMusic(musicName)
    end

    -- 遍历所有阵营，通知每个 ClientBattleTeam 开始战斗表现
    for _, team in (self.teams:pairs()) do
        team:OnStartBattle()
    end

    -- 应用玩家设置的战斗速率（1x/2x/3x）
    self:SetTimeRate(GameSetting.timeRate)

    -- 剧情模式下隐藏所有将领的血条和 Buff 图标，避免 HUD 干扰演出
    if isPerform then
        for _, team in (self.teams:pairs()) do
            for id, ent in (team.entities:pairs()) do
                ent:SetBloodBarIconVisible(false)
            end
        end
    end

    -- 广播战斗开始事件，各组件监听后启动对应表现
    self:Send(ClientBattleEventID.StartBattle)

    -- 禁用玩家输入，待开场动画/战斗条件就绪后再由对应逻辑开启
    CS.CSharpCall.SetInputEnable(false)
end
```

## 9. 练习题

**练习 1**：在 `ClientBattleFightComp` 中，战斗双方入场动画由 `moveTime`（默认 0.6s）控制。假设需要在高速模式（`timeRate = 3`）下将入场时间等比缩短，应该在哪个方法中读取 `timeRate` 并等比修改 `moveTime`？写出伪代码。

**练习 2**：`VisEntityPool:Recycle` 有一个 `checkLoad` 参数。如果一个 `VisFx` 特效在 `Load` 尚未完成时就被回收，且 `checkLoad = false`，会发生什么问题？结合 `VisEntity:Reset` 和 `loadState` 分析。

**练习 3**：`ClientBattleEventID.HeroDying`（血量为 0 时触发）和 `HeroDie`（移除时触发）是两个不同的事件。请描述：当一个将领触发死亡动画时，这两个事件的触发顺序，以及各自应该由哪个系统订阅处理。

## 10. 常见陷阱

### 陷阱 1：在表现层修改逻辑数据

`ClientBattleHero.logicObject` 是逻辑层 `BattleHero` 的**直接引用**，表现层代码可以读取其数值，但**绝不能写入**。逻辑层数据的修改必须通过逻辑层自身的方法完成，否则会导致逻辑-表现状态不一致，在回放/存档场景下产生无法复现的 bug。

```lua
-- 错误：在表现层直接修改逻辑数据，破坏逻辑确定性，回放结果将不一致
hero.logicObject.hp = hero.logicObject.hp - 10   -- 禁止

-- 正确：通过逻辑层方法触发伤害，表现层订阅 HeroHp 事件刷新血条显示
-- logicBattle 侧调用 hero:TakeDamage(10)，再由 ClientBattleEventID.HeroHp 同步
```

### 陷阱 2：更新频率不匹配导致的视觉抖动

逻辑层每 0.03s 更新一次位置，表现层每 0.016666s 驱动动画。如果表现层直接用逻辑坐标渲染而不做插值，角色会以 30Hz 的频率跳变，视觉上明显抖动。`ComMoveComp` 负责在两帧逻辑位置之间做平滑插值，不要绕过它直接 `SetPosition`。

### 陷阱 3：VisEntity 未归还对象池导致内存泄漏

循环特效（`isLoop = true`）不会自动回收。将领死亡、战斗结束时必须对所有挂载特效调用 `Recycle`。常见症状：连续战斗后粒子特效越来越多，帧率持续下降。`GraphicComp` 的 `destroy` 方法负责此清理，确保不跳过 `super.destroy`。

### 陷阱 4：在 FixedUpdate60Hz 中执行重度逻辑

表现层更新频率高（60Hz），在 `FixedUpdate60Hz` 中执行复杂的配置表查询、字符串拼接或 GC 分配会迅速累积开销。时序相关的一次性逻辑应用事件驱动（`Send/On`），轮询检测只适合轻量的状态查询。

### 陷阱 5：`isPerform` 模式下的 HUD 差异

`StartBattle(isPerform=true)` 时会强制隐藏所有将领的血条 Buff 图标。如果在剧情播放中创建了新的将领（`CreateHero`），该将领的血条图标初始化代码需要检查 `isPerform` 标志，否则图标会意外显示在剧情演出中。

### 陷阱 6：SetLogicBattle 调用时机

`ClientBattle:init()` 完成后 `logicBattle` 为 `nil`，组件的 `init` 方法中不能假设 `logicBattle` 已存在。依赖逻辑层数据的初始化操作应监听 `EventID.Logic_BATTLE_CREATE` 事件，在该事件触发后再执行。

## 11. 扩展阅读

- `ClientBattle/ClientBattleReceiverComp.lua`：完整的逻辑消息处理表（2200+ 行），  覆盖所有 `LogicEventID` 到表现动作的映射，是理解表现层行为的最佳索引。
- `ClientEntity/Battle/Comp/GraphicComp.lua`：将领 Spine 模型加载、士兵排列、  特效挂载的完整实现（1300+ 行）。
- `Graphic/VisEntity/AnimationStateMachine.lua`：Spine 动画状态机，  理解动画优先级、打断规则和过渡逻辑。
- `ClientBattle/Perform/ClientPerformManager.lua`：剧情/演出序列管理，  理解逻辑层如何通过 `performMgr` 驱动客户端动画序列。
- `Graphic/FxManager.lua`：全局特效管理器，`VisFx` 的上层调度，  了解特效资源的批量加载和复用策略。
