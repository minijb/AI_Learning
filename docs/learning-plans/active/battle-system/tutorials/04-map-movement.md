# 04 地图系统与移动寻路

## 前置依赖

- 教程 01：架构入口与 Stage 状态机
- 教程 02：Battle 类与组件系统（`class.AddComponents`、Component 生命周期）
- 了解 Dijkstra 最短路径算法的基本概念

---

## 1. 地图数据结构

### 1.1 格子坐标系约定

地图使用**二维格子坐标系**。整个系统中存在两套坐标：

| 层 | 起点 | 使用场合 |
|----|------|---------|
| 外部逻辑层（BattleHero.X/Y、API 入参/出参） | **0** | 战斗逻辑、AI、技能 |
| 内部运算层（mapGrids 数组索引、Dijkstra 节点） | **1** | BattleMapComp 内部、Dijkstra 节点 ID |

源码注释（`BattleMapComp.lua` 第 84 行）明确写道：

```
-- lua实现的寻路，统一使用的原则是输入的参数都是以0开始的坐标，
-- 输出的也是以0开始的结果，中间运算是使用以1开始的坐标，
-- 外面逻辑层不需要考虑这个问题
```

因此，**所有对外 API 传入/返回的坐标都从 0 开始**，`BattleMapComp` 内部在操作 `mapGrids` 数组前统一执行 `x+1`/`y+1`。

### 1.2 MapGridElement：格子的完整描述

```lua
---@class MapGridElement
---@field id      integer            当前占据该格的英雄实体 ID（0 = 空格）
-- 阵营信息：战斗逻辑通过 camp 判断敌对/友方占格，决定通行或攻击目标
---@field camp    Enum.Team|nil      占据者的阵营
-- rangeFlag 标记该格是否在本次移动力可达范围内（Dijkstra 搜索后置位）
---@field rangeFlag  integer|nil     1 = 在本次行动的可达范围内
-- clickFlag 由 UI 交互层写入，控制格子高亮颜色（绿=可行走，红=可攻击）
---@field clickFlag  integer|nil     0=不可点击  1=可行走点击  2=可攻击点击
---@field terrain    integer         地形 ID（对应 BattleTerrainInfo 配置表）
-- 四种移动类型的消耗值：0 表示该类型无法通过此地形的网格
---@field foot    integer            步行移动力消耗
---@field ride    integer            骑行移动力消耗
---@field water   integer            水行移动力消耗
---@field fly     integer            飞行移动力消耗
-- 叠加地形效果（如技能产生的火焰/沼泽），为 nil 时使用原地形消耗
---@field terrainEff MapTerrainEffect|nil  叠加在该格上的地形效果
```

`mapGrids` 是一个**二维数组**，以 `mapGrids[x][y]` 访问（x、y 均从 1 开始）：

```lua
-- mapGrids 是整个地图逻辑层数据的核心容器，外部访问必须将 0 起始坐标 +1
---@field mapGrids MapGridElement[][]  逻辑层格子，坐标从 1 开始
```

构建过程（`LoadMap`，第 247–275 行）：

```lua
-- 按列优先遍历地图，构建二维格子数组
for x = 1, self.logicSizeX do
    local col = {}
    for y = 1, self.logicSizeY do
        -- 将二维坐标 (x,y) 映射到一维配置数组中的索引
        -- 线性索引：index = x + (y-1)*logicSizeX
        index = x + (y-1)*self.logicSizeX
        terrainId = data.Terrains[index]
        -- 初始化每个格子的默认状态：无人占据、无阵营
        local grid = {x = x, y = y, id = 0, camp = nil,
            terrain = terrainId,
            foot = foot, ride = ride, water = water, fly = fly}
        col[#col+1] = grid
    end
    tmpMapGrids[#tmpMapGrids+1] = col
end
```

### 1.3 MapTerrainEffect：叠加地形效果

```lua
---@class MapTerrainEffect
-- 格子逻辑坐标（外部 0 起始），标记效果影响的具体位置
---@field X           integer   格子逻辑坐标 X（从 0 开始）
---@field Y           integer   格子逻辑坐标 Y（从 0 开始）
---@field ID          integer   效果实例 ID
-- Replace 决定效果是替换原地形（如水面变冰地）还是仅叠加额外修正
---@field Replace     integer   是否替换原地形
-- 限时效果：startTurnID 标记生效回合，配合回合系统实现到期自动移除
---@field startTurnID integer   效果生效回合
---@field BuffID      integer   附加 Buff ID
---@field buffEndTurn integer   Buff 结束回合
---@field buffOwnerId integer   Buff 归属者 ID
---@field configData  TerrainsEf  配置表数据
```

---

## 2. 地形与移动力消耗

### 2.1 MoveIfElement：四种移动类型

```lua
-- MoveIfElement 定义单格对四种移动类型的消耗——0 表示不可通行
---@class MoveIfElement
---@field foot  integer  步行移动力消耗（0 = 不可通过）
---@field ride  integer  骑行移动力消耗
---@field water integer  水行移动力消耗
---@field fly   integer  飞行移动力消耗
```

`moveIfDicts` 是地形 ID 到 `MoveIfElement` 的字典，在 `LoadMap` 阶段从配置表 `BattleTerrainInfo` 预构建：

```lua
-- 从配置表 BattleTerrainInfo 预构建地形→移动消耗字典，避免运行时反复查表
for _, d in pairs(terrainInfodata) do
    -- 以地形 ID 为键，存储四种移动类型的消耗值
    self.moveIfDicts[d.ID] = {
        foot  = d.FootMoveIf,
        ride  = d.RideMoveIf,
        water = d.WaterMoveIf,
        fly   = d.FlyMoveIf,
    }
end
```

消耗值为 **0** 表示该类型单位**无法通过**此地形（不是零消耗，而是不可通行）。

### 2.2 移动消耗计算规则

部队通过一格的消耗取**将领与士兵的最大值**（`mapTileWeightCommon`，第 525–552 行）：

```lua
-- 部队移动消耗取将领与士兵的较大值——部队整体被最慢单位拖累
-- v1 = 将领在该地形的消耗，v2 = 士兵在该地形的消耗
if v1 > v2 then
    v = v1
else
    v = v2
end
```

地形效果（`mapTerrainMovePointModify`）作为修正量叠加在 v 之上，最终消耗不得低于 `MinWalkCost = 1`：

```lua
-- 先检查是否有地形效果修正表（可能为 nil）
if nil ~= mapTerrainMovePointModify then
    -- 应用特定地形的修正量（如山地 +1，沼泽 +2）
    if nil ~= mapTerrainMovePointModify[grid.terrain] then
        v = v + mapTerrainMovePointModify[grid.terrain]
    end
    -- key=0 为全地形修正，作用于所有格子（如全局"泥泞"效果）
    if nil ~= mapTerrainMovePointModify[0] then
        v = v + mapTerrainMovePointModify[0]
    end
end
-- 兜底：移动消耗不得低于最小行走消耗，保证即使"免费通行"也有基线代价
if v < MinWalkCost then v = MinWalkCost end
```
`mapTerrainMovePointModify[0]` 是**全地形修正**键（key=0 对所有地形生效）。

---

## 3. 寻路算法：Dijkstra

### 3.1 节点 ID 编码

Dijkstra 不直接传递 `(x, y)` 对，而是将坐标压缩为单个整数：

```lua
-- Dijkstra.lua 第 707–714 行
-- 将 (x,y) 打包为单个整数：x 高 16 位，y 低 16 位，可直接作 table key
function Dijkstra:GetNodeId(x, y)
    return (x << 16) | y      -- x 占高 16 位，y 占低 16 位
end

-- 从整数节点 ID 拆解回 (x,y)，反向解包操作
function Dijkstra:GetNodeXY(id)
    local x = id >> 16        -- 右移 16 位取出 x
    local y = id & 0xFFFF     -- 按位与掩码取出低 16 位 y
    return x, y
end
```

这个设计的好处是：节点 ID 可直接作为 Lua table 的整数键使用，避免了字符串拼接的内存分配，同时保持 O(1) 的格子去重判断。

### 3.2 DJFuncBind：类方法→纯函数适配器

Dijkstra 算法要求回调为**纯函数签名**（无 `self` 参数），而 `BattleMapComp` 的通行判断方法是面向对象的实例方法。`DJFuncBind` 解决这个阻抗：

```lua
-- BattleMapComp.lua 第 15–19 行
-- 适配器：将依赖 self 的实例方法包装为 Dijkstra 要求的纯函数回调
-- 闭包捕获 self + method，在调用时自动补上 self 参数
local function DJFuncBind(self, method)
    return function(...)
        return method(self, ...)
    end
end
```

```lua
-- BattleMapComp.lua 第 116–118 行
-- 在构造时预绑定三个核心回调，避免每次寻路分配新闭包（减少 GC 压力）
self.isCanPassCommonFunc    = DJFuncBind(self, self.isCanPassCommon)
self.isCanPassWithFlagFunc  = DJFuncBind(self, self.isCanPassWithFlag)
self.mapTileWeightCommonFunc = DJFuncBind(self, self.mapTileWeightCommon)
```

**为什么在 `ctor` 预绑定而不是每次传参时绑定？**  
每次 `DJFuncBind` 都会分配一个新闭包（Lua 中 `function` 是堆对象）。战斗中寻路调用频繁，预绑定可完全消除这部分 GC 压力。

### 3.3 canWalkGridMap 与 canAttackGridMap

这两个表是**中间运算缓存**，存储当前选中英雄的可达格和可攻击格：

```lua
-- canWalkGridMap：以节点 ID 为键缓存当前英雄的可达格，支持 O(1) 查询
---@field canWalkGridMap   table<integer, PosXY>  格子 key → 坐标（下标从 1 开始）
-- canAttackGridMap：在可达格基础上进一步计算可攻击格（含 AOE 范围）
---@field canAttackGridMap table<integer, PosXY>  格子 key → 坐标（下标从 1 开始）
```

- key 使用与节点 ID 相同的编码：`(x << 16) | y`（x、y 从 1 开始）
- 实际数据存在英雄对象 `hero.canWalkGridMap` 上，`BattleMapComp` 只持有引用（`ClickByGridIndex` 第 1398–1400 行）
- `IsCanClickWalk`（第 482–495 行）通过 key 查表，O(1) 判断格子是否可行走

填充流程：`ClickByGridIndex` → `CalcuteCanWalkGridsByGridIndex` → `Dijkstra:FindNodesWithinCostPack`

---

## 4. 关键 API

### 4.1 BattleMapComp 核心方法签名

```lua
-- 加载地图配置，构建 mapGrids 和 moveIfDicts
-- 调用时机：战斗初始化阶段，一次性完成地形数据加载
function BattleMapComp:LoadMap(mapId)

-- 计算指定英雄位置的可行走格集合（下标从 1 开始内部用）
-- 返回值: count（填充的格子数量）
-- 注意：结果写入 outCanWalkGrids 而非返回新表，复用表避免 GC
function BattleMapComp:CalcuteCanWalkGridsByGridIndex(
    outCanWalkGrids,          -- 输出表 table<nodeId, PosXY>
    ix, iy,                   -- 起点（从 1 开始）
    moveType, soldierMoveType,
    mapTerrainMovePointModify,
    movePoint,                -- 移动力上限
    teamType
) -> integer

-- 计算可攻击格（依赖 walkGridMap 已填充）
-- 必须先调用 CalcuteCanWalkGridsByGridIndex 再调用此方法
function BattleMapComp:CalcuteCanAttackGridsByGridIndex(
    outCanAttackGrids, walkGridMap,
    ix, iy,
    bfAttackDistance, bfAOERange
)

-- 寻路（对外接口，坐标从 0 开始）
-- 返回: found, pathNodes(从0开始的PosXY列表), cost
-- withFlag=true 时路径必须全部在 canWalkGridMap 范围内，用于限制行动范围
function BattleMapComp:GetActorMapPath(
    withFlag,     -- true=限制在 canWalkGridMap 范围内
    actor,        -- BattleHero
    sX, sY,       -- 起点（从 0 开始）
    eX, eY,       -- 终点（从 0 开始）
    isIgnoreBlock -- 是否忽略阻挡物
) -> boolean, PosXY[]|nil, integer

-- AI 专用寻路：目标点有人时忽略占格，路径不含目标点
-- 用于 AI 计算移动后攻击目标可达性，与玩家点击寻路逻辑略有不同
function BattleMapComp:GetActorMapPathIgnoreTargetBlock(
    actor, sX, sY, eX, eY
) -> boolean, PosXY[]|nil

-- 移动英雄到目标格（触发客户端表现）
-- onCompletedCallback 在移动动画播放完毕后回调，驱动后续技能释放等流程
function BattleMapComp:HeroMoveTo(
    withFlag, hero, x, y,
    onCompletedCallback,
    clientIsMove,
    isIgnoreBlock
)

-- 获取指定格上的实体 ID（坐标从 0 开始）
-- 返回 0 表示空格，非 0 表示该格有英雄占据
function BattleMapComp:GetHeroAtGridXY(x, y) -> integer

-- 更新英雄在 mapGrids 上的位置记录
-- 同时清空旧位置占用、填写新位置，并同步客户端渲染层
function BattleMapComp:RefreshEntityGridXY(id, teamType, oldX, oldY, newX, newY)

-- 获取地形 ID（坐标从 0 开始）
function BattleMapComp:GetTerrainID(x, y) -> integer

-- 坐标合法性检查（坐标从 0 开始）
function BattleMapComp:IsValidGridXY(x, y) -> boolean
```

### 4.2 格子 key 的计算方式

系统中格子 key 统一为：

```lua
-- 系统中统一的格子 key 编码：x 左移 16 位 | y，x、y 均从 1 开始的内部坐标
local key = (x << 16) | y    -- x、y 均从 1 开始
```

**例**：格子 (3, 5)（内部坐标）→ `key = (3 << 16) | 5 = 196613`

外部代码传入从 0 开始的坐标时，`IsCanClickWalk` 会自动加 1 再算 key：

```lua
-- 外部传入最小 0 起始坐标，内部自动转为 1 起始再编码 key
function BattleMapComp:IsCanClickWalk(x, y)  -- x, y 从 0 开始
    local rx = x + 1         -- 转换为内部 1 起始坐标
    local ry = y + 1
    local key = (rx << 16) | ry  -- 编码为整数 key
    -- O(1) 查表：canWalkGridMap 中不存在则说明该格不可达
    return self.canWalkGridMap[key] ~= nil
end
```

---

## 5. 逻辑层与客户端格子管理的分工

| 职责     | 逻辑层（Lua Logic/）                         | 客户端表现层（ClientBattle/）                                            |
| ------ | --------------------------------------- | ---------------------------------------------------------------- |
| 持有对象   | `battle.mapGrids`（`MapGridElement[][]`） | `CS.Core.GridManager.Inst`（C# GridManager）                       |
| 数据内容   | 地形、移动消耗、占据信息、可行走标记                      | 渲染用格子、高亮显示、点击事件                                                  |
| 更新时机   | 每次英雄移动、地形变化时实时更新                        | `ClickByGridIndex` 结束后由 `clientGridMgr:SetWalkGrids()` 等接口驱动     |
| 访问方式   | `self.mapGrids[x+1][y+1]`（从 1 的数组）      | `clientGridMgr:Clear()` / `clientGridMgr:SetWalkGrids()` 等 C# 接口 |
| SC 服务器 | 完整运行，维护 `mapGrids`                      | 不存在，`macroIsClient` 宏控制跳过                                        |

关键原则：**逻辑层不持有任何 Unity 对象引用**。`BattleMapComp.clientGridMgr` 字段仅在客户端赋值，服务器侧为 `nil`，所有涉及该字段的代码必须先判断 `self.isClient`。

`RefreshEntityGridXY` 是两层同步的典型示例：

```lua
-- 两层同步的核心方法：同时更新逻辑层 mapGrids 和客户端渲染层
function BattleMapComp:RefreshEntityGridXY(id, teamType, oldX, oldY, newX, newY)
    -- 通知客户端 C# 层更新渲染；服务器侧 self.isClient 为 false，跳过此分支
    if self.isClient and self.clientBattle then
        self.clientBattle:SetGridActorID(oldX, oldY, 0, 0)   -- 清空旧位置
        self.clientBattle:SetGridActorID(newX, newY, id, teamType)  -- 设置新位置
    end
    -- 更新逻辑层 mapGrids（服务器和客户端都执行）
    -- 边界检查：oldX/oldY 可能为 -1（英雄初始未放置），需跳过
    if oldX >= 0 and oldX < Xmax and oldY >= 0 and oldY < Ymax then
        local g = self.mapGrids[oldX+1][oldY+1]  -- 外部 0 起始转内部 1 起始
        g.id = 0       -- 清空旧格子的占据记录
        g.camp = nil
    end
    if newX >= 0 and newX < Xmax and newY >= 0 and newY < Ymax then
        local g = self.mapGrids[newX+1][newY+1]
        g.id = id      -- 在新格子上记录占据者信息
        g.camp = teamType
    end
end
```

---

## 6. 代码示例

### 6.1 MapGridElement 类型定义（真实代码）

```lua
-- BattleMapComp.lua 第 21–50 行

-- 地形叠加效果：Buff/技能产生的临时地形变更（如火焰地形、毒沼）
---@class MapTerrainEffect
---@field X integer
---@field Y integer
---@field ID integer
---@field Replace integer
---@field startTurnID integer
---@field BuffID integer
---@field buffEndTurn integer
---@field buffOwnerId integer
---@field configData TerrainsEf

-- 地图格子的完整运行时状态，是寻路、战斗、AI 的核心数据结构
---@class MapGridElement
---@field id integer
---@field camp Enum.Team|nil 被哪个Team占领
---@field rangeFlag integer|nil 1 可行走
---@field clickFlag integer|nil 0 不可点击 1 可点击(可行走) 2 可攻击
---@field terrain integer  地形ID(类型)
---@field foot integer  步行移动力消耗
---@field ride integer  骑行移动力消耗
---@field water integer 水行移动力消耗
---@field fly integer   飞行移动力消耗
---@field terrainEff MapTerrainEffect|nil

-- 移动消耗数据：每种移动类型通过一格所需的移动力，0 表示该类型不可通行
---@class MoveIfElement
---@field foot integer 步行移动力消耗
---@field ride integer 骑行移动力消耗
---@field water integer 水行移动力消耗
---@field fly integer 飞行移动力消耗
```

### 6.2 DJFuncBind 实现（真实代码）

```lua
-- BattleMapComp.lua 第 11–19 行

-- 将 类方法 method 绑定成 Dijkstra 接口期望的纯函数：
-- "给路径算法传回调"时，需要把面向对象的方法（依赖 self）包装成无 self 的函数签名。
-- Dijkstra 的接口期望的是纯函数回调，例如 (x, y, moveType, ...) -> bool/number，
-- 而类方法是 (self, x, y, ...)。
-- 闭包捕获 self + method，每次调用时自动插入 self 为第一参数
local function DJFuncBind(self, method)
    return function(...)
        return method(self, ...)
    end
end

-- ctor 中预绑定，复用闭包，避免寻路时重复分配（每次 DJFuncBind 都会产生新的堆对象）
self.isCanPassCommonFunc     = DJFuncBind(self, self.isCanPassCommon)
self.isCanPassWithFlagFunc   = DJFuncBind(self, self.isCanPassWithFlag)
self.mapTileWeightCommonFunc = DJFuncBind(self, self.mapTileWeightCommon)
```

### 6.3 完整寻路调用链（真实代码）

```lua
-- BattleMapComp.lua 第 584–603 行
-- 外部传入坐标从 0 开始，内部转为从 1 开始后交给 Dijkstra
function BattleMapComp:GetActorMapPath(withFlag, actor, sX, sY, eX, eY, isIgnoreBlock)
    -- 入口统一 +1：将外部 0 起始坐标转为内部 1 起始节点 ID
    local startPos = self.dijkstra:GetNodeId(sX+1, sY+1)  -- 坐标+1 转内部
    local endPos   = self.dijkstra:GetNodeId(eX+1, eY+1)

    -- 根据 withFlag 选择不同的通行判断函数：
    -- isCanPassCommonFunc：基于 mapGrids 实际占据情况判断
    -- isCanPassWithFlagFunc：额外限制必须在 canWalkGridMap 已标记的范围内
    local isCanPassFunc = self.isCanPassCommonFunc
    if withFlag == true then
        isCanPassFunc = self.isCanPassWithFlagFunc
    end

    -- 调用 Dijkstra 核心寻路，costLimit=-1 表示不限制总消耗（寻求最优解）
    local path, cost = self.dijkstra:FindPathQuick(
        startPos, endPos,
        self.mapTileWeightCommonFunc,
        -1,                                          -- costLimit=-1 表示无上限
        isCanPassFunc,
        actor.moveType, actor.soldiderMoveType,
        actor:GetBuffTerrainMovePointModifyMap(),
        actor.teamType, isIgnoreBlock
    )

    if path == nil then
        return false, nil, math_maxinteger   -- 无法到达，返回最大整数标记
    else
        local pathIndexFromZero = {}
        -- 将路径节点从内部 1 起始坐标转换回外部 0 起始坐标
        self.dijkstra:PointResultAdapter(path, pathIndexFromZero)  -- 坐标-1 转外部
        return true, pathIndexFromZero, cost
    end
end
```

---

## 7. 练习题

**练习 1**：坐标转换

已知地图尺寸为 10×8（logicSizeX=10, logicSizeY=8），外部逻辑层的英雄位置为 `(X=4, Y=2)`（从 0 开始）。

1. 写出访问该格子的 `mapGrids` 索引
2. 写出该格子的 Dijkstra 节点 ID（十进制）
3. 写出对应的 `canWalkGridMap` 查询 key

---

**练习 2**：移动力消耗

一名将领的移动类型为 `Enum.MoveType.Ride`（骑行），其士兵类型为 `Enum.MoveType.Walk`（步行）。目标格子的配置为 `foot=3, ride=2, water=0, fly=1`，且该格地形对骑行有 `+1` 的修正（`mapTerrainMovePointModify[terrainId] = 1`）。

计算部队通过该格的实际移动力消耗，并说明最终消耗不为 2 而是 4 的原因。

---

**练习 3**：代码阅读

阅读 `BattleMapComp:isCanPassCommon`（第 420–459 行）回答：

1. 当 `isIgnoreBlock = true` 时，函数直接返回什么？为什么 `mapTileWeightCommon` 在同样条件下不能也直接返回 0？
2. 当敌方单位（`teamType = Enum.Team.Enemy`）寻路时，哪种阵营的占格会阻止其通行？

---

## 8. 常见陷阱

### 陷阱 1：坐标系混用（最高频错误）

**错误写法**：
```lua
-- 直接用 hero.X（从0开始）访问 mapGrids——索引未 +1，越界或取错格子
local grid = self.mapGrids[hero.X][hero.Y]   -- ❌ 索引偏移1，或越界
```

**正确写法**：
```lua
-- 外部 0 起始坐标 +1 转换为内部 1 起始索引，正确访问 mapGrids
local grid = self.mapGrids[hero.X + 1][hero.Y + 1]  -- ✅
```

记忆口诀：**对外 0，内部 1，进函数加，出函数减**。

---

### 陷阱 2：移动消耗 0 ≠ 零消耗

`BattleTerrainInfo` 中 `FootMoveIf = 0` 意为**步行不可通过**，而非零消耗。`isCanPassCommon` 中的判断：
```lua
-- 判断通行：只有当移动消耗 > 0 时才可通行，0 意味着该移动类型无法通过此地形
if moveType == Enum.MoveType.Walk then
    return grid.foot > 0   -- 0 → false，不可通行
end
```

如果把 0 当作"免费通行"处理，会让步行单位穿越山地、水域等地形。

---

### 陷阱 3：在服务器侧访问 clientGridMgr

`clientGridMgr` 在服务器侧为 `nil`。不做保护直接调用会触发 nil 引用错误：
```lua
-- ❌ 直接调用 clientGridMgr，服务器侧为 nil 将导致运行时错误
self.clientGridMgr:Clear()

-- ✅ 先判断客户端环境和引用有效性，服务器侧自动跳过此分支
if self.isClient and self.clientGridMgr then
    self.clientGridMgr:Clear()
end
```
---

### 陷阱 4：canWalkGridMap 是英雄缓存，不是全局状态

`BattleMapComp.canWalkGridMap` 在每次 `ClickByGridIndex` 时被**替换**为当前选中英雄的缓存引用：

```lua
-- 直接引用赋值（非深拷贝）：每次 ClickByGridIndex 都会替换引用，之前英雄的数据被覆盖
self.canWalkGridMap = hero.canWalkGridMap
```

因此同一时刻它只反映**最后一次计算的那个英雄**的可达范围。在多英雄同时计算场景（AI 批量决策）中，不要依赖 `self.canWalkGridMap` 保存多个英雄的结果。

---

### 陷阱 5：`withFlag=true` 的前提条件

`isCanPassWithFlagFunc` 通过 `canWalkGridMap` 判断格子是否可行走。若在调用 `ClickByGridIndex` / `CalcuteCanWalkGridsByGridIndex` **之前**就传入 `withFlag=true` 寻路，`canWalkGridMap` 为空，所有格子都不可通行，寻路必然失败。

---

## 9. 扩展阅读

- `Client/Assets/Script/Lua/Common/Path/Dijkstra.lua`：完整 Dijkstra 实现，包含对象池（`m_touchedNodePool`）和路径版本号优化（`m_allCostPathVersion`）
- `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleMapComp.lua`（第 1400 行起）：`ClickByGridIndex` 完整流程，含缓存命中逻辑（`HasValidGridDatas`）
- `Client/Assets/Script/Lua/Logic/Entity/Battle/BattleHero.lua`：`hero.canWalkGridMap`、`hero.calcuteX/Y`、`hero.isGridDirty` 等缓存字段定义
- 教程 05：英雄实体系统（BattleHero 组件拆解）
