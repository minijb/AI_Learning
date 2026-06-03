# 教程 08：AI 决策系统

## 前置依赖

- 教程 01：BattleHero 实体与组件系统
- 教程 03：技能系统概览（CombatSkill / BFSkill）

---

## 1. AI 分层架构总览

战斗 AI 被拆成四个职责单一的层次，数据驱动，每层只做一件事：

```
AIBehaviorComp              每英雄决策入口（组件挂载于 BattleHero）
  |-- AIBehaviorCondition   行为条件：行动前置检查、行为模式转换
  |-- AIPickTarget          目标选择：选谁？
  `-- AIPickSkill           技能选择：用哪个技能？走到哪？
        `-- AIUtil          工具库：克制评分 / AOE最优释放点 / 范围查询
```

**数据驱动**：每个英雄从配置表读取 `aiBehaviorID`，加载对应的 `aiInfo`（`Behavior` 数据对象）。`aiInfo` 决定了：

- 用哪个条件函数（`StartActionCondition`、`StopAttackCondition`）
- 目标选择策略（`MoveTarget`、`PickAttackTarget`）
- 技能选择策略（`PickSkill`）
- 各参数 P1 / P2 / P3

**完整行动调用链**：

```
BattleHero 行动触发
  -> AIBehaviorComp:DoAI()
       -> AIBehaviorComp:doAiAttack()
            1. HasFightTagCannotAction         -- 眩晕/无法行动直接 DoWait
            2. CheckStartActionCondition        -- 未满足开始条件 -> DoWait
            3. CheckStopAttackCondition         -- 满足停止条件   -> DoWait
            4. CheckBehaviorConvertRules        -- 是否切换行为模式
            5. AIPickTarget.PickMoveTarget      -- 选移动目标
            6. AIPickSkill:PickSkill()          -- 选技能 + 计算最优走位
            7. AIPickSkill:UseSkill()           -- 执行移动 + 技能释放
```

---

## 2. AIBehaviorComp：每英雄的决策入口

`AIBehaviorComp` 是 `BattleHero` 上负责 AI 行为的组件，核心字段：

```lua
-- AIBehaviorComp.lua
-- 每个 BattleHero 挂载的核心 AI 组件，存储 AI 决策所需的全部运行时状态
function AIBehaviorComp:ctor()
    self.aiBehaviorID   = nil    -- 从配置表加载的行为 ID
    self.aiInfo         = nil    -- 解析后的 Behavior 数据对象
    self.aiPickSkill    = nil    -- AIPickSkill 实例，技能选择器
    self.banPickTargetMap = {}   -- 本回合禁止选为目标的单位集合
    self.pickTarget     = nil    -- 本次行动选定的攻击目标
    self.pickSkillId    = nil    -- 本次行动选定的技能 ID
    self.aiControl      = false  -- 是否由 AI 控制（false = 玩家控制）
    self.beAttackWeight = 0      -- 被攻击权重，用于快速筛选对象
    self.startAiTurnId  = 0      -- 初次运行 AI 的回合编号
end
```

### 关键方法

| 方法 | 作用 |
|------|------|
| `DoAI(aiAction, callback)` | 外部统一入口；根据 `aiAction` 分发到攻击/移动/待机 |
| `DoAIAttack()` | 走完完整行动流程（移动 + 技能释放） |
| `DoAIMove()` | 仅执行移动，不释放技能 |
| `DoAIWait(str)` | 执行待机（原地不动） |
| `DoAINewMove(callback)` | 技能后获得 DoubleMove 时的再移动 |
| `doAiAttack()` | 内部核心流程（见上方调用链） |
| `convert()` | 检查并执行行为模式切换 |
| `SetAIData(aiId)` | 运行时更换 AI 配置（热切换行为 ID） |

---

## 3. AIUtil：工具库与克制评分

`AIUtil` 是无状态的工具函数集合，供 `AIPickTarget`、`AIPickSkill` 调用。最核心的函数是 `getRestrainValue`，它量化"攻击者对防御者的克制优势"。

### 3.1 getRestrainValue：四维度克制评分

```lua
-- 量化"攻击者对防御者的克制优势"，返回 [-4, 4] 的综合评分
-- AIUtil.lua
function AIUtil.getRestrainValue(hero, defender)
    -- ArmyRestrainUtil 从兵种克制表计算四个维度的原始值
    local heroVal, soldierVal, heroToSoldierVal, soldierToHeroVal =
        ArmyRestrainUtil.GetAIArmyRestrainAttackVal(hero, defender)
    -- 每个维度各自 clamp 到 [-1, 1]，防止单维度过度主导
    if heroVal > 1 then heroVal = 1 elseif heroVal < -1 then heroVal = -1 end
    if soldierVal > 1 then soldierVal = 1 elseif soldierVal < -1 then soldierVal = -1 end
    if heroToSoldierVal > 1 then heroToSoldierVal = 1 elseif heroToSoldierVal < -1 then heroToSoldierVal = -1 end
    if soldierToHeroVal > 1 then soldierToHeroVal = 1 elseif soldierToHeroVal < -1 then soldierToHeroVal = -1 end

-- 返回值 >0：攻击方克制防御方；=0：均势；<0：被克制
    -- 最终分数 = 四维之和，范围 [-4, 4]
    return heroVal + soldierVal + heroToSoldierVal + soldierToHeroVal
end
```

**四个维度的含义**：

| 维度 | 含义 |
|------|------|
| `heroVal` | 将领对将领的克制关系 |
| `soldierVal` | 兵种对兵种的克制关系 |
| `heroToSoldierVal` | 我方将领克制对方兵种 |
| `soldierToHeroVal` | 我方兵种克制对方将领 |

每个维度先被 clamp 到 `[-1, 1]`，再求和。这样单维度的极端克制不会掩盖其他维度的信息，最终分数落在 `[-4, 4]`。

### 3.2 目标优先级权重常量

```lua
-- 权重按数量级分层：指定目标(百万级) > 克制分组(十万级) > 低血量(万级) > 远近偏好(万级) > 克制分微调(百级)
-- 组间差距 10 万确保层级之间不会互相干扰
-- AIUtil.lua — 目标优先级相关权重常量
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_POSITIVE      = 5000  -- 克制分>=1：低血量阈值 50%
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_NEUTRAL       = 4000  -- 克制分=0：低血量阈值 40%（近战攻击者）
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_NEUTRAL_FAR   = 5000  -- 克制分=0：低血量阈值 50%（远程攻击者）
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_NEGATIVE      = 1500  -- 克制分<0：低血量阈值 15%
local ATTACK_PRIORITY_APPOINT_TARGET_WEIGHT          = 1000000  -- 指定目标权重（最高优先级）
local ATTACK_PRIORITY_RESTRAIN_GROUP_WEIGHT_POSITIVE = 300000   -- 克制分>=1 组权重
local ATTACK_PRIORITY_RESTRAIN_GROUP_WEIGHT_NEUTRAL  = 200000   -- 克制分=0  组权重
local ATTACK_PRIORITY_RESTRAIN_GROUP_WEIGHT_NEGATIVE = 100000   -- 克制分<0  组权重
local ATTACK_PRIORITY_LOW_HP_WEIGHT_BASE             = 20000    -- 低血量加分基数
local ATTACK_PRIORITY_NEUTRAL_RANGE_PREFER_WEIGHT   = 10000    -- 远程/近战偏好加分
local ATTACK_PRIORITY_RESTRAIN_VALUE_WEIGHT_SCALE   = 100      -- 克制分细粒度缩放系数
```

这些常量共同构成了目标优先级的"打分机制"：

1. **指定目标（APPOINT）**：权重 100 万，绝对优先。
2. **克制分组（RESTRAIN_GROUP）**：先按克制分分桶（正/零/负），组间权重差距 10 万，确保克制对象永远优先于非克制对象。
3. **低血量加分（LOW_HP）**：组内再用"目标当前血量 / 最大血量 < 阈值"触发，按最大血量倒序给 2 万基础分。
4. **远近程偏好（RANGE_PREFER）**：远程攻击者优先打近战，近战攻击者优先打远程，加 1 万分。
5. **克制分细粒度（RESTRAIN_VALUE_SCALE）**：同组内以 `restrainValue * 100` 区分高低。

---

## 4. AIPickTarget：目标选择策略

`AIPickTarget` 是一张**策略路由表**：配置的枚举值 `CDataEnum.PickTarget.*` 映射到对应的选择函数。

```lua
-- AIPickTarget.lua
-- 策略路由表：配置枚举 -> 函数名字符串，通过动态调用实现多态分发
local PickTargetFuncs = {
    [CDataEnum.PickTarget.Nearest]                    = "PickTargetNearest",
    [CDataEnum.PickTarget.SelfPosition]               = "PickTargetSelfPosition",
    [CDataEnum.PickTarget.Random]                     = "PickTargetRandom",
    [CDataEnum.PickTarget.NearestPosition]            = "PickTargetNearestPosition",
    [CDataEnum.PickTarget.IndexGeneral]               = "PickTargetIndexGeneral",
    [CDataEnum.PickTarget.GeneralWithBuffAll]         = "PickTargetGeneralWithBuffAll",
    [CDataEnum.PickTarget.GeneralWithBuffAny]         = "PickTargetGeneralWithBuffAny",
    [CDataEnum.PickTarget.GeneralWithoutBuff]         = "PickTargetGeneralWithoutBuff",
    [CDataEnum.PickTarget.EnemyFilter]                = "PickTargetEnemyFilter",
    [CDataEnum.PickTarget.Never]                      = "PickTargetNever",
    [CDataEnum.PickTarget.EnemyOfEnterAttackRange]    = "PickTargetEnemyOfEnterAttackRange",
    [CDataEnum.PickTarget.EnemyOfEnterMoveAndAttackRange] = "PickTargetEnemyOfEnterMoveAndAttackRange",
}

-- 移动目标选择（aiInfo.MoveTarget 决定策略，MTParam1/2/3 为参数）
-- 通过 aiInfo 配置参数驱动目标选择，返回目标对象或 nil（无合法目标时）
function AIPickTarget.PickMoveTarget(hero)
    local pickTargetType = hero.aiInfo.MoveTarget
    local checkFunc = PickTargetFuncs[pickTargetType]
    if checkFunc then
        return AIPickTarget[checkFunc](hero,
            hero.aiInfo.MTParam1, hero.aiInfo.MTParam2,
            hero.aiInfo.MTParam3, hero.banPickTargetMap)
    end
end
-- 攻击目标选择：同样通过路由表分发，参数通过 aiInfo.PAParam 传入目标筛选函数

-- 攻击目标选择（aiInfo.PickAttackTarget 决定策略，PAParam1/2/3 为参数）
function AIPickTarget.PickAttackTarget(hero)
    local pickTargetType = hero.aiInfo.PickAttackTarget
    local checkFunc = PickTargetFuncs[pickTargetType]
    if checkFunc then
        return AIPickTarget[checkFunc](hero,
            hero.aiInfo.PAParam1, hero.aiInfo.PAParam2,
            hero.aiInfo.PAParam3, hero.banPickTargetMap)
    end
end
```

### 4.1 三大目标权重维度

`GetEnemyListByAttackPriority`（被 `PickTargetNearest` 等内部调用）按以下优先级排序攻击范围内的敌人：

**① 指定目标权重（APPOINT_TARGET_WEIGHT = 1,000,000）**

某些剧情/BOSS AI 会通过 `banPickTargetMap` 的反面逻辑"钦点"特定目标。一旦设置，该目标得到 100 万加分，压倒一切其他因素。

**② 克制分组权重（RESTRAIN_GROUP_WEIGHT）**

按 `getRestrainValue` 的结果分三档：

| 克制分 | 组权重 | 低血阈值（近战） | 低血阈值（远程） |
|--------|--------|------------------|------------------|
| >= 1   | 30 万  | 50%              | 50%              |
| = 0    | 20 万  | 40%              | 50%              |
| < 0    | 10 万  | 15%              | 15%              |

两组之间差距为 10 万，确保"克制优势 > 0 的对象"永远排在克制分为 0 的对象之前，克制分为 0 的又永远排在被克制对象之前。

**③ 低血量阈值权重（LOW_HP_WEIGHT_BASE = 20,000）**

同克制分组内，若目标当前 HP 百分比低于该组阈值，则按"最大血量从大到小"叠加 LOW_HP_WEIGHT_BASE 加分。目的是优先击杀快要死的单位（"补刀"逻辑），但不会打破组间顺序。

---

## 5. AIPickSkill：技能选择

`AIPickSkill` 是一个有状态的对象（`class.Class`），每个 `BattleHero` 持有一个实例（`self.aiPickSkill`）。它的核心职责是：**遍历英雄所有可用技能，找到第一个满足条件的技能，同时计算出最优走位和释放点**。

### 5.1 技能 AI 类型路由表

```lua
-- AIPickSkill.lua
-- 技能 AI 类型路由表：配置表中的 SkillAIType 枚举 -> 对应的选择逻辑函数名
-- 每个 PickSkillXxx 函数负责判断该技能是否值得释放，并计算最优走位和释放点
local PickSkillFuncs = {
    [CDataEnum.SkillAIType.None]                      = "PickSkillNone",
    [CDataEnum.SkillAIType.DamageSingle]              = "PickSkillDamageSingle",
    [CDataEnum.SkillAIType.DamageAOE]                 = "PickSkillDamageAOE",
    [CDataEnum.SkillAIType.DamageAOESelf]             = "PickSkillDamageAOESelf",
    [CDataEnum.SkillAIType.Heal]                      = "PickSkillHeal",
    [CDataEnum.SkillAIType.DamageAssault]             = "PickSkillDamageAssault",
    [CDataEnum.SkillAIType.HealRange]                 = "PickSkillHealRange",
    [CDataEnum.SkillAIType.BuffSingle]                = "PickSkillBuffSingle",
    [CDataEnum.SkillAIType.BuffAOE]                   = "PickSkillBuffAOE",
    [CDataEnum.SkillAIType.BuffSelf1]                 = "PickSkillBuffSelf1",
    [CDataEnum.SkillAIType.BuffSelf2]                 = "PickSkillBuffSelf2",
    [CDataEnum.SkillAIType.BuffSelfAOE]               = "PickSkillBuffSelfAOE",
    [CDataEnum.SkillAIType.Guard]                     = "PickSkillGuard",
    [CDataEnum.SkillAIType.NewTurn]                   = "PickSkillNewTurn",
    [CDataEnum.SkillAIType.DamageAOE2]                = "PickSkillDamageAOE2",
    [CDataEnum.SkillAIType.DamageAOESingleTarget]     = "PickSkillDamageAOESingleTarget",
    [CDataEnum.SkillAIType.LiJian]                    = "PickSkillLijian",
    [CDataEnum.SkillAIType.DamageLineAOE]             = "PickSkillDamageLineAOE",
    [CDataEnum.SkillAIType.DamageLineAOESingleTarget] = "PickSkillDamageLineAOESingleTarget",
    [CDataEnum.SkillAIType.JueDou]                    = "PickSkillJueDou",
}
```

每个技能在配置表中标记了 `SkillAIType`，决定了 AI 用哪套逻辑来判断"该技能此刻是否值得释放"以及"最优走位在哪"。

### 5.2 PickSkill 遍历流程

```lua
-- AIPickSkill.lua（简化）
-- 核心技能选择流程：遍历英雄所有可用技能，找到第一个满足条件的
-- 同时通过 PickSkillXxx 子函数计算出最优走位（bestWalkPoint）和释放点（releasePos）
-- isUsePickTarget：是否强制使用已选定的目标（指定攻击模式）
function AIPickSkill:PickSkill(isUsePickTarget, target)
    self:Clear()
    local pickSkillType = self.owner.aiInfo.PickSkill
    local skillIds = self.owner:GetAllSkillIDs(false)  -- 不含被动技

    -- 闭包函数：检查单个技能是否可用 — 五道关卡：nil / 被动技 / 可用性 / CD / AI判断
    local function canUseSkill(skillData, isActiveSkill)
    -- 关卡①：技能数据为空则不可用
    -- 关卡②：被动技不参与主动选择
    -- 关卡③：技能未满足使用条件（如所需怒气/道具不足）
    -- 关卡④：技能还在冷却中
        if skillData == nil then return false end
        if skillData.SkillType == CDataEnum.SkillType.Passive then return false end
        if not self.owner:IsSkillCanUse(skillId) then return false end
        local isCD, _ = self.owner:SkillIsInCD(skillId)
        if isCD then return false end

-- 关卡⑤：AI 判断 — 调用对应的 PickSkillXxx 函数，同时计算最优走位和释放点
        -- 根据 SkillAIType 调用对应的 PickSkillXxx 函数
        local checkFunc = PickSkillFuncs[skillData.SkillAIType]
        if checkFunc and self[checkFunc](self, skillData) then
            self.skillData = skillData
            -- 对于必须有目标的 BF 技能，还要验证合法目标列表
            if not BattleSkillUtil.IsBFSkillCanHasNoTarget(skillData)
                and BattleSkillUtil.IsBFSkill(skillData) then
-- 验证释放点附近确实有合法目标，防止空放技能导致逻辑异常
                local hasValidTarget, targetList =
                    self:getBFSkillTarget(self.releasePosX, self.releasePosY, self.ori)
                self.hasValidTarget = hasValidTarget
                self.targetList = targetList
                return hasValidTarget
            end
            return true
        end
        return false
    end

    -- Include 模式：优先使用配置指定技能，其余技能降级
    if pickSkillType == CDataEnum.PickSkill.Include then
        -- ... 优先尝试 skillsInclude 中的技能
-- Default 模式 / Include 模式 fallback：按列表顺序遍历，返回第一个通过 canUseSkill 的技能
    end
    -- Default 模式：按 skillIds 顺序逐一尝试，找到第一个可用的
    for i = 1, #skillIds do
        local skillData = dataMgr:GetSkillInfo(skillIds[i])
        if canUseSkill(skillData, true) then
            return skillIds[i]  -- 选定，后续由 UseSkill() 执行
        end
    end
end
```

**关键细节**：
- `PickSkillXxx` 函数返回 `true` 表示"该技能此时值得释放"，同时会把最优走位写入 `self.bestWalkPointX/Y` 和释放点写入 `self.releasePosX/Y`。
- 对 AOE 技能，调用 `AIUtil.GetBestReleasePoint` 等函数计算覆盖最多目标的释放点。
- 对突击技（`DamageAssault`），额外确保移动距离越远越好。
- BF 技能还要通过 `getBFSkillTarget` 验证释放点附近确实有合法目标，防止空放。

### 5.3 Hunter Buff 覆盖逻辑

部分 Buff 会给英雄附加"猎人"状态，强制锁定携带"猎物 Buff"的目标：

```lua
-- 在每个 PickSkillXxx 开头（部分技能类型）调用
-- Hunter/Prey 机制：Buff 驱动的目标锁定，优先级高于常规目标选择
-- 若英雄携带猎人 Buff，且 Buff.P2 匹配当前技能 ID，则强制锁定全场猎物目标
function AIPickSkill:tryHunterOverride(skillData)
    local hunterBuffs = self.owner:GetBuffsByType(CDataEnum.BuffType.Hunter)
    -- 若猎人 Buff 的 P2 匹配当前技能 ID，则在全场找到猎物并强制锁定
    -- 返回 true 表示已覆盖（跳过常规目标选择），false 表示回退到常规流程
end
```

---

## 6. AIBehaviorCondition：行为条件

行为条件是 AI 行为的"前置门卫"，决定英雄**何时开始行动、何时停止、何时切换行为模式**。

```lua
-- AIBehaviorCondition.lua
-- 行为条件路由表：配置枚举 -> 函数名，用于 StartActionCondition / StopAttackCondition / BehaviorConvertRules
-- 每个检查函数返回 true（条件满足）或 false（条件不满足），驱动 AI 行为转换
local BehaviorConditionFuncs = {
    [CDataEnum.BehaviorCondition.EnemyEnterAlertRange]         = "CheckEnemyEnterAlertRange",
    [CDataEnum.BehaviorCondition.NoEnemyEnteAlertRange]        = "CheckNoEnemyEnteAlertRange",
    [CDataEnum.BehaviorCondition.EveryTurn]                    = "CheckEveryTurn",
    [CDataEnum.BehaviorCondition.Never]                        = "CheckNever",
    [CDataEnum.BehaviorCondition.HPPercent]                    = "CheckHPPercent",
    [CDataEnum.BehaviorCondition.EnemyAttack]                  = "CheckEnemyAttack",
    [CDataEnum.BehaviorCondition.TargetTurn]                   = "CheckTargetTurn",
    [CDataEnum.BehaviorCondition.TargetTurnCount]              = "CheckTargetTurnCount",
    [CDataEnum.BehaviorCondition.EnemyEnterAttackRange]        = "CheckEnemyEnterAttackRange",
    [CDataEnum.BehaviorCondition.NoEnemyEnterAttackRange]      = "CheckNoEnemyEnterAttackRange",
    [CDataEnum.BehaviorCondition.GeneralWithBuffAll]           = "CheckGeneralWithBuffAll",
    [CDataEnum.BehaviorCondition.GeneralWithBuffAny]           = "CheckGeneralWithBuffAny",
    [CDataEnum.BehaviorCondition.GeneralWithoutBuff]           = "CheckGeneralWithoutBuff",
    [CDataEnum.BehaviorCondition.MoveTargetDistanceEqual]      = "CheckMoveTargetDistanceEqual",
    [CDataEnum.BehaviorCondition.EnemyEnterMoveAndAttackRange] = "CheckEnemyEnterMoveAndAttackRange",
    [CDataEnum.BehaviorCondition.MoveTargetCanStay]            = "CheckMoveTargetCanStay",
    [CDataEnum.BehaviorCondition.MoveChoice]                   = "CheckMoveChoice",
}
```

### 6.1 三种使用场景

| 场景 | aiInfo 字段 | 参数字段 | 含义 |
|------|-------------|---------|------|
| 开始行动条件 | `StartActionCondition` | `SACParam1/2/3` | 不满足则直接 DoWait，本回合不行动 |
| 停止攻击条件 | `StopAttackCondition` | 类似 | 满足则停止攻击，执行 DoWait |
| 行为转换规则 | `BehaviorConvertRules`（列表） | 每条规则含条件和目标 ID | 满足则切换到另一个 aiBehaviorID |

### 6.2 条件示例

**CheckHPPercent**（血量百分比判断）：

```
P1 = 0         -- 不指定阵营（默认检查行为者自身）
P2 = {}        -- 不指定将领 ID（默认自身）
P3 = 5000,-1   -- HP 百分比 50%，判断方式 -1（<=）
```
表示：当自身血量 <= 50% 时条件成立。

**CheckTargetTurnCount**（固定回合数后激活）：

```
P1 = 1   -- 我方阵营
P2 = 3   -- 初始 AI 生效后第 3 回合
```
表示：英雄行动 3 回合后才开始使用此行为。常用于关卡设计中，让 BOSS 在前几回合保持被动，然后突然发动。

**CheckBehaviorConvertRules**（行为模式转换）：

```lua
-- 遍历配置的转换规则列表，匹配则返回目标 behaviorID，驱动热切换
function AIBehaviorCondition.CheckBehaviorConvertRules(hero)
    -- 遍历 hero.aiInfo.BehaviorConvertRules 列表
    -- 每条规则含 Condition + 目标 BehaviorID
    -- 返回第一个满足条件的目标 BehaviorID，或 nil
end
```

`AIBehaviorComp:convert()` 调用此函数，若返回新 ID 则调用 `SetAIData` 热切换行为配置，无需重新初始化组件。

---

## 7. aiRandom：AI 专用随机数

战斗系统中存在**三个独立的随机数生成器**，各司其职：

```lua
-- Battle.lua
-- 三随机数生成器设计：隔离战斗逻辑、NPC AI、托管 AI 的随机序列，防止 desync
self.battleRandom      = Random("battleRandom", self, true)
-- 记录日志，用于所有战斗逻辑（伤害计算、暴击等）

self.aiRandom          = Random("aiRandom", self, true)
-- 记录日志，用于机器人/NPC AI 的决策（目标选择、技能选择中的随机）

self.autoBattleRandom  = Random("autoBattleRandom", self, false)
-- 不记录日志，用于玩家托管 AI 的决策
```

种子在每场战斗开始时统一设置，三者使用不同的种子偏移：

```lua
-- 从同一基础种子派生出三个独立序列：乘法偏移 + 大质数加法确保序列不重叠
self.battleRandom:SetSeed(seed)
self.aiRandom:SetSeed(seed * 97531 + 33333)
self.autoBattleRandom:SetSeed(seed * 13579 + 11111)
```

### 7.1 为什么 AI 决策必须用 aiRandom 而非 battleRandom？

**隔离性原则**：`battleRandom` 的随机序列决定伤害、暴击等战斗结果，必须在服务器与客户端之间严格同步。如果 AI 决策也消耗 `battleRandom`，那么 AI 决策的随机次数一旦在两端不一致（例如 AI 调试时跳过了某次随机），就会导致后续所有伤害计算偏移，产生不可复现的 desync 问题。

使用独立的 `aiRandom`：

- AI 的目标选择随机不影响伤害随机序列
- 服务器重放（悔棋）时，`aiRandom` 可以独立重置
- 日志记录（`true`）确保出问题时可以复现 AI 决策路径

```lua
-- AI 决策中所有随机调用必须走 aiRandom，绝不能消耗 battleRandom 的序列
-- 正确：使用 aiRandom
local i = hero.battle.aiRandom:GetRandom(1, cnt)

-- 错误：绝对不能这样写
-- local i = hero.battle.battleRandom:GetRandom(1, cnt)
```

---

## 8. AIAutoComp：自动托管

`AIAutoComp` 是挂载在**玩家英雄**上的自动战斗组件（`isAutoBattle = true` 时激活）。它复用了 `AIPickSkill` 等逻辑，但有一个关键区别：**使用 `autoBattleRandom` 而非 `aiRandom`**。

### 8.1 与普通 AI（AIBehaviorComp）的区别

| 维度 | AIBehaviorComp（NPC/BOSS AI） | AIAutoComp（玩家托管） |
|------|-------------------------------|------------------------|
| 控制对象 | 机器人/NPC/BOSS | 玩家英雄（托管模式） |
| 随机数 | `aiRandom`（记录日志） | `autoBattleRandom`（不记录） |
| 是否参与悔棋/服务器重放 | 是 | 否 |
| 特殊技能处理 | 无 | 额外处理主公技、桃、酒 |
| 技能选择入口 | `AIPickSkill:PickSkill()` | `AIAutoComp:AIUseNormalSkill()` |

### 8.2 autoBattleRandom 隔离理由

玩家托管的决策**本质上是客户端行为**：服务器并不知道玩家是否开启了托管，托管逻辑只在客户端生成操作指令，再发送给服务器执行。因此：

- 托管的随机不需要服务器同步，也不应该污染 `aiRandom`（后者用于 NPC，服务器需要完全重放）
- `autoBattleRandom` 不写调试日志（`false`），因为它产生的操作序列已通过指令日志记录，再记录随机数是冗余且混淆的

```lua
-- Battle.lua 注释原文：
-- Battle.lua 源码中的原始注释，明确指出 autoBattleRandom 仅用于客户端 UI，不参与服务器重放
-- autoBattleRandom：给客户端UI上生成玩家操作指令专用的AI，
-- 悔棋时和服务器上逻辑层不应用到这个随机数生成器
```

### 8.3 AIAutoComp 的技能使用流程

```lua
-- 玩家托管 AI 的技能决策入口：特殊资源（主公技/酒/桃）优先于普通技能，避免浪费
function AIAutoComp:AIUseSkill(callback)
    -- 1. UseZhuGongJiSkill  -- 尝试使用主公技
    -- 2. UseJiuSkill         -- 尝试使用酒
    -- 3. UseTaoSkill         -- 尝试使用桃（自救）
    -- 4. AIUseNormalSkill    -- 使用普通战法技 / BF 技能
end
```

主公技、酒、桃有单独的优先级处理，确保在 AI 决策时也能正确使用特殊资源，而不会被普通技能"抢先"。

---

## 9. 代码示例：getRestrainValue 完整实现与权重常量

以下摘自 `AIUtil.lua`，是理解整个目标优先级打分机制的基础：

```lua
-- 分层优先级打分体系：指定目标(100万) > 克制分组(10-30万) > 低血量(2万) > 远近偏好(1万) > 克制微调(×100)
-- === 权重常量定义（AIUtil.lua 顶部）===
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_POSITIVE      = 5000   -- 克制分>=1 低血量阈值 50%
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_NEUTRAL       = 4000   -- 克制分=0  低血量阈值 40%（近战攻击者）
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_NEUTRAL_FAR   = 5000   -- 克制分=0  低血量阈值 50%（远程攻击者）
local ATTACK_PRIORITY_LOW_HP_THRESHOLD_NEGATIVE      = 1500   -- 克制分<0  低血量阈值 15%
local ATTACK_PRIORITY_APPOINT_TARGET_WEIGHT          = 1000000
local ATTACK_PRIORITY_RESTRAIN_GROUP_WEIGHT_POSITIVE = 300000
local ATTACK_PRIORITY_RESTRAIN_GROUP_WEIGHT_NEUTRAL  = 200000
local ATTACK_PRIORITY_RESTRAIN_GROUP_WEIGHT_NEGATIVE = 100000
local ATTACK_PRIORITY_LOW_HP_WEIGHT_BASE             = 20000
local ATTACK_PRIORITY_NEUTRAL_RANGE_PREFER_WEIGHT    = 10000
local ATTACK_PRIORITY_RESTRAIN_VALUE_WEIGHT_SCALE    = 100

-- === 四维度克制评分（AIUtil.lua）===
function AIUtil.getRestrainValue(hero, defender)
    local heroVal, soldierVal, heroToSoldierVal, soldierToHeroVal =
        ArmyRestrainUtil.GetAIArmyRestrainAttackVal(hero, defender)
-- 先分别 clamp 再求和（而非求和后 clamp），确保单维度极端值不淹没其他维度信息

    -- 各维度 clamp 到 [-1, 1]
    if heroVal > 1 then heroVal = 1 elseif heroVal < -1 then heroVal = -1 end
    if soldierVal > 1 then soldierVal = 1 elseif soldierVal < -1 then soldierVal = -1 end
    if heroToSoldierVal > 1 then heroToSoldierVal = 1
    elseif heroToSoldierVal < -1 then heroToSoldierVal = -1 end
    if soldierToHeroVal > 1 then soldierToHeroVal = 1
    elseif soldierToHeroVal < -1 then soldierToHeroVal = -1 end

    return heroVal + soldierVal + heroToSoldierVal + soldierToHeroVal
    -- 返回值范围: [-4, 4]
    -- > 0 : 攻击者对防御者有克制优势
    -- = 0 : 无明显克制
    -- < 0 : 攻击者被防御者克制
end
```

**打分结果示例**（单个防御者的最终 priority 分）：

```
英雄 A（远程）攻击 英雄 B（克制分 = 2，血量 30%，最大血量 = 10000）：
  组权重         = 300000  （克制分 >= 1）
  克制细粒度     =    200  （2 * 100）
  低血量加分     =  20000  （30% < 50% 阈值，最大血量贡献）
  远程偏好       =  10000  （远程攻击者加分）
  ─────────────────────────
  最终 priority  = 330200+
```

---

## 10. 练习题

**练习 1**：克制评分的边界分析

假设 `ArmyRestrainUtil.GetAIArmyRestrainAttackVal` 返回 `heroVal=3, soldierVal=-2, heroToSoldierVal=0, soldierToHeroVal=1`，请计算 `getRestrainValue` 的返回值，并解释为什么要对每个维度单独 clamp 而不是直接对总和 clamp。

> 提示：若不单独 clamp，`heroVal=3` 会直接贡献 3 分；单独 clamp 后最多贡献 1 分。两种方案对"极端单维度克制"的处理有何不同？

---

**练习 2**：新增一个行为条件

需求：当战场上存活的我方英雄数量 <= 2 时，AI 切换到保守行为模式（只移动不攻击）。

1. 在 `AIBehaviorCondition.lua` 中新增函数 `CheckAliveAllyCount`，参数格式：`P1 = 我方单位数阈值`，`P2 = 判断方式（-1表示<=）`。
2. 在 `BehaviorConditionFuncs` 中注册新枚举 `CheckAliveAllyCount`。
3. 在配置表中如何配置 `BehaviorConvertRules`，使 BOSS 在我方存活 <= 2 人时切换到 behaviorID = 999？

---

**练习 3**：理解 aiRandom 隔离的必要性

设想一个场景：游戏客户端在调试时新增了一处 `battleRandom:GetRandom()` 调用（误用），而服务器没有这行代码。

1. 描述这会如何导致 desync（客户端与服务器战斗结果不一致）。
2. 说明为什么托管模式使用 `autoBattleRandom` 而非 `aiRandom`，从"服务器是否需要重放托管决策"角度分析。
3. 如果要为战场特效（纯表现层）新增一个随机数，应该用哪个生成器？理由是什么？

---

## 11. 常见陷阱

**陷阱 1：在 AI 逻辑中误用 battleRandom**

AI 逻辑（目标选择、技能选择）内所有随机必须使用 `battle.aiRandom`。误用 `battleRandom` 会消耗其随机序列，导致后续伤害/暴击计算在客户端和服务器上偏移，产生难以复现的 desync。

**陷阱 2：PickSkillXxx 函数忘记写入走位信息**

每个 `PickSkillXxx` 函数在返回 `true` 前，必须正确设置 `self.bestWalkPointX/Y` 和 `self.releasePosX/Y`。若忘记写入（例如只 `return true` 但没计算位置），后续 `UseSkill()` 会使用默认零值坐标，导致英雄走位错误甚至走到地图原点。

**陷阱 3：忘记 clamp 克制分单个维度**

`getRestrainValue` 对每个维度单独 clamp 到 `[-1, 1]`，然后求和。如果在调用 `ArmyRestrainUtil.GetAIArmyRestrainAttackVal` 之后直接使用原始值参与权重计算（跳过 clamp），单维度极端克制会使权重失控，导致 AI 忽略其他维度完全由一个维度主导。

**陷阱 4：行为条件函数使用了错误的随机数**

`AIBehaviorCondition` 中的条件检查函数（如 `CheckHPPercent`）是纯判断逻辑，不应包含任何随机调用。若误在其中引入随机，每次调用（包括 `CheckStartActionCondition` 和 `CheckStopAttackCondition`）都会消耗随机数，产生意外的序列偏移。

**陷阱 5：BF 技能忘记验证 hasValidTarget**

`PickSkill` 对 BF 技能会额外调用 `getBFSkillTarget` 验证是否有合法目标。若自定义一个新的 `PickSkillXxx` 处理 BF 技能时跳过这一步直接 `return true`，会导致技能释放后没有实际目标，造成技能白放甚至逻辑异常。

**陷阱 6：SetAIData 切换后 aiPickSkill 状态未清理**

`AIBehaviorComp:convert()` 调用 `SetAIData` 热切换行为 ID 后，必须确保 `aiPickSkill:Clear()` 被调用（在下一次 `doAiAttack` 开头会自动清理）。如果在 `convert` 后立即在同一帧内继续使用旧的 `skillData`、`coverEntities` 等缓存字段，可能命中已清理的目标对象。

---

## 12. 扩展阅读

- **`ArmyRestrainUtil.lua`**：`GetAIArmyRestrainAttackVal` 的具体实现，了解四维度克制值的计算公式和兵种克制表结构。
- **`AIPickSkillAtTarget.lua`**：`AIPickSkill` 通过 `class.AddComponent` 混入的扩展，处理"强制指定目标时的技能选择"逻辑（`isUsePickTarget = true` 时走这条路径）。
- **`AIPickSkill:PickSkillDamageAOE`** 和 **`GetBestReleasePoint`**：AOE 最优释放点的穷举算法，理解"包围盒遍历 + 覆盖计数"的核心思路。
- **`Battle.lua` 中的 Random 初始化**：三个随机数生成器的种子偏移设计，理解为何用乘法偏移（`seed * 97531 + 33333`）而不是加法偏移。
- **教程 06：Buff 系统深入**：部分 Buff（如 Hunter Buff、BuffJN 系列）会在 `autoBattleRandom` 下触发自动行为，理解 Buff 与 AI 的交互边界。
