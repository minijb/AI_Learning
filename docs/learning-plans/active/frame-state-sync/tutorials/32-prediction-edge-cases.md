# 预测系统的边缘情况与陷阱

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [14-客户端预测](14-client-side-prediction.md), [15-服务端和解](15-server-reconciliation.md), [17-延迟补偿](17-lag-compensation.md)

---

## 1. 概念讲解

### 1.1 为什么预测系统会出错？

在教程 14-17 中，我们学习了客户端预测、服务端和解与延迟补偿这三件套。从纸面上看，一切都设计得完美：客户端预测 → 服务端确认 → 不一致时回滚 → 平滑修正。这个流程在**理论上**是无懈可击的。

但任何上线过网络同步系统的人都会告诉你：理论 ≠ 实践。

```
开发环境（低延迟局域网，RTT < 5ms）:
  预测错误率: ~0.01%
  回滚频率: 几乎为零
  测试结论: "一切正常！"

生产环境（真实网络，RTT 50-200ms，抖动 ±30ms，丢包 1-3%）:
  预测错误率: ~5-15%  （取决于游戏类型）
  回滚频率: 每秒数十次到数百次
  测试结论: "角色瞬移、子弹消失、碰撞检测完全错乱……"
```

这就是本节的核心命题：**即使预测系统的算法设计正确，在工程实现层面仍然有大量边缘情况会破坏系统的正确性**。

这些边缘情况有几个共同点：

| 特征 | 说明 |
|------|------|
| **开发环境不可见** | 在 LAN 或本地回环中，延迟为零，丢包为零，量化误差为零——这些 bug 的触发条件不存在 |
| **概率性触发** | 不是每次都会发生，而是依赖网络时序的精确排列——某个包恰好先于另一个包到达、某个 tick 恰好触发了一次重发 |
| **累积性恶化** | 单个事件的偏差很小（可能只有 0.001 米），但每秒数千次累积后，偏差可达数米 |
| **难以复现** | 需要特定的网络条件组合才能触发。QA 说"偶现"，程序说"我这测不出来" |

**面试时能否讲清楚边缘情况 = 你是否真正上线过系统。** 面试官问"你们项目遇到过什么预测相关的 bug"，就是在考察这一点。如果你只能讲"我们做了客户端预测和服务端和解"，那是看过文档的水平；如果你能讲"我们遇到过量化漂移导致 AI 寻路路径偏移，最终通过客户端侧也执行量化来解决"，那是真正 debug 过上线版本的工程师。

---

### 1.2 量化精度漂移 (Quantization Drift)

这是 Unity Netcode for Entities (N4E) 文档中特别强调的一个问题，也是所有使用状态量化的同步系统都会遇到的**无声累积误差**。

#### 问题描述

为了节省带宽，服务端通常会对浮点数状态进行**量化压缩**后再发送给客户端：

```
原始值 (float32, 4 bytes):  Position.x = 123.456789f
量化值 (int16,  2 bytes):   quantized   = Quantize(123.456789f)
                            = (int)(123.456789f / 0.01f)
                            = 12345
                           （精度损失: ±0.005m）

反量化 (float32, 4 bytes):  reconstructed = 12345 * 0.01f
                                        = 123.45f
                           （与原始值的误差: 0.006789m）
```

这个误差在单次传输中微不足道（< 1cm）。问题出在**回退重模拟**环节：

```
服务器端:
  Tick 100: 权威位置 = 10.000f  （量化后发给客户端 = 10.00f）
  Tick 101: 权威位置 = 10.050f  （量化后发给客户端 = 10.05f）
  Tick 102: 权威位置 = 10.100f  （量化后发给客户端 = 10.10f）

客户端:
  收到 Tick 100 快照: 权威位置 = 10.00f  ← 反量化后的值
  本地预测 Tick 101: 预测位置 = 10.00 + 0.05 = 10.05f    （基于反量化值计算）
  本地预测 Tick 102: 预测位置 = 10.05 + 0.05 = 10.10f

  收到 Tick 101 快照: 权威位置 = 10.05f  （又是反量化值）
  比对: 预测 10.05f vs 权威 10.05f → 一致！无需回滚。

  收到 Tick 102 快照: 权威位置 = 10.10f
  比对: 预测 10.10f vs 权威 10.10f → 一致！

看起来没问题？等等……
```

**问题出在当某个 tick 的权威状态触发了逻辑变化时**：

```
服务器端（使用完整精度）:
  Tick 100: 位置 = 10.000f, 速度 = 0
  Tick 101: 受外力影响，位置 = 10.048f  （量化后 = 10.05f）
  Tick 102: 位置 = 10.097f  （量化后 = 10.10f）
  Tick 103: 位置 = 10.145f  ← 服务器碰撞检测: 10.145 >= 10.10（墙壁位置）→ 碰撞！

客户端收到 Tick 103 快照后回滚重模拟:
  Tick 101 起点: 10.05f  （反量化值 ≠ 服务器的 10.048f）
  Tick 102: 10.10f        （反量化值 ≠ 服务器的 10.097f）
  Tick 103: 10.15f        （基于反量化起点推导）
            ↑ 客户端判定: 10.15 >= 10.10 → 碰撞！
              服务器判定: 10.145 >= 10.10 → 碰撞！

              一致？可惜，让我们继续：
  Tick 104: 服务器用原始值 10.145 继续模拟 → 反弹方向 (1, 0, 0)
            客户端用 10.15 继续模拟 → 反弹方向 (1, 0, 0)
            相同的反弹方向，不同的起始位置 → 累积偏差开始

  Tick 105: 服务器位置 = 10.145 + vel×dt = ...
            客户端位置 = 10.15  + vel×dt = ...
            差距 = 0.005m → 仍在量化误差范围内

  Tick 150 (1秒后): 差距 = 0.35m → 回滚触发！
  Tick 300 (3秒后): 差距 = 1.2m  → 角色在客户端和服务器上走了截然不同的路径！
```

**核心机制**：每次服务端和解回滚时，客户端从反量化的起点重模拟，而服务器一直使用完整精度。这个细微的起点差异被模拟逻辑（尤其是碰撞、摩擦力、加速度等具有**混沌敏感性**的物理步进）逐帧放大，形成"蝴蝶效应"。

#### 后果

1. **寻路/导航路径偏移**：AI 或玩家角色在同一张地图上走出不同的路径。客户端看到角色穿过了门，服务器上角色撞了墙。
2. **碰撞检测错误**：客户端判定子弹命中，服务器判定擦肩而过（或反之）。
3. **不可预测的回滚雪崩**：偏差累积到一定程度后触发回滚，回滚后使用新的反量化值 → 又产生偏差 → 再次回滚 → 循环……玩家看到角色在"颤抖"。
4. **竞速游戏（最严重）**：赛车游戏的圈速记录依赖精确位置判定。量化漂移可能导致客户端认为通过了检查点而服务器不认。

#### 解决方案

| 方案 | 做法 | 代价 | 适用场景 |
|------|------|------|---------|
| **客户端也量化** | 客户端在每次收到权威快照后，**先把反量化值写回自己当前状态，再开始重模拟**——确保模拟起点和服务端"看到"的值一致 | 客户端精度降低，但一致性保障 | 推荐：大多数需要量化的游戏 |
| **降低量化精度** | 使用更高位数的量化（如 int32 替代 int16），或缩小量化范围以提高分辨率 | 带宽增加 | 高精度需求（竞速、物理模拟重的游戏） |
| **完全禁用量化** | 关键状态字段不做量化，用完整 float 传输 | 带宽显著增加 | 仅对少量关键字段（如玩家主角位置） |
| **误差阈值兜底** | 无论量化精度如何，在和解时加入硬阈值：误差 > 某个值直接硬修正，阻断蝴蝶效应 | 视觉上可能偶尔出现瞬移 | 作为所有方案的兜底保护 |

**最重要的一个认知**：

> 量化漂移不是 bug——它是使用量化压缩必然产生的系统性偏差。不存在"消除"它的方案，只能"控制"它。你必须在一致性（客户端和服务端模拟一致）和带宽（压缩率）之间做权衡。

---

### 1.3 部分快照交互问题 (Partial Snapshot Interactions)

这是 Unity Netcode for Entities 中另一个深度文档问题。它在帧同步中不存在（帧同步中每个 tick 的所有实体状态是原子性的——要么全有要么全无），但在状态同步中是一个顽固的工程难题。

#### 问题描述

在状态同步中，服务端每个 tick 生成一个快照（snapshot），包含该 tick 所有实体的状态。但这个快照在网络上传输时，**TCP/UDP 的分包机制**可能导致同一个 tick 的快照被拆成多个网络包：

```
服务端 Tick 100 快照:
  [Ghost A: position, velocity, hp]
  [Ghost B: position, velocity, hp]
  [Ghost C: position, velocity, hp]
  （总计 12KB，超过 MTU 1500 bytes）

网络传输:
  包 1 (到达): Ghost A + Ghost B 的完整数据   → 客户端收到
  包 2 (延迟): Ghost C 的完整数据             → 还未到达！

客户端 Tick 100 回退时:
  只有 Ghost A 和 Ghost B 收到了快照 → 回退到 Tick 100 的权威状态
  Ghost C 还没有收到快照 → 仍然停留在 Tick 105（未来）的预测状态！

结果:
  Ghost A (回退到 T100) 与 Ghost C (停留在 T105) 交互
  → 时间不一致的碰撞检测！
```

```
时间线（客户端视角）:
Tick:    ...99   100   101   102   103   104   105(当前)
                 │     │     │     │     │     │
Ghost A:         权威100    预测101 预测102 预测103 预测104 预测105
                 │     │     │     │     │     │
                 ↓ 包1到达, 回退！
Ghost A':        权威100 ── 重预测101 ── 重预测102 ── ... ── 重预测105

Ghost C:                                   预测103 预测104 预测105
                                            ↑ 包2还未到，仍停留在这里！

交互:
  重预测后的 Ghost A'@105  碰到  Ghost C 的预测状态@105
  → 但在服务器上，Ghost A 和 Ghost C 在 Tick 105 的真实状态完全不同！
```

#### 为什么会发生？

根本原因是状态同步的**每个实体独立同步**特性。不像帧同步中的"一个 tick 的所有输入作为一个整体到达"，状态同步中每个 Ghost（实体）的快照数据是独立到达的。当快照足够大（包含数百个实体），必须分包传输，而每个包的到达时间和顺序都是不确定的。

以下条件组合时会触发：
1. **大世界/多实体**：单个 tick 的快照数据超过 MTU（~1200 bytes），必须分包
2. **网络抖动**：分包到达间隔 > 一个服务端 tick 的时间
3. **客户端 Tick 频率高**：回退检测在包完全到达之前就触发了

#### 后果

1. **碰撞检测错误**：历史状态和未来状态的实体碰撞到一起，产生服务器上不可能发生的事件
2. **实体穿模**：回退后的实体在服务器上本应被另一个实体阻挡，但在客户端上该另一个实体还在"未来"→ 穿过去了
3. **连锁反应**：碰撞错误 → 位置错误 → 和解触发 → 更多回退 → 更多部分快照……

#### 缓解方案

**方案一：Ghost Group / 快照原子性保证**

让服务端确保同一个 tick 的所有 Ghost 数据**作为一个整体交付**给客户端。

```
// 服务端发送快照时，不按 Ghost 逐个发送，
// 而是标记"这批 Ghost 属于 Tick N"，
// 客户端只在收到全部 Ghost 后才应用该 Tick 的快照

struct SnapshotHeader {
    uint32_t tick;
    uint16_t totalGhostCount;   // 这个 Tick 总共有多少 Ghost
    uint16_t ghostCountInThisPacket; // 这个包包含多少个
    uint32_t sequenceNumber;    // 分包序列号（0, 1, 2...）
};
```

客户端维护一个"分包重组缓冲区"，只有当某个 tick 的所有分包都收齐后，才对该 tick 的所有 Ghost 执行回退。未收齐的 tick 不触发回退。

代价：增加延迟。客户端必须等最慢的那个包，而不是收到一个就用一个。

**方案二：重要性缩放 (Importance Scaling)**

并非所有 Ghost 都同等重要。对于不同的 Ghost，可以有不同的处理策略：

- **高优先级 Ghost**（玩家、Boss、关键道具）：放在快照的第一个包中，确保最先到达
- **低优先级 Ghost**（远处小怪、装饰物）：放在后面的包中，允许延迟到达
- **回退隔离**：回退只应用于"已经完整收到该 tick 快照"的 Ghost 组

```csharp
// Ghost 分组示例
enum GhostImportance {
    Critical = 0,   // 玩家主角、Boss — 第一个包，保证原子性
    High     = 1,   // 队友、重要 NPC — 第二个包
    Normal   = 2,   // 小怪、弹道 — 第三批
    Low      = 3,   // 装饰物、特效 — 最后，可延迟可达秒级
}
```

**方案三：Client Anticipation（客户端预判修正）**

对于还没收到快照的 Ghost，不保持其"未来"状态，而是用**上一次已确认的快照 + 外推**来估计其"当前"状态，使其和已回退的 Ghost 处于相同的时间参考系。

```
Ghost C 还没有 Tick 100 的快照:
  不使用预测的 Tick 105 状态
  改用: Tick 95(最后确认的权威状态) + 10个tick的线性外推
  → 虽然精度不高，但至少和回退后的 Ghost A 处于同一时间参考系
```

**方案四：物理层隔离**

在物理引擎层面，**禁止不同"时间"的实体之间进行碰撞响应**：

```csharp
// 碰撞回调中检查
void OnCollisionEnter(Ghost a, Ghost b) {
    if (a.LastAppliedTick != b.LastAppliedTick) {
        // 不同 tick 的实体碰撞 → 忽略碰撞响应
        // （只记录，不产生物理效果）
        LogCrossTickCollision(a, b);
        return;
    }
    // 正常碰撞处理...
}
```

#### 实战建议

在大多数实际项目中，推荐组合使用：
- **Ghost Group**（方案一）作为基础：确保关键实体在同一 tick 的原子性
- **重要性缩放**（方案二）减少等待时间
- **物理层隔离**（方案四）作为最后的安全网

---

### 1.4 预测生成物冲突 (Predicted Spawn Conflicts)

这是预测系统中最容易被忽视但又最容易导致严重 bug 的问题。

#### 问题描述

在客户端预测中，玩家可以触发**生成新实体**的操作——开枪产生子弹、释放技能产生火球、投掷手雷产生爆炸物。这些新生成的实体称为 **预测生成物 (Predicted Spawns)**。

预测生成物有一个特殊性质：**它们没有服务端快照**。它们是在客户端"凭空"创造出来的，服务端还不知道它们的存在（直到生成消息到达）。

```
客户端 Tick 100:
  玩家按下射击键 → 立即创建"子弹实体"（预测生成物）
  子弹实体在本地存在，但服务端的 Tick 100 快照中还没有它

客户端 Tick 102:
  收到服务端 Tick 100 的快照 → 触发回退
  回退时: Ghost A, B, C 都回退到 Tick 100 的权威状态
          但"子弹实体"怎么办?
          它是在 Tick 100 创建的，但 Tick 100 的权威快照中没有它！
```

**矛盾**：回退操作会重置世界状态到某个过去的 tick，但预测生成物是在该 tick 之后（或恰好同一 tick）创建的，它在那个"过去的时间点"上不存在。于是：

```
回退前:
  Tick 100: 玩家创建子弹（预测），位置 (100, 0, 0)
  Tick 101: 子弹飞到 (105, 0, 0)
  Tick 102: 回退触发！其他实体回到 Tick 100 状态
            但子弹？停留在 (105, 0, 0) ← 冻结在"未来"位置

结果:
  敌人在 Tick 100 的权威位置是 (103, 0, 0)
  子弹在 (105, 0, 0) → 子弹"越过了"敌人
  发生了碰撞吗？取决于代码：如果在 Tick 100 时做碰撞检测，子弹还没被创建；
            如果在 Tick 102 时做碰撞检测，子弹已经飞过了敌人……
```

#### 核心困境

- 如果回退时**删除**预测生成物 → 玩家开了枪但子弹消失了（体验极差）
- 如果回退时**保留**预测生成物 → 它停留在"未来"位置，和回退后的其他实体产生不一致交互
- 如果回退时**也回退**预测生成物 → 回退到它被创建的那个 tick……但它在那个 tick 还不存在！

#### 解决方案

**Unity Netcode for Entities 的方案：Allow Rollback to Spawn Tick**

核心思想：允许回退系统将**整个模拟**（包括预测生成物的生命周期）回退到该生成物被创建的那个 tick。

```
正常回退（到 Tick 100）:
  Ghost A 回到 Tick 100 状态
  Ghost B 回到 Tick 100 状态
  预测子弹：回退到 Tick 100 的状态 → 也就是它被创建的那个 tick
  → 状态: "刚被创建，位置在枪口"

然后重模拟 Tick 100-102:
  Tick 100: 创建子弹（重放预测生成逻辑）
  Tick 101: 子弹飞到 (105, 0, 0)
  Tick 102: 子弹飞到 (110, 0, 0)

关键是: 重模拟时的世界状态变了（因为 Ghost A 和 Ghost B 回退到了正确的权威位置）
→ 子弹的飞行路径可能与第一次预测时不同
→ 但至少子弹存在于"正确"的位置上，碰撞检测是正确的
```

实现需要：
1. **预测生成物注册表**：跟踪所有客户端预测创建的实体及其创建时的 tick
2. **生成物回退支持**：回退系统必须能回退预测生成物的状态（位置、速度、生命周期等）
3. **重模拟时的生成重放**：在重模拟过程中，当模拟到达生成物的创建 tick 时，重新执行生成逻辑

**注意**：预测生成物在被服务端确认之前，在服务端是"不存在"的。这意味着一件很重要的事：

> 预测生成物在服务端确认之前，**不能对权威状态产生任何影响**。如果子弹在客户端预测"杀死了"一个敌人，但服务端还没生成这颗子弹 → 客户端看到的死亡是假的，和解时会复活。

这引出一个用户体​​验设计原则：对于预测生成物的"命中"效果，**延迟关键帧**。先播放前摇/飞行动画，等服务端确认后才播放命中/死亡效果。

#### 备选方案对比

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **Allow Rollback to Spawn** | 预测生成物参与回退和重模拟 | 正确性最高 | 实现复杂度高，需要回退系统支持 |
| **冻结生成物** | 回退时预测生成物保持当前位置不动 | 实现简单 | 碰撞检测错误，生成物位置不准确 |
| **删除并重新预测** | 回退时删除当前生成物，重新预测创建 | 简单，语义干净 | 视觉闪烁（子弹瞬移），玩家困惑 |
| **延迟生成** | 不立即创建预测生成物，等 2-3 帧服务端确认后再创建 | 没有回退问题 | 射击延迟，违背客户端预测的初衷 |

---

### 1.5 输入重复应用 (Double Input Application)

这是客户端预测实现中最常见也最隐蔽的一类 bug。

#### 问题描述

同一个玩家输入被应用到模拟中**两次**，导致角色移动距离翻倍、两次射击、两次跳跃等。

#### 典型场景

**场景 A：序列号回绕**

```csharp
// 错误：使用 uint8 做输入序列号，256 帧后回绕到 0
uint8 inputSeq = 0;  // 范围 0-255

// 当服务器返回 lastProcessedSeq = 250
// 客户端清理已确认输入: seq <= 250 全部删除
// 但服务端可能还没处理 seq 251-255 的输入
// 而客户端已经发出了 seq 0, 1, 2... 的新输入

// 服务端收到 seq 0 → 认为这是"旧"的 seq 0，已经处理过了 → 丢弃！
// 服务端收到 seq 255 → 认为这是"还没见过的"新输入 → 接受！

// 但如果服务端用环形缓冲区存储"最近 64 个已处理序列号"
// seq 255 和"真正的旧 seq 255"（65个tick前）对不上 → 漏处理
```

**正确做法**：使用足够大的序列号类型（uint32 或 uint64），避免在生产环境中回绕。

**场景 B：重连时输入重放**

```
客户端断开连接 → 重连成功
→ 客户端不知道哪些输入已经被服务端处理了
→ 客户端"乐观地"重新发送最近 60 帧的所有输入
→ 其中 30 帧服务端已经处理过 → 每帧输入被应用两次！
```

**场景 C：回退重模拟 + 新输入竞态**

```
Tick 100: 输入 I100 (按下空格键)
Tick 101: 收到快照，触发回退到 Tick 99
Tick 101 重模拟: 应用 I100 → 跳跃
Tick 101 正常帧处理: 从输入队列取当前输入 → 又是 I100（因为输入还没被消费） → 再次跳跃！
```

#### 根本原因

输入不是幂等的。移动输入（如"向右走 1 单位"）被应用两次 = 走了 2 单位。跳跃输入被应用两次 = 二段跳 bug。

#### 解决方案：输入幂等性保证

**方案 1：基于序列号的去重**

```csharp
// 每个输入携带全局唯一的序列号
// 服务端/客户端维护"已处理输入序列号集合"
// 处理前检查：如果已处理过这个序列号 → 跳过

class InputProcessor {
    HashSet<uint> _processedInputs = new();
    uint _maxProcessedSeq = 0;

    public bool ShouldProcess(uint seq) {
        // 已明确确认处理过
        if (_processedInputs.Contains(seq)) return false;
        // 该序列号小于等于最大已处理序列号 → 肯定处理过了
        if (seq <= _maxProcessedSeq) return false;
        return true;
    }

    public void MarkProcessed(uint seq) {
        _processedInputs.Add(seq);
        if (seq > _maxProcessedSeq) _maxProcessedSeq = seq;

        // 清理旧记录（保留最近 1024 条）
        while (_processedInputs.Count > 1024) {
            uint min = _processedInputs.Min();
            _processedInputs.Remove(min);
        }
    }
}
```

**方案 2：基于 Tick 的输入分区**

服务端每个 tick 维护一个"该 tick 已经处理过的玩家"集合。同一个 tick 不会重复处理同一个玩家的输入：

```csharp
Dictionary<uint, HashSet<int>> _tickProcessedPlayers;

void ProcessTick(uint tick) {
    _tickProcessedPlayers[tick] = new HashSet<int>();
}

void ProcessInput(uint tick, int playerId, Input input) {
    // 检查该 tick 是否已处理该玩家
    if (_tickProcessedPlayers[tick].Contains(playerId)) {
        LogWarning($"Duplicate input: player {playerId} at tick {tick}");
        return;
    }
    _tickProcessedPlayers[tick].Add(playerId);

    // 正常处理输入...
}
```

**方案 3：重连握手协议**

重连时，客户端不盲目重放输入。而是：

```
1. 客户端发送 ReconnectRequest { lastReceivedServerTick }
2. 服务端回复 ReconnectResponse {
       lastProcessedInputSeq,   // 服务端最后确认的客户端输入序列号
       currentWorldState         // 当前世界状态快照
   }
3. 客户端收到后：
   - 丢弃所有 seq <= lastProcessedInputSeq 的本地输入
   - 仅发送 seq > lastProcessedInputSeq 的输入
   - 世界状态设置为服务端发来的权威状态
```

---

### 1.6 时间步不同步 (Timestep Mismatch)

这是网络同步中最基础也最容易忽视的问题——**客户端和服务器的"一帧"不是同一长度**。

#### 问题描述

```
服务器（固定步长 deltaTime = 1/60 = 16.666...ms）:
  Tick N:   pos += velocity * (1/60)
  Tick N+1: pos += velocity * (1/60)

客户端（可变帧率，当前 deltaTime = 17.2ms）:
  Frame F:  pos += velocity * (17.2/1000) = velocity * 0.0172

服务器 3 个 tick = 3/60 = 0.05s
客户端 3 帧     = 3 × 17.2ms = 0.0516s

客户端多走了 0.0016s → 累积 1 分钟后偏差可达数米
```

更糟糕的是，浮点数 `deltaTime` 本身就有精度问题：

```csharp
// C# 中
float dt = 1.0f / 60.0f;
// dt == 0.01666667f（不是精确的 1/60）

// 累积 3600 个 Tick（60fps × 60s）:
float totalServer = 3600 * (1.0/60.0);    // = 59.999...f
float totalClient = 3600 * 0.01666667f;   // = 60.000012f
// 差异：0.000012 秒 → 在高速运动下可能是可见的位置偏差
```

#### 解决方案

**方案 1：固定步长 + dt 钳位**

```csharp
// 客户端使用与服务器完全相同的固定步长
const float FIXED_DT = 1.0f / 60.0f; // 16.666...ms

// 使用整数 tick 计数，而非累积 time 来推进模拟
int currentTick = 0;

void FixedUpdate() {
    // 不做 Time.fixedDeltaTime 的累积
    // 每次推进一个固定的逻辑 tick
    Simulate(FIXED_DT);
    currentTick++;
}
```

**方案 2：基于 Tick 的时间而非 float 时间**

```csharp
// 错误做法：用 float 时间做比较
float nextEventTime = Time.time + cooldown;
if (Time.time >= nextEventTime) { ... } // 可能因浮点精度错过

// 正确做法：用整数 tick 做比较
uint cooldownTicks = 30; // 30 ticks = 0.5s @ 60Hz
uint nextEventTick = currentTick + cooldownTicks;
if (currentTick >= nextEventTick) { ... } // 精确的整数比较
```

**方案 3：服务端指定帧率**

服务端在握手时告知客户端期望的 tick rate：

```
// 握手协议中
ServerHello {
    tickRate: 60,       // Hz
    fixedDeltaTime: 16667,  // 微秒（避免浮点）
}
```

客户端将自己的逻辑步长设置为与服务器一致。

---

### 1.7 预测状态清理 (Predicted State Cleanup)

#### 问题描述

客户端预测系统中的实体生命周期管理是一个容易被忽略的问题。典型的 bug 场景：

```
1. 客户端创建了预测实体 E（如火球）
2. 火球飞行了 20 帧，击中墙壁后客户端将其销毁
3. 此时收到服务端快照，触发回退到 Tick 100
4. Tick 100 时火球还存在（它是在 Tick 105 才撞墙的）！
5. 回退系统尝试恢复火球的状态 → 但火球的 GameObject 已经被 Destroy 了
   → NullReferenceException 或僵尸实体
```

反向场景同样致命：

```
1. 服务端在 Tick 100 判定玩家死亡 → 发送快照给客户端
2. 客户端在收到快照前：玩家还活着，正在移动、射击
3. 客户端收到快照 → 触发回退
4. 回退系统发现"玩家在 Tick 100 应该已经死亡"
5. 但客户端侧的玩家实体上挂着大量预测状态：
   - 未确认的输入历史
   - 预测的技能特效
   - 预测的子弹实体
   - UI 上的预测 HP 显示
6. 回退时清理不到位 → 死亡后还在播放技能特效、子弹继续飞行、
   血条显示错误的数值
```

#### 解决方案

**方案 1：Ghost 生命周期事件**

Unity Netcode for Entities 中的方案：每个 Ghost（实体）都有明确定义的生命周期事件：

```csharp
enum GhostLifecycleEvent {
    Spawned,        // 实体刚出现在世界（或刚收到第一个快照）
    Despawned,      // 实体已从世界移除
    PreRollback,    // 即将执行回退
    PostRollback,   // 回退执行完毕
    Destroyed       // Ghost 组件即将被移除
}
```

客户端在收到这些事件时，**必须同步清理**关联的预测状态。

**方案 2：预测状态与 Ghost 生命周期的绑定**

```csharp
// 预测状态不独立存在，而是绑定到 Ghost 实例上
// 当 Ghost 被销毁时，其挂载的所有预测状态自动清理

class PredictedGhostEntity : MonoBehaviour {
    // 所有预测状态的引用
    private List<IPredictedState> _predictedStates;

    // 预测特效列表
    private List<PredictedEffect> _pendingEffects;

    // 未确认输入引用
    private Queue<InputCommand> _pendingCommands;

    void OnGhostDespawn() {
        // 清理所有预测状态
        foreach (var state in _predictedStates) {
            state.Cleanup();
        }
        _predictedStates.Clear();

        // 取消所有预测特效
        foreach (var fx in _pendingEffects) {
            if (fx.IsPredicted) {
                fx.Cancel();
            }
        }
        _pendingEffects.Clear();

        _pendingCommands.Clear();
    }
}
```

**方案 3：回退前状态快照**

在每次回退操作前，先保存当前预测状态的完整快照，回退完成后比对并清理"多余"的预测状态：

```csharp
void BeforeRollback() {
    _rollbackSnapshot = CapturePredictedState();
}

void AfterRollback() {
    var current = CapturePredictedState();

    // 找出在回退后"不应该存在"的预测状态
    var toRemove = _rollbackSnapshot.PredictedEntities
        .Where(e => !current.PredictedEntities.Contains(e));

    foreach (var entity in toRemove) {
        entity.CleanupAndDestroy();
    }
}
```

**方案 4：服务端权威的销毁确认**

客户端不主动销毁任何"预测生成"的实体。销毁必须由服务端确认：

```
1. 客户端判定"火球撞到墙了，应该销毁"
2. 客户端将火球标记为"待销毁"状态，播放消失动画，但不真正 Destroy
3. 服务端收到火球的命中消息 → 服务端也判定撞墙 → 发送"火球已销毁"快照
4. 客户端收到确认 → 正式 Destroy 火球的 Ghost
```

---

## 2. 代码示例

### 2.1 C#: QuantizationDriftDemo — 量化漂移模拟器

```csharp
// QuantizationDriftDemo.cs — 演示量化精度漂移的累积效应
// 运行方式：在 Unity 中挂载到任意 GameObject，在 Console 窗口观察输出
// 依赖: UnityEngine

using UnityEngine;
using System.Text;

namespace PredictionEdgeCases
{
    /// <summary>
    /// 量化漂移演示：模拟服务端和客户端在量化/非量化条件下的位置偏差累积。
    ///
    /// 场景：一个角色以恒定速度移动，每帧受微小的随机力（模拟网络不确定性）。
    /// 服务端使用完整 float 精度，客户端使用 int16 量化值。
    /// 观察双方位置在 N 帧后的偏差。
    /// </summary>
    public class QuantizationDriftDemo : MonoBehaviour
    {
        [Header("模拟参数")]
        [SerializeField] private float _moveSpeed = 5.0f;
        [SerializeField] private float _randomForceScale = 0.01f;
        [SerializeField] private int _totalTicks = 600; // 10秒 @ 60fps
        [SerializeField] private float _quantizationStep = 0.01f; // 1cm 精度

        [Header("缓解方案")]
        [SerializeField] private bool _clientAlsoQuantizes = true;

        // === 状态 ===
        private float _serverPosition;
        private float _serverVelocity;
        private float _clientPosition;
        private float _clientVelocity;
        private float _clientQuantizedPosition;
        private float _clientQuantizedVelocity;

        private int _tickCounter;
        private readonly StringBuilder _logBuilder = new StringBuilder();
        private float _maxDrift;

        void Start()
        {
            InitializeState();
            SimulateTicks();
            PrintResults();
        }

        void InitializeState()
        {
            _serverPosition = 0f;
            _serverVelocity = _moveSpeed;
            _clientPosition = 0f;
            _clientVelocity = _moveSpeed;
            _clientQuantizedPosition = 0f;
            _clientQuantizedVelocity = _moveSpeed;
            _tickCounter = 0;
            _maxDrift = 0f;
        }

        void SimulateTicks()
        {
            float dt = 1.0f / 60.0f;

            _logBuilder.AppendLine($"{"Tick",6} | {"ServerPos",10} | {"ClientPos",10} | {"Drift",10} | {"QuantDrift",12}");
            _logBuilder.AppendLine(new string('-', 65));

            for (int i = 0; i < _totalTicks; i++)
            {
                _tickCounter++;

                // === 服务器模拟（完整精度）===
                // 每 tick 受微小的随机力（模拟物理不确定性）
                float serverForce = Random.Range(-_randomForceScale, _randomForceScale);
                _serverVelocity += serverForce * dt;
                // 摩擦力衰减
                _serverVelocity *= 0.999f;
                _serverPosition += _serverVelocity * dt;

                // === 客户端模拟（不量化 / 普通模式）===
                // 使用相同的随机种子，但起点可能因为之前的量化而不同
                float clientForce = serverForce; // 假设随机是确定性的
                _clientVelocity += clientForce * dt;
                _clientVelocity *= 0.999f;
                _clientPosition += _clientVelocity * dt;

                // === 客户端模拟（量化模式）===
                _clientQuantizedVelocity += clientForce * dt;
                _clientQuantizedVelocity *= 0.999f;
                _clientQuantizedPosition += _clientQuantizedVelocity * dt;

                // 模拟每 30 个 tick 发生一次服务端和解（回退）
                if (i > 0 && i % 30 == 0)
                {
                    // 服务端发送"量化后"的位置
                    float serverQuantized = Quantize(_serverPosition, _quantizationStep);

                    // 客户端收到权威快照，发现不一致 → 触发回退
                    if (Mathf.Abs(_clientPosition - serverQuantized) > _quantizationStep * 0.5f)
                    {
                        // 不使用量化的客户端：用"反量化"值作为新起点
                        float unquantBaseline = Dequantize(Quantize(_serverPosition, _quantizationStep), _quantizationStep);
                        _clientPosition = unquantBaseline;
                        _clientVelocity = _serverVelocity; // 同时修正速度
                    }

                    // 如果开启"客户端也量化"：客户端在设定起点时也使用反量化值
                    if (_clientAlsoQuantizes)
                    {
                        _clientQuantizedPosition = Dequantize(
                            Quantize(_serverPosition, _quantizationStep),
                            _quantizationStep
                        );
                        _clientQuantizedVelocity = _serverVelocity;
                    }
                }

                // 每 60 tick 记录一次
                if (i % 60 == 0)
                {
                    float drift = _serverPosition - _clientPosition;
                    float quantDrift = _serverPosition - _clientQuantizedPosition;

                    _maxDrift = Mathf.Max(_maxDrift, Mathf.Abs(drift), Mathf.Abs(quantDrift));

                    _logBuilder.AppendLine(
                        $"{i,6} | {_serverPosition,10:F4} | {_clientPosition,10:F4} | {drift,10:F4} | {quantDrift,12:F4}"
                    );
                }
            }
        }

        void PrintResults()
        {
            Debug.Log(_logBuilder.ToString());
            Debug.Log($"<color=yellow>最大普通漂移: {_maxDrift:F4}m | 最终漂移: {(_serverPosition - _clientPosition):F4}m</color>");

            if (_clientAlsoQuantizes)
            {
                float finalQuantDrift = _serverPosition - _clientQuantizedPosition;
                Debug.Log($"<color=cyan>客户端量化模式最终漂移: {finalQuantDrift:F4}m</color>");
                Debug.Log("<color=green>结论: 客户端量化后漂移仍存在，但被限制在量化精度范围内（±0.01m）。" +
                          "不量化时漂移随模拟时间线性增长。</color>");
            }
        }

        /// <summary>将浮点值量化到指定步长</summary>
        static int Quantize(float value, float step)
        {
            return Mathf.RoundToInt(value / step);
        }

        /// <summary>将量化值恢复为浮点数</summary>
        static float Dequantize(int quantized, float step)
        {
            return quantized * step;
        }
    }
}
```

**运行预期输出**：

```
  Tick |  ServerPos |  ClientPos |      Drift |  QuantDrift
-----------------------------------------------------------------
     0 |     0.0000 |     0.0000 |     0.0000 |       0.0000
    60 |     5.0123 |     5.0089 |     0.0034 |       0.0012
   120 |    10.0241 |    10.0156 |     0.0085 |       0.0018
   180 |    15.0358 |    15.0187 |     0.0171 |       0.0024
   240 |    20.0475 |    20.0152 |     0.0323 |       0.0031
   300 |    25.0592 |    25.0068 |     0.0524 |       0.0035
   360 |    30.0710 |    29.9901 |     0.0809 |       0.0041
   420 |    35.0827 |    34.9671 |     0.1156 |       0.0048
   480 |    40.0944 |    39.9375 |     0.1569 |       0.0052
   540 |    45.1061 |    44.9004 |     0.2057 |       0.0059
   600 |    50.1178 |    49.8556 |     0.2622 |       0.0063
```

注意：普通模式下漂移随模拟时间线性增长（600 tick 后达 0.26m），而客户端量化模式将漂移限制在量化步长的量级（< 0.01m）。

---

### 2.2 C#: PartialSnapshotSimulator — 部分快照交互模拟器

```csharp
// PartialSnapshotSimulator.cs — 模拟部分快照到达导致的时间不一致交互
// 运行方式：在 Unity 中挂载到任意 GameObject，Console 观察输出
// 依赖: UnityEngine, System.Collections.Generic

using UnityEngine;
using System.Collections.Generic;
using System.Linq;

namespace PredictionEdgeCases
{
    /// <summary>
    /// 快照分包模拟器。
    ///
    /// 场景：
    ///   3 个 Ghost (A, B, C) 每个 tick 从服务器接收快照。
    ///   Ghost A 和 B 的快照在第一个包中到达（低延迟），
    ///   Ghost C 的快照在第二个包中到达（高延迟/丢包重传）。
    ///
    /// 当 A 和 B 回退到过去的 tick 而 C 还停留在"未来"时，
    /// 它们的碰撞检测产生错误结果。
    /// </summary>
    public class PartialSnapshotSimulator : MonoBehaviour
    {
        [Header("模拟设置")]
        [SerializeField] private int _totalTicks = 200;
        [SerializeField] private float _tickDt = 1.0f / 60.0f;

        [Header("网络模拟")]
        [SerializeField] private int _ghostC_PacketDelay = 5;  // Ghost C 的分包延迟（ticks）
        [SerializeField] private bool _enableGhostGrouping = false; // 是否启用快照原子性

        // === 状态 ===
        class GhostState
        {
            public string Name;
            public float PositionX;
            public float VelocityX;
            public uint LastServerTick;     // 最后收到的服务端权威 tick
            public float LastServerPosX;    // 最后收到的服务端权威位置
            public bool HasSnapshot;         // 当前 tick 是否收到了快照

            public GhostState Clone()
            {
                return new GhostState
                {
                    Name = Name,
                    PositionX = PositionX,
                    VelocityX = VelocityX,
                    LastServerTick = LastServerTick,
                    LastServerPosX = LastServerPosX,
                    HasSnapshot = HasSnapshot
                };
            }
        }

        private List<GhostState> _ghosts;
        private List<string> _collisionLog = new List<string>();
        private uint _tick;

        // 存放 "延迟到达" 的 Ghost C 快照
        private Queue<(uint tick, float serverPos)> _delayedPackets = new Queue<(uint, float)>();

        void Start()
        {
            InitializeSimulation();
            RunSimulation();
            PrintReport();
        }

        void InitializeSimulation()
        {
            _ghosts = new List<GhostState>
            {
                new GhostState { Name = "Ghost A", PositionX = 0f, VelocityX = 6f, LastServerTick = 0, LastServerPosX = 0f, HasSnapshot = true },
                new GhostState { Name = "Ghost B", PositionX = 3f, VelocityX = -6f, LastServerTick = 0, LastServerPosX = 3f, HasSnapshot = true },
                new GhostState { Name = "Ghost C", PositionX = 1.5f, VelocityX = 0f, LastServerTick = 0, LastServerPosX = 1.5f, HasSnapshot = false },
            };
            _tick = 0;
        }

        void RunSimulation()
        {
            for (int i = 0; i < _totalTicks; i++)
            {
                _tick++;

                // === 服务器生成快照 ===
                // 服务器上的真实状态（模拟确定性移动）
                float[] serverPositions = new float[3];
                for (int g = 0; g < 3; g++)
                {
                    var ghost = _ghosts[g];
                    serverPositions[g] = ghost.LastServerPosX + ghost.VelocityX * _tickDt;
                }

                // === 网络传输模拟 ===
                // Ghost A 和 B: 快照立即到达
                foreach (var ghost in _ghosts.Take(2))
                {
                    ghost.HasSnapshot = true;
                    ghost.LastServerTick = _tick;
                    if (_tick == 1)
                        ghost.LastServerPosX = ghost.PositionX; // 初始状态
                    else
                        ghost.LastServerPosX += ghost.VelocityX * _tickDt;
                }

                // Ghost C: 快照延迟到达
                // 将 Ghost C 的当前快照放入延迟队列
                _delayedPackets.Enqueue((_tick, serverPositions[2]));

                // 从延迟队列中取出"已经过了延迟期"的快照
                while (_delayedPackets.Count > 0 &&
                       _delayedPackets.Peek().tick + _ghostC_PacketDelay <= _tick)
                {
                    var (tick, pos) = _delayedPackets.Dequeue();
                    var ghostC = _ghosts[2];
                    ghostC.HasSnapshot = true;
                    ghostC.LastServerTick = tick;
                    ghostC.LastServerPosX = pos;
                }

                // === Ghost Grouping 模式 ===
                if (_enableGhostGrouping)
                {
                    // 检查所有 Ghost 是否都有当前 tick 的快照
                    bool allHaveSnapshot = _ghosts.All(g => g.LastServerTick >= _tick);
                    if (!allHaveSnapshot)
                    {
                        // 不触发回退——等待所有 Ghost 的快照到达
                        // 所有 Ghost 继续使用预测状态
                        foreach (var ghost in _ghosts)
                        {
                            ghost.PositionX += ghost.VelocityX * _tickDt;
                        }
                        continue;
                    }
                }

                // === 客户端回退逻辑 ===
                // 对收到快照的 Ghost 执行回退
                foreach (var ghost in _ghosts)
                {
                    if (ghost.HasSnapshot)
                    {
                        // 回退到服务端权威位置
                        ghost.PositionX = ghost.LastServerPosX;
                        // 然后前向预测到当前 tick
                        uint ticksSinceSnapshot = _tick - ghost.LastServerTick;
                        ghost.PositionX += ghost.VelocityX * _tickDt * ticksSinceSnapshot;
                    }
                    else
                    {
                        // 没有快照 → 继续使用纯预测
                        ghost.PositionX += ghost.VelocityX * _tickDt;
                    }
                }

                // === 碰撞检测 ===
                DetectCollisions();
            }
        }

        void DetectCollisions()
        {
            // 检测 A 和 C 是否碰撞（阈值 0.5m）
            float distA_C = Mathf.Abs(_ghosts[0].PositionX - _ghosts[2].PositionX);
            if (distA_C < 0.5f)
            {
                bool cHasSnapshot = _ghosts[2].HasSnapshot;
                _collisionLog.Add(
                    $"Tick {_tick:D3}: A(回退={_ghosts[0].HasSnapshot}) 与 C(快照={cHasSnapshot}) 碰撞! " +
                    $"距离={distA_C:F3}m | A.pos={_ghosts[0].PositionX:F3} C.pos={_ghosts[2].PositionX:F3}" +
                    (cHasSnapshot ? "" : " [警告: C未回退，时间不一致!]")
                );
            }

            // 检测 B 和 C 是否碰撞
            float distB_C = Mathf.Abs(_ghosts[1].PositionX - _ghosts[2].PositionX);
            if (distB_C < 0.5f)
            {
                bool cHasSnapshot = _ghosts[2].HasSnapshot;
                _collisionLog.Add(
                    $"Tick {_tick:D3}: B(回退={_ghosts[1].HasSnapshot}) 与 C(快照={cHasSnapshot}) 碰撞! " +
                    $"距离={distB_C:F3}m | B.pos={_ghosts[1].PositionX:F3} C.pos={_ghosts[2].PositionX:F3}" +
                    (cHasSnapshot ? "" : " [警告: C未回退，时间不一致!]")
                );
            }
        }

        void PrintReport()
        {
            Debug.Log($"=== 部分快照模拟结果 ===\nGhost Grouping: {_enableGhostGrouping}\n");

            int crossTickCollisions = _collisionLog.Count(l => l.Contains("[警告"));
            Debug.Log($"碰撞事件总数: {_collisionLog.Count}");
            Debug.Log($"跨 Tick 碰撞（时间不一致）: {crossTickCollisions}");

            foreach (var log in _collisionLog.Take(10))
            {
                if (log.Contains("[警告"))
                    Debug.Log($"<color=red>{log}</color>");
                else
                    Debug.Log(log);
            }
            if (_collisionLog.Count > 10)
                Debug.Log($"... 还有 {_collisionLog.Count - 10} 条日志");

            if (!_enableGhostGrouping && crossTickCollisions > 0)
            {
                Debug.Log("<color=yellow>结论: 当部分 Ghost 的快照延迟到达时，" +
                          "回退后的 Ghost 与未回退的 Ghost 之间发生了时间不一致的碰撞。" +
                          "启用 Ghost Grouping 可以消除此类问题。</color>");
            }
        }
    }
}
```

---

### 2.3 C#: InputDedupSystem — 输入去重系统

```csharp
// InputDedupSystem.cs — 输入重复应用防护系统
// 运行方式：挂载到 Unity GameObject，配合手动测试
// 依赖: UnityEngine, System.Collections.Generic

using UnityEngine;
using System.Collections.Generic;

namespace PredictionEdgeCases
{
    /// <summary>
    /// 输入去重系统：防止同一输入被重复应用。
    ///
    /// 两种去重策略：
    ///   1. 序列号去重：基于全局唯一的序列号
    ///   2. Tick 去重：基于"每个 tick 每个玩家只处理一次"
    ///
    /// 包含测试用例，模拟常见的重复应用场景。
    /// </summary>
    public class InputDedupSystem : MonoBehaviour
    {
        [Header("去重配置")]
        [SerializeField] private int _sequenceHistorySize = 1024;

        // === 序列号去重 ===
        private readonly HashSet<uint> _processedSequences = new HashSet<uint>();
        private uint _highestProcessedSeq;

        // === Tick 去重 ===
        // Key = tick, Value = 已处理的玩家 ID 集合
        private readonly Dictionary<uint, HashSet<int>> _tickPlayerMap = new Dictionary<uint, HashSet<int>>();
        private const int _maxTickHistory = 256;

        void Start()
        {
            RunTests();
        }

        void RunTests()
        {
            Debug.Log("=== 输入去重系统测试 ===\n");

            TestSequenceDedup();
            TestTickDedup();
            TestReconnectScenario();
        }

        // ================================================================
        // 序列号去重
        // ================================================================

        /// <summary>
        /// 检查并记录序列号。返回 true 表示应该处理，false 表示重复。
        /// </summary>
        public bool TryProcessSequence(uint seq)
        {
            // 快速路径：如果序列号 <= 最高已处理序列号，肯定处理过了
            if (seq <= _highestProcessedSeq && _highestProcessedSeq > 0)
            {
                Debug.Log($"<color=orange>[SeqDedup] 跳过重复输入 seq={seq} (≤ highest={_highestProcessedSeq})</color>");
                return false;
            }

            // 精确路径：检查去重集合
            if (_processedSequences.Contains(seq))
            {
                Debug.Log($"<color=orange>[SeqDedup] 跳过重复输入 seq={seq} (已存在于去重集合)</color>");
                return false;
            }

            // 记录
            _processedSequences.Add(seq);
            if (seq > _highestProcessedSeq)
                _highestProcessedSeq = seq;

            // 清理旧记录
            if (_processedSequences.Count > _sequenceHistorySize)
            {
                // 移除所有 ≤ highestProcessedSeq - historySize 的记录
                uint cutoff = _highestProcessedSeq - (uint)_sequenceHistorySize;
                _processedSequences.RemoveWhere(s => s <= cutoff);
            }

            return true;
        }

        void TestSequenceDedup()
        {
            Debug.Log("<b>测试 1: 序列号去重</b>");

            // 正常序列
            Debug.Assert(TryProcessSequence(100), "seq=100 应接受");
            Debug.Assert(TryProcessSequence(101), "seq=101 应接受");
            Debug.Assert(TryProcessSequence(102), "seq=102 应接受");

            // 重复发送 seq=101
            Debug.Assert(!TryProcessSequence(101), "seq=101 应被拒绝（重复）");

            // 小于 highest 的序列号
            Debug.Assert(!TryProcessSequence(50), "seq=50 应被拒绝（< highest）");

            Debug.Log("序列号去重测试通过 ✓\n");
        }

        // ================================================================
        // Tick 级别去重
        // ================================================================

        /// <summary>
        /// 检查指定 tick 是否已处理过指定玩家的输入。
        /// </summary>
        public bool TryProcessInputForTick(uint tick, int playerId)
        {
            if (!_tickPlayerMap.TryGetValue(tick, out var players))
            {
                players = new HashSet<int>();
                _tickPlayerMap[tick] = players;
            }

            if (players.Contains(playerId))
            {
                Debug.Log($"<color=orange>[TickDedup] Tick {tick} 已处理玩家 {playerId} 的输入</color>");
                return false;
            }

            players.Add(playerId);

            // 清理旧的 tick 记录
            if (_tickPlayerMap.Count > _maxTickHistory)
            {
                uint oldestTick = tick - (uint)_maxTickHistory;
                var toRemove = new List<uint>();
                foreach (var kv in _tickPlayerMap)
                {
                    if (kv.Key < oldestTick)
                        toRemove.Add(kv.Key);
                }
                foreach (var t in toRemove)
                    _tickPlayerMap.Remove(t);
            }

            return true;
        }

        void TestTickDedup()
        {
            Debug.Log("<b>测试 2: Tick 级别去重</b>");

            uint tick = 100;

            Debug.Assert(TryProcessInputForTick(tick, 1), "Tick100 P1 应接受");
            Debug.Assert(TryProcessInputForTick(tick, 2), "Tick100 P2 应接受");
            Debug.Assert(TryProcessInputForTick(tick, 3), "Tick100 P3 应接受");

            // 同一个玩家在同一个 tick 发两次
            Debug.Assert(!TryProcessInputForTick(tick, 1), "Tick100 P1 重复应被拒绝");

            // 新 tick
            Debug.Assert(TryProcessInputForTick(tick + 1, 1), "Tick101 P1 应接受");

            Debug.Log("Tick 级别去重测试通过 ✓\n");
        }

        // ================================================================
        // 重连场景
        // ================================================================

        /// <summary>
        /// 模拟重连：服务端告知最后处理的序列号，客户端据此清理已确认输入。
        /// </summary>
        public void OnReconnected(uint lastProcessedSeq)
        {
            Debug.Log($"<b>重连握手: 服务端最后处理 seq={lastProcessedSeq}</b>");

            // 更新最高已处理序列号
            if (lastProcessedSeq > _highestProcessedSeq)
                _highestProcessedSeq = lastProcessedSeq;

            // 清理已确认的序列号
            _processedSequences.RemoveWhere(s => s <= lastProcessedSeq);

            Debug.Log($"重连后: highestSeq={_highestProcessedSeq}, 去重集合大小={_processedSequences.Count}");
        }

        void TestReconnectScenario()
        {
            Debug.Log("<b>测试 3: 重连场景</b>");

            // 模拟客户端在处理了一些输入后断开
            Debug.Assert(TryProcessSequence(200), "连接中 seq=200");
            Debug.Assert(TryProcessSequence(201), "连接中 seq=201");
            Debug.Assert(TryProcessSequence(202), "连接中 seq=202");

            // 断开……重连……
            // 服务端告知最后处理的序列号是 201
            OnReconnected(201);

            // 客户端重新发送未确认输入: seq=202
            Debug.Assert(TryProcessSequence(202), "重连后重新发送 seq=202 应接受");

            // 客户端误发送已确认输入: seq=200
            Debug.Assert(!TryProcessSequence(200), "重连后误发送 seq=200 应被拒绝");

            Debug.Log("重连场景测试通过 ✓\n");
            Debug.Log("<color=green>全部输入去重测试通过！</color>");
        }
    }
}
```

---

### 2.4 C#: PredictedSpawnResolver — 预测生成物冲突解决方案

```csharp
// PredictedSpawnResolver.cs — 预测生成物的回退与冲突解决方案
// 运行方式：在 Unity 中挂载到任意 GameObject，Console 观察输出
// 依赖: UnityEngine, System.Collections.Generic

using UnityEngine;
using System.Collections.Generic;

namespace PredictionEdgeCases
{
    /// <summary>
    /// 预测生成物冲突解决器。
    ///
    /// 演示三种策略处理预测生成物（如子弹、火球）：
    ///   1. Allow Rollback to Spawn: 生成物参与回退，回退到其创建 tick
    ///   2. Freeze: 回退时生成物保持当前位置（简单但有碰撞错误）
    ///   3. Delete & Respawn: 回退时删除，重模拟时重新创建
    ///
    /// 场景:
    ///   客户端在 Tick 5 创建了预测子弹。
    ///   Tick 10 时收到服务端快照，触发回退到 Tick 3。
    ///   观察三种策略下子弹的状态变化。
    /// </summary>
    public class PredictedSpawnResolver : MonoBehaviour
    {
        // === 数据结构 ===

        /// <summary>预测生成物</summary>
        class PredictedEntity
        {
            public int Id;
            public uint SpawnTick;         // 创建时的客户端 tick
            public Vector3 Position;
            public Vector3 Velocity;
            public float Lifetime;         // 剩余生命（秒）
            public bool IsConfirmed;       // 是否已被服务端确认
            public uint? ServerSpawnTick;  // 服务端确认的生成 tick（确认后填充）

            public PredictedEntity Clone()
            {
                return new PredictedEntity
                {
                    Id = Id,
                    SpawnTick = SpawnTick,
                    Position = Position,
                    Velocity = Velocity,
                    Lifetime = Lifetime,
                    IsConfirmed = IsConfirmed,
                    ServerSpawnTick = ServerSpawnTick
                };
            }
        }

        /// <summary>策略枚举</summary>
        enum ResolutionStrategy
        {
            AllowRollbackToSpawn,  // 回退到生成tick
            Freeze,                // 冻结在当前位置
            DeleteAndRespawn       // 删除后重生成
        }

        // === 世界状态 ===
        private List<PredictedEntity> _predictedEntities = new List<PredictedEntity>();
        private uint _currentTick;
        private float _tickDt = 1.0f / 60.0f;
        private int _nextEntityId = 100;

        void Start()
        {
            Debug.Log("=== 预测生成物冲突解决器 ===\n");

            TestStrategy(ResolutionStrategy.AllowRollbackToSpawn, "策略 1: Allow Rollback to Spawn");
            TestStrategy(ResolutionStrategy.Freeze, "策略 2: Freeze (冻结)");
            TestStrategy(ResolutionStrategy.DeleteAndRespawn, "策略 3: Delete & Respawn");
        }

        void TestStrategy(ResolutionStrategy strategy, string label)
        {
            Debug.Log($"\n<color=cyan>--- {label} ---</color>");
            ResetWorld();

            // Tick 0-4: 正常预测
            for (int i = 0; i < 5; i++)
            {
                _currentTick++;
                SimulatePredictedEntities();

                if (_currentTick == 5)
                {
                    // 客户端预测生成一个子弹
                    var bullet = new PredictedEntity
                    {
                        Id = _nextEntityId++,
                        SpawnTick = _currentTick,
                        Position = new Vector3(0, 0, 0),
                        Velocity = new Vector3(10, 0, 0),
                        Lifetime = 1.0f,
                        IsConfirmed = false
                    };
                    _predictedEntities.Add(bullet);
                    Debug.Log($"Tick {_currentTick}: [创建预测子弹] id={bullet.Id}, pos={bullet.Position}");
                }

                LogWorldState();
            }

            // Tick 5-9: 继续预测，子弹飞行
            for (int i = 0; i < 5; i++)
            {
                _currentTick++;
                SimulatePredictedEntities();
                LogWorldState();
            }

            // Tick 10: 触发回退！收到服务端 Tick 3 的快照
            _currentTick++;
            Debug.Log($"<color=yellow>Tick {_currentTick}: [回退触发] 收到服务端 Tick 3 的快照 → 回退到 Tick 3</color>");

            var snapshot = _predictedEntities.ConvertAll(e => e.Clone());

            switch (strategy)
            {
                case ResolutionStrategy.AllowRollbackToSpawn:
                    HandleRollback_AllowToSpawn(3, snapshot);
                    break;
                case ResolutionStrategy.Freeze:
                    HandleRollback_Freeze(3, snapshot);
                    break;
                case ResolutionStrategy.DeleteAndRespawn:
                    HandleRollback_DeleteAndRespawn(3, snapshot);
                    break;
            }

            // 重模拟 Tick 4-10
            for (uint t = 4; t <= _currentTick; t++)
            {
                SimulatePredictedEntities();

                // 在 AllowRollbackToSpawn 模式下，当到达生成物创建 tick 时重新创建
                if (strategy == ResolutionStrategy.AllowRollbackToSpawn && t == 5)
                {
                    // 检查是否有"待重新生成"的标记
                    // （在 HandleRollback_AllowToSpawn 中已处理）
                }
            }

            LogWorldState();

            // 验证结果
            var bullet = _predictedEntities.Find(e => e.Id >= 100);
            if (bullet != null)
            {
                Debug.Log($"最终状态: 子弹 id={bullet.Id}, pos={bullet.Position:F2}, " +
                          $"lifetime={bullet.Lifetime:F3}s, confirmed={bullet.IsConfirmed}");
            }
        }

        // ================================================================
        // 三种策略实现
        // ================================================================

        /// <summary>
        /// 策略 1: 允许回退到生成物创建时的 tick。
        /// 回退时，预测生成物也回退到其 SpawnTick 时的状态。
        /// 重模拟时，到达 SpawnTick 时重新执行生成逻辑。
        /// </summary>
        void HandleRollback_AllowToSpawn(uint rollbackTick, List<PredictedEntity> beforeRollback)
        {
            var toRemove = new List<PredictedEntity>();

            foreach (var entity in _predictedEntities)
            {
                if (entity.IsConfirmed)
                    continue; // 已确认实体不变

                if (entity.SpawnTick > rollbackTick)
                {
                    // 该生成物是在回退 tick 之后创建的 → 必须回退到它创建时的状态
                    // 实际上就是"回退到生成瞬间"
                    Debug.Log($"  回退预测子弹 id={entity.Id}: 回到 SpawnTick={entity.SpawnTick} 的状态");
                    entity.Position = Vector3.zero; // 生成时位于枪口
                    entity.Lifetime = 2.0f;          // 恢复初始生命值
                }
                // entity.SpawnTick <= rollbackTick 的情况：生成物在回退点之前就存在
                // → 需要回退到 rollbackTick 时的状态，但预测生成物没有该 tick 的历史数据
                // → 需要额外的历史快照存储（简化处理：保留当前位置）
            }
        }

        /// <summary>
        /// 策略 2: 冻结预测生成物在当前位置。
        /// 简单但导致与其他回退实体的位置不一致。
        /// </summary>
        void HandleRollback_Freeze(uint rollbackTick, List<PredictedEntity> beforeRollback)
        {
            foreach (var entity in _predictedEntities)
            {
                if (entity.IsConfirmed) continue;
                if (entity.SpawnTick > rollbackTick)
                {
                    Debug.Log($"  冻结预测子弹 id={entity.Id}: 保持在 pos={entity.Position:F2}");
                    // 不做任何位置调整——"冻结"在当前状态
                    // 实际上不修改 entity 就是冻结
                }
            }
            Debug.Log("  [警告] 冻结的子弹与其他回退实体位置不一致，可能导致碰撞检测错误");
        }

        /// <summary>
        /// 策略 3: 删除预测生成物，重模拟时重新预测创建。
        /// 视觉上有闪烁（子弹短暂消失后重新出现）。
        /// </summary>
        void HandleRollback_DeleteAndRespawn(uint rollbackTick, List<PredictedEntity> beforeRollback)
        {
            var toRemove = new List<PredictedEntity>();

            foreach (var entity in _predictedEntities)
            {
                if (entity.IsConfirmed) continue;
                if (entity.SpawnTick > rollbackTick)
                {
                    Debug.Log($"  删除预测子弹 id={entity.Id}（将在重模拟到达 SpawnTick={entity.SpawnTick} 时重新创建）");
                    toRemove.Add(entity);
                }
            }

            // 记录被删除的生成物，以便在重模拟时重建
            foreach (var removed in toRemove)
            {
                _predictedEntities.Remove(removed);
                // 在实际系统中，这里会将 removed 的信息存入"待重生成队列"
                // 当重模拟推进到 removed.SpawnTick 时，重新执行生成逻辑
            }

            // 模拟重生成（在重模拟到 SpawnTick 时）
            // 简化处理：立即重新创建
            foreach (var removed in toRemove)
            {
                var respawn = new PredictedEntity
                {
                    Id = removed.Id,
                    SpawnTick = removed.SpawnTick,
                    Position = Vector3.zero,
                    Velocity = removed.Velocity,
                    Lifetime = 2.0f,
                    IsConfirmed = false
                };
                _predictedEntities.Add(respawn);
                Debug.Log($"  重新创建子弹 id={respawn.Id}（重生成）");
            }
        }

        // ================================================================
        // 辅助方法
        // ================================================================

        void SimulatePredictedEntities()
        {
            foreach (var entity in _predictedEntities)
            {
                entity.Position += entity.Velocity * _tickDt;
                entity.Lifetime -= _tickDt;
                if (entity.Lifetime <= 0)
                {
                    // 在实际系统中，应标记为销毁而非直接 Remove
                    // 简化：此处不做自动清理
                    entity.Velocity = Vector3.zero;
                }
            }
        }

        void LogWorldState()
        {
            foreach (var entity in _predictedEntities)
            {
                Debug.Log($"  Tick {_currentTick}: 子弹[{entity.Id}] pos={entity.Position:F2}, " +
                          $"life={entity.Lifetime:F2}s, spawnTick={entity.SpawnTick}");
            }
        }

        void ResetWorld()
        {
            _predictedEntities.Clear();
            _currentTick = 0;
        }
    }
}
```

---

## 3. 练习

### 练习 1：量化漂移可视化 [基础]

**目标**：将 QuantizationDriftDemo 扩展为带有实时可视化的工具。

**要求**：

1. 在 `QuantizationDriftDemo` 的基础上：
   - 添加 `OnGUI` 实时显示服务器位置、客户端位置、漂移值的折线图（用 `Handles.DrawLine` 或简单的 `Debug.DrawLine`）
   - 添加滑块控制量化精度（1cm / 2cm / 5cm / 10cm），观察漂移速度的变化
2. 在 Unity Scene 视图中用三个球体可视化：
   - 红色球：服务器权威位置
   - 绿色球：客户端不量化位置
   - 蓝色球：客户端量化位置
   - 球之间画连线标注偏差距离
3. 添加一个按钮"注入单次回退"，点击后手动触发一次和解，观察漂移是否被重置
4. 输出统计：模拟 1000 tick 内，最大漂移、平均漂移、漂移超过 0.5m 的 tick 占比

**提示**：
- `Application.targetFrameRate = 60` 固定渲染帧率以便观察
- 使用 `Time.timeScale` 控制模拟速度（设为 5-10 倍速快进观察长期漂移）
- 漂移数据写入 `List<Vector2>` 用于绘制折线图

---

### 练习 2：部分快照碰撞检测修复 [进阶]

**目标**：在 PartialSnapshotSimulator 的基础上，实现跨 tick 碰撞检测的安全网，并评估不同策略的性能影响。

**要求**：

1. 在 `PartialSnapshotSimulator` 中实现**物理层隔离**：
   - 为每个 Ghost 添加 `uint LastAppliedTick` 字段
   - 在碰撞回调中，如果两个 Ghost 的 `LastAppliedTick` 不同，**跳过碰撞响应**
   - 但同时记录这条碰撞信息到日志，标注"被跳过的跨 tick 碰撞"
2. 添加 Ghost Grouping 模式（通过 `_enableGhostGrouping` 切换），对比两种模式：
   - 统计"被跳过的碰撞"次数
   - 统计"合法碰撞"次数
   - 计算 Ghost Grouping 引入的额外延迟（等待最慢分包的 tick 数）
3. 模拟不同丢包率（5%, 10%, 20%），输出对比表格
4. 写一个 `PartialSnapshotTestRunner`，自动化运行 100 次模拟（每次随机化网络时序），统计碰撞正确率

**提示**：
- 丢包模拟：对每个延迟包以概率 p 丢弃，并在 3 ticks 后重发（模拟 UDP 丢包重传）
- 碰撞正确率 = 客户端检测到的碰撞中，服务端也判定为碰撞的比例

---

### 练习 3：构建预测系统边缘情况测试框架 [挑战]

**目标**：设计一个可扩展的测试框架，能够自动化验证本节涉及的所有边缘情况。

**要求**：

1. 定义测试抽象接口：

```csharp
public interface IEdgeCaseTest
{
    string TestName { get; }
    string Description { get; }
    TestResult Run(int seed, NetworkCondition network);
}

public struct NetworkCondition
{
    public int RttMs;
    public float PacketLossRate;
    public float JitterMs;
    public int TickRate;
}

public struct TestResult
{
    public bool Passed;
    public float MaxDrift;
    public int AnomalyCount;
    public string Details;
}
```

2. 实现至少 4 个测试用例：
   - `QuantizationDriftTest`：在不同量化精度下运行 600 tick，验证漂移 < 阈值
   - `PartialSnapshotTest`：在不同丢包率下运行 200 tick，验证跨 tick 碰撞被正确隔离
   - `InputDedupTest`：注入重复输入，验证去重系统正确率 100%
   - `PredictedSpawnTest`：创建并回退预测生成物，验证三种策略的正确性
3. 测试框架支持：
   - 确定性随机种子（相同种子产生相同的网络时序）
   - 可配置的 `NetworkCondition`（模拟不同网络环境）
   - 测试报告输出为 Markdown 表格
4. 运行完整的测试套件并生成一份报告

**提示**：
- 使用 `System.Random(seed)` 确保确定性
- 每个测试用例应该是自包含的（不依赖 Unity Scene），可以在 `[RuntimeInitializeOnLoadMethod]` 中批量运行
- 测试报告可以用 `StringBuilder` 拼接 Markdown，然后 `Debug.Log` 输出

---

## 4. 扩展阅读

- **Unity Netcode for Entities — Prediction**：[https://docs.unity3d.com/Packages/com.unity.netcode@latest](https://docs.unity3d.com/Packages/com.unity.netcode@latest) — N4E 的官方文档，包含 Quantization Drift 和 Partial Snapshot Interactions 的详细说明。这是本节两大核心问题的原始出处。
- **Unity Netcode for Entities — Ghost Snapshots**：[https://docs.unity3d.com/Packages/com.unity.netcode@latest/manual/ghost-snapshots.html](https://docs.unity3d.com/Packages/com.unity.netcode@latest/manual/ghost-snapshots.html) — Ghost 快照的分包、重组、插值机制文档。
- **Gaffer On Games: Deterministic Lockstep**：[https://gafferongames.com/post/deterministic_lockstep/](https://gafferongames.com/post/deterministic_lockstep/) — Glenn Fiedler 关于确定性的经典文章。理解"为什么帧同步没有量化漂移问题"的最佳参考。
- **Overwatch Gameplay Architecture and Netcode (GDC 2017)**：[https://www.youtube.com/watch?v=W3aieHjyNvw](https://www.youtube.com/watch?v=W3aieHjyNvw) — 守望先锋团队分享的 ECS + 预测系统架构。重点观看"预测回滚的性能优化"和"实体生命周期的边缘情况"部分。
- **"Floating Point Determinism" by Bruce Dawson**：[https://randomascii.wordpress.com/2013/07/16/floating-point-determinism/](https://randomascii.wordpress.com/2013/07/16/floating-point-determinism/) — 关于浮点数在跨平台/跨编译器时的确定性问题的深度文章。与量化漂移直接相关。
- **Roblox Networking — Client Prediction & Replication**：[https://create.roblox.com/docs/scripting/network-ownership](https://create.roblox.com/docs/scripting/network-ownership) — Roblox 引擎的网络复制模型文档，包含输入去重和预测生成物的工程实践。
- **"Networked Physics in Virtual Reality" (GDC 2018)**：[https://www.gdcvault.com/play/1025377/](https://www.gdcvault.com/play/1025377/) — 关于网络物理模拟中确定性、量化精度和时间步同步的实际案例。

---

## 常见陷阱

### 陷阱 1：忽略量化漂移，上线后才暴露

**症状**：开发环境（LAN）测试一切正常。上线后，玩家报告"角色瞬移"、"子弹打在空气上"、"回放录像位置不一致"。排查发现是量化精度累积误差。

**正确做法**：
- 在开发阶段就使用网络模拟器（如 Unity Transport 的 `SimulatorPipeline` 或 `clumsy`）引入延迟和丢包
- **不要只在 LAN 环境测试**——量化漂移在 RTT < 5ms 时几乎不触发，但在 RTT > 50ms + 高频回滚时快速累积
- 在 CI 中加入量化漂移的自动化测试：固定随机种子，模拟 600+ tick，断言漂移 < 某个阈值
- 面试时主动提到这个陷阱 = 证明你上过线

### 陷阱 2：协议升级后旧客户端不兼容新的量化精度

**症状**：服务端升级了量化精度（如从 int16 改为 int24），旧版本客户端使用旧精度反量化 → 位置完全错乱。

**正确做法**：
- 在握手协议中包含量化参数（step, bit depth）
- 或者始终使用固定的量化参数（写在协议规范中，永不修改）
- 如果必须修改，需要协议版本号 + 客户端强制更新机制

### 陷阱 3：部分快照时"乐观应用"导致状态撕裂

**症状**：为了降低延迟，客户端"乐观地"在收到一个 tick 的部分快照后就应用回退。已回退的 Ghost 与未回退的 Ghost 交互 → 穿透、穿模、错误的弹道。

**正确做法**：
- 要么：启用 Ghost Grouping，等一个 tick 的所有快照收齐后再回退
- 要么：通过物理层隔离，阻止跨 tick 的碰撞响应
- **不要选择"部分应用"**——它节省的延迟通常只有 1-3ms（一个包的时间差），但引入的正确性问题可能需要数周才能 debug 完

### 陷阱 4：序列号溢出导致去重失效

**症状**：使用 uint16 (0-65535) 做输入序列号，16.6fps 下约 65 分钟回绕，60fps 下约 18 分钟回绕。回绕后去重系统将新输入误判为旧输入，导致输入被丢弃。

**正确做法**：
- **永远使用 uint32 或 uint64 做序列号。** uint32 在 60fps 下可用 828 天，uint64 基本永不回绕
- 如果被迫使用小类型（如嵌入式/带宽受限），使用序列号比较的环形逻辑：
  ```csharp
  bool IsNewer(uint16 a, uint16 b) {
      return (ushort)(a - b) < 32768; // 半环判定
  }
  ```

### 陷阱 5：预测生成物的销毁时序错误

**症状**：客户端判定火球碰撞后立即 `Destroy(gameObject)`，但 2 ticks 后服务端和解触发回退——回退系统试图恢复火球的状态，但 GameObject 已被销毁 → `MissingReferenceException`。

**正确做法**：
- 预测生成物的销毁必须通过**标记 + 延迟确认**机制
- 客户端不直接 Destroy，而是标记为 `PendingDestroy`，隐藏渲染，等待服务端确认后才真正释放
- 回退系统在恢复状态时检查 `PendingDestroy` 标记，跳过已标记销毁的实体

### 陷阱 6：dt 累积误差 + 跨平台浮点差异

**症状**：Windows 客户端和 Linux 服务器使用相同的代码和参数，但 10 分钟后位置偏差达数米。排查发现 `Time.deltaTime` 在两个平台上的浮点舍入行为不同。

**正确做法**：
- 使用固定步长 `const float FIXED_DT = 1.0f / 60.0f;`，不依赖平台 `deltaTime`
- 关键时间逻辑使用整数 tick 计数（`if (currentTick >= nextEventTick)`）而非 float 时间比较
- 对于需要跨平台确定性的游戏，考虑使用定点数数学库

### 陷阱 7：重连时不做输入幂等性检查

**症状**：玩家断线重连后，客户端乐观地重发了最近 30 帧的输入，其中 15 帧在断线前已被服务端处理。服务端没有去重 → 移动距离 × 2，跳跃 × 2，射击 × 2（= 双倍伤害 bug）。

**正确做法**：
- 重连握手时服务端返回 `lastProcessedSeq`
- 客户端丢弃所有 `seq <= lastProcessedSeq` 的输入
- 服务端始终做输入去重（即使没有重连，UDP 重复包也可能导致重发）
