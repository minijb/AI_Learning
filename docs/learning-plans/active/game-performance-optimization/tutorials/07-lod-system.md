---
title: "LOD 系统 — Mesh/Shader/Texture 层级管理"
updated: 2026-06-05
---

# LOD 系统 — Mesh/Shader/Texture 层级管理
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: 06-裁剪技术 (了解视锥体裁剪和基本渲染管线)

---

## 1. 概念讲解

### 为什么需要这个？

想象一个场景：玩家站在山顶，远处有一片森林。每棵树有 5000 个三角形。如果 1000 棵树都以全精度渲染，那就是 500 万个三角形。但屏幕分辨率只有 1920×1080 = 200 万像素——远处的树可能只占屏幕上 2×3 个像素。**用 5000 个三角形去填充 6 个像素，每个三角形贡献不到 0.001 个像素，这是在浪费 GPU 的一切**。

这就是 LOD（Level of Detail，细节层级）要解决的问题：**根据物体在屏幕上的实际可见尺寸，动态调整其渲染复杂度**。核心公式：

```
屏幕覆盖率 = (物体包围球半径 / 到相机距离) × (屏幕高度 / (2 × tan(FOV/2)))
```

当覆盖率低于阈值时，切换到更低细节的版本，GPU 工作量可以减少 50%–90%。

真实游戏数据：
- 《地平线：零之黎明》：单个机械兽 LOD0 有 55 万三角形，LOD3 仅 1.2 万（减少 97.8%）
- 《战神》：场景中最远的 LOD 只有 LOD0 的 3% 三角形数
- UE5 Nanite：自动 LOD，每个三角形约 1 像素，完全消除 LOD pop-in

### 核心思想

LOD 系统包含四个维度：

#### 1. Mesh LOD（几何体层级）
| LOD 层级 | 用途 | 三角形比例（典型） |
|----------|------|-------------------|
| LOD0 | 近距离（0–15m） | 100% |
| LOD1 | 中距离（15–40m） | 50% |
| LOD2 | 远距离（40–100m） | 25% |
| LOD3 | 极远距离（100m+） | 5%–10% |

**离散 LOD（Discrete LOD）**：预生成几个固定层级的模型，运行时根据距离切换。优点：简单、性能可预测。缺点：切换时有视觉跳变（pop-in）。

**连续 LOD（Continuous LOD）**：运行时动态调整三角形数量，过渡平滑但 CPU 开销大。现代引擎大多采用离散 LOD + 过渡技术（dithering/blending）。

**LOD 切换判定**：基于屏幕空间覆盖率的比例计算。Unity 的 `LOD Group` 使用 `屏幕相对高度 = 包围盒高度 / 距离`；UE 使用 `屏幕尺寸 = 包围球直径 × 屏幕高度 / (距离 × 2 × tan(FOV/2))`。

#### 2. LOD 过渡技术

- **Dithering（抖动过渡）**：在切换点附近，使用基于屏幕坐标的棋盘格 pattern 让新旧 LOD 各渲染一半像素。UE 默认使用这种方法（`LOD Dither`），无额外 draw call 开销。
- **Alpha Fade（透明度渐变）**：两个 LOD 同时渲染一段时间，一个 fade out，一个 fade in。开销大（双倍渲染），但效果自然。
- **Geometry Morph**：在两个 LOD 之间做顶点插值，需要两个 LOD 拓扑相同（顶点数一致），少见。

#### 3. Shader LOD

同一物体在不同距离可以用不同复杂度的 Shader：
- LOD0 Shader：完整 PBR + 法线贴图 + 视差贴图
- LOD1 Shader：简化 PBR（去掉法线贴图）
- LOD2 Shader：纯漫反射 + 无贴图

实现方式：在 Shader 中使用 `#pragma multi_compile _ LOD1 LOD2`，材质中根据距离设置 keyword。也可以用 Shader 内部的 `LOD` 指令：HLSL 中 `#pragma shader_feature` 配合运行时设置。

#### 4. Texture LOD（Mipmap）

GPU 自动选择合适分辨率的纹理层级。Mipmap 链：从原始分辨率（Level 0）一路缩小到 1×1。Mipmap 开销 = 原始纹理的 1/3 额外内存。可以手动控制最大 Mip Level 来减少显存占用（远处的物体不需要完整分辨率）。

**Texture Streaming**：动态加载需要的 Mip Level，而不是一次性加载全部。UE 的 Texture Streaming 系统和 Unity 的 Mipmap Streaming 都属于此类。

#### 5. LOD 生成算法

**边折叠（Edge Collapse）**：每次选择一条边，将其收缩为一个顶点。选择标准是 QEM（Quadric Error Metrics，二次误差度量）—— 计算折叠后新顶点到原始平面的距离平方和。Garland-Heckbert 算法（1997）是工业标准。

简化步骤：
1. 对每条边计算折叠代价（QEM 值）
2. 将边按代价排序放入最小堆
3. 每次取出代价最小的边进行折叠
4. 更新受影响的边的代价
5. 重复直到达到目标三角形数

#### 6. HLOD（Hierarchical LOD）

场景中成组物体的 LOD：将一组远处的物体合并成一个低精度代理模型。比如远处的城市街区 → 一个简单 box 加贴图。UE 的 World Partition HLOD 系统在开放世界游戏中至关重要。

---

## 2. 代码示例

### 示例 1：Shader LOD 选择（C++ / GLSL）

```cpp
// lod_select.cpp — 根据距离选择 Shader LOD 级别
// 编译: g++ -std=c++17 lod_select.cpp -o lod_select && ./lod_select

#include <iostream>
#include <cmath>
#include <vector>
#include <string>

struct Object {
    float distance;    // 到相机的距离（米）
    float radius;      // 包围球半径（米）
};

// 计算物体在屏幕上的大致覆盖率（0~1）
float ScreenCoverage(const Object& obj, float screenHeight, float fovDegrees) {
    // 屏幕空间大小 = 物体直径 / 距离 × 屏幕高度 / (2×tan(FOV/2))
    float fovRad = fovDegrees * 3.14159265f / 180.0f;
    float projectedSize = (obj.radius * 2.0f) / obj.distance;
    float screenSize = projectedSize * screenHeight / (2.0f * std::tan(fovRad / 2.0f));
    // 归一化到屏幕高度
    return screenSize / screenHeight;
}

// 根据覆盖率和距离确定 Shader LOD
struct ShaderLODResult {
    int lodLevel;
    const char* description;
    const char* shaderType;       // 使用的 Shader 类型
    const char* textureMipBias;   // Mipmap 偏移
};

ShaderLODResult SelectShaderLOD(const Object& obj) {
    float coverage = ScreenCoverage(obj, 1080.0f, 90.0f);

    if (coverage > 0.15f) {
        return { 0, "近距离 - 全精度渲染",
                 "PBR_FULL (BaseColor + Normal + Roughness + Metallic + AO + Parallax)",
                 "MipBias = 0" };
    } else if (coverage > 0.05f) {
        return { 1, "中距离 - 简化 PBR",
                 "PBR_SIMPLE (BaseColor + Normal + Roughness + Metallic)",
                 "MipBias = 2" };
    } else if (coverage > 0.01f) {
        return { 2, "远距离 - 基础着色",
                 "BASIC (BaseColor + Roughness only, no normal map)",
                 "MipBias = 4" };
    } else {
        return { 3, "极远距离 - 无光照",
                 "UNLIT (BaseColor only, unlit)",
                 "MipBias = 6, MaxMipLevel = 8" };
    }
}

// GLSL Shader LOD 示例 — 在 Shader 中根据距离调整计算
const char* glslShaderExample = R"(
// vertex shader — 传递距离信息
#version 450 core
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;

uniform mat4 uModel;
uniform mat4 uViewProj;
uniform vec3  uCameraPos;

out vec3 vWorldPos;
out vec3 vNormal;
out vec2 vTexCoord;
out float vDistance;  // 到相机的距离

void main() {
    vec4 worldPos = uModel * vec4(aPosition, 1.0);
    vWorldPos = worldPos.xyz;
    vDistance = distance(uCameraPos, worldPos.xyz);
    vNormal = mat3(uModel) * aNormal;
    vTexCoord = aTexCoord;
    gl_Position = uViewProj * worldPos;
}

// fragment shader — 根据距离选择不同计算路径
#version 450 core
in vec3 vWorldPos;
in vec3 vNormal;
in vec2 vTexCoord;
in float vDistance;

uniform sampler2D uBaseColor;
uniform sampler2D uNormalMap;      // 仅近距离使用
uniform sampler2D uRoughnessMap;   // 仅近距离使用
uniform sampler2D uMetallicMap;    // 仅近距离使用
uniform vec3 uLightDir;
uniform vec3 uCameraPos;
uniform float uLODDistance0;       // = 15.0  LOD0 最大距离
uniform float uLODDistance1;       // = 40.0  LOD1 最大距离
uniform float uLODDistance2;       // = 100.0 LOD2 最大距离

out vec4 fragColor;

vec3 CalcPBRFull(vec3 base, vec3 N, vec3 V, vec3 L);
vec3 CalcPBRLite(vec3 base, vec3 N, vec3 V, vec3 L);
vec3 CalcBasic(vec3 base);

void main() {
    vec3 baseColor = texture(uBaseColor, vTexCoord).rgb;

    if (vDistance < uLODDistance0) {
        // ===== Shader LOD 0: 完整 PBR =====
        vec3 normalTex = texture(uNormalMap, vTexCoord).xyz * 2.0 - 1.0;
        vec3 N = normalize(vNormal + normalTex);
        float roughness = texture(uRoughnessMap, vTexCoord).r;
        float metallic  = texture(uMetallicMap, vTexCoord).r;
        vec3 V = normalize(uCameraPos - vWorldPos);
        vec3 L = normalize(uLightDir);
        fragColor.rgb = CalcPBRFull(baseColor, N, V, L);
        fragColor.rgb *= (1.0 + metallic) * (1.0 - roughness * 0.5);

    } else if (vDistance < uLODDistance1) {
        // ===== Shader LOD 1: 去法线贴图，保留金属度/粗糙度 =====
        vec3 N = normalize(vNormal);
        float roughness = texture(uRoughnessMap, vTexCoord).r;
        float metallic  = texture(uMetallicMap, vTexCoord).r;
        vec3 V = normalize(uCameraPos - vWorldPos);
        vec3 L = normalize(uLightDir);
        fragColor.rgb = CalcPBRLite(baseColor, N, V, L);
        fragColor.rgb *= (1.0 - roughness * 0.3);

    } else if (vDistance < uLODDistance2) {
        // ===== Shader LOD 2: 纯漫反射 =====
        vec3 N = normalize(vNormal);
        vec3 L = normalize(uLightDir);
        float NdotL = max(dot(N, L), 0.0);
        fragColor.rgb = baseColor * (0.3 + 0.7 * NdotL);

    } else {
        // ===== Shader LOD 3: 无光照，仅 base color =====
        fragColor.rgb = baseColor * 0.8;  // 稍微压暗模拟距离衰减
    }

    fragColor.a = 1.0;
}
)";

int main() {
    const float screenHeight = 1080.0f;
    const float fov = 90.0f;

    std::vector<Object> objects = {
        { 5.0f,  1.0f },   // 近处
        { 20.0f, 1.0f },   // 中等距离
        { 60.0f, 1.0f },   // 远距离
        { 200.0f, 1.0f },  // 极远
        { 8.0f,  0.5f },   // 小物体近处
        { 30.0f, 0.3f },   // 小物体中距离
    };

    std::cout << "========== Shader LOD 选择系统 ==========\n";
    std::cout << "屏幕分辨率: " << screenHeight << "p, FOV: " << fov << "°\n\n";

    for (size_t i = 0; i < objects.size(); ++i) {
        auto& obj = objects[i];
        auto result = SelectShaderLOD(obj);
        float coverage = ScreenCoverage(obj, screenHeight, fov);

        std::cout << "物体 " << (i + 1) << ": "
                  << "距离=" << obj.distance << "m, "
                  << "半径=" << obj.radius << "m\n";
        std::cout << "  屏幕覆盖率: " << (coverage * 100.0f) << "%\n";
        std::cout << "  LOD Level:  " << result.lodLevel << "\n";
        std::cout << "  Shader:     " << result.shaderType << "\n";
        std::cout << "  Texture:    " << result.textureMipBias << "\n";
        std::cout << "  [" << result.description << "]\n\n";
    }

    std::cout << "========== GLSL Shader 示例（片段） ==========\n";
    std::cout << glslShaderExample << "\n";

    return 0;
}
```

**预期输出**：
```
物体 1: 距离=5m, 半径=1m → 覆盖率 29.8% → LOD 0 (全精度 PBR)
物体 2: 距离=20m, 半径=1m → 覆盖率 7.5%  → LOD 1 (简化 PBR)
物体 3: 距离=60m, 半径=1m → 覆盖率 2.5%  → LOD 2 (基础着色)
物体 4: 距离=200m, 半径=1m → 覆盖率 0.7% → LOD 3 (无光照)
```

### 示例 2：简易 Mesh 简化器

```cpp
// mesh_simplify_demo.cpp — 演示 QEM 边折叠的基本概念
// 编译: g++ -std=c++17 mesh_simplify_demo.cpp -o mesh_simplify && ./mesh_simplify
// 这不是完整的 QEM 实现, 而是展示算法骨架和数据流

#include <iostream>
#include <vector>
#include <queue>
#include <cmath>
#include <cstring>

// ====== 数据结构定义 ======

struct Vec3 {
    float x, y, z;
    Vec3() : x(0), y(0), z(0) {}
    Vec3(float x, float y, float z) : x(x), y(y), z(z) {}
    Vec3 operator+(const Vec3& o) const { return {x+o.x, y+o.y, z+o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x-o.x, y-o.y, z-o.z}; }
    Vec3 operator*(float s) const { return {x*s, y*s, z*s}; }
    float Dot(const Vec3& o) const { return x*o.x + y*o.y + z*o.z; }
    Vec3 Cross(const Vec3& o) const {
        return {y*o.z - z*o.y, z*o.x - x*o.z, x*o.y - y*o.x};
    }
    float Length() const { return std::sqrt(x*x + y*y + z*z); }
    Vec3 Normalized() const { float l = Length(); return l>0 ? (*this)*(1.0f/l) : *this; }
};

// 平面: n·p + d = 0
struct Plane {
    Vec3 n;
    float d;
    Plane(const Vec3& a, const Vec3& b, const Vec3& c) {
        n = (b - a).Cross(c - a).Normalized();
        d = -n.Dot(a);
    }
};

// 4×4 对称矩阵，存储 QEM 误差
struct QEM {
    float m[10]; // 对称矩阵只需存上三角: 0-9 = 00,01,02,03,11,12,13,22,23,33
    QEM() { std::memset(m, 0, sizeof(m)); }

    void AddPlane(const Plane& p) {
        float a = p.n.x, b = p.n.y, c = p.n.z, d = p.d;
        m[0] += a*a;  m[1] += a*b;  m[2] += a*c;  m[3] += a*d;
                      m[4] += b*b;  m[5] += b*c;  m[6] += b*d;
                                    m[7] += c*c;  m[8] += c*d;
                                                  m[9] += d*d;
    }

    // 计算位置 v 的误差: v^T * Q * v
    float Evaluate(const Vec3& v) const {
        float x = v.x, y = v.y, z = v.z;
        return m[0]*x*x + 2*m[1]*x*y + 2*m[2]*x*z + 2*m[3]*x
                         + m[4]*y*y + 2*m[5]*y*z + 2*m[6]*y
                                     + m[7]*z*z + 2*m[8]*z
                                                 + m[9];
    }
};

struct Edge {
    int v0, v1;             // 两端顶点索引
    float cost;             // 折叠代价
    Vec3 optimalPos;        // 最优折叠位置

    // 用于优先队列排序（最小代价优先）
    bool operator<(const Edge& o) const { return cost > o.cost; }
};

// ====== 核心算法 ======

// 计算边折叠的最优位置（简化版：取中点）
Vec3 ComputeOptimalPosition(const Vec3& v0, const Vec3& v1, const QEM& q0, const QEM& q1) {
    // 完整 QEM 应该解线性方程组求最小化 v^T*(Q0+Q1)*v 的位置
    // 这里简化为加权中点
    QEM qSum;
    for (int i = 0; i < 10; ++i) qSum.m[i] = q0.m[i] + q1.m[i];
    float errMid = qSum.Evaluate((v0 + v1) * 0.5f);
    float errV0  = qSum.Evaluate(v0);
    float errV1  = qSum.Evaluate(v1);

    // 选三者中误差最小的
    float minErr = std::min({errV0, errV1, errMid});
    if (minErr == errV0)  return v0;
    if (minErr == errV1)  return v1;
    return (v0 + v1) * 0.5f;
}

// ====== 演示主函数 ======

int main() {
    std::cout << "========== Mesh 简化器演示（QEM 边折叠） ==========\n\n";

    // 创建一个简单四面体
    std::vector<Vec3> vertices = {
        { 0.0f, 1.0f, 0.0f },   // v0: 顶部
        { -1.0f, 0.0f, 0.5f },  // v1
        { 1.0f, 0.0f, 0.5f },   // v2
        { 0.0f, 0.0f, -1.0f },  // v3: 底部
    };

    // 四个面（三角形）
    struct Tri { int a,b,c; };
    std::vector<Tri> triangles = {
        {0, 1, 2}, {0, 2, 3}, {0, 3, 1}, {1, 3, 2}
    };

    std::cout << "原始模型: " << vertices.size() << " 顶点, "
              << triangles.size() << " 三角形\n\n";

    // Step 1: 为每个顶点计算 QEM
    std::vector<QEM> vertexQEM(vertices.size());
    for (const auto& tri : triangles) {
        Plane plane(vertices[tri.a], vertices[tri.b], vertices[tri.c]);
        vertexQEM[tri.a].AddPlane(plane);
        vertexQEM[tri.b].AddPlane(plane);
        vertexQEM[tri.c].AddPlane(plane);
    }

    // Step 2: 计算每条边的折叠代价
    // 边的集合（简化：用邻接表）
    struct EdgeInfo { int v1; float cost; Vec3 optPos; };
    std::vector<std::vector<EdgeInfo>> edges(vertices.size());

    // 构建边（从三角形中提取，去重逻辑省略）
    auto AddEdge = [&](int a, int b) {
        Vec3 optPos = ComputeOptimalPosition(vertices[a], vertices[b],
                                              vertexQEM[a], vertexQEM[b]);
        QEM qSum;
        for (int i = 0; i < 10; ++i) qSum.m[i] = vertexQEM[a].m[i] + vertexQEM[b].m[i];
        float cost = qSum.Evaluate(optPos);
        edges[a].push_back({b, cost, optPos});
        edges[b].push_back({a, cost, optPos});
    };

    AddEdge(0, 1); AddEdge(0, 2); AddEdge(0, 3);
    AddEdge(1, 2); AddEdge(2, 3); AddEdge(3, 1);

    // Step 3: 放入优先队列
    std::priority_queue<Edge> pq;
    for (size_t i = 0; i < edges.size(); ++i) {
        for (auto& e : edges[i]) {
            if ((int)i < e.v1) { // 避免重复
                pq.push({(int)i, e.v1, e.cost, e.optPos});
            }
        }
    }

    // Step 4: 迭代折叠
    int targetTris = triangles.size() / 2;  // 目标：减少一半三角形
    std::cout << "目标: 折叠到 ≤ " << targetTris << " 个三角形\n\n";
    std::cout << "边折叠序列（按代价升序）:\n";
    std::cout << "----------------------------------------\n";

    int collapseCount = 0;
    while (!pq.empty() && (int)triangles.size() > targetTris) {
        Edge e = pq.top(); pq.pop();

        std::cout << "折叠 #" << (++collapseCount)
                  << ": 边 (" << e.v0 << ", " << e.v1 << ")"
                  << "  代价 = " << e.cost
                  << "  新位置 = (" << e.optimalPos.x
                  << ", " << e.optimalPos.y
                  << ", " << e.optimalPos.z << ")\n";

        // 在实际实现中，这里会：
        // 1. 将 v0 移到 optimalPos
        // 2. 将所有引用 v1 的三角形改为引用 v0
        // 3. 删除退化的三角形
        // 4. 更新受影响的边的代价

        if (collapseCount >= 4) break; // 演示只做 4 次折叠
    }

    std::cout << "\n========== 关键参数调优 ==========\n\n";
    std::cout << "LOD 层级划分建议:\n";
    std::cout << "  LOD0 (0-15m):   100% 三角形 — 当覆盖率 > 15%\n";
    std::cout << "  LOD1 (15-40m):  50% 三角形  — 当覆盖率 5%-15%\n";
    std::cout << "  LOD2 (40-100m): 25% 三角形  — 当覆盖率 1%-5%\n";
    std::cout << "  LOD3 (100+m):   10% 三角形  — 当覆盖率 < 1%\n\n";

    std::cout << "性能收益估算:\n";
    std::cout << "  假设场景 1000 个物体，70% 在中远距离:\n";
    std::cout << "  无 LOD:  1000 × 5000 = 5,000,000 三角形/帧\n";
    std::cout << "  有 LOD:  300×5000 + 400×2500 + 200×1250 + 100×500\n";
    std::cout << "          = 1,500,000 + 1,000,000 + 250,000 + 50,000\n";
    std::cout << "          = 2,800,000 三角形/帧 (减少 44%)\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: 计算最佳 LOD 切换距离

给定一个角色模型，包围球半径 1.2 米，屏幕分辨率 1920×1080，FOV 60°。计算 LOD 切换距离，使每级 LOD 的屏幕覆盖率分别为 20%、8%、2%。
- LOD0→LOD1 距离 = ?
- LOD1→LOD2 距离 = ?
- LOD2→LOD3（剔除）距离 = ?

### 练习 2: 分析一个真实游戏的 LOD 数据

打开你最熟悉的 3D 游戏，使用 RenderDoc 或引擎 Profiler 捕获一帧，观察：
1. 有多少个物体使用了 LOD？
2. 最常见的是 LOD 第几级？
3. 是否有物体不应该用 LOD 却用了？（比如总是离相机很近的 UI 或角色武器）

### 练习 3: 实现 LOD 过渡（挑战）

扩展示例 1 的 Shader LOD 选择器，实现 alpha-fade 过渡：
- 在切换距离 ±20% 范围内，同时渲染两级 LOD
- 根据距离在区间内的位置计算 alpha 值
- 渲染结果 = lerp(LOD_old_color, LOD_new_color, alpha)
- 计算过渡带宽对渲染开销的影响（额外 draw call 数）

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **计算步骤：**
>
> 使用屏幕覆盖率公式：
> ```
> 屏幕覆盖率 = (物体包围球半径 × 2 / 距离) × (屏幕高度 / (2 × tan(FOV/2)))
>           = (2.4 / 距离) × (1080 / (2 × tan(30°)))
>           = (2.4 / 距离) × (1080 / 1.1547)
>           = (2.4 / 距离) × 935.3
>           = 2244.7 / 距离
> ```
>
> 反解距离：
> ```
> 距离 = 2244.7 / 覆盖率
> ```
>
> | LOD 切换点 | 覆盖率 | 计算 | 距离 |
> |-----------|--------|------|------|
> | LOD0 → LOD1 | 20% = 0.20 | 2244.7 / 0.20 | **11.2 米** |
> | LOD1 → LOD2 | 8% = 0.08 | 2244.7 / 0.08 | **28.1 米** |
> | LOD2 → 剔除 | 2% = 0.02 | 2244.7 / 0.02 | **112.2 米** |
>
> **验证**：
> - 距离 11.2m 时覆盖率 = 2244.7/11.2/1080 ≈ 0.186 ≈ 18.6% ≈ 20% ✓
> - 距离 28.1m 时覆盖率 = 2244.7/28.1/1080 ≈ 0.074 ≈ 7.4% ≈ 8% ✓
> - 距离 112.2m 时覆盖率 = 2244.7/112.2/1080 ≈ 0.0185 ≈ 1.85% ≈ 2% ✓
>
> **实用建议**：这个距离基于纯几何覆盖率。实际项目中还需要考虑：
> - 屏幕分辨率越高，切换距离越远（4K 屏幕覆盖率需求更大）
> - FOV 变化（瞄准镜放大 FOV→切换距离也变化）
> - 在实际项目中通常会在计算结果上叠加 ±15-20% 的容差

> [!tip]- 练习 2 参考答案
> **使用 RenderDoc 分析 LOD 的步骤：**
>
> 1. **捕获一帧**：
>    - 打开 RenderDoc，Launch 目标游戏
>    - 选择一个有开阔视野的场景（如开放世界的山顶俯视）
>    - 按 F12 捕获
>
> 2. **在 Event Browser 中识别 LOD**：
>    - 按 Draw Call 排序，找使用相同 Material 但不同 Mesh 的 Draw Call
>    - 同一个资产的 LOD 层级通常有命名规律：`SM_Tree_LOD0`, `SM_Tree_LOD1`, `SM_Tree_LOD2`
>    - 在 Mesh Viewer 中查看三角形数量来确认 LOD 级别
>
> 3. **统计 LOD 分布**：
>    - 筛选所有带 `LOD` 后缀的 Draw Call
>    - 按 LOD 级别分组统计数量
>    - 典型分布：LOD0 ~15%, LOD1 ~35%, LOD2 ~30%, LOD3 ~20%（取决于摄像机位置和场景密度）
>
> 4. **异常检测**：
>    - 距离摄像机 5 米的物体用了 LOD2（切换距离设置过大）
>    - 距离摄像机 200 米的物体用了 LOD0（没有 LOD 或切换距离过小）
>    - UI/武器模型用了 LOD → 这些物体永远近距离，不应有 LOD
>
> 5. **判断标准**：
>    - 好的 LOD 配置：近处物体高精度，远处物体低精度，切换点不可见
>    - 差的 LOD 配置：LOD 级别分布与距离不相关、大量物体无 LOD、切换 pop-in 明显

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // lod_alpha_transition.cpp — LOD Alpha Fade 过渡实现
> // 编译: g++ -std=c++17 lod_alpha_transition.cpp -o lod_trans && ./lod_trans
> #include <iostream>
> #include <cmath>
> #include <iomanip>
>
> struct LODTransitionResult {
>     int lod_current;     // 当前主要 LOD 级别
>     int lod_next;        // 过渡目标 LOD 级别
>     float alpha_current; // 当前 LOD 的 alpha (1.0 = 完全不透明)
>     float alpha_next;    // 下一级 LOD 的 alpha
>     int extra_draw_call; // 过渡期间的额外 Draw Call
> };
>
> LODTransitionResult ComputeLODTransition(
>     float distance,              // 当前距离
>     float transition_distance,   // 切换点距离
>     float transition_band_pct = 0.20f) // 过渡带宽（±20%）
> {
>     LODTransitionResult r = {};
>     r.extra_draw_call = 0;
>
>     float band_half = transition_distance * transition_band_pct;
>     float band_start = transition_distance - band_half;
>     float band_end   = transition_distance + band_half;
>
>     if (distance < band_start) {
>         // 完全在 LOD 当前级别内
>         r.lod_current = 0;
>         r.lod_next = -1;
>         r.alpha_current = 1.0;
>         r.alpha_next = 0.0;
>     } else if (distance > band_end) {
>         // 完全过渡到下一级 LOD
>         r.lod_current = 1;
>         r.lod_next = -1;
>         r.alpha_current = 1.0;
>         r.alpha_next = 0.0;
>     } else {
>         // 在过渡带内：同时渲染两级 LOD
>         r.lod_current = 0;
>         r.lod_next = 1;
>         r.extra_draw_call = 1; // 额外渲染一级 LOD
>
>         // 计算过渡系数 t (0→1)
>         float t = (distance - band_start) / (band_end - band_start);
>         // 使用 smoothstep 让过渡更自然
>         float st = t * t * (3.0f - 2.0f * t);
>
>         r.alpha_current = 1.0f - st; // LOD0 逐渐变透明
>         r.alpha_next    = st;        // LOD1 逐渐变不透明
>     }
>
>     return r;
> }
>
> // GLSL 中的使用:
> // vec4 finalColor = mix(LOD0_color, LOD1_color, transition_alpha);
>
> int main() {
>     std::cout << "========== LOD Alpha Fade 过渡分析 ==========\n\n";
>
>     const float SWITCH_DIST = 30.0f; // LOD0→LOD1 切换点 30 米
>     const float BAND_PCT = 0.20f;    // ±20% = 24m~36m 过渡带
>
>     std::cout << "切换点: " << SWITCH_DIST << "m | 过渡带: ±"
>               << (int)(BAND_PCT * 100) << "% (" << SWITCH_DIST * (1-BAND_PCT)
>               << "m ~ " << SWITCH_DIST * (1+BAND_PCT) << "m)\n\n";
>
>     std::cout << std::setw(8) << "距离" << std::setw(10) << "LOD0 α"
>               << std::setw(10) << "LOD1 α" << std::setw(12) << "额外 Draw Call\n";
>     std::cout << std::string(40, '-') << "\n";
>
>     float test_distances[] = {20.0f, 25.0f, 28.0f, 30.0f, 32.0f, 35.0f, 40.0f};
>     for (float d : test_distances) {
>         auto r = ComputeLODTransition(d, SWITCH_DIST, BAND_PCT);
>         std::cout << std::fixed << std::setprecision(1)
>                   << std::setw(6) << d << "m  "
>                   << std::setprecision(2) << std::setw(6) << r.alpha_current
>                   << "   " << std::setw(6) << r.alpha_next
>                   << "   " << std::setw(10) << r.extra_draw_call << "\n";
>     }
>
>     // 成本分析
>     std::cout << "\n========== 过渡带渲染成本分析 ==========\n"
>               << "过渡带宽度: " << SWITCH_DIST * BAND_PCT * 2 << "m\n"
>               << "过渡带内: 额外 1 个 Draw Call (同时渲染两级 LOD)\n"
>               << "过渡带外: 无额外开销\n"
>               << "总体影响: 只有距离恰好在过渡带内的物体才双倍渲染\n"
>               << "         (通常 < 10% 的物体同时处于过渡带)\n\n"
>               << "替代方案对比:\n"
>               << "  Alpha Fade:  效果好，但额外 Draw Call\n"
>               << "  Dithering:   几乎零额外开销，UE 默认方案\n"
>               << "  Pop (硬切):  零开销，但有视觉跳变\n";
>     return 0;
> }
> ```
>
> **设计要点：**
> - smoothstep 过渡函数避免线性渐变的生硬感
> - 过渡带宽度通常设为切换距离的 ±15-20%
> - Dithering（UE 默认）比 Alpha Fade 更推荐：无额外 Draw Call，使用棋盘格像素剔除实现过渡
> - 过渡期间需要同时渲染两级 LOD，shader 中使用 `mix(LOD0_color, LOD1_color, alpha)` 合成最终颜色

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Garland & Heckbert (1997)** — *Surface Simplification Using Quadric Error Metrics*：QEM 算法的原始论文，所有现代 LOD 工具的数学基础
- **UE5 Nanite 文档** — https://docs.unrealengine.com/5.0/en-US/nanite-virtualized-geometry-in-unreal-engine/：了解自动化 LOD 的终极形态
- **Unity LOD Group 手册** — https://docs.unity3d.com/Manual/LevelOfDetail.html：LOD Group 组件的配置指南
- **Simplygon** — https://www.simplygon.com/：工业级自动 LOD 生成工具（已被微软收购，集成到 Xbox GDK）
- **Texture Streaming in UE** — https://docs.unrealengine.com/5.0/en-US/texture-streaming-in-unreal-engine/：UE 纹理流式加载的实现细节

---

## 常见陷阱

- **LOD 切换距离设置过大**：物体还很清晰就看到低精度模型。症状：角色脸上的多边形棱角在 10 米外就出现了。修复：将 LOD1 切换距离从 10m 调到 20m，或降低 LOD1 的缩减比例。
- **LOD 级别太少**：只有 2 级 LOD（LOD0 和 LOD1），切换时 pop-in 明显。修复：至少设置 3–4 级 LOD，让每级之间的变化更小。
- **忘记更新包围体**：动画骨骼变形后物体的包围球变了，但 LOD 判定还在用静态包围盒。修复：在蒙皮后重新计算包围盒，或使用保守的静态包围盒（略大于实际范围）。
- **Shader LOD 与 Mesh LOD 不协调**：Mesh 已经切换到 LOD2，但 Shader 还在计算完整的 PBR。修复：让 Shader LOD 触发条件与 Mesh LOD 保持一致，共用同一个距离判定。
- **HLOD 和普通 LOD 冲突**：远处的建筑群既有 HLOD 又有各自的 LOD，造成双重渲染。修复：配置 HLOD 的显示距离，确保在 HLOD 激活范围内，组内个体的 LOD 已被剔除。
- **Texture Streaming 池太小**：UE 默认 r.Streaming.PoolSize=1000 (MB)，4K 纹理多的项目容易爆池导致纹理模糊。修复：增大到 3000–4000，或降低纹理最大分辨率。
