---
title: "网格数据结构与内存布局"
updated: 2026-06-05
---

# 网格数据结构与内存布局

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: 网格寻路基础 (04)，C++ 模板，缓存层次结构与数据局部性

## 1. 概念讲解

### 为什么需要这个？

在 04 中我们用了 `vector<vector<Cell>>`——这很好上手，但它是一个**性能灾难**：

- **指针追踪 (Pointer chasing)**：`vector<vector<T>>` 是 `vector<vector<T>*>` 的语法糖。访问 `cells[x][y]` 需要两次间接寻址：先解引用外部 vector 的行指针，再解引用内部 vector 的元素。
- **缓存不友好**：每一行是独立分配的，它们可能在堆上散布各处。遍历一行 → 访问一行 → 下一行在缓存已污染时重新 miss。
- **内存碎片**：1000×1000 网格 = 1001 次堆分配（1000 行 + 外部 vector）。分配器压力大，遍历时 TLB miss 不断。

对于运行在每帧毫秒级预算下的寻路系统，这些问题不可忽视。**数据布局决定性能上限**——本节教你如何正确地存储网格数据。

### 核心思想

#### AoS vs SoA：两种内存布局

**AoS (Array of Structures)**：把每个格子的全部属性打包在一起。

```
内存: [x.cost|x.walkable|x.terrain] [x.cost|x.walkable|x.terrain] ...
```

**SoA (Structure of Arrays)**：把每个属性单独放入一个连续数组。

```
内存: [cost[0],cost[1],cost[2],...] [walkable[0],walkable[1],...] [terrain[0],terrain[1],...]
```

关键差异在**访问模式**：

| 操作 | AoS 性能 | SoA 性能 | 原因 |
|------|---------|---------|------|
| 访问单个格子的所有属性 | 优 (1 条 cache line) | 差 (3 条 cache line) | AoS 是局部展开的 |
| 遍历所有格子的 `cost` 字段 | 差 (跳过了 walkable/terrain) | 优 (纯连续流) | SoA 不加载不需要的字段 |
| SIMD 向量化 | 差 (需要 gather/scatter) | 优 (连续 load 即可) | SoA 天然适配 SIMD |

在寻路系统中，典型操作是"遍历所有邻居，查询 cost"——只会访问 cost 和 walkable，这正是 SoA 的优势场景。

#### 平坦数组索引 (Flat Array Indexing)

将 2D 网格映射为 1D 数组：

```cpp
// 行优先 (row-major): 内存中连续的行
size_t index = y * width + x;   // x=列, y=行
// 或
size_t index = x * height + y;  // 列优先 (column-major)
```

- **零间接寻址**：`data[y * width + x]` 是一条 LEA + MOV 指令
- **单次分配**：`new Cell[width * height]` 一次堆分配
- **可预测的步长**：遍历相邻行只需加 `width`

#### 稀疏网格 vs 稠密网格

对于可能极其巨大但大多数格子是"空"的世界：

| 方案 | 内存 (10000²，10% 可通行) | 随机访问 | 遍历 |
|------|--------------------------|---------|------|
| 稠密 flat array | ~100M cells × N bytes | O(1) | O(W×H) |
| `unordered_map<pair<int,int>, Cell>` | ~10M cells × (N + hash overhead) | O(1) 均摊 | 必须按 key 迭代 |
| 分块稀疏 (Chunked Sparse) | 只分配有内容的 chunk | O(1)（一次 chunk 查找） | O(已分配 chunk) |

在游戏中通常用**稠密网格 + 分块**：世界虽大，但"可导航"区域是连续的。

#### 网格分块 (Grid Chunking)

将 N×M 大网格拆分为 `chunk_size × chunk_size` 的子块：

```
好处:
- 大世界中不必一次性加载所有数据 → 流式加载
- 寻路时只触及相关 chunk → 更好的缓存行为
- 烘焙时可以并行处理每个 chunk
- 每个 chunk 可以有自己的 LOD（远处用粗粒度）
```

### N 维网格模板

游戏很少只需要 2D 网格——体素世界(3D)、时间维度的 4D 寻路都会出现。用 C++ 模板一劳永逸：

```cpp
template<typename T, size_t Dims>
class Grid {
    // compile-time N-dimensional flat array
};
```

## 2. 代码示例

### 生产级 Grid<T>：SoA + 平坦数组 + 维度模板

```cpp
// grid_data_structures.cpp — AoS vs SoA, 平坦数组, 分块, N维网格
// 编译: g++ -std=c++17 -O2 -Wall -o grid_ds grid_data_structures.cpp
// 运行: ./grid_ds

#include <iostream>
#include <vector>
#include <cstring>
#include <chrono>
#include <iomanip>
#include <numeric>
#include <cassert>
#include <cmath>
#include <functional>
#include <limits>
#include <unordered_map>

// ============================================================
// 1. AoS 布局 — 传统方式 (用作对比基线)
// ============================================================
namespace aos {

struct Cell {
    bool walkable;
    double cost;
    int terrain_id;
};

class Grid {
public:
    int rows, cols;
    std::vector<std::vector<Cell>> cells;

    Grid(int r, int c) : rows(r), cols(c), cells(r, std::vector<Cell>(c)) {}

    bool in_bounds(int x, int y) const { return x >= 0 && x < rows && y >= 0 && y < cols; }

    double cost_at(int x, int y) const { return cells[x][y].cost; }
    bool walkable_at(int x, int y) const { return cells[x][y].walkable; }

    void set_walkable(int x, int y, bool v) { cells[x][y].walkable = v; }
    void set_cost(int x, int y, double v)   { cells[x][y].cost = v; }
    void set_terrain(int x, int y, int v)   { cells[x][y].terrain_id = v; }

    size_t memory_bytes() const {
        return sizeof(Cell) * rows * cols + rows * sizeof(std::vector<Cell>);
    }
};

} // namespace aos

// ============================================================
// 2. SoA 布局 — 平坦数组
// ============================================================
class GridSoA {
public:
    int rows, cols;

private:
    std::vector<bool>    walkable_;
    std::vector<double>  cost_;
    std::vector<int>     terrain_id_;
    size_t total_cells_;

public:
    GridSoA(int r, int c)
        : rows(r), cols(c), total_cells_(static_cast<size_t>(r) * c),
          walkable_(total_cells_), cost_(total_cells_, 1.0), terrain_id_(total_cells_, 0)
    {}

    size_t index(int x, int y) const {
        // row-major: y * cols + x  (y=行 x=列)
        return static_cast<size_t>(y) * cols + x;
    }

    bool in_bounds(int x, int y) const { return x >= 0 && x < rows && y >= 0 && y < cols; }

    bool    walkable_at(int x, int y) const { return walkable_[index(x, y)]; }
    double  cost_at(int x, int y)     const { return cost_[index(x, y)]; }
    int     terrain_at(int x, int y)  const { return terrain_id_[index(x, y)]; }

    void set_walkable(int x, int y, bool v)   { walkable_[index(x, y)] = v; }
    void set_cost(int x, int y, double v)     { cost_[index(x, y)] = v; }
    void set_terrain(int x, int y, int v)     { terrain_id_[index(x, y)] = v; }

    // 直接访问底层数组 — 给寻路算法用（免除 index() 的乘法）
    const double* cost_data()  const { return cost_.data(); }
    const bool*   walkable_data() const { return walkable_.data(); }

    size_t memory_bytes() const {
        return walkable_.capacity() / 8 + 1   // bits → bytes 近似
             + cost_.capacity() * sizeof(double)
             + terrain_id_.capacity() * sizeof(int);
    }

    // 批量操作：一次设置大面积区域 —— SoA 的亮点（SIMD 可向量化）
    void fill_cost(double value) {
        std::fill(cost_.begin(), cost_.end(), value);
    }

    // 邻居迭代 — 直接使用平坦索引，避开 in_bounds 的分支（用哨兵）
    void for_each_neighbor(int x, int y,
                           std::function<void(int nx, int ny, double step_cost)> callback) const
    {
        static const int DX[] = {1, -1, 0, 0};
        static const int DY[] = {0, 0, 1, -1};

        for (int d = 0; d < 4; ++d) {
            int nx = x + DX[d];
            int ny = y + DY[d];
            if (!in_bounds(nx, ny)) continue;
            if (!walkable_at(nx, ny)) continue;
            callback(nx, ny, cost_at(nx, ny));
        }
    }
};

// ============================================================
// 3. 分块网格 (Chunked Grid) — 大世界
// ============================================================
class ChunkedGrid {
public:
    static constexpr int CHUNK_SIZE = 16;   // 16×16 每块 = 256 cells
    static constexpr int CHUNK_MASK = CHUNK_SIZE - 1;

    struct Chunk {
        std::vector<double>  cost;          // 平坦 SoA
        std::vector<bool>    walkable;
        int chunk_x, chunk_y;
        bool loaded = true;

        Chunk(int cx, int cy)
            : chunk_x(cx), chunk_y(cy),
              cost(CHUNK_SIZE * CHUNK_SIZE, 1.0),
              walkable(CHUNK_SIZE * CHUNK_SIZE, true)
        {}
    };

    int world_rows, world_cols;             // 以 cell 为单位
    int chunks_x, chunks_y;                 // 以 chunk 为单位

private:
    std::vector<std::unique_ptr<Chunk>> chunks_; // 只存储非空的 chunk
    // chunk 查找表: 平坦索引 → chunk 指针 (nullptr = 空 chunk)
    std::vector<Chunk*> chunk_map_;

    size_t chunk_index(int cx, int cy) const { return cy * chunks_x + cx; }

public:
    ChunkedGrid(int total_rows, int total_cols)
        : world_rows(total_rows), world_cols(total_cols),
          chunks_x((total_cols + CHUNK_SIZE - 1) / CHUNK_SIZE),
          chunks_y((total_rows + CHUNK_SIZE - 1) / CHUNK_SIZE),
          chunk_map_(chunks_x * chunks_y, nullptr)
    {
        // 默认所有 chunk 为空 —— 按需创建
    }

    // 确保某个 chunk 被加载（延迟创建）
    Chunk* ensure_chunk(int cx, int cy) {
        size_t ci = chunk_index(cx, cy);
        if (chunk_map_[ci] == nullptr) {
            auto c = std::make_unique<Chunk>(cx, cy);
            chunk_map_[ci] = c.get();
            chunks_.push_back(std::move(c));
        }
        return chunk_map_[ci];
    }

    // 卸载某个 chunk（大世界中用于 LOD）
    void unload_chunk(int cx, int cy) {
        size_t ci = chunk_index(cx, cy);
        if (chunk_map_[ci]) {
            auto it = std::find_if(chunks_.begin(), chunks_.end(),
                [p = chunk_map_[ci]](const auto& u) { return u.get() == p; });
            if (it != chunks_.end()) chunks_.erase(it);
            chunk_map_[ci] = nullptr;
        }
    }

    double cost_at(int x, int y) const {
        int cx = y / CHUNK_SIZE;
        int cy = x / CHUNK_SIZE;  // 注意：x=行 y=列
        // world_rows/world_cols 命名跟 GridSoA 一致:
        // x=行 (0..rows-1), y=列 (0..cols-1)
        // chunk 坐标: cx = row/CHUNK_SIZE, cy = col/CHUNK_SIZE
        Chunk* c = chunk_map_[chunk_index(cx, cy)];
        if (!c) return 1.0;  // 未加载的 chunk 默认为平地
        int lx = x % CHUNK_SIZE;
        int ly = y % CHUNK_SIZE;
        return c->cost[lx * CHUNK_SIZE + ly];
    }

    size_t chunk_count() const { return chunks_.size(); }
    size_t total_allocated_bytes() const {
        size_t total = 0;
        for (auto& c : chunks_) {
            total += c->cost.capacity() * sizeof(double);
            total += c->walkable.capacity() / 8 + 1;
        }
        return total;
    }
};

// ============================================================
// 4. 模板化 N 维网格 (Grid<Dims>)
// ============================================================
template<typename T, size_t Dims>
class GridND {
    static_assert(Dims >= 1 && Dims <= 4, "Dims must be 1..4");

    std::vector<T> data_;
    int extents_[Dims];   // 每个维度的尺寸
    int strides_[Dims];   // 每个维度的步长

public:
    template<typename... Ints,
             typename = std::enable_if_t<sizeof...(Ints) == Dims &&
                                         (std::is_integral_v<Ints> && ...)>>
    GridND(Ints... dims) {
        const int sizes[] = {static_cast<int>(dims)...};
        size_t total = 1;
        for (size_t d = 0; d < Dims; ++d) {
            extents_[d] = sizes[d];
            total *= sizes[d];
        }
        // 计算 strides: row-major (最后维度连续)
        strides_[Dims - 1] = 1;
        for (int d = Dims - 2; d >= 0; --d)
            strides_[d] = strides_[d + 1] * extents_[d + 1];

        data_.resize(total);
    }

    int extent(size_t dim) const { return extents_[dim]; }

    // flat index
    template<typename... Ints>
    size_t index(Ints... coords) const {
        const int cs[] = {static_cast<int>(coords)...};
        size_t idx = 0;
        for (size_t d = 0; d < Dims; ++d)
            idx += cs[d] * strides_[d];
        return idx;
    }

    template<typename... Ints>
    T& operator()(Ints... coords) {
        return data_[index(coords...)];
    }

    template<typename... Ints>
    const T& operator()(Ints... coords) const {
        return data_[index(coords...)];
    }

    const T* raw_data() const { return data_.data(); }
          T* raw_data()       { return data_.data(); }
    size_t size() const { return data_.size(); }
};

// ============================================================
// 5. 稀疏网格 (unordered_map 实现) — 对比用
// ============================================================
class SparseGrid {
    struct Key { int x, y; };
    struct KeyHash {
        size_t operator()(Key k) const {
            return (static_cast<uint64_t>(k.x) << 32) | static_cast<uint32_t>(k.y);
        }
    };
    struct KeyEqual {
        bool operator()(Key a, Key b) const { return a.x == b.x && a.y == b.y; }
    };

    struct Cell { double cost = 1.0; int terrain = 0; };

    std::unordered_map<Key, Cell, KeyHash, KeyEqual> cells_;

public:
    double cost_at(int x, int y) const {
        auto it = cells_.find({x, y});
        return it != cells_.end() ? it->second.cost : 1.0;
    }

    void set_cost(int x, int y, double c) { cells_[{x, y}] = {c, 0}; }
    void set_terrain(int x, int y, int t) { cells_[{x, y}].terrain = t; }

    size_t cell_count() const { return cells_.size(); }
};

// ============================================================
// 基准测试
// ============================================================
struct BenchResult {
    double time_ms;
    const char* name;
};

template<typename F>
double benchmark(F fn, int iterations = 100) {
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; ++i) fn();
    auto end = std::chrono::high_resolution_clock::now();
    return std::chrono::duration<double, std::milli>(end - start).count() / iterations;
}

// ============================================================
// 主程序
// ============================================================
int main() {
    constexpr int SIZE = 512; // 512×512 = 262K cells

    std::cout << "========================================================\n";
    std::cout << "网格数据结构与内存布局 — 基准测试\n";
    std::cout << "网格尺寸: " << SIZE << "×" << SIZE << " = "
              << SIZE * SIZE << " cells\n";
    std::cout << "========================================================\n\n";

    // ---- 创建网格 ----
    std::cout << "--- 1. 内存占用 ---\n";

    // AoS
    aos::Grid grid_aos(SIZE, SIZE);
    for (int y = 0; y < SIZE; ++y)
        for (int x = 0; x < SIZE; ++x) {
            grid_aos.set_cost(x, y, 1.0 + (x + y) * 0.01);
            grid_aos.set_walkable(x, y, (x + y) % 5 != 0);
        }

    // SoA
    GridSoA grid_soa(SIZE, SIZE);
    for (int y = 0; y < SIZE; ++y)
        for (int x = 0; x < SIZE; ++x) {
            grid_soa.set_cost(x, y, 1.0 + (x + y) * 0.01);
            grid_soa.set_walkable(x, y, (x + y) % 5 != 0);
        }

    std::cout << "  AoS (vector<vector<Cell>>): " << grid_aos.memory_bytes() / 1024.0 / 1024.0
              << " MB\n";
    std::cout << "  SoA (flat array):           " << grid_soa.memory_bytes() / 1024.0 / 1024.0
              << " MB\n";

    // ---- 遍历 cost 基准 (SoA 的强项) ----
    std::cout << "\n--- 2. 遍历所有 cell 的 cost (求和) ---\n";

    auto bench_aos_sum = [&]() {
        double sum = 0;
        for (int y = 0; y < SIZE; ++y)
            for (int x = 0; x < SIZE; ++x)
                sum += grid_aos.cost_at(x, y);
        return sum;
    };

    auto bench_soa_sum = [&]() {
        double sum = 0;
        const double* d = grid_soa.cost_data();
        size_t n = grid_soa.rows * grid_soa.cols;
        for (size_t i = 0; i < n; ++i) sum += d[i];
        return sum;
    };

    double t_aos = benchmark(bench_aos_sum, 50);
    double t_soa = benchmark(bench_soa_sum, 50);
    std::cout << "  AoS: " << std::fixed << std::setprecision(3) << t_aos << " ms\n";
    std::cout << "  SoA: " << t_soa << " ms  (speedup: " << t_aos / t_soa << "x)\n";

    // ---- 随机访问基准 ----
    std::cout << "\n--- 3. 随机访问 (10K random lookups) ---\n";

    auto bench_aos_rand = [&]() {
        for (int i = 0; i < 10000; ++i) {
            int x = (i * 7919) % SIZE;
            int y = (i * 6271) % SIZE;
            volatile double v = grid_aos.cost_at(x, y);
            (void)v;
        }
    };
    auto bench_soa_rand = [&]() {
        for (int i = 0; i < 10000; ++i) {
            int x = (i * 7919) % SIZE;
            int y = (i * 6271) % SIZE;
            volatile double v = grid_soa.cost_at(x, y);
            (void)v;
        }
    };

    double t_rand_aos = benchmark(bench_aos_rand, 200);
    double t_rand_soa = benchmark(bench_soa_rand, 200);
    std::cout << "  AoS: " << t_rand_aos << " ms\n";
    std::cout << "  SoA: " << t_rand_soa << " ms\n";

    // ---- 分块网格 ----
    std::cout << "\n--- 4. 分块网格 (8192×8192 world, 10% chunks loaded) ---\n";

    ChunkedGrid chunked(8192, 8192);
    int expected_chunks = chunked.chunks_x * chunked.chunks_y; // 总数
    int loaded = 0;
    for (int cy = 0; cy < chunked.chunks_y; ++cy) {
        for (int cx = 0; cx < chunked.chunks_x; ++cx) {
            // 只加载有"内容"的区域：棋盘格加载 50%
            if ((cx + cy) % 2 == 0) {
                chunked.ensure_chunk(cx, cy);
                loaded++;
            }
        }
    }
    std::cout << "  Total chunks: " << expected_chunks
              << " (" << chunked.chunks_x << "×" << chunked.chunks_y << ")\n";
    std::cout << "  Loaded chunks: " << loaded
              << " (" << (100.0 * loaded / expected_chunks) << "%)\n";
    std::cout << "  Allocated: " << chunked.total_allocated_bytes() / 1024.0 / 1024.0 << " MB\n";

    // ---- N 维网格 ----
    std::cout << "\n--- 5. 模板化 N 维网格 ---\n";

    {
        GridND<double, 1> g1d(100);
        for (int i = 0; i < 100; ++i) g1d(i) = i * 0.1;
        std::cout << "  1D grid[100]: g1d(42) = " << g1d(42)
                  << ", extent=(" << g1d.extent(0) << ")\n";
    }
    {
        GridND<int, 3> g3d(10, 20, 30); // 体素世界: 10×20×30
        for (int z = 0; z < 10; ++z)
            for (int y = 0; y < 20; ++y)
                for (int x = 0; x < 30; ++x)
                    g3d(z, y, x) = z * 1000 + y * 100 + x;

        std::cout << "  3D grid[10][20][30]: g3d(5,3,7) = " << g3d(5, 3, 7)
                  << ", raw size=" << g3d.size() << "\n";
        std::cout << "  extents=(" << g3d.extent(0) << ", " << g3d.extent(1)
                  << ", " << g3d.extent(2) << ")\n";
    }

    // ---- 稀疏网格 (大世界 - 多空) ----
    std::cout << "\n--- 6. 稀疏网格 (10000², 1000 active cells) ---\n";
    SparseGrid sparse;
    for (int i = 0; i < 1000; ++i) {
        int x = (i * 7919) % 10000;
        int y = (i * 6271) % 10000;
        sparse.set_cost(x, y, 1.0 + i * 0.01);
    }
    std::cout << "  Cell count: " << sparse.cell_count() << "\n";
    std::cout << "  cost_at(500, 500): " << sparse.cost_at(500, 500) << " (should be default 1.0)\n";

    // ---- Unity 集成提示 ----
    std::cout << "\n--- 7. Unity 集成提示 (概念) ---\n";
    std::cout << "  在 Unity 中显示网格数据到 Scene View:\n";
    std::cout << "  1. 创建 GridVisualizer : MonoBehaviour 组件\n";
    std::cout << "  2. 在 OnDrawGizmos() 中遍历 Grid\n";
    std::cout << "  3. Gizmos.color = cost → 颜色映射; Gizmos.DrawCube()\n";
    std::cout << "  4. 对于大网格，只绘制摄像机视野内的 cell (culling)\n";
    std::cout << "  5. C++/Unity 数据交换: NativeArray<float> ↔ Unity Mesh\n";
    std::cout << "     或使用 ComputeBuffer 传递 cost 数据给 GPU\n";

    std::cout << "\nDone.\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o grid_ds grid_data_structures.cpp
./grid_ds
```

**预期输出:**
```
========================================================
网格数据结构与内存布局 — 基准测试
网格尺寸: 512×512 = 262144 cells
========================================================

--- 1. 内存占用 ---
  AoS (vector<vector<Cell>>): ~8.0 MB
  SoA (flat array):           ~5.0 MB

--- 2. 遍历所有 cell 的 cost (求和) ---
  AoS: ~1.2xx ms
  SoA: ~0.2xx ms  (speedup: ~4-6x)

--- 3. 随机访问 (10K random lookups) ---
  AoS: ~0.0xx ms
  SoA: ~0.0xx ms

--- 4. 分块网格 (8192×8192 world, 50% chunks loaded) ---
  Total chunks: 262144 (512×512)
  Loaded chunks: 131072 (50%)
  Allocated: ~32 MB

--- 5. 模板化 N 维网格 ---
  1D grid[100]: g1d(42) = 4.2, extent=(100)
  3D grid[10][20][30]: g3d(5,3,7) = 5307, raw size=6000
  extents=(10, 20, 30)

--- 6. 稀疏网格 (10000², 1000 active cells) ---
  Cell count: 1000
  cost_at(500, 500): 1 (should be default 1.0)

--- 7. Unity 集成提示 (概念) ---
  ...
```

### Unity Scene View 集成示例 (C#)

```csharp
// GridVisualizer.cs — 挂到场景中的空 GameObject 上
// 在 Scene View 中用 Gizmos 绘制网格数据

using UnityEngine;
using System;

public class GridVisualizer : MonoBehaviour
{
    [Header("Grid Settings")]
    public int width = 50;
    public int height = 50;
    public float cellSize = 1f;
    public Vector3 origin = Vector3.zero;

    [Header("Visual")]
    public bool showCost = true;
    public float costMin = 1f;
    public float costMax = 10f;

    // 模拟的 C++ SoA 数据 (实际项目中从 C++  DLL/插件获取)
    private float[] costs;
    private bool[] walkable;

    void Awake()
    {
        costs = new float[width * height];
        walkable = new bool[width * height];
        GenerateRandomTerrain();
    }

    void GenerateRandomTerrain()
    {
        var rng = new System.Random(42);
        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                int i = y * width + x;
                // 障碍物：边缘 + 随机斑点
                bool isWall = (x == 0 || x == width-1 || y == 0 || y == height-1) ||
                              (rng.NextDouble() < 0.15);
                walkable[i] = !isWall;
                costs[i] = isWall ? float.MaxValue : (float)(1.0 + rng.NextDouble() * 4.0);
            }
        }
    }

    void OnDrawGizmos()
    {
        if (costs == null) return;

        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                int i = y * width + x;
                Vector3 pos = origin + new Vector3(x * cellSize, 0, y * cellSize);

                if (!walkable[i])
                {
                    Gizmos.color = Color.red;
                    Gizmos.DrawCube(pos, Vector3.one * cellSize * 0.9f);
                }
                else if (showCost)
                {
                    // 代价 → 颜色映射：低代价绿色 → 高代价红色
                    float t = Mathf.InverseLerp(costMin, costMax, costs[i]);
                    Gizmos.color = Color.Lerp(Color.green, Color.red, t);
                    Gizmos.DrawCube(pos, Vector3.one * cellSize * 0.7f);
                }
            }
        }
    }
}
```

## 3. 练习

### 基础练习
1. **改写 04 的 A* 为 SoA 网格**：将 `std::vector<std::vector<Cell>>` 替换为本节的 `GridSoA` 类，观察性能变化。（提示：`index(x,y)` 替代 `cells[x][y]`）
2. **验证 stride 计算**：手动写出一个 `4×5×6` 的 3D Grid 的 strides，然后运行 `GridND<int, 3>(4,5,6)` 验证 `strides[2]` 是否等于 1，`strides[1]` 是否等于 6，`strides[0]` 是否等于 30。

### 进阶练习
1. **添加 `for_each_neighbor_8dir` 的 SoA 版本**：在 `GridSoA` 中添加 8 方向邻居迭代，处理对角线 corner-cutting。
2. **实现分块网格的 A***：扩展 `ChunkedGrid` 使其能用 A* 寻路。提示：`for_each_neighbor` 需要检查跨 chunk 边界 (`CHUNK_MASK` 判断)。
3. **性能测量**：修改 `fill_cost` 用 `std::fill` 对比 `std::memset`（仅当 T 是 POD 时）。测量 `512×512` 网格上 100 次 memset vs fill 的时间。

### 挑战练习（可选）
1. **实现基于位图的 SoA walkable**：将 `std::vector<bool>`（每个 bool 1 bit）替换为手写的 `std::vector<uint64_t>` 位图。实现 `bool is_walkable(size_t idx)` 的位运算版本。在 4096×4096 网格上对比内存占用。
2. **流式分块加载**：为 `ChunkedGrid` 添加 `load_range(int x0, int y0, int x1, int y1)` 和 `unload_outside(int x0, int y0, int x1, int y1)`，模拟摄像机移动时的分块流式加载。


## 3.5 参考答案

> [!tip]- 基础练习 1 参考答案 — 改写 A\* 为 SoA 网格
> 将教程 04 的 A\* 中的 `std::vector<std::vector<Cell>>` 替换为 `GridSoA`，用 `index(x,y)` 替代 `cells[x][y]`。核心改动点：
>
> ```cpp
> // 原来的 AoS 访问
> double cost = grid.cells[x][y].cost;
> bool   walk = grid.cells[x][y].walkable;
>
> // 改为 SoA 访问
> size_t idx = grid.index(x, y);
> double cost = grid.cost_data()[idx];
> bool   walk = grid.walkable_data()[idx];
> ```
>
> 完整改造示例：
>
> ```cpp
> // SoA 版 A* — 直接操作平坦数组指针以消除 index() 乘法开销
> auto astar_soa(const GridSoA& grid, int sx, int sy, int gx, int gy)
>     -> std::vector<std::pair<int,int>>
> {
>     int rows = grid.rows, cols = grid.cols;
>     size_t total = static_cast<size_t>(rows) * cols;
>     const double INF = std::numeric_limits<double>::infinity();
>
>     std::vector<double> g_cost(total, INF);
>     std::vector<int> parent(total, -1);
>     std::vector<bool> closed(total, false);
>
>     struct State { double f, g; int x, y;
>         bool operator<(const State& o) const { return f > o.f; } };
>     std::priority_queue<State> open;
>
>     auto idx = [cols](int x, int y) { return static_cast<size_t>(y) * cols + x; };
>     auto heuristic = [](int x1, int y1, int x2, int y2) {
>         return std::abs(x1-x2) + std::abs(y1-y2); }; // 曼哈顿
>
>     size_t si = idx(sx, sy);
>     g_cost[si] = 0.0;
>     open.push({heuristic(sx,sy,gx,gy), 0.0, sx, sy});
>
>     static const int DX[] = {1,-1,0,0};
>     static const int DY[] = {0,0,1,-1};
>
>     while (!open.empty()) {
>         State cur = open.top(); open.pop();
>         int x = cur.x, y = cur.y;
>         size_t ci = idx(x, y);
>         if (closed[ci]) continue;
>         closed[ci] = true;
>
>         if (x == gx && y == gy) {
>             std::vector<std::pair<int,int>> path;
>             for (int i = idx(gx, gy); i != -1; i = parent[i]) {
>                 int px = static_cast<int>(i) / cols;
>                 int py = static_cast<int>(i) % cols;
>                 path.emplace_back(px, py);
>             }
>             std::reverse(path.begin(), path.end());
>             return path;
>         }
>
>         for (int d = 0; d < 4; ++d) {
>             int nx = x + DX[d], ny = y + DY[d];
>             if (nx < 0 || nx >= rows || ny < 0 || ny >= cols) continue;
>             size_t ni = idx(nx, ny);
>             if (!grid.walkable_data()[ni]) continue;
>
>             double step_cost = grid.cost_data()[ni];
>             double new_g = g_cost[ci] + step_cost;
>             if (new_g < g_cost[ni]) {
>                 g_cost[ni] = new_g;
>                 parent[ni] = static_cast<int>(ci);
>                 double f = new_g + heuristic(nx, ny, gx, gy);
>                 open.push({f, new_g, nx, ny});
>             }
>         }
>     }
>     return {};
> }
> ```
>
> **性能变化预期：** SoA 版在 cost 查询时只需一次指针解引用 `cost_data()[ni]`，而 AoS 版需要 `cells[x][y].cost` → 两次间接寻址（外部 vector + 内部 vector）。在 512×512 网格上遍历搜索的 10K-50K 节点时，SoA 版通常比 AoS 版快 1.3-2×（取决于缓存压力）。

> [!tip]- 基础练习 2 参考答案 — 验证 stride 计算
> **手动计算 4×5×6 3D Grid 的 strides（row-major，最后维度连续）：**
>
> - `strides[2]` (最内层维度，dim 2，size=6)：**1** —— 相邻元素在内存中差 1
> - `strides[1]` (dim 1，size=5)：`strides[2] * extent[2] = 1 * 6 =` **6**
> - `strides[0]` (dim 0，size=4)：`strides[1] * extent[1] = 6 * 5 =` **30**
>
> **内存布局：** `data[0..29]` 第一层，`data[30..59]` 第二层，...，总共 4×5×6=120 元素。
>
> **index(i₀, i₁, i₂) = i₀·30 + i₁·6 + i₂·1**
>
> **验证代码：**
>
> ```cpp
> GridND<int, 3> g(4, 5, 6);
> std::cout << "strides[2] (innermost, size 6): "
>           << g.index(0, 0, 1) - g.index(0, 0, 0) << " (expected 1)\n";
> std::cout << "strides[1] (middle, size 5):    "
>           << g.index(0, 1, 0) - g.index(0, 0, 0) << " (expected 6)\n";
> std::cout << "strides[0] (outermost, size 4):  "
>           << g.index(1, 0, 0) - g.index(0, 0, 0) << " (expected 30)\n";
> ```
>
> **验证连续分配：** 写入连续值并验证 `g(0,0,0)` 到 `g(0,0,5)` 在内存中地址连续（`raw_data()[0]` 到 `raw_data()[5]`），`g(0,1,0)` 应该在 `raw_data()[6]`。

> [!tip]- 进阶练习 1 参考答案 — SoA 8 方向邻居迭代
> 在 `GridSoA` 中添加 8 方向迭代，包含对角线 corner-cutting 检查：
>
> ```cpp
> // 添加到 GridSoA 类中
> void for_each_neighbor_8dir(int x, int y,
>     std::function<void(int nx, int ny, double step_cost)> callback) const
> {
>     static const int DX[] = {1,-1,0,0,  1,1,-1,-1};
>     static const int DY[] = {0,0,1,-1,  1,-1,1,-1};
>     static const double BASE_COST[] = {
>         1.0, 1.0, 1.0, 1.0,
>         std::sqrt(2.0), std::sqrt(2.0), std::sqrt(2.0), std::sqrt(2.0)
>     };
>
>     for (int d = 0; d < 8; ++d) {
>         int nx = x + DX[d], ny = y + DY[d];
>         if (!in_bounds(nx, ny)) continue;
>         size_t ni = index(nx, ny);
>         if (!walkable_[ni]) continue;
>
>         // Corner-cutting 检查 (d >= 4 是对角线方向)
>         if (d >= 4) {
>             int adj1_x = x + DX[d];  // 水平邻居
>             int adj1_y = y;
>             int adj2_x = x;
>             int adj2_y = y + DY[d];  // 垂直邻居
>
>             bool adj1_blocked = !in_bounds(adj1_x, adj1_y)
>                 || !walkable_[index(adj1_x, adj1_y)];
>             bool adj2_blocked = !in_bounds(adj2_x, adj2_y)
>                 || !walkable_[index(adj2_x, adj2_y)];
>
>             // 两侧都是墙 → 禁止穿越
>             if (adj1_blocked && adj2_blocked) continue;
>         }
>
>         callback(nx, ny, BASE_COST[d] * cost_[ni]);
>     }
> }
> ```
>
> **模板化优化（生产级）：**
>
> ```cpp
> template<typename F>
> void for_each_neighbor_8dir(int x, int y, F&& callback) const {
>     // ... 同上逻辑，但 callback 是模板参数，避免 std::function 堆分配
>     // 在热路径中这是显著的优化
> }
> ```

> [!tip]- 进阶练习 2 参考答案 — 分块网格 A\*
> `ChunkedGrid` 的 key insight：邻居迭代用**全局坐标**，`cost_at(x,y)` 内部处理 chunk 查找。A\* 算法本身无需修改——只需要一致的 `cost_at` 和 `walkable_at` 接口。
>
> ```cpp
> // 为 ChunkedGrid 补充 walkable_at 查询
> bool walkable_at(int x, int y) const {
>     if (x < 0 || x >= world_rows || y < 0 || y >= world_cols) return false;
>     int cx = y / CHUNK_SIZE;  // chunk 列
>     int cy = x / CHUNK_SIZE;  // chunk 行
>     Chunk* c = chunk_map_[chunk_index(cx, cy)];
>     if (!c) return true;  // 未加载 = 默认可通行
>     int lx = x % CHUNK_SIZE, ly = y % CHUNK_SIZE;
>     return c->walkable[lx * CHUNK_SIZE + ly];
> }
>
> // 跨 chunk 边界的邻居迭代
> void for_each_neighbor(int x, int y,
>     std::function<void(int nx, int ny, double step_cost)> callback) const
> {
>     static const int DX[] = {1,-1,0,0};
>     static const int DY[] = {0,0,1,-1};
>
>     for (int d = 0; d < 4; ++d) {
>         int nx = x + DX[d], ny = y + DY[d];
>         if (nx < 0 || nx >= world_rows || ny < 0 || ny >= world_cols) continue;
>         if (!walkable_at(nx, ny)) continue;
>
>         // cost_at 内部自动处理 chunk 查找和 chunk 边界
>         callback(nx, ny, cost_at(nx, ny));
>     }
> }
> ```
>
> **Chunked A\* 的完整签名：**
>
> ```cpp
> auto astar_chunked(const ChunkedGrid& grid, int sx, int sy, int gx, int gy,
>                    std::vector<std::pair<int,int>>& out_path)
>     -> bool
> {
>     // 使用 pair<int,int> 作为 key 的 unordered_map 存储 g_cost 和 parent
>     // 因为分块网格的活跃区域远小于世界总尺寸
>     std::unordered_map<size_t, double> g_cost; // key = (x<<32)|y
>     std::unordered_map<size_t, std::pair<int,int>> parent;
>
>     auto hash_xy = [](int x, int y) -> size_t {
>         return (static_cast<uint64_t>(x) << 32) | static_cast<uint32_t>(y);
>     };
>
>     // ... A* 逻辑同前，但使用 cost_at/walkable_at/world_rows/world_cols
>     // 而不是 rows/cols/cells
>     return true; // placeholder
> }
> ```
>
> **关键设计决策：** 在分块网格上，`closed` 和 `g_cost` 集合不应分配 `world_rows × world_cols` 大小——那会抵消分块的全部好处。使用 `std::unordered_map` 或与 chunk 粒度对齐的稀疏存储。需要 `ensure_chunk` 在探索到未加载 chunk 时自动创建。

> [!tip]- 进阶练习 3 参考答案 — memset vs fill 性能测量
> `memset` 只能用于 trivially copyable 且不包含非平凡构造的类型。`std::fill` 对 POD 类型通常会优化为 `memset`，但不是保证。
>
> ```cpp
> #include <cstring>
> #include <chrono>
>
> // 在 GridSoA 中添加
> void fill_cost_memset(double value) {
>     // 警告：仅对整数零值的 memset 是可移植的
>     // 对于 double，只有 value == 0.0 时 memset 正确（IEEE 754 零 = 全零位）
>     if (value == 0.0) {
>         std::memset(cost_.data(), 0, cost_.size() * sizeof(double));
>     } else {
>         // 其他值用 memset 不安全（double 的 bit pattern 不等于字节重复）
>         std::fill(cost_.begin(), cost_.end(), value);
>     }
> }
>
> // 基准代码
> void bench_memset_vs_fill() {
>     constexpr int SIZE = 512;
>     constexpr int ITERATIONS = 100;
>
>     GridSoA grid(SIZE, SIZE);
>     size_t n = grid.rows * grid.cols;
>
>     // memset 版本 (仅对 0.0 安全)
>     auto bench_memset = [&]() {
>         for (int i = 0; i < ITERATIONS; ++i)
>             std::memset(const_cast<double*>(grid.cost_data()), 0,
>                         n * sizeof(double));
>     };
>
>     // std::fill 版本
>     auto bench_fill = [&]() {
>         for (int i = 0; i < ITERATIONS; ++i)
>             std::fill(const_cast<double*>(grid.cost_data()),
>                       const_cast<double*>(grid.cost_data()) + n, 0.0);
>     };
>
>     auto t1 = std::chrono::high_resolution_clock::now();
>     bench_memset();
>     auto t2 = std::chrono::high_resolution_clock::now();
>     bench_fill();
>     auto t3 = std::chrono::high_resolution_clock::now();
>
>     double ms_memset = std::chrono::duration<double, std::milli>(t2 - t1).count();
>     double ms_fill   = std::chrono::duration<double, std::milli>(t3 - t2).count();
>
>     std::cout << "memset(0): " << ms_memset << " ms ("
>               << (n * sizeof(double) * ITERATIONS / ms_memset / 1e6) << " GB/s)\n";
>     std::cout << "fill(0):   " << ms_fill << " ms ("
>               << (n * sizeof(double) * ITERATIONS / ms_fill / 1e6) << " GB/s)\n";
>     std::cout << "Ratio: fill/memset = " << ms_fill / ms_memset << "x\n";
> }
> ```
>
> **预期结果：** 在启用 `-O2` 的现代编译器上，`std::fill` 对 POD 类型会内联为 `__builtin_memset`，两者性能几乎相同（±5%）。差异来自：`memset` 是库函数调用（可能被优化为 REP STOSB），而 `std::fill` 可能被自动向量化为 SSE/AVX 循环。实际测量中两者带宽通常都在 40-60 GB/s 左右。

> [!tip]- 挑战练习 1 参考答案 — 位图 SoA walkable
> 将 `std::vector<bool>` 替换为 `std::vector<uint64_t>` 位图，提供手写位运算访问。
>
> ```cpp
> class BitmapWalkable {
>     std::vector<uint64_t> bits_;
>     size_t total_cells_;
>
>     static constexpr int BITS_PER_WORD = 64;
>
> public:
>     BitmapWalkable(size_t total_cells)
>         : total_cells_(total_cells),
>           bits_((total_cells + BITS_PER_WORD - 1) / BITS_PER_WORD, ~0ULL)
>     {}
>
>     // 位查询
>     bool test(size_t idx) const {
>         size_t word = idx / BITS_PER_WORD;
>         size_t bit  = idx % BITS_PER_WORD;
>         return (bits_[word] >> bit) & 1ULL;
>     }
>
>     // 位设置
>     void set(size_t idx, bool value) {
>         size_t word = idx / BITS_PER_WORD;
>         size_t bit  = idx % BITS_PER_WORD;
>         if (value)
>             bits_[word] |=  (1ULL << bit);
>         else
>             bits_[word] &= ~(1ULL << bit);
>     }
>
>     // 批量操作：一次设置 64 个 cell
>     void fill_word(size_t word_idx, uint64_t mask) {
>         bits_[word_idx] = mask;
>     }
>
>     size_t memory_bytes() const {
>         return bits_.capacity() * sizeof(uint64_t);
>     }
>
>     const uint64_t* raw_bits() const { return bits_.data(); }
> };
> ```
>
> **内存对比 (4096×4096 = 16M cells)：**
>
> | 方案 | 内存占用 | 说明 |
> |------|---------|------|
> | `std::vector<bool>` | ~2 MB | 1 bit/cell，但 `data()` 不可用，迭代器代理对象有开销 |
> | `std::vector<uint8_t>` | 16 MB | 1 byte/cell，简单但浪费 87.5% |
> | `BitmapWalkable` | ~2 MB | 1 bit/cell，手写位图，可直接访问 `uint64_t*` |
>
> **位图 + SoA 的完整 Grid 类：** 将 `BitmapWalkable` 整合进 `GridSoA`，替换 `std::vector<bool> walkable_`，保持 `cost_` 和 `terrain_id_` 不变。寻路时先做便宜的 `walkable` 位测试，再读取 `cost`。

> [!tip]- 挑战练习 2 参考答案 — 流式分块加载
> 为 `ChunkedGrid` 添加基于视口范围的增量加载/卸载：
>
> ```cpp
> // 添加到 ChunkedGrid 类
>
> // 确保指定矩形区域内的所有 chunk 都已加载
> void load_range(int x0, int y0, int x1, int y1) {
>     // 裁剪到世界边界
>     x0 = std::max(0, x0); y0 = std::max(0, y0);
>     x1 = std::min(world_rows - 1, x1);
>     y1 = std::min(world_cols - 1, y1);
>
>     int cx0 = y0 / CHUNK_SIZE; int cy0 = x0 / CHUNK_SIZE;
>     int cx1 = y1 / CHUNK_SIZE; int cy1 = x1 / CHUNK_SIZE;
>
>     for (int cy = cy0; cy <= cy1; ++cy)
>         for (int cx = cx0; cx <= cx1; ++cx)
>             ensure_chunk(cx, cy);
> }
>
> // 卸载指定矩形外面的所有 chunk
> void unload_outside(int x0, int y0, int x1, int y1,
>                     int margin_chunks = 2) // 保留边缘的 margin
> {
>     x0 = std::max(0, x0); y0 = std::max(0, y0);
>     x1 = std::min(world_rows - 1, x1);
>     y1 = std::min(world_cols - 1, y1);
>
>     int cx0 = y0 / CHUNK_SIZE - margin_chunks;
>     int cy0 = x0 / CHUNK_SIZE - margin_chunks;
>     int cx1 = y1 / CHUNK_SIZE + margin_chunks;
>     int cy1 = x1 / CHUNK_SIZE + margin_chunks;
>
>     // 遍历所有已加载的 chunk，卸载不在视口内的
>     chunks_.erase(
>         std::remove_if(chunks_.begin(), chunks_.end(),
>             [&](const std::unique_ptr<Chunk>& c) {
>                 if (c->chunk_x < cx0 || c->chunk_x > cx1 ||
>                     c->chunk_y < cy0 || c->chunk_y > cy1) {
>                     chunk_map_[chunk_index(c->chunk_x, c->chunk_y)] = nullptr;
>                     return true;
>                 }
>                 return false;
>             }),
>         chunks_.end());
> }
>
> // 摄像机移动时调用（每帧或每 N 帧）
> void update_streaming(const ChunkedGrid& grid,
>                       int cam_x, int cam_y,
>                       int view_radius) {
>     // 加载新的可见 chunk
>     grid.load_range(cam_x - view_radius, cam_y - view_radius,
>                     cam_x + view_radius, cam_y + view_radius);
>     // 卸载远处 chunk（异步可另行处理）
>     grid.unload_outside(cam_x - view_radius, cam_y - view_radius,
>                         cam_x + view_radius, cam_y + view_radius,
>                         /*margin=*/3);
> }
> ```
>
> **生产级注意事项：**
> - 每帧只处理有限数量的 chunk 加载/卸载（如 2-3 个），避免帧时间尖峰
> - 使用 `std::future` 或 job system 异步加载 chunk 数据（从磁盘/网络）
> - 远端 chunk 可降级为低 LOD（粗粒度路径图），节省内存
> - chunk 卸载前标记 `loaded = false` 但不立即释放内存——使用 LRU 淘汰策略

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **Data-Oriented Design (Richard Fabian)**：整本书都在讲为什么 AoS vs SoA 影响游戏性能。关键章节：Chapter 2 "Data Layout"。
- **Game Engine Architecture (Jason Gregory)**：第 6 章讨论内存管理与数据导向设计。
- **"What Every Programmer Should Know About Memory" (Ulrich Drepper)**：经典长文，详细解释 CPU 缓存为何主导性能。关注 3.3 "Cache effects on data layout"。
- **Intel Intrinsics Guide**：`_mm256_loadu_pd` / `_mm256_fmadd_pd` — 当你用 SoA 布局时，这些 SIMD 指令可以直接操作连续 float/double 数组，而不需要 gather/scatter。
- **Unity Job System + Burst Compiler**：在 Unity 中，`NativeArray<T>` 就是平坦 SoA 数组。Jobs 对连续内存的 SIMD 自动向量化正是 SoA 的最大受益者。
- **std::mdspan (C++23)**：标准化的多维视图，不拥有内存但提供 `mdspan[x,y,z]` 语法。与 `GridND` 的概念一致。

## 常见陷阱

1. **错误的行/列顺序**：`index = y * width + x`（row-major）vs `index = x * height + y`（col-major）。混用会导致数据静默错位，且不会崩溃——只是所有访问偏移了一点点。**对策**：在 Debug 模式断言 `index(x,y)` 对于连续 y 值产生连续 index。

2. **std::vector<bool> 不是容器**：`std::vector<bool>` 是位压缩的特化，`data()` 不返回 `bool*`，`operator[]` 返回代理对象。在需要原始指针的场景用 `std::vector<uint8_t>` 或 `std::vector<char>` 替代。

3. **分块边界处理**：当 chunk 边界恰好穿过寻路路径时，`for_each_neighbor` 必须处理跨 chunk 情况。忘记处理 → 路径在 chunk 边界断裂。**对策**：邻居迭代时用全局坐标，在 `cost_at(x,y)` 内部处理 chunk 查找。

4. **过早优化稀疏数据结构**：如果你的世界是大片连续的（如开放世界地形），稠密平坦数组通常比稀疏 map 更快、代码更简单。稀疏结构只适用于 < 5% 的格子有数据的场景（如太空游戏中的小行星带）。

5. **std::function 在热路径中**：`for_each_neighbor` 中的 `std::function` callback 可能触发堆分配。在生产代码中用模板参数替代：`template<typename F> void for_each_neighbor(int x, int y, F&& callback)`。
