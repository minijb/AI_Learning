# Unity DOTS 总览

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 2 小时
> 前置知识: ECS 基本原理（见教程 01-05）、C# 基础

---

## 1. 概念讲解

### 为什么需要 DOTS？

传统的 Unity 开发以 GameObject / MonoBehaviour 为核心，对象拥有自己的数据和行为，通过 `Update()` 逐帧驱动。这种模式在中小规模项目（几百个对象）中运转良好，但当对象数量达到数千甚至上万时，瓶颈显现：

- **托管对象开销**: 每个 GameObject 都是托管堆上的对象，GC 压力巨大。
- **缓存不友好**: 组件散落在堆内存中，CPU 缓存命中率低。
- **单线程限制**: MonoBehaviour 的 `Update()` 在主线程顺序执行，无法利用多核。

Unity DOTS (Data-Oriented Technology Stack) 正是为解决这些问题设计的。它将数据与行为分离，利用连续内存布局和 Burst 编译器，实现数十倍的性能提升。

### DOTS 的四大支柱

```
┌──────────────────────────────────────────────────────┐
│                     Unity DOTS                        │
├────────────┬────────────┬─────────────┬───────────────┤
│  Entities  │   Jobs     │   Burst     │  Collections │
│  (ECS)     │  (并行)    │  (编译器)   │  (数据结构)  │
├────────────┴────────────┴─────────────┴───────────────┤
│              Data-Oriented Design                     │
│         "把数据放在一起，一起处理"                      │
└──────────────────────────────────────────────────────┘
```

1. **Entities** — 纯数据容器。Entity 只是一个整数 ID，组件数据存储在线性数组中。
2. **Jobs System** — C# 多线程框架，让开发者安全地编写并行代码。
3. **Burst Compiler** — 将 C# 子集编译为高度优化的原生代码（LLVM 后端），自动 SIMD 向量化。
4. **Collections** — 非托管数据结构（NativeArray, NativeHashMap 等），可在 Job 中安全使用。

### 范式转换：从 GameObject 到 Entity

| 旧范式 (GameObject) | 新范式 (ECS) |
|---------------------|--------------|
| GameObject 是对象容器 | Entity 只是一个索引 |
| MonoBehaviour 持有数据+行为 | IComponentData 只存数据 |
| MonoBehaviour.Update() 驱动行为 | ISystem / SystemBase 处理逻辑 |
| 组件散落在堆上 | 组件存储在连续 Chunk 中（Archetype） |
| 通过 GetComponent<T>() 访问 | 通过 SystemAPI.Query 遍历 |
| GC 分配频繁 | 几乎零 GC |

**核心思想：** 把"什么数据"和"怎么处理"彻底分开。Entity = 什么样的组件组合（Archetype），System = 对这些组合做什么操作。

### Entities 1.0 架构

Unity 2022 LTS 之后，Entities 进入 1.0 稳定版，架构清晰：

- **World**: 一个隔离的 ECS 世界，可以同时存在多个 World（如客户端 World、服务器 World）。
- **EntityManager**: 管理 Entity 的创建、销毁、组件增删。每个 World 一个。
- **Archetype**: 实体组件类型的唯一组合。相同 Archetype 的 Entity 存储在同一个 Chunk 中。
- **Chunk**: 16KB 的连续内存块，存储同一 Archetype 的多个 Entity 的数据。
- **SystemGroup**: System 的分组容器，定义更新顺序。
- **ISystem / SystemBase**: 系统逻辑的载体。ISystem 是非托管版本（推荐），SystemBase 是托管版本（兼容旧代码）。

### Package 依赖

在 `Packages/manifest.json` 中或通过 Package Manager 添加：

```json
{
  "dependencies": {
    "com.unity.entities": "1.0.16",
    "com.unity.entities.graphics": "1.0.16",
    "com.unity.collections": "2.1.4",
    "com.unity.burst": "1.8.12",
    "com.unity.mathematics": "1.2.6",
    "com.unity.physics": "1.0.16"
  }
}
```

核心包说明：
- `com.unity.entities`: ECS 核心框架（Entity、Component、System、World）
- `com.unity.entities.graphics`: 配合 ECS 的渲染（Entities Graphics）
- `com.unity.collections`: NativeContainer 数据结构
- `com.unity.burst`: Burst 编译器
- `com.unity.mathematics`: `float3`、`quaternion` 等 SIMD 友好的数学类型
- `com.unity.physics`: 基于 ECS 的物理系统（可选）

### 与传统 Unity 开发的共存方式

DOTS 不需要你"全有或全无"。可以：

1. **渐进式迁移**: 在现有项目中创建 SubScene，将一部分 GameObject 转为 Entity。
2. **混合世界**: Unity 自动维护一个"转换世界"——GameObject 在 SubScene 中的数据变更会实时同步到 Entity。
3. **互操作**: 使用 `GameObjectEntity` 让普通 GameObject 也可被 ECS System 查询到。
4. **并行运行**: MonoBehaviour `Update()` 和 ISystem `OnUpdate()` 在同一个 PlayerLoop 中执行，互不阻塞。

---

## 2. 代码示例

### 最小 DOTS 项目：旋转 Cube

这是一个完整的 DOTS 入门项目。效果：一个 Cube 持续绕 Y 轴旋转。

#### 步骤 1: 创建 SubScene

在 Hierarchy 中：右键 → New Sub Scene → Empty Scene。将 Cube（或其他 3D 对象）放入 SubScene。

#### 步骤 2: 定义组件

```csharp
// RotationSpeed.cs
using Unity.Entities;

public struct RotationSpeed : IComponentData
{
    public float RadiansPerSecond;
}
```

#### 步骤 3: 编写 Authoring（将 GameObject 上的数据转为 Entity 组件）

```csharp
// RotationSpeedAuthoring.cs
using Unity.Entities;
using UnityEngine;

public class RotationSpeedAuthoring : MonoBehaviour
{
    public float DegreesPerSecond = 90f;

    class Baker : Baker<RotationSpeedAuthoring>
    {
        public override void Bake(RotationSpeedAuthoring authoring)
        {
            // 获取当前被 Bake 的 Entity
            var entity = GetEntity(TransformUsageFlags.Dynamic);
            
            // 添加组件
            AddComponent(entity, new RotationSpeed
            {
                RadiansPerSecond = math.radians(authoring.DegreesPerSecond)
            });
        }
    }
}
```

#### 步骤 4: 编写 System

```csharp
// RotationSystem.cs
using Unity.Burst;
using Unity.Entities;
using Unity.Mathematics;
using Unity.Transforms;

// ISystem 是非托管的，可以用 Burst 编译
[BurstCompile]
public partial struct RotationSystem : ISystem
{
    [BurstCompile]
    public void OnCreate(ref SystemState state)
    {
        // 要求 World 中至少存在一个带 RotationSpeed 和 LocalTransform 的实体后才运行此 System
        state.RequireForUpdate<RotationSpeed>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state)
    {
        float deltaTime = SystemAPI.Time.DeltaTime;

        // SystemAPI.Query 遍历所有同时拥有 RotationSpeed 和 LocalTransform 的实体
        foreach (var (localTransform, rotationSpeed) in
                 SystemAPI.Query<RefRW<LocalTransform>, RefRO<RotationSpeed>>())
        {
            // 旋转变换
            localTransform.ValueRW = localTransform.ValueRO.RotateY(
                rotationSpeed.ValueRO.RadiansPerSecond * deltaTime
            );
        }
    }

    [BurstCompile]
    public void OnDestroy(ref SystemState state) { }
}
```

#### 步骤 5: 挂载 Authoring

将 `RotationSpeedAuthoring` 脚本挂载到 Cube 上，设置 `DegreesPerSecond = 90`。进入 Play 模式，Cube 开始旋转。

**运行方式:** 在 Unity 2022 LTS+ 中创建项目，通过 Package Manager 安装 Entities、Entities Graphics、Burst、Collections、Mathematics。将上述代码放入 Scripts 文件夹。Hierarchy 中创建 SubScene，放入带有 `RotationSpeedAuthoring` 的 Cube。

**预期效果:** 运行后，Cube 以每秒 90 度的速度绕 Y 轴旋转；通过 SystemAPI.Query 自动批量处理所有符合条件的 Entity。

---

## 3. 练习

### 练习 1: 基础练习 — 多 Cube 不同速度

创建 10 个 Cube，每个设置不同的 `DegreesPerSecond`。观察：
- System 如何在一个循环中处理所有实体
- 修改 `DegreesPerSecond` 值，所有 Cube 的旋转速度独立变化

### 练习 2: 进阶练习 — 添加上下浮动效果

新增一个 `FloatAmplitude` 组件（浮点值），编写 `FloatSystem`，让所有带此组件的实体在 Y 轴上正弦浮动。
- 提示：使用 `LocalTransform.ValueRW.Position.y` 和 `math.sin()`
- 确保 `FloatSystem` 和 `RotationSystem` 在同一 `SimulationSystemGroup` 中正确执行

### 练习 3: 挑战练习（可选） — 自定义 SystemGroup 排序

创建两个自定义 System：`MovementSystem` 和 `BoundaryCheckSystem`。要求 `BoundaryCheckSystem` 在 `MovementSystem` 之后执行（因为需要先移动再检查边界）。
- 提示：使用 `[UpdateAfter(typeof(MovementSystem))]` 特性
- 在 `BoundaryCheckSystem` 中，当实体 Y < -5 时将其 Y 重置为 5

---

## 4. 扩展阅读

- [Unity ECS 官方文档](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/index.html)
- [DOTS 最佳实践](https://unity.com/dots)
- [Entities 1.0 与旧版的主要区别](https://discussions.unity.com/t/entities-1-0-changes/1234567)
- [Unity Mathematics API](https://docs.unity3d.com/Packages/com.unity.mathematics@1.2/manual/index.html)

---

## 常见陷阱

1. **忘记 `RequireForUpdate<T>()`**: 如果没有在 `OnCreate` 中调用 `RequireForUpdate<T>()`，System 会在没有任何符合条件的 Entity 时也运行，浪费 CPU 时间。

2. **Burst 兼容性**: `ISystem` 必须标记 `[BurstCompile]` 才能获得 Burst 加速。`SystemBase` 不支持 Burst（因为它是托管类）。

3. **SubScene 不等于 Prefab**: SubScene 是编辑时和运行时之间的数据转换桥梁；Prefab 是在运行时可以通过 ECB 实例化的模板。

4. **`RefRW<T>` vs `RefRO<T>`**: 需要写入的组件用 `RefRW<T>`，只读的用 `RefRO<T>`。错误使用会导致编译错误或运行时数据竞争（在 Job 中）。

5. **Transform 组件**: ECS 使用 `LocalTransform`（来自 `Unity.Transforms`），不是 `Transform`。需要安装 `com.unity.entities.graphics` 并在 Authoring 中正确设置 `TransformUsageFlags`。

6. **`math.radians`**: Unity Mathematics 提供 SIMD 友好的数学函数，使用 `math.radians()` 而非 `Mathf.Deg2Rad`。
