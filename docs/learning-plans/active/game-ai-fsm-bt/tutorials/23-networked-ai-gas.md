---
title: "网络同步 AI 与 GAS 深度集成"
updated: 2026-06-05
---

# 网络同步 AI 与 GAS 深度集成

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: 09-bt-unreal-cpp, 15-hybrid-architectures

---

## 1. 概念讲解

### Part A — Networked AI Architecture

#### 为什么网络 AI 架构必须在第一天就设计？

单机游戏中的 AI 是一个纯粹的本地问题：AI Controller 读取世界状态 → 做决策 → 驱动角色，全在同一帧内完成。但当你切换到多人游戏时，同一个 AI 实体被一个服务器和 N 个客户端同时观察。**谁做决策、谁看到什么、什么时候到达**——这三个问题决定你的 AI 在网络上是"看起来聪明"还是"看起来像在作弊"。

网络 AI 的根本矛盾是：**服务器拥有权威（authority），但客户端拥有眼睛（rendering）。** 玩家的显示器连接到客户端，他们看不到服务器内部的 AI 状态——他们只能看到服务器复制过来的位置、动画、特效。如果服务器上的 AI 决定攻击、而攻击动画通过复制到达客户端晚了 100ms，玩家会看到敌人"出招瞬移"。

这一节不是对 UE 网络复制机制的入门教程——我们假设你已经理解 `AActor::bReplicates`、`UPROPERTY(Replicated)`、`OnRep_` 的基本概念。我们聚焦的是：**在这个网络基础设施之上，AI 的架构应该长什么样。**

#### Server-Authoritative AI Model

服务器权威模型是游戏 AI 网络架构的黄金标准：

```
┌──────────────────────────────────────┐
│              SERVER                  │
│  ┌────────────────────────────┐      │
│  │     AIController            │      │
│  │  ├─ BehaviorTree (ticking)  │      │
│  │  ├─ Blackboard (read/write) │      │
│  │  ├─ Perception (full)       │      │
│  │  └─ Decision Making         │      │
│  └──────────┬─────────────────┘      │
│             │ drives                  │
│  ┌──────────▼─────────────────┐      │
│  │     ACharacter (AI Body)   │      │
│  │  ├─ Mesh (replicated)      │      │
│  │  ├─ Movement (replicated)  │      │
│  │  ├─ Health (replicated)    │      │
│  │  └─ Animation State (rep)  │      │
│  └────────────────────────────┘      │
│                  │                   │
└──────────────────┼───────────────────┘
                   │ Replication (unreliable for movement,
                   │  reliable for state changes)
┌──────────────────┼───────────────────┐
│              CLIENT                  │
│  ┌──────────────▼───────────────┐   │
│  │  SimulatedProxy (AI Body)    │   │
│  │  ├─ Mesh (rendered)          │   │
│  │  ├─ Movement (interpolated)  │   │
│  │  ├─ Health (displayed)       │   │
│  │  └─ Animation (driven by     │   │
│  │       replicated state)      │   │
│  └──────────────────────────────┘   │
│                                      │
│  AI Controller: DOES NOT EXIST      │
│  BehaviorTree: DOES NOT EXIST       │
│  Blackboard: DOES NOT EXIST         │
│  Perception: DOES NOT EXIST         │
└──────────────────────────────────────┘
```

关键原则：

1. **AI 大脑只存在于服务器**。客户端上没有 `AIController` 实例，没有 `UBehaviorTreeComponent`，没有 `UBlackboardComponent`。这意味着客户端**不能**独立决策 AI 应该做什么——它只能展示服务器告诉它的结果。

2. **为什么必须这样**？三个理由：反作弊（客户端不能修改 BT 让敌人变傻）、确定性（所有玩家看到同一个 AI 的行为——因为只有一个决策源）、权威伤害（服务器决定 AI 是否命中玩家，客户端无法伪造"我没被打到"）。

3. **`APawn::bReplicates = true` 就够了吗？** 不够。`bReplicates` 决定 Actor 是否参与复制，但**复制什么**由 `UPROPERTY(Replicated)` 和 `GetLifetimeReplicatedProps` 决定。AI Character 需要精确地声明：哪些属性是状态（需要复制）、哪些属性是决策临时的（不需要复制）。

#### 什么应该复制、什么不应该

这是网络 AI 中最容易犯错的设计决策。复制的每多一个变量，都意味着带宽成本 × AI 实例数。我们按类别梳理：

| 类别 | 是否复制 | 复制方式 | 理由 |
|------|---------|---------|------|
| **位置 (Location/Rotation)** | 必须 | 由 `UCharacterMovementComponent` 自动复制。使用 `bReplicateMovement` 控制。 | 客户端需要知道敌人在哪才能渲染。 |
| **生命值 (Health)** | 必须 | `UPROPERTY(ReplicatedUsing = OnRep_Health)`，reliable RPC | UI 需要显示血条；死亡动画触发依赖 Health。 |
| **动画状态 (Animation State)** | 条件性 | 通过复制 `PlayMontage` 调用 + 移动速度/方向 | 客户端不需要完整的 AnimBP 状态机，但需要"当前在播放什么动画"。 |
| **BT 执行状态** | 不复制 | N/A | BT 的当前节点指针、节点内存、Decorator 评估结果——客户端不需要，也不能看到（反作弊）。 |
| **Blackboard 值** | 选择性复制 | 只复制影响视觉的 key（如 `TargetActor`, `bIsStunned`），通过 `OnRep_` 或 RPC | 客户端不需要知道 `NextPatrolIndex`，但需要知道 `bIsStunned` 来播放被控动画。 |
| **感知数据 (Perception)** | 不复制 | N/A | 感知是 AI 决策的输入——客户端不需要知道"这个敌人听到了什么"。 |
| **Ability 激活 / GameplayEffect** | 必须（GAS 默认） | GAS 自带复制：`AbilitySystemComponent` 自动同步 Ability 激活和 GE 应用 | GAS 被设计为网络原生系统——ASC 的复制机制已经处理了 Ability 的预测和 GE 的同步。 |

**关键洞察**：Blackboard 中大部分数据是"决策中间变量"——`NextPatrolIndex`、`LastKnownPlayerPosition`、`BehaviorState`、`CombatTimer`。复制它们不仅浪费带宽，还会暴露 AI 内部逻辑给客户端（作弊风险）。只复制**视觉消费型 Blackboard 值**——客户端用这些值来渲染正确的动画、粒子、UI。

#### 客户端预测 Client-Side Prediction for AI

标准服务器权威模型有一个体验问题：**从服务器决策到客户端看到结果的延迟**。

想象一个近战战斗场景：服务器上的 AI 在帧 N 决定"攻击"。这个决策通过 Ability 激活 → ASC 复制 → 到达客户端，通常需要 50-150ms（取决于网络 RTT）。在这段延迟里，客户端玩家看到的敌人"无所事事"——然后突然"瞬移"到攻击动画中间。这破坏了战斗的可读性（readability）。

**客户端 AI 预测** 的思路是：客户端运行一个**简化版的 AI 逻辑**，在服务器确认到达之前**猜测**AI 会做什么，提前展示视觉反馈：

```
SERVER                                    CLIENT
  │                                         │
  │  BT decides: Attack                     │
  │  → ActivateAbility("Attack")             │
  │                                          │  Prediction:
  │                                          │  "Last attack was 2s ago,
  │                                          │  enemy is in range,
  │                                          │  probably attacking soon"
  │                                          │  → Show telegraph VFX
  │  (replication in flight...)              │
  │                                          │  → Start attack anticipation anim
  │  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~→   │  Server confirms: Attack
  │                                          │  → Blend prediction into real anim
```

实现客户端预测的三个层次（复杂度递增）：

| 层次 | 实现方式 | 适用场景 | 风险 |
|------|---------|---------|------|
| **Level 1: 预感 VFX** | 客户端检测"敌人在攻击范围内 + 正在面向我" → 播放隐约的蓄力特效（如武器发光、地面扩散圈）。不涉及动画预测。 | 慢节奏近战（如《黑暗之魂》类） | 极低——视觉提示即使不对也不影响 gameplay。 |
| **Level 2: 动画预测** | 客户端根据历史数据（过去 3 次攻击的间隔、当前距离）预测下次攻击时机 → 提前进入准备姿势（如抬剑）。服务器确认后混合。 | 快节奏近战（如《仁王》、《鬼泣》） | 中等——预测错误时需要从准备姿势平滑过渡回 idle，否则出现抖动。 |
| **Level 3: 行为预测** | 客户端运行完整的简化 BT（无 Blackboard、无感知）→ 预测 AI 会进入哪个顶层分支 → 提前展示符合该分支的动画状态。 | 竞技 PvE（如《命运 2》的敌人生成 AI） | 高——需要复杂的校正逻辑；如果预测与服务器不一致，校正可能比没有预测更糟糕。 |

**Level 1 的实现**（最实用、风险最低）：

```cpp
// On client, in AI Character's Tick
void AEnemyCharacter::TickClientPrediction(float DeltaTime)
{
    if (!HasAuthority())
    {
        // Simple heuristic: enemy in range + facing me → likely attacking soon
        APlayerCharacter* LocalPlayer = GetLocalPlayer();
        if (LocalPlayer)
        {
            float Dist = FVector::Dist(GetActorLocation(), LocalPlayer->GetActorLocation());
            bool bFacingMe = IsFacingTarget(LocalPlayer);
            bool bInAttackRange = Dist < AttackRange;

            if (bFacingMe && bInAttackRange && !bIsPlayingAttackAnim)
            {
                // Show subtle telegraph — no animation prediction, just VFX
                float ThreatLevel = 1.0f - (Dist / AttackRange); // 0..1, closer = more threat
                ShowTelegraphVFX(ThreatLevel);
            }
            else
            {
                HideTelegraphVFX();
            }
        }
    }
}
```

**校正策略**：当服务器数据到达且与客户端预测不一致时：

1. **预测成功**：从预测动画直接混合到服务器确认的动画（通常两者一致或接近，混合平滑）。
2. **预测失败（AI 没有攻击）**：从蓄力姿势过渡回 idle。使用 `Montage_Stop(0.15f)` 的 blend-out 时间——足够快以避免"凭空消失"，足够慢以避免抖动。
3. **预测失败（AI 做了不同攻击）**：如果预测轻攻击但实际是重攻击，利用两种攻击的起始姿势通常相似（都涉及抬手）——在抬手阶段完成校正。

**什么时候不应该做客户端预测**：
- **远程 AI**（狙击手、法师）：玩家看不到细节，100ms 延迟感知不到。
- **低频率决策 AI**（Boss 每 2 秒切换阶段）：等待服务器确认完全可接受。
- **已经使用 GAS 预测的系统**：GAS 自带客户端预测（通过 `InitAbilityActorInfo` + `ScopedPredictionKey`）。如果 AI 通过 GAS 激活 Ability，ASC 的预测管线已经在工作——不要叠加自己的预测层。

#### Network Relevancy

50 个 AI 敌人在场景中，但玩家只能看到 5 个。为什么要把 50 个 AI 的位置都复制给每个客户端？

UE 的 **Network Relevancy** 机制决定了"这个 Actor 应该复制到哪些客户端"。默认实现基于距离和可见性，但 AI 需要更精细的控制：

```
Default Relevancy:
  Actor is relevant if:
    - Distance(actor, player) < NetCullDistance
    - OR actor is always relevant (bAlwaysRelevant)
    - OR actor is the player's own Pawn/Controller

For AI, we customize:
  - Close AI (< 30m): Full replication (Position, Animation, Health, GAS)
  - Mid AI (30-80m): Minimal replication (Position only, 5Hz update rate)
  - Far AI (> 80m): No replication at all (server simulates, client doesn't know)
```

关键 UE 类和概念：

| 机制 | 类/设置 | 说明 |
|------|---------|------|
| **默认相关性** | `AActor::IsNetRelevantFor()` | 虚函数，可覆写。默认检查距离和所有者。 |
| **NetCullDistance** | `AActor::NetCullDistanceSquared` | 超过此距离的 Actor 不会被复制。AI 敌人通常设 3000-5000 单位。 |
| **ReplicationGraph** | `UReplicationGraph` (UE 4.20+) | 替代默认的相关性系统。为 AI 提供专门节点：`UReplicationGraphNode_ActorListFrequencyBuckets`——高距离 AI 降低复制频率。 |
| **Dormancy** | `AActor::SetNetDormancy()` | 完全停止复制直到被唤醒。适合远处非活动 AI。`DORM_Awake` / `DORM_DormantAll` / `DORM_DormantPartial`。 |

**UReplicationGraph 的基本集成**：

```cpp
// In your GameState or custom ReplicationGraph
void UMyReplicationGraph::RouteAddNetworkActorToNodes(
    const FNewReplicatedActorInfo& ActorInfo, FGlobalActorReplicationInfo& GlobalInfo)
{
    if (ActorInfo.Class->IsChildOf(AEnemyCharacter::StaticClass()))
    {
        // Add to distance-based node with custom cull distance
        UReplicationGraphNode_GridSpatialization2D* GridNode = GetGridNode();
        GridNode->AddActor(ActorInfo, GlobalInfo);

        // Set update frequency based on distance
        GlobalInfo.Settings.SetCullDistance(3000.0f);          // Cull beyond 30m
        GlobalInfo.Settings.SetCullDistanceSquared(9000000.0f);
    }
}
```

**Dormancy 在 AI 中的应用模式**：

```
AI Lifecycle:
  Active (near player)     → DORM_Awake, full replication
  Passive (far, visible)   → DORM_DormantPartial (replicate position only, 2Hz)
  Sleeping (far, invisible)→ DORM_DormantAll (no replication, server ticks at 0.5Hz)
  Waking (player approaches)→ FlushNetDormancy() → DORM_Awake
```

调用 `FlushNetDormancy()` 会强制立即复制 Actor 的所有属性——确保玩家接近时 AI 的状态立即可见，而非等待下一个复制间隔。

#### AI LOD + Network LOD 协同

AI 的决策 LOD（Level of Detail）和网络 LOD 是两个正交但需要协同的系统：

| LOD 级别 | AI Tick 频率 | BT 决策频率 | 网络更新频率 | 复制内容 |
|---------|------------|------------|------------|---------|
| **LOD 0 (近)** | 每帧 (60Hz) | 每帧评估 | 每帧 (位置) + 按需 (状态) | 全部 |
| **LOD 1 (中)** | 每 4 帧 (15Hz) | 每 0.25s 评估 | 每 0.1s (位置) | 位置 + 血量 |
| **LOD 2 (远)** | 每 20 帧 (3Hz) | 每 2.0s 评估 | 每 0.5s (位置) | 仅位置 |
| **LOD 3 (极远)** | 每 120 帧 (0.5Hz) | 暂停 BT | ~2.0s (位置) | 仅位置 |
| **离线** | 暂停 | 暂停 | 不复制 | 无 |

**协同设计的关键点**：

1. **LOD 切换时同步唤醒**：AI 从 LOD 3 切换到 LOD 0（玩家突然接近），在同一帧内需要：恢复 BT Tick → `FlushNetDormancy()` → 强制执行一次完整属性复制。顺序不对会导致客户端看到 T-pose 或位置跳变。

2. **GAS 的特殊处理**：GAS 的 `UAbilitySystemComponent` 有独立的复制机制。即使 AI 处于 LOD 2（低 Tick），如果它有一个持续性的 GameplayEffect（如增益光环），该 GE 的复制频率不应被降级——否则客户端看到的 buff 图标会闪烁。

3. **距离划分不可见**：LOD 切换的距离阈值必须有滞回（hysteresis）。例如：LOD 0→1 在 30m 切换，但 LOD 1→0 在 28m 切换。没有滞回的话，一个站在 30m 边界上的玩家会导致 AI 在两种 LOD 之间每帧切换，造成网络风暴。

#### RPC Patterns for AI

RPC（Remote Procedure Call）是 AI 网络通信的第二通道——复制（Replication）传递持续状态，RPC 传递瞬时事件。

**Server → Client RPC（最常用）**：

```cpp
// --- MULTICAST or CLIENT RPC: Play attack montage on all clients ---
UFUNCTION(NetMulticast, Reliable)
void Multicast_PlayAttackMontage(UAnimMontage* Montage, float PlayRate);

// --- CLIENT RPC: Spawn hit VFX on specific client ---
UFUNCTION(Client, Reliable)
void Client_SpawnHitEffect(FVector HitLocation, FVector HitNormal);

// --- MULTICAST (Unreliable): Update AI facial expression ---
UFUNCTION(NetMulticast, Unreliable)
void Multicast_UpdateFacialExpression(EFacialExpression Expression);
```

AI 中使用 RPC 的典型模式：

| 模式 | RPC 类型 | 示例 | 可靠性 |
|------|---------|------|--------|
| 播放动画 | `NetMulticast` | `Multicast_PlayAttackMontage` | Reliable——错过攻击动画体验很差 |
| 生成粒子 | `NetMulticast` 或 `Client` | `Multicast_SpawnMuzzleFlash` | Unreliable 通常够用——错过一个粒子看不出来 |
| 播放音效 | `NetMulticast` | `Multicast_PlayFootstepSound` | Unreliable 通常够用（人耳对丢帧不敏感） |
| 状态通知 | `Client` | `Client_NotifyBossPhaseChange` | Reliable——UI 更新不能丢失 |

**Client → Server RPC（谨慎使用）**：

AI 自身很少使用 Client→Server RPC，因为 AI 由服务器控制。但有一个例外：**AI 感知报告（Perception Reports）**。

在 UE 的原生 AI Perception 系统中，感知在服务器端运行——服务器做 raycast、检测可见性、更新 Stimuli。但在某些架构中（尤其是使用 `AIPerceptionStimuliSource` 的场景），客户端可以在本地做一些初步筛选，将"可能重要的刺激"上报给服务器做最终验证：

```cpp
// Client reports "I think I heard something here" — server validates
UFUNCTION(Server, Unreliable, WithValidation)
void Server_ReportSuspiciousSound(FVector Location, float Loudness);
```

**绝大多数情况下，服务器权威的感知系统已经足够——不要引入 Client→Server 的感知 RPC，除非你有明确的性能瓶颈证明需要客户端预筛选。**

---

### Part B — GAS + AI Deep Integration

#### GAS Architecture Overview for AI

Gameplay Ability System (GAS) 是 UE 中处理战斗和属性逻辑的网络原生框架。它最初为玩家角色设计，但它的架构特性使它与 AI 集成具有极高的价值：

```
AEnemyCharacter (APawn, replicates)
  ├── USkeletalMeshComponent
  ├── UCharacterMovementComponent
  ├── UAbilitySystemComponent (ASC)     ← GAS 核心：管理 Ability 激活和 GE 应用
  │     ├── Granted GameplayAbilities:
  │     │     ├── GA_EnemyFireWeapon    (由 BT Task 触发)
  │     │     ├── GA_EnemyDash          (由 BT Task 触发)
  │     │     ├── GA_EnemyHeal          (由 BT Task 触发)
  │     │     └── GA_EnemyStun          (由受到伤害事件触发)
  │     └── Active GameplayEffects:
  │           ├── GE_Stunned (Tag: State.Stunned)
  │           └── GE_AttackCooldown (Tag: Cooldown.Attack)
  │
  └── UEnemyAttributeSet (UAttributeSet)
        ├── float Health (replicated)
        ├── float MaxHealth (replicated)
        ├── float Stamina
        └── float Ammo
```

**GAS 对 AI 的四大集成点**：

1. **Ability 是 AI 动作**：`GA_EnemyFireWeapon` 不是一个简单的 C++ 函数调用——它是一个完整的 GameplayAbility，自带 cooldown、cost、interrupt 处理、网络复制。BT 的 Task 不直接调用"扣血量、播放动画、生成子弹"——它触发一个 Ability，由 Ability 的 `ActivateAbility()` 编排完整动作。

2. **GameplayEffect 是 AI 状态**：`State.Stunned` 不是一个 bool 变量——它是一个 GameplayTag 加在一个持续性的 GameplayEffect 上。BT Decorator 不检查 `bIsStunned` bool——它检查 `OwnerComp.GetAIOwner()->GetPawn()->GetAbilitySystemComponent()->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag("State.Stunned"))`。

3. **AttributeSet 是 AI 资源**：BT Service 定期读取 `Health`、`Stamina`、`Ammo` 属性值 → 写入 Blackboard → BT 分支据此选择行为。属性的修改（伤害、治疗、消耗）通过 GameplayEffect 处理——保证网络同步和 Modifier 计算的正确性。

4. **GameplayTags 是 AI 决策语言**：标签系统跨越 GAS 和 BT 的边界。同一个标签 `State.Stunned` 既被 GAS 用于标记"这个 AI 被眩晕了"，又被 BT 的 Decorator 用于检查"是否禁用攻击子树"。标签是这两个系统之间的**类型安全、网络感知的共享词汇**。

#### GAS + BT 的数据流模型

```
┌─────────────────────────────────────────────────────────────────┐
│                         BLACKBOARD                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
│  │ Health    │ │ Stamina  │ │ Ammo     │ │ bHasStunTag      │    │
│  │ (Float)   │ │ (Float)  │ │ (Float)  │ │ (Bool)           │    │
│  └─────┬─────┘ └─────┬────┘ └────┬─────┘ └────────┬─────────┘    │
│        │              │           │                │              │
│  ┌─────▼──────────────▼───────────▼────────────────▼──────────┐  │
│  │              BTService_UpdateGASValues                      │  │
│  │  Reads ASC → AttributeSet → writes Blackboard              │  │
│  │  Reads ASC → GameplayTagContainer → writes Blackboard      │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │          BEHAVIOR TREE (reads Blackboard)                    ││
│  │  Selector:                                                   ││
│  │  ├── Sequence "Combat"                                       ││
│  │  │   ├── Decorator: NOT HasTag(State.Stunned)                ││
│  │  │   ├── Decorator: NOT HasTag(Cooldown.Attack)              ││
│  │  │   ├── Decorator: Blackboard Health > 0.2 * MaxHealth      ││
│  │  │   └── BTTask_ActivateAbilityByTag("Ability.Attack")       ││
│  │  ├── Sequence "Retreat"                                      ││
│  │  │   ├── Decorator: Blackboard Health < 0.2 * MaxHealth      ││
│  │  │   └── BTTask_ActivateAbilityByTag("Ability.Dash")         ││
│  │  └── Sequence "Stunned"                                      ││
│  │      ├── Decorator: HasTag(State.Stunned)                    ││
│  │      └── BTTask_Wait (no action — just wait)                 ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**这个架构的核心价值**：BT 不直接调用 `GA_EnemyFireWeapon`——它通过 `BTTask_ActivateAbilityByTag` 按标签触发。当设计师在编辑器中配置 BT 时，他们不需要知道 C++ 类的名字——只需要知道 `Ability.Attack` 标签。这个标签到具体 Ability 的映射在 `AEnemyCharacter::BeginPlay()` 中通过 `GiveAbility()` 建立——完全数据驱动。

#### How AI Triggers Abilities via BT

BT 触发 Ability 的标准模式：

```cpp
// In BTTask_ActivateAbilityByTag
EBTNodeResult::Type UBTTask_ActivateAbilityByTag::ExecuteTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    AAIController* AIController = OwnerComp.GetAIOwner();
    APawn* AIPawn = AIController->GetPawn();
    UAbilitySystemComponent* ASC = AIPawn->FindComponentByClass<UAbilitySystemComponent>();

    if (ASC && AbilityTag.IsValid())
    {
        // TryActivateAbilitiesByTag checks cooldowns, costs, blocking tags automatically
        bool bSuccess = ASC->TryActivateAbilitiesByTag(
            FGameplayTagContainer(AbilityTag));

        return bSuccess ? EBTNodeResult::Succeeded : EBTNodeResult::Failed;
    }

    return EBTNodeResult::Failed;
}
```

**为什么通过标签而不是直接调用**：
- `TryActivateAbilitiesByTag` 自动处理 GAS 的激活条件检查：该 Ability 的 cooldown 是否完毕？cost 是否付得起？是否有 block tag 阻止激活？——BT Task 不需要知道这些逻辑。
- 同一个标签可以对应多个 Ability（如 `Ability.Attack`→ 轻攻击 / 重攻击随机选择），`TryActivateAbilitiesByTag` 会选择第一个满足激活条件的。
- 如果 AI Character 的不同子类有不同的 Ability 集合（如 Boss 版 vs 普通版），BT 不需要修改——只需在 `BeginPlay` 中授予不同的 Ability。

#### GameplayEffect for AI State: 眩晕为例

眩晕不是 AI 代码中的一个 `bIsStunned` bool 和 `StunTimer` float——它是 GAS 中的一个 GameplayEffect：

**GE_Stun 的配置（通常在 DataTable 或 Blueprint 中定义）**：

```
GameplayEffect: GE_Stun
  Duration Policy: Has Duration
  Duration: 3.0s (based on Magnitude)

  Granted Tags (Added):
    State.Stunned          ← This tag is what BT checks

  Granted Tags (Removed):
    State.Attacking        ← If AI was attacking, cancel it
    State.Moving           ← Stop movement

  GameplayEffect Components:
    - RemoveOtherGameplayEffectOnApplication:
        Remove any GE with tag "State.Interruptible"
```

当 AI 被击中且附带眩晕效果时：

```cpp
// Damage was applied; now check for stun
void AEnemyCharacter::OnDamageReceived(float Damage, const FGameplayEffectSpec& DamageSpec)
{
    // The damage GE may have a StunChance setbycaller magnitude
    const FGameplayTag StunChanceTag = FGameplayTag::RequestGameplayTag("Effect.StunChance");
    float StunChance = DamageSpec.GetSetByCallerMagnitude(StunChanceTag, false, 0.0f);

    if (FMath::FRand() < StunChance)
    {
        // Apply stun GE through ASC — automatically sets State.Stunned tag
        FGameplayEffectContextHandle Context = ASC->MakeEffectContext();
        FGameplayEffectSpecHandle StunSpec = ASC->MakeOutgoingSpec(
            GE_Stun, 1.0f, Context);
        ASC->ApplyGameplayEffectSpecToSelf(*StunSpec.Data.Get());
    }
}
```

**BT Decorator 对眩晕的反应**：

```
Behavior Tree Structure:
  Selector (Root)
  ├── Sequence "Stunned"          ← Priority 1: if stunned, just wait
  │   ├── Decorator: HasGameplayTag (State.Stunned)
  │   │   FlowAbortMode: Both     ← When stunned → abort lower priority
  │   │                          ← When not stunned → abort self, fall through
  │   └── Wait (passive — do nothing)
  │
  └── Selector "NormalBehavior"   ← Priority 2: normal combat behavior
      ├── Sequence "Attack" ...
      ├── Sequence "Dash" ...
      └── Sequence "Idle" ...
```

`FlowAbortMode::Both` 是关键：当 `State.Stunned` 标签出现时，这个 Decorator 的条件变为 true → 触发 `LowerPriority` abort → 打断正常的攻击/移动行为。当眩晕 GE 过期（标签被移除），Decorator 条件变为 false → 触发 `Self` abort → 退出 `Stunned` 分支，恢复正常行为。

**为什么这比手动管理 `bIsStunned` + Timer 更好**：
- GE 的持续时间、Modifier、Tag 都是数据驱动的——设计师可以在不修改 C++ 的情况下调整眩晕时长。
- 如果一个 AI 同时受到多个 CC（眩晕 + 冰冻），`HasMatchingGameplayTag` 天然处理多状态并存。
- GE 的网络复制是 GAS 自带的——服务器应用 GE 后，客户端自动同步 `State.Stunned` 标签，触发正确的动画状态机切换。

#### Cooldown and Cost Management

GAS 的 cooldown 和 cost 机制直接服务于 AI 的可行性检查：

**Cooldown 集成**：

```cpp
// In GA_EnemyFireWeapon
void UGA_EnemyFireWeapon::ActivateAbility(...)
{
    // ... do attack logic ...

    // Commit cooldown — this applies a GE with Cooldown.Attack tag
    CommitAbilityCooldown(Handle, CurrentActorInfo, GetCurrentActivationInfoRef(), true);

    // Alternative: manually define cooldown in the Ability's CooldownGameplayEffectClass
    // The GE_AttackCooldown has:
    //   - Duration: 2.0s
    //   - Granted Tag: Cooldown.Attack
    //   - Modifier: reduce cooldown by Haste attribute
}
```

BT Decorator 检查冷却：

```
Sequence "RangedAttack"
  ├── Decorator: HasGameplayTag (Cooldown.Attack) [Invert Condition: true]
  │   FlowAbortMode: None          ← Only check when branch is entered
  │   (Passes when Cooldown.Attack tag is NOT present)
  │
  └── BTTask_ActivateAbilityByTag (Ability.Attack.Ranged)
```

或者使用 UE 内置的 `UBTDecorator_TagCooldown`（如果项目中使用 GameplayTag 冷却模式）：

```
Sequence "RangedAttack"
  ├── Decorator: TagCooldown
  │   GameplayTag: Cooldown.Attack
  │   CooldownDuration: 2.0
  │   bAddToExistingDuration: false
  │   bActivatesCooldown: true
  └── BTTask_ActivateAbilityByTag (Ability.Attack.Ranged)
```

**Cost 管理**：在 BT 决策前检查资源是否足够：

```cpp
// BTService_UpdateAttributeValues — runs periodically under Combat composite
void UBTService_UpdateAttributeValues::TickNode(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds)
{
    AAIController* AIController = OwnerComp.GetAIOwner();
    APawn* AIPawn = AIController->GetPawn();
    UAbilitySystemComponent* ASC = AIPawn->FindComponentByClass<UAbilitySystemComponent>();
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();

    if (ASC && BB)
    {
        // Read attribute values and write to Blackboard
        float Health = ASC->GetNumericAttribute(UEnemyAttributeSet::GetHealthAttribute());
        float MaxHealth = ASC->GetNumericAttribute(UEnemyAttributeSet::GetMaxHealthAttribute());
        float Stamina = ASC->GetNumericAttribute(UEnemyAttributeSet::GetStaminaAttribute());
        float Ammo = ASC->GetNumericAttribute(UEnemyAttributeSet::GetAmmoAttribute());

        BB->SetValueAsFloat(HealthKey.SelectedKeyName, Health);
        BB->SetValueAsFloat(MaxHealthKey.SelectedKeyName, MaxHealth);
        BB->SetValueAsFloat(StaminaKey.SelectedKeyName, Stamina);
        BB->SetValueAsFloat(AmmoKey.SelectedKeyName, Ammo);

        // Also sync tag states for BT Decorators that check Blackboard instead of ASC
        bool bStunned = ASC->HasMatchingGameplayTag(
            FGameplayTag::RequestGameplayTag("State.Stunned"));
        BB->SetValueAsBool(IsStunnedKey.SelectedKeyName, bStunned);
    }
}
```

然后用 Blackboard-based Decorator 在 BT 中做条件判断：

```
Sequence "PowerAttack"
  ├── Decorator: Blackboard (Stamina > 50.0f)
  ├── Decorator: Blackboard (Ammo > 0.0f)
  └── BTTask_ActivateAbilityByTag (Ability.Attack.PowerShot)
```

#### GameplayTags as AI Decision Backbone

当 GAS 和 BT 通过 GameplayTags 深度集成后，AI 决策逻辑从"if-else 嵌套在 C++ 代码中"变成"标签条件在 BT 编辑器中可视化配置"：

**标签分层策略**：

```
State.*       — AI 的当前状态（由 GE 授予/移除）
  State.Stunned
  State.KnockedDown
  State.Frozen
  State.Burning
  State.InCombat
  State.Fleeing
  State.Healing

Cooldown.*    — 冷却状态（由 Ability cooldown GE 授予）
  Cooldown.Attack
  Cooldown.Special
  Cooldown.Dash
  Cooldown.Heal

Ability.*     — Ability 触发标签
  Ability.Attack.Melee
  Ability.Attack.Ranged
  Ability.Attack.Power
  Ability.Dash
  Ability.Heal
  Ability.Taunt

Effect.*      — 效果和 buff/debuff 标签
  Effect.Buff.DamageBoost
  Effect.Debuff.ArmorBreak
  Effect.Invulnerable
```

**BT 中的标签驱动决策**（编辑器视图的文本表示）：

```
Selector (Root)                           ← Evaluate every frame
│
├── Sequence "Heal"                       ← Priority 1: survival
│   ├── Decorator: HasGameplayTag (State.Burning)  ← OR: is taking damage over time?
│   ├── Decorator: Blackboard (Health < 30.0f)     ← AND: low health
│   ├── Decorator: NOT HasGameplayTag (Cooldown.Heal) ← AND: heal off cooldown
│   └── BTTask_ActivateAbilityByTag (Ability.Heal)
│
├── Sequence "Power Attack"               ← Priority 2: burst damage
│   ├── Decorator: Blackboard (Stamina > 50.0f)
│   ├── Decorator: NOT HasGameplayTag (Cooldown.Special)
│   └── BTTask_ActivateAbilityByTag (Ability.Attack.Power)
│
├── Sequence "Retreat"                    ← Priority 3: reposition
│   ├── Decorator: HasGameplayTag (State.InCombat)
│   ├── Decorator: Blackboard (Health < 50.0f)
│   ├── Decorator: NOT HasGameplayTag (Cooldown.Dash)
│   └── BTTask_ActivateAbilityByTag (Ability.Dash)
│
├── Sequence "Ranged"                     ← Priority 4: ranged engage
│   ├── Decorator: NOT HasGameplayTag (Cooldown.Attack)
│   ├── Decorator: Blackboard (Ammo > 0.0f)
│   └── BTTask_ActivateAbilityByTag (Ability.Attack.Ranged)
│
└── Sequence "Melee"                      ← Priority 5: melee engage
    ├── Decorator: NOT HasGameplayTag (Cooldown.Attack)
    └── BTTask_ActivateAbilityByTag (Ability.Attack.Melee)
```

**这个结构的工程优势**：
- **设计师可以在 BT 编辑器中调整优先级顺序**——拖动 Sequence 节点重排。
- **新增行为不需要修改 C++**——只需在 `BeginPlay()` 中授予新的 Ability，在 BT 中增加新的 Sequence 分支。
- **标签的层级关系**（如 `Cooldown.Attack` 是 `Cooldown.*` 的子标签）可以被 `HasMatchingGameplayTag` 利用——你可以检查 `MatchesTag(Cooldown)` 来判断"是否有任何冷却"，而不必列出所有冷却子标签。

---

## 2. 代码示例

> 以下代码基于 UE 5.3+ API。所有示例都是完整可编译的 C++ 类，包含头文件和实现文件。

### 示例 A: 网络化 AI 设置

**目的**：展示服务器端 AI 的完整网络设置——AIController 在服务器运行 BT，角色属性复制到客户端，`OnRep_` 用作客户端视觉更新触发器。

```cpp
// EnemyCharacter.h
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AbilitySystemInterface.h"
#include "EnemyCharacter.generated.h"

class UAbilitySystemComponent;
class UEnemyAttributeSet;

UCLASS()
class AEnemyCharacter : public ACharacter, public IAbilitySystemInterface
{
    GENERATED_BODY()

public:
    AEnemyCharacter();

    // IAbilitySystemInterface
    virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;

    // Called on server when health changes — triggers replication
    void SetHealth(float NewHealth);
    float GetHealth() const { return Health; }
    float GetMaxHealth() const { return MaxHealth; }

protected:
    virtual void BeginPlay() override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

    // Replicated properties
    UPROPERTY(ReplicatedUsing = OnRep_Health)
    float Health;

    UPROPERTY(ReplicatedUsing = OnRep_MaxHealth)
    float MaxHealth;

    UPROPERTY(ReplicatedUsing = OnRep_AnimationState)
    uint8 AnimationState;

    // OnRep callbacks — trigger client-side visual updates
    UFUNCTION()
    void OnRep_Health();

    UFUNCTION()
    void OnRep_MaxHealth();

    UFUNCTION()
    void OnRep_AnimationState();

    // Client-side visual update implementations
    UFUNCTION()
    void UpdateHealthBarWidget();

    UFUNCTION()
    void TriggerAnimationStateChange();

private:
    UPROPERTY(VisibleAnywhere, Category = "GAS")
    UAbilitySystemComponent* AbilitySystemComponent;

    UPROPERTY()
    UEnemyAttributeSet* AttributeSet;

    // Client-cached widget reference
    class UEnemyHealthBar* HealthBarWidget;

    // Animation state enum
    static constexpr uint8 ANIM_Idle = 0;
    static constexpr uint8 ANIM_Combat = 1;
    static constexpr uint8 ANIM_Stunned = 2;
    static constexpr uint8 ANIM_Dead = 3;
};
```

```cpp
// EnemyCharacter.cpp
#include "EnemyCharacter.h"
#include "AbilitySystemComponent.h"
#include "EnemyAttributeSet.h"
#include "Net/UnrealNetwork.h"
#include "Components/WidgetComponent.h"

AEnemyCharacter::AEnemyCharacter()
{
    bReplicates = true;
    // Movement replication is handled by UCharacterMovementComponent by default
    // Set replication frequency for this specific character type
    NetUpdateFrequency = 100.0f;          // 100Hz max — engine clamps to reasonable value
    MinNetUpdateFrequency = 33.0f;        // ~30fps minimum
    NetCullDistanceSquared = 9000000.0f;  // 3000 units cull distance

    AbilitySystemComponent = CreateDefaultSubobject<UAbilitySystemComponent>(
        TEXT("AbilitySystemComponent"));
    AbilitySystemComponent->SetIsReplicated(true);
    // Minimal replication mode: only GameplayEffects and GameplayTags are replicated,
    // not the full Ability activation state (saves bandwidth for AI)
    AbilitySystemComponent->SetReplicationMode(EGameplayEffectReplicationMode::Minimal);

    AttributeSet = CreateDefaultSubobject<UEnemyAttributeSet>(TEXT("AttributeSet"));

    Health = 100.0f;
    MaxHealth = 100.0f;
    AnimationState = ANIM_Idle;
}

UAbilitySystemComponent* AEnemyCharacter::GetAbilitySystemComponent() const
{
    return AbilitySystemComponent;
}

void AEnemyCharacter::BeginPlay()
{
    Super::BeginPlay();

    if (HasAuthority())
    {
        // Server-side initialization
        Health = MaxHealth;

        // Initialize ASC with this actor as both owner and avatar
        AbilitySystemComponent->InitAbilityActorInfo(this, this);

        // Grant default attributes
        if (IsValid(AttributeSet))
        {
            // Apply initial GE to set base attribute values
            // This is typically a GE with instant duration and attribute modifiers
            FGameplayEffectContextHandle Context = AbilitySystemComponent->MakeEffectContext();
            // ... apply default attribute GE ...
        }

        // Server-side: find and cache health bar widget
        // (WidgetComponent might be on a child actor or component)
    }
    else
    {
        // Client-side: find health bar widget for later updates
        TArray<UWidgetComponent*> WidgetComponents;
        GetComponents<UWidgetComponent>(WidgetComponents);
        for (UWidgetComponent* WidgetComp : WidgetComponents)
        {
            if (WidgetComp->GetWidget())
            {
                HealthBarWidget = Cast<UEnemyHealthBar>(WidgetComp->GetWidget());
                if (HealthBarWidget) break;
            }
        }
    }
}

void AEnemyCharacter::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    // COND_None = replicate to all clients unconditionally
    DOREPLIFETIME_CONDITION(AEnemyCharacter, Health, COND_None);
    DOREPLIFETIME_CONDITION(AEnemyCharacter, MaxHealth, COND_None);
    // COND_SkipOwner — AI doesn't have an "owner client", but this is safe practice
    DOREPLIFETIME_CONDITION(AEnemyCharacter, AnimationState, COND_None);
}

void AEnemyCharacter::SetHealth(float NewHealth)
{
    if (HasAuthority())
    {
        float OldHealth = Health;
        Health = FMath::Clamp(NewHealth, 0.0f, MaxHealth);
        // UPROPERTY(Replicated) — engine marks dirty, replicates on next update

        // On server, trigger logic immediately (don't wait for OnRep)
        if (Health <= 0.0f && OldHealth > 0.0f)
        {
            // Server-side death handling
            SetAnimationState(ANIM_Dead);
        }
    }
}

// ========== OnRep Callbacks ==========

void AEnemyCharacter::OnRep_Health()
{
    // Called on clients when Health is replicated
    // Don't run gameplay logic here — only visual updates
    UpdateHealthBarWidget();

    // Check for death on client for animation trigger
    if (Health <= 0.0f)
    {
        TriggerAnimationStateChange();
    }
}

void AEnemyCharacter::OnRep_MaxHealth()
{
    UpdateHealthBarWidget();
}

void AEnemyCharacter::OnRep_AnimationState()
{
    TriggerAnimationStateChange();
}

void AEnemyCharacter::UpdateHealthBarWidget()
{
    if (HealthBarWidget)
    {
        float HealthPercent = (MaxHealth > 0.0f) ? (Health / MaxHealth) : 0.0f;
        HealthBarWidget->SetHealthPercent(HealthPercent);
    }
}

void AEnemyCharacter::TriggerAnimationStateChange()
{
    // Drive the Animation Blueprint's state machine via a replicated variable
    // The AnimBP reads AnimationState in its AnimGraph to select the correct state

    // For montage-based animations:
    // The server calls Multicast_PlayMontage, which replicates reliably to all clients
}

void AEnemyCharacter::SetAnimationState(uint8 NewState)
{
    if (HasAuthority())
    {
        AnimationState = NewState;
        // Replication happens automatically
    }
}
```

```cpp
// EnemyAIController.h
#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "EnemyAIController.generated.h"

UCLASS()
class AEnemyAIController : public AAIController
{
    GENERATED_BODY()

public:
    AEnemyAIController();

protected:
    virtual void BeginPlay() override;
    virtual void OnPossess(APawn* InPawn) override;

    // Behavior Tree asset — configured in Blueprint subclass or DataAsset
    UPROPERTY(EditDefaultsOnly, Category = "AI")
    UBehaviorTree* BehaviorTreeAsset;

    // Blackboard asset — must match the keys used by the BT
    UPROPERTY(EditDefaultsOnly, Category = "AI")
    UBlackboardData* BlackboardAsset;

private:
    // Ensure BT only runs on server
    void StartBehaviorTreeIfServer();
};
```

```cpp
// EnemyAIController.cpp
#include "EnemyAIController.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "EnemyCharacter.h"

AEnemyAIController::AEnemyAIController()
{
    // AIController itself does NOT replicate to clients
    bReplicates = false;
}

void AEnemyAIController::BeginPlay()
{
    Super::BeginPlay();
}

void AEnemyAIController::OnPossess(APawn* InPawn)
{
    Super::OnPossess(InPawn);
    StartBehaviorTreeIfServer();
}

void AEnemyAIController::StartBehaviorTreeIfServer()
{
    // Safety check: only server runs the BT
    if (!HasAuthority())
    {
        UE_LOG(LogTemp, Warning, TEXT("EnemyAIController::StartBehaviorTreeIfServer called on client — ignoring"));
        return;
    }

    if (BehaviorTreeAsset)
    {
        // Initialize Blackboard with the specified asset
        if (BlackboardAsset)
        {
            UseBlackboard(BlackboardAsset, Blackboard);
        }

        // Run the behavior tree — this starts the server-side AI loop
        RunBehaviorTree(BehaviorTreeAsset);

        UE_LOG(LogTemp, Log, TEXT("Enemy AI started: %s"), *GetName());
    }
}
```

### 示例 B: GAS 集成 AI

**目的**：展示 ASC 在 AI 角色上的完整设置，包含自定义 AttributeSet、AI Attack Ability、以及 BT Task/Service 与 GAS 的桥接。

```cpp
// EnemyAttributeSet.h
#pragma once

#include "CoreMinimal.h"
#include "AttributeSet.h"
#include "AbilitySystemComponent.h"
#include "EnemyAttributeSet.generated.h"

// Attribute accessors — macros from AttributeSet.h
#define ATTRIBUTE_ACCESSORS(ClassName, PropertyName) \
    GAMEPLAYATTRIBUTE_PROPERTY_GETTER(ClassName, PropertyName) \
    GAMEPLAYATTRIBUTE_VALUE_GETTER(PropertyName) \
    GAMEPLAYATTRIBUTE_VALUE_SETTER(PropertyName) \
    GAMEPLAYATTRIBUTE_VALUE_INITTER(PropertyName)

UCLASS()
class UEnemyAttributeSet : public UAttributeSet
{
    GENERATED_BODY()

public:
    UEnemyAttributeSet();

    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

    // Attribute clamp and validation on modification
    virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;
    virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;

    // --- Core combat attributes ---

    UPROPERTY(BlueprintReadOnly, Category = "Attributes", ReplicatedUsing = OnRep_Health)
    FGameplayAttributeData Health;
    ATTRIBUTE_ACCESSORS(UEnemyAttributeSet, Health)

    UPROPERTY(BlueprintReadOnly, Category = "Attributes", ReplicatedUsing = OnRep_MaxHealth)
    FGameplayAttributeData MaxHealth;
    ATTRIBUTE_ACCESSORS(UEnemyAttributeSet, MaxHealth)

    // --- Resource attributes ---

    UPROPERTY(BlueprintReadOnly, Category = "Attributes", ReplicatedUsing = OnRep_Stamina)
    FGameplayAttributeData Stamina;
    ATTRIBUTE_ACCESSORS(UEnemyAttributeSet, Stamina)

    UPROPERTY(BlueprintReadOnly, Category = "Attributes", ReplicatedUsing = OnRep_MaxStamina)
    FGameplayAttributeData MaxStamina;
    ATTRIBUTE_ACCESSORS(UEnemyAttributeSet, MaxStamina)

    UPROPERTY(BlueprintReadOnly, Category = "Attributes", ReplicatedUsing = OnRep_Ammo)
    FGameplayAttributeData Ammo;
    ATTRIBUTE_ACCESSORS(UEnemyAttributeSet, Ammo)

    // --- OnRep functions for client-side UI update ---
    UFUNCTION()
    void OnRep_Health(const FGameplayAttributeData& OldHealth);

    UFUNCTION()
    void OnRep_MaxHealth(const FGameplayAttributeData& OldMaxHealth);

    UFUNCTION()
    void OnRep_Stamina(const FGameplayAttributeData& OldStamina);

    UFUNCTION()
    void OnRep_MaxStamina(const FGameplayAttributeData& OldMaxStamina);

    UFUNCTION()
    void OnRep_Ammo(const FGameplayAttributeData& OldAmmo);
};
```

```cpp
// EnemyAttributeSet.cpp
#include "EnemyAttributeSet.h"
#include "Net/UnrealNetwork.h"
#include "GameplayEffectExtension.h"

UEnemyAttributeSet::UEnemyAttributeSet()
{
    Health = 100.0f;
    MaxHealth = 100.0f;
    Stamina = 80.0f;
    MaxStamina = 100.0f;
    Ammo = 30.0f;
}

void UEnemyAttributeSet::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    DOREPLIFETIME_CONDITION_NOTIFY(UEnemyAttributeSet, Health, COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UEnemyAttributeSet, MaxHealth, COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UEnemyAttributeSet, Stamina, COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UEnemyAttributeSet, MaxStamina, COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UEnemyAttributeSet, Ammo, COND_None, REPNOTIFY_Always);
}

void UEnemyAttributeSet::PreAttributeChange(
    const FGameplayAttribute& Attribute, float& NewValue)
{
    Super::PreAttributeChange(Attribute, NewValue);

    // Clamp to valid ranges before the value is applied
    if (Attribute == GetHealthAttribute())
    {
        NewValue = FMath::Clamp(NewValue, 0.0f, GetMaxHealth());
    }
    else if (Attribute == GetStaminaAttribute())
    {
        NewValue = FMath::Clamp(NewValue, 0.0f, GetMaxStamina());
    }
    else if (Attribute == GetAmmoAttribute())
    {
        NewValue = FMath::Clamp(NewValue, 0.0f, 999.0f);
    }
}

void UEnemyAttributeSet::PostGameplayEffectExecute(
    const FGameplayEffectModCallbackData& Data)
{
    Super::PostGameplayEffectExecute(Data);

    // Post-gameplay effect execution: handle death, resource depletion, etc.
    if (Data.EvaluatedData.Attribute == GetHealthAttribute())
    {
        if (GetHealth() <= 0.0f)
        {
            // Notify AI that this character is dead
            // This can be done through GAS tag or delegate
            AActor* Owner = GetOwningActor();
            if (Owner && Owner->HasAuthority())
            {
                UAbilitySystemComponent* ASC = Data.Target.GetOwnerGAS();
                if (ASC)
                {
                    // Apply a "dead" tag — BT will react to this
                    FGameplayTag DeadTag = FGameplayTag::RequestGameplayTag("State.Dead");
                    ASC->AddLooseGameplayTag(DeadTag);
                }
            }
        }
    }
}

// OnRep implementations — delegate to the owning character for UI updates
void UEnemyAttributeSet::OnRep_Health(const FGameplayAttributeData& OldHealth)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UEnemyAttributeSet, Health, OldHealth);
}

void UEnemyAttributeSet::OnRep_MaxHealth(const FGameplayAttributeData& OldMaxHealth)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UEnemyAttributeSet, MaxHealth, OldMaxHealth);
}

void UEnemyAttributeSet::OnRep_Stamina(const FGameplayAttributeData& OldStamina)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UEnemyAttributeSet, Stamina, OldStamina);
}

void UEnemyAttributeSet::OnRep_MaxStamina(const FGameplayAttributeData& OldMaxStamina)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UEnemyAttributeSet, MaxStamina, OldMaxStamina);
}

void UEnemyAttributeSet::OnRep_Ammo(const FGameplayAttributeData& OldAmmo)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UEnemyAttributeSet, Ammo, OldAmmo);
}
```

```cpp
// GA_EnemyRangedAttack.h
#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbility.h"
#include "GA_EnemyRangedAttack.generated.h"

/**
 * AI Ranged Attack Ability.
 * Activated by BT via TryActivateAbilityByTag.
 * Handles animation montage, projectile spawning, and cooldown commit.
 */
UCLASS()
class UGA_EnemyRangedAttack : public UGameplayAbility
{
    GENERATED_BODY()

public:
    UGA_EnemyRangedAttack();

    virtual void ActivateAbility(
        const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo,
        const FGameplayEventData* TriggerEventData) override;

    virtual void EndAbility(
        const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo,
        bool bReplicateEndAbility, bool bWasCancelled) override;

    // Ability tag — used by BT to trigger this ability
    UPROPERTY(EditDefaultsOnly, Category = "Ability")
    FGameplayTag AbilityTag;

    // Cooldown duration in seconds
    UPROPERTY(EditDefaultsOnly, Category = "Cooldown")
    float CooldownDuration = 2.0f;

    // Stamina cost per use
    UPROPERTY(EditDefaultsOnly, Category = "Cost")
    float StaminaCost = 15.0f;

    // Ammo consumed per shot
    UPROPERTY(EditDefaultsOnly, Category = "Cost")
    float AmmoCost = 1.0f;

    // Attack montage for visual representation
    UPROPERTY(EditDefaultsOnly, Category = "Animation")
    UAnimMontage* AttackMontage;

    // Projectile class to spawn
    UPROPERTY(EditDefaultsOnly, Category = "Combat")
    TSubclassOf<AActor> ProjectileClass;

protected:
    // Commit the cooldown and cost
    virtual void CommitExecute(const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo) override;

private:
    // Called when the attack montage finishes
    UFUNCTION()
    void OnMontageCompleted();

    // Called when the attack montage is interrupted
    UFUNCTION()
    void OnMontageInterrupted();

    // Spawn the projectile
    void FireProjectile();

    FGameplayAbilitySpecHandle CurrentHandle;
    const FGameplayAbilityActorInfo* CurrentActorInfo;
    FGameplayAbilityActivationInfo CurrentActivationInfo;

    FTimerHandle MontageTimeoutHandle;
};
```

```cpp
// GA_EnemyRangedAttack.cpp
#include "GA_EnemyRangedAttack.h"
#include "AbilitySystemComponent.h"
#include "EnemyAttributeSet.h"
#include "GameFramework/Character.h"
#include "Animation/AnimInstance.h"
#include "TimerManager.h"

UGA_EnemyRangedAttack::UGA_EnemyRangedAttack()
{
    // This ability is instanced per execution — AI-specific: don't reuse across instances
    InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerExecution;

    // Networking: execute on server, minimal replication to clients
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerInitiated;

    // This ability CANNOT be predicted by the client (server authority for AI)
    NetSecurityPolicy = EGameplayAbilityNetSecurityPolicy::ServerOnly;

    // Trigger tag — BT's TryActivateAbilityByTag matches against this
    AbilityTag = FGameplayTag::RequestGameplayTag("Ability.Attack.Ranged");
    AbilityTags.AddTag(AbilityTag);

    // Block this ability if we're stunned
    BlockAbilitiesWithTag.AddTag(FGameplayTag::RequestGameplayTag("State.Stunned"));
    BlockAbilitiesWithTag.AddTag(FGameplayTag::RequestGameplayTag("State.Dead"));

    // When activating, cancel abilities tagged as interruptible
    CancelAbilitiesWithTag.AddTag(FGameplayTag::RequestGameplayTag("State.Interruptible"));
}

void UGA_EnemyRangedAttack::ActivateAbility(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo,
    const FGameplayEventData* TriggerEventData)
{
    if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
    {
        // Commit failed — cooldown not ready or cost can't be paid
        EndAbility(Handle, ActorInfo, ActivationInfo, true, false);
        return;
    }

    // Cache handles for async completion
    CurrentHandle = Handle;
    CurrentActorInfo = ActorInfo;
    CurrentActivationInfo = ActivationInfo;

    // Mark as interruptible so other abilities can cancel this one
    if (UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get())
    {
        ASC->AddLooseGameplayTag(
            FGameplayTag::RequestGameplayTag("State.Interruptible"));
    }

    // Play attack montage on the AI character
    ACharacter* Character = Cast<ACharacter>(ActorInfo->AvatarActor.Get());
    if (Character && AttackMontage)
    {
        UAnimInstance* AnimInstance = Character->GetMesh()->GetAnimInstance();
        if (AnimInstance)
        {
            float MontageLength = AnimInstance->Montage_Play(AttackMontage);

            // Bind to montage completion delegates
            FOnMontageEnded EndDelegate;
            EndDelegate.BindUObject(this, &UGA_EnemyRangedAttack::OnMontageCompleted);
            AnimInstance->Montage_SetEndDelegate(EndDelegate, AttackMontage);

            // Fire projectile at the appropriate time (mid-animation via notifier is better,
            // but for simplicity we use a timer-based approach)
            float FireTime = MontageLength * 0.4f; // 40% into the animation
            Character->GetWorldTimerManager().SetTimer(
                MontageTimeoutHandle,
                this, &UGA_EnemyRangedAttack::FireProjectile,
                FireTime, false);
        }
    }
    else
    {
        // No montage — fire immediately
        FireProjectile();
        EndAbility(Handle, ActorInfo, ActivationInfo, true, false);
    }
}

void UGA_EnemyRangedAttack::EndAbility(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo,
    bool bReplicateEndAbility, bool bWasCancelled)
{
    // Remove interruptible tag
    if (UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get())
    {
        ASC->RemoveLooseGameplayTag(
            FGameplayTag::RequestGameplayTag("State.Interruptible"));
    }

    // Clear montage timer
    if (ActorInfo->AvatarActor.IsValid())
    {
        ActorInfo->AvatarActor->GetWorldTimerManager().ClearTimer(MontageTimeoutHandle);
    }

    Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

void UGA_EnemyRangedAttack::CommitExecute(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo)
{
    // Commit cooldown and cost through GAS standard path
    // This applies the cooldown GE and cost GE automatically
    Super::CommitExecute(Handle, ActorInfo, ActivationInfo);
}

void UGA_EnemyRangedAttack::OnMontageCompleted()
{
    EndAbility(CurrentHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UGA_EnemyRangedAttack::OnMontageInterrupted()
{
    EndAbility(CurrentHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}

void UGA_EnemyRangedAttack::FireProjectile()
{
    ACharacter* Character = Cast<ACharacter>(CurrentActorInfo->AvatarActor.Get());
    if (!Character || !ProjectileClass) return;

    // Spawn projectile at muzzle location
    FVector MuzzleLocation = Character->GetActorLocation()
        + Character->GetActorForwardVector() * 100.0f
        + FVector(0, 0, 50.0f);
    FRotator MuzzleRotation = Character->GetActorForwardVector().Rotation();

    FActorSpawnParameters SpawnParams;
    SpawnParams.Owner = Character;
    SpawnParams.Instigator = Character;
    SpawnParams.SpawnCollisionHandlingOverride =
        ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

    AActor* Projectile = Character->GetWorld()->SpawnActor<AActor>(
        ProjectileClass, MuzzleLocation, MuzzleRotation, SpawnParams);
}
```

```cpp
// BTTask_ActivateAbilityByTag.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Tasks/BTTask_BlackboardBase.h"
#include "GameplayTagContainer.h"
#include "BTTask_ActivateAbilityByTag.generated.h"

/**
 * BT Task that activates a GameplayAbility by tag on the AI character.
 * Uses TryActivateAbilitiesByTag, which automatically handles
 * cooldown checking, cost checking, and blocking tag validation.
 */
UCLASS()
class UBTTask_ActivateAbilityByTag : public UBTTask_BlackboardBase
{
    GENERATED_BODY()

public:
    UBTTask_ActivateAbilityByTag();

    /** Tag to match against the ability's AbilityTags */
    UPROPERTY(EditAnywhere, Category = "Ability")
    FGameplayTag AbilityTag;

    /** If true, wait for ability to end before completing task */
    UPROPERTY(EditAnywhere, Category = "Ability")
    bool bWaitForAbilityCompletion = true;

protected:
    virtual EBTNodeResult::Type ExecuteTask(
        UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) override;
    virtual EBTNodeResult::Type AbortTask(
        UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) override;
    virtual void TickTask(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;
    virtual uint16 GetInstanceMemorySize() const override;
    virtual FString GetStaticDescription() const override;
};

struct FBTTask_ActivateAbilityByTagMemory
{
    /** Handle of the ability we're waiting on */
    FGameplayAbilitySpecHandle ActiveAbilityHandle;

    /** Cached ASC pointer (valid for lifetime of the task) */
    TWeakObjectPtr<UAbilitySystemComponent> CachedASC;

    /** Whether we've registered the ability end delegate */
    bool bDelegateRegistered;

    /** Whether the ability has completed */
    bool bAbilityComplete;

    /** Whether the ability succeeded */
    bool bAbilitySucceeded;
};

// Required for BT node instance memory
template<>
struct TIsPODType<FBTTask_ActivateAbilityByTagMemory>
{
    enum { Value = false };
};
```

```cpp
// BTTask_ActivateAbilityByTag.cpp
#include "BTTask_ActivateAbilityByTag.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemInterface.h"

UBTTask_ActivateAbilityByTag::UBTTask_ActivateAbilityByTag()
{
    NodeName = TEXT("Activate Ability By Tag");
    bCreateNodeInstance = false;
}

uint16 UBTTask_ActivateAbilityByTag::GetInstanceMemorySize() const
{
    return sizeof(FBTTask_ActivateAbilityByTagMemory);
}

FString UBTTask_ActivateAbilityByTag::GetStaticDescription() const
{
    return FString::Printf(TEXT("%s: '%s' %s"),
        *Super::GetStaticDescription(),
        *AbilityTag.ToString(),
        bWaitForAbilityCompletion ? TEXT("(Wait for completion)") : TEXT("(Fire and forget)"));
}

EBTNodeResult::Type UBTTask_ActivateAbilityByTag::ExecuteTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    FBTTask_ActivateAbilityByTagMemory* MyMemory =
        reinterpret_cast<FBTTask_ActivateAbilityByTagMemory*>(NodeMemory);

    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return EBTNodeResult::Failed;

    APawn* AIPawn = AIController->GetPawn();
    if (!AIPawn) return EBTNodeResult::Failed;

    // Get ASC through the IAbilitySystemInterface
    IAbilitySystemInterface* GASInterface = Cast<IAbilitySystemInterface>(AIPawn);
    if (!GASInterface) return EBTNodeResult::Failed;

    UAbilitySystemComponent* ASC = GASInterface->GetAbilitySystemComponent();
    if (!ASC) return EBTNodeResult::Failed;

    MyMemory->CachedASC = ASC;
    MyMemory->bDelegateRegistered = false;
    MyMemory->bAbilityComplete = false;
    MyMemory->bAbilitySucceeded = false;

    // Build a tag container from the single tag
    FGameplayTagContainer TagContainer;
    TagContainer.AddTag(AbilityTag);

    // Try to activate any granted ability matching this tag
    // This handles: cooldown check, cost check, blocking tag check
    bool bSuccess = ASC->TryActivateAbilitiesByTag(TagContainer);

    if (!bSuccess)
    {
        // Activation failed — ability may be on cooldown, blocked, or not granted
        return EBTNodeResult::Failed;
    }

    if (!bWaitForAbilityCompletion)
    {
        // Fire-and-forget mode — task succeeds immediately
        return EBTNodeResult::Succeeded;
    }

    // Wait-for-completion mode — we need to listen for ability end
    // Register a delegate for the next ability ended callback
    // (simplified: in practice, you'd subscribe to AbilityEndedCallbacks)
    ASC->OnAbilityEnded.AddUObject(this, &UBTTask_ActivateAbilityByTag::OnAbilityEnded);
    MyMemory->bDelegateRegistered = true;

    return EBTNodeResult::InProgress;
}

void UBTTask_ActivateAbilityByTag::OnAbilityEnded(
    const FAbilityEndedData& EndedData)
{
    // This is called when any ability ends — we need to check if it's "ours"
    // We use the ability spec's AbilityTags to match
    const UGameplayAbility* EndedAbility = EndedData.AbilityThatEnded;
    if (EndedAbility && EndedAbility->AbilityTags.HasTag(AbilityTag))
    {
        // Found our ability — it completed
        // Signal completion to the TickTask (stored in node memory)
        // In a real implementation, you'd store a handle and compare here
    }
}

void UBTTask_ActivateAbilityByTag::TickTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds)
{
    FBTTask_ActivateAbilityByTagMemory* MyMemory =
        reinterpret_cast<FBTTask_ActivateAbilityByTagMemory*>(NodeMemory);

    if (MyMemory->bAbilityComplete)
    {
        FinishLatentTask(OwnerComp, MyMemory->bAbilitySucceeded
            ? EBTNodeResult::Succeeded : EBTNodeResult::Failed);
    }
}

EBTNodeResult::Type UBTTask_ActivateAbilityByTag::AbortTask(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    FBTTask_ActivateAbilityByTagMemory* MyMemory =
        reinterpret_cast<FBTTask_ActivateAbilityByTagMemory*>(NodeMemory);

    // Cancel the ability if it's still running
    if (MyMemory->CachedASC.IsValid() && MyMemory->ActiveAbilityHandle.IsValid())
    {
        MyMemory->CachedASC->CancelAbilityHandle(MyMemory->ActiveAbilityHandle);
    }

    if (MyMemory->bDelegateRegistered && MyMemory->CachedASC.IsValid())
    {
        MyMemory->CachedASC->OnAbilityEnded.RemoveAll(this);
    }

    return EBTNodeResult::Aborted;
}
```

```cpp
// BTService_UpdateGASValues.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Services/BTService_BlackboardBase.h"
#include "BTService_UpdateGASValues.generated.h"

/**
 * BT Service that reads GAS attributes and tag states
 * and writes them to the Blackboard for BT conditions.
 */
UCLASS()
class UBTService_UpdateGASValues : public UBTService_BlackboardBase
{
    GENERATED_BODY()

public:
    UBTService_UpdateGASValues();

protected:
    virtual void TickNode(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory, float DeltaSeconds) override;

    virtual FString GetStaticDescription() const override;

public:
    // --- Blackboard key selectors ---

    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector HealthKey;

    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector MaxHealthKey;

    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector StaminaKey;

    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector AmmoKey;

    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector IsStunnedKey;

    UPROPERTY(EditAnywhere, Category = "Blackboard")
    FBlackboardKeySelector IsDeadKey;

    // --- Tags to check ---

    UPROPERTY(EditAnywhere, Category = "Tags")
    FGameplayTag StunnedTag;

    UPROPERTY(EditAnywhere, Category = "Tags")
    FGameplayTag DeadTag;
};
```

```cpp
// BTService_UpdateGASValues.cpp
#include "BTService_UpdateGASValues.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemInterface.h"
#include "EnemyAttributeSet.h"

UBTService_UpdateGASValues::UBTService_UpdateGASValues()
{
    NodeName = TEXT("Update GAS Values");

    // Default update interval: 0.25s — fast enough for responsive BT decisions
    Interval = 0.25f;
    RandomDeviation = 0.05f; // Stagger updates across AI instances

    // Set BB key type filters
    HealthKey.AddFloatFilter(this, GET_MEMBER_NAME_CHECKED(
        UBTService_UpdateGASValues, HealthKey));
    MaxHealthKey.AddFloatFilter(this, GET_MEMBER_NAME_CHECKED(
        UBTService_UpdateGASValues, MaxHealthKey));
    StaminaKey.AddFloatFilter(this, GET_MEMBER_NAME_CHECKED(
        UBTService_UpdateGASValues, StaminaKey));
    AmmoKey.AddFloatFilter(this, GET_MEMBER_NAME_CHECKED(
        UBTService_UpdateGASValues, AmmoKey));
    IsStunnedKey.AddBoolFilter(this, GET_MEMBER_NAME_CHECKED(
        UBTService_UpdateGASValues, IsStunnedKey));
    IsDeadKey.AddBoolFilter(this, GET_MEMBER_NAME_CHECKED(
        UBTService_UpdateGASValues, IsDeadKey));

    // Default tag values
    StunnedTag = FGameplayTag::RequestGameplayTag("State.Stunned");
    DeadTag = FGameplayTag::RequestGameplayTag("State.Dead");
}

void UBTService_UpdateGASValues::TickNode(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory, float DeltaSeconds)
{
    Super::TickNode(OwnerComp, NodeMemory, DeltaSeconds);

    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return;

    APawn* AIPawn = AIController->GetPawn();
    if (!AIPawn) return;

    IAbilitySystemInterface* GASInterface = Cast<IAbilitySystemInterface>(AIPawn);
    if (!GASInterface) return;

    UAbilitySystemComponent* ASC = GASInterface->GetAbilitySystemComponent();
    if (!ASC) return;

    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (!BB) return;

    // Read attribute values from the AttributeSet
    float Health = ASC->GetNumericAttribute(
        UEnemyAttributeSet::GetHealthAttribute());
    float MaxHealth = ASC->GetNumericAttribute(
        UEnemyAttributeSet::GetMaxHealthAttribute());
    float Stamina = ASC->GetNumericAttribute(
        UEnemyAttributeSet::GetStaminaAttribute());
    float Ammo = ASC->GetNumericAttribute(
        UEnemyAttributeSet::GetAmmoAttribute());

    // Write to Blackboard
    BB->SetValueAsFloat(HealthKey.SelectedKeyName, Health);
    BB->SetValueAsFloat(MaxHealthKey.SelectedKeyName, MaxHealth);
    BB->SetValueAsFloat(StaminaKey.SelectedKeyName, Stamina);
    BB->SetValueAsFloat(AmmoKey.SelectedKeyName, Ammo);

    // Write tag states to Blackboard (simple bools for Decorator conditions)
    BB->SetValueAsBool(IsStunnedKey.SelectedKeyName,
        ASC->HasMatchingGameplayTag(StunnedTag));
    BB->SetValueAsBool(IsDeadKey.SelectedKeyName,
        ASC->HasMatchingGameplayTag(DeadTag));
}

FString UBTService_UpdateGASValues::GetStaticDescription() const
{
    return FString::Printf(TEXT("Update GAS attrs every %.2fs (+/-%.2fs)"),
        Interval, RandomDeviation);
}
```

### 示例 C: GAS + BT 标签协调——眩晕系统

**目的**：展示从眩晕 GE 应用 → 标签变更 → BT Decorator 响应 → 行为子树动态切换的完整链路。

```cpp
// BTDecorator_HasGameplayTag.h
#pragma once

#include "CoreMinimal.h"
#include "BehaviorTree/Decorators/BTDecorator_BlackboardBase.h"
#include "GameplayTagContainer.h"
#include "BTDecorator_HasGameplayTag.generated.h"

/**
 * Behavior Tree Decorator that checks for the presence (or absence)
 * of a GameplayTag on the AI's AbilitySystemComponent.
 *
 * Supports Observer Abort: when the tag appears or disappears,
 * the decorator can instantly abort the running branch.
 */
UCLASS()
class UBTDecorator_HasGameplayTag : public UBTDecorator_BlackboardBase
{
    GENERATED_BODY()

public:
    UBTDecorator_HasGameplayTag();

protected:
    virtual bool CalculateRawConditionValue(
        UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const override;

    virtual void OnBecomeRelevant(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;
    virtual void OnCeaseRelevant(UBehaviorTreeComponent& OwnerComp,
        uint8* NodeMemory) override;

    virtual FString GetStaticDescription() const override;

#if WITH_EDITOR
    virtual FName GetNodeIconName() const override;
#endif

public:
    /** The tag to check for on the AI's ASC */
    UPROPERTY(EditAnywhere, Category = "Condition")
    FGameplayTag CheckTag;

    /** If true, the condition passes when the tag is present; if false, when absent */
    UPROPERTY(EditAnywhere, Category = "Condition")
    bool bCheckForPresence = true;

    /** Which abort modes to enable for Observer Abort */
    UPROPERTY(EditAnywhere, Category = "FlowControl")
    EBTFlowAbortMode FlowAbortModeSetting = EBTFlowAbortMode::Both;

private:
    /** Register as a tag change observer on ASC */
    void RegisterTagObserver(UBehaviorTreeComponent& OwnerComp) const;

    /** Unregister tag change observer */
    void UnregisterTagObserver(UBehaviorTreeComponent& OwnerComp) const;
};
```

```cpp
// BTDecorator_HasGameplayTag.cpp
#include "BTDecorator_HasGameplayTag.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "AIController.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemInterface.h"
#include "GameplayTagAssetInterface.h"

UBTDecorator_HasGameplayTag::UBTDecorator_HasGameplayTag()
{
    NodeName = TEXT("Has Gameplay Tag");

    // Observer Abort: enable all modes for maximum responsiveness
    bNotifyBecomeRelevant = true;
    bNotifyCeaseRelevant = true;
    FlowAbortMode = EBTFlowAbortMode::Both; // Default to full observer abort

    bAllowAbortNone = false;
    bAllowAbortLowerPri = true;
    bAllowAbortChildNodes = true;
}

bool UBTDecorator_HasGameplayTag::CalculateRawConditionValue(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory) const
{
    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return !bCheckForPresence;

    APawn* AIPawn = AIController->GetPawn();
    if (!AIPawn) return !bCheckForPresence;

    // Try the GAS interface first
    IAbilitySystemInterface* GASInterface = Cast<IAbilitySystemInterface>(AIPawn);
    UAbilitySystemComponent* ASC = GASInterface
        ? GASInterface->GetAbilitySystemComponent() : nullptr;

    if (ASC)
    {
        bool bHasTag = ASC->HasMatchingGameplayTag(CheckTag);
        return bCheckForPresence ? bHasTag : !bHasTag;
    }

    // Fallback: check IGameplayTagAssetInterface (loose tags on Actor)
    IGameplayTagAssetInterface* TagInterface = Cast<IGameplayTagAssetInterface>(AIPawn);
    if (TagInterface)
    {
        bool bHasTag = TagInterface->HasMatchingGameplayTag(CheckTag);
        return bCheckForPresence ? bHasTag : !bHasTag;
    }

    // No tag source found — return the "safe" inverse
    return !bCheckForPresence;
}

void UBTDecorator_HasGameplayTag::OnBecomeRelevant(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    Super::OnBecomeRelevant(OwnerComp, NodeMemory);

    // Register for tag change notifications to enable Observer Abort
    if (FlowAbortMode != EBTFlowAbortMode::None)
    {
        RegisterTagObserver(OwnerComp);
    }
}

void UBTDecorator_HasGameplayTag::OnCeaseRelevant(
    UBehaviorTreeComponent& OwnerComp, uint8* NodeMemory)
{
    Super::OnCeaseRelevant(OwnerComp, NodeMemory);

    if (FlowAbortMode != EBTFlowAbortMode::None)
    {
        UnregisterTagObserver(OwnerComp);
    }
}

void UBTDecorator_HasGameplayTag::RegisterTagObserver(
    UBehaviorTreeComponent& OwnerComp) const
{
    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return;

    APawn* AIPawn = AIController->GetPawn();
    if (!AIPawn) return;

    UAbilitySystemComponent* ASC = AIPawn->FindComponentByClass<UAbilitySystemComponent>();
    if (!ASC) return;

    // Register a delegate that fires when ANY tag changes on this ASC
    // When registered, we request the BT to re-evaluate this decorator
    ASC->RegisterGameplayTagEvent(CheckTag, EGameplayTagEventType::NewOrRemoved)
        .AddUObject(this, &UBTDecorator_HasGameplayTag::OnGameplayTagChanged);
}

void UBTDecorator_HasGameplayTag::UnregisterTagObserver(
    UBehaviorTreeComponent& OwnerComp) const
{
    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return;

    APawn* AIPawn = AIController->GetPawn();
    if (!AIPawn) return;

    UAbilitySystemComponent* ASC = AIPawn->FindComponentByClass<UAbilitySystemComponent>();
    if (!ASC) return;

    // Unregister the tag change delegate
    // In a complete implementation, store the delegate handle for removal
}

FString UBTDecorator_HasGameplayTag::GetStaticDescription() const
{
    return FString::Printf(TEXT("%s: %s Tag '%s' (FlowAbort: %s)"),
        *Super::GetStaticDescription(),
        bCheckForPresence ? TEXT("Has") : TEXT("NOT Has"),
        *CheckTag.ToString(),
        *UEnum::GetValueAsString(FlowAbortMode));
}

#if WITH_EDITOR
FName UBTDecorator_HasGameplayTag::GetNodeIconName() const
{
    return FName("BTEditor.Graph.BTNode.Decorator.Cooldown.Icon");
}
#endif
```

**眩晕 GE 的创建**（以 C++ 代码配置表示，实际在 Blueprint 或 DataTable 中）：

```cpp
// EnemyStunHandler.h — demonstrates how stun GE is applied and how ASC responds
#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "EnemyStunHandler.generated.h"

UCLASS()
class UEnemyStunHandler : public UObject
{
    GENERATED_BODY()

public:
    /** Apply stun for a given duration in seconds */
    UFUNCTION(BlueprintCallable, Category = "AI|Stun")
    static void ApplyStun(AActor* TargetActor, float Duration);

    /** Remove all active stun effects */
    UFUNCTION(BlueprintCallable, Category = "AI|Stun")
    static void RemoveStun(AActor* TargetActor);

    /** Check if an actor is currently stunned */
    UFUNCTION(BlueprintCallable, Category = "AI|Stun")
    static bool IsStunned(AActor* TargetActor);

private:
    static const FGameplayTag StunnedTag;
    static const FGameplayTag InterruptibleTag;
};
```

```cpp
// EnemyStunHandler.cpp
#include "EnemyStunHandler.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemInterface.h"
#include "GameplayEffect.h"

const FGameplayTag UEnemyStunHandler::StunnedTag =
    FGameplayTag::RequestGameplayTag("State.Stunned");
const FGameplayTag UEnemyStunHandler::InterruptibleTag =
    FGameplayTag::RequestGameplayTag("State.Interruptible");

void UEnemyStunHandler::ApplyStun(AActor* TargetActor, float Duration)
{
    if (!TargetActor || !TargetActor->HasAuthority()) return;

    IAbilitySystemInterface* GASInterface = Cast<IAbilitySystemInterface>(TargetActor);
    if (!GASInterface) return;

    UAbilitySystemComponent* ASC = GASInterface->GetAbilitySystemComponent();
    if (!ASC) return;

    // Create a stun GameplayEffect spec
    FGameplayEffectContextHandle Context = ASC->MakeEffectContext();
    Context.AddSourceObject(TargetActor);

    // The GE class is typically defined as a Blueprint subclass;
    // for C++ demonstration, assume it's loaded from a DataAsset or Class reference.
    // GE_Stun configuration (as if defined in its class defaults):
    //   - Duration Policy: Has Duration
    //   - Duration Magnitude: SetByCaller (float, keyed by "Duration")
    //   - Granted Tags: State.Stunned, State.Interruptible (removed)
    //   - RemoveOtherGameplayEffectOnApplication: Remove any GE with tag State.Movement
    //
    // The GE should be set in a UPROPERTY(EditDefaultsOnly) on your game-specific subclass

    // For illustration, here's the equivalent manual approach:
    // Add the Stunned tag directly (GE approach is preferred for full GAS integration)
    ASC->AddLooseGameplayTag(StunnedTag);

    // Remove Interruptible tag (abilities currently running should be canceled)
    ASC->RemoveLooseGameplayTag(InterruptibleTag);

    // Schedule stun removal after Duration
    TargetActor->GetWorldTimerManager().SetTimer(
        // Timer handle would be stored in a member — omitted for brevity
        [ASC]()
        {
            if (ASC)
            {
                ASC->RemoveLooseGameplayTag(StunnedTag);
            }
        },
        Duration, false
    );
}

void UEnemyStunHandler::RemoveStun(AActor* TargetActor)
{
    if (!TargetActor || !TargetActor->HasAuthority()) return;

    IAbilitySystemInterface* GASInterface = Cast<IAbilitySystemInterface>(TargetActor);
    if (!GASInterface) return;

    UAbilitySystemComponent* ASC = GASInterface->GetAbilitySystemComponent();
    if (ASC)
    {
        ASC->RemoveLooseGameplayTag(StunnedTag);
    }
}

bool UEnemyStunHandler::IsStunned(AActor* TargetActor)
{
    if (!TargetActor) return false;

    IAbilitySystemInterface* GASInterface = Cast<IAbilitySystemInterface>(TargetActor);
    if (!GASInterface) return false;

    UAbilitySystemComponent* ASC = GASInterface->GetAbilitySystemComponent();
    if (!ASC) return false;

    return ASC->HasMatchingGameplayTag(StunnedTag);
}
```

**BT 结构（眩晕响应）**——用伪代码表示编辑器中的树结构：

```
Selector (Root)                                   ← Evaluate condition every frame
│
├── Sequence "DeadCheck"                          ← Priority 1: dead = do nothing
│   ├── Decorator: Has Gameplay Tag (State.Dead)
│   │   FlowAbortMode: LowerPriority
│   └── Wait (infinite — AI is dead)
│
├── Sequence "StunnedBehavior"                    ← Priority 2: stunned = passive
│   ├── Decorator: Has Gameplay Tag (State.Stunned)
│   │   FlowAbortMode: Both
│   │   ← When State.Stunned appears:
│   │       LowerPriority abort → interrupts combat/patrol
│   │   ← When State.Stunned disappears:
│   │       Self abort → exits this branch, falls through to combat
│   └── Task: Wait (0.5s loop — AI does nothing while stunned)
│
└── Selector "NormalBehavior"                     ← Priority 3: normal combat
    ├── Sequence "Heal"
    │   ├── Decorator: Blackboard (Health < 30.0f)
    │   ├── Decorator: HAS NOT GameplayTag (Cooldown.Heal)
    │   └── BTTask_ActivateAbilityByTag (Ability.Heal)
    │
    ├── Sequence "Retreat"
    │   ├── Decorator: Blackboard (Health < 50.0f)
    │   ├── Decorator: HAS NOT GameplayTag (Cooldown.Dash)
    │   └── BTTask_ActivateAbilityByTag (Ability.Dash)
    │
    ├── Sequence "RangedAttack"
    │   ├── Decorator: HAS NOT GameplayTag (Cooldown.Attack)
    │   ├── Decorator: Blackboard (Ammo > 0.0f)
    │   ├── Service: BTService_UpdateGASValues (0.25s interval)
    │   └── BTTask_ActivateAbilityByTag (Ability.Attack.Ranged)
    │
    └── Sequence "MeleeAttack"
        ├── Decorator: HAS NOT GameplayTag (Cooldown.Attack)
        └── BTTask_ActivateAbilityByTag (Ability.Attack.Melee)
```

**流程分析**（眩晕发生时的完整事件链）：

```
T=0.000s  玩家攻击命中 AI
          → Damage GE 附带眩晕几率 Modifier → 触发眩晕
          → EnemyStunHandler::ApplyStun(AI, 3.0s)
          → ASC->AddLooseGameplayTag("State.Stunned")

T=0.001s  ASC 的 Tag 变更事件触发
          → UBTDecorator_HasGameplayTag("State.Stunned") 的 Observer 回调
          → 装饰器重新评估：CheckTag 现在存在 → 条件变为 true
          → FlowAbortMode::LowerPriority 触发
          → BT 中断 NormalBehavior 分支（攻击任务被 Abort）
          → BT 从根重新搜索 → 找到 StunnedBehavior 分支

T=0.002s  StunnedBehavior 的 Wait 任务激活
          → AI 停止攻击，播放眩晕动画（通过 Animation Blueprint 读取 State.Stunned tag）
          → BT 每 0.5s 循环 Wait（直到眩晕结束）

T=3.000s  眩晕 Timer 到期
          → ASC->RemoveLooseGameplayTag("State.Stunned")

T=3.001s  ASC 的 Tag 变更事件触发
          → UBTDecorator_HasGameplayTag("State.Stunned") 的 Observer 回调
          → 装饰器重新评估：CheckTag 不再存在 → 条件变为 false
          → FlowAbortMode::Self 触发
          → BT 中断 StunnedBehavior 分支
          → BT 从根重新搜索 → StunnedBehavior 不再满足 → 进入 NormalBehavior
          → AI 恢复正常战斗行为

总响应延迟：< 2 帧（Observer Abort 事件驱动，不等待下一轮 BT 评估）
```

---

## 3. 练习

### 练习 1: 设计 50 敌人合作游戏的网络架构（40min）

你正在开发一个 4 人合作 PvE 游戏（类似于《深岩银河》或《喋血复仇》的规模）。每个关卡中有约 50 个 AI 敌人同时活动，包括 40 个普通敌人和 10 个特殊敌人（有独特 AI 行为）。玩家通过 P2P 或专用服务器连接。

**要求**：画出完整的网络架构图，标注以下内容：

1. **服务器上运行什么**：列出所有在服务器上执行的 AI 系统（BT、Perception、GAS、Pathfinding），说明为什么每个都在服务器。
2. **什么属性被复制**：为每种属性（位置、血量、动画、AI 状态）标注复制频率和可靠性。指出哪些 AI 内部状态**不**被复制，并说明理由。
3. **瓶颈分析**：识别 3 个最可能的网络/CPU 瓶颈，并提出定量缓解方案（例如"如果带宽 > X Mbps，则对 Y 距离外的敌人减少 Z 属性复制"）。
4. **LOD 策略**：设计距离分级的 LOD 表（参考上文 AI LOD + Network LOD 表格），为每个 LOD 级别写出 BT Tick 频率、网络更新频率、复制内容。
5. **特殊情况**：如果玩家使用高射速武器同时命中 20 个敌人，服务器需要处理 20 个伤害 GE 的应用和复制。描述 GAS 如何在这个场景下工作，以及如何避免网络风暴。

**交付物**：一张架构图（可以是 ASCII art 或文字描述）+ 对应以上 5 点的详细书面答案。

### 练习 2: 实现完整的 GAS 驱动 BT（60min）

基于示例 B 和 C 的代码，实现以下系统。可以基于示例代码扩展，也可以从头实现。

**要求**：

1. **创建至少 4 个 GameplayAbilities**：
   - `GA_AI_MeleeAttack`：近距离攻击，消耗 Stamina，有冷却
   - `GA_AI_RangedAttack`：远程攻击，消耗 Ammo + Stamina，有冷却
   - `GA_AI_Dash`：快速位移（向目标或逃离），消耗 Stamina，无伤害，有冷却
   - `GA_AI_Heal`：回复 Health，消耗 Stamina，长冷却

2. **实现完整的 AttributeSet**：`Health`, `MaxHealth`, `Stamina`, `MaxStamina`, `Ammo`，包含 `PreAttributeChange` 的 Clamp 逻辑和 `PostGameplayEffectExecute` 的死亡检测。

3. **实现 BTService_UpdateGASValues**：将 AttributeSet 的值和关键标签状态同步到 Blackboard。

4. **构建 BT 结构**（文字描述即可，不需要 UE 编辑器截图）：
   - 优先级 1：死亡检查（State.Dead → Wait）
   - 优先级 2：眩晕检查（State.Stunned → Wait）
   - 优先级 3：治疗检查（Health < 30% → Heal）
   - 优先级 4：撤退检查（Health < 50% → Dash away）
   - 优先级 5：远程攻击（有 Ammo → RangedAttack）
   - 优先级 6：近战攻击（默认 → MeleeAttack）

5. **解释为什么每个 Decorator 使用特定的 FlowAbortMode**：至少为 3 个不同的 Decorator 写出其选择的 FlowAbortMode 和理由。

**交付物**：头文件和实现文件的完整代码 + BT 结构的文字描述 + FlowAbortMode 选择理由。

### 练习 3（可选）: 近战游戏的客户端 AI 预测（30min）

设计并实现 Level 1 客户端 AI 预测（预感 VFX 层）用于一个快节奏近战游戏。

**要求**：

1. **客户端预测逻辑**：在 `AEnemyCharacter` 的客户端 Tick 中实现 Level 1 预测——检测"敌人在攻击范围内 + 面向本地玩家 + 当前未在播放攻击动画"条件，决定是否显示 telegraph VFX。

2. **Telegraph VFX 管理器**：创建一个 `UTelegraphVFXComponent`，管理 VFX 的显示/隐藏/强度。强度基于距离（越近越明显）。

3. **服务器校正**：当服务器复制攻击动画到达时，无论预测是否准确，立即隐藏 telegraph VFX。预测错误的情况（预测会攻击但没有）不需要额外校正——因为是 Level 1，只涉及 VFX。

4. **性能约束**：预测逻辑的执行频率不应该超过每 0.1s 一次（60fps 下每 6 帧），在 `Tick` 中使用简单的帧计数器实现。

**交付物**：`UTelegraphVFXComponent` 的完整代码 + 集成到 `AEnemyCharacter::Tick` 的代码片段 + 解释为什么 Level 1 预测的性能开销可以忽略不计。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **50 敌人合作游戏网络架构**
>
> **1. 服务器上运行的内容**：
>
> | 系统 | 运行位置 | 原因 |
> |------|---------|------|
> | Behavior Tree | 服务器 Only | BT 做出权威决策（目标选择、攻击时机）——客户端信任服务器。若客户端运行 BT → 作弊（客户端篡改 BT 强制 AI 忽略玩家） |
> | Perception | 服务器 Only | 感知数据（视线射线检测）必须权威——客户端不应决定"AI 是否能看到玩家"。作弊者可通过修改客户端感知半径实现隐身 |
> | GAS (ASC + AttributeSet + GE) | 服务器 Authoritative, 客户端接收副本 | GE 应用只在服务器端产生权威属性变化。客户端 ASC 处于 `OnlyRelevantToOwner` 的预测模式——用于 UI 显示 |
> | Pathfinding | 服务器 Only | 导航网格查询 + 路径规划在服务器执行。客户端只接收最终位置——作弊者无法修改 AI 移动路径 |
>
> **2. 属性复制策略**：
>
> | 属性 | 复制频率 | 可靠性 | 说明 |
> |------|---------|--------|------|
> | Position (Vector) | 15Hz (LOD 0), 5Hz (LOD 1), 1Hz (LOD 2) | Unreliable（最新值覆盖旧值） | 位置最重要——高频更新但丢失一两个包无影响（下一帧覆盖） |
> | Health (Float) | 每次变化 | Reliable | 关键战斗数据——不可丢包。使用 `DOREPLIFETIME_CONDITION(UAIAttributeSet, Health, COND_None)` |
> | Animation State (Enum) | 状态变化时 | Reliable | 频率极低（状态切换不频繁）→ 开销可忽略 |
> | AI 内部状态 (BB values, BT node path) | 不复制 | N/A | BB 值是服务器 BT 的内部计算中间值——客户端不需要。需要显示的状态通过专用渠道发送（如 Alert 状态用 RPC） |
> | GameplayTags (State.Stunned/Dead) | 标签变化时 | Reliable | 通过 GAS 的 Minimal 模式自动同步——GE 复制包含标签变化 |
>
> **3. 瓶颈分析与缓解**：
>
> | 瓶颈 | 定量缓解方案 |
> |------|-------------|
> | 带宽 — 50 敌人 × 15Hz × 24 byte/pos = 18KB/s（单玩家） | 距离 LOD 降频 + `ReplicationGraph` 的 `ActorListFrequencyBuckets`。>50m 用 5Hz，>100m 用 1Hz。启用 `bOnlyRelevantToOwner=false` + 空间相关性裁剪 |
> | CPU — 50 BT tick × LOD 0 @ 0.015ms = 0.75ms（可接受）| 频率 LOD + 事件驱动 Abort。未激活状态的 BT 通过 Observer Abort 等待事件唤醒而不每帧遍历 |
> | GC/Burst — 50 GAS GE 应用开销（AttributeSet 的 Pre/Post 回调）| 使用 `EGameplayEffectReplicationMode::Minimal`（仅复制 GE + Tag，不单独复制 Attribute）。Batch 多个 GE 到同一个 `FActiveGameplayEffectsContainer` 更新周期 |
>
> **4. LOD 策略表**：
>
> | LOD | 距离 | BT Tick | 网络更新 | 复制内容 | 感知频率 |
> |-----|------|---------|---------|---------|---------|
> | 0 | 0-30m | 每帧 | 15Hz Pos + Health + Anim | 全量 | 每帧 |
> | 1 | 30-80m | 每 3 帧 | 5Hz Pos + Health | Position + Health + State Tag | 每 5 帧 |
> | 2 | 80-150m | 每 10 帧 | 1Hz Pos | Position Only | 每 10 帧 |
> | 3 | >150m | 停止（保持最后行为） | 不复制 | 无（休眠） | 停止 |
>
> **5. 高射速武器命中 20 敌人场景**：
>
> GAS 处理流程：每个命中 → 服务器 `UAbilitySystemComponent::ApplyGameplayEffectToTarget` → 创建 `FActiveGameplayEffect` → `AttributeSet::PreAttributeChange` (Clamp) → 修改 `Health` → `PostGameplayEffectExecute` (死亡检测)。
>
> 20 个 GE 应用在单帧内完成——核心开销在 `PostGameplayEffectExecute`（每个 ~0.01ms），总计 < 0.3ms，可接受。**真正的瓶颈是网络复制**：20 个 Health 变化 + 可能的 5 个 Death 标签 → 35 个属性变化。缓解方案：
> - 使用 `FActiveGameplayEffect` 的 batch 复制——一个 replication update 打包所有 GE 变化
> - 死亡 GE 设置 `bReplicateWhileActive = false`（死亡是永久状态，无需持续复制）
> - `ReplicationGraph` 的 `NetCullDistanceSquared` 自动裁剪：对远处玩家，收到的 AI 数量少 → Health 复制量自然降低

> [!tip]- 练习 2 参考答案
> **GAS 驱动 BT 完整实现**
>
> **1. AttributeSet**：
> ```cpp
> // AIAttributeSet.h
> UCLASS()
> class UAIAttributeSet : public UAttributeSet {
>     GENERATED_BODY()
> public:
>     UPROPERTY(ReplicatedUsing=OnRep_Health)
>     FGameplayAttributeData Health;
>     ATTRIBUTE_ACCESSORS(UAIAttributeSet, Health)
>
>     UPROPERTY(ReplicatedUsing=OnRep_MaxHealth)
>     FGameplayAttributeData MaxHealth;
>
>     UPROPERTY(ReplicatedUsing=OnRep_Stamina)
>     FGameplayAttributeData Stamina;
>
>     UPROPERTY(ReplicatedUsing=OnRep_MaxStamina)
>     FGameplayAttributeData MaxStamina;
>
>     UPROPERTY(ReplicatedUsing=OnRep_Ammo)
>     FGameplayAttributeData Ammo;
>
>     virtual void PreAttributeChange(const FGameplayAttribute& Attr, float& NewVal) override {
>         Super::PreAttributeChange(Attr, NewVal);
>         if (Attr == GetHealthAttribute()) NewVal = FMath::Clamp(NewVal, 0, MaxHealth.GetCurrentValue());
>         if (Attr == GetStaminaAttribute()) NewVal = FMath::Clamp(NewVal, 0, MaxStamina.GetCurrentValue());
>     }
>
>     virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override {
>         if (Data.EvaluatedData.Attribute == GetHealthAttribute() && GetHealth() <= 0) {
>             // 触发死亡——应用 Dead Tag
>             Data.Target.GetAbilitySystemComponent()->AddLooseGameplayTag(
>                 FGameplayTag::RequestGameplayTag("State.Dead"));
>         }
>     }
>
>     UFUNCTION() void OnRep_Health(const FGameplayAttributeData& Old) {
>         GAMEPLAYATTRIBUTE_REPNOTIFY(UAIAttributeSet, Health, Old);
>     }
>     // ... OnRep_Stamina, OnRep_Ammo 同理
> };
> ```
>
> **2. 四个 GameplayAbility**：
> ```cpp
> // GA_AI_MeleeAttack — 近距离攻击，消耗 Stamina，有冷却
> // AbilityTags: "Ability.AI.MeleeAttack"
> // CooldownTag: "Ability.Cooldown.MeleeAttack" (Duration=1.0s)
> // Cost: Stamina -= 10 (通过 GE_Cost_Stamina)
> // Effect: GE_Damage_Melee (Damage=25) 应用到 Target
>
> // GA_AI_RangedAttack — 远程攻击，消耗 Ammo + Stamina
> // AbilityTags: "Ability.AI.RangedAttack"
> // ActivationBlockedTags: "State.Stunned", "State.Dead"
> // Cost: Stamina -= 5, Ammo -= 1
> // Cooldown: 1.5s
> // Requires: HasAmmo Tag Check (条件: Ammo > 0 → ASC 添加 "State.HasAmmo" Tag)
>
> // GA_AI_Dash — 快速位移
> // Cost: Stamina -= 20; Cooldown: 3s
> // Effect: GE_Dash (Set MoveSpeed * 3 for 0.3s via GameplayEffect with Duration)
>
> // GA_AI_Heal — 回复 Health
> // Cost: Stamina -= 30; Cooldown: 15s
> // Effect: GE_Heal (Health +40 over 3s via ModifierMagnitude over Duration)
> // ActivationRequiredTags: "State.LowHealth" (仅 HP < 30% 时可激活)
> ```
>
> **3. BTService_UpdateGASValues**：
> ```cpp
> void UBTService_UpdateGASValues::TickNode(UBehaviorTreeComponent& OwnerComp,
>     uint8* NodeMemory, float DeltaSeconds) {
>     AAIController* AICon = OwnerComp.GetAIOwner();
>     UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(
>         AICon->GetPawn());
>     if (!ASC) return;
>
>     UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
>     BB->SetValueAsFloat("Health", ASC->GetNumericAttribute(UAIAttributeSet::GetHealthAttribute()));
>     BB->SetValueAsFloat("HealthPercent",
>         ASC->GetNumericAttribute(UAIAttributeSet::GetHealthAttribute()) /
>         ASC->GetNumericAttribute(UAIAttributeSet::GetMaxHealthAttribute()));
>     BB->SetValueAsFloat("Stamina", ASC->GetNumericAttribute(UAIAttributeSet::GetStaminaAttribute()));
>     BB->SetValueAsBool("HasAmmo",
>         ASC->GetNumericAttribute(UAIAttributeSet::GetAmmoAttribute()) > 0);
>     BB->SetValueAsBool("IsStunned",
>         ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag("State.Stunned")));
> }
> ```
>
> **4. BT 结构**：
> ```
> [Selector] Root
>  │
>  ├── [Sequence] DeadCheck (优先级 1)
>  │    [Decorator] HasGameplayTag: State.Dead (FlowAbortMode: Both)
>  │    [Task] Wait (infinite, 播放死亡布娃娃后 BT 停止)
>  │
>  ├── [Sequence] StunCheck (优先级 2)
>  │    [Decorator] HasGameplayTag: State.Stunned (FlowAbortMode: Both)
>  │    [Task] Wait (duration = StunDuration from GE, 期间所有其他行为被 Abort)
>  │
>  ├── [Sequence] Heal (优先级 3)
>  │    [Decorator] Blackboard: HealthPercent < 0.3 (FlowAbortMode: LowerPriority)
>  │    [Decorator] Cooldown: HealCooldown (15s, FlowAbortMode: None)
>  │    [Task] BTTask_ActivateAbility(GA_AI_Heal)
>  │
>  ├── [Sequence] Retreat (优先级 4)
>  │    [Decorator] Blackboard: HealthPercent < 0.5 (FlowAbortMode: Both)
>  │    [Task] BTTask_ActivateAbility(GA_AI_Dash)  ← Dash away
>  │    [Task] MoveTo (CoverPosition from EQS)
>  │
>  ├── [Sequence] RangedAttack (优先级 5)
>  │    [Decorator] Blackboard: HasAmmo == true (FlowAbortMode: LowerPriority)
>  │    [Decorator] Blackboard: DistToTarget > 500 (FlowAbortMode: Both)
>  │    [Task] BTTask_ActivateAbility(GA_AI_RangedAttack)
>  │
>  └── [Sequence] MeleeAttack (优先级 6 — 默认)
>       [Decorator] Blackboard: DistToTarget < 300 (FlowAbortMode: Both)
>       [Task] BTTask_ActivateAbility(GA_AI_MeleeAttack)
> ```
>
> **5. FlowAbortMode 选择理由**：
>
> | Decorator | FlowAbortMode | 理由 |
> |-----------|--------------|------|
> | State.Dead | Both | 死亡是最高优先级——无论当前在做什么（Lower Priority 子节点 or 自身 Running 的 Action），死亡标签出现时立即中断一切。Both = Self + LowerPriority |
> | State.Stunned | Both | 眩晕同样是全局中断——被眩晕时不能攻击、不能移动、不能治疗。Both 确保任何当前行为被中断 |
> | HealthPercent < 0.3 (Heal) | LowerPriority Only | 如果已经在治疗中（Self Running），不需要 Abort 自己——继续完成当前治疗。但如果正在攻击/追击（Lower Priority），需要 Abort 切换到治疗 |
> | HasAmmo (RangedAttack) | LowerPriority Only | 弹药用尽时：如果正在远程攻击（Self）→ 不 Abort（当前攻击应该完成）。如果正在做更低优先级的事 → 阻止进入该分支。注意：实际应用中应使用 `None` 或 `LowerPriority`——弹药在攻击过程中可能归零，但 Abort 当前攻击会让动画不完整 |
> | DistToTarget (MeleeAttack) | Both | 距离变化需要同时影响 Self 和 LowerPriority。目标跑出近战范围时立即 Abort 近战攻击（Self）并切换到追击（通过 Selector 的下一个优先分支） |

> [!tip]- 练习 3 参考答案（可选）
> **Level 1 客户端 AI 预测（Telegraph VFX 层）**
>
> ```cpp
> // UTelegraphVFXComponent.h
> UCLASS(ClassGroup=(AI), meta=(BlueprintSpawnableComponent))
> class UTelegraphVFXComponent : public UActorComponent {
>     GENERATED_BODY()
> public:
>     void ShowTelegraph(float Intensity);  // Intensity 0-1, 0=barely visible, 1=full danger
>     void HideTelegraph();
>     bool IsShowing() const { return bIsShowing; }
>
> private:
>     UPROPERTY() UParticleSystemComponent* VFXComponent;
>     UPROPERTY(EditDefaultsOnly) UParticleSystem* TelegraphVFX;
>     UPROPERTY(EditDefaultsOnly) float MinIntensity = 0.3f;
>     UPROPERTY(EditDefaultsOnly) float MaxIntensity = 1.0f;
>     bool bIsShowing = false;
> };
>
> // UTelegraphVFXComponent.cpp
> void UTelegraphVFXComponent::ShowTelegraph(float Intensity) {
>     if (!VFXComponent) {
>         VFXComponent = UGameplayStatics::SpawnEmitterAttached(TelegraphVFX,
>             GetOwner()->GetRootComponent());
>     }
>     float ClampedIntensity = FMath::Clamp(Intensity, MinIntensity, MaxIntensity);
>     // 通过 Material Parameter 控制透明度/颜色强度
>     VFXComponent->SetFloatParameter("Intensity", ClampedIntensity);
>     VFXComponent->SetVisibility(true);
>     bIsShowing = true;
> }
>
> void UTelegraphVFXComponent::HideTelegraph() {
>     if (VFXComponent) VFXComponent->SetVisibility(false);
>     bIsShowing = false;
> }
> ```
>
> **客户端 Tick 集成**：
> ```cpp
> // AEnemyCharacter.cpp
> void AEnemyCharacter::Tick(float DeltaTime) {
>     Super::Tick(DeltaTime);
>
>     if (!IsLocallyControlled() && GetLocalRole() == ROLE_AutonomousProxy) {
>         // 客户端预测逻辑 —— 每 6 帧执行一次（0.1s @ 60fps）
>         PredictionFrameCounter++;
>         if (PredictionFrameCounter % 6 != 0) return;
>
>         UpdateTelegraphPrediction();
>     }
> }
>
> void AEnemyCharacter::UpdateTelegraphPrediction() {
>     APlayerCharacter* LocalPlayer = GetLocalPlayerCharacter();
>     if (!LocalPlayer) { TelegraphVFX->HideTelegraph(); return; }
>
>     float DistToPlayer = FVector::Dist(GetActorLocation(), LocalPlayer->GetActorLocation());
>     bool bFacingPlayer = IsFacingTarget(LocalPlayer);
>     bool bIsAttacking = GetMesh()->GetAnimInstance()->IsAnyMontagePlaying(); // 当前是否在攻击动画
>
>     // 预测条件：在攻击范围内 + 面朝玩家 + 当前未在播放攻击动画
>     if (DistToPlayer < AttackRange && bFacingPlayer && !bIsAttacking) {
>         float DangerIntensity = 1.0f - (DistToPlayer / AttackRange); // 越近越危险
>         TelegraphVFX->ShowTelegraph(DangerIntensity);
>     } else {
>         TelegraphVFX->HideTelegraph();
>     }
> }
>
> // 服务器校正 —— 当攻击动画通过网络复制到达时
> void AEnemyCharacter::OnRep_AttackMontage() {
>     // 无论预测是否正确，立即隐藏 telegraph VFX
>     // 预测正确 → 玩家看到 VFX → 触发闪避 → 攻击动画出现 → VFX 消失（自然）
>     // 预测错误 → 玩家看到 VFX → 攻击未发生 → VFX 在 0.1s 后自然消失（已足够快）
>     TelegraphVFX->HideTelegraph();
> }
> ```
>
> **为什么 Level 1 预测性能开销可忽略**：
> - 每 0.1s 执行一次（60fps 下每 6 帧）→ 每秒仅 10 次预测检查
> - 每次检查：一次距离计算 + 一次朝向判断（Dot Product）+ 一次 AnimInstance 查询 = < 5μs
> - 10 次 × 5μs = 50μs/s ≈ 帧预算的 0.0003%
> - VFX 自身的渲染开销由 GPU 承担，不影响 CPU AI 预算
> - 无网络开销——VFX 是纯客户端效果，预测结果不同步到服务器
## 4. 扩展阅读

### 官方文档

| 资源 | 说明 |
|------|------|
| [Unreal Engine Networked Multiplayer Overview](https://docs.unrealengine.com/5.3/en-US/networking-overview-for-unreal-engine/) | UE 网络复制系统的完整架构文档。理解 `bReplicates`、`Replicated`、`OnRep`、`RPC`、`Relevancy` 的核心概念。**必读**。 |
| [Gameplay Ability System Documentation](https://docs.unrealengine.com/5.3/en-US/gameplay-ability-system-for-unreal-engine/) | Epic 官方 GAS 文档。覆盖 ASC 设置、AttributeSet、GameplayAbility、GameplayEffect、GameplayTags、网络复制模式。 |
| [Unreal Engine AI Perception System](https://docs.unrealengine.com/5.3/en-US/ai-perception-in-unreal-engine/) | AI Perception 是 AI 的"输入层"，在网络 AI 中完全运行于服务器。理解其与 BT 的集成方式。 |
| [Unreal Engine Replication Graph](https://docs.unrealengine.com/5.3/en-US/replication-graph-in-unreal-engine/) | UReplicationGraph 替代默认相关性系统。对于 50+ AI 的场景，ReplicationGraph 的 `ActorListFrequencyBuckets` 是优化网络带宽的关键工具。 |

### 社区与进阶资源

| 资源 | 说明 |
|------|------|
| [GASDocumentation by tranek](https://github.com/tranek/GASDocumentation) | **GAS 社区圣经**。非官方的 GAS 完整文档，覆盖从基础设置到高级网络模式的一切。包含完整的代码示例和常见陷阱。AI 开发者应该特别关注 "Ability System Component"、"AttributeSet"、"GameplayEffect" 章节。 |
| [Unreal Engine Lyra Sample Game](https://github.com/EpicGames/UnrealEngine/tree/5.3/Samples/Games/Lyra) | Epic 官方的 UE5 多人游戏示例项目。Lyra 的 AI 系统展示了 GAS + BT + 网络的完整生产级集成——尤其是 `BTTask_ActivateAbility` 的实现。**强烈建议阅读 Lyra 的 AI 相关源码**。 |
| [Unreal Engine Multiplayer Network Compendium](https://cedric-neukirchen.net/Downloads/Compendium/UE5_Network_Compendium_by_Cedric_Neukirchen.pdf) | Cedric Neukirchen 的 UE5 网络复制完整手册（PDF）。100+ 页的深度指南，覆盖 Actor 复制、RPC、相关性、带宽优化。适合作为每日参考。 |
| [GDC 2021: Building Scalable AI in Unreal Engine](https://www.gdcvault.com/) | Epic 工程师关于 UE5 AI 系统在大规模场景中的性能优化的演讲。 |
| [High-Level AI in Games with Unreal Engine (Andrzej Krzemieński)](https://www.youtube.com/) | 关于在 UE 中构建复杂 AI 行为的 C++ 实现模式，包括 GAS 集成的实际经验。 |

### 书籍

| 书名 | 章节 | 说明 |
|------|------|------|
| *Multiplayer Game Programming* (Josh Glazer, Sanjay Madhav, 2015) | Chapters 5-7 | 多人游戏编程的经典教材。第 5 章覆盖网络复制模型，第 7 章讨论延迟补偿和预测——对理解 AI 客户端预测至关重要。 |
| *Game AI Pro 3*, Chapter 18: *Networked AI for MMOs* | 全文 | 关于大规模 AI 的网络架构，包括服务器端 AI 实例化、AOI（Area of Interest）管理、分布式 AI 负载均衡。 |
| *Unreal Engine 5 Game Development with C++ Scripting* (Zhenyu George Li, 2023) | Chapter 11: Multiplayer Development | UE5 多人游戏开发实战，包含 GAS 的网络设置和调试。 |

---

## 常见陷阱

### 1. 在客户端 AIController 中运行 Behavior Tree

**症状**：`AIController` 的 `BeginPlay` 中调用 `RunBehaviorTree`，在 Listen Server（兼客户端）测试时一切正常。但部署到专用服务器（Dedicated Server）后，客户端玩家看不到 AI 移动——AI 在服务器位置和客户端预期位置之间抖动。

**根因**：`AAIController::bReplicates` 默认为 `true`（自 UE 5.0 起）。当 `bReplicates = true` 时，AIController 在客户端也会存在一个 proxy——但这个 proxy **没有关联 Pawn** 的 Possess 关系（客户端不会执行 `OnPossess`）。如果 BT 在客户端的 AIController proxy 上也启动运行，你会得到一个在完全孤立环境下做决策的"幽灵 AI"——它修改客户端的 Blackboard，驱动客户端的 Pawn，但服务器一无所知。

**解法**：始终在 `RunBehaviorTree` 前检查 `HasAuthority()`。在 `EnemyAIController` 中设置 `bReplicates = false`（AI Controller 不需要在客户端存在——节省带宽和内存）。参见示例 A 的 `StartBehaviorTreeIfServer()` 方法。

### 2. GAS 属性在客户端不更新——AttributeSet 未正确注册复制

**症状**：服务器上 AI 的 Health 正确变化，但客户端的血条 UI 永远显示 100%。日志中没有 `OnRep_Health` 的调用。

**根因**：GAS 的 AttributeSet 复制依赖两个条件：(1) `GetLifetimeReplicatedProps` 中正确使用 `DOREPLIFETIME_CONDITION_NOTIFY` 宏；(2) ASC 的 `InitAbilityActorInfo` 必须在服务器端调用。缺第一个 → 属性根本不复制。缺第二个 → ASC 不知道谁是 Owner/Avatar → 属性值虽然被修改但不会被标记为 dirty → 复制不触发。

**额外陷阱**：如果使用 `EGameplayEffectReplicationMode::Minimal`（如示例 A 中推荐的 AI 优化模式），只有 GameplayEffect 和 GameplayTag 会被复制——**Attribute 值的独立复制被禁用**。在这种情况下，客户端属性的更新完全依赖 GE 的复制同步，而不是 Attribute 的直接复制。如果 AI 通过非 GE 途径修改了属性值（如直接调用 `SetNumericAttributeBase`），该修改**不会**复制到客户端。确保所有属性修改都通过 GE 完成——这是 GAS 的设计契约。

**解法**：
- 确认 `InitAbilityActorInfo` 在服务器端被调用
- 确认 `GetLifetimeReplicatedProps` 中属性被正确声明
- 如果使用 `Minimal` 模式，确保所有属性修改通过 GE（非直接 setter）
- 客户端调试：使用 `ShowDebug AbilitySystem` 控制台命令查看 ASC 状态

### 3. BT Decorator 的 GameplayTag 检查使用 Polling 而非 Observer

**症状**：AI 被眩晕后，仍然继续攻击了 0.5-1.0 秒才停下。眩晕结束后，AI 又多等了 0.5 秒才恢复战斗。

**根因**：使用 Blackboard-based Decorator 检查眩晕状态（`UBTDecorator_Blackboard` 检查 `IsStunned` bool），但 `BTService_UpdateGASValues` 的更新间隔是 0.5s。眩晕的 GE 应用到 BB 更新之间的延迟就是 AI 的反应延迟。

**正确做法**：如示例 C 所示，使用 `UBTDecorator_HasGameplayTag` 直接检查 ASC 的 GameplayTag，并设置 `FlowAbortMode::Both`。当 GE 应用或移除标签时，ASC 的 `RegisterGameplayTagEvent` 在**同一帧内**触发 Observer 回调，Decorator 立即重新评估 → 触发 abort → BT 在 < 2 帧内响应。

**性能考虑**：Observer Abort 比 Polling 更高效——Decorator 只在标签实际变化时才重新评估，而不是每 0.5s 轮询一次。当场景中有 50 个 AI 时，这意味着每秒减少了 50 × 2 = 100 次不必要的 GameplayTag 查询。

### 4. 客户端预测与 GAS 自带预测冲突

**症状**：实现了自定义的客户端 AI 预测逻辑（如 Level 2 动画预测），同时 AI 通过 GAS 的 `ServerInitiated` Ability 播放动画。有时客户端播放两遍攻击动画（一次来自预测、一次来自 GAS 复制的 PlayMontage），有时动画卡在中间状态。

**根因**：GAS 的 Ability 激活复制到客户端时，`UGameplayAbility` 的 `ActivateAbility` 事件会触发动画播放（通过 `UAbilityTask_PlayMontageAndWait` 等 AbilityTask）。如果你的自定义预测逻辑也在同一时间里触发了动画播放，两个系统竞争对 `UAnimInstance` 的控制。

**解法**：
- Level 1 预测（VFX only）不与 GAS 冲突——VFX 和动画走不同的通道。
- Level 2/3 预测**必须了解 GAS 的状态**：在启动预测动画前，检查客户端 ASC 是否已经有活跃的对应 Ability（通过 `ASC->GetActivatableAbilities()` 或检查相关 GameplayTag）。
- 设置预测动画的 Blend-In 时间为 0.0s、Blend-Out 时间为 0.15s——这样当 GAS 动画到达时可以快速覆盖预测动画而不产生明显的混合伪影。
- **更强的方案**：不要做独立的动画预测——利用 GAS 自身的预测机制。如果 AI 使用 `ServerInitiated` Ability（如示例 B），GAS 已经在内核中支持了"服务器激活 → 客户端接收 → 播放动画"的复制路径。额外的预测层在大多数场景中是过度设计。

### 5. 网络 LOD 切换时的 Blackboard 撕裂

**症状**：玩家快速接近一个远处 AI（从 LOD 2 切换到 LOD 0），AI 被唤醒后，行为混乱了几帧——例如 AI 面向错误方向、使用错误的武器、或播放 T-pose 动画。

**根因**：当 AI 从 LOD 2（BT 暂停、低频率位置复制）切换到 LOD 0（BT 恢复、全频复制）时，存在一个"信息撕裂窗口"：服务器的 BT 已经基于完整感知数据做出了决策（如"目标在北方"），但客户端的 Blackboard 同步还在队列中等待复制。客户端看到的 Blackboard 值是过时的（几秒前的），而 Animation Blueprint 基于这些过时值驱动动画（如面朝上次已知的南方）。

**解法**：
- 在 LOD 切换唤醒时，调用 `FlushNetDormancy()` 强制立即全量复制所有属性，然后等待 1 帧（或使用 `NetUpdateFrequency` 突发）再恢复 BT Tick。这确保了客户端在 BT 做出新决策之前拥有最新的状态快照。
- 关键 Blackboard 值的复制应该使用 Reliable RPC 而不是依赖标准的属性复制周期——尤其是在 LOD 切换场景下。
- 对于动画相关的 Blackboard 值，使用滞后（latched）模式：客户端始终保留"最后知道的服务器值"，直到收到新值。避免在等待新值时回退到默认值（如 Vector::ZeroVector 导致面朝世界原点）。

---

> **下一步**: 完成本教程后，建议复习 [[09-bt-unreal-cpp|Tutorial 09: 行为树在 Unreal Engine 中的实现 (C++)]] 和 [[15-hybrid-architectures|Tutorial 15: 混合架构与 AI 系统设计]] 中与 GAS 相关的部分。对于面试准备，特别注意练习 1（网络架构设计）和练习 2（GAS 驱动 BT）——这两个场景是游戏 AI 面试中的高频网络/GAS 交叉问题。
