# 05 BattleHero 实体与属性系统

## 前置依赖

| 依赖 | 说明 |
|------|------|
| 教程 01 | 战斗系统架构总览，了解 Battle 对象与帧循环 |
| 教程 02 | 组件系统（class.AddComponents / class.Component）机制 |
| 教程 03 | 行动状态机与回合流程 |
| 教程 04 | 战场地图与格子移动 |

---

## 1. 继承层次

```
Entity  (Logic.Entity.Entity)
  └── BattleHero  (Logic.Entity.Battle.BattleHero)
```

`Entity` 是所有战场实体的基类，定义最小公约字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | integer | 实例 ID（战场内唯一） |
| `name` | string | 实体名称 |
| `battleState` | Enum.BattleState | 战斗状态枚举 |
| `entityType` | integer | 实体类型（HERO / SOLDIER…） |
| `entityStatus` | integer | 存活状态（Alive / Died…） |
| `moveType` | integer | 移动类型（Walk / Fly…） |
| `teamType` | Enum.Team | 所属阵营（Self / Friend / Enemy / Hide） |
| `isDied` | boolean | 是否已死亡 |
| `isVisible` | boolean | 是否可见 |
| `onDying` | EventHandler | 垂死事件（血条归零但角色尚在场） |
| `onDied` | EventHandler | 死亡事件（角色完全离场） |

`BattleHero` 在 Entity 基础上新增战场专用字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `battle` | Battle | 所属战斗对象引用 |
| `armyType` | ArmyTag | 兵种类型（步/骑/弓…），从 ClassInfo 加载 |
| `actionValue` | integer | 行动值，决定每轮行动先后顺序 |
| `addActionValue` | integer | 辅助行动值，`actionValue` 相同时做二次排序 |
| `autoActionValue` | integer | 玩家自动托管时使用的行动值 |
| `isInPerform` | boolean | 是否正处于剧情演出中 |
| `isReinforcement` | boolean | 是否为剧情产生的援军 |
| `clientEntity` | ClientBattleHero | 对应客户端表现对象（逻辑/渲染分离） |
| `delayCallbackList` | function[] | 隔帧延迟执行回调队列（下一帧执行） |
| `delayCallbackList2` | function[] | 本帧延迟执行回调队列 |

> **关键设计**：`actionValue` 在 `LoadClassInfo()` 时由配置表 ClassInfo 的 `BF_ActionValue`
> 字段写入；援军入场后若需调整行动顺序，通过 `SetAutoActionValue()` 修改并可选同步到战报二进制流。

---

## 2. 16 个组件一览

`class.AddComponents` 按以下顺序挂载，**顺序即初始化顺序**（也是 `ctor` 链的调用顺序）：

| # | 组件类 | 职责 |
|---|--------|------|
| 1 | `HeroDamageComp` | 伤害计算：物理/策略/战场伤害公式、暴击、减免、反弹 |
| 2 | `HeroComAttrComp` | 核心属性：基础属性值读写、士兵管理、格子坐标 |
| 3 | `HeroSkillComp` | 主动技（CombatSkill）管理：CD、释放条件、执行入口 |
| 4 | `HeroBFSkillComp` | 战场技（BFSkill）管理：行军/攻击/辅助类战场技 |
| 5 | `ComMoveComp` | 移动逻辑：寻路、步骤执行、动画同步 |
| 6 | `HeroBuffComp` | Buff 持有与生命周期：添加/移除/激活/失活/触发 |
| 7 | `HeroBuffAttrComp` | Buff 对属性的修改计算，提供所有 `Get属性()` 对外 API |
| 8 | `HeroBuffTerrainComp` | 地形 Buff：地形移动消耗修正映射 |
| 9 | `HeroBattleFightComp` | 对冲战斗（CombatField）：发起、参与、结算 |
| 10 | `AIBehaviorComp` | 每英雄 AI 决策：目标选取、技能选取、行动执行 |
| 11 | `AIAutoComp` | 玩家自动托管：代替玩家操控 Self 阵营英雄 |
| 12 | `HeroTriggerComp` | 触发器：订阅 BattleEventID 事件并执行响应逻辑 |
| 13 | `HeroTurnComp` | 行动状态机：回合开始/结束、再动/继续移动逻辑 |
| 14 | `HeroDebugComp` | 调试信息输出（仅开发期有效） |
| 15 | `HeroEquipComp` | 装备系统：将领随身装备的属性加成 |
| 16 | `HeroMapComp` | 格子缓存：可行走/可攻击格子数据的懒计算与脏标记 |

> 代码中有一行注释掉的 `DebugGraphicComp`，不计入运行期组件列表，实际共 16 个。

---

## 3. HeroComAttrComp 详解

**文件**：`Logic/Entity/Battle/Comp/HeroComAttrComp.lua`

### 3.1 基础属性字段

`setInitAttr()` 在 `ctor` 和 `clear` 时都会调用，保证对象池复用干净：

```lua
-- 基础属性——来自配置表 ClassLevelInfo（通过 LoadClassConnection 写入）
self.HP_INI  = 0   -- 生命基础值
self.AT_INI  = 0   -- 物攻基础值
self.SAT_INI = 0   -- 策攻基础值
self.DF_INI  = 0   -- 物防基础值
self.SDF_INI = 0   -- 策防基础值
self.CRI_INI     = 0   -- 暴击率基础值
self.CRI_VAL_INI = 0   -- 暴击值（暴击伤害倍率）基础值

-- 战场移动相关——来自配置表 ClassInfo（通过 LoadClassInfo 写入）
self.BFMovePoint_INI     = 0   -- 战场移动力基础值
self.BFAttackDistance_INI = 0  -- 战场攻击距离基础值

-- 运行期可变字段
self.curHp   = 0    -- 当前生命值
self.maxHP   = 100  -- 最大生命（经 GetMaxHP 计算后缓存）
self.bornTurn = 1   -- 出生回合数

-- 对冲战场专用
self.formationLine = 11  -- 前后排（11=前，默认）
self.preHP         = 0   -- 预计算 HP（对冲结算前暂存）
```

`modifyProperties["MaxHP"]` 是个特殊槽位：它既不等于 `HP_INI`，也不是最终 MaxHP，而是
"本次战斗中基础 HP 的当前值"（初始化为 `HP_INI`，某些机制可以在运行期修改它）。

### 3.2 属性加载顺序

英雄上阵时属性按以下顺序写入，后一步覆盖或叠加前一步：

```
1. LoadConfig(battle, teamType, generalId, level)
   └─ 从 GeneralInfo 读取星级、SoldierID 等
   └─ LoadClassConnection(classConnectionId, level)
      └─ 从 ClassLevelInfo 写入 HP_INI / AT_INI / SAT_INI / DF_INI / SDF_INI / CRI_INI / CRI_VAL_INI
      └─ self.HP = self.HP_INI  (同时初始化运行时字段)

2. LoadClassInfo(cInfoData)
   └─ 写入 armyType / moveType / bfMoveSpeed
   └─ 写入 BFMovePoint_INI / actionValue / BFAttackDistance_INI

3. LoadAttr()  ← 客户端从 scWorldHeroManager 注入装备/培养加成
   └─ 调用 BattleHeroAssign.AssignHeroAttr(...)

4. OnEnterBattle() → ResetAttr()
   └─ modifyProperties["MaxHP"] = HP_INI
   └─ maxHP = GetMaxHP()    ← 此时已加载全部 Buff，含 Buff 加成
   └─ curHp = maxHP
```

---

## 4. HeroTurnComp 详解

**文件**：`Logic/Entity/Battle/Comp/HeroTurnComp.lua`

### 4.1 行动状态枚举

`turnState`（类型 `Enum.HeroTurnState`）是英雄行动状态机的核心，取值含义：

| 状态值 | 含义 |
|--------|------|
| `None` | 空闲，未轮到该英雄 |
| `Start` | 本轮行动开始，触发行动前检查 |
| `InProgress` | 行动进行中（正在操作） |
| `Stop` | 本轮行动结束 |
| `NewTurn` | 已获得"再行动"资格（待进入） |
| `StartNewTurn` | 再行动开始 |
| `InNewTurn` | 再行动进行中 |
| `NewMove` | 已获得"再移动"资格（行动后额外移动一次） |
| `StartNewMove` | 再移动开始 |
| `InNewMove` | 再移动进行中 |
| `Continue` | 已获得"继续移动"资格（移动后额外再移动） |
| `StartContinue` | 继续移动开始 |
| `InContinue` | 继续移动进行中 |

### 4.2 关键字段

```lua
-- HeroTurnComp:ctor() 初始化
self.actionIndex           = 0      -- 本轮第几次行动（从 1 开始）
self.newTurnNoIndexIncrement = false -- 再动时不递增 actionIndex 的标志
self.isSkipTurnAction      = false  -- 是否跳过本次行动
self.isGroupAction         = false  -- 是否为群组行动
self.turnState             = Enum.HeroTurnState.None

self.hasNewTurn  = false  -- 拥有"再行动"资格（结算后触发）
self.hasNewMove  = false  -- 拥有"再移动"资格（行动完结算）
self.hasContinue = false  -- 拥有"继续移动"资格（移动后结算）
self.inNewTurn   = false  -- 当前处于再行动阶段中
```

`movePoint` 不在 HeroTurnComp 中持有，而是通过 `HeroBuffAttrComp:GetMovePoint()` 实时
计算（见第 7 节）。`actionIndex` 与 `turnId` 组合为 `turnInfoRecord` 的 key，控制该次
行动是否扣减技能 CD 和 Buff 生命周期——这使得"再动不扣 CD"成为可选行为。

### 4.3 状态转移关键方法

| 方法 | 触发时机 |
|------|----------|
| `TryStartAction(turnID, actionIndex, callback)` | 行动队列调度到该英雄时调用 |
| `StartTurnAction(turnID, actionIndex, inPerform)` | 确认开始行动，设置 `actionIndex` |
| `DoWait()` | 英雄选择待机，添加地形 Buff 并推进操作步骤 |
| `IsActing()` | 返回 `isUsingSkill or isMoving`，用于锁定操作 |
| `IsCanOperationNext()` | 是否可以把控制权交给下一个英雄 |
| `IsInNewMove()` | 当前是否处于"再移动"阶段 |
| `IsInContinue()` | 当前是否处于"继续移动"阶段 |

---

## 5. HeroMapComp 详解

**文件**：`Logic/Entity/Battle/Comp/HeroMapComp.lua`

### 5.1 字段

```lua
-- HeroMapComp:ctor()
self.canWalkGridMap    = nil   -- 可行走格子集合（key = (x<<16)|y, value = Vector2Int）
self.canAttackGridMap  = nil   -- 可攻击格子集合（同上编码）
self.canAOEGrids       = nil   -- AOE 范围格子列表
self.calcuteX          = -1   -- 上次计算时的格子 X（缓存 key）
self.calcuteY          = -1   -- 上次计算时的格子 Y（缓存 key）
self.calcuteMovePoint  = 0    -- 上次计算时的移动力（缓存 key）
self.calcutebfAttackDistance = 0  -- 上次计算时的攻击距离（缓存 key）
self.isGridDirty       = false    -- 脏标记，Buff 变动时置 true 强制重算
```

`X` / `Y`（英雄当前格子坐标，**从 0 开始**）存放在 `HeroComAttrComp` 中，
`HeroMapComp` 的缓存字段 `calcuteX/Y` 是上一次计算格子数据时的坐标快照，二者不同
时触发重算。

### 5.2 关键方法

| 方法 | 说明 |
|------|------|
| `HasValidGridDatas(px,py,terrainMap,movePoint,attackDist)` | 判断缓存是否仍然有效（坐标/移动力/地形均未变化且非脏） |
| `ClearGridDatas()` | 回收所有 Vector2Int 到对象池，清空三张格子表，重置缓存 key |
| `CheckXYInAttackRange(px,py)` | 检查坐标是否在可攻击集合中（先查 canWalkGridMap，再查 canAttackGridMap） |
| `CheckXYInAttackRangeByDistance(px,py)` | 仅凭曼哈顿距离快速判断，不依赖缓存数据 |

**格子 key 编码**（在多处出现）：
```lua
local key = (x << 16) | y   -- 其中 x = px+1, y = py+1（坐标从1偏移）
```

**与 Battle 对象的职责分界**：
- `Battle:SetEntityGridXY(id, teamType, x, y)` — 在战场全局格子占用表中标记
- `Battle:ClearEntityGridXY(teamType, x, y)` — 清除全局占用
- `HeroComAttrComp:SetGridXY(x, y)` — 更新英雄自身 X/Y 并通知 Battle 刷新
- `HeroMapComp:ClearGridDatas()` — 仅清理该英雄的**可行/可攻缓存**，不影响全局占用

---

## 6. 英雄属性修改的三层架构

最终对外暴露的属性值由三层叠加产生，全部实现在 `HeroBuffAttrComp`：

```
第一层：基础值（_INI 字段）
  HP_INI / AT_INI / SAT_INI / DF_INI / SDF_INI ...
  ↓ 由 LoadClassConnection → ClassLevelInfo 写入，战斗中不变

第二层：Buff 修改（遍历 self.buffs）
  offset（万分比乘法）：来自 General2_XXXMul 类型的 Buff
  addset（绝对加法）：来自 General2_XXXAdd 类型的 Buff
  ↓

  公式（以 MaxHP 为例）：
    maxHp = modifyProperties["MaxHP"]                -- 基础值
    maxHp = (maxHp * (10000 + offset) + 5000) // 10000  -- 乘法加成（四舍五入）
    maxHp = maxHp + addset                           -- 加法加成

第三层：对冲战斗 Buff 修改（HeroBattleFightComp 阶段额外叠加）
  对冲期间部分属性另有一套修改通道（CombatPropertiesModify）
```

**为什么用万分比（ScaleUp4 = 10000）而非浮点？**
战报要求在不同机器上严格帧同步，整数运算可消除浮点精度差异。`ScaleUp.Round4 = 5000`
是四舍五入修正项：`(base * (10000 + rate) + 5000) // 10000`。

**防无限递归快照**：`GetMaxHP()` 内部遍历 Buff 时，Buff 的激活条件可能又要查询
`GetMaxHP()`，形成循环。解决方案：在技能/行动关键时间点调用
`SetValueOfBreakRecursion()` 拍快照，将 `breakRecursion_Hero_LastMaxHP` 定格，
Buff 条件判断读快照而非实时值。

---

## 7. 代码示例

### 7.1 BattleHero 的 ctor 与 AddComponents

```lua
-- BattleHero.lua（节选）

-- 挂载 16 个组件（顺序决定 ctor 调用顺序）
class.AddComponents(BattleHero, {
    HeroDamageComp,
    HeroComAttrComp,
    HeroSkillComp,
    HeroBFSkillComp,
    ComMoveComp,
    HeroBuffComp,
    HeroBuffAttrComp,
    HeroBuffTerrainComp,
    HeroBattleFightComp,
    AIBehaviorComp,
    AIAutoComp,
    HeroTriggerComp,
    HeroTurnComp,
    HeroDebugComp,
    HeroEquipComp,
    HeroMapComp,
})

function BattleHero:ctor()
    BattleHero.super.ctor(self)   -- Entity:ctor()，初始化 id/teamType/isDied 等
    self.battle          = nil
    self.clientEntity    = nil
    self.armyType        = CDataEnum.ArmyTag.None
    self.actionValue     = 0
    self.addActionValue  = 0
    self.autoActionValue = 0
    self.isInPerform     = false
    self.isReinforcement = nil
    self.delayCallbackList  = nil
    self.delayCallbackList2 = nil
end
```

### 7.2 HeroComAttrComp 基础属性初始化

```lua
-- HeroComAttrComp.lua — setInitAttr()（节选）
self.HP_INI  = 0   -- 生命
self.AT_INI  = 0   -- 物攻
self.SAT_INI = 0   -- 策攻
self.DF_INI  = 0   -- 物防
self.SDF_INI = 0   -- 策防
self.CRI_INI     = 0
self.CRI_VAL_INI = 0
self.BFMovePoint_INI      = 0
self.BFAttackDistance_INI = 0

self.modifyProperties = {}
self.modifyProperties["MaxHP"] = 0   -- 运行期基础 HP 槽
```

### 7.3 GetMaxHP 完整实现

```lua
-- HeroBuffAttrComp.lua
function HeroBuffAttrComp:GetMaxHP()
    local maxHp = self.modifyProperties["MaxHP"]  -- 第一层：基础值
    local offset = 0   -- 乘法修正（万分比，来自 Buff）
    local addset = 0   -- 加法修正（绝对值，来自 Buff）

    for i = 1, #self.buffs do
        local buff = self.buffs[i]
        if buff.GetPropsModify ~= nil and (not buff.isDestroy) then
            local val = buff:GetPropsModify(General2_HPMul)  -- 乘法 Buff
            if val ~= nil then offset = offset + val end

            local valA = buff:GetPropsModify(General2_HPAdd) -- 加法 Buff
            if valA ~= nil then addset = addset + valA end
        end
    end

    -- 公式：先乘后加，万分比四舍五入
    maxHp = (maxHp * (ScaleUp.Scale4 + offset) + ScaleUp.Round4) // ScaleUp.Scale4
    maxHp = maxHp + addset
    return maxHp
end
```

---

## 8. 练习题

**题目一：追踪行动值来源**

给定一名英雄对象 `hero`，不查文件，仅通过字段和方法，写出一段 Lua 伪代码，
打印该英雄的 `actionValue`、`addActionValue`、`autoActionValue` 三个字段，并说明
哪个字段在 AI 控制时决定行动先后顺序、哪个在玩家自动托管时起作用。

---

**题目二：属性公式验证**

已知某英雄：`HP_INI = 500`，身上有两个 Buff：
- Buff A：`General2_HPMul = 2000`（即 +20%）
- Buff B：`General2_HPAdd = 100`（即 +100 绝对值）

请手算 `GetMaxHP()` 的返回值（`modifyProperties["MaxHP"]` 初始化为 `HP_INI`，
`ScaleUp.Scale4 = 10000`，`ScaleUp.Round4 = 5000`），并对比直接用浮点
`500 * 1.2 + 100` 的结果，说明整数方案与浮点方案的差异。

---

**题目三：格子缓存失效时机**

阅读 `HeroMapComp:HasValidGridDatas()` 的实现，列出所有会使缓存失效（返回 false）
的条件，并说明 `isGridDirty` 标记应该在哪些时机被置为 `true`（提示：查找
`isGridDirty = true` 在 Buff 系统中的赋值点）。

---

## 9. 常见陷阱

**陷阱 1：直接读 `_INI` 字段而不调用 `Get方法`**

```lua
-- 错误：忽略了 Buff 加成
local atk = hero.AT_INI

-- 正确：经过 Buff 层叠加的最终值
local atk = hero:GetAT()
```

`_INI` 字段是初始化时写入的裸配置值，不含任何 Buff 修改。所有战斗计算必须通过
`Get属性()` 系列方法取值。

---

**陷阱 2：在 Buff 条件中调用 `GetMaxHP` 导致无限递归**

`GetMaxHP` 内部遍历所有 Buff；若某个 Buff 的激活条件又调用 `GetMaxHP`，则无限循环。
正确做法：Buff 激活条件中读取 `hero.breakRecursion_Hero_LastMaxHP`（快照值），
而不是调用 `GetMaxHP()`。快照在每次行动/技能前后由
`Battle:SetValueOfBreakRecursion4AllTeams()` 统一刷新。

---

**陷阱 3：混淆格子坐标下标起始**

- `hero.X` / `hero.Y`：**从 0 开始**（在 `HeroComAttrComp` 注释中明确标注）
- `HeroMapComp` 计算格子 key 时做 `+1` 偏移：`local key = ((px+1)<<16)|(py+1)`
- `Battle:GetWorldPositionByIndex(X, Y)` 入参同样从 0 开始

如果把 UI 层从 1 开始的坐标直接传入逻辑层，会导致格子偏移一格，触发错误的碰撞检测。

---

**陷阱 4：`modifyProperties["MaxHP"]` 不等于 `HP_INI`**

`modifyProperties["MaxHP"]` 是战斗中动态可修改的基础 HP 槽，初始化时等于 `HP_INI`，
但某些 Buff 或剧情机制可调用 `ModifyProperty("MaxHP", newVal)` 改写它。
`HP_INI` 是只读的配置基准值，永远不被覆盖。读最大生命，永远用 `GetMaxHP()`。

---

**陷阱 5：`hasNewTurn` / `hasNewMove` / `hasContinue` 三者区别**

| 标志 | 获得时机 | 能否放主公技 |
|------|----------|-------------|
| `hasNewTurn` | 行动结束后结算获得"再行动" | 可以 |
| `hasNewMove` | 行动结束后结算获得"再移动" | **不可以** |
| `hasContinue` | 移动一次后获得"继续移动" | — |

`IsCanOperationNext()` 在三个标志任意为 true 时都返回 false，阻止把操作权交出。
新手常把 `hasNewMove` 当"额外回合"处理，导致主公技被错误允许释放。

---

## 10. 扩展阅读

- **Buff 系统生命周期**：`BuffBase.lua` 约 1583 行，重点关注 `init` / `activate` /
  `deactivate` / `destroy` 四个阶段，以及 `GetPropsModify` 如何向 `HeroBuffAttrComp`
  暴露属性修改量。
- **对冲战场属性层**：`HeroBattleFightComp.lua` 中的 `CombatPropertiesModify` 类型
  Buff 是第三层属性修改的实现入口，仅在 CombatField 结算期间生效。
- **属性分配入口**：`Logic/Assign/BattleHeroAssign.lua` — `AssignHeroAttr` 函数，
  将客户端将领数据（培养值、装备加成）注入 `HeroComAttrComp`，是理解属性来源的完整
  链路终点。
- **AI 决策如何使用属性**：`AIUtil.lua` 的评分函数直接调用 `hero:GetAT()` 等方法；
  学习 AI 系统时需先掌握本教程的属性 API。
