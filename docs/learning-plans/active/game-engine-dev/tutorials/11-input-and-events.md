---
title: "输入系统与事件管理"
updated: 2026-06-05
---

# 输入系统与事件管理

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 4h
> 前置知识: 无

---

## 1. 概念讲解

输入系统是游戏引擎中连接玩家与游戏世界的桥梁。它负责将物理设备（键盘、鼠标、手柄、触屏）产生的原始信号转换为游戏可以理解和响应的逻辑动作。一个设计良好的输入系统需要具备低延迟、高可扩展性和跨平台能力。

### 为什么需要这个？

游戏是交互式体验，玩家的每一个操作——按下跳跃键、移动鼠标瞄准、扳动手柄扳机——都需要被引擎准确、及时地捕获和处理。没有输入系统，游戏就只是一段无法互动的动画。

输入系统解决的核心问题包括：

1. **设备异构性**：不同平台使用不同的输入设备。PC 有键鼠，主机有手柄，手机有触屏和陀螺仪。引擎需要统一的抽象来屏蔽底层差异。
2. **按键绑定与重映射**：玩家可能希望自定义按键布局。硬编码 "W 键 = 前进" 无法满足需求。
3. **输入延迟**：从玩家按下按键到屏幕上出现响应，每一毫秒的延迟都会影响体验。格斗游戏和 FPS 对延迟尤其敏感。
4. **多人与多设备**：本地多人游戏需要区分不同玩家的手柄输入。
5. **输入回放与调试**：记录输入序列用于复现 Bug 或制作回放系统。
6. **组合输入**：如 "Ctrl+Shift+S" 或手柄的复杂连招需要特殊处理。

### 核心思想

#### 1.1 输入设备抽象

输入设备抽象的核心思想是将物理设备统一视为 "输入源"，每个源产生 "输入事件"。事件包含以下信息：

- **设备类型**：Keyboard / Mouse / Gamepad / Touch
- **事件类型**：Pressed / Released / Moved / AxisChanged
- **物理标识**：键码(KeyCode)、按钮ID、轴ID
- **值**：布尔（按下/释放）或浮点（轴值，如摇杆偏移量）
- **时间戳**：事件发生的精确时间

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Keyboard  │    │    Mouse    │    │   Gamepad   │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ▼
              ┌─────────────────────┐
              │   Input Device Abstraction  │
              │   (统一的事件格式)     │
              └─────────────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │   Input Manager     │
              └─────────────────────┘
```

#### 1.2 轮询(Polling) vs 事件驱动(Event-driven)

这是输入系统两种截然不同的处理模式：

**轮询模式**：游戏主循环每帧主动查询输入设备当前状态。

```cpp
// 轮询示例
void GameLoop() {
    while (running) {
        // 每帧查询按键状态
        if (Input::IsKeyPressed(KEY_W)) {
            player.MoveForward();
        }
        if (Input::IsKeyPressed(KEY_SPACE)) {
            player.Jump();
        }
        Update();
        Render();
    }
}
```

优点：
- 实现简单直观
- 与游戏帧率天然对齐
- 适合持续状态（如按住 W 前进）

缺点：
- 可能丢失快速按键（如果在两帧之间按下并释放）
- 输入延迟最高可达一帧（16.6ms @ 60fps）
- 不适合处理文本输入等需要精确时序的场景

**事件驱动模式**：操作系统在输入发生时立即通知应用程序。

```cpp
// 事件驱动示例
void OnKeyPressed(KeyEvent event) {
    if (event.key == KEY_SPACE) {
        player.Jump();
    }
}
```

优点：
- 不丢失输入事件
- 延迟更低（绕过帧率限制）
- 适合离散动作（如打开菜单、触发技能）

缺点：
- 事件可能在任意时刻到达，需要线程安全处理
- 与游戏更新循环解耦，需要额外同步机制
- 实现复杂度更高

**现代引擎通常混合使用两种模式**：
- 事件驱动收集原始输入，存入缓冲区
- 游戏循环开始时，一次性处理缓冲区中的所有事件
- 轮询用于查询当前持续状态（如摇杆方向）

#### 1.3 事件系统架构

事件系统是输入处理的核心基础设施，常见的架构模式有三种：

**观察者模式(Observer Pattern)**：

被观察者（Subject）维护一个观察者列表，状态变化时通知所有观察者。

```
┌──────────────┐         ┌──────────────┐
│   Subject    │◄────────│   Observer   │
│ (InputManager)│         │  (GameSystem)│
└──────┬───────┘         └──────────────┘
       │ notify()
       ▼
┌──────────────┐
│   Observer   │
│  (UISystem)  │
└──────────────┘
```

优点：松耦合，观察者可以自由订阅/取消订阅。
缺点：通知顺序不确定，难以控制优先级。

**发布-订阅模式(Pub-Sub)**：

引入事件总线（Event Bus）作为中间层，发布者和订阅者彼此不知道对方存在。

```
Publisher ──► Event Bus ──► Subscriber A
                │
                └──► Subscriber B
                │
                └──► Subscriber C
```

优点：完全解耦，支持动态添加/移除订阅者。
缺点：调试困难，可能出现事件风暴。

**事件队列(Event Queue)**：

所有事件先入队，后处理。消费者按顺序从队列中取出事件处理。

```
[Event1] → [Event2] → [Event3] → ... → [Processor]
```

优点：天然支持异步和缓冲，易于实现输入回放。
缺点：增加延迟（排队时间）。

实际引擎中通常将三者结合：使用事件队列缓冲原始输入，通过发布-订阅分发给感兴趣的系统，各系统内部使用观察者模式管理回调。

#### 1.4 输入映射(Input Mapping)

输入映射解决 "物理按键 → 逻辑动作" 的转换问题。

**为什么需要映射？**

```cpp
// ❌ 硬编码——不可配置
if (key == GLFW_KEY_W) player.MoveForward();
if (key == GLFW_KEY_SPACE) player.Jump();

// ✅ 映射——灵活可配置
if (action == "MoveForward") player.MoveForward();
if (action == "Jump") player.Jump();
// 映射表: W → MoveForward, Space → Jump（可修改）
```

**映射层级**：

```
物理层                    逻辑层                    游戏层
┌─────────┐             ┌─────────┐             ┌─────────┐
│ KEY_W   │ ────────►   │ Move    │ ────────►   │ Player  │
│         │   映射      │ Forward │   绑定      │ Walk()  │
└─────────┘             └─────────┘             └─────────┘

┌─────────┐             ┌─────────┐             ┌─────────┐
│ GP_A    │ ────────►   │ Jump    │ ────────►   │ Player  │
│ (手柄A键)│   映射      │         │   绑定      │ Jump()  │
└─────────┘             └─────────┘             └─────────┘
```

**轴映射(Axis Mapping)**：

模拟输入（摇杆、扳机）产生 -1 到 1 的浮点值，需要映射到游戏动作：

```
左摇杆 X 轴 → [-1, 1] → MoveRight (负值 = 左移)
左摇杆 Y 轴 → [-1, 1] → MoveForward (负值 = 后退)
右扳机     → [0, 1]  → Accelerate
```

**修饰键与组合**：

```
Shift + W → Sprint (冲刺)
Ctrl + Click → ContextMenu (右键菜单)
```

#### 1.5 输入缓冲和状态管理

**输入状态**：

每帧需要追踪的按键状态有三种：

| 状态 | 含义 | 典型用途 |
|------|------|----------|
| Pressed | 当前帧按下 | 触发一次性动作（跳跃、开火） |
| Held | 持续按住 | 持续动作（移动、瞄准） |
| Released | 当前帧释放 | 结束动作（停止蓄力、松开攀爬） |

**输入缓冲(Input Buffering)**：

格斗游戏中，玩家可能在角色硬直结束前提前输入。输入缓冲将输入暂存一小段时间（通常 3-8 帧），在角色恢复可行动状态时执行。

```
时间轴:  [硬直中]───[硬直结束]───►
输入:        [Jump]           (提前输入)
缓冲:        [3帧缓冲]        (暂存)
执行:                      [Jump] (硬直结束后执行)
```

**消费(Consume)**：

一个输入事件可能被多个系统响应（如 UI 和 游戏世界都监听 ESC 键）。"消费"机制确保事件只被第一个处理的系统响应：

```cpp
if (UI::IsOpen() && event.key == KEY_ESC) {
    UI::Close();
    event.Consumed = true;  // 标记已消费
    return;                 // 不再传递给游戏世界
}
if (event.key == KEY_ESC && !event.Consumed) {
    Game::Pause();          // UI 未打开时才暂停游戏
}
```

#### 1.6 游戏手柄支持

**XInput**（Windows/Xbox）：

微软提供的原生手柄 API，支持 Xbox 控制器。

```cpp
// XInput 核心结构
XINPUT_STATE state;
DWORD result = XInputGetState(controllerIndex, &state);

// 读取按钮
bool aButton = state.Gamepad.wButtons & XINPUT_GAMEPAD_A;
// 读取左摇杆 (短整型，范围 -32768 ~ 32767)
float thumbLX = state.Gamepad.sThumbLX / 32768.0f;
```

**SDL_GameController**（跨平台）：

SDL 提供的高级手柄抽象，将不同厂商的手柄统一映射到标准布局（ABXY、摇杆、扳机等）。

**死区(Deadzone)**：

摇杆在中心位置时由于硬件误差会产生微小偏移，需要设置死区忽略这些噪声：

```cpp
float ApplyDeadzone(float value, float deadzone) {
    if (std::abs(value) < deadzone) return 0.0f;
    // 重新映射剩余范围到 [0, 1]
    return (value - deadzone * Sign(value)) / (1.0f - deadzone);
}
```

#### 1.7 输入延迟和帧对齐

输入延迟(Input Lag)是玩家操作到屏幕响应之间的时间。主要来源：

1. **硬件延迟**：USB 轮询率（通常 125Hz = 8ms，游戏鼠标可达 1000Hz = 1ms）
2. **操作系统延迟**：Windows 消息队列处理时间
3. **引擎处理**：事件收集、游戏逻辑更新
4. **渲染延迟**：CPU 提交渲染命令到 GPU 完成扫描输出
5. **显示延迟**：显示器刷新率和响应时间

**减少延迟的策略**：

- **原始输入(Raw Input)**：绕过操作系统输入处理，直接读取设备数据
- **高轮询率**：使用 1000Hz 轮询率的鼠标
- **输入预测**：在服务器端游戏中，客户端预测输入结果并立即显示
- **降低帧缓冲**：减少 GPU 预渲染帧数

**帧对齐**：

输入处理应与游戏更新同步。常见模式：

```
收集输入 → 固定时间步长更新 → 渲染（插值）
    ↑_________________________________|
```

使用固定时间步长（如 1/60 秒）更新游戏逻辑，渲染时插值显示，确保输入响应的一致性。

#### 1.8 命令模式(Command Pattern)与输入回放

**命令模式**将操作封装为对象：

```cpp
class ICommand {
public:
    virtual ~ICommand() = default;
    virtual void Execute() = 0;
    virtual void Undo() = 0;
};

class MoveCommand : public ICommand {
    Entity* entity;
    Vec3 direction;
public:
    void Execute() override { entity->Move(direction); }
    void Undo() override { entity->Move(-direction); }
};
```

**输入回放**：

记录每帧的输入状态，之后重放这些状态来复现游戏过程。

```cpp
struct InputFrame {
    uint32_t frameNumber;
    uint64_t keyStates;      // 位掩码表示按键状态
    float mouseX, mouseY;
    float axisValues[8];
};

std::vector<InputFrame> recording;

// 回放时
for (const auto& frame : recording) {
    Input::LoadState(frame);
    Game::Update();
}
```

这在以下场景非常有用：
- **调试**：复现难以触发的 Bug
- **回放系统**：保存精彩操作
- **网络同步**：确定性回放用于客户端预测和服务器校验

### 平台差异

不同平台的输入系统有显著差异：

| 特性 | PC (Windows/Linux/macOS) | 主机 (PS/Xbox/Switch) | 移动 (iOS/Android) |
|------|--------------------------|----------------------|-------------------|
| 主要输入 | 键鼠 + 手柄 | 手柄 | 触屏 + 陀螺仪 |
| 按键数量 | 多（键盘100+键） | 固定（约15个按钮+4轴） | 无物理按键 |
| 指针设备 | 鼠标（高精度） | 无（右摇杆模拟） | 触摸（多点） |
| 文本输入 | 物理键盘 | 屏幕键盘 | 屏幕键盘 |
| API | Raw Input / XInput / SDL | 厂商专有 SDK | Touch API / 传感器 API |
| 特殊考虑 | 多键同时按下（NKRO） | 手柄震动/LED/触摸板 | 虚拟摇杆、手势识别 |

**跨平台抽象策略**：

1. 定义平台无关的输入事件格式
2. 每个平台实现独立的 "InputBackend"
3. 运行时根据平台加载对应后端
4. UI 层使用虚拟输入（如虚拟摇杆）适配触屏

---

## 2. 代码示例

以下是一个完整的、自包含的输入系统实现，包含事件系统、输入管理器、动作映射和输入回放。

```cpp
// ============================================================
// input_system.hpp — 游戏引擎输入系统完整实现
// ============================================================
// 编译: g++ -std=c++17 input_demo.cpp -o input_demo
// ============================================================

#pragma once

#include <iostream>
#include <vector>
#include <map>
#include <string>
#include <functional>
#include <memory>
#include <queue>
#include <chrono>
#include <cmath>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <iomanip>

// ============================================================
// 1. 基础类型与枚举
// ============================================================

enum class DeviceType {
    Keyboard,
    Mouse,
    Gamepad,
    Touch
};

enum class InputEventType {
    Pressed,      // 按下（离散）
    Released,     // 释放（离散）
    Held,         // 持续按住
    AxisChanged,  // 模拟值变化
    Moved         // 位置变化（鼠标/触摸）
};

enum class KeyCode : int {
    // 字母
    A = 0, B, C, D, E, F, G, H, I, J, K, L, M,
    N, O, P, Q, R, S, T, U, V, W, X, Y, Z,
    // 数字
    Num0, Num1, Num2, Num3, Num4, Num5, Num6, Num7, Num8, Num9,
    // 功能键
    F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12,
    // 控制键
    Escape, Space, Enter, Tab, Backspace,
    LeftShift, RightShift, LeftCtrl, RightCtrl,
    LeftAlt, RightAlt, LeftSuper, RightSuper,
    // 方向键
    Up, Down, Left, Right,
    // 鼠标
    MouseLeft, MouseRight, MouseMiddle,
    MouseWheelUp, MouseWheelDown,
    // 手柄按钮 (Xbox 布局)
    Gamepad_A, Gamepad_B, Gamepad_X, Gamepad_Y,
    Gamepad_LB, Gamepad_RB,
    Gamepad_Back, Gamepad_Start,
    Gamepad_LS, Gamepad_RS,  // 摇杆按下
    Gamepad_DPadUp, Gamepad_DPadDown, Gamepad_DPadLeft, Gamepad_DPadRight,
    // 手柄轴
    Gamepad_LeftStickX, Gamepad_LeftStickY,
    Gamepad_RightStickX, Gamepad_RightStickY,
    Gamepad_LeftTrigger, Gamepad_RightTrigger,
    // 特殊
    Unknown,
    Count
};

// 将 KeyCode 转为可读字符串
inline std::string KeyCodeToString(KeyCode key) {
    static const std::map<KeyCode, std::string> names = {
        {KeyCode::A, "A"}, {KeyCode::B, "B"}, {KeyCode::C, "C"},
        {KeyCode::D, "D"}, {KeyCode::E, "E"}, {KeyCode::F, "F"},
        {KeyCode::G, "G"}, {KeyCode::H, "H"}, {KeyCode::I, "I"},
        {KeyCode::J, "J"}, {KeyCode::K, "K"}, {KeyCode::L, "L"},
        {KeyCode::M, "M"}, {KeyCode::N, "N"}, {KeyCode::O, "O"},
        {KeyCode::P, "P"}, {KeyCode::Q, "Q"}, {KeyCode::R, "R"},
        {KeyCode::S, "S"}, {KeyCode::T, "T"}, {KeyCode::U, "U"},
        {KeyCode::V, "V"}, {KeyCode::W, "W"}, {KeyCode::X, "X"},
        {KeyCode::Y, "Y"}, {KeyCode::Z, "Z"},
        {KeyCode::Num0, "0"}, {KeyCode::Num1, "1"}, {KeyCode::Num2, "2"},
        {KeyCode::Num3, "3"}, {KeyCode::Num4, "4"}, {KeyCode::Num5, "5"},
        {KeyCode::Num6, "6"}, {KeyCode::Num7, "7"}, {KeyCode::Num8, "8"},
        {KeyCode::Num9, "9"},
        {KeyCode::Space, "Space"}, {KeyCode::Enter, "Enter"},
        {KeyCode::Escape, "Escape"}, {KeyCode::Tab, "Tab"},
        {KeyCode::Up, "Up"}, {KeyCode::Down, "Down"},
        {KeyCode::Left, "Left"}, {KeyCode::Right, "Right"},
        {KeyCode::LeftShift, "LShift"}, {KeyCode::LeftCtrl, "LCtrl"},
        {KeyCode::MouseLeft, "MouseL"}, {KeyCode::MouseRight, "MouseR"},
        {KeyCode::Gamepad_A, "GP_A"}, {KeyCode::Gamepad_B, "GP_B"},
        {KeyCode::Gamepad_X, "GP_X"}, {KeyCode::Gamepad_Y, "GP_Y"},
        {KeyCode::Gamepad_LeftStickX, "GP_LStickX"},
        {KeyCode::Gamepad_LeftStickY, "GP_LStickY"},
        {KeyCode::Gamepad_LeftTrigger, "GP_LTrigger"},
        {KeyCode::Gamepad_RightTrigger, "GP_RTrigger"},
    };
    auto it = names.find(key);
    return it != names.end() ? it->second : "Unknown";
}

// ============================================================
// 2. 事件系统 (Event System)
// ============================================================

// 前向声明
template<typename T>
class EventDispatcher;

// 基础事件接口
class IEvent {
public:
    virtual ~IEvent() = default;
    virtual std::string GetName() const = 0;
    virtual std::string ToString() const = 0;
    bool Consumed = false;
};

// 输入事件
struct InputEvent : public IEvent {
    DeviceType Device;
    InputEventType Type;
    KeyCode Key;
    float Value = 0.0f;        // 轴值或鼠标偏移
    float PosX = 0.0f;         // 鼠标/触摸位置
    float PosY = 0.0f;
    uint64_t Timestamp = 0;    // 微秒时间戳
    int GamepadIndex = -1;     // 手柄编号（-1 = 无）

    std::string GetName() const override { return "InputEvent"; }

    std::string ToString() const override {
        std::ostringstream oss;
        oss << "[Input] ";
        switch (Type) {
            case InputEventType::Pressed: oss << "Pressed"; break;
            case InputEventType::Released: oss << "Released"; break;
            case InputEventType::Held: oss << "Held"; break;
            case InputEventType::AxisChanged: oss << "Axis"; break;
            case InputEventType::Moved: oss << "Moved"; break;
        }
        oss << " " << KeyCodeToString(Key);
        if (Type == InputEventType::AxisChanged || std::abs(Value) > 0.001f) {
            oss << " value=" << std::fixed << std::setprecision(3) << Value;
        }
        if (PosX != 0 || PosY != 0) {
            oss << " pos=(" << PosX << ", " << PosY << ")";
        }
        if (GamepadIndex >= 0) {
            oss << " pad=" << GamepadIndex;
        }
        return oss.str();
    }
};

// 动作事件（映射后的逻辑动作）
struct ActionEvent : public IEvent {
    std::string ActionName;
    float Value = 1.0f;        // 动作强度（按钮=1，轴=浮点值）
    InputEventType Type;
    uint64_t Timestamp = 0;

    std::string GetName() const override { return "ActionEvent"; }

    std::string ToString() const override {
        std::ostringstream oss;
        oss << "[Action] '" << ActionName << "' ";
        switch (Type) {
            case InputEventType::Pressed: oss << "triggered"; break;
            case InputEventType::Released: oss << "released"; break;
            case InputEventType::AxisChanged: oss << "value=" << Value; break;
            default: oss << "active"; break;
        }
        return oss.str();
    }
};

// 事件监听器接口
template<typename T>
using EventCallback = std::function<void(const T&)>;

// 事件分发器（发布-订阅实现）
template<typename T>
class EventDispatcher {
public:
    using Callback = EventCallback<T>;

    // 订阅事件，返回订阅ID用于取消订阅
    int Subscribe(Callback callback) {
        int id = nextId++;
        callbacks[id] = callback;
        return id;
    }

    void Unsubscribe(int id) {
        callbacks.erase(id);
    }

    // 发布事件给所有订阅者
    void Publish(const T& event) {
        // 复制回调列表，防止回调中修改订阅列表
        auto callbacksCopy = callbacks;
        for (const auto& [id, cb] : callbacksCopy) {
            if (callbacks.find(id) != callbacks.end()) {  // 检查是否仍有效
                cb(event);
            }
        }
    }

    size_t SubscriberCount() const { return callbacks.size(); }

private:
    std::map<int, Callback> callbacks;
    int nextId = 0;
};

// 全局事件总线
class EventBus {
public:
    EventDispatcher<InputEvent> InputEvents;
    EventDispatcher<ActionEvent> ActionEvents;

    static EventBus& Instance() {
        static EventBus instance;
        return instance;
    }

private:
    EventBus() = default;
};

// ============================================================
// 3. 输入状态管理
// ============================================================

class InputState {
public:
    // 当前帧按键状态（位掩码，最多支持64个键）
    // 实际引擎中应使用更大的位集或哈希表
    std::map<KeyCode, bool> CurrentKeys;
    std::map<KeyCode, bool> PreviousKeys;

    // 轴值状态
    std::map<KeyCode, float> AxisValues;

    // 鼠标位置
    float MouseX = 0.0f, MouseY = 0.0f;
    float MouseDeltaX = 0.0f, MouseDeltaY = 0.0f;

    // 更新上一帧状态
    void UpdatePrevious() {
        PreviousKeys = CurrentKeys;
        MouseDeltaX = 0;
        MouseDeltaY = 0;
    }

    // 查询接口
    bool IsPressed(KeyCode key) const {
        auto it = CurrentKeys.find(key);
        return it != CurrentKeys.end() && it->second;
    }

    bool WasPressed(KeyCode key) const {
        auto it = PreviousKeys.find(key);
        return it != PreviousKeys.end() && it->second;
    }

    // 本帧刚按下
    bool IsJustPressed(KeyCode key) const {
        return IsPressed(key) && !WasPressed(key);
    }

    // 本帧刚释放
    bool IsJustReleased(KeyCode key) const {
        return !IsPressed(key) && WasPressed(key);
    }

    float GetAxis(KeyCode key) const {
        auto it = AxisValues.find(key);
        return it != AxisValues.end() ? it->second : 0.0f;
    }
};

// ============================================================
// 4. 输入映射系统 (Action Mapping)
// ============================================================

// 映射条目
struct MappingEntry {
    KeyCode Key;
    float Scale = 1.0f;        // 轴缩放（如 W=+1, S=-1）
    DeviceType Device;
    int GamepadIndex = -1;     // -1 = 任意手柄
};

// 动作定义
struct ActionDefinition {
    std::string Name;
    std::vector<MappingEntry> Mappings;
    bool IsAxis = false;       // 是否为轴动作（产生浮点值）
    float Deadzone = 0.1f;     // 死区阈值
};

class ActionMappingSystem {
public:
    // 注册动作
    void RegisterAction(const std::string& name, bool isAxis = false, float deadzone = 0.1f) {
        ActionDefinition def;
        def.Name = name;
        def.IsAxis = isAxis;
        def.Deadzone = deadzone;
        actions[name] = def;
    }

    // 绑定按键到动作
    void BindKey(const std::string& actionName, KeyCode key, float scale = 1.0f,
                 DeviceType device = DeviceType::Keyboard, int gamepadIndex = -1) {
        auto it = actions.find(actionName);
        if (it == actions.end()) {
            std::cerr << "Action '" << actionName << "' not registered!" << std::endl;
            return;
        }
        MappingEntry entry{key, scale, device, gamepadIndex};
        it->second.Mappings.push_back(entry);
    }

    // 从配置文件加载映射（简化版）
    void LoadFromConfig(const std::map<std::string, std::vector<std::pair<KeyCode, float>>>& config) {
        for (const auto& [actionName, bindings] : config) {
            bool isAxis = false;
            for (const auto& [key, scale] : bindings) {
                if (scale != 1.0f && scale != 0.0f) {
                    isAxis = true;
                    break;
                }
            }
            RegisterAction(actionName, isAxis);
            for (const auto& [key, scale] : bindings) {
                BindKey(actionName, key, scale);
            }
        }
    }

    // 根据输入状态计算动作值
    std::vector<ActionEvent> EvaluateActions(const InputState& state) const {
        std::vector<ActionEvent> results;
        uint64_t now = GetTimestamp();

        for (const auto& [name, def] : actions) {
            if (def.IsAxis) {
                float value = 0.0f;
                for (const auto& mapping : def.Mappings) {
                    if (IsAxisKey(mapping.Key)) {
                        float axisVal = state.GetAxis(mapping.Key) * mapping.Scale;
                        value += ApplyDeadzone(axisVal, def.Deadzone);
                    } else if (state.IsPressed(mapping.Key)) {
                        value += mapping.Scale;
                    }
                }
                // 钳制到 [-1, 1]
                value = std::max(-1.0f, std::min(1.0f, value));
                if (std::abs(value) > def.Deadzone) {
                    ActionEvent evt;
                    evt.ActionName = name;
                    evt.Value = value;
                    evt.Type = InputEventType::AxisChanged;
                    evt.Timestamp = now;
                    results.push_back(evt);
                }
            } else {
                // 按钮动作：检测按下/释放
                for (const auto& mapping : def.Mappings) {
                    if (state.IsJustPressed(mapping.Key)) {
                        ActionEvent evt;
                        evt.ActionName = name;
                        evt.Value = 1.0f;
                        evt.Type = InputEventType::Pressed;
                        evt.Timestamp = now;
                        results.push_back(evt);
                    }
                    if (state.IsJustReleased(mapping.Key)) {
                        ActionEvent evt;
                        evt.ActionName = name;
                        evt.Value = 0.0f;
                        evt.Type = InputEventType::Released;
                        evt.Timestamp = now;
                        results.push_back(evt);
                    }
                }
            }
        }
        return results;
    }

    void PrintMappings() const {
        std::cout << "\n=== Action Mappings ===" << std::endl;
        for (const auto& [name, def] : actions) {
            std::cout << "Action: '" << name << "' (" << (def.IsAxis ? "axis" : "button") << ")" << std::endl;
            for (const auto& mapping : def.Mappings) {
                std::cout << "  -> " << KeyCodeToString(mapping.Key);
                if (mapping.Scale != 1.0f) std::cout << " * " << mapping.Scale;
                std::cout << std::endl;
            }
        }
        std::cout << "======================\n" << std::endl;
    }

private:
    std::map<std::string, ActionDefinition> actions;

    bool IsAxisKey(KeyCode key) const {
        return key == KeyCode::Gamepad_LeftStickX || key == KeyCode::Gamepad_LeftStickY ||
               key == KeyCode::Gamepad_RightStickX || key == KeyCode::Gamepad_RightStickY ||
               key == KeyCode::Gamepad_LeftTrigger || key == KeyCode::Gamepad_RightTrigger;
    }

    float ApplyDeadzone(float value, float deadzone) const {
        if (std::abs(value) < deadzone) return 0.0f;
        float sign = value > 0 ? 1.0f : -1.0f;
        return (value - deadzone * sign) / (1.0f - deadzone);
    }

    static uint64_t GetTimestamp() {
        auto now = std::chrono::steady_clock::now().time_since_epoch();
        return std::chrono::duration_cast<std::chrono::microseconds>(now).count();
    }
};

// ============================================================
// 5. 输入回放系统
// ============================================================

// 单帧输入快照
struct InputSnapshot {
    uint32_t FrameNumber;
    std::map<KeyCode, bool> KeyStates;
    std::map<KeyCode, float> AxisStates;
    float MouseX, MouseY;
    uint64_t Timestamp;
};

class InputRecorder {
public:
    enum class Mode {
        Idle,
        Recording,
        Playing
    };

    void StartRecording() {
        recording.clear();
        mode = Mode::Recording;
        frameCounter = 0;
        std::cout << "[Recorder] Started recording" << std::endl;
    }

    void StopRecording() {
        mode = Mode::Idle;
        std::cout << "[Recorder] Stopped. Recorded " << recording.size() << " frames" << std::endl;
    }

    void StartPlayback() {
        if (recording.empty()) {
            std::cout << "[Recorder] Nothing to playback!" << std::endl;
            return;
        }
        mode = Mode::Playing;
        playbackIndex = 0;
        std::cout << "[Recorder] Started playback (" << recording.size() << " frames)" << std::endl;
    }

    void StopPlayback() {
        mode = Mode::Idle;
        std::cout << "[Recorder] Playback stopped" << std::endl;
    }

    // 每帧调用：记录当前状态或回放下一帧
    void Update(InputState& state) {
        if (mode == Mode::Recording) {
            InputSnapshot snap;
            snap.FrameNumber = frameCounter++;
            snap.KeyStates = state.CurrentKeys;
            snap.AxisStates = state.AxisValues;
            snap.MouseX = state.MouseX;
            snap.MouseY = state.MouseY;
            snap.Timestamp = GetTimestamp();
            recording.push_back(snap);
        } else if (mode == Mode::Playing) {
            if (playbackIndex < recording.size()) {
                const auto& snap = recording[playbackIndex++];
                state.CurrentKeys = snap.KeyStates;
                state.AxisValues = snap.AxisStates;
                state.MouseX = snap.MouseX;
                state.MouseY = snap.MouseY;
            } else {
                StopPlayback();
            }
        }
    }

    bool IsRecording() const { return mode == Mode::Recording; }
    bool IsPlaying() const { return mode == Mode::Playing; }

    // 保存到文件（简化文本格式）
    bool SaveToFile(const std::string& filename) const {
        std::ofstream file(filename);
        if (!file.is_open()) return false;

        file << "INPUT_RECORDING v1\n";
        file << recording.size() << "\n";
        for (const auto& snap : recording) {
            file << snap.FrameNumber << " " << snap.Timestamp << "\n";
            file << snap.KeyStates.size() << "\n";
            for (const auto& [key, pressed] : snap.KeyStates) {
                if (pressed) file << static_cast<int>(key) << " ";
            }
            file << "\n";
        }
        return true;
    }

    size_t GetFrameCount() const { return recording.size(); }

private:
    Mode mode = Mode::Idle;
    std::vector<InputSnapshot> recording;
    size_t playbackIndex = 0;
    uint32_t frameCounter = 0;

    static uint64_t GetTimestamp() {
        auto now = std::chrono::steady_clock::now().time_since_epoch();
        return std::chrono::duration_cast<std::chrono::microseconds>(now).count();
    }
};

// ============================================================
// 6. 输入管理器 (Input Manager)
// ============================================================

class InputManager {
public:
    InputState State;
    ActionMappingSystem Actions;
    InputRecorder Recorder;

    // 事件队列（缓冲）
    std::queue<InputEvent> EventQueue;

    // 初始化默认映射
    void SetupDefaultMappings() {
        // 移动（轴映射：W/S 控制前后，A/D 控制左右）
        Actions.RegisterAction("MoveForward", true);
        Actions.BindKey("MoveForward", KeyCode::W, 1.0f);
        Actions.BindKey("MoveForward", KeyCode::S, -1.0f);
        Actions.BindKey("MoveForward", KeyCode::Gamepad_LeftStickY, 1.0f);

        Actions.RegisterAction("MoveRight", true);
        Actions.BindKey("MoveRight", KeyCode::D, 1.0f);
        Actions.BindKey("MoveRight", KeyCode::A, -1.0f);
        Actions.BindKey("MoveRight", KeyCode::Gamepad_LeftStickX, 1.0f);

        // 视角（鼠标/右摇杆）
        Actions.RegisterAction("LookUp", true);
        Actions.BindKey("LookUp", KeyCode::Gamepad_RightStickY, 1.0f);

        Actions.RegisterAction("LookRight", true);
        Actions.BindKey("LookRight", KeyCode::Gamepad_RightStickX, 1.0f);

        // 动作按钮
        Actions.RegisterAction("Jump");
        Actions.BindKey("Jump", KeyCode::Space);
        Actions.BindKey("Jump", KeyCode::Gamepad_A);

        Actions.RegisterAction("Fire");
        Actions.BindKey("Fire", KeyCode::MouseLeft);
        Actions.BindKey("Fire", KeyCode::Gamepad_RightTrigger);

        Actions.RegisterAction("Sprint");
        Actions.BindKey("Sprint", KeyCode::LeftShift);
        Actions.BindKey("Sprint", KeyCode::Gamepad_LeftStickY, 1.0f);

        Actions.RegisterAction("Pause");
        Actions.BindKey("Pause", KeyCode::Escape);
        Actions.BindKey("Pause", KeyCode::Gamepad_Start);

        // 录制控制
        Actions.RegisterAction("RecordToggle");
        Actions.BindKey("RecordToggle", KeyCode::F10);

        Actions.RegisterAction("PlaybackToggle");
        Actions.BindKey("PlaybackToggle", KeyCode::F11);
    }

    // 处理原始输入事件（由平台后端调用）
    void ProcessRawInput(const InputEvent& event) {
        // 发布到事件总线
        EventBus::Instance().InputEvents.Publish(event);

        // 更新内部状态
        switch (event.Type) {
            case InputEventType::Pressed:
            case InputEventType::Held:
                State.CurrentKeys[event.Key] = true;
                break;
            case InputEventType::Released:
                State.CurrentKeys[event.Key] = false;
                break;
            case InputEventType::AxisChanged:
                State.AxisValues[event.Key] = event.Value;
                break;
            case InputEventType::Moved:
                State.MouseDeltaX += event.Value;  // 这里 Value 复用为 delta
                State.MouseDeltaY += event.PosY;
                State.MouseX = event.PosX;
                State.MouseY = event.PosY;
                break;
        }

        // 入队缓冲
        EventQueue.push(event);
    }

    // 模拟按键（用于测试和回放）
    void SimulateKeyPress(KeyCode key) {
        InputEvent evt;
        evt.Device = DeviceType::Keyboard;
        evt.Type = InputEventType::Pressed;
        evt.Key = key;
        evt.Timestamp = GetTimestamp();
        ProcessRawInput(evt);
    }

    void SimulateKeyRelease(KeyCode key) {
        InputEvent evt;
        evt.Device = DeviceType::Keyboard;
        evt.Type = InputEventType::Released;
        evt.Key = key;
        evt.Timestamp = GetTimestamp();
        ProcessRawInput(evt);
    }

    void SimulateAxis(KeyCode axis, float value) {
        InputEvent evt;
        evt.Device = DeviceType::Gamepad;
        evt.Type = InputEventType::AxisChanged;
        evt.Key = axis;
        evt.Value = value;
        evt.Timestamp = GetTimestamp();
        ProcessRawInput(evt);
    }

    // 每帧更新（在游戏循环开始时调用）
    void Update() {
        // 更新上一帧状态
        State.UpdatePrevious();

        // 处理事件队列
        while (!EventQueue.empty()) {
            auto event = EventQueue.front();
            EventQueue.pop();

            // 消费检测：如果事件已被处理则跳过
            if (event.Consumed) continue;

            // 特殊处理：录制控制
            if (event.Type == InputEventType::Pressed) {
                if (event.Key == KeyCode::F10) {
                    if (Recorder.IsRecording()) {
                        Recorder.StopRecording();
                    } else {
                        Recorder.StartRecording();
                    }
                    event.Consumed = true;
                }
                if (event.Key == KeyCode::F11) {
                    if (Recorder.IsPlaying()) {
                        Recorder.StopPlayback();
                    } else {
                        Recorder.StartPlayback();
                    }
                    event.Consumed = true;
                }
            }
        }

        // 评估动作映射
        auto actionEvents = Actions.EvaluateActions(State);
        for (const auto& action : actionEvents) {
            EventBus::Instance().ActionEvents.Publish(action);
        }

        // 更新录制器
        Recorder.Update(State);
    }

    // 轮询接口
    bool IsPressed(KeyCode key) const { return State.IsPressed(key); }
    bool IsJustPressed(KeyCode key) const { return State.IsJustPressed(key); }
    bool IsJustReleased(KeyCode key) const { return State.IsJustReleased(key); }
    float GetAxis(KeyCode key) const { return State.GetAxis(key); }

private:
    static uint64_t GetTimestamp() {
        auto now = std::chrono::steady_clock::now().time_since_epoch();
        return std::chrono::duration_cast<std::chrono::microseconds>(now).count();
    }
};

// ============================================================
// 7. 命令模式实现
// ============================================================

// 游戏实体（简化）
struct GameEntity {
    std::string Name;
    float X = 0.0f, Y = 0.0f, Z = 0.0f;
    float RotationY = 0.0f;
    bool IsJumping = false;

    void PrintState() const {
        std::cout << "[" << Name << "] pos=("
                  << std::fixed << std::setprecision(2)
                  << X << ", " << Y << ", " << Z << ")"
                  << " rotY=" << RotationY
                  << (IsJumping ? " [JUMPING]" : "")
                  << std::endl;
    }
};

// 命令基类
class ICommand {
public:
    virtual ~ICommand() = default;
    virtual void Execute() = 0;
    virtual void Undo() = 0;
    virtual std::string GetName() const = 0;
};

// 移动命令
class MoveCommand : public ICommand {
    GameEntity* entity;
    float dx, dy, dz;
    float prevX, prevY, prevZ;
public:
    MoveCommand(GameEntity* e, float dx_, float dy_, float dz_)
        : entity(e), dx(dx_), dy(dy_), dz(dz_) {}

    void Execute() override {
        prevX = entity->X; prevY = entity->Y; prevZ = entity->Z;
        entity->X += dx;
        entity->Y += dy;
        entity->Z += dz;
    }

    void Undo() override {
        entity->X = prevX;
        entity->Y = prevY;
        entity->Z = prevZ;
    }

    std::string GetName() const override {
        return "Move(" + std::to_string(dx) + ", " + std::to_string(dy) + ", " + std::to_string(dz) + ")";
    }
};

// 旋转命令
class RotateCommand : public ICommand {
    GameEntity* entity;
    float deltaAngle;
    float prevAngle;
public:
    RotateCommand(GameEntity* e, float angle) : entity(e), deltaAngle(angle) {}

    void Execute() override {
        prevAngle = entity->RotationY;
        entity->RotationY += deltaAngle;
    }

    void Undo() override {
        entity->RotationY = prevAngle;
    }

    std::string GetName() const override {
        return "Rotate(" + std::to_string(deltaAngle) + ")";
    }
};

// 跳跃命令
class JumpCommand : public ICommand {
    GameEntity* entity;
    bool wasJumping;
public:
    explicit JumpCommand(GameEntity* e) : entity(e) {}

    void Execute() override {
        wasJumping = entity->IsJumping;
        if (!entity->IsJumping) {
            entity->IsJumping = true;
            entity->Y += 1.0f;  // 简化：直接上升
        }
    }

    void Undo() override {
        entity->IsJumping = wasJumping;
        entity->Y -= 1.0f;
    }

    std::string GetName() const override { return "Jump"; }
};

// 命令历史（用于 Undo/Redo）
class CommandHistory {
public:
    void Execute(std::shared_ptr<ICommand> cmd) {
        cmd->Execute();
        history.push_back(cmd);
        // 清除 redo 栈
        redoStack.clear();
    }

    void Undo() {
        if (history.empty()) return;
        auto cmd = history.back();
        history.pop_back();
        cmd->Undo();
        redoStack.push_back(cmd);
    }

    void Redo() {
        if (redoStack.empty()) return;
        auto cmd = redoStack.back();
        redoStack.pop_back();
        cmd->Execute();
        history.push_back(cmd);
    }

    void Clear() {
        history.clear();
        redoStack.clear();
    }

    size_t Size() const { return history.size(); }

private:
    std::vector<std::shared_ptr<ICommand>> history;
    std::vector<std::shared_ptr<ICommand>> redoStack;
};

// ============================================================
// 8. 玩家控制器（连接输入与命令）
// ============================================================

class PlayerController {
public:
    GameEntity* Player = nullptr;
    InputManager* Input = nullptr;
    CommandHistory History;

    float MoveSpeed = 5.0f;
    float RotationSpeed = 90.0f;  // 度/秒
    float SprintMultiplier = 2.0f;

    void Update(float deltaTime) {
        if (!Player || !Input) return;

        float speed = MoveSpeed;
        if (Input->IsPressed(KeyCode::LeftShift)) {
            speed *= SprintMultiplier;
        }

        // 移动
        float forward = 0.0f, right = 0.0f;

        // 轮询方式读取轴值
        if (Input->IsPressed(KeyCode::W)) forward += 1.0f;
        if (Input->IsPressed(KeyCode::S)) forward -= 1.0f;
        if (Input->IsPressed(KeyCode::D)) right += 1.0f;
        if (Input->IsPressed(KeyCode::A)) right -= 1.0f;

        // 也读取映射的动作值（演示两种方式）
        // 实际项目中应统一使用一种方式

        float dx = right * speed * deltaTime;
        float dz = forward * speed * deltaTime;

        if (std::abs(dx) > 0.001f || std::abs(dz) > 0.001f) {
            auto cmd = std::make_shared<MoveCommand>(Player, dx, 0.0f, dz);
            History.Execute(cmd);
        }

        // 跳跃（使用 JustPressed 确保只触发一次）
        if (Input->IsJustPressed(KeyCode::Space)) {
            auto cmd = std::make_shared<JumpCommand>(Player);
            History.Execute(cmd);
        }
    }

    // 事件驱动方式处理动作
    void BindToActionEvents() {
        EventBus::Instance().ActionEvents.Subscribe(
            [this](const ActionEvent& evt) {
                if (!Player) return;

                if (evt.ActionName == "Jump" && evt.Type == InputEventType::Pressed) {
                    auto cmd = std::make_shared<JumpCommand>(Player);
                    History.Execute(cmd);
                }
            }
        );
    }
};
```

```cpp
// ============================================================
// input_demo.cpp — 演示程序
// ============================================================
// 编译: g++ -std=c++17 input_demo.cpp -o input_demo
// 运行: ./input_demo
// ============================================================

#include "input_system.hpp"
#include <thread>

// 模拟几帧游戏循环
void SimulateGameFrames(InputManager& input, int frameCount) {
    GameEntity player{"Hero"};
    PlayerController controller;
    controller.Player = &player;
    controller.Input = &input;

    std::cout << "\n=== 模拟游戏帧 ===" << std::endl;

    for (int frame = 0; frame < frameCount; ++frame) {
        std::cout << "\n--- Frame " << frame << " ---" << std::endl;

        // 模拟输入（实际游戏中由平台后端提供）
        if (frame == 1) input.SimulateKeyPress(KeyCode::W);
        if (frame == 2) input.SimulateKeyPress(KeyCode::LeftShift);  // 开始冲刺
        if (frame == 3) { /* 持续按住 W + Shift */ }
        if (frame == 4) input.SimulateKeyPress(KeyCode::Space);      // 跳跃
        if (frame == 5) input.SimulateKeyRelease(KeyCode::Space);
        if (frame == 6) input.SimulateKeyRelease(KeyCode::LeftShift);
        if (frame == 7) {
            input.SimulateKeyRelease(KeyCode::W);
            input.SimulateKeyPress(KeyCode::A);  // 向左转
        }
        if (frame == 8) input.SimulateKeyRelease(KeyCode::A);

        // 模拟手柄摇杆输入
        if (frame >= 2 && frame <= 5) {
            input.SimulateAxis(KeyCode::Gamepad_LeftStickY, 0.8f);
        }
        if (frame == 6) {
            input.SimulateAxis(KeyCode::Gamepad_LeftStickY, 0.0f);
        }

        // 输入管理器更新
        input.Update();

        // 游戏逻辑更新
        controller.Update(1.0f / 60.0f);  // 假设 60fps

        // 打印状态
        player.PrintState();

        // 打印当前帧的动作事件
        std::cout << "  Actions: ";
        bool hasAction = false;
        // 这里简化处理，实际通过事件回调收集
        if (input.IsJustPressed(KeyCode::Space)) {
            std::cout << "Jump triggered ";
            hasAction = true;
        }
        if (input.IsPressed(KeyCode::W)) {
            std::cout << "MoveForward ";
            hasAction = true;
        }
        if (!hasAction) std::cout << "(none)";
        std::cout << std::endl;
    }
}

// 演示输入回放
void DemoInputPlayback(InputManager& input) {
    std::cout << "\n\n=== 输入回放演示 ===" << std::endl;

    // 录制一段输入
    input.Recorder.StartRecording();

    // 模拟一些输入
    input.SimulateKeyPress(KeyCode::W);
    input.Update();
    input.SimulateKeyPress(KeyCode::Space);
    input.Update();
    input.SimulateAxis(KeyCode::Gamepad_LeftStickX, 0.5f);
    input.Update();
    input.SimulateKeyRelease(KeyCode::Space);
    input.Update();
    input.SimulateKeyRelease(KeyCode::W);
    input.SimulateAxis(KeyCode::Gamepad_LeftStickX, 0.0f);
    input.Update();

    input.Recorder.StopRecording();

    // 清空当前状态
    input.State.CurrentKeys.clear();
    input.State.AxisValues.clear();

    // 回放
    std::cout << "\n--- 开始回放 ---" << std::endl;
    input.Recorder.StartPlayback();

    for (int i = 0; i < 10; ++i) {
        input.Update();
        std::cout << "Frame " << i << ": ";
        if (input.IsPressed(KeyCode::W)) std::cout << "W ";
        if (input.IsPressed(KeyCode::Space)) std::cout << "Space ";
        float axis = input.GetAxis(KeyCode::Gamepad_LeftStickX);
        if (std::abs(axis) > 0.01f) std::cout << "Axis=" << axis << " ";
        std::cout << std::endl;

        if (!input.Recorder.IsPlaying()) break;
    }
}

// 演示命令模式
void DemoCommandPattern() {
    std::cout << "\n\n=== 命令模式演示 ===" << std::endl;

    GameEntity player{"CommandDemo"};
    CommandHistory history;

    std::cout << "Initial: ";
    player.PrintState();

    // 执行一系列命令
    history.Execute(std::make_shared<MoveCommand>(&player, 1.0f, 0.0f, 0.0f));
    std::cout << "After Move(1,0,0): "; player.PrintState();

    history.Execute(std::make_shared<MoveCommand>(&player, 0.0f, 0.0f, 2.0f));
    std::cout << "After Move(0,0,2): "; player.PrintState();

    history.Execute(std::make_shared<JumpCommand>(&player));
    std::cout << "After Jump: "; player.PrintState();

    history.Execute(std::make_shared<RotateCommand>(&player, 45.0f));
    std::cout << "After Rotate(45): "; player.PrintState();

    // Undo
    std::cout << "\n--- Undo ---" << std::endl;
    history.Undo();
    std::cout << "After Undo: "; player.PrintState();

    history.Undo();
    std::cout << "After Undo: "; player.PrintState();

    // Redo
    std::cout << "\n--- Redo ---" << std::endl;
    history.Redo();
    std::cout << "After Redo: "; player.PrintState();
}

// 演示事件订阅
void DemoEventSystem() {
    std::cout << "\n\n=== 事件系统演示 ===" << std::endl;

    // 订阅输入事件
    int inputSub = EventBus::Instance().InputEvents.Subscribe(
        [](const InputEvent& evt) {
            std::cout << "[Listener A] " << evt.ToString() << std::endl;
        }
    );

    // 另一个订阅者
    EventBus::Instance().InputEvents.Subscribe(
        [](const InputEvent& evt) {
            if (evt.Type == InputEventType::Pressed) {
                std::cout << "[Listener B] Button pressed detected!" << std::endl;
            }
        }
    );

    // 订阅动作事件
    EventBus::Instance().ActionEvents.Subscribe(
        [](const ActionEvent& evt) {
            std::cout << "[Action Listener] " << evt.ToString() << std::endl;
        }
    );

    // 创建输入管理器并触发事件
    InputManager input;
    input.SetupDefaultMappings();

    std::cout << "\n--- 模拟按键 W ---" << std::endl;
    input.SimulateKeyPress(KeyCode::W);
    input.Update();

    std::cout << "\n--- 模拟按键 Space ---" << std::endl;
    input.SimulateKeyPress(KeyCode::Space);
    input.Update();

    std::cout << "\n--- 模拟轴输入 ---" << std::endl;
    input.SimulateAxis(KeyCode::Gamepad_LeftStickX, 0.75f);
    input.Update();

    // 取消订阅
    EventBus::Instance().InputEvents.Unsubscribe(inputSub);
    std::cout << "\n--- 取消订阅后再次按键 ---" << std::endl;
    input.SimulateKeyPress(KeyCode::A);
    input.Update();
}

// 演示死区处理
void DemoDeadzone() {
    std::cout << "\n\n=== 死区处理演示 ===" << std::endl;

    auto applyDeadzone = [](float value, float deadzone) -> float {
        if (std::abs(value) < deadzone) return 0.0f;
        float sign = value > 0 ? 1.0f : -1.0f;
        return (value - deadzone * sign) / (1.0f - deadzone);
    };

    float deadzone = 0.15f;
    std::cout << "Deadzone = " << deadzone << std::endl;
    std::cout << "Raw -> Processed" << std::endl;

    float testValues[] = {0.0f, 0.05f, 0.10f, 0.15f, 0.20f, 0.50f, 0.80f, 1.0f};
    for (float v : testValues) {
        float processed = applyDeadzone(v, deadzone);
        std::cout << "  " << v << " -> " << processed << std::endl;
    }

    std::cout << "\nNegative values:" << std::endl;
    for (float v : testValues) {
        float processed = applyDeadzone(-v, deadzone);
        std::cout << "  " << -v << " -> " << processed << std::endl;
    }
}

// 演示消费机制
void DemoConsumption() {
    std::cout << "\n\n=== 输入消费机制演示 ===" << std::endl;

    InputManager input;
    input.SetupDefaultMappings();

    // UI 层订阅者：消费 ESC 键
    EventBus::Instance().InputEvents.Subscribe(
        [](const InputEvent& evt) {
            // 模拟 UI 打开时消费 ESC
            if (evt.Key == KeyCode::Escape && evt.Type == InputEventType::Pressed) {
                const_cast<InputEvent&>(evt).Consumed = true;
                std::cout << "[UI] ESC consumed (closing menu)" << std::endl;
            }
        }
    );

    // 游戏层订阅者
    EventBus::Instance().InputEvents.Subscribe(
        [](const InputEvent& evt) {
            if (evt.Key == KeyCode::Escape && evt.Type == InputEventType::Pressed) {
                if (!evt.Consumed) {
                    std::cout << "[Game] ESC received, pausing game" << std::endl;
                } else {
                    std::cout << "[Game] ESC was consumed, ignoring" << std::endl;
                }
            }
        }
    );

    std::cout << "--- 按下 ESC（UI 打开状态）---" << std::endl;
    input.SimulateKeyPress(KeyCode::Escape);
    input.Update();
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  游戏引擎输入系统演示" << std::endl;
    std::cout << "========================================" << std::endl;

    // 1. 事件系统
    DemoEventSystem();

    // 2. 模拟游戏循环
    {
        InputManager input;
        input.SetupDefaultMappings();
        input.Actions.PrintMappings();
        SimulateGameFrames(input, 10);
    }

    // 3. 输入回放
    {
        InputManager input;
        input.SetupDefaultMappings();
        DemoInputPlayback(input);
    }

    // 4. 命令模式
    DemoCommandPattern();

    // 5. 死区处理
    DemoDeadzone();

    // 6. 消费机制
    DemoConsumption();

    std::cout << "\n========================================" << std::endl;
    std::cout << "  演示结束" << std::endl;
    std::cout << "========================================" << std::endl;

    return 0;
}
```

**运行方式:**

1. 将上述代码保存为两个文件：`input_system.hpp` 和 `input_demo.cpp`
2. 编译：`g++ -std=c++17 input_demo.cpp -o input_demo`
3. 运行：`./input_demo`

**预期输出:**

```
========================================
  游戏引擎输入系统演示
========================================

=== 事件系统演示 ===

--- 模拟按键 W ---
[Listener A] [Input] Pressed W
[Listener B] Button pressed detected!
[Action Listener] [Action] 'MoveForward' value=1.000000

--- 模拟按键 Space ---
[Listener A] [Input] Pressed Space
[Listener B] Button pressed detected!
[Action Listener] [Action] 'Jump' triggered

--- 模拟轴输入 ---
[Listener A] [Input] Axis GP_LStickX value=0.750
[Action Listener] [Action] 'MoveRight' value=0.750

--- 取消订阅后再次按键 ---
[Listener B] Button pressed detected!

=== Action Mappings ===
Action: 'MoveForward' (axis)
  -> W * 1
  -> S * -1
  -> GP_LStickY * 1
Action: 'MoveRight' (axis)
  -> D * 1
  -> A * -1
  -> GP_LStickX * 1
...
======================

=== 模拟游戏帧 ===

--- Frame 0 ---
[Hero] pos=(0.00, 0.00, 0.00) rotY=0.00
  Actions: (none)

--- Frame 1 ---
[Hero] pos=(0.00, 0.00, 0.00) rotY=0.00
  Actions: MoveForward
...

=== 输入回放演示 ===
[Recorder] Started recording
[Recorder] Stopped. Recorded 5 frames
[Recorder] Started playback (5 frames)
Frame 0: W
Frame 1: W Space
Frame 2: W Axis=0.5
Frame 3: W
Frame 4:
[Recorder] Playback stopped

=== 命令模式演示 ===
Initial: [CommandDemo] pos=(0.00, 0.00, 0.00) rotY=0.00
After Move(1,0,0): [CommandDemo] pos=(1.00, 0.00, 0.00) rotY=0.00
After Move(0,0,2): [CommandDemo] pos=(1.00, 0.00, 2.00) rotY=0.00
After Jump: [CommandDemo] pos=(1.00, 1.00, 2.00) rotY=0.00 [JUMPING]
After Rotate(45): [CommandDemo] pos=(1.00, 1.00, 2.00) rotY=45.00 [JUMPING]

--- Undo ---
After Undo: [CommandDemo] pos=(1.00, 1.00, 2.00) rotY=0.00 [JUMPING]
After Undo: [CommandDemo] pos=(1.00, 0.00, 2.00) rotY=0.00

--- Redo ---
After Redo: [CommandDemo] pos=(1.00, 1.00, 2.00) rotY=0.00 [JUMPING]

=== 死区处理演示 ===
Deadzone = 0.15
Raw -> Processed
  0 -> 0
  0.05 -> 0
  0.1 -> 0
  0.15 -> 0
  0.2 -> 0.058824
  0.5 -> 0.411765
  0.8 -> 0.764706
  1 -> 1

=== 输入消费机制演示 ===
--- 按下 ESC（UI 打开状态）---
[UI] ESC consumed (closing menu)
[Game] ESC was consumed, ignoring
```

---

## 3. 练习

### 练习 1：实现触屏手势识别

在现有输入系统基础上，添加触屏支持并实现以下手势识别：

1. **单指点击(Tap)**：快速按下并释放
2. **长按(Long Press)**：按住超过 500ms
3. **滑动(Swipe)**：快速单向移动超过阈值距离
4. **捏合(Pinch)**：双指距离变化（用于缩放）

要求：
- 定义 `TouchEvent` 结构，包含手指 ID、位置、时间戳
- 实现 `GestureRecognizer` 类，维护触摸状态机
- 当识别到手势时，发布对应的逻辑事件（如 `GestureEvent`）

提示：手势识别的核心是维护每个触摸点的历史轨迹，根据时间、距离和速度判断手势类型。

### 练习 2：实现输入缓冲系统

为格斗游戏实现一个输入缓冲系统：

1. 创建一个 `InputBuffer` 类，维护最近 N 帧（如 10 帧）的输入历史
2. 实现连招检测：定义连招序列（如 "下+右+攻击 = 升龙拳"），在缓冲历史中匹配
3. 支持输入优先级：当多个连招同时匹配时，选择最长的或最新的
4. 添加可视化调试输出，显示当前缓冲内容

要求：
- 缓冲使用环形缓冲区实现，避免频繁分配内存
- 连招定义使用配置文件或数据结构，便于扩展
- 考虑方向输入的容差（如 "下" 允许摇杆 225-315 度范围）

### 练习 3（可选）：跨平台 Raw Input 后端

实现一个基于操作系统 API 的原始输入后端：

**Windows 版本**：
- 使用 `RegisterRawInputDevices` 注册原始输入设备
- 在窗口消息循环中处理 `WM_INPUT` 消息
- 解析 `RAWINPUT` 结构获取鼠标和键盘数据

**Linux 版本**：
- 使用 `evdev` 接口读取 `/dev/input/event*` 设备
- 解析 `input_event` 结构

**macOS 版本**：
- 使用 `IOHIDManager` 框架

要求：
- 抽象出 `IInputBackend` 接口
- 实现 `WindowsRawInputBackend`、`LinuxEvdevBackend` 等具体类
- 在 `InputManager` 中通过工厂模式加载对应平台的后端
- 对比原始输入与标准窗口消息输入的延迟差异

---

## 4. 扩展阅读

### 书籍

1. **《Game Engine Architecture》第3版 - Jason Gregory**
   - 第8章 "Human Interface Devices (HID)"：深入讲解输入设备硬件原理和引擎集成
   - 涵盖 Raw Input、DirectInput、XInput 等 API 的对比

2. **《Game Programming Patterns》 - Robert Nygard**
   - "Command Pattern" 章节：命令模式在游戏中的经典应用
   - "Observer Pattern" 章节：事件系统的设计

3. **《Real-Time Rendering》第4版 - Tomas Akenine-Moller 等**
   - 虽然主要讲渲染，但第25章涉及 VR 输入（头显追踪、手柄空间定位）

### 文章与文档

1. **SDL Input Documentation**: https://wiki.libsdl.org/CategoryInput
   - 跨平台输入抽象的工业标准参考实现
   - 了解 `SDL_Event`、`SDL_GameController`、手势 API

2. **Microsoft XInput Documentation**: https://docs.microsoft.com/en-us/windows/win32/xinput/xinput-game-controller-apis-portal
   - Xbox 手柄编程的官方文档
   - 包含震动反馈、电池状态、耳机支持等高级功能

3. **"Fix Your Timestep!" by Glenn Fiedler**: https://gafferongames.com/post/fix_your_timestep/
   - 讲解固定时间步长更新与输入处理的关系
   - 理解为什么输入应该在固定更新中处理而非渲染帧

4. **"Input Lag and Code Optimization"**: 搜索 "input lag game development"
   - 了解输入延迟的测量方法和优化策略
   - 原始输入 vs 标准输入的性能对比

### 开源参考

1. **Godot Engine Input System**: https://github.com/godotengine/godot/tree/master/core/input
   - `InputEvent` 类层次结构
   - `InputMap` 资源系统
   - 动作强度(Action Strength)和死区处理

2. **Unreal Engine Input**: https://docs.unrealengine.com/5.0/en-US/input-in-unreal-engine/
   - Enhanced Input 插件（UE5 新系统）
   - Input Mapping Context、Triggers、Modifiers

3. **GLFW Input**: https://www.glfw.org/docs/latest/input_guide.html
   - 轻量级跨平台输入库
   - 了解回调 vs 轮询的 API 设计

### 进阶主题

1. **VR/AR 输入**：手柄 6DOF 追踪、手势识别（Leap Motion、Quest Hand Tracking）、眼动追踪
2. **云游戏输入**：网络延迟补偿、预测输入、服务器端输入验证
3. **无障碍输入**：语音控制、单开关输入、自适应手柄（如 Xbox Adaptive Controller）
4. **AI 输入注入**：自动化测试、机器人玩家、输入序列的机器学习生成

---

## 常见陷阱

### 陷阱 1：丢失快速按键

**问题**：在轮询模式下，如果玩家在两帧之间快速按下并释放按键，引擎可能检测不到。

**解决方案**：
- 使用事件驱动的输入收集，将所有事件存入队列
- 或者使用操作系统提供的按键状态查询（如 Windows 的 `GetAsyncKeyState` 可以检测 "本帧是否按下过"）
- 对于关键动作（如射击），优先使用事件驱动

```cpp
// ❌ 可能丢失输入
if (IsKeyPressed(KEY_SPACE)) Jump();

// ✅ 使用事件队列确保不丢失
while (!eventQueue.empty()) {
    if (event.key == KEY_SPACE && event.type == Pressed) {
        Jump();
    }
}
```

### 陷阱 2：输入与帧率绑定

**问题**：移动速度基于每帧更新，导致不同帧率下移动速度不一致。

```cpp
// ❌ 帧率相关
player.x += speed;  // 30fps 时慢，120fps 时快

// ✅ 帧率无关
player.x += speed * deltaTime;  // deltaTime = 1/60, 1/30, 1/144...
```

**注意**：使用固定时间步长更新物理和输入响应，避免 deltaTime 波动导致的抖动。

### 陷阱 3：摇杆死区处理不当

**问题**：不做死区处理时摇杆漂移；做死区但未重新映射时，小幅度推动没有响应。

```cpp
// ❌ 简单截断——小推动无响应
if (abs(value) < deadzone) value = 0;
// 当 value = 0.16, deadzone = 0.15 时，输出 0.16（跳跃感）

// ✅ 重新映射——平滑过渡
if (abs(value) < deadzone) value = 0;
else value = (value - deadzone * sign(value)) / (1 - deadzone);
// 当 value = 0.16, deadzone = 0.15 时，输出 0.012（平滑）
```

### 陷阱 4：多手柄玩家分配混乱

**问题**：本地多人游戏中，玩家1的手柄断开后再连接，可能被识别为玩家2。

**解决方案**：
- 使用手柄的持久化 ID（如 GUID）而非连接索引识别手柄
- 在手柄断开时保持玩家槽位，显示 "请重新连接手柄" 提示
- 提供手动分配界面让玩家选择手柄

### 陷阱 5：输入在暂停时继续处理

**问题**：游戏暂停时，输入事件仍然传递给游戏世界，导致意外行为。

**解决方案**：
- 实现输入上下文(Input Context)或输入模式
- 暂停时切换到 "Menu" 上下文，只响应菜单导航输入
- 使用栈结构管理上下文：Gameplay -> PauseMenu -> Settings

```cpp
enum class InputContext {
    Gameplay,
    UI,
    PauseMenu,
    Console
};

// 只有栈顶上下文接收输入
InputContextStack.Push(InputContext.PauseMenu);
// 此时只有 PauseMenu 的映射生效
```

### 陷阱 6：文本输入与游戏输入冲突

**问题**：玩家在聊天框输入 "WASD" 时，角色同时移动。

**解决方案**：
- 当 UI 文本框获得焦点时，将输入上下文切换到 "TextInput"
- 文本输入模式下，字符事件发送给文本框，不触发游戏动作
- 保留 ESC、Enter 等功能键用于关闭文本框或发送消息

### 陷阱 7：命令历史内存泄漏

**问题**：长时间游戏后，命令历史无限增长，占用大量内存。

**解决方案**：
- 设置历史上限（如最多保存 1000 条命令）
- 或者定期保存检查点，丢弃旧历史
- 对于不需要 Undo 的操作（如其他玩家的移动），不创建命令

### 陷阱 8：跨平台键码不一致

**问题**：Windows 的虚拟键码与 macOS 的键码不同，直接传递导致映射错误。

**解决方案**：
- 定义引擎内部的 `KeyCode` 枚举（如示例代码所示）
- 平台后端负责将原生键码转换为引擎键码
- 配置文件使用引擎键码名称（如 "Space"、"LeftShift"），而非平台相关数值
