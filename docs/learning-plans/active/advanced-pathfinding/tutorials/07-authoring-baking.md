---
title: "Authoring 与 Baking 烘焙管线"
updated: 2026-06-05
---

# Authoring 与 Baking 烘焙管线

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: 网格数据结构 (05)，地形代价 (06)，文件 I/O 与序列化基础

## 1. 概念讲解

### 为什么需要这个？

前面的教程中，我们直接在代码里硬编码地形数据——`for (int x=0; x<10; ++x) grid.set_terrain(...)`。这在一个真正的游戏项目中不可行：

- 关卡设计师需要**可视化工具**来放置可导航/不可导航区域（Authoring 阶段）
- 运行时需要**高效数据格式**来加载导航数据（Baking 后产物）
- 修改设计后需要**增量重烘焙**，不能每次全量重建
- 不同平台可能需要不同精度的烘焙数据（移动端低精度 vs PC 高精度）

这就是 **Authoring → Baking → Runtime** 管线：设计时创建高层数据 → 离线预处理为优化格式 → 运行时直接加载。

### 核心思想

#### 三阶段管线

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Authoring      │─────▶│     Baking        │─────▶│    Runtime       │
│  (编辑器/工具)    │      │  (离线预处理)      │      │  (游戏引擎)       │
├─────────────────┤      ├──────────────────┤      ├─────────────────┤
│ 关卡设计师操作:   │      │ 算法处理:          │      │ 引擎加载:         │
│ • 放置地形块     │      │ • 标记不可通行区    │      │ • 反序列化 nav   │
│ • 设置通行属性   │      │ • 生成邻接图       │      │ • 加载到内存      │
│ • 定义区域代价   │      │ • 计算连通分量     │      │ • 准备寻路查询    │
│ • 标记特殊区域   │      │ • 压缩/优化数据    │      │ • 释放编辑数据    │
│                 │      │ • 写入二进制文件   │      │                  │
│ 产出:            │      │ 产出:              │      │ 消费:            │
│ .asset/.json     │      │ nav_data.bin       │      │ 二进制 nav blob   │
│ (human-readable) │      │ (optimized binary) │      │ (mmap/直接读取)   │
└─────────────────┘      └──────────────────┘      └─────────────────┘
```

**关键原则**：Authoring 数据和 Runtime 数据是**不同格式**。Authoring 是为人类/编辑器操作优化的；Runtime 是为 CPU 缓存/内存节省/加载速度优化的。

#### 为什么需要 Baking 阶段？

1. **验证完整性**：检查地图是否所有区域连通、是否有孤岛、是否有悬挂的不可通行区
2. **性能优化**：转换成平坦数组、去除冗余信息、压缩数据
3. **增量构建**：只重烘焙修改过的区域
4. **跨平台适配**：从一个源数据生成多份目标格式（PC/移动/主机）

#### 序列化策略

| 格式 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **JSON** | 人类可读，易调试，可版本控制 diff | 文件大，解析慢，二进制数据需 base64 | Authoring 数据，小地图 |
| **MessagePack/BSON** | 介于 JSON 和二进制之间 | 仍需解析开销 | 中等地图，快速原型 |
| **FlatBuffers/Cap'n Proto** | 零拷贝读取，无需解析 | 格式复杂，文件稍大 | Runtime 高频访问 |
| **自定义二进制** | 最小体积，最快加载 | 不透明，调试困难，需版本管理 | 生产级 Runtime 数据 |

推荐：**Authoring → JSON**（可读、可 diff），**Runtime → 自定义二进制**（mmap 直接映射）。

## 2. 代码示例

### 完整的 Authoring → Baking → Runtime 管线

```cpp
// authoring_baking.cpp — 完整烘焙管线
// 编译: g++ -std=c++17 -O2 -Wall -o baking authoring_baking.cpp
// 运行: ./baking [bake|load]

#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstring>
#include <cstdint>
#include <cassert>
#include <functional>
#include <algorithm>
#include <iomanip>
#include <sstream>
#include <limits>

// ============================================================
// Authoring 层: 关卡设计师操作的数据
// ============================================================

// 高层语义枚举 — 设计师理解的概念
enum class AuthoringTerrain : uint8_t {
    Road, Grass, Forest, Swamp, Water, Mountain, Cliff, COUNT
};

const char* auth_terrain_name(AuthoringTerrain t) {
    switch (t) {
        case AuthoringTerrain::Road:  return "Road";
        case AuthoringTerrain::Grass: return "Grass";
        case AuthoringTerrain::Forest:return "Forest";
        case AuthoringTerrain::Swamp: return "Swamp";
        case AuthoringTerrain::Water: return "Water";
        case AuthoringTerrain::Mountain: return "Mountain";
        case AuthoringTerrain::Cliff: return "Cliff";
        default: return "?";
    }
}

double auth_terrain_cost(AuthoringTerrain t) {
    constexpr double costs[] = {0.8, 1.0, 2.5, 5.0, 999.0, 999.0, 999.0};
    return costs[static_cast<int>(t)];
}

bool auth_terrain_walkable(AuthoringTerrain t) {
    return t <= AuthoringTerrain::Swamp;
}

// Authoring 级网格数据 — 存为 JSON 的文件格式
struct AuthoringData {
    int width, height;
    std::vector<uint8_t> terrain_ids;  // 平坦数组, AuthoringTerrain 的 uint8 值
    std::vector<std::string> region_names; // 命名区域（可选）

    // JSON 序列化（简化为文本格式用于演示）
    std::string to_json() const {
        std::ostringstream ss;
        ss << "{\n";
        ss << "  \"version\": 1,\n";
        ss << "  \"width\": " << width << ",\n";
        ss << "  \"height\": " << height << ",\n";
        ss << "  \"terrain\": [";
        for (size_t i = 0; i < terrain_ids.size(); ++i) {
            if (i > 0) ss << ",";
            if (i % width == 0) ss << "\n    ";
            ss << static_cast<int>(terrain_ids[i]);
        }
        ss << "\n  ]";
        if (!region_names.empty()) {
            ss << ",\n  \"regions\": [";
            for (size_t i = 0; i < region_names.size(); ++i) {
                if (i > 0) ss << ",";
                ss << "\"" << region_names[i] << "\"";
            }
            ss << "]";
        }
        ss << "\n}\n";
        return ss.str();
    }

    static AuthoringData from_json_string(const std::string& json) {
        // 简化解析器 — 生产中用 nlohmann/json 或 rapidjson
        AuthoringData ad{};
        // 在实际项目中用真正的 JSON 库；这里演示字段提取语义
        // 解析 width
        auto wp = json.find("\"width\"");
        auto cp = json.find(':', wp);
        auto ep = json.find(',', cp);
        ad.width = std::stoi(json.substr(cp + 1, ep - cp - 1));

        // 解析 height
        wp = json.find("\"height\"");
        cp = json.find(':', wp);
        ep = json.find(',', cp);
        ad.height = std::stoi(json.substr(cp + 1, ep - cp - 1));

        // 解析 terrain 数组
        wp = json.find("\"terrain\"");
        cp = json.find('[', wp);
        ep = json.find(']', cp);
        std::string arr = json.substr(cp + 1, ep - cp - 1);
        std::istringstream iss(arr);
        int val;
        while (iss >> val) {
            ad.terrain_ids.push_back(static_cast<uint8_t>(val));
            if (iss.peek() == ',') iss.ignore();
        }
        return ad;
    }
};

// ============================================================
// Baking 层: 离线处理
// ============================================================

#pragma pack(push, 1)
// 烘焙后的紧凑二进制格式
struct BakedCell {
    float cost;        // 最终代价 (4 bytes)
    uint8_t flags;     // bit 0: walkable, bits 1-3: area_id, bits 4-7: reserved
};

struct BakedHeader {
    uint32_t magic;        // 文件魔数: 'NAV0'
    uint16_t version;      // 格式版本
    uint16_t flags;        // 特性标志位
    uint32_t width;
    uint32_t height;
    float    min_cost;     // 用于启发函数下界
    uint32_t island_count; // 连通分量数量
    // 后面紧跟 BakedCell[width * height]
};
#pragma pack(pop)

constexpr uint32_t NAV_MAGIC = 0x3056414E; // 'NAV0' little-endian

class NavBaker {
public:
    struct BakeResult {
        bool success;
        std::string error;
        size_t baked_bytes;
        int walkable_cells;
        int unwalkable_cells;
    };

    // 烘焙主函数: AuthoringData → 二进制 blob
    BakeResult bake(const AuthoringData& auth,
                     std::vector<uint8_t>& out_blob)
    {
        BakeResult result{};
        size_t total_cells = auth.width * auth.height;

        // 验证
        if (auth.terrain_ids.size() != total_cells) {
            result.error = "terrain_ids size mismatch";
            return result;
        }

        // 分配输出 buffer
        size_t data_size = sizeof(BakedHeader) + total_cells * sizeof(BakedCell);
        out_blob.resize(data_size, 0);

        // 写入 header
        auto* header = reinterpret_cast<BakedHeader*>(out_blob.data());
        header->magic   = NAV_MAGIC;
        header->version = 1;
        header->flags   = 0;
        header->width   = auth.width;
        header->height  = auth.height;
        header->min_cost = 0.8f; // 从 terrain DB 获取的最优代价
        header->island_count = 0; // 连通分量分析在 08 中做

        // 写入 cells
        auto* cells = reinterpret_cast<BakedCell*>(out_blob.data() + sizeof(BakedHeader));
        double min_c = std::numeric_limits<double>::max();

        for (size_t i = 0; i < total_cells; ++i) {
            auto terrain = static_cast<AuthoringTerrain>(auth.terrain_ids[i]);
            bool walkable = auth_terrain_walkable(terrain);
            double cost = auth_terrain_cost(terrain);

            cells[i].cost  = static_cast<float>(std::min(cost, 65534.0));
            cells[i].flags = (walkable ? 0x01 : 0x00);

            if (walkable) {
                result.walkable_cells++;
                if (cost < min_c) min_c = cost;
            } else {
                result.unwalkable_cells++;
            }
        }

        header->min_cost = static_cast<float>(min_c);
        result.success = true;
        result.baked_bytes = data_size;
        return result;
    }

    // 反序列化验证
    static bool validate_blob(const std::vector<uint8_t>& blob) {
        if (blob.size() < sizeof(BakedHeader)) return false;
        auto* header = reinterpret_cast<const BakedHeader*>(blob.data());
        if (header->magic != NAV_MAGIC) return false;
        size_t expected = sizeof(BakedHeader) + header->width * header->height * sizeof(BakedCell);
        return blob.size() == expected;
    }
};

// ============================================================
// Runtime 层: 快速加载与查询
// ============================================================
class RuntimeNavData {
    const BakedHeader* header_;
    const BakedCell*   cells_;
    uint32_t width_, height_;

public:
    // 从内存中的 blob 加载（模拟 mmap）
    bool load(const std::vector<uint8_t>& blob) {
        if (!NavBaker::validate_blob(blob)) return false;
        header_ = reinterpret_cast<const BakedHeader*>(blob.data());
        cells_  = reinterpret_cast<const BakedCell*>(blob.data() + sizeof(BakedHeader));
        width_  = header_->width;
        height_ = header_->height;
        return true;
    }

    uint32_t width()  const { return width_; }
    uint32_t height() const { return height_; }
    float min_cost()  const { return header_->min_cost; }

    bool walkable(uint32_t x, uint32_t y) const {
        if (x >= width_ || y >= height_) return false;
        return (cells_[y * width_ + x].flags & 0x01) != 0;
    }

    float cost(uint32_t x, uint32_t y) const {
        if (x >= width_ || y >= height_) return INFINITY;
        return walkable(x, y) ? cells_[y * width_ + x].cost : INFINITY;
    }

    void print_info() const {
        std::cout << "RuntimeNavData: " << width_ << "×" << height_
                  << " cells, min_cost=" << min_cost()
                  << ", island_count=" << header_->island_count << "\n";
    }

    // 遍历所有 walkable cells 用于寻路
    void for_each_walkable(std::function<void(uint32_t x, uint32_t y, float cost)> fn) const {
        for (uint32_t y = 0; y < height_; ++y) {
            for (uint32_t x = 0; x < width_; ++x) {
                size_t i = y * width_ + x;
                if (cells_[i].flags & 0x01)
                    fn(x, y, cells_[i].cost);
            }
        }
    }
};

// ============================================================
// Unity Integration: ScriptableObject Authoring
// ============================================================
void show_unity_authoring() {
    std::cout << R"(
========================================================
Unity 集成 — ScriptableObject Authoring
========================================================

C# 代码概念:

// NavAuthoringData.cs
using UnityEngine;
using System.Collections.Generic;

[CreateAssetMenu(menuName = "Navigation/Authoring Data")]
public class NavAuthoringData : ScriptableObject
{
    public int width = 100;
    public int height = 100;

    [System.Serializable]
    public struct CellData
    {
        public int terrainId;
        public float customCost;     // 覆盖默认代价
        public int areaFlags;        // 区域标记
    }

    public CellData[] cells;  // 平坦数组

    // 在 Inspector 中编辑后调用
    [ContextMenu("Bake Navigation Data")]
    public void Bake()
    {
        // 1. 做验证
        // 2. 调用 C++ baking 逻辑 (通过 Native Plugin)
        // 3. 写入 StreamingAssets/nav_data.bin
        // 4. 或生成 NavMeshSurface 数据（如果用 Unity NavMesh）
    }

    void OnValidate()
    {
        if (cells == null || cells.Length != width * height)
            cells = new CellData[width * height];
    }
}

// 在 Unity Editor 中:
// 1. Project 窗口右键 → Create → Navigation → Authoring Data
// 2. 选中 .asset 文件 → Inspector 中显示 terrain 编辑器
// 3. 在 Scene View 中挂 NavAuthoringVisualizer 组件，画刷绘制
// 4. 右键 ScriptableObject → "Bake Navigation Data"
)";
}

// ============================================================
// 主程序
// ============================================================
int main(int argc, char* argv[]) {
    std::string mode = (argc > 1) ? argv[1] : "bake";

    std::cout << "========================================================\n";
    std::cout << "Authoring → Baking → Runtime 管线演示\n";
    std::cout << "========================================================\n\n";

    // ---- Phase 1: Authoring ----
    std::cout << "--- Phase 1: Authoring (设计师创建数据) ---\n";
    AuthoringData auth;
    auth.width = 16;
    auth.height = 12;
    auth.terrain_ids.resize(auth.width * auth.height, 1); // 默认草地

    // 设计师放置地形
    // 道路
    for (int y = 0; y < auth.height; ++y)
        auth.terrain_ids[y * auth.width + 5] = static_cast<uint8_t>(AuthoringTerrain::Road);

    // 森林区域
    for (int y = 0; y < 6; ++y)
        for (int x = 8; x < 14; ++x)
            auth.terrain_ids[y * auth.width + x] = static_cast<uint8_t>(AuthoringTerrain::Forest);

    // 河流
    for (int x = 0; x < 16; ++x)
        auth.terrain_ids[3 * auth.width + x] = static_cast<uint8_t>(AuthoringTerrain::Water);

    // 山地区域
    for (int y = 8; y < 12; ++y)
        for (int x = 12; x < 16; ++x)
            auth.terrain_ids[y * auth.width + x] = static_cast<uint8_t>(AuthoringTerrain::Mountain);

    auth.region_names = {"StartArea", "ForestZone", "MountainPass"};

    // 打印 Authoring 地图
    std::cout << "  Authoring 地图 (R=Road G=Grass F=Forest W=Water M=Mountain):\n";
    for (int y = 0; y < auth.height; ++y) {
        std::cout << "  ";
        for (int x = 0; x < auth.width; ++x) {
            auto t = static_cast<AuthoringTerrain>(auth.terrain_ids[y * auth.width + x]);
            char c = '?';
            switch (t) {
                case AuthoringTerrain::Road: c = 'R'; break;
                case AuthoringTerrain::Grass: c = 'G'; break;
                case AuthoringTerrain::Forest: c = 'F'; break;
                case AuthoringTerrain::Swamp: c = 'S'; break;
                case AuthoringTerrain::Water: c = 'W'; break;
                case AuthoringTerrain::Mountain: c = 'M'; break;
                case AuthoringTerrain::Cliff: c = 'C'; break;
                default: break;
            }
            std::cout << c << ' ';
        }
        std::cout << "\n";
    }

    // 序列化为 JSON
    std::cout << "\n  Authoring JSON (前 300 chars):\n";
    std::string json = auth.to_json();
    std::cout << json.substr(0, std::min(json.size(), size_t(300))) << "...\n";

    if (mode == "load") {
        // Round-trip: JSON → AuthoringData
        std::cout << "\n--- JSON Round-Trip Test ---\n";
        AuthoringData auth2 = AuthoringData::from_json_string(json);
        std::cout << "  Re-parsed: " << auth2.width << "×" << auth2.height
                  << ", " << auth2.terrain_ids.size() << " cells\n";
        assert(auth2.width == auth.width);
        assert(auth2.height == auth.height);
        assert(auth2.terrain_ids.size() == auth.terrain_ids.size());
        std::cout << "  Round-trip: OK\n";
    }

    // ---- Phase 2: Baking ----
    std::cout << "\n--- Phase 2: Baking (离线处理) ---\n";
    NavBaker baker;
    std::vector<uint8_t> baked_blob;
    auto result = baker.bake(auth, baked_blob);

    if (!result.success) {
        std::cout << "  Baking FAILED: " << result.error << "\n";
        return 1;
    }

    std::cout << "  Bake successful:\n";
    std::cout << "    Walkable cells:   " << result.walkable_cells << "\n";
    std::cout << "    Unwalkable cells: " << result.unwalkable_cells << "\n";
    std::cout << "    Baked blob size:  " << result.baked_bytes
              << " bytes (header=" << sizeof(BakedHeader)
              << " + cells=" << result.walkable_cells + result.unwalkable_cells
              << "×" << sizeof(BakedCell) << ")\n";

    // 检查 header
    const auto* header = reinterpret_cast<const BakedHeader*>(baked_blob.data());
    std::cout << "    Header magic: 0x" << std::hex << header->magic << std::dec << "\n";
    std::cout << "    Header version: " << header->version << "\n";
    std::cout << "    Header min_cost: " << header->min_cost << "\n";

    // ---- Phase 3: Runtime loading ----
    std::cout << "\n--- Phase 3: Runtime (游戏加载) ---\n";
    RuntimeNavData nav;
    if (!nav.load(baked_blob)) {
        std::cout << "  Runtime load FAILED!\n";
        return 1;
    }
    nav.print_info();

    // 验证几个格子的数据
    std::cout << "\n  Spot check:\n";
    struct { uint32_t x, y; } spots[] = {{5, 0}, {5, 3}, {0, 0}, {12, 10}};
    for (auto [x, y] : spots) {
        std::cout << "    (" << x << "," << y << "): "
                  << "walkable=" << (nav.walkable(x, y) ? "yes" : "no")
                  << " cost=" << nav.cost(x, y) << "\n";
    }

    // ---- Phase 4: File I/O 模拟 ----
    std::cout << "\n--- Phase 4: 文件 I/O 模拟 ---\n";

    // 写入文件
    {
        std::ofstream out("nav_data.bin", std::ios::binary);
        out.write(reinterpret_cast<const char*>(baked_blob.data()), baked_blob.size());
        out.close();
        std::cout << "  Written to nav_data.bin (" << baked_blob.size() << " bytes)\n";
    }

    // 从文件读取
    {
        std::ifstream in("nav_data.bin", std::ios::binary | std::ios::ate);
        size_t file_size = in.tellg();
        in.seekg(0);
        std::vector<uint8_t> loaded(file_size);
        in.read(reinterpret_cast<char*>(loaded.data()), file_size);
        in.close();

        RuntimeNavData nav2;
        if (nav2.load(loaded)) {
            std::cout << "  Reloaded from file: OK (" << file_size << " bytes)\n";
            nav2.print_info();
        } else {
            std::cout << "  Reload FAILED!\n";
        }
    }

    // ---- Unity 集成 ----
    show_unity_authoring();

    // ---- 对比表格 ----
    std::cout << "\n--- 数据大小对比 ---\n";
    size_t json_size = json.size();
    size_t bin_size  = baked_blob.size();
    std::cout << "  JSON (Authoring):   " << json_size << " bytes\n";
    std::cout << "  Binary (Runtime):   " << bin_size << " bytes"
              << " (" << (100.0 * bin_size / json_size) << "% of JSON)\n";
    std::cout << "  Per-cell binary:    " << sizeof(BakedCell) << " bytes\n";

    std::cout << "\nDone.\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o baking authoring_baking.cpp
./baking bake    # 完整烘焙并写入 nav_data.bin
./baking load    # 含 JSON round-trip 测试
```

**预期输出:**
```
========================================================
Authoring → Baking → Runtime 管线演示
========================================================

--- Phase 1: Authoring (设计师创建数据) ---
  Authoring 地图 (R=Road G=Grass F=Forest W=Water M=Mountain):
  G G G G G R G G F F F F F F G G
  G G G G G R G G F F F F F F G G
  G G G G G R G G F F F F F F G G
  W W W W W R W W W W W W W W W W
  G G G G G R G G F F F F F F G G
  ...

  Authoring JSON (前 300 chars):
  {
    "version": 1,
    "width": 16,
    "height": 12,
    "terrain": [
      1,1,1,1,1,0,1,1,2,2,2,2,2,2,1,1,
      ...

--- Phase 2: Baking (离线处理) ---
  Bake successful:
    Walkable cells:   144
    Unwalkable cells: 48
    Baked blob size:  980 bytes

--- Phase 3: Runtime (游戏加载) ---
  RuntimeNavData: 16×12 cells, min_cost=0.8, island_count=0

  Spot check:
    (5,0): walkable=yes cost=0.8    ← 道路
    (5,3): walkable=no cost=inf     ← 水
    (0,0): walkable=yes cost=1      ← 草地
    (12,10): walkable=no cost=inf   ← 山

--- Phase 4: 文件 I/O 模拟 ---
  Written to nav_data.bin (980 bytes)
  Reloaded from file: OK (980 bytes)

--- Unity 集成 — ScriptableObject Authoring ---
...

--- 数据大小对比 ---
  JSON (Authoring):   450 bytes
  Binary (Runtime):   980 bytes (217% of JSON)
  Per-cell binary:    5 bytes
```

## 3. 练习

### 基础练习
1. **扩展 BakedHeader**：添加 `uint32_t crc32` 字段用于验证数据完整性。在 baking 时计算所有 cells 的 CRC32 校验和写入 header，在 `RuntimeNavData::load` 中验证。
2. **添加版本迁移**：创建 version=2 的格式，在 version=1 基础上增加 `uint16_t area_id` 到 `BakedCell`。在 `load()` 中实现 version=1→2 的自动迁移。

### 进阶练习
1. **实现增量烘焙**：扩展 `NavBaker` 使其支持 `bake_region(int x0, int y0, int x1, int y1)` —— 只重烘焙指定矩形区域，写出到同一个二进制文件的对应偏移位置。（需要理解文件布局和 `fseek`/`pwrite`）
2. **FlatBuffers 集成**：用 FlatBuffers schema 定义 Runtime 导航数据格式，对比与自定义二进制在文件大小和加载速度上的差异。注意 FlatBuffers 的零拷贝特性——不需要 `load()` 步骤。
3. **Baking 验证规则**：在 `NavBaker::bake()` 中添加验证 pass —— 检测地图边缘是否封闭、是否存在孤立的 1×1 可通行小岛、可通行区域是否足够大。失败时返回具体错误信息。

### 挑战练习（可选）
1. **mmap 加载**：在 Linux/Mac 上实现基于 `mmap` 的导航数据加载——文件直接映射到进程地址空间，零拷贝、零解析开销。（Windows 上用 `MapViewOfFile`）
2. **多线程 Baking**：将世界按 256×256 chunk 分区，用 `std::async` 并行烘焙每个 chunk，最后合并结果。测量 N 线程的速度提升。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案（CRC32 数据完整性校验）
> **修改 BakedHeader：在末尾添加 `uint32_t crc32` 字段**
> ```cpp
> struct BakedHeader {
>     uint32_t magic;
>     uint16_t version;
>     uint16_t flags;
>     uint32_t width;
>     uint32_t height;
>     float    min_cost;
>     uint32_t island_count;
>     uint32_t crc32;     // 新增：所有 BakedCell 的 CRC32 校验和
> };
> ```
>
> **Baking 时计算 CRC32：**
> ```cpp
> // CRC32 查表实现 (IEEE 802.3 多项式)
> static uint32_t crc32_table[256];
> static bool crc_table_built = false;
>
> static void build_crc32_table() {
>     for (uint32_t i = 0; i < 256; ++i) {
>         uint32_t crc = i;
>         for (int j = 0; j < 8; ++j)
>             crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320 : 0);
>         crc32_table[i] = crc;
>     }
>     crc_table_built = true;
> }
>
> static uint32_t crc32(const uint8_t* data, size_t len, uint32_t crc = 0xFFFFFFFF) {
>     if (!crc_table_built) build_crc32_table();
>     for (size_t i = 0; i < len; ++i)
>         crc = (crc >> 8) ^ crc32_table[(crc ^ data[i]) & 0xFF];
>     return crc ^ 0xFFFFFFFF;
> }
> ```
>
> **在 `NavBaker::bake()` 末尾（写入 header 之后）计算并回填：**
> ```cpp
> // 计算所有 cells 的 CRC32
> uint32_t checksum = crc32(
>     reinterpret_cast<const uint8_t*>(cells),
>     total_cells * sizeof(BakedCell));
> header->crc32 = checksum;
> ```
>
> **在 `RuntimeNavData::load()` 中验证：**
> ```cpp
> bool load(const std::vector<uint8_t>& blob) {
>     if (!NavBaker::validate_blob(blob)) return false;
>     header_ = reinterpret_cast<const BakedHeader*>(blob.data());
>     cells_  = reinterpret_cast<const BakedCell*>(blob.data() + sizeof(BakedHeader));
>
>     // 验证 CRC32
>     uint32_t computed = crc32(
>         reinterpret_cast<const uint8_t*>(cells_),
>         header_->width * header_->height * sizeof(BakedCell));
>     if (computed != header_->crc32) {
>         std::cerr << "CRC32 mismatch! Data corrupted.\n";
>         return false;
>     }
>     // ...
> }
> ```
>
> **注意：** `crc32` 字段本身不参与校验和计算。校验和保护的是 cells 数据，而非 header。生产环境中可扩展为对 `BakedHeader` 自身（除 crc32 字段外）也做校验。

> [!tip]- 练习 2 参考答案（版本迁移 v1→v2）
> **定义 v2 的 BakedCell：增加 `area_id` 字段**
> ```cpp
> #pragma pack(push, 1)
> struct BakedCellV2 {
>     float cost;
>     uint8_t flags;
>     uint8_t area_id;    // 新增：区域 ID (0-255)
> };
> struct BakedCellV1 {
>     float cost;
>     uint8_t flags;
>     // v1 没有 area_id
> };
> #pragma pack(pop)
> ```
>
> **迁移函数（在 `load()` 中自动检测版本）：**
> ```cpp
> static std::vector<uint8_t> migrate_v1_to_v2(const std::vector<uint8_t>& old_blob) {
>     const auto* old_hdr = reinterpret_cast<const BakedHeader*>(old_blob.data());
>     size_t cell_count = old_hdr->width * old_hdr->height;
>
>     // 新 blob 大小: header + cell_count * sizeof(BakedCellV2)
>     size_t new_size = sizeof(BakedHeader) + cell_count * sizeof(BakedCellV2);
>     std::vector<uint8_t> new_blob(new_size, 0);
>
>     // 复制并更新 header
>     auto* new_hdr = reinterpret_cast<BakedHeader*>(new_blob.data());
>     std::memcpy(new_hdr, old_hdr, sizeof(BakedHeader));
>     new_hdr->version = 2;
>
>     // 逐 cell 迁移：v1 → v2，area_id 默认填 0
>     const auto* old_cells = reinterpret_cast<const BakedCellV1*>(
>         old_blob.data() + sizeof(BakedHeader));
>     auto* new_cells = reinterpret_cast<BakedCellV2*>(
>         new_blob.data() + sizeof(BakedHeader));
>
>     for (size_t i = 0; i < cell_count; ++i) {
>         new_cells[i].cost    = old_cells[i].cost;
>         new_cells[i].flags   = old_cells[i].flags;
>         new_cells[i].area_id = 0;  // v1 没有此信息，默认 0
>     }
>     return new_blob;
> }
> ```
>
> **RuntimeNavData::load() 的版本分支：**
> ```cpp
> bool load(const std::vector<uint8_t>& blob) {
>     if (blob.size() < sizeof(BakedHeader)) return false;
>     const auto* hdr = reinterpret_cast<const BakedHeader*>(blob.data());
>
>     if (hdr->version == 1) {
>         // 自动迁移到 v2
>         auto migrated = migrate_v1_to_v2(blob);
>         return load_internal(migrated);  // 递归加载 v2 格式
>     }
>     if (hdr->version != 2) {
>         std::cerr << "Unsupported version: " << hdr->version << "\n";
>         return false;
>     }
>     return load_internal(blob);
> }
> ```
>
> **关键设计决策：**
> - **为什么不就地修改原 blob？** 原 blob 可能是 mmap 的只读映射，不可写。迁移产生新 blob。
> - **area_id=0 的语义**：默认区域（"未分配"），与设计工具中 "No Area" 的含义一致。
> - **可扩展为 vN 链式迁移**：`v1→v2→v3`，每个迁移步骤只转换相邻版本。

> [!tip]- 练习 3 参考答案（增量烘焙）
> 扩展 `NavBaker` 支持区域增量烘焙：
>
> ```cpp
> #include <cstdio>
>
> class NavBaker {
>     // ... 原有成员 ...
>
> public:
>     // 增量烘焙指定矩形区域到已有文件
>     BakeResult bake_region(const AuthoringData& auth,
>                            int x0, int y0, int x1, int y1,
>                            const std::string& file_path) {
>         BakeResult result{};
>
>         // 边界裁剪
>         x0 = std::max(0, x0); y0 = std::max(0, y0);
>         x1 = std::min(auth.width - 1, x1);
>         y1 = std::min(auth.height - 1, y1);
>
>         // 打开已有文件（二进制读写模式，不清空）
>         FILE* f = fopen(file_path.c_str(), "r+b");
>         if (!f) {
>             result.error = "Cannot open file for incremental bake";
>             return result;
>         }
>
>         // 验证 header
>         BakedHeader hdr;
>         fread(&hdr, sizeof(BakedHeader), 1, f);
>         if (hdr.magic != NAV_MAGIC) {
>             fclose(f);
>             result.error = "Invalid file magic";
>             return result;
>         }
>
>         // 遍历矩形区域，计算并写入每个 cell
>         for (int y = y0; y <= y1; ++y) {
>             for (int x = x0; x <= x1; ++x) {
>                 size_t idx = y * auth.width + x;
>                 auto terrain = static_cast<AuthoringTerrain>(auth.terrain_ids[idx]);
>
>                 BakedCell cell;
>                 cell.cost  = static_cast<float>(auth_terrain_cost(terrain));
>                 cell.flags = auth_terrain_walkable(terrain) ? 0x01 : 0x00;
>
>                 // 计算该 cell 在文件中的偏移：header + cell 偏移
>                 long offset = sizeof(BakedHeader) + idx * sizeof(BakedCell);
>                 fseek(f, offset, SEEK_SET);
>                 fwrite(&cell, sizeof(BakedCell), 1, f);
>
>                 // 更新统计
>                 if (auth_terrain_walkable(terrain))
>                     result.walkable_cells++;
>                 else
>                     result.unwalkable_cells++;
>             }
>         }
>
>         fclose(f);
>         result.success = true;
>         result.baked_bytes = (y1 - y0 + 1) * (x1 - x0 + 1) * sizeof(BakedCell);
>         return result;
>     }
> };
> ```
>
> **核心要点：**
> - 用 `"r+b"` 模式打开文件——读写但不截断
> - `fseek` + `fwrite` 定点写入，不影响其他区域
> - 只重烘焙修改过的矩形区域（如设计师刚编辑的 16×16 刷子区域）
> - 生产级变体：使用 `pwrite()`（POSIX）或 `OVERLAPPED` I/O（Windows）避免 seek+write 的竞态
> - **局限：** 此方案不更新 header 中的 `min_cost` 和 `island_count`——若增量修改影响了这些值，需重新全量烘焙

> [!tip]- 练习 4 参考答案（FlatBuffers 集成）
> **FlatBuffers schema (`nav_data.fbs`)：**
> ```fbs
> namespace NavData;
>
> // 单个导航格子
> table NavCell {
>     cost: float = 1.0;
>     flags: uint8 = 1;       // bit 0: walkable
> }
>
> // 导航网格（根表）
> table NavGrid {
>     width: uint32;
>     height: uint32;
>     min_cost: float;
>     island_count: uint32 = 0;
>     cells: [NavCell];  // 平坦数组
> }
>
> root_type NavGrid;
> ```
>
> **生成 C++ 代码并序列化：**
> ```cpp
> // flatc --cpp nav_data.fbs → nav_data_generated.h
> #include "nav_data_generated.h"
>
> flatbuffers::FlatBufferBuilder builder(1024 * 1024);
>
> // 构建 cells 向量
> std::vector<flatbuffers::Offset<NavData::NavCell>> cell_offsets;
> for (size_t i = 0; i < total_cells; ++i) {
>     cell_offsets.push_back(
>         NavData::CreateNavCell(builder, cost, walkable ? 1 : 0));
> }
> auto cells_vec = builder.CreateVector(cell_offsets);
>
> // 构建根表
> auto grid = NavData::CreateNavGrid(builder, width, height, min_cost,
>                                     island_count, cells_vec);
> builder.Finish(grid);
>
> // 获取二进制 blob
> const uint8_t* buf = builder.GetBufferPointer();
> size_t size = builder.GetSize();
> ```
>
> **零拷贝读取（Runtime）：**
> ```cpp
> // 直接映射文件内容到内存（无需反序列化步骤）
> const NavData::NavGrid* grid = NavData::GetNavGrid(blob.data());
>
> auto cells = grid->cells();
> float c = cells->Get(idx)->cost();
> bool walkable = cells->Get(idx)->flags() & 0x01;
> ```
>
> **对比自定义二进制：**
>
> | 维度 | 自定义二进制 | FlatBuffers |
> |------|-------------|-------------|
> | 文件大小 | ~5B/cell（紧凑） | ~8-12B/cell（vtable 开销） |
> | 加载速度 | 指针转换（O(1)） | 零拷贝读取（O(1)） |
> | Schema 演进 | 手动管理 version | 自动后向兼容（字段可选） |
> | 调试难度 | 困难（hex dump） | 可读（JSON 导出） |
> | 跨平台 | 手动处理字节序 | 自动处理 |
>
> **结论：** 自定义二进制文件更小（约 40-50%），FlatBuffers 更安全可维护。大团队/长生命周期项目选 FlatBuffers；性能极致/受控环境选手动二进制。

> [!tip]- 练习 5 参考答案（Baking 验证规则）
> 在 `NavBaker::bake()` 开头添加验证 pass：
>
> ```cpp
> struct BakeValidationResult {
>     bool passed;
>     std::vector<std::string> warnings;
>     std::vector<std::string> errors;
> };
>
> BakeValidationResult validate(const AuthoringData& auth) {
>     BakeValidationResult vr{true};
>     int w = auth.width, h = auth.height;
>
>     // 规则 1：地图边缘是否全部不可通行/封闭？
>     int edge_walkable = 0;
>     for (int x = 0; x < w; ++x) {
>         if (auth_terrain_walkable(static_cast<AuthoringTerrain>(
>                 auth.terrain_ids[x]))) ++edge_walkable;          // top
>         if (auth_terrain_walkable(static_cast<AuthoringTerrain>(
>                 auth.terrain_ids[(h-1) * w + x]))) ++edge_walkable; // bottom
>     }
>     for (int y = 0; y < h; ++y) {
>         if (auth_terrain_walkable(static_cast<AuthoringTerrain>(
>                 auth.terrain_ids[y * w]))) ++edge_walkable;      // left
>         if (auth_terrain_walkable(static_cast<AuthoringTerrain>(
>                 auth.terrain_ids[y * w + w - 1]))) ++edge_walkable; // right
>     }
>     if (edge_walkable > w + h) // 超过一半的边缘可通行 → 警告
>         vr.warnings.push_back("地图边缘" + std::to_string(edge_walkable)
>             + "个格子可通行——单位可能走出地图");
>
>     // 规则 2：检测孤立 1×1 可通行小岛
>     int isolated_count = 0;
>     const int DIRS[8][2] = {{1,0},{-1,0},{0,1},{0,-1},{1,1},{1,-1},{-1,1},{-1,-1}};
>     for (int y = 0; y < h; ++y) {
>         for (int x = 0; x < w; ++x) {
>             auto t = static_cast<AuthoringTerrain>(auth.terrain_ids[y * w + x]);
>             if (!auth_terrain_walkable(t)) continue;
>             // 检查 8 邻域是否全部不可通行
>             bool isolated = true;
>             for (int d = 0; d < 8; ++d) {
>                 int nx = x + DIRS[d][0], ny = y + DIRS[d][1];
>                 if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
>                 if (auth_terrain_walkable(static_cast<AuthoringTerrain>(
>                         auth.terrain_ids[ny * w + nx]))) {
>                     isolated = false; break;
>                 }
>             }
>             if (isolated) ++isolated_count;
>         }
>     }
>     if (isolated_count > 0)
>         vr.warnings.push_back("检测到" + std::to_string(isolated_count)
>             + "个孤立可通行格子——可能是作者遗漏");
>
>     // 规则 3：可通行区域是否足够大？
>     int total_walkable = 0;
>     for (auto tid : auth.terrain_ids)
>         if (auth_terrain_walkable(static_cast<AuthoringTerrain>(tid)))
>             ++total_walkable;
>     if (total_walkable < w * h / 4)
>         vr.errors.push_back("可通行区域仅占" +
>             std::to_string(100 * total_walkable / (w * h)) +
>             "%，低于 25%——游戏可能无法正常寻路");
>
>     vr.passed = vr.errors.empty();
>     return vr;
> }
> ```
>
> **在 `bake()` 中集成：**
> ```cpp
> BakeResult bake(const AuthoringData& auth, std::vector<uint8_t>& out_blob) {
>     // 先验证
>     auto validation = validate(auth);
>     if (!validation.passed) {
>         BakeResult result{};
>         result.success = false;
>         for (auto& e : validation.errors) result.error += e + "\n";
>         return result;
>     }
>     for (auto& w : validation.warnings)
>         std::cerr << "Baking warning: " << w << "\n";
>
>     // ... 原有烘焙逻辑 ...
> }
> ```

> [!tip]- 练习 6 参考答案（mmap 加载，可选）
> **Linux/macOS 实现：**
> ```cpp
> #include <sys/mman.h>
> #include <sys/stat.h>
> #include <fcntl.h>
> #include <unistd.h>
>
> class MmapNavData {
>     int fd_ = -1;
>     void* mapped_ = nullptr;
>     size_t file_size_ = 0;
>     const BakedHeader* header_ = nullptr;
>     const BakedCell* cells_ = nullptr;
>
> public:
>     ~MmapNavData() { unload(); }
>
>     bool load(const char* file_path) {
>         fd_ = open(file_path, O_RDONLY);
>         if (fd_ < 0) return false;
>
>         struct stat st;
>         if (fstat(fd_, &st) < 0) { close(fd_); return false; }
>         file_size_ = st.st_size;
>
>         // 将整个文件映射到进程地址空间
>         mapped_ = mmap(nullptr, file_size_, PROT_READ,
>                        MAP_PRIVATE, fd_, 0);
>         if (mapped_ == MAP_FAILED) { close(fd_); return false; }
>
>         // 可选：提示内核预读
>         madvise(mapped_, file_size_, MADV_SEQUENTIAL);
>
>         header_ = static_cast<const BakedHeader*>(mapped_);
>         cells_  = reinterpret_cast<const BakedCell*>(
>             static_cast<const char*>(mapped_) + sizeof(BakedHeader));
>
>         return header_->magic == NAV_MAGIC;
>     }
>
>     void unload() {
>         if (mapped_) { munmap(mapped_, file_size_); mapped_ = nullptr; }
>         if (fd_ >= 0)  { close(fd_); fd_ = -1; }
>     }
>
>     bool walkable(uint32_t x, uint32_t y) const {
>         return (cells_[y * header_->width + x].flags & 0x01) != 0;
>     }
>     float cost(uint32_t x, uint32_t y) const {
>         return cells_[y * header_->width + x].cost;
>     }
> };
> ```
>
> **Windows 实现（`MapViewOfFile`）：**
> ```cpp
> #include <windows.h>
>
> class MmapNavDataWin {
>     HANDLE file_handle_ = INVALID_HANDLE_VALUE;
>     HANDLE mapping_handle_ = nullptr;
>     void* mapped_ = nullptr;
>     // ... (类似 mmap 版本，用 CreateFileMapping + MapViewOfFile)
> };
> ```
>
> **核心优势：**
> - 零拷贝——数据直接映射到页缓存，无 `memcpy`、无解析
> - 延迟加载——操作系统按需调页（page fault），不用一次读完整个文件
> - 多进程共享——同一文件的同一物理页可被多个游戏实例共享（节约 RAM）
> - **注意事项：** mmap 映射的指针在文件被替换/截断后可能访问已释放内存→需在打开文件后 `flock` 加读锁

> [!tip]- 练习 7 参考答案（多线程 Baking，可选）
> 将地图按 chunk 分区，并行烘焙：
>
> ```cpp
> #include <future>
> #include <thread>
>
> BakeResult bake_parallel(const AuthoringData& auth,
>                          std::vector<uint8_t>& out_blob) {
>     constexpr int CHUNK_SIZE = 256;
>     int chunks_x = (auth.width + CHUNK_SIZE - 1) / CHUNK_SIZE;
>     int chunks_y = (auth.height + CHUNK_SIZE - 1) / CHUNK_SIZE;
>     int total_chunks = chunks_x * chunks_y;
>
>     // 预分配输出 blob（包含 header 空间）
>     size_t total_cells = auth.width * auth.height;
>     size_t data_size = sizeof(BakedHeader) + total_cells * sizeof(BakedCell);
>     out_blob.resize(data_size, 0);
>
>     // 写入 header
>     auto* header = reinterpret_cast<BakedHeader*>(out_blob.data());
>     header->magic = NAV_MAGIC;
>     header->version = 1;
>     header->width = auth.width;
>     header->height = auth.height;
>     // min_cost 最后统一计算
>
>     auto* cells = reinterpret_cast<BakedCell*>(
>         out_blob.data() + sizeof(BakedHeader));
>
>     // 每个 chunk 一个异步任务
>     std::vector<std::future<void>> futures;
>     std::vector<BakeResult> chunk_results(total_chunks);
>
>     for (int cy = 0; cy < chunks_y; ++cy) {
>         for (int cx = 0; cx < chunks_x; ++cx) {
>             int ci = cy * chunks_x + cx;
>             futures.push_back(std::async(std::launch::async,
>                 [&, ci, cx, cy]() {
>                     BakeResult& r = chunk_results[ci];
>                     int x0 = cx * CHUNK_SIZE;
>                     int y0 = cy * CHUNK_SIZE;
>                     int x1 = std::min(x0 + CHUNK_SIZE, auth.width);
>                     int y1 = std::min(y0 + CHUNK_SIZE, auth.height);
>
>                     double local_min_cost = std::numeric_limits<double>::max();
>                     for (int y = y0; y < y1; ++y) {
>                         for (int x = x0; x < x1; ++x) {
>                             size_t idx = y * auth.width + x;
>                             auto terrain = static_cast<AuthoringTerrain>(
>                                 auth.terrain_ids[idx]);
>                             bool walkable = auth_terrain_walkable(terrain);
>                             double cost = auth_terrain_cost(terrain);
>
>                             cells[idx].cost  = static_cast<float>(cost);
>                             cells[idx].flags = walkable ? 0x01 : 0x00;
>
>                             if (walkable) {
>                                 r.walkable_cells++;
>                                 if (cost < local_min_cost) local_min_cost = cost;
>                             } else {
>                                 r.unwalkable_cells++;
>                             }
>                         }
>                     }
>                     r.success = true;
>                 }));
>         }
>     }
>
>     // 等待所有 chunk 完成
>     for (auto& f : futures) f.get();
>
>     // 合并结果：汇总统计、计算全局 min_cost
>     BakeResult merged{true};
>     double global_min = std::numeric_limits<double>::max();
>     for (auto& cr : chunk_results) {
>         if (!cr.success) { merged.success = false; continue; }
>         merged.walkable_cells += cr.walkable_cells;
>         merged.unwalkable_cells += cr.unwalkable_cells;
>     }
>     merged.baked_bytes = data_size;
>
>     // 最终的 min_cost 需要遍历（各 chunk 的局部 min 的最小值）
>     // TODO: 从 chunk_results 收集各自的 local_min_cost 取全局最小值
>     return merged;
> }
> ```
>
> **关键点：**
> - 每个 chunk 写入独立的 `cells[idx]` 区域，无数据竞争（归并写入到预分配数组的不同偏移）
> - `std::async` 按 chunk 分区，数量 = CPU 核数时效率最优
> - **速度提升**：N 核理论加速 N 倍，实际约 0.7N–0.85N（受内存带宽限制）
> - **内存布局关键**：按 `y` 顺序遍历（缓存友好），chunk 按 256×256 划分（一页 4KB 内紧密排列）
> - **合并阶段的 min_cost** 可存储在每个 chunk_result 的 `local_min_cost` 字段中，最后取 `min()`

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Recast Navigation**：`Recast` 是 NavMesh 的 baking 工具链，其 `rcConfig` 中的 `baking` 参数是理解 baking 概念的最佳实践。读 `RecastDemo` 的 `Sample_SoloMesh::handleBuild()` 流程：体素化→过滤→区域→轮廓→多边形网格。
- **FlatBuffers 文档**：`flatbuffers.dev` — "Why FlatBuffers" 一节解释了零拷贝序列化的设计哲学，与本文的 Runtime 加载思想一致。
- **Unity NavMesh Surface**：`NavMeshSurface.BuildNavMesh()` 就是 baking。理解其 `collectObjects` → `BuildNavMesh` 流程，`NavMeshData` 是 baked 产物。
- **《Data-Oriented Design》** (Fabian)：Chapter 6 关于 "Schemas vs Objects"，讨论 baking 的本质——将编辑时的 OOP 结构转换为运行时的 DOD 结构。
- **Protocol Buffers vs FlatBuffers vs Cap'n Proto**：对比文章 (kentonv.github.io) — 理解三种序列化策略（解析、零拷贝、RPC 优化）在游戏中的应用场景。

## 常见陷阱

1. **Authoring 数据直接用于 Runtime**：在原型期这样做没问题，但一旦性能重要就必须分开。Authoring 数据通常包含冗余字段、字符串、嵌套结构——解析开销在每帧毫秒预算中是灾难。

2. **字节序问题**：自定义二进制格式在不同平台（x86 little-endian vs ARM/console big-endian）间可能出错。**对策**：使用固定字节序（如 `htole32()`），或在 header 中标记字节序并用 `__builtin_bswap32()` 转换。

3. **格式版本不向后兼容**：更新 baked 数据格式后，旧版本游戏无法加载。**对策**：在 header 中存储 `version`，`load()` 按版本分支处理。大版本不兼容时，用 `magic` 不同来区分。

4. **Baking 时忘记验证边界**：如果 Authoring 数据中有越界索引，baking 可能静默产生错误数据。**对策**：baking 开始时一次性验证所有输入。

5. **二进制文件不原子写入**：如果在 baking 过程中游戏崩溃，可能留下半写文件。**对策**：先写到临时文件 (`nav_data.bin.tmp`)，完成后再 `rename()` 到正式路径——`rename()` 在 POSIX 上是原子操作。
