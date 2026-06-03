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

-- C# 的 XLuaManager 在 Start() 时回调此函数，是整个 Lua 业务层的启动入口
-- C# 调用 Start() 时执行
function Start()
    Init()          -- 初始化所有子系统（EventManager、StageManager、PanelManager 等）
    GotoStage("LoginStage", { mapid = 1 })  -- 跳转登录 Stage，开始状态机
end

-- C# 的 XLuaManager 每帧回调此函数，是 Lua 层的主循环驱动入口
function Update()
    -- 所有每帧驱动均在此集中分发
    local dt = UnityTime.deltaTime            -- 受 Time.timeScale 影响的逻辑帧时间
    timerMgr:update(dt)                       -- 驱动所有定时器/延迟回调
    stageMgr:Update(dt)     -- 当前 Stage 的 Update 从这里触发
    socketManager:update(dt, UnityTime.unscaledDeltaTime)  -- 网络层需要不受暂停影响的真实时间
end

-- C# 的 XLuaManager 在 LateUpdate() 时回调，渲染完成后执行，适合处理摄像机跟随等依赖渲染结果的操作
function LateUpdate()
    stageMgr:LateUpdate()   -- 渲染后处理
end

-- 应用退出时回调，做全局资源释放——面板关闭、事件解绑、子系统销毁
function Close()
    OnClose()  -- 解绑事件、销毁各子系统
end
```

**`Init()` 初始化顺序**（摘自实际代码）：

```lua
-- LuaGame.lua – Init()
-- 先加载并注册全局数据容器，后续模块可能依赖 BattleGlobalData 中的字段
local BattleGlobalData = require("ClientBattle.BattleGlobalData")
GLDeclare("BattleGlobalData", BattleGlobalData)   -- 注册全局战斗数据容器

-- 各子系统按依赖顺序初始化："获取单例 → 调用 init" 是项目约定模式
timerMgr  = TimeManager("ClientGlobal")            -- "ClientGlobal" 是定时器的命名空间，用于分类管理
eventMgr  = EventManager.GetInstance()             -- 事件系统不调用 init（构造时就已完成初始化）
stageMgr  = StageManager.GetInstance(); stageMgr:init()    -- Stage 状态机必须初始化后才能使用
panelMgr  = PanelManager.GetInstance(); panelMgr:init()    -- 面板管理器需在 Stage 之前就绪
socketManager = require("Net.LuaSocketManager").GetInstance(); socketManager:init()  -- 网络模块通过 require 按需加载
-- … 其余子系统依次初始化
```

`GLDeclare` 是项目封装的全局变量声明函数（见 `Common/Global.lua`），用于将单例注册为全局可访问变量，同时保证不被重复赋值。

---

## 2. Stage 状态机

### StageManager 的核心逻辑

`Client/Assets/Script/Lua/Stage/StageManager.lua` 是一个单例，持有唯一的 `curStage` 引用，并在 `ChangeStage` 时做旧 Stage 的销毁和新 Stage 的创建：

```lua
-- StageManager.lua
-- 核心方法：先销毁旧 Stage，再创建新 Stage，保证同一时刻只有一个活跃 Stage
function StageManager:ChangeStage(stageName, data)
    -- 定义为局部闭包以捕获 stageName/data，避免作为回调传递时额外打包参数
    local function changeStage()
        local preStage = ''
        if nil ~= self.curStage then             -- Lua 惯用写法：nil ~= x 而非 x ~= nil
            preStage = self.curStage.name
            self.curStage:Exit(stageName, data)   -- 通知旧 Stage 退出
            self.curStage:destroy()               -- 销毁旧 Stage
        end
        self.curStage = nil                       -- 显式置 nil 防止悬空引用
        local cls = require("Stage." .. stageName) -- 按名称动态加载，支持热更时按需 require
        local newStage = cls()                     -- 实例化新 Stage
        self.curStage = newStage
        newStage:Enter(preStage, data)             -- 进入新 Stage
    end
    -- 切换到 LoadingStage 时需先打开 Loading 面板（遮挡画面）
    -- OpenPanel 加载完面板后回调 changeStage，保证加载界面已显示再执行耗时操作
    if stageName == "LoadingStage" then
        panelMgr:OpenPanel("LoadingPanel", changeStage, stageName, 3)
    else
        changeStage()                              -- 非 LoadingStage 直接切换，无需过渡面板
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
-- 所有 Stage 切换的统一路由：根据目标 Stage 类型决定是否需要 Loading 过渡
local function GotoStage(targetStage, stageData)
    -- 记录跳转日志，短路求值避免 stageData 为 nil 时访问 .nextStage 崩溃
    log(string.format("GotoStage %s %s", targetStage, stageData and stageData.nextStage))
    if targetStage == "BattleStage" then
        -- 必须经过 LoadingStage 加载地图资源，再跳转 BattleStage
        stageMgr:ChangeStage("LoadingStage", { data = stageData, nextStage = targetStage })
    elseif targetStage == "WorldStage" then
        -- WorldStage 场景资源重，同样需要 Loading 过渡
        stageMgr:ChangeStage("LoadingStage", { data = stageData, nextStage = targetStage })
    elseif targetStage == "LoginStage" or targetStage == "EmptyStage" then
        -- Login/Empty 是轻量 Stage，无需 Loading 面板，直接切换
        stageMgr:ChangeStage(targetStage, stageData)  -- 直接切换，无需 Loading
    -- … 其余 Stage
    end
end

-- 注册为全局函数后，全工程任意位置均可直接调用 GotoStage(xxx)，无需 require
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
-- EmmyLua 类型注解：三横线 --- 开头是类型注解，双横线 -- 是普通注释，二者不可混淆
---@class BattleGlobalData                       -- 声明一个类，供 IDE 类型检查和自动补全
---@field public battle ClientBattle|nil  -- 客户端战斗对象（表现层），竖线 |nil 表示可为空
---@field public logicBattle Battle|nil   -- 逻辑层战斗对象（确定性逻辑），非 BattleStage 期间为 nil
```

| 字段 | 类型 | 所在目录 | 职责 |
|---|---|---|---|
| `globalData.battle` | `ClientBattle` | `ClientBattle/` | 表现层：渲染、动画、音效、UI 绑定、镜头 |
| `globalData.logicBattle` | `Battle` | `Logic/Battle/` | 逻辑层：伤害计算、状态机、回合管理，SC 服务器同步运行 |

### Enter() 方法解析

`Enter()` 是 BattleStage 的核心初始化入口，它从 `BattleGlobalData` 取出已预先创建好的两个对象，然后根据 `data` 参数决定进入哪个战斗子状态：

```lua
-- BattleStage.lua – Enter()（精简注释版）
-- 战斗 Stage 的初始化入口——取引用、绑事件、根据参数分流到不同子状态
function BattleStage:Enter(preStage, data)
    BattleGlobalData.battlePause = false     -- 重置暂停标志，确保每次进入战斗默认不暂停

    -- 初始化 C# 侧的 HUD 按钮和伤害数字显示器（CS. 前缀通过 xLua 桥接访问 C# 类）
    CS.Core.HudButtonManager.Inst:Init()
    CS.Core.HurtTextManager.Inst:Init()

    -- 从全局数据容器取出已创建好的战斗对象（LoadingStage 负责创建，这里只取引用）
    self.battle      = globalData.battle       -- 表现层（ClientBattle）
    self.logicBattle = globalData.logicBattle  -- 逻辑层（Battle）

    -- 将表现层的事件与 UI 系统绑定，绑定后才可响应面板回调中的事件通知
    clientUILogic:BindBattleEvent(self.battle)

    -- 根据参数决定进入哪个战斗子状态——共三条分支路径
    if data.isSkipArray or self.battle.isSkipArray then   -- 跳过布阵：data 或 battle 对象均可标记
        if data.isPerform then
            -- 回放模式：直接播放战斗录像，不创建逻辑层状态机
            panelMgr:OpenPanel("RoundPanel", function(rp)
                rp:StartBattle(true)           -- 参数 true 表示回放模式（跳过布阵+跳过输入）
                -- 加载并播放战斗 Perform 数据
            end)
        else
            -- 跳过布阵分支：直接进入上场战斗状态（如竞技场、PVP 等无需布阵的场景）
            panelMgr:OpenPanel("BattlePanel", function(pp)
                globalData.logicBattle.mainStateMgr:SetCurState("FieldState")  -- 直接切换到上场状态
            end)
        end
    else
        -- 正常流程：先打开布阵面板，再进入 ArrangeState（布阵状态）
        panelMgr:OpenPanel("ArrayPanel", function(p)
            globalData.logicBattle.mainStateMgr:SetCurState("ArrangeState")  -- 进入布阵状态
        end)
    end
end
```

**关键细节**：`battle` 和 `logicBattle` 在 `Enter()` 被调用前已由 `LoadingStage` 创建并写入 `BattleGlobalData`。`BattleStage` 只是取引用，不负责创建。

### Exit() 的销毁顺序

销毁顺序严格要求：**先关闭 UI 面板（解绑事件），再销毁战斗对象**。

```lua
-- 销毁顺序严格遵循"面板 → 表现 → 逻辑 → 全局引用 → 资源池"的依赖链，逆序于构造过程
function BattleStage:Exit(nextStage, targetStage)
    -- 1. 先关闭所有依赖 battle 的面板（面板关闭时会解绑事件监听，防止后续 destroy 触发面板回调）
    panelMgr:ClosePanel("ArrayPanel")
    panelMgr:ClosePanel("BattlePanel")
    -- … 其余面板

    -- 2. 停止战斗表现（强制终止所有动画/特效播放，防止访问已销毁数据）
    self.battle:StopFightForce()

    -- 3. 先销毁逻辑层——逻辑层依赖较少，表现层 destructor 可能仍查询逻辑层状态
    self.logicBattle:destroy()
    self.logicBattle = nil                       -- 显式置 nil 防止悬空引用被误用

    -- 4. 解绑表现层事件后再销毁——事件回调可能引用 battle 自身字段
    clientUILogic:UnBindBattleEvent(self.battle)
    self.battle:destroy()
    self.battle = nil

    -- 5. 清理全局引用，确保非 BattleStage 期间访问 globalData.battle 返回 nil
    globalData.battle      = nil
    globalData.logicBattle = nil

    -- 6. 清理各资源池和 C# 侧管理器——释放特效对象池、快照数据、网格系统
    fxMgr:Clear()
    SnapDataPool.GetInstance():Clear()
    CS.Core.GridManager.Inst:Close()
    -- …
end
```


### Update() 的驱动顺序

```lua
-- 每帧驱动顺序：世界 → 引导 → 逻辑 → 表现 → C# 飘字，前层可能影响后层行为
function BattleStage:Update(dt)
    if globalData.battlePause then return end  -- 暂停时全部跳过，包括逻辑和表现

    world:Update(dt)              -- 世界（地图场景中的动态元素），先于战斗逻辑更新
    GuideManager:Update(dt)       -- 引导系统。引导可能拦截输入，需在逻辑层之前判断
    self.logicBattle:Update(dt)   -- 逻辑层：推进状态机、回合计算，产出本帧逻辑状态
    self.battle:Update(dt)        -- 表现层：驱动动画、特效、镜头，消费逻辑层产出的状态
    CS.Core.HurtTextManager.Inst:Update(dt)  -- C# 伤害飘字，依赖本帧逻辑层的伤害结果
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
-- 加载项目的 OOP 基础设施：Class 提供类创建，StageBase 提供 Stage 生命周期接口
local class     = require("Common.Class")
local StageBase = require("Stage.StageBase")

-- EmmyLua 类型注解：声明 BattleStage 继承 StageBase，IDE 可获得基类的字段/方法提示
---@class BattleStage:StageBase
---@field public battle      ClientBattle   -- 表现层对象（BattleGlobalData.battle）
---@field public logicBattle Battle         -- 逻辑层对象（BattleGlobalData.logicBattle）
local BattleStage = class.Class("BattleStage", StageBase, false)
--                    类名用于调试 ↑         ↑基类    ↑false=非单例，允许多个实例并存

-- GLDeclare 注册的全局变量，通过全局名称直接访问，无需 require
local globalData = BattleGlobalData  -- 使用 LuaGame.lua 注册的全局变量
```

### 5.2 Enter：跳过布阵进入战斗

```lua
-- BattleStage.lua – Enter()（跳过布阵的分支）
-- 打开 BattlePanel 后在其回调中切换状态——保证面板初始化完毕后状态机才推进
panelMgr:OpenPanel("BattlePanel", function(pp)
    -- 直接将逻辑层主状态机设为 FieldState（上场状态），跳过 ArrangeState
    globalData.logicBattle.mainStateMgr:SetCurState("FieldState")
end)
```

### 5.3 Enter：正常布阵流程

```lua
-- BattleStage.lua – Enter()（正常布阵分支）
-- 先打开 ArrayPanel（布阵 UI），面板就绪后回调中才切换逻辑层状态
panelMgr:OpenPanel("ArrayPanel", function(p)
    -- 打开布阵面板后，逻辑层进入 ArrangeState（布阵状态），等待玩家操作
    globalData.logicBattle.mainStateMgr:SetCurState("ArrangeState")
end)
```

### 5.4 Update：暂停守卫 + 双层驱动

```lua
-- BattleStage.lua – Update()
-- 双重守卫：暂停开关 + nil 检查，保证在各种边界条件下都不会崩溃
function BattleStage:Update(dt)
    if globalData.battlePause then
        return  -- 暂停期间所有战斗逻辑和表现均停止更新
    end

    -- nil ~= 是防御性检查：连续战斗的 EmptyStage 清场期间这两个字段为 nil
    if nil ~= self.logicBattle then
        self.logicBattle:Update(dt)   -- 逻辑层先更新（状态机推进、伤害结算）
    end

    if nil ~= self.battle then
        self.battle:Update(dt)        -- 表现层后更新（读取逻辑结果驱动动画）
        CS.Core.HurtTextManager.Inst:Update(dt)  -- 飘字依赖 battle 的动画状态，故放在其后
    end
end
```

### 5.5 连续战斗中转（isJumpToBattleStage）

```lua
-- BattleStage.lua – Update() 内的连续战斗跳转逻辑
-- isJumpToBattleStage 由外部模块（如结算面板）置 true，触发"当前战斗结束 → 下一场战斗"
if self.isJumpToBattleStage then
    self.isJumpToBattleStage = false       -- 立即复位标志，防止本帧重复触发跳转
    -- 在调用 GotoStage 之前提取所有数据——GotoStage 会触发 Exit() 将 self.battle 置 nil
    local id           = self.battle.mainBattleID
    local levelID      = self.battle.logicBattle.levelId
    local gameFuncType = self.battle.logicBattle.gameFuncType
    ---@type BattleStageData                -- EmmyLua 类型注解，标注此 table 的结构
    local bsData = {
        battleId     = id,
        levelid      = levelID,
        gameFuncType = gameFuncType,
        isSkipArray  = isSkipArray,
        nextStage    = "BattleStage",  -- 告知 EmptyStage 清场后目标为 BattleStage
    }
    GotoStage("EmptyStage", bsData)   -- 经 EmptyStage 清场再重新进入 BattleStage，避免资源累积
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
-- 逻辑层跑在服务器上用于反作弊验证，任何非确定性调用都会导致客户端/服务器结果分歧
function SomeLogicComp:OnHit(target)
    CS.UnityEngine.ParticleSystem.Play()  -- 逻辑层不能触发渲染——服务器没有 Unity 引擎
    local t = os.time()                   -- 非确定性，服务器与客户端结果不同，会导致验证失败
end

-- ✅ 正确做法：逻辑层只修改状态，表现层监听事件后触发特效
-- 事件驱动解耦：逻辑层不知道也不关心谁会响应 ON_HIT 事件
function SomeLogicComp:OnHit(target)
    target:SetHp(target.hp - damage)          -- 仅修改纯数据状态，客户端和服务器得到相同结果
    eventMgr:Send(EventID.ON_HIT, target)  -- 抛事件，表现层自己处理（播特效、飘字等）
end
```

### 陷阱 2：直接访问 `globalData.battle` 而不做 nil 检查

`BattleGlobalData.battle` 和 `BattleGlobalData.logicBattle` 在非 BattleStage 期间均为 `nil`（见 `Exit()` 末尾的 `globalData.battle = nil`）。在 WorldStage 或 UI 回调中不加判断直接使用会导致空指针崩溃：

```lua
-- ❌ 错误示例（在某个 Panel 的回调里）
-- 链式访问不作 nil 检查：battle 为 nil 时访问 .hero 直接抛异常
local hp = BattleGlobalData.battle.hero:GetHp()  -- battle 可能已被 Exit() 置 nil

-- ✅ 正确做法：先缓存引用再判 nil——避免 TOCTOU 问题（两次读取间 battle 被置 nil）
local battle = BattleGlobalData.battle            -- 先缓存到局部变量，保证判 nil 和使用的引用一致
if battle then
    local hp = battle.hero:GetHp()               -- 只在确认非 nil 后才访问
end
```

### 陷阱 3：误用 `math.random()` 替代隔离随机数

```lua
-- ❌ 错误示例（Logic/Battle/ 内）
-- math.random 使用全局 Lua 随机状态，客户端和服务器序列不同，导致伤害/命中结果不一致
local roll = math.random(1, 100)  -- 全局随机状态，客户端与服务器种子不同步

-- ✅ 正确做法：使用战斗专用隔离随机对象——种子由服务器下发，保证双端一致
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
