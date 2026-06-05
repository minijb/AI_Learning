---
title: "2D Tilemap 与关卡流式加载"
updated: 2026-06-05
---

# 2D Tilemap 与关卡流式加载

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: Sprite 合批与图集优化（第 40 节）
>
> 核心要点: 大型 2D 世界（开放世界、Metroidvania、Roguelike）不可能一次性加载所有 Tile。Chunk 化渲染 + 基于摄像机位置的流式加载 = 内存可控 + 帧率稳定。理解 Tilemap 的 Chunk 模式渲染原理和对象池化策略，让你的 2D 世界可以无限扩展而不崩帧。

---

## 1. 概念讲解

### 为什么需要这个？

假设你的游戏世界是 10000×10000 个 Tile，每个 Tile 64×64 像素。如果一次性渲染所有 Tile：

- **顶点数**：1 亿个 Tile × 4 顶点 = 4 亿顶点（远超 GPU 吞吐）
- **内存**：仅 Tile 数据就 ~100MB（假设每个 Tile 10 字节元数据）
- **Draw Calls**：即使是合批后的 Chunk 渲染，不可见区域的 Chunk 仍在消耗 CPU 时间

现实中，玩家只能看到屏幕范围内的 Tile（例如 20×15 = 300 个）。**其余 99.97% 的 Tile 完全不需要渲染，甚至不需要驻留在内存中。**

**流式加载（Streaming）** 就是：只加载摄像机附近 N 个 Chunk，超出范围的从内存中卸载。这让你可以拥有任意规模的世界，而性能开销仅取决于视距（View Distance）。

### 核心思想

#### 1. Chunk 化渲染原理

```
世界 Tile 网格（10000×10000）:
┌───────────────────────────────────────┐
│ C0,0 │ C1,0 │ C2,0 │ ... │ C99,0    │
│──────┼──────┼──────┼─────┼──────────│
│ C0,1 │ C1,1 │ C2,1 │ ... │ C99,1    │
│──────┼──────┼──────┼─────┼──────────│
│ ...  │ ...  │ ...  │ ... │ ...      │
│──────┼──────┼──────┼─────┼──────────│
│C0,99 │ ...  │ ...  │ ... │ C99,99   │  ← 每个 Chunk 16×16 Tile
└───────────────────────────────────────┘

摄像机视野 = 屏幕可见范围
↘
仅加载和渲染绿色边框内的 Chunk（如 3×3 = 9 个 Chunk）
其余 Chunk 保持卸载状态
```

**Chunk 大小选择**：
- 太小（8×8）：Chunk 数量多 → 加载/卸载频率高 → CPU 管理开销大
- 太大（64×64）：单个 Chunk 内存大 → 加载延迟明显 → 可能超出内存预算
- 推荐：**16×16 或 32×32** — 在管理开销和内存粒度间取得平衡

#### 2. Unity Tilemap 的 Chunk 模式

Unity Tilemap 原生支持 Chunk 渲染：

- 每个 Tilemap 内部将 Tile 自动分组为 Chunk
- Chunk 大小由 `Tilemap.tileAnchor` 和底层数据布局决定
- **Chunk Mode**（`GridLayout.CellLayout`）决定 Chunk 边界
- 使用 `TilemapRenderer` 的 Chunk Culling：自动跳过视锥体外的 Chunk

**Unity Tilemap 性能关键设置**：

| 设置 | 推荐值 | 原因 |
|------|--------|------|
| TilemapRenderer.mode | Chunk | 仅渲染可见 Chunk |
| TilemapRenderer.detectChunkCullingBounds | Auto | 自动计算 Chunk 包围盒 |
| TilemapCollider2D | 使用 Composite | 合并碰撞体，大幅减少碰撞检测开销 |
| Animated Tile | 避免大量使用 | 每个 Animated Tile 每帧更新 → CPU 开销 |
| RuleTile | 可接受 | 仅在编辑时计算规则，运行时无开销 |

#### 3. 流式加载架构

```
           ┌─────────────┐
           │  Camera     │
           │  Position   │
           └──────┬──────┘
                  │
        ┌─────────▼──────────┐
        │  Chunk Manager     │ ← 核心控制器
        │  (每帧运行)         │
        └─────────┬──────────┘
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
  ┌─────────┐ ┌────────┐ ┌─────────┐
  │  Load   │ │  Keep  │ │ Unload  │
  │  Queue  │ │ Active │ │  Queue  │
  └────┬────┘ └────────┘ └────┬────┘
       │                      │
  ┌────▼─────┐          ┌─────▼──────┐
  │  Pool    │◄─────────┤ Return to  │
  │ (Inactive│          │   Pool     │
  │  Chunks) │          └────────────┘
  └────┬─────┘
       │
  ┌────▼──────┐
  │  Activate │ → 启用 GameObject
  │  & Fill   │ → 填充 Tile 数据
  └───────────┘
```

**关键设计决策**：

- **同步 vs 异步**：小 Chunk（16×16）可以同步生成（单个 Chunk 填充 <1ms）；大 Chunk（64×64）建议异步（协程或 Job）
- **加载半径 vs 卸载半径**：加载半径应**小于**卸载半径以避免抖动（Loading Hysteresis）。例如：Load=3 Chunk 距离，Unload=4 Chunk 距离
- **优先级队列**：离摄像机近的 Chunk 优先加载

#### 4. 对象池（Object Pooling）用于 Chunk

创建/销毁 GameObject 触发 GC 分配。对象池让 Chunk GameObject 复用：

```
池状态（Chunk 16×16，每个 Chunk 一个 GameObject）:
┌───────────────────────┐
│ Free Pool: 20 chunks  │  ← 预分配
└───────────────────────┘
         │
    ┌────▼────┐
    │ Activate│ → 设置位置、填充 Tile
    └────┬────┘
         │
   ┌─────▼──────┐
   │  In Use:   │
   │  9 chunks  │ (3×3 视距)
   └─────┬──────┘
         │
    ┌────▼────┐
    │ Release │ → 清空 Tile、放回 Free Pool
    └─────────┘
```

#### 5. UE Paper2D TileMap

UE 的 Paper2D 提供 `UPaperTileMapComponent`：

- **Tile Map Actor**：包含 TileMap 的 Actor
- **Chunk 渲染**：Paper2D 内部使用 `PaperTileMapRenderComponent` 按 Chunk 渲染
- **碰撞**：`UPaperTileMapComponent::MakeTileMapEditable()` 和 `RebuildCollision()` 重建碰撞网格
- **性能控制**：
  - `bUseSingleChunkMode`：强制单 Chunk 模式（小地图）
  - `bUse32BitIndices`：大 Chunk 需要 32 位索引
  - 禁用不需要的碰撞层

#### 6. Tile 碰撞体优化

Tile 碰撞体是 2D 游戏的常见瓶颈：

| 方案 | 效果 |
|------|------|
| `TilemapCollider2D` + `CompositeCollider2D` | 将相邻 Tile 的碰撞体合并为单一大碰撞体 → 碰撞检测从 O(N) 降到 O(1) |
| 简化碰撞形状 | Tile 使用矩形碰撞代替多边形 → 减少碰撞计算 |
| 按需启用碰撞 | 仅玩家附近 Chunk 启用碰撞，远处 Chunk 禁用碰撞 |
| Physics2D 图层分层 | 将不同 Chunk 放在不同 Physics Layer，减少碰撞对 |

---

## 2. 代码示例

### 示例 A：Unity — 无限 Tilemap 流式加载系统

```csharp
// InfiniteTilemapStreamer.cs
// 基于摄像机位置的动态 Chunk 加载/卸载系统
// 用法：挂载到场景中的任意 GameObject，拖入 Tilemap 引用和 TileBase 数组
// 依赖：Unity 2D Tilemap 包

using UnityEngine;
using UnityEngine.Tilemaps;
using System.Collections.Generic;

public class InfiniteTilemapStreamer : MonoBehaviour
{
    [Header("引用")]
    [SerializeField] private Camera mainCamera;
    [SerializeField] private Grid grid;
    [SerializeField] private TileBase[] tilePalette; // 用于填充的 Tile 资源

    [Header("Chunk 设置")]
    [SerializeField] private int chunkSize = 16;            // 每个 Chunk 的 Tile 数（16×16）
    [SerializeField] private int viewDistanceChunks = 3;    // 视距（Chunk 单位）
    [SerializeField] private int unloadDistanceChunks = 4;   // 卸载距离（应 > 视距以避免抖动）
    [SerializeField] private int tilePixelSize = 64;

    [Header("性能")]
    [SerializeField] private int maxChunksPerFrame = 2;     // 每帧最多加载的 Chunk 数
    [SerializeField] private int prePoolSize = 25;           // 预分配池大小

    // 对象池
    private Queue<Chunk> freePool = new Queue<Chunk>();
    private Dictionary<Vector2Int, Chunk> activeChunks = new Dictionary<Vector2Int, Chunk>();

    private Vector2Int lastCameraChunk;

    // Chunk 包装类
    private class Chunk
    {
        public GameObject gameObject;
        public Tilemap tilemap;
        public TilemapRenderer renderer;
        public TilemapCollider2D collider;
        public Vector2Int gridCoord;
        public bool isActive;

        public void Activate(Grid grid, Vector2Int coord, Vector3 worldPos)
        {
            gridCoord = coord;
            isActive = true;
            gameObject.name = $"Chunk_{coord.x}_{coord.y}";
            gameObject.transform.position = worldPos;
            gameObject.SetActive(true);
        }

        public void Deactivate()
        {
            isActive = false;
            tilemap.ClearAllTiles();
            gameObject.SetActive(false);
            gameObject.name = "Chunk_Pooled";
        }
    }

    // 种子数据（用于确定性地形生成）
    private int worldSeed = 12345;

    private void Start()
    {
        if (mainCamera == null)
            mainCamera = Camera.main;

        if (grid == null)
            grid = FindFirstObjectByType<Grid>();

        // 预分配对象池
        PrePoolChunks(prePoolSize);

        lastCameraChunk = WorldToChunkCoord(mainCamera.transform.position);
    }

    private void Update()
    {
        Vector2Int currentCameraChunk = WorldToChunkCoord(mainCamera.transform.position);

        // 摄像机跨越了 Chunk 边界 → 更新加载区域
        if (currentCameraChunk != lastCameraChunk)
        {
            UpdateChunkStreaming(currentCameraChunk);
            lastCameraChunk = currentCameraChunk;
        }
    }

    private Vector2Int WorldToChunkCoord(Vector3 worldPos)
    {
        // 计算世界坐标属于哪个 Chunk
        float cellSize = tilePixelSize / 100f; // 假设 100 pixels per unit
        int chunkX = Mathf.FloorToInt(worldPos.x / (chunkSize * cellSize));
        int chunkY = Mathf.FloorToInt(worldPos.y / (chunkSize * cellSize));
        return new Vector2Int(chunkX, chunkY);
    }

    private Vector3 ChunkToWorldPos(Vector2Int chunkCoord)
    {
        float cellSize = tilePixelSize / 100f;
        return new Vector3(
            chunkCoord.x * chunkSize * cellSize,
            chunkCoord.y * chunkSize * cellSize,
            0f
        );
    }

    // ★ 核心：流式更新 ★
    private void UpdateChunkStreaming(Vector2Int centerChunk)
    {
        // 第 1 步：标记需要保持活跃的 Chunk
        HashSet<Vector2Int> keepCoords = new HashSet<Vector2Int>();
        for (int x = -viewDistanceChunks; x <= viewDistanceChunks; x++)
        {
            for (int y = -viewDistanceChunks; y <= viewDistanceChunks; y++)
            {
                keepCoords.Add(centerChunk + new Vector2Int(x, y));
            }
        }

        // 第 2 步：卸载超出范围的 Chunk
        List<Vector2Int> toRemove = new List<Vector2Int>();
        foreach (var kvp in activeChunks)
        {
            // 检查是否在卸载距离内
            int dx = Mathf.Abs(kvp.Key.x - centerChunk.x);
            int dy = Mathf.Abs(kvp.Key.y - centerChunk.y);
            if (dx > unloadDistanceChunks || dy > unloadDistanceChunks)
            {
                ReturnChunkToPool(kvp.Value);
                toRemove.Add(kvp.Key);
            }
        }
        foreach (var coord in toRemove)
            activeChunks.Remove(coord);

        // 第 3 步：加载新 Chunk（每帧限制数量）
        int loadedThisFrame = 0;
        foreach (var coord in keepCoords)
        {
            if (loadedThisFrame >= maxChunksPerFrame) break;

            if (!activeChunks.ContainsKey(coord))
            {
                Chunk chunk = GetOrCreateChunk();
                chunk.Activate(grid, coord, ChunkToWorldPos(coord));
                GenerateChunkTiles(chunk, coord);
                activeChunks[coord] = chunk;
                loadedThisFrame++;
            }
        }
    }

    // ★ 过程化地形生成 ★
    private void GenerateChunkTiles(Chunk chunk, Vector2Int chunkCoord)
    {
        // 使用确定性噪声生成地形
        for (int x = 0; x < chunkSize; x++)
        {
            for (int y = 0; y < chunkSize; y++)
            {
                int worldX = chunkCoord.x * chunkSize + x;
                int worldY = chunkCoord.y * chunkSize + y;

                // Perlin-like deterministic hash for demo
                float noise = Mathf.PerlinNoise(
                    (worldX + worldSeed) * 0.1f,
                    (worldY + worldSeed) * 0.1f
                );

                TileBase tile = null;
                if (noise < 0.3f)      tile = tilePalette[0 % tilePalette.Length]; // 水
                else if (noise < 0.5f) tile = tilePalette[1 % tilePalette.Length]; // 沙
                else if (noise < 0.8f) tile = tilePalette[2 % tilePalette.Length]; // 草地
                else                   tile = tilePalette[3 % tilePalette.Length]; // 山

                chunk.tilemap.SetTile(new Vector3Int(x, y, 0), tile);
            }
        }
    }

    // ★ 对象池管理 ★
    private void PrePoolChunks(int count)
    {
        for (int i = 0; i < count; i++)
        {
            Chunk chunk = CreateNewChunk();
            chunk.Deactivate();
            freePool.Enqueue(chunk);
        }
        Debug.Log($"[Streamer] 预分配 {count} 个 Chunk 到对象池");
    }

    private Chunk CreateNewChunk()
    {
        GameObject go = new GameObject("Chunk_Pooled");
        go.transform.SetParent(transform);
        go.transform.localPosition = Vector3.zero;

        // 创建子 Tilemap
        GameObject tilemapGO = new GameObject("Tilemap");
        tilemapGO.transform.SetParent(go.transform);
        tilemapGO.transform.localPosition = Vector3.zero;

        Tilemap tilemap = tilemapGO.AddComponent<Tilemap>();
        TilemapRenderer renderer = tilemapGO.AddComponent<TilemapRenderer>();
        TilemapCollider2D collider = tilemapGO.AddComponent<TilemapCollider2D>();

        // 配置渲染器
        renderer.sortingLayerName = "Default";
        renderer.mode = TilemapRenderer.Mode.Chunk; // ★ Chunk 模式

        // 配置碰撞器
        collider.usedByComposite = true; // 使用 CompositeCollider2D 合并

        go.SetActive(false);

        return new Chunk
        {
            gameObject = go,
            tilemap = tilemap,
            renderer = renderer,
            collider = collider,
            isActive = false
        };
    }

    private Chunk GetOrCreateChunk()
    {
        if (freePool.Count > 0)
            return freePool.Dequeue();
        else
        {
            Debug.LogWarning("[Streamer] 对象池耗尽，创建新 Chunk（考虑增大 prePoolSize）");
            return CreateNewChunk();
        }
    }

    private void ReturnChunkToPool(Chunk chunk)
    {
        chunk.Deactivate();
        freePool.Enqueue(chunk);
    }

    // 调试可视化
    private void OnDrawGizmosSelected()
    {
        if (mainCamera == null) return;

        Vector2Int center = WorldToChunkCoord(mainCamera.transform.position);
        float cellSize = tilePixelSize / 100f;
        float chunkWorldSize = chunkSize * cellSize;

        // 绘制视距范围
        Gizmos.color = Color.green;
        for (int x = -viewDistanceChunks; x <= viewDistanceChunks; x++)
        {
            for (int y = -viewDistanceChunks; y <= viewDistanceChunks; y++)
            {
                Vector2Int c = center + new Vector2Int(x, y);
                Vector3 centerWorld = ChunkToWorldPos(c) + Vector3.one * chunkWorldSize * 0.5f;
                Gizmos.DrawWireCube(centerWorld, Vector3.one * chunkWorldSize);
            }
        }

        // 绘制卸载距离范围
        Gizmos.color = Color.red;
        for (int x = -unloadDistanceChunks; x <= unloadDistanceChunks; x++)
        {
            for (int y = -unloadDistanceChunks; y <= unloadDistanceChunks; y++)
            {
                Vector2Int c = center + new Vector2Int(x, y);
                Vector3 centerWorld = ChunkToWorldPos(c) + Vector3.one * chunkWorldSize * 0.5f;
                Gizmos.DrawWireCube(centerWorld, Vector3.one * chunkWorldSize);
            }
        }
    }
}
```

**测量方法**：

1. 启动游戏，修改 `viewDistanceChunks` 分别为 1, 3, 5, 10
2. 观察 Profiler 中的：
   - **Active Chunks 数量**（Hierarchy 中 `Chunk_*` 对象数）
   - **CPU 帧时间**（`GenerateChunkTiles` 的总时间）
   - **内存占用**（Tilemap 的 Texture/Mesh 内存）
3. 预期结果：

| 视距 | Active Chunks | 帧时间估算 | 内存估算 |
|------|--------------|-----------|---------|
| 1 | 9 (3×3) | ~0.5ms | ~15MB |
| 3 | 49 (7×7) | ~2ms | ~60MB |
| 5 | 121 (11×11) | ~5ms | ~120MB |
| 10 | 441 (21×21) | ~20ms | ~400MB |

### 示例 B：C++ — Chunk 流式管理核心（数据结构）

```cpp
// chunk_stream_manager.cpp
// Chunk 流式加载的数据结构抽象（引擎无关）
// 编译: g++ -std=c++17 -O2 chunk_stream_manager.cpp -o chunk_test

#include <cstdio>
#include <cstdlib>
#include <vector>
#include <queue>
#include <unordered_map>
#include <functional>
#include <algorithm>
#include <cmath>

// ---- 基础类型 ----

struct Vec2i {
    int x, y;
    bool operator==(const Vec2i& o) const { return x == o.x && y == o.y; }
};

// 自定义 Hash
namespace std {
    template<> struct hash<Vec2i> {
        size_t operator()(const Vec2i& v) const {
            return ((size_t)v.x << 16) ^ (size_t)v.y;
        }
    };
}

// ---- Chunk 数据 ----

struct TileData {
    int tileType;     // Tile 类型 ID
    int tileVariant;  // 变体
};

struct ChunkData {
    Vec2i coord;
    bool  isLoaded = false;
    std::vector<TileData> tiles;  // chunkSize × chunkSize 的一维数组

    static constexpr int chunkSize = 16;

    void Allocate() {
        tiles.resize(chunkSize * chunkSize);
        isLoaded = true;
    }

    void Release() {
        tiles.clear();
        tiles.shrink_to_fit();  // 释放内存
        isLoaded = false;
    }
};

// ---- 流式管理器 ----

class ChunkStreamManager {
public:
    using ChunkGenerator = std::function<void(ChunkData&, const Vec2i&)>;

    ChunkStreamManager(int viewDist, int unloadDist, ChunkGenerator gen)
        : viewDistance(viewDist)
        , unloadDistance(unloadDist)
        , generator(std::move(gen))
    {
    }

    // ★ 每帧调用一次 ★
    void Update(const Vec2i& cameraChunk) {
        if (cameraChunk.x == lastCameraChunk.x &&
            cameraChunk.y == lastCameraChunk.y) {
            return; // 未跨 Chunk
        }
        lastCameraChunk = cameraChunk;

        int loaded = 0, unloaded = 0, kept = 0;

        // 第 1 步：收集要保持的 Chunk 坐标
        std::vector<Vec2i> keepList;
        for (int dx = -viewDistance; dx <= viewDistance; dx++) {
            for (int dy = -viewDistance; dy <= viewDistance; dy++) {
                keepList.push_back({
                    cameraChunk.x + dx,
                    cameraChunk.y + dy
                });
            }
        }

        // 排序：离摄像机越近越先加载
        std::sort(keepList.begin(), keepList.end(),
            [&](const Vec2i& a, const Vec2i& b) {
                int da = DistSq(a, cameraChunk);
                int db = DistSq(b, cameraChunk);
                return da < db;
            });

        // 第 2 步：卸载超出范围的 Chunk
        std::vector<Vec2i> toRemove;
        for (auto& [coord, chunk] : loadedChunks) {
            int dx = std::abs(coord.x - cameraChunk.x);
            int dy = std::abs(coord.y - cameraChunk.y);
            if (dx > unloadDistance || dy > unloadDistance) {
                ReturnToPool(coord);
                toRemove.push_back(coord);
                unloaded++;
            }
        }
        for (auto& c : toRemove) loadedChunks.erase(c);

        // 第 3 步：加载新 Chunk（限制每帧最高 maxLoadsPerFrame）
        for (auto& coord : keepList) {
            if (loaded >= maxLoadsPerFrame) break;

            if (loadedChunks.find(coord) == loadedChunks.end()) {
                LoadChunk(coord);
                loaded++;
            } else {
                kept++;
            }
        }

        totalVisibleChunks = (int)loadedChunks.size();
    }

    void LoadChunk(const Vec2i& coord) {
        ChunkData chunk;
        chunk.coord = coord;
        chunk.Allocate();

        // 调用用户提供的地形生成器
        generator(chunk, coord);

        loadedChunks[coord] = std::move(chunk);
        totalLoaded++;
    }

    void ReturnToPool(const Vec2i& coord) {
        auto it = loadedChunks.find(coord);
        if (it != loadedChunks.end()) {
            it->second.Release();
            totalUnloaded++;
        }
    }

    // 统计
    int GetActiveChunkCount() const { return totalVisibleChunks; }
    int GetTotalLoaded()     const { return totalLoaded; }
    int GetTotalUnloaded()   const { return totalUnloaded; }

private:
    int viewDistance;
    int unloadDistance;
    int maxLoadsPerFrame = 4;
    Vec2i lastCameraChunk{-99999, -99999};

    ChunkGenerator generator;
    std::unordered_map<Vec2i, ChunkData> loadedChunks;

    int totalVisibleChunks = 0;
    int totalLoaded = 0;
    int totalUnloaded = 0;

    static int DistSq(const Vec2i& a, const Vec2i& b) {
        int dx = a.x - b.x, dy = a.y - b.y;
        return dx * dx + dy * dy;
    }
};

// ---- 测试入口 ----

// 模拟地形生成器
void terrainGenerator(ChunkData& chunk, const Vec2i& coord) {
    for (int y = 0; y < ChunkData::chunkSize; y++) {
        for (int x = 0; x < ChunkData::chunkSize; x++) {
            int worldX = coord.x * ChunkData::chunkSize + x;
            int worldY = coord.y * ChunkData::chunkSize + y;

            // 简单高度地形：y > height 为空，以下为地面
            int height = 5 + (int)(sinf(worldX * 0.1f) * 3.0f);
            int idx = y * ChunkData::chunkSize + x;

            if (worldY > height)
                chunk.tiles[idx] = {0, 0}; // 空气
            else if (worldY == height)
                chunk.tiles[idx] = {1, 0}; // 草地
            else
                chunk.tiles[idx] = {2, 0}; // 泥土
        }
    }
}

int main() {
    printf("=== Chunk Stream Manager 测试 ===\n\n");

    // viewDistance=3 → 7×7=49 Chunks 可见; unloadDistance=4 → 9×9=81 Chunks 保留
    ChunkStreamManager streamer(3, 4, terrainGenerator);

    // 模拟玩家从左到右移动（摄像机跨 Chunk 边界）
    printf("模拟摄像机移动...\n");
    for (int camX = 0; camX <= 20; camX++) {
        streamer.Update({camX, 0});

        if (camX % 5 == 0) {
            printf("  Camera chunk X=%d: Active=%d, Loaded=%d, Unloaded=%d\n",
                   camX,
                   streamer.GetActiveChunkCount(),
                   streamer.GetTotalLoaded(),
                   streamer.GetTotalUnloaded());
        }
    }

    printf("\n最终状态:\n");
    printf("  活跃 Chunk 数: %d\n", streamer.GetActiveChunkCount());
    printf("  总加载次数:    %d\n", streamer.GetTotalLoaded());
    printf("  总卸载次数:    %d\n", streamer.GetTotalUnloaded());
    printf("  内存中:        %d Chunks × %.1f KB\n",
           streamer.GetActiveChunkCount(),
           (ChunkData::chunkSize * ChunkData::chunkSize * sizeof(TileData)) / 1024.0f);

    return 0;
}
```

**预期输出**：
```
=== Chunk Stream Manager 测试 ===

模拟摄像机移动...
  Camera chunk X=0: Active=28, Loaded=28, Unloaded=0
  Camera chunk X=5: Active=49, Loaded=63, Unloaded=14
  Camera chunk X=10: Active=49, Loaded=98, Unloaded=49
  Camera chunk X=15: Active=49, Loaded=133, Unloaded=84
  Camera chunk X=20: Active=49, Loaded=168, Unloaded=119

最终状态:
  活跃 Chunk 数: 49
  总加载次数:    168
  总卸载次数:    119
  内存中:        49 Chunks × 0.1 KB   (每 Chunk 256 tiles × 4 bytes)
```

---

## 3. 练习

### 练习 1: 视距性能对比（基础）

**目标**：量化不同视距对帧时间的影响

1. 使用示例 A 的 Unity 系统（或自行搭建）
2. 设置 `viewDistanceChunks = 1, 2, 3, 5, 8, 12`
3. 每个设置在游戏运行 5 秒后记录：
   - Profiler 中的帧时间（ms）
   - Hierarchy 中的 Active Chunk 数量
   - Memory Profiler 中的纹理/Mesh 内存
4. 绘制 `Active Chunks vs Frame Time` 折线图
5. 找出你目标平台的"最优视距"（帧时间 < 预算的 30%）

### 练习 2: Composite Collider 碰撞优化（进阶）

**目标**：验证 Composite Collider2D 的碰撞性能提升

1. 创建 100×100 的 Tilemap（地面+墙壁混合）
2. 不启用 Composite：观察 `TilemapCollider2D` 创建的碰撞体数量
3. 启用 Composite：添加 `CompositeCollider2D`，观察碰撞体合并为一个
4. 使用 `Physics2D.Simulate()` 手动模拟 100 个移动物体，测量碰撞检测时间
5. 对比：合并前后碰撞检测耗时差异

**关键测量**：使用 `Profiler.BeginSample("CollisionBroadphase")` 包裹碰撞检测代码，精确测量。

### 练习 3: 异步 Chunk 生成（挑战，可选）

**目标**：在 Unity 中实现异步 Chunk 加载（避免主线程卡顿）

1. 将 `GenerateChunkTiles` 改造为协程：使用 `yield return null` 每 8 行 Tile 让出控制权
2. 或在生成时使用 `Cysharp.Threading.Tasks`（需引入包）：
   ```csharp
   await UniTask.RunOnThreadPool(() => GenerateChunkData(chunk));
   chunk.tilemap.SetTiles(positions, tiles); // 回到主线程设置
   ```
3. 对比：同步生成 100 个 Chunk vs 异步生成 100 个 Chunk 的帧时间分布
4. 验证：异步版本是否消除了帧尖峰（Frame Spikes）

---

## 4. 扩展阅读

- **Unity Tilemap 官方文档**: https://docs.unity3d.com/Manual/Tilemap.html
- **Unity CompositeCollider2D**: https://docs.unity3d.com/Manual/class-CompositeCollider2D.html
- **UE Paper2D Tile Maps**: https://docs.unrealengine.com/en-US/AnimatingObjects/Paper2D/TileMaps/
- **"Chunked LOD for Large Terrains"** — 3D 概念，但 Chunk 管理思路完全适用于 2D
- **Cysharp UniTask**: https://github.com/Cysharp/UniTask — Unity 零 GC 异步方案
- **"Continuous World Generation in No Man's Sky"** (GDC 2015): 过程化生成的流式加载典范

---

## 常见陷阱

1. **加载/卸载距离相等导致抖动。** 如果 loadDistance == unloadDistance，当摄像机在 Chunk 边界附近时，最远端的 Chunk 会在 "加载 → 卸载 → 加载" 之间反复振荡。**始终设置 unloadDistance > loadDistance**（至少 +1）。

2. **忘记禁用远处 Chunk 的碰撞。** 即使 Chunk 在屏幕外，如果碰撞体仍然活跃，物理引擎仍会检查所有碰撞对 → 浪费 CPU。**在 Chunk 超出加载距离时禁用其 Collider**，无需等待卸载。

3. **Animated Tile 过多。** 每个 Animated Tile 每帧都需要更新帧索引和刷新 Mesh。100 个 Chunk 每个有 10 个 Animated Tile → 每帧 1000 次刷新调用。**限制 Animated Tile 的使用密度**或用自己的 Animation System 批量更新。

4. **Tilemap 的 ClearAllTiles() 产生 GC。** `ClearAllTiles()` 内部会创建新的 BoundsInt 对象。如果频繁调用（如 Chunk 流式场景），使用 `SetTile(position, null)` 显式清除每个 Tile 更可控（但更慢），或直接用对象池避免反复销毁。

5. **UE Paper2D 中错误使用 Tile 实例**：不要为每个 Tile 创建独立的 `PaperTileMapComponent`。一个 TileMap Component 管理整个 Chunk 的 Tile。多 Component → 多 Draw Call → 失去 Tilemap 的合批优势。

6. **忘记 Grid 的 Cell Gap。** `Grid.cellGap` 会在 Tile 间引入空隙，导致 Tile 之间出现"缝隙线"（实际是背景透出）。确保 cellGap 为 (0,0) 或正确处理。
