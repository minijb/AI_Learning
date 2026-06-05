---
title: "FSM 核心概念与理论"
updated: 2026-06-05
---

# FSM 核心概念与理论

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 90min
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要这个？

想象你正在开发一个敌人 AI。敌人需要巡逻、发现玩家后追击、接近后攻击、被击败后死亡。如果不用任何结构化方法，你可能会这样写：

```cpp
// 最原始的 AI 更新逻辑——不要这样写
void Enemy::Update(float dt) {
    if (health <= 0) {
        PlayDeathAnimation();
        return;
    }

    float dist = DistanceToPlayer();

    if (dist < attackRange) {
        Attack();
    } else if (dist < detectRange) {
        Chase();
    } else {
        Patrol();
    }
}
```

这段代码初看没问题，但当你需要加入"受伤后硬直"、"巡逻中途停下来观察"、"被阻挡时绕过障碍"、"低血量时逃跑"、"呼叫同伴"等行为时，`if-else` 会像癌细胞一样分裂。每个新条件与已有条件之间的交互呈指数级增长——你会发现自己在六个嵌套 `if` 里调试一个半年没人敢碰的逻辑。

更致命的三个问题：

1. **隐式状态**。代码没有显式声明"敌人当前在做什么"，状态藏在 `if` 分支的执行路径里。调试时你只能靠猜。
2. **状态切换逻辑散布各处**。从"巡逻"到"追击"的触发条件写在 `Update` 里，从"追击"回到"巡逻"的条件写在别处。修改一个条件时，你无法确定是否破坏了另一个。
3. **不可组合**。你想让两个敌人共享"巡逻"行为？复制粘贴。你想为 Boss 加入"二阶段"逻辑？在已有 `if-else` 树上嫁接新分支。

**有限状态机（Finite State Machine, FSM）** 是解决这些问题的经典工具。它不是银弹，但当你的 AI 行为可以自然划分成若干"互斥的、明确命名的模式"时，FSM 是最简单也最可靠的选择。

在游戏工业中，FSM 无处不在：

- **Pac-Man（1980）**：四个幽灵各有一个简单的 FSM——Chase（追击）/ Scatter（散开）/ Frightened（逃跑）。Blinky 直接追击玩家，Pinky 瞄准玩家前方，Inky 和 Clyde 各有不同逻辑。这些状态机的组合创造了至今仍在被分析的 emergent behavior。
- **敌人的巡逻/追击/攻击/死亡**：几乎所有 3D 动作游戏的敌人 AI 都基于这个四态或五态 FSM 构建。从《黑暗之魂》的普通活尸到《毁灭战士》的恶魔，核心骨架都是 FSM。
- **角色动画控制器**：Idle/Walk/Run/Jump/Fall/Land 构成一个典型的地面移动 FSM。Unity 的 Mecanim 和 Unreal 的 Animation Blueprint 本质上就是可视化有限状态机。
- **UI 流程**：主菜单 → 设置 → 游戏内 → 暂停 → 结算。这也是 FSM。
- **回合制游戏流程**：布阵 → 战斗 → 结算 → 奖励。同样是 FSM。

理解了 FSM，你就理解了游戏 AI 大厦的基石。后续的行为树、分层状态机、效用 AI 都建立在对 FSM 的深刻理解之上。

### 核心思想

#### 形式化定义

数学上，一个有限状态机由五元组 `(Σ, S, s₀, δ, F)` 定义：

| 符号 | 名称 | 含义 |
|------|------|------|
| `Σ` | 输入字母表 (Input Alphabet) | 所有可能的事件/输入的集合 |
| `S` | 状态集合 (Set of States) | 系统可以处于的所有离散状态 |
| `s₀ ∈ S` | 初始状态 (Initial State) | 系统启动时所在的默认状态 |
| `δ: S × Σ → S` | 状态转移函数 (Transition Function) | 给定当前状态和输入事件，返回下一个状态 |
| `F ⊆ S` | 终止状态集合 (Final States) | 可选；对于游戏 AI 通常不适用，但对于有限自动机理论是核心概念 |

对于游戏 AI，我们通常使用一个**六元组**的扩展形式，在实践中更实用：

| 元素 | 说明 | 游戏 AI 中的例子 |
|------|------|------------------|
| **状态 (State)** | 系统在某时刻的确定行为模式 | `Patrol`, `Chase`, `Attack`, `Dead` |
| **转移 (Transition)** | 从一个状态到另一个状态的有向边 | `Patrol → Chase`（检测到玩家） |
| **事件 (Event)** | 触发转移的外部或内部信号 | `OnPlayerDetected`, `OnHealthZero` |
| **条件 (Condition / Guard)** | 转移是否允许执行的布尔表达式 | `distance < detectRange && hasLineOfSight` |
| **动作 (Action)** | 状态中执行的持续性行为 | 巡逻时沿路径点移动，攻击时播放动画并造成伤害 |
| **进入/退出回调 (Entry/Exit Action)** | 状态切换时执行的一次性行为 | 进入 `Chase` 时播放"警觉"音效，退出 `Patrol` 时停止哼歌 |

#### 状态转移图与状态转移表

FSM 有两种等价的表示法：

**状态转移图 (State Transition Diagram)**：

```
              ┌─────────────┐
              │   Patrol     │
              │ entry: 播放  │
              │   巡逻动画   │
              │ tick:  沿路径│
              │   点移动     │
              └──────┬──────┘
        playerInSight  │  !playerInSight && health > 30%
         ┌─────────────┼──────────────────┐
         ▼             │                  ▼
  ┌─────────────┐      │         ┌─────────────┐
  │   Chase      │      │         │   Flee       │
  │ entry: 播放  │◄─────┘         │ entry: 播放  │
  │   警觉音效   │ health < 30%   │   逃跑动画   │
  │ tick:  导航至│◄───────────────│ tick:  远离   │
  │   最后已知位置│                │   玩家       │
  └──────┬──────┘                  └──────┬──────┘
         │ playerInAttackRange            │
         ▼                                │
  ┌─────────────┐                         │
  │   Attack     │                         │
  │ tick:  面向  │                         │
  │   玩家攻击   │                         │
  └──────┬──────┘                         │
         │ health <= 0                     │
         ▼                                ▼
  ┌─────────────────────────────────────────┐
  │               Dead                       │
  │ entry: 播放死亡动画，禁用碰撞，延迟销毁  │
  └─────────────────────────────────────────┘
```

这种图直观易懂，适合沟通和设计文档。但当状态和转移数量增长后，图会变成一个意大利面怪物。

**状态转移表 (State Transition Table)**：

| 当前状态 \ 事件 | PlayerDetected | PlayerLost | LowHealth | InAttackRange | HealthZero |
|-----------------|----------------|------------|-----------|---------------|------------|
| Patrol          | → Chase        | Patrol *(自转移)* | → Flee | Patrol *(忽略)* | → Dead |
| Chase           | Chase *(自转移)* | → Patrol   | → Flee | → Attack | → Dead |
| Attack          | Attack *(忽略)* | → Chase   | → Flee | Attack *(自转移)* | → Dead |
| Flee            | Flee *(忽略)*   | → Patrol   | Flee *(自转移)* | Flee *(忽略)* | → Dead |
| Dead            | Dead *(忽略)*   | Dead *(忽略)* | Dead *(忽略)* | Dead *(忽略)* | Dead *(自转移)* |

转移表在处理复杂 FSM 时远比图清晰。它迫使你显式处理**每一对** `(state, event)` 的组合，暴露出被遗漏的转移路径。注释中标注"忽略"的事件意味着在那个状态下这个事件不应该发生或可以安全丢弃；标注"自转移"的意味着事件发生但状态不变（如巡逻中再次收到巡逻指令）。

**转移表优于转移图的场景**：
- 调试时快速确认"在 A 状态收到 B 事件应该去哪里"。
- Code review 时逐行核对逻辑完备性。
- 自动代码生成——你可以把表直接映射到二维数组或 `switch` 语句。

**转移图优于转移表的场景**：
- 向非技术人员解释设计。
- 发现"死状态"（Dead-end State）和不可达状态——从图上一眼可见。
- 设计早期快速草图。

成熟团队同时使用两者：图用于设计讨论，表用于实现和 review。

#### Mealy 机 vs Moore 机

这是 FSM 理论中一个重要的分类，直接影响你的实现设计：

| 特性 | Moore 机 | Mealy 机 |
|------|----------|----------|
| 输出由什么决定 | **仅**当前状态 | 当前状态 + 当前输入 |
| 状态数量 | 通常更多 | 通常更少 |
| 输出时序 | 输出在状态切换后才变化 | 输出随输入即时变化 |
| 经典例子 | 大多数游戏 AI 状态机 | 响应式输入处理 |

**在游戏 AI 语境下的实际含义**：

- **Moore 风格**：状态本身定义了全部行为。`Attack` 状态意味着"每帧面对玩家、执行攻击逻辑"。进入这个状态的唯一方式是满足转移条件——触发那件事的事件已经发生了，现在系统稳定地处于 `Attack` 模式。这是游戏 AI 中最常见的模式。
- **Mealy 风格**：同一状态下，不同的输入产生不同的输出。例如 `Combat` 状态下，如果输入是"玩家在攻击范围内"就攻击，如果输入是"玩家格挡"就换破防技。状态只是上下文的约束，具体行为由输入驱动。

实践中，大多数游戏 FSM 是 **Moore 为主、Mealy 为辅** 的混合体。状态定义了主体的行为框架，但状态更新函数内部会根据当前感知（类似输入）做细粒度决策：

```python
# 伪代码：Moore 外壳 + Mealy 内部分支
def state_attack_update(self, perception):
    if perception.player_blocking:
        self.perform_guard_break()
    elif perception.player_in_range:
        self.perform_combo()
    else:
        self.transition_to("Chase")
```

#### 确定性 FSM vs 非确定性 FSM

| | 确定性 (DFA / DFSM) | 非确定性 (NFA / NFSM) |
|---|---|---|
| 转移规则 | 一个 (state, event) 对 → 唯一下一状态 | 一个 (state, event) 对 → 可能多个下一状态 |
| 实现复杂度 | 简单——一个 `switch` 或 `unordered_map` | 需要优先级规则、随机选择或并行评估 |
| 行为可预测性 | 完全可预测（给定输入序列，行为唯一） | 可引入随机性和 emergent 行为 |
| 游戏 AI 用途 | 95% 的场景 | 需要"意外感"的 Boss AI、RTS 战术选择 |

游戏 AI 几乎总是**确定性 FSM**。原因很简单：可调试性。如果你的 Boss 有时在第三阶段释放技能 A，有时释放技能 B，而你不知道为什么——因为你用了一个非确定性转移——你会花一整天追踪一个"bug"后发现这只是随机选择的结果。

当你确实需要"非确定性"行为时（比如让敌人偶尔换一种攻击方式），不要把非确定性放进状态转移层。**在状态内部使用随机选择**，保持转移层确定：

```cpp
// ✅ 好的做法：转移层是确定的，状态内部用随机性
void AttackState::Update(float dt) {
    if (cooldownTimer <= 0) {
        // 状态内部随机选择攻击类型，转移逻辑不受影响
        int attackIdx = Random::Range(0, availableAttacks.size());
        PerformAttack(availableAttacks[attackIdx]);
    }
}
```

```cpp
// ❌ 坏的做法：转移层引入了非确定性
//    一个事件对应两个可能的目标状态，不可预测、不可调试
void CombatState::OnPlayerClose() {
    if (Random::Chance(0.5f)) {
        TransitionTo("Attack");
    } else {
        TransitionTo("Retreat");
    }
}
```

#### 为什么 FSM 是游戏 AI 的基石？——三个历史案例

**1. Pac-Man 幽灵 AI（1980）**

Pac-Man 的四个幽灵各自运行独立的 FSM，只有三个状态：

- **Chase**：每个幽灵用不同的策略追逐 Pac-Man。Blinky 直接追踪 Pac-Man 当前位置，Pinky 瞄准 Pac-Man 前方 4 格，Inky 使用 Blinky 位置和 Pac-Man 前方的复杂矢量计算，Clyde 在距离 Pac-Man 8 格内时切换到 Scatter 模式。
- **Scatter**：每个幽灵移动到地图的一个预设角落。
- **Frightened**：吃到大豆后，所有幽灵反转方向并随机移动。

全局有一个计时器在 Chase 和 Scatter 之间周期性切换所有幽灵。仅三个状态 + 四个略有不同的追逐策略，创造了直到今天仍被研究和赞美的游戏体验。这是"简单规则产生 emergent 复杂性"的经典案例。

**2. Halo 系列敌人 AI（2001-）**

Bungie 在 Halo 中使用的敌人行为系统是 FSM 的教科书级应用。以精英（Elite）为例：

- `Idle` → 巡逻或站岗
- `Alert` → 检测到异常（尸体、枪声），搜索最后已知位置
- `Combat` → 与玩家交火，使用掩体、投掷手雷、侧翼包抄
- `Retreat` → 护盾破裂后撤退到安全位置等待护盾恢复
- `Berserk` → 护盾破裂且无路可退时，持能量剑自杀式冲锋
- `Dead` → 播放死亡动画

每个状态内部有丰富的子行为（子 FSM 或参数化逻辑），但顶层转移清晰且可预测。这就是 FSM 的威力：**顶层逻辑简单，内部行为丰富**。

**3. 现代角色控制器**

Unity 的 Animator Controller 和 Unreal 的 Animation Blueprint 本质上是**可视化 FSM**。一个典型的地面移动控制器：

```
          Idle ──→ Walk ──→ Run ──→ Sprint
           ↑        ↓        ↑
           │        │        │
           ├────────┴────────┤  (速度变化)
           │                 │
           └─── Land ←─ Fall ←─ Jump
                │                 ↑
                └──→ Idle ───────┘
```

这个 FSM 的几个关键设计点：
- 从 `Any State` 可以跳转到 `Fall`（当角色失去地面支撑时）——这是对"Any-State Transition"的实际应用。
- `Jump` 只能从 `Idle`/`Walk`/`Run` 进入，不能从 `Fall` 进入——防止二段跳。
- 每个状态关联不同的动画混合树（Blend Tree），实现动画间的平滑过渡。

---

## 2. 代码示例

### 2.1 基础 FSM 实现：switch 驱动

这是游戏开发中最常见的 FSM 实现模式。直接、无分配、极快。适合简单到中等复杂度的 FSM。

```cpp
// ============================================================
// FSM: 语言无关伪代码 (C++ 风格)
// 演示 switch-based FSM 的核心结构
// ============================================================

// ---- 1. 定义状态枚举 ----
enum class EnemyState {
    Patrol,
    Chase,
    Attack,
    Dead
};

// ---- 2. 定义事件枚举 ----
enum class EnemyEvent {
    PlayerDetected,      // 检测到玩家
    PlayerLost,          // 丢失玩家
    InAttackRange,       // 进入攻击范围
    OutOfAttackRange,    // 离开攻击范围
    HealthCritical,      // 血量低于阈值
    HealthRegenerated,   // 血量恢复
    HealthZero           // 血量归零
};

// ---- 3. 敌人 AI 类 ----
class EnemyAI {
public:
    EnemyAI() : m_currentState(EnemyState::Patrol) {}

    // 主入口：每帧由游戏循环调用
    void Update(float deltaTime) {
        // 阶段 1: 接收事件（由感知系统填充）
        // 阶段 2: 评估转移
        // 阶段 3: 执行状态逻辑

        // 步骤 1: 先处理状态切换——保证本帧使用正确的状态
        EnemyEvent event = PollEvents();
        Transition(event);

        // 步骤 2: 执行当前状态的每帧行为
        UpdateState(deltaTime);
    }

private:
    EnemyState m_currentState;

    // ---- 状态转移表 ----
    void Transition(EnemyEvent event) {
        switch (m_currentState) {
        case EnemyState::Patrol:
            if (event == EnemyEvent::PlayerDetected) {
                SetState(EnemyState::Chase);
            } else if (event == EnemyEvent::HealthCritical) {
                SetState(EnemyState::Chase); // or Flee
            } else if (event == EnemyEvent::HealthZero) {
                SetState(EnemyState::Dead);
            }
            break;

        case EnemyState::Chase:
            if (event == EnemyEvent::InAttackRange) {
                SetState(EnemyState::Attack);
            } else if (event == EnemyEvent::PlayerLost) {
                SetState(EnemyState::Patrol);
            } else if (event == EnemyEvent::HealthZero) {
                SetState(EnemyState::Dead);
            }
            break;

        case EnemyState::Attack:
            if (event == EnemyEvent::OutOfAttackRange) {
                SetState(EnemyState::Chase);
            } else if (event == EnemyEvent::HealthZero) {
                SetState(EnemyState::Dead);
            }
            break;

        case EnemyState::Dead:
            // Dead 是吸收态——不会再有转移
            break;
        }
    }

    void SetState(EnemyState newState) {
        if (newState == m_currentState) return;

        // 步骤 1: 退出当前状态（Exit callback）
        OnStateExit(m_currentState);

        // 步骤 2: 切换状态
        m_currentState = newState;

        // 步骤 3: 进入新状态（Enter callback）
        OnStateEnter(m_currentState);
    }

    void OnStateEnter(EnemyState state) {
        switch (state) {
        case EnemyState::Patrol:
            SetMoveSpeed(patrolSpeed);
            PlayAnimation("Walk");
            SetDestination(GetNextPatrolPoint());
            break;
        case EnemyState::Chase:
            SetMoveSpeed(chaseSpeed);
            PlayAnimation("Run");
            PlayOneShotSound("alert_bark");
            // 通知附近敌人
            AlertNearbyAllies();
            break;
        case EnemyState::Attack:
            SetMoveSpeed(0);
            FaceTarget(player.position);
            ResetAttackCooldown();
            break;
        case EnemyState::Dead:
            DisableCollision();
            PlayAnimation("Death");
            DropLoot();
            ScheduleDestroy(5.0f); // 5 秒后移除
            break;
        }
    }

    void OnStateExit(EnemyState state) {
        switch (state) {
        case EnemyState::Patrol:
            StopMovement();
            break;
        case EnemyState::Chase:
            // 退出追击时清除最后已知位置
            ClearLastKnownPlayerPosition();
            break;
        case EnemyState::Attack:
            // 什么也不做
            break;
        case EnemyState::Dead:
            // Dead 状态不应该被退出
            break;
        }
    }

    void UpdateState(float deltaTime) {
        switch (m_currentState) {
        case EnemyState::Patrol:
            UpdatePatrol(deltaTime);
            break;
        case EnemyState::Chase:
            UpdateChase(deltaTime);
            break;
        case EnemyState::Attack:
            UpdateAttack(deltaTime);
            break;
        case EnemyState::Dead:
            // Dead 状态下无行为
            break;
        }
    }

    // ---- 状态行为函数 ----
    void UpdatePatrol(float dt) {
        if (ReachedPatrolPoint()) {
            SetDestination(GetNextPatrolPoint());
        }
    }

    void UpdateChase(float dt) {
        // 持续更新目标位置——追击玩家最后已知位置
        SetDestination(player.position);
    }

    void UpdateAttack(float dt) {
        FaceTarget(player.position);
        m_attackCooldown -= dt;
        if (m_attackCooldown <= 0) {
            PerformAttack();
            m_attackCooldown = attackInterval;
        }
    }

    // ---- 感知与事件轮询 ----
    EnemyEvent PollEvents() {
        // 注意：Dead 状态一般不再轮询事件
        if (m_currentState == EnemyState::Dead) return EnemyEvent::HealthZero;

        float dist = DistanceTo(player.position);

        if (health <= 0)           return EnemyEvent::HealthZero;
        if (health < maxHealth * 0.3f) return EnemyEvent::HealthCritical;
        if (dist <= attackRange)   return EnemyEvent::InAttackRange;
        if (dist > attackRange && dist <= detectRange) return EnemyEvent::PlayerDetected;
        return EnemyEvent::PlayerLost;
    }

    // ... 其他成员变量（health, patrolSpeed, attackRange, 等）
};
```

### 2.2 角色控制器 FSM：一个更直观的例子

```cpp
// ============================================================
// 角色地面移动控制器 FSM
// 演示一个典型的四态 FSM：Idle / Walk / Run / Jump
// ============================================================

enum class LocomotionState {
    Idle,
    Walk,
    Run,
    Jump,
    Fall
};

class CharacterController {
public:
    void Update(float dt) {
        // 读取玩家输入
        PlayerInput input = GetInput();
        bool isGrounded = CheckGrounded();

        // 评估转移（转移表逻辑）
        EvaluateTransitions(input, isGrounded);

        // 执行当前状态的逻辑
        switch (m_state) {
        case LocomotionState::Idle:
            // Idle 状态下速度衰减到零
            m_velocity.x *= 0.9f;
            m_velocity.z *= 0.9f;
            break;

        case LocomotionState::Walk: {
            float speed = walkSpeed;
            m_velocity.x = input.moveX * speed;
            m_velocity.z = input.moveZ * speed;
            break;
        }

        case LocomotionState::Run: {
            float speed = runSpeed;
            m_velocity.x = input.moveX * speed;
            m_velocity.z = input.moveZ * speed;
            break;
        }

        case LocomotionState::Jump:
            // 跳跃已在上一个转移帧施加了初速度
            // 这里只处理水平移动（允许空中微调方向）
            m_velocity.x += input.moveX * airControl * dt;
            m_velocity.z += input.moveZ * airControl * dt;
            break;

        case LocomotionState::Fall:
            // 同 Jump，空中控制
            m_velocity.x += input.moveX * airControl * dt;
            m_velocity.z += input.moveZ * airControl * dt;
            break;
        }

        // 无论什么状态，始终应用重力
        if (!isGrounded) {
            m_velocity.y -= gravity * dt;
        }

        // 物理位移
        Move(m_velocity * dt);
    }

private:
    LocomotionState m_state = LocomotionState::Idle;
    Vector3 m_velocity;

    void EvaluateTransitions(const PlayerInput& input, bool grounded) {
        // ──── 转移表（按优先级排列）────
        //
        // 优先级规则：
        // 1. 落地检测优先级最高——从任何空中状态落地必须立即处理
        // 2. 离地检测次之——从任何地面状态跌落必须立即处理
        // 3. 按状态分组评估自觉动作（跳跃、移动、停止）

        // --- 全局高优先级转移 (Any State → X) ---

        // 落地：Air → Ground
        if (grounded && (m_state == LocomotionState::Jump || m_state == LocomotionState::Fall)) {
            if (input.moveX != 0 || input.moveZ != 0) {
                SetState(LocomotionState::Walk);
            } else {
                SetState(LocomotionState::Idle);
            }
            return; // 落地后本帧不再评估其他转移
        }

        // 离地：Ground → Air（未主动跳跃，从边缘跌落）
        if (!grounded && (m_state == LocomotionState::Idle || m_state == LocomotionState::Walk || m_state == LocomotionState::Run)) {
            SetState(LocomotionState::Fall);
            return;
        }

        // --- 状态特定转移 ---

        switch (m_state) {
        case LocomotionState::Idle:
            if (input.jumpPressed && grounded) {
                m_velocity.y = jumpVelocity;
                SetState(LocomotionState::Jump);
            } else if (input.moveX != 0 || input.moveZ != 0) {
                if (input.runHeld) {
                    SetState(LocomotionState::Run);
                } else {
                    SetState(LocomotionState::Walk);
                }
            }
            break;

        case LocomotionState::Walk:
            if (input.jumpPressed && grounded) {
                m_velocity.y = jumpVelocity;
                SetState(LocomotionState::Jump);
            } else if (input.moveX == 0 && input.moveZ == 0) {
                SetState(LocomotionState::Idle);
            } else if (input.runHeld) {
                SetState(LocomotionState::Run);
            }
            break;

        case LocomotionState::Run:
            if (input.jumpPressed && grounded) {
                m_velocity.y = jumpVelocity;
                SetState(LocomotionState::Jump);
            } else if (input.moveX == 0 && input.moveZ == 0) {
                SetState(LocomotionState::Idle);
            } else if (!input.runHeld) {
                SetState(LocomotionState::Walk);
            }
            break;

        case LocomotionState::Jump:
            // 跳跃顶点后自动进入下落
            if (m_velocity.y <= 0) {
                SetState(LocomotionState::Fall);
            }
            break;

        case LocomotionState::Fall:
            // Fall → 落地由全局转移处理
            break;
        }
    }

    void SetState(LocomotionState newState) {
        if (newState == m_state) return;

        // Exit
        OnStateExit(m_state);
        // Switch
        m_state = newState;
        // Enter
        OnStateEnter(m_state);
    }

    void OnStateEnter(LocomotionState state) {
        switch (state) {
        case LocomotionState::Idle:   PlayAnimation("Idle"); break;
        case LocomotionState::Walk:   PlayAnimation("Walk"); break;
        case LocomotionState::Run:    PlayAnimation("Run");  break;
        case LocomotionState::Jump:   PlayAnimation("Jump"); break;
        case LocomotionState::Fall:   PlayAnimation("Fall"); break;
        }
    }

    void OnStateExit(LocomotionState state) {
        // 大多数状态退出时不需要特殊清理
        switch (state) {
        case LocomotionState::Jump:
            // 如果跳跃被外部中断（如被击中），重置跳跃相关变量
            m_jumpRequested = false;
            break;
        default:
            break;
        }
    }
};
```

### 2.3 状态转移表的代码化表示

上面的 switch 实现已经内嵌了转移逻辑，但如果你想将转移表**显式化为数据**（便于热更新和可视化），可以这样做：

```python
# ============================================================
# 数据驱动的状态转移表
# 将转移规则从代码中分离，变成可序列化的数据
# ============================================================

from dataclasses import dataclass
from typing import Callable, Optional

# 转移规则：一条转移 = (当前状态, 事件, 条件, 目标状态)
@dataclass
class TransitionRule:
    from_state: str
    event: str
    condition: Optional[Callable[[], bool]] = None  # Guard
    to_state: str = ""

# 敌人的 FSM 转移表
enemy_transitions = [
    # (from_state,       event,              condition,            to_state)
    TransitionRule("Patrol", "PlayerDetected",    None,               "Chase"),
    TransitionRule("Patrol", "HealthZero",        None,               "Dead"),
    TransitionRule("Chase",  "InAttackRange",     None,               "Attack"),
    TransitionRule("Chase",  "PlayerLost",        lambda: lastSeenTime > 5.0, "Patrol"),
    TransitionRule("Chase",  "HealthZero",        None,               "Dead"),
    TransitionRule("Attack", "OutOfAttackRange",  None,               "Chase"),
    TransitionRule("Attack", "HealthZero",        None,               "Dead"),
]

# 评估函数：遍历表，找到第一个匹配的转移
def evaluate_transitions(current_state: str, event: str) -> Optional[str]:
    for rule in enemy_transitions:
        if rule.from_state == current_state and rule.event == event:
            if rule.condition is None or rule.condition():
                return rule.to_state
    return None  # 没有匹配的转移，保持当前状态
```

**关键设计决策——转移优先级**：

当同一个 `(state, event)` 对应多条规则时，表中的**顺序决定了优先级**。这是最容易出错的地方之一。例如：

```python
# 危险：这两条规则的优先级不明确
TransitionRule("Combat", "EnemyClose", lambda: health > 30, "Attack"),
TransitionRule("Combat", "EnemyClose", lambda: health <= 30, "Flee"),
```

这里条件互斥，所以顺序无所谓。但如果条件有重叠（某次调用时两个  `condition()` 都返回 `true`），第一个匹配的会胜出。在多人协作的项目中，这种隐式优先级很容易被后来的开发者打破。

**更好的做法**：让条件逻辑显式且互斥，或使用优先级字段：

```python
@dataclass
class TransitionRule:
    from_state: str
    event: str
    condition: Optional[Callable[[], bool]] = None
    to_state: str = ""
    priority: int = 0       # 显式优先级，0 为最高

# 评估时按优先级排序
def evaluate_transitions(current_state: str, event: str) -> Optional[str]:
    candidates = [r for r in enemy_transitions
                  if r.from_state == current_state and r.event == event
                  and (r.condition is None or r.condition())]
    if not candidates:
        return None
    # 按优先级降序排列，取第一个
    candidates.sort(key=lambda r: r.priority, reverse=True)
    return candidates[0].to_state
```

---

## 3. 练习

### 练习 1: 敌方 AI 状态图设计与伪代码实现

**目标**：为一个近战敌人 AI 设计完整的 FSM，包含 `Patrol` / `Chase` / `Attack` / `Dead` 四个状态，并用 switch 模式实现伪代码。

**要求**：

1. 画出状态转移图（可以用 Mermaid、ASCII 图或手绘拍照）。图中必须标注：
   - 每个状态的 Enter / Exit / Update 行为
   - 每条转移的触发条件
   - 从哪些状态可以进入 `Dead`（答案：所有状态）

2. 用你熟悉的语言写出伪代码实现。必须包含：
   - 至少一个 "Enter callback" 中产生副作用的例子（如播放音效、广播事件）
   - 至少一个带 Guard 条件的转移（如：追击超过 10 秒 → 放弃并返回巡逻）
   - `Dead` 状态进入后如何确保不会再被转移出去

3. 回答：你的 FSM 中哪些 `(state, event)` 组合没有被处理？它们是"不可能发生"还是"应该处理但被遗漏了"？

**提示**：用状态转移表来检查完备性。一个 `N` 个状态、`M` 个事件的 FSM 有 `N × M` 种组合需要决策。

---

### 练习 2: 从 switch 到状态模式的重构

**目标**：将练习 1 的 switch-based 实现重构为面向对象的状态模式（State Pattern），并分析两种实现的优劣。

**要求**：

1. 设计一个状态基类 `IEnemyState`，包含 `OnEnter()` / `OnExit()` / `OnUpdate(dt)` / `OnEvent(event)` 四个纯虚方法。

2. 为每个具体状态（`PatrolState`、`ChaseState`、`AttackState`、`DeadState`）实现这些方法。`OnEvent` 返回 `IEnemyState*`（新的状态指针）或 `nullptr`（保持当前状态）。

3. 比较两种实现：

| 维度 | switch 模式 | 状态模式 |
|------|------------|----------|
| 代码行数 | | |
| 新增加一个状态的改动量 | | |
| 编译期类型安全性 | | |
| 状态私有数据管理 | | |
| 性能（分支预测、虚函数开销） | | |
| 单元测试便利性 | | |
| 适合的场景 | | |

4. 思考：状态对象应该是单例（每个状态类只有一个全局实例）还是每个敌人拥有自己的状态实例？为什么？

---

### 练习 3: 格斗游戏角色 FSM——识别 FSM 的边界（可选）

**目标**：尝试用 FSM 建模一个格斗游戏角色的完整行为，亲身体验 FSM 在复杂场景下的局限性。

**要求**：

1. 尝试设计涵盖以下行为的状态机：
   - 基础：`Idle`、`WalkForward`、`WalkBack`、`Crouch`、`Jump`
   - 攻击：`LightPunch`、`HeavyPunch`、`LightKick`、`HeavyKick`
   - 特殊技：至少两个（如 `Fireball`、`DragonPunch`），每个有自己独特的输入窗口和取消窗口
   - 防御：`BlockStanding`、`BlockCrouching`
   - 受伤：`HitStun`、`Knockdown`、`WakeUp`
   - 连招：从 `LightPunch` 可以接 `HeavyPunch` 再接入 `SpecialMove`

2. **关键问题**：在以下场景中，你的 FSM 遇到了什么问题？
   - 连招链：`A → B → C` 和 `A → D → E` 是两条不同的连招路线。FSM 如何表达"在 A 的第 3 帧可以取消进入 B 或 D"？
   - 输入缓冲：玩家在 `WakeUp` 的最后一帧输入了 `DragonPunch`。FSM 如何记住这个输入并在站立的第一帧执行？
   - 可取消性：`LightPunch` 可以取消进入 `SpecialMove`，但 `HeavyPunch` 不能。这种"状态属性"如何表达？

3. 写一段 200-300 字的分析：为什么纯 FSM 在格斗游戏中会指数级膨胀？有哪些替代方案（帧数据系统、命令解释器、分层 FSM）可以缓解？

---

## 4. 扩展阅读

以下资源按推荐阅读顺序排列。标注了大致阅读时间和适用场景。

### 书籍章节

| 书名 | 章节 | 说明 |
|------|------|------|
| *Programming Game AI by Example* (Mat Buckland, 2005) | Chapter 2: State-Driven Agent Design | 游戏 AI FSM 的经典教材。从最简 switch 到状态模式到消息分发，以西部枪手游戏为例逐步构建。代码是 C++ 但注释丰富。**必须读**。 |
| *Artificial Intelligence for Games* (Ian Millington, 2nd ed., 2009) | Chapter 5.3: State Machines | 比 Buckland 的书更偏理论。包含 HFSM（分层状态机）的详细分析，以及 FSM 的严格形式化定义。 |
| *Game AI Pro* 系列 (Steve Rabin 主编) | 多篇 | Game AI Pro 1/2/3 共有约 10 篇与状态机直接相关的文章。详见下文。 |
| *Game Engine Architecture* (Jason Gregory, 3rd ed.) | Section 15.2: State Machines | Naughty Dog 引擎架构师的视角。讨论了状态机在商业引擎中的实际应用和性能考量。 |

### Game AI Pro 精选文章

Game AI Pro 是游戏 AI 领域的工业论文集，每篇文章由 AAA 工作室的从业者撰写。以下是与 FSM 最相关的：

| 文章 | 作者 | 位置 | 核心内容 |
|------|------|------|----------|
| *Behavior Selection Algorithms: An Overview* | Michael Dawe | Game AI Pro 3, Ch 4 | FSM、BT、Utility AI 的全景对比。 |
| *A Reusable, Light-Weight Finite State Machine* | David "Rez" Graham | Game AI Pro 1, Ch 12 | 一个可在任何项目中复用的轻量 FSM 框架设计。 |
| *The Simplest AI Trick in the Book* | various | Game AI Pro 1, Ch 11 | FSM 在量产型游戏敌人中的应用模式。 |
| *Modular AI* | Kevin Dill | Game AI Pro 2, Ch 13 | 将 FSM 模块化的架构技巧。 |

### GDC 演讲（可在 GDC Vault 找到）

- **"Building a Better Battlefield: AI in Battlefield 1"** (2017) — DICE 团队讲解如何用层次状态机制作大规模战场中的士兵 AI。
- **"AI for 'Middle-earth: Shadow of Mordor' — The Nemesis System"** (2015) — Monolith Productions 的宿敌系统，底层大量使用 FSM 管理兽人行为。
- **"The AI of 'DOOM' (2016)"** (2017) — id Software 讲解新版 DOOM 的敌人 AI，大量使用 FSM 加行为树混合架构。

### 在线资源

- [State Pattern in Game Programming](https://gameprogrammingpatterns.com/state.html) — Robert Nystrom 的《Game Programming Patterns》中关于状态模式的章节。免费在线阅读，示例代码清晰。
- [Halo 2 AI — "The Illegitimate Child of a Finite State Machine and a Fuzzy Logic Engine"](https://www.gamedeveloper.com/programming/gdc-2005-proceeding---i-the-illegitimate-child-of-a-finite-state-machine-and-a-fuzzy-logic-engine-i) — Damian Isla 在 GDC 2005 的经典演讲文字版。讲解 Halo 2 中行为树如何取代了 Halo 1 的 FSM。
- [GDC Vault](https://www.gdcvault.com/) — 搜索 "finite state machine AI" 可找到大量工业演讲。

---

## 常见陷阱

### 1. Switch 语句爆炸

**症状**：你的 `Update()` 和 `Transition()` 各有一个 200 行的 `switch`，新增一个状态需要在四五处添加 `case`。

**根因**：把所有逻辑塞进了单一函数，而不是将状态行为委托给独立函数或类。

**解法**：
- 至少将每个状态的 `Enter`/`Exit`/`Update` 逻辑抽取为独立函数。
- 当状态数超过 6-8 个时，认真考虑改用状态模式或数据驱动方式。
- 将转移表从 `switch` 中提取为显式数据结构（如上文的 `TransitionRule` 表）。

### 2. 隐藏状态——布尔标志的诱惑

**症状**：你的 FSM 有 4 个显式状态，但实际行为由 `isAlerted`、`hasSeenPlayer`、`isEnraged`、`wasRecentlyHit` 等 6 个布尔变量的组合决定。你的真实状态数不是 4 而是 `2^6 = 64`。

**根因**：在认识到需要新状态时，偷懒加了一个布尔标志而不是一个真正的状态。

**识别方法**：如果你的代码中有这种模式：

```cpp
void EnemyAI::UpdateChase(float dt) {
    if (m_isEnraged) {
        // 暴怒追击：速度翻倍，无视障碍
        SetMoveSpeed(chaseSpeed * 2.0f);
        if (DistanceToPlayer() > enragedChaseRange) {
            GiveUpChase(); // 又是一种隐式状态切换
        }
    } else if (m_wasRecentlyHit) {
        // 被击中：暂时减速
        SetMoveSpeed(chaseSpeed * 0.5f);
    } else {
        // 正常追击
        SetMoveSpeed(chaseSpeed);
    }
}
```

那你需要的是 `ChaseNormal`、`ChaseEnraged`、`ChaseWounded` 三个独立状态，而不是一个 `Chase` + 两个布尔标志。

**解法**：每个行为上显著的差异都对应一个独立状态。不要把状态内部条件分支当作状态机本身。

### 3. 转移优先级模糊

**症状**：同一帧内发生多个事件，FSM 的行为取决于事件被处理的顺序，而这个顺序是偶然的。

**根因**：转移表中多条规则可以同时匹配，但评估函数只取第一个。同时匹配的规则之间的优先级没有被显式定义。

**解法**：
- 在转移表中引入显式 `priority` 字段。
- 或者，在同一帧内只处理**一个**事件（取最高优先级的事件）。
- 在转移函数开头先检查**全局高优先级转移**（如 `HealthZero → Dead` 应该无视所有其他事件）。

### 4. 状态 Enter/Exit 执行顺序错误

**症状**：从 `Attack` 转移到 `Dead` 时，`Dead::Enter` 先于 `Attack::Exit` 执行，或者更糟糕——`Exit` 根本没有被调用。

**根因**：没有统一的 `SetState()` 函数做 Enter/Exit 调度，而是在各处的代码中直接修改 `m_currentState`。

**绝对法则**：

```cpp
void SetState(State newState) {
    if (newState == m_currentState) return;

    // 1. EXIT 旧状态  ← 先退出
    OnStateExit(m_currentState);

    // 2. SWITCH        ← 然后切换
    m_currentState = newState;

    // 3. ENTER 新状态  ← 最后进入
    OnStateEnter(m_currentState);
}
```

**绝对不能跳过** `OnStateExit`。如果你的某个状态退出时需要清理资源（取消计时器、归还对象池对象、解除事件监听），跳过一次 Exit 就意味着资源泄露或悬垂引用。

### 5. 在 Dead 状态下继续接收事件

**症状**：敌人死亡动画播放到一半，因为它碰巧收到了 `PlayerDetected` 事件，`SetState(Chase)` 被调用，尸体站起来继续追你。

**根因**：没有在 `Transition()` 或 `PollEvents()` 中提前拦截吸收态。

**解法**：

```cpp
void Transition(EnemyEvent event) {
    // 吸收态防护：一旦进入 Dead，不再处理任何事件
    if (m_currentState == EnemyState::Dead) return;
    // ... 正常转移逻辑
}
```

或者更彻底：在 `SetState` 中添加断言，禁止从 `Dead` 状态转移出去。

### 6. 状态过多——FSM 的适用边界

**症状**：你的 FSM 有 30+ 个状态，转移图看起来像意大利面。新增一个行为需要同时修改 5 个已有状态。

**根因**：你的问题已经超出了纯平铺 FSM 的舒适区。

**信号**：
- 多个状态有相似的子行为（如 `PatrolAttack` 和 `StationaryAttack` 共享相同的攻击逻辑）。
- 你频繁需要在状态之间共享数据。
- 状态之间出现大量重复代码。

**过渡方案**（按复杂度递增）：
- **分层状态机 (HSM)**：将共享子行为的状态组织成层次结构——后续 Tutorial 05 会深入讲解。
- **行为树 (BT)**：当状态间的组合关系比序列关系更重要时——后续 Tutorial 06-13 会深入讲解。
- **效用 AI (Utility AI)**：当行为选择需要同时考虑多个加权因素时。

关键是：**不要试图用 FSM 解决所有问题**。识别它的适用边界，在合适的地方切换到合适的工具。
