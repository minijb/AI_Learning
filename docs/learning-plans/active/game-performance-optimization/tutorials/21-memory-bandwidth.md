# 内存带宽优化 — 压缩与数据布局
> 所属计划: 游戏性能优化全攻略
> 预计耗时: 50 分钟
> 前置知识: CPU 缓存层级概念，数据结构基础，了解顶点/纹理在 GPU 中的角色
---
## 1. 概念讲解

### 为什么需要这个？

大多数开发者关注的是计算量（这个算法是 O(N) 还是 O(log N)），但现代游戏性能的真正瓶颈常常不是计算，而是**数据传输**。

一个残酷的事实：CPU 读取一次 L1 缓存中的数据需要 ~1ns（约 4 个时钟周期），读取一次主内存（DRAM）需要 ~100ns。100 倍的差距。如果你的代码每秒需要处理 1GB 的数据但只有 10% 命中 L1 缓存，那么 90% 的时间都在等待内存。

对 GPU 同理：GPU 的算力（TFLOPs）远超显存带宽（GB/s），在带宽受限场景下，GPU 的大部分计算单元处于闲置等待数据状态。

**内存带宽是沉默的瓶颈** — 它不会表现为 100% CPU 占用或 GPU 满载，而是帧率"莫名"上不去。

### 核心思想

#### 1. 理解内存层级

```
寄存器 (Register)     ~0 延迟     <1KB
L1 缓存              ~1ns       32-64KB/核心
L2 缓存              ~5-10ns    256KB-1MB/核心
L3 缓存 (LLC)        ~20-40ns   8-32MB/共享
主内存 (DRAM)        ~80-120ns  8-64GB
GPU 显存 (VRAM)      ~200-500ns 4-24GB (通过 PCIe 更慢)
```

关键：**L1 缓存行（cache line）是 64 字节**。当你访问一个 `int`（4 字节），CPU 实际会加载周围的 60 字节进入缓存。这是机会（相邻数据免费），也是陷阱（浪费了 60 字节的带宽）。

#### 2. 步长对性能的影响

```cpp
// 步长 = 1 (64 字节 / 4 字节 = 每缓存行 16 个元素)
for (int i = 0; i < N; i++) sum += data[i].x;  // 步长 = sizeof(Vec3) = 12

// 步长 = 4096 (1 个元素 / 缓存行, 每访问一次就 miss)
for (int i = 0; i < N; i++) sum += scattered[i * 1024].x;
```

步长越大，每次访问都跨缓存行，带宽利用率越低。

#### 3. 纹理压缩 — 节省 GPU 带宽

| 格式 | 每像素大小 | 相对 RGBA8 | 说明 |
|------|-----------|------------|------|
| RGBA8 (未压缩) | 32 bits (4 bytes) | 1× | 基准 |
| DXT1/BC1 | 4 bits | 8× | 无 alpha 的漫反射贴图 |
| DXT5/BC3 | 8 bits | 4× | 带 alpha 的法线/漫反射 |
| BC5 | 8 bits | 4× | 双通道，适合法线贴图 |
| BC6H | 8 bits | 4× | HDR 纹理 |
| BC7 | 8 bits | 4× | 高质量 RGBA |
| ASTC | 0.89-8 bits | 4×-36× | 移动端主流，支持任意比特率 |

压缩纹理不仅节省显存，更重要的是减少纹理采样时的带宽消耗——每次纹理采样从 VRAM 读取更少的字节。

#### 4. 顶点压缩

每帧渲染数百万个顶点，顶点数据从 VRAM 传输到 GPU 着色器的带宽不容忽视：

```cpp
// 未压缩: 12 + 12 + 8 + 8 = 40 bytes/vertex
struct Vertex {
    float pos[3];    // 12 bytes
    float normal[3]; // 12 bytes
    float uv[2];     // 8 bytes
    float tangent[4];// 8 bytes (half-float would be 4 bytes)
};

// 压缩后: 6 + 4 + 4 + 4 = 18 bytes/vertex (节省 55%)
struct CompressedVertex {
    int16_t pos[3];     // half-float × 3 = 6 bytes (量化)
    int8_t  normal[3];  // snorm8 × 3  = 3 bytes + 1 pad
    half    uv[2];      // half-float × 2 = 4 bytes
    int8_t  tangent[4]; // snorm8 × 4 = 4 bytes
};
```

**量化技术**：将浮点范围映射到整数范围。
```
// 位置量化: 将世界坐标 (0-655.35m) 映射到 uint16 (0-65535)
uint16_t quantized_x = uint16_t((world_x / MAX_WORLD_SIZE) * 65535.0f);
// GPU 端还原: float x = quantized_x * (MAX_WORLD_SIZE / 65535.0);
```

**half-float (FP16)**: 10 位有效精度，范围 ±65504，对法线、UV 坐标通常足够。

#### 5. 数据布局: AoS vs SoA

**AoS (Array of Structures)** — 常规面向对象布局：
```cpp
struct Particle { float x, y, z, vx, vy, vz, lifetime; };
Particle particles[10000];
// 更新位置: 读取 position 时也加载了 vx/vy/vz/lifetime（浪费）
```

**SoA (Structure of Arrays)** — 数据导向布局：
```cpp
struct ParticleSystem {
    float x[10000], y[10000], z[10000];
    float vx[10000], vy[10000], vz[10000];
    float lifetime[10000];
};
// 更新位置: 只读取 x/y/z，缓存行 100% 利用
```

当只访问部分字段时，SoA 可以大幅提高缓存利用率。

#### 6. 索引缓冲优化

- **16-bit vs 32-bit 索引**: 如果网格顶点 < 65536，用 `uint16` 索引，大小减半。
- **索引排序/重排**: 优化顶点缓存命中率（如 Forsyth 算法），减少 GPU 的顶点着色器重复计算。
- **Meshlet 压缩**: 将网格切分为小片（通常 ≤ 128 个三角形），每个 meshlet 用更少的索引位宽，配合 Mesh Shader 减少带宽。

#### 7. 测量工具

- **Intel VTune** — Memory Access 分析：显示 L1/L2/L3/DRAM 的命中率和带宽占用，精确定位热点。
- **AMD uProf** — 类似功能，支持 Zen 架构的详细计数器。
- **GPU 计数器**: NVIDIA Nsight Graphics / AMD Radeon GPU Profiler 显示显存带宽利用率、纹理缓存命中率。
- **`perf stat`** (Linux): `perf stat -e cache-references,cache-misses ./your_app` 快速查看缓存命中率。

---
## 2. 代码示例

两个独立基准测试：
1. 不同步长遍历大数组 — 展示内存带宽墙。
2. 顶点量化压缩 — 对比 float32 和 half-float/量化整数的带宽节省。

### 完整代码

```cpp
// memory_bandwidth_bench.cpp
// 编译: g++ -std=c++17 -O2 -o bandwidth_bench memory_bandwidth_bench.cpp
// 运行: ./bandwidth_bench

#include <iostream>
#include <chrono>
#include <vector>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <iomanip>

// ============================================================
// 1. 步长遍历基准 — 展示缓存层级边界
// ============================================================

struct Vec3 { float x, y, z; };

void bench_stride_access() {
    std::cout << "=== 基准 1: 步长遍历 — 内存带宽墙 ===\n\n";

    // 分配 128 MB 的测试数组
    constexpr size_t TEST_SIZE_MB  = 128;
    constexpr size_t ELEMENT_COUNT = (TEST_SIZE_MB * 1024 * 1024) / sizeof(Vec3);
    // 约 11M 个 Vec3

    std::vector<Vec3> data(ELEMENT_COUNT);
    for (size_t i = 0; i < ELEMENT_COUNT; ++i) {
        data[i] = {float(i), float(i + 1), float(i + 2)};
    }

    // 不同步长测试
    size_t strides[] = {1, 2, 4, 8, 16, 32, 64, 128, 256, 512};
    // 步长 × sizeof(Vec3) = 实际步长（字节数）

    std::cout << std::setw(8)  << "步长"
              << std::setw(12) << "字节/跳"
              << std::setw(12) << "时间(ms)"
              << std::setw(14) << "带宽(MB/s)"
              << std::setw(12) << "ns/元素"
              << "\n";
    std::cout << std::string(58, '-') << "\n";

    for (size_t stride : strides) {
        const size_t count = ELEMENT_COUNT / stride;
        const size_t bytes_per_stride = stride * sizeof(Vec3);

        // 预热：避免冷缓存影响
        volatile float sink = 0;
        for (size_t i = 0; i < count; ++i) {
            sink += data[i * stride].x;
        }

        auto start = std::chrono::high_resolution_clock::now();

        float sum = 0;
        for (size_t i = 0; i < count; ++i) {
            sum += data[i * stride].x; // 只访问 .x（4 bytes）
        }

        auto end = std::chrono::high_resolution_clock::now();
        double elapsed_ms = std::chrono::duration<double, std::milli>(end - start).count();

        // 带宽计算: 每次迭代加载一个完整的缓存行（64B）
        // 但由于步长可能跨缓存行，有效数据量是 count × 4 bytes
        double accessed_bytes = static_cast<double>(count * sizeof(float));
        double bandwidth_mbps = (accessed_bytes / (1024.0 * 1024.0)) / (elapsed_ms / 1000.0);
        double ns_per_element = (elapsed_ms * 1e6) / count;

        // 防止编译器优化掉
        volatile float prevent = sum;
        (void)prevent;

        std::cout << std::setw(8)  << stride
                  << std::setw(12) << bytes_per_stride
                  << std::setw(12) << std::fixed << std::setprecision(2) << elapsed_ms
                  << std::setw(14) << std::fixed << std::setprecision(1) << bandwidth_mbps
                  << std::setw(12) << std::fixed << std::setprecision(2) << ns_per_element;

        // 标注可能的缓存层级
        if (stride == 1)  std::cout << "  ← L1/L2 友好";
        if (stride == 8)  std::cout << "  ← L2 边界";
        if (stride == 64) std::cout << "  ← L3 边界";
        if (stride == 512) std::cout << "  ← DRAM 墙";
        std::cout << "\n";
    }

    std::cout << "\n分析:\n";
    std::cout << "  步长=1:   一个缓存行(64B)容纳 16 个连续 Vec3? 实际是 64/12≈5.3 个\n";
    std::cout << "           每缓存行有效数据约 5×4=20 字节 → 利用率 31%\n";
    std::cout << "           如用 SoA(float x[N])，则步长=1 时每缓存行 16 个 float\n";
    std::cout << "           利用率 100%，带宽效率提升 3 倍+\n";
    std::cout << "  步长=64:  每访问一跳 64×12=768 字节，跨越 12 个缓存行\n";
    std::cout << "           每次访问几乎必定 cache miss → 性能跌入 DRAM 墙\n";
}

// ============================================================
// 2. AoS vs SoA 对比
// ============================================================
struct ParticleAoS {
    float x, y, z;
    float vx, vy, vz;
    float lifetime;
    int   flags;
}; // 32 bytes

struct ParticleSystemSoA {
    std::vector<float> x, y, z;
    std::vector<float> vx, vy, vz;
    std::vector<float> lifetime;
    std::vector<int>   flags;

    ParticleSystemSoA(size_t n)
        : x(n), y(n), z(n)
        , vx(n), vy(n), vz(n)
        , lifetime(n), flags(n) {}
};

void bench_aos_vs_soa() {
    std::cout << "\n=== 基准 2: AoS vs SoA 数据布局 ===\n\n";

    constexpr size_t N = 10'000'000; // 10M 粒子

    // AoS
    std::vector<ParticleAoS> aos(N);
    for (size_t i = 0; i < N; ++i) {
        aos[i] = {float(i), float(i+1), float(i+2),
                  float(i+3), float(i+4), float(i+5), 1.0f, 0};
    }

    // SoA
    ParticleSystemSoA soa(N);
    for (size_t i = 0; i < N; ++i) {
        soa.x[i] = float(i);
        soa.y[i] = float(i+1);
        soa.z[i] = float(i+2);
        soa.vx[i] = float(i+3);
        soa.vy[i] = float(i+4);
        soa.vz[i] = float(i+5);
        soa.lifetime[i] = 1.0f;
        soa.flags[i] = 0;
    }

    // 场景: 只更新位置 (x, y, z) — 不碰速度/lifetime
    // 这是粒子系统的典型 hot loop

    constexpr int ITERATIONS = 10;

    // AoS: 每次迭代加载整个 32 字节的 ParticleAoS，但只用其中 12 字节
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int iter = 0; iter < ITERATIONS; ++iter) {
            for (size_t i = 0; i < N; ++i) {
                aos[i].x += aos[i].vx * 0.016f;
                aos[i].y += aos[i].vy * 0.016f;
                aos[i].z += aos[i].vz * 0.016f;
            }
        }
        auto end = std::chrono::high_resolution_clock::now();
        double elapsed = std::chrono::duration<double, std::milli>(end - start).count();
        std::cout << "  AoS (更新位置): " << elapsed << " ms\n";
        std::cout << "    → 每次读 32B, 用 12B(xyz) + 12B(vx,vy,vz), 浪费 8B\n";
        std::cout << "    → 每元素触发的缓存行数: 1 (32B < 64B)\n";
    }

    // SoA: 只加载需要的三个数组 (x, y, z 和 vx, vy, vz)
    {
        auto start = std::chrono::high_resolution_clock::now();
        for (int iter = 0; iter < ITERATIONS; ++iter) {
            for (size_t i = 0; i < N; ++i) {
                soa.x[i] += soa.vx[i] * 0.016f;
                soa.y[i] += soa.vy[i] * 0.016f;
                soa.z[i] += soa.vz[i] * 0.016f;
            }
        }
        auto end = std::chrono::high_resolution_clock::now();
        double elapsed = std::chrono::duration<double, std::milli>(end - start).count();
        std::cout << "  SoA (更新位置): " << elapsed << " ms\n";
        std::cout << "    → 从 6 个独立连续数组读取, 每缓存行 16 个 float\n";
        std::cout << "    → 缓存利用率 100%\n";
    }
}

// ============================================================
// 3. 顶点量化演示
// ============================================================

// 量化工具函数
inline uint16_t quantize_position(float world_x, float world_min, float world_max) {
    float range = world_max - world_min;
    float normalized = (world_x - world_min) / range;
    return static_cast<uint16_t>(normalized * 65535.0f + 0.5f);
}

inline float dequantize_position(uint16_t q, float world_min, float world_max) {
    float range = world_max - world_min;
    return world_min + (static_cast<float>(q) / 65535.0f) * range;
}

inline int8_t quantize_normal(float component) {
    // 法线分量范围 [-1, +1] → snorm8 [-127, 127]
    return static_cast<int8_t>(std::clamp(component * 127.0f, -127.0f, 127.0f));
}

inline float dequantize_normal(int8_t q) {
    return static_cast<float>(q) / 127.0f;
}

#include <cstdint>
struct half {
    uint16_t bits;
    half() : bits(0) {}
    explicit half(float f) {
        uint32_t fi;
        std::memcpy(&fi, &f, sizeof(fi));
        uint32_t sign = (fi >> 16) & 0x8000;
        int32_t exp   = static_cast<int32_t>((fi >> 23) & 0xFF) - 127 + 15;
        uint32_t mant = (fi >> 13) & 0x3FF;

        if (exp <= 0)       { exp = 0; mant = 0; }       // 下溢 → 0
        else if (exp >= 31) { exp = 31; mant = 0; }      // 上溢 → Inf
        bits = static_cast<uint16_t>(sign | (exp << 10) | mant);
    }
    operator float() const {
        uint32_t sign = (bits & 0x8000) << 16;
        int32_t exp   = ((bits >> 10) & 0x1F) - 15 + 127;
        uint32_t mant = (bits & 0x3FF) << 13;
        uint32_t fi   = sign | (exp << 23) | mant;
        float f;
        std::memcpy(&f, &fi, sizeof(f));
        return f;
    }
};

struct VertexF32 {
    float pos[3];    // 12B
    float normal[3]; // 12B
    float uv[2];     // 8B
    // total: 32B
};

struct VertexCompressed {
    uint16_t pos[3];    // 6B  (quantized position)
    int8_t   normal[3]; // 3B + 1B padding
    uint8_t  _pad;
    half     uv[2];     // 4B  (half-float)
    // total: 14B (节省 56%)
};

void bench_vertex_compression() {
    std::cout << "\n=== 基准 3: 顶点压缩 — 带宽对比 ===\n\n";

    constexpr size_t VERTEX_COUNT = 10'000'000; // 10M 顶点
    constexpr float WORLD_MIN = 0.0f;
    constexpr float WORLD_MAX = 1024.0f;

    // 创建未压缩顶点数据
    std::vector<VertexF32> uncompressed(VERTEX_COUNT);
    for (size_t i = 0; i < VERTEX_COUNT; ++i) {
        float fx = static_cast<float>(i % 1000);
        uncompressed[i] = {
            {fx, fx + 1.0f, fx + 2.0f},
            {0.0f, 0.0f, 1.0f},
            {fx / 1000.0f, (fx + 1.0f) / 1000.0f}
        };
    }

    // 创建压缩顶点数据
    std::vector<VertexCompressed> compressed(VERTEX_COUNT);
    for (size_t i = 0; i < VERTEX_COUNT; ++i) {
        auto& src = uncompressed[i];
        compressed[i].pos[0] = quantize_position(src.pos[0], WORLD_MIN, WORLD_MAX);
        compressed[i].pos[1] = quantize_position(src.pos[1], WORLD_MIN, WORLD_MAX);
        compressed[i].pos[2] = quantize_position(src.pos[2], WORLD_MIN, WORLD_MAX);
        compressed[i].normal[0] = quantize_normal(src.normal[0]);
        compressed[i].normal[1] = quantize_normal(src.normal[1]);
        compressed[i].normal[2] = quantize_normal(src.normal[2]);
        compressed[i].uv[0] = half(src.uv[0]);
        compressed[i].uv[1] = half(src.uv[1]);
    }

    // 测试 1: 遍历访问（模拟 VS 输入）
    {
        std::cout << "  顶点遍历 (模拟 VS 输入阶段):\n";

        // F32
        {
            auto start = std::chrono::high_resolution_clock::now();
            float sum = 0;
            for (size_t i = 0; i < VERTEX_COUNT; ++i) {
                sum += uncompressed[i].pos[0] + uncompressed[i].pos[1] + uncompressed[i].pos[2];
            }
            auto end = std::chrono::high_resolution_clock::now();
            double elapsed = std::chrono::duration<double, std::milli>(end - start).count();
            volatile float s = sum; (void)s;
            std::cout << "    F32 (32B/vtx, " << (VERTEX_COUNT * 32) / (1024*1024) << " MB): "
                      << elapsed << " ms\n";
        }

        // Compressed
        {
            auto start = std::chrono::high_resolution_clock::now();
            float sum = 0;
            for (size_t i = 0; i < VERTEX_COUNT; ++i) {
                sum += dequantize_position(compressed[i].pos[0], WORLD_MIN, WORLD_MAX)
                     + dequantize_position(compressed[i].pos[1], WORLD_MIN, WORLD_MAX)
                     + dequantize_position(compressed[i].pos[2], WORLD_MIN, WORLD_MAX);
            }
            auto end = std::chrono::high_resolution_clock::now();
            double elapsed = std::chrono::duration<double, std::milli>(end - start).count();
            volatile float s = sum; (void)s;
            std::cout << "    压缩 (14B/vtx, " << (VERTEX_COUNT * 14) / (1024*1024) << " MB): "
                      << elapsed << " ms\n";
        }

        // 压缩的 CPU 端需解量化，但 GPU 端解包几乎没有额外开销
        std::cout << "    注意: 压缩版含 CPU 解量化开销; GPU 端解包开销几乎为零(硬件支持)\n";
    }

    // 测试 2: 纯内存拷贝（模拟 DMA 传输）
    {
        std::cout << "\n  内存拷贝 (模拟 GPU 上传):\n";

        // F32
        {
            std::vector<VertexF32> dst(VERTEX_COUNT);
            auto start = std::chrono::high_resolution_clock::now();
            std::memcpy(dst.data(), uncompressed.data(), VERTEX_COUNT * sizeof(VertexF32));
            auto end = std::chrono::high_resolution_clock::now();
            double elapsed = std::chrono::duration<double, std::milli>(end - start).count();
            double bandwidth = (VERTEX_COUNT * sizeof(VertexF32)) / (elapsed / 1000.0) / (1024*1024*1024);
            std::cout << "    F32  拷贝 " << (VERTEX_COUNT * 32) / (1024*1024) << " MB: "
                      << elapsed << " ms (" << bandwidth << " GB/s)\n";
        }

        // Compressed
        {
            std::vector<VertexCompressed> dst(VERTEX_COUNT);
            auto start = std::chrono::high_resolution_clock::now();
            std::memcpy(dst.data(), compressed.data(), VERTEX_COUNT * sizeof(VertexCompressed));
            auto end = std::chrono::high_resolution_clock::now();
            double elapsed = std::chrono::duration<double, std::milli>(end - start).count();
            double bandwidth = (VERTEX_COUNT * sizeof(VertexCompressed)) / (elapsed / 1000.0) / (1024*1024*1024);
            std::cout << "    压缩 拷贝 " << (VERTEX_COUNT * 14) / (1024*1024) << " MB: "
                      << elapsed << " ms (" << bandwidth << " GB/s)\n";
        }

        std::cout << "    节省: " << (320 - 140) << " MB 每次上传 ("
                  << (1.0 - 14.0/32.0) * 100 << "%)\n";
    }
}

// ============================================================
// 4. 量化精度验证
// ============================================================
void demo_quantization_precision() {
    std::cout << "\n=== 量化精度分析 ===\n\n";

    constexpr float WORLD_SIZE = 1024.0f;

    // 位置量化精度
    float pos_step = WORLD_SIZE / 65535.0f;
    std::cout << "  世界范围: 0 - " << WORLD_SIZE << " m\n";
    std::cout << "  位置量化步长 (uint16): " << pos_step * 1000.0f << " mm\n";
    std::cout << "  对大多数游戏物体定位足够（< 2cm 误差）\n";

    // 法线量化精度
    float normal_step = 1.0f / 127.0f;
    std::cout << "\n  法线量化步长 (snorm8): " << normal_step << " (~" << normal_step * 100.0f << "%)\n";
    std::cout << "  与原始法线的最大角度偏差: ~0.45°\n";

    // half-float 精度
    std::cout << "\n  half-float (FP16):\n";
    std::cout << "    有效精度: ~3.3 位十进制\n";
    std::cout << "    范围: ±65504\n";
    std::cout << "    对 UV 坐标 (0-1), 步长 = 1/1024 ≈ 0.001\n";
    std::cout << "    对 2048×2048 纹理, 1 像素 ≈ UV 步长 0.0005, 精度足够\n";

    // 演示量化往返误差
    std::cout << "\n  往返误差演示:\n";
    float test_vals[] = {0.0f, 0.5f, 511.3f, 1023.999f, 512.777f};
    for (float original : test_vals) {
        uint16_t q  = quantize_position(original, 0.0f, WORLD_SIZE);
        float restored = dequantize_position(q, 0.0f, WORLD_SIZE);
        float error = std::abs(original - restored);
        std::cout << "    " << original << " → quantize → " << restored
                  << " (误差 " << error * 1000.0f << " mm)\n";
    }
}

int main() {
    std::cout << "========== 内存带宽与数据压缩基准测试 ==========\n";

    bench_stride_access();
    bench_aos_vs_soa();
    bench_vertex_compression();
    demo_quantization_precision();

    std::cout << "\n========== 完成 ==========\n";
    return 0;
}
```

### 预期输出

```
========== 内存带宽与数据压缩基准测试 ==========

=== 基准 1: 步长遍历 — 内存带宽墙 ===

    步长     字节/跳      时间(ms)     带宽(MB/s)    ns/元素
----------------------------------------------------------
       1          12        7.82       2389.5        0.71  ← L1/L2 友好
       2          24        8.01       1166.4        1.45
       4          48        9.45        494.3        3.43
       8          96       12.34        189.2        8.96  ← L2 边界
      16         192       18.67         62.5       27.12
      32         384       35.12         16.6      102.01
      64         768       63.40          4.6      368.31  ← L3 边界
     128        1536       71.23          2.0      827.43
     256        3072       72.91          1.0     1693.02
     512        6144       73.45          0.5     3407.14  ← DRAM 墙

分析:
  步长=1:   一个缓存行(64B)容纳 16 个连续 Vec3? 实际是 64/12≈5.3 个
           每缓存行有效数据约 5×4=20 字节 → 利用率 31%
           如用 SoA(float x[N])，则步长=1 时每缓存行 16 个 float
           利用率 100%，带宽效率提升 3 倍+

=== 基准 2: AoS vs SoA 数据布局 ===

  AoS (更新位置): 124.5 ms
    → 每次读 32B, 用 12B(xyz) + 12B(vx,vy,vz), 浪费 8B
    → 每元素触发的缓存行数: 1 (32B < 64B)
  SoA (更新位置): 68.3 ms
    → 从 6 个独立连续数组读取, 每缓存行 16 个 float
    → 缓存利用率 100%

=== 基准 3: 顶点压缩 — 带宽对比 ===

  顶点遍历 (模拟 VS 输入阶段):
    F32 (32B/vtx, 305 MB): 45.12 ms
    压缩 (14B/vtx, 133 MB): 22.87 ms
    注意: 压缩版含 CPU 解量化开销; GPU 端解包开销几乎为零(硬件支持)

  内存拷贝 (模拟 GPU 上传):
    F32  拷贝 305 MB: 24.50 ms (12.4 GB/s)
    压缩 拷贝 133 MB: 10.71 ms (12.4 GB/s)
    节省: 172 MB 每次上传 (56.25%)

=== 量化精度分析 ===

  世界范围: 0 - 1024 m
  位置量化步长 (uint16): 15.626 mm
  对大多数游戏物体定位足够（< 2cm 误差）

  法线量化步长 (snorm8): 0.00787402 (~0.79%)
  与原始法线的最大角度偏差: ~0.45°

  half-float (FP16):
    有效精度: ~3.3 位十进制
    范围: ±65504
    对 UV 坐标 (0-1), 步长 = 1/1024 ≈ 0.001
    对 2048x2048 纹理, 1 像素 ≈ UV 步长 0.0005, 精度足够

  往返误差演示:
    0 → quantize → 0 (误差 0 mm)
    0.5 → quantize → 0.5 (误差 0.01 mm)
    511.3 → quantize → 511.28 (误差 1.56 mm)
    1024 → quantize → 1024 (误差 0 mm)
    512.777 → quantize → 512.78 (误差 1.09 mm)
```

---
## 3. 练习

### 练习 1: 实现 SoA 粒子系统

用 SoA 布局实现一个完整的粒子系统：
- 支持发射、更新（位置+速度）、销毁（lifetime 归零时）。
- 对比 AoS 和 SoA 版本在"只更新位置"、"更新位置+速度"、"更新全部字段"三种场景下的性能。
- 记录每次迭代的 `std::chrono` 耗时，绘制"活跃粒子数 vs 每帧耗时"曲线。

### 练习 2: 索引缓冲优化

给定一个 Plane 网格（如 512×512 顶点）：
- 生成 16-bit 索引缓冲（512×512 < 65536，可行）。
- 对比 16-bit 和 32-bit 索引的网格在虚拟渲染循环中的内存带宽消耗。
- 实现 Forsyth 的顶点缓存优化算法（或使用现成的 `meshoptimizer` 库）对索引重排，测量顶点着色器重复计算率的变化。
- 工具推荐: https://github.com/zeux/meshoptimizer

### 练习 3: GPU 带宽分析（挑战）

使用 NVIDIA Nsight Graphics 或 AMD Radeon GPU Profiler：
- 加载一个 3D 场景，分析显存带宽利用率。
- 对比使用 BC7 压缩纹理 vs 未压缩 RGBA8 纹理时的带宽变化。
- 对比 float32×3 顶点格式 vs half×3 + snorm8 法线时的顶点着色器输入带宽。
- 如果你的 GPU 不支持这些工具，使用 CPU 端的 micro-benchmark 估算：模拟不同数据量的 DMA 传输（`glBufferData`/`vkCmdUpdateBuffer`）并测量帧时间。

---
## 4. 扩展阅读

- **"What Every Programmer Should Know About Memory" (Ulrich Drepper)** — 内存子系统经典文献，涵盖 DRAM、缓存层级、预取器。
- **meshoptimizer (Arseny Kapoulkine)**: https://github.com/zeux/meshoptimizer — 业界标准的网格优化库，含顶点缓存优化、索引压缩、meshlet 生成。
- **"Data-Oriented Design" (Richard Fabian)** — 深入 AoS vs SoA 在实际游戏系统中的选择。
- **NVIDIA — "Life of a Triangle"**: https://developer.nvidia.com/content/life-triangle-nvidias-logical-pipeline — 理解顶点数据从内存到屏幕的全路径。
- **ASTC Texture Compression (ARM)** — 移动端纹理压缩的事实标准，详细规格和评估指南。
- **"Mesh Shaders" (NVIDIA Turing+)** — 新一代几何管线，meshlet 压缩可减少传统顶点管线的带宽浪费。
- **Intel VTune Cookbook** — Memory Access 分析的实操指南: https://www.intel.com/content/www/us/en/docs/vtune-profiler/cookbook/

---
## 常见陷阱

1. **过度压缩**: 不是所有数据都适合压缩。物理碰撞需要精确的位置（量化误差可能导致穿模），动画骨骼变换需要高精度角度。评估精度损失对视觉/游戏性的实际影响。
2. **SoA 不总是更快**: 如果你总是同时访问所有字段（如粒子系统的每帧全量更新），AoS 的局部性反而更好——一次 cache miss 拉入所有字段。SoA 在"只访问部分字段"时才是赢家。
3. **GPU 压缩格式限制**: 不是所有纹理都能用 BC/ASTC 压缩——法线贴图推荐 BC5（双通道），HDR 纹理需 BC6H，UI 纹理可能需要无压缩（避免压缩伪影）。选错格式会导致视觉质量灾难。
4. **压缩纹理增加加载时间**: 虽然运行时带宽节省，但 BC/ASTC 纹理首次创建时的压缩编码可能很慢（离线预处理可规避此问题）。
5. **忘记对齐**: 压缩顶点格式可能引入未对齐访问。`uint16_t` 数组需要 2 字节对齐，`half` 也是。如果 GPU 要求 4 字节对齐的顶点 stride，压缩顶点可能需要显式 padding。
6. **缓存行伪共享**: 多线程访问同一缓存行中的不同字段时，即使没有数据竞争，也会因缓存一致性协议导致性能下降。SoA 可以有效避免伪共享（每个线程处理不同数组）。
