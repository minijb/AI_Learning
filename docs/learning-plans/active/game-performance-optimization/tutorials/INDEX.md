---
title: "教程目录索引"
updated: 2026-06-05
---

# 教程目录索引

> 游戏性能优化全攻略 — 44 节课，按学习路径排序

---

## Phase 1: 性能思维与测量基础

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 01 | [[01-why-optimize]] | 为什么要优化 — 性能优化的经济学与时机 | 基础 | 45min |
| 02 | [[02-profiling-methodology]] | 性能测量方法学 — 测量、定位、验证三步法 | 基础 | 60min |
| 03 | [[03-profiling-tools]] | Profiling 工具概览 | 基础 | 45min |
| 04 | [[04-frame-analysis]] | 帧分析基础 — Frame Timing 与瓶颈识别 | 基础 | 60min |

## Phase 2: 渲染优化原理

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 05 | [[05-draw-call-batching]] | Draw Call 优化 — 合批、实例化、材质合并 | 基础 | 60min |
| 06 | [[06-culling-techniques]] | 裁剪技术 — 视锥体、遮挡、Portal 裁剪 | 基础 | 60min |
| 07 | [[07-lod-system]] | LOD 系统 — Mesh/Shader/Texture 层级管理 | 基础 | 45min |
| 08 | [[08-shader-optimization]] | Shader 优化基础 — ALU、采样、精度、变体 | 进阶 | 60min |
| 09 | [[09-texture-optimization]] | 纹理优化 — 压缩、图集、流式加载 | 基础 | 45min |
| 10 | [[10-overdraw-fillrate]] | Overdraw 与填充率优化 | 进阶 | 50min |
| 11 | [[11-lighting-optimization]] | 光照优化 — 烘焙、Light Culling、阴影 | 进阶 | 60min |
| 12 | [[12-post-processing]] | 后处理优化 — 全屏特效的代价与降级 | 进阶 | 45min |

## Phase 3: CPU 优化原理

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 13 | [[13-data-oriented-design]] | 数据导向设计 (DOD) — Cache 与数据布局 | 基础 | 60min |
| 14 | [[14-multithreading]] | 多线程基础 — Job System 与 Task Graph | 进阶 | 60min |
| 15 | [[15-ecs-architecture]] | ECS 架构 — Entity Component System 原理 | 进阶 | 50min |
| 16 | [[16-simd-vectorization]] | SIMD 与向量化入门 | 进阶 | 45min |
| 17 | [[17-spatial-partitioning]] | 算法与数据结构优化 — 空间分割 | 基础 | 60min |

## Phase 4: 内存优化原理

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 18 | [[18-memory-allocation]] | 内存分配策略 — 池/Arena/帧分配器 | 基础 | 50min |
| 19 | [[19-object-pooling]] | 对象池与复用 — 减少分配抖动 | 基础 | 45min |
| 20 | [[20-streaming-async-io]] | 流式加载与异步 IO | 进阶 | 50min |
| 21 | [[21-memory-bandwidth]] | 内存带宽优化 — 压缩与数据布局 | 进阶 | 45min |
| 22 | [[22-gc-avoidance]] | GC 规避策略 — C#/Unity 中的 GC 压力管理 | 进阶 | 50min |

## Phase 5: GPU 深入优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 23 | [[23-gpu-architecture]] | GPU 架构简析 — 并行模型与调度 | 进阶 | 60min |
| 24 | [[24-gpu-bandwidth]] | GPU 带宽优化 — 纹理压缩与 Tiling | 进阶 | 50min |
| 25 | [[25-compute-shader]] | Compute Shader 优化 | 进阶 | 60min |
| 26 | [[26-async-compute]] | Async Compute 与现代 GPU 并行 | 进阶 | 45min |

## Phase 6: Profiling 实战

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 27 | [[27-renderdoc-practice]] | GPU Capture 实战 — RenderDoc 全流程 | 基础 | 60min |
| 28 | [[28-cpu-profiling]] | CPU Profiling 实战 — Tracy/Superluminal | 进阶 | 50min |
| 29 | [[29-auto-perf-testing]] | 自动化性能测试与回归检测 | 进阶 | 45min |

## Phase 7: Unity 引擎优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 30 | [[30-unity-rendering]] | Unity 渲染管线优化 — URP/HDRP 选型 | 基础 | 60min |
| 31 | [[31-unity-job-burst]] | Unity Job System + Burst Compiler | 进阶 | 60min |
| 32 | [[32-unity-memory-addressables]] | Unity 内存管理与 Addressables | 基础 | 50min |
| 33 | [[33-unity-performance-pitfalls]] | Unity 常见性能陷阱 | 基础 | 50min |
| 34 | [[34-unity-dots]] | Unity DOTS 入门 — ECS+Job+Burst | 进阶 | 60min |

## Phase 8: Unreal Engine 优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 35 | [[35-ue-rendering]] | UE 渲染优化 — Nanite/Lumen/VSM | 进阶 | 60min |
| 36 | [[36-ue-threading]] | UE 线程模型与 Task System | 进阶 | 50min |
| 37 | [[37-ue-memory-gc]] | UE 内存管理与 GC | 进阶 | 50min |
| 38 | [[38-ue-profiler]] | UE Profiler 工具链 — Insights, Stat, CSV | 基础 | 60min |
| 39 | [[39-ue-performance-pitfalls]] | UE 常见性能陷阱 | 基础 | 50min |

## Phase 9: 2D 游戏专属优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 40 | [[40-2d-sprite-batching]] | 2D Sprite 合批与图集优化 | 基础 | 45min |
| 41 | [[41-2d-tilemap-streaming]] | 2D Tilemap 与关卡流式加载 | 基础 | 45min |
| 42 | [[42-ui-optimization]] | UI 性能优化 — Canvas/UMG/UIToolkit | 进阶 | 50min |

## Phase 10: 实战综合

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 43 | [[43-case-study-3d]] | 案例研究：3D 场景 30fps→60fps 全流程 | 综合 | 90min |
| 44 | [[44-case-study-2d]] | 案例研究：2D 手游性能调优全流程 | 综合 | 90min |
