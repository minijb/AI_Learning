---
title: 输入系统
updated: 2026-06-22
tags: [game-architecture, input-system, unity-input-system, action-mapping, device-abstraction]
---

> 所属计划: 游戏架构设计
> 预计耗时: 75min
> 前置知识: [[13-game-state-management|13 游戏状态管理]]

---

## 1. 概念讲解

### 为什么需要这个？

游戏输入是玩家与虚拟世界之间的唯一桥梁，但这座桥梁的建造远比"检测按键"复杂。一个现代游戏可能同时面对：键盘鼠标的精确点击、手柄摇杆的模拟输入、触屏的多点手势、甚至 VR 控制器的 6DOF 追踪。如果游戏逻辑直接耦合到 `KeyCode.W` 或 `Input.GetAxis("Horizontal")`，每新增一种设备就要重写玩法代码——这在跨平台发行时代是不可接受的。

更隐蔽的问题是**语义混乱**。`GetKeyDown(KeyCode.Space)` 在代码里是一个物理按键检测，但设计者想表达的是"跳跃"。当 Space 被改绑到手柄 A 键时，直接引用 `KeyCode.Space` 的代码全部失效。输入系统的核心使命就是建立**设备无关的语义层**：底层消化硬件差异，上层暴露"玩家意图"。

类比：想象一家国际餐厅的后厨。顾客用不同语言点餐（英语、日语、手语），但厨师只认"订单编号 7 号套餐"。输入系统就是那位多语言服务员——把各种"我要吃那个"翻译成统一的厨房指令，还能在旺季动态分配服务员到不同餐桌（多设备/分屏）。

---

### 核心思想

#### 1. 输入抽象层：从 Scan Code 到 Action

输入系统采用经典的分层架构，与 [[02-architecture-styles|第2章 架构风格]] 中讨论的分层模式一致：

| 层级 | 职责 | 示例 |
| --- | --- | --- |
| 物理层 | 读取原始设备状态 | USB HID 报告、XInput 摇杆值、触控坐标 |
| 设备层 | 标准化设备表示 | `Gamepad`、`Keyboard`、`Mouse`、`Touchscreen` |
| 动作层 | 语义化玩家意图 | `Move`、`Jump`、`Fire`、`Pause` |
| 游戏层 | 响应意图执行逻辑 | 应用速度向量、触发跳跃状态机、打开菜单 |

这种分层使 [[10-component-based|第10章 基于组件的架构]] 中的 PlayerController 无需知道"移动"来自键盘 WASD 还是手柄左摇杆。物理层的变更（如新增 Steam Deck 陀螺仪）被隔离在设备层以下。

#### 2. Action Mapping：绑定与上下文的动态组合

Action 不是单一绑定的别名，而是**一组 Binding 的集合**。`Move` 可以同时绑定：
- `<Keyboard>/w,a,s,d`（组合键，用 WASD 或箭头键）
- `<Gamepad>/leftStick`
- `<Mouse>/delta`（用于 FPS 视角旋转）

Binding 之外还有 **Mapping Context（或 Layer）**：战斗时 `Fire` 绑定到鼠标左键，驾驶时同一按键变成 `Horn`。上下文切换在 [[13-game-state-management|第13章 游戏状态管理]] 的状态机中触发，实现输入语义的动态重配置。

Unity Input System 的 Action Map 与 Unreal Enhanced Input 的 Input Mapping Context 是这一思想的工业实现。

#### 3. 轮询 vs 事件：两种消费模型的精确分工

这是输入系统中最易混淆的决策点：

| 模型 | 机制 | 适用场景 | 风险 |
| --- | --- | --- | --- |
| **轮询 (Polling)** | 每帧 `Update()` 读取当前值 | 连续量：移动方向、相机旋转、油门深度 | 离散动作可能丢帧（按键在帧间隙按下释放） |
| **事件 (Event)** | 订阅 `performed`/`canceled`/`started` | 离散量：跳跃、换弹、交互、UI 确认 | 连续量需手动插值，增加复杂度 |

关键洞察：同一 Action 往往**同时需要两种模型**。`Move` 用轮询获取 `Vector2` 方向，但 `Jump` 用事件确保按下瞬间绝不遗漏。Unity Input System 的 `InputAction` 同时提供 `ReadValue<T>()`（轮询）和 `.performed += callback`（事件），正是为此。

#### 4. 运行时重绑定：玩家自定义的完整闭环

静态绑定在发布时确定，但现代游戏必须支持玩家自定义。重绑定的技术挑战在于：
- **交互式捕获**：监听下一个有效输入，过滤误触（如手柄震动触发的瞬时轴值）
- **冲突检测**：避免两个 Action 绑定到同一按键
- **持久化**：将 `overridePath` 序列化到玩家配置文件

Unity 的 `InputActionRebindingExtensions.RebindingOperation` 封装了这一流程，底层通过 `InputSystem.onEvent` 监听设备事件，在超时或有效输入时完成替换。

#### 5. 多设备与玩家分配

本地多人游戏需要**设备到玩家的显式映射**，而非隐式共享。核心问题：
- **分屏**：Player 1 → 手柄 #1，Player 2 → 手柄 #2
- **AI/远程占位**：虚拟 `InputDevice` 或网络数据流注入输入事件
- **热插拔**：手柄拔出时进入"等待重连"状态，而非崩溃

Unity 的 `InputUser` API 设计用于此场景，维护 `pairedDevices` 列表并触发 `onChange` 事件。

#### 6. 死区与缓冲：手感工程的数学

**死区 (Deadzone)**：模拟摇杆的物理中心存在机械公差，静止时轴值在 `±0.1` 范围内漂移。直接判断 `!= 0` 会导致角色缓慢移动或相机微抖。径向死区算法：
- 内死区：`|v| < inner` → 输出 `0`
- 外死区：`|v| > outer` → 归一化到 `0~1`
- 中间区：线性映射

**输入缓冲 (Input Buffer)**：格斗游戏的 3 帧跳跃预输入、动作游戏的攻击连携窗口。缓冲区保存最近 N 帧（或毫秒）的有效输入，在状态机进入可接受状态时消费。这是提升"手感"的核心技术，与 [[07-game-loop|第7章 游戏循环]] 的固定/可变步长紧密相关。

#### 7. 新输入系统的完整特性矩阵

以 Unity Input System 1.7+ 和 Unreal Enhanced Input 为代表：

| 特性 | 说明 |
| --- | --- |
| Action-first | 设计从"玩家做什么"开始，而非"按哪个键" |
| Modifiers | `Negate`（反转）、`Swizzle`（轴交换）、`Scale`（灵敏度）、`Deadzone`（死区） |
| Triggers | `Press`（按下）、`Hold`（按住超时）、`Tap`（快速轻触）、`Chord`（组合键） |
| 上下文切换 | Action Map 的 Enable/Disable 实现动态绑定集 |

---

## 2. 代码示例

以下示例演示完整的 Unity Input System 工作流：Action 定义、事件订阅、输入缓冲、运行时重绑定。代码在 Unity 2022.3 LTS + Input System 1.7+ 下可直接运行。

```csharp
using UnityEngine;
using UnityEngine.InputSystem;
using System;
using System.Collections.Generic;
using UnityEngine.UI;

// ============================================
// 1. 输入缓冲：保存最近 N 帧的离散输入
// ============================================
public class InputBuffer
{
    private readonly Queue<(string actionName, int frameNumber)> _records;
    private readonly int _maxFrames;

    public InputBuffer(int maxFrames = 10)
    {
        _maxFrames = maxFrames;
        _records = new Queue<(string, int)>();
    }

    /// <summary>
    /// 记录一次输入事件，附带当前帧号
    /// </summary>
    public void Record(string actionName, int currentFrame)
    {
        _records.Enqueue((actionName, currentFrame));
        CleanExpired(currentFrame);
    }

    /// <summary>
    /// 尝试消费指定 Action 的缓冲输入
    /// </summary>
    public bool Consume(string actionName, int currentFrame, int withinFrames)
    {
        CleanExpired(currentFrame);
        
        var array = _records.ToArray();
        for (int i = 0; i < array.Length; i++)
        {
            if (array[i].actionName == actionName)
            {
                int age = currentFrame - array[i].frameNumber;
                if (age <= withinFrames)
                {
                    // 移除该记录及之前的所有记录
                    for (int j = 0; j <= i; j++)
                        _records.Dequeue();
                    return true;
                }
            }
        }
        return false;
    }

    private void CleanExpired(int currentFrame)
    {
        while (_records.Count > 0 && currentFrame - _records.Peek().frameNumber > _maxFrames)
        {
            _records.Dequeue();
        }
    }
}

// ============================================
// 2. 玩家控制器：订阅输入事件，使用缓冲
// ============================================
public class PlayerController : MonoBehaviour
{
    [Header("Movement")]
    public float moveSpeed = 5f;
    public float jumpForce = 10f;
    
    [Header("Ground Check")]
    public Transform groundCheck;
    public float groundDistance = 0.4f;
    public LayerMask groundMask;

    private PlayerInputActions _actions;
    private InputBuffer _inputBuffer;
    private Rigidbody _rb;
    private bool _isGrounded;
    private int _frameCounter;

    // 公开属性供 UI 重绑定使用
    public PlayerInputActions Actions => _actions;

    void Awake()
    {
        _rb = GetComponent<Rigidbody>();
        _inputBuffer = new InputBuffer(maxFrames: 10);
        
        // 初始化 Input Action Asset
        _actions = new PlayerInputActions();
        
        // 订阅事件：离散动作用事件，避免丢帧
        _actions.Gameplay.Jump.performed += OnJumpPerformed;
        _actions.Gameplay.Fire.performed += OnFirePerformed;
    }

    void OnEnable()
    {
        _actions.Gameplay.Enable();
    }

    void OnDisable()
    {
        _actions.Gameplay.Disable();
        _actions.Gameplay.Jump.performed -= OnJumpPerformed;
        _actions.Gameplay.Fire.performed -= OnFirePerformed;
    }

    void Update()
    {
        _frameCounter++;
        
        // --- 轮询：连续量每帧读取 ---
        Vector2 moveInput = _actions.Gameplay.Move.ReadValue<Vector2>();
        Vector3 move = new Vector3(moveInput.x, 0, moveInput.y);
        
        // 应用移动（物理在 FixedUpdate，但方向计算在 Update 保证响应性）
        _rb.velocity = new Vector3(move.x * moveSpeed, _rb.velocity.y, move.z * moveSpeed);

        // --- 地面检测 ---
        _isGrounded = Physics.CheckSphere(groundCheck.position, groundDistance, groundMask);
        
        // --- 消费缓冲：落地瞬间检查是否有预输入的跳跃 ---
        if (_isGrounded && _inputBuffer.Consume("Jump", _frameCounter, withinFrames: 3))
        {
            ExecuteJump();
        }
    }

    void OnJumpPerformed(InputAction.CallbackContext context)
    {
        // 如果在地面，立即执行；否则记录到缓冲
        if (_isGrounded)
        {
            ExecuteJump();
        }
        else
        {
            _inputBuffer.Record("Jump", _frameCounter);
        }
    }

    void ExecuteJump()
    {
        _rb.velocity = new Vector3(_rb.velocity.x, jumpForce, _rb.velocity.z);
    }

    void OnFirePerformed(InputAction.CallbackContext context)
    {
        Debug.Log($"Fire! Frame {_frameCounter}");
    }

    void OnDrawGizmosSelected()
    {
        if (groundCheck != null)
        {
            Gizmos.color = Color.yellow;
            Gizmos.DrawWireSphere(groundCheck.position, groundDistance);
        }
    }
}

// ============================================
// 3. 运行时重绑定 UI
// ============================================
public class RebindActionUI : MonoBehaviour
{
    [Header("UI References")]
    public Text actionNameText;
    public Button rebindButton;
    public Text bindingText;

    [Header("Target Action")]
    public InputActionReference actionReference;
    public int bindingIndex = 0; // 0 = 主绑定

    private InputActionRebindingExtensions.RebindingOperation _rebindOperation;

    void Start()
    {
        if (actionReference == null) return;

        actionNameText.text = actionReference.action.name;
        UpdateBindingDisplay();

        rebindButton.onClick.AddListener(StartRebinding);
    }

    void OnDestroy()
    {
        _rebindOperation?.Dispose();
    }

    void StartRebinding()
    {
        if (actionReference == null || actionReference.action == null) return;

        // 禁用当前 Action 避免自触发
        actionReference.action.Disable();

        rebindButton.interactable = false;
        bindingText.text = "Listening...";

        _rebindOperation = actionReference.action.PerformInteractiveRebinding(bindingIndex)
            .WithControlsExcluding("<Mouse>/position")   // 排除鼠标位置
            .WithControlsExcluding("<Mouse>/delta")     // 排除鼠标移动
            .WithCancelingThrough("<Keyboard>/escape")  // ESC 取消
            .OnMatchWaitForAnother(0.1f)                // 等待 100ms 确认无其他输入
            .OnComplete(operation => {
                // 保存到用户配置（实际项目应序列化到文件）
                string overridePath = operation.selectedControl.path;
                PlayerPrefs.SetString($"Rebind_{actionReference.action.name}", overridePath);
                PlayerPrefs.Save();

                operation.Dispose();
                actionReference.action.Enable();
                rebindButton.interactable = true;
                UpdateBindingDisplay();
            })
            .OnCancel(operation => {
                operation.Dispose();
                actionReference.action.Enable();
                rebindButton.interactable = true;
                UpdateBindingDisplay();
            })
            .Start();
    }

    void UpdateBindingDisplay()
    {
        if (actionReference?.action == null) return;

        var binding = actionReference.action.bindings[bindingIndex];
        string display = binding.overridePath ?? binding.path;
        bindingText.text = InputControlPath.ToHumanReadableString(display);
    }

    /// <summary>
    /// 启动时加载保存的重绑定
    /// </summary>
    public void LoadSavedOverrides()
    {
        if (actionReference?.action == null) return;

        string key = $"Rebind_{actionReference.action.name}";
        if (PlayerPrefs.HasKey(key))
        {
            string overridePath = PlayerPrefs.GetString(key);
            actionReference.action.ApplyBindingOverride(bindingIndex, overridePath);
            UpdateBindingDisplay();
        }
    }
}

// ============================================
// 4. 双人设备分配示例（简化版）
// ============================================
public class MultiplayerDeviceAssigner : MonoBehaviour
{
    public List<PlayerInput> playerInputs = new List<PlayerInput>();

    void Start()
    {
        // 监听设备变更
        InputSystem.onDeviceChange += OnDeviceChange;
        
        // 初始分配：Player 1 键盘，Player 2 等待手柄
        AssignInitialDevices();
    }

    void OnDestroy()
    {
        InputSystem.onDeviceChange -= OnDeviceChange;
    }

    void AssignInitialDevices()
    {
        // 简化：实际应使用 InputUser.PerformPairingWithDevice
        var keyboard = Keyboard.current;
        if (keyboard != null && playerInputs.Count > 0)
        {
            // 通过 PlayerInput 组件的 SwitchCurrentControlScheme
            // 或手动设置 User.pairedDevices
            Debug.Log("Player 1 assigned to Keyboard");
        }
    }

    void OnDeviceChange(InputDevice device, InputDeviceChange change)
    {
        switch (change)
        {
            case InputDeviceChange.Added:
                Debug.Log($"Device added: {device.displayName}");
                // 寻找未分配设备的玩家进行配对
                TryAssignDeviceToWaitingPlayer(device);
                break;

            case InputDeviceChange.Removed:
                Debug.Log($"Device removed: {device.displayName}");
                // 标记对应玩家为"等待重连"
                HandleDeviceLost(device);
                break;

            case InputDeviceChange.Disconnected:
                HandleDeviceLost(device);
                break;
        }
    }

    void TryAssignDeviceToWaitingPlayer(InputDevice device)
    {
        if (device is Gamepad)
        {
            // 查找没有 Gamepad 的玩家
            Debug.Log($"Attempting to assign {device.displayName} to waiting player");
        }
    }

    void HandleDeviceLost(InputDevice device)
    {
        // 暂停对应玩家，显示"请重新连接手柄"UI
        Debug.Log($"Player lost device: {device.displayName}");
    }
}
```

**运行方式:**

```bash
# 1. Unity 编辑器：创建新项目，通过 Package Manager 安装 Input System
#    Window → Package Manager → Unity Registry → Input System → Install

# 2. 创建 Input Action Asset：
#    Project 窗口右键 → Create → Input Actions → 命名为 "PlayerInputActions"
#    配置 Action Map "Gameplay"：
#      - Move: Action Type = Value, Control Type = Vector2
#        Bindings: WASD (Composite), Left Stick, Arrow Keys
#      - Jump: Action Type = Button
#        Bindings: Space (Keyboard), South Button (Gamepad)
#      - Fire: Action Type = Button
#        Bindings: Left Click (Mouse), West Button (Gamepad)
#    Generate C# Class：Asset Inspector → "Generate C# Class" → 应用

# 3. 将上述脚本挂载到场景中的 Player GameObject
#    添加 Rigidbody，创建 GroundCheck 空物体作为子对象

# 4. 创建 UI Canvas，添加 RebindActionUI 组件，绑定对应 Action Reference
```

**预期输出:**

```text
[编辑器 Console，正常游戏时]
Fire! Frame 152
Fire! Frame 187
[跳跃预输入成功时]
[无显式日志，但角色在落地瞬间立即起跳，而非按键无效]

[重绑定 UI 交互时]
Listening...
[按下 Gamepad 的 North Button]
绑定显示更新为 "Button North [Gamepad]"

[设备插拔时]
Device added: Xbox Controller
Attempting to assign Xbox Controller to waiting player
Device removed: Xbox Controller
Player lost device: Xbox Controller
```

---

## 3. 练习

### 练习 1: 基础

在示例中加入一个 `Sprint` Action，绑定为 `Left Shift` 按住（键盘）和 `Left Shoulder` 按住（手柄）。在 `Update` 中用**轮询**检测是否按住，并作为移动速度倍率（按住时 1.5x，松开时 1.0x）。

---

### 练习 2: 进阶

实现一个**10 帧的输入缓冲区**，让角色在**离地前 3 帧内**按下跳跃仍可在落地瞬间起跳。修改 `PlayerController` 的缓冲消费逻辑，确保预输入窗口精确可控。

---

### 练习 3: 挑战（可选）

为双人本地游戏设计设备分配策略，并在代码中处理手柄插入/拔出。要求：
- Player 1 默认键盘，Player 2 默认等待手柄
- 手柄拔出时对应玩家进入"暂停等待"状态，而非控制转移到其他玩家
- 新插入手柄优先分配给无设备的玩家

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 核心是在 `PlayerInputActions` 的 `Gameplay` Action Map 中新增 `Sprint` Action，然后在 `Update` 中轮询其按下状态。
> 
> ```csharp
> // 在 PlayerInputActions 的 generated 代码中（或通过 Inspector 配置后重新生成）：
> // Sprint: Action Type = Button, Initial State Check = true
> // Bindings: <Keyboard>/leftShift, <Gamepad>/leftShoulder
> 
> // 在 PlayerController 中：
> [Header("Sprint")]
> public float sprintMultiplier = 1.5f;
> 
> void Update()
> {
>     // ... 原有移动代码 ...
>     
>     // 轮询 Sprint：IsPressed 在按住期间每帧返回 true
>     float currentMultiplier = _actions.Gameplay.Sprint.IsPressed() ? sprintMultiplier : 1.0f;
>     
>     Vector2 moveInput = _actions.Gameplay.Move.ReadValue<Vector2>();
>     Vector3 move = new Vector3(moveInput.x, 0, moveInput.y);
>     
>     // 应用速度倍率
>     _rb.velocity = new Vector3(
>         move.x * moveSpeed * currentMultiplier, 
>         _rb.velocity.y, 
>         move.z * moveSpeed * currentMultiplier
>     );
>     
>     // ... 其余代码 ...
> }
> ```
> 
> 关键细节：`IsPressed()` 是轮询 API，适合持续状态检测；若用事件 `performed` 则只能触发一次，无法持续加速。注意 `leftShift` 在 Input System 的命名规范是 `leftShift`（小写 l），但路径写为 `<Keyboard>/leftShift`。

> [!tip]- 练习 2 参考答案
> 核心修改是扩大 `InputBuffer` 的 `maxFrames` 到 10，并在 `OnJumpPerformed` 中无论是否 grounded 都记录缓冲（原代码已如此），但将消费窗口从 3 改为 10 帧中的任意时刻。
> 
> ```csharp
> public class PlayerController : MonoBehaviour
> {
>     // 修改：缓冲区扩大到 10 帧
>     void Awake()
>     {
>         _inputBuffer = new InputBuffer(maxFrames: 10); // 原为 10，现明确用于 10 帧缓冲
>         // ...
>     }
> 
>     void Update()
>     {
>         _frameCounter++;
>         
>         // ... 移动代码 ...
>         
>         // 修改：扩大消费窗口为 10 帧
>         // 关键：在 grounded 变为 true 的帧，检查最近 10 帧内是否有跳跃输入
>         if (_isGrounded && _inputBuffer.Consume("Jump", _frameCounter, withinFrames: 10))
>         {
>             ExecuteJump();
>         }
>     }
> 
>     void OnJumpPerformed(InputAction.CallbackContext context)
>     {
>         // 统一：所有跳跃输入都先进入缓冲
>         // 如果已在地面，本帧 Update 就会消费（因为 buffered 帧差为 0）
>         // 如果不在地面，保留到落地瞬间
>         _inputBuffer.Record("Jump", _frameCounter);
>     }
> }
> ```
> 
> 关键洞察：缓冲系统的"帧"与物理帧解耦。若使用固定步长物理（`FixedUpdate`），应记录 `Time.fixedTime` 而非帧计数，避免帧率波动导致窗口不稳定。与 [[07-game-loop|第7章 游戏循环]] 的讨论结合，这是可变帧率游戏必须处理的细节。

> [!tip]- 练习 3 参考答案
> 使用 Unity 的 `InputUser` API 实现设备与玩家的显式配对，替代简化版的手动映射。
> 
> ```csharp
> using UnityEngine.InputSystem.Users;
> 
> public class RobustMultiplayerAssigner : MonoBehaviour
> {
>     public int maxPlayers = 2;
>     private List<InputUser> _users = new List<InputUser>();
>     private Dictionary<InputUser, PlayerInput> _userToPlayer = new Dictionary<InputUser, PlayerInput>();
> 
>     void Start()
>     {
>         InputSystem.onDeviceChange += OnDeviceChange;
>         
>         // 创建 Player 1，初始配对键盘
>         var user1 = InputUser.CreateUserWithoutPairedDevices();
>         user1.ActivateControlScheme("KeyboardMouse");
>         if (Keyboard.current != null)
>             InputUser.PerformPairingWithDevice(Keyboard.current, user1);
>         _users.Add(user1);
> 
>         // 创建 Player 2，无初始设备
>         var user2 = InputUser.CreateUserWithoutPairedDevices();
>         user2.ActivateControlScheme("Gamepad");
>         _users.Add(user2);
>     }
> 
>     void OnDeviceChange(InputDevice device, InputDeviceChange change)
>     {
>         if (change == InputDeviceChange.Added)
>         {
>             // 新设备：优先分配给未配对的玩家
>             foreach (var user in _users)
>             {
>                 if (user.pairedDevices.Count == 0 && device is Gamepad)
>                 {
>                     InputUser.PerformPairingWithDevice(device, user);
>                     OnPlayerDeviceAssigned(user, device);
>                     return;
>                 }
>             }
>         }
>         else if (change == InputDeviceChange.Removed || change == InputDeviceChange.Disconnected)
>         {
>             // 查找持有该设备的玩家
>             foreach (var user in _users)
>             {
>                 if (user.pairedDevices.Contains(device))
>                 {
>                     InputUser.RemoveDeviceFromUser(device);
>                     OnPlayerDeviceLost(user, device);
>                 }
>             }
>         }
>     }
> 
>     void OnPlayerDeviceAssigned(InputUser user, InputDevice device)
>     {
>         Debug.Log($"Player {_users.IndexOf(user) + 1} assigned {device.displayName}");
>         // 恢复游戏状态
>     }
> 
>     void OnPlayerDeviceLost(InputUser user, InputDevice device)
>     {
>         Debug.Log($"Player {_users.IndexOf(user) + 1} lost {device.displayName} - PAUSED");
>         // 暂停玩家，显示"请重新连接手柄"UI
>         // 关键：不自动重新分配其他设备，保持玩家身份
>     }
> }
> ```
> 
> 关键设计决策：
> 1. **玩家身份与设备分离**：`InputUser` 是持久身份，设备是临时配对。拔出设备不销毁玩家。
> 2. **控制方案 (Control Scheme)** 预声明：Player 1 的 `KeyboardMouse` 与 Player 2 的 `Gamepad` 避免键盘被手柄玩家抢走。
> 3. **不自动抢占**：新设备只分配给 `pairedDevices.Count == 0` 的玩家，避免已游玩玩家被干扰。

> [!note] 答案使用方式
> 如果你的实现通过了测试或达到了题目要求，就是正确的。参考答案展示的是**一种**可行路径，而非唯一标准。练习 1 的速度倍率可用 `ReadValue<float>()` 替代 `IsPressed()`（Button 的 ReadValue 返回 0/1）；练习 2 的帧计数可替换为 `Time.time` 的毫秒版本；练习 3 若不使用 `InputUser`，手动维护 `Dictionary<int, List<InputDevice>>` 也是有效方案，但需自行处理设备身份验证。
>
> ---

## 4. 扩展阅读

- Unity Input System Actions documentation: https://docs.unity3d.com/Packages/com.unity.inputsystem@1.17/manual/Actions.html
- Unreal Enhanced Input documentation: https://dev.epicgames.com/documentation/unreal-engine/enhanced-input-in-unreal-engine
- Polling vs event driven input discussion: https://gamedev.stackexchange.com/questions/12146/polling-vs-event-driven-input

---

## 常见陷阱

- **混用旧 `Input` API 与新 Input System，导致同一按键触发两次或设备冲突**。正确做法：在 Project Settings → Player → Other Settings 中启用 "Input System Package (New)"，并彻底移除 `Input.GetKey`/`Input.GetAxis` 调用；若需过渡，使用 "Both" 模式但谨慎隔离调用路径。

- **对摇杆值只判断 `!= 0` 而不做死区处理，导致角色漂移或相机微抖**。正确做法：在 Action 的 Binding 或 Processor 中添加 `Deadzone` modifier，或在代码中用 `Mathf.Abs(value) > deadzoneThreshold` 过滤；径向死区对 `Vector2` 需计算 `.magnitude`，而非分量独立判断。

- **在事件回调中直接读取 `Input.mousePosition` 而不是依赖 Action 的 value，破坏设备抽象**。正确做法：所有游戏逻辑只消费 `InputAction` 提供的数据；若需鼠标位置，定义 `Aim` Action 绑定 `<Mouse>/position`，在回调中读取 `context.ReadValue<Vector2>()`，确保该 Action 可重绑到触摸屏或右摇杆。