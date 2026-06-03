# 07. Buff 系统

**前置依赖**：教程 02（组件体系）、03（回合状态机）、06（技能系统）

---

## 1. 总体架构：为什么有 60+ 个具体类

Buff 系统采用**基类 + 子类注册**的经典策略模式。`BuffBase.lua`（约 1583 行）是唯一的公共基类，负责：

- 声明所有字段与 EmmyLua 注解
- 提供 `ctor / init / destroy` 生命周期骨架
- 实现通用工具方法（`ReduceBuffLifetime`、`CheckBuffCondition`、`SetDestroyFlag` 等）
- 声明钩子函数签名（由子类覆盖）

每种 `BuffType` 对应一个子类文件（如 `BuffPropertiesModify`、`BuffHealOverTime`、`BuffNeverDie`……）。子类只覆盖它关心的钩子，其他行为沿用基类默认空实现。这样做的原因：

1. **运行时多态无虚表开销**：Lua 通过元表 `__index` 链完成方法查找，子类不需要声明它不关心的钩子。
2. **配置驱动扩展**：策划新增一种 Buff 类型时，只需新增一个子类文件 + 在 `BuffCreator` 注册，无需修改调度中枢 `BattleBuffComp`。
3. **便于隔离调试**：每种逻辑独立成文件，Bug 定位直接定位到对应子类。

```
BuffBase（基类，公共骨架）
  ├── BuffPropertiesModify    -- 属性加成
  ├── BuffHealOverTime        -- 持续治疗
  ├── BuffDamageOverTime      -- 持续伤害
  ├── BuffNeverDie            -- 不屈
  ├── BuffChain               -- 铁索连环
  ├── BuffJinNang             -- 锦囊
  └── ... （共 60+ 个）
```

`BuffDefault`（无匹配子类时的兜底）保证任何 buffId 都能安全创建实例。

---

## 2. BuffBase 关键字段

以下字段均来自 `BuffBase.lua` 第 13–58 行的 EmmyLua 注解及 `ctor` 初始化。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 实例 ID，同一英雄身上每个 Buff 唯一，由 `owner.buffIdCreator:GetNextBufId()` 分配 |
| `buffId` | `integer` | 配置表 ID（对应 `BuffInfo` 表行），多个实例可共享同一 `buffId` |
| `owner` | `BattleHero` | 携带此 Buff 的英雄（受益方或受害方） |
| `caster` | `BattleHero\|nil` | 施加者；主公技/地形 Buff 等来源无施加者时为 `nil` |
| `state` | `Enum.BuffState` | 当前状态机状态（见第 4 节） |
| `isActive` | `boolean` | 遗留字段，计划 2025.7.30 后删除，当前逻辑已以 `state` 为准 |
| `isEnabel` | `boolean` | 是否可用（被禁用时强制不触发） |
| `isDestroy` | `boolean` | 标记已进入销毁流程，防重入 |
| `isOnce` | `boolean` | 一次性 Buff：触发后在本回合结束时自动销毁 |
| `isBufCoolDown` | `boolean` | 是否处于 CD 冷却阶段（由 `CDBuff_ID` 指向的 CD 指示 Buff 控制） |
| `remainLifetime` | `integer` | 剩余回合数，由配置表 `Time` 字段初始化 |
| `hasExtralLifetime` | `boolean` | 是否有额外 1 回合豁免（先消耗此标志，再减 `remainLifetime`） |
| `noCDCount` | `number` | 可免除 CD 的次数（当前版本暂未使用，2025.7.29） |
| `num` | `integer` | 叠加层数，初始为 1；叠加型 Buff 子类会修改此值 |
| `color` | `integer` | 0=无色 / 1=黑色 / 2=红色；仅 BasicCard/JinNang 类型从 `P3` 赋值 |
| `info` | `BuffInfo` | 指向配置表行的引用，`destroy` 时置 `nil` 释放 |
| `propsModify` | `table<integer,integer>` | 属性 ID → 修改值映射，由 `Property1~4` 字段初始化 |
| `fightTags` | `table<integer,boolean>` | 战斗标签集合，由配置表 `FightTags` 字段初始化 |
| `initTurnId` | `integer` | 添加时的回合 ID（战斗开始前添加的统一记为 1） |
| `addCase` | `Enum.BuffAddCase` | 添加原因，便于调试和特殊逻辑分支 |
| `remCase` | `Enum.BuffRemCase` | 移除原因，便于调试和特殊逻辑分支 |
| `P1` | `integer` | 通用参数 1，来自配置表 `BuffTypeParam1` |
| `P2` | `integer` | 通用参数 2，来自配置表 `BuffTypeParam2` |
| `P3` | `integer` | 通用参数 3，来自配置表 `BuffTypeParam3` |
| `P4` | `integer[]` | 通用参数数组 4（`nil` 时用空常量表代替，避免 GC 压力） |
| `P5` | `integer\|StatusModifyType` | 通用参数 5 |
| `P6` | `integer[]` | 通用参数数组 6（`nil` 时用空常量表代替） |
| `battle` | `Battle` | 战场全局对象引用，`destroy` 时置 `nil` |
| `fromJinNangSource` | `Enum.BuffJinNangSource` | 锦囊来源枚举，仅锦囊类 Buff 有意义 |
| `debug` | `boolean` | 调试开关，默认 `true` |

---

## 3. Buff 生命周期

### 3.1 BuffState 枚举

```lua
-- Buff 状态机枚举：控制 Buff 从创建到销毁的完整生命周期，各状态按序流转不可逆
-- Enum.lua 第 296 行
BuffState = {
    None     = 0,  -- 初始，ctor 后尚未 init
    Active   = 1,  -- 已激活，每回合参与判断
    Deactive = 2,  -- 失活，不触发但仍挂在 owner 身上
    Destroy  = 3,  -- 已标记销毁，等待帧末清除
}
```

### 3.2 完整生命周期流转

```
BuffCreator.Create()
  │
  ├─ buff.ctor()          -- 字段零值初始化
  ├─ 字段赋值             -- id/buffId/owner/caster/battle/info/addCase
  └─ buff:init()          -- 从配置表读取 P1~P6、propsModify、fightTags
       │  state = Active（默认）
       │
       ▼
  [挂载到 owner.buffs]
       │
       ├─ 每回合 StartTurn/StopTurnAction 阶段
       │    └─ BattleBuffComp 按 BuffConfig 顺序遍历，调用各钩子
       │
       ├─ remainLifetime 归零 或 外部调用 SetDestroyFlag()
       │    └─ state = Destroy，isDestroy = true
       │
       ├─ 帧末 / 阶段末 移除脏标记的 Buff
       │    └─ buff:destroy()  -- 清空所有字段引用，触发 onDestroy 事件
       │
       └─ 从 owner.buffs 中移除
```

### 3.3 关键方法说明

**`init()`**（第 101 行）：从 `self.info` 读取配置参数，初始化 `propsModify`、`fightTags`、`remainLifetime`，将 `state` 设为 `Active`。返回 `true` 表示初始化成功。

**`ReduceBuffLifetime()`**（第 175 行）：按以下优先级依次消耗寿命：
1. 若 `noCDCount > 0`，免除一次 CD（减 `noCDCount`）
2. 否则若 `hasExtralLifetime == true`，先消耗额外回合标志
3. 否则 `remainLifetime -= 1`，归零则返回 `true`（通知调用方移除）

**`SetDestroyFlag(remCase?)`**（第 218 行）：幂等，多次调用安全。设置 `state = Destroy`、`isDestroy = true`，并通知 `owner` 检查是否需要联动添加新 Buff（`BuffOnDestroyCheckAddBuff`）。

**`destroy()`**（第 150 行）：先触发 `onDestroy` 事件，再将所有字段置 `nil` 释放引用，防止循环引用导致 GC 无法回收。

---

## 4. 钩子模式：6 个常用方法

基类将这些方法声明为可选字段（类型为 `function|nil`），子类若需要某个时机则在自身定义同名函数覆盖。调用方在调用前先判空（`if buff.CheckCombatSkillCond ~= nil then`）。

### 4.1 CheckCombatSkillCond

```lua
-- 对冲技能（主动技）阶段钩子：判断 Buff 是否在本次技能结算中生效
-- 返回 true 执行 Buff 效果，false 则跳过；分为技能前/后两轮调用
---@field public CheckCombatSkillCond
---   (fun(self, attacker, defender, isAttacker, skillData, effPhase):boolean)?
```

**触发时机**：对冲技能（主动技）结算阶段，分为技能前（StartCombat）和技能后（StopCombat）两轮。

**作用**：判断此 Buff 在当前对冲战斗中是否生效。返回 `true` 表示生效并执行 Buff 效果，返回 `false` 跳过。

**参数说明**：
- `attacker`：技能发起方英雄
- `defender`：技能承受方英雄
- `isAttacker`：`owner` 是否为技能发起方（`true`=攻方，`false`=守方）
- `skillData`：技能配置数据
- `effPhase`：触发阶段枚举（技能前/技能后）

### 4.2 CheckBFSkillCond

```lua
-- 战场技（BFSkill）阶段钩子：与 CheckCombatSkillCond 类似，但用于 BF 技能结算
-- target 可能为单个英雄、英雄数组或 nil（群体技能/无目标场景）
---@field public CheckBFSkillCond
---   (fun(self, attacker, target, isMultiTarget, skill, effPhase):boolean)?
```

**触发时机**：战场技（BFSkill）结算阶段。战场技目标可能是多个英雄，故 `target` 为 `BattleHero|BattleHero[]|nil`。

**作用**：与 `CheckCombatSkillCond` 类似，决定 BF 技能阶段此 Buff 是否触发。

### 4.3 CheckTurnCond

```lua
-- 回合开始阶段钩子：每个新回合开始时判断 Buff 是否触发
-- 主要用于回合型 Buff，如属性刷新、新回合施加 Buff 等
---@field public CheckTurnCond
---   (fun(self, turnID, effPhase):boolean)?
```

**触发时机**：每个新回合开始（`StartTurnBuff` 阶段）。主要用于回合型触发 Buff，如 `PropertiesModify`、`NewRoundAddBuff`、`NewRoundBFSkill` 等（见 `BuffConfig.StartTurnBuff`）。

**参数说明**：
- `turnID`：当前回合 ID
- `effPhase`：触发阶段枚举

### 4.4 CheckTurnActionCond

```lua
-- 行动结束阶段钩子：每次英雄完成行动后判断 Buff 是否触发
-- 覆盖 HealOverTime、DamageOverTime、DoubleMove 等持续效果类型
---@field public CheckTurnActionCond
---   (fun(self, turnID, actionIndex, effPhase):boolean)?
```

**触发时机**：每次英雄行动结束（`SopTurnActionBuff` 阶段），包括 `HealOverTime`、`DamageOverTime`、`DoubleMove`、`AddBuff` 等类型。

**参数说明**：
- `actionIndex`：当前回合内的行动序号（同一回合内可能有多次行动，如再动）

### 4.5 CheckNeverDie

```lua
-- 不屈钩子：伤害结算后 owner HP≤0 时调用，返回 true 拦截此次致命伤害
-- 典型实现：将 HP 设为 1 并触发复活特效
---@field public CheckNeverDie
---   (fun(self, turnId, isAttacker, deathCause):boolean)?
```

**触发时机**：伤害结算后，当 `owner` HP ≤ 0 时，由 `BattleBuffComp:DoDiedBuffByAllHeros` 检查不屈 Buff。

**作用**：返回 `true` 表示此次死亡被不屈 Buff 拦截，英雄以 1 HP 复活（或执行子类定义的复活逻辑）。

### 4.6 DoOtherDiedBuff

```lua
-- 响应"他人死亡"事件的钩子：战场上任意其他英雄确认死亡后，遍历全场 Buff 调用
-- 用于 Harvester（收割者）等类型，在他人阵亡时获得增益
---@field public DoOtherDiedBuff function|nil
```

**触发时机**：战场上任意其他英雄确认死亡后，由 `BattleBuffComp` 遍历全场存活英雄的 Buff，找到带 `Harvester`（收割者）等类型的 Buff 调用此钩子。

**作用**：响应"他人死亡"事件，如获得属性增益、触发特殊效果等。与之相关的配置分类为 `BuffConfig.OtherDiedBuff = { Harvester }`。

---
## 5. BuffConfig 分类：性能分类的意义

`BuffConfig.lua` 不存储任何 Buff 数值，它是**调度顺序表**和**分类索引**。核心分类：

### 5.1 触发顺序表（数组形式）

```lua
-- 格式：{ buffType, 触发者身份(1=攻方, 2=守方, 3=特殊) }
-- 对冲技能触发顺序表：数组元素 {buffType, 触发方身份(1=攻方,2=守方,3=特殊)}，严格按序遍历
-- 顺序错误会导致属性计算时序 Bug，注释中标注了「下面的 buff 要放在最后执行」
StartCombatSkillBuff = {
    {CombatAttachBuff, 1},  -- 攻方附着 Buff 最先
    {CombatHeal, 1},
    ...
    {CombatPropertiesModify, 1}, -- 属性修改类最后
}
```

**作用**：`HeroSkillComp`（或对应调度器）按此数组顺序遍历全场英雄的 Buff，保证触发顺序确定性。顺序错误会导致属性计算时序 Bug。注释中明确标注了「下面的 buff 要放在最后执行」等约束。

涵盖阶段：`StartCombatSkillBuff / StopCombatSkillBuff / StartBFSkillBuff / StopBFSkillBuff / StartTurnBuff / SopTurnActionBuff` 等。

### 5.2 StaticBuff（静态 Buff）

```lua
-- 静态 Buff 分类表：add 时即刻生效，无固定触发时机，不配置 CD（配置了属于 Bug）
-- 每次使用前需做有效性检查，典型如 PropertiesModify 在存活期间持续生效
StaticBuff = {
    [AddSkillLevel] = true,
    [BanSkill]      = true,
    [PropertiesModify] = true,
    [Immune]        = true,
    -- ... 共 20+ 项
}
```

**含义**：没有固定触发时机，添加（`add`）时即生效，每次使用前需做有效性检查。**不配置 CD**（否则属于配置 Bug）。典型例子：`PropertiesModify`（属性加成）在英雄存活期间持续生效，不需要每回合重新触发。

### 5.3 PropertiesModifyBuff（属性变更类）

```lua
-- 属性修改类 Buff 分类：HeroBuffAttrComp 扫描此表汇总最终属性值
-- 触发式属性 Buff 有严格时序——技能前末尾生效、技能后开头失效
PropertiesModifyBuff = {
    [PropertiesModify]        = true, -- 静态
    [SoldierAttributeModify]  = true, -- 静态
    [CombatPropertiesModify]  = true, -- 触发式（技能前生效，技能后失效）
    [DistancePropertiesModify]= true, -- 触发式
    [Charge]                  = true, -- 触发式
}
```

**含义**：凡是修改 `propsModify` 字段影响属性计算的 Buff 都列于此。触发式属性 Buff 有严格时序要求：必须在**技能前所有 Buff 执行结束时生效**，在**技能后所有 Buff 执行开始前失效**。`HeroBuffAttrComp` 会扫描此分类的 Buff 来汇总最终属性值。

### 5.4 CanBackBuff（可回退类）

```lua
-- 可回退 Buff 分类：失活后需要回退副作用的 Buff 类型
-- 如 ClassChange 销毁时需还原原始阵型，框架调用子类回退逻辑
CanBackBuff = {
    [SkillChange]     = true,
    [AddSkillLevel]   = true,
    [ExileBasicCard]  = true,
    [ClassChange]     = true,
    -- ...
}
```

**含义**：失活后需要回退副作用的 Buff。例如 `ClassChange`（换阵型）在 Buff 销毁时需还原原始阵型，框架会调用子类的回退逻辑。

### 5.5 SelfDiedBuff / OtherDiedBuff

```lua
-- 死亡相关 Buff 分类：伤害后收集死亡英雄，按 不屈→自身死亡→他人死亡 顺序触发，不可颠倒
SelfDiedBuff  = { DieAttachBuff }             -- 自身死亡时触发
OtherDiedBuff = { Harvester }                 -- 他人死亡时触发
```

`BattleBuffComp:DoDiedBuffByAllHeros` 在伤害后收集死亡英雄，优先触发不屈（NeverDie），再依次触发 SelfDiedBuff → OtherDiedBuff，顺序不可颠倒。

---

## 6. BuffCreator 工厂：根据 buffId 创建正确子类

`BuffCreator.lua` 暴露单一函数 `Create`，是 Buff 唯一的实例化入口。

```lua
-- BuffCreator.lua 第 5-89 行：类型注册表
-- 类型注册表：模块加载时一次性 require 所有子类，避免运行时动态加载延迟
-- 用 BuffType 枚举值作为 key 映射到对应子类，无匹配时降级为 BuffDefault
local BuffClasses = {
    [CDataEnum.BuffType.PropertiesModify]  = require("Logic.Battle.Buff.BuffPropertiesModify"),
    [CDataEnum.BuffType.HealOverTime]      = require("Logic.Battle.Buff.BuffHealOverTime"),
    [CDataEnum.BuffType.NeverDie]          = require("Logic.Battle.Buff.BuffNeverDie"),
    [CDataEnum.BuffType.Chain]             = require("Logic.Battle.Buff.BuffChain"),
    -- ... 共 60+ 项
}

-- BuffCreator.lua 第 98-124 行：工厂函数
-- 工厂函数 Create：唯一外部入口，根据 buffId 查配置表 → 确定子类 → 实例化 → 赋值 → init → 返回
local function Create(addCase, buffId, owner, battle, caster)
    local data = battle.dataMgr:GetData("BuffInfo", buffId) or {}
    local buffType = data.BuffType
    local BuffClass = BuffClasses[buffType]  -- 按类型找到对应子类

    local buff = BuffClass ~= nil and BuffClass() or BuffDefault()  -- 兜底

    -- 统一赋值公共字段
    buff.id       = owner.buffIdCreator:GetNextBufId()
    buff.buffId   = buffId
    buff.info     = data
    buff.battle   = battle
    buff.owner    = owner
    buff.caster   = caster
    buff.initActive = not CreateDeactiveBuff[buffType]  -- 绝大多数默认激活
    buff.addCase  = addCase

    buff:init()   -- 从 info 读取 P1~P6、propsModify、fightTags 等
    return buff
end
```

**关键设计点**：
- `BuffClasses` 在模块加载时就 `require` 所有子类，避免运行时动态加载的延迟。
- `CreateDeactiveBuff` 表用于声明少数需要延迟激活的类型（当前为空，预留扩展）。
- `BuffDefault()` 兜底保证配置表中有 buffId 但代码尚未实现子类时不会崩溃，只是 Buff 不会有任何额外行为。

---

## 7. BattleBuffComp 全局调度

`BattleBuffComp` 作为 `Battle` 的组件（`class.Component`），负责**全局**（跨所有队伍、所有英雄）的 Buff 协调，而每个英雄自身的 Buff 增删由 `HeroBuffComp` 负责。

### 7.1 回合开始（StartTurn）

```lua
-- 调度伪代码（实际分散在 HeroTurnComp / Battle 的回合流程中）
-- 遍历全场所有队伍、所有存活英雄，按 BuffConfig.StartTurnBuff 优先级顺序调用 Buff 钩子
for each team:
    for each hero (alive):
        -- 按 BuffConfig.StartTurnBuff 中的优先级顺序
        for buffType, priority in StartTurnBuff:
            hero:CheckTurnBuff(buffType, turnId, EffPhase.Start)
```

`BuffConfig.StartTurnBuff` 以哈希表形式存储优先级：

```lua
-- StartTurnBuff 优先级哈希表：数值越小越先执行，属性刷新(10200)先于新回合施加 Buff(10300)
StartTurnBuff = {
    [PropertiesModify]     = 10200,
    [NewRoundAddBuff]      = 10300,
    [NewRoundHealOverTime] = 10400,
    [NewRoundBFSkill]      = 10500,
}
```

数值越小越先执行，保证属性刷新（10200）先于回合末施加新 Buff（10300）。

### 7.2 行动结束（StopTurnAction）

```lua
-- BuffConfig.SopTurnActionBuff 为数组，顺序即执行顺序
-- SopTurnActionBuff 执行顺序数组：每次英雄行动结束后按序调用，再动类优先于持续效果
-- 顺序直接决定游戏行为——DoubleMove 必须在 HealOverTime 之前执行
SopTurnActionBuff = {
    DoubleMove,   -- 再动类（获得额外行动）
    HealOverTime, -- 持续回血
    DamageOverTime,
    Chain,        -- 铁索连环
    RemoveDebuff,
    AddBuff,
    BFSkill,
    RemoveCD,
    NewTurn,      -- 回合刷新类
}
```

`BattleBuffComp` 还提供：

| 方法 | 作用 |
|------|------|
| `OnStopTurnActionCheckBuffDestroyFlag(actionHeroId)` | 遍历全场，将 `isOnce==true` 且 `caster==actionHeroId` 的 Buff 标记为销毁 |
| `DoDiedBuffByAllHeros(attacker, callback)` | 伤害后死亡处理：不屈 → 自身死亡 Buff → 他人死亡 Buff，全程异步回调 |
| `RerfeshAllAuraBuffs()` | 遍历全场刷新光环 Buff（`GeneralAura` 类型） |
| `CheckAllBuffActiveOnAuraTime()` | 光环刷新时机，逐个调用 `buff.checkActiveOnAuraTime` 钩子 |
| `AllEntityCanBackBuffCheckState()` | 遍历全场执行可回退 Buff 的状态检查 |

---

## 8. 如何添加一个新 Buff（实践指南）

**不需要修改 `BattleBuffComp`**，只需以下 3 步：

### 步骤一：确定 BuffType

在 `CDataEnum.BuffType`（配置表枚举）中新增一个类型值，例如 `MyCustomBuff = 9999`。

### 步骤二：新建子类文件

新建 `Client/Assets/Script/Lua/Logic/Battle/Buff/BuffMyCustom.lua`：

```lua
-- 引入 class 工具模块和 BuffBase 基类，class.Class 提供面向对象继承机制
local class = require("Common.Class")
local BuffBase = require("Logic.Battle.Buff.BuffBase")

---@class BuffMyCustom:BuffBase
-- 通过 class.Class 创建子类：第一个参数是类名（调试用），第二个参数是父类
local BuffMyCustom = class.Class("BuffMyCustom", BuffBase)

-- ctor：先调用父类 BuffBase.ctor 初始化公共字段（id/buffId/state 等），再初始化子类特有字段
function BuffMyCustom:ctor()
    BuffBase.ctor(self)
    -- 子类特有字段初始化（如有）
end

-- 覆盖关心的钩子：每次行动结束触发
---@param turnID integer
---@param actionIndex integer
---@param effPhase Enum.BuffEffectivePhase
---@return boolean
-- 覆盖 CheckTurnActionCond 钩子：每次 owner 行动结束后框架调用此方法判断 Buff 是否触发
function BuffMyCustom:CheckTurnActionCond(turnID, actionIndex, effPhase)
    -- 仅在行动结束后阶段生效
    if effPhase ~= Enum.BuffEffectivePhase.Stop then
        return false
    end
    -- 通用条件检查（ConditionType1/2 等配置表条件）
    if not self:CheckBuffCondition(nil, nil, true) then
        return false
    end

    -- 执行效果：给 owner 治疗
    local healVal = self.P1  -- 从配置表参数读取
-- 效果执行：从配置表参数 P1 读取治疗量，调用 owner:AddHp 增加生命值
    self.owner:AddHp(healVal, self)
    return true
end

-- 返回类定义供 require 调用方使用，完成模块导出
return BuffMyCustom
```

### 步骤三：在 BuffCreator 注册

在 `BuffCreator.lua` 的 `BuffClasses` 表中添加一行：

```lua
-- 注册新子类：BuffType 枚举值 → require 子类模块路径，BuffCreator 根据此表创建实例
[CDataEnum.BuffType.MyCustomBuff] = require("Logic.Battle.Buff.BuffMyCustom"),
```

### 可选步骤四：加入 BuffConfig 调度序列

如果新 Buff 需要在某个特定阶段被遍历，将其加入 `BuffConfig.lua` 对应的数组中：

```lua
-- 将新 Buff 类型加入 SopTurnActionBuff 执行顺序数组，位置决定与其他 Buff 的执行先后
SopTurnActionBuff = {
    ...
    MyCustomBuff,  -- 加在适当位置
}
```

若属于 StaticBuff（add 时即生效，无固定触发时机），加入 `StaticBuff` 哈希表即可：

```lua
-- 静态 Buff 只需加入 StaticBuff 哈希表，不需要加入调度顺序数组
StaticBuff = {
    ...
    [MyCustomBuff] = true,
}
```

---

## 9. 代码示例：BuffBase.lua 字段定义和 ctor（第 1–99 行）

```lua
-- BuffBase.lua 第 13-59 行（EmmyLua 注解，精简部分条目）
-- 类声明注解：标记 BuffBase 继承自 Class 基类
---@class BuffBase:Class
---@field public id integer                   -- 实例ID(在owner身上的唯一标识)
---@field public buffId integer               -- Buff配置ID
---@field public owner BattleHero             -- BUFF拥有者
---@field public caster BattleHero|nil        -- BUFF施加者(可以为nil)
---@field public isActive boolean             -- 是否生效(主要目的:代码执行效率提升)
---@field public isBufCoolDown boolean        -- 是否冷却中
---@field public state Enum.BuffState
---@field public isDestroy boolean
---@field public isEnabel boolean             -- 是否生效(是否可以使用)
---@field public isOnce boolean               -- 一次性的，触发后回合结束即销毁
---@field public color integer                --0 无色,1 黑色,2 红色
---@field public info BuffInfo                -- Buff配置
---@field public remainLifetime integer       --剩余回合数
---@field public hasExtralLifetime boolean    -- 是否有额外的1个回合
---@field public noCDCount number             --可以免CD的次数
---@field public battle Battle
---@field public propsModify table<integer, integer>
---@field public fightTags table<integer, boolean>
---@field public num integer                  --叠加层数
---@field public P1 integer
---@field public P2 integer
---@field public P3 integer
---@field public P4 integer[]
---@field public P5 integer|StatusModifyType
---@field public P6 integer[]
---@field public initTurnId integer
---@field public addCase Enum.BuffAddCase     -- 添加原因
---@field public remCase Enum.BuffRemCase     -- 移除原因
---@field public CheckCombatSkillCond (fun(self:BuffBase, ...):boolean)?
---@field public CheckBFSkillCond (fun(self:BuffBase, ...):boolean)?
---@field public CheckTurnCond (fun(self:BuffBase, ...):boolean)?
---@field public CheckTurnActionCond (fun(self:BuffBase, ...):boolean)?
---@field public CheckNeverDie (fun(self:BuffBase, ...):boolean)?
---@field public DoOtherDiedBuff function|nil
-- 通过 class.Class 创建 BuffBase 基类实例
local BuffBase = class.Class("BuffBase")

-- ctor：字段零值初始化（第 61-99 行）
-- ctor 构造函数：将所有字段初始化为安全的零值/空值，防止未初始化字段导致 nil 异常
function BuffBase:ctor()
-- 实例标识与上下文引用：id 唯一标识、buffId 配置 ID、owner 持有者、caster 施放者、battle 全局上下文
    self.id = 0
    self.buffId = 0
    self.owner = nil
    self.battle = nil
    self.caster = nil

-- 状态控制字段：state/initActive/isActive 控制激活态，isDestroy 防重入销毁，isEnabel 开关，isOnce 一次性标记
    self.state = Enum.BuffState.None
    self.initActive = false
    self.isActive = false   -- 遗留，计划删除
    self.isBufCoolDown = false
    self.isDestroy = false
    self.isEnabel = true
    self.isOnce = false

-- 配置驱动字段：从 BuffInfo 配置表读取的运行时数据，包括属性修改映射和战斗标签集合
    self.color = nil
    self.info = nil
    self.remainLifetime = 0
    self.hasExtralLifetime = false
    self.noCDCount = 0
    self.fightTags = {}
    self.num = 1
    self.initTurnId = 0
    self.isCompleted = true
    self.addCase = 0
    self.remCase = 0

-- 通用参数 P1~P6：从配置表 BuffTypeParam1~6 读取，子类按自身语义解读（治疗量、伤害系数、格子数等）
-- P4/P6 在 ctor 中置 nil，init() 中才赋值为 info.BuffTypeParam4 or constEmptyT，共享空表减少 GC 压力
    self.P1 = 0
    self.P2 = 0
    self.P3 = 0
    self.P4 = nil   -- init() 中赋值为 info.BuffTypeParam4 or constEmptyT
    self.P5 = 0
    self.P6 = nil   -- 同 P4

-- 事件系统：onDestroy 事件处理器，destroy 时触发所有注册的观察者回调
    self.onDestroy = EventHandler()
    self.debug = true
end
```

**注意** `P4` / `P6` 在 `ctor` 中初始化为 `nil`，在 `init()` 中才赋值为 `info.BuffTypeParam4 or constEmptyT`。`constEmptyT` 是模块顶层的 `local constEmptyT = {}` 常量空表，避免每个无参数组的 Buff 都分配新表，是一个重要的 GC 优化。

---

## 10. 练习题

**题 1（基础）**：

查看 `BuffHealOverTime`（`BuffHealOverTime.lua`），回答：它覆盖了哪个钩子？在钩子中如何计算每回合回血量？回血量和 `P1`、`P2` 的关系是什么？

**题 2（中级）**：

假设策划要新增一个 Buff，效果是「每回合开始时，若 owner 周围 2 格内有友军，则给 owner 加一层护盾」。

1. 应覆盖 `CheckTurnCond` 还是 `CheckTurnActionCond`？为什么？
2. 如何使用 `CheckBuffCondition` 复用配置表条件，而不是硬编码格子数？
3. 是否需要加入 `StaticBuff`？为什么？

**题 3（高级）**：

`SetDestroyFlag()` 第 228 行调用了 `self.owner:BuffOnDestroyCheckAddBuff(self)`。

1. 追踪这个调用（在 `HeroBuffComp` 中查找），说明它的作用。
2. 举一个需要在 Buff 销毁时联动添加新 Buff 的游戏场景。
3. 为什么这个逻辑在 `SetDestroyFlag` 而不是 `destroy` 中触发？两者的区别是什么？

---

## 11. 常见陷阱

**陷阱 1：在 `destroy()` 之后访问字段**

`destroy()` 会将 `owner`、`battle`、`info`、`P4`、`P6`、`propsModify` 等全部置 `nil`。如果在 `onDestroy` 事件回调中（或之后）访问这些字段会立即报错。正确做法：在注册 `onDestroy` 观察者时，提前缓存需要用到的值。

```lua
-- 错误示例
-- 错误写法：回调闭包直接引用 buff.info，但 destroy() 已将 info 置 nil，访问报错
buff.onDestroy:AddObserver(nil, function()
    log(buff.info.ID)  -- buff.info 已经是 nil！
end)

-- 正确做法
local infoId = buff.buffId  -- 提前缓存
-- 正确写法：注册回调前将 buffId 缓存到局部变量，闭包捕获的是安全的局部值副本
buff.onDestroy:AddObserver(nil, function()
    log(infoId)  -- 安全
end)
```

**陷阱 2：混淆 `isActive` 和 `state`**

`isActive` 是遗留字段，注释明确标注「2025.7.30 后删掉」。新代码**必须**用 `state == Enum.BuffState.Active` 判断激活状态，不要依赖 `isActive`。两者在极端情况下可能不一致。

**陷阱 3：PropertiesModify 类 Buff 忘记加入 PropertiesModifyBuff 表**

新写一个修改属性的 Buff 子类，若不在 `BuffConfig.PropertiesModifyBuff` 中注册，`HeroBuffAttrComp` 就不会扫描它，属性修改永远不会生效。症状：数值明明改了但英雄属性没变。

**陷阱 4：触发式属性 Buff 的时序错误**

`CombatPropertiesModify`、`DistancePropertiesModify`、`Charge` 等触发式属性 Buff 在 `StartCombatSkillBuff` 中被放在**数组末尾**，在 `StopCombatSkillBuff` 中被放在**数组开头**（见配置注释）。如果乱改顺序，会导致属性在错误的时间段生效，造成伤害计算 Bug。

**陷阱 5：isOnce 的清理依赖 actionHeroId**

`BattleBuffComp:OnStopTurnActionCheckBuffDestroyFlag` 只销毁 `caster.id == actionHeroId` 的一次性 Buff。如果 `caster` 为 `nil`（如地形 Buff），该 Buff 不会被此方法销毁，需要通过其他机制（如 `remainLifetime`）控制生命周期，否则会永久残留。

**陷阱 6：在 BuffCreator 注册前忘记添加 require**

新建子类文件后只在 `BuffConfig` 分类表中加了条目，却忘记在 `BuffCreator.lua` 的 `BuffClasses` 中添加 `require`，导致运行时创建的是 `BuffDefault` 实例，子类逻辑完全不执行，且不会报错，极难排查。

---

## 12. 扩展阅读

- `Client/Assets/Script/Lua/Logic/Battle/Buff/BuffBase.lua` — 基类全文（1583 行），包含所有通用条件判断逻辑
- `Client/Assets/Script/Lua/Logic/Battle/Buff/BuffConfig.lua` — 调度顺序表和分类索引（378 行）
- `Client/Assets/Script/Lua/Logic/Battle/Buff/BuffCreator.lua` — 工厂函数（127 行）
- `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleBuffComp.lua` — 全局调度组件（745 行），重点看 `DoDiedBuffByAllHeros`
- `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroBuffComp.lua` — 单英雄 Buff 增删管理
- `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroBuffAttrComp.lua` — 属性 Buff 汇总计算
- `Client/Assets/Script/Lua/Enum.lua` 第 294–363 行 — `BuffState`、`BuffAddCase`、`BuffRemCase` 枚举定义
