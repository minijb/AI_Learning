# 帧同步客户端实现（Unreal/C++）

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [07-帧同步协议设计](07-lockstep-protocol-design.md)

---

## 1. 概念讲解

### 1.1 为什么 Unreal 帧同步需要"另起炉灶"？

Unreal Engine 自带一套强大的网络复制系统——属性复制（Replication）、RPC、Relevancy、NetDriver。但它天生是为**状态同步**设计的：

```
UE 默认网络模型：
客户端 ──[输入]──► 服务器（权威）
                    │
                    │ 服务器计算 → 复制属性 → 客户端接收
                    ▼
客户端（接收状态，插值渲染）
```

而帧同步（Lockstep）的核心是**同步输入而非状态**，这与 UE 内置网络的哲学完全相反。如果你在 UE 里做帧同步，**UE 的 `UNetDriver`、`AActor::GetLifetimeReplicatedProps()`、`ServerRPC` 几乎全部用不上**。

你需要的是一套**自定义 UDP 网络层 + 固定时钟逻辑 Tick + 确定性系统**。

这不是坏事——正因为 UE 的网络层与你无关，你不会被它的限制框住。但也意味着**你要自己管理 Socket、收发线程、帧缓冲、逻辑/渲染分离**。

#### UE 帧同步的技术栈替代表

| 需求 | UE 内置方案 | 帧同步替代方案 |
|------|------------|---------------|
| 网络传输 | `UNetDriver` + `UNetConnection` | `FUdpSocketBuilder` + 自定义 `FRunnable` 收发线程 |
| 数据序列化 | `FArchive` + `UPROPERTY(Replicated)` | 自定义 `FMemoryWriter`/`FMemoryReader` 或 Protobuf |
| Tick 驱动 | `AActor::Tick`（渲染帧驱动） | `UGameInstanceSubsystem::Tick`（逻辑帧驱动，固定时钟） |
| 输入系统 | `APlayerController::InputComponent` | `UEnhancedInputComponent` → 自定义 `FFrameCommand` |
| Actor 生成/销毁 | `UWorld::SpawnActor` 自动复制 | 手动管理，在逻辑世界创建/销毁，表现层跟随 |
| 动画同步 | `ACharacter` 自动复制 Movement | 由表现层插值驱动，不依赖网络复制 |

### 1.2 整体架构

UE 帧同步客户端的分层架构如下：

```
┌─────────────────────────────────────────────────────────────┐
│                      游戏表现层 (Visual Layer)               │
│  AActor (渲染), UStaticMesh, USkeletalMesh, UMG, 音效       │
│  由表现层 Actor 驱动，每渲染帧更新                            │
├─────────────────────────────────────────────────────────────┤
│                      表现桥接层 (Sync Bridge)                │
│  读取逻辑世界状态 → 插值/平滑 → 更新表现层 Transform/动画     │
├─────────────────────────────────────────────────────────────┤
│                      逻辑层 (Logic Layer)                    │
│  ALockstepActor (纯逻辑, 无Mesh), 确定性C++, 定点数计算      │
│  由 LockstepSubsystem 按固定逻辑帧率驱动                      │
├─────────────────────────────────────────────────────────────┤
│  LockstepSubsystem (UGameInstanceSubsystem)                  │
│  帧时钟管理, 帧缓冲, 追帧逻辑, 输入收集, 帧分发               │
├─────────────────────────────────────────────────────────────┤
│  网络层                                                      │
│  LockstepNetComponent (FUdpSocketBuilder, FRunnable)         │
│  UDP 收发线程, 包序列化/反序列化, 冗余控制                    │
├─────────────────────────────────────────────────────────────┤
│  输入层                                                      │
│  Enhanced Input → FrameCommand 映射                          │
└─────────────────────────────────────────────────────────────┘
```

**核心设计原则**：

1. **逻辑层零渲染依赖**：逻辑层的 `ALockstepActor` 不挂载任何 `UStaticMeshComponent`、`USkeletalMeshComponent`。它只有数据（定点数位置、血量、状态机）和纯逻辑函数。这使得逻辑层可以脱离渲染完全独立运行——这正是帧同步确定性的要求。

2. **表现层只读逻辑状态**：表现层 Actor **绝不修改**逻辑层状态。它从逻辑对象读取 Transform/状态，插值后更新自己的 SceneComponent。

3. **网络层与游戏逻辑解耦**：网络收发在独立线程中运行（`FRunnable`），与游戏主线程通过 `TQueue`（无锁队列）通信。避免网络抖动阻塞渲染。

4. **使用 `UGameInstanceSubsystem` 而非 `AActor` 或 `UObject` 管理帧循环**：Subsystem 的生命周期与 `UGameInstance` 绑定，不随关卡切换而销毁，非常适合管理整个游戏会话的帧同步状态。

### 1.3 UE 引擎的 Tick 体系与帧同步的冲突

UE 的标准 Tick 管线如下：

```
UWorld::Tick
 └─ TickGroups (TG_PrePhysics, TG_DuringPhysics, TG_PostPhysics, ...)
   └─ AActor::Tick (每个 Actor 按组注册)
     └─ UActorComponent::TickComponent
       └─ ...
```

问题在于：这个 Tick 体系是**按渲染帧驱动的**（60/120/144 Hz，且是**可变的**——帧率掉到 40fps 时 Tick 频率也掉到 40Hz）。而帧同步需要的是**固定的逻辑帧率**（如 15Hz、20Hz、30Hz），且不应受渲染帧率波动的影响。

UE 提供了 **`FTickableGameObject`** 接口和 **`UWorld::GetFixedTimeStep()`**，但更干净的方案是使用 `UGameInstanceSubsystem` 的 Tick：

```cpp
// UGameInstanceSubsystem 的 Tick 在每个 UWorld::Tick 中被调用
// 但这仍是可变频率的。我们需要的做法是：

void ULockstepSubsystem::Tick(float DeltaTime)
{
    AccumulatedTime += DeltaTime;  // 累积真实时间

    // 固定步长推进逻辑帧
    while (AccumulatedTime >= LogicFrameInterval)
    {
        AdvanceOneLogicFrame();     // 推进一个逻辑帧
        AccumulatedTime -= LogicFrameInterval;
    }

    // 渲染帧部分：更新表现层插值
    UpdatePresentationLayer(AccumulatedTime / LogicFrameInterval);
}
```

这与 Unity 的 `FixedUpdate` 思路一致：将可变渲染帧的 DeltaTime 累积，按固定步长消费，产生逻辑帧。

---

## 2. 代码示例

以下代码为 Unreal Engine 5.x 的生产级参考实现。所有代码均标注了关键决策点和可优化的方向。

### 2.1 FFrameCommand：帧指令数据结构

这是帧同步网络上传输的核心数据单元。

```cpp
// ============================================================
// FrameCommand.h
// 帧同步输入指令的数据结构定义
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "FrameCommand.generated.h"

// 帧指令中可用的操作类型
// 使用位掩码以支持一帧内多个操作组合
UENUM(BlueprintType, meta = (Bitflags, UseEnumValuesAsMaskValuesInEditor = "true"))
enum class EFrameCommandType : uint8
{
    None        = 0,
    Move        = 1 << 0,   // 移动指令（带方向/目标点）
    Attack      = 1 << 1,   // 攻击指令（带目标ID/方向）
    Skill       = 1 << 2,   // 技能释放（带技能ID）
    Item        = 1 << 3,   // 使用道具（带道具ID）
    Stop        = 1 << 4,   // 停止/取消当前动作
    Ping        = 1 << 5,   // 保活心跳（空操作）
};

// 移动方向编码：8 方向 + 停止
// 使用枚举而非浮点方向向量，确保确定性
UENUM()
enum class EMoveDirection : uint8
{
    None        = 0,
    Up          = 1,
    UpRight     = 2,
    Right       = 3,
    DownRight   = 4,
    Down        = 5,
    DownLeft    = 6,
    Left        = 7,
    UpLeft      = 8,
};

// 核心帧指令
// 使用 Packed 布局以最小化网络传输体积
// 总计 12 字节（不含填充对齐）
USTRUCT(BlueprintType)
struct FFrameCommand
{
    GENERATED_BODY()

    // 目标逻辑帧号（服务端分配的帧号）
    UPROPERTY()
    uint32 FrameNumber = 0;

    // 玩家ID（单局内的玩家编号，0~N-1）
    UPROPERTY()
    uint8 PlayerId = 0;

    // 指令类型位掩码
    UPROPERTY()
    uint8 CommandFlags = 0;

    // 移动方向（仅当 CommandFlags & Move 时生效）
    UPROPERTY()
    EMoveDirection MoveDir = EMoveDirection::None;

    // 技能ID / 道具ID（视指令类型决定含义）
    // 高5位: 技能类型大类, 低11位: 具体技能编号
    UPROPERTY()
    uint16 ActionId = 0;

    // 目标实体ID（用于攻击/技能的目标选择）
    UPROPERTY()
    uint16 TargetEntityId = 0;

    // 快捷判断
    bool HasMove() const    { return (CommandFlags & static_cast<uint8>(EFrameCommandType::Move)) != 0; }
    bool HasAttack() const  { return (CommandFlags & static_cast<uint8>(EFrameCommandType::Attack)) != 0; }
    bool HasSkill() const   { return (CommandFlags & static_cast<uint8>(EFrameCommandType::Skill)) != 0; }
    bool IsEmpty() const    { return CommandFlags == 0; }

    // 序列化（手动控制，支持版本兼容）
    void Serialize(FArchive& Ar)
    {
        // 网络字节序处理：使用 UE 的字节序工具
        Ar << FrameNumber;
        Ar << PlayerId;
        Ar << CommandFlags;
        Ar << MoveDir;
        Ar << ActionId;
        Ar << TargetEntityId;
    }

    // 重置为空指令
    void Reset()
    {
        CommandFlags = 0;
        MoveDir = EMoveDirection::None;
        ActionId = 0;
        TargetEntityId = 0;
    }

    // 创建一个空指令（用于缺帧填充）
    static FFrameCommand MakeEmpty(uint32 InFrameNumber, uint8 InPlayerId)
    {
        FFrameCommand Cmd;
        Cmd.FrameNumber = InFrameNumber;
        Cmd.PlayerId = InPlayerId;
        return Cmd;
    }
};

// 一帧内所有玩家的指令集合
// 这个结构是服务端广播给客户端的完整帧数据
USTRUCT()
struct FFrameInputSet
{
    GENERATED_BODY()

    UPROPERTY()
    uint32 FrameNumber = 0;

    // 每个玩家的指令（按 PlayerId 索引）
    UPROPERTY()
    TArray<FFrameCommand> Commands;

    // 该帧的时间戳（服务器时间，用于延迟计算）
    UPROPERTY()
    double ServerTimestamp = 0.0;

    bool IsValid() const { return Commands.Num() > 0; }

    // 获取指定玩家的指令
    const FFrameCommand* GetPlayerCommand(uint8 PlayerId) const
    {
        if (PlayerId < (uint8)Commands.Num())
        {
            return &Commands[PlayerId];
        }
        return nullptr;
    }
};
```

### 2.2 FrameBuffer.h：帧缓冲模板

`TCircularBuffer` 是一个固定大小的环形缓冲区，用于缓存待消费的网络帧。

```cpp
// ============================================================
// FrameBuffer.h
// 固定容量环形帧缓冲区
// ============================================================

#pragma once

#include "CoreMinimal.h"

/**
 * 环形帧缓冲区模板
 * 
 * 用途：存储从网络收到的帧数据，解决网络抖动导致的帧到达时间不均匀问题。
 * 
 * 帧同步中，网络帧按固定间隔（如每66ms一帧）到达。但由于网络抖动，
 * 实际到达时间不均匀——可能一口气到3帧，然后卡300ms没帧。
 * 
 * TCircularBuffer 缓存 N 帧（通常 6~10 帧，即 0.4~0.66 秒缓冲），
 * 消费端（逻辑层）按固定频率从缓冲区取帧，实现"削峰填谷"。
 * 
 * 关键参数：
 * - Capacity: 缓冲容量（帧数）。太小→无法应对抖动；太大→输入延迟增加。
 * - ReadIndex: 下一个待消费帧的索引
 * - WriteIndex: 下一个可写入位置的索引
 */
template<typename TFrameData, int32 Capacity>
struct TCircularBuffer
{
    static_assert(Capacity >= 2, "Capacity must be at least 2");
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2 for bitmask optimization");

    TFrameData Buffer[Capacity];
    
    // 使用 int32 避免索引溢出，用位掩码快速取模
    uint32 ReadIndex = 0;
    uint32 WriteIndex = 0;

    // 容量掩码：Capacity = 8 → Mask = 0b111 → idx & Mask 等价于 idx % 8
    static constexpr uint32 Mask = Capacity - 1;

    // 缓冲区中的帧数量
    int32 Count() const
    {
        return (int32)(WriteIndex - ReadIndex);
    }

    // 缓冲区是否为空
    bool IsEmpty() const
    {
        return ReadIndex == WriteIndex;
    }

    // 缓冲区是否已满
    bool IsFull() const
    {
        return Count() >= Capacity;
    }

    // 可用的空闲槽位数
    int32 AvailableSlots() const
    {
        return Capacity - Count();
    }

    // 写入一帧。
    // @return true 如果写入成功；false 如果缓冲区已满。
    bool Enqueue(const TFrameData& Frame)
    {
        if (IsFull())
        {
            return false;
        }
        Buffer[WriteIndex & Mask] = Frame;
        ++WriteIndex;
        return true;
    }

    // 写入一帧（移动语义）
    bool Enqueue(TFrameData&& Frame)
    {
        if (IsFull())
        {
            return false;
        }
        Buffer[WriteIndex & Mask] = MoveTemp(Frame);
        ++WriteIndex;
        return true;
    }

    // 取出下一帧。
    // @return true 如果成功取出；false 如果缓冲区为空。
    bool Dequeue(TFrameData& OutFrame)
    {
        if (IsEmpty())
        {
            return false;
        }
        OutFrame = MoveTemp(Buffer[ReadIndex & Mask]);
        ++ReadIndex;
        return true;
    }

    // 查看下一帧但不取出。
    const TFrameData* Peek() const
    {
        if (IsEmpty())
        {
            return nullptr;
        }
        return &Buffer[ReadIndex & Mask];
    }

    // 跳过 N 帧（用于追帧——网络恢复后快速消费积压帧）。
    // @return 实际跳过的帧数。
    int32 SkipFrames(int32 NumFrames)
    {
        int32 Skipped = FMath::Min(NumFrames, Count());
        ReadIndex += Skipped;
        return Skipped;
    }

    // 清空缓冲区。
    void Clear()
    {
        ReadIndex = WriteIndex;
    }

    // 当前缓冲深度占容量的比例（0.0~1.0）。
    float FillRatio() const
    {
        return (float)Count() / (float)Capacity;
    }
};
```

### 2.3 LockstepSubsystem：帧同步核心

这是整个帧同步客户端的控制中心。

**文件：LockstepSubsystem.h**

```cpp
// ============================================================
// LockstepSubsystem.h
// 帧同步核心子系统
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "FrameCommand.h"
#include "FrameBuffer.h"
#include "LockstepSubsystem.generated.h"

// 帧同步状态
UENUM()
enum class ELockstepState : uint8
{
    Uninitialized,      // 未初始化
    Connecting,         // 正在连接服务器
    Syncing,            // 正在同步初始状态 / 追帧
    Running,            // 正常运行
    Paused,             // 暂停
    Disconnected,       // 断线
};

// 逻辑 Tick 委托：每个逻辑帧广播一次，逻辑层 Actor 注册此委托
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnLogicTick, uint32, FrameNumber);

// 帧同步事件委托
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnFrameSyncConnected);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnFrameSyncDisconnected);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnDesyncDetected, uint32, FrameNumber, const FString&, HashDiff);

// 前向声明
class ULockstepNetComponent;
class FFrameInputCollector;

/**
 * 帧同步子系统 (UGameInstanceSubsystem)
 * 
 * 生命周期跟随 UGameInstance：
 * - 游戏启动 → Initialize()
 * - 关卡切换 → 不会销毁（与 UGameInstance 同生命周期）
 * - 游戏结束 → Deinitialize()
 * 
 * 职责：
 * 1. 管理帧时钟和逻辑帧推进
 * 2. 维护帧缓冲区和追帧逻辑
 * 3. 收集本地玩家输入 → FFrameCommand
 * 4. 分发逻辑帧事件给逻辑层 Actor
 * 5. 管理连接生命周期
 */
UCLASS()
class ULockstepSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
    GENERATED_BODY()

public:
    // ── USubsystem 生命周期 ──
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    // ── FTickableGameObject 接口 ──
    virtual void Tick(float DeltaTime) override;
    virtual TStatId GetStatId() const override;
    virtual bool IsTickable() const override { return !IsTemplate(); }
    virtual bool IsTickableInEditor() const override { return false; }

    // ── 公共 API ──

    // 连接到帧同步服务器
    UFUNCTION(BlueprintCallable)
    void ConnectToServer(const FString& ServerAddress, int32 Port, uint8 InPlayerId);

    // 断开连接
    UFUNCTION(BlueprintCallable)
    void Disconnect();

    // 获取当前状态
    UFUNCTION(BlueprintCallable)
    ELockstepState GetState() const { return CurrentState; }

    // 获取当前逻辑帧号
    UFUNCTION(BlueprintCallable)
    uint32 GetCurrentFrameNumber() const { return CurrentFrameNumber; }

    // 获取网络延迟（RTT，毫秒）
    UFUNCTION(BlueprintCallable)
    float GetNetworkRTT() const { return NetworkRTT; }

    // 获取帧缓冲深度
    UFUNCTION(BlueprintCallable)
    int32 GetBufferFrameCount() const { return FrameBuffer.Count(); }

    // 是否处于追帧状态
    UFUNCTION(BlueprintCallable)
    bool IsCatchingUp() const { return bIsCatchingUp; }

    // ── 事件 ──
    UPROPERTY(BlueprintAssignable)
    FOnLogicTick OnLogicTick;

    UPROPERTY(BlueprintAssignable)
    FOnFrameSyncConnected OnConnected;

    UPROPERTY(BlueprintAssignable)
    FOnFrameSyncDisconnected OnDisconnected;

    // ── 配置 ──

    // 逻辑帧间隔（秒），15Hz → 0.0667s，20Hz → 0.05s，30Hz → 0.0333s
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Lockstep|Timing")
    float LogicFrameInterval = 1.0f / 15.0f;

    // 帧缓冲容量（帧数）。推荐 6~10。
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Lockstep|Buffer")
    int32 FrameBufferCapacity = 8;

    // 追帧加速倍数。处于追帧状态时，每个渲染帧消费 N 个逻辑帧。
    // 1 = 不加速，3 = 3倍速追赶。
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Lockstep|CatchUp")
    int32 CatchUpMultiplier = 3;

    // 触发追帧的缓冲阈值：低于此帧数时恢复正常速度。
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Lockstep|Buffer")
    int32 BufferLowThreshold = 3;

    // 开始追帧的缓冲阈值：超过此帧数时启动加速。
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Lockstep|Buffer")
    int32 BufferHighThreshold = 5;

    // 最大允许的缓冲帧数（超过此值视为严重落后，直接跳帧）。
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Lockstep|Buffer")
    int32 MaxBufferFrames = 30;

protected:
    // ── 内部方法 ──

    // 尝试推进一个逻辑帧
    void AdvanceOneLogicFrame();

    // 追帧模式：一次消费多帧
    void CatchUpFrames(int32 NumFrames);

    // 处理一个完整的帧输入集
    void ProcessFrameInput(const FFrameInputSet& InputSet);

    // 收集本地玩家输入
    FFrameCommand CollectLocalInput(uint32 FrameNumber);

    // 发送本地输入到服务器
    void SendLocalInput(const FFrameCommand& Command);

    // 计算网络 RTT
    void UpdateRTT();

    // ── 成员变量 ──

    // 当前状态
    ELockstepState CurrentState = ELockstepState::Uninitialized;

    // 当前逻辑帧号
    uint32 CurrentFrameNumber = 0;

    // 上次帧号（用于跳帧检测）
    uint32 LastProcessedFrameNumber = 0;

    // 本地玩家ID
    uint8 LocalPlayerId = 0;

    // 累积的渲染帧时间
    float AccumulatedTime = 0.0f;

    // 帧缓冲区：网络帧 → 逻辑消费
    TCircularBuffer<FFrameInputSet, 8> FrameBuffer;

    // 是否处于追帧状态
    bool bIsCatchingUp = false;

    // 网络 RTT（毫秒）
    float NetworkRTT = 50.0f;

    // 上次 RTT 测量的时间戳
    double LastRTTMeasureTime = 0.0;

    // 网络组件
    UPROPERTY()
    TObjectPtr<ULockstepNetComponent> NetComponent;

    // 输入收集器（处理 Enhanced Input → FrameCommand 映射）
    TUniquePtr<class FFrameInputCollector> InputCollector;

    // 追帧中跳过的帧数（统计用）
    int32 TotalSkippedFrames = 0;

private:
    // 帧缓冲区实际模板参数（使用 FrameBufferCapacity 配置）
    // 简化处理：固定使用 64 帧最大容量（实际可根据配置调整）
    static constexpr int32 MaxFrameCapacity = 64;
    TCircularBuffer<FFrameInputSet, MaxFrameCapacity> FrameBuffer64;
};
```

**文件：LockstepSubsystem.cpp（核心逻辑）**

```cpp
// ============================================================
// LockstepSubsystem.cpp
// ============================================================

#include "LockstepSubsystem.h"
#include "LockstepNetComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"

// 输入收集器的简单实现
class FFrameInputCollector
{
public:
    FFrameInputCollector(uint8 InPlayerId) : PlayerId(InPlayerId) {}

    // 从 Enhanced Input 或原始输入映射到 FFrameCommand
    FFrameCommand BuildCommand(uint32 FrameNumber)
    {
        FFrameCommand Cmd;
        Cmd.FrameNumber = FrameNumber;
        Cmd.PlayerId = PlayerId;

        // 这里读取缓存的输入状态。
        // 实际项目中，Enhanced Input 的回调会更新 CachedMoveDirection 等成员，
        // 然后在这里消费。
        if (bHasPendingMove)
        {
            Cmd.CommandFlags |= static_cast<uint8>(EFrameCommandType::Move);
            Cmd.MoveDir = CachedMoveDirection;
            bHasPendingMove = false;
        }
        if (bHasPendingAttack)
        {
            Cmd.CommandFlags |= static_cast<uint8>(EFrameCommandType::Attack);
            Cmd.TargetEntityId = CachedAttackTarget;
            bHasPendingAttack = false;
        }
        if (bHasPendingSkill)
        {
            Cmd.CommandFlags |= static_cast<uint8>(EFrameCommandType::Skill);
            Cmd.ActionId = CachedSkillId;
            bHasPendingSkill = false;
        }

        return Cmd;
    }

    // 这些方法由 Enhanced Input 回调调用
    void SetMoveDirection(EMoveDirection Dir)
    {
        // 同帧内多次移动输入 → 保留最后一个（Last Wins）
        CachedMoveDirection = Dir;
        bHasPendingMove = true;
    }

    void SetPendingAttack(uint16 TargetId)
    {
        CachedAttackTarget = TargetId;
        bHasPendingAttack = true;
    }

    void SetPendingSkill(uint16 SkillId)
    {
        CachedSkillId = SkillId;
        bHasPendingSkill = true;
    }

    // 在每个逻辑帧结束时重置"按下"类输入（如技能按键抬起）
    // 移动/持续性输入在消费后自动重置
    void ClearConsumedInputs()
    {
        bHasPendingAttack = false;
        bHasPendingSkill = false;
    }

private:
    uint8 PlayerId;
    
    EMoveDirection CachedMoveDirection = EMoveDirection::None;
    uint16 CachedAttackTarget = 0;
    uint16 CachedSkillId = 0;
    
    bool bHasPendingMove = false;
    bool bHasPendingAttack = false;
    bool bHasPendingSkill = false;
};

// ──────────────────────────────────────────────
// ULockstepSubsystem 实现
// ──────────────────────────────────────────────

void ULockstepSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    UE_LOG(LogTemp, Log, TEXT("[Lockstep] Subsystem initialized."));

    // 创建网络组件
    NetComponent = NewObject<ULockstepNetComponent>(this);
    if (NetComponent)
    {
        NetComponent->OnFrameReceived.BindUObject(this, &ULockstepSubsystem::OnFrameReceived);
    }

    // 将 Tick 函数注册到 Tick 管理器
    // FTickableGameObject 会自动被 UE 的 Tick 系统调用
}

void ULockstepSubsystem::Deinitialize()
{
    Disconnect();
    NetComponent = nullptr;
    InputCollector.Reset();

    UE_LOG(LogTemp, Log, TEXT("[Lockstep] Subsystem deinitialized."));
    Super::Deinitialize();
}

void ULockstepSubsystem::Tick(float DeltaTime)
{
    if (CurrentState != ELockstepState::Running && 
        CurrentState != ELockstepState::Syncing)
    {
        return;
    }

    // ── 第一步：处理网络收到的帧 ──
    // NetComponent 在独立线程收包，通过 TQueue 将帧数据传给主线程
    NetComponent->FlushReceivedFrames(FrameBuffer64);

    // ── 第二步：判断缓冲状态 ──
    int32 BufferedCount = FrameBuffer64.Count();

    if (BufferedCount == 0)
    {
        // 完全没有帧可消费 → 网络严重延迟或断线
        // 在帧同步中这是"卡住"的信号。
        // 生产环境可能进入暂停状态等待网络恢复。
        return;
    }

    if (BufferedCount > MaxBufferFrames)
    {
        // 缓冲严重溢出 → 追不上，直接跳帧到阈值以内
        int32 FramesToSkip = BufferedCount - BufferHighThreshold;
        FrameBuffer64.SkipFrames(FramesToSkip);
        TotalSkippedFrames += FramesToSkip;
        UE_LOG(LogTemp, Warning, TEXT("[Lockstep] Buffer overflow! Skipped %d frames (total skipped: %d)"), 
            FramesToSkip, TotalSkippedFrames);
    }

    // ── 第三步：确定加速策略 ──
    bIsCatchingUp = (BufferedCount > BufferHighThreshold);
    int32 FramesToProcess = bIsCatchingUp ? CatchUpMultiplier : 1;

    // ── 第四步：累积时间，按固定步长消费 ──
    AccumulatedTime += DeltaTime;

    while (AccumulatedTime >= LogicFrameInterval && FramesToProcess > 0)
    {
        AdvanceOneLogicFrame();
        AccumulatedTime -= LogicFrameInterval;
        --FramesToProcess;

        // 如果缓冲已空或恢复到低水位，停止加速
        if (FrameBuffer64.Count() <= BufferLowThreshold)
        {
            bIsCatchingUp = false;
            break;
        }
    }

    // ── 第五步：收集并发送本地输入 ──
    // 每逻辑帧发送一次输入。服务器收到后将其归入对应帧号。
    if (CurrentState == ELockstepState::Running)
    {
        FFrameCommand LocalCmd = CollectLocalInput(CurrentFrameNumber);
        SendLocalInput(LocalCmd);
    }
}

TStatId ULockstepSubsystem::GetStatId() const
{
    RETURN_QUICK_DECLARE_CYCLE_STAT(ULockstepSubsystem, STATGROUP_Tickables);
}

// ──────────────────────────────────────────────
// 核心：推进一个逻辑帧
// ──────────────────────────────────────────────
void ULockstepSubsystem::AdvanceOneLogicFrame()
{
    FFrameInputSet InputSet;
    if (!FrameBuffer64.Dequeue(InputSet))
    {
        // 缓冲区为空——不应该到达这里（Tick 中已检查 Count == 0）
        return;
    }

    uint32 FrameNum = InputSet.FrameNumber;

    // 跳帧检测：如果当前帧号与上次处理帧号不连续
    if (LastProcessedFrameNumber > 0 && FrameNum != LastProcessedFrameNumber + 1)
    {
        UE_LOG(LogTemp, Warning, TEXT("[Lockstep] Frame gap detected: %u -> %u"), 
            LastProcessedFrameNumber, FrameNum);
    }

    // 处理帧指令集：广播给所有逻辑层 Actor
    ProcessFrameInput(InputSet);

    CurrentFrameNumber = FrameNum;
    LastProcessedFrameNumber = FrameNum;
}

// ──────────────────────────────────────────────
// 处理帧输入
// ──────────────────────────────────────────────
void ULockstepSubsystem::ProcessFrameInput(const FFrameInputSet& InputSet)
{
    // ── 步骤 1：将本帧的输入指令写入每个逻辑 Actor 的指令队列 ──
    // （逻辑 Actor 通过注册表查找，此处简化）
    
    // ── 步骤 2：广播逻辑 Tick 事件 ──
    // 所有注册了 OnLogicTick 的逻辑 Actor 在这个回调中推进自己的状态。
    // 注意：广播顺序必须确定。使用有序容器（TArray/TMap 按 ID 排序）。
    OnLogicTick.Broadcast(InputSet.FrameNumber);
}

// ──────────────────────────────────────────────
// 追帧
// ──────────────────────────────────────────────
void ULockstepSubsystem::CatchUpFrames(int32 NumFrames)
{
    bIsCatchingUp = true;
    for (int32 i = 0; i < NumFrames; ++i)
    {
        if (FrameBuffer64.Count() <= BufferLowThreshold)
        {
            bIsCatchingUp = false;
            break;
        }
        AdvanceOneLogicFrame();
    }
}

// ──────────────────────────────────────────────
// 收集本地输入
// ──────────────────────────────────────────────
FFrameCommand ULockstepSubsystem::CollectLocalInput(uint32 FrameNumber)
{
    if (InputCollector.IsValid())
    {
        return InputCollector->BuildCommand(FrameNumber);
    }

    FFrameCommand EmptyCmd = FFrameCommand::MakeEmpty(FrameNumber, LocalPlayerId);
    return EmptyCmd;
}

// ──────────────────────────────────────────────
// 发送本地输入到服务器
// ──────────────────────────────────────────────
void ULockstepSubsystem::SendLocalInput(const FFrameCommand& Command)
{
    if (NetComponent && CurrentState == ELockstepState::Running)
    {
        // 空指令也发送，作为保活心跳
        NetComponent->SendCommand(Command);
    }
}

// ──────────────────────────────────────────────
// 连接管理
// ──────────────────────────────────────────────
void ULockstepSubsystem::ConnectToServer(const FString& ServerAddress, int32 Port, uint8 InPlayerId)
{
    LocalPlayerId = InPlayerId;
    CurrentState = ELockstepState::Connecting;

    // 初始化输入收集器
    InputCollector = MakeUnique<FFrameInputCollector>(InPlayerId);

    // 初始化网络组件
    if (NetComponent)
    {
        NetComponent->Connect(ServerAddress, Port);
    }

    // 切换到同步状态（等待服务端下发初始状态和帧数据）
    CurrentState = ELockstepState::Syncing;
    FrameBuffer64.Clear();
    AccumulatedTime = 0.0f;
    CurrentFrameNumber = 0;
    LastProcessedFrameNumber = 0;
    TotalSkippedFrames = 0;

    UE_LOG(LogTemp, Log, TEXT("[Lockstep] Connecting to %s:%d as Player %d"), 
        *ServerAddress, Port, InPlayerId);
}

void ULockstepSubsystem::Disconnect()
{
    CurrentState = ELockstepState::Disconnected;
    
    if (NetComponent)
    {
        NetComponent->Disconnect();
    }

    FrameBuffer64.Clear();
    OnDisconnected.Broadcast();

    UE_LOG(LogTemp, Log, TEXT("[Lockstep] Disconnected."));
}

// ──────────────────────────────────────────────
// 网络帧到达回调（由 LockstepNetComponent 在主线程调用）
// ──────────────────────────────────────────────
void ULockstepSubsystem::OnFrameReceived(const FFrameInputSet& InputSet)
{
    if (!FrameBuffer64.Enqueue(InputSet))
    {
        UE_LOG(LogTemp, Warning, TEXT("[Lockstep] Frame buffer full, dropping frame %u"), 
            InputSet.FrameNumber);
    }
    else if (CurrentState == ELockstepState::Syncing && 
             FrameBuffer64.Count() >= BufferLowThreshold)
    {
        // 缓冲足够，开始执行
        CurrentState = ELockstepState::Running;
        OnConnected.Broadcast();
        UE_LOG(LogTemp, Log, TEXT("[Lockstep] Buffer ready, starting execution at frame %u"),
            CurrentFrameNumber);
    }
}

void ULockstepSubsystem::UpdateRTT()
{
    // RTT 由 NetComponent 的 Ping/Pong 机制维护
    if (NetComponent)
    {
        NetworkRTT = NetComponent->GetEstimatedRTT();
    }
}
```

### 2.4 LockstepNetComponent：UDP 网络层

**文件：LockstepNetComponent.h**

```cpp
// ============================================================
// LockstepNetComponent.h
// 帧同步 UDP 网络组件
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HAL/Runnable.h"
#include "HAL/RunnableThread.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Containers/Queue.h"
#include "FrameCommand.h"
#include "LockstepNetComponent.generated.h"

// 接收帧的回调委托
DECLARE_DELEGATE_OneParam(FOnFrameReceivedDelegate, const FFrameInputSet&);

// 网络包类型标记
namespace ELockstepPacketType
{
    enum Type : uint8
    {
        FrameData   = 1,    // 帧输入数据（服务端广播）
        ClientInput = 2,    // 客户端输入（上行）
        Ping        = 3,    // 保活/延迟测量
        Pong        = 4,    // 保活响应
    };
}

/**
 * 帧同步网络组件
 * 
 * 使用 FUdpSocketBuilder 创建 UDP Socket，收发线程通过 FRunnable 实现。
 * 
 * 线程模型：
 * - 主线程：游戏逻辑线程，从 TQueue 消费收到的帧，将待发送指令写入 TQueue
 * - 接收线程 (FRunnable)：阻塞读取 UDP Socket，反序列化后写入接收队列
 * - 发送线程 (FRunnable)：从发送队列取指令，序列化后写入 UDP Socket
 * 
 * 收发分离的线程设计避免发送阻塞影响接收。
 */
UCLASS(ClassGroup = (Lockstep), meta = (BlueprintSpawnableComponent))
class ULockstepNetComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    ULockstepNetComponent();

    // ── 连接管理 ──
    void Connect(const FString& ServerAddress, int32 Port);
    void Disconnect();
    bool IsConnected() const { return bIsConnected; }

    // ── 发送指令 ──
    void SendCommand(const FFrameCommand& Command);

    // ── 从接收队列刷新帧数据到帧缓冲区（主线程调用） ──
    void FlushReceivedFrames(TCircularBuffer<FFrameInputSet, 64>& OutBuffer);

    // ── 获取估计的 RTT（毫秒） ──
    float GetEstimatedRTT() const { return EstimatedRTT; }

    // ── 帧到达回调 ──
    FOnFrameReceivedDelegate OnFrameReceived;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    // ── 收发包序列化 ──
    static TArray<uint8> SerializeFrameInputSet(const FFrameInputSet& InputSet);
    static TArray<uint8> SerializeClientCommand(const FFrameCommand& Command);
    static bool DeserializeToFrameInputSet(const TArray<uint8>& Data, FFrameInputSet& OutSet);

    // ── 连接状态 ──
    bool bIsConnected = false;
    FString ServerAddr;
    int32 ServerPort = 0;

    // ── UDP Socket ──
    FSocket* UdpSocket = nullptr;
    ISocketSubsystem* SocketSubsystem = nullptr;
    TSharedPtr<FInternetAddr> ServerInternetAddr;

    // ── 收发线程 ──
    class FReceiveThread : public FRunnable
    {
    public:
        FReceiveThread(ULockstepNetComponent* InOwner, FSocket* InSocket);
        virtual bool Init() override;
        virtual uint32 Run() override;
        virtual void Stop() override;
        virtual void Exit() override;

        // 主线程从这里取出收到的帧数据
        TQueue<TArray<uint8>, EQueueMode::Mpsc> ReceivedData;

    private:
        ULockstepNetComponent* Owner;
        FSocket* Socket;
        FRunnableThread* Thread;
        FThreadSafeBool bStopping;
    };

    class FSendThread : public FRunnable
    {
    public:
        FSendThread(ULockstepNetComponent* InOwner, FSocket* InSocket);
        virtual uint32 Run() override;
        virtual void Stop() override;

        // 主线程将待发送数据写入此队列
        TQueue<TArray<uint8>, EQueueMode::Mpsc> PendingSends;

    private:
        ULockstepNetComponent* Owner;
        FSocket* Socket;
        FRunnableThread* Thread;
        FThreadSafeBool bStopping;
    };

    TUniquePtr<FReceiveThread> ReceiveThread;
    TUniquePtr<FSendThread> SendThread;

    // ── RTT 估算 ──
    float EstimatedRTT = 50.0f;
    double LastPingTime = 0.0;
    static constexpr float PingIntervalSec = 1.0f;

    // ── 统计 ──
    uint64 TotalBytesSent = 0;
    uint64 TotalBytesReceived = 0;
    uint64 TotalPacketsDropped = 0;
};
```

**文件：LockstepNetComponent.cpp（关键实现）**

```cpp
// ============================================================
// LockstepNetComponent.cpp
// ============================================================

#include "LockstepNetComponent.h"
#include "HAL/PlatformProcess.h"
#include "Serialization/MemoryWriter.h"
#include "Serialization/MemoryReader.h"

ULockstepNetComponent::ULockstepNetComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    // 帧同步中网络组件不需要 Tick，主线程由 LockstepSubsystem 驱动
    PrimaryComponentTick.bStartWithTickEnabled = false;
}

void ULockstepNetComponent::BeginPlay()
{
    Super::BeginPlay();
}

void ULockstepNetComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    Disconnect();
    Super::EndPlay(EndPlayReason);
}

void ULockstepNetComponent::Connect(const FString& ServerAddress, int32 InPort)
{
    if (bIsConnected) return;

    ServerAddr = ServerAddress;
    ServerPort = InPort;
    SocketSubsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);

    if (!SocketSubsystem)
    {
        UE_LOG(LogTemp, Error, TEXT("[LockstepNet] No socket subsystem available."));
        return;
    }

    // 创建 UDP Socket
    UdpSocket = FUdpSocketBuilder(TEXT("LockstepSocket"))
        .AsNonBlocking()            // 非阻塞模式，线程内 select/poll
        .WithReceiveBufferSize(256 * 1024)   // 256KB 接收缓冲
        .WithSendBufferSize(256 * 1024)      // 256KB 发送缓冲
        .BoundToPort(0)             // 客户端使用 OS 分配的临时端口
        .Build();

    if (!UdpSocket)
    {
        UE_LOG(LogTemp, Error, TEXT("[LockstepNet] Failed to create UDP socket."));
        return;
    }

    // 解析服务器地址
    ServerInternetAddr = SocketSubsystem->CreateInternetAddr();
    bool bIsValid = false;
    ServerInternetAddr->SetIp(*ServerAddress, bIsValid);
    ServerInternetAddr->SetPort(InPort);

    if (!bIsValid)
    {
        UE_LOG(LogTemp, Error, TEXT("[LockstepNet] Invalid server address: %s"), *ServerAddress);
        return;
    }

    // 启动收发线程
    ReceiveThread = MakeUnique<FReceiveThread>(this, UdpSocket);
    SendThread = MakeUnique<FSendThread>(this, UdpSocket);

    bIsConnected = true;
    UE_LOG(LogTemp, Log, TEXT("[LockstepNet] Connected to %s:%d"), *ServerAddress, InPort);
}

void ULockstepNetComponent::Disconnect()
{
    bIsConnected = false;

    // 停止线程（FRunnable::Stop 设置标志；Run 循环检测到后退出）
    ReceiveThread.Reset();
    SendThread.Reset();

    // 关闭 Socket
    if (UdpSocket)
    {
        UdpSocket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(UdpSocket);
        UdpSocket = nullptr;
    }

    UE_LOG(LogTemp, Log, TEXT("[LockstepNet] Disconnected."));
}

void ULockstepNetComponent::SendCommand(const FFrameCommand& Command)
{
    if (!bIsConnected || !SendThread.IsValid()) return;

    TArray<uint8> Serialized = SerializeClientCommand(Command);
    SendThread->PendingSends.Enqueue(MoveTemp(Serialized));
}

void ULockstepNetComponent::FlushReceivedFrames(TCircularBuffer<FFrameInputSet, 64>& OutBuffer)
{
    if (!ReceiveThread.IsValid()) return;

    TArray<uint8> RawData;
    while (ReceiveThread->ReceivedData.Dequeue(RawData))
    {
        FFrameInputSet InputSet;
        if (DeserializeToFrameInputSet(RawData, InputSet))
        {
            OutBuffer.Enqueue(MoveTemp(InputSet));
            OnFrameReceived.ExecuteIfBound(InputSet);
        }
        else
        {
            ++TotalPacketsDropped;
        }
    }
}

// ──────────────────────────────────────────────
// 序列化实现（简化版——生产环境建议使用 Protobuf 或 FlatBuffers）
// ──────────────────────────────────────────────

TArray<uint8> ULockstepNetComponent::SerializeClientCommand(const FFrameCommand& Command)
{
    TArray<uint8> Buffer;
    FMemoryWriter Writer(Buffer);

    uint8 PacketType = ELockstepPacketType::ClientInput;
    Writer << PacketType;
    Writer << Command.FrameNumber;
    Writer << Command.PlayerId;
    Writer << Command.CommandFlags;

    if (Command.HasMove())
    {
        // 移动指令：序列化方向
        uint8 DirByte = static_cast<uint8>(Command.MoveDir);
        Writer << DirByte;
    }
    if (Command.HasSkill())
    {
        Writer << Command.ActionId;
    }
    // ... 其他指令类型的序列化

    return Buffer;
}

bool ULockstepNetComponent::DeserializeToFrameInputSet(const TArray<uint8>& Data, FFrameInputSet& OutSet)
{
    FMemoryReader Reader(Data);

    uint8 PacketType = 0;
    Reader << PacketType;

    if (PacketType != ELockstepPacketType::FrameData)
    {
        return false; // 不是帧数据类型
    }

    // 简化：读出 FrameNumber 和命令数组
    Reader << OutSet.FrameNumber;
    // ... 读取每个玩家的 FFrameCommand

    return true;
}

// ──────────────────────────────────────────────
// FReceiveThread 实现
// ──────────────────────────────────────────────

ULockstepNetComponent::FReceiveThread::FReceiveThread(ULockstepNetComponent* InOwner, FSocket* InSocket)
    : Owner(InOwner), Socket(InSocket), bStopping(false)
{
    Thread = FRunnableThread::Create(this, TEXT("LockstepRecvThread"), 0, TPri_AboveNormal);
}

bool ULockstepNetComponent::FReceiveThread::Init()
{
    return Socket != nullptr;
}

uint32 ULockstepNetComponent::FReceiveThread::Run()
{
    const int32 MaxReadSize = 2048; // 单次最大读取 2KB
    TArray<uint8> ReadBuffer;
    ReadBuffer.SetNumUninitialized(MaxReadSize);

    while (!bStopping)
    {
        int32 BytesRead = 0;
        
        // 非阻塞读取
        bool bReadSuccess = Socket->Recv(
            ReadBuffer.GetData(), 
            MaxReadSize, 
            BytesRead, 
            ESocketReceiveFlags::None
        );

        if (bReadSuccess && BytesRead > 0)
        {
            // 截取实际读取的数据，写入队列
            TArray<uint8> ReceivedPacket;
            ReceivedPacket.Append(ReadBuffer.GetData(), BytesRead);
            ReceivedData.Enqueue(MoveTemp(ReceivedPacket));
        }
        else
        {
            // 无数据到达时短暂休眠，降低 CPU 占用
            FPlatformProcess::Sleep(0.0001f); // 0.1ms
        }
    }

    return 0;
}

void ULockstepNetComponent::FReceiveThread::Stop()
{
    bStopping = true;
    if (Thread)
    {
        Thread->WaitForCompletion();
        delete Thread;
        Thread = nullptr;
    }
}

void ULockstepNetComponent::FReceiveThread::Exit()
{
    // 清理
}

// ──────────────────────────────────────────────
// FSendThread 实现
// ──────────────────────────────────────────────

ULockstepNetComponent::FSendThread::FSendThread(ULockstepNetComponent* InOwner, FSocket* InSocket)
    : Owner(InOwner), Socket(InSocket), bStopping(false)
{
    Thread = FRunnableThread::Create(this, TEXT("LockstepSendThread"), 0, TPri_Normal);
}

uint32 ULockstepNetComponent::FSendThread::Run()
{
    while (!bStopping)
    {
        TArray<uint8> DataToSend;
        if (PendingSends.Dequeue(DataToSend))
        {
            int32 BytesSent = 0;
            // 直接向服务器地址发送
            Socket->SendTo(
                DataToSend.GetData(), 
                DataToSend.Num(), 
                BytesSent, 
                *Owner->ServerInternetAddr
            );
        }
        else
        {
            FPlatformProcess::Sleep(0.0001f);
        }
    }
    return 0;
}

void ULockstepNetComponent::FSendThread::Stop()
{
    bStopping = true;
    if (Thread)
    {
        Thread->WaitForCompletion();
        delete Thread;
        Thread = nullptr;
    }
}
```

### 2.5 LockstepActor：纯逻辑 Actor

**文件：LockstepActor.h**

```cpp
// ============================================================
// LockstepActor.h
// 帧同步逻辑 Actor 基类
// ============================================================

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LockstepActor.generated.h"

/**
 * 帧同步逻辑 Actor 基类
 * 
 * 核心设计规则：
 * 1. 不挂载任何 UMeshComponent（避免渲染依赖）
 * 2. 所有计算使用定点数（TFixed64/Fixed32），不使用 float/double
 * 3. Tick 由 LockstepSubsystem::OnLogicTick 驱动，不使用 AActor::Tick
 * 4. 所有成员变量的修改仅在逻辑帧回调中进行
 * 5. 构造函数中禁用 PrimaryActorTick
 */
UCLASS(Abstract)
class ALockstepActor : public AActor
{
    GENERATED_BODY()

public:
    ALockstepActor();

    // ── 逻辑帧 Tick（由 LockstepSubsystem 调用） ──
    // 子类重写此方法实现自己的逻辑。
    // @param FrameNumber  当前逻辑帧号
    // @param Command      本帧该实体的输入指令
    UFUNCTION()
    virtual void OnLockstepTick(uint32 FrameNumber, const FFrameCommand& Command);

    // ── 实体ID（快速查找） ──
    UPROPERTY(BlueprintReadOnly, Category = "Lockstep")
    uint16 EntityId = 0;

    // ── 所属玩家ID ──
    UPROPERTY(BlueprintReadOnly, Category = "Lockstep")
    uint8 OwnerPlayerId = 0;

    // ── 确定性状态 ──
    
    // 使用定点数表示位置（Q24.8: 24位整数 + 8位小数）
    // int32: ±8,388,607 单位的范围，1/256 的分辨率
    UPROPERTY(BlueprintReadOnly, Category = "Lockstep|State")
    int32 PosX = 0, PosY = 0, PosZ = 0;

    // 朝向（0~65535 映射到 0~2π，16位定点角度）
    UPROPERTY(BlueprintReadOnly, Category = "Lockstep|State")
    uint16 RotationYaw = 0;

    // 血量（定点数：原始值 × 256，如 100HP → 25600）
    UPROPERTY(BlueprintReadOnly, Category = "Lockstep|State")
    int32 Health = 0;

    // 状态机（枚举：Idle/Moving/Attacking/Dead/...）
    UPROPERTY(BlueprintReadOnly, Category = "Lockstep|State")
    uint8 State = 0;

    // ── 表现层查询接口（供表现桥接层使用） ──

    FVector GetVisualLocation() const
    {
        return FVector(
            PosX / 256.0f,
            PosY / 256.0f,
            PosZ / 256.0f
        );
    }

    float GetVisualRotationDegrees() const
    {
        return (float)RotationYaw / 65535.0f * 360.0f;
    }

protected:
    virtual void BeginPlay() override;

    // 辅助：向 LockstepSubsystem 注册自己
    void RegisterWithLockstepSubsystem();
    void UnregisterFromLockstepSubsystem();

private:
    // 指向 LockstepSubsystem 的弱引用
    TWeakObjectPtr<class ULockstepSubsystem> CachedSubsystem;
};
```

**文件：LockstepActor.cpp**

```cpp
// ============================================================
// LockstepActor.cpp
// ============================================================

#include "LockstepActor.h"
#include "LockstepSubsystem.h"
#include "Engine/GameInstance.h"

ALockstepActor::ALockstepActor()
{
    // 关键：禁用 Actor 默认 Tick！逻辑帧由 LockstepSubsystem 驱动
    PrimaryActorTick.bCanEverTick = false;
    PrimaryActorTick.bStartWithTickEnabled = false;

    // 帧同步逻辑 Actor 完全不依赖网络复制
    bReplicates = false;
}

void ALockstepActor::BeginPlay()
{
    Super::BeginPlay();
    RegisterWithLockstepSubsystem();
}

void ALockstepActor::OnLockstepTick(uint32 FrameNumber, const FFrameCommand& Command)
{
    // ── 基类默认实现 ──
    // 子类应重写此方法，实现具体逻辑。
    // 
    // 示例子类实现框架：
    //
    // void AMyHeroActor::OnLockstepTick(uint32 FrameNumber, const FFrameCommand& Command)
    // {
    //     if (Command.HasMove())
    //     {
    //         // 根据方向更新位置（使用定点数运算）
    //         const int32 Speed = 768; // 3.0 单位/帧 (Q24.8: 3.0 × 256 = 768)
    //         PosX += DirectionDeltaX[Command.MoveDir] * Speed;
    //         PosY += DirectionDeltaY[Command.MoveDir] * Speed;
    //     }
    //     if (Command.HasAttack())
    //     {
    //         // 执行攻击判定
    //     }
    // }
}

void ALockstepActor::RegisterWithLockstepSubsystem()
{
    if (UGameInstance* GI = GetGameInstance())
    {
        ULockstepSubsystem* Subsystem = GI->GetSubsystem<ULockstepSubsystem>();
        if (Subsystem)
        {
            CachedSubsystem = Subsystem;
            // 注册 OnLogicTick 回调
            // 注意：实际项目中需要一个 EntityManager 来分发指令，
            // 而不是让每个 Actor 直接注册。
            Subsystem->OnLogicTick.AddDynamic(this, &ALockstepActor::OnLockstepTick);
        }
    }
}

void ALockstepActor::UnregisterFromLockstepSubsystem()
{
    if (CachedSubsystem.IsValid())
    {
        CachedSubsystem->OnLogicTick.RemoveDynamic(this, &ALockstepActor::OnLockstepTick);
    }
}
```

---

## 3. 关键技术深度分析

### 3.1 Unreal 网络架构与帧同步的适配

UE 的网络层由 `UNetDriver` 管理。帧同步客户端必须绕开这套体系。

#### 为什么不能复用 UNetDriver？

| UE 内置网络 | 帧同步需求 | 冲突 |
|------------|-----------|------|
| 面向连接（可靠性优先） | 尽力而为（UDP，延迟优先） | 语义冲突 |
| 自动状态复制 | 只同步输入 | 数据量错误 |
| 服务器权威模型 | 无权威模型（对等执行） | 架构冲突 |
| Tick 与复制管线耦合 | 独立的逻辑 Tick | 时序冲突 |
| `UPROPERTY(Replicated)` 标记 | 无标记，纯手动 | 机制不兼容 |

结论：**帧同步在 UE 中必须使用原始 Socket**，`FUdpSocketBuilder` 是正确的起点。

#### UE5 Iris 对帧同步的影响

UE5 引入的 **Iris** 是下一代复制系统，旨在替代传统的 `UNetDriver` 复制管线。Iris 的核心改进是：

1. **数据驱动**：使用 `FReplicationStateDescriptor` 描述复制状态，自动生成序列化代码
2. **过滤系统**：更精细的 relevancy 和优先级控制
3. **更好的批处理**：按连接聚合数据，减少包头开销

**对帧同步的影响**：几乎为零。Iris 仍然是状态同步系统——它是 UE 内置复制管线的替代品，不是通用网络层。帧同步客户端不会使用 Iris。但 Iris 的存在提醒我们：**引擎的复制系统变得越来越专用化，自定义网络层的价值不会减少**。

### 3.2 GAS (Gameplay Ability System) 与帧同步的融合

GAS 是 UE 的 MMO 级别技能系统，它有两部分：

- **`UAbilitySystemComponent` (ASC)**：管理 GameplayEffect、GameplayTag、AttributeSet
- **`UGameplayAbility`**：技能的逻辑实现

**GAS 在帧同步中的适配挑战**：

GAS 被设计为「技能在服务器上授权执行，通过 GameplayEffect 修改属性，属性通过 ASC 复制到客户端」。这完全是状态同步的思维。

但在帧同步中，我们可以这样使用 GAS：

```cpp
// 帧同步中的 GAS 适配方案
// 
// 方案：保留 GAS 的数据结构（AttributeSet、GameplayEffect），
// 但去掉其网络复制部分，改为由帧同步逻辑驱动。

class ULockstepAbilitySystemComponent : public UAbilitySystemComponent
{
public:
    // 在逻辑帧中执行技能
    void ExecuteAbilityOnLogicFrame(uint32 FrameNumber, uint16 AbilityId, uint16 TargetId)
    {
        // 1. 根据 AbilityId 查找 UGameplayAbility
        // 2. 调用 ActivateAbility，但使用定点数参数
        // 3. GameplayEffect 的计算结果（伤害值等）必须使用定点数
        // 4. 禁止启动任何异步 Task（GAS 的 AbilityTask 依赖 Tick）
    }

    // 定点数版本的属性修改
    void ApplyFixedPointDamage(int32 FixedPointDamage, const FGameplayTagContainer& EffectTags)
    {
        // 使用定点数更新 AttributeSet，而非浮点
    }
};
```

**关键要点**：

- GAS 的 `AbilityTask`（异步任务，如等待动画事件）在帧同步中不可用，因为逻辑帧不使用动画
- `GameplayEffect` 的 `ModifierMagnitudeCalculation` 必须使用确定性公式（无随机数、无系统时间）
- 属性变化（HP/MP 等）不需要复制——每帧由逻辑计算直接得出
- 保留下 GAS 的 `GameplayTag` 系统用于技能互斥和状态管理——它们属于纯逻辑，天然确定

### 3.3 Enhanced Input → FrameCommand 映射

UE5 的 **Enhanced Input System** 非常适合帧同步的输入收集：

```cpp
// 在 PlayerController 或 Pawn 中绑定 Enhanced Input
void ALockstepPlayerController::SetupInputComponent()
{
    Super::SetupInputComponent();

    if (UEnhancedInputComponent* EnhancedInput = Cast<UEnhancedInputComponent>(InputComponent))
    {
        // 移动动作：持续触发（每渲染帧触发一次）
        EnhancedInput->BindAction(MoveAction, ETriggerEvent::Triggered, 
            this, &ALockstepPlayerController::OnMoveTriggered);
        EnhancedInput->BindAction(MoveAction, ETriggerEvent::Completed, 
            this, &ALockstepPlayerController::OnMoveCompleted);

        // 攻击动作：只在按下瞬间触发一次
        EnhancedInput->BindAction(AttackAction, ETriggerEvent::Started, 
            this, &ALockstepPlayerController::OnAttackStarted);

        // 技能动作
        EnhancedInput->BindAction(SkillAction, ETriggerEvent::Started, 
            this, &ALockstepPlayerController::OnSkillStarted);
    }
}

void ALockstepPlayerController::OnMoveTriggered(const FInputActionValue& Value)
{
    // 从 InputActionValue 提取方向
    const FVector2D MoveVector = Value.Get<FVector2D>();
    
    // 将连续方向量化为 8 方向枚举（确定性要求）
    EMoveDirection Dir = QuantizeDirection(MoveVector);

    // 写入输入收集器（不直接发送网络包）
    InputCollector->SetMoveDirection(Dir);
}

void ALockstepPlayerController::OnAttackStarted(const FInputActionValue& Value)
{
    // 攻击是瞬时动作，设置标记
    InputCollector->SetPendingAttack(SelectedTargetId);
}
```

**设计要点**：

- `ETriggerEvent::Triggered`（持续触发）用于移动、转向等持续性操作——输入收集器在每个渲染帧更新方向缓存
- `ETriggerEvent::Started`（按下瞬间）用于技能、攻击等一次性的操作——输入收集器设置「待发送」标记
- 方向量化（8 方向）确保不同设备（键盘、手柄、触屏）产生的输入指令一致
- 输入收集器不区分输入设备来源——键盘 WASD 和手柄左摇杆映射到相同的 `EMoveDirection`

### 3.4 表现层桥接：从逻辑 Actor 到渲染 Actor

这是帧同步中「两个世界」的核心：

```cpp
// ============================================================
// LockstepPresentationActor.h
// 表现层 Actor：负责视觉呈现，无游戏逻辑
// ============================================================

UCLASS()
class ALockstepPresentationActor : public AActor
{
    GENERATED_BODY()

public:
    ALockstepPresentationActor();

    // 绑定到逻辑 Actor
    UFUNCTION(BlueprintCallable)
    void BindToLogicActor(ALockstepActor* LogicActor);

    virtual void Tick(float DeltaTime) override;

protected:
    // 逻辑层数据源（只读）
    UPROPERTY()
    TObjectPtr<ALockstepActor> BoundLogicActor;

    // 渲染组件
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UStaticMeshComponent> MeshComponent;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<USkeletalMeshComponent> SkeletalMeshComponent;

    // 插值用的缓存
    FVector PreviousLogicPosition;
    FVector CurrentLogicPosition;
    FRotator PreviousLogicRotation;
    FRotator CurrentLogicRotation;

    // 收到的最后一次逻辑更新帧号
    uint32 LastReceivedFrameNumber = 0;
};

void ALockstepPresentationActor::BindToLogicActor(ALockstepActor* LogicActor)
{
    BoundLogicActor = LogicActor;
    LastReceivedFrameNumber = 0;
}

void ALockstepPresentationActor::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

    if (!BoundLogicActor.IsValid()) return;

    // ── 检测新逻辑帧 ──
    uint32 CurrentLogicFrame = BoundLogicActor->GetCurrentFrameNumber(); // 假设有此方法
    if (CurrentLogicFrame != LastReceivedFrameNumber)
    {
        // 新的逻辑帧到来 → 更新插值目标
        PreviousLogicPosition = CurrentLogicPosition;
        PreviousLogicRotation = CurrentLogicRotation;

        CurrentLogicPosition = BoundLogicActor->GetVisualLocation();
        CurrentLogicRotation = FRotator(0.0f, BoundLogicActor->GetVisualRotationDegrees(), 0.0f);

        LastReceivedFrameNumber = CurrentLogicFrame;
    }

    // ── 平滑插值 ──
    // 插值因子：根据逻辑帧间隔和渲染帧 DeltaTime 计算
    // 假设逻辑帧间隔 = 66ms，当前渲染帧在逻辑帧中的进度 = t
    float InterpFactor = FMath::Clamp(DeltaTime / 0.0667f, 0.0f, 1.0f);

    FVector InterpolatedPos = FMath::Lerp(PreviousLogicPosition, CurrentLogicPosition, InterpFactor);
    FRotator InterpolatedRot = FMath::Lerp(PreviousLogicRotation, CurrentLogicRotation, InterpFactor);

    // 应用到渲染组件
    SetActorLocation(InterpolatedPos);
    SetActorRotation(InterpolatedRot);

    // 动画状态机由逻辑状态驱动
    if (BoundLogicActor->State == static_cast<uint8>(EUnitState::Moving))
    {
        // 播放走路动画
    }
    else if (BoundLogicActor->State == static_cast<uint8>(EUnitState::Attacking))
    {
        // 播放攻击动画
    }
}
```

**关键规则**：

1. **表现层绝不修改逻辑状态**：`SetActorLocation` 只修改渲染 Actor 的位置，逻辑 Actor 完全不受影响
2. **插值是显示层的技巧，不能作弊**：逻辑层计算命中判定时使用精确的定点数位置，不是插值后的浮点位置
3. **两个 Actor 没有继承关系**：`ALockstepPresentationActor` **不是** `ALockstepActor` 的子类。它们是平级的独立 Actor，通过指针/ID 关联

---

## 4. 常见陷阱

### 陷阱 1：混淆逻辑 Tick 和渲染 Tick

**症状**：将帧同步游戏逻辑写在 `AActor::Tick` 中，或让逻辑 Actor 设置了 `PrimaryActorTick.bCanEverTick = true`。

**根因**：`AActor::Tick` 的 DeltaTime 是可变渲染帧间隔，不是固定逻辑帧间隔。

**解决**：
```cpp
// 正确做法：在 ALockstepActor 构造函数中
PrimaryActorTick.bCanEverTick = false;  // 关闭 Actor Tick！
PrimaryActorTick.bStartWithTickEnabled = false;
```
逻辑帧完全由 `LockstepSubsystem::OnLogicTick` 驱动。如果你看到逻辑层 Actor 的 `Tick` 方法被调用，你已经错了。

### 陷阱 2：在逻辑层使用 UE 的碰撞系统

**症状**：逻辑层 Actor 使用了 `UPrimitiveComponent` 的 `OnComponentHit` 或调用了 `GetWorld()->SweepMultiByChannel()`。

**根因**：UE 的 PhysX/Chaos 物理引擎**不是确定性的**。即使相同的输入，不同平台的物理模拟结果可能不同。

**解决**：
```cpp
// 帧同步中的碰撞检测必须使用自定义的确定性实现：
bool CheckCircleOverlap(int32 X1, int32 Y1, int32 R1, int32 X2, int32 Y2, int32 R2)
{
    // 使用定点数计算距离平方，与半径平方和比较
    // 所有运算使用 64-bit 定点数，完全确定
    int64 dX = (int64)(X1 - X2);
    int64 dY = (int64)(Y1 - Y2);
    int64 DistSq = (dX * dX + dY * dY) >> 8; // Q24.8
    
    int64 RSum = (int64)(R1 + R2);
    int64 RSumSq = (RSum * RSum) >> 8;
    
    return DistSq <= RSumSq;
}
```

### 陷阱 3：在逻辑层使用 UE 的随机数系统

**症状**：逻辑层调用了 `FMath::RandRange()` 或 `FRandomStream`。

**根因**：UE 的 `FMath::Rand()` 基于全局状态，可能与网络帧的顺序耦合导致不同步。

**解决**：使用确定性 PRNG，种子从帧数据中获取：

```cpp
// 确定性随机数生成器（xorshift128+）
class FDeterministicRandom
{
    uint64 State0, State1;

public:
    // 种子必须从帧数据中获取（服务端统一下发）
    void Seed(uint64 S0, uint64 S1) { State0 = S0; State1 = S1; }

    uint64 Next()
    {
        uint64 s1 = State0;
        const uint64 s0 = State1;
        State0 = s0;
        s1 ^= s1 << 23;
        State1 = s1 ^ s0 ^ (s1 >> 18) ^ (s0 >> 5);
        return State1 + s0;
    }

    // 生成 [Min, Max] 范围内的整数
    int32 RandRange(int32 Min, int32 Max)
    {
        return Min + (int32)(Next() % (uint64)(Max - Min + 1));
    }
};
```

### 陷阱 4：在逻辑帧中访问 `UWorld` 或 `UGameInstance`

**症状**：逻辑层 Actor 在 `OnLockstepTick` 中调用了 `GetWorld()->GetTimeSeconds()`。

**根因**：逻辑帧的回调可能在追帧时被快速连续调用（3 倍速追赶），此时 `GetWorld()->GetTimeSeconds()` 返回的是渲染世界的时间，与逻辑帧的时间不对应。

**解决**：逻辑层所需的所有时间/帧信息都应从 `OnLockstepTick` 的参数获取：
```cpp
void AMyHeroActor::OnLockstepTick(uint32 FrameNumber, const FFrameCommand& Command)
{
    // 正确：使用 FrameNumber 推算逻辑时间
    float LogicTime = FrameNumber * LogicFrameInterval;
    
    // 错误：不要用 GetWorld()->GetTimeSeconds()
}
```

### 陷阱 5：使用 `TArray` 的无序迭代

**症状**：逻辑世界中的实体存储在 `TArray` 中，在 `OnLogicTick` 中遍历处理。

**根因**：`TArray` 的遍历顺序在插入/删除后可能变化，导致不同客户端以不同顺序处理实体。

**解决**：总是按 EntityId 排序后再遍历：
```cpp
// 安全模式：收集 ID → 排序 → 按序处理
TArray<uint16> SortedIds;
EntityMap.GetKeys(SortedIds);
SortedIds.Sort(); // 确定性的排序

for (uint16 Id : SortedIds)
{
    EntityMap[Id]->OnLockstepTick(FrameNumber, Command);
}
```

### 陷阱 6：序列化时忽略字节序

**症状**：客户端在 Xbox/PS5（通常 Little-Endian）和移动端（ARM，通常是 Little-Endian 但历史上可变）都能运行，但与服务器交换的数据用了主机字节序。

**根因**：虽然当前主流平台都是 Little-Endian，但帧同步通过网络传输的数据可能经过中转服务器（可能是 Big-Endian 的 Linux/PowerPC 平台）。

**解决**：
```cpp
// 使用 UE 提供的字节序处理宏
#include "Serialization/Archive.h"

// FArchive 默认处理字节序（基于平台的 PLATFORM_LITTLE_ENDIAN 宏）
// 自定义序列化应该使用 FMemoryWriter / FMemoryReader
// 它们自动处理字节序转换

// 如果手写序列化，务必使用：
void SerializeUInt32(uint8* Buffer, uint32 Value)
{
    // 网络字节序 = Big-Endian
    Buffer[0] = (Value >> 24) & 0xFF;
    Buffer[1] = (Value >> 16) & 0xFF;
    Buffer[2] = (Value >> 8) & 0xFF;
    Buffer[3] = Value & 0xFF;
}
```

---

## 5. 练习

### 练习 1：基础——搭建最小帧同步回路（30 min）

**目标**：在 UE5 编辑器内，无需真实服务器，实现一个本地的帧同步模拟回路。

**要求**：
1. 创建 `ULockstepSubsystem` 和 `ULockstepNetComponent` 的 UCLASS 实现
2. 创建一个简单的 `AMyLockstepUnit`（继承自 `ALockstepActor`），在 `OnLockstepTick` 中根据移动指令更新位置
3. 模拟网络层：在 Tick 中直接向 FrameBuffer 写入假的 `FFrameInputSet`（包含一个玩家的移动指令），模拟「从网络收到帧」
4. 使用 `DrawDebugSphere` 在表现层绘制单位位置
5. 验证每次运行结果一致——位置轨迹完全相同

**验证标准**：运行 10 次，使用相同的模拟帧序列，单位最终位置完全相同。

### 练习 2：进阶——帧缓冲与追帧（45 min）

**目标**：实现完整的帧缓冲区和追帧逻辑。

**要求**：
1. 使用 `TCircularBuffer` 模板，创建容量为 8 的帧缓冲区
2. 模拟「网络抖动」：在高频写入时（连续 20 帧快速入队），观察追帧逻辑是否被触发
3. 模拟「网络延迟恢复」：先清空帧输入（模拟断线），然后一口气写入 30 帧，验证 `SkipFrames` 机制是否正确工作
4. 添加统计输出：`UE_LOG` 输出当前缓冲帧数、是否追帧中、跳过的总帧数
5. 当缓冲帧数 < `BufferLowThreshold` 时正常步进，> `BufferHighThreshold` 时加速追赶

**验证标准**：
- 正常时每渲染帧消费 1 个逻辑帧
- 追帧时每渲染帧消费 N 个逻辑帧（N = `CatchUpMultiplier`）
- 缓冲清空后追帧停止

### 练习 3：挑战——逻辑/表现分离（60 min）

**目标**：完整实现逻辑层 Actor 和表现层 Actor 的分离架构。

**要求**：
1. 创建两个 Actor 子类：
   - `ALogicHero`（继承 `ALockstepActor`）——纯逻辑，无 Mesh
   - `AVisualHero`（继承 `AActor`）——纯表现，绑定到 `ALogicHero`
2. `ALogicHero` 实现：
   - 存放定点数位置（int32 PosX, PosY, PosZ，Q24.8 格式）
   - 在 `OnLockstepTick` 中根据 `FFrameCommand` 更新位置
   - 8 方向移动，每逻辑帧移动固定距离（定点数）
3. `AVisualHero` 实现：
   - 挂载 `UStaticMeshComponent`（用一个 Cube 即可）
   - 在 `Tick` 中读取绑定的 `ALogicHero` 的位置，使用 `FMath::Lerp` 平滑
   - 注意：逻辑帧率为 15Hz、渲染帧率为 60Hz，需要 4 个渲染帧完成 1 次逻辑帧间的插值
4. 在关卡中创建 1 个 `AVisualHero` 和 1 个 `ALogicHero`，将二者绑定
5. 模拟 100 帧移动指令，观察视觉上位置是否平滑

**验证标准**：
- 视觉单位移动平滑无抖动
- `ALogicHero` 不包含任何 `UMeshComponent`
- 关闭渲染（PIE 中注释掉 `AVisualHero`）后 `ALogicHero` 的逻辑仍可正常运行（通过日志验证位置更新）

---

## 6. 扩展阅读

### Unreal Engine 相关

1. **UE5 官方文档 - Sockets and Networking**
   - [Using Sockets](https://docs.unrealengine.com/5.0/en-US/sockets-in-unreal-engine/)
   - 理解 `FSocket`、`FUdpSocketBuilder`、`FRunnable` 的完整生命周期

2. **UE5 官方文档 - GameInstanceSubsystem**
   - [UGameInstanceSubsystem](https://docs.unrealengine.com/5.0/en-US/programming-subsystems-in-unreal-engine/)
   - 理解 Subsystem 的生命周期及其与 GameInstance 的关系

3. **UE5 官方文档 - Enhanced Input**
   - [Enhanced Input](https://docs.unrealengine.com/5.0/en-US/enhanced-input-in-unreal-engine/)
   - 理解 InputAction、InputMappingContext、TriggerEvent 体系

4. **UE5 官方文档 - Gameplay Ability System**
   - [GAS Documentation](https://docs.unrealengine.com/5.0/en-US/gameplay-ability-system-for-unreal-engine/)
   - 理解 GAS 在非复制模式下的使用方式

5. **UE5 Iris Replication System**
   - [Iris Overview](https://docs.unrealengine.com/5.4/en-US/iris-replication-system-in-unreal-engine/)
   - 了解 Iris 的架构，理解它为什么仍然是状态复制系统

### 帧同步理论与实践

6. **《1500 Archers on a 28.8: Network Programming in Age of Empires and Beyond》**
   - Mark Terrano & Paul Bettner, GDC 2001
   - 帝国时代系列的帧同步实现，经典必读

7. **《Deterministic Lockstep》- Glenn Fiedler (Gaffer on Games)**
   - [https://gafferongames.com/post/deterministic_lockstep/](https://gafferongames.com/post/deterministic_lockstep/)
   - 帧同步网络模型的清晰介绍

8. **《Networking for Game Programmers》- Building a Lockstep Protocol**
   - [https://gafferongames.com/post/building_a_lockstep_protocol/](https://gafferongames.com/post/building_a_lockstep_protocol/)
   - Lockstep 协议层的具体实现

9. **《王者荣耀技术架构》- 腾讯游戏学院**
   - 王者荣耀的帧同步实现细节（中文）。

### 定点数与确定性

10. **《Fixed Point Arithmetic on the ARM》- ARM 官方应用笔记**
    - ARM 平台上高效的定点数运算实现

11. **Xorshift128+ PRNG 论文**
    - S. Vigna, "Further scramblings of Marsaglia's xorshift generators", 2014
    - 确定性随机数生成的工业标准

---

## 7. 与 Unity/C# 版本的对应关系

如果你同时学习 [08-帧同步客户端实现（Unity/C#）](08-lockstep-client-unity.md)，以下是关键对应：

| Unity/C# | Unreal/C++ | 说明 |
|----------|-----------|------|
| `MonoBehaviour::FixedUpdate` | `LockstepSubsystem` 累积时间 + 固定步长消费 | Unity 有内置固定更新；UE 需要手动实现 |
| `NetworkManager` (自定义) | `ULockstepNetComponent` | 都是自定义 UDP 层 |
| `FrameBuffer<T>` | `TCircularBuffer<T>` | 同是环形缓冲区 |
| `ILogicUnit` 接口 | `ALockstepActor` 基类 | 纯逻辑对象的抽象 |
| `VisualUnit : MonoBehaviour` | `ALockstepPresentationActor : AActor` | 表现层桥接 |
| `InputCollector` | `FFrameInputCollector` | 输入收集和 Bucket 聚合 |
| `DeterministicRandom` | `FDeterministicRandom` | 确定性 PRNG |

**关键差异**：
- Unity 的 `MonoBehaviour` 体系更轻量，帧同步方案更容易「另起炉灶」
- UE 的 `UGameInstanceSubsystem` 提供更清晰的全局生命周期管理
- UE 的多线程（`FRunnable`）比 Unity 的 C# `Thread` + Job System 更底层
- UE 的 Enhanced Input 比 Unity 的 Input System 更适合帧同步的输入收集

---

## 8. 面试要点

> 以下问题在腾讯、网易、米哈游等公司的游戏开发面试中高频出现：

1. **「为什么 UE 的帧同步客户端不能用 UNetDriver？」**
   - 答：UNetDriver 是为状态复制设计的权威服务器模型，而帧同步是对等执行模型。UNetDriver 的自动属性复制、RPC 确认、连接管理等机制与帧同步的「只同步输入指令」冲突。帧同步需要直接控制 UDP Socket 和 Tick 时钟。

2. **「逻辑帧和渲染帧如何分离？在 UE 中如何保证逻辑 Tick 不受渲染帧率影响？」**
   - 答：使用 `UGameInstanceSubsystem` 的 `Tick` 累积 DeltaTime，按固定步长消费逻辑帧（Fixed Timestep 模式）。逻辑层 Actor 的 `AActor::Tick` 必须关闭。追帧时可以在单个渲染帧内消费多个逻辑帧。

3. **「TCircularBuffer 为什么容量必须是 2的幂？如何选择容量？」**
   - 答：2的幂可以使用位掩码 `idx & (Cap - 1)` 替代取模 `idx % Cap`，避免除法指令。容量选择依赖于网络抖动程度：通常 6-10 帧（0.4-0.66 秒 @15Hz）。太小无法应对抖动，太大增加输入延迟。

4. **「如果逻辑帧率为 15Hz，渲染帧率为 60Hz，一个逻辑帧周期内有 4 个渲染帧。这 4 个渲染帧内玩家做了多次操作，如何处理？」**
   - 答：使用 Bucket 机制。每个渲染帧将输入写入 `FFrameInputCollector` 的缓存。Bucket 结束时（每 66ms），缓存中的最终状态被打包成一个 `FFrameCommand` 发送。对于互斥操作（攻击 vs 移动），使用 Last Wins 策略。

5. **「帧同步中如何做断线重连？」**
   - 答：服务端缓存最近的帧输入历史（如最近 300 帧 = 20 秒 @15Hz）。重连客户端请求从断线帧号开始的所有输入数据，客户端在追帧模式下快速消费这些帧（比正常情况下快 3-5 倍），直到赶上下线前的最新帧。
