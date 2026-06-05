---
title: "战斗系统教程导航"
updated: 2026-06-05
---

# 战斗系统教程导航

## 教程总览

| # | 文件 | 主题 | 关键源文件 |
|---|------|------|-----------|
| 01 | [[01-architecture-entry]] | 项目整体架构与战斗入口 | `LuaGame.lua`<br>`Stage/StageManager.lua`<br>`Stage/BattleStage.lua`<br>`Stage/GoToStage.lua`<br>`ClientBattle/BattleGlobalData.lua` |
| 02 | [[02-battle-class-components]] | Battle 核心类与组件系统 | `Common/Class.lua`<br>`Logic/Battle/Battle.lua`<br>`Logic/Battle/Comp/BattleLoadComp.lua`<br>`Logic/Battle/Comp/BattleTurnComp.lua` |
| 03 | [[03-state-machine-turn-flow]] | 战斗状态机与回合流程 | `Logic/Battle/Battle.lua`<br>`Logic/Battle/Comp/BattleTurnComp.lua`<br>`Logic/Battle/Comp/BattleFightComp.lua`<br>`Common/StateManager.lua` |
| 04 | [[04-map-movement]] | 地图系统与移动寻路 | `Logic/Battle/Comp/BattleMapComp.lua`<br>`Logic/Entity/Battle/BattleHero.lua`（`HeroMapComp`）<br>`Logic/Battle/Comp/BattleTurnComp.lua`（移动指令段） |
| 05 | [[05-battle-hero-entity]] | BattleHero 实体与属性系统 | `Logic/Entity/Battle/BattleHero.lua`<br>`Logic/Entity/Entity.lua`<br>`Logic/Entity/Battle/Comp/HeroComAttrComp.lua`<br>`Logic/Entity/Battle/Comp/HeroDamageComp.lua`<br>`Logic/Entity/Battle/Comp/HeroTurnComp.lua`<br>`Logic/Entity/Battle/Comp/HeroBuffAttrComp.lua` |
| 06 | [[06-skill-system]] | 技能系统（主动/战场技/对冲） | `Logic/Battle/Skill/CombatSkill.lua`<br>`Logic/Battle/Skill/BFSkill.lua`<br>`Logic/Battle/Skill/CombatField.lua`<br>`Logic/Battle/Skill/CombatActor.lua`<br>`Logic/Battle/Skill/BattleSkillUtil.lua`<br>`Logic/Entity/Battle/Comp/HeroSkillComp.lua`<br>`Logic/Entity/Battle/Comp/HeroBFSkillComp.lua` |
| 07 | [[07-buff-system]] | Buff 系统（基类/生命周期/扩展） | `Logic/Battle/Buff/BuffBase.lua`<br>`Logic/Battle/Buff/BuffConfig.lua`<br>`Logic/Battle/Comp/BattleBuffComp.lua`<br>`Logic/Entity/Battle/Comp/HeroBuffComp.lua`<br>`Logic/Entity/Battle/Comp/HeroBuffAttrComp.lua` |
| 08 | [[08-ai-system]] | AI 决策系统（目标/技能选择） | `Logic/Battle/AI/AIBehaviorComp.lua`<br>`Logic/Battle/AI/AIUtil.lua`<br>`Logic/Battle/AI/AIPickTarget.lua`<br>`Logic/Battle/AI/AIPickSkill.lua`<br>`Logic/Battle/AI/AIPickSkillAtTarget.lua`<br>`Logic/Entity/Battle/Comp/AIAutoComp.lua` |
| 09 | [[09-client-presentation]] | 客户端表现层（ClientBattle/VisEntity） | `ClientBattle/ClientBattle.lua`<br>`ClientBattle/Comp/ClientBattleMapComp.lua`<br>`ClientBattle/Comp/ClientBattleFightComp.lua`<br>`ClientBattle/Comp/ClientBattleSelectComp.lua`<br>`ClientBattle/Comp/ClientPerformManager.lua`<br>`Graphic/VisEntity/VisEntity.lua`<br>`ClientEntity/Battle/ClientBattleHero.lua` |
| 10 | [[10-battle-verify-regret]] | 战斗校验、快进与悔棋 | `Logic/Battle/Comp/BattleLogicComp.lua`<br>`Logic/Battle/Comp/BattleTurnComp.lua`<br>`Logic/Battle/Comp/BattleRegretComp.lua`<br>`Logic/Battle/Comp/BattleDebugComp.lua`<br>`Logic/Battle/BattleRebuild.lua` |

---

## 建议学习顺序

```
01 架构与入口
  └─→ 02 核心类与组件系统
        └─→ 03 状态机与回合流程
              ├─→ 04 地图与移动寻路
              │     └─→ 05 BattleHero 实体与属性
              │           ├─→ 06 技能系统
              │           │     └─→ 07 Buff 系统
              │           │           └─→ 08 AI 决策系统
              │           └─→ 09 客户端表现层
              │                 └─→ 10 战斗校验与悔棋
              └─→ 09 客户端表现层（可与 04 并行）
```

**强依赖链**（必须按序）：`01 → 02 → 03 → 05 → 06 → 07`

**弱依赖**（可以略读前置后继续）：`03 → 04`、`07 → 08`、`09 → 10`

---

## 里程碑

| 里程碑 | 完成教程 | 可以独立完成 |
|--------|----------|-------------|
| M1 | 01–02 | 浏览战斗代码，理解文件分工，不再迷路 |
| M2 | 03–05 | 跟踪一场完整战斗的运行流程，理解行动顺序 |
| M3 | 06–07 | 阅读任意 Buff/技能代码，添加简单 Buff |
| M4 | 08–10 | 理解 AI 决策逻辑、战斗校验原理，具备独立 Debug 能力 |
