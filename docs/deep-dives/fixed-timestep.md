---
title: "固定时间步长 (Fixed Timestep) 深度剖析"
updated: 2026-06-05
---

# 固定时间步长 (Fixed Timestep) 深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 无
> 分析日期: 2026-06-01

---

## 第 1 层: 直觉理解

**一句话**: 固定时间步长是一种让游戏逻辑（尤其是物理模拟）以恒定频率更新，同时允许渲染帧率自由波动的技术。

**类比**: 想象一个工厂流水线。传送带（渲染）可以加速或减速，但每个工位上工人焊接零件的动作间隔（物理更新）始终保持固定的节奏——比如每 0.02 秒一次。传送带停了工人不会多做，传送带加速时工人也不会少做。两者各干各的，工人只关心自己焊了多少次，不关心传送带走了多远。

**核心矛盾**: 帧率不可控（VSYNC 开关、硬件差异、场景复杂度变化），但物理模拟必须是确定性的。同一个世界、同样的输入，刷 30fps 和 240fps 的机器上物体必须落在同一个坑里。

---

## 第 2 层: 使用场景

### 典型场景

| 场景 | 原因 |
|------|------|
| 物理模拟（刚体、碰撞检测） | 可变 dt 导致数值积分误差爆炸 |
| 确定性多人游戏（lockstep 网络） | 非确定 dt 在不同客户端产生不同结果 |
| 回放系统 | 回放帧需要与录制帧的状态一致 |
| 录像导出/离线渲染 | 输出帧与实时帧解耦 |

### 不适用场景

| 场景 | 原因 |
|------|------|
| 纯视觉效果（粒子特效） | dt 大小只影响观感，不影响正确性；可变 dt 更省资源 |
| UI 动画 | 与帧率绑定更流畅 |
| 非物理的手感逻辑（相机平滑、输入响应） | 放在 `Update` 中响应更快 |

### 决策流程

```
需要确定性 / 物理确定性？ ─── 是 ──→ 固定时间步长
    │
    否
    │
    ↓
对 dt 变化敏感的计算？ ────── 是 ──→ 固定时间步长（或 clamp dt 上限）
    │
    否
    │
    ↓
可以用可变 dt（Update / Tick）
```

---

## 第 3 层: API 层

### Unity (2022 LTS / 6.x)

#### 核心属性

| API | 类型 | 说明 |
|-----|------|------|
| `Time.fixedDeltaTime` | `float` (get/set) | 每次 FixedUpdate 之间的时间间隔，单位秒。默认 0.02（50Hz） |
| `Time.fixedTime` | `float` (readonly) | 从游戏开始累加的固定步长时间（`fixedDeltaTime` × 累计步数） |
| `Time.fixedUnscaledTime` | `float` (readonly) | 不受 `timeScale` 影响的 `fixedTime` |
| `Time.maximumDeltaTime` | `float` (get/set) | 单帧允许的最大 dt 上限，防止帧卡顿导致物理瞬移 |
| `Time.maximumParticleDeltaTime` | `float` (get/set) | 粒子系统单帧允许的最大 dt |

#### 回调方法

```csharp
// MonoBehaviour 生命周期中固定频率调用的入口
void FixedUpdate()
{
    // 每次调用 timeDelta = Time.fixedDeltaTime
    // 一个渲染帧内可能被调用 0 次、1 次或 N 次
}

// 内部物理步进完成后的回调（Unity 6+）
void OnTriggerStay(Collider other) { }  // 物理回调也在 fixed 阶段
```

#### 修改步长

```csharp
// 运行时修改
Time.fixedDeltaTime = 0.01f;  // 100 Hz

// 或在 Editor → Edit → Project Settings → Time → Fixed Timestep
```

#### PlayerLoop 中的位置

Unity 的 PlayerLoop 中物理阶段位于 `FixedUpdate` 和渲染之间：

```
Initialization → ... → FixedUpdate → [物理引擎步进] → Update → ... → Rendering
```

可通过 `PlayerLoop` API 自定义注入（Unity 2018.1+）。

---

### Unreal Engine (5.x)

#### 内置系统

UE 的默认 Tick 是可变时间步长（`DeltaSeconds` 随帧率变化）。固定时间步长通过 **CustomTimeStep** 体系实现。

#### 核心类

| 类 | 头文件 | 作用 |
|----|--------|------|
| `UEngineCustomTimeStep` | `Engine/EngineCustomTimeStep.h` | 抽象基类，控制引擎帧率和时间步长 |
| `UFixedFrameRateCustomTimeStep` | `TimeManagement/FixedFrameRateCustomTimeStep.h` | 抽象类，按固定帧率步进 |
| `UCatchupFixedRateCustomTimeStep` | （派生自上面） | **可变帧率渲染 + 固定步长逻辑**——类似 Unity 的 FixedUpdate |
| `UGenlockedCustomTimeStep` | （派生自上面） | 与外部时钟源（硬件 genlock）同步 |

#### 使用方式

```cpp
// 在 GameMode 或 Engine 初始化时设置 CustomTimeStep
if (GEngine)
{
    GEngine->CustomTimeStep = NewObject<UCatchupFixedRateCustomTimeStep>();
}
```

#### 物理子步

UE 支持物理子步（Physics Sub-stepping），在项目设置中启用：

- `Project Settings → Physics → Framerate → Max Physics Delta Time`：单次物理步进的最大 dt
- `bSubstepping`：启用后引擎会在一个 Tick 内多次步进物理

```cpp
// 物理 Tick 中
void UPhysicsMovementComponent::TickComponent(float DeltaTime, ...)
{
    // DeltaTime 是渲染帧的 dt
    // 如果启用子步，内部会按 MaxPhysicsDeltaTime 切分
    Super::TickComponent(DeltaTime, ...);
}
```

#### CustomTimeStep 回调

```cpp
virtual bool UpdateTimeStep(UEngine* InEngine);
// 返回 true 时引擎执行一个 tick
// 返回 false 时等待（用于固定帧率锁帧）
```

---

### C++ (独立实现)

#### 经典实现 (Glenn Fiedler, 2004)

```cpp
#include <chrono>

constexpr double FIXED_DT = 1.0 / 60.0;  // 60 Hz
constexpr double MAX_FRAME_TIME = 0.25;   // 防止螺旋死亡

double accumulator = 0.0;

// 插值用的双缓冲状态
State previous_state;
State current_state;

auto current_time = std::chrono::high_resolution_clock::now();

while (!quit)
{
    auto new_time = std::chrono::high_resolution_clock::now();
    double frame_time = std::chrono::duration<double>(new_time - current_time).count();
    current_time = new_time;

    // 防止螺旋死亡：单帧时间上限
    if (frame_time > MAX_FRAME_TIME)
        frame_time = MAX_FRAME_TIME;

    accumulator += frame_time;

    // 消耗累积时间
    while (accumulator >= FIXED_DT)
    {
        previous_state = current_state;
        integrate(current_state, FIXED_DT);
        accumulator -= FIXED_DT;
    }

    // 渲染插值状态以消除视觉抖动
    const double alpha = accumulator / FIXED_DT;
    State render_state = interpolate(previous_state, current_state, alpha);

    render(render_state);
}
```

#### C++17/20 现代化版本

```cpp
#include <chrono>
#include <thread>

using Clock = std::chrono::steady_clock;
using Duration = std::chrono::duration<double>;

class FixedTimestepLoop
{
public:
    using StepFn = std::function<void(double)>;
    using RenderFn = std::function<void(double)>;

    FixedTimestepLoop(double fixedDt, double maxFrameTime = 0.25)
        : m_fixedDt(fixedDt), m_maxFrameTime(maxFrameTime) {}

    void run(StepFn step, RenderFn render)
    {
        auto currentTime = Clock::now();
        double accumulator = 0.0;

        while (m_running)
        {
            auto newTime = Clock::now();
            double frameTime = Duration(newTime - currentTime).count();
            currentTime = newTime;

            if (frameTime > m_maxFrameTime)
                frameTime = m_maxFrameTime;

            accumulator += frameTime;

            while (accumulator >= m_fixedDt)
            {
                step(m_fixedDt);
                accumulator -= m_fixedDt;
            }

            double alpha = accumulator / m_fixedDt;
            render(alpha);
        }
    }

    void stop() { m_running = false; }

private:
    double m_fixedDt;
    double m_maxFrameTime;
    bool m_running = true;
};
```

---

## 第 4 层: 行为契约

### 前置条件

1. **`fixedDeltaTime` 不能为 0 或负数** —— 否则进入无限循环或除零
2. **引擎必须装配高精度计时器** —— Unity 用 `Time.realtimeSinceStartup`，UE 用 `FPlatformTime::Seconds()`，自实现用 `std::chrono::high_resolution_clock`
3. **物理/逻辑步进函数必须接受固定 dt 参数** —— 即 `step(dt)` 中的 `dt` 必须是常量

### 后置条件

1. **仿真时间步数固定** —— 同一时间段内，无论帧率高低，`FixedUpdate` / `step()` 调用次数一致
2. **累积器溢出有上界** —— `accumulator` 被 `maxFrameTime` 限制，不会无限膨胀
3. **插值 alpha ∈ [0, 1)** —— 渲染状态始终是最近两个物理状态的线性混合

### 不变量

| 不变量 | 说明 |
|--------|------|
| `accumulator < FIXED_DT` | 每次内循环后，累积器总是 < dt，剩余的挂到下一帧 |
| `step_call_count = floor(total_time / FIXED_DT)` | 步进总次数完全由真实时间决定 |
| `alpha == 0 → 帧刚好与物理步同步` | 无插值需求 |
| `alpha → 1 → 刚好多累积了一个 FIXED_DT（下一帧将触发一次 step）` | |

### 异常 / 边界情况

| 情况 | 行为 |
|------|------|
| `frameTime > maxFrameTime` | 截断为 `maxFrameTime`，仿真变慢但不崩溃（非"螺旋死亡"） |
| `frameTime ≈ 0`（极高帧率） | 正常，累积器无积累，不触发 step |
| 游戏暂停 (`timeScale = 0`) | Unity: `FixedUpdate` 停止调用；UE: `DeltaSeconds = 0` |
| 机器休眠恢复（dt 极大） | `maxFrameTime` 截断，防止物理瞬移；但仿真变慢仍不可避免 |

### 线程安全

- Unity: `FixedUpdate` 始终在主线程
- UE: Tick 在主线程，物理子步在主线程（Physics Thread 仅用于异步物理烘焙）
- C++ 自实现: 单步 + 渲染通常在同一线程；如需多线程，`step()` 和 `render()` 间需要双缓冲 + 原子交换

---

## 第 5 层: 实现原理

### 核心算法：累积器模式 (Accumulator Pattern)

核心思想：**渲染器产生时间，模拟器消耗时间**。

```
[高精度计时器] ──→ 帧时间 ──→ [累积器] ──→ 消耗 FIXED_DT 大小的块 ──→ integrate()
                                   │
                               剩余时间 ──→ 计算 alpha ──→ 插值 ──→ render()
```

### 伪代码

```
算法: 固定步长主循环

输入:
  FIXED_DT        ← 固定步长 (如 0.0167 秒, 60Hz)
  MAX_FRAME_TIME  ← 单帧最大耗时 (如 0.25 秒)
  integrate(state, dt)  ← 物理/逻辑步进函数
  render(state, alpha)  ← 渲染函数
  interpolate(a, b, t)  ← 插值函数

初始化:
  previous_state, current_state ← 初始状态
  accumulator ← 0.0
  current_time ← now()

循环:
  new_time ← now()
  frame_time ← new_time - current_time
  current_time ← new_time

  如果 frame_time > MAX_FRAME_TIME:
    frame_time ← MAX_FRAME_TIME     // 防止螺旋死亡

  accumulator ← accumulator + frame_time

  当 accumulator >= FIXED_DT:
    previous_state ← current_state
    integrate(current_state, FIXED_DT)
    accumulator ← accumulator - FIXED_DT

  alpha ← accumulator / FIXED_DT     // ∈ [0, 1)
  render_state ← interpolate(previous_state, current_state, alpha)
  render(render_state)
```

### 螺旋死亡 (Spiral of Death)

```
原因: simulate(X 秒) 耗时 > X 秒
      → 累积器膨胀 → 更多 simulate 调用 → 进一步膨胀 → ...
```

**解决方案**:
1. **上限截断** — 设置 `MAX_FRAME_TIME`，超出部分丢弃（宁愿仿真变慢，不崩溃）
2. **最大步数限制** — `while` 内循环限制最大迭代次数（如 Unity 内部有最大 `FixedUpdate` 调用上限）
3. **设计余量** — 确保 `simulate(FIXED_DT)` 耗时远小于 `FIXED_DT`

### Unity 内部实现（推断）

Unity 的 FixedUpdate 循环可近似为：

```
// C++ 伪代码（Unity 内部引擎层）
void PhysicsSimulate()
{
    float dt = fixedDeltaTime;
    float maxDt = maxAllowedTimestep;

    while (m_physicsAccumulator >= dt)
    {
        // 调用所有 MonoBehaviour.FixedUpdate()
        ExecuteFixedUpdates();

        // 执行物理引擎步进（PhysX 内部）
        PhysicsStep(dt);

        // 触发内部物理回调（OnTriggerStay, OnCollisionStay 等）
        PhysicsCallbacks();

        m_physicsAccumulator -= dt;
    }
}
```

关键区别：Unity 的 `Update`（每帧一次）在 `FixedUpdate` **之后**执行。一个低帧率帧中的调用顺序是：

```
FixedUpdate × 3  →  Update × 1  →  Rendering
```

### UE 内部实现（推断）

```cpp
// UE 物理子步引擎侧
void FPhysScene::Tick(float DeltaSeconds)
{
    if (bSubstepping)
    {
        float SubTime = 0.0f;
        while (SubTime < DeltaSeconds)
        {
            float SubDt = FMath::Min(MaxPhysicsDeltaTime, DeltaSeconds - SubTime);
            // 模拟一步
            Simulate(SubDt);
            SubTime += SubDt;
        }
    }
    else
    {
        Simulate(DeltaSeconds);
    }
}
```

---

## 第 6 层: 源码分析

### Unity TimeManager 相关引用

Unity C# 侧的 `Time` 类是 `UnityEngine` 原生代码的包装。关键内部实现细节：

`Time.fixedDeltaTime` 在 Unity Editor 中的默认值来自 `TimeManager` 资源：

```
ProjectSettings/TimeManager.asset 中的 Fixed Timestep 字段
默认值: 0.02 (50 Hz)
```

内部受 `Time.maximumDeltaTime` 约束，该值默认 0.333 秒（约 3fps）。当 dt 超过此值时，Unity 会截断，等同于上述算法的 `MAX_FRAME_TIME`。

> **来源**: Unity 6.0+ `TimeManager` Asset serialized properties. `UnityEngine.Time` 包装的 native 属性 `fixedDeltaTime` / `maximumDeltaTime`。

### UE `UCatchupFixedRateCustomTimeStep` 源码特征

根据 UE 5.x 文档：

```cpp
// 头文件: TimeManagement/Public/FixedFrameRateCustomTimeStep.h
// UCatchupFixedRateCustomTimeStep 派生于 UFixedFrameRateCustomTimeStep

UCLASS()
class UCatchupFixedRateCustomTimeStep : public UFixedFrameRateCustomTimeStep
{
    GENERATED_BODY()

    // 重写 UpdateTimeStep —— 决定何时 Tick
    // 返回 true → Tick; false → 等待/跳过
    virtual bool UpdateTimeStep(UEngine* InEngine) override;
};
```

`UpdateTimeStep` 的典型行为：
- 检查上次 Tick 以来的真实时间
- 如果累积时间 ≥ 1 / FixedFrameRate：返回 `true`，允许 Tick
- 否则返回 `false` 或等待（`FPlatformProcess::Sleep`）

> **来源**: Epic Games, Unreal Engine 5.7 API Reference — `UCatchupFixedRateCustomTimeStep`. (https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/TimeManagement/UCatchupFixedRateCustomTimeStep)

### Glenn Fiedler 原作 (Gaffer On Games)

以上第 5 层的伪代码直接来源于 Glenn Fiedler 2004 年的文章 *Fix Your Timestep!* (https://gafferongames.com/post/fix_your_timestep/)。该文章是整个游戏行业固定步长实现的**事实标准参考**。

关键设计决策（截至 2004 年原文）：
- **累积器 + 固定消耗**: 帧剩余时间不丢弃，滚入下一帧
- **插值渲染**: alpha 混合前后两个物理状态，消除视觉抖动
- **maxFrameTime 截断**: 0.25 秒上限，防止螺旋死亡

### Box2D 固定步长

Box2D 推荐的固定步长模式（Erin Catto）：

```cpp
// Box2D manual 建议
const float32 timeStep = 1.0f / 60.0f;
const int32 velocityIterations = 6;
const int32 positionIterations = 2;

float32 accumulator = 0.0f;

while (accumulator >= timeStep)
{
    world->Step(timeStep, velocityIterations, positionIterations);
    accumulator -= timeStep;
}
```

> **来源**: Box2D 2.4.1 手册, "Hello World" 示例章节. (https://box2d.org/documentation/)

---

## 第 7 层: 对比与边界

### 三种引擎对比

| 维度 | Unity | Unreal Engine | 纯 C++ |
|------|-------|---------------|--------|
| **固定步长名称** | FixedUpdate | CustomTimeStep / Sub-stepping | 自实现（accumulator pattern） |
| **默认频率** | 50 Hz (0.02s) | 无默认（默认可变 dt） | 自定 |
| **API 复杂度** | 低（`FixedUpdate` 直接写） | 中（需继承 `UEngineCustomTimeStep`） | 高（完全手写） |
| **插值渲染** | Unity 自动处理（Rigidbody 插值） | 需手写或依赖引擎内部 | 需手写 |
| **螺旋死亡防护** | `Time.maximumDeltaTime` | `MaxPhysicsDeltaTime` | 需手写 `MAX_FRAME_TIME` |
| **修改频率** | `Time.fixedDeltaTime` | 设置 `FixedFrameRate` | 改常量 |
| **物理引擎解耦** | 深度绑定 PhysX | 可切换 PhysX/Chaos | 完全自控 |
| **网络确定性** | 不保证（浮点精度跨平台） | 不保证 | 取决于实现 |
| **适用场景** | 中小型项目、快速开发 | AAA、影视级 | 引擎开发、嵌入式 |

### 设计取舍

| 方案 | 优点 | 缺点 |
|------|------|------|
| **完全固定 dt**（渲染也锁帧） | 最简单，100% 确定性 | 低帧率机器全部变慢 |
| **可变 dt**（dt 传 delta） | 帧率自由 | 物理非确定、边缘情况爆炸 |
| **半固定 dt**（clamp + 可变） | 比完全可变稳定 | 仍有精度漂移 |
| **累积器 + 固定 dt**（本文主题） | 帧率自由 + 物理确定 | 实现复杂，需插值消除视觉抖动 |
| **累积器 + 固定 dt + 插值** | 最优视觉 + 物理确定性 | 最高复杂度，额外内存（双缓冲状态） |

### 性能数据

以 60Hz 为目标固定步长：

| 场景 | 物理步进调用次数/秒 | 渲染帧数/秒 | CPU 开销 |
|------|---------------------|-------------|---------|
| 稳定 60fps 渲染 | 60 | 60 | 基准 |
| 慢机 30fps | 60（每帧 2 步） | 30 | 略高（插值计算） |
| 快机 240fps | 60（每 4 帧 1 步） | 240 | 更低（跳帧） |
| 卡顿 2fps (0.5s 帧) | 被截断到 0.25s | 2 | 仿真变慢 |

`maxFrameTime` 为 0.25 秒时，最坏情况下每帧最多执行 `0.25 / 0.0167 ≈ 15` 次物理步进。

### 常见陷阱

1. **`FixedUpdate` 中读 `Input`**: `Input.GetKeyDown` 等瞬时事件可能在多次 FixedUpdate 间丢失 —— 应在 `Update` 捕获，缓存到变量中供 `FixedUpdate` 使用
2. **在 `FixedUpdate` 中做可变的 `for` 循环**: 如果循环依赖动态数据（如实体列表长度），每步执行结果不同导致确定性破灭
3. **忘记 `rigidbody.interpolation`**: Unity 中如果不开启 Rigidbody 插值，在帧率高于物理频率时物体会抖动
4. **插值只适用于上一帧已知状态**: 如果物体刚出生，没有 `previous_state`，直接使用 `current_state`
5. **累积器用 `float` 精度不足**: 长时间运行后 `accumulator` 精度丢失，优选 `double`

---

## 常见面试题

**Q1: Unity 中 FixedUpdate 和 Update 的调用频率有什么不同？为什么物理要放在 FixedUpdate？**

Update 每渲染帧调用一次（频率可变）；FixedUpdate 按固定间隔调用（默认 0.02s/50Hz），一帧可能被调用 0~N 次。物理模拟需要固定 dt 以保证数值积分的稳定性和确定性。

**Q2: 什么是"螺旋死亡" (Spiral of Death)？如何防止？**

物理步进耗时超过步长导致累积器不断膨胀的恶性循环。防止方法：① 设置 `maxFrameTime` 上限截断；② 限制内循环最大迭代次数；③ 确保模拟耗时远小于步长（设计余量）。

**Q3: 固定步长下为什么还需要插值渲染？**

累积器通常有剩余时间（< dt），渲染和物理之间存在时差，直接用最新物理状态会导致视觉抖动。用 `alpha = accumulator / dt` 在前后两帧物理状态间插值可消除此抖动。

**Q4: UE 如何实现类似 Unity FixedUpdate 的效果？**

方案一：启用 Physics Sub-stepping（`bSubstepping` + `MaxPhysicsDeltaTime`）。方案二：使用 `UCatchupFixedRateCustomTimeStep` 设置固定帧率。方案三：自行在 Tick 中实现累积器模式。

**Q5: 固定步长对网络游戏有什么影响？**

确定性的固定步长是 lockstep 网络模型的基础——所有客户端用相同 dt、相同输入序列推导出相同状态。但浮点精度在不同平台/编译器下可能不一致，通常需要定点数或软浮点库辅助。

---

## 延伸主题

- **数值积分方法**: Euler / Verlet / RK4 —— 固定 dt 下不同积分器的精度与稳定性
- **确定性浮点**: 跨平台确定性的实现（定点数、`ffast-math` 关闭、IEEE 754 严格模式）
- **网络同步模型**: Lockstep vs. State Sync vs. Snapshot Interpolation
- **Unity DOTS/ECS**: `SystemBase` 中如何在不同 `SystemGroup` 中控制更新频率
- **Box2D / PhysX / Chaos 内部步进**: 物理引擎内部的子步、CCD 和时间管理
- **时间缩放 (Time Scale)**: `Time.timeScale` 对 fixed 和 variable update 的不同影响
