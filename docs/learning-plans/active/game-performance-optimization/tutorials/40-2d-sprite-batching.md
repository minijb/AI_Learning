---
title: "2D Sprite 合批与图集优化"
updated: 2026-06-05
---

# 2D Sprite 合批与图集优化

> 所属计划: 游戏性能优化全攻略
> 预计耗时: 45min
> 前置知识: Draw Call 优化基础（第 5 节）
>
> 核心要点: Sprite 合批是 2D 游戏最重要的渲染优化 — 将多个 Sprite 打包到同一张纹理（Atlas），让 GPU 在一次 Draw Call 中完成所有绘制。理解合批条件和破坏因素（材质切换、Z-Order、不同纹理），能让你从 1000+ Draw Calls 降到个位数。

---

## 1. 概念讲解

### 为什么需要这个？

想象你的 2D 游戏场景有 500 个 Sprite：树木、石头、角色、UI 元素。如果每个 Sprite 使用独立的纹理文件，GPU 需要：

1. 绑定纹理 A → 画树 → 解除绑定
2. 绑定纹理 B → 画石头 → 解除绑定
3. 绑定纹理 C → 画角色 → 解除绑定
4. ...重复 500 次

每一次"绑定纹理 → 发送顶点 → 绘制"就是一个 **Draw Call**。500 个 Draw Call 在移动端可能直接让帧率跌到 15fps，即使每个 Sprite 只有 4 个顶点。

**核心问题不是顶点多，而是状态切换多。** GPU 每次切换纹理（或材质、Shader）都需要等待管线排空、重新配置采样器，开销巨大。

**图集（Texture Atlas）** 就是把所有小 Sprite 拼到一张大纹理上。这样 500 个 Sprite 共享同一张纹理 → GPU 可以一次性画完 → 1 个 Draw Call。**这是 2D 渲染优化的第 0 号法则。**

### 核心思想

#### 1. 图集的工作原理

```
独立纹理方案（差）:
┌───┐ ┌───┐ ┌───┐     ┌───┐
│ A │ │ B │ │ C │ ... │ Z │  → 500 个 Draw Calls
└───┘ └───┘ └───┘     └───┘

图集方案（好）:
┌────────────────────────────┐
│ A │ B │ C │  ...  │  Z     │
│───┼───┼───┼───────┼─────── │
│   │   │   │       │        │
│   │   │   │       │        │
└────────────────────────────┘
→ 1 个 Draw Call（所有 Sprite 共享同一纹理）
```

关键：每个 Sprite 的 UV 坐标仍然正确映射到图集中的对应区域。Sprite 的视觉不变，但渲染效率天差地别。

#### 2. 合批条件（Unity SpriteRenderer）

Unity 自动尝试将使用**同一材质**的 SpriteRenderer 合批。合批成功的条件是：

| 条件 | 说明 |
|------|------|
| 相同材质 | Material 对象必须完全相同（不是"参数相同"） |
| 相同纹理 | 材质的 Main Texture 必须指向同一纹理（即同一个 Atlas） |
| 相同 Sorting Layer | 不同的 Sorting Layer 打断合批 |
| 相同 Order in Layer | 相邻的 Z-Order 才能合批；插入不同 Z 的 Sprite 会打断 |
| 相同 MaterialPropertyBlock | 如果使用了 PropertyBlock，必须相同 |
| 同一个 Renderer | 同一种 SpriteRenderer 类型（不是 SpriteShape 等） |

**Z-Order 的破坏性**是最容易被忽视的：

```
场景中的 Sprite（按 Sorting Order 排列）:
[树(0)] [树(1)] [石头(2)] [树(3)] [石头(4)] [树(5)]
         ↑        ↑                  ↑        ↑
      Batch 1   打断              Batch 2   打断

最终：3 个 Batches（而不是 1 个）
```

Z-Order 0,1 合批 → 同一纹理；Z-Order 2 插入（不同纹理）→ **打断**；Z-Order 3 合批 → 同一纹理；Z-Order 4 插入 → 打断；Z-Order 5 → 新 Batch。

**优化策略**：如果可以接受视觉调整，将同纹理的 Sprite 放在相邻 Z-Order。

#### 3. 图集生成方案

| 方案 | 工具 | 适用场景 |
|------|------|---------|
| Unity Sprite Atlas | Unity 内置 | Unity 项目，推荐 |
| UE Paper2D Sprite Sheet | UE 内置 | UE 项目 |
| TexturePacker | 第三方 | 跨引擎，强大的 packing 算法 |
| Shader 变体（Texture Array） | 自定义 | 大量相同尺寸的 Sprite |

**Unity Sprite Atlas 使用要点**：

- 创建：`Assets → Create → 2D → Sprite Atlas`
- 将 Sprite 拖入 `Objects for Packing` 列表
- 设置 Max Texture Size（建议 2048 或 4096，根据平台）
- **勾选 `Include in Build`** 确保打包进构建
- Late Binding：运行时动态绑定 Sprite 到 Atlas

**UE Paper2D 处理**：

- UE 的 Paper2D 使用 Sprite Sheet（Flipbook 式）
- 将多个 Sprite 排列在一张纹理上，通过 `PaperSprite` 资源指定 UV 区域
- Sprite Sheet 导入时设置 Grid 尺寸自动切割
- 同一 Sprite Sheet 的 Sprite 天然共享一张纹理

#### 4. 多边形 Sprite vs 矩形 Sprite

| 属性 | 矩形 Sprite (Rect) | 多边形 Sprite (Polygon) |
|------|-------------------|------------------------|
| 顶点数 | 4 | 可变（取决于轮廓复杂度） |
| Fill Rate | 浪费（透明区域也占像素） | 高效（只覆盖非透明区域） |
| Overdraw | 高（透明像素写入 alpha 0） | 低（减少像素着色器调用） |
| 合批兼容性 | 好 | 差（顶点格式不同，打断合批） |
| 生成成本 | 低 | 高（需要 Mesh 生成） |

**决策**：大多数场景使用矩形 Sprite + Tight Mesh 即可。多边形 Sprite 仅在大量透明区域且 Overdraw 成为瓶颈时考虑 — 且要注意它可能破坏合批。

#### 5. 动态合批 vs 静态合批（2D 语境）

- **动态合批**（Dynamic Batching）：Unity 在运行时自动将小网格（<300 顶点）合并。对 SpriteRenderer 自动生效，但有顶点数限制。每一帧都重新合并 → CPU 开销。
- **静态合批**（Static Batching）：标记为 `static` 的对象在构建时预先合并。不适用于动态生成的 Sprite。
- **GPU Instancing**：对同 Mesh+Material 的对象，使用常量缓冲区（CBuffer）传递每个实例的变换矩阵。对 Sprite 不太实用（因为每个 Sprite 的 UV 不同）。
- **SRP Batcher**（URP/HDRP）：不合并顶点，但将材质属性缓存到 GPU 上，大幅减少状态设置时间。对 SpriteRenderer 有效，前提是使用兼容的 Shader。

**最佳实践**：在 URP 项目中使用 SRP Batcher + Sprite Atlas 是最佳组合。SRP Batcher 加速材质切换，Atlas 确保纹理不变。

---

## 2. 代码示例

### 示例 A：Unity — 1000 Sprite 有无 Atlas 的性能对比

```csharp
// SpriteBatchingBenchmark.cs
// 用法：挂载到空 GameObject，设置 spriteCount=1000，运行后观察 Profiler
// 前提：创建 Sprite Atlas 并将 Sprites 打包进去
// 对比：atlasSprites 指向 Atlas 中的 Sprite vs separateSprites 指向独立纹理的 Sprite

using UnityEngine;
using UnityEngine.U2D; // SpriteAtlas
using System.Collections.Generic;
using System.Diagnostics;

public class SpriteBatchingBenchmark : MonoBehaviour
{
    [Header("Sprites")]
    [SerializeField] private SpriteAtlas spriteAtlas;
    [SerializeField] private Sprite[] separateSprites; // 来自独立纹理
    [SerializeField] private Sprite[] atlasSprites;    // 来自 Atlas（打包后）

    [Header("Settings")]
    [SerializeField] private int spriteCount = 1000;
    [SerializeField] private float spreadRadius = 10f;
    [SerializeField] private bool useAtlas = true;

    private List<GameObject> spawnedSprites = new List<GameObject>();

    private void Start()
    {
        if (useAtlas && atlasSprites == null)
        {
            UnityEngine.Debug.LogError("请将 Atlas 中的 Sprites 拖入 atlasSprites 数组");
            return;
        }
        if (!useAtlas && separateSprites == null)
        {
            UnityEngine.Debug.LogError("请将独立纹理的 Sprites 拖入 separateSprites 数组");
            return;
        }
        SpawnSprites();
    }

    private void SpawnSprites()
    {
        Sprite[] sourcePool = useAtlas ? atlasSprites : separateSprites;
        Material baseMaterial = sourcePool[0].texture != null
            ? new Material(Shader.Find("Sprites/Default"))
            : null;

        Vector3 center = transform.position;
        for (int i = 0; i < spriteCount; i++)
        {
            GameObject go = new GameObject($"Sprite_{i}");
            go.transform.SetParent(transform);
            go.transform.position = center + new Vector3(
                Random.Range(-spreadRadius, spreadRadius),
                Random.Range(-spreadRadius, spreadRadius),
                0f
            );

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = sourcePool[i % sourcePool.Length];

            // 保持相同材质以促进合批
            if (baseMaterial != null)
                sr.sharedMaterial = baseMaterial;

            // 随机排序层以模拟真实场景
            sr.sortingOrder = Random.Range(0, 50);

            spawnedSprites.Add(go);
        }
    }

    private void Update()
    {
        // 每帧移动 Sprite 使合批器持续工作
        float t = Time.time;
        for (int i = 0; i < spawnedSprites.Count; i++)
        {
            Vector3 pos = spawnedSprites[i].transform.position;
            pos.y += Mathf.Sin(t + i * 0.1f) * 0.01f;
            spawnedSprites[i].transform.position = pos;
        }
    }

    private void OnDestroy()
    {
        foreach (var go in spawnedSprites)
            if (go != null) Destroy(go);
        spawnedSprites.Clear();
    }

    // 在 Editor 中通过 Profiler 或 Frame Debugger 观察：
    // - 不使用 Atlas：Batches ≈ spriteCount（每个 Sprite 独立 Draw Call）
    // - 使用 Atlas：Batches ≈ sortingOrder 的不同值数量（大幅减少）
    //
    // 预期结果（spriteCount=1000）：
    // 无 Atlas: ~800-1000 Batches, ~8-15ms CPU
    // 有 Atlas: ~30-60 Batches（取决于 Sorting Order 分布）, ~1-3ms CPU
}

// 使用方法（Editor 模式）：
// 1. 创建 Sprite Atlas（Assets → Create → 2D → Sprite Atlas）
// 2. 将你的 Sprite 纹理拖入 Atlas 的 Objects for Packing
// 3. 点击 Pack Preview 生成 Atlas
// 4. 通过 SpriteAtlas.GetSprites() 获取所有打包后的 Sprite
// 5. 或者分别引用独立纹理的 Sprite 和 Atlas 中的 Sprite 进行对比

// 自动填充 Atlas Sprites 的辅助方法（放在同一个类中）：
#if UNITY_EDITOR
    [ContextMenu("Load Atlas Sprites")]
    private void LoadAtlasSprites()
    {
        if (spriteAtlas == null)
        {
            UnityEngine.Debug.LogWarning("请先拖入 SpriteAtlas");
            return;
        }
        Sprite[] sprites = new Sprite[spriteAtlas.spriteCount];
        spriteAtlas.GetSprites(sprites);
        atlasSprites = sprites;
        UnityEngine.Debug.Log($"从 Atlas 加载了 {sprites.Length} 个 Sprites");
    }
#endif
```

### 示例 B：C++ — 手动实现 Sprite Batch（单 Draw Call 绘制纹理四边形）

```cpp
// sprite_batch_renderer.cpp
// 平台无关的 OpenGL 示例：手动将多个 Sprite 合并到一次 Draw Call
// 编译 (Linux): g++ -std=c++17 sprite_batch_renderer.cpp -o batch_test -lglfw -lGL
// 编译 (Win/mingw): g++ -std=c++17 sprite_batch_renderer.cpp -o batch_test.exe -lglfw3 -lopengl32

#include <GL/glew.h>
#include <GLFW/glfw3.h>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <cmath>

// ---- 数据结构 ----

struct Vertex {
    float x, y;     // 位置
    float u, v;     // UV
};

struct SpriteInstance {
    float posX, posY;       // 世界位置
    float scaleX, scaleY;   // 缩放
    float rotation;         // 旋转（弧度）
    float uvLeft, uvTop;    // 在图集中的 UV 区域
    float uvRight, uvBottom;
    float r, g, b, a;       // 颜色
};

// ---- 批处理渲染器 ----

class SpriteBatchRenderer {
private:
    GLuint vao = 0, vbo = 0, ibo = 0;
    GLuint shaderProgram = 0;
    GLuint textureID = 0;

    // 每个 Sprite 用 4 个顶点、6 个索引（两个三角形）
    static constexpr int VERTICES_PER_SPRITE = 4;
    static constexpr int INDICES_PER_SPRITE  = 6;
    static constexpr int MAX_SPRITES         = 2048;

    // 预分配缓冲区，避免每帧分配
    Vertex  vertexBuffer[MAX_SPRITES * VERTICES_PER_SPRITE];
    GLuint  indexBuffer [MAX_SPRITES * INDICES_PER_SPRITE];
    int     spriteCount = 0;

    // 着色器源码
    static const char* vertexShaderSrc;
    static const char* fragmentShaderSrc;

public:
    bool Initialize(const char* texturePath) {
        // 创建 VAO
        glGenVertexArrays(1, &vao);
        glBindVertexArray(vao);

        // 创建 VBO（动态更新）
        glGenBuffers(1, &vbo);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBufferData(GL_ARRAY_BUFFER,
                     sizeof(vertexBuffer), nullptr, GL_DYNAMIC_DRAW);

        // 创建 IBO（静态，因为索引模式不变）
        glGenBuffers(1, &ibo);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo);

        // 预生成索引：每个 quad 的 6 个索引
        for (int i = 0; i < MAX_SPRITES; i++) {
            int baseVert = i * VERTICES_PER_SPRITE;
            int baseIdx  = i * INDICES_PER_SPRITE;
            indexBuffer[baseIdx + 0] = baseVert + 0;
            indexBuffer[baseIdx + 1] = baseVert + 1;
            indexBuffer[baseIdx + 2] = baseVert + 2;
            indexBuffer[baseIdx + 3] = baseVert + 2;
            indexBuffer[baseIdx + 4] = baseVert + 3;
            indexBuffer[baseIdx + 5] = baseVert + 0;
        }
        glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                     sizeof(indexBuffer), indexBuffer, GL_STATIC_DRAW);

        // 顶点属性布局
        // position (2 floats)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE,
                              sizeof(Vertex), (void*)offsetof(Vertex, x));
        glEnableVertexAttribArray(0);
        // uv (2 floats)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE,
                              sizeof(Vertex), (void*)offsetof(Vertex, u));
        glEnableVertexAttribArray(1);

        // 编译着色器
        if (!CompileShaders()) return false;

        // 加载纹理（单张图集，所有 Sprite 来源）
        if (!LoadTexture(texturePath)) return false;

        glBindVertexArray(0);
        printf("[SpriteBatch] 初始化完成，最大 Sprite 数: %d\n", MAX_SPRITES);
        return true;
    }

    void BeginBatch() {
        spriteCount = 0;
    }

    void AddSprite(const SpriteInstance& sprite) {
        if (spriteCount >= MAX_SPRITES) {
            Flush(); // 缓冲区满，先提交当前批次
        }

        int vi = spriteCount * VERTICES_PER_SPRITE;

        // 计算旋转后的 4 个角点
        float cosR = cosf(sprite.rotation);
        float sinR = sinf(sprite.rotation);
        float hw = sprite.scaleX * 0.5f;
        float hh = sprite.scaleY * 0.5f;

        float corners[4][2] = {
            {-hw, -hh}, { hw, -hh}, { hw,  hh}, {-hw,  hh}
        };

        float uvs[4][2] = {
            {sprite.uvLeft,  sprite.uvBottom},
            {sprite.uvRight, sprite.uvBottom},
            {sprite.uvRight, sprite.uvTop},
            {sprite.uvLeft,  sprite.uvTop}
        };

        for (int c = 0; c < 4; c++) {
            // 旋转角点
            float rx = corners[c][0] * cosR - corners[c][1] * sinR;
            float ry = corners[c][0] * sinR + corners[c][1] * cosR;

            vertexBuffer[vi + c].x = sprite.posX + rx;
            vertexBuffer[vi + c].y = sprite.posY + ry;
            vertexBuffer[vi + c].u = uvs[c][0];
            vertexBuffer[vi + c].v = uvs[c][1];
        }

        spriteCount++;
    }

    void Flush() {
        if (spriteCount == 0) return;

        glUseProgram(shaderProgram);

        // 上传顶点数据
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBufferSubData(GL_ARRAY_BUFFER, 0,
                        spriteCount * VERTICES_PER_SPRITE * sizeof(Vertex),
                        vertexBuffer);

        // 设置 uniform
        GLint texLoc = glGetUniformLocation(shaderProgram, "uTexture");
        glUniform1i(texLoc, 0);

        // 传入投影矩阵（正交投影）
        GLint projLoc = glGetUniformLocation(shaderProgram, "uProjection");
        // 这里简化为单位矩阵，实际应传入正交投影
        float identity[16] = {
            1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1
        };
        glUniformMatrix4fv(projLoc, 1, GL_FALSE, identity);

        glBindVertexArray(vao);
        glBindTexture(GL_TEXTURE_2D, textureID);

        // ★ 关键：一次 Draw Call 绘制所有 Sprite ★
        glDrawElements(GL_TRIANGLES,
                       spriteCount * INDICES_PER_SPRITE,
                       GL_UNSIGNED_INT, nullptr);

        glBindVertexArray(0);
        // printf("[SpriteBatch] Flush: %d sprites in 1 draw call\n", spriteCount);
        spriteCount = 0;
    }

    void EndBatch() {
        Flush();
    }

    void Shutdown() {
        glDeleteVertexArrays(1, &vao);
        glDeleteBuffers(1, &vbo);
        glDeleteBuffers(1, &ibo);
        glDeleteProgram(shaderProgram);
        glDeleteTextures(1, &textureID);
    }

private:
    bool CompileShaders() {
        GLuint vs = glCreateShader(GL_VERTEX_SHADER);
        glShaderSource(vs, 1, &vertexShaderSrc, nullptr);
        glCompileShader(vs);

        GLuint fs = glCreateShader(GL_FRAGMENT_SHADER);
        glShaderSource(fs, 1, &fragmentShaderSrc, nullptr);
        glCompileShader(fs);

        shaderProgram = glCreateProgram();
        glAttachShader(shaderProgram, vs);
        glAttachShader(shaderProgram, fs);
        glLinkProgram(shaderProgram);

        // 检查链接状态
        GLint success;
        glGetProgramiv(shaderProgram, GL_LINK_STATUS, &success);
        if (!success) {
            char log[512];
            glGetProgramInfoLog(shaderProgram, 512, nullptr, log);
            printf("[SpriteBatch] Shader link error: %s\n", log);
            return false;
        }

        glDeleteShader(vs);
        glDeleteShader(fs);
        return true;
    }

    bool LoadTexture(const char* path) {
        // 简化版纹理加载（实际项目应使用 stb_image 等库）
        // 这里创建一个 256x256 的程序化纹理作为示例
        glGenTextures(1, &textureID);
        glBindTexture(GL_TEXTURE_2D, textureID);

        int width = 256, height = 256;
        std::vector<unsigned char> pixels(width * height * 4);

        // 生成棋盘格纹理（代表多个 Sprite 的图集）
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int idx = (y * width + x) * 4;
                int cx = x / 64, cy = y / 64;
                bool white = (cx + cy) % 2 == 0;
                pixels[idx + 0] = white ? 255 : 64;   // R
                pixels[idx + 1] = white ? 255 : 64;   // G
                pixels[idx + 2] = white ? 255 : 64;   // B
                pixels[idx + 3] = 255;                 // A
            }
        }

        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

        printf("[SpriteBatch] 纹理加载完成: %dx%d\n", width, height);
        return true;
    }
};

// 静态着色器源码定义
const char* SpriteBatchRenderer::vertexShaderSrc = R"(
#version 330 core
layout(location = 0) in vec2 aPosition;
layout(location = 1) in vec2 aTexCoord;

uniform mat4 uProjection;

out vec2 vTexCoord;

void main() {
    gl_Position = uProjection * vec4(aPosition, 0.0, 1.0);
    vTexCoord = aTexCoord;
}
)";

const char* SpriteBatchRenderer::fragmentShaderSrc = R"(
#version 330 core
in vec2 vTexCoord;

uniform sampler2D uTexture;

out vec4 FragColor;

void main() {
    FragColor = texture(uTexture, vTexCoord);
}
)";

// ---- 测试入口 ----

int main() {
    if (!glfwInit()) {
        printf("GLFW 初始化失败\n");
        return 1;
    }

    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);

    GLFWwindow* window = glfwCreateWindow(800, 600, "Sprite Batch Demo", nullptr, nullptr);
    if (!window) {
        printf("窗口创建失败\n");
        glfwTerminate();
        return 1;
    }

    glfwMakeContextCurrent(window);

    if (glewInit() != GLEW_OK) {
        printf("GLEW 初始化失败\n");
        return 1;
    }

    SpriteBatchRenderer batch;
    batch.Initialize(nullptr);

    // 生成 1000 个随机 Sprite（都来自同一图集）
    std::vector<SpriteInstance> sprites(1000);
    for (int i = 0; i < 1000; i++) {
        float cellU = (float)(rand() % 4) * 0.25f;  // 4x4 图集格
        float cellV = (float)(rand() % 4) * 0.25f;

        sprites[i] = {
            (float)(rand() % 800) - 400,   // posX
            (float)(rand() % 600) - 300,   // posY
            32.0f, 32.0f,                  // scaleX, scaleY
            0.0f,                          // rotation
            cellU, cellV,                  // uvLeft, uvTop
            cellU + 0.25f, cellV + 0.25f,  // uvRight, uvBottom
            1.0f, 1.0f, 1.0f, 1.0f        // color (white)
        };
    }

    double lastTime = glfwGetTime();
    int frameCount = 0;

    while (!glfwWindowShouldClose(window)) {
        glClear(GL_COLOR_BUFFER_BIT);

        // ★ 一次 Begin/End 提交全部 1000 个 Sprite ★
        batch.BeginBatch();
        for (auto& s : sprites) {
            batch.AddSprite(s);
        }
        batch.EndBatch();
        // → 仅 1 次 Draw Call！

        glfwSwapBuffers(window);
        glfwPollEvents();

        frameCount++;
        double now = glfwGetTime();
        if (now - lastTime >= 1.0) {
            printf("FPS: %.1f | 1000 sprites in 1 draw call\n",
                   frameCount / (now - lastTime));
            lastTime = now;
            frameCount = 0;
        }
    }

    batch.Shutdown();
    glfwDestroyWindow(window);
    glfwTerminate();
    return 0;
}
```

**关键要点**：注意 C++ 示例中的 `glDrawElements` 只调用**一次** — 所有 Sprite 的顶点和 UV 已在 `BeginBatch/EndBatch` 之间预打包进 VBO。这就是合批的本质：CPU 端将数据预合并，GPU 端一次绘制。

---

## 3. 练习

### 练习 1: 合批观测（基础）

**目标**：使用 Frame Debugger 直观观察合批行为

1. 在 Unity 中创建 20 个 SpriteRenderer，10 个使用 Sprite A（来自 Atlas X），10 个使用 Sprite B（来自 Atlas Y）
2. 调整 Sorting Order 使 A 和 B 交替排列
3. 打开 `Window → Analysis → Frame Debugger`，点击 Enable，观察 Batches 数量
4. 现在创建一个 Sprite Atlas，将 A 和 B 打包到一起
5. 将所有 Sprite 替换为 Atlas 版本，再次观察 Batches 数量
6. 记录：合并前后 Batches 数量从多少降到多少？

**预期**：合并前 ~15-20 Batches，合并后 ~1-5 Batches

### 练习 2: 动态分辨率调整（进阶）

**目标**：修改 C++ 示例，添加 frustum culling 仅提交可见 Sprite

1. 在 `AddSprite` 前添加包围盒检查：如果 Sprite 的 AABB 完全在屏幕外，跳过
2. 实现一个简单的移动摄像机（WASD 控制）
3. 测量：1000 个 Sprite 分布在大地图上（如 10000x10000 世界），仅 10% 可见时，Batch 提交的 Sprite 数量变化

**关键问题**：即使只绘制 100 个可见 Sprite，它们仍然在**同一个 Batch 中** — 这就是 Batch 的优势：可见性裁剪不增加 Draw Call。

### 练习 3: 自定义 Shader 合批（挑战，可选）

**目标**：在 Unity 中实现一个"颜色闪烁"效果的合批兼容 Shader

1. 创建自定义 Shader（基于 `Sprites/Default`），添加 `_FlashColor` 属性
2. 使用 `MaterialPropertyBlock` 为每个 Sprite 传递不同的 `_FlashColor`
3. 观察：Frame Debugger 中 Batches 是否仍然合并？
   - 如果 Batches 增加 → 你的 Shader 不支持 SRP Batcher
   - 如果 Batches 不变 → SRP Batcher 生效

---

## 4. 扩展阅读

- **Unity 官方文档 — Sprite Atlas**: https://docs.unity3d.com/Manual/class-SpriteAtlas.html
- **Unity Frame Debugger 指南**: https://docs.unity3d.com/Manual/FrameDebugger.html
- **UE Paper2D 文档**: https://docs.unrealengine.com/en-US/AnimatingObjects/Paper2D/
- **TexturePacker**: https://www.codeandweb.com/texturepacker — 支持多边形打包、多引擎导出
- **"A Primer on Efficient Rendering of Sprites"** — Intel Developer Zone（已归档，搜索 Wayback Machine）
- **NVIDIA "Batch, Batch, Batch"** (GDC 2014): 深入讲解合批决策对 GPU 的影响

---

## 常见陷阱

1. **"我把 Sprite 放进 Atlas 就自动合批了"— 不对。** 还必须确保所有 SpriteRenderer 使用**相同的 Material 实例**。如果你给每个 Sprite 创建了新的 Material，即使它们引用同一 Atlas，也不会合批。

2. **透明度排序 (Alpha Sorting) 破坏合批。** 如果启用了 Transparency Sort Mode 或手动调整了 Sorting Order 使不同纹理的 Sprite 交错排列，每个交错点都会产生新的 Batch。**解决方案**：尽可能按纹理分组排列 Z-Order。

3. **Atlas 尺寸过大。** 一张 8192x8192 的 Atlas 在移动端会直接加载失败（大多数移动 GPU 最大支持 4096）。**解决方案**：按场景/关卡拆分 Atlas，每张不超过 2048（移动端）或 4096（桌面端）。

4. **忘记了 Late Binding 的开销。** Unity Sprite Atlas 的 Late Binding 允许运行时动态加载，但如果每帧都调用 `atlas.GetSprite("sprite_name")`，字符串查找和字典查询会产生 CPU 开销。预先缓存 Sprite 引用。

5. **多边形 Sprite 静默破坏合批。** 当一个多边形 Sprite（有自己独特的 Mesh）出现在矩形 Sprite 之间时，合批器会因顶点格式不匹配而失败。Frame Debugger 会显示 "Non-instanced renderers cannot be batched"。

6. **UE Paper2D 性能陷阱**：Paper2D 的 Tile Map 如果每个 Tile 是独立的 Actor → 每个 Actor 一个 Draw Call → 灾难。应使用 `PaperTileMapActor` + `PaperTileMapComponent`，它内部使用 Instanced Rendering。
