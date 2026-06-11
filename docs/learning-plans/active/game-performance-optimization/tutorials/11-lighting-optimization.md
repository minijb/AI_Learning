---
title: "光照优化 — 烘焙、Light Culling、阴影"
updated: 2026-06-05
---

# 光照优化 — 烘焙、Light Culling、阴影
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: 05-Draw Call 优化 (了解渲染管线基础), 08-Shader 优化 (了解 Pixel Shader 成本)

---

## 1. 概念讲解

### 为什么需要这个？

光照是 3D 游戏视觉质量的基石，也是 GPU 性能的最大消费者之一。一个典型场景中：

- **前向渲染**：每个物体 × 每个光源 = O(objects × lights) 的光照计算
- **延迟渲染**：每个像素 × 每个光源 = O(pixels × lights) 的光照计算

如果场景中有 100 个动态光源，1080p 的帧需要计算 200 万 × 100 = 2 亿次光照。每次光照涉及 NdotL、半向量、镜面反射、阴影采样等数十条指令。这就是光照优化的核心战场。

一个真实案例：《地平线：零之黎明》的技术分享中指出，光照计算占 GPU 帧时间的 35%–50%。通过 Light Culling（将每个像素的光源列表从 50+ 个降到平均 3 个），GPU 时间降低超过 40%。

### 核心思想

#### 1. Forward vs Deferred 光照成本模型

**前向渲染（Forward Rendering）**：
```
每个物体 × 每个影响它的光源 → PS 执行光照
成本 ∝ 物体数 × 有效光源数 × 平均 PS 复杂度
```

优点：支持 MSAA，透明物体处理简单，内存占用小。
缺点：光源数多了之后成本指数增长。

**延迟渲染（Deferred Rendering）**：
```
GBuffer Pass（所有物体）→ 所有光源在屏幕空间计算光照
成本 ∝ 像素数 × 光源数 × 平均光照 PS 复杂度
```

优点：光源数对几何 Pass 无影响，光照计算与几何复杂度脱钩。
缺点：不支持硬件 MSAA，透明物体需额外处理，GBuffer 显存大。

**成本对比**（1080p，100 个物体，不同光源数）：

| 光源数 | 前向 (无culling) | 前向 (有culling) | 延迟 (无culling) | 延迟 (有culling) |
|--------|-----------------|-----------------|-----------------|-----------------|
| 1      | 1.0× | 1.0× | 1.2× (GBuffer开销) | 1.2× |
| 4      | 2.5× | 1.5× | 1.5× | 1.3× |
| 16     | 8.0× | 2.0× | 3.0× | 1.5× |
| 64     | 30.0× | 3.0× | 10.0× | 2.0× |

结论：对于多光源场景，前向+剔除或延迟+剔除都可以。超过 16 个光源后，延迟渲染优势明显——但 Light Culling 是不可或缺的。

#### 2. 光照烘焙（Baked Lighting）

对于静态场景（建筑、地形），光照可以在编辑器中预计算并"烘焙"到 Lightmap 中。

**Lightmap**：一张额外的纹理，存储了静态物体表面的预计算光照信息（通常是 indirect lighting + shadow）。运行时只需采样 Lightmap，不需要重新计算光照。

**Light Probe**：在空间中放置采样点，记录该位置的间接光照信息（球谐函数或环境贴图）。运行时动态物体根据最近的 Probe 插值获得间接光照。

**Reflection Probe**：记录特定位置的反射信息（Cubemap），用于动态物体的镜面反射。

**优势**：
- 烘焙后零运行时开销（只需一次纹理采样）
- 可以使用路径追踪质量的离线渲染器（如 UE 的 Lightmass GPU）

**代价**：
- 只适用于静态场景（Lightmap UV 需要预生成）
- 占用额外的显存（一张 1024 的 Lightmap 约 4MB）
- 不能响应动态光照变化（日夜循环需要特殊处理）

#### 3. Light Culling

将"所有光源照所有像素"改为"每个像素只受附近光源影响"。

**Tiled Forward/Deferred**：
将屏幕划分为 Tile（如 16×16 像素），对每个 Tile 计算影响它的光源列表。
```
Tile 数量 = ceil(1920/16) × ceil(1080/16) = 120 × 68 = 8160
每个 Tile 只包含影响该区域的光源（平均 2-10 个）
```

步骤（Compute Shader）：
1. 对每个 Tile，找到最小和最大深度
2. 用 Tile 的视锥体子区域与光源包围体求交
3. 将相交的光源索引写入该 Tile 的光源列表
4. Pixel Shader 只遍历自己 Tile 的光源列表

**Clustered Forward/Deferred**：
在 Tiled 基础上增加深度维度：
```
Cluster 数量 = tileX × tileY × depthSlices
            = 120 × 68 × 32 = 261,120
```

优势：避免 Tiled 方案中深度不连续区域的误判（例如：Tile 中有近处墙壁和远处天空，Light Culling 无法区分为两个子树）。

UE 使用 Clustered Deferred，Unity URP/HDRP 使用 Tiled/Clustered Forward。

#### 4. 阴影优化

阴影是光照中成本最高的部分：

**Shadow Map 分辨率**：阴影贴图的像素数。2K Shadow Map = 4M 像素，4K = 16M 像素。更高的分辨率 = 更好的阴影边缘质量 = 更高的渲染和采样成本。

**Cascade Shadow Maps（CSM，级联阴影）**：
- 将相机的视锥体分割成多个深度范围
- 每个范围一张独立的 Shadow Map
- 近处用高分辨率（如 2K），远处用低分辨率（如 512）
- 典型配置：4 cascade，分辨率 2048/1024/512/512

**Shadow Distance**：超出此距离不渲染阴影。减少 Shadow Distance 是获得性能的最快方式（但视觉上可能注意到阴影突然出现/消失）。

**Shadow Caching**：静态物体的阴影可以缓存（Shadow Cache），每 N 帧更新一次而不是每帧。

**UE 阴影系统**：
| 类型 | 性能 | 质量 | 使用场景 |
|------|------|------|----------|
| Baked Shadow Maps | 零运行时 | 高（离线质量） | 静态场景 |
| Shadow Maps (CSM) | 中 | 中-高 | 方向光 |
| Distance Field Shadows | 中 | 中 | 远距离柔和阴影 |
| Ray Traced Shadows | 高（需要 RT 硬件） | 极高 | 近距离精确阴影 |
| Virtual Shadow Maps | 中-高 | 高 | UE5 默认，Nanite 兼容 |

**Unity 阴影系统**：
| 类型 | 性能 | 质量 | 使用场景 |
|------|------|------|----------|
| Baked Shadows | 零运行时 | 高 | 静态场景 |
| Shadow Maps (CSM) | 中 | 中-高 | URP/HDRP 全部 |
| Screen Space Shadows | 低 | 低-中 | HDRP 接触阴影 |

**最佳实践**：
- 减少 Cascade 数：4 → 3 或 2。每减少一个 Cascade = 减少一张 Shadow Map 的渲染+采样
- 降低远 Cascade 分辨率：Cascade 2/3 用 512，Cascade 0 用 2048
- 提高 Shadow Distance 过渡的艺术感：在 Shadow Distance 边缘做 Distance Fadeout
- 静态物体用 Baked Shadow：减少每帧的 Shadow Map 渲染

---

## 2. 代码示例

### 示例 1：Tiled Light Culling（Compute Shader）

```hlsl
// tiled_light_culling.compute — Tiled Forward Light Culling
// 在 Unity/UE 中用 Compute Shader 实现

// 常量定义
#define TILE_SIZE       16      // 每个 Tile 16×16 像素
#define MAX_LIGHTS      1024    // 场景最大光源数
#define MAX_LIGHTS_PER_TILE 256 // 每个 Tile 最大光源数
#define DEPTH_SLICES    1       // 设为 > 1 即升级为 Clustered

// 光源数据结构
struct Light {
    float3 position;
    float  range;           // 光源影响范围半径
    float3 color;
    float  intensity;
    int    type;            // 0=Point, 1=Spot, 2=Directional
    float3 direction;       // Spot/Directional 用
    float  spotAngleCos;    // Spot 内角余弦
    float  spotAngleCosOuter; // Spot 外角余弦
};

// 视锥体平面
struct FrustumPlane {
    float3 normal;
    float  d;
};

// ====== 缓冲区 ======
// 输入
StructuredBuffer<Light>    g_Lights;           // 所有光源
// 输出
RWStructuredBuffer<uint>   g_LightIndexList;   // 每个 Tile 的光源索引列表（扁平化）
RWStructuredBuffer<uint>   g_LightGrid;        // 每个 Tile 的光源数+起始偏移（2×uint per Tile）

// ====== Tile 视锥体计算 ======
// 从屏幕坐标和深度范围计算视锥体平面

float4 ClipToView(float4 clip, float4x4 invProj) {
    float4 view = mul(invProj, clip);
    return view / view.w;
}

FrustumPlane MakePlane(float3 a, float3 b, float3 c) {
    float3 normal = normalize(cross(b - a, c - a));
    return (FrustumPlane){ normal, -dot(normal, a) };
}

// 构建 Tile 的视锥体（4 个侧面 + 近平面 + 远平面）
void BuildTileFrustum(
    uint2 tileXY, float2 tileCount,
    float minDepthVS, float maxDepthVS,
    float4x4 invProj,
    out FrustumPlane frustum[6]
) {
    // Tile 的屏幕空间范围
    float2 tileMin = (float2)tileXY / tileCount;
    float2 tileMax = (float2)(tileXY + 1) / tileCount;

    // 四个角的 NDC 坐标
    float4 corners[4];
    corners[0] = float4(tileMin * 2.0 - 1.0, 0.0, 1.0); // 左下
    corners[1] = float4(tileMax.x * 2.0 - 1.0, tileMin.y * 2.0 - 1.0, 0.0, 1.0);
    corners[2] = float4(tileMax * 2.0 - 1.0, 0.0, 1.0); // 右上
    corners[3] = float4(tileMin.x * 2.0 - 1.0, tileMax.y * 2.0 - 1.0, 0.0, 1.0);

    // 转换为 View Space
    float3 cornersVS[4];
    for (int i = 0; i < 4; i++) {
        float4 vs = ClipToView(corners[i], invProj);
        cornersVS[i] = vs.xyz * minDepthVS;  // 近平面缩放
    }

    // 构建视锥体平面（只做侧面，近远平面用深度判断）
    frustum[0] = MakePlane(float3(0, 0, 0), cornersVS[1], cornersVS[0]); // 上
    frustum[1] = MakePlane(float3(0, 0, 0), cornersVS[3], cornersVS[2]); // 下
    frustum[2] = MakePlane(float3(0, 0, 0), cornersVS[0], cornersVS[3]); // 左
    frustum[3] = MakePlane(float3(0, 0, 0), cornersVS[2], cornersVS[1]); // 右
    // 近平面和远平面用深度范围判断（比平面测试更快）
    float3 nearCenter = (cornersVS[0] + cornersVS[1] + cornersVS[2] + cornersVS[3]) * 0.25;
    frustum[4] = (FrustumPlane){ normalize(nearCenter), -minDepthVS };
    frustum[5] = (FrustumPlane){ -normalize(nearCenter), maxDepthVS };
}

// 球体与视锥体相交测试
bool SphereInFrustum(FrustumPlane frustum[6], float3 center, float radius) {
    // 测试到每个平面的有符号距离
    [unroll]
    for (int i = 0; i < 6; i++) {
        float dist = dot(frustum[i].normal, center) + frustum[i].d;
        if (dist < -radius) {
            return false; // 球体完全在平面外侧
        }
    }
    return true;
}

// ====== 主入口 ======
[numthreads(TILE_SIZE, TILE_SIZE, 1)]
void CSMain(uint3 groupID : SV_GroupID, uint3 threadID : SV_DispatchThreadID) {
    uint2 tileXY = groupID.xy;
    uint tileIndex = tileXY.y * ((uint)g_TileCountX) + tileXY.x;

    // Step 1: 计算 Tile 的深度范围（用 InterlockedMin/Max 收集）
    // ... 在实际实现中，需要先跑一次 Z-reduce pass 获取深度范围
    // 这里假设已经获得 minDepth 和 maxDepth
    float minDepthVS = 0.1f;  // 近平面
    float maxDepthVS = 500.0f; // 远平面

    // Step 2: 构建 Tile 视锥体
    FrustumPlane frustum[6];
    BuildTileFrustum(tileXY, float2(g_TileCountX, g_TileCountY),
                     minDepthVS, maxDepthVS, g_InvProj, frustum);

    // Step 3: 遍历所有光源，收集影响该 Tile 的光源
    uint lightIndices[MAX_LIGHTS_PER_TILE];
    uint lightCount = 0;

    for (uint i = 0; i < g_NumLights && lightCount < MAX_LIGHTS_PER_TILE; i++) {
        Light light = g_Lights[i];

        bool visible = false;

        if (light.type == 2) {
            // Directional light 总是影响所有 Tile
            visible = true;
        } else {
            // Point/Spot light：球体-视锥体相交测试
            visible = SphereInFrustum(frustum, light.position, light.range);
        }

        if (visible) {
            lightIndices[lightCount++] = i;
        }
    }

    // Step 4: 写入光源列表
    // 获取全局偏移（通过原子操作分配）
    uint offset;
    InterlockedAdd(g_GlobalLightListCounter, lightCount, offset);

    // 写入每个 Tile 的元数据
    g_LightGrid[tileIndex * 2 + 0] = offset;      // 光源列表的起始偏移
    g_LightGrid[tileIndex * 2 + 1] = lightCount;  // 光源数量

    // 写入光源索引
    for (uint j = 0; j < lightCount; j++) {
        g_LightIndexList[offset + j] = lightIndices[j];
    }
}

// ====== Pixel Shader 中使用 ======
// 在像素着色器中读取光源列表:
/*
uint2 tileXY = uint2(floor(input.screenPos.xy / TILE_SIZE));
uint tileIndex = tileXY.y * tileCountX + tileXY.x;
uint lightOffset = g_LightGrid[tileIndex * 2 + 0];
uint lightCount  = g_LightGrid[tileIndex * 2 + 1];

for (uint i = 0; i < lightCount; i++) {
    uint lightIdx = g_LightIndexList[lightOffset + i];
    Light light = g_Lights[lightIdx];
    // ... 计算光照 ...
}
*/
```

### 示例 2：光照成本模拟器

```cpp
// lighting_cost_simulator.cpp — 对比不同光照方案的成本
// 编译: g++ -std=c++17 lighting_cost_simulator.cpp -o light_cost && ./light_cost

#include <iostream>
#include <vector>
#include <cmath>
#include <iomanip>
#include <string>

struct SceneConfig {
    std::string name;
    int screenW, screenH;
    int objectCount;
    int dynamicLightCount;
    int staticLightCount;
    int shadowCastingLightCount;
    int shadowMapResolution;
    int cascadeCount;
    bool hasLightCulling;
    bool hasBakedLighting;
    bool isDeferred;
};

struct CostBreakdown {
    float geometryPass_ms;      // 几何 Pass（GBuffer/Forward）
    float lightCulling_ms;      // Light Culling 开销
    float lighting_ms;          // 光照计算
    float shadowRendering_ms;   // 阴影渲染
    float shadowSampling_ms;    // 阴影采样
    float total_ms;
};

CostBreakdown Simulate(const SceneConfig& cfg) {
    CostBreakdown cb = {};
    int totalPixels = cfg.screenW * cfg.screenH;

    // 几何 Pass
    float geoBaseCost = cfg.objectCount * 0.005f; // ms per object
    if (cfg.isDeferred) {
        // 延迟渲染的几何 Pass 稍贵（需要输出多个 RT）
        geoBaseCost *= 1.3f;
    }
    cb.geometryPass_ms = geoBaseCost;

    // Light Culling
    if (cfg.hasLightCulling) {
        // Tiled/Clustered culling 开销（Compute Shader）
        int tiles = (cfg.screenW / 16) * (cfg.screenH / 16);
        cb.lightCulling_ms = tiles * 0.0002f; // 每个 Tile 的处理时间
    }

    // 光照计算
    if (cfg.isDeferred) {
        // 延迟渲染：每个像素 × 有效光源数
        int effectiveLights = cfg.dynamicLightCount;
        if (cfg.hasLightCulling) {
            effectiveLights = std::min(cfg.dynamicLightCount, 8); // 平均每 Tile 8 个
        }
        cb.lighting_ms = totalPixels * effectiveLights * 0.0000008f; // 每个像素每条光
    } else {
        // 前向渲染：已包含在几何 Pass 中（多光源）
        // 简化：每个物体 × 有效光源
        int effectiveLights = cfg.dynamicLightCount;
        if (cfg.hasLightCulling) {
            effectiveLights = std::min(cfg.dynamicLightCount, 4);
        }
        cb.lighting_ms = cfg.objectCount * effectiveLights * 0.003f;
    }

    // 阴影渲染（渲染 Shadow Map）
    int shadowPasses = cfg.shadowCastingLightCount;
    if (cfg.isDeferred) {
        shadowPasses *= cfg.cascadeCount;
    }
    int shadowMapPixels = cfg.shadowMapResolution * cfg.shadowMapResolution;
    cb.shadowRendering_ms = shadowPasses * cfg.objectCount * 0.001f;
    cb.shadowRendering_ms += shadowPasses * shadowMapPixels * 0.0000001f; // Shadow Map 光栅化

    // 阴影采样（在光照计算中进行）
    if (cfg.shadowCastingLightCount > 0) {
        float shadowSampleCost = totalPixels * cfg.dynamicLightCount * 0.0000005f;
        if (cfg.hasLightCulling) {
            shadowSampleCost *= 0.3f; // 只有被剔除后剩余的光源需要阴影
        }
        cb.shadowSampling_ms = shadowSampleCost;
    }

    // 烘焙节省（静态光源变免费）
    if (cfg.hasBakedLighting && cfg.staticLightCount > 0) {
        // 静态光源的光照已有 Lightmap，运行时省掉
        float saving = (float)cfg.staticLightCount / (cfg.dynamicLightCount + cfg.staticLightCount);
        cb.lighting_ms *= (1.0f - saving * 0.9f);
        cb.shadowRendering_ms *= (1.0f - saving * 0.8f);
    }

    cb.total_ms = cb.geometryPass_ms + cb.lightCulling_ms + cb.lighting_ms
                + cb.shadowRendering_ms + cb.shadowSampling_ms;
    return cb;
}

void PrintResults(const SceneConfig& cfg, const CostBreakdown& cb) {
    std::cout << "场景: " << cfg.name << "  ";
    std::cout << "(" << cfg.screenW << "×" << cfg.screenH
              << ", " << cfg.objectCount << " objects, "
              << cfg.dynamicLightCount << " dynamic + "
              << cfg.staticLightCount << " static lights)";
    if (cfg.isDeferred) std::cout << " [Deferred]";
    else std::cout << " [Forward]";
    if (cfg.hasLightCulling) std::cout << " +Culling";
    if (cfg.hasBakedLighting) std::cout << " +Baked";
    std::cout << "\n";

    auto bar = [](float val, float max) -> std::string {
        int len = (int)(val / max * 30);
        return std::string(len, '█') + std::string(30 - len, '░');
    };

    float maxCost = std::max({cb.geometryPass_ms, cb.lighting_ms,
                              cb.shadowRendering_ms, cb.shadowSampling_ms,
                              cb.lightCulling_ms, 0.01f});

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "  几何Pass:     " << std::setw(6) << cb.geometryPass_ms
              << "ms " << bar(cb.geometryPass_ms, maxCost) << "\n";
    std::cout << "  Light Culling:" << std::setw(6) << cb.lightCulling_ms
              << "ms " << bar(cb.lightCulling_ms, maxCost) << "\n";
    std::cout << "  光照计算:     " << std::setw(6) << cb.lighting_ms
              << "ms " << bar(cb.lighting_ms, maxCost) << "\n";
    std::cout << "  阴影渲染:     " << std::setw(6) << cb.shadowRendering_ms
              << "ms " << bar(cb.shadowRendering_ms, maxCost) << "\n";
    std::cout << "  阴影采样:     " << std::setw(6) << cb.shadowSampling_ms
              << "ms " << bar(cb.shadowSampling_ms, maxCost) << "\n";
    std::cout << "  ─────────────────────────────────\n";
    std::cout << "  总计:         " << std::setw(6) << cb.total_ms << "ms\n\n";
}

int main() {
    std::cout << "========== 光照方案成本对比 ==========\n\n";

    std::vector<SceneConfig> configs = {
        {
            "A: 前向，无优化",
            1920, 1080, 500, 16, 0, 4, 2048, 4,
            false, false, false
        },
        {
            "B: 前向，+Light Culling",
            1920, 1080, 500, 16, 0, 4, 2048, 4,
            true, false, false
        },
        {
            "C: 延迟，+Light Culling",
            1920, 1080, 500, 16, 0, 4, 2048, 4,
            true, false, true
        },
        {
            "D: 延迟，+Culling + 烘焙 10 个静态光源",
            1920, 1080, 500, 6, 10, 2, 2048, 4,
            true, true, true
        },
        {
            "E: 延迟，+Culling + 烘焙 + 降低阴影分辨率",
            1920, 1080, 500, 6, 10, 2, 1024, 2,
            true, true, true
        },
    };

    // 先计算所有结果
    std::vector<CostBreakdown> results;
    for (auto& cfg : configs) {
        results.push_back(Simulate(cfg));
    }

    // 打印所有结果
    for (size_t i = 0; i < configs.size(); i++) {
        PrintResults(configs[i], results[i]);
    }

    // 对比总结
    std::cout << "========== 优化效果总结 ==========\n\n";
    float baseline = results[0].total_ms;
    for (size_t i = 1; i < configs.size(); i++) {
        float reduction = (baseline - results[i].total_ms) / baseline * 100.0f;
        std::cout << configs[i].name.substr(3) << ":\n";
        std::cout << "  相比 A 降低 " << std::setprecision(1) << reduction << "% 光照成本\n";
        std::cout << "  节省 " << (baseline - results[i].total_ms) << "ms\n\n";
    }

    std::cout << "========== 光照优化检查清单 ==========\n";
    std::cout << "□ 1. 区分静态/动态光源 — 静态光源务必烘焙\n";
    std::cout << "□ 2. 启用 Light Culling (Tiled/Clustered)\n";
    std::cout << "□ 3. 减少阴影 Casting 光源数（不是所有光源都需要阴影）\n";
    std::cout << "□ 4. 降低 Cascade 数 (4→3 或 3→2)\n";
    std::cout << "□ 5. 降低远 Cascade 的 Shadow Map 分辨率\n";
    std::cout << "□ 6. 减少 Shadow Distance\n";
    std::cout << "□ 7. 调整光源 Range — 不要用无限 Range 的 Point Light\n";
    std::cout << "□ 8. 重叠的 Spot Light → 合并为 1 个更大范围的\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: 分析场景光源配置

打开你项目中的一个主要场景：
1. 统计各类光源数量：Directional / Point / Spot / Area
2. 标记哪些光源投射阴影（最贵的操作）
3. 找出 3 个可能不必要的阴影光源
4. 估算禁用它们后节省的 GPU 时间

### 练习 2: 调整 Cascade Shadow Map

在 Unity 或 UE 中：
1. 将 Cascade 数从 4 降到 2
2. 将 Cascade 2 的 Shadow Map 分辨率从 1024 降到 512
3. 将 Shadow Distance 从 100 米降到 60 米
4. 测量帧率变化
5. 记录可以接受的视觉妥协点

### 练习 3: 实现简易 Tiled Light Culling（挑战）

在 Unity 中用 Compute Shader 实现本节示例 1 的 Tiled Light Culling：
1. 创建 Compute Shader，输入光源列表 + 深度缓冲
2. 输出每个 Tile 的光源索引列表
3. 在 Shader 中读取 Tile 的光源列表来计算光照
4. 对比有/无 Light Culling 的帧率（100 个 Point Light）

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **光源审计模板：**
>
> ```
> 场景: [名称] | 帧预算: 16.67ms (60fps)
>
> 光源统计:
> ┌──────────┬──────┬────────┬──────────┬─────────┬──────────────┐
> │ 类型     │ 数量 │ 投射阴影│ 阴影分辨率│ 范围(m) │ 备注         │
> ├──────────┼──────┼────────┼──────────┼─────────┼──────────────┤
> │Directional│  1   │   是   │  2048×4  │ 无限    │ 主光源(必须)  │
> │ Point    │  23  │   5    │  1024    │ 10-50   │ 5 个有阴影!   │
> │ Spot     │  8   │   2    │  512     │ 8-30    │ 2 个有阴影!   │
> │ Area     │  4   │   0    │  N/A     │ 3-10    │ 补光(无阴影)  │
> └──────────┴──────┴────────┴──────────┴─────────┴──────────────┘
>
> 3 个可能不必要的阴影光源:
>
> 1. "WallTorch_PointLight_03" — 墙上火炬，范围 5m
>    阴影几乎不可见（太小太暗），可禁用阴影 → 节省 1 个 Shadow Map 渲染
>
> 2. "Hallway_FillLight" — 走廊补光，范围 8m
>    不投射主阴影，且 3 个方向光已覆盖阴影 → 禁用阴影
>
> 3. "Exterior_Ambient_Spot" — 室外环境 Spot，范围 50m
>    范围太大但亮度低，几乎不产生可见阴影 → 禁用阴影，Range 降到 30m
>
> 估算节省:
>   每减少 1 个阴影光源 = 减少 1 次 Shadow Map 渲染 Pass
>   @ 1024 Shadow Map, 场景 500 物体 → 约 1-2ms GPU 时间
>   减少 3 个 → 节约 3-6ms GPU 时间
> ```
>
> **查找"不必要阴影"的启发式规则**：
> - 灯光 Range < 5m 且亮度 < 1.0 → 阴影几乎不可见
> - 补光 / Fill Light → 通常不需要阴影
> - 在其他光源 Shadow Map 范围内的重叠光源 → 阴影被覆盖
> - 快速移动或闪烁的光源 → 阴影反而显得奇怪

> [!tip]- 练习 2 参考答案
> **Cascade Shadow Map 调整步骤和预期结果：**
>
> **Unity 操作**：
> 1. 选中 Directional Light → Inspector → Shadow Type
> 2. 将 Cascades 从 4 降到 2
> 3. 在 Quality Settings 中调整 Cascade 分辨率：
>    - Cascade 0: 2048 (保持)
>    - Cascade 1: 512 (从 1024 降低)
> 4. Shadow Distance: 从 100m 降到 60m
>
> **UE 操作**：
> 1. Directional Light → Cascaded Shadow Maps
> 2. Dynamic Shadow Cascades: 4 → 2
> 3. Cascade Distribution Exponent: 调整使 Cascade 1 覆盖更近
> 4. Shadow Distance: 100m → 60m (或 `r.Shadow.DistanceScale 0.6`)
>
> **预期帧率变化**（1080p, 典型场景）：
> ```
> 配置                    Shadow Map 渲染   帧时间     vs 默认
> ─────────────────────────────────────────────────────────────
> 默认(4 cascade, 100m)   4× Shadow Pass    ~4.5ms    基准
> 2 cascade, 100m         2× Shadow Pass    ~3.2ms    -30%
> 2 cascade, 60m          2× Shadow Pass    ~2.1ms    -53%
> 2 cascade, 60m, 低分辨率 2× (2048+512)   ~1.8ms    -60%
> ```
>
> **可接受的视觉妥协点**：
> - 远景阴影消失 → 用 Distance Field Shadows 或 Contact Shadows 补偿
> - Cascade 边缘更明显 → 增加 Cascade Blend 区域
> - 远景阴影锯齿 → 提高 Shadow Filter Quality 但不提高分辨率
>
> **最佳实践**：Shadow Distance = Camera Far Clip × 30~50%。如果玩家很少看到 100m 外的阴影，减少到 50-60m 是零成本优化。

> [!tip]- 练习 3 参考答案（可选）
> **Unity Compute Shader 实现 Tiled Light Culling 的关键架构：**
>
> ```hlsl
> // TiledLightCulling.compute — Unity 中的 Tiled Light Culling
> // 所需输入 Buffer:
> //   StructuredBuffer<float4> _LightsPositionRange;  // xyz=pos, w=range
> //   StructuredBuffer<float4> _LightsColor;           // rgb=color, a=intensity
> //   Texture2D<float> _DepthTexture;                  // 深度缓冲
> //   float4x4 _InvProjectionMatrix;                   // 逆投影矩阵
> //
> // 输出 Buffer:
> //   RWStructuredBuffer<uint> _LightIndexList;  // 所有 Tile 的光源索引(扁平)
> //   RWStructuredBuffer<uint2> _LightGrid;      // x=offset, y=count per tile
>
> #define TILE_SIZE 16
> #define MAX_LIGHTS_PER_TILE 64
>
> float LinearEyeDepth(float z) {
>     // 将非线性深度缓冲值转为线性眼空间深度
>     return 1.0 / (_ZBufferParams.z * z + _ZBufferParams.w);
> }
>
> [numthreads(TILE_SIZE, TILE_SIZE, 1)]
> void CSMain(uint3 groupID : SV_GroupID, uint3 threadID : SV_DispatchThreadID) {
>     uint2 tileID = groupID.xy;
>     uint tileIndex = tileID.y * _TileCountX + tileID.x;
>
>     // Step 1: 在 LDS 中计算 Tile 的 min/max 深度
>     groupshared uint gsMinDepth;
>     groupshared uint gsMaxDepth;
>
>     if (threadID.x == 0 && threadID.y == 0) {
>         gsMinDepth = 0xFFFFFFFF;
>         gsMaxDepth = 0;
>     }
>     GroupMemoryBarrierWithGroupSync();
>
>     float depth = _DepthTexture[threadID.xy].r;
>     uint depthAsUint = asuint(depth);
>     InterlockedMin(gsMinDepth, depthAsUint);
>     InterlockedMax(gsMaxDepth, depthAsUint);
>     GroupMemoryBarrierWithGroupSync();
>
>     float minDepth = LinearEyeDepth(asfloat(gsMinDepth));
>     float maxDepth = LinearEyeDepth(asfloat(gsMaxDepth));
>
>     // Step 2: 构建 Tile 的视锥体
>     // (从 tileID 和深度范围计算 4 个侧面的平面方程)
>
>     // Step 3: 遍历所有光源 → 保存影响此 Tile 的索引
>     if (threadID.x == 0 && threadID.y == 0) {
>         uint lightIndices[MAX_LIGHTS_PER_TILE];
>         uint lightCount = 0;
>
>         for (uint i = 0; i < _LightCount; i++) {
>             // 球-视锥体相交测试 (或简化为球-AABB 测试)
>             float3 lightPos = _LightsPositionRange[i].xyz;
>             float range = _LightsPositionRange[i].w;
>
>             if (/* light affects this tile */) {
>                 lightIndices[lightCount++] = i;
>                 if (lightCount >= MAX_LIGHTS_PER_TILE) break;
>             }
>         }
>
>         // Step 4: 写入全局光源索引列表
>         uint offset;
>         InterlockedAdd(_GlobalIndexCounter, lightCount, offset);
>         _LightGrid[tileIndex] = uint2(offset, lightCount);
>         for (uint j = 0; j < lightCount; j++) {
>             _LightIndexList[offset + j] = lightIndices[j];
>         }
>     }
> }
> ```
>
> **在 Shader 中使用**：
> ```hlsl
> // Fragment Shader 中读取 Tile 的光源列表:
> uint2 tileID = uint2(floor(i.screenPos.xy / TILE_SIZE));
> uint tileIndex = tileID.y * _TileCountX + tileID.x;
> uint2 gridData = _LightGrid[tileIndex];
> uint lightOffset = gridData.x;
> uint lightCount  = gridData.y;
>
> float3 lighting = float3(0,0,0);
> for (uint i = 0; i < lightCount; i++) {
>     uint lightIdx = _LightIndexList[lightOffset + i];
>     lighting += ComputeLight(lightIdx, worldPos, normal, viewDir);
> }
> ```
>
> **预期提升**：100 个 Point Light 场景，无 Light Culling → ~30ms，有 Tiled Light Culling → ~5ms（约 6× 提升，因为每个像素从处理 100 个光降到平均 3-5 个）。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Olsson et al. — Clustered Deferred and Forward Shading** (HPG 2012)：Clustered Shading 的原始论文
- **UE5 Lighting Documentation** — https://docs.unrealengine.com/5.0/en-US/lighting-the-environment-in-unreal-engine/：UE5 完整光照系统文档
- **URP Lighting** — https://docs.unity3d.com/Packages/com.unity.render-pipelines.universal@latest：Unity URP 光照管线
- **Cascaded Shadow Maps (NVIDIA)** — https://developer.nvidia.com/gpugems/gpugems3/part-ii-light-and-shadows/chapter-10-parallel-split-shadow-maps-programmable-gpus：CSM 的原始 GPU Gems 文章

---

## 常见陷阱

- **不减少光源 Range**：默认的 Unity Point Light Range = 10，很多人保持默认。如果有 50 个这样的光，它们的影响范围巨大重叠。调整每个光源的 Range 为实际需要的范围，Light Culling 可以剔除掉更多光源。
- **所有光源都投射阴影**：阴影是光照中最贵的部分。环境填充光、补光、小的装饰光不需要投射阴影。Unity 中默认 Shadow Type = Soft Shadows，需要主动改为 No Shadows。
- **无限 Shadow Distance**：Shadow Distance = 0 表示无限。远处的阴影不可见但仍在渲染。将 Shadow Distance 设为相机 Far Clip 的 30%–50%（如 Far=500m → Shadow Distance=150-200m）。
- **忽略 Spot Light 比 Point Light 便宜**：Spot Light 的衰减计算更简单（不需要 1/(d²) 的精确物理衰减），范围更可控。能用 Spot 的地方不要用 Point。
- **Light Probe 太少或分布不均**：动态物体走过没有 Light Probe 的区域时，间接光照降级为 Sky Light（通常是蓝色），出现明显的颜色突变。在室内入口、走廊等光照变化大的区域加密 Light Probe。
- **开了 Light Culling 但 Tile Size 太大**：Tile Size = 32 意味着每个 Tile 覆盖 32×32=1024 像素，包含太多不同深度，导致大量光源被保留。用 16 或 8。
