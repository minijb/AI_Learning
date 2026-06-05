---
title: "学习资源: 帧同步、状态同步与状态帧同步"
updated: 2026-06-05
---

# 学习资源: 帧同步、状态同步与状态帧同步

## 官方文档

- [Unity Netcode for GameObjects](https://docs-multiplayer.unity3d.com/netcode/current/about/) — Unity 官方网络框架
- [Unity Netcode for Entities](https://docs.unity3d.com/Packages/com.unity.netcode@latest) — Unity DOTS ECS 网络方案
- [Unreal Engine Networking & Multiplayer](https://dev.epicgames.com/documentation/en-us/unreal-engine/networking-and-multiplayer-in-unreal-engine) — UE 官方网络文档
- [Unreal Iris Replication System](https://dev.epicgames.com/documentation/en-us/unreal-engine/components-of-iris-in-unreal-engine) — UE5 Iris 复制系统
- [Unreal Gameplay Ability System](https://dev.epicgames.com/documentation/en-us/unreal-engine/understanding-the-unreal-engine-gameplay-ability-system) — GAS 文档
- [Protobuf](https://protobuf.dev/) / [FlatBuffers](https://flatbuffers.dev/) — 序列化库

## 经典文章

- [Gaffer On Games: Deterministic Lockstep](https://gafferongames.com/post/deterministic_lockstep/) — 帧同步经典
- [Gaffer On Games: Networked Physics](https://gafferongames.com/post/networked_physics/) — 网络物理
- [Gabriel Gambetta: Client-Side Prediction and Server Reconciliation](https://www.gabrielgambetta.com/client-side-prediction-server-reconciliation.html) — 状态同步必读三件套
- [Gabriel Gambetta: Entity Interpolation](https://www.gabrielgambetta.com/entity-interpolation.html)
- [Gabriel Gambetta: Lag Compensation](https://www.gabrielgambetta.com/lag-compensation.html)
- [Valve: Source Multiplayer Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) — Source 引擎网络架构
- [Riot: Peeking into VALORANT's Netcode](https://technology.riotgames.com/news/peeking-valorants-netcode)
- [Overwatch GDC: Gameplay Architecture and Netcode](https://www.gdcvault.com/play/1024001/Overwatch-Gameplay-Architecture-and)

## 中文资源

- [腾讯云: 从王者荣耀聊聊游戏的帧同步](https://cloud.tencent.com/developer/article/2479003)
- [帧同步战斗服务器的设计](https://luda.plus/frame-synchronization-server-design/)
- [网络同步：状态帧同步DS方案总结（合金弹头觉醒）](https://www.crydust.top/p/State-LockStep/)
- [状态同步与帧同步：多人游戏网络同步技术深度解析](https://crazy-boy.com/posts/state-and-frame-sync.html)
- [帧同步游戏开发基础指南（腾讯）](https://developer.cloud.tencent.com/article/1050868)
- [网络游戏同步技术系列（CSDN）](https://blog.csdn.net/antsmall/article/details/138723002)
- [GAMES104: 网络游戏的架构基础 (B站)](https://www.bilibili.com/video/BV1La411o7kG)
- [合金弹头: 基于Unity引擎的前后端研发实战 (B站)](https://www.bilibili.com/video/BV1we411r757)

## 开源项目

### 帧同步
- [Kirito9910/UnityLockstep](https://github.com/Kirito9910/UnityLockstep) — Unity 帧同步实现
- [pietrobassi/deterministic-lockstep-demo](https://github.com/pietrobassi/deterministic-lockstep-demo) — C++ 确定性锁步 Demo
- [GbGr/lagless](https://github.com/GbGr/lagless) — 帧同步网络库

### 状态同步
- [tranek/GASDocumentation](https://github.com/tranek/GASDocumentation) — UE GAS 详解
- [V4LKdev/UE5-AbilitySystemFramework-Sample](https://github.com/V4LKdev/UE5-AbilitySystemFramework-Sample) — UE5 GAS 示例

### 混合同步 / 游戏服务器
- [wqaetly/NKGMobaBasedOnET](https://github.com/wqaetly/NKGMobaBasedOnET) — 基于 ET 框架的 MOBA
- [cloudwu/skynet](https://github.com/cloudwu/skynet) — Lua 游戏服务器框架
- [dudu502/LittleBee](https://github.com/dudu502/LittleBee) — 帧同步+状态同步混合方案
- [Weikang01/moba_game_server](https://github.com/Weikang01/moba_game_server) — Lua MOBA 游戏服务器

## 推荐书籍

- *Multiplayer Game Programming* — Joshua Glazer, Sanjay Madhav
- *Game Engine Architecture* (3rd Edition) — Jason Gregory (Chapter 8: Networking)
- *网络游戏同步技术* (中文) — 各平台有售

## 视频课程

- GDC Vault: Overwatch Netcode
- GDC Vault: 8 Frames in 16ms — Rollback Networking in Mortal Kombat and Injustice 2
- GDC Vault: I Shot You First — Networking the Gameplay of Halo: Reach
- B站: GAMES104-现代游戏引擎：从入门到实践 (网络章节)
