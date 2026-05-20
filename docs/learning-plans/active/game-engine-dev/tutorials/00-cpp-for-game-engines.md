# C++ 引擎编程：语言特性精要

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: C++ 基础语法（类、继承、模板基础）、操作系统基础

---

## 1. 为什么游戏引擎需要"特殊"的 C++ 知识

游戏引擎是 C++ 最具挑战性的应用领域之一。与其他 C++ 项目相比，引擎开发有独特约束：

| 约束 | 对 C++ 的要求 |
|------|-------------|
| **确定性帧时间** (16.6ms @ 60FPS) | 禁止 GC 暂停，需要精确的 RAII 和手动内存控制 |
| **零开销抽象** | 虚函数开销在热路径不可接受，需要静态多态和编译期派发 |
| **多核并行** | Job System 需要深入理解内存序、原子操作和缓存一致性 |
| **硬件亲和** | SIMD 对齐、缓存行大小、DMA 对齐需要用语言特性精确控制 |
| **跨平台** | 条件编译、平台抽象需要模板和宏的审慎配合 |
| **大规模代码库** | 编译时间敏感，需要权衡模板元编程的使用深度 |

本章不是 C++ 入门教程。它聚焦**引擎开发中高频使用、容易误用、且对性能有显著影响**的语言特性。如果你已经掌握 C++ 基础，本章帮你建立"引擎视角"；如果你发现某些概念陌生，建议先补充相应基础。

---

## 2. RAII：引擎资源管理的基石

### 2.1 核心思想

**RAII (Resource Acquisition Is Initialization)**：资源的生命周期与对象的生命周期绑定，在构造函数中获取资源，在析构函数中释放资源。

```cpp
// 引擎中典型的 RAII 封装
class GLBuffer {
public:
    explicit GLBuffer(size_t size, const void* data) {
        glGenBuffers(1, &id_);
        glBindBuffer(GL_ARRAY_BUFFER, id_);
        glBufferData(GL_ARRAY_BUFFER, size, data, GL_STATIC_DRAW);
    }

    // 禁止拷贝：GPU 资源不能被"复制"
    GLBuffer(const GLBuffer&) = delete;
    GLBuffer& operator=(const GLBuffer&) = delete;

    // 移动语义：转移 GPU 资源所有权（第 3 节详解）
    GLBuffer(GLBuffer&& other) noexcept : id_(other.id_) {
        other.id_ = 0;  // 置空源对象，防止双重释放
    }

    ~GLBuffer() {
        if (id_ != 0) {
            glDeleteBuffers(1, &id_);
        }
    }

    GLuint id() const { return id_; }

private:
    GLuint id_ = 0;
};
```

**为什么引擎中 RAII 比垃圾回收更关键：**

- **确定性销毁**：GPU 纹理、音频缓冲、文件句柄必须在精确时机释放，不能等 GC "决定"
- **异常安全**：即使中途抛出异常，栈展开也会调用析构函数，不会泄漏资源
- **性能可预测**：没有 GC 带来的世界停顿（stop-the-world）

### 2.2 Rule of Zero / Rule of Five

引擎类管理资源时，必须明确声明拷贝和移动语义：

```cpp
// Rule of Five：如果定义了其中一个，通常需要定义全部五个
class Mesh {
public:
    Mesh(const Vertex* vertices, size_t count);           // 构造函数
    ~Mesh();                                               // 析构函数

    Mesh(const Mesh& other);                               // 拷贝构造
    Mesh& operator=(const Mesh& other);                    // 拷贝赋值

    Mesh(Mesh&& other) noexcept;                           // 移动构造
    Mesh& operator=(Mesh&& other) noexcept;                // 移动赋值

private:
    Vertex* vertices_;
    size_t vertexCount_;
    GLuint vao_, vbo_;
};
```

**引擎中的黄金法则：**

| 规则 | 适用场景 |
|------|---------|
| **Rule of Zero** | 类只包含值语义成员（如 `std::vector`, `std::string`, `std::unique_ptr`），让编译器自动生成所有特殊函数 |
| **Rule of Five** | 类管理原始资源（裸指针、文件描述符、GPU ID），必须手动定义或删除所有五个特殊函数 |
| **Delete Copy** | 几乎所有引擎资源类都应删除拷贝（GPU 资源、窗口句柄、音频设备） |
| **Noexcept Move** | 移动操作标记 `noexcept`，否则 `std::vector` 扩容时会用拷贝而非移动 |

```cpp
// 更现代的写法：用 unique_ptr 管理原始资源，回归 Rule of Zero
class ModernMesh {
public:
    ModernMesh(const Vertex* vertices, size_t count);
    // 编译器自动生成：析构、拷贝、移动——全部正确！
    // 因为 unique_ptr 已经正确处理了这些语义

private:
    std::unique_ptr<Vertex[]> vertices_;
    size_t vertexCount_;
    std::unique_ptr<GLBuffer, GLBufferDeleter> buffer_;
};
```

### 2.3 异常处理策略：引擎中的工程决策

#### 为什么主流游戏引擎禁用异常？

现代编译器（GCC、Clang、MSVC x64）实现了**零成本异常模型**——不抛出异常时没有运行时开销。但引擎开发者仍然倾向于禁用异常（`-fno-exceptions` / `/EHs-`）：

| 原因 | 说明 |
|------|------|
| **二进制体积** | unwind 表和异常处理元数据可使可执行文件增加 **~10-19%** |
| **缓存压力** | 更大的二进制意味着更多的指令缓存未命中 |
| **确定性** | 16.6ms 帧预算内不能容忍隐藏的栈展开路径 |
| **主机兼容性** | 部分主机工具链历史上有异常支持问题 |
| **控制流透明** | 异常是隐式的非局部跳转，难以追踪和预测 |

**实测数据**（Release -O2）：
- 返回错误码路径：~11 ns
- throw/catch 异常路径：~1092 ns（约 **100 倍**差距）

```cpp
// 引擎中的典型做法：禁用异常，使用显式错误处理
class Result {
public:
    enum Code { Ok, FileNotFound, InvalidFormat, OutOfMemory };

    static Result success() { return Result{Ok, ""}; }
    static Result failure(Code code, const char* msg) { return Result{code, msg}; }

    bool isOk() const { return code_ == Ok; }
    Code code() const { return code_; }
    const char* message() const { return msg_; }

private:
    Result(Code c, const char* m) : code_(c), msg_(m) {}
    Code code_;
    const char* msg_;
};

// 使用：
Result loadTexture(const char* path, Texture& out) {
    FILE* file = fopen(path, "rb");
    if (!file) {
        return Result::failure(Result::FileNotFound, path);
    }
    // ... 加载逻辑 ...
    if (/* 格式错误 */) {
        fclose(file);
        return Result::failure(Result::InvalidFormat, "bad header");
    }
    out = /* 构造纹理 */;
    fclose(file);
    return Result::success();
}

// 调用方：
Texture tex;
Result r = loadTexture("player.png", tex);
if (!r.isOk()) {
    logError("Failed to load texture: %s", r.message());
    // 使用默认纹理或退出
}
```

#### C++23 std::expected（未来的标准方案）

```cpp
#include <expected>

std::expected<Texture, ErrorCode> loadTexture(const char* path) {
    FILE* file = fopen(path, "rb");
    if (!file) return std::unexpected(ErrorCode::FileNotFound);
    // ...
    return Texture{/* ... */};
}

// 调用：
auto result = loadTexture("player.png");
if (result) {
    Texture tex = *result;  // 解引用获取值
} else {
    ErrorCode err = result.error();
}
```

#### 构造函数中报告错误

禁用异常后，构造函数不能抛出。替代方案：

```cpp
// 方案 1：两段式初始化
class Mesh {
public:
    Mesh() = default;
    bool initialize(const Vertex* data, size_t count);  // 返回是否成功
    bool isValid() const;
};

// 方案 2：工厂函数
std::optional<Mesh> Mesh::create(const Vertex* data, size_t count) {
    Mesh mesh;
    if (!mesh.initialize(data, count)) {
        return std::nullopt;
    }
    return mesh;  // 移动语义保证无拷贝
}

// 方案 3：在引擎中最常见的做法——断言 + 不处理
// "如果资源加载失败，引擎不能继续运行，直接崩溃并报告"
class Mesh {
public:
    Mesh(const Vertex* data, size_t count) {
        bool ok = initInternal(data, count);
        assert(ok && "Mesh initialization failed");  // Debug 断点
        (void)ok;  // Release 下忽略
    }
};
```

#### `noexcept` 的使用策略

即使禁用异常，仍应标记 `noexcept`：

```cpp
// 标记 noexcept 告诉编译器和调用者：这个函数不会抛出
// 容器（vector）在知道移动构造是 noexcept 后会使用移动而非拷贝
class Buffer {
public:
    Buffer(Buffer&& other) noexcept;           // 必须标记
    Buffer& operator=(Buffer&& other) noexcept; // 必须标记
    void reset() noexcept;                     // 简单操作，不会失败
};

// 注意：noexcept 不是性能优化保证，而是契约工具
// 编译器可能利用它做优化，但主要价值是接口设计
```

**引擎中的黄金法则：**
- **热路径函数**：标记 `noexcept`，使用断言处理"不可能"的错误
- **资源加载函数**：返回 `Result` / `std::optional` / 布尔值
- **工具代码**（编辑器、离线工具）：可以用异常，简化错误处理

---

## 3. 移动语义：消除不必要的拷贝

### 3.1 值类别速查

```cpp
int x = 42;              // x 是左值（有名字，可取地址）
int& getLValue();        // 返回左值引用
int&& getRValue();       // 返回右值引用（将亡值）

// 右值：字面量、临时对象、std::move 的结果
42;                       // 纯右值
std::move(x);             // 将亡值（x 转成了右值引用）
getLValue();              // 左值（有名字的引用）
```

**引擎中的关键区别**：返回一个大对象（如网格数据、渲染命令列表）时，移动语义避免拷贝兆字节级的数据。

### 3.2 移动构造函数与移动赋值

```cpp
class RenderCommandList {
public:
    RenderCommandList() = default;

    // 拷贝：深拷贝所有命令（昂贵！）
    RenderCommandList(const RenderCommandList& other)
        : commands_(other.commands_)
        , capacity_(other.capacity_)
        , count_(other.count_) {}

    // 移动：窃取资源（廉价）
    RenderCommandList(RenderCommandList&& other) noexcept
        : commands_(other.commands_)      // 偷走指针
        , capacity_(other.capacity_)
        , count_(other.count_) {
        other.commands_ = nullptr;         // 置空源对象
        other.capacity_ = 0;
        other.count_ = 0;
    }

    RenderCommandList& operator=(RenderCommandList&& other) noexcept {
        if (this != &other) {
            delete[] commands_;            // 释放自己的资源
            commands_ = other.commands_;    // 偷走
            capacity_ = other.capacity_;
            count_ = other.count_;
            other.commands_ = nullptr;      // 置空源对象
            other.capacity_ = 0;
            other.count_ = 0;
        }
        return *this;
    }

    ~RenderCommandList() { delete[] commands_; }

private:
    RenderCommand* commands_ = nullptr;
    size_t capacity_ = 0;
    size_t count_ = 0;
};
```

**`noexcept` 为什么重要：**

```cpp
std::vector<RenderCommandList> lists;
lists.reserve(100);
for (int i = 0; i < 100; ++i) {
    RenderCommandList list = buildCommands(i);  // 临时对象（右值）
    lists.push_back(std::move(list));            // 移动构造
}

// 当 vector 需要扩容时：
// 如果移动构造是 noexcept → vector 用移动，O(1) 每个元素
// 如果移动构造不是 noexcept → vector 回退到拷贝，O(n) 每个元素
// 在引擎中，这可能意味着拷贝数万条渲染命令
```

### 3.3 完美转发与万能引用

```cpp
// 万能引用（Universal Reference）：T&& 在模板推导中既能绑定左值也能绑定右值
template<typename T>
void wrapper(T&& arg) {
    // std::forward<T>：保持 arg 的值类别
    // 如果 arg 是左值，转发为左值引用
    // 如果 arg 是右值，转发为右值引用
    process(std::forward<T>(arg));
}

// 引擎中的应用：工厂函数
template<typename T, typename... Args>
std::unique_ptr<T> makeResource(Args&&... args) {
    // 完美转发构造参数到 T 的构造函数
    return std::unique_ptr<T>(new T(std::forward<Args>(args)...));
}

// 使用：
auto mesh = makeResource<Mesh>(vertices, count);  // Mesh(vertices, count)
auto copy = makeResource<Mesh>(otherMesh);        // Mesh(const Mesh&) — 拷贝
auto moved = makeResource<Mesh>(std::move(temp)); // Mesh(Mesh&&) — 移动
```

**折叠规则速查：**

| 模板参数 T | 实参类型 | T&& 推导为 | std::forward<T> 结果 |
|-----------|---------|-----------|---------------------|
| `int&` | 左值 `int` | `int&` | `int&` |
| `int` | 右值 `int` | `int&&` | `int&&` |
| `const int&` | const 左值 | `const int&` | `const int&` |

### 3.4 引擎中的移动语义实践

```cpp
// 场景：资源加载线程加载完成后，把数据交给渲染线程
class TextureData {
public:
    TextureData(size_t width, size_t height, std::vector<uint8_t> pixels)
        : width_(width), height_(height), pixels_(std::move(pixels)) {}
        // pixels 是函数的参数（左值），但用 std::move 转为右值
        // 触发 vector 的移动构造，避免拷贝整个图像数据

    TextureData(TextureData&&) = default;
    TextureData& operator=(TextureData&&) = default;

private:
    size_t width_, height_;
    std::vector<uint8_t> pixels_;  // 可能几十 MB 的图像数据
};

// 加载线程
TextureData loadTexture(const std::string& path) {
    std::vector<uint8_t> rawData = readFile(path);  // 读取原始数据
    decodeImage(rawData);                            // 解码
    return TextureData(width, height, std::move(rawData));
    // NRVO / 移动语义保证这里没有拷贝
}

// 主线程
TextureData tex = loadTexture("player_diffuse.png");  // 直接构造，无拷贝
```

---

## 4. 智能指针策略：引擎中的取舍

### 4.1 引擎中的所有权哲学

游戏引擎中，**所有权必须清晰、显式、可追踪**。智能指针是工具，不是万能药。

```cpp
// 原则 1：默认使用 unique_ptr 表示独占所有权
std::unique_ptr<Renderer> renderer = std::make_unique<Renderer>();

// 原则 2：需要共享所有权时，明确说明为什么
// （在引擎中，共享所有权通常是设计缺陷的信号）
std::shared_ptr<Texture> sharedTex;  // 为什么需要共享？是否可以用句柄替代？
```

### 4.2 unique_ptr：引擎中的默认选择

```cpp
class Scene {
public:
    void addMesh(std::unique_ptr<Mesh> mesh) {
        meshes_.push_back(std::move(mesh));
    }

    std::unique_ptr<Mesh> removeMesh(size_t index) {
        std::unique_ptr<Mesh> removed = std::move(meshes_[index]);
        meshes_.erase(meshes_.begin() + index);
        return removed;  // 移动返回，不拷贝
    }

private:
    std::vector<std::unique_ptr<Mesh>> meshes_;
};

// 使用自定义删除器管理 GPU 资源
struct GLBufferDeleter {
    void operator()(GLuint* buffer) const {
        glDeleteBuffers(1, buffer);
        delete buffer;
    }
};
using GLBufferPtr = std::unique_ptr<GLuint, GLBufferDeleter>;
```

### 4.3 shared_ptr 的陷阱

```cpp
// 陷阱 1：引用计数的原子操作开销
void processEntities(const std::vector<std::shared_ptr<Entity>>& entities) {
    for (const auto& e : entities) {
        e->update();  // 每次循环都原子递增/递减引用计数！
    }
}

// 修复：用原始指针或引用遍历
void processEntitiesBetter(const std::vector<std::shared_ptr<Entity>>& entities) {
    for (const auto& e : entities) {
        Entity* raw = e.get();  // 获取原始指针，无原子操作
        raw->update();
    }
}

// 更好的修复：引擎中避免 shared_ptr 表示实体关系
// 用句柄系统替代：
struct EntityHandle {
    uint32_t index;
    uint32_t generation;
};
```

**shared_ptr 在引擎中的合理使用场景：**

| 场景 | 理由 |
|------|------|
| 工具代码（编辑器、调试器） | 工具代码不需要极致性能，shared_ptr 简化生命周期管理 |
| 异步加载的资源 | 加载线程和主线程可能同时引用资源 |
| 共享的着色器/材质 | 多个材质共享同一个 shader 程序 |
| 第三方库接口 | 某些库返回 shared_ptr，保持一致性 |

### 4.4 weak_ptr：打破循环引用

```cpp
class Entity;
class Component {
public:
    // Component 不拥有 Entity，只是观察
    std::weak_ptr<Entity> owner;
};

class Entity {
public:
    std::vector<std::shared_ptr<Component>> components;
};

// 使用：
void Component::onUpdate() {
    if (auto e = owner.lock()) {  // 尝试提升为 shared_ptr
        // Entity 仍然存在
        auto pos = e->transform.position;
    } else {
        // Entity 已被销毁
    }
}
```

**引擎中的替代方案：原始指针 + 显式生命周期管理**：

```cpp
// ECS 架构中更常见的做法：Component 存实体 ID，不存指针
struct TransformComponent {
    EntityID entityId;  // 只是一个 uint32_t
    Vector3 position;
    Quaternion rotation;
};

// 系统遍历时不涉及任何指针操作，纯粹的数组遍历
class TransformSystem : public System {
public:
    void update(float dt) {
        auto& transforms = registry_->getComponents<TransformComponent>();
        for (auto& t : transforms) {
            // 直接访问，无间接寻址，缓存友好
            t.position += velocities[t.entityId] * dt;
        }
    }
};
```

---

## 5. placement new 与对齐分配

### 5.1 placement new：在预分配内存上构造对象

```cpp
// 普通 new：分配内存 + 构造对象
T* ptr = new T(args);   // 1. operator new(sizeof(T))  2. T::T(args)

// placement new：只在已有内存上构造对象
char buffer[sizeof(T)];
T* ptr = new (buffer) T(args);  // 只调用构造函数，不分配内存

// 显式调用析构函数（placement new 的对象不能用 delete！）
ptr->~T();
```

**引擎中的应用：池分配器**：

```cpp
template<typename T>
class ObjectPool {
public:
    explicit ObjectPool(size_t capacity) {
        // 一次性分配原始内存（不构造对象）
        memory_ = static_cast<std::byte*>(
            ::operator new[](sizeof(T) * capacity, std::align_val_t{alignof(T)})
        );
        capacity_ = capacity;
        freeCount_ = capacity;

        // 初始化自由列表
        for (size_t i = 0; i < capacity; ++i) {
            T* slot = reinterpret_cast<T*>(memory_ + i * sizeof(T));
            *reinterpret_cast<T**>(slot) = (i == capacity - 1)
                ? nullptr
                : reinterpret_cast<T*>(memory_ + (i + 1) * sizeof(T));
        }
        freeList_ = reinterpret_cast<T*>(memory_);
    }

    ~ObjectPool() {
        // 注意：如果还有存活对象，这里不会调用析构函数
        // 生产代码需要断言或处理
        ::operator delete[](memory_, std::align_val_t{alignof(T)});
    }

    template<typename... Args>
    T* acquire(Args&&... args) {
        if (!freeList_) return nullptr;

        T* slot = freeList_;
        freeList_ = *reinterpret_cast<T**>(slot);
        --freeCount_;

        // placement new：在预分配的内存上构造对象
        new (slot) T(std::forward<Args>(args)...);
        return slot;
    }

    void release(T* obj) {
        if (!obj) return;

        // 显式调用析构函数
        obj->~T();

        // 归还到自由列表
        *reinterpret_cast<T**>(obj) = freeList_;
        freeList_ = obj;
        ++freeCount_;
    }

private:
    std::byte* memory_;
    T* freeList_ = nullptr;
    size_t capacity_ = 0;
    size_t freeCount_ = 0;
};
```

### 5.2 对齐分配（C++17）

```cpp
// C++17 之前：平台相关函数
// MSVC: _aligned_malloc(size, alignment)
// POSIX: posix_memalign(&ptr, alignment, size)

// C++17 标准对齐分配
void* aligned = ::operator new(size, std::align_val_t{64});  // 64 字节对齐
::operator delete(aligned, std::align_val_t{64});

// new 表达式也支持对齐
struct alignas(64) CacheLineData {
    float data[16];  // 64 字节
};

CacheLineData* arr = new CacheLineData[100];  // 每个元素 64 字节对齐
```

**引擎中的应用：SIMD 对齐**：

```cpp
// SSE/AVX 需要严格对齐
struct alignas(32) Vec8f {
    float data[8];  // 256 bit = 32 byte，AVX 对齐
};

// 动态分配 SIMD 友好的数组
template<typename T>
T* alignedAlloc(size_t count, size_t alignment = alignof(T)) {
    size_t bytes = count * sizeof(T);
    void* ptr = nullptr;

#if defined(_WIN32)
    ptr = _aligned_malloc(bytes, alignment);
#else
    posix_memalign(&ptr, alignment, bytes);
#endif

    return static_cast<T*>(ptr);
}

void alignedFree(void* ptr) {
#if defined(_WIN32)
    _aligned_free(ptr);
#else
    free(ptr);
#endif
}
```

### 5.3 对齐的陷阱

```cpp
// 陷阱：new[] 分配的内存，用普通 delete 释放
T* arr = new T[10];
delete arr;    // 未定义行为！必须用 delete[] arr;

// 陷阱 2：对齐的 new[] 与 delete[] 不匹配
struct alignas(64) BigAligned { int x; };
BigAligned* arr = new BigAligned[10];
delete[] arr;  // 正确

// 陷阱 3：placement new 的对象不能用 delete
char buffer[sizeof(T)];
T* ptr = new (buffer) T();
delete ptr;    // 灾难！delete 会尝试释放 buffer 的"内存"，而 buffer 在栈上

// 正确：显式析构
ptr->~T();
```

### 5.4 std::pmr：标准库的多态内存资源

C++17 引入了 `<memory_resource>`，让标准容器**无需修改模板参数**就能使用自定义分配器。这与引擎中已有的 Arena/Pool 分配器天然互补。

#### 核心组件

```cpp
#include <memory_resource>

// 1. monotonic_buffer_resource：线性分配器（Arena）的标准化
char buffer[1024 * 1024];  // 1MB 栈缓冲或预分配堆内存
std::pmr::monotonic_buffer_resource arena(buffer, sizeof(buffer));

// 2. 让标准容器使用 Arena
std::pmr::vector<RenderCommand> commands{&arena};
commands.reserve(1000);

// 3. 每帧填充命令
for (const auto& obj : visibleObjects) {
    commands.emplace_back(obj.mesh, obj.material);
}

// 4. 帧结束时重置 Arena，所有 commands 的析构不释放内存
arena.release();  // O(1) 重置，下一帧复用
```

#### 与自定义分配器的对比

| 特性 | 自定义 ArenaAllocator | std::pmr::monotonic_buffer_resource |
|------|----------------------|-------------------------------------|
| 接口 | 自定义 allocate/free | 标准 `std::pmr::memory_resource*` |
| 容器兼容 | 需自定义 vector/string | 直接用 `std::pmr::vector<T>` |
| 性能 | 完全可控 | 略多一层虚函数调用（可忽略） |
| 调试 | 自己实现统计 | 可用 `std::pmr::synchronized_pool_resource` |
| 跨模块 | 需自己定义接口 | 标准接口，第三方库可直接使用 |

#### 池分配器的标准版本

```cpp
// unsynchronized_pool_resource：线程不安全的池分配器
// 适合每个线程独立的分配场景
std::pmr::unsynchronized_pool_resource pool;

// 多个容器共享同一个池
std::pmr::vector<int> ints{&pool};
std::pmr::list<float> floats{&pool};

// pool 析构时释放所有内存
```

#### 自定义 memory_resource

```cpp
// 把引擎已有的 ArenaAllocator 包装成 std::pmr::memory_resource
class ArenaMemoryResource : public std::pmr::memory_resource {
public:
    explicit ArenaMemoryResource(ArenaAllocator* arena) : arena_(arena) {}

protected:
    void* do_allocate(size_t bytes, size_t alignment) override {
        return arena_->allocate(bytes, alignment);
    }

    void do_deallocate(void* p, size_t bytes, size_t alignment) override {
        // Arena 不支持单个释放，忽略
    }

    bool do_is_equal(const std::pmr::memory_resource& other) const noexcept override {
        return this == &other;
    }

private:
    ArenaAllocator* arena_;
};
```

**引擎中使用 std::pmr 的时机：**
- 工具代码和编辑器：需要快速开发，用 `std::pmr` 减少自定义容器工作
- 跨模块接口：第三方库要求 `std::pmr::memory_resource*`
- 原型阶段：用 `std::pmr` 快速验证分配策略，后续再手写优化版本

---

## 6. 模板元编程：编译期多态

### 6.1 引擎为什么需要模板元编程

| 需求 | 模板解决方案 |
|------|------------|
| 不同类型的组件数组（Transform、Mesh、Collider）共享同一套存储逻辑 | 模板化的 ComponentArray<T> |
| 系统遍历组件时根据类型选择遍历方式 | 类型特征（Type Traits） |
| 数学库中 Vector2/Vector3/Vector4 共享运算逻辑 | 表达式模板（Expression Templates） |
| 编译期计算查找表、哈希值 | constexpr 函数 |

### 6.2 类型特征（Type Traits）

```cpp
// 检查类型是否平凡可拷贝（决定能否用 memcpy）
template<typename T>
void copyComponentData(T* dst, const T* src, size_t count) {
    if constexpr (std::is_trivially_copyable_v<T>) {
        // 可以安全地用 memcpy，极快
        std::memcpy(dst, src, count * sizeof(T));
    } else {
        // 必须逐个拷贝构造
        for (size_t i = 0; i < count; ++i) {
            new (&dst[i]) T(src[i]);
        }
    }
}

// 检查类型是否 POD（Plain Old Data），用于 ECS 组件约束
template<typename T>
concept PODComponent = std::is_standard_layout_v<T> && std::is_trivially_copyable_v<T>;

// 编译期类型信息
static_assert(PODComponent<TransformComponent>);   // OK
// static_assert(PODComponent<std::string>);        // 编译错误
```

### 6.3 SFINAE：Substitution Failure Is Not An Error

```cpp
// C++11/14 的方式：用 SFINAE 启用/禁用模板函数

// 只对整数类型启用的序列化函数
template<typename T>
std::enable_if_t<std::is_integral_v<T>, void>
serialize(Buffer& buf, T value) {
    buf.write(&value, sizeof(T));
}

// 只对浮点类型启用的序列化函数
template<typename T>
std::enable_if_t<std::is_floating_point_v<T>, void>
serialize(Buffer& buf, T value) {
    // 处理浮点特殊值（NaN、Inf）
    buf.write(&value, sizeof(T));
}

// 引擎中的应用：根据组件类型选择最优存储策略
template<typename T>
std::enable_if_t<std::is_trivially_destructible_v<T>>
destroyComponents(T* data, size_t count) {
    // 平凡析构：什么都不做！O(1)
}

template<typename T>
std::enable_if_t<!std::is_trivially_destructible_v<T>>
destroyComponents(T* data, size_t count) {
    // 非平凡析构：逐个调用析构函数，O(n)
    for (size_t i = 0; i < count; ++i) {
        data[i].~T();
    }
}
```

### 6.4 C++20 Concepts：SFINAE 的进化

```cpp
// C++20 的 Concepts 让约束更清晰、错误信息更友好

template<typename T>
concept Component = std::is_standard_layout_v<T> &&
                    std::is_trivially_copyable_v<T> &&
                    sizeof(T) <= 256;  // 组件大小上限

template<typename T>
concept Renderable = requires(T t) {
    { t.getMesh() } -> std::same_as<MeshHandle>;
    { t.getMaterial() } -> std::same_as<MaterialHandle>;
};

// 使用 concept 约束模板参数
class ComponentArray {
public:
    template<Component T>
    void registerType() {
        // 编译器保证 T 满足 Component 概念
        arrays_[typeid(T)] = std::make_unique<TypedArray<T>>();
    }

    template<Renderable T>
    void submitForRendering(EntityID id) {
        T& comp = getComponent<T>(id);
        renderer_.submit(comp.getMesh(), comp.getMaterial());
    }
};
```

**SFINAE vs Concepts 对比：**

| 特性 | SFINAE (C++11/14) | Concepts (C++20) |
|------|------------------|-----------------|
| 可读性 | 晦涩，嵌套在模板参数中 | 声明式，像接口 |
| 错误信息 | 模板实例化错误极长 | 清晰指出不满足哪个 concept |
| 编译速度 | 实例化失败后才报错 | 提前短路，减少实例化 |
| 引擎适用 | 现有代码库广泛存在 | 新项目推荐 |

### 6.5 CRTP：编译期静态多态

```cpp
// CRTP (Curiously Recurring Template Pattern)：
// 派生类把自己作为模板参数传给基类

template<typename Derived>
class SystemBase {
public:
    void update(float dt) {
        // static_cast 实现编译期多态，无 vtable 开销
        static_cast<Derived*>(this)->onUpdate(dt);
    }

    void onEntityAdded(EntityID id) {
        static_cast<Derived*>(this)->onEntityAddedImpl(id);
    }
};

class TransformSystem : public SystemBase<TransformSystem> {
public:
    // 不是虚函数！编译器直接内联
    void onUpdate(float dt) {
        // 处理所有 Transform 组件
    }

    void onEntityAddedImpl(EntityID id) {
        // 初始化 Transform
    }
};

class RenderSystem : public SystemBase<RenderSystem> {
public:
    void onUpdate(float dt) {
        // 收集渲染命令
    }

    void onEntityAddedImpl(EntityID id) {
        // 注册可渲染实体
    }
};

// 使用：统一接口，零运行时开销
template<typename Sys>
void runSystem(Sys& system, float dt) {
    system.update(dt);  // 编译器直接内联具体系统的 onUpdate
}
```

**CRTP + Concepts 结合（C++20）：**

```cpp
template<typename Derived>
concept SystemLike = requires(Derived d, float dt, EntityID id) {
    { d.onUpdate(dt) } -> std::same_as<void>;
    { d.onEntityAddedImpl(id) } -> std::same_as<void>;
};

template<SystemLike Derived>
class SystemBase {
public:
    void update(float dt) {
        static_cast<Derived*>(this)->onUpdate(dt);
    }
};
```

### 6.5 std::optional 与 std::variant：现代类型系统

C++17 引入的**词汇类型**让代码意图直接表达在类型系统中，减少魔法值和裸指针的使用。

#### std::optional：可空的值语义

```cpp
#include <optional>

// 引擎场景 1：可能找不到的组件
std::optional<Transform> findTransform(EntityID id) {
    auto it = transforms_.find(id);
    if (it == transforms_.end()) return std::nullopt;
    return it->second;  // 返回值，不是指针
}

// 使用：
auto trans = registry.findTransform(playerId);
if (trans) {  // 检查是否有值
    trans->position += velocity * dt;  // 解引用访问
} else {
    // 实体没有 Transform 组件
}

// 引擎场景 2：Raycast 可能未命中
std::optional<HitResult> raycast(const Ray& ray) {
    float tMin = FLT_MAX;
    const Collider* hitCollider = nullptr;
    // ... 遍历碰撞体 ...
    if (!hitCollider) return std::nullopt;
    return HitResult{hitCollider, ray.origin + ray.direction * tMin};
}

// 带默认值的访问
Vector3 pos = registry.findTransform(id).value_or(Vector3{0, 0, 0});
```

**与指针的对比：**

| | `std::optional<T>` | `T*` | `std::unique_ptr<T>` |
|---|-------------------|------|---------------------|
| 所有权 | 值语义（拥有数据） | 无所有权 | 独占所有权 |
| 分配 | 无堆分配 | 可能指向堆/栈 | 堆分配 |
| 空状态 | `std::nullopt` | `nullptr` | `nullptr` |
| 拷贝 | 可拷贝（T 可拷贝时） | 浅拷贝 | 不可拷贝 |
| 引擎适用 | 返回值可能缺失 | 观察/引用外部对象 | 动态生命周期管理 |

#### std::variant：类型安全的联合体

```cpp
#include <variant>

// 引擎场景：事件系统的多种载荷
event PlayerDamaged { EntityID attacker; float damage; };
event LevelCompleted { int score; float time; };
event GamePaused { };

using GameEvent = std::variant<PlayerDamaged, LevelCompleted, GamePaused>;

// 分发事件
void dispatchEvent(const GameEvent& event) {
    std::visit([](const auto& e) {
        using T = std::decay_t<decltype(e)>;
        if constexpr (std::is_same_v<T, PlayerDamaged>) {
            applyDamage(e.attacker, e.damage);
        } else if constexpr (std::is_same_v<T, LevelCompleted>) {
            showScoreScreen(e.score, e.time);
        } else if constexpr (std::is_same_v<T, GamePaused>) {
            pauseGame();
        }
    }, event);
}

// 引擎场景 2：Shader 参数类型
using ShaderParam = std::variant<
    float,           // scalar
    Vector2,         // vec2
    Vector3,         // vec3
    Vector4,         // vec4
    Matrix4x4,       // mat4
    TextureHandle    // sampler
>;

// 与 union 的对比：std::variant 自动跟踪当前活跃类型，访问错误类型会抛异常（或返回 nullptr）
```

#### std::span：非拥有的连续数据视图

```cpp
#include <span>

// 替代 (T* data, size_t count) 的 C 风格接口
void submitDrawCalls(std::span<const DrawCommand> commands);

// 可以接收任何连续容器
std::vector<DrawCommand> vec;
submitDrawCalls(vec);                    // OK

std::array<DrawCommand, 64> arr;
submitDrawCalls(arr);                    // OK

DrawCommand raw[10];
submitDrawCalls(raw);                    // OK

// span 的子视图（零拷贝）
std::span<const DrawCommand> opaque = commands.subspan(0, opaqueCount);
std::span<const DrawCommand> transparent = commands.subspan(opaqueCount);

// 固定大小的 span（编译期已知）
void setViewport(std::span<const float, 4> rect);  // 必须传入 4 个 float
```

**引擎中的典型使用：**

```cpp
// 顶点数据传递
void uploadVertexBuffer(GLuint vbo, std::span<const Vertex> vertices);

// 音频采样处理
void mixAudio(std::span<const float> source, std::span<float> destination, float gain);

// 网络包数据
void sendPacket(std::span<const std::byte> payload);
```

| 容器 | 拥有数据 | 大小固定 | 引擎场景 |
|------|---------|---------|---------|
| `std::vector<T>` | 是 | 运行时 | 动态数组（实体列表、组件数组） |
| `std::array<T, N>` | 是 | 编译期 | 固定大小缓冲（矩阵、四元数） |
| `std::span<T>` | 否 | 均可 | 函数参数：接受任何连续数据 |
| `T*` | 否 | 否 | C API 互操作、原始指针 |

---

## 7. 内存序与原子操作

### 7.1 为什么需要理解内存序

现代 CPU 和编译器会对指令进行重排序以优化性能。在单线程程序中，这完全透明。但在多线程引擎中（Job System、渲染线程、加载线程），重排序可能导致数据竞争和不可预测的行为。

```cpp
// 问题示例：没有正确同步的双缓冲渲染
std::atomic<bool> frameReady{false};
RenderData renderData;

// 渲染线程
void renderThread() {
    while (running) {
        if (frameReady.load()) {   // 检查新帧是否就绪
            draw(renderData);      // 使用 renderData
            frameReady.store(false);
        }
    }
}

// 逻辑线程
void logicThread() {
    while (running) {
        update(renderData);        // 更新 renderData
        frameReady.store(true);    // 标记新帧就绪
    }
}

// 危险！没有内存序保证：
// logicThread 中 frameReady = true 可能在 renderData 更新完成前就可见
// 导致 renderThread 读到半更新的 renderData
```

### 7.2 memory_order_relaxed：最弱，最快

```cpp
// relaxed：只保证原子性，不保证顺序
// 适用：计数器、统计信息、不需要同步其他数据的场景

std::atomic<uint64_t> frameCounter{0};

void onFrameEnd() {
    frameCounter.fetch_add(1, std::memory_order_relaxed);
    // 只计数，不需要和其他操作同步
}

// 读取统计
uint64_t getFrameCount() {
    return frameCounter.load(std::memory_order_relaxed);
}
```

### 7.3 acquire-release：最常用的引擎同步模式

```cpp
// acquire-release 建立了"发布-订阅"关系：
// release 写操作之前的所有写操作，对随后 acquire 读操作的线程可见

std::atomic<Job*> jobQueueHead{nullptr};

// 工作线程提交 Job（发布者）
void submitJob(Job* job) {
    job->execute();  // A: 准备 job 数据
    // ...           // B: 更多准备工作

    jobQueueHead.store(job, std::memory_order_release);
    // release 保证：A、B 都在 store 之前完成
    // 相当于说"我把 job 发布了，之前的工作都已完成"
}

// 工作者线程获取 Job（订阅者）
Job* getJob() {
    Job* job = jobQueueHead.load(std::memory_order_acquire);
    // acquire 保证：如果读到了 job，那么 submitJob 中 A、B 的写操作都可见
    // 相当于说"我收到了 job，发布者之前的工作我都看到了"

    if (job) {
        jobQueueHead.store(nullptr, std::memory_order_relaxed);
        return job;
    }
    return nullptr;
}
```

** acquire-release 的 happens-before 关系：**

```cpp
// 线程 1                          线程 2
// ------                          ------
data.value = 42;                   //
data.ready.store(true, release);   //   if (data.ready.load(acquire))
                                   //       assert(data.value == 42);  // 保证成立！
```

### 7.4 memory_order_seq_cst：最强，最慢

```cpp
// seq_cst (sequential consistency)：所有线程以相同顺序看到所有 seq_cst 操作
// 默认的 memory_order，最安全但最慢

std::atomic<int> x{0};
std::atomic<int> y{0};

// 线程 1
x.store(1, std::memory_order_seq_cst);
int r1 = y.load(std::memory_order_seq_cst);

// 线程 2
y.store(1, std::memory_order_seq_cst);
int r2 = x.load(std::memory_order_seq_cst);

// seq_cst 保证：不可能同时 r1 == 0 && r2 == 0
// 如果用 relaxed，则可能出现这种结果
```

**引擎中的选择指南：**

| 场景 | 推荐内存序 | 理由 |
|------|-----------|------|
| 纯计数器（帧数、统计） | `relaxed` | 不需要同步其他数据 |
| Job System 任务队列 | `acquire/release` | 发布任务+任务数据的经典模式 |
| 双缓冲交换指针 | `acquire/release` | 保证缓冲区内容完全可见 |
| 多生产者单消费者队列 | `seq_cst` | 需要全局顺序确定谁先入队 |
| 自旋锁 | `acquire/release` | lock 用 acquire，unlock 用 release |

### 7.5 无锁队列：引擎 Job System 的核心

```cpp
// 简化版单生产者单消费者无锁队列
template<typename T, size_t Capacity>
class LockFreeQueue {
public:
    LockFreeQueue() {
        for (size_t i = 0; i < Capacity; ++i) {
            buffer_[i].sequence.store(i, std::memory_order_relaxed);
        }
    }

    bool push(const T& item) {
        size_t pos = writePos_.load(std::memory_order_relaxed);
        Cell& cell = buffer_[pos % Capacity];

        size_t seq = cell.sequence.load(std::memory_order_acquire);
        if (seq != pos) {
            return false;  // 队列满
        }

        cell.data = item;
        cell.sequence.store(pos + 1, std::memory_order_release);
        writePos_.store(pos + 1, std::memory_order_release);
        return true;
    }

    bool pop(T& item) {
        size_t pos = readPos_.load(std::memory_order_relaxed);
        Cell& cell = buffer_[pos % Capacity];

        size_t seq = cell.sequence.load(std::memory_order_acquire);
        if (seq != pos + 1) {
            return false;  // 队列空
        }

        item = cell.data;
        cell.sequence.store(pos + Capacity, std::memory_order_release);
        readPos_.store(pos + 1, std::memory_order_release);
        return true;
    }

private:
    struct Cell {
        std::atomic<size_t> sequence;
        T data;
    };

    alignas(64) Cell buffer_[Capacity];  // 缓存行对齐，避免伪共享
    alignas(64) std::atomic<size_t> writePos_{0};
    alignas(64) std::atomic<size_t> readPos_{0};
};
```

### 7.5 C++20 Coroutines：异步编程的新范式

协程（Coroutines）允许函数在执行过程中**暂停**（`co_await`）并在稍后**恢复**，而无需阻塞线程。在引擎中，这意味着可以写出顺序风格的异步代码，同时底层运行在 Job System 上。

#### 核心概念

```cpp
#include <coroutine>

// 最简单的协程：返回一个 task
task<void> loadAssetAsync(const char* path) {
    // co_await 挂起当前协程，把控制权交还调用者
    // 当异步操作完成时，协程在某个工作线程上恢复
    auto data = co_await fileSystem.readAsync(path);

    // 这里可能在不同的线程上执行！
    auto texture = parseTexture(data);

    // co_return 结束协程（void 协程可以省略）
    co_return;
}

// 使用：
void startLoading() {
    auto t = loadAssetAsync("player.png");
    // loadAssetAsync 在第一个 co_await 处就返回了
    // 引擎继续执行，不会被阻塞
}
```

#### 协程的引擎应用场景

| 场景 | 传统方案 | 协程方案 |
|------|---------|---------|
| 异步资源加载 | 回调地狱 | `co_await loadAsync()` |
| 任务依赖链 | 手动维护依赖计数器 | `co_await jobA; co_await jobB;` |
| 流式关卡加载 | 复杂状态机 | `for (auto& chunk : level) co_await loadChunk(chunk);` |
| AI 行为序列 | 行为树节点 | `co_await playAnimation("attack"); co_await wait(0.5s);` |

#### 与传统回调的对比

```cpp
// 传统回调：状态分散在多个函数中
void loadLevel(const char* path) {
    loadManifest(path, [](Manifest* manifest) {
        loadTextures(manifest, [](TexturePack* pack) {
            loadMeshes(manifest, [](MeshPack* meshes) {
                spawnEntities(manifest, []() {
                    finalizeLevel();
                });
            });
        });
    });
}

// 协程：线性的、可读的控制流
task<void> loadLevel(const char* path) {
    auto manifest = co_await loadManifest(path);
    auto textures = co_await loadTextures(manifest);
    auto meshes = co_await loadMeshes(manifest);
    co_await spawnEntities(manifest);
    finalizeLevel();
}
```

#### 协程与 Job System 的结合

```cpp
// 简化版：让 co_await 等待 Job 完成
struct JobAwaiter {
    Job* job;

    // 协程挂起前调用：把协程注册为 job 的完成回调
    bool await_ready() const { return job->isDone(); }
    void await_suspend(std::coroutine_handle<> handle) const {
        job->onComplete([handle]() { handle.resume(); });
    }
    void await_resume() const {}  // 恢复时什么都不做
};

// 协程可以 await 一个 Job
task<void> physicsUpdate(float dt) {
    // 把物理计算拆成多个并行 Job
    Job* broadPhase = jobSystem.schedule(broadPhaseTask);
    Job* narrowPhase = jobSystem.schedule(narrowPhaseTask);

    // 等待所有 Job 完成
    co_await JobAwaiter{broadPhase};
    co_await JobAwaiter{narrowPhase};

    // 继续执行：整合结果
    applyConstraints();
}
```

**重要权衡：**

| | 传统回调/状态机 | C++20 协程 |
|---|---------------|-----------|
| 性能 | 最优，无额外分配 | 每次协程调用有 promise 分配（可用内存池优化）|
| 可读性 | 差，状态分散 | 好，线性控制流 |
| 调试 | 容易 | 困难（调用栈碎片化）|
| 编译时间 | 快 | 慢（编译器生成大量状态机代码）|
| 工具链 | 到处支持 | C++20，部分嵌入式工具链不支持 |

**引擎中的建议：**
- 工具代码、编辑器、脚本层：大胆使用协程
- 核心热路径（渲染、物理每帧更新）：保持传统方案
- 异步加载、网络、AI：协程显著提升代码可维护性

---

## 8. 数据导向设计中的 C++ 技巧

### 8.1 SoA vs AoS：从 OOP 到 DOD

```cpp
// Array of Structs (OOP 风格)：缓存不友好
struct AoSEntity {
    Vector3 position;    // 12 bytes
    Vector3 velocity;    // 12 bytes
    float health;        // 4 bytes
    bool active;         // 1 byte + 3 padding
};
std::vector<AoSEntity> entities;  // 遍历 position 时会把 velocity/health 也加载进缓存

// Structure of Arrays (DOD 风格)：缓存友好
struct SoAEntities {
    std::vector<Vector3> positions;
    std::vector<Vector3> velocities;
    std::vector<float> healths;
    std::vector<bool> actives;
};

// 系统只遍历需要的数据
void updatePositions(SoAEntities& e, float dt) {
    size_t count = e.positions.size();
    for (size_t i = 0; i < count; ++i) {
        if (e.actives[i]) {
            e.positions[i] += e.velocities[i] * dt;
        }
    }
    // positions 数组连续存储，每次缓存行加载 16 个 float
    // 不会加载无关的 health/active 数据
}
```

### 8.2 缓存行对齐：避免伪共享

```cpp
// 伪共享：两个线程修改同一缓存行（64 字节）的不同变量
struct BadCounters {
    std::atomic<uint64_t> threadAWork;   // 在同一条缓存行
    std::atomic<uint64_t> threadBWork;   // 也在同一条缓存行
};  // 两个线程不断争用同一个缓存行，性能暴跌

// 解决方案：每个变量独占一个缓存行
struct alignas(64) PaddedCounter {
    std::atomic<uint64_t> value;
    char padding[64 - sizeof(std::atomic<uint64_t>)];
};

struct GoodCounters {
    PaddedCounter threadA;  // 64 字节对齐，独占缓存行
    PaddedCounter threadB;  // 64 字节对齐，独占缓存行
};
```

### 8.3 编译期计算

```cpp
// constexpr：编译期计算，运行时零开销
constexpr float deg2rad(float deg) {
    return deg * 3.14159265f / 180.0f;
}

constexpr float sinTable[91] = {
    []{  // lambda 编译期初始化数组
        std::array<float, 91> table{};
        for (int i = 0; i <= 90; ++i) {
            table[i] = std::sin(deg2rad(i));
        }
        return table;
    }().data()[0]  // C++20 支持更简洁的方式
};

// 使用编译期查找表
float fastSin(int degrees) {
    return sinTable[degrees];  // 编译期计算好的值，O(1)
}

// 编译期哈希：用于资源 ID
consteval uint32_t hashString(std::string_view str) {
    uint32_t hash = 2166136261u;
    for (char c : str) {
        hash ^= static_cast<uint32_t>(c);
        hash *= 16777619u;
    }
    return hash;
}

// 编译期使用
constexpr auto PlayerTextureID = hashString("textures/player.png");
// PlayerTextureID 是编译期常量，零运行时开销
```

### 8.4 位操作与标志位管理

引擎中大量使用紧凑的标志位来节省内存和带宽：

#### ECS 组件掩码

```cpp
// 用 64 位整数表示实体拥有哪些组件
using ComponentMask = uint64_t;

constexpr ComponentMask TRANSFORM_MASK = 1u << 0;
constexpr ComponentMask MESH_MASK      = 1u << 1;
constexpr ComponentMask COLLIDER_MASK  = 1u << 2;
constexpr ComponentMask RIGIDBODY_MASK = 1u << 3;
constexpr ComponentMask ANIMATION_MASK = 1u << 4;
// ... 最多支持 64 种组件

// 实体的组件掩码
struct Entity {
    ComponentMask components;
};

// 查询：实体是否有 Transform 和 Mesh？
bool canRender(const Entity& e) {
    return (e.components & (TRANSFORM_MASK | MESH_MASK))
           == (TRANSFORM_MASK | MESH_MASK);
}

// 添加组件
void addComponent(Entity& e, ComponentMask mask) {
    e.components |= mask;  // 置位
}

// 移除组件
void removeComponent(Entity& e, ComponentMask mask) {
    e.components &= ~mask;  // 清零
}

// 查询：是否有任何物理组件？
bool hasPhysics(const Entity& e) {
    constexpr ComponentMask PHYSICS = COLLIDER_MASK | RIGIDBODY_MASK;
    return (e.components & PHYSICS) != 0;
}
```

#### 渲染管线屏障标志

```cpp
enum class PipelineStage : uint32_t {
    VertexInput    = 1u << 0,
    VertexShader   = 1u << 1,
    FragmentShader = 1u << 2,
    ColorOutput    = 1u << 3,
    ComputeShader  = 1u << 4,
};

enum class AccessMask : uint32_t {
    None          = 0,
    ReadIndirect  = 1u << 0,
    ReadIndex     = 1u << 1,
    ReadUniform   = 1u << 2,
    WriteColor    = 1u << 8,
    WriteDepth    = 1u << 9,
};

// 资源屏障描述
struct Barrier {
    PipelineStage srcStage;    // 源阶段
    PipelineStage dstStage;    // 目标阶段
    AccessMask srcAccess;      // 源访问类型
    AccessMask dstAccess;      // 目标访问类型
};
```

#### std::bitset vs 原始位运算

```cpp
#include <bitset>

// std::bitset：编译期已知大小，类型安全
std::bitset<64> componentMask;
componentMask.set(TRANSFORM_BIT);
componentMask.set(MESH_BIT);
bool hasBoth = componentMask.test(TRANSFORM_BIT) && componentMask.test(MESH_BIT);

// 原始位运算：运行时灵活，零开销
uint64_t mask = 0;
mask |= (1ull << TRANSFORM_BIT);
mask |= (1ull << MESH_BIT);
bool hasBoth2 = (mask & ((1ull << TRANSFORM_BIT) | (1ull << MESH_BIT))) == ...;

// 引擎中的选择：
// - 固定大小、编译期已知：std::bitset（可读性好）
// - 动态大小、需要序列化：原始位运算 + std::vector<uint64_t>
// - 热路径（每帧查询数千次）：原始位运算（编译器优化更激进）
```

#### 常用位运算技巧

```cpp
// 1. 判断是否为 2 的幂（用于分配器对齐）
bool isPowerOfTwo(uint32_t x) {
    return x > 0 && (x & (x - 1)) == 0;
}

// 2. 向上对齐到 2 的幂
uint32_t alignUpPow2(uint32_t x, uint32_t alignment) {
    assert(isPowerOfTwo(alignment));
    return (x + alignment - 1) & ~(alignment - 1);
}

// 3. 交换两个整数（不使用临时变量）——面试题，但别在引擎里用
void swap(uint32_t& a, uint32_t& b) {
    a ^= b;
    b ^= a;
    a ^= b;
}

// 4. 计算整数中 1 的位数（population count）
// 现代 CPU 有内置指令：
#ifdef __GNUC__
    int count = __builtin_popcount(mask);
#elif defined(_MSC_VER)
    #include <intrin.h>
    int count = __popcnt(mask);
#endif
// C++20: std::popcount(mask)

// 5. 找到最低位的 1 的位置（用于空闲块分配）
// C++20: std::countr_zero(mask)
#ifdef __GNUC__
    int index = __builtin_ctz(mask);  // count trailing zeros
#endif
```

---

## 9. C++ 编译链接原理

理解 C++ 从源代码到可执行文件的完整过程，是诊断编译错误、优化构建时间、管理大型项目依赖的基础。游戏引擎通常包含数十万行代码、数百个模块，编译链接的效率直接影响开发迭代速度。

### 9.1 四阶段编译模型

C++ 的编译过程分为四个阶段：**预处理（Preprocessing）**、**编译（Compilation）**、**汇编（Assembly）**、**链接（Linking）**。

```cpp
// 示例文件：math_utils.h
#ifndef MATH_UTILS_H  // 头文件保护——防止重复包含
#define MATH_UTILS_H

#include <cmath>  // 预处理阶段会将此头文件的内容完整插入此处

// 内联函数——建议编译器在每个调用点展开函数体
inline float FastSqrt(float x) {
    return std::sqrt(x);
}

// 宏定义——预处理器文本替换，无类型检查
#define SQUARE(x) ((x) * (x))  // 注意括号——否则 SQUARE(a + b) 会出错

// 现代 C++ 中，优先使用 constexpr 替代宏
constexpr float SquareConstexpr(float x) {
    return x * x;  // 有类型检查，可在编译期求值
}

#endif  // MATH_UTILS_H
```

**预处理阶段**执行文本替换操作：处理 `#include` 指令（将被包含文件的内容插入）、展开宏定义（`#define`）、处理条件编译（`#if`、`#ifdef`）、移除注释。预处理器的输出是一个扩展后的 C++ 源文件（`.i` 文件）。预处理阶段不参与 C++ 的语法和语义分析——这既是它的强大之处（可以编写任意复杂的宏），也是危险之源（宏展开可能产生意想不到的语法错误）。

**编译阶段**将预处理后的 C++ 代码翻译成目标机器的汇编代码。编译器在此阶段执行完整的语法分析、语义检查、类型推导、以及大量的优化——常量传播、死代码消除、函数内联、循环优化等。输出的汇编文件（`.s`）是人类可读的文本格式。

**汇编阶段**将汇编代码转换为机器码，生成**目标文件（Object File, `.o` 或 `.obj`）**。目标文件包含了二进制机器指令、数据，以及**符号表（Symbol Table）**——记录了该文件中定义和引用的全局符号（函数名、全局变量名）。

**链接阶段**将一个或多个目标文件和库文件合并，解析符号引用，生成最终的可执行文件。链接器的工作是解决"符号未定义"和"符号重复定义"的问题。

### 9.2 静态库与动态库

| 特性 | 静态库（`.lib`/`.a`） | 动态库（`.dll`/`.so`/`.dylib`） |
|------|----------------------|--------------------------------|
| 链接时机 | 编译链接时——库代码被复制到可执行文件中 | 运行时/启动时——可执行文件仅包含引用 |
| 文件大小 | 可执行文件较大（包含库代码） | 可执行文件较小 |
| 内存占用 | 每个进程有独立的库代码副本 | 多个进程共享同一库代码（代码段） |
| 部署 | 简单——仅需可执行文件 | 复杂——需确保 DLL 在目标系统上可用 |
| 更新 | 需重新链接整个可执行文件 | 可独立更新 DLL（二进制兼容性允许时） |
| 启动速度 | 快——无需运行时解析 | 稍慢——需要动态链接器解析符号 |
| 版本冲突 | 无——已静态链接 | DLL 地狱（Windows）或符号版本控制（Linux） |

引擎核心通常以静态库形式链接——这消除了 DLL 地狱的风险，允许编译器进行跨模块的优化（Link-Time Optimization, LTO），并简化了发布版本的分发。插件系统则必须使用动态库——这是运行时扩展引擎功能的唯一方式。Unreal Engine 的模块系统允许每个模块选择静态或动态链接，根据模块的用途和更新频率做出最优选择。

### 9.3 名称修饰与 extern "C"

**名称修饰（Name Mangling）**是 C++ 编译器将函数名、类名、命名空间等信息编码为唯一符号名的过程。例如，函数 `void Engine::Math::Vector3::Normalize()` 可能被修饰为 `_ZN6Engine4Math7Vector39NormalizeEv`。链接器使用修饰后的名称来匹配符号引用和定义。

```cpp
// 解决 C++ 与 C 代码互操作的关键：extern "C"

// C++ 编译器会对此处的函数名进行名称修饰
void MyCppFunction(int x);

// extern "C" 告诉编译器使用 C 的名称修饰规则（不修饰）
extern "C" {
    void RenderAPI_Init();
    void RenderAPI_Shutdown();
}

// 条件编译：仅在 C++ 编译器中启用 extern "C"
#ifdef __cplusplus
extern "C" {
#endif

void* Engine_Allocate(size_t size);
void Engine_Free(void* ptr);

#ifdef __cplusplus
}
#endif
```

`extern "C"` 在游戏引擎开发中无处不在，因为引擎需要与大量 C 语言编写的库交互——操作系统 API、图形 API（OpenGL/Vulkan）、物理引擎、音频库（OpenAL）等。理解名称修饰机制对于解读链接错误（"unresolved external symbol"）和编写跨语言绑定代码至关重要。

**DLL 地狱问题**是 Windows 平台上动态库的经典困境。当多个应用程序或插件依赖同一 DLL 的不同版本时，Windows 的 DLL 搜索路径规则可能导致加载了错误的版本。解决方案包括：**Side-by-Side Assembly（SxS）**——将 DLL 与其版本信息一起打包；**静态链接运行时库**——避免对 MSVCRUNTIME 等系统 DLL 的依赖；**延迟加载（Delay-Loaded DLLs）**——仅在需要时才加载 DLL，提供了更灵活的错误处理。在游戏引擎开发中，最可靠的策略是最小化外部 DLL 依赖，对必须使用的库采用静态链接，并通过自研模块系统管理插件接口。

### 9.4 虚函数表（vtable）机制

**多态（Polymorphism）**是 OOP 的核心特性之一，而 C++ 实现运行时多态的机制是**虚函数表（Virtual Table, vtable）**。理解 vtable 的机制对于引擎优化至关重要，因为虚函数调用比普通函数调用多出一次间接寻址（indirection），这可能导致指令缓存未命中（instruction cache miss）和分支预测失败。

```cpp
// 基类——定义游戏对象的通用接口
class GameObject {
public:
    virtual ~GameObject() = default;
    virtual void Update(float deltaTime) = 0;
    virtual void Render() = 0;
    void SetActive(bool active) { m_active = active; }
    bool IsActive() const { return m_active; }
protected:
    bool m_active = true;
};

class Player : public GameObject {
public:
    void Update(float deltaTime) override {
        m_health += m_healthRegen * deltaTime;
    }
    void Render() override { /* ... */ }
private:
    float m_health = 100.0f;
    float m_healthRegen = 1.0f;
};
```

当编译器处理包含虚函数的类时，它会为该类生成一个虚函数表——本质上是一个函数指针数组，按照虚函数声明的顺序存储每个虚函数的地址。每个该类的实例对象会在其内存布局的开头（或特定偏移位置）包含一个隐藏的**虚表指针（vptr）**，指向该类的虚函数表。

| 对象内存布局 | 大小（64 位平台） | 说明 |
|-------------|----------------|------|
| `vptr`（虚表指针） | 8 字节 | 指向类型对应的虚函数表 |
| `m_active`（基类成员） | 1 字节 | `bool` 类型 |
| 填充（Padding） | 7 字节 | 使下一个成员按 8 字节对齐 |
| `m_health` | 4 字节 | Player 类成员 |
| `m_healthRegen` | 4 字节 | |
| **Player 对象总计** | **32 字节** | |

虚函数调用的开销分析揭示了一个关键的性能权衡。普通函数调用通过直接跳转（direct jump）完成，通常只需 1 个 CPU 周期；而虚函数调用需要：1）从对象地址加载 `vptr`（内存读取，可能缓存命中）；2）从 `vtable` 加载函数地址（内存读取）；3）间接跳转到函数地址。在现代 CPU 上，这两次额外的内存读取可能导致 5-20 个周期的延迟。更重要的是，间接跳转难以被分支预测器正确预测，错误预测将导致流水线清空（pipeline flush），代价可达 20-40 个周期。

在引擎的高频调用路径中——例如每帧更新数千个游戏对象、渲染调用提交——这种开销会累积成显著的性能瓶颈。这正是为什么现代引擎倾向于使用函数指针表、策略模式模板、或完全避免虚函数的 ECS 架构。

### 9.5 多继承与虚继承

**多继承（Multiple Inheritance, MI）**允许一个类继承多个基类。这在游戏引擎中有实际应用场景——例如一个对象可能同时是"可渲染的"和"可物理模拟的"。然而，多继承引入了**菱形继承问题（Diamond Problem）**：

```cpp
class Entity {
public:
    uint32_t m_entityID = 0;
};

// 使用 virtual 继承——确保 Entity 在最终对象中只有一份拷贝
class Renderable : public virtual Entity {
public:
    uint32_t m_materialID = 0;
};

class Simulatable : public virtual Entity {
public:
    uint32_t m_physicsBodyID = 0;
};

// 同时继承 Renderable 和 Simulatable
// 没有 virtual 继承时，NPC 会包含两份 Entity 子对象
// 有了 virtual 继承，Entity 只出现一次
class NPC : public Renderable, public Simulatable {
public:
    void PrintIDs() const {
        std::cout << "Entity ID: " << m_entityID << "\n";
        std::cout << "Material ID: " << m_materialID << "\n";
        std::cout << "Physics Body ID: " << m_physicsBodyID << "\n";
    }
};
```

虚继承通过引入**虚基类表（Virtual Base Table, vbase table）**来解决菱形问题。每个包含虚基类的对象会额外持有一个指向 vbase table 的指针，该表记录了虚基类子对象相对于派生类对象起始地址的偏移量。这种机制确保了即使在复杂的继承层次中，虚基类也只有一个实例。

然而，虚继承的开销不容忽视：额外的指针存储、额外的间接寻址、更复杂的对象构造顺序。在现代引擎设计中，多继承的使用已大幅减少，取而代之的是**接口类（纯虚基类）**和**组合（Composition）**模式。例如 Unity 引擎的核心架构——组件模式（Component Pattern），将"是一个（is-a）"关系转换为"有一个（has-a）"关系，消除了继承层次带来的耦合和性能问题。

---

## 10. 综合代码实战

下面是一个结合本章多个特性的简化 ECS 注册表实现：

```cpp
#include <vector>
#include <memory>
#include <typeindex>
#include <unordered_map>
#include <cassert>
#include <algorithm>

// =============================================================================
// 类型工具
// =============================================================================

template<typename T>
concept Component = std::is_standard_layout_v<T> && std::is_trivially_copyable_v<T>;

// =============================================================================
// 组件数组接口（类型擦除，运行时多态）
// =============================================================================

class IComponentArray {
public:
    virtual ~IComponentArray() = default;
    virtual void onEntityDestroyed(uint32_t entityId) = 0;
};

// =============================================================================
// 类型化组件数组（编译期多态 + 概念约束）
// =============================================================================

template<Component T>
class ComponentArray : public IComponentArray {
public:
    // 移动语义保证 vector 扩容高效
    ComponentArray() {
        components_.reserve(1024);
        entityToIndex_.reserve(1024);
    }

    // 禁止拷贝：组件数组是单例资源
    ComponentArray(const ComponentArray&) = delete;
    ComponentArray& operator=(const ComponentArray&) = delete;

    // 默认移动（Rule of Zero，因为成员都能正确移动）
    ComponentArray(ComponentArray&&) = default;
    ComponentArray& operator=(ComponentArray&&) = default;

    void insert(uint32_t entityId, T component) {
        assert(entityToIndex_.find(entityId) == entityToIndex_.end()
               && "Component already exists for entity");

        size_t index = components_.size();
        entityToIndex_[entityId] = index;
        indexToEntity_.push_back(entityId);
        components_.push_back(std::move(component));  // 移动语义
    }

    void remove(uint32_t entityId) {
        auto it = entityToIndex_.find(entityId);
        assert(it != entityToIndex_.end() && "Removing non-existent component");

        size_t removedIndex = it->second;
        size_t lastIndex = components_.size() - 1;

        // 用最后一个元素填充空洞，保持数组紧凑
        components_[removedIndex] = std::move(components_[lastIndex]);
        uint32_t lastEntity = indexToEntity_[lastIndex];
        indexToEntity_[removedIndex] = lastEntity;
        entityToIndex_[lastEntity] = removedIndex;

        components_.pop_back();
        indexToEntity_.pop_back();
        entityToIndex_.erase(it);
    }

    T& get(uint32_t entityId) {
        return components_[entityToIndex_.at(entityId)];
    }

    const std::vector<T>& getAll() const { return components_; }

    void onEntityDestroyed(uint32_t entityId) override {
        auto it = entityToIndex_.find(entityId);
        if (it != entityToIndex_.end()) {
            remove(entityId);
        }
    }

private:
    std::vector<T> components_;                          // 紧凑的组件数组（SoA 核心）
    std::unordered_map<uint32_t, size_t> entityToIndex_; // Entity -> 数组索引
    std::vector<uint32_t> indexToEntity_;                // 数组索引 -> Entity
};

// =============================================================================
// ECS 注册表
// =============================================================================

class Registry {
public:
    uint32_t createEntity() {
        return nextEntityId_++;
    }

    void destroyEntity(uint32_t entityId) {
        // 通知所有组件数组移除该实体的组件
        for (auto& [type, array] : componentArrays_) {
            array->onEntityDestroyed(entityId);
        }
    }

    template<Component T, typename... Args>
    void addComponent(uint32_t entityId, Args&&... args) {
        getComponentArray<T>()->insert(
            entityId,
            T(std::forward<Args>(args)...)  // 完美转发
        );
    }

    template<Component T>
    void removeComponent(uint32_t entityId) {
        getComponentArray<T>()->remove(entityId);
    }

    template<Component T>
    T& getComponent(uint32_t entityId) {
        return getComponentArray<T>()->get(entityId);
    }

    template<Component T>
    std::vector<T>& getComponents() {
        return getComponentArray<T>()->getAll();
    }

private:
    template<Component T>
    ComponentArray<T>* getComponentArray() {
        std::type_index type = typeid(T);
        auto it = componentArrays_.find(type);
        if (it == componentArrays_.end()) {
            auto array = std::make_unique<ComponentArray<T>>();
            auto* ptr = array.get();
            componentArrays_[type] = std::move(array);
            return ptr;
        }
        return static_cast<ComponentArray<T>*>(it->second.get());
    }

    uint32_t nextEntityId_ = 0;
    std::unordered_map<std::type_index, std::unique_ptr<IComponentArray>> componentArrays_;
};

// =============================================================================
// 使用示例
// =============================================================================

struct Transform {
    float x, y, z;
};
static_assert(Component<Transform>);  // 编译期验证

struct Velocity {
    float vx, vy, vz;
};
static_assert(Component<Velocity>);

class MovementSystem {
public:
    void update(Registry& registry, float dt) {
        auto& transforms = registry.getComponents<Transform>();
        auto& velocities = registry.getComponents<Velocity>();

        // 注意：实际 ECS 需要按 entity 关联，这里简化展示
        // 真正的实现会用 archetype 或 sparse set 保证同组实体对齐
        size_t count = std::min(transforms.size(), velocities.size());
        for (size_t i = 0; i < count; ++i) {
            transforms[i].x += velocities[i].vx * dt;
            transforms[i].y += velocities[i].vy * dt;
            transforms[i].z += velocities[i].vz * dt;
        }
    }
};
```

---

## 10. 练习

### 练习 1：实现 RAII 封装的文件映射

基于本章的 RAII 和 Rule of Five，实现一个跨平台的内存映射文件类：

**要求：**
1. 构造函数接受文件路径和只读/读写模式
2. 析构函数自动解除映射并关闭文件
3. 删除拷贝语义（映射内存不可复制）
4. 实现移动语义转移映射所有权
5. 提供 `data()` 返回映射地址，`size()` 返回大小
6. 支持 Windows (`CreateFileMapping`/`MapViewOfFile`) 和 POSIX (`mmap`)

**验证：**
```cpp
MappedFile map("texture.dds", MappedFile::ReadOnly);
const uint8_t* data = static_cast<const uint8_t*>(map.data());
size_t size = map.size();
// 读取 DDS 头部
const DDSHeader* header = reinterpret_cast<const DDSHeader*>(data);
// map 离开作用域自动解除映射
```

---

### 练习 2：实现编译期类型 ID 系统

利用模板和 `constexpr` 实现零开销的运行时类型识别：

**要求：**
1. `TypeID<T>()` 返回唯一的 `uint32_t` 类型标识
2. 标识在编译期确定，运行时只读取常量
3. 不同编译单元中的同一类型返回相同 ID
4. 使用 `constexpr` 函数或模板特化实现

**提示：**
- 可以用 `__PRETTY_FUNCTION__` / `__FUNCSIG__` 的哈希（编译期字符串处理）
- 或利用函数模板实例化的地址唯一性

**验证：**
```cpp
static_assert(TypeID<int>() != TypeID<float>());
assert(TypeID<int>() == TypeID<int>());
assert(TypeID<Transform>() == TypeID<Transform>());
```

---

### 练习 3：实现无锁多生产者单消费者队列

扩展 7.5 节的单生产者版本，支持多生产者：

**要求：**
1. 使用 `compare_exchange_weak` 实现无锁的 `push`
2. 使用 `memory_order_seq_cst` 或 `acquire/release` 保证正确性
3. 容量固定为 2 的幂，用位运算替代取模
4. 处理 ABA 问题（使用序列号或 tagged pointer）

**参考思路：**
```cpp
template<typename T, size_t N>
class MPSCQueue {
    static_assert((N & (N - 1)) == 0, "Capacity must be power of 2");

    bool push(const T& item) {
        // 1. 原子获取当前写位置
        // 2. 检查该位置是否可用（序列号匹配）
        // 3. compare_exchange_weak 竞争写入位置
        // 4. 写入数据 + 更新序列号（release）
    }
};
```

---

### 练习 4：用 std::span 重构 API

把引擎中常见的裸指针+大小接口重构为 `std::span`：

**要求：**
1. 将 `void uploadVertices(Vertex* data, size_t count)` 重构为使用 `std::span`
2. 确保函数可以接受 `std::vector<Vertex>`、`std::array<Vertex, N>` 和 C 数组
3. 添加一个固定大小的重载：`void setViewport(std::span<const float, 4> rect)`
4. 对比重构前后的接口安全性和调用便利性

---

### 练习 5：实现 ECS 组件掩码查询系统

基于 8.4 节的位操作，实现一个组件掩码查询系统：

**要求：**
1. 定义至少 8 种组件，每种对应一个 `ComponentMask` 位
2. 实现 `Registry::queryEntities(ComponentMask required, ComponentMask excluded)` 函数
3. 返回所有满足"拥有 required 的所有组件、且不拥有 excluded 任何组件"的实体
4. 用位运算实现，避免循环遍历单个位

**验证：**
```cpp
// 查询同时拥有 Transform 和 Mesh，但没有 Collider 的实体
auto entities = registry.queryEntities(
    TRANSFORM_MASK | MESH_MASK,
    COLLIDER_MASK
);
// 结果只包含同时满足两个条件的实体
```

---

### 练习 6（可选）：用协程简化异步加载

将以下回调式资源加载代码改写为协程风格：

**原始代码：**
```cpp
void loadLevel(const char* path, std::function<void()> onComplete) {
    loadManifest(path, [onComplete](Manifest* m) {
        loadTextures(m, [m, onComplete](TexturePack* t) {
            loadMeshes(m, [m, t, onComplete](MeshPack* meshes) {
                onComplete();
            });
        });
    });
}
```

**目标：** 使用 `co_await` 写出线性的加载逻辑。

**提示：**
- 定义一个简单的 `task<T>` 类型（或使用伪代码）
- 每个 `loadXxxAsync()` 函数返回一个可 `co_await` 的对象
- 忽略协程的底层实现细节，关注控制流的简化效果
```

---

## 11. 扩展阅读

### 书籍

1. **《Effective Modern C++》by Scott Meyers** — 现代 C++ 核心特性的最佳实践，必读
2. **《C++ Concurrency in Action, 2nd Edition》by Anthony Williams** — 第 5 章内存模型和原子操作详解
3. **《C++ Templates: The Complete Guide, 2nd Edition》by David Vandevoorde** — 模板元编程权威参考
4. **《Optimized C++》by Kurt Guntheroth** — C++ 性能优化，包含缓存、SIMD、编译器优化

### 在线资源

5. **[cppreference.com](https://en.cppreference.com/)** — 最权威的 C++ 参考，特别是 [std::memory_order](https://en.cppreference.com/w/cpp/atomic/memory_order) 页面
6. **[Bartosz Milewski: C++ Atomics and Memory Ordering](https://bartoszmilewski.com/2008/12/01/c-atomics-and-memory-ordering/)** — 内存序的经典解释
7. **[Jeff Preshing: Memory Ordering at Compile Time and Processor Time](https://preshing.com/20120930/weak-vs-strong-memory-models/)** — 编译器重排序和 CPU 重排序的可视化解释
8. **[Herb Sutter: atomic Weapons](https://herbsutter.com/2013/02/11/atomic-weapons-the-c-memory-model-and-modern-hardware/)** — C++ 内存模型权威演讲

### 开源参考

9. **[EnTT](https://github.com/skypjack/entt)** — 现代 C++ ECS 库，观察其 Type Traits 和 Sparse Set 实现
10. **[Jolt Physics](https://github.com/jrouwe/JoltPhysics)** — 现代 C++ 物理引擎，观察其 Job System 和内存对齐实践
11. **[bgfx](https://github.com/bkaradzic/bgfx)** — 跨平台渲染库，观察其平台抽象和 RAII 封装
12. **[ViennaGameJobSystem](https://github.com/hlavacs/ViennaGameJobSystem)** — C++20 协程 Job System，支持 work stealing
13. **[janekb04/job_system](https://github.com/janekb04/job_system)** — 无锁协程 Job System，参考其原子操作用法

### 新增主题资源

14. **[C++20 Coroutines Driving a Job System](https://poniesandlight.co.uk/reflect/coroutines_job_system/)** — 协程与 Job System 结合的深入教程
15. **[cppreference: std::span](https://en.cppreference.com/w/cpp/container/span)** — span 的完整接口参考
16. **[cppreference: std::optional](https://en.cppreference.com/w/cpp/utility/optional)** / **[std::variant](https://en.cppreference.com/w/cpp/utility/variant)** — 词汇类型的权威文档
17. **[Performance Overhead of C++ Exceptions](https://www.nutrient.io/blog/performance-overhead-of-exceptions-in-cpp/)** — 异常开销的实测分析

---

## 常见陷阱

### 陷阱 1：忘记 noexcept

```cpp
// 错误：移动构造没有 noexcept
class Buffer {
public:
    Buffer(Buffer&& other) {  // 隐式不是 noexcept！
        data_ = other.data_;
        // 如果有任何可能抛出的操作...
    }
};

// 修复：显式标记 noexcept
class Buffer {
public:
    Buffer(Buffer&& other) noexcept
        : data_(other.data_), size_(other.size_) {
        other.data_ = nullptr;
        other.size_ = 0;
    }
};
```

### 陷阱 2：在热路径使用 shared_ptr

```cpp
// 错误：每帧数千次原子操作
for (auto& e : entities) {
    auto shared = e->getSharedComponent();  // atomic ref count +1
    shared->update();
}  // atomic ref count -1

// 修复：用原始指针或引用
for (auto& e : entities) {
    Component& comp = e->getComponentRef();  // 无原子操作
    comp.update();
}
```

### 陷阱 3：placement new 后误用 delete

```cpp
// 错误
char buffer[256];
T* obj = new (buffer) T();
delete obj;  // 未定义行为！尝试释放栈内存

// 正确
obj->~T();   // 只调用析构函数
// buffer 在作用域结束时自动释放
```

### 陷阱 4：忽略内存序导致数据竞争

```cpp
// 错误：用 relaxed 同步数据
std::atomic<bool> ready{false};
int sharedData = 0;

// 线程 1
sharedData = 42;
ready.store(true, std::memory_order_relaxed);  // 不保证顺序！

// 线程 2
if (ready.load(std::memory_order_relaxed)) {   // 可能看到 ready=true 但 sharedData 未更新
    use(sharedData);  // 可能读到旧值！
}

// 修复：使用 acquire/release
ready.store(true, std::memory_order_release);
// ...
if (ready.load(std::memory_order_acquire)) {
    use(sharedData);  // 保证读到 42
}
```

### 陷阱 5：过度使用模板元编程

```cpp
// 不要为了元编程而元编程
// 如果运行时多态的性能足够，就用虚函数
// 模板元编程的代价：编译时间、代码膨胀、调试困难

// 决策流程：
// 1. 这是热路径吗？（每帧调用数千次以上）
//    → 是：考虑模板/CRTP 消除虚调用开销
//    → 否：虚函数可能更清晰
// 2. 类型在编译期确定吗？
//    → 是：模板
//    → 否：虚函数或 std::variant
// 3. 编译时间可接受吗？
//    → 否：减少模板深度，用运行时多态替代
```

---

## 本章小结

本章覆盖了游戏引擎开发中最关键的 C++ 语言特性：

1. **RAII**：确定性资源管理，Rule of Zero / Rule of Five 的抉择
2. **异常策略**：引擎中禁用异常的原因，错误码和 `std::expected` 替代方案
3. **移动语义**：消除拷贝，noexcept 保证容器扩容效率
4. **智能指针**：unique_ptr 为默认，shared_ptr 慎用，weak_ptr 打破循环
5. **placement new / std::pmr**：自定义分配器的基石，标准库多态内存资源
6. **模板元编程**：SFINAE → Concepts 演进，CRTP 实现零开销静态多态
7. **现代类型系统**：std::optional、std::variant、std::span 在引擎中的实践
8. **内存序**：relaxed/acquire-release/seq_cst 的选择，Job System 的核心
9. **协程**：C++20 coroutines 简化异步编程和任务依赖
10. **数据导向设计**：SoA 布局、缓存行对齐、位操作标志、编译期计算

**关键原则：**
- **先正确，后优化**：先用标准库和简单方案，性能分析确认瓶颈后再引入复杂技术
- **测量一切**：自定义分配器、无锁结构、模板元编程都有代价，必须有数据支撑
- **可读性优先**：模板元编程深度每增加一层，维护成本指数级增长
- **安全默认**：不写 `noexcept`、不写 `override`、不写 `explicit` 都是隐患
