# 综合寻路系统：全线集成

> 所属计划: 高阶寻路系统
> 预计耗时: 120min
> 前置知识: 全部 29 个前置教程（A*, JPS, Theta*, Flow Field, ORCA, KD-Tree, NavMesh, ECS, GPU）

## 1. 概念讲解

### 为什么需要这个？

学完 29 个独立模块后，你需要**缝合**它们。单个算法在隔离环境中工作良好，但在真实项目中它们必须协作：

- A* 产出全局路径，ORCA 在路径上做局部避障
- Flow Field 为群体导航，但 Flow Field 的代价图来自地形系统
- KD-Tree 加速 ORCA 的邻居查询（O(N²) → O(N log N)）
- ECS 把所有系统调度到 worker thread 上

这个最终项目不是"做一个新东西"——而是**组装你已掌握的所有零件**。

### 核心思想

#### 系统全景

```
┌─────────────────────────────────────────────────────────────────┐
│                     NavigationDirector (ECS System)              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐ │
│  │ 请求收集  │ → │ 算法选择 │ → │ 路径计算 │ → │ 结果分发     │ │
│  │ (帧N)    │   │ 路由器   │   │ (Job)    │   │ → Movement   │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │                │                │                │
    ┌────▼────┐      ┌───▼────┐      ┌───▼────┐      ┌───▼────┐
    │ Grid    │      │ A*     │      │ Flow   │      │ ORCA   │
    │ System  │      │ JPS    │      │ Field  │      │ System │
    │(terrain,│      │ Theta* │      │ System │      │(local  │
    │ costs,  │      │ System │      │(multi- │      │ avoid) │
    │ blur)   │      │        │      │ agent) │      │        │
    └─────────┘      └────────┘      └────────┘      └────────┘
                                              │
                                         ┌───▼────┐
                                         │ KD-Tree│
                                         │ (spatial│
                                         │ query) │
                                         └────────┘
```

#### 数据流总览

```
Frame N:
  1. GridSystem:      更新地形代价 → GridData (singleton)
  2. RequestSystem:   收集 PathRequest 组件 → 分组 (单 / 批量)
  3. Router:          选择算法:
     - 单目标, 无地形代价→ JPS
     - 单目标, 有地形代价→ A*
     - 单目标, 需要直路径→ Theta*
     - 多目标同向 → Flow Field
  4. Compute Jobs:    Burst 编译的寻路 → PathResult
  5. MovementSystem:  读取 PathResult → 沿路径移动
  6. ORCASystem:      读取邻居 (KD-Tree) → 速度约束求解 → 调整速度

Frame N+1:
  7. MovementSystem:  waypoint 前进
  8. ORCASystem:      持续避障
  9. CleanupSystem:   回收完成的 PathResult + BlobAsset
```

#### 算法路由器的设计

```csharp
public enum PathfindingAlgorithm {
    AStar,       // 通用, 支持任意代价
    JPS,         // 均匀代价网格, 极快
    ThetaStar,   // 任意角度, 直线路径
    FlowField    // 多智能体共用
}

public struct AlgorithmSelection {
    // 决策逻辑 (在 System 中实现)
    public static PathfindingAlgorithm Select(
        bool hasTerrainCost,  // 地形代价是否非均匀
        bool isGroup,          // 是否多个单位去同一目标
        bool needStraightLine, // 是否需要直线路径
        int agentCount) {

        if (isGroup && agentCount >= 5)
            return PathfindingAlgorithm.FlowField;
        if (needStraightLine)
            return PathfindingAlgorithm.ThetaStar;
        if (!hasTerrainCost)
            return PathfindingAlgorithm.JPS;
        return PathfindingAlgorithm.AStar;
    }
}
```

#### ECS 系统执行顺序

Unity ECS 中，系统执行顺序由 `[UpdateInGroup]` 和 `[UpdateBefore/After]` 控制：

```
[UpdateInGroup(typeof(SimulationSystemGroup))]
[UpdateBefore(typeof(TransformSystemGroup))]
partial struct GridSystem : ISystem { }         // 1. 地形

[UpdateAfter(typeof(GridSystem))]
partial struct KDTreeBuildSystem : ISystem { }  // 2. 空间索引

[UpdateAfter(typeof(KDTreeBuildSystem))]
partial struct NavigationSystem : ISystem { }   // 3. 路由 + 寻路

[UpdateAfter(typeof(NavigationSystem))]
partial struct MovementSystem : ISystem { }     // 4. 沿路径移动

[UpdateAfter(typeof(MovementSystem))]
partial struct ORCASystem : ISystem { }         // 5. 避障 (调整速度)

[UpdateAfter(typeof(ORCASystem))]
partial struct NavigationCleanupSystem : ISystem { } // 6. 回收
```

### 项目规划：分阶段实现

#### Phase 1: 搭建骨架（基础场景 + ECS 框架）
- Unity 项目设置 (Entities 1.0+, Burst, Mathematics)
- 网格可视化 (Gizmos/LineRenderer + 网格编辑器)
- 地形类型定义 (Road/Grass/Forest/Swamp/Mountain)
- 基础 ECS 组件: `GridData`, `PathRequest`, `PathResult`, `MovementState`

#### Phase 2: 核心算法 (A* + JPS + Theta*)
- Burst 编译的 A* (带地形代价)
- Burst 编译的 JPS (均匀代价)
- Theta* (视线检查 + 路径平滑)
- 算法路由器: 运行时选择算法
- 单实体验证: 手工地图上的路径可视化

#### Phase 3: 多智能体 (Flow Field + ORCA)
- Flow Field 的 Burst 实现 (Dijkstra 传播 + 方向场)
- ORCA 速度障碍求解 (最优互惠碰撞避免)
- KD-Tree 构建与 KNN 查询 (加速 ORCA 邻居查找)
- 100+ 实体同时导航的压力测试

#### Phase 4: 优化与打磨
- 模糊惩罚的高斯模糊预处理 (bake 时完成)
- 岛屿检测 (连通分量分析, 避免在孤立区域寻路)
- 路径拉直 (Funnel Algorithm / 视线后处理)
- 动态障碍物处理 (运行时障碍添加/移除)
- 性能分析 (Profiler/Burst Inspector)

#### Phase 5: 可视化与调试
- 路径可视化 (MultiLineRenderer / Debug.DrawLine)
- 代价图热力图 (Texture2D overlay)
- Flow Field 方向箭 (Gizmo arrow grid)
- ORCA 速度向量显示
- 统计面板 (FPS, 活跃路径数, Job 耗时)

## 2. 代码示例

以下代码是一个**完整但模块化的骨架**。每个部分对应一个 Phase，可以在 Unity 项目中逐步组装。

### Phase 1: 项目骨架

#### 地形定义与网格数据

```csharp
// GridTypes.cs — 所有网格相关的基础类型定义
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;
using Unity.Burst;

// ── 地形类型 ──
public enum TerrainType : byte {
    Road    = 0,  // cost 0.8
    Grass   = 1,  // cost 1.0
    Forest  = 2,  // cost 2.5
    Swamp   = 3,  // cost 5.0
    Water   = 4,  // cost 4.0 (shallow, walkable)
    DeepWater = 5, // impassable
    Mountain = 6,  // impassable
}

// ── 地形配置 ──
[BurstCompile]
public static class TerrainConfig {
    public static readonly float[] BaseCost = { 0.8f, 1.0f, 2.5f, 5.0f, 4.0f, float.PositiveInfinity, float.PositiveInfinity };
    public static readonly bool[] Walkable =  { true, true, true,  true,  true,  false, false };

    [BurstCompile]
    public static float GetCost(TerrainType t) => BaseCost[(int)t];

    [BurstCompile]
    public static bool IsWalkable(TerrainType t) => Walkable[(int)t];
}

// ── 网格 Blob (不可变共享数据) ──
public struct GridBlob {
    public int width;
    public int height;
    public float cellSize;
    public BlobArray<byte> terrainTypes;  // width × height, TerrainType cast
    public BlobArray<float> costMap;      // 预处理的地形代价 (含模糊)
    public BlobArray<bool> walkable;      // 预处理的可通行性
}

// ── 网格 Singleton ──
public struct GridData : IComponentData {
    public BlobAssetReference<GridBlob> grid;
    public float3 origin;      // 网格左下角的世界坐标
}

// ── 请求组件 ──
public struct PathRequest : IComponentData {
    public float3 goal;
    public PathfindingAlgorithm algorithm; // 可覆盖路由器的选择
    public float maxCost;
    public byte priority;  // 0=低, 1=中, 2=高, 3=紧急
}

// ── 结果组件 ──  
public struct PathResult : IComponentData {
    public BlobAssetReference<PathBlob> blob;
    public int waypointIndex;
    public byte state; // 0=active, 1=complete, 2=failed
}

// ── 路径 Blob ──
public struct PathBlob {
    public BlobArray<float3> waypoints;   // 世界坐标
    public BlobArray<int2> gridPath;      // 格子坐标 (调试用)
    public float totalCost;
    public PathfindingAlgorithm algorithm;
}

// ── 移动状态 ──
public struct MovementState : IComponentData {
    public float maxSpeed;
    public float currentSpeed;
    public float arrivalRadius;
    public float3 velocity;
}
```

#### 网格编辑器 (MonoBehaviour 辅助)

```csharp
// GridAuthoring.cs — Unity Editor 中的网格配置
using UnityEngine;
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;

public class GridAuthoring : MonoBehaviour {
    [Header("Grid Settings")]
    public int width = 64;
    public int height = 64;
    public float cellSize = 1f;
    public Vector3 origin = Vector3.zero;

    [Header("Terrain Layers (Paint in Inspector)")]
    public TerrainType[] terrainMap; // Serialized as byte[], width × height

    // Editor 工具: 随机生成地形
    [ContextMenu("Generate Random Terrain")]
    public void GenerateRandom() {
        terrainMap = new TerrainType[width * height];
        var rand = new System.Random(42);
        for (int i = 0; i < terrainMap.Length; i++) {
            float r = (float)rand.NextDouble();
            if (r < 0.1f) terrainMap[i] = TerrainType.Water;
            else if (r < 0.15f) terrainMap[i] = TerrainType.Forest;
            else if (r < 0.17f) terrainMap[i] = TerrainType.Swamp;
            else if (r < 0.70f) terrainMap[i] = TerrainType.Grass;
            else terrainMap[i] = TerrainType.Road;
        }
    }
}

// Baker: 将 MonoBehaviour 数据转换到 ECS
public class GridBaker : Baker<GridAuthoring> {
    public override void Bake(GridAuthoring authoring) {
        var entity = GetEntity(TransformUsageFlags.None);

        // Build BlobAsset
        var builder = new BlobBuilder(Allocator.Temp);
        ref var gridBlob = ref builder.ConstructRoot<GridBlob>();

        gridBlob.width = authoring.width;
        gridBlob.height = authoring.height;
        gridBlob.cellSize = authoring.cellSize;

        int cellCount = authoring.width * authoring.height;
        var terrainArray = builder.Allocate(ref gridBlob.terrainTypes, cellCount);
        var costArray    = builder.Allocate(ref gridBlob.costMap, cellCount);
        var walkArray    = builder.Allocate(ref gridBlob.walkable, cellCount);

        for (int i = 0; i < cellCount; i++) {
            var t = (i < authoring.terrainMap.Length)
                ? authoring.terrainMap[i] : TerrainType.Grass;
            terrainArray[i] = (byte)t;
            costArray[i]    = TerrainConfig.GetCost(t);
            walkArray[i]    = TerrainConfig.IsWalkable(t);
        }

        var blobRef = builder.CreateBlobAssetReference<GridBlob>(Allocator.Persistent);
        builder.Dispose();

        AddComponent(entity, new GridData {
            grid = blobRef,
            origin = authoring.origin
        });
    }
}
```

### Phase 2: 核心算法

#### A* (Burst 编译)

```csharp
// BurstAStar.cs — 生产级 A*, 复用 29-ECS 的版本但增强
using Unity.Burst;
using Unity.Collections;
using Unity.Mathematics;

[BurstCompile]
public static class BurstAStar {
    static readonly int2[] DIRS = {
        new(0,-1), new(1,-1), new(1,0), new(1,1),
        new(0,1),  new(-1,1), new(-1,0), new(-1,-1)
    };
    static readonly float[] DIR_COST = {
        1f, 1.41421356f, 1f, 1.41421356f,
        1f, 1.41421356f, 1f, 1.41421356f
    };

    [BurstCompile]
    public static bool FindPath(
        in NativeArray<float> costMap,
        in NativeArray<bool> walkable,
        int w, int h,
        int2 start, int2 goal, float maxCost,
        NativeList<int2> outPath, out float totalCost) {

        totalCost = float.MaxValue;
        outPath.Clear();
        if (!InBounds(start, w, h) || !InBounds(goal, w, h)) return false;
        int si = Idx(start, w), gi = Idx(goal, w);
        if (!walkable[si] || !walkable[gi]) return false;

        var gScores = new NativeArray<float>(w * h, Allocator.Temp);
        var parents  = new NativeArray<int2>(w * h, Allocator.Temp);
        var closed   = new NativeArray<bool>(w * h, Allocator.Temp);

        for (int i = 0; i < w * h; i++) gScores[i] = float.MaxValue;
        gScores[si] = 0f;

        // Min-heap open set
        var heap = new NativeList<HeapEntry>(w * h, Allocator.Temp);
        heap.Add(new HeapEntry { pos = start, f = OctileHeuristic(start, goal) });

        bool found = false;
        while (heap.Length > 0) {
            var cur = PopMin(heap);
            int ci = Idx(cur.pos, w);
            if (closed[ci]) continue;
            closed[ci] = true;

            if (math.all(cur.pos == goal)) {
                totalCost = gScores[ci];
                found = true;
                break;
            }

            for (int d = 0; d < 8; d++) {
                int2 nb = cur.pos + DIRS[d];
                if (!InBounds(nb, w, h)) continue;
                int ni = Idx(nb, w);
                if (!walkable[ni] || closed[ni]) continue;

                float step = DIR_COST[d] * costMap[ni];
                float ng = gScores[ci] + step;
                if (ng >= gScores[ni] || ng > maxCost) continue;

                gScores[ni] = ng;
                parents[ni] = cur.pos;
                heap.Add(new HeapEntry { pos = nb, f = ng + OctileHeuristic(nb, goal) });
            }
        }

        if (found) ReconstructPath(start, goal, parents, w, outPath);

        gScores.Dispose();
        parents.Dispose();
        closed.Dispose();
        heap.Dispose();
        return found;
    }

    [BurstCompile]
    static float OctileHeuristic(int2 a, int2 b) {
        int dx = math.abs(a.x - b.x), dy = math.abs(a.y - b.y);
        return (dx + dy) + (1.41421356f - 2f) * math.min(dx, dy);
    }

    struct HeapEntry { public int2 pos; public float f; }

    static HeapEntry PopMin(NativeList<HeapEntry> heap) {
        int last = heap.Length - 1;
        var result = heap[0];
        heap[0] = heap[last];
        heap.RemoveAt(last);
        SiftDown(heap, 0);
        return result;
    }

    static void SiftDown(NativeList<HeapEntry> heap, int i) {
        int n = heap.Length;
        while (true) {
            int left = 2 * i + 1, right = 2 * i + 2, smallest = i;
            if (left < n && heap[left].f < heap[smallest].f) smallest = left;
            if (right < n && heap[right].f < heap[smallest].f) smallest = right;
            if (smallest == i) break;
            (heap[i], heap[smallest]) = (heap[smallest], heap[i]);
            i = smallest;
        }
    }

    static void ReconstructPath(int2 start, int2 goal,
        NativeArray<int2> parents, int w, NativeList<int2> outPath) {
        int2 cur = goal;
        var temp = new NativeList<int2>(Allocator.Temp);
        while (math.any(cur != start)) {
            temp.Add(cur);
            cur = parents[Idx(cur, w)];
        }
        temp.Add(start);
        for (int i = temp.Length - 1; i >= 0; i--) outPath.Add(temp[i]);
        temp.Dispose();
    }

    [BurstCompile] static int Idx(int2 p, int w) => p.y * w + p.x;
    [BurstCompile] static bool InBounds(int2 p, int w, int h) =>
        p.x >= 0 && p.x < w && p.y >= 0 && p.y < h;
}
```

#### JPS (Burst 编译)

```csharp
// BurstJPS.cs — Jump Point Search (均匀代价网格)
using Unity.Burst;
using Unity.Collections;
using Unity.Mathematics;

[BurstCompile]
public static class BurstJPS {
    // JPS 要求在均匀代价网格上运行
    // 关键函数: jump(node, direction) — 递归扫描

    static readonly int2[] DIRS = {
        new(0,-1), new(1,-1), new(1,0), new(1,1),
        new(0,1),  new(-1,1), new(-1,0), new(-1,-1)
    };
    static readonly float[] DIR_COST = {
        1f, 1.41421356f, 1f, 1.41421356f,
        1f, 1.41421356f, 1f, 1.41421356f
    };

    [BurstCompile]
    public static bool FindPath(
        in NativeArray<bool> walkable, int w, int h,
        int2 start, int2 goal,
        NativeList<int2> outPath, out float totalCost) {

        totalCost = float.MaxValue;
        outPath.Clear();
        if (!InBounds(start, w, h) || !InBounds(goal, w, h)) return false;

        int si = start.y * w + start.x;
        int gi = goal.y * w + goal.x;
        if (!walkable[si] || !walkable[gi]) return false;

        var gScores = new NativeArray<float>(w * h, Allocator.Temp);
        var parents  = new NativeArray<int2>(w * h, Allocator.Temp);
        var closed   = new NativeArray<bool>(w * h, Allocator.Temp);

        for (int i = 0; i < w * h; i++) gScores[i] = float.MaxValue;
        gScores[si] = 0f;

        var heap = new NativeList<HeapEntry>(w * h, Allocator.Temp);
        heap.Add(new HeapEntry { pos = start, f = Heuristic(start, goal) });

        bool found = false;
        while (heap.Length > 0) {
            var cur = PopMin(heap);
            if (closed[cur.pos.y * w + cur.pos.x]) continue;
            closed[cur.pos.y * w + cur.pos.x] = true;

            if (math.all(cur.pos == goal)) {
                totalCost = gScores[goal.y * w + goal.x];
                found = true;
                break;
            }

            // Identify successors via jump points (not direct neighbors)
            var successors = IdentifySuccessors(cur.pos, parents, w, h, walkable);

            for (int s = 0; s < successors.length; s++) {
                var jp = successors.points[s];
                int ji = jp.y * w + jp.x;
                if (closed[ji]) continue;

                float ng = gScores[cur.pos.y * w + cur.pos.x] +
                    Heuristic(cur.pos, jp) * (walkable[ji] ? 1f : float.MaxValue);
                if (ng >= gScores[ji]) continue;

                gScores[ji] = ng;
                parents[ji] = cur.pos;
                heap.Add(new HeapEntry { pos = jp, f = ng + Heuristic(jp, goal) });
            }
        }

        if (found) ReconstructPath(start, goal, parents, w, outPath);
        return found;
    }

    // 简化版 successor 识别 (生产级需要完整剪枝规则)
    struct SuccessorList { public NativeArray<int2> points; public int length; }

    static SuccessorList IdentifySuccessors(int2 node,
        NativeArray<int2> parents, int w, int h,
        in NativeArray<bool> walkable) {
        // 简化: 对 8 方向分别调用 jump
        var result = new NativeArray<int2>(8, Allocator.Temp);
        int count = 0;

        for (int d = 0; d < 8; d++) {
            var jp = Jump(node, d, w, h, walkable);
            if (jp.HasValue && walkable[jp.Value.y * w + jp.Value.x]) {
                result[count++] = jp.Value;
            }
        }
        return new SuccessorList { points = result, length = count };
    }

    static int2? Jump(int2 node, int dir, int w, int h,
        in NativeArray<bool> walkable) {
        int2 next = node + DIRS[dir];
        if (!InBounds(next, w, h) || !walkable[next.y * w + next.x])
            return null;

        // Goal check
        // (caller checks goal separately)

        // Forced neighbor check (straight only for simplicity)
        if (dir % 2 == 0) { // cardinal
            // Check if there's a forced neighbor
            // Forced neighbor: obstacle on one side + walkable diagonal
            int leftDir  = (dir + 6) % 8;  // 90° left
            int rightDir = (dir + 2) % 8;  // 90° right

            var leftN  = next + DIRS[leftDir];
            var diagL  = leftN + DIRS[dir];
            var rightN = next + DIRS[rightDir];
            var diagR  = rightN + DIRS[dir];

            if ((InBounds(leftN, w, h) && !walkable[leftN.y * w + leftN.x] &&
                 InBounds(diagL, w, h) && walkable[diagL.y * w + diagL.x]) ||
                (InBounds(rightN, w, h) && !walkable[rightN.y * w + rightN.x] &&
                 InBounds(diagR, w, h) && walkable[diagR.y * w + diagR.x]))
                return next;
        }

        // Diagonal: scan horizontal + vertical components
        if (dir % 2 == 1) {
            int horzDir = dir - 1; // e.g., NE→E
            int vertDir = dir + 1; // e.g., NE→N
            if (vertDir > 7) vertDir -= 8;

            if (Jump(next, horzDir, w, h, walkable).HasValue ||
                Jump(next, vertDir, w, h, walkable).HasValue)
                return next;
        }

        // Continue recursion
        return Jump(next, dir, w, h, walkable);
    }

    // (Helper functions: PopMin, Heuristic, ReconstructPath same as A*)
    struct HeapEntry { public int2 pos; public float f; }

    static HeapEntry PopMin(NativeList<HeapEntry> heap) {
        int last = heap.Length - 1; var r = heap[0]; heap[0] = heap[last];
        heap.RemoveAt(last); SiftDown(heap, 0); return r;
    }

    static void SiftDown(NativeList<HeapEntry> h, int i) {
        int n = h.Length;
        while (true) {
            int l = 2*i+1, r = 2*i+2, s = i;
            if (l < n && h[l].f < h[s].f) s = l;
            if (r < n && h[r].f < h[s].f) s = r;
            if (s == i) break;
            (h[i], h[s]) = (h[s], h[i]); i = s;
        }
    }

    static float Heuristic(int2 a, int2 b) {
        int dx = math.abs(a.x-b.x), dy = math.abs(a.y-b.y);
        return (dx+dy) + 0.41421356f * math.min(dx,dy);
    }

    static void ReconstructPath(int2 s, int2 g, NativeArray<int2> parents,
        int w, NativeList<int2> out) {
        var t = new NativeList<int2>(Allocator.Temp); int2 c = g;
        while (math.any(c != s)) { t.Add(c); c = parents[c.y*w+c.x]; }
        t.Add(s);
        for (int i = t.Length-1; i >= 0; i--) out.Add(t[i]);
        t.Dispose();
    }

    static bool InBounds(int2 p, int w, int h) =>
        p.x >= 0 && p.x < w && p.y >= 0 && p.y < h;
}
```

### Phase 3: Flow Field + ORCA + KD-Tree

#### Flow Field

```csharp
// FlowField.cs — 矢量场寻路 (Burst)
using Unity.Burst;
using Unity.Collections;
using Unity.Mathematics;

[BurstCompile]
public static class FlowFieldBuilder {
    /// <summary>
    /// 从目标格子向外传播 Dijkstra，构建积分代价场和方向场。
    /// 多个单位前往同一目标时共享结果。
    /// </summary>
    [BurstCompile]
    public static void Build(
        in NativeArray<float> costMap,
        in NativeArray<bool> walkable,
        int w, int h, int2 goal,
        out NativeArray<float> integrationField,   // 每个格子的积分代价
        out NativeArray<float2> flowField) {        // 每个格子的方向向量

        int cells = w * h;
        integrationField = new NativeArray<float>(cells, Allocator.TempJob);
        flowField = new NativeArray<float2>(cells, Allocator.TempJob);

        for (int i = 0; i < cells; i++)
            integrationField[i] = float.MaxValue;

        int gi = goal.y * w + goal.x;
        integrationField[gi] = 0f;

        // Wavefront BFS (Dijkstra without heap — use queue for uniform-like costs)
        var queue = new NativeQueue<int2>(Allocator.TempJob);
        queue.Enqueue(goal);

        while (queue.TryDequeue(out var cur)) {
            float curDist = integrationField[cur.y * w + cur.x];

            for (int d = 0; d < 8; d++) {
                int2 nb = cur + new int2(
                    d == 1 || d == 2 || d == 3 ? 1 : (d == 5 || d == 6 || d == 7 ? -1 : 0),
                    d == 3 || d == 4 || d == 5 ? 1 : (d == 7 || d == 0 || d == 1 ? -1 : 0));

                if (nb.x < 0 || nb.x >= w || nb.y < 0 || nb.y >= h) continue;
                int ni = nb.y * w + nb.x;
                if (!walkable[ni]) continue;

                float stepCost = (d % 2 == 1 ? 1.41421356f : 1f) * costMap[ni];
                float newDist = curDist + stepCost;

                if (newDist < integrationField[ni]) {
                    integrationField[ni] = newDist;
                    queue.Enqueue(nb);
                }
            }
        }

        // 构建方向场: 每个格子指向代价最低的邻居
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                int i = y * w + x;
                float bestDist = integrationField[i];
                int2 bestDir = new int2(0, 0);

                for (int d = 0; d < 8; d++) {
                    int nx = x + (d == 1 || d == 2 || d == 3 ? 1 :
                                  d == 5 || d == 6 || d == 7 ? -1 : 0);
                    int ny = y + (d == 3 || d == 4 || d == 5 ? 1 :
                                  d == 7 || d == 0 || d == 1 ? -1 : 0);

                    if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
                    float nd = integrationField[ny * w + nx];
                    if (nd < bestDist) {
                        bestDist = nd;
                        bestDir = new int2(nx - x, ny - y);
                    }
                }

                flowField[i] = math.normalizesafe(
                    new float2(bestDir.x, bestDir.y));
            }
        }
    }
}
```

#### ORCA 速度障碍求解

```csharp
// ORCA.cs — Optimal Reciprocal Collision Avoidance (Burst)
using Unity.Burst;
using Unity.Collections;
using Unity.Mathematics;

[BurstCompile]
public static class ORCASolver {
    /// <summary>
    /// 为一个 agent 计算 ORCA 速度 (考虑所有邻居)
    /// </summary>
    [BurstCompile]
    public static float2 ComputeVelocity(
        float2 position, float2 prefVelocity,
        float radius, float maxSpeed, float timeHorizon,
        NativeArray<NeighborInfo> neighbors) {

        var lines = new NativeList<ORCALine>(neighbors.Length, Allocator.Temp);

        for (int i = 0; i < neighbors.Length; i++) {
            var n = neighbors[i];
            float2 relPos = n.position - position;
            float dist = math.length(relPos);
            float combinedRadius = radius + n.radius;

            if (dist < combinedRadius) {
                // 已经碰撞: 紧急分离
                float2 normal = dist > 0.0001f ? relPos / dist : new float2(1f, 0f);
                lines.Add(new ORCALine {
                    point = position + normal * combinedRadius,
                    direction = normal
                });
                continue;
            }

            // ORCA 核心: 速度障碍 → 半平面约束
            float2 relVel = prefVelocity - n.velocity;
            float invT = 1f / timeHorizon;

            // 速度障碍锥的顶点
            float2 u;
            if (dist > combinedRadius + 0.001f) {
                float2 unitRelPos = relPos / dist;
                float angle = math.asin(math.min(combinedRadius / dist, 1f));

                // 左/右切线方向
                float cosA = math.cos(angle);
                float sinA = math.sin(angle);
                float2 leftDir = new float2(
                    unitRelPos.x * cosA - unitRelPos.y * sinA,
                    unitRelPos.x * sinA + unitRelPos.y * cosA);

                // 相对速度在锥内 → 计算最小调整量 u
                float legLen = dist * invT;
                float dotU = math.dot(relVel, unitRelPos);

                if (dotU < legLen) {
                    // 需要调整
                    u = unitRelPos * (legLen - dotU);
                } else {
                    // 不需要调整
                    continue;
                }
            } else {
                u = relPos / timeHorizon - relVel;
            }

            float2 lineNormal = math.normalizesafe(u);
            lines.Add(new ORCALine {
                point = prefVelocity + u * 0.5f,
                direction = lineNormal
            });
        }

        // 求解半平面交: 线性规划 (简化版: 投影到半平面的交集)
        float2 result = prefVelocity;

        for (int iter = 0; iter < 10; iter++) { // 最多 10 次迭代
            bool valid = true;
            for (int i = 0; i < lines.Length; i++) {
                var line = lines[i];
                float dot = math.dot(result - line.point, line.direction);
                if (dot < 0) {
                    // 当前解在平面外 → 投影到平面上
                    result -= line.direction * dot;
                    valid = false;
                }
            }
            if (valid) break;
        }

        // 速度限制
        float speed = math.length(result);
        if (speed > maxSpeed)
            result = result / speed * maxSpeed;

        lines.Dispose();
        return result;
    }

    struct ORCALine {
        public float2 point;
        public float2 direction; // 法向量 (指向可行域)
    }

    public struct NeighborInfo {
        public float2 position;
        public float2 velocity;
        public float radius;
    }
}
```

#### KD-Tree

```csharp
// KDTree.cs — 2D KD-Tree for ORCA neighbor queries (Burst)
using Unity.Burst;
using Unity.Collections;
using Unity.Mathematics;

[BurstCompile]
public static class KDTree2D {
    // 定点数节点: left/right 索引, axis (0=x, 1=y), split value
    public struct Node {
        public int left, right;
        public int pointIndex;
        public int axis;
        public float splitValue;
    }

    /// <summary>构建 KD-Tree (递归, 但 Burst 不支持递归→用栈模拟)</summary>
    [BurstCompile]
    public static void Build(NativeArray<float2> points,
        NativeArray<Node> nodes, NativeArray<int> indices) {
        // 初始化 indices
        for (int i = 0; i < indices.Length; i++) indices[i] = i;

        // 迭代构建 (使用显式栈)
        var stack = new NativeList<(int start, int end, int nodeIdx, int depth)>(
            points.Length, Allocator.Temp);

        int nextNode = 0;
        stack.Add((0, points.Length, 0, 0));

        while (stack.Length > 0) {
            var frame = stack[stack.Length - 1];
            stack.RemoveAt(stack.Length - 1);

            int start = frame.start, end = frame.end, depth = frame.depth;
            if (start >= end) continue;

            int axis = depth % 2;

            // Median of three partition
            int mid = (start + end) / 2;
            int pi = PartitionByAxis(points, indices, start, end, axis, mid);

            int ni = nextNode++;
            nodes[ni] = new Node {
                axis = axis,
                splitValue = points[indices[pi]].x,
                pointIndex = indices[pi],
                left = nextNode,
                right = nextNode + 1
            };

            stack.Add((start, pi, ni, depth + 1)); // left
            stack.Add((pi + 1, end, ni, depth + 1)); // right  (will reuse node slots)
        }
    }

    static int PartitionByAxis(NativeArray<float2> pts, NativeArray<int> idx,
        int start, int end, int axis, int pivotIdx) {
        float pivot = pts[idx[pivotIdx]].x;

        // Swap pivot to end
        (idx[pivotIdx], idx[end - 1]) = (idx[end - 1], idx[pivotIdx]);

        int store = start;
        for (int i = start; i < end - 1; i++) {
            if (pts[idx[i]].x < pivot ||
                (math.abs(pts[idx[i]].x - pivot) < 0.0001f && idx[i] < idx[end - 1])) {
                (idx[store], idx[i]) = (idx[i], idx[store]);
                store++;
            }
        }

        (idx[store], idx[end - 1]) = (idx[end - 1], idx[store]);
        return store;
    }

    /// <summary>KNN 查询: 查找 query 点周围的 k 个最近邻居</summary>
    [BurstCompile]
    public static void KNN(NativeArray<Node> nodes, NativeArray<float2> points,
        float2 query, int k, NativeArray<int> result, NativeArray<float> dists) {
        // 简化实现: 线性扫描 + 排序 (对于 < 500 个 agent 够快)
        // 生产级: 真正的 KNN 遍历 KD-Tree
        int n = points.Length;
        var temp = new NativeList<(int idx, float dist)>(n, Allocator.Temp);

        for (int i = 0; i < n; i++) {
            float d = math.distancesq(query, points[i]);
            temp.Add((i, d));
        }

        // 部分排序取前 k
        for (int i = 0; i < math.min(k, temp.Length); i++) {
            int minIdx = i;
            for (int j = i + 1; j < temp.Length; j++)
                if (temp[j].dist < temp[minIdx].dist) minIdx = j;
            (temp[i], temp[minIdx]) = (temp[minIdx], temp[i]);
            result[i] = temp[i].idx;
            dists[i] = math.sqrt(temp[i].dist);
        }
    }
}
```

### Phase 4 & 5: Navigation System + Visualization

#### 导航主系统 (算法路由器)

```csharp
// NavigationSystem.cs — 算法路由器 + 请求调度
using Unity.Entities;
using Unity.Collections;
using Unity.Burst;
using Unity.Jobs;
using Unity.Mathematics;
using Unity.Transforms;

[UpdateInGroup(typeof(SimulationSystemGroup))]
[UpdateBefore(typeof(TransformSystemGroup))]
[BurstCompile]
public partial struct NavigationSystem : ISystem {
    private EntityQuery _singleQuery;     // 单目标请求
    private EntityQuery _groupQuery;      // 多智能体同目标请求

    [BurstCompile]
    public void OnCreate(ref SystemState state) {
        _singleQuery = state.GetEntityQuery(
            ComponentType.ReadOnly<PathRequest>(),
            ComponentType.ReadOnly<LocalTransform>(),
            ComponentType.Exclude<PathResult>(),
            ComponentType.Exclude<GroupTag>());

        _groupQuery = state.GetEntityQuery(
            ComponentType.ReadOnly<PathRequest>(),
            ComponentType.ReadOnly<GroupTag>(),
            ComponentType.ReadOnly<LocalTransform>(),
            ComponentType.Exclude<PathResult>());

        state.RequireForUpdate<GridData>();
    }

    [BurstCompile]
    public void OnUpdate(ref SystemState state) {
        var gridData = SystemAPI.GetSingleton<GridData>();
        ref var grid = ref gridData.grid.Value;

        // — 处理单目标请求 (A* / JPS / Theta*) —
        int singleCount = _singleQuery.CalculateEntityCount();
        if (singleCount > 0) {
            ProcessSingleRequests(ref state, grid, singleCount);
        }

        // — 处理组请求 (Flow Field) —
        int groupCount = _groupQuery.CalculateEntityCount();
        if (groupCount > 0) {
            ProcessGroupRequests(ref state, grid, groupCount);
        }
    }

    void ProcessSingleRequests(ref SystemState state, in GridBlob grid, int count) {
        var requests = new NativeArray<PathRequestData>(count, Allocator.TempJob);
        var entities = _singleQuery.ToEntityArray(Allocator.TempJob);
        var ecb = new EntityCommandBuffer(Allocator.TempJob);

        // 收集请求
        for (int i = 0; i < count; i++) {
            var entity = entities[i];
            var req = SystemAPI.GetComponentRO<PathRequest>(entity);
            var transform = SystemAPI.GetComponentRO<LocalTransform>(entity);

            int2 startCell = WorldToCell(transform.ValueRO.Position, grid);
            int2 goalCell  = WorldToCell(req.ValueRO.goal, grid);

            requests[i] = new PathRequestData {
                start = startCell, goal = goalCell,
                algorithm = req.ValueRO.algorithm,
                maxCost = req.ValueRO.maxCost,
                entity = entity
            };
        }

        // 按算法分组
        for (int i = 0; i < count; i++) {
            var req = requests[i];
            var pathOut = new NativeList<int2>(1024, Allocator.TempJob);
            float cost;
            bool success = false;

            switch (SelectAlgorithm(req.algorithm, grid)) {
                case PathfindingAlgorithm.AStar:
                    success = BurstAStar.FindPath(
                        grid.costMap, grid.walkable, grid.width, grid.height,
                        req.start, req.goal, req.maxCost, pathOut, out cost);
                    break;
                case PathfindingAlgorithm.JPS:
                    success = BurstJPS.FindPath(
                        grid.walkable, grid.width, grid.height,
                        req.start, req.goal, pathOut, out cost);
                    break;
                default:
                    success = BurstAStar.FindPath(
                        grid.costMap, grid.walkable, grid.width, grid.height,
                        req.start, req.goal, req.maxCost, pathOut, out cost);
                    break;
            }

            // 构建 PathBlob
            if (success) {
                var builder = new BlobBuilder(Allocator.Temp);
                ref var blob = ref builder.ConstructRoot<PathBlob>();
                var wps = builder.Allocate(ref blob.waypoints, pathOut.Length);

                for (int w = 0; w < pathOut.Length; w++) {
                    wps[w] = CellToWorld(pathOut[w], grid);
                }
                blob.totalCost = cost;
                blob.algorithm = SelectAlgorithm(req.algorithm, grid);

                var blobRef = builder.CreateBlobAssetReference<PathBlob>(Allocator.Persistent);
                builder.Dispose();

                ecb.AddComponent(req.entity, new PathResult {
                    blob = blobRef, waypointIndex = 0, state = 0
                });
            } else {
                ecb.AddComponent(req.entity, new PathResult {
                    state = 2 // failed
                });
            }

            ecb.RemoveComponent<PathRequest>(req.entity);
            pathOut.Dispose();
        }

        ecb.Playback(state.EntityManager);
        ecb.Dispose();
        requests.Dispose();
        entities.Dispose();
    }

    void ProcessGroupRequests(ref SystemState state, in GridBlob grid, int count) {
        // 按目标分组 → 对每个唯一目标构建 Flow Field → 所有去该目标的实体共享
        // (生产级: 需要目标去重 + 引用计数管理)
        // 这里简化为: 直接构建 Flow Field

        // ... (Flow Field 构建代码见上文)
    }

    // 算法路由器
    static PathfindingAlgorithm SelectAlgorithm(
        PathfindingAlgorithm requested, in GridBlob grid) {
        if (requested != PathfindingAlgorithm.AStar) return requested;

        // 自动选择: 检测代价是否均匀
        bool uniformCost = true;
        float firstCost = grid.costMap[0];
        for (int i = 1; i < grid.width * grid.height; i++) {
            if (math.abs(grid.costMap[i] - firstCost) > 0.001f) {
                uniformCost = false;
                break;
            }
        }
        return uniformCost ? PathfindingAlgorithm.JPS : PathfindingAlgorithm.AStar;
    }

    static int2 WorldToCell(float3 pos, in GridBlob grid) {
        return new int2(
            (int)(pos.x / grid.cellSize),
            (int)(pos.z / grid.cellSize));
    }

    static float3 CellToWorld(int2 cell, in GridBlob grid) {
        return new float3(
            (cell.x + 0.5f) * grid.cellSize, 0,
            (cell.y + 0.5f) * grid.cellSize);
    }
}

public struct GroupTag : IComponentData { }
```

#### 可视化系统

```csharp
// PathVisualizationSystem.cs — Debug 路径绘制
using Unity.Entities;
using Unity.Collections;
using Unity.Mathematics;
using UnityEngine;

[UpdateInGroup(typeof(PresentationSystemGroup))]
public partial class PathVisualizationSystem : SystemBase {
    protected override void OnUpdate() {
        // 为每个有 PathResult 的实体绘制路径
        Entities.ForEach((in PathResult result, in LocalTransform transform) => {
            if (result.state != 0) return;

            ref var blob = ref result.blob.Value;
            var wps = blob.waypoints;

            // 绘制从当前位置到下一个 waypoint
            int idx = result.waypointIndex;
            if (idx < wps.Length) {
                Debug.DrawLine(transform.Position, wps[idx], Color.green, 0f);

                // 绘制剩余路径
                for (int i = idx; i < wps.Length - 1; i++) {
                    Debug.DrawLine(wps[i], wps[i + 1],
                        blob.algorithm == PathfindingAlgorithm.JPS ? Color.cyan :
                        blob.algorithm == PathfindingAlgorithm.AStar ? Color.yellow :
                        Color.magenta, 0f);
                }
            }
        }).WithoutBurst().Run(); // Debug.DrawLine 不能在 Burst 中调用
    }
}
```

#### 调试统计面板

```csharp
// DebugStats.cs — MonoBehaviour 统计显示
using UnityEngine;
using Unity.Entities;
using Unity.Collections;

public class DebugStats : MonoBehaviour {
    public World world;
    private float _deltaTime;

    void OnGUI() {
        if (world == null || !world.IsCreated) return;

        var em = world.EntityManager;

        int pathReq = em.CreateEntityQuery(typeof(PathRequest)).CalculateEntityCount();
        int pathRes = em.CreateEntityQuery(typeof(PathResult)).CalculateEntityCount();

        _deltaTime = Mathf.Lerp(_deltaTime, Time.unscaledDeltaTime, 0.1f);
        float fps = 1f / _deltaTime;

        GUILayout.BeginArea(new Rect(10, 10, 300, 200));
        GUILayout.Box("Pathfinding Stats");
        GUILayout.Label($"FPS: {fps:F1}");
        GUILayout.Label($"Active PathRequests: {pathReq}");
        GUILayout.Label($"Active PathResults: {pathRes}");
        GUILayout.Label($"Agents: {em.CreateEntityQuery(typeof(MovementState)).CalculateEntityCount()}");
        GUILayout.EndArea();
    }
}
```

## 3. 练习

### 基础练习
1. **最小可运行项目**: 按照 Phase 1-2 搭建项目。创建一个 20×20 的手工网格（草地 + 道路 + 几个障碍），让一个实体从 A 到 B 寻路，验证路径可视化正确。
2. **算法切换**: 修改网格使代价均匀（全部设为草地），观察路由器自动选择 JPS（路径为黄色）。然后添加地形代价，观察路由器切换回 A*（路径为青色）。
3. **多实体测试**: 生成 10 个实体，每个有随机目标和随机起始位置。验证所有实体都能正确到达目标。

### 进阶练习
1. **Flow Field 集成**: 实现组寻路：创建 50 个实体，目标为同一个点。构建 Flow Field，让所有实体沿矢量场移动。对比 50 个独立 A* 请求的性能。
2. **ORCA 避障**: 让 20 个实体在相向而行（10 个从左到右，10 个从右到左），开启 ORCA。观察它们能否互相绕过而不碰撞。
3. **KD-Tree 加速**: 对比有无 KD-Tree 时 ORCA 的帧时间（100 个实体）。关闭 KD-Tree → 回退到暴力 O(N²) 邻居查找。

### 挑战练习
1. **全系统集成**: 同时运行 A* + JPS + Theta* (单目标) 和 Flow Field (组目标)，以及 ORCA + KD-Tree。使用 200 个实体，其中 100 个为独立寻路，100 个为 2 个 Flow Field 组。验证系统在 60 FPS 下稳定运行。
2. **运行时动态地图**: 添加"放置/移除障碍物"功能。当障碍物变化时，重新 bake costMap 和 walkable (使用脏矩形增量更新)，让之前计算的所有路径自动过期并重算。实现完整的动态世界反应。
3. **Benchmark 套件**: 编写自动化性能测试——在不同参数下（地图尺寸、实体数量、障碍物密度）测量每种算法的延迟和吞吐量。生成对比报告（CSV/图表）。

## 4. 扩展阅读

- **"Game AI Pro" Series** (Rabin, ed.): 整个系列的寻路章节。尤其是 Volume 1 的 "JPS+", Volume 2 的 "Hierarchical Pathfinding in Games", Volume 3 的 "ORCA for Large Crowds"。
- **"Reciprocal Collision Avoidance for Multiple Mobile Robots"** (van den Berg et al., 2011): 原始 ORCA 论文。包含完整数学推导和收敛分析。
- **"Parallel Continuous Collision Detection"** (Tang et al., 2011): 对 ORCA/碰撞检测的 GPU 加速方法。
- **Unity Entities 1.0 官方范例**: `EntitiesSamples` 仓库（GitHub）中的 `PhysicsSamples` 和 `DOPsSamples`。https://github.com/Unity-Technologies/EntityComponentSystemSamples
- **"Flow Field Pathfinding"** (Elijah Emerson, GDC 2014): Supreme Commander 2 的 Flow Field 实现分享——工业级的多智能体导航系统设计。
- **"KD-Tree" (Wikipedia)**: 用于理解 KD-Tree 的构建/查询复杂度、维度灾难、与 R-Tree 的比较。https://en.wikipedia.org/wiki/K-d_tree

## 常见陷阱

1. **不同算法的路径质量不同**: A* 路径可能包含锯齿（8 方向离散化），JPS 同样。如果 MovementSystem 直接 follow 这些 waypoints，实体会做之字形运动。必须在 MovementSystem 中做**路径平滑**（视线检查：跳过共线 points，或用 Catmull-Rom / Funnel 平滑）。

2. **Flow Field 的静态假设**: Flow Field 假设目标和代价图不变。如果目标移动了，整个场需要重算。对于动态目标，Flow Field 不适合——回退到独立 A*。

3. **ORCA 的死锁**: ORCA 保证无碰撞但不保证进度。在高密度场景（corridor 宽度 < 2×radius），agent 可能互相阻挡导致死锁。解决方案：添加扰动噪声、分层规划（先决定方向再 ORCA）、或引入 leader-follower 模式。

4. **BlobAsset 的内存**: 每个 PathBlob 可能在 Persistent 分配器中累积。如果没有正确 Dispose（在 PathResult 被移除时），会泄漏 GPU 内存。NavigationCleanupSystem 是必需的。

5. **Burst 的递归限制**: KD-Tree 构建天然是递归的。Burst 不支持递归深度不可预测的函数。使用显式栈模拟递归（如上文的 KD-Tree 代码），或限制树深度 + 切换到迭代。

6. **Job 的 NativeArray 分配开销**: 在 Job.Execute 中分配 `Allocator.Temp` 的数组是每次调用都 malloc 的（不是真 temp）。对于高频率调用（每帧几千次），这会压垮分配器。预分配池化或在 System 级别分配。

7. **EntityCommandBuffer 的回放时机**: ECB 的 `Playback` 必须在 `OnUpdate` 结束前调用。如果在 Job 中创建了 ECB.ParallelWriter，它的 Playback 必须在 Job.Complete() 之后立即执行，否则 Entity 可能被其他 System 在未完成状态下访问。

8. **Debug.DrawLine 不能入 Burst**: 所有可视化代码必须在非 Burst System 中运行。将可视化分离到独立的 PresentationSystemGroup 中的 System，使用 `.WithoutBurst().Run()`。

9. **网格坐标与世界坐标混用**: 在多个系统间传递坐标时，确保明确标注是 grid cell 还是 world position。使用 `int2` 类型表示格子坐标，`float3` 表示世界坐标，避免隐式转换导致 1-cellSize 倍的误差。
