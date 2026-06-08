---
title: "架构对比与延伸阅读"
updated: 2026-06-05
---

# 架构对比与延伸阅读

> 基于笔记: gabrielgambetta-network.md
> 所属教程: 快节奏多人游戏网络架构 — 从 Gambetta 系列到工业实践
> 章: 5/5

---

## 直觉理解：三种"时空观"

多人游戏的网络架构，本质上是对**时空一致性**的不同折衷方案。想象三个人在不同房间，通过电话玩同一个棋类游戏：

- **Lockstep**：每个人都有完整的棋盘。每走一步，大家**等所有人都确认**后再一起更新棋盘。没有人看到"未来"，没有人看到"错误"——但最慢的人决定了所有人的等待时间。

- **权威服务器 + 预测**（Gambetta 方案）：只有一个人（服务器）的棋盘是"真正的"棋盘。其他人有**自己的本地棋盘**（预测），但随时可能被服务器的**最新棋盘照片**（快照）纠正。你看自己的棋子是即时反应，看别人的棋子是"几秒前的照片"。

- **Rollback（GGPO）**：两个人各自预测对方的走法。如果预测错了，**回退棋盘状态**到错误发生前的瞬间，用对方实际的走法重新模拟。没有中央权威——谁都可以是"正确的"，但回退时的视觉闪烁是不可避免的代价。

---

## 三种架构对比

### Lockstep（确定性同步）

```
工作原理:
  客户端 A → 输入 #1 → 广播给所有人
  客户端 B → 输入 #1 → 广播给所有人
  （等待所有人的输入 #1 到齐）
  所有人一起执行 tick #1
  所有人一起执行 tick #2
  ...
```

**优势**：
- 带宽极低——只传输入，不传世界状态
- 天然一致性——每台机器运行相同的确定性模拟，状态必然相同
- 回放简单——记录输入序列即可完整重现

**劣势**：
- **最慢玩家决定所有人的延迟**——一个高 ping 玩家卡住整个游戏
- 无法隐藏输入延迟——必须等待输入到达后才能渲染
- 安全性差——每个客户端看到完整游戏状态（地图 hack 问题）

**代表游戏**：星际争霸 1/2、帝国时代、文明系列（回合制是 lockstep 的特例）

### 权威服务器 + 预测（Gambetta 方案，本教程核心）

```
工作原理:
  客户端 → 输入 → 服务器 → 权威世界状态 → 快照 → 所有客户端
  客户端本地立即预测（不等服务器确认）
  客户端协调（用服务器状态纠正预测）
```

**优势**：
- 每个玩家独立的输入延迟——不受其他玩家影响
- 服务器控制信息分发（防止地图 hack）
- 支持大规模玩家（MMO）

**劣势**：
- 带宽中等——需要发送世界快照
- 需要实现多种协同技术（预测、插值、延迟补偿）
- 协调不一致时产生"橡皮筋"效果

**代表游戏**：CS:GO、Valorant、Overwatch、LOL、Fortnite

### Rollback Netcode（GGPO）

```
工作原理:
  客户端 A 预测 B 的输入 → 本地模拟
  客户端 B 预测 A 的输入 → 本地模拟
  当实际输入到达且与预测不同时:
    回退到预测偏离帧 → 用实际输入重新模拟到当前帧
```

**优势**：
- 零输入延迟——和单机体验一样
- 不需要服务器——P2P 直连
- 用带宽换延迟——只传输入，极低带宽

**劣势**：
- 回退时的视觉闪烁（"画面回跳"）
- 只适合 2-4 人（状态规模小，回退成本低）
- 模拟必须是确定性的（不能用浮点随机数）

**代表游戏**：街霸 5、Guilty Gear Strive、Skullgirls、Killer Instinct

---

### 决策矩阵

| 你的游戏是……            | 推荐架构              | 核心技术                  |
| ------------------ | ----------------- | --------------------- |
| 2 人 1v1 格斗（毫秒级反应）  | Rollback (GGPO)   | 预测 + 回退               |
| 多人 FPS/TPS（空间敏感射击） | 权威服务器 + 全套        | 预测 + 插值 + 延迟补偿        |
| 多人 MOBA（技能判定敏感）    | 权威服务器 + 预测        | 预测 + 插值（通常不需要延迟补偿）    |
| 多人赛车/飞行模拟          | 权威服务器 + 预测 + 航位推算 | 航位推算（不需要延迟补偿）         |
| 大型 MMO（大量玩家）       | 权威服务器 + 兴趣管理      | 插值 + 兴趣管理（预测可选）       |
| RTS（少人对战）          | Lockstep          | 确定性同步                 |
| 回合制/卡牌             | 朴素客户端-服务器         | 无特殊需求                 |
| 大逃杀（100 玩家）        | 权威服务器 + 全套        | 预测 + 插值 + 延迟补偿 + 兴趣管理 |
| 合作 PvE（低竞争）        | 权威服务器 + 预测        | 预测 + 插值（延迟补偿可选）       |

---

## 笔记中提出的额外阅读

笔记末尾列出了多个 Valve Developer Wiki 链接。这里按学习顺序重新组织：

### 必读（按顺序）

1. **[Source Multiplayer Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking)**
   Valve 官方对 Source Engine 网络栈的完整文档。涵盖所有本教程讨论的技术在真实引擎中的实现细节。建议在读完本教程全部 5 章后阅读——此时你已经理解原理，可以专注于"引擎怎么实现的"。

2. **[Latency Compensating Methods in Client/Server In-game Protocol Design and Optimization](https://developer.valvesoftware.com/wiki/Latency_Compensating_Methods_in_Client/Server_In-game_Protocol_Design_and_Optimization)**
   Yahn Bernier（Valve 工程师）撰写的延迟补偿原始设计文档。这是本教程第 3 章的"源头文献"——Gambetta 的延迟补偿解释源自这篇论文。它讨论了许多 Gambetta 文章中跳过的细节，包括：
   - 误差累积和校正策略
   - 多种补偿方法的数学比较
   - 作弊防护考量

3. **[Gaffer On Games: Networked Physics](https://gafferongames.com/post/networked_physics_2004/)**
   Glenn Fiedler 的网络物理系列。与本教程的视角互补——Gambetta 从架构层面讲，Glenn 从物理模拟的确定性入手。

### 进阶（探索特定主题）

4. **[Overwatch Gameplay Architecture and Netcode](https://www.youtube.com/watch?v=W3aieHjyNvw)**（GDC 演讲）
   Blizzard 在 Overwatch 中使用的快照插值（snapshot interpolation）架构。与本教程的"状态插值"（state interpolation）形成对比。

5. **[Mas Bandwidth](https://mas-bandwidth.com/)**
   游戏网络带宽建模工具。如果笔记中对"我的游戏需要多少带宽"有疑问，这个工具可以提供估算。

6. **[GGPO](https://www.ggpo.net/)**
   回滚网络代码的开创性实现。如果对本章讨论的 rollback 架构感兴趣，这是起点。
   一篇极好的回退算法解释：[Gaffer On Games: Deterministic Lockstep](https://gafferongames.com/post/deterministic_lockstep/)

7. **[Valve Networking Category](https://developer.valvesoftware.com/wiki/Category:Networking)**
   Valve 网络文档的索引页面——包含 Source 2 引擎更新的网络相关信息。

---

## 关键收获

1. **网络延迟是物理定律，无法消除——只能隐藏。**客户端预测隐藏输入延迟，实体插值隐藏更新间隔，延迟补偿隐藏判定延迟。三者各司其职。

2. **序列号是协调机制的基石。**一个单调递增的 int 解决了"服务器确认了哪些输入"的问题，进而使得客户端可以准确地用公式 `predicted_state = server_state + Σ(unacked_inputs)` 重建正确的当前状态。

3. **"看到自己在现在，看到他人在过去"是客户端-服务器架构的必然结果，不是 bug。**延迟补偿的存在是为了让"射击过去的他人"变得公平，但它引入的"favor the shooter"原则是一种哲学选择——不是唯一正确的答案。

4. **技术选型取决于游戏类型的物理特性。**可预测的运动 → 航位推算；不可预测的运动 → 插值；空间敏感交互 → 延迟补偿；确定性要求高 → Lockstep；2 人对战 → Rollback。

5. **带宽优化和作弊防护是一枚硬币的两面。**兴趣管理既节省带宽又防止 wallhack；输入验证既减少同步错误又防止 speedhack；延迟补偿上限既控制内存又防止 lag switch。

---

## 本教程中涉及的外部知识与引用

本教程在撰写过程中引用了以下已有知识库内容，建议交叉阅读：

- **[[../../deep-dives/client-server-netcode|快节奏多人游戏网络架构深度剖析]]** — 7 层深度的完整分析，覆盖本教程所有概念的底层数学、性能数据和代码实现的 C++ 版本
- **[[../../deep-dives/fixed-timestep|固定时间步长深度分析]]** — 游戏循环中固定时间步长的完整指南，包括 Unity/Unreal/C++ 三大平台的实现

---

*教程完成于 2026-06-05。基于 Gabriel Gambetta 的四篇系列文章（客户端-服务器架构、客户端预测与协调、实体插值、延迟补偿）及用户在 drafts/gabrielgambetta-network.md 中的笔记深化。*
