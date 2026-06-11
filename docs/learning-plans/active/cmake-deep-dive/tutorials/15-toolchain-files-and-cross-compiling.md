---
title: "工具链文件与交叉编译"
updated: 2026-06-10
---

> 所属计划: [[INDEX|CMake 深度学习]]
> 预计耗时: 60 分钟
> 前置知识: [[05-project-and-compiler-detection]]（`project()` 与编译器检测）、[[14-cmake-presets]]（CMakePresets.json）

---

## 1. 概念讲解

### 为什么需要这个？

你正在 x86_64 Linux 上开发，但目标要跑在树莓派（ARM）上。或者你想把 C++ 代码编译成 WebAssembly 跑在浏览器里。又或者你需要同时发布 Windows、macOS、Linux 三平台的二进制文件。

这些场景有一个共同点：**构建平台 ≠ 目标平台**。这就是交叉编译（cross-compilation）。

CMake 对交叉编译的支持极其优雅——你只需要一个**工具链文件（Toolchain File）**，告诉 CMake "别用你身边的编译器，用这台设备上的"，CMake 就会自动调整所有行为：
- 不再尝试运行编译出的测试程序（因为目标平台的二进制无法在构建机上执行）
- `find_package()` 在目标 sysroot 里查找库，而不是构建机系统目录
- 编译器检测逻辑调整为仅检查编译能力，不检查链接和运行

> [!warning] 没有工具链文件
> 如果你试图在 x86_64 上直接用 ARM 编译器而不指定工具链文件，CMake 会把交叉编译器当作本地编译器使用，产生各种诡异的链接错误和头文件找不到的问题。

### 核心思想

**工具链文件 = 目标平台的全部描述。** 它是一个 CMake 脚本，在 `project()` 命令**之前**被读取，负责设置：

1. **目标系统身份**：`CMAKE_SYSTEM_NAME`、`CMAKE_SYSTEM_PROCESSOR`
2. **编译器路径**：`CMAKE_C_COMPILER`、`CMAKE_CXX_COMPILER`
3. **目标文件系统根**：`CMAKE_SYSROOT`、`CMAKE_FIND_ROOT_PATH`
4. **查找行为**：`CMAKE_FIND_ROOT_PATH_MODE_PROGRAM` 等

一旦设置了 `CMAKE_SYSTEM_NAME`（且它不等于构建机系统名），CMake 就进入**交叉编译模式**，变量 `CMAKE_CROSSCOMPILING` 自动为 `TRUE`。

```
┌─────────────────────────────────────────────────┐
│  构建主机 (Build/Host)                          │
│  x86_64 Linux + CMake + 交叉编译器              │
│                                                 │
│  ┌───────────────────────────┐                 │
│  │  CMakeLists.txt            │                 │
│  │    │                       │                 │
│  │    ▼                       │                 │
│  │  project() ←── toolchain ──┤                 │
│  │    │          file          │                 │
│  │    ▼                       │                 │
│  │  交叉编译工具链             │                 │
│  │  (arm-linux-gnueabihf-g++) │                 │
│  └─────────────┬─────────────┘                 │
│                │ 产出 ARM 二进制                │
│                ▼                                │
│  ┌───────────────────────────┐                 │
│  │  目标设备 (Target)         │                 │
│  │  ARM Linux (树莓派)        │                 │
│  └───────────────────────────┘                 │
└─────────────────────────────────────────────────┘
```

> [!tip] 执行顺序
> CMake 的执行顺序：`CMakeLists.txt` 的 `cmake_minimum_required()` → **工具链文件** → `project()`。工具链文件是第一个被 CMake 处理的用户脚本，因此它的变量设置会覆盖 CMake 的所有自动检测。

---

## 2. 代码示例

### 示例 1: ARM Linux 交叉编译 — 完整工具链文件

下面是一个完整的、可直接用于 ARM Linux（树莓派 / BeagleBone）的工具链文件。它演示了所有核心机制。

**文件: `arm-linux-toolchain.cmake`**

```cmake
# arm-linux-toolchain.cmake
# 用法: cmake -B build -DCMAKE_TOOLCHAIN_FILE=arm-linux-toolchain.cmake

# ============================================================
# 1. 目标系统身份
# ============================================================
set(CMAKE_SYSTEM_NAME Linux)              # 目标操作系统
set(CMAKE_SYSTEM_PROCESSOR arm)           # 目标 CPU 架构
# 可选：更精细的版本
# set(CMAKE_SYSTEM_VERSION 1)

# ============================================================
# 2. 交叉编译器
# ============================================================
# 方式 A: 直接指定编译器路径
set(CMAKE_C_COMPILER    /usr/bin/arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER  /usr/bin/arm-linux-gnueabihf-g++)
set(CMAKE_ASM_COMPILER  /usr/bin/arm-linux-gnueabihf-gcc)

# 方式 B (推荐): 不指定完整路径，让 PATH 去解析
# set(CMAKE_C_COMPILER   arm-linux-gnueabihf-gcc)
# set(CMAKE_CXX_COMPILER arm-linux-gnueabihf-g++)

# ============================================================
# 3. 目标 sysroot — 目标系统的 "/"
# ============================================================
# Sysroot 是目标设备文件系统的镜像，包含目标平台的
# libc、头文件、系统库。通常通过 rsync 从目标设备同步
# 或从 Linaro/GCC 工具链包解压得到。
set(CMAKE_SYSROOT /path/to/arm-sysroot)

# ============================================================
# 4. 查找根路径 — 告诉 find_* 只在这些路径下搜索
# ============================================================
set(CMAKE_FIND_ROOT_PATH
    ${CMAKE_SYSROOT}                     # sysroot 本身
    ${CMAKE_SYSROOT}/usr                 # 标准系统库
    ${CMAKE_SYSROOT}/usr/local           # 手动安装的库
    /path/to/custom-arm-libs             # 你自己的 ARM 预编译库
)

# ============================================================
# 5. 查找行为控制 — 只在目标 sysroot 中查找
# ============================================================
# PROGRAM: 可执行文件（NEVER — 因为在目标 sysroot 里找
#          到的可执行文件无法在构建机上运行）
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)

# LIBRARY: 库文件（ONLY — 只在目标 sysroot 里找，避免
#         误链接构建机的 x86_64 库）
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)

# INCLUDE: 头文件（ONLY — 只在目标 sysroot 里找）
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)

# PACKAGE: CMake 包的查找位置（ONLY）
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# ============================================================
# 6. (可选) 目标编译标志
# ============================================================
set(CMAKE_C_FLAGS   "${CMAKE_C_FLAGS}   -march=armv7-a -mfpu=neon -mfloat-abi=hard" CACHE STRING "")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -march=armv7-a -mfpu=neon -mfloat-abi=hard" CACHE STRING "")

# ============================================================
# 7. (可选) 如果链接器无法生成可执行文件
#    设为 STATIC_LIBRARY 让 CMake 只测试编译，不测试链接
# ============================================================
# set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
```

**配套的 `CMakeLists.txt`：**

```cmake
cmake_minimum_required(VERSION 3.24)
project(HelloARM VERSION 1.0 LANGUAGES CXX)

add_executable(hello_arm main.cpp)
install(TARGETS hello_arm DESTINATION bin)
```

**运行方式：**

```bash
# 1. 确保交叉编译器已安装（Ubuntu/Debian 示例）
sudo apt-get install gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf

# 2. 准备 sysroot（可选：从设备同步）
mkdir -p ~/arm-sysroot
rsync -avz pi@raspberrypi:/lib     ~/arm-sysroot/
rsync -avz pi@raspberrypi:/usr/lib ~/arm-sysroot/usr/
rsync -avz pi@raspberrypi:/usr/include ~/arm-sysroot/usr/

# 3. 配置 + 构建
cmake -B build-arm \
    -DCMAKE_TOOLCHAIN_FILE=arm-linux-toolchain.cmake \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build-arm

# 4. 验证生成的二进制
file build-arm/hello_arm
# 预期输出: ELF 32-bit LSB executable, ARM, EABI5...
```

**预期输出：**

```text
-- The CXX compiler identification is GNU 12.2.0
-- Detecting CXX compiler ABI info
-- Detecting CXX compiler ABI info - done
-- Check for working CXX compiler: /usr/bin/arm-linux-gnueabihf-g++ - skipped
-- Configuring done
-- Generating done
-- Build files have been written to: /home/user/project/build-arm
```

---

### 示例 2: Android NDK 工具链文件

Android NDK 自带官方的 CMake 工具链文件 `android.toolchain.cmake`。你只需指定它，再加上 Android 相关的 ABI 和 API 级别参数。

**文件: `CMakeLists.txt`**

```cmake
cmake_minimum_required(VERSION 3.24)
project(HelloAndroid VERSION 1.0 LANGUAGES CXX)

add_library(hello_jni SHARED
    hello_jni.cpp
)
```

**文件: `hello_jni.cpp`**

```cpp
#include <jni.h>
#include <string>

extern "C" JNIEXPORT jstring JNICALL
Java_com_example_MainActivity_stringFromJNI(
    JNIEnv* env, jobject /* this */) {
    return env->NewStringUTF("Hello from CMake + NDK!");
}
```

**运行方式：**

```bash
# 1. 下载 Android NDK（如果还没有）
# 从 https://developer.android.com/ndk/downloads 下载
# 或通过 Android Studio SDK Manager 安装
# 假设 NDK 安装在: ~/Android/Sdk/ndk/26.1.10909125

export ANDROID_NDK=~/Android/Sdk/ndk/26.1.10909125

# 2. 使用 NDK 自带的工具链文件
cmake -B build-android-arm64 \
    -DCMAKE_TOOLCHAIN_FILE=${ANDROID_NDK}/build/cmake/android.toolchain.cmake \
    -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-24 \
    -DCMAKE_BUILD_TYPE=Release

# 3. 构建
cmake --build build-android-arm64

# 4. 验证
file build-android-arm64/libhello_jni.so
# 预期: ELF 64-bit LSB shared object, ARM aarch64...

# 5. 还可以一次构建多个 ABI（配合 CMakePresets 更佳）
for abi in armeabi-v7a arm64-v8a x86 x86_64; do
    cmake -B build-android-$abi \
        -DCMAKE_TOOLCHAIN_FILE=${ANDROID_NDK}/build/cmake/android.toolchain.cmake \
        -DANDROID_ABI=$abi \
        -DANDROID_PLATFORM=android-24
    cmake --build build-android-$abi
done
```

**关键 NDK 变量一览：**

| 变量 | 说明 | 可选值 |
|------|------|--------|
| `ANDROID_ABI` | 目标 ABI | `armeabi-v7a`, `arm64-v8a`, `x86`, `x86_64` |
| `ANDROID_PLATFORM` | 最低 API 级别 | `android-21` ~ `android-34` |
| `ANDROID_STL` | C++ 标准库 | `c++_shared`, `c++_static`, `none` |
| `ANDROID_NDK` | NDK 路径（通常自动检测） | 文件系统路径 |

> [!tip] `ANDROID_STL`
> 默认使用 `c++_shared`（`libc++_shared.so`），打包 APK 时记得把该 `.so` 也放进 `lib/` 目录。如果多个 `.so` 都依赖 C++ STL，务必使用 `c++_shared` 避免 ODR 问题。

---

### 示例 3: Emscripten / WebAssembly 工具链文件

Emscripten 将 C/C++ 编译为 WebAssembly，运行在浏览器或 Node.js 中。它自带工具链文件 `Emscripten.cmake`。

**文件: `CMakeLists.txt`**

```cmake
cmake_minimum_required(VERSION 3.24)
project(HelloWasm VERSION 1.0 LANGUAGES CXX)

# Emscripten 下通常构建为可执行文件
# 产出 .html + .wasm + .js 三件套
add_executable(hello_wasm main.cpp)

# 设置 Emscripten 特定链接选项
target_link_options(hello_wasm PRIVATE
    "-sEXPORTED_FUNCTIONS=['_main','_fibonacci']"
    "-sEXPORTED_RUNTIME_METHODS=['ccall','cwrap']"
)
```

**文件: `main.cpp`**

```cpp
#include <iostream>
#include <emscripten.h>

// EMSCRIPTEN_KEEPALIVE 阻止链接器优化掉此函数
extern "C" {
    EMSCRIPTEN_KEEPALIVE
    int fibonacci(int n) {
        if (n <= 1) return n;
        return fibonacci(n - 1) + fibonacci(n - 2);
    }
}

int main() {
    std::cout << "Hello from WebAssembly!" << std::endl;
    std::cout << "fib(10) = " << fibonacci(10) << std::endl;
    return 0;
}
```

**运行方式：**

```bash
# 1. 安装 Emscripten SDK
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest
source ./emsdk_env.sh          # Linux/macOS
# emsdk_env.bat                # Windows

# 2. 配置 — 使用 Emscripten 工具链文件
cmake -B build-wasm \
    -DCMAKE_TOOLCHAIN_FILE=${EMSDK}/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake \
    -DCMAKE_BUILD_TYPE=Release

# 3. 构建
cmake --build build-wasm

# 4. 在浏览器中运行
# 产出文件: build-wasm/hello_wasm.html
# 直接用浏览器打开（需要本地 HTTP 服务器）
python3 -m http.server 8000 -d build-wasm
# 然后在浏览器打开 http://localhost:8000/hello_wasm.html

# 5. 或用 Node.js 运行
node build-wasm/hello_wasm.js
```

**预期输出（控制台/终端）：**

```text
Hello from WebAssembly!
fib(10) = 55
```

> [!tip] Emscripten 变量速查
> 你可以在 `cmake` 命令行传 `-DCMAKE_CXX_FLAGS="-sUSE_SDL=2"` 或通过 `target_link_options` 追加链接标志。常用链接标志：
> - `-sEXPORTED_FUNCTIONS='[...]'` — 导出 C 函数给 JS 调用
> - `-sALLOW_MEMORY_GROWTH=1` — 允许动态增长内存
> - `-sINITIAL_MEMORY=256MB` — 初始内存大小
> - `-sUSE_PTHREADS=1` — 启用多线程（需 SharedArrayBuffer）

---

### 更多交叉编译场景

#### iOS / tvOS

目标系统名为 `Darwin`，结合 `CMAKE_SYSTEM_PROCESSOR` 和特定标志：

```cmake
# ios-toolchain.cmake
set(CMAKE_SYSTEM_NAME Darwin)
set(CMAKE_SYSTEM_PROCESSOR arm64)
set(CMAKE_OSX_SYSROOT iphoneos)
set(CMAKE_C_COMPILER   "$(xcode-select -p)/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang")
set(CMAKE_CXX_COMPILER "$(xcode-select -p)/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++")

# 也可以直接用社区维护的通用工具链文件:
# https://github.com/leetal/ios-cmake
```

#### Windows from Linux (MinGW)

使用 MinGW 交叉编译器在 Linux 上编译 Windows `.exe`：

```cmake
# mingw-w64-toolchain.cmake
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)

set(CMAKE_C_COMPILER   x86_64-w64-mingw32-gcc)
set(CMAKE_CXX_COMPILER x86_64-w64-mingw32-g++)
set(CMAKE_RC_COMPILER  x86_64-w64-mingw32-windres)

# 可选：静态链接 libgcc/libstdc++ 避免目标机器缺少 DLL
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -static-libgcc -static-libstdc++" CACHE STRING "")
```

```bash
# 安装工具链
sudo apt-get install mingw-w64
# 配置构建
cmake -B build-win \
    -DCMAKE_TOOLCHAIN_FILE=mingw-w64-toolchain.cmake
cmake --build build-win
```

---

### CMakePresets.json 中使用工具链文件

将工具链文件直接嵌入 presets，团队成员无需记忆命令行参数：

```json
{
  "version": 6,
  "cmakeMinimumRequired": {
    "major": 3,
    "minor": 24,
    "patch": 0
  },
  "configurePresets": [
    {
      "name": "native-release",
      "displayName": "Native Release (x86_64)",
      "binaryDir": "${sourceDir}/build/native-release",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release"
      }
    },
    {
      "name": "arm-linux-release",
      "displayName": "ARM Linux Release",
      "inherits": "native-release",
      "binaryDir": "${sourceDir}/build/arm-linux-release",
      "toolchainFile": "${sourceDir}/cmake/arm-linux-toolchain.cmake"
    },
    {
      "name": "android-arm64",
      "displayName": "Android arm64-v8a",
      "binaryDir": "${sourceDir}/build/android-arm64",
      "toolchainFile": "$env{ANDROID_NDK}/build/cmake/android.toolchain.cmake",
      "cacheVariables": {
        "ANDROID_ABI": "arm64-v8a",
        "ANDROID_PLATFORM": "android-24",
        "CMAKE_BUILD_TYPE": "Release"
      }
    },
    {
      "name": "wasm-release",
      "displayName": "WebAssembly Release",
      "binaryDir": "${sourceDir}/build/wasm-release",
      "toolchainFile": "$env{EMSDK}/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release"
      }
    }
  ],
  "buildPresets": [
    {
      "name": "native-release",
      "configurePreset": "native-release"
    },
    {
      "name": "arm-linux-release",
      "configurePreset": "arm-linux-release"
    },
    {
      "name": "android-arm64",
      "configurePreset": "android-arm64"
    },
    {
      "name": "wasm-release",
      "configurePreset": "wasm-release"
    }
  ]
}
```

```bash
# 一键配置任意目标
cmake --preset arm-linux-release
cmake --build --preset arm-linux-release
```

---

### 交叉编译下的 `try_compile()` 与 `try_run()`

#### `try_compile()`

CMake 在配置阶段会执行编译器特性检测——这些"尝试编译"本质上就是 `try_compile()`。在交叉编译模式下：

- 如果链接没问题 → 检测正常进行
- 如果无法链接（比如缺少目标平台的 crt0、libc）→ 测试失败

解决方案：设置 `CMAKE_TRY_COMPILE_TARGET_TYPE` 为 `STATIC_LIBRARY`，让 CMake 只测试编译能力，不测试链接：

```cmake
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
```

#### `try_run()`

`try_run()` 会在构建机上运行编译出的程序来获取运行时信息（如 `sizeof(int)`）。交叉编译时这不可能——二进制是 ARM 的，无法在 x86_64 上运行。

有三种处理方式：

**方式 1：提供预计算结果（最常用）**

在工具链文件中预设答案，跳过运行时检测：

```cmake
# arm-linux-toolchain.cmake
set(HAVE_SIZEOF_INT       1 CACHE INTERNAL "")
set(SIZEOF_INT            4 CACHE INTERNAL "")
set(SIZEOF_POINTER        4 CACHE INTERNAL "")  # 32-bit ARM

# 每个 try_run() 都对应一个 RESULT_VARIABLE 和 OUTPUT_VARIABLE
# 你需要在工具链文件中用 set(... CACHE) 预设它们
```

**方式 2：使用模拟器**

设置 `CMAKE_CROSSCOMPILING_EMULATOR`，CMake 会通过这个模拟器运行编译出的程序：

```cmake
# 使用 QEMU 用户模式模拟 ARM 程序
set(CMAKE_CROSSCOMPILING_EMULATOR qemu-arm)
# 或带参数
set(CMAKE_CROSSCOMPILING_EMULATOR qemu-arm;-L;${CMAKE_SYSROOT})
```

```bash
# 安装 QEMU 用户模式
sudo apt-get install qemu-user qemu-user-static
```

**方式 3：在代码中使用 `CMAKE_CROSSCOMPILING`**

```cmake
if(CMAKE_CROSSCOMPILING)
    # 交叉编译 — 用预设值
    message(STATUS "Cross-compiling: using predefined values")
    set(MY_SIZEOF_INT 4)
else()
    # 本地编译 — 可以安全运行
    try_run(RUN_RESULT COMPILE_RESULT
        ${CMAKE_BINARY_DIR}
        ${CMAKE_SOURCE_DIR}/cmake/check_sizeof.cpp
        RUN_OUTPUT_VARIABLE MY_SIZEOF_INT
    )
endif()
```

---

## 3. 练习

### 练习 1: 32-bit 编译工具链文件

在 64-bit Linux 主机上编写一个工具链文件，使用 `gcc -m32` 实现 32-bit 编译（本质上是同架构但不同字长的"交叉编译"）。

要求：
- 目标系统名仍为 `Linux`，处理器设为 `i686`
- 通过 `CMAKE_C_FLAGS` 和 `CMAKE_CXX_FLAGS` 传入 `-m32`，编译器仍使用系统的 `gcc`/`g++`
- 设置合适的 `CMAKE_FIND_ROOT_PATH_MODE_*`
- 创建一个简单的 `CMakeLists.txt`（打印 `sizeof(void*)`），分别用 native 和 32-bit 工具链构建，验证指针大小

提示：需要安装 32-bit 库：

```bash
sudo apt-get install gcc-multilib g++-multilib
```

### 练习 2: Android NDK 交叉编译实践

使用 Android NDK 的工具链文件，完成以下步骤：

1. 创建一个包含 JNI 函数的共享库（如练习 2 示例）
2. 用 `cmake --preset`（配合 CMakePresets.json）构建 `arm64-v8a` 和 `x86_64` 两个 ABI
3. 验证产出的 `.so` 文件架构：`file build-android-*/libhello_jni.so`
4. 实验 `ANDROID_STL` 分别设为 `c++_shared` 和 `c++_static`，观察链接产物的文件大小差异

### 练习 3: 多平台 CMakePresets.json

为一个库项目（3~4 个源文件，使用 C++17）编写 `CMakePresets.json`，包含以下 configure presets：

- `native-debug` / `native-release`：本地构建
- `arm-linux-release`：ARM Linux 交叉编译（toolchainFile 指向练习 1 的文件）
- `mingw-release`：MinGW 交叉编译 Windows（toolchainFile 指向自写的 MinGW 工具链文件）
- `android-arm64`：Android NDK（使用 `$env{ANDROID_NDK}` 动态路径）
- `wasm-release`：Emscripten

并确保每个 configure preset 都有对应的 build preset。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **`i686-linux-toolchain.cmake`：**
> ```cmake
> # i686-linux-toolchain.cmake
> # 用法: cmake -B build32 -DCMAKE_TOOLCHAIN_FILE=i686-linux-toolchain.cmake
>
> set(CMAKE_SYSTEM_NAME Linux)
> set(CMAKE_SYSTEM_PROCESSOR i686)
>
> # 使用系统的 gcc/g++，通过 -m32 编译 32-bit
> set(CMAKE_C_COMPILER    gcc)
> set(CMAKE_CXX_COMPILER  g++)
>
> set(CMAKE_C_FLAGS   "${CMAKE_C_FLAGS}   -m32" CACHE STRING "")
> set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -m32" CACHE STRING "")
>
> # 查找行为：尽量在宿主机路径中查找（32-bit lib 和普通 lib 可能同路径）
> set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
> set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
> set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
> set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
> ```
>
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(PtrSize VERSION 1.0 LANGUAGES CXX)
>
> add_executable(ptr_size main.cpp)
> ```
>
> **`main.cpp`：**
> ```cpp
> #include <iostream>
> int main() {
>     std::cout << "sizeof(void*) = " << sizeof(void*) << "\n";
>     return 0;
> }
> ```
>
> **验证：**
> ```bash
> sudo apt-get install gcc-multilib g++-multilib
>
> # Native 64-bit
> cmake -B build64
> cmake --build build64
> ./build64/ptr_size    # → sizeof(void*) = 8
>
> # 32-bit
> cmake -B build32 -DCMAKE_TOOLCHAIN_FILE=i686-linux-toolchain.cmake
> cmake --build build32
> ./build32/ptr_size    # → sizeof(void*) = 4
> ```

> [!tip]- 练习 2 参考答案
> **`CMakeLists.txt`：**
> ```cmake
> cmake_minimum_required(VERSION 3.24)
> project(HelloJNI VERSION 1.0 LANGUAGES CXX)
>
> add_library(hello_jni SHARED hello_jni.cpp)
> ```
>
> **`CMakePresets.json`：**
> ```json
> {
>   "version": 6,
>   "configurePresets": [
>     {
>       "name": "android-arm64",
>       "toolchainFile": "$env{ANDROID_NDK}/build/cmake/android.toolchain.cmake",
>       "cacheVariables": {
>         "ANDROID_ABI": "arm64-v8a",
>         "ANDROID_PLATFORM": "android-24",
>         "ANDROID_STL": "c++_shared"
>       }
>     },
>     {
>       "name": "android-x86_64",
>       "toolchainFile": "$env{ANDROID_NDK}/build/cmake/android.toolchain.cmake",
>       "cacheVariables": {
>         "ANDROID_ABI": "x86_64",
>         "ANDROID_PLATFORM": "android-24",
>         "ANDROID_STL": "c++_shared"
>       }
>     }
>   ],
>   "buildPresets": [
>     { "name": "android-arm64", "configurePreset": "android-arm64" },
>     { "name": "android-x86_64", "configurePreset": "android-x86_64" }
>   ]
> }
> ```
>
> **`hello_jni.cpp`**（复用示例 2 中的代码）。
>
> **验证：**
> ```bash
> export ANDROID_NDK=~/Android/Sdk/ndk/26.1.10909125
> cmake --preset android-arm64
> cmake --build --preset android-arm64
> file build-android-arm64/libhello_jni.so
> # 预期: ELF 64-bit LSB shared object, ARM aarch64
>
> cmake --preset android-x86_64
> cmake --build --preset android-x86_64
> file build-android-x86_64/libhello_jni.so
> # 预期: ELF 64-bit LSB shared object, x86-64
> ```
>
> **`ANDROID_STL` 实验：**
> ```bash
> # c++_shared → .so 小，运行时依赖 libc++_shared.so（~1MB），APK 中需打包
> # c++_static → .so 大（STL 嵌入），自包含但多个 .so 会重复
> cmake -B build-shared \
>     -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/... \
>     -DANDROID_STL=c++_shared -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=24
> cmake -B build-static \
>     -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/... \
>     -DANDROID_STL=c++_static -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=24
> ls -lh build-shared/libhello_jni.so build-static/libhello_jni.so
> ```

> [!tip]- 练习 3 参考答案
> **`CMakePresets.json`：**
> ```json
> {
>   "version": 6,
>   "configurePresets": [
>     {
>       "name": "native-debug",
>       "displayName": "Native Debug",
>       "cacheVariables": { "CMAKE_BUILD_TYPE": "Debug" }
>     },
>     {
>       "name": "native-release",
>       "displayName": "Native Release",
>       "cacheVariables": { "CMAKE_BUILD_TYPE": "Release" }
>     },
>     {
>       "name": "arm-linux-release",
>       "displayName": "ARM Linux Release",
>       "toolchainFile": "${sourceDir}/cmake/arm-linux-toolchain.cmake",
>       "cacheVariables": { "CMAKE_BUILD_TYPE": "Release" }
>     },
>     {
>       "name": "mingw-release",
>       "displayName": "MinGW Windows Release",
>       "toolchainFile": "${sourceDir}/cmake/mingw-toolchain.cmake",
>       "cacheVariables": { "CMAKE_BUILD_TYPE": "Release" }
>     },
>     {
>       "name": "android-arm64",
>       "displayName": "Android arm64-v8a",
>       "toolchainFile": "$env{ANDROID_NDK}/build/cmake/android.toolchain.cmake",
>       "cacheVariables": {
>         "ANDROID_ABI": "arm64-v8a",
>         "ANDROID_PLATFORM": "android-24",
>         "ANDROID_STL": "c++_shared"
>       }
>     },
>     {
>       "name": "wasm-release",
>       "displayName": "WebAssembly Release",
>       "toolchainFile": "$env{EMSDK}/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake",
>       "cacheVariables": { "CMAKE_BUILD_TYPE": "Release" }
>     }
>   ],
>   "buildPresets": [
>     { "name": "native-debug",   "configurePreset": "native-debug" },
>     { "name": "native-release", "configurePreset": "native-release" },
>     { "name": "arm-linux",      "configurePreset": "arm-linux-release" },
>     { "name": "mingw",          "configurePreset": "mingw-release" },
>     { "name": "android-arm64",  "configurePreset": "android-arm64" },
>     { "name": "wasm",           "configurePreset": "wasm-release" }
>   ]
> }
> ```
>
> **使用：**
> ```bash
> cmake --preset native-debug
> cmake --build --preset native-debug
> cmake --preset arm-linux-release
> cmake --build --preset arm-linux
> ```
>
> **关键点：** `${sourceDir}` 在 CMakePresets 中引用项目源码根目录；`$env{ANDROID_NDK}` 引用环境变量。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- [CMake 官方文档: cmake-toolchains(7)](https://cmake.org/cmake/help/latest/manual/cmake-toolchains.7.html) — 工具链文件权威文档
- [CMake 官方文档: CMAKE_TOOLCHAIN_FILE](https://cmake.org/cmake/help/latest/variable/CMAKE_TOOLCHAIN_FILE.html)
- [CMake 官方文档: Cross Compiling](https://cmake.org/cmake/help/latest/manual/cmake-toolchains.7.html#cross-compiling)
- [Android NDK CMake 指南](https://developer.android.com/ndk/guides/cmake)
- [Emscripten CMake 集成](https://emscripten.org/docs/compiling/Building-Projects.html#building-projects)
- [ios-cmake 通用 iOS 工具链文件](https://github.com/leetal/ios-cmake)
- [Raspberry Pi CMake 交叉编译指南](https://www.raspberrypi.com/documentation/computers/linux_kernel.html#cross-compiling-the-kernel) — 虽然针对内核，但 sysroot 原理相同
- [Craig Scott《Professional CMake》第 22 章: Cross-compiling](https://crascit.com/professional-cmake/)

---

## 常见陷阱

- **陷阱 1: 在工具链文件中使用 `CMAKE_SOURCE_DIR`。** 工具链文件可能通过 `include()` 被间接使用，此时 `CMAKE_SOURCE_DIR` 是**包含者的**源码目录，不是你工具链文件所在目录。始终使用 `CMAKE_CURRENT_LIST_DIR` 来定位工具链文件自己的目录，比如引用同目录下的 `.cmake` 模块或 sysroot 路径。

- **陷阱 2: `CMAKE_FIND_ROOT_PATH_MODE_PROGRAM` 设为 `ONLY` 或 `BOTH`。** 这会让 CMake 去目标 sysroot 里找可执行工具（如 `protoc`、`llvm-tblgen`）。但目标 sysroot 里的程序无法在构建机上运行。**始终设为 `NEVER`**，让 CMake 在构建机 `PATH` 中查找代码生成工具。

- **陷阱 3: `try_run()` 失败导致配置中断。** 交叉编译时 `try_run()` 无法在构建机上运行目标平台的二进制，默认行为是报错。解决方案：在工具链文件中用 `set(... CACHE INTERNAL "")` 预设所有 `try_run()` 的结果变量，或设置 `CMAKE_CROSSCOMPILING_EMULATOR`。`cmake --debug-trycompile` 可以帮助定位哪些 `try_compile`/`try_run` 失败了。

- **陷阱 4: 忘记设置 `CMAKE_FIND_ROOT_PATH`。** 没有设置查找路径时，`find_library()` 和 `find_path()` 可能返回到**构建机**的库和头文件。同样致命的是部分设置了（如 `MODE_LIBRARY ONLY` 但 `MODE_INCLUDE` 仍是 `BOTH`），导致目标平台的库编译时混用了构建机的头文件。

- **陷阱 5: 工具链文件被多次 `include()`。** CMake 处理工具链文件时只读取一次，但如果你在项目中 `include()` 它，它会被重新执行。使用 `include_guard(GLOBAL)` 或在文件开头检查一个已设置的变量：

  ```cmake
  if(DEFINED MY_TOOLCHAIN_INCLUDED)
      return()
  endif()
  set(MY_TOOLCHAIN_INCLUDED TRUE)
  ```

- **陷阱 6: NDK 工具链文件中 `ANDROID_STL` 默认值。** 如果不显式设置，Android NDK 的 CMake 工具链默认使用 `none`，意味着没有 C++ 标准库、没有 `std::string`、没有异常。多数项目需要设为 `c++_shared` 或 `c++_static`。
