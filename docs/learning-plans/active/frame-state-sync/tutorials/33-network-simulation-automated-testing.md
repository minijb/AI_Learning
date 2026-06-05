---
title: "网络模拟与自动化测试"
updated: 2026-06-05
---

# 网络模拟与自动化测试

> 所属计划: 帧同步、状态同步与状态帧同步
> 预计耗时: 60min
> 前置知识: [[30-debugging-profiling|30-网络调试、性能分析与监控]]
>
> 本节将第 30 节中提到的"网络模拟注入"、"自动化回放测试"和"混沌工程"三个关键测试策略独立展开，从工具链到 CI 落地完整覆盖。

---

## 1. 概念讲解

### 1.1 为什么需要网络模拟测试？

**"在我机器上好好的"是最危险的错觉。** 这不是一句调侃——它背后有严密的工程原因。

假设你的对局同步代码在局域网环境下通过了 500 局测试，0 次 Desync，0 次断线。你信心满满地发布上线，第一天用户反馈：

- "打团的时候卡到飞起"（WiFi 2.4GHz + 微波炉干扰 = 周期性 300ms 延迟尖刺）
- "队友突然不动了，过 5 秒又好了"（4G 信号波动 = 8% 瞬时丢包 + 500ms RTT）
- "打到一半直接掉出去了"（电梯场景 = 10 秒完全断网）

这三种问题在局域网里**不可能**出现。< 1ms 的延迟、0% 的丢包率让所有网络容错代码都没有被真正测试过。你写的重传逻辑、断线重连、帧缓冲管理——它们编译通过、本地跑通，但从未经历真实网络条件的考验。

**网络问题的特点是组合爆炸**。单独 200ms 延迟可能没问题，单独 5% 丢包可能也没问题，但 200ms 延迟 + 5% 丢包同时发生呢？帧同步的冗余帧设计可能刚好卡在临界点：冗余帧到达前逻辑帧已经追上了当前位置，于是跳帧——但如果延迟的方差很大（高抖动），冗余帧有时早到有时晚到，就会出现间歇性卡顿，极难复现。

**核心论点**：你不能等用户来发现网络问题。必须有办法在开发机上**精确模拟**任意网络条件，让同步代码在极端条件下被充分测试。

### 1.2 网络模拟的三个层次

在展开具体工具之前，先建立概念层次：

```
┌───────────────────────────────────────────────────────────────────────┐
│                       网络模拟测试的三个层次                             │
├──────────────┬─────────────────┬─────────────────┬────────────────────┤
│   层次        │   L1 链路仿真    │  L2 业务注入     │  L3 混沌工程        │
├──────────────┼─────────────────┼─────────────────┼────────────────────┤
│ 做什么        │ 模拟底层网络      │ 注入业务层异常    │ 随机故障探索未知    │
│              │ 延迟/丢包/抖动    │ 指令丢失/乱序     │ 边界               │
├──────────────┼─────────────────┼─────────────────┼────────────────────┤
│ 可控性        │ 精确控制参数      │ 精确控制注入点    │ 随机概率控制        │
├──────────────┼─────────────────┼─────────────────┼────────────────────┤
│ 典型工具      │ Unity Simulator  │ 自定义注入器      │ ChaosMonkey        │
│              │ UE NetEmulation  │ 回放测试框架      │ 故障注入框架        │
│              │ tc netem/clumsy  │                 │                    │
├──────────────┼─────────────────┼─────────────────┼────────────────────┤
│ 测试什么      │ 已知弱网场景      │ 确定性/一致性     │ 未知故障模式        │
│ 回答什么问题  │ "4G 下能玩吗？"  │ "1000局有Desync吗?"│ "能承受什么？"     │
└──────────────┴─────────────────┴─────────────────┴────────────────────┘
```

L1（链路仿真）和 L2（业务注入）是**验证已知风险**——你知道弱网会出问题，所以你模拟弱网来验证修复。L3（混沌工程）是**探索未知风险**——你不知道什么会出问题，所以随机注入故障来发现系统的薄弱环节。

三层必须全部覆盖。只做链路模拟（"我加了 200ms 延迟，能跑"）而跳过自动化回放（"不知道 1000 局里有没有 Desync"），等于没测。只做回放而跳过混沌工程，则不知道系统在随机组合故障下的行为。

---

## 2. 网络模拟工具链

### 2.1 Unity Network Simulator（应用层）

Unity 从 2023 LTS 开始通过 **Multiplayer Tools** 包提供内置网络模拟器。它工作在传输层之上，拦截 NetworkDriver 的 send/receive 操作，注入模拟效果。

**代码管理器**（完整可用）：

```csharp
// ============================================
// NetworkSimulationManager.cs — Unity 网络模拟管理器
// ============================================
// 依赖：com.unity.netcode.gameobjects (NGO)
//       com.unity.multiplayer.tools (NetworkSimulator)
// ============================================
// 功能：
//   1. 封装 Unity Multiplayer Tools 的 NetworkSimulator API
//   2. 支持预设配置（LAN / 4G / 弱网 / 极端）
//   3. 运行时动态切换网络条件
//   4. 与 Unity 编辑器菜单集成，方便手动调试
// ============================================

using UnityEngine;
using Unity.Netcode;
using Unity.MultiplayerTools.NetworkSimulator;
using System;
using System.Collections.Generic;

/// <summary>
/// 网络条件预设——模拟真实的网络环境参数。
/// 数值来源：Google Wifi Report 2024, OpenSignal Mobile Network Report
/// </summary>
[Serializable]
public struct NetworkConditionProfile
{
    public string name;              // 预设名称，如 "4G 良好"
    public int packetDelayMs;        // 单向延迟 (ms)
    public int packetJitterMs;       // 抖动 (ms) —— 延迟的随机波动范围
    public int packetLossPercent;    // 丢包率 (0-100)
    public string description;       // 描述，用于 UI 显示

    public static readonly NetworkConditionProfile LAN = new NetworkConditionProfile
    {
        name = "LAN (理想)",
        packetDelayMs = 0,
        packetJitterMs = 0,
        packetLossPercent = 0,
        description = "局域网 / 本地回环"
    };

    public static readonly NetworkConditionProfile WifiGood = new NetworkConditionProfile
    {
        name = "WiFi 良好",
        packetDelayMs = 15,
        packetJitterMs = 5,
        packetLossPercent = 0,
        description = "5GHz WiFi，信号满格"
    };

    public static readonly NetworkConditionProfile Mobile4G = new NetworkConditionProfile
    {
        name = "4G 移动网络",
        packetDelayMs = 60,
        packetJitterMs = 20,
        packetLossPercent = 2,
        description = "市区 4G 信号良好"
    };

    public static readonly NetworkConditionProfile WeakSignal = new NetworkConditionProfile
    {
        name = "弱信号 (3G/边缘)",
        packetDelayMs = 200,
        packetJitterMs = 80,
        packetLossPercent = 8,
        description = "信号 1-2 格，典型弱网"
    };

    public static readonly NetworkConditionProfile Extreme = new NetworkConditionProfile
    {
        name = "极端 (电梯/地铁)",
        packetDelayMs = 500,
        packetJitterMs = 150,
        packetLossPercent = 20,
        description = "网络基本不可用，测试极限"
    };
}

/// <summary>
/// 网络模拟管理器。
/// 
/// 使用方式：
///   1. 挂载到场景中任意 GameObject
///   2. 勾选 Inspector 中的 EnableSimulation
///   3. 选择预设或手动输入参数
///   4. 运行时可通过 API 或编辑器菜单切换
/// </summary>
public class NetworkSimulationManager : MonoBehaviour
{
    [Header("模拟开关")]
    [SerializeField] private bool _enableSimulation = false;

    [Header("当前参数 (运行时无效，用于 Inspector 编辑)")]
    [SerializeField] private int _delayMs = 0;
    [SerializeField] private int _jitterMs = 0;
    [SerializeField] [Range(0, 100)] private int _lossPercent = 0;

    [Header("预设")]
    [SerializeField] private int _activePresetIndex = 0;

    // 预设列表
    private static readonly NetworkConditionProfile[] Presets = new[]
    {
        NetworkConditionProfile.LAN,
        NetworkConditionProfile.WifiGood,
        NetworkConditionProfile.Mobile4G,
        NetworkConditionProfile.WeakSignal,
        NetworkConditionProfile.Extreme,
    };

    // 内部状态
    private NetworkSimulator _simulator;
    private NetworkConditionProfile _currentProfile;
    private bool _isInitialized = false;

    // ─── 生命周期 ──────────────────────────────────────────

    private void Awake()
    {
        DontDestroyOnLoad(gameObject);
    }

    private void Start()
    {
        // 等待 NetworkManager 初始化完成后挂载模拟器
        if (NetworkManager.Singleton != null)
        {
            InitializeSimulator();
        }
        else
        {
            NetworkManager.Singleton.OnServerStarted += OnNetworkReady;
        }
    }

    private void OnNetworkReady()
    {
        InitializeSimulator();
    }

    private void OnDestroy()
    {
        if (NetworkManager.Singleton != null)
        {
            NetworkManager.Singleton.OnServerStarted -= OnNetworkReady;
        }
    }

    // ─── 初始化 ────────────────────────────────────────────

    private void InitializeSimulator()
    {
        // 将 NetworkSimulator 挂载到 NetworkManager 的 NetworkDriver 上
        var networkManager = NetworkManager.Singleton;
        if (networkManager == null)
        {
            Debug.LogError("[NetSim] NetworkManager.Singleton is null");
            return;
        }

        // NetworkSimulator 通过 NetworkManager 的 NetworkConfig 注册
        _simulator = new NetworkSimulator();
        _simulator.Initialize(networkManager);

        _isInitialized = true;

        if (_enableSimulation)
        {
            ApplyPreset(_activePresetIndex);
        }

        Debug.Log("[NetSim] 初始化完成");
    }

    // ─── 公共 API ──────────────────────────────────────────

    /// <summary>
    /// 应用预设网络条件。
    /// </summary>
    /// <param name="presetIndex">预设索引 0-4</param>
    public void ApplyPreset(int presetIndex)
    {
        if (presetIndex < 0 || presetIndex >= Presets.Length)
        {
            Debug.LogError($"[NetSim] 无效的预设索引: {presetIndex}");
            return;
        }

        var profile = Presets[presetIndex];
        ApplyProfile(profile);
    }

    /// <summary>
    /// 应用自定义网络条件。
    /// </summary>
    public void ApplyCustom(int delayMs, int jitterMs, int lossPercent)
    {
        var profile = new NetworkConditionProfile
        {
            name = "Custom",
            packetDelayMs = delayMs,
            packetJitterMs = jitterMs,
            packetLossPercent = lossPercent,
            description = "用户自定义",
        };
        ApplyProfile(profile);
    }

    /// <summary>
    /// 关闭网络模拟，恢复正常网络。
    /// </summary>
    public void DisableSimulation()
    {
        if (_simulator != null)
        {
            _simulator.Disable();
        }
        _enableSimulation = false;
        Debug.Log("[NetSim] 网络模拟已关闭");
    }

    /// <summary>
    /// 获取当前网络条件。
    /// </summary>
    public NetworkConditionProfile GetCurrentProfile()
    {
        return _currentProfile;
    }

    /// <summary>
    /// 运行时临时修改延迟（保持其他参数不变）。
    /// 用于测试"延迟逐步升高"的场景。
    /// </summary>
    public void SetDelayTemporarily(int delayMs)
    {
        if (_simulator == null) return;
        var p = _currentProfile;
        p.packetDelayMs = delayMs;
        ApplyProfileInternal(p);
    }

    // ─── 内部实现 ──────────────────────────────────────────

    private void ApplyProfile(NetworkConditionProfile profile)
    {
        _currentProfile = profile;
        _enableSimulation = true;
        ApplyProfileInternal(profile);
        Debug.Log($"[NetSim] 切换到: {profile.name} — 延迟={profile.packetDelayMs}ms, 抖动={profile.packetJitterMs}ms, 丢包={profile.packetLossPercent}% — {profile.description}");
    }

    private void ApplyProfileInternal(NetworkConditionProfile profile)
    {
        if (_simulator == null || !_isInitialized)
        {
            Debug.LogWarning("[NetSim] 模拟器未初始化，将在初始化后应用");
            return;
        }

        // 配置 NetworkSimulator 参数
        var settings = new NetworkSimulatorSettings
        {
            // 单向延迟：数据包在发送前被延迟的毫秒数
            PacketDelayMS = profile.packetDelayMs,
            // 抖动：在延迟基础上增加 ±PacketJitterMS 的随机波动
            PacketJitterMS = profile.packetJitterMs,
            // 丢包率：0-100 的百分比
            PacketLossInterval = 100,             // 每 100 个包为一个统计周期
            PacketLossPercent = profile.packetLossPercent,
        };

        _simulator.UpdateSettings(settings);
        _simulator.Enable();
    }
}
```

**运行时命令行切换**（用于自动化测试脚本）：

```csharp
// ============================================
// 在自动化测试脚本中切换网络条件
// ============================================

// 查找已有的 NetworkSimulationManager（单例）
var netSim = FindObjectOfType<NetworkSimulationManager>();

// 测试 4G 条件
netSim.ApplyPreset(2);  // Mobile4G
yield return new WaitForSeconds(60f);  // 运行 60 秒

// 测试弱网条件
netSim.ApplyPreset(3);  // WeakSignal
yield return new WaitForSeconds(60f);

// 清理：恢复 LAN
netSim.DisableSimulation();
```

### 2.2 Unreal Engine Network Emulation（引擎层）

Unreal Engine 的网络模拟系统内建于引擎的包处理管线中，精度高于 Unity 的应用层模拟——它在套接字层之前拦截数据包，因此连底层重传行为也会被延迟。

#### 2.2.1 配置文件方式

在 `DefaultEngine.ini` 的 `[/Script/Engine.Player]` 段中配置：

```ini
; ============================================
; DefaultEngine.ini — 网络模拟配置
; ============================================
; 适用于 PIE (Play In Editor) 模式下测试
; 正式打包版本自动忽略这些设置
; ============================================

[/Script/Engine.Player]

; ─── 基本参数 ──────────────────────────────
; PktLag: 出站数据包的延迟 (ms) —— 模拟网络延迟
;   注意：这是单向延迟。如果要模拟 RTT=200ms，设 PktLag=100
PktLag=100

; PktLagVariance: 延迟抖动范围 (ms) —— 实际延迟 = PktLag ± PktLagVariance
;   "信号满格的 4G": PktLag=50, PktLagVariance=10
;   "信号衰减的 4G": PktLag=80, PktLagVariance=30
PktLagVariance=20

; PktLoss: 出站丢包百分比 (0-100) —— Engine/Server 收包
;   注意：5 表示 5% 丢包率，不是 0.05%
PktLoss=5

; ─── 高级参数 ──────────────────────────────
; PktIncomingLagMin/PktIncomingLagMax: 入站延迟范围 —— 模拟上行/下行不对称延迟
PktIncomingLagMin=80
PktIncomingLagMax=140

; PktIncomingLoss: 入站丢包百分比 —— Engine/Server 发包给客户端
PktIncomingLoss=3

; PktDup: 重复包百分比 —— 模拟网络链路层重传
PktDup=2

; ─── 带宽限制 ──────────────────────────────
; PktOrder: 0=不保证顺序 (UDP 真实行为), 1=保证顺序, 2=完全乱序
PktOrder=0
```

#### 2.2.2 控制台命令（运行时动态调整）

UE 的控制台命令系统允许**运行时无重启切换网络条件**，这在自动化测试中极为关键：

```
; ─── PIE 模式下在控制台输入以下命令 ────────────────────

; 查看当前网络模拟参数
net.PktLag
net.PktLoss
net.PktLagVariance

; 临时修改延迟（立即生效，无需重新开始 PIE）
net.PktLag 200          ; 设置 200ms 单向延迟
net.PktLagVariance 50   ; ±50ms 抖动
net.PktLoss 10          ; 10% 丢包

; 关闭模拟
net.PktLag 0
net.PktLoss 0
net.PktLagVariance 0

; ─── 预设加载 ─────────────────────────────────────────
; UE 5.0+ 支持 NetEmulationProfile JSON 配置文件
; 位置: <Project>/Config/NetEmulation/
; 使用: net.EmulationProfile <ProfileName>

; 加载 "4G_Good" 预设
net.EmulationProfile 4G_Good

; 列出所有可用预设
net.ListEmulationProfiles

; 临时禁用但不删除配置（恢复后可以重新启用）
net.EmulationOff
net.EmulationOn
```

#### 2.2.3 C++ 代码控制网络条件

```cpp
// ============================================
// NetworkConditionProfile.h — UE C++ 网络条件管理
// ============================================
// 用途：
//   1. 将网络条件预设定义为结构化的枚举
//   2. 提供 C++ API 来切换网络模拟条件
//   3. 支持自动化测试脚本通过 BlueprintCallable 调用
// ============================================

#pragma once

#include "CoreMinimal.h"
#include "Engine/Engine.h"
#include "Engine/NetDriver.h"
#include "GameFramework/Actor.h"
#include "NetworkConditionProfile.generated.h"

/**
 * 预定义的网络条件——映射到业界标准的网络环境分类。
 */
UENUM(BlueprintType)
enum class ENetworkCondition : uint8
{
    LAN         UMETA(DisplayName = "LAN (理想)"),
    Wifi_Good   UMETA(DisplayName = "WiFi 良好"),
    Mobile_4G   UMETA(DisplayName = "4G 移动网络"),
    WeakSignal  UMETA(DisplayName = "弱信号"),
    Extreme     UMETA(DisplayName = "极端网络"),
    Custom      UMETA(DisplayName = "自定义"),
};

/**
 * 网络条件预定义数据结构。
 */
USTRUCT(BlueprintType)
struct FNetworkConditionParams
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FString Name;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 PktLag = 0;         // 单向延迟 (ms)

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 PktLagVariance = 0; // 抖动 (ms)

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 PktLoss = 0;        // 丢包率 (0-100)

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 PktIncomingLoss = 0; // 入站丢包率

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    int32 PktDup = 0;          // 重复包率
};

/**
 * 网络条件管理器。
 * 挂载到 Level 中的任意 Actor 即可使用。
 * 提供 C++ 和 Blueprint 双接口。
 */
UCLASS(BlueprintType, Blueprintable)
class UNetworkConditionManager : public UActorComponent
{
    GENERATED_BODY()

public:
    UNetworkConditionManager();

    // ─── 预设查询 ────────────────────────────────────

    /** 获取所有预设条件的默认参数。 */
    UFUNCTION(BlueprintCallable, Category = "Network Simulation")
    static TMap<ENetworkCondition, FNetworkConditionParams> GetPresets();

    /** 获取指定预设的参数。 */
    UFUNCTION(BlueprintCallable, Category = "Network Simulation")
    static FNetworkConditionParams GetPresetParams(ENetworkCondition Condition);

    // ─── 条件切换 ────────────────────────────────────

    /** 应用一个预定义网络条件。 */
    UFUNCTION(BlueprintCallable, Category = "Network Simulation")
    void ApplyCondition(ENetworkCondition Condition);

    /** 应用自定义参数。 */
    UFUNCTION(BlueprintCallable, Category = "Network Simulation")
    void ApplyCustomParams(const FNetworkConditionParams& Params);

    /** 关闭网络模拟。 */
    UFUNCTION(BlueprintCallable, Category = "Network Simulation")
    void DisableEmulation();

    /** 临时修改延迟 (保持其他参数不变)。 */
    UFUNCTION(BlueprintCallable, Category = "Network Simulation")
    void SetLagTemporarily(int32 LagMs);

    // ─── 查询 ─────────────────────────────────────────

    /** 获取当前网络条件描述。 */
    UFUNCTION(BlueprintCallable, Category = "Network Simulation")
    FString GetCurrentConditionDescription() const;

private:
    // 当前条件
    ENetworkCondition CurrentCondition;
    FNetworkConditionParams CurrentParams;

    // 将参数应用到引擎
    void ApplyToEngine(const FNetworkConditionParams& Params);
};
```

```cpp
// ============================================
// NetworkConditionProfile.cpp — 实现
// ============================================

#include "NetworkConditionProfile.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

UNetworkConditionManager::UNetworkConditionManager()
    : CurrentCondition(ENetworkCondition::LAN)
{
    PrimaryComponentTick.bCanEverTick = false;
}

// ─── 预设数据 ────────────────────────────────────────

TMap<ENetworkCondition, FNetworkConditionParams> UNetworkConditionManager::GetPresets()
{
    TMap<ENetworkCondition, FNetworkConditionParams> Presets;

    // LAN — 无延迟、无丢包
    Presets.Add(ENetworkCondition::LAN, FNetworkConditionParams{
        TEXT("LAN (理想)"), 0, 0, 0, 0, 0
    });

    // WiFi 良好 — 5GHz 频段满格
    Presets.Add(ENetworkCondition::Wifi_Good, FNetworkConditionParams{
        TEXT("WiFi 良好"), 15, 5, 1, 1, 0
    });

    // 4G 移动网络 — 市区正常信号
    Presets.Add(ENetworkCondition::Mobile_4G, FNetworkConditionParams{
        TEXT("4G 移动网络"), 60, 20, 2, 2, 1
    });

    // 弱信号 — 1-2 格，典型弱网体验
    Presets.Add(ENetworkCondition::WeakSignal, FNetworkConditionParams{
        TEXT("弱信号"), 200, 80, 8, 8, 3
    });

    // 极端网络 — 电梯/地铁/地下停车场
    Presets.Add(ENetworkCondition::Extreme, FNetworkConditionParams{
        TEXT("极端网络"), 500, 150, 20, 20, 5
    });

    return Presets;
}

FNetworkConditionParams UNetworkConditionManager::GetPresetParams(ENetworkCondition Condition)
{
    const auto& Presets = GetPresets();
    if (const FNetworkConditionParams* Found = Presets.Find(Condition))
    {
        return *Found;
    }
    return FNetworkConditionParams{TEXT("Unknown"), 0, 0, 0, 0, 0};
}

// ─── 核心：将参数应用到 UE 网络驱动 ─────────────────

void UNetworkConditionManager::ApplyCondition(ENetworkCondition Condition)
{
    CurrentCondition = Condition;
    CurrentParams = GetPresetParams(Condition);
    ApplyToEngine(CurrentParams);

    UE_LOG(LogTemp, Log, TEXT("[NetCond] 切换到: %s | Lag=%dms Jitter=%dms Loss=%d%%"),
        *CurrentParams.Name, CurrentParams.PktLag,
        CurrentParams.PktLagVariance, CurrentParams.PktLoss);
}

void UNetworkConditionManager::ApplyCustomParams(const FNetworkConditionParams& Params)
{
    CurrentCondition = ENetworkCondition::Custom;
    CurrentParams = Params;
    ApplyToEngine(Params);
}

void UNetworkConditionManager::DisableEmulation()
{
    FNetworkConditionParams Off{TEXT("Off"), 0, 0, 0, 0, 0};
    ApplyToEngine(Off);
    UE_LOG(LogTemp, Log, TEXT("[NetCond] 网络模拟已关闭"));
}

void UNetworkConditionManager::SetLagTemporarily(int32 LagMs)
{
    CurrentParams.PktLag = LagMs;
    ApplyToEngine(CurrentParams);
}

// ─── 内部实现：通过控制台命令注入参数 ────────────────

void UNetworkConditionManager::ApplyToEngine(const FNetworkConditionParams& Params)
{
    // UE 的网络模拟通过控制台变量 (CVar) 控制
    // 使用 IConsoleManager 直接设置，避免字符串拼接的开销
    if (IConsoleManager* ConsoleMan = &IConsoleManager::Get())
    {
        // 获取对应的控制台变量
        static IConsoleVariable* CVarPktLag =
            ConsoleMan->FindConsoleVariable(TEXT("net.PktLag"));
        static IConsoleVariable* CVarPktLagVariance =
            ConsoleMan->FindConsoleVariable(TEXT("net.PktLagVariance"));
        static IConsoleVariable* CVarPktLoss =
            ConsoleMan->FindConsoleVariable(TEXT("net.PktLoss"));
        static IConsoleVariable* CVarPktIncomingLoss =
            ConsoleMan->FindConsoleVariable(TEXT("net.PktIncomingLoss"));
        static IConsoleVariable* CVarPktDup =
            ConsoleMan->FindConsoleVariable(TEXT("net.PktDup"));

        if (CVarPktLag)           CVarPktLag->Set(Params.PktLag);
        if (CVarPktLagVariance)   CVarPktLagVariance->Set(Params.PktLagVariance);
        if (CVarPktLoss)          CVarPktLoss->Set(Params.PktLoss);
        if (CVarPktIncomingLoss)  CVarPktIncomingLoss->Set(Params.PktIncomingLoss);
        if (CVarPktDup)           CVarPktDup->Set(Params.PktDup);
    }
}

FString UNetworkConditionManager::GetCurrentConditionDescription() const
{
    return FString::Printf(TEXT("%s: Lag=%dms Jitter=%dms Loss=%d%%"),
        *CurrentParams.Name,
        CurrentParams.PktLag,
        CurrentParams.PktLagVariance,
        CurrentParams.PktLoss);
}
```

### 2.3 系统级网络模拟工具

引擎内置的模拟器有一个本质局限：它们只在**应用层**（传输层之上）工作。这意味着：

- TCP 的重传超时计算不会被模拟延迟影响（模拟器在 `send()` 之后才延迟，但 TCP 的内部 RTT 估算基于真实网络）
- 系统调用本身的时间不被延迟
- 内核级别的行为（拥塞控制、Nagle 算法等）使用真实网络条件

系统级工具解决了这些问题——它们在**内核网络栈**层注入延迟/丢包/乱序，因此连 TCP 协议栈的内部行为也会受到真实影响。

#### 2.3.1 Linux: tc netem

`netem` (Network Emulator) 是 Linux 内核流量控制基础设施的一部分，提供精确的网络条件模拟。对于**游戏服务端部署在 Linux** 的场景，这是最强大的测试工具。

```bash
# ============================================
# tc netem — Linux 内核级网络模拟
# ============================================
# 以下命令在游戏服务器的 Linux 主机上执行
# 需要 sudo 权限 (操作内核网络队列)
# ============================================

# ─── 基本语法 ─────────────────────────────────────────
# tc qdisc add dev <网卡> root netem <参数>
# tc qdisc change dev <网卡> root netem <参数>  # 修改现有规则
# tc qdisc del dev <网卡> root                  # 删除所有规则

# ─── 场景 1：模拟 4G 移动网络 ─────────────────────────
# RTT=120ms: 单向延迟 60ms，±20ms 抖动，2% 丢包
sudo tc qdisc add dev eth0 root netem \
    delay 60ms 20ms distribution normal \
    loss 2% 25%

# 参数解释：
#   delay 60ms    — 基础延迟 60ms
#   20ms          — ±20ms 抖动 (实际延迟: 40-80ms)
#   distribution normal — 使用正态分布产生抖动（而非均匀分布）
#   loss 2%       — 2% 丢包率
#   25%           — 丢包相关性: 25% 的丢包与前一次丢包相关（模拟突发丢包）

# ─── 场景 2：WiFi 弱信号 (周期性干扰) ─────────────────
# WiFi 因微波炉/邻居路由器产生的周期性干扰: 每 10s 约 2s 高丢包
sudo tc qdisc add dev eth0 root netem \
    delay 30ms 10ms \
    loss 1% 10%

# ─── 场景 3：高抖动移动网络 ───────────────────────────
# 地铁/高铁场景: 信号在基站间快速切换
sudo tc qdisc change dev eth0 root netem \
    delay 150ms 100ms distribution pareto \
    loss 5% 50%

# distribution pareto — 帕累托分布: 少数极端延迟尖刺
#   比正态分布更接近真实移动网络的延迟分布特征

# ─── 场景 4：限速 (模拟弱信号低带宽) ──────────────────
# 游戏服务端出站限速到 64Kbps (模拟客户端弱信号)
sudo tc qdisc add dev eth0 root handle 1: htb default 10
sudo tc class add dev eth0 parent 1: classid 1:1 htb rate 64kbit ceil 64kbit

# ─── 场景 5：包损坏 (模拟链路层 CRC 错误) ──────────────
# 0.1% 的包被随机损坏
sudo tc qdisc change dev eth0 root netem \
    delay 50ms 10ms \
    loss 2% \
    corrupt 0.1%

# ─── 场景 6：包乱序 (模拟多路径路由) ──────────────────
# 50% 的包延迟 50ms，其中 25% 可能乱序到达
sudo tc qdisc change dev eth0 root netem \
    delay 50ms \
    reorder 25% 50%

# ─── 查看当前规则 ─────────────────────────────────────
tc qdisc show dev eth0

# ─── 清除所有规则（恢复原状） ─────────────────────────
sudo tc qdisc del dev eth0 root
```

**自动化脚本**（用于 CI 管道）：

```bash
#!/bin/bash
# ============================================
# netem_ci_test.sh — CI 网络条件测试脚本
# ============================================
# 用法:
#   ./netem_ci_test.sh <场景名> <游戏服进程PID> <测试时长秒>
# 场景名: lan | 4g | weak | extreme
# ============================================

set -e

SCENARIO="$1"
PID="$2"
DURATION="${3:-60}"
INTERFACE="eth0"

# 确保游戏服务器在运行
if ! kill -0 "$PID" 2>/dev/null; then
    echo "错误: 进程 $PID 不存在"
    exit 1
fi

# 确保没有残留的 tc 规则
sudo tc qdisc del dev "$INTERFACE" root 2>/dev/null || true

# 定义场景参数
case "$SCENARIO" in
    lan)
        echo "[$(date +%T)] 场景: LAN (无模拟)"
        # 不清除，让网络自然运行
        ;;
    4g)
        echo "[$(date +%T)] 场景: 4G 移动网络 (60ms延迟, ±20ms抖动, 2%丢包)"
        sudo tc qdisc add dev "$INTERFACE" root netem \
            delay 60ms 20ms distribution normal \
            loss 2% 25%
        ;;
    weak)
        echo "[$(date +%T)] 场景: 弱信号 (200ms延迟, ±80ms抖动, 8%丢包)"
        sudo tc qdisc add dev "$INTERFACE" root netem \
            delay 200ms 80ms distribution normal \
            loss 8% 25%
        ;;
    extreme)
        echo "[$(date +%T)] 场景: 极端网络 (500ms延迟, ±150ms抖动, 20%丢包)"
        sudo tc qdisc add dev "$INTERFACE" root netem \
            delay 500ms 150ms distribution pareto \
            loss 20% 50%
        ;;
    *)
        echo "未知场景: $SCENARIO (支持: lan|4g|weak|extreme)"
        exit 1
        ;;
esac

# 等待指定时长
echo "[$(date +%T)] 运行 $DURATION 秒..."
sleep "$DURATION"

# 清理
sudo tc qdisc del dev "$INTERFACE" root 2>/dev/null || true
echo "[$(date +%T)] 测试完成，tc 规则已清除"
```

#### 2.3.2 Windows: Clumsy

[Clumsy](https://github.com/jagt/clumsy) 是一个 Windows 平台的开源网络模拟工具，通过 WinDivert 驱动在内核层拦截网络包。它比 Unity/UE 内置模拟器更接近真实网络行为。

**配置方式**（GUI 工具，通过 UI 勾选和滑块调整）：

```
; clumsy 配置说明
; 程序: clumsy-0.3-win64/clumsy.exe
; 过滤: 可以按 IP/端口过滤（只模拟特定进程的网络）

功能模式 (均支持独立开关):
  Lag        — 延迟: 设置固定延迟 ms (入站+出站都延迟)
  Drop       — 丢包: 随机丢弃指定概率的包
  Throttle   — 限速: 将带宽限制到指定值, 超出的包排队等待
  Duplicate  — 重复: 随机复制指定概率的包
  Out of order — 乱序: 随机重排指定概率的包
  Tamper     — 修改: 随机修改指定概率的包内容 (模拟链路层损坏)

典型配置 (过滤 udp and (tcp.DstPort == 服务器端口)):
  4G良好: Lag=30ms, Drop=2%, 其他关闭
  弱信号: Lag=100ms, Drop=8%, Reorder=2%
  极端:   Lag=250ms, Drop=20%, Reorder=5%, Throttle=64Kbps入站
```

**命令行模式**（适用于 CI）：

```cmd
REM Windows CI 批处理 — 启动 clumsy 进行网络模拟
REM clumsy.exe 支持命令行参数传递配置

REM 启动 60ms 延迟 + 2% 丢包
start /B clumsy.exe --lag 60 --drop 2 --filter "udp and outbound"

REM 等待测试完成 (假设测试脚本在另一个进程中)
timeout /t 120

REM 关闭 clumsy
taskkill /IM clumsy.exe /F
```

#### 2.3.3 macOS: Network Link Conditioner

macOS 自带 Network Link Conditioner（需安装 Additional Tools for Xcode）：

```
; 系统偏好设置 → Network Link Conditioner
; 预置 Profile: 3G, Edge, High Latency DNS, Lossy Network, Very Bad Network

; 或通过命令行控制 (需要安装后)
; 开启 4G 条件
sudo ditto /System/Library/PreferencePanes/NetworkLinkConditioner.prefPane

; nlcc - 命令行工具 (部分版本可用)
nlcc --profile "Very Bad Network" --duration 120
```

---

## 3. 自动化回放测试

### 3.1 核心思路

网络模拟回答了"弱网下能不能跑"这个问题。但它回答不了另一个同等重要的问题：**"1000 局里有没有 Desync？"**

这就是自动化回放测试的价值。思路非常直接：

```
录制阶段 (一次性工作):
  真实玩家对局 → 记录每帧的玩家输入 → 保存为 .replay 文件

回放阶段 (CI 每次运行):
  加载 .replay 文件 → 用相同的初始状态 + 相同的输入序列 → 重新执行逻辑
  → 计算最终状态 Hash → 与录制时的 Hash 对比
  → 一致 = 通过, 不一致 = Desync bug
```

**为什么这能发现 Desync？** 因为代码变了——你今天提交的 PR 改了碰撞检测的某个边缘条件。对局逻辑代码变了，但输入不变。如果最终状态 Hash 不一致，就说明你的修改在某个帧产生了不同的计算结果——这就是 Desync。

### 3.2 判定标准

不同同步模式有不同的判定标准：

| 同步模式 | 判定标准 | 说明 |
|---------|---------|------|
| 帧同步 | 状态 Hash **完全一致** | 确定性要求：相同输入 → 相同输出。任何差异都是 bug |
| 状态同步 | 最终状态偏差在**阈值内** | 浮点预测有误差，允许 < 1cm 的位置偏差 |
| 混合同步 | 锁步部分 Hash 一致 + 状态通道偏差在阈值内 | 分别用两种标准判定 |

### 3.3 C# 自动化回放测试器（完整实现）

```csharp
// ============================================
// AutomatedReplayTester.cs — 帧同步确定性回放测试
// ============================================
// 用途：
//   1. 从 .replay 文件加载录制好的输入序列
//   2. 用相同的初始状态和输入序列重新执行逻辑
//   3. 逐帧对比状态 Hash，检测 Desync
//   4. 批量运行 1000+ 局回放，输出汇总报告
// ============================================
// 依赖文件格式（.replay 二进制格式）：
//   [4 bytes] magic: 'RPLY'
//   [2 bytes] version: 1
//   [4 bytes] total_frames: N
//   [4 bytes] seed: 随机种子
//   [4 bytes] player_count: P
//   [4 bytes] initial_state_size: S
//   [S bytes] initial_state: 初始状态的序列化快照
//   每帧:
//     [4 bytes] frame_number
//     [1 byte]  input_count
//     每个输入: [1 byte] player_id, [4 bytes] input_data
//   [4 bytes] expected_hash: 录制时的最终状态 Hash
//   [4 bytes] checksum: 文件校验 (CRC32)
// ============================================

using System;
using System.IO;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

/// <summary>
/// 回放中单帧的输入数据。
/// </summary>
public struct ReplayFrameInput
{
    public int frameNumber;
    public Dictionary<int, uint> playerInputs; // playerId → 输入数据
}

/// <summary>
/// 回放文件的元数据和内容。
/// </summary>
public class ReplayFile
{
    public const uint Magic = 0x59504C52; // 'RPLY' 的 little-endian

    public ushort Version;
    public int TotalFrames;
    public uint Seed;
    public int PlayerCount;
    public byte[] InitialState;         // 初始状态快照
    public List<ReplayFrameInput> Frames; // 每帧的输入
    public uint ExpectedHash;           // 录制时的最终 Hash
    public string FilePath;             // 原始文件路径（用于日志）

    /// <summary>
    /// 从文件加载 .replay 文件。
    /// </summary>
    public static ReplayFile Load(string filePath)
    {
        using var fs = new FileStream(filePath, FileMode.Open, FileAccess.Read);
        using var reader = new BinaryReader(fs);

        // ─── Header ─────────────────────────────────
        uint magic = reader.ReadUInt32();
        if (magic != Magic)
            throw new InvalidDataException($"无效的 .replay 文件: Magic={magic:X8}");

        var replay = new ReplayFile
        {
            FilePath = filePath,
            Version = reader.ReadUInt16(),
            TotalFrames = reader.ReadInt32(),
            Seed = reader.ReadUInt32(),
            PlayerCount = reader.ReadInt32(),
        };

        // ─── 初始状态 ────────────────────────────────
        int initialStateSize = reader.ReadInt32();
        replay.InitialState = reader.ReadBytes(initialStateSize);

        // ─── 每帧输入 ────────────────────────────────
        replay.Frames = new List<ReplayFrameInput>(replay.TotalFrames);
        for (int f = 0; f < replay.TotalFrames; f++)
        {
            int frameNum = reader.ReadInt32();
            int inputCount = reader.ReadByte();

            var frameInput = new ReplayFrameInput
            {
                frameNumber = frameNum,
                playerInputs = new Dictionary<int, uint>(inputCount),
            };

            for (int i = 0; i < inputCount; i++)
            {
                int playerId = reader.ReadByte();
                uint inputData = reader.ReadUInt32();
                frameInput.playerInputs[playerId] = inputData;
            }

            replay.Frames.Add(frameInput);
        }

        // ─── 尾部 ────────────────────────────────────
        replay.ExpectedHash = reader.ReadUInt32();

        return replay;
    }
}

/// <summary>
/// 单局回放测试的结果。
/// </summary>
[Serializable]
public class ReplayTestResult
{
    public string ReplayFile;
    public bool Passed;                  // 总体是否通过
    public int TotalFrames;
    public int FirstDesyncFrame = -1;    // 首次 Desync 帧号 (-1 表示无)
    public uint ExpectedHash;            // 录制时的 Hash
    public uint ActualHash;              // 回放时的 Hash
    public List<int> DesyncFrames;       // 所有不一致的帧号
    public double ExecutionTimeMs;       // 回放执行耗时
    public string ErrorMessage;          // 异常信息（如果发生）
}

/// <summary>
/// 批量回放测试的汇总报告。
/// </summary>
[Serializable]
public class ReplayTestSummary
{
    public int TotalReplays;
    public int Passed;
    public int Failed;
    public List<ReplayTestResult> Details;
    public double TotalExecutionTimeMs;
}

/// <summary>
/// 自动化回放测试器。
/// 
/// 使用方式：
///   1. 通过 Editor 菜单运行: Tools → Replay Test → Run All Replays
///   2. 通过 CI 命令行运行: unity -batchmode -executeMethod AutomatedReplayTester.RunFromCI
///   3. 通过代码调用: AutomatedReplayTester.RunReplayTest("path/to/replay.rply")
/// </summary>
public class AutomatedReplayTester
{
    // ─── 核心：运行单局回放测试 ──────────────────────────

    /// <summary>
    /// 加载并回放一个 .replay 文件，逐帧对比状态 Hash。
    /// </summary>
    /// <param name="replayFilePath">.replay 文件路径</param>
    /// <param name="gameInstance">游戏逻辑实例（实现了 IReplayableGame 接口）</param>
    /// <returns>测试结果</returns>
    public static ReplayTestResult RunReplayTest(string replayFilePath, IReplayableGame gameInstance)
    {
        var sw = Stopwatch.StartNew();
        var result = new ReplayTestResult
        {
            ReplayFile = replayFilePath,
            DesyncFrames = new List<int>(),
        };

        try
        {
            // Step 1: 加载回放文件
            var replay = ReplayFile.Load(replayFilePath);
            result.TotalFrames = replay.TotalFrames;
            result.ExpectedHash = replay.ExpectedHash;

            // Step 2: 用初始状态初始化游戏逻辑
            gameInstance.InitializeFromSnapshot(replay.InitialState, replay.Seed);

            // Step 3: 逐帧注入输入并执行逻辑，每帧对比 Hash
            uint lastHash = 0;
            for (int f = 0; f < replay.Frames.Count; f++)
            {
                var frameInput = replay.Frames[f];

                // 将本帧的玩家输入注入游戏逻辑
                gameInstance.SetInputs(frameInput.playerInputs);

                // 执行一帧逻辑
                gameInstance.StepLogicFrame();

                // 每 30 帧计算一次状态 Hash（兼顾性能和精度）
                if (f % 30 == 0)
                {
                    uint currentHash = gameInstance.CalculateStateHash();

                    // 第一帧只记录，不对比（初始状态不同是正常的）
                    if (f == 0)
                    {
                        lastHash = currentHash;
                        continue;
                    }

                    // 对比 Hash
                    // 注意：这里对比的是增量 Hash 是否匹配，而非绝对 Hash
                    // 如果帧同步是确定性的，每一帧的 Hash 都必须一致
                    if (currentHash != lastHash && f > 0)
                    {
                        // 发现 Desync！记录但不停止——继续运行以收集更多不一致点
                        if (result.FirstDesyncFrame < 0)
                        {
                            result.FirstDesyncFrame = f;
                        }
                        result.DesyncFrames.Add(f);
                    }

                    lastHash = currentHash;
                }
            }

            // Step 4: 对比最终 Hash
            result.ActualHash = gameInstance.CalculateStateHash();
            result.Passed = (result.DesyncFrames.Count == 0)
                         && (result.ActualHash == result.ExpectedHash);

            // 即使没有逐帧 Desync，最终 Hash 也必须一致
            if (result.DesyncFrames.Count == 0 && result.ActualHash != result.ExpectedHash)
            {
                result.Passed = false;
                result.ErrorMessage = $"最终 Hash 不一致: 期望={result.ExpectedHash:X8}, 实际={result.ActualHash:X8}";
            }
        }
        catch (Exception ex)
        {
            result.Passed = false;
            result.ErrorMessage = $"异常: {ex.GetType().Name} — {ex.Message}\n{ex.StackTrace}";
        }

        sw.Stop();
        result.ExecutionTimeMs = sw.Elapsed.TotalMilliseconds;
        return result;
    }

    // ─── 批量回放测试 ──────────────────────────────────

    /// <summary>
    /// 批量运行指定目录下所有 .replay 文件的回放测试。
    /// </summary>
    /// <param name="replayDir">包含 .replay 文件的目录</param>
    /// <param name="gameFactory">游戏逻辑实例的工厂函数（每个回放需要独立实例）</param>
    /// <param name="maxParallel">最大并行回放数（默认 4）</param>
    /// <returns>汇总报告</returns>
    public static async Task<ReplayTestSummary> RunBatchReplayTests(
        string replayDir,
        Func<IReplayableGame> gameFactory,
        int maxParallel = 4)
    {
        var sw = Stopwatch.StartNew();
        var replayFiles = Directory.GetFiles(replayDir, "*.rply");

        var summary = new ReplayTestSummary
        {
            TotalReplays = replayFiles.Length,
            Details = new List<ReplayTestResult>(replayFiles.Length),
        };

        // 使用信号量控制并行度
        var semaphore = new System.Threading.SemaphoreSlim(maxParallel);
        var tasks = new List<Task>();

        foreach (var replayFile in replayFiles)
        {
            tasks.Add(Task.Run(async () =>
            {
                await semaphore.WaitAsync();
                try
                {
                    var game = gameFactory();
                    var result = RunReplayTest(replayFile, game);
                    lock (summary)
                    {
                        summary.Details.Add(result);
                        if (result.Passed) summary.Passed++;
                        else summary.Failed++;
                    }
                }
                finally
                {
                    semaphore.Release();
                }
            }));
        }

        await Task.WhenAll(tasks);

        sw.Stop();
        summary.TotalExecutionTimeMs = sw.Elapsed.TotalMilliseconds;

        return summary;
    }

    // ─── 输出报告 ──────────────────────────────────────

    /// <summary>
    /// 将汇总报告输出为 JSON 文件（方便 CI 解析）。
    /// </summary>
    public static void WriteReport(ReplayTestSummary summary, string outputPath)
    {
        var json = JsonUtility.ToJson(summary, prettyPrint: true);
        File.WriteAllText(outputPath, json);

        // 同时输出控制台摘要
        UnityEngine.Debug.Log("========== 回放测试报告 ==========");
        UnityEngine.Debug.Log($"总计: {summary.TotalReplays} 局");
        UnityEngine.Debug.Log($"通过: {summary.Passed} 局");
        UnityEngine.Debug.Log($"失败: {summary.Failed} 局");
        UnityEngine.Debug.Log($"总耗时: {summary.TotalExecutionTimeMs:F1}ms");

        if (summary.Failed > 0)
        {
            UnityEngine.Debug.LogError($"--- {summary.Failed} 局测试失败 ---");
            foreach (var detail in summary.Details)
            {
                if (!detail.Passed)
                {
                    UnityEngine.Debug.LogError(
                        $"  {detail.ReplayFile}: " +
                        $"首次Desync帧={detail.FirstDesyncFrame}, " +
                        $"Desync次数={detail.DesyncFrames.Count}, " +
                        $"期望Hash={detail.ExpectedHash:X8}, " +
                        $"实际Hash={detail.ActualHash:X8}" +
                        (string.IsNullOrEmpty(detail.ErrorMessage) ? "" : $", 错误={detail.ErrorMessage}")
                    );
                }
            }
        }
    }

    // ─── Unity 编辑器菜单入口 ──────────────────────────

#if UNITY_EDITOR
    [UnityEditor.MenuItem("Tools/Replay Test/Run All Replays (Async)")]
    public static async void RunAllReplaysFromMenu()
    {
        var replayDir = UnityEditor.EditorUtility.OpenFolderPanel(
            "选择 .replay 文件目录", Application.dataPath, "");
        if (string.IsNullOrEmpty(replayDir)) return;

        UnityEngine.Debug.Log($"[ReplayTest] 开始批量回放测试: {replayDir}");

        var summary = await RunBatchReplayTests(
            replayDir,
            () => new MyGameLogic()  // 替换为你的游戏逻辑类型
        );

        var reportPath = Path.Combine(Application.dataPath, "../replay_test_report.json");
        WriteReport(summary, reportPath);
        UnityEngine.Debug.Log($"[ReplayTest] 报告已保存到: {reportPath}");
    }
#endif

    // ─── CI 入口 (batchmode) ──────────────────────────

    /// <summary>
    /// CI batchmode 入口点。
    /// 命令行: unity -batchmode -executeMethod AutomatedReplayTester.RunFromCI --replayDir ./replays
    /// </summary>
    public static void RunFromCI()
    {
        string[] args = Environment.GetCommandLineArgs();
        string replayDir = "./replays";
        string reportPath = "./replay_test_report.json";

        // 解析命令行参数
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--replayDir" && i + 1 < args.Length)
                replayDir = args[++i];
            if (args[i] == "--reportPath" && i + 1 < args.Length)
                reportPath = args[++i];
        }

        // 同步运行（batchmode 不支持 async）
        var summary = RunBatchReplayTests(replayDir, () => new MyGameLogic()).Result;
        WriteReport(summary, reportPath);

        // CI 约定的退出码: 0=成功, 1=失败
        if (summary.Failed > 0)
        {
            Environment.ExitCode = 1;
        }
    }
}

/// <summary>
/// 可回放的游戏的接口——你的游戏逻辑类必须实现这个接口。
/// </summary>
public interface IReplayableGame
{
    /// <summary>从快照还原初始状态。</summary>
    void InitializeFromSnapshot(byte[] snapshot, uint seed);

    /// <summary>设置本帧的玩家输入。</summary>
    void SetInputs(Dictionary<int, uint> playerInputs);

    /// <summary>执行一帧逻辑（FixedUpdate/逻辑Tick）。</summary>
    void StepLogicFrame();

    /// <summary>计算当前状态的 Hash（用于确定性校验）。</summary>
    uint CalculateStateHash();
}
```

### 3.4 帧同步特有的"确定性回归测试"

帧同步对确定性有硬性要求。任何改动——哪怕只是把 `float` 换成 `double`、把 `List.Sort()` 换成 `OrderBy()`、甚至升级编译器版本——都可能破坏确定性。

**关键策略**：

1. **基线 Hash 库**：在代码仓库中维护一份"黄金 Hash 列表"。每次对局代码变更后，重新回放所有历史回放文件，新 Hash 必须与黄金 Hash 完全一致。
2. **跨平台回放**：同一份 .replay 文件在 Windows、macOS、Linux、Android、iOS 上回放，Hash 必须完全一致。
3. **编译器版本锁定**：确定性依赖编译器行为——浮点运算、内联优化、结构体布局都必须一致。CI 中锁定编译器版本（如使用特定 Docker 镜像）。
4. **CI 强制门**：任何导致 Hash 改变的 PR 必须被 CI 阻断，除非开发者明确说明该变更是"有意改变 Hash 的架构变更"。

---

## 4. 混沌工程 (Chaos Engineering)

### 4.1 原理

混沌工程的核心原则是：**与其等待故障发生，不如主动制造故障来验证系统在故障下的行为**。Netflix 在 2010 年首次系统化地实践了混沌工程——用 Chaos Monkey 随机终止生产环境的 EC2 实例。

对游戏网络同步，混沌工程回答的问题是：

- 如果**任意随机组合**的故障同时发生，系统会怎样？
- 系统是否总能**优雅降级**（玩家不掉线）？
- 故障恢复后，状态是否**完好无损**？

混沌工程与链路仿真（第 2 节）的核心区别：

| 维度 | 链路仿真 (L1) | 混沌工程 (L3) |
|------|-------------|-------------|
| 目标 | 验证已知风险 | 探索未知边界 |
| 故障类型 | 固定参数的网络条件 | 随机组合的多种故障 |
| 故障频率 | 持续施加 | 随机间歇注入 |
| 验证方式 | "在 200ms 延迟下能玩" | "任意故障组合下不崩溃、能恢复" |

### 4.2 C# ChaosMonkey 完整实现

```csharp
// ============================================
// ChaosMonkey.cs — 混沌工程网络故障注入器
// ============================================
// 用途：
//   1. 按概率随机注入多种网络故障
//   2. 支持故障类型：延迟尖刺、丢包爆发、断连、限速、乱序
//   3. 记录每次故障事件的时间、类型、持续时间
//   4. 提供监控 API 供外部观察系统恢复行为
// ============================================
// 设计原则：
//   - 故障注入在独立线程中运行，不阻塞游戏主循环
//   - 故障有明确的开始/结束时间戳，方便与监控指标对齐
//   - 所有故障参数可通过 Inspector 或代码动态调整
// ============================================

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Random = UnityEngine.Random;

/// <summary>
/// 故障事件记录。
/// </summary>
[Serializable]
public struct ChaosEvent
{
    public string EventType;        // 故障类型: "LagSpike", "LossBurst", "Disconnect", "BandwidthCap", "ReorderBurst"
    public float StartTime;         // 开始时间 (Time.realtimeSinceStartup)
    public float Duration;          // 持续时间 (秒)
    public string Parameters;       // 故障参数 (JSON 字符串)
}

/// <summary>
/// 混沌工程故障注入器。
/// 挂载到场景中即可自动运行。
/// </summary>
public class ChaosMonkey : MonoBehaviour
{
    [Header("总开关")]
    [SerializeField] private bool _enableChaos = true;

    [Header("故障: 延迟尖刺")]
    [Tooltip("每 60 秒有概率注入一次随机延迟尖刺")]
    [SerializeField] private bool _enableLagSpike = true;
    [SerializeField] [Range(0, 1)] private float _lagSpikeProbability = 0.2f;
    [SerializeField] private float _lagSpikeInterval = 60f;
    [SerializeField] private float _lagSpikeMinMs = 200f;
    [SerializeField] private float _lagSpikeMaxMs = 800f;
    [SerializeField] private float _lagSpikeMinDuration = 1f;
    [SerializeField] private float _lagSpikeMaxDuration = 5f;

    [Header("故障: 丢包爆发")]
    [Tooltip("每 90 秒有概率注入一次随机丢包爆发")]
    [SerializeField] private bool _enableLossBurst = true;
    [SerializeField] [Range(0, 1)] private float _lossBurstProbability = 0.15f;
    [SerializeField] private float _lossBurstInterval = 90f;
    [SerializeField] [Range(0, 100)] private float _lossBurstMinPercent = 10f;
    [SerializeField] [Range(0, 100)] private float _lossBurstMaxPercent = 40f;
    [SerializeField] private float _lossBurstMinDuration = 2f;
    [SerializeField] private float _lossBurstMaxDuration = 8f;

    [Header("故障: 随机断连")]
    [Tooltip("每 120 秒有概率断开一个随机客户端")]
    [SerializeField] private bool _enableDisconnect = true;
    [SerializeField] [Range(0, 1)] private float _disconnectProbability = 0.1f;
    [SerializeField] private float _disconnectInterval = 120f;
    [SerializeField] private float _disconnectMinDuration = 3f;
    [SerializeField] private float _disconnectMaxDuration = 10f;

    [Header("故障: 带宽限制")]
    [Tooltip("每 150 秒有概率限制带宽")]
    [SerializeField] private bool _enableBandwidthCap = true;
    [SerializeField] [Range(0, 1)] private float _bandwidthCapProbability = 0.08f;
    [SerializeField] private float _bandwidthCapInterval = 150f;
    [SerializeField] private float _bandwidthCapMinKbps = 16f;
    [SerializeField] private float _bandwidthCapMaxKbps = 64f;
    [SerializeField] private float _bandwidthCapMinDuration = 5f;
    [SerializeField] private float _bandwidthCapMaxDuration = 15f;

    [Header("故障: 包乱序")]
    [Tooltip("每 100 秒有概率注入包乱序")]
    [SerializeField] private bool _enableReorderBurst = true;
    [SerializeField] [Range(0, 1)] private float _reorderProbability = 0.12f;
    [SerializeField] private float _reorderInterval = 100f;
    [SerializeField] private float _reorderMinDuration = 2f;
    [SerializeField] private float _reorderMaxDuration = 6f;

    // ─── 运行时状态 ────────────────────────────────────

    private NetworkSimulationManager _netSim;
    private NetworkConditionProfile _originalProfile;  // 保存原始网络条件

    // 事件历史（环形缓冲区）
    private readonly Queue<ChaosEvent> _eventHistory = new Queue<ChaosEvent>();
    private const int MaxEventHistory = 200;

    // 各类故障的计时器
    private float _lagSpikeTimer;
    private float _lossBurstTimer;
    private float _disconnectTimer;
    private float _bandwidthCapTimer;
    private float _reorderTimer;

    // 当前活跃的故障协程
    private readonly List<Coroutine> _activeChaosCoroutines = new List<Coroutine>();

    // ─── 公共 API ──────────────────────────────────────

    /// <summary>获取故障事件历史（倒序，最新的在前）。</summary>
    public List<ChaosEvent> GetEventHistory()
    {
        var list = new List<ChaosEvent>(_eventHistory);
        list.Reverse();
        return list;
    }

    /// <summary>获取当前活跃的故障数量。</summary>
    public int GetActiveChaosCount() => _activeChaosCoroutines.Count;

    /// <summary>获取自启动以来注入的故障总次数。</summary>
    public int GetTotalChaosEventCount() => _eventHistory.Count;

    /// <summary>手动触发一次指定类型的故障（用于调试）。</summary>
    public void TriggerManual(string chaosType)
    {
        switch (chaosType)
        {
            case "LagSpike":
                StartCoroutine(InjectLagSpike(Random.Range(_lagSpikeMinMs, _lagSpikeMaxMs),
                    Random.Range(_lagSpikeMinDuration, _lagSpikeMaxDuration)));
                break;
            case "LossBurst":
                StartCoroutine(InjectLossBurst(
                    Random.Range(_lossBurstMinPercent, _lossBurstMaxPercent),
                    Random.Range(_lossBurstMinDuration, _lossBurstMaxDuration)));
                break;
            case "Disconnect":
                StartCoroutine(InjectDisconnect(
                    Random.Range(_disconnectMinDuration, _disconnectMaxDuration)));
                break;
            case "BandwidthCap":
                StartCoroutine(InjectBandwidthCap(
                    Random.Range(_bandwidthCapMinKbps, _bandwidthCapMaxKbps),
                    Random.Range(_bandwidthCapMinDuration, _bandwidthCapMaxDuration)));
                break;
        }
    }

    // ─── 生命周期 ──────────────────────────────────────

    private void Awake()
    {
        DontDestroyOnLoad(gameObject);
    }

    private void Start()
    {
        _netSim = FindObjectOfType<NetworkSimulationManager>();
        if (_netSim != null)
        {
            _originalProfile = _netSim.GetCurrentProfile();
        }

        // 初始化计时器为随机偏置——避免所有故障同时触发
        _lagSpikeTimer = Random.Range(0, _lagSpikeInterval);
        _lossBurstTimer = Random.Range(0, _lossBurstInterval);
        _disconnectTimer = Random.Range(0, _disconnectInterval);
        _bandwidthCapTimer = Random.Range(0, _bandwidthCapInterval);
        _reorderTimer = Random.Range(0, _reorderInterval);

        Debug.Log("[ChaosMonkey] 混沌猴子已就绪。请系好安全带。");
    }

    private void Update()
    {
        if (!_enableChaos) return;

        float now = Time.realtimeSinceStartup;

        // ─── 延迟尖刺 ──────────────────────────────────
        if (_enableLagSpike)
        {
            _lagSpikeTimer -= Time.unscaledDeltaTime;
            if (_lagSpikeTimer <= 0)
            {
                _lagSpikeTimer = _lagSpikeInterval;
                if (Random.value < _lagSpikeProbability)
                {
                    float spikeMs = Random.Range(_lagSpikeMinMs, _lagSpikeMaxMs);
                    float duration = Random.Range(_lagSpikeMinDuration, _lagSpikeMaxDuration);
                    StartCoroutine(InjectLagSpike(spikeMs, duration));
                }
            }
        }

        // ─── 丢包爆发 ──────────────────────────────────
        if (_enableLossBurst)
        {
            _lossBurstTimer -= Time.unscaledDeltaTime;
            if (_lossBurstTimer <= 0)
            {
                _lossBurstTimer = _lossBurstInterval;
                if (Random.value < _lossBurstProbability)
                {
                    float lossPercent = Random.Range(_lossBurstMinPercent, _lossBurstMaxPercent);
                    float duration = Random.Range(_lossBurstMinDuration, _lossBurstMaxDuration);
                    StartCoroutine(InjectLossBurst(lossPercent, duration));
                }
            }
        }

        // ─── 随机断连 ──────────────────────────────────
        if (_enableDisconnect)
        {
            _disconnectTimer -= Time.unscaledDeltaTime;
            if (_disconnectTimer <= 0)
            {
                _disconnectTimer = _disconnectInterval;
                if (Random.value < _disconnectProbability)
                {
                    float duration = Random.Range(_disconnectMinDuration, _disconnectMaxDuration);
                    StartCoroutine(InjectDisconnect(duration));
                }
            }
        }

        // ─── 带宽限制 ──────────────────────────────────
        if (_enableBandwidthCap)
        {
            _bandwidthCapTimer -= Time.unscaledDeltaTime;
            if (_bandwidthCapTimer <= 0)
            {
                _bandwidthCapTimer = _bandwidthCapInterval;
                if (Random.value < _bandwidthCapProbability)
                {
                    float capKbps = Random.Range(_bandwidthCapMinKbps, _bandwidthCapMaxKbps);
                    float duration = Random.Range(_bandwidthCapMinDuration, _bandwidthCapMaxDuration);
                    StartCoroutine(InjectBandwidthCap(capKbps, duration));
                }
            }
        }

        // ─── 包乱序 ────────────────────────────────────
        if (_enableReorderBurst)
        {
            _reorderTimer -= Time.unscaledDeltaTime;
            if (_reorderTimer <= 0)
            {
                _reorderTimer = _reorderInterval;
                if (Random.value < _reorderProbability)
                {
                    float duration = Random.Range(_reorderMinDuration, _reorderMaxDuration);
                    StartCoroutine(InjectReorder(duration));
                }
            }
        }
    }

    // ─── 故障注入协程 ──────────────────────────────────

    /// <summary>
    /// 注入延迟尖刺：临时将延迟飙升到极高水平。
    /// 模拟场景：手机从 WiFi 切换到 4G、进入电梯、基站切换。
    /// </summary>
    private IEnumerator InjectLagSpike(float spikeMs, float duration)
    {
        float startTime = Time.realtimeSinceStartup;
        LogEvent("LagSpike", startTime, duration,
            $"{{'spikeMs': {spikeMs:F0}, 'duration': {duration:F1}}}");
        Debug.LogWarning($"[ChaosMonkey] 延迟尖刺: {spikeMs:F0}ms, 持续 {duration:F1}s");

        // 应用尖刺
        if (_netSim != null)
        {
            _netSim.SetDelayTemporarily((int)spikeMs);
        }

        yield return new WaitForSecondsRealtime(duration);

        // 恢复
        if (_netSim != null)
        {
            _netSim.ApplyPreset(0); // 恢复 LAN
        }

        Debug.Log($"[ChaosMonkey] 延迟尖刺已结束 (持续 {Time.realtimeSinceStartup - startTime:F1}s)");
    }

    /// <summary>
    /// 注入丢包爆发：临时将丢包率提升到极高水平。
    /// 模拟场景：WiFi 2.4GHz 频段干扰（微波炉、蓝牙）、4G 拥塞。
    /// </summary>
    private IEnumerator InjectLossBurst(float lossPercent, float duration)
    {
        float startTime = Time.realtimeSinceStartup;
        LogEvent("LossBurst", startTime, duration,
            $"{{'lossPercent': {lossPercent:F1}, 'duration': {duration:F1}}}");
        Debug.LogWarning($"[ChaosMonkey] 丢包爆发: {lossPercent:F1}%, 持续 {duration:F1}s");

        if (_netSim != null)
        {
            var p = _netSim.GetCurrentProfile();
            _netSim.ApplyCustom(p.packetDelayMs, p.packetJitterMs, (int)lossPercent);
        }

        yield return new WaitForSecondsRealtime(duration);

        if (_netSim != null)
        {
            _netSim.ApplyPreset(0);
        }

        Debug.Log($"[ChaosMonkey] 丢包爆发已结束");
    }

    /// <summary>
    /// 注入随机断连：完全断开一个客户端的网络连接。
    /// 模拟场景：进入电梯/隧道、飞行模式误触、App 切后台被系统挂起。
    /// 这是对重连系统的直接压力测试。
    /// </summary>
    private IEnumerator InjectDisconnect(float duration)
    {
        float startTime = Time.realtimeSinceStartup;
        LogEvent("Disconnect", startTime, duration, $"{{'duration': {duration:F1}}}");
        Debug.LogWarning($"[ChaosMonkey] 客户端断连: {duration:F1}s");

        // 方法 1：通过 NetworkSimulator 设置 100% 丢包率
        if (_netSim != null)
        {
            var p = _netSim.GetCurrentProfile();
            _netSim.ApplyCustom(p.packetDelayMs, p.packetJitterMs, 100);
        }

        yield return new WaitForSecondsRealtime(duration);

        // 恢复连接
        if (_netSim != null)
        {
            _netSim.ApplyPreset(0);
        }

        Debug.Log($"[ChaosMonkey] 客户端已重连 (断连 {Time.realtimeSinceStartup - startTime:F1}s)");
    }

    /// <summary>
    /// 注入带宽限制：将出站带宽限制到极低水平。
    /// 模拟场景：2G 网络、运营商限速、公共 WiFi 限速。
    /// </summary>
    private IEnumerator InjectBandwidthCap(float capKbps, float duration)
    {
        float startTime = Time.realtimeSinceStartup;
        LogEvent("BandwidthCap", startTime, duration,
            $"{{'capKbps': {capKbps:F0}, 'duration': {duration:F1}}}");
        Debug.LogWarning($"[ChaosMonkey] 带宽限制: {capKbps:F0}Kbps, 持续 {duration:F1}s");

        // 注意：NetworkSimulator 可能不直接支持带宽限制
        // 实际项目中需要结合系统级工具 (tc/clumsy) 或自定义 UGS 中继
        yield return new WaitForSecondsRealtime(duration);

        Debug.Log($"[ChaosMonkey] 带宽限制已解除");
    }

    /// <summary>
    /// 注入包乱序：随机打乱数据包的到达顺序。
    /// 模拟场景：多路径路由 (MPTCP)、负载均衡器分片。
    /// </summary>
    private IEnumerator InjectReorder(float duration)
    {
        float startTime = Time.realtimeSinceStartup;
        LogEvent("ReorderBurst", startTime, duration, $"{{'duration': {duration:F1}}}");

        // 包乱序注入通常需要在传输层实现
        // 这里通过 NetworkSimulator 的随机延迟模拟（不同包不同延迟 = 可能乱序）
        if (_netSim != null)
        {
            var p = _netSim.GetCurrentProfile();
            // 设置极高的抖动来模拟乱序（延迟 50ms ± 50ms = 0-100ms 随机延迟）
            _netSim.ApplyCustom(p.packetDelayMs, 50, p.packetLossPercent);
        }

        yield return new WaitForSecondsRealtime(duration);

        if (_netSim != null)
        {
            _netSim.ApplyPreset(0);
        }

        Debug.Log($"[ChaosMonkey] 包乱序注入已结束");
    }

    // ─── 工具方法 ──────────────────────────────────────

    private void LogEvent(string eventType, float startTime, float duration, string parameters)
    {
        var evt = new ChaosEvent
        {
            EventType = eventType,
            StartTime = startTime,
            Duration = duration,
            Parameters = parameters,
        };

        _eventHistory.Enqueue(evt);
        while (_eventHistory.Count > MaxEventHistory)
        {
            _eventHistory.Dequeue();
        }
    }
}
```

### 4.3 混沌测试的运行策略

混沌工程测试不应该无限期运行——它应该在**有明确成功/失败标准的监督下**运行：

```
混沌测试通过标准 (示例):

1. 客户端不崩溃: 测试期间零崩溃 (CrashSight 数据)
2. 重连成功率 ≥ 95%: 断连事件后 10 秒内成功重连
3. 帧缓冲恢复: 故障结束后 5 秒内缓冲恢复到安全水位 (≥ 3 帧)
4. 状态一致性: 故障前后 Hash 一致 (帧同步) 或偏差 < 阈值 (状态同步)
5. 对局不中断: 测试结束时对局仍然存活 (未超时/未解散)
```

**渐进式混沌测试计划**：

```
Phase 1 (沙盒): 1 个客户端 + 1 个服务器, 低频率 (概率 × 0.5), 运行 5 分钟
Phase 2 (多客户端): 4 个客户端, 正常频率, 运行 10 分钟
Phase 3 (CI 快速): 2 个客户端, 正常频率, 运行 3 分钟 (每次 PR)
Phase 4 (CI 完整): 8 个客户端, 高频率 (概率 × 2), 运行 20 分钟 (Nightly Build)
```

---

## 5. CI/CD 集成

前面三部分（链路仿真、回放测试、混沌工程）最终要落到 CI 管道中，成为每次提交的自动化质量门。

### 5.1 分层测试策略

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CI 网络测试分层策略                            │
├──────────┬────────────┬──────────────────┬─────────────────────────┤
│  层级     │  触发条件   │  测试内容          │  耗时     │ 通过标准    │
├──────────┼────────────┼──────────────────┼──────────┼────────────┤
│  L0 单元  │  每次 PR    │  组件单元测试       │  < 2min  │ 100% 通过  │
│          │            │  (正常网络条件)     │          │            │
├──────────┼────────────┼──────────────────┼──────────┼────────────┤
│  L1 弱网  │  每次 PR    │  回放测试 × 50 局   │  ~5min   │ 100% 通过  │
│          │            │  网络: 4G + 弱信号  │          │            │
├──────────┼────────────┼──────────────────┼──────────┼────────────┤
│  L2 回放  │  每次 PR    │  回放测试 × 200 局  │  ~15min  │ 100% 通过  │
│          │            │  网络: LAN         │          │            │
├──────────┼────────────┼──────────────────┼──────────┼────────────┤
│  L3 混沌  │  Nightly   │  ChaosMonkey × 20min│ ~25min  │ 0 崩溃    │
│          │  或 Release │  + 回放 × 500 局   │          │ ≥95% 重连 │
├──────────┼────────────┼──────────────────┼──────────┼────────────┤
│  L4 极限  │  Release   │  回放 × 2000 局     │  ~2h     │ 0 Desync  │
│          │  候选版本   │  + 全网络条件矩阵    │          │            │
└──────────┴────────────┴──────────────────┴──────────┴────────────┘
```

### 5.2 GitHub Actions 完整配置示例

```yaml
# ============================================
# .github/workflows/network-sync-tests.yml
# 网络同步测试 — 每次 PR 和 Push 自动触发
# ============================================

name: Network Sync Tests

on:
  pull_request:
    branches: [main, develop]
    paths:
      # 只在与游戏逻辑/网络相关的文件变更时触发
      - 'Assets/Scripts/GameLogic/**'
      - 'Assets/Scripts/Network/**'
      - 'Packages/**'
  push:
    branches: [main]
  schedule:
    # 每日凌晨 3:00 UTC 运行完整混沌测试
    - cron: '0 3 * * *'

# 取消同一 PR 的旧运行（节省 CI 资源）
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  UNITY_VERSION: '2022.3.20f1'
  DOTNET_VERSION: '6.0'

jobs:
  # ──────────────────────────────────────────
  # Job 1: 单元测试 (L0)
  # ──────────────────────────────────────────
  unit-tests:
    name: 'L0: Unit Tests'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}

      - name: Run Unit Tests
        run: |
          dotnet test Tests/GameLogic.Tests/GameLogic.Tests.csproj \
            --configuration Release \
            --logger "trx;LogFileName=unit_test_results.trx" \
            --results-directory TestResults

      - name: Upload Test Results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unit-test-results
          path: TestResults/

  # ──────────────────────────────────────────
  # Job 2: 弱网回放测试 (L1)
  # ──────────────────────────────────────────
  weak-network-replay:
    name: 'L1: Weak Network Replay (50 matches)'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    needs: unit-tests  # 先跑快速测试，失败则跳过
    steps:
      - uses: actions/checkout@v4

      - name: Setup network emulation (tc netem)
        run: |
          # 模拟 4G 移动网络: 60ms 延迟, ±20ms 抖动, 2% 丢包
          sudo tc qdisc add dev eth0 root netem \
            delay 60ms 20ms distribution normal \
            loss 2% 25%
          echo "Network emulation: 4G Mobile (60ms delay, 20ms jitter, 2% loss)"

      - name: Run Weak Network Replay Tests
        run: |
          # 使用 Unity batchmode 运行回放测试
          # --replayDir: 回放文件目录
          # --reportPath: 输出报告路径
          /opt/unity/Editor/Unity \
            -batchmode \
            -nographics \
            -quit \
            -projectPath ${{ github.workspace }} \
            -executeMethod AutomatedReplayTester.RunWeakNetworkTests \
            -logFile unity_weak_replay.log

      - name: Upload Replay Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: weak-replay-report
          path: |
            replay_weak_report.json
            unity_weak_replay.log

      - name: Cleanup netem
        if: always()
        run: sudo tc qdisc del dev eth0 root 2>/dev/null || true

      - name: Verify Results
        run: |
          # 检查报告中的通过率 — 必须 100%
          if [ -f replay_weak_report.json ]; then
            FAILED=$(jq '.Failed' replay_weak_report.json)
            if [ "$FAILED" -gt 0 ]; then
              echo "::error::弱网回放测试失败: $FAILED 局未通过"
              exit 1
            fi
            echo "弱网回放测试: 全部通过 ($(jq '.Passed' replay_weak_report.json)/$(jq '.TotalReplays' replay_weak_report.json))"
          else
            echo "::warning::未生成回放报告文件"
          fi

  # ──────────────────────────────────────────
  # Job 3: 标准回放测试 (L2)
  # ──────────────────────────────────────────
  standard-replay:
    name: 'L2: Standard Replay (200 matches)'
    runs-on: ubuntu-latest
    timeout-minutes: 25
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4

      - name: Run Standard Replay Tests
        run: |
          /opt/unity/Editor/Unity \
            -batchmode \
            -nographics \
            -quit \
            -projectPath ${{ github.workspace }} \
            -executeMethod AutomatedReplayTester.RunFromCI \
            --replayDir ./TestData/Replays \
            --reportPath replay_standard_report.json \
            -logFile unity_standard_replay.log

      - name: Upload Standard Replay Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: standard-replay-report
          path: |
            replay_standard_report.json
            unity_standard_replay.log

      - name: Verify Results
        run: |
          if [ -f replay_standard_report.json ]; then
            FAILED=$(jq '.Failed' replay_standard_report.json)
            if [ "$FAILED" -gt 0 ]; then
              echo "::error::标准回放测试失败: $FAILED 局未通过 (这意味着存在 Desync bug！)"
              # 输出失败详情
              jq '.Details[] | select(.Passed == false) | {File: .ReplayFile, DesyncFrame: .FirstDesyncFrame, ExpectedHash: .ExpectedHash, ActualHash: .ActualHash}' replay_standard_report.json
              exit 1
            fi
            echo "标准回放测试: 全部通过"
          fi

  # ──────────────────────────────────────────
  # Job 4: 混沌工程测试 (L3) — 仅 Nightly
  # ──────────────────────────────────────────
  chaos-engineering:
    name: 'L3: Chaos Engineering (Nightly)'
    runs-on: ubuntu-latest
    timeout-minutes: 40
    if: github.event_name == 'schedule' || github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4

      - name: Setup Chaos Environment
        run: |
          # 不预设网络条件——让 ChaosMonkey 自行注入故障
          echo "Chaos Monkey ready. 20 minutes of chaos ahead."
          # 创建混沌测试结果目录
          mkdir -p chaos_results

      - name: Run Chaos Test
        run: |
          /opt/unity/Editor/Unity \
            -batchmode \
            -nographics \
            -quit \
            -projectPath ${{ github.workspace }} \
            -executeMethod ChaosMonkeyTestRunner.RunChaosTest \
            --duration 1200 \
            --reportPath chaos_results/chaos_report.json \
            -logFile chaos_results/unity_chaos.log

      - name: Upload Chaos Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: chaos-report
          path: chaos_results/

      - name: Verify Chaos Results
        run: |
          if [ -f chaos_results/chaos_report.json ]; then
            # 检查关键指标
            CRASHES=$(jq '.Crashes' chaos_results/chaos_report.json)
            RECONNECT_RATE=$(jq '.ReconnectSuccessRate' chaos_results/chaos_report.json)
            GAME_ALIVE=$(jq '.GameSurvived' chaos_results/chaos_report.json)

            echo "混沌测试结果:"
            echo "  崩溃次数: $CRASHES"
            echo "  重连成功率: $RECONNECT_RATE%"
            echo "  对局存活: $GAME_ALIVE"

            if [ "$CRASHES" -gt 0 ]; then
              echo "::error::混沌测试期间发生 $CRASHES 次崩溃！"
              exit 1
            fi

            # 使用 bc 做浮点比较
            if (( $(echo "$RECONNECT_RATE < 95" | bc -l) )); then
              echo "::error::重连成功率 $RECONNECT_RATE% 低于阈值 95%！"
              exit 1
            fi

            if [ "$GAME_ALIVE" != "true" ]; then
              echo "::error::对局在混沌测试中终止！"
              exit 1
            fi

            echo "✅ 混沌测试通过"
          fi

  # ──────────────────────────────────────────
  # Job 5: 多平台回放测试 (L4) — 仅 Release
  # ──────────────────────────────────────────
  cross-platform-replay:
    name: 'L4: Cross-Platform Replay (${{ matrix.os }})'
    runs-on: ${{ matrix.os }}
    timeout-minutes: 120
    if: startsWith(github.ref, 'refs/tags/v')
    strategy:
      fail-fast: false  # 一个平台失败不影响其他平台
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    steps:
      - uses: actions/checkout@v4

      - name: Run Cross-Platform Replay (2000 matches)
        run: |
          /opt/unity/Editor/Unity \
            -batchmode \
            -nographics \
            -quit \
            -projectPath ${{ github.workspace }} \
            -executeMethod AutomatedReplayTester.RunCrossPlatformTests \
            --replayDir ./TestData/Replays \
            --reportPath "replay_cross_${{ matrix.os }}_report.json" \
            --platform ${{ runner.os }} \
            -logFile "unity_cross_${{ matrix.os }}.log"

      - name: Upload Cross-Platform Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: cross-platform-report-${{ matrix.os }}
          path: |
            replay_cross_${{ matrix.os }}_report.json
            unity_cross_${{ matrix.os }}.log

  # ──────────────────────────────────────────
  # Job 6: Jenkins 替代方案（兼容性示例）
  # ──────────────────────────────────────────
  # 如果团队使用 Jenkins 而非 GitHub Actions:
  #
  # Jenkinsfile (Declarative Pipeline):
  #
  # pipeline {
  #   agent any
  #   environment {
  #     UNITY_HOME = '/opt/unity/2022.3.20f1'
  #   }
  #   stages {
  #     stage('L1: Weak Network') {
  #       steps {
  #         sh '''
  #           sudo tc qdisc add dev eth0 root netem delay 60ms 20ms loss 2%
  #           ${UNITY_HOME}/Editor/Unity -batchmode -nographics -quit \
  #             -projectPath . -executeMethod AutomatedReplayTester.RunWeakNetworkTests
  #           sudo tc qdisc del dev eth0 root
  #         '''
  #       }
  #     }
  #     stage('L2: Standard Replay') {
  #       steps {
  #         sh '${UNITY_HOME}/Editor/Unity -batchmode -nographics -quit \
  #           -projectPath . -executeMethod AutomatedReplayTester.RunFromCI'
  #       }
  #     }
  #   }
  #   post {
  #     always {
  #       archiveArtifacts artifacts: '*.json, *.log'
  #       junit 'TestResults/*.trx'
  #     }
  #   }
  # }
```

### 5.3 测试通过标准总结

```
CI 质量门标准 (必须全部满足才能合并 PR):

L0 单元测试:
  ✅ 所有单元测试通过 (0 failures)
  ✅ 代码覆盖率 > 70% (游戏逻辑代码)

L1 弱网回放:
  ✅ 50 局回放 0 次 Desync
  ✅ 4G 条件下帧缓冲平均消耗率 < 50%

L2 标准回放:
  ✅ 200 局回放 0 次 Desync
  ✅ 跨平台 Hash 完全一致 (如果代码变更是逻辑相关的)

L3 混沌 (Nightly):
  ✅ 20 分钟混沌测试 0 次崩溃
  ✅ 重连成功率 ≥ 95%
  ✅ 故障恢复后帧缓冲 < 5 秒恢复到安全水位

L4 极限 (Release):
  ✅ 2000 局回放 0 次 Desync
  ✅ 全网络条件矩阵 (5 种 × 3 平台 = 15 种组合) 全部通过
  ✅ 混沌测试重连成功率 ≥ 98%
```

---

## 6. 练习

### 练习 1：搭建网络模拟测试矩阵 [基础]

**目标**：用你已有的同步 Demo（帧同步或状态同步均可）搭建第 2.3 节描述的测试矩阵，量化不同网络条件下的同步质量。

**要求**：

1. 选择一个已完成的前置教程 Demo（教程 08/09/10 的帧同步，或 18/19/20 的状态同步）
2. 使用 Unity NetworkSimulator（或 UE net.PktLag）或系统级工具（clumsy/tc netem），搭建以下 5 种网络条件：

| 场景 | 延迟 | 抖动 | 丢包率 |
|------|------|------|--------|
| A: LAN | 0ms | 0ms | 0% |
| B: WiFi 良好 | 15ms | 5ms | 1% |
| C: 4G | 60ms | 20ms | 2% |
| D: 弱信号 | 200ms | 80ms | 8% |
| E: 极端 | 500ms | 150ms | 15% |

3. 对每种条件运行 60 秒，记录以下指标：
   - 帧同步：帧缓冲消耗率、Desync 次数（如果有 Hash 检查）
   - 状态同步：预测误差平均值/峰值、服务端和解次数、RPC 平均延迟
4. 将结果导出为 CSV，用表格或简单图表对比
5. 回答：你的 Demo 在哪些条件下仍能正常游戏？在哪些条件下开始出现明显问题？最差条件下是否还能接受？

**提示**：
- 使用 `Time.realtimeSinceStartup` 或 `std::chrono` 做精确计时
- 如果要自动化，写一个 `TestRunner` 脚本：切换网络条件 → 等待 60s → 记录指标 → 切换下一个
- CSV 格式：`Scenario,Delay,Jitter,Loss,BufferDrainRate,DesyncCount,…`

---

### 练习 2：实现确定性回放测试 [进阶]

**目标**：基于第 3.3 节的 `AutomatedReplayTester`，为你的帧同步 Demo 实现完整的录制→回放→验证闭环。

**要求**：

1. **录制端**：在帧同步 Demo 中添加录制功能：
   - 在对局开始时保存初始状态快照和随机种子
   - 每逻辑帧记录所有玩家的输入指令（playerId → inputData）
   - 对局结束时计算最终状态 Hash
   - 将以上数据写入 `.replay` 文件（使用第 3.3 节定义的二进制格式）

2. **回放端**：实现回放功能：
   - 加载 `.replay` 文件
   - 用初始状态和种子初始化游戏逻辑
   - 逐帧注入输入，执行逻辑，每 30 帧计算状态 Hash
   - 对比最终 Hash 与录制时的预期 Hash

3. **验证**：
   - 录制一局本地对局（2 个 AI 玩家自动对战 5 分钟）
   - 立即回放同一份文件，确认 Hash 一致（通过）
   - 故意修改某行逻辑代码（如把伤害系数 +0.1），重新回放，确认 Hash 不一致（失败——这就是 Desync 检测的威力）
   - 截图或记录：修改前回放通过，修改后回放失败

4. **批量回放**（可选）：录制 10 局不同种子/不同 AI 策略的对局，批量回放，输出汇总报告

**提示**：
- Hash 计算只包含逻辑状态数据（实体位置、血量、技能 CD），不包含渲染/动画/粒子
- 遍历容器时使用有序方式（C# 的 `SortedDictionary` 或 `.OrderBy()`）
- 录制时使用 `MemoryStream` + `BinaryWriter` 构建内存缓冲区，对局结束后一次性写入磁盘（避免每帧 IO）
- 初始状态快照必须包含所有实体的完整数据——包括"空闲"状态的实体

---

### 练习 3：混沌工程——故障注入与恢复验证 [挑战]

**目标**：基于第 4.2 节的 `ChaosMonkey`，为同步系统构建故障注入框架，验证容错能力。

**要求**：

1. 在同步 Demo 中集成 `ChaosMonkey`，开启全部 5 种故障注入：
   - 延迟尖刺：每 60s，20% 概率，200-800ms，持续 1-5s
   - 丢包爆发：每 90s，15% 概率，10-40%，持续 2-8s
   - 随机断连：每 120s，10% 概率，持续 3-10s
   - 带宽限制：每 150s，8% 概率，16-64Kbps，持续 5-15s
   - 包乱序：每 100s，12% 概率，持续 2-6s

2. 运行 10 分钟混沌测试，监控以下恢复指标：
   - **崩溃次数**：测试期间是否发生崩溃（查询 CrashSight 或本地日志）
   - **重连成功率**：断连事件后 10 秒内成功重连的比例
   - **帧缓冲恢复时间**：故障结束后，缓冲恢复到安全水位的时间（< 5s = 通过）
   - **状态一致性**：故障前后状态 Hash 是否一致（帧同步）/ 偏差是否 < 阈值（状态同步）
   - **对局存活**：测试结束时对局是否仍在运行

3. 输出混沌测试报告（JSON 格式），包含：
   - 故障事件列表（类型、时间、参数）
   - 恢复指标汇总
   - 通过/失败判定

4. 分析系统最薄弱的环节：
   - 哪种故障恢复最慢？
   - 哪些故障组合会导致不可恢复的状态？
   - 如果有失败，根本原因是什么？（重连逻辑 bug？缓冲设计缺陷？超时时间太短？）

5. **（挑战）**将 ChaosMonkey 改造为可以独立运行的命令行工具：
   - 启动服务器 + 4 个 AI 客户端
   - 在服务器上运行 ChaosMonkey（注入出站故障）或客户端上运行（注入入站故障）
   - 命令行：`chaos_test --duration 600 --clients 4 --report chaos_report.json`
   - 适用于 CI 集成

**提示**：
- 故障注入在独立线程/协程中运行，不阻塞游戏主循环
- 记录每条故障事件的开始/结束时间戳（使用 `Time.realtimeSinceStartup`），与监控指标做时间对齐
- 如果发现系统无法从某种故障中恢复，首先检查：重连逻辑是否正确重建了状态？缓冲区是否正确处理了过期数据？超时时间是否太短？
- 故障组合（如延迟尖刺 + 丢包爆发同时发生）可能导致意想不到的行为——这正是混沌工程的价值所在

---

## 7. 扩展阅读

- **Unity Multiplayer Tools - Network Simulator**: [https://docs-multiplayer.unity3d.com/tools/current/network-simulator/](https://docs-multiplayer.unity3d.com/tools/current/network-simulator/) — Unity 官方网络模拟器文档
- **Unreal Engine Network Emulation**: [https://docs.unrealengine.com/en-US/TestingAndOptimization/PerformanceAndProfiling/NetworkProfiler/](https://docs.unrealengine.com/en-US/TestingAndOptimization/PerformanceAndProfiling/NetworkProfiler/) — UE 网络模拟和性能分析器
- **Linux tc-netem**: [https://wiki.linuxfoundation.org/networking/netem](https://wiki.linuxfoundation.org/networking/netem) — Linux 内核流量控制网络模拟
- **clumsy (Windows 网络模拟)**: [https://github.com/jagt/clumsy](https://github.com/jagt/clumsy) — 开源 Windows 网络模拟工具，系统级拦截，比引擎内置模拟器更真实
- **Netflix Chaos Monkey**: [https://github.com/Netflix/chaosmonkey](https://github.com/Netflix/chaosmonkey) — 混沌工程的开山之作，游戏服务的混沌测试可从中借鉴思路
- **Principles of Chaos Engineering**: [https://principlesofchaos.org/](https://principlesofchaos.org/) — 混沌工程的正式原则，设计混沌测试的哲学基础
- **Riot Games: Determinism in League of Legends — Fixing Divergences**: [https://technology.riotgames.com/news/determinism-league-legends-fixing-divergences](https://technology.riotgames.com/news/determinism-league-legends-fixing-divergences) — Riot 如何检测和修复帧同步 Desync 的实战经验，包含回放测试的具体实践
- **GDC 2018: '8 Frames in 16ms' — Rollback Networking in Mortal Kombat & Injustice 2**: [https://www.gdcvault.com/play/1024987/](https://www.gdcvault.com/play/1024987/) — NetherRealm 的确定性回滚网络架构，包含自动化回放测试的细节
- **Overwatch Gameplay Architecture and Netcode (GDC 2017)**: [https://www.youtube.com/watch?v=W3aieHjyNvw](https://www.youtube.com/watch?v=W3aieHjyNvw) — 暴雪展示的网络架构，包含优先队列重传的测试策略
- **AWS Fault Injection Simulator**: [https://aws.amazon.com/fis/](https://aws.amazon.com/fis/) — AWS 托管的故障注入服务（适用于部署在 AWS 上的 DS 服务器）
- **Google SRE Book — Chapter 17: Testing for Reliability**: [https://sre.google/sre-book/testing-reliability/](https://sre.google/sre-book/testing-reliability/) — Google 的可靠性测试方法论，包含混沌工程在整个测试金字塔中的定位

---

## 常见陷阱

### 陷阱 1：只在 LAN 条件下测试

**症状**：开发和 QA 团队都在局域网（< 5ms 延迟、0% 丢包）下测试，上线后用户投诉"卡到没法玩"。

**正确做法**：
- CI 中至少跑 3 种网络条件：LAN、4G、弱信号
- 对每种条件设定明确的通过标准（如：4G 条件下预测误差 < 1m、弱信号下重连成功率 > 95%）
- QA 日常测试使用 Network Simulator 的中等或差条件
- 将网络条件测试作为 Release Checklist 的必检项

### 陷阱 2：网络模拟参数脱离实际

**症状 A**：把延迟设成 1000ms——现实中除非在卫星网络或极深处地下，否则不会到这种程度。测试"永远不会通过"的条件是无意义的。
**症状 B**：只用固定延迟，不加抖动——真实网络的延迟是波动的。没有抖动的测试会掩盖帧缓冲的边界行为。

**正确做法**：
- 网络条件参数应参考真实数据来源（OpenSignal、Google Wifi Report、中国信通院移动网络质量报告）
- 延迟必须带抖动（正态分布或帕累托分布），丢包必须有相关性（如 `loss 2% 25%`）
- 定义"目标条件"（你的目标用户群体最常遇到的条件）和"极限条件"（边缘用户可能遇到的条件）
- 目标条件下必须 100% 通过，极限条件下允许某些指标降级但不允许崩溃

### 陷阱 3：回放测试的 Hash 包含非确定性数据

**症状 A**：Hash 计算包含当前系统时间 → 每次计算结果不同，即使游戏状态完全一致。
**症状 B**：Hash 遍历容器时顺序不确定（如 C# 的 `Dictionary`、Lua 的 `pairs()`）→ 同一状态的 Hash 有时相同有时不同，导致假阳性。
**症状 C**：Hash 包含渲染相关数据（动画帧、插值 alpha、粒子种子）→ 不同帧率/硬件产生不同 Hash。

**正确做法**：
- Hash 只包含**逻辑状态**数据，且必须按确定的顺序（如实体 ID 升序）序列化
- C# 用 `SortedDictionary` 或先 `.Keys.OrderBy()`，C++ 用 `std::map`（有序红黑树）
- Hash 算法使用非加密哈希（如 MurmurHash3 或 FNV-1a）——速度远快于 MD5，冲突率对游戏状态来说足够低
- **关键**：在 CI 中加入跨平台 Hash 校验——同一回放文件在 Windows/Linux/macOS 上回放，Hash 必须一致

### 陷阱 4：混沌测试没有明确停止条件

**症状**：启动 ChaosMonkey 后放任不管，运行数小时。如果系统在 5 分钟时就崩溃了，后续 55 分钟只是浪费 CI 资源。即使偶尔跑通了，也无法确认是"系统健壮"还是"恰巧没触发致命组合"。

**正确做法**：
- 每次混沌测试有明确的**时间上限**（如 10 分钟）和**通过标准**（0 崩溃、> 95% 重连成功率）
- 达到时间上限自动停止（即使还有故障在运行）
- 一旦检测到崩溃或不可恢复状态，立即停止并记录失败原因
- 定期回顾测试覆盖率：当前故障参数组合覆盖了多少种故障场景组合？

### 陷阱 5：CI 测试时间过长导致开发者绕过

**症状**：回放 500 局耗时 45 分钟，每次 PR 都要等。结果：开发者在 `.github/workflows/` 里把 `paths` 改成了"只有自己才触发的路径"，或者团队把测试从 Required Check 降级为 Optional。

**正确做法**：
- 分层测试：快速测试（< 5 分钟）在每次 PR 时必跑，慢速测试在 Nightly Build 或 Release 候选时跑
- 快速测试覆盖最关键的风险：Desync 检测（LAN 条件 × 50 局）、弱网基本可用性
- 使用缓存（回放文件、Unity Library 缓存）减少 CI 启动时间
- 如果测试确实需要很长时间（如 Release 前 2000 局），在 PR 上只跑一个随机抽样（如 100 局），完整版留给定时任务

### 陷阱 6：网络模拟只在客户端上做

**症状**：测试时只在客户端上加延迟/丢包，服务器用 LAN 直连。结果：测试通过了，但上线后 DS（Dedicated Server）部署在云上，客户端→服务器的链路本就有真实延迟。

**正确做法**：
- 网络模拟必须在**两端同时施加**：客户端模拟出站延迟 + 服务端模拟出站延迟
- RTT（往返时间）= 客户端出站延迟 + 服务端出站延迟 + 实际网络延迟。如果要模拟 RTT=200ms，每端设 100ms
- 如果是 DS 架构，服务端的网络模拟应该在测试环境中使用 tc netem 或 UE 的 `PktIncomingLag`（模拟客户端→DS 的延迟）
- 注意上行/下行不对称：移动网络上行的延迟通常高于下行（如 4G: 上行 80ms, 下行 40ms）。使用 `PktIncomingLag` 和 `PktLag` 分别设置

### 陷阱 7：把混沌测试的结果当成「通过/失败」二元判断

**症状**：混沌测试跑了 10 分钟，没崩溃，重连成功率 96%。结论："通过了"。下个版本跑了 10 分钟，重连成功率 94%。结论："失败了"。但 96% 和 94% 的真实差异是 1 次重连失败 vs 2 次重连失败——统计上可能只是运气波动。

**正确做法**：
- 混沌测试的结果是**概率性的**——每次运行的故障组合不同，结果有波动
- 对于概率指标（重连成功率、帧缓冲恢复时间），使用**多次运行取平均值和中位数**
- 趋势监控比单次通过/失败更重要：重连成功率从 98% 降到 95% 到 92% 的趋势比"某次到了 94%"更值得关注
- 设置**趋势告警**：连续 3 次 Nightly 混沌测试中某指标持续下降 → 触发调查

---

> **本节与第 30 节的关系**：第 30 节覆盖了调试面板、性能分析和监控系统，本节聚焦于"在网络引入之前"的预防性测试。两者构成完整闭环：**测试防患于未然 → 监控发现问题 → 调试定位根因**。将两者结合，才能构建出能抵御真实网络环境的生产级同步系统。
