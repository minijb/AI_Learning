---
title: "学习计划: 游戏性能优化全攻略"
updated: 2026-06-05
---

# 学习计划: 游戏性能优化全攻略

> 创建日期: 2026-05-31
> 预计总耗时: ~40 小时（44 节，每节 45-90 分钟）
> 目标水平: 精通 — 从零基础到能独立完成游戏性能分析、定位瓶颈并实施优化方案

---

## 学习目标

完成本计划后，你将能：

1. 使用至少 3 种 Profiling 工具（RenderDoc、Tracy/Superluminal、引擎内置 Profiler）独立进行帧分析
2. 识别并解决 Draw Call 过多、Overdraw、填充率瓶颈、Shader 变体爆炸等渲染问题
3. 运用数据导向设计、多线程任务系统、ECS 架构优化 CPU 端性能
4. 设计内存池、Arena、流式加载方案降低内存分配开销
5. 理解 GPU 架构管线，优化带宽占用和 Compute Shader 调度
6. 分别在 Unity 和 Unreal Engine 中落地上述优化技术
7. 为 2D 游戏专门应用 Sprite 合批、图集、UI 优化
8. 独立完成一个游戏场景从 30fps 到 60fps 的性能优化闭环

---

## 前置要求

- [ ] 至少一门游戏开发常用语言的基础（C++、C# 或 Blueprint）
- [ ] 基本 3D/2D 数学知识（向量、矩阵、坐标变换）
- [ ] 有使用过 Unity 或 Unreal Engine 运行过 Demo 的经验（非必须，但强烈建议）
- [ ] 如果没有以上基础，建议先完成 `game-engine-dev` 学习计划的前 2 个阶段

---

## 学习路径

| 序号 | 知识点 | 预计耗时 | 类型 | 前置 |
|------|--------|---------|------|------|
| 01 | 为什么要优化 — 性能优化的经济学与时机 | 45min | 基础 | 无 |
| 02 | 性能测量方法学 — 测量、定位、验证三步法 | 60min | 基础 | 01 |
| 03 | Profiling 工具概览 | 45min | 基础 | 02 |
| 04 | 帧分析基础 — Frame Timing 与瓶颈识别 | 60min | 基础 | 03 |
| 05 | Draw Call 优化 — 合批、实例化、材质合并 | 60min | 基础 | 04 |
| 06 | 裁剪技术 — 视锥体、遮挡、Portal 裁剪 | 60min | 基础 | 05 |
| 07 | LOD 系统 — Mesh/Shader/Texture 层级管理 | 45min | 基础 | 06 |
| 08 | Shader 优化基础 — ALU、采样、精度、变体 | 60min | 进阶 | 05 |
| 09 | 纹理优化 — 压缩、图集、流式加载 | 45min | 基础 | 07 |
| 10 | Overdraw 与填充率优化 | 50min | 进阶 | 05 |
| 11 | 光照优化 — 烘焙、Light Culling、阴影 | 60min | 进阶 | 05 |
| 12 | 后处理优化 — 全屏特效的代价与降级 | 45min | 进阶 | 11 |
| 13 | 数据导向设计 (DOD) — Cache 与数据布局 | 60min | 基础 | 01 |
| 14 | 多线程基础 — Job System 与 Task Graph | 60min | 进阶 | 13 |
| 15 | ECS 架构 — Entity Component System 原理 | 50min | 进阶 | 14 |
| 16 | SIMD 与向量化入门 | 45min | 进阶 | 13 |
| 17 | 算法与数据结构优化 — 空间分割 | 60min | 基础 | 13 |
| 18 | 内存分配策略 — 池/Arena/帧分配器 | 50min | 基础 | 13 |
| 19 | 对象池与复用 — 减少分配抖动 | 45min | 基础 | 18 |
| 20 | 流式加载与异步 IO | 50min | 进阶 | 19 |
| 21 | 内存带宽优化 — 压缩与数据布局 | 45min | 进阶 | 18 |
| 22 | GC 规避策略 — C#/Unity 中的 GC 压力管理 | 50min | 进阶 | 18 |
| 23 | GPU 架构简析 — 并行模型与调度 | 60min | 进阶 | 05 |
| 24 | GPU 带宽优化 — 纹理压缩与 Tiling | 50min | 进阶 | 23 |
| 25 | Compute Shader 优化 | 60min | 进阶 | 24 |
| 26 | Async Compute 与现代 GPU 并行 | 45min | 进阶 | 25 |
| 27 | GPU Capture 实战 — RenderDoc 全流程 | 60min | 基础 | 04 |
| 28 | CPU Profiling 实战 — Tracy/Superluminal | 50min | 进阶 | 14 |
| 29 | 自动化性能测试与回归检测 | 45min | 进阶 | 02 |
| 30 | Unity 渲染管线优化 — URP/HDRP 选型 | 60min | 基础 | 05 |
| 31 | Unity Job System + Burst Compiler | 60min | 进阶 | 14 |
| 32 | Unity 内存管理与 Addressables | 50min | 基础 | 18 |
| 33 | Unity 常见性能陷阱 | 50min | 基础 | 30 |
| 34 | Unity DOTS 入门 — ECS+Job+Burst | 60min | 进阶 | 15 |
| 35 | UE 渲染优化 — Nanite/Lumen/VSM | 60min | 进阶 | 05 |
| 36 | UE 线程模型与 Task System | 50min | 进阶 | 14 |
| 37 | UE 内存管理与 GC | 50min | 进阶 | 18 |
| 38 | UE Profiler 工具链 — Insights, Stat, CSV | 60min | 基础 | 04 |
| 39 | UE 常见性能陷阱 | 50min | 基础 | 35 |
| 40 | 2D Sprite 合批与图集优化 | 45min | 基础 | 05 |
| 41 | 2D Tilemap 与关卡流式加载 | 45min | 基础 | 40 |
| 42 | UI 性能优化 — Canvas/UMG/UIToolkit | 50min | 进阶 | 40 |
| 43 | 案例研究：3D 场景 30fps→60fps 全流程 | 90min | 综合 | 06-39 |
| 44 | 案例研究：2D 手游性能调优全流程 | 90min | 综合 | 40-42 |

---

## 里程碑

- [ ] **第一阶段 (01-04)**：掌握性能思维 — 能独立测量帧时间，识别 CPU/GPU Bound，使用至少一种 Profiler
- [ ] **第二阶段 (05-12)**：掌握渲染优化 — 能诊断并解决 Draw Call、Overdraw、Shader 问题
- [ ] **第三阶段 (13-17)**：掌握 CPU 优化 — 能应用 DOD、多线程、ECS 优化游戏逻辑
- [ ] **第四阶段 (18-22)**：掌握内存优化 — 能设计分配器、对象池、流式加载方案
- [ ] **第五阶段 (23-26)**：掌握 GPU 深入 — 能优化 Compute Shader 和带宽占用
- [ ] **第六阶段 (27-29)**：掌握 Profiling 实战 — 能独立完成帧分析和性能回归检测
- [ ] **第七阶段 (30-34)**：掌握 Unity 落地 — 能在 Unity 项目中实施全套优化
- [ ] **第八阶段 (35-39)**：掌握 Unreal 落地 — 能在 UE 项目中实施全套优化
- [ ] **第九阶段 (40-42)**：掌握 2D 优化 — 能为 2D 游戏专门调优
- [ ] **最终项目**：任选一个 3D Demo 场景，使用所学技术将其从 <30fps 优化到稳定 60fps，并产出优化报告
