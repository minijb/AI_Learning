# 17. constexpr 与编译期计算

> **所属计划**: C++ 游戏工程师详细攻略 — 阶段 4：模板与编译期抽象
> **预计耗时**: 4 小时
> **前置知识**: [13-模板基础与实例化模型](13-template-instantiation.md)、[16-Variadic Templates](16-variadic-templates.md)
> **C++ 标准**: C++11/14/17/20 (持续演进)

---

## 1. 概念讲解

### 1.1 constexpr 的演变：从单 return 到完整语言

`constexpr` 表示"该表达式**可以**在编译期求值"——如果出现在要求常量表达式的上下文中，编译器**必须**在编译期完成计算；否则**可能**回退到运行时。

| 标准 | 能力 | 新增 |
|------|------|------|
| C++11 | 单 `return` 语句的函数 | `constexpr` 变量、函数 |
| C++14 | 循环、局部变量、多个 return | `constexpr` 大幅扩展 |
| C++17 | `if constexpr`、`constexpr` lambda | 编译期分支、lambda |
| C++20 | `consteval`、`constinit`、`new`/`delete`、`std::string`、`std::vector` | 动态分配、强制编译期求值 |

### 1.2 constexpr 变量 vs constexpr 函数

```cpp
constexpr int compile_time_value = 42;         // 必须在编译期初始化
constexpr int runtime_value   = some_func();    // 如果 some_func 不是 constexpr，编译失败

constexpr int square(int x) { return x * x; }  // constexpr 函数

int arr[square(5)];          // ✅ 编译期求值：int arr[25]
int n = some_runtime_input();
int x = square(n);           // ✅ 运行时调用，合法但不做编译期求值
```

**游戏引擎中的关键区别**：标记为 `constexpr` 的函数在 Debug 构建中可能在运行时执行，而 `consteval` 函数强制编译期求值——避免 Debug 性能被编译期计算拖累的意外。

### 1.3 consteval（C++20）：强制编译期求值

`consteval` 声明的函数**必须**在编译期求值，不存在运行时版本：

```cpp
consteval int compile_only(int x) {
    return x * x;
}

int a = compile_only(5);     // ✅ 编译期执行
int n = 5;
int b = compile_only(n);     // ❌ 编译错误！n 不是常量表达式
```

**引擎应用**：资源路径验证——`consteval` 确保非法路径在编译期就被拒绝：

```cpp
consteval bool is_valid_asset_path(std::string_view path) {
    return path.starts_with("/assets/") && path.ends_with(".json");
}
```

### 1.4 constinit（C++20）：解决静态初始化顺序惨案

**静态初始化顺序惨案 (Static Initialization Order Fiasco)**：不同翻译单元中的全局对象初始化顺序未定义。如果 A 的构造函数依赖 B，但 B 尚未初始化 → 未定义行为。

```cpp
// ❌ 传统问题：
// file_a.cpp: LogSystem g_logger;          // 可能先于 g_audio 初始化
// file_b.cpp: AudioSystem g_audio(&g_logger); // 可能收到未初始化的 g_logger
```

`constinit` 强制变量在编译期初始化（零开销），但运行时仍可修改：

```cpp
constinit LogSystem* g_logger = nullptr;  // 编译期初始化为 null

void engine_init() {
    static LogSystem logger;   // 可控的初始化顺序
    g_logger = &logger;
    // 现在所有依赖 g_logger 的子系统都可以安全访问
}
```

**引擎传统方案 vs constinit**：

| 方案 | 描述 | 优劣 |
|------|------|------|
| 构造函数依赖 | 放任自由 | 不可靠 |
| `init()` 函数 | 手动调用 `InitAll()` 控制顺序 | 可靠但容易忘记调用 |
| Singleton 懒加载 | 函数内 `static` 变量 | C++11 起线程安全，但首次调用有锁开销 |
| `constinit` + 显式 `init()` | 编译期零初始化，运行时可控赋值 | **推荐** |

### 1.5 编译期计算即优化

游戏引擎的编译期优化核心思想：**把能提前算完的东西从每帧预算中挪走**。

| 优化目标 | 编译期替代方案 | 收益 |
|---------|--------------|------|
| 字符串→资源 ID 映射 | 编译期哈希 | 消除运行时字符串比较 |
| 数学常量表 (sin/cos) | 编译期生成 LUT | 省去预计算或文件加载 |
| CRC32/哈希校验 | 编译期计算 | 构建时验证资源完整性 |
| 类型信息/反射 | 编译期注册 | 零运行时反射开销 |
| 配置常量 | constexpr 变量 | 直接嵌入代码段 |

### 1.6 编译期字符串哈希（FNV-1a）

这是游戏引擎使用 constexpr 的**核心场景**：将人类可读的资源路径在编译期哈希为整数 ID，运行时只用整数比较。

```cpp
constexpr uint64_t hash_string(std::string_view sv) {
    uint64_t hash = 14695981039346656037ULL;
    for (char c : sv) {
        hash ^= static_cast<uint64_t>(c);
        hash *= 1099511628211ULL;
    }
    return hash;
}

// 使用 user-defined literal 简化
constexpr uint64_t operator""_h(const char* str, size_t len) {
    return hash_string({str, len});
}

// 运行时：整数 switch/case，不是字符串比较！
uint64_t id = "player_health"_h;
switch (id) {
    case "player_health"_h:  /* ... */ break;
    case "enemy_count"_h:    /* ... */ break;
}
```

### 1.7 编译期 Map（C++20）

C++20 允许在 constexpr 中使用 `new`/`delete` 和 `std::vector`，从而可以构建编译期数据结构：

```cpp
constexpr auto build_asset_table() {
    std::vector<std::pair<uint64_t, const char*>> table;
    table.push_back({"player_config"_h,  "/assets/config/player.json"});
    table.push_back({"level_01"_h,      "/assets/levels/level_01.bin"});
    // ...
    std::sort(table.begin(), table.end());  // constexpr sort!
    return table;
}
```

**限制**：编译期 `new` 分配的内存必须在常量求值结束前释放（不能泄漏到运行时）。

### 1.8 if constexpr（C++17）

编译期条件分支——不满足条件的分支**不被实例化**，从而可以写出对不同类型有不同行为的泛型代码：

```cpp
template<typename T>
void process_component(T& comp) {
    if constexpr (std::is_same_v<T, Transform>) {
        // 这段代码只在 T=Transform 时编译
        comp.x += 1.0f;
    } else if constexpr (std::is_same_v<T, Health>) {
        // 这段代码只在 T=Health 时编译
        comp.hp = std::min(comp.hp, comp.max_hp);
    } else {
        static_assert(sizeof(T) == 0, "Unknown component type");
    }
}
```

### 1.9 constexpr 的限制

即使在 C++20，constexpr 函数不能做的事：
- `reinterpret_cast` —— 绝对禁止
- 内联汇编 (`asm`)
- 调用非 constexpr 函数
- 静态/thread_local 变量声明（C++20 开始放宽了对局部 static 的限制）
- `goto`（C++20 之前）
- 未定义行为 —— constexpr 上下文中 UB 是**编译错误**

---

## 2. 代码示例

### 示例 1：编译期 FNV-1a 字符串哈希器 + 资源 ID 系统

```cpp
#include <string_view>
#include <cstdint>
#include <array>
#include <algorithm>
#include <iostream>
#include <optional>

// ============ 编译期 FNV-1a 哈希 ============
constexpr uint64_t hash_string(std::string_view sv, uint64_t seed = 14695981039346656037ULL) {
    uint64_t hash = seed;
    for (char c : sv) {
        hash ^= static_cast<uint64_t>(c);
        hash *= 1099511628211ULL;
    }
    return hash;
}

// 用户自定义字面量： "asset_name"_id → uint64_t
consteval uint64_t operator""_id(const char* str, size_t len) {
    return hash_string({str, len});
}

// ============ 编译期静态查找表 ============
struct AssetEntry {
    uint64_t      id;
    std::string_view path;
    int           type;  // 0=texture, 1=mesh, 2=sound

    constexpr bool operator<(const AssetEntry& o) const { return id < o.id; }
};

// 编译期构建并排序的 Asset 表
constexpr auto build_asset_manifest() {
    std::array<AssetEntry, 5> manifest = {{
        {"player"_id,     "/assets/characters/player.mesh", 1},
        {"enemy_01"_id,   "/assets/characters/enemy_01.mesh", 1},
        {"main_theme"_id, "/assets/audio/main_theme.ogg", 2},
        {"hud"_id,        "/assets/ui/hud.tex", 0},
        {"skybox"_id,     "/assets/environments/skybox.tex", 0},
    }};

    // 编译期排序（启用二分查找）
    std::sort(manifest.begin(), manifest.end());
    return manifest;
}

constexpr auto g_asset_manifest = build_asset_manifest();

// 运行时 O(log N) 查找
constexpr std::optional<AssetEntry> find_asset(uint64_t id) {
    auto it = std::lower_bound(g_asset_manifest.begin(), g_asset_manifest.end(),
                               AssetEntry{id, {}, 0});
    if (it != g_asset_manifest.end() && it->id == id)
        return *it;
    return std::nullopt;
}
```

### 示例 2：consteval 资产路径验证

```cpp
#include <string_view>
#include <stdexcept>

consteval bool validate_asset_path(std::string_view path) {
    // 路径必须以 /assets/ 开头
    if (!path.starts_with("/assets/"))
        throw "Asset path must start with /assets/";  // consteval 中可以 throw
    // 禁止路径穿越
    if (path.find("..") != std::string_view::npos)
        throw "Path traversal detected";
    return true;
}

// 使用：编译期检查
template<auto Path>
struct ValidatedAsset {
    static constexpr std::string_view path = Path;
    static_assert(validate_asset_path(Path));
};

// 使用示例：
// ValidatedAsset<"/assets/textures/player.tex">  asset1;  // ✅ 通过
// ValidatedAsset<"/data/../secret.txt">          asset2;  // ❌ 编译错误！
```

### 示例 3：constinit 解决全局子系统初始化顺序

```cpp
#include <cstdint>
#include <cstdio>

// ============ 引擎子系统定义 ============
struct MemorySystem {
    void* alloc(size_t bytes) {
        total_allocated += bytes;
        return ::operator new(bytes);
    }
    size_t total_allocated = 0;
    bool initialized = false;
};

struct LogSystem {
    void log(const char* msg) {
        frame_count++;
        if (output) std::printf("[Frame %zu] %s\n", frame_count, msg);
    }
    size_t frame_count = 0;
    FILE* output = nullptr;
    bool initialized = false;
};

struct AudioSystem {
    void play(uint64_t sound_id) {
        if (!initialized) std::printf("ERROR: Audio not initialized!\n");
        else std::printf("Playing sound %llu\n", sound_id);
    }
    bool initialized = false;
};

// ============ constinit 全局句柄 ============
// 编译期初始化为 nullptr，运行时由 init() 统一赋值
constinit MemorySystem* g_memory = nullptr;
constinit LogSystem*    g_log    = nullptr;
constinit AudioSystem*  g_audio  = nullptr;

// 独立于任何构造函数的显式初始化函数
void engine_subsystems_init() {
    static MemorySystem memory; memory.initialized = true; g_memory = &memory;
    static LogSystem    log;    log.initialized    = true; g_log    = &log;
    static AudioSystem  audio;  audio.initialized  = true; g_audio  = &audio;

    // 此时可以安全建立子系统间的依赖——所有对象已存在
    g_log->output = stdout;
}

void engine_subsystems_shutdown() {
    g_audio  = nullptr;
    g_log    = nullptr;
    g_memory = nullptr;
}

// 使用
void demo_constinit() {
    engine_subsystems_init();

    g_log->log("Engine booted");
    g_audio->play("ui_click"_id);

    engine_subsystems_shutdown();
}
```

### 示例 4：constexpr 四元数数学（编译期计算朝向常量）

```cpp
#include <cmath>
#include <array>

struct Quaternion {
    float w, x, y, z;

    constexpr Quaternion() : w(1), x(0), y(0), z(0) {}

    constexpr Quaternion(float w_, float x_, float y_, float z_)
        : w(w_), x(x_), y(y_), z(z_) {}

    // constexpr 共轭
    constexpr Quaternion conjugate() const {
        return {w, -x, -y, -z};
    }

    // constexpr 乘法（用于旋转组合）
    constexpr Quaternion operator*(const Quaternion& q) const {
        return {
            w * q.w - x * q.x - y * q.y - z * q.z,
            w * q.x + x * q.w + y * q.z - z * q.y,
            w * q.y - x * q.z + y * q.w + z * q.x,
            w * q.z + x * q.y - y * q.x + z * q.w
        };
    }

    // constexpr 模长平方
    constexpr float norm_sq() const {
        return w * w + x * x + y * y + z * z;
    }
};

// 编译期计算预定义旋转
constexpr Quaternion g_identity     = {1, 0, 0, 0};
constexpr Quaternion g_rot90_y      = {0.707107f, 0, 0.707107f, 0};  // 绕 Y 轴 90°
constexpr Quaternion g_rot180_y     = g_rot90_y * g_rot90_y;           // 编译期乘法！

static_assert(g_rot180_y.w < 0.001f && g_rot180_y.w > -0.001f, "w should be 0 for 180°");
static_assert(g_rot180_y.y > 0.99f, "y component should be ~1 for Y-axis 180°");
```

### 示例 5：编译期 CRC32

```cpp
#include <cstdint>
#include <array>

// 编译期 CRC32 表生成
constexpr auto make_crc32_table() {
    std::array<uint32_t, 256> table{};
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t crc = i;
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320u : 0);
        }
        table[i] = crc;
    }
    return table;
}

constexpr auto g_crc32_table = make_crc32_table();

constexpr uint32_t crc32(const char* data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; ++i) {
        crc = g_crc32_table[(crc ^ static_cast<uint8_t>(data[i])) & 0xFF] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFFu;
}

// 编译期校验
static_assert(crc32("hello", 5) == 0x3610A686u, "CRC32 mismatch");
```

---

## 3. 练习

### 练习 1（必修）：构建编译期资源 ID 系统

实现一个完整的编译期资源 ID 系统：

1. 使用 FNV-1a 哈希将字符串路径映射为 `uint64_t` 资源 ID
2. 提供 `consteval operator""_id` 用户自定义字面量
3. 实现一个编译期 `AssetDatabase` 类，包含资源 ID→文件路径的映射，支持编译期查找
4. 用 `static_assert` 验证至少 5 个资源的 ID 互不相同

### 练习 2（必修）：实现编译期 CRC32 并重构全局单例

1. 实现 `consteval uint32_t crc32(std::string_view)` 函数（包含表生成）
2. 用 `constinit` 重构以下代码，消除静态初始化顺序问题：

```cpp
// 原始代码（有问题）
// file_a.cpp: Logger g_logger("engine.log");
// file_b.cpp: MemoryTracker g_tracker(&g_logger); // g_logger 可能未初始化
```

要求：写一个完整的测试，展示初始化顺序是可控的。

### 练习 3（选做挑战）：编译期资产打包

实现一个 `constexpr` 版本的简单资产打包器：

1. 定义 `struct AssetBlob { uint64_t id; uint32_t offset; uint32_t size; }`
2. 实现 `consteval auto pack_assets(std::initializer_list<std::string_view> paths) -> std::array<AssetBlob, N>`
3. 确保输出的 asset blob 数组按 ID 排序（编译期排序）
4. 实现二进制搜索的编译期查找函数
5. 用 `static_assert` 验证正确性：已知路径 → 预期的 offset 和 size

---

## 4. 扩展阅读

- **C++ Reference: [constexpr specifier](https://en.cppreference.com/w/cpp/language/constexpr)** — 完整的 constexpr 规则
- **C++ Reference: [consteval](https://en.cppreference.com/w/cpp/language/consteval)** — C++20 立即函数
- **"Compile-Time String Hashing in C++"** (Many blog posts) — FNV-1a 和其他哈希策略
- **CppCon 2018: "Compile Time Regular Expressions"** (Hana Dusíková) — constexpr 极限应用的案例
- **Compiler Explorer (godbolt.org)** — 必用工具：检查你的 constexpr 是否真的在编译期求值
- **EASTL** — `eastl::fixed_vector` 等编译期可用容器
- **"The Static Initialization Order Fiasco"** — C++ FAQ 经典文章
- `docs/deep-dives/raii-complete-analysis.md` — RAII 与初始化顺序的关系

---

## 常见陷阱

### 陷阱 1：误以为标记 `constexpr` 就能在编译期执行

```cpp
constexpr int divide(int a, int b) {
    return a / b;  // 如果 b=0 且在编译期求值 → 编译错误！
}

constexpr int x = divide(10, 2);  // ✅ 编译期，正常
constexpr int y = divide(10, 0);  // ❌ 编译错误：除以零
int z = divide(10, runtime_val);  // ⚠️ 运行时，如果 runtime_val=0 → UB（不是编译错误）
```

**教训**：编译期求值的 constexpr 函数会暴露运行时可能隐藏的 UB。这是好事——在编译期发现 bug。

### 陷阱 2：`constexpr` vs `const` 混淆

```cpp
const int a = 42;         // 运行时常量（承诺不修改，但不保证编译期可知）
constexpr int b = 42;     // 编译期常量（保证编译期可知）

int arr1[a];  // ❌ 某些编译器可能不通过（a 不是编译期常量）
int arr2[b];  // ✅ 总是通过（b 是编译期常量）
```

**引擎建议**：需要数组大小、模板参数、`if constexpr` 条件时，必须用 `constexpr`。

### 陷阱 3：C++20 编译期 new 必须在同一求值中 delete

```cpp
constexpr auto leak_at_compile_time() {
    auto* p = new int(42);    // C++20: 编译期分配 OK
    return *p;                // ❌ 编译错误：内存泄漏（p 未被 delete）
}

constexpr auto safe_at_compile_time() {
    auto* p = new int(42);
    int val = *p;
    delete p;                 // ✅ 必须在返回前释放
    return val;
}
```

### 陷阱 4：`consteval` 函数的参数必须是常量表达式

```cpp
consteval int square(int x) { return x * x; }

int   n = square(5);       // ✅
int   m = 5;
// int o = square(m);      // ❌ 编译错误：m 不是常量表达式
```

**引擎场景**：`consteval` 资产路径验证器不能接受用户输入的路径——这符合预期，因为资产路径应该在构建时已知。

### 陷阱 5：过度依赖 `constexpr` 导致编译时间爆炸

```cpp
// ❌ 用 constexpr 计算 100000 个粒子的初始位置
// 可能显著增加编译时间，而这些值完全可以在资源文件中预计算
constexpr auto particles = generate_particles<100000>();  // 编译慢

// ✅ 合理使用：编译期计算数学常量、字符串哈希、CRC
constexpr auto PI = 3.14159265358979323846f;
constexpr auto resource_id = "player_mesh"_id;
```
