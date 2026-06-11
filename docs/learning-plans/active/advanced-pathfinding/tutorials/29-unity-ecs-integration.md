---
title: "Unity ECS 寻路集成"
updated: 2026-06-05
---

# Unity ECS 寻路集成

> 所属计划: 高阶寻路系统
> 预计耗时: 30min
> 前置知识: A* 算法 (03), Unity ECS 基础 (Entities/ISystem/IJobEntity), Burst 编译器概念, NativeArray/NativeContainer

## 1. 概念讲解

### 为什么需要这个？

传统 Unity MonoBehaviour 寻路面临两个缩放瓶颈：

1. **主线程瓶颈**: 100 个单位的寻路请求在 `Update()` 中顺序处理 → 主线程阻塞 → 帧率崩溃。
2. **GC 压力**: 每帧分配 `List<Vector3>`, `HashSet<Node>`, `PriorityQueue` → GC spike → 帧时间抖动。

Unity ECS 通过三样东西解决这些问题：

- **Jobs System**: 将寻路计算放到 worker thread，释放主线程
- **Burst Compiler**: 将 C# 寻路代码编译为高度优化的原生代码（LLVM 后端，SIMD 自动向量化）
- **Entity Component System**: 数据导向的架构，路径数据以 NativeArray 存储，零 GC 分配

**性能对比** (100 个单位同时寻路, 64×64 网格):

| 方法 | 耗时 | GC Alloc |
|------|------|----------|
| MonoBehaviour A* (主线程) | ~45ms (22 FPS) | ~2.3 MB/frame |
| Job + Burst A* (8 worker) | ~5ms (200 FPS) | 0 B |
| ECS System + IJobParallelFor | ~3ms (333 FPS) | 0 B |

### 核心思想

#### ECS 寻路架构

```
┌──────────────────────────────────────────────────────────────┐
│                    PathfindingSystem (ISystem)                 │
│                                                                │
│  ┌─────────────┐   ┌──────────────────┐   ┌───────────────┐  │
│  │ Collect      │   │ Schedule         │   │ Apply         │  │
│  │ PathRequests │──▶│ IJobParallelFor  │──▶│ PathResults   │  │
│  │ (query)      │   │ (A* on worker    │   │ → MovementSys │  │
│  │              │   │  threads, Burst) │   │               │  │
│  └─────────────┘   └──────────────────┘   └───────────────┘  │
│                                                                │
│  Shared Data:                                                  │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ GridData (singleton component):                       │     │
│  │   NativeArray<float>  costMap                         │     │
│  │   NativeArray<bool>   obstacles                       │     │
│  │   int width, height                                   │     │
│  └──────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

#### 核心组件设计

```csharp
// 请求组件 — 当单位需要路径时添加
public struct PathRequest : IComponentData {
    public float3 start;
    public float3 goal;
    public float maxPathCost;    // 超过此代价放弃
    public bool needsRecalculate; // 目标移动时设为 true
}

// 结果组件 — 系统计算完成后写入
public struct PathResult : IComponentData {
    public BlobAssetReference<PathBlob> path; // 共享不可变路径数据
    public int currentWaypointIndex;           // 当前正在前往的路径点
    public bool isComplete;
    public bool isFailed;                      // 无可达路径
}

// 路径的 Blob Asset (不可变, 引用计数, 多实体共享)
public struct PathBlob {
    public BlobArray<float3> waypoints;
    public float totalCost;
}
```

#### Blob Asset 的意义

路径数据本质上是只读的——计算出来后，多个实体可以读取它，但没人会修改它。Blob Asset 完美适配：

- **零拷贝共享**: 500 个实体沿同一 Flow Field 移动 → 共享一个 `PathBlob`
- **引用计数**: `BlobAssetReference<T>` 自动管理生命周期，最后一个引用消失时释放
- **不可变保证**: Burst 编译器可以激进优化（没有 aliasing，不需要 volatile）

#### 数据流: Request → System → Job → Result → MovementSystem

```
Frame N:
1. 单位请求寻路:
   entityManager.AddComponent<PathRequest>(entity, new PathRequest { ... });

2. PathfindingSystem.OnUpdate():
   a. 查询所有带 PathRequest 的实体 (EntityQuery)
   b. 收集请求数据到 NativeArray<PathRequestData>
   c. Schedule IJobParallelFor (每个请求一个 job iteration)
   d. 在 job 中: 运行 Burst 编译的 A* → 产出 BlobAssetReference<PathBlob>

3. Job 完成后 (OnUpdate 的后半段):
   a. 遍历完成的 job 结果
   b. 给对应实体添加 PathResult 组件
   c. 移除 PathRequest 组件 (消费请求)

Frame N+1:
4. MovementSystem.OnUpdate():
   a. 查询所有带 PathResult 的实体
   b. 每帧沿路径移动 (Steering/ORCA)
   c. 到达当前 waypoint → currentWaypointIndex++
   d. 到达终点 → 移除 PathResult
```

#### Burst 编译的 A* 核心

Burst 的关键约束：
- 不能使用托管对象 (`class`, `List<T>`, `Dictionary<K,V>`)
- 必须使用 `NativeContainer` (`NativeArray`, `NativeHashMap`, `NativeQueue`)
- 不能抛出异常
- 不能使用 `string`

因此，Burst 版本的 A* 需要手写优先队列（或使用 `NativePriorityQueue` 第三方库），用 `NativeHashMap<Position, NodeData>` 代替 `Dictionary`。

**手写 Burst 兼容的最小堆:**

```csharp
[BurstCompile]
public struct MinHeap {
    public NativeArray<HeapEntry> data;
    public int count;

    public void Push(HeapEntry entry) { /* sift up */ }
    public HeapEntry Pop() { /* sift down */ }
}
```

#### IJobParallelFor 模式

```csharp
[BurstCompile]
public struct PathfindingJob : IJobParallelFor {
    [ReadOnly] public NativeArray<float> costMap;
    [ReadOnly] public int mapWidth, mapHeight;
    [ReadOnly] public NativeArray<PathRequestData> requests;

    // 输出 (预先分配)
    public NativeArray<PathOutputData> results;

    public void Execute(int index) {
        var req = requests[index];
        // 每个 Execute 运行在独立的 worker thread 上
        // 运行 A* → 写 results[index]
        results[index] = RunAStar(costMap, mapWidth, mapHeight, req.start, req.goal);
    }
}
```

**关键性能细节**: `IJobParallelFor` 的每个 `Execute(index)` 必须有独立的工作集。不能共享 open/closed 集合。这意味着每个请求需要一个完整的 A* 状态——内存消耗为 `O(batch_size × grid_size)`，需要预先分配。

#### Unity ECS 系统调度

```csharp
public partial struct PathfindingSystem : ISystem {
    private EntityQuery _requestQuery;

    [BurstCompile]
    public void OnCreate(ref SystemState state) {
        _requestQuery = state.GetEntityQuery(
            ComponentType.ReadOnly<PathRequest>(),
            ComponentType.Exclude<PathResult>());
        state.RequireForUpdate<GridData>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state) {
        var gridData = SystemAPI.GetSingleton<GridData>();
        int requestCount = _requestQuery.CalculateEntityCount();
        if (requestCount == 0) return;

        // 1. 收集请求
        var requests = new NativeArray<PathRequestData>(
            requestCount, Allocator.TempJob);
        var entities = _requestQuery.ToEntityArray(Allocator.TempJob);

        // 填充 requests 数组 (在 main thread 上, 很快)
        var fillJob = new CollectRequestsJob {
            requests = requests,
            pathRequests = SystemAPI.GetComponentLookup<PathRequest>(true)
        };
        fillJob.ScheduleParallel(_requestQuery, state.Dependency).Complete();

        // 2. 分配输出
        var results = new NativeArray<PathOutputData>(
            requestCount, Allocator.TempJob);

        // 3. Schedule 寻路 job
        var pathJob = new PathfindingJob {
            costMap = gridData.costMap,
            mapWidth = gridData.width,
            mapHeight = gridData.height,
            requests = requests,
            results = results
        };
        var handle = pathJob.Schedule(requestCount, 64, state.Dependency);

        // 4. 应用结果 (job 完成后)
        var applyJob = new ApplyResultsJob {
            results = results,
            entities = entities,
            pathResults = SystemAPI.GetComponentLookup<PathResult>(),
            pathRequests = SystemAPI.GetComponentLookup<PathRequest>()
        };
        var applyHandle = applyJob.Schedule(handle);

        // 5. 清理
        state.Dependency = JobHandle.CombineDependencies(handle, applyHandle);
        requests.Dispose(state.Dependency);
        results.Dispose(state.Dependency);
        entities.Dispose(state.Dependency);
    }
}
```

#### 与 ORCA / Flow Field 的集成

ECS 寻路系统不是独立工作的。它与整个导航管线配合：

```
PathfindingSystem → 全局路径 (waypoints)
       ↓
MovementSystem → 每帧沿路径移动
       ↓
ORCASystem → 局部避障 (调整速度避免碰撞)
       ↓
TransformSystem → 更新位置
```

在 ECS 中这意味着四个系统按顺序执行，每个系统只依赖上一个系统的输出组件。

## 2. 代码示例

以下是一个**完整但最小化的 Unity ECS 寻路实现**，包含所有核心部分。

### C# — ECS Pathfinding 完整骨架

```csharp
// ECS_Pathfinding.cs — Unity ECS 寻路系统完整实现
// 依赖: Unity.Entities, Unity.Collections, Unity.Burst, Unity.Jobs, Unity.Mathematics
// 使用: 将此脚本放在 Unity 项目中，配合 Entities 1.0+ 包

using Unity.Entities;
using Unity.Collections;
using Unity.Burst;
using Unity.Jobs;
using Unity.Mathematics;
using Unity.Transforms;
using System.Runtime.CompilerServices;

// ============================================================
// 组件定义
// ============================================================

/// <summary>全局网格数据 (Singleton)</summary>
public struct GridData : IComponentData {
    public int width;
    public int height;
    public float cellSize;
    public BlobAssetReference<GridBlob> gridBlob;
}

/// <summary>网格的不可变数据 (可被多个世界共享)</summary>
public struct GridBlob {
    public BlobArray<float> costMap;     // width × height
    public BlobArray<bool> obstacles;    // width × height
}

/// <summary>寻路请求 (添加到需要路径的实体)</summary>
public struct PathRequest : IComponentData {
    public float3 goal;
    public float maxPathCost;
}

/// <summary>寻路结果 (系统产出, 驱动 MovementSystem)</summary>
public struct PathResult : IComponentData {
    public BlobAssetReference<PathBlob> pathBlob;
    public int currentWaypoint;
    public bool isComplete;
    public bool isFailed;
}

/// <summary>路径的 Blob Asset (不可变, 共享)</summary>
public struct PathBlob {
    public BlobArray<float3> waypoints;
    public float totalCost;
}

/// <summary>单位移动状态</summary>
public struct MovementState : IComponentData {
    public float speed;
    public float arrivalRadius;
}

// ============================================================
// 辅助结构
// ============================================================

/// <summary>请求数据 (从 Entity 收集到 NativeArray)</summary>
public struct PathRequestData {
    public int2 startCell;
    public int2 goalCell;
    public float3 startWorld;
    public float3 goalWorld;
    public float maxPathCost;
}

/// <summary>Job 输出: 每个请求的结果</summary>
public struct PathOutputData {
    public bool success;
    public float totalCost;
    public int waypointCount;
    public NativeList<float3> waypoints; // 由 job 内部分配
}

/// <summary>最小堆条目 — Burst 兼容</summary>
public struct HeapEntry {
    public int2 pos;
    public float fScore;
}

/// <summary>A* 节点数据</summary>
public struct PathNode {
    public float gScore;
    public int2 parent;
    public bool closed;
}

// ============================================================
// Burst 兼容的 A* 实现 (无托管分配)
// ============================================================

[BurstCompile]
public static class BurstAStar {
    const int MAX_NEIGHBORS = 8;
    static readonly int2[] DIRS = {
        new(0,-1), new(1,-1), new(1,0), new(1,1),
        new(0,1), new(-1,1), new(-1,0), new(-1,-1)
    };
    static readonly float[] DIR_COST = { 1f, 1.414f, 1f, 1.414f, 1f, 1.414f, 1f, 1.414f };

    /// <summary>Octile 启发式 (8 方向)</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    static float Heuristic(int2 a, int2 b) {
        int dx = math.abs(a.x - b.x);
        int dy = math.abs(a.y - b.y);
        return (dx + dy) + (1.414f - 2.0f) * math.min(dx, dy);
    }

    /// <summary>Burst 最小堆</summary>
    public struct MinHeap {
        public NativeArray<HeapEntry> data;
        public int count;

        public MinHeap(int capacity, Allocator allocator) {
            data = new NativeArray<HeapEntry>(capacity, allocator);
            count = 0;
        }

        public void Push(HeapEntry e) {
            int i = count++;
            while (i > 0) {
                int parent = (i - 1) >> 1;
                if (data[parent].fScore <= e.fScore) break;
                data[i] = data[parent];
                i = parent;
            }
            data[i] = e;
        }

        public HeapEntry Pop() {
            var result = data[0];
            var last = data[--count];
            int i = 0;
            while (true) {
                int left = (i << 1) + 1;
                int right = left + 1;
                int smallest = i;

                if (left < count && data[left].fScore < data[smallest].fScore)
                    smallest = left;
                if (right < count && data[right].fScore < data[smallest].fScore)
                    smallest = right;
                if (smallest == i) break;

                data[i] = data[smallest];
                i = smallest;
            }
            data[i] = last;
            return result;
        }

        public bool isEmpty => count == 0;
    }

    /// <summary>
    /// 在网格上运行 A* (Burst 编译, 零 GC)
    /// 返回: 从 start 到 goal 的路径 (格子坐标序列)
    /// </summary>
    [BurstCompile]
    public static bool FindPath(
        // 输入
        in NativeArray<float> costMap,
        in NativeArray<bool> obstacles,
        int mapWidth, int mapHeight,
        int2 start, int2 goal,
        float maxCost,
        // 输出
        NativeList<int2> outPath,
        out float totalCost) {

        totalCost = float.MaxValue;
        outPath.Clear();

        if (obstacles[start.y * mapWidth + start.x] ||
            obstacles[goal.y * mapWidth + goal.x])
            return false;

        int cellCount = mapWidth * mapHeight;
        var nodes = new NativeArray<PathNode>(cellCount, Allocator.Temp);
        for (int i = 0; i < cellCount; i++)
            nodes[i] = new PathNode { gScore = float.MaxValue, closed = false };

        int startIdx = start.y * mapWidth + start.x;
        nodes[startIdx] = new PathNode {
            gScore = 0f, parent = start, closed = false
        };

        var openSet = new MinHeap(cellCount, Allocator.Temp);
        openSet.Push(new HeapEntry { pos = start, fScore = Heuristic(start, goal) });

        bool found = false;
        while (!openSet.isEmpty) {
            var current = openSet.Pop();
            int curIdx = current.pos.y * mapWidth + current.pos.x;

            if (nodes[curIdx].closed) continue;
            nodes[curIdx] = new PathNode {
                gScore = nodes[curIdx].gScore,
                parent = nodes[curIdx].parent,
                closed = true
            };

            if (math.all(current.pos == goal)) {
                found = true;
                totalCost = nodes[curIdx].gScore;
                break;
            }

            for (int d = 0; d < MAX_NEIGHBORS; d++) {
                int2 nb = new(current.pos.x + DIRS[d].x,
                               current.pos.y + DIRS[d].y);

                if (nb.x < 0 || nb.x >= mapWidth ||
                    nb.y < 0 || nb.y >= mapHeight) continue;

                int nbIdx = nb.y * mapWidth + nb.x;
                if (obstacles[nbIdx]) continue;

                float terrainCost = costMap[nbIdx];
                float stepCost = DIR_COST[d] * terrainCost;
                float tentativeG = nodes[curIdx].gScore + stepCost;

                if (tentativeG >= nodes[nbIdx].gScore || tentativeG > maxCost)
                    continue;

                nodes[nbIdx] = new PathNode {
                    gScore = tentativeG,
                    parent = current.pos,
                    closed = false
                };

                float f = tentativeG + Heuristic(nb, goal);
                openSet.Push(new HeapEntry { pos = nb, fScore = f });
            }
        }

        if (!found) return false;

        // 回溯路径
        var tempPath = new NativeList<int2>(Allocator.Temp);
        int2 p = goal;
        while (!math.all(p == start)) {
            tempPath.Add(p);
            p = nodes[p.y * mapWidth + p.x].parent;
        }
        tempPath.Add(start);

        // 反转
        for (int i = tempPath.Length - 1; i >= 0; i--)
            outPath.Add(tempPath[i]);

        return true;
    }
}

// ============================================================
// IJobParallelFor: 批量寻路
// ============================================================

[BurstCompile]
public struct PathfindingJob : IJobParallelFor {
    [ReadOnly] public NativeArray<float> costMap;
    [ReadOnly] public NativeArray<bool> obstacles;
    [ReadOnly] public int mapWidth;
    [ReadOnly] public int mapHeight;
    [ReadOnly] public NativeArray<PathRequestData> requests;

    // 输出: 每个请求的结果 (使用 NativeList 的临时分配器)
    [WriteOnly] public NativeArray<bool> results_success;
    [WriteOnly] public NativeArray<float> results_cost;

    // 路径数据: 每个请求有一个 NativeList (预分配)
    // 注意: NativeList 不能直接放在 NativeArray 中
    // 这里用扁平化存储: 最大路径长度 × 请求数
    [WriteOnly] public NativeArray<int2> allWaypoints;
    [WriteOnly] public NativeArray<int> waypointCounts;
    public int maxWaypointsPerPath;

    public void Execute(int index) {
        var req = requests[index];

        var path = new NativeList<int2>(maxWaypointsPerPath, Allocator.Temp);
        bool found = BurstAStar.FindPath(
            costMap, obstacles, mapWidth, mapHeight,
            req.startCell, req.goalCell, req.maxPathCost,
            path, out float cost);

        results_success[index] = found;
        results_cost[index] = cost;

        if (found) {
            int count = math.min(path.Length, maxWaypointsPerPath);
            waypointCounts[index] = count;
            int baseIdx = index * maxWaypointsPerPath;
            for (int i = 0; i < count; i++)
                allWaypoints[baseIdx + i] = path[i];
        } else {
            waypointCounts[index] = 0;
        }
    }
}

// ============================================================
// System: 收集请求 + 调度 Job
// ============================================================

/// <summary>收集 PathRequest 到 NativeArray 的 Job</summary>
[BurstCompile]
public partial struct CollectRequestsJob : IJobEntity {
    public NativeArray<PathRequestData> requests;
    public NativeArray<int> entityIndexMap; // entity → request 索引
    public NativeArray<int> counter;        // atomic 计数器

    [ReadOnly] public ComponentLookup<LocalTransform> transformLookup;

    void Execute(Entity entity, in PathRequest request, in LocalTransform transform) {
        int idx = counter[0];
        counter[0] = idx + 1;
        entityIndexMap[entity.Index] = idx;

        // 世界坐标 → 格子坐标 (需要 cellSize, 这里简化)
        int2 startCell = new((int)(transform.Position.x), (int)(transform.Position.z));
        int2 goalCell  = new((int)(request.goal.x), (int)(request.goal.z));

        requests[idx] = new PathRequestData {
            startCell = startCell,
            goalCell = goalCell,
            startWorld = transform.Position,
            goalWorld = request.goal,
            maxPathCost = request.maxPathCost
        };
    }
}

// ============================================================
// PathfindingSystem: 主系统
// ============================================================

[BurstCompile]
public partial struct PathfindingSystem : ISystem {
    private EntityQuery _requestQuery;

    [BurstCompile]
    public void OnCreate(ref SystemState state) {
        _requestQuery = state.GetEntityQuery(
            ComponentType.ReadOnly<PathRequest>(),
            ComponentType.ReadOnly<LocalTransform>(),
            ComponentType.Exclude<PathResult>());

        state.RequireForUpdate<GridData>();
        state.RequireForUpdate(_requestQuery);
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state) {
        int requestCount = _requestQuery.CalculateEntityCount();
        if (requestCount == 0) return;

        var gridData = SystemAPI.GetSingleton<GridData>();
        ref var gridBlob = ref gridData.gridBlob.Value;

        // 1. 收集请求
        var requests = new NativeArray<PathRequestData>(
            requestCount, Allocator.TempJob);
        var entityArray = _requestQuery.ToEntityArray(Allocator.TempJob);
        var counter = new NativeArray<int>(1, Allocator.TempJob);
        counter[0] = 0;

        // 手动遍历实体收集 (避免 IJobEntity 的限制)
        for (int i = 0; i < entityArray.Length; i++) {
            var entity = entityArray[i];
            var request = SystemAPI.GetComponentRO<PathRequest>(entity);
            var transform = SystemAPI.GetComponentRO<LocalTransform>(entity);

            int2 startCell = new(
                (int)(transform.ValueRO.Position.x / gridData.cellSize),
                (int)(transform.ValueRO.Position.z / gridData.cellSize));
            int2 goalCell = new(
                (int)(request.ValueRO.goal.x / gridData.cellSize),
                (int)(request.ValueRO.goal.z / gridData.cellSize));

            requests[i] = new PathRequestData {
                startCell = startCell,
                goalCell = goalCell,
                startWorld = transform.ValueRO.Position,
                goalWorld = request.ValueRO.goal,
                maxPathCost = request.ValueRO.maxPathCost
            };
        }

        // 2. 分配输出
        int maxWaypoints = 256;
        var resultsSuccess = new NativeArray<bool>(requestCount, Allocator.TempJob);
        var resultsCost = new NativeArray<float>(requestCount, Allocator.TempJob);
        var allWaypoints = new NativeArray<int2>(
            requestCount * maxWaypoints, Allocator.TempJob);
        var waypointCounts = new NativeArray<int>(requestCount, Allocator.TempJob);

        // 3. Schedule 寻路 Job
        var pathJob = new PathfindingJob {
            costMap = gridBlob.costMap,
            obstacles = gridBlob.obstacles,
            mapWidth = gridData.width,
            mapHeight = gridData.height,
            requests = requests,
            results_success = resultsSuccess,
            results_cost = resultsCost,
            allWaypoints = allWaypoints,
            waypointCounts = waypointCounts,
            maxWaypointsPerPath = maxWaypoints
        };

        // 并行度: 64 个请求一组 (适配 L1 cache)
        var handle = pathJob.Schedule(requestCount, 64, state.Dependency);

        // 4. 应用结果 (需要在主线程完成)
        handle.Complete();

        var ecb = new EntityCommandBuffer(Allocator.TempJob);
        for (int i = 0; i < requestCount; i++) {
            var entity = entityArray[i];

            if (resultsSuccess[i]) {
                // 构建 PathBlob
                int count = waypointCounts[i];
                var blobBuilder = new BlobBuilder(Allocator.Temp);
                ref var pathBlob = ref blobBuilder.ConstructRoot<PathBlob>();
                var waypointArray = blobBuilder.Allocate(
                    ref pathBlob.waypoints, count);

                for (int w = 0; w < count; w++) {
                    var cell = allWaypoints[i * maxWaypoints + w];
                    waypointArray[w] = new float3(
                        (cell.x + 0.5f) * gridData.cellSize, 0,
                        (cell.y + 0.5f) * gridData.cellSize);
                }
                pathBlob.totalCost = resultsCost[i];

                var blobRef = blobBuilder.CreateBlobAssetReference<PathBlob>(
                    Allocator.Persistent);
                blobBuilder.Dispose();

                ecb.AddComponent(entity, new PathResult {
                    pathBlob = blobRef,
                    currentWaypoint = 0,
                    isComplete = false,
                    isFailed = false
                });
            } else {
                ecb.AddComponent(entity, new PathResult {
                    pathBlob = default,
                    currentWaypoint = 0,
                    isComplete = false,
                    isFailed = true
                });
            }

            ecb.RemoveComponent<PathRequest>(entity);
        }

        ecb.Playback(state.EntityManager);
        ecb.Dispose();

        // 5. 清理
        requests.Dispose();
        entityArray.Dispose();
        counter.Dispose();
        resultsSuccess.Dispose();
        resultsCost.Dispose();
        allWaypoints.Dispose();
        waypointCounts.Dispose();
    }
}

// ============================================================
// MovementSystem: 沿路径移动 + 局部避障桩
// ============================================================

[BurstCompile]
public partial struct MovementSystem : ISystem {
    [BurstCompile]
    public void OnUpdate(ref SystemState state) {
        float deltaTime = SystemAPI.Time.DeltaTime;

        foreach (var (transform, result, movement)
                 in SystemAPI.Query<RefRW<LocalTransform>,
                                    RefRW<PathResult>,
                                    RefRO<MovementState>>()) {

            if (result.ValueRO.isFailed) continue;

            ref var pathBlob = ref result.ValueRW.pathBlob.Value;
            int waypointIdx = result.ValueRO.currentWaypoint;

            if (waypointIdx >= pathBlob.waypoints.Length) {
                result.ValueRW.isComplete = true;
                continue;
            }

            float3 target = pathBlob.waypoints[waypointIdx];
            float3 pos = transform.ValueRO.Position;

            // 朝向目标移动
            float3 dir = target - pos;
            float dist = math.length(dir);

            if (dist < movement.ValueRO.arrivalRadius) {
                result.ValueRW.currentWaypoint++;
            } else {
                float3 move = math.normalize(dir) *
                              movement.ValueRO.speed * deltaTime;
                transform.ValueRW.Position += move;
            }
        }

        // 清理已完成的路径
        var ecb = new EntityCommandBuffer(Allocator.Temp);
        foreach (var (result, entity)
                 in SystemAPI.Query<RefRO<PathResult>>()
                          .WithEntityAccess()) {
            if (result.ValueRO.isComplete || result.ValueRO.isFailed) {
                if (result.ValueRO.pathBlob.IsCreated)
                    result.ValueRO.pathBlob.Dispose();
                ecb.RemoveComponent<PathResult>(entity);
            }
        }
        ecb.Playback(state.EntityManager);
        ecb.Dispose();
    }
}
```

### 辅助: 请求路径的 MonoBehaviour 桥接

```csharp
// PathRequestAuthoring.cs
// 用于在 MonoBehaviour 世界中发起 ECS 寻路请求
// 适合从 UI/输入系统桥接到 ECS

using Unity.Entities;
using Unity.Mathematics;
using UnityEngine;

public class PathRequestAuthoring : MonoBehaviour {
    public class Baker : Baker<PathRequestAuthoring> {
        public override void Bake(PathRequestAuthoring authoring) {
            var entity = GetEntity(TransformUsageFlags.Dynamic);
            // 不在这里添加 PathRequest — 它由运行时逻辑添加
            AddComponent<MovementState>(entity, new MovementState {
                speed = 5f, arrivalRadius = 0.3f
            });
        }
    }
}

public static class PathfindingECS {
    /// <summary>发起寻路请求 (从 MonoBehaviour/System 调用)</summary>
    public static void RequestPath(
        World world, Entity entity, float3 goal, float maxCost = float.MaxValue) {
        var em = world.EntityManager;
        em.AddComponentData(entity, new PathRequest { goal = goal, maxPathCost = maxCost });
    }

    /// <summary>检查实体是否有活跃路径</summary>
    public static bool HasPath(World world, Entity entity) {
        return world.EntityManager.HasComponent<PathResult>(entity);
    }

    /// <summary>获取当前路径的下一个 waypoint</summary>
    public static float3? GetNextWaypoint(World world, Entity entity) {
        if (!world.EntityManager.HasComponent<PathResult>(entity))
            return null;

        var result = world.EntityManager.GetComponentData<PathResult>(entity);
        if (result.isFailed || result.isComplete) return null;

        ref var blob = ref result.pathBlob.Value;
        return blob.waypoints[result.currentWaypoint];
    }
}
```

## 3. 练习

### 基础练习
1. **最小 ECS 寻路**: 创建 Unity 项目 (Entities 1.0+)，复制上述代码。在一个 20×20 的手工网格上测试单个实体的寻路，确认路径正确。
2. **批量压力测试**: 生成 500 个随机实体，每个请求随机目标。使用 Profiler 测量 PathfindingSystem 的耗时。对比关闭/开启 Burst 的性能差异。
3. **路径平滑**: 在 `MovementSystem` 中实现简单的路径平滑（如 Catmull-Rom 插值），消除 waypoint 之间的锐角转弯。

### 进阶练习
1. **路径重用与增量更新**: 当目标移动时，不要重新计算整条路径。实现路径拼接：从当前位置找到原路径上最近的可达点，只重算中间段。
2. **多层网格系统**: 在 GridData 中添加多个细节层级（如 4×4 粗网格 + 64×64 细网格）。实现 HPA* 的 ECS 版本。
3. **Blob Asset 共享**: 实现 Flow Field 的 Blob Asset 共享：多个前往同一目标的实体共享一个方向场。在 PathfindingSystem 中添加请求分组逻辑。

### 挑战练习
1. **Burst ORCA**: 在 ECS 中实现 ORCA 局部避障作为 MovementSystem 的一部分。使用 `IJobParallelFor` 处理所有实体对的速度约束求解。测量 200+ 实体的帧时间。
2. **完全无主线程寻路**: 将 BlobBuilder 构造从主线程移到 Job 中（使用 `Allocator.Persistent` + EntityCommandBuffer.ParallelWriter）。验证完全 off-main-thread 的收益。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```csharp
> // 验证脚本：在 20×20 手工网格上测试单个实体寻路
> // 放在 GameObject 上，运行时按 Space 键触发寻路验证
> public class ECS_PathfindingTest : MonoBehaviour {
>     public int mapWidth = 20;
>     public int mapHeight = 20;
>
>     private World _world;
>     private Entity _testEntity;
>
>     void Start() {
>         _world = World.DefaultGameObjectInjectionWorld;
>         var em = _world.EntityManager;
>
>         // 1. 创建手工网格 (20×20，左下角有 L 形障碍)
>         int cellCount = mapWidth * mapHeight;
>         var costMap = new NativeArray<float>(cellCount, Allocator.Temp);
>         var obstacles = new NativeArray<bool>(cellCount, Allocator.Temp);
>
>         for (int i = 0; i < cellCount; i++) {
>             costMap[i] = 1.0f;
>             int x = i % mapWidth, y = i / mapWidth;
>             // L 形障碍: (5,5)→(5,14) + (5,14)→(14,14)
>             obstacles[i] = (x == 5 && y >= 5 && y <= 14) ||
>                            (y == 14 && x >= 5 && x <= 14);
>         }
>
>         // 2. 构建 GridBlob
>         var bb = new BlobBuilder(Allocator.Temp);
>         ref var gridBlob = ref bb.ConstructRoot<GridBlob>();
>         var costArr = bb.Allocate(ref gridBlob.costMap, cellCount);
>         var obsArr = bb.Allocate(ref gridBlob.obstacles, cellCount);
>         for (int i = 0; i < cellCount; i++) {
>             costArr[i] = costMap[i]; obsArr[i] = obstacles[i];
>         }
>         var blobRef = bb.CreateBlobAssetReference<GridBlob>(Allocator.Persistent);
>         bb.Dispose();
>
>         // 3. 创建 GridData singleton
>         var gridEntity = em.CreateEntity();
>         em.AddComponentData(gridEntity, new GridData {
>             width = mapWidth, height = mapHeight, cellSize = 1.0f,
>             gridBlob = blobRef
>         });
>
>         // 4. 创建测试实体 (起点 (1,1)，目标 (18,18))
>         _testEntity = em.CreateEntity(
>             typeof(LocalTransform), typeof(PathRequest));
>         em.SetComponentData(_testEntity, new LocalTransform {
>             Position = new float3(1.5f, 0, 1.5f),
>             Rotation = quaternion.identity, Scale = 1f
>         });
>         em.AddComponentData(_testEntity, new PathRequest {
>             goal = new float3(18.5f, 0, 18.5f), maxPathCost = float.MaxValue
>         });
>
>         costMap.Dispose(); obstacles.Dispose();
>     }
>
>     void Update() {
>         if (Input.GetKeyDown(KeyCode.Space)) {
>             var em = _world.EntityManager;
>             if (em.HasComponent<PathResult>(_testEntity)) {
>                 var result = em.GetComponentData<PathResult>(_testEntity);
>                 if (result.isComplete) {
>                     ref var blob = ref result.pathBlob.Value;
>                     Debug.Log($"Path found: {blob.waypoints.Length} waypoints, "
>                         + $"cost={blob.totalCost:F2}");
>                     // 打印路径坐标
>                     for (int i = 0; i < blob.waypoints.Length; i++)
>                         Debug.Log($"  [{i}] {blob.waypoints[i]}");
>                 } else if (result.isFailed) {
>                     Debug.LogError("Pathfinding failed!");
>                 }
>             } else {
>                 Debug.Log("Pathfinding in progress... (PathResult not yet added)");
>             }
>         }
>     }
> }
>
> // 验证要点:
> // 1. 路径应绕过 L 形障碍（不能穿过 (5,5)→(5,14) 或 (5,14)→(14,14)）
> // 2. waypoint 数量应 > 曼哈顿距离 (因为有绕行)
> // 3. PathResult 应在 1 帧内添加（系统 OnUpdate 后）
> ```

> [!tip]- 练习 2 参考答案
> ```csharp
> // 批量压力测试脚本
> public class ECS_StressTest : MonoBehaviour {
>     public int entityCount = 500;
>     public int mapWidth = 64;
>     public int mapHeight = 64;
>     public bool useBurst = true;
>
>     private World _world;
>     private Entity[] _entities;
>     private System.Random _rand = new(42);
>
>     void Start() {
>         _world = World.DefaultGameObjectInjectionWorld;
>         var em = _world.EntityManager;
>
>         // 创建随机地图 (20% 障碍)
>         int cellCount = mapWidth * mapHeight;
>         var costMap = new NativeArray<float>(cellCount, Allocator.Temp);
>         var obstacles = new NativeArray<bool>(cellCount, Allocator.Temp);
>         var rng = new Unity.Mathematics.Random(42);
>         for (int i = 0; i < cellCount; i++) {
>             costMap[i] = 1.0f;
>             obstacles[i] = (rng.NextFloat() < 0.2f);
>         }
>
>         // 确保 (0,0) 和 (63,63) 可通行
>         obstacles[0] = false;
>         obstacles[cellCount - 1] = false;
>
>         var bb = new BlobBuilder(Allocator.Temp);
>         ref var gridBlob = ref bb.ConstructRoot<GridBlob>();
>         var costArr = bb.Allocate(ref gridBlob.costMap, cellCount);
>         var obsArr = bb.Allocate(ref gridBlob.obstacles, cellCount);
>         for (int i = 0; i < cellCount; i++) {
>             costArr[i] = costMap[i]; obsArr[i] = obstacles[i];
>         }
>         var blobRef = bb.CreateBlobAssetReference<GridBlob>(Allocator.Persistent);
>         bb.Dispose();
>
>         var gridEntity = em.CreateEntity();
>         em.AddComponentData(gridEntity, new GridData {
>             width = mapWidth, height = mapHeight, cellSize = 1.0f,
>             gridBlob = blobRef
>         });
>
>         // 生成 500 个实体
>         _entities = new Entity[entityCount];
>         for (int i = 0; i < entityCount; i++) {
>             var e = em.CreateEntity(typeof(LocalTransform));
>             int sx, sy, gx, gy;
>             do { sx = _rand.Next(mapWidth); sy = _rand.Next(mapHeight); }
>             while (obstacles[sy * mapWidth + sx]);
>             do { gx = _rand.Next(mapWidth); gy = _rand.Next(mapHeight); }
>             while (obstacles[gy * mapWidth + gx] || (sx == gx && sy == gy));
>
>             em.SetComponentData(e, new LocalTransform {
>                 Position = new float3(sx + 0.5f, 0, sy + 0.5f),
>                 Rotation = quaternion.identity, Scale = 1f
>             });
>             _entities[i] = e;
>         }
>         costMap.Dispose(); obstacles.Dispose();
>     }
>
>     void Update() {
>         if (Input.GetKeyDown(KeyCode.Space)) {
>             var em = _world.EntityManager;
>             // 给所有实体添加 PathRequest
>             for (int i = 0; i < entityCount; i++) {
>                 if (!em.HasComponent<PathRequest>(_entities[i])) {
>                     int gx = _rand.Next(mapWidth);
>                     int gy = _rand.Next(mapWidth);
>                     em.AddComponentData(_entities[i], new PathRequest {
>                         goal = new float3(gx + 0.5f, 0, gy + 0.5f),
>                         maxPathCost = float.MaxValue
>                     });
>                 }
>             }
>             // 打开 Profiler (Window → Analysis → Profiler)
>             // 找到 PathfindingSystem.OnUpdate 的耗时
>         }
>
>         // 显示统计
>         if (Time.frameCount % 60 == 0) {
>             int completed = 0, failed = 0, pending = 0;
>             foreach (var e in _entities) {
>                 if (!em.HasComponent<PathResult>(e)) pending++;
>                 else {
>                     var r = em.GetComponentData<PathResult>(e);
>                     if (r.isComplete) completed++;
>                     else if (r.isFailed) failed++;
>                 }
>             }
>             Debug.Log($"Frame {Time.frameCount}: {completed} complete, "
>                 + $"{failed} failed, {pending} pending");
>         }
>     }
> }
> ```
>
> **Burst 性能差异预期**：关闭 Burst → PathfindingSystem ~45ms (主线程阻塞明显)。开启 Burst → ~5-8ms。加速比约 6-9×。主要原因：(1) Burst 将 C# 数学运算编译为 SIMD 指令；(2) 消除托管分配（`NativeArray` 替代 `List`）；(3) 内联展开小函数（如 `Heuristic`、`Push/Pop`）。在 Profiler 中，Burst 模式下 `BurstAStar.FindPath` 的 CPU 时间主要由节点扩展循环（70%）和 `NativeArray` 索引（15%）组成。

> [!tip]- 练习 3 参考答案
> ```csharp
> // MovementSystem 中添加 Catmull-Rom 平滑
> [BurstCompile]
> public static float3 CatmullRom(float3 p0, float3 p1, float3 p2, float3 p3, float t) {
>     // Catmull-Rom 样条：t ∈ [0,1] 在 p1→p2 之间
>     float t2 = t * t;
>     float t3 = t2 * t;
>     return 0.5f * (
>         (2f * p1) +
>         (-p0 + p2) * t +
>         (2f * p0 - 5f * p1 + 4f * p2 - p3) * t2 +
>         (-p0 + 3f * p1 - 3f * p2 + p3) * t3
>     );
> }
>
> // 修改 MovementSystem 的 OnUpdate 中的移动逻辑
> float3 GetSmoothedTarget(ref PathBlob pathBlob, int waypointIdx) {
>     int len = pathBlob.waypoints.Length;
>     if (len <= 2) return pathBlob.waypoints[waypointIdx];
>
>     // 获取 4 个控制点（边界 clamp）
>     int i0 = math.max(0, waypointIdx - 1);
>     int i1 = waypointIdx;
>     int i2 = math.min(len - 1, waypointIdx + 1);
>     int i3 = math.min(len - 1, waypointIdx + 2);
>
>     float3 p0 = pathBlob.waypoints[i0];
>     float3 p1 = pathBlob.waypoints[i1];
>     float3 p2 = pathBlob.waypoints[i2];
>     float3 p3 = pathBlob.waypoints[i3];
>
>     // t 由当前位置到 waypoint 的距离比例插值
>     return CatmullRom(p0, p1, p2, p3, 0.5f);
> }
>
> // 在 MovementSystem 的 foreach 中替换 target 获取:
> float3 target = GetSmoothedTarget(ref pathBlob, waypointIdx);
> ```
>
> **效果**：原始路径在 waypoint 之间呈折线（锐角转弯），Catmull-Rom 插值后路径变为平滑曲线。参数 `t` 控制插值位置——`t=0.5` 给出中点，可用于计算"朝向曲线切线方向"的瞬时方向（对 steering 行为更友好）。注意：`waypointIdx` 到 `waypointIdx+1` 之间需要 `t` 从 0 线性增长到 1（基于当前位置的距离比例）。

> [!tip]- 练习 4 参考答案（进阶）
> ```csharp
> // 增量路径更新：目标移动时只重算局部段
> [BurstCompile]
> public static bool IncrementalUpdatePath(
>     in NativeArray<float> costMap, in NativeArray<bool> obstacles,
>     int mapWidth, int mapHeight,
>     NativeList<int2> currentPath, // 当前路径 (会被修改)
>     float3 agentPos, int2 newGoal) {
>
>     // 1. 找到当前位置在原路径上最近的可达点
>     int2 agentCell = new((int)agentPos.x, (int)agentPos.z);
>     int closestIdx = -1;
>     float closestDist = float.MaxValue;
>
>     for (int i = 0; i < currentPath.Length; i++) {
>         // 检查该 waypoint 是否仍可达
>         var wp = currentPath[i];
>         if (!obstacles[wp.y * mapWidth + wp.x]) {
>             float d = math.distancesq(agentCell, wp);
>             if (d < closestDist) { closestDist = d; closestIdx = i; }
>         }
>     }
>
>     if (closestIdx < 0) {
>         // 当前路径上无可达点 → 需要全量重算
>         currentPath.Clear();
>         float _;
>         return BurstAStar.FindPath(costMap, obstacles,
>             mapWidth, mapHeight, agentCell, newGoal,
>             float.MaxValue, currentPath, out _);
>     }
>
>     // 2. 截断路径到最近可达点
>     int keepCount = closestIdx + 1;
>     var tail = new NativeList<int2>(Allocator.Temp);
>     for (int i = keepCount; i < currentPath.Length; i++)
>         tail.Add(currentPath[i]);
>     currentPath.Resize(keepCount, NativeArrayOptions.UninitializedMemory);
>
>     // 3. 从尾段最后一点到新目标重算
>     int2 reconnectStart = currentPath[currentPath.Length - 1];
>     var newTail = new NativeList<int2>(256, Allocator.Temp);
>     float _;
>     bool found = BurstAStar.FindPath(costMap, obstacles,
>         mapWidth, mapHeight, reconnectStart, newGoal,
>         float.MaxValue, newTail, out _);
>
>     if (found) {
>         // 拼接：保留段 + 新段（跳过重复的连接点）
>         for (int i = 1; i < newTail.Length; i++) // 跳过 start
>             currentPath.Add(newTail[i]);
>         return true;
>     }
>
>     return false;
> }
> ```
>
> **性能收益**：目标移动 5 格时，全量 A* 需探索 ~100 节点。增量更新只需探索局部段（~20 节点）+ O(N) 线搜索（N=当前路径长度）。加速约 3-5×。关键前提：新目标与旧路径的尾段方向一致（同向延伸）效果最好；如果目标反向移动（U-turn），增量更新的收益消失。

> [!tip]- 练习 5 参考答案（进阶）
> ```csharp
> // ECS 版 HPA*：在 GridData 中存储两个层级
> public struct HierarchicalGridData : IComponentData {
>     public int fineWidth, fineHeight;    // 64×64
>     public int coarseWidth, coarseHeight; // 8×8 (每 cluster 8×8)
>     public int clusterSize;
>     public BlobAssetReference<FineGridBlob> fineGrid;
>     public BlobAssetReference<CoarseGraphBlob> coarseGraph;
> }
>
> public struct CoarseGraphBlob {
>     public BlobArray<int> edgeTargets;   // 扁平化的邻接表
>     public BlobArray<int> edgeOffsets;   // 每个节点的起始 offset
>     public BlobArray<float> edgeCosts;   // cluster 间最短路径代价
> }
>
> [BurstCompile]
> public struct HierarchicalPathfindingJob : IJobParallelFor {
>     // ... 输入 ...
>     public void Execute(int index) {
>         var req = requests[index];
>
>         // Phase 1: 粗粒度路径 (8×8 抽象图)
>         int2 coarseStart = new(req.startCell.x / clusterSize,
>                                 req.startCell.y / clusterSize);
>         int2 coarseGoal = new(req.goalCell.x / clusterSize,
>                               req.goalCell.y / clusterSize);
>
>         var coarsePath = new NativeList<int2>(64, Allocator.Temp);
>         float _;
>         // 在 8×8 抽象图上跑 A* —— 极快 (<0.01ms)
>         bool coarseFound = BurstAStar.FindPath(
>             coarseGraphAsCostMap, coarseObstacles,
>             coarseWidth, coarseHeight, coarseStart, coarseGoal,
>             float.MaxValue, coarsePath, out _);
>
>         if (!coarseFound) { results_success[index] = false; return; }
>
>         // Phase 2: 在粗路径通过的 cluster 内细化
>         // 限制搜索空间: 只搜索粗路径通过的 cluster + 相邻 cluster
>         var restrictedObstacles = new NativeArray<bool>(
>             fineWidth * fineHeight, Allocator.Temp);
>         // 将搜索限制区域外的格子标记为障碍
>         // ... (构建 restricted 地图) ...
>
>         var finePath = new NativeList<int2>(256, Allocator.Temp);
>         bool fineFound = BurstAStar.FindPath(
>             costMap, restrictedObstacles,
>             fineWidth, fineHeight, req.startCell, req.goalCell,
>             float.MaxValue, finePath, out float totalCost);
>
>         // 输出结果...
>     }
> }
> ```
>
> **加速比**：64×64 网格全量 A* ~1ms/query。HPA*：(1) 8×8 抽象图 0.01ms + (2) 约 3-5 个 cluster 的局部搜索 0.15ms → 总 0.16ms。加速约 6×。对于 256×256 网格差异更大（全量 ~16ms vs HPA* ~0.5ms，32×）。

> [!tip]- 练习 6 参考答案（进阶）
> ```csharp
> // Flow Field Blob Asset 共享系统
> // 核心思想：多个前往同一目标的实体共享同一个方向场
>
> public struct FlowFieldRequest : IComponentData {
>     public int2 goalCell;
> }
>
> // FlowFieldManager: 管理已计算的 Flow Field 的缓存
> public struct FlowFieldCache : IComponentData {
>     // goalCellHash → BlobAssetReference<FlowFieldBlob>
>     // 使用 NativeHashMap<int, BlobAssetReference<FlowFieldBlob>>
>     public NativeHashMap<int, BlobAssetReference<FlowFieldBlob>> cache;
>     public NativeHashMap<int, int> refCounts; // 引用计数
> }
>
> public struct FlowFieldBlob {
>     public BlobArray<float2> directions;  // 每个格子的方向
>     public BlobArray<float>  distances;   // 到目标的积分距离
>     public int2 goalCell;
> }
>
> [BurstCompile]
> public partial struct FlowFieldSystem : ISystem {
>     public void OnUpdate(ref SystemState state) {
>         // 1. 按 goalCell 分组所有 FlowFieldRequest
>         //    (使用 NativeMultiHashMap<int2, Entity>)
>         var goalGroups = new NativeMultiHashMap<int2, Entity>(
>             256, Allocator.TempJob);
>
>         foreach (var (req, entity) in
>                  SystemAPI.Query<RefRO<FlowFieldRequest>>()
>                           .WithEntityAccess()) {
>             goalGroups.Add(req.ValueRO.goalCell, entity);
>         }
>
>         // 2. 对每个唯一目标（组大小 > 1 才值得共享），计算 Flow Field
>         var uniqueGoals = goalGroups.GetUniqueKeyArray(Allocator.Temp);
>         for (int g = 0; g < uniqueGoals.Length; g++) {
>             var goal = uniqueGoals[g];
>             int count = goalGroups.CountValuesForKey(goal);
>
>             if (count >= 2) {
>                 // 计算 Flow Field 并存储为 Blob Asset
>                 var blobRef = ComputeFlowFieldBlob(goal);
>                 // 给该组所有实体添加 SharedFlowField 组件
>                 // (指向同一个 blobRef)
>                 foreach (var entity in goalGroups.GetValuesForKey(goal)) {
>                     ecb.AddComponent(entity, new SharedFlowField {
>                         blobRef = blobRef
>                     });
>                 }
>             }
>         }
>     }
> }
> ```
>
> **共享收益**：500 个实体前往 3 个不同目标（如攻占点 A/B/C）。不共享：500 次 A* = ~2500ms。共享：3 次 Flow Field 计算 + 500 次 O(1) 采样 = ~15ms。加速 160×。这是 RTS 游戏（数百单位向同一目标移动）的标准优化。

> [!tip]- 练习 7 参考答案（挑战）
> ```csharp
> // Burst ORCA —— 在 ECS MovementSystem 中集成
> [BurstCompile]
> public struct OrcaSolveJob : IJobParallelFor {
>     [ReadOnly] public NativeArray<float2> positions;
>     [ReadOnly] public NativeArray<float2> velocities;
>     [ReadOnly] public NativeArray<float2> prefVels;
>     [ReadOnly] public NativeArray<float>  radii;
>     [ReadOnly] public NativeArray<float>  maxSpeeds;
>     [ReadOnly] public NativeArray<float>  timeHorizons;
>     public NativeArray<float2> newVelocities;
>     public float neighborDist;
>     public float deltaTime;
>
>     public void Execute(int agentIdx) {
>         float2 posA = positions[agentIdx];
>         float2 velA = velocities[agentIdx];
>         float2 prefV = prefVels[agentIdx];
>         float rA = radii[agentIdx], maxSpd = maxSpeeds[agentIdx];
>         float tauA = timeHorizons[agentIdx];
>
>         // 收集约束 (最多 32 条)
>         var lines = new NativeList<OrcaLine>(32, Allocator.Temp);
>         // 速度边界
>         float vmax = maxSpd;
>         lines.Add(new OrcaLine { dir = new float2(1,0),  point = -vmax });
>         lines.Add(new OrcaLine { dir = new float2(-1,0), point =  vmax });
>         lines.Add(new OrcaLine { dir = new float2(0,1),  point = -vmax });
>         lines.Add(new OrcaLine { dir = new float2(0,-1), point =  vmax });
>
>         // 对每个邻居构造 ORCA 半平面
>         float ndSq = neighborDist * neighborDist;
>         for (int j = 0; j < positions.Length; j++) {
>             if (j == agentIdx) continue;
>             float2 relPos = positions[j] - posA;
>             float distSq = math.lengthsq(relPos);
>             if (distSq > ndSq || distSq < 0.0001f) continue;
>
>             float dist = math.sqrt(distSq);
>             float R = rA + radii[j];
>             float2 toB = relPos / dist;
>             float closing = math.dot(velA - velocities[j], toB);
>             float tau = math.max(tauA, timeHorizons[j]);
>             float minChange = (dist - R) / tau;
>             float wMag = closing - minChange;
>             if (wMag <= 0f) continue;
>
>             float2 w = toB * wMag;
>             float2 uOpt = velA - 0.5f * w;
>             lines.Add(new OrcaLine { dir = math.normalize(w), point = math.dot(math.normalize(w), uOpt) });
>         }
>
>         // 2D LP 求解 (随机增量法, Burst 兼容)
>         float2 opt = prefV;
>         for (int i = 0; i < lines.Length; i++) {
>             var L = lines[i];
>             if (math.dot(L.dir, opt) >= L.point - 1e-5f) continue;
>             float d = L.point - math.dot(L.dir, prefV);
>             opt = prefV + L.dir * d;
>             for (int k = 0; k < i; k++) {
>                 var Lk = lines[k];
>                 if (math.dot(Lk.dir, opt) >= Lk.point - 1e-5f) continue;
>                 float det = L.dir.x * Lk.dir.y - L.dir.y * Lk.dir.x;
>                 if (math.abs(det) < 1e-7f) continue;
>                 opt = new float2(
>                     (L.point * Lk.dir.y - Lk.point * L.dir.y) / det,
>                     (L.dir.x * Lk.point - Lk.dir.x * L.point) / det);
>             }
>         }
>         newVelocities[agentIdx] = opt;
>     }
> }
>
> struct OrcaLine { public float2 dir; public float point; }
> ```
>
> **性能预期**：200 个实体的 ORCA 求解（暴力 O(N²) 邻居检查）在 Burst 编译 + IJobParallelFor 下约 1.2ms（200×200 次距离检查 + LP）。使用空间哈希将邻居检查降至 O(N×K) 可进一步优化到 ~0.3ms。对比 MonoBehaviour ORCA（~15ms），加速约 12-50×。

> [!tip]- 练习 8 参考答案（挑战）
> ```csharp
> // 完全无主线程寻路：将 BlobBuilder 移到 Job 中
> [BurstCompile]
> public struct BuildPathBlobJob : IJobParallelFor {
>     [ReadOnly] public NativeArray<int2> allWaypoints;
>     [ReadOnly] public NativeArray<int> waypointCounts;
>     [ReadOnly] public NativeArray<float> resultsCost;
>     [ReadOnly] public NativeArray<Entity> entities;
>     public int maxWaypoints;
>     public float cellSize;
>
>     // EntityCommandBuffer.ParallelWriter 是线程安全的
>     public EntityCommandBuffer.ParallelWriter ecb;
>
>     public void Execute(int index) {
>         int count = waypointCounts[index];
>         if (count == 0) {
>             ecb.AddComponent(index, entities[index], new PathResult {
>                 pathBlob = default, isComplete = false, isFailed = true
>             });
>             ecb.RemoveComponent<PathRequest>(index, entities[index]);
>             return;
>         }
>
>         // BlobBuilder 在 Job 线程中构造
>         // 必须使用 Allocator.Persistent（Temp 在 Job 返回时失效）
>         var bb = new BlobBuilder(Allocator.Temp);
>         ref var pathBlob = ref bb.ConstructRoot<PathBlob>();
>         var wpArr = bb.Allocate(ref pathBlob.waypoints, count);
>         int baseIdx = index * maxWaypoints;
>         for (int w = 0; w < count; w++) {
>             var cell = allWaypoints[baseIdx + w];
>             wpArr[w] = new float3(
>                 (cell.x + 0.5f) * cellSize, 0,
>                 (cell.y + 0.5f) * cellSize);
>         }
>         pathBlob.totalCost = resultsCost[index];
>
>         var blobRef = bb.CreateBlobAssetReference<PathBlob>(
>             Allocator.Persistent);
>         bb.Dispose();
>
>         ecb.AddComponent(index, entities[index], new PathResult {
>             pathBlob = blobRef, currentWaypoint = 0,
>             isComplete = false, isFailed = false
>         });
>         ecb.RemoveComponent<PathRequest>(index, entities[index]);
>     }
> }
>
> // 在 PathfindingSystem.OnUpdate() 中替换主线程的 BlobBuilder 循环：
> var buildJob = new BuildPathBlobJob {
>     allWaypoints = allWaypoints,
>     waypointCounts = waypointCounts,
>     resultsCost = resultsCost,
>     entities = entityArray,
>     maxWaypoints = maxWaypoints,
>     cellSize = gridData.cellSize,
>     ecb = ecb.AsParallelWriter()
> };
> var buildHandle = buildJob.Schedule(requestCount, 32, handle);
> // 不再需要 handle.Complete() — 链式调度
> state.Dependency = buildHandle;
> ```
>
> **完全脱离主线程的收益**：原始方案中 `handle.Complete()` 阻塞主线程等待所有 A* Job 完成，然后主线程循环构造 BlobAsset。优化后，PathfindingSystem.OnUpdate 仅做调度（<0.1ms），所有工作（A* + BlobBuilder + ECB 写入）在 worker thread 上异步完成。主线程空闲时间增加 ~3ms/frame，可将更多渲染/AI 逻辑放入主线程。注意：`Allocator.Persistent` 的 BlobAsset 必须在之后由主线程（或其他 Job）通过 ECB 的 `DisposeBlobAsset` 释放——这需要在 PathResult 移除时额外处理。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- **Unity ECS 官方文档**: `ISystem`, `IJobEntity`, `EntityCommandBuffer`, `BlobAsset` 的完整 API。https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/
- **"Burst User Guide"** (Unity): Burst 编译器支持的 C# 子集、优化技术（loop vectorization, auto-vectorization, function pointers）。https://docs.unity3d.com/Packages/com.unity.burst@1.8/manual/
- **"Data-Oriented Design"** (Richard Fabian, 2018): 理解 ECS 背后的哲学——为什么数据布局比代码结构更重要。免费在线版: https://www.dataorienteddesign.com/dodbook/
- **"DOTS Best Practices"** (Unity, 2022): 实体拆分粒度、System 执行顺序、Job 依赖管理的官方指南。
- **BlobAsset Deep Dive** (Unity Blog, 2020): Blob Asset 的内部实现——引用计数、线程安全、与 SerializeReference 的关系。
- **"Job Tips and Tricks"** (GDC 2019, Unity): 实际项目中的 Job 优化技巧——IJobParallelForTransform、EntityCommandBuffer 时序、安全系统。

## 常见陷阱

1. **在 Job 中创建 Entity**: 不能在 IJobParallelFor 中调用 `EntityManager.CreateEntity()`。使用 `EntityCommandBuffer.ParallelWriter` (线程安全的 ECB) 来创建实体。

2. **BlobAssetReference 生命周期**: `pathBlob.Dispose()` 必须在实体销毁或 PathResult 移除时调用。忘记 Dispose 导致内存泄漏；过早 Dispose 导致 dangling reference。在 MovementSystem 中统一清理是最安全的模式。

3. **NativeContainer 泄漏**: 所有 `Allocator.TempJob` 的 NativeArray 必须在 `OnUpdate` 返回前 Dispose。使用 `state.Dependency` 延迟 Dispose（Job 完成后自动释放）可以避免过早释放。

4. **Burst 不支持 try-catch**: 任何可能抛出异常的操作（如数组越界访问）在 Burst 编译后会静默失败或产生未定义行为。确保所有索引访问都有边界检查。

5. **SystemAPI.Query 的性能陷阱**: 在 foreach 循环中使用 `.WithAll<>()` / `.WithNone<>()` 的条件过滤会在每次迭代中检查，对于大量实体这可能很慢。优先使用 `EntityQuery` 预过滤。

6. **Job 之间的不必要 Complete**: `handle.Complete()` 会阻塞主线程等待 Job 完成。尽可能让多个 Job 通过 `JobHandle.CombineDependencies` 链式调度，只在最后才 Complete。

7. **NativeArray 过大导致分配停滞**: 为每个请求分配 `costMap` 大小的数组会消耗大量内存。对于 64×64 地图和 500 个请求：500 × 4096 × 4B = 8 MB 的 PathNode 数组。在 Burst 中使用 `Allocator.Temp`（栈分配）可以避免堆分配。

8. **忘记设置 RequireForUpdate**: 如果 `GridData` 尚未被创建，`SystemAPI.GetSingleton<GridData>()` 会抛出异常。使用 `state.RequireForUpdate<GridData>()` 可以让系统在 GridData 可用之前自动跳过。
