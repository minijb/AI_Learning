# 战斗系统学习计划

## 目标

系统掌握本项目（三国策略/战棋 RPG）的客户端战斗模块全貌，能够：

1. 独立阅读和理解战斗逻辑代码
2. 定位并修复战斗相关 Bug
3. 在现有架构上添加新的 Buff / 技能 / Trigger
4. 理解逻辑层与表现层的分离边界

## 技术背景要求

- 会 Lua 基本语法（table、闭包、metatables）
- 了解 Unity C# 基础（GameObject、MonoBehaviour 生命周期）
- 熟悉 xLua 桥接模式（`CS.` 命名空间访问 C#）

---

## 模块地图

```
游戏入口 (LuaGame.lua)
  └─ Stage 状态机
       └─ BattleStage.lua        ← 战斗场景入口，协调逻辑层+表现层
            ├─ Logic层 (SC通用，确定性)
            │    └─ Battle.lua                  ← 战斗主对象（组件宿主）
            │         ├─ BattleLoadComp         ← 战场加载 & 配置读取
            │         ├─ BattleTurnComp         ← 回合/行动顺序管理（最核心）
            │         ├─ BattleFightComp        ← 对冲战斗流程
            │         ├─ BattleMapComp          ← 地图/寻路/地形
            │         ├─ BattleTriggerComp      ← 胜负判定/触发器
            │         ├─ BattleLogicComp        ← 指令录制/快进/校验
            │         ├─ BattleBuffComp         ← Buff 生命周期管理
            │         ├─ BattleAIGroupComp      ← AI 组行为驱动
            │         ├─ BattleRegretComp       ← 悔棋
            │         ├─ BattleAchievementComp  ← 成就/战报
            │         └─ BattleReportComp       ← 战报快进
            │
            ├─ Entity层
            │    └─ BattleHero.lua             ← 战场单位（组件宿主）
            │         ├─ HeroComAttrComp       ← 基础属性（攻防血等）
            │         ├─ HeroSkillComp         ← 技能（主动/被动）
            │         ├─ HeroBFSkillComp       ← 战场技（BFSkill）
            │         ├─ HeroBuffComp          ← Buff 持有与管理
            │         ├─ HeroBuffAttrComp      ← Buff 对属性的修改
            │         ├─ HeroDamageComp        ← 伤害计算
            │         ├─ HeroTurnComp          ← 行动状态机（每角色）
            │         ├─ HeroMapComp           ← 格子位置
            │         ├─ AIBehaviorComp        ← AI 行为决策
            │         └─ AIAutoComp            ← 自动托管
            │
            ├─ Skill层
            │    ├─ CombatSkill.lua            ← 主动技能执行
            │    ├─ BattleSkillUtil.lua        ← 技能工具集（伤害/范围/检索）
            │    ├─ CombatField.lua            ← 对冲战场（攻方视角）
            │    ├─ CombatActor.lua            ← 对冲单体角色
            │    └─ BFSkill.lua               ← 战场技
            │
            ├─ Buff层
            │    ├─ BuffBase.lua              ← Buff 基类（所有 Buff 的父类）
            │    ├─ BuffConfig.lua            ← Buff 分类配置
            │    └─ Buff*.lua                ← 各种具体 Buff（约 60 个）
            │
            ├─ AI层
            │    ├─ AIUtil.lua               ← AI 工具集（优先级/评分）
            │    ├─ AIPickTarget.lua         ← 目标选择
            │    ├─ AIPickSkill.lua          ← 技能选择
            │    └─ AIPickSkillAtTarget.lua  ← 针对目标选技能
            │
            └─ 表现层 (Client-only)
                 └─ ClientBattle.lua         ← 客户端战斗对象（镜像逻辑层）
                      ├─ ClientBattleMapComp      ← 地图显示
                      ├─ ClientBattleFightComp    ← 对冲表现
                      ├─ ClientBattleSelectComp   ← 玩家选择
                      └─ ClientPerformManager     ← 剧情演出管理
```

---

## 学习路径

| # | 文件 | 主题 | 预计用时 |
|---|------|------|---------|
| 01 | `tutorials/01-architecture-entry.md` | 项目整体架构与战斗入口 | 1h |
| 02 | `tutorials/02-battle-class-components.md` | Battle 核心类与组件系统 | 1.5h |
| 03 | `tutorials/03-state-machine-turn-flow.md` | 战斗状态机与回合流程 | 2h |
| 04 | `tutorials/04-map-movement.md` | 地图系统与移动寻路 | 1.5h |
| 05 | `tutorials/05-battle-hero-entity.md` | BattleHero 实体与属性系统 | 1.5h |
| 06 | `tutorials/06-skill-system.md` | 技能系统（主动/战场技/对冲） | 2h |
| 07 | `tutorials/07-buff-system.md` | Buff 系统（基类/生命周期/扩展） | 2h |
| 08 | `tutorials/08-ai-system.md` | AI 决策系统（目标/技能选择） | 1.5h |
| 09 | `tutorials/09-client-presentation.md` | 客户端表现层（ClientBattle/VisEntity） | 1.5h |
| 10 | `tutorials/10-battle-verify-regret.md` | 战斗校验、快进与悔棋 | 1.5h |

**总预计时间**：约 16 小时

---

## 里程碑

- **M1（完成01-02）**：能独立浏览战斗代码，理解文件分工，不再迷路
- **M2（完成03-05）**：能跟踪一场完整战斗的运行流程，理解角色行动顺序
- **M3（完成06-07）**：能阅读任意 Buff/技能代码，能添加一个新的简单 Buff
- **M4（完成08-10）**：理解 AI 决策逻辑，理解战斗校验原理，具备独立 Debug 能力
