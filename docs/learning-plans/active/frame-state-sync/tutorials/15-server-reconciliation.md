# 服务端和解 (Server Reconciliation)

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 45min
> 前置知识: [14-客户端预测](14-client-side-prediction.md)

---

## 1. 概念讲解

### 1.1 为什么需要和解？

在上一节「客户端预测」中，我们学会了如何让本地玩家获得即时反馈：客户端不等服务端确认，直接本地模拟移动/射击。这解决了"按下按键 100ms 后才看到角色移动"的糟糕体验。

但客户端预测带来了一个新问题：**客户端预测可能出错。**

预测错的原因有三类：

| 类型 | 例子 | 后果 |
|------|------|------|
| **其他玩家干扰** | A 预测自己继续向前跑，但服务端判定 B 已经击中了 A（减速/击退/死亡） | 客户端预测的 A 位置和移动状态与服务端不一致 |
| **物理碰撞** | 客户端预测角色穿过了门，但服务端判定另一玩家先关上了这道门 | 客户端认为自己在门后，服务端认为自己在门前 |
| **服务端逻辑修正** | 客户端在 HP=100 时按下喝药 → 预测自己变成 HP=150；但到达服务端时，服务端判定另一玩家先攻击了你，你的 HP 只有 20 → 喝药后 HP=70 | 客户端显示 HP=150，服务端真实 HP=70 |

**和解 (Reconciliation)** 就是客户端收到服务端的"正确答案"后，**修正本地世界状态以匹配服务端权威状态**的过程。

一句话总结：

> 客户端预测给了你"即时反馈的幻觉"。和解就是当幻觉与现实（服务端权威状态）不一致时，**把幻觉修正为现实**。

### 1.2 和解场景全景图

```
时间轴:
Server:  ──[Tick100]────[Tick101]────[Tick102]────[Tick103]──→
               │            │            │            │
               │ 输入A@100  │ 输入A@101  │            │
Client: ──预测100──预测101──预测102──收到服务器Tick100状态──→
              正确        正确        来自服务端         │
                                                  │
                                    客户端发现：我的预测102位置
                                    和服务端权威100→102推导结果
                                    不一致！
                                                  │
                                    触发 和解流程 ↓
```

和解流程的核心步骤：

```
1. 客户端发送输入时，附带帧号/序列号
2. 服务端处理输入，返回：
   - 权威世界状态
   - "已处理的最后一帧输入号" (lastProcessedSeq)
3. 客户端收到后：
   a. 找到 lastProcessedSeq 对应的本地历史帧
   b. 回滚到该帧的权威状态（丢弃该帧之后的预测结果）
   c. 重新应用 lastProcessedSeq 之后仍未确认的预测帧
   d. 平滑过渡到修正后的位置
```

### 1.3 和解流程详解

#### 第一步：服务端返回权威状态

服务端每帧（或每隔几帧）向客户端下发当前权威状态。关键字段：

```
ServerSnapshot {
    tick: uint32;            // 服务端当前的 tick 号
    lastInputSeq: uint32;    // 本客户端最近一次已被服务端处理的输入序列号
    playerState: {           // 玩家权威状态
        posX, posY, posZ,    // 位置
        velX, velY, velZ,    // 速度
        hp,                  // 血量
        stateFlags           // 状态位（奔跑/蹲下/死亡…）
    };
    worldState: {            // 附近实体的权威状态（可选增量）
        entities: [...]
    };
}
```

**核心字段 `lastInputSeq`**：这是服务端和解协议中最关键的值。它告诉客户端："你发来的输入中，序列号 ≤ lastInputSeq 的我都已经处理了；序列号 > lastInputSeq 的尚未处理或未到达。"

客户端用这个值来判断：**哪些预测帧已经被服务端"承认"了，哪些还没有。**

#### 第二步：客户端比对

当客户端收到服务端快照时：

```
客户端状态:
  已确认帧: [100] [101] [102] ← lastInputSeq=102，服务端已处理
  未确认预测帧: [103] [104] [105] ← 服务端尚未处理
  当前显示帧: 105

服务端说: lastInputSeq=102，你的权威位置是 (500, 200, 30)
客户端对比: 我的本地帧102缓存的位置是 (500, 200, 30) → 一致！无需修正
但我的本地帧103→105的累积预测位置是 (520, 210, 30)...
服务端对我执行了帧103→105吗？没有——它还没收到这些输入。
```

**比对失败的情况：**

```
服务端说: lastInputSeq=102，你的权威位置是 (490, 180, 0)  // 被击退了！
客户端对比: 我的本地帧102缓存的位置是 (500, 200, 0) → 不一致！
原因: 在帧100时，另一个玩家击中了"我"，导致我被击退。
      客户端当时还不知道这个事件，所以预测出了错误的结果。
```

#### 第三步：状态回滚 (State Rollback)

当检测到不一致时，客户端需要回滚。回滚的核心算法：

```
1. 将游戏状态重置为服务端发来的权威状态（对应于 lastInputSeq 帧）
2. 从 lastInputSeq+1 帧开始，重新执行每一个"尚未被确认的输入帧"
3. 每个重执行的帧使用的输入不变，但起始状态变了（因为回滚到了服务端权威状态）
4. 重执行完毕后，得到新的帧105预测状态——此次基于正确的起点
5. 如果新的预测位置和当前显示位置有差异，需要进行平滑修正
```

图解：

```
回滚前:
  已确认: [100]──[101]──[102]
  预测:                ──[103]──[104]──[105]  ← 基于错误的[102]起点
                       ↑ 这里就已经错了

回滚后:
  权威:  [100]──[101]──[102]server
                                ──[103]'──[104]'──[105]'  ← 重新预测
                                ↑ 基于正确的权威起点
```

#### 第四步：和解平滑 (Smoothing)

即使回滚重预测正确了，直接让玩家的画面从旧位置"跳"到新位置也会产生**瞬移 (Teleport)** 感——非常破坏体验。

常见平滑策略：

**策略 A：Lerp 平滑（Soft Correction）**

```csharp
// 不直接赋值新位置，而是每帧向目标位置插值
Vector3 targetPos = reconciledPos;
Vector3 currentDisplayPos = transform.position;
float correctionSpeed = 5.0f; // 每秒修正 5 单位距离

// 每渲染帧：
transform.position = Vector3.Lerp(
    currentDisplayPos,
    targetPos,
    correctionSpeed * Time.deltaTime
);
```

优点: 视觉平滑，玩家几乎感觉不到
缺点: 修正期间客户端和权威位置仍不一致；大误差时修正很慢

**策略 B：阈值混合 (Hybrid)**

```csharp
float error = Vector3.Distance(displayPos, authorityPos);
if (error < 0.1f) {
    // 误差很小 — 直接忽略，不修正
    return;
} else if (error < 2.0f) {
    // 中等误差 — 平滑 Lerp
    transform.position = Vector3.Lerp(displayPos, authorityPos, 5f * dt);
} else {
    // 大误差 — 硬修正（瞬移），因为继续平滑会导致更长时间的不一致
    transform.position = authorityPos;
    // 通常伴随一个"被拉回"的视觉特效
    PlayCorrectionVFX();
}
```

**策略 C：速度修正 (Velocity-Based)**

```csharp
// 不直接修改位置，而是修改速度向量让玩家自然"滑"到正确位置
Vector3 error = authorityPos - displayPos;
float correctionForce = 10.0f;

// 在 velocity 中加入一个指向正确位置的修正力
player.velocity += error * correctionForce * Time.deltaTime;
// 同时施加阻尼防止震荡
player.velocity *= 0.95f;
```

这种方式最自然——看起来像是"被一阵风推回去"，而不是被传送。但对于瞬发型修正（如 HP 突变、死亡状态切换）不适用。

### 1.4 和解策略对比

| 策略 | 视觉体验 | 一致性保障 | 实现复杂度 | 适用场景 |
|------|---------|-----------|-----------|---------|
| **Hard Reset** | 差（瞬移） | 强 | 很低 | 死亡/复活、传送技能、断线重连 |
| **Soft Correction (Lerp)** | 好 | 弱（修正期间不一致） | 低 | 小幅度位置差异（< 2m） |
| **Hybrid** | 中等 | 较强 | 中 | **推荐**：大多数 FPS/TPS |
| **Velocity-Based** | 最好 | 中 | 中高 | 移动速度快的动作游戏 |
| **No Correction (Ignore)** | 最好 | 无 | 很低 | 误差 < 阈值时的策略 |

### 1.5 和解中的特效处理

这是和解实现中最容易被忽视但用户体验影响极大的部分。

**问题场景：**
玩家按下技能键 → 客户端预测播放了华丽的技能特效 → 服务端回包说"那时候你已经死了" → 技能特效必须被**取消**。

直接取消特效会让玩家感觉"被耍了"——已经看到火焰特效却突然消失。

**解决模式：**

```csharp
// 1. 预测特效标记为"未确认"
void PlayPredictedEffect(EffectType type) {
    int effectId = PlayEffect(type);
    // 标记为预测特效：如果被和解撤销，可以被取消
    pendingEffects.Add(new PendingEffect {
        effectId = effectId,
        inputSeq = currentInputSeq,
        isPredicted = true
    });
}

// 2. 收到服务端确认后，将特效标记为"已确认"
void OnServerAck(uint confirmedSeq) {
    // 所有 inputSeq <= confirmedSeq 的预测特效 → 确认有效
    foreach (var fx in pendingEffects) {
        if (fx.inputSeq <= confirmedSeq) {
            fx.isPredicted = false; // 不会被撤销了
        }
    }
}

// 3. 回滚时取消未确认特效
void OnRollback(uint rollbackToSeq) {
    foreach (var fx in pendingEffects) {
        if (fx.inputSeq > rollbackToSeq && fx.isPredicted) {
            CancelEffect(fx.effectId);
        }
    }
    pendingEffects.RemoveAll(fx => fx.inputSeq > rollbackToSeq);
}
```

**更优雅的做法——延迟特效关键帧：**
不是立即播放特效的主体部分，而是先播放"前摇"动画（挥刀动作、蓄力光效），等到服务端确认后才播放"命中火花"等关键帧。这样即使被撤销，也只是收回了一个蓄力动作，玩家不会有"已经砍中了却被撤回"的挫败感。

### 1.6 和解调试：预测 vs 权威状态的可视化

调试和解问题是网络同步中最繁琐的工作之一。推荐在 Debug 模式下渲染两套视觉：

```csharp
void OnDrawGizmos() {
    if (!debugMode) return;

    // 绿色线条：当前显示位置（预测位置）
    Gizmos.color = Color.green;
    Gizmos.DrawWireSphere(displayPosition, 0.5f);

    // 红色线条：最近一次服务端权威位置
    Gizmos.color = Color.red;
    Gizmos.DrawWireSphere(lastAuthorityPosition, 0.5f);

    // 蓝色线条：连线显示偏差
    if (Vector3.Distance(displayPosition, lastAuthorityPosition) > 0.01f) {
        Gizmos.color = Color.blue;
        Gizmos.DrawLine(displayPosition, lastAuthorityPosition);
    }

    // 显示误差值
    float error = Vector3.Distance(displayPosition, lastAuthorityPosition);
    Handles.Label(displayPosition + Vector3.up * 2f,
        $"Error: {error:F3}m | Seq: {lastAckedSeq}/{currentInputSeq}");
}
```

**关键调试指标：**
- `predictionError`: 客户端预测位置与服务端权威位置的差值
- `reconciliationCount`: 累计和解次数（过高 → 网络不稳定或预测逻辑有 bug）
- `rollbackDepth`: 每次回滚需要重放的帧数（过大 → RTT 太高或输入未被及时确认）

---

## 2. 代码示例

### 2.1 Unity C#：ReconciliationSystem 完整实现

```csharp
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 服务端和解系统。
/// 核心职责：收到服务端权威状态后，比对并修正本地预测状态。
/// </summary>
public class ReconciliationSystem : MonoBehaviour
{
    [Header("配置")]
    [SerializeField] private float softCorrectionSpeed = 8.0f;   // Lerp 修正速度
    [SerializeField] private float hardCorrectionThreshold = 3.0f; // 超过此距离硬修正
    [SerializeField] private float ignoreErrorThreshold = 0.05f;  // 低于此距离忽略
    [SerializeField] private int maxInputHistory = 512;           // 最多缓存多少帧输入

    [Header("调试")]
    [SerializeField] private bool showDebugGizmos = true;

    // ──── 输入历史（用于回滚后重放）────
    // 结构：每帧我们发送给服务端的输入快照
    private struct InputSnapshot
    {
        public uint sequence;       // 输入序列号
        public Vector3 moveDir;     // 移动方向
        public bool jump;           // 跳跃键
        public bool fire;           // 开火键
        public float yaw;           // 视角 yaw
        public float pitch;         // 视角 pitch
    }
    private List<InputSnapshot> _inputHistory = new List<InputSnapshot>();
    private uint _nextInputSeq = 0; // 下一个输入序列号

    // ──── 本地预测状态 ────
    private Vector3 _predictedPosition;
    private Vector3 _predictedVelocity;
    private float _predictedYaw;
    private float _predictedPitch;

    // ──── 服务端权威状态 ────
    private Vector3 _authorityPosition;
    private Vector3 _authorityVelocity;
    private bool _hasAuthorityState = false;

    // ──── 和解追踪 ────
    private uint _lastAckedSeq = 0;           // 服务端已确认的最大序列号
    private uint _latestReceivedServerTick = 0;
    private int _reconciliationCount = 0;
    private float _lastPredictionError = 0f;

    /// <summary>
    /// 每帧调用：生成当前输入快照、执行本地预测、发送输入到服务端。
    /// </summary>
    public InputSnapshot CaptureAndPredict()
    {
        // 1. 捕获当前输入
        var input = new InputSnapshot
        {
            sequence = _nextInputSeq++,
            moveDir = new Vector3(Input.GetAxis("Horizontal"), 0, Input.GetAxis("Vertical")),
            jump = Input.GetButtonDown("Jump"),
            fire = Input.GetButtonDown("Fire1"),
            yaw = transform.eulerAngles.y,
            pitch = Camera.main.transform.eulerAngles.x
        };

        // 2. 缓存输入到历史（用于回滚时重放）
        _inputHistory.Add(input);
        if (_inputHistory.Count > maxInputHistory)
            _inputHistory.RemoveAt(0);

        // 3. 本地预测模拟（简化版：恒速移动 + 重力）
        SimulateLocalMovement(input, Time.deltaTime);

        // 4. 发送输入到服务端（实际项目中会进入可靠 UDP 发送队列）
        SendInputToServer(input);

        return input;
    }

    /// <summary>
    /// 本地预测移动模拟。
    /// </summary>
    private void SimulateLocalMovement(InputSnapshot input, float dt)
    {
        float speed = 6.0f;
        float gravity = -9.81f;

        // 水平移动
        Vector3 move = input.moveDir.normalized * speed;
        _predictedVelocity.x = move.x;
        _predictedVelocity.z = move.z;

        // 跳跃
        if (input.jump && IsGrounded())
            _predictedVelocity.y = 5.0f;

        // 重力
        _predictedVelocity.y += gravity * dt;

        // 更新位置
        _predictedPosition += _predictedVelocity * dt;

        // 简单地面检测
        if (_predictedPosition.y < 0)
        {
            _predictedPosition.y = 0;
            _predictedVelocity.y = 0;
        }

        // 更新视角
        _predictedYaw = input.yaw;
        _predictedPitch = input.pitch;

        // 应用预测结果到 Transform（让玩家看到）
        transform.position = _predictedPosition;
    }

    private bool IsGrounded() => _predictedPosition.y <= 0.01f;

    /// <summary>
    /// 收到服务端权威状态快照时调用。
    /// </summary>
    /// <param name="serverTick">服务端当前 tick</param>
    /// <param name="lastProcessedSeq">服务端已处理的最后一帧输入序列号</param>
    /// <param name="authorityPos">权威位置</param>
    /// <param name="authorityVel">权威速度</param>
    public void OnServerSnapshot(uint serverTick, uint lastProcessedSeq,
                                  Vector3 authorityPos, Vector3 authorityVel)
    {
        _latestReceivedServerTick = serverTick;
        _authorityPosition = authorityPos;
        _authorityVelocity = authorityVel;
        _hasAuthorityState = true;

        // ── 步骤 1：判断是否需要回滚 ──
        // 找到 lastProcessedSeq 对应的本地历史帧
        int ackedIndex = FindInputIndex(lastProcessedSeq);
        if (ackedIndex < 0)
        {
            // 本地已经没有这个序列号的历史了（可能太旧被清除了）
            // 直接接受权威状态
            HardResetToAuthority(authorityPos, authorityVel);
            return;
        }

        // ── 步骤 2：获取本地记录的"已确认帧的预测结果" ──
        // 注：实际实现中需要在每一帧保存完整的状态快照。
        // 这里简化——我们只比对当前位置和服务端权威位置。
        Vector3 localPredictedAtAcked = _predictedPosition; // 简化

        // ── 步骤 3：比对差异 ──
        float error = Vector3.Distance(localPredictedAtAcked, authorityPos);
        _lastPredictionError = error;

        if (error <= ignoreErrorThreshold)
        {
            // 预测准确，无需修正。只需更新 lastAckedSeq
            _lastAckedSeq = lastProcessedSeq;
            // 清理已被确认的旧历史帧
            PruneInputHistory(lastProcessedSeq);
            return;
        }

        // ── 步骤 4：回滚重预测 ──
        _reconciliationCount++;
        Debug.Log($"[Reconciliation] Error={error:F3}m, Rolling back from seq={lastProcessedSeq}");

        // 4a. 回滚位置到权威状态
        _predictedPosition = authorityPos;
        _predictedVelocity = authorityVel;
        _lastAckedSeq = lastProcessedSeq;

        // 4b. 重新播放 lastProcessedSeq 之后的所有未确认输入
        for (int i = ackedIndex + 1; i < _inputHistory.Count; i++)
        {
            var oldInput = _inputHistory[i];
            // 使用固定 dt 或历史帧的 dt 重模拟
            SimulateLocalMovement(oldInput, Time.fixedDeltaTime);
        }

        // 4c. 清理已确认的历史
        PruneInputHistory(lastProcessedSeq);

        // ── 步骤 5：视觉平滑 ──
        // 不直接瞬移 Transform（已在 SimulateLocalMovement 中更新了 _predictedPosition）
        // 而是让渲染帧的 Lerp 逻辑慢慢过渡
        ApplySmoothCorrection(authorityPos);
    }

    /// <summary>
    /// 在 Update（渲染帧）中平滑过渡到修正位置。
    /// </summary>
    private void ApplySmoothCorrection(Vector3 authorityPos)
    {
        Vector3 displayPos = transform.position;
        Vector3 targetPos = _predictedPosition; // 已通过重预测更新
        float error = Vector3.Distance(displayPos, targetPos);

        if (error < ignoreErrorThreshold)
            return;

        if (error > hardCorrectionThreshold)
        {
            // 大误差 → 硬修正（瞬移）
            transform.position = targetPos;
            OnHardCorrection();
        }
        else
        {
            // 中等误差 → Lerp 平滑
            float t = 1.0f - Mathf.Exp(-softCorrectionSpeed * Time.deltaTime);
            transform.position = Vector3.Lerp(displayPos, targetPos, t);
        }
    }

    /// <summary>
    /// 硬修正时触发的视觉反馈。
    /// </summary>
    private void OnHardCorrection()
    {
        // 可以播放一个短暂的"拉扯"粒子特效
        Debug.Log("Hard correction applied (teleport)");
    }

    /// <summary>
    /// 完全重置到权威状态（当本地历史不足以回滚时使用）。
    /// </summary>
    private void HardResetToAuthority(Vector3 pos, Vector3 vel)
    {
        _predictedPosition = pos;
        _predictedVelocity = vel;
        _lastAckedSeq = _nextInputSeq - 1;
        _inputHistory.Clear();
        transform.position = pos;
        Debug.LogWarning("Hard reset to authority state");
    }

    /// <summary>
    /// 在输入历史列表中查找指定序列号的索引。
    /// </summary>
    private int FindInputIndex(uint seq)
    {
        for (int i = _inputHistory.Count - 1; i >= 0; i--)
        {
            if (_inputHistory[i].sequence == seq)
                return i;
        }
        return -1;
    }

    /// <summary>
    /// 删除已被服务端确认的旧输入帧。
    /// </summary>
    private void PruneInputHistory(uint ackedSeq)
    {
        _inputHistory.RemoveAll(input => input.sequence <= ackedSeq);
    }

    // ──── 网络发送（占位）────
    private void SendInputToServer(InputSnapshot input)
    {
        // 实际项目中：序列化为字节流 → 可靠UDP发送队列 → 网络层
        // 这里省略实现细节（参见教程 02、03）
    }

    // ──── 调试可视化 ────
    private void OnDrawGizmos()
    {
        if (!showDebugGizmos || !_hasAuthorityState) return;

        // 绿色球：当前显示位置
        Gizmos.color = Color.green;
        Gizmos.DrawWireSphere(transform.position, 0.3f);

        // 红色球：服务端权威位置
        Gizmos.color = Color.red;
        Gizmos.DrawWireSphere(_authorityPosition, 0.3f);

        // 蓝色连线：偏差
        float error = Vector3.Distance(transform.position, _authorityPosition);
        if (error > 0.01f)
        {
            Gizmos.color = Color.blue;
            Gizmos.DrawLine(transform.position, _authorityPosition);
        }

        // 如果误差超过硬修正阈值，用黄色警告线标出
        if (error > hardCorrectionThreshold)
        {
            Gizmos.color = Color.yellow;
            Gizmos.DrawLine(transform.position, _authorityPosition);
        }
    }

    // ──── 调试信息 ────
    private void OnGUI()
    {
        if (!showDebugGizmos) return;

        GUILayout.BeginArea(new Rect(10, 10, 400, 200));
        GUILayout.Label($"Input Seq: {_nextInputSeq}");
        GUILayout.Label($"Server Tick: {_latestReceivedServerTick}");
        GUILayout.Label($"Last Acked Seq: {_lastAckedSeq}");
        GUILayout.Label($"Prediction Error: {_lastPredictionError:F3}m");
        GUILayout.Label($"Reconciliations: {_reconciliationCount}");
        GUILayout.Label($"Input History: {_inputHistory.Count} frames");
        GUILayout.EndArea();
    }
}
```

### 2.2 C++：和解缓冲区管理

```cpp
#include <vector>
#include <cstdint>
#include <cmath>
#include <algorithm>

// ──── 输入快照 ────
struct InputSnapshot {
    uint32_t sequence = 0;
    float move_x = 0.0f, move_y = 0.0f;  // 移动输入 [-1, 1]
    bool jump = false;
    bool fire = false;
    float yaw = 0.0f, pitch = 0.0f;
};

// ──── 状态快照（用于回滚） ────
struct StateSnapshot {
    uint32_t sequence = 0;  // 此状态对应的输入序列号
    float pos_x = 0.0f, pos_y = 0.0f, pos_z = 0.0f;
    float vel_x = 0.0f, vel_y = 0.0f, vel_z = 0.0f;
    float yaw = 0.0f, pitch = 0.0f;
    int hp = 100;
    uint8_t state_flags = 0;  // 位掩码：0x01=蹲下, 0x02=奔跑, 0x04=死亡...
};

// ──── 环状缓冲区（固定内存，无动态分配） ────
template<typename T, size_t Capacity>
class RingBuffer {
public:
    void push_back(const T& item) {
        if (count_ < Capacity) {
            buf_[count_++] = item;
        } else {
            buf_[write_pos_] = item;
            write_pos_ = (write_pos_ + 1) % Capacity;
            read_pos_ = (read_pos_ + 1) % Capacity;  // 覆盖最旧的
        }
    }

    T* find_by_sequence(uint32_t seq) {
        // 从最新到最旧反向搜索（大多数查找是针对最近帧的）
        size_t n = count_ > Capacity ? Capacity : count_;
        // 简化实现：线性扫描；生产环境可优化为二分
        for (int i = static_cast<int>(n) - 1; i >= 0; --i) {
            size_t idx = (read_pos_ + i) % Capacity;
            if (buf_[idx].sequence == seq)
                return &buf_[idx];
        }
        return nullptr;
    }

    // 删除序列号 <= acked_seq 的所有条目
    void prune_before(uint32_t acked_seq) {
        while (count_ > 0) {
            if (buf_[read_pos_].sequence <= acked_seq) {
                read_pos_ = (read_pos_ + 1) % Capacity;
                --count_;
            } else {
                break; // 遇到第一个大于 acked_seq 的就停
            }
        }
        if (count_ == 0) {
            read_pos_ = write_pos_ = 0;
        }
    }

    void clear() {
        count_ = 0;
        read_pos_ = 0;
        write_pos_ = 0;
    }

    size_t size() const { return count_; }

    // 迭代器支持（用于回滚重放）
    T* begin() { return count_ == 0 ? nullptr : &buf_[read_pos_]; }
    const T* begin() const { return count_ == 0 ? nullptr : &buf_[read_pos_]; }

    // 获取从指定索引开始的第 i 个元素
    T& at(size_t i) {
        size_t idx = (read_pos_ + i) % Capacity;
        return buf_[idx];
    }
    const T& at(size_t i) const {
        size_t idx = (read_pos_ + i) % Capacity;
        return buf_[idx];
    }

private:
    T buf_[Capacity];
    size_t read_pos_ = 0;
    size_t write_pos_ = 0;
    size_t count_ = 0;
};

// ──── 和解管理器 ────
class ReconciliationManager {
public:
    static constexpr size_t MAX_INPUT_HISTORY = 512;
    static constexpr size_t MAX_STATE_HISTORY = 128;  // 状态快照通常只需更短的历史

    ReconciliationManager()
        : next_input_seq_(0)
        , last_acked_seq_(0)
        , reconciliation_count_(0)
        , prediction_error_(0.0f)
    {}

    // ── 每逻辑帧调用：记录当前状态并生成输入 ──
    InputSnapshot capture_input(float move_x, float move_y,
                                 bool jump, bool fire,
                                 float yaw, float pitch)
    {
        InputSnapshot input;
        input.sequence = next_input_seq_++;
        input.move_x = move_x;
        input.move_y = move_y;
        input.jump = jump;
        input.fire = fire;
        input.yaw = yaw;
        input.pitch = pitch;

        // 缓存输入
        input_history_.push_back(input);

        // 保存当前预测状态（用于回滚恢复）
        StateSnapshot ss;
        ss.sequence = input.sequence;
        ss.pos_x = pos_x_; ss.pos_y = pos_y_; ss.pos_z = pos_z_;
        ss.vel_x = vel_x_; ss.vel_y = vel_y_; ss.vel_z = vel_z_;
        ss.yaw = yaw; ss.pitch = pitch;
        ss.hp = hp_;
        ss.state_flags = state_flags_;
        state_history_.push_back(ss);

        return input;
    }

    // ── 收到服务端权威快照时调用 ──
    void on_server_snapshot(uint32_t server_tick,
                             uint32_t last_processed_seq,
                             float auth_x, float auth_y, float auth_z,
                             float auth_vx, float auth_vy, float auth_vz,
                             int auth_hp, uint8_t auth_flags)
    {
        StateSnapshot* acked_state = state_history_.find_by_sequence(last_processed_seq);
        if (!acked_state) {
            // 本地已无此帧的历史 → 全量重置
            hard_reset(auth_x, auth_y, auth_z, auth_vx, auth_vy, auth_vz,
                       auth_hp, auth_flags);
            return;
        }

        // 比对差异
        float dx = acked_state->pos_x - auth_x;
        float dy = acked_state->pos_y - auth_y;
        float dz = acked_state->pos_z - auth_z;
        float error = std::sqrt(dx * dx + dy * dy + dz * dz);
        prediction_error_ = error;

        if (error < 0.01f && acked_state->hp == auth_hp) {
            // 预测完全准确，无需回滚
            last_acked_seq_ = last_processed_seq;
            input_history_.prune_before(last_processed_seq);
            state_history_.prune_before(last_processed_seq);
            return;
        }

        // 预测不一致 → 回滚
        ++reconciliation_count_;

        // 1. 回滚到服务端权威状态
        pos_x_ = auth_x; pos_y_ = auth_y; pos_z_ = auth_z;
        vel_x_ = auth_vx; vel_y_ = auth_vy; vel_z_ = auth_vz;
        hp_ = auth_hp;
        state_flags_ = auth_flags;
        last_acked_seq_ = last_processed_seq;

        // 2. 清理已确认的历史
        input_history_.prune_before(last_processed_seq);
        state_history_.prune_before(last_processed_seq);

        // 3. 重新应用所有未确认的输入
        for (size_t i = 0; i < input_history_.size(); ++i) {
            const auto& input = input_history_.at(i);
            simulate_move(input);
        }
    }

    // ── 本地模拟移动（简化版，生产环境会接入完整物理/逻辑引擎） ──
    void simulate_move(const InputSnapshot& input) {
        const float speed = 6.0f;
        const float gravity = -9.81f;
        const float dt = 1.0f / 60.0f; // 假设 60Hz 逻辑帧

        // 水平移动
        vel_x_ = input.move_x * speed;
        vel_z_ = input.move_y * speed;

        // 跳跃
        if (input.jump && pos_z_ <= 0.01f) {
            vel_y_ = 5.0f;
        }

        // 重力
        vel_y_ += gravity * dt;

        // 位移
        pos_x_ += vel_x_ * dt;
        pos_y_ += vel_y_ * dt;
        pos_z_ += vel_z_ * dt;

        // 简单地面碰撞
        if (pos_z_ < 0.0f) {
            pos_z_ = 0.0f;
            vel_y_ = 0.0f;
        }

        yaw_ = input.yaw;
        pitch_ = input.pitch;
    }

    // ── 硬重置 ──
    void hard_reset(float x, float y, float z,
                    float vx, float vy, float vz,
                    int hp, uint8_t flags)
    {
        pos_x_ = x; pos_y_ = y; pos_z_ = z;
        vel_x_ = vx; vel_y_ = vy; vel_z_ = vz;
        hp_ = hp;
        state_flags_ = flags;
        last_acked_seq_ = next_input_seq_ - 1;
        input_history_.clear();
        state_history_.clear();
    }

    // ── Getters for rendering ──
    float get_pos_x() const { return pos_x_; }
    float get_pos_y() const { return pos_y_; }
    float get_pos_z() const { return pos_z_; }
    float get_prediction_error() const { return prediction_error_; }
    uint32_t get_last_acked_seq() const { return last_acked_seq_; }
    int get_reconciliation_count() const { return reconciliation_count_; }

private:
    // 当前预测状态
    float pos_x_ = 0, pos_y_ = 0, pos_z_ = 0;
    float vel_x_ = 0, vel_y_ = 0, vel_z_ = 0;
    float yaw_ = 0, pitch_ = 0;
    int hp_ = 100;
    uint8_t state_flags_ = 0;

    uint32_t next_input_seq_ = 0;
    uint32_t last_acked_seq_ = 0;

    int reconciliation_count_ = 0;
    float prediction_error_ = 0.0f;

    RingBuffer<InputSnapshot, MAX_INPUT_HISTORY> input_history_;
    RingBuffer<StateSnapshot, MAX_STATE_HISTORY> state_history_;
};
```

**RingBuffer 设计要点：**

1. **固定容量、无堆分配**：游戏运行时每秒可能新增 60-120 个快照，使用动态 `std::vector` 的 `push_back` 会导致频繁的 reallocation。RingBuffer 预分配固定内存，O(1) 插入和删除。
2. **`prune_before()` 的 O(n) 现实**：虽然最坏是 O(n)，但已确认帧总是在 buffer 头部（最旧端），实际只需出队少数几个元素。`while` 循环 `break` 在看到第一帧未确认时就立刻停止。
3. **不支持随机删除**：和解场景下只需"删除尾部之前"的批量清除，单元素随机删除不是需求。保持 API 最小化可减少 bug 面。
4. **`find_by_sequence()` 的搜索方向**：从新到旧搜索，因为服务端 `last_processed_seq` 通常指向最近的几帧之一。

### 2.3 Lua：和解逻辑（嵌入 C/C++ 引擎的脚本层）

Lua 通常不直接做预测/和解（性能敏感且依赖帧数据），但在某些架构中，Lua 层负责**和解策略决策**（是否修正、用什么策略），而 C 层负责实际的状态回滚。

```lua
-- reconciliation.lua
-- 挂载在 PlayerEntity 上，由 C 层网络模块驱动

local Reconciliation = {}
Reconciliation.__index = Reconciliation

-- 配置
Reconciliation.SOFT_CORRECTION_SPEED = 8.0      -- Lerp 速度
Reconciliation.HARD_CORRECTION_THRESHOLD = 3.0   -- 硬修正阈值(米)
Reconciliation.IGNORE_ERROR = 0.05               -- 忽略阈值
Reconciliation.MAX_INPUT_HISTORY = 512

function Reconciliation.new(player_entity, net_module)
    local self = setmetatable({}, Reconciliation)
    self.player = player_entity
    self.net = net_module

    -- 输入历史：{ sequence, move_x, move_y, jump, fire, yaw, pitch }
    self.input_history = {}
    self.next_input_seq = 0
    self.last_acked_seq = 0

    -- 键值：用于快速查找输入帧
    -- seq -> { move_x, move_y, ... }
    self.input_map = {}

    -- 统计
    self.reconciliation_count = 0
    self.prediction_error = 0
    self.last_server_tick = 0

    -- 特效追踪：{ effect_id, input_seq, is_predicted }
    self.pending_effects = {}

    return self
end

-- 每帧由 C 层调用：捕获输入并执行本地预测
function Reconciliation:capture_and_predict(move_x, move_y, jump, fire, yaw, pitch)
    local seq = self.next_input_seq
    self.next_input_seq = seq + 1

    -- 记录输入
    local input = {
        sequence = seq,
        move_x = move_x, move_y = move_y,
        jump = jump, fire = fire,
        yaw = yaw, pitch = pitch,
    }
    table.insert(self.input_history, input)
    self.input_map[seq] = input

    -- 清理过旧的输入
    while #self.input_history > self.MAX_INPUT_HISTORY do
        local old = table.remove(self.input_history, 1)
        self.input_map[old.sequence] = nil
    end

    -- 本地模拟（这里调用 C 层的物理模拟函数）
    self:_simulate_movement(input)

    -- 发送到服务端
    self.net:send_input(input)

    return input
end

-- 由 C 层调用：收到服务端权威快照
-- server_snapshot: { tick, last_processed_seq, pos_x, pos_y, pos_z, vel_x, vel_y, vel_z, hp, flags }
function Reconciliation:on_server_snapshot(snapshot)
    self.last_server_tick = snapshot.tick
    local acked_seq = snapshot.last_processed_seq

    -- 找到本地记录的该帧输入
    local acked_input = self.input_map[acked_seq]
    if not acked_input then
        -- 本地历史已丢失 → 完全接受服务端状态
        self:_hard_reset(snapshot)
        return
    end

    -- 获取本地在 acked_seq 帧时的预测位置（由 C 层提供）
    local local_x, local_y, local_z = self.player:get_recorded_position(acked_seq)

    -- 计算误差
    local dx = local_x - snapshot.pos_x
    local dy = local_y - snapshot.pos_y
    local dz = local_z - snapshot.pos_z
    local error = math.sqrt(dx * dx + dy * dy + dz * dz)
    self.prediction_error = error

    if error <= self.IGNORE_ERROR then
        -- 预测准确，只需标记已确认
        self.last_acked_seq = acked_seq
        self:_prune_inputs(acked_seq)
        self:_confirm_effects(acked_seq)
        return
    end

    -- ── 和解触发 ──
    self.reconciliation_count = self.reconciliation_count + 1

    -- 如果误差巨大，可能是断线重连 → 全量重置
    if error > 100.0 then
        self:_hard_reset(snapshot)
        return
    end

    -- 回滚到服务端权威状态
    self.player:set_position(snapshot.pos_x, snapshot.pos_y, snapshot.pos_z)
    self.player:set_velocity(snapshot.vel_x, snapshot.vel_y, snapshot.vel_z)
    self.player:set_hp(snapshot.hp)
    self.player:set_state_flags(snapshot.flags)
    self.last_acked_seq = acked_seq

    -- 取消未确认的特效
    self:_cancel_predicted_effects(acked_seq)

    -- 清理已确认的历史
    self:_prune_inputs(acked_seq)

    -- 重新应用未确认的输入
    for _, input in ipairs(self.input_history) do
        if input.sequence > acked_seq then
            self:_simulate_movement(input)
        end
    end

    -- 决定视觉修正策略
    self:_apply_visual_correction(error)
end

-- 本地移动模拟（简化版，实际调用 C 层的 game_simulate_step）
function Reconciliation:_simulate_movement(input)
    -- 这里直接操作 C 层的 player entity
    -- 实际项目中这个函数由 C 侧引擎提供，Lua 只是调度
    self.player:apply_input(input.move_x, input.move_y,
                             input.jump, input.fire,
                             input.yaw, input.pitch)
end

-- 视觉修正策略选择
function Reconciliation:_apply_visual_correction(error)
    -- 把修正策略告知渲染层
    if error > self.HARD_CORRECTION_THRESHOLD then
        -- 硬修正：直接跳转 + 播放拉扯特效
        self.player:hard_snap_to_simulated()
        self.player:play_effect("correction_teleport")
    elseif error > self.IGNORE_ERROR then
        -- 软修正：开启 Lerp 平滑
        self.player:enable_soft_correction(self.SOFT_CORRECTION_SPEED)
    else
        -- 微小误差：不修正
    end
end

-- 标记一个预测特效
function Reconciliation:track_predicted_effect(effect_id, input_seq)
    table.insert(self.pending_effects, {
        effect_id = effect_id,
        input_seq = input_seq,
        is_predicted = true,
    })
end

-- 服务端确认后，标记特效为"有效"
function Reconciliation:_confirm_effects(acked_seq)
    for _, fx in ipairs(self.pending_effects) do
        if fx.input_seq <= acked_seq then
            fx.is_predicted = false -- 不会再被撤销
        end
    end
end

-- 回滚时取消未确认特效
function Reconciliation:_cancel_predicted_effects(rollback_seq)
    local i = 1
    while i <= #self.pending_effects do
        local fx = self.pending_effects[i]
        if fx.input_seq > rollback_seq and fx.is_predicted then
            self.player:cancel_effect(fx.effect_id)
            table.remove(self.pending_effects, i)
        else
            i = i + 1
        end
    end
end

-- 清理已确认的输入
function Reconciliation:_prune_inputs(acked_seq)
    while #self.input_history > 0 do
        local first = self.input_history[1]
        if first.sequence <= acked_seq then
            table.remove(self.input_history, 1)
            self.input_map[first.sequence] = nil
        else
            break
        end
    end
end

-- 硬重置到服务端权威状态
function Reconciliation:_hard_reset(snapshot)
    self.player:set_position(snapshot.pos_x, snapshot.pos_y, snapshot.pos_z)
    self.player:set_velocity(snapshot.vel_x, snapshot.vel_y, snapshot.vel_z)
    self.player:set_hp(snapshot.hp)
    self.player:set_state_flags(snapshot.flags)
    self.player:hard_snap_to_simulated()

    self.last_acked_seq = self.next_input_seq - 1
    self.input_history = {}
    self.input_map = {}
    self.pending_effects = {}
end

-- 调试：获取和解统计
function Reconciliation:get_stats()
    return {
        next_input_seq = self.next_input_seq,
        last_acked_seq = self.last_acked_seq,
        pending_inputs = #self.input_history,
        prediction_error = self.prediction_error,
        reconciliation_count = self.reconciliation_count,
        last_server_tick = self.last_server_tick,
    }
end

return Reconciliation
```

**Lua 层和解逻辑的设计考量：**

1. **input_map 作为索引加速**：Lua table 既是数组也是 hash map。`self.input_map[seq]` O(1) 查找，用于服务端回 `last_processed_seq` 时的快速定位。但需要与 `input_history` 数组保持同步清理，避免内存泄漏。
2. **C/Lua 边界**：位置查询 `get_recorded_position(acked_seq)` 和输入模拟 `apply_input()` 由 C 层引擎提供。Lua 层负责**决策**（是否回滚、用什么修正策略），C 层负责**执行**（状态快照、物理模拟）。这种分层让策划/逻辑程序员可以调整和解参数而不碰 C++ 代码。
3. **特效追踪**：`pending_effects` 追踪每个预测特效的生死。Lua 层的 GC 友好——cancel 时直接 `table.remove`，不做额外内存管理。
4. **100m 硬重置阈值**：如果预测误差超过 100 米，几乎可以肯定是断线重连或重大状态丢失——此时放弃回滚，直接接受全量权威状态。

---

## 3. 练习

### 练习 1：基础和解模拟器 [基础]

**目标**：在 Unity 中实现一个带可视化差异的简易和解系统。

**要求**：

1. 创建一个场景，包含：
   - 一个玩家角色（Cube），由本地输入控制（WASD 移动，Space 跳跃）
   - 一个"伪服务端"（另一个不可见的 GameObject，模拟服务端逻辑）
2. 每 0.5 秒，伪服务端向客户端发送一个"权威状态快照"，包含：
   - 服务端记录的玩家位置（**故意加入 ±0.3 的随机偏移**来模拟预测误差）
   - `lastProcessedSeq`（本地输入序列号）
3. 客户端收到快照后：
   - 比对本地预测位置与服务端权威位置
   - 如果误差 > 0.05，执行回滚 + 重预测
   - 如果误差 > 2.0，执行硬修正
4. 在 Scene 视图中用 Gizmos 绘制：
   - 绿色球：当前显示位置
   - 红色球：服务端权威位置
   - 蓝色线：偏差
5. 在 UI 上显示：预测误差值、和解次数、pending 输入帧数

**提示**：
- 伪服务端可以很简单——每 0.5 秒取一次客户端的当前位置，加一个随机偏移，然后作为"权威位置"发回
- 使用 `Time.fixedDeltaTime` 做逻辑帧步进，与渲染帧解耦
- `lastProcessedSeq` 可以直接用 `currentInputSeq - 5`（模拟服务端滞后 5 帧）

---

### 练习 2：特效和解系统 [进阶]

**目标**：实现预测特效的确认/撤销机制（在练习 1 的基础上扩展）。

**要求**：

1. 当玩家按下"攻击键"时：
   - 立即在客户端播放攻击特效（粒子 + 音效）
   - 记录该特效对应的 `inputSeq`
   - 将特效实例存入 `pendingEffects` 列表
2. 当服务端快照到达时：
   - 如果 `ackedSeq >= 特效的inputSeq` → 特效被确认，从 pending 列表移除（特效继续播放）
   - 如果 `ackedSeq < 特效的inputSeq` 且发生了回滚 → 取消该特效（`Destroy` 或 `Stop`）
3. 特效需要区分"前摇"和"命中"阶段：
   - 前摇（0~0.3s）：挥刀动作，被撤销时只需播放取消动画
   - 命中（0.3s~）：火花粒子，收到服务端确认后才播放
4. 在 UI 上显示当前 pending 特效数量

**提示**：
- 使用 `Coroutine` 实现特效的时间线控制：前摇阶段不播放火花，等 `ackedSeq` 到达后才触发"命中"回调
- 将特效 ID 与 `inputSeq` 关联，方便批量子销

---

### 练习 3：和解策略性能分析 [挑战]

**目标**：构建一个可配置的和解策略测试床，量化不同策略的表现。

**要求**：

1. 实现三种和解策略的独立模块：**Hard Reset**、**Soft Lerp**、**Hybrid**
2. 构建测试场景：
   - 本地玩家持续向右移动（速度 6 m/s）
   - 模拟一个外部事件：在 t=2s 时，"服务端"判定玩家被击退（位置瞬间向左偏移 3m）
3. 对每种策略，量化以下指标：
   - **收敛时间**：从检测到误差到显示位置与权威位置误差 < 0.05m 所需的时间
   - **最大视觉跳跃**：修正过程中屏幕显示位置的最大不连续变化
   - **体验评分**：主观打分（可以用公式模拟：`score = 1.0 / (convergence_time * max_jump)`）
4. 在不同网络延迟下测试（50ms, 100ms, 200ms, 500ms RTT），输出对比表格
5. 分析结果并撰写简短结论：在什么延迟/误差范围下哪种策略最优

**提示**：
- 使用 `Time.realtimeSinceStartup` 精确计时
- 收敛检测逻辑：连续 3 帧误差 < 0.05 才算收敛（防止震荡误判）
- 可导出 CSV 数据用于 Excel/Matplotlib 绘图

---

## 4. 扩展阅读

- **Source Multiplayer Networking**：[https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) — Valve 官方对 CS:GO/L4D 状态同步（含和解）的完整描述。这是业界最权威的参考文档之一。
- **Gaffer On Games: Networked Physics**：[https://gafferongames.com/post/networked_physics_2004/](https://gafferongames.com/post/networked_physics_2004/) — Glenn Fiedler 关于网络物理的系列文章（包括预测+和解）。2004 年发表但原理至今未变。
- **Overwatch Gameplay Architecture and Netcode**：[https://www.youtube.com/watch?v=W3aieHjyNvw](https://www.youtube.com/watch?v=W3aieHjyNvw) (GDC 2017) — 守望先锋的网络架构演讲，涵盖预测、和解、以及业内最先进的"优先队列重传"（每个实体独立确认/重传）。
- **Rocket League Netcode**：[https://www.gdcvault.com/play/1025362/](https://www.gdcvault.com/play/1025362/) (GDC 2019) — Psyonix 分享的物理密集型游戏（车+球）如何做和解，重点在刚体物理的回滚策略。
- **Unity Netcode for GameObjects (NGO) Source**：[https://github.com/Unity-Technologies/com.unity.netcode.gameobjects](https://github.com/Unity-Technologies/com.unity.netcode.gameobjects) — 阅读 `NetworkTransform` 和 `AnticipatedNetworkTransform` 的源码，观察 Unity 官方如何实现和解。
- **Fast-Paced Multiplayer (Gabriel Gambetta)**：[https://www.gabrielgambetta.com/client-server-game-architecture.html](https://www.gabrielgambetta.com/client-server-game-architecture.html) — 包含"Entity Interpolation"、"Client-Side Prediction"、"Server Reconciliation"三篇系列，非常适合串联学习。

---

## 常见陷阱

### 陷阱 1：回滚时忘记清理特效/音效

**症状**：和解触发后角色位置正确了，但之前预测的技能粒子特效还在播放、音效还在重复——玩家看到"已经取消的招数还在出特效"。

**正确做法**：回滚时必须遍历 `pendingEffects`，取消所有 `inputSeq > rollbackSeq` 的未确认特效。特效系统应支持 `Cancel(effectId)` 接口，必要时播放"取消过渡动画"。

### 陷阱 2：输入历史无限增长导致 OOM

**症状**：客户端运行 30 分钟后，`inputHistory` 列表包含 108000 条记录（60fps × 1800s），内存占用达数百 MB。

**正确做法**：
- 设置最大历史容量（如 512 帧 ≈ 8.5 秒 @ 60fps）
- 每次收到 `lastProcessedSeq` 后立即 `prune_before(ackedSeq)`
- 使用固定大小的 RingBuffer 而非 `std::vector` 或 `List<T>`（参见 C++ 示例代码）

### 陷阱 3：在渲染帧中执行回滚重预测

**症状**：`OnServerSnapshot` 回调在渲染线程被调用，其中执行了 `for` 循环重放 60 帧输入——每帧 16ms 的渲染预算直接爆掉，画面掉帧。

**正确做法**：
- 回滚 + 重预测必须在**逻辑帧**（`FixedUpdate` / 独立逻辑线程）中执行，或分摊到多帧
- 渲染层只做平滑修正（Lerp），耗时的状态计算交给逻辑帧
- 如果重预测帧数过多（如 > 30 帧），考虑直接硬重置而非重放

### 陷阱 4：和解与实体插值冲突

**症状**：A 玩家对 B 玩家做了预测 + 和解；同时 A 客户端也在对 B 做实体插值（见教程 16）。两个系统同时修改 B 的位置 → 抖动。

**正确做法**：
- 和解只修正**本地玩家**的状态。其他玩家的状态通过实体插值系统管理。
- 两个系统操作的对象应该严格隔离：和解系统写 `localPlayer`，插值系统读写 `remotePlayers`。
- 如果和解需要更新本地玩家以外的对象（如被击退影响了周围 AI），应通过服务端权威快照统一更新，不混合两种修正机制。

### 陷阱 5：`lastProcessedSeq` 语义理解错误

**症状**：服务端返回 `lastProcessedSeq = 105`，客户端理解为"服务端已经处理了我所有的输入"——但实际上服务端只处理了 105，客户端已经发了 110 到 120。客户端错误地清理了所有历史帧 105-120，导致后续无法回滚。

**正确做法**：
- `lastProcessedSeq` 的正确语义：**序列号 ≤ 该值的所有输入已被服务端处理和确认。**
- 只清理 `seq <= lastProcessedSeq` 的帧，**绝不清理 `seq > lastProcessedSeq` 的帧**。
- 在代码中用 `prune_before(acked_seq)`（≤ 清理）而非 `prune_after`。

### 陷阱 6：在服务端强制执行客户端预测的"结果"

**症状**：客户端在输入中夹带了"我预测我现在在 (500, 200)"的信息，并要求服务端"按这个来"。服务端信任了客户端的位置——反外挂的噩梦。

**正确做法**：
- 服务端只接受**输入指令**（按键、摇杆方向），不接受客户端声称的"位置/状态"。
- 服务端独立模拟所有客户端的移动——**服务端是唯一的权威**。
- 和解的方向是**服务端 → 客户端**，永远不是客户端 → 服务端。

### 陷阱 7：硬修正阈值设置不当

**症状 A**（阈值太小）：0.5m 就硬修正 → 画面频繁瞬移，体验极差。
**症状 B**（阈值太大）：10m 才硬修正 → 玩家长时间看到自己在错误位置，甚至穿墙。

**调优建议**：
- 从 `3.0m` 开始，在内部测试中观察
- 快速移动游戏（赛车、飞行）：适当增大到 5-8m（因为大速度下误差自然更大）
- 慢速战术游戏（彩虹六号）：减小到 1-1.5m（精度要求高）
- 最终值应由 QA 在实际网络条件下测试确定，不是拍脑袋
