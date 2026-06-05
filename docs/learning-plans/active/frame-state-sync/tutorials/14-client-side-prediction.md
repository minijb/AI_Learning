---
title: "客户端预测"
updated: 2026-06-05
---

# 客户端预测

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [[13-state-sync-core|13-状态同步核心原理：权威服务器模型]]

---

## 1. 概念讲解

### 1.1 为什么需要客户端预测？

想象你正在玩一款 FPS 游戏。你按下 `W` 键想往前走。

在纯权威服务器模型中，流程是这样的：

```
玩家按W → 客户端发Input包 → ...200ms网络往返... → 服务器收到 → 移动角色 → 发回新位置
                                                                              │
玩家看到角色移动 ← ...100ms... ← 客户端收到 ←────────────────────────────────────┘
```

**按下按键到看到反应：300ms。**

这在单机游戏中完全不可接受。试想一下：
- 你按下前进键，角色要等 300ms 才开始走
- 你按下跳跃，300ms 后角色才跳起来
- 你按下射击，300ms 后枪口才闪光

这个延迟直接决定了一个游戏"能不能玩"。根据大量用户研究数据：

| RTT | 体验描述 | 可玩性 |
|-----|---------|--------|
| <30ms | 感觉不到延迟，和单机一样 | 完美 |
| 30-60ms | 略微有感觉，但不影响操作 | 良好 |
| 60-100ms | 能明显感觉到，需要适应 | 可玩 |
| 100-150ms | 操作有粘滞感，精准操作困难 | 勉强 |
| >150ms | **无预测时完全不可玩** | 不可接受 |

> 注意：上述表格是**无预测**时的体验。有了客户端预测后，即使 RTT 200ms，玩家的即时操作反馈依然可以做到 <16ms（一帧之内）。

**客户端预测的核心洞察**：客户端不等待服务器确认，而是**自己先猜**服务器会怎么处理自己的输入。

```
玩家按W → [立即移动角色！] → 发Input包 → ...200ms... → 服务器确认 → 客户端校验
          ↑                                                              ↓
          └──────── 如果猜错了，回滚修正 ←────────────────────────────┘
```

### 1.2 核心思想

客户端预测建立在两个简单事实上：

1. **客户端对自己的输入有完整信息。** 服务器不知道你什么时候按了 W，但你自己知道。既然你"知道未来服务器也会知道的事"，为什么不等服务器回来再做？

2. **大多数时候你猜得对。** 在没有第三方干扰时，`移动(Input=向前, Pos=100) → 新Pos=105` 这个公式，客户端算出来的和服务器算出来的一模一样。预测错误只发生在"其他人的行为改变了你的预期结果"时——比如有人撞了你的角色、有人在你落点放了个墙。

预测的数学本质：

```
客户端预测位置 = 上一次权威位置 + ∑(本地未确认输入 × 模拟逻辑)

当服务器确认回来时：
  if (服务器计算的位置 == 客户端预测的位置):
      预测正确，无需处理
  else:
      存在误差 → 服务端和解(Reconciliation) → 回滚到服务器位置，重新应用未确认输入
```

```
┌──────────────────────────────────────────────────────────────────────┐
│                        客户端预测架构                                │
│                                                                      │
│  ┌─────────────────────┐         ┌─────────────────────────────┐     │
│  │  客户端本地输入      │         │     服务器权威状态           │     │
│  │  ┌───────────────┐  │         │  ┌───────────────────────┐  │     │
│  │  │ Input Queue   │  │  上行   │  │ Server Sim Tick N     │  │     │
│  │  │ [Cmd@F100,    │──┼───────→│  │ → 处理所有玩家输入    │  │     │
│  │  │  Cmd@F101,    │  │        │  │ → 计算新权威状态      │  │     │
│  │  │  Cmd@F102]    │  │        │  └───────────────────────┘  │     │
│  │  └───────────────┘  │        │              │               │     │
│  │         │           │        │  下行         │               │     │
│  │         ▼           │        │  (含lastProcessedInput帧号) │     │
│  │  ┌───────────────┐  │        │              │               │     │
│  │  │ 本地预测模拟   │  │        │              ▼               │     │
│  │  │ (Run Inputs    │  │        │  ┌───────────────────────┐  │     │
│  │  │  Immediately)  │  │        │  │ 客户端收到权威状态     │  │     │
│  │  └───────────────┘  │        │  │ + lastProcessed=N      │  │     │
│  │         │           │  │        │ └───────────────────────┘  │     │
│  │         ▼           │  │        │              │               │     │
│  │  ┌───────────────┐  │◄────────┼──────────────┘               │     │
│  │  │ Reconciliation│  │        │                                │     │
│  │  │ 比对 & 回滚   │  │        │                                │     │
│  │  └───────────────┘  │        │                                │     │
│  └─────────────────────┘        └─────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. 预测状态管理

这是客户端预测中最核心、也最容易搞错的部分。你必须清楚地跟踪三种状态。

### 2.1 三种状态的精确定义

```
时间线（客户端视角）：

帧号:    ...98    99    100   101   102   103   104   105
         ────────┬─────┬─────┬─────┬─────┬─────┬─────┬──→
                 │     │     │     │     │     │     │
权威状态:  Auth@98   │     │     │  Auth@101         │
                      │     │     │     │     │     │
本地输入:              Cmd99 Cmd100 Cmd101 Cmd102
                      │     │     │     │     │
预测路径:              P99   P100  P101  P102  P103
                            ↑     ↑           ↑
                            基于权威98 + Cmd99+100 推导
                                  ↑
                                  收到Auth@101后重新基于它预测
```

**三种状态：**

| 状态类型 | 来源 | 帧号范围 | 可靠性 | 用途 |
|---------|------|---------|--------|------|
| **Authoritative（权威状态）** | 服务器下发 | ≤ lastAckedFrame | 100%正确 | 基准、校验 |
| **Predicted（预测状态）** | 客户端本地模拟 | lastAckedFrame+1 ~ 当前 | 可能错误 | 即时反馈、显示 |
| **Pending Input（待确认输入）** | 本地采集 | lastAckedFrame+1 ~ 当前 | 已发送未确认 | 重放、校验 |

### 2.2 预测帧号管理

关键数据结构：

```csharp
public class PredictionManager
{
    // === 帧号跟踪 ===
    public uint LocalFrame      { get; private set; }  // 客户端当前帧号（不断递增）
    public uint LastAckedFrame  { get; private set; }  // 服务器最后确认的帧号
    public uint LastSentFrame   { get; private set; }  // 最后发送输入的帧号

    // === 状态存储 ===
    // 保存每帧的权威状态快照，用于回滚
    // Key = 帧号, Value = 该帧执行完后的权威状态
    private Dictionary<uint, Snapshot> _authoritativeSnapshots;

    // 未确认的本地输入（帧号 → 输入）
    private Dictionary<uint, PlayerInput> _pendingInputs;

    // === 预测窗口 ===
    // 预测帧数 = LocalFrame - LastAckedFrame
    public int PendingFrameCount => (int)(LocalFrame - LastAckedFrame);
}
```

**预测帧号的生命周期**：

```
1. 客户端采集输入 → 分配 LocalFrame = N
2. 将输入存入 _pendingInputs[N]
3. 客户端立即基于 _authoritativeSnapshots[lastAcked] + _pendingInputs 模拟出预测状态
4. 输入发送到服务器（带上帧号N）
5. 服务器处理完，下发状态时附带 "lastProcessedInputFrame = N"
6. 客户端收到：确认帧号 N 已被处理
   - 从 _pendingInputs 中移除 ≤N 的输入
   - 更新 LastAckedFrame = N
   - 将服务器下发的状态存入 _authoritativeSnapshots[N]
   - 比对预测状态 vs 权威状态，决定是否需要回滚
```

### 2.3 输入缓冲区设计

输入不能只发不收。客户端需要保存未确认的输入，原因有二：
1. **丢包重发**：如果某个输入包丢了，服务器没收到，客户端需要重发
2. **预测回滚**：当收到服务器状态后，客户端需要用未确认输入重新模拟

```csharp
public class InputBuffer
{
    // 配置
    const int MAX_PENDING_INPUTS = 64;  // 最多存64帧的输入（~1秒@60Hz）

    // 环形缓冲区：按帧号索引
    private PlayerInput[] _inputs = new PlayerInput[MAX_PENDING_INPUTS];
    private uint _baseFrame; // 缓冲区起始帧号

    public void Store(uint frame, PlayerInput input)
    {
        // 确保容量
        if (frame >= _baseFrame + MAX_PENDING_INPUTS)
        {
            // 扩展或丢弃旧帧（说明服务器太久没确认）
            EvictOldFrames(frame - MAX_PENDING_INPUTS + 1);
        }

        int index = (int)(frame % MAX_PENDING_INPUTS);
        _inputs[index] = input;
    }

    public PlayerInput Get(uint frame)
    {
        if (frame < _baseFrame || frame >= _baseFrame + MAX_PENDING_INPUTS)
            return default;

        int index = (int)(frame % MAX_PENDING_INPUTS);
        return _inputs[index];
    }

    // 获取 lastAcked+1 到 current 的所有输入（用于重模拟）
    public List<PlayerInput> GetUnacknowledged(uint fromFrame, uint toFrame)
    {
        var result = new List<PlayerInput>();
        for (uint f = fromFrame; f <= toFrame; f++)
        {
            var input = Get(f);
            if (input.IsValid)
                result.Add(input);
        }
        return result;
    }

    // 服务器确认了某帧 → 清除该帧及之前的所有输入
    public void AcknowledgeUpTo(uint frame)
    {
        for (uint f = _baseFrame; f <= frame; f++)
        {
            int index = (int)(f % MAX_PENDING_INPUTS);
            _inputs[index] = default;
        }
        if (frame >= _baseFrame)
            _baseFrame = frame + 1;
    }

    private void EvictOldFrames(uint newBase)
    {
        for (uint f = _baseFrame; f < newBase; f++)
        {
            int index = (int)(f % MAX_PENDING_INPUTS);
            _inputs[index] = default;
        }
        _baseFrame = newBase;
    }
}
```

---

## 3. 输入预测：移动、跳跃、射击

### 3.1 移动预测

移动是预测最常见的场景。移动的公式在所有客户端和服务器上相同（假设使用相同的物理参数），因此预测**通常正确**。

```csharp
/// <summary>
/// 客户端移动预测
/// 核心原则：客户端立即应用移动输入，维护预测位置
/// 服务器确认到达时，比对并修正
/// </summary>
public class MovementPrediction
{
    // 权威数据（服务器最后确认的状态）
    private Vector3 _authPosition;
    private Vector3 _authVelocity;
    private uint _authFrame;

    // 预测数据（客户端当前显示的位置）
    private Vector3 _predictedPosition;
    private Vector3 _predictedVelocity;

    // 移动参数（必须与服务器一致）
    private float _moveSpeed = 5.0f;
    private float _acceleration = 20.0f;
    private float _friction = 10.0f;

    // 输入缓冲区
    private InputBuffer _inputBuffer;

    /// <summary>
    /// 每帧调用：应用本地输入，立即更新预测位置
    /// </summary>
    public Vector3 UpdatePrediction(uint localFrame, Vector2 moveInput, float deltaTime)
    {
        // 1. 构造输入
        var input = new PlayerInput
        {
            frame = localFrame,
            moveDirection = moveInput,
            actions = 0 // 移动帧暂无其他动作
        };

        // 2. 存入输入缓冲区（用于后续回滚重放）
        _inputBuffer.Store(localFrame, input);

        // 3. 在预测位置上执行移动模拟
        (_predictedPosition, _predictedVelocity) = SimulateMovement(
            _predictedPosition, _predictedVelocity, moveInput, deltaTime);

        return _predictedPosition;
    }

    /// <summary>
    /// 收到服务器权威状态时调用
    /// </summary>
    public Vector3 OnServerStateReceived(ServerState state)
    {
        uint serverFrame = state.frame;
        uint lastProcessedInput = state.lastProcessedInputFrame;

        // 1. 比较预测位置 vs 权威位置
        float error = Vector3.Distance(_predictedPosition, state.playerPosition);

        if (error > 0.01f) // 有显著偏差
        {
            // 2. 回滚：用服务器位置作为新的起点
            _authPosition = state.playerPosition;
            _authVelocity = state.playerVelocity;
            _predictedPosition = _authPosition;
            _predictedVelocity = _authVelocity;
            _authFrame = serverFrame;

            // 3. 重新应用服务器未确认的输入
            var unackedInputs = _inputBuffer.GetUnacknowledged(
                lastProcessedInput + 1, LocalFrame);

            foreach (var input in unackedInputs)
            {
                (_predictedPosition, _predictedVelocity) = SimulateMovement(
                    _predictedPosition, _predictedVelocity,
                    input.moveDirection, FIXED_DELTA_TIME);
            }

            Debug.Log($"[Reconciliation] Error={error:F3}, " +
                      $"Replayed={unackedInputs.Count} inputs, " +
                      $"Final: pred={_predictedPosition}, auth={state.playerPosition}");
        }
        else
        {
            // 预测正确，静默更新权威基准
            _authPosition = state.playerPosition;
            _authVelocity = state.playerVelocity;
            _authFrame = serverFrame;

            // 清除已确认的输入
            _inputBuffer.AcknowledgeUpTo(lastProcessedInput);
        }

        return _predictedPosition;
    }

    /// <summary>
    /// 确定性移动模拟（与服务器完全相同的逻辑）
    /// </summary>
    private (Vector3, Vector3) SimulateMovement(
        Vector3 pos, Vector3 vel, Vector2 input, float dt)
    {
        // 目标速度
        Vector3 targetVelocity = new Vector3(input.x, 0, input.y) * _moveSpeed;

        // 加速/减速平滑过渡
        if (input.magnitude > 0.01f)
        {
            vel = Vector3.MoveTowards(vel, targetVelocity, _acceleration * dt);
        }
        else
        {
            vel = Vector3.MoveTowards(vel, Vector3.zero, _friction * dt);
        }

        // 位置更新
        pos += vel * dt;

        return (pos, vel);
    }
}
```

**关键点总结**：
- 客户端和服务器必须使用**完全相同的**移动参数（速度、加速度、摩擦力）
- 浮点误差通常可接受（状态同步不像帧同步要求绝对确定性），但误差会累积
- 服务器确认到达后，用误差阈值判断是否需要回滚——避免每次微小浮点误差都触发回滚

### 3.2 跳跃预测

跳跃与移动不同：跳跃有**状态切换**（地面→空中），且受**物理引擎**影响。预测跳跃需要处理物理状态。

```csharp
public class JumpPrediction
{
    private bool _predictedIsGrounded = true;
    private bool _authIsGrounded = true;
    private float _jumpForce = 8.0f;
    private float _gravity = 20.0f;

    /// <summary>
    /// 处理跳跃输入
    /// 注意：跳跃必须检查预测的地面状态，而非权威状态
    /// </summary>
    public void PredictJump(uint frame)
    {
        // 检查预测状态下角色是否在地面
        // 不能等服务器确认地面状态——那会引入 RTT 延迟
        if (!_predictedIsGrounded)
            return; // 空中不能跳

        // 立即应用跳跃（预测）
        _predictedVelocity.y = _jumpForce;
        _predictedIsGrounded = false;

        // 存储输入（用于回滚）
        _inputBuffer.Store(frame, new PlayerInput
        {
            frame = frame,
            actions = InputActions.Jump
        });
    }

    /// <summary>
    /// 服务器确认跳跃结果
    /// 注意：服务器可能拒绝跳跃（如反外挂检测到你不在可跳跃状态）
    /// </summary>
    public void OnJumpConfirmed(ServerState state)
    {
        if (!state.isJumping && _predictedIsGrounded == false)
        {
            // 预测错误：服务器拒绝了这个跳跃
            // 原因可能是：实际上角色在地面边缘但服务器判定为空中
            //            或者服务器有特殊逻辑（如被沉默不能跳）
            _predictedPosition.y = state.playerPosition.y;
            _predictedVelocity.y = state.playerVelocity.y;
            _predictedIsGrounded = state.isGrounded;

            // 回滚重放未确认输入
            ReplayUnacknowledgedInputs();
        }
        else
        {
            // 预测正确
            _authIsGrounded = state.isGrounded;
        }
    }
}
```

### 3.3 射击预测

射击涉及两个层面：
1. **即时反馈**：枪口闪光、后坐力动画、音效——应该立即播放
2. **命中判定**：子弹是否打到人——必须服务器说了算

```csharp
public class ShootingPrediction
{
    /// <summary>
    /// 射击时：客户端立即播放特效，服务器做命中判定
    /// 这是"预测特效 + 异步伤害"模型
    /// </summary>
    public void FireWeapon(uint frame, Vector3 aimDirection)
    {
        // === 客户端立即执行（预测） ===

        // 1. 播放枪口闪光（纯视觉，无游戏逻辑影响）
        _muzzleFlash.Play();

        // 2. 播放后坐力动画（纯视觉）
        _weaponAnimator.PlayRecoil();

        // 3. 本地扣除弹药（可预测——客户端知道自己有多少子弹）
        _predictedAmmo--;

        // 4. 创建"临时弹道"视觉效果（射线检测客户端近似的命中点）
        Vector3 predictedHitPoint = PerformLocalRaycast(aimDirection);
        _tracerEffect.Play(_gunMuzzle.position, predictedHitPoint);

        // === 发送到服务器 ===
        SendFireCommand(frame, aimDirection);

        // === 等待服务器确认 ===
        // - 真正的伤害数值由服务器计算后下发
        // - 如果客户端预测的弹药数不对，服务器下发纠正
    }

    /// <summary>
    /// 服务器返回射击结果
    /// </summary>
    public void OnFireResult(ServerFireResult result)
    {
        // 伤害显示：只有服务器确认后才显示
        if (result.hitEntity != 0)
        {
            ShowDamageNumber(result.damage, result.hitEntity);
        }

        // 弹药同步：如果预测的弹药数不对，修正
        if (result.actualAmmo != _predictedAmmo)
        {
            _predictedAmmo = result.actualAmmo;
            // 注意：这里可能出现"弹药回滚"——玩家看到子弹从 5 变成 4，
            // 然后又跳回 5（如果服务器拒绝开火）。这是预测的固有瑕疵。
        }
    }

    private Vector3 PerformLocalRaycast(Vector3 direction)
    {
        // 注意：这是客户端本地射线检测，结果不权威
        // 只用于弹道视觉效果——真正的命中判定在服务器
        if (Physics.Raycast(_gunMuzzle.position, direction, out var hit, 100f))
        {
            return hit.point;
        }
        return _gunMuzzle.position + direction * 100f;
    }
}
```

---

## 4. 多帧预测

### 4.1 为什么客户端会领先服务器多帧？

正常情况下，客户端和服务器以相同频率运行（如 60Hz）。但由于网络延迟，客户端的输入"到达"服务器时，服务器已经推进了若干帧：

```
客户端:  F100  F101  F102  F103  F104  F105  F106  F107
          │     │     │     │     │     │     │     │
输入:     C100  C101  C102  C103  C104  C105  C106  C107
          │     │     │     │     │     │     │     │
          │     │     └──┬──┘     └──┬──┘     └──┬──┘
          │     │        │           │           │
网络:     ▼     ▼        ▼           ▼           ▼
服务器:  F100  F101  F102  F103  F104  F105  F106  ...
          │     │     │     │     │     │     │
收到:          C100  C101  C102  C103  ...

客户端领先:  0帧   1帧   2帧   3帧   4帧  ...  (取决于RTT和Tick Rate)
```

以 60Hz Tick Rate 和 100ms RTT 为例：
- 100ms RTT = 50ms 单向延迟
- 50ms / (1000ms/60) ≈ **3帧领先**
- 客户端在 F103 时，服务器正在处理 F100 的输入

### 4.2 多帧预测的风险

```
领先帧数越多，预测错误概率越高。但输入延迟越低。

┌──────────────────────────────────────────────────────────────┐
│ 领先帧数  │ 输入反馈  │ 错误概率  │       适用场景            │
│───────────│──────────│──────────│──────────────────────────│
│   0-2帧   │  30-50ms │  很低     │ 环境稳定、移动为主         │
│   3-5帧   │  15-30ms │  中等     │ 通用推荐（多数FPS/TPS）     │
│   6-10帧  │  <10ms   │  较高     │ 高RTT网络、竞技需低延迟     │
│   >10帧   │  <5ms    │  很高     │ 格斗游戏（Rollback Netcode）│
└──────────────────────────────────────────────────────────────┘
```

**格斗游戏的极端情况**：GGPO 等 Rollback Netcode 可能领先 **7-8 帧**（~120ms），错误时回滚。这在 FPS 中通常不可行——射击的"回滚"体验很差（你看到打中了，然后服务器说没打中）。

### 4.3 多帧预测的实现

```csharp
/// <summary>
/// 多帧预测管理器
/// 维护一个"预测窗口"：从 lastAcked+1 到 currentFrame
/// </summary>
public class MultiFramePrediction
{
    // 预测状态环形缓冲区
    private struct PredictedFrame
    {
        public uint frame;
        public Vector3 position;
        public Vector3 velocity;
        public bool isGrounded;
        public int hp;
        public int ammo;
        // ... 其他状态字段
    }

    private const int MAX_PREDICTION_WINDOW = 32; // 最多预测32帧
    private PredictedFrame[] _predictionWindow = new PredictedFrame[MAX_PREDICTION_WINDOW];

    // 当前预测基准
    private uint _predictionBaseFrame; // _predictionWindow[0] 对应的帧号

    /// <summary>
    /// 推进预测一帧
    /// </summary>
    public void Tick(uint frame, PlayerInput input)
    {
        // 1. 获取上一个预测状态
        PredictedFrame prev;
        if (frame == _predictionBaseFrame + 1)
        {
            // 正常推进
            prev = GetPredictedFrame(frame - 1);
        }
        else if (frame > _predictionBaseFrame + MAX_PREDICTION_WINDOW)
        {
            // 预测窗口溢出：以权威状态重建
            RebuildFromAuthoritative();
            return;
        }
        else
        {
            // 回滚场景：已处理
            return;
        }

        // 2. 在上一帧基础上模拟
        var predicted = Simulate(prev, input, FIXED_DT);

        // 3. 存储预测状态
        int index = (int)(frame % MAX_PREDICTION_WINDOW);
        _predictionWindow[index] = predicted;
    }

    /// <summary>
    /// 回滚：收到服务器权威状态，重建预测窗口
    /// </summary>
    public void Reconcile(uint serverFrame, ServerState state)
    {
        // 1. 设置新的基准
        int baseIndex = (int)(serverFrame % MAX_PREDICTION_WINDOW);
        _predictionWindow[baseIndex] = new PredictedFrame
        {
            frame = serverFrame,
            position = state.playerPosition,
            velocity = state.playerVelocity,
            isGrounded = state.isGrounded,
            hp = state.hp,
            ammo = state.ammo
        };
        _predictionBaseFrame = serverFrame;

        // 2. 重新应用未确认输入
        var unackedInputs = _inputBuffer.GetUnacknowledged(
            state.lastProcessedInputFrame + 1, _localFrame);

        uint currentFrame = serverFrame;
        var currentState = _predictionWindow[baseIndex];

        foreach (var input in unackedInputs)
        {
            currentFrame++;
            currentState = Simulate(currentState, input, FIXED_DT);

            int idx = (int)(currentFrame % MAX_PREDICTION_WINDOW);
            _predictionWindow[idx] = currentState;
        }
    }

    private PredictedFrame Simulate(PredictedFrame prev, PlayerInput input, float dt)
    {
        // 移动模拟
        Vector3 targetVel = new Vector3(input.moveDirection.x, 0, input.moveDirection.y) * _moveSpeed;
        Vector3 newVel = Vector3.MoveTowards(prev.velocity, targetVel, _acceleration * dt);

        // 跳跃/重力
        if ((input.actions & InputActions.Jump) != 0 && prev.isGrounded)
        {
            newVel.y = _jumpForce;
        }
        else if (!prev.isGrounded)
        {
            newVel.y -= _gravity * dt;
        }

        Vector3 newPos = prev.position + newVel * dt;

        // 地面检测
        bool newGrounded = newPos.y <= 0;
        if (newGrounded) { newPos.y = 0; newVel.y = 0; }

        return new PredictedFrame
        {
            frame = prev.frame + 1,
            position = newPos,
            velocity = newVel,
            isGrounded = newGrounded,
            hp = prev.hp,       // HP 不由预测改变，等服务器确认
            ammo = (input.actions & InputActions.Fire) != 0
                ? prev.ammo - 1 : prev.ammo
        };
    }
}
```

### 4.4 预测窗口截断

当预测错误累积太大时，与其"硬跳"到服务器位置（造成角色瞬移），更好的做法是**平滑修正**：

```csharp
/// <summary>
/// 平滑误差修正：在N帧内逐渐将预测位置拉向权威位置
/// 避免瞬移造成的视觉不适
/// </summary>
public class SmoothCorrection
{
    private Vector3 _correctionOffset; // 需要修正的偏移量
    private float _correctionDuration = 0.1f; // 修正时间（秒）
    private float _correctionTimer;

    public void ApplyCorrection(Vector3 predictedPos, Vector3 authorityPos)
    {
        Vector3 error = authorityPos - predictedPos;
        float errorMag = error.magnitude;

        if (errorMag < 0.01f)
            return; // 误差可忽略

        if (errorMag > 1.0f)
        {
            // 误差太大（>1米），硬切：平滑修正也掩盖不了
            _correctionOffset = error;
            _correctionDuration = 0.0f; // 立即应用
            Debug.LogWarning($"[Correction] Large error {errorMag:F2}m, snap!");
        }
        else
        {
            // 小误差：在0.1秒内平滑修正
            _correctionOffset = error;
            _correctionDuration = 0.1f;
        }
        _correctionTimer = 0;
    }

    public Vector3 GetCorrectedPosition(Vector3 predictedPos, float deltaTime)
    {
        if (_correctionTimer >= _correctionDuration)
            return predictedPos; // 修正已完成

        _correctionTimer += deltaTime;
        float t = _correctionTimer / _correctionDuration;

        // 平滑插值（ease-out）
        float smoothT = 1.0f - Mathf.Pow(1.0f - t, 3.0f);
        Vector3 remainingOffset = _correctionOffset * (1.0f - smoothT);

        return predictedPos + remainingOffset;
    }
}
```

---

## 5. 预测物理：Unity PhysX / UE Chaos

### 5.1 物理引擎预测的挑战

物理引擎（PhysX、Chaos、Bullet、Havok）是客户端预测中最难处理的部分。原因是：

1. **非确定性**：大多数物理引擎的浮点运算不可在不同平台间复现
2. **状态复杂**：碰撞体内部状态（接触点、摩擦约束、sleep 状态）极难序列化
3. **难以回滚**：物理引擎通常不支持"还原到某个历史时刻的状态"
4. **性能消耗**：回滚重放意味着要重新跑物理模拟

### 5.2 策略一：双物理世界（推荐）

维护两个独立的物理世界：
- **权威物理世界**：只由服务器状态驱动，不自主模拟
- **预测物理世界**：用于客户端预测，接收本地输入

```csharp
/// <summary>
/// 双物理世界方案：分离权威和预测
/// </summary>
public class DualPhysicsWorld : MonoBehaviour
{
    // 权威物理场景（只反映服务器确认的状态）
    private PhysicsScene _authoritativeScene;

    // 预测物理场景（用于客户端本地模拟）
    private PhysicsScene _predictionScene;

    // 本地玩家在权威场景中的 GameObject（不可见，仅用于碰撞查询）
    private GameObject _authPlayerProxy;

    // 本地玩家在预测场景中的 GameObject（实际渲染的）
    private GameObject _predictedPlayer;

    void Awake()
    {
        // 创建两个独立的物理场景
        // 注意：需要在 Project Settings → Physics 中允许多场景
        _authoritativeScene = Physics.defaultPhysicsScene;

        // 创建预测物理场景
        var predictionScene = SceneManager.CreateScene("PredictionPhysics",
            new CreateSceneParameters(LocalPhysicsMode.Physics3D));
        _predictionScene = predictionScene.GetPhysicsScene();
    }

    /// <summary>
    /// 模拟一帧预测物理
    /// </summary>
    public void SimulatePredicted(float deltaTime)
    {
        // 在预测场景中运行物理模拟
        _predictionScene.Simulate(deltaTime);

        // 读取预测场景中的位置，渲染
        var body = _predictedPlayer.GetComponent<Rigidbody>();
        transform.position = body.position;
        transform.rotation = body.rotation;
    }

    /// <summary>
    /// 回滚预测：将预测物理世界重置到权威状态
    /// </summary>
    public void RollbackToAuthoritative()
    {
        // 将预测场景中的 Rigidbody 重置到权威状态对应的位置/速度
        var authBody = _authPlayerProxy.GetComponent<Rigidbody>();
        var predBody = _predictedPlayer.GetComponent<Rigidbody>();

        predBody.position = authBody.position;
        predBody.rotation = authBody.rotation;
        predBody.velocity = authBody.velocity;
        predBody.angularVelocity = authBody.angularVelocity;

        // 注意：这里只重置了刚体状态
        // PhysX 内部的碰撞缓存、接触点缓存不会完全一致
        // 这意味着回滚后的预测和服务器物理可能出现微小偏差
    }
}
```

### 5.3 策略二：无物理预测（规避方案）

对大多数 FPS/TPS 游戏，角色控制器（CharacterController）的移动是**运动学**的（kinematic），不依赖物理引擎的碰撞响应。真正需要物理的只是**被推动物体**（箱子、球）。

这种策略下：
- **角色移动**：自己在代码中处理（`Move` + 自定义重力），完全可预测
- **物理物体**：不预测，等服务器状态下发后，用插值渲染

```csharp
/// <summary>
/// 运动学移动预测（不使用物理引擎）
/// 适合 90% 的 FPS/TPS 游戏
/// </summary>
public class KinematicPrediction
{
    // 地面检测用简单的 SphereCast，不依赖物理引擎内部状态
    private bool CheckGrounded(Vector3 position, float radius, float height)
    {
        float halfHeight = height * 0.5f;
        Vector3 origin = position + Vector3.up * 0.1f;
        float castDistance = halfHeight - radius + 0.05f;

        return Physics.SphereCast(origin, radius * 0.9f,
            Vector3.down, out _, castDistance,
            LayerMask.GetMask("Ground"));
    }

    // 移动处理：步进检测（Step Detection）+ 水平滑动
    public Vector3 MoveCharacter(
        Vector3 pos, Vector3 vel, float dt,
        float radius, float height, float stepHeight)
    {
        // 1. 水平移动
        Vector3 horizontalDelta = new Vector3(vel.x, 0, vel.z) * dt;
        pos = SlideHorizontal(pos, horizontalDelta, radius, height);

        // 2. 垂直移动（重力 + 跳跃）
        float verticalDelta = vel.y * dt;
        pos = SlideVertical(pos, verticalDelta, radius, height, stepHeight);

        return pos;
    }

    private Vector3 SlideHorizontal(Vector3 pos, Vector3 delta,
        float radius, float height)
    {
        float halfHeight = height * 0.5f - radius;
        Vector3 topSphere = pos + Vector3.up * halfHeight;
        Vector3 bottomSphere = pos + Vector3.up * radius;

        // CapsuleCast 检测水平碰撞
        if (Physics.CapsuleCast(topSphere, bottomSphere, radius,
            delta.normalized, out var hit, delta.magnitude,
            LayerMask.GetMask("World")))
        {
            // 沿碰撞面滑动
            Vector3 remaining = delta - delta.normalized * hit.distance;
            Vector3 slide = Vector3.ProjectOnPlane(remaining, hit.normal);
            return pos + delta.normalized * hit.distance + slide;
        }

        return pos + delta;
    }
    // ... SlideVertical 类似
}
```

### 5.4 UE Chaos 物理预测

Unreal Engine 的 Chaos 物理系统提供了 `FChaosPhysicsPrediction` 相关接口：

```cpp
// Unreal 5.3+ 的 Chaos 预测支持
// 位于 Engine/Plugins/Runtime/ChaosSolverPlugin

// Chaos 支持两种预测模式：
// 1. 内建预测（Built-in Prediction）：
//    - 通过 UPrimitiveComponent::bPredictClientSimulation 启用
//    - Engine 自动处理回滚和重模拟
//
// 2. 自定义预测（Custom Prediction）：
//    - 使用 FChaosScene::CreateSolver 创建独立求解器
//    - 维护权威和预测两个求解器实例

// === 内建预测示例 ===
void AMyPhysicsActor::BeginPlay()
{
    Super::BeginPlay();

    // 标记该组件需要客户端预测
    if (GetLocalRole() == ROLE_AutonomousProxy)
    {
        StaticMeshComponent->bPredictClientSimulation = true;
        StaticMeshComponent->PredictionLerpTime = 0.1f; // 预测误差平滑时间
    }
}

// === 自定义预测求解器（简化示意）===
class FMyPredictionSolver
{
    // 权威状态
    Chaos::FPBDRigidsSolver* AuthoritySolver;

    // 预测状态（客户端本地）
    Chaos::FPBDRigidsSolver* PredictionSolver;

    void OnServerStateReceived(const FServerState& State)
    {
        // 将权威求解器的状态复制到预测求解器
        CopySolverState(AuthoritySolver, PredictionSolver);

        // 重新应用未确认的输入
        for (const auto& Input : UnackedInputs)
        {
            ApplyInput(PredictionSolver, Input);
            PredictionSolver->AdvanceAndDispatch_External(FixedDt);
        }
    }
};
```

---

## 6. 预测技能/能力：GAS Prediction 详解

### 6.1 GAS 预测架构

Unreal 的 Gameplay Ability System (GAS) 内置了**能力预测**框架。这是业界最成熟的预测实现之一。

```
┌─────────────────────────────────────────────────────────────────┐
│                     GAS 预测流程                                │
│                                                                 │
│  客户端 (Autonomous Proxy)        服务器 (Authority)           │
│  ┌─────────────────────────┐    ┌─────────────────────────┐    │
│  │ 1. TryActivateAbility() │    │                         │    │
│  │    ↓                    │    │                         │    │
│  │ 2. CanActivateAbility() │    │                         │    │
│  │    (CheckTag, Cost, CD) │    │                         │    │
│  │    ↓                    │    │                         │    │
│  │ 3. 生成 PredictionKey ──│──→│ 4. ServerTryActivate()  │    │
│  │    ↓                    │    │    CanActivateAbility() │    │
│  │ 5. ActivateAbility()    │    │    ↓                    │    │
│  │    (本地立即执行)        │    │ 6. ActivateAbility()    │    │
│  │    ↓                    │    │    (服务器权威执行)      │    │
│  │ 7. ApplyGameplayEffect  │    │    ↓                    │    │
│  │    (Predicted GE)       │    │ 8. 下发确认/拒绝        │    │
│  │    ↓                    │    │    ↓                    │    │
│  │ 9. 收到确认 ←───────────│───│ 10. PredictionKey       │    │
│  │    OnRep_PredictionKey  │    │     Replicated          │    │
│  └─────────────────────────┘    └─────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 PredictionKey 机制

`FPredictionKey` 是 GAS 预测的核心令牌。每个预测的能力激活都生成一个唯一 Key，服务器处理后会回传确认。

```cpp
// === GAS 预测能力示例 ===

// .h 文件
UCLASS()
class UGameAbility_FireProjectile : public UGameplayAbility
{
    GENERATED_BODY()

public:
    virtual void ActivateAbility(
        const FGameplayAbilitySpecHandle Handle,
        const FGameplayAbilityActorInfo* ActorInfo,
        const FGameplayAbilityActivationInfo ActivationInfo,
        const FGameplayEventData* TriggerEventData) override;

    // 服务器 RPC
    UFUNCTION(Server, Reliable)
    void ServerFire(const FVector& AimDirection);

protected:
    UPROPERTY(EditDefaultsOnly, Category = "Fire")
    TSubclassOf<class AMyProjectile> ProjectileClass;

    UPROPERTY(EditDefaultsOnly, Category = "Fire")
    float ProjectileSpeed = 3000.0f;

private:
    // 本地预测生成投射物
    void LocalSpawnProjectile(const FVector& AimDir);

    // 客户端收到服务器确认后的回调
    void OnPredictionKeyConfirmed();

    // 客户端收到服务器拒绝后的回调
    void OnPredictionKeyRejected();
};

// .cpp 文件
void UGameAbility_FireProjectile::ActivateAbility(
    const FGameplayAbilitySpecHandle Handle,
    const FGameplayAbilityActorInfo* ActorInfo,
    const FGameplayAbilityActivationInfo ActivationInfo,
    const FGameplayEventData* TriggerEventData)
{
    // === 关键：检查当前 ActivationInfo 的预测状态 ===

    if (IsLocallyControlled())
    {
        // 我们是本地玩家，走预测路径

        // 1. 生成预测 Key（必须！告诉 GAS 这是一次预测激活）
        //    ScopedPredictionKey 在构造时生成 key，析构时结束预测窗口
        FScopedPredictionWindow ScopedPrediction(ActorInfo, CurrentActivationInfo);

        // 2. 本地立即应用预测的 GameplayEffect（如扣蓝）
        //    bIsPredicted = true 是关键
        if (HasAuthority() == false)
        {
            // 客户端预测扣除蓝量
            // 这个 GE 会被标记为 "Predicted" 并加入预测列表
            ApplyCost(Handle, ActorInfo, ActivationInfo);
        }

        // 3. 本地生成投射物（纯预测）
        FVector AimDir = GetAimDirection();
        LocalSpawnProjectile(AimDir);

        // 4. 呼叫服务器
        ServerFire(AimDir);

        // 5. 能力"预测完成"，提交预测
        //    ScopedPredictionWindow 析构时自动调用
        //    CommitAbility(...) 内部
    }
    else if (HasAuthority())
    {
        // 服务器直接执行（不需预测）
        FVector AimDir = GetAimDirection();
        ServerFire_Implementation(AimDir);
    }

    // 注意：预测的能力不应该在这里 EndAbility
    // EndAbility 由服务器确认后 Replicated 的 PredictionKey 触发
}

void UGameAbility_FireProjectile::ServerFire_Implementation(
    const FVector& AimDirection)
{
    // === 服务器权威执行 ===

    // 1. 服务器端再次检查条件（防止作弊！）
    if (!CommitCheck(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo))
    {
        // 拒绝：客户端预测错误
        // GAS 会自动通过 PredictionKey 通知客户端拒绝
        K2_EndAbility(); // 结束能力，会触发 Rejected
        return;
    }

    // 2. 服务器端扣蓝（权威扣除）
    CommitAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo);

    // 3. 生成权威投射物
    FActorSpawnParameters SpawnParams;
    SpawnParams.Owner = GetAvatarActorFromActorInfo();
    SpawnParams.Instigator = GetAvatarActorFromActorInfo();

    AMyProjectile* Projectile = GetWorld()->SpawnActor<AMyProjectile>(
        ProjectileClass,
        GetAvatarActorFromActorInfo()->GetActorLocation(),
        AimDirection.Rotation(),
        SpawnParams);

    if (Projectile)
    {
        Projectile->Initialize(AimDirection, ProjectileSpeed);
    }

    // 4. 能力结束 → GAS 自动 Replicate PredictionKey
    K2_EndAbility();
}

void UGameAbility_FireProjectile::LocalSpawnProjectile(const FVector& AimDir)
{
    // 生成本地预测投射物
    // 注意：这个投射物是临时的！
    // 当服务器确认后，服务器会生成权威投射物并通过 Replication 下发
    // 客户端收到权威投射物后需要"替换"掉本地的预测投射物

    AActor* Avatar = GetAvatarActorFromActorInfo();
    FVector SpawnLoc = Avatar->GetActorLocation();

    FActorSpawnParameters Params;
    Params.Owner = Avatar;
    Params.Instigator = Avatar;
    // 标记为预测 Actor
    Params.bNoFail = true;

    AMyProjectile* LocalProj = GetWorld()->SpawnActor<AMyProjectile>(
        ProjectileClass, SpawnLoc, AimDir.Rotation(), Params);

    if (LocalProj)
    {
        // 标记为预测实例
        LocalProj->bIsPredicted = true;
        LocalProj->Initialize(AimDir, ProjectileSpeed);
    }
}
```

### 6.3 Predicted GameplayEffect

```cpp
// === 预测 GameplayEffect 的关键标记 ===

// 在技能的预测窗口中：
void UMyGameplayAbility::ActivateAbility(...)
{
    // FScopedPredictionWindow 开启预测窗口
    FScopedPredictionWindow PredictionWindow(ActorInfo, CurrentActivationInfo);

    // 在这个窗口内 Apply 的所有 GameplayEffect，
    // 都会被自动标记为 "Predicted"
    //
    // GAS 内部：
    // 1. 客户端 Apply → 存入 PredictedGEs 列表
    // 2. 发送 Server RPC → 服务器也 Apply
    // 3. 服务器确认 → 通过 PredictionKey Replicated 回客户端
    // 4. 客户端收到确认 → 从 PredictedGEs 中移除对应项
    // 5. 如果 PredictionKey Rejected → 回滚所有关联的 PredictedGEs

    UGameplayEffect* CostGE = GetCostGameplayEffect();
    ApplyGameplayEffectToOwner(Handle, ActorInfo, ActivationInfo, CostGE, 1.0f);
    // ↑ 这个 GE 是预测的。若服务器拒绝能力激活，GE 会回滚。
}
```

### 6.4 预测 Key 的复制与回调

```cpp
// === 响应预测确认/拒绝 ===

// 在 Ability 中重写：
void UGameAbility_FireProjectile::OnRep_PredictionKey()
{
    // PredictionKey 被 Replicated 时调用
    // 意味着服务器处理了这个能力激活

    if (CurrentActivationInfo.GetActivationPredictionKey().bIsValidKey)
    {
        if (CurrentActivationInfo.GetActivationPredictionKey().bIsServerInitiated == false)
        {
            // 这是我们客户端发起的预测激活
            // 检查它是被确认还是被拒绝
            if (CurrentActivationInfo.GetActivationPredictionKey().bHasBeenConfirmed)
            {
                OnPredictionKeyConfirmed();
            }
            else if (CurrentActivationInfo.GetActivationPredictionKey().bHasBeenRejected)
            {
                OnPredictionKeyRejected();
            }
        }
    }
}

void UGameAbility_FireProjectile::OnPredictionKeyConfirmed()
{
    // 服务器确认了我们的预测！
    // 本地预测投射物可以保留（或已被服务器权威投射物替换）
    UE_LOG(LogTemp, Log, TEXT("Fire prediction CONFIRMED by server"));
}

void UGameAbility_FireProjectile::OnPredictionKeyRejected()
{
    // 服务器拒绝了我们的预测！
    // 需要回滚：
    // 1. 摧毁本地预测投射物
    // 2. 退还预测扣除的资源（GAS 自动处理 PredictedGE）
    // 3. 恢复冷却（如果有 Cooldown GE，GAS 也自动回滚）
    UE_LOG(LogTemp, Warning, TEXT("Fire prediction REJECTED by server"));

    // GAS 会自动回滚 Predicted GameplayEffects
    // 但本地生成的非 GE 效果（如我们 Spawn 的本地投射物）需要手动清理
    for (auto LocalProj : LocalPredictedProjectiles)
    {
        if (LocalProj.IsValid())
        {
            LocalProj->Destroy();
        }
    }
    LocalPredictedProjectiles.Empty();
}
```

### 6.5 GAS 可预测条件

并非所有 GameplayEffect 都应该被预测。GAS 中只有满足以下条件的 GE 才会被客户端预测执行：

| GE 类型 | 可预测？ | 原因 |
|---------|---------|------|
| **Cost GE**（消耗，如扣蓝） | ✅ 是 | 客户端知道当前蓝量，可以本地扣减 |
| **Cooldown GE**（冷却） | ✅ 是 | 可预测冷却时间 |
| **Damage GE**（伤害） | ❌ 否 | 伤害值由服务器计算（护甲、减伤等） |
| **Healing GE**（治疗） | ❌ 否 | 同理，服务器权威 |
| **Buff/Debuff GE** | ⚠️ 视情况 | 如果 Buff 效果客户端可计算则可预测 |
| **Movement Speed Mod** | ✅ 可以 | 移速修改客户端可安全预测 |

```cpp
// === 标记不可预测的 GE ===
// 在 GameplayEffect 蓝图或定义中：
// - 对于 Damage GE: 不要设置 bIsPredicted = true
// - 服务器 Apply 后通过正常 Replication 下发
// - 客户端收到 OnRep 后更新显示

// 或者，在代码中判断：
void UMyGameplayAbility::ApplyDamageEffect(AActor* Target)
{
    if (IsPredictingClient())
    {
        // 伤害特效/音效可以预测播放
        PlayHitEffect(Target);

        // 但伤害 GE 本身不预测应用
        // 等服务器确认后再应用
        return;
    }

    // 服务器权威应用伤害
    UGameplayEffect* DamageGE = GetDamageGameplayEffect();
    ApplyGameplayEffectToTarget(Handle, ActorInfo, ActivationInfo,
        Target->GetAbilitySystemComponent(), DamageGE, 1.0f);
}
```

---

## 7. 预测中的特效处理

### 7.1 特效分类决策

游戏中的视觉特效有不同的"预测容忍度"：

```
┌──────────────────────────────────────────────────────────────┐
│          特效类型              │ 策略        │ 回滚处理      │
│───────────────────────────────│────────────│──────────────│
│ 枪口闪光、枪焰                │ 立即播放    │ 无需回滚      │
│ 弹道轨迹（Tracer）            │ 立即播放    │ 无需回滚      │
│ 后坐力动画                    │ 立即播放    │ 无需回滚      │
│ ─────────────────────────────│────────────│──────────────│
│ 击中火花（预测命中）          │ 立即播放    │ 若错误则停止  │
│ 击中动画（受击方反馈）        │ 等待确认    │ 不播放        │
│ 伤害数字                      │ 等待确认    │ 不显示        │
│ ─────────────────────────────│────────────│──────────────│
│ 技能释放动画                  │ 立即播放    │ 若拒绝则打断  │
│ 技能范围指示器（AOE圈）       │ 立即播放    │ 若拒绝则取消  │
│ 技能投射物（持续影响游戏逻辑） │ 立即生成    │ 若拒绝则销毁  │
│ 技能命中判定特效              │ 等待确认    │ 不播放        │
└──────────────────────────────────────────────────────────────┘
```

### 7.2 实现：特效管理器

```csharp
/// <summary>
/// 特效生命周期管理器
/// 区分"瞬态特效"（立即播放，不可撤回）和"确认特效"（等服务器确认）
/// </summary>
public class EffectPredictionManager : MonoBehaviour
{
    // === 瞬态特效池（立即播放，不管服务器是否确认）===
    // 特点：播放完就完了，没有"回滚"概念
    // 例如：枪口闪光、后坐力、脚步声

    public void PlayTransientEffect(EffectType type)
    {
        switch (type)
        {
            case EffectType.MuzzleFlash:
                // 枪口闪光只持续 0.05s，完全播放完时服务器还没回包
                // 即使服务器拒绝了这次射击，闪光已经播完了，玩家根本注意不到
                Instantiate(_muzzleFlashPrefab, _gunMuzzle).SetLifetime(0.05f);
                break;

            case EffectType.RecoilAnimation:
                // 后坐力动画：立即播放
                // 如果服务器拒绝开火（极少情况），动画已播完
                _weaponAnimator.Play("Recoil");
                break;

            case EffectType.Footstep:
                // 脚步声：立即播放
                _audioSource.PlayOneShot(_footstepSound);
                break;
        }
    }

    // === 预测特效（立即播放，但服务器拒绝时可以中断/移除）===
    private Dictionary<uint, GameObject> _predictedEffects = new();

    public uint PlayPredictedEffect(EffectType type, Vector3 position)
    {
        uint effectId = GenerateEffectId();

        GameObject effect = null;
        switch (type)
        {
            case EffectType.HitSpark:
                effect = Instantiate(_hitSparkPrefab, position, Quaternion.identity);
                break;

            case EffectType.Projectile:
                effect = Instantiate(_projectilePrefab, position, Quaternion.identity);
                // 标记为预测实例
                effect.GetComponent<Projectile>().IsPredicted = true;
                break;

            case EffectType.AbilityCast:
                effect = Instantiate(_abilityCastPrefab, position, Quaternion.identity);
                break;
        }

        if (effect != null)
        {
            _predictedEffects[effectId] = effect;
        }
        return effectId;
    }

    /// <summary>
    /// 服务器确认：特效可以安全保留
    /// </summary>
    public void ConfirmEffect(uint effectId)
    {
        if (_predictedEffects.TryGetValue(effectId, out var effect))
        {
            // 标记为已确认，不再受回滚影响
            if (effect.TryGetComponent<Projectile>(out var proj))
            {
                proj.IsPredicted = false;
            }
            _predictedEffects.Remove(effectId);
        }
    }

    /// <summary>
    /// 服务器拒绝：需要清理预测特效
    /// </summary>
    public void RejectEffect(uint effectId, EffectType type)
    {
        if (_predictedEffects.TryGetValue(effectId, out var effect))
        {
            switch (type)
            {
                case EffectType.Projectile:
                    // 投射物：平滑消失（小型爆炸或淡出）
                    StartCoroutine(SmoothDestroy(effect, 0.15f));
                    break;

                case EffectType.AbilityCast:
                    // 技能释放：立即打断
                    Destroy(effect);
                    break;

                case EffectType.HitSpark:
                    // 火花：停止粒子系统
                    if (effect.TryGetComponent<ParticleSystem>(out var ps))
                    {
                        ps.Stop(true, ParticleSystemStopBehavior.StopEmitting);
                    }
                    Destroy(effect, 0.5f); // 让已生成的粒子自然消亡
                    break;
            }
            _predictedEffects.Remove(effectId);
        }
    }

    // === 确认特效（只等服务器确认后再播放）===
    public void PlayConfirmedEffect(EffectType type, Vector3 position, int damage)
    {
        switch (type)
        {
            case EffectType.DamageNumber:
                // 伤害数字：只在服务器确认伤害值后才显示
                var dmgText = Instantiate(_damageNumberPrefab, position, Quaternion.identity);
                dmgText.GetComponent<DamageNumber>().SetDamage(damage);
                break;

            case EffectType.KillEffect:
                // 击杀特效：必须是服务器确认击杀
                Instantiate(_killEffectPrefab, position, Quaternion.identity);
                break;

            case EffectType.HitAnimation:
                // 受击动画：必须是服务器确认命中
                // 防止"我预测打中了→播了受击动画→服务器说没打中"的尴尬
                break;
        }
    }

    private IEnumerator SmoothDestroy(GameObject obj, float duration)
    {
        // 缩放消失
        float timer = 0;
        Vector3 originalScale = obj.transform.localScale;
        while (timer < duration)
        {
            timer += Time.deltaTime;
            float t = timer / duration;
            obj.transform.localScale = Vector3.Lerp(originalScale, Vector3.zero, t);
            yield return null;
        }
        Destroy(obj);
    }
}
```

### 7.3 特效回滚的用户体验

特效回滚是最容易让玩家感知到"延迟"的地方。几种常见处理策略：

```
场景：玩家开枪，客户端判定命中敌人，播放了击中特效。
      服务器随后说："没打中"。

策略 A（硬回滚）：立即移除特效
  → 用户体验：看到火花闪了一下然后消失，感觉很假

策略 B（忽略）：保留特效，不显示伤害数字
  → 用户体验：有火花但没伤害数字，玩家可能会疑惑但不会太在意
  → 推荐用于火花等"非关键"特效

策略 C（延迟播放）：完全不预测击中特效
  → 用户体验：开枪后 100ms 才看到火花，操作延迟感明显
  → 仅用于极关键的特效（如击杀确认）

策略 D（概率忽略）：预测命中 → 播放特效；服务器拒绝 → 保留特效 0.2s 再淡出
  → 用户体验：如果很快收到拒绝，特效自然淡去
  → 如果 RTT 很低（<30ms），拒绝可能在特效自然结束前到达
```

**推荐**：音效、枪口闪光、弹道等纯客户端视觉 → 无条件立即播放。击中火花 → 立即播放，服务器拒绝时忽略。伤害数字、击杀确认 → 严格等服务器确认。

---

## 8. 代码示例

### 8.1 Unity C# 完整客户端预测系统 (~250行)

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 完整的客户端预测系统
///
/// 设置说明：
/// 1. 将此脚本挂载到本地玩家 GameObject 上
/// 2. 确保服务器以固定 Tick Rate 运行（如60Hz）
/// 3. 客户端和服务器使用相同的移动参数
/// 4. 输入通过 NetworkManager 发送，状态通过 OnServerState 接收
///
/// 架构：
///   ClientPredictionSystem
///   ├── InputBuffer          — 未确认输入存储
///   ├── MovementPrediction   — 移动预测
///   ├── JumpPrediction       — 跳跃预测
///   └── EffectPredictionManager — 特效处理（上一节已实现）
/// </summary>
public class ClientPredictionSystem : MonoBehaviour
{
    // ========== 配置 ==========
    [Header("Tick Settings")]
    [SerializeField] private int _tickRate = 60;
    [SerializeField] private float _reconciliationThreshold = 0.05f; // 5cm 误差触发回滚
    [SerializeField] private float _maxPredictedFrames = 16; // 最多预测16帧

    [Header("Movement")]
    [SerializeField] private float _moveSpeed = 6.0f;
    [SerializeField] private float _acceleration = 50.0f;
    [SerializeField] private float _friction = 15.0f;
    [SerializeField] private float _jumpForce = 8.0f;
    [SerializeField] private float _gravity = 25.0f;

    [Header("Character")]
    [SerializeField] private CharacterController _characterController;
    [SerializeField] private float _characterRadius = 0.3f;
    [SerializeField] private float _characterHeight = 1.8f;
    [SerializeField] private float _stepHeight = 0.3f;

    // ========== 状态 ==========
    // 帧号
    private uint _localFrame = 0;
    private uint _lastAckedFrame = 0;

    // 权威状态（服务器最后确认的）
    private struct AuthoritativeState
    {
        public uint frame;
        public Vector3 position;
        public Vector3 velocity;
        public bool isGrounded;
        public Quaternion rotation;

        public static AuthoritativeState FromServer(
            uint frame, Vector3 pos, Vector3 vel, bool grounded, Quaternion rot)
        {
            return new AuthoritativeState
            {
                frame = frame, position = pos,
                velocity = vel, isGrounded = grounded, rotation = rot
            };
        }
    }

    private AuthoritativeState _latestAuthState;

    // 预测状态（当前显示的位置）
    private Vector3 _predictedPosition;
    private Vector3 _predictedVelocity;
    private bool _predictedGrounded;

    // 平滑修正
    private Vector3 _correctionOffset;
    private float _correctionRemaining;

    // 输入缓冲
    private readonly InputBuffer _inputBuffer = new InputBuffer();

    // 本地输入（由外部每帧设置）
    [HideInInspector] public Vector2 MoveInput;
    [HideInInspector] public bool JumpPressed;
    [HideInInspector] public bool FirePressed;

    // ========== 初始化 ==========
    void Start()
    {
        // 初始状态：假设服务器已经确认了帧0
        _predictedPosition = transform.position;
        _predictedVelocity = Vector3.zero;
        _predictedGrounded = true;
        _latestAuthState = AuthoritativeState.FromServer(
            0, transform.position, Vector3.zero, true, transform.rotation);

        // 注意：不需要 CharacterController.Move() 每帧被 Unity 调用
        // CharacterController 在这里只用于碰撞检测（我们不使用它内置的运动）
        if (_characterController != null)
            _characterController.enabled = false;
    }

    // ========== 主循环 ==========
    void FixedUpdate()
    {
        // 确保以固定频率运行
        // 如果 Unity 的 FixedUpdate 频率不等于 _tickRate，用自己的 timer
        // 这里简化：假设 FixedUpdate = _tickRate

        float dt = Time.fixedDeltaTime;
        _localFrame++;

        // 1. 采集输入
        var input = new PlayerInput
        {
            frame = _localFrame,
            moveDirection = MoveInput,
            actions = 0
        };
        if (JumpPressed) input.actions |= InputActions.Jump;
        if (FirePressed) input.actions |= InputActions.Fire;
        JumpPressed = false;
        FirePressed = false;

        // 2. 本地预测模拟
        PredictStep(input, dt);

        // 3. 发送输入到服务器
        SendInputToServer(input);

        // 4. 应用平滑修正
        ApplySmoothCorrection(dt);

        // 5. 更新 Transform（渲染用）
        transform.position = _predictedPosition + _correctionOffset;
    }

    // ========== 预测模拟 ==========
    private void PredictStep(PlayerInput input, float dt)
    {
        // 存储输入（用于回滚）
        _inputBuffer.Store(_localFrame, input);

        // 移动模拟
        (_predictedPosition, _predictedVelocity, _predictedGrounded) =
            SimulateMovement(
                _predictedPosition,
                _predictedVelocity,
                _predictedGrounded,
                input,
                dt);
    }

    private (Vector3 pos, Vector3 vel, bool grounded) SimulateMovement(
        Vector3 pos, Vector3 vel, bool grounded,
        PlayerInput input, float dt)
    {
        // 水平移动
        Vector2 moveInput = input.moveDirection;
        Vector3 wishDir = new Vector3(moveInput.x, 0, moveInput.y);

        // 加速/摩擦
        if (wishDir.magnitude > 0.01f)
        {
            Vector3 targetVel = wishDir.normalized * _moveSpeed;
            vel.x = Mathf.MoveTowards(vel.x, targetVel.x, _acceleration * dt);
            vel.z = Mathf.MoveTowards(vel.z, targetVel.z, _acceleration * dt);
        }
        else
        {
            vel.x = Mathf.MoveTowards(vel.x, 0, _friction * dt);
            vel.z = Mathf.MoveTowards(vel.z, 0, _friction * dt);
        }

        // 跳跃
        if ((input.actions & InputActions.Jump) != 0 && grounded)
        {
            vel.y = _jumpForce;
            grounded = false;
        }

        // 重力
        if (!grounded)
        {
            vel.y -= _gravity * dt;
        }

        // 位置更新（使用简单碰撞检测）
        Vector3 delta = vel * dt;
        pos = MoveWithCollision(pos, delta, grounded);

        // 地面检测
        if (!grounded && pos.y <= 0)
        {
            pos.y = 0;
            vel.y = 0;
            grounded = true;
        }

        return (pos, vel, grounded);
    }

    private Vector3 MoveWithCollision(Vector3 pos, Vector3 delta, bool grounded)
    {
        // 使用 SphereCast 或 CapsuleCast 进行水平碰撞检测
        float castRadius = _characterRadius * 0.9f;
        float castHeight = _characterHeight - castRadius * 2;
        Vector3 p1 = pos + Vector3.up * castRadius;
        Vector3 p2 = pos + Vector3.up * (castRadius + castHeight);

        // 水平碰撞
        Vector3 horizontalDelta = new Vector3(delta.x, 0, delta.z);
        if (horizontalDelta.magnitude > 0.001f)
        {
            if (Physics.CapsuleCast(p1, p2, castRadius,
                horizontalDelta.normalized, out var hit,
                horizontalDelta.magnitude,
                LayerMask.GetMask("World", "Default")))
            {
                // 沿法线滑动
                pos += horizontalDelta.normalized * (hit.distance - 0.01f);
                Vector3 remaining = horizontalDelta -
                    horizontalDelta.normalized * hit.distance;
                Vector3 slide = Vector3.ProjectOnPlane(remaining, hit.normal);
                pos += slide;
            }
            else
            {
                pos += horizontalDelta;
            }
        }

        // 垂直移动
        pos.y += delta.y;

        return pos;
    }

    // ========== 服务端和解 ==========
    /// <summary>
    /// 收到服务器状态更新时调用
    /// </summary>
    public void OnServerStateReceived(ServerPlayerState state)
    {
        uint serverFrame = state.frame;
        uint lastProcessedInput = state.lastProcessedInputFrame;

        // 更新权威基准
        _latestAuthState = AuthoritativeState.FromServer(
            serverFrame, state.position, state.velocity,
            state.isGrounded, state.rotation);

        // 计算预测误差
        Vector3 predictedAtServerFrame = GetPredictedPositionAtFrame(serverFrame);
        float error = Vector3.Distance(predictedAtServerFrame, state.position);

        if (error > _reconciliationThreshold)
        {
            // 需要回滚
            Debug.Log($"[Prediction] Error {error:F3}m at frame {serverFrame}, " +
                      $"rolling back...");

            // 1. 重置预测基准到权威状态
            _predictedPosition = state.position;
            _predictedVelocity = state.velocity;
            _predictedGrounded = state.isGrounded;

            // 2. 清除已确认的输入
            _inputBuffer.AcknowledgeUpTo(lastProcessedInput);

            // 3. 重新应用未确认的输入
            var unackedInputs = _inputBuffer.GetUnacknowledged(
                lastProcessedInput + 1, _localFrame - 1);

            foreach (var input in unackedInputs)
            {
                (_predictedPosition, _predictedVelocity, _predictedGrounded) =
                    SimulateMovement(
                        _predictedPosition,
                        _predictedVelocity,
                        _predictedGrounded,
                        input,
                        Time.fixedDeltaTime);
            }

            // 4. 记录修正偏移（用于平滑过渡）
            _correctionOffset = Vector3.zero;

            _lastAckedFrame = lastProcessedInput;
        }
        else
        {
            // 预测正确
            _lastAckedFrame = lastProcessedInput;
            _inputBuffer.AcknowledgeUpTo(lastProcessedInput);
        }
    }

    private Vector3 GetPredictedPositionAtFrame(uint frame)
    {
        // 简化实现：如果 frame 在预测范围内，从预测窗口查找
        // 完整实现需要存储每帧的预测位置
        if (frame <= _lastAckedFrame)
            return _latestAuthState.position;

        // 估算：从权威位置开始，逐步模拟到目标帧
        // 实际项目中应缓存预测历史
        return _predictedPosition;
    }

    private void ApplySmoothCorrection(float dt)
    {
        if (_correctionRemaining > 0)
        {
            _correctionRemaining -= dt;
            if (_correctionRemaining <= 0)
            {
                _correctionOffset = Vector3.zero;
            }
        }
    }

    // ========== 输入发送 ==========
    private void SendInputToServer(PlayerInput input)
    {
        // 通过你的网络层发送
        // 简化示例：
        // NetworkManager.Instance.SendReliable(new InputPacket
        // {
        //     frame = input.frame,
        //     moveX = input.moveDirection.x,
        //     moveY = input.moveDirection.y,
        //     actions = input.actions
        // });

        // 在真实项目中，不能每帧都发可靠消息（带宽浪费）
        // 应使用不可靠通道 + 序列号来支持去重和丢包检测
    }
}

// ========== 数据结构 ==========

[System.Flags]
public enum InputActions : byte
{
    None  = 0,
    Jump  = 1 << 0,
    Fire  = 1 << 1,
    Reload = 1 << 2,
    Ability1 = 1 << 3,
    Ability2 = 1 << 4,
}

public struct PlayerInput
{
    public uint frame;
    public Vector2 moveDirection;
    public InputActions actions;

    public bool IsValid => frame > 0;
}

// 服务器下发的玩家状态
public struct ServerPlayerState
{
    public uint frame;
    public uint lastProcessedInputFrame; // 服务器最后处理的客户端输入帧号
    public Vector3 position;
    public Vector3 velocity;
    public Quaternion rotation;
    public bool isGrounded;
    public int hp;
    public int ammo;
}

/// <summary>
/// 输入环形缓冲区
/// </summary>
public class InputBuffer
{
    private const int MAX_PENDING = 1024;
    private PlayerInput[] _inputs = new PlayerInput[MAX_PENDING];
    private uint _baseFrame;

    public void Store(uint frame, PlayerInput input)
    {
        if (frame >= _baseFrame + MAX_PENDING)
        {
            EvictOldFrames(frame - MAX_PENDING / 2);
        }
        _inputs[frame % MAX_PENDING] = input;
    }

    public PlayerInput Get(uint frame)
    {
        if (frame < _baseFrame || frame >= _baseFrame + MAX_PENDING)
            return default;
        return _inputs[frame % MAX_PENDING];
    }

    public void AcknowledgeUpTo(uint frame)
    {
        for (uint f = _baseFrame; f <= frame && f < _baseFrame + MAX_PENDING; f++)
        {
            _inputs[f % MAX_PENDING] = default;
        }
        if (frame >= _baseFrame)
            _baseFrame = frame + 1;
    }

    public List<PlayerInput> GetUnacknowledged(uint from, uint to)
    {
        var result = new List<PlayerInput>();
        uint start = Mathf.Max(from, _baseFrame);
        for (uint f = start; f <= to && f < _baseFrame + MAX_PENDING; f++)
        {
            var input = _inputs[f % MAX_PENDING];
            if (input.IsValid)
                result.Add(input);
        }
        return result;
    }

    private void EvictOldFrames(uint newBase)
    {
        for (uint f = _baseFrame; f < newBase; f++)
        {
            _inputs[f % MAX_PENDING] = default;
        }
        _baseFrame = newBase;
    }
}
```

### 8.2 Unreal C++ 基于GAS的预测实现

（上文第 6 节已覆盖 GAS 核心预测逻辑，此处补充运动组件预测）

```cpp
// ========== UMyMovementComponent.h ==========
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "MyMovementComponent.generated.h"

/**
 * 支持客户端预测的角色移动组件
 *
 * 关键设计：
 * - 客户端(AutonomousProxy)本地预测移动
 * - 服务器保存 SavedMoves，用于校验客户端发送的移动序列
 * - 客户端也保存 PendingMoves，用于回滚重放
 * - 使用 FSavedMove_MyCharacter 存储每帧移动的完整快照
 */
UCLASS()
class UMyMovementComponent : public UCharacterMovementComponent
{
    GENERATED_BODY()

public:
    UMyMovementComponent();

    // === 客户端预测 ===
    // 服务器收到客户端移动时调用
    virtual void ServerMove_PerformMovement(const FCharacterNetworkMoveData& MoveData) override;

    // 客户端收到服务器确认后调用
    virtual void ClientAckGoodMove_Implementation(float TimeStamp) override;

    // 客户端移动修正（预测错误时）
    virtual void ClientAdjustPosition_Implementation(
        float TimeStamp,
        FVector NewLocation,
        FVector NewVelocity,
        UPrimitiveComponent* NewBase,
        FName NewBaseBoneName,
        bool bHasBase,
        bool bBaseRelativePosition,
        uint8 ServerMovementMode) override;

protected:
    // 每帧执行移动（客户端本地预测核心）
    virtual void PerformMovement(float DeltaTime) override;

    // 创建 SavedMove 实例
    virtual FNetworkPredictionData_Client* GetPredictionData_Client() const override;
};

// ========== FSavedMove_MyCharacter (SavedMove) ==========
/**
 * SavedMove 存储一帧的移动快照
 * UCharacterMovementComponent 使用 FSavedMove_Character 在客户端和服务器间同步移动
 * 扩展它来存储自定义状态
 */
class FSavedMove_MyCharacter : public FSavedMove_Character
{
public:
    // 自定义移动数据
    uint8 SavedCustomMovementFlags;
    float SavedStamina; // 例如：存储耐力值用于预测回滚

    // 清除：重置为新帧
    virtual void Clear() override
    {
        FSavedMove_Character::Clear();
        SavedCustomMovementFlags = 0;
        SavedStamina = 0;
    }

    // 设置初始状态：从当前角色的状态快照
    virtual void SetInitialPosition(ACharacter* C) override
    {
        FSavedMove_Character::SetInitialPosition(C);

        if (auto* MyChar = Cast<AMyCharacter>(C))
        {
            SavedStamina = MyChar->GetStamina();
        }
    }

    // 将 SavedMove 应用到角色（用于预测回滚）
    virtual void PrepMoveFor(ACharacter* C) override
    {
        FSavedMove_Character::PrepMoveFor(C);

        if (auto* MyChar = Cast<AMyCharacter>(C))
        {
            // 恢复耐力到这一帧的状态
            MyChar->SetStamina(SavedStamina);
        }
    }

    // 判断两个 SavedMove 是否可以合并（连续相同输入时压缩）
    virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InPawn, float MaxDelta) const override
    {
        // 如果关键状态不同，不能合并
        if (SavedCustomMovementFlags !=
            ((FSavedMove_MyCharacter*)&NewMove)->SavedCustomMovementFlags)
        {
            return false;
        }

        return FSavedMove_Character::CanCombineWith(NewMove, InPawn, MaxDelta);
    }

    // 合并两个 SavedMove（用于输入压缩）
    virtual void CombineWith(const FSavedMove_Character* OldMove, ACharacter* InPawn,
        APlayerController* PC, const FVector& OldRelativeLocation) override
    {
        FSavedMove_Character::CombineWith(OldMove, InPawn, PC, OldRelativeLocation);
    }
};

// ========== UMyMovementComponent.cpp ==========
#include "MyMovementComponent.h"
#include "GameFramework/Character.h"

UMyMovementComponent::UMyMovementComponent()
{
    // 启用网络平滑修正
    bNetworkSmoothingComplete = false; // 让预测回滚即时生效
    NetworkSmoothingMode = ENetworkSmoothingMode::Disabled; // 自定义修正逻辑
}

void UMyMovementComponent::PerformMovement(float DeltaTime)
{
    if (GetOwnerRole() == ROLE_AutonomousProxy)
    {
        // === 客户端预测模式 ===
        // 1. 本地立即执行移动
        Super::PerformMovement(DeltaTime);

        // 2. 保存这一帧的移动到 SavedMoves（用于回滚）
        //    UCharacterMovementComponent 内部自动处理
    }
    else if (GetOwnerRole() == ROLE_Authority)
    {
        // === 服务器权威模式 ===
        // 服务器端校验：比较客户端发送的移动序列 vs 服务器自己的模拟
        Super::PerformMovement(DeltaTime);
    }
}

void UMyMovementComponent::ServerMove_PerformMovement(
    const FCharacterNetworkMoveData& MoveData)
{
    // 服务器执行客户端发送的移动
    // 这是"权威模拟"——如果客户端预测错误，这里产生的位置才是正确的

    // 使用服务器物理环境执行移动
    Super::ServerMove_PerformMovement(MoveData);

    // 额外的服务器端校验（防加速挂）
    ACharacter* Owner = GetCharacterOwner();
    if (Owner)
    {
        float CurrentSpeed = Owner->GetVelocity().Size();
        float MaxAllowedSpeed = GetMaxSpeed() * 1.1f; // 10%容差

        if (CurrentSpeed > MaxAllowedSpeed)
        {
            UE_LOG(LogTemp, Warning, TEXT("Speed hack detected: %.1f > %.1f"),
                CurrentSpeed, MaxAllowedSpeed);
            // 强制限制速度
            Owner->GetCharacterMovement()->Velocity =
                Owner->GetVelocity().GetClampedToMaxSize(MaxAllowedSpeed);
        }
    }
}

void UMyMovementComponent::ClientAckGoodMove_Implementation(float TimeStamp)
{
    // 服务器确认了这个移动是正确的
    // 从 SavedMoves 中移除已确认的移动
    // UCharacterMovementComponent 内部处理
    Super::ClientAckGoodMove_Implementation(TimeStamp);
}

void UMyMovementComponent::ClientAdjustPosition_Implementation(
    float TimeStamp,
    FVector NewLocation,
    FVector NewVelocity,
    UPrimitiveComponent* NewBase,
    FName NewBaseBoneName,
    bool bHasBase,
    bool bBaseRelativePosition,
    uint8 ServerMovementMode)
{
    // 客户端预测错误！服务器发来纠正位置
    UE_LOG(LogTemp, Verbose, TEXT("ClientAdjustPosition: err=%.2f"),
        FVector::Dist(GetActorLocation(), NewLocation));

    // 1. 应用服务器权威位置（基准修正）
    Super::ClientAdjustPosition_Implementation(
        TimeStamp, NewLocation, NewVelocity,
        NewBase, NewBaseBoneName, bHasBase,
        bBaseRelativePosition, ServerMovementMode);

    // 2. 重新应用未确认的 SavedMoves（重预测）
    //    UCharacterMovementComponent 自动调用
    //    ClientUpdatePositionAfterServerUpdate() → ReplayMove()
}
```

### 8.3 Lua 预测输入队列

```lua
-- ============================================================
-- prediction_queue.lua
-- 客户端预测输入队列
--
-- 用于自定义引擎（如 Lua+Love2D、Lua+Defold、自研引擎）
-- 核心职责：管理未确认的输入，支持回滚重放
-- ============================================================

local PredictionQueue = {}
PredictionQueue.__index = PredictionQueue

-- 最大存储帧数（约1秒@60Hz）
local MAX_QUEUE_SIZE = 64

--- 创建一个新的预测队列
--- @param tick_rate number 逻辑帧率
--- @return PredictionQueue
function PredictionQueue.new(tick_rate)
    local self = setmetatable({}, PredictionQueue)
    self.tick_rate = tick_rate or 60
    self.fixed_dt = 1.0 / self.tick_rate

    -- 帧号管理
    self.local_frame = 0        -- 客户端当前帧号
    self.last_acked_frame = 0   -- 服务器最后确认的帧号

    -- 权威状态（服务器最后确认的）
    self.authoritative_state = {
        frame = 0,
        pos_x = 0, pos_y = 0, pos_z = 0,
        vel_x = 0, vel_y = 0, vel_z = 0,
        is_grounded = true,
        hp = 100,
        ammo = 30,
    }

    -- 预测状态（当前显示的）
    self.predicted_state = {
        pos_x = 0, pos_y = 0, pos_z = 0,
        vel_x = 0, vel_y = 0, vel_z = 0,
        is_grounded = true,
        hp = 100,
        ammo = 30,
    }

    -- 未确认输入环形缓冲区
    -- inputs[i] = { frame=N, move_x=0, move_y=0, actions=0 }
    self.inputs = {}
    self.input_base_frame = 0   -- inputs[1] 对应的帧号

    -- 预测帧缓存（用于回滚时获取中间状态的预测位置）
    -- key=帧号, value=predicted_state快照
    self.prediction_snapshots = {}

    return self
end

--- 每帧调用：应用本地输入，立即更新预测状态
--- @param move_x number 水平移动输入 (-1 to 1)
--- @param move_y number 垂直移动输入 (-1 to 1)
--- @param actions number 位掩码动作 (JUMP=1, FIRE=2, RELOAD=4)
--- @return table 预测后的状态
function PredictionQueue:tick(move_x, move_y, actions)
    self.local_frame = self.local_frame + 1

    -- 1. 构造输入
    local input = {
        frame = self.local_frame,
        move_x = move_x or 0,
        move_y = move_y or 0,
        actions = actions or 0,
    }

    -- 2. 存储到缓冲区
    self:_store_input(input)

    -- 3. 本地模拟（基于预测状态）
    self:_simulate(self.predicted_state, input, self.fixed_dt)

    -- 4. 保存预测快照（用于回滚重建）
    self:_save_snapshot(self.local_frame, self.predicted_state)

    -- 5. 返回当前预测状态（供渲染使用）
    return self:_copy_state(self.predicted_state)
end

--- 收到服务器权威状态时调用
--- @param server_state table 服务器下发的状态
function PredictionQueue:on_server_state(server_state)
    local server_frame = server_state.frame
    local last_processed = server_state.last_processed_input_frame

    -- 更新权威状态
    self.authoritative_state = self:_copy_state(server_state)
    self.authoritative_state.frame = server_frame

    -- 检查预测误差
    local predicted_at_server_frame = self:_get_predicted_snapshot(server_frame)
    local err = self:_calc_error(
        predicted_at_server_frame or self.authoritative_state,
        server_state
    )

    if err > 0.05 then  -- 5cm 阈值
        -- === 需要回滚 ===
        print(string.format(
            "[Prediction] Frame %d error %.3f, reconciling...",
            server_frame, err
        ))

        -- 1. 重置预测状态到权威基准
        self.predicted_state = self:_copy_state(server_state)

        -- 2. 清除已确认的输入
        self:_acknowledge_inputs_up_to(last_processed)

        -- 3. 重新应用未确认的输入
        local unacked = self:_get_unacknowledged(last_processed + 1, self.local_frame)
        for _, input in ipairs(unacked) do
            self:_simulate(self.predicted_state, input, self.fixed_dt)
            self:_save_snapshot(input.frame, self.predicted_state)
        end

        self.last_acked_frame = last_processed
    else
        -- 预测正确
        self.last_acked_frame = last_processed
        self:_acknowledge_inputs_up_to(last_processed)
    end

    -- 更新权威基准
    self.authoritative_state = self:_copy_state(server_state)
end

--- 模拟一帧
--- @param state table 当前状态（会被修改）
--- @param input table 输入数据
--- @param dt number 固定时间步长
function PredictionQueue:_simulate(state, input, dt)
    -- 移动参数（必须与服务器一致！）
    local move_speed = 6.0
    local acceleration = 50.0
    local friction = 15.0
    local jump_force = 8.0
    local gravity = 25.0

    -- 水平移动方向
    local wish_dir_x = input.move_x
    local wish_dir_y = input.move_y
    local wish_len = math.sqrt(wish_dir_x * wish_dir_x + wish_dir_y * wish_dir_y)

    -- 归一化移动方向
    if wish_len > 1.0 then
        wish_dir_x = wish_dir_x / wish_len
        wish_dir_y = wish_dir_y / wish_len
    end

    -- 加速/摩擦
    if wish_len > 0.01 then
        local target_vx = wish_dir_x * move_speed
        local target_vy = wish_dir_y * move_speed
        state.vel_x = self:_move_toward(state.vel_x, target_vx, acceleration * dt)
        state.vel_z = self:_move_toward(state.vel_z, target_vy, acceleration * dt)
    else
        state.vel_x = self:_move_toward(state.vel_x, 0, friction * dt)
        state.vel_z = self:_move_toward(state.vel_z, 0, friction * dt)
    end

    -- 跳跃
    if bit32_band(input.actions, ACTION_JUMP) ~= 0 and state.is_grounded then
        state.vel_y = jump_force
        state.is_grounded = false
    end

    -- 重力
    if not state.is_grounded then
        state.vel_y = state.vel_y - gravity * dt
    end

    -- 位置更新
    state.pos_x = state.pos_x + state.vel_x * dt
    state.pos_y = state.pos_y + state.vel_y * dt
    state.pos_z = state.pos_z + state.vel_z * dt

    -- 地面检测
    if not state.is_grounded and state.pos_y <= 0 then
        state.pos_y = 0
        state.vel_y = 0
        state.is_grounded = true
    end

    -- 射击处理（预测弹药）
    if bit32_band(input.actions, ACTION_FIRE) ~= 0 and state.ammo > 0 then
        state.ammo = state.ammo - 1
    end
end

--- 辅助：向目标值平滑移动
function PredictionQueue:_move_toward(current, target, max_delta)
    if math.abs(target - current) <= max_delta then
        return target
    end
    if target > current then
        return current + max_delta
    else
        return current - max_delta
    end
end

-- ========== 输入缓冲区操作 ==========

function PredictionQueue:_store_input(input)
    local frame = input.frame
    -- 确保足够的容量
    if frame >= self.input_base_frame + MAX_QUEUE_SIZE then
        self:_evict_old_inputs(frame - MAX_QUEUE_SIZE / 2)
    end

    local index = self:_input_index(frame)
    self.inputs[index] = input
end

function PredictionQueue:_get_input(frame)
    if frame < self.input_base_frame or frame >= self.input_base_frame + MAX_QUEUE_SIZE then
        return nil
    end
    return self.inputs[self:_input_index(frame)]
end

function PredictionQueue:_input_index(frame)
    -- 环形缓冲区索引（Lua 数组从 1 开始）
    return (frame % MAX_QUEUE_SIZE) + 1
end

function PredictionQueue:_acknowledge_inputs_up_to(frame)
    for f = self.input_base_frame, frame do
        local idx = self:_input_index(f)
        self.inputs[idx] = nil
    end
    if frame >= self.input_base_frame then
        self.input_base_frame = frame + 1
    end
end

function PredictionQueue:_get_unacknowledged(from_frame, to_frame)
    local result = {}
    local start = math.max(from_frame, self.input_base_frame)
    for f = start, math.min(to_frame, self.input_base_frame + MAX_QUEUE_SIZE - 1) do
        local input = self:_get_input(f)
        if input then
            table.insert(result, input)
        end
    end
    return result
end

function PredictionQueue:_evict_old_inputs(new_base)
    for f = self.input_base_frame, new_base - 1 do
        self.inputs[self:_input_index(f)] = nil
    end
    self.input_base_frame = new_base
end

-- ========== 快照管理 ==========

function PredictionQueue:_save_snapshot(frame, state)
    self.prediction_snapshots[frame] = self:_copy_state(state)

    -- 清理旧快照（只保留最近 MAX_QUEUE_SIZE 帧）
    local min_frame = frame - MAX_QUEUE_SIZE
    for f, _ in pairs(self.prediction_snapshots) do
        if f < min_frame then
            self.prediction_snapshots[f] = nil
        end
    end
end

function PredictionQueue:_get_predicted_snapshot(frame)
    return self.prediction_snapshots[frame]
end

-- ========== 工具函数 ==========

function PredictionQueue:_copy_state(src)
    -- 状态可能是嵌套的 table，做浅拷贝即可（字段都是值类型）
    return {
        frame = src.frame,
        pos_x = src.pos_x, pos_y = src.pos_y, pos_z = src.pos_z,
        vel_x = src.vel_x, vel_y = src.vel_y, vel_z = src.vel_z,
        is_grounded = src.is_grounded,
        hp = src.hp,
        ammo = src.ammo,
    }
end

function PredictionQueue:_calc_error(state_a, state_b)
    local dx = state_a.pos_x - state_b.pos_x
    local dy = state_a.pos_y - state_b.pos_y
    local dz = state_a.pos_z - state_b.pos_z
    return math.sqrt(dx * dx + dy * dy + dz * dz)
end

-- ========== 常量和辅助 ==========

-- 动作位掩码
local ACTION_JUMP  = 1
local ACTION_FIRE  = 2
local ACTION_RELOAD = 4

--- Lua 5.1/5.2/LuaJIT 兼容的位操作
local bit32_band
if bit and bit.band then
    bit32_band = bit.band  -- LuaJIT
elseif bit32 and bit32.band then
    bit32_band = bit32.band -- Lua 5.2+
else
    -- Lua 5.1 fallback
    bit32_band = function(a, b)
        local result = 0
        local bitval = 1
        while a > 0 and b > 0 do
            if a % 2 == 1 and b % 2 == 1 then
                result = result + bitval
            end
            bitval = bitval * 2
            a = math.floor(a / 2)
            b = math.floor(b / 2)
        end
        return result
    end
end

-- 导出模块
return {
    new = PredictionQueue.new,
    ACTION_JUMP = ACTION_JUMP,
    ACTION_FIRE = ACTION_FIRE,
    ACTION_RELOAD = ACTION_RELOAD,
}

-- ============================================================
-- 使用示例
-- ============================================================
--[[
local PredictionQueue = require("prediction_queue")

-- 初始化
local pq = PredictionQueue.new(60)  -- 60Hz

-- 游戏主循环
function love.update(dt)
    -- 采集输入
    local move_x = 0
    local move_y = 0
    local actions = 0

    if love.keyboard.isDown("w") then move_y = move_y - 1 end
    if love.keyboard.isDown("s") then move_y = move_y + 1 end
    if love.keyboard.isDown("a") then move_x = move_x - 1 end
    if love.keyboard.isDown("d") then move_x = move_x + 1 end
    if love.keyboard.isDown("space") then
        actions = bit32_band(actions, PredictionQueue.ACTION_JUMP)
    end

    -- 逐帧预测
    local state = pq:tick(move_x, move_y, actions)

    -- 更新渲染位置
    player.x = state.pos_x
    player.y = state.pos_z  -- 2D游戏: Y轴映射到Z
end

-- 收到服务器状态回调
function on_server_state_received(data)
    pq:on_server_state(data)
end
]]
```

---

## 9. 练习

### 练习 1：基础——实现简单移动预测（30分钟）

**目标**：在 Unity 中实现一个简化版的客户端移动预测

**要求**：
1. 创建一个 `SimplePrediction` 脚本，支持 WASD 移动和空格跳跃
2. 实现 `PredictStep()` 方法：本地立即执行移动
3. 实现 `OnServerState()` 方法：收到服务器位置后比对误差
4. 如果误差 > 0.1m，打印 `"[Reconciliation] Frame X, error Y"` 并回滚
5. 创建一个模拟服务器脚本：每秒收到客户端位置后回传（延迟 100ms）

**测试方法**：
- 在 Unity 中创建两个 Cube（一个代表预测位置，一个代表权威位置）
- 移动 5 秒后观察两个 Cube 的位置差
- 人为在服务器端修改回传位置（模拟"预测错误"），观察回滚是否触发

**验收标准**：
- 预测正确时，误差 < 0.01m（浮点精度）
- 人为制造误差时，帧日志中能看到 reconciliation 触发
- 输入响应无延迟（按 W 立刻移动）

### 练习 2：进阶——预测回滚与输入队列（45分钟）

**目标**：基于练习 1，增加多帧预测和输入回放

**要求**：
1. 实现 `InputBuffer` 类（环形缓冲区，支持按帧号存取）
2. 模拟 5 帧领先（客户端帧号比服务器高 5）
3. 实现完整的回滚重放：用服务器位置 + 未确认输入重新模拟
4. 加入平滑修正：当误差 < 0.5m 时，在 0.1s 内平滑过渡，不跳变
5. 记录每帧的回滚次数到 Unity Profiler

**测试方法**：
- 人为使服务器回传位置与本地相差 0.3m
- 观察回滚是否以平滑过渡而非跳变完成
- 打开 Unity Profiler 确认回滚频率

**验收标准**：
- 多帧领先时，输入队列正确管理未确认帧
- 回滚后，角色的渲染位置平滑过渡到权威位置
- 0.5m 以上的大误差直接跳变（硬切），小误差平滑过渡

### 练习 3：挑战——射击预测 + 特效管理（60分钟）

**目标**：在练习 2 的基础上增加射击预测和特效区分

**要求**：
1. 实现射击预测：
   - 客户端立即播放枪口闪光、后坐力动画
   - 本地射线检测确定"预测命中点"，播放火花特效
   - 本地减少弹药显示
2. 实现特效管理器 `EffectPredictionManager`：
   - 瞬态特效（枪口闪光、后坐力）：立即播放，不管服务器
   - 预测特效（火花、弹道）：立即播放，但服务器拒绝时淡出销毁
   - 确认特效（伤害数字、击杀特效）：严格等服务器确认
3. 服务器随机 20% 概率拒绝射击（模拟 CD 未好或反外挂），观察客户端的回滚表现
4. 实现弹药回滚：服务器拒绝射击时，弹药数从 29 恢复为 30

**测试方法**：
- 连续射击 20 次（20% 拒绝率 → 约 4 次拒绝）
- 观察被拒绝时：火花是否自然淡出，弹药是否正确恢复
- 检查拒绝帧和确认帧的特效行为差异

**验收标准**：
- 闪光/后坐力无论如何都立即播放
- 火花在拒绝后 0.3s 内淡出消失
- 伤害数字只在服务器确认后才出现
- 弹药在拒绝后正确恢复

---

## 10. 扩展阅读

| 资源 | 类型 | 说明 |
|------|------|------|
| [Source Multiplayer Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) | 官方文档 | Valve 的 Source 引擎网络架构，包含延迟补偿和预测的经典实现 |
| [Unreal Engine: Gameplay Ability System Prediction](https://docs.unrealengine.com/5.3/en-US/gameplay-ability-system-for-unreal-engine/) | 官方文档 | GAS 预测的完整文档，包括 PredictionKey 生命周期 |
| [Overwatch Gameplay Architecture and Netcode](https://www.youtube.com/watch?v=W3aieHjyNvw) | GDC 演讲 | Overwatch 的状态同步架构，含移动预测和技能预测的实战细节 |
| [Gabriel Gambetta: Client-Server Game Architecture](https://www.gabrielgambetta.com/client-server-game-architecture.html) | 教程 | 经典的客户端预测+服务端和解+实体插值三部曲教程 |
| [Unreal Engine: Character Movement Component](https://docs.unrealengine.com/5.3/en-US/gameplay-framework-movement-in-unreal-engine/) | 官方文档 | UCharacterMovementComponent 的 SavedMove 客户端预测机制详解 |
| [Fast-Paced Multiplayer: Client-Side Prediction](https://www.gabrielgambetta.com/client-side-prediction-server-reconciliation.html) | 教程 | 原文经典，包含可运行的 JavaScript 示例 |
| [Unity Netcode for GameObjects: Client Prediction](https://docs-multiplayer.unity3d.com/netcode/current/advanced-topics/relevancy/) | 官方文档 | Unity NGO 的预测支持说明 |
| [Fighting Game Netcode: GGPO](https://www.ggpo.net/) | 开源项目 | GGPO Rollback Netcode，客户端预测的极端应用（格斗游戏） |

---

## 常见陷阱

| 陷阱 | 现象 | 解决方法 |
|------|------|---------|
| **客户端和服务器物理参数不一致** | 预测位置持续漂移，每帧都在回滚 | 使用配置文件确保两端使用完全相同的参数（速度、加速度、重力等）。用版本号校验参数脚本 |
| **浮点误差累积导致"永远是错的"** | reconciliation 每帧都触发但误差很小 | 设置合理的 reconciliation 阈值（如 0.05m）。不要为 0.001mm 的浮点误差触发回滚 |
| **回滚后角色跳变** | 角色突然瞬移到另一个位置 | 使用平滑修正：小误差平滑过渡，大误差硬切。但永远不要隐藏大误差——那是真正的问题而非显示问题 |
| **预测窗口过大** | 客户端领先 20 帧，回滚时重放 20 帧导致卡顿 | 限制预测窗口大小（通常 ≤10 帧）。超过窗口时拉慢客户端逻辑帧或丢弃过旧输入 |
| **忘记处理"非本人引起"的状态变化** | 其他人推了你一下，你的预测不知道，直到服务器确认才发现错了 | 这是预测的固有限制。外部实体变化只能等服务器确认。在混乱场景中（大量外部交互），适当降低预测激进度 |
| **特效回滚处理不当** | 伤害数字出现了又消失，或者完全不出现 | 区分"瞬态特效"和"确认特效"。伤害数字、击杀反馈等必须等服务器确认。枪口闪光、后坐力可以无条件播放 |
| **GAS 中忘记 ScopedPredictionWindow** | GE 被应用但没有被标记为 Predicted，导致服务器确认时无法回滚 | 在 ActivateAbility 中始终使用 `FScopedPredictionWindow`。检查 `ActivationInfo` 中的 `PredictionKey` 是否为有效值 |
| **移动组件预测与物理引擎冲突** | CharacterMovement 的预测和 PhysX/Chaos 的同步在客户端产生二重移动 | 使用 UCharacterMovementComponent 的内置预测时，确保服务器端使用相同的移动模式。不要同时使用物理模拟和 CMC 预测 |
| **预测了不该预测的数据** | 客户端的 HP 减少是预测的，但服务器说了个不同的值，导致血条跳变 | 客户端只预测"知道信息足够的事"：自己的移动、自己的技能冷却、自己的弹药。不预测伤害来源、其他玩家位置、服务器计算的结果 |
| **输入压缩导致精度丢失** | 连续 3 帧向右移动被合并为 1 帧，丢失了中间帧的细节状态变化（如第 2 帧按了跳跃） | 输入压缩时检查关键状态是否有变化。有跳跃/射击/技能等关键动作时不允许合并 |

---

## 核心公式速查

```
预测模型：
  P(t+1) = P(t) + Simulate(Input_t, Δt)
  其中 P = 预测状态, Simulate = 与服务器相同的模拟函数

回滚条件：
  if |P(serverFrame) - Auth(serverFrame)| > threshold:
      P(baseFrame) = Auth(baseFrame)
      for each unacked_input from baseFrame+1 to now:
          P = Simulate(P, input, Δt)

误差平滑：
  P_display(t) = P_predicted(t) + Correction(t)
  其中 Correction(t) 在 N 帧内从 error 渐变为 0

GAS 预测 Key 生命周期：
  生成 → 标记预测GE → 发送ServerRPC → 服务器处理 → Replicate回客户端 → Confirm/Reject
```
