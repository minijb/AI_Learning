# 教程目录索引

> 游戏性能优化全攻略 — 44 节课，按学习路径排序

---

## Phase 1: 性能思维与测量基础

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 01 | [01-why-optimize.md](01-why-optimize.md) | 为什么要优化 — 性能优化的经济学与时机 | 基础 | 45min |
| 02 | [02-profiling-methodology.md](02-profiling-methodology.md) | 性能测量方法学 — 测量、定位、验证三步法 | 基础 | 60min |
| 03 | [03-profiling-tools.md](03-profiling-tools.md) | Profiling 工具概览 | 基础 | 45min |
| 04 | [04-frame-analysis.md](04-frame-analysis.md) | 帧分析基础 — Frame Timing 与瓶颈识别 | 基础 | 60min |

## Phase 2: 渲染优化原理

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 05 | [05-draw-call-batching.md](05-draw-call-batching.md) | Draw Call 优化 — 合批、实例化、材质合并 | 基础 | 60min |
| 06 | [06-culling-techniques.md](06-culling-techniques.md) | 裁剪技术 — 视锥体、遮挡、Portal 裁剪 | 基础 | 60min |
| 07 | [07-lod-system.md](07-lod-system.md) | LOD 系统 — Mesh/Shader/Texture 层级管理 | 基础 | 45min |
| 08 | [08-shader-optimization.md](08-shader-optimization.md) | Shader 优化基础 — ALU、采样、精度、变体 | 进阶 | 60min |
| 09 | [09-texture-optimization.md](09-texture-optimization.md) | 纹理优化 — 压缩、图集、流式加载 | 基础 | 45min |
| 10 | [10-overdraw-fillrate.md](10-overdraw-fillrate.md) | Overdraw 与填充率优化 | 进阶 | 50min |
| 11 | [11-lighting-optimization.md](11-lighting-optimization.md) | 光照优化 — 烘焙、Light Culling、阴影 | 进阶 | 60min |
| 12 | [12-post-processing.md](12-post-processing.md) | 后处理优化 — 全屏特效的代价与降级 | 进阶 | 45min |

## Phase 3: CPU 优化原理

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 13 | [13-data-oriented-design.md](13-data-oriented-design.md) | 数据导向设计 (DOD) — Cache 与数据布局 | 基础 | 60min |
| 14 | [14-multithreading.md](14-multithreading.md) | 多线程基础 — Job System 与 Task Graph | 进阶 | 60min |
| 15 | [15-ecs-architecture.md](15-ecs-architecture.md) | ECS 架构 — Entity Component System 原理 | 进阶 | 50min |
| 16 | [16-simd-vectorization.md](16-simd-vectorization.md) | SIMD 与向量化入门 | 进阶 | 45min |
| 17 | [17-spatial-partitioning.md](17-spatial-partitioning.md) | 算法与数据结构优化 — 空间分割 | 基础 | 60min |

## Phase 4: 内存优化原理

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 18 | [18-memory-allocation.md](18-memory-allocation.md) | 内存分配策略 — 池/Arena/帧分配器 | 基础 | 50min |
| 19 | [19-object-pooling.md](19-object-pooling.md) | 对象池与复用 — 减少分配抖动 | 基础 | 45min |
| 20 | [20-streaming-async-io.md](20-streaming-async-io.md) | 流式加载与异步 IO | 进阶 | 50min |
| 21 | [21-memory-bandwidth.md](21-memory-bandwidth.md) | 内存带宽优化 — 压缩与数据布局 | 进阶 | 45min |
| 22 | [22-gc-avoidance.md](22-gc-avoidance.md) | GC 规避策略 — C#/Unity 中的 GC 压力管理 | 进阶 | 50min |

## Phase 5: GPU 深入优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 23 | [23-gpu-architecture.md](23-gpu-architecture.md) | GPU 架构简析 — 并行模型与调度 | 进阶 | 60min |
| 24 | [24-gpu-bandwidth.md](24-gpu-bandwidth.md) | GPU 带宽优化 — 纹理压缩与 Tiling | 进阶 | 50min |
| 25 | [25-compute-shader.md](25-compute-shader.md) | Compute Shader 优化 | 进阶 | 60min |
| 26 | [26-async-compute.md](26-async-compute.md) | Async Compute 与现代 GPU 并行 | 进阶 | 45min |

## Phase 6: Profiling 实战

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 27 | [27-renderdoc-practice.md](27-renderdoc-practice.md) | GPU Capture 实战 — RenderDoc 全流程 | 基础 | 60min |
| 28 | [28-cpu-profiling.md](28-cpu-profiling.md) | CPU Profiling 实战 — Tracy/Superluminal | 进阶 | 50min |
| 29 | [29-auto-perf-testing.md](29-auto-perf-testing.md) | 自动化性能测试与回归检测 | 进阶 | 45min |

## Phase 7: Unity 引擎优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 30 | [30-unity-rendering.md](30-unity-rendering.md) | Unity 渲染管线优化 — URP/HDRP 选型 | 基础 | 60min |
| 31 | [31-unity-job-burst.md](31-unity-job-burst.md) | Unity Job System + Burst Compiler | 进阶 | 60min |
| 32 | [32-unity-memory-addressables.md](32-unity-memory-addressables.md) | Unity 内存管理与 Addressables | 基础 | 50min |
| 33 | [33-unity-performance-pitfalls.md](33-unity-performance-pitfalls.md) | Unity 常见性能陷阱 | 基础 | 50min |
| 34 | [34-unity-dots.md](34-unity-dots.md) | Unity DOTS 入门 — ECS+Job+Burst | 进阶 | 60min |

## Phase 8: Unreal Engine 优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 35 | [35-ue-rendering.md](35-ue-rendering.md) | UE 渲染优化 — Nanite/Lumen/VSM | 进阶 | 60min |
| 36 | [36-ue-threading.md](36-ue-threading.md) | UE 线程模型与 Task System | 进阶 | 50min |
| 37 | [37-ue-memory-gc.md](37-ue-memory-gc.md) | UE 内存管理与 GC | 进阶 | 50min |
| 38 | [38-ue-profiler.md](38-ue-profiler.md) | UE Profiler 工具链 — Insights, Stat, CSV | 基础 | 60min |
| 39 | [39-ue-performance-pitfalls.md](39-ue-performance-pitfalls.md) | UE 常见性能陷阱 | 基础 | 50min |

## Phase 9: 2D 游戏专属优化

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 40 | [40-2d-sprite-batching.md](40-2d-sprite-batching.md) | 2D Sprite 合批与图集优化 | 基础 | 45min |
| 41 | [41-2d-tilemap-streaming.md](41-2d-tilemap-streaming.md) | 2D Tilemap 与关卡流式加载 | 基础 | 45min |
| 42 | [42-ui-optimization.md](42-ui-optimization.md) | UI 性能优化 — Canvas/UMG/UIToolkit | 进阶 | 50min |

## Phase 10: 实战综合

| 序号 | 文件 | 标题 | 类型 | 耗时 |
|------|------|------|------|------|
| 43 | [43-case-study-3d.md](43-case-study-3d.md) | 案例研究：3D 场景 30fps→60fps 全流程 | 综合 | 90min |
| 44 | [44-case-study-2d.md](44-case-study-2d.md) | 案例研究：2D 手游性能调优全流程 | 综合 | 90min |
