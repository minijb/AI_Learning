# 状态同步客户端（Unity Netcode / NGO）

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 75min
> 前置知识: [17-延迟补偿](17-lag-compensation.md)

---

## 1. 概念讲解

### 1.1 为什么 Unity Netcode 是面试必问？

如果你面试 Unity 多人游戏岗位，NGO（Netcode for GameObjects）是绕不过的话题。它是 Unity 官方在 2022 年收购 MLAPI 后推出的第一方网络方案，目前已替代旧的 UNET，成为 Unity 6 的官方推荐框架。

对比前面 7-12 节的帧同步（Lockstep），状态同步的客户端实现完全不同：

| 维度 | 帧同步客户端 | 状态同步客户端（NGO） |
|------|-------------|---------------------|
| 逻辑执行 | 客户端执行确定性逻辑 | 服务器执行权威逻辑 |
| 同步内容 | 玩家输入 | 实体状态（位置、血量、动画） |
| 表现分离 | 逻辑层 + 表现层，定点数 | 无逻辑层，浮点数直接表现 |
| 延迟处理 | 帧缓冲 + 追赶 | 预测 + 和解 + 插值 |
| 反外挂 | 依赖哈希校验 | 服务器权威天然防作弊 |

**本篇的目标**：用 NGO 从零构建一个 3D 射击 Demo（移动 + 射击 + 血量同步），覆盖你在面试和实际项目中需要用到的所有核心 API 和设计模式。

### 1.2 核心思想

NGO 的本质就是一句话：

> **服务器拥有所有 NetworkObject 的权威状态。客户端通过 RPC 发送输入，通过 NetworkVariable 接收状态变化，通过预测和插值隐藏网络延迟。**

NGO 为这五个任务提供了开箱即用的组件：

1. **谁有权限修改？** — `NetworkBehaviour.IsOwner` / `IsServer` 控制权限
2. **状态怎么同步？** — `NetworkVariable<T>` 自动从服务器同步到客户端
3. **输入怎么发给服务器？** — `ServerRpc` 从客户端调用服务器方法
4. **服务器怎么通知客户端？** — `ClientRpc` 从服务器广播到所有客户端
5. **玩家怎么看到平滑移动？** — `NetworkTransform` 内置插值与外推

### 1.3 NGO 核心架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        Unity 场景                                │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    NetworkManager                        │    │
│  │  传输层(UTP/UNET) │ 连接管理 │ 对象生成(Spawn) │ RPC路由  │    │
│  └─────────────────────────────────────────────────────────┘    │
│         │                                                        │
│    ┌────┴────┬─────────┬──────────┐                               │
│    ▼         ▼         ▼          ▼                               │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐                        │
│  │Player│ │Enemy │ │Item  │ │Projectile│  ← NetworkObject 们     │
│  │  GO  │ │  GO  │ │  GO  │ │    GO    │                        │
│  └──┬───┘ └──┬───┘ └──┬───┘ └────┬─────┘                        │
│     │        │        │           │                               │
│     ▼        ▼        ▼           ▼                               │
│  ┌─────────────────────────────────────────────┐                 │
│  │            NetworkBehaviour 派生类             │                 │
│  │  ┌─────────────┐ ┌───────────┐ ┌──────────┐ │                 │
│  │  │NetworkVariable│ │ ServerRpc │ │ClientRpc │ │                 │
│  │  │  自动同步状态  │ │  客户端→服│ │  服务器→客│ │                 │
│  │  └─────────────┘ └───────────┘ └──────────┘ │                 │
│  └─────────────────────────────────────────────┘                 │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              可选组件（挂载在 NetworkObject 上）            │    │
│  │  ┌────────────────┐ ┌────────────────┐ ┌──────────────┐ │    │
│  │  │NetworkTransform│ │NetworkAnimator│ │Rigidbody(网)  │ │    │
│  │  │  位置/旋转/缩放  │ │  动画参数同步   │ │  物理同步     │ │    │
│  │  └────────────────┘ └────────────────┘ └──────────────┘ │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

**数据流方向（关键）**：

- **上行（客户端 → 服务器）**：玩家输入 → `ServerRpc` → 服务器处理 → 服务器状态变更
- **下行（服务器 → 客户端）**：服务器状态变更 → `NetworkVariable` 自动同步 → 客户端接收到新值 → 表现层更新
- **权威在服务器**：客户端永远不能直接修改 `NetworkVariable`（除非服务器设置了写权限）。客户端通过 `ServerRpc` _请求_ 修改，服务器决定是否执行。

### 1.4 关键组件职责表

| 组件 | 谁挂？ | 做什么？ | 同步方向 |
|------|--------|---------|---------|
| `NetworkManager` | 场景根节点 | 连接管理、传输层、Prefab 注册 | — |
| `NetworkObject` | 每个网络实体 | 唯一标识（NetworkObjectId）、所有权 | — |
| `NetworkBehaviour` | 脚本基类 | 替代 MonoBehaviour，提供 IsOwner/IsServer/IsClient | — |
| `NetworkVariable<T>` | NetworkBehaviour 字段 | 自动同步字段（值类型 + string） | Server → Clients |
| `NetworkTransform` | NetworkObject 上 | 位置/旋转/缩放同步 + 插值 | Server → Clients |
| `NetworkAnimator` | 带 Animator 的 NetworkObject | 动画参数同步 | Server → Clients |
| `ServerRpc` | NetworkBehaviour 方法 | 客户端调用，服务端执行 | Client → Server |
| `ClientRpc` | NetworkBehaviour 方法 | 服务端调用，所有客户端执行 | Server → Clients |

### 1.5 NGO 的延迟隐藏策略

NGO 不像帧同步那样依赖帧缓冲，而是使用三种策略组合：

```
时间轴 ──────────────────────────────────────────────────────►

客户端:  [输入] ───RTT/2───► [服务器收到输入]
           │                       │
           ▼                       ▼
      [本地立即执行]          [权威处理]
      (客户端预测)            [状态变更]
           │                       │
           │               ┌───────┴───────┐
           │               ▼               ▼
           │         [NetworkVariable] [ClientRpc]
           │         (状态同步回去)    (事件通知)
           │               │               │
           ▼               ▼               ▼
      [预测结果] ←──RTT── [服务器权威状态到达]
           │
           ▼
      [和解: 比较预测与权威]
      [如果不一致 → 回滚到权威状态 + 重放未确认输入]
```

NGO 本身**不提供**完整的客户端预测和和解框架（不像 UE 的 CharacterMovementComponent）。NGO 提供了传输和同步的基础设施——预测和和解需要你自己实现。这正是本篇的重点之一。

---

## 2. 代码示例

> **重要说明**：以下代码构建一个功能完整的 3D 多人射击 Demo。需要 Unity 2022.3+ 和 `com.unity.netcode.gameobjects` 包。所有 `.cs` 文件按依赖顺序列出。

### 2.0 项目初始化

```bash
# 1. 创建 Unity 项目（3D 模板）
# 2. Window → Package Manager → Add package by name:
#    com.unity.netcode.gameobjects
# 3. 等导入完成后继续
```

在场景中创建以下层级结构：

```
Scene
├── NetworkManager (挂 NetworkManager.cs + 我们自定义的 GameNetworkManager.cs)
├── --- UI ---
│   ├── Canvas
│   │   ├── HostButton
│   │   ├── ClientButton
│   │   └── ServerButton
└── --- SpawnPoints ---
    ├── SpawnPoint (0,0,0)
    ├── SpawnPoint (5,0,0)
    ├── SpawnPoint (0,0,5)
    └── SpawnPoint (5,0,5)
```

### 2.1 GameNetworkManager.cs — 网络管理器（~80行）

这是整个 Demo 的入口。负责启动 Host/Server/Client、注册 PlayerPrefab、以及在玩家连接时生成角色。

```csharp
// GameNetworkManager.cs
// 挂载在与 NetworkManager 同一个 GameObject 上。
// 负责：连接模式选择（UI 触发） + 玩家生成逻辑。

using UnityEngine;
using Unity.Netcode;
using UnityEngine.UI;

/// <summary>
/// 自定义网络管理器：处理连接和玩家生成。
/// NetworkManager 由 Unity 内置，我们通过 GetComponent 获取并配置。
/// </summary>
public class GameNetworkManager : MonoBehaviour
{
    [Header("UI 按钮")]
    [SerializeField] private Button _hostButton;
    [SerializeField] private Button _clientButton;
    [SerializeField] private Button _serverButton;

    [Header("玩家 Prefab")]
    [SerializeField] private GameObject _playerPrefab;  // 需要在 NetworkManager 中注册为 NetworkPrefab

    private NetworkManager _netManager;

    private void Awake()
    {
        _netManager = GetComponent<NetworkManager>();

        // 将 PlayerPrefab 注册到 NetworkManager 的可生成列表中
        // 这一步也可以在 NetworkManager 的 Inspector 中手动拖入
        _netManager.NetworkConfig.PlayerPrefab = _playerPrefab;

        // 绑定 UI 按钮事件
        if (_hostButton != null)   _hostButton.onClick.AddListener(StartHost);
        if (_clientButton != null) _clientButton.onClick.AddListener(StartClient);
        if (_serverButton != null) _serverButton.onClick.AddListener(StartServer);
    }

    private void StartHost()
    {
        Debug.Log("[GameNetworkManager] 启动 Host 模式（既是服务器又是客户端）");
        _netManager.StartHost();
        // StartHost() 同时启动 Server 和 Client 实例。
        // 回调顺序: OnServerStarted → OnClientConnected → OnClientConnectedCallback(本地)
    }

    private void StartClient()
    {
        Debug.Log("[GameNetworkManager] 启动 Client 模式，连接 127.0.0.1:7777");
        // 连接localhost——局域网中改为服务器IP
        _netManager.GetComponent<Unity.Netcode.Transports.UTP.UnityTransport>()
            .ConnectionData.Address = "127.0.0.1";
        _netManager.StartClient();
    }

    private void StartServer()
    {
        Debug.Log("[GameNetworkManager] 启动纯 Server 模式（无本地客户端）");
        // 纯服务器模式：没有本地玩家，只做权威处理
        _netManager.StartServer();
    }

    // ── 玩家生成 ──────────────────────────────────────────
    // 当客户端连接成功后，服务器需要为该客户端生成对应的 Player 对象。
    // 订阅 NetworkManager.OnClientConnectedCallback 即可。

    private void OnEnable()
    {
        // 服务器端监听客户端连接事件
        if (_netManager != null)
            _netManager.OnClientConnectedCallback += OnClientConnected;
    }

    private void OnDisable()
    {
        if (_netManager != null)
            _netManager.OnClientConnectedCallback -= OnClientConnected;
    }

    /// <summary>
    /// 服务器端回调：当有客户端连接时触发。
    /// 为连接者生成 Player 对象。
    /// </summary>
    private void OnClientConnected(ulong clientId)
    {
        Debug.Log($"[GameNetworkManager] Client {clientId} 已连接");

        // 选择出生点（轮询可用位置）
        Vector3 spawnPos = GetSpawnPosition(clientId);

        // 在服务器上生成 Player 对象，并指定 ownership 为 clientId
        // 第三个参数为 true 表示此对象"属于"该客户端——客户端获得 IsOwner = true
        GameObject playerObj = Instantiate(_playerPrefab, spawnPos, Quaternion.identity);
        NetworkObject netObj = playerObj.GetComponent<NetworkObject>();

        // SpawnWithOwnership: 服务器生成此对象，所有权授予指定客户端
        // 生成后，所有客户端都会创建此对象的副本
        netObj.SpawnWithOwnership(clientId);
    }

    private Vector3 GetSpawnPosition(ulong clientId)
    {
        // 简单的固定出生点轮询
        // 生产项目中应使用 SpawnManager 管理动态出生点
        Vector3[] spawns = new Vector3[]
        {
            new Vector3(0f, 1f, 0f),
            new Vector3(5f, 1f, 0f),
            new Vector3(0f, 1f, 5f),
            new Vector3(5f, 1f, 5f),
        };
        return spawns[clientId % (ulong)spawns.Length];
    }
}
```

### 2.2 PlayerController.cs — 移动 + 客户端预测（~120行）

这是教程中最核心的类。它展示了**客户端预测**的手动实现方法——在 NGO 的范围内，这是最"高级"的主题。

```csharp
// PlayerController.cs
// 挂载在 Player Prefab 上。需要 NetworkObject + NetworkTransform + CharacterController。
//
// 设计要点：
// 1. 本地玩家（IsOwner=true）：立即处理输入并移动角色（客户端预测），同时用 ServerRpc 发给服务器
// 2. 远程玩家（IsOwner=false）：只通过 NetworkTransform 的自动同步来更新位置
// 3. 服务器收到输入后权威处理移动，结果通过 NetworkTransform 同步回客户端
// 4. 客户端通过比较预测位置和服务器位置来和解（简化版）

using UnityEngine;
using Unity.Netcode;
using System.Collections.Generic;

[RequireComponent(typeof(CharacterController))]
public class PlayerController : NetworkBehaviour
{
    [Header("移动参数")]
    [SerializeField] private float _moveSpeed = 6f;
    [SerializeField] private float _rotationSpeed = 720f;
    [SerializeField] private float _gravity = -20f;

    // ── 预测系统相关 ──────────────────────────────────────
    // 存储未确认的输入及其时间戳，用于服务器回包时和解
    private struct PendingInput
    {
        public uint Tick;           // 输入序号（自增）
        public Vector3 MoveDir;     // 移动方向
        public Vector3 Position;    // 输入执行后的预测位置
    }
    private Queue<PendingInput> _pendingInputs = new Queue<PendingInput>();
    private uint _inputTick;            // 当前输入序号
    private const int MAX_PENDING = 64; // 最多保留 64 个未确认输入

    // ── 服务器权威位置（通过 NetworkVariable 同步回客户端） ──
    private NetworkVariable<Vector3> _serverPosition = new NetworkVariable<Vector3>(
        Vector3.zero,
        NetworkVariableReadPermission.Everyone,       // 所有客户端可读
        NetworkVariableWritePermission.Server         // 只有服务器可写
    );

    private CharacterController _controller;
    private Vector3 _verticalVelocity; // 重力累积
    private Camera _playerCamera;

    public override void OnNetworkSpawn()
    {
        base.OnNetworkSpawn();

        _controller = GetComponent<CharacterController>();

        // 只有本地玩家才启用输入和摄像机
        if (IsOwner)
        {
            // 查找或创建本地玩家的摄像机
            _playerCamera = Camera.main;
            if (_playerCamera != null)
            {
                // 摄像机跟随设置——实际项目中用 Cinemachine
                _playerCamera.transform.SetParent(transform);
                _playerCamera.transform.localPosition = new Vector3(0, 1.7f, 0);
                _playerCamera.transform.localRotation = Quaternion.identity;
            }

            // 远程玩家的 CharacterController 禁用（避免物理冲突）
            // 由 NetworkTransform 驱动远程玩家位置
        }
        else
        {
            // 远程玩家——禁用 CharacterController，由 NetworkTransform 接管移动
            _controller.enabled = false;
        }

        // 监听服务器权威位置的变化（用于和解）
        _serverPosition.OnValueChanged += OnServerPositionChanged;
    }

    public override void OnNetworkDespawn()
    {
        _serverPosition.OnValueChanged -= OnServerPositionChanged;
        base.OnNetworkDespawn();
    }

    private void Update()
    {
        // 只有本地玩家才处理输入
        if (!IsOwner) return;

        // 1. 收集输入
        Vector3 moveDir = GetInputDirection();

        // 2. 计算预测移动
        Vector3 predictedPos = CalculateMovement(moveDir);

        // 3. 记录预测状态（用于后续和解）
        _inputTick++;
        _pendingInputs.Enqueue(new PendingInput
        {
            Tick = _inputTick,
            MoveDir = moveDir,
            Position = predictedPos
        });
        // 保持队列大小
        while (_pendingInputs.Count > MAX_PENDING)
            _pendingInputs.Dequeue();

        // 4. 通过 ServerRpc 发送输入到服务器
        SendInputServerRpc(_inputTick, moveDir, Time.deltaTime);
    }

    /// <summary>
    /// 收集键盘输入并返回世界空间移动方向。
    /// </summary>
    private Vector3 GetInputDirection()
    {
        float horizontal = Input.GetAxisRaw("Horizontal");
        float vertical = Input.GetAxisRaw("Vertical");

        Vector3 direction = new Vector3(horizontal, 0f, vertical).normalized;

        // 基于摄像机朝向转换方向
        if (_playerCamera != null)
        {
            Vector3 forward = _playerCamera.transform.forward;
            Vector3 right = _playerCamera.transform.right;
            forward.y = 0f;
            right.y = 0f;
            forward.Normalize();
            right.Normalize();
            direction = forward * direction.z + right * direction.x;
        }

        return direction;
    }

    /// <summary>
    /// 根据输入计算预测位置。
    /// 本地立即执行移动——不等服务器确认。
    /// </summary>
    private Vector3 CalculateMovement(Vector3 moveDir)
    {
        // 水平移动
        Vector3 horizontalMove = moveDir * (_moveSpeed * Time.deltaTime);

        // 重力处理
        if (_controller.isGrounded && _verticalVelocity.y < 0)
            _verticalVelocity.y = -2f; // 小负值确保贴地
        _verticalVelocity.y += _gravity * Time.deltaTime;
        Vector3 verticalMove = _verticalVelocity * Time.deltaTime;

        // 合并并移动
        Vector3 totalMove = horizontalMove + verticalMove;
        _controller.Move(totalMove);

        // 旋转朝向移动方向
        if (moveDir.sqrMagnitude > 0.01f)
        {
            Quaternion targetRotation = Quaternion.LookRotation(moveDir);
            transform.rotation = Quaternion.RotateTowards(
                transform.rotation, targetRotation, _rotationSpeed * Time.deltaTime);
        }

        return transform.position;
    }

    // ── RPC ──────────────────────────────────────────────

    /// <summary>
    /// ServerRpc: 客户端将输入发给服务器做权威处理。
    /// 参数包含 tick 用于服务器回包时告诉客户端"我处理到了第几个输入"。
    /// 注意：ServerRpc 必须是 public 且函数名以 "ServerRpc" 结尾。
    /// </summary>
    [ServerRpc]
    private void SendInputServerRpc(uint tick, Vector3 moveDir, float deltaTime)
    {
        // 服务器权威处理移动（与客户端相同的逻辑，但使用服务器的物理环境）
        // 注意：服务器上没有 CharacterController 的本地概念，
        // 这里我们直接修改 _serverPosition 的值
        Vector3 newPos = _serverPosition.Value + moveDir * (_moveSpeed * deltaTime);

        // 简单重力（服务器端）
        // 实际项目中应在服务器维护完整的物理状态
        _serverPosition.Value = newPos;

        // 更新 NetworkTransform（如果启用的话）
        // NetworkTransform 会基于 transform.position 的变更自动同步
        transform.position = newPos;
        if (moveDir.sqrMagnitude > 0.01f)
            transform.rotation = Quaternion.LookRotation(moveDir);
    }

    // ── 和解系统 ─────────────────────────────────────────

    /// <summary>
    /// 当服务器权威位置更新时回调。
    /// 客户端比较预测位置和服务器位置，如不一致则和解。
    /// </summary>
    private void OnServerPositionChanged(Vector3 oldValue, Vector3 newValue)
    {
        // 只有本地玩家需要和解——因为只有本地玩家在预测
        if (!IsOwner) return;

        // 简化版和解：直接将位置纠正为服务器位置
        // 生产级实现应保留未确认输入并重新模拟（见练习3）

        Vector3 predictedPos = transform.position;
        float error = Vector3.Distance(predictedPos, newValue);

        // 如果误差超过阈值，执行"硬纠正"
        const float SNAP_THRESHOLD = 0.5f;
        if (error > SNAP_THRESHOLD)
        {
            Debug.LogWarning($"[Reconciliation] 位置偏差 {error:F3}m，纠正中...");
            // 关掉 CharacterController 以避免冲突
            _controller.enabled = false;
            transform.position = newValue;
            _controller.enabled = true;

            // 清理已经被服务器确认的旧输入
            // （简化版：直接清空。生产版应保留未确认的输入并重放）
            _pendingInputs.Clear();
        }
    }

    // ── 调试信息 ─────────────────────────────────────────
    private void OnGUI()
    {
        if (!IsOwner) return;
        GUILayout.BeginArea(new Rect(10, 10, 300, 200));
        GUILayout.Label($"Input Tick: {_inputTick}");
        GUILayout.Label($"Pending Inputs: {_pendingInputs.Count}");
        GUILayout.Label($"Server Pos: {_serverPosition.Value}");
        GUILayout.Label($"Local Pos: {transform.position}");
        GUILayout.EndArea();
    }
}
```

**关键设计决策注释**：

1. **CharacterController 的双重角色**：本地玩家用它做物理移动（预测），远程玩家禁用它（由 NetworkTransform 接管）。如果不禁用，远程玩家的 CharacterController 会与 NetworkTransform 的同步位置发生冲突。

2. **预测与和解的简化**：上面的实现使用了最简单的"硬纠正"（snap to server position）。生产级系统应保留 `_pendingInputs` 中未被服务器处理的输入，纠正位置后重新模拟它们。（见练习 3）

3. **`NetworkVariable<Vector3>` 并非必要**：如果已经挂载了 `NetworkTransform`，NGO 会自动同步 `transform.position`。这里显式使用 `NetworkVariable` 是为了教学目的——让你看到服务器权威状态的同步路径。在实际项目中，`NetworkTransform` 就够用了。

### 2.3 NetworkTransform 配置要点

在 Player Prefab 上挂载 `NetworkTransform` 组件并做如下配置：

```
NetworkTransform 配置（Inspector）:
  ┌─────────────────────────────────────────────┐
  │ Sync Position:       ✓ (World Space)        │
  │ Sync Rotation:       ✓ (World Space)        │
  │ Sync Scale:          ✗                      │
  │ Interpolate:         ✓ (Enabled)            │
  │   └─ 使远程玩家移动平滑插值                   │
  │ Use Half Float Precision: ✓ (降低带宽 50%)    │
  │ Position Threshold:   0.001 (最小变化才同步)  │
  │ Rotation Threshold:   0.01                   │
  └─────────────────────────────────────────────┘
```

**为什么启用 Interpolate？**

`NetworkTransform.Interpolate` 是 NGO 内置的插值系统。当服务器以固定频率（通常 30Hz）发送位置快照时，插值在客户端两个快照之间做平滑过渡。没有插值 → 远程玩家"瞬移"；有插值 → 远程玩家平滑移动。

**重要限制**：NGO 的插值是**纯表现层**的——它不改变逻辑，只是在渲染时补间。这意味着远程玩家的实际位置（`transform.position`）仍然是快照值，只有渲染位置是插值过的。如果你需要通过 `transform.position` 做碰撞检测，需要自行维护一个平滑的位置缓冲区。

### 2.4 HealthSystem.cs — NetworkVariable 血量同步（~60行）

```csharp
// HealthSystem.cs
// 挂载在 Player Prefab 上。
// 用法：服务器权威管理血量，客户端通过 NetworkVariable 自动获取变化。
// 当血量 <= 0 时，触发死亡逻辑（由服务器决定）。

using UnityEngine;
using Unity.Netcode;
using System;

public class HealthSystem : NetworkBehaviour
{
    [Header("血量配置")]
    [SerializeField] private int _maxHealth = 100;

    // ── NetworkVariable ──────────────────────────────────
    // NetworkVariable<T> 是 NGO 的核心同步原语。
    // 任何写操作（.Value = xxx）只有在服务器执行时才生效并同步。
    // 客户端可以通过 OnValueChanged 回调监听变化。
    private NetworkVariable<int> _currentHealth = new NetworkVariable<int>(
        100,                                            // 初始值
        NetworkVariableReadPermission.Everyone,         // 所有客户端都可读
        NetworkVariableWritePermission.Server           // 只有服务器可写
    );

    // ── 事件 ────────────────────────────────────────────
    /// <summary>当血量变化时触发（服务器和所有客户端都会收到）</summary>
    public event Action<int, int> OnHealthChanged; // (newHealth, maxHealth)

    /// <summary>当玩家死亡时触发</summary>
    public event Action<ulong> OnPlayerDeath;       // (clientId)

    public int CurrentHealth => _currentHealth.Value;
    public int MaxHealth => _maxHealth;
    public bool IsDead => _currentHealth.Value <= 0;

    public override void OnNetworkSpawn()
    {
        base.OnNetworkSpawn();

        // 监听血量变化——在所有客户端上触发
        _currentHealth.OnValueChanged += OnHealthValueChanged;

        // 初始化时触发一次，让 UI 同步
        if (IsClient)
            OnHealthChanged?.Invoke(_currentHealth.Value, _maxHealth);
    }

    public override void OnNetworkDespawn()
    {
        _currentHealth.OnValueChanged -= OnHealthValueChanged;
        base.OnNetworkDespawn();
    }

    /// <summary>
    /// NetworkVariable 变化回调。
    /// 注意：此回调在服务器和所有客户端都会触发。
    /// </summary>
    private void OnHealthValueChanged(int oldValue, int newValue)
    {
        Debug.Log($"[HealthSystem] 血量变化: {oldValue} → {newValue} (Owner: {OwnerClientId})");
        OnHealthChanged?.Invoke(newValue, _maxHealth);

        // 死亡检测
        if (newValue <= 0 && oldValue > 0)
        {
            OnPlayerDeath?.Invoke(OwnerClientId);
            HandleDeath();
        }
    }

    // ── 服务器权限操作 ───────────────────────────────────

    /// <summary>
    /// 造成伤害。
    /// 只能在服务器调用。客户端应通过 ServerRpc 间接调用。
    /// </summary>
    public void TakeDamage(int damage)
    {
        if (!IsServer)
        {
            Debug.LogError("TakeDamage must be called on server!");
            return;
        }

        if (IsDead) return;

        int newHealth = Mathf.Max(0, _currentHealth.Value - damage);
        _currentHealth.Value = newHealth;
        // 赋值 .Value 会触发 OnValueChanged 回调（服务器端 + 所有客户端）
    }

    /// <summary>
    /// 治疗。
    /// </summary>
    public void Heal(int amount)
    {
        if (!IsServer) return;
        if (IsDead) return;

        int newHealth = Mathf.Min(_maxHealth, _currentHealth.Value + amount);
        _currentHealth.Value = newHealth;
    }

    /// <summary>
    /// 复活（重置血量）。
    /// </summary>
    public void Respawn()
    {
        if (!IsServer) return;
        _currentHealth.Value = _maxHealth;
    }

    // ── 死亡处理 ─────────────────────────────────────────

    private void HandleDeath()
    {
        Debug.Log($"[HealthSystem] Player {OwnerClientId} 死亡");

        // 服务器端处理：禁用碰撞体、播放死亡动画等
        if (IsServer)
        {
            // 3 秒后重生
            Invoke(nameof(Respawn), 3f);
        }

        // 客户端也可以在这里播放死亡表现
        // 注意：要用 ClientRpc 来确保所有客户端都看到死亡效果
    }
}
```

**NetworkVariable 的内部实现要点**：

- 服务器赋值 `.Value` 时，NGO 内部对值做脏标记（dirty flag），下一个网络帧自动序列化并发送给客户端
- 如果连续多次赋值（如快速扣血），只有最后一个值会被发送——NGO 精确到"最新状态"
- `NetworkVariable` 支持的类型有限：`int`, `float`, `bool`, `string`, `Vector3`, `Quaternion` 等值类型。复杂类型需自定义序列化（实现 `INetworkSerializable`）

### 2.5 ShootingSystem.cs — ServerRpc + 命中回退（~100行）

```csharp
// ShootingSystem.cs
// 挂载在 Player Prefab 上。
// 设计要点：
// 1. 客户端通过 ServerRpc 请求射击
// 2. 服务器执行射线检测（权威命中判定）并扣血
// 3. 服务器通过 ClientRpc 广播射击效果（枪口火焰、弹道等）
// 4. 客户端预测射击特效：不等服务器确认，本地立即播放

using UnityEngine;
using Unity.Netcode;
using System.Collections;

public class ShootingSystem : NetworkBehaviour
{
    [Header("射击参数")]
    [SerializeField] private float _fireRate = 0.1f;        // 射速（秒/发）
    [SerializeField] private float _range = 100f;            // 射程
    [SerializeField] private int _damage = 15;               // 每发伤害
    [SerializeField] private LayerMask _hitMask;             // 可命中层级

    [Header("视觉反馈")]
    [SerializeField] private GameObject _muzzleFlashPrefab;  // 枪口火焰预制体
    [SerializeField] private Transform _muzzlePoint;          // 枪口位置
    [SerializeField] private LineRenderer _tracerPrefab;      // 弹道拖尾

    private float _nextFireTime;

    private void Update()
    {
        // 只有本地玩家才处理射击输入
        if (!IsOwner) return;

        if (Input.GetButton("Fire1") && Time.time >= _nextFireTime)
        {
            _nextFireTime = Time.time + _fireRate;
            Fire();
        }
    }

    /// <summary>
    /// 客户端射击入口。
    /// 1. 本地立即做射线检测（客户端预测命中）
    /// 2. 播放射击特效（不等服务器）
    /// 3. 通过 ServerRpc 请求服务器做权威判定
    /// </summary>
    private void Fire()
    {
        // ── 客户端预测：本地射线检测（仅用于即时反馈） ──
        Ray ray = new Ray(_muzzlePoint.position, _muzzlePoint.forward);
        RaycastHit clientHit;
        bool clientHitSomething = Physics.Raycast(ray, out clientHit, _range, _hitMask);

        // ── 本地立即播放特效 ──
        PlayMuzzleFlashClientRpc(); // 用 ClientRpc 通知所有客户端看到特效
        if (clientHitSomething)
            PlayTracerClientRpc(_muzzlePoint.position, clientHit.point);

        // ── 请求服务器做权威判定 ──
        // 将射击参数发给服务器。服务器重新做射线检测（以服务器视角），
        // 如果命中则扣目标血量。
        RequestFireServerRpc(
            _muzzlePoint.position,
            _muzzlePoint.forward,
            Time.time
        );

        Debug.Log($"[ShootingSystem] 本地射击请求已发送 (Pos: {_muzzlePoint.position})");
    }

    // ── RPC ──────────────────────────────────────────────

    /// <summary>
    /// ServerRpc: 客户端请求服务器处理射击。
    /// 参数包含射击时的精确位置和方向（注意：服务器上的玩家位置可能略有不同）。
    /// </summary>
    [ServerRpc]
    private void RequestFireServerRpc(Vector3 origin, Vector3 direction, float clientTime)
    {
        Debug.Log($"[ShootingSystem] 服务器处理射击 (Owner: {OwnerClientId}, Time: {clientTime})");

        // ── 服务器权威射线检测 ──
        // 注意：使用客户端发送的 origin/direction 还是使用服务器的当前位置？
        // 答案：取决于延迟补偿策略。

        // 简化版：使用服务器当前位置（更准确但延迟高）
        // Vector3 serverOrigin = _muzzlePoint.position;

        // 进阶版：使用客户端发送的 origin（需要服务端维护历史位置做延迟补偿）
        // 这里采用客户端参数——模拟简单的"客户端视角判定"
        Ray ray = new Ray(origin, direction);
        RaycastHit hit;

        if (Physics.Raycast(ray, out hit, _range, _hitMask))
        {
            // 检测命中的对象是否有 HealthSystem
            HealthSystem targetHealth = hit.collider.GetComponent<HealthSystem>();
            if (targetHealth != null)
            {
                // 服务器权威扣血
                targetHealth.TakeDamage(_damage);

                // 广播命中效果给所有客户端
                NotifyHitClientRpc(hit.point, hit.normal, _damage);

                Debug.Log($"[ShootingSystem] 命中目标 {targetHealth.OwnerClientId}, 伤害: {_damage}");
            }
        }
    }

    /// <summary>
    /// ClientRpc: 通知所有客户端播放枪口火焰。
    /// 服务器调用后，所有客户端（包括发送方）都会执行。
    /// </summary>
    [ClientRpc]
    private void PlayMuzzleFlashClientRpc()
    {
        if (_muzzleFlashPrefab != null && _muzzlePoint != null)
        {
            GameObject flash = Instantiate(_muzzleFlashPrefab, _muzzlePoint);
            Destroy(flash, 0.1f); // 0.1秒后销毁
        }
    }

    /// <summary>
    /// ClientRpc: 绘制弹道拖尾。
    /// </summary>
    [ClientRpc]
    private void PlayTracerClientRpc(Vector3 start, Vector3 end)
    {
        if (_tracerPrefab != null)
        {
            LineRenderer tracer = Instantiate(_tracerPrefab);
            tracer.SetPosition(0, start);
            tracer.SetPosition(1, end);
            StartCoroutine(FadeAndDestroyTracer(tracer));
        }
    }

    /// <summary>
    /// ClientRpc: 命中特效（火花、血液等）。
    /// </summary>
    [ClientRpc]
    private void NotifyHitClientRpc(Vector3 hitPoint, Vector3 hitNormal, int damage)
    {
        Debug.Log($"[ShootingSystem] 命中点: {hitPoint}, 伤害: {damage}");
        // 这里播放命中特效——火花、血液粒子等
        // 实际项目中调用 VFXManager 或对象池
    }

    // ── 辅助 ─────────────────────────────────────────────

    private IEnumerator FadeAndDestroyTracer(LineRenderer tracer)
    {
        yield return new WaitForSeconds(0.05f);
        // 简单的淡出（省略 alpha 操作）
        Destroy(tracer.gameObject);
    }

    // ── 命中回退（Lag Compensation）说明 ──────────────────
    //
    // 上面的实现有一个根本问题：如果客户端和服务器之间延迟为 100ms，
    // 客户端看到的"命中"是在 100ms 前的玩家位置上。到服务器时，目标已经移动了。
    //
    // 解决方案（NGO 不内置，需手动实现）：
    // 1. 服务器维护所有玩家最近 N 帧的位置历史（环形缓冲）
    // 2. 客户端发送射击请求时附带一个时间戳
    // 3. 服务器根据 RTT 倒推目标在该时间戳时的位置
    // 4. 用倒推位置做命中判定
    //
    // 这就是"延迟补偿"(Lag Compensation)的简化实现。
    // 详细原理见第 17 节教程。
}
```

**关键设计决策注释**：

1. **客户端预测特效 vs 服务器权威伤害**：特效（枪口火焰、弹道）在本地立即播放以消除视觉延迟；伤害判定始终在服务器执行以反外挂。两者解耦。

2. **客户端发 origin 还是服务器自己算**：代码中选择使用客户端发送的 `origin` 参数——这是"偏好客户端体验"的做法，代价是服务器需要信任客户端的位置信息（外挂风险）。更严格的做法是服务器用自己的 `_muzzlePoint.position` 做射线（更安全，但高延迟下命中窗口更苛刻）。

3. **ServerRpc 的 `SendTo` 选项**：默认 `SendTo.Server`。实际上还有 `SendTo.Owner`（只有 owner 能调用）等权限控制——这里依赖 `IsOwner` 的客户端检查。

### 2.6 NetworkAnimator — 动画同步

在 Player Prefab 上挂载 `NetworkAnimator` 组件：

```
Player Prefab Inspector:
  ├── Animator (带 Humanoid Avatar)
  │   ├── Parameters:
  │   │   ├── Speed (Float)
  │   │   ├── IsGrounded (Bool)
  │   │   ├── Fire (Trigger)
  │   │   └── Death (Trigger)
  │   └── Controller: PlayerAnimController
  └── NetworkAnimator (组件)
      └── Animator: 拖入上述 Animator
```

然后在 `PlayerController` 中驱动动画参数（仅本地玩家需要设置 Animator 参数——`NetworkAnimator` 自动将它们同步到远程客户端）：

```csharp
// 在 PlayerController.Update() 中添加（仅 IsOwner=true 时执行）：

private Animator _animator;

public override void OnNetworkSpawn()
{
    base.OnNetworkSpawn();
    _animator = GetComponent<Animator>();
    // ...
}

// 在 Update() 中（IsOwner 分支内）：
private void UpdateAnimator(Vector3 moveDir)
{
    if (_animator == null) return;

    // 设置动画参数
    // NetworkAnimator 会自动将这些参数同步到所有客户端
    _animator.SetFloat("Speed", moveDir.magnitude);
    _animator.SetBool("IsGrounded", _controller.isGrounded);
}

// 射击时：
// _animator.SetTrigger("Fire");  // NetworkAnimator 自动同步 Trigger
```

**NetworkAnimator 工作原理**：

- 它在 `Owner` 的 `Animator` 上监听参数变化
- 每帧将脏标记的参数序列化并通过 `NetworkVariable` 机制发送
- 远程客户端自动应用接收到的参数值
- Trigger 类型参数会被自动重置（`SetTrigger` → 一帧后 `ResetTrigger`），NetworkAnimator 只同步"触发"这一事件

### 2.7 场景配置总览

完整的 Player Prefab 组件表：

```
Player Prefab:
├── NetworkObject
│   └── 勾选 "Destroy With Scene": false（让对象在切换场景时销毁）
├── NetworkTransform
│   ├── Sync Position: ✓ (World)
│   ├── Sync Rotation: ✓ (World)
│   ├── Interpolate: ✓
│   └── Position Threshold: 0.001
├── NetworkAnimator
│   └── Animator: (拖入)
├── Animator
│   └── Controller: PlayerAnimController
├── CharacterController
│   ├── Center: (0, 1, 0)
│   ├── Radius: 0.5
│   └── Height: 2
├── PlayerController (Script)
├── HealthSystem (Script)
└── ShootingSystem (Script)
    ├── Muzzle Flash Prefab: (拖入)
    ├── Muzzle Point: (子节点 Transform)
    └── Tracer Prefab: (拖入)
```

### 2.8 NGO vs Netcode for Entities 对比

Unity 在 2023 年推出了第二个网络方案 **Netcode for Entities**（基于 ECS/DOTS）。两者对比如下：

| 维度 | Netcode for GameObjects (NGO) | Netcode for Entities |
|------|------------------------------|---------------------|
| 底层架构 | GameObject / MonoBehaviour | ECS (Entity, Component, System) |
| 学习曲线 | 低——与现有 Unity 开发模式一致 | 高——需要学 ECS + Burst + Job System |
| 同步方式 | NetworkVariable + RPC | Ghost (快照) + RPC + IComponentData 自动同步 |
| 插值 | NetworkTransform.Interpolate | Ghost 内置可配置插值系统 |
| 预测 | 手动实现（本教程方式） | GhostPredictionSystemGroup（内置客户端预测框架） |
| 性能上限 | ~100-200 个同步对象/客户端 | 数千个同步对象（ECS 的内存和 CPU 优势） |
| 适用场景 | 小规模多人（<32 玩家）、RPG、休闲游戏 | 大世界、大量实体（RTS、大型射击游戏） |
| 成熟度 | 生产可用（Unity 6 正式版） | 仍在完善中（2024-2025） |
| 物理 | 依赖 GameObject 物理 | Unity Physics（基于 DOTS 的确定性物理） |

**选择建议**：

- 刚入门多人游戏 → NGO。与 GameObject 开发模式一致，社区资源丰富
- 需要客户端预测开箱即用 → 评估 Netcode for Entities 的 GhostPredictionSystemGroup
- 超大规模多实体同步 → Netcode for Entities（或 Photon Quantum/Bolt）
- 面试准备 → 掌握 NGO，但能说清楚 Entities 版本的差异（加分项）

---

## 3. 练习

### 练习 1: 基础——补全计分板 UI（预计 30min）

当前的 Demo 缺少 HUD。请完成以下任务：

1. 创建一个 `PlayerHUD` 类（挂载在 Canvas 上），显示：
   - 当前血量条（绑定 `HealthSystem.OnHealthChanged`）
   - 当前弹药数（给 `ShootingSystem` 添加 `_ammo` 和 `_maxAmmo` NetworkVariable）
   - 击杀/死亡数（使用 NetworkVariable 从服务器同步）
2. 确保 UI 只在本地玩家的 Canvas 上显示（通过 `IsOwner` 控制）
3. 验证：两个客户端连接后，各自的 HUD 显示正确的个人数据

**验收标准**：两个客户端同时运行，每个客户端的 HUD 显示自己的血量，射中对方时对方的血条减少。

### 练习 2: 进阶——实现基于历史缓冲区的延迟补偿（预计 45min）

当前 `ShootingSystem.RequestFireServerRpc()` 使用客户端发送的 origin 做射线检测，没有做延迟补偿。请改进：

1. 服务器端维护一个 `Dictionary<ulong, Queue<Vector3>>`，记录每个玩家最近 60 帧（约 2 秒 @ 30Hz）的位置历史
2. 客户端发送射击请求时附带一个 `serverTime` 参数（而非客户端的 `Time.time`）
3. 服务器根据 `serverTime` 和当前服务器时间计算 RTT，从历史缓冲区取出目标在该时刻的位置
4. 用倒推位置做射线检测，而非当前位置
5. 分析：这样做后，高延迟（200ms+）下的命中判定准确度有什么变化？

**验收标准**：在 `NetworkManager` 中模拟 200ms 延迟（见下），两个玩家对射时，命中判定仍然"看起来准确"（客户端视角和服务器判定一致）。

延迟模拟代码（在 `NetworkManager` 的传输层设置中）：
```csharp
// 添加到 GameNetworkManager 中
var transport = GetComponent<Unity.Netcode.Transports.UTP.UnityTransport>();
// 注意：Unity Transport 本身不支持直接模拟延迟。
// 使用 Unity Transport 的模拟工具或第三方工具（如 Clumsy for Windows）。
// 或使用 UNET Transport（旧版）的 Simulator 参数。
// 也可以用 NetworkManager 的 NetworkConfig 做 RTT 模拟：
// （具体取决于 NGO 版本，部分版本内置了模拟参数）
```

### 练习 3: 挑战——完整的预测回滚和解系统（预计 60min）

当前 `PlayerController` 的"和解"只是简单地将位置纠正为服务器位置。请实现一个完整的预测回滚系统：

1. 维护一个 `Dictionary<uint, PlayerState>`（tick → 位置/速度/输入），记录每个 tick 的预测状态
2. 当收到服务器的权威位置时：
   a. 从字典中找到服务器确认的最新 tick
   b. 将该 tick 的位置替换为服务器位置（回滚）
   c. 重新模拟（重放）该 tick 之后的所有未确认输入
3. 确保"重放"过程与原始预测使用完全相同的输入和 deltaTime（确定性重放）
4. 添加平滑纠正：如果误差很小（<0.1m），不使用硬纠正，而是逐渐 lerp 到服务器位置（视觉上平滑）
5. 分析：在什么情况下硬纠正比平滑纠正更好？（提示：考虑瞬移、穿墙、外挂检测）

**验收标准**：在高延迟（200ms）下，本地玩家的移动仍然流畅——不会因为每次服务器回包而"跳回"到服务器位置。用 Debug 面板显示和解发生的次数和平均误差。

```csharp
// 提示：PlayerState 结构体
private struct PlayerState
{
    public uint Tick;
    public Vector3 Position;
    public Vector3 Velocity;
    public Vector3 InputDirection; // 该 tick 的输入
}

// 预测回滚伪代码：
// void Reconcile(Vector3 serverPos, uint serverAckedTick)
// {
//     // 1. 移除已确认的旧状态
//     while (_stateHistory.Count > 0 && _stateHistory.Peek().Tick <= serverAckedTick)
//         _stateHistory.Dequeue();
//
//     // 2. 计算误差
//     Vector3 predictedPos = _stateHistory.Peek().Position; // 服务器确认 tick 对应我们的预测位置
//     Vector3 error = serverPos - predictedPos;
//
//     // 3. 如果误差大，回滚并重放
//     if (error.magnitude > 0.1f) {
//         transform.position = serverPos;
//         foreach (var state in _stateHistory) {
//             // 重放每个未确认的输入
//             ApplyInput(state.InputDirection, state.Velocity, deltaTime);
//         }
//     } else {
//         // 小误差 → 平滑纠正
//         transform.position = Vector3.Lerp(transform.position, transform.position + error, 0.1f);
//     }
// }
```

---

## 4. 扩展阅读

### 4.1 官方文档
- **[Unity Netcode for GameObjects 官方文档](https://docs-multiplayer.unity3d.com/netcode/current/about/)**：所有 API 的权威参考，包含 NetworkVariable、RPC、NetworkTransform 的详细说明
- **[NGO GitHub 仓库](https://github.com/Unity-Technologies/com.unity.netcode.gameobjects)**：源码。面试中"你读过 NGO 的 NetworkVariable 序列化实现吗？"是高级问题
- **[Unity Transport Package](https://docs.unity3d.com/Packages/com.unity.transport@latest)**：NGO 底层的 UDP 传输层，了解它的可靠性模式和带宽管理

### 4.2 业界参考
- **[Valve 的 Source Multiplayer Networking](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking)**：CS:GO / TF2 的网络模型，包含业界最成熟的延迟补偿实现（server-side lag compensation using hitbox history）
- **[Overwatch Gameplay Architecture and Netcode (GDC 2017)](https://www.youtube.com/watch?v=W3aieHjyNvw)**：最著名的状态同步 ECS 架构案例，服务器 Tick Rate 60Hz + 客户端预测 + 完整的射击命中回退
- **[Rocket League 网络架构](https://www.gdcvault.com/play/1024970/It-IS-Rocket-Science-The)**：物理驱动的状态同步（车辆物理 + 球物理），展示了 NetworkPhysics 的实现难点

### 4.3 开源项目
- **[Boss Room (Unity 官方)](https://github.com/Unity-Technologies/com.unity.multiplayer.samples.coop)**：Unity 官方用 NGO 构建的完整多人 RPG Demo，包含角色选择、战斗、场景切换
- **[NGO Best Practices](https://docs-multiplayer.unity3d.com/netcode/current/learn/best-practices/)**：官方最佳实践——从 NetworkVariable 粒度到 RPC 频率的优化指南

---

## 常见陷阱

### 陷阱 1: 在客户端直接修改 NetworkVariable

```csharp
// ❌ 错误——客户端没有写权限（除非设置了 Everyone 写权限）
_currentHealth.Value = 50;  // 编译通过，运行时无效！客户端不会同步这个修改

// ✅ 正确——通过 ServerRpc 请求服务器修改
[ServerRpc]
private void RequestDamageServerRpc(int damage) {
    _currentHealth.Value -= damage;  // 服务器上执行，自动同步回所有客户端
}
```

`NetworkVariableWritePermission` 默认是 `Server`。如果你在客户端赋值 `.Value`，NGO 不会报错也不会同步，赋值被静默忽略。这是一个很难排查的 bug。

### 陷阱 2: ServerRpc 在错误的所有权上下文中调用

```csharp
// ❌ 错误——ServerRpc 默认只有 Owner 能调用
[ServerRpc]
private void DoSomethingServerRpc() { /* ... */ }

// 在非 Owner 的客户端上调用 → 报错 "ServerRpc called on non-owner"
// 解决方法：添加 RequireOwnership = false
[ServerRpc(RequireOwnership = false)]
private void AnyoneCanCallServerRpc() { /* ... */ }
```

### 陷阱 3: NetworkTransform 与物理系统冲突

```
常见错误：在 Player Prefab 上同时启用 CharacterController 和 NetworkTransform。
远程玩家的 CharacterController 会尝试让角色"站在地上"，
而 NetworkTransform 在更新位置 → 抖动。
```

**解决方法**：远程玩家禁用 CharacterController（或 Rigidbody），让 NetworkTransform 完全接管。只在 `IsOwner=true` 时启用物理组件。

### 陷阱 4: NetworkAnimator 的 Trigger 同步时机

`NetworkAnimator` 同步 Animator 的 Trigger 参数有延迟（最多一帧）。如果本地玩家在 `Update()` 中 `SetTrigger("Fire")` 然后立即检查该 Trigger 的状态，可能会读到"还没触发"的状态。**不要依赖 Trigger 的即时状态做逻辑判断**——用 C# 变量替代。

### 陷阱 5: SpawnWithOwnership 的时机问题

```csharp
// ❌ 错误——在客户端已经连接但 OnClientConnectedCallback 还未触发时
// 手动调用 SpawnWithOwnership 会失败

// ✅ 正确——在 OnClientConnectedCallback 中生成
_netManager.OnClientConnectedCallback += OnClientConnected;
```

`SpawnWithOwnership` 必须在客户端完全连接后才能调用。最佳位置就是 `OnClientConnectedCallback`。

### 陷阱 6: 高频 NetworkVariable 更新导致带宽爆炸

```csharp
// ❌ 错误——每帧更新 NetworkVariable（60Hz = 60 次/秒的同步）
void Update() { _serverPosition.Value = transform.position; }  // 每帧发送！

// ✅ 正确——用阈值或定时器控制同步频率
private float _syncTimer;
void Update() {
    _syncTimer += Time.deltaTime;
    if (_syncTimer >= 0.033f) { // 30Hz 同步频率
        _syncTimer = 0f;
        _serverPosition.Value = transform.position;
    }
}
```

或者直接用 `NetworkTransform`（内置阈值和频率控制），不要手动同步 Transform。

### 陷阱 7: 没有在 OnDestroy/OnDisable 中取消 NetworkVariable 的事件订阅

```csharp
// ❌ 错误——GameObject 销毁后，OnValueChanged 回调仍可能触发（GC 延迟）
// 导致 null reference 异常

// ✅ 正确——始终在 OnNetworkDespawn 或 OnDestroy 中取消订阅
public override void OnNetworkDespawn() {
    _currentHealth.OnValueChanged -= OnHealthValueChanged;
    base.OnNetworkDespawn();
}
```

`NetworkVariable` 的内部事件系统在对象销毁后不会自动清理订阅——这是 C# event 的通用陷阱，但在网络环境中尤为常见（对象可能在网络事件触发的同一帧被销毁）。

### 陷阱 8: 混淆 NetworkObjectId 和 OwnerClientId

- `NetworkObject.NetworkObjectId`：这个 NetworkObject 的唯一 ID（场景内全局唯一）
- `NetworkBehaviour.OwnerClientId`：拥有此对象的客户端 ID（服务器为 0，客户端从 1 开始）

常见错误：将 `OwnerClientId` 当作"实体 ID"使用——两个不同的 Player 对象可能有不同的 `NetworkObjectId`，但相同的 `OwnerClientId`（如果属于同一玩家）。做字典查找时，用 `NetworkObjectId` 做 Key，不要用 `OwnerClientId`。
