# 工具链与编辑器开发

> **所属计划**: [游戏引擎开发工程师](../plan.md)
> **预计耗时**: 8 小时
> **前置知识**: [06-渲染管线基础](06-rendering-pipeline.md), [07-着色器编程](07-shader-programming.md)

---

## 概述

工具链是连接引擎技术与内容创作者的桥梁，其质量直接决定了开发团队的迭代效率和最终产品的表现力。一个设计精良的编辑器能够让美术师、设计师和程序员在统一的 Workflow 中高效协作；而一条自动化的资产流水线则能确保从源资产到运行时资源的无缝、可重复、可追溯的转换过程。

本章分为两大主题：编辑器开发（使用 Dear ImGui 构建专业编辑器）和资产流水线（多格式导入、处理、管理与构建）。

---

## 1. Dear ImGui 框架深入

Dear ImGui 采用即时模式（Immediate Mode）设计——每一帧，用户代码直接描述"这一帧应该显示什么"，ImGui 负责处理输入、布局和绘制。

### ImGui 与 OpenGL 集成

```cpp
class ImGuiOpenGLBackend {
public:
    GLuint shaderProgram_ = 0, vao_ = 0, vbo_ = 0, ebo_ = 0, fontTexture_ = 0;
    GLint locTex_ = 0, locProjMtx_ = 0;
    size_t vboCapacity_ = 0, eboCapacity_ = 0;

    bool Init() {
        // 编译 Shader 程序
        const char* vs = R"(#version 330 core
            layout(location=0) in vec2 aPos;
            layout(location=1) in vec2 aTexCoord;
            layout(location=2) in vec4 aColor;
            uniform mat4 uProjMtx;
            out vec4 vColor; out vec2 vTexCoord;
            void main() {
                gl_Position = uProjMtx * vec4(aPos, 0.0, 1.0);
                vColor = aColor; vTexCoord = aTexCoord;
            }
        )";
        const char* fs = R"(#version 330 core
            in vec4 vColor; in vec2 vTexCoord;
            uniform sampler2D uTexture;
            out vec4 FragColor;
            void main() { FragColor = vColor * texture(uTexture, vTexCoord).r; }
        )";

        // 编译、链接、获取 uniform 位置...
        // 创建 VAO/VBO/EBO...
        BuildFontTexture();
        return true;
    }

    void RenderDrawData(ImDrawData* drawData) {
        if (drawData->CmdListsCount == 0) return;

        // 设置正交投影
        float L = drawData->DisplayPos.x;
        float R = drawData->DisplayPos.x + drawData->DisplaySize.x;
        float T = drawData->DisplayPos.y;
        float B = drawData->DisplayPos.y + drawData->DisplaySize.y;
        const float ortho[4][4] = {
            { 2.0f/(R-L), 0.0f, 0.0f, 0.0f },
            { 0.0f, 2.0f/(T-B), 0.0f, 0.0f },
            { 0.0f, 0.0f, -1.0f, 0.0f },
            { (R+L)/(L-R), (T+B)/(B-T), 0.0f, 1.0f }
        };

        glUseProgram(shaderProgram_);
        glUniformMatrix4fv(locProjMtx_, 1, GL_FALSE, &ortho[0][0]);
        glUniform1i(locTex_, 0);
        glBindVertexArray(vao_);

        for (int n = 0; n < drawData->CmdListsCount; n++) {
            const ImDrawList* cmdList = drawData->CmdLists[n];
            // 上传顶点和索引数据...
            for (int cmdI = 0; cmdI < cmdList->CmdBuffer.Size; cmdI++) {
                const ImDrawCmd* pcmd = &cmdList->CmdBuffer[cmdI];
                // 设置裁剪矩形、绑定纹理、绘制...
                glScissor(...);
                glBindTexture(GL_TEXTURE_2D, (GLuint)pcmd->TextureId);
                glDrawElements(GL_TRIANGLES, pcmd->ElemCount, ...);
            }
        }
    }
};
```

### 平台后端（GLFW）

```cpp
class ImGuiGlfwPlatform {
public:
    void Init(GLFWwindow* window) {
        window_ = window;
        ImGuiIO& io = ImGui::GetIO();
        io.BackendPlatformName = "engine_glfw";
        io.ConfigFlags |= ImGuiConfigFlags_DockingEnable;
        io.ConfigFlags |= ImGuiConfigFlags_ViewportsEnable;

        glfwSetMouseButtonCallback(window, MouseButtonCallback);
        glfwSetScrollCallback(window, ScrollCallback);
        glfwSetKeyCallback(window, KeyCallback);
        glfwSetWindowUserPointer(window, this);
    }

    void NewFrame() {
        ImGuiIO& io = ImGui::GetIO();
        int w, h, displayW, displayH;
        glfwGetWindowSize(window_, &w, &h);
        glfwGetFramebufferSize(window_, &displayW, &displayH);
        io.DisplaySize = ImVec2((float)w, (float)h);
        io.DisplayFramebufferScale = ImVec2(
            w > 0 ? (float)displayW / w : 0.0f,
            h > 0 ? (float)displayH / h : 0.0f
        );
        // 更新鼠标位置、按钮状态、滚轮...
    }
};
```

### 主循环集成

```cpp
while (!glfwWindowShouldClose(window)) {
    glfwPollEvents();
    platform.NewFrame();
    ImGui::NewFrame();

    ShowEditorUI();  // 描述所有 UI 元素

    ImGui::Render();
    renderer.RenderDrawData(ImGui::GetDrawData());
    glfwSwapBuffers(window);
}
```

### 主题定制与编辑器视觉风格

专业编辑器通常需要定制化的视觉风格。ImGui 通过修改 `ImGuiStyle` 结构体中的 50+ 个颜色条目来实现主题定制：

```cpp
void SetupEngineEditorTheme() {
    ImGuiStyle& style = ImGui::GetStyle();
    ImVec4* colors = style.Colors;

    // 基础色调：深蓝灰色系，减少视觉疲劳
    colors[ImGuiCol_WindowBg]      = ImVec4(0.15f, 0.16f, 0.18f, 1.0f);
    colors[ImGuiCol_ChildBg]       = ImVec4(0.13f, 0.14f, 0.16f, 1.0f);
    colors[ImGuiCol_MenuBarBg]     = ImVec4(0.12f, 0.13f, 0.15f, 1.0f);
    colors[ImGuiCol_TitleBgActive] = ImVec4(0.18f, 0.40f, 0.80f, 1.0f);

    // 交互元素
    colors[ImGuiCol_Button]        = ImVec4(0.20f, 0.22f, 0.25f, 1.0f);
    colors[ImGuiCol_ButtonHovered] = ImVec4(0.28f, 0.30f, 0.35f, 1.0f);
    colors[ImGuiCol_ButtonActive]  = ImVec4(0.35f, 0.50f, 0.90f, 1.0f);

    // 选中与强调色
    colors[ImGuiCol_Header]        = ImVec4(0.18f, 0.40f, 0.80f, 0.5f);
    colors[ImGuiCol_HeaderHovered] = ImVec4(0.22f, 0.50f, 0.95f, 0.7f);
    colors[ImGuiCol_HeaderActive]  = ImVec4(0.25f, 0.55f, 1.0f, 1.0f);

    // 样式参数
    style.WindowRounding  = 4.0f;
    style.FrameRounding   = 3.0f;
    style.GrabRounding    = 3.0f;
    style.WindowPadding   = ImVec2(8.0f, 8.0f);
    style.FramePadding    = ImVec2(6.0f, 4.0f);
}
```

### 编辑器整体架构

游戏编辑器的模块间协作关系采用分层设计：

```
渲染层 (Render Layer)
  ├── OpenGL/Vulkan 渲染后端
  ├── 视口渲染 (Viewport FBO)
  └── 渲染场景 (RenderScene)

编辑器框架 (Editor Framework)
  ├── Dear ImGui GUI 系统
  ├── 属性面板 (Property Panel)
  ├── 层级面板 (Hierarchy)
  └── 主题定制 (Theme System)

交互系统 (Interaction)
  ├── 变换 Gizmo (Translate/Rotate/Scale)
  ├── 对象拾取 (Ray Picking)
  └── 命令系统 (Undo/Redo)

专用编辑器 (Specialized Editors)
  ├── 材质编辑器 (Node Graph)
  ├── 地形编辑器 (Heightmap Brush)
  └── 粒子编辑器 (CPU/GPU System)

数据层 (Data Layer)
  ├── 场景数据 (Scene Graph)
  ├── 资产数据库 (Asset Database)
  ├── 纹理资源 (Texture Assets)
  └── 模型资源 (Mesh Assets)
```

---

## 2. 场景编辑器

### 视口渲染（Viewport）

视口将引擎渲染输出嵌入到 ImGui 窗口中——场景渲染到 FBO，颜色附件作为纹理在 ImGui 窗口显示。

```cpp
class SceneViewport {
public:
    GLuint fbo_ = 0, colorTexture_ = 0, depthRbo_ = 0;
    int width_ = 1280, height_ = 720;
    glm::vec3 cameraPos_, cameraTarget_;
    float cameraYaw_ = -45.0f, cameraPitch_ = -35.0f, cameraDistance_ = 17.3f;

    void CreateFramebuffer(int w, int h) {
        // 删除旧资源，创建新的颜色纹理和深度 RBO，组装 FBO
        glGenTextures(1, &colorTexture_);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glGenRenderbuffers(1, &depthRbo_);
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, w, h);
        glGenFramebuffers(1, &fbo_);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, colorTexture_, 0);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, depthRbo_);
    }

    void Render(Scene* scene, Renderer* renderer) {
        ImGui::Begin("Scene Viewport");
        ImVec2 contentSize = ImGui::GetContentRegionAvail();
        if (contentSize.x != width_ || contentSize.y != height_) {
            CreateFramebuffer((int)contentSize.x, (int)contentSize.y);
        }

        // 绑定 FBO 渲染场景
        glBindFramebuffer(GL_FRAMEBUFFER, fbo_);
        glViewport(0, 0, width_, height_);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        glm::mat4 view, proj;
        UpdateCameraMatrices(view, proj);
        renderer->RenderScene(scene, view, proj, cameraPos_);
        glBindFramebuffer(GL_FRAMEBUFFER, 0);

        // 显示 FBO 纹理（UV 翻转）
        ImGui::Image((ImTextureID)(intptr_t)colorTexture_, contentSize,
                     ImVec2(0, 1), ImVec2(1, 0));
        ImGui::End();
    }
};
```

### Gizmo 实现

变换操控器将 2D 鼠标位移映射到 3D 空间变换。经典 Gizmo 使用三轴箭头（平移）、三个圆环（旋转）和三轴缩放手柄，每个轴使用标准颜色编码：X 红色、Y 绿色、Z 蓝色。

Gizmo 的数学核心在于射线与几何体的求交，以及屏幕空间到世界空间的坐标映射。对于平移操作，定义一个包含操作轴的平面，计算鼠标射线与该平面的交点，然后将交点在轴上的投影差值应用到对象位置。旋转操作使用"虚拟轨迹球"概念，追踪鼠标在平面上的移动角度。缩放操作与平移类似，但将位移量解释为缩放因子。

关键实现要点：
- 计算 Gizmo 在屏幕保持固定大小所需的世界空间缩放
- 射线到线段的最短距离计算
- 屏幕坐标到世界射线的转换
- 拖拽状态的保存与恢复

### 对象选择（Picking）

对象选择是场景编辑的基础交互。最常用的技术是基于射线的包围盒检测（Ray-AABB Intersection），使用 slab method：

```cpp
struct AABB {
    glm::vec3 min, max;
    bool Intersect(const Ray& ray, float& outT) const {
        float tmin = 0.0f, tmax = FLT_MAX;
        for (int i = 0; i < 3; i++) {
            if (abs(ray.direction[i]) < 1e-6f) {
                if (ray.origin[i] < min[i] || ray.origin[i] > max[i])
                    return false;
            } else {
                float ood = 1.0f / ray.direction[i];
                float t1 = (min[i] - ray.origin[i]) * ood;
                float t2 = (max[i] - ray.origin[i]) * ood;
                if (t1 > t2) std::swap(t1, t2);
                tmin = std::max(tmin, t1);
                tmax = std::min(tmax, t2);
                if (tmin > tmax) return false;
            }
        }
        outT = tmin;
        return true;
    }
};
```

对于需要更高精度的场景，使用 **Moller-Trumbore 射线-三角形相交算法**。对于大型 Mesh（数十万到数百万三角形），需要引入层次包围盒（BVH）加速结构。

### 撤销重做系统（Command Pattern）

```cpp
class ICommand {
public:
    virtual ~ICommand() = default;
    virtual void Execute() = 0;
    virtual void Undo() = 0;
    virtual const char* GetName() const = 0;
};

class CommandManager {
    static constexpr size_t MAX_HISTORY_SIZE = 256;
    std::vector<std::unique_ptr<ICommand>> history_;
    int currentIndex_ = -1;
public:
    void Execute(std::unique_ptr<ICommand> cmd) {
        cmd->Execute();
        // 清除当前位置之后的历史（分支历史被丢弃）
        if (currentIndex_ < (int)history_.size() - 1) {
            history_.erase(history_.begin() + currentIndex_ + 1, history_.end());
        }
        // 尝试合并连续命令
        if (!history_.empty() && currentIndex_ >= 0) {
            if (history_[currentIndex_]->Merge(cmd.get())) {
                return;  // 合并成功，不添加新命令
            }
        }
        history_.push_back(std::move(cmd));
        currentIndex_++;
        // 超过最大容量时移除最旧的命令
        if (history_.size() > MAX_HISTORY_SIZE) {
            history_.erase(history_.begin());
            currentIndex_--;
        }
    }
    void Undo() {
        if (currentIndex_ >= 0) {
            history_[currentIndex_]->Undo();
            currentIndex_--;
        }
    }
    void Redo() {
        if (currentIndex_ < (int)history_.size() - 1) {
            currentIndex_++;
            history_[currentIndex_]->Redo();
        }
    }
};
```

撤销重做系统的关键设计在于**命令的粒度控制**。过细的粒度会导致用户需要多次撤销才能完成一个逻辑操作，过粗的粒度则丧失了撤销的精确性。解决方案是引入**命令合并机制**：`Merge()` 方法允许将时间上连续、目标相同的命令合并为一个。另一个重要设计是**批量命令**（CompositeCommand），将多个子命令组合为一个原子操作，确保撤销和重做时所有子操作作为一个整体被处理。

---

## 3. 材质、地形与粒子编辑器

### 材质编辑器

材质编辑器允许美术师以可视化的方式创建和编辑着色器材质。其核心设计是一个**节点图编辑器**（Node Graph Editor），用户通过连接代表数学运算和渲染状态的节点来构建材质逻辑，编辑器将这些节点图编译为可执行的 GPU Shader 代码。

#### 节点图数据模型

节点图采用有向无环图（DAG）结构。每个节点包含输入端口（Pin）、输出端口和内部运算逻辑。连接（Link）将上游节点的输出端口与下游节点的输入端口关联。

关键约束：
- 输入端口只能有一个连接（单源）
- 输出端口可以有多个连接（广播）
- 连接的两端必须类型匹配
- 不能形成有向环（环检测使用 DFS）

#### Shader 代码生成

节点图到 GLSL 的编译采用**后序遍历**（Post-order Traversal）算法，从材质输出节点出发，递归访问所有输入连接，为每个已访问节点生成对应的 GLSL 代码片段。

```cpp
class ShaderCodeGenerator {
public:
    struct GeneratedShader {
        std::string vertexSource;
        std::string fragmentSource;
        std::vector<std::string> textureUniforms;
    };

    GeneratedShader Generate(const NodeGraph& graph) {
        // 找到 MaterialOutput 节点作为生成起点
        Node* outputNode = nullptr;
        for (auto& node : graph.nodes) {
            if (node->type == NodeType::MaterialOutput) {
                outputNode = node.get();
                break;
            }
        }
        if (!outputNode) return {};

        // 生成片段 Shader：从输出节点递归遍历
        fragmentShader_ << "#version 330 core\n";
        fragmentShader_ << "out vec4 FragColor;\n\n";
        fragmentShader_ << "void main() {\n";

        for (auto& pin : outputNode->inputPins) {
            for (const auto& link : graph.links) {
                if (link.toPin == pin.id) {
                    std::string varName = GenerateNodeCode(graph, link.fromPin);
                    if (pin.name == "Base Color") {
                        fragmentShader_ << "    vec3 baseColor = " << varName << ";\n";
                    } else if (pin.name == "Metallic") {
                        fragmentShader_ << "    float metallic = " << varName << ";\n";
                    }
                }
            }
        }
        fragmentShader_ << "}\n";
        return {vertexShader_.str(), fragmentShader_.str(), textureUniforms_};
    }

private:
    std::string GenerateNodeCode(const NodeGraph& graph, uint32_t outputPinId) {
        // 找到对应的节点和端口
        // 已访问则返回缓存的变量名
        // 递归生成输入连接的代码
        // 生成本节点的运算代码
        // 返回输出变量名
    }
};
```

代码生成完成后，需要通过 OpenGL Shader 编译器验证生成的代码。如果编译失败，错误信息需要映射回节点图中的具体节点。实时预览采用延迟策略：用户停止编辑后 200ms 再触发编译，避免频繁修改导致的编译开销。

### 地形编辑器

地形编辑器是开放世界游戏引擎的重要组成部分。

#### 高度图编辑

高度图（Heightmap）是地形表示的核心数据结构，本质上是一张灰度图像，每个像素的亮度值代表该位置的地形高度。笔刷系统包括：

- **隆起（Raise）**：在局部区域增加高度值
- **凹陷（Lower）**：降低高度值
- **平滑（Smooth）**：使用高斯核对邻域进行卷积平均
- **整平（Flatten）**：将区域线性插值到目标高度
- **噪点（Noise）**：使用 Simplex Noise 或 Value Noise 添加随机扰动

关键问题：
- **边界处理**：笔刷影响区域可能超出高度图边界，必须通过钳制确保数组访问安全
- **法线更新**：每次高度图修改后，对应区域的法线贴图必须同步重新计算
- **性能优化**：对于 4096x4096 的高度图，采用局部更新策略（`glTexSubImage2D`）或将法线计算 offload 到 GPU Compute Shader

#### 纹理层混合（Splatting）

地形表面通常需要多种材质（草地、泥土、岩石、雪地）的自然过渡。Splat map 为每个像素存储每种材质的权重，Shader 中根据权重进行纹理混合。编辑器的泼溅绘制工具允许美术师直接在 3D 视口中"绘制"材质分布。

#### 植被放置工具

植被系统采用**程序化散布**结合手动调整的策略。核心算法包括：

- **伪随机数生成位置**：结合地形高度和坡度约束进行过滤
- **泊松盘采样**（Poisson Disk Sampling）：保证实例之间的最小间距
- **空间哈希网格**（Spatial Hash Grid）：将实例按世界位置分桶存储，使剔除和碰撞检测从 O(n) 降低到接近 O(1)
- **GPU Instancing** 或 **Indirect Draw**：数千甚至数百万个植被实例的渲染

### 粒子编辑器

#### CPU 粒子系统

CPU 粒子系统使用主处理器逐个更新粒子状态。数据结构采用 **SoA（Structure of Arrays）** 布局：

```cpp
struct ParticleSoA {
    std::vector<glm::vec3> positions;
    std::vector<glm::vec3> velocities;
    std::vector<glm::vec4> colors;
    std::vector<float> sizes;
    std::vector<float> lifetimes;
    std::vector<bool> alive;
    size_t count = 0;
    size_t capacity = 0;

    void RemoveDead() {
        size_t write = 0;
        for (size_t read = 0; read < count; read++) {
            if (alive[read]) {
                if (write != read) {
                    positions[write] = positions[read];
                    velocities[write] = velocities[read];
                    colors[write] = colors[read];
                    sizes[write] = sizes[read];
                }
                alive[write] = true;
                write++;
            }
        }
        count = write;
    }
};
```

死亡粒子的移除使用 **swap-and-pop** 策略，将死亡粒子与数组末尾的存活粒子交换然后减少计数，这种 O(1) 的操作避免了大规模数据搬移。

发射器形状包括：点、球体、立方体、圆锥、网格表面、环形。粒子的渲染使用 GPU Instancing，所有粒子共享同一个 Billboard 几何体。

#### 软粒子（Soft Particles）

软粒子技术解决了传统粒子渲染中粒子与场景几何体相交时的硬边问题。通过比较粒子的深度值和场景深度缓冲中的值，当粒子位于场景表面附近时，逐渐降低其透明度：

```glsl
float sceneDepth = texture(uDepthTexture, screenUV).r;
float sceneLinear = LinearizeDepth(sceneDepth);
float particleLinear = LinearizeDepth(gl_FragCoord.z);
float depthDiff = sceneLinear - particleLinear;
float fade = smoothstep(0.0, 0.5, depthDiff);
particleAlpha *= fade;
```

#### GPU 粒子系统（Compute Shader 驱动）

当粒子数量超过数十万个时，CPU 更新成为瓶颈。GPU 粒子系统将发射、模拟和死亡检测全部迁移到 Compute Shader 中。

核心架构：
- **双缓冲**（Ping-Pong Buffer）：模拟阶段读取上一帧状态，写入下一帧缓冲
- **死亡粒子索引池**（Dead Index Pool）：栈结构，存储当前未使用的粒子索引
- **存活索引列表**（Alive Index List）：记录当前所有活跃粒子的索引
- **间接绘制**（Indirect Draw）：GPU 通过原子计数器计算存活粒子数，写入间接参数缓冲，无需 CPU 回读

Compute Shader 中的原子操作（`atomicCounterIncrement` / `atomicCounterDecrement`）确保多线程同时访问索引池时的线程安全。`glMemoryBarrier` 在发射和模拟阶段之间插入同步点。

---

## 4. 资产流水线

### 资产导入器

| 格式 | 用途 | 特点 |
|------|------|------|
| FBX | 模型/动画 | 业界标准，闭源 SDK |
| glTF | 3D 资产传输 | Khronos 开放标准，Web/移动端友好 |
| OBJ | 简单模型 | 文本格式，适合快速原型 |

#### FBX SDK 导入

FBX 是 Autodesk 推出的 3D 数据交换格式。FBX SDK 提供了 C++ 接口，允许读取场景图、几何体、动画、材质等完整数据。

**关键实现要点**：
- **坐标系和单位转换**：`FbxAxisSystem::ConvertScene` 进行自动坐标系转换，`FbxSystemUnit::m.ConvertScene` 转换单位到米
- **三角化**（Triangulation）：FBX 中的多边形可能是任意边数，需要扇形或条带三角化
- **骨骼蒙皮权重提取**：处理每顶点超过 4 个骨骼引用的情况，按权重排序保留最大的 4 个并归一化

#### glTF 导入

glTF（GL Transmission Format）是 Khronos Group 推出的开放 3D 资产格式，基于 JSON 描述场景结构，几何体和动画数据存储在二进制 Buffer 中。

glTF 的解析反映了其格式设计的核心思想——通过 **Accessor + BufferView + Buffer** 的三层间接机制描述数据布局：
- **Accessor** 定义数据的语义（类型、分量数、取值范围）
- **BufferView** 定义数据的物理布局（偏移、步幅、目标用途）
- **Buffer** 是原始二进制数据

这种设计允许多个 Accessor 共享同一个 BufferView，多个 BufferView 指向同一个 Buffer 的不同区域，最大化空间利用率。

#### OBJ 格式快速导入

OBJ 虽然功能有限（不支持骨骼、动画、PBR 材质），但其纯文本格式使其成为快速原型的理想选择。核心挑战在于面定义中的顶点索引去重——OBJ 允许每个三角形角点引用不同的位置、UV 和法线索引，而 GPU 渲染需要每个顶点拥有唯一的属性组合。通过哈希表将 `(posIdx, uvIdx, normIdx)` 三元组映射到合并后的顶点索引，实现高效的重复顶点消除。

### 资产处理管线

```
源资产文件 (.fbx, .png, .wav)
    |
    v
导入器解析 → 引擎内部中间格式
    |
    v
处理器流水线：
  - 纹理：压缩 (BC/ASTC/ETC)、生成 Mipmap
  - 模型：生成 LOD、计算切线、优化顶点缓存
  - 音频：转码、采样率转换
    |
    v
运行时资源文件 (.engine_asset)
```

**纹理压缩格式**：

| 格式 | 平台 | 压缩比 | 质量 |
|------|------|--------|------|
| BC1-7 (DXT/S3TC) | PC / Xbox | 4:1 ~ 8:1 | 良好 |
| ASTC | 移动端 | 可变 (4x4 到 12x12) | 优秀 |
| ETC2 | Android | 4:1 | 良好 |

#### 纹理压缩管线

纹理是游戏中内存占用最大的资源类别之一。一张未压缩的 4K 纹理（RGBA8）占用 64MB 显存。纹理压缩通过专用的 GPU 压缩格式，在保持硬件解压能力的同时将内存占用降低 4-8 倍。

**BC（Block Compression）系列**是 DirectX 平台上的标准。BC1 使用 64 比特存储每个 4x4 块（两个 16 位基准颜色 + 16 个 2 位插值索引），实现 4bpp 压缩比。BC3 在 BC1 基础上额外增加 64 比特的 Alpha 压缩，达到 8bpp。BC5 使用两个 BC3 的 Alpha 通道分别存储法线贴图的 X 和 Y 分量，Z 分量在 Shader 中通过 `Z = sqrt(1 - X^2 - Y^2)` 重建。BC7 为每个 4x4 块从 8 种压缩模式中选择最优方案，是最高质量的格式。

**ASTC**（Adaptive Scalable Texture Compression）支持 4x4 到 12x12 多种块大小，允许在质量和压缩比之间精确权衡。ASTC 4x4 提供与 BC7 相当的质量，ASTC 8x8 达到 2bpp 的极端压缩比。

**ETC2** 主要面向移动端的 OpenGL ES，在所有支持 OpenGL ES 3.0 的设备上可用，是跨安卓设备最安全的压缩选择。

纹理压缩的管线实现需要考虑平台差异：桌面端优先使用 BC7 或 BC5；iOS 端使用 ASTC；安卓端需要回退到 ETC2 以兼容低端设备。

#### 模型 LOD 自动生成

细节层次（Level of Detail，LOD）通过边折叠（Edge Collapse）操作逐步简化几何。核心算法是 **Garland 和 Heckbert 提出的二次误差度量（QEM）**：

为每个三角形定义平面方程 `n · x + d = 0`，每个顶点的误差定义为它到所有关联三角形平面的距离平方和，编码为 4x4 的二次矩阵 Q。当折叠边 `(vi, vj)` 时，新顶点 v' 的二次矩阵为 `Q' = Qi + Qj`，最优折叠位置是使 `v^T Q' v` 最小的点。

算法每次选择误差代价最小的边进行折叠，通过优先队列高效实现。对于生产级应用，还需要考虑边界保持、纹理坐标保留、法线连续性等约束。

#### 法线贴图烘焙

法线贴图将高分辨率模型的表面细节编码到低分辨率模型表面。烘焙过程计算低模表面每个采样点对应高模表面的法线方向，存储为 RGB 纹理。

切线空间到法线空间的转换需要构建 **TBN（Tangent-Bitangent-Normal）矩阵**。切线空间的法线贴图存储的是相对于表面法线的偏移方向，大多数法线贴图呈现偏蓝的色调，因为默认法线方向 `(0, 0, 1)` 对应 RGB `(128, 128, 255)`。

#### 资产依赖追踪

现代游戏资产之间存在复杂的依赖关系：材质依赖纹理、Shader 和参数配置文件；预制体依赖 Mesh、材质和子预制体；场景依赖所有其中引用的资产。

依赖追踪通过**有向无环图（DAG）**实现。当资产 A 修改时，所有从 A 可达的节点都需要重新处理。图的构建在导入时完成：导入器扫描每个资产的引用关系，生成依赖描述文件。处理管线在每次构建前比较源文件的时间戳和依赖图的拓扑顺序，确定需要重新处理的最小资产集合。

### 资产数据库

#### 资产目录结构

```
Project/
├── Assets/                  # 源资产（由美术师/设计师编辑）
│   ├── Models/
│   ├── Textures/
│   ├── Materials/
│   ├── Animations/
│   ├── Audio/
│   ├── Prefabs/
│   └── Scenes/
├── Library/                 # 引擎处理后的运行时资产
│   ├── metadata/           # 每个源资产的元数据文件
│   ├── cache/              # 中间处理结果缓存
│   └── built/              # 最终构建输出
└── ProjectSettings/         # 引擎和项目配置文件
```

核心原则是严格分离**源资产**和**运行时资产**。源资产保留可编辑性，运行时资产被优化为引擎的最高效格式。两者通过元数据文件建立映射关系。

#### GUID 引用系统

全局唯一标识符（GUID）是资产引用的核心机制。每个源资产在首次导入时被分配一个 GUID（128 位 UUID），后续引用都通过 GUID 而非文件路径进行。

**核心优势**：当美术师将 `Textures/Characters/Hero.png` 移动到 `Textures/Hero/` 时，所有引用该纹理的材质、预制体和场景都不需要修改——因为引用是基于 GUID 的，GUID 到路径的映射在数据库中统一更新。

**增量导入策略**：通过比较文件的修改时间戳和内容哈希（SHA-256），系统可以识别未发生变化的文件并跳过处理。当依赖资产变更时，反向依赖图精确识别需要重新导入的受影响资产。

#### 资产版本控制

游戏项目通常包含大量二进制资产，传统 Git 在处理大型二进制文件时效率低下。常用方案：

- **Git LFS**（Large File Storage）：将大文件存储在单独的 LFS 服务器上，Git 仓库中只保留指针文件
- **Perforce**（Helix Core）：文件级锁定机制防止多人同时修改同一资产，高效的二进制文件处理

重要实践：忽略 `Library/` 目录，只将 `Assets/` 和 `ProjectSettings/` 提交到版本控制。`.meta` 文件必须提交，因为它们包含 GUID 和导入设置。

### 构建系统

#### 资源打包（Asset Bundle）

Asset Bundle 将多个资产文件组合为一个或多个打包文件，主要动机包括：
- 减少文件系统开销（数万个小文件的随机读取远慢于少量大文件的顺序读取）
- 支持压缩（减小安装包大小）
- 实现按需加载（DLC、关卡流送、资源热更新）

Bundle 文件结构：
```
Bundle 文件:
├── 文件头 (BundleHeader)
│   ├── 魔数 "BUND"
│   ├── 版本号
│   ├── 压缩标志
│   ├── 条目数量
│   ├── 目录表偏移
│   └── 数据区偏移
├── 数据区 (对齐到 4096 字节)
│   └── [压缩后的资产数据...]
└── 目录表 (TOC)
    └── [TOCEntry: GUID, 偏移, 压缩大小, 原始大小, 类型哈希...]
```

运行时加载器通过 GUID 查询目录表，定位资产在 Bundle 中的偏移和大小，然后解压并加载。

#### 平台差异处理

不同目标平台使用不同的纹理格式、着色器变体和渲染特性。构建系统需要：
- 根据目标平台选择最佳纹理压缩格式（BC7/ASTC/ETC2）
- 生成平台特定的着色器变体（HLSL/GLSL/SPIR-V/Metal SL）
- 处理平台特定的渲染特性差异

#### CI/CD 集成

自动化构建流水线确保每次代码提交都能生成可测试的构建产物，包括：
- 自动导入和处理器管线执行
- 多平台并行构建
- 自动化测试（单元测试、集成测试、性能基准）
- 构建产物打包和分发

---

## 总结

本章涵盖了将引擎技术转化为实际开发工具的关键内容：

1. **Dear ImGui** 的即时模式设计使编辑器 UI 开发极为高效，与游戏循环天然集成
2. **场景编辑器** 的核心子系统包括视口渲染（FBO + ImGui 嵌入）、Gizmo（2D-3D 映射）、Picking（射线检测）和撤销重做（Command Pattern）
3. **材质/地形/粒子编辑器** 是内容创作的核心工具，节点图编辑器和笔刷系统是典型实现
4. **资产流水线** 从源文件到运行时格式的完整转换流程，包含导入、处理、管理和构建四个环节

掌握这些工具链开发技能，你就能为引擎打造专业的内容创作环境——这是区分"可用的引擎"与"生产级的引擎"的关键标志。

---

## 延伸阅读

- **[Dear ImGui Documentation](https://github.com/ocornut/imgui)** — 官方文档和示例
- **《Game Engine Architecture, 3rd Edition》** — Jason Gregory — 工具链章节
- **[glTF 2.0 Specification](https://registry.khronos.org/glTF/)** — Khronos 开放 3D 资产标准
- **Autodesk FBX SDK** — 模型导入的行业标准
