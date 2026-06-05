---
title: "教程 10：战斗校验、快进与悔棋"
updated: 2026-06-05
---

# 教程 10：战斗校验、快进与悔棋

## 前置依赖

- 教程 02：Battle 类与组件系统（BattleLogicComp / BattleTurnComp）
- 教程 03：状态机与回合流程
- 教程 05：BattleHero 实体

---

## 1. 战斗确定性要求

战棋 RPG 的服务器校验依赖一个核心假设：**给定相同输入，战斗计算结果完全可复现**。这被称为确定性（Determinism）。

### 为什么必须确定性？

校验流程是：
1. 客户端完成战斗 → 将初始状态 + 操作序列发给服务器
2. 服务器用同一份逻辑代码**重放**所有操作
3. 比对服务器计算的结果与客户端上报的结果

若战斗不确定，重放结果将与客户端不同，校验永远失败。

### 确定性的具体禁止项

| 禁止项 | 原因 |
|--------|------|
| `math.random()` 不可控调用 | 随机数序列必须由 `initRandomSeed` 完全决定 |
| `os.time()` / `os.clock()` 影响逻辑分支 | 时间值每次不同 |
| Lua table 遍历（`pairs`）无序依赖 | Lua hash 表遍历顺序不保证稳定 |
| 浮点运算直接比较 | 平台差异，改用 `ScaleUp` 整数放大运算 |
| 客户端专属副作用写入逻辑状态 | `isClient` 分支只能触发表现，不能改变逻辑数值 |

---

## 2. cmdList 记录机制

### BattleLogicComp 的核心字段

```lua
-- BattleLogicComp.lua
-- 构造函数：初始化战斗校验数据管道所需的全部核心字段
-- 客户端填充 → 战斗结束时随 endnowbattleReq 发送 → 服务器重放校验
function BattleLogicComp:ctor()
    self.clientBattle   = nil   -- 逻辑消息接收器（表现层引用）
    self.performMgr     = nil
    -- 表现播放管理器：控制技能动画与特效队列，纯客户端表现，不参与校验计算
    self.triggerActionMgr = nil
    self.heroNurtureData  = {}  -- 将领养成数据（校验时发服务器）
    self.battleBasicInfo  = nil -- 战斗基本信息（校验时发服务器）
    self.cmdList          = {}  -- 操作指令列表（校验时发服务器）
    self.cmdMaps          = {}  -- step -> BattleCommand 索引，快进时查找用
    self.gainHideTreasure = {}
    -- 隐藏宝箱获取列表：校验阶段对比客户端与服务器重放结果是否一致
    self.opCmdPool        = {}  -- 操作命令对象池，减少 GC
    self.commandMgr       = nil -- CoreLib.CommandManager，持久化写入
end
```

### BattleCommand 结构

每条 BattleCommand 是一个 Lua table，核心字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| `cmd` | `Enum.Command` | 操作类型（UseSkill / UseBFSkill / Wait / BuffInteraction / …） |
| `turnId` | integer | 所属回合 ID |
| `step` | integer | 操作步数（全局单调递增，悔棋的主键） |
| `attackerId` | integer | 发起操作的英雄 ID |
| `skillId` | integer | 技能 ID（UseSkill/UseBFSkill 有效） |
| `endX / endY` | integer | 移动目标格坐标 |
| `moveGridCount` | integer | 实际移动格数 |
| `leftRegretCount` | integer | 操作发生时剩余悔棋次数（快进恢复用） |

### 写入时机

每次操作完成（技能命中结算后）才写入，不是操作发起时。以 `DoUseSkill` 为例：

```lua
-- BattleLogicComp.lua : DoUseSkill
-- 技能结算完成后的回调：此时所有伤害/状态变更已确定，写入结果才可复现
local function onSkillCompleted()
-- 三重守卫条件：仅客户端或悔棋模式 → 且允许记录 → 且非剧情播放中
    if (self.isClient or self.isRegretMode) and isSaveCmd then
        if not self.isPlayPerform then
-- 构造操作指令快照：记录本次技能的全部上下文，使服务器可精确重现
            local cmdData = {
                cmd            = Enum.Command.UseSkill,
                turnId         = self.turnId,
                step           = self.operationStep,
                attackerId     = attackerId,
                endX           = endX, endY = endY,
                moveGridCount  = moveGridCount,
                defenderId     = defenderId,
                skillId        = skillId,
                leftRegretCount = self.leftRegretCount,
            }
-- 同时写入内存列表（网络发送用）和持久化存储（闪退恢复用）
            table.insert(self.cmdList, cmdData)      -- 追加到列表
            if self.commandMgr ~= nil then
                local data = cmsgpack.pack(cmdData)
                self.commandMgr:AddCmd(data)         -- 持久化写入
            end
        end
    end
    if callback ~= nil then callback() end
end
```

`DoWait` 和 `DoUseBFSkill` 采用完全相同的模式：条件 `(isClient or isRegretMode) and isSaveCmd and not isPlayPerform` 保证只在需要记录的模式下写入。

---

## 3. 战斗校验流程

战斗结束（胜利）时，`BattleTurnComp` 构造 `endnowbattleReq` 发送给服务器：

```lua
-- BattleTurnComp.lua（胜利分支）
-- 从连接池获取可复用请求表，构造战斗结束校验请求
local req = socketManager:getReqTable()
req.result            = 1
req.roleid            = self.scWorldHeroManager.scPlayerData4Battle.roleid
-- 代码版本三元组：服务器校验前先比对版本，不一致则跳过校验
req.strSCVersion      = SCVersion         -- 代码版本号
req.strSCMd5          = SCMd5             -- 公共代码 MD5
req.strGAMEDATA_VERSION = GAMEDATA_VERSION
-- 校验核心三要素：英雄初始状态 + 战斗环境 + 完整操作序列
req.heroNurtureData   = self.heroNurtureData   -- 将领养成数据
req.battleBasicInfo   = self.battleBasicInfo   -- 地图/关卡信息
req.battleCommands    = self.cmdList           -- 完整操作序列
-- 校验比对目标：剩余血量、星级、宝箱、得分
req.remainEntityHp    = self:GetRemainEntityHp()
req.finishstar        = self.battleCollectResultData.finishstar
req.gainbox           = self.gainHideTreasure
req.score             = score
```

失败时，`battleCommands` / `heroNurtureData` / `battleBasicInfo` 均为 `nil`，服务器不做战斗校验，只记录失败。

**服务器校验步骤**：
1. 从 `battleBasicInfo.initRandomSeed` 恢复随机数发生器
2. 用 `heroNurtureData` 初始化将领属性
3. 按 `battleCommands` 顺序调用同一套 `BattleLogicComp:RunCommand()`
4. 对比最终 `remainEntityHp`、星级、宝箱等

---

## 4. SC 代码一致性验证

### SCMd5 / SCMd5ThisTime

```lua
-- BattleTurnComp.lua 开头（第 17-29 行）
-- (1) 内网开发环境下，客户端代码频繁改变，改变后公共代码就跟服务器不一致了
-- (2) 所以：客户端用 SCMd5ThisTime，服务器端用 SCMd5
-- 在 Unity 客户端中点开始游戏后，会重新计算公共代码的 md5，并生成 SCMd5ThisTime
-- 通过比对 SCMd5ThisTime 和 SCMd5 来判断：SC 公共代码是否一致
-- 如果不一致，就没必要浪费时间看战斗校验异常的问题
-- (3) 服务器上没有必要用 SCMd5ThisTime，也没有这个文件
local SCMd5 = require("SCMd5")
-- 客户端/服务器分支：客户端运行时使用重算的 MD5，服务器使用打包时的静态 MD5
if macroIsClient then
    SCMd5 = require("SCMd5ThisTime")   -- 运行时重算的 MD5
end
```

- **`SCMd5`**（静态文件）：上次打包时生成，代表"预期"的公共代码版本
- **`SCMd5ThisTime`**（运行时生成）：每次启动 Unity 客户端时重新计算所有 SC（Shared Code）文件的 MD5
- 两者不一致 → 本地代码改动未提交/打包 → 战斗校验结果不可信，先对齐代码再排查

### CMd5GameDataThisTime

```lua
-- BattleTurnComp.lua 第 31-38 行
-- 用途：本地对同 1 份战报快进执行时，可能用了不同的 GameData 配置
-- 此时，需要比对这个值（不是用来比对客户端和服务器配置的）
-- 默认值全零：服务器端不需要此值；客户端启动时动态计算并覆盖
local CMd5GameDataThisTime = "00000000000000000000000000000000"
-- 仅在客户端运行时重新计算 GameData 的 MD5，用于本地战报回放时检测配置版本差异
if macroIsClient then
    CMd5GameDataThisTime = require("CMd5GameDataThisTime")
end
```

场景：开发者拿到一份战报（`.bin`），在不同版本的配置表下分别快进，结果不一致 → 通过比对 `CMd5GameDataThisTime` 快速定位配置变化。

---

## 5. 快进 / 战报回放

### isRegretMode 标志

`isRegretMode = true` 表示当前处于**快进重放**状态（悔棋和战报回放共用此标志）。该状态下：

- `cmdList` 写入仍然开启（`isSaveCmd` 默认 true，且条件 `isClient or isRegretMode` 满足）
- `clientBattle` 通知被抑制（`StartRegret` 中 `self.isClient = false`）
- 表现层跳过（`isSkipDisplay = GameSetting.isSkipDisplay`）

### 重放过程

`RebuildBattle` 是快进的核心：

```lua
-- BattleRegretComp.lua
function BattleRegretComp:RebuildBattle(basicBattleInfo, cmdList, toStep, ...)
-- 清空当前战场状态，准备从头重建
    self:clear()
    self.regretStep = toStep or 1
-- 构建 step→命令 索引表：快进时 O(1) 查找，避免每帧线性扫描 cmdList
    self.cmdMaps, self.triggerActionCmdMaps,
    self.buffInterCmdMaps, self.dialogChoiceMaps = self:BuildCmdMap(cmdList)

    -- 用原始随机种子重启战斗
    self:StartBattleWithFast(basicBattleInfo.initRandomSeed)

-- IntervalTime 从毫秒转秒：CombatConfig 定义常量，用除法避免浮点累积误差
    local intervalTime = CombatConfig.IntervalTime / 1000
-- 主循环：逐帧推进逻辑直到到达目标步数或超时
    while true do
        self:Update(intervalTime)          -- 推进逻辑帧
-- 到达目标步数后，等待当前剧情/动画播完再退出，保证状态完整
        if self.isStopRegret then
            if not (self.triggerActionMgr.isPlaying
                    or self.performMgr.isPlaying) then
                break                      -- 到达目标步数且无剧情播放
            end
        end
-- 30 秒超时保护：防止死循环（如 buff 相互触发）导致快进永久挂起
        if (os.clock()*1000 - t1) > 30*1000 then break end  -- 超时保护
    end
end
```

**随机数重建的重要性**：`StartBattleWithFast(initRandomSeed)` 用完全相同的种子重置随机数发生器。若种子不一致，技能伤害、暴击等所有随机结果将偏离，导致快进后状态与原战斗不同，悔棋得到错误的战场状态。

### BuildCmdMap 索引构建

快进时不线性扫描 `cmdList`，而是先建索引：

```lua
-- BattleRegretComp.lua : BuildCmdMap
-- 线性遍历 cmdList 一次，按命令类型分派到不同的索引表
for i = 1, #cmdList do
    local d = cmdList[i]
-- 主操作命令（技能/等待）：step 为全局唯一主键，直接映射
    if d.cmd == UseSkill or d.cmd == UseBFSkill or d.cmd == Wait then
        tmpCmdMaps[d.step] = d            -- step -> 主操作
        -- 同时从 leftRegretCount 恢复剩余悔棋次数
-- 从 Record 命令中恢复剩余悔棋次数：取历史最大值，确保次数不因回退而虚增
        if d.leftRegretCount > self.leftRegretCount then
            self.leftRegretCount = d.leftRegretCount
        end
    elseif d.cmd == RunTriggerAction then
        triggerActionCmdMaps[d.step] = d
-- Buff 交互使用复合键 (ownerId, buffId)：同一回合同一英雄可有多个 buff 同时交互
    elseif d.cmd == BuffInteraction then
-- 位运算合成 32 位键：高 16 位 ownerId，低 16 位 buffId，保证唯一性
        local key = (d.ownerId << 16) | d.buffId
        buffInterCmdMaps[d.turnId][key] = d
    elseif d.cmd == DialogChoice then
        table.insert(dialogChoiceMaps[d.turnId], d)
    end
end
```

---

## 6. 悔棋实现

### BattleRegretComp 字段

| 字段 | 含义 |
|------|------|
| `isRegretMode` | 当前处于悔棋重放中 |
| `readyToRegret` | 准备进入悔棋（中断我方托管） |
| `backCmdList` | 本次悔棋前的 cmdList 快照 |
| `curRegretStep` | 目标悔棋步数 |
| `leftRegretCount` | 剩余悔棋次数（由 `SaveRecordCommand` 写入 cmdList） |
| `isRebuilding` | 防止重入死循环 |
| `isSkipDisplay` | 快进时跳过战斗表现 |

### RegretToStep：悔棋到指定步

```lua
-- BattleRegretComp.lua
-- 悔棋核心入口：将战场回退到指定 step，然后玩家可从此步重新操作
function BattleRegretComp:RegretToStep(toStep)
-- 防重入守卫：isRebuilding 为 true 时说明上一次重建尚未完成，直接拒绝
    if self.isRebuilding then
        logError("RegretToStep blocked: preventing infinite loop")
        return
    end
    self.isRebuilding = true

    -- 1. 快照当前 cmdList → backCmdList
-- 浅拷贝 cmdList 引用：备份原列表以便重建，后续 cmdList 将被新的操作覆盖
    self.backCmdList = {}
    for i = 1, #self.cmdList do
        self.backCmdList[i] = self.cmdList[i]
    end

    -- 2. 持久化备份（CopyToBack）并清空当前记录
    if self.isClient and self.commandMgr ~= nil then
        self.commandMgr:CopyToBack(string.format("Count-%d", self.leftRegretCount))
        self.commandMgr:ClearCmds()
    end

-- StartRegret 设 isRegretMode=true / isClient=false，屏蔽表现层通知
-- RebuildBattle 用备份的 cmdList 快进到 toStep 之前
-- StopRegret 恢复 isRegretMode=false / isClient=true
    -- 3. 快进重建到 toStep 之前的状态
    self.curRegretStep = toStep
    local battleBasicInfo = self.battleBasicInfo
    self:StartRegret()    -- isRegretMode=true, isClient=false
    self:RebuildBattle(battleBasicInfo, self.backCmdList, toStep, false, true, self.isPvp)
    self:StopRegret()     -- isRegretMode=false, isClient=true

    -- 4. 刷新客户端表现层
-- 清空客户端表现对象：快进期间表现被跳过，重建后需从当前状态重新渲染
    if self.isClient and nil ~= self.clientBattle then
        self.clientBattle:clear()
    end
    self:StartBattle(false)
    self.isRebuilding = false
end
```

**leftRegretCount 限制**：`RebuildBattle` 中 `isManual=true` 时执行 `self.leftRegretCount - 1`，次数归零后依然可以快进，但不再扣减（`< 0` 时钳位为 0）。UI 层根据 `leftRegretCount == 0` 禁用悔棋按钮。

### SaveRecordCommand：悔棋存档点

每次我方完成一个完整操作后调用，将当时的 `leftRegretCount` 写入 `cmdList`：

```lua
-- 在 cmdList 中插入一个 Record 类型的存档点标记
-- 此标记不参与战斗逻辑，仅供快进时恢复 leftRegretCount 使用
function BattleRegretComp:SaveRecordCommand()
    local cmdData = {
        cmd             = Enum.Command.Record,
        turnId          = self.turnId,
        step            = self.operationStep,
-- 记录此时的剩余悔棋次数：快进重建到此步时，从此值恢复，而非重新计数
        leftRegretCount = self.leftRegretCount,
    }
    table.insert(self.cmdList, cmdData)
    if self.commandMgr ~= nil then
        self.commandMgr:AddCmd(cmsgpack.pack(cmdData))
    end
end
```

快进时 `BuildCmdMap` 读取 `Record` 类型命令来恢复 `leftRegretCount`，确保悔棋次数不被重放过程重置。

---

## 7. 客户端就地校验

`isClientBattleVerify` 是开发阶段的调试开关：

```lua
-- BattleTurnComp.lua ctor
-- 客户端本地战斗校验开关：默认关闭，仅开发调试时手动打开
self.isClientBattleVerify = false
```

启用时（`true`），`StopBattle` 路径中：

```lua
-- 校验模式下保持网络连接活跃，确保 MockBattleVerifyServer 可接收数据
if self.isClient and self.isClientBattleVerify == true then
    socketManager.isCheckConnect = true
end
-- ...
-- 三重条件：调试模式 + 客户端 + 校验开关；满足时才加载本地模拟服务器
if self.debug and macroIsClient == true and self.isClientBattleVerify == true then
-- 延迟加载 Server.GameServer：避免正常流程引入服务器依赖
    if MockBattleVerifyServer == nil then
        MockBattleVerifyServer = require("Server.GameServer")
    end
    -- 在客户端进程内模拟服务器校验逻辑
-- 在客户端进程中调用服务器端的战斗重建入口，使用同一份 cmdList 重放并比对
    MockBattleVerifyServer.ClientBattleRebuildStart(
        nil,
        self.scWorldHeroManager.scPlayerData4Battle.roleid,
        BattleGlobalData.clientBattleIndex
    )
end
```

**用途**：不依赖真实服务器，在本地直接 require `Server.GameServer`，用同一份 cmdList 重跑一遍战斗逻辑，比对结果。主要用于：
- 排查悔棋快进后战场状态不一致
- 验证新技能/新 buff 是否破坏确定性
- CI 环境下的自动化战斗回归测试

---

## 8. 代码摘录

### BattleTurnComp.lua 第 1-38 行：SC 一致性验证

```lua
-- BattleTurnComp.lua
-- 编译期写入的版本常量：每次打包时由构建系统生成
local SCVersion = require("SCVersion")
local GAMEDATA_VERSION = require("GameData.GAMEDATA_VERSION")

-- 客户端 用 SCMd5ThisTime；服务器端 用 SCMd5
-- Unity 启动后重新计算公共代码 md5 → SCMd5ThisTime
-- 两者不一致说明本地代码未同步，战斗校验异常不必排查
local SCMd5 = require("SCMd5")
local MockBattleVerifyServer = nil
local socketManager = nil
-- 仅在客户端进程中重写这些全局变量：服务器端保持 require 的静态值不变
if macroIsClient then
    SCMd5 = require("SCMd5ThisTime")
    socketManager = require("Net.LuaSocketManager").GetInstance()
end

-- 本地运行时 GameData 配置 md5
-- 用途：同一份战报在不同配置版本下快进，比对此值定位配置变化
local CMd5GameDataThisTime = "00000000000000000000000000000000"
if macroIsClient then
    CMd5GameDataThisTime = require("CMd5GameDataThisTime")
end
```

### BattleLogicComp.lua ctor：核心数据结构

```lua
-- BattleLogicComp.lua
-- 战斗逻辑组件构造：所有字段共同构成战斗校验的完整数据快照
function BattleLogicComp:ctor()
    self.clientBattle     = nil   -- 表现层引用（逻辑通知接收器）
    self.performMgr       = nil
    -- 表现管理器：驱动技能动画/特效序列，不影响逻辑运算
    self.triggerActionMgr = nil
    self.heroNurtureData  = {}    -- 上阵将领养成数据（发服务器）
    self.battleBasicInfo  = nil   -- 战斗基本信息（发服务器）
    self.cmdList          = {}    -- 操作指令序列（发服务器）
    self.cmdMaps          = {}    -- step -> BattleCommand（快进查找）
    self.gainHideTreasure = {}
    -- 隐藏宝箱：战斗中获取的宝箱列表，校验时比对获取一致性
    self.opCmdPool        = {}    -- 命令对象池
    -- 对象池复用 table：频繁创建 cmdData 时避免 Lua GC 尖峰
    self.commandMgr       = nil   -- 持久化写入管理器
end
```

---

## 9. 练习题

**题目一**：当玩家执行悔棋后，`cmdList` 中仍保留了悔棋前的所有指令。服务器校验时如何区分"悔棋前的旧操作"和"悔棋后玩家重新操作"的指令？请从 `BattleRegretComp:RegretToStep` 的实现中找到答案。

**题目二**：假设你在实现一个新的"特殊触发技能"，技能触发时需要记录一条自定义 `BattleCommand`。参考 `DoUseSkill` 的实现，写出正确的写入代码，并说明为什么必须在技能结算**完成后**才能调用 `table.insert(self.cmdList, cmdData)`，而不是在技能**发起时**写入。

**题目三**：测试环境中，一名开发者发现启用 `isClientBattleVerify` 后，战斗校验偶发性失败，但去掉后正常。他检查了 `SCMd5ThisTime == SCMd5` 和 `CMd5GameDataThisTime` 均一致。请列举至少两种可能导致此问题的代码模式，并说明如何定位。

---

## 10. 常见陷阱

**陷阱 1：在 isPlayPerform 为 true 时写入 cmdList**

剧情播放（`isPlayPerform = true`）期间不应写入任何操作指令。`DoUseSkill` 和 `DoWait` 都有 `if not self.isPlayPerform then` 保护。如果新增操作忘记这个检查，剧情中的假操作会混入 `cmdList`，服务器重放时对应帧无英雄行动，导致 `step` 错位。

**陷阱 2：悔棋后 leftRegretCount 不正确**

`leftRegretCount` 由 `BuildCmdMap` 从 `Record` 命令中恢复。如果 `SaveRecordCommand` 调用时机不对（如回合结束前少调一次），快进后 `leftRegretCount` 会偏低，玩家实际还有次数却显示为 0。

**陷阱 3：RebuildBattle 超时保护触发**

```lua
-- 超时保护：t1 为循环开始时间，30 秒后强制退出防止死循环挂起进程
if (t2 - t1) > 30 * 1000 then break end
```

若战斗逻辑中有死循环（如 buff 相互触发循环），快进会在 30 秒超时后强制退出，此时战场状态不完整。排查方式：开启 `detailDebug`，观察 `operationStep` 是否停止增长。

**陷阱 4：isRegretMode 期间误发网络请求**

`StartRegret` 将 `isClient` 设为 `false`，但仅仅屏蔽了 `NotifyClient`。如果其他逻辑直接检查 `self.isClient` 并发送网络包，悔棋重建过程中会产生非预期的服务器请求。正确做法：所有网络发包路径都应检查 `self.isClient and not self.isRegretMode`。

**陷阱 5：pairs 遍历顺序依赖**

Lua `pairs` 对 hash 表的遍历顺序不稳定。战斗逻辑中若用 `pairs` 遍历英雄集合并依赖顺序（如"谁先触发 buff"），客户端和服务器的 Lua VM 可能给出不同顺序，导致不确定性。应使用 `OrderedMap` 或显式按 `id` 排序后遍历。

---

## 11. 扩展阅读

- `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleTurnComp.lua`：完整的 `endnowbattleReq` 构造逻辑（约第 678-722 行），以及 `StartBattleWithFast` 随机种子重置
- `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleLogicComp.lua`：`DoUseBFSkill`（第 315-391 行），战场技能的 cmdList 写入，包含多目标 `target` 列表序列化
- `Client/Assets/Script/Lua/Logic/Battle/BattleRecord.lua`：战报的加载与本地文件读写
- `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleRegretComp.lua`：`CheckRegretIsCompleted`，快进过程中判断是否已到达目标步数的实现细节
