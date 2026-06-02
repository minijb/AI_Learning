# 状态同步客户端（Unreal Replication / GAS / Iris）

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [17-延迟补偿](17-lag-compensation.md)

---

## 1. 概念讲解

### 1.1 为什么要学 UE 状态同步的"三重体系"？

在 Unity 教程（第 18 节）中，我们讨论的是 NGO：一个层次分明的、有明确"意见"的框架。但在 Unreal Engine 中，状态同步是一个**跨越 20 年演进的庞杂体系**——它不是一个"框架"，而是三层技术的叠加：

```
┌──────────────────────────────────────────────────────────────┐
│                    你的游戏逻辑层                              │
│          (MyCharacter, MyAbility, MyWeapon, …)               │
├──────────────────────────────────────────────────────────────┤
│                    第三层: Iris (UE5.0+)                      │
│  新复制架构：NetRefHandle, ReplicationState, Fragment, Filter │
│  ★ UE5 默认，但旧系统的 API 仍然可用（兼容层）                   │
├──────────────────────────────────────────────────────────────┤
│                    第二层: Gameplay Ability System (4.x+)     │
│  属性集(AttributeSet), GameplayEffect, GameplayTag,           │
│  Ability预测(PredictionKey), GameplayCue                      │
│  ★ 并非所有 UE 游戏都用 GAS，但面试一定会问                     │
├──────────────────────────────────────────────────────────────┤
│                    第一层: UE Legacy Replication (UE1~)        │
│  UPROPERTY(Replicated), DOREPLIFETIME, ServerRPC, NetMulticastRPC│
│  NetworkRole, Relevancy, NetUpdateFrequency                   │
│  ★ 底层全部依赖这套机制，它是理解一切的起点                     │
└──────────────────────────────────────────────────────────────┘
```

面试中，面试官期望你能**逐层讲清楚**：
- 基础层：`UPROPERTY(Replicated)` 和 `ServerRPC` 在字节流层面是怎么工作的（`FArchive` + `FObjectReplicator` + `FNetBitWriter`）
- CMC 层：为什么 `ACharacter` 的移动能"本地立即响应"（客户端预测 + ServerMove + ClientAdjustment）
- GAS 层：为什么技能能"本地立即释放"（PredictionKey + `FPredictionKey` 机制 + "预测窗口"）
- Iris 层：为什么 UE5 要重写整个复制系统（旧的 `FObjectReplicator` 的瓶颈在哪）

**本篇的目标**：从底层复制机制到顶层 GAS 预测，给你一条完整的知识链。学完后，你可以在面试中从容地说："UE 的网络架构我分层理解，从 `UNetDriver` 到 `FObjectReplicator` 到 Iris 的 `UReplicationBridge`，每一层我都写过代码。"

### 1.2 架构全景图

```
                         ┌─────────────┐
                         │   服务器     │
                         │ (ROLE_Authority) │
                         └──────┬──────┘
                                │
                  ┌─────────────┼─────────────┐
                  │             │             │
            复制属性(Property) RPC(函数调用)  关联性(Relevancy)
                  │             │             │
        ┌─────────┼──────┐      │      ┌──────┴──────┐
        │         │      │      │      │             │
    Cond_None Cond_OwnerOnly …  ServerRpc  NetRelevant  NetNotRelevant
        │         │      │     ClientRpc   │             │
        ▼         ▼      ▼    NetMulticast ▼             ▼
   [FObjectReplicator 将属性编码为比特流]   [UNetDriver 决定发送给哪些连接]
        │                                        │
        └────────────────┬───────────────────────┘
                         ▼
                  ┌──────────────┐
                  │  UNetConnection │
                  │  (每个客户端一个) │
                  └──────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ 客户端 A  │  │ 客户端 B  │  │ 客户端 C  │
    │ROLE_      │  │ROLE_      │  │ROLE_      │
    │Autonomous │  │Simulated  │  │Simulated  │
    │Proxy      │  │Proxy      │  │Proxy      │
    └──────────┘  └──────────┘  └──────────┘
```

**数据流口诀**：

- **属性复制 (Property Replication):**
  - 方向: 服务器 → 客户端
  - 触发: `AActor::GetLifetimeReplicatedProps()` 注册 + 服务器修改值 → `MARK_PROPERTY_DIRTY_FROM_NAME`
  - 客户端接收: `AActor::OnRep_XXX()` 回调

- **ServerRPC:**
  - 方向: 客户端 → 服务器
  - 触发: 客户端调用 `Server_XXX()` 
  - 到达: 服务器在对应的 `AActor` 上执行

- **ClientRPC:**
  - 方向: 服务器 → 指定客户端
  - 触发: 服务器调用 `Client_XXX()`
  - 到达: 拥有该 Actor 的客户端执行

- **NetMulticastRPC:**
  - 方向: 服务器 → 所有客户端
  - 触发: 服务器调用 `Multicast_XXX()`
  - 到达: 所有能看到该 Actor 的客户端执行

- **CMC (Character Movement Component) 移动同步:**
  - 混合: 客户端本地预测（AutonomousProxy 本地立即移动）+ 服务器权威校验（ServerMove RPC）+ 服务器纠正（ClientAdjustment RPC）
  - 其他客户端（SimulatedProxy）：服务器位置 → 插值/平滑 → 渲染

### 1.3 属性复制底层：从 UPROPERTY(Replicated) 到网络字节流

**第一步：注册复制属性**

```cpp
// MyCharacter.h
UPROPERTY(Replicated)
float Health;

UPROPERTY(ReplicatedUsing = OnRep_PlayerName)
FString PlayerName;

UFUNCTION()
void OnRep_PlayerName();
```

**第二步：在 GetLifetimeReplicatedProps 中配置复制条件**

```cpp
// MyCharacter.cpp
void AMyCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    // 无条件复制给所有客户端（默认）
    DOREPLIFETIME(AMyCharacter, Health);

    // 带条件复制
    DOREPLIFETIME_CONDITION(AMyCharacter, PlayerName, COND_OwnerOnly);
    // PlayerName 只同步给拥有这个 Character 的客户端

    DOREPLIFETIME_CONDITION(AMyCharacter, AmmoCount, COND_SkipOwner);
    // AmmoCount 不同步给 Owner（避免本地玩家看到双倍数据）
}
```

**第三步：引擎自动生成复制代码**

`DOREPLIFETIME` 宏展开后，UE 的头文件工具（UHT）会生成一个 `XXX_NetSerialize` 或类似的函数。运行时，`FObjectReplicator` 在每个网络 Tick 中：

1. 遍历该 Actor 的所有注册复制属性
2. 对每个属性，比较"上次发送的值"与"当前值"（shadow state / compare cache）
3. 只有**变化了的属性**才被序列化到 `FNetBitWriter`
4. 序列化使用属性的 `NetSerialize()`（自定义）或 `FArchive` 的默认序列化

```cpp
// 引擎内部伪代码：FObjectReplicator::ReplicateProperties()
for (FRepLayoutCmd& Cmd : RepLayout->Cmds)
{
    // 获取当前值
    const uint8* CurrentValue = Cmd.GetCurrentValue(Actor);
    // 比较 shadow state（上次成功发送的值）
    if (Cmd.ShouldSend(CurrentValue))
    {
        // 写入"属性变化位"（changed = 1）
        Writer.WriteBit(1);
        // 序列化属性值
        Cmd.NetSerialize(Writer, CurrentValue);
        // 更新 shadow state
        Cmd.UpdateShadowState(CurrentValue);
    }
    else
    {
        Writer.WriteBit(0); // 未变化 = 0
    }
}
```

**关键认知**：属性复制是**增量式**的——只有变化才传输，没变化时只占 1 bit。这是 UE 复制效率的基础。

### 1.4 DOREPLIFETIME 条件详解

| 条件 | 含义 | 典型用途 |
|------|------|---------|
| `COND_None` | 无条件复制 | 位置、血量（所有客户端都需要） |
| `COND_OwnerOnly` | 只复制给 Owner | 背包内容、任务进度（其他玩家不需要看到） |
| `COND_SkipOwner` | 跳过 Owner | AmmoCount（Owner 有本地预测值，不需要服务器同步重复） |
| `COND_SimulatedOnly` | 只复制给 SimulatedProxy | 音效/特效触发参数 |
| `COND_AutonomousOnly` | 只复制给 AutonomousProxy | RPC 已经在本地执行过一次后的确认 |
| `COND_InitialOnly` | 只在 Actor 初次复制时发送一次 | 角色名、初始外观配置（之后不再变） |
| `COND_Custom` | 自定义条件函数 | 复杂逻辑（如"只同步给距离<50m的客户端"） |

**COND_SkipOwner 的深意**：

```
场景：射击游戏，本地玩家开枪，子弹减少
┌──────────────────────────────────────┐
│ 本地客户端（AutonomousProxy）          │
│ 1. 按下鼠标 → 立即执行本地逻辑:       │
│    AmmoCount--; (本地预测)            │
│ 2. 同时发送 ServerRPC(开枪)            │
│                                       │
│ 如果 AmmoCount 也通过属性复制同步回来: │
│   → 本地已经减了1，服务器又同步减了1   │
│   → 结果: AmmoCount 减了2 ← BUG!     │
│                                       │
│ 使用 COND_SkipOwner:                  │
│   → 本地预测值不再被服务器同步覆盖     │
│   → 只有由服务器和解时才会纠正         │
└──────────────────────────────────────┘
```

### 1.5 RPC 体系：Server/Client/NetMulticast

UE 的 RPC 通过函数命名前缀约定：

| RPC 类型 | 调用方 | 执行方 | 可靠性 | 典型场景 |
|----------|--------|--------|--------|---------|
| `Server` | 客户端 | 服务器 | 默认 Unreliable | 移动输入、射击请求 |
| `Server` + Reliable | 客户端 | 服务器 | Reliable | 购买物品、释放技能 |
| `Client` | 服务器 | 拥有者客户端 | 默认 Unreliable | 位置纠正 |
| `Client` + Reliable | 服务器 | 拥有者客户端 | Reliable | 任务完成通知 |
| `NetMulticast` | 服务器 | 所有客户端 | 默认 Unreliable | 爆炸特效、脚步声 |
| `NetMulticast` + Reliable | 服务器 | 所有客户端 | Reliable | 游戏结束通知 |

**RPC 声明语法**：

```cpp
// ServerRPC — 客户端调用，服务器执行
UFUNCTION(Server, Reliable)
void ServerFire(FVector_NetQuantize AimTarget);

// 实现时函数名必须加 _Implementation 后缀
void AMyCharacter::ServerFire_Implementation(FVector_NetQuantize AimTarget)
{
    // 在服务器上执行
}

// ClientRPC — 服务器调用，Owner 客户端执行
UFUNCTION(Client, Unreliable)
void ClientAdjustPosition(FVector NewLocation);

// NetMulticastRPC — 服务器调用，所有客户端执行
UFUNCTION(NetMulticast, Unreliable)
void MulticastPlayFireEffect();
```

**Reliable vs Unreliable 决策树**：

```
这个 RPC 如果丢了，游戏逻辑会出错吗？
        │
    ┌───┴───┐
    │ 是    │ 否
    ▼       ▼
 Reliable  Unreliable
      如果这个 RPC 高频发送（>10Hz）
      且丢了无关紧要（下一帧会覆盖）？
          │
      ┌───┴───┐
      │ 是    │ 否
      ▼       ▼
  Unreliable Reliable
  (节省带宽，   (虽然高频但每帧都关键)
   避免可靠层
   重传队列爆炸)
```

**关键陷阱**：Reliable RPC 有**顺序保证**（同一 channel 内），但 Unreliable RPC 没有。如果你混用 Reliable 和 Unreliable 传输同一 Actor 的状态更新，可能导致"旧状态在可靠通道上延时到达后覆盖新状态"。

### 1.6 网络角色（NetworkRole）深度解析

每个网络 Actor 在不同端有不同的"角色"身份：

| 角色 | 所在端 | 有输入权限？ | 有逻辑权限？ | 典型行为 |
|------|--------|-------------|-------------|---------|
| `ROLE_Authority` | 服务器 | 否（服务器直接用代码控制） | 是（唯一权威） | 执行所有逻辑，复制属性，校验输入 |
| `ROLE_AutonomousProxy` | 客户端（Owner） | 是 | 否 | 本地预测移动 + 技能，发送 ServerRPC |
| `ROLE_SimulatedProxy` | 客户端（非 Owner） | 否 | 否 | 接收服务器位置，插值渲染 |
| `ROLE_None` | 尚未初始化 | 否 | 否 | Actor 刚生成，角色未确定 |

**角色判断的正确姿势**：

```cpp
// ✅ 正确——通过 Role 判断
if (GetLocalRole() == ROLE_Authority)
{
    // 我在服务器上
}

// ✅ 对于 Pawn/Character，UE 提供了便捷方法
if (IsLocallyControlled())  // AutonomousProxy → true; 等价于 Role==ROLE_AutonomousProxy
{
    // 我是这个客户端控制的角色
}

// ❌ 常见错误——在客户端直接检查 Authority
if (HasAuthority())  // 客户端永远返回 false
{
    // 这段代码在客户端永远不会执行
}
```

**三种角色在移动同步中的协作**：

```
时间线：玩家按下 W 键 → 向前移动

─────────────────────────────────────────────────────────────► time

AutonomousProxy (本地玩家):
│  读取输入(W键)
│  立即移动角色 (客户端预测)
│  调用 ServerMove(Time, Input, …) → 发送到服务器
│
▼
Server (Authority):
│  收到 ServerMove
│  用相同输入重新模拟移动 (权威计算)
│  比较: 客户端位置 vs 服务器计算位置
│  if (误差 > AcceptableRadius):
│     ClientAdjustPosition(ServerPos) → 纠正客户端
│  复制 Location 属性 → 同步给其他客户端
│
▼
SimulatedProxy (其他玩家):
│  收到复制的 Location
│  插值/平滑 → 渲染
```

### 1.7 Character Movement Component (CMC) 的预测-纠正回路

CMC 是 UE 网络同步的皇冠：它做到了**客户端本地预测 + 服务器权威校验 + 平滑纠正**的全自动闭环。

**ServerMove RPC 的内部流程**：

```cpp
// 每次客户端本地 Tick 时，CMC 调用:
void UCharacterMovementComponent::TickComponent(float DeltaTime, …)
{
    if (Pawn->IsLocallyControlled())
    {
        // 1. 本地执行移动（预测）
        PerformMovement(DeltaTime);
        
        // 2. 构建 ServerMove 参数
        FSavedMove_Character NewMove;
        NewMove.SetMoveFor(this, DeltaTime, …);  // 记录时间戳、加速度、旋转
        
        // 3. 将移动保存到 PendingMove 列表（用于后续和解）
        SavedMoves.push(NewMove);
        
        // 4. 发送 ServerMove RPC（合并多个移动到一个 RPC——合并优化）
        if (ShouldSendServerMove())
        {
            ServerMove(TimeStamp, Acceleration, ClientLoc, CompressedMoveFlags, …);
        }
    }
}
```

**服务端收到 ServerMove 后**：

```cpp
void UCharacterMovementComponent::ServerMove_Implementation(
    float TimeStamp, FVector Accel, FVector ClientLoc, …)
{
    // 1. 使用客户端发来的输入（加速度、旋转）重新模拟移动
    //    这样服务器上的移动路径 = 客户端上的移动路径
    MoveAutonomous(TimeStamp, Accel, …);
    
    // 2. 比较：服务器计算出的位置 vs 客户端声称的位置
    FVector ServerLoc = UpdatedComponent->GetComponentLocation();
    float Error = FVector::Dist(ClientLoc, ServerLoc);
    
    // 3. 如果误差过大 → 发送纠正
    if (Error > MaxPositionError)  // 默认值：客户端预测允许的误差半径
    {
        ClientAdjustPosition(TimeStamp, ServerLoc, ServerVelocity);
    }
    
    // 4. 确认该移动已被处理 → 客户端可以丢弃对应的 SavedMove
}
```

**客户端收到 ClientAdjustPosition（纠正）**：

```cpp
void UCharacterMovementComponent::ClientAdjustPosition_Implementation(
    float TimeStamp, FVector NewLoc, FVector NewVel, …)
{
    // 1. 确认已处理的 SavedMove → 从 SavedMoves 中移除
    AcknowledgeMovePacket(TimeStamp);
    
    // 2. 检查纠正是否必要
    FVector CurrentLoc = UpdatedComponent->GetComponentLocation();
    if (!CurrentLoc.Equals(NewLoc))
    {
        // 3. 回滚到服务器位置
        UpdatedComponent->SetWorldLocation(NewLoc);
        
        // 4. 重放未被确认的 SavedMove（预测回滚重放）
        //    将 SavedMoves 中剩余的移动重新执行一遍
        for (auto& Move : SavedMoves)
        {
            Move->PrepMoveFor(Character);
            Move->SetInitialPosition(Character);
            // 重新执行这个移动
            PerformMovementWithMove(Move);
        }
    }
}
```

**CMC 的设计精髓**：

1. **合并发送**：ServerMove 不是每帧发一次（那样太浪费），而是将多个客户端的 Tick 合并到一个 RPC 中。当前 Tick 未被发送时，数据在 `FSavedMove_Character` 中累积。
2. **确定性重放**：客户端和服务端使用相同的移动代码（`PerformMovement`），确保在相同输入下产生相同输出。
3. **自适应误差**：`MaxPositionError` 不是固定值——网络条件好时收紧，差时放宽。

### 1.8 Gameplay Ability System (GAS) 的网络机制

GAS 是 UE 的状态同步皇冠上的明珠。它的网络设计解决了一个核心矛盾：

> **技能效果应该本地立即生效（好的手感），但最终裁决必须在服务器（反作弊）。**

GAS 通过 **PredictionKey** 机制优雅地解决了这个矛盾。

**PredictionKey 工作流**：

```
客户端按下技能键 ──────────────────────────────────────► 时间

1. 客户端生成唯一的 FPredictionKey (Guid)
2. 客户端调用 TryActivateAbility() 
   → 立即在本地执行技能逻辑 (预测激活)
   → 同时发送 ServerTryActivateAbility(PredictionKey)
   
3. 服务器收到 ServerTryActivateAbility:
   → 用相同的 PredictionKey 执行技能
   → 如果成功: 服务器权威执行 → 同步 GameplayEffect 到所有客户端
   → 如果失败: 服务器发送 ClientActivateAbilityFailed()
      → 客户端收到后，撤销本地预测的所有效果
      
4. 客户端收到服务器确认的 GameplayEffect:
   → 检查 PredictionKey 是否匹配
   → 如果匹配: 本地预测的效果成为权威效果（无缝过渡）
   → 如果不匹配: 撤销本地预测，应用服务器效果
```

**为什么预测"无缝"？**

因为 PredictionKey 匹配时，客户端早已在本地执行了相同的 `UGameplayEffect` 修改——服务器同步过来的 GE 和本地预测的 GE 是**同一个效果**。引擎会将本地预测版本标记为"已确认"，不需要重新应用。

**GameplayEffect 同步的三种模式**：

| 同步模式 | 何时用 | 网络开销 |
|---------|--------|---------|
| `Local Predicted` | 本地玩家的技能（立即生效） | 小（只有失败时才撤销） |
| `Server Only` | AI 的 BUFF、全局效果 | 中（服务器同步 GE 到客户端） |
| `Server Initiated` | 环境伤害、服务端主动施加的效果 | 中（同 Server Only） |

**GameplayTag 复制**：

```cpp
// GameplayTag 本身不需要 UPROPERTY(Replicated)——它们通过 GAS 的专用系统同步
// 但 Tag 的 容器(UAbilitySystemComponent) 需要复制

// 在 ASC 中注册要复制的 Tag
AbilitySystemComponent->SetReplicatedGameplayTagCount(
    FGameplayTag::RequestGameplayTag("State.Debuff.Stun"), ReplicatedTagCount, 1);
```

GAS 内部使用 `FGameplayTagContainer` 的紧凑序列化：只同步变化的 Tag（增量），而非整个容器。

**GameplayCue 的两种路由**：

```
GameplayCue 触发 (如: 火焰特效、音效)

    ├── GameplayCue.Local (本地立即播放)
    │   └── AddGameplayCue_Local(Tag, Parameters)
    │       使用场景: 本地预测的技能效果
    │       → 客户端立即播放，不等服务器确认
    │
    └── GameplayCue.Replicated (服务器触发，同步到客户端)
        └── AddGameplayCue_Replicated(Tag, Parameters)
            使用场景: 其他玩家的技能、服务器权威效果
            → 服务器添加 Cue → 通过属性复制同步 → 客户端播放
```

### 1.9 UE5 Iris：下一代复制系统

UE5 引入 Iris 重写了整个复制层。理解 Iris 不仅是面试的加分项——它代表了 Epic 对"未来网络复制"的愿景。

**旧系统 (Legacy) 的瓶颈**：

```
旧复制系统的问题:
┌─────────────────────────────────────────────────┐
│ 1. 所有 Actor 通过同一个路径复制                  │
│    UWorld → UNetDriver → 遍历所有 Actor            │
│    → FObjectReplicator → 检查每个属性              │
│    没有优先级系统，线性遍历 → O(N)                  │
│                                                   │
│ 2. FObjectReplicator 绑定在 Actor 生命周期上       │
│    无法为不同连接定制不同的复制数据                  │
│                                                   │
│ 3. Shadow State 存储在 Actor 的 CDO 中            │
│    内存布局不友好，缓存命中率低                      │
│                                                   │
│ 4. 依赖 UE 反射系统 (UProperty)                   │
│    无法为非 UObject 类型做增量复制                   │
└─────────────────────────────────────────────────┘
```

**Iris 的架构革新**：

```
┌─────────────────────────────────────────────────────────────┐
│                    UReplicationSystem                        │
│  (替代 UNetDriver 的复制管理部分)                             │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ NetRefHandle │  │Replication   │  │ReplicationFilter  │  │
│  │ 全局唯一句柄  │  │  Bridge      │  │  (Filtering)     │  │
│  │ (替代NetGUID)│  │  连接游戏层   │  │  空间网格/距离   │  │
│  └─────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              ReplicationState (每个连接一份)            │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │  │
│  │  │ MemberState  │ │ ConditionState│ │ ChangeMask   │  │  │
│  │  │  描述一个属性  │ │  复制条件     │ │  增量变化位图 │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Prioritization (优先级调度)                   │  │
│  │  不再线性遍历 → 按优先级 + 带宽预算调度                  │  │
│  │  高频重要对象优先发送，低优先级对象降频/延迟             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Iris 的核心概念**：

1. **NetRefHandle**：替代旧的 `FNetworkGUID`。全局唯一的 64-bit 句柄，不依赖 Actor 指针。支持静态和动态两种分配——静态句柄用于关卡内置对象，动态句柄用于运行时生成的对象。

2. **ReplicationState**：描述"什么东西需要复制"。使用 `FReplicationStateDescriptor` 定义成员（MemberDescriptors），每个成员有自己的 change mask（变化位）。Iris 用这个来实现属性级别的增量复制——比旧的"遍历所有属性比较"高效得多。

3. **ReplicationFragment**：连接 ReplicationState 和游戏对象的"适配器"。游戏代码实现 Fragment，告诉 Iris 如何读取/写入状态。这使得 Iris 不依赖 UObject 反射——理论上可以复制任何 C++ 对象。

4. **ReplicationBridge**：游戏层和 Iris 核心之间的桥梁。`UEngineReplicationBridge` 是 UE 内置的桥接实现，处理 Actor/Component 的创建和销毁。你可以在 `UReplicationBridge` 子类中自定义"什么条件触发对象开始/停止复制"。

5. **Filtering & Prioritization**：
   - **Filtering**（筛选）：决定"这个对象是否复制给这个连接"。Iris 内置了空间网格过滤器（Spatial Filter）、连接过滤器和自定义过滤器。
   - **Prioritization**（优先级）：决定"在有限带宽下，先发送哪个对象"。Iris 支持静态优先级（距离越近→优先级越高）和动态优先级（最近受过伤害的敌人→高优先级）。

**Iris 对前端开发的改变**：

| 方面 | 旧系统 | Iris |
|------|--------|------|
| 属性定义 | `UPROPERTY(Replicated)` | 同旧系统（兼容）或 `FReplicationStateDescriptor` |
| 注册复制属性 | `GetLifetimeReplicatedProps` | 同旧系统（兼容层），或在 Fragment 中注册 |
| 复制条件 | `COND_OwnerOnly` 等 | `ReplicationCondition`（更灵活的组合） |
| 带宽管理 | `NetUpdateFrequency` 单一频率 | 优先级调度 + 带宽预算 |
| 对象筛选 | `IsNetRelevantFor()` | `UReplicationFilter` 子类 + 空间网格 |
| 优先级 | `GetNetPriority()` 返回值 | `SetPriority()` + 调度器 |

**实际影响**：

- Iris 下你**仍然可以使用** `UPROPERTY(Replicated)` + `DOREPLIFETIME`——Iris 提供了兼容层。
- 但如果你**启用 Iris（默认在 UE5 中）**，底层的复制逻辑已经是 Iris 在跑了。你会注意到带宽利用更高效（大世界对象 >1000 时尤其明显）。
- 未来的方向是**逐步迁移到 Iris 原生 API**：用 `FReplicationStateDescriptor` 定义状态，用 `UReplicationFragment` 绑定到游戏对象。

### 1.10 UE 网络调试工具地图

```
调试方向         工具                         控制台命令
────────────────────────────────────────────────────────────
属性复制验证     net.KnownMissingDependencies  列出缺失复制依赖的 Actor
                LogNetPackageMap              包映射日志
                LogRep                        复制详细日志
                
带宽/频率分析    stat net                      实时网络统计
                stat NetUpdateFrequency       对象更新频率
                stat NetRelevancy             关联性计算耗时
                
RPC 追踪        LogNetTraffic                 网络流量日志
                LogNetRPCCall                 每个 RPC 调用记录
                
CMC 调试        p.VisualizeMovement           可视化移动路径
                net.PktLag                    模拟网络延迟
                net.PktLagVariance            模拟延迟抖动
                
GAS 调试        showdebug abilitysystem       GAS 状态面板
                AbilitySystem.Debug.NextCategory 调试分类
                
Iris 调试       Iris.LogReplication           复制日志
                Iris.DebugDraw                可视化复制范围
                
综合性能分析    Network Profiler              Unreal Insights 插件
                net.SimulateLatency           仿真网络条件
```

---

## 2. 代码示例

> **环境要求**：Unreal Engine 5.x，启用 Gameplay Ability System 插件。以下代码为完整的 `.h`/`.cpp` 对，可直接添加到 UE 项目中编译。

### 2.0 项目设置

```ini
; DefaultEngine.ini — 启用 GAS 和 Iris
[/Script/Engine.Engine]
; Iris 是 UE5 默认复制系统，确认已启用
+EnabledPlugins=Iris

[/Script/GameplayAbilities.AbilitySystemGlobals]
; 使用 GameplayCue 需要设置 GlobalGameplayCueManager
GlobalGameplayCueManagerClass=/Script/GameplayAbilities.GameplayCueManager

; 启用预测
AllowGlobalPrediction=true

[/Script/OnlineSubsystemUtils.IpNetDriver]
; 模拟网络延迟（仅开发环境）
; NetServerMaxTickRate=30
; MaxClientRate=60000
; MaxInternetClientRate=60000
```

### 2.1 MyCharacter.h — 复制属性 + CMC 集成

```cpp
// ============================================================
// MyCharacter.h
// 状态同步客户端核心：用 UE 复制系统同步角色状态
// 继承 ACharacter 自动获得 CMC 的预测-纠正回路
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AbilitySystemInterface.h"
#include "MyCharacter.generated.h"

class UMyAbilitySystemComponent;
class UMyAttributeSet;

/**
 * 网络角色：
 * - 服务器: ROLE_Authority — 执行所有逻辑，同步状态
 * - 本地客户端: ROLE_AutonomousProxy — 本地预测移动 + 技能
 * - 其他客户端: ROLE_SimulatedProxy — 插值渲染
 */
UCLASS()
class NETWORKTUTORIAL_API AMyCharacter : public ACharacter, public IAbilitySystemInterface
{
    GENERATED_BODY()

public:
    AMyCharacter(const FObjectInitializer& ObjectInitializer);

    // ── IAbilitySystemInterface ──────────────────────────────
    virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;

    // ── 复制属性 ──────────────────────────────────────────────
    // 血量（无条件复制 — 所有客户端都需要看到）
    UPROPERTY(ReplicatedUsing = OnRep_Health, BlueprintReadOnly, Category = "Combat")
    float Health;

    // 护盾值（只同步给 Owner — 其他玩家不需要知道精确数值）
    UPROPERTY(ReplicatedUsing = OnRep_Shield, BlueprintReadOnly, Category = "Combat")
    float Shield;

    // 玩家名称（只在初始化时复制一次 — Cond_InitialOnly）
    UPROPERTY(Replicated, BlueprintReadOnly, Category = "Identity")
    FString PlayerName;

    // 弹药数（跳过 Owner — Owner 有本地预测值，无需服务器同步）
    UPROPERTY(Replicated, BlueprintReadOnly, Category = "Combat")
    int32 AmmoCount;

    // 团队ID（自定义条件 — 只同步给同队队友）
    UPROPERTY(Replicated, BlueprintReadOnly, Category = "Team")
    int32 TeamId;

    // ── 技能系统组件 ──────────────────────────────────────────
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Abilities")
    UMyAbilitySystemComponent* AbilitySystemComponent;

    UPROPERTY()
    UMyAttributeSet* AttributeSet;

    // ── RPC ───────────────────────────────────────────────────
    // ServerRPC: 客户端调用的射击请求
    UFUNCTION(Server, Reliable)
    void ServerFire(FVector_NetQuantize AimTarget);

    // ServerRPC: 客户端调用的换弹请求（不要求 Owner 才能调用）
    UFUNCTION(Server, Reliable, WithValidation)
    void ServerReload();

    // ClientRPC: 服务器通知 Owner 弹药更新
    UFUNCTION(Client, Reliable)
    void ClientAmmoUpdate(int32 NewAmmo, int32 NewReserve);

    // NetMulticastRPC: 广播开火特效到所有客户端
    UFUNCTION(NetMulticast, Unreliable)
    void MulticastFireEffect(FVector_NetQuantize MuzzleLocation, FRotator AimRotation);

    // ── 网络钩子 ──────────────────────────────────────────────
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    virtual void PossessedBy(AController* NewController) override;   // 服务器
    virtual void OnRep_PlayerState() override;                       // 客户端

protected:
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaTime) override;
    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

    // ── OnRep 回调 ───────────────────────────────────────────
    UFUNCTION()
    void OnRep_Health();

    UFUNCTION()
    void OnRep_Shield();

    // ── 输入处理 ──────────────────────────────────────────────
    void MoveForward(float Value);
    void MoveRight(float Value);
    void OnFirePressed();
    void OnReloadPressed();

private:
    // ── 本地预测弹药管理 ──────────────────────────────────────
    // 本地玩家的 AmmoCount 由本地逻辑控制（预测），
    // 服务器通过 ClientAmmoUpdate 做权威纠正
    int32 LocalAmmoCount;
    int32 LocalReserveAmmo;

    // 检查：是否应该用本地预测值还是服务器权威值
    bool ShouldUseLocalAmmoPrediction() const
    {
        return IsLocallyControlled() && GetLocalRole() == ROLE_AutonomousProxy;
    }
};
```

### 2.2 MyCharacter.cpp — 复制逻辑实现

```cpp
// ============================================================
// MyCharacter.cpp
// ============================================================

#include "MyCharacter.h"
#include "MyAbilitySystemComponent.h"
#include "MyAttributeSet.h"
#include "Net/UnrealNetwork.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/ActorChannel.h"

AMyCharacter::AMyCharacter(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
    , Health(100.0f)
    , Shield(50.0f)
    , AmmoCount(30)
    , LocalAmmoCount(30)
    , LocalReserveAmmo(90)
    , TeamId(0)
{
    // ── CMC 网络配置 ──────────────────────────────────────────
    // 以下设置影响 CMC 的预测-纠正行为

    // 开启客户端预测移动（默认已开启，显式设置以确保）
    GetCharacterMovement()->SetIsReplicated(true);

    // 客户端位置误差容忍度（单位: cm）
    // 值越小→纠正越频繁→网络开销越大→但位置更准确
    // 值越大→纠正越少→看起来更平滑→但可能"穿墙"
    // 推荐: 近战游戏 20-30，射击游戏 10-15
    GetCharacterMovement()->NetworkMaxSmoothUpdateDistance = 40.0f;

    // 频率: 服务器向客户端同步位置的频率
    // 默认 = CharacterMovementComponent 的 NetUpdateFrequency
    // 射击游戏推荐 60-90 Hz
    NetUpdateFrequency = 60.0f;
    // 最低同步频率（带宽紧张时不会低于此值）
    MinNetUpdateFrequency = 20.0f;

    // ── 复制设置 ──────────────────────────────────────────────
    bReplicates = true;
    // 使用子对象复制列表（GAS 的 ASC 和 AttributeSet 需要此项）
    SetReplicateMovement(true);
}

// ══════════════════════════════════════════════════════════════
// 复制属性注册
// ══════════════════════════════════════════════════════════════

void AMyCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    // 无条件复制 — 所有连接的客户端都收到
    DOREPLIFETIME(AMyCharacter, Health);

    // OwnerOnly — 只有拥有此角色的客户端收到（护盾值不暴露给敌人）
    DOREPLIFETIME_CONDITION(AMyCharacter, Shield, COND_OwnerOnly);

    // InitialOnly — 只在第一次复制时发送，之后不再同步
    DOREPLIFETIME_CONDITION(AMyCharacter, PlayerName, COND_InitialOnly);

    // SkipOwner — Owner 有本地预测值，跳过服务器同步
    DOREPLIFETIME_CONDITION(AMyCharacter, AmmoCount, COND_SkipOwner);

    // Custom — 使用自定义条件函数
    // 只同步给同队的队友（团队ID匹配）
    DOREPLIFETIME_CONDITION(AMyCharacter, TeamId, COND_Custom);
}

// 自定义复制条件：TeamId 只同步给同队队友
// 这个函数在服务器端被 UNetDriver 调用，判断是否应该向某个连接复制 TeamId
void AMyCharacter::PreReplication(IRepChangedPropertyTracker& ChangedPropertyTracker)
{
    Super::PreReplication(ChangedPropertyTracker);

    // COND_Custom 的具体逻辑由 DOREPLIFETIME_ACTIVE_OVERRIDE 处理
    // 在 UE5 中推荐用 ReplicationCondition 替代旧 COND_Custom
}

// ══════════════════════════════════════════════════════════════
// IAbilitySystemInterface
// ══════════════════════════════════════════════════════════════

UAbilitySystemComponent* AMyCharacter::GetAbilitySystemComponent() const
{
    return AbilitySystemComponent;
}

// ══════════════════════════════════════════════════════════════
// 初始化
// ══════════════════════════════════════════════════════════════

void AMyCharacter::BeginPlay()
{
    Super::BeginPlay();

    // 本地预测的弹药初始值 = 服务器权威的初始值
    LocalAmmoCount = AmmoCount;
}

void AMyCharacter::PossessedBy(AController* NewController)
{
    Super::PossessedBy(NewController);

    // 服务器端初始化 GAS
    if (AbilitySystemComponent)
    {
        AbilitySystemComponent->InitAbilityActorInfo(this, this);
    }
}

void AMyCharacter::OnRep_PlayerState()
{
    Super::OnRep_PlayerState();

    // 客户端初始化 GAS（PlayerState 复制到达后）
    if (AbilitySystemComponent)
    {
        AbilitySystemComponent->InitAbilityActorInfo(this, this);
    }
}

// ══════════════════════════════════════════════════════════════
// 输入处理
// ══════════════════════════════════════════════════════════════

void AMyCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
    Super::SetupPlayerInputComponent(PlayerInputComponent);

    // 移动输入绑定
    PlayerInputComponent->BindAxis("MoveForward", this, &AMyCharacter::MoveForward);
    PlayerInputComponent->BindAxis("MoveRight", this, &AMyCharacter::MoveRight);

    // 动作输入绑定
    PlayerInputComponent->BindAction("Fire", IE_Pressed, this, &AMyCharacter::OnFirePressed);
    PlayerInputComponent->BindAction("Reload", IE_Pressed, this, &AMyCharacter::OnReloadPressed);
}

void AMyCharacter::MoveForward(float Value)
{
    if (Value != 0.0f)
    {
        AddMovementInput(GetActorForwardVector(), Value);
    }
}

void AMyCharacter::MoveRight(float Value)
{
    if (Value != 0.0f)
    {
        AddMovementInput(GetActorRightVector(), Value);
    }
}

// ══════════════════════════════════════════════════════════════
// Tick
// ══════════════════════════════════════════════════════════════

void AMyCharacter::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

    // ── 调试：可视化网络角色 ──────────────────────────────────
    if (GEngine && GetWorld()->GetNetMode() != NM_Standalone)
    {
        FString RoleStr;
        switch (GetLocalRole())
        {
        case ROLE_Authority:        RoleStr = TEXT("Authority"); break;
        case ROLE_AutonomousProxy:  RoleStr = TEXT("AutonomousProxy"); break;
        case ROLE_SimulatedProxy:   RoleStr = TEXT("SimulatedProxy"); break;
        default:                    RoleStr = TEXT("None"); break;
        }
        // 调试用：在角色头顶显示网络角色（仅在开发构建中启用）
        // GEngine->AddOnScreenDebugMessage(GetUniqueID(), 0.0f, FColor::Cyan,
        //     FString::Printf(TEXT("Role: %s | NetMode: %d"), *RoleStr, (int32)GetWorld()->GetNetMode()));
    }
}

// ══════════════════════════════════════════════════════════════
// RPC 实现
// ══════════════════════════════════════════════════════════════

// ── ServerFire: 客户端请求射击 ──────────────────────────────
// 客户端调用，服务端执行
void AMyCharacter::ServerFire_Implementation(FVector_NetQuantize AimTarget)
{
    // ★ 这里在服务器上执行 ★
    // 1. 验证：客户端是否有足够的弹药
    if (AmmoCount <= 0)
    {
        UE_LOG(LogTemp, Warning, TEXT("ServerFire: Client %s attempted to fire with no ammo!"),
            *GetName());
        return;  // 拒绝这个射击请求
    }

    // 2. 权威逻辑：消耗弹药
    AmmoCount--;
    // 属性变化会自动触发复制（因为 AmmoCount 是 Replicated 属性，条件为 COND_SkipOwner）

    // 3. 执行射击逻辑（射线检测、伤害计算等）
    // ...（此处省略具体实现）

    // 4. 通过 ClientRPC 通知 Owner 弹药已更新
    ClientAmmoUpdate(AmmoCount, LocalReserveAmmo);

    // 5. 通过 NetMulticastRPC 广播开火特效
    FVector MuzzleLocation = GetActorLocation() + GetActorForwardVector() * 50.0f;
    MulticastFireEffect(MuzzleLocation, GetActorRotation());
}

// ── ServerReload: 客户端请求换弹 ─────────────────────────────
// 使用 WithValidation 做客户端校验
bool AMyCharacter::ServerReload_Validate()
{
    // _Validate 在服务器收到 RPC 后、执行 _Implementation 前调用
    // 如果返回 false，RPC 被丢弃（客户端被强制断开连接）
    // 用于防止作弊：例如客户端声称自己有 999 发子弹换弹
    return AmmoCount < 30;  // 弹匣满时不能换弹
}

void AMyCharacter::ServerReload_Implementation()
{
    // 服务器权威执行换弹逻辑
    int32 NeededAmmo = 30 - AmmoCount;
    int32 ActualReload = FMath::Min(NeededAmmo, LocalReserveAmmo);
    AmmoCount += ActualReload;
    LocalReserveAmmo -= ActualReload;

    // 通知客户端更新
    ClientAmmoUpdate(AmmoCount, LocalReserveAmmo);
}

// ── ClientAmmoUpdate: 服务器通知 Owner 弹药变化 ────────────
void AMyCharacter::ClientAmmoUpdate_Implementation(int32 NewAmmo, int32 NewReserve)
{
    // ★ 这里在 Owner 客户端上执行 ★
    // 更新本地预测的弹药值，覆盖之前的预测值
    LocalAmmoCount = NewAmmo;
    LocalReserveAmmo = NewReserve;

    // 如果误差很小（<2 发），不需要硬纠正——平滑过渡即可
    // 如果误差很大，立即纠正（可能预测出错或检测到作弊）
}

// ── MulticastFireEffect: 广播开火特效 ──────────────────────
void AMyCharacter::MulticastFireEffect_Implementation(
    FVector_NetQuantize MuzzleLocation, FRotator AimRotation)
{
    // ★ 这里在所有客户端上执行（包括 Owner 和非 Owner）★
    // 生成枪口闪光粒子特效
    // 注意：使用 Unreliable RPC — 特效丢了不影响游戏逻辑，下一帧会发新的

    // 示例：生成粒子（省略具体实现）
    // UGameplayStatics::SpawnEmitterAtLocation(GetWorld(), MuzzleFlashTemplate,
    //     MuzzleLocation, AimRotation, FVector(1.0f));
}

// ══════════════════════════════════════════════════════════════
// OnRep 回调 — 当复制属性到达客户端时触发
// ══════════════════════════════════════════════════════════════

void AMyCharacter::OnRep_Health()
{
    // ★ 这在收到 Health 属性更新的客户端上调用 ★
    // 更新 HUD 血量条
    // 触发受伤动画/红色闪烁效果

    if (Health <= 0.0f)
    {
        // 触发死亡逻辑
        // 注意：不要在这里做权威判断——权威在服务器
        // 这里只是表现层反应
    }
}

void AMyCharacter::OnRep_Shield()
{
    // 护盾值变化（只有 Owner 收到这个更新）
    // 更新 HUD 护盾条
}

// ══════════════════════════════════════════════════════════════
// 射击输入处理（本地预测版本）
// ══════════════════════════════════════════════════════════════

void AMyCharacter::OnFirePressed()
{
    if (!IsLocallyControlled())
        return;  // 非本地控制的角色不处理输入

    // ── 本地预测：立即消耗弹药 ────────────────────────────────
    // 这里直接修改 LocalAmmoCount（不是 Replicated 属性）
    // 好处：玩家感觉零延迟
    // 风险：如果服务器拒绝这个射击，需要回滚弹药
    LocalAmmoCount--;

    // ── 发送 ServerRPC ────────────────────────────────────────
    // 服务器会做权威校验，如果拒绝→通过 ClientAmmoUpdate 纠正
    FVector AimTarget = GetActorLocation() + GetActorForwardVector() * 1000.0f;
    ServerFire(AimTarget);

    // ── 本地播放开火特效（Unreliable Multicast 可能延迟，
    //     所以本地先播——这是 GAS 的 "Local Predicted Cue" 思路的手动版）
    // PlayLocalFireEffect();
}

void AMyCharacter::OnReloadPressed()
{
    if (!IsLocallyControlled())
        return;

    if (LocalAmmoCount >= 30)
        return;  // 弹匣已满

    ServerReload();
    // 换弹不需要本地预测（换弹时间通常在服务器上计算）
}
```

### 2.3 MyAbilitySystemComponent.h — GAS 集成

```cpp
// ============================================================
// MyAbilitySystemComponent.h
// GAS 核心组件：管理 GameplayAbility 和 GameplayEffect
// 网络：ASC 本身通过 Replication 同步到 Owner 客户端
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "MyAbilitySystemComponent.generated.h"

/**
 * 自定义 ASC：
 * - 复制模式：Mixed（推荐用于玩家控制的角色）
 *   Mixed = GameplayEffect 被复制到 Owner 客户端
 *           GameplayTag 被复制到所有客户端
 *           GameplayCue 通过复制事件触发
 */
UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class NETWORKTUTORIAL_API UMyAbilitySystemComponent : public UAbilitySystemComponent
{
    GENERATED_BODY()

public:
    UMyAbilitySystemComponent();

    // ── 网络复制配置 ──────────────────────────────────────────
    // 在 BeginPlay 中调用，根据网络模式设置复制
    void ConfigureReplicationMode();

    // ── 便捷方法 ──────────────────────────────────────────────
    
    /** 授予一个 GameplayAbility 给此 ASC */
    void GrantAbility(TSubclassOf<UGameplayAbility> AbilityClass, int32 Level = 1);

    /** 应用一个 Instant GameplayEffect（如：造成伤害） */
    void ApplyInstantEffect(TSubclassOf<UGameplayEffect> EffectClass, AActor* Target);

    /** 应用一个 Duration GameplayEffect（如：Buff/DeBuff） */
    FActiveGameplayEffectHandle ApplyDurationEffect(
        TSubclassOf<UGameplayEffect> EffectClass, float Duration);

    /** 检查是否拥有某个 GameplayTag */
    bool HasTag(const FGameplayTag& Tag) const;

    /** 获取一个 AttributeSet 中的属性值 */
    float GetAttributeValue(const FGameplayAttribute& Attribute) const;

    // ── 网络钩子 ──────────────────────────────────────────────
    virtual void BeginPlay() override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
    // ── 默认授予的技能 ────────────────────────────────────────
    UPROPERTY(EditDefaultsOnly, Category = "Abilities")
    TArray<TSubclassOf<UGameplayAbility>> DefaultAbilities;

    // ── 复制的 Tag 容器 ──────────────────────────────────────
    // 客户端需要知道服务器上哪些 Tag 是激活的（用于状态判断、UI 显示等）
    UPROPERTY(Replicated)
    FGameplayTagContainer ReplicatedTags;
};
```

### 2.4 MyAbilitySystemComponent.cpp — GAS 网络实现

```cpp
// ============================================================
// MyAbilitySystemComponent.cpp
// ============================================================

#include "MyAbilitySystemComponent.h"
#include "MyAttributeSet.h"
#include "Net/UnrealNetwork.h"
#include "GameFramework/Character.h"

UMyAbilitySystemComponent::UMyAbilitySystemComponent()
{
    // ── 设置默认复制模式 ──────────────────────────────────────
    // Full: 复制所有 GameplayEffect 到所有客户端（开销大，仅用于小型游戏）
    // Mixed: GE 复制到 Owner, Tag 复制到所有（推荐）
    // Minimal: 只复制最小的信息（纯服务器游戏）
    SetReplicationMode(EGameplayEffectReplicationMode::Mixed);

    // 启用预测
    SetIsReplicated(true);
}

void UMyAbilitySystemComponent::BeginPlay()
{
    Super::BeginPlay();

    ConfigureReplicationMode();

    // ── 授予默认技能 ──────────────────────────────────────────
    if (GetOwnerRole() == ROLE_Authority)
    {
        for (TSubclassOf<UGameplayAbility> AbilityClass : DefaultAbilities)
        {
            if (AbilityClass)
            {
                GrantAbility(AbilityClass);
            }
        }
    }
}

void UMyAbilitySystemComponent::ConfigureReplicationMode()
{
    // ── 根据是否是 AI 控制选择不同的复制模式 ─────────────────
    ACharacter* OwnerChar = Cast<ACharacter>(GetOwner());
    if (!OwnerChar)
        return;

    if (OwnerChar->IsPlayerControlled())
    {
        // 玩家控制 → Mixed 模式
        // GameplayEffect 复制到 Owner（用于 UI/HUD 更新）
        // GameplayTag 复制到所有客户端（用于其他玩家显示状态特效）
        SetReplicationMode(EGameplayEffectReplicationMode::Mixed);
    }
    else
    {
        // AI 控制 → Minimal 模式
        // AI 的 GE 不需要复制到客户端（服务器只发送最终状态如位置）
        SetReplicationMode(EGameplayEffectReplicationMode::Minimal);
    }
}

void UMyAbilitySystemComponent::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    // 复制 Tag 容器 —— 客户端需要知道服务器上有哪些激活的 Tag
    DOREPLIFETIME(UMyAbilitySystemComponent, ReplicatedTags);
}

// ══════════════════════════════════════════════════════════════
// 便捷方法
// ══════════════════════════════════════════════════════════════

void UMyAbilitySystemComponent::GrantAbility(
    TSubclassOf<UGameplayAbility> AbilityClass, int32 Level)
{
    if (!HasAuthority())
    {
        UE_LOG(LogTemp, Warning, TEXT("GrantAbility must be called on server!"));
        return;
    }

    if (!AbilityClass)
        return;

    // 创建 AbilitySpec 并授予
    FGameplayAbilitySpec AbilitySpec(AbilityClass, Level, INDEX_NONE, GetOwner());
    GiveAbility(AbilitySpec);
}

void UMyAbilitySystemComponent::ApplyInstantEffect(
    TSubclassOf<UGameplayEffect> EffectClass, AActor* Target)
{
    if (!HasAuthority())
        return;

    if (!EffectClass || !Target)
        return;

    UAbilitySystemComponent* TargetASC = Target->FindComponentByClass<UAbilitySystemComponent>();
    if (!TargetASC)
        return;

    // 创建 Effect 上下文（携带 Instigator、Causer 等信息）
    FGameplayEffectContextHandle EffectContext = MakeEffectContext();
    EffectContext.AddSourceObject(this);

    // 创建 Effect Spec
    FGameplayEffectSpecHandle SpecHandle = MakeOutgoingSpec(EffectClass, 1.0f, EffectContext);
    if (SpecHandle.IsValid())
    {
        // 应用到目标
        ApplyGameplayEffectSpecToTarget(*SpecHandle.Data.Get(), TargetASC);
    }
}

FActiveGameplayEffectHandle UMyAbilitySystemComponent::ApplyDurationEffect(
    TSubclassOf<UGameplayEffect> EffectClass, float Duration)
{
    if (!HasAuthority())
        return FActiveGameplayEffectHandle();

    FGameplayEffectContextHandle EffectContext = MakeEffectContext();
    EffectContext.AddSourceObject(this);

    FGameplayEffectSpecHandle SpecHandle = MakeOutgoingSpec(EffectClass, 1.0f, EffectContext);
    if (SpecHandle.IsValid())
    {
        // 覆写持续时间
        SpecHandle.Data->SetDuration(Duration, true);
        return ApplyGameplayEffectSpecToSelf(*SpecHandle.Data.Get());
    }

    return FActiveGameplayEffectHandle();
}

bool UMyAbilitySystemComponent::HasTag(const FGameplayTag& Tag) const
{
    return HasMatchingGameplayTag(Tag);
}

float UMyAbilitySystemComponent::GetAttributeValue(const FGameplayAttribute& Attribute) const
{
    if (!Attribute.IsValid())
        return 0.0f;

    // 使用 GetNumericAttribute — 返回属性当前值（含 GE 修改后）
    return GetNumericAttribute(Attribute);
}
```

### 2.5 MyGameplayAbility.h — 带预测的技能

```cpp
// ============================================================
// MyGameplayAbility.h
// 展示 GAS 中支持客户端预测的 GameplayAbility
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbility.h"
#include "MyGameplayAbility.generated.h"

/**
 * 技能网络执行策略：
 * - LocalPredicted: 客户端立即执行（预测），服务器确认后无缝过渡（推荐）
 * - LocalOnly: 只在客户端执行（纯表现层技能，如 UI 动画）
 * - ServerInitiated: 由服务器触发执行
 * - ServerOnly: 只在服务器执行（如 AI 技能）
 */
UCLASS()
class NETWORKTUTORIAL_API UMyFireballAbility : public UGameplayAbility
{
    GENERATED_BODY()

public:
    UMyFireballAbility();

    // ── 预测配置 ──────────────────────────────────────────────
    // 这个技能使用客户端预测
    // 预测窗口：150ms（在此时间内收到的服务器确认被视为"即时"）
    // PredictionKey 会自动生成并管理

    virtual void ActivateAbility(
        const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo,
        const FGameplayEventData* TriggerEventData) override;

    virtual void EndAbility(
        const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo,
        bool bReplicateEndAbility,
        bool bWasCancelled) override;

    // ── 技能参数 ──────────────────────────────────────────────
    UPROPERTY(EditDefaultsOnly, Category = "Fireball")
    TSubclassOf<class AProjectile> ProjectileClass;

    UPROPERTY(EditDefaultsOnly, Category = "Fireball")
    float DamageAmount = 50.0f;

    UPROPERTY(EditDefaultsOnly, Category = "Fireball")
    float ManaCost = 25.0f;

    UPROPERTY(EditDefaultsOnly, Category = "Fireball")
    float CooldownDuration = 3.0f;

    // ── 预测相关 ──────────────────────────────────────────────
    // PredictionKey: GAS 自动管理，但我们可以在代码中访问
    // 用于验证客户端预测是否正确

protected:
    // ── 复制的状态 ────────────────────────────────────────────
    // 技能的关键状态（如投射物 ID）需要复制
    UPROPERTY(Replicated)
    int32 LastSpawnedProjectileId;

    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

    // ── 核心逻辑（服务器和客户端共用）────────────────────────
    void ExecuteFireball(const FGameplayAbilityActorInfo* ActorInfo);

    // ── 服务器专属逻辑 ────────────────────────────────────────
    void ExecuteFireballOnServer(const FGameplayAbilityActorInfo* ActorInfo);

    // ── 客户端专属逻辑 ────────────────────────────────────────
    void PlayFireballEffectOnClient(const FVector& SpawnLocation, const FVector& Direction);
};

// ══════════════════════════════════════════════════════════════
// 第二个技能示例：有预测的冲刺技能
// ══════════════════════════════════════════════════════════════

UCLASS()
class NETWORKTUTORIAL_API UMyDashAbility : public UGameplayAbility
{
    GENERATED_BODY()

public:
    UMyDashAbility();

    virtual void ActivateAbility(
        const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo,
        const FGameplayEventData* TriggerEventData) override;

    virtual void EndAbility(
        const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo,
        bool bReplicateEndAbility,
        bool bWasCancelled) override;

    UPROPERTY(EditDefaultsOnly, Category = "Dash")
    float DashDistance = 800.0f;

    UPROPERTY(EditDefaultsOnly, Category = "Dash")
    float DashDuration = 0.2f;

    UPROPERTY(EditDefaultsOnly, Category = "Dash")
    UCurveFloat* DashCurve;  // 速度曲线（Time→Speed）

private:
    FVector DashStartLocation;
    FVector DashDirection;
    float DashElapsedTime;
};
```

### 2.6 MyGameplayAbility.cpp — 技能预测实现

```cpp
// ============================================================
// MyGameplayAbility.cpp
// 技能预测的关键：ExecuteFireball 在客户端和服务器上都执行
// 客户端版本是"预测"，服务器版本是"权威"
// ============================================================

#include "MyGameplayAbility.h"
#include "AbilitySystemComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Net/UnrealNetwork.h"
#include "Abilities/GameplayAbilityTypes.h"

// ══════════════════════════════════════════════════════════════
// UMyFireballAbility
// ══════════════════════════════════════════════════════════════

UMyFireballAbility::UMyFireballAbility()
{
    // ── 网络执行策略：LocalPredicted ──────────────────────────
    // 这是 GAS 网络预测的核心设置
    // LocalPredicted = 客户端立即执行 + 服务器确认
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

    // ── 预测触发策略 ──────────────────────────────────────────
    // 当服务器确认到达时，如果 PredictionKey 匹配，不会重新触发 ActivateAbility
    // 这使得客户端预测 → 服务器确认的过程对游戏逻辑透明
    InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
}

void UMyFireballAbility::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    // 投射物 ID 需要复制——这样在生成投射物后，其他客户端也能看到它
    DOREPLIFETIME(UMyFireballAbility, LastSpawnedProjectileId);
}

void UMyFireballAbility::ActivateAbility(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo,
    const FGameplayEventData* TriggerEventData)
{
    if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
    {
        // CommitAbility 失败 → 资源不足（如蓝不够、CD 未好）
        // 在客户端（预测模式）下，即使 Commit 失败也会触发
        // 服务器收到后会拒绝，客户端收到拒绝后回滚
        EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
        return;
    }

    // ── 预测流程 ──────────────────────────────────────────────
    // 1. 客户端：ActivateAbility 立即执行 → ExecuteFireball 在本地生成投射物
    // 2. 同时：GAS 框架自动发送 ServerTryActivateAbility(PredictionKey) 到服务器
    // 3. 服务器：也执行 ActivateAbility → ExecuteFireball 在服务器上生成投射物
    // 4. 服务器生成投射物后，其 Actor Replication 会同步到所有客户端
    // 5. 客户端收到服务器生成的投射物 → 检查 PredictionKey → 匹配！
    //    → 客户端本地生成的投射物"无缝过渡"为服务器权威投射物
    ExecuteFireball(ActorInfo);

    // 技能执行完成后结束
    EndAbility(Handle, ActorInfo, ActivationInfo, true, false);
}

void UMyFireballAbility::ExecuteFireball(const FGameplayAbilityActorInfo* ActorInfo)
{
    if (!ActorInfo || !ActorInfo->AvatarActor.IsValid())
        return;

    AActor* Avatar = ActorInfo->AvatarActor.Get();
    FVector SpawnLocation = Avatar->GetActorLocation() + Avatar->GetActorForwardVector() * 100.0f;
    FVector SpawnDirection = Avatar->GetActorForwardVector();

    // ── 这里检查是在服务器还是客户端 ──────────────────────────
    if (Avatar->HasAuthority())
    {
        ExecuteFireballOnServer(ActorInfo);
    }
    else
    {
        // 客户端预测：立即播放特效
        PlayFireballEffectOnClient(SpawnLocation, SpawnDirection);
    }
}

void UMyFireballAbility::ExecuteFireballOnServer(const FGameplayAbilityActorInfo* ActorInfo)
{
    // ★ 只有服务器执行这里 ★

    // 1. 生成投射物（Actor Replication 自动同步到客户端）
    AActor* Avatar = ActorInfo->AvatarActor.Get();
    FVector SpawnLocation = Avatar->GetActorLocation() + Avatar->GetActorForwardVector() * 100.0f;
    FRotator SpawnRotation = Avatar->GetActorRotation();

    FActorSpawnParameters SpawnParams;
    SpawnParams.Owner = Avatar;
    SpawnParams.Instigator = Cast<APawn>(Avatar);

    // 实际生成投射物（需要 ProjectileClass 在编辑器中设置）
    // AProjectile* Projectile = GetWorld()->SpawnActor<AProjectile>(
    //     ProjectileClass, SpawnLocation, SpawnRotation, SpawnParams);
    // if (Projectile)
    // {
    //     Projectile->SetDamage(DamageAmount);
    //     LastSpawnedProjectileId = Projectile->GetUniqueID();
    // }

    // 2. 如果任何验证失败（如瞄准位置不合法），服务器可以拒绝此技能
    // 拒绝时服务器不需要做任何事——GAS 自动发送客户端失败通知
}

void UMyFireballAbility::PlayFireballEffectOnClient(
    const FVector& SpawnLocation, const FVector& Direction)
{
    // ★ 只有客户端执行这里（本地预测）

    // 播放施法动画
    // 播放投射物生成特效
    // 播放音效

    // 注意：这里生成的"预测投射物"是临时的
    // 当服务器的权威投射物同步过来后，预测投射物应该被销毁
    // 这通常通过检查 PredictionKey 匹配来实现
}

void UMyFireballAbility::EndAbility(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo,
    bool bReplicateEndAbility,
    bool bWasCancelled)
{
    Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

// ══════════════════════════════════════════════════════════════
// UMyDashAbility
// ══════════════════════════════════════════════════════════════

UMyDashAbility::UMyDashAbility()
{
    // LocalPredicted: 客户端立即执行冲刺 = 零感知延迟
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;
    InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
}

void UMyDashAbility::ActivateAbility(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo,
    const FGameplayEventData* TriggerEventData)
{
    if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
    {
        EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
        return;
    }

    ACharacter* Character = Cast<ACharacter>(ActorInfo->AvatarActor.Get());
    if (!Character)
    {
        EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
        return;
    }

    // 记录冲刺起始位置和方向（用于后续插值）
    DashStartLocation = Character->GetActorLocation();
    DashDirection = Character->GetLastMovementInputVector();
    if (DashDirection.IsNearlyZero())
    {
        DashDirection = Character->GetActorForwardVector();
    }
    DashDirection.Normalize();
    DashElapsedTime = 0.0f;

    // 禁用 CMC 的移动输入（冲刺期间不接受正常移动输入）
    if (Character->GetCharacterMovement())
    {
        Character->GetCharacterMovement()->SetMovementMode(MOVE_Flying);
        Character->GetCharacterMovement()->StopMovementImmediately();
    }

    // 冲刺在 Tick 中逐帧更新位置（通过 UGameplayAbility 的 Tick 机制）
}

void UMyDashAbility::EndAbility(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo,
    bool bReplicateEndAbility,
    bool bWasCancelled)
{
    // 恢复 CMC 移动模式
    if (ACharacter* Character = Cast<ACharacter>(ActorInfo->AvatarActor.Get()))
    {
        if (Character->GetCharacterMovement())
        {
            Character->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
        }
    }

    Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
```

### 2.7 Iris 配置示例

```cpp
// ============================================================
// MyIrisConfig.h
// Iris 原生 API 配置示例
// 演示如何定义 FReplicationStateDescriptor 和 Filter
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "Iris/ReplicationSystem/ReplicationFragment.h"
#include "Iris/ReplicationSystem/ReplicationBridge.h"
#include "Net/Core/NetHandle/NetHandle.h"

// ══════════════════════════════════════════════════════════════
// 示例 1: 自定义 ReplicationFragment
// 用于将非 UObject 的数据结构注册到 Iris 复制系统
// ══════════════════════════════════════════════════════════════

/**
 * 展示如何为一个简单结构体创建 Iris ReplicationFragment
 * 这个 Fragment 连接游戏数据到 Iris 的 ReplicationState
 */
USTRUCT()
struct FPlayerNetworkState
{
    GENERATED_BODY()

    // 这些字段将通过 Iris 复制
    UPROPERTY()
    FVector_NetQuantize Position;

    UPROPERTY()
    FRotator Rotation;

    UPROPERTY()
    float Health;

    UPROPERTY()
    uint8 TeamIndex;

    // 脏标记：由游戏代码设置，Iris 读取
    bool bIsDirty = true;
};

/**
 * Iris Fragment：将 FPlayerNetworkState 注册到 Iris
 * 
 * 工作流：
 * 1. 在 Owner 对象的 BeginPlay 中创建 Fragment
 * 2. 调用 UReplicationSystem::CreateReplicationFragment()
 * 3. 每帧在 PreReplication 中更新 Dirty 标记
 * 4. Iris 自动处理序列化和发送
 */
UCLASS()
class UPlayerStateFragment : public UReplicationFragment
{
    GENERATED_BODY()

public:
    void Initialize(FPlayerNetworkState* InState)
    {
        State = InState;
    }

    // ── 实现 UReplicationFragment 接口 ──────────────────────

    /** Iris 调用此函数获取当前状态 */
    virtual void GetLifetimeReplicatedProps(
        TArray<class FLifetimeProperty>& OutLifetimeProps) const override
    {
        // 方式1: 使用旧的 DOREPLIFETIME 兼容路径
        Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    }

    /** Iris 调用此函数检查状态是否 dirty */
    virtual bool PollDirtyState() override
    {
        if (State && State->bIsDirty)
        {
            State->bIsDirty = false;  // 消费 dirty 标记
            return true;
        }
        return false;
    }

private:
    FPlayerNetworkState* State = nullptr;
};

// ══════════════════════════════════════════════════════════════
// 示例 2: 自定义 Iris 复制条件
// 使用 Filtering 实现"只复制给特定客户端"的逻辑
// ══════════════════════════════════════════════════════════════

/**
 * 自定义过滤器：只向同队队友复制对象
 * 
 * 在 Iris 中，Filtering 决定"这个对象是否复制给这个连接"
 * 替代旧系统中的 IsNetRelevantFor() 和 COND_Custom
 */
UCLASS()
class UTeamReplicationFilter : public UObject
{
    GENERATED_BODY()

public:
    /**
     * 检查此对象是否应该复制给指定连接
     * 
     * @param Object 被复制的对象
     * @param ConnectionId 目标连接的 ID
     * @return true = 应该复制, false = 跳过
     */
    bool ShouldReplicateToConnection(UObject* Object, uint32 ConnectionId) const
    {
        // 示例逻辑：只有同队玩家才接收此对象的更新
        // 实际实现需要访问玩家的 TeamId 信息
        
        // 伪代码：
        // AMyCharacter* Char = Cast<AMyCharacter>(Object);
        // APlayerController* PC = GetControllerFromConnectionId(ConnectionId);
        // if (Char && PC)
        // {
        //     AMyCharacter* ViewerChar = Cast<AMyCharacter>(PC->GetPawn());
        //     return ViewerChar && ViewerChar->TeamId == Char->TeamId;
        // }
        return true;  // 默认返回 true
    }
};

// ══════════════════════════════════════════════════════════════
// 示例 3: Iris 带宽优先级
// ══════════════════════════════════════════════════════════════

/**
 * Iris 优先级配置
 * 
 * 优先级决定"带宽有限时，先发送谁的状态"
 * 
 * Iris 优先级 = 静态优先级 × 动态优先级系数
 * 
 * 静态优先级（通常基于对象重要性）：
 *   - 玩家角色: 3.0
 *   - 敌人: 2.0
 *   - 可拾取物品: 1.0
 *   - 装饰物: 0.5
 * 
 * 动态优先级（基于情境）：
 *   - 正在被玩家瞄准的敌人: ×2.0
 *   - 距离 > 100m: ×0.3
 *   - 最近受过伤害: ×1.5
 */
UCLASS(Config = Game)
class UMyReplicationPrioritizationConfig : public UDeveloperSettings
{
    GENERATED_BODY()

public:
    // 玩家角色的基础优先级
    UPROPERTY(Config, EditDefaultsOnly, Category = "Priorities")
    float PlayerPawnPriority = 3.0f;

    // 敌人的基础优先级
    UPROPERTY(Config, EditDefaultsOnly, Category = "Priorities")
    float EnemyPriority = 2.0f;

    // 距离衰减曲线：横轴=距离(m)，纵轴=优先级系数
    UPROPERTY(Config, EditDefaultsOnly, Category = "Priorities")
    UCurveFloat* DistanceFalloffCurve;

    // 带宽预算：每秒最大复制字节数（每连接）
    UPROPERTY(Config, EditDefaultsOnly, Category = "Bandwidth")
    int32 MaxBytesPerSecond = 65536;  // 64 KB/s

    // 带宽预算：每秒最大对象复制数
    UPROPERTY(Config, EditDefaultsOnly, Category = "Bandwidth")
    int32 MaxReplicatedObjectsPerFrame = 256;
};

// ══════════════════════════════════════════════════════════════
// 示例 4: Iris 配置（ini 文件）
// ══════════════════════════════════════════════════════════════
/*
// DefaultEngine.ini

[/Script/IrisCore.ReplicationSystem]
; 启用 Iris（UE5 默认）
bEnableIris=true

; 最大复制对象数
MaxReplicatedObjectCount=65536

; 复制 Tick 频率（每帧的复制预算）
ReplicationTickRate=60

; 带宽限制（字节/秒）
MaxBytesPerSecond=131072

[/Script/IrisCore.ObjectReplicationBridge]
; 轮询频率：检查 objects 是否需要更新的频率
PollFrequency=30.0

; 脏状态检测的批处理大小
MaxDirtyBatchSize=256

[/Script/IrisCore.NetBlobHandler]
; 大数据分片大小（如初始复制的大型数组）
MaxNetBlobSize=65536

[/Script/IrisCore.SpatialFiltering]
; 空间过滤器：基于距离的对象筛选
; 只向距离 < MaxCullDistance 的客户端复制
MaxCullDistance=20000.0  ; 200m
CullDistanceAngleBias=30.0
*/
```

---

## 3. 练习

### 练习 1: 基础——补全 MyCharacter 的伤害同步（预计 30min）

当前代码中 `ServerFire_Implementation` 只做了弹药消耗，没有做伤害处理。请完成：

1. 添加 `TakeDamage(float DamageAmount, AController* InstigatedBy)` 的 `Server` RPC
2. 服务器接收到伤害请求后，执行权威校验：
   - 检查伤害发起者是否有权限造成伤害（同队免伤）
   - 扣除 `Health`（Health 是 Replicated 属性，修改后会自动同步）
3. 验证 `OnRep_Health()` 在两个客户端上都能正确触发
4. 添加一个 `ClientRPC` —— `ClientNotifyDamageReceived(float Damage, AActor* DamageCauser)`，只发送给受伤的客户端，用于播放受击特效/屏幕闪红

**验收标准**：两个客户端连接后，客户端 A 的射击能正确地减少客户端 B 的 Health（B 的 HUD 血条减少），且 B 的屏幕上出现受击特效。

### 练习 2: 进阶——为 CMC 添加自定义移动模式校验（预计 45min）

CMC 的 `ServerMove` 会做位置误差校验，但它只校验了最终位置。请扩展校验逻辑：

1. 在 `AMyCharacter` 中覆写 `UCharacterMovementComponent` 的派生类
2. 在自定义 CMC 中，为 `ServerMove_Implementation` 添加额外的校验：
   - **速度校验**：检查客户端声明的速度是否超过 `MaxWalkSpeed * 1.2`（防止加速外挂）
   - **时间戳校验**：检查 `TimeStamp` 是否在合理范围内（防止"时间旅行"外挂，即客户端声称自己在未来的位置）
   - **移动模式校验**：检查当前移动模式是否允许 `ServerMove`（如：飞行模式下的地面移动 = 外挂）
3. 如果校验失败，不要立即踢掉客户端（避免误判），而是：
   - 记录一次"可疑"事件
   - 累计 3 次可疑事件后断开连接
   - 使用 `ClientAdjustPosition` 纠正

**验收标准**：运行时在客户端作弊（修改 MaxWalkSpeed），服务器能检测到速度异常并能纠正客户端位置。

```cpp
// 提示：自定义 CMC 派生类框架
UCLASS()
class UNetworkTutorialCMC : public UCharacterMovementComponent
{
    GENERATED_BODY()

public:
    // 覆写网络移动校验
    virtual void ServerMove_Implementation(
        float TimeStamp,
        FVector_NetQuantize10 InAccel,
        FVector_NetQuantize100 ClientLoc,
        uint8 CompressedMoveFlags,
        uint8 ClientRoll,
        uint32 View,
        UPrimitiveComponent* ClientMovementBase,
        FName ClientBaseBoneName,
        uint8 ClientMovementMode) override;

private:
    // 可疑事件计数
    int32 SuspiciousMoveCount = 0;
    static constexpr int32 MaxSuspiciousMoves = 3;

    bool ValidateMoveSpeed(const FVector& Accel, float DeltaTime);
    bool ValidateTimestamp(float TimeStamp);
    bool ValidateMovementMode(uint8 ClientMovementMode);
};
```

### 练习 3: 挑战——用 Iris 原生 API 实现自定义属性复制（预计 60min）

当前所有代码都使用 UE 兼容层的 `UPROPERTY(Replicated)`。为了理解 Iris 的底层，请实现：

1. 创建一个 `UMyIrisReplicatedObject` 类（继承 `UObject`），不依赖 `AActor` 的复制机制
2. 使用 `FReplicationStateDescriptor` 定义需要复制的状态成员：
   - `FVector Position`
   - `FRotator Rotation`
   - `float Health`
3. 实现一个 `UIrisFragmentImpl`（`UReplicationFragment` 的子类）：
   - 在 `PollDirtyState()` 中检查上述属性是否变化
   - 只有变化的属性才标记 Dirty（增量复制）
4. 注册到 `UReplicationSystem`：
   - 使用 `UReplicationSystem::CreateReplicationFragment()` 创建 Fragment
   - 将 Fragment 绑定到 `FNetRefHandle`
5. 添加一个简单的 `IrisFilter`：只向距离 < 50m 的客户端复制（空间过滤）
6. 验证：使用 `stat Iris` 查看复制统计，对比使用旧复制系统和 Iris 原生 API 的带宽差异

**验收标准**：你的自定义 Iris 对象能被正确地复制到客户端，且在 Network Profiler 中能看到 Iris 的统计数据。对比旧系统，Iris 的 Dirty 检测更高效（只传输实际变化的属性，而非整个结构体）。

```cpp
// 提示：Iris Fragment 注册流程
void UMyIrisReplicatedObject::RegisterWithIris(UReplicationSystem* RepSystem)
{
    // 1. 创建 ReplicationState 描述符
    FReplicationStateDescriptorBuilder Builder;
    FReplicationStateDescriptor StateDesc;
    Builder.BuildDescriptor(StateDesc, this);  // 自动从 UPROPERTY 生成描述符

    // 2. 创建 Fragment
    FFragmentRegistrationContext Context(RepSystem, StateDesc);
    IrisFragment = CreateReplicationFragment(Context, this);

    // 3. 注册对象（获取 NetRefHandle）
    FNetRefHandle Handle = RepSystem->GetReplicationBridge()->BeginReplication(this);
    
    // 4. 可选：设置过滤器
    RepSystem->SetFilter(Handle, MySpatialFilter);
}
```

---

## 4. 扩展阅读

### 4.1 官方文档
- **[UE Networking Overview](https://docs.unrealengine.com/5.4/en-US/networking-overview-for-unreal-engine/)**：UE 网络系统的权威官方概述，包含 Client-Server 模型、RPC、属性复制的基础
- **[UE Character Movement Component](https://docs.unrealengine.com/5.4/en-US/character-movement-component-in-unreal-engine/)**：CMC 的详细文档，包括 `NetworkSmoothingMode`、`MaxPositionError` 等关键参数的说明
- **[Gameplay Ability System](https://docs.unrealengine.com/5.4/en-US/gameplay-ability-system-for-unreal-engine/)**：GAS 官方文档，包含 Ability、Effect、Cue、Tag 四个子系统的完整 API
- **[UE5 Iris Replication](https://docs.unrealengine.com/5.4/en-US/iris-replication-system-in-unreal-engine/)**：Iris 复制系统的白皮书级文档

### 4.2 业界参考
- **[Networking Insights: How Epic handles 100-player Fortnite](https://www.unrealengine.com/en-US/blog/replication-graph-and-network-budgets-in-fortnite-battle-royale)**：Epic 自己写的 Fortnite 网络架构文章，讲解 Replication Graph 和带宽预算
- **[Overwatch Gameplay Architecture (GDC 2017)](https://www.youtube.com/watch?v=W3aieHjyNvw)**：虽然 Overwatch 不是 UE 游戏，但其 ECS + 预测模型与 GAS 的 PredictionKey 思路高度一致，是面试常考对比
- **[The TRIBES Engine Networking Model](https://www.gamedeveloper.com/programming/the-tribes-engine-networking-model)**：业界最早的客户端预测 + 服务器和解的经典论文，CMC 的设计源泉

### 4.3 GAS 社区资源
- **[GASDocumentation (GitHub)](https://github.com/tranek/GASDocumentation)**：社区维护的 GAS 最佳实践文档，被誉为"非官方的官方 GAS 指南"。包含 Prediction、Targeting、Replication 的完整示例
- **[GASShooter (GitHub)](https://github.com/tranek/GASShooter)**：基于 GAS 构建的多人射击 Demo，完整示范了 PredictionKey、GE 同步、GameplayCue 的生产级用法
- **[Lyra Sample Game](https://docs.unrealengine.com/5.4/en-US/lyra-sample-game-in-unreal-engine/)**：Epic 官方的 UE5 多人游戏示例，使用 GAS + Enhanced Input + Modular Gameplay，是理解 UE5 网络架构的最佳生产级参考

### 4.4 Iris 深入
- **[Iris: UE5 新网络复制系统浅析 (知乎)](https://zhuanlan.zhihu.com/p/576967242)**：中文社区对 Iris 的深入分析
- **[Iris source code](https://github.com/EpicGames/UnrealEngine/tree/release/Engine/Source/Runtime/Experimental/Iris)**：Iris 的全部源码，想真正理解 Iris 的内部机制必读

---

## 常见陷阱

### 陷阱 1: ServerRPC 默认要求 Owner 才能调用

```cpp
// ❌ 错误：非 Owner 客户端调用 ServerRPC → 被静默忽略
UFUNCTION(Server, Reliable)
void ServerDoSomething();

// ✅ 正确：添加 WithValidation 并声明任何人可调用
UFUNCTION(Server, Reliable, WithValidation)
void ServerDoSomething();

bool AMyActor::ServerDoSomething_Validate()
{
    // 在这里做权限检查
    return true;  // 允许所有人
    // 或: return Cast<APlayerController>(GetInstigatorController()) != nullptr;
}

// ✅ 替代：直接在 RPC 体内用 HasAuthority() 做二次确认
void AMyActor::ServerDoSomething_Implementation()
{
    if (!HasAuthority())
        return;
    // 执行逻辑
}
```

### 陷阱 2: 复制属性的 OnRep 在服务器上也会被调用

```cpp
// ❌ 常见误解：OnRep 只在客户端调用
// 实际上：服务器在初始化时也会调用一次 OnRep（属性首次复制时）

void AMyCharacter::OnRep_Health()
{
    // 如果不检查角色定位，服务器初始化时也会执行这段
    if (GetLocalRole() == ROLE_SimulatedProxy || GetLocalRole() == ROLE_AutonomousProxy)
    {
        // 只在客户端更新 UI
        UpdateHealthBar();
    }
    // 更好的方式：直接用 GetNetMode() 判断
    if (GetNetMode() != NM_DedicatedServer)
    {
        UpdateHealthBar();  // 在所有非专用服务器端更新
    }
}
```

### 陷阱 3: CMC 的 ServerMove 不代表"移动已确认"

```
常见错误：在 ServerMove RPC 到达服务器时，认为"客户端的这次移动已被确认"。

实际情况：ServerMove 只是请求。服务器还需要：
1. 用客户端输入重新模拟移动
2. 比较位置误差
3. 只有误差 < MaxPositionError 时，客户端预测才"被接受"

正确的确认：ClientAdjustPosition 中有 AcknowledgedTimeStamp。
客户端通过这个时间戳确认"哪些 SavedMove 已经不需要了"。
```

### 陷阱 4: GAS 的 PredictionKey 过期

```cpp
// ❌ 错误：依赖 PredictionKey 的本地匹配做长时间验证
// PredictionKey 有一个"预测窗口"（默认 150ms）
// 超过这个窗口，服务器会生成新的 PredictionKey

// 场景：客户网络延迟 300ms
// 1. 客户端生成 PK1，立即预测执行技能
// 2. 300ms 后服务器收到 → PK1 已过期 → 服务器生成 PK2
// 3. 客户端收到 PK2 → 不匹配本地 PK1 → 撤销本地预测 + 应用服务器效果
// 结果：玩家看到技能"闪回"（先播放又取消再播放）← Bug！

// ✅ 解决方案：增加预测窗口（如果网络条件允许）
// 在 DefaultGame.ini:
// [/Script/GameplayAbilities.AbilitySystemGlobals]
// PredictionKeyWindowMS=300  // 增加到 300ms
```

### 陷阱 5: GameplayCue Local vs Replicated 混淆

```cpp
// ❌ 错误：对其他玩家使用 Local Cue（对方看不到）
void ApplyDamageToEnemy(AActor* Enemy)
{
    // 在服务器上执行
    // 错误：AddGameplayCue_Local 只在调用方本地播放
    Enemy->GetAbilitySystemComponent()->AddGameplayCue_Local(HitCueTag);
    // → 服务器上播放了特效（无人看到），而敌方客户端看不到
}

// ✅ 正确：对其他玩家使用 Replicated Cue
void ApplyDamageToEnemy(AActor* Enemy)
{
    // 在服务器上执行
    // Replicated Cue: 服务器添加 → 通过复制同步到所有客户端
    FGameplayCueParameters CueParams;
    CueParams.Location = HitLocation;
    CueParams.Normal = HitNormal;
    Enemy->GetAbilitySystemComponent()->AddGameplayCue_Replicated(HitCueTag, CueParams);
    // → 敌方客户端看到受击特效
}

// ✅ 对本地玩家使用 Local Cue（用于预测）
void PredictDamageOnSelf()
{
    // 在 AutonomousProxy 上执行（客户端预测）
    SelfASC->AddGameplayCue_Local(HitCueTag);
    // → 立即播放受击特效（不等服务器确认）
}
```

### 陷阱 6: 在属性复制的 OnRep 中调用 RPC

```cpp
// ❌ 严重错误：OnRep 可能被多个客户端同时触发，在其中调用 ClientRPC 会广播
void AMyCharacter::OnRep_Health()
{
    // 如果这里调用 NetMulticastRPC → 所有客户端的 OnRep 都会触发 Multicast
    // → 等于一个广播变成 N 个广播（N = 客户端数量）
    // 在最坏情况下会导致网络风暴
    MulticastDeathEffect();  // ❌ 绝对不要这样做
}

// ✅ 正确：只在服务器上检查状态变化并决定是否发 RPC
void AMyCharacter::TakeDamage_ServerSide(float Damage)
{
    // 仅在服务器上执行
    if (!HasAuthority())
        return;

    Health -= Damage;
    // 修改 Health 会自动触发 OnRep_Health 在客户端上执行

    if (Health <= 0)
    {
        // 只在服务器上调用 Multicast
        MulticastDeathEffect();
    }
}
```

### 陷阱 7: CMC 的 MaxPositionError 设置不当

```
设置太小（<5cm）：
  → 服务器频繁纠正 → 客户端"抖动" → 玩家体验极差
  → 带宽浪费（每次纠正都需要发送 ClientAdjustPosition）

设置太大（>100cm）：
  → 客户端可以"远程瞬移"（加速挂）不被检测
  → 玩家穿墙、穿地板（服务器认为位置误差在容忍范围内）

推荐值（经验法则）：
  - 第一人称射击：5-15cm（要求精确位置）
  - 第三人称动作：15-30cm
  - 开放世界 RPG：30-60cm
  - 赛车游戏：取决于速度（高速时放宽）
  
动态调整策略：
  if (Character->GetVelocity().Size() > 1000.f) // 高速移动
      MaxPositionError = 60.0f;  // 放宽
  else
      MaxPositionError = 15.0f;  // 收紧
```

### 陷阱 8: Iris 下仍用旧的 IsNetRelevantFor

```
UE5 启用了 Iris 后，旧系统的 IsNetRelevantFor() 可能不再被调用。
检查你的项目设置：

[/Script/IrisCore.ReplicationSystem]
bEnableIris=true  ← 如果是 true，使用 Iris 的 Filtering 系统

如果你在代码中覆写了 IsNetRelevantFor() 但 Iris 已启用：
  → 这个函数不会被调用
  → 你的自定义相关性逻辑不起作用
  → 解决：使用 Iris 的 UReplicationFilter 子类替代

验证方法：
  在 IsNetRelevantFor() 中加断点或日志，看看是否被调用
  如果从不触发，说明 Iris 已接管
```
