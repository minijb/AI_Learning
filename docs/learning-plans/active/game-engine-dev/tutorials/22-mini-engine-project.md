# 综合实践：迷你游戏引擎构建

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 20h
> 前置知识: 全部前21章

---

## 1. 概念讲解

### 为什么需要这个？

在前17章中，我们分别学习了游戏引擎的各个子系统：数学基础、渲染管线、物理模拟、动画系统、音频处理、ECS架构、资源管理、输入系统等等。然而，知道每个零件如何工作，与能够把它们组装成一台运转的机器，是完全不同的两件事。

本章的目标是构建一个名为 **MiniEngine** 的完整3D游戏引擎原型。这不是一个玩具项目——它将具备生产级引擎的核心骨架，包括：

- 模块化的架构设计，各子系统通过清晰接口协作
- 基于OpenGL的现代渲染管线（PBR光照、阴影映射）
- 完整的ECS架构，支持组件化游戏逻辑
- 刚体物理系统（AABB碰撞检测 + 重力模拟）
- 骨骼动画播放
- 3D空间音频
- 资源管理器（异步加载、引用计数）
- ImGui调试面板和内置Profiler

通过这个综合项目，你将理解：
1. **子系统如何交互**：渲染器如何查询ECS中的Renderable组件？物理系统如何更新Transform？
2. **数据流设计**：游戏循环中数据如何在各阶段流动？
3. **性能权衡**：何时使用缓存？如何减少跨系统数据拷贝？
4. **工程实践**：CMake构建、跨平台抽象、版本控制策略

### 核心思想

#### 1.1 分层架构

MiniEngine采用经典的分层架构：

```
┌─────────────────────────────────────────┐
│           Application Layer              │  ← 游戏逻辑、场景脚本
├─────────────────────────────────────────┤
│           Gameplay Systems               │  ← ECS、输入映射、动画状态机
├─────────────────────────────────────────┤
│           Middleware Layer               │  ← 渲染器、物理、音频、资源管理
├─────────────────────────────────────────┤
│           Core Layer                     │  ← 数学库、内存分配器、平台抽象、日志
├─────────────────────────────────────────┤
│           Platform Layer                 │  ← OS API、OpenGL、窗口系统
└─────────────────────────────────────────┘
```

**依赖规则**：上层可以调用下层，下层绝不能调用上层。同层之间尽量减少直接依赖，通过事件或接口通信。

#### 1.2 游戏循环架构

采用**固定时间步更新 + 可变渲染**模式：

```
while (running) {
    // 1. 处理输入（尽可能频繁）
    ProcessInput();

    // 2. 固定步长更新（物理、游戏逻辑）
    accumulator += deltaTime;
    while (accumulator >= FIXED_TIMESTEP) {
        FixedUpdate(FIXED_TIMESTEP);  // 物理、动画更新
        accumulator -= FIXED_TIMESTEP;
    }

    // 3. 可变帧率渲染
    interpolation = accumulator / FIXED_TIMESTEP;
    Render(interpolation);
}
```

这种分离确保物理模拟的确定性（无论帧率如何，物理结果一致），同时允许渲染以最高帧率运行。

#### 1.3 ECS设计哲学

ECS（Entity-Component-System）是本引擎的核心架构模式：

- **Entity**：只是一个ID，没有任何数据和行为
- **Component**：纯数据（POD），描述实体的某个方面
- **System**：处理具有特定组件组合的实体的逻辑

ECS的优势在于**缓存友好**和**组合优于继承**。所有同类型组件连续存储，System遍历时CPU缓存命中率高。

#### 1.4 资源管理策略

采用**引用计数 + 延迟加载**策略：

- 资源（纹理、模型、着色器）由`ResourceManager`统一管理
- 使用`ResourceHandle<T>`智能指针，自动管理生命周期
- 支持异步加载，加载期间使用占位资源
- 热重载：开发模式下文件变更自动重新加载

---

## 2. 代码示例

### 2.1 项目结构

```
MiniEngine/
├── CMakeLists.txt
├── third_party/
│   ├── glad/              ← OpenGL loader
│   ├── glfw/              ← 窗口和输入
│   ├── glm/               ← 数学库（可选，我们自研）
│   ├── stb/               ← 图像加载
│   ├── miniaudio/         ← 音频引擎
│   ├── imgui/             ← 调试UI
│   ├── cgltf/             ← glTF解析
│   └── spdlog/            ← 日志库
├── engine/
│   ├── CMakeLists.txt
│   ├── core/
│   │   ├── include/
│   │   │   ├── MiniEngine/Core/Types.hpp
│   │   │   ├── MiniEngine/Core/Math.hpp
│   │   │   ├── MiniEngine/Core/Memory.hpp
│   │   │   ├── MiniEngine/Core/Platform.hpp
│   │   │   ├── MiniEngine/Core/Log.hpp
│   │   │   └── MiniEngine/Core/Profiler.hpp
│   │   └── src/
│   │       ├── Math.cpp
│   │       ├── Memory.cpp
│   │       ├── Platform.cpp
│   │       └── Log.cpp
│   ├── render/
│   │   ├── include/
│   │   │   ├── MiniEngine/Render/Renderer.hpp
│   │   │   ├── MiniEngine/Render/Shader.hpp
│   │   │   ├── MiniEngine/Render/Texture.hpp
│   │   │   ├── MiniEngine/Render/Mesh.hpp
│   │   │   ├── MiniEngine/Render/Material.hpp
│   │   │   ├── MiniEngine/Render/Camera.hpp
│   │   │   ├── MiniEngine/Render/Light.hpp
│   │   │   └── MiniEngine/Render/Framebuffer.hpp
│   │   └── src/
│   │       ├── Renderer.cpp
│   │       ├── Shader.cpp
│   │       ├── Texture.cpp
│   │       ├── Mesh.cpp
│   │       └── Camera.cpp
│   ├── physics/
│   │   ├── include/
│   │   │   ├── MiniEngine/Physics/PhysicsWorld.hpp
│   │   │   ├── MiniEngine/Physics/RigidBody.hpp
│   │   │   └── MiniEngine/Physics/Collision.hpp
│   │   └── src/
│   │       ├── PhysicsWorld.cpp
│   │       └── Collision.cpp
│   ├── animation/
│   │   ├── include/
│   │   │   ├── MiniEngine/Animation/Animation.hpp
│   │   │   ├── MiniEngine/Animation/Skeleton.hpp
│   │   │   └── MiniEngine/Animation/Animator.hpp
│   │   └── src/
│   │       ├── Animation.cpp
│   │       └── Animator.cpp
│   ├── audio/
│   │   ├── include/
│   │   │   ├── MiniEngine/Audio/AudioEngine.hpp
│   │   │   └── MiniEngine/Audio/AudioSource.hpp
│   │   └── src/
│   │       └── AudioEngine.cpp
│   ├── ecs/
│   │   ├── include/
│   │   │   ├── MiniEngine/ECS/World.hpp
│   │   │   ├── MiniEngine/ECS/Entity.hpp
│   │   │   ├── MiniEngine/ECS/Component.hpp
│   │   │   ├── MiniEngine/ECS/System.hpp
│   │   │   └── MiniEngine/ECS/Components.hpp
│   │   └── src/
│   │       ├── World.cpp
│   │       └── System.cpp
│   ├── resources/
│   │   ├── include/
│   │   │   ├── MiniEngine/Resources/ResourceManager.hpp
│   │   │   ├── MiniEngine/Resources/ResourceHandle.hpp
│   │   │   └── MiniEngine/Resources/ModelLoader.hpp
│   │   └── src/
│   │       ├── ResourceManager.cpp
│   │       └── ModelLoader.cpp
│   └── app/
│       ├── include/
│       │   ├── MiniEngine/App/Application.hpp
│       │   ├── MiniEngine/App/Input.hpp
│       │   └── MiniEngine/App/Window.hpp
│       └── src/
│           ├── Application.cpp
│           ├── Input.cpp
│           └── Window.cpp
├── editor/
│   ├── CMakeLists.txt
│   └── src/
│       └── Editor.cpp       ← 编辑器入口，链接engine
└── game/
    ├── CMakeLists.txt
    ├── assets/
    │   ├── shaders/
    │   ├── textures/
    │   ├── models/
    │   └── scenes/
    └── src/
        └── Main.cpp         ← 游戏入口
```

### 2.2 顶层 CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.16)
project(MiniEngine VERSION 0.1.0 LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# 编译选项
if(MSVC)
    add_compile_options(/W4 /WX- /permissive- /Zc:__cplusplus)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 第三方库
add_subdirectory(third_party/glad)
add_subdirectory(third_party/glfw)
add_subdirectory(third_party/imgui)
add_subdirectory(third_party/spdlog)

# 引擎核心
add_subdirectory(engine)

# 编辑器
add_subdirectory(editor)

# 示例游戏
add_subdirectory(game)
```

### 2.3 Core 层

#### Types.hpp — 基础类型定义

```cpp
#pragma once
#include <cstdint>
#include <cstddef>
#include <typeindex>
#include <limits>

namespace MiniEngine {

using u8  = uint8_t;
using u16 = uint16_t;
using u32 = uint32_t;
using u64 = uint64_t;
using i8  = int8_t;
using i16 = int16_t;
using i32 = int32_t;
using i64 = int64_t;
using f32 = float;
using f64 = double;

// Entity ID 类型
using EntityID = u32;
static constexpr EntityID INVALID_ENTITY = std::numeric_limits<EntityID>::max();

// Component 类型 ID
using ComponentTypeID = u32;

// 时间类型（秒）
using Time = f64;

} // namespace MiniEngine
```

#### Math.hpp — 自研数学库

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include <cmath>

namespace MiniEngine::Math {

// ─── Vec2 ───
struct Vec2 {
    f32 x, y;
    Vec2() : x(0), y(0) {}
    Vec2(f32 v) : x(v), y(v) {}
    Vec2(f32 x_, f32 y_) : x(x_), y(y_) {}

    Vec2 operator+(const Vec2& o) const { return Vec2(x + o.x, y + o.y); }
    Vec2 operator-(const Vec2& o) const { return Vec2(x - o.x, y - o.y); }
    Vec2 operator*(f32 s) const { return Vec2(x * s, y * s); }
    Vec2 operator/(f32 s) const { return Vec2(x / s, y / s); }
    Vec2& operator+=(const Vec2& o) { x += o.x; y += o.y; return *this; }

    f32 LengthSq() const { return x * x + y * y; }
    f32 Length() const { return std::sqrt(LengthSq()); }
    Vec2 Normalized() const { f32 len = Length(); return len > 0 ? *this / len : Vec2(); }
};

inline Vec2 operator*(f32 s, const Vec2& v) { return v * s; }

// ─── Vec3 ───
struct Vec3 {
    f32 x, y, z;
    Vec3() : x(0), y(0), z(0) {}
    Vec3(f32 v) : x(v), y(v), z(v) {}
    Vec3(f32 x_, f32 y_, f32 z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x - o.x, y - o.y, z - o.z); }
    Vec3 operator*(f32 s) const { return Vec3(x * s, y * s, z * s); }
    Vec3 operator/(f32 s) const { return Vec3(x / s, y / s, z / s); }
    Vec3 operator*(const Vec3& o) const { return Vec3(x * o.x, y * o.y, z * o.z); }
    Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
    Vec3 operator-() const { return Vec3(-x, -y, -z); }

    f32 LengthSq() const { return x * x + y * y + z * z; }
    f32 Length() const { return std::sqrt(LengthSq()); }
    Vec3 Normalized() const { f32 len = Length(); return len > 0 ? *this / len : Vec3(); }

    static f32 Dot(const Vec3& a, const Vec3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
    static Vec3 Cross(const Vec3& a, const Vec3& b) {
        return Vec3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
    }
    static Vec3 Lerp(const Vec3& a, const Vec3& b, f32 t) {
        return a + (b - a) * t;
    }
};

inline Vec3 operator*(f32 s, const Vec3& v) { return v * s; }

// ─── Vec4 ───
struct Vec4 {
    f32 x, y, z, w;
    Vec4() : x(0), y(0), z(0), w(0) {}
    Vec4(f32 x_, f32 y_, f32 z_, f32 w_) : x(x_), y(y_), z(z_), w(w_) {}
    Vec4(const Vec3& v, f32 w_) : x(v.x), y(v.y), z(v.z), w(w_) {}

    Vec3 xyz() const { return Vec3(x, y, z); }
};

// ─── Mat4 ───
struct Mat4 {
    f32 m[16];

    Mat4() { *this = Identity(); }

    static Mat4 Identity() {
        Mat4 r;
        for (int i = 0; i < 16; ++i) r.m[i] = 0;
        r.m[0] = r.m[5] = r.m[10] = r.m[15] = 1.0f;
        return r;
    }

    static Mat4 Translate(const Vec3& t) {
        Mat4 r = Identity();
        r.m[12] = t.x; r.m[13] = t.y; r.m[14] = t.z;
        return r;
    }

    static Mat4 Scale(const Vec3& s) {
        Mat4 r = Identity();
        r.m[0] = s.x; r.m[5] = s.y; r.m[10] = s.z;
        return r;
    }

    static Mat4 RotateY(f32 angle) {
        Mat4 r = Identity();
        f32 c = std::cos(angle), s = std::sin(angle);
        r.m[0] = c;  r.m[2] = s;
        r.m[8] = -s; r.m[10] = c;
        return r;
    }

    static Mat4 RotateX(f32 angle) {
        Mat4 r = Identity();
        f32 c = std::cos(angle), s = std::sin(angle);
        r.m[5] = c;  r.m[6] = -s;
        r.m[9] = s;  r.m[10] = c;
        return r;
    }

    static Mat4 Perspective(f32 fov, f32 aspect, f32 near, f32 far) {
        Mat4 r;
        for (int i = 0; i < 16; ++i) r.m[i] = 0;
        f32 tanHalfFov = std::tan(fov * 0.5f);
        r.m[0] = 1.0f / (aspect * tanHalfFov);
        r.m[5] = 1.0f / tanHalfFov;
        r.m[10] = -(far + near) / (far - near);
        r.m[11] = -1.0f;
        r.m[14] = -(2.0f * far * near) / (far - near);
        return r;
    }

    static Mat4 LookAt(const Vec3& eye, const Vec3& center, const Vec3& up) {
        Vec3 f = (center - eye).Normalized();
        Vec3 s = Vec3::Cross(f, up).Normalized();
        Vec3 u = Vec3::Cross(s, f);

        Mat4 r = Identity();
        r.m[0] = s.x;  r.m[4] = s.y;  r.m[8] = s.z;
        r.m[1] = u.x;  r.m[5] = u.y;  r.m[9] = u.z;
        r.m[2] = -f.x; r.m[6] = -f.y; r.m[10] = -f.z;
        r.m[12] = -Vec3::Dot(s, eye);
        r.m[13] = -Vec3::Dot(u, eye);
        r.m[14] = Vec3::Dot(f, eye);
        return r;
    }

    Mat4 operator*(const Mat4& o) const {
        Mat4 r;
        for (int row = 0; row < 4; ++row) {
            for (int col = 0; col < 4; ++col) {
                r.m[row * 4 + col] =
                    m[row * 4 + 0] * o.m[0 * 4 + col] +
                    m[row * 4 + 1] * o.m[1 * 4 + col] +
                    m[row * 4 + 2] * o.m[2 * 4 + col] +
                    m[row * 4 + 3] * o.m[3 * 4 + col];
            }
        }
        return r;
    }

    Vec3 TransformPoint(const Vec3& p) const {
        Vec4 v(p.x, p.y, p.z, 1.0f);
        f32 x = m[0]*v.x + m[4]*v.y + m[8]*v.z + m[12]*v.w;
        f32 y = m[1]*v.x + m[5]*v.y + m[9]*v.z + m[13]*v.w;
        f32 z = m[2]*v.x + m[6]*v.y + m[10]*v.z + m[14]*v.w;
        f32 w = m[3]*v.x + m[7]*v.y + m[11]*v.z + m[15]*v.w;
        return Vec3(x/w, y/w, z/w);
    }

    Vec3 TransformVector(const Vec3& v) const {
        f32 x = m[0]*v.x + m[4]*v.y + m[8]*v.z;
        f32 y = m[1]*v.x + m[5]*v.y + m[9]*v.z;
        f32 z = m[2]*v.x + m[6]*v.y + m[10]*v.z;
        return Vec3(x, y, z);
    }

    Mat4 Transposed() const {
        Mat4 r;
        for (int i = 0; i < 4; ++i)
            for (int j = 0; j < 4; ++j)
                r.m[i*4+j] = m[j*4+i];
        return r;
    }
};

// ─── Quaternion ───
struct Quat {
    f32 x, y, z, w;
    Quat() : x(0), y(0), z(0), w(1) {}
    Quat(f32 x_, f32 y_, f32 z_, f32 w_) : x(x_), y(y_), z(z_), w(w_) {}

    static Quat FromAxisAngle(const Vec3& axis, f32 angle) {
        f32 half = angle * 0.5f;
        f32 s = std::sin(half);
        return Quat(axis.x * s, axis.y * s, axis.z * s, std::cos(half));
    }

    Quat operator*(const Quat& o) const {
        return Quat(
            w*o.x + x*o.w + y*o.z - z*o.y,
            w*o.y - x*o.z + y*o.w + z*o.x,
            w*o.z + x*o.y - y*o.x + z*o.w,
            w*o.w - x*o.x - y*o.y - z*o.z
        );
    }

    Quat Normalized() const {
        f32 len = std::sqrt(x*x + y*y + z*z + w*w);
        return len > 0 ? Quat(x/len, y/len, z/len, w/len) : Quat();
    }

    Mat4 ToMat4() const {
        Mat4 r = Mat4::Identity();
        f32 xx = x*x, yy = y*y, zz = z*z;
        f32 xy = x*y, xz = x*z, yz = y*z;
        f32 wx = w*x, wy = w*y, wz = w*z;
        r.m[0] = 1 - 2*(yy + zz); r.m[4] = 2*(xy - wz);     r.m[8]  = 2*(xz + wy);
        r.m[1] = 2*(xy + wz);     r.m[5] = 1 - 2*(xx + zz); r.m[9]  = 2*(yz - wx);
        r.m[2] = 2*(xz - wy);     r.m[6] = 2*(yz + wx);     r.m[10] = 1 - 2*(xx + yy);
        return r;
    }

    Vec3 RotateVector(const Vec3& v) const {
        Quat qv(v.x, v.y, v.z, 0);
        Quat conj(-x, -y, -z, w);
        Quat result = (*this) * qv * conj;
        return Vec3(result.x, result.y, result.z);
    }
};

// ─── AABB ───
struct AABB {
    Vec3 min, max;
    AABB() : min(Vec3(1e30f)), max(Vec3(-1e30f)) {}
    AABB(const Vec3& mn, const Vec3& mx) : min(mn), max(mx) {}

    void Expand(const Vec3& p) {
        min.x = std::min(min.x, p.x); max.x = std::max(max.x, p.x);
        min.y = std::min(min.y, p.y); max.y = std::max(max.y, p.y);
        min.z = std::min(min.z, p.z); max.z = std::max(max.z, p.z);
    }

    Vec3 Center() const { return (min + max) * 0.5f; }
    Vec3 Extents() const { return (max - min) * 0.5f; }

    bool Intersects(const AABB& o) const {
        return (min.x <= o.max.x && max.x >= o.min.x) &&
               (min.y <= o.max.y && max.y >= o.min.y) &&
               (min.z <= o.max.z && max.z >= o.min.z);
    }
};

// ─── Color ───
struct Color {
    f32 r, g, b, a;
    Color() : r(1), g(1), b(1), a(1) {}
    Color(f32 r_, f32 g_, f32 b_, f32 a_ = 1.0f) : r(r_), g(g_), b(b_), a(a_) {}
};

} // namespace MiniEngine::Math
```

#### Memory.hpp — 内存分配器

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include <vector>
#include <memory>
#include <cstdlib>

namespace MiniEngine {

// 线性分配器 —— 适合每帧分配、一帧后全部释放的场景
class LinearAllocator {
public:
    explicit LinearAllocator(size_t size);
    ~LinearAllocator();

    void* Allocate(size_t size, size_t alignment = 16);
    void Reset();
    size_t GetUsed() const { return m_offset; }
    size_t GetCapacity() const { return m_capacity; }

private:
    u8* m_buffer;
    size_t m_capacity;
    size_t m_offset;
};

// 对象池 —— 适合频繁创建销毁的同尺寸对象
template<typename T>
class ObjectPool {
public:
    explicit ObjectPool(size_t initialCapacity = 256) {
        m_objects.reserve(initialCapacity);
        m_freeList.reserve(initialCapacity);
    }

    template<typename... Args>
    T* Acquire(Args&&... args) {
        if (!m_freeList.empty()) {
            T* obj = m_freeList.back();
            m_freeList.pop_back();
            new (obj) T(std::forward<Args>(args)...);
            return obj;
        }
        m_objects.emplace_back(std::make_unique<T>(std::forward<Args>(args)...));
        return m_objects.back().get();
    }

    void Release(T* obj) {
        obj->~T();
        m_freeList.push_back(obj);
    }

    void Clear() {
        m_objects.clear();
        m_freeList.clear();
    }

private:
    std::vector<std::unique_ptr<T>> m_objects;
    std::vector<T*> m_freeList;
};

} // namespace MiniEngine
```

#### Log.hpp — 日志系统

```cpp
#pragma once
#include <spdlog/spdlog.h>
#include <memory>

namespace MiniEngine {

class Log {
public:
    static void Init();
    static std::shared_ptr<spdlog::logger>& GetEngineLogger() { return s_engineLogger; }
    static std::shared_ptr<spdlog::logger>& GetAppLogger() { return s_appLogger; }

private:
    static std::shared_ptr<spdlog::logger> s_engineLogger;
    static std::shared_ptr<spdlog::logger> s_appLogger;
};

} // namespace MiniEngine

// 宏定义
#define ME_LOG_TRACE(...) ::MiniEngine::Log::GetEngineLogger()->trace(__VA_ARGS__)
#define ME_LOG_INFO(...)  ::MiniEngine::Log::GetEngineLogger()->info(__VA_ARGS__)
#define ME_LOG_WARN(...)  ::MiniEngine::Log::GetEngineLogger()->warn(__VA_ARGS__)
#define ME_LOG_ERROR(...) ::MiniEngine::Log::GetEngineLogger()->error(__VA_ARGS__)
#define ME_LOG_FATAL(...) ::MiniEngine::Log::GetEngineLogger()->critical(__VA_ARGS__)
```

#### Profiler.hpp — 性能分析器

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include <chrono>
#include <string>
#include <vector>
#include <unordered_map>

namespace MiniEngine {

struct ProfileSample {
    std::string name;
    f64 elapsedMs;
    u32 callCount;
};

class Profiler {
public:
    static Profiler& Instance();

    void BeginFrame();
    void EndFrame();

    void PushScope(const char* name);
    void PopScope();

    const std::vector<ProfileSample>& GetLastFrameSamples() const { return m_lastFrameSamples; }
    f64 GetFrameTime() const { return m_frameTime; }
    f64 GetFPS() const { return m_fps; }

private:
    struct Scope {
        const char* name;
        std::chrono::high_resolution_clock::time_point start;
    };

    std::vector<Scope> m_scopeStack;
    std::unordered_map<std::string, ProfileSample> m_currentSamples;
    std::vector<ProfileSample> m_lastFrameSamples;
    f64 m_frameTime = 0;
    f64 m_fps = 0;
    std::chrono::high_resolution_clock::time_point m_frameStart;
};

// RAII scope timer
class ProfileScope {
public:
    explicit ProfileScope(const char* name) { Profiler::Instance().PushScope(name); }
    ~ProfileScope() { Profiler::Instance().PopScope(); }
};

#define ME_PROFILE_SCOPE(name) ::MiniEngine::ProfileScope _profScope##__LINE__(name)
#define ME_PROFILE_FUNCTION() ME_PROFILE_SCOPE(__FUNCTION__)

} // namespace MiniEngine
```

### 2.4 ECS 层

#### Entity.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"

namespace MiniEngine::ECS {

// Entity 只是一个32位ID，高16位是生成计数（防止ID复用问题），低16位是索引
struct Entity {
    u32 id;

    bool operator==(const Entity& o) const { return id == o.id; }
    bool operator!=(const Entity& o) const { return id != o.id; }
    bool IsValid() const { return id != 0; }

    static Entity Invalid() { return Entity{0}; }
};

} // namespace MiniEngine::ECS

namespace std {
template<>
struct hash<MiniEngine::ECS::Entity> {
    size_t operator()(const MiniEngine::ECS::Entity& e) const {
        return hash<u32>()(e.id);
    }
};
} // namespace std
```

#### Component.hpp — 组件类型系统

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include <vector>
#include <type_traits>
#include <cassert>

namespace MiniEngine::ECS {

// 组件基类标记（仅用于类型约束）
struct IComponent {};

// 组件类型注册器
class ComponentRegistry {
public:
    template<typename T>
    static ComponentTypeID GetTypeID() {
        static_assert(std::is_base_of_v<IComponent, T>, "T must derive from IComponent");
        static ComponentTypeID id = s_nextTypeID++;
        return id;
    }

    static u32 GetComponentTypeCount() { return s_nextTypeID; }

private:
    static inline ComponentTypeID s_nextTypeID = 0;
};

// 稀疏集 —— 用于快速查询某实体是否有某组件
template<typename T>
class SparseSet {
public:
    static_assert(std::is_base_of_v<IComponent, T>, "T must be a component");

    bool Has(Entity entity) const {
        u32 index = entity.id;
        return index < m_sparse.size() && m_sparse[index] != INVALID_INDEX;
    }

    T& Get(Entity entity) {
        assert(Has(entity));
        return m_dense[m_sparse[entity.id]].component;
    }

    const T& Get(Entity entity) const {
        assert(Has(entity));
        return m_dense[m_sparse[entity.id]].component;
    }

    T* TryGet(Entity entity) {
        if (!Has(entity)) return nullptr;
        return &m_dense[m_sparse[entity.id]].component;
    }

    T& Add(Entity entity, const T& component) {
        u32 index = entity.id;
        if (index >= m_sparse.size()) {
            m_sparse.resize(index + 1, INVALID_INDEX);
        }
        m_sparse[index] = static_cast<u32>(m_dense.size());
        m_dense.push_back({entity, component});
        return m_dense.back().component;
    }

    void Remove(Entity entity) {
        if (!Has(entity)) return;
        u32 denseIndex = m_sparse[entity.id];
        u32 lastDenseIndex = static_cast<u32>(m_dense.size()) - 1;

        // Swap with last and pop
        if (denseIndex != lastDenseIndex) {
            m_dense[denseIndex] = m_dense[lastDenseIndex];
            m_sparse[m_dense[denseIndex].entity.id] = denseIndex;
        }
        m_dense.pop_back();
        m_sparse[entity.id] = INVALID_INDEX;
    }

    void Clear() {
        m_sparse.clear();
        m_dense.clear();
    }

    size_t Size() const { return m_dense.size(); }

    // 迭代支持
    struct Iterator {
        typename std::vector<std::pair<Entity, T>>::iterator it;
        Entity entity() const { return it->first; }
        T& component() { return it->second; }
        Iterator& operator++() { ++it; return *this; }
        bool operator!=(const Iterator& o) const { return it != o.it; }
    };

    auto begin() { return m_dense.begin(); }
    auto end() { return m_dense.end(); }
    auto begin() const { return m_dense.begin(); }
    auto end() const { return m_dense.end(); }

private:
    static constexpr u32 INVALID_INDEX = std::numeric_limits<u32>::max();
    std::vector<u32> m_sparse;
    std::vector<std::pair<Entity, T>> m_dense;
};

} // namespace MiniEngine::ECS
```

#### Components.hpp — 内置组件

```cpp
#pragma once
#include "MiniEngine/ECS/Component.hpp"
#include "MiniEngine/Core/Math.hpp"
#include <string>

namespace MiniEngine::ECS {

// ─── Transform ─── 世界变换
struct Transform : IComponent {
    Math::Vec3 position = Math::Vec3(0);
    Math::Quat rotation = Math::Quat();
    Math::Vec3 scale = Math::Vec3(1);

    Math::Mat4 GetMatrix() const {
        Math::Mat4 t = Math::Mat4::Translate(position);
        Math::Mat4 r = rotation.ToMat4();
        Math::Mat4 s = Math::Mat4::Scale(scale);
        return t * r * s;
    }

    Math::Vec3 Forward() const { return rotation.RotateVector(Math::Vec3(0, 0, -1)); }
    Math::Vec3 Right() const { return rotation.RotateVector(Math::Vec3(1, 0, 0)); }
    Math::Vec3 Up() const { return rotation.RotateVector(Math::Vec3(0, 1, 0)); }
};

// ─── Camera ─── 相机组件
struct Camera : IComponent {
    f32 fov = 60.0f * 3.14159f / 180.0f;
    f32 aspect = 16.0f / 9.0f;
    f32 nearPlane = 0.1f;
    f32 farPlane = 1000.0f;
    bool isMain = false;

    Math::Mat4 GetProjection() const {
        return Math::Mat4::Perspective(fov, aspect, nearPlane, farPlane);
    }

    Math::Mat4 GetView(const Transform& transform) const {
        Math::Vec3 eye = transform.position;
        Math::Vec3 center = eye + transform.Forward();
        Math::Vec3 up = transform.Up();
        return Math::Mat4::LookAt(eye, center, up);
    }
};

// ─── MeshRenderer ─── 网格渲染器
struct MeshRenderer : IComponent {
    std::string meshPath;
    std::string materialPath;
    bool castShadow = true;
    bool receiveShadow = true;
    u32 meshID = 0;      // 运行时由ResourceManager填充
    u32 materialID = 0;  // 运行时由ResourceManager填充
};

// ─── Light ─── 光源组件
struct Light : IComponent {
    enum Type { Directional, Point, Spot } type = Directional;
    Math::Color color = Math::Color(1, 1, 1);
    f32 intensity = 1.0f;
    f32 range = 10.0f;       // Point/Spot
    f32 spotAngle = 45.0f;   // Spot

    // 阴影
    bool castShadow = true;
    u32 shadowMapID = 0;
};

// ─── RigidBody ─── 刚体组件
struct RigidBody : IComponent {
    Math::Vec3 velocity = Math::Vec3(0);
    Math::Vec3 acceleration = Math::Vec3(0);
    f32 mass = 1.0f;
    f32 drag = 0.01f;
    bool useGravity = true;
    bool isKinematic = false;
};

// ─── Collider ─── 碰撞体
struct Collider : IComponent {
    Math::AABB localBounds;
    Math::AABB worldBounds;  // 每帧由PhysicsSystem更新
};

// ─── Animator ─── 动画器
struct Animator : IComponent {
    std::string animationPath;
    f32 playbackSpeed = 1.0f;
    bool isPlaying = false;
    bool loop = true;
    f32 currentTime = 0;
    u32 animationID = 0;
};

// ─── AudioSource ─── 音频源
struct AudioSource : IComponent {
    std::string clipPath;
    bool playOnStart = false;
    bool loop = false;
    f32 volume = 1.0f;
    f32 pitch = 1.0f;
    f32 minDistance = 1.0f;
    f32 maxDistance = 100.0f;
    u32 clipID = 0;
};

// ─── Tag ─── 标签
struct Tag : IComponent {
    std::string name = "Entity";
};

} // namespace MiniEngine::ECS
```

#### World.hpp — ECS 世界管理器

```cpp
#pragma once
#include "MiniEngine/ECS/Entity.hpp"
#include "MiniEngine/ECS/Component.hpp"
#include "MiniEngine/Core/Types.hpp"
#include <vector>
#include <array>
#include <memory>
#include <functional>

namespace MiniEngine::ECS {

class ISystem;

constexpr u32 MAX_COMPONENTS = 64;

class World {
public:
    World();
    ~World();

    // Entity 管理
    Entity CreateEntity();
    void DestroyEntity(Entity entity);
    bool IsAlive(Entity entity) const;

    // Component 管理
    template<typename T, typename... Args>
    T& AddComponent(Entity entity, Args&&... args) {
        auto& pool = GetOrCreatePool<T>();
        return pool.Add(entity, T{std::forward<Args>(args)...});
    }

    template<typename T>
    void RemoveComponent(Entity entity) {
        auto& pool = GetOrCreatePool<T>();
        pool.Remove(entity);
    }

    template<typename T>
    bool HasComponent(Entity entity) {
        auto& pool = GetOrCreatePool<T>();
        return pool.Has(entity);
    }

    template<typename T>
    T& GetComponent(Entity entity) {
        auto& pool = GetOrCreatePool<T>();
        return pool.Get(entity);
    }

    template<typename T>
    T* TryGetComponent(Entity entity) {
        auto& pool = GetOrCreatePool<T>();
        return pool.TryGet(entity);
    }

    template<typename T>
    SparseSet<T>& GetComponentPool() {
        return GetOrCreatePool<T>();
    }

    // System 管理
    void RegisterSystem(std::unique_ptr<ISystem> system);
    void UnregisterSystem(ISystem* system);

    // 查询
    template<typename... Components>
    std::vector<Entity> Query() {
        std::vector<Entity> result;
        // 找到组件数最少的pool作为遍历基础
        // 简化实现：遍历所有entity检查
        for (u32 i = 1; i < m_nextEntityID; ++i) {
            Entity e{i};
            if (IsAlive(e) && (HasComponent<Components>(e) && ...)) {
                result.push_back(e);
            }
        }
        return result;
    }

    // 游戏循环
    void Update(f32 deltaTime);
    void FixedUpdate(f32 fixedDeltaTime);
    void Render();

    // 获取所有存活实体
    const std::vector<Entity>& GetAllEntities() const { return m_aliveEntities; }

private:
    // 类型擦除的组件池接口
    class IComponentPool {
    public:
        virtual ~IComponentPool() = default;
        virtual void Remove(Entity entity) = 0;
        virtual void Clear() = 0;
    };

    template<typename T>
    class TypedPool : public IComponentPool {
    public:
        SparseSet<T> data;
        void Remove(Entity entity) override { data.Remove(entity); }
        void Clear() override { data.Clear(); }
    };

    template<typename T>
    SparseSet<T>& GetOrCreatePool() {
        ComponentTypeID typeID = ComponentRegistry::GetTypeID<T>();
        if (typeID >= m_componentPools.size()) {
            m_componentPools.resize(typeID + 1);
        }
        if (!m_componentPools[typeID]) {
            m_componentPools[typeID] = std::make_unique<TypedPool<T>>();
        }
        return static_cast<TypedPool<T>*>(m_componentPools[typeID].get())->data;
    }

    u32 m_nextEntityID = 1;
    std::vector<u32> m_entityGenerations;
    std::vector<bool> m_entityAlive;
    std::vector<Entity> m_aliveEntities;
    std::vector<u32> m_freeList;
    std::vector<std::unique_ptr<IComponentPool>> m_componentPools;
    std::vector<std::unique_ptr<ISystem>> m_systems;

    // 延迟删除
    std::vector<Entity> m_entitiesToDestroy;
    void ProcessDestructions();
};

// System 基类
class ISystem {
public:
    virtual ~ISystem() = default;
    virtual void OnAttach(World* world) { m_world = world; }
    virtual void OnDetach() {}
    virtual void OnUpdate(f32 deltaTime) {}
    virtual void OnFixedUpdate(f32 fixedDeltaTime) {}
    virtual void OnRender() {}

protected:
    World* m_world = nullptr;
};

} // namespace MiniEngine::ECS
```

#### World.cpp

```cpp
#include "MiniEngine/ECS/World.hpp"
#include "MiniEngine/Core/Log.hpp"

namespace MiniEngine::ECS {

World::World() = default;
World::~World() = default;

Entity World::CreateEntity() {
    u32 id;
    if (!m_freeList.empty()) {
        id = m_freeList.back();
        m_freeList.pop_back();
        m_entityGenerations[id]++;
    } else {
        id = m_nextEntityID++;
        m_entityGenerations.push_back(1);
        m_entityAlive.push_back(false);
    }
    m_entityAlive[id] = true;
    Entity e{(m_entityGenerations[id] << 16) | id};
    m_aliveEntities.push_back(e);
    return e;
}

void World::DestroyEntity(Entity entity) {
    m_entitiesToDestroy.push_back(entity);
}

bool World::IsAlive(Entity entity) const {
    u32 index = entity.id & 0xFFFF;
    u32 generation = entity.id >> 16;
    return index < m_entityGenerations.size() &&
           m_entityGenerations[index] == generation &&
           m_entityAlive[index];
}

void World::ProcessDestructions() {
    for (Entity e : m_entitiesToDestroy) {
        if (!IsAlive(e)) continue;
        u32 index = e.id & 0xFFFF;

        // 移除所有组件
        for (auto& pool : m_componentPools) {
            if (pool) pool->Remove(e);
        }

        m_entityAlive[index] = false;
        m_freeList.push_back(index);

        // 从 alive 列表移除
        auto it = std::find(m_aliveEntities.begin(), m_aliveEntities.end(), e);
        if (it != m_aliveEntities.end()) {
            m_aliveEntities.erase(it);
        }
    }
    m_entitiesToDestroy.clear();
}

void World::RegisterSystem(std::unique_ptr<ISystem> system) {
    system->OnAttach(this);
    m_systems.push_back(std::move(system));
}

void World::UnregisterSystem(ISystem* system) {
    auto it = std::remove_if(m_systems.begin(), m_systems.end(),
        [system](const auto& s) { return s.get() == system; });
    if (it != m_systems.end()) {
        (*it)->OnDetach();
        m_systems.erase(it, m_systems.end());
    }
}

void World::Update(f32 deltaTime) {
    ME_PROFILE_FUNCTION();
    for (auto& system : m_systems) {
        system->OnUpdate(deltaTime);
    }
    ProcessDestructions();
}

void World::FixedUpdate(f32 fixedDeltaTime) {
    ME_PROFILE_FUNCTION();
    for (auto& system : m_systems) {
        system->OnFixedUpdate(fixedDeltaTime);
    }
}

void World::Render() {
    ME_PROFILE_FUNCTION();
    for (auto& system : m_systems) {
        system->OnRender();
    }
}

} // namespace MiniEngine::ECS
```

### 2.5 Render 层

#### Shader.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include "MiniEngine/Core/Math.hpp"
#include <string>
#include <unordered_map>

namespace MiniEngine::Render {

class Shader {
public:
    Shader() = default;
    ~Shader();

    bool LoadFromSource(const std::string& vertexSrc, const std::string& fragmentSrc);
    bool LoadFromFiles(const std::string& vertPath, const std::string& fragPath);

    void Bind() const;
    void Unbind() const;

    void SetInt(const std::string& name, i32 value);
    void SetFloat(const std::string& name, f32 value);
    void SetVec3(const std::string& name, const Math::Vec3& value);
    void SetVec4(const std::string& name, const Math::Vec4& value);
    void SetMat4(const std::string& name, const Math::Mat4& value);

    u32 GetID() const { return m_programID; }
    bool IsValid() const { return m_programID != 0; }

private:
    u32 m_programID = 0;
    std::unordered_map<std::string, i32> m_uniformCache;

    i32 GetUniformLocation(const std::string& name);
    u32 CompileShader(u32 type, const std::string& source);
};

} // namespace MiniEngine::Render
```

#### Shader.cpp

```cpp
#include "MiniEngine/Render/Shader.hpp"
#include "MiniEngine/Core/Log.hpp"
#include <glad/glad.h>
#include <fstream>
#include <sstream>

namespace MiniEngine::Render {

Shader::~Shader() {
    if (m_programID != 0) {
        glDeleteProgram(m_programID);
    }
}

bool Shader::LoadFromSource(const std::string& vertexSrc, const std::string& fragmentSrc) {
    u32 vs = CompileShader(GL_VERTEX_SHADER, vertexSrc);
    if (vs == 0) return false;

    u32 fs = CompileShader(GL_FRAGMENT_SHADER, fragmentSrc);
    if (fs == 0) {
        glDeleteShader(vs);
        return false;
    }

    m_programID = glCreateProgram();
    glAttachShader(m_programID, vs);
    glAttachShader(m_programID, fs);
    glLinkProgram(m_programID);

    int success;
    glGetProgramiv(m_programID, GL_LINK_STATUS, &success);
    if (!success) {
        char infoLog[512];
        glGetProgramInfoLog(m_programID, 512, nullptr, infoLog);
        ME_LOG_ERROR("Shader link failed: {}", infoLog);
        glDeleteProgram(m_programID);
        m_programID = 0;
        glDeleteShader(vs);
        glDeleteShader(fs);
        return false;
    }

    glDeleteShader(vs);
    glDeleteShader(fs);
    return true;
}

bool Shader::LoadFromFiles(const std::string& vertPath, const std::string& fragPath) {
    std::ifstream vFile(vertPath), fFile(fragPath);
    if (!vFile || !fFile) {
        ME_LOG_ERROR("Failed to open shader files: {} {}", vertPath, fragPath);
        return false;
    }
    std::stringstream vStream, fStream;
    vStream << vFile.rdbuf();
    fStream << fFile.rdbuf();
    return LoadFromSource(vStream.str(), fStream.str());
}

u32 Shader::CompileShader(u32 type, const std::string& source) {
    u32 shader = glCreateShader(type);
    const char* src = source.c_str();
    glShaderSource(shader, 1, &src, nullptr);
    glCompileShader(shader);

    int success;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
    if (!success) {
        char infoLog[512];
        glGetShaderInfoLog(shader, 512, nullptr, infoLog);
        ME_LOG_ERROR("Shader compile failed: {}", infoLog);
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

void Shader::Bind() const { glUseProgram(m_programID); }
void Shader::Unbind() const { glUseProgram(0); }

i32 Shader::GetUniformLocation(const std::string& name) {
    auto it = m_uniformCache.find(name);
    if (it != m_uniformCache.end()) return it->second;

    i32 loc = glGetUniformLocation(m_programID, name.c_str());
    m_uniformCache[name] = loc;
    return loc;
}

void Shader::SetInt(const std::string& name, i32 value) {
    glUniform1i(GetUniformLocation(name), value);
}
void Shader::SetFloat(const std::string& name, f32 value) {
    glUniform1f(GetUniformLocation(name), value);
}
void Shader::SetVec3(const std::string& name, const Math::Vec3& value) {
    glUniform3f(GetUniformLocation(name), value.x, value.y, value.z);
}
void Shader::SetVec4(const std::string& name, const Math::Vec4& value) {
    glUniform4f(GetUniformLocation(name), value.x, value.y, value.z, value.w);
}
void Shader::SetMat4(const std::string& name, const Math::Mat4& value) {
    glUniformMatrix4fv(GetUniformLocation(name), 1, GL_FALSE, value.m);
}

} // namespace MiniEngine::Render
```

#### Mesh.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include "MiniEngine/Core/Math.hpp"
#include <vector>
#include <string>

namespace MiniEngine::Render {

struct Vertex {
    Math::Vec3 position;
    Math::Vec3 normal;
    Math::Vec2 texCoord;
    Math::Vec4 tangent;
    u32 boneIDs[4] = {0, 0, 0, 0};
    f32 boneWeights[4] = {0, 0, 0, 0};
};

struct SubMesh {
    u32 indexOffset = 0;
    u32 indexCount = 0;
    u32 materialIndex = 0;
};

class Mesh {
public:
    Mesh() = default;
    ~Mesh();

    void SetVertices(const std::vector<Vertex>& vertices);
    void SetIndices(const std::vector<u32>& indices);
    void SetSubMeshes(const std::vector<SubMesh>& subMeshes);

    void Bind() const;
    void Unbind() const;
    void Draw() const;
    void DrawSubMesh(u32 subMeshIndex) const;

    const std::vector<SubMesh>& GetSubMeshes() const { return m_subMeshes; }
    const Math::AABB& GetBounds() const { return m_bounds; }

private:
    u32 m_vao = 0, m_vbo = 0, m_ebo = 0;
    std::vector<SubMesh> m_subMeshes;
    u32 m_indexCount = 0;
    Math::AABB m_bounds;
};

} // namespace MiniEngine::Render
```

#### Mesh.cpp

```cpp
#include "MiniEngine/Render/Mesh.hpp"
#include <glad/glad.h>

namespace MiniEngine::Render {

Mesh::~Mesh() {
    if (m_vao) glDeleteVertexArrays(1, &m_vao);
    if (m_vbo) glDeleteBuffers(1, &m_vbo);
    if (m_ebo) glDeleteBuffers(1, &m_ebo);
}

void Mesh::SetVertices(const std::vector<Vertex>& vertices) {
    if (!m_vao) glGenVertexArrays(1, &m_vao);
    if (!m_vbo) glGenBuffers(1, &m_vbo);

    glBindVertexArray(m_vao);
    glBindBuffer(GL_ARRAY_BUFFER, m_vbo);
    glBufferData(GL_ARRAY_BUFFER, vertices.size() * sizeof(Vertex), vertices.data(), GL_STATIC_DRAW);

    // Position
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, position));
    // Normal
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, normal));
    // TexCoord
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, texCoord));
    // Tangent
    glEnableVertexAttribArray(3);
    glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, tangent));
    // BoneIDs
    glEnableVertexAttribArray(4);
    glVertexAttribIPointer(4, 4, GL_INT, sizeof(Vertex), (void*)offsetof(Vertex, boneIDs));
    // BoneWeights
    glEnableVertexAttribArray(5);
    glVertexAttribPointer(5, 4, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, boneWeights));

    glBindVertexArray(0);

    // 计算AABB
    m_bounds = Math::AABB();
    for (const auto& v : vertices) {
        m_bounds.Expand(v.position);
    }
}

void Mesh::SetIndices(const std::vector<u32>& indices) {
    if (!m_ebo) glGenBuffers(1, &m_ebo);
    glBindVertexArray(m_vao);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m_ebo);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.size() * sizeof(u32), indices.data(), GL_STATIC_DRAW);
    glBindVertexArray(0);
    m_indexCount = static_cast<u32>(indices.size());
}

void Mesh::SetSubMeshes(const std::vector<SubMesh>& subMeshes) {
    m_subMeshes = subMeshes;
}

void Mesh::Bind() const { glBindVertexArray(m_vao); }
void Mesh::Unbind() const { glBindVertexArray(0); }

void Mesh::Draw() const {
    if (m_subMeshes.empty()) {
        glDrawElements(GL_TRIANGLES, m_indexCount, GL_UNSIGNED_INT, nullptr);
    } else {
        for (u32 i = 0; i < m_subMeshes.size(); ++i) {
            DrawSubMesh(i);
        }
    }
}

void Mesh::DrawSubMesh(u32 subMeshIndex) const {
    const auto& sub = m_subMeshes[subMeshIndex];
    glDrawElements(GL_TRIANGLES, sub.indexCount, GL_UNSIGNED_INT,
                   reinterpret_cast<void*>(static_cast<uintptr_t>(sub.indexOffset * sizeof(u32))));
}

} // namespace MiniEngine::Render
```

#### Texture.hpp / Texture.cpp

```cpp
// Texture.hpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include <string>

namespace MiniEngine::Render {

class Texture {
public:
    enum class Format { RGB, RGBA, Depth, Depth16 };
    enum class Filter { Nearest, Linear, Mipmap };
    enum class Wrap { Repeat, Clamp, ClampToEdge };

    Texture() = default;
    ~Texture();

    bool LoadFromFile(const std::string& path, bool sRGB = true);
    bool CreateEmpty(u32 width, u32 height, Format format, Filter filter = Filter::Linear);
    bool CreateDepthMap(u32 width, u32 height);

    void Bind(u32 slot = 0) const;
    void Unbind() const;

    u32 GetID() const { return m_textureID; }
    u32 GetWidth() const { return m_width; }
    u32 GetHeight() const { return m_height; }

    void SetWrapMode(Wrap wrap);

private:
    u32 m_textureID = 0;
    u32 m_width = 0, m_height = 0;
    Format m_format = Format::RGBA;
};

} // namespace MiniEngine::Render
```

```cpp
// Texture.cpp
#include "MiniEngine/Render/Texture.hpp"
#include "MiniEngine/Core/Log.hpp"
#include <glad/glad.h>
#define STB_IMAGE_IMPLEMENTATION
#include <stb_image.h>

namespace MiniEngine::Render {

Texture::~Texture() {
    if (m_textureID) glDeleteTextures(1, &m_textureID);
}

bool Texture::LoadFromFile(const std::string& path, bool sRGB) {
    int width, height, channels;
    stbi_set_flip_vertically_on_load(true);
    unsigned char* data = stbi_load(path.c_str(), &width, &height, &channels, 0);
    if (!data) {
        ME_LOG_ERROR("Failed to load texture: {}", path);
        return false;
    }

    glGenTextures(1, &m_textureID);
    glBindTexture(GL_TEXTURE_2D, m_textureID);

    GLenum internalFormat, dataFormat;
    if (channels == 3) {
        internalFormat = sRGB ? GL_SRGB8 : GL_RGB8;
        dataFormat = GL_RGB;
    } else {
        internalFormat = sRGB ? GL_SRGB8_ALPHA8 : GL_RGBA8;
        dataFormat = GL_RGBA;
    }

    glTexImage2D(GL_TEXTURE_2D, 0, internalFormat, width, height, 0, dataFormat, GL_UNSIGNED_BYTE, data);
    glGenerateMipmap(GL_TEXTURE_2D);

    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

    stbi_image_free(data);
    m_width = width;
    m_height = height;
    return true;
}

bool Texture::CreateEmpty(u32 width, u32 height, Format format, Filter filter) {
    glGenTextures(1, &m_textureID);
    glBindTexture(GL_TEXTURE_2D, m_textureID);

    GLenum internalFmt, dataFmt;
    switch (format) {
        case Format::RGB: internalFmt = GL_RGB8; dataFmt = GL_RGB; break;
        case Format::RGBA: internalFmt = GL_RGBA8; dataFmt = GL_RGBA; break;
        case Format::Depth: internalFmt = GL_DEPTH_COMPONENT; dataFmt = GL_DEPTH_COMPONENT; break;
        default: internalFmt = GL_RGBA8; dataFmt = GL_RGBA;
    }

    glTexImage2D(GL_TEXTURE_2D, 0, internalFmt, width, height, 0, dataFmt, GL_UNSIGNED_BYTE, nullptr);

    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER,
                    filter == Filter::Mipmap ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

    m_width = width;
    m_height = height;
    m_format = format;
    return true;
}

bool Texture::CreateDepthMap(u32 width, u32 height) {
    glGenTextures(1, &m_textureID);
    glBindTexture(GL_TEXTURE_2D, m_textureID);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, width, height, 0,
                 GL_DEPTH_COMPONENT, GL_FLOAT, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);
    float borderColor[] = {1.0f, 1.0f, 1.0f, 1.0f};
    glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, borderColor);
    m_width = width;
    m_height = height;
    return true;
}

void Texture::Bind(u32 slot) const {
    glActiveTexture(GL_TEXTURE0 + slot);
    glBindTexture(GL_TEXTURE_2D, m_textureID);
}
void Texture::Unbind() const { glBindTexture(GL_TEXTURE_2D, 0); }

void Texture::SetWrapMode(Wrap wrap) {
    glBindTexture(GL_TEXTURE_2D, m_textureID);
    GLint mode = (wrap == Wrap::Repeat) ? GL_REPEAT : GL_CLAMP_TO_EDGE;
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, mode);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, mode);
}

} // namespace MiniEngine::Render
```

#### Material.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include "MiniEngine/Core/Math.hpp"
#include "MiniEngine/Render/Shader.hpp"
#include "MiniEngine/Render/Texture.hpp"
#include <memory>
#include <unordered_map>

namespace MiniEngine::Render {

// PBR 材质参数
struct Material {
    std::shared_ptr<Shader> shader;

    // PBR 参数
    Math::Color albedo = Math::Color(1, 1, 1);
    f32 metallic = 0.0f;
    f32 roughness = 0.5f;
    f32 ao = 1.0f;
    f32 emissive = 0.0f;

    // 纹理
    std::shared_ptr<Texture> albedoMap;
    std::shared_ptr<Texture> normalMap;
    std::shared_ptr<Texture> metallicMap;
    std::shared_ptr<Texture> roughnessMap;
    std::shared_ptr<Texture> aoMap;

    // 其他参数
    bool transparent = false;
    bool doubleSided = false;

    void Bind() const;
};

} // namespace MiniEngine::Render
```

#### Renderer.hpp — 渲染器主类

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include "MiniEngine/Core/Math.hpp"
#include "MiniEngine/Render/Shader.hpp"
#include "MiniEngine/Render/Texture.hpp"
#include "MiniEngine/Render/Mesh.hpp"
#include "MiniEngine/Render/Material.hpp"
#include "MiniEngine/Render/Framebuffer.hpp"
#include <vector>
#include <memory>

namespace MiniEngine::ECS { class World; struct Transform; struct Light; struct Camera; }

namespace MiniEngine::Render {

struct RenderCommand {
    Mesh* mesh;
    Material* material;
    Math::Mat4 transform;
    Math::AABB bounds;
    u32 entityID;
};

class Renderer {
public:
    Renderer();
    ~Renderer();

    bool Initialize(u32 width, u32 height);
    void Shutdown();

    void SetViewport(u32 x, u32 y, u32 width, u32 height);
    void SetClearColor(const Math::Color& color);
    void Clear();

    // 渲染主入口
    void RenderFrame(ECS::World* world);

    // 立即模式渲染（用于调试）
    void DrawLine(const Math::Vec3& from, const Math::Vec3& to, const Math::Color& color);
    void DrawAABB(const Math::AABB& aabb, const Math::Color& color);

    // 阴影
    bool IsShadowEnabled() const { return m_shadowEnabled; }
    void SetShadowEnabled(bool enabled) { m_shadowEnabled = enabled; }

    // 渲染统计
    struct Stats {
        u32 drawCalls = 0;
        u32 triangleCount = 0;
        u32 shaderSwitches = 0;
        f64 shadowPassTime = 0;
        f64 mainPassTime = 0;
    };
    const Stats& GetStats() const { return m_stats; }

private:
    void ShadowPass(ECS::World* world);
    void MainPass(ECS::World* world);
    void SubmitRenderCommands(ECS::World* world);
    void ExecuteRenderCommands();

    void SetupLighting(Shader* shader, ECS::World* world);
    void SetupShadowMatrix(Shader* shader);

    u32 m_width = 0, m_height = 0;
    Math::Color m_clearColor = Math::Color(0.1f, 0.1f, 0.15f);

    // 阴影映射
    bool m_shadowEnabled = true;
    std::unique_ptr<Framebuffer> m_shadowFramebuffer;
    std::unique_ptr<Texture> m_shadowMap;
    u32 m_shadowMapSize = 2048;
    Math::Mat4 m_lightSpaceMatrix;

    // 渲染队列
    std::vector<RenderCommand> m_opaqueQueue;
    std::vector<RenderCommand> m_transparentQueue;

    // 全屏四边形（用于后期处理）
    u32 m_quadVAO = 0, m_quadVBO = 0;

    // 调试绘制
    std::unique_ptr<Shader> m_debugShader;
    std::vector<f32> m_debugLines;

    Stats m_stats;
};

} // namespace MiniEngine::Render
```

#### Renderer.cpp（核心实现）

```cpp
#include "MiniEngine/Render/Renderer.hpp"
#include "MiniEngine/ECS/World.hpp"
#include "MiniEngine/ECS/Components.hpp"
#include "MiniEngine/Core/Log.hpp"
#include "MiniEngine/Core/Profiler.hpp"
#include <glad/glad.h>
#include <algorithm>

namespace MiniEngine::Render {

// 标准 PBR 着色器源码
static const char* s_pbrVertexShader = R"(
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;
layout(location = 3) in vec4 aTangent;

out vec3 FragPos;
out vec3 Normal;
out vec2 TexCoord;
out vec4 FragPosLightSpace;
out mat3 TBN;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;
uniform mat4 lightSpaceMatrix;

void main() {
    vec4 worldPos = model * vec4(aPos, 1.0);
    FragPos = worldPos.xyz;
    TexCoord = aTexCoord;

    vec3 N = normalize(mat3(model) * aNormal);
    vec3 T = normalize(mat3(model) * aTangent.xyz);
    T = normalize(T - dot(T, N) * N);
    vec3 B = cross(N, T) * aTangent.w;
    TBN = mat3(T, B, N);
    Normal = N;

    FragPosLightSpace = lightSpaceMatrix * worldPos;
    gl_Position = projection * view * worldPos;
}
)";

static const char* s_pbrFragmentShader = R"(
#version 330 core
out vec4 FragColor;

in vec3 FragPos;
in vec3 Normal;
in vec2 TexCoord;
in vec4 FragPosLightSpace;
in mat3 TBN;

// Material
uniform vec3 albedo;
uniform float metallic;
uniform float roughness;
uniform float ao;
uniform float emissive;

uniform sampler2D albedoMap;
uniform sampler2D normalMap;
uniform sampler2D metallicMap;
uniform sampler2D roughnessMap;
uniform sampler2D aoMap;

uniform bool hasAlbedoMap;
uniform bool hasNormalMap;
uniform bool hasMetallicMap;
uniform bool hasRoughnessMap;
uniform bool hasAOMap;

// Lights
struct DirLight {
    vec3 direction;
    vec3 color;
    float intensity;
};
uniform DirLight dirLight;
uniform vec3 viewPos;

// Shadow
uniform sampler2D shadowMap;
uniform bool shadowEnabled;

const float PI = 3.14159265359;

float ShadowCalculation(vec4 fragPosLightSpace) {
    vec3 projCoords = fragPosLightSpace.xyz / fragPosLightSpace.w;
    projCoords = projCoords * 0.5 + 0.5;
    if(projCoords.z > 1.0) return 0.0;

    float closestDepth = texture(shadowMap, projCoords.xy).r;
    float currentDepth = projCoords.z;
    float bias = 0.005;
    float shadow = currentDepth - bias > closestDepth ? 1.0 : 0.0;
    return shadow;
}

float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    float num = a2;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = PI * denom * denom;
    return num / denom;
}

float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = (roughness + 1.0);
    float k = (r * r) / 8.0;
    float num = NdotV;
    float denom = NdotV * (1.0 - k) + k;
    return num / denom;
}

float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    float ggx2 = GeometrySchlickGGX(NdotV, roughness);
    float ggx1 = GeometrySchlickGGX(NdotL, roughness);
    return ggx1 * ggx2;
}

vec3 FresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}

void main() {
    vec3 albedoVal = hasAlbedoMap ? texture(albedoMap, TexCoord).rgb : albedo;
    float metallicVal = hasMetallicMap ? texture(metallicMap, TexCoord).r : metallic;
    float roughnessVal = hasRoughnessMap ? texture(roughnessMap, TexCoord).r : roughness;
    float aoVal = hasAOMap ? texture(aoMap, TexCoord).r : ao;

    vec3 N = Normal;
    if (hasNormalMap) {
        N = texture(normalMap, TexCoord).rgb * 2.0 - 1.0;
        N = normalize(TBN * N);
    }

    vec3 V = normalize(viewPos - FragPos);
    vec3 F0 = vec3(0.04);
    F0 = mix(F0, albedoVal, metallicVal);

    // Directional light
    vec3 L = normalize(-dirLight.direction);
    vec3 H = normalize(V + L);
    float distance = length(-dirLight.direction);
    vec3 radiance = dirLight.color * dirLight.intensity;

    float NDF = DistributionGGX(N, H, roughnessVal);
    float G = GeometrySmith(N, V, L, roughnessVal);
    vec3 F = FresnelSchlick(max(dot(H, V), 0.0), F0);

    vec3 numerator = NDF * G * F;
    float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.001;
    vec3 specular = numerator / denominator;

    vec3 kS = F;
    vec3 kD = vec3(1.0) - kS;
    kD *= 1.0 - metallicVal;

    float NdotL = max(dot(N, L), 0.0);
    vec3 Lo = (kD * albedoVal / PI + specular) * radiance * NdotL;

    float shadow = shadowEnabled ? ShadowCalculation(FragPosLightSpace) : 0.0;
    Lo *= (1.0 - shadow);

    vec3 ambient = vec3(0.03) * albedoVal * aoVal;
    vec3 color = ambient + Lo + vec3(emissive);

    // HDR tonemapping
    color = color / (color + vec3(1.0));
    // Gamma correction
    color = pow(color, vec3(1.0 / 2.2));

    FragColor = vec4(color, 1.0);
}
)";

// 阴影深度着色器
static const char* s_shadowVertexShader = R"(
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 lightSpaceMatrix;
uniform mat4 model;
void main() {
    gl_Position = lightSpaceMatrix * model * vec4(aPos, 1.0);
}
)";

static const char* s_shadowFragmentShader = R"(
#version 330 core
void main() {
    // gl_FragDepth = gl_FragCoord.z;
}
)";

// 调试线着色器
static const char* s_debugVertexShader = R"(
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 mvp;
void main() {
    gl_Position = mvp * vec4(aPos, 1.0);
}
)";

static const char* s_debugFragmentShader = R"(
#version 330 core
uniform vec3 color;
out vec4 FragColor;
void main() {
    FragColor = vec4(color, 1.0);
}
)";

Renderer::Renderer() = default;
Renderer::~Renderer() = default;

bool Renderer::Initialize(u32 width, u32 height) {
    m_width = width;
    m_height = height;

    // 启用深度测试和背面剔除
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_CULL_FACE);
    glCullFace(GL_BACK);
    glFrontFace(GL_CCW);

    // 创建阴影贴图
    m_shadowMap = std::make_unique<Texture>();
    m_shadowMap->CreateDepthMap(m_shadowMapSize, m_shadowMapSize);

    m_shadowFramebuffer = std::make_unique<Framebuffer>();
    m_shadowFramebuffer->AttachDepth(m_shadowMap->GetID());
    if (!m_shadowFramebuffer->IsComplete()) {
        ME_LOG_ERROR("Shadow framebuffer incomplete!");
        return false;
    }

    // 创建调试着色器
    m_debugShader = std::make_unique<Shader>();
    m_debugShader->LoadFromSource(s_debugVertexShader, s_debugFragmentShader);

    // 创建全屏四边形
    float quadVertices[] = {
        -1,  1, 0, 1,
        -1, -1, 0, 0,
         1, -1, 1, 0,
        -1,  1, 0, 1,
         1, -1, 1, 0,
         1,  1, 1, 1,
    };
    glGenVertexArrays(1, &m_quadVAO);
    glGenBuffers(1, &m_quadVBO);
    glBindVertexArray(m_quadVAO);
    glBindBuffer(GL_ARRAY_BUFFER, m_quadVBO);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quadVertices), quadVertices, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)(2 * sizeof(float)));

    ME_LOG_INFO("Renderer initialized ({}x{})", width, height);
    return true;
}

void Renderer::Shutdown() {
    if (m_quadVAO) glDeleteVertexArrays(1, &m_quadVAO);
    if (m_quadVBO) glDeleteBuffers(1, &m_quadVBO);
}

void Renderer::SetViewport(u32 x, u32 y, u32 width, u32 height) {
    glViewport(x, y, width, height);
}

void Renderer::SetClearColor(const Math::Color& color) {
    m_clearColor = color;
}

void Renderer::Clear() {
    glClearColor(m_clearColor.r, m_clearColor.g, m_clearColor.b, m_clearColor.a);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
}

void Renderer::RenderFrame(ECS::World* world) {
    ME_PROFILE_FUNCTION();
    m_stats = Stats{};

    // 1. 收集渲染命令
    SubmitRenderCommands(world);

    // 2. 阴影 Pass
    if (m_shadowEnabled) {
        ME_PROFILE_SCOPE("ShadowPass");
        auto start = std::chrono::high_resolution_clock::now();
        ShadowPass(world);
        auto end = std::chrono::high_resolution_clock::now();
        m_stats.shadowPassTime = std::chrono::duration<f64, std::milli>(end - start).count();
    }

    // 3. 主渲染 Pass
    {
        ME_PROFILE_SCOPE("MainPass");
        auto start = std::chrono::high_resolution_clock::now();
        MainPass(world);
        auto end = std::chrono::high_resolution_clock::now();
        m_stats.mainPassTime = std::chrono::duration<f64, std::milli>(end - start).count();
    }

    // 4. 调试绘制
    if (!m_debugLines.empty()) {
        // 绘制所有调试线
    }
}

void Renderer::SubmitRenderCommands(ECS::World* world) {
    m_opaqueQueue.clear();
    m_transparentQueue.clear();

    auto& meshPool = world->GetComponentPool<ECS::MeshRenderer>();
    auto& transformPool = world->GetComponentPool<ECS::Transform>();

    for (auto& [entity, meshRenderer] : meshPool) {
        auto* transform = transformPool.TryGet(entity);
        if (!transform) continue;

        // 这里简化处理，实际应从ResourceManager获取
        // 假设 meshRenderer 已经解析了 meshID 和 materialID
        // 实际实现需要ResourceManager的集成

        RenderCommand cmd;
        cmd.transform = transform->GetMatrix();
        cmd.entityID = entity.id;
        // cmd.mesh = ...; // 从ResourceManager获取
        // cmd.material = ...;

        // 简化：这里假设所有都是opaque
        m_opaqueQueue.push_back(cmd);
    }

    // 按材质排序以减少状态切换
    std::sort(m_opaqueQueue.begin(), m_opaqueQueue.end(),
        [](const RenderCommand& a, const RenderCommand& b) {
            return a.material < b.material;
        });
}

void Renderer::ShadowPass(ECS::World* world) {
    // 找到主光源
    auto& lightPool = world->GetComponentPool<ECS::Light>();
    auto& transformPool = world->GetComponentPool<ECS::Transform>();

    ECS::Light* mainLight = nullptr;
    ECS::Transform* mainLightTransform = nullptr;

    for (auto& [entity, light] : lightPool) {
        if (light.type == ECS::Light::Directional && light.castShadow) {
            mainLight = &light;
            mainLightTransform = transformPool.TryGet(entity);
            break;
        }
    }

    if (!mainLight) return;

    // 计算光源视锥
    Math::Vec3 lightDir = mainLightTransform ? mainLightTransform->Forward() : Math::Vec3(0, -1, 0);
    Math::Vec3 lightPos = -lightDir * 20.0f;
    Math::Mat4 lightView = Math::Mat4::LookAt(lightPos, Math::Vec3(0), Math::Vec3(0, 1, 0));
    Math::Mat4 lightProj = Math::Mat4::Ortho(-20, 20, -20, 20, 0.1f, 50.0f); // 简化为正交投影
    m_lightSpaceMatrix = lightProj * lightView;

    // 渲染到阴影贴图
    m_shadowFramebuffer->Bind();
    glViewport(0, 0, m_shadowMapSize, m_shadowMapSize);
    glClear(GL_DEPTH_BUFFER_BIT);
    glCullFace(GL_FRONT); // 防止peter-panning

    Shader shadowShader;
    shadowShader.LoadFromSource(s_shadowVertexShader, s_shadowFragmentShader);
    shadowShader.Bind();
    shadowShader.SetMat4("lightSpaceMatrix", m_lightSpaceMatrix);

    // 渲染所有投射阴影的物体
    auto& meshPool = world->GetComponentPool<ECS::MeshRenderer>();
    for (auto& [entity, meshRenderer] : meshPool) {
        if (!meshRenderer.castShadow) continue;
        auto* transform = transformPool.TryGet(entity);
        if (!transform) continue;

        shadowShader.SetMat4("model", transform->GetMatrix());
        // mesh->Draw(); // 实际绘制
        m_stats.drawCalls++;
    }

    glCullFace(GL_BACK);
    m_shadowFramebuffer->Unbind();
    SetViewport(0, 0, m_width, m_height);
}

void Renderer::MainPass(ECS::World* world) {
    Clear();

    // 找到主相机
    auto& cameraPool = world->GetComponentPool<ECS::Camera>();
    auto& transformPool = world->GetComponentPool<ECS::Transform>();

    ECS::Camera* mainCamera = nullptr;
    ECS::Transform* cameraTransform = nullptr;

    for (auto& [entity, camera] : cameraPool) {
        if (camera.isMain) {
            mainCamera = &camera;
            cameraTransform = transformPool.TryGet(entity);
            break;
        }
    }

    if (!mainCamera || !cameraTransform) {
        ME_LOG_WARN("No main camera found!");
        return;
    }

    Math::Mat4 view = mainCamera->GetView(*cameraTransform);
    Math::Mat4 proj = mainCamera->GetProjection();

    // 创建标准PBR着色器（实际应由材质系统管理）
    Shader pbrShader;
    pbrShader.LoadFromSource(s_pbrVertexShader, s_pbrFragmentShader);
    pbrShader.Bind();
    pbrShader.SetMat4("view", view);
    pbrShader.SetMat4("projection", proj);
    pbrShader.SetVec3("viewPos", cameraTransform->position);
    pbrShader.SetMat4("lightSpaceMatrix", m_lightSpaceMatrix);

    // 设置光照
    SetupLighting(&pbrShader, world);

    // 绑定阴影贴图
    if (m_shadowEnabled) {
        m_shadowMap->Bind(5);
        pbrShader.SetInt("shadowMap", 5);
        pbrShader.SetInt("shadowEnabled", 1);
    } else {
        pbrShader.SetInt("shadowEnabled", 0);
    }

    // 执行渲染命令
    for (auto& cmd : m_opaqueQueue) {
        pbrShader.SetMat4("model", cmd.transform);
        // cmd.material->Bind();
        // cmd.mesh->Draw();
        m_stats.drawCalls++;
        // m_stats.triangleCount += cmd.mesh->GetIndexCount() / 3;
    }
}

void Renderer::SetupLighting(Shader* shader, ECS::World* world) {
    auto& lightPool = world->GetComponentPool<ECS::Light>();
    auto& transformPool = world->GetComponentPool<ECS::Transform>();

    // 简化：只设置第一个方向光
    for (auto& [entity, light] : lightPool) {
        if (light.type == ECS::Light::Directional) {
            auto* transform = transformPool.TryGet(entity);
            Math::Vec3 dir = transform ? transform->Forward() : Math::Vec3(0, -1, 0);
            shader->SetVec3("dirLight.direction", dir);
            shader->SetVec3("dirLight.color", Math::Vec3(light.color.r, light.color.g, light.color.b));
            shader->SetFloat("dirLight.intensity", light.intensity);
            break;
        }
    }
}

void Renderer::DrawLine(const Math::Vec3& from, const Math::Vec3& to, const Math::Color& color) {
    m_debugLines.push_back(from.x); m_debugLines.push_back(from.y); m_debugLines.push_back(from.z);
    m_debugLines.push_back(to.x);   m_debugLines.push_back(to.y);   m_debugLines.push_back(to.z);
}

void Renderer::DrawAABB(const Math::AABB& aabb, const Math::Color& color) {
    Math::Vec3 min = aabb.min, max = aabb.max;
    // 12条边
    DrawLine(Math::Vec3(min.x, min.y, min.z), Math::Vec3(max.x, min.y, min.z), color);
    DrawLine(Math::Vec3(max.x, min.y, min.z), Math::Vec3(max.x, max.y, min.z), color);
    DrawLine(Math::Vec3(max.x, max.y, min.z), Math::Vec3(min.x, max.y, min.z), color);
    DrawLine(Math::Vec3(min.x, max.y, min.z), Math::Vec3(min.x, min.y, min.z), color);
    DrawLine(Math::Vec3(min.x, min.y, max.z), Math::Vec3(max.x, min.y, max.z), color);
    DrawLine(Math::Vec3(max.x, min.y, max.z), Math::Vec3(max.x, max.y, max.z), color);
    DrawLine(Math::Vec3(max.x, max.y, max.z), Math::Vec3(min.x, max.y, max.z), color);
    DrawLine(Math::Vec3(min.x, max.y, max.z), Math::Vec3(min.x, min.y, max.z), color);
    DrawLine(Math::Vec3(min.x, min.y, min.z), Math::Vec3(min.x, min.y, max.z), color);
    DrawLine(Math::Vec3(max.x, min.y, min.z), Math::Vec3(max.x, min.y, max.z), color);
    DrawLine(Math::Vec3(max.x, max.y, min.z), Math::Vec3(max.x, max.y, max.z), color);
    DrawLine(Math::Vec3(min.x, max.y, min.z), Math::Vec3(min.x, max.y, max.z), color);
}

} // namespace MiniEngine::Render
```

#### Framebuffer.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"

namespace MiniEngine::Render {

class Framebuffer {
public:
    Framebuffer();
    ~Framebuffer();

    bool Create(u32 width, u32 height);
    void AttachColor(u32 textureID, u32 attachment = 0);
    void AttachDepth(u32 textureID);

    void Bind() const;
    void Unbind() const;
    bool IsComplete() const;

    u32 GetID() const { return m_fbo; }

private:
    u32 m_fbo = 0;
    u32 m_width = 0, m_height = 0;
};

} // namespace MiniEngine::Render
```

```cpp
// Framebuffer.cpp
#include "MiniEngine/Render/Framebuffer.hpp"
#include <glad/glad.h>

namespace MiniEngine::Render {

Framebuffer::Framebuffer() {
    glGenFramebuffers(1, &m_fbo);
}

Framebuffer::~Framebuffer() {
    if (m_fbo) glDeleteFramebuffers(1, &m_fbo);
}

void Framebuffer::Bind() const {
    glBindFramebuffer(GL_FRAMEBUFFER, m_fbo);
}

void Framebuffer::Unbind() const {
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

void Framebuffer::AttachColor(u32 textureID, u32 attachment) {
    Bind();
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0 + attachment,
                           GL_TEXTURE_2D, textureID, 0);
}

void Framebuffer::AttachDepth(u32 textureID) {
    Bind();
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,
                           GL_TEXTURE_2D, textureID, 0);
    // 显式告知OpenGL我们不读取也不写入颜色
    glDrawBuffer(GL_NONE);
    glReadBuffer(GL_NONE);
}

bool Framebuffer::IsComplete() const {
    Bind();
    return glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
}

} // namespace MiniEngine::Render
```

### 2.6 Physics 层

#### PhysicsWorld.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include "MiniEngine/Core/Math.hpp"
#include <vector>

namespace MiniEngine::ECS { class World; }

namespace MiniEngine::Physics {

struct CollisionInfo {
    ECS::Entity entityA;
    ECS::Entity entityB;
    Math::Vec3 normal;
    f32 penetration;
    Math::Vec3 contactPoint;
};

class PhysicsWorld {
public:
    PhysicsWorld();
    ~PhysicsWorld();

    void SetGravity(const Math::Vec3& gravity) { m_gravity = gravity; }
    const Math::Vec3& GetGravity() const { return m_gravity; }

    void Step(f32 deltaTime, ECS::World* ecsWorld);

    // 射线检测
    bool Raycast(const Math::Vec3& origin, const Math::Vec3& direction, f32 maxDistance,
                 CollisionInfo& outHit);

    // 碰撞回调
    using CollisionCallback = std::function<void(const CollisionInfo&)>;
    void SetCollisionCallback(CollisionCallback callback) { m_collisionCallback = callback; }

private:
    void Integrate(f32 deltaTime, ECS::World* ecsWorld);
    void DetectCollisions(ECS::World* ecsWorld);
    void ResolveCollisions();

    Math::Vec3 m_gravity = Math::Vec3(0, -9.81f, 0);
    std::vector<CollisionInfo> m_collisions;
    CollisionCallback m_collisionCallback;
};

} // namespace MiniEngine::Physics
```

#### PhysicsWorld.cpp

```cpp
#include "MiniEngine/Physics/PhysicsWorld.hpp"
#include "MiniEngine/ECS/World.hpp"
#include "MiniEngine/ECS/Components.hpp"
#include "MiniEngine/Core/Log.hpp"
#include "MiniEngine/Core/Profiler.hpp"

namespace MiniEngine::Physics {

PhysicsWorld::PhysicsWorld() = default;
PhysicsWorld::~PhysicsWorld() = default;

void PhysicsWorld::Step(f32 deltaTime, ECS::World* ecsWorld) {
    ME_PROFILE_FUNCTION();
    Integrate(deltaTime, ecsWorld);
    DetectCollisions(ecsWorld);
    ResolveCollisions();
}

void PhysicsWorld::Integrate(f32 deltaTime, ECS::World* ecsWorld) {
    auto& rbPool = ecsWorld->GetComponentPool<ECS::RigidBody>();
    auto& transformPool = ecsWorld->GetComponentPool<ECS::Transform>();

    for (auto& [entity, rb] : rbPool) {
        if (rb.isKinematic) continue;

        auto* transform = transformPool.TryGet(entity);
        if (!transform) continue;

        // 应用重力
        if (rb.useGravity) {
            rb.acceleration += m_gravity;
        }

        // 半隐式欧拉积分
        rb.velocity += rb.acceleration * deltaTime;
        rb.velocity = rb.velocity * (1.0f - rb.drag * deltaTime);
        transform->position += rb.velocity * deltaTime;

        // 重置加速度
        rb.acceleration = Math::Vec3(0);
    }
}

void PhysicsWorld::DetectCollisions(ECS::World* ecsWorld) {
    m_collisions.clear();

    auto& colliderPool = ecsWorld->GetComponentPool<ECS::Collider>();
    auto& transformPool = ecsWorld->GetComponentPool<ECS::Transform>();
    auto& rbPool = ecsWorld->GetComponentPool<ECS::RigidBody>();

    // 更新世界空间包围盒
    for (auto& [entity, collider] : colliderPool) {
        auto* transform = transformPool.TryGet(entity);
        if (!transform) continue;

        Math::Vec3 center = collider.localBounds.Center();
        Math::Vec3 extents = collider.localBounds.Extents();

        // 应用缩放
        extents = extents * transform->scale;

        // 应用旋转和位移（简化：AABB不旋转，只取旋转后的最大 extents）
        Math::Mat4 m = transform->GetMatrix();
        Math::Vec3 worldCenter = m.TransformPoint(center);

        // 计算旋转后的AABB（使用基向量长度）
        Math::Vec3 axisX = Math::Vec3(std::abs(m.m[0]), std::abs(m.m[1]), std::abs(m.m[2]));
        Math::Vec3 axisY = Math::Vec3(std::abs(m.m[4]), std::abs(m.m[5]), std::abs(m.m[6]));
        Math::Vec3 axisZ = Math::Vec3(std::abs(m.m[8]), std::abs(m.m[9]), std::abs(m.m[10]));

        f32 ex = Math::Vec3::Dot(axisX, Math::Vec3(extents.x, 0, 0)) +
                 Math::Vec3::Dot(axisX, Math::Vec3(0, extents.y, 0)) +
                 Math::Vec3::Dot(axisX, Math::Vec3(0, 0, extents.z));
        f32 ey = Math::Vec3::Dot(axisY, Math::Vec3(extents.x, 0, 0)) +
                 Math::Vec3::Dot(axisY, Math::Vec3(0, extents.y, 0)) +
                 Math::Vec3::Dot(axisY, Math::Vec3(0, 0, extents.z));
        f32 ez = Math::Vec3::Dot(axisZ, Math::Vec3(extents.x, 0, 0)) +
                 Math::Vec3::Dot(axisZ, Math::Vec3(0, extents.y, 0)) +
                 Math::Vec3::Dot(axisZ, Math::Vec3(0, 0, extents.z));

        collider.worldBounds = Math::AABB(
            worldCenter - Math::Vec3(ex, ey, ez),
            worldCenter + Math::Vec3(ex, ey, ez)
        );
    }

    // 暴力O(n^2)碰撞检测（实际应用需要空间分割）
    std::vector<ECS::Entity> entities;
    for (auto& [entity, collider] : colliderPool) {
        entities.push_back(entity);
    }

    for (size_t i = 0; i < entities.size(); ++i) {
        for (size_t j = i + 1; j < entities.size(); ++j) {
            auto& colA = colliderPool.Get(entities[i]);
            auto& colB = colliderPool.Get(entities[j]);

            if (!colA.worldBounds.Intersects(colB.worldBounds)) continue;

            // 计算碰撞信息
            CollisionInfo info;
            info.entityA = entities[i];
            info.entityB = entities[j];

            Math::Vec3 centerA = colA.worldBounds.Center();
            Math::Vec3 centerB = colB.worldBounds.Center();
            info.normal = (centerB - centerA).Normalized();
            if (info.normal.LengthSq() < 0.0001f) info.normal = Math::Vec3(0, 1, 0);

            Math::Vec3 overlapMin = Math::Vec3(
                std::max(colA.worldBounds.min.x, colB.worldBounds.min.x),
                std::max(colA.worldBounds.min.y, colB.worldBounds.min.y),
                std::max(colA.worldBounds.min.z, colB.worldBounds.min.z)
            );
            Math::Vec3 overlapMax = Math::Vec3(
                std::min(colA.worldBounds.max.x, colB.worldBounds.max.x),
                std::min(colA.worldBounds.max.y, colB.worldBounds.max.y),
                std::min(colA.worldBounds.max.z, colB.worldBounds.max.z)
            );
            info.penetration = std::min({
                overlapMax.x - overlapMin.x,
                overlapMax.y - overlapMin.y,
                overlapMax.z - overlapMin.z
            });
            info.contactPoint = (centerA + centerB) * 0.5f;

            m_collisions.push_back(info);
        }
    }
}

void PhysicsWorld::ResolveCollisions() {
    for (auto& collision : m_collisions) {
        auto* rbA = m_world->TryGetComponent<ECS::RigidBody>(collision.entityA);
        auto* rbB = m_world->TryGetComponent<ECS::RigidBody>(collision.entityB);
        auto* tA = m_world->TryGetComponent<ECS::Transform>(collision.entityA);
        auto* tB = m_world->TryGetComponent<ECS::Transform>(collision.entityB);

        if (!tA || !tB) continue;

        // 位置修正（防止穿透）
        if (!rbA || rbA->isKinematic) {
            if (rbB && !rbB->isKinematic) {
                tB->position += collision.normal * collision.penetration;
            }
        } else if (!rbB || rbB->isKinematic) {
            tA->position -= collision.normal * collision.penetration;
        } else {
            f32 totalMass = rbA->mass + rbB->mass;
            tA->position -= collision.normal * collision.penetration * (rbB->mass / totalMass);
            tB->position += collision.normal * collision.penetration * (rbA->mass / totalMass);
        }

        // 简单弹性碰撞响应
        if (rbA && !rbA->isKinematic && rbB && !rbB->isKinematic) {
            Math::Vec3 relativeVel = rbB->velocity - rbA->velocity;
            f32 velAlongNormal = Math::Vec3::Dot(relativeVel, collision.normal);

            if (velAlongNormal > 0) continue; // 已经在分离

            f32 restitution = 0.5f; // 弹性系数
            f32 impulseScalar = -(1.0f + restitution) * velAlongNormal;
            impulseScalar /= (1.0f / rbA->mass + 1.0f / rbB->mass);

            Math::Vec3 impulse = impulseScalar * collision.normal;
            rbA->velocity -= impulse / rbA->mass;
            rbB->velocity += impulse / rbB->mass;
        } else if (rbA && !rbA->isKinematic) {
            rbA->velocity -= 2.0f * Math::Vec3::Dot(rbA->velocity, collision.normal) * collision.normal;
            rbA->velocity *= 0.5f; // 能量损失
        } else if (rbB && !rbB->isKinematic) {
            rbB->velocity -= 2.0f * Math::Vec3::Dot(rbB->velocity, collision.normal) * collision.normal;
            rbB->velocity *= 0.5f;
        }

        if (m_collisionCallback) {
            m_collisionCallback(collision);
        }
    }
}

bool PhysicsWorld::Raycast(const Math::Vec3& origin, const Math::Vec3& direction,
                           f32 maxDistance, CollisionInfo& outHit) {
    // 简化实现：遍历所有AABB做射线-AABB相交测试
    // 实际应用应使用BVH或八叉树加速
    return false;
}

} // namespace MiniEngine::Physics
```

### 2.7 Audio 层

#### AudioEngine.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include "MiniEngine/Core/Math.hpp"
#include <string>
#include <vector>
#include <memory>
#include <unordered_map>

// miniaudio 前向声明
struct ma_engine;
struct ma_sound;

namespace MiniEngine::Audio {

struct AudioClip {
    std::string path;
    ma_sound* sound = nullptr;
    bool loaded = false;
};

class AudioEngine {
public:
    AudioEngine();
    ~AudioEngine();

    bool Initialize();
    void Shutdown();

    // 加载音频
    u32 LoadClip(const std::string& path);
    void UnloadClip(u32 clipID);

    // 播放控制
    void Play(u32 clipID, bool loop = false);
    void Stop(u32 clipID);
    void SetVolume(u32 clipID, f32 volume);
    void SetPitch(u32 clipID, f32 pitch);

    // 3D 音频
    void SetListenerPosition(const Math::Vec3& position);
    void SetListenerDirection(const Math::Vec3& forward, const Math::Vec3& up);
    void SetSourcePosition(u32 clipID, const Math::Vec3& position);
    void SetSourceRange(u32 clipID, f32 minDistance, f32 maxDistance);

    // 全局设置
    void SetMasterVolume(f32 volume);
    void SetPaused(bool paused);

private:
    ma_engine* m_engine = nullptr;
    std::unordered_map<u32, std::unique_ptr<AudioClip>> m_clips;
    u32 m_nextClipID = 1;
};

} // namespace MiniEngine::Audio
```

#### AudioEngine.cpp

```cpp
#include "MiniEngine/Audio/AudioEngine.hpp"
#include "MiniEngine/Core/Log.hpp"
#define MINIAUDIO_IMPLEMENTATION
#include <miniaudio.h>

namespace MiniEngine::Audio {

AudioEngine::AudioEngine() = default;
AudioEngine::~AudioEngine() { Shutdown(); }

bool AudioEngine::Initialize() {
    m_engine = new ma_engine();
    ma_result result = ma_engine_init(nullptr, m_engine);
    if (result != MA_SUCCESS) {
        ME_LOG_ERROR("Failed to initialize audio engine");
        delete m_engine;
        m_engine = nullptr;
        return false;
    }
    ME_LOG_INFO("Audio engine initialized");
    return true;
}

void AudioEngine::Shutdown() {
    m_clips.clear();
    if (m_engine) {
        ma_engine_uninit(m_engine);
        delete m_engine;
        m_engine = nullptr;
    }
}

u32 AudioEngine::LoadClip(const std::string& path) {
    if (!m_engine) return 0;

    auto clip = std::make_unique<AudioClip>();
    clip->path = path;
    clip->sound = new ma_sound();

    ma_result result = ma_sound_init_from_file(m_engine, path.c_str(),
        MA_SOUND_FLAG_DECODE | MA_SOUND_FLAG_ASYNC, nullptr, nullptr, clip->sound);

    if (result != MA_SUCCESS) {
        ME_LOG_ERROR("Failed to load audio: {}", path);
        delete clip->sound;
        return 0;
    }

    u32 id = m_nextClipID++;
    clip->loaded = true;
    m_clips[id] = std::move(clip);
    return id;
}

void AudioEngine::UnloadClip(u32 clipID) {
    auto it = m_clips.find(clipID);
    if (it == m_clips.end()) return;
    ma_sound_uninit(it->second->sound);
    delete it->second->sound;
    m_clips.erase(it);
}

void AudioEngine::Play(u32 clipID, bool loop) {
    auto it = m_clips.find(clipID);
    if (it == m_clips.end()) return;
    ma_sound_set_looping(it->second->sound, loop);
    ma_sound_start(it->second->sound);
}

void AudioEngine::Stop(u32 clipID) {
    auto it = m_clips.find(clipID);
    if (it == m_clips.end()) return;
    ma_sound_stop(it->second->sound);
}

void AudioEngine::SetVolume(u32 clipID, f32 volume) {
    auto it = m_clips.find(clipID);
    if (it == m_clips.end()) return;
    ma_sound_set_volume(it->second->sound, volume);
}

void AudioEngine::SetPitch(u32 clipID, f32 pitch) {
    auto it = m_clips.find(clipID);
    if (it == m_clips.end()) return;
    ma_sound_set_pitch(it->second->sound, pitch);
}

void AudioEngine::SetListenerPosition(const Math::Vec3& position) {
    if (!m_engine) return;
    ma_engine_listener_set_position(m_engine, 0, position.x, position.y, position.z);
}

void AudioEngine::SetListenerDirection(const Math::Vec3& forward, const Math::Vec3& up) {
    if (!m_engine) return;
    ma_engine_listener_set_direction(m_engine, 0, forward.x, forward.y, forward.z);
    ma_engine_listener_set_world_up(m_engine, 0, up.x, up.y, up.z);
}

void AudioEngine::SetSourcePosition(u32 clipID, const Math::Vec3& position) {
    auto it = m_clips.find(clipID);
    if (it == m_clips.end()) return;
    ma_sound_set_position(it->second->sound, position.x, position.y, position.z);
}

void AudioEngine::SetSourceRange(u32 clipID, f32 minDistance, f32 maxDistance) {
    auto it = m_clips.find(clipID);
    if (it == m_clips.end()) return;
    ma_sound_set_min_distance(it->second->sound, minDistance);
    ma_sound_set_max_distance(it->second->sound, maxDistance);
}

void AudioEngine::SetMasterVolume(f32 volume) {
    if (m_engine) ma_engine_set_volume(m_engine, volume);
}

void AudioEngine::SetPaused(bool paused) {
    if (!m_engine) return;
    if (paused) ma_engine_stop(m_engine);
    else ma_engine_start(m_engine);
}

} // namespace MiniEngine::Audio
```

### 2.8 Application 层

#### Application.hpp

```cpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include <memory>
#include <functional>

struct GLFWwindow;

namespace MiniEngine::ECS { class World; }
namespace MiniEngine::Render { class Renderer; }
namespace MiniEngine::Physics { class PhysicsWorld; }
namespace MiniEngine::Audio { class AudioEngine; }

namespace MiniEngine::App {

class Application {
public:
    Application(const std::string& title, u32 width, u32 height);
    virtual ~Application();

    bool Initialize();
    void Run();
    void Shutdown();

    void Stop() { m_running = false; }

    // 子系统访问
    ECS::World* GetWorld() const { return m_world.get(); }
    Render::Renderer* GetRenderer() const { return m_renderer.get(); }
    Physics::PhysicsWorld* GetPhysics() const { return m_physics.get(); }
    Audio::AudioEngine* GetAudio() const { return m_audio.get(); }

    f32 GetDeltaTime() const { return m_deltaTime; }
    f32 GetFPS() const { return m_fps; }

    // 事件回调
    using UpdateCallback = std::function<void(f32)>;
    using FixedUpdateCallback = std::function<void(f32)>;
    using RenderCallback = std::function<void()>;

    void SetUpdateCallback(UpdateCallback cb) { m_updateCallback = cb; }
    void SetFixedUpdateCallback(FixedUpdateCallback cb) { m_fixedUpdateCallback = cb; }
    void SetRenderCallback(RenderCallback cb) { m_renderCallback = cb; }

protected:
    virtual void OnInitialize() {}
    virtual void OnUpdate(f32 deltaTime) {}
    virtual void OnFixedUpdate(f32 fixedDeltaTime) {}
    virtual void OnRender() {}
    virtual void OnShutdown() {}

private:
    void ProcessInput();
    void UpdateWindowTitle();

    std::string m_title;
    u32 m_width, m_height;
    GLFWwindow* m_window = nullptr;
    bool m_running = false;

    std::unique_ptr<ECS::World> m_world;
    std::unique_ptr<Render::Renderer> m_renderer;
    std::unique_ptr<Physics::PhysicsWorld> m_physics;
    std::unique_ptr<Audio::AudioEngine> m_audio;

    // 时间
    f64 m_lastFrameTime = 0;
    f32 m_deltaTime = 0;
    f32 m_fps = 0;
    f32 m_fpsAccumulator = 0;
    u32 m_fpsFrameCount = 0;

    // 固定时间步
    static constexpr f32 FIXED_TIMESTEP = 1.0f / 60.0f;
    f32 m_accumulator = 0;

    // 回调
    UpdateCallback m_updateCallback;
    FixedUpdateCallback m_fixedUpdateCallback;
    RenderCallback m_renderCallback;
};

} // namespace MiniEngine::App
```

#### Application.cpp

```cpp
#include "MiniEngine/App/Application.hpp"
#include "MiniEngine/App/Window.hpp"
#include "MiniEngine/App/Input.hpp"
#include "MiniEngine/ECS/World.hpp"
#include "MiniEngine/ECS/Components.hpp"
#include "MiniEngine/Render/Renderer.hpp"
#include "MiniEngine/Physics/PhysicsWorld.hpp"
#include "MiniEngine/Audio/AudioEngine.hpp"
#include "MiniEngine/Core/Log.hpp"
#include "MiniEngine/Core/Profiler.hpp"
#include <glad/glad.h>
#include <GLFW/glfw3.h>

namespace MiniEngine::App {

static Application* s_instance = nullptr;

static void GLFWErrorCallback(int error, const char* description) {
    ME_LOG_ERROR("GLFW Error {}: {}", error, description);
}

static void GLFWFramebufferSizeCallback(GLFWwindow* window, int width, int height) {
    if (s_instance && s_instance->GetRenderer()) {
        s_instance->GetRenderer()->SetViewport(0, 0, width, height);
    }
}

Application::Application(const std::string& title, u32 width, u32 height)
    : m_title(title), m_width(width), m_height(height) {
    s_instance = this;
}

Application::~Application() = default;

bool Application::Initialize() {
    Log::Init();
    ME_LOG_INFO("Initializing MiniEngine...");

    // GLFW
    glfwSetErrorCallback(GLFWErrorCallback);
    if (!glfwInit()) {
        ME_LOG_FATAL("Failed to initialize GLFW");
        return false;
    }

    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
#ifdef __APPLE__
    glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE);
#endif

    m_window = glfwCreateWindow(m_width, m_height, m_title.c_str(), nullptr, nullptr);
    if (!m_window) {
        ME_LOG_FATAL("Failed to create window");
        glfwTerminate();
        return false;
    }

    glfwMakeContextCurrent(m_window);
    glfwSetFramebufferSizeCallback(m_window, GLFWFramebufferSizeCallback);
    glfwSwapInterval(1); // VSync

    // GLAD
    if (!gladLoadGLLoader((GLADloadproc)glfwGetProcAddress)) {
        ME_LOG_FATAL("Failed to initialize GLAD");
        return false;
    }

    ME_LOG_INFO("OpenGL {}.{} initialized", GLVersion.major, GLVersion.minor);

    // 子系统
    m_world = std::make_unique<ECS::World>();
    m_renderer = std::make_unique<Render::Renderer>();
    m_physics = std::make_unique<Physics::PhysicsWorld>();
    m_audio = std::make_unique<Audio::AudioEngine>();

    if (!m_renderer->Initialize(m_width, m_height)) return false;
    if (!m_audio->Initialize()) {
        ME_LOG_WARN("Audio initialization failed, continuing without audio");
    }

    Input::Initialize(m_window);
    OnInitialize();

    m_running = true;
    m_lastFrameTime = glfwGetTime();
    return true;
}

void Application::Run() {
    while (m_running && !glfwWindowShouldClose(m_window)) {
        ME_PROFILE_SCOPE("Frame");
        Profiler::Instance().BeginFrame();

        // 计算delta time
        f64 currentTime = glfwGetTime();
        m_deltaTime = static_cast<f32>(currentTime - m_lastFrameTime);
        m_lastFrameTime = currentTime;

        // 限制最大delta time防止调试时的跳跃
        if (m_deltaTime > 0.1f) m_deltaTime = 0.1f;

        // FPS计算
        m_fpsAccumulator += m_deltaTime;
        m_fpsFrameCount++;
        if (m_fpsAccumulator >= 1.0f) {
            m_fps = static_cast<f32>(m_fpsFrameCount) / m_fpsAccumulator;
            m_fpsAccumulator = 0;
            m_fpsFrameCount = 0;
            UpdateWindowTitle();
        }

        // 处理输入
        ProcessInput();

        // 固定步长更新
        m_accumulator += m_deltaTime;
        while (m_accumulator >= FIXED_TIMESTEP) {
            ME_PROFILE_SCOPE("FixedUpdate");
            m_physics->Step(FIXED_TIMESTEP, m_world.get());
            m_world->FixedUpdate(FIXED_TIMESTEP);
            if (m_fixedUpdateCallback) m_fixedUpdateCallback(FIXED_TIMESTEP);
            OnFixedUpdate(FIXED_TIMESTEP);
            m_accumulator -= FIXED_TIMESTEP;
        }

        // 可变帧率更新
        {
            ME_PROFILE_SCOPE("Update");
            m_world->Update(m_deltaTime);
            if (m_updateCallback) m_updateCallback(m_deltaTime);
            OnUpdate(m_deltaTime);
        }

        // 渲染
        {
            ME_PROFILE_SCOPE("Render");
            m_renderer->RenderFrame(m_world.get());
            if (m_renderCallback) m_renderCallback();
            OnRender();
        }

        // 交换缓冲
        glfwSwapBuffers(m_window);
        glfwPollEvents();

        Profiler::Instance().EndFrame();
    }
}

void Application::Shutdown() {
    OnShutdown();
    m_audio->Shutdown();
    m_renderer->Shutdown();
    Input::Shutdown();
    glfwDestroyWindow(m_window);
    glfwTerminate();
    s_instance = nullptr;
    ME_LOG_INFO("MiniEngine shutdown complete");
}

void Application::ProcessInput() {
    Input::Update();
    if (Input::IsKeyPressed(GLFW_KEY_ESCAPE)) {
        m_running = false;
    }
}

void Application::UpdateWindowTitle() {
    std::string title = m_title + " | FPS: " + std::to_string(static_cast<int>(m_fps));
    glfwSetWindowTitle(m_window, title.c_str());
}

} // namespace MiniEngine::App
```

#### Input.hpp / Input.cpp

```cpp
// Input.hpp
#pragma once
#include "MiniEngine/Core/Types.hpp"
#include "MiniEngine/Core/Math.hpp"
#include <unordered_map>
#include <vector>

struct GLFWwindow;

namespace MiniEngine::App {

class Input {
public:
    static void Initialize(GLFWwindow* window);
    static void Shutdown();
    static void Update();

    // 键盘
    static bool IsKeyPressed(int key);
    static bool IsKeyDown(int key);      // 本帧刚按下
    static bool IsKeyReleased(int key);  // 本帧刚释放

    // 鼠标
    static bool IsMouseButtonPressed(int button);
    static Math::Vec2 GetMousePosition();
    static Math::Vec2 GetMouseDelta();
    static f32 GetMouseScroll();

    // 光标模式
    static void SetCursorVisible(bool visible);
    static void SetCursorLocked(bool locked);

private:
    static GLFWwindow* s_window;
    static std::unordered_map<int, bool> s_currentKeys;
    static std::unordered_map<int, bool> s_previousKeys;
    static std::unordered_map<int, bool> s_currentMouse;
    static std::unordered_map<int, bool> s_previousMouse;
    static Math::Vec2 s_mousePos;
    static Math::Vec2 s_lastMousePos;
    static Math::Vec2 s_mouseDelta;
    static f32 s_mouseScroll;
};

} // namespace MiniEngine::App
```

```cpp
// Input.cpp
#include "MiniEngine/App/Input.hpp"
#include <GLFW/glfw3.h>

namespace MiniEngine::App {

GLFWwindow* Input::s_window = nullptr;
std::unordered_map<int, bool> Input::s_currentKeys;
std::unordered_map<int, bool> Input::s_previousKeys;
std::unordered_map<int, bool> Input::s_currentMouse;
std::unordered_map<int, bool> Input::s_previousMouse;
Math::Vec2 Input::s_mousePos;
Math::Vec2 Input::s_lastMousePos;
Math::Vec2 Input::s_mouseDelta;
f32 Input::s_mouseScroll = 0;

static void ScrollCallback(GLFWwindow*, double, double yoffset) {
    Input::s_mouseScroll += static_cast<f32>(yoffset);
}

void Input::Initialize(GLFWwindow* window) {
    s_window = window;
    glfwSetScrollCallback(window, ScrollCallback);
}

void Input::Shutdown() {
    s_window = nullptr;
}

void Input::Update() {
    s_previousKeys = s_currentKeys;
    s_previousMouse = s_currentMouse;

    // 更新键盘状态
    for (int key = GLFW_KEY_SPACE; key <= GLFW_KEY_LAST; ++key) {
        s_currentKeys[key] = glfwGetKey(s_window, key) == GLFW_PRESS;
    }

    // 更新鼠标按钮
    for (int button = GLFW_MOUSE_BUTTON_1; button <= GLFW_MOUSE_BUTTON_LAST; ++button) {
        s_currentMouse[button] = glfwGetMouseButton(s_window, button) == GLFW_PRESS;
    }

    // 更新鼠标位置
    s_lastMousePos = s_mousePos;
    double x, y;
    glfwGetCursorPos(s_window, &x, &y);
    s_mousePos = Math::Vec2(static_cast<f32>(x), static_cast<f32>(y));
    s_mouseDelta = s_mousePos - s_lastMousePos;
}

bool Input::IsKeyPressed(int key) {
    return s_currentKeys[key];
}

bool Input::IsKeyDown(int key) {
    return s_currentKeys[key] && !s_previousKeys[key];
}

bool Input::IsKeyReleased(int key) {
    return !s_currentKeys[key] && s_previousKeys[key];
}

bool Input::IsMouseButtonPressed(int button) {
    return s_currentMouse[button];
}

Math::Vec2 Input::GetMousePosition() {
    return s_mousePos;
}

Math::Vec2 Input::GetMouseDelta() {
    return s_mouseDelta;
}

f32 Input::GetMouseScroll() {
    f32 scroll = s_mouseScroll;
    s_mouseScroll = 0;
    return scroll;
}

void Input::SetCursorVisible(bool visible) {
    glfwSetInputMode(s_window, GLFW_CURSOR,
        visible ? GLFW_CURSOR_NORMAL : GLFW_CURSOR_DISABLED);
}

void Input::SetCursorLocked(bool locked) {
    glfwSetInputMode(s_window, GLFW_CURSOR,
        locked ? GLFW_CURSOR_DISABLED : GLFW_CURSOR_NORMAL);
}

} // namespace MiniEngine::App
```

### 2.9 游戏示例 — 使用引擎

```cpp
// game/src/Main.cpp
#include <MiniEngine/App/Application.hpp>
#include <MiniEngine/App/Input.hpp>
#include <MiniEngine/ECS/World.hpp>
#include <MiniEngine/ECS/Components.hpp>
#include <MiniEngine/Render/Renderer.hpp>
#include <MiniEngine/Core/Math.hpp>
#include <MiniEngine/Core/Log.hpp>
#include <GLFW/glfw3.h>

using namespace MiniEngine;

class GameApp : public App::Application {
public:
    GameApp() : App::Application("MiniEngine Demo", 1280, 720) {}

    void OnInitialize() override {
        ME_LOG_INFO("Game initializing...");

        auto* world = GetWorld();

        // 创建相机
        {
            auto camera = world->CreateEntity();
            world->AddComponent<ECS::Tag>(camera, ECS::Tag{"MainCamera"});
            auto& transform = world->AddComponent<ECS::Transform>(camera);
            transform.position = Math::Vec3(0, 5, 10);
            transform.rotation = Math::Quat::FromAxisAngle(Math::Vec3(1, 0, 0), -0.4f);
            auto& cam = world->AddComponent<ECS::Camera>(camera);
            cam.isMain = true;
            cam.aspect = 1280.0f / 720.0f;
            m_cameraEntity = camera;
        }

        // 创建方向光
        {
            auto light = world->CreateEntity();
            world->AddComponent<ECS::Tag>(light, ECS::Tag{"Sun"});
            auto& transform = world->AddComponent<ECS::Transform>(light);
            transform.rotation = Math::Quat::FromAxisAngle(Math::Vec3(1, 0, 0), -0.8f) *
                                 Math::Quat::FromAxisAngle(Math::Vec3(0, 1, 0), 0.5f);
            auto& lightComp = world->AddComponent<ECS::Light>(light);
            lightComp.type = ECS::Light::Directional;
            lightComp.color = Math::Color(1.0f, 0.95f, 0.8f);
            lightComp.intensity = 2.0f;
            lightComp.castShadow = true;
        }

        // 创建地面
        {
            auto ground = world->CreateEntity();
            world->AddComponent<ECS::Tag>(ground, ECS::Tag{"Ground"});
            auto& transform = world->AddComponent<ECS::Transform>(ground);
            transform.position = Math::Vec3(0, -1, 0);
            transform.scale = Math::Vec3(20, 1, 20);
            auto& collider = world->AddComponent<ECS::Collider>(ground);
            collider.localBounds = Math::AABB(Math::Vec3(-0.5f), Math::Vec3(0.5f));
            auto& rb = world->AddComponent<ECS::RigidBody>(ground);
            rb.isKinematic = true;
            rb.mass = 0;
        }

        // 创建几个箱子
        for (int i = 0; i < 5; ++i) {
            auto box = world->CreateEntity();
            world->AddComponent<ECS::Tag>(box, ECS::Tag{"Box" + std::to_string(i)});
            auto& transform = world->AddComponent<ECS::Transform>(box);
            transform.position = Math::Vec3(i * 2.0f - 4.0f, 5.0f + i * 2.0f, 0);
            transform.rotation = Math::Quat::FromAxisAngle(Math::Vec3(0, 1, 0), i * 0.5f);
            auto& collider = world->AddComponent<ECS::Collider>(box);
            collider.localBounds = Math::AABB(Math::Vec3(-0.5f), Math::Vec3(0.5f));
            auto& rb = world->AddComponent<ECS::RigidBody>(box);
            rb.mass = 1.0f + i * 0.5f;
            rb.useGravity = true;
        }

        // 隐藏鼠标
        App::Input::SetCursorLocked(true);
    }

    void OnUpdate(f32 deltaTime) override {
        // 相机控制
        auto* world = GetWorld();
        auto& camTransform = world->GetComponent<ECS::Transform>(m_cameraEntity);

        f32 speed = 5.0f * deltaTime;
        if (App::Input::IsKeyPressed(GLFW_KEY_LEFT_SHIFT)) speed *= 3.0f;

        Math::Vec3 moveDir(0);
        if (App::Input::IsKeyPressed(GLFW_KEY_W)) moveDir += camTransform.Forward();
        if (App::Input::IsKeyPressed(GLFW_KEY_S)) moveDir -= camTransform.Forward();
        if (App::Input::IsKeyPressed(GLFW_KEY_A)) moveDir -= camTransform.Right();
        if (App::Input::IsKeyPressed(GLFW_KEY_D)) moveDir += camTransform.Right();
        if (App::Input::IsKeyPressed(GLFW_KEY_Q)) moveDir -= Math::Vec3(0, 1, 0);
        if (App::Input::IsKeyPressed(GLFW_KEY_E)) moveDir += Math::Vec3(0, 1, 0);

        if (moveDir.LengthSq() > 0) {
            camTransform.position += moveDir.Normalized() * speed;
        }

        // 鼠标视角
        Math::Vec2 mouseDelta = App::Input::GetMouseDelta();
        f32 sensitivity = 0.002f;
        f32 yaw = -mouseDelta.x * sensitivity;
        f32 pitch = -mouseDelta.y * sensitivity;

        Math::Quat yawRot = Math::Quat::FromAxisAngle(Math::Vec3(0, 1, 0), yaw);
        Math::Quat pitchRot = Math::Quat::FromAxisAngle(camTransform.Right(), pitch);
        camTransform.rotation = yawRot * camTransform.rotation * pitchRot;
        camTransform.rotation = camTransform.rotation.Normalized();

        // 音频监听器跟随相机
        if (GetAudio()) {
            GetAudio()->SetListenerPosition(camTransform.position);
            GetAudio()->SetListenerDirection(camTransform.Forward(), camTransform.Up());
        }
    }

    void OnFixedUpdate(f32 fixedDeltaTime) override {
        // 物理相关的游戏逻辑
    }

    void OnRender() override {
        // ImGui 调试面板等
    }

    void OnShutdown() override {
        App::Input::SetCursorLocked(false);
    }

private:
    ECS::Entity m_cameraEntity = ECS::Entity::Invalid();
};

int main() {
    GameApp app;
    if (!app.Initialize()) {
        return -1;
    }
    app.Run();
    app.Shutdown();
    return 0;
}
```

### 2.10 engine/CMakeLists.txt

```cmake
# engine/CMakeLists.txt

file(GLOB_RECURSE ENGINE_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/core/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/render/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/physics/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/animation/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/audio/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/ecs/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/resources/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/app/src/*.cpp
)

file(GLOB_RECURSE ENGINE_HEADERS
    ${CMAKE_CURRENT_SOURCE_DIR}/core/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/render/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/physics/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/animation/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/audio/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/ecs/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/resources/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/app/include/*.hpp
)

add_library(MiniEngine STATIC ${ENGINE_SOURCES} ${ENGINE_HEADERS})

target_include_directories(MiniEngine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/core/include
    ${CMAKE_CURRENT_SOURCE_DIR}/render/include
    ${CMAKE_CURRENT_SOURCE_DIR}/physics/include
    ${CMAKE_CURRENT_SOURCE_DIR}/animation/include
    ${CMAKE_CURRENT_SOURCE_DIR}/audio/include
    ${CMAKE_CURRENT_SOURCE_DIR}/ecs/include
    ${CMAKE_CURRENT_SOURCE_DIR}/resources/include
    ${CMAKE_CURRENT_SOURCE_DIR}/app/include
    ${CMAKE_SOURCE_DIR}/third_party/glad/include
    ${CMAKE_SOURCE_DIR}/third_party/glfw/include
    ${CMAKE_SOURCE_DIR}/third_party/imgui
    ${CMAKE_SOURCE_DIR}/third_party/spdlog/include
    ${CMAKE_SOURCE_DIR}/third_party/stb
    ${CMAKE_SOURCE_DIR}/third_party/miniaudio
)

target_link_libraries(MiniEngine PUBLIC
    glad
    glfw
    imgui
    spdlog
)

# 平台特定库
if(WIN32)
    target_link_libraries(MiniEngine PUBLIC opengl32)
elseif(UNIX AND NOT APPLE)
    target_link_libraries(MiniEngine PUBLIC GL dl pthread m)
elseif(APPLE)
    target_link_libraries(MiniEngine PUBLIC "-framework OpenGL" "-framework Cocoa"
                                             "-framework IOKit" "-framework CoreVideo")
endif()
```

### 2.11 game/CMakeLists.txt

```cmake
# game/CMakeLists.txt

add_executable(Game
    src/Main.cpp
)

target_link_libraries(Game PRIVATE MiniEngine)

# 复制资源文件
add_custom_command(TARGET Game POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
    ${CMAKE_CURRENT_SOURCE_DIR}/assets
    $<TARGET_FILE_DIR:Game>/assets
)
```

---

## 3. 练习

### 练习 1：完善渲染系统（预计 3h）

当前Renderer.cpp中的`SubmitRenderCommands`和`MainPass`中缺少实际的Mesh和Material绑定代码。请完成以下任务：

1. 创建`ResourceManager`类，管理Mesh、Texture、Material、Shader的加载和缓存
2. 实现`MeshRenderer`组件在场景加载时自动解析`meshPath`和`materialPath`
3. 修改`Renderer::SubmitRenderCommands`，从ResourceManager获取实际的Mesh和Material指针
4. 确保材质切换时正确绑定纹理和设置uniform

**提示**：使用`std::unordered_map<std::string, std::shared_ptr<T>>`作为资源缓存，支持引用计数自动卸载。

### 练习 2：实现空间分割加速结构（预计 4h）

当前物理系统的碰撞检测是暴力O(n^2)，在实体数量增加时性能急剧下降。请实现以下之一：

**选项A：均匀网格（Uniform Grid）**
- 将世界空间划分为固定大小的网格单元
- 每个碰撞体根据其AABB中心点注册到对应网格
- 只检测同一网格和相邻网格中的碰撞体对

**选项B：BVH（Bounding Volume Hierarchy）**
- 使用自顶向下或自底向上的方式构建AABB树
- 每帧更新时采用"refit"策略（只更新叶子节点，自底向上重新计算父节点AABB）
- 使用递归或栈实现树的遍历

**验证**：创建100个动态碰撞体，对比优化前后的帧率。

### 练习 3（可选）：添加后期处理管线（预计 6h）

实现一个完整的后期处理系统：

1. 创建`PostProcess`类，管理多个后处理效果的链式执行
2. 实现以下效果：
   - **Bloom**：提取高亮区域 → 高斯模糊 → 混合
   - **Tone Mapping**：Reinhard或ACES
   - **FXAA**：快速近似抗锯齿
   - **Vignette**：暗角效果
3. 使用ping-pong framebuffer在两个纹理间交替渲染
4. 在ImGui面板中添加效果开关和参数调节

**架构提示**：
```cpp
class PostProcess {
    void AddEffect(std::unique_ptr<PostProcessEffect> effect);
    void Render(Texture* sceneColor, Texture* sceneDepth);
};
```

---

## 3. 前置项目：软渲染器（Software Rasterizer）

在构建基于GPU的MiniEngine之前，强烈建议先完成一个**CPU软渲染器**项目。软渲染器完全在CPU上执行光栅化过程，不依赖GPU硬件加速。这个经历会让你在面对GPU上的调试难题时拥有直觉性的判断力——当屏幕上出现错误像素时，你能从CPU端验证管线的数学正确性。

### 3.1 为什么需要软渲染器

硬件加速是一层抽象，它隐藏了光栅化的内部机制。软渲染器要求你亲手实现每一个步骤：从三维顶点坐标到屏幕像素颜色的完整映射。完成软渲染器后，你将拥有一项宝贵的能力：**CPU与GPU交叉验证**——当GPU渲染出现视觉错误时，你能够判断问题出在几何、光栅化还是着色阶段。

### 3.2 管线架构

```
输入层 (VBO + 纹理 + Uniforms)
    ↓
顶点阶段 (Vertex Shader: MVP变换)
    ↓
光栅化阶段 (图元装配 → 背面剔除 → Edge Function扫描 → 属性插值)
    ↓
片段阶段 (Fragment Shader: 纹理采样 + 光照计算)
    ↓
深度测试 (Z-Buffer)
    ↓
颜色输出 (帧缓冲区)
```

### 3.3 核心实现要点

**Edge Function光栅化**：利用有符号距离判断像素是否在三角形内部。对于三角形每条边，定义线性函数 `E(x,y) = (x-x_A)(y_B-y_A) - (y-y_A)(x_B-x_A)`。若一点对三条边的E值同号，则在三角形内部。

**透视校正纹理映射**：直接在屏幕空间线性插值UV会导致近大远小的失真。正确做法是在屏幕空间中对 `u/z`、`v/z` 和 `1/z` 进行线性插值，然后在每个像素处恢复正确的UV值：

```
ubar = (Σ wi · ui/zi) / (Σ wi · 1/zi)
vbar = (Σ wi · vi/zi) / (Σ wi · 1/zi)
```

**Z-Buffer与Early-Z**：为每个像素维护深度值。现代GPU的Early-Z技术在片段着色器执行前进行深度测试，避免为被遮挡像素执行昂贵的着色计算。Reverse-Z技术将深度映射反转（近处=1.0，远处=0.0），利用浮点数在0附近精度更高的特性改善远距离深度分辨率。

### 3.4 项目阶段检查表

| 阶段 | 实现内容 | 验证标准 | 预计耗时 |
|------|----------|----------|----------|
| Stage 0 | 数学库（Vec3/Vec4/Mat4） | 矩阵乘法、逆矩阵单元测试通过 | 1-2天 |
| Stage 1 | 线框渲染 | 正确显示模型边线 | 1天 |
| Stage 2 | 顶点处理 + 透视投影 | 模型正确投影到屏幕 | 1天 |
| Stage 3 | Edge Function光栅化 + Z-Buffer | 实心填充，深度关系正确 | 2-3天 |
| Stage 4 | 透视校正纹理映射 | 纹理无近大远小失真 | 2天 |
| Stage 5 | Gouraud/Phong光照 | 有明暗变化 | 1-2天 |
| Stage 6 | 双线性纹理过滤 + OBJ加载 | 支持外部模型和纹理 | 2天 |
| Stage 7 | 优化（增量Edge Function + SIMD） | 帧率提升3x+ | 2-3天 |

---

## 4. 进阶特性实现

基础Mini引擎运行起来后，接下来的目标是逐步添加现代引擎中的关键特性。本节聚焦于四个核心模块：**延迟渲染管线**、**IBL环境光照**、**动画状态机**和**Lua脚本绑定**。

### 4.1 延迟渲染管线（Deferred Rendering）

当场景中存在大量动态光源时，前向渲染的性能急剧下降——每个光源都需要对所有受影响的物体执行一次绘制。延迟渲染通过将几何信息预先写入多个缓冲区（G-Buffer），再将光照计算推迟到一个全屏Pass中，实现了光源数量与场景复杂度的大幅解耦。

**G-Buffer布局**：

| 附件 | 格式 | 内容 | 用途 |
|------|------|------|------|
| GBuffer0 (Albedo) | RGBA8 | albedo.rgb + ao | 漫反射颜色和环境遮蔽 |
| GBuffer1 (Normal) | RGB10A2 | worldNormal.xyz | 光照方向计算 |
| GBuffer2 (Material) | RGBA8 | metallic, roughness, emissive, shaderID | BRDF参数 |
| Depth | D24S8 | depth | 深度测试和位置重建 |

位置通常不直接存储，而是通过深度缓冲和逆ViewProj矩阵重建：

```glsl
vec3 ReconstructWorldPos(vec2 uv, float depth) {
    vec4 clipPos = vec4(uv * 2.0 - 1.0, depth, 1.0);
    vec4 worldPos = uInvViewProj * clipPos;
    return worldPos.xyz / worldPos.w;
}
```

**延迟渲染的优势与劣势**：
- 优势：光源数量与场景复杂度解耦；天然支持高复杂度光照场景
- 劣势：高带宽需求（G-Buffer多个附件写入）；不支持MSAA；半透明物体需单独前向渲染Pass

现代引擎通常采用**混合方案**：不透明物体用延迟渲染，透明物体和特殊效果用前向渲染。

### 4.2 IBL环境光照

基于图像的光照（Image-Based Lighting, IBL）使用环境贴图（Environment Map）来模拟间接光照。完整的PBR材质系统应包含：

**漫反射环境光**：用辐照度贴图（Irradiance Map）预计算漫反射积分
**镜面反射环境光**：用预过滤环境贴图（Prefiltered Environment Map）结合BRDF LUT查找表

```glsl
// 简化版IBL
vec3 F = FresnelSchlick(max(dot(N, V), 0.0), F0);
vec3 kS = F;
vec3 kD = 1.0 - kS;
kD *= 1.0 - metallic;

vec3 irradiance = texture(uEnvMap, N).rgb;
vec3 diffuse = irradiance * albedo;

vec3 R = reflect(-V, N);
vec3 prefilteredColor = textureLod(uEnvMap, R, roughness * MAX_REFLECTION_LOD).rgb;
vec3 specular = prefilteredColor * F;

vec3 ambient = (kD * diffuse + specular) * ao;
```

### 4.3 动画状态机

骨骼动画系统除了基本的矩阵调色板播放外，还需要**动画状态机（Animation State Machine）**来管理角色在不同动画之间的过渡：

```cpp
struct AnimationState {
    std::string name;
    AnimationClip* clip;
    float playbackSpeed = 1.0f;
    bool loop = true;
};

struct AnimationTransition {
    std::string fromState;
    std::string toState;
    float transitionDuration;  // 混合时间
    std::function<bool()> condition;  // 触发条件
};

class AnimationStateMachine {
public:
    void AddState(const AnimationState& state);
    void AddTransition(const AnimationTransition& trans);
    void Update(float deltaTime);
    
    // 当前混合结果
    std::vector<Mat4> GetCurrentPose() const;
    
private:
    AnimationState* currentState = nullptr;
    AnimationState* targetState = nullptr;
    float blendTime = 0;
    float blendDuration = 0;
};
```

**动画混合**：在两个动画状态之间过渡时，对骨骼的局部变换（位置、旋转、缩放）进行插值。旋转使用四元数的球面插值（Slerp），确保平滑过渡。

### 4.4 Lua脚本绑定

为引擎添加脚本支持可以让游戏逻辑在不重新编译引擎的情况下迭代。使用sol2库绑定C++类和函数到Lua：

```cpp
class ScriptingEngine {
public:
    sol::state lua;
    
    void Initialize() {
        lua.open_libraries(sol::lib::base, sol::lib::math);
        BindMath();
        BindECS();
    }
    
    void LoadScript(const std::string& path) {
        lua.script_file(path);
    }
    
    void Update(float deltaTime) {
        sol::protected_function update = lua["OnUpdate"];
        if (update.valid()) {
            auto result = update(deltaTime);
            if (!result.valid()) {
                sol::error err = result;
                std::cerr << "Lua error: " << err.what() << std::endl;
            }
        }
    }
};
```

---

## 5. 性能优化专项

一个功能完整的引擎如果不能以稳定的帧率运行，就无法投入实际使用。本节涵盖五个核心优化方向。

### 5.1 Tracy Profiler集成

"你无法优化你无法测量的东西。" 性能优化的第一步是建立准确的测量体系。Tracy Profiler是一个现代化的帧分析工具，支持CPU和GPU时间线可视化。

```cpp
#ifdef ENABLE_PROFILER
    #include <tracy/Tracy.hpp>
    #define PROFILER_SCOPE(name) ZoneScopedN(name)
    #define PROFILER_FRAME() FrameMark
#else
    #define PROFILER_SCOPE(name)
    #define PROFILER_FRAME()
#endif
```

在渲染系统中插入Profiler标记点，追踪每个子系统的耗时。

### 5.2 Draw Call合批（Batching）

每次Draw Call都有固定开销（状态验证、命令缓冲区提交等）。**合批**是将使用相同材质和Shader的多个网格合并为一个Draw Call提交。实现方式：

1. **排序**：按Shader/材质/渲染层对渲染命令排序，最小化状态切换
2. **静态合批**：离线将使用相同材质的静态物体合并为单个Mesh
3. **动态合批**：运行时合并顶点数据（适合少量动态物体）

### 5.3 GPU实例化渲染（Instancing）

当场景中需要渲染大量相同网格的副本时（草地、树木、粒子），实例化渲染允许在一次Draw Call中绘制多个实例：

```cpp
// 设置实例属性（每个实例一个mat4）
for (int i = 0; i < 4; ++i) {
    glEnableVertexAttribArray(4 + i);
    glVertexAttribPointer(4 + i, 4, GL_FLOAT, GL_FALSE,
                          sizeof(InstanceData),
                          (void*)(sizeof(Vec4) * i));
    glVertexAttribDivisor(4 + i, 1);  // 每实例更新一次
}

glDrawElementsInstanced(GL_TRIANGLES, indexCount, GL_UNSIGNED_INT, 
                        nullptr, instanceCount);
```

### 5.4 LOD切换系统

**细节层次（Level of Detail）**根据物体与摄像机的距离自动切换不同精度的模型：

```cpp
struct LODLevel {
    MeshHandle mesh;
    float screenSpaceSize;  // 该LOD适用的最小屏幕空间尺寸
};

class LODSystem {
public:
    static int SelectLODLevel(const std::vector<LODLevel>& levels,
                               float distanceToCamera,
                               float screenHeight, float fov) {
        float projectedSize = (boundsRadius * screenHeight) /
                              (distanceToCamera * tan(fov * 0.5f) * 2.0f);
        for (int i = 0; i < levels.size(); ++i) {
            if (projectedSize >= levels[i].screenSpaceSize) return i;
        }
        return levels.size() - 1;
    }
};
```

### 5.5 多线程渲染改造

现代引擎普遍采用**多线程渲染架构**：主线程负责游戏逻辑更新和渲染命令生成，渲染线程负责向GPU提交命令。

```cpp
class RenderThread {
public:
    // 双缓冲命令队列：主线程写入back buffer，渲染线程读取front buffer
    void Submit() {
        std::lock_guard<std::mutex> lock(swapMutex);
        std::swap(writeBuffer, readBuffer);
        commandBuffers[writeBuffer].clear();
        hasNewCommands = true;
        cv.notify_one();
    }
    
    template<typename Cmd>
    void Enqueue(Cmd&& cmd) {
        commandBuffers[writeBuffer].push_back(
            std::make_unique<std::decay_t<Cmd>>(std::forward<Cmd>(cmd)));
    }
};
```

### 5.6 优化技术汇总

| 优化技术 | 适用场景 | 主要收益 | 实现复杂度 | 典型提升 |
|----------|----------|----------|------------|----------|
| Draw Call合批 | 多个相同材质的静态物体 | 减少CPU开销 | 中 | 2-5x |
| GPU Instancing | 大量相同网格（草/树/粒子） | Draw Call从N降为1 | 低 | 10-100x |
| LOD系统 | 大规模场景（开放世界） | 减少GPU几何负载 | 中 | 2-4x |
| 多线程渲染 | CPU端逻辑复杂的场景 | GPU不被CPU阻塞 | 高 | 1.2-2x |
| Early-Z/Depth Prepass | 复杂遮挡关系的场景 | 减少过度绘制 | 低 | 1.5-3x |
| 纹理图集（Atlas） | 大量小纹理 | 减少纹理切换 | 中 | 1.2-1.5x |

这些优化技术通常组合使用。例如，在开放世界场景中，先用Frustum Culling剔除视锥外物体，再用LOD为远处物体选择低精度网格，最后对同类植被使用GPU Instancing批量绘制——组合优化可以将原始渲染负载降低一个数量级。

---

## 6. 扩展阅读

### 开源引擎参考

1. **Hazel Engine** (TheCherno)
   - GitHub: https://github.com/TheCherno/Hazel
   - 特点：现代C++、Vulkan + OpenGL双后端、完整编辑器
   - 学习重点：渲染抽象层设计、事件系统、场景序列化

2. **Wicked Engine**
   - GitHub: https://github.com/turanszkij/WickedEngine
   - 特点：DX12/Vulkan、实时光线追踪、ECS架构
   - 学习重点：多线程渲染、GPU-driven rendering

3. **Banshee Engine** (现更名为 bs::framework)
   - GitHub: https://github.com/GameFoundry/bsf
   - 特点：模块化设计、脚本绑定、材质系统
   - 学习重点：插件架构、跨平台抽象

4. **Filament** (Google)
   - GitHub: https://github.com/google/filament
   - 特点：PBR-first、移动端优化、基于物理的光照
   - 学习重点：PBR实现细节、材质系统、IBL

### 书籍推荐

- 《Game Engine Architecture》by Jason Gregory — 游戏引擎架构圣经
- 《Real-Time Rendering, 4th Edition》— 实时渲染技术大全
- 《Physically Based Rendering, 3rd Edition》— 离线渲染，但原理相通
- 《Data-Oriented Design》by Richard Fabian — ECS和DOD设计

### 在线资源

- **OpenGL Tutorial**: https://learnopengl.com/ — 本引擎大量参考了此教程
- **Vulkan Guide**: https://vkguide.dev/ — 如果要迁移到Vulkan
- **GDC Vault**: 搜索 "Entity Component System"、"Multithreaded Game Engines"

---

## 常见陷阱

### 1. 组件指针失效

ECS中使用`SparseSet`存储组件，当添加/删除组件时，内部的`std::vector`可能重新分配内存，导致之前获取的指针失效。

**错误代码**：
```cpp
auto& transform = world->GetComponent<Transform>(entity);
world->AddComponent<Collider>(entity);  // 可能触发其他pool的realloc
// transform 可能已失效！
```

**解决方案**：
- 不要在遍历时修改组件池
- 使用延迟删除/添加机制
- 或者存储Entity ID而非组件指针

### 2. 固定时间步的插值

如果在渲染时不使用插值，物体会出现抖动（stuttering）。

**错误代码**：
```cpp
// 渲染时直接使用物理位置
RenderAt(transform.position);  // 抖动！
```

**正确做法**：
```cpp
// 保存上一帧位置
Vec3 prevPos = transform.position;
// 物理更新后
Vec3 interpolated = prevPos + (transform.position - prevPos) * interpolation;
RenderAt(interpolated);
```

### 3. OpenGL状态泄漏

忘记恢复OpenGL状态会导致难以调试的渲染错误。

**错误代码**：
```cpp
void SomeEffect::Render() {
    glDisable(GL_DEPTH_TEST);  // 修改了全局状态
    // ... 绘制
}  // 没有恢复深度测试！
```

**解决方案**：
- 使用RAII包装器管理状态
- 或每帧开始时重置所有状态
- 或使用状态缓存系统（记录当前状态，只在需要时切换）

### 4. 资源循环引用

使用`shared_ptr`管理资源时，循环引用会导致内存泄漏。

**错误代码**：
```cpp
struct Material {
    shared_ptr<Texture> texture;
};
struct Texture {
    shared_ptr<Material> material;  // 循环引用！
};
```

**解决方案**：
- 使用`weak_ptr`打破循环
- 或者让ResourceManager拥有所有权，外部只持有句柄/ID

### 5. 多线程数据竞争

如果在多个线程中同时访问ECS组件，会发生数据竞争。

**错误代码**：
```cpp
// 线程A
world->GetComponent<Transform>(entity).position += velocity;

// 线程B（同时）
world->GetComponent<Transform>(entity).position = spawnPoint;
```

**解决方案**：
- 使用任务系统，每个System在独立任务中运行
- 明确读写依赖，使用barrier同步
- 或使用无锁数据结构（如原子操作的位置更新）

### 6. 阴影贴图精度问题

方向光的正交投影阴影贴图容易出现锯齿和精度不足。

**解决方案**：
- 使用CSM（Cascaded Shadow Maps）：将视锥分割为多个级联，每级使用独立的阴影贴图
- 使用PCF（Percentage Closer Filtering）柔化阴影边缘
- 调整阴影贴图的分辨率和投影范围

### 7. 音频线程阻塞

在主线程直接加载音频文件会导致卡顿。

**解决方案**：
- 使用miniaudio的异步加载（`MA_SOUND_FLAG_ASYNC`）
- 或者创建独立的加载线程池
- 大文件使用流式播放而非完全解码到内存

---

## 附录：编译和运行指南

### 环境要求

- **CMake** >= 3.16
- **C++17** 兼容编译器
  - Windows: Visual Studio 2019+ 或 MinGW-w64
  - Linux: GCC 9+ 或 Clang 10+
  - macOS: Xcode 11+
- **Python 3**（用于资源处理脚本，可选）

### 第三方库获取

```bash
# 在项目根目录执行
mkdir -p third_party
cd third_party

# glad (使用在线生成器 https://glad.dav1d.de/)
# 选择 OpenGL 3.3 Core，生成后解压到 glad/

# glfw
git clone https://github.com/glfw/glfw.git
cd glfw && git checkout 3.3.8 && cd ..

# imgui
git clone https://github.com/ocornut/imgui.git
cd imgui && git checkout docking && cd ..

# spdlog
git clone https://github.com/gabime/spdlog.git
cd spdlog && git checkout v1.12.0 && cd ..

# stb (单头文件库)
mkdir stb && cd stb
curl -O https://raw.githubusercontent.com/nothings/stb/master/stb_image.h
cd ..

# miniaudio (单头文件库)
mkdir miniaudio && cd miniaudio
curl -O https://raw.githubusercontent.com/mackron/miniaudio/master/miniaudio.h
cd ..
```

### 构建步骤

```bash
# Windows (Visual Studio)
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release

# Windows (MinGW)
mkdir build && cd build
cmake .. -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(nproc)

# Linux
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(nproc)

# macOS
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(sysctl -n hw.ncpu)
```

### 运行

```bash
# Windows
cd build\game\Release
.\Game.exe

# Linux/macOS
cd build/game
./Game
```

### 常见问题

**Q: 编译报错 "glad/glad.h not found"**
A: 确保 glad 的头文件在 `third_party/glad/include/` 下，且 CMake 正确配置了 include 路径。

**Q: 链接错误 "undefined reference to glfw..."**
A: 确保 GLFW 子模块已正确初始化：`git submodule update --init --recursive`

**Q: 运行时崩溃 "Failed to initialize GLAD"**
A: 确保创建了 OpenGL 上下文（`glfwMakeContextCurrent`）后再调用 `gladLoadGLLoader`。

**Q: 阴影贴图全黑**
A: 检查阴影贴图的边框颜色设置，以及光源视锥是否覆盖了场景。使用ImGui调试面板查看光源视角的渲染结果。

---

## 扩展方向

在MiniEngine的基础上，你可以朝以下方向扩展：

### 1. 渲染系统升级
- **Vulkan/DX12后端**：使用现代图形API，支持多线程命令缓冲录制
- **延迟渲染（Deferred Shading）**：支持大量动态光源
- **实时光线追踪**：集成DXR或Vulkan RT
- **GPU粒子系统**：使用Compute Shader实现百万级粒子

### 2. 物理系统增强
- **集成Bullet/PhysX**：替换自研物理，获得完整刚体、软体、布料模拟
- **角色控制器**：专门的 kinematic character controller
- **布娃娃系统**：ragdoll，基于物理的死亡动画

### 3. 动画系统完善
- **动画混合树**：blend tree、1D/2D blending
- **IK（反向动力学）**：Two Bone IK、FABRIK
- **动画压缩**：关键帧压缩、曲线拟合

### 4. 网络系统
- **客户端-服务器架构**：状态同步、快照插值
- **预测回滚**：客户端预测、服务器 reconciliation
- **ECS网络序列化**：组件级别的增量同步

### 5. 编辑器完善
- **场景编辑器**：gizmo操作、多视口、场景树面板
- **材质编辑器**：节点图编辑材质
- **地形系统**：高度图导入、刷地形、植被散布

### 6. 平台扩展
- **Android/iOS**：OpenGL ES / Metal 后端
- **WebAssembly**：Emscripten编译，WebGL渲染
- **主机平台**：PlayStation/Xbox SDK集成
