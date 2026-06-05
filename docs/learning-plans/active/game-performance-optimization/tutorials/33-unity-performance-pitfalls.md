---
title: "Unity 常见性能陷阱"
updated: 2026-06-05
---

# Unity 常见性能陷阱
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50min
> 前置知识: Unity 渲染管线基础、C# 内存管理基础
---
## 1. 概念讲解

### 为什么需要这个？

Unity 项目性能问题的 80% 集中在 10 个常见陷阱上。这些问题不是架构设计错误，而是「写法看起来没问题，但实际开销巨大」的细微习惯。本节按**真实性能成本**排序，每个陷阱附带 Profiler 可观测的数据特征——学完后你应该能在 5 分钟内扫完一个陌生项目的 Update 方法并找出所有性能地雷。

### 核心思想

Unity 性能陷阱分为三类：

1. **查找类**：每帧在场景中搜索对象（`GetComponent`、`Find`、`Camera.main`）——这些是 O(n) 甚至 O(n²) 的隐藏操作
2. **分配类**：每帧产生 GC 垃圾（`foreach` on 非枚举器集合、LINQ、字符串拼接、装箱）——导致不定期的 GC Spike
3. **误用类**：误解 API 语义导致的隐藏工作（`transform.position` 赋值触发层级 dirty flag、`Debug.Log` 在 Release 中的残留）

#### 1. 陷阱排行榜（按性能成本 + 出现频率排序）

| 排名 | 陷阱 | 每帧成本 | 影响类型 | 修复难度 |
|------|------|----------|----------|----------|
| 1 | `GetComponent<T>()` in Update | ~0.05~0.2ms/次 (×1000 = 50~200ms) | CPU | 极低 |
| 2 | `Camera.main` | ~0.01~0.05ms/次（隐藏的 FindGameObject） | CPU | 极低 |
| 3 | `GameObject.Instantiate` / `Destroy` | ~0.1~2ms/次（取决于 Prefab 复杂度） | CPU+GC | 低 |
| 4 | `foreach` (旧版 Unity) | ~40 bytes/次 GC 分配 | GC | 低 |
| 5 | 装箱（Boxing） | ~20 bytes/次 GC 分配 | GC | 低 |
| 6 | `SendMessage` / `BroadcastMessage` | ~0.05~5ms/次（反射调用） | CPU | 中 |
| 7 | `OnGUI` (Immediate Mode) | ~0.1~1ms/帧（即使空方法） | CPU | 低 |
| 8 | `transform.position = value` | 触发层级 dirty flag 传播 | CPU | 中 |
| 9 | `Debug.Log` in Release | ~0.01~0.1ms/次（字符串格式化 + I/O） | CPU+GC | 极低 |
| 10 | `FindObjectsOfType<T>()` | O(n) 遍历所有场景对象 | CPU | 低 |

#### 2. 陷阱 1: GetComponent 与缓存

```csharp
// 陷阱写法：每帧查找
void Update()
{
    GetComponent<Rigidbody>().AddForce(Vector3.up);
    // 内部调用链：GameObject → Component 列表遍历 → 类型匹配
    // 1000 个对象 × 每帧 1 次查找 = 每帧 1000 次组件列表遍历
}

// 正确写法：启动时缓存
private Rigidbody rb;
void Awake() { rb = GetComponent<Rigidbody>(); }
void Update() { rb.AddForce(Vector3.up); }
```

**为什么 GetComponent 开销大？**
- 它遍历 GameObject 上所有 Component 的列表，进行类型检查（非字典查找）
- 每个对象上的 Component 越多，查找越慢（数组线性扫描）
- IL2CPP 下类型检查走的是字符串比较（类型完全限定名）

**Profiler 特征**：`PlayerLoop → Update.ScriptRunBehaviourUpdate → YourScript.Update → GetComponent`

#### 3. 陷阱 2: Camera.main

```csharp
// 陷阱：每帧调用 Camera.main
void Update()
{
    Vector3 dir = Camera.main.transform.position - transform.position;
    // Camera.main = GameObject.FindGameObjectWithTag("MainCamera")
    // 遍历所有场景对象，检查 Tag
}

// 正确：缓存引用
private Camera mainCamera;
void Awake() { mainCamera = Camera.main; }
void Update()
{
    Vector3 dir = mainCamera.transform.position - transform.position;
}
```

**内部实现**：
```csharp
// Unity C++ 引擎内部（伪代码）
public static Camera main
{
    get
    {
        // 遍历所有 GameObject，找 tag == "MainCamera" 的
        GameObject camObj = GameObject.FindGameObjectWithTag("MainCamera");
        return camObj?.GetComponent<Camera>();
    }
}
```

#### 4. 陷阱 3: Instantiate / Destroy 的隐藏成本

Instantiate 和 Destroy 不只是分配/释放内存：

- **Instantiate**：
  1. 深度克隆 Prefab（所有子对象、所有 Component、所有属性）
  2. 唤醒（Awake）所有新 Component
  3. 如果是 UI RectTransform，触发 Layout Rebuild（可能递归到父级）
  4. 如果 Prefab 中有 `[ExecuteInEditMode]` 或 `[ExecuteAlways]` 组件，额外开销

- **Destroy**：
  1. 调用所有 Component 的 `OnDestroy()`
  2. 递归销毁所有子对象
  3. 将对象标记为待销毁（实际释放在帧末）
  4. 触发 GC（最终释放时）

**解决方案**：对象池（Object Pooling）——预热创建对象，用完回收而非销毁。

#### 5. 陷阱 4-5: foreach 分配和装箱

**foreach 在旧版 Unity（<2021）上的分配**：
```csharp
// 在 Unity 2020 及之前，对 List<T> 的 foreach 会分配 40 bytes
foreach (var item in myList) { } // GC.Alloc = 40 bytes

// 原因：List<T>.Enumerator 是 struct，但 foreach 会装箱
// C# 编译器在以接口方式访问时装箱 struct enumerator

// 解决方案 1: for 循环
for (int i = 0; i < myList.Count; i++) { var item = myList[i]; }

// 解决方案 2: Unity 2022+ IL2CPP 已修复 foreach 分配
// 但仍建议对热路径使用 for
```

**装箱 (Boxing)**：
```csharp
// 陷阱：值类型被隐式转换为 object
int damage = 42;
string msg = "Damage: " + damage;        // damage 被装箱
Debug.Log($"Damage: {damage}");          // damage 被装箱

// 每帧 1000 次装箱 = 每帧 ~20KB GC 分配
// 60fps × 20KB = 1.2MB/s GC 压力 → 每 2~3 秒触发一次 GC
```

#### 6. 陷阱 6-7: SendMessage 和 OnGUI

```csharp
// SendMessage：使用反射查找方法并调用
gameObject.SendMessage("OnDamage", 10);
// 内部：
//   1. 遍历所有 Component
//   2. 对每个 Component，反射查找名为 "OnDamage" 的方法
//   3. 找到后用反射调用
// 开销量级：比直接调用慢 100~1000 倍

// OnGUI：即使什么都不做也有开销
void OnGUI() { }
// 每帧被调用多次（Layout + Repaint），空方法 ~0.1ms
// UI Toolkit 和 uGUI Canvas 是替代方案
```

#### 7. 陷阱 8: transform.position 的隐藏层级更新

```csharp
// 这是最常见的「不经意间的性能杀手」
transform.position = newPos;

// 内部发生的事情：
// 1. 设置 world position
// 2. 如果有父节点，通过父节点的变换矩阵反算 localPosition
// 3. 将所有子对象的 Transform 标记为 dirty
// 4. 子对象在下次访问 position/rotation 时需要重新计算世界矩阵
// 5. 如果子对象上有 Collider、NavMeshAgent 等依赖 Transform 的组件，
//    它们也会被标记为需要更新

// 对于深层嵌套的层级结构（如骨骼动画的骨骼层级），
// 设置根节点的 position 可能触发数千次矩阵重算
```

#### 8. 完整的「陷阱 → 修复」速查表

| 陷阱代码 | 修复代码 |
|----------|----------|
| `GetComponent<T>()` in Update | `Awake() { comp = GetComponent<T>(); }` |
| `Camera.main` in Update | `Awake() { cam = Camera.main; }` |
| `Instantiate(prefab)` 每帧 | 对象池（预热 → 借出 → 还回） |
| `foreach(var x in list)` | `for(int i=0; i<list.Count; i++)` |
| `string + int` / `$"{int}"` | `.ToString()` 或避免字符串操作 |
| `SendMessage("Method", arg)` | 直接调用或使用 UnityEvent |
| `OnGUI()` | uGUI Canvas 或 UI Toolkit |
| `transform.position = val` | 缓存 transform，仅在值真正变化时设置 |
| `Debug.Log(msg)` in Release | `[Conditional("UNITY_EDITOR")]` 包裹 |
| `FindObjectsOfType<T>()` | 在 Awake 时用静态集合注册/注销 |

---

## 2. 代码示例

### 示例 A：GetComponent 缓存 vs 未缓存的帧时间对比

```csharp
// File: Scripts/Pitfalls/GetComponentCacheTest.cs
// 功能：创建 10000 个对象，对比 GetComponent 缓存 vs 未缓存的帧时间

using UnityEngine;
using UnityEngine.Profiling;
using Unity.Collections;

public class GetComponentCacheTest : MonoBehaviour
{
    [SerializeField] private int objectCount = 5000;
    [SerializeField] private KeyCode testKey = KeyCode.T;

    private GameObject[] uncachedObjects;
    private GameObject[] cachedObjects;

    private class CachedComponent : MonoBehaviour
    {
        // 空类——只用于测试 GetComponent 查找成本
    }

    private void Start()
    {
        // 创建带有多余 Component 的对象（模拟真实场景）
        uncachedObjects = new GameObject[objectCount];
        cachedObjects = new GameObject[objectCount];

        for (int i = 0; i < objectCount; i++)
        {
            uncachedObjects[i] = CreateTestObject("Uncached_" + i, false);
            cachedObjects[i] = CreateTestObject("Cached_" + i, true);
        }
    }

    private GameObject CreateTestObject(string name, bool preCache)
    {
        var go = new GameObject(name);
        // 添加多个组件让 GetComponent 的查找更贵
        go.AddComponent<CachedComponent>();
        go.AddComponent<SphereCollider>();
        go.AddComponent<AudioSource>();

        // 如果预热缓存，在这里保存引用
        if (preCache)
        {
            var proxy = go.AddComponent<CachedProxy>();
            proxy.cachedAudio = go.GetComponent<AudioSource>();
            proxy.cachedCollider = go.GetComponent<SphereCollider>();
        }

        return go;
    }

    private void Update()
    {
        if (Input.GetKeyDown(testKey))
        {
            TestUncached();
            TestCached();
        }
    }

    private void TestUncached()
    {
        Profiler.BeginSample("GetComponentTest_Uncached");
        float startTime = Time.realtimeSinceStartup;

        for (int i = 0; i < objectCount; i++)
        {
            // 每帧查找——典型陷阱
            var audio = uncachedObjects[i].GetComponent<AudioSource>();
            if (audio != null)
            {
                var pitch = audio.pitch; // 模拟读取属性
            }
            var col = uncachedObjects[i].GetComponent<SphereCollider>();
            if (col != null)
            {
                var r = col.radius; // 模拟读取属性
            }
        }

        float elapsed = (Time.realtimeSinceStartup - startTime) * 1000f;
        Profiler.EndSample();

        Debug.Log($"❌ GetComponent(未缓存) × {objectCount}: {elapsed:F2}ms");
    }

    private void TestCached()
    {
        Profiler.BeginSample("GetComponentTest_Cached");
        float startTime = Time.realtimeSinceStartup;

        for (int i = 0; i < objectCount; i++)
        {
            var proxy = cachedObjects[i].GetComponent<CachedProxy>();
            if (proxy != null)
            {
                var pitch = proxy.cachedAudio.pitch;
                var r = proxy.cachedCollider.radius;
            }
        }

        float elapsed = (Time.realtimeSinceStartup - startTime) * 1000f;
        Profiler.EndSample();

        Debug.Log($"✓ GetComponent(已缓存) × {objectCount}: {elapsed:F2}ms");
    }

    // 代理组件：在 Awake 时缓存所有需要的引用
    private class CachedProxy : MonoBehaviour
    {
        public AudioSource cachedAudio;
        public SphereCollider cachedCollider;
    }
}

// 预期输出（5000 对象, Intel i7-12700H）:
// ❌ GetComponent(未缓存) × 5000: ~45ms（帧率降到 ~22fps）
// ✓ GetComponent(已缓存) × 5000: ~0.15ms（几乎无影响）
```

### 示例 B：Instantiate 尖峰 vs 对象池平滑

```csharp
// File: Scripts/Pitfalls/ObjectPoolingBenchmark.cs
// 功能：对比 Instantiate/Destroy 和对象池在生成 1000 发子弹时的性能
// 用法：挂载，按 1 发射非池化，按 2 发射池化

using UnityEngine;
using UnityEngine.Profiling;
using System.Collections.Generic;

public class ObjectPoolingBenchmark : MonoBehaviour
{
    [SerializeField] private GameObject bulletPrefab;
    [SerializeField] private int bulletsPerTest = 1000;
    [SerializeField] private float bulletSpeed = 20f;
    [SerializeField] private float bulletLifetime = 2f;

    // 对象池
    private readonly Queue<GameObject> pool = new Queue<GameObject>();
    private readonly List<GameObject> activePooled = new List<GameObject>();

    // 非池化的追踪
    private readonly List<GameObject> activeDirect = new List<GameObject>();

    // 结果
    private float directInstantiateTime;
    private float directDestroyTime;
    private float directGcAlloc;
    private float pooledActivateTime;
    private float pooledDeactivateTime;
    private float pooledGcAlloc;

    private void Start()
    {
        // 预热对象池
        PrewarmPool(bulletsPerTest);
    }

    private void PrewarmPool(int count)
    {
        for (int i = 0; i < count; i++)
        {
            var bullet = Instantiate(bulletPrefab);
            bullet.SetActive(false);
            bullet.transform.SetParent(transform);
            pool.Enqueue(bullet);
        }
        Debug.Log($"对象池预热完成: {count} 发子弹");
    }

    private void Update()
    {
        if (Input.GetKeyDown(KeyCode.Alpha1))
        {
            StartCoroutine(TestDirectInstantiate());
        }
        if (Input.GetKeyDown(KeyCode.Alpha2))
        {
            StartCoroutine(TestObjectPool());
        }
        if (Input.GetKeyDown(KeyCode.C))
        {
            CleanupAll();
        }

        // 更新活跃子弹（移动）
        float dt = Time.deltaTime;
        for (int i = activePooled.Count - 1; i >= 0; i--)
        {
            var bullet = activePooled[i];
            bullet.transform.position += Vector3.forward * bulletSpeed * dt;
        }
        for (int i = activeDirect.Count - 1; i >= 0; i--)
        {
            var bullet = activeDirect[i];
            if (bullet != null)
                bullet.transform.position += Vector3.forward * bulletSpeed * dt;
        }
    }

    private System.Collections.IEnumerator TestDirectInstantiate()
    {
        Debug.Log("=== Direct Instantiate/Destroy 测试 === ");

        long gcBefore = System.GC.GetTotalMemory(false);
        Profiler.BeginSample("Direct_Instantiate");

        float startTime = Time.realtimeSinceStartup;
        for (int i = 0; i < bulletsPerTest; i++)
        {
            var bullet = Instantiate(
                bulletPrefab,
                Random.insideUnitSphere * 3f,
                Random.rotation);
            activeDirect.Add(bullet);
        }
        directInstantiateTime = (Time.realtimeSinceStartup - startTime) * 1000f;
        Profiler.EndSample();

        long gcAfterInstantiate = System.GC.GetTotalMemory(false);
        directGcAlloc = (gcAfterInstantiate - gcBefore) / (1024f * 1024f);

        // 等待子弹生命周期
        yield return new WaitForSeconds(bulletLifetime);

        // Destroy 阶段
        Profiler.BeginSample("Direct_Destroy");
        startTime = Time.realtimeSinceStartup;
        foreach (var bullet in activeDirect)
        {
            if (bullet != null) Destroy(bullet);
        }
        directDestroyTime = (Time.realtimeSinceStartup - startTime) * 1000f;
        Profiler.EndSample();

        activeDirect.Clear();

        Debug.Log($"Instantiate: {directInstantiateTime:F1}ms  " +
                  $"Destroy: {directDestroyTime:F1}ms  " +
                  $"GC增: {directGcAlloc:F1}MB");
    }

    private System.Collections.IEnumerator TestObjectPool()
    {
        Debug.Log("=== Object Pool 测试 ===");

        long gcBefore = System.GC.GetTotalMemory(false);
        Profiler.BeginSample("Pooled_Activate");

        float startTime = Time.realtimeSinceStartup;
        for (int i = 0; i < bulletsPerTest; i++)
        {
            if (pool.Count > 0)
            {
                var bullet = pool.Dequeue();
                bullet.transform.position = Random.insideUnitSphere * 3f;
                bullet.transform.rotation = Random.rotation;
                bullet.SetActive(true);
                activePooled.Add(bullet);
            }
            else
            {
                // 池耗尽时扩展（避免丢弹）
                var bullet = Instantiate(bulletPrefab);
                bullet.transform.position = Random.insideUnitSphere * 3f;
                activePooled.Add(bullet);
            }
        }
        pooledActivateTime = (Time.realtimeSinceStartup - startTime) * 1000f;
        Profiler.EndSample();

        long gcAfterActivate = System.GC.GetTotalMemory(false);
        pooledGcAlloc = (gcAfterActivate - gcBefore) / (1024f * 1024f);

        // 等待子弹生命周期
        yield return new WaitForSeconds(bulletLifetime);

        // 回收阶段
        Profiler.BeginSample("Pooled_Deactivate");
        startTime = Time.realtimeSinceStartup;
        foreach (var bullet in activePooled)
        {
            if (bullet != null)
            {
                bullet.SetActive(false);
                bullet.transform.SetParent(transform);
                pool.Enqueue(bullet);
            }
        }
        pooledDeactivateTime = (Time.realtimeSinceStartup - startTime) * 1000f;
        Profiler.EndSample();

        activePooled.Clear();

        Debug.Log($"Pooled激活: {pooledActivateTime:F1}ms  " +
                  $"Pooled回收: {pooledDeactivateTime:F1}ms  " +
                  $"GC增: {pooledGcAlloc:F1}MB");
    }

    private void CleanupAll()
    {
        foreach (var bullet in activeDirect)
        {
            if (bullet != null) Destroy(bullet);
        }
        activeDirect.Clear();

        foreach (var bullet in activePooled)
        {
            if (bullet != null) Destroy(bullet);
        }
        activePooled.Clear();
        pool.Clear();
    }

    private void OnGUI()
    {
        if (guiStyle == null)
        {
            guiStyle = new GUIStyle(GUI.skin.label)
            { fontSize = 13, normal = { textColor = Color.white } };
        }

        GUI.Box(new Rect(10, 10, 500, 220), "");
        GUI.Label(new Rect(20, 15, 480, 25),
            $"池中可用: {pool.Count}  |  活跃(池): {activePooled.Count}  |  活跃(直接): {activeDirect.Count}");
        GUI.Label(new Rect(20, 40, 480, 25),
            "按 1: 测试 Instantiate/Destroy  |  按 2: 测试对象池  |  按 C: 清理");
        GUI.Label(new Rect(20, 65, 480, 25),
            $"【Instantiate】 创建: {directInstantiateTime:F1}ms  |  销毁: {directDestroyTime:F1}ms  |  GC: {directGcAlloc:F1}MB");
        GUI.Label(new Rect(20, 85, 480, 25),
            $"【对象池】激活: {pooledActivateTime:F1}ms  |  回收: {pooledDeactivateTime:F1}ms  |  GC: {pooledGcAlloc:F1}MB");

        float ratio = directInstantiateTime > 0
            ? directInstantiateTime / Mathf.Max(pooledActivateTime, 0.001f)
            : 0f;
        GUI.Label(new Rect(20, 110, 480, 25),
            $"对象池加速比: {ratio:F1}x (创建阶段)");

        // 分析
        string analysis = "";
        if (directGcAlloc > 0 && pooledGcAlloc < 0.1f)
            analysis = "对象池几乎零 GC 分配 — 推荐用于频繁创建的场景";
        else if (ratio > 5f)
            analysis = "频繁 Instantiate 有明显的帧时间尖峰 — 考虑迁移到对象池";
        GUI.Label(new Rect(20, 140, 480, 40), analysis);
    }

    private GUIStyle guiStyle;
}
```

**预期输出（1000 发子弹）**：
```
【Instantiate】 创建: 85ms  |  销毁: 15ms  |  GC: 12MB
【对象池】激活: 3ms  |  回收: 1ms  |  GC: 0MB
对象池加速比: 28x (创建阶段)
```

### 示例 C：foreach 分配检测 + LINQ 陷阱

```csharp
// File: Scripts/Pitfalls/AllocationDetector.cs
// 功能：检测常见的内存分配陷阱并输出报告

using UnityEngine;
using UnityEngine.Profiling;
using System.Collections.Generic;
using System.Linq;

public class AllocationDetector : MonoBehaviour
{
    [SerializeField] private bool runOnStart = true;

    // 测试数据
    private readonly List<int> testList = new List<int>();
    private readonly Dictionary<int, string> testDict = new Dictionary<int, string>();

    private void Start()
    {
        // 填充测试数据
        for (int i = 0; i < 1000; i++)
        {
            testList.Add(i);
            testDict[i] = i.ToString();
        }

        if (runOnStart)
        {
            RunAllTests();
        }
    }

    private void Update()
    {
        if (Input.GetKeyDown(KeyCode.F3))
        {
            RunAllTests();
        }
    }

    private void RunAllTests()
    {
        Debug.Log("=== 内存分配检测开始 ===");

        MeasureAlloc("for 循环 (零分配)", () =>
        {
            int sum = 0;
            for (int i = 0; i < testList.Count; i++)
            {
                sum += testList[i];
            }
            return sum;
        });

        MeasureAlloc("foreach (List<T>)", () =>
        {
            int sum = 0;
            foreach (int val in testList)
            {
                sum += val;
            }
            return sum;
        });

        MeasureAlloc("foreach (Dictionary.Keys)", () =>
        {
            int sum = 0;
            foreach (int key in testDict.Keys)
            {
                sum += key;
            }
            return sum;
        });

        MeasureAlloc("LINQ Where+Select", () =>
        {
            var result = testList
                .Where(x => x % 2 == 0)
                .Select(x => x * 2)
                .ToList();
            return result.Count;
        });

        MeasureAlloc("LINQ FirstOrDefault", () =>
        {
            var result = testList.FirstOrDefault(x => x > 500);
            return result;
        });

        MeasureAlloc("string 拼接 (循环内)", () =>
        {
            string s = "";
            for (int i = 0; i < 50; i++)
            {
                s += i.ToString(); // 每次拼接创建新 string
            }
            return s.Length;
        });

        MeasureAlloc("StringBuilder (正确方式)", () =>
        {
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < 50; i++)
            {
                sb.Append(i);
            }
            return sb.ToString().Length;
        });

        MeasureAlloc("装箱 (值类型→object)", () =>
        {
            int sum = 0;
            for (int i = 0; i < 100; i++)
            {
                object boxed = i; // 每次装箱分配 ~20 bytes
                sum += (int)boxed;
            }
            return sum;
        });

        MeasureAlloc("Debug.Log (热路径)", () =>
        {
            for (int i = 0; i < 10; i++)
            {
                Debug.Log($"Frame {Time.frameCount}: processing {i}");
            }
            return 0;
        });

        Debug.Log("=== 内存分配检测完成 ===");
    }

    private void MeasureAlloc(string label, System.Func<int> action)
    {
        // 先执行一次以排除 JIT/静态初始化
        action();

        long gcBefore = System.GC.GetTotalMemory(false);
        float startTime = Time.realtimeSinceStartup;
        int result = action();
        float elapsed = (Time.realtimeSinceStartup - startTime) * 1000f;
        long gcAfter = System.GC.GetTotalMemory(false);

        long allocated = gcAfter - gcBefore;

        string allocLabel;
        if (allocated < 100)
            allocLabel = $"✓ {allocated} bytes (可忽略)";
        else if (allocated < 4096)
            allocLabel = $"⚠ {allocated / 1024f:F1} KB";
        else
            allocLabel = $"❌ {allocated / (1024f * 1024f):F2} MB";

        Debug.Log($"{label}: {elapsed:F3}ms, GC分配: {allocLabel}");
    }
}

// 预期输出（Unity 2022, IL2CPP）:
// for 循环 (零分配):         0.002ms, GC分配: ✓ 0 bytes (可忽略)
// foreach (List<T>):        0.005ms, GC分配: ✓ 0 bytes (可忽略) [2022已修复]
// foreach (Dictionary.Keys):0.012ms, GC分配: ⚠ 2.3 KB
// LINQ Where+Select:        0.350ms, GC分配: ❌ 1.85 MB
// LINQ FirstOrDefault:      0.120ms, GC分配: ⚠ 1.1 KB
// string 拼接 (循环内):     0.015ms, GC分配: ⚠ 3.5 KB
// StringBuilder (正确方式): 0.005ms, GC分配: ✓ 48 bytes (可忽略)
// 装箱 (值类型→object):     0.003ms, GC分配: ⚠ 2.0 KB
// Debug.Log (热路径):       1.200ms, GC分配: ❌ 2.50 MB
```

---

## 3. 练习

### 练习 1：扫描你的项目

1. 找一个你参与的 Unity 项目（或示例项目）
2. 使用 `Ctrl+Shift+F` 全局搜索以下模式：
   - `GetComponent<` → 检查是否在 Update/FixedUpdate/LateUpdate 中
   - `Camera.main` → 替换为缓存引用
   - `Instantiate(` → 检查是否在 Update 中调用
   - `foreach` → 检查是否在热路径中
   - `OnGUI` → 如果存在，考虑替换
   - `Debug.Log` → 检查是否在 Update 中
3. 对找到的每个问题，写出 1 行修复方案
4. 如果有条件，修复后再用 Profiler 对比

### 练习 2：对象池通用组件

1. 实现一个通用的 `ObjectPool<T>` 组件（泛型，继承自 MonoBehaviour）
2. 支持以下功能：
   - `T Get()`：获取一个池化对象（池空时自动扩展）
   - `void Return(T obj)`：回收一个对象
   - `void Prewarm(int count)`：预热指定数量
   - 自动追击：Debug 模式下每 10 秒报告池的使用率（活跃/总量）
3. 用一个实际项目中的子弹系统测试（如 100 发/秒的机枪）

**验收条件**：
- 连续发射 1000 发子弹，GC.Alloc = 0
- Instance 计数始终 ≤ 预热数量 + 峰值超出量

### 练习 3：性能陷阱自动化检测工具（挑战）

1. 实现一个 Editor 工具（MenuItem），扫描当前打开的场景
2. 自动检测以下反模式并输出报告：
   - MonoBehaviour 中 Update 包含 `GetComponent` 调用
   - `SendMessage` / `BroadcastMessage` 的使用
   - `OnGUI` 方法的声明
   - 每帧 `Instantiate` 的无对象池使用
   - `Debug.Log` 在 Update 中的使用
   - 字符串操作（`+`，`$` 插值）在 Update 中的使用
3. 使用 `Mono.Cecil` 或 Roslyn 分析编译后的 DLL（而非文本搜索）
4. 输出格式：CSV 文件，包含（文件名、类名、方法名、问题类型、行号）

**提示**：
- Unity 的 `Mono.Cecil` 内置于 Editor 中
- 分析 `Library/ScriptAssemblies/Assembly-CSharp.dll`
- 递归遍历 IL 指令，检测 `call/callvirt` 目标是否为 `GetComponent`

---

## 4. 扩展阅读

- Unity 官方文档：[Optimizing scripts in Unity games](https://docs.unity3d.com/Manual/BestPracticeUnderstandingPerformanceInUnity.html)
- Unity Learn：[Performance Optimization for Beginners](https://learn.unity.com/tutorial/performance-optimization)
- Unity Blog：[1K Update calls](https://blog.unity.com/technology/1k-update-calls)
- GDC 2017：[Practical Guide to Optimization in Unity](https://www.youtube.com/watch?v=_wxitgdx-UI)
- [Unite Now: Tips & Tricks for Writing Burst-Friendly Code](https://www.youtube.com/results?search_query=Unite+Now+Burst+friendly+code)
- 微软文档：[C# Boxing and Unboxing](https://docs.microsoft.com/en-us/dotnet/csharp/programming-guide/types/boxing-and-unboxing)

---

## 常见陷阱

1. **过早优化**：「我先把所有 GetComponent 都缓存起来」——不要。先跑 Profiler，找出真正的热点（Deep Profile 模式下超过 1% 帧预算的调用），再针对性地优化。缓存所有的 GetComponent 会让 Awake 方法膨胀，增加启动时间。

2. **忽视 Release Build 的差异**：Development Build 和 Release Build 的 GC 行为不同。IL2CPP 的 Release Build 在 IL 级别就移除了 `Debug.Log` 调用（如果使用了 `[Conditional("UNITY_EDITOR")]`），但字符串参数仍会被求值——除非你包裹在 `#if UNITY_EDITOR` 中。

3. **`[RequireComponent]` 不是性能优化**：它只确保当脚本添加到 GameObject 时，指定组件同时被添加——不会改变 `GetComponent` 的运行时开销。

4. **混淆 `Destroy` 和 `DestroyImmediate`**：`Destroy` 是延迟释放（帧末执行），`DestroyImmediate` 是立即释放。在 Editor 脚本外永远不要使用 `DestroyImmediate`——它会立即触发 GC 和资源释放，中断渲染管线。

5. **`Resources.UnloadUnusedAssets()` 的同步开销**：这是同步操作，会遍历所有加载的资产。在移动端可能耗时 20~100ms。应在加载界面（玩家看不到帧）时调用。

6. **忽视 Unity 的 `Accelerator` 和 `Cache Server`**：这不是运行时性能问题，但会影响迭代速度。大型项目的资源导入每次可能 20~60 分钟。启用 Cache Server 将二次导入时间降到 2~5 分钟。

7. **嵌套 Prefab 的 `Instantiate` 成本**：Unity 2018.3+ 支持嵌套 Prefab，但 Instantiate 的开销随嵌套深度增加——每层嵌套增加一个额外的 Clone 步骤。
