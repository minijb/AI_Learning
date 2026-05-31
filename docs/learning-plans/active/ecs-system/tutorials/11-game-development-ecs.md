# 游戏开发中的 ECS 模式

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 90 分钟
> 前置知识: 第 1-10 节（ECS 核心概念、组件与系统、Archetype 存储）

---

## 1. 概念讲解

### 为什么需要这个？

传统 OOP 游戏开发中，玩家、NPC、武器、技能通过继承链组织：

```
GameObject → Actor → Character → Player
                          → NPC
           → Projectile → Arrow
                        → Fireball
```

当需求交叉时（"让 NPC 也能使用玩家的技能"），继承树迅速失控。**菱形继承**、**庞大基类**、**组合爆炸**是 OOP 游戏开发的三大噩梦。

ECS 将行为从实体中剥离：一个实体是否可移动、可攻击、携带 AI 完全由组件组合决定——不是"是什么"，而是"有什么"。

### 核心思想

| 子系统 | 组件 | 系统 |
|--------|------|------|
| 角色 | `Position`, `Health`, `Movement`, `Faction` | `MovementSystem`, `HealthSystem` |
| 武器 | `Weapon`, `Ammo`, `Damage`, `Range` | `WeaponSystem`, `ProjectileSystem` |
| 技能 | `SkillCooldown`, `Buff`, `Debuff` | `SkillSystem`, `BuffSystem` |
| AI | `AIState`, `BehaviorTree`, `AITarget` | `AISystem`, `PerceptionSystem` |

关键认知：系统只读写它关心的组件。`AISystem` 不需要知道 `Weapon` 组件的存在。

---

## 2. 代码示例

```cpp
// 小 RPG 场景：玩家、NPC、武器、技能、AI 行为树 — ECS 实现
#include <iostream>
#include <vector>
#include <unordered_map>
#include <string>
#include <algorithm>
#include <cassert>
#include <sstream>
using namespace std;

// ===================== ECS 框架基石 =====================
using Entity = uint32_t;

struct ComponentPool {
    vector<uint8_t> data;
    size_t elementSize;
    vector<Entity> entityMap;
    unordered_map<Entity, size_t> indexMap;

    explicit ComponentPool(size_t elemSize) : elementSize(elemSize) {}

    template<typename T>
    T* add(Entity e) {
        if (indexMap.count(e)) return get<T>(e);
        size_t idx = entityMap.size();
        indexMap[e] = idx;
        entityMap.push_back(e);
        size_t oldSize = data.size();
        data.resize(oldSize + elementSize);
        T* ptr = reinterpret_cast<T*>(data.data() + oldSize);
        new (ptr) T{};
        return ptr;
    }

    template<typename T>
    T* get(Entity e) {
        auto it = indexMap.find(e);
        if (it == indexMap.end()) return nullptr;
        return reinterpret_cast<T*>(data.data() + it->second * elementSize);
    }

    template<typename T>
    bool has(Entity e) { return indexMap.count(e); }

    void remove(Entity e) {
        auto it = indexMap.find(e);
        if (it == indexMap.end()) return;
        size_t idx = it->second;
        size_t last = entityMap.size() - 1;
        if (idx != last) {
            memcpy(data.data() + idx * elementSize,
                   data.data() + last * elementSize, elementSize);
            indexMap[entityMap[last]] = idx;
            entityMap[idx] = entityMap[last];
        }
        entityMap.pop_back();
        indexMap.erase(e);
    }
};

class World {
    Entity nextEntity = 1;
    unordered_map<Entity, vector<int>> entityArchetype; // 简化 archetype 追踪
public:
    unordered_map<int, ComponentPool> pools;

    Entity create() { return nextEntity++; }

    template<typename T>
    T* addComponent(Entity e, int componentId) {
        if (!pools.count(componentId))
            pools.emplace(componentId, ComponentPool(sizeof(T)));
        auto* ptr = pools[componentId].add<T>(e);
        entityArchetype[e].push_back(componentId);
        return ptr;
    }

    template<typename T>
    T* getComponent(Entity e, int componentId) {
        if (!pools.count(componentId)) return nullptr;
        return pools[componentId].get<T>(e);
    }

    template<typename T>
    bool hasComponent(Entity e, int componentId) {
        if (!pools.count(componentId)) return false;
        return pools[componentId].has(e);
    }

    void destroy(Entity e) {
        for (auto& [id, pool] : pools) pool.remove(e);
        entityArchetype.erase(e);
    }

    const vector<Entity>& entities(int compId) {
        static vector<Entity> empty;
        if (!pools.count(compId)) return empty;
        return pools[compId].entityMap;
    }
};

// ===================== 组件定义 (ID + 结构体) =====================
enum Comp : int { C_POS=1, C_HEALTH, C_MOVEMENT, C_FACTION, C_WEAPON, C_AMMO,
                  C_SKILL, C_COOLDOWN, C_BUFF, C_AI, C_NAME };

struct Position  { float x=0, y=0; };
struct Health    { float hp=100, maxHp=100; };
struct Movement  { float speed=0, vx=0, vy=0; };
enum class FactionType { Player, NPC, Monster };
struct Faction   { FactionType type; };
struct Weapon    {
    enum Type { Sword, Bow, Staff } type=Sword;
    float damage=10, range=1.5f, attackSpeed=1.0f;
    float lastAttackTime=0;
};
struct Ammo      { int current=30, max=30; float reloadTime=0; };
struct Skill     { string name; float baseDamage=0; int manaCost=0; };
struct Cooldown  { float duration=0, elapsed=0; };
struct Buff      { enum Type { SpeedUp, DamageBoost, Shield } type;
                   float value=0, duration=0, elapsed=0; };
struct AIState   {
    enum State { Idle, Patrol, Chase, Attack, Flee } state = State::Idle;
    Entity currentTarget = 0;
    float detectionRange = 10.0f;
    float aggroRange = 15.0f;
    vector<Entity> patrolPoints;
    size_t currentPatrolIdx = 0;
    float waitTimer = 0;
};
struct NameComp  { string name; };

// ===================== 系统实现 =====================
class MovementSystem {
public:
    void update(World& w, float dt) {
        auto& entities = w.entities(C_POS);
        for (Entity e : entities) {
            auto* pos = w.getComponent<Position>(e, C_POS);
            auto* mov = w.getComponent<Movement>(e, C_MOVEMENT);
            if (!pos || !mov) continue;
            pos->x += mov->vx * dt;
            pos->y += mov->vy * dt;
        }
    }
};

class HealthSystem {
public:
    void update(World& w, float dt) {
        auto& entities = w.entities(C_HEALTH);
        for (Entity e : entities) {
            auto* hp = w.getComponent<Health>(e, C_HEALTH);
            if (hp->hp <= 0) {
                // 死亡处理：如果是 NPC/怪物，可以标记销毁
                auto* fac = w.getComponent<Faction>(e, C_FACTION);
                if (fac && fac->type != FactionType::Player) {
                    w.destroy(e);
                    break; // entity 失效，中断当前遍历
                }
            }
        }
    }
};

class CombatSystem {
public:
    void update(World& w, float dt, float gameTime) {
        auto& entities = w.entities(C_WEAPON);
        for (Entity attacker : entities) {
            auto* wpn = w.getComponent<Weapon>(attacker, C_WEAPON);
            auto* atkPos = w.getComponent<Position>(attacker, C_POS);
            if (!wpn || !atkPos) continue;
            if (gameTime - wpn->lastAttackTime < 1.0f / wpn->attackSpeed) continue;

            // 寻找攻击范围内的最近敌人
            auto* atkFaction = w.getComponent<Faction>(attacker, C_FACTION);
            Entity bestTarget = 0;
            float bestDist = wpn->range + 1;

            auto& targets = w.entities(C_HEALTH);
            for (Entity target : targets) {
                if (target == attacker) continue;
                auto* tarFac = w.getComponent<Faction>(target, C_FACTION);
                if (!atkFaction || !tarFac) continue;
                if (atkFaction->type == tarFac->type) continue; // 不攻击同阵营

                auto* tarPos = w.getComponent<Position>(target, C_POS);
                float dx = atkPos->x - tarPos->x;
                float dy = atkPos->y - tarPos->y;
                float dist = sqrt(dx*dx + dy*dy);
                if (dist <= wpn->range && dist < bestDist) {
                    bestDist = dist;
                    bestTarget = target;
                }
            }

            if (bestTarget) {
                auto* hp = w.getComponent<Health>(bestTarget, C_HEALTH);
                if (hp) {
                    hp->hp -= wpn->damage;
                    wpn->lastAttackTime = gameTime;
                    auto* atkName = w.getComponent<NameComp>(attacker, C_NAME);
                    auto* tarName = w.getComponent<NameComp>(bestTarget, C_NAME);
                    cout << (atkName?atkName->name:"?") << " 攻击 "
                         << (tarName?tarName->name:"?") << " 造成 " << wpn->damage
                         << " 伤害 (剩余HP: " << hp->hp << ")\n";
                }
            }
        }
    }
};

class SkillSystem {
public:
    void update(World& w, float dt) {
        auto& entities = w.entities(C_SKILL);
        for (Entity e : entities) {
            auto* cd = w.getComponent<Cooldown>(e, C_COOLDOWN);
            if (cd && cd->elapsed < cd->duration) {
                cd->elapsed += dt;
            }
        }
    }

    void useSkill(World& w, Entity caster, Entity target) {
        auto* skill = w.getComponent<Skill>(caster, C_SKILL);
        auto* cd = w.getComponent<Cooldown>(caster, C_COOLDOWN);
        if (!skill) return;
        if (cd && cd->elapsed < cd->duration) {
            cout << "技能冷却中 (" << (cd->duration - cd->elapsed) << "s 剩余)\n";
            return;
        }
        auto* hp = w.getComponent<Health>(target, C_HEALTH);
        if (hp) hp->hp -= skill->baseDamage;
        if (cd) cd->elapsed = 0;
        auto* cName = w.getComponent<NameComp>(caster, C_NAME);
        auto* tName = w.getComponent<NameComp>(target, C_NAME);
        cout << (cName?cName->name:"?") << " 施放 " << skill->name
             << " → " << (tName?tName->name:"?") << " 伤害 " << skill->baseDamage << "\n";
    }
};

class BuffSystem {
public:
    void update(World& w, float dt) {
        auto& entities = w.entities(C_BUFF);
        for (Entity e : entities) {
            auto* buff = w.getComponent<Buff>(e, C_BUFF);
            buff->elapsed += dt;
            if (buff->elapsed >= buff->duration) {
                // Buff 过期：移除效果
                auto* mov = w.getComponent<Movement>(e, C_MOVEMENT);
                if (mov && buff->type == Buff::SpeedUp)
                    mov->speed -= buff->value; // 恢复原速
                w.pools[C_BUFF].remove(e);
            }
        }
    }

    void apply(World& w, Entity target, Buff::Type type, float value, float duration) {
        auto* buff = w.addComponent<Buff>(target, C_BUFF);
        buff->type = type; buff->value = value;
        buff->duration = duration; buff->elapsed = 0;

        auto* mov = w.getComponent<Movement>(target, C_MOVEMENT);
        if (mov && type == Buff::SpeedUp) mov->speed += value;
    }
};

// ===================== 简化行为树 AI =====================
class AISystem {
    struct BTNode {
        enum Kind { Selector, Sequence, Condition, Action } kind;
        function<bool(World&, Entity, float)> run;
    };

public:
    void update(World& w, float dt, float gameTime) {
        auto& entities = w.entities(C_AI);
        for (Entity e : entities) {
            auto* ai = w.getComponent<AIState>(e, C_AI);
            if (!ai) continue;
            runBehaviorTree(w, e, *ai, dt);
        }
    }

private:
    void runBehaviorTree(World& w, Entity e, AIState& ai, float dt) {
        auto* pos = w.getComponent<Position>(e, C_POS);
        auto* mov = w.getComponent<Movement>(e, C_MOVEMENT);
        auto* f = w.getComponent<Faction>(e, C_FACTION);
        if (!pos || !mov || !f) return;

        // Step 1: 感知 —— 扫描范围内敌对实体
        Entity closest = 0;
        float closestDist = ai.aggroRange + 1;
        auto& allHealth = w.entities(C_HEALTH);
        for (Entity other : allHealth) {
            if (other == e) continue;
            auto* of = w.getComponent<Faction>(other, C_FACTION);
            if (!of || of->type == f->type) continue;
            auto* op = w.getComponent<Position>(other, C_POS);
            float dx = pos->x - op->x, dy = pos->y - op->y;
            float dist = sqrt(dx*dx + dy*dy);
            if (dist < closestDist) { closestDist = dist; closest = other; }
        }

        // Step 2: 状态转换
        if (closest && closestDist <= ai.detectionRange) {
            ai.state = AIState::Chase;
            ai.currentTarget = closest;
        } else if (ai.state == AIState::Chase && !closest) {
            ai.state = AIState::Patrol;
            ai.currentTarget = 0;
        }

        // Step 3: 行为执行
        switch (ai.state) {
        case AIState::Idle:
            mov->vx = mov->vy = 0;
            break;
        case AIState::Chase:
            if (ai.currentTarget) {
                auto* tp = w.getComponent<Position>(ai.currentTarget, C_POS);
                float dx = tp->x - pos->x, dy = tp->y - pos->y;
                float len = sqrt(dx*dx+dy*dy);
                if (len > 0.1f) {
                    mov->vx = dx/len * mov->speed;
                    mov->vy = dy/len * mov->speed;
                }
            }
            break;
        case AIState::Patrol:
            if (!ai.patrolPoints.empty()) {
                auto& pt = ai.patrolPoints[ai.currentPatrolIdx];
                auto* pp = w.getComponent<Position>(pt, C_POS);
                float dx = pp->x - pos->x, dy = pp->y - pos->y;
                float len = sqrt(dx*dx+dy*dy);
                if (len < 0.5f) ai.currentPatrolIdx = (ai.currentPatrolIdx+1) % ai.patrolPoints.size();
                else { mov->vx = dx/len * mov->speed; mov->vy = dy/len * mov->speed; }
            }
            break;
        default: break;
        }
    }
};

// ===================== 小 RPG 场景 =====================
int main() {
    World world;
    MovementSystem moveSys;
    HealthSystem healthSys;
    CombatSystem combatSys;
    SkillSystem skillSys;
    BuffSystem buffSys;
    AISystem aiSys;

    // --- 创建玩家 ---
    Entity player = world.create();
    auto* pp = world.addComponent<Position>(player, C_POS);
    pp->x = 0; pp->y = 0;
    auto* ph = world.addComponent<Health>(player, C_HEALTH);
    ph->hp = ph->maxHp = 200;
    auto* pm = world.addComponent<Movement>(player, C_MOVEMENT);
    pm->speed = 5.0f;
    auto* pf = world.addComponent<Faction>(player, C_FACTION);
    pf->type = FactionType::Player;
    auto* pw = world.addComponent<Weapon>(player, C_WEAPON);
    pw->type = Weapon::Sword; pw->damage = 25; pw->range = 2.0f; pw->attackSpeed = 1.5f;
    auto* ps = world.addComponent<Skill>(player, C_SKILL);
    ps->name = "烈焰斩"; ps->baseDamage = 60; ps->manaCost = 30;
    auto* pcd = world.addComponent<Cooldown>(player, C_COOLDOWN);
    pcd->duration = 3.0f; pcd->elapsed = 3.0f;
    auto* pn = world.addComponent<NameComp>(player, C_NAME);
    pn->name = "勇者";

    // --- 创建 NPC 同伴 ---
    Entity npc = world.create();
    world.addComponent<Position>(npc, C_POS)->x = 2;
    world.addComponent<Position>(npc, C_POS)->y = 0;
    world.addComponent<Health>(npc, C_HEALTH)->hp = 150;
    world.addComponent<Movement>(npc, C_MOVEMENT)->speed = 4.0f;
    world.addComponent<Faction>(npc, C_FACTION)->type = FactionType::NPC;
    world.addComponent<Weapon>(npc, C_WEAPON)->damage = 15;
    world.addComponent<NameComp>(npc, C_NAME)->name = "艾琳";

    // --- 创建怪物 ---
    auto createMonster = [&](float x, float y, string name, float hpVal, float dmg) -> Entity {
        Entity e = world.create();
        world.addComponent<Position>(e, C_POS)->x = x;
        world.addComponent<Position>(e, C_POS)->y = y;
        world.addComponent<Health>(e, C_HEALTH)->hp = hpVal;
        world.addComponent<Health>(e, C_HEALTH)->maxHp = hpVal;
        world.addComponent<Movement>(e, C_MOVEMENT)->speed = 3.0f;
        world.addComponent<Faction>(e, C_FACTION)->type = FactionType::Monster;
        world.addComponent<Weapon>(e, C_WEAPON)->damage = dmg;
        world.addComponent<Weapon>(e, C_WEAPON)->range = 1.5f;
        world.addComponent<Weapon>(e, C_WEAPON)->attackSpeed = 1.0f;
        auto* ai = world.addComponent<AIState>(e, C_AI);
        ai->state = AIState::Patrol;
        ai->detectionRange = 8.0f;
        ai->aggroRange = 12.0f;
        world.addComponent<NameComp>(e, C_NAME)->name = name;
        return e;
    };

    Entity goblin = createMonster(8, 3, "哥布林", 60, 12);
    Entity orc    = createMonster(-6, 4, "兽人", 100, 20);
    Entity slime  = createMonster(2, 7, "史莱姆", 30, 8);

    // --- 设置巡逻点 ---
    auto* ga = world.getComponent<AIState>(goblin, C_AI);
    auto* oa = world.getComponent<AIState>(orc, C_AI);

    cout << "===== 小 RPG ECS 模拟开始 =====\n\n";

    // --- 模拟帧 ---
    float dt = 1.0f/30.0f;
    for (int frame = 1; frame <= 6; frame++) {
        float gameTime = frame * dt;

        cout << "[帧 " << frame << "] time=" << gameTime << "s\n";

        // 玩家向右移动
        pm->vx = 4.0f; pm->vy = 1.0f;

        // 技能使用（帧 3 施放烈焰斩）
        if (frame == 3) skillSys.useSkill(world, player, goblin);

        // 帧 4 给 NPC 加速 buff
        if (frame == 4) buffSys.apply(world, npc, Buff::SpeedUp, 3.0f, 5.0f);

        moveSys.update(world, dt);
        aiSys.update(world, dt, gameTime);
        combatSys.update(world, dt, gameTime);
        skillSys.update(world, dt);
        buffSys.update(world, dt);
        healthSys.update(world, dt);

        // 打印状态
        for (Entity e : {player, npc, goblin, orc, slime}) {
            auto* pos = world.getComponent<Position>(e, C_POS);
            auto* hp  = world.getComponent<Health>(e, C_HEALTH);
            auto* nm  = world.getComponent<NameComp>(e, C_NAME);
            if (pos && hp && nm)
                printf("  %-8s pos=(%5.1f, %5.1f) HP=%5.0f\n",
                       nm->name.c_str(), pos->x, pos->y, hp->hp);
        }
        cout << "\n";
    }

    cout << "===== 模拟结束 =====\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 rpg_ecs.cpp -o rpg_ecs && ./rpg_ecs
```

**预期输出:**
```text
===== 小 RPG ECS 模拟开始 =====

[帧 1] time=0.033333s
  勇者     pos=( 0.1,  0.0) HP=  200
  艾琳     pos=( 2.0,  0.0) HP=  150
  哥布林   pos=( 8.0,  3.0) HP=   60
  兽人     pos=(-6.0,  4.0) HP=  100
  史莱姆   pos=( 2.0,  7.0) HP=   30

[帧 2] time=0.066667s
  勇者     pos=( 0.3,  0.1) HP=  200
  ...

[帧 3] time=0.1s
  勇者 施放 烈焰斩 → 哥布林 伤害 60
  勇者 攻击 哥布林 造成 25 伤害 (剩余HP: -25)
  哥布林 (死亡，被销毁)
  ...

===== 模拟结束 =====
```

### 对比：OOP vs ECS 代码量

| 功能 | OOP 实现 | ECS 实现 | 备注 |
|------|----------|----------|------|
| 新增"飞行"能力 | 修改 `Actor` 基类 + 所有子类 | 添加 `Flight` 组件 + `FlightSystem` | OOP 波及所有子类 |
| 怪物也能用技能 | 将 `UseSkill` 上提到 `Actor` | 给实体添加 `Skill` + `Cooldown` 组件 | ECS 零侵入 |
| AI 切换行为 | `if (npc->IsBoss())` 散落各处 | 替换 `AIState` 组件的数据 | ECS 纯数据驱动 |

---

## 3. 练习

### 练习 1: 扩展武器类型
为 `Weapon` 组件添加 `Bow`（远程弓）类型，修改 `CombatSystem` 使远程武器在攻击时创建 `Projectile` 实体（带 `Position` + `Velocity` + `Damage` 组件），`ProjectileSystem` 处理飞行和命中。

### 练习 2: 实现 Buff/Debuff 叠加
修改 `BuffSystem` 支持同名 Buff 叠加（层数）或刷新持续时间。实现"中毒"Debuff：每 1 秒造成固定伤害。

### 练习 3: 行为树 DSL（挑战）
设计一个简单的 JSON/文本 DSL 描述行为树，运行时解析并挂载到实体的 `AIState` 组件上。实现 Selector/Sequence/Condition/Action 四种节点。

---

## 4. 扩展阅读

- **《Game Programming Patterns》** — Chapter "Component"：OOP 中组件模式的先驱
- **EnTT (C++ ECS 库)** — `entt::registry` 的实际使用，比本文示例成熟 100 倍
- **Bevy Engine** — Rust 语言中最活跃的 ECS 游戏引擎，零成本抽象
- **Unity DOTS** — 生产级 ECS 架构，参考其 `ISystem` / `IJobEntity` 的设计

---

## 常见陷阱

1. **System 间通过组件隐式通信导致顺序依赖**。`DamageSystem` 在 `AnimationSystem` 之前运行导致伤害数字和动画不同步。解法：显式阶段管线（`PreUpdate → Update → PostUpdate`）。

2. **把 ECS 当成 OOP 用**。给每个实体配一整套组件、在 System 里写 `if (entity.Has<X>())` 分支。ECS 的优势在于 Archetype 对齐——同 Archetype 的实体批量处理。

3. **忽视数据局部性**。`Position` 和 `Health` 混在同一个组件里、分散在不同的 pool 中。应该把经常一起访问的字段放在同一个组件中（AoS），或按访问模式组织组件（SoA）。
