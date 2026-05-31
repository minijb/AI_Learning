# C++ 编译模型与游戏构建系统

> 所属计划: C++ 游戏工程师详细攻略
> 预计耗时: 3h
> 前置知识: 无（本系列第一节）

---

## 1. 概念讲解

### 1.1 翻译单元：编译的基本单位

C++ 程序不是"一口气"编译出来的。编译器每次只处理一个 **翻译单元（Translation Unit, TU）**——一个 `.cpp` 文件加上它 `#include` 的所有头文件，经过预处理后的完整文本。

对于一个拥有 10,000+ 源文件的 AAA 游戏引擎，这意味着编译器要独立处理 10,000 个翻译单元，**每个 TU 对彼此一无所知**。它们通过**头文件中的声明**来建立"信任"——"我保证这个函数存在，链接时你会找到它"。

### 1.2 编译的四个阶段

```
源文件 (.cpp)
    │
    ▼
┌──────────────────────┐
│ 阶段 1: 预处理       │  展开 #include, #define, #ifdef...
│  翻译单元诞生         │  输出: 纯 C++ 文本（.i 文件）
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ 阶段 2: 编译         │  语法分析 → AST → 中间表示
│  生成目标代码         │  输出: 汇编 (.s) 或目标文件 (.o/.obj)
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ 阶段 3: 汇编         │  汇编 → 机器码
│  生成可重定位目标文件 │  输出: .o / .obj
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│ 阶段 4: 链接         │  解析符号引用，合并段
│  生成可执行文件       │  输出: .exe / ELF
└──────────────────────┘
```

**游戏引擎的关键影响：** 阶段 2（编译）占整体构建时间的 60-80%。10,000 个 TU 即使每个只花 1 秒编译，也是近 3 小时的构建时间。因此引擎团队投入大量精力在**减少每个 TU 的编译负担**上——这就是后续 PCH、Unity Build、LTO 等技术的动机。

### 1.3 头文件与源文件的分离模式

**声明（declaration）** 告诉编译器"这个东西存在"，**定义（definition）** 告诉编译器"这个东西是什么"。头文件放声明，源文件放定义：

```cpp
// math_types.h  — 声明
#pragma once
struct Vec3 { float x, y, z; };
Vec3 normalize(Vec3 v);           // 声明

// math_types.cpp  — 定义
#include "math_types.h"
#include <cmath>
Vec3 normalize(Vec3 v) {
    float len = std::sqrt(v.x*v.x + v.y*v.y + v.z*v.z);
    return {v.x/len, v.y/len, v.z/len};
}
```

头文件中的**内联函数**和**模板**是例外——它们必须在头文件中提供定义，因为编译器需要看到完整定义才能实例化/内联。这正是编译时间膨胀的主要原因之一。

### 1.4 包含守卫：`#pragma once` vs `#ifndef`

```cpp
// 传统方式
#ifndef MY_ENGINE_MATH_TYPES_H_
#define MY_ENGINE_MATH_TYPES_H_
// ... 头文件内容 ...
#endif

// 现代方式（所有主流编译器支持）
#pragma once
// ... 头文件内容 ...
```

`#pragma once` 的优势：不会因忘写 `#endif` 或宏名冲突而出错；编译器可以优化跳过整个文件（无需重新词法分析）。在 10,000 文件规模的引擎中，这累积节省显著。UE5、Godot 等引擎均使用 `#pragma once`。

### 1.5 单一定义规则（ODR）

ODR 是 C++ 编译模型的核心约束——在每个 TU 中，任何变量、函数、类、枚举或模板最多只能有一个定义；在整个程序中，**非内联**函数或变量的定义必须恰好出现一次。

违反 ODR 的最严重后果是 **ODR 违规无诊断（ill-formed, no diagnostic required）**：两个 TU 各自看到不同的定义（比如不同版本的头文件），链接器可能静默选择其中一个，导致运行时行为随机。这是游戏引擎最难调试的 bug 之一。

**引擎中的防护措施：**
- 严格的头文件依赖管理（Include What You Use）
- CI 中使用 `-Wodr`（GCC/Clang）检查
- 避免在头文件中定义非内联/非模板的函数

### 1.6 内部链接 vs 外部链接

```cpp
// 外部链接（默认）：跨 TU 可见
int g_playerCount = 0;          // 全局变量 → 外部链接
void updatePhysics();           // 函数声明 → 外部链接

// 内部链接：仅本 TU 可见
static int s_threadCount = 8;   // 文件作用域的 static
namespace {                      // 匿名命名空间
    int s_helperVar = 0;        // 内部链接
    void computeImpl() { /*...*/ }
}

// C++17: inline 变量也可以有外部链接且跨 TU 合并
inline constexpr int kMaxPlayers = 64;
```

**引擎实践：** 匿名命名空间（C++ 推荐方式）代替文件作用域的 `static`，给每个 TU 提供真正的"私有"区域。这是 Unity Build 中的关键安全措施之一。

### 1.7 Unity Build（单翻译单元构建）

Unity Build 将多个 `.cpp` 文件 `#include` 进一个"主" `.cpp` 中，使编译器只看到一个巨大的翻译单元：

```cpp
// unity_engine.cpp — Unity Build 主文件
#include "src/math/vec3.cpp"
#include "src/math/mat4.cpp"
#include "src/math/quat.cpp"
#include "src/physics/rigidbody.cpp"
// ... 更多的 #include "xxx.cpp"
```

**优势：**
- 编译时间减少 50-80%（头文件只解析一次）
- 跨 TU 内联/LTO 效果的等效收益
- 模板实例化去重（每个模板实例只生成一次）

**陷阱：**
- **匿名命名空间冲突**：两个 `.cpp` 中同名的匿名命名空间符号会产生重定义错误
- **`static` 函数冲突**：同上
- **宏泄漏**：一个 `.cpp` 中的 `#define` 影响后续所有 `.cpp`
- **增量编译退化**：改一行，整个 Unity TU 重新编译

**引擎中的解决方案：** 用唯一的具名命名空间替代匿名命名空间；确保所有 `.cpp` 在包含前都 `#include` 了自身的依赖；CI 中同时运行 Unity Build 和常规 Build 以捕获 bug。

### 1.8 预编译头文件（PCH）

PCH 将"几乎从不改变"的头文件集合预先编译为二进制映像，后续 TU 直接加载：

```cpp
// pch.h — 预编译头
#pragma once
#include <vector>
#include <string>
#include <unordered_map>
#include <memory>
#include <cmath>
#include <algorithm>
// 引擎核心类型
#include "Engine/Math/Vec3.h"
#include "Engine/Math/Mat4.h"
#include "Engine/Core/Types.h"
// 不常修改的第三方库
#include <EASTL/vector.h>
```

**放入 PCH 的原则：**
- ✅ 标准库头文件
- ✅ 稳定且大体积的第三方库（EASTL, fmt, glm）
- ✅ 引擎核心类型定义（修改频率低）
- ❌ 频繁修改的引擎模块头文件
- ❌ 只有少数 `.cpp` 使用的头文件
- ❌ 平台特定头文件（用不同 PCH 分别管理）

**CMake 中的 PCH 设置：**
```cmake
target_precompile_headers(EngineCore REUSE_FROM EnginePCH)
target_precompile_headers(EngineCore PUBLIC
    <vector>
    <string>
    "Engine/Core/Types.h"
)
```

### 1.9 链接时优化（LTO）

LTO（GCC/Clang）或 Whole Program Optimization（MSVC）将优化推迟到链接阶段，使编译器能看到整个程序的调用图：

```
常规编译:
  TU1 → 优化 → .o1  ─┐
  TU2 → 优化 → .o2  ─┤→ 链接 → 可执行文件
  TU3 → 优化 → .o3  ─┘
  （每个 TU 独立优化，看不到跨 TU 调用机会）

LTO:
  TU1 → 生成 IR → .o1 (含 IR) ─┐
  TU2 → 生成 IR → .o2 (含 IR) ─┤→ 链接 + 全局优化 → 可执行文件
  TU3 → 生成 IR → .o3 (含 IR) ─┘
  （链接器看到完整的 IR，可以做跨模块内联、去虚等）
```

**引擎中的权衡：**
- LTO 可带来 5-15% 的运行时性能提升（通过跨模块内联热路径）
- 但链接时间增加 2-5 倍，链接内存增加 3-10 倍
- Release 构建启用 LTO（慢但值得），Debug/迭代构建关闭（快但不需要）
- Unity Build + LTO 的叠加收益递减——因为 Unity Build 已经消除了很多跨 TU 边界

### 1.10 增量链接与热重载

**增量链接（Incremental Linking）：** MSVC 的 `/INCREMENTAL` 标志使链接器只重新处理变化的部分，将 Debug 链接时间从分钟级降到秒级。

**热重载（Hot Reload）：** 在运行时替换已编译的代码。引擎运行时检测到源文件变化 → 编译为动态库 → 加载新库 → 替换函数指针。这使美术/设计师可以在游戏运行时调整参数而无需重启。Live++ 和 Unreal Engine 的 Live Coding 都基于此原理。

CMake 组织游戏项目时，Engine 层编译为静态库，Game 层编译为可执行文件链接 Engine，Hot Reload 模块编译为独立动态库。这样引擎改动需要重新链接，但 Game 逻辑可以直接热替换。

### 1.11 CMake 游戏引擎项目组织

```cmake
cmake_minimum_required(VERSION 3.21)
project(MyEngine VERSION 1.0 LANGUAGES CXX)

# 全局编译设置
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 平台检测
if(MSVC)
    add_compile_options(/W4 /Zc:preprocessor)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Wno-unused-parameter)
endif()

# Engine 为静态库
add_library(Engine STATIC
    src/engine/core/game_object.cpp
    src/engine/math/vec3.cpp
    # ...
)
target_include_directories(Engine PUBLIC include)

# Game 为可执行文件
add_executable(MyGame
    src/game/main.cpp
    src/game/player.cpp
)
target_link_libraries(MyGame PRIVATE Engine)

# Hot Reload 模块（动态库）
add_library(GameModule SHARED
    src/game/hot_reload_module.cpp
)
target_link_libraries(GameModule PRIVATE Engine)
```

---

## 2. 代码示例

### 示例 1：编译阶段演示 + ODR 检查

```cpp
// compile_demo.cpp
// 演示翻译单元概念和 ODR
#include <iostream>
#include <string>

// 声明（可以出现在任意多个 TU 中）
void greet(const std::string& name);

// 定义只能出现一次（本 TU 中）
void greet(const std::string& name) {
    std::cout << "Hello, " << name << "!\n";
}

// 内联函数可以定义在头文件中，每个 TU 各有一份
inline int square(int x) { return x * x; }

// 内部链接：仅本 TU 可见
namespace {
    int s_callCount = 0;
}

void trackCall() {
    ++s_callCount;
    std::cout << "Called " << s_callCount << " times\n";
}

int main() {
    greet("Engine Developer");
    trackCall();
    std::cout << "Square of 16: " << square(16) << '\n';
    return 0;
}
```

**运行方式：**
```bash
# 查看预处理结果（-E 只做阶段 1）
g++ -std=c++20 -E compile_demo.cpp -o compile_demo.i
# 查看汇编结果（-S 做完阶段 1-2）
g++ -std=c++20 -S -O2 compile_demo.cpp -o compile_demo.s
# 正常编译+链接
g++ -std=c++20 -O2 compile_demo.cpp -o compile_demo && ./compile_demo
```

**预期输出：**
```text
Hello, Engine Developer!
Called 1 times
Square of 16: 256
```

### 示例 2：Unity Build 生成器脚本

```cpp
// unity_gen.cpp — 一个简单的 Unity Build 生成器
// 编译: g++ -std=c++20 unity_gen.cpp -o unity_gen
// 运行: ./unity_gen src/engine/ unity_engine.cpp

#include <iostream>
#include <fstream>
#include <filesystem>
#include <vector>
#include <string>
#include <algorithm>

namespace fs = std::filesystem;

std::vector<std::string> collectCppFiles(const std::string& root) {
    std::vector<std::string> files;
    for (const auto& entry : fs::recursive_directory_iterator(root)) {
        if (entry.path().extension() == ".cpp" &&
            entry.path().filename() != "unity_engine.cpp") {
            files.push_back(fs::relative(entry.path()).string());
        }
    }
    std::sort(files.begin(), files.end());
    return files;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: unity_gen <source_dir> <output_file>\n";
        return 1;
    }

    const std::string srcDir = argv[1];
    const std::string outFile = argv[2];

    auto files = collectCppFiles(srcDir);
    std::ofstream out(outFile);
    out << "// Auto-generated Unity Build — " << files.size() << " source files\n";
    out << "// Generated by unity_gen\n\n";
    out << "#include \"" << srcDir << "/pch.h\"\n\n";

    for (const auto& f : files) {
        out << "#include \"" << f << "\"\n";
    }

    std::cout << "Generated " << outFile << " with " << files.size() << " files.\n";

    // 匿名命名空间冲突警告
    std::cout << "\n⚠️  Ensure all .cpp files use NAMED nested namespaces instead of\n"
              << "   anonymous namespaces to avoid symbol collisions in Unity Build.\n";
    return 0;
}
```

**运行方式：**
```bash
g++ -std=c++20 -O2 unity_gen.cpp -o unity_gen
mkdir -p src/engine/math src/engine/core
# 创建一些测试源文件...
echo 'namespace engine::math { int add(int a, int b) { return a + b; } }' > src/engine/math/basic.cpp
echo 'namespace engine::core { void init() {} }' > src/engine/core/init.cpp
./unity_gen src/engine unity_engine.cpp
cat unity_engine.cpp
```

### 示例 3：PCH 效果测量脚本

```cpp
// pch_bench.cpp — 测量 PCH 对编译时间的影响
// 编译（无 PCH）：  time g++ -std=c++20 -O2 test_no_pch.cpp -o /dev/null
// 编译（有 PCH）：  g++ -std=c++20 -O2 pch.h          → 生成 pch.h.gch
//                  time g++ -std=c++20 -O2 test_with_pch.cpp -o /dev/null

#include <iostream>
#include <chrono>
#include <fstream>
#include <string>
#include <vector>

// 这个文件用于演示：大规模的 #include 会如何拖慢编译
// 实际测量请用 time 命令

int main() {
    std::cout << "PCH Benchmark Helper\n";
    std::cout << "Run the following commands to measure:\n\n";
    std::cout << "1. Generate PCH:\n";
    std::cout << "   g++ -std=c++20 -O2 pch.h -o pch.h.gch\n\n";
    std::cout << "2. Compile WITHOUT PCH:   time g++ -std=c++20 -O2 test.cpp -o /dev/null\n";
    std::cout << "3. Compile WITH PCH:      time g++ -std=c++20 -O2 -include pch.h test.cpp -o /dev/null\n";
    return 0;
}
```

---

## 3. 练习

### 练习 1：搭建 CMake 引擎项目（基础）

创建一个最小游戏引擎 CMake 项目：
- `Engine` 静态库（含两个源文件：`vec3.cpp`, `game_object.cpp`）
- `MyGame` 可执行文件（`main.cpp`，链接 Engine）
- 设置 C++20 标准
- 为两个目标分别设置不同的编译警告级别
- 验证 `cmake --build .` 成功

### 练习 2：实现 Unity Build 生成器（进阶）

扩展上面的 `unity_gen.cpp`，增加以下功能：
- 支持通过命令行参数指定排除文件列表
- 检测并警告潜在的匿名命名空间冲突（提示但不报错）
- 支持生成多个 Unity TU（将源文件分组，每组生成一个 Unity 文件，避免单个 TU 过大）
- 输出详细的统计信息：文件数量、预估总行数、每组文件列表

### 练习 3：测量 & 优化编译时间（可选）

在一个至少包含 20 个以上源文件的项目中（可以自己生成）：
- 测量常规编译的耗时作为基线
- 为项目配置 PCH，测量改进效果
- 生成 Unity Build 文件，测量编译时间
- 对比三种方案的编译时间，并分析原因
- （进阶）尝试启用 LTO（`-flto`），测量编译+链接总时间，以及生成的可执行文件大小差异

---

## 4. 扩展阅读

- **[必读] C++ Reference — Translation phases:** https://en.cppreference.com/w/cpp/language/translation_phases — 编译阶段的标准定义
- **[必读] C++ Reference — ODR:** https://en.cppreference.com/w/cpp/language/definition — 单一定义规则的精确条款
- **[推荐] "#pragma once vs #include guards"** — https://en.wikipedia.org/wiki/Pragma_once
- **[推荐] CMake Official Tutorial** — https://cmake.org/cmake/help/latest/guide/tutorial/ — CMake 入门到进阶
- **[推荐] "Unity Builds" by Aras Pranckevičius** — https://aras-p.info/blog/2018/02/02/Unity-Builds/ — Unity 引擎团队的实践总结
- **[进阶] Link-Time Optimization (GCC internals)** — https://gcc.gnu.org/onlinedocs/gccint/LTO.html
- **[工具] Compiler Explorer** — https://godbolt.org/ — 在线查看编译结果
- **[工具] Ccache** — https://ccache.dev/ — 编译缓存加速工具

---

## 常见陷阱

1. **在头文件中使用匿名命名空间。**
   ```cpp
   // ❌ 错误：helper.h
   namespace { int g_counter = 0; }  // 每个 TU 都创建一个独立变量！
   
   // ✅ 正确：helper.h
   inline int& getCounter() {
       static int counter = 0;  // 唯一的变量（C++17 inline static）
       return counter;
   }
   ```
   匿名命名空间给每个 TU 创建私有副本，多个 TU 各自拥有独立的 `g_counter`——这几乎不可能是你想要的。

2. **头文件中使用 `using namespace` 指令。**
   ```cpp
   // ❌ 错误：engine_math.h
   #pragma once
   using namespace std;  // 污染所有包含此头的 TU！
   
   // ✅ 正确：在 .cpp 中使用，或限制在函数作用域内
   // engine_math.h
   #pragma once
   namespace engine::math {
       using Vector3 = std::array<float, 3>;  // 类型别名，可控
   }
   ```

3. **PCH 中包含频繁修改的头文件。**
   - 修改 PCH 中任何一个文件，会导致**所有 TU 重新编译**
   - 将 PCH 看作"编译防火墙"——只放几乎不变的代码
   - 如果某个头文件每周都在改，它不该在 PCH 中

4. **Unity Build 中忘记保护 `#define` 泄漏。**
   ```cpp
   // file_a.cpp
   #define MAX_SIZE 256
   // file_b.cpp（被同一个 Unity TU 包含）
   #define MAX_SIZE 512  // ❌ 重定义错误！file_a 的宏泄漏到了 file_b
   
   // ✅ 正确：使用 constexpr 替代宏，或用完后 #undef
   constexpr int kMaxSizeA = 256;
   ```

5. **混淆 `#include` 路径导致 ODR 违规。**
   ```cpp
   // 文件系统中有两个路径指向同一个头文件
   // module_a.cpp: #include "Engine/Math/Vec3.h"
   // module_b.cpp: #include "../Engine/Math/Vec3.h"
   // → 在某些构建配置中可能被视为不同文件 → ODR 违规
   
   // ✅ 正确：统一使用 include 目录，相对路径从 include root 开始
   // CMake: target_include_directories(Engine PUBLIC include)
   // 所有文件: #include "Engine/Math/Vec3.h"
   ```
