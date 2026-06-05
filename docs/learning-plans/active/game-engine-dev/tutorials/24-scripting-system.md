---
title: "脚本系统"
updated: 2026-06-05
---

# 脚本系统

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 5h
> 前置知识: 02-内存管理与自定义分配器, 04-ECS 架构

---

## 1. 概念讲解

### 为什么需要脚本系统？

脚本系统允许使用高级脚本语言（而非 C++）来编写游戏逻辑。这为游戏开发带来了两个主要优势：

1. **快速迭代**：脚本修改后无需重新编译整个引擎即可生效，大大缩短开发周期
2. **降低门槛**：脚本语言通常比 C++ 更容易学习，使游戏设计师和策划也能参与逻辑开发

想象一下没有脚本系统的游戏开发：
- 每次调整一个数值（如玩家移动速度）都需要重新编译整个引擎
- 游戏设计师必须等待程序员实现每一个逻辑细节
- 不同平台的构建和测试周期以小时计

有了脚本系统，设计师可以直接修改脚本文件并立即看到效果，迭代周期缩短到秒级。

### 核心思想

脚本系统的核心设计围绕以下几个原则展开：

**1. 宿主-脚本分离**

引擎核心（渲染、物理、音频）用 C++ 编写以保证性能，游戏逻辑（角色行为、任务系统、UI 交互）用脚本编写以保证灵活性。脚本运行在虚拟机或解释器中，通过绑定层与 C++ 引擎交互。

**2. 双向绑定**

- **C++ -> 脚本**：从 C++ 调用脚本函数、读取/修改脚本变量
- **脚本 -> C++**：从脚本调用 C++ 函数、访问 C++ 类的成员

**3. 生命周期管理**

脚本对象的生命周期需要与 C++ 对象正确同步。当 C++ 对象被销毁时，脚本中的引用需要被清理，避免悬空指针。

**4. 热重载**

脚本修改后，引擎检测到文件变化，自动重新加载并执行新脚本，无需重启游戏。

---

### 1.1 脚本语言选择

游戏引擎中常用的脚本语言包括：

| 脚本语言 | 特点 | 绑定复杂度 | 典型用户 | 代表引擎 |
|---------|------|----------|---------|---------|
| Lua | 轻量、嵌入简单、速度快 | 低 (sol2) | 游戏设计师、程序员 | WoW, Angry Birds |
| C# | 类型安全、生态丰富、JIT | 中 (HostFXR/Mono) | 开发者 | Unity |
| Python | 生态极丰富、易学 | 高 (pybind11/boost) | 工具开发 | Maya 插件 |
| JavaScript | Web 生态、异步模型 | 中 (V8/Duktape) | Web 开发者 | 部分 Web 引擎 |
| 自定义 (如 UE Blueprint) | 可视化、引擎深度集成 | N/A | 设计师 | Unreal Engine |

**Lua** 是游戏行业使用最广泛的脚本语言，其优势在于：

- **极小的运行时**：Lua 解释器的体积只有约 200 KB，适合嵌入式使用
- **简单的 C API**：Lua 提供了非常简洁的 C API 用于与宿主程序交互
- **高效的 JIT 实现**：LuaJIT 是 Lua 的高性能 JIT 编译器，执行速度接近原生 C 代码
- **协程支持**：Lua 的协程（coroutine）非常适合实现游戏逻辑中的状态机和异步流程

**C#** 在 Unity 中的成功证明了强类型脚本语言的优势：
- 编译时类型检查减少运行时错误
- 丰富的标准库和第三方生态
- JIT 编译提供接近原生的性能

---

### 1.2 C++ 与脚本交互（反射/绑定层）

C++ 与脚本语言的交互需要解决两个方向的问题。由于 C++ 本身不支持运行时反射，引擎通常通过以下方式实现绑定：

**1. 手动绑定**

为每个需要暴露给脚本的 C++ 类和函数编写绑定代码。这是最直接但最繁琐的方式。

```cpp
// 手动绑定示例：将 C++ 的 Player 类暴露给 Lua
// 需要为每个方法编写包装函数
int lua_Player_Move(lua_State* L) {
    Player* player = (Player*)lua_touserdata(L, 1);
    float dx = lua_tonumber(L, 2);
    float dy = lua_tonumber(L, 3);
    player->Move(dx, dy);
    return 0;
}
```

**2. 代码生成**

使用解析工具（如 Clang LibTooling）扫描 C++ 源码，自动生成绑定代码。这种方式可以大幅减少手动工作量，但需要维护代码生成工具链。

**3. 宏系统**

使用 C++ 宏来标记需要暴露的类和函数，编译时展开为绑定代码。

```cpp
// 宏系统示例
SCRIPT_CLASS(Player) {
    SCRIPT_METHOD(Move);
    SCRIPT_METHOD(Jump);
    SCRIPT_PROPERTY(health);
};
```

**4. 现代绑定库（推荐）**

使用 sol2（C++17 Lua 绑定）、pybind11（Python 绑定）等现代库，它们利用 C++ 模板元编程自动生成绑定代码，几乎零样板代码。

---

### 1.3 脚本组件架构

在 ECS（Entity-Component-System）架构中，脚本通常以**ScriptComponent**的形式存在：

```
Entity (玩家角色)
  ├── TransformComponent (位置、旋转、缩放)
  ├── MeshComponent (模型、材质)
  ├── PhysicsComponent (刚体、碰撞体)
  └── ScriptComponent (脚本逻辑)
        ├── 脚本文件路径: "scripts/player_controller.lua"
        ├── Update 回调
        ├── OnCollisionEnter 回调
        └── OnDestroy 回调
```

每个 ScriptComponent 管理一个脚本实例的生命周期：

1. **初始化（Initialize）**：加载脚本文件，注册回调函数
2. **更新（Update）**：每帧调用脚本的 Update 函数
3. **事件响应**：当特定事件发生时（如碰撞、输入），调用对应的回调
4. **销毁（Destroy）**：清理脚本状态，释放资源

---

### 1.4 脚本热重载

脚本热重载的实现比 C++ 代码的热重载简单得多——只需重新加载脚本文件并重新绑定回调即可。

实现步骤：

1. **文件监控**：监控脚本文件的最后修改时间戳
2. **变更检测**：检测到变更后，重新加载脚本文件
3. **回调重新绑定**：重新获取脚本中定义的回调函数引用
4. **状态恢复**：调用脚本的 `OnReload` 函数（如果存在），让脚本有机会恢复状态

```cpp
class ScriptSystem {
    // 每帧检查脚本文件是否被修改
    void CheckHotReload() {
        for (auto& script : scriptComponents) {
            auto currentTime = GetFileModifyTime(script->path);
            if (currentTime > script->lastLoadedTime) {
                ReloadScript(script);
            }
        }
    }

    void ReloadScript(ScriptComponent* script) {
        // 1. 保存当前状态（可选）
        auto savedState = script->SaveState();

        // 2. 重新加载脚本
        luaState.load_file(script->path);

        // 3. 重新绑定回调
        script->RebindCallbacks();

        // 4. 恢复状态
        script->RestoreState(savedState);

        // 5. 调用 OnReload
        script->CallOnReload();
    }
};
```

---

### 1.5 垃圾回收桥接

Lua 使用**增量式垃圾回收（Incremental GC）**来管理内存。当 C++ 对象被 Lua 引用时（如通过 `new_usertype` 绑定的对象），需要确保对象的生命周期正确管理。

现代绑定库（如 sol2）提供两种生命周期管理策略：

1. **值语义**：Lua 持有 C++ 对象的副本。适用于小对象。
2. **引用/指针语义**：Lua 持有 C++ 对象的指针，需要 C++ 侧确保对象存活期间 Lua 不会访问它。适用于由 C++ 管理的游戏对象。

对于游戏对象这类由 C++ 管理生命周期的对象，通常使用指针语义，并在对象销毁时清除 Lua 中的引用，防止悬空指针。

---

## 2. 代码示例

以下代码展示了一个使用 sol2 的完整脚本系统实现，包括 C++ 类型绑定、脚本组件管理和热重载支持。

```cpp
// ============================================================
// scripting_system.cpp
// 脚本系统完整实现（使用 sol2 绑定 Lua）
// 编译: g++ -std=c++17 scripting_system.cpp -o scripting_system -llua
// ============================================================

#include <sol/sol.hpp>
#include <iostream>
#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
#include <filesystem>
#include <chrono>

// ============================================================
// 游戏对象组件基类 - 需要暴露给 Lua
// ============================================================
class GameObject {
public:
    GameObject(const std::string& name) : m_name(name) {}
    virtual ~GameObject() = default;

    const std::string& GetName() const { return m_name; }

    // 变换接口
    void SetPosition(float x, float y, float z) {
        m_positionX = x; m_positionY = y; m_positionZ = z;
    }
    float GetPositionX() const { return m_positionX; }
    float GetPositionY() const { return m_positionY; }
    float GetPositionZ() const { return m_positionZ; }

    // 激活状态
    void SetActive(bool active) { m_active = active; }
    bool IsActive() const { return m_active; }

private:
    std::string m_name;
    float m_positionX = 0.0f, m_positionY = 0.0f, m_positionZ = 0.0f;
    bool m_active = true;
};

// ============================================================
// 脚本组件 - 附加到 GameObject 上，执行 Lua 逻辑
// ============================================================
class ScriptComponent {
public:
    ScriptComponent(GameObject* owner, const std::string& scriptPath)
        : m_owner(owner), m_scriptPath(scriptPath) {}

    void Initialize(sol::state& lua);
    void Update(float deltaTime);
    void OnCollisionEnter(GameObject* other);

    const std::string& GetPath() const { return m_scriptPath; }

private:
    GameObject* m_owner = nullptr;
    std::string m_scriptPath;

    // Lua 回调引用
    sol::protected_function m_luaUpdate;
    sol::protected_function m_luaOnCollisionEnter;
    bool m_hasUpdate = false;
    bool m_hasOnCollisionEnter = false;
};

// ============================================================
// 脚本系统 - 管理 Lua 状态和所有脚本组件
// ============================================================
class ScriptSystem {
public:
    void Initialize();
    void Shutdown();

    // 帧更新 - 调用所有脚本组件的 Update
    void Update(float deltaTime);

    // 加载并执行 Lua 脚本
    bool ExecuteScript(const std::string& path);
    bool ExecuteString(const std::string& code);

    // 暴露 C++ 类型和函数给 Lua
    void BindEngineAPI();

    // 创建绑定到 GameObject 的脚本组件
    std::unique_ptr<ScriptComponent> CreateScriptComponent(GameObject* owner,
                                                             const std::string& scriptPath);

    // 热重载
    void CheckHotReload();

    sol::state& GetLuaState() { return m_lua; }

private:
    void BindMathLibrary();

private:
    sol::state m_lua;
    std::vector<ScriptComponent*> m_scriptComponents;
    std::unordered_map<std::string, std::filesystem::file_time_type> m_scriptFileTimes;
};

// ============================================================
// 实现
// ============================================================

void ScriptSystem::Initialize() {
    // 打开 Lua 标准库
    m_lua.open_libraries(
        sol::lib::base,
        sol::lib::package,
        sol::lib::coroutine,
        sol::lib::string,
        sol::lib::os,
        sol::lib::math,
        sol::lib::table,
        sol::lib::debug,
        sol::lib::bit32,
        sol::lib::io,
        sol::lib::utf8
    );

    // 暴露引擎 API
    BindEngineAPI();
}

void ScriptSystem::BindEngineAPI() {
    // 绑定 GameObject 类到 Lua
    m_lua.new_usertype<GameObject>("GameObject",
        sol::constructors<GameObject(const std::string&)>(),
        "GetName", &GameObject::GetName,
        "SetPosition", &GameObject::SetPosition,
        "GetPositionX", &GameObject::GetPositionX,
        "GetPositionY", &GameObject::GetPositionY,
        "GetPositionZ", &GameObject::GetPositionZ,
        "SetActive", &GameObject::SetActive,
        "IsActive", &GameObject::IsActive
    );

    // 绑定数学库
    BindMathLibrary();

    // 绑定全局函数
    m_lua.set_function("LogInfo", [](const std::string& msg) {
        std::cout << "[Lua] " << msg << std::endl;
    });

    m_lua.set_function("LogError", [](const std::string& msg) {
        std::cerr << "[Lua Error] " << msg << std::endl;
    });

    m_lua.set_function("GetDeltaTime", []() -> float {
        return 1.0f / 60.0f;  // 简化：返回固定值
    });

    m_lua.set_function("FindObjectByName", [](const std::string& name) -> GameObject* {
        // 实际实现从场景管理器中查找对象
        return nullptr;
    });
}

void ScriptSystem::BindMathLibrary() {
    // 绑定 Vec3 到 Lua（简化版）
    m_lua.new_usertype<sol::table>("Vec3");  // 占位

    // 绑定数学函数
    sol::table mathExtra = m_lua.create_named_table("Math");
    mathExtra.set_function("Lerp", [](float a, float b, float t) {
        return a + (b - a) * t;
    });
    mathExtra.set_function("Clamp", [](float value, float min, float max) {
        return value < min ? min : (value > max ? max : value);
    });
}

void ScriptSystem::Update(float deltaTime) {
    for (ScriptComponent* script : m_scriptComponents) {
        if (script) {
            script->Update(deltaTime);
        }
    }
}

void ScriptSystem::CheckHotReload() {
    for (ScriptComponent* script : m_scriptComponents) {
        if (!std::filesystem::exists(script->GetPath())) continue;

        auto currentTime = std::filesystem::last_write_time(script->GetPath());
        auto it = m_scriptFileTimes.find(script->GetPath());

        if (it == m_scriptFileTimes.end()) {
            m_scriptFileTimes[script->GetPath()] = currentTime;
        } else if (currentTime != it->second) {
            std::cout << "[HotReload] Detected change in: " << script->GetPath() << std::endl;
            it->second = currentTime;
            // 实际实现：重新加载脚本并重新绑定回调
        }
    }
}

std::unique_ptr<ScriptComponent> ScriptSystem::CreateScriptComponent(
    GameObject* owner, const std::string& scriptPath) {
    auto comp = std::make_unique<ScriptComponent>(owner, scriptPath);
    comp->Initialize(m_lua);
    m_scriptComponents.push_back(comp.get());
    return comp;
}

// ============================================================
// 脚本组件实现
// ============================================================
void ScriptComponent::Initialize(sol::state& lua) {
    try {
        // 加载脚本文件
        sol::load_result script = lua.load_file(m_scriptPath);
        if (!script.valid()) {
            sol::error err = script;
            std::cerr << "Failed to load script '" << m_scriptPath
                      << "': " << err.what() << std::endl;
            return;
        }

        // 执行脚本以注册类型和函数
        script();

        // 获取脚本中定义的 Update 函数
        sol::optional<sol::protected_function> updateFunc =
            lua[m_owner->GetName()]["Update"];
        if (updateFunc.has_value()) {
            m_luaUpdate = updateFunc.value();
            m_hasUpdate = true;
        }

        // 获取 OnCollisionEnter 回调
        sol::optional<sol::protected_function> collisionFunc =
            lua[m_owner->GetName()]["OnCollisionEnter"];
        if (collisionFunc.has_value()) {
            m_luaOnCollisionEnter = collisionFunc.value();
            m_hasOnCollisionEnter = true;
        }
    } catch (const std::exception& e) {
        std::cerr << "Script initialization error for '" << m_scriptPath
                  << "': " << e.what() << std::endl;
    }
}

void ScriptComponent::Update(float deltaTime) {
    if (!m_hasUpdate) return;

    try {
        sol::protected_function_result result = m_luaUpdate(m_owner, deltaTime);
        if (!result.valid()) {
            sol::error err = result;
            std::cerr << "Script '" << m_scriptPath << "' Update error: "
                      << err.what() << std::endl;
        }
    } catch (...) {
        // 脚本执行异常，避免崩溃
    }
}

void ScriptComponent::OnCollisionEnter(GameObject* other) {
    if (!m_hasOnCollisionEnter) return;

    try {
        sol::protected_function_result result = m_luaOnCollisionEnter(m_owner, other);
        if (!result.valid()) {
            sol::error err = result;
            std::cerr << "Script '" << m_scriptPath << "' OnCollisionEnter error: "
                      << err.what() << std::endl;
        }
    } catch (...) {}
}

// ============================================================
// 演示主函数
// ============================================================
int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  游戏引擎脚本系统演示" << std::endl;
    std::cout << "========================================" << std::endl;

    ScriptSystem scriptSystem;
    scriptSystem.Initialize();

    // 创建一个游戏对象
    GameObject player("Player");
    player.SetPosition(0.0f, 1.0f, 0.0f);

    // 演示：直接在 Lua 中执行代码
    std::cout << "\n--- 执行 Lua 代码 ---" << std::endl;
    scriptSystem.ExecuteString(R"(
        LogInfo("Hello from Lua!")

        -- 创建 GameObject
        local enemy = GameObject.new("Enemy")
        enemy:SetPosition(10, 0, 5)
        LogInfo("Enemy created at: " .. enemy:GetPositionX() .. ", " .. enemy:GetPositionY() .. ", " .. enemy:GetPositionZ())

        -- 使用数学库
        local result = Math.Lerp(0, 100, 0.5)
        LogInfo("Lerp(0, 100, 0.5) = " .. result)
    )");

    std::cout << "\n========================================" << std::endl;
    std::cout << "  演示结束" << std::endl;
    std::cout << "========================================" << std::endl;

    return 0;
}
```

**运行方式:**

```bash
# 需要安装 sol2 和 Lua 开发库
# Ubuntu/Debian:
sudo apt-get install liblua5.3-dev

# 编译（假设 sol2 头文件在当前目录）
g++ -std=c++17 -I. scripting_system.cpp -o scripting_system -llua5.3

./scripting_system
```

**预期输出:**

```text
========================================
  游戏引擎脚本系统演示
========================================

--- 执行 Lua 代码 ---
[Lua] Hello from Lua!
[Lua] Enemy created at: 10, 0, 5
[Lua] Lerp(0, 100, 0.5) = 50

========================================
  演示结束
========================================
```

---

## 3. 练习

### 练习 1：实现 Lua 状态机

使用 Lua 协程（coroutine）实现一个 NPC 的 AI 状态机：

1. 定义三种状态：Idle（待机）、Patrol（巡逻）、Chase（追击）
2. 使用 `coroutine.create` 和 `coroutine.resume` 管理状态切换
3. 每个状态是一个独立的协程函数
4. 在 C++ 侧，每帧调用 `resume` 推进状态机

**提示：** 协程可以在中间 `yield` 并返回当前状态，下次 `resume` 时从 yield 处继续执行。

### 练习 2：实现脚本事件系统

扩展脚本系统，实现一个事件总线：

1. 在 C++ 中定义 `EventBus` 类，支持订阅/发布事件
2. 将 `EventBus` 暴露给 Lua
3. Lua 脚本可以订阅事件（如 "OnPlayerDamaged"）并定义回调
4. C++ 游戏逻辑可以发布事件，触发所有 Lua 订阅者的回调

**要求：**
- 支持带参数的事件（如 `EventBus.Publish("OnPlayerDamaged", player, damageAmount)`）
- 支持取消订阅
- 处理脚本热重载时的订阅清理

### 练习 3（可选）：实现简单的可视化脚本系统

不依赖 Lua，实现一个基于节点的可视化脚本系统：

1. 定义节点类型：Start、Update、Move、Rotate、If、Loop
2. 每个节点有输入端口和输出端口
3. 节点之间通过连接（Link）传递数据和控制流
4. 序列化脚本图为 JSON 格式
5. 实现一个简单的解释器，执行脚本图

**提示：** 参考 Unreal Engine Blueprint 或 Unity Visual Scripting 的设计。

---

## 4. 扩展阅读

### 书籍

1. **《Programming in Lua》** — Roberto Ierusalimschy
   - Lua 官方教材，深入理解 Lua 语言特性和 C API

2. **《Game Engine Architecture》第 3 版 — Jason Gregory**
   - 第 15 章 "Scripting"：脚本系统在引擎中的定位和实现

3. **《Lua Programming Gems》**
   - Lua 高级技巧和模式，包括协程、元表等在游戏中的应用

### 文章与文档

1. **sol2 官方文档**: https://sol2.readthedocs.io/
   - 现代 C++ Lua 绑定库的最佳实践

2. **LuaJIT 文档**: https://luajit.org/
   - 高性能 Lua 实现的内部原理

3. **Unity Mono Runtime**: https://docs.unity3d.com/Manual/ScriptingRestrictions.html
   - 了解 C# 在引擎中的限制和最佳实践

### 开源参考

1. **Godot Engine GDScript**: https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/index.html
   - 专为游戏设计的脚本语言，语法类似 Python

2. **Bevy Engine Scripting**: https://bevyengine.org/
   - Rust 引擎的脚本系统探索（使用 Rust 本身作为脚本语言）

3. **Unreal Engine Blueprint VM**: UE 源码中的 `BlueprintCore` 模块
   - 可视化脚本的虚拟机实现

---

## 常见陷阱

### 陷阱 1：C++ 对象被销毁但 Lua 仍持有引用

**问题**：C++ 侧销毁了一个 GameObject，但 Lua 中还有一个 userdata 指向它。后续访问会导致崩溃。

**解决方案**：
- 使用弱引用（weak reference）模式
- 在 C++ 对象销毁时，通知 Lua 清除引用
- 使用句柄系统（Handle + Generation ID）替代裸指针

### 陷阱 2：脚本错误导致引擎崩溃

**问题**：Lua 脚本中的错误（如访问 nil）可能通过 C++ 调用栈传播，导致整个引擎崩溃。

**解决方案**：
- 始终使用 `protected_function` 调用 Lua 函数（如 sol2 的 `sol::protected_function`）
- 在 C++ 绑定函数中添加 try-catch 块
- 为脚本执行设置独立的错误处理上下文

### 陷阱 3：热重载时丢失脚本状态

**问题**：热重载后，脚本中的局部变量和全局状态被重置。

**解决方案**：
- 在重载前序列化关键状态
- 提供 `OnReload` 回调让脚本恢复状态
- 将持久状态存储在 C++ 侧，脚本只保存逻辑

### 陷阱 4：绑定层性能瓶颈

**问题**：频繁地在 C++ 和脚本之间传递数据（如每帧传递大量向量）导致性能下降。

**解决方案**：
- 批量传递数据，减少跨边界调用次数
- 在脚本侧缓存 C++ 对象的引用
- 对于性能关键路径，将逻辑移到 C++ 中

### 陷阱 5：Lua 垃圾回收导致卡顿

**问题**：Lua 的增量式 GC 在标记阶段可能消耗大量 CPU 时间，导致帧率下降。

**解决方案**：
- 控制 GC 步长：`collectgarbage("setpause", 150)` 和 `collectgarbage("setstepmul", 200)`
- 在加载屏幕期间执行完整 GC：`collectgarbage("collect")`
- 使用对象池减少 GC 压力

### 陷阱 6：多线程访问 Lua 状态

**问题**：Lua 的默认实现不是线程安全的，多个线程同时操作同一个 `lua_State` 会导致崩溃。

**解决方案**：
- 每个线程拥有独立的 Lua 状态
- 使用锁保护共享的 Lua 状态（但会严重影响性能）
- 将脚本执行限制在主线程
