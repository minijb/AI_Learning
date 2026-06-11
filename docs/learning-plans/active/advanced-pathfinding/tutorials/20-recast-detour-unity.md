---
title: "Recast/Detour 与 Unity 集成"
updated: 2026-06-05
---

# Recast/Detour 与 Unity 集成

> 所属计划: 高阶寻路系统
> 预计耗时: 30min
> 前置知识: Recast NavMesh 生成管线（18），Detour 运行时查询（19），Unity C# 基础，C++/C# 互操作（P/Invoke）

## 1. 概念讲解

### 为什么需要这个？

Unity 内置了 NavMesh 系统（`NavMeshSurface` + `NavMeshAgent`），但它有结构性限制：

| 限制 | Unity 内置 NavMesh | Recast/Detour 原生 |
|------|-------------------|-------------------|
| 烘焙时机 | 仅编辑器时离线烘焙 | 支持运行时生成（服务器端、程序化地图） |
| 动态更新 | 仅 NavMeshObstacle 雕刻 | Tile Cache 支持局部重烘焙 |
| 多平台一致性 | 每个平台的烘焙结果略有差异 | 相同输入 → 相同输出（确定性） |
| 内存控制 | 黑盒管理 | 完全可控（瓦片大小、流式加载） |
| 服务器端 | 不可用（Unity 是客户端引擎） | 完全可用（纯 C++ 无 Unity 依赖） |
| 自定义代价 | 仅 Area Mask | 完全自定义 `dtQueryFilter` |

**何时用原生 Recast/Detour 而非 Unity NavMesh？**

- **服务器端寻路**: MMO 服务端验证玩家移动合法性 → 纯 C++ Detour
- **程序化地图**: Roguelike 地牢每次运行都需要重新生成 NavMesh
- **运行时地形修改**: Minecraft 风格的世界修改 → Tile Cache 增量更新
- **需要确定性**: 跨平台/跨客户端一致的 NavMesh 结果
- **大世界流式加载**: 按需加载/卸载 NavMesh 瓦片

**何时用 Unity 内置 NavMesh？**

- 中小型静态关卡
- 不需要服务端寻路
- 团队不熟悉 C++ 互操作
- 需要 Unity Editor 的可视化工具和 Component 工作流

### 核心思路：三层桥接

```
Unity C# Layer (MonoBehaviour)
    │
    ▼  P/Invoke
Native Plugin Layer (C++ DLL/so/dylib)
    │  ├── 自定义 wrapper (导出 C 函数)
    │  └── Recast/Detour 库 (静态链接或源码内嵌)
    │
    ▼
Recast/Detour (纯 C++ 导航逻辑)
```

**三种集成方案**：

| 方案 | 复杂度 | 性能 | 适用场景 |
|------|--------|------|---------|
| **方案 A: P/Invoke 包装器** | 中 | 高 | 已有 C++ 代码，需要 C# 调用 |
| **方案 B: 纯 C# 移植** | 高 | 中 | 需要 IL2CPP 兼容性、无原生依赖 |
| **方案 C: Unity 组件桥** | 低 | 中 | 只在 Editor 用 Recast 烘焙，运行时用 Unity NavMesh |

本节聚焦**方案 A —— P/Invoke 包装器**，这是最常见的生产路径。

### 架构设计

```
Unity 端:
  RecastBridge.cs         ← C# wrapper (P/Invoke 声明)
  RecastNavMeshBaker.cs   ← 收集场景几何体，调用烘焙
  DetourPathfinder.cs     ← 运行时寻路组件
  DetourDebugDraw.cs      ← Gizmos/GL 可视化

C++ Plugin 端:
  recast_unity_bridge.cpp ← C 函数导出 (extern "C")
    ├── recast_bake()       → 调用完整 Recast 管线
    ├── detour_load()       → 加载 .navmesh 文件
    ├── detour_find_path()  → A* + 漏斗
    └── detour_raycast()    → 射线投射
```

### 数据传递策略

C# 和 C++ 之间的数据传递是互操作的核心难点：

**浮点数组**（顶点、三角形坐标）:
```csharp
// C# 端: 固定大小的托管数组 → 传递指针
float[] verts = new float[vertCount * 3];
// 固定数组防止 GC 移动
GCHandle handle = GCHandle.Alloc(verts, GCHandleType.Pinned);
IntPtr ptr = handle.AddrOfPinnedObject();
// 调用 native
recast_bake(ptr, vertCount, triIndices, triCount, out navDataSize);
handle.Free();
```

**NavMesh 数据（二进制块）**:
```csharp
// Native 端分配内存，C# 端读取后释放
[DllImport("recast_unity_bridge")]
static extern IntPtr recast_bake(IntPtr verts, int vertCount,
                                  IntPtr tris, int triCount,
                                  out int dataSize);

// C# 端 Marshal
IntPtr navData = recast_bake(vertsPtr, vertCount, trisPtr, triCount, out int size);
byte[] managed = new byte[size];
Marshal.Copy(navData, managed, 0, size);
recast_free_buffer(navData);  // Native 端释放
```

**路径结果（变长数组）**:
```csharp
// 两次调用模式: 第一次获取大小，第二次获取数据
[DllImport("recast_unity_bridge")]
static extern int detour_find_path(
    IntPtr navMeshData, int dataSize,
    float startX, float startY, float startZ,
    float endX, float endY, float endZ,
    IntPtr outPath, int maxPathPoints);

// 使用:
float[] pathBuffer = new float[maxPoints * 3];
GCHandle handle = GCHandle.Alloc(pathBuffer, GCHandleType.Pinned);
int count = detour_find_path(..., handle.AddrOfPinnedObject(), maxPoints);
handle.Free();
// pathBuffer[0..count*3-1] 现在包含 [x,y,z, x,y,z, ...]
```

### Unity 的 IL2CPP 注意事项

Unity 在 iOS 和 console 上使用 IL2CPP（AOT 编译），这意味着：

- **不要使用 `Marshal.GetDelegateForFunctionPointer`**（AOT 不支持）
- 使用 `__Internal` 作为 DLL 名（静态链接）：`[DllImport("__Internal")]`
- 避免复杂的泛型 Marshal 操作

## 2. 代码示例

### 2a: C++ Native Plugin (recast_unity_bridge.cpp)

```cpp
// recast_unity_bridge.cpp — Unity P/Invoke 的 C++ 桥梁
//
// 编译 (Windows):
//   cl /LD /O2 recast_unity_bridge.cpp Recast/Source/*.cpp Detour/Source/*.cpp
//      /I Recast/Include /I Detour/Include
//      /Fe:recast_unity_bridge.dll
//
// 编译 (Linux/Mac):
//   g++ -std=c++11 -shared -fPIC -O2 recast_unity_bridge.cpp *.cpp
//       -I Recast/Include -I Detour/Include
//       -o libRecastUnityBridge.so

#include "Recast.h"
#include "DetourNavMesh.h"
#include "DetourNavMeshQuery.h"
#include "DetourCommon.h"
#include <cstdlib>
#include <cstring>

#ifdef _MSC_VER
#define EXPORT_API extern "C" __declspec(dllexport)
#else
#define EXPORT_API extern "C" __attribute__((visibility("default")))
#endif

// ============================================================
// 共享配置
// ============================================================
struct SharedContext {
    dtNavMesh* navMesh;
    dtNavMeshQuery* query;
    dtQueryFilter* filter;
};

// 静态单例 (简化; 生产代码应使用 context handle)
static SharedContext g_ctx;

// ============================================================
// 1. Recast 烘焙: Mesh数据 → NavMesh 二进制块
// ============================================================
EXPORT_API int recast_bake(
    const float* verts, int vertCount,
    const int* triIndices, int triCount,
    unsigned char** outData, int* outDataSize,
    float cellSize, float cellHeight,
    float agentHeight, float agentRadius,
    float agentMaxSlope, float agentMaxClimb)
{
    // ---- 包围盒 ----
    float bmin[3] = { 1e10f, 1e10f, 1e10f };
    float bmax[3] = { -1e10f, -1e10f, -1e10f };
    for (int i = 0; i < vertCount; ++i) {
        float v = verts[i*3], v1 = verts[i*3+1], v2 = verts[i*3+2];
        if (v < bmin[0]) bmin[0] = v;
        if (v1 < bmin[1]) bmin[1] = v1;
        if (v2 < bmin[2]) bmin[2] = v2;
        if (v > bmax[0]) bmax[0] = v;
        if (v1 > bmax[1]) bmax[1] = v1;
        if (v2 > bmax[2]) bmax[2] = v2;
    }

    // ---- Recast 配置 ----
    rcConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.cs = cellSize;
    cfg.ch = cellHeight;
    cfg.walkableSlopeAngle = agentMaxSlope;
    cfg.walkableHeight = (int)ceilf(agentHeight / cfg.ch);
    cfg.walkableClimb = (int)ceilf(agentMaxClimb / cfg.ch);
    cfg.walkableRadius = (int)ceilf(agentRadius / cfg.cs);
    cfg.maxEdgeLen = (int)(12.0f / cfg.cs);
    cfg.maxSimplificationError = 1.3f;
    cfg.minRegionArea = (int)rcSqr(8.0f);
    cfg.mergeRegionArea = (int)rcSqr(20.0f);
    cfg.maxVertsPerPoly = 6;
    cfg.detailSampleDist = cfg.cs * 6.0f;
    cfg.detailSampleMaxError = cfg.ch * 1.0f;
    cfg.borderSize = cfg.walkableRadius + 3;
    rcVcopy(cfg.bmin, bmin);
    rcVcopy(cfg.bmax, bmax);
    cfg.width  = cfg.borderSize*2 + (int)((cfg.bmax[0]-cfg.bmin[0])/cfg.cs);
    cfg.height = cfg.borderSize*2 + (int)((cfg.bmax[2]-cfg.bmin[2])/cfg.cs);

    // ---- 阶段 1-2: 体素化 + 过滤 ----
    rcHeightfield* hf = rcAllocHeightfield();
    if (!rcCreateHeightfield(nullptr, *hf, cfg.width, cfg.height,
                              cfg.bmin, cfg.bmax, cfg.cs, cfg.ch)) {
        rcFreeHeightField(hf);
        return -1;
    }

    unsigned char* triAreas = new unsigned char[triCount];
    memset(triAreas, RC_WALKABLE_AREA, triCount);

    rcRasterizeTriangles(nullptr, verts, vertCount,
                          triIndices, triAreas, triCount, *hf, cfg.walkableClimb);
    delete[] triAreas;

    rcFilterLowHangingWalkableObstacles(nullptr, cfg.walkableClimb, *hf);
    rcFilterLedgeSpans(nullptr, cfg.walkableHeight, cfg.walkableClimb, *hf);
    rcFilterWalkableLowHeightSpans(nullptr, cfg.walkableHeight, *hf);

    // ---- 阶段 3: 区域 ----
    rcCompactHeightfield* chf = rcAllocCompactHeightfield();
    rcBuildCompactHeightfield(nullptr, cfg.walkableHeight, cfg.walkableClimb, *hf, *chf);
    rcFreeHeightField(hf);

    rcErodeWalkableArea(nullptr, cfg.walkableRadius, *chf);
    rcBuildDistanceField(nullptr, *chf);
    rcBuildRegions(nullptr, *chf, cfg.borderSize, cfg.minRegionArea, cfg.mergeRegionArea);

    // ---- 阶段 4: 轮廓 ----
    rcContourSet* cset = rcAllocContourSet();
    rcBuildContours(nullptr, *chf, cfg.maxSimplificationError, cfg.maxEdgeLen, *cset);

    // ---- 阶段 5: 多边形剖分 ----
    rcPolyMesh* pmesh = rcAllocPolyMesh();
    rcBuildPolyMesh(nullptr, *cset, cfg.maxVertsPerPoly, *pmesh);

    // ---- 阶段 6: 细节网格 ----
    rcPolyMeshDetail* dmesh = rcAllocPolyMeshDetail();
    rcBuildPolyMeshDetail(nullptr, *pmesh, *chf,
                           cfg.detailSampleDist, cfg.detailSampleMaxError, *dmesh);

    // ---- 构建 Detour NavMesh 数据 ----
    dtNavMeshCreateParams params;
    memset(&params, 0, sizeof(params));
    params.verts = pmesh->verts;
    params.vertCount = pmesh->nverts;
    params.polys = pmesh->polys;
    params.polyAreas = pmesh->areas;
    params.polyFlags = pmesh->flags;
    params.polyCount = pmesh->npolys;
    params.nvp = pmesh->nvp;
    params.detailMeshes = dmesh->meshes;
    params.detailVerts = dmesh->verts;
    params.detailVertsCount = dmesh->nverts;
    params.detailTris = dmesh->tris;
    params.detailTriCount = dmesh->ntris;

    // 最终: 创建 tile 二进制数据
    unsigned char* navData = nullptr;
    int navDataSize = 0;
    bool ok = dtCreateNavMeshData(&params, &navData, &navDataSize);

    if (ok) {
        *outData = navData;
        *outDataSize = navDataSize;
    } else {
        *outData = nullptr;
    }

    rcFreeContourSet(cset);
    rcFreeCompactHeightfield(chf);
    rcFreePolyMesh(pmesh);
    rcFreePolyMeshDetail(dmesh);

    return ok ? navDataSize : -1;
}

// ============================================================
// 2. 释放 Recast 分配的内存
// ============================================================
EXPORT_API void recast_free_buffer(unsigned char* data) {
    dtFree(data);
}

// ============================================================
// 3. Detour: 加载 NavMesh 数据到运行时
// ============================================================
EXPORT_API bool detour_init_navmesh(const unsigned char* data, int dataSize,
                                     float tileWidth, float tileHeight) {
    // 释放旧数据
    if (g_ctx.query) { dtFreeNavMeshQuery(g_ctx.query); g_ctx.query = nullptr; }
    if (g_ctx.navMesh) { dtFreeNavMesh(g_ctx.navMesh); g_ctx.navMesh = nullptr; }
    delete g_ctx.filter; g_ctx.filter = nullptr;

    g_ctx.navMesh = dtAllocNavMesh();
    if (!g_ctx.navMesh) return false;

    dtNavMeshParams params;
    memset(&params, 0, sizeof(params));
    params.orig[0] = -2.0f; params.orig[1] = -1.0f; params.orig[2] = -2.0f;
    params.tileWidth = tileWidth;
    params.tileHeight = tileHeight;
    params.maxTiles = 64;
    params.maxPolys = 2048;

    dtStatus status = g_ctx.navMesh->init(&params);
    if (dtStatusFailed(status)) return false;

    // 添加 tile (复制数据，navMesh 接管所有权)
    unsigned char* dataCopy = (unsigned char*)dtAlloc(dataSize, DT_ALLOC_PERM);
    memcpy(dataCopy, data, dataSize);
    status = g_ctx.navMesh->addTile(dataCopy, dataSize, DT_TILE_FREE_DATA, 0, nullptr);
    if (dtStatusFailed(status)) { dtFree(dataCopy); return false; }

    g_ctx.query = dtAllocNavMeshQuery();
    status = g_ctx.query->init(g_ctx.navMesh, 4096);
    if (dtStatusFailed(status)) return false;

    g_ctx.filter = new dtQueryFilter();
    memset(g_ctx.filter, 0, sizeof(dtQueryFilter));
    g_ctx.filter->setIncludeFlags(0xFFFF);
    g_ctx.filter->setExcludeFlags(0);
    for (int i = 0; i < DT_MAX_AREAS; ++i)
        g_ctx.filter->setAreaCost(i, 1.0f);

    return true;
}

// ============================================================
// 4. Detour: 查找路径 (返回路径点数量)
// ============================================================
EXPORT_API int detour_find_path(
    float startX, float startY, float startZ,
    float endX, float endY, float endZ,
    float* outPath, int maxPathPoints)
{
    if (!g_ctx.navMesh || !g_ctx.query) return 0;

    float extents[3] = { 5.0f, 10.0f, 5.0f };
    float nearestStart[3], nearestEnd[3];
    dtPolyRef startRef = 0, endRef = 0;

    g_ctx.query->findNearestPoly(&startX, extents, g_ctx.filter, &startRef, nearestStart);
    g_ctx.query->findNearestPoly(&endX, extents, g_ctx.filter, &endRef, nearestEnd);

    if (!startRef || !endRef) return 0;

    static const int MAX_POLYS = 512;
    dtPolyRef path[MAX_POLYS];
    int pathCount = 0;

    dtStatus status = g_ctx.query->findPath(
        startRef, endRef, nearestStart, nearestEnd,
        g_ctx.filter, path, &pathCount, MAX_POLYS);

    if (dtStatusFailed(status) || pathCount == 0) return 0;

    // Funnel 拉绳
    int straightCount = 0;
    g_ctx.query->findStraightPath(
        nearestStart, nearestEnd,
        path, pathCount,
        outPath, nullptr, nullptr, &straightCount, maxPathPoints);

    return straightCount;
}

// ============================================================
// 5. Detour: 射线投射
// ============================================================
EXPORT_API bool detour_raycast(
    float startX, float startY, float startZ,
    float endX, float endY, float endZ,
    float* outHitTime, float* outHitNormal)
{
    if (!g_ctx.navMesh || !g_ctx.query) return false;

    float extents[3] = { 5.0f, 10.0f, 5.0f };
    dtPolyRef startRef = 0;
    float nearestStart[3];

    g_ctx.query->findNearestPoly(&startX, extents, g_ctx.filter, &startRef, nearestStart);
    if (!startRef) return false;

    dtPolyRef path[256];
    int pathCount = 0;
    dtStatus status = g_ctx.query->raycast(
        startRef, nearestStart, &endX,
        g_ctx.filter, outHitTime, outHitNormal, path, &pathCount, 256);

    return dtStatusSucceed(status);
}

// ============================================================
// 6. 清理
// ============================================================
EXPORT_API void detour_cleanup() {
    if (g_ctx.query) { dtFreeNavMeshQuery(g_ctx.query); g_ctx.query = nullptr; }
    if (g_ctx.navMesh) { dtFreeNavMesh(g_ctx.navMesh); g_ctx.navMesh = nullptr; }
    delete g_ctx.filter; g_ctx.filter = nullptr;
}
```

### 2b: Unity C# Wrapper

```csharp
// RecastBridge.cs — Unity C# 端的 P/Invoke 包装器
//
// 使用方法: 将此脚本放在 Assets/Scripts/Navigation/ 下，
//           将编译好的 recast_unity_bridge.dll 放在 Assets/Plugins/ 下

using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace RecastUnity
{
    /// <summary>
    /// Recast 烘焙配置 (对应 rcConfig)
    /// </summary>
    [Serializable]
    public struct RecastBakeConfig
    {
        public float cellSize;          // 体素大小 (默认 0.3m)
        public float cellHeight;        // 体素高度 (默认 0.2m)
        public float agentHeight;       // agent 高度 (默认 2.0m)
        public float agentRadius;       // agent 半径 (默认 0.6m)
        public float agentMaxSlope;     // 最大坡度 度 (默认 45)
        public float agentMaxClimb;     // 最大攀爬高度 (默认 0.9m)

        public static RecastBakeConfig Default => new RecastBakeConfig
        {
            cellSize = 0.3f,
            cellHeight = 0.2f,
            agentHeight = 2.0f,
            agentRadius = 0.6f,
            agentMaxSlope = 45.0f,
            agentMaxClimb = 0.9f
        };
    }

    /// <summary>
    /// Recast/Detour 的 C# 桥接 — 管理与 native plugin 的所有交互
    /// </summary>
    public static class RecastBridge
    {
#if UNITY_IOS && !UNITY_EDITOR
        const string DLL = "__Internal";  // 静态链接
#else
        const string DLL = "recast_unity_bridge";
#endif

        // ---- Native 函数声明 ----

        [DllImport(DLL)]
        private static extern int recast_bake(
            IntPtr verts, int vertCount,
            IntPtr triIndices, int triCount,
            out IntPtr outData, out int outDataSize,
            float cellSize, float cellHeight,
            float agentHeight, float agentRadius,
            float agentMaxSlope, float agentMaxClimb);

        [DllImport(DLL)]
        private static extern void recast_free_buffer(IntPtr data);

        [DllImport(DLL)]
        private static extern bool detour_init_navmesh(
            IntPtr data, int dataSize,
            float tileWidth, float tileHeight);

        [DllImport(DLL)]
        private static extern int detour_find_path(
            float startX, float startY, float startZ,
            float endX, float endY, float endZ,
            [Out] float[] outPath, int maxPathPoints);

        [DllImport(DLL)]
        private static extern bool detour_raycast(
            float startX, float startY, float startZ,
            float endX, float endY, float endZ,
            out float outHitTime, [Out] float[] outHitNormal);

        [DllImport(DLL)]
        private static extern void detour_cleanup();

        // ---- 公共 API ----

        /// <summary>
        /// 从 Unity Mesh 烘焙 NavMesh 数据
        /// </summary>
        public static byte[] BakeNavMesh(
            Vector3[] vertices, int[] triangles,
            RecastBakeConfig config = default)
        {
            if (config.cellSize <= 0)
                config = RecastBakeConfig.Default;

            // 转换 Vector3[] → float[] (flattened)
            float[] vertFloats = new float[vertices.Length * 3];
            for (int i = 0; i < vertices.Length; ++i)
            {
                vertFloats[i * 3]     = vertices[i].x;
                vertFloats[i * 3 + 1] = vertices[i].y;
                vertFloats[i * 3 + 2] = vertices[i].z;
            }

            // Pin 托管数组获取原生指针
            GCHandle vertHandle = GCHandle.Alloc(vertFloats, GCHandleType.Pinned);
            GCHandle triHandle  = GCHandle.Alloc(triangles, GCHandleType.Pinned);

            try
            {
                IntPtr outData;
                int outDataSize;
                int result = recast_bake(
                    vertHandle.AddrOfPinnedObject(), vertices.Length,
                    triHandle.AddrOfPinnedObject(), triangles.Length / 3,
                    out outData, out outDataSize,
                    config.cellSize, config.cellHeight,
                    config.agentHeight, config.agentRadius,
                    config.agentMaxSlope, config.agentMaxClimb);

                if (result <= 0 || outData == IntPtr.Zero)
                {
                    Debug.LogError($"Recast bake failed with code {result}");
                    return null;
                }

                byte[] navData = new byte[outDataSize];
                Marshal.Copy(outData, navData, 0, outDataSize);
                recast_free_buffer(outData);

                Debug.Log($"Recast bake success: {outDataSize} bytes, "
                        + $"{vertices.Length} verts, {triangles.Length/3} tris");
                return navData;
            }
            finally
            {
                vertHandle.Free();
                triHandle.Free();
            }
        }

        /// <summary>
        /// 初始化 Detour 运行时（加载 NavMesh 数据）
        /// </summary>
        public static bool InitDetour(byte[] navMeshData,
                                       float tileWidth = 256f,
                                       float tileHeight = 256f)
        {
            if (navMeshData == null || navMeshData.Length == 0)
                return false;

            GCHandle handle = GCHandle.Alloc(navMeshData, GCHandleType.Pinned);
            try
            {
                return detour_init_navmesh(
                    handle.AddrOfPinnedObject(), navMeshData.Length,
                    tileWidth, tileHeight);
            }
            finally
            {
                handle.Free();
            }
        }

        /// <summary>
        /// 查找路径（返回世界坐标路径点列表）
        /// </summary>
        public static Vector3[] FindPath(Vector3 start, Vector3 end, int maxPoints = 256)
        {
            float[] pathBuffer = new float[maxPoints * 3];
            int count = detour_find_path(
                start.x, start.y, start.z,
                end.x, end.y, end.z,
                pathBuffer, maxPoints);

            if (count <= 0) return Array.Empty<Vector3>();

            Vector3[] result = new Vector3[count];
            for (int i = 0; i < count; ++i)
            {
                result[i] = new Vector3(
                    pathBuffer[i * 3],
                    pathBuffer[i * 3 + 1],
                    pathBuffer[i * 3 + 2]);
            }
            return result;
        }

        /// <summary>
        /// 射线投射
        /// </summary>
        public static bool Raycast(Vector3 start, Vector3 end,
                                    out float hitTime, out Vector3 hitNormal)
        {
            float[] normalBuf = new float[3];
            bool hit = detour_raycast(
                start.x, start.y, start.z,
                end.x, end.y, end.z,
                out hitTime, normalBuf);

            hitNormal = new Vector3(normalBuf[0], normalBuf[1], normalBuf[2]);
            return hit;
        }

        /// <summary>
        /// 释放资源
        /// </summary>
        public static void Cleanup()
        {
            detour_cleanup();
        }
    }
}
```

### 2c: Unity 使用示例

```csharp
// RecastNavMeshBaker.cs — Unity 中使用 Recast/Detour 的完整示例
//
// 挂在场景中的一个 GameObject 上
// 收集该 GameObject 下所有 MeshFilter/MeshRenderer 的几何体

using UnityEngine;
using System.Collections.Generic;

public class RecastNavMeshBaker : MonoBehaviour
{
    [Header("Bake Settings")]
    public RecastUnity.RecastBakeConfig bakeConfig = RecastUnity.RecastBakeConfig.Default;

    [Header("Gizmos")]
    public bool drawBakedNavMesh = true;

    private byte[] cachedNavData;
    private bool isInitialized = false;

    void Awake()
    {
        BakeAndInit();
    }

    [ContextMenu("Bake NavMesh")]
    public void BakeAndInit()
    {
        // 1. 收集场景中的几何体
        var (verts, tris) = CollectSceneGeometry();

        if (verts.Length == 0 || tris.Length == 0)
        {
            Debug.LogError("No geometry found to bake NavMesh from!");
            return;
        }

        Debug.Log($"Baking NavMesh from {verts.Length} verts, {tris.Length/3} tris...");

        // 2. 调用 Recast 烘焙
        cachedNavData = RecastUnity.RecastBridge.BakeNavMesh(verts, tris, bakeConfig);

        if (cachedNavData == null)
        {
            Debug.LogError("NavMesh baking failed.");
            return;
        }

        // 3. 初始化 Detour
        isInitialized = RecastUnity.RecastBridge.InitDetour(cachedNavData);
        Debug.Log(isInitialized
            ? "Detour runtime initialized successfully."
            : "Detour init failed!");
    }

    /// <summary>
    /// 收集场景几何体（合并所有子 MeshFilter 的顶点）
    /// </summary>
    private (Vector3[], int[]) CollectSceneGeometry()
    {
        var allVerts = new List<Vector3>();
        var allTris  = new List<int>();
        int vertOffset = 0;

        foreach (var mf in GetComponentsInChildren<MeshFilter>())
        {
            if (mf.sharedMesh == null) continue;

            // 转换到世界空间（Recast 需要世界坐标的几何体）
            Matrix4x4 localToWorld = mf.transform.localToWorldMatrix;
            Vector3[] meshVerts = mf.sharedMesh.vertices;
            int[] meshTris = mf.sharedMesh.triangles;

            foreach (var v in meshVerts)
                allVerts.Add(localToWorld.MultiplyPoint3x4(v));

            foreach (var t in meshTris)
                allTris.Add(t + vertOffset);

            vertOffset += meshVerts.Length;
        }

        // 额外添加 Terrain 的几何体（如果存在）
        foreach (var terrain in GetComponentsInChildren<Terrain>())
        {
            TerrainData td = terrain.terrainData;
            Vector3 terrainPos = terrain.transform.position;
            int res = td.heightmapResolution;

            float[,] heights = td.GetHeights(0, 0, res, res);
            Vector3 size = td.size;
            float cellW = size.x / (res - 1);
            float cellH = size.z / (res - 1);

            int baseVert = allVerts.Count;
            for (int z = 0; z < res; ++z)
            for (int x = 0; x < res; ++x)
            {
                allVerts.Add(terrainPos + new Vector3(
                    x * cellW,
                    heights[z, x] * size.y,
                    z * cellH));
            }
            for (int z = 0; z < res - 1; ++z)
            for (int x = 0; x < res - 1; ++x)
            {
                int bl = baseVert + z * res + x;
                int br = bl + 1;
                int tl = bl + res;
                int tr = tl + 1;
                allTris.Add(bl); allTris.Add(tl); allTris.Add(br);
                allTris.Add(br); allTris.Add(tl); allTris.Add(tr);
            }
        }

        return (allVerts.ToArray(), allTris.ToArray());
    }

    void OnDestroy()
    {
        RecastUnity.RecastBridge.Cleanup();
    }

    void OnDrawGizmos()
    {
        if (!drawBakedNavMesh || !isInitialized || cachedNavData == null)
            return;

        // 测试路径：从原点走到 (10, 0, 10)
        var path = RecastUnity.RecastBridge.FindPath(
            Vector3.zero,
            new Vector3(10, 0, 10));

        if (path.Length > 0)
        {
            Gizmos.color = Color.cyan;
            for (int i = 0; i < path.Length - 1; ++i)
            {
                Gizmos.DrawLine(path[i], path[i + 1]);
                Gizmos.DrawSphere(path[i], 0.2f);
            }
            Gizmos.color = Color.green;
            Gizmos.DrawSphere(path[0], 0.4f);   // 起点
            Gizmos.color = Color.red;
            Gizmos.DrawSphere(path[path.Length-1], 0.4f); // 终点
        }
    }
}
```

**运行方式（Unity 中使用）:**

```
1. 编译 recast_unity_bridge.cpp 为 DLL:
   (Windows): 使用 Visual Studio Developer Command Prompt
   (Mac):     g++ -std=c++11 -shared -fPIC -O2 ...
   (Linux):   同上

2. 将 .dll/.so/.dylib 放入 Unity 项目的 Assets/Plugins/ 目录

3. 将 RecastBridge.cs + RecastNavMeshBaker.cs 放入 Assets/Scripts/Navigation/

4. 在场景中创建一个 GameObject，挂上 RecastNavMeshBaker

5. 在子节点下放置任意 3D 模型（MeshFilter + MeshRenderer）
   → 或使用 Unity Terrain

6. 点击 Play，Awake 自动烘焙并测试路径

7. 在 Scene 视图中查看 Gizmos 绘制的路径
```

**预期输出 (Unity Console):**
```
Baking NavMesh from 2456 verts, 4096 tris...
Recast bake success: 18432 bytes, 2456 verts, 1365 tris
Detour runtime initialized successfully.
```

### 对比 Unity 内置 NavMesh

```csharp
// 等效的 Unity 内置 NavMesh 写法 (对比参考)
// Unity 内置: 编辑器烘焙 + 运行时查询
using UnityEngine;
using UnityEngine.AI;

public class UnityNavMeshPathfinder : MonoBehaviour
{
    public Transform target;

    void Update()
    {
        NavMeshPath path = new NavMeshPath();
        if (NavMesh.CalculatePath(transform.position, target.position,
                                   NavMesh.AllAreas, path))
        {
            for (int i = 0; i < path.corners.Length - 1; ++i)
                Debug.DrawLine(path.corners[i], path.corners[i+1], Color.cyan);
        }
    }
}
// 注: 这需要在 Editor 中预先烘焙 NavMesh (Window → AI → Navigation)
//
// 关键差异:
// - Unity 内置: 2 行代码查询，但烘焙必须离线
// - Recast/Detour: 需要 P/Invoke wrapper，但支持运行时烘焙
```

## 3. 练习

### 基础练习：运行时烘焙一个 Cube 场景

在 Unity 中创建一个 3×3 排列的 Cube 网格（9 个 Cube，间距 2 米），用 `RecastNavMeshBaker` 烘焙 NavMesh。在 Gizmos 中观察 NavMesh 是否正确覆盖所有 Cube 顶部，以及 Cube 之间的间隙是否被标记为不可通行。

**目标**: 理解 Recast 如何从 Unity 场景几何体生成 NavMesh。

### 进阶练习：实现逐帧路径重规划

实现一个简单 AI：让一个 Cube agent 沿 Detour 路径移动，当检测到前方路径被阻挡时（用 `detour_raycast`），重新请求路径。使用 Unity 的 `OnTriggerEnter` 模拟动态障碍物出现。

**目标**: 结合 `findPath` 和 `raycast` 实现基本的动态导航。

### 挑战练习：实现 Detour 路径的 Corners 可视化 + 平滑

在每个 NavMesh 路径拐点处放置小 Sphere Gizmos，并实现路径平滑：

1. 获取原始 Detour 路径（折线）
2. 对路径做 Catmull-Rom 样条插值（Unity 端 C#）
3. 检查插值后路径的每个点是否仍在 NavMesh 上（用 `findNearestPoly` 验证）
4. 剔除离开 NavMesh 的平滑段，回退到原始转折点

**目标**: 将 Detour 的 minimial-path 转换为适合 game agent 运动的平滑轨道。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 创建 3×3 Cube 场景并运行时烘焙 NavMesh：
>
> ```csharp
> // CubeNavMeshDemo.cs — 运行时生成 3×3 Cube 网格并烘焙 NavMesh
> // 挂在空 GameObject 上即可运行
> using UnityEngine;
> using System.Collections.Generic;
>
> public class CubeNavMeshDemo : MonoBehaviour
> {
>     [Header("Grid Settings")]
>     public int gridSize = 3;        // 3×3
>     public float spacing = 2.0f;   // Cube 间距
>     public float cubeSize = 1.0f;  // Cube 边长
>
>     [Header("Bake Settings")]
>     public RecastUnity.RecastBakeConfig bakeConfig = RecastUnity.RecastBakeConfig.Default;
>
>     [Header("Visualization")]
>     public bool showNavMeshGizmos = true;
>     public bool showTestPath = true;
>
>     private byte[] navMeshData;
>     private bool navMeshReady = false;
>     private Vector3[] lastPath;
>
>     void Start()
>     {
>         GenerateCubes();
>         BakeNavMeshFromScene();
>         if (navMeshReady && showTestPath)
>             lastPath = RecastUnity.RecastBridge.FindPath(
>                 GetCubeCenter(0, 0), GetCubeCenter(gridSize - 1, gridSize - 1));
>     }
>
>     void GenerateCubes()
>     {
>         float offset = (gridSize - 1) * spacing * 0.5f;
>
>         for (int z = 0; z < gridSize; ++z)
>         {
>             for (int x = 0; x < gridSize; ++x)
>             {
>                 GameObject cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
>                 cube.name = $"Cube_{x}_{z}";
>                 cube.transform.SetParent(transform);
>                 cube.transform.position = new Vector3(
>                     x * spacing - offset, 0, z * spacing - offset);
>                 cube.transform.localScale = Vector3.one * cubeSize;
>                 // 确保有 MeshFilter（CreatePrimitive 自带）
>             }
>         }
>     }
>
>     void BakeNavMeshFromScene()
>     {
>         // 复用 RecastNavMeshBaker 的几何体收集逻辑
>         // 或直接在此收集所有子 Cube 的 Mesh
>         var allVerts = new List<Vector3>();
>         var allTris = new List<int>();
>         int vertOffset = 0;
>
>         foreach (var mf in GetComponentsInChildren<MeshFilter>())
>         {
>             if (mf.sharedMesh == null) continue;
>             Matrix4x4 l2w = mf.transform.localToWorldMatrix;
>             // 只收集 Cube 顶部面（Y-up 平面）用于 NavMesh
>             // 但更简单的做法是收集所有顶点，让 Recast 的 walkable 过滤处理
>             Vector3[] verts = mf.sharedMesh.vertices;
>             int[] tris = mf.sharedMesh.triangles;
>
>             foreach (var v in verts)
>                 allVerts.Add(l2w.MultiplyPoint3x4(v));
>             foreach (var t in tris)
>                 allTris.Add(t + vertOffset);
>             vertOffset += verts.Length;
>         }
>
>         Debug.Log($"Collecting geometry: {allVerts.Count} verts, {allTris.Count / 3} tris");
>
>         // 调用 Recast 烘焙
>         navMeshData = RecastUnity.RecastBridge.BakeNavMesh(
>             allVerts.ToArray(), allTris.ToArray(), bakeConfig);
>
>         if (navMeshData != null)
>         {
>             navMeshReady = RecastUnity.RecastBridge.InitDetour(navMeshData);
>             Debug.Log(navMeshReady
>                 ? $"NavMesh baked: {navMeshData.Length} bytes"
>                 : "Detour init failed");
>         }
>     }
>
>     Vector3 GetCubeCenter(int x, int z)
>     {
>         float offset = (gridSize - 1) * spacing * 0.5f;
>         return new Vector3(x * spacing - offset, cubeSize * 0.5f,
>                            z * spacing - offset);
>     }
>
>     void OnDrawGizmos()
>     {
>         if (!showNavMeshGizmos || !navMeshReady) return;
>
>         // 绘制测试路径
>         if (lastPath != null && lastPath.Length > 1)
>         {
>             Gizmos.color = Color.cyan;
>             for (int i = 0; i < lastPath.Length - 1; ++i)
>                 Gizmos.DrawLine(lastPath[i], lastPath[i + 1]);
>
>             // 在每个拐点处画小球
>             Gizmos.color = Color.yellow;
>             foreach (var p in lastPath)
>                 Gizmos.DrawSphere(p, 0.15f);
>
>             Gizmos.color = Color.green;
>             Gizmos.DrawSphere(lastPath[0], 0.3f);
>             Gizmos.color = Color.red;
>             Gizmos.DrawSphere(lastPath[^1], 0.3f);
>         }
>
>         // 绘制 Cube 间隙的不可通行区域（红色半透明方框）
>         float offset = (gridSize - 1) * spacing * 0.5f;
>         Gizmos.color = new Color(1, 0, 0, 0.3f);
>         for (int z = 0; z < gridSize - 1; ++z)
>         {
>             for (int x = 0; x < gridSize - 1; ++x)
>             {
>                 Vector3 center = new Vector3(
>                     x * spacing - offset + spacing * 0.5f,
>                     0,
>                     z * spacing - offset + spacing * 0.5f);
>                 Gizmos.DrawWireCube(center,
>                     new Vector3(spacing - cubeSize, 0.1f, spacing - cubeSize));
>             }
>         }
>     }
>
>     void OnDestroy()
>     {
>         RecastUnity.RecastBridge.Cleanup();
>     }
> }
> ```
>
> **关键点**：Cube 之间的间隙（间距 > cubeSize 时）不会被 Recast 体素化，因为那里没有几何体表面。Recast 只在实际有三角形的区域生成 walkable span。间隙自动成为不可通行区域。如果想测试 Cube 间隙是否被正确标记，可以尝试设置路径从 Cube A 到 Cube C（中间隔了一个 Cube B）——路径应该绕过间隙而不是跳过去（因为 agent 的 `agentRadius` 限制）。

> [!tip]- 练习 2 参考答案
> 实现逐帧路径重规划 + 动态障碍检测：
>
> ```csharp
> // DynamicPathAgent.cs — 使用 Detour 寻路 + raycast 检测 + 动态重规划
> using UnityEngine;
> using System.Collections;
> using System.Collections.Generic;
>
> public class DynamicPathAgent : MonoBehaviour
> {
>     [Header("Movement")]
>     public float speed = 5.0f;
>     public float waypointThreshold = 0.5f;  // 距目标点多远算"到达"
>
>     [Header("Detection")]
>     public float raycastCheckInterval = 0.5f; // 射线检测间隔
>     public float raycastLookAhead = 5.0f;     // 前瞻距离
>
>     private Vector3[] currentPath;
>     private int currentWaypointIndex = 0;
>     private float lastRaycastTime = 0f;
>     private bool needsReplan = false;
>
>     // 动态障碍物列表（通过 OnTriggerEnter/Exit 维护）
>     private HashSet<Collider> nearbyObstacles = new HashSet<Collider>();
>
>     public void SetDestination(Vector3 target)
>     {
>         currentPath = RecastUnity.RecastBridge.FindPath(transform.position, target);
>         currentWaypointIndex = 0;
>         needsReplan = false;
>
>         if (currentPath.Length == 0)
>             Debug.LogWarning("No path found to target!");
>         else
>             Debug.Log($"Path found: {currentPath.Length} waypoints");
>     }
>
>     void Update()
>     {
>         if (currentPath == null || currentPath.Length == 0) return;
>         if (currentWaypointIndex >= currentPath.Length) return;
>
>         // ---- 射线检测前方是否有新障碍 ----
>         if (Time.time - lastRaycastTime > raycastCheckInterval)
>         {
>             lastRaycastTime = Time.time;
>             CheckPathAhead();
>         }
>
>         // ---- 如果需要重规划 ----
>         if (needsReplan)
>         {
>             Vector3 target = currentPath[^1]; // 原始目标
>             SetDestination(target);
>             return;
>         }
>
>         // ---- 沿路径移动 ----
>         Vector3 targetWaypoint = currentPath[currentWaypointIndex];
>         Vector3 direction = (targetWaypoint - transform.position).normalized;
>         transform.position += direction * speed * Time.deltaTime;
>
>         // 面向移动方向
>         if (direction != Vector3.zero)
>             transform.rotation = Quaternion.LookRotation(direction);
>
>         // 到达 waypoint → 前进到下一个
>         if (Vector3.Distance(transform.position, targetWaypoint) < waypointThreshold)
>         {
>             currentWaypointIndex++;
>             if (currentWaypointIndex >= currentPath.Length)
>                 Debug.Log("Destination reached!");
>         }
>     }
>
>     void CheckPathAhead()
>     {
>         if (currentPath == null || currentWaypointIndex >= currentPath.Length)
>             return;
>
>         // 沿当前路径方向做 raycast
>         Vector3 from = transform.position;
>         int lookIdx = Mathf.Min(currentWaypointIndex + 3, currentPath.Length - 1);
>         Vector3 to = currentPath[lookIdx];
>         Vector3 dir = (to - from).normalized;
>         Vector3 rayEnd = from + dir * raycastLookAhead;
>
>         float hitTime;
>         Vector3 hitNormal;
>         bool blocked = RecastUnity.RecastBridge.Raycast(from, rayEnd,
>                                                          out hitTime, out hitNormal);
>
>         if (blocked && hitTime < 1.0f)
>         {
>             Vector3 hitPoint = from + (rayEnd - from) * hitTime;
>             Debug.Log($"Path blocked at {hitPoint} (hitTime={hitTime:F2}) — replanning");
>             needsReplan = true;
>         }
>
>         // 也检查 Unity 物理障碍（通过 OnTriggerEnter 收集的）
>         foreach (var col in nearbyObstacles)
>         {
>             if (col == null) continue;
>             Vector3 closestPoint = col.ClosestPoint(transform.position);
>             float dist = Vector3.Distance(transform.position, closestPoint);
>             if (dist < raycastLookAhead)
>             {
>                 // 检查障碍物是否在路径方向的锥形区域中
>                 Vector3 toClosest = (closestPoint - transform.position).normalized;
>                 float dot = Vector3.Dot(dir, toClosest);
>                 if (dot > 0.5f) // 在前进方向 ±60° 内
>                 {
>                     Debug.Log($"Dynamic obstacle ahead: {col.name} — replanning");
>                     needsReplan = true;
>                     break;
>                 }
>             }
>         }
>     }
>
>     void OnTriggerEnter(Collider other)
>     {
>         if (other.CompareTag("DynamicObstacle"))
>             nearbyObstacles.Add(other);
>     }
>
>     void OnTriggerExit(Collider other)
>     {
>         nearbyObstacles.Remove(other);
>     }
>
>     void OnDrawGizmos()
>     {
>         if (currentPath == null) return;
>
>         // 绘制剩余路径
>         Gizmos.color = Color.cyan;
>         for (int i = currentWaypointIndex; i < currentPath.Length - 1; ++i)
>             Gizmos.DrawLine(currentPath[i], currentPath[i + 1]);
>
>         // 绘制前瞻射线
>         if (currentWaypointIndex < currentPath.Length)
>         {
>             Gizmos.color = Color.yellow;
>             Vector3 from = transform.position;
>             int lookIdx = Mathf.Min(currentWaypointIndex + 3, currentPath.Length - 1);
>             Gizmos.DrawRay(from, (currentPath[lookIdx] - from).normalized * raycastLookAhead);
>         }
>     }
> }
> ```
>
> **关键点**：
> - `detour_raycast` 检测路径是否被 NavMesh 边界阻挡（如 tile 边界、新烘焙的障碍区）
> - Unity 的 `OnTriggerEnter` 检测 Unity 层面的动态障碍（如移动的箱子）
> - 两者配合：NavMesh 级别障碍用 Detour raycast，物理级别障碍用 Unity 碰撞检测
> - 重规划频率需要节流（`raycastCheckInterval`），避免每帧都重新 `findPath`
> - 生产环境中，通常在 `dtCrowd::update` 内部自动处理局部避障，而不需要手动 raycast 触发重规划

> [!tip]- 练习 3 参考答案（可选）
> 路径拐点可视化 + Catmull-Rom 样条平滑：
>
> ```csharp
> // PathSmoother.cs — 对 Detour 路径做 Catmull-Rom 插值 + NavMesh 验证
> using UnityEngine;
> using System.Collections.Generic;
>
> public class PathSmoother : MonoBehaviour
> {
>     [Header("Smooth Settings")]
>     [Range(2, 20)] public int subdivisionsPerSegment = 8;
>     [Range(0f, 1f)] public float alpha = 0.5f; // Catmull-Rom 张力参数
>
>     [Header("Validation")]
>     public bool validateOnNavMesh = true;
>     public float validationSearchRadius = 2.0f;
>
>     [Header("Visualization")]
>     public Color cornerColor = Color.yellow;
>     public float cornerSize = 0.3f;
>     public Color rawPathColor = Color.gray;
>     public Color smoothPathColor = Color.cyan;
>     public Color invalidSegmentColor = Color.red;
>
>     /// <summary>
>     /// 获取原始路径拐点（在拐点处放置 Gizmo Sphere）
>     /// </summary>
>     public void DrawCorners(Vector3[] path)
>     {
>         if (path == null || path.Length < 2) return;
>
>         Gizmos.color = cornerColor;
>         for (int i = 1; i < path.Length - 1; ++i) // 跳过首尾（起点/终点）
>         {
>             Gizmos.DrawSphere(path[i], cornerSize);
>         }
>     }
>
>     /// <summary>
>     /// Catmull-Rom 样条插值
>     /// 对每对相邻路径点之间的段进行细分
>     /// </summary>
>     public Vector3[] SmoothPath(Vector3[] rawPath)
>     {
>         if (rawPath == null || rawPath.Length < 2)
>             return rawPath;
>
>         int segmentCount = rawPath.Length - 1;
>         var smooth = new List<Vector3>();
>
>         for (int i = 0; i < segmentCount; ++i)
>         {
>             // Catmull-Rom 需要 4 个控制点: P(i-1), P(i), P(i+1), P(i+2)
>             Vector3 p0 = rawPath[Mathf.Max(i - 1, 0)];
>             Vector3 p1 = rawPath[i];
>             Vector3 p2 = rawPath[Mathf.Min(i + 1, rawPath.Length - 1)];
>             Vector3 p3 = rawPath[Mathf.Min(i + 2, rawPath.Length - 1)];
>
>             // 边界处理：如果是首段，p0 = p1（或镜像）
>             if (i == 0) p0 = p1 + (p1 - p2); // 反射
>             // 如果是末段，p3 = p2 + (p2 - p1)
>             if (i == segmentCount - 1) p3 = p2 + (p2 - p1);
>
>             for (int s = 0; s < subdivisionsPerSegment; ++s)
>             {
>                 float t = s / (float)subdivisionsPerSegment;
>                 smooth.Add(CatmullRom(p0, p1, p2, p3, t, alpha));
>             }
>         }
>
>         // 添加终点
>         smooth.Add(rawPath[^1]);
>
>         return smooth.ToArray();
>     }
>
>     /// <summary>
>     /// 标准 Catmull-Rom 公式
>     /// </summary>
>     Vector3 CatmullRom(Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3,
>                         float t, float alpha)
>     {
>         // 使用 centripetal Catmull-Rom（alpha=0.5）
>         // 比 uniform (alpha=0) 更平滑，比 chordal (alpha=1) 更自然
>         float t0 = 0f;
>         float t1 = GetT(t0, p0, p1, alpha);
>         float t2 = GetT(t1, p1, p2, alpha);
>         float t3 = GetT(t2, p2, p3, alpha);
>
>         float tt = Mathf.Lerp(t1, t2, t);
>
>         Vector3 a1 = (t1 - tt) / (t1 - t0) * p0 + (tt - t0) / (t1 - t0) * p1;
>         Vector3 a2 = (t2 - tt) / (t2 - t1) * p1 + (tt - t1) / (t2 - t1) * p2;
>         Vector3 a3 = (t3 - tt) / (t3 - t2) * p2 + (tt - t2) / (t3 - t2) * p3;
>
>         Vector3 b1 = (t2 - tt) / (t2 - t0) * a1 + (tt - t0) / (t2 - t0) * a2;
>         Vector3 b2 = (t3 - tt) / (t3 - t1) * a2 + (tt - t1) / (t3 - t1) * a3;
>
>         return (t2 - tt) / (t2 - t1) * b1 + (tt - t1) / (t2 - t1) * b2;
>     }
>
>     float GetT(float tPrev, Vector3 p0, Vector3 p1, float alpha)
>     {
>         float dist = Vector3.Distance(p0, p1);
>         return tPrev + Mathf.Pow(dist, alpha);
>     }
>
>     /// <summary>
>     /// 验证平滑后的路径点是否仍在 NavMesh 上
>     /// 通过检查每个点到最近 poly 的距离是否在范围内
>     /// </summary>
>     public List<Vector3> ValidatePath(Vector3[] smoothPath)
>     {
>         if (!validateOnNavMesh) return new List<Vector3>(smoothPath);
>
>         var valid = new List<Vector3>();
>         bool inInvalidSegment = false;
>
>         for (int i = 0; i < smoothPath.Length; ++i)
>         {
>             // 用 Detour 的路径查询验证：尝试从该点到自身 findPath
>             // 如果该点对应的 poly ref 为 0（不在 NavMesh 上），则回退
>             var testPath = RecastUnity.RecastBridge.FindPath(
>                 smoothPath[i], smoothPath[i], maxPoints: 2);
>
>             if (testPath.Length > 0)
>             {
>                 // 该点在 NavMesh 上
>                 valid.Add(smoothPath[i]);
>                 inInvalidSegment = false;
>             }
>             else
>             {
>                 // 不在 NavMesh 上 → 回退到上一个有效拐点
>                 if (!inInvalidSegment && valid.Count > 0)
>                 {
>                     inInvalidSegment = true;
>                     Debug.Log($"Smooth point [{i}] off NavMesh — "
>                              + $"clamping to last valid corner {valid[^1]}");
>                 }
>                 // 跳过该点
>             }
>         }
>         return valid;
>     }
>
>     /// <summary>
>     /// 完整流程：原始路径 → 平滑 → 验证
>     /// </summary>
>     public Vector3[] ProcessPath(Vector3[] rawPath)
>     {
>         var smooth = SmoothPath(rawPath);
>         var valid = ValidatePath(smooth);
>         return valid.ToArray();
>     }
>
>     // ---- Gizmos 绘制 ----
>     public void DrawFullGizmos(Vector3[] rawPath, Vector3[] processed)
>     {
>         // 原始路径
>         if (rawPath != null && rawPath.Length > 1)
>         {
>             Gizmos.color = rawPathColor;
>             for (int i = 0; i < rawPath.Length - 1; ++i)
>                 Gizmos.DrawLine(rawPath[i], rawPath[i + 1]);
>         }
>
>         // 拐点球
>         DrawCorners(rawPath);
>
>         // 平滑后路径
>         if (processed != null && processed.Length > 1)
>         {
>             Gizmos.color = smoothPathColor;
>             for (int i = 0; i < processed.Length - 1; ++i)
>                 Gizmos.DrawLine(processed[i], processed[i + 1]);
>         }
>     }
> }
>
> // ============================================================
> // 使用示例：挂到 RecastNavMeshBaker 所在的 GameObject 上
> // ============================================================
> // [RequireComponent(typeof(RecastNavMeshBaker))]
> // public class PathSmoothDemo : MonoBehaviour
> // {
> //     private PathSmoother smoother;
> //     private Vector3[] rawPath;
> //     private Vector3[] smoothPath;
> //
> //     void Start()
> //     {
> //         smoother = GetComponent<PathSmoother>();
> //         rawPath = RecastUnity.RecastBridge.FindPath(
> //             Vector3.zero, new Vector3(18, 0, 18));
> //         smoothPath = smoother.ProcessPath(rawPath);
> //     }
> //
> //     void OnDrawGizmos()
> //     {
> //         if (smoother != null)
> //             smoother.DrawFullGizmos(rawPath, smoothPath);
> //     }
> // }
> ```
>
> **关键点**：
> - **Centripetal Catmull-Rom** (alpha=0.5)：比 uniform 版本更平滑自然，不会在长段和短段交界处产生"打结"（因为参数化基于距离的平方根而非均匀 t）
> - **NavMesh 验证**是平滑的难点：平滑曲线可能会"切角"穿出 NavMesh。解决方案：对每个平滑点用 `findPath` 检验（如果该点到自身的路径有效 → 在 NavMesh 上），不在 NavMesh 上的段用上一个有效拐点替代
> - 也可以反过来做：先用漏斗算法获得最小拐点路径，再用 Catmull-Rom 平滑漏斗路径，这样平滑偏离 NavMesh 的概率更低
> - 生产环境通常用 steering（`dtCrowd` 的 moveTarget）而非样条插值来平滑运动，因为 steering 考虑了 agent 的物理约束（加速度、转弯半径）

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。Unity 端的代码需要 `RecastBridge.cs`（教程中的 P/Invoke wrapper）和编译好的 native plugin 才能实际运行。没有 native plugin 时，可以用 `UnityEngine.AI.NavMesh` 的等效 API 做概念验证。

## 4. 扩展阅读

- **Unity Native Plugin 文档**: `docs.unity3d.com/Manual/NativePlugins.html` — 官方 P/Invoke 和 Native Plugin 指南
- **Mikko Mononen 的 Recast Demo**: `recastnavigation/RecastDemo` — 可视化 Recast 每阶段输出的交互工具，是理解管线的最佳方式
- **"Runtime NavMesh Generation in Unity"**: Unity 官方博客 (2018) — 使用 `NavMeshBuilder.BuildNavMeshData` 的运行时烘焙 API（Unity 2017.2+ 也支持运行时烘焙，但精度不如 Recast）
- **Entity Component System + NavMesh**: 使用 Unity ECS 的 `NavMeshQuery` 对几百个 entity 同时寻路（`Unity.Physics` 包中的相关 API）
- **A* Pathfinding Project (Aron Granberg)**: Unity Asset Store 上的第三方寻路库 — 提供 C# 实现的 Recast/Detour 替代方案，纯 C# 无需原生插件

## 常见陷阱

### 1. 运行时 DLL 加载路径问题

在 Editor 中 Unity 从 `Assets/Plugins/` 加载 DLL，但在构建后路径不同：Windows 构建将 DLL 放在 `Data/Plugins/`，Mac 构建在 `.app/Contents/Plugins/`。未正确配置插件平台设置（`.meta` 文件）会导致 DLL 找不到。

**修正**: 在 Unity Inspector 中选中 DLL，确保为其目标平台启用了正确的 CPU 架构（x86_64 for desktop, arm64 for iOS/Mac Silicon）。

### 2. 几何体坐标系转换

Unity 使用左手坐标系（Y-up），而 Recast/Detour 也是左手坐标系（Y-up）—— 但顶点数据需要是**世界坐标**，不是本地坐标。忘记 `localToWorldMatrix` 转换会导致 NavMesh 生成在错误位置。

**修正**: 在 `CollectSceneGeometry()` 中确保所有顶点都经过了 `localToWorldMatrix.MultiplyPoint3x4()` 转换。

### 3. IL2CPP 与托管内存 Pin

在 IL2CPP 构建（iOS/Console/WebGL）中，`GCHandle.Alloc` 固定托管内存的行为与 Mono 不同。长时间 Pin 大数组可能导致 GC 碎片化。

**修正**: 将 Pin 的时间限制到最小；在大型项目中使用 `NativeArray<T>`（Unity Collections 包）+ unsafe 指针。

### 4. 多次烘焙的内存泄漏

每次调用 `recast_bake` 分配 rcHeightfield、rcCompactHeightfield 等的内存。如果忘记释放中间结构（如 `rcFreeHeightField`），会导致内存持续增长。

**修正**: native 端每个 `rcAlloc*` 必须有对应的 `rcFree*`。使用 RAII 或在函数末尾集中释放。

### 5. Detour 的 `findNearestPoly` 返回 0

当起点/终点远离 NavMesh 时（如代理在空中/在地下），`findNearestPoly` 返回的 `dtPolyRef` 为 0。如果不检查这个返回值，`findPath` 会静默失败。

**修正**: 始终检查 `startRef != 0 && endRef != 0`，失败时给出清晰的日志并回退处理（如 clamp 到最近可行走点）。

### 6. 线程安全：Native Plugin 的全局状态

`recast_unity_bridge.cpp` 使用了静态全局 `g_ctx`，这意味着**不能从多个线程同时调用 `detour_find_path`**。在 Unity 中如果使用 Jobs System 多线程寻路，需要改用 context handle 模式（每个查询线程有独立的 `dtNavMeshQuery` 实例）。

**修正**: 改为 `void* ctx = detour_create_context(navData); detour_find_path(ctx, ...); detour_destroy_context(ctx);` 模式，每个 ctx 是线程独立的。
