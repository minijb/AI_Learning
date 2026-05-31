# Unity 渲染管线优化 — URP/HDRP 选型与配置
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 60min
> 前置知识: Draw Call 合批、GPU 基础架构、Shader 基本概念
---
## 1. 概念讲解

### 为什么需要这个？

Unity 提供三条渲染管线，选错管线意味着项目后期可能面临推倒重来的风险。一条管线从根本上决定了你的 Draw Call 上限、支持的图形特性、跨平台兼容性以及最终的性能天花板。本节帮你建立「管线即架构」的认知——不是改几个参数，而是从项目立项阶段就做对选择。

**关键事实**：
- Built-in RP：Unity 2022 仍支持但不再接受新特性，适合维护老项目
- URP：2019 年推出，覆盖移动端到 PC 端的单一管线，Unity 的战略重心
- HDRP：面向高端 PC/主机的影视级管线，手游不可能跑

### 核心思想

三条管线的核心差异不在于「画质高低」，而在于**可编程性、批处理策略、GPU 驻留数据路径**三个维度。URP 的核心武器是 SRP Batcher——它不是传统的 Draw Call Batch，而是让 GPU 端材质属性驻留，避免每帧重复上传。理解这个差异，才能理解 URP 为什么在移动端可以做到数千个不同材质物体的稳定渲染。

#### 1. 三条管线全景对比

| 特性 | Built-in RP | URP | HDRP |
|------|-------------|-----|------|
| 渲染路径 | Forward / Deferred | Forward / Forward+ / Deferred | Deferred / Forward / Forward+ |
| SRP Batcher | 不支持 | 内置 | 内置 |
| 可编程渲染 | 有限（CommandBuffer） | ScriptableRenderPass | CustomPass / ScriptableRenderPass |
| 图形 API | 全平台 | 全平台 | DX12 / Vulkan / Metal |
| 移动端 | 支持（无优化） | **主力目标** | 不支持 |
| 光照上限 | 实时光无限制（贵） | 实时光 ≤ 8（Forward+ 放宽） | 实时光无上限 |
| 阴影 | 基础 Cascaded | 主光源 Per-Object 优化 | 全特性（接触阴影、微阴影） |
| 后处理 | 第三方 | Volume 系统 | Volume 系统 |
| Asset Store 兼容 | 全兼容 | 大部分兼容（需升级） | 小部分兼容 |

#### 2. SRP Batcher 原理——URP 的性能引擎

传统渲染中，GPU 每帧需要从 CPU 上传大量的材质属性（constants、textures、buffers）。SRP Batcher 通过两个关键设计消除这个开销：

**（A）持久化 GPU 属性块**
URP 要求 Shader 将所有材质属性声明在 `UnityPerMaterial` CBUFFER 中。引擎将这些属性一次性上传到 GPU 端，并维护一个持久化的 buffer。后续帧中，只要材质属性不变，就不需要重新上传——只需要切换指针。

**（B）大型 GPU 数据表**
引擎在 GPU 端维护两张表：
- **Per-Object 表**：每对象的基础变换、LOD 因子等（引擎自动管理）
- **Per-Material 表**：所有材质的属性（Shader 中声明在 `UnityPerMaterial` 内的变量）

渲染时，SRP Batcher 批量遍历场景中的 Renderer，逐对象写入 Per-Object 数据，然后直接切换 Per-Material 指针——这个过程比传统 SetPass Call 快 3~10 倍。

**兼容性条件**：
- Shader 必须声明 `CBUFFER_START(UnityPerMaterial)` / `CBUFFER_END`
- 对象必须是 MeshRenderer / SkinnedMeshRenderer
- 材质不能使用 MaterialPropertyBlock（它会绕过 CBUFFER）

#### 3. 渲染路径选择

**Forward（移动端首选）**：
- 每个物体的每个光源产生额外 Pass
- 光源数 ≤ 1~2 时，效率最高（无 GBuffer 开销）
- 内存友好，无需多 RenderTarget

**Forward+（URP 12+）**：
- 屏幕空间切分为 Tile，每 Tile 计算受影响的光源列表
- 支持大量实时光源（理论上无上限，实际 32~64 仍可接受）
- 内存开销高于传统 Forward，但远低于 Deferred
- 需要 compute shader 支持（移动端 ES 3.1+ 或 Metal）

**Deferred（PC/主机）**：
- 几何信息写入 GBuffer（Albedo / Normal / Depth / MaterialFlags 等 4~6 张 RT）
- 光照在屏幕空间独立计算，光源数量几乎不影响几何阶段
- 移动端致命伤：带宽占用（需要读写多张高精度 RT）
- 不支持 MSAA（需要其他抗锯齿方案）

#### 4. URP Render Graph（URP 14+ / Unity 2023.1+）

Render Graph 是 URP 最新的资源管理框架。它让引擎在渲染前预分析整个帧的所有 Pass，然后：
- **自动管理中间 RT 的生命周期**（创建、复用、销毁），避免手动的 `RenderTexture.ReleaseTemporary`
- **native render pass 优化**（移动端 Tile-based GPU 可利用 subpass 减少带宽）
- **资源 barrier 自动插入**（确保 Read-After-Write 的正确性）

传统 URP 中，开发者手写 `ScriptableRenderPass` 需要显式管理 RenderTarget 的创建和释放；Render Graph 将这一步自动化，减少了人为内存泄漏和不必要的 RT 分配。

#### 5. URP 核心性能配置项

在 `Assets/Settings/URP-*.asset` 中，以下选项对性能影响最大：

| 配置项 | 作用 | 性能建议 |
|--------|------|----------|
| Main Light | 逐像素主光源 | 移动端关掉 Per Pixel，改用逐顶点或烘焙 |
| Cast Shadows | 主光源投射阴影 | 移动端关闭（或用静态阴影烘焙） |
| Shadow Resolution | 阴影贴图分辨率 | 移动端 512~1024，PC 2048~4096 |
| Cascade Count | 级联阴影数 | 移动端 1，PC ≤ 3 |
| Depth Texture | 生成深度纹理 | 按需开启（软粒子、后处理需要） |
| Opaque Texture | 拷贝不透明纹理 | 极贵——仅在需要 GrabPass 效果时开启 |
| Render Scale | 渲染分辨率缩放 | 移动端 0.7~0.85 换取填充率 |
| MSAA | 多重采样抗锯齿 | 移动端 2x，PC 4x；Forward+ 不支持 |
| HDR | 高动态范围 | 移动端关闭节省 2x 内存 |
| Intermediate Texture | 中间渲染纹理 | URP 14+ 可设为 Auto（Render Graph 自动管理） |
| LOD Bias | LOD 切换距离偏置 | 移动端可适度提高以提前切换到低模 |

#### 6. HDRP 专属优化考量

HDRP 对性能的要求远高于 URP：

- **延迟 + 前向混合**：不透明物体走 Deferred，透明物体走 Forward，利用每种路径的优势
- **Tile/Cluster 光照**：HDRP 自动将屏幕空间分为 Tile（或视锥体 Cluster），每 Tile 追踪影响它的光源。移动端无法承受这种计算
- **体积系统（Volume）**：全局雾、局部体积光、体积云等——每一项都有独立的 GPU 开销。在 HDRP 中需要显式关闭不需要的 Volume 组件
- **光线追踪**：RTX 下的反射、阴影、AO、GI 每一项都有极高开销。即使是 RTX 4090，全开 RT GI 在 4K 下也可能掉到 30fps 以下

#### 7. Frame Debugger 走查流程

Frame Debugger（Window → Analysis → Frame Debugger）是排查渲染问题的第一工具：

1. **启用 Frame Debugger**，观察当前帧的所有渲染事件
2. **按 Draw Call 分组浏览**：每个事件显示 Draw Call 数量、所用 Shader、RT 格式
3. **关注 SetPass Call 数量**：SetPass 切换是最大的 CPU 瓶颈之一——每切换一次，CPU 需要重新设置 GPU 状态
4. **检查 Clear 事件**：过多的 RenderTarget Clear 意味着管线在做重复工作
5. **检查 Copy 事件**：RenderTexture 的 Blit/Copy 意味着带宽浪费

**典型诊断流程**：
```
Frame Debugger 打开
→ 观察 Draw Call 总数（移动端 < 200, PC < 2000）
→ 观察 SetPass Call 数（应远小于 Draw Call——SRP Batcher 生效的标志）
→ 检查是否有非预期的 Fullscreen Pass（Opaque Texture 导致）
→ 检查阴影 Pass（Shadow Map 渲染开销）
→ 检查后处理 Pass（Bloom、DoF 等全屏特效）
```

---

## 2. 代码示例

### 示例 A：检查 SRP Batcher 兼容性

```csharp
// File: Scripts/Profiling/SRPBatcherCompatibilityChecker.cs
// 放在 Editor 文件夹下作为 Editor 工具
// 功能：遍历所有 Shader，检查是否声明了 UnityPerMaterial CBUFFER

#if UNITY_EDITOR
using UnityEngine;
using UnityEditor;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;

public class SRPBatcherCompatibilityChecker : EditorWindow
{
    private Vector2 scrollPos;
    private List<ShaderReport> reports = new List<ShaderReport>();
    private int compatibleCount;
    private int incompatibleCount;

    private struct ShaderReport
    {
        public string shaderName;
        public string assetPath;
        public bool isCompatible;
        public string reason;
    }

    [MenuItem("Tools/Performance/Check SRP Batcher Compatibility")]
    public static void ShowWindow()
    {
        GetWindow<SRPBatcherCompatibilityChecker>("SRP Batcher Checker");
    }

    private void OnGUI()
    {
        EditorGUILayout.LabelField("SRP Batcher 兼容性检查", EditorStyles.boldLabel);
        EditorGUILayout.Space();

        if (GUILayout.Button("扫描所有 Shader", GUILayout.Height(30)))
        {
            ScanAllShaders();
        }

        EditorGUILayout.Space();
        EditorGUILayout.LabelField($"兼容: {compatibleCount}  |  不兼容: {incompatibleCount}");

        scrollPos = EditorGUILayout.BeginScrollView(scrollPos);
        foreach (var report in reports)
        {
            GUI.color = report.isCompatible ? Color.green : Color.red;
            EditorGUILayout.BeginHorizontal("box");
            EditorGUILayout.LabelField(report.shaderName, GUILayout.Width(300));
            EditorGUILayout.LabelField(report.reason, GUILayout.Width(500));
            EditorGUILayout.ObjectField(
                AssetDatabase.LoadAssetAtPath<Shader>(report.assetPath),
                typeof(Shader), false);
            EditorGUILayout.EndHorizontal();
        }
        GUI.color = Color.white;
        EditorGUILayout.EndScrollView();
    }

    private void ScanAllShaders()
    {
        reports.Clear();
        compatibleCount = 0;
        incompatibleCount = 0;

        string[] shaderGuids = AssetDatabase.FindAssets("t:Shader");
        foreach (string guid in shaderGuids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            Shader shader = AssetDatabase.LoadAssetAtPath<Shader>(path);
            if (shader == null) continue;

            string source = File.ReadAllText(path);
            var report = new ShaderReport
            {
                shaderName = shader.name,
                assetPath = path
            };

            // 检查 UnityPerMaterial CBUFFER 声明（SRP Batcher 兼容的关键）
            bool hasPerMaterialCBuffer = Regex.IsMatch(
                source,
                @"CBUFFER_START\s*\(\s*UnityPerMaterial\s*\)"
            );

            bool hasSRPBatcherTag = source.Contains("\"SRPBatcher\"")
                && source.Contains("\"ForceIntoSRPBatcher\"");

            if (hasPerMaterialCBuffer)
            {
                report.isCompatible = true;
                report.reason = "已声明 UnityPerMaterial CBUFFER — SRP Batcher 兼容";
                compatibleCount++;
            }
            else if (hasSRPBatcherTag)
            {
                report.isCompatible = true;
                report.reason = "通过标签强制加入 SRP Batcher（非最佳实践）";
                compatibleCount++;
            }
            else
            {
                report.isCompatible = false;
                report.reason = "缺少 UnityPerMaterial CBUFFER — SRP Batcher 不兼容";
                incompatibleCount++;
            }

            reports.Add(report);
        }

        // 按兼容性排序（不兼容的排前面以便关注）
        reports.Sort((a, b) => a.isCompatible.CompareTo(b.isCompatible));
    }
}
#endif
```

**运行方式**：Unity Editor → Tools → Performance → Check SRP Batcher Compatibility

### 示例 B：URP 自定义 Renderer Feature — 批量精灵排序

```csharp
// File: Scripts/Rendering/BatchSpriteRenderFeature.cs
// 功能：自定义 Renderer Feature，在 Forward 渲染前插入批量绘制 Pass
// 实际项目中可用于绘制 Debug 可视化、Gizmos、批量精灵等

using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

public class BatchSpriteRenderFeature : ScriptableRendererFeature
{
    [System.Serializable]
    public class Settings
    {
        public Material spriteMaterial;
        public LayerMask layerMask = -1;
        public RenderPassEvent renderPassEvent = RenderPassEvent.AfterRenderingOpaques;
    }

    public Settings settings = new Settings();
    private BatchSpritePass batchSpritePass;

    public override void Create()
    {
        batchSpritePass = new BatchSpritePass(settings);
        batchSpritePass.renderPassEvent = settings.renderPassEvent;
    }

    public override void AddRenderPasses(
        ScriptableRenderer renderer,
        ref RenderingData renderingData)
    {
        if (settings.spriteMaterial == null) return;
        renderer.EnqueuePass(batchSpritePass);
    }

    private class BatchSpritePass : ScriptableRenderPass
    {
        private readonly Settings settings;
        private readonly Matrix4x4[] matrices = new Matrix4x4[1023];
        private readonly Vector4[] colors = new Vector4[1023];
        private Mesh quadMesh;
        private MaterialPropertyBlock propertyBlock;

        public BatchSpritePass(Settings settings)
        {
            this.settings = settings;
            // 与内置管线不同，URP render pass 不需要手动设置 renderTarget
        }

        public override void OnCameraSetup(
            CommandBuffer cmd, ref RenderingData renderingData)
        {
            // 使用当前摄像机的颜色 RT（URP 自动管理）
        }

        public override void Execute(
            ScriptableRenderContext context,
            ref RenderingData renderingData)
        {
            if (settings.spriteMaterial == null) return;

            CommandBuffer cmd = CommandBufferPool.Get("BatchSpritePass");

            // 收集场景中标记为指定 Layer 的 SpriteRenderer
            // 实际项目中应从缓存的数据结构读取
            // 这里展示批量绘制 API 的使用
            if (quadMesh == null)
            {
                quadMesh = CreateQuadMesh();
            }

            // 模拟游戏逻辑中收集到的变换矩阵
            // 真实场景中这些来自 ECS/Job System 的计算结果
            int count = Unity.Mathematics.math.min(1023, 500); // 500 个精灵
            for (int i = 0; i < count; i++)
            {
                float x = (i % 25) * 2f - 24f;
                float y = (i / 25) * 2f - 20f;
                matrices[i] = Matrix4x4.TRS(
                    new Vector3(x, y, 0),
                    Quaternion.identity,
                    Vector3.one * 0.8f);
                colors[i] = new Vector4(
                    (i % 3) / 2f + 0.5f,
                    ((i + 1) % 3) / 2f + 0.5f,
                    ((i + 2) % 3) / 2f + 0.5f,
                    1f);
            }

            // 关键 API: DrawMeshInstanced 单次 Draw Call 绘制所有实例
            // URP 下，SRP Batcher 会自动接管 Instanced Draw
            if (propertyBlock == null)
                propertyBlock = new MaterialPropertyBlock();

            // 将颜色数组上传到 MaterialPropertyBlock
            // 注意：SRP Batcher 兼容的 Shader 才能高效使用此 API
            propertyBlock.SetVectorArray("_BaseColor", colors);

            cmd.DrawMeshInstanced(
                quadMesh, 0, settings.spriteMaterial, 0,
                matrices, count, propertyBlock);

            context.ExecuteCommandBuffer(cmd);
            CommandBufferPool.Release(cmd);
        }

        private Mesh CreateQuadMesh()
        {
            Mesh mesh = new Mesh();
            mesh.vertices = new Vector3[]
            {
                new Vector3(-0.5f, -0.5f, 0),
                new Vector3( 0.5f, -0.5f, 0),
                new Vector3(-0.5f,  0.5f, 0),
                new Vector3( 0.5f,  0.5f, 0),
            };
            mesh.uv = new Vector2[]
            {
                new Vector2(0, 0), new Vector2(1, 0),
                new Vector2(0, 1), new Vector2(1, 1)
            };
            mesh.triangles = new int[] { 0, 2, 1, 2, 3, 1 };
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }
    }
}
```

**配置方式**：在 URP Renderer Asset 上添加 `BatchSpriteRenderFeature`。

### 示例 C：SetPass Call 与 Batch 统计脚本

```csharp
// File: Scripts/Profiling/RenderStatsDisplay.cs
// 功能：在 Game View 左上角显示渲染统计数据
// 通过 Unity 内置 API 实时获取 Draw Call、SetPass Call、Batch 数量

using UnityEngine;
using UnityEngine.Rendering;

public class RenderStatsDisplay : MonoBehaviour
{
    [SerializeField] private KeyCode toggleKey = KeyCode.F2;
    [SerializeField] private int targetFPS = 60;

    private bool showStats = true;
    private GUIStyle style;
    private Rect statsRect;

    // 历史数据用于计算趋势
    private float[] frameTimeHistory = new float[60];
    private int historyIndex;

    private void Awake()
    {
        statsRect = new Rect(10, 10, 400, 200);
    }

    private void Update()
    {
        if (Input.GetKeyDown(toggleKey))
            showStats = !showStats;

        // 记录帧时间历史
        frameTimeHistory[historyIndex] = Time.unscaledDeltaTime * 1000f;
        historyIndex = (historyIndex + 1) % frameTimeHistory.Length;
    }

    private void OnGUI()
    {
        if (!showStats) return;

        if (style == null)
        {
            style = new GUIStyle(GUI.skin.label);
            style.fontSize = 14;
            style.normal.textColor = Color.green;
        }

        float avgFrameTime = 0f;
        float maxFrameTime = 0f;
        int count = 0;
        for (int i = 0; i < frameTimeHistory.Length; i++)
        {
            if (frameTimeHistory[i] > 0.01f)
            {
                avgFrameTime += frameTimeHistory[i];
                maxFrameTime = Mathf.Max(maxFrameTime, frameTimeHistory[i]);
                count++;
            }
        }
        avgFrameTime /= Mathf.Max(count, 1);

        // 获取 Unity 内置渲染统计
        // 这些数据来自 Unity PlayerLoop 的渲染阶段
        int drawCalls = UnityEngine.Rendering.UnityStats.drawCalls;
        int batches = UnityEngine.Rendering.UnityStats.batches;
        int setPassCalls = UnityEngine.Rendering.UnityStats.setPassCalls;
        int triangles = UnityEngine.Rendering.UnityStats.triangles;
        int vertices = UnityEngine.Rendering.UnityStats.vertices;
        int dynamicBatches = UnityEngine.Rendering.UnityStats.dynamicBatches;
        int staticBatches = UnityEngine.Rendering.UnityStats.staticBatches;

        // 关键指标：SetPass/Frame 是最大的 CPU 瓶颈
        // SRP Batcher 生效时，SetPass << DrawCall
        float batcherRatio = (setPassCalls > 0)
            ? (float)drawCalls / setPassCalls
            : 0f;

        GUI.Box(new Rect(5, 5, 420, 210), "");
        GUI.Label(new Rect(15, 10, 400, 25),
            $"FPS: {1f / Time.unscaledDeltaTime:F1}  |  帧时间: {Time.unscaledDeltaTime * 1000f:F1}ms",
            style);
        GUI.Label(new Rect(15, 35, 400, 25),
            $"平均: {avgFrameTime:F1}ms  |  最大: {maxFrameTime:F1}ms  |  目标: {1000f / targetFPS:F1}ms",
            style);

        GUI.Label(new Rect(15, 65, 400, 25),
            $"Draw Calls: {drawCalls}  |  Batches: {batches}  |  SetPass: {setPassCalls}",
            style);

        // 如果 SetPass 明显少于 DrawCall，SRP Batcher 在起作用
        string batcherStatus;
        if (batcherRatio > 3f)
            batcherStatus = $"SRP Batcher 活跃 (Draw/SetPass={batcherRatio:F1})";
        else if (batcherRatio > 1.5f)
            batcherStatus = $"SRP Batcher 部分工作 (Draw/SetPass={batcherRatio:F1})";
        else
            batcherStatus = $"SRP Batcher 未生效 (Draw/SetPass={batcherRatio:F1})";

        style.normal.textColor = batcherRatio > 3f ? Color.green : Color.yellow;
        GUI.Label(new Rect(15, 90, 400, 25), batcherStatus, style);
        style.normal.textColor = Color.green;

        GUI.Label(new Rect(15, 115, 400, 25),
            $"Static Batching: {staticBatches}  |  Dynamic Batching: {dynamicBatches}",
            style);

        GUI.Label(new Rect(15, 140, 400, 25),
            $"Triangles: {triangles:N0}  |  Vertices: {vertices:N0}",
            style);

        // 管线信息
        string pipelineName = "Unknown";
        if (GraphicsSettings.currentRenderPipeline != null)
            pipelineName = GraphicsSettings.currentRenderPipeline.name;
        GUI.Label(new Rect(15, 165, 400, 25),
            $"管线: {pipelineName}  |  API: {SystemInfo.graphicsDeviceType}",
            style);
    }
}
```

**运行方式**：将此脚本挂载到场景中的任意 GameObject 上即可看到实时统计。按 F2 切换显示。

### URP Asset 优化配置对比

**优化前（默认配置）**：
```yaml
# URP Asset - 默认设置（性能较差的配置）
Main Light: Per Pixel
Cast Shadows: true
Shadow Resolution: 2048
Cascade Count: 4
Depth Texture: On
Opaque Texture: On
Render Scale: 1.0
MSAA: 4x
HDR: true
Additional Lights: Per Pixel
Additional Lights Count: 4
```

**优化后（移动端配置）**：
```yaml
# URP Asset - 移动端优化配置
Main Light: Per Vertex  # 逐顶点光照代替逐像素
Cast Shadows: false      # 使用静态烘焙代替实时阴影
Shadow Resolution: 512   # 如果必须开阴影，降分辨率
Cascade Count: 1         # 单级联（移动端标准）
Depth Texture: On         # 软粒子等需要时再开
Opaque Texture: Off       # 关闭——节省每帧一次全屏 Blit
Render Scale: 0.75        # 75% 渲染分辨率，填充率换帧率
MSAA: 2x                  # 降低到 2x
HDR: false                # 关闭 HDR 节省 RT 内存
Additional Lights: Disabled  # 移动端不用额外逐像素光
Intermediate Texture: Auto   # URP 14+ 让 RenderGraph 管理
LOD Bias: 0.6             # 更早切换到低精度 LOD
```

**URP 优化前后性能对比（典型中端手机）**：
```
指标                    优化前        优化后        提升
Frame Time              35ms          16ms          54%
Draw Calls              420           280           33%
SetPass Calls           85            18            79%
Opaque Texture 耗时     2.3ms         0ms           ∞
阴影渲染耗时             4.1ms         0ms           ∞
GPU 占用                98%           55%           44%
```

---

## 3. 练习

### 练习 1：管线诊断 — Frame Debugger 走查

1. 在任意 URP 项目中，打开 Frame Debugger（Window → Analysis → Frame Debugger）
2. 点击 Enable 按钮，观察当前帧的所有渲染事件
3. 回答以下问题：
   - 当前场景共有多少个 Draw Call？
   - 有多少个 SetPass Call？Draw/SetPass 比率是多少？
   - 有没有非预期的 `CopyFramebuffer`（Opaque Texture 导致）？
   - 阴影 Pass 占了多少个 Draw Call？
   - 哪个 Pass 耗时最长（观察 RenderThread 的时间差异）？
4. 关闭 Opaque Texture（URP Asset → Opaque Texture = Off）后重新走查，观察 Frame Debugger 中减少的事件

**目标**：能独立使用 Frame Debugger 诊断渲染管线。

### 练习 2：自定义 SRP Batcher 兼容 Shader + 批量测试

1. 创建一个新的 Unlit Shader（URP），确保包含 `CBUFFER_START(UnityPerMaterial)` 声明
2. 在场景中创建 500 个不同颜色的 Cube（每种颜色一个材质）
3. 使用示例 C 的脚本观测 Draw Call 和 SetPass Call
4. **对比实验**：将同一个 Shader 的 `UnityPerMaterial` CBUFFER 移除，重新观测数据
5. 记录两次测试的 SetPass Call 差异

**预期结果**：
- 兼容版：SetPass Call ≈ 材质种类数（而非物体数），Draw/SepPass 比率高
- 不兼容版：每个材质一次 SetPass 切换（但仍可能少于 500，因为相同材质会合批）

### 练习 3：URP Renderer Feature 实战（挑战）

1. 在 URP 项目中创建一个 `ScriptableRendererFeature`
2. 实现一个简单的调试可视化：在 Opaque 渲染之后、Transparent 渲染之前，绘制所有 Directional Light 的视锥体线框
3. 使用 `CommandBuffer.DrawMesh` 或 `DrawProcedural` 绘制线框
4. 验证：在 Scene View 和 Game View 中都能看到绘制的线框
5. 使用 Frame Debugger 验证你的 Pass 确实在正确的阶段执行

---

## 4. 扩展阅读

- Unity 官方文档：[Universal Render Pipeline overview](https://docs.unity3d.com/Packages/com.unity.render-pipelines.universal@latest)
- Unity Blog：[SRP Batcher: Speed up your rendering](https://blog.unity.com/technology/srp-batcher-speed-up-your-rendering)
- Unity 论坛讨论：[URP Performance Guidelines](https://docs.unity3d.com/Packages/com.unity.render-pipelines.universal@latest/manual/performance.html)
- 官方示例项目：[URP Samples](https://github.com/Unity-Technologies/UniversalRenderingExamples)
- GDC 2022：[Optimizing Unity Games for Mobile in URP](https://www.youtube.com/results?search_query=GDC+URP+mobile+optimization)
- Render Graph 深入：[Unity Render Graph System documentation](https://docs.unity3d.com/Packages/com.unity.render-pipelines.core@latest/manual/render-graph-system.html)

---

## 常见陷阱

1. **「URP 只适合移动端」**：URP 是 Unity 的主力管线，PC/主机游戏同样使用（如 Cuphead、Hollow Knight: Silksong）。它不是「低端管线」。

2. **忘记设置 Shader 的 SRP Batcher 兼容性**：即使 Shader 声明了 `UnityPerMaterial`，如果 Shader 使用了 MaterialPropertyBlock 或 Shader keywords 过多，SRP Batcher 仍可能 fallback。

3. **Opaque Texture 默认开启**：URP 默认开启 Opaque Texture（为了 GrabPass 兼容），但它导致每帧一次全屏 Blit，在移动端成本极高。除非明确需要（软粒子、折射效果），否则应关闭。

4. **阴影开得太「大方」**：移动端的主光源 Per-Object 阴影已经很贵了，再加 4 级级联阴影会让 GPU 带宽直接爆炸。规则：移动端要么烘焙，要么单级联 512 分辨率。

5. **使用 MaterialPropertyBlock 打断了 SRP Batcher**：MaterialPropertyBlock 会强制引擎走传统路径（每个实例独立上传属性），在 URP 中应避免与 SRP Batcher 同时使用。

6. **忽视管线切换成本**：从 Built-in RP 迁移到 URP 不是「改个 Asset 文件」——所有 Shader 需要重写、所有后处理需要替换、光照烘焙需要重新生成。预估迁移成本：小型项目 1~2 周，中型项目 1~2 月。

7. **HDRP 在不需要高画质的场景中使用**：HDRP 的 4K GBuffer 在集成显卡上是灾难。如果你不需要体积雾、光线追踪、屏幕空间反射，别碰 HDRP——URP 足够了。
