---
title: "07 — 智能指针策略与 GPU 资源管理"
updated: 2026-06-05
---

# 07 — 智能指针策略与 GPU 资源管理

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 4h
> 前置知识: 02-对象生命周期与内存布局, 05-移动语义与值类别精讲, 06-完美转发与万能引用

---

## 1. 概念讲解

### 引擎中的所有权迷局

游戏引擎管理着成千上万的资源——纹理、Shader、Mesh、音频片段、物理网格、渲染命令缓冲。这些资源的最大问题不是"怎么创建"，而是"谁负责销毁、何时销毁"。

考虑这个场景：

```
Renderer 持有 VBO，Physics 引用该 VBO 做碰撞检测
→ Audio 系统不关心 VBO，但 SoundEmitter 引用了 Physics Body
→ 场景卸载时，谁负责删除 VBO？
```

裸指针无法回答这个问题。C++ 中的答案：**智能指针编码所有权语义，在类型层面消除歧义**。

### unique_ptr：引擎资源的默认选择

`std::unique_ptr<T>`（C++11）编码"独占所有权"——有且仅有一个 `unique_ptr` 拥有所指对象。它的大小等于裸指针（零开销），移动即转移所有权，析构时自动释放。

**为什么 unique_ptr 覆盖引擎 95% 的资源管理？**

| 资源类型 | 所有权模式 | 适合的指针 |
|:---------|:---------|:----------|
| GPU 纹理 | 纹理管理器独占拥有 | `unique_ptr<Texture>` |
| 场景节点 | 父节点拥有子节点 | `unique_ptr<SceneNode>` |
| 音频源 | AudioManager 拥有 | `unique_ptr<AudioSource>` |
| 实体组件 | ECS World 拥有 | `unique_ptr<Component>` |
| 渲染后端 | Engine 单例拥有 | `unique_ptr<IRenderBackend>` |

引擎中极少数需要共享所有权。大多数资源有明确的所有者——系统 A 创建它，系统 A 销毁它。其他系统只是"借用"（用裸指针或引用观察）。

### 自定义删除器：GPU 资源的生命线

GPU 资源（OpenGL 纹理、Vulkan Image、D3D12 Resource）必须通过特定的 API 调用来销毁——不是 `delete`，而是 `glDeleteTextures`、`vkDestroyImage` 等。

`unique_ptr<T, Deleter>` 的第二个模板参数支持自定义删除器：

```cpp
// 方式 1: 函数对象（零开销 — 空基类优化）
struct GLTextureDeleter {
    void operator()(GLuint* id) const {
        glDeleteTextures(1, id);
        delete id;
    }
};
using GLTexture = std::unique_ptr<GLuint, GLTextureDeleter>;

// 方式 2: Lambda（C++17 起 lambda 默认构造）
auto deleter = [](GLuint* id) { glDeleteTextures(1, id); delete id; };
std::unique_ptr<GLuint, decltype(deleter)> tex(new GLuint{0}, deleter);
```

### 删除器的开销权衡

| 删除器类型 | 指针大小 | 开销 | 限制 |
|:----------|:--------|:-----|:-----|
| `std::default_delete<T>` | `sizeof(T*)` | 零开销 | 只调用 `delete` |
| 无捕获 lambda（C++20） | `sizeof(T*)` | 零开销 | 需要 C++20 |
| 无状态函数对象 | `sizeof(T*)` | 零开销 | 依赖 EBO |
| 有捕获 lambda | `sizeof(T*) + sizeof(capture)` | 额外存储 | 按引用捕获可缩减 |
| `std::function<void(T*)>` | `sizeof(T*) + 32~64` | 堆分配！ | **永远不要用于热路径** |

**关键教训**：永远不要用 `std::function` 作为 `unique_ptr` 的删除器。每次构造/移动都可能堆分配。

### shared_ptr：罕见但存在

`shared_ptr` 在引擎中只有极少数合理场景：

**1. 异步加载**：IO 线程和主线程需要同时持有加载中的资源。
**2. 不可变资产共享**：多个 Material 引用同一个 Shader（Shader 只读）。`shared_ptr<const Shader>`。
**3. 跨系统的观察者**：多个系统需要知道某个资源还活着，但不独占。

### shared_ptr 的真实开销

```
sizeof(shared_ptr<T>) = 2 × sizeof(T*)  (16 bytes on 64-bit)
                      = 指针 + 控制块指针

控制块分配：
  make_shared → 对象 + 控制块 合并分配（1 次 malloc）
  shared_ptr(new T) → 2 次独立分配（对象 + 控制块）

引用计数操作：
  拷贝 → 原子递增     (~5-10ns)
  析构 → 原子递减     (~5-10ns)
  移动 → 无原子操作   (零额外开销)
```

**引擎约束**：在每帧预算 16.6ms 内，如果你在 `O(N)` 循环中拷贝 `shared_ptr`（N=10,000 对象），仅引用计数就吃掉 100us——这还没算实际工作。热路径上绝对避免。

### weak_ptr：打破循环、安全观察

在引擎树结构（Transform 层级、Scene Graph）中，parent 拥有 child（`unique_ptr` 或 `shared_ptr`），child 需要引用 parent 但不应阻止 parent 销毁 → `weak_ptr`。

```cpp
struct SceneNode : std::enable_shared_from_this<SceneNode> {
    std::weak_ptr<SceneNode> parent_;               // 不阻止 parent 销毁
    std::vector<std::shared_ptr<SceneNode>> children_;
};
```

`weak_ptr::lock()` 原子地检查 `use_count > 0`，是则将计数 +1 返回有效的 `shared_ptr`，否则返回空。这个过程是线程安全的。

### 侵入式引用计数

当 `shared_ptr` 的双分配和原子开销不可接受时，侵入式引用计数是游戏引擎的标准替代：

```cpp
class RefCounted {
    mutable std::atomic<int> ref_count_{0};
public:
    void add_ref() const { ref_count_.fetch_add(1, std::memory_order_relaxed); }
    void release() const {
        if (ref_count_.fetch_sub(1, std::memory_order_acq_rel) == 1)
            delete this;
    }
    int ref_count() const { return ref_count_.load(std::memory_order_relaxed); }
};
```

对比 `shared_ptr`：

| | `shared_ptr<T>` | 侵入式 RefCounted |
|:--|:---------------|:------------------|
| 内存分配 | 至少 1 次（控制块） | 0 次（计数在对象内） |
| 对象大小 | `sizeof(T) + sizeof(control_block)` | `sizeof(T) + sizeof(atomic<int>)` |
| 从 `this` 获取智能指针 | 需要 `enable_shared_from_this` | 天然支持 |
| 弱引用支持 | `weak_ptr`（额外弱计数） | 需手动实现或放弃 |
| 类型安全 | 模板保证 | 需基类，易误用 |

Unreal Engine 的 `UObject` 和 Godot 的 `RefCounted` 都使用侵入式引用计数。

### make_unique / make_shared 的重要性

```cpp
// 异常不安全：如果 bar() 抛异常，new Foo 泄漏
process(std::unique_ptr<Foo>(new Foo), bar());

// 安全：make_unique 是单表达式，无泄漏窗口
process(std::make_unique<Foo>(), bar());
```

`make_shared` 还有额外优势：单次分配对象 + 控制块，减少一次 malloc 和更好的缓存局部性。

---

## 2. 代码示例

### 示例 1: unique_ptr 管理的 GPU 资源管理器

```cpp
// compile: g++ -std=c++20 -O2 gpu_resource_manager.cpp -o gpu_resource_manager
#include <iostream>
#include <memory>
#include <vector>
#include <cassert>
#include <cstring>

// ============ 模拟 GPU API ============
using GLuint = unsigned int;
GLuint mock_glCreateTexture() {
    static GLuint next = 1;
    std::cout << "  [GPU] glCreateTexture → ID=" << next << "\n";
    return next++;
}
void mock_glDeleteTexture(GLuint id) {
    std::cout << "  [GPU] glDeleteTexture ID=" << id << "\n";
}
void mock_glBindTexture(GLuint id) {
    std::cout << "  [GPU] glBindTexture ID=" << id << "\n";
}

// ============ 零开销 GPU 删除器 ============
struct GLTextureDeleter {
    void operator()(GLuint* id) const noexcept {
        if (id && *id) {
            mock_glDeleteTexture(*id);
        }
        delete id;
    }
};

// 类型别名：GPU 纹理句柄
using GLTextureHandle = std::unique_ptr<GLuint, GLTextureDeleter>;

// 工厂函数
GLTextureHandle make_texture() {
    auto* id = new GLuint{mock_glCreateTexture()};
    return GLTextureHandle{id};
}

// ============ GPU Buffer（VBO/IBO）— 用无捕获 lambda ============
auto make_gpu_buffer(size_t size, const void* data) {
    // C++20: 无捕获 lambda 可默认构造 → 零开销删除器
    auto deleter = [](char* ptr) {
        std::cout << "  [GPU] Destroying buffer\n";
        delete[] ptr;
    };
    auto* buf = new char[size];
    std::memcpy(buf, data, size);
    return std::unique_ptr<char[], decltype(deleter)>(buf, deleter);
}

// ============ GPU 资源管理器 ============
class GPUResourceManager {
public:
    GLTextureHandle create_texture() {
        return make_texture();
    }

    // 转移所有权：调用方获取独占所有权
    void register_texture(GLTextureHandle tex) {
        textures_.push_back(std::move(tex));
    }

    void bind_and_draw(size_t index) {
        if (index < textures_.size() && textures_[index]) {
            mock_glBindTexture(*textures_[index]);
        }
    }

    void release_all() {
        std::cout << "\n[ResourceManager] Releasing all textures...\n";
        textures_.clear();  // 每个 unique_ptr 析构调用 glDeleteTexture
    }

    size_t texture_count() const { return textures_.size(); }

private:
    std::vector<GLTextureHandle> textures_;
};

int main() {
    GPUResourceManager manager;

    // 创建纹理 — 所有权在 manager
    auto tex1 = manager.create_texture();  // ID=1
    auto tex2 = manager.create_texture();  // ID=2

    manager.register_texture(std::move(tex1));
    manager.register_texture(std::move(tex2));

    std::cout << "Textures registered: " << manager.texture_count() << "\n";
    manager.bind_and_draw(0);

    // 转移所有权出去
    {
        auto tex3 = manager.create_texture();  // ID=3
        // tex3 离开作用域 → 自动 glDeleteTexture(3)
        std::cout << "\n--- tex3 going out of scope ---\n";
    }

    // GPU Buffer 演示
    float vertices[] = {0.0f, 0.5f, 1.0f, -0.5f, -0.5f, 0.0f};
    auto vbo = make_gpu_buffer(sizeof(vertices), vertices);

    manager.release_all();  // 手动释放 ID=1, ID=2
    std::cout << "All resources cleaned up.\n";

    return 0;
}
```

### 示例 2: 侵入式引用计数

```cpp
// compile: g++ -std=c++20 -O2 intrusive_ptr.cpp -o intrusive_ptr
#include <iostream>
#include <atomic>
#include <cassert>

// ============ 侵入式引用计数基类 ============
class RefCounted {
public:
    RefCounted() : ref_count_(0) {}
    virtual ~RefCounted() = default;

    void add_ref() const noexcept {
        ref_count_.fetch_add(1, std::memory_order_relaxed);
    }

    void release() const noexcept {
        if (ref_count_.fetch_sub(1, std::memory_order_acq_rel) == 1) {
            delete this;
        }
    }

    int use_count() const noexcept {
        return ref_count_.load(std::memory_order_relaxed);
    }

    RefCounted(const RefCounted&) = delete;
    RefCounted& operator=(const RefCounted&) = delete;

private:
    mutable std::atomic<int> ref_count_;
};

// ============ 侵入式智能指针 ============
template<typename T>
class IntrusivePtr {
    static_assert(std::is_base_of_v<RefCounted, T>,
                  "T must derive from RefCounted");

public:
    IntrusivePtr() noexcept : ptr_(nullptr) {}

    explicit IntrusivePtr(T* p) noexcept : ptr_(p) {
        if (ptr_) ptr_->add_ref();
    }

    IntrusivePtr(const IntrusivePtr& other) noexcept : ptr_(other.ptr_) {
        if (ptr_) ptr_->add_ref();
    }

    IntrusivePtr(IntrusivePtr&& other) noexcept : ptr_(other.ptr_) {
        other.ptr_ = nullptr;
    }

    ~IntrusivePtr() {
        if (ptr_) ptr_->release();
    }

    IntrusivePtr& operator=(const IntrusivePtr& other) noexcept {
        if (this != &other) {
            if (ptr_) ptr_->release();
            ptr_ = other.ptr_;
            if (ptr_) ptr_->add_ref();
        }
        return *this;
    }

    IntrusivePtr& operator=(IntrusivePtr&& other) noexcept {
        if (this != &other) {
            if (ptr_) ptr_->release();
            ptr_ = other.ptr_;
            other.ptr_ = nullptr;
        }
        return *this;
    }

    T* get() const noexcept { return ptr_; }
    T& operator*() const noexcept { return *ptr_; }
    T* operator->() const noexcept { return ptr_; }
    explicit operator bool() const noexcept { return ptr_ != nullptr; }

    int use_count() const noexcept {
        return ptr_ ? ptr_->use_count() : 0;
    }

private:
    T* ptr_;
};

// ============ 引擎资源示例 ============
class Shader : public RefCounted {
public:
    explicit Shader(const char* name) : name_(name) {
        std::cout << "  Shader(\"" << name_ << "\") constructed\n";
    }
    ~Shader() override {
        std::cout << "  Shader(\"" << name_ << "\") destroyed\n";
    }
    void bind() const {
        std::cout << "  Binding shader \"" << name_ << "\"\n";
    }
private:
    std::string name_;
};

class Material {
public:
    Material(IntrusivePtr<Shader> shader) : shader_(std::move(shader)) {}
    void render() const { shader_->bind(); }
private:
    IntrusivePtr<Shader> shader_;
};

int main() {
    // 创建一个 Shader，初始引用计数 0（刚构造完还没 add_ref）
    auto* shader = new Shader("PBR");
    // 包装进 IntrusivePtr → add_ref → ref_count = 1
    IntrusivePtr<Shader> shader_ptr(shader);

    std::cout << "ref count after create: " << shader_ptr.use_count() << "\n";

    {
        Material mat1(shader_ptr);
        std::cout << "ref count after mat1: " << shader_ptr.use_count() << "\n";

        Material mat2(shader_ptr);
        std::cout << "ref count after mat2: " << shader_ptr.use_count() << "\n";
        // mat2 析构 → release → ref_count = 2
    }
    std::cout << "ref count after mat2 destroyed: " << shader_ptr.use_count() << "\n";
    // shader_ptr 析构 → release → ref_count = 0 → delete shader

    return 0;
}
```

### 示例 3: shared_ptr 开销实测

```cpp
// compile: g++ -std=c++20 -O2 shared_ptr_overhead.cpp -o shared_ptr_overhead
#include <iostream>
#include <memory>
#include <chrono>

struct SmallObject {
    int value;
    SmallObject(int v = 0) : value(v) {}
};

int main() {
    constexpr int N = 10'000'000;

    // === 创建开销: make_shared vs new + shared_ptr ===
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            auto sp = std::make_shared<SmallObject>(i);
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        std::cout << "make_shared x " << N << ": " << us << "us ("
                  << (double)us / N * 1000 << "ns each)\n";
    }

    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            std::shared_ptr<SmallObject> sp(new SmallObject(i));
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        std::cout << "shared_ptr(new) x " << N << ": " << us << "us ("
                  << (double)us / N * 1000 << "ns each)\n";
    }

    // === 拷贝开销 ===
    auto sp = std::make_shared<SmallObject>(42);
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            auto copy = sp;  // 原子递增
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        std::cout << "shared_ptr copy x " << N << ": " << us << "us ("
                  << (double)us / N * 1000 << "ns each)\n";
    }

    // === 移动开销（零原子操作！）===
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int i = 0; i < N; ++i) {
            auto moved = std::move(sp);
            sp = std::move(moved);
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
        std::cout << "shared_ptr move x " << N << ": " << us << "us ("
                  << (double)us / N * 1000 << "ns each)\n";
    }

    // === sizeof 对比 ===
    std::cout << "\nsizeof(void*):              " << sizeof(void*) << "\n";
    std::cout << "sizeof(unique_ptr<int>):    " << sizeof(std::unique_ptr<int>) << "\n";
    std::cout << "sizeof(shared_ptr<int>):    " << sizeof(std::shared_ptr<int>) << " (2 pointers!)\n";
    std::cout << "sizeof(weak_ptr<int>):      " << sizeof(std::weak_ptr<int>) << "\n";

    return 0;
}
```

### 示例 4: weak_ptr 打破循环引用 + 引擎场景图

```cpp
// compile: g++ -std=c++20 -O2 weak_ptr_scene.cpp -o weak_ptr_scene
#include <iostream>
#include <memory>
#include <vector>
#include <string>

class SceneNode : public std::enable_shared_from_this<SceneNode> {
public:
    explicit SceneNode(std::string name) : name_(std::move(name)) {
        std::cout << "+ Node \"" << name_ << "\"\n";
    }
    ~SceneNode() {
        std::cout << "- Node \"" << name_ << "\"\n";
    }

    void add_child(std::shared_ptr<SceneNode> child) {
        child->parent_ = shared_from_this();  // weak_ptr → 不阻止 parent 析构
        children_.push_back(std::move(child));
    }

    void print_hierarchy(int depth = 0) const {
        std::cout << std::string(depth * 2, ' ') << name_;
        if (auto p = parent_.lock()) {
            std::cout << " (parent: " << p->name_ << ")";
        }
        std::cout << "\n";
        for (auto& c : children_)
            c->print_hierarchy(depth + 1);
    }

    const std::string& name() const { return name_; }

private:
    std::string name_;
    std::weak_ptr<SceneNode> parent_;                 // 关键：弱引用
    std::vector<std::shared_ptr<SceneNode>> children_; // 强引用
};

int main() {
    auto root = std::make_shared<SceneNode>("Root");
    auto child1 = std::make_shared<SceneNode>("Child1");
    auto child2 = std::make_shared<SceneNode>("Child2");
    auto grandchild = std::make_shared<SceneNode>("GrandChild");

    root->add_child(child1);
    root->add_child(child2);
    child1->add_child(grandchild);

    std::cout << "\n--- Hierarchy ---\n";
    root->print_hierarchy();

    std::cout << "\n--- Remove child1 (detaches subtree) ---\n";
    // 从 root 移除 child1 → root 不再持有 child1 的 shared_ptr
    // child1 的 parent_ 是 weak_ptr → 不阻止析构
    // grandchild 被 child1 的 children_ 持有 → 一起析构
    // 但这里为了简洁，我们直接让 root 重置来演示完整析构
    root.reset();
    std::cout << "Root released. All nodes should be destroyed.\n";

    return 0;
}
```

---

## 3. 练习

### 练习 1: GPU 资源缓存（必做）

设计一个 `GPUTextureCache` 类，满足：

1. 内部用 `std::unordered_map<std::string, std::unique_ptr<Texture, CustomDeleter>>` 存储纹理
2. `load(path)` — 如果缓存中有则返回裸指针（不转移所有权），否则加载并存储
3. `evict(path)` — 从缓存中移除并释放 GPU 内存
4. `evict_unused()` — 通过引用计数或时间戳机制剔除不活跃纹理（提示：可以用 `weak_ptr` 做观察，或简单的 LRU）
5. 所有纹理使用自定义删除器（调用模拟的 `glDeleteTexture`）

**要求**：在 `main` 中验证：加载相同路径两次只分配一次 GPU 纹理；`evict` 后资源被释放；`evict_unused` 正确剔除。

### 练习 2: 选择正确的智能指针（必做）

为以下每个引擎场景选择最合适的智能指针（或裸指针），并写一句话解释理由：

1. **Transform 组件** — `Entity` 独占拥有它的 `Transform`
2. **Shader 资产** — 100 个 `Material` 实例引用同一个 `Shader`，Shader 不可变
3. **物理世界引用** — `RigidBody` 需要引用 `PhysicsWorld`，但 `PhysicsWorld` 的生命周期比所有 `RigidBody` 都长
4. **异步加载回调** — IO 线程和主线程都需要访问正在加载的 `Mesh`
5. **Scene Graph 双向链接** — 父节点拥有子节点，子节点需要回访父节点
6. **帧临时渲染命令** — `RenderCommand` 在帧内分配，帧结束时整体销毁

用代码片段演示每种情况（类型声明即可，不需要完整实现）。

### 练习 3: 实现一个完整的侵入式 shared_ptr + weak_ptr（可选挑战）

扩充上面的 `IntrusivePtr` 实现，加入 `IntrusiveWeakPtr`：

1. `RefCounted` 需要额外的 `weak_count`（原子整数）
2. 当 `ref_count == 0` 时销毁对象，但控制块保留直到 `weak_count == 0`
3. `IntrusiveWeakPtr::lock()` 原子地检查 ref_count 并提升为 `IntrusivePtr`
4. 实现 `IntrusivePtr<T>` 可以从 `IntrusiveWeakPtr<T>` 构造（需要 `lock()`）

**提示**：参考 `std::shared_ptr` / `std::weak_ptr` 的设计，但把所有计数内嵌在对象中。关键挑战：当 `ref_count == 0` 时对象被析构但内存不能立即释放——weak_ptr 还需要访问 weak_count。解决方案是用一个分离的 control block，或者在 `RefCounted` 中用 placement delete 延迟释放。

---

## 4. 扩展阅读

- **深度探索**: `docs/deep-dives/cpp-smart-pointers.md` — 849 行完整分析
- **cppreference**: [std::unique_ptr](https://en.cppreference.com/w/cpp/memory/unique_ptr), [std::shared_ptr](https://en.cppreference.com/w/cpp/memory/shared_ptr)
- **Scott Meyers**: *Effective Modern C++*, Item 18-22 — 智能指针专项
- **Herb Sutter**: [GotW #91](https://herbsutter.com/2013/06/05/gotw-91-solution-smart-pointer-parameters/) — 智能指针参数传递指南
- **引擎参考**: [Unreal Engine TUniquePtr](https://docs.unrealengine.com/), [Godot Ref<T>](https://github.com/godotengine/godot/blob/master/core/object/ref_counted.h)

---

## 常见陷阱

### 陷阱 1: 对 GPU 资源使用默认删除器

```cpp
// 错误 — 永远不会调用 glDeleteTextures
std::unique_ptr<GLuint> texture(new GLuint{glCreateTexture()});
// texture 析构 → delete (GLuint*) → 未定义行为，GPU 资源泄漏
```

`GLuint` 不是通过 `new` 分配的堆对象，而且 `delete` 不会通知 GPU 驱动释放纹理。必须使用自定义删除器调用 `glDeleteTextures`。

### 陷阱 2: 在头文件中暴露 shared_ptr 作为热路径接口

```cpp
// 错误 — 每个调用方被迫原子递增引用计数
class Renderer {
public:
    std::shared_ptr<Shader> get_shader(const char* name);
    // 调用方只需要"使用" Shader，不需要"共享所有权"
};
```

**正确做法**：
```cpp
class Renderer {
public:
    Shader* get_shader(const char* name);  // 裸指针 — 调用方不获取所有权
    // 或 const Shader& 返回值
};
```

热路径上用裸指针/引用传递。`shared_ptr` 只在需要延长生命周期的地方（异步回调、长期持有）创建临时拷贝。

### 陷阱 3: 在容器中使用 `shared_ptr` 导致隐式的 N×M 原子操作

```cpp
// 如果每个粒子持有一个 shared_ptr<Material>
std::vector<std::shared_ptr<Material>> particle_materials;  // 100,000 个
// 每次 resize/reallocation → 100,000 次原子递增
```

**解决方案**：用 `unique_ptr<Material>` 或直接用值语义（小对象）或句柄系统（`uint32_t MaterialID`）。

### 陷阱 4: 从 `this` 直接创建 `shared_ptr`

```cpp
struct Node {
    std::shared_ptr<Node> get_shared() {
        return std::shared_ptr<Node>(this);  // 致命错误！
        // 如果 this 已被另一个 shared_ptr 管理 → 两个独立的 control block
        // → 双重删除！
    }
};
```

**正确做法**：继承 `std::enable_shared_from_this<Node>`，使用 `shared_from_this()`。

### 陷阱 5: 忘记 `make_unique` / `make_shared` 的异常安全优势

```cpp
// 异常不安全
process(std::unique_ptr<Foo>(new Foo), bar());
// 编译器可能先执行 new Foo，再执行 bar()
// 如果 bar() 抛异常 → new Foo 泄漏

// 安全
process(std::make_unique<Foo>(), bar());
// make_unique 的返回值和 bar() 的求值之间没有泄漏窗口
```
