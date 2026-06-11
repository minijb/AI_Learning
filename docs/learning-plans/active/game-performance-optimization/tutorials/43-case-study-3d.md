---
title: "案例研究：3D 场景 30fps→60fps 全流程"
updated: 2026-06-05
---

# 案例研究：3D 场景 30fps→60fps 全流程

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 90min
> 前置知识: 06-39（渲染/CPU/内存/GPU 全系列 + Unity/UE 引擎优化）

---

## 1. 概念讲解

### 为什么需要这个？

前 39 节课你学到了散落的技术点。本节把它们串联成一个完整的优化闭环——从一个真实性能瓶颈出发，一步步诊断、定位、修复、验证，最终把帧率从 30fps 翻到 60fps。

这不是理论推演，而是一个**可复现的实战案例**。

### 核心思想

性能优化的本质是**识别约束 → 解除约束 → 下一个约束浮出 → 重复**。一个场景从来不是"有一个瓶颈"——它是"有一个当前的瓶颈"。解决它之后，另一个瓶颈会自动顶上来。本案例让你经历这个完整链条。

---

## 2. 案例设定：中世纪市场场景

### 场景描述

- **美术资产**：200+ 静态建筑模块、50+ 角色 NPC（骨骼动画）、100+ 道具装饰、粒子火把/烟雾
- **光照**：1 个方向光（实时阴影）、20+ 点光源（火把）、天光（烘焙+SSAO）
- **后处理**：Bloom、Color Grading、Motion Blur
- **目标平台**：PC（GTX 1660 Super / 1080p）
- **初始帧率**：~28-32fps（不稳定，min 22fps）

### 第一步：不碰任何代码，先测量

```cpp
// 使用 Tracy 框架插桩的帧循环（简化示意）
void GameFrame()
{
    ZoneScoped;  // 自动测量整个帧

    {
        ZoneScopedN("Input");
        ProcessInput();
    }
    {
        ZoneScopedN("Gameplay Update");
        UpdateAI();
        UpdateAnimation();
        UpdatePhysics();  // ← 这里花了 14.2ms！
    }
    {
        ZoneScopedN("Culling");
        FrustumCull();
        OcclusionCull();
    }
    {
        ZoneScopedN("Render Submission");
        SubmitDrawCalls();  // ← 提交了 5,847 个 DC！
    }
    {
        ZoneScopedN("GPU Frame");
        TracyVkCollect;  // Vulkan GPU 时间戳收集
    }
}
```

运行后从 Tracy 得到的数据：

```
Frame time: 33.4ms (avg)
├── Gameplay Update: 19.2ms  ← 🔴 最大块
│   ├── UpdateAnimation: 8.1ms
│   ├── UpdatePhysics: 6.3ms
│   └── UpdateAI: 4.8ms
├── Render Submission: 8.7ms  ← 🔴 第二大块
│   └── 5,847 draw calls
├── Culling: 2.1ms
├── GPU Frame: 14.2ms  ← 渲染耗时（GPU Bound）
│   ├── Shadow Pass: 5.8ms
│   ├── Base Pass: 4.3ms
│   └── Post Process: 3.1ms
└── Input: 0.1ms
```

**诊断结论**：
- CPU 端总计 ~31ms → CPU 严重超标（目标 16.6ms）
- GPU 端 ~14ms → GPU 接近极限（目标 16.6ms）
- 当前是 **CPU Bound**，但解决 CPU 后 GPU 会成为新瓶颈

---

## 3. 优化迭代

### 迭代 1：动画系统优化（-8.1ms → -6.2ms）

**问题定位**：
```
UpdateAnimation 内部 Tracy 细分:
├── BoneTransform: 4.2ms  ← 每帧计算 50 个角色的全部骨骼
├── AnimGraph Eval: 2.1ms
└── BlendSpace: 1.8ms
```

**根因**：所有 NPC 都在进行完全骨骼计算，即使它们离相机 200 米远，屏幕上只有 3 像素。

**修复 — 动画 LOD**：

```cpp
// 动画 LOD 系统：距离越远，更新频率越低，骨骼数越少
struct AnimationLODConfig {
    float distance;
    float updateInterval;  // 秒
    int maxBoneCount;      // 计算骨骼数量上限
};

const AnimationLODConfig g_AnimLODs[] = {
    {  20.0f, 1.0f/60.0f, 64 },  // LOD0: 近处全精度
    {  50.0f, 1.0f/30.0f, 32 },  // LOD1: 中等距离，30fps 更新
    { 100.0f, 1.0f/15.0f, 16 },  // LOD2: 远处，15fps 更新
    { 200.0f, 1.0f/5.0f,   0 },  // LOD3: 极远，停用骨骼（用静态 pose）
};

void AnimationSystem::Update(float dt)
{
    ZoneScopedN("Animation Update (LOD-ed)");

    for (auto& entity : m_AnimatedEntities) {
        float dist = DistanceToCamera(entity.transform);
        int lod = SelectLOD(dist);

        // 时间累积，决定本帧是否更新
        entity.timeAccum += dt;
        if (entity.timeAccum < g_AnimLODs[lod].updateInterval)
            continue;  // 跳过本帧

        entity.timeAccum = 0.0f;

        // 限制骨骼数
        EvaluateSkeleton(entity, g_AnimLODs[lod].maxBoneCount);
    }
}
```

**效果**：
- `UpdateAnimation` 从 8.1ms → 1.9ms（节省 6.2ms）
- 视觉差异：几乎不可察觉——远处角色骨骼减少只影响精度，屏幕 3 像素根本看不出来
- CPU 总耗时：33.4ms → 27.2ms

---

### 迭代 2：物理系统优化（-6.3ms → -5.1ms）

**问题定位**：
```
UpdatePhysics 内部:
├── Cloth Simulation: 2.8ms  ← 🔴 NPC 斗篷布料模拟
├── Rigid Body: 1.5ms
├── Collision Detection: 1.2ms
└── Constraint Solver: 0.8ms
```

**根因**：50 个 NPC 都有布料物理（斗篷），远距离依然在完整模拟。

**修复 — 物理 LOD + 简化碰撞**：

```cpp
void PhysicsSystem::Update(float dt)
{
    ZoneScopedN("Physics Update (Optimized)");

    // Step 1: 远处用简化的碰撞体
    for (auto& body : m_RigidBodies) {
        float dist = DistanceToCamera(body.position);

        if (dist > 80.0f) {
            // 远处：球体替代网格碰撞
            body.collisionType = CollisionType::Sphere;
            body.physicsStepRate = 15;  // 15Hz 更新
        } else {
            body.collisionType = CollisionType::Mesh;
            body.physicsStepRate = 60;
        }
    }

    // Step 2: 布料模拟只在 LOD0/1 启用
    for (auto& cloth : m_ClothComponents) {
        if (DistanceToCamera(cloth.position) > 30.0f)
            continue;  // 远处完全跳过布料
        SimulateCloth(cloth, dt);
    }

    // Step 3: 物理步进用分帧更新
    for (auto& body : m_RigidBodies) {
        body.accumulator += dt;
        while (body.accumulator >= 1.0f / body.physicsStepRate) {
            StepPhysics(body);
            body.accumulator -= 1.0f / body.physicsStepRate;
        }
    }
}
```

**效果**：
- `UpdatePhysics` 从 6.3ms → 1.2ms（节省 5.1ms）
- CPU 总耗时：27.2ms → 22.1ms

---

### 迭代 3：Draw Call 优化（5,847 → 487 DC）

**问题定位**：RenderDoc 抓帧分析：

```
Draw Call 分布:
├── StaticMesh 建筑: 3,200 DC  (材质种类: 45 种)
├── SkeletalMesh NPC: 1,500 DC  (材质种类: 12 种)
├── Particle 火把: 800 DC
├── Decal 贴花: 247 DC
└── UI: 100 DC
```

**根因 1 — 材质种类过多**：45 种建筑材质，大部分只有颜色差异。每个不同材质 = 一次状态切换 = 一个 Draw Call。

**根因 2 — 未使用 GPU Instancing**：大量重复物体（柱子、石砖、木桶）各走各的 Draw Call。

**修复 — 材质合并 + Instancing**：

```cpp
// 材质合并：将所有只有颜色差异的建筑材质合并到一张纹理图集
// + 一个 instance buffer 传递 per-object 颜色

// Before: 45 种材质 → 3,200 DC
// After: 合并为 3 种图集材质 → 配合 instancing

// Instancing 设置（简化）
struct InstanceData {
    float4x4 worldMatrix;
    float4   colorTint;     // 替代材质变体
    float    roughness;     // 替代材质变体
};

void SubmitInstancedGeometry()
{
    ZoneScopedN("Instanced Draw");

    // 按材质+网格分组
    for (auto& [key, group] : m_InstanceGroups) {
        if (group.count == 0) continue;

        // 更新 instance buffer
        UpdateBuffer(group.instanceBuffer, group.instances.data(),
                     group.count * sizeof(InstanceData));

        // 一次 draw call 画全部
        DrawInstanced(group.mesh, group.material,
                      group.count, group.instanceBuffer);
    }
}
```

**效果**：
```
Draw Calls:
├── 建筑（Instanced）:   3,200 → 120 DC
├── NPC（Instanced）:     1,500 → 180 DC
├── 粒子（合并）:         800 → 45 DC
├── Decal（合批）:         247 → 42 DC
└── UI:                    100 → 100 DC
Total: 5,847 → 487 DC  (减少 91.7%)
```

Render Submission 耗时：8.7ms → 1.8ms
CPU 总耗时：22.1ms → 15.2ms ← 终于进入 16.6ms 预算！

---

### 迭代 4：GPU 端优化（面对新瓶颈）

CPU 问题解决后，GPU 暴露为新瓶颈：14.2ms，仍然过高。

RenderDoc GPU 分析：

```
GPU Timeline:
├── Shadow Pass: 5.8ms  ← 🔴 最大块
│   └── 2,048×2,048 shadow map × 4 cascades
├── Base Pass: 4.3ms
│   └── 20+ dynamic point lights
├── Post Process: 3.1ms
│   └── Bloom (full-res): 1.5ms
│   └── SSAO: 1.0ms
└── Other: 1.0ms
```

**修复 1 — 阴影优化**：

```cpp
// 阴影 Cascade 距离和分辨率优化
struct ShadowConfig {
    int   cascadeCount   = 4;     // 从 4 降到 3
    float cascadeDist[3] = {15.0f, 50.0f, 120.0f};  // 紧缩距离
    int   resolutions[3] = {1024, 1024, 512};        // 降低远端分辨率
    float maxShadowDist  = 80.0f; // 80 米外不投影（市场场景够用）
};

// 点光源阴影：只为最近的 3 个点光源渲染阴影
// 远处的火把只发光，不投射阴影
```

**修复 2 — 光照优化（Tiled Forward 裁剪）**：

```hlsl
// Compute Shader: Tiled Light Culling
// 将屏幕分成 16×16 的 tile，每个 tile 只考虑影响它的光源

[numthreads(16, 16, 1)]
void LightCullingCS(uint3 dispatchThreadID : SV_DispatchThreadID,
                    uint3 groupID : SV_GroupID)
{
    // 计算 tile 的 frustum
    Frustum tileFrustum = ComputeTileFrustum(groupID.xy);

    uint lightCount = 0;
    uint lightIndices[MAX_LIGHTS_PER_TILE];

    // 只测试影响此 tile 的光源
    for (uint i = 0; i < totalLightCount; ++i) {
        if (IntersectFrustumSphere(tileFrustum, lights[i].boundingSphere)) {
            lightIndices[lightCount++] = i;
        }
    }

    // 写入 tile 的光源列表
    tileLightLists[groupID.y * tileCountX + groupID.x].count = lightCount;
    // ... store indices
}

// Pixel Shader 端只迭代 tile 内的光源，而非全部 20+
```

**修复 3 — 后处理降分辨率**：

```cpp
// Bloom: 全分辨率 → 半分辨率
SetRenderTarget(bloomRT_HalfRes);  // 960×540
ApplyBloom();                      // 节省 75% 像素着色

// SSAO: 全分辨率 → 半分辨率 + 时域累积
SetRenderTarget(ssaoRT_HalfRes);
ApplySSAO();  // 配合 Temporal filter 消除低分辨率噪点
```

**GPU 效果汇总**：
```
GPU Timeline (After):
├── Shadow Pass: 5.8ms → 2.1ms  (cascade 减少 + 距离限定)
├── Base Pass: 4.3ms → 2.0ms    (Tiled Light Culling)
├── Post Process: 3.1ms → 1.2ms  (半分辨率 Bloom + SSAO)
└── Other: 1.0ms → 0.8ms
Total GPU: 14.2ms → 6.1ms  ✅
```

---

### 迭代 5：最终调优 — 帧分析收尾

```cpp
// Tracy 最终帧分析结果
Frame time: 15.2ms (avg) → 稳定 60fps
├── Gameplay Update: 7.9ms   (从 19.2ms 降)
│   ├── UpdateAnimation: 1.9ms
│   ├── UpdatePhysics: 1.2ms
│   └── UpdateAI: 4.8ms     ← 暂不做（已达标）
├── Render Submission: 1.8ms (从 8.7ms 降)
├── Culling: 2.1ms
├── GPU Frame: 6.1ms        (从 14.2ms 降)
└── Other: 2.4ms

Budget remaining: 1.4ms headroom  ✅
```

**优化效果总览**：

| 优化项 | 操作前 | 操作后 | 节省 |
|--------|--------|--------|------|
| 动画 LOD | 8.1ms | 1.9ms | 6.2ms |
| 物理 LOD | 6.3ms | 1.2ms | 5.1ms |
| Draw Call 合批 | 5,847 DC (8.7ms) | 487 DC (1.8ms) | 6.9ms |
| Shadow 优化 | 5.8ms | 2.1ms | 3.7ms |
| Light Culling | 4.3ms | 2.0ms | 2.3ms |
| 后处理降分辨率 | 3.1ms | 1.2ms | 1.9ms |
| **总计** | **~33ms / 30fps** | **~15ms / 60fps** | **~26ms** |

---

## 4. 练习

### 练习 1: 复现本案例的测量流程

1. 准备一个包含 50+ 骨骼动画角色、大量静态网格、多个动态光源的 3D 场景
2. 集成 Tracy 到你的项目中，为每帧的子系统添加 `ZoneScoped`
3. 截图 Tracy 时间线，标注出 CPU 端前 3 大耗时项
4. 用 RenderDoc 抓一帧，统计 Draw Call 数量和 GPU 各 Pass 耗时

### 练习 2: 实施至少 3 项优化

1. 选择从案例中学习的 3 项优化（例如：动画 LOD + Instancing + Shadow 优化）
2. 在你的场景中实施它们
3. 测量优化前后的帧时间，产出对比表格

### 练习 3: 找到你的第 N 个瓶颈（可选）

1. 将你的场景优化到稳定 60fps
2. 然后提高目标到 120fps
3. 找出新的瓶颈是什么——它是 CPU Bound 还是 GPU Bound？
4. 写一个简短的优化计划：你会怎么修？


## 4.5 参考答案

> [!tip]- 练习 1 参考答案
> **复现测量流程的操作步骤：**
>
> 1. **场景准备**：使用 UE5 的 City Sample 或自行搭建包含 50+ Skeletal Mesh 角色、大量 Static Mesh 建筑、多个动态光源（点光源+聚光灯）的场景。
>
> 2. **集成 Tracy**：
>    ```cpp
>    // 在项目的 Build.cs 中添加 Tracy 依赖
>    // 在 GameMode/Actor 中添加 ZoneScoped
>    #include "Tracy.hpp"
>
>    void AMyGameMode::Tick(float DeltaTime)
>    {
>        ZoneScoped;  // 整个 GameMode Tick 计时
>        Super::Tick(DeltaTime);
>    }
>
>    void UMyAnimationSystem::UpdateAnimation(float DT)
>    {
>        ZoneScopedN("AnimationUpdate");
>        for (auto& Entity : AnimatedEntities)
>        {
>            ZoneScopedN("SingleEntityAnim");
>            EvaluateSkeleton(Entity);
>        }
>    }
>    ```
>
> 3. **Tracy 时间线截图标注**（典型输出）：
>    ```
>    Frame 33.4ms
>    ├── Gameplay Update: 19.2ms  ← CPU #1
>    │   ├── Animation: 8.1ms      ← CPU #2
>    │   ├── Physics: 6.3ms        ← CPU #3
>    │   └── AI: 4.8ms
>    ├── Render Submission: 8.7ms
>    └── GPU Frame: 14.2ms
>    ```
>    前三耗时：Gameplay Update (19.2ms)、Render Submission (8.7ms)、GPU Frame (14.2ms GPU side)
>
> 4. **RenderDoc 抓帧统计**：
>    - 打开 RenderDoc → Launch Application → 选择 UE5 Editor
>    - F12 捕获一帧 → Event Browser 中查看 Draw Call 分布
>    - 统计主分类：
>      ```
>      StaticMesh: 3,200 DC (45 种材质)
>      SkeletalMesh: 1,500 DC (12 种材质)
>      Particles: 800 DC
>      Decals: 247 DC
>      Total: 5,847 DC
>      ```
>    - GPU Timeline (Performance Counter Viewer)：Shadow Pass 5.8ms, Base Pass 4.3ms, Post Process 3.1ms
>
> **验收标准**：能画出类似案例中的帧时间分解图，标注出前 3 大 CPU 耗时和 GPU 各 Pass 耗时。

> [!tip]- 练习 2 参考答案
> **三项优化实施模板：**
>
> ### 优化 1: 动画 LOD（基于距离的骨骼更新频率）
> ```cpp
> // 在 AnimationSystem 中实现
> struct FAnimLODConfig
> {
>     float Distance;
>     float UpdateInterval;  // 秒
>     int32 MaxBoneCount;
> };
>
> static const FAnimLODConfig AnimLODs[] = {
>     {  20.0f, 1.0f/60.0f, 64 },  // LOD0: 近处全精度
>     {  50.0f, 1.0f/30.0f, 32 },  // LOD1: 30fps 更新
>     { 100.0f, 1.0f/15.0f, 16 },  // LOD2: 15fps 更新
>     { 200.0f, 1.0f/5.0f,   0 },  // LOD3: 停用骨骼
> };
>
> void UpdateAnimationLODed(float DT)
> {
>     for (auto& Entity : AnimatedEntities)
>     {
>         float Dist = FVector::Dist(CameraPos, Entity.Transform.GetLocation());
>         int32 LOD = SelectLOD(Dist);
>         Entity.TimeAccum += DT;
>         if (Entity.TimeAccum < AnimLODs[LOD].UpdateInterval)
>             continue;
>         Entity.TimeAccum = 0.0f;
>         EvaluateSkeleton(Entity, AnimLODs[LOD].MaxBoneCount);
>     }
> }
> ```
> 预期：Animation 8.1ms → 1.9ms
>
> ### 优化 2: GPU Instancing（合并相同 Mesh+Material 的绘制）
> ```cpp
> // StaticMesh 建筑：收集所有使用相同 Mesh+Material 的实例
> // 使用 Instance Buffer 一次 Draw Call 绘制全部
> TMap<FMeshMaterialKey, TArray<FTransform>> InstanceGroups;
> for (auto& StaticMesh : SceneStaticMeshes)
> {
>     FMeshMaterialKey Key(StaticMesh.Mesh, StaticMesh.Material);
>     InstanceGroups.FindOrAdd(Key).Add(StaticMesh.Transform);
> }
> for (auto& [Key, Transforms] : InstanceGroups)
> {
>     RHICmdList.DrawPrimitiveInstanced(Key.Mesh, Transforms.Num(),
>         Transforms.GetData());
> }
> ```
> 预期：建筑类 Draw Call 3,200 → 120；Render Submission 8.7ms → 1.8ms
>
> ### 优化 3: Shadow 优化（降低 Cascade 数量 + 分辨率）
> ```cpp
> // 控制台命令或 Console Variable
> r.Shadow.CSM.MaxCascades 2          // 从 4 降到 2
> r.Shadow.MaxResolution 1024         // 从 2048 降到 1024
> r.Shadow.CachedShadows 1            // 启用阴影缓存（静态物体不每帧渲染阴影）
> r.Shadow.DistanceScale 0.7          // 阴影距离缩小到 70%
> ```
> 预期：Shadow Pass 5.8ms → 2.1ms
>
> **优化前后对比表**：
>
> | 优化项 | 操作前 | 操作后 | 节省 |
> |--------|--------|--------|------|
> | 动画 LOD | 8.1ms | 1.9ms | 6.2ms |
> | GPU Instancing | 5,847 DC / 8.7ms | 487 DC / 1.8ms | 6.9ms |
> | Shadow 优化 | 5.8ms | 2.1ms | 3.7ms |
> | **总计** | **~33ms** | **~15ms** | **~18ms** |

> [!tip]- 练习 3 参考答案（可选）
> **120fps 场景瓶颈分析：**
>
> 1. **将场景优化到 60fps**（~15ms/frame）后，提高目标到 120fps（~8.3ms/frame）。
>
> 2. **找出新瓶颈的方法**：
>    - 重新运行 Tracy：所有耗时 > 1ms 的子系统都是候选
>    - 典型 120fps 场景的新瓶颈分布：
>      ```
>      Frame 8.3ms budget
>      ├── Culling: 2.1ms         ← 🔴 占比 25%，新瓶颈
>      ├── Render Submission: 1.8ms
>      ├── GPU Frame: 6.1ms       ← 🔴 接近极限
>      └── Gameplay Update: 5.5ms
>      ```
>
> 3. **瓶颈类型判定**：
>    - Culling 2.1ms 接近 CPU 预算 → **CPU Bound**（CPU 侧剔除算法太慢）
>    - GPU 6.1ms < 8.3ms → GPU 有 2.2ms 余量
>
> 4. **优化计划**：
>    ```
>    优先级 1: Culling 优化（预计节省 1.2ms）
>      - 使用空间哈希/八叉树替代线性遍历
>      - 启用 GPU Occlusion Culling（将部分剔除工作移到 GPU）
>      - 粗粒度 LOD 剔除（远处物体用更松的包围盒批量剔除）
>
>    优先级 2: GPU 端为 120fps 做准备（预计节省 2ms）
>      - 降低后处理分辨率（Upscaling）
>      - Shader 复杂度审查（移除不必要的指令）
>      - 考虑使用 Variable Rate Shading
>
>    优先级 3: 如果前两项不够，降低视觉保真度
>      - 将目标锁定在 90fps 作为妥协（VR/高刷显示器的 sweet spot）
>      ```

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 5. 扩展阅读

- [GPUOpen — Performance Profiling with RenderDoc](https://gpuopen.com/learn/renderdoc-tutorial/)
- [Tracy Profiler Manual](https://github.com/wolfpld/tracy/releases/latest/download/tracy.pdf)
- [EA — Frostbite Frame Analysis (GDC)](https://www.gdcvault.com/)
- [Naughty Dog — Parallelizing the Naughty Dog Engine](https://www.gdcvault.com/play/1021922/)
- [Ubisoft — Practical Optimization for Console Games](https://www.gdcvault.com/)

---

## 常见陷阱

- **过早优化**：案例中先测量再优化，没有一步是拍脑袋做的。如果不先看 Tracy 数据就动手优化动画系统，可能浪费几小时在根本不成瓶颈的模块上
- **一次性改太多**：每次只改一个变量，测量效果后再改下一个。一次改 5 样，你不知道哪样起效了、哪样引入了新的性能退化
- **优化完不验证**：每次修改后必须重新抓帧确认效果。"我觉得快多了"不是测量。Tracy/RenderDoc 的每次运行都会给出硬数据
- **忽略 headroom**：优化到 60fps 刚好达标就停止 → 后续内容增加时帧率又会掉。至少留 2-3ms 余量
- **GPU Bound 时优化 CPU**：反过来也一样。先确认瓶颈在哪一端，再动手
