---
title: "帧同步核心原理：Lockstep 模型"
updated: 2026-06-05
---

# 帧同步核心原理：Lockstep 模型

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: 04 - 游戏循环与网络Tick集成

---

## 1. 概念讲解

### 1.1 为什么需要帧同步？

想象你在玩《王者荣耀》。你点击"攻击"按钮，你的英雄向敌人砍了一刀。与此同时，另外9个玩家也在各自操作。问题是：**如何让10台设备上运行的游戏世界保持完全一致？**

如果有人手机上显示"你砍中了敌人"，而敌人手机上显示"你miss了"，这游戏就没法玩了。

游戏网络同步的本质问题可以浓缩为一句话：

> 如何在多个独立计算机上维护同一个游戏世界的**一致视图**？

业界有两条主流路线：

| 方案 | 核心思想 | 代表游戏 |
|------|---------|---------|
| **帧同步 (Lockstep)** | 只同步玩家输入，每个客户端独立计算 | 星际争霸、魔兽争霸3、王者荣耀、Dota2 |
| **状态同步 (State Sync)** | 服务器是权威，同步对象状态 | CS:GO、守望先锋、魔兽世界 |

本篇聚焦帧同步。它的核心哲学极其简洁：

> **不要同步结果，同步原因。**

与其告诉所有人"英雄移动到了(100, 200)"，不如告诉所有人"玩家按了右键，目标点(300, 400)"。每个客户端拿到相同的输入，运行相同的逻辑代码，自然得到相同的结果。

### 1.2 Lockstep 的历史

Lockstep 的概念最早来自**实时策略游戏 (RTS)**。

**1998年，《星际争霸》** 的 Battle.net 对战需要同步成百上千个单位——每个小兵、每架飞机、每颗子弹。如果同步每个单位的状态，带宽需求将是指数级的。暴雪的工程师们意识到：RTS 游戏的玩家输入其实很少——每分钟只有几十到上百次点击。同步点击而非单位状态，带宽直接从"每帧几KB"降到"每秒几百字节"。这在 56K 拨号上网时代是生死攸关的区别。

**2002年，《魔兽争霸3》** 继承了这一架构，并将其打磨到极致。War3 的 Replay 文件之所以只有几十KB，正是因为录像只需存储初始状态 + 所有玩家的输入序列——回放时重新执行一遍即可。

**2010年代，MOBA 崛起。** Dota2（Source 2引擎）和《英雄联盟》在传统 RTS Lockstep 基础上做了关键改进：引入**服务器中转**（Server-Relayed），不再依赖 P2P 网络拓扑。

**2015年至今，《王者荣耀》** 将帧同步推向了移动端。在 4G/5G 不稳定的网络环境下，王者采用了**乐观帧锁定 (Optimistic Lockstep)**——服务器按固定频率广播帧，不等慢玩家，牺牲公平换流畅。这是帧同步在移动 MOBA 领域的标杆实践。

### 1.3 核心概念

#### Turn（逻辑帧）

帧同步中的"帧"不是渲染帧（60fps/120fps的GPU帧），而是**逻辑帧 (Logic Frame)**，通常称为 **Turn**。

```
时间轴: ──┬────┬────┬────┬────┬────→
        Turn0 Turn1 Turn2 Turn3 Turn4
         ↑     ↑     ↑     ↑     ↑
        收集   收集   收集   收集   收集
        输入   输入   输入   输入   输入
```

每个 Turn 包含三个步骤：
1. **收集输入**：汇集所有玩家在本 Turn 的操作指令
2. **执行逻辑**：所有客户端用相同的输入推进游戏状态
3. **等待同步**：P2P模式下等待所有人完成本Turn；服务器模式下等待服务器下发下Turn数据

Turn 的频率通常是 **15~30Hz**（每秒15~30个逻辑帧）。王者荣耀使用 15Hz（66ms/Turn），Dota2 使用 30Hz（33ms/Turn），星际争霸使用约 22.4Hz（游戏速度×真实时间）。

#### 确定性 (Determinism)

帧同步成立的前提条件是**确定性**：

> 相同的初始状态 + 相同的输入序列 + 相同的逻辑代码 = 相同的最终状态。

而且不是"差不多相同"——必须**逐比特完全相同**。一个浮点数最低位不同 → 蝴蝶效应 → 30秒后两个客户端的世界完全不一样（俗称"不同步"或 Desync）。

这是帧同步最大的工程挑战。我们在第6节会深入探讨浮点数陷阱及其解决方案。

#### 输入同步 (Input Synchronization)

帧同步网络上传输的是**玩家输入**，而非游戏状态。

典型的输入结构：

```csharp
struct FrameInput {
    uint frameNumber;       // 属于哪个Turn
    byte playerId;          // 哪个玩家
    uint16 inputFlags;      // 按键位掩码（每个bit代表一个操作）
    float targetX, targetY; // 鼠标/摇杆目标位置（实际用定点数）
}
```

对于王者荣耀一场10人对战、15fps逻辑帧率：
- 每个玩家每66ms发送一次输入
- 每个输入包约 8~16 字节
- 10个玩家每帧总计 80~160 字节
- 每秒上行带宽：每个玩家约 120~240 bytes/s
- 每秒下行（服务器广播整帧）：约 1.2~2.4 KB/s

对比状态同步：同步10个英雄的 position/rotation/velocity/HP/MP/技能CD...每秒轻松 20~50 KB/s。帧同步带宽优势是 **10~100倍**。

---

## 2. 数学模型

### 2.1 状态转移方程

帧同步可以用一个简洁的数学公式描述：

$$S_{n+1} = F(S_n, I_n)$$

其中：
- $S_n$：第 n 个 Turn 的游戏状态（所有实体的位置、血量、技能冷却等）
- $I_n$：第 n 个 Turn 所有玩家的输入集合（一个由所有玩家操作合并而成的指令集）
- $F$：游戏逻辑函数（确定性函数，对所有客户端完全一致）

这个公式揭示的关键性质：

1. **封闭性**：游戏状态只由前一个状态和当前输入决定，不受外部因素（系统时间、随机硬件状态、网络包到达顺序等）影响
2. **确定性**：F 是纯函数——相同输入永远产生相同输出
3. **可重现性**：给定 $S_0$ 和 $I_0, I_1, ..., I_k$，任何人都可以精确重现 $S_{k+1}$

### 2.2 展开形式

将递推公式展开：

$$S_n = F(F(...F(F(S_0, I_0), I_1), ...), I_{n-1})$$

这表明：**游戏全程状态可以被初始状态 S₀ 和所有 Turn 的输入序列唯一确定**。

这就是录像回放系统的理论基础：录像文件 = S₀ + [I₀, I₁, I₂, ..., Iₙ]。

### 2.3 输入集合的定义

$$I_n = \{ i_n^1, i_n^2, ..., i_n^P \}$$

其中 P 是玩家数量，$i_n^p$ 是玩家 p 在第 n 帧的输入。注意：

- 如果玩家 p 在第 n 帧没有任何操作，$i_n^p = \emptyset$（空操作）
- **空操作也是一种确定性的输入**——不能说"没有输入就是未知"，必须明确定义空操作的行为
- 所有客户端的 $I_n$ 必须完全一致——包括输入的顺序

---

## 3. 三种 Lockstep 变体

### 3.1 P2P Lockstep（传统 RTS 模型）

```
┌─────────┐         ┌─────────┐
│ Player A │◄───────►│ Player B │
└─────────┘  输入     └─────────┘
     │  互相发送          │
     │                    │
     ▼                    ▼
  各自执行逻辑        各自执行逻辑
```

**工作原理**：
1. 每个玩家将自己本 Turn 的输入直接发送给其他所有玩家
2. 每个玩家等待**收到所有其他玩家**的输入后，才执行本 Turn 逻辑
3. 如果某个玩家网络延迟高，**所有玩家都必须等待**

**特点**：
- 优点：无服务器成本，纯P2P网络；带宽利用率高
- 致命缺陷：**网络差的人拖累所有人**。一个玩家 200ms 延迟 → 所有玩家每帧等 200ms → 游戏卡成 PPT

**代表游戏**：星际争霸1（Battle.net 1.0）、魔兽争霸3（LAN模式）、帝国时代系列早期版本。

### 3.2 Server-Relayed Lockstep（服务器中转）

```
┌─────────┐         ┌──────────┐         ┌─────────┐
│ Player A │──输入──►│  服务器   │◄──输入──│ Player B │
└─────────┘         └──────────┘         └─────────┘
     │                    │                    │
     │◄──广播所有输入─────│────广播所有输入────►│
     │                    │                    │
     ▼                    ▼                    ▼
  执行逻辑             (可选)校验          执行逻辑
```

**工作原理**：
1. 玩家将输入发送给**服务器**而非彼此
2. 服务器在收集完所有玩家本 Turn 的输入后（或超时后），统一广播给所有人
3. 客户端收到完整的 $I_n$ 后才执行

**P2P 变体的关键改进**：
- 解决了 P2P 的 NAT 穿透问题（尤其是移动网络）
- 服务器可以**超时决策**：某个玩家超过时限未发送输入 → 服务器生成一个空输入代替，不阻塞其他人
- 服务器可做基本校验（输入合法性、帧号连续性）
- 断线重连更容易：服务器缓存输入历史，重连客户端可以"追赶"

**代表游戏**：Dota2、英雄联盟、王者荣耀（早期版本）。

### 3.3 Optimistic Lockstep（乐观帧锁定）

```
服务器固定频率广播（不等待慢玩家）
         │
    ┌────┴────┐
    ▼         ▼
 Turn n    Turn n+1
  │          │
  │ 玩家A延迟? → 服务器用"空操作"填充玩家A的输入
  │ 不等待！直接广播继续
  │
  ▼
 快玩家不受影响，慢玩家丢失操作
```

**工作原理**：
1. 服务器按**固定频率**（如每 66ms）广播一帧
2. 在广播时刻，服务器收集**已到达**的所有玩家输入
3. 未到达的玩家 → 其输入被视为"空操作"
4. 服务器立即广播，**不等待任何人**

**这是王者荣耀当前使用的方案**。

**关键权衡**：
- 快玩家体验丝滑——不会因队友网卡而被拖累
- 慢玩家吃亏——延迟导致操作在预期之外的时间生效或被丢失
- 服务器需要维持一个**帧缓冲区 (Frame Buffer)**：客户端不是到了 Turn n 才发送输入，而是提前发送未来几帧的输入，给网络抖动留出缓冲空间

**与"乐观"一词的对应**：服务器"乐观地"假设所有玩家的输入都会按时到达，直接推进逻辑帧。如果后续发现不对——在严格的 Optimistic Lockstep 中可能需要**回滚 (Rollback)**。但王者荣耀的实现更接近"超时不等待"而非真正的"乐观执行+回滚"。

---

## 4. Bucket 机制

### 4.1 渲染帧 vs 逻辑帧

游戏面临两个不同的帧率：

| | 渲染帧 (Render Frame) | 逻辑帧 (Logic Frame / Turn) |
|---|---|---|
| **频率** | 30/60/120/144 Hz | 15~30 Hz |
| **驱动** | GPU vsync / 可变 | 网络时钟 / 固定 |
| **内容** | 绘制画面、播放动画 | 执行游戏逻辑、更新状态 |
| **可变性** | 可变（帧率不稳时） | 稳定（由服务器时钟驱动） |

帧同步中，**逻辑帧率远低于渲染帧率**。一个 60fps 的渲染帧率搭配 15Hz 的逻辑帧率意味着：**每4个渲染帧对应1个逻辑帧**。

```
渲染帧: ████│████│████│████│████ (每 16.6ms)
逻辑帧: ██████│██████│██████│      (每 66ms)
            Turn N   Turn N+1
```

### 4.2 Bucket 的定义

**Bucket（桶）** 是指一个逻辑帧周期内的**渲染帧集合**。

- 逻辑帧率 15Hz → 逻辑帧间隔 66.67ms
- 渲染帧率 60Hz → 渲染帧间隔 16.67ms
- 一个 Bucket = 4 个渲染帧

玩家在一个 Bucket 内的所有操作，在 Bucket 结束时被打包成一个输入发送给服务器：

```
Bucket N (对应 Turn N):
  渲染帧0: 玩家按下了"右键" (移动指令)
  渲染帧1: (无操作)
  渲染帧2: 玩家按下了"A键" (攻击指令)
  渲染帧3: (无操作)
  ── Bucket 结束 ──
  发送 Input{N}: { move:(300,400), attack:targetEnemyId }
```

### 4.3 同一 Bucket 内的冲突解决

如果玩家在同一 Bucket 内做了两个互斥的操作（比如先按攻击、再按移动），通常有两种策略：

- **最后有效 (Last Wins)**：保留 Bucket 内最后一个操作。简单，但可能丢失意图。
- **操作队列 (Action Queue)**：保留所有操作按顺序在下个逻辑帧依次执行。更精确，但实现复杂。

王者荣耀采用**操作队列 + 逻辑帧内依次消费**的方式。

### 4.4 为什么要用 Bucket？

1. **减少网络包数量**：不是每个渲染帧都发包，而是凑满一个 Bucket 再发
2. **掩盖输入抖动**：渲染帧率不稳不影响逻辑层
3. **降低服务器负载**：15Hz 意味着服务器每秒只需处理 15 次帧广播，而不是 60 次
4. **与网络 RTT 对齐**：Bucket 时长（66ms）≈ 移动网络典型 RTT（50~100ms），输入延迟可预测

---

## 5. 帧同步的优缺点深度分析

### 5.1 优点

#### ① 带宽极小

这是帧同步最核心的优势。网络传输量只与**玩家数量和操作频率**有关，与**游戏世界复杂度**无关。

对比表格：

| 场景 | 帧同步带宽 | 状态同步带宽 |
|------|-----------|-------------|
| 100 个小兵战斗 | ~200 bytes/s (只传操作) | ~5KB/s (传100个单位状态) |
| 1000 个单位会战 | ~200 bytes/s (不变!) | ~50KB/s (线性增长) |
| 仅1个英雄走动 | ~200 bytes/s | ~1KB/s |

对于 MOBA/RTS 这种单位数量动态变化的游戏，帧同步在带宽上的优势是降维打击。

#### ② 天然可录像

由于游戏状态完全由初始状态 + 输入序列决定，录像文件只需存储：
- 游戏配置（版本号、地图）
- 随机种子
- 初始状态（S₀）
- 所有玩家的输入序列 [I₀, I₁, ..., Iₙ]

一场 30 分钟的对战，录像文件通常只有 50~200KB。对比视频录像的几百MB，这是**1000倍**的压缩比。更重要的是，录像可以**任意视角回放**——因为回放时是重新执行游戏逻辑，你可以自由切换视角、查看任何角落。

#### ③ 反外挂相对简单（理论上）

帧同步中，所有客户端运行相同的逻辑代码。反外挂的基本手段是**状态校验**：

- 每隔 N 帧，客户端计算当前游戏状态的 **Hash（如 MD5 前8字节）** 发送给服务器
- 服务器比对所有客户端的 Hash
- Hash 不一致 → 有人作弊或出现了 desync

这是"校验"而非"预防"。但帧同步的校验比状态同步的成本低很多——不需要服务器也跑完整逻辑。

在 Dota2 中，Valve 通过**服务器也跑一份逻辑**来做裁决（类似仲裁者模式），组队比赛中如果3人状态一致而1人不一致，可以直接判定不一致者作弊或客户端异常。

#### ④ 服务器成本低

P2P Lockstep 不需要服务器。Server-Relayed Lockstep 的服务器只做**转发 + 轻量校验**，不需要运行游戏逻辑，因此：
- 单台服务器可以承载数百个房间
- 不需要高性能 CPU，甚至可以不用 GPU
- 扩展性好——加服务器就是加房间容量

### 5.2 缺点

#### ① 确定性极难保证

这是帧同步工程上最大的难点。以下任何一个差异都会导致 desync：

| 差异来源 | 例子 |
|---------|------|
| **浮点数** | x86 vs ARM 的浮点运算可能产生不同低位结果 |
| **编译器优化** | Release 模式下 `(a+b)+c` vs `a+(b+c)` 结合律 |
| **不同语言的运行时** | C# 的 `Math.Sin()` vs C++ 的 `std::sin()` |
| **随机数实现** | 不同语言/库的 PRNG 算法不同 |
| **容器迭代顺序** | `Dictionary.Keys` 在不同机器上遍历顺序不同 |
| **多线程竞态** | 两个线程计算结果的合并顺序不确定 |
| **第三方物理引擎** | PhysX/Box2D 内部有非确定性优化 |

解决方案：定点数数学库、确定性物理引擎重写、禁止使用任何不确定性API。详见教程 06。

#### ② P2P 模式：网络差影响所有人

传统 P2P Lockstep 中，所有玩家必须等待最慢的那个人。这是设计上的"木桶效应"——全队的体验由网最差的人决定。在互联网环境下这是致命缺陷。

Server-Relayed + Optimistic 极大地缓解了这个问题，但代价是慢玩家体验下降。

#### ③ 断线重连困难

状态同步下，断线重连只需服务器发一次"当前世界快照"，客户端用最新状态替换即可。

帧同步下，断线的客户端缺失了一段时间的输入序列。要恢复到当前状态，它有两个选择：

- **快进追赶 (Fast-forward)**：从断线时刻开始，用服务器缓存的输入序列以最快速度重新执行逻辑帧，直到追上当前帧。这是主流方案。
- **快照恢复**：服务器定期保存完整游戏状态快照，重连时下发快照 + 快照之后的输入序列。缺点是需要大量存储。

王者荣耀采用**快进追赶**：断线重连时客户端加速执行所有历史帧，玩家看到"正在重新连接..."的进度条就是逻辑帧在追赶。

#### ④ 客户端可以做外挂

因为所有逻辑计算都在客户端，作弊者可以：
- 修改本地逻辑代码（如"攻击力 × 100"）
- 读取本地内存获取全图信息（地图 hack）
- 伪造输入（虽然可能被基本校验拦截）

**状态校验**可以检测到结果不一致，但仍有两个问题：
- 校验是**事后**的，作弊者已经获得了好处
- 1v1 场景下 Hash 不一致无法判断谁对谁错

这也是为什么帧同步更适合**团队竞技**（3v3/5v5）——可以用多数投票来判定。

---

## 6. 与帧同步配合的技术栈

### 6.1 定点数 (Fixed-Point Math)

帧同步的基石。用整数模拟小数，确保所有平台上的运算结果逐比特一致。

```csharp
// 定点数：用 64 位整数存储，低 16 位为小数部分
public struct Fix64 {
    long rawValue; // Q48.16 格式
    
    public static Fix64 operator +(Fix64 a, Fix64 b) {
        return new Fix64 { rawValue = a.rawValue + b.rawValue };
    }
    
    public static Fix64 FromFloat(float f) {
        return new Fix64 { rawValue = (long)(f * 65536.0f) };
    }
}
```

第6节教程会专门深度讲解定点数的完整实现。

### 6.2 确定性物理

不能使用 PhysX/Box2D/Havok 的默认模式——它们内部使用了浮点数和非确定性优化。

解决方案：
- 自研简单的确定性物理（AABB 碰撞 + 固定步长积分）
- 或使用第三方确定性物理库（如 BEPUphysics v2 的定点数模式）
- 对于复杂物理需求不高的 MOBA，自研 2D 碰撞即可满足需求

### 6.3 确定性伪随机

所有"随机"行为（暴击率、伤害浮动、掉落）必须基于**伪随机数生成器 (PRNG)**：

```csharp
// 确定性随机：指定种子后序列完全确定
class DeterministicRandom {
    uint state;
    
    public DeterministicRandom(uint seed) {
        state = seed;
    }
    
    // Xorshift32 算法
    public uint Next() {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        return state;
    }
    
    // 生成 [0, max) 范围内的整数
    public int Range(int max) {
        return (int)(Next() % (uint)max);
    }
}
```

每个随机行为（暴击、掉落）必须从一个由服务器分配的**全局随机种子**派生出自己的种子，确保所有客户端在相同逻辑帧产生相同的"随机"结果。

### 6.4 逻辑与表现分离

帧同步架构要求严格分离逻辑层和表现层：

```
┌─────────────────────────────────┐
│          表现层 (View)            │
│  - 渲染动画、粒子特效              │
│  - 插值/平滑移动                  │
│  - 音效                          │
│  - UI 更新                       │
│  ┌─────────────────────────────┐│
│  │     逻辑层 (Model)           ││
│  │  - 确定性游戏逻辑             ││
│  │  - 定点数数学                ││
│  │  - 确定性物理                ││
│  │  - 输入处理                  ││
│  │  - 状态管理                  ││
│  │  ← 由网络帧驱动，每Turn执行  ││
│  └─────────────────────────────┘│
└─────────────────────────────────┘
```

- **逻辑层**：纯数据驱动，无副作用，无 IO，无 Unity/UE API 调用。只需要 C#/C++/Lua 的纯计算。
- **表现层**：读取逻辑层状态，做插值、动画、特效。不写回逻辑层。

这是帧同步和状态同步共通的架构原则。

---

## 7. 王者荣耀帧同步架构深度解析

### 7.1 整体架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  客户端 A     │     │   Battle     │     │  客户端 B     │
│              │     │   Server     │     │              │
│ ┌──────────┐ │     │ ┌──────────┐ │     │ ┌──────────┐ │
│ │ 逻辑层    │ │◄───►│ │ 帧管理器  │ │◄───►│ │ 逻辑层    │ │
│ │(15Hz)    │ │ UDP │ │ 广播帧    │ │ UDP │ │(15Hz)    │ │
│ └──────────┘ │     │ │ 缓存历史  │ │     │ └──────────┘ │
│ ┌──────────┐ │     │ │ 输入校验  │ │     │ ┌──────────┐ │
│ │ 表现层    │ │     │ └──────────┘ │     │ │ 表现层    │ │
│ │(30-60fps)│ │     │              │     │ │(30-60fps)│ │
│ └──────────┘ │     │  GameCenter  │     │ └──────────┘ │
│              │     │  (匹配服务器) │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
```

### 7.2 服务器角色

王者荣耀的 Battle Server 并非"哑转发"——它是一个智能中转器：

| 职责 | 说明 |
|------|------|
| **帧时钟** | 15Hz 固定频率驱动，不受客户端影响 |
| **输入聚合** | 收集所有玩家在截止时间前的输入 |
| **空操作填充** | 超时未到的玩家用空输入替代 |
| **帧广播** | 将聚合后的整帧输入推送给所有客户端 |
| **输入缓存** | 保留最近 N 帧的输入历史（用于断线重连） |
| **状态校验** | 定期收集客户端 Hash 比对 |

### 7.3 帧时序详解

```
服务器时间轴:

 t=0     t=66ms  t=132ms t=198ms
  │        │       │       │
  ├─Turn0──┤─Turn1─┤─Turn2─┤
  │        │       │       │
  │ 收集窗口│       │       │
  │←─20ms─→│       │       │
  │ 广播   │       │       │

客户端时间轴 (正常):

 发送Turn0输入     收到Turn0广播
  │   发送Turn1输入   │   执行Turn0
  │    │   收到Turn1广播 │   执行Turn1
  │    │    │    │       │
  ├────┼────┼────┼───────┤
  │    │    │    │       │
  │ 提前发送未来帧输入
  │ (Frame Buffer 2-3帧)
```

关键点：
- 客户端**提前**发送未来 2~3 帧的输入（预测性缓冲）
- 服务器在 Turn N 的收集窗口结束时，立刻广播 Turn N 数据
- 客户端收到 Turn N 数据后执行逻辑，同时继续发送 Turn N+2、N+3 的输入

### 7.4 断线重连流程

```
1. 客户端检测断线 (UDP 心跳超时)
       │
2. 重新连接 Battle Server
       │
3. 服务器下发: "你断在 Turn 1250, 当前 Turn 1800"
       │
4. 服务器下发历史输入: I_1250 到 I_1800 (约 550 帧)
       │
5. 客户端以最快速度执行 1250→1800 的逻辑
   (跳过渲染, 纯计算, 通常 2-5 秒完成)
       │
6. 追赶完成, 进入正常同步
```

为什么是"快进"而非"跳帧"？因为每帧的游戏状态是累积计算的——不能跳过中间帧直接算最终状态（除非服务器也保存了快照）。

### 7.5 为什么王者荣耀选帧同步而不是状态同步？

| 考量因素 | 分析 |
|---------|------|
| **单位数量** | 每局 10 英雄 + 小兵 + 野怪 ≈ 50+ 个单位，状态同步带宽过高 |
| **移动网络** | 中国 4G/5G 上行带宽有限（1~3Mbps），帧同步的 200 bytes/s 上行完全无压力 |
| **录像回放** | 王者内置的"王者时刻"录像系统天然受益于帧同步，录像文件极小 |
| **服务器成本** | 帧同步 Battle Server 只转发，不跑逻辑，成本远低于状态同步的 DS |
| **确定性需求** | MOBA 的技能逻辑相对可控——自研引擎，无第三方物理库依赖 |

---

## 8. 代码示例

### 8.1 C# — 简单 Lockstep 模拟器（控制台，2 玩家）

```csharp
// LockstepSimulator.cs — 用控制台模拟 2 人帧同步对战
// 编译运行: dotnet run
// 需要: .NET 6+

using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

namespace LockstepSimulator;

// ─── 输入结构 ────────────────────────────────────────
public struct PlayerInput
{
    public int FrameNumber;
    public int PlayerId;
    public char Action; // 'M'=移动, 'A'=攻击, 'N'=无操作
    public int TargetX, TargetY;

    public static PlayerInput Empty(int frame, int playerId)
        => new() { FrameNumber = frame, PlayerId = playerId, Action = 'N' };

    public override string ToString() => $"[P{PlayerId} F{FrameNumber}] {Action}({TargetX},{TargetY})";
}

// ─── 游戏状态 ────────────────────────────────────────
public class GameState
{
    // 模拟 2 个玩家的位置和血量
    public int[] PosX = { 0, 10 };
    public int[] PosY = { 0, 10 };
    public int[] HP   = { 100, 100 };
    public int CurrentFrame;

    // 确定性逻辑 Tick: 对所有客户端完全一致
    public void ApplyInput(PlayerInput[] inputs)
    {
        foreach (var input in inputs)
        {
            int pid = input.PlayerId;
            switch (input.Action)
            {
                case 'M':
                    // 移动指令 (简化: 直接设置目标位置)
                    PosX[pid] = input.TargetX;
                    PosY[pid] = input.TargetY;
                    Console.WriteLine($"  P{pid} 移动到 ({input.TargetX},{input.TargetY})");
                    break;

                case 'A':
                    // 攻击指令 (攻击另一名玩家)
                    int other = 1 - pid;
                    // 简化: 距离 ≤3 则造成伤害
                    int dx = PosX[pid] - PosX[other];
                    int dy = PosY[pid] - PosY[other];
                    if (dx * dx + dy * dy <= 9)
                    {
                        HP[other] -= 10;
                        Console.WriteLine($"  P{pid} 攻击 P{other}! P{other} HP={HP[other]}");
                    }
                    else
                    {
                        Console.WriteLine($"  P{pid} 攻击 P{other} 但距离太远无伤害");
                    }
                    break;

                case 'N':
                    // 无操作 — 帧同步中必须显式处理
                    break;
            }
        }
        CurrentFrame++;
    }

    public void Display()
    {
        Console.WriteLine($"\n=== Frame {CurrentFrame} ===");
        Console.WriteLine($"  P0: pos=({PosX[0]},{PosY[0]}) HP={HP[0]}");
        Console.WriteLine($"  P1: pos=({PosX[1]},{PosY[1]}) HP={HP[1]}");
        Console.WriteLine(new string('-', 30));
    }
}

// ─── 模拟网络延迟 ────────────────────────────────────
public class SimulatedNetwork
{
    private readonly ConcurrentQueue<(int targetId, PlayerInput input)> _queue = new();
    private readonly Random _rng = new();

    // 模拟丢包与延迟
    public void Send(int fromPlayerId, PlayerInput input, int toPlayerId)
    {
        // 10% 丢包率
        if (_rng.NextDouble() < 0.1)
        {
            Console.WriteLine($"  [网络] P{fromPlayerId}→P{toPlayerId} 丢包: {input}");
            return;
        }

        // 模拟 20~80ms 随机延迟
        int delayMs = _rng.Next(20, 80);
        Task.Run(async () =>
        {
            await Task.Delay(delayMs);
            _queue.Enqueue((toPlayerId, input));
        });
    }

    public bool TryReceive(int playerId, out PlayerInput input)
    {
        // 简单轮询: 查找队列中目标为此玩家的输入
        var snapshot = _queue.ToArray();
        for (int i = 0; i < snapshot.Length; i++)
        {
            if (snapshot[i].targetId == playerId)
            {
                input = snapshot[i].input;
                // 移除 (简化: 重新构建队列)
                _queue.Clear();
                for (int j = 0; j < snapshot.Length; j++)
                    if (j != i) _queue.Enqueue(snapshot[j]);
                return true;
            }
        }
        input = default;
        return false;
    }
}

// ─── 主循环 ──────────────────────────────────────────
public class Program
{
    // 模拟每个玩家的操作序列 (帧号 → 操作)
    private static readonly PlayerInput[] PlayerScript = new[]
    {
        // P0 的操作脚本
        new PlayerInput { PlayerId = 0, Action = 'M', TargetX = 3, TargetY = 3 },
        new PlayerInput { PlayerId = 0, Action = 'M', TargetX = 5, TargetY = 5 },
        new PlayerInput { PlayerId = 0, Action = 'A', TargetX = 0, TargetY = 0 },
        new PlayerInput { PlayerId = 0, Action = 'N' },
        new PlayerInput { PlayerId = 0, Action = 'A', TargetX = 0, TargetY = 0 },
    };

    public static async Task Main()
    {
        Console.WriteLine("=== Lockstep 帧同步模拟器 (2 Players, 5 Turns) ===\n");

        var network = new SimulatedNetwork();
        var stateP0 = new GameState(); // P0 视角的游戏状态
        var stateP1 = new GameState(); // P1 视角的游戏状态 (应与 P0 完全一致)

        // 在帧同步中，P2P 模式每个玩家都需要等待收到对方输入才能推进
        // 这里模拟 Server-Relayed: 有一个中央汇聚点
        for (int frame = 0; frame < 5; frame++)
        {
            Console.WriteLine($"--- Turn {frame} ---");

            // 1. 玩家发送自己的输入给对方
            var inputP0 = frame < PlayerScript.Length
                ? PlayerScript[frame] with { FrameNumber = frame }
                : PlayerInput.Empty(frame, 0);

            // P1 做一个简单操作 (每帧向 P0 移动)
            var inputP1 = new PlayerInput
            {
                FrameNumber = frame,
                PlayerId = 1,
                Action = 'M',
                TargetX = Math.Max(0, stateP1.PosX[1] - 1), // 向{P0坐标}靠近
                TargetY = Math.Max(0, stateP1.PosY[1] - 1)
            };

            Console.WriteLine($"  P0 发送: {inputP0}");
            Console.WriteLine($"  P1 发送: {inputP1}");

            // 2. 通过网络互相发送
            network.Send(0, inputP0, 1);
            network.Send(1, inputP1, 0);

            // 3. 等待收到对方输入 (模拟网络延迟)
            PlayerInput receivedP1ByP0 = default, receivedP0ByP1 = default;
            bool p0Ready = false, p1Ready = false;
            var timeout = DateTime.UtcNow.AddMilliseconds(200);

            while (!p0Ready || !p1Ready)
            {
                if (!p0Ready && network.TryReceive(0, out var inp))
                {
                    receivedP1ByP0 = inp;
                    p0Ready = true;
                }
                if (!p1Ready && network.TryReceive(1, out var inp2))
                {
                    receivedP0ByP1 = inp2;
                    p1Ready = true;
                }
                if (DateTime.UtcNow > timeout)
                {
                    Console.WriteLine("  [超时] 未收到对方输入，使用空操作代替");
                    if (!p0Ready) { receivedP1ByP0 = PlayerInput.Empty(frame, 1); p0Ready = true; }
                    if (!p1Ready) { receivedP0ByP1 = PlayerInput.Empty(frame, 0); p1Ready = true; }
                }
                await Task.Delay(5);
            }

            // 4. 两个客户端各自执行相同的逻辑
            //    P0 收到: 自己的输入 + P1 的输入
            //    P1 收到: 自己的输入 + P0 的输入
            //    关键: 两者构造的 inputs[] 顺序必须完全一致 (通常按 PlayerId 排序)
            var inputsP0 = new[] { inputP0, receivedP1ByP0 };
            var inputsP1 = new[] { receivedP0ByP1, inputP1 };

            stateP0.ApplyInput(inputsP0);
            stateP1.ApplyInput(inputsP1);

            stateP0.Display();

            // 5. 验证确定性: 两个状态必须完全一致
            bool consistent =
                stateP0.PosX[0] == stateP1.PosX[0] &&
                stateP0.PosY[0] == stateP1.PosY[0] &&
                stateP0.HP[0] == stateP1.HP[0] &&
                stateP0.PosX[1] == stateP1.PosX[1] &&
                stateP0.PosY[1] == stateP1.PosY[1] &&
                stateP0.HP[1] == stateP1.HP[1];

            Console.WriteLine(consistent
                ? "  ✓ 状态一致 (P0 == P1)"
                : "  ✗ DESYNC! P0 和 P1 状态不一致!");
        }

        Console.WriteLine("\n=== 模拟结束 ===");
    }
}
```

**运行说明**：
- 新建 .NET 控制台项目，将上述代码替换 `Program.cs`
- `dotnet run` 即可看到帧同步的完整流程
- 注意观察网络丢包和延迟模拟下，超时机制如何保证游戏不卡死
- 两个 GameState 实例代表两个不同客户端，最终状态应一致

### 8.2 C++ — LockstepManager 骨架代码

```cpp
// LockstepManager.h — 帧同步管理器骨架
// 编译: clang++ -std=c++20 LockstepManager.cpp -o lockstep
#pragma once

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <functional>
#include <queue>
#include <chrono>

// ─── 基本类型定义 ────────────────────────────────────
using FrameNum = uint32_t;
using PlayerId = uint8_t;

// 玩家输入: 按位编码以节省带宽
union PlayerInput {
    struct {
        uint16_t move      : 1;   // 移动标志
        uint16_t attack    : 1;   // 攻击标志
        uint16_t skill1    : 1;   // 技能1
        uint16_t skill2    : 1;   // 技能2
        uint16_t skill3    : 1;   // 技能3
        uint16_t skill4    : 1;   // 技能4 (大招)
        uint16_t reserved  : 10;  // 预留
    } flags;
    uint16_t raw;

    PlayerInput() : raw(0) {}
    explicit PlayerInput(uint16_t r) : raw(r) {}

    bool operator==(const PlayerInput& other) const {
        return raw == other.raw;
    }
};

// 一个逻辑帧的完整输入 (所有玩家)
struct FrameInput {
    FrameNum frame;
    std::unordered_map<PlayerId, PlayerInput> inputs; // playerId → 输入

    bool hasPlayer(PlayerId pid) const {
        return inputs.contains(pid);
    }

    PlayerInput getOr(PlayerId pid, PlayerInput fallback) const {
        auto it = inputs.find(pid);
        return (it != inputs.end()) ? it->second : fallback;
    }
};

// ─── Lockstep 管理器 ─────────────────────────────────
class LockstepManager {
public:
    // 逻辑帧率: 每秒 N 帧
    static constexpr int LOGIC_FPS = 15;
    // 每帧间隔毫秒
    static constexpr int FRAME_MS = 1000 / LOGIC_FPS;  // 66ms

    // 帧缓冲区大小: 服务器会预缓存未来 N 帧
    static constexpr size_t FRAME_BUFFER_SIZE = 60; // 缓存 4 秒

    // 逻辑 Tick 回调: 每帧 State → State
    using LogicTickFn = std::function<void(FrameNum, const FrameInput&)>;

private:
    FrameNum m_currentFrame = 0;
    std::vector<PlayerId> m_players;

    // 输入队列: frameNum → FrameInput
    std::unordered_map<FrameNum, FrameInput> m_inputBuffer;

    // 逻辑 Tick
    LogicTickFn m_onTick;

    // 时钟
    using Clock = std::chrono::steady_clock;
    Clock::time_point m_lastTickTime;

public:
    explicit LockstepManager(LogicTickFn onTick)
        : m_onTick(std::move(onTick))
    {
        m_lastTickTime = Clock::now();
    }

    // 设置玩家列表 (服务器在房间创建时确定)
    void setPlayers(std::vector<PlayerId> players) {
        m_players = std::move(players);
    }

    // ─── 客户端方法 ──────────────────────────────

    // 客户端: 提交本地输入
    void submitLocalInput(PlayerId pid, PlayerInput input) {
        m_inputBuffer[m_currentFrame].inputs[pid] = input;
        m_inputBuffer[m_currentFrame].frame = m_currentFrame;
    }

    // ─── 服务器方法 ──────────────────────────────

    // 服务器: 接收某个玩家的输入
    void receivePlayerInput(FrameNum frame, PlayerId pid, PlayerInput input) {
        m_inputBuffer[frame].inputs[pid] = input;
        m_inputBuffer[frame].frame = frame;
    }

    // 服务器: 检查是否所有玩家都已提交当前帧输入
    bool isFrameComplete(FrameNum frame) const {
        auto it = m_inputBuffer.find(frame);
        if (it == m_inputBuffer.end()) return false;

        for (auto pid : m_players) {
            if (!it->second.hasPlayer(pid)) return false;
        }
        return true;
    }

    // 服务器: 如果超时，用空操作填充未到达的玩家输入
    void fillMissingWithEmpty(FrameNum frame) {
        auto& frameInput = m_inputBuffer[frame];
        for (auto pid : m_players) {
            if (!frameInput.hasPlayer(pid)) {
                frameInput.inputs[pid] = PlayerInput{}; // 空操作
            }
        }
    }

    // 服务器: 获取完整的帧输入 (含空操作填充)
    FrameInput getFrameInput(FrameNum frame) const {
        auto it = m_inputBuffer.find(frame);
        if (it == m_inputBuffer.end()) return FrameInput{};

        auto result = it->second;
        // 确保所有玩家都有输入 (包括空)
        for (auto pid : m_players) {
            if (!result.hasPlayer(pid)) {
                result.inputs[pid] = PlayerInput{};
            }
        }
        return result;
    }

    // ─── 公共方法 ────────────────────────────────

    // 推进逻辑帧 (客户端在收到服务器广播后调用)
    void advance(const FrameInput& frameInput) {
        if (m_onTick) {
            m_onTick(m_currentFrame, frameInput);
        }
        m_currentFrame++;

        // 清理已消费的旧帧数据 (保留最近 FRAME_BUFFER_SIZE 帧)
        if (m_currentFrame > FRAME_BUFFER_SIZE) {
            FrameNum toRemove = m_currentFrame - FRAME_BUFFER_SIZE - 1;
            m_inputBuffer.erase(toRemove);
        }
    }

    // 获取输入缓存 (用于断线重连，发送历史帧)
    const std::unordered_map<FrameNum, FrameInput>& getInputHistory() const {
        return m_inputBuffer;
    }

    FrameNum currentFrame() const { return m_currentFrame; }

    // 帧状态快照 Hash (简化实现: XOR 所有输入的 raw 值)
    uint32_t computeStateHash(FrameNum frame) const {
        auto it = m_inputBuffer.find(frame);
        if (it == m_inputBuffer.end()) return 0;

        uint32_t hash = 0;
        for (const auto& [pid, input] : it->second.inputs) {
            hash ^= (static_cast<uint32_t>(input.raw) << (pid * 2));
        }
        return hash;
    }
};

// ─── 使用示例 ────────────────────────────────────────
// int main() {
//     LockstepManager manager([](FrameNum frame, const FrameInput& input) {
//         // 游戏逻辑在这里执行
//         printf("Tick Frame %u\n", frame);
//     });
//
//     manager.setPlayers({0, 1}); // 2 个玩家
//
//     // 模拟: 接收 P0 和 P1 的输入
//     manager.receivePlayerInput(0, 0, PlayerInput(0x0001)); // P0 移动
//     manager.receivePlayerInput(0, 1, PlayerInput(0x0000)); // P1 无操作
//
//     if (manager.isFrameComplete(0)) {
//         manager.advance(manager.getFrameInput(0));
//     }
//
//     return 0;
// }
```

### 8.3 Lua — 帧同步主循环实现

```lua
-- lockstep_loop.lua — 帧同步客户端主循环
-- 在 Lua 游戏引擎 (如 Skynet/ET 框架) 中集成

local LockstepLoop = {}
LockstepLoop.__index = LockstepLoop

-- ─── 常量 ────────────────────────────────────────────
local LOGIC_FPS      = 15         -- 逻辑帧率
local FRAME_MS       = 1000 / 15  -- 每帧毫秒数 (66.67ms)
local BUFFER_FRAMES  = 3          -- 提前缓冲帧数

-- ─── 构造函数 ────────────────────────────────────────
function LockstepLoop.new(logic_tick_fn, render_fn)
    local self = setmetatable({}, LockstepLoop)
    self.current_frame    = 0
    self.accumulator      = 0.0
    self.last_time        = os.clock()

    -- 帧数据缓冲: frameNum → { inputs = {...}, complete = bool }
    self.frame_buffer     = {}

    -- 本地输入队列: 在 Bucket 内收集
    self.local_input_queue = {}

    -- 回调
    self.logic_tick_fn = logic_tick_fn  -- function(frameNum, allInputs)
    self.render_fn     = render_fn      -- function(alpha) alpha∈[0,1) 插值因子

    -- 网络发送函数 (外部注入)
    self.send_input_fn = nil  -- function(frameNum, packedInput)

    -- 状态 Hash 缓存 (用于校验)
    self.state_checksums = {}

    return self
end

-- ─── 设置网络发送回调 ────────────────────────────────
function LockstepLoop:set_network_sender(fn)
    self.send_input_fn = fn
end

-- ─── 本地输入收集 (表现层调用，在渲染帧中) ───────────
-- 在同一个 Bucket 内，多次调用 queue_input 会合并
function LockstepLoop:queue_input(action_type, ...)
    table.insert(self.local_input_queue, {
        type = action_type,    -- "move", "attack", "skill"
        args = { ... },
        timestamp = os.clock()
    })
end

-- ─── 打包本地输入 ────────────────────────────────────
function LockstepLoop:pack_local_input()
    if #self.local_input_queue == 0 then
        return { type = "empty" }  -- 空操作
    end

    -- 策略: 取最后一个操作 (Last Wins)
    -- 也可以展开为操作列表 (操作队列策略)
    local last_input = self.local_input_queue[#self.local_input_queue]
    self.local_input_queue = {}  -- 清空队列
    return last_input
end

-- ─── 发送本地输入到服务器 ────────────────────────────
function LockstepLoop:send_input()
    local packed = self:pack_local_input()
    local target_frame = self.current_frame + BUFFER_FRAMES

    if self.send_input_fn then
        self.send_input_fn(target_frame, packed)
    end

    -- 本地也暂存一份 (服务器会广播回来确认)
    self.frame_buffer[target_frame] = self.frame_buffer[target_frame] or {}
    self.frame_buffer[target_frame].local_input = packed
end

-- ─── 接收服务器广播的帧数据 ──────────────────────────
-- 服务器发来: { frame = N, inputs = { [pid1] = {...}, [pid2] = {...} } }
function LockstepLoop:on_server_frame(frame_data)
    local frame = frame_data.frame
    self.frame_buffer[frame] = self.frame_buffer[frame] or {}
    self.frame_buffer[frame].server_data = frame_data
    self.frame_buffer[frame].complete = true
end

-- ─── 主循环 (每渲染帧调用) ───────────────────────────
function LockstepLoop:update()
    local now = os.clock()
    local delta = now - self.last_time
    self.last_time = now

    -- 防止螺旋死亡: 单帧最多模拟 4 个逻辑帧
    local MAX_FRAMES_PER_RENDER = 4
    local frames_simulated = 0

    self.accumulator = self.accumulator + delta

    while self.accumulator >= (FRAME_MS / 1000.0)
        and frames_simulated < MAX_FRAMES_PER_RENDER
    do
        -- 检查下一帧是否准备好
        local next_frame = self.current_frame + 1
        local buf = self.frame_buffer[next_frame]

        if buf and buf.complete then
            -- 执行逻辑帧
            local server_data = buf.server_data
            if self.logic_tick_fn then
                -- server_data.inputs 包含所有玩家的输入
                self.logic_tick_fn(next_frame, server_data.inputs)
            end

            -- 计算状态 Hash (用于防作弊校验)
            self:compute_and_store_checksum(next_frame)

            -- 清理已消费的帧数据
            self.frame_buffer[next_frame] = nil

            self.current_frame = next_frame
            frames_simulated = frames_simulated + 1
        else
            -- 帧未就绪: 等待 (跳过本次逻辑更新)
            -- 注意: 在 Optimistic Lockstep 中这里不会等待，
            -- 而是服务器已用空操作填充
            break
        end

        self.accumulator = self.accumulator - (FRAME_MS / 1000.0)
    end

    -- 发送本地输入 (每渲染帧都可能更新预发送的帧)
    self:send_input()

    -- 渲染插值
    local alpha = self.accumulator / (FRAME_MS / 1000.0)
    alpha = math.min(alpha, 1.0)  -- 安全钳位

    if self.render_fn then
        self.render_fn(alpha)
    end
end

-- ─── 状态校验 ────────────────────────────────────────
function LockstepLoop:compute_and_store_checksum(frame)
    -- 简化: 在实际项目中需要序列化整个游戏状态
    -- 这里只演示概念
    local checksum = 0
    -- checksum = self.game_state:compute_hash()
    self.state_checksums[frame] = checksum
end

function LockstepLoop:get_checksum(frame)
    return self.state_checksums[frame]
end

-- ─── 断线重连: 快进追赶 ──────────────────────────────
function LockstepLoop:fast_forward(history_inputs, target_frame)
    print(string.format(
        "[重连] 快进追赶: 当前帧=%d → 目标帧=%d (共%d帧)",
        self.current_frame, target_frame,
        target_frame - self.current_frame
    ))

    local start_clock = os.clock()
    local processed = 0

    -- 以最快速度执行所有历史帧 (跳过渲染)
    for frame = self.current_frame + 1, target_frame do
        local inputs = history_inputs[frame]
        if inputs and self.logic_tick_fn then
            self.logic_tick_fn(frame, inputs)
            processed = processed + 1
        else
            print(string.format("[重连] 警告: 帧%d缺少输入数据", frame))
        end
    end

    self.current_frame = target_frame
    self.accumulator = 0

    local elapsed = os.clock() - start_clock
    print(string.format(
        "[重连] 追赶完成: %d帧 / %.2f秒 = %.0f帧/秒",
        processed, elapsed, processed / elapsed
    ))
end

-- ─── 导出 ────────────────────────────────────────────
return LockstepLoop


--[[
    ─── 使用示例 ──────────────────────────────────────

    local LockstepLoop = require("lockstep_loop")

    -- 游戏状态 (确定性)
    local game_state = {
        players = {
            { x = 0, y = 0, hp = 100 },
            { x = 10, y = 10, hp = 100 }
        }
    }

    -- 逻辑 Tick: 处理所有玩家的输入
    local function on_logic_tick(frame_num, all_inputs)
        for pid, input in pairs(all_inputs) do
            local player = game_state.players[pid + 1]
            if input.type == "move" then
                player.x = input.args[1]
                player.y = input.args[2]
            elseif input.type == "attack" then
                local other = game_state.players[2 - pid]  -- 另一玩家
                other.hp = other.hp - 10
            end
        end
    end

    -- 渲染
    local function on_render(alpha)
        -- 用 alpha 在前后两个逻辑帧之间插值
        -- render_entities(game_state.players, alpha)
    end

    -- 初始化循环
    local loop = LockstepLoop.new(on_logic_tick, on_render)

    -- 注入网络发送
    loop:set_network_sender(function(frame, input)
        -- udp_socket:send(serialize({frame = frame, input = input}))
    end)

    -- 游戏主循环 (每渲染帧一次)
    while game_running do
        -- 处理输入 (由上层输入系统驱动)
        -- if move_pressed then
        --     loop:queue_input("move", target_x, target_y)
        -- end

        -- 处理网络消息
        -- while udp_socket:has_message() do
        --     local data = udp_socket:receive()
        --     loop:on_server_frame(deserialize(data))
        -- end

        loop:update()
    end

--]]
```

---

## 9. 练习

### 练习 1: 基础 — 补全模拟器（30min）

基于 8.1 节的 C# 模拟器，做出以下修改：

1. **增加第3名玩家** (Player 2)，修改 PlayerScript 并给 P2 添加操作序列
2. **实现输入合并的确定顺序**：确保三个玩家在构造 `inputs[]` 时总是按 PlayerId 升序排列（否则 desync）
3. **加入伤害公式**：攻击伤害 = 基础攻击力(15) + 距离加成(越近伤害越高)。在两个 GameState 上验证计算结果一致
4. **打印每个 Turn 结束后的状态 Hash**（把 HP 和 Position 的字节 XOR 起来），观察两个 GameState 每帧 Hash 是否相等

要求：如果 Hash 不一致，程序应立即停止并报告哪个 Turn 发生了 desync。

### 练习 2: 进阶 — 实现 Bucket 机制（45min）

用任意语言实现一个 Bucket 调度器：

1. **输入**：模拟一个以 60Hz 频率产生的玩家操作流（随机生成 move/attack/idle）
2. **Bucket**：每 4 个操作合并为一个逻辑帧的输入（Last Wins 策略）
3. **输出**：打印每个 Bucket 内收集到的操作，以及最终打包的输入
4. **边界处理**：如果 60fps 和 15fps 不同步（例如第 3 帧只有 3 个操作），如何处理？

扩展：实现操作队列策略（保留 Bucket 内所有操作）与 Last Wins 策略的对比。

### 练习 3: 挑战 — 网络抖动模拟与帧缓冲区调优（60min）

基于 8.1 的模拟器，加入真实的网络模拟：

1. **延迟分布**：模拟 50~200ms 的随机延迟 + 5% 丢包率
2. **帧缓冲区**：客户端提前发送未来 N 帧的输入（N=2,3,4,5 分别测试）
3. **测量指标**：
   - 有效帧率（实际每秒执行的逻辑帧数）
   - 帧等待率（因为缺输入而等待的帧占比）
   - 输入丢弃率（超时而被空操作替代的输入占比）
4. **分析**：绘制 N 从 1 到 5 的三项指标折线图，找出最优的缓冲区大小，并解释为什么不是越大越好

---

## 10. 扩展阅读

### 必读文章
- **Gaffer On Games — Deterministic Lockstep**：帧同步的祖师爷级别文章，本文大量借鉴其论述框架
  https://gafferongames.com/post/deterministic_lockstep/
- **Gaffer On Games — Floating Point Determinism**：浮点数确定性问题的深入讨论
  https://gafferongames.com/post/floating_point_determinism/

### 中文深度文章
- **腾讯云: 从王者荣耀聊聊游戏的帧同步**：王者荣耀帧同步方案的公开分析
  https://cloud.tencent.com/developer/article/2479003
- **基于帧同步的游戏框架说明**：实际项目的帧同步架构分享（含 BattleServer 设计）
  https://cloud.tencent.com/developer/article/2147386
- **帧同步游戏开发基础指南**（腾讯）：入门级的帧同步概念与实现
  https://developer.cloud.tencent.com/article/1050868

### 开源参考
- **UnityLockstep (GitHub: Kirito9910)**：Unity C# 实现的完整帧同步框架
- **deterministic-lockstep-demo (GitHub: pietrobassi)**：C++ 确定性锁步演示
- **NKGMobaBasedOnET (GitHub: wqaetly)**：基于 ET 框架的 MOBA 帧同步实现

### 相关教程
- 本计划下一节：**06 - 确定性游戏逻辑：定点数与跨平台一致性**
- 本计划第 12 节：**帧同步进阶：快照校验、预测回滚与反外挂**

---

## 常见陷阱

### 陷阱 1: 把逻辑帧和渲染帧混为一谈

**错误**：在 `Update()` 里直接执行帧同步逻辑，然后用 `Time.deltaTime` 作为 dt 参数。

**为什么错**：渲染帧率是变化的（30~120fps 不定），逻辑帧必须是固定的（如 15fps）。混用会导致不同客户端同一 Turn 内执行了不同次数的逻辑更新。

**正确做法**：逻辑层使用固定时间步长（FixedUpdate 风格），从网络层接收 Turn 数据作为驱动信号，而非用渲染帧时间。

### 陷阱 2: 使用语言/引擎内置的浮点运算做逻辑计算

**错误**：`Vector3.Distance()` 或 `std::sqrt()` 直接用在逻辑层。

**为什么错**：不同平台/编译器的浮点实现可能差几个 ULP（最低有效位），这足以导致碰撞检测、物理积分的分歧。蝴蝶效应下，1 个 ULP 的差异在 1000 帧后可能造成完全不同的游戏结果。

**正确做法**：逻辑层使用定点数数学库。所有涉及"决策"的计算（移动、碰撞、伤害）必须用定点数。

### 陷阱 3: 使用非确定性容器迭代

**错误**：
```csharp
// C# Dictionary 的迭代顺序不保证
foreach (var kv in myDictionary) {
    Process(kv.Value); // 不同机器上顺序不同！
}
```

**为什么错**：`Dictionary<K,V>`、`HashSet<T>` 等哈希容器的迭代顺序依赖哈希值和内部桶分配，不同运行时/不同插入顺序会产生不同的遍历顺序。

**正确做法**：逻辑层使用有序容器（`SortedDictionary`、`List` 排序后迭代），或在迭代前对键进行排序。

### 陷阱 4: 忘记处理空操作

**错误**：当某玩家没有操作时，不在输入集合中为该玩家添加条目。

**为什么错**：帧同步要求 $I_n$ 对所有客户端完全一致。如果一个客户端认为"P3 没有输入"意味着 P3 啥都不做，另一个客户端完全没收到 P3 的数据而不知道该如何处理——结果必然 desync。

**正确做法**：显式定义空操作（Empty/NOP），并在每个 Turn 为所有玩家显式设置输入（含空操作）。

### 陷阱 5: 服务器时间 ≠ 客户端时间

**错误**：客户端用本地 `DateTime.Now` 或 `os.clock()` 来判断当前逻辑帧号。

**为什么错**：不同设备的时钟可能偏差数秒。用本地时钟推导帧号会导致不同客户端给同一输入打上不同的帧号标签。

**正确做法**：帧号由服务器分配和广播。客户端发送输入时使用相对帧号（当前帧 + BUFFER_FRAMES），服务器进行帧号映射。

### 陷阱 6: 断线重连时丢弃了随机种子状态

**错误**：断线重连时执行快进追赶，但随机数生成器的状态没有被正确恢复。

**为什么错**：如果随机种子在 1250 帧被播种，而 PRNG 在 1250~1800 帧之间被调用了 N 次——重连快进时必须正好调用 N 次，不多不少。如果由于快进代码中某个逻辑分支不同而调用了不同次数，后续所有"随机"结果都将不同。

**正确做法**：逻辑帧中所有随机操作必须基于帧号派生的确定性种子（如 `seed = hash(baseSeed, frameNumber, eventIndex)`），而非依赖 PRNG 的调用次数。
