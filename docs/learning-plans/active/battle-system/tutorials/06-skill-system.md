# 06 技能系统

## 前置依赖

- [02 战场单位与组件系统](02-battle-class-components.md) — BattleHero、HeroSkillComp、HeroBFSkillComp
- [03 状态机与回合流程](03-state-machine-turn-flow.md) — HeroTurnComp、行动触发时机
- [05 Buff 系统](05-buff-system.md) — BuffBase 生命周期，Buff 如何触发被动技

---

## 1. 技能类型分类

游戏内技能分为三种，触发时机和归属类完全不同：

| 类型 | 代码类 | 触发时机 | 挂载组件 |
|------|--------|----------|----------|
| 主动技（对冲技） | `CombatSkill` | 回合行动、AI 选技后发起对冲 | `HeroSkillComp` |
| 战场技（BF 技） | `BFSkill` | 战场格子行动阶段，英雄移动/位置触发 | `HeroBFSkillComp` |
| 被动触发技 | — | Buff 钩子（`CheckCombatSkillCond` 等）内部触发，无独立类 | `HeroBuffComp` |

**主动技**（`CombatSkill`）是两军对冲时产生的 1v1 或 1vN 技能，每次对冲在 `CombatField`
虚拟战场内运行，有完整的攻击者/防御者角色和伤害结算。

**战场技**（`BFSkill`）在真实格子战场上直接释放，使用 `BFAttackCreator` 分发给各种
`BFAttack` 子对象（`BFComAttack`、`BFHeal`、`BFAddBuff`、`BFChain`、`BFJueDouAttack` 等）执行效果。

**被动触发技**不单独实例化，其逻辑嵌在对应 Buff 的钩子方法中——当回合条件或技能条件满足时，由
BuffBase 调度执行。

---

## 2. SkillBase 基类

`Logic.Battle.Skill.SkillBase` 是所有技能的公共基类，持有技能生命周期内所需的全部状态字段。

### 关键字段（摘自源码注解）

```lua
---@class SkillBase
---@field public battle         Battle              -- 所属战斗实例
---@field public owner          BattleHero|Soldier  -- 技能施放者
---@field public target         BattleHero|BattleHero[]  -- 当前目标
---@field public skillData      SkillInfo           -- 策划配置数据
---@field public id             integer             -- 本次施放的唯一实例 ID
---@field public index          integer             -- 英雄技能槽位索引
---@field public power          number              -- 当次施放威力
---@field public isCri          boolean             -- 本次是否暴击
---@field public coolDownCount  integer             -- 剩余 CD（帧数）
---@field public useRoundId     integer             -- 施放时的回合 ID
---@field public useActionIndex integer             -- 施放时的行动 ID
---@field public cardColor      integer             -- 牌色（黑/红，影响伤害倍率）
---@field public haveUseCount   integer             -- 本战中已使用次数
---@field public onStart        EventHandler        -- 技能开始事件
---@field public onStop         EventHandler        -- 技能停止事件
```

`useRoundId` 初始值为 `-2^32`，确保任何真实回合 ID 都不会误判为"已在本回合使用"。

### SkillIdCreator：实例 ID 生成

每次施放技能需要一个全战斗唯一的实例 ID，由 `SkillIdCreator` 生成：

```lua
-- Logic/Battle/Skill/SkillIdCreator.lua
function SkillIdCreator:GetNextSkillId()
    self.skillIdIndex = self.skillIdIndex + 1
    if self.skillIdIndex > 2^32 then
        self.skillIdIndex = 1   -- 回绕，避免整数溢出
    end
    return self.skillIdIndex
end
```

`skillIdIndex` 初始为 0，每次调用自增。上限 2^32 回绕——单场战斗不会耗尽，仅作防御性保护。

### 生命周期接口

```lua
skill:init()                       -- 初始化（注册状态机状态）
skill:Play(target, isMultiTarget)  -- 启动技能播放
skill:Update(dt)                   -- 逐帧驱动（客户端 30fps / 服务器单循环走完）
skill:Stop()                       -- 正常停止，重置 attackCount/cardColor 等
skill:ForceStop()                  -- 强制中断（死亡等异常原因）
skill:Pause()                      -- 暂停（isPause = true）
skill:Resume()                     -- 恢复
skill:destroy()                    -- 销毁，释放 EventHandler
```

`SkillBase:Play` 会根据 `owner.entityType` 判断是英雄还是士兵，设置方向（`ori`）和目标后，
由子类覆写的 `Play` 继续启动状态机。

---

## 3. CombatSkill 主动技

`CombatSkill` 继承 `SkillBase`，用状态机（`StateManager`）驱动整个对冲流程。

### 状态机状态

```lua
-- CombatSkill.lua:29-38
local SkillState = {
    Invalid = 0,  -- 初始/结束
    Init    = 1,  -- 初始化准备
    Wait    = 2,  -- 等待前摇延迟
    Sing    = 3,  -- 吟唱
    Move    = 4,  -- 移动冲向目标
    Attack  = 5,  -- 攻击/伤害帧
    Return  = 6,  -- 回位
    Died    = 7,  -- 对冲中死亡
}
```

状态注册发生在 `init()`，每个状态对应 Enter / Running / Leave 三个回调：

```lua
-- CombatSkill.lua:80-88
self.stateMgr:AddState("InitState",
    CallbackHandler(self, "onInitStateEnter"),
    CallbackHandler(self, "onInitStateRunning"),
    CallbackHandler(self, "onInitStateLeave"))
-- ... 其余状态类似
```

### 执行流程概述

```
选择目标（AI / 玩家输入）
    │
    ▼
HeroSkillComp 检查 CD + 使用条件
    │
    ▼
CombatField:CreateCombatActor()  ← 注册攻/守双方 Actor
    │
    ▼
CombatSkill:Play(target)  →  stateMgr 切换到 InitState
    │
    ▼ 逐帧 Update(dt)
WaitState → SingState → MoveState → AttackState（伤害帧） → ReturnState
    │
    ▼
CombatField:AddDamage()  ← 记录伤害结果
    │
    ▼
结算：扣 HP、触发 Buff、广播 onStop 事件
```

### 关键构造字段

```lua
-- CombatSkill.lua:44-74（节选）
function CombatSkill:ctor()
    self.damageFlagMaps      = {}   -- 防重复命中标记
    self.hitIndex            = 1    -- 当前第几次伤害
    self.attackIndex         = 1    -- 当前第几次攻击
    self.combatField         = nil  -- 所属对冲战场
    self.preCastDelay        = 0    -- 前置施法延迟
    self.debugTotalDamageVal = 0    -- 调试：累计伤害
end
```

`hitIndex` 和 `attackIndex` 支持多段攻击（如连击技），每段独立记录伤害。

---

## 4. CombatField + CombatActor：对冲战场架构

### CombatField

`CombatField` 是一次主动技施放时临时搭建的虚拟战场，管理攻方队列、守方队列、伤害记录和飞行物。

```lua
---@class CombatField
---@field public attackActors           CombatActor[]                          -- 攻方 Actor 列表
---@field public defendActors           CombatActor[]                          -- 守方 Actor 列表
---@field public damageRecords          table<integer, CombatFieldDamageRecord[]>  -- 伤害记录
---@field public flyObjMaps             table<integer, table<integer, CombatFlyObject>>
---@field public attackerHasFirstStrike boolean  -- 攻方是否有先攻
---@field public defenderHasFirstStrike boolean  -- 守方是否有先攻
```

### 攻方 vs 守方角色

`CreateCombatActor` 的 `isAttacker` 参数决定 Actor 归属：

```lua
-- CombatField.lua:195-218（节选）
function CombatField:CreateCombatActor(battle, attacker, defender,
                                        skillData, fieldDis, isAttacker)
    local actor = self:getFromPool()   -- 对象池复用
    actor.attacker    = attacker
    actor.defender    = defender
    actor.skillData   = skillData
    actor.fieldDis    = fieldDis
    actor.combatField = self
    if isAttacker then
        self.attackActors[#self.attackActors + 1] = actor
    else
        self.defendActors[#self.defendActors + 1] = actor
    end
end
```

`attackActors` 和 `defendActors` 均可包含多个 Actor（AOE 或反击场景），每个 Actor 独立计算伤害。

### 对冲储备与结算

**写入**：攻击命中时调用 `AddDamage()`：

```lua
-- CombatField.lua:224-261
function CombatField:AddDamage(frameCount, attacker, target, skillData,
                                attackIndex, hitIndex, damageVal, isCrit)
    -- 去重：同 attackIndex+hitIndex 的记录已存在且 damageVal<=0 时覆盖，否则追加
    -- ...
end
```

**查询**：结算阶段或表现层读取：

```lua
local record = combatField:GetDamageByIndex(attacker.id, attackIndex, hitIndex)
```

**对象池**：`CombatField` 维护四个池——`pools`（Actor）、`flyObjPools`（飞行物）、
`hitObjPools`（命中特效）、`attackObjPools`（攻击对象），`Clear()` 时批量回收，避免 GC 压力。

---

## 5. BFSkill 战场技

### 与主动技的核心差异

| 维度 | CombatSkill | BFSkill |
|------|-------------|---------|
| 战场 | CombatField 虚拟对冲战场 | 真实格子地图 |
| 目标选择 | `CombatActor` 的 attacker/defender | BattleSkillUtil 计算格子范围 |
| 效果执行 | 状态机内直接计算 | 委托给 BFAttack 子对象 |
| 状态数 | 8 个（含 Move/Return） | 7 个（无 Move/Return） |

### BFSkill 状态机

```lua
-- BFSkill.lua:42-49（节选）
self.stateMgr:AddState("InvalidState",  ...)
self.stateMgr:AddState("InitState",     ...)
self.stateMgr:AddState("WaitState",     ...)
self.stateMgr:AddState("SingState",     ...)
self.stateMgr:AddState("CutSceneState", ...)
self.stateMgr:AddState("AttackState",   ...)  -- 无 MoveState/ReturnState
self.stateMgr:AddState("DiedState",     ...)
self.stateMgr:AddState("StopState",     ...)
```

### 启动入口

```lua
-- BFSkill.lua:62-80（节选）
function BFSkill:Play(target, isMultiTarget)
    BFSkill.super.Play(self, target, isMultiTarget)
    self.battle = self.owner.battle
    self.preCastDelay = self.battle.dataMgr:GetConstConfig(
        CDataEnum.ConfigableConst.Battle_SkillPreCastDelay)
    -- 通知客户端开始播放战场技特效
    if self.isClient then
        local clientObj = self.owner.clientEntity
        if clientObj then clientObj:OnStartBFSkill() end
    end
    self.stateMgr:SetCurState("InitState")
end
```

### BFAttack 子类型（BFAttack/ 目录）

| 文件 | 用途 |
|------|------|
| `BFDefaultAttack` | 普通单体/AOE 伤害 |
| `BFComAttack` | 通用组合攻击 |
| `BFChain` | 链式/连射攻击（如连射类战场技） |
| `BFHeal` / `BFHealPercent` | 治疗（固定值/百分比） |
| `BFAddBuff` | 施加 Buff |
| `BFRemoveBuff` | 移除 Buff |
| `BFJueDouAttack` | 决斗型攻击 |
| `BFJNAOEAttack` | 锦囊 AOE 伤害 |
| `BFLiJianAttack` | 离间型攻击 |
| `BFMingCe` | 明策类效果 |
| `BFNewTurn` | 触发新回合 |
| `BFHealRemoveCD` | 治疗并清除 CD |
| `BFJNChai` / `BFJNHuo` / `BFJNShun` | 锦囊类型变体 |

`BFAttackCreator` 根据 `skillData.SkillType` 工厂创建对应子对象，挂在 `BFSkill.attackObj`。

---

## 6. Damage.lua 伤害计算

`Logic.Battle.Skill.Damage` 是**无状态静态工具类**，所有方法直接调用，无需实例化。

### 设计特征

```lua
-- Damage.lua:13-15
local Damage = {
    debug = true   -- QA 验收阶段开启，记录伤害计算细节日志
}
```

文件头部大量 `local` 缓存枚举常量（Fire/Thunder/Ice/Poison 元素，黑沙/红沙牌色，暴击率/暴伤，
技能伤害倍率、战场技伤害倍率、间接伤害倍率等），避免每帧查表开销。

### 核心方法一览

| 方法 | 说明 |
|------|------|
| `Damage.IsCriDamage(rd, CRI)` | 随机判定是否暴击（1-10000 区间） |
| `Damage.GetDamageElem(elemType, atk, def)` | 获取元素伤害系数（万分比加和） |
| `Damage.GetCardColorDamage(cardColor, atk, def)` | 获取牌色（黑/红）伤害加成 |
| `Damage.GetCritRate(atk, def, ...)` | 计算最终暴击率 |

**暴击判定**示例：

```lua
-- Damage.lua:91-97
function Damage.IsCriDamage(rd, CRI)
    local IsCrit = false
    local rands = rd:GetRandom(1, 10000)
    if rands <= CRI then
        IsCrit = true
    end
    return IsCrit
end
```

**元素伤害系数**（以火元素为例）：

```lua
-- Damage.lua:102-148（节选）
function Damage.GetDamageElem(damageElemType, atk, def)
    local atkVal = 0
    local defVal = 0
    -- 攻击方加成：区分将领(HERO) / 士兵(SOLDIER) × 元素类型
    if atk.entityType == Enum.EntityType.HERO then
        if damageElemType == EDET_Fire then
            atkVal = atk:GetStatusModify(General2_FireDamageMul)
        -- elseif Thunder / Ice / Poison ...
        end
    end
    -- 防御方减免：同样区分将领/士兵
    if def.entityType == Enum.EntityType.HERO then
        if damageElemType == EDET_Fire then
            defVal = def:GetStatusModify(General2_FireDamageRecvMul)
        end
    end
    return atkVal + defVal  -- 返回万分比系数，正值=增伤，负值=减伤
end
```

> 伤害系数均为**万分比整数**（策划配表一致），最终乘以基础伤害后除以 10000 得到实际值。

---

## 7. BattleSkillUtil 工具集

`Logic.Battle.Skill.BattleSkillUtil` 是技能系统的**静态工具集**，覆盖格子计算、目标筛选、
距离判断、帧时转换等高频操作。

### 初始化

```lua
-- BattleSkillUtil.lua:35-56
function BattleSkillUtil.Init(dataMgr)
    -- 从常量配置表读取关键参数
    BattleSkillUtil.CombatSoldierMoveDelay    = dataMgr:GetConstConfig(...)
    BattleSkillUtil.CombatSoldierReturnDelay  = dataMgr:GetConstConfig(...)
    BattleSkillUtil.BattleMeleeATKPunishMult  = dataMgr:GetConstConfig(...)
    BattleSkillUtil.SplitScreenDistance       = dataMgr:GetConstConfig(...)
    -- 初始化杀/闪/桃/酒 Buff ID 和数量
    -- 加载格局配置（CommonDefault / GeneralDefault / ShuXingZhen / Walk01）
end
```

### 常用方法

| 方法 | 说明 |
|------|------|
| `BF_GetRhomboidGridsAtPt(battle,x,y,d,useMap)` | 获取菱形范围格子（默认扩散型） |
| `BF_GetVHLineGridsAtPt(...)` | 获取十字线格子 |
| `BF_GetRectGridsAtPt(...)` | 获取矩形范围格子 |
| `BF_GetSquareGridsAtPt(...)` | 获取方形范围格子 |
| `GetSkillReleaseGrids(battle,hero,skillData)` | 按技能配置获取释放范围格子 |
| `GetSkillTakeEffectGrids(...)` | 获取技能生效范围格子 |
| `GetHeroTargets(battle,hero,grids,targetType)` | 在格子集合内查找目标 |
| `GetSkillReleaseObjects(battle,hero,skillData,...)` | 获取技能可选中的将领 ID 列表 |
| `FilterSelectedObjectsBySkillTargetCondition(...)` | 按技能目标条件过滤目标列表 |
| `IsEnemySide(itselfTeamType,targetTeamType)` | 判断是否敌对方 |
| `IsFriendSide(...)` | 判断是否友方 |
| `IsCanUseByAttackDistance(skillId,attacker,defender)` | 检查攻击距离是否满足技能释放 |
| `IsBFSkill(skillData)` | 判断是否为战场技 |
| `IsAOESkill(skillData)` | 判断是否为 AOE 技能（`BF_Range > 1`） |
| `ComputeTargetScore(x,y,target)` | 计算目标评分（前排优先、近距优先、不选预判死亡） |
| `FrameToMillisecond(frame)` | 帧数 → 毫秒（30fps 基准） |
| `MillisecondToFrame(ms)` | 毫秒 → 帧数（四舍五入） |

### 格子 vs Map 两种返回形式

大多数格子方法支持 `useMap` 参数：

- `useMap = false`（默认）：返回 `Vector2[]` 数组，适合遍历
- `useMap = true`：返回 `table<(x<<16)|y, boolean>` map，适合 O(1) 查找

工具类复用同一个静态 `r` / `rMap` 变量（而非每次分配新表），调用前会清空旧数据。**不要持有返回值的引用跨帧使用**，下次调用会覆盖其内容。

---

## 8. 代码示例：追踪一次主动技施放

以下代码展示从技能选择到伤害结算的完整调用链（简化）：

```lua
-- 1. AI 选技，HeroSkillComp 检查 CD
local skillData = hero.heroSkillComp:GetUsableSkill()

-- 2. 创建对冲 Actor（攻方）
battle.combatField:CreateCombatActor(
    battle, hero, targetHero, skillData, fieldDis, true)  -- isAttacker=true

-- 如果目标有反击技，也在守方注册
-- battle.combatField:CreateCombatActor(..., false)

-- 3. 启动技能
local skill = hero.heroSkillComp:GetSkill(skillData.ID)
skill:Play(targetHero, false)

-- 4. 每帧驱动（由 Battle:Update 统一调用）
-- skill:Update(dt)

-- 5. AttackState 命中时写入伤害
-- battle.combatField:AddDamage(frameCount, hero, targetHero,
--     skillData, attackIndex, hitIndex, damageVal, isCrit)

-- 6. 结算阶段读取并应用
local record = battle.combatField:GetDamageByIndex(hero.id, 1, 1)
if record then
    targetHero:ApplyDamage(record.damageVal, record.isCrit)
end
```

**暴击判定片段**（Damage.lua 实际调用）：

```lua
local isCrit = Damage.IsCriDamage(battle.random, hero:GetCRI())
local elemBonus = Damage.GetDamageElem(
    CDataEnum.DamageElementType.Fire, hero, targetHero)
-- elemBonus 是万分比整数，最终: finalDmg = baseDmg * (10000 + elemBonus) / 10000
```

---

## 9. 练习题

**练习 1**：`CombatField` 维护了四个对象池（pools / flyObjPools / hitObjPools / attackObjPools），
说明每个池对应什么对象，以及为什么在 `Clear()` 而非 `destroy()` 时回收。

**练习 2**：`BattleSkillUtil` 的格子查询方法（如 `BF_GetRhomboidGridsAtPt`）复用静态变量
`r` / `rMap`。编写一个错误示例代码，展示跨帧持有返回值引用会引发什么问题；
然后给出正确做法（遍历后立即消费或深拷贝）。

**练习 3**：`Damage.GetDamageElem` 返回的系数是"万分比整数"。假设攻击者火元素加成为 `500`、
目标火元素减免为 `-200`，基础技能伤害为 `1000`，写出最终伤害的计算公式并求值。

---

## 10. 常见陷阱

### 陷阱 1：混淆 `attackIndex` 和 `hitIndex`

`attackIndex` 表示"第几次攻击动作"（适用于多段攻击技），`hitIndex` 表示"该次攻击动作内第几次命中"。
`AddDamage` 和 `GetDamageByIndex` 都需要两者匹配，用其中一个替代另一个会导致伤害记录查不到或被覆盖。

### 陷阱 2：持有格子查询结果的引用

`BattleSkillUtil.BF_GetRhomboidGridsAtPt` 等方法返回的是工具类内部静态表，
下次调用同类方法会原地清空并重新填写。持有引用跨帧或跨调用使用将读到空/错误数据。

### 陷阱 3：`isBFSkill` 字段与 `BattleSkillUtil.IsBFSkill()` 不一致

`SkillBase.isBFSkill` 是实例字段，在构造时由子类设置。`BattleSkillUtil.IsBFSkill(skillData)` 则
根据技能配置数据中的 `SkillType` 枚举判断。两者语义不同——前者表示"这个技能实例是 BFSkill 类"，
后者用于在没有实例时仅凭配置数据判断。在 Buff 钩子里只有 `skillData` 时，应使用后者。

### 陷阱 4：`coolDownCount` 减少方向

`coolDownCount` 存的是**剩余帧数**，每帧递减直到 0 才可再次施放。修改 CD 时是直接写入剩余量，
不是写入总 CD——对 CD 清除/缩短等 Buff，应操作 `coolDownCount` 而不是 `skillData.CoolDown`。

### 陷阱 5：在 `destroy()` 之后访问 EventHandler

`SkillBase:destroy()` 调用了 `onStart:destroy()` 和 `onStop:destroy()`，销毁后这两个字段置 nil。
技能池化时若忘记在 `Reset()` 中重新创建 EventHandler，后续调用 `onStart:AddListener()` 会崩溃。

---

## 11. 扩展阅读

- `Client/Assets/Script/Lua/Logic/Battle/Skill/CombatSkill.lua` — 完整对冲状态机实现
- `Client/Assets/Script/Lua/Logic/Battle/Skill/BFSkill.lua` — 战场技完整流程
- `Client/Assets/Script/Lua/Logic/Battle/Skill/CombatField.lua` — 对冲战场伤害记录与对象池
- `Client/Assets/Script/Lua/Logic/Battle/Skill/Damage.lua` — 所有伤害/治疗静态计算函数
- `Client/Assets/Script/Lua/Logic/Battle/Skill/BattleSkillUtil.lua` — 格子、目标、距离工具集
- `Client/Assets/Script/Lua/Logic/Battle/Skill/BFAttack/BFAttackCreator.lua` — BFAttack 工厂
- `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroSkillComp.lua` — 主动技组件（CD 管理、技能触发）
- `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroBFSkillComp.lua` — 战场技组件
