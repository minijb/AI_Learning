---
title: "平台抽象层与窗口系统"
updated: 2026-06-05
---

# 平台抽象层与窗口系统

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 5h
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要平台抽象层？

游戏引擎需要在多个平台上运行——Windows、macOS、Linux、iOS、Android、PlayStation、Xbox、Nintendo Switch。每个平台都有其独特的 API、窗口系统、文件路径格式、线程模型和内存布局。如果没有统一的抽象层，引擎代码将充斥着 `#ifdef _WIN32`、`#ifdef __linux__` 等条件编译，导致：

- **代码可读性极差**：业务逻辑被平台细节淹没
- **维护成本高昂**：修改一个功能需要在 N 个平台分支上同步
- **测试矩阵爆炸**：每新增一个平台，测试工作量倍增
- **新人上手困难**：需要同时掌握多个平台的原生 API

平台抽象层（Platform Abstraction Layer, PAL）的核心思想是：**将平台相关的代码收敛到少数几个接口文件，上层系统只调用统一的跨平台接口**。

> 以 Unreal Engine 的 `FPlatformMisc`、Godot 的 `OS` 单例、Bevy 的 `winit` 窗口抽象为例，顶级引擎无一例外都采用这种分层设计。

### 核心思想

PAL 的设计遵循以下原则：

1. **接口与实现分离**：定义纯虚接口类，每个平台提供具体实现
2. **工厂模式创建实例**：运行时（或编译时）决定实例化哪个平台的实现
3. **最小功能集**：只抽象引擎真正需要的功能，不试图封装整个操作系统
4. **零开销抽象**：热路径上的调用避免虚函数开销（可用 CRTP 或宏分发）
5. **头文件隔离**：平台相关的头文件（如 `<windows.h>`）不污染引擎公共头文件

典型的 PAL 架构层次：

```
┌─────────────────────────────────────────┐
│         引擎上层系统（渲染/物理/音频）        │
├─────────────────────────────────────────┤
│         平台抽象层接口（Platform.h）         │
├─────────────┬─────────────┬─────────────┤
│  Windows    │   Linux     │   macOS     │
│ Platform    │  Platform   │  Platform   │
│  Impl       │   Impl      │   Impl      │
└─────────────┴─────────────┴─────────────┘
```

### 窗口系统概述

窗口系统是图形应用与操作系统显示子系统之间的桥梁。不同平台的窗口系统差异巨大：

| 平台 | 原生窗口 API | 事件机制 | 特点 |
|------|-------------|---------|------|
| Windows | Win32 API (`CreateWindowEx`) | 消息队列 (`GetMessage`) | 成熟稳定，COM 组件多 |
| Linux | X11 / Wayland | XEvent / Wayland 协议 | 分裂严重，Wayland 是未来 |
| macOS | Cocoa (`NSWindow`) | RunLoop + NSEvent | 闭源，Objective-C++ 桥接 |
| iOS | UIKit (`UIWindow`) | RunLoop + UIEvent | 触摸为主，生命周期受系统管控 |
| Android | NativeActivity / ANativeWindow | ALooper + AInputQueue | 需处理 Activity 生命周期 |
| Console | 专用 SDK | 回调/轮询 | 无传统"窗口"概念，独占全屏 |

**GLFW 和 SDL** 是两个广泛使用的跨平台窗口库，它们封装了上述差异。对于自研引擎，通常有两种策略：

- **策略 A（推荐起步）**：使用 GLFW/SDL 处理窗口和输入，自己抽象文件系统、线程等
- **策略 B（大型引擎）**：完全自研窗口系统，直接调用原生 API 以获得最大控制

### 渲染上下文

渲染上下文是图形 API 与窗口系统之间的连接点：

- **OpenGL**：需要创建 GL Context（Windows 上通过 `wglCreateContext`，Linux 上通过 `glXCreateContext`），并通过 `SwapBuffers` 呈现
- **Vulkan**：通过 `vkCreateInstance` 创建实例，用 `VkSurfaceKHR` 绑定窗口（平台相关的 WSI 扩展：`VK_KHR_win32_surface`、`VK_KHR_xcb_surface` 等）
- **DirectX 11/12**：通过 DXGI 枚举适配器，创建 `IDXGISwapChain` 与窗口句柄绑定
- **Metal**：`CAMetalLayer` 绑定到 `NSView` / `UIView`

关键洞察：**渲染 API 的选择与窗口系统的选择是正交的**。一个好的 PAL 应该允许你在同一个窗口上切换 OpenGL / Vulkan / DirectX。

### 文件系统抽象

各平台文件系统差异：

| 特性 | Windows | Linux/macOS | 备注 |
|------|---------|-------------|------|
| 路径分隔符 | `\` 或 `/` | `/` | Windows 实际接受 `/` |
| 大小写敏感 | 不敏感（默认） | 敏感 | 导致跨平台 bug 的常见原因 |
| 当前工作目录 | 可执行文件位置 | 启动时 shell 的 cwd | 游戏引擎通常不使用相对 cwd |
| 用户数据目录 | `%APPDATA%` | `~/.config/` | 存档、配置存放位置 |
|  Bundle 资源 | 无 | macOS `.app/Contents/Resources` | 需特殊处理 |

### 线程与同步抽象

C++11 的 `<thread>`、`<mutex>`、`<condition_variable>`、`<atomic>` 已经提供了良好的跨平台基础，但引擎通常需要额外封装：

- **线程命名**：便于调试器识别（`SetThreadDescription` on Windows, `pthread_setname_np` on Linux）
- **线程亲和性**：将线程绑定到特定 CPU 核心，减少缓存抖动
- **读写锁**：C++17 才有 `std::shared_mutex`，引擎可能需要自研或封装
- **信号量**：C++20 才有 `std::counting_semaphore`
- **纤程/协程**：用户态调度，用于 Job System（第 14 章深入）

### 时间与时钟

游戏循环对时间精度要求极高：

- **高精度计时器**：Windows `QueryPerformanceCounter`（~1us 精度），Linux `clock_gettime(CLOCK_MONOTONIC)`
- **帧率计算**：瞬时 FPS vs 平均 FPS vs 滑动窗口平均
- **固定时间步**（Fixed Timestep）：物理模拟需要稳定的 `dt`，避免浮点误差累积和确定性问题
- **时间缩放**：游戏暂停（`timescale = 0`）、慢动作（`timescale = 0.5`）

### 动态库加载

引擎插件系统、渲染 API 动态切换、第三方 SDK 延迟加载都需要动态库支持：

| 操作 | Windows | Linux | macOS |
|------|---------|-------|-------|
| 加载 | `LoadLibraryA` | `dlopen` | `dlopen` |
| 获取符号 | `GetProcAddress` | `dlsym` | `dlsym` |
| 卸载 | `FreeLibrary` | `dlclose` | `dlclose` |
| 扩展名 | `.dll` | `.so` | `.dylib` |

### 跨平台编译系统

- **CMake**：事实标准，生成 Visual Studio / Xcode / Makefile / Ninja 工程
- **Premake**：基于 Lua 的配置脚本，生成速度快，适合大型项目（Used by GLFW, Bullet）
- **Bazel**：Google 出品，增量编译和远程缓存强大，学习曲线陡峭
- **GN + Ninja**：Chromium 使用，配置简洁，生成速度极快

---

## 2. 代码示例

### 2.1 平台抽象基类设计

```cpp
// Platform.h —— 平台抽象层公共接口
#pragma once

#include <cstdint>
#include <string>
#include <memory>
#include <vector>
#include <functional>

// ============================================================
// 前向声明：避免在公共头文件中包含平台相关头文件
// ============================================================
class Window;
class FileSystem;
class Thread;
class Mutex;
class ConditionVariable;
class DynamicLibrary;
class Timer;

// ============================================================
// 平台信息结构
// ============================================================
struct PlatformInfo {
    std::string osName;           // "Windows", "Linux", "macOS"
    std::string osVersion;        // 详细版本号
    uint32_t    cpuCoreCount;     // 逻辑核心数
    uint64_t    totalPhysicalRAM; // 物理内存总量（字节）
    bool        isDebugBuild;     // 是否为 Debug 构建
};

// ============================================================
// 窗口描述
// ============================================================
struct WindowDesc {
    std::string title = "Game Engine";
    int32_t     width = 1280;
    int32_t     height = 720;
    bool        fullscreen = false;
    bool        resizable = true;
    bool        vsync = true;
};

// ============================================================
// 文件信息
// ============================================================
struct FileInfo {
    std::string path;
    uint64_t    size = 0;
    bool        isDirectory = false;
    bool        isReadOnly = false;
    uint64_t    lastModifiedTime = 0; // Unix timestamp
};

// ============================================================
// 动态库句柄（不透明类型）
// ============================================================
using LibraryHandle = void*;
using ProcAddress = void(*)();

// ============================================================
// 平台抽象接口
// ============================================================
class IPlatform {
public:
    virtual ~IPlatform() = default;

    // ---- 平台信息 ------------------------------------------------
    virtual PlatformInfo GetInfo() const = 0;

    // ---- 窗口系统 ------------------------------------------------
    virtual std::unique_ptr<Window> CreateWindow(const WindowDesc& desc) = 0;

    // ---- 文件系统 ------------------------------------------------
    virtual std::unique_ptr<FileSystem> CreateFileSystem() = 0;

    // ---- 动态库 --------------------------------------------------
    virtual LibraryHandle LoadLibrary(const std::string& path) = 0;
    virtual void          UnloadLibrary(LibraryHandle handle) = 0;
    virtual ProcAddress   GetProcAddress(LibraryHandle handle, const std::string& name) = 0;

    // ---- 内存 ----------------------------------------------------
    virtual void* AlignedAlloc(size_t size, size_t alignment) = 0;
    virtual void  AlignedFree(void* ptr) = 0;

    // ---- 调试 ----------------------------------------------------
    virtual void DebugBreak() = 0;           // 触发调试器断点
    virtual void OutputDebugString(const std::string& msg) = 0;

    // ---- 单例访问 ------------------------------------------------
    static IPlatform* Get();
};

// ============================================================
// 窗口接口
// ============================================================
class Window {
public:
    using EventCallback = std::function<void(/* event type, data */)>;

    virtual ~Window() = default;

    virtual void Show() = 0;
    virtual void Hide() = 0;
    virtual void Close() = 0;
    virtual bool ShouldClose() const = 0;

    virtual void SetTitle(const std::string& title) = 0;
    virtual void SetSize(int32_t width, int32_t height) = 0;
    virtual void GetSize(int32_t& width, int32_t& height) const = 0;

    virtual void PollEvents() = 0;           // 处理窗口事件
    virtual void SwapBuffers() = 0;          // 交换前后缓冲

    // 获取原生窗口句柄（用于绑定渲染 API）
    virtual void* GetNativeHandle() const = 0;
    virtual void* GetNativeDisplay() const = 0; // Linux X11/Wayland 需要

    // 事件回调注册
    void SetEventCallback(const EventCallback& cb) { m_eventCallback = cb; }

protected:
    EventCallback m_eventCallback;
};

// ============================================================
// 文件系统接口
// ============================================================
class FileSystem {
public:
    virtual ~FileSystem() = default;

    // 路径操作
    virtual std::string GetExecutablePath() const = 0;
    virtual std::string GetUserDataDirectory() const = 0;
    virtual std::string GetEngineRootDirectory() const = 0;
    virtual std::string JoinPath(const std::string& a, const std::string& b) const = 0;
    virtual std::string GetFileName(const std::string& path) const = 0;
    virtual std::string GetDirectory(const std::string& path) const = 0;
    virtual std::string GetExtension(const std::string& path) const = 0;

    // 文件操作
    virtual bool   FileExists(const std::string& path) const = 0;
    virtual bool   DirectoryExists(const std::string& path) const = 0;
    virtual uint64_t GetFileSize(const std::string& path) const = 0;
    virtual bool   DeleteFile(const std::string& path) = 0;
    virtual bool   CreateDirectory(const std::string& path) = 0;
    virtual bool   DeleteDirectory(const std::string& path) = 0;

    // 读写
    virtual std::vector<uint8_t> ReadFileBinary(const std::string& path) = 0;
    virtual std::string          ReadFileText(const std::string& path) = 0;
    virtual bool                 WriteFileBinary(const std::string& path, const std::vector<uint8_t>& data) = 0;
    virtual bool                 WriteFileText(const std::string& path, const std::string& text) = 0;

    // 目录遍历
    virtual std::vector<FileInfo> ListDirectory(const std::string& path) = 0;
};

// ============================================================
// 高精度计时器
// ============================================================
class Timer {
public:
    virtual ~Timer() = default;

    // 重置计时器
    virtual void Reset() = 0;

    // 获取经过的秒数（从 Reset 或构造时开始）
    virtual double GetElapsedSeconds() const = 0;

    // 获取经过的毫秒数
    virtual double GetElapsedMilliseconds() const = 0;

    // 获取当前绝对时间（秒，单调递增）
    static double GetAbsoluteTime();

    // 获取当前绝对时间（微秒）
    static uint64_t GetAbsoluteTimeMicroseconds();
};

// ============================================================
// 时钟（游戏时间管理层）
// ============================================================
class Clock {
public:
    explicit Clock(double fixedTimestep = 1.0 / 60.0);

    // 每帧调用，传入真实经过时间
    void Tick(double realDeltaTime);

    // 获取缩放后的 DeltaTime（受 timeScale 影响）
    double GetDeltaTime() const { return m_deltaTime; }

    // 获取固定时间步长（用于物理更新）
    double GetFixedTimestep() const { return m_fixedTimestep; }

    // 获取自启动以来的总时间
    double GetTotalTime() const { return m_totalTime; }

    // 获取当前帧率
    double GetFPS() const { return m_fps; }

    // 时间缩放（0 = 暂停, 1 = 正常, 2 = 二倍速）
    void SetTimeScale(double scale) { m_timeScale = scale; }
    double GetTimeScale() const { return m_timeScale; }

    // 固定时间步更新回调（物理模拟用）
    using FixedUpdateCallback = std::function<void(double fixedDt)>;
    void SetFixedUpdateCallback(const FixedUpdateCallback& cb) { m_fixedCallback = cb; }

private:
    double m_deltaTime = 0.0;
    double m_fixedTimestep = 1.0 / 60.0;
    double m_totalTime = 0.0;
    double m_timeScale = 1.0;
    double m_fps = 0.0;

    double m_accumulator = 0.0;        // 固定时间步累积器
    double m_fpsAccumulator = 0.0;     // FPS 计算累积
    uint32_t m_fpsFrameCount = 0;      // FPS 帧计数

    FixedUpdateCallback m_fixedCallback;
};
```

### 2.2 Windows 平台实现

```cpp
// PlatformWindows.cpp —— Windows 平台实现
// 此文件是唯一包含 <windows.h> 的引擎源文件之一

#include "Platform.h"
#include <windows.h>
#include <shlobj.h>     // SHGetFolderPathA
#include <psapi.h>      // GetProcessMemoryInfo
#include <intrin.h>     // __cpuid
#include <DbgHelp.h>    // DebugBreak

#pragma comment(lib, "shell32.lib")

// ============================================================
// Windows 计时器实现
// ============================================================
class TimerWindows : public Timer {
public:
    TimerWindows() {
        QueryPerformanceFrequency(&m_frequency);
        Reset();
    }

    void Reset() override {
        QueryPerformanceCounter(&m_startTime);
    }

    double GetElapsedSeconds() const override {
        LARGE_INTEGER now;
        QueryPerformanceCounter(&now);
        return static_cast<double>(now.QuadPart - m_startTime.QuadPart) / m_frequency.QuadPart;
    }

    double GetElapsedMilliseconds() const override {
        return GetElapsedSeconds() * 1000.0;
    }

private:
    LARGE_INTEGER m_frequency;
    LARGE_INTEGER m_startTime;
};

// ============================================================
// Windows 文件系统实现
// ============================================================
class FileSystemWindows : public FileSystem {
public:
    std::string GetExecutablePath() const override {
        char buffer[MAX_PATH];
        DWORD len = GetModuleFileNameA(nullptr, buffer, MAX_PATH);
        return (len > 0 && len < MAX_PATH) ? std::string(buffer, len) : "";
    }

    std::string GetUserDataDirectory() const override {
        char path[MAX_PATH];
        if (SUCCEEDED(SHGetFolderPathA(nullptr, CSIDL_APPDATA, nullptr, 0, path))) {
            return std::string(path);
        }
        return "";
    }

    std::string GetEngineRootDirectory() const override {
        std::string exePath = GetExecutablePath();
        size_t lastSlash = exePath.find_last_of("\\/");
        if (lastSlash != std::string::npos) {
            return exePath.substr(0, lastSlash);
        }
        return ".";
    }

    std::string JoinPath(const std::string& a, const std::string& b) const override {
        if (a.empty()) return b;
        if (b.empty()) return a;
        char last = a.back();
        if (last == '\\' || last == '/') {
            return a + b;
        }
        return a + "\\" + b;
    }

    std::string GetFileName(const std::string& path) const override {
        size_t pos = path.find_last_of("\\/");
        return (pos != std::string::npos) ? path.substr(pos + 1) : path;
    }

    std::string GetDirectory(const std::string& path) const override {
        size_t pos = path.find_last_of("\\/");
        return (pos != std::string::npos) ? path.substr(0, pos) : ".";
    }

    std::string GetExtension(const std::string& path) const override {
        size_t pos = path.find_last_of('.');
        return (pos != std::string::npos) ? path.substr(pos) : "";
    }

    bool FileExists(const std::string& path) const override {
        DWORD attr = GetFileAttributesA(path.c_str());
        return (attr != INVALID_FILE_ATTRIBUTES) && !(attr & FILE_ATTRIBUTE_DIRECTORY);
    }

    bool DirectoryExists(const std::string& path) const override {
        DWORD attr = GetFileAttributesA(path.c_str());
        return (attr != INVALID_FILE_ATTRIBUTES) && (attr & FILE_ATTRIBUTE_DIRECTORY);
    }

    uint64_t GetFileSize(const std::string& path) const override {
        WIN32_FILE_ATTRIBUTE_DATA attr;
        if (GetFileAttributesExA(path.c_str(), GetFileExInfoStandard, &attr)) {
            LARGE_INTEGER size;
            size.HighPart = attr.nFileSizeHigh;
            size.LowPart = attr.nFileSizeLow;
            return size.QuadPart;
        }
        return 0;
    }

    bool DeleteFile(const std::string& path) override {
        return ::DeleteFileA(path.c_str()) != 0;
    }

    bool CreateDirectory(const std::string& path) override {
        return ::CreateDirectoryA(path.c_str(), nullptr) != 0 || GetLastError() == ERROR_ALREADY_EXISTS;
    }

    bool DeleteDirectory(const std::string& path) override {
        return RemoveDirectoryA(path.c_str()) != 0;
    }

    std::vector<uint8_t> ReadFileBinary(const std::string& path) override {
        std::vector<uint8_t> data;
        HANDLE hFile = CreateFileA(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                                    OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (hFile == INVALID_HANDLE_VALUE) return data;

        LARGE_INTEGER size;
        GetFileSizeEx(hFile, &size);
        data.resize(size.QuadPart);

        DWORD read = 0;
        ReadFile(hFile, data.data(), static_cast<DWORD>(size.QuadPart), &read, nullptr);
        CloseHandle(hFile);
        return data;
    }

    std::string ReadFileText(const std::string& path) override {
        auto binary = ReadFileBinary(path);
        return std::string(binary.begin(), binary.end());
    }

    bool WriteFileBinary(const std::string& path, const std::vector<uint8_t>& data) override {
        HANDLE hFile = CreateFileA(path.c_str(), GENERIC_WRITE, 0, nullptr,
                                    CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (hFile == INVALID_HANDLE_VALUE) return false;

        DWORD written = 0;
        BOOL ok = WriteFile(hFile, data.data(), static_cast<DWORD>(data.size()), &written, nullptr);
        CloseHandle(hFile);
        return ok && written == data.size();
    }

    bool WriteFileText(const std::string& path, const std::string& text) override {
        std::vector<uint8_t> data(text.begin(), text.end());
        return WriteFileBinary(path, data);
    }

    std::vector<FileInfo> ListDirectory(const std::string& path) override {
        std::vector<FileInfo> results;
        std::string searchPath = JoinPath(path, "*");

        WIN32_FIND_DATAA findData;
        HANDLE hFind = FindFirstFileA(searchPath.c_str(), &findData);
        if (hFind == INVALID_HANDLE_VALUE) return results;

        do {
            std::string name(findData.cFileName);
            if (name == "." || name == "..") continue;

            FileInfo info;
            info.path = JoinPath(path, name);
            info.isDirectory = (findData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
            info.isReadOnly = (findData.dwFileAttributes & FILE_ATTRIBUTE_READONLY) != 0;

            LARGE_INTEGER size;
            size.HighPart = findData.nFileSizeHigh;
            size.LowPart = findData.nFileSizeLow;
            info.size = size.QuadPart;

            // FILETIME to Unix timestamp
            ULARGE_INTEGER ull;
            ull.LowPart = findData.ftLastWriteTime.dwLowDateTime;
            ull.HighPart = findData.ftLastWriteTime.dwHighDateTime;
            info.lastModifiedTime = ull.QuadPart / 10000000ULL - 11644473600ULL;

            results.push_back(info);
        } while (FindNextFileA(hFind, &findData));

        FindClose(hFind);
        return results;
    }
};

// ============================================================
// Windows 平台主类
// ============================================================
class PlatformWindows : public IPlatform {
public:
    PlatformInfo GetInfo() const override {
        PlatformInfo info;
        info.osName = "Windows";

        // OS 版本
        OSVERSIONINFOEXA osvi = { sizeof(OSVERSIONINFOEXA) };
        #pragma warning(disable: 4996) // GetVersionEx is deprecated but still works
        GetVersionExA(reinterpret_cast<OSVERSIONINFOA*>(&osvi));
        info.osVersion = std::to_string(osvi.dwMajorVersion) + "." +
                         std::to_string(osvi.dwMinorVersion) + " Build " +
                         std::to_string(osvi.dwBuildNumber);

        // CPU 核心数
        SYSTEM_INFO sysInfo;
        GetSystemInfo(&sysInfo);
        info.cpuCoreCount = sysInfo.dwNumberOfProcessors;

        // 物理内存
        MEMORYSTATUSEX memStatus = { sizeof(MEMORYSTATUSEX) };
        GlobalMemoryStatusEx(&memStatus);
        info.totalPhysicalRAM = memStatus.ullTotalPhys;

        #ifdef _DEBUG
        info.isDebugBuild = true;
        #else
        info.isDebugBuild = false;
        #endif

        return info;
    }

    std::unique_ptr<Window> CreateWindow(const WindowDesc& desc) override;
    std::unique_ptr<FileSystem> CreateFileSystem() override {
        return std::make_unique<FileSystemWindows>();
    }

    LibraryHandle LoadLibrary(const std::string& path) override {
        return ::LoadLibraryA(path.c_str());
    }

    void UnloadLibrary(LibraryHandle handle) override {
        if (handle) ::FreeLibrary(static_cast<HMODULE>(handle));
    }

    ProcAddress GetProcAddress(LibraryHandle handle, const std::string& name) override {
        if (!handle) return nullptr;
        return reinterpret_cast<ProcAddress>(::GetProcAddress(static_cast<HMODULE>(handle), name.c_str()));
    }

    void* AlignedAlloc(size_t size, size_t alignment) override {
        return _aligned_malloc(size, alignment);
    }

    void AlignedFree(void* ptr) override {
        _aligned_free(ptr);
    }

    void DebugBreak() override {
        ::DebugBreak();
    }

    void OutputDebugString(const std::string& msg) override {
        ::OutputDebugStringA(msg.c_str());
    }
};
```

### 2.3 GLFW 窗口实现

```cpp
// WindowGLFW.cpp —— 基于 GLFW 的跨平台窗口实现

#include "Platform.h"
#include <GLFW/glfw3.h>
#include <iostream>

// ============================================================
// GLFW 窗口实现
// ============================================================
class WindowGLFW : public Window {
public:
    explicit WindowGLFW(const WindowDesc& desc) {
        if (!glfwInit()) {
            std::cerr << "Failed to initialize GLFW!" << std::endl;
            return;
        }

        // 设置 OpenGL 版本提示（可根据需要调整）
        glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 4);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 6);
        glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
        glfwWindowHint(GLFW_RESIZABLE, desc.resizable ? GLFW_TRUE : GLFW_FALSE);

        // 创建窗口
        GLFWmonitor* monitor = desc.fullscreen ? glfwGetPrimaryMonitor() : nullptr;
        m_window = glfwCreateWindow(desc.width, desc.height, desc.title.c_str(), monitor, nullptr);

        if (!m_window) {
            std::cerr << "Failed to create GLFW window!" << std::endl;
            glfwTerminate();
            return;
        }

        glfwMakeContextCurrent(m_window);
        glfwSwapInterval(desc.vsync ? 1 : 0);

        // 设置用户指针以便在回调中访问 this
        glfwSetWindowUserPointer(m_window, this);

        // 注册 GLFW 回调
        glfwSetWindowSizeCallback(m_window, OnResize);
        glfwSetWindowCloseCallback(m_window, OnClose);
        glfwSetKeyCallback(m_window, OnKey);
        glfwSetMouseButtonCallback(m_window, OnMouseButton);
        glfwSetCursorPosCallback(m_window, OnCursorPos);
        glfwSetScrollCallback(m_window, OnScroll);
        glfwSetFramebufferSizeCallback(m_window, OnFramebufferSize);
    }

    ~WindowGLFW() override {
        if (m_window) {
            glfwDestroyWindow(m_window);
            glfwTerminate();
        }
    }

    void Show() override {
        glfwShowWindow(m_window);
    }

    void Hide() override {
        glfwHideWindow(m_window);
    }

    void Close() override {
        glfwSetWindowShouldClose(m_window, GLFW_TRUE);
    }

    bool ShouldClose() const override {
        return glfwWindowShouldClose(m_window);
    }

    void SetTitle(const std::string& title) override {
        glfwSetWindowTitle(m_window, title.c_str());
    }

    void SetSize(int32_t width, int32_t height) override {
        glfwSetWindowSize(m_window, width, height);
    }

    void GetSize(int32_t& width, int32_t& height) const override {
        glfwGetWindowSize(m_window, &width, &height);
    }

    void PollEvents() override {
        glfwPollEvents();
    }

    void SwapBuffers() override {
        glfwSwapBuffers(m_window);
    }

    void* GetNativeHandle() const override {
    #ifdef _WIN32
        return glfwGetWin32Window(m_window);
    #elif defined(__linux__)
        return reinterpret_cast<void*>(glfwGetX11Window(m_window));
    #elif defined(__APPLE__)
        return glfwGetCocoaWindow(m_window);
    #else
        return nullptr;
    #endif
    }

    void* GetNativeDisplay() const override {
    #ifdef __linux__
        return glfwGetX11Display();
    #else
        return nullptr;
    #endif
    }

    // ---- GLFW 回调（静态方法，通过 user pointer 转发）---------------
    static void OnResize(GLFWwindow* w, int width, int height) {
        auto* self = static_cast<WindowGLFW*>(glfwGetWindowUserPointer(w));
        if (self && self->m_eventCallback) {
            // 可构造 ResizeEvent 并回调
        }
    }

    static void OnClose(GLFWwindow* w) {
        auto* self = static_cast<WindowGLFW*>(glfwGetWindowUserPointer(w));
        if (self) {
            glfwSetWindowShouldClose(w, GLFW_TRUE);
        }
    }

    static void OnKey(GLFWwindow* w, int key, int scancode, int action, int mods) {
        auto* self = static_cast<WindowGLFW*>(glfwGetWindowUserPointer(w));
        // 转发键盘事件...
    }

    static void OnMouseButton(GLFWwindow* w, int button, int action, int mods) {
        auto* self = static_cast<WindowGLFW*>(glfwGetWindowUserPointer(w));
        // 转发鼠标按钮事件...
    }

    static void OnCursorPos(GLFWwindow* w, double x, double y) {
        auto* self = static_cast<WindowGLFW*>(glfwGetWindowUserPointer(w));
        // 转发鼠标移动事件...
    }

    static void OnScroll(GLFWwindow* w, double xoffset, double yoffset) {
        auto* self = static_cast<WindowGLFW*>(glfwGetWindowUserPointer(w));
        // 转发滚轮事件...
    }

    static void OnFramebufferSize(GLFWwindow* w, int width, int height) {
        auto* self = static_cast<WindowGLFW*>(glfwGetWindowUserPointer(w));
        // 帧缓冲大小变化（DPI 缩放相关）...
    }

private:
    GLFWwindow* m_window = nullptr;
};

// 在 PlatformWindows 中实现 CreateWindow
std::unique_ptr<Window> PlatformWindows::CreateWindow(const WindowDesc& desc) {
    return std::make_unique<WindowGLFW>(desc);
}
```

### 2.4 Linux 平台实现

```cpp
// PlatformLinux.cpp —— Linux 平台实现

#include "Platform.h"
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <dirent.h>
#include <dlfcn.h>
#include <cstring>
#include <fstream>
#include <climits>
#include <ctime>

// Linux 计时器实现
class TimerLinux : public Timer {
public:
    TimerLinux() {
        Reset();
    }

    void Reset() override {
        clock_gettime(CLOCK_MONOTONIC, &m_startTime);
    }

    double GetElapsedSeconds() const override {
        timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        return (now.tv_sec - m_startTime.tv_sec) +
               (now.tv_nsec - m_startTime.tv_nsec) / 1e9;
    }

    double GetElapsedMilliseconds() const override {
        return GetElapsedSeconds() * 1000.0;
    }

private:
    timespec m_startTime;
};

// Linux 文件系统实现
class FileSystemLinux : public FileSystem {
public:
    std::string GetExecutablePath() const override {
        char buffer[PATH_MAX];
        ssize_t len = readlink("/proc/self/exe", buffer, PATH_MAX - 1);
        if (len != -1) {
            buffer[len] = '\0';
            return std::string(buffer);
        }
        return "";
    }

    std::string GetUserDataDirectory() const override {
        const char* home = getenv("HOME");
        if (home) {
            return std::string(home) + "/.config";
        }
        return "/tmp";
    }

    std::string GetEngineRootDirectory() const override {
        std::string exePath = GetExecutablePath();
        size_t lastSlash = exePath.find_last_of('/');
        if (lastSlash != std::string::npos) {
            return exePath.substr(0, lastSlash);
        }
        return ".";
    }

    std::string JoinPath(const std::string& a, const std::string& b) const override {
        if (a.empty()) return b;
        if (b.empty()) return a;
        if (a.back() == '/') return a + b;
        return a + "/" + b;
    }

    std::string GetFileName(const std::string& path) const override {
        size_t pos = path.find_last_of('/');
        return (pos != std::string::npos) ? path.substr(pos + 1) : path;
    }

    std::string GetDirectory(const std::string& path) const override {
        size_t pos = path.find_last_of('/');
        return (pos != std::string::npos) ? path.substr(0, pos) : ".";
    }

    std::string GetExtension(const std::string& path) const override {
        size_t pos = path.find_last_of('.');
        return (pos != std::string::npos) ? path.substr(pos) : "";
    }

    bool FileExists(const std::string& path) const override {
        struct stat st;
        return (stat(path.c_str(), &st) == 0) && S_ISREG(st.st_mode);
    }

    bool DirectoryExists(const std::string& path) const override {
        struct stat st;
        return (stat(path.c_str(), &st) == 0) && S_ISDIR(st.st_mode);
    }

    uint64_t GetFileSize(const std::string& path) const override {
        struct stat st;
        if (stat(path.c_str(), &st) == 0) {
            return static_cast<uint64_t>(st.st_size);
        }
        return 0;
    }

    bool DeleteFile(const std::string& path) override {
        return unlink(path.c_str()) == 0;
    }

    bool CreateDirectory(const std::string& path) override {
        return mkdir(path.c_str(), 0755) == 0 || errno == EEXIST;
    }

    bool DeleteDirectory(const std::string& path) override {
        return rmdir(path.c_str()) == 0;
    }

    std::vector<uint8_t> ReadFileBinary(const std::string& path) override {
        std::ifstream file(path, std::ios::binary | std::ios::ate);
        if (!file) return {};

        std::streamsize size = file.tellg();
        file.seekg(0, std::ios::beg);

        std::vector<uint8_t> buffer(size);
        if (file.read(reinterpret_cast<char*>(buffer.data()), size)) {
            return buffer;
        }
        return {};
    }

    std::string ReadFileText(const std::string& path) override {
        auto binary = ReadFileBinary(path);
        return std::string(binary.begin(), binary.end());
    }

    bool WriteFileBinary(const std::string& path, const std::vector<uint8_t>& data) override {
        std::ofstream file(path, std::ios::binary);
        if (!file) return false;
        file.write(reinterpret_cast<const char*>(data.data()), data.size());
        return file.good();
    }

    bool WriteFileText(const std::string& path, const std::string& text) override {
        std::ofstream file(path);
        if (!file) return false;
        file << text;
        return file.good();
    }

    std::vector<FileInfo> ListDirectory(const std::string& path) override {
        std::vector<FileInfo> results;
        DIR* dir = opendir(path.c_str());
        if (!dir) return results;

        struct dirent* entry;
        while ((entry = readdir(dir)) != nullptr) {
            std::string name(entry->d_name);
            if (name == "." || name == "..") continue;

            std::string fullPath = JoinPath(path, name);
            struct stat st;
            if (stat(fullPath.c_str(), &st) != 0) continue;

            FileInfo info;
            info.path = fullPath;
            info.isDirectory = S_ISDIR(st.st_mode);
            info.isReadOnly = (st.st_mode & S_IWUSR) == 0;
            info.size = static_cast<uint64_t>(st.st_size);
            info.lastModifiedTime = static_cast<uint64_t>(st.st_mtime);
            results.push_back(info);
        }

        closedir(dir);
        return results;
    }
};

// Linux 平台主类
class PlatformLinux : public IPlatform {
public:
    PlatformInfo GetInfo() const override {
        PlatformInfo info;
        info.osName = "Linux";

        // 读取 OS 版本
        FILE* f = fopen("/etc/os-release", "r");
        if (f) {
            char line[256];
            while (fgets(line, sizeof(line), f)) {
                if (strncmp(line, "PRETTY_NAME=", 12) == 0) {
                    info.osVersion = std::string(line + 13);
                    // 去除引号和换行
                    info.osVersion.erase(info.osVersion.find_last_of('"'));
                    info.osVersion.erase(0, info.osVersion.find_first_of('"') + 1);
                    break;
                }
            }
            fclose(f);
        }

        // CPU 核心数
        info.cpuCoreCount = static_cast<uint32_t>(sysconf(_SC_NPROCESSORS_ONLN));

        // 物理内存
        long pages = sysconf(_SC_PHYS_PAGES);
        long pageSize = sysconf(_SC_PAGE_SIZE);
        info.totalPhysicalRAM = static_cast<uint64_t>(pages) * static_cast<uint64_t>(pageSize);

        #ifdef _DEBUG
        info.isDebugBuild = true;
        #else
        info.isDebugBuild = false;
        #endif

        return info;
    }

    std::unique_ptr<Window> CreateWindow(const WindowDesc& desc) override {
        // GLFW 实现跨平台共享
        return std::make_unique<WindowGLFW>(desc);
    }

    std::unique_ptr<FileSystem> CreateFileSystem() override {
        return std::make_unique<FileSystemLinux>();
    }

    LibraryHandle LoadLibrary(const std::string& path) override {
        return dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    }

    void UnloadLibrary(LibraryHandle handle) override {
        if (handle) dlclose(handle);
    }

    ProcAddress GetProcAddress(LibraryHandle handle, const std::string& name) override {
        if (!handle) return nullptr;
        return reinterpret_cast<ProcAddress>(dlsym(handle, name.c_str()));
    }

    void* AlignedAlloc(size_t size, size_t alignment) override {
        void* ptr = nullptr;
        posix_memalign(&ptr, alignment, size);
        return ptr;
    }

    void AlignedFree(void* ptr) override {
        free(ptr);
    }

    void DebugBreak() override {
        #if defined(__x86_64__) || defined(__i386__)
        __asm__ volatile("int $0x03");
        #else
        raise(SIGTRAP);
        #endif
    }

    void OutputDebugString(const std::string& msg) override {
        // Linux 没有系统级调试输出，打印到 stderr
        std::cerr << "[DEBUG] " << msg << std::endl;
    }
};
```

### 2.5 时钟实现（平台无关）

```cpp
// Clock.cpp —— 游戏时钟实现（平台无关）

#include "Platform.h"
#include <cmath>

// ============================================================
// Timer 静态方法实现
// ============================================================
#ifdef _WIN32
#include <windows.h>
double Timer::GetAbsoluteTime() {
    LARGE_INTEGER freq, count;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&count);
    return static_cast<double>(count.QuadPart) / freq.QuadPart;
}
uint64_t Timer::GetAbsoluteTimeMicroseconds() {
    LARGE_INTEGER freq, count;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&count);
    return (count.QuadPart * 1000000ULL) / freq.QuadPart;
}
#else
#include <ctime>
double Timer::GetAbsoluteTime() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}
uint64_t Timer::GetAbsoluteTimeMicroseconds() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<uint64_t>(ts.tv_sec) * 1000000ULL + ts.tv_nsec / 1000;
}
#endif

// ============================================================
// Clock 实现
// ============================================================
Clock::Clock(double fixedTimestep)
    : m_fixedTimestep(fixedTimestep) {}

void Clock::Tick(double realDeltaTime) {
    // 防止断点或卡顿导致的时间跳跃
    const double MAX_DT = 0.25; // 最大 250ms
    if (realDeltaTime > MAX_DT) {
        realDeltaTime = MAX_DT;
    }

    // 应用时间缩放
    m_deltaTime = realDeltaTime * m_timeScale;
    m_totalTime += m_deltaTime;

    // ---- 固定时间步更新 ----------------------------------------
    // 使用 Glenn Fiedler 的 "Fix Your Timestep!" 方法
    m_accumulator += realDeltaTime; // 固定步长使用真实时间

    while (m_accumulator >= m_fixedTimestep) {
        if (m_fixedCallback) {
            m_fixedCallback(m_fixedTimestep);
        }
        m_accumulator -= m_fixedTimestep;
    }

    // ---- FPS 计算（滑动窗口平均）--------------------------------
    m_fpsAccumulator += realDeltaTime;
    m_fpsFrameCount++;

    if (m_fpsAccumulator >= 0.5) { // 每 0.5 秒更新一次 FPS
        m_fps = static_cast<double>(m_fpsFrameCount) / m_fpsAccumulator;
        m_fpsAccumulator = 0.0;
        m_fpsFrameCount = 0;
    }
}
```

### 2.6 平台工厂与主程序

```cpp
// PlatformFactory.cpp —— 平台实例创建

#include "Platform.h"

// 前向声明各平台实现
#ifdef _WIN32
    class PlatformWindows;
    using PlatformImpl = PlatformWindows;
#elif defined(__linux__)
    class PlatformLinux;
    using PlatformImpl = PlatformLinux;
#elif defined(__APPLE__)
    class PlatformMacOS;
    using PlatformImpl = PlatformMacOS;
#else
    #error "Unsupported platform"
#endif

// 单例实现
static std::unique_ptr<IPlatform> g_platform;

IPlatform* IPlatform::Get() {
    if (!g_platform) {
        g_platform = std::make_unique<PlatformImpl>();
    }
    return g_platform.get();
}
```

```cpp
// main.cpp —— 使用示例

#include "Platform.h"
#include <iostream>
#include <memory>

int main() {
    // 获取平台实例
    IPlatform* platform = IPlatform::Get();

    // 打印平台信息
    PlatformInfo info = platform->GetInfo();
    std::cout << "OS: " << info.osName << " " << info.osVersion << std::endl;
    std::cout << "CPU Cores: " << info.cpuCoreCount << std::endl;
    std::cout << "RAM: " << (info.totalPhysicalRAM / (1024 * 1024 * 1024)) << " GB" << std::endl;

    // 创建文件系统
    auto fs = platform->CreateFileSystem();
    std::cout << "Executable: " << fs->GetExecutablePath() << std::endl;
    std::cout << "Engine Root: " << fs->GetEngineRootDirectory() << std::endl;

    // 创建窗口
    WindowDesc desc;
    desc.title = "Game Engine - Platform Abstraction Demo";
    desc.width = 1280;
    desc.height = 720;
    desc.vsync = true;

    auto window = platform->CreateWindow(desc);
    if (!window) {
        std::cerr << "Failed to create window!" << std::endl;
        return -1;
    }

    window->Show();

    // 创建游戏时钟（固定 60Hz 物理更新）
    Clock clock(1.0 / 60.0);
    clock.SetFixedUpdateCallback([](double dt) {
        // 物理更新在这里执行
        // 每帧以固定 16.67ms 调用
    });

    // 主循环
    double lastTime = Timer::GetAbsoluteTime();
    while (!window->ShouldClose()) {
        double currentTime = Timer::GetAbsoluteTime();
        double deltaTime = currentTime - lastTime;
        lastTime = currentTime;

        // 更新时钟
        clock.Tick(deltaTime);

        // 处理窗口事件
        window->PollEvents();

        // ---- 游戏逻辑更新 ----------------------------------------
        // 使用 clock.GetDeltaTime() 进行帧率无关的更新

        // ---- 渲染 ------------------------------------------------
        // glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        // ... 渲染代码 ...

        window->SwapBuffers();

        // 打印 FPS（调试用）
        static double fpsTimer = 0.0;
        fpsTimer += deltaTime;
        if (fpsTimer >= 1.0) {
            std::cout << "FPS: " << clock.GetFPS()
                      << " | Delta: " << (clock.GetDeltaTime() * 1000.0) << "ms" << std::endl;
            fpsTimer = 0.0;
        }
    }

    return 0;
}
```

### 2.7 CMake 构建配置

```cmake
# CMakeLists.txt —— 跨平台构建配置

cmake_minimum_required(VERSION 3.16)
project(GameEnginePlatform VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ============================================================
# 源文件分组
# ============================================================
set(COMMON_SOURCES
    src/Platform.h
    src/Clock.cpp
    src/PlatformFactory.cpp
    src/WindowGLFW.cpp
)

set(WINDOWS_SOURCES
    src/PlatformWindows.cpp
)

set(LINUX_SOURCES
    src/PlatformLinux.cpp
)

# ============================================================
# 平台检测与源文件选择
# ============================================================
if(WIN32)
    list(APPEND PLATFORM_SOURCES ${WINDOWS_SOURCES})
    add_definitions(-DNOMINMAX -DWIN32_LEAN_AND_MEAN)
elseif(UNIX AND NOT APPLE)
    list(APPEND PLATFORM_SOURCES ${LINUX_SOURCES})
elseif(APPLE)
    # macOS 实现（类似 Linux，使用 Cocoa 窗口）
endif()

# ============================================================
# 可执行文件
# ============================================================
add_executable(PlatformDemo
    src/main.cpp
    ${COMMON_SOURCES}
    ${PLATFORM_SOURCES}
)

target_include_directories(PlatformDemo PRIVATE src)

# ============================================================
# GLFW
# ============================================================
include(FetchContent)
FetchContent_Declare(
    glfw
    GIT_REPOSITORY https://github.com/glfw/glfw.git
    GIT_TAG        3.3.9
)
FetchContent_MakeAvailable(glfw)

target_link_libraries(PlatformDemo PRIVATE glfw)

# ============================================================
# 平台特定链接库
# ============================================================
if(WIN32)
    target_link_libraries(PlatformDemo PRIVATE
        shell32
        psapi
        DbgHelp
    )
elseif(UNIX)
    target_link_libraries(PlatformDemo PRIVATE
        pthread
        dl
    )
endif()

# ============================================================
# OpenGL（示例渲染）
# ============================================================
find_package(OpenGL REQUIRED)
target_link_libraries(PlatformDemo PRIVATE OpenGL::GL)
```

**运行方式:**

```bash
# 1. 克隆或创建项目目录，将上述代码放入对应文件

# 2. 构建
mkdir build && cd build
cmake ..
cmake --build . --config Release

# 3. 运行
./PlatformDemo        # Linux/macOS
PlatformDemo.exe      # Windows
```

**预期输出:**

```
OS: Windows 10.0 Build 22631
CPU Cores: 16
RAM: 32 GB
Executable: D:\GameEngine\build\Release\PlatformDemo.exe
Engine Root: D:\GameEngine\build\Release
FPS: 60.0023 | Delta: 16.665ms
FPS: 60.0011 | Delta: 16.666ms
...
```

---

## 3. 练习

### 练习 1：实现 macOS 平台层

基于 Windows 和 Linux 的实现，完成 macOS 平台层 (`PlatformMacOS.cpp`)。需要实现：

- `GetExecutablePath()`：使用 `_NSGetExecutablePath`
- `GetUserDataDirectory()`：使用 `NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory)`
- `DebugBreak()`：使用 `__builtin_debugtrap()` 或 `raise(SIGTRAP)`
- 注意 macOS 的文件系统默认大小写不敏感（但保留大小写），与 Linux 不同

### 练习 2：添加线程抽象封装

在 PAL 中增加线程相关接口：

```cpp
class IThread {
public:
    virtual void Start(std::function<void()> entryPoint) = 0;
    virtual void Join() = 0;
    virtual void SetName(const std::string& name) = 0;
    virtual void SetAffinity(uint64_t coreMask) = 0;
    virtual uint32_t GetID() const = 0;
};
```

实现 Windows 版本（`CreateThread` + `SetThreadAffinityMask`）和 Linux 版本（`pthread_create` + `pthread_setaffinity_np`）。注意 macOS 不支持线程亲和性设置。

### 练习 3（可选）：自研 Win32 窗口系统

不依赖 GLFW，直接使用 Win32 API 创建窗口并处理消息循环。要求：

- 注册窗口类 (`RegisterClassEx`)
- 创建窗口 (`CreateWindowEx`)
- 实现消息泵 (`GetMessage` / `PeekMessage` / `DispatchMessage`)
- 处理 `WM_SIZE`、`WM_CLOSE`、`WM_KEYDOWN`、`WM_MOUSEMOVE`
- 使用 `wglCreateContext` 创建 OpenGL 上下文并绑定

这是理解"GLFW 到底做了什么"的最佳方式。

---

## 4. 扩展阅读

### 必读文章

- Glenn Fiedler, ["Fix Your Timestep!"](https://gafferongames.com/post/fix_your_timestep/) —— 游戏循环与固定时间步的权威文章
- Mike Acton, ["Data-Oriented Design and C++"](https://www.youtube.com/watch?v=rX0ItVEVjHc) —— 理解为什么引擎要避免虚函数热路径
- Handmade Hero 系列 —— Casey Muratori 从零手写 Windows 平台层，每日直播编码

### 引擎源码参考

| 引擎 | 平台层位置 | 特点 |
|------|-----------|------|
| Unreal Engine | `Runtime/Core/Public/HAL/` | `FPlatformMisc`, `FPlatformFileManager`，宏分发为主 |
| Godot | `platform/` 目录 | 每个平台一个子目录，OS 单例模式 |
| Bevy | `crates/bevy_window/` | Rust + winit，现代设计 |
| O3DE | `Code/Framework/AzCore/Platform/` | 复杂的 Gems 插件系统 |
| bgfx | `src/` 下各平台文件 | 极简设计，渲染 API 也一并抽象 |

### 窗口库对比

| 库 | 优点 | 缺点 | 适用场景 |
|----|------|------|---------|
| **GLFW** | 轻量、文档好、OpenGL/Vulkan 友好 | 功能较基础 | 学习、中小型引擎 |
| **SDL2** | 功能全（窗口+输入+音频+线程+文件） | 较重、API 较老 | 需要一站式解决方案 |
| **SDL3** | 现代化 API、更好的 GPU 支持 | 较新，生态还在迁移 | 新项目 |
| **SFML** | C++ 风格、易学 | 功能有限、性能一般 | 2D 游戏、学习 |
| **自研** | 完全可控、零依赖 | 工作量大 | 商业引擎、特殊需求 |

### 工具与文档

- [CMake 官方文档](https://cmake.org/documentation/)
- [GLFW 文档](https://www.glfw.org/documentation.html)
- [Vulkan WSI 规范](https://www.khronos.org/registry/vulkan/specs/1.3-extensions/html/vkspec.html#wsi) —— 理解各平台 Surface 创建
- [Microsoft Docs: Windowing](https://docs.microsoft.com/en-us/windows/win32/winmsg/windowing)

---

## 常见陷阱

1. **`<windows.h>` 污染**：`windows.h` 定义了大量宏（如 `min`/`max`、`CreateWindow` 等），与 C++ 标准库冲突。务必在包含前定义 `NOMINMAX` 和 `WIN32_LEAN_AND_MEAN`，或将平台实现编译为独立的 `.cpp` 文件。

2. **路径分隔符混用**：Windows API 实际上接受 `/` 作为路径分隔符。建议在引擎内部统一使用 `/`，仅在调用原生 API 前转换为 `\`。

3. **大小写敏感假设**：Linux 文件系统大小写敏感，Windows/macOS 默认不敏感。不要在代码中依赖 `"Shader.vert"` 和 `"shader.vert"` 指向不同文件。

4. **当前工作目录不可靠**：用户可能从任意目录启动游戏。永远不要用相对路径假设资源位置。使用 `GetExecutablePath()` 或 `GetEngineRootDirectory()` 作为基准。

5. **计时器精度陷阱**：
   - 不要用 `std::chrono::system_clock` 做游戏计时（可能被 NTP 调整）
   - 始终使用单调时钟（`QueryPerformanceCounter` / `CLOCK_MONOTONIC`）
   - 注意多核 CPU 上 `rdtsc` 指令不同步的问题，优先使用 OS 提供的 API

6. **GLFW 与 Glad/GL3W 的加载顺序**：必须在 `glfwMakeContextCurrent` 之后加载 OpenGL 函数指针，否则会导致段错误。

7. **Linux 显示服务器分裂**：X11 和 Wayland 的窗口句柄获取方式不同。GLFW 3.4+ 支持 Wayland，但 Vulkan Surface 创建需要不同的扩展（`VK_KHR_wayland_surface` vs `VK_KHR_xcb_surface`）。

8. **动态库路径**：Linux 需要 `LD_LIBRARY_PATH` 或 `rpath` 设置才能找到 `.so`，Windows 则在 `PATH` 和可执行文件同级目录搜索。部署时务必处理依赖库复制。

9. **DebugBreak 在 Release 构建中**：`DebugBreak()` 在 Release 构建中应优雅降级（如打印日志后退出），而不是真的触发断点导致崩溃。

10. **固定时间步的插值**：物理以固定步长更新，但渲染帧率不固定。渲染时应对物理状态进行插值，否则会出现抖动。参考 Glenn Fiedler 文章中的 `State previous; State current; double t;` 插值方法。
