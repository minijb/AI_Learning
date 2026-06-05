---
title: "帧同步客户端实现（Unity/C#）"
updated: 2026-06-05
---

# 帧同步客户端实现（Unity/C#）

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [[07-lockstep-protocol-design|07-帧同步协议设计：帧指令、冗余发包、丢包处理]]

---

## 1. 概念讲解

### 1.1 为什么这是最重要的教程？

前面 7 篇教程铺垫了所有理论基础：Lockstep 模型、确定性逻辑、协议设计。现在到了最关键的一步——**把它们变成能跑起来的代码**。

作为游戏前端工程师，客户端是你面试时被问到最多的部分。面试官关心的不是"帧同步是什么"，而是"你怎么在 Unity 里实现它"——每个类的职责、每一帧的数据流、输入延迟如何被隐藏、以及出了问题怎么定位。

这篇教程从零构建一个完整的 2 人对战 Lockstep Demo，包含所有核心模块。学完你不仅能面试，还能直接作为新项目的技术基座。

### 1.2 核心思想

帧同步客户端的本质任务只有一句话：

> **在正确的时刻，拿到所有玩家的输入，塞进确定性的逻辑引擎，把结果渲染出来。**

拆开看是五个子问题：

1. **什么时候执行逻辑帧？** ——网络包到了没有？缓冲够了吗？要不要追赶？
2. **输入怎么发出去？** ——玩家的触屏/键盘操作如何打包、何时发送？
3. **逻辑和表现怎么分离？** ——逻辑层跑确定性的定点数，表现层用浮点做平滑渲染，两层之间如何沟通？
4. **网络波动怎么扛？** ——丢包了怎么办？延迟高了怎么追赶？
5. **出了 bug 怎么查？** ——帧号对不上？计算结果不一致？怎么定位问题？

下面我们逐个击破。

### 1.3 客户端整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                        Unity 客户端                            │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │  InputManager │    │ NetworkClient │    │   DebugPanel  │    │
│  │  输入收集      │    │  UDP 收发     │    │  帧号/Desync  │    │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘    │
│         │                   │                                │
│         │    本地输入        │  远端输入(帧包)                  │
│         ▼                   ▼                                │
│  ┌──────────────────────────────────────────────┐            │
│  │              LockstepManager                  │            │
│  │        核心帧管理器 (Monobehaviour)            │            │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │            │
│  │  │FrameBuffer│  │ 帧追赶    │  │ 帧推进调度  │  │            │
│  │  │ 环形缓冲  │  │ 加速/跳帧 │  │ Update     │  │            │
│  │  └──────────┘  └──────────┘  └────────────┘  │            │
│  └────────────────────┬─────────────────────────┘            │
│                       │ 每逻辑帧: 输入 → 逻辑                   │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────┐            │
│  │                 GameLogic                     │            │
│  │           纯C#确定性逻辑引擎                    │            │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │            │
│  │  │ 定点数学  │ │ 碰撞检测  │ │ 实体状态管理  │  │            │
│  │  │ FixedMath│ │Collision │ │ EntityManager│  │            │
│  │  └──────────┘ └──────────┘ └──────────────┘  │            │
│  └────────────────────┬─────────────────────────┘            │
│                       │ 每逻辑帧输出: 逻辑状态快照               │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────┐            │
│  │                RenderProxy                    │            │
│  │        表现层: 逻辑位置 → 平滑渲染位置           │            │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────┐    │            │
│  │  │ 位置插值  │ │ 动画驱动  │ │ 特效触发   │    │            │
│  │  └──────────┘ └──────────┘ └────────────┘    │            │
│  └──────────────────────────────────────────────┘            │
│                                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                 │
│  │  GameObject│   │  Animator │   │  VFX      │                 │
│  │  Transform │   │  (表现)   │   │  Particle │                 │
│  └──────────┘   └──────────┘   └──────────┘                 │
└──────────────────────────────────────────────────────────────┘
```

数据流方向（关键）：
- **上行**：InputManager → LockstepManager → NetworkClient → 服务器
- **下行**：NetworkClient → LockstepManager(帧缓冲) → LockstepManager(帧推进) → GameLogic → RenderProxy → Unity 表现层
- **逻辑与表现之间是单向只读的**：表现层只读取逻辑层的状态快照，绝不反向写入。

---

## 2. 代码示例

> **重要说明**：以下代码是一个功能完整的 2 人对战 Lockstep Demo。所有类按依赖关系排列。你可以按顺序创建 `.cs` 文件并挂载到 Unity 场景中运行——见 2.7 节运行指南。

### 2.1 FixedMath.cs —— 定点数数学库

这是整个帧同步系统的地基。前面第 6 节深入讲过原理，这里给出可直接使用的 C# 实现。我们在 Demo 中使用 Q16.16 格式（32 位有符号整数，16 位小数）。

```csharp
// FixedMath.cs — 确定性定点数学库 (Q16.16)
// 所有游戏逻辑中涉及"位置/速度/方向"的计算必须使用此类型，绝不使用 float/double。

using System;
using System.Runtime.CompilerServices;

/// <summary>
/// Q16.16 定点数：32-bit 有符号整数，低 16 位为小数部分。
/// 范围：±32767.99998，分辨率 ≈ 0.000015
/// 所有运算通过整数完成，保证跨平台逐位确定性。
/// </summary>
public struct FP : IEquatable<FP>, IComparable<FP>
{
    // ── 内部存储 ──────────────────────────────────────
    public int RawValue;  // 原始定点值 = 实际值 × 65536

    // ── 常量 ─────────────────────────────────────────
    public const int FRACTIONAL_BITS = 16;
    public const int SCALE = 1 << FRACTIONAL_BITS;           // 65536
    public const long SCALE_LONG = 1L << FRACTIONAL_BITS;     // 64-bit 版 scale

    // 常用常量（构造时自动乘以 SCALE）
    public static readonly FP Zero  = new FP(0);
    public static readonly FP One   = new FP(SCALE);
    public static readonly FP Half  = new FP(SCALE / 2);
    public static readonly FP Two   = new FP(SCALE * 2);
    public static readonly FP Pi    = new FP(205887);  // π ≈ 3.14159 × 65536
    public static readonly FP Epsilon = new FP(1);      // 最小可表示单位

    // ── 构造函数 ──────────────────────────────────────
    // 注意：有两个构造路径——
    //   CreateFromRaw(int raw)       直接用 raw value 构造（从网络/文件恢复）
    //   CreateFromFloat(float f)     从浮点数构造（编辑器配置、表现层传值）
    // 运行时逻辑计算中严禁使用 CreateFromFloat——必须通过 FP 的运算链。

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    private FP(int raw) { RawValue = raw; }  // private: 强制使用 CreateFromRaw

    /// <summary>从原始整数值创建 FP（用于网络反序列化/存档恢复）</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP CreateFromRaw(int raw) => new FP(raw);

    /// <summary>从浮点数创建 FP。仅在编辑器/配置/测试中使用，运行时逻辑中禁止。</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP CreateFromFloat(float f) =>
        new FP((int)(f * SCALE));  // 截断舍入——所有客户端使用相同方式，确定性一致

    /// <summary>从整数创建 FP</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP CreateFromInt(int i) => new FP(i * SCALE);

    // ── 算术运算 ──────────────────────────────────────
    // 所有运算返回新的 FP，不修改自身。保证引用透明性——利于确定性。

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP operator +(FP a, FP b) =>
        new FP(a.RawValue + b.RawValue);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP operator -(FP a, FP b) =>
        new FP(a.RawValue - b.RawValue);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP operator -(FP a) =>
        new FP(-a.RawValue);

    /// <summary>
    /// 乘法：(a * b) / SCALE
    /// 使用 64-bit 中间结果防止溢出。
    /// 两个 Q16.16 相乘 = Q32.32，右移 16 位回到 Q16.16。
    /// </summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP operator *(FP a, FP b) =>
        new FP((int)(((long)a.RawValue * (long)b.RawValue) >> FRACTIONAL_BITS));

    /// <summary>
    /// 除法：(a * SCALE) / b
    /// 先左移再除，保证精度。
    /// 除以零 → 返回 Zero（帧同步中不应出现此情况，由上层保证）。
    /// </summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP operator /(FP a, FP b)
    {
        if (b.RawValue == 0) return Zero;
        return new FP((int)(((long)a.RawValue << FRACTIONAL_BITS) / (long)b.RawValue));
    }

    // ── 比较运算 ──────────────────────────────────────
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator ==(FP a, FP b) => a.RawValue == b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator !=(FP a, FP b) => a.RawValue != b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator <(FP a, FP b) => a.RawValue < b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator >(FP a, FP b) => a.RawValue > b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator <=(FP a, FP b) => a.RawValue <= b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator >=(FP a, FP b) => a.RawValue >= b.RawValue;

    // ── 转换 ─────────────────────────────────────────
    /// <summary>转回浮点数（仅供表现层/调试使用）</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public float ToFloat() => (float)RawValue / SCALE;

    /// <summary>取整（向下取整到整数 FP）</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public FP Floor() => new FP(RawValue & ~(SCALE - 1));  // 清掉小数位

    /// <summary>绝对值</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public FP Abs() => new FP(RawValue < 0 ? -RawValue : RawValue);

    // 平方根：牛顿迭代法，纯整数运算，确定性。
    public FP Sqrt()
    {
        if (RawValue <= 0) return Zero;

        // 初始猜测：利用 long 的整数 sqrt 作为 seed
        long val = (long)RawValue << FRACTIONAL_BITS;
        long x = val;
        // 快速整数 sqrt 近似
        long bit = 1L << 62;
        while (bit > val) bit >>= 2;
        long result = 0;
        while (bit != 0)
        {
            long sum = result + bit;
            result >>= 1;
            if (val >= sum) { val -= sum; result += bit; }
            bit >>= 2;
        }

        // 牛顿迭代精炼 (x = (x + a/x) / 2)
        long a = (long)RawValue << FRACTIONAL_BITS;
        for (int i = 0; i < 5; i++)
        {
            if (result == 0) break;
            result = (result + a / result) >> 1;
        }
        return new FP((int)result);
    }

    // ── Equals / GetHashCode ────────────────────────
    public bool Equals(FP other) => RawValue == other.RawValue;
    public override bool Equals(object obj) => obj is FP other && Equals(other);
    public override int GetHashCode() => RawValue;
    public int CompareTo(FP other) => RawValue.CompareTo(other.RawValue);
    public override string ToString() => ToFloat().ToString("F5");
}

/// <summary>
/// 二维定点向量，用于逻辑层的位置/速度/方向表示。
/// 所有运算通过 FP 完成，零浮点依赖。
/// </summary>
public struct FPVector2 : IEquatable<FPVector2>
{
    public FP X, Y;

    public FPVector2(FP x, FP y) { X = x; Y = y; }

    public static readonly FPVector2 Zero = new FPVector2(FP.Zero, FP.Zero);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FPVector2 operator +(FPVector2 a, FPVector2 b) =>
        new FPVector2(a.X + b.X, a.Y + b.Y);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FPVector2 operator -(FPVector2 a, FPVector2 b) =>
        new FPVector2(a.X - b.X, a.Y - b.Y);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FPVector2 operator *(FPVector2 v, FP s) =>
        new FPVector2(v.X * s, v.Y * s);

    /// <summary>两点距离（欧几里得）</summary>
    public FP Magnitude()
    {
        FP dx2 = X * X;
        FP dy2 = Y * Y;
        // (dx² + dy²).Sqrt()
        // 但 FP 的加法结果可能溢出... 我们用中间 long
        long sum = (long)dx2.RawValue + (long)dy2.RawValue;
        // clamp to int range
        if (sum > int.MaxValue) sum = int.MaxValue;
        if (sum < int.MinValue) sum = int.MinValue;
        return FP.CreateFromRaw((int)sum).Sqrt();
    }

    /// <summary>归一化（长度可能不精确，但对帧同步足够）</summary>
    public FPVector2 Normalized()
    {
        FP mag = Magnitude();
        if (mag.RawValue == 0) return Zero;
        return new FPVector2(X / mag, Y / mag);
    }

    // 浮点转换（仅供 RenderProxy 使用）
    public UnityEngine.Vector2 ToVector2() =>
        new UnityEngine.Vector2(X.ToFloat(), Y.ToFloat());

    public bool Equals(FPVector2 other) => X == other.X && Y == other.Y;
    public override bool Equals(object obj) => obj is FPVector2 other && Equals(other);
    public override int GetHashCode() => X.RawValue ^ (Y.RawValue * 397);
    public override string ToString() => $"({X}, {Y})";
}
```

**关键设计决策**：
- `struct` 而非 `class`：定点数应该是值类型，避免 GC 压力（每帧可能创建数千个）和引用语义的隐蔽 bug。
- `RawValue` 公开：性能优先——在热路径中直接访问 `RawValue` 比每次调 getter 快。外部代码禁止直接修改。
- `CreateFromRaw` 和 `CreateFromFloat` 函数分离：后者只在编辑器/配置层使用，前者用于网络反序列化。命名区分防止混用。
- 平方根用牛顿迭代：纯整数运算，跨平台一致。

---

### 2.2 FrameBuffer.cs —— 帧缓冲区

帧同步不能"收到一帧就执行一帧"。网络有抖动：可能连续收到 3 帧，然后卡 150ms。帧缓冲区的作用是**削峰填谷**——预缓冲 N 帧才开始播放，让网络抖动被缓冲吸收。

```csharp
// FrameBuffer.cs — 环形帧缓冲区
// 核心职责：缓存从服务器收到的帧数据，按帧号顺序提供消费。

using System;

/// <summary>
/// 一帧的输入数据——来自所有玩家的输入集合。
/// 实际游戏中通常更复杂（含玩家数量、帧号、操作数组），这里简化为帧号映射。
/// </summary>
public class FrameData
{
    public uint FrameNumber;
    public byte[] PlayerInputs; // 玩家输入数组: PlayerInputs[playerIndex] = 该玩家本帧输入
    public long ArrivalTimestamp; // 到达时间戳(Stopwatch ticks)，用于统计延迟

    public FrameData(uint frameNumber, int playerCount)
    {
        FrameNumber = frameNumber;
        PlayerInputs = new byte[playerCount];
    }
}

/// <summary>
/// 环形帧缓冲区。
/// 
/// 工作原理：
///   1. 网络线程调用 EnqueueFrame() 写入帧数据
///   2. 主线程调用 TryDequeueFrame(frameNumber) 按序取出帧数据
///   3. 如果请求的帧号尚未到达 → 返回 null → 主线程等待/追赶
/// 
/// 环形缓冲区优势：
///   - 无 GC 分配（预分配数组，循环使用）
///   - O(1) 读写
///   - 自动淘汰旧帧（超出窗口大小的帧被新帧覆盖）
/// </summary>
public class FrameBuffer
{
    private readonly FrameData[] _buffer;         // 环形存储
    private readonly int _capacity;               // 缓冲区容量（必须是 2 的幂，方便取模）
    private readonly int _mask;                   // 位掩码取模: index & mask (比 % 快)
    private uint _newestFrame;                    // 已缓冲的最大帧号
    private uint _oldestFrame;                    // 仍在缓冲中的最小帧号
    private int _count;                           // 当前缓冲帧数

    public int Count => _count;
    public uint NewestFrame => _newestFrame;
    public uint OldestFrame => _oldestFrame;
    public int Capacity => _capacity;

    /// <summary>
    /// 构造帧缓冲区。
    /// </summary>
    /// <param name="capacity">容量，自动向上取整为 2 的幂</param>
    public FrameBuffer(int capacity = 256)
    {
        // 向上取整到 2 的幂
        _capacity = 1;
        while (_capacity < capacity) _capacity <<= 1;
        _mask = _capacity - 1;
        _buffer = new FrameData[_capacity];
        _newestFrame = 0;
        _oldestFrame = 0;
        _count = 0;
    }

    /// <summary>
    /// 向缓冲区写入一帧数据。由网络线程调用。
    /// 不检查顺序——允许乱序到达（但太旧的帧会被丢弃）。
    /// </summary>
    public void EnqueueFrame(FrameData frame)
    {
        // 太旧的帧（已超出缓冲区窗口）直接丢弃
        if (_count > 0 && frame.FrameNumber <= _oldestFrame)
            return;

        int index = (int)(frame.FrameNumber & (uint)_mask);
        _buffer[index] = frame;

        if (_count == 0)
        {
            _oldestFrame = frame.FrameNumber;
            _newestFrame = frame.FrameNumber;
            _count = 1;
        }
        else
        {
            if (frame.FrameNumber > _newestFrame)
            {
                // 新帧比当前最大帧号大 → 扩展窗口
                uint gap = frame.FrameNumber - _newestFrame;
                // 如果 gap 太大，说明跳帧了——旧帧可能永不到达，直接推进 oldest
                if (gap > (uint)_capacity)
                {
                    _oldestFrame = frame.FrameNumber - (uint)_capacity + 1;
                    _count = _capacity;
                }
                else
                {
                    _count += (int)gap;
                    if (_count > _capacity)
                    {
                        // 窗口超出容量 → 推进 oldest，丢弃最旧帧
                        _oldestFrame += (uint)(_count - _capacity);
                        _count = _capacity;
                    }
                }
                _newestFrame = frame.FrameNumber;
            }
            // else: 乱序到达的旧帧（已在 oldest..newest 范围内），覆盖即可
        }
    }

    /// <summary>
    /// 尝试获取指定帧号的数据。由主线程（LockstepManager）调用。
    /// 如果帧数据尚未到达，返回 null。
    /// </summary>
    public FrameData TryGetFrame(uint frameNumber)
    {
        if (_count == 0 || frameNumber < _oldestFrame || frameNumber > _newestFrame)
            return null;

        int index = (int)(frameNumber & (uint)_mask);
        var frame = _buffer[index];
        // 验证帧号匹配（环形缓冲区可能被不同帧复用同一 slot）
        if (frame != null && frame.FrameNumber == frameNumber)
            return frame;
        return null;
    }

    /// <summary>
    /// 消费一帧后，推进 oldest 指针，释放缓冲区空间。
    /// </summary>
    public void ConsumeFrame(uint frameNumber)
    {
        if (_count > 0 && frameNumber >= _oldestFrame)
        {
            uint consumed = frameNumber - _oldestFrame + 1;
            _oldestFrame = frameNumber + 1;
            _count -= (int)consumed;
            if (_count < 0) _count = 0;
            if (_count == 0)
            {
                _newestFrame = 0;
                _oldestFrame = 0;
            }
        }
    }

    /// <summary>
    /// 检查指定帧号之前是否已连续缓存了 requiredCount 帧。
    /// 用于判断"预缓冲是否就绪"——比如要求缓冲满 8 帧才开始播放。
    /// </summary>
    public int CountConsecutiveFrom(uint fromFrame, int required)
    {
        int consecutive = 0;
        for (uint f = fromFrame; f <= _newestFrame && consecutive < required; f++)
        {
            if (TryGetFrame(f) != null)
                consecutive++;
            else
                break;
        }
        return consecutive;
    }
}
```

**核心设计**：
- 环形缓冲区用掩码取模（`index = frameNumber & mask`）替代 `%` 运算，快约 5-10 倍。
- 容量必须是 2 的幂——`FrameBuffer(256)` 自动向上取整。
- `EnqueueFrame` 是线程安全的（写操作由单一网络线程执行），读取由主线程执行——无锁设计依赖的是"生产者-消费者"的单写单读模式。
- `CountConsecutiveFrom()` 用于帧追赶时的"缓冲就绪判断"：如果当前落后服务器 5 帧，且连续缓存了 5 帧以上，就可以启动追赶。

---

### 2.3 NetworkClient.cs —— 网络层

网络层负责 UDP 通信。在帧同步中，网络层只做三件事：**发送本地输入**、**接收帧包**、**管理连接状态**。它不做任何帧逻辑——那是 LockstepManager 的职责。

```csharp
// NetworkClient.cs — UDP 网络通信层
// 职责：连接管理、发送输入包、接收帧包并喂入 FrameBuffer。
// 不包含任何帧逻辑——纯粹的传输层。

using System;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

/// <summary>
/// 网络消息类型标识（简化版：帧输入包）。
/// 完整协议设计见 tutorial 07。
/// </summary>
public enum MessageType : byte
{
    ConnectRequest  = 1,
    ConnectAck      = 2,
    PlayerInput     = 3,     // 客户端 → 服务器：本帧输入
    FrameBroadcast  = 4,     // 服务器 → 客户端：所有玩家的本帧输入集合
    Heartbeat       = 5,
}

/// <summary>
/// 网络层：使用 UDP Socket 收发数据。
/// 
/// 为什么用 UDP 而非 TCP？
/// - 帧同步的输入数据很小（几个字节/帧），丢一帧影响不大（有冗余/插值兜底）
/// - TCP 的可靠传输 = 丢包重传导致的队头阻塞 (Head-of-Line Blocking)，
///   在移动网络下会让后续所有帧都被阻塞，体验极差
/// - 帧同步容忍偶尔丢包（下帧数据可补），但不能容忍延迟抖动
/// 
/// 发送策略：每逻辑帧发送一次输入（约 15-66ms 间隔）
/// 接收策略：非阻塞轮询（30fps 逻辑帧率下，每 33ms 查询一次收包队列）
/// </summary>
public class NetworkClient : MonoBehaviour
{
    [Header("Network Config")]
    [SerializeField] private string _serverIP = "127.0.0.1";
    [SerializeField] private int _serverPort = 9999;
    [SerializeField] private int _localPort = 0; // 0 = 系统自动分配

    private UdpClient _udpClient;
    private IPEndPoint _serverEndPoint;
    private Thread _receiveThread;
    private volatile bool _isRunning;

    // 接收队列：网络线程写入，主线程读取
    private readonly System.Collections.Concurrent.ConcurrentQueue<byte[]> _receivedQueue =
        new System.Collections.Concurrent.ConcurrentQueue<byte[]>();

    // 引用
    private FrameBuffer _frameBuffer;
    private LockstepManager _lockstep;

    // 统计
    public int PacketsSent { get; private set; }
    public int PacketsReceived { get; private set; }
    public int PacketsLost { get; private set; }  // 估算，基于帧号跳变
    public bool IsConnected { get; private set; }

    void Awake()
    {
        _serverEndPoint = new IPEndPoint(IPAddress.Parse(_serverIP), _serverPort);
    }

    /// <summary>初始化并连接服务器（由 LockstepManager 在 Start 时调用）</summary>
    public void Initialize(FrameBuffer frameBuffer, LockstepManager lockstep)
    {
        _frameBuffer = frameBuffer;
        _lockstep = lockstep ?? throw new ArgumentNullException(nameof(lockstep));

        try
        {
            _udpClient = new UdpClient(_localPort);
            _udpClient.Client.ReceiveBufferSize = 256 * 1024; // 256KB 收缓冲
            _udpClient.Client.SendBufferSize = 64 * 1024;     // 64KB 发缓冲
            _isRunning = true;

            // 启动接收线程
            _receiveThread = new Thread(ReceiveLoop)
            {
                Name = "UDP-Receive",
                IsBackground = true
            };
            _receiveThread.Start();

            // 发送连接请求
            SendConnectRequest();
            Debug.Log($"[NetworkClient] 已启动，目标服务器: {_serverIP}:{_serverPort}");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[NetworkClient] 初始化失败: {ex.Message}");
        }
    }

    /// <summary>发送连接请求（简化：发送一次，期待服务器回复）</summary>
    private void SendConnectRequest()
    {
        var writer = new ByteWriter(16);
        writer.WriteByte((byte)MessageType.ConnectRequest);
        writer.WriteInt32(0); // 客户端版本号
        SendBytes(writer.GetBuffer(), writer.Length);
    }

    /// <summary>接收线程主循环</summary>
    private void ReceiveLoop()
    {
        while (_isRunning)
        {
            try
            {
                if (_udpClient.Available > 0)
                {
                    IPEndPoint remoteEP = new IPEndPoint(IPAddress.Any, 0);
                    byte[] data = _udpClient.Receive(ref remoteEP);
                    _receivedQueue.Enqueue(data);
                    PacketsReceived++;
                }
                else
                {
                    Thread.Sleep(1); // 无数据时短暂休眠，避免空转吃满 CPU
                }
            }
            catch (SocketException ex)
            {
                if (_isRunning)
                    Debug.LogError($"[NetworkClient] Socket 异常: {ex.Message}");
            }
            catch (ObjectDisposedException)
            {
                break; // socket 已关闭，正常退出
            }
        }
    }

    /// <summary>
    /// 每帧由主线程调用：处理接收队列中的消息。
    /// 这个设计避免了网络线程直接操作 Unity API（Unity 主线程限制）。
    /// </summary>
    public void UpdateReceive()
    {
        int processed = 0;
        while (_receivedQueue.TryDequeue(out byte[] data))
        {
            ProcessReceivedData(data);
            processed++;
            if (processed > 20) break; // 单帧最多处理 20 个包，防止卡帧
        }
    }

    /// <summary>解析接收到的数据包</summary>
    private void ProcessReceivedData(byte[] data)
    {
        if (data.Length < 1) return;

        var reader = new ByteReader(data);
        MessageType msgType = (MessageType)reader.ReadByte();

        switch (msgType)
        {
            case MessageType.ConnectAck:
                byte assignedPlayerId = reader.ReadByte();
                uint startFrame = reader.ReadUInt32();
                int totalPlayers = reader.ReadByte();
                IsConnected = true;
                _lockstep.OnConnected(assignedPlayerId, startFrame, totalPlayers);
                Debug.Log($"[NetworkClient] 连接确认: PlayerID={assignedPlayerId}, StartFrame={startFrame}, TotalPlayers={totalPlayers}");
                break;

            case MessageType.FrameBroadcast:
                uint frameNumber = reader.ReadUInt32();
                int playerCount = reader.ReadByte();
                var frameData = new FrameData(frameNumber, playerCount);
                for (int i = 0; i < playerCount; i++)
                {
                    frameData.PlayerInputs[i] = reader.ReadByte();
                }
                frameData.ArrivalTimestamp = System.Diagnostics.Stopwatch.GetTimestamp();
                _frameBuffer.EnqueueFrame(frameData);
                break;

            case MessageType.Heartbeat:
                // 心跳响应：可用于计算 RTT
                break;

            default:
                Debug.LogWarning($"[NetworkClient] 未知消息类型: {msgType}");
                break;
        }
    }

    /// <summary>发送本帧输入到服务器</summary>
    public void SendInput(uint frameNumber, byte playerId, byte inputData)
    {
        if (!IsConnected || _udpClient == null) return;

        var writer = new ByteWriter(32);
        writer.WriteByte((byte)MessageType.PlayerInput);
        writer.WriteUInt32(frameNumber);
        writer.WriteByte(playerId);
        writer.WriteByte(inputData);
        SendBytes(writer.GetBuffer(), writer.Length);
        PacketsSent++;
    }

    private void SendBytes(byte[] data, int length)
    {
        try
        {
            _udpClient.Send(data, length, _serverEndPoint);
        }
        catch (Exception ex)
        {
            Debug.LogError($"[NetworkClient] 发送失败: {ex.Message}");
        }
    }

    void OnDestroy()
    {
        _isRunning = false;
        _receiveThread?.Join(500); // 等待线程退出，最多等 500ms
        _udpClient?.Close();
        _udpClient?.Dispose();
    }
}

/// <summary>
/// 简易的字节流写入器（替代 BinaryWriter，避免其内部缓冲和编码开销）。
/// 帧同步中只写原始字节——不需要任何编码/解码逻辑。
/// </summary>
public class ByteWriter
{
    private byte[] _buffer;
    private int _position;

    public int Length => _position;

    public ByteWriter(int capacity)
    {
        _buffer = new byte[capacity];
        _position = 0;
    }

    public void WriteByte(byte value) { _buffer[_position++] = value; }
    public void WriteUInt32(uint value)
    {
        _buffer[_position++] = (byte)(value);
        _buffer[_position++] = (byte)(value >> 8);
        _buffer[_position++] = (byte)(value >> 16);
        _buffer[_position++] = (byte)(value >> 24);
    }
    public void WriteInt32(int value) { WriteUInt32((uint)value); }
    public byte[] GetBuffer() => _buffer;
}

/// <summary>
/// 简易的字节流读取器。
/// </summary>
public class ByteReader
{
    private byte[] _buffer;
    private int _position;

    public ByteReader(byte[] data)
    {
        _buffer = data;
        _position = 0;
    }

    public byte ReadByte() => _buffer[_position++];
    public uint ReadUInt32()
    {
        uint value = (uint)(_buffer[_position] | (_buffer[_position + 1] << 8) |
                            (_buffer[_position + 2] << 16) | (_buffer[_position + 3] << 24));
        _position += 4;
        return value;
    }
    public int ReadInt32() => (int)ReadUInt32();
}
```

**关键设计决策**：

1. **UDP 而非 TCP**：帧同步输入包很小（典型 8-12 字节），丢失一帧不会致命——下一帧的数据会覆盖。TCP 的队头阻塞在移动网络下会让数百毫秒的延迟累积。UDP + 应用层冗余（下帧携带上帧输入）是标准做法。

2. **接收线程 + 主线程处理**：网络线程只负责 `UdpClient.Receive()` 并入队，不做任何解析。主线程在 `UpdateReceive()` 中解包——避免线程安全问题，也符合 Unity 的 API 调用限制。

3. **ByteWriter/ByteReader**：不用 `BinaryWriter`/`BitConverter`。帧同步的序列化极简——直接操作字节数组，零额外分配，且跨平台字节序可控（这里用小端序，C# 默认）。

4. **`ConcurrentQueue`**：接收队列的线程安全由 BCL 保证，避免了手动加锁的性能损失。

---

### 2.4 InputManager.cs —— 输入收集

输入收集层的核心挑战不是"怎么读按键"，而是**怎么把硬件输入映射为确定性的逻辑指令**。

```csharp
// InputManager.cs — 输入收集与标准化
// 职责：将 Unity Input（键盘/触屏/鼠标）映射为标准化指令字节，
//       为每个逻辑帧收集该帧内的操作，打包为一个 byte 指令。

using UnityEngine;

/// <summary>
/// 输入指令格式（每帧每个玩家 1 字节）：
///   bit 0-1: 移动方向 (0=不动, 1=上, 2=下, 3=左, 4=右)
///   bit 2:   攻击键
///   bit 3:   技能1
///   bit 4-7: 保留
/// 
/// 如果一帧内有多个操作（先移动再攻击），需要帧内合并策略：
///   本 Demo 采用"合并"模式——移动方向 + 攻击位可以同时存在。
///   实际项目可能需要"操作队列"模式（见 5.3 节扩展讨论）。
/// </summary>
public class InputManager
{
    public const byte INPUT_NONE        = 0;
    public const byte INPUT_MOVE_UP     = 1;
    public const byte INPUT_MOVE_DOWN   = 2;
    public const byte INPUT_MOVE_LEFT   = 3;
    public const byte INPUT_MOVE_RIGHT  = 4;
    public const byte INPUT_ATTACK      = 0x04; // bit 2
    public const byte INPUT_SKILL1      = 0x08; // bit 3

    // 当前帧的输入（在 Update 中累积，在逻辑帧开始时读取并清空）
    private byte _currentInput = 0;
    private bool _hasInputThisFrame = false;

    /// <summary>
    /// 每渲染帧调用：累积玩家操作到当前输入缓存。
    /// Unity 的 Input 系统是帧相关的，每帧读一次即可。
    /// </summary>
    public void PollInput()
    {
        byte input = INPUT_NONE;

        // ── 移动输入 ────────────────────────────
        // 使用 Unity 旧 Input 系统（简单、跨平台、无 GC）
        float h = Input.GetAxisRaw("Horizontal");
        float v = Input.GetAxisRaw("Vertical");

        // 优先处理水平方向（大多数游戏的惯例）
        if (h > 0.1f)
            input = INPUT_MOVE_RIGHT;
        else if (h < -0.1f)
            input = INPUT_MOVE_LEFT;
        else if (v > 0.1f)
            input = INPUT_MOVE_UP;
        else if (v < -0.1f)
            input = INPUT_MOVE_DOWN;

        // ── 攻击输入 ────────────────────────────
        if (Input.GetKeyDown(KeyCode.J) || Input.GetKeyDown(KeyCode.Space))
            input |= INPUT_ATTACK;

        // ── 技能输入 ────────────────────────────
        if (Input.GetKeyDown(KeyCode.K))
            input |= INPUT_SKILL1;

        // 累积到当前帧
        if (input != INPUT_NONE)
        {
            _currentInput |= input; // 合并模式：保留所有操作
            _hasInputThisFrame = true;
        }
    }

    /// <summary>
    /// 每逻辑帧开始时调用：读取并清空当前逻辑帧的输入。
    /// 
    /// 注意"合并模式"的限制：
    ///   如果玩家在同一渲染帧内按下"A→D"，会得到"同时按了左和右"的歧义输入。
    ///   解决方法：逻辑帧中按方向优先级解析（先检查新覆盖），或用"最后写入覆盖"策略。
    ///   本 Demo 中，由于 Input.GetAxisRaw 返回的是"当前状态"而非"事件"，方向由最后按下的键决定，
    ///   所以实际上方向不会冲突（只有松开+再按才能改变方向）。
    /// </summary>
    public byte ConsumeInput()
    {
        byte result = _currentInput;
        _currentInput = 0;
        _hasInputThisFrame = false;
        return result;
    }

    /// <summary>
    /// 将输入字节解码为可读字符串（调试用）
    /// </summary>
    public static string InputToString(byte input)
    {
        if (input == 0) return "NONE";
        var parts = new System.Collections.Generic.List<string>();
        byte dir = (byte)(input & 0x03);
        switch (dir)
        {
            case 1: parts.Add("UP"); break;
            case 2: parts.Add("DOWN"); break;
            case 3: parts.Add("LEFT"); break;
            case 4: parts.Add("RIGHT"); break;
        }
        if ((input & INPUT_ATTACK) != 0) parts.Add("ATTACK");
        if ((input & INPUT_SKILL1) != 0) parts.Add("SKILL1");
        return string.Join("+", parts);
    }
}
```

**关键设计**：

- **输入压缩为 1 字节**：帧同步的带宽价值在于"只传输入"。每个玩家每帧 1 字节 → 10 人对战、15fps → 上行仅 150 bytes/s。
- **合并 vs 队列**：本 Demo 采用合并模式（`|=`），适合简单场景。王者荣耀等 MOBA 用操作队列——每逻辑帧可以执行多个操作（移动→技能→攻击）。
- **`PollInput()` 在渲染帧中调用**，`ConsumeInput()` 在逻辑帧开始时调用。两者频率不同——4 个渲染帧对应 1 个逻辑帧时，`PollInput()` 被调 4 次，但最终消费时只有最后一次合并结果。
- **使用 `Input.GetAxisRaw`** 而非 `Input.GetAxis`：前者无平滑，返回 -1/0/1，映射到离散方向更明确。

---

### 2.5 GameLogic.cs —— 纯逻辑层

这是帧同步的核心——确定性逻辑引擎。它**绝不访问 Unity 的 Transform、GameObject、Time.deltaTime 或任何非确定性 API**。

```csharp
// GameLogic.cs — 确定性游戏逻辑引擎
// 规则：
//   1. 不引用 UnityEngine（除 Editor 调试宏外）
//   2. 不使用 float/double（全部用 FP）
//   3. 不使用 System.Random（用确定性 PRNG）
//   4. 不依赖系统时间（逻辑帧间隔由调用者传入，固定值）
//   5. 所有遍历按确定顺序（ID/索引升序）

using System.Collections.Generic;

/// <summary>
/// 实体类型标识
/// </summary>
public enum EntityType : byte
{
    Player = 1,
    Projectile = 2,
}

/// <summary>
/// 逻辑层实体状态。仅包含游戏逻辑关心的数据，不含任何表现层字段。
/// 每个逻辑帧结束后，这个结构体就是该实体的"权威状态"。
/// </summary>
public class LogicEntity
{
    public uint Id;
    public EntityType Type;
    public byte OwnerPlayerId;
    public FPVector2 Position;
    public FPVector2 Velocity;
    public int HP;
    public int MaxHP;
    public FP AttackCooldown;     // 攻击冷却（逻辑帧计数）
    public byte FacingDirection;  // 1=上 2=下 3=左 4=右

    public bool IsDead => HP <= 0;

    public LogicEntity(uint id, EntityType type, byte ownerId)
    {
        Id = id;
        Type = type;
        OwnerPlayerId = ownerId;
        Position = FPVector2.Zero;
        Velocity = FPVector2.Zero;
        HP = 100;
        MaxHP = 100;
        AttackCooldown = FP.Zero;
        FacingDirection = 4; // 默认向右
    }
}

/// <summary>
/// 确定性随机数生成器 (Xorshift128+)。
/// 种子相同 → 序列完全相同 → 所有客户端产生相同的随机事件。
/// </summary>
public class DeterministicRandom
{
    private ulong _state0, _state1;

    public DeterministicRandom(ulong seed)
    {
        // 简单种子扩展
        _state0 = seed ^ 0xDEADBEEF12345678UL;
        _state1 = (seed >> 32) ^ 0x87654321FEDCBA98UL;
        if (_state0 == 0 && _state1 == 0)
            _state0 = 1; // 不能全零
    }

    /// <summary>返回 [0, max) 的整数</summary>
    public int Next(int max)
    {
        ulong s1 = _state0;
        ulong s0 = _state1;
        _state0 = s0;
        s1 ^= s1 << 23;
        _state1 = s1 ^ s0 ^ (s1 >> 18) ^ (s0 >> 5);
        return (int)((_state1 + s0) % (ulong)max);
    }

    /// <summary>返回 Q16.16 格式的 FP，范围 [0, 1)</summary>
    public FP NextFP()
    {
        return FP.CreateFromRaw((int)(Next(FP.SCALE)));
    }
}

/// <summary>
/// 游戏逻辑引擎。
/// 
/// 每逻辑帧调用 ExecuteFrame()：
///   输入：上一帧状态 + 本帧所有玩家输入
///   输出：更新后的状态（原地修改 entity 列表）
/// 
/// 这里实现一个简单的 2 人对战 Demo：
///   玩家操作 → 移动 1 单位/帧 或 攻击（近战范围 1.5 单位，伤害 20）
/// </summary>
public class GameLogic
{
    // ── 常量（逻辑帧单位）─────────────────────────
    private static readonly FP MOVE_SPEED      = FP.CreateFromFloat(0.15f); // 每逻辑帧移动距离
    private static readonly FP ATTACK_RANGE    = FP.CreateFromFloat(1.5f);  // 攻击范围
    private static readonly int ATTACK_DAMAGE  = 20;                        // 攻击伤害
    private static readonly int ATTACK_COOLDOWN_FRAMES = 10;                // 攻击冷却（逻辑帧数）
    private static readonly FP MAP_WIDTH       = FP.CreateFromFloat(10f);
    private static readonly FP MAP_HEIGHT      = FP.CreateFromFloat(10f);

    // ── 状态 ──────────────────────────────────────
    public List<LogicEntity> Entities { get; private set; } = new List<LogicEntity>();
    public uint CurrentFrame { get; private set; }
    private DeterministicRandom _random;
    private uint _nextEntityId = 1;

    // ── 统计 ──────────────────────────────────────
    public int TotalDamageDealt { get; private set; }

    /// <summary>初始化游戏世界（所有客户端必须使用相同的种子和初始状态）</summary>
    public void Initialize(ulong randomSeed, int playerCount)
    {
        _random = new DeterministicRandom(randomSeed);
        Entities.Clear();
        CurrentFrame = 0;
        TotalDamageDealt = 0;

        // 创建玩家实体，分散在地图四角
        FPVector2[] spawnPositions = new FPVector2[]
        {
            new FPVector2(FP.CreateFromFloat(-3), FP.CreateFromFloat(-3)), // P1
            new FPVector2(FP.CreateFromFloat(3), FP.CreateFromFloat(3)),   // P2
            new FPVector2(FP.CreateFromFloat(-3), FP.CreateFromFloat(3)),  // P3
            new FPVector2(FP.CreateFromFloat(3), FP.CreateFromFloat(-3)),  // P4
        };

        for (byte i = 0; i < playerCount && i < spawnPositions.Length; i++)
        {
            var entity = new LogicEntity(_nextEntityId++, EntityType.Player, i)
            {
                Position = spawnPositions[i],
                HP = 100,
                MaxHP = 100,
                FacingDirection = (byte)(i + 1), // 不同朝向区分
            };
            Entities.Add(entity);
        }
    }

    /// <summary>
    /// 执行一个逻辑帧。
    /// 
    /// 这是确定性引擎的核心——相同输入 + 相同状态 → 相同输出。
    /// 
    /// 遍历顺序：按 entity.Id 升序。这是确定性的关键——不同的遍历顺序
    /// 可能导致不同的逻辑结果（例如两个玩家同时攻击对方，谁先结算）。
    /// </summary>
    /// <param name="frameInputs">frameInputs[playerIndex] = 该玩家本帧的输入字节</param>
    public void ExecuteFrame(byte[] frameInputs)
    {
        CurrentFrame++;

        // ── 第一步：处理每个玩家的输入（按玩家索引顺序）────────────
        for (int i = 0; i < frameInputs.Length; i++)
        {
            byte input = frameInputs[i];
            if (input == 0) continue; // 无操作，跳过

            // 找到该玩家的实体
            LogicEntity playerEntity = FindEntityByOwner((byte)i);
            if (playerEntity == null || playerEntity.IsDead) continue;

            // 解析输入
            byte direction = (byte)(input & 0x03);
            bool attack = (input & InputManager.INPUT_ATTACK) != 0;
            bool skill = (input & InputManager.INPUT_SKILL1) != 0;

            // 处理移动
            if (direction != 0)
            {
                FPVector2 moveDir = DirectionToVector(direction);
                playerEntity.Position += moveDir * MOVE_SPEED;
                playerEntity.FacingDirection = direction;

                // 边界钳制
                playerEntity.Position = ClampToMap(playerEntity.Position);
            }

            // 处理攻击（冷却中不能攻击）
            if (attack && playerEntity.AttackCooldown.RawValue <= 0)
            {
                PerformAttack(playerEntity);
                playerEntity.AttackCooldown = FP.CreateFromInt(ATTACK_COOLDOWN_FRAMES);
            }
        }

        // ── 第二步：冷却递减（每帧对所有实体）─────────────────────
        // 遍历顺序：按 Id 升序（确定性）
        Entities.Sort((a, b) => a.Id.CompareTo(b.Id)); // 确保顺序
        for (int i = 0; i < Entities.Count; i++)
        {
            var entity = Entities[i];
            if (entity.AttackCooldown.RawValue > 0)
            {
                entity.AttackCooldown -= FP.One;
                if (entity.AttackCooldown.RawValue < 0)
                    entity.AttackCooldown = FP.Zero;
            }
        }

        // ── 第三步：移除死亡实体（清理由逻辑层负责）─────────────────
        Entities.RemoveAll(e => e.IsDead);
    }

    /// <summary>执行攻击：检查范围内的敌方实体并造成伤害</summary>
    private void PerformAttack(LogicEntity attacker)
    {
        foreach (var target in Entities)
        {
            if (target.Id == attacker.Id) continue;
            if (target.IsDead) continue;

            // 计算距离
            FPVector2 diff = target.Position - attacker.Position;
            FP distance = diff.Magnitude();

            if (distance.RawValue <= ATTACK_RANGE.RawValue)
            {
                // 造成伤害
                target.HP -= ATTACK_DAMAGE;
                TotalDamageDealt += ATTACK_DAMAGE;

                if (target.HP < 0) target.HP = 0;

                // 攻击只命中第一个目标（单体攻击）
                break;
            }
        }
    }

    /// <summary>按 OwnerPlayerId 查找实体</summary>
    private LogicEntity FindEntityByOwner(byte ownerId)
    {
        foreach (var entity in Entities)
        {
            if (entity.OwnerPlayerId == ownerId && entity.Type == EntityType.Player)
                return entity;
        }
        return null;
    }

    /// <summary>方向枚举 → 单位向量</summary>
    private static FPVector2 DirectionToVector(byte dir)
    {
        switch (dir)
        {
            case InputManager.INPUT_MOVE_UP:    return new FPVector2(FP.Zero,  FP.One);
            case InputManager.INPUT_MOVE_DOWN:  return new FPVector2(FP.Zero, -FP.One);
            case InputManager.INPUT_MOVE_LEFT:  return new FPVector2(-FP.One, FP.Zero);
            case InputManager.INPUT_MOVE_RIGHT: return new FPVector2(FP.One,  FP.Zero);
            default: return FPVector2.Zero;
        }
    }

    /// <summary>钳制位置到地图边界内</summary>
    private static FPVector2 ClampToMap(FPVector2 pos)
    {
        FP halfW = MAP_WIDTH / FP.Two;
        FP halfH = MAP_HEIGHT / FP.Two;
        int x = pos.X.RawValue;
        int y = pos.Y.RawValue;
        if (x < -halfW.RawValue) x = -halfW.RawValue;
        if (x > halfW.RawValue)  x = halfW.RawValue;
        if (y < -halfH.RawValue) y = -halfH.RawValue;
        if (y > halfH.RawValue)  y = halfH.RawValue;
        return new FPVector2(FP.CreateFromRaw(x), FP.CreateFromRaw(y));
    }

    /// <summary>
    /// 计算当前帧的状态哈希（用于 Desync 检测）。
    /// 对每个实体的关键字段做 XOR 哈希。
    /// </summary>
    public ulong ComputeStateHash()
    {
        ulong hash = 0x9E3779B97F4A7C15UL; // 黄金比例初始值
        hash ^= CurrentFrame;

        foreach (var entity in Entities)
        {
            hash ^= entity.Id;
            hash ^= (ulong)entity.Position.X.RawValue;
            hash ^= ((ulong)entity.Position.Y.RawValue) << 32;
            hash ^= (ulong)(uint)entity.HP;
            // 简单的位混合
            hash = (hash ^ (hash >> 30)) * 0xBF58476D1CE4E5B9UL;
            hash = (hash ^ (hash >> 27)) * 0x94D049BB133111EBUL;
        }
        return hash ^ (hash >> 31);
    }
}
```

**关键设计决策**：

1. **逐帧冷却用逻辑帧数而非秒数**：`AttackCooldown` 用 FP 表示"剩余冷却帧数"，每帧减 `FP.One`。这样不依赖系统时间，所有客户端一致。游戏设计层面，一个攻击冷却 = 10 逻辑帧 = 666ms（15fps）。

2. **遍历顺序确定性**：`Entities.Sort((a, b) => a.Id.CompareTo(b.Id))` 在每帧开始时排序。即使 List 在不同帧被修改过，遍历顺序依然一致。生产级项目可以在插入时保证有序（SortedList / 按 Id 插入），避免每帧排序的 O(n log n) 开销。

3. **移除死亡实体**：逻辑层负责清理——`Entities.RemoveAll(e => e.IsDead)`。表现层检测到实体消失后，触发死亡动画。

4. **状态哈希**：`ComputeStateHash()` 为 Desync 检测提供基础。每 N 帧（如每 100 帧）所有客户端计算哈希值并交换对比——本机结果和在服务器上的一致即无 Desync。

5. **`ExecuteFrame` 是纯函数**：给定相同的 `Entities` 列表内容 + 相同的 `frameInputs`，输出完全确定。没有读取系统时间、没有随机数、没有外部状态。

---

### 2.6 LockstepManager.cs —— 核心帧管理器

这是整个客户端的"大脑"。所有模块都围绕它运转。

```csharp
// LockstepManager.cs — 核心帧管理器
// 职责：
//   1. 协调 InputManager / FrameBuffer / GameLogic / NetworkClient
//   2. 决定何时推进逻辑帧（正常播放 / 帧追赶 / 等待缓冲）
//   3. 统一所有模块的生命周期
// 这是客户端的主状态机——所有其他组件只提供服务，LockstepManager 做决策。

using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 帧管理器的运行状态
/// </summary>
public enum LockstepState
{
    Disconnected,      // 未连接
    Buffering,         // 预缓冲中：积累足够的帧数据再开始播放
    Playing,           // 正常播放：按固定间隔推进逻辑帧
    CatchingUp,        // 帧追赶：加速推进以追上服务器（落后太多时）
    Paused,            // 暂停（网络断开/切换后台等）
}

/// <summary>
/// LockstepManager — 帧同步客户端核心
/// 
/// 生命周期：
///   1. Awake:  创建所有子模块
///   2. Start:  连接服务器
///   3. OnConnected: 收到 ConnectAck → 创建游戏世界 → 进入 Buffering
///   4. Buffering 完成 → 进入 Playing
///   5. 每帧 Update: PollInput → UpdateReceive → MaybeAdvanceFrame
///   6. 每逻辑帧: 执行 GameLogic.ExecuteFrame() → 刷新 RenderProxy
/// </summary>
public class LockstepManager : MonoBehaviour
{
    [Header("Frame Config")]
    [SerializeField] private int _logicFrameRate = 15;        // 逻辑帧率 (Hz)
    [SerializeField] private int _bufferSize = 8;             // 预缓冲帧数（2 人对战: 4-8 帧 ≈ 266-533ms）
    [SerializeField] private int _catchUpThreshold = 4;       // 落后超过此帧数 → 进入追赶模式
    [SerializeField] private int _maxCatchUpFramesPerUpdate = 3; // 每次 Update 最多追赶多少帧

    [Header("References")]
    [SerializeField] private RenderProxy _renderProxy;        // 表现层代理
    [SerializeField] private DebugPanel _debugPanel;          // 调试面板

    // ── 子模块 ──────────────────────────────────────
    private InputManager _inputManager;
    private FrameBuffer _frameBuffer;
    private NetworkClient _networkClient;
    private GameLogic _gameLogic;

    // ── 状态 ────────────────────────────────────────
    private LockstepState _state = LockstepState.Disconnected;
    private uint _currentFrame;                    // 当前已执行的逻辑帧号
    private uint _serverFrame;                     // 服务器广播的最新帧号
    private byte _localPlayerId;                   // 本机玩家 ID
    private int _totalPlayers;                     // 总玩家数
    private float _logicFrameInterval;             // 逻辑帧间隔（秒）
    private float _accumulator;                    // 时间累积器（用于固定时间步长）

    // ── Desync 检测 ────────────────────────────────
    private readonly List<ulong> _frameHashes = new List<ulong>(); // 每 100 帧记录一次哈希
    private const int HASH_CHECK_INTERVAL = 100;    // 每 100 帧检查一次

    // ── 统计 ────────────────────────────────────────
    public LockstepState CurrentState => _state;
    public uint CurrentFrameNumber => _currentFrame;
    public int BufferedFrameCount => _frameBuffer?.Count ?? 0;
    public float LogicFrameInterval => _logicFrameInterval;

    // ── 回调（供其他模块注册）────────────────────────
    public System.Action<LogicEntity> OnEntityUpdated;  // 实体更新后回调
    public System.Action<uint, ulong> OnFrameHashReady; // 帧哈希就绪回调（供调试）

    void Awake()
    {
        // 初始化子模块
        _inputManager = new InputManager();
        _frameBuffer = new FrameBuffer(256);
        _gameLogic = new GameLogic();

        // 网络客户端从当前 GameObject 获取（可在 Inspector 挂载或运行时创建）
        _networkClient = GetComponent<NetworkClient>();
        if (_networkClient == null)
            _networkClient = gameObject.AddComponent<NetworkClient>();

        _logicFrameInterval = 1.0f / _logicFrameRate;
        _accumulator = 0f;
    }

    void Start()
    {
        _networkClient.Initialize(_frameBuffer, this);
        _state = LockstepState.Disconnected;
    }

    /// <summary>收到 ConnectAck 后，网络层回调此方法</summary>
    public void OnConnected(byte playerId, uint startFrame, int totalPlayers)
    {
        _localPlayerId = playerId;
        _serverFrame = startFrame;
        _totalPlayers = totalPlayers;
        _currentFrame = startFrame - 1; // 下一帧将执行 startFrame

        // 初始化游戏世界（使用确定性随机种子）
        // 种子由服务器统一分配，所有客户端相同
        ulong gameSeed = (ulong)startFrame * 0x123456789ABCDEFUL;
        _gameLogic.Initialize(gameSeed, totalPlayers);

        // 进入预缓冲状态
        _state = LockstepState.Buffering;
        _accumulator = 0f;
        Debug.Log($"[LockstepManager] 已连接，进入预缓冲模式 (BufferSize={_bufferSize})");
    }

    void Update()
    {
        // ── 第一步：收集输入（每个渲染帧都执行）───────────────
        _inputManager.PollInput();

        // ── 第二步：处理网络收包 ────────────────────────────
        _networkClient.UpdateReceive();

        // ── 第三步：根据状态决定是否推进逻辑帧 ────────────────
        switch (_state)
        {
            case LockstepState.Buffering:
                UpdateBuffering();
                break;
            case LockstepState.Playing:
                UpdatePlaying();
                break;
            case LockstepState.CatchingUp:
                UpdateCatchingUp();
                break;
            case LockstepState.Disconnected:
            case LockstepState.Paused:
                break;
        }
    }

    /// <summary>预缓冲阶段：等待足够的帧数据就绪</summary>
    private void UpdateBuffering()
    {
        // 检查缓冲区中从 currentFrame+1 开始是否有连续的 bufferSize 帧
        uint nextFrame = _currentFrame + 1;
        int consecutive = _frameBuffer.CountConsecutiveFrom(nextFrame, _bufferSize);

        if (consecutive >= _bufferSize)
        {
            _state = LockstepState.Playing;
            _accumulator = 0f;
            Debug.Log($"[LockstepManager] 预缓冲完成 ({consecutive} 帧就绪)，开始播放");
        }
    }

    /// <summary>正常播放阶段：按固定间隔推进逻辑帧</summary>
    private void UpdatePlaying()
    {
        // 检查是否需要追赶（落后服务器太多）
        int behind = (int)(_serverFrame - _currentFrame);
        if (behind > _catchUpThreshold)
        {
            _state = LockstepState.CatchingUp;
            Debug.Log($"[LockstepManager] 落后 {behind} 帧，进入追赶模式");
            return;
        }

        // 固定时间步长推进
        _accumulator += Time.deltaTime;
        int framesAdvanced = 0;

        while (_accumulator >= _logicFrameInterval)
        {
            _accumulator -= _logicFrameInterval;
            if (AdvanceFrame())
                framesAdvanced++;
            else
                break; // 下一帧数据未就绪 → 等待

            if (framesAdvanced >= _maxCatchUpFramesPerUpdate)
                break; // 单帧最多推进 N 帧，防止卡帧
        }
    }

    /// <summary>帧追赶阶段：快速消费缓冲帧，追上服务器进度</summary>
    private void UpdateCatchingUp()
    {
        int behind = (int)(_serverFrame - _currentFrame);
        if (behind <= 1)
        {
            _state = LockstepState.Playing;
            _accumulator = 0f;
            Debug.Log("[LockstepManager] 追赶完成，恢复正常播放");
            return;
        }

        // 加速推进：每帧最多执行 _maxCatchUpFramesPerUpdate 个逻辑帧
        int advanced = 0;
        for (int i = 0; i < _maxCatchUpFramesPerUpdate; i++)
        {
            if (!AdvanceFrame())
                break;
            advanced++;
        }

        if (advanced == 0)
        {
            // 没有帧数据可消费 → 等待缓冲或跳帧
            // 如果等待太久（超时），直接跳帧（用空输入填充）
            Debug.LogWarning("[LockstepManager] 追赶中但无可用帧数据，等待中...");
        }
    }

    /// <summary>
    /// 推进一个逻辑帧。
    /// 
    /// 步骤：
    ///   1. 从 InputManager 消费本地输入
    ///   2. 发送本地输入到服务器
    ///   3. 从 FrameBuffer 获取完整输入集合（所有玩家）
    ///   4. 调用 GameLogic.ExecuteFrame()
    ///   5. 通知 RenderProxy 更新表现
    ///   6. 检测 Desync（定期）
    ///   7. 消费缓冲区中的该帧（释放空间）
    /// </summary>
    /// <returns>true=成功推进一帧, false=数据未就绪</returns>
    private bool AdvanceFrame()
    {
        uint nextFrame = _currentFrame + 1;

        // ── 1. 消费本地输入并发送 ──────────────────────
        byte localInput = _inputManager.ConsumeInput();
        _networkClient.SendInput(nextFrame, _localPlayerId, localInput);

        // ── 2. 从缓冲区获取完整输入 ────────────────────
        FrameData frameData = _frameBuffer.TryGetFrame(nextFrame);
        if (frameData == null)
            return false; // 数据未到达

        // ── 3. 执行逻辑帧 ──────────────────────────────
        _gameLogic.ExecuteFrame(frameData.PlayerInputs);
        _currentFrame = nextFrame;
        _serverFrame = System.Math.Max(_serverFrame, _frameBuffer.NewestFrame);

        // ── 4. 通知表现层 ──────────────────────────────
        if (_renderProxy != null)
            _renderProxy.OnLogicFrameCompleted(_gameLogic.Entities);

        // ── 5. Desync 检测 ─────────────────────────────
        if (_currentFrame % HASH_CHECK_INTERVAL == 0)
        {
            ulong hash = _gameLogic.ComputeStateHash();
            _frameHashes.Add(hash);
            OnFrameHashReady?.Invoke(_currentFrame, hash);
            // 生产环境中：将 hash 发送给服务器，服务器比对所有客户端的结果
        }

        // ── 6. 消费缓冲区中的该帧 ───────────────────────
        _frameBuffer.ConsumeFrame(nextFrame);

        return true;
    }

    /// <summary>获取帧哈希历史（调试面板用）</summary>
    public List<ulong> GetFrameHashes() => _frameHashes;

    /// <summary>获取当前所有逻辑实体的快照（表现层用）</summary>
    public List<LogicEntity> GetEntitySnapshot() => _gameLogic.Entities;

    /// <summary>断线/暂停时调用</summary>
    public void Pause() { _state = LockstepState.Paused; }
    public void Resume() { _state = LockstepState.Playing; }
}
```

**核心设计决策**：

1. **帧缓冲 + 预播放**：客户端不会一收到帧就执行，而是先在 `FrameBuffer` 中缓存 `_bufferSize` 帧（典型值 4-8 帧 ≈ 266-533ms）。这笔"时间债"换来的是网络抖动平滑——即使服务器连续 200ms 没发帧，客户端也有缓冲可播。

2. **固定时间步长 (`_accumulator`)**：逻辑帧按固定间隔推进（15Hz → 66ms），不受渲染帧率波动影响。渲染帧可能 30fps 或 144fps，但逻辑帧始终每 66ms 一步。这是确定性要求的——`Time.deltaTime` 不被用于逻辑计算。

3. **帧追赶 (`CatchingUp`)**: 当客户端落后服务器超过阈值（如 4 帧 → 266ms），进入追赶模式——每渲染帧执行多个逻辑帧，直到追上。追赶期间表现层可以跳过插值动画，直接"快进"到最新状态。

4. **单帧推进上限 (`_maxCatchUpFramesPerUpdate`)**：防止追赶时一次性执行太多逻辑帧卡死主线程。即使落后 100 帧，每次 Update 最多追赶 3 帧——这大约需要 2.2 秒追完（3帧/16ms × 100帧 / 60fps）。

5. **Desync 检测 + 帧哈希**：每 100 帧计算一次状态哈希。生产环境中所有客户端将哈希发送给服务器，服务器比对——任何不一致的客户端标记为 Desync，触发断线重连或日志上报。

---

### 2.7 RenderProxy.cs —— 表现层插值

逻辑层和表现层之间的桥梁。它从 `LockstepManager` 获取逻辑实体快照，驱动 Unity 的 `GameObject`/`Transform`。

```csharp
// RenderProxy.cs — 表现层代理
// 职责：将逻辑层的 FP 位置/状态映射到 Unity 表现层，使用插值消除逻辑帧的"跳跃感"。
// 
// 为什么需要插值？
//   逻辑帧只有 15Hz（66ms/帧），如果直接设置 transform.position = 逻辑位置，
//   实体会"瞬移"——每 66ms 跳一次。视觉上非常糟糕。
//   解决：在连续两帧逻辑位置之间做线性插值（Lerp），让实体看起来平滑移动。

using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 表现层的实体状态缓存。每个逻辑实体对应一个表现代理。
/// </summary>
public class RenderEntity
{
    public uint LogicEntityId;
    public GameObject GameObject;
    public Transform Transform;
    public SpriteRenderer Renderer;
    public Vector3 PreviousPosition;    // 上逻辑帧的位置（浮点）
    public Vector3 TargetPosition;      // 当前逻辑帧的位置（浮点）
    public float InterpTime;            // 插值计时器 (0..1)
}

public class RenderProxy : MonoBehaviour
{
    [Header("Rendering")]
    [SerializeField] private GameObject _playerPrefab;      // 玩家表现预制体
    [SerializeField] private float _interpDuration = 0.066f; // 插值时间（= 1/15 ≈ 0.066s，与逻辑帧间隔一致）
    [SerializeField] private Color _localPlayerColor = Color.green;
    [SerializeField] private Color _remotePlayerColor = Color.red;

    private LockstepManager _lockstep;
    private Dictionary<uint, RenderEntity> _renderEntities = new Dictionary<uint, RenderEntity>();
    private float _accumulatedTime; // 用于插值的时间基准

    // ── 初始化 ──────────────────────────────────────
    void Start()
    {
        _lockstep = GetComponent<LockstepManager>();
        if (_lockstep == null)
        {
            Debug.LogError("[RenderProxy] 必须在同一 GameObject 上挂载 LockstepManager");
            enabled = false;
            return;
        }
    }

    /// <summary>
    /// 每逻辑帧完成后由 LockstepManager 调用。
    /// 注意：这发生在 Update 过程中，不等同于 LateUpdate。
    /// 这里的"上一帧"指的是"上一个逻辑帧"——可能和渲染帧不同步。
    /// </summary>
    public void OnLogicFrameCompleted(List<LogicEntity> logicEntities)
    {
        // 同步逻辑实体到表现实体：
        //   新实体 → 创建 GameObject
        //   已有实体 → 更新 targetPosition
        //   消失的实体 → 标记销毁

        HashSet<uint> activeIds = new HashSet<uint>();

        foreach (var logicEntity in logicEntities)
        {
            activeIds.Add(logicEntity.Id);

            if (_renderEntities.TryGetValue(logicEntity.Id, out RenderEntity renderEntity))
            {
                // 已有：更新目标位置
                renderEntity.PreviousPosition = renderEntity.TargetPosition;
                renderEntity.TargetPosition = LogicPosToWorldPos(logicEntity.Position);
                renderEntity.InterpTime = 0f; // 插值复位
            }
            else
            {
                // 新实体：创建
                CreateRenderEntity(logicEntity);
            }

            // 更新颜色（表现层字段）
            if (_renderEntities.TryGetValue(logicEntity.Id, out RenderEntity re))
            {
                if (re.Renderer != null)
                {
                    // 这里需要知道哪个是本地玩家——通过 LockstepManager 获取
                    // 简化处理：ID 小的用色1，ID 大的用色2
                    re.Renderer.color = (logicEntity.OwnerPlayerId == 0)
                        ? _localPlayerColor : _remotePlayerColor;
                }
            }
        }

        // 清理已消失的实体
        var toRemove = new List<uint>();
        foreach (var kv in _renderEntities)
        {
            if (!activeIds.Contains(kv.Key))
                toRemove.Add(kv.Key);
        }
        foreach (var id in toRemove)
        {
            if (_renderEntities[id].GameObject != null)
                Destroy(_renderEntities[id].GameObject);
            _renderEntities.Remove(id);
        }
    }

    /// <summary>每渲染帧执行：平滑插值所有实体位置</summary>
    void Update()
    {
        // 获取当前的逻辑帧间隔（用于插值时间基准）
        float interval = _lockstep != null ? _lockstep.LogicFrameInterval : 0.066f;

        foreach (var kv in _renderEntities)
        {
            RenderEntity re = kv.Value;
            if (re.GameObject == null) continue;

            // 插值推进
            re.InterpTime += Time.deltaTime / interval;
            if (re.InterpTime > 1f) re.InterpTime = 1f; // 钳制

            // 线性插值：prevPos → targetPos
            re.Transform.position = Vector3.Lerp(
                re.PreviousPosition, re.TargetPosition, re.InterpTime);
        }
    }

    /// <summary>创建表现实体</summary>
    private void CreateRenderEntity(LogicEntity logicEntity)
    {
        GameObject go;
        if (_playerPrefab != null)
            go = Instantiate(_playerPrefab);
        else
        {
            // 无预制体时创建一个简单的方形
            go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.transform.localScale = new Vector3(0.8f, 0.8f, 0.8f);
        }

        go.name = $"Player_{logicEntity.Id}";

        var renderEntity = new RenderEntity
        {
            LogicEntityId = logicEntity.Id,
            GameObject = go,
            Transform = go.transform,
            Renderer = go.GetComponent<SpriteRenderer>(),
            TargetPosition = LogicPosToWorldPos(logicEntity.Position),
            PreviousPosition = LogicPosToWorldPos(logicEntity.Position),
            InterpTime = 1f, // 初始化时直接到位，不平滑过渡
        };

        _renderEntities[logicEntity.Id] = renderEntity;
    }

    /// <summary>逻辑层 FP 坐标 → Unity 世界坐标</summary>
    private static Vector3 LogicPosToWorldPos(FPVector2 logicPos)
    {
        // 通常逻辑坐标是 Q16.16 格式的世界坐标，Unity 中直接使用浮点即可
        // 注意：Z 轴为 0（2D 游戏）
        return new Vector3(logicPos.X.ToFloat(), logicPos.Y.ToFloat(), 0f);
    }
}
```

**插值机制详解**：

```
逻辑帧 N (t=0)            逻辑帧 N+1 (t=66ms)
    │                           │
    │  PrevPos = Pn            │  TargetPos = Pn+1
    │                           │
    ├─── 渲染帧0 (t=0ms):   Lerp(0.00) → Pn      ──
    ├─── 渲染帧1 (t=16ms):  Lerp(0.24) → Pn+0.24Δ  │ 逐步靠近
    ├─── 渲染帧2 (t=33ms):  Lerp(0.50) → Pn+0.50Δ  │
    ├─── 渲染帧3 (t=50ms):  Lerp(0.76) → Pn+0.76Δ──
    │
    ▼ 逻辑帧 N+1 到达: 切换 PrevPos/TargetPos
```

表现层总是**滞后逻辑层一个逻辑帧**——这引入了最多 1 个逻辑帧（66ms）的额外延迟，但视觉效果从"瞬移"变为"平滑移动"。

---

### 2.8 DebugPanel.cs —— 调试面板

帧同步最怕的就是"不知道哪里不同步了"。调试面板提供运行时帧数据可视化。

```csharp
// DebugPanel.cs — 帧同步调试面板
// 运行时在屏幕左上角显示：帧号、缓冲帧数、状态、帧哈希等。

using System.Text;
using UnityEngine;

public class DebugPanel : MonoBehaviour
{
    private LockstepManager _lockstep;
    private FrameBuffer _frameBuffer;
    private NetworkClient _networkClient;

    // ── 帧哈希历史（用于跨客户端对比）─────────────────
    private readonly System.Collections.Generic.List<(uint frame, ulong hash)> _hashHistory
        = new System.Collections.Generic.List<(uint, ulong)>();

    void Start()
    {
        _lockstep = GetComponent<LockstepManager>();
        _frameBuffer = new FrameBuffer(); // 实际引用来自 LockstepManager
        _networkClient = GetComponent<NetworkClient>();

        // 订阅帧哈希事件
        if (_lockstep != null)
            _lockstep.OnFrameHashReady += OnFrameHashReady;
    }

    private void OnFrameHashReady(uint frame, ulong hash)
    {
        _hashHistory.Add((frame, hash));
        // 保留最近 100 条
        if (_hashHistory.Count > 100)
            _hashHistory.RemoveAt(0);
    }

    void OnGUI()
    {
        if (_lockstep == null) return;

        var sb = new StringBuilder();
        sb.AppendLine($"═══ Lockstep Debug ═══");
        sb.AppendLine($"状态:      {_lockstep.CurrentState}");
        sb.AppendLine($"逻辑帧:    {_lockstep.CurrentFrameNumber}");
        sb.AppendLine($"缓冲帧数:  {_lockstep.BufferedFrameCount}");
        sb.AppendLine($"帧间隔:    {_lockstep.LogicFrameInterval * 1000f:F1}ms");

        if (_networkClient != null)
        {
            sb.AppendLine($"已发送包:  {_networkClient.PacketsSent}");
            sb.AppendLine($"已接收包:  {_networkClient.PacketsReceived}");
        }

        sb.AppendLine();
        sb.AppendLine("── 最近哈希 ──");
        int start = System.Math.Max(0, _hashHistory.Count - 8);
        for (int i = start; i < _hashHistory.Count; i++)
        {
            var (frame, hash) = _hashHistory[i];
            sb.AppendLine($"  F#{frame}: {hash:X16}");
        }

        // ── 简易样式 ──────────────────────────────
        var style = new GUIStyle(GUI.skin.box)
        {
            fontSize = 14,
            alignment = TextAnchor.UpperLeft,
            normal = { textColor = Color.white }
        };

        GUI.Box(new Rect(10, 10, 350, 280), sb.ToString(), style);
    }
}
```

---

### 2.9 完整 Demo 运行指南

#### 场景搭建

1. **创建场景**：新建 Unity 场景 `LockstepDemo`

2. **创建空 GameObject**，命名为 `LockstepRoot`，挂载以下脚本：
   - `LockstepManager`
   - `NetworkClient`
   - `RenderProxy`
   - `DebugPanel`

3. **创建玩家预制体**：
   - `GameObject` → `2D Object` → `Sprites` → `Square`
   - 命名为 `PlayerPrefab`
   - 将预制体拖入 `RenderProxy` 的 `_playerPrefab` 字段

4. **设置 Config**：
   - `LockstepManager.Logic Frame Rate`: 15
   - `LockstepManager.Buffer Size`: 6
   - `LockstepManager.Catch Up Threshold`: 4
   - `NetworkClient.Server IP`: 127.0.0.1
   - `NetworkClient.Server Port`: 9999

5. **运行方式**：
   - 先启动服务器（参考 tutorial 11 的服务器实现）
   - 启动两个 Unity Editor 实例（或 Build 一个 standalone + Editor）
   - 两个客户端连接到同一服务器
   - 使用 `WASD` 移动，`J`/`Space` 攻击

#### 控制台验证确定性

在两个客户端同时运行，在控制台中观察帧哈希输出。如果每 100 帧的哈希值完全相同，说明没有 Desync：

```
[LockstepManager] F#100: A3B7C2D4E5F6091A
[LockstepManager] F#200: 1A2B3C4D5E6F7089
[LockstepManager] F#300: 9F8E7D6C5B4A3021
```

两台机器输出完全一致 → 帧同步正常工作。任何不一致 → Desync，需要排查。

---

## 3. 练习

### 练习 1: 基础——补全客户端（预计 30min）

上述代码中，`LockstepManager` 依赖 `NetworkClient.OnConnected` 回调来启动游戏。请完成以下任务：

1. 创建一个简单的**本地 Loopback 模拟服务器**（不需要真正的网络）：在 `LockstepManager` 中增加一个 `SimulateServer` 模式——每逻辑帧自动生成所有玩家的输入并用 `FrameBuffer.EnqueueFrame` 模拟服务器广播。
2. 实现"另一个玩家"的 AI 输入生成：AI 向本地玩家方向移动并每秒攻击一次。
3. 验证：在无网络的本地环境下，两个实体（本地玩家 + AI）可以正确移动和战斗。

**验收标准**：单客户端运行，能看到两个实体在场景中移动、攻击、扣血，且 `DebugPanel` 显示正常的帧推进。

### 练习 2: 进阶——帧偏移插值（预计 45min）

当前 `RenderProxy` 使用 1 帧插值（66ms 延迟）。请实现**可配置的多帧插值**：

1. 在 `RenderProxy` 中添加 `_interpDelayFrames` 参数（默认 1，可选 2 或 3）
2. 维护一个位置历史缓冲区（队列），记录最近 N 帧的逻辑位置
3. 渲染时使用"过去帧"之间的插值，而非"当前帧与上一帧"
4. 分析：帧偏移 2 帧（133ms）和 3 帧（200ms）分别带来什么样的延迟和流畅度？

**验收标准**：调整参数后，能看到插值延迟的变化。写一段注释分析帧偏移对体验的影响。

### 练习 3: 挑战——Desync 注入与检测（预计 60min）

构建一个 **Desync 故障模拟系统**：

1. 在 `GameLogic.ExecuteFrame()` 中添加一个 `_desyncInjectChance` 参数（0.0~1.0）
2. 当随机数命中时，故意将一个实体位置偏移 1 个定点单位（模拟计算误差）
3. 然后利用 `ComputeStateHash()` 检测：这个注入的误差是否在所有后续帧的哈希中被检测到？
4. 分析：为什么 1 个单位的定点误差最终可能导致"完全不同"的哈希值（蝴蝶效应）？
5. 扩展：如果 1000 帧前有一个位级的计算差异，哈希值会在多少帧内完全发散？

**验收标准**：能清晰地看到注入误差前后的哈希变化。在代码注释中解释蝴蝶效应的累积路径。

---

## 4. 扩展阅读

### 4.1 开源项目
- **[LockstepFramework (GitHub)](https://github.com/SnpM/LockstepFramework)**：一个完整的 Unity 帧同步框架，包含定点数、确定性物理、帧回放等。
- **[ET Framework (GitHub)](https://github.com/egametang/ET)**：国产开源游戏框架，帧同步部分的设计值得深入研究——特别是其 `Entity-Component` 架构在确定性场景下的应用。
- **[Dota2 网络模型 (Valve Developer Wiki)](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking)**：Dota 2 使用 Source 2 引擎的混合网络模型，结合了帧同步和状态同步。

### 4.2 推荐阅读
- **《网络游戏同步技术》(Game Networking) — Glenn Fiedler 系列文章**：业界标杆，第 1-4 篇详解帧同步的客户端实现。
- **《守望先锋》GDC 演讲 (2017)**："Gameplay Architecture and Netcode"——状态同步与帧同步混合架构的真实案例。
- **[1500 Archers on a 28.8: Network Programming in Age of Empires and Beyond](https://www.gamasutra.com/view/feature/131503/1500_archers_on_a_288_network_.php)**：帧同步的经典起源文献，Mark Terrano 讲述如何在拨号时代让 1500 个单位同步。

---

## 常见陷阱

### 陷阱 1: 逻辑帧中使用了 `Time.deltaTime`
```csharp
// ❌ 错误——逻辑帧不应该依赖渲染帧时间
void ExecuteFrame() {
    entity.Position += velocity * Time.deltaTime; // Time.deltaTime 是渲染帧的
}

// ✅ 正确——逻辑帧间隔是常量
void ExecuteFrame() {
    entity.Position += velocity * LOGIC_DT; // LOGIC_DT = 1/15 = 0.0667（定点数）
}
```
这可能是帧同步 bug 排名第一的根因。逻辑帧中的 `deltaTime` 必须是编译时常量（`FP.CreateFromFloat(0.0667f)`），不能来自 `Time` 类。

### 陷阱 2: 使用 `Dictionary` 遍历而不排序
```csharp
// ❌ 错误——遍历顺序不确定
Dictionary<uint, Entity> entities = ...;
foreach (var kv in entities) { kv.Value.Update(); }

// ✅ 正确——先收集 key、排序、再按顺序遍历
var keys = new List<uint>(entities.Keys);
keys.Sort();
foreach (var key in keys) { entities[key].Update(); }
```
`Dictionary` 的遍历顺序在不同 CLR 版本、不同平台、不同插入顺序下可能不同。帧同步中任何"遍历集合"的操作必须按确定顺序。

### 陷阱 3: 忘记清空"死亡实体"的引用
逻辑层标记实体死亡（`HP <= 0`）并移除后，表现层的 `GameObject` 也应该销毁。如果忘记清理，会产生悬空引用，表现层继续渲染一个不应该存在的实体，导致视觉不同步。

### 陷阱 4: 预缓冲过大或过小
- **过大**（如 20 帧 → 1.3 秒延迟）：操作延迟严重，玩家感觉"卡"
- **过小**（如 2 帧 → 133ms）：网络稍有抖动就会卡帧，频繁进入追赶模式
- **推荐值**：移动 MOBA 4-8 帧（266-533ms），RTS 2-4 帧（约 100-200ms）

### 陷阱 5: 追赶模式下不限制单帧推进上限
如果一次性追赶 100 帧，`ExecuteFrame()` 可能执行数百次碰撞检测导致帧耗时从 16ms 暴增到 500ms+，Unity 主线程卡死，玩家看到"假死"。**必须设置 `_maxCatchUpFramesPerUpdate`（典型值 3-5 帧）**。

### 陷阱 6: UDP 接收线程与 Unity API 混用
`UdpClient.Receive()` 在子线程中执行。如果直接在子线程中调用 `Debug.Log()` 以外的 Unity API（如 `Instantiate`、`Transform.position`），Unity 会抛出 "can only be called from the main thread" 异常。解决办法：接收线程只入队数据，主线程的 `UpdateReceive()` 做解包和后续处理。

### 陷阱 7: 定点数运算不检查溢出
```csharp
// Q16.16 乘法：(a * b) >> 16
// 如果 a.RawValue = 46340, b.RawValue = 46340（约 ±0.7 的范围）
// a * b = 2,147,395,600 → 超出 int.MaxValue → 溢出
// 必须使用 long 做中间乘法！
return new FP((int)(((long)a.RawValue * (long)b.RawValue) >> 16)); // ✅
```
所有定点数的乘法和除法中间结果必须用 64-bit（`long` / `ulong`）。32-bit 乘法在游戏逻辑中极易溢出（两个 2¹⁶ 级别值相乘即超 2³¹）。
