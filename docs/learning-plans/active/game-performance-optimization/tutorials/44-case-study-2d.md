---
title: "案例研究：2D 手游性能调优全流程"
updated: 2026-06-05
---

# 案例研究：2D 手游性能调优全流程

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 90min
> 前置知识: 40-42（2D Sprite/图集/Tilemap/UI）+ 01-04（Profiling 基础）

---

## 1. 概念讲解

### 为什么需要这个？

2D 游戏看起来"简单"——没有复杂的 3D 几何、没有 PBR 材质、没有 Nanite。但正因如此，开发者常常忽略性能问题，直到手机发烫、帧率掉到 15fps、用户卸载。

本节模拟一个真实的 2D 手游案例：弹幕射击游戏（类似 Vampire Survivors），展示从卡顿到流畅的完整优化路径。

### 核心思想

2D 游戏优化的独特挑战：
1. **大量 Sprite 对象**（子弹、敌人、特效）→ Batches 爆炸
2. **UI 覆盖**（血条、分数、技能图标）→ Canvas 重建
3. **移动端约束**（<2W 功耗、GC 敏感、带宽窄）→ 比 PC 更苛刻
4. **对象频繁创建/销毁** → GC spikes

---

## 2. 案例设定：弹幕生存游戏

### 场景描述

- **屏幕同时可见**：~200 敌人 + ~500 子弹 + ~50 粒子特效
- **UI**：HP 条 × 200（每个敌人头顶）+ 玩家 HP/技能栏/分数/金币
- **Tilemap**：100×100 tile 的地图（无限卷轴）
- **目标平台**：Android 中端机（骁龙 730G / 1080p）
- **引擎**：Unity 2022 LTS (URP)
- **初始帧率**：~18-22fps（不稳定，战斗中掉到 12fps）

---

## 3. 诊断阶段：别猜，用 Profiler

### Unity Profiler 截图（模拟数据）

```
CPU Usage (Main Thread): 48.2ms
├── Scripts: 32.1ms  ← 🔴
│   ├── EnemyAI.Update(): 8.3ms
│   ├── BulletManager.Update(): 7.1ms
│   ├── DamageSystem.Update(): 5.2ms
│   └── Others: 11.5ms
├── Rendering: 9.4ms   ← 🔴
│   ├── SpriteRender.Render: 6.2ms  (4,200 batches!)
│   └── Canvas.Render: 2.1ms
├── Physics2D: 3.8ms   ← 🔴
└── GC.Collect: 2.9ms  ← 🔴 (每 3 秒触发一次)

GPU Usage: 8.1ms (passable)
Memory: Managed Heap 180MB → 频繁 GC
```

**诊断结论**：
- CPU 严重超标（48ms vs 16.6ms 目标）
- 主要瓶颈：脚本逻辑（32ms）+ 渲染批次（4,200 batches）+ GC spikes
- GPU 暂时 OK，但解决 CPU 问题后批次减少也会帮到 GPU

---

## 4. 优化迭代

### 迭代 1：消灭 GameObject.Instantiate/Destroy（-15ms GC + 逻辑优化）

**问题定位**：子弹和敌人用 `Instantiate` + `Destroy` 管理：

```csharp
// 原始代码 —— 每帧都在分配内存
void EnemyAI::Update()
{
    // ❌ 每 2 秒 Instantiate 一只新敌人
    if (Time.time - lastSpawn > 2.0f) {
        Instantiate(enemyPrefab, spawnPoint, Quaternion.identity);
        lastSpawn = Time.time;
    }
}

void BulletManager::Update()
{
    // ❌ 射击：每颗子弹 = 一次 Instantiate
    if (Input.GetButton("Fire1")) {
        var bullet = Instantiate(bulletPrefab, muzzle.position, muzzle.rotation);
        bullet.GetComponent<Rigidbody2D>().velocity = direction * speed;
    }

    // ❌ 每帧遍历所有子弹检查是否出界然后 Destroy
    foreach (var bullet in activeBullets) {
        if (IsOutOfBounds(bullet.transform.position)) {
            Destroy(bullet.gameObject);  // ← 触发 GC 分配
        }
    }
}
```

**修复 — 对象池 + 值类型化**：

```csharp
// C# 通用对象池（支持 GameObject 和普通对象）
public class ObjectPool<T> where T : Component
{
    private Queue<T> pool = new Queue<T>();
    private T prefab;

    public ObjectPool(T prefab, int initialSize)
    {
        this.prefab = prefab;
        for (int i = 0; i < initialSize; i++) {
            var obj = GameObject.Instantiate(prefab);
            obj.gameObject.SetActive(false);
            pool.Enqueue(obj);
        }
    }

    public T Acquire(Vector3 position, Quaternion rotation)
    {
        T obj;
        if (pool.Count > 0) {
            obj = pool.Dequeue();
        } else {
            // 池子耗尽：扩容（可选：记录警告日志）
            obj = GameObject.Instantiate(prefab);
        }
        obj.transform.SetPositionAndRotation(position, rotation);
        obj.gameObject.SetActive(true);
        return obj;
    }

    public void Release(T obj)
    {
        obj.gameObject.SetActive(false);
        pool.Enqueue(obj);
    }
}

// 改造后的子弹管理器
public class BulletManager_Optimized : MonoBehaviour
{
    private ObjectPool<Bullet> bulletPool;

    // 代替 GameObject，用 struct 存储在 NativeArray 中
    // 子弹移动用 Job System 批量计算
    struct BulletData
    {
        public float2 position;
        public float2 velocity;
        public float lifetime;
        public bool active;
        public int spriteIndex;  // 对应的 Sprite 实例 ID
    }

    private NativeArray<BulletData> bullets;  // 值类型，无 GC！
    private int bulletCapacity = 2000;

    void Awake()
    {
        bullets = new NativeArray<BulletData>(
            bulletCapacity, Allocator.Persistent);
    }

    void OnDestroy()
    {
        bullets.Dispose();
    }

    public void Fire(Vector2 origin, Vector2 direction, float speed)
    {
        // 找空闲槽位（不用分配）
        for (int i = 0; i < bullets.Length; i++) {
            if (!bullets[i].active) {
                bullets[i] = new BulletData {
                    position = origin,
                    velocity = direction * speed,
                    lifetime = 3.0f,
                    active = true
                };
                break;
            }
        }
    }
}
```

**效果**：
- `Instantiate/Destroy` 调用：~200/s → 0
- GC.Alloc per frame：~450KB → ~2KB
- GC.Collect 间隔：3s → 从未触发（增量 GC 够用）
- Scripts 耗时：32.1ms → 22.3ms（节省 9.8ms）

---

### 迭代 2：Sprite 合批攻击（4,200 → 180 Batches）

**问题定位**：Frame Debugger 分析：

```
Batch Breakdown:
├── Enemy Sprite (200):        200 batches  (同材质不同精灵)
├── Bullet Sprite (500):       500 batches  (透明混合）
├── Particle Sprite (50):      50 batches
├── Tilemap Chunks (25):       25 batches
├── HP Bar Sprites (200):      200 batches  (每个敌人独立 HP 条)
└── Other:                     ...
```

**根因**：
1. HP 条 Sprite 打断了敌人 Sprite 的合批（不同材质/Texture）
2. 子弹使用默认 Sprite-Default 材质，透明混合阻止动态合批
3. 精灵图集（Sprite Atlas）已使用，但不同图集之间仍然打断批次

**修复 1 — HP 条从 Sprite 改为 Shader 驱动的进度条**：

```hlsl
// 敌人 Shader：内置 HP 条，消除额外的 Sprite
// 不需要 DisplayHPBar() GameObject

Shader "Custom/EnemyWithHP"
{
    Properties
    {
        _MainTex ("Sprite", 2D) = "white" {}
        _HPFill ("HP Fill", Range(0, 1)) = 1.0
        _HPColor ("HP Bar Color", Color) = (0, 1, 0, 1)
        _HPBackground ("HP BG Color", Color) = (0.3, 0, 0, 1)
    }

    SubShader
    {
        Pass
        {
            // ... vertex shader ...

            float4 frag(v2f i) : SV_Target
            {
                float4 texColor = tex2D(_MainTex, i.uv);

                // HP 条绘制在贴图上方 4 像素宽区域（UV 空间）
                float hpBarHeight = 4.0 / _MainTex_TexelSize.w; // 4px
                float hpBarUV = (i.uv.y - (1.0 - hpBarHeight)) / hpBarHeight;

                if (i.uv.y > 1.0 - hpBarHeight && i.uv.y <= 1.0) {
                    // HP 条区域
                    if (i.uv.x <= _HPFill) {
                        return _HPColor;
                    } else {
                        return _HPBackground;
                    }
                }

                return texColor;
            }
        }
    }
}
```

```csharp
// C# 端：每帧只更新 MaterialPropertyBlock（不改 GameObject/Texture）
private MaterialPropertyBlock mpb;

void UpdateHPBar(SpriteRenderer renderer, float hpPercent)
{
    // 一次 MaterialPropertyBlock.SetFloat 比创建/销毁 GameObject 快 100×
    renderer.GetPropertyBlock(mpb);
    mpb.SetFloat("_HPFill", hpPercent);
    renderer.SetPropertyBlock(mpb);
}
```

**效果 — HP 条消除**：
- HP Bar Batches: 200 → 0
- 总 Batches: 4,200 → 4,000

**修复 2 — 子弹 Sprite 改用 Sprite Atlas + 同一材质**：

```
将所有子弹精灵打包到一个 Sprite Atlas（2048×2048）
→ 同材质、同图集 → Sprite Atlas 合批自动生效

子弹 Batches: 500 → 8  (按 Sorting Layer 分组)
```

**修复 3 — 粒子特效合并到全局粒子管理器**：

```csharp
// 使用 Unity ParticleSystem + GPU Instancing（URP 支持）
// 所有相同材质的粒子系统自动合并批次
```

**最终 Batches 效果**：

```
Batches (After):
├── Enemy Sprite (atlas):       3 batches
├── Bullet Sprite (atlas):      8 batches
├── Particle System (instanced): 12 batches
├── Tilemap (chunked):          25 batches
├── UI Canvas (single):         2 batches
└── Other:                      ...
Total: ~180 batches (从 4,200 减少了 96%)
```

Rendering 耗时：9.4ms → 2.1ms

---

### 迭代 3：Tilemap 裁剪 + Chunk 管理（-3ms）

**问题**：100×100 tile 地图全量渲染，即使 90% 不在屏幕内。

```csharp
// Unity Tilemap 的 Chunk 模式已内置视锥体裁剪
// 但需要正确配置：

// 1. 确保 Tilemap 使用 Chunk 模式（默认）
//    检查：Tilemap component → Mode: Chunk

// 2. 调整 Chunk Size 平衡内存和裁剪粒度
//    tilemap.CompressBounds() 在运行时缩小边界

// 3. 对于超大世界，用 Tilemap + 主动加载/卸载 Chunk
public class TilemapStreamer : MonoBehaviour
{
    public Grid worldGrid;
    public int chunkRadius = 3;   // 加载相机周围 3 个 chunk

    private Dictionary<Vector2Int, GameObject> loadedChunks;
    private Vector2Int lastCameraChunk;

    void Update()
    {
        Vector2Int camChunk = WorldToChunk(Camera.main.transform.position);

        if (camChunk == lastCameraChunk) return;

        // 卸载远距离 chunk
        var toUnload = loadedChunks.Keys
            .Where(c => ChebyshevDist(c, camChunk) > chunkRadius)
            .ToList();

        foreach (var chunk in toUnload) {
            chunkPool.Release(loadedChunks[chunk]);
            loadedChunks.Remove(chunk);
        }

        // 加载新进入范围的 chunk
        for (int x = -chunkRadius; x <= chunkRadius; x++)
        for (int y = -chunkRadius; y <= chunkRadius; y++) {
            var pos = new Vector2Int(camChunk.x + x, camChunk.y + y);
            if (!loadedChunks.ContainsKey(pos)) {
                loadedChunks[pos] = LoadChunk(pos);
            }
        }

        lastCameraChunk = camChunk;
    }

    GameObject LoadChunk(Vector2Int chunkPos)
    {
        var chunk = chunkPool.Acquire();
        // 从数据生成 tilemap...
        return chunk;
    }
}
```

**效果**：Rendering 额外节省 ~2ms（只渲染可见 chunk）

---

### 迭代 4：UI Canvas 拆分（-1.5ms Canvas 重建）

**问题**：
```
Canvas.Render: 2.1ms
├── Canvas.BuildBatch: 1.7ms  ← 🔴 每次 HP/分数变化触发全部重建
└── Canvas.SendWillRenderCanvases: 0.4ms
```

**根因**：所有 UI 元素（HP 条、分数、技能图标、敌人 HP 条）都在一个 Canvas 下 → 任何元素变化触发全 Canvas 重建。

**修复 — Canvas 分层**：

```csharp
// 方案：把 UI 按更新频率拆到不同 Canvas

// Canvas 1 (Static Canvas)  —— 从不变化的 UI
//  ├── Background Panel
//  ├── Skill Icon Frames
//  └── Game Title
// 特点：标记为 Static，不参与每帧重建

// Canvas 2 (Slow Canvas)  —— 低频更新（每秒 1-2 次）
//  ├── HP Bar (玩家)
//  ├── Score Text
//  ├── Coin Counter
// 特点：元素少、更新频率低，重建开销小

// Canvas 3 (Enemy HP Canvas)  —— 高频更新 → 改为 Shader 方案！
//  已移除（见迭代 2），0 个 UI 元素

// 设置方式：
// 为每个 Canvas 创建独立的 Canvas 组件
// 将对应的 UI GameObject 拖到对应的 Canvas 下

// 额外优化：Score Text 使用 TextMeshPro + 非重建更新
public class ScoreDisplay : MonoBehaviour
{
    private TMP_Text scoreText;
    private int lastDisplayedScore = -1;

    void Update()
    {
        int score = GameManager.Instance.score;
        if (score != lastDisplayedScore) {
            // SetText 只在值变化时调用，避免每帧触发重建
            scoreText.SetText("{0:N0}", score);
            lastDisplayedScore = score;
        }
    }
}
```

**效果**：
- `Canvas.BuildBatch`：1.7ms → 0.3ms（节省 1.4ms）
- 总 Canvas 渲染：2.1ms → 0.7ms

---

### 迭代 5：Physics2D 优化（-2.5ms）

**问题定位**：
```
Physics2D.Simulate: 3.8ms
├── Broadphase: 0.8ms
├── Narrowphase (700 bodies × 500 bullets): 2.6ms  ← 🔴
└── Solver: 0.4ms
```

**修复 — 分层碰撞 + 简化碰撞体**：

```csharp
// 碰撞矩阵优化
// Edit → Project Settings → Physics2D → Layer Collision Matrix
// 
// 禁用不需要的碰撞检测：
// - Bullet vs Bullet:    ❌ (子弹之间不需要碰撞)
// - Enemy vs Enemy:      ❌ (敌人在同一层)
// - Bullet vs Enemy:     ✅
// - Player vs Enemy:     ✅
// - Player vs Bullet:    ✅
// - Enemy vs Wall:       ✅

// 碰撞体形状简化：
// 圆形碰撞体 (CircleCollider2D) 比多边形快 ~3×
// 对于弹幕游戏，圆形碰撞体精度足够

// 接触点数量限制
// Project Settings → Physics2D → Default Contact Offset: 0.01 (降低)
```

```csharp
// 敌人碰撞体设置
[RequireComponent(typeof(CircleCollider2D))]
public class Enemy : MonoBehaviour
{
    void Awake()
    {
        var col = GetComponent<CircleCollider2D>();
        col.radius = 0.3f;  // 比多边形快，精度够用
        col.isTrigger = true; // 如果需要触发器而非物理响应
    }
}

// 如果不需要真实物理反应（只是检测碰撞）
// 使用 OverlapCircle 手动检测 + 空间哈希加速
```

**C# 手动空间哈希替代物理引擎（极致优化）**：

```csharp
public class SpatialHash
{
    private float cellSize;
    private Dictionary<long, List<int>> cells;

    public void Insert(int entityId, Vector2 position)
    {
        long key = HashCell(position);
        if (!cells.TryGetValue(key, out var list)) {
            list = new List<int>();
            cells[key] = list;
        }
        list.Add(entityId);
    }

    public void QueryCircle(Vector2 center, float radius, List<int> results)
    {
        results.Clear();
        int cellRadius = Mathf.CeilToInt(radius / cellSize);

        for (int x = -cellRadius; x <= cellRadius; x++)
        for (int y = -cellRadius; y <= cellRadius; y++) {
            Vector2 cellCenter = center + new Vector2(x, y) * cellSize;
            long key = HashCell(cellCenter);
            if (cells.TryGetValue(key, out var list)) {
                foreach (int entityId in list) {
                    if (Vector2.Distance(GetPosition(entityId), center) <= radius)
                        results.Add(entityId);
                }
            }
        }
    }
}
```

**效果**：
- Physics2D 耗时：3.8ms → 1.3ms（节省 2.5ms）

---

## 5. 最终结果

```
优化前 (18-22fps):
├── Scripts: 32.1ms
├── Rendering: 9.4ms (4,200 batches)
├── Physics2D: 3.8ms
├── GC.Collect: 2.9ms (spikes)
└── Total: ~48ms

优化后 (稳定 60fps):
├── Scripts: 12.5ms  (对象池 + 值类型化 -19.6ms)
├── Rendering: 2.1ms   (Sprite Atlas + HP Shader 化 + Canvas 拆分 -7.3ms)
├── Physics2D: 1.3ms   (碰撞分层 + 空间哈希 -2.5ms)
├── GC.Collect: 0ms    (零分配热路径)
└── Total: ~15.9ms  ✅

Managed Heap: 180MB → 45MB
```

---

## 6. 练习

### 练习 1: 重现并测量

1. 在 Unity 中创建一个场景：200 个 Sprite 敌人 + 帧循环生成 500 个子弹
2. 所有对象用 `Instantiate`/`Destroy` 管理
3. 用 Unity Profiler 记录：Batches 数量、GC.Alloc、Main Thread 耗时
4. 标注出前 3 大瓶颈

### 练习 2: 实施优化

1. 将敌人和子弹改为对象池管理
2. 将子弹 Sprite 打包到同一 Sprite Atlas
3. 为敌人实现 Shader 驱动的 HP 条（替代独立 Sprite）
4. 重新测量，与练习 1 的数据做对比

### 练习 3: 移动端真机测试（可选）

1. 将场景部署到 Android/iOS 真机
2. 使用 Unity Profiler (Device 模式) 或 Android GPU Inspector 分析
3. 找出 PC 上看不到、移动端才暴漏的瓶颈（通常是带宽/填充率）
4. 记录你的发现和修复方案

---

## 7. 扩展阅读

- [Unity — Optimizing Unity UI](https://learn.unity.com/tutorial/optimizing-unity-ui)
- [Unity — Introduction to Object Pooling](https://learn.unity.com/tutorial/introduction-to-object-pooling)
- [Unity — Sprite Atlas Documentation](https://docs.unity3d.com/Manual/class-SpriteAtlas.html)
- [Unity — Physics 2D Best Practices](https://docs.unity3d.com/Manual/class-Physics2DManager.html)
- [Android GPU Inspector](https://gpuinspector.dev/)

---

## 常见陷阱

- **Canvas 放太多东西**：把静态 UI、动态 UI、超高频更新 UI 混在一个 Canvas → 任何一个变化都触发全部重建。规则：一 Canvas 一更新频率
- **用 Sprite 当 UI 元素**：HP 条、进度条用独立 Sprite 对象 → 不仅增加 Batch，还无法利用 Canvas 的合批能力。用 Shader/MaterialPropertyBlock 省 10× 开销
- **为每个敌人创建 Collider**：200 个敌人 + 500 个子弹 = 35 万对碰撞检测。只在必要时用 Physics2D，弹幕类碰撞更适合空间哈希手算
- **忽略移动端 Draw Call 限制**：PC 上 4,000 batches 勉强跑，移动端 4,000 batches = 8fps。目标：移动端 <300 batches
- **GC 在移动端更致命**：Mono IL2CPP GC 比 PC .NET GC 慢得多。热路径做到零分配是移动端的硬性要求
