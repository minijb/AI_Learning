# 01 项目整体架构与战斗入口

## 前置知识

- Lua 基础语法（table、function、require、闭包）
- Unity MonoBehaviour 生命周期（Start / Update / LateUpdate）
- 面向对象概念（类、继承、实例）——本项目通过 `Common/Class.lua` 实现

---

## 1. 整体架构概览

### C# 框架 + Lua 业务逻辑

本项目采用 **C# 引擎框架 + Lua 业务逻辑** 的双层架构，通过 [xLua](https://github.com/Tencent/xLua) 在运行时双向桥接：

```
┌─────────────────────────────────────────────────────┐
│                    Unity C# 层                       │
│  MonoBehaviour 生命周期  │  引擎 API（物理/渲染/音频）  │
│  XLuaManager（启动 Lua VM）                          │
└────────────────┬────────────────────────────────────┘
                 │ xLua 桥接
                 │  CS.*  访问 C# 对象/方法
                 │  C# 直接调用 Lua 全局函数
┌────────────────▼────────────────────────────────────┐
│                    Lua 业务层                         │
│  LuaGame.lua（总入口）                               │
│  StageManager → Stage 状态机                        │
│  逻辑层 Logic/Battle/  ←→  表现层 ClientBattle/      │
└─────────────────────────────────────────────────────┘
```

> **为什么这样分层？**
> C# 负责引擎驱动，Lua 负责所有游戏逻辑。热更新时只需替换 Lua 文件包，C# 层无需重新发版。

### LuaGame.lua 生命周期

`Client/Assets/Script/Lua/LuaGame.lua` 是 C# 调用的唯一入口，它暴露四个全局函数供 C# 的 `XLuaManager` 驱动：

| C# 调用时机 | Lua 函数 | 职责 |
|---|---|---|
| `Start()` | `Start()` | 调用 `Init()` 完成所有子系统初始化，然后跳转首个 Stage |
| 每帧 | `Update()` | 驱动 `timerMgr`、`stageMgr`、`socketManager` 等的 Update |
| 每帧（渲染后） | `LateUpdate()` | 驱动 `stageMgr:LateUpdate()` |
| 应用退出 | `Close()` | 销毁所有子系统，清理资源 |

```lua
-- LuaGame.lua（简化）

-- C# 调用 Start() 时执行
function Start()
    Init()          -- 初始化所有子系统（EventManager、StageManager、PanelManager 等）
    GotoStage("LoginStage", { mapid = 1 })  -- 跳转登录 Stage，开始状态机
end

function Update()
    -- 所有每帧驱动均在此集中分发
    local dt = UnityTime.deltaTime
    timerMgr:update(dt)
    stageMgr:Update(dt)     -- 当前 Stage 的 Update 从这里触发
    socketManager:update(dt, UnityTime.unscaledDeltaTime)
end

function LateUpdate()
    stageMgr:LateUpdate()   -- 渲染后处理
end

function Close()
    OnClose()  -- 解绑事件、销毁各子系统
end
```

**`Init()` 初始化顺序**（摘自实际代码）：

```lua
-- LuaGame.lua – Init()
local BattleGlobalData = require("ClientBattle.BattleGlobalData")
GLDeclare("BattleGlobalData", BattleGlobalData)   -- 注册全局战斗数据容器

timerMgr  = TimeManager("ClientGlobal")
eventMgr  = EventManager.GetInstance()
stageMgr  = StageManager.GetInstance(); stageMgr:init()
panelMgr  = PanelManager.GetInstance(); panelMgr:init()
socketManager = require("Net.LuaSocketManager").GetInstance(); socketManager:init()
-- … 其余子系统依次初始化
```

`GLDeclare` 是项目封装的全局变量声明函数（见 `Common/Global.lua`），用于将单例注册为全局可访问变量，同时保证不被重复赋值。

---

## 2. Stage 状态机

### StageManager 的核心逻辑

`Client/Assets/Script/Lua/Stage/StageManager.lua` 是一个单例，持有唯一的 `curStage` 引用，并在 `ChangeStage` 时做旧 Stage 的销毁和新 Stage 的创建：

```lua
-- StageManager.lua
function StageManager:ChangeStage(stageName, data)
    local function changeStage()
        local preStage = ''
        if nil ~= self.curStage then
            preStage = self.curStage.name
            self.curStage:Exit(stageName, data)   -- 通知旧 Stage 退出
            self.curStage:destroy()               -- 销毁旧 Stage
        end
        self.curStage = nil
        local cls = require("Stage." .. stageName) -- 按名称动态加载
        local newStage = cls()
        self.curStage = newStage
        newStage:Enter(preStage, data)             -- 进入新 Stage
    end
    -- 切换到 LoadingStage 时需先打开 Loading 面板（遮挡画面）
    if stageName == "LoadingStage" then
        panelMgr:OpenPanel("LoadingPanel", changeStage, stageName, 3)
    else
        changeStage()
    end
end
```

### 主要 Stage 列表

| Stage 文件 | 职责 |
|---|---|
| `LoginStage.lua` | 登录、账号验证、资源热更新 |
| `LoadingStage.lua` | 通用加载过渡，加载完成后跳转目标 Stage |
| `WorldStage.lua` | 世界地图、城池、外交等主玩法 |
| `BattleStage.lua` | 战场全流程（布阵 → 上场 → 战斗 → 结算） |
| `BattleOfflinePVPStage.lua` | 离线 PVP 专用战斗 Stage |
| `PlotPerformStage.lua` | 剧情演出 Stage |
| `EmptyStage.lua` | 空 Stage，用于连续战斗（BattleStage → EmptyStage → BattleStage）时的中转清场 |

### 进入 BattleStage 的路径

`GotoStage` 函数（`Stage/GoToStage.lua`）是所有 Stage 切换的统一入口，它屏蔽了"是否需要 Loading 过渡"的细节：

```lua
-- GoToStage.lua
local function GotoStage(targetStage, stageData)
    log(string.format("GotoStage %s %s", targetStage, stageData and stageData.nextStage))
    if targetStage == "BattleStage" then
        -- 必须经过 LoadingStage 加载地图资源，再跳转 BattleStage
        stageMgr:ChangeStage("LoadingStage", { data = stageData, nextStage = targetStage })
    elseif targetStage == "WorldStage" then
        stageMgr:ChangeStage("LoadingStage", { data = stageData, nextStage = targetStage })
    elseif targetStage == "LoginStage" or targetStage == "EmptyStage" then
        stageMgr:ChangeStage(targetStage, stageData)  -- 直接切换，无需 Loading
    -- … 其余 Stage
    end
end

GLDeclare("GotoStage", GotoStage)  -- 注册为全局函数，全工程可直接调用
```

**完整跳转链路**：

```
WorldStage（玩家点击战斗入口）
  └─ GotoStage("BattleStage", battleStageData)
       └─ stageMgr:ChangeStage("LoadingStage", { nextStage="BattleStage", data=... })
            └─ LoadingStage:Enter() → 加载地图场景、战斗资源
                 └─ 加载完成 → stageMgr:ChangeStage("BattleStage", battleStageData)
                      └─ BattleStage:Enter(preStage, data)
```

连续战斗（当前战斗中触发下一场）时，走的是 `EmptyStage` 中转：

```
BattleStage（战斗中触发下一战）
  └─ GotoStage("EmptyStage", { nextStage="BattleStage", ... })
       └─ EmptyStage（短暂清场）→ GotoStage("BattleStage", ...)
```

---

## 3. BattleStage 的职责

### 两个核心对象

`BattleStage` 持有两个通过 `BattleGlobalData` 传入的核心对象：

```lua
-- BattleGlobalData.lua（类型注解）
---@class BattleGlobalData
---@field public battle ClientBattle|nil  -- 客户端战斗对象（表现层）
---@field public logicBattle Battle|nil   -- 逻辑层战斗对象（确定性逻辑）
```

| 字段 | 类型 | 所在目录 | 职责 |
|---|---|---|---|
| `globalData.battle` | `ClientBattle` | `ClientBattle/` | 表现层：渲染、动画、音效、UI 绑定、镜头 |
| `globalData.logicBattle` | `Battle` | `Logic/Battle/` | 逻辑层：伤害计算、状态机、回合管理，SC 服务器同步运行 |

### Enter() 方法解析

`Enter()` 是 BattleStage 的核心初始化入口，它从 `BattleGlobalData` 取出已预先创建好的两个对象，然后根据 `data` 参数决定进入哪个战斗子状态：

```lua
-- BattleStage.lua – Enter()（精简注释版）
function BattleStage:Enter(preStage, data)
    BattleGlobalData.battlePause = false     -- 重置暂停标志

    -- 初始化 C# 侧的 HUD 按钮和伤害数字显示器
    CS.Core.HudButtonManager.Inst:Init()
    CS.Core.HurtTextManager.Inst:Init()

    -- 从全局数据容器取出已创建好的战斗对象
    self.battle      = globalData.battle       -- 表现层（ClientBattle）
    self.logicBattle = globalData.logicBattle  -- 逻辑层（Battle）

    -- 将表现层的事件与 UI 系统绑定
    clientUILogic:BindBattleEvent(self.battle)

    -- 根据参数决定是否跳过布阵阶段
    if data.isSkipArray or self.battle.isSkipArray then
        if data.isPerform then
            -- 回放模式：直接播放战斗录像
            panelMgr:OpenPanel("RoundPanel", function(rp)
                rp:StartBattle(true)
                -- 加载并播放战斗 Perform 数据
            end)
        else
            -- 跳过布阵，直接进入战斗状态
            panelMgr:OpenPanel("BattlePanel", function(pp)
                globalData.logicBattle.mainStateMgr:SetCurState("FieldState")
            end)
        end
    else
        -- 正常流程：先进入布阵状态
        panelMgr:OpenPanel("ArrayPanel", function(p)
            globalData.logicBattle.mainStateMgr:SetCurState("ArrangeState")
        end)
    end
end
```

**关键细节**：`battle` 和 `logicBattle` 在 `Enter()` 被调用前已由 `LoadingStage` 创建并写入 `BattleGlobalData`。`BattleStage` 只是取引用，不负责创建。

### Exit() 的销毁顺序

销毁顺序严格要求：**先关闭 UI 面板（解绑事件），再销毁战斗对象**。

```lua
function BattleStage:Exit(nextStage, targetStage)
    -- 1. 先关闭所有依赖 battle 的面板（面板关闭时会解绑事件监听）
    panelMgr:ClosePanel("ArrayPanel")
    panelMgr:ClosePanel("BattlePanel")
    -- … 其余面板

    -- 2. 停止战斗表现（防止动画访问已销毁数据）
    self.battle:StopFightForce()

    -- 3. 销毁逻辑层（先于表现层）
    self.logicBattle:destroy()
    self.logicBattle = nil

    -- 4. 解绑表现层事件，再销毁表现层
    clientUILogic:UnBindBattleEvent(self.battle)
    self.battle:destroy()
    self.battle = nil

    -- 5. 清理全局引用
    globalData.battle      = nil
    globalData.logicBattle = nil

    -- 6. 清理各资源池和 C# 侧管理器
    fxMgr:Clear()
    SnapDataPool.GetInstance():Clear()
    CS.Core.GridManager.Inst:Close()
    -- …
end
```

### Update() 的驱动顺序

```lua
function BattleStage:Update(dt)
    if globalData.battlePause then return end  -- 暂停时全部跳过

    world:Update(dt)              -- 世界（地图场景中的动态元素）
    GuideManager:Update(dt)       -- 引导系统
    self.logicBattle:Update(dt)   -- 逻辑层：推进状态机、回合计算
    self.battle:Update(dt)        -- 表现层：驱动动画、特效、镜头
    CS.Core.HurtTextManager.Inst:Update(dt)  -- C# 伤害飘字
end
```

逻辑层 Update 先于表现层执行，确保表现层每帧都能读到最新的逻辑状态。

---

## 4. 逻辑层 vs 表现层的分离原则

### 为什么要分离？

本项目的战斗逻辑需要在 **客户端** 和 **服务器（SC 通用代码）** 上同时运行，用于结果验证和反作弊。

```
客户端
  ├─ Logic/Battle/（逻辑层）  ←── 与服务器共享的 Lua 代码
  └─ ClientBattle/（表现层）  ←── 仅客户端，服务器不运行

SC 服务器
  └─ Logic/Battle/（逻辑层）  ←── 同一份代码
```

### 确定性要求

逻辑层代码必须满足**确定性（Deterministic）**：

- 相同输入 + 相同随机种子 → 始终产生相同输出
- **严禁**在逻辑层使用 `math.random()`——必须使用项目封装的隔离随机数对象：

| 随机数对象 | 用途 |
|---|---|
| `battleRandom` | 战斗逻辑（技能命中、伤害浮动）|
| `aiRandom` | AI 决策逻辑 |
| `autoBattleRandom` | 托管（自动战斗）表现随机 |
| `combatRandom` | 对冲表现随机（不影响逻辑结果）|

- **严禁**在逻辑层调用任何渲染/音效 API（`CS.UnityEngine.*` 中的渲染类）
- **严禁**在逻辑层读取 `os.clock()` / `os.time()` 等非确定性系统函数

### 如何区分你在哪一层？

| 判断 | 逻辑层 `Logic/Battle/` | 表现层 `ClientBattle/` |
|---|---|---|
| 能否调用 C# 渲染 API | 不能 | 可以 |
| 能否 `require` 表现层模块 | 不能 | 可以 |
| 服务器是否运行 | 是 | 否 |
| 随机数来源 | `battleRandom` 等隔离对象 | 任意 |

---

## 5. 代码示例：BattleStage 关键代码摘录与注释

### 5.1 类声明与字段

```lua
-- BattleStage.lua
local class     = require("Common.Class")
local StageBase = require("Stage.StageBase")

---@class BattleStage:StageBase
---@field public battle      ClientBattle   -- 表现层对象（BattleGlobalData.battle）
---@field public logicBattle Battle         -- 逻辑层对象（BattleGlobalData.logicBattle）
local BattleStage = class.Class("BattleStage", StageBase, false)
--                                           ↑继承 StageBase  ↑false=非单例

local globalData = BattleGlobalData  -- 使用 LuaGame.lua 注册的全局变量
```

### 5.2 Enter：跳过布阵进入战斗

```lua
-- BattleStage.lua – Enter()（跳过布阵的分支）
panelMgr:OpenPanel("BattlePanel", function(pp)
    -- 直接将逻辑层主状态机设为 FieldState（上场状态）
    globalData.logicBattle.mainStateMgr:SetCurState("FieldState")
end)
```

### 5.3 Enter：正常布阵流程

```lua
-- BattleStage.lua – Enter()（正常布阵分支）
panelMgr:OpenPanel("ArrayPanel", function(p)
    -- 打开布阵面板后，逻辑层进入 ArrangeState（布阵状态）
    globalData.logicBattle.mainStateMgr:SetCurState("ArrangeState")
end)
```

### 5.4 Update：暂停守卫 + 双层驱动

```lua
-- BattleStage.lua – Update()
function BattleStage:Update(dt)
    if globalData.battlePause then
        return  -- 暂停期间所有战斗逻辑和表现均停止更新
    end

    if nil ~= self.logicBattle then
        self.logicBattle:Update(dt)   -- 逻辑层先更新（状态机推进、伤害结算）
    end

    if nil ~= self.battle then
        self.battle:Update(dt)        -- 表现层后更新（读取逻辑结果驱动动画）
        CS.Core.HurtTextManager.Inst:Update(dt)
    end
end
```

### 5.5 连续战斗中转（isJumpToBattleStage）

```lua
-- BattleStage.lua – Update() 内的连续战斗跳转逻辑
if self.isJumpToBattleStage then
    self.isJumpToBattleStage = false
    local id           = self.battle.mainBattleID
    local levelID      = self.battle.logicBattle.levelId
    local gameFuncType = self.battle.logicBattle.gameFuncType
    ---@type BattleStageData
    local bsData = {
        battleId     = id,
        levelid      = levelID,
        gameFuncType = gameFuncType,
        isSkipArray  = isSkipArray,
        nextStage    = "BattleStage",  -- 告知 EmptyStage 目标是 BattleStage
    }
    GotoStage("EmptyStage", bsData)   -- 经 EmptyStage 清场再重新进入 BattleStage
end
```

---

## 6. 练习题

**练习 1（理解架构）**

阅读 `LuaGame.lua` 的 `Update()` 函数，画出每帧从 C# 调用到 `BattleStage:Update()` 再到 `logicBattle:Update()` 的完整调用链。说明每一层的角色和职责。

**练习 2（分析分支）**

在 `BattleStage:Enter()` 中，共有几个进入战斗的分支路径？分别对应什么游戏场景（正常布阵、跳过布阵、回放模式）？每条路径最终将逻辑层状态机设置为哪个状态？

**练习 3（追踪销毁顺序）**

在 `BattleStage:Exit()` 中，`panelMgr:ClosePanel()` 必须在 `self.battle:destroy()` 之前调用。代码注释中给出了原因。请解释：如果顺序反过来（先销毁 battle，再关闭面板），会发生什么问题？结合事件绑定的机制给出分析。

---

## 7. 常见陷阱

### 陷阱 1：在逻辑层调用渲染或时间 API

```lua
-- ❌ 错误示例（Logic/Battle/ 内的某个文件）
function SomeLogicComp:OnHit(target)
    CS.UnityEngine.ParticleSystem.Play()  -- 逻辑层不能触发渲染
    local t = os.time()                   -- 非确定性，服务器与客户端结果不同
end

-- ✅ 正确做法：逻辑层只修改状态，表现层监听事件后触发特效
function SomeLogicComp:OnHit(target)
    target:SetHp(target.hp - damage)
    eventMgr:Send(EventID.ON_HIT, target)  -- 抛事件，表现层自己处理
end
```

### 陷阱 2：直接访问 `globalData.battle` 而不做 nil 检查

`BattleGlobalData.battle` 和 `BattleGlobalData.logicBattle` 在非 BattleStage 期间均为 `nil`（见 `Exit()` 末尾的 `globalData.battle = nil`）。在 WorldStage 或 UI 回调中不加判断直接使用会导致空指针崩溃：

```lua
-- ❌ 错误示例（在某个 Panel 的回调里）
local hp = BattleGlobalData.battle.hero:GetHp()  -- battle 可能已被 Exit() 置 nil

-- ✅ 正确做法
local battle = BattleGlobalData.battle
if battle then
    local hp = battle.hero:GetHp()
end
```

### 陷阱 3：误用 `math.random()` 替代隔离随机数

```lua
-- ❌ 错误示例（Logic/Battle/ 内）
local roll = math.random(1, 100)  -- 全局随机状态，客户端与服务器种子不同步

-- ✅ 正确做法
local roll = battleRandom:NextInt(1, 100)  -- 使用战斗专用随机对象
```

---

## 8. 扩展阅读

| 文件路径 | 内容 |
|---|---|
| `Client/Assets/Script/Lua/LuaGame.lua` | Lua 总入口，所有子系统初始化 |
| `Client/Assets/Script/Lua/Stage/StageManager.lua` | Stage 状态机管理器 |
| `Client/Assets/Script/Lua/Stage/StageBase.lua` | Stage 基类接口定义 |
| `Client/Assets/Script/Lua/Stage/GoToStage.lua` | 全局 `GotoStage` 函数，Stage 跳转路由 |
| `Client/Assets/Script/Lua/Stage/LoadingStage.lua` | 加载过渡 Stage（负责创建 battle/logicBattle） |
| `Client/Assets/Script/Lua/ClientBattle/BattleGlobalData.lua` | 战斗全局数据容器（battle / logicBattle 的持有者） |
| `Client/Assets/Script/Lua/Common/Class.lua` | 项目 OOP 系统（class.Class / AddComponents）|
| `Client/Assets/Script/Lua/Logic/Battle/` | 逻辑层战斗核心（SC 通用代码）|
| `Client/Assets/Script/Lua/ClientBattle/` | 表现层战斗（仅客户端）|
