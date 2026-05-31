# Unity 内存管理与 Addressables
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50min
> 前置知识: 内存分配策略（对象池、Arena）、GC 规避策略
---
## 1. 概念讲解

### 为什么需要这个？

2018 年 Qihoo 360 统计：移动游戏中 43% 的崩溃与内存超标相关。iOS 对单个 App 的内存限制约为设备总 RAM 的 50%~60%（iPhone 14 Pro 有 6GB，App 约 2.8~3.5GB 可用），超过限制系统会直接 SIGKILL——没有异常、没有日志，玩家看到的就是闪退。

Unity 的「内存问题」不是单一问题，而是**三块内存池的协同管理**：托管堆（C# GC）、原生内存（C++ 引擎/NativeArray）、GPU 内存（纹理/网格/RenderTexture）。三块池互不透明但共享物理 RAM 上限——任何一块爆炸都会导致整体崩溃。

### 核心思想

内存管理的核心任务是**让每一帧的内存分配趋近于零**，并确保常驻内存在平台预算之内。Addressables 解决的是「何时把什么加载进来」的问题——它不是 AssetBundle 的替代品，而是**引用计数 + 异步加载 + 依赖解析**的生命周期管理系统。

#### 1. Unity 内存的三层模型

```
┌────────────────────────────────────────────────────────┐
│                    物理 RAM 上限                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  托管堆       │  │  原生内存     │  │  GPU 内存     │  │
│  │  (Mono/IL2CPP)│  │  (C++ Engine)│  │  (VRAM)      │  │
│  │               │  │               │  │               │  │
│  │ • C# 对象     │  │ • NativeArray │  │ • Texture2D   │  │
│  │ • Scriptable- │  │ • Mesh 数据   │  │ • Mesh        │  │
│  │   Object      │  │ • Asset 元数据│  │ • RenderTex   │  │
│  │ • List<T>     │  │ • Shader 编译 │  │ • ComputeBuf  │  │
│  │ • string      │  │ • Audio 解码  │  │ • Shader 常量 │  │
│  │               │  │               │  │               │  │
│  │ GC: Boehm/    │  │ 手动管理      │  │ 手动管理      │  │
│  │ Precise       │  │               │  │               │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────────────────────────────────────────────────────┘
```

**关键事实**：
- `Texture2D` 在 C# 侧是 ~80 字节的包装对象（托管堆），在 GPU 侧是完整的像素数据（VRAM）
- `Mesh` 同理：C# 侧是引用（托管堆），数据在原生+GPU 内存中
- IL2CPP 的托管堆比 Mono 更紧凑（约 20~30% 更小），但 GC 延迟更高（缺少 generational GC）

#### 2. 各平台的内存预算（经验值）

| 平台 | 设备 RAM | 可用内存上限 | 建议常驻 |
|------|---------|-------------|----------|
| iPhone 12 (4GB) | 4GB | ~2.2GB | < 1.6GB |
| iPhone 14 Pro (6GB) | 6GB | ~3.5GB | < 2.2GB |
| Android 低端 (3GB) | 3GB | ~1.5GB | < 800MB |
| Android 中端 (6GB) | 6GB | ~3GB | < 1.8GB |
| Android 高端 (8GB+) | 8GB | ~4.5GB | < 2.5GB |
| PS5 | 16GB | ~13.5GB | < 10GB |
| Xbox Series X | 16GB | ~13.5GB | < 10GB |
| Switch | 4GB | ~3.2GB | < 2.5GB |
| PC (16GB) | 16GB | ~14GB | < 10GB |

**注意**：这些是操作系统允许的上限，不是达到上限才应该优化——你应该在达到建议常驻值之前就开始主动释放。

#### 3. IL2CPP vs Mono 内存差异

Unity 2022 LTS+ 默认使用 IL2CPP（Mono 仅用于 Editor 和少数平台）：

**Mono（Boehm GC）**：
- 非精确（conservative）扫描：栈上的整数可能被误识别为指针，阻止其指向的对象被回收
- 不压缩堆：碎片随时间积累
- 单线程 Stop-The-World

**IL2CPP**：
- 精确（precise）扫描：只追踪真正的对象引用，误报率接近零
- 使用 libgc（Unity 修改版）：支持增量 GC（Unity 2019.3+）
- 同样不压缩、单线程 Stop-The-World（但有 Incremental GC 分段执行）
- C++ 编译的本机代码，没有 JIT 开销

**内存对比**：
- IL2CPP 的 C# 对象通常更小（类型信息优化）
- IL2CPP 的 GC 暂停时间可能更长（遍历的堆更大，因为是本机代码）
- 启用 Incremental GC（Project Settings → Player → Use incremental GC）将一次大暂停分散到多帧

#### 4. Addressables 系统——核心概念

Addressables 不是 AssetBundle 的替代品，而是它的**生命周期管理器**：

**核心原语**：
- **AssetReference**：对资产的「地址」引用（类似 WeakReference，但不阻止 GC）
- **Addressable Asset**：通过 Address（字符串）或 Label（标签）标识的资产
- **Asset Group**：资产的逻辑分组，可映射到独立的 AssetBundle
- **Load/Unload**：显式的异步加载和释放操作
- **Reference Counting**：引擎内部追踪每个资产的引用次数，只有引用数为 0 时才真正释放

**加载流程**：
```
Addressables.LoadAssetAsync<GameObject>("Enemy_Goblin")
  ↓
Catalog lookup（key → resource location）
  ↓
Dependency resolution（Enemy_Goblin 依赖的材质、纹理、动画）
  ↓
AssetBundle download（如果是远程）或直接从本地加载
  ↓
Asset deserialization
  ↓
回调 / await → GameObject 可用
```

#### 5. Resources 文件夹——为什么应该避免？

`Resources` 文件夹在 Unity 中有两个致命问题：

1. **所有资源都在启动时被索引**：`Resources` 文件夹中的所有资源（不管是否被引用）都会在游戏启动时被注册到一个全局查找表。这意味着：
   - 启动时间线性增长
   - 索引表占用内存（每个资源 ~200 bytes 元数据）
   - 10,000 个资源 = ~2MB 常驻索引开销

2. **资源无法被 Unity 的依赖追踪系统排除**：只要资源在 `Resources` 中，即使场景中没有任何引用，它也会被打包。无法进行「仅打包被引用资源」的优化。

3. **`Resources.Load` 是同步操作**：在游戏循环中调用会导致明显的帧卡顿。

**迁移策略**：`Resources.Load` → `Addressables.LoadAssetAsync`。

#### 6. 纹理 / Mip Streaming

Unity 的 Texture Streaming（纹理流式加载）将纹理的 Mip 链按需加载到 GPU 内存：

- **启用方法**：Quality Settings → Texture Streaming → Add All Textures
- **Mip Map Bias**：控制加载哪个级别的 Mip（越高 = 越低精度 = 越低内存）
- **Memory Budget**：纹理流式加载的内存预算上限
- **不适用场景**：UI 纹理（需要始终完整精度）、Sprite Atlas

**GPU 内存节省**：在 4K 纹理上启用 Mip Streaming，内存从 ~85MB（全 Mip 链）降至 ~1.3MB（仅加载使用到的 Mip Level）。

#### 7. Unity Memory Profiler 实战三步法

1. **抓取快照**（Window → Analysis → Memory Profiler → Capture）
2. **分析三块内存的分布**：
   - Unity Objects：按类型排序，找 Top 10
   - Managed Heap：找非预期的 `List<T>`、`string` 堆积
   - GPU Memory：找大纹理、未压缩的 RenderTexture
3. **对比两个快照**（场景加载前后、关卡切换前后）——增量比绝对值更有用

**典型内存异常模式**：
- Mesh 数量异常多 → 检查是否有非预期的 `Instantiate` 或未释放的 Mesh
- Texture2D 过大 → 检查导入设置（是否用了 4K 纹理做 UI Sprite？）
- `string` 分配过多 → 检查 Log、JSON 解析、字符串拼接
- `Material` 泄漏 → 每帧创建临时材质未释放（`renderer.material` 而非 `sharedMaterial`）

---

## 2. 代码示例

### 示例 A：Addressables 场景异步加载 + 内存监控

```csharp
// File: Scripts/Addressables/AddressableSceneLoader.cs
// 功能：异步加载 Addressables 场景，监控加载过程中的内存变化
// 用法：挂到空 GameObject 上，设置 sceneAddress 后运行

using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;
using UnityEngine.ResourceManagement.ResourceProviders;
using UnityEngine.SceneManagement;
using System.Collections;
using UnityEngine.Profiling;
using System.Text;

public class AddressableSceneLoader : MonoBehaviour
{
    [Header("Addressables 场景配置")]
    [SerializeField] private AssetReference sceneReference;
    // 如果不用 AssetReference，也可以直接用地址字符串
    [SerializeField] private string sceneAddress = "Level_01";

    [Header("UI")]
    [SerializeField] private bool showMemoryGUI = true;

    // 加载状态
    private AsyncOperationHandle<SceneInstance> loadHandle;
    private bool isLoaded;
    private float loadProgress;

    // 内存快照
    private long memBeforeLoad;
    private long memAfterLoad;
    private long managedBeforeLoad;
    private long managedAfterLoad;
    private long nativeBeforeLoad;
    private long nativeAfterLoad;

    // 历史采样（环形缓冲）
    private readonly float[] memHistory = new float[300]; // 5 秒 @ 60fps
    private int memHistoryIndex;
    private GUIStyle guiStyle;

    private void Start()
    {
        // 启动时记录基准内存
        TakeMemorySnapshot(ref memBeforeLoad, ref managedBeforeLoad, ref nativeBeforeLoad);
    }

    private void Update()
    {
        // 每帧记录内存（用于图表）
        memHistory[memHistoryIndex] = GetTotalUsedMemoryMB();
        memHistoryIndex = (memHistoryIndex + 1) % memHistory.Length;

        // 按键加载/卸载
        if (Input.GetKeyDown(KeyCode.L) && !isLoaded)
        {
            StartCoroutine(LoadSceneAsync());
        }
        if (Input.GetKeyDown(KeyCode.U) && isLoaded)
        {
            StartCoroutine(UnloadSceneAsync());
        }
    }

    private IEnumerator LoadSceneAsync()
    {
        TakeMemorySnapshot(ref memBeforeLoad, ref managedBeforeLoad, ref nativeBeforeLoad);

        // 使用地址字符串加载
        loadHandle = Addressables.LoadSceneAsync(
            sceneAddress,
            LoadSceneMode.Additive, // 叠加模式（不销毁当前场景）
            activateOnLoad: true);

        loadHandle.Completed += OnSceneLoaded;

        // 显示加载进度
        while (!loadHandle.IsDone)
        {
            loadProgress = loadHandle.PercentComplete;
            yield return null;
        }
    }

    private void OnSceneLoaded(AsyncOperationHandle<SceneInstance> handle)
    {
        if (handle.Status == AsyncOperationStatus.Succeeded)
        {
            isLoaded = true;
            SceneInstance sceneInstance = handle.Result;
            Debug.Log($"场景加载成功: {sceneInstance.Scene.name}");

            TakeMemorySnapshot(ref memAfterLoad, ref managedAfterLoad, ref nativeAfterLoad);

            long deltaTotal = memAfterLoad - memBeforeLoad;
            long deltaManaged = managedAfterLoad - managedBeforeLoad;
            long deltaNative = nativeAfterLoad - nativeBeforeLoad;

            Debug.Log($"=== 内存增量 ===");
            Debug.Log($"总内存: +{deltaTotal / (1024f * 1024f):F1} MB");
            Debug.Log($"托管堆: +{deltaManaged / (1024f * 1024f):F1} MB");
            Debug.Log($"原生内存: +{deltaNative / (1024f * 1024f):F1} MB");
        }
        else
        {
            Debug.LogError($"场景加载失败: {handle.OperationException}");
        }
    }

    private IEnumerator UnloadSceneAsync()
    {
        if (loadHandle.IsValid())
        {
            var unloadHandle = Addressables.UnloadSceneAsync(
                loadHandle, UnloadSceneOptions.UnloadAllEmbeddedSceneObjects);

            yield return unloadHandle;

            isLoaded = false;
            Debug.Log("场景已卸载");

            // 主动触发一次 GC 和资源释放
            System.GC.Collect();
            Resources.UnloadUnusedAssets();

            Debug.Log("GC + 资源释放完成");
        }
    }

    private void TakeMemorySnapshot(
        ref long total, ref long managed, ref long native)
    {
        // Unity 2022+ 提供了更精确的内存 API
        total = Profiler.GetTotalAllocatedMemoryLong();
        managed = Profiler.GetMonoHeapSizeLong();
        native = Profiler.GetTotalAllocatedMemoryLong() - Profiler.GetMonoHeapSizeLong();
    }

    private float GetTotalUsedMemoryMB()
    {
        return Profiler.GetTotalAllocatedMemoryLong() / (1024f * 1024f);
    }

    private void OnGUI()
    {
        if (!showMemoryGUI) return;

        if (guiStyle == null)
        {
            guiStyle = new GUIStyle(GUI.skin.label);
            guiStyle.fontSize = 13;
            guiStyle.normal.textColor = Color.white;
        }

        float currentMem = GetTotalUsedMemoryMB();

        // 背景
        GUI.Box(new Rect(10, 10, 400, 200), "");

        // 当前内存
        GUI.Label(new Rect(20, 15, 380, 20),
            $"当前总内存: {currentMem:F1} MB", guiStyle);

        // 加载状态
        string statusText = isLoaded
            ? $"场景已加载 ({sceneAddress})"
            : (loadProgress > 0 && loadProgress < 1
                ? $"加载中... {loadProgress * 100:F0}%"
                : "等待加载");
        GUI.Label(new Rect(20, 40, 380, 20), statusText, guiStyle);

        // 加载增量
        if (isLoaded)
        {
            long deltaTotal = memAfterLoad - memBeforeLoad;
            GUI.Label(new Rect(20, 65, 380, 20),
                $"场景加载增量: +{deltaTotal / (1024f * 1024f):F1} MB", guiStyle);
        }

        // 内存历史折线图（简化的柱状显示）
        GUI.Label(new Rect(20, 95, 380, 20),
            "内存趋势 (5秒窗口):", guiStyle);

        float chartY = 115f;
        float chartHeight = 60f;
        float chartWidth = 360f;
        float barWidth = chartWidth / 60f; // 显示最近 60 帧

        // 绘制简化的内存趋势
        float maxMem = 0f;
        for (int i = 0; i < 60 && i < memHistory.Length; i++)
        {
            int idx = (memHistoryIndex - 60 + i + memHistory.Length) % memHistory.Length;
            maxMem = Mathf.Max(maxMem, memHistory[idx]);
        }

        for (int i = 0; i < 60; i++)
        {
            int idx = (memHistoryIndex - 60 + i + memHistory.Length) % memHistory.Length;
            float normalizedHeight = (maxMem > 0)
                ? (memHistory[idx] / maxMem) * chartHeight
                : 0f;

            GUI.Box(new Rect(
                20 + i * barWidth,
                chartY + chartHeight - normalizedHeight,
                barWidth - 1,
                normalizedHeight), "");
        }

        // 操作提示
        GUI.Label(new Rect(20, 185, 380, 20),
            "按 L 加载场景  |  按 U 卸载场景", guiStyle);
    }

    private void OnDestroy()
    {
        if (loadHandle.IsValid())
        {
            Addressables.Release(loadHandle);
        }
    }
}
```

### 示例 B：资源生命周期管理 — 加载/释放封装

```csharp
// File: Scripts/Addressables/AssetLifecycleManager.cs
// 功能：封装 Addressables 的加载/释放生命周期，防止泄漏
// 特性：引用计数、自动卸载、超时清理

using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

public class AssetLifecycleManager : MonoBehaviour
{
    // 单例访问
    public static AssetLifecycleManager Instance { get; private set; }

    // 追踪所有已加载的资产句柄
    private readonly Dictionary<string, TrackedAsset> trackedAssets
        = new Dictionary<string, TrackedAsset>();

    // 超时未使用的资产自动释放 (秒)
    [SerializeField] private float autoReleaseTimeout = 300f; // 5 分钟

    private class TrackedAsset
    {
        public AsyncOperationHandle handle;
        public int refCount;
        public float lastAccessTime;
        public Type assetType;
    }

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }
        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    /// <summary>
    /// 异步加载资产，自动追踪引用计数
    /// </summary>
    public AsyncOperationHandle<T> LoadAsset<T>(string address) where T : UnityEngine.Object
    {
        string key = $"{typeof(T).Name}:{address}";

        if (trackedAssets.TryGetValue(key, out TrackedAsset tracked))
        {
            tracked.refCount++;
            tracked.lastAccessTime = Time.realtimeSinceStartup;
            return tracked.handle.Convert<T>();
        }

        var handle = Addressables.LoadAssetAsync<T>(address);
        tracked = new TrackedAsset
        {
            handle = handle,
            refCount = 1,
            lastAccessTime = Time.realtimeSinceStartup,
            assetType = typeof(T)
        };

        // 如果已同步完成（缓存在内存中），直接记录
        if (handle.IsDone)
        {
            trackedAssets[key] = tracked;
        }
        else
        {
            handle.Completed += (h) =>
            {
                if (h.Status == AsyncOperationStatus.Succeeded)
                    trackedAssets[key] = tracked;
                else
                    Debug.LogError($"加载失败: {address} -> {h.OperationException}");
            };
        }

        return handle;
    }

    /// <summary>
    /// 释放资产引用。引用计数归零时自动调用 Addressables.Release
    /// </summary>
    public void ReleaseAsset(string address, Type assetType = null)
    {
        if (assetType == null) assetType = typeof(UnityEngine.Object);
        string key = $"{assetType.Name}:{address}";

        if (!trackedAssets.TryGetValue(key, out TrackedAsset tracked))
        {
            Debug.LogWarning($"尝试释放未追踪的资产: {key}");
            return;
        }

        tracked.refCount--;
        if (tracked.refCount <= 0)
        {
            Addressables.Release(tracked.handle);
            trackedAssets.Remove(key);
        }
    }

    /// <summary>
    /// 每次调用 Update 检查超时资产并自动释放
    /// </summary>
    private void Update()
    {
        float now = Time.realtimeSinceStartup;
        var toRelease = new List<string>();

        foreach (var kvp in trackedAssets)
        {
            if (kvp.Value.refCount <= 0
                && (now - kvp.Value.lastAccessTime) > autoReleaseTimeout)
            {
                toRelease.Add(kvp.Key);
            }
        }

        foreach (string key in toRelease)
        {
            TrackedAsset tracked = trackedAssets[key];
            Addressables.Release(tracked.handle);
            trackedAssets.Remove(key);
            Debug.Log($"[AssetManager] 自动释放超时资产: {key}");
        }
    }

    /// <summary>
    /// 获取当前追踪的资产列表（用于调试）
    /// </summary>
    public string GetDebugReport()
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("=== 当前追踪资产 ===");
        foreach (var kvp in trackedAssets)
        {
            sb.AppendLine($"  {kvp.Key}: refs={kvp.Value.refCount}, " +
                $"idle={Time.realtimeSinceStartup - kvp.Value.lastAccessTime:F1}s");
        }
        return sb.ToString();
    }

    private void OnDestroy()
    {
        // 释放所有追踪的资产
        foreach (var kvp in trackedAssets)
        {
            Addressables.Release(kvp.Value.handle);
        }
        trackedAssets.Clear();
    }
}
```

### 示例 C：Resources vs Addressables 内存对比

```csharp
// File: Scripts/Addressables/ResourcesVsAddressablesTest.cs
// 功能：对比 Resources.Load 和 Addressables 加载同一组资产的内存占用
// 用法：挂到空 GameObject 上，确保 Resources 和 Addressables 中有相同的资产

using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;
using System.Collections;
using System.Collections.Generic;
using UnityEngine.Profiling;

public class ResourcesVsAddressablesTest : MonoBehaviour
{
    [Header("测试资产")]
    [SerializeField] private string[] resourcesPaths = new string[]
    {
        "Prefabs/Enemy_Goblin",
        "Prefabs/Enemy_Orc",
        "Prefabs/Prop_Tree",
    };

    [SerializeField] private AssetReferenceGameObject[] addressableRefs;

    [Header("结果")]
    private long resourcesMemoryDelta;
    private long addressablesMemoryDelta;
    private float resourcesLoadTime;
    private float addressablesLoadTime;

    private readonly List<GameObject> loadedObjects = new List<GameObject>();

    private void OnGUI()
    {
        if (guiStyle == null)
        {
            guiStyle = new GUIStyle(GUI.skin.label)
            { fontSize = 14, normal = { textColor = Color.white } };
        }

        GUI.Box(new Rect(10, 10, 500, 200), "");

        GUILayout.BeginArea(new Rect(20, 15, 480, 190));
        GUILayout.Label("=== Resources vs Addressables 对比测试 ===");

        if (GUILayout.Button("测试 Resources.Load", GUILayout.Height(30)))
        {
            StartCoroutine(TestResourcesLoad());
        }
        if (GUILayout.Button("测试 Addressables.Load", GUILayout.Height(30)))
        {
            StartCoroutine(TestAddressablesLoad());
        }
        if (GUILayout.Button("卸载所有资源", GUILayout.Height(30)))
        {
            UnloadAll();
        }

        GUILayout.Space(10);
        GUILayout.Label($"Resources 加载时间: {resourcesLoadTime:F2}ms  |  内存增量: {resourcesMemoryDelta / (1024f * 1024f):F2} MB");
        GUILayout.Label($"Addressables 加载时间: {addressablesLoadTime:F2}ms  |  内存增量: {addressablesMemoryDelta / (1024f * 1024f):F2} MB");

        float ratio = resourcesMemoryDelta > 0
            ? (float)addressablesMemoryDelta / resourcesMemoryDelta
            : 0f;
        GUILayout.Label($"Addressables / Resources 内存比: {ratio:F2}x");
        GUILayout.EndArea();
    }

    private GUIStyle guiStyle;

    private IEnumerator TestResourcesLoad()
    {
        UnloadAll();
        yield return new WaitForSeconds(0.5f);

        long memBefore = Profiler.GetTotalAllocatedMemoryLong();
        float startTime = Time.realtimeSinceStartup;

        foreach (string path in resourcesPaths)
        {
            GameObject prefab = Resources.Load<GameObject>(path);
            if (prefab != null)
            {
                loadedObjects.Add(Instantiate(prefab));
            }
            else
            {
                Debug.LogWarning($"Resources 中未找到: {path}");
            }
        }

        resourcesLoadTime = (Time.realtimeSinceStartup - startTime) * 1000f;
        resourcesMemoryDelta = Profiler.GetTotalAllocatedMemoryLong() - memBefore;

        Debug.Log($"Resources 加载完成: {resourcesLoadTime:F1}ms, " +
                  $"+{resourcesMemoryDelta / (1024f * 1024f):F1}MB");
    }

    private IEnumerator TestAddressablesLoad()
    {
        UnloadAll();
        yield return new WaitForSeconds(0.5f);

        long memBefore = Profiler.GetTotalAllocatedMemoryLong();
        float startTime = Time.realtimeSinceStartup;

        var handles = new List<AsyncOperationHandle<GameObject>>();

        foreach (var assetRef in addressableRefs)
        {
            if (assetRef == null) continue;

            var handle = assetRef.LoadAssetAsync();
            handles.Add(handle);

            yield return handle;

            if (handle.Status == AsyncOperationStatus.Succeeded)
            {
                loadedObjects.Add(Instantiate(handle.Result));
            }
        }

        addressablesLoadTime = (Time.realtimeSinceStartup - startTime) * 1000f;
        addressablesMemoryDelta = Profiler.GetTotalAllocatedMemoryLong() - memBefore;
    }

    private void UnloadAll()
    {
        foreach (var obj in loadedObjects)
        {
            if (obj != null) Destroy(obj);
        }
        loadedObjects.Clear();

        // 触发卸载
        System.GC.Collect();
        Resources.UnloadUnusedAssets();

        resourcesMemoryDelta = 0;
        addressablesMemoryDelta = 0;
        resourcesLoadTime = 0;
        addressablesLoadTime = 0;
    }
}
```

**预期结果**（在包含 3 个角色 Prefab 的测试项目中）：

```
指标                    Resources       Addressables    说明
加载时间                12ms            15ms            Addressables 略有异步开销
内存增量                +45MB           +42MB           相近（预加载模式下）
卸载后内存回收          不完全           完全             Resources 有缓存残留
启动时索引内存           ~2MB            0               Resources 预索引所有资产
```

---

## 3. 练习

### 练习 1：Memory Profiler 快照对比

1. 在任意 URP 项目中，打开 Window → Analysis → Memory Profiler
2. 捕获第一张快照（场景初始状态）
3. 通过 Addressables 加载一个新场景
4. 捕获第二张快照
5. 切换到 Diff 模式，找出内存增量的 Top 10 类型
6. 写出你的分析结论：哪些资产占用了最多的内存？预期内还是异常？

### 练习 2：手动 Addressables Group 策略设计

1. 为一个假设的开放世界手游设计 Addressables Group 分区策略
2. 写出以下内容：
   - **Remote vs Local**：哪些资产放在本地（安装包内），哪些放在远程 CDN？
   - **Group 划分**：按什么维度分组？（场景、角色类型、稀有度、LOD 等级？）
   - **Bundle 大小**：单个 AssetBundle 的理想大小是多少？为什么？
   - **加载时机**：什么时候预加载下一片区域？什么时候释放当前区域？
3. 在你的设计中，如果玩家快速传送（跳过多个区域），内存如何处理？写出处理流程

**参考答案框架**：
- Local：核心 UI、玩家角色、启动场景、Essential 音效
- Remote：非主线关卡、皮肤、非核心语音
- Bundle 大小：1~5MB（移动端下载友好，CDN 缓存友好）
- 传送处理：取消所有正在进行的加载，释放所有非当前区域的资源，加载目标区域

### 练习 3：内存泄漏检测器（挑战）

基于 `AssetLifecycleManager`，扩展实现一个内存泄漏检测工具：

1. 每 10 秒记录一次所有追踪资产的状态
2. 如果某个资产的引用计数 > 0 但超过 60 秒未被访问（`lastAccessTime`），标记为「可疑泄漏」
3. 输出可疑泄漏报告（资产地址、引用计数、空闲时间、引用者堆栈）
4. 在 Game View 中显示泄漏告警图标

**提示**：
- 引用者追踪可以通过 `System.Diagnostics.StackTrace` 捕获（仅在 Editor 下有效）
- Release Build 中可以通过手动埋点追踪

---

## 4. 扩展阅读

- Unity 官方文档：[Addressables System](https://docs.unity3d.com/Packages/com.unity.addressables@latest)
- Unity 官方文档：[Memory Profiler](https://docs.unity3d.com/Packages/com.unity.memoryprofiler@latest)
- Unity Blog：[Understanding the managed heap](https://blog.unity.com/technology/understanding-the-managed-heap)
- Unity Learn：[Memory Management in Unity](https://learn.unity.com/tutorial/memory-management-in-unity)
- GDC 2019：[Addressables: A New Way to Manage Assets](https://www.youtube.com/watch?v=YQdEq5QJZR0)
- IL2CPP 深入：[IL2CPP Internals: Memory](https://docs.unity3d.com/Manual/IL2CPP-Internals-Memory.html)

---

## 常见陷阱

1. **`Resources.UnloadUnusedAssets()` 的误用**：这个 API 会遍历所有加载的资产并释放无引用的部分。如果频繁调用（如在 Update 中），会导致严重的帧卡顿（5~50ms）。应该在关卡切换、加载界面等时机调用，而不是每帧。

2. **Addressables 的隐式加载缓存**：`LoadAssetAsync` 在相同的 key 上重复调用不会重新加载（优化行为）。但如果你持有 `AsyncOperationHandle` 而不释放，资产永远无法被卸载——Addressables 内部有引用计数器。

3. **`renderer.material` 而非 `renderer.sharedMaterial`**：访问 `renderer.material` 会创建一个材质的实例副本（运行时实例化），导致内存泄漏。除非确实需要修改单个实例的材质属性，否则始终使用 `sharedMaterial`。

4. **忽略 GPU 内存**：很多人盯着 Memory Profiler 的 Managed Heap，但 GPU 内存才是大户。一张 2048×2048 RGBA32 未压缩纹理 = 16MB VRAM，10 张就是 160MB——而你看到 C# 侧只有 10 个 ~80 字节的 Texture2D 包装对象。

5. **AsyncOperationHandle 未释放**：每个 `LoadAssetAsync` 返回的 handle 都需要释放（直接或通过 `Addressables.Release`）。如果只加载不释放，内存会持续增长。

6. **AssetBundle 冗余依赖**：如果 Prefab A 和 Prefab B 都引用了 Texture T，而它们被放在不同的 AssetBundle 中，T 会被重复打包到两个 Bundle 中。使用 Addressables Analyze 工具检测重复依赖。

7. **Allocator.Temp 用于跨帧数据**：`Allocator.Temp` 分配的内存在帧结束时被释放。如果需要跨越帧边界（如等到 Job 完成），使用 `Allocator.TempJob`，并确保在 4 帧内释放。
