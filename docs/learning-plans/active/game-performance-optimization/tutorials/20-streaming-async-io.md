---
title: "流式加载与异步 IO"
updated: 2026-06-05
---

# 流式加载与异步 IO
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 55 分钟
> 前置知识: 文件 IO 基础，多线程编程概念，了解互斥锁和条件变量
---
## 1. 概念讲解

### 为什么需要这个？

开放式世界游戏（如《塞尔达传说：旷野之息》、《原神》、《艾尔登法环》）的地图动辄几十平方公里，包含了数 GB 的纹理、模型、音频资源。你不可能把它们全部加载到内存中——显存容量不够，加载时间也会让玩家等到天荒地老。

**流式加载**的核心思想：只加载玩家附近（或即将需要）的资源，不需要时卸载，在需要前提前加载。

同时，文件 IO 必须**异步进行**：如果游戏主线程阻塞等待磁盘读取，帧率会直接跌到个位数——即使 NVMe SSD 也需要数百微秒到数毫秒，足以吃掉一整帧的时间。

### 核心思想

#### 三级加载策略

1. **基于距离（Distance-based）**: 离玩家越近的对象优先级越高。远处的低模、近处的高模。
2. **基于可见性（Visibility-based）**: 不可见的对象根本不需要加载完整资源——只需加载碰撞数据和低模代理。
3. **基于优先级（Priority-based）**: 关键任务（Boss 战区域）优先于装饰性内容（远处的草）。

#### 异步 IO 模型

```
┌──────────────┐    请求队列    ┌──────────────┐    磁盘
│  游戏主线程   │ ────────────→ │  IO 工作线程  │ ────────→ SSD/HDD
│              │ ←──────────── │              │
└──────────────┘   完成回调     └──────────────┘
```

Windows 使用 **Overlapped I/O + I/O Completion Ports (IOCP)**；Linux 使用 `libaio`/`io_uring`。核心原则：主线程只提交请求和处理完成结果，不等待 IO。

#### 资源生命周期

```
加载(Load)→驻留(Resident)→驱逐(Evict)→重新加载(Reload)→...
```

- **Load**: 从磁盘读取到内存，解析格式（如解码 PNG 为像素数据）。
- **Resident**: 资源在内存中，可被渲染/使用。此时通过引用计数追踪是否仍在被使用。
- **Evict**: 引用计数归零 + 超出距离/优先级阈值时卸载，释放内存。
- **Reload**: 玩家返回时重新加载。可配合 LRU 缓存避免立即重新读取。

#### UE 中的流式加载

- **World Composition**: 将大世界分割为多个子关卡（sub-levels），根据玩家位置自动加载/卸载。每个子关卡对应一个 `.umap` 文件。
- **Level Streaming Volume**: 放置于关卡中的触发器体积，玩家进入时触发子关卡加载。
- **`ULevelStreamingDynamic`**: 运行时通过代码控制关卡加载/卸载。
- **Asset Manager + Primary Asset Labels**: 定义资源的优先级分组，控制 chunking 和按需加载。

#### Unity 中的流式加载

- **Addressables**: Unity 推荐的异步资源加载系统。通过 address（字符串/AssetReference）加载资源，支持远程（CDN）和本地。
- **AssetBundles**: 老式的资源打包方案，将资源分组为 `.bundle` 文件，运行时按需加载。
- **`AsyncOperation`**: 所有异步加载操作的基类，通过 `isDone` 或 completed 回调检测完成。
- **`SceneManager.LoadSceneAsync`**: 异步加载场景，支持 `allowSceneActivation` 控制激活时机。

#### 优先级调度

```
优先级 = 重要性度量 / 加载成本

其中:
- 重要性度量 = f(距离, 可见性, 游戏逻辑需求)
- 加载成本 = f(文件大小, 依赖链长度)
```

实现：IO 工作线程维护一个优先队列，每完成一个请求就从队列顶部取下一个。高优先级的请求（如玩家人物的纹理）可以插队到低优先级请求（如远处山体的高精度模型）之前。

---
## 2. 代码示例

实现一个基于优先级队列的异步文件加载器，模拟渐进式场景加载。

### 完整代码

```cpp
// async_streaming_loader.cpp
// 编译: g++ -std=c++17 -O2 -pthread -o stream_loader async_streaming_loader.cpp
// 运行: ./stream_loader
//
// 注意: 代码会在当前目录创建临时测试文件，运行结束后自动清理。

#include <iostream>
#include <fstream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <vector>
#include <functional>
#include <atomic>
#include <chrono>
#include <cstring>
#include <cstdint>
#include <memory>
#include <map>
#include <filesystem>

namespace fs = std::filesystem;

// ============================================================
// 1. 资源请求 — 带优先级的加载任务
// ============================================================
struct ResourceRequest {
    enum Priority : int {
        Critical  = 0,  // 摄像机前的关键资源
        High      = 1,  // 视野内的资源
        Normal    = 2,  // 周边区域
        Low       = 3,  // 远处/不可见
        Background = 4, // 后台预加载
    };

    std::string filepath;  // 文件路径
    Priority    priority;
    uint64_t    request_id;
    uint64_t    timestamp; // 提交时间（用于同优先级 FIFO）

    // 优先队列比较：优先级数值越小越优先；同优先级则先来先服务
    bool operator<(const ResourceRequest& other) const {
        if (priority != other.priority)
            return priority > other.priority; // 注意：priority_queue 默认最大堆
        return timestamp > other.timestamp;
    }
};

// ============================================================
// 2. 资源 — 加载完成后的内存块
// ============================================================
struct Resource {
    std::string           name;
    std::vector<uint8_t>  data;
    std::atomic<int>      ref_count{1}; // 引用计数

    Resource(const std::string& n, std::vector<uint8_t>&& d)
        : name(n), data(std::move(d)) {}

    void add_ref()  { ref_count.fetch_add(1, std::memory_order_relaxed); }
    void release()  {
        if (ref_count.fetch_sub(1, std::memory_order_acq_rel) == 1) {
            delete this;
        }
    }
};

// ============================================================
// 3. 异步文件加载器 — IOCP 风格（用线程池模拟）
// ============================================================
class AsyncFileLoader {
public:
    using CompletionCallback = std::function<void(Resource*)>;
    using Priority           = ResourceRequest::Priority;

    AsyncFileLoader(size_t worker_count = 2)
        : running_(true)
        , next_request_id_(0)
    {
        for (size_t i = 0; i < worker_count; ++i) {
            workers_.emplace_back(&AsyncFileLoader::worker_loop, this);
        }
    }

    ~AsyncFileLoader() {
        shutdown();
    }

    // 提交异步加载请求
    uint64_t request_load(const std::string& filepath,
                          Priority priority = Priority::Normal,
                          CompletionCallback on_done = nullptr) {
        ResourceRequest req;
        req.filepath  = filepath;
        req.priority  = priority;
        req.request_id = next_request_id_++;
        req.timestamp  = get_timestamp();

        {
            std::lock_guard<std::mutex> lock(mutex_);
            request_queue_.push(req);
            callbacks_[req.request_id] = std::move(on_done);
        }
        cv_.notify_one();

        return req.request_id;
    }

    // 主线程轮询 — 收集已完成的加载结果
    size_t poll_completions() {
        std::vector<std::pair<uint64_t, Resource*>> batch;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            batch.swap(completed_);
        }

        for (auto& [req_id, resource] : batch) {
            auto it = callbacks_.find(req_id);
            if (it != callbacks_.end() && it->second) {
                it->second(resource);
                callbacks_.erase(it);
            }
            if (resource) {
                resource->release(); // 回调完成后减少引用
            }
        }

        return batch.size();
    }

    // 主线程等待特定请求完成（不使用轮询，使用条件变量）
    Resource* wait_for(uint64_t request_id, int timeout_ms = -1) {
        std::unique_lock<std::mutex> lock(mutex_);
        auto it = results_.find(request_id);
        if (it != results_.end()) {
            Resource* r = it->second;
            results_.erase(it);
            return r;
        }

        // 等待完成信号
        if (timeout_ms < 0) {
            result_cv_.wait(lock, [&] {
                return results_.find(request_id) != results_.end();
            });
        } else {
            auto timeout = std::chrono::milliseconds(timeout_ms);
            bool success = result_cv_.wait_for(lock, timeout, [&] {
                return results_.find(request_id) != results_.end();
            });
            if (!success) return nullptr;
        }

        auto jt = results_.find(request_id);
        if (jt != results_.end()) {
            Resource* r = jt->second;
            results_.erase(jt);
            return r;
        }
        return nullptr;
    }

    void shutdown() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            running_ = false;
        }
        cv_.notify_all();
        for (auto& w : workers_) {
            if (w.joinable()) w.join();
        }
    }

    size_t pending_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return request_queue_.size();
    }

private:
    void worker_loop() {
        while (true) {
            ResourceRequest req;
            CompletionCallback cb;
            bool has_work = false;

            {
                std::unique_lock<std::mutex> lock(mutex_);
                cv_.wait(lock, [this] { return !request_queue_.empty() || !running_; });

                if (!running_ && request_queue_.empty()) return;

                if (!request_queue_.empty()) {
                    req = request_queue_.top();
                    request_queue_.pop();
                    has_work = true;
                }
            }

            if (has_work) {
                // 模拟磁盘 IO（实际项目中这里使用 OS async IO API）
                Resource* resource = load_file_sync(req.filepath);

                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    completed_.emplace_back(req.request_id, resource);
                    results_[req.request_id] = resource;
                }
                result_cv_.notify_one();
            }
        }
    }

    Resource* load_file_sync(const std::string& filepath) {
        // 模拟不同大小文件的加载延迟
        std::ifstream file(filepath, std::ios::binary | std::ios::ate);
        if (!file.is_open()) {
            return new Resource(filepath + " (NOT FOUND)", {});
        }

        // 根据文件大小模拟加载延迟（模拟磁盘 IO 时间）
        size_t file_size = file.tellg();
        size_t delay_us  = file_size / 10 + 500; // 越大越慢

        file.seekg(0, std::ios::beg);
        std::vector<uint8_t> data(file_size);
        file.read(reinterpret_cast<char*>(data.data()), file_size);
        file.close();

        // 模拟磁盘延迟
        std::this_thread::sleep_for(std::chrono::microseconds(delay_us));

        return new Resource(filepath, std::move(data));
    }

    uint64_t get_timestamp() {
        static std::atomic<uint64_t> counter{0};
        return counter.fetch_add(1, std::memory_order_relaxed);
    }

    mutable std::mutex mutex_;
    std::condition_variable cv_;
    std::condition_variable result_cv_;

    std::priority_queue<ResourceRequest> request_queue_;
    std::map<uint64_t, CompletionCallback> callbacks_;
    std::vector<std::pair<uint64_t, Resource*>> completed_;
    std::map<uint64_t, Resource*> results_;

    std::vector<std::thread> workers_;
    std::atomic<bool> running_;
    std::atomic<uint64_t> next_request_id_;
};

// ============================================================
// 4. 流式场景管理器 — 模拟渐进式场景加载
// ============================================================
class StreamingWorld {
public:
    StreamingWorld(AsyncFileLoader& loader) : loader_(loader) {}

    // 模拟玩家移动到新区域
    void move_to_zone(int zone_id) {
        std::cout << "\n[玩家移动到区域 " << zone_id << "]\n";
        current_zone_ = zone_id;

        // 旧区域的资源可卸载
        unload_distant_zones(zone_id);

        // 新区域：按距离分配优先级
        for (int z = zone_id - 2; z <= zone_id + 2; ++z) {
            if (z < 0 || z >= TOTAL_ZONES_) continue;
            if (z == zone_id) {
                // 当前区域 — 关键优先级
                load_zone(z, ResourceRequest::Critical);
            } else if (abs(z - zone_id) == 1) {
                // 相邻区域 — 高优先级（预加载）
                load_zone(z, ResourceRequest::High);
            } else {
                // 更远 — 普通优先级
                load_zone(z, ResourceRequest::Normal);
            }
        }

        // 完成后台预加载更远的区域
        for (int z = zone_id + 3; z <= zone_id + 5; ++z) {
            if (z < TOTAL_ZONES_) {
                load_zone(z, ResourceRequest::Background);
            }
        }
    }

    void update() {
        // 主线程中轮询完成的加载
        size_t completed = loader_.poll_completions();
        if (completed > 0) {
            std::cout << "  [帧更新] 收到 " << completed << " 个加载完成\n";
        }
    }

    std::map<int, std::string> zone_state() const {
        std::map<int, std::string> result;
        for (const auto& [zone_id, state] : zones_) {
            result[zone_id] = state;
        }
        return result;
    }

    size_t loaded_zones() const {
        size_t count = 0;
        for (const auto& [id, state] : zones_) {
            if (state == "loaded") ++count;
        }
        return count;
    }

private:
    void load_zone(int zone_id, ResourceRequest::Priority priority) {
        auto it = zones_.find(zone_id);
        if (it != zones_.end() && it->second == "loaded") return;

        char filename[64];
        snprintf(filename, sizeof(filename), "zone_%02d.dat", zone_id);

        zones_[zone_id] = "loading";
        loader_.request_load(filename, priority,
            [this, zone_id](Resource* res) {
                if (res && !res->data.empty()) {
                    zones_[zone_id] = "loaded";
                    std::cout << "  [完成] zone_" << zone_id
                              << " (" << (res->data.size() / 1024.0) << " KB)\n";
                } else {
                    zones_[zone_id] = "failed";
                }
                res->release();
            });
    }

    void unload_distant_zones(int center) {
        for (auto& [zone_id, state] : zones_) {
            if (state == "loaded" && abs(zone_id - center) > 2) {
                state = "unloaded";
                std::cout << "  [卸载] zone_" << zone_id << "\n";
            }
        }
    }

    AsyncFileLoader& loader_;
    int current_zone_ = 0;
    static constexpr int TOTAL_ZONES_ = 20;
    std::map<int, std::string> zones_; // zone_id -> state
};

// ============================================================
// 5. 创建测试文件
// ============================================================
void create_test_files() {
    std::cout << "创建测试文件...\n";
    for (int i = 0; i < 20; ++i) {
        char filename[64];
        snprintf(filename, sizeof(filename), "zone_%02d.dat", i);

        // 模拟不同大小的区域数据: 近处(核心区域)较大(模拟高精度资源)
        int size_kb = 50 + i * 5; // 50KB - 145KB
        std::vector<char> data(size_kb * 1024, 'A' + (i % 26));

        std::ofstream file(filename, std::ios::binary);
        file.write(data.data(), data.size());
        file.close();
    }
    std::cout << "  创建了 20 个测试区域文件\n";
}

void cleanup_test_files() {
    for (int i = 0; i < 20; ++i) {
        char filename[64];
        snprintf(filename, sizeof(filename), "zone_%02d.dat", i);
        fs::remove(filename);
    }
    std::cout << "测试文件已清理\n";
}

// ============================================================
// 6. 主演示
// ============================================================
int main() {
    std::cout << "========== 异步流式加载器演示 ==========\n\n";

    create_test_files();

    {
        AsyncFileLoader loader(2); // 2 个 IO 工作线程
        StreamingWorld world(loader);

        // 场景 1: 初始加载（玩家在 zone 0）
        std::cout << "--- 场景 1: 玩家出生在 zone 0 ---\n";
        world.move_to_zone(0);

        // 模拟几帧的主循环
        for (int frame = 0; frame < 30; ++frame) {
            world.update();
            std::this_thread::sleep_for(std::chrono::milliseconds(50));

            // 显示加载进度
            if (frame % 5 == 0) {
                size_t pending = loader.pending_count();
                std::cout << "  [帧 " << frame << "] 已加载 " << world.loaded_zones()
                          << " 个区域, 队列中 " << pending << " 个\n";
            }

            if (loader.pending_count() == 0 && world.loaded_zones() >= 5) break;
        }

        // 场景 2: 玩家快速移动到远处
        std::cout << "\n--- 场景 2: 玩家传送到 zone 15 ---\n";
        world.move_to_zone(15);

        // 等待加载完成
        for (int frame = 0; frame < 30; ++frame) {
            world.update();
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            if (frame % 5 == 0 && loader.pending_count() == 0) {
                size_t pending = loader.pending_count();
                std::cout << "  [帧 " << frame << "] 已加载 " << world.loaded_zones()
                          << " 个区域, 队列中 " << pending << " 个\n";
            }
            if (loader.pending_count() == 0) break;
        }

        // 场景 3: 演示优先级 — 同时提交不同优先级的请求
        std::cout << "\n--- 场景 3: 优先级调度 ---\n";
        std::cout << "  提交 6 个请求（从低到高优先级先后提交）\n";

        auto cb = [](Resource* r) {
            std::cout << "  [完成] " << r->name
                      << " (" << (r->data.size() / 1024.0) << " KB)\n";
            r->release();
        };

        // 先提交低优先级，后提交高优先级 — 观察高优先级是否插队
        loader.request_load("zone_05.dat", ResourceRequest::Background, cb);
        loader.request_load("zone_07.dat", ResourceRequest::Low,        cb);
        loader.request_load("zone_09.dat", ResourceRequest::Normal,     cb);
        loader.request_load("zone_01.dat", ResourceRequest::High,       cb);

        // 稍微等一会儿让低优先级开始处理
        std::this_thread::sleep_for(std::chrono::milliseconds(100));

        // 然后提交关键请求 — 应该插队
        loader.request_load("zone_10.dat", ResourceRequest::Critical,   cb);
        loader.request_load("zone_11.dat", ResourceRequest::Critical,   cb);

        // 等待全部完成
        while (loader.pending_count() > 0) {
            world.update();
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        world.update(); // 最后一次收尾
    }

    std::cout << "\n========== 完成 ==========\n";
    cleanup_test_files();
    return 0;
}
```

### 预期输出

```
========== 异步流式加载器演示 ==========

创建测试文件...
  创建了 20 个测试区域文件

--- 场景 1: 玩家出生在 zone 0 ---

[玩家移动到区域 0]
  [帧 0] 已加载 0 个区域, 队列中 5 个
  [完成] zone_00 (50 KB)
  [帧更新] 收到 1 个加载完成
  [完成] zone_01 (55 KB)
  [帧更新] 收到 1 个加载完成
  ...
  [帧 25] 已加载 5 个区域, 队列中 0 个

--- 场景 2: 玩家传送到 zone 15 ---

[玩家移动到区域 15]
  [卸载] zone_0
  ...
  [帧 0] 已加载 2 个区域, 队列中 5 个
  ...

--- 场景 3: 优先级调度 ---

  提交 6 个请求（从低到高优先级先后提交）
  [完成] zone_10.dat (100 KB)    ← 尽管后提交，但因 Critical 优先级先完成
  [完成] zone_11.dat (105 KB)
  [完成] zone_01.dat (55 KB)     ← High 优先级
  [完成] zone_09.dat (95 KB)     ← Normal 优先级
  [完成] zone_07.dat (85 KB)     ← Low 优先级
  [完成] zone_05.dat (75 KB)     ← Background 最后

========== 完成 ==========
测试文件已清理
```

**关键观察**：
- 场景 3 中，后提交的 Critical 请求插队到先提交的低优先级请求之前。
- 主线程通过 `poll_completions()` 以非阻塞方式收集结果，不会被 IO 阻塞。
- 玩家移动时，旧区域自动卸载，新区域按距离分配优先级。

---
## 3. 练习

### 练习 1: 实现引用计数资源缓存

在 `StreamingWorld` 中添加 `ResourceCache`：
- 维护 `std::unordered_map<std::string, Resource*> cache_`。
- `request_load` 前先检查缓存——如果命中且数据有效，直接返回缓存版本。
- 引用计数归零且不在任何邻近区域时，从缓存中驱逐。
- 统计缓存命中率。

### 练习 2: 带宽限制的多级调度

在上层 `StreamingWorld` 之上实现节流：
- 每帧最多处理 N 个 IO 请求（如 3 个）。
- 当带宽受限时，严格按优先级调度——低优先级的请求可能被推迟多帧。
- 模拟低带宽场景（如 HDD 而非 SSD）和快速场景进行对比。

### 练习 3: 依赖感知加载（挑战）

真实游戏资源有依赖链：
- 加载 `zone_00.dat` 之前必须加载 `shared_textures.dat`（共享纹理包）。
- 实现一个依赖图管理器，当请求加载 zone 时自动检查并先加载其依赖。
- 如果多个 zone 依赖同一资源，引用计数确保它不会被提前卸载。
- 提示：使用拓扑排序或简单的 `std::set<std::string>` 列表。

---
## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **引用计数资源缓存实现：**
>
> ```cpp
> class ResourceCache {
>     struct CacheEntry {
>         Resource* resource = nullptr;
>         uint64_t  last_access_frame = 0;  // 用于 LRU 驱逐
>     };
>
>     std::unordered_map<std::string, CacheEntry> cache_;
>     uint64_t current_frame_ = 0;
>
>     // 驱逐阈值：资源未被访问超过 N 帧
>     static constexpr uint64_t EVICT_AFTER_FRAMES = 300;  // 5 秒 @60fps
>
> public:
>     // 尝试从缓存获取；如果命中返回资源并增加引用计数
>     Resource* get(const std::string& key) {
>         auto it = cache_.find(key);
>         if (it != cache_.end()) {
>             it->second.resource->add_ref();
>             it->second.last_access_frame = current_frame_;
>             ++hit_count_;
>             return it->second.resource;
>         }
>         ++miss_count_;
>         return nullptr;
>     }
>
>     // 将新加载的资源插入缓存
>     void put(const std::string& key, Resource* resource) {
>         cache_[key] = {resource, current_frame_};
>     }
>
>     // 每帧调用：驱逐引用计数为 0 且长时间未访问的资源
>     void evict() {
>         auto it = cache_.begin();
>         while (it != cache_.end()) {
>             auto& entry = it->second;
>             if (entry.resource->ref_count.load() <= 1  // 仅缓存持有引用
>                 && current_frame_ - entry.last_access_frame > EVICT_AFTER_FRAMES) {
>                 entry.resource->release();  // 释放缓存持有的引用 → 可能 delete
>                 it = cache_.erase(it);
>                 ++evict_count_;
>             } else {
>                 ++it;
>             }
>         }
>     }
>
>     void next_frame() { ++current_frame_; }
>
>     double hit_rate() const {
>         size_t total = hit_count_ + miss_count_;
>         return total > 0 ? double(hit_count_) / total : 0.0;
>     }
>
> private:
>     size_t hit_count_ = 0;
>     size_t miss_count_ = 0;
>     size_t evict_count_ = 0;
> };
>
> // 集成到 StreamingWorld::request_load
> Resource* StreamingWorld::request_load_cached(const std::string& path) {
>     // 1. 先查缓存
>     Resource* cached = cache_.get(path);
>     if (cached) return cached;  // 缓存命中
>
>     // 2. 缓存未命中 → 提交异步加载
>     uint64_t req_id = loader_.request_load(path, Priority::Normal,
>         [this](Resource* res) {
>             cache_.put(res->name, res);  // 加载完成后插入缓存
>         });
>     return loader_.wait_for(req_id);
> }
> ```
>
> **缓存命中率的影响因素：**
> - 玩家移动慢 + 区域重叠大 → 命中率 > 80%
> - 玩家快速移动（如传送）→ 命中率 < 20%
> - 可配合预加载（预测玩家下个区域）提升命中率

> [!tip]- 练习 2 参考答案
> **带宽受限的多级调度实现：**
>
> ```cpp
> class BandwidthLimitedScheduler {
>     static constexpr size_t MAX_LOADS_PER_FRAME = 3;  // 每帧最多处理 N 个 IO
>     static constexpr size_t MAX_PENDING = 50;          // 最大排队请求数
>
>     struct ScheduledRequest {
>         uint64_t request_id;
>         Priority priority;
>         uint64_t age_frames = 0;  // 排队等待的帧数 → 饥饿预防
>     };
>
>     std::priority_queue<ScheduledRequest, std::vector<ScheduledRequest>,
>         /* 自定义比较：优先级优先，同优先级按年龄（先来先服务）*/> pending_;
>     size_t loads_this_frame_ = 0;
>
> public:
>     uint64_t schedule(const std::string& path, Priority priority,
>                       AsyncFileLoader& loader) {
>         // 如果超过排队上限，拒绝最低优先级的请求
>         if (pending_.size() >= MAX_PENDING) {
>             // 仅当新请求优先级更高时才替换
>             auto lowest = pending_.top();  // 最低优先级在堆顶
>             if (priority < lowest.priority) {
>                 pending_.pop();
>                 // 取消被替换的请求...
>             } else {
>                 return 0;  // 拒绝
>             }
>         }
>
>         uint64_t req_id = next_id_++;
>         pending_.push({req_id, priority, 0});
>         return req_id;
>     }
>
>     // 每帧初调用：从队列中取出最多 MAX_LOADS_PER_FRAME 个请求提交给 IO
>     void dispatch_frame(AsyncFileLoader& loader) {
>         loads_this_frame_ = 0;
>
>         // 临时取出所有请求并增加年龄
>         std::vector<ScheduledRequest> all;
>         while (!pending_.empty()) {
>             auto req = pending_.top(); pending_.pop();
>             req.age_frames++;
>             // 饥饿预防：等待超过 60 帧（1秒）→ 临时提升到 Critical
>             if (req.age_frames > 60) {
>                 req.priority = Priority::Critical;
>             }
>             all.push_back(req);
>         }
>
>         // 按优先级排序
>         std::sort(all.begin(), all.end(),
>             [](const auto& a, const auto& b) {
>                 if (a.priority != b.priority) return a.priority < b.priority;
>                 return a.age_frames > b.age_frames;  // 同龄等待久的优先
>             });
>
>         // 提交前 MAX_LOADS_PER_FRAME 个
>         for (size_t i = 0; i < all.size(); ++i) {
>             if (i < MAX_LOADS_PER_FRAME) {
>                 loader.submit(all[i].request_id);  // 提交到 IO
>                 ++loads_this_frame_;
>             } else {
>                 pending_.push(all[i]);  // 重新排队
>             }
>         }
>     }
> };
> ```
>
> **HDD vs SSD 场景对比：**
> - SSD (1GB/s, ~50μs 延迟)：`MAX_LOADS_PER_FRAME = 10-20`，队列短，所有请求能在 1-2 帧内完成。
> - HDD (100MB/s, ~10ms 延迟)：`MAX_LOADS_PER_FRAME = 2-3`，低优先级请求可能排队数百帧。饥饿预防机制关键——否则远处资源永远加载不到。

> [!tip]- 练习 3 参考答案
> **依赖感知加载管理器：**
>
> ```cpp
> class DependencyAwareLoader {
>     // 依赖图: key → 其依赖的资源列表
>     std::unordered_map<std::string, std::vector<std::string>> dependencies_;
>
>     // 反向依赖: key → 依赖它的资源列表（用于引用计数管理）
>     std::unordered_map<std::string, std::set<std::string>> reverse_deps_;
>
>     // 正在加载中的资源（防止重复请求）
>     std::set<std::string> in_flight_;
>
>     AsyncFileLoader& loader_;
>     ResourceCache& cache_;
>
> public:
>     void add_dependency(const std::string& resource,
>                         const std::string& depends_on) {
>         dependencies_[resource].push_back(depends_on);
>         reverse_deps_[depends_on].insert(resource);
>     }
>
>     uint64_t request_with_deps(const std::string& path, Priority priority) {
>         // BFS/DFS 收集所有依赖（循环检测略）
>         std::set<std::string> all_required = collect_dependencies(path);
>
>         // 按拓扑顺序提交：依赖先于被依赖者
>         // 简化：对每个依赖递归提交
>         return request_recursive(path, priority);
>     }
>
> private:
>     uint64_t request_recursive(const std::string& path, Priority priority) {
>         // 1. 检查缓存
>         Resource* cached = cache_.get(path);
>         if (cached) return 0;  // 已加载
>
>         // 2. 检查是否已在加载中
>         if (in_flight_.count(path)) return 0;  // 去重
>
>         // 3. 先加载依赖
>         if (dependencies_.count(path)) {
>             for (const auto& dep : dependencies_[path]) {
>                 request_recursive(dep, priority);  // 依赖优先级与被依赖者相同
>             }
>         }
>
>         // 4. 加载自身
>         in_flight_.insert(path);
>         return loader_.request_load(path, priority,
>             [this, path](Resource* res) {
>                 in_flight_.erase(path);
>                 cache_.put(path, res);
>             });
>     }
>
>     // 递归收集依赖（含循环检测）
>     std::set<std::string> collect_dependencies(const std::string& path) {
>         std::set<std::string> result;
>         std::set<std::string> visited;
>         std::function<void(const std::string&)> dfs =
>             [&](const std::string& node) {
>                 if (visited.count(node)) return;  // 已处理
>                 visited.insert(node);
>                 if (dependencies_.count(node)) {
>                     for (const auto& dep : dependencies_[node]) {
>                         if (dep != node) {  // 跳过自依赖
>                             result.insert(dep);
>                             dfs(dep);
>                         }
>                     }
>                 }
>             };
>         dfs(path);
>         return result;
>     }
> };
>
> // 使用示例：
> // loader.add_dependency("zone_00.dat", "shared_textures.dat");
> // loader.add_dependency("zone_00.dat", "common_audio.dat");
> // loader.add_dependency("zone_01.dat", "shared_textures.dat");
> // → request_with_deps("zone_00.dat") 会自动先加载 shared_textures.dat + common_audio.dat
> ```
>
> **关键设计点：**
> 1. **引用计数由缓存管理**：`shared_textures.dat` 被 `zone_00` 和 `zone_01` 都依赖。只要任一引用者还在，就不会被驱逐。
> 2. **去重**：`in_flight_` 防止同时发起多个相同的加载请求。
> 3. **循环依赖检测**：DFS 中用 `visited` 集合防止无限递归。真实项目中可以预先验证依赖图是 DAG。
> 4. **加载顺序**：先加载依赖后加载主资源，确保主资源加载完成时所有依赖已就绪。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- **UE 文档 — World Composition**: https://docs.unrealengine.com/en-US/world-composition/ — UE 的大型世界加载方案。
- **UE 文档 — Asset Manager**: https://docs.unrealengine.com/en-US/asset-management/ — Primary Asset 的优先级和 chunking 策略。
- **Unity Addressables 文档**: https://docs.unity3d.com/Packages/com.unity.addressables@latest — Unity 的异步资源加载系统。
- **Windows IOCP 文档**: https://learn.microsoft.com/en-us/windows/win32/fileio/i-o-completion-ports — Windows 异步 IO 的核心机制。
- **Linux io_uring**: https://kernel.dk/io_uring.pdf — Linux 新一代高性能异步 IO 接口。
- **"Open-World Streaming in Horizon Zero Dawn"** (GDC 2017) — Guerrilla Games 分享的流式加载系统设计，包括预算管理和优先级调度。

---
## 常见陷阱

1. **同步 IO 在主线程**: 即使用了异步 API，如果在完成回调中做同步 IO（如解析 JSON），依然会阻塞主线程。所有回调应只做轻量工作（更新状态、发起新请求），繁重工作交给工作线程。
2. **回调中的资源释放**: 完成回调中如果释放了资源，但其他系统仍在使用该资源，会导致崩溃。始终使用引用计数，并在回调完成后 `release()`。
3. **内存预算失控**: 流式加载系统需要一个硬上限——"最多同时驻留 N MB"。否则在资源丰富的区域，内存可能膨胀失控。UE 的 `FStreamingManager` 和 Unity 的 `MemoryBudget` 都有此功能。
4. **加载延迟导致的 Pop-in**: 资源加载晚于玩家到达，导致物体突然出现（pop-in）。缓解方案：增大预加载半径、使用低模 LOD 作为临时代理、渐进式纹理加载（先低分辨率后高分辨率）。
5. **优先级反转**: 低优先级请求持有锁/资源，高优先级请求在等待它——传统操作系统问题在 IO 调度中同样存在。缓解：将大请求拆分为多个小请求，使用非抢占式调度时注意限制单个请求的最大处理时间。
6. **重复请求**: 同一资源被多次请求（如两个 zone 共享的纹理）。需要去重机制——`std::set<std::string> in_flight_` 追踪正在进行中的请求，后续相同请求直接复用。
