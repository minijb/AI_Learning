---
title: "确定性游戏逻辑：定点数与跨平台一致性"
updated: 2026-06-05
---

# 确定性游戏逻辑：定点数与跨平台一致性

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [[05-lockstep-core-principles|05-帧同步核心原理：Lockstep 模型]]

---

## 1. 概念讲解

### 为什么需要确定性？

回忆帧同步的核心约定：**所有客户端执行完全相同的逻辑，只同步输入指令**。这意味着——给定完全相同的输入序列和完全相同的初始状态，每台机器上的第 N 帧的游戏状态必须逐位一致。差一个 bit 都不行。

现实给了我们一记闷棍：**同样的 C++ 代码，在 Windows/x86-64 和 Android/ARM64 上编译运行，浮点计算结果可能不同。** 这不是 bug，这是 CPU 厂商为了性能主动选择的行为差异。

在帧同步中，"基本一致"就是不一致。1e-7 的误差经过 36000 帧（10 分钟 @ 60fps）的累积放大，足以让单位位置偏差几个格子，从而导致玩家 A 看到自己击杀了敌人，而玩家 B 看到敌人还活着——这就是 **desync（不同步）**。

本教程将系统性地讲解如何让游戏逻辑在跨平台、跨编译器、跨 CPU 架构的环境中实现**逐位确定性（bitwise determinism）**。

### 核心思想

确定性游戏逻辑建立在以下五根支柱上：

```
┌───────────────────────────────────────────────────────────────┐
│                     确定性游戏逻辑                              │
├─────────────┬──────────────┬──────────────┬───────────────────┤
│  定点数学    │ 确定性容器    │ 确定性随机数   │ 确定性物理/碰撞    │
│  (Fixed-Point│ (Deterministic│ (Deterministic│ (Deterministic    │
│   Math)      │  Containers)  │  PRNG)        │  Physics)         │
├─────────────┴──────────────┴──────────────┴───────────────────┤
│                    跨平台确定性验证                             │
│              (Desync Detection & Replay Debugging)              │
└───────────────────────────────────────────────────────────────┘
```

任何一根支柱的倒塌都会导致整个体系的崩溃。下面我们逐一深挖。

---

### 1.1 浮点数的非确定性陷阱

#### 陷阱一：x87 vs SSE 指令集差异

x86 平台有两套浮点指令集。老旧的 **x87** 使用 80 位扩展精度内部寄存器，而 **SSE2+** 使用 64 位寄存器。同一个 `double` 运算可能使用不同的指令路径：

```cpp
double a = 0.1;
double b = 0.2;
double c = a + b;
// x87:   内部以 80-bit 计算，结果存回 64-bit 时"舍入"
// SSE2:  全程 64-bit 计算
// 两次舍入 vs 一次舍入 → 最终值可能相差 1 ULP
```

这个问题在 GCC 中尤其明显。32 位模式下 GCC 默认使用 x87，64 位模式默认使用 SSE2。即使代码完全相同，编译产物也会产生不同的浮点结果。

**为什么 `-ffloat-store` 和 `/fp:strict` 不能完全解决？** 因为截断到内存是真正的性能杀手，而且无法处理寄存器溢出、CSE（公共子表达式消除）、内联展开中的所有中间精度差异。

#### 陷阱二：编译器优化级别差异

```cpp
double compute(double a, double b, double c) {
    return (a + b) + c;  // 你写的
}
```

编译器在 `-O2` 下可能将表达式重排为 `a + (b + c)`（利用结合律减少寄存器压力）。对实数加法这是合法的数学变换，但对浮点数——`(a + b) + c != a + (b + c)` 因为每次加法都会舍入。

```cpp
// 实际案例：0.1 + (0.2 + 1e16)  vs  (0.1 + 0.2) + 1e16
// 前者：0.2 + 1e16 = 1e16（0.2 被舍入吞掉），+0.1 = 1e16
// 后者：0.1 + 0.2 = 0.3，+ 1e16 = 1e16（0.3 被吞掉）
// 结果相同，但中间路径不同——某些情况下结果真的会不同
```

#### 陷阱三：超越函数的精度差异

`sin()`, `cos()`, `sqrt()`, `pow()` 等数学库函数在不同平台上实现不同：

| 平台/库 | `sin()` 实现 | 精度特征 |
|---------|-------------|----------|
| Windows/MSVC | 基于 Intel SVML 或直接调用 x87 fsin | 扩展精度中间值 |
| Linux/glibc | IBM 的精确表驱动算法 | 正确舍入（correctly rounded） |
| Android/Bionic | 简化的多项式近似 | 稍低精度但更快 |
| iOS/macOS | Apple 优化的向量数学库 | 不一定与 glibc 逐位一致 |

即使同一平台，`-ffast-math` 会激进替换 `sin()` 为 SIMD 实现，精度大幅下降。

#### 陷阱四：FMA（Fused Multiply-Add）

FMA 指令在一条指令中完成 `a * b + c`，**只做一次舍入**（而不是乘法一次、加法一次）。这对精度是好事，但对确定性是噩梦：

```cpp
double r = a * b + c;
// 无 FMA:  (a * b) [舍入1] + c [舍入2]
// 有 FMA:  fma(a, b, c) [舍入1]
// 结果：差 0.5 ULP —— 但足够让碰撞检测判定不同
```

ARM64 有原生 FMA 指令。x86-64 的 Haswell+ 有 FMA3/FMA4。即使同一份代码，运行的 CPU 不同，编译器可能生成不同指令。

---

### 1.2 IEEE 754 深入：规范与实现的差距

IEEE 754 定义了一套严格的浮点运算标准，但它并不意味着跨平台一致性：

1. **IEEE 754 规定的是"结果应该是什么"，不是"结果必须是什么序列"。** 它允许在不同精度下做中间运算（x87 80-bit 扩展），只要求最终存储值时舍入到位宽。
2. **NaN 的传递有歧义。** `NaN` 有多种 bit 表示（signaling vs quiet），不同平台产生的 `NaN` bit 模式可能不同。`0.0/0.0` 在 x86 上是 `0xFFF8000000000000`，在 ARM 上可能是 `0x7FF8000000000000`。
3. **舍入模式默认都是 round-to-nearest-even，但 80-bit → 64-bit 时的"二次舍入"不受规范约束。**
4. **非规格化数（subnormal）的处理。** x86 有 DAZ/FTZ 标志位（flush-to-zero），ARM 有 FZ 模式。非规格化数被刷新为零→结果彻底不同。

**所谓"严格模式"（`/fp:strict` MSVC, `-ffloat-store` GCC）只是减少了问题，没有消除它。** 真正的答案是：**禁用硬件浮点用于游戏逻辑。**

---

### 1.3 定点数（Fixed-Point Math）

#### Q 格式

定点数的核心思想：**用整数模拟小数，小数点位置固定（故称"定点"）。**

```
Qm.n 格式：m 位整数部分，n 位小数部分，共 m+n 位（通常 32 或 64）
                    ┌──── m 位 ────┬──── n 位 ────┐
Q16.16 (32-bit):    │ 整数部分 16bit │ 小数部分 16bit │
                    值 = raw / 2^16 = raw / 65536

Q24.8  (32-bit):    │ 整数 24bit │ 小数 8bit │
                    值 = raw / 256

Q32.32 (64-bit):    │   整数部分 32bit   │   小数部分 32bit   │
                    值 = raw / 2^32
```

关键转换公式：

```
浮点数 → 定点数:  fixed = (int)(float_val * SCALE)
定点数 → 浮点数:  float_val = fixed / (double)SCALE
```

其中 `SCALE = 2^n = 1 << n`（n = 小数位数）。

#### 基本运算

```cpp
// 设 SCALE = 65536 (Q16.16)
// a, b 都是 Q16.16 格式的原始整数值

// 加法/减法：直接运算（scale 相同）
fixed_t add(fixed_t a, fixed_t b)    { return a + b; }
fixed_t sub(fixed_t a, fixed_t b)    { return a - b; }

// 乘法：(a * b) / SCALE
// 关键：中间结果需要 64-bit 才能容纳 32-bit × 32-bit = 64-bit
fixed_t mul(fixed_t a, fixed_t b) {
    return (fixed_t)(((int64_t)a * (int64_t)b) >> 16);
}

// 除法：(a * SCALE) / b
// 先乘 SCALE 保证精度，再除以 b
fixed_t div(fixed_t a, fixed_t b) {
    return (fixed_t)(((int64_t)a << 16) / (int64_t)b);
}
```

#### 溢出处理

定点数乘法容易溢出。Q16.16 的两个正值相乘，如果结果 ≥ 65536（约 32768² > 2³¹），就会溢出 32-bit。实战中的策略：

1. **Q32.32 (64-bit)**：直接用 64-bit 定点数，几乎不会溢出——两个 32 位有符号整数相乘，中间结果用 128-bit，最终裁切到 64-bit。代价是 2× 内存。
2. **饱和运算**：超过范围就钳制到 `INT32_MAX` / `INT32_MIN`，防止静默回绕。
3. **范围检查 + 降精度**：对已知范围的值使用更小的 Q 格式（如坐标用 Q24.8 而非 Q16.16）。

**帧同步项目的常规选择**：
- 位置/速度：Q24.8 或 Q16.16（32-bit），范围够用且 64-bit 中间计算安全
- 累计值（时间、分数）：Q32.32（64-bit），永不溢出
- 三角函数/角度：不需要 Q 格式——用查表法，0~2π 映射到整数范围

#### 三角函数查表法

浮点 `sin()`/`cos()` 是非确定性的根源之一。标准替代方案：

**方案一：LUT (Lookup Table)**

```cpp
// 将 0 ~ 2π 离散化为 TABLE_SIZE 个条目，预计算 sin 值
static const int TABLE_SIZE = 4096;
static fixed_t sin_table[TABLE_SIZE];

void init_sin_table() {
    for (int i = 0; i < TABLE_SIZE; ++i) {
        double angle = (double)i / TABLE_SIZE * 2.0 * M_PI;
        sin_table[i] = double_to_fixed(sin(angle));
    }
}

// 查表：将定点角度映射到表索引
fixed_t fixed_sin(fixed_t angle_rad) {
    // 归一化角度到 [0, 2π)
    // 映射到表索引
    int idx = (int)(angle_rad * TABLE_SIZE / (2 * FIXED_PI));
    idx = idx & (TABLE_SIZE - 1); // 模运算（TABLE_SIZE 是 2 的幂）
    return sin_table[idx];
}
```

**方案二：CORDIC 算法**

CORDIC（COordinate Rotation DIgital Computer）通过一系列固定的微旋转迭代逼近 sin/cos。它只使用移位和加减——天然适合定点数，且完全确定。

```cpp
// CORDIC 预计算的 atan(2^-i) 值表
// 迭代 16 次即可获得 ~4 位小数精度，32 次 ~9 位
static const fixed_t cordic_table[32] = { /* atan(2^0), atan(2^-1), ... */ };

void cordic_sincos(fixed_t theta, fixed_t* sin_out, fixed_t* cos_out) {
    fixed_t x = CORDIC_GAIN; // K = ∏ 1/sqrt(1+2^(-2i)) ≈ 0.607253
    fixed_t y = 0;
    fixed_t z = theta;
    
    for (int i = 0; i < 32; ++i) {
        fixed_t x_shift = x >> i;
        fixed_t y_shift = y >> i;
        if (z >= 0) {
            x -= y_shift;
            y += x_shift;
            z -= cordic_table[i];
        } else {
            x += y_shift;
            y -= x_shift;
            z += cordic_table[i];
        }
    }
    *cos_out = x;
    *sin_out = y;
}
```

#### 平方根：牛顿迭代法

```cpp
fixed_t fixed_sqrt(fixed_t a) {
    if (a <= 0) return 0;
    
    // 初始猜测：利用整数 sqrt 近似
    fixed_t x = (fixed_t)(int_sqrt64((int64_t)a << 16));
    
    // 牛顿迭代：x_{n+1} = (x_n + a / x_n) / 2
    // 通常 4-6 次迭代足够 Q16.16 收敛
    for (int i = 0; i < 6; ++i) {
        if (x == 0) break;
        x = (x + fixed_div(a, x)) >> 1;
    }
    return x;
}
```

#### 定点数与浮点数的精度对比

| 格式 | 有效位数 | 最小分辨率 | 整数范围 | 非确定性风险 |
|------|---------|-----------|---------|-------------|
| `float` (32-bit) | ~7 位十进制 | 约 1.2e-38 | ±3.4e38 | **高**（指令集、编译器） |
| `double` (64-bit) | ~16 位十-进制 | 约 2.2e-308 | ±1.8e308 | **中**（超越函数） |
| Q16.16 (32-bit) | ~5 位十进制 | 1/65536 (~1.5e-5) | ±32767 | **无**（纯整数运算） |
| Q24.8 (32-bit) | ~7 位十进制 | 1/256 (~3.9e-3) | ±8388607 | **无** |
| Q32.32 (64-bit) | ~10 位十-进制 | 1/2³² (~2.3e-10) | ±21 亿 | **无** |

---

### 1.4 确定性容器

浮点数的确定性解决了，但还有另一个隐蔽的陷阱：**容器的遍历顺序**。

```cpp
// 非确定性代码！
std::unordered_map<int, Enemy*> enemies;
for (auto& pair : enemies) {
    pair.second->Update(dt);  // 遍历顺序取决于 hash 桶布局
}
// 不同平台/不同运行时：hash 表增长策略不同 → 遍历顺序不同
// → 更新顺序不同 → 浮点累积误差或逻辑分支不同 → desync
```

**确定性容器的要求**：

1. **遍历顺序必须稳定**。`std::unordered_map` 和 `std::unordered_set` 的遍历顺序与插入历史、hash 策略、负载因子有关，不是跨平台一致的。替代：在遍历前将 key 收集到 `std::vector` 中排序，然后按排序后的 key 访问。
2. **增量更新要小心**。如果在遍历过程中增删元素，容器的内部状态变化可能影响后续帧。
3. **自定义 hash 函数必须跨平台一致**。`std::hash<std::string>` 的实现在不同标准库中不同。

**实战模式**：

```cpp
// 帧同步中的安全遍历模式
std::vector<EntityId> sorted_ids;
for (auto& [id, entity] : entities) {
    sorted_ids.push_back(id);
}
std::sort(sorted_ids.begin(), sorted_ids.end());  // 确定的排序

for (EntityId id : sorted_ids) {
    entities[id]->Update(dt);  // 每次遍历顺序相同
}
```

**排序稳定性**：`std::sort` 本身不是稳定排序（相等元素的相对顺序不保证），但对于唯一 ID 这不是问题。如果排序键可能重复（如按 Z-order 排序），使用 `std::stable_sort` 或加第二排序键（如 ID）。

---

### 1.5 确定性随机数

游戏中大量使用随机数：暴击判定、伤害浮动、掉落表、AI 行为变化。在帧同步中，所有客户端必须产生**相同的随机数序列**。

#### 伪随机数生成器（PRNG）的选择

| 算法 | 周期 | 状态大小 | 速度 | 推荐场景 |
|------|------|---------|------|---------|
| LCG (Linear Congruential Generator) | 2³¹ | 32/64 bit | 最快 | 简单随机（非核心） |
| MT19937 (Mersenne Twister) | 2^19937-1 | 2.5 KB | 中 | 高质量随机需求 |
| Xorshift128+ | 2^128-1 | 128 bit | 快 | 现代推荐 |
| PCG Family | 2^64 或更大 | 128 bit | 快 | 统计质量最好 |

**确定性保证关键**：
- **所有 PRNG 操作必须是纯整数运算**（无浮点）
- **相同种子 → 相同序列**（这是 PRNG 的基本性质）
- **种子必须作为初始状态的一部分同步**

#### 多人共享种子

```
游戏开始前：
  服务端生成随机种子 seed（或由第一个玩家提供）
  → 将 seed 随游戏开始帧广播给所有客户端
  → 所有客户端用 seed 初始化各自的 PRNG
  → 每帧消耗的随机数顺序完全一致

运行时：
  每帧开始时，记录当前 PRNG 状态（用于后续 desync 诊断）
  每帧结束时，校验 PRNG 消耗的随机数数量是否与预期一致
```

**注意**：不能在游戏逻辑中调用系统 `rand()`！它的实现完全不可移植。必须用自带的确定性 PRNG。

#### 实现示例

```cpp
// 确定性 PRNG：Xorshift128+（纯整数，完全可移植）
class DeterministicRandom {
    uint64_t s[2];
public:
    DeterministicRandom(uint64_t seed) {
        // 用 splitmix64 从单一 seed 生成两个状态
        s[0] = splitmix64(seed);
        s[1] = splitmix64(s[0]);
    }
    
    uint64_t next() {
        uint64_t s1 = s[0];
        uint64_t s0 = s[1];
        s[0] = s0;
        s1 ^= s1 << 23;
        s1 ^= s1 >> 17;
        s1 ^= s0;
        s1 ^= s0 >> 26;
        s[1] = s1;
        return s0 + s1;
    }
    
    // 生成 [0, max) 的随机整数
    uint64_t range(uint64_t max) {
        // 拒绝采样避免取模偏置
        uint64_t mask = max - 1;
        if ((max & mask) == 0) {  // max 是 2 的幂
            return next() & mask;
        }
        uint64_t r;
        do { r = next(); } while (r < (UINT64_MAX / max) * max);
        return r % max;
    }
    
    // 生成 [0, 1) 的定点数（Q32.32）
    int64_t fixed_01() {
        return (int64_t)(next() >> 32);  // 取高 32 位作为 0~2^32-1
    }
};
```

---

### 1.6 确定性物理

如果项目使用了物理引擎（如 Box2D、Bullet），需要做定点数移植：

#### Box2D 定点数移植要点

1. **替换 `float` → 定点数类型**。Box2D 的 `b2Vec2` 的 `x`, `y` 成员从 `float` 变为 `fixed_t`。
2. **碰撞检测中的迭代求解器**。Box2D 使用 Sequential Impulse 算法迭代约束求解。在浮点版本中，收敛取决于浮点运算的精度；在定点版本中，必须固定迭代次数（不能用"直到收敛"的条件）。
3. **位置修正（Baumgarte stabilization）**。穿透修正的系数必须用定点数表示，且修正量需要量化。
4. **AABB 树更新**。浮点中惰性更新边界依赖浮点运算，定点版需要确定性的边界扩张策略。

```cpp
// 定点 Box2D 向量类的核心片段
struct FixedVec2 {
    fixed_t x, y;
    
    FixedVec2() : x(0), y(0) {}
    FixedVec2(fixed_t _x, fixed_t _y) : x(_x), y(_y) {}
    
    fixed_t length() const {
        return fixed_sqrt(fixed_mul(x, x) + fixed_mul(y, y));
    }
    
    FixedVec2 normalize() const {
        fixed_t len = length();
        if (len == 0) return *this;
        return FixedVec2(fixed_div(x, len), fixed_div(y, len));
    }
    
    fixed_t dot(const FixedVec2& other) const {
        return fixed_mul(x, other.x) + fixed_mul(y, other.y);
    }
};
```

**里程碑案例**：《王者荣耀》使用自研定点数物理引擎（基于 Box2D 思想），《合金弹头觉醒》同样采用定点数物理方案。

---

### 1.7 跨平台确定性验证

#### Desync 检测

帧同步中 desync 是常驻威胁。需要在开发期和线上持续检测：

**方案一：帧哈希校验**

```cpp
// 每 N 帧，所有客户端计算当前帧状态的哈希值
// 发送给服务端比对
uint32_t compute_state_hash() {
    uint32_t hash = 0x811c9dc5;  // FNV-1a 初始值
    for (auto& [id, entity] : entities) {
        hash = fnv1a_hash(hash, entity->x);
        hash = fnv1a_hash(hash, entity->y);
        hash = fnv1a_hash(hash, entity->hp);
        // ... 所有游戏状态字段
    }
    return hash;
}
```

**方案二：全量快照校验**

每 300-600 帧（5-10 秒），服务端下发一次"所有人对 XXX 帧做完整快照校验"。每台客户端将该帧的完整状态序列化并计算 hash，发送给服务端比对。不一致的客户端被标记为 desync。

#### 回放调试

Desync 发生后，最有效的手段是**确定性的战斗回放**：

1. 记录从头到尾的完整指令序列（包括每帧所有玩家的输入）
2. 在开发机上**单步回放**：从第一帧开始执行，每帧记录状态 hash
3. 对比"正确"客户端和 desync 客户端的 hash 曲线，找到**第一帧 hash 不同的位置**
4. 在该帧打断点，对比两个客户端的状态差异，定位具体不一致的字段
5. 追溯该字段的赋值逻辑，分析不同机器上产生不同值的原因

这就是为什么帧同步的调试能力极强——**一切都可以重现**。

```cpp
// 回放系统核心循环
void replay_from(uint32_t start_frame) {
    // 恢复初始状态
    restore_checkpoint(start_frame);
    
    // 逐帧执行指令
    for (uint32_t frame = start_frame; frame < total_frames; ++frame) {
        execute_frame_commands(frame);
        uint32_t hash = compute_state_hash();
        
        if (hash != expected_hashes[frame]) {
            printf("DESYNC at frame %u: expected 0x%08X, got 0x%08X\n",
                   frame, expected_hashes[frame], hash);
            break;  // 在此帧打断点进行详细分析
        }
    }
}
```

---

## 2. 代码示例

### 2.1 C#: Q32.32 定点数完整实现

适用于 Unity 项目的帧同步逻辑层。`long` (Int64) 作为底层存储，32 位整数位 + 32 位小数位。

```csharp
// ============================================================
// FixedPoint64.cs — Q32.32 定点数 (C#)
// 
// 使用 long (Int64) 作为底层存储。
// 范围: 大约 ±21 亿，精度: 1/2^32 ≈ 2.3e-10
//
// 在 Unity 中的使用方式:
//   - 不要直接在 MonoBehaviour 或 Transform 中使用此类型
//   - 创建一个独立的"逻辑层"，内部所有数值用 FP64
//   - Transform.position 仅用于渲染，逻辑层从 FP64 计算完再同步过去
// ============================================================

using System;
using System.Runtime.CompilerServices;

/// <summary>
/// Q32.32 定点数结构。不可变值类型。
/// </summary>
[Serializable]
public struct FP64 : IEquatable<FP64>, IComparable<FP64>
{
    // ──── 常量 ────
    /// <summary>小数部分的位数</summary>
    public const int FRAC_BITS = 32;

    /// <summary>缩放因子 = 2^32</summary>
    public const long SCALE = 1L << FRAC_BITS; // 4294967296

    /// <summary>乘法右移位数（用于中间 128-bit 结果截断）</summary>
    private const int MUL_SHIFT = FRAC_BITS;

    // 常用常量
    public static readonly FP64 Zero = new FP64(0);
    public static readonly FP64 One = new FP64(SCALE);
    public static readonly FP64 Half = new FP64(SCALE / 2);
    public static readonly FP64 NegOne = new FP64(-SCALE);
    public static readonly FP64 Pi = FromRaw(13493037704L);   // π * 2^32
    public static readonly FP64 TwoPi = FromRaw(26986075409L);
    public static readonly FP64 PiOver2 = FromRaw(6746518852L);
    public static readonly FP64 Epsilon = new FP64(1);         // 最小精度
    public static readonly FP64 MaxValue = new FP64(long.MaxValue);
    public static readonly FP64 MinValue = new FP64(long.MinValue);

    // ──── 存储 ────
    /// <summary>原始定点数值（Q32.32 格式）</summary>
    public readonly long RawValue;

    // ──── 构造函数 ────

    /// <summary>从原始 Q32.32 值构造（内部使用）</summary>
    private FP64(long raw)
    {
        RawValue = raw;
    }

    /// <summary>从原始值构造（显式命名，避免歧义）</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP64 FromRaw(long raw) => new FP64(raw);

    /// <summary>从整数构造</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP64 FromInt(int value) => new FP64((long)value << FRAC_BITS);

    /// <summary>从 float 构造（仅在编辑器/加载阶段使用！游戏逻辑中禁止）</summary>
    public static FP64 FromFloat(float value)
    {
        return new FP64((long)(value * SCALE));
    }

    /// <summary>从 double 构造（仅在编辑器/加载阶段使用！游戏逻辑中禁止）</summary>
    public static FP64 FromDouble(double value)
    {
        return new FP64((long)(value * SCALE));
    }

    // ──── 转换 ────

    /// <summary>转为整数（截断小数）</summary>
    public int ToInt() => (int)(RawValue >> FRAC_BITS);

    /// <summary>转为 float（仅用于渲染/调试输出）</summary>
    public float ToFloat() => (float)RawValue / SCALE;

    /// <summary>转为 double（仅用于调试输出）</summary>
    public double ToDouble() => (double)RawValue / SCALE;

    // ──── 基本运算 ────

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP64 operator +(FP64 a, FP64 b) => new FP64(a.RawValue + b.RawValue);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP64 operator -(FP64 a, FP64 b) => new FP64(a.RawValue - b.RawValue);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static FP64 operator -(FP64 a) => new FP64(-a.RawValue);

    /// <summary>
    /// 乘法: (a.RawValue * b.RawValue) >> FRAC_BITS
    /// 中间使用 128-bit 防止溢出（C# 没有原生 128-bit 整数类型，手动拆分模拟）
    /// </summary>
    public static FP64 operator *(FP64 a, FP64 b)
    {
        // 使用 Math.BigMul 获取 128-bit 乘积
        long hi = Math.BigMul(a.RawValue, b.RawValue, out long lo);

        // 将 128-bit 结果右移 FRAC_BITS 得到 64-bit 定点值
        // hi:lo >> 32 = (hi << 32) | (lo >> 32)
        long result = (hi << (64 - MUL_SHIFT)) | (long)((ulong)lo >> MUL_SHIFT);

        // 舍入：检查被截断的最高位
        // 如果 lo 的第 31 位（0-indexed）为 1，向上舍入
        if ((lo & (1L << (MUL_SHIFT - 1))) != 0)
            result += 1;

        return new FP64(result);
    }

    /// <summary>
    /// 除法: (a.RawValue << FRAC_BITS) / b.RawValue
    /// </summary>
    public static FP64 operator /(FP64 a, FP64 b)
    {
        if (b.RawValue == 0)
            throw new DivideByZeroException("FP64 division by zero");

        // 先将被除数左移获取足够精度
        // 同样使用 128-bit 中间计算
        long hi = Math.BigMul(a.RawValue, SCALE, out long lo);

        // 128-bit 除以 64-bit
        // 简化实现：使用 double 作为中间桥梁来除（生产代码应用完整的长除法）
        // 或者：
        // 对于被除数绝对值不太大的情况，可以直接用 64-bit
        if (a.RawValue <= long.MaxValue / SCALE && a.RawValue >= long.MinValue / SCALE)
        {
            return new FP64((a.RawValue << FRAC_BITS) / b.RawValue);
        }

        // 128-bit 长除法（简化版本）
        long result = Divide128By64(hi, lo, b.RawValue);
        return new FP64(result);
    }

    /// <summary>128-bit (hi:lo) / divisor → 64-bit quotient</summary>
    private static long Divide128By64(long hi, long lo, long divisor)
    {
        // 简化实现：将 hi:lo 转换为 double 近似后做除法
        // 生产环境应实现完整的 Knuth Algorithm D
        // 对于游戏场景，我们保证 hi 不会太大
        if (hi == 0)
            return lo / divisor;

        // 使用逼近法
        long result = 0;
        // 处理高位
        if (hi >= divisor)
            throw new OverflowException("FP64 division overflow");

        // 转换 128-bit 为两个 64-bit 的值，分别除
        // hi 中蕴含 2^64 的权重
        // result ≈ (hi * 2^64 + lo) / divisor
        // 首先用 hi 和 divisor 的高位部分逼近
        long hiDiv = hi / divisor;
        long hiRem = hi % divisor;

        // 将余量扩展并与 lo 的高位组合
        // 这个简化版本假设商不会溢出 64-bit
        result = hiDiv << 32; // 近似的高位贡献
        long combined = (hiRem << 32) | (long)((ulong)lo >> 32);
        result += combined / divisor;

        return result;
    }

    // ──── 取模运算 ────
    public static FP64 operator %(FP64 a, FP64 b)
    {
        return new FP64(a.RawValue % b.RawValue);
    }

    // ──── 比较运算 ────

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator ==(FP64 a, FP64 b) => a.RawValue == b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator !=(FP64 a, FP64 b) => a.RawValue != b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator >(FP64 a, FP64 b) => a.RawValue > b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator <(FP64 a, FP64 b) => a.RawValue < b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator >=(FP64 a, FP64 b) => a.RawValue >= b.RawValue;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static bool operator <=(FP64 a, FP64 b) => a.RawValue <= b.RawValue;

    // ──── 高级数学函数 ────

    /// <summary>绝对值</summary>
    public static FP64 Abs(FP64 value)
    {
        if (value.RawValue == long.MinValue)
            return MaxValue; // 防止溢出
        return new FP64(value.RawValue >= 0 ? value.RawValue : -value.RawValue);
    }

    /// <summary>取最小值</summary>
    public static FP64 Min(FP64 a, FP64 b) => a.RawValue < b.RawValue ? a : b;

    /// <summary>取最大值</summary>
    public static FP64 Max(FP64 a, FP64 b) => a.RawValue > b.RawValue ? a : b;

    /// <summary>钳制到 [min, max] 范围</summary>
    public static FP64 Clamp(FP64 value, FP64 min, FP64 max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }

    /// <summary>
    /// 平方根：牛顿迭代法
    /// 初始值猜选用 Bit 级别的近似，6 次迭代收敛到 1 ULP 以内
    /// </summary>
    public static FP64 Sqrt(FP64 value)
    {
        if (value.RawValue <= 0)
            return Zero;

        // 初始猜测：用 double 近似（仅用于提供初始值，不影响最终精度）
        long guess = (long)(Math.Sqrt((double)value.RawValue / SCALE) * SCALE);
        if (guess < 1) guess = 1;

        FP64 x = FromRaw(guess);
        FP64 half = Half;

        // 牛顿迭代：x_{n+1} = (x_n + value / x_n) / 2
        for (int i = 0; i < 10; i++)
        {
            FP64 next = (x + value / x) * half;
            if (Abs(next - x) < Epsilon)
                break;
            x = next;
        }
        return x;
    }

    /// <summary>
    /// 平方根：纯定点数牛顿迭代（完全不依赖浮点初始值）
    /// 生产环境推荐使用此版本
    /// </summary>
    public static FP64 SqrtPure(FP64 value)
    {
        if (value.RawValue <= 0) return Zero;

        // 通过找到最高位来估算初始值
        // sqrt(x) ≈ 2^(floor(log2(x)/2))
        long raw = value.RawValue;
        long guess = 1L << ((63 - LeadingZeroCount((ulong)raw)) / 2 + 16);
        if (guess < 1) guess = 1;

        FP64 x = FromRaw(guess);
        FP64 half = Half;

        for (int i = 0; i < 8; i++)
        {
            FP64 next = (x + value / x) * half;
            if (Abs(next - x).RawValue <= 1) // 1 ULP 以内
                break;
            x = next;
        }
        return x;
    }

    /// <summary>计算 64-bit 前导零</summary>
    private static int LeadingZeroCount(ulong x)
    {
        // 使用 .NET 的 BitOperations.LeadingZeroCount
        // 这里提供手动版本以保证可移植性
        int count = 0;
        if ((x & 0xFFFFFFFF00000000UL) == 0) { count += 32; x <<= 32; }
        if ((x & 0xFFFF000000000000UL) == 0) { count += 16; x <<= 16; }
        if ((x & 0xFF00000000000000UL) == 0) { count += 8;  x <<= 8;  }
        if ((x & 0xF000000000000000UL) == 0) { count += 4;  x <<= 4;  }
        if ((x & 0xC000000000000000UL) == 0) { count += 2;  x <<= 2;  }
        if ((x & 0x8000000000000000UL) == 0) { count += 1;  }
        return count;
    }

    // ──── IEquatable, IComparable ────

    public bool Equals(FP64 other) => RawValue == other.RawValue;
    public override bool Equals(object obj) => obj is FP64 other && Equals(other);
    public override int GetHashCode() => RawValue.GetHashCode();
    public int CompareTo(FP64 other) => RawValue.CompareTo(other.RawValue);
    public override string ToString() => ToDouble().ToString("F6");
}

// ============================================================
// FP64Vector2.cs — 定点数二维向量 (C#)
// ============================================================

public struct FPVector2 : IEquatable<FPVector2>
{
    public FP64 x;
    public FP64 y;

    public static readonly FPVector2 Zero = new FPVector2(FP64.Zero, FP64.Zero);
    public static readonly FPVector2 One = new FPVector2(FP64.One, FP64.One);
    public static readonly FPVector2 Up = new FPVector2(FP64.Zero, FP64.One);
    public static readonly FPVector2 Right = new FPVector2(FP64.One, FP64.Zero);

    public FPVector2(FP64 x, FP64 y) { this.x = x; this.y = y; }

    public static FPVector2 operator +(FPVector2 a, FPVector2 b) =>
        new FPVector2(a.x + b.x, a.y + b.y);

    public static FPVector2 operator -(FPVector2 a, FPVector2 b) =>
        new FPVector2(a.x - b.x, a.y - b.y);

    public static FPVector2 operator *(FPVector2 v, FP64 s) =>
        new FPVector2(v.x * s, v.y * s);

    public static FPVector2 operator /(FPVector2 v, FP64 s) =>
        new FPVector2(v.x / s, v.y / s);

    public FP64 magnitudeSqr => x * x + y * y;
    public FP64 magnitude => FP64.Sqrt(magnitudeSqr);

    public FPVector2 normalized
    {
        get
        {
            FP64 mag = magnitude;
            if (mag == FP64.Zero) return Zero;
            return this / mag;
        }
    }

    /// <summary>点积</summary>
    public static FP64 Dot(FPVector2 a, FPVector2 b) =>
        a.x * b.x + a.y * b.y;

    /// <summary>2D 叉积（标量）</summary>
    public static FP64 Cross(FPVector2 a, FPVector2 b) =>
        a.x * b.y - a.y * b.x;

    /// <summary>线性插值</summary>
    public static FPVector2 Lerp(FPVector2 a, FPVector2 b, FP64 t) =>
        a + (b - a) * t;

    public bool Equals(FPVector2 other) => x == other.x && y == other.y;
    public override string ToString() => $"({x.ToDouble():F3}, {y.ToDouble():F3})";
}

// ============================================================
// FPMath.cs — 定点三角函数（查表法） (C#)
// ============================================================

public static class FPMath
{
    private const int TRIG_TABLE_SIZE = 4096;
    private const int TRIG_TABLE_MASK = TRIG_TABLE_SIZE - 1;
    private static readonly FP64[] sinTable = new FP64[TRIG_TABLE_SIZE];
    private static readonly FP64[] cosTable = new FP64[TRIG_TABLE_SIZE];
    private static bool tablesInitialized = false;

    /// <summary>初始化三角函数表（游戏启动时调用一次）</summary>
    public static void InitTrigTables()
    {
        if (tablesInitialized) return;
        tablesInitialized = true;

        for (int i = 0; i < TRIG_TABLE_SIZE; i++)
        {
            double angle = (double)i / TRIG_TABLE_SIZE * 2.0 * Math.PI;
            sinTable[i] = FP64.FromDouble(Math.Sin(angle));
            cosTable[i] = FP64.FromDouble(Math.Cos(angle));
        }
    }

    /// <summary>将定点角度映射到查表索引</summary>
    private static int AngleToIndex(FP64 angleRad)
    {
        // 将角度归一化到 [0, 2π) 再映射
        // 表索引: 0 ~ TRIG_TABLE_SIZE-1 对应 0 ~ 2π
        long normalized = angleRad.RawValue % FP64.TwoPi.RawValue;
        if (normalized < 0) normalized += FP64.TwoPi.RawValue;

        // 映射: index = normalized * TRIG_TABLE_SIZE / TwoPi
        return (int)((normalized * TRIG_TABLE_SIZE) >> 32);
    }

    public static FP64 Sin(FP64 angleRad) => sinTable[AngleToIndex(angleRad) & TRIG_TABLE_MASK];
    public static FP64 Cos(FP64 angleRad) => cosTable[AngleToIndex(angleRad) & TRIG_TABLE_MASK];

    /// <summary>反正切（使用简单多项式近似或查表）</summary>
    public static FP64 Atan2(FP64 y, FP64 x)
    {
        // 简化实现：使用 8 阶多项式近似
        // atan(z) ≈ z * (0.999866 + z^2 * (-0.3302995 + z^2 * (0.180141 + ...)))
        // 完整实现见下一节的 C++ 代码
        if (x == FP64.Zero && y == FP64.Zero) return FP64.Zero;

        FP64 z = FP64.Abs(y) / FP64.Abs(x);
        FP64 z2 = z * z;

        // atan(z) 多项式近似（8 阶，最大误差 < 0.001 弧度）
        FP64 atan_z = z * (
            FP64.FromRaw(4294914641L) + z2 * (  // 0.999866 * 2^32
            FP64.FromRaw(-1418755820L) + z2 * ( // -0.3302995 * 2^32
            FP64.FromRaw( 773498176L)            //  0.180141 * 2^32
        )));

        // 根据象限调整
        if (x < FP64.Zero)
            atan_z = (y >= FP64.Zero ? FP64.Pi : -FP64.Pi) - atan_z;
        else if (y < FP64.Zero)
            atan_z = -atan_z;

        return atan_z;
    }
}
```

---

### 2.2 C++: 定点数模板类 + 三角函数查表

```cpp
// ============================================================
// fixed_point.hpp — 定点数模板类 + 数学库 (C++17)
//
// 特性:
//   - 模板化定点格式：Fixed<TotalBits, FracBits>
//   - 编译期确定缩放因子，零运行时开销
//   - 完整的算术运算：+, -, *, /, %, sqrt
//   - 三角函数查表 + 线性插值
//   - 饱和运算保护
//   - CORDIC sin/cos 纯整数实现
//
// 用法:
//   using fp16 = Fixed<32, 16>;  // Q16.16
//   using fp24 = Fixed<32, 8>;   // Q24.8
//   using fp64 = Fixed<64, 32>;  // Q32.32
// ============================================================

#pragma once
#include <cstdint>
#include <type_traits>
#include <limits>
#include <cassert>

// ──── 编译期工具 ────

template<size_t Bits>
struct IntTypeFor {
    using type = void;
};

template<> struct IntTypeFor<32> { using type = int32_t; };
template<> struct IntTypeFor<64> { using type = int64_t; };

template<size_t Bits>
struct UIntTypeFor {
    using type = void;
};
template<> struct UIntTypeFor<32> { using type = uint32_t; };
template<> struct UIntTypeFor<64> { using type = uint64_t; };

// 两倍宽度的类型（用于乘法中间结果）
template<size_t Bits>
struct DoubleIntTypeFor {
    using type = void;
};
template<> struct DoubleIntTypeFor<32> { using type = int64_t; };
// 对于 64 位，我们需要 __int128（编译器扩展）
#if defined(__SIZEOF_INT128__) || defined(__GNUC__)
template<> struct DoubleIntTypeFor<64> { using type = __int128; };
#endif

// ──── 定点数模板 ────

template<size_t TotalBits = 32, size_t FracBits = 16>
class Fixed {
    static_assert(TotalBits == 32 || TotalBits == 64, "Only 32 or 64-bit fixed supported");
    static_assert(FracBits > 0 && FracBits < TotalBits, "Invalid FracBits");
    static_assert(TotalBits == 64 || FracBits <= 30, "Q32: FracBits too large for safe mul");

public:
    using RawType = typename IntTypeFor<TotalBits>::type;
    using DoubleType = typename DoubleIntTypeFor<TotalBits>::type;
    using UnsignedType = typename UIntTypeFor<TotalBits>::type;

    static constexpr size_t kFracBits = FracBits;
    static constexpr RawType kScale = RawType(1) << FracBits;
    static constexpr RawType kHalfScale = kScale / 2;

    // ──── 构造 ────

    constexpr Fixed() : raw_(0) {}
    constexpr Fixed(RawType raw, bool /*tagged*/) : raw_(raw) {} // 原始值构造（内部使用）

    // 从整数构造
    constexpr Fixed(int v) : raw_(RawType(v) << FracBits) {}
    constexpr Fixed(long v) : raw_(RawType(v) << FracBits) {}

    // 从浮点构造（仅在初始化/配置阶段使用，游戏逻辑中禁止）
    explicit constexpr Fixed(float v)
        : raw_(static_cast<RawType>(v * kScale + (v >= 0 ? 0.5f : -0.5f))) {}
    explicit constexpr Fixed(double v)
        : raw_(static_cast<RawType>(v * kScale + (v >= 0 ? 0.5 : -0.5))) {}

    // 工厂：从原始内部值创建
    static constexpr Fixed FromRaw(RawType raw) { return Fixed(raw, true); }

    // 工厂：从整数创建
    static constexpr Fixed FromInt(int v) { return Fixed(v); }

    // ──── 访问器 ────

    constexpr RawType raw() const { return raw_; }
    constexpr int to_int() const { return static_cast<int>(raw_ >> FracBits); }
    constexpr float to_float() const { return static_cast<float>(raw_) / kScale; }
    constexpr double to_double() const { return static_cast<double>(raw_) / kScale; }

    // ──── 算术运算 ────

    friend constexpr Fixed operator+(Fixed a, Fixed b) {
        return FromRaw(a.raw_ + b.raw_);
    }
    friend constexpr Fixed operator-(Fixed a, Fixed b) {
        return FromRaw(a.raw_ - b.raw_);
    }
    friend constexpr Fixed operator-(Fixed a) {
        return FromRaw(-a.raw_);
    }

    /// 乘法：(a.raw_ * b.raw_) / kScale（舍入到最近偶数）
    friend constexpr Fixed operator*(Fixed a, Fixed b) {
        DoubleType product = DoubleType(a.raw_) * DoubleType(b.raw_);
        // 加半比例因子做舍入
        return FromRaw(RawType((product + kHalfScale) >> FracBits));
    }

    /// 除法：(a.raw_ * kScale) / b.raw_（舍入到最近偶数）
    friend constexpr Fixed operator/(Fixed a, Fixed b) {
        assert(b.raw_ != 0 && "Division by zero");
        DoubleType num = DoubleType(a.raw_) << FracBits;
        // 加半除数做舍入
        return FromRaw(RawType((num + DoubleType(b.raw_) / 2) / b.raw_));
    }

    friend constexpr Fixed operator%(Fixed a, Fixed b) {
        return FromRaw(a.raw_ % b.raw_);
    }

    Fixed& operator+=(Fixed o) { raw_ += o.raw_; return *this; }
    Fixed& operator-=(Fixed o) { raw_ -= o.raw_; return *this; }
    Fixed& operator*=(Fixed o) { *this = *this * o; return *this; }
    Fixed& operator/=(Fixed o) { *this = *this / o; return *this; }

    // ──── 比较 ────

    friend constexpr bool operator==(Fixed a, Fixed b) { return a.raw_ == b.raw_; }
    friend constexpr bool operator!=(Fixed a, Fixed b) { return a.raw_ != b.raw_; }
    friend constexpr bool operator<(Fixed a, Fixed b)  { return a.raw_ < b.raw_; }
    friend constexpr bool operator>(Fixed a, Fixed b)  { return a.raw_ > b.raw_; }
    friend constexpr bool operator<=(Fixed a, Fixed b) { return a.raw_ <= b.raw_; }
    friend constexpr bool operator>=(Fixed a, Fixed b) { return a.raw_ >= b.raw_; }

    // ──── 基本数学函数 ────

    friend constexpr Fixed abs(Fixed v) {
        return v.raw_ >= 0 ? v : -v;
    }

    friend constexpr Fixed min(Fixed a, Fixed b) { return a < b ? a : b; }
    friend constexpr Fixed max(Fixed a, Fixed b) { return a > b ? a : b; }

    friend constexpr Fixed clamp(Fixed v, Fixed lo, Fixed hi) {
        return v < lo ? lo : (v > hi ? hi : v);
    }

    /// 平方根（牛顿迭代法）
    friend Fixed sqrt(Fixed value) {
        if (value.raw_ <= 0) return FromRaw(0);

        // 初始猜测：利用位运算快速近似
        // sqrt(x) ≈ 2^(floor(log2(x)/2))
        UnsignedType abs_raw = value.raw_ > 0
            ? UnsignedType(value.raw_)
            : UnsignedType(-value.raw_);

        // 计算最高有效位
        int msb = 0;
        UnsignedType tmp = abs_raw;
        while (tmp >>= 1) ++msb;

        RawType guess = RawType(1) << ((msb + FracBits) / 2);
        Fixed x = FromRaw(guess);
        Fixed half = Fixed(0.5);

        for (int i = 0; i < 10; ++i) {
            Fixed next = (x + value / x) * half;
            if (abs(next - x).raw_ <= 1) // 1 ULP 内收敛
                break;
            x = next;
        }
        return x;
    }

private:
    RawType raw_;
};

// 常用别名
using FP16 = Fixed<32, 16>;  // Q16.16, ±32767, 精度 1/65536
using FP24 = Fixed<32, 8>;   // Q24.8,  ±8M, 精度 1/256
using FP64 = Fixed<64, 32>;  // Q32.32, ±2G, 精度 1/2^32

// ============================================================
// fp_vec2.hpp — 定点二维向量 (C++)
// ============================================================

template<typename F>
struct FpVec2 {
    F x, y;

    constexpr FpVec2() : x(0), y(0) {}
    constexpr FpVec2(F x, F y) : x(x), y(y) {}

    friend constexpr FpVec2 operator+(FpVec2 a, FpVec2 b) { return {a.x + b.x, a.y + b.y}; }
    friend constexpr FpVec2 operator-(FpVec2 a, FpVec2 b) { return {a.x - b.x, a.y - b.y}; }
    friend constexpr FpVec2 operator*(FpVec2 v, F s) { return {v.x * s, v.y * s}; }
    friend constexpr FpVec2 operator/(FpVec2 v, F s) { return {v.x / s, v.y / s}; }

    constexpr F mag_sqr() const { return x * x + y * y; }
    F mag() const { return sqrt(mag_sqr()); }

    FpVec2 normalized() const {
        F m = mag();
        return m == F(0) ? FpVec2() : *this / m;
    }

    friend constexpr F dot(FpVec2 a, FpVec2 b) { return a.x * b.x + a.y * b.y; }
    friend constexpr F cross(FpVec2 a, FpVec2 b) { return a.x * b.y - a.y * b.x; }

    friend FpVec2 lerp(FpVec2 a, FpVec2 b, F t) { return a + (b - a) * t; }
};

using Vec2FP16 = FpVec2<FP16>;
using Vec2FP64 = FpVec2<FP64>;

// ============================================================
// fp_trig.hpp — 定点三角函数（LUT + CORDIC 两种实现）(C++)
// ============================================================

#include <array>
#include <cmath>

template<typename F>
class FixedTrig {
    static constexpr size_t TABLE_BITS = 12;  // 4096 条目
    static constexpr size_t TABLE_SIZE = 1 << TABLE_BITS;
    static constexpr size_t TABLE_MASK = TABLE_SIZE - 1;

    // 将 [0, 2π) 映射到 [0, TABLE_SIZE)
    static inline size_t angle_to_idx(typename F::RawType angle_raw) {
        // 归一化
        using Raw = typename F::RawType;
        constexpr Raw kPi = Raw(3.141592653589793 * F::kScale);
        constexpr Raw k2Pi = Raw(2.0 * 3.141592653589793 * F::kScale);

        Raw norm = angle_raw % k2Pi;
        if (norm < 0) norm += k2Pi;

        return size_t((norm * TABLE_SIZE) >> F::kFracBits);
    }

    static std::array<F, TABLE_SIZE>& sin_table() {
        static std::array<F, TABLE_SIZE> table = []() {
            std::array<F, TABLE_SIZE> t;
            for (size_t i = 0; i < TABLE_SIZE; ++i) {
                double angle = double(i) / TABLE_SIZE * 2.0 * M_PI;
                t[i] = F(std::sin(angle));
            }
            return t;
        }();
        return table;
    }

    static std::array<F, TABLE_SIZE>& cos_table() {
        static std::array<F, TABLE_SIZE> table = []() {
            std::array<F, TABLE_SIZE> t;
            for (size_t i = 0; i < TABLE_SIZE; ++i) {
                double angle = double(i) / TABLE_SIZE * 2.0 * M_PI;
                t[i] = F(std::cos(angle));
            }
            return t;
        }();
        return table;
    }

public:
    /// 查表正弦
    static F sin(F angle) {
        size_t idx = angle_to_idx(angle.raw()) & TABLE_MASK;
        return sin_table()[idx];
    }

    /// 查表余弦
    static F cos(F angle) {
        size_t idx = angle_to_idx(angle.raw()) & TABLE_MASK;
        return cos_table()[idx];
    }

    /// CORDIC 算法计算 sin/cos（纯定点，无浮点依赖）
    /// @param theta 角度（弧度，定点格式）
    /// @return {sin, cos}
    static std::pair<F, F> cordic_sincos(F theta) {
        // CORDIC 增益 K ≈ 0.607252935
        // 16 次迭代 → 精度约 4 位十进制
        // 32 次迭代 → 精度约 9 位十进制

        // 预计算的 atan(2^-i) 查找表，定点格式
        static const typename F::RawType atan_table[32] = {
            // atan(2^0), atan(2^-1), ..., atan(2^-31)
            // 对应 45°, 26.565°, 14.036°, ...
            // 以下是以 Q16.16 格式存储的近似值
            // 注：生产代码应使用精确计算值
            2949120,    // atan(1)     = 0.785398 * 2^16
            1740967,    // atan(0.5)   = 0.463648 * 2^16
            919789,     // atan(0.25)  = 0.244979 * 2^16
            466945,     // atan(0.125) = 0.124355 * 2^16
            234280,     // ...
            117257,
            58644,
            29323,
            14662,
            7331,
            3665,
            1833,
            916,
            458,
            229,
            115,
            57,
            29,
            14,
            7,
            4,
            2,
            1,
            0, 0, 0, 0, 0, 0, 0, 0
        };

        // 初始化
        F x = F::FromRaw(typename F::RawType(0.6072529350088814 * F::kScale));
        F y = F::FromRaw(0);
        F z = theta;

        constexpr size_t ITERATIONS = 16;

        for (size_t i = 0; i < ITERATIONS; ++i) {
            F x_shift = F::FromRaw(x.raw() >> i);
            F y_shift = F::FromRaw(y.raw() >> i);
            F atan_val = F::FromRaw(atan_table[i]);

            if (z.raw() >= 0) {
                x = x - y_shift;
                y = y + x_shift;
                z = z - atan_val;
            } else {
                x = x + y_shift;
                y = y - x_shift;
                z = z + atan_val;
            }
        }
        return {y, x};  // CORDIC 输出: {sin, cos}
    }
};

// 显式实例化常用类型
template class FixedTrig<FP16>;
template class FixedTrig<FP64>;
```

---

### 2.3 Lua: 32 位整数模拟定点数

Lua 5.3+ 原生支持 64-bit 整数（`math.type(1) == "integer"`），这使得定点数实现变得简洁高效。以下是一个完整的 Lua 定点数库，适用于游戏逻辑层（如基于 Lua 的帧同步战斗服务器）。

```lua
-- ============================================================
-- fixed_point.lua — 定点数数学库 (Lua 5.3+)
--
-- 利用 Lua 5.3+ 的 64-bit integer 作为底层存储。
-- 格式: Q16.16（32位数据存储在 Lua integer 中）
-- Lua integer 是 64-bit，Q16.16 只需要 32-bit，所以安全。
--
-- 为什么用 Q16.16 而不是 Q32.32？
--   - Lua integer 是 64-bit signed，Q32.32 乘法需要 128-bit 中间值
--   - Lua 不支持 128-bit 运算，需要手动拆分，性能较差
--   - Q16.16 的范围 (±32767) 对大多数 2D 游戏足够
--   - 需要更大范围时使用 Q8.24 或分区域坐标
--
-- 用法:
--   local fp = require("fixed_point")
--   local a = fp.from_float(3.5)
--   local b = fp.from_int(2)
--   local c = fp.mul(a, b)      -- 7.0
--   local dist = fp.sqrt(c)     -- ~2.6457
-- ============================================================

local fp = {}

-- ---- 常量 ----
local SCALE      = 65536          -- 2^16
local SCALE_F    = 65536.0        -- 浮点版本
local FRAC_BITS  = 16
local HALF_SCALE = SCALE // 2     -- 舍入用

-- 常用定点数值（内部原始值）
fp.ZERO  = 0
fp.ONE   = SCALE
fp.HALF  = SCALE // 2
fp.TWO   = SCALE * 2
fp.PI    = 205887     -- π * 65536
fp.TWO_PI = 411775    -- 2π * 65536
fp.PI_OVER_2 = 102944 -- π/2 * 65536
fp.EPSILON = 1        -- 最小精度单位

-- ---- 构造与转换 ----

--- 从浮点数构造定点数（仅初始化/加载阶段使用）
function fp.from_float(f)
    return math.floor(f * SCALE_F + 0.5)
end

--- 从整数构造定点数
function fp.from_int(i)
    return i << FRAC_BITS
end

--- 定点数 → 浮点数（仅渲染/调试使用）
function fp.to_float(v)
    return v / SCALE_F
end

--- 定点数 → 整数（截断）
function fp.to_int(v)
    return v >> FRAC_BITS
end

--- 定点数 → 整数（四舍五入）
function fp.round_to_int(v)
    return (v + HALF_SCALE) >> FRAC_BITS
end

-- ---- 基本运算 ----

--- 加法
function fp.add(a, b)
    return a + b
end

--- 减法
function fp.sub(a, b)
    return a - b
end

--- 乘法: (a * b) / SCALE
--  使用 Lua 的 64-bit 整数自动处理中间结果
--  注意：a * b 不能超过 2^63 - 1 否则溢出
--  对于 Q16.16：两个最大正值相乘 = 2^31 * 2^31 = 2^62 < 2^63 ✓
function fp.mul(a, b)
    -- Lua 5.3+ 的整数乘法自动使用 64-bit
    -- 除以 SCALE 并舍入
    local product = a * b
    if product >= 0 then
        return (product + HALF_SCALE) >> FRAC_BITS
    else
        return (product - HALF_SCALE) >> FRAC_BITS
    end
end

--- 除法: (a * SCALE) / b
--  b 不能为 0
function fp.div(a, b)
    assert(b ~= 0, "Division by zero in fixed_point.div")
    -- 先乘 SCALE，再做除法（带舍入）
    local num = a << FRAC_BITS
    if num >= 0 then
        return (num + (b >> 1)) // b
    else
        return (num - (b >> 1)) // b
    end
end

--- 取模
function fp.mod(a, b)
    return a % b
end

--- 取反
function fp.neg(a)
    return -a
end

--- 绝对值
function fp.abs(a)
    return a >= 0 and a or -a
end

-- ---- 比较 ----

function fp.eq(a, b)  return a == b end
function fp.ne(a, b)  return a ~= b end
function fp.lt(a, b)  return a < b  end
function fp.le(a, b)  return a <= b end
function fp.gt(a, b)  return a > b  end
function fp.ge(a, b)  return a >= b end

--- 钳制
function fp.clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

--- 取 min/max
function fp.min(a, b) return a < b and a or b end
function fp.max(a, b) return a > b and a or b end

-- ---- 高级数学 ----

--- 平方根（牛顿迭代法）
--  @param v 定点数（必须 ≥ 0）
--  @return sqrt(v) 定点数
function fp.sqrt(v)
    if v <= 0 then return 0 end

    -- 初始猜测：用浮点 sqrt 提供（非确定性但仅用于初始值不碍事）
    -- 生产环境可用位操作近似
    local guess = math.floor(math.sqrt(fp.to_float(v)) * SCALE_F)
    if guess < 1 then guess = 1 end

    -- 牛顿迭代
    local x = guess
    local half = HALF_SCALE -- Q16.16 的 0.5
    for _ = 1, 10 do
        local next_x
        if x == 0 then break end

        -- next = (x + v / x) / 2
        local div_term = fp.div(v, x)
        next_x = (x + div_term + 1) >> 1  -- +1 做舍入

        -- 检查收敛（1 ULP 以内）
        local diff = next_x - x
        if diff >= -1 and diff <= 1 then break end

        x = next_x
    end
    return x
end

--- 计算两点间距离
function fp.distance(ax, ay, bx, by)
    local dx = fp.sub(ax, bx)
    local dy = fp.sub(ay, by)
    local dist_sq = fp.mul(dx, dx) + fp.mul(dy, dy)
    return fp.sqrt(dist_sq)
end

-- ---- 三角函数（查表法） ----

local SIN_TABLE = {}
local COS_TABLE = {}
local TRIG_TABLE_SIZE = 4096
local TRIG_TABLE_MASK = 4095

--- 初始化 sin/cos 查表（程序启动时调用一次）
function fp.init_trig()
    -- 避免重复初始化
    if #SIN_TABLE > 0 then return end

    for i = 0, TRIG_TABLE_SIZE - 1 do
        local angle = (i / TRIG_TABLE_SIZE) * (2.0 * math.pi)
        SIN_TABLE[i] = fp.from_float(math.sin(angle))
        COS_TABLE[i] = fp.from_float(math.cos(angle))
    end
end

--- 将定点角度映射到查表索引
local function angle_to_index(angle_raw)
    -- 归一化到 [0, 2π)
    local norm = angle_raw % fp.TWO_PI
    if norm < 0 then norm = norm + fp.TWO_PI end

    -- 映射: index = norm * TABLE_SIZE / TWO_PI
    -- 等价的定点运算: index = (norm * TABLE_SIZE) >> FRAC_BITS / TWO_PI
    -- 但 TWO_PI 是定点值，直接用整数乘法/除法
    local idx = (norm * TRIG_TABLE_SIZE) // fp.TWO_PI
    return idx & TRIG_TABLE_MASK
end

--- 正弦
function fp.sin(angle)
    return SIN_TABLE[angle_to_index(angle)]
end

--- 余弦
function fp.cos(angle)
    return COS_TABLE[angle_to_index(angle)]
end

-- ---- 2D 向量 ----

--- 二维向量表
-- 使用纯表: { x = fp_val, y = fp_val }
-- ⚠️ 帧同步中禁止使用 userdata（跨平台不可移植）

function fp.vec2(x, y)
    return { x = x or 0, y = y or 0 }
end

function fp.vec2_zero()
    return { x = 0, y = 0 }
end

function fp.vec2_add(a, b)
    return { x = a.x + b.x, y = a.y + b.y }
end

function fp.vec2_sub(a, b)
    return { x = a.x - b.x, y = a.y - b.y }
end

function fp.vec2_scale(v, s)
    return { x = fp.mul(v.x, s), y = fp.mul(v.y, s) }
end

function fp.vec2_mag_sqr(v)
    return fp.mul(v.x, v.x) + fp.mul(v.y, v.y)
end

function fp.vec2_mag(v)
    return fp.sqrt(fp.vec2_mag_sqr(v))
end

function fp.vec2_normalize(v)
    local mag = fp.vec2_mag(v)
    if mag == 0 then return fp.vec2_zero() end
    return { x = fp.div(v.x, mag), y = fp.div(v.y, mag) }
end

function fp.vec2_dot(a, b)
    return fp.mul(a.x, b.x) + fp.mul(a.y, b.y)
end

--- 2D 叉积（标量）
function fp.vec2_cross(a, b)
    return fp.mul(a.x, b.y) - fp.mul(a.y, b.x)
end

function fp.vec2_lerp(a, b, t)
    return {
        x = a.x + fp.mul(b.x - a.x, t),
        y = a.y + fp.mul(b.y - a.y, t),
    }
end

-- ---- 确定性随机数 ----

--- Xorshift128+ 随机数生成器
-- 状态存储为包含两个 64-bit 整数的表
local Random = {}
Random.__index = Random

--- 创建新的随机数生成器
-- @param seed 种子值（整数）
function fp.new_random(seed)
    -- 使用 SplitMix64 从单一 seed 生成两个初始状态
    local function splitmix64(x)
        x = x + 0x9E3779B97F4A7C15
        x = (x ~ (x >> 30)) * 0xBF58476D1CE4E5B9
        x = (x ~ (x >> 27)) * 0x94D049BB133111EB
        return x ~ (x >> 31)
    end

    -- Lua 5.3+ 的整数运算保证 64-bit 回绕
    local s0 = splitmix64(seed)
    local s1 = splitmix64(s0)

    return setmetatable({ s = { s0, s1 } }, Random)
end

--- 获取下一个随机数
function Random:next()
    local s1 = self.s[1]
    local s0 = self.s[2]
    self.s[1] = s0
    s1 = s1 ~ (s1 << 23)
    s1 = s1 ~ (s1 >> 17)
    s1 = s1 ~ s0
    s1 = s1 ~ (s0 >> 26)
    self.s[2] = s1
    return s0 + s1
end

--- 生成 [0, max) 范围的随机整数
function Random:range(max)
    -- 使用位掩码优化当 max 为 2 的幂时
    if (max & (max - 1)) == 0 then
        return self:next() & (max - 1)
    end
    -- 拒绝采样避免取模偏置
    -- 简化：直接用取模（对于非关键场景）
    return self:next() % max
end

--- 生成 [0, 1) 的定点随机数（Q16.16 格式）
function Random:fixed_01()
    -- 取高 32 位中的 16 位
    return (self:next() >> 48) & 0xFFFF
end

return fp
```

**Lua 使用示例**：

```lua
-- ============================================================
-- 在帧同步游戏逻辑中使用定点数（Lua）
-- ============================================================

local fp = require("fixed_point")

-- 游戏启动时初始化
fp.init_trig()
local rng = fp.new_random(123456789)  -- 由服务端下发种子

-- 玩家位置（Q16.16）
local player_x = fp.from_float(100.0)
local player_y = fp.from_float(200.0)

-- 速度（单位/帧）= 5.5 * Q16.16
local speed = fp.from_float(5.5)

-- 移动方向（角度）
local angle = fp.from_float(0.785398)  -- 45°

-- 每帧更新
local function update(dt_fixed)
    -- dt_fixed 是定点格式的 delta time
    -- 但通常帧同步不用 dt，而是固定帧率
    -- 这里演示带速度的移动

    local dx = fp.mul(speed, fp.cos(angle))
    local dy = fp.mul(speed, fp.sin(angle))

    player_x = fp.add(player_x, dx)
    player_y = fp.add(player_y, dy)

    -- 检查与敌人的碰撞距离
    local enemy_x = fp.from_float(150.0)
    local enemy_y = fp.from_float(250.0)
    local dist = fp.distance(player_x, player_y, enemy_x, enemy_y)

    -- 攻击范围 = 20.0
    local attack_range = fp.from_float(20.0)
    if dist <= attack_range then
        -- 触发攻击判定
        print("hit!")
    end
end
```

---

## 3. 练习

### 练习 1：定点数 AABB 碰撞检测 [基础]

**目标**：用定点数实现一个简单矩形碰撞检测系统，验证跨平台一致性。

**要求**：

1. 选择一个语言的定点数实现（C#/C++/Lua），基于本教程提供的代码
2. 实现一个 `AABB` 结构体，包含 `min_x`, `min_y`, `max_x`, `max_y`（均为定点数）
3. 实现 `aabb_overlap(a, b)` 返回 `bool`
4. 创建 100 个随机 AABB（用确定性随机数），检测所有两两碰撞对
5. **关键验证**：用相同的随机种子，在不同的编译器优化级别下（如 GCC `-O0` vs `-O2`）运行，确认碰撞检测结果完全一致

**提示**：
- AABB 重叠判断：`!(a.max_x < b.min_x || a.min_x > b.max_x || ...)`
- 定点数比较直接用整数比较即可
- 测试时使用 `std::sort` 对碰撞对排序后再对比

---

### 练习 2：定点数追逐 AI [进阶]

**目标**：实现使用定点数的追逐 AI，体验如何将浮点逻辑转换为定点。

**要求**：

1. 实现一个 `ChaseAI` 类：
   - 拥有位置 `(x, y)`（定点数）
   - 拥有速度（定点数，每帧移动距离）
   - 目标位置（定点数）
2. 每帧更新逻辑：
   - 计算到目标的方向向量：`dir = normalize(target_pos - my_pos)`
   - 向目标移动：`my_pos += dir * speed`
   - 如果距离小于 `attack_range`，进入攻击状态
3. 使用定点数的 `sqrt`、`sin`/`cos` 和 `atan2` 来实现**平滑旋转**：AI 每次最多旋转 `max_turn_rate` 弧度朝向目标
4. 绘制 AI 的移动轨迹（控制台输出坐标或简单图形），验证路径正确性

**提示**：
- `atan2(y, x)` 可以利用 `fp.atan2` 或 CORDIC 实现
- 角度差需要归一化到 `[-π, π]`
- 每帧旋转量 = `min(max_turn_rate, abs(angle_diff)) * sign(angle_diff)`

---

### 练习 3：跨平台 Desync 检测框架 [挑战]

**目标**：构建一个简易的帧同步 desync 检测和回放系统。

**要求**：

1. **帧状态记录**：
   - 每帧结束时，计算当前游戏状态的 hash 值（FNV-1a 或 CRC32）
   - 每 60 帧（1 秒）输出一次 hash 到日志
   
2. **指令记录**：
   - 记录每帧所有玩家的输入指令
   - 将指令序列保存为 JSON 文件（或在内存中保存）
   
3. **状态序列化**：
   - 实现游戏状态的序列化函数（输出为字节序列）
   - 每 300 帧保存一次完整状态快照
   
4. **回放验证**：
   - 实现从指定帧开始的回放功能
   - 回放时比对每帧的 hash 值
   - 定位第一帧不一致的位置
   
5. **差异定位**：
   - 在 desync 发生帧停止，打印该帧的所有游戏状态
   - 逐字段比对两个版本的状态差异

**提示**：
- Hash 函数选择 FNV-1a（简单且跨平台一致）：
  ```cpp
  uint32_t fnv1a(const void* data, size_t len, uint32_t hash = 0x811c9dc5) {
      const uint8_t* p = (const uint8_t*)data;
      for (size_t i = 0; i < len; ++i)
          hash = (hash ^ p[i]) * 0x01000193;
      return hash;
  }
  ```
- 状态序列化必须按**固定字段顺序**进行——不可用反射
- 反序列化时比对反序列化后的 hash 与记录中的 hash

---

## 4. 扩展阅读

- **IEEE 754 标准**：[IEEE 754-2019](https://standards.ieee.org/standard/754-2019.html) — 了解浮点运算的严格定义
- **CORDIC 算法**：Jack E. Volder, "The CORDIC Trigonometric Computing Technique" (1959) — 仅用移位和加法计算三角函数
- **《王者荣耀》技术分享**：[从王者荣耀聊聊游戏的帧同步](https://cloud.tencent.com/developer/article/2479003) — 国内帧同步标杆的技术选型
- **Gaffer On Games: Deterministic Lockstep**：[https://gafferongames.com/post/deterministic_lockstep/](https://gafferongames.com/post/deterministic_lockstep/) — 帧同步确定性经典文章
- **Unity DOTS FixedString**：Unity 的定点数学库 `com.unity.mathematics` 中的 `fixed` 类型
- **libfixmath**：[https://github.com/PetteriAimonen/libfixmath](https://github.com/PetteriAimonen/libfixmath) — C 语言 Q16.16 定点数开源库，含完整三角实现
- **Box2D 定点数移植**：[https://github.com/erincatto/box2d-lite](https://github.com/erincatto/box2d-lite) — Box2D 的简化版，可以尝试做定点移植练习
- **PCG 随机数生成器**：[https://www.pcg-random.org/](https://www.pcg-random.org/) — 统计质量优于 MT 的现代 PRNG

---

## 常见陷阱

### 陷阱 1：在游戏逻辑中混用浮点和定点

**症状**：部分计算使用定点，但调用了一个返回 `float` 的函数（如 Unity 的 `Vector3.Distance`），结果转换回定点——破坏了确定性。

**正确做法**：逻辑层完全禁止 `float`/`double`。所有数学运算通过定点数库完成。渲染层允许使用浮点，但这是**单向数据流**：逻辑层（定点） → 渲染层（浮点），绝不可反向。

### 陷阱 2：定点数溢出静默失败

**症状**：Q16.16 下两个 20000 相乘 → `20000 * 65536 * 20000 * 65536 >> 16` ≈ 溢出，结果为负值或小值。没有崩溃，但计算结果彻底错误。

**正确做法**：
- 使用 64-bit 中间结果（模板中的 `DoubleType`）
- 预判溢出：`if (abs(a) > safe_limit || abs(b) > safe_limit) clamp or error`
- 使用 `Q32.32`（64-bit）格式消除中间溢出风险

### 陷阱 3：查表法精度不足导致周期性错位

**症状**：4096 条目的 sin 表在 2π 周期的某些角度上精度为 `2π / 4096 ≈ 0.00153` 弧度。导航中方向反复切换时，由于量化误差，角色可能无法精确朝目标走，而是左右微摆。

**应对**：
- 增大表到 65536 条目（代价：256KB 内存）
- 使用线性插值：`sin(angle) = lerp(table[idx], table[idx+1], frac)`
- 对于高精度需求（如长距离弹道），使用 CORDIC 在线计算代替查表

### 陷阱 4：直接使用 `std::unordered_map` 遍历

**症状**：不同平台的 hash map 遍历顺序不同 → 实体更新顺序不同 → 两帧后状态微小差异 → 30 分钟后完全 desync。

**正确做法**：使用确定性容器——在遍历前收集 key 到 `std::vector` 中排序。

### 陷阱 5：忘记同步随机数种子

**症状**：`srand(time(NULL))` 每个客户端自己调用 → 永远不可能同步。

**正确做法**：服务端在开始帧下发统一的随机数种子。所有客户端的 PRNG 状态是**游戏状态的一部分**，需要被 hash 校验。

### 陷阱 6：定点数 sin/cos 的输入归一化不充分

**症状**：角度在长时间运行后累积到极大值（如 10000π），查表时映射到 `[0, 2π)` 的过程使用了浮点取模或依赖大整数除法——在不同平台上产生略微不同的结果。

**正确做法**：使用定点数取模（`%` 运算符）做归一化，确保纯整数运算。且取模过程中处理负值（Lua `%` 和 C `%` 对负数的语义不同！使用 `if (norm < 0) norm += TWO_PI` 统一行为）。

### 陷阱 7：物理引擎中的迭代收敛不确定

**症状**：Box2D 的约束求解器使用"迭代直到误差小于阈值"的策略。在定点数下，阈值本身就是一个固定值，迭代到该阈值时停止——但不同精度（Q16.16 vs Q32.32）的阈值位数不同，导致不同格式间停止在不同迭代数。

**正确做法**：固定迭代次数（如 body 的 `positionIterations = 3`，`velocityIterations = 8`），不依赖收敛判断。
