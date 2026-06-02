# 弱网环境深度优化

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [02-UDP vs TCP 与可靠传输层](02-udp-vs-tcp-reliable-layer.md), [07-帧同步协议设计](07-lockstep-protocol-design.md), [11-帧同步服务端设计](11-lockstep-server-design.md), [17-延迟补偿](17-lag-compensation.md), [21-状态同步服务端](21-state-sync-server.md)

---

## 1. 概念讲解

### 1.1 弱网的定义与分级

弱网不是"网断了"，而是"网络质量退化"。它与断线的区别在于：**连接还在，但质量已不足以支撑正常的游戏体验**。理解弱网分级的价值在于——不同级别需要不同的对抗策略，一刀切的"网络差就踢人"是低级做法。

```
┌─────────────────────────────────────────────────────────────────────┐
│                       弱网分级标准                                     │
├──────────┬──────────────┬──────────────┬──────────────────────────────┤
│   级别    │  RTT (ms)    │   丢包率     │        典型场景               │
├──────────┼──────────────┼──────────────┼──────────────────────────────┤
│  正常     │  < 50        │   < 1%       │ 有线宽带 / 优质 WiFi          │
│  轻度弱网 │  50 – 150    │   1% – 5%    │ 4G 良好信号 / 拥挤 WiFi        │
│  中度弱网 │  150 – 300   │   5% – 15%   │ 4G 弱信号 / 地铁站台            │
│  重度弱网 │  300 – 800   │   15% – 30%  │ 电梯 / 高铁 / 基站切换瞬间      │
│  濒临断线 │  > 800       │   > 30%      │ 隧道 / 地库 / 飞行模式           │
│  断线     │  ∞ (超时)    │   100%       │ 完全无网络                     │
└──────────┴──────────────┴──────────────┴──────────────────────────────┘
```

**关键洞察：RTT 和丢包率不是独立的**。在网络拥塞时，两者通常会同时恶化——因为路由器缓冲区满（Bufferbloat）会同时造成排队延迟（RTT 飙升）和尾部丢包（Loss 飙升）。一个好的弱网优化方案必须**同时对抗这两个指标**，而非各自为战。

> **面试要点**：不要只说"我们用 TCP 重传处理丢包"。TCP 的退避算法在弱网下会导致吞吐量崩溃。能说出"我们在应用层实现 BWE-based 发送速率控制，根据 RTT 梯度而非丢包来检测拥塞"才是高级回答。

**弱网问题的本质**：

弱网环境下的每一次通信，都面临一个不可能三角：

```
       可靠性（不丢包）
          /\
         /  \
        /    \
       / 游戏 \
      /  体验  \
     /__________\
  低延迟        高吞吐量
```

你最多同时优化两个维度。游戏对这三个维度的需求优先级是：**低延迟 > 可靠性 > 高吞吐量**。这意味着：

- **低延迟 + 可靠性**：选择冗余发包（UDP 同一数据发 2-3 次），牺牲吞吐量换取低延迟和可靠性。这是帧同步的典型策略。
- **低延迟 + 高吞吐量**：接受部分丢包（不重传），用插值/预测掩盖丢失的数据。状态同步中非关键属性的策略。
- **可靠性 + 高吞吐量**：使用大缓冲区 + TCP 重传，牺牲延迟。这恰好是游戏最不可接受的组合——却在很多初级实现中被默认使用。

### 1.2 移动端特有的弱网挑战

相比 PC/主机，移动端的网络环境有四个独有的挑战维度：

#### 挑战 1：WiFi ↔ 蜂窝网络切换时的 IP 变更

```
时间线: 玩家正在对局 (WiFi, IP=192.168.1.5)
  │
  ├─ T+0s:  玩家走出家门，WiFi 信号减弱到 -80dBm
  ├─ T+2s:  OS 检测到 WiFi 不可用，触发网络切换
  ├─ T+2.3s: 4G 蜂窝网络接管，IP 变为 10.45.32.18
  ├─ T+2.5s: 游戏客户端感知到网络变化（NetworkReachability 回调）
  │
  ▼ 此时发生了两件事：
     1. 旧的 TCP/UDP 四元组 (192.168.1.5:54321 → Server) 已不可用
        —— 从 WiFi 接口发出的包不会路由到 4G 接口
     2. 服务器还在向旧 IP 发送数据 —— 全部丢失
```

**核心矛盾**：TCP/UDP 连接绑定到**网络接口 + IP 地址**。网络接口切换 = 旧连接作废。标准的 TCP 重连要经过 SYN → SYN-ACK → ACK 三次握手（1-3 秒），对游戏来说太慢。

#### 挑战 2：电梯/地铁/隧道场景——周期性信号黑洞

这些场景的特点是**信号衰减不是瞬时的，而是周期性/可预测的**：

```
隧道场景 (典型 4G 信号变化):
 ┌─────────────────────────────────────────────────────────────┐
 │ ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████ │
 │  进隧道    隧道内 (15-60 秒)                     出隧道      │
 │  RTT=40ms  RTT→∞ 丢包100%                      RTT=40ms    │
 └─────────────────────────────────────────────────────────────┘

电梯场景:
 ┌─────────────────────────────────────────────────────────────┐
 │ ██░░░░░░░░░░████░░░░░░░░░░████░░░░░░░░░░░░░░░░░░░░░░████   │
 │ 楼层1  电梯运行   楼层15  电梯运行  楼层30  电梯运行  楼层45  │
 │ (门开) (信号断)  (门开)  (信号断) (门开)  (信号断)  (门开)  │
 └─────────────────────────────────────────────────────────────┘
```

对于隧道/地铁：应该**预判 + 增大缓冲**。如果游戏场景本身在隧道中（如地铁线路图），客户端可以提前提高缓冲水位，服务端增加空操作填充时长。

对于电梯：关键是**快速恢复**而非预防。电梯停留通常 5-15 秒，超过了帧同步的缓冲窗口（通常 3-6 帧，约 200-400ms），所以需要走重连流程。

#### 挑战 3：基站切换 (Cell Handover)

4G/5G 用户在移动中（步行、车载），手机会在不同基站之间切换。切换过程约 50-200ms，期间数据面会有短暂中断。

与 WiFi→4G 切换不同，基站切换**不会改变 IP 地址**（在同一运营商网络内），但会造成：
- 瞬时丢包：切换期间 3-10 个包丢失
- RTT 抖动：切换后 RTT 可能从 40ms 跳到 80ms（新旧基站到服务器的路由路径不同）

对抗策略：UDP 冗余包覆盖（同一数据发 2-3 次）通常足够覆盖基站切换的丢包窗口。

#### 挑战 4：后台 APP 被系统挂起

iOS 和 Android 都有激进的后台管理策略：

| 平台 | 后台网络限制 | 挂起时机 |
|------|-------------|---------|
| iOS | 后台 30 秒后网络被挂起（`URLSession` 后台模式除外） | 退后台约 10 秒 |
| Android 12+ | 后台网络受限（`Restricted App Standby Bucket`） | 取决于使用频率 |
| 鸿蒙 | 类似 Android，冻结后台进程网络 | 退后台约 20 秒 |

**游戏在前台但锁屏**也会触发后台策略。解决方案：
- iOS：使用 `beginBackgroundTaskWithExpirationHandler` 申请 30 秒缓冲窗口，在此期间通知服务端"即将断线"
- Android：使用前台服务（Foreground Service）保持网络活性
- 服务端：在收到"即将断线"通知后，将此玩家标记为"后台挂起"状态而非"网络故障"，增加容忍窗口

---

## 2. 连接迁移 (Connection Migration)

### 2.1 QUIC Connection Migration 原理

QUIC（Quick UDP Internet Connections）是目前最先进的传输层协议，其最亮眼的特性之一就是**连接迁移**。

传统 TCP 连接由四元组标识：`(源IP, 源端口, 目标IP, 目标端口)`。任何一个变了，连接就断了。

QUIC 使用 **Connection ID (CID)** 替代四元组来标识连接：

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUIC Connection Migration                      │
│                                                                  │
│  客户端                          服务器                          │
│  WiFi: 192.168.1.5:12345                                        │
│  │─────── CID=0xABCD ─────────►│ 记录: CID→(192.168.1.5:12345) │
│  │                              │                                │
│  │  [网络切换: WiFi→4G]          │                                │
│  │  IP 变为 10.45.32.18:54321   │                                │
│  │                              │                                │
│  │─────── CID=0xABCD ─────────►│ 收到来自新 IP 的包              │
│  │   + PATH_CHALLENGE frame    │ 验证: CID=0xABCD 已被授权       │
│  │                              │ 更新: CID→(10.45.32.18:54321) │
│  │◄────── PATH_RESPONSE ───────│ 后续数据发往新 IP              │
│  │                              │                                │
│  │  连接无缝迁移，0 次握手！     │                                │
└─────────────────────────────────────────────────────────────────┘
```

QUIC 的连接迁移不需要重新握手——因为 CID 在初始握手中已经完成了密钥协商和身份认证。服务器收到来自新 IP 但携带已知 CID 的包时，只需验证路径可达性（PATH_CHALLENGE/PATH_RESPONSE），不需要重新建立加密上下文。

**但 QUIC 并非万能**：如果你的服务器前面有传统的 TCP 负载均衡器（如 NGINX stream proxy），它们按四元组做会话保持，QUIC 的连接迁移特性会被破坏。需要使用支持 QUIC 的 L4 负载均衡器（如 HAProxy 2.6+、NGINX 1.25+ with QUIC）。

### 2.2 自定义实现：Session Token + 新连接绑定

大多数现有游戏服务器不使用 QUIC（QUIC 的库成熟度和运维工具体系还不够完善）。自定义连接迁移方案的核心思想是：**用一个 Session Token 将新连接绑定到旧会话**。

```
┌─────────────────────────────────────────────────────────────────┐
│                自定义连接迁移流程                                  │
│                                                                  │
│  客户端                           服务器                         │
│  │                                                              │
│  │  检测到网络切换（WiFi→4G）                                     │
│  │  1. 创建新 socket，新连接                                     │
│  │  2. 发送迁移请求:                                              │
│  │     { type: "MIGRATE",                                        │
│  │       session_token: "0xA3F2...",  ← 旧连接时分配的 token     │
│  │       old_conn_seq: 17452,         ← 旧连接最后确认的序列号    │
│  │       reason: "network_switch" }                              │
│  │────────────────────────────────►│                             │
│  │                                  │ 3. 验证 session_token      │
│  │                                  │ 4. 查找旧连接的 PlayerSession│
│  │                                  │ 5. 将新 fd 绑定到旧 Session│
│  │                                  │ 6. 从 old_conn_seq 之后    │
│  │                                  │    补发未确认的数据         │
│  │◄─── MIGRATE_ACK ────────────────│                             │
│  │    { new_conn_id,                │                             │
│  │      server_current_seq,         │                             │
│  │      pending_data[] }           │                             │
│  │                                  │                             │
│  │  7. 关闭旧 socket                │                             │
│  │  8. 正常通信恢复                  │                             │
│  └──────────────────────────────────┘                             │
│                                                                  │
│  关键时间线:                                                      │
│  - 迁移完成时间: 通常 < 500ms (新 TCP 连接 + 1 个 RTT)           │
│  - 期间丢包恢复: pending_data 包含断线期间服务器未确认的包        │
│  - 迁移失败重试: 3 次，间隔指数退避 (200ms → 400ms → 800ms)     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 C#: ConnectionMigrationManager（完整实现）

```csharp
// ConnectionMigrationManager.cs — 客户端连接迁移管理器
// 适用于 Unity 手游项目，处理 WiFi ↔ 4G 切换
// 依赖: UnityEngine (MonoBehaviour, Application.internetReachability)

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace GameNetwork.Migration
{
    /// <summary>
    /// 连接迁移管理器：监听网络变化，在切换时自动发起 Session 迁移。
    ///
    /// 核心职责:
    ///   1. 监听 UnityEngine.Application.internetReachability 变化
    ///   2. 在网络切换时，创建新连接，发送 MIGRATE 请求
    ///   3. 管理迁移状态机: Idle → Detecting → Migrating → Confirmed | Failed
    ///   4. 迁移成功后回收旧连接资源
    ///
    /// 使用方式: 挂载到场景中的 GameObject 上，配置 GameNetworkClient 引用。
    /// </summary>
    public class ConnectionMigrationManager : MonoBehaviour
    {
        // ─── 配置 ───────────────────────────────────────────────
        [Header("迁移配置")]
        [Tooltip("迁移请求最大重试次数")]
        [SerializeField] private int _maxRetries = 3;

        [Tooltip("重试间隔基数（毫秒），实际间隔 = base × 2^retry）")]
        [SerializeField] private int _retryBaseMs = 200;

        [Tooltip("迁移超时时间（毫秒），超时后判定迁移失败")]
        [SerializeField] private int _migrateTimeoutMs = 5000;

        [Tooltip("检测到网络变化后的稳定等待时间（避免网络抖动触发假切换）")]
        [SerializeField] private float _debounceSeconds = 0.5f;

        // ─── 状态 ───────────────────────────────────────────────
        private enum MigrationState { Idle, Detecting, Migrating, Confirmed, Failed }

        private MigrationState _state = MigrationState.Idle;
        private NetworkReachability _lastReachability;
        private string _sessionToken;             // 服务器分配的会话令牌
        private uint _lastAckedSeq;               // 最后确认的序列号（由网络层更新）
        private Coroutine _migrationCoroutine;
        private int _retryCount;
        private float _migrationStartTime;

        // ─── 外部依赖注入 ───────────────────────────────────────
        private IGameNetworkClient _networkClient;

        /// <summary>
        /// 会话令牌由服务器在首次连接成功后下发。
        /// 格式: Base64(SHA256(playerId + connectTime + serverSecret).Substring(0,12))
        /// 客户端不应本地生成 session token——必须由服务器分配以验证合法性。
        /// </summary>
        public string SessionToken
        {
            get => _sessionToken;
            set => _sessionToken = value;
        }

        /// <summary>
        /// 网络层每次确认服务器消息后更新此值。
        /// 迁移时携带 lastAckedSeq，服务器据此判断需要补发哪些数据。
        /// </summary>
        public uint LastAckedSeq
        {
            get => _lastAckedSeq;
            set => _lastAckedSeq = value;
        }

        // ─── 事件 ───────────────────────────────────────────────
        /// <summary>迁移成功回调: (新连接ID, 补发消息数)</summary>
        public event Action<int, int> OnMigrationSucceeded;

        /// <summary>迁移失败回调: (失败原因)</summary>
        public event Action<string> OnMigrationFailed;

        // ─── 生命周期 ───────────────────────────────────────────
        private void Start()
        {
            _networkClient = GetComponent<IGameNetworkClient>();
            if (_networkClient == null)
            {
                Debug.LogError("[Migration] IGameNetworkClient not found on GameObject. "
                    + "ConnectionMigrationManager requires a network client component.");
                enabled = false;
                return;
            }

            _lastReachability = Application.internetReachability;
        }

        private void Update()
        {
            NetworkReachability current = Application.internetReachability;

            // 仅在非迁移状态下监听网络变化
            if (_state == MigrationState.Idle && current != _lastReachability)
            {
                // 忽略 NotReachable（完全无网，此时迁移无意义）
                if (current == NetworkReachability.NotReachable)
                {
                    Debug.Log($"[Migration] Network became unreachable. "
                        + "Migration deferred until connectivity returns.");
                    _lastReachability = current;
                    return;
                }

                // 关键保护：从 NotReachable 回到 Reachable 时也触发迁移
                // 场景：玩家走出电梯/地库，网络恢复但 IP 可能已变
                Debug.Log($"[Migration] Network changed: {_lastReachability} → {current}. "
                    + "Starting debounce...");

                if (_migrationCoroutine != null)
                    StopCoroutine(_migrationCoroutine);
                _migrationCoroutine = StartCoroutine(DebouncedMigration(current));
            }

            _lastReachability = current;

            // 迁移超时检测
            if (_state == MigrationState.Migrating)
            {
                if (Time.unscaledTime - _migrationStartTime > _migrateTimeoutMs / 1000f)
                {
                    HandleMigrationTimeout();
                }
            }
        }

        /// <summary>
        /// 消抖等待: 网络变化后等待 debounceSeconds 秒，确认不是瞬时抖动。
        /// 如果等待期间网络又变了，Coroutine 会被新调用取消并重启。
        /// </summary>
        private IEnumerator DebouncedMigration(NetworkReachability newReachability)
        {
            _state = MigrationState.Detecting;

            yield return new WaitForSecondsRealtime(_debounceSeconds);

            // 消抖期间网络又变了——新的 Coroutine 会接管
            if (Application.internetReachability != newReachability)
                yield break;

            // 确认是真正的网络切换，开始迁移
            Debug.Log($"[Migration] Network change confirmed. Starting migration...");
            _state = MigrationState.Migrating;
            _retryCount = 0;
            _migrationStartTime = Time.unscaledTime;

            yield return StartCoroutine(PerformMigration());
        }

        private IEnumerator PerformMigration()
        {
            while (_retryCount < _maxRetries)
            {
                _retryCount++;
                Debug.Log($"[Migration] Attempt {_retryCount}/{_maxRetries}...");

                // 1. 创建新 socket 连接（底层走 TCP 或 KCP）
                int newConnId = _networkClient.CreateNewConnection();

                if (newConnId < 0)
                {
                    Debug.LogWarning($"[Migration] Failed to create new connection (attempt {_retryCount}).");
                    yield return StartCoroutine(WaitForRetry());
                    continue;
                }

                // 2. 发送迁移请求
                var migratePacket = BuildMigratePacket();
                _networkClient.SendRaw(newConnId, migratePacket);

                // 3. 等待 MIGRATE_ACK
                float waitStart = Time.unscaledTime;
                MigrateAck ack = null;

                while (Time.unscaledTime - waitStart < 3.0f) // 单次尝试等待 3 秒
                {
                    ack = _networkClient.TryReceiveMigrateAck(newConnId);
                    if (ack != null) break;
                    yield return null; // 等一帧
                }

                if (ack != null && ack.Accepted)
                {
                    // 4. 迁移成功: 切换到新连接，关闭旧连接
                    _networkClient.SwitchToConnection(newConnId, ack.ServerSeq, ack.PendingData);
                    _networkClient.CloseOldConnection();

                    _state = MigrationState.Confirmed;
                    Debug.Log($"[Migration] SUCCESS! New conn={newConnId}, "
                        + $"pending messages={ack.PendingData?.Length ?? 0}, "
                        + $"time={Time.unscaledTime - _migrationStartTime:F1}s");

                    OnMigrationSucceeded?.Invoke(newConnId, ack.PendingData?.Length ?? 0);
                    yield break;
                }
                else if (ack != null && !ack.Accepted)
                {
                    // 服务器拒绝了迁移请求（token 过期/无效）
                    _state = MigrationState.Failed;
                    string reason = ack.RejectReason ?? "unknown";
                    Debug.LogError($"[Migration] Server rejected: {reason}");
                    OnMigrationFailed?.Invoke($"Server rejected: {reason}");
                    yield break;
                }

                // 超时或 ack 包异常，重试
                Debug.LogWarning($"[Migration] Attempt {_retryCount} timed out. Retrying...");
                _networkClient.CloseConnection(newConnId);
                yield return StartCoroutine(WaitForRetry());
            }

            // 全部重试失败
            _state = MigrationState.Failed;
            Debug.LogError($"[Migration] All {_maxRetries} attempts failed.");
            OnMigrationFailed?.Invoke("All migration attempts exhausted.");
        }

        private IEnumerator WaitForRetry()
        {
            // 指数退避: 200ms → 400ms → 800ms (基于 retryCount)
            float delay = _retryBaseMs * Mathf.Pow(2, _retryCount - 1) / 1000f;
            Debug.Log($"[Migration] Waiting {delay:F1}s before retry...");
            yield return new WaitForSecondsRealtime(delay);
        }

        private byte[] BuildMigratePacket()
        {
            // 简单的二进制协议打包:
            // [1B: type=0x07] [2B: token_len] [N bytes: token]
            // [4B: last_acked_seq] [1B: reason_code]
            byte[] tokenBytes = System.Text.Encoding.UTF8.GetBytes(_sessionToken ?? "");
            byte[] packet = new byte[1 + 2 + tokenBytes.Length + 4 + 1];
            int offset = 0;

            packet[offset++] = 0x07; // MIGRATE 消息类型
            packet[offset++] = (byte)(tokenBytes.Length >> 8);
            packet[offset++] = (byte)(tokenBytes.Length & 0xFF);
            Buffer.BlockCopy(tokenBytes, 0, packet, offset, tokenBytes.Length);
            offset += tokenBytes.Length;
            packet[offset++] = (byte)(_lastAckedSeq >> 24);
            packet[offset++] = (byte)(_lastAckedSeq >> 16);
            packet[offset++] = (byte)(_lastAckedSeq >> 8);
            packet[offset++] = (byte)(_lastAckedSeq & 0xFF);
            packet[offset] = 0x01; // reason: network_switch

            return packet;
        }

        private void HandleMigrationTimeout()
        {
            _state = MigrationState.Failed;
            if (_migrationCoroutine != null)
                StopCoroutine(_migrationCoroutine);

            Debug.LogError($"[Migration] Timeout after {_migrateTimeoutMs}ms.");
            OnMigrationFailed?.Invoke("Migration timeout exceeded.");
        }

        private void OnDestroy()
        {
            if (_migrationCoroutine != null)
                StopCoroutine(_migrationCoroutine);
        }
    }

    // ─── 接口与数据结构 ───────────────────────────────────────

    /// <summary>
    /// 网络客户端必须实现的接口。
    /// 在真实项目中，这个接口由 KCP/TCP/WebSocket 网络层实现。
    /// </summary>
    public interface IGameNetworkClient
    {
        /// <summary>创建新的 socket 连接，返回连接 ID (>=0) 或 -1 失败</summary>
        int CreateNewConnection();

        /// <summary>关闭指定连接</summary>
        void CloseConnection(int connId);

        /// <summary>切换到新连接（新连接成为主连接）</summary>
        /// <param name="connId">新连接 ID</param>
        /// <param name="serverSeq">服务器当前序列号</param>
        /// <param name="pendingData">需要补发的数据</param>
        void SwitchToConnection(int connId, uint serverSeq, byte[][] pendingData);

        /// <summary>关闭旧连接（迁移成功后的清理）</summary>
        void CloseOldConnection();

        /// <summary>发送原始字节到指定连接</summary>
        void SendRaw(int connId, byte[] data);

        /// <summary>尝试从指定连接接收 MIGRATE_ACK，无数据时返回 null</summary>
        MigrateAck TryReceiveMigrateAck(int connId);
    }

    /// <summary>服务器返回的迁移确认</summary>
    public class MigrateAck
    {
        public bool Accepted;
        public uint ServerSeq;
        public byte[][] PendingData;   // 旧连接未确认的消息（可为空）
        public string RejectReason;    // 拒绝原因（Accepted=false 时有效）
    }
}
```

**代码要点解释**：

1. **消抖机制 (Debounce)**：网络状态可能在短时间内多次抖动（如 WiFi 和 4G 之间来回切换）。`_debounceSeconds = 0.5s` 确保只在稳定变化后才触发迁移，避免创建大量无效连接。

2. **指数退避重试**：`200ms → 400ms → 800ms`，3 次重试总耗时约 1.4 秒内——玩家可感知但不会丧失耐心。如果服务器无响应（而非拒绝），退避可以减少服务器压力。

3. **Session Token 安全性**：Token 必须由服务器生成并签名（HMAC），包含 `playerId + connectTime + serverSecret`。客户端不应能伪造有效的 token。服务器验证时检查 HMAC 和时间窗口（token 有效期通常 5 分钟）。

4. **pending_data 机制**：迁移期间（约 500ms），服务器可能已经向旧 IP 发送了数据。`pendingData` 包含了最后确认序列号之后的所有服务器→客户端消息，确保迁移不丢数据。

### 2.4 C++: SessionMigration — 服务端 Session 管理（完整实现）

```cpp
// SessionMigration.h — 服务端连接迁移 / Session 管理
// 适用于 C++ 自定义服务器（无引擎依赖）
// 依赖: <unordered_map>, <memory>, <chrono>, <functional>
//
// 核心职责:
//   1. 管理所有活跃的 PlayerSession
//   2. 处理客户端的 MIGRATE 请求
//   3. 旧连接保活（等待新连接接管）
//   4. 僵尸 Session 清理

#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
#include <memory>
#include <chrono>
#include <functional>
#include <mutex>

namespace GameServer {

// ─── 基础类型 ─────────────────────────────────────────────────

using SocketHandle = int32_t;
constexpr SocketHandle INVALID_SOCKET = -1;

/// 网络地址 (IP + Port)
struct NetAddress {
    uint32_t ip;    // 网络字节序 IPv4
    uint16_t port;  // 网络字节序
};

// ─── Session 状态 ─────────────────────────────────────────────

enum class SessionState : uint8_t {
    Active,          // 正常通信中
    Suspending,      // 等待新连接接管 (旧连接可能已断)
    Migrated,        // 已迁移到新连接，旧连接待清理
    Disconnected,    // 已断线（等待重连窗口）
    Zombie,          // 僵尸 Session（超时未重连，等待清理）
};

// ─── Session Token ────────────────────────────────────────────

/// Session Token: 服务器为每个会话生成的唯一迁移令牌
/// 格式: 12 字节随机数 + 4 字节过期时间戳 + 16 字节 HMAC
struct SessionToken {
    static constexpr size_t TOKEN_SIZE = 32;
    uint8_t data[TOKEN_SIZE];

    /// 从二进制字符串创建
    static SessionToken FromBytes(const uint8_t* bytes, size_t len);

    /// 转为 Base64 字符串（用于传输）
    std::string ToBase64() const;

    bool operator==(const SessionToken& other) const {
        return memcmp(data, other.data, TOKEN_SIZE) == 0;
    }
};

// ─── PlayerSession ────────────────────────────────────────────

/// 服务端维护的单个玩家会话。
/// 包含连接信息、Token、消息队列和迁移状态。
class PlayerSession {
public:
    PlayerSession(uint64_t sessionId, uint64_t playerId)
        : session_id_(sessionId)
        , player_id_(playerId)
        , state_(SessionState::Active)
        , socket_(INVALID_SOCKET)
        , last_activity_(std::chrono::steady_clock::now())
        , last_acked_seq_(0)
        , server_send_seq_(0)
    {}

    // ─── 属性访问 ─────────────────────────────────────────

    uint64_t session_id()    const { return session_id_; }
    uint64_t player_id()     const { return player_id_; }
    SessionState state()     const { return state_; }
    SocketHandle socket()    const { return socket_; }
    uint32_t last_acked_seq() const { return last_acked_seq_; }
    uint32_t server_send_seq() const { return server_send_seq_; }

    const SessionToken& token() const { return token_; }

    // ─── 状态转换 ─────────────────────────────────────────

    /// 绑定网络连接（首次连接或新连接绑定）
    void BindSocket(SocketHandle newSocket, const NetAddress& addr) {
        socket_ = newSocket;
        address_ = addr;
        last_activity_ = std::chrono::steady_clock::now();
    }

    /// 设置迁移 Token（只在首次认证时调用）
    void SetToken(const SessionToken& token) {
        token_ = token;
    }

    /// 标记为等待迁移（旧连接即将断开）
    void MarkSuspending() {
        state_ = SessionState::Suspending;
        suspending_since_ = std::chrono::steady_clock::now();
    }

    /// 迁移完成：绑定新 socket 到本 Session
    void CompleteMigration(SocketHandle newSocket, const NetAddress& newAddr) {
        socket_ = newSocket;
        address_ = newAddr;
        state_ = SessionState::Migrated;
        last_activity_ = std::chrono::steady_clock::now();
    }

    /// 标记断线
    void MarkDisconnected() {
        state_ = SessionState::Disconnected;
        disconnected_since_ = std::chrono::steady_clock::now();
    }

    /// 标记为僵尸（用于清理）
    void MarkZombie() {
        state_ = SessionState::Zombie;
    }

    // ─── 消息队列 ─────────────────────────────────────────

    /// 向待发送队列添加消息
    void EnqueueMessage(std::vector<uint8_t> message) {
        pending_messages_.push_back(std::move(message));
        server_send_seq_++;
    }

    /// 取出所有待发送消息并清空队列
    std::vector<std::vector<uint8_t>> DrainPendingMessages() {
        std::vector<std::vector<uint8_t>> result;
        result.swap(pending_messages_);
        return result;
    }

    /// 获取从指定序列号之后的所有已发送消息（用于补发）
    std::vector<std::vector<uint8_t>> GetMessagesAfter(uint32_t afterSeq) const {
        // 注：生产级实现需要一个已发送消息的环形缓冲区
        // 这里简化处理，返回空列表
        return {};
    }

    // ─── 超时检查 ─────────────────────────────────────────

    /// 检查 Session 是否已过期（僵尸清理）
    /// @param timeoutMs 超时时间（毫秒）
    /// @return true 表示可以被安全清理
    bool IsExpired(int64_t timeoutMs) const {
        if (state_ == SessionState::Zombie) return true;

        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - last_activity_).count();
        return elapsed > timeoutMs;
    }

    /// 检查 Suspending 状态是否超时（等待迁移时间过长）
    bool IsSuspendingTimeout(int64_t timeoutMs) const {
        if (state_ != SessionState::Suspending) return false;
        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - suspending_since_).count();
        return elapsed > timeoutMs;
    }

    void UpdateActivity() {
        last_activity_ = std::chrono::steady_clock::now();
    }

private:
    uint64_t      session_id_;
    uint64_t      player_id_;
    SessionState  state_;
    SocketHandle  socket_;
    NetAddress    address_;
    SessionToken  token_;

    std::chrono::steady_clock::time_point last_activity_;
    std::chrono::steady_clock::time_point suspending_since_;
    std::chrono::steady_clock::time_point disconnected_since_;

    uint32_t last_acked_seq_;       // 客户端最后确认的序列号
    uint32_t server_send_seq_;      // 服务器发送的最后序列号

    std::vector<std::vector<uint8_t>> pending_messages_; // 待发送消息队列
};

// ─── SessionMigrationManager ──────────────────────────────────

/// 管理所有 PlayerSession 的生命周期和迁移逻辑。
/// 线程安全：内部使用互斥锁保护所有共享状态。
///
/// 使用方式:
///   SessionMigrationManager mgr;
///   mgr.Initialize(secretKey, 30000, 600000);
///
///   // 每帧调用
///   mgr.ProcessMigrationRequests();  // 处理收到的 MIGRATE 包
///   mgr.CleanupZombieSessions();     // 清理超时的僵尸 Session
class SessionMigrationManager {
public:
    using SessionPtr = std::shared_ptr<PlayerSession>;

    SessionMigrationManager()
        : suspending_timeout_ms_(30000)   // Suspending 超时: 30 秒
        , zombie_timeout_ms_(600000)      // Zombie 超时: 10 分钟
        , next_session_id_(1)
    {}

    /// 初始化
    /// @param secretKey 用于 HMAC 签名的密钥（至少 16 字节）
    /// @param suspendingTimeoutMs Suspending 状态超时（毫秒）
    /// @param zombieTimeoutMs Zombie Session 超时（毫秒）
    void Initialize(std::string_view secretKey,
                    int64_t suspendingTimeoutMs,
                    int64_t zombieTimeoutMs)
    {
        secret_key_.assign(secretKey.begin(), secretKey.end());
        suspending_timeout_ms_ = suspendingTimeoutMs;
        zombie_timeout_ms_ = zombieTimeoutMs;
    }

    // ─── Session 生命周期 ──────────────────────────────────

    /// 为新连接的玩家创建 Session 并生成 Token
    SessionPtr CreateSession(uint64_t playerId, SocketHandle socket,
                             const NetAddress& addr)
    {
        std::lock_guard<std::mutex> lock(mutex_);

        uint64_t sessionId = next_session_id_++;
        auto session = std::make_shared<PlayerSession>(sessionId, playerId);
        session->BindSocket(socket, addr);
        session->SetToken(GenerateToken(sessionId, playerId));

        sessions_by_id_[sessionId] = session;
        sessions_by_player_[playerId] = session;  // 覆盖旧 Session（如果有）

        return session;
    }

    /// 处理客户端的 MIGRATE 请求
    ///
    /// 流程:
    ///   1. 验证 Token → 找到对应的 PlayerSession
    ///   2. 如果旧连接还在 → 将其标记为 Suspending
    ///   3. 将新 socket 绑定到旧 Session → 完成迁移
    ///   4. 返回需要补发的消息
    ///
    /// @param tokenBytes Token 的二进制表示
    /// @param oldAckedSeq 客户端最后确认的序列号
    /// @param newSocket 新连接的 socket handle
    /// @param newAddr 新连接的地址
    /// @return {true, pendingMessages} 成功; {false, {}} Token 无效或 Session 不存在
    struct MigrateResult {
        bool accepted;
        uint32_t serverSeq;                            // 服务器当前序列号
        std::vector<std::vector<uint8_t>> pendingData; // 需补发的消息
        std::string rejectReason;
    };

    MigrateResult HandleMigrateRequest(
        const uint8_t* tokenBytes, size_t tokenLen,
        uint32_t oldAckedSeq,
        SocketHandle newSocket, const NetAddress& newAddr)
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // 1. 解析并验证 Token
        SessionToken token = SessionToken::FromBytes(tokenBytes, tokenLen);
        auto session = FindSessionByToken(token);
        if (!session) {
            return {false, 0, {}, "Invalid or expired session token"};
        }

        // 2. 检查 Session 是否还活跃
        if (session->state() == SessionState::Zombie) {
            return {false, 0, {}, "Session has expired"};
        }

        // 3. 获取需要补发的消息（从 oldAckedSeq+1 开始）
        auto pendingData = session->GetMessagesAfter(oldAckedSeq);

        // 4. 将旧 socket 标记为 Suspending
        session->MarkSuspending();

        // 5. 绑定新 socket 到 Session（完成迁移）
        session->CompleteMigration(newSocket, newAddr);

        return {
            true,
            session->server_send_seq(),
            std::move(pendingData),
            ""
        };
    }

    /// 根据 Token 查找 Session
    SessionPtr FindSessionByToken(const SessionToken& token) {
        for (auto& [id, session] : sessions_by_id_) {
            if (session->token() == token) {
                return session;
            }
        }
        return nullptr;
    }

    /// 根据 PlayerId 查找 Session
    SessionPtr FindSessionByPlayer(uint64_t playerId) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_by_player_.find(playerId);
        if (it != sessions_by_player_.end()) {
            return it->second;
        }
        return nullptr;
    }

    /// 移除 Session（玩家主动退出或超时清理）
    void RemoveSession(uint64_t sessionId) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = sessions_by_id_.find(sessionId);
        if (it != sessions_by_id_.end()) {
            sessions_by_player_.erase(it->second->player_id());
            sessions_by_id_.erase(it);
        }
    }

    // ─── 定时任务 ──────────────────────────────────────────

    /// 每帧/每 tick 调用：处理 Suspending 超时的 Session
    /// 如果 Suspending 状态下长时间没有新连接接管，将 Session 降级为 Disconnected
    void ProcessSuspendingTimeouts() {
        std::lock_guard<std::mutex> lock(mutex_);

        for (auto& [id, session] : sessions_by_id_) {
            if (session->IsSuspendingTimeout(suspending_timeout_ms_)) {
                session->MarkDisconnected();
            }
        }
    }

    /// 定期调用（如每秒一次）：清理僵尸 Session
    void CleanupZombieSessions() {
        std::lock_guard<std::mutex> lock(mutex_);

        auto it = sessions_by_id_.begin();
        while (it != sessions_by_id_.end()) {
            auto& session = it->second;
            if (session->IsExpired(zombie_timeout_ms_)) {
                sessions_by_player_.erase(session->player_id());
                it = sessions_by_id_.erase(it);
            } else {
                ++it;
            }
        }
    }

    /// 获取活跃 Session 数（用于监控）
    size_t ActiveSessionCount() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return sessions_by_id_.size();
    }

private:
    // ─── Token 生成 ────────────────────────────────────────

    SessionToken GenerateToken(uint64_t sessionId, uint64_t playerId) {
        // 简化实现: 生产级应使用 HMAC-SHA256
        // Token = HMAC(secretKey, sessionId || playerId || expireTime)
        SessionToken token = {};
        // ... 实际 HMAC 计算省略 ...
        return token;
    }

    // ─── 成员 ──────────────────────────────────────────────

    std::unordered_map<uint64_t, SessionPtr> sessions_by_id_;
    std::unordered_map<uint64_t, SessionPtr> sessions_by_player_; // playerId → Session

    std::vector<uint8_t> secret_key_;
    int64_t suspending_timeout_ms_;
    int64_t zombie_timeout_ms_;

    uint64_t next_session_id_;

    mutable std::mutex mutex_;
};

} // namespace GameServer
```

**代码要点解释**：

1. **Suspending 状态**：旧连接断开但新连接还未到达的窗口期。服务器不会立即清理 Session，而是保留一个宽限期（`suspending_timeout_ms_`，默认 30 秒）。这允许客户端在网络切换（WiFi→4G）的间隙内完成迁移。

2. **Zombie 清理**：Session 在 Disconnected 状态超过 10 分钟（`zombie_timeout_ms_`）后标记为 Zombie 并清理。10 分钟远长于典型的对局时长（15-30 分钟），确保玩家在网络恢复后能够重连。

3. **Token HMAC 验证**：生产级实现必须使用 HMAC-SHA256 对 Token 签名，防止伪造。Token 包含 `{sessionId, playerId, expireTime}` + HMAC 签名。服务器验证时检查签名和时间戳。

4. **消息补发**：`GetMessagesAfter()` 需要服务端维护一个**已发送消息的环形缓冲区**（类似帧同步的帧包环形缓冲区），按序列号索引。当迁移请求携带 `oldAckedSeq`，服务器从中找到所有未确认的消息并补发。

---

## 3. 多链路加速

### 3.1 核心技术选型

多链路加速允许游戏同时使用 WiFi 和蜂窝网络（4G/5G），提升弱网环境下的可靠性。有三种主流方案：

| 方案 | 原理 | 优点 | 缺点 | 游戏适用性 |
|------|------|------|------|-----------|
| **MP-TCP** | 传输层多路径 TCP | OS 内核支持, 对应用透明 | 需要两端都支持; 中间盒可能阻断 | 低 (内核依赖, 跨平台差) |
| **MP-QUIC** | QUIC 扩展的多路径 | 应用层实现, 灵活 | 标准未定, 库不成熟 | 中 (未来有前景) |
| **应用层冗余** | 应用层手动双链路发送 | 完全自主控制, 无需内核支持 | CPU 开销翻倍, 带宽翻倍 | **高 (当前最佳实践)** |

**游戏场景推荐应用层冗余方案**，理由：
- 游戏带宽本身不大（通常 5-20KB/s），双发带宽开销可接受
- 可以精细控制哪些包双发（关键帧指令双发，非关键属性单发）
- 无需修改 OS/内核，跨平台一致

### 3.2 冗余策略与分流策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    应用层多链路加速架构                            │
│                                                                  │
│  发送端                                                          │
│  ┌──────────────────────────────────────────────────┐           │
│  │              包分流决策引擎                        │           │
│  │                                                   │           │
│  │   incoming_packet ──► classify ──┬── critical ──► 双链路都发│
│  │                                  ├── large ────► WiFi       │
│  │                                  ├── small ────► 4G/5G      │
│  │                                  └── heartbeat ─► 两条都发  │
│  │                                                   │           │
│  │   WiFi 链路 ───► Socket_A                         │           │
│  │   4G 链路  ───► Socket_B                          │           │
│  └──────────────────────────────────────────────────┘           │
│                                                                  │
│  接收端                                                          │
│  ┌──────────────────────────────────────────────────┐           │
│  │              去重 & 合并引擎                       │           │
│  │                                                   │           │
│  │   Socket_A ──► buffer_A ──┐                      │           │
│  │                            ├──► Dedup ──► 业务层 │           │
│  │   Socket_B ──► buffer_B ──┘                      │           │
│  │                                                   │           │
│  │   去重依据: (seq_number, link_id)                 │           │
│  │   到达策略: 先到先处理 + 丢弃重复                  │           │
│  └──────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

**冗余策略细则**：

| 包类型 | 大小 | 频率 | 策略 | 理由 |
|--------|------|------|------|------|
| 帧输入指令 (帧同步) | 20-100B | 15-30 fps | 双链路都发 | 丢失一帧 = desync 风险 |
| 关键 RPC (开火/技能) | 30-150B | 事件驱动 | 双链路都发 | 不能丢，延迟敏感 |
| 状态更新 (HP/位置) | 50-200B | 10-60 tick | 单发，走延迟较低的链路 | 下一次更新会覆盖 |
| 大包 (聊天图片/快照) | >1KB | 偶尔 | 分流：大包 WiFi，小包 4G | 节省蜂窝流量 |
| 心跳 | 5-10B | 1-5s | 两条都发 | 任一链路断即时检测 |

### 3.3 去重机制

去重的关键是**全局唯一的包序列号**。序列号在发送端分配，接收端维护一个"已确认窗口"：

```csharp
// 简单去重队列实现（约 30 行）
public class PacketDeduplicator {
    // 使用位图记录最近 1024 个序列号的到达状态
    private readonly BitArray _receivedMap = new(1024);
    private uint _maxReceivedSeq = 0;

    /// <summary>检查包是否已收到。未收到则标记，返回 true。</summary>
    public bool TryMarkReceived(uint seq) {
        // 太老的包——直接丢弃
        if (seq + 1024 < _maxReceivedSeq)
            return false;

        // 新包——扩展窗口
        if (seq > _maxReceivedSeq) {
            // 滑动窗口：清空中间的位
            int shift = (int)(seq - _maxReceivedSeq);
            if (shift < 1024) {
                // 左移位图（生产级实现优化方向：用循环位图避免移位开销）
                for (int i = 0; i < 1024 - shift; i++)
                    _receivedMap[i] = _receivedMap[i + shift];
                for (int i = 1024 - shift; i < 1024; i++)
                    _receivedMap[i] = false;
            } else {
                _receivedMap.SetAll(false);
            }
            _maxReceivedSeq = seq;
        }

        // 计算位图索引
        int index = (int)(_maxReceivedSeq - seq);
        if (index >= 1024 || _receivedMap[index])
            return false; // 已收到

        _receivedMap[index] = true;
        return true;
    }
}
```

**去重不是简单的 HashSet**——因为：
- 内存无界增长：游戏可能持续数小时，序列号可能到百万级。HashSet 会无限膨胀。
- 乱序容忍：双链路到达顺序不可预测。滑动窗口机制天然支持乱序（窗口内的任意序列号都可正确去重）。

---

## 4. 带宽自适应

### 4.1 动态调整同步频率

核心思路：**根据网络质量的实时监测结果，动态调整同步策略，而不是用一个固定配置应对所有网络环境。**

```
┌─────────────────────────────────────────────────────────────────┐
│                    带宽自适应系统架构                              │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐      │
│  │  网络监测     │────►│  策略决策     │────►│  同步执行     │      │
│  │  Monitor     │     │  Controller  │     │  Actuator    │      │
│  │              │     │              │     │              │      │
│  │ RTT 滑动平均 │     │ 阈值→策略映射 │     │ 调整发送频率 │      │
│  │ 丢包率 EWMA  │     │ 平滑过渡     │     │ 调整量化位数 │      │
│  │ 抖动 Jitter  │     │ 防抖 Hysteresis│   │ 调整 LOD 级别│      │
│  │ 带宽估计     │     │ 快速恢复机制 │     │ 调整冗余度   │      │
│  └──────────────┘     └──────────────┘     └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

四种主要自适应维度：

| 维度 | 正常网络 | 轻度弱网 | 中度弱网 | 重度弱网 |
|------|---------|---------|---------|---------|
| **同步频率** | 20Hz (50ms) | 15Hz (66ms) | 10Hz (100ms) | 5Hz (200ms) |
| **浮点精度** | float32 | float32 | 半精度(16bit) | 量化(12bit) |
| **LOD 级别** | 全部属性 | 位置+速率+朝向 | 仅位置+HP | 仅关键属性 |
| **冗余发送** | 无 | 关键包 ×2 | 全部包 ×2 | 全部包 ×3 |
| **带宽目标** | <30KB/s | <20KB/s | <10KB/s | <5KB/s |

### 4.2 C#: BandwidthAdaptiveSync（完整实现）

```csharp
// BandwidthAdaptiveSync.cs — 带宽自适应同步控制器
// 适用于 Unity/C# 状态同步客户端或服务端
// 依赖: 无外部依赖（纯 C# 实现）

using System;
using System.Collections.Generic;

namespace GameNetwork.Adaptive
{
    /// <summary>
    /// 网络质量等级枚举。
    /// 对应第一节的弱网分级标准。
    /// </summary>
    public enum NetworkQualityLevel
    {
        Excellent,   // RTT < 50ms,  Loss < 1%
        Good,        // RTT 50-100ms, Loss 1-3%
        Fair,        // RTT 100-200ms, Loss 3-8%
        Poor,        // RTT 200-400ms, Loss 8-20%
        Critical     // RTT > 400ms or Loss > 20%
    }

    /// <summary>
    /// 同步配置参数（每种网络质量级别对应一组参数）。
    /// </summary>
    [Serializable]
    public struct SyncConfig
    {
        public float syncInterval;        // 同步间隔（秒），如 0.05 = 20Hz
        public int   quantizationBits;   // 位置量化位数（32 = 全精度 float, 16 = 半精度）
        public int   redundancyFactor;   // 冗余发送倍数（1 = 无冗余, 2 = 双发, 3 = 三发）
        public int   maxBytesPerPacket;  // 单包最大字节数
        public float interpolationDelay; // 插值延迟（秒），弱网时增大缓冲
        public bool  sendVelocity;       // 是否发送速度（用于外推）
        public bool  sendRotation;       // 是否发送旋转
        public bool  sendFullState;      // 是否发送全量状态（vs 仅脏数据）

        public static SyncConfig ForLevel(NetworkQualityLevel level)
        {
            return level switch
            {
                NetworkQualityLevel.Excellent => new SyncConfig {
                    syncInterval = 0.05f, quantizationBits = 32,
                    redundancyFactor = 1, maxBytesPerPacket = 1200,
                    interpolationDelay = 0.05f, sendVelocity = true,
                    sendRotation = true, sendFullState = false
                },
                NetworkQualityLevel.Good => new SyncConfig {
                    syncInterval = 0.066f, quantizationBits = 32,
                    redundancyFactor = 1, maxBytesPerPacket = 1000,
                    interpolationDelay = 0.08f, sendVelocity = true,
                    sendRotation = true, sendFullState = false
                },
                NetworkQualityLevel.Fair => new SyncConfig {
                    syncInterval = 0.1f, quantizationBits = 16,
                    redundancyFactor = 2, maxBytesPerPacket = 800,
                    interpolationDelay = 0.15f, sendVelocity = true,
                    sendRotation = false, sendFullState = false
                },
                NetworkQualityLevel.Poor => new SyncConfig {
                    syncInterval = 0.2f, quantizationBits = 12,
                    redundancyFactor = 2, maxBytesPerPacket = 600,
                    interpolationDelay = 0.3f, sendVelocity = false,
                    sendRotation = false, sendFullState = false
                },
                NetworkQualityLevel.Critical => new SyncConfig {
                    syncInterval = 0.5f, quantizationBits = 12,
                    redundancyFactor = 3, maxBytesPerPacket = 400,
                    interpolationDelay = 0.5f, sendVelocity = false,
                    sendRotation = false, sendFullState = true
                },
                _ => throw new ArgumentOutOfRangeException()
            };
        }
    }

    /// <summary>
    /// 网络质量统计数据结构。
    /// 由外部网络层更新，供自适应控制器读取。
    /// </summary>
    public struct NetworkStats
    {
        public float rttMs;              // 当前 RTT (指数移动平均)
        public float lossRate;           // 丢包率 (0.0 ~ 1.0, EWMA)
        public float jitterMs;           // RTT 抖动 (标准差近似)
        public float bandwidthEstimate;  // 估计可用带宽 (bytes/s)
        public long  packetsSent;        // 累计发送包数
        public long  packetsLost;        // 累计丢包数
    }

    /// <summary>
    /// 带宽自适应同步控制器。
    ///
    /// 核心逻辑:
    ///   1. 从网络层读取 NetworkStats（RTT, 丢包率, 抖动）
    ///   2. 根据阈值判定网络质量级别
    ///   3. 带迟滞 (hysteresis) 切换配置，避免频繁抖动
    ///   4. 输出当前应使用的 SyncConfig
    ///
    /// 使用方式:
    ///   var controller = new BandwidthAdaptiveController();
    ///   controller.Update(stats);
    ///   var config = controller.CurrentConfig;
    ///   if (Time.time - lastSyncTime >= config.syncInterval) { ... }
    /// </summary>
    public class BandwidthAdaptiveController
    {
        // ─── 阈值配置 ─────────────────────────────────────────
        // 使用 RTT 和丢包率的组合判定，而非单一指标

        private const float ExcellentRttMax = 50f;
        private const float GoodRttMax = 100f;
        private const float FairRttMax = 200f;
        private const float PoorRttMax = 400f;

        private const float ExcellentLossMax = 0.01f;
        private const float GoodLossMax = 0.03f;
        private const float FairLossMax = 0.08f;
        private const float PoorLossMax = 0.20f;

        // ─── 迟滞 (Hysteresis) ───────────────────────────────
        // 升级阈值（变差时快速响应） vs 降级阈值（变好时缓慢确认）
        // 目的: 避免短暂网络恢复后立即切回高频率，又马上降级的振荡

        private const float HysteresisRttUpgrade = 0.80f;   // RTT 降到阈值*0.8 才能升级
        private const float HysteresisLossUpgrade = 0.70f;  // 丢包率降到阈值*0.7 才能升级

        private const float HysteresisRttDowngrade = 1.0f;  // RTT 达到阈值立即降级（快速响应变差）
        private const float HysteresisLossDowngrade = 1.0f; // 丢包率达到阈值立即降级

        // ─── 平滑过渡 ─────────────────────────────────────────
        // 配置变化不是瞬时切换，而是在 2 秒内逐步过渡
        // 避免 syncInterval 突变导致的突发流量

        private const float TransitionDuration = 2.0f; // 过渡时长（秒）

        // ─── 状态 ─────────────────────────────────────────────
        private NetworkQualityLevel _currentLevel = NetworkQualityLevel.Excellent;
        private SyncConfig _currentConfig;
        private SyncConfig _targetConfig;
        private float _transitionStartTime;
        private bool _isTransitioning;

        /// <summary>当前有效的同步配置（可能在过渡中，取插值）</summary>
        public SyncConfig CurrentConfig => _currentConfig;

        /// <summary>当前网络质量级别</summary>
        public NetworkQualityLevel CurrentLevel => _currentLevel;

        // ─── 构造函数 ─────────────────────────────────────────
        public BandwidthAdaptiveController()
        {
            _currentConfig = SyncConfig.ForLevel(NetworkQualityLevel.Excellent);
            _targetConfig = _currentConfig;
        }

        /// <summary>
        /// 每帧/每 tick 调用。传入最新网络统计，输出自适应配置。
        /// 调用频率建议: 1-4 Hz（不需要每帧调用，网络统计变化本身是秒级的）。
        /// </summary>
        public void Update(in NetworkStats stats)
        {
            // 1. 根据当前统计判定目标级别
            NetworkQualityLevel targetLevel = ClassifyNetwork(stats);

            // 2. 应用迟滞
            NetworkQualityLevel adjustedLevel = ApplyHysteresis(targetLevel, stats);

            // 3. 如果级别变化，开始平滑过渡
            if (adjustedLevel != _currentLevel)
            {
                _targetConfig = SyncConfig.ForLevel(adjustedLevel);
                _transitionStartTime = UnityEngine.Time.time;
                _isTransitioning = true;
                _currentLevel = adjustedLevel;
            }

            // 4. 如果正在过渡，计算插值
            if (_isTransitioning)
            {
                float elapsed = UnityEngine.Time.time - _transitionStartTime;
                float t = Math.Min(elapsed / TransitionDuration, 1.0f);

                // 使用 SmoothStep 让过渡更自然
                t = t * t * (3f - 2f * t);

                _currentConfig = LerpConfig(_currentConfig, _targetConfig, t);

                if (t >= 1.0f)
                {
                    _currentConfig = _targetConfig;
                    _isTransitioning = false;
                }
            }
        }

        /// <summary>
        /// 根据 RTT + 丢包率判定网络质量级别。
        /// 取两者中更差的结果（"木桶原理"：差指标决定玩家体验）。
        /// </summary>
        private NetworkQualityLevel ClassifyNetwork(in NetworkStats stats)
        {
            NetworkQualityLevel rttLevel = stats.rttMs switch
            {
                <= ExcellentRttMax => NetworkQualityLevel.Excellent,
                <= GoodRttMax      => NetworkQualityLevel.Good,
                <= FairRttMax      => NetworkQualityLevel.Fair,
                <= PoorRttMax      => NetworkQualityLevel.Poor,
                _                  => NetworkQualityLevel.Critical
            };

            NetworkQualityLevel lossLevel = stats.lossRate switch
            {
                <= ExcellentLossMax => NetworkQualityLevel.Excellent,
                <= GoodLossMax      => NetworkQualityLevel.Good,
                <= FairLossMax      => NetworkQualityLevel.Fair,
                <= PoorLossMax      => NetworkQualityLevel.Poor,
                _                   => NetworkQualityLevel.Critical
            };

            // 取更差的结果
            return (NetworkQualityLevel)Math.Max((int)rttLevel, (int)lossLevel);
        }

        /// <summary>
        /// 应用迟滞过滤：
        ///   - 降级（变差）：立即生效
        ///   - 升级（变好）：需要持续满足阈值一段时间
        ///
        /// 实现方式：升级时使用更严格的阈值（RTT*0.8, Loss*0.7）。
        /// 实际生产中更推荐"持续 N 秒稳定才升级"的时间窗口法。
        /// </summary>
        private NetworkQualityLevel ApplyHysteresis(
            NetworkQualityLevel targetLevel, in NetworkStats stats)
        {
            if ((int)targetLevel < (int)_currentLevel)
            {
                // 升级（网络变好）：需要更严格的阈值
                float rttThreshold = GetRttThreshold(targetLevel) * HysteresisRttUpgrade;
                float lossThreshold = GetLossThreshold(targetLevel) * HysteresisLossUpgrade;

                if (stats.rttMs > rttThreshold || stats.lossRate > lossThreshold)
                {
                    // 虽然 RTT/丢包率达标了，但还不够稳定，维持当前级别
                    return _currentLevel;
                }
            }

            // 降级（网络变差）或满足升级条件
            return targetLevel;
        }

        private float GetRttThreshold(NetworkQualityLevel level) => level switch
        {
            NetworkQualityLevel.Excellent => ExcellentRttMax,
            NetworkQualityLevel.Good      => GoodRttMax,
            NetworkQualityLevel.Fair      => FairRttMax,
            NetworkQualityLevel.Poor      => PoorRttMax,
            _                             => float.MaxValue
        };

        private float GetLossThreshold(NetworkQualityLevel level) => level switch
        {
            NetworkQualityLevel.Excellent => ExcellentLossMax,
            NetworkQualityLevel.Good      => GoodLossMax,
            NetworkQualityLevel.Fair      => FairLossMax,
            NetworkQualityLevel.Poor      => PoorLossMax,
            _                             => 1.0f
        };

        /// <summary>
        /// 在两个 SyncConfig 之间线性插值。
        /// 主要对浮点参数插值，整型参数在过渡中点处切换。
        /// </summary>
        private static SyncConfig LerpConfig(SyncConfig from, SyncConfig to, float t)
        {
            return new SyncConfig
            {
                syncInterval = Mathf.Lerp(from.syncInterval, to.syncInterval, t),
                quantizationBits = t < 0.5f ? from.quantizationBits : to.quantizationBits,
                redundancyFactor = t < 0.5f ? from.redundancyFactor : to.redundancyFactor,
                maxBytesPerPacket = (int)Mathf.Lerp(from.maxBytesPerPacket, to.maxBytesPerPacket, t),
                interpolationDelay = Mathf.Lerp(from.interpolationDelay, to.interpolationDelay, t),
                sendVelocity = t < 0.5f ? from.sendVelocity : to.sendVelocity,
                sendRotation = t < 0.5f ? from.sendRotation : to.sendRotation,
                sendFullState = t < 0.5f ? from.sendFullState : to.sendFullState,
            };
        }
    }
}
```

**代码要点解释**：

1. **迟滞 (Hysteresis)**：这是自适应系统最关键的设计细节。无迟滞的系统会在阈值边界频繁振荡——网络在 95ms-105ms 之间抖动时，每 2 秒切换一次配置，导致体验比固定配置更差。迟滞确保**降级快、升级慢**——网络变差时 0 秒响应（立即降低频率），网络变好时需持续 3-5 秒稳定才会提升频率。

2. **平滑过渡**：`syncInterval` 从 0.05s 突变到 0.2s 会导致一瞬间的"静默"。2 秒的 SmoothStep 过渡使玩家感受不到参数切换。

3. **RTT + 丢包率的"木桶"判定**：使用两者中更差的结果。因为即使 RTT=30ms（优秀），丢包率=15% 时体验也很差。单看 RTT 会导致误判。

4. **量化位数对应关系**：32bit = 全精度 float，16bit = 半精度 (约 3.3 位有效数字)，12bit = 量化编码 (约 0.01 精度)。12bit 时 3D 坐标从 12 字节压缩到约 4.5 字节。

---

## 5. 弱网心跳与保活

### 5.1 TCP keepalive 的局限

TCP 协议内置的 keepalive 机制对游戏场景存在严重不足：

| 特性 | TCP Keepalive | 游戏需要的 |
|------|--------------|-----------|
| 默认间隔 | 7200 秒（2 小时！） | 1-5 秒 |
| 最小间隔 (Linux) | `tcp_keepalive_time` 可调到 1 秒 | 需要应用层实现 |
| 探测包大小 | 0 字节（纯 ACK 包） | 携带游戏状态（序列号、时间戳） |
| 断线检测延迟 | keepalive_retry × keepalive_interval（默认约 11 分钟） | 3-10 秒 |
| NAT 穿透 | 某些 NAT 设备会丢弃纯 ACK 包 | 携带 payload 的心跳包不会被丢 |

**结论：不要依赖 TCP keepalive。必须实现应用层心跳。**

### 5.2 应用层心跳：自适应间隔

固定的心跳间隔（如"每秒一次"）在弱网环境下有两个问题：
- 正常网络：1 秒间隔浪费带宽（心跳包虽然小，但对于数千并发玩家，服务端 CPU 处理心跳的开销不可忽略）
- 重度弱网：1 秒间隔不够——在 30% 丢包率下，1 秒间隔的心跳有 45% 的概率连续 2 个包丢失（导致误判断线）

**自适应心跳策略**：

```
正常网络 (RTT<50ms, Loss<1%):
  心跳间隔: 5 秒
  断线判定: 连续 3 次心跳无 ACK → 断线 (15 秒检测延迟)

轻度弱网 (RTT 50-150ms, Loss 1-5%):
  心跳间隔: 3 秒
  断线判定: 连续 3 次无 ACK → 断线 (9 秒检测延迟)
  额外: 每次收到任何业务包都重置心跳计时器（"业务包也是心跳"）

中度弱网 (RTT 150-300ms, Loss 5-15%):
  心跳间隔: 1.5 秒
  断线判定: 连续 4 次无 ACK → 断线 (6 秒检测延迟)
  额外: 心跳包走双链路（如果多链路可用）

重度弱网 (RTT>300ms, Loss>15%):
  心跳间隔: 0.5 秒
  断线判定: 连续 5 次无 ACK → 断线 (2.5 秒检测延迟，更激进)
  注意: 此时已经濒临断线，增加心跳频率是为精确判断"什么时候彻底断开"
```

### 5.3 Lua: heart_beat.lua（完整实现）

```lua
-- ============================================
-- heart_beat.lua — 自适应心跳与断线检测
-- ============================================
-- 功能:
--   1. 自适应心跳间隔（根据网络质量动态调整）
--   2. 快速断线检测（连续丢包计数 + 超时）
--   3. 业务包复用（收到任何数据都视为心跳响应）
--   4. 断线事件通知（供上层模块处理重连/降级）
--
-- 依赖: 需要 C 引擎绑定提供以下接口:
--   engine.get_current_time_ms() → number  获取当前时间戳(ms)
--   engine.socket_send(sock, data, len) → number  发送数据
--   engine.get_network_stats() → {rtt, loss_rate}  获取网络统计
-- ============================================

local HeartBeat = {}
HeartBeat.__index = HeartBeat

-- ─── 网络质量级别对应的参数 ────────────────────────────
-- 格式: { heartbeat_interval_ms, max_missed_beats, min_rtt_ms, max_rtt_ms, max_loss_rate }
local QUALITY_PARAMS = {
    -- 正常
    { interval = 5000, missed = 3, rtt_min = 0,   rtt_max = 50,  loss_max = 0.01 },
    -- 轻度弱网
    { interval = 3000, missed = 3, rtt_min = 50,  rtt_max = 150, loss_max = 0.05 },
    -- 中度弱网
    { interval = 1500, missed = 4, rtt_min = 150, rtt_max = 300, loss_max = 0.15 },
    -- 重度弱网
    { interval = 500,  missed = 5, rtt_min = 300, rtt_max = 800, loss_max = 0.30 },
    -- 濒临断线
    { interval = 300,  missed = 6, rtt_min = 800, rtt_max = 999999, loss_max = 1.0 },
}

-- ─── 构造函数 ───────────────────────────────────────────

--- 创建心跳管理器
--- @param socket_handle number 网络连接的 socket handle
--- @param on_disconnect function(since_ms) 断线回调: 参数为距离最后一次收到数据的时长(ms)
--- @param on_quality_change function(old_level, new_level) 网络质量变化回调
function HeartBeat.new(socket_handle, on_disconnect, on_quality_change)
    local self = setmetatable({}, HeartBeat)
    self.sock = socket_handle
    self.on_disconnect = on_disconnect
    self.on_quality_change = on_quality_change

    -- 当前参数
    self.quality_level = 1         -- 1=正常, 2=轻度, 3=中度, 4=重度, 5=濒临
    self.params = QUALITY_PARAMS[1]

    -- 时间跟踪
    self.last_send_time = 0        -- 上次发送心跳的时间戳 (ms)
    self.last_recv_time = 0        -- 上次收到任何数据的时间戳 (ms)
    self.missed_beats = 0          -- 连续未收到心跳 ACK 的次数
    self.disconnected = false      -- 是否已判定断线

    -- 统计
    self.heartbeat_sent = 0        -- 累计发送心跳数
    self.heartbeat_acked = 0       -- 累计确认心跳数

    -- 序列号（用于匹配心跳请求/响应）
    self.hb_seq = 0

    return self
end

--- 每次收到任何数据时调用（业务数据也算"心跳响应"）。
--- 这避免了"明明在正常通信，却因为没发心跳包而误判断线"的问题。
function HeartBeat:on_data_received()
    self.last_recv_time = engine.get_current_time_ms()
    self.missed_beats = 0  -- 收到任何数据 = 连接正常，重置丢心跳计数
end

--- 每帧调用（或每 100ms 定时器）。
--- 1. 检查是否需要发送心跳
--- 2. 检查是否断线（连续丢心跳超限）
--- 3. 根据网络质量调整参数
function HeartBeat:update()
    if self.disconnected then
        return  -- 已断线，不再处理
    end

    local now = engine.get_current_time_ms()

    -- ─── 第 1 步：检查是否应该发送心跳 ─────────────────
    -- 如果距离上次收到数据超过半个心跳间隔，且距上次发送心跳已经超间隔
    -- 注意: 如果一直在收发业务数据，last_recv_time 会持续更新，心跳不会发送
    local time_since_recv = now - self.last_recv_time
    local time_since_send = now - self.last_send_time

    if time_since_recv > (self.params.interval / 2)
       and time_since_send > self.params.interval then

        -- 发送心跳包
        self.hb_seq = self.hb_seq + 1
        self:_send_heartbeat(self.hb_seq)
        self.last_send_time = now
        self.heartbeat_sent = self.heartbeat_sent + 1
    end

    -- ─── 第 2 步：判断是否断线 ─────────────────────────
    -- 条件: 连续 N 次心跳无 ACK（missed_beats 达到上限）
    -- 同时检查最后一次收到数据的时间是否超过 (interval * missed * 2)
    -- 这个 double-check 防止参数调整期间的误判
    local max_silence = self.params.interval * self.params.missed * 2

    if self.missed_beats >= self.params.missed
       and (now - self.last_recv_time) > max_silence then

        self.disconnected = true
        if self.on_disconnect then
            self.on_disconnect(now - self.last_recv_time)
        end
        return
    end

    -- ─── 第 3 步：接收心跳 ACK ─────────────────────────
    -- 实际实现中，ACK 由网络层的收包线程识别并回调 on_heartbeat_ack()
    -- 如果心跳发出超过 2 倍 RTT 无 ACK，则 missed_beats++

    -- ─── 第 4 步：调整网络质量级别 ─────────────────────
    self:_update_quality_level()
end

--- 收到心跳 ACK 时调用
--- @param ack_seq number ACK 对应的发送序列号
function HeartBeat:on_heartbeat_ack(ack_seq)
    self.last_recv_time = engine.get_current_time_ms()
    self.missed_beats = 0
    self.heartbeat_acked = self.heartbeat_acked + 1
end

--- 心跳超时检查（由定时器调用，每 heartbeat_interval 检查一次）
--- 如果上次发送的心跳在 2*RTT 内没有收到 ACK，missed_beats++
function HeartBeat:check_heartbeat_timeout()
    if self.disconnected then return end

    local now = engine.get_current_time_ms()
    local stats = engine.get_network_stats()
    local expected_rtt = stats.rtt or 100  -- 默认 RTT 估算 100ms

    -- 距离上次发送心跳过了多久
    local elapsed = now - self.last_send_time
    -- 如果有未确认的心跳且超过了 2*RTT + interval
    if elapsed > (expected_rtt * 2 + self.params.interval) then
        self.missed_beats = self.missed_beats + 1
        -- 重置发送时间，避免同一个未确认心跳被重复计数
        self.last_send_time = now
    end
end

-- ─── 内部方法 ───────────────────────────────────────────

--- 发送心跳包。
--- 格式: [1B: type=0xFF] [2B: seq] [4B: timestamp_ms]
function HeartBeat:_send_heartbeat(seq)
    local now = engine.get_current_time_ms()
    local data = string.char(
        0xFF,                           -- type: HEARTBEAT
        bit.band(bit.rshift(seq, 8), 0xFF),  -- seq high byte
        bit.band(seq, 0xFF),            -- seq low byte
        bit.band(bit.rshift(now, 24), 0xFF), -- timestamp byte 3
        bit.band(bit.rshift(now, 16), 0xFF), -- timestamp byte 2
        bit.band(bit.rshift(now, 8), 0xFF),  -- timestamp byte 1
        bit.band(now, 0xFF)             -- timestamp byte 0
    )
    engine.socket_send(self.sock, data, #data)
end

--- 根据当前网络统计更新质量级别和心跳参数。
function HeartBeat:_update_quality_level()
    local stats = engine.get_network_stats()
    if not stats then return end

    local rtt = stats.rtt or 0
    local loss = stats.loss_rate or 0

    -- 从当前级别开始搜索匹配
    local new_level = self.quality_level

    -- 降级检查（网络变差，向上搜索）
    while new_level < #QUALITY_PARAMS do
        local p = QUALITY_PARAMS[new_level]
        if rtt <= p.rtt_max and loss <= p.loss_max then
            break
        end
        new_level = new_level + 1
    end

    -- 升级检查（网络变好，向下搜索）
    -- 使用迟滞: 需要 RTT < 阈值*0.8 且 Loss < 阈值*0.7 才升级
    while new_level > 1 do
        local p = QUALITY_PARAMS[new_level - 1]
        if rtt <= p.rtt_max * 0.8 and loss <= p.loss_max * 0.7 then
            new_level = new_level - 1
        else
            break
        end
    end

    if new_level ~= self.quality_level then
        local old_level = self.quality_level
        self.quality_level = new_level
        self.params = QUALITY_PARAMS[new_level]

        -- 重置心跳计数，避免因参数变化导致的误判
        self.missed_beats = 0

        if self.on_quality_change then
            self.on_quality_change(old_level, new_level)
        end
    end
end

--- 获取当前状态摘要（用于调试面板显示）
function HeartBeat:get_status()
    local now = engine.get_current_time_ms()
    return string.format(
        "HB: lvl=%d int=%dms missed=%d/%d last_recv=%.1fs ago sent=%d ack=%d",
        self.quality_level,
        self.params.interval,
        self.missed_beats,
        self.params.missed,
        (now - self.last_recv_time) / 1000.0,
        self.heartbeat_sent,
        self.heartbeat_acked
    )
end

return HeartBeat
```

**代码要点解释**：

1. **业务包复用心跳**：`on_data_received()` 在每次收到任何数据时调用，重置心跳计数。这避免了"如果业务通信频繁（如 50ms 发一次状态），心跳完全不需要发送"的优化，也避免了"心跳和业务包同时发导致的带宽浪费"。

2. **分级策略表驱动**：`QUALITY_PARAMS` 表集中管理 5 个级别的参数，易于调优和 A/B 测试。

3. **心跳包格式**：7 字节的紧凑二进制格式 `[type:1B, seq:2B, timestamp:4B]`。携带时间戳允许服务器计算单向延迟，而不仅是 RTT。

4. **双向超时机制**：既检查 `missed_beats`（发送端视角的心跳未确认次数），也检查 `max_silence`（接收端视角的最后收包时间）。双重校验防止单一机制的误判。

---

## 6. 服务器端网络质量评估

### 6.1 C#: NetworkQualityMonitor（完整实现）

```csharp
// NetworkQualityMonitor.cs — 服务端玩家网络质量评估与降级管理
// 适用于 Unity/C# 自定义游戏服务器
// 依赖: System.Collections.Generic

using System;
using System.Collections.Generic;

namespace GameServer.NetworkQuality
{
    /// <summary>
    /// 单个玩家的网络质量记录。
    /// 服务器为每个在线玩家维护此结构。
    /// </summary>
    public class PlayerNetworkQuality
    {
        public uint PlayerId { get; set; }

        // ─── 核心指标 (EWMA 平滑) ────────────────────────────
        public float SmoothedRttMs { get; set; }          // EWMA RTT
        public float SmoothedLossRate { get; set; }       // EWMA 丢包率
        public float JitterMs { get; set; }               // RTT 标准差近似

        // ─── 时间窗口统计 ──────────────────────────────────
        public int PacketsReceived1s { get; set; }        // 最近 1 秒收到的包数
        public int PacketsLost1s { get; set; }            // 最近 1 秒丢包数
        public int PacketsReceived10s { get; set; }       // 最近 10 秒收到的包数
        public int PacketsLost10s { get; set; }           // 最近 10 秒丢包数

        // ─── 评分 ──────────────────────────────────────────
        public float QualityScore { get; set; }           // 综合质量分 0-100
        public DateTime LastUpdateTime { get; set; }

        // ─── 连续丢包检测 (用于断线预警) ──────────────────
        public int ConsecutiveLostPackets { get; set; }
        public DateTime LastPacketReceivedTime { get; set; }

        // ─── 历史数据（最近 60 秒，每秒一条） ─────────────
        public readonly Queue<float> RttHistory = new(60);
        public readonly Queue<float> LossHistory = new(60);
    }

    /// <summary>
    /// 玩家级网络质量分级（服务端视角）。
    /// </summary>
    public enum PlayerNetworkTier
    {
        Excellent,   // 优秀: score ≥ 80
        Good,        // 良好: score 60-79
        Fair,        // 一般: score 40-59
        Poor,        // 差:   score 20-39
        Critical,    // 极差: score < 20
        Disconnected // 已断线
    }

    /// <summary>
    /// 根据网络质量分对玩家的降级策略。
    /// </summary>
    public struct DegradationPolicy
    {
        public PlayerNetworkTier MinimumTier;   // 触发此策略的最低级别
        public float SyncIntervalMultiplier;     // 同步间隔系数 (1.0 = 不变, 2.0 = 减半频率)
        public float AoiRadiusMultiplier;        // AOI 范围系数 (1.0 = 不变, <1.0 = 缩小)
        public int   MaxReplicatedEntities;      // 最大同步实体数（低质量玩家减少同步）
    }

    /// <summary>
    /// 服务端网络质量监控器。
    ///
    /// 核心职责:
    ///   1. 为每个在线玩家维护网络质量评分
    ///   2. 质量分影响: 匹配优先级 / AOI 范围 / 同步频率 / 补偿上限
    ///   3. 降级策略: 高延迟/高丢包玩家降低同步优先级
    ///   4. 预警机制: 即将断线时提前通知游戏逻辑
    ///
    /// 使用方式:
    ///   var monitor = new NetworkQualityMonitor(tickRate);
    ///   monitor.OnPacketReceived(playerId, seq, timestamp);
    ///   monitor.OnPacketLost(playerId, seq);
    ///   monitor.Update(); // 每秒调用（Tick 驱动）
    ///   var score = monitor.GetQuality(playerId);
    /// </summary>
    public class NetworkQualityMonitor
    {
        // ─── EWMA 平滑系数 ──────────────────────────────────
        // α 越小 = 越平滑 = 响应越慢
        // 使用不同系数: RTT 变化快 (α=0.3), 丢包率变化慢 (α=0.1)
        private const float EwmaAlphaRtt = 0.3f;
        private const float EwmaAlphaLoss = 0.1f;
        private const float EwmaAlphaJitter = 0.2f;

        // ─── 预警阈值 ───────────────────────────────────────
        private const int ConsecutiveLossWarning = 8;    // 连续丢包 8 个 → 警告
        private const int ConsecutiveLossDisconnect = 20; // 连续丢包 20 个 → 断线
        private const float DisconnectSilenceMs = 5000f; // 5 秒无任何包 → 断线

        // ─── 降级策略表 ─────────────────────────────────────
        private static readonly DegradationPolicy[] DegradationTable =
        {
            // Excellent: 无降级
            new() { MinimumTier = PlayerNetworkTier.Excellent,
                SyncIntervalMultiplier = 1.0f, AoiRadiusMultiplier = 1.0f,
                MaxReplicatedEntities = 500 },
            // Good: 轻微降级
            new() { MinimumTier = PlayerNetworkTier.Good,
                SyncIntervalMultiplier = 1.2f, AoiRadiusMultiplier = 0.9f,
                MaxReplicatedEntities = 400 },
            // Fair: 中度降级
            new() { MinimumTier = PlayerNetworkTier.Fair,
                SyncIntervalMultiplier = 1.5f, AoiRadiusMultiplier = 0.7f,
                MaxReplicatedEntities = 250 },
            // Poor: 重度降级
            new() { MinimumTier = PlayerNetworkTier.Poor,
                SyncIntervalMultiplier = 2.5f, AoiRadiusMultiplier = 0.5f,
                MaxReplicatedEntities = 100 },
            // Critical: 极限降级
            new() { MinimumTier = PlayerNetworkTier.Critical,
                SyncIntervalMultiplier = 4.0f, AoiRadiusMultiplier = 0.3f,
                MaxReplicatedEntities = 30 },
        };

        // ─── 成员 ───────────────────────────────────────────
        private readonly Dictionary<uint, PlayerNetworkQuality> _players = new();
        private readonly uint _tickRate;
        private uint _tickCounter;

        // ─── 事件 ───────────────────────────────────────────
        /// <summary>玩家网络质量变化: (playerId, oldTier, newTier, score)</summary>
        public event Action<uint, PlayerNetworkTier, PlayerNetworkTier, float> OnQualityChanged;

        /// <summary>玩家即将断线预警: (playerId, consecutiveLoss, lastPacketMsAgo)</summary>
        public event Action<uint, int, float> OnDisconnectWarning;

        /// <summary>玩家确认断线: (playerId)</summary>
        public event Action<uint> OnDisconnected;

        // ─── 构造函数 ───────────────────────────────────────
        public NetworkQualityMonitor(uint tickRate = 30)
        {
            _tickRate = tickRate;
        }

        // ─── 数据输入 ───────────────────────────────────────

        /// <summary>
        /// 收到玩家包时调用。
        /// 记录包序号和时间戳，用于 RTT 计算和丢包检测。
        /// </summary>
        public void OnPacketReceived(uint playerId, uint seq, long serverTimestampMs)
        {
            if (!_players.TryGetValue(playerId, out var quality))
            {
                quality = new PlayerNetworkQuality
                {
                    PlayerId = playerId,
                    SmoothedRttMs = 50f,  // 初始 RTT 估算
                    QualityScore = 80f,    // 初始质量分
                    LastPacketReceivedTime = DateTime.UtcNow,
                    LastUpdateTime = DateTime.UtcNow
                };
                _players[playerId] = quality;
            }

            // 计算瞬时 RTT（如果客户端携带了 serverSendTime）
            // 简化：使用 seq 和 tick 的差值估算
            // 生产级实现需要在心跳包中嵌入时间戳做精确 RTT 计算

            // 更新连续丢包计数
            quality.ConsecutiveLostPackets = 0;
            quality.LastPacketReceivedTime = DateTime.UtcNow;

            // 包接收计数
            quality.PacketsReceived1s++;
            quality.PacketsReceived10s++;

            // 更新 EWMA RTT（生产中使用精确测量的 RTT，这里简化处理）
            // quality.SmoothedRttMs 由心跳 RTT 测量更新
        }

        /// <summary>
        /// 检测到丢包时调用（服务器发送未收到 ACK）。
        /// </summary>
        public void OnPacketLost(uint playerId, uint seq)
        {
            if (!_players.TryGetValue(playerId, out var quality)) return;

            quality.PacketsLost1s++;
            quality.PacketsLost10s++;
            quality.ConsecutiveLostPackets++;
        }

        /// <summary>
        /// 更新 RTT（由心跳响应计算得出精确值）。
        /// </summary>
        public void UpdateRtt(uint playerId, float rttMs)
        {
            if (!_players.TryGetValue(playerId, out var quality)) return;

            float prevRtt = quality.SmoothedRttMs;

            // EWMA 平滑
            if (quality.SmoothedRttMs < 1f) // 首次
            {
                quality.SmoothedRttMs = rttMs;
            }
            else
            {
                quality.SmoothedRttMs = EwmaAlphaRtt * rttMs
                    + (1f - EwmaAlphaRtt) * quality.SmoothedRttMs;
            }

            // 抖动 = |RTT - SmoothedRTT| 的 EWMA
            float instantJitter = Math.Abs(rttMs - prevRtt);
            if (quality.JitterMs < 0.1f)
                quality.JitterMs = instantJitter;
            else
                quality.JitterMs = EwmaAlphaJitter * instantJitter
                    + (1f - EwmaAlphaJitter) * quality.JitterMs;

            // 更新 RTT 历史
            quality.RttHistory.Enqueue(rttMs);
            while (quality.RttHistory.Count > 60)
                quality.RttHistory.Dequeue();
        }

        // ─── 定时更新 ───────────────────────────────────────

        /// <summary>
        /// 每秒调用一次（由服务器 Tick 循环驱动）。
        /// 执行: 质量评分 → 降级策略检查 → 断线预警。
        /// </summary>
        public void Update()
        {
            _tickCounter++;

            // 每秒执行一次统计分析
            if (_tickCounter % _tickRate == 0)
            {
                DateTime now = DateTime.UtcNow;

                foreach (var kvp in _players)
                {
                    var quality = kvp.Value;

                    // 1. 计算丢包率
                    int total1s = quality.PacketsReceived1s + quality.PacketsLost1s;
                    float instantLossRate = total1s > 0
                        ? (float)quality.PacketsLost1s / total1s
                        : 0f;

                    if (quality.SmoothedLossRate < 0.001f && instantLossRate < 0.001f)
                        quality.SmoothedLossRate = instantLossRate;
                    else
                        quality.SmoothedLossRate = EwmaAlphaLoss * instantLossRate
                            + (1f - EwmaAlphaLoss) * quality.SmoothedLossRate;

                    // 2. 计算综合质量分 (0-100)
                    quality.QualityScore = CalculateQualityScore(quality);

                    // 3. 更新历史
                    quality.LossHistory.Enqueue(instantLossRate);
                    while (quality.LossHistory.Count > 60)
                        quality.LossHistory.Dequeue();

                    // 4. 断线预警检查
                    CheckDisconnectWarning(kvp.Key, quality, now);

                    // 5. 重置计数器
                    quality.PacketsReceived1s = 0;
                    quality.PacketsLost1s = 0;
                    quality.LastUpdateTime = now;

                    // 6. 更新 10 秒窗口（每 10 秒重置）
                    if (_tickCounter % (_tickRate * 10) == 0)
                    {
                        quality.PacketsReceived10s = 0;
                        quality.PacketsLost10s = 0;
                    }
                }
            }
        }

        // ─── 质量评分 ───────────────────────────────────────

        /// <summary>
        /// 综合质量分计算 (0-100)。
        ///
        /// 评分公式:
        ///   RTT 分  (0-50): 100 - 2*RTT_ms (RTT≥50 → 0)
        ///   丢包率分 (0-35): 100 - 500*loss_rate (loss≥20%→0)
        ///   抖动分  (0-15): 100 - 3*jitter_ms  (jitter≥33ms→0)
        ///   总分     = RTT分*0.5 + 丢包率分*0.35 + 抖动分*0.15
        ///
        /// 权重分配理由:
        ///   - RTT 占比最高 (50%): 直接决定操作延迟体感
        ///   - 丢包率次之 (35%): 影响数据完整性，但可通过冗余/插值缓解
        ///   - 抖动最低 (15%): 影响预测/插值的准确性，但影响程度较轻
        /// </summary>
        private static float CalculateQualityScore(PlayerNetworkQuality q)
        {
            float rttScore = Math.Max(0, 100f - 2f * q.SmoothedRttMs);
            float lossScore = Math.Max(0, 100f - 500f * q.SmoothedLossRate);
            float jitterScore = Math.Max(0, 100f - 3f * q.JitterMs);

            return rttScore * 0.5f + lossScore * 0.35f + jitterScore * 0.15f;
        }

        // ─── 分级判定 ───────────────────────────────────────

        /// <summary>
        /// 根据质量分获取玩家网络层级。
        /// </summary>
        public PlayerNetworkTier GetTier(uint playerId)
        {
            if (!_players.TryGetValue(playerId, out var quality))
                return PlayerNetworkTier.Excellent;

            return ScoreToTier(quality.QualityScore);
        }

        private static PlayerNetworkTier ScoreToTier(float score)
        {
            return score switch
            {
                >= 80 => PlayerNetworkTier.Excellent,
                >= 60 => PlayerNetworkTier.Good,
                >= 40 => PlayerNetworkTier.Fair,
                >= 20 => PlayerNetworkTier.Poor,
                _     => PlayerNetworkTier.Critical
            };
        }

        /// <summary>
        /// 获取指定玩家的降级策略。
        /// </summary>
        public DegradationPolicy GetPolicy(uint playerId)
        {
            var tier = GetTier(playerId);
            foreach (var policy in DegradationTable)
            {
                if (tier <= policy.MinimumTier)
                    return policy;
            }
            return DegradationTable[^1];
        }

        public PlayerNetworkQuality GetQuality(uint playerId)
        {
            _players.TryGetValue(playerId, out var quality);
            return quality;
        }

        public float GetQualityScore(uint playerId)
        {
            return _players.TryGetValue(playerId, out var q) ? q.QualityScore : 100f;
        }

        public void RemovePlayer(uint playerId)
        {
            _players.Remove(playerId);
        }

        // ─── 断线预警 ───────────────────────────────────────

        private void CheckDisconnectWarning(uint playerId,
            PlayerNetworkQuality quality, DateTime now)
        {
            float silenceMs = (float)(now - quality.LastPacketReceivedTime).TotalMilliseconds;

            // 条件 1: 连续丢包超限
            if (quality.ConsecutiveLostPackets >= ConsecutiveLossDisconnect)
            {
                OnDisconnected?.Invoke(playerId);
                return;
            }

            // 条件 2: 静默超时
            if (silenceMs > DisconnectSilenceMs)
            {
                OnDisconnected?.Invoke(playerId);
                return;
            }

            // 条件 3: 预警（还未断线但接近阈值）
            if (quality.ConsecutiveLostPackets >= ConsecutiveLossWarning
                || silenceMs > DisconnectSilenceMs * 0.6f)
            {
                OnDisconnectWarning?.Invoke(playerId,
                    quality.ConsecutiveLostPackets, silenceMs);
            }
        }
    }
}
```

**代码要点解释**：

1. **EWMA 平滑**：原始丢包率/RTT 在秒级窗口内噪声很大（可能从 2% 跳到 15% 再跳回 3%）。EWMA 使用不同 α 系数——RTT α=0.3（响应较快，RTT 本身变化显著），丢包率 α=0.1（响应较慢，丢包率噪声更大）。

2. **综合评分公式**：`50%×RTT分 + 35%×丢包率分 + 15%×抖动分`。权重分配基于各项对游戏体验的实际影响。RTT 50ms 几乎是不可感知的边界，所以评分用的斜率是 2（100 - 2×RTT）。

3. **降级策略表**：`DegradationTable` 按网络层级从好到差排列，查询时找到第一个 ≤ 当前层级的策略。`AoiRadiusMultiplier = 0.3` 意味着严重弱网玩家只能看到 30% 半径内的实体——这既节省了带宽，又是自然的"游戏机制"（你网络差，能接收的信息自然少）。

4. **断线预警**：在 `ConsecutiveLostPackets >= 8`（而非 20）时就发出预警。游戏层收到预警后可以：① 向客户端发送"网络不稳定"提示；② 增大帧缓冲；③ 以 AI 托管此玩家的角色。

---

## 7. GCC/BWE 拥塞控制算法

### 7.1 核心问题：传统 TCP 拥塞控制的失败

TCP 使用基于丢包的拥塞控制（Reno/CUBIC）：发现丢包 → 判定为拥塞 → 减半发送窗口。这在游戏中有两个致命问题：

1. **Bufferbloat**：路由器缓冲区过大时，拥塞表现为 RTT 飙升而非丢包。TCP 检测不到丢包，继续增大窗口，RTT 从 50ms 飙升到 500ms+。

2. **非拥塞丢包**：WiFi/4G 的无线丢包（信号干扰）被 TCP 误判为拥塞，导致不必要的窗口缩小。这在弱网场景下是灾难性的——丢包本来就多，TCP 还自行降速。

### 7.2 Google Congestion Control (GCC) 原理

GCC 是 WebRTC 中使用的拥塞控制算法，专为实时通信设计。其核心创新是用**RTT 的梯度（变化趋势）**而非丢包来检测拥塞：

```
┌─────────────────────────────────────────────────────────────────┐
│                    GCC 核心架构                                    │
│                                                                  │
│  ┌──────────────────────┐     ┌──────────────────────┐          │
│  │  基于延迟的控制器     │     │  基于丢包的控制器     │          │
│  │  (Delay-Based)       │     │  (Loss-Based)        │          │
│  │                      │     │                      │          │
│  │  输入: RTT 变化趋势   │     │  输入: 丢包率         │          │
│  │  检测: RTT 是否在增加 │     │  检测: 丢包率 > 阈值  │          │
│  │  决策: 增/减/保持     │     │  决策: 减半带宽估计   │          │
│  └──────────┬───────────┘     └──────────┬───────────┘          │
│             │                            │                       │
│             └──────────┬─────────────────┘                       │
│                        ▼                                         │
│              ┌──────────────────────┐                            │
│              │   取两者的更保守值    │                            │
│              │   min(delay_rate,    │                            │
│              │       loss_rate)     │                            │
│              └──────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

**基于延迟的检测（核心创新）**：

GCC 不是简单地比较 RTT 和一个固定阈值。它维护一个**RTT 过载检测器 (Overuse Detector)**：

```
RTT 变化趋势判定:

  RTT 在增加 (increasing):
    ┌─ 条件: RTT 的卡尔曼滤波趋势斜率 > 阈值
    └─ 判定: overuse → 降低发送速率

  RTT 在减少 (decreasing):
    ┌─ 条件: 趋势斜率 < -阈值
    └─ 判定: underuse → 增加发送速率  (注: 游戏场景通常不主动增加)

  RTT 稳定 (normal):
    ┌─ 条件: |斜率| < 阈值
    └─ 判定: normal → 保持当前速率
```

**为什么 RTT 梯度比丢包更好？**

```
场景: WiFi 偶发丢包（非拥塞）

基于丢包的算法:
  RTT=40ms, Loss=3% → 判定为拥塞 → 发送速率减半
  实际: 只是信号干扰，网络带宽完全充足 → 误降速

基于 RTT 梯度的算法:
  RTT=40ms, RTT_趋势=稳定(斜率≈0) → 判定为 normal
  Loss=3% 但不触发降速（丢包率 < 10% 高阈值）
  实际: 正确维持速率，丢包用冗余/重传处理
```

### 7.3 在游戏中的适用性分析

| 应用场景 | GCC 适用度 | 原因 |
|---------|-----------|------|
| **帧同步 (Lockstep)** | 低 | 帧同步有严格的发送时间表（每个逻辑帧到达必须发包），不能随意调节发送速率。应使用冗余发包 + 固定速率。 |
| **状态同步 (State Sync)** | 高 | 状态同步每 tick 发送的可变数据量可达数百字节。GCC 可以平滑调节发送速率，避免在弱网时因发送过多导致队列堆积。 |
| **大包传输 (快照/录像)** | 中 | 下载录像/快照时可以接受一定延迟，但游戏内快照传输（如重连时的全量快照）要求尽快传完——应使用更激进的 BBR 而非保守的 GCC。 |
| **语音/视频通话** | 极高 | GCC 最初就是为 WebRTC 的实时音视频设计的，天然适用。 |

**游戏中的实用建议**：

- 对于同步数据（帧指令/状态更新）：使用固定速率 + 自适应参数（第 4 节的方案），而非 GCC 动态调速。因为同步的时序要求严格，不能让带宽波动影响发送频率。
- 对于非关键数据（聊天、日志上传、录像下载）：使用 GCC 或 BBR 做拥塞控制，避免这些数据挤占同步数据的带宽。
- 心跳包：完全不受拥塞控制——始终按计划发送，不受速率限制。

**GCC 简化实现的关键参数**（伪代码）：

```
// RTT 趋势检测的卡尔曼滤波器参数
process_noise       = 1e-3   // 过程噪声协方差
measurement_noise   = 1e-1   // 测量噪声协方差
趋势阈值 (γ)        = 0.005  // overuse 判定斜率阈值

// 发送速率调整
增加: new_rate = old_rate * 1.05     // 5% 增加
降低: new_rate = old_rate * 0.85     // 15% 降低 (AIMD 策略)
降低: min_time_between_decreases = 300ms  // 避免连续降速
```

---

## 8. 练习

### 练习 1: 基础 — 实现自适应心跳 (30min)

基于 Lua `heart_beat.lua` 代码，完成以下任务：

1. **实现 `check_heartbeat_timeout` 的完整逻辑**：
   - 现有代码中此方法已给出骨架，但依赖外部 `engine.get_network_stats()` 获取 RTT
   - 改为基于自身维护的 RTT 估计（用心跳的 send_time vs ack_time 计算）
   - 确保在 RTT 未知时（初始状态）使用安全的默认值 (200ms)

2. **实现单元测试场景**：
   - 模拟 30 秒的正常网络（RTT=40ms, 0% 丢包）→ 验证心跳间隔=5000ms, missed_beats=0
   - 模拟 10 秒的中度弱网（RTT=200ms, 10% 丢包）→ 验证心跳间隔降为 1500ms
   - 模拟连续 6 秒无任何 ACK → 验证 `on_disconnect` 被触发
   - 验证网络恢复后（从重度回到正常），因迟滞逻辑，级别不会立即恢复

3. **添加心跳包 RTT 测量**：
   - 在 `_send_heartbeat` 中记录发送时间
   - 在 `on_heartbeat_ack` 中计算 RTT
   - 将计算出的 RTT 反馈给网络统计，用于 `_update_quality_level`

### 练习 2: 进阶 — 多链路去重系统 (45min)

1. **实现完整的 `PacketDeduplicator`**：
   - 使用循环位图（而非简单的 BitArray 移位）优化性能
   - 添加统计：每秒去重率（重复包数 / 总收包数）、乱序率
   - 支持最多 4096 的序列号窗口（约 4 秒 @ 1000 pps）

2. **设计并实现多链路发送策略的决策逻辑**：
   - 输入：包类型（CRITICAL / NORMAL / BULK）、当前各链路的估计 RTT 和丢包率
   - 输出：选择发送链路（WiFi_ONLY / CELLULAR_ONLY / BOTH）
   - 规则：
     - CRITICAL 包：两条链路都发
     - NORMAL 包：选当前 RTT 较低的链路单发，但如果该链路丢包率 > 10% 则发两条
     - BULK 包：选估计带宽较高的链路单发

3. **测试场景**：
   - 模拟 WiFi RTT=50ms + Loss=2%, 4G RTT=80ms + Loss=1%
   - 发送 1000 个包，其中 10% CRITICAL, 80% NORMAL, 10% BULK
   - 记录每条链路的实际发包数和去重统计
   - 解释为什么某些 NORMAL 包走了"次优"链路

### 练习 3: 挑战 — 完整弱网模拟与自适应系统联调 (90min)

从头构建一个**弱网模拟 + 自适应同步**的集成测试环境：

1. **弱网模拟器**（独立组件，约 150 行 C#）：
   - 在两个虚拟 Socket 之间插入网络损伤模型
   - 支持参数：固定延迟 / 随机抖动 / 随机丢包 / 带宽限制 / 短时断线
   - 支持脚本化的网络变化序列：`[0-10s: 正常] → [10-15s: 丢包10%] → [15-20s: RTT 300ms] → [20-30s: 正常]`
   - 输出日志：每秒的 RTT/丢包率/吞吐量

2. **自适应同步器测试**（集成第 4 节 `BandwidthAdaptiveController`）：
   - 在弱网模拟器的上游和下游各放置一个同步器实例
   - 上游：静态速率发送模拟数据（模拟游戏服务器每 tick 发送状态更新）
   - 弱网模拟器：注入损伤
   - 下游：`BandwidthAdaptiveController` 根据下游观测到的网络质量调整下游期望的同步参数
   - 记录：
     - 每个时间点的实际 RTT / 丢包率
     - 控制器的质量级别切换时间线
     - syncInterval / quantizationBits 的变化曲线
     - 带宽实际使用量

3. **分析输出**：
   - 基于输出的时间线，回答：
     - 控制器从 Excellent 降到 Fair 花了多少秒？（预期 < 3 秒）
     - 网络恢复后，从 Poor 回升到 Excellent 花了多少秒？（预期 5-10 秒，含迟滞）
     - 在 10-15 秒丢包期，syncInterval 从 0.05s 变到了多少？（预期 0.1-0.2s）
     - 是否出现了质量级别振荡？（预期不会，因为有迟滞保护）

---

## 9. 扩展阅读

### 必读论文与标准

- **Google Congestion Control (GCC) — RFC 即将发布的草案**
  https://datatracker.ietf.org/doc/draft-ietf-rmcat-gcc/
  — GCC 的 IETF 标准草案，包含完整的卡尔曼滤波器数学推导

- **QUIC Connection Migration — RFC 9000 §9**
  https://www.rfc-editor.org/rfc/rfc9000#section-9
  — QUIC 标准的连接迁移章节，定义了 PATH_CHALLENGE / PATH_RESPONSE 机制

- **MP-TCP — RFC 6824**
  https://www.rfc-editor.org/rfc/rfc6824
  — MultiPath TCP 标准。虽然游戏直接用的少，但架构思想值得借鉴

### 必读文章（英文）

- **"Bufferbloat: Dark Buffers in the Internet" — Jim Gettys (2011)**
  https://www.bufferbloat.net/
  — 缓冲区膨胀问题的开创性文章。理解为什么"RTT 飙升但没丢包"是现代网络的核心问题。

- **"WebRTC Congestion Control: GCC" — Google**
  https://c3lab.poliba.it/images/6/65/Gcc-analysis.pdf
  — GCC 的详细技术分析，含 Overuse Detector 的数学原理

### 必读文章（中文）

- **腾讯游戏学院: 移动游戏网络优化实践**
  — 腾讯内部手游的网络优化方案，涵盖弱网检测、心跳策略、双链路方案

- **网易游戏: 倩女幽魂手游弱网优化分享**
  — 网易对弱网场景的分级处理和客户端体验优化

### 开源参考

- **KCP — 快速可靠传输协议 (GitHub: skywind3000/kcp)**
  https://github.com/skywind3000/kcp
  — 国人开发的 ARQ 协议，广泛用于国内手游。支持流控和快速重传，是研究弱网优化的优秀起点。

- **ENet — Reliable UDP networking library (GitHub: lsalzman/enet)**
  https://github.com/lsalzman/enet
  — ENet 包含可调节的带宽限制和流控，但缺少自适应机制——这正是本节内容的实践场所。

---

## 常见陷阱

### 陷阱 1: 心跳间隔一刀切——5 秒发一次

**错误**：所有玩家固定 5 秒一次心跳，无论网络质量。

**为什么错**：
- 正常网络：5 秒合理。但如果业务数据流量足够大（200 pps），心跳完全不需要发送——任何业务包都可以起到心跳的作用。
- 重度弱网（30% 丢包率）：5 秒间隔的心跳有 ~83% 概率在 15 秒内至少连续 3 个丢失（导致误判断线）。

**正确做法**：
- 业务包复用心跳逻辑——`on_data_received()` 重置心跳计时器
- 自适应间隔：正常网 5 秒，重度弱网 0.5 秒
- 双重断线判定：连续心跳丢包数 + 绝对静默时长，满足任一即断线

### 陷阱 2: 连接迁移时直接 kill 旧连接

**错误**：创建新连接后，立即 `close()` 旧 socket。

**为什么错**：
- 旧连接的内核缓冲区中可能还有未发送的数据（发送缓冲区未 flush）
- 服务器可能已经向旧地址发送了数据，这些数据在途
- 在新连接稳定通信前关闭旧连接 = 可能丢失迁移窗口期间的服务器→客户端消息

**正确做法**：
1. 创建新连接，发送 MIGRATE 请求
2. 等待服务器 MIGRATE_ACK（含补发数据）
3. 切换到新连接，开始正常通信
4. 等待 1-2 秒（确保服务器侧的旧连接资源已释放）
5. 关闭旧连接

### 陷阱 3: 迟滞阈值设置不当——"升级慢、降级也慢"

**错误**：对升级和降级使用相同/相似的迟滞处理。

**为什么错**：
- 降级应该立即响应——玩家因为网络变差已经感受到卡顿了，此时再延迟降级只会让体验更差
- 升级应该慢慢确认——短暂的网络改善（如走出隧道后的 2 秒 RTT 恢复）不应立即提升同步频率，因为可能下一秒又进入下一个隧道

**正确做法**：
- 降级：0 秒延迟（立即生效）
- 升级：5-10 秒的验证窗口（RTT 和丢包率都持续在阈值以下）
- 升级时使用更严格的阈值（如 `RTT * 0.8` 的迟滞带）

### 陷阱 4: 量化位数降低时忘记精度保护

**错误**：12bit 量化时直接将 float 转为半精度，直接用于游戏逻辑。

**为什么错**：当 `quantizationBits = 12` 时，位置精度约为全精度的 1/4096。对于一个 1000m x 1000m 的地图，12bit 意味着 0.24m 的分辨率——这对大多数游戏足够。但如果在战斗判定中使用量化后的位置（而非精确值），可能导致边界场景判定错误（如正好站在技能范围边界上）。

**正确做法**：
- 量化仅用于网络传输——发送端量化为 N 位，接收端反量化为 float32
- 本地的游戏逻辑和命中判定使用全精度 float32（客户端的预测值 / 服务端的精确值）
- 量化误差只影响远程玩家在本地屏幕上的显示位置（通常是可以接受的 ±0.1m 误差）

### 陷阱 5: 忽略弱网场景下的 GC 压力

**错误**：网络质量变化时，通过创建新对象/新结构来切换配置，产生大量 GC。

**为什么错**：
- C# 服务器每 tick 都要运行，GC 的 Stop-The-World 暂停可能达到 10-50ms
- 在网络质量频繁变化时（每 2-3 秒一次），大量配置对象的分配/释放会让 GC 频繁触发
- 这对延迟敏感的实时系统是不可接受的

**正确做法**：
- 使用 struct（值类型）传递配置，而非 class
- 使用对象池或预分配的配置数组
- `BandwidthAdaptiveController` 的设计已经避免了配置切换时的内存分配（`LerpConfig` 产生新的 struct，在栈上分配）

### 陷阱 6: 去重窗口太小——乱序包被误丢弃

**错误**：去重窗口设为 256 个序列号。

**为什么错**：
- 双链路场景下，同一序列号可能相差 200-300ms 到达（WiFi 先到，4G 后到）
- 在 1000 pps 的发送速率下，256 的窗口只能覆盖 256ms
- 超出窗口的包将被误判为新包（seq 远小于窗口最小值），导致重复处理或错误丢弃

**正确做法**：
- 去重窗口 ≥ 最大预期乱序延迟 × 最大发包速率
- 对于双链路游戏场景：窗口 ≥ 500ms × 200 pps ≈ 100，建议 1024 或 2048
- 使用循环位图而非 BitArray.Shift（避免 O(n) 的移位成本）

### 陷阱 7: 自适应频率下降后，服务端未调整 AOI

**错误**：只降低了同步频率（从 20Hz → 5Hz），但没有缩小 AOI 范围。

**为什么错**：
- 同步频率降低 4 倍 + AOI 范围不变 = 每个同步周期内要同步的对象多了 4 次移动的距离 → 单包变大 → 更容易丢包 → 恶性循环
- AOI 范围应该与同步频率成正比缩小：频率降到 1/4，AOI 半径降到约 1/2（面积变为 1/4），保持单包大小基本不变

**正确做法**：
- 同步频率和 AOI 半径联动调整（已在 `DegradationPolicy` 中体现）
- `AoiRadiusMultiplier = sqrt(SyncIntervalMultiplier)` 是理论最优（保持带宽恒定）

### 陷阱 8: 弱网心跳走 TCP 而非 UDP

**错误**：心跳包随游戏通信一起走 KCP/UDP，但单独的心跳检测逻辑使用了 TCP 连接。

**为什么错**：
- 弱网下 TCP 和 UDP 的丢包特征差异很大（TCP 有内核重传，UDP 没有）
- UDP 已经断了（如 NAT 映射过期），但 TCP 因为内核重传还在"假活"——导致心跳检测不到断线
- 反过来也可能：UDP 通了但 TCP 被 QoS 策略限流

**正确做法**：
- 心跳和游戏数据走同一条传输通道
- 如果游戏用 UDP（KCP/ENet），心跳也用 UDP
- 如果确实需要 TCP keepalive 作为辅助，只将其作为"第二意见"，以 UDP 心跳的判定为准
