# C++23 特性引擎实战

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 24-C++20特性引擎实战

---

## 1. 概念讲解

### 1.1 `std::expected<T, E>`——值或错误的标准化表达

`std::expected` 是 C++23 引入的"要么有值，要么有错误"类型。它在游戏引擎中**终结了 Result 类型的碎片化**——每个引擎都造过自己的 `Result<T>` 或 `Outcome<T>`，现在标准库统一了。

```cpp
#include <expected>
#include <string>

// 引擎：资产加载的函数签名——失败是正常业务流程
std::expected<TextureHandle, std::string> load_texture(std::string_view path) {
    if (path.empty())
        return std::unexpected("empty path");

    if (!file_exists(path))
        return std::unexpected("file not found: " + std::string(path));

    // 成功路径
    return gpu_upload_texture(path);
}

// 使用
auto result = load_texture("hero_diffuse.dds");
if (result) {
    bind_texture(*result, 0);     // 有值
} else {
    log_error(result.error());    // 有错误
}

// 带默认值
auto tex = load_texture("optional_glow.dds").value_or(fallback_white);
```

**`expected<T, E>` vs 其他错误处理策略**：

| 策略 | 优点 | 缺点 | 引擎适用性 |
|------|------|------|----------|
| 异常 | 自动传播，语法简洁 | 不可预测的开销，禁用的引擎很多 | 仅在非性能关键路径 |
| 返回码 + 输出参数 | 零开销 | 丢失类型信息，调用方容易忽略 | 仅最简单的场景 |
| `std::optional<T>` | 表达"有/无" | 无错误详情 | 查找类操作 |
| `std::expected<T, E>` | 类型安全，强制检查 | 每层都要显式处理（无自动冒泡） | **最佳通用方案** |
| `std::variant<T, Error>` | 灵活 | 无单子操作，语法繁琐 | 需要更多错误类型的场景 |

### 1.2 单子操作（Monadic Operations）——链式错误处理

`expected` 最强大的特性是**单子操作**——允许将多个可能失败的操作链接起来，错误自动传播，无需层层 if-else。

```cpp
#include <expected>
#include <string>
#include <cstdint>
#include <vector>
#include <cstring>

// 资产加载管线的每一步都可能失败
struct RawData { std::vector<std::byte> bytes; };
struct ParsedHeader { uint32_t width, height, format; };
struct TextureData { ParsedHeader header; std::vector<std::byte> pixels; };

std::expected<RawData, std::string> read_file(std::string_view path);
std::expected<ParsedHeader, std::string> parse_header(const RawData& raw);
std::expected<TextureData, std::string> decode_pixels(const ParsedHeader& hdr, const RawData& raw);

// C++17 写法：层层 if-else
std::expected<TextureData, std::string> load_tex_old(std::string_view path) {
    auto raw = read_file(path);
    if (!raw) return std::unexpected(raw.error());

    auto hdr = parse_header(*raw);
    if (!hdr) return std::unexpected(hdr.error());

    return decode_pixels(*hdr, *raw);
}

// C++23 单子链式写法——错误自动传播
std::expected<TextureData, std::string> load_tex_new(std::string_view path) {
    return read_file(path)
        .and_then([](const RawData& raw) {
            return parse_header(raw)
                .and_then([&raw](const ParsedHeader& hdr) {
                    return decode_pixels(hdr, raw);
                });
        });
}

// 或更自然的写法：每个 .and_then 只在成功时调用
auto load_chain = read_file(path)
    .and_then(parse_header)       // 注意：parse_header 返回 expected
    .transform([](const auto& hdr) { return hdr.format; }) // 映射值
    .or_else([](const std::string& err) {
        log_error(err);
        return std::expected<ParsedHeader, std::string>{default_header};
    });
```

**四个核心单子操作**：

| 操作 | 签名 | 语义 |
|------|------|------|
| `and_then(f)` | `(T) -> expected<U, E>` | 有值时调用 f，无值时传播错误 |
| `or_else(f)` | `(E) -> expected<T, G>` | 无值时调用 f（错误恢复/转换） |
| `transform(f)` | `(T) -> U` | 有值时映射 T→U，包装回 expected |
| `transform_error(f)` | `(E) -> G` | 无值时映射 E→G（丰富错误信息） |

**引擎中的典型链**：

```cpp
// 关卡加载管线
auto level = load_config(path)                     // expected<Config, Error>
    .and_then(validate_config)                      // expected<Config, Error>
    .and_then([](auto& cfg) { return load_terrain(cfg); })    // expected<Terrain, Error>
    .and_then([](auto& t)  { return load_entities(t); })     // expected<Entities, Error>
    .transform([](auto& e) { return build_world(e); })       // World（总是成功）
    .or_else([](const Error& e) {
        show_error_dialog(e.message);
        return std::expected<World, Error>{empty_world};     // 回退到空世界
    });
```

### 1.3 `std::mdspan`——多维数据视图

`mdspan` 是 `span` 的多维泛化——一个 N 维数组的零开销视图。引擎中最常见的用途：2D 图像、3D 体素、高度图。

```cpp
#include <mdspan> // C++23 <mdspan>, 之前可用参考实现

// 1D span：float buffer[1024]
// 2D mdspan：灰度图像 512 x 512
// 3D mdspan：体素数据 128 x 128 x 128

// 引擎示例：高度图地形采样
float heightmap_data[1024 * 1024]; // 1MB 的扁平数组

// 用 mdspan 将其视为 2D 数组
std::mdspan terrain(heightmap_data, 1024, 1024);

// 现在可以自然访问：
float h00 = terrain[0, 0];       // 左下角
float h511 = terrain[511, 511];  // 某个采样点

// 双线性插值采样（地形高度查询）
float sample_terrain(std::mdspan<const float, std::dextents<size_t, 2>> terrain,
                     float u, float v) {
    float ui = u * (terrain.extent(0) - 1);
    float vi = v * (terrain.extent(1) - 1);
    size_t x0 = static_cast<size_t>(ui);
    size_t y0 = static_cast<size_t>(vi);
    size_t x1 = std::min(x0 + 1, terrain.extent(0) - 1);
    size_t y1 = std::min(y0 + 1, terrain.extent(1) - 1);
    float fx = ui - x0;
    float fy = vi - y0;

    float h00 = terrain[x0, y0];
    float h10 = terrain[x1, y0];
    float h01 = terrain[x0, y1];
    float h11 = terrain[x1, y1];

    return (h00 * (1-fx) + h10 * fx) * (1-fy) +
           (h01 * (1-fx) + h11 * fx) * fy;
}
```

**`mdspan` 布局策略**：

```cpp
// 默认：行主序（row-major）——C/C++ 原生布局
std::mdspan<float, std::dextents<size_t, 2>> row_major(data, rows, cols);

// 列主序（column-major）—— Fortran/MATLAB/某些图形 API
std::mdspan<float, std::dextents<size_t, 2>,
            std::layout_left> col_major(data, rows, cols);

// 自定义步长（stride）—— 子矩阵视图
// 例如：从大纹理中提取一个矩形子区域
```

**引擎使用场景**：

| 场景 | extents 维度 | 数据 |
|------|-------------|------|
| 2D 纹理 / 精灵表 | 2 | `uint8_t[width * height * 4]` |
| 高度图 / 地形 | 2 | `float[width * height]` |
| 3D 体素 | 3 | `uint8_t[x * y * z]` |
| 动画骨骼矩阵 | 2 | `Matrix4[num_frames][num_bones]` |
| 卷积核 / 滤波器 | 2 | `float[kernel_w][kernel_h]` |

### 1.4 Deducing `this`——显式对象参数

C++23 允许成员函数的第一个参数是显式的 `this`（`this Self&& self`），替代隐式 `*this`。这解决了 C++ 中 **const 和非 const 方法代码重复** 的老大难问题。

```cpp
// C++20：两个几乎相同的方法
template<typename T>
class OptionalRef {
    T* ptr_;

public:
    // 非 const 版本
    T& value() & {
        if (!ptr_) throw std::runtime_error("empty");
        return *ptr_;
    }

    // const 版本——99% 相同的代码！
    const T& value() const& {
        if (!ptr_) throw std::runtime_error("empty");
        return *ptr_;
    }

    // 右值版本（又一个！）
    T&& value() && { return std::move(value()); }
};

// C++23 deducing this：一个方法覆盖所有情况
template<typename T>
class OptionalRef {
    T* ptr_;

public:
    template<typename Self>
    auto value(this Self&& self) -> decltype(auto) {
        if (!self.ptr_) throw std::runtime_error("empty");
        return *self.ptr_;
        // self 的类型自动推导：OptionalRef& / const OptionalRef& / OptionalRef&&
    }
};
```

**CRTP 简化**：传统 CRTP 需要 `static_cast<Derived&>(*this)`，deducing this 直接推导。

```cpp
// C++20 CRTP——繁琐
template<typename Derived>
struct Addable {
    Derived operator+(const Derived& other) const {
        return Derived(static_cast<const Derived&>(*this)) += other;
    }
};

// C++23 deducing this——干净
struct Addable {
    template<typename Self>
    auto operator+(this const Self& self, const Self& other) -> Self {
        auto result = self;
        result += other;
        return result;
    }
};
```

### 1.5 `std::flat_map` / `std::flat_set`——缓存友好的关联容器

传统 `std::map`（红黑树）节点散布在堆上，每次查找有 O(log N) 次指针追踪，缓存局部性极差。`std::flat_map` 使用 **有序 vector** 存储键值对——二分查找，缓存友好。

```cpp
#include <flat_map>  // C++23

// 引擎场景：静态配置表、材质属性表、LOD 距离表
// 这些表在加载后不再修改——完美适配 flat_map
std::flat_map<std::string, MaterialProperties> material_table = {
    {"concrete",  {0.6f, 1.0f, 0.1f}},
    {"metal",     {0.2f, 0.3f, 0.9f}},
    {"wood",      {0.8f, 0.5f, 0.2f}},
    {"glass",     {0.1f, 0.1f, 0.9f}},
};
// flat_map 自动维护有序排列（一次排序，之后查找均为二分）

// 查找性能对比（1000 个条目）：
// std::map:    ~50-100ns（指针追踪，cache miss 多）
// flat_map:    ~10-30ns（二分查找，线性扫描缓存友好）
```

**`flat_map` 的取舍**：

| 特性 | `std::map` | `std::flat_map` |
|------|-----------|----------------|
| 查找 | O(log N)，跟随指针 | O(log N)，连续二分 |
| 插入/删除 | O(log N)，单节点 | O(N)，可能需要移动所有后续元素 |
| 内存开销 | 每节点 3 指针（~24 bytes） | 几乎零开销（纯数组） |
| 遍历 | 指针跳跃 | 线性扫描——极快 |
| 适用场景 | 频繁插入/删除 | **构建一次、查询多次**（引擎最常见） |

### 1.6 `std::print` / `std::println`——类型安全的 I/O

```cpp
#include <print>

// 替代 std::cout 和 printf——兼具类型安全和格式控制
std::println("Frame {}: delta={:.3f}ms, draws={}, tris={}",
             frame_count, delta_ms, draw_calls, triangles);

// vs std::cout（C++17 方式）：
// std::cout << "Frame " << frame_count << ": delta="
//           << std::fixed << std::setprecision(3) << delta_ms
//           << "ms, draws=" << draw_calls << ", tris=" << triangles << '\n';
// 哪个更清晰？
```

### 1.7 `std::stacktrace`——程序化调用栈

```cpp
#include <stacktrace>
#include <iostream>

// 崩溃处理器——记录完整的调用栈
void crash_handler() {
    auto trace = std::stacktrace::current();
    std::println(stderr, "=== CRASH ===");
    std::println(stderr, "{}", trace);
    // 输出：
    //  0# crash_handler() at crash.cpp:15
    //  1# physics_update(float) at physics.cpp:342
    //  2# game_loop() at main.cpp:89
    //  3# main at main.cpp:127
}

// 性能剖面的辅助信息
void expensive_operation() {
    auto entry = std::stacktrace::current();
    // 将调用栈附加到 profiler 的采样点
    profiler.record_sample("expensive", entry);
}
```

**重要**：`stacktrace` 在 Release 构建中可能无法展开符号（需要调试符号）。引擎中通常在 Debug/RelWithDebInfo 构建中使用，Release 中只记录原始地址。

### 1.8 `std::generator<T>`——协程生成器

第一个进入 C++ 标准的协程类型。惰性地逐个生成值，调用方按需拉取。

```cpp
#include <generator>  // C++23

// 生成 LOD 级别序列——惰性求值
std::generator<float> lod_distances(float max_distance, float factor) {
    float d = 0.0f;
    while (d < max_distance) {
        d = d == 0.0f ? 10.0f : d * factor;
        co_yield d;  // 产生一个值并暂停
    }
}

// 使用：自动在迭代器中暂停/恢复
for (float lod_d : lod_distances(1000.0f, 1.8f)) {
    // lod_d: 10.0, 18.0, 32.4, 58.3, 104.9, ...
    setup_lod_level(lod_d);
}

// 另一个场景：遍历资产目录
std::generator<std::string> scan_assets(const std::string& root) {
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root)) {
        if (entry.is_regular_file()) {
            co_yield entry.path().string();
        }
    }
}
```

### 1.9 `[[assume(expr)]]`——编译器优化提示

告诉编译器"这个条件永远为真"——编译器据此优化掉死路径、消除空指针检查。

```cpp
void process_vertices(std::span<const float> vertices) {
    // 保证顶点数是 3 的倍数（三角形）
    [[assume(vertices.size() % 3 == 0)]];
    // 编译器可以：优化掉循环中 % 3 边界检查；展开为 3-元素 SIMD 操作

    for (size_t i = 0; i < vertices.size(); i += 3) {
        // 编译器知道 i+2 不越界 → 消除边界检查 → 生成更紧凑的代码
        float x = vertices[i];
        float y = vertices[i + 1];
        float z = vertices[i + 2];
        transform_vertex(x, y, z);
    }
}

void safe_divide(float* result, float a, float b) {
    [[assume(b != 0.0f)]];  // 告诉编译器分母非零
    *result = a / b;         // 编译器可以消除 NaN 检查路径
}
```

**⚠️ 警告**：如果 `assume` 的条件在运行时为 false，行为是**未定义的**——比 assert 更危险（assert 失败是可观察的行为）。只在性能关键的、你已经通过其他方式确保的条件上使用。

---

## 2. 代码示例

### 2.1 `expected` 资产加载管线（单子链）

```cpp
#include <expected>
#include <string>
#include <vector>
#include <cstdint>
#include <format>
#include <print>

// 错误类型
struct AssetError {
    std::string message;
    std::string path;
    int line = 0;
};

// 管线每一步
std::expected<std::vector<uint8_t>, AssetError> read_file(std::string_view path) {
    // 模拟文件读取
    if (path.empty()) return std::unexpected(AssetError{"empty path", std::string(path), __LINE__});
    if (path == "corrupt") return std::unexpected(AssetError{"corrupt file", std::string(path), __LINE__});
    return std::vector<uint8_t>(1024, 0xAB); // 模拟数据
}

std::expected<uint32_t, AssetError> parse_magic(const std::vector<uint8_t>& data) {
    if (data.size() < 4)
        return std::unexpected(AssetError{"file too small", "", __LINE__});
    if (data[0] != 0xAB)
        return std::unexpected(AssetError{"bad magic number", "", __LINE__});
    return 42; // 模拟成功的 magic
}

std::expected<std::string, AssetError> load_asset_string(std::string_view path) {
    // 使用 transform_error 丰富错误信息
    return read_file(path)
        .transform_error([path](AssetError e) {
            e.path = path;
            return e;
        })
        .and_then(parse_magic)
        .transform([](uint32_t magic) {
            return std::format("Asset(magic={})", magic);
        });
}

// 使用
void demo_asset_loading() {
    auto result = load_asset_string("hero.dds");
    if (result) {
        std::println("Loaded: {}", *result);
    } else {
        std::println("Failed: {} (path={}, line={})",
                     result.error().message, result.error().path, result.error().line);
    }
}
```

### 2.2 `mdspan` 图像卷积

```cpp
#include <mdspan>
#include <vector>
#include <algorithm>

// 3x3 卷积核（边缘检测 Sobel）
constexpr float SOBEL_KERNEL[3][3] = {
    {-1, 0, 1},
    {-2, 0, 2},
    {-1, 0, 1}
};

// 对灰度图应用卷积
std::vector<float> apply_convolution(
    std::mdspan<const float, std::dextents<size_t, 2>> input)
{
    size_t h = input.extent(0);
    size_t w = input.extent(1);
    std::vector<float> output(h * w);
    auto output_2d = std::mdspan(output.data(), h, w);

    for (size_t y = 1; y < h - 1; ++y) {
        for (size_t x = 1; x < w - 1; ++x) {
            float sum = 0.0f;
            for (int ky = -1; ky <= 1; ++ky)
                for (int kx = -1; kx <= 1; ++kx)
                    sum += input[y + ky, x + kx] * SOBEL_KERNEL[ky + 1][kx + 1];
            output_2d[y, x] = sum;
        }
    }
    return output;
}

// 使用：
// float img[512*512] = { /* ... */ };
// std::mdspan img_view(img, 512, 512);
// auto edges = apply_convolution(img_view);
```

### 2.3 Deduplicating `this`：CRTP 简化

```cpp
#include <cstddef>

// C++23: deducing this 实现 CRTP 的克隆模式
struct Cloneable {
    template<typename Self>
    auto clone(this const Self& self) -> Self {
        // Self 自动推导为 MyWidget / MyWindow 等
        return self; // 调用派生类的拷贝构造
    }
};

struct MyWidget : Cloneable {
    int id;
    const char* name;
    // 不需要任何额外代码——clone() 自动可用
};

// 对比 C++20 CRTP：
/*
template<typename Derived>
struct CloneableCRTP {
    Derived clone() const {
        return static_cast<const Derived&>(*this);
    }
};
struct MyWidgetOld : CloneableCRTP<MyWidgetOld> { ... };
*/

void demo_deducing_this() {
    MyWidget w{1, "button"};
    auto w2 = w.clone();        // w2 是 MyWidget
    const MyWidget cw{2, "label"};
    // auto cw2 = cw.clone();   // cw2 也是 MyWidget（const 被正确处理）
}
```

### 2.4 `flat_map` 静态属性查找

```cpp
#include <flat_map>
#include <string>
#include <print>

// 物理材质属性表——编译后不再修改
struct PhysMaterial {
    float restitution;   // 弹性系数
    float friction;      // 摩擦系数
    float density;       // 密度
};

const std::flat_map<std::string, PhysMaterial> PHYSICS_MATERIALS = {
    {"steel",    {0.3f, 0.5f, 7.8f}},
    {"rubber",   {0.9f, 1.2f, 1.2f}},
    {"ice",      {0.1f, 0.05f, 0.9f}},
    {"concrete", {0.1f, 0.8f, 2.4f}},
    {"wood",     {0.3f, 0.6f, 0.7f}},
};

PhysMaterial lookup_material(std::string_view name) {
    // flat_map 尚不支持异构查找（C++23 flat_map），所以需要临时 string
    auto it = PHYSICS_MATERIALS.find(std::string(name));
    if (it != PHYSICS_MATERIALS.end())
        return it->second;
    return PhysMaterial{0.5f, 0.5f, 1.0f}; // 默认
}

void demo_flat_map() {
    auto mat = lookup_material("rubber");
    std::println("Rubber: bounciness={}, friction={}, density={}",
                 mat.restitution, mat.friction, mat.density);
}
```

### 2.5 `stacktrace` 崩溃处理器

```cpp
#include <stacktrace>
#include <csignal>
#include <print>

void install_crash_handler() {
    std::signal(SIGSEGV, [](int) {
        std::println(stderr, "\n========== ENGINE CRASH ==========");
        std::println(stderr, "Signal: SIGSEGV (Segmentation Fault)");
        std::println(stderr, "Stack trace:");
        std::println(stderr, "{}", std::stacktrace::current());
        std::println(stderr, "===================================");
        std::_Exit(1);
    });
}

// 在 main() 开始时调用：
// install_crash_handler();
```

---

## 3. 练习

### 练习 1（必做）：将 Result 类型迁移到 `std::expected`

假设项目中有如下常见的自定义错误处理：

```cpp
template<typename T, typename E>
struct Result {
    bool ok;
    union { T value; E error; };
    // ...
};
```

1. 找一个你现有的使用自定义 `Result` 的函数（或创建一个：文件读取 + JSON 解析 + 验证）。
2. 将所有返回 `Result<T, E>` 的地方改为 `std::expected<T, E>`。
3. 用 `.and_then()` / `.or_else()` 链式重写调用代码，消除层层 if-else。
4. 测量：链式写法 vs if-else 写法在 -O2 下的汇编输出是否相同（应该相同——单子操作是零开销抽象）。

### 练习 2（必做）：用 `mdspan` 实现图像滤波

1. 创建一个 256x256 的灰度测试图像（单精度浮点，值 0-1）。
2. 用 `std::mdspan` 将 `std::vector<float>` 包装为 2D 视图。
3. 实现 5x5 高斯模糊滤波器（卷积核）。
4. 实现边界处理（clamp / mirror / zero-padding）。
5. 分别用 `mdspan` 方式和裸指针 `(y * width + x)` 方式实现，比较性能差异（应相同）。
6. 扩展：用 `mdspan` 处理 RGBA 四通道图像（extent 维度从 2 变为 3，第三维是通道）。

### 练习 3（可选·挑战）：用 deducing this 统一 const 和非 const 迭代器

1. 设计一个自定义容器类（如 `FixedVector<T, N>` —— 栈上的固定容量 vector）。
2. 使用 C++23 deducing this 实现单一的 `operator[]` 和 `begin()`/`end()` 方法，同时覆盖 `&`、`const&`、`&&` 三种值类别。
3. 验证：`const FixedVector` 返回 `const T&`，非 const 返回 `T&`，右值返回 `T&&`。
4. 对比：如果用 C++17 方式需要多少个重载？deducing this 节省了多少代码？
5. Bonus：用 deducing this 实现一个 `view()` 方法，返回 `std::span<const T>` 而不是 `T&`——无论调用对象是什么值类别。

---

## 4. 扩展阅读

- **[必读]** *C++23 Standard (N4950)* — ISO C++23 最终草案
- **[推荐]** "std::expected — The Result Type We've Been Waiting For" — Sy Brand (CppCon 2022)，微软 STL 开发者的详细讲解
- **[推荐]** "mdspan: A Multi-dimensional Array View for C++" — Christian Trott, Mark Hoemmen (CppCon 2022)，Kokkos 团队的 mdspan 设计哲学
- **[推荐]** "Deducing this: C++23's Explicit Object Parameter" — Sy Brand (CppCon 2022)，CRTP 简化、lambda 递归、const/non-const 去重
- **[推荐]** "std::flat_map and std::flat_set" — Arthur O'Dwyer (CppCon 2022)，缓存友好容器的实现细节与取舍
- **[工具]** `mdspan` 参考实现（https://github.com/kokkos/mdspan）—— 官方 C++23 mdspan 的前身，可用在 C++17/20 项目

---

## 常见陷阱

### 陷阱 1：`expected` 的单子操作返回类型必须匹配

```cpp
// ❌ 编译错误：and_then 的回调必须返回 expected<U, E>，E 可转换即可
load_config("game.cfg")
    .and_then([](auto& cfg) {
        return cfg.version; // 返回 int，不是 expected<U, Error> → 编译错误！
    });

// ✅ 正确：用 .transform 映射值（不改变错误类型）
load_config("game.cfg")
    .transform([](auto& cfg) {
        return cfg.version; // transform 接受 T→U，返回 expected<U, E>
    });

// 规则：
// .and_then(f)   —— f 返回 expected<U, E>
// .transform(f)  —— f 返回 U（会被包装成 expected<U, E>）
// .or_else(f)    —— f 返回 expected<T, G>
// .transform_error(f) —— f 返回 G（会被包装成 expected<T, G>）
```

### 陷阱 2：`expected<void, E>` 的使用

```cpp
// ✅ C++23: expected<void, E> 用于"可能失败但成功时无值"的操作
std::expected<void, std::string> validate_config(const Config& cfg) {
    if (cfg.version < 2)
        return std::unexpected("config version too old");
    // 成功——不需要返回任何值
    return {};  // 或 return std::expected<void, std::string>{};
}

// 单子操作中，transform 的回调不接受参数
validate_config(cfg)
    .transform([] { std::println("validation passed"); })
    .or_else([](const std::string& e) {
        std::println("validation failed: {}", e);
        return std::expected<void, std::string>{}; // 必须返回 void expected
    });
```

### 陷阱 3：`deducing this` 中的 `decltype(auto)` 与值类别绑定

```cpp
// ❌ 陷阱：不正确的返回类型导致悬垂引用
template<typename Self>
auto get_value(this Self&& self) -> decltype(auto) {  // ⚠️
    return self.value_;  // Self 是右值时，返回右值引用——可能悬垂
}

// ✅ 正确：显式控制返回类型
template<typename Self>
auto get_value(this Self&& self) -> std::remove_reference_t<Self>::value_type& {
    return self.value_;
}
// 或使用 std::forward_like (C++23):
template<typename Self>
decltype(auto) get_value(this Self&& self) {
    return std::forward_like<Self>(self.value_);
}
```

### 陷阱 4：`flat_map` 插入成本被忽略

```cpp
// ❌ 陷阱：在高频插入场景中使用 flat_map
std::flat_map<int, Entity> entities;
void add_entity(Entity e) {
    entities[e.id] = e; // 每次插入 O(N)！移动所有元素
    // 如果每帧插入 1000 个实体 → 每帧 ~500 万次元素移动
}

// ✅ 解决方案 1：构建时批量插入
std::vector<std::pair<int, Entity>> to_add;
void queue_entity(Entity e) {
    to_add.push_back({e.id, e});
}
void flush_entities() {
    entities.insert(to_add.begin(), to_add.end()); // 一次性排序+合并
    to_add.clear();
}

// ✅ 解决方案 2：需要频繁插入就用 std::map 或 std::unordered_map
```

### 陷阱 5：`[[assume]]` 在调试构建中的危险

```cpp
// ❌ 危险：调试构建中 assume 的条件不成立
void resize_buffer(void* ptr, size_t new_size) {
    [[assume(new_size > 0 && new_size <= MAX_SIZE)]];
    // 如果一个 bug 传入 new_size=0，调试器中也无法捕获——
    // 编译器已经基于 assume 优化掉了检查分支
    *ptr = ...; // UB 静默发生
}

// ✅ 正确：assume 用于已经过验证的条件
void resize_buffer(void* ptr, size_t new_size) {
    assert(new_size > 0 && new_size <= MAX_SIZE); // Debug 中检查
    [[assume(new_size > 0 && new_size <= MAX_SIZE)]]; // Release 中优化
    // 双重保险
}
```
