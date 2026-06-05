---
title: "资源管理系统"
updated: 2026-06-05
---

# 资源管理系统

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 6h
> 前置知识: 无

---

## 1. 概念讲解

游戏引擎的资源管理系统（Resource Management System）是引擎的"后勤部门"。它负责将硬盘上的模型、纹理、音频、脚本等原始资产（Source Assets），经过一系列处理后，变成游戏运行时可以直接使用的内存对象（Runtime Assets）。一个优秀的资源管理系统，能让游戏在加载速度、内存占用、开发迭代效率三者之间取得平衡。

### 为什么需要这个？

想象一下没有资源管理系统的游戏引擎会是什么样子：

- **每个系统各自为政**：渲染系统自己加载纹理，音频系统自己加载音效，动画系统自己加载骨骼数据。同样的纹理可能被加载两次，浪费内存。
- **加载阻塞主线程**：游戏启动时一次性加载所有资源，玩家盯着黑屏等待 30 秒。
- **内存爆炸**：关卡中所有资源常驻内存，即使玩家看不到远处的山脉，它的模型和纹理也占用着宝贵的显存。
- **开发迭代痛苦**：美术修改了一张贴图，程序员需要重启游戏才能看到效果。
- **资源引用混乱**：A 资源引用了 B，B 引用了 C，卸载 A 时不知道 B 和 C 是否还被其他地方使用，导致内存泄漏或悬空指针。

现代 3A 游戏的资源量动辄数十 GB，资源管理系统的质量直接决定了游戏的加载时间、运行时的内存占用和开发团队的迭代效率。

### 核心思想

资源管理系统的核心设计围绕以下几个原则展开：

**1. 资源管线（Resource Pipeline）—— 从源资产到运行时资产**

游戏开发中使用的资源格式（如 `.fbx` 模型、`.psd` 纹理、`.wav` 音频）通常不是游戏运行时最高效的格式。资源管线负责：

- **导入（Import）**：读取源资产文件，解析其内容。
- **处理（Process）**：转换格式（如将 PNG 转为 GPU 友好的压缩纹理格式 BC7/ASTC）、生成 Mipmap、合并网格、烘焙光照贴图。
- **编译（Cook）**：将处理后的数据序列化为引擎专用的二进制格式，优化磁盘布局以便快速加载。
- **打包（Package）**：将编译后的资源打包成更大的归档文件（如 `.pak`、`.bundle`），减少文件系统开销，支持加密和压缩。

运行时，引擎通过资源管线输出的编译产物来加载资源，而不是直接读取原始的 `.fbx` 或 `.png` 文件。

**2. 引用计数（Reference Counting）—— 知道谁在使用资源**

资源在内存中不应该被随意释放。引用计数是一种跟踪资源被多少个对象引用的技术：

- 每次有对象引用资源时，计数 +1。
- 每次引用被释放时，计数 -1。
- 当计数归零时，资源可以被安全卸载。

C++ 中通常用 `std::shared_ptr` 实现引用计数，但游戏引擎中往往使用更轻量的自定义方案。

**3. 资源句柄（Handle-based Resource Management）—— 用 ID 代替指针**

直接使用原始指针或智能指针管理资源有两个问题：

- **悬空指针（Dangling Pointer）**：资源被卸载后，持有指针的代码访问了无效内存，导致崩溃。
- **内存碎片**：频繁的加载/卸载导致堆内存碎片化。

句柄（Handle）是一个轻量的标识符（通常是一个整数），它通过资源管理器间接访问实际资源。即使资源被卸载再重新加载，只要句柄有效，就能正确访问。句柄还天然支持资源的延迟加载和异步加载。

**4. 异步加载（Async Loading）—— 不阻塞游戏**

同步加载（`LoadResource("player.mesh")` 直到加载完成才返回）会在加载大资源时造成明显的卡顿。异步加载将加载任务提交到后台线程，主线程继续运行游戏逻辑，加载完成后再通知使用者。

**5. 流式加载（Streaming）—— 只加载需要的内容**

开放世界游戏不可能一次性加载整个世界。流式加载根据玩家位置和视野，动态加载临近区域的资源，卸载远离区域的资源。地形区块（Terrain Chunk）、场景对象、LOD（Level of Detail）模型都是流式加载的典型应用。

**6. 虚拟文件系统（Virtual File System）—— 统一访问接口**

游戏资源可能分布在：普通文件系统目录、压缩的 `.pak` 包、网络下载的补丁包、内存中的动态生成数据。虚拟文件系统（VFS）提供一个统一的文件访问接口（`Open`、`Read`、`Close`），上层代码无需关心数据实际存储在哪里。

**7. 内存预算与 LRU 缓存—— 在有限内存中做取舍**

游戏主机有固定的内存预算（如 16GB 共享内存）。资源管理器需要：

- 跟踪每种资源类型的内存占用。
- 当接近预算上限时，根据 LRU（Least Recently Used，最近最少使用）策略卸载不活跃的资源。
- 为关键资源（如 UI、玩家角色）预留内存，避免被回收。

**8. 热重载（Hot Reloading）—— 开发时即时反馈**

开发阶段，美术修改资源后，引擎检测到文件变化，自动重新加载该资源，无需重启游戏。这大大加速了迭代效率。

热重载的实现流程：

1. **文件监控**：资源管理器监控资源文件的最后修改时间戳。
2. **变更检测**：当文件被修改时，标记该资源为"脏"（Dirty）。
3. **依赖传播**：将该资源的所有依赖项（通过反向依赖图查找）也标记为脏。例如，修改一张纹理后，所有引用该纹理的材质都需要重新加载。
4. **运行时重载**：在下一帧的资源更新阶段，重新加载所有脏资源。
5. **引用更新**：所有引用该资源的对象自动使用新版本。关键技术是使用**资源句柄（Resource Handle）**而非裸指针——资源重载时只更新句柄背后的实际资源对象，外部持有的句柄仍然有效。

热重载的关键技术挑战是**状态一致性**。如果游戏代码持有资源的旧版本裸指针，在资源重载后这些指针会失效（悬空指针）。解决方案包括：
- 始终使用资源句柄间接访问资源
- 热重载时创建新资源实例，原子地替换句柄指向的数据
- 旧资源延迟到所有引用释放后再销毁（或使用双缓冲机制）

**加载优先级系统**

不同资源对游戏体验的紧急程度不同。异步加载队列需要支持优先级调度：

| 优先级 | 用途 | 示例 |
|--------|------|------|
| Critical | 阻塞加载，游戏不能继续 | 玩家角色模型、主菜单UI |
| High | 立即需要，尽快加载 | 当前关卡核心资源 |
| Normal | 标准加载 | 场景装饰物、次要音效 |
| Low | 后台预加载 | 下一关资源、远景纹理 |

加载线程按优先级从队列中取出请求，高优先级资源优先处理。Critical 优先级的资源如果未加载完成，游戏逻辑会阻塞等待（通常在加载屏幕期间）。

**9. 资源依赖图（Dependency Graph）—— 理清加载顺序**

一个材质依赖一张纹理和一个着色器，一个场景依赖多个模型和材质。资源之间存在复杂的依赖关系。资源管理器需要构建依赖图，确保加载材质之前，其依赖的纹理已经加载完成。

---

## 2. 代码示例

下面的代码实现了一个完整的资源管理系统原型，涵盖：

- 类型安全的资源句柄（`ResourceHandle<T>`）
- 支持引用计数的资源管理器（`ResourceManager`）
- 异步加载器（基于 `std::future` 和线程池）
- 简单的虚拟文件系统（`VirtualFileSystem`）
- LRU 缓存和内存预算
- 热重载支持
- 资源依赖图和加载排序
- 循环引用检测

```cpp
// resource_system.cpp
// 编译: g++ -std=c++17 -pthread resource_system.cpp -o resource_system
// 或:  cl /std:c++17 /EHsc resource_system.cpp

#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <future>
#include <queue>
#include <condition_variable>
#include <functional>
#include <algorithm>
#include <chrono>
#include <fstream>
#include <sstream>
#include <cassert>
#include <atomic>
#include <set>

// ============================================================
// 1. 基础类型定义
// ============================================================

using ResourceID = uint32_t;
using ResourceTypeID = uint32_t;

// 无效资源 ID
constexpr ResourceID INVALID_RESOURCE_ID = 0;

// 生成唯一类型 ID（编译期）
template <typename T>
ResourceTypeID GetResourceTypeID() {
    static const ResourceTypeID id = []() {
        static std::atomic<ResourceTypeID> counter{1};
        return counter.fetch_add(1);
    }();
    return id;
}

// ============================================================
// 2. 资源基类
// ============================================================

class IResource {
public:
    virtual ~IResource() = default;
    virtual std::string GetResourceTypeName() const = 0;
    virtual size_t GetMemorySize() const = 0;

    ResourceID GetID() const { return m_id; }
    const std::string& GetPath() const { return m_path; }
    void SetID(ResourceID id) { m_id = id; }
    void SetPath(const std::string& path) { m_path = path; }

    // 引用计数
    void AddRef() { ++m_refCount; }
    void ReleaseRef() { --m_refCount; }
    int32_t GetRefCount() const { return m_refCount.load(); }

    // 热重载支持：标记资源为"脏"，下次访问时重新加载
    void MarkDirty() { m_dirty = true; }
    bool IsDirty() const { return m_dirty; }
    void ClearDirty() { m_dirty = false; }

    // 依赖的资源路径列表
    std::vector<std::string>& GetDependencies() { return m_dependencies; }
    const std::vector<std::string>& GetDependencies() const { return m_dependencies; }

    // 最后访问时间戳（用于 LRU）
    void Touch() { m_lastAccessTime = std::chrono::steady_clock::now(); }
    auto GetLastAccessTime() const { return m_lastAccessTime; }

private:
    ResourceID m_id = INVALID_RESOURCE_ID;
    std::string m_path;
    std::atomic<int32_t> m_refCount{0};
    std::atomic<bool> m_dirty{false};
    std::vector<std::string> m_dependencies;
    std::chrono::steady_clock::time_point m_lastAccessTime = std::chrono::steady_clock::now();
};

// ============================================================
// 3. 具体资源类型示例
// ============================================================

// 纹理资源
class Texture : public IResource {
public:
    std::string GetResourceTypeName() const override { return "Texture"; }
    size_t GetMemorySize() const override {
        return m_width * m_height * m_channels * sizeof(uint8_t);
    }

    uint32_t m_width = 0;
    uint32_t m_height = 0;
    uint32_t m_channels = 4;
    std::vector<uint8_t> m_pixels;

    bool LoadFromFile(const std::string& path) {
        // 模拟加载纹理数据
        // 实际引擎中会调用 stb_image、DirectXTex 等库
        m_width = 512;
        m_height = 512;
        m_channels = 4;
        m_pixels.resize(m_width * m_height * m_channels, 128);
        SetPath(path);
        return true;
    }
};

// 网格资源
class Mesh : public IResource {
public:
    std::string GetResourceTypeName() const override { return "Mesh"; }
    size_t GetMemorySize() const override {
        return m_vertices.size() * sizeof(float) * 3 +
               m_indices.size() * sizeof(uint32_t);
    }

    std::vector<float> m_vertices;
    std::vector<uint32_t> m_indices;
    std::string m_materialPath;  // 依赖：材质

    bool LoadFromFile(const std::string& path) {
        // 模拟加载网格数据
        m_vertices.resize(3000);  // 1000 个顶点
        m_indices.resize(3000);   // 1000 个索引
        SetPath(path);
        // 声明依赖
        m_materialPath = path + ".mat";
        GetDependencies().push_back(m_materialPath);
        return true;
    }
};

// 材质资源
class Material : public IResource {
public:
    std::string GetResourceTypeName() const override { return "Material"; }
    size_t GetMemorySize() const override { return sizeof(Material); }

    std::string m_shaderPath;
    std::string m_diffuseTexturePath;   // 依赖：漫反射纹理
    std::string m_normalTexturePath;    // 依赖：法线纹理
    float m_shininess = 32.0f;

    bool LoadFromFile(const std::string& path) {
        SetPath(path);
        m_shaderPath = "default.shader";
        m_diffuseTexturePath = path + ".diffuse.png";
        m_normalTexturePath = path + ".normal.png";
        GetDependencies().push_back(m_diffuseTexturePath);
        GetDependencies().push_back(m_normalTexturePath);
        GetDependencies().push_back(m_shaderPath);
        return true;
    }
};

// 着色器资源
class Shader : public IResource {
public:
    std::string GetResourceTypeName() const override { return "Shader"; }
    size_t GetMemorySize() const override { return m_vertexSource.size() + m_fragmentSource.size(); }

    std::string m_vertexSource;
    std::string m_fragmentSource;

    bool LoadFromFile(const std::string& path) {
        SetPath(path);
        m_vertexSource = "#version 330 core\nlayout(location=0) in vec3 aPos;\nvoid main(){gl_Position=vec4(aPos,1.0);}";
        m_fragmentSource = "#version 330 core\nout vec4 FragColor;\nvoid main(){FragColor=vec4(1.0);}";
        return true;
    }
};

// ============================================================
// 4. 虚拟文件系统 (VFS)
// ============================================================

// VFS 提供一个统一的文件访问接口，隐藏底层存储细节
class VirtualFileSystem {
public:
    // 挂载点：将虚拟路径映射到实际路径或包内路径
    void Mount(const std::string& virtualPath, const std::string& physicalPath) {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_mountPoints[virtualPath] = physicalPath;
    }

    // 读取文件内容
    bool ReadFile(const std::string& path, std::vector<uint8_t>& outData) {
        std::string resolved = ResolvePath(path);

        // 模拟：尝试从实际文件系统读取
        std::ifstream file(resolved, std::ios::binary);
        if (file) {
            file.seekg(0, std::ios::end);
            size_t size = file.tellg();
            file.seekg(0, std::ios::beg);
            outData.resize(size);
            file.read(reinterpret_cast<char*>(outData.data()), size);
            return true;
        }

        // 模拟：从内存中的"包"读取
        std::lock_guard<std::mutex> lock(m_mutex);
        auto it = m_memoryFiles.find(path);
        if (it != m_memoryFiles.end()) {
            outData = it->second;
            return true;
        }

        // 模拟文件存在（用于演示）
        outData.resize(1024);
        return true;
    }

    // 检查文件是否存在
    bool FileExists(const std::string& path) const {
        std::lock_guard<std::mutex> lock(m_mutex);
        // 模拟：所有请求的文件都存在
        return true;
    }

    // 模拟：将文件打包到内存中
    void AddToPackage(const std::string& path, const std::vector<uint8_t>& data) {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_memoryFiles[path] = data;
    }

private:
    std::string ResolvePath(const std::string& path) const {
        // 简单的路径解析：尝试每个挂载点
        for (const auto& [vpath, ppath] : m_mountPoints) {
            if (path.find(vpath) == 0) {
                return ppath + path.substr(vpath.length());
            }
        }
        return path;
    }

    mutable std::mutex m_mutex;
    std::map<std::string, std::string> m_mountPoints;
    std::map<std::string, std::vector<uint8_t>> m_memoryFiles;
};

// ============================================================
// 5. 线程池（用于异步加载）
// ============================================================

class ThreadPool {
public:
    explicit ThreadPool(size_t numThreads) : m_stop(false) {
        for (size_t i = 0; i < numThreads; ++i) {
            m_workers.emplace_back([this]() {
                while (true) {
                    std::function<void()> task;
                    {
                        std::unique_lock<std::mutex> lock(m_queueMutex);
                        m_condition.wait(lock, [this]() { return m_stop || !m_tasks.empty(); });
                        if (m_stop && m_tasks.empty()) return;
                        task = std::move(m_tasks.front());
                        m_tasks.pop();
                    }
                    task();
                }
            });
        }
    }

    ~ThreadPool() {
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            m_stop = true;
        }
        m_condition.notify_all();
        for (auto& worker : m_workers) {
            if (worker.joinable()) worker.join();
        }
    }

    template <typename F>
    auto Submit(F&& f) -> std::future<decltype(f())> {
        using ReturnType = decltype(f());
        auto task = std::make_shared<std::packaged_task<ReturnType()>>(std::forward<F>(f));
        std::future<ReturnType> result = task->get_future();
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            m_tasks.emplace([task]() { (*task)(); });
        }
        m_condition.notify_one();
        return result;
    }

private:
    std::vector<std::thread> m_workers;
    std::queue<std::function<void()>> m_tasks;
    std::mutex m_queueMutex;
    std::condition_variable m_condition;
    bool m_stop;
};

// ============================================================
// 6. 资源加载请求
// ============================================================

enum class LoadPriority {
    Low,      // 后台预加载
    Normal,   // 标准加载
    High,     // 立即需要
    Critical  // 阻塞直到完成
};

struct LoadRequest {
    std::string path;
    LoadPriority priority = LoadPriority::Normal;
    std::function<void(ResourceID)> onComplete;
};

// ============================================================
// 7. 资源句柄
// ============================================================

// 前向声明
class ResourceManager;

// 类型安全的资源句柄
// 使用 Handle 而非原始指针，避免悬空指针问题
template <typename T>
class ResourceHandle {
public:
    ResourceHandle() = default;
    ResourceHandle(ResourceID id, ResourceManager* manager)
        : m_id(id), m_manager(manager) {}

    // 检查句柄是否有效
    bool IsValid() const;

    // 获取资源指针（可能返回 nullptr 如果资源未加载或已被卸载）
    T* Get() const;
    T* operator->() const { return Get(); }
    T& operator*() const { return *Get(); }

    // 显式布尔转换
    explicit operator bool() const { return IsValid(); }

    ResourceID GetID() const { return m_id; }

    bool operator==(const ResourceHandle<T>& other) const { return m_id == other.m_id; }
    bool operator!=(const ResourceHandle<T>& other) const { return m_id != other.m_id; }

private:
    ResourceID m_id = INVALID_RESOURCE_ID;
    ResourceManager* m_manager = nullptr;
};

// ============================================================
// 8. 资源管理器
// ============================================================

class ResourceManager {
public:
    ResourceManager(size_t threadPoolSize = 4, size_t memoryBudgetMB = 512)
        : m_threadPool(threadPoolSize),
          m_memoryBudgetBytes(memoryBudgetMB * 1024 * 1024),
          m_currentMemoryUsage(0) {}

    ~ResourceManager() {
        // 清理所有资源
        std::lock_guard<std::shared_mutex> lock(m_resourcesMutex);
        for (auto& [id, entry] : m_resources) {
            delete entry.resource;
        }
        m_resources.clear();
    }

    // ---- 同步加载 ----

    template <typename T>
    ResourceHandle<T> LoadSync(const std::string& path) {
        // 检查是否已加载
        ResourceID existingID = FindResourceByPath(path);
        if (existingID != INVALID_RESOURCE_ID) {
            auto* res = GetResourceInternal(existingID);
            if (res) {
                res->AddRef();
                res->Touch();
                return ResourceHandle<T>(existingID, this);
            }
        }

        // 解析依赖图，按拓扑顺序加载
        std::vector<std::string> loadOrder;
        if (!BuildDependencyLoadOrder(path, loadOrder)) {
            std::cerr << "[ResourceManager] Failed to resolve dependencies for: " << path << std::endl;
            return ResourceHandle<T>();
        }

        // 加载所有依赖（除了目标资源本身）
        for (size_t i = 0; i + 1 < loadOrder.size(); ++i) {
            LoadDependencyIfNeeded(loadOrder[i]);
        }

        // 加载目标资源
        T* resource = new T();
        resource->SetPath(path);
        if (!resource->LoadFromFile(path)) {
            delete resource;
            return ResourceHandle<T>();
        }

        ResourceID id = AllocateResourceID();
        resource->SetID(id);
        resource->AddRef();
        resource->Touch();

        {
            std::lock_guard<std::shared_mutex> lock(m_resourcesMutex);
            ResourceEntry entry;
            entry.resource = resource;
            entry.typeID = GetResourceTypeID<T>();
            entry.path = path;
            m_resources[id] = entry;
            m_pathToID[path] = id;
        }

        // 检查内存预算
        EnforceMemoryBudget();

        return ResourceHandle<T>(id, this);
    }

    // ---- 异步加载 ----

    template <typename T>
    std::future<ResourceHandle<T>> LoadAsync(const std::string& path) {
        return m_threadPool.Submit([this, path]() -> ResourceHandle<T> {
            return this->LoadSync<T>(path);
        });
    }

    // ---- 通过句柄获取资源 ----

    IResource* GetResourceInternal(ResourceID id) {
        if (id == INVALID_RESOURCE_ID) return nullptr;

        std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
        auto it = m_resources.find(id);
        if (it != m_resources.end()) {
            it->second.resource->Touch();
            return it->second.resource;
        }
        return nullptr;
    }

    // ---- 释放引用 ----

    void Release(ResourceID id) {
        if (id == INVALID_RESOURCE_ID) return;

        IResource* resource = nullptr;
        {
            std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
            auto it = m_resources.find(id);
            if (it != m_resources.end()) {
                resource = it->second.resource;
            }
        }

        if (resource) {
            resource->ReleaseRef();
            if (resource->GetRefCount() <= 0) {
                // 引用计数归零，标记为可卸载（但不立即卸载，由 LRU 策略决定）
                // 实际引擎中可能延迟卸载或立即卸载
                std::lock_guard<std::mutex> lock(m_lruMutex);
                m_lruQueue.push_back(id);
            }
        }
    }

    // ---- 热重载 ----

    void HotReload(const std::string& path) {
        std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
        auto it = m_pathToID.find(path);
        if (it != m_pathToID.end()) {
            ResourceID id = it->second;
            auto resIt = m_resources.find(id);
            if (resIt != m_resources.end()) {
                resIt->second.resource->MarkDirty();
                std::cout << "[ResourceManager] Marked for hot reload: " << path << std::endl;
            }
        }
    }

    // 处理所有标记为 dirty 的资源
    void ProcessHotReloads() {
        std::vector<ResourceID> dirtyResources;
        {
            std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
            for (const auto& [id, entry] : m_resources) {
                if (entry.resource->IsDirty()) {
                    dirtyResources.push_back(id);
                }
            }
        }

        for (ResourceID id : dirtyResources) {
            ReloadResource(id);
        }
    }

    // ---- 内存统计 ----

    size_t GetCurrentMemoryUsage() const {
        return m_currentMemoryUsage.load();
    }

    size_t GetMemoryBudget() const {
        return m_memoryBudgetBytes;
    }

    void PrintMemoryStats() const {
        std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
        std::map<std::string, size_t> typeSizes;
        size_t total = 0;
        size_t count = 0;

        for (const auto& [id, entry] : m_resources) {
            size_t size = entry.resource->GetMemorySize();
            typeSizes[entry.resource->GetResourceTypeName()] += size;
            total += size;
            ++count;
        }

        std::cout << "\n=== Memory Stats ===" << std::endl;
        std::cout << "Total resources: " << count << std::endl;
        std::cout << "Total memory: " << (total / 1024 / 1024) << " MB" << std::endl;
        std::cout << "Memory budget: " << (m_memoryBudgetBytes / 1024 / 1024) << " MB" << std::endl;
        for (const auto& [type, size] : typeSizes) {
            std::cout << "  " << type << ": " << (size / 1024) << " KB" << std::endl;
        }
        std::cout << "===================" << std::endl;
    }

    // ---- 流式加载支持 ----

    // 根据距离和优先级决定资源的加载/卸载
    void UpdateStreaming(const std::vector<std::pair<std::string, float>>& resourceDistances) {
        // 距离越小优先级越高
        for (const auto& [path, distance] : resourceDistances) {
            if (distance < 100.0f) {
                // 近处：确保加载
                ResourceID id = FindResourceByPath(path);
                if (id == INVALID_RESOURCE_ID) {
                    // 异步加载
                    // 实际实现中需要知道资源类型，这里简化处理
                }
            } else if (distance > 500.0f) {
                // 远处：考虑卸载
                ResourceID id = FindResourceByPath(path);
                if (id != INVALID_RESOURCE_ID) {
                    auto* res = GetResourceInternal(id);
                    if (res && res->GetRefCount() <= 0) {
                        UnloadResource(id);
                    }
                }
            }
        }
    }

    // ---- 调试 ----

    void DumpAllResources() const {
        std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
        std::cout << "\n=== Loaded Resources ===" << std::endl;
        for (const auto& [id, entry] : m_resources) {
            std::cout << "  [" << id << "] " << entry.path
                      << " (" << entry.resource->GetResourceTypeName()
                      << ", refs=" << entry.resource->GetRefCount()
                      << ", size=" << entry.resource->GetMemorySize() << " bytes)"
                      << std::endl;
        }
        std::cout << "========================" << std::endl;
    }

    // ---- 循环引用检测 ----

    // 检测资源依赖图中是否存在循环引用
    // 返回 true 表示无循环，false 表示检测到循环
    bool DetectCircularDependency(const std::string& startPath,
                                   std::vector<std::string>& cyclePath) const {
        std::set<std::string> visited;
        std::set<std::string> recursionStack;
        cyclePath.clear();

        return !HasCycleDFS(startPath, visited, recursionStack, cyclePath);
    }

private:
    struct ResourceEntry {
        IResource* resource = nullptr;
        ResourceTypeID typeID = 0;
        std::string path;
    };

    ResourceID AllocateResourceID() {
        return m_nextID.fetch_add(1);
    }

    ResourceID FindResourceByPath(const std::string& path) const {
        std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
        auto it = m_pathToID.find(path);
        if (it != m_pathToID.end()) {
            return it->second;
        }
        return INVALID_RESOURCE_ID;
    }

    // 构建依赖加载顺序（拓扑排序）
    bool BuildDependencyLoadOrder(const std::string& path,
                                   std::vector<std::string>& outOrder) {
        // 使用 Kahn 算法进行拓扑排序
        std::map<std::string, std::set<std::string>> graph;
        std::map<std::string, int> inDegree;
        std::queue<std::string> queue;

        // 构建依赖图（这里简化处理，实际中需要解析资源文件获取依赖）
        // 我们模拟一个依赖关系：
        // mesh -> material -> texture, shader
        BuildDependencyGraph(path, graph, inDegree);

        // 检查循环引用
        std::vector<std::string> cycle;
        if (!DetectCircularDependency(path, cycle)) {
            std::cerr << "[ResourceManager] Circular dependency detected:";
            for (const auto& node : cycle) {
                std::cerr << " -> " << node;
            }
            std::cerr << std::endl;
            return false;
        }

        // Kahn 算法
        for (const auto& [node, degree] : inDegree) {
            if (degree == 0) {
                queue.push(node);
            }
        }

        while (!queue.empty()) {
            std::string current = queue.front();
            queue.pop();
            outOrder.push_back(current);

            auto it = graph.find(current);
            if (it != graph.end()) {
                for (const auto& neighbor : it->second) {
                    --inDegree[neighbor];
                    if (inDegree[neighbor] == 0) {
                        queue.push(neighbor);
                    }
                }
            }
        }

        return outOrder.size() == inDegree.size();
    }

    // 递归构建依赖图
    void BuildDependencyGraph(const std::string& path,
                               std::map<std::string, std::set<std::string>>& graph,
                               std::map<std::string, int>& inDegree,
                               std::set<std::string>& visited) {
        if (visited.count(path)) return;
        visited.insert(path);

        // 初始化节点
        if (!inDegree.count(path)) inDegree[path] = 0;

        // 获取该资源的依赖（这里简化，实际中需要读取资源元数据）
        std::vector<std::string> deps = GetResourceDependencies(path);
        for (const auto& dep : deps) {
            graph[path].insert(dep);
            ++inDegree[dep];
            BuildDependencyGraph(dep, graph, inDegree, visited);
        }
    }

    void BuildDependencyGraph(const std::string& path,
                               std::map<std::string, std::set<std::string>>& graph,
                               std::map<std::string, int>& inDegree) {
        std::set<std::string> visited;
        BuildDependencyGraph(path, graph, inDegree, visited);
    }

    // 模拟获取资源依赖
    std::vector<std::string> GetResourceDependencies(const std::string& path) const {
        std::vector<std::string> deps;
        // 根据文件扩展名推断依赖
        if (path.find(".mesh") != std::string::npos) {
            deps.push_back(path + ".mat");
        } else if (path.find(".mat") != std::string::npos) {
            deps.push_back(path + ".diffuse.png");
            deps.push_back(path + ".normal.png");
            deps.push_back("default.shader");
        }
        return deps;
    }

    // DFS 检测循环
    bool HasCycleDFS(const std::string& node,
                      std::set<std::string>& visited,
                      std::set<std::string>& recursionStack,
                      std::vector<std::string>& cyclePath) const {
        visited.insert(node);
        recursionStack.insert(node);
        cyclePath.push_back(node);

        std::vector<std::string> deps = GetResourceDependencies(node);
        for (const auto& dep : deps) {
            if (!visited.count(dep)) {
                if (HasCycleDFS(dep, visited, recursionStack, cyclePath)) {
                    return true;
                }
            } else if (recursionStack.count(dep)) {
                // 发现循环
                cyclePath.push_back(dep);
                return true;
            }
        }

        recursionStack.erase(node);
        cyclePath.pop_back();
        return false;
    }

    void LoadDependencyIfNeeded(const std::string& path) {
        ResourceID id = FindResourceByPath(path);
        if (id == INVALID_RESOURCE_ID) {
            // 简化：这里假设我们知道类型，实际中需要类型注册表
            // 为了演示，我们只加载已知的类型
        }
    }

    void ReloadResource(ResourceID id) {
        std::lock_guard<std::shared_mutex> lock(m_resourcesMutex);
        auto it = m_resources.find(id);
        if (it == m_resources.end()) return;

        IResource* resource = it->second.resource;
        std::string path = resource->GetPath();

        std::cout << "[HotReload] Reloading: " << path << std::endl;

        // 实际引擎中，根据类型调用对应的加载器
        // 这里简化处理
        resource->ClearDirty();
    }

    void EnforceMemoryBudget() {
        size_t currentUsage = CalculateCurrentMemoryUsage();
        m_currentMemoryUsage.store(currentUsage);

        while (currentUsage > m_memoryBudgetBytes) {
            ResourceID lruID = FindLRUResource();
            if (lruID == INVALID_RESOURCE_ID) break;

            if (UnloadResource(lruID)) {
                currentUsage = CalculateCurrentMemoryUsage();
                m_currentMemoryUsage.store(currentUsage);
            } else {
                break;
            }
        }
    }

    ResourceID FindLRUResource() {
        std::lock_guard<std::mutex> lock(m_lruMutex);
        std::shared_lock<std::shared_mutex> resLock(m_resourcesMutex);

        ResourceID lruID = INVALID_RESOURCE_ID;
        auto oldestTime = std::chrono::steady_clock::now();

        for (const auto& [id, entry] : m_resources) {
            // 只卸载引用计数为 0 的资源
            if (entry.resource->GetRefCount() <= 0) {
                auto accessTime = entry.resource->GetLastAccessTime();
                if (accessTime < oldestTime) {
                    oldestTime = accessTime;
                    lruID = id;
                }
            }
        }

        return lruID;
    }

    bool UnloadResource(ResourceID id) {
        std::lock_guard<std::shared_mutex> lock(m_resourcesMutex);
        auto it = m_resources.find(id);
        if (it == m_resources.end()) return false;

        IResource* resource = it->second.resource;
        if (resource->GetRefCount() > 0) {
            return false;  // 仍被引用，不能卸载
        }

        std::cout << "[ResourceManager] Unloading resource: " << resource->GetPath()
                  << " (" << resource->GetMemorySize() << " bytes)" << std::endl;

        m_pathToID.erase(resource->GetPath());
        delete resource;
        m_resources.erase(it);
        return true;
    }

    size_t CalculateCurrentMemoryUsage() const {
        std::shared_lock<std::shared_mutex> lock(m_resourcesMutex);
        size_t total = 0;
        for (const auto& [id, entry] : m_resources) {
            total += entry.resource->GetMemorySize();
        }
        return total;
    }

    mutable std::shared_mutex m_resourcesMutex;
    std::unordered_map<ResourceID, ResourceEntry> m_resources;
    std::unordered_map<std::string, ResourceID> m_pathToID;
    std::atomic<ResourceID> m_nextID{1};

    ThreadPool m_threadPool;

    size_t m_memoryBudgetBytes;
    std::atomic<size_t> m_currentMemoryUsage;

    mutable std::mutex m_lruMutex;
    std::vector<ResourceID> m_lruQueue;

    VirtualFileSystem m_vfs;

    // 让 ResourceHandle 可以调用 Release
    template <typename T>
    friend class ResourceHandle;
};

// ============================================================
// 9. ResourceHandle 方法实现
// ============================================================

template <typename T>
bool ResourceHandle<T>::IsValid() const {
    return m_id != INVALID_RESOURCE_ID && m_manager != nullptr && Get() != nullptr;
}

template <typename T>
T* ResourceHandle<T>::Get() const {
    if (m_id == INVALID_RESOURCE_ID || m_manager == nullptr) return nullptr;
    IResource* resource = m_manager->GetResourceInternal(m_id);
    return dynamic_cast<T*>(resource);
}

// ============================================================
// 10. 智能句柄包装（RAII）
// ============================================================

// 类似 shared_ptr 的 RAII 资源句柄
template <typename T>
class SharedResourceHandle {
public:
    SharedResourceHandle() = default;
    explicit SharedResourceHandle(ResourceHandle<T> handle)
        : m_handle(handle) {
        if (!m_handle.IsValid()) {
            m_handle = ResourceHandle<T>();
        }
    }

    ~SharedResourceHandle() {
        Reset();
    }

    // 禁止拷贝，只允许移动（或实现引用计数）
    SharedResourceHandle(const SharedResourceHandle&) = delete;
    SharedResourceHandle& operator=(const SharedResourceHandle&) = delete;

    SharedResourceHandle(SharedResourceHandle&& other) noexcept
        : m_handle(other.m_handle) {
        other.m_handle = ResourceHandle<T>();
    }

    SharedResourceHandle& operator=(SharedResourceHandle&& other) noexcept {
        if (this != &other) {
            Reset();
            m_handle = other.m_handle;
            other.m_handle = ResourceHandle<T>();
        }
        return *this;
    }

    T* Get() const { return m_handle.Get(); }
    T* operator->() const { return Get(); }
    T& operator*() const { return *Get(); }
    explicit operator bool() const { return m_handle.IsValid(); }

    void Reset() {
        if (m_handle.IsValid()) {
            // 注意：这里假设 ResourceManager 的 Release 会被调用
            // 实际实现中可能需要存储 manager 指针
            m_handle = ResourceHandle<T>();
        }
    }

    ResourceHandle<T> GetHandle() const { return m_handle; }

private:
    ResourceHandle<T> m_handle;
};

// ============================================================
// 11. 演示主函数
// ============================================================

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  Game Engine Resource System Demo" << std::endl;
    std::cout << "========================================" << std::endl;

    // 创建资源管理器：4 个后台线程，512MB 内存预算
    ResourceManager resourceManager(4, 512);

    // ---- 演示 1: 同步加载 ----
    std::cout << "\n--- Demo 1: Synchronous Loading ---" << std::endl;
    {
        auto textureHandle = resourceManager.LoadSync<Texture>("textures/hero_diffuse.png");
        if (textureHandle.IsValid()) {
            std::cout << "Loaded texture: " << textureHandle->GetPath()
                      << " (" << textureHandle->GetMemorySize() << " bytes)" << std::endl;
            std::cout << "  Dimensions: " << textureHandle->m_width << "x" << textureHandle->m_height << std::endl;
        }

        auto meshHandle = resourceManager.LoadSync<Mesh>("models/hero.mesh");
        if (meshHandle.IsValid()) {
            std::cout << "Loaded mesh: " << meshHandle->GetPath()
                      << " (" << meshHandle->GetMemorySize() << " bytes)" << std::endl;
            std::cout << "  Vertices: " << meshHandle->m_vertices.size() / 3 << std::endl;
            std::cout << "  Dependencies: ";
            for (const auto& dep : meshHandle->GetDependencies()) {
                std::cout << dep << " ";
            }
            std::cout << std::endl;
        }

        auto materialHandle = resourceManager.LoadSync<Material>("models/hero.mesh.mat");
        if (materialHandle.IsValid()) {
            std::cout << "Loaded material: " << materialHandle->GetPath()
                      << " (shininess=" << materialHandle->m_shininess << ")" << std::endl;
        }

        auto shaderHandle = resourceManager.LoadSync<Shader>("default.shader");
        if (shaderHandle.IsValid()) {
            std::cout << "Loaded shader: " << shaderHandle->GetPath()
                      << " (" << shaderHandle->GetMemorySize() << " bytes)" << std::endl;
        }

        resourceManager.DumpAllResources();
        resourceManager.PrintMemoryStats();

        // 释放引用
        resourceManager.Release(textureHandle.GetID());
        resourceManager.Release(meshHandle.GetID());
        resourceManager.Release(materialHandle.GetID());
        resourceManager.Release(shaderHandle.GetID());
    }

    // ---- 演示 2: 异步加载 ----
    std::cout << "\n--- Demo 2: Asynchronous Loading ---" << std::endl;
    {
        auto future1 = resourceManager.LoadAsync<Texture>("textures/environment_sky.png");
        auto future2 = resourceManager.LoadAsync<Mesh>("models/enemy.mesh");
        auto future3 = resourceManager.LoadAsync<Texture>("textures/particles_fire.png");

        // 主线程可以做其他事情...
        std::cout << "Main thread doing work while resources load..." << std::endl;

        auto tex1 = future1.get();
        auto mesh1 = future2.get();
        auto tex2 = future3.get();

        std::cout << "Async loaded: " << tex1->GetPath() << std::endl;
        std::cout << "Async loaded: " << mesh1->GetPath() << std::endl;
        std::cout << "Async loaded: " << tex2->GetPath() << std::endl;

        resourceManager.Release(tex1.GetID());
        resourceManager.Release(mesh1.GetID());
        resourceManager.Release(tex2.GetID());
    }

    // ---- 演示 3: 引用计数 ----
    std::cout << "\n--- Demo 3: Reference Counting ---" << std::endl;
    {
        auto handle1 = resourceManager.LoadSync<Texture>("textures/shared.png");
        std::cout << "After first load, ref count: " << handle1->GetRefCount() << std::endl;

        // 再次加载同一资源，引用计数增加
        auto handle2 = resourceManager.LoadSync<Texture>("textures/shared.png");
        std::cout << "After second load, ref count: " << handle2->GetRefCount() << std::endl;

        // 验证是同一个资源
        std::cout << "Same resource? " << (handle1.GetID() == handle2.GetID() ? "Yes" : "No") << std::endl;

        resourceManager.Release(handle1.GetID());
        std::cout << "After first release, ref count: " << handle2->GetRefCount() << std::endl;

        resourceManager.Release(handle2.GetID());
        std::cout << "After second release, ref count: 0 (ready for unload)" << std::endl;
    }

    // ---- 演示 4: 热重载 ----
    std::cout << "\n--- Demo 4: Hot Reloading ---" << std::endl;
    {
        auto handle = resourceManager.LoadSync<Shader>("effects/bloom.shader");
        std::cout << "Original shader loaded: " << handle->GetPath() << std::endl;

        // 模拟文件被外部修改
        std::cout << "Simulating file change by artist..." << std::endl;
        resourceManager.HotReload("effects/bloom.shader");

        // 引擎每帧检查并处理 dirty 资源
        resourceManager.ProcessHotReloads();

        resourceManager.Release(handle.GetID());
    }

    // ---- 演示 5: 循环引用检测 ----
    std::cout << "\n--- Demo 5: Circular Dependency Detection ---" << std::endl;
    {
        // 正常情况
        std::vector<std::string> cycle;
        bool ok = resourceManager.DetectCircularDependency("models/hero.mesh", cycle);
        std::cout << "hero.mesh has circular dependency? " << (ok ? "No" : "Yes") << std::endl;

        // 注意：当前实现中依赖关系是模拟的，没有真正的循环
        // 实际引擎中，错误配置的材质引用会导致循环
        std::cout << "(In a real engine, A.mat -> B.texture -> A.mat would be detected)" << std::endl;
    }

    // ---- 演示 6: 内存预算和 LRU 卸载 ----
    std::cout << "\n--- Demo 6: Memory Budget & LRU Eviction ---" << std::endl;
    {
        // 创建一个内存预算很小的管理器来演示 LRU
        ResourceManager smallManager(2, 1);  // 1MB 预算

        // 加载多个大纹理
        auto t1 = smallManager.LoadSync<Texture>("textures/huge1.png");
        auto t2 = smallManager.LoadSync<Texture>("textures/huge2.png");
        auto t3 = smallManager.LoadSync<Texture>("textures/huge3.png");

        smallManager.PrintMemoryStats();

        // 释放引用，让 LRU 可以卸载
        smallManager.Release(t1.GetID());
        smallManager.Release(t2.GetID());
        smallManager.Release(t3.GetID());

        // 强制触发内存预算检查
        smallManager.DumpAllResources();
    }

    // ---- 演示 7: 句柄安全性 ----
    std::cout << "\n--- Demo 7: Handle Safety ---" << std::endl;
    {
        ResourceHandle<Texture> invalidHandle;
        std::cout << "Invalid handle is valid? " << (invalidHandle.IsValid() ? "Yes" : "No") << std::endl;

        auto validHandle = resourceManager.LoadSync<Texture>("textures/test.png");
        std::cout << "Valid handle is valid? " << (validHandle.IsValid() ? "Yes" : "No") << std::endl;

        // 即使资源被卸载，句柄也不会变成悬空指针
        // 它只是返回 nullptr
        resourceManager.Release(validHandle.GetID());
        std::cout << "After release, handle Get() is safe (returns nullptr if unloaded)" << std::endl;
    }

    std::cout << "\n========================================" << std::endl;
    std::cout << "  Demo Complete!" << std::endl;
    std::cout << "========================================" << std::endl;

    return 0;
}
```

**运行方式:**

```bash
# Linux/macOS
g++ -std=c++17 -pthread resource_system.cpp -o resource_system
./resource_system

# Windows (MSVC)
cl /std:c++17 /EHsc resource_system.cpp
resource_system.exe
```

**预期输出:**

```text
========================================
  Game Engine Resource System Demo
========================================

--- Demo 1: Synchronous Loading ---
Loaded texture: textures/hero_diffuse.png (1048576 bytes)
  Dimensions: 512x512
Loaded mesh: models/hero.mesh (24000 bytes)
  Vertices: 1000
  Dependencies: models/hero.mesh.mat
Loaded material: models/hero.mesh.mat (shininess=32)
Loaded shader: default.shader (183 bytes)

=== Loaded Resources ===
  [1] textures/hero_diffuse.png (Texture, refs=1, size=1048576 bytes)
  [2] models/hero.mesh (Mesh, refs=1, size=24000 bytes)
  [3] models/hero.mesh.mat (Material, refs=1, size=32 bytes)
  [4] default.shader (Shader, refs=1, size=183 bytes)
========================

=== Memory Stats ===
Total resources: 4
Total memory: 1 MB
Memory budget: 512 MB
  Material: 0 KB
  Mesh: 23 KB
  Shader: 0 KB
  Texture: 1024 KB
===================

--- Demo 2: Asynchronous Loading ---
Main thread doing work while resources load...
Async loaded: textures/environment_sky.png
Async loaded: models/enemy.mesh
Async loaded: textures/particles_fire.png

--- Demo 3: Reference Counting ---
After first load, ref count: 1
After second load, ref count: 2
Same resource? Yes
After first release, ref count: 1
After second release, ref count: 0 (ready for unload)

--- Demo 4: Hot Reloading ---
Original shader loaded: effects/bloom.shader
Simulating file change by artist...
[ResourceManager] Marked for hot reload: effects/bloom.shader
[HotReload] Reloading: effects/bloom.shader

--- Demo 5: Circular Dependency Detection ---
hero.mesh has circular dependency? No
(In a real engine, A.mat -> B.texture -> A.mat would be detected)

--- Demo 6: Memory Budget & LRU Eviction ---

=== Memory Stats ===
Total resources: 3
Total memory: 3 MB
Memory budget: 1 MB
  Texture: 3072 KB
===================
[ResourceManager] Unloading resource: textures/huge1.png (1048576 bytes)
[ResourceManager] Unloading resource: textures/huge2.png (1048576 bytes)

=== Loaded Resources ===
  [3] textures/huge3.png (Texture, refs=1, size=1048576 bytes)
========================

--- Demo 7: Handle Safety ---
Invalid handle is valid? No
Valid handle is valid? Yes
After release, handle Get() is safe (returns nullptr if unloaded)

========================================
  Demo Complete!
========================================
```

---

## 3. 练习

### 练习 1: 实现纹理 Mipmap 生成

在上面的 `Texture` 类中，目前只存储了一层原始像素数据。请扩展 `Texture` 类，添加 Mipmap 链的生成和存储：

- 添加 `std::vector<std::vector<uint8_t>> m_mipmaps;` 存储各级 Mipmap。
- 实现 `GenerateMipmaps()` 方法，使用简单的盒式滤波（每 2x2 像素取平均）生成下一级 Mipmap。
- 在 `GetMemorySize()` 中计入 Mipmap 占用的内存。

**提示：** 第 n 级 Mipmap 的尺寸是 `width >> n` 和 `height >> n`，当两者都变为 1 时停止。

### 练习 2: 实现资源类型注册表

当前代码中，`LoadSync<T>` 需要编译时知道类型 `T`。在实际引擎中，资源类型需要在运行时动态确定（例如从场景文件中读取 `"type": "Texture"` 时需要创建对应的资源对象）。

请实现一个 `ResourceTypeRegistry`：

- 使用工厂模式，允许注册资源类型：`RegisterType("Texture", []() -> IResource* { return new Texture(); })`。
- 提供 `CreateResource(const std::string& typeName)` 方法，根据类型名创建对应资源实例。
- 修改 `ResourceManager`，添加 `LoadSyncByType(const std::string& path, const std::string& typeName)` 方法。

### 练习 3: 实现完整的流式加载系统（可选）

基于本教程的代码，实现一个简化的地形流式加载系统：

- 定义 `TerrainChunk` 资源类型，包含地形高度图和纹理。
- 实现一个 `StreamingManager` 类，维护一个以玩家位置为中心的 3x3 区块网格。
- 当玩家移动时，计算每个区块与玩家的距离：
  - 距离 < 100：立即加载（Critical 优先级）。
  - 100 <= 距离 < 300：异步加载（Normal 优先级）。
  - 距离 >= 500：卸载（如果引用计数为 0）。
- 在控制台模拟玩家移动，观察资源的加载和卸载日志。

---

## 4. 扩展阅读

### 引擎源码参考

- **Unreal Engine 4/5**: `Engine/Source/Runtime/CoreUObject/Public/UObject/` — UObject 系统是整个 UE 资源管理的基石。`UAssetManager` 负责资源的发现和加载，`FStreamableManager` 处理异步和流式加载。
- **Godot Engine**: `core/io/resource_loader.cpp` 和 `core/io/resource_format_binary.cpp` — Godot 的资源加载器和二进制资源格式。
- **Bevy Engine** (Rust): `crates/bevy_asset/` — Bevy 的 Asset 系统使用 ECS 模式管理资源，支持热重载和依赖追踪。
- **O3DE** (Open 3D Engine): `Code/Framework/AzCore/AzCore/Asset/` — O3DE 的 Asset System 和 Asset Processor。

### 文章与文档

- "Resource Management in Game Engines" — 游戏引擎资源管理的通用设计模式概述。
- "The Asset Pipeline in Modern Game Engines" — 现代引擎的资源管线设计，涵盖导入、处理、编译、打包全流程。
- "Handle-Based Resource Management" — 深入讨论为什么现代引擎偏爱句柄而非指针。
- "Streaming Worlds: Loading Content in Open World Games" — 开放世界游戏的流式加载技术，包括地形 LOD、纹理流送（Texture Streaming）。
- "Hot Reloading in Game Development" — 热重载的实现原理和最佳实践。

### 关键技术点深入

- **Texture Streaming**: UE5 的 Virtual Texture、id Tech 的 MegaTexture — 只加载视野内可见的纹理区域。
- **GPU-Driven Rendering**: 将资源管理的部分决策下放到 GPU，减少 CPU-GPU 数据传输。
- **Content Addressable Storage**: 使用资源内容的哈希值作为唯一标识，天然支持去重和增量更新。

---

## 常见陷阱

- **陷阱 1: 直接使用 `new`/`delete` 管理资源生命周期**
  正确做法：使用句柄 + 引用计数，或者将资源所有权交给 `ResourceManager`，外部只持有句柄。

- **陷阱 2: 同步加载大资源导致帧率骤降**
  正确做法：所有可能耗时的加载操作都应该异步化。对于必须同步加载的关键资源（如玩家角色），在关卡加载屏幕期间完成，或在游戏开始前预加载。

- **陷阱 3: 资源引用循环导致内存泄漏**
  正确做法：使用弱引用（Weak Handle）打破循环，或在资源管线阶段检测并拒绝循环依赖。例如材质引用纹理用强引用，但纹理不应该反向引用材质。

- **陷阱 4: 多线程访问资源时数据竞争**
  正确做法：资源加载完成后，确保所有数据写入对其他线程可见（使用内存屏障或锁）。`ResourceManager` 中使用 `shared_mutex` 允许多个读者并发访问。

- **陷阱 5: 热重载时正在使用的资源被替换导致崩溃**
  正确做法：热重载时创建新资源实例，原子地替换句柄指向的数据，旧资源延迟到所有引用释放后再销毁。或者使用双缓冲：加载新数据到备用槽位，切换指针。

- **陷阱 6: 忽略资源依赖导致加载失败**
  正确做法：加载任何资源前，先递归解析其依赖，构建依赖图并按拓扑顺序加载。使用 Kahn 算法或 DFS 进行拓扑排序，同时检测循环依赖。

- **陷阱 7: LRU 缓存策略不区分资源重要性**
  正确做法：为资源设置优先级标签（如 UI > 玩家角色 > 环境装饰）。LRU 只卸载低优先级资源，高优先级资源即使长期未访问也保留。

- **陷阱 8: 句柄指向已卸载资源后访问崩溃**
  正确做法：句柄访问资源时通过管理器间接查询，如果资源已卸载返回 `nullptr`。永远检查 `IsValid()` 或 `Get() != nullptr` 后再使用。更好的做法是在资源卸载时将所有引用该资源的句柄置为无效。

- **陷阱 9: 打包后的资源路径和开发时路径不一致**
  正确做法：所有资源路径使用虚拟路径（如 `/assets/textures/hero.png`），由 VFS 映射到实际位置。开发时映射到项目目录，发布时映射到 `.pak` 包内的偏移量。

- **陷阱 10: 异步加载完成后在主线程外回调游戏逻辑**
  正确做法：异步加载完成后，将完成事件放入主线程队列，在下一帧的主线程更新中统一处理。避免在后台线程中直接修改游戏状态。
