# 战斗系统学习资源

## 1. 项目内部文档

目前 `openspec/` 目录不存在于本仓库。以下内部文档仍有参考价值：

| 路径 | 内容 |
|------|------|
| `docs/learning-plans/active/battle-system/plan.md` | 本学习计划总览：模块地图、学习路径、里程碑 |
| `docs/learning-plans/active/battle-system/tutorials/INDEX.md` | 教程导航：文件列表、关键源文件、建议学习顺序 |
| `Client/PersistentData/Debug/` | 运行时生成的战斗 Debug 信息文件（格式：`<时间>_<roleId>_<matchToken>_<battleId>_<operation>_debug.txt`） |
| `Client/PersistentData/Logs/` | 客户端运行日志，格式 `YYYY-MM-DD HH-MM-SS-<毫秒>.txt` |
| `Client/PersistentData/BattleInfoCmd.bin` | 最近一场战斗的完整指令录像（二进制，`cmsgpack` 编码）；可用 `BattleRebuild.lua` 重放 |
| `DesignData/技能.xlsx` | 技能配置表（`SkillAIType`、`BuffType`、伤害公式、CD 等） |
| `DesignData/状态表.xlsx` | Buff/状态完整配置（`BuffType` 枚举映射到具体 Buff 子类） |

---

## 2. 关键源文件对照表

### 2.1 战斗入口与流程

| 系统 | 最重要的源文件 |
|------|--------------|
| Lua 总入口 | `Client/Assets/Script/Lua/LuaGame.lua` |
| Stage 状态机 | `Client/Assets/Script/Lua/Stage/StageManager.lua` |
| 战斗 Stage | `Client/Assets/Script/Lua/Stage/BattleStage.lua` |
| Stage 跳转 | `Client/Assets/Script/Lua/Stage/GoToStage.lua` |
| 全局战斗数据 | `Client/Assets/Script/Lua/ClientBattle/BattleGlobalData.lua` |
| OOP 框架 | `Client/Assets/Script/Lua/Common/Class.lua` |

### 2.2 逻辑层（Logic/Battle）

| 系统 | 最重要的源文件 |
|------|--------------|
| 战斗主对象 | `Client/Assets/Script/Lua/Logic/Battle/Battle.lua` |
| 回合/行动管理 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleTurnComp.lua` |
| 对冲战斗流程 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleFightComp.lua` |
| 地图/寻路 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleMapComp.lua` |
| 胜负/触发器 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleTriggerComp.lua` |
| 指令录制/快进/校验 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleLogicComp.lua` |
| Buff 生命周期管理 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleBuffComp.lua` |
| AI 组驱动 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleAIGroupComp.lua` |
| 悔棋 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleRegretComp.lua` |
| Debug 信息保存 | `Client/Assets/Script/Lua/Logic/Battle/Comp/BattleDebugComp.lua` |
| 战斗重建/重放 | `Client/Assets/Script/Lua/Logic/Battle/BattleRebuild.lua` |

### 2.3 实体层（Logic/Entity/Battle）

| 系统 | 最重要的源文件 |
|------|--------------|
| 实体基类 | `Client/Assets/Script/Lua/Logic/Entity/Entity.lua` |
| 战场单位 | `Client/Assets/Script/Lua/Logic/Entity/Battle/BattleHero.lua` |
| 基础属性 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroComAttrComp.lua` |
| 伤害计算 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroDamageComp.lua` |
| 行动状态机 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroTurnComp.lua` |
| Buff 持有 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroBuffComp.lua` |
| Buff 属性修改 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroBuffAttrComp.lua` |
| 格子位置 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroMapComp.lua` |
| 主动/BF技能 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroSkillComp.lua`<br>`Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/HeroBFSkillComp.lua` |
| AI 决策 | `Client/Assets/Script/Lua/Logic/Entity/Battle/Comp/AIBehaviorComp.lua` |

### 2.4 技能层（Logic/Battle/Skill）

| 系统 | 最重要的源文件 |
|------|--------------|
| 主动技执行 | `Client/Assets/Script/Lua/Logic/Battle/Skill/CombatSkill.lua` |
| 技能工具集 | `Client/Assets/Script/Lua/Logic/Battle/Skill/BattleSkillUtil.lua` |
| 对冲战场 | `Client/Assets/Script/Lua/Logic/Battle/Skill/CombatField.lua` |
| 对冲单体 | `Client/Assets/Script/Lua/Logic/Battle/Skill/CombatActor.lua` |
| 战场技 | `Client/Assets/Script/Lua/Logic/Battle/Skill/BFSkill.lua` |

### 2.5 Buff 层（Logic/Battle/Buff）

| 系统 | 最重要的源文件 |
|------|--------------|
| Buff 基类 | `Client/Assets/Script/Lua/Logic/Battle/Buff/BuffBase.lua` |
| Buff 分类配置 | `Client/Assets/Script/Lua/Logic/Battle/Buff/BuffConfig.lua` |
| 各具体 Buff | `Client/Assets/Script/Lua/Logic/Battle/Buff/Buff*.lua`（约 60 个文件） |

### 2.6 AI 层（Logic/Battle/AI）

| 系统 | 最重要的源文件 |
|------|--------------|
| 决策入口 | `Client/Assets/Script/Lua/Logic/Battle/AI/AIBehaviorComp.lua` |
| 目标选择 | `Client/Assets/Script/Lua/Logic/Battle/AI/AIPickTarget.lua` |
| 技能选择 | `Client/Assets/Script/Lua/Logic/Battle/AI/AIPickSkill.lua` |
| 针对目标选技能 | `Client/Assets/Script/Lua/Logic/Battle/AI/AIPickSkillAtTarget.lua` |
| 工具函数集 | `Client/Assets/Script/Lua/Logic/Battle/AI/AIUtil.lua` |

### 2.7 表现层（ClientBattle / Graphic / ClientEntity）

| 系统 | 最重要的源文件 |
|------|--------------|
| 客户端战斗主对象 | `Client/Assets/Script/Lua/ClientBattle/ClientBattle.lua` |
| 地图显示 | `Client/Assets/Script/Lua/ClientBattle/Comp/ClientBattleMapComp.lua` |
| 对冲表现 | `Client/Assets/Script/Lua/ClientBattle/Comp/ClientBattleFightComp.lua` |
| 玩家选择交互 | `Client/Assets/Script/Lua/ClientBattle/Comp/ClientBattleSelectComp.lua` |
| 剧情演出管理 | `Client/Assets/Script/Lua/ClientBattle/Comp/ClientPerformManager.lua` |
| 可视化实体基类 | `Client/Assets/Script/Lua/Graphic/VisEntity/VisEntity.lua` |
| 骨骼动画状态机 | `Client/Assets/Script/Lua/Graphic/VisEntity/AnimationStateMachine.lua` |
| 特效管理 | `Client/Assets/Script/Lua/Graphic/VisEntity/VisFx.lua` |
| 客户端战场单位 | `Client/Assets/Script/Lua/ClientEntity/Battle/ClientBattleHero.lua` |
| 本地玩家单位 | `Client/Assets/Script/Lua/ClientEntity/Battle/ClientLocalHero.lua` |

---

## 3. Lua 进阶资源

### xLua

| 资源 | 地址 |
|------|------|
| xLua 官方 GitHub | https://github.com/Tencent/xLua |
| 快速入门教程 | https://github.com/Tencent/xLua/blob/master/Assets/XLua/Doc/XLua%E6%95%99%E7%A8%8B.md |
| API 参考 | https://github.com/Tencent/xLua/blob/master/Assets/XLua/Doc/XLua%E7%94%9F%E5%91%BD%E5%91%A8%E6%9C%9F%E4%B8%8E%E5%8F%8AAPI.md |
| 本地离线文档 | `ThirdLib/xLua-master/docs/public/v1/guide/` |
| 本地快速入门 | `ThirdLib/xLua-master/docs/source/src/v1/guide/tutorial.md` |
| 本地 API 说明 | `ThirdLib/xLua-master/docs/source/src/v1/guide/api.md` |
| 本地 GC 优化指南 | `ThirdLib/xLua-master/docs/source/src/v1/guide/gc-optimization.md` |

**项目中 xLua 的常见用法**：

```lua
-- 访问 C# 静态类
CS.UnityEngine.Debug.Log("message")
CS.Core.HudButtonManager.Inst:Init()

-- 获取 C# 组件
local go = CS.UnityEngine.GameObject.Find("MapRoot")
local transform = go.transform

-- 调用 C# 的 PersistentData 路径
local path = CS.Core.Utils.GetPersistentDataPath()
```

### EmmyLua 类型注解规范

本项目所有 Lua 文件均使用 EmmyLua 注解，需要安装 IntelliJ IDEA 的 **EmmyLua 插件** 或 VSCode 的 **Lua Language Server（sumneko）** 以获得类型检查和跳转支持。

| 资源 | 地址 |
|------|------|
| EmmyLua 注解语法文档 | https://emmylua.github.io/annotation.html |
| sumneko Lua Language Server | https://github.com/LuaLS/lua-language-server |
| sumneko 注解文档 | https://luals.github.io/wiki/annotations/ |
| 项目 EmmyLua Skill 规范 | `skill://emmylua-annotation` |

**项目注解约定**（摘自 `BattleTurnComp.lua`）：

```lua
---@class (partial) Battle        -- partial 表示跨文件分段声明同一个类
---@field public turnId integer   -- 字段类型声明
---@field public debug boolean

---@param operation string 操作方式
---@return boolean
function BattleTurnComp:ClientSaveBattleDebugInfos(operation)
    -- ...
end
```

> 注意：`(partial)` 标记由本项目自定义，用于将同一个组件化类（`Battle`、`BattleHero` 等）的字段声明分散到各 Component 文件中，避免单文件过大。

---

## 4. 调试工具

### 4.1 战斗日志路径

| 文件类型 | 路径 |
|----------|------|
| 客户端运行日志 | `Client/PersistentData/Logs/<日期时间>.txt` |
| 战斗 Debug 详情 | `Client/PersistentData/Debug/<时间>_<roleId>_<matchToken>_<battleId>_<operation>_debug.txt` |
| 战斗指令录像 | `Client/PersistentData/Debug/<时间>_<roleId>_<matchToken>_<battleId>_<operation>_BattleInfoCmd.bin` |
| 随机数 Debug | `Client/PersistentData/random_debug.txt` |

`<operation>` 的常见取值：`StartBattle`（战斗开始时保存）、`StopBattle`（战斗结束时保存）、`BattleRebuildOnClient`（本地重建/重放时保存）。

### 4.2 开启 DEBUG 模式

#### 开启战斗逻辑 DEBUG

`Battle` 对象上有 `self.debug` 布尔字段，由 `BattleDebugComp` 读取。当 `self.debug == true` 时，战斗结束时会自动调用 `ClientSaveBattleDebugInfos`，将每回合调试快照写入 Debug 文件：

```lua
-- Logic/Battle/Comp/BattleTurnComp.lua（客户端保存战斗 Debug 信息）
function BattleTurnComp:ClientSaveBattleDebugInfos(operation)
    if self.debug then
        if macroIsClient == true and self.isBattleRebuildOnClient ~= true then
            self.saveBattleDebugInfosOperation = operation
            local path = CS.Core.Utils.GetPersistentDataPath()
            -- 写出 debug.txt 和 BattleInfoCmd.bin
            self:SaveDebugInfoToFile(path, ...)
            self:SaveBattleInfoCmdToFile(path, ...)
        end
    end
end
```

将 `battle.debug = true` 后进入战斗即可在 `PersistentData/Debug/` 目录看到输出文件。

#### 开启 AI DEBUG

`AIPickSkill.lua` 和 `AIPickSkillAtTarget.lua` 文件顶部各有一个本地开关：

```lua
-- Logic/Battle/AI/AIPickSkill.lua  第 52 行
local isDebugAI = false   -- 改为 true 后，每次技能选择都会打印详细日志
```

开启后，AI 每次评估技能时都会调用 `log(...)` 输出英雄坐标、技能 ID、释放点等信息，可在 Unity Console 或日志文件中查看。

#### 查看实时日志

- **Unity Editor**：直接在 Unity Console 窗口过滤 `[Battle]` 前缀。
- **真机/包体**：日志写入 `Client/PersistentData/Logs/` 下的文本文件；Logger 通过 `CS.UnityEngine.Debug.Log` 输出，包体环境可接入 Bugly / CrashSight（见 `Client/Assets/CrashSight/`）。

#### 使用 BattleRebuild 重放战斗

`BattleInfoCmd.bin` 是一场战斗的完整指令录像，可在本地无网络环境下重放：

```lua
-- Logic/Battle/BattleRebuild.lua
local battle = BattleCreator(battleBasicInfo.battleId, nil)
battle.saveBattleDebugInfosOperation = "BattleRebuildOnClient"
battle.isBattleRebuildOnClient = true
battle.isClient = false
-- 随后传入 cmdList 逐条重放，最终对比结果是否与服务器一致
```

重放结束后会在 `PersistentData/Debug/` 再次写出 Debug 文件，可与服务器端日志对比以定位不一致的回合。
