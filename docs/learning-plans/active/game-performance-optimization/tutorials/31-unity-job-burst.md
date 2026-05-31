# Unity Job System + Burst Compiler
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: 多线程基础、C# struct/值类型语义、SIMD 基本概念
---
## 1. 概念讲解

### 为什么需要这个？

C# 的主线程 Update 循环能跑 1000 个简单物体，但 10000 个就掉到 15fps，100000 个直接卡死。核心问题不是「C# 慢」，而是**单线程 + 缓存不友好 + 托管分配**三重打击。Unity Job System 把计算分散到多个 Worker Thread，Burst Compiler 把 C# 子集编译为高度优化的本机代码——两者叠加，数学密集型代码通常获得 **10x~100x 的加速**。

**真实案例**：
- Unity 的 ECS 物理系统使用 Jobs + Burst，可模拟 100K 个物理刚体
- V Rising 使用 Jobs 处理地图生成和路径查找
- Timberborn 使用 Jobs 处理水流模拟

### 核心思想

Job System 的本质是**数据导向的多线程任务调度**：将数据从 GameObjects 中剥离，以连续内存块（NativeContainer）的形式提供给 Job，让多个 Worker Thread 并行处理。Burst Compiler 本质是**LLVM 后端**：将符合限制的 C# 代码直接编译为本机指令（而非 IL2CPP 的中间步骤），启用自动向量化（把 4 个 float 运算打包为 1 条 SIMD 指令）。

#### 1. Job 类型族谱

| Job 接口 | 并行模型 | 典型用途 |
|----------|----------|----------|
| `IJob` | 单线程执行一次 | 单次计算、IO 操作 |
| `IJobParallelFor` | 数组索引并行 | 粒子更新、顶点变换、颜色计算 |
| `IJobFor` | 数组索引并行（灵活步长） | 不等分块的数据处理 |
| `IJobParallelForTransform` | 按 Transform 并行 | 批量修改 Transform（有写入限制） |
| `IJobEntity` (ECS) | 按 Entity/Chunk 并行 | ECS 系统中的组件遍历 |

#### 2. NativeContainer 安全系统——为什么不能直接传数组？

托管数组（`T[]`）可以被 GC 移动，且在多线程环境下无所有权保护。Job System 使用 NativeContainer 解决这两个问题：

**核心容器**：
- `NativeArray<T>`：连续内存块，可被单个 Job 读写或多个 Job 只读
- `NativeList<T>`：动态增长的列表（job 中可写）
- `NativeHashMap<K,V>` / `NativeMultiHashMap<K,V>`：并行安全的哈希表
- `NativeQueue<T>`：并行安全的 FIFO 队列

**安全规则**（编译期 + 运行时双重检查）：
- 一个容器同时只能有一个 Writer，或多个 Reader（`[ReadOnly]` 标记）
- Job 依赖链确保读写顺序
- `DisposeSentinel` 检测内存泄漏

#### 3. Job 依赖链

```csharp
JobHandle handleA = jobA.Schedule();          // 启动 Job A
JobHandle handleB = jobB.Schedule(handleA);   // B 等待 A 完成
JobHandle handleC = jobC.Schedule(handleB);   // C 等待 B 完成
handleC.Complete();                            // 主线程等待 C 完成
JobHandle.CombineDependencies(handleA, handleB); // 多依赖合并
```

**关键原则**：
- 尽量 `Schedule` 而非 `Run`（`Run` 在主线程执行，失去并行优势）
- 组合 `Schedule` 和 `Complete` 的时机：在真正需要结果前不 `Complete`
- 使用 `JobHandle.ScheduleBatchedJobs()` 提前提交已调度的 Job（减少延迟）

#### 4. Burst Compiler 内部：它做了什么？

Burst 基于 LLVM，对 C# 的子集（HPC#）进行 JIT/AOT 编译：

**优化能力**：
- **自动向量化**：`float4` 的加减乘除 → 1 条 SIMD 指令（SSE/NEON/AVX2）
- **循环展开**：自动识别小循环并展开
- **内联**：激进地将小函数内联到调用点
- **死代码消除**：移除 const 条件分支和未使用变量
- **数学函数重写**：`Mathf.Sin` → CPU 的 FSIN 指令（比 .NET 的 Math.Sin 快 10x）

**限制**（Burst 不能编译的）：
- 托管对象（class）的引用和分配
- `try/catch` 和异常
- `string` 操作（除了字面量比较）
- `delegate` 和虚方法调用
- `System.Reflection`
- `System.IO` 的大部分操作
- `UnityEngine.Object` 派生类的访问

**调试工具**：
- **Burst Inspector**：`Jobs → Burst → Inspector`，查看每个 Job 编译后的汇编代码
- **Burst 编译标记**：`[BurstCompile(FloatMode = FloatMode.Fast, FloatPrecision = FloatPrecision.Low)]` 控制浮点精度（Fast 模式下不严格遵循 IEEE 754）

#### 5. `Unity.Mathematics` 库——Burst 的最佳搭档

```csharp
// 传统 C# 写法（标量，不向量化）
for (int i = 0; i < count; i++)
{
    positions[i] += velocities[i] * deltaTime;
}

// Mathematics 库写法（自动向量化）
for (int i = 0; i < count; i++)
{
    positions[i] = math.mad(velocities[i], deltaTime, positions[i]);
    // mad = multiply + add，编译为 1 条 FMA 指令
}
```

`Unity.Mathematics` 提供：
- `float3`、`float4`、`float4x4`、`quaternion` 等 SIMD 友好类型
- `math.mad()`、`math.rsqrt()`、`math.normalize()` 等高速数学函数
- `math.select()`、`math.step()`、`math.smoothstep()` 等无分支的选择/插值函数

#### 6. 性能阶梯（典型加速比）

| 方案 | 10K 粒子更新 | 100K 粒子更新 | 说明 |
|------|-------------|--------------|------|
| MonoBehaviour Update | ~8ms | ~80ms | 单线程 + GC 分配 |
| IJobParallelFor (无 Burst) | ~2ms | ~18ms | 多线程，但 C# 仍有 IL 开销 |
| IJobParallelFor + Burst | ~0.15ms | ~1.2ms | 多线程 + 本机代码 + SIMD |
| IJobParallelFor + Burst + 数据重排 | ~0.08ms | ~0.5ms | 额外优化缓存行对齐 |

---

## 2. 代码示例

### 示例 A：粒子移动 — MonoBehaviour vs Job+Burst 对比

```csharp
// File: Scripts/Jobs/ParticleMovementComparison.cs
// 功能：对比三种粒子移动方案的性能
// 用法：挂到空 GameObject 上，按 1/2/3 切换方案，观察 Profiler

using UnityEngine;
using Unity.Collections;
using Unity.Jobs;
using Unity.Burst;
using Unity.Mathematics;
using UnityEngine.Profiling;

public class ParticleMovementComparison : MonoBehaviour
{
    [Header("粒子数量")]
    [SerializeField] private int particleCount = 50000;
    [SerializeField] private float moveSpeed = 2f;
    [SerializeField] private float boundsRadius = 20f;

    [Header("显示")]
    [SerializeField] private bool showParticles = true;
    [SerializeField] private Mesh particleMesh;
    [SerializeField] private Material particleMaterial;

    // 方案 1: MonoBehaviour 数组
    private ParticleMonoBehaviour[] monoParticles;

    // 方案 2 & 3: 纯数据 + Job
    private NativeArray<ParticleData> particleDataArray;
    private NativeArray<float3> positionsForRendering;
    private NativeArray<Matrix4x4> renderMatrices;

    // 当前方案
    private enum Mode { MonoBehaviour, JobOnly, JobBurst }
    private Mode currentMode = Mode.MonoBehaviour;
    private float lastFrameTime;

    private struct ParticleData
    {
        public float3 position;
        public float3 velocity;
        public float3 color;
        public float scale;
    }

    // 模拟原来的 MonoBehaviour（仅做对比，实际不推荐）
    private class ParticleMonoBehaviour
    {
        public Vector3 position;
        public Vector3 velocity;
        public Vector3 color;
        public float scale;
    }

    // ---------- Job 定义 ----------

    // 无 Burst 的 Job（仍在多线程运行，但代码是 IL2CPP/Mono JIT 的）
    private struct MoveParticlesJobNoBurst : IJobParallelFor
    {
        public NativeArray<ParticleData> particles;
        [ReadOnly] public float deltaTime;
        [ReadOnly] public float speed;
        [ReadOnly] public float boundsRadius;

        public void Execute(int index)
        {
            ParticleData p = particles[index];
            float3 pos = p.position;
            float3 vel = p.velocity;

            pos += vel * speed * deltaTime;

            // 边界回弹
            if (math.length(pos) > boundsRadius)
            {
                float3 dir = math.normalize(pos);
                pos = dir * boundsRadius;
                vel = math.reflect(vel, -dir);
            }

            p.position = pos;
            p.velocity = vel;
            particles[index] = p;
        }
    }

    // Burst 编译的 Job
    [BurstCompile(FloatMode = FloatMode.Fast, FloatPrecision = FloatPrecision.Low)]
    private struct MoveParticlesJobBurst : IJobParallelFor
    {
        public NativeArray<ParticleData> particles;
        [ReadOnly] public float deltaTime;
        [ReadOnly] public float speed;
        [ReadOnly] public float boundsRadius;

        public void Execute(int index)
        {
            ParticleData p = particles[index];
            float3 pos = p.position;
            float3 vel = p.velocity;

            // 使用 math.mad 代替 a + b * c —— 编译为 1 条 FMA 指令
            pos = math.mad(vel, speed * deltaTime, pos);

            float lenSq = math.lengthsq(pos);
            if (lenSq > boundsRadius * boundsRadius)
            {
                float3 dir = math.normalize(pos);
                pos = dir * boundsRadius;
                // math.reflect: I - 2*dot(I,N)*N
                vel = math.reflect(vel, -dir);
            }

            p.position = pos;
            p.velocity = vel;
            particles[index] = p;
        }
    }

    // 准备渲染矩阵的 Job
    [BurstCompile]
    private struct PrepareRenderMatricesJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float3> positions;
        [ReadOnly] public NativeArray<float3> colors;
        [ReadOnly] public NativeArray<float> scales;
        public NativeArray<Matrix4x4> matrices;

        public void Execute(int index)
        {
            matrices[index] = Matrix4x4.TRS(
                positions[index],
                quaternion.identity,
                new float3(scales[index]));
        }
    }

    // ---------- Unity 生命周期 ----------

    private void Start()
    {
        InitializeParticles();
    }

    private void Update()
    {
        // 切换模式
        if (Input.GetKeyDown(KeyCode.Alpha1)) currentMode = Mode.MonoBehaviour;
        if (Input.GetKeyDown(KeyCode.Alpha2)) currentMode = Mode.JobOnly;
        if (Input.GetKeyDown(KeyCode.Alpha3)) currentMode = Mode.JobBurst;

        Profiler.BeginSample("ParticleMovement.Update");
        float startTime = Time.realtimeSinceStartup;

        switch (currentMode)
        {
            case Mode.MonoBehaviour:
                UpdateMonoBehaviourParticles();
                break;
            case Mode.JobOnly:
                UpdateJobParticles(false);
                break;
            case Mode.JobBurst:
                UpdateJobParticles(true);
                break;
        }

        lastFrameTime = (Time.realtimeSinceStartup - startTime) * 1000f;
        Profiler.EndSample();
    }

    private void UpdateMonoBehaviourParticles()
    {
        float dt = Time.deltaTime;
        float speed = moveSpeed;
        float radius = boundsRadius;

        for (int i = 0; i < particleCount; i++)
        {
            var p = monoParticles[i];
            p.position += p.velocity * speed * dt;

            if (p.position.magnitude > radius)
            {
                Vector3 dir = p.position.normalized;
                p.position = dir * radius;
                p.velocity = Vector3.Reflect(p.velocity, -dir);
            }
            monoParticles[i] = p;
        }

        // 手动重建渲染数组（MonoBehaviour 路径下这个也很费时）
        for (int i = 0; i < particleCount; i++)
        {
            var p = monoParticles[i];
            renderMatrices[i] = Matrix4x4.TRS(
                p.position, Quaternion.identity,
                Vector3.one * p.scale);
        }
    }

    private void UpdateJobParticles(bool useBurst)
    {
        float dt = Time.deltaTime;

        JobHandle moveHandle;
        if (useBurst)
        {
            var job = new MoveParticlesJobBurst
            {
                particles = particleDataArray,
                deltaTime = dt,
                speed = moveSpeed,
                boundsRadius = boundsRadius
            };
            moveHandle = job.Schedule(particleCount, 128);
        }
        else
        {
            var job = new MoveParticlesJobNoBurst
            {
                particles = particleDataArray,
                deltaTime = dt,
                speed = moveSpeed,
                boundsRadius = boundsRadius
            };
            moveHandle = job.Schedule(particleCount, 128);
        }

        // 提前提交 batch 以减少延迟
        JobHandle.ScheduleBatchedJobs();

        // 在 job 完成后，提取位置用于渲染
        var extractJob = new ExtractPositionsJob
        {
            particles = particleDataArray,
            positions = positionsForRendering,
            scales = particleDataArray
        };
        JobHandle extractHandle = extractJob.Schedule(
            particleCount, 128, moveHandle);

        // 渲染矩阵准备
        // 注意：这里为了简洁直接传 NativeArray，
        // 实际项目中需要使用 NativeArray 的副本或更精细的同步
        extractHandle.Complete();

        // 在作业完成后准备渲染矩阵（这部分在主线程，但很快）
        for (int i = 0; i < particleCount; i++)
        {
            var pd = particleDataArray[i];
            renderMatrices[i] = Matrix4x4.TRS(
                positionsForRendering[i],
                Quaternion.identity,
                new Vector3(pd.scale, pd.scale, pd.scale));
        }
    }

    [BurstCompile]
    private struct ExtractPositionsJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<ParticleData> particles;
        public NativeArray<float3> positions;
        [ReadOnly] public NativeArray<ParticleData> scales;

        public void Execute(int index)
        {
            positions[index] = particles[index].position;
        }
    }

    private void LateUpdate()
    {
        // 使用 Graphics.DrawMeshInstanced 绘制所有粒子
        // 这是 Unity 最高效的大批量绘制方式
        if (showParticles && renderMatrices.IsCreated)
        {
            // 分批绘制（DrawMeshInstanced 每次最多 1023 个实例）
            int batchSize = 1023;
            for (int i = 0; i < particleCount; i += batchSize)
            {
                int count = math.min(batchSize, particleCount - i);
                // 创建子数组切片（实际项目中用 NativeSlice 更高效）
                Matrix4x4[] batch = new Matrix4x4[count];
                for (int j = 0; j < count; j++)
                    batch[j] = renderMatrices[i + j];

                Graphics.DrawMeshInstanced(
                    particleMesh, 0, particleMaterial, batch);
            }
        }
    }

    private void InitializeParticles()
    {
        monoParticles = new ParticleMonoBehaviour[particleCount];
        particleDataArray = new NativeArray<ParticleData>(
            particleCount, Allocator.Persistent);
        positionsForRendering = new NativeArray<float3>(
            particleCount, Allocator.Persistent);
        renderMatrices = new NativeArray<Matrix4x4>(
            particleCount, Allocator.Persistent);

        var random = new Unity.Mathematics.Random(12345);
        for (int i = 0; i < particleCount; i++)
        {
            float3 pos = random.NextFloat3Direction() * random.NextFloat(0, boundsRadius);
            float3 vel = random.NextFloat3Direction() * random.NextFloat(0.5f, 2f);
            float3 col = new float3(
                random.NextFloat(0.3f, 1f),
                random.NextFloat(0.3f, 1f),
                random.NextFloat(0.3f, 1f));
            float scale = random.NextFloat(0.05f, 0.2f);

            monoParticles[i] = new ParticleMonoBehaviour
            {
                position = pos,
                velocity = vel,
                color = col,
                scale = scale
            };

            particleDataArray[i] = new ParticleData
            {
                position = pos,
                velocity = vel,
                color = col,
                scale = scale
            };

            renderMatrices[i] = Matrix4x4.TRS(pos, Quaternion.identity, Vector3.one * scale);
        }
    }

    private void OnDestroy()
    {
        if (particleDataArray.IsCreated)
            particleDataArray.Dispose();
        if (positionsForRendering.IsCreated)
            positionsForRendering.Dispose();
        if (renderMatrices.IsCreated)
            renderMatrices.Dispose();
    }

    private void OnGUI()
    {
        GUI.Box(new Rect(10, 10, 350, 120), "");
        GUILayout.BeginArea(new Rect(20, 15, 330, 110));
        GUILayout.Label($"粒子数量: {particleCount:N0}");
        GUILayout.Label($"当前模式: {currentMode}");
        GUILayout.Label($"更新耗时: {lastFrameTime:F2}ms");
        GUILayout.Label($"FPS: {1f / Time.unscaledDeltaTime:F0}");
        GUILayout.Label("按 1/2/3 切换模式");
        GUILayout.EndArea();
    }
}
```

### 示例 B：Burst 编译的 A* 寻路

```csharp
// File: Scripts/Jobs/BurstAStarPathfinding.cs
// 功能：Burst 编译的 A* 寻路，对比 C# 托管版本
// 用法：挂到空 GameObject 上，按 Space 触发 100 次随机寻路并计时

using UnityEngine;
using Unity.Collections;
using Unity.Jobs;
using Unity.Burst;
using Unity.Mathematics;
using UnityEngine.Profiling;

public class BurstAStarPathfinding : MonoBehaviour
{
    [SerializeField] private int gridWidth = 256;
    [SerializeField] private int gridHeight = 256;
    [SerializeField] private float cellSize = 0.5f;
    [SerializeField] private int pathCount = 100;

    // 障碍物地图（true = 可通过）
    private NativeArray<bool> walkableGrid;
    // 路径起点/终点（每次寻路随机生成）
    private NativeArray<int2> startPositions;
    private NativeArray<int2> endPositions;
    // 寻路结果（路径长度）
    private NativeArray<int> pathLengths;

    // 托管版本的结果（仅用于对比）
    private bool[] managedWalkable;
    private Vector2Int[] managedStarts;
    private Vector2Int[] managedEnds;
    private int[] managedResults;

    private void Start()
    {
        InitializeGrid();
        GenerateRandomQueries();
    }

    private void InitializeGrid()
    {
        walkableGrid = new NativeArray<bool>(
            gridWidth * gridHeight, Allocator.Persistent);

        var random = new Unity.Mathematics.Random(42);
        for (int y = 0; y < gridHeight; y++)
        {
            for (int x = 0; x < gridWidth; x++)
            {
                // 20% 的格子是障碍物（边缘始终可通过）
                bool isEdge = x == 0 || y == 0
                    || x == gridWidth - 1 || y == gridHeight - 1;
                walkableGrid[y * gridWidth + x] = isEdge
                    || random.NextFloat() > 0.20f;
            }
        }

        // 托管版本副本
        managedWalkable = new bool[gridWidth * gridHeight];
        for (int i = 0; i < managedWalkable.Length; i++)
            managedWalkable[i] = walkableGrid[i];
    }

    private void GenerateRandomQueries()
    {
        startPositions = new NativeArray<int2>(
            pathCount, Allocator.Persistent);
        endPositions = new NativeArray<int2>(
            pathCount, Allocator.Persistent);
        pathLengths = new NativeArray<int>(
            pathCount, Allocator.Persistent);

        managedStarts = new Vector2Int[pathCount];
        managedEnds = new Vector2Int[pathCount];
        managedResults = new int[pathCount];

        var random = new Unity.Mathematics.Random(12345);
        for (int i = 0; i < pathCount; i++)
        {
            int2 start, end;
            do
            {
                start = new int2(
                    random.NextInt(0, gridWidth),
                    random.NextInt(0, gridHeight));
                end = new int2(
                    random.NextInt(0, gridWidth),
                    random.NextInt(0, gridHeight));
            } while (!IsWalkable(start) || !IsWalkable(end)
                || math.distancesq(start, end) < 100f);

            startPositions[i] = start;
            endPositions[i] = end;
            managedStarts[i] = new Vector2Int(start.x, start.y);
            managedEnds[i] = new Vector2Int(end.x, end.y);
        }
    }

    private bool IsWalkable(int2 cell)
    {
        if (cell.x < 0 || cell.x >= gridWidth
            || cell.y < 0 || cell.y >= gridHeight)
            return false;
        return walkableGrid[cell.y * gridWidth + cell.x];
    }

    private void Update()
    {
        if (Input.GetKeyDown(KeyCode.Space))
        {
            RunComparison();
        }
    }

    private void RunComparison()
    {
        // --- Burst A* ---
        Profiler.BeginSample("Burst A* Pathfinding");
        float burstStart = Time.realtimeSinceStartup;

        var burstJob = new AStarBurstJob
        {
            gridWidth = gridWidth,
            gridHeight = gridHeight,
            walkable = walkableGrid,
            starts = startPositions,
            ends = endPositions,
            pathLengths = pathLengths
        };

        JobHandle handle = burstJob.Schedule(pathCount, 4);
        handle.Complete();

        float burstTime = (Time.realtimeSinceStartup - burstStart) * 1000f;
        Profiler.EndSample();

        // --- Managed A* ---
        Profiler.BeginSample("Managed A* Pathfinding");
        float managedStart = Time.realtimeSinceStartup;

        for (int i = 0; i < pathCount; i++)
        {
            managedResults[i] = ManagedAStar(
                managedStarts[i], managedEnds[i]);
        }

        float managedTime = (Time.realtimeSinceStartup - managedStart) * 1000f;
        Profiler.EndSample();

        Debug.Log($"Burst A*: {burstTime:F2}ms  |  " +
                  $"Managed A*: {managedTime:F2}ms  |  " +
                  $"加速比: {managedTime / burstTime:F1}x");
    }

    // Burst 编译的 A* 单次寻路（在 Job 中并行执行）
    [BurstCompile]
    private struct AStarBurstJob : IJobParallelFor
    {
        [ReadOnly] public int gridWidth;
        [ReadOnly] public int gridHeight;
        [ReadOnly] public NativeArray<bool> walkable;
        [ReadOnly] public NativeArray<int2> starts;
        [ReadOnly] public NativeArray<int2> ends;
        public NativeArray<int> pathLengths;

        public void Execute(int index)
        {
            pathLengths[index] = AStarSearch(
                starts[index], ends[index]);
        }

        private int AStarSearch(int2 start, int2 end)
        {
            int cellCount = gridWidth * gridHeight;

            // 使用 NativeArray 的临时分配（在 job 中不安全，这里用栈分配）
            // Burst 会将 NativeArray temp 优化为栈上的数组
            var gScore = new NativeArray<float>(
                cellCount, Allocator.Temp,
                NativeArrayOptions.UninitializedMemory);
            var cameFrom = new NativeArray<int>(
                cellCount, Allocator.Temp,
                NativeArrayOptions.UninitializedMemory);
            var openSet = new NativeList<int>(
                cellCount, Allocator.Temp);

            // 初始化
            for (int i = 0; i < cellCount; i++)
            {
                gScore[i] = float.MaxValue;
                cameFrom[i] = -1;
            }

            int startIdx = Index(start);
            int endIdx = Index(end);
            gScore[startIdx] = 0f;
            openSet.Add(startIdx);

            // 邻居偏移（4 方向）
            var neighbors = new NativeArray<int2>(4, Allocator.Temp);
            neighbors[0] = new int2(0, 1);
            neighbors[1] = new int2(0, -1);
            neighbors[2] = new int2(1, 0);
            neighbors[3] = new int2(-1, 0);

            int pathLength = 0;

            while (openSet.Length > 0)
            {
                // 找 F 值最小的节点
                int currentIdx = -1;
                float minF = float.MaxValue;
                int minOpenIdx = 0;

                for (int i = 0; i < openSet.Length; i++)
                {
                    int idx = openSet[i];
                    float g = gScore[idx];
                    float h = Heuristic(idx, endIdx);
                    float f = g + h;

                    if (f < minF)
                    {
                        minF = f;
                        currentIdx = idx;
                        minOpenIdx = i;
                    }
                }

                if (currentIdx == endIdx)
                {
                    // 重构路径长度
                    int cur = endIdx;
                    while (cur != startIdx && cur >= 0 && cur < cellCount)
                    {
                        pathLength++;
                        cur = cameFrom[cur];
                    }
                    gScore.Dispose();
                    cameFrom.Dispose();
                    openSet.Dispose();
                    neighbors.Dispose();
                    return pathLength;
                }

                // 从 open set 中移除
                openSet.RemoveAtSwapBack(minOpenIdx);

                // 探索邻居
                int2 currentPos = new int2(
                    currentIdx % gridWidth,
                    currentIdx / gridWidth);

                for (int n = 0; n < 4; n++)
                {
                    int2 neighborPos = currentPos + neighbors[n];
                    if (neighborPos.x < 0 || neighborPos.x >= gridWidth
                        || neighborPos.y < 0 || neighborPos.y >= gridHeight)
                        continue;

                    int neighborIdx = Index(neighborPos);
                    if (!walkable[neighborIdx])
                        continue;

                    float tentativeG = gScore[currentIdx] + 1f;
                    if (tentativeG < gScore[neighborIdx])
                    {
                        cameFrom[neighborIdx] = currentIdx;
                        gScore[neighborIdx] = tentativeG;

                        // 检查是否已在 open set
                        bool inOpen = false;
                        for (int k = 0; k < openSet.Length; k++)
                        {
                            if (openSet[k] == neighborIdx)
                            { inOpen = true; break; }
                        }
                        if (!inOpen)
                            openSet.Add(neighborIdx);
                    }
                }
            }

            gScore.Dispose();
            cameFrom.Dispose();
            openSet.Dispose();
            neighbors.Dispose();
            return -1; // 无路径
        }

        private int Index(int2 cell) => cell.y * gridWidth + cell.x;

        private float Heuristic(int a, int b)
        {
            int2 posA = new int2(a % gridWidth, a / gridWidth);
            int2 posB = new int2(b % gridWidth, b / gridWidth);
            return math.abs(posA.x - posB.x) + math.abs(posA.y - posB.y);
        }
    }

    // 托管版本的 A*（仅用于对比，包含 GC 分配）
    private int ManagedAStar(Vector2Int start, Vector2Int end)
    {
        int cellCount = gridWidth * gridHeight;
        var gScore = new float[cellCount];
        var fScore = new float[cellCount];
        var cameFrom = new int[cellCount];
        var closedSet = new bool[cellCount];

        for (int i = 0; i < cellCount; i++)
        {
            gScore[i] = float.MaxValue;
            fScore[i] = float.MaxValue;
            cameFrom[i] = -1;
        }

        var openSet = new System.Collections.Generic.List<int>();
        int startIdx = start.y * gridWidth + start.x;
        int endIdx = end.y * gridWidth + end.x;

        gScore[startIdx] = 0;
        fScore[startIdx] = Mathf.Abs(start.x - end.x)
            + Mathf.Abs(start.y - end.y);
        openSet.Add(startIdx);

        int[] dx = { 0, 0, 1, -1 };
        int[] dy = { 1, -1, 0, 0 };

        while (openSet.Count > 0)
        {
            int currentIdx = openSet[0];
            int currentIdx_i = 0;
            for (int i = 1; i < openSet.Count; i++)
            {
                if (fScore[openSet[i]] < fScore[currentIdx])
                {
                    currentIdx = openSet[i];
                    currentIdx_i = i;
                }
            }

            if (currentIdx == endIdx)
            {
                int length = 0;
                int cur = endIdx;
                while (cur != startIdx)
                {
                    length++;
                    cur = cameFrom[cur];
                }
                return length;
            }

            openSet.RemoveAt(currentIdx_i);
            closedSet[currentIdx] = true;

            int cx = currentIdx % gridWidth;
            int cy = currentIdx / gridWidth;

            for (int n = 0; n < 4; n++)
            {
                int nx = cx + dx[n];
                int ny = cy + dy[n];
                if (nx < 0 || nx >= gridWidth
                    || ny < 0 || ny >= gridHeight)
                    continue;

                int neighborIdx = ny * gridWidth + nx;
                if (!managedWalkable[neighborIdx] || closedSet[neighborIdx])
                    continue;

                float tentativeG = gScore[currentIdx] + 1;
                if (tentativeG < gScore[neighborIdx])
                {
                    cameFrom[neighborIdx] = currentIdx;
                    gScore[neighborIdx] = tentativeG;
                    fScore[neighborIdx] = gScore[neighborIdx]
                        + Mathf.Abs(nx - end.x) + Mathf.Abs(ny - end.y);
                    if (!openSet.Contains(neighborIdx))
                        openSet.Add(neighborIdx);
                }
            }
        }

        return -1;
    }

    private void OnDestroy()
    {
        if (walkableGrid.IsCreated) walkableGrid.Dispose();
        if (startPositions.IsCreated) startPositions.Dispose();
        if (endPositions.IsCreated) endPositions.Dispose();
        if (pathLengths.IsCreated) pathLengths.Dispose();
    }

    // --- Burst Inspector 输出示例（注释中展示） ---

    /*
    在 Burst Inspector (Jobs -> Burst -> Inspector) 中选中
    AStarBurstJob.Execute，你会看到类似下面的 x64 汇编：

    ; AStarSearch - Heuristic 函数内联后
    vmovss   xmm0, dword ptr [rsp + 0x40]   ; 加载 gScore[current]
    vaddss   xmm0, xmm0, dword ptr [rcx]     ; + 1.0f (tentativeG)
    vcomiss  xmm0, dword ptr [rsp + 0x44]    ; compare with gScore[neighbor]
    ja       .LBB0_12                        ; 如果新的更大则跳过

    ; 关键：一个简单的 A* neighbor 检查被编译为紧凑的 SIMD 指令块
    ; 传统 C# 版本此处会有多次托管内存访问 + bounds check
    */
}
```

### 示例 C：Burst Inspector 输出

在 Unity Editor 中，打开 `Jobs → Burst → Inspector`，选中上面 `AStarBurstJob`，你会看到汇编输出。一个典型的 Burst 优化效果（循环展开 + 自动向量化）：

```asm
; Burst 编译的粒子移动核心循环（x64 AVX2）
.LBB0_3:
    vmovups  ymm0, ymmword ptr [rdi + 4*rax]    ; 加载 8 个 float3（含填充）
    vmovups  ymm1, ymmword ptr [rdi + 4*rax + 32]
    vfmadd213ps ymm0, ymm2, ymmword ptr [rsi + 4*rax]    ; FMA: pos += vel * dt
    vfmadd213ps ymm1, ymm2, ymmword ptr [rsi + 4*rax + 32]
    vmovups  ymmword ptr [rdi + 4*rax], ymm0     ; 写回
    vmovups  ymmword ptr [rdi + 4*rax + 32], ymm1
    add      rax, 16
    cmp      rax, rbx
    jl       .LBB0_3
```

**关键观察**：
- `ymm0`/`ymm1`：AVX2 256 位寄存器，每条指令处理 8 个 float
- `vfmadd213ps`：融合乘加指令（FMA），`pos += vel * dt` 在 1 个时钟周期内完成
- 循环展开因子 ≈ 16（`add rax, 16`），减少分支预测次数

---

## 3. 练习

### 练习 1：技术验证 — 三种方案基准测试

1. 复制示例 A 的脚本到你的 URP 项目中
2. 修改 `particleCount` 分别为 1000、10000、50000、100000
3. 每种粒子数下测试三种模式（按 1/2/3），记录帧时间和 FPS
4. 填写性能对比表：

| 粒子数 | Mono Update | Job Only | Job + Burst | Burst 加速比 |
|--------|-------------|----------|-------------|-------------|
| 1K | ?ms/?fps | ?ms/?fps | ?ms/?fps | ?x |
| 10K | ?ms/?fps | ?ms/?fps | ?ms/?fps | ?x |
| 50K | ?ms/?fps | ?ms/?fps | ?ms/?fps | ?x |
| 100K | ?ms/?fps | ?ms/?fps | ?ms/?fps | ?x |

**目标**：亲身体验 Job + Burst 的加速效果。

### 练习 2：手写 Burst Job — 4 方向邻居平滑

1. 创建一个 MeshFilter 网格（如 128×128 的 Plane），读取顶点数据到 `NativeArray<float3>`
2. 实现一个 `IJobParallelFor`，对每个顶点计算 4 方向邻居的平均位置（简单平滑滤波）
3. 添加 `[BurstCompile]` 标记
4. Job 完成后将结果写回 Mesh
5. 在 Burst Inspector 中查看编译后的汇编代码

**提示**：
- 使用 `Mesh.GetNativeVertexBufferPtr`（高级）或 `Mesh.vertices`（简单但有一次拷贝）
- 注意边界顶点的处理（邻居不存在时，使用自身位置）

### 练习 3：完整 ECS 化粒子系统（挑战）

1. 基于示例 A 的粒子数据，实现完整的「初始化 → 更新 → 渲染」Job 管线
2. 使用 `IJobParallelForTransform` 直接操作 Transform（而非通过 NativeArray 中转）
3. 将渲染改为 `DrawMeshInstancedProcedural`（无 1023 限制的 GPU 实例化）
4. 对比三种方案的完整帧时间：MonoBehaviour → Job+NativeArray → Job+Transform+Procedural

**提示**：
- `DrawMeshInstancedProcedural` 需要将矩阵数据放在 GPU Buffer 中
- 使用 `ComputeBuffer` 配合 `Material.SetBuffer`

---

## 4. 扩展阅读

- Unity 官方文档：[C# Job System](https://docs.unity3d.com/Manual/JobSystem.html)
- Unity 官方文档：[Burst User Guide](https://docs.unity3d.com/Packages/com.unity.burst@latest)
- [Unity.Mathematics API Reference](https://docs.unity3d.com/Packages/com.unity.mathematics@latest)
- GDC 2018：[C# Job System + ECS by Mike Acton](https://www.youtube.com/watch?v=kwn5XO5YR0A)
- Unite 2022：[Burst Deep Dive: Optimizing for all platforms](https://www.youtube.com/results?search_query=Burst+Deep+Dive+Unite+2022)
- [Burst Inspector Guide](https://docs.unity3d.com/Packages/com.unity.burst@latest/manual/compilation-burstinspector.html)

---

## 常见陷阱

1. **Job 中访问托管对象**：这是最常见的 Burst 编译失败原因。如果在 Job 的 `Execute` 中访问 `Transform`、`GameObject` 或任何 `class` 引用，Burst 会拒绝编译。解决方案：将引用数据预先复制到 NativeContainer。

2. **忘记 Dispose NativeContainer**：`NativeArray` 等容器不会自动释放（它们不是托管对象），必须手动调用 `Dispose()`。泄漏检测器仅在 Editor 中报错，Release Build 中静默泄漏。

3. **在主线程过早 Complete**：`handle.Complete()` 会阻塞主线程直到 Job 完成。应该尽可能推迟 Complete，或使用 `JobHandle.ScheduleBatchedJobs()` 让 Job 尽早开始执行。

4. **过小的并行粒度**：`IJobParallelFor` 的 `innerloopBatchCount` 参数控制每个线程处理的最小元素数。如果单个元素工作太少（如只做一次加法），线程切换开销会超过计算本身。通常设为 64~256。

5. **Burst 的浮点精度差异**：`FloatMode.Fast` 下 Burst 不保证 IEEE 754 严格精度（如 NaN 传播、次正规数处理）。对确定性要求很高的场景（如网络同步的物理模拟），使用 `FloatMode.Strict`。

6. **忽略数据对齐**：Burst 自动向量化要求数据 16/32 字节对齐。`float3` 是 12 字节但会被填充到 16 字节。如果自行分配原始内存，需要注意对齐。

7. **NativeContainer 的 Temp Allocator 用于 Job**：`Allocator.Temp` 的内存仅在当前帧内有效，在 Job 中可能已被释放。始终使用 `Allocator.TempJob`（短生命周期 Job）或 `Allocator.Persistent`（长生命周期）。

8. **Schedule 后修改 NativeContainer**：一旦 Job 被 Schedule，就不应该从主线程修改传递给它的 NativeContainer（除非使用 `NativeArray` 的并发安全模式，但一般避免这样做）。
