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

## 3.5 参考答案

> [!tip]- 练习 1：Lua 状态机
> #### C++ 侧 — 状态机组件与逐帧驱动
> ```cpp
> // NpcStateMachine.h
> #pragma once
> #include <sol/sol.hpp>
> #include <string>
>
> class NpcStateMachine {
> public:
>     explicit NpcStateMachine(sol::state& lua, const std::string& scriptPath);
>     ~NpcStateMachine();
>
>     std::string Update(float deltaTime);
>     // 返回当前状态名，供外部调试/显示
>
> private:
>     sol::state& m_lua;
>     sol::coroutine m_coroutine;
>     std::string m_currentState;
>     bool m_coroutineDead = false;
> };
> ```
>
> ```cpp
> // NpcStateMachine.cpp
> #include "NpcStateMachine.h"
> #include <iostream>
>
> NpcStateMachine::NpcStateMachine(sol::state& lua, const std::string& scriptPath)
>     : m_lua(lua)
> {
>     // 执行脚本，脚本返回一个 coroutine 工厂函数
>     sol::protected_function_result loadResult = lua.safe_script_file(
>         scriptPath, sol::script_pass_on_error);
>     if (!loadResult.valid()) {
>         sol::error err = loadResult;
>         std::cerr << "Failed to load state machine script: " << err.what() << '\n';
>         m_coroutineDead = true;
>         return;
>     }
>
>     // 脚本定义了 CreateNpcAI() 返回一个 coroutine
>     sol::protected_function factory = lua["CreateNpcAI"];
>     if (!factory.valid()) {
>         std::cerr << "CreateNpcAI not found in script\n";
>         m_coroutineDead = true;
>         return;
>     }
>
>     sol::protected_function_result callResult = factory();
>     if (!callResult.valid()) {
>         sol::error err = callResult;
>         std::cerr << "CreateNpcAI error: " << err.what() << '\n';
>         m_coroutineDead = true;
>         return;
>     }
>
>     m_coroutine = callResult.get<sol::coroutine>();
>     m_currentState = "Idle";
> }
>
> NpcStateMachine::~NpcStateMachine() {
>     // coroutine 随 sol::state 生命周期自动清理
> }
>
> std::string NpcStateMachine::Update(float deltaTime) {
>     if (m_coroutineDead) return m_currentState;
>
>     sol::protected_function_result result = m_coroutine(deltaTime);
>     if (!result.valid()) {
>         sol::error err = result;
>         // coroutine 正常结束不是错误；sol2 中死 coroutine 再次调用会抛错
>         std::string errMsg = err.what();
>         if (errMsg.find("dead coroutine") != std::string::npos) {
>             m_coroutineDead = true;
>             return m_currentState;
>         }
>         std::cerr << "State machine error: " << errMsg << '\n';
>         m_coroutineDead = true;
>         return m_currentState;
>     }
>
>     // yield 返回 {stateName, ...其他数据}
>     if (result.return_count() >= 1) {
>         m_currentState = result.get<std::string>(0);
>     }
>     return m_currentState;
> }
> ```
>
> #### Lua 侧 — 协程状态机脚本
> ```lua
> -- npc_ai.lua
> -- 三个状态协程，通过外层协程调度
>
> local function IdleState(deltaTime)
>     while true do
>         -- 模拟待机行为
>         deltaTime = coroutine.yield("Idle")
>         -- 简化：随机切换到 Patrol
>         if math.random() < 0.01 then
>             return "Patrol"
>         end
>     end
> end
>
> local function PatrolState(deltaTime)
>     local elapsed = 0
>     while true do
>         elapsed = elapsed + deltaTime
>         deltaTime = coroutine.yield("Patrol")
>         -- 巡逻 5 秒后切换
>         if elapsed > 5.0 then
>             return "Idle"
>         end
>         -- 检测到玩家则追击
>         if DetectPlayer() then
>             return "Chase"
>         end
>     end
> end
>
> local function ChaseState(deltaTime)
>     while true do
>         deltaTime = coroutine.yield("Chase")
>         -- 丢失目标后回到巡逻
>         if not DetectPlayer() then
>             return "Patrol"
>         end
>     end
> end
>
> -- 辅助：检测玩家（由 C++ 注入实现）
> function DetectPlayer()
>     -- 实际实现通过 C++ 绑定提供
>     return false
> end
>
> -- 调度器：按状态名查找协程函数并 resume 它
> local stateFunctions = {
>     Idle   = IdleState,
>     Patrol = PatrolState,
>     Chase  = ChaseState,
> }
>
> function CreateNpcAI()
>     return coroutine.create(function()
>         local current = "Idle"
>         while true do
>             local stateFn = stateFunctions[current]
>             if not stateFn then
>                 LogError("Unknown state: " .. tostring(current))
>                 return
>             end
>             -- 创建子协程执行具体状态
>             local stateCo = coroutine.create(stateFn)
>             while true do
>                 local ok, nextState = coroutine.resume(stateCo, GetDeltaTime())
>                 if not ok then
>                     LogError("State coroutine error: " .. tostring(nextState))
>                     return
>                 end
>                 -- 如果状态函数返回了字符串，说明需要切换状态
>                 if type(nextState) == "string" then
>                     current = nextState
>                     break  -- 跳出内层 while，进入新状态
>                 end
>                 -- 否则 yield 当前状态名给 C++ 侧
>                 coroutine.yield(current)
>             end
>         end
>     end)
> end
> ```
>
> #### 集成到 ScriptSystem::Update
> ```cpp
> // 在 ScriptSystem 中持有 state machines
> std::vector<std::unique_ptr<NpcStateMachine>> m_stateMachines;
>
> // Update 中逐帧驱动
> void ScriptSystem::Update(float deltaTime) {
>     // 设置 deltaTime 供 Lua 脚本使用
>     m_lua["_dt"] = deltaTime;
>
>     for (auto& sm : m_stateMachines) {
>         std::string state = sm->Update(deltaTime);
>         // 可选：打印或记录状态变化
>     }
>
>     // 同时也更新 ScriptComponent
>     for (ScriptComponent* script : m_scriptComponents) {
>         if (script) script->Update(deltaTime);
>     }
> }
> ```

---

> [!tip]- 练习 2：脚本事件系统
> #### C++ 侧 — EventBus 类定义与绑定
> ```cpp
> // EventBus.h
> #pragma once
> #include <sol/sol.hpp>
> #include <string>
> #include <vector>
> #include <unordered_map>
> #include <functional>
>
> class EventBus {
> public:
>     // 订阅：返回订阅 ID，用于取消订阅
>     int Subscribe(const std::string& eventName, sol::protected_function callback);
>     void Unsubscribe(const std::string& eventName, int subscriptionId);
>     void UnsubscribeAll(const std::string& eventName);
>
>     // 发布：可变参数传递给所有订阅者
>     void Publish(const std::string& eventName, sol::variadic_args args);
>
>     // 热重载清理：移除所有 Lua 侧订阅（C++ 侧订阅保留）
>     void ClearAllLuaSubscriptions();
>
> private:
>     int m_nextId = 1;
>
>     struct Subscription {
>         int id;
>         sol::protected_function callback;
>         // 标记来源：C++ 或 Lua
>         bool fromLua = false;
>         // 可选：关联的脚本路径，用于热重载时按路径清理
>         std::string scriptPath;
>     };
>
>     // eventName → 订阅列表
>     std::unordered_map<std::string, std::vector<Subscription>> m_subscribers;
> };
> ```
>
> ```cpp
> // EventBus.cpp
> #include "EventBus.h"
> #include <iostream>
> #include <algorithm>
>
> int EventBus::Subscribe(const std::string& eventName, sol::protected_function callback) {
>     int id = m_nextId++;
>     m_subscribers[eventName].push_back({id, callback, true, ""});
>     return id;
> }
>
> void EventBus::Unsubscribe(const std::string& eventName, int subscriptionId) {
>     auto it = m_subscribers.find(eventName);
>     if (it == m_subscribers.end()) return;
>
>     auto& vec = it->second;
>     vec.erase(
>         std::remove_if(vec.begin(), vec.end(),
>             [subscriptionId](const Subscription& s) { return s.id == subscriptionId; }),
>         vec.end()
>     );
> }
>
> void EventBus::UnsubscribeAll(const std::string& eventName) {
>     m_subscribers.erase(eventName);
> }
>
> void EventBus::Publish(const std::string& eventName, sol::variadic_args args) {
>     auto it = m_subscribers.find(eventName);
>     if (it == m_subscribers.end()) return;
>
>     // 复制订阅列表，防止回调中修改订阅列表导致迭代器失效
>     auto subsCopy = it->second;
>     for (auto& sub : subsCopy) {
>         sol::protected_function_result result = sub.callback(args);
>         if (!result.valid()) {
>             sol::error err = result;
>             std::cerr << "[EventBus] Error in subscriber #" << sub.id
>                       << " for event '" << eventName << "': " << err.what() << '\n';
>             // 错误不终止其他订阅者
>         }
>     }
> }
>
> void EventBus::ClearAllLuaSubscriptions() {
>     for (auto& [eventName, subs] : m_subscribers) {
>         subs.erase(
>             std::remove_if(subs.begin(), subs.end(),
>                 [](const Subscription& s) { return s.fromLua; }),
>             subs.end()
>         );
>     }
> }
> ```
>
> #### C++ 侧 — 绑定到 Lua
> ```cpp
> void ScriptSystem::BindEventBus() {
>     // 将 EventBus 作为单例 usertype
>     m_lua.new_usertype<EventBus>("EventBus",
>         "Subscribe",      &EventBus::Subscribe,
>         "Unsubscribe",    &EventBus::Unsubscribe,
>         "UnsubscribeAll", &EventBus::UnsubscribeAll,
>         "Publish",        &EventBus::Publish
>     );
>
>     // 将全局 EventBus 实例暴露为 m_eventBus 的指针/usertype
>     // 方式一：直接设置全局变量（注意生命周期 — m_eventBus 是 ScriptSystem 成员）
>     m_lua["EventBus"] = &m_eventBus;
>
>     // 方式二（更安全）：通过函数获取，确保 Lua 不会持有悬空指针
>     m_lua.set_function("GetEventBus", [this]() -> EventBus* { return &m_eventBus; });
> }
> ```
>
> #### Lua 侧 — 脚本订阅事件
> ```lua
> -- player_health.lua — 监听伤害事件的范例脚本
>
> local subIds = {}   -- 记录所有订阅 ID，便于清理
>
> function SubscribePlayerEvents()
>     local id1 = EventBus:Subscribe("OnPlayerDamaged",
>         function(player, damage, attacker)
>             LogInfo(string.format("[Event] %s took %.0f damage from %s",
>                 player:GetName(), damage, attacker))
>
>             -- 业务逻辑：扣血后检查是否死亡
>             local newHealth = health - damage
>             if newHealth <= 0 then
>                 EventBus:Publish("OnPlayerDied", player)
>             end
>         end)
>     table.insert(subIds, id1)
>
>     local id2 = EventBus:Subscribe("OnPlayerHealed",
>         function(player, amount)
>             LogInfo(string.format("[Event] %s healed %.0f HP", player:GetName(), amount))
>         end)
>     table.insert(subIds, id2)
>
>     local id3 = EventBus:Subscribe("OnPlayerDied",
>         function(player)
>             LogInfo("[Event] Game Over — player has died!")
>             -- 触发复活或游戏结束逻辑
>         end)
>     table.insert(subIds, id3)
> end
>
> -- 热重载时调用：清理所有旧订阅，避免重复回调
> function OnReload()
>     for _, id in ipairs(subIds) do
>         EventBus:Unsubscribe("OnPlayerDamaged", id)
>         EventBus:Unsubscribe("OnPlayerHealed", id)
>         EventBus:Unsubscribe("OnPlayerDied", id)
>     end
>     subIds = {}
>     -- 重新订阅
>     SubscribePlayerEvents()
> end
>
> -- 初始化
> SubscribePlayerEvents()
> ```
>
> #### C++ 侧 — 游戏逻辑发布事件
> ```cpp
> // 伤害系统中发布事件
> void DamageSystem::ApplyDamage(GameObject* target, float amount, GameObject* attacker) {
>     // 扣血逻辑...
>     // target->health -= amount;
>
>     // 发布参数化事件
>     m_eventBus.Publish("OnPlayerDamaged", target, amount, attacker);
> }
>
> // 热重载流程中的订阅清理
> void ScriptSystem::ReloadScript(const std::string& path) {
>     // 1. 通知旧脚本清理其订阅
>     m_lua.safe_script("if OnReload then OnReload() end");
>
>     // 2. 重新执行脚本
>     ExecuteScript(path);
>
>     // 3. 重新绑定回调
>     // ... ScriptComponent::Initialize 会重新获取 Update 等
> }
> ```

---

> [!tip]- 练习 3（可选）：可视化脚本系统
> #### C++ 侧 — 节点与连接定义
> ```cpp
> // VisualScript.h
> #pragma once
> #include <string>
> #include <vector>
> #include <unordered_map>
> #include <memory>
> #include <any>
> #include <functional>
> #include <nlohmann/json.hpp>  // 使用 nlohmann/json 进行序列化
>
> using json = nlohmann::json;
>
> // ============================================================
> // 端口定义
> // ============================================================
> enum class PortDirection { Input, Output };
> enum class PortType { Flow, Float, Vec3, Bool, Any };
>
> struct Port {
>     std::string name;
>     PortDirection direction;
>     PortType type;
>     std::any defaultValue;  // 输入端口可设默认值
> };
>
> // ============================================================
> // 连接定义
> // ============================================================
> struct Link {
>     int sourceNodeId;
>     std::string sourcePort;   // 输出端口名
>     int targetNodeId;
>     std::string targetPort;   // 输入端口名
> };
>
> // ============================================================
> // 节点基类
> // ============================================================
> struct Node {
>     int id;
>     std::string type;   // "Start", "Update", "Move", "Rotate", "If", "Loop"
>     std::vector<Port> ports;
>
>     Node(int id_, const std::string& type_) : id(id_), type(type_) {}
>     virtual ~Node() = default;
> };
>
> // ============================================================
> // 脚本图
> // ============================================================
> class ScriptGraph {
> public:
>     int AddNode(const std::string& type);
>     bool Connect(int srcId, const std::string& srcPort,
>                  int dstId, const std::string& dstPort);
>     void RemoveNode(int id);
>
>     std::string Serialize() const;
>     static std::unique_ptr<ScriptGraph> Deserialize(const std::string& jsonStr);
>
>     // 给解释器使用
>     const std::unordered_map<int, std::unique_ptr<Node>>& GetNodes() const { return m_nodes; }
>     const std::vector<Link>& GetLinks() const { return m_links; }
>
> private:
>     int m_nextId = 1;
>     std::unordered_map<int, std::unique_ptr<Node>> m_nodes;
>     std::vector<Link> m_links;
>
>     // 工厂：根据类型创建带默认端口的节点
>     static std::unique_ptr<Node> CreateNode(int id, const std::string& type);
> };
> ```
>
> #### 节点工厂 — 各类型节点的端口预设
> ```cpp
> // NodeFactory.cpp (内联在 ScriptGraph 实现中)
> std::unique_ptr<Node> ScriptGraph::CreateNode(int id, const std::string& type) {
>     auto node = std::make_unique<Node>(id, type);
>
>     if (type == "Start") {
>         node->ports = {
>             Port{"Out", PortDirection::Output, PortType::Flow},
>         };
>     } else if (type == "Update") {
>         node->ports = {
>             Port{"DeltaTime", PortDirection::Input, PortType::Float, 0.016f},
>             Port{"Out", PortDirection::Output, PortType::Flow},
>         };
>     } else if (type == "Move") {
>         node->ports = {
>             Port{"In",       PortDirection::Input,  PortType::Flow},
>             Port{"Target",   PortDirection::Input,  PortType::Vec3},
>             Port{"Speed",    PortDirection::Input,  PortType::Float, 1.0f},
>             Port{"Out",      PortDirection::Output, PortType::Flow},
>         };
>     } else if (type == "Rotate") {
>         node->ports = {
>             Port{"In",       PortDirection::Input,  PortType::Flow},
>             Port{"Angle",    PortDirection::Input,  PortType::Float},
>             Port{"Axis",     PortDirection::Input,  PortType::Vec3},
>             Port{"Out",      PortDirection::Output, PortType::Flow},
>         };
>     } else if (type == "If") {
>         node->ports = {
>             Port{"In",       PortDirection::Input,  PortType::Flow},
>             Port{"Condition",PortDirection::Input,  PortType::Bool},
>             Port{"True",     PortDirection::Output, PortType::Flow},
>             Port{"False",    PortDirection::Output, PortType::Flow},
>         };
>     } else if (type == "Loop") {
>         node->ports = {
>             Port{"In",       PortDirection::Input,  PortType::Flow},
>             Port{"Count",    PortDirection::Input,  PortType::Float, 1.0f},
>             Port{"LoopBody", PortDirection::Output, PortType::Flow},
>             Port{"Out",      PortDirection::Output, PortType::Flow},
>         };
>     }
>
>     return node;
> }
>
> int ScriptGraph::AddNode(const std::string& type) {
>     int id = m_nextId++;
>     m_nodes[id] = CreateNode(id, type);
>     return id;
> }
>
> bool ScriptGraph::Connect(int srcId, const std::string& srcPort,
>                            int dstId, const std::string& dstPort) {
>     if (!m_nodes.count(srcId) || !m_nodes.count(dstId))
>         return false;
>     m_links.push_back({srcId, srcPort, dstId, dstPort});
>     return true;
> }
>
> void ScriptGraph::RemoveNode(int id) {
>     m_nodes.erase(id);
>     m_links.erase(
>         std::remove_if(m_links.begin(), m_links.end(),
>             [id](const Link& l) { return l.sourceNodeId == id || l.targetNodeId == id; }),
>         m_links.end()
>     );
> }
> ```
>
> #### JSON 序列化
> ```cpp
> std::string ScriptGraph::Serialize() const {
>     json j;
>     j["nodes"] = json::array();
>     for (const auto& [id, node] : m_nodes) {
>         json nj;
>         nj["id"]   = node->id;
>         nj["type"] = node->type;
>         nj["ports"] = json::array();
>         for (const auto& p : node->ports) {
>             json pj;
>             pj["name"]      = p.name;
>             pj["direction"] = (p.direction == PortDirection::Input) ? "in" : "out";
>             pj["portType"]  = static_cast<int>(p.type);
>             nj["ports"].push_back(pj);
>         }
>         j["nodes"].push_back(nj);
>     }
>
>     j["links"] = json::array();
>     for (const auto& l : m_links) {
>         json lj;
>         lj["srcId"]     = l.sourceNodeId;
>         lj["srcPort"]   = l.sourcePort;
>         lj["dstId"]     = l.targetNodeId;
>         lj["dstPort"]   = l.targetPort;
>         j["links"].push_back(lj);
>     }
>
>     return j.dump(2);
> }
>
> std::unique_ptr<ScriptGraph> ScriptGraph::Deserialize(const std::string& jsonStr) {
>     json j = json::parse(jsonStr);
>     auto graph = std::make_unique<ScriptGraph>();
>
>     // 先恢复节点，记录旧 id → 新 id 映射
>     std::unordered_map<int, int> idMap;
>     for (const auto& nj : j["nodes"]) {
>         int oldId = nj["id"].get<int>();
>         int newId = graph->AddNode(nj["type"].get<std::string>());
>         idMap[oldId] = newId;
>     }
>
>     // 恢复连接（使用映射后的新 ID）
>     for (const auto& lj : j["links"]) {
>         int srcId = idMap.at(lj["srcId"].get<int>());
>         int dstId = idMap.at(lj["dstId"].get<int>());
>         graph->Connect(srcId, lj["srcPort"], dstId, lj["dstPort"]);
>     }
>
>     return graph;
> }
> ```
>
> #### 解释器 — 执行脚本图
> ```cpp
> // ScriptInterpreter.h
> #pragma once
> #include "VisualScript.h"
> #include <stack>
>
> class ScriptInterpreter {
> public:
>     explicit ScriptInterpreter(ScriptGraph* graph);
>
>     // 从 Start 节点开始执行
>     void Execute(float deltaTime);
>
>     // 获取/设置变量（如节点执行过程中产生的中间值）
>     std::any GetVariable(const std::string& name) const;
>     void SetVariable(const std::string& name, std::any value);
>
> private:
>     // 获取连接：给定源节点和源端口，找目标节点
>     std::vector<std::pair<Node*, std::string>> GetConnectedTargets(
>         int srcNodeId, const std::string& srcPort) const;
>
>     // 获取输入值：沿连接回溯或使用默认值
>     std::any GetInputValue(int nodeId, const std::string& portName) const;
>
>     // 执行单个节点，返回下一个要执行的节点列表（Flow 端口连接的目标）
>     std::vector<Node*> ExecuteNode(Node* node);
>
>     ScriptGraph* m_graph;
>     std::unordered_map<std::string, std::any> m_variables;
>     std::unordered_map<int, int> m_loopCounters; // nodeId → 剩余循环次数
>     float m_deltaTime = 0.0f;
> };
> ```
>
> ```cpp
> // ScriptInterpreter.cpp
> #include "ScriptInterpreter.h"
> #include <queue>
> #include <cassert>
>
> ScriptInterpreter::ScriptInterpreter(ScriptGraph* graph)
>     : m_graph(graph) {}
>
> std::vector<std::pair<Node*, std::string>> ScriptInterpreter::GetConnectedTargets(
>         int srcNodeId, const std::string& srcPort) const {
>     std::vector<std::pair<Node*, std::string>> results;
>     for (const auto& link : m_graph->GetLinks()) {
>         if (link.sourceNodeId == srcNodeId && link.sourcePort == srcPort) {
>             auto it = m_graph->GetNodes().find(link.targetNodeId);
>             if (it != m_graph->GetNodes().end()) {
>                 results.emplace_back(it->second.get(), link.targetPort);
>             }
>         }
>     }
>     return results;
> }
>
> std::any ScriptInterpreter::GetInputValue(int nodeId, const std::string& portName) const {
>     // 查找是否有连接提供此输入端口的输入
>     for (const auto& link : m_graph->GetLinks()) {
>         if (link.targetNodeId == nodeId && link.targetPort == portName) {
>             // 从源节点的输出端口获取值（简化：查变量表）
>             std::string key = std::to_string(link.sourceNodeId) + ":" + link.sourcePort;
>             auto it = m_variables.find(key);
>             if (it != m_variables.end()) return it->second;
>         }
>     }
>     // 回退到端口的默认值
>     auto nodeIt = m_graph->GetNodes().find(nodeId);
>     if (nodeIt != m_graph->GetNodes().end()) {
>         for (const auto& p : nodeIt->second->ports) {
>             if (p.name == portName && p.direction == PortDirection::Input) {
>                 return p.defaultValue;
>             }
>         }
>     }
>     return {};
> }
>
> std::vector<Node*> ScriptInterpreter::ExecuteNode(Node* node) {
>     std::vector<Node*> nextNodes;
>
>     if (node->type == "Start") {
>         auto targets = GetConnectedTargets(node->id, "Out");
>         for (auto& [tgt, _] : targets) nextNodes.push_back(tgt);
>     }
>     else if (node->type == "Update") {
>         auto dt = GetInputValue(node->id, "DeltaTime");
>         if (dt.has_value()) m_deltaTime = std::any_cast<float>(dt);
>         auto targets = GetConnectedTargets(node->id, "Out");
>         for (auto& [tgt, _] : targets) nextNodes.push_back(tgt);
>     }
>     else if (node->type == "Move") {
>         // 读取 Target 和 Speed，执行移动逻辑
>         auto target  = GetInputValue(node->id, "Target");
>         auto speed   = GetInputValue(node->id, "Speed");
>         // 实际实现中会调用引擎 API 移动对象；这里简化
>         float sp = speed.has_value() ? std::any_cast<float>(speed) : 1.0f;
>         // ... Lerp toward target by sp * m_deltaTime
>
>         auto targets = GetConnectedTargets(node->id, "Out");
>         for (auto& [tgt, _] : targets) nextNodes.push_back(tgt);
>     }
>     else if (node->type == "Rotate") {
>         auto angleVal = GetInputValue(node->id, "Angle");
>         auto axisVal  = GetInputValue(node->id, "Axis");
>         float angle = angleVal.has_value() ? std::any_cast<float>(angleVal) : 0.0f;
>         // ... 执行旋转
>
>         auto targets = GetConnectedTargets(node->id, "Out");
>         for (auto& [tgt, _] : targets) nextNodes.push_back(tgt);
>     }
>     else if (node->type == "If") {
>         auto cond = GetInputValue(node->id, "Condition");
>         bool result = cond.has_value() ? std::any_cast<bool>(cond) : false;
>
>         std::string portName = result ? "True" : "False";
>         auto targets = GetConnectedTargets(node->id, portName);
>         for (auto& [tgt, _] : targets) nextNodes.push_back(tgt);
>     }
>     else if (node->type == "Loop") {
>         auto& counter = m_loopCounters[node->id];
>         // 首次进入：读取 Count 输入端口的初始值
>         if (counter == 0) {
>             auto cnt = GetInputValue(node->id, "Count");
>             counter = static_cast<int>(cnt.has_value() ? std::any_cast<float>(cnt) : 1.0f);
>         }
>
>         if (counter > 0) {
>             --counter;
>             auto bodyTargets = GetConnectedTargets(node->id, "LoopBody");
>             for (auto& [tgt, _] : bodyTargets) nextNodes.push_back(tgt);
>         } else {
>             // 循环结束，走 Out 端口
>             counter = 0;  // 重置
>             auto outTargets = GetConnectedTargets(node->id, "Out");
>             for (auto& [tgt, _] : outTargets) nextNodes.push_back(tgt);
>         }
>     }
>
>     return nextNodes;
> }
>
> void ScriptInterpreter::Execute(float deltaTime) {
>     m_deltaTime = deltaTime;
>
>     // BFS 遍历执行图：从 Start 节点开始
>     std::queue<Node*> queue;
>     for (const auto& [id, node] : m_graph->GetNodes()) {
>         if (node->type == "Start") {
>             queue.push(node.get());
>             break;
>         }
>     }
>
>     std::unordered_set<int> visited;
>     while (!queue.empty()) {
>         Node* current = queue.front();
>         queue.pop();
>
>         // 避免无限循环（Loop 节点由内部计数控制，这里只防普通环路）
>         if (visited.count(current->id)) continue;
>         visited.insert(current->id);
>
>         auto next = ExecuteNode(current);
>         for (Node* n : next) {
>             queue.push(n);
>         }
>     }
> }
>
> std::any ScriptInterpreter::GetVariable(const std::string& name) const {
>     auto it = m_variables.find(name);
>     return (it != m_variables.end()) ? it->second : std::any{};
> }
>
> void ScriptInterpreter::SetVariable(const std::string& name, std::any value) {
>     m_variables[name] = std::move(value);
> }
> ```
>
> #### 使用示例：构建并执行一个简单的脚本图
> ```cpp
> void DemoVisualScript() {
>     ScriptGraph graph;
>
>     // 创建节点
>     int startId  = graph.AddNode("Start");
>     int updateId = graph.AddNode("Update");
>     int moveId   = graph.AddNode("Move");
>     int loopId   = graph.AddNode("Loop");
>     int ifId     = graph.AddNode("If");
>     int rotateId = graph.AddNode("Rotate");
>
>     // 连接节点
>     graph.Connect(startId,  "Out",       updateId,  "In");
>     graph.Connect(updateId, "Out",       loopId,    "In");
>     graph.Connect(loopId,   "LoopBody",  ifId,      "In");
>     graph.Connect(ifId,     "True",      moveId,    "In");
>     graph.Connect(ifId,     "False",     rotateId,  "In");
>     graph.Connect(moveId,   "Out",       loopId,    "In");     // 回到 Loop
>     graph.Connect(rotateId, "Out",       loopId,    "In");     // 回到 Loop
>
>     // 序列化
>     std::string json = graph.Serialize();
>     std::cout << "Serialized graph:\n" << json << '\n';
>
>     // 反序列化
>     auto restored = ScriptGraph::Deserialize(json);
>
>     // 执行
>     ScriptInterpreter interpreter(restored.get());
>     interpreter.SetVariable(std::to_string(ifId) + ":Condition", true);
>     interpreter.Execute(0.016f);
> }
> ```
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
