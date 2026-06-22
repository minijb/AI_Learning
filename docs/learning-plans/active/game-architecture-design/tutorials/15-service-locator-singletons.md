---
title: Service Locator 与 Singleton 替代
updated: 2026-06-22
tags: [game-architecture, service-locator, dependency-injection, singleton, ioc, testability, csharp]
---

# Service Locator 与 Singleton 替代

> 所属计划: 游戏架构设计
> 预计耗时: 45min
> 前置知识: [[03-coupling-cohesion-di|3. 耦合、内聚与依赖管理（IoC/DI）]]

---

## 1. 概念讲解

### 为什么需要这个？

游戏开发中，「我需要从任何地方播放音效」是一个极其常见的需求。最自然的反应是写一个 `AudioManager.Instance.Play("jump")`——Singleton 模式。这看似解决了问题，却在代码中埋下了系统性隐患。

全局单例的核心问题在于**隐式依赖**。当你看到 `Player.Jump()` 方法时，你无法直接知道它依赖了 `AudioManager`；这个依赖藏在实现细节里，直到运行时通过 `Instance` 属性才暴露出来。这种隐藏性带来连锁反应：

| 问题 | 具体表现 |
| --- | --- |
| **破坏可测试性** | 单元测试 `Player.Jump()` 必须初始化真实的 `AudioManager`，可能触发实际的音频设备 |
| **全局状态污染** | 测试顺序影响结果，测试间产生耦合 |
| **多线程风险** | `Instance` 的懒加载在并发下需要额外同步，容易出错 |
| **多场景/生命周期混乱** | 场景切换时单例残留，或重复初始化导致状态冲突 |
| **实现难以替换** | 想换用 `Wwise` 替代 `UnityAudio`？所有 `Instance` 调用点都需要修改 |

这些问题的根源并非「只有一个实例」——某些底层系统确实只需要一个实例——而是**实例的获取方式**通过全局可访问的硬编码路径，将依赖关系从接口契约降级为实现细节。

### 核心思想

#### 1. Singleton 的合理边界

Singleton 并非完全不可用。底层硬件抽象、真正的操作系统级唯一资源（如文件句柄、渲染上下文、特定音频设备）适合单例。但即使如此，也应**显式接口化**：

```csharp
// 即使底层是单例，也暴露为接口
public interface IFileSystem { Stream Open(string path); }
public class OSFileSystem : IFileSystem { /* 真正的单例实现 */ }
```

关键在于：**调用方依赖 `IFileSystem`，而非 `OSFileSystem.Instance`**。这让替换成为可能——测试时用 `MockFileSystem`，MOD 加载时用 `VirtualFileSystem`。

#### 2. Service Locator：可配置的全局访问

Service Locator 是 Nystrom 在《Game Programming Patterns》中提出的「可配置的单例替代品」。它用一个注册表解耦「服务的获取」与「服务的实现」：

```csharp
// 注册
Services.Register<IAudio>(new FMODAudio());

// 使用
IAudio audio = Services.Get<IAudio>();
audio.Play("jump");
```

这比硬编码 `AudioManager.Instance` 灵活：实现可替换、支持空对象（`NullAudio`）。但它仍是**隐式依赖**——`Player` 的代码中不出现 `IAudio` 参数，依赖关系无法从签名中读取。延迟绑定意味着错误（未注册服务）要到运行时才暴露。

Unity 的 `GameServices`、XNA 的 `Game.Services` 都是此模式的实例。

#### 3. DI/IoC 容器：显式依赖图

依赖注入（DI）将依赖变为**构造函数或属性的显式参数**：

```csharp
public class Player {
    private readonly IAudio audio;
    public Player(IAudio audio) => this.audio = audio;
}
```

依赖关系完全暴露在类型系统中，编译器可验证，IDE 可自动补全，测试时可传入 `MockAudio`。IoC 容器（如 Unity 的 VContainer、Extenject）负责**装配**：在启动时根据配置自动解析依赖图，创建对象并注入。

游戏中的关键区分是**生命周期**：
- **Singleton（容器管理）**：整个游戏存在，如 `SaveSystem`
- **Scoped/Transient**：每场景新建，如 `LevelController`
- **场景上下文**：Unity 中 `LifetimeScope` 绑定到场景加载/卸载

#### 4. 游戏中的实际取舍

完全消除全局访问在游戏开发中不现实。合理的分层策略：

| 层级 | 推荐方案 | 原因 |
| --- | --- | --- |
| 底层子系统（音频、输入、文件） | 接口化 Singleton 或 Locator | 高频访问，调用点极多，接口化已足够 |
| 业务逻辑（玩家、敌人、技能） | 构造函数 DI | 需要大量单元测试，依赖关系复杂 |
| 跨场景持久服务 | Scoped DI 或显式 Locator | 生命周期需精确控制 |
| 第三方插件/中间件 | Facade + 注入 | 隔离外部依赖，便于替换 |

#### 5. 可测试性收益

这是架构决策的最终检验标准。注入 `MockAudio`/`MockInput`/`MockPhysics` 后，单元测试无需启动引擎：

```csharp
[Test]
public void Jump_PlaySound() {
    var mockAudio = new MockAudio();
    var player = new Player(mockAudio);
    player.Jump();
    Assert.That(mockAudio.LastPlayedClip, Is.EqualTo("jump"));
}
```

这种测试在毫秒级完成，而启动 Unity 场景测试需要秒级甚至分钟级。可测试性差异直接影响 TDD 可行性和回归测试频率。

---

## 2. 代码示例

以下 .NET 6+ 控制台程序完整演示 Service Locator 与构造函数注入两种方案，包含 `NullAudio` 安全默认和 `MockAudio` 测试替身。

```csharp
using System;
using System.Collections.Generic;

// ==================== 共享接口 ====================
public interface IAudio
{
    void Play(string clip);
    void Stop(string clip);
}

// ==================== 实现 ====================

// 真实音频（生产环境）
public class AudioService : IAudio
{
    public void Play(string clip) => Console.WriteLine($"[AUDIO] Playing: {clip}");
    public void Stop(string clip) => Console.WriteLine($"[AUDIO] Stopped: {clip}");
}

// 空对象：默认安全行为，避免 NullReferenceException
public class NullAudio : IAudio
{
    public void Play(string clip) { /* 静默 */ }
    public void Stop(string clip) { /* 静默 */ }
}

// 测试替身：记录调用用于断言
public class MockAudio : IAudio
{
    public List<string> PlayedClips { get; } = new();
    public List<string> StoppedClips { get; } = new();
    
    public void Play(string clip) => PlayedClips.Add(clip);
    public void Stop(string clip) => StoppedClips.Add(clip);
}

// ==================== Service Locator 版 ====================
public static class Services
{
    private static readonly Dictionary<Type, object> _map = new();
    
    // 默认提供 NullAudio，避免未注册时崩溃
    private static readonly Dictionary<Type, object> _defaults = new()
    {
        [typeof(IAudio)] = new NullAudio()
    };
    
    public static void Register<T>(T implementation) where T : notnull
        => _map[typeof(T)] = implementation;
    
    public static void Unregister<T>() => _map.Remove(typeof(T));
    
    public static T Get<T>()
    {
        var type = typeof(T);
        if (_map.TryGetValue(type, out var found))
            return (T)found;
        if (_defaults.TryGetValue(type, out var def))
            return (T)def;
        throw new InvalidOperationException($"No service registered for {type.Name}");
    }
    
    public static void Clear() => _map.Clear();
}

// 使用 Locator 的 Player：隐式依赖
public class PlayerWithLocator
{
    public void Jump()
    {
        Console.WriteLine("Player jumping!");
        Services.Get<IAudio>().Play("jump");
    }
    
    public void Land()
    {
        Console.WriteLine("Player landed!");
        Services.Get<IAudio>().Play("land");
    }
}

// ==================== 构造函数注入版 ====================
public class PlayerWithInjection
{
    private readonly IAudio _audio;
    
    // 依赖显式声明：无法构造没有 IAudio 的 Player
    public PlayerWithInjection(IAudio audio)
    {
        _audio = audio ?? throw new ArgumentNullException(nameof(audio));
    }
    
    public void Jump()
    {
        Console.WriteLine("Player jumping!");
        _audio.Play("jump");
    }
    
    public void Land()
    {
        Console.WriteLine("Player landed!");
        _audio.Play("land");
    }
}

// ==================== 简单 DI 容器（演示原理） ====================
public class SimpleContainer
{
    private readonly Dictionary<Type, Func<object>> _factories = new();
    
    public void Register<T>(Func<T> factory) where T : notnull
        => _factories[typeof(T)] = () => factory()!;
    
    public T Resolve<T>() where T : notnull
    {
        var type = typeof(T);
        if (!_factories.TryGetValue(type, out var factory))
            throw new InvalidOperationException($"No registration for {type.Name}");
        return (T)factory();
    }
}

// ==================== 程序入口 ====================
class Program
{
    static void Main()
    {
        Console.WriteLine("=== Service Locator 演示 ===\n");
        
        // 未注册时：安全默认（NullAudio）
        var playerLocator1 = new PlayerWithLocator();
        Console.WriteLine("--- 未注册服务（默认 NullAudio）---");
        playerLocator1.Jump(); // 无输出，不崩溃
        
        // 注册真实服务
        Services.Register<IAudio>(new AudioService());
        Console.WriteLine("\n--- 注册 AudioService 后 ---");
        var playerLocator2 = new PlayerWithLocator();
        playerLocator2.Jump();
        playerLocator2.Land();
        
        Services.Clear();
        
        Console.WriteLine("\n=== 构造函数注入演示 ===\n");
        
        // 注入真实服务
        var audio = new AudioService();
        var playerInjected = new PlayerWithInjection(audio);
        playerInjected.Jump();
        playerInjected.Land();
        
        Console.WriteLine("\n=== 测试替身演示 ===\n");
        
        // 单元测试场景：注入 MockAudio
        var mockAudio = new MockAudio();
        var playerTest = new PlayerWithInjection(mockAudio);
        playerTest.Jump();
        playerTest.Land();
        
        Console.WriteLine($"Mock 记录的播放: {string.Join(", ", mockAudio.PlayedClips)}");
        
        Console.WriteLine("\n=== 简单 DI 容器演示 ===\n");
        
        var container = new SimpleContainer();
        container.Register<IAudio>(() => new AudioService());
        container.Register<PlayerWithInjection>(() => 
            new PlayerWithInjection(container.Resolve<IAudio>()));
        
        var playerFromContainer = container.Resolve<PlayerWithInjection>();
        playerFromContainer.Jump();
    }
}
```

**运行方式:**

```bash
# 需要 .NET 6 SDK 或更高版本
dotnet new console -n ServiceLocatorDemo
# 将上述代码复制到 Program.cs
dotnet run
```

**预期输出:**

```text
=== Service Locator 演示 ===

--- 未注册服务（默认 NullAudio）---
Player jumping!

--- 注册 AudioService 后 ---
Player jumping!
[AUDIO] Playing: jump
Player landed!
[AUDIO] Playing: land

=== 构造函数注入演示 ===

Player jumping!
[AUDIO] Playing: jump
Player landed!
[AUDIO] Playing: land

=== 测试替身演示 ===

Player jumping!
Player landed!
Mock 记录的播放: jump, land

=== 简单 DI 容器演示 ===

Player jumping!
[AUDIO] Playing: jump
```

---

## 3. 练习

### 练习 1: 基础

将以下使用 `AudioManager.Instance` 的 `Player` 类改写为构造函数注入 `IAudio`。要求删除所有 `Instance` 引用，保持原有行为。

```csharp
public class AudioManager
{
    public static AudioManager Instance { get; } = new();
    public void PlaySFX(string name) => Console.WriteLine($"SFX: {name}");
}

public class Player
{
    private int _health = 100;
    
    public void TakeDamage(int amount)
    {
        _health -= amount;
        AudioManager.Instance.PlaySFX("hurt");
        if (_health <= 0)
            AudioManager.Instance.PlaySFX("death");
    }
    
    public void Heal(int amount)
    {
        _health = Math.Min(_health + amount, 100);
        AudioManager.Instance.PlaySFX("heal");
    }
}
```

### 练习 2: 进阶

实现一个支持**作用域**的 `ScopedServiceLocator`，区分全局服务与场景级服务。要求：
- `RegisterGlobal<T>` / `GetGlobal<T>`：跨场景持久
- `RegisterScene<T>` / `GetScene<T>`：当前场景有效
- 场景切换时自动 `Dispose` 场景级服务（实现 `IDisposable` 接口的）并清空场景字典
- 提供 `SceneScope` 类封装场景生命周期管理

### 练习 3: 挑战（可选）

比较 **DI 容器**与 **Service Locator** 在以下三个维度的差异，并给出游戏项目中的决策树：

| 维度 | DI 容器 | Service Locator |
| --- | --- | --- |
| 编译期错误发现 | ? | ? |
| 运行时灵活性 | ? | ? |
| 测试便利性 | ? | ? |

要求：分析为何 DI 容器「启动时解析」与 Locator「延迟绑定」会导致这些差异，并给出具体场景建议（如：业务逻辑系统、底层音频、MOD 加载等）。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> 核心步骤：提取 `IAudio` 接口，将 `AudioManager` 改为实现该接口，修改 `Player` 构造函数接收 `IAudio`。
> 
> ```csharp
> public interface IAudio
> {
>     void PlaySFX(string name);
> }
> 
> // 生产实现
> public class AudioManager : IAudio
> {
>     public void PlaySFX(string name) => Console.WriteLine($"SFX: {name}");
> }
> 
> // 测试实现
> public class SilentAudio : IAudio
> {
>     public void PlaySFX(string name) { }
> }
> 
> public class Player
> {
>     private readonly IAudio _audio;
>     private int _health = 100;
>     
>     public Player(IAudio audio)
>     {
>         _audio = audio ?? throw new ArgumentNullException(nameof(audio));
>     }
>     
>     public void TakeDamage(int amount)
>     {
>         _health -= amount;
>         _audio.PlaySFX("hurt");
>         if (_health <= 0)
>             _audio.PlaySFX("death");
>     }
>     
>     public void Heal(int amount)
>     {
>         _health = Math.Min(_health + amount, 100);
>         _audio.PlaySFX("heal");
>     }
> }
> 
> // 启动装配（Composition Root）
> var audio = new AudioManager();
> var player = new Player(audio);
> ```
> 
> 关键验证点：删除 `AudioManager.Instance` 属性后，`Player` 类不再有任何静态依赖；测试时可传入 `SilentAudio` 或 `MockAudio` 记录调用。

> [!tip]- 练习 2 参考答案
> 核心设计：双字典分离全局与场景作用域，`SceneScope` 封装场景生命周期。
> 
> ```csharp
> using System;
> using System.Collections.Generic;
> 
> public interface ISceneService : IDisposable { }
> 
> public static class ScopedServiceLocator
> {
>     private static readonly Dictionary<Type, object> _global = new();
>     private static readonly Dictionary<Type, object> _scene = new();
>     private static readonly HashSet<Type> _sceneTypes = new(); // 追踪哪些类型是场景级
>     
>     // ========== 全局 ==========
>     public static void RegisterGlobal<T>(T service) where T : notnull
>     {
>         _global[typeof(T)] = service;
>     }
>     
>     public static T GetGlobal<T>()
>     {
>         var type = typeof(T);
>         if (_global.TryGetValue(type, out var found))
>             return (T)found;
>         throw new InvalidOperationException($"No global service for {type.Name}");
>     }
>     
>     // ========== 场景 ==========
>     public static void RegisterScene<T>(T service) where T : notnull
>     {
>         var type = typeof(T);
>         _scene[type] = service;
>         _sceneTypes.Add(type);
>     }
>     
>     public static T GetScene<T>()
>     {
>         var type = typeof(T);
>         if (_scene.TryGetValue(type, out var found))
>             return (T)found;
>         throw new InvalidOperationException($"No scene service for {type.Name}");
>     }
>     
>     // ========== 清理 ==========
>     public static void ClearScene()
>     {
>         foreach (var kvp in _scene)
>         {
>             if (kvp.Value is IDisposable disposable)
>             {
>                 try { disposable.Dispose(); }
>                 catch (Exception ex) { Console.WriteLine($"Dispose error: {ex.Message}"); }
>             }
>         }
>         _scene.Clear();
>         _sceneTypes.Clear();
>     }
>     
>     // 通用获取：优先场景，回退全局
>     public static T Get<T>()
>     {
>         var type = typeof(T);
>         if (_scene.ContainsKey(type)) return GetScene<T>();
>         if (_global.ContainsKey(type)) return GetGlobal<T>();
>         throw new InvalidOperationException($"No service for {type.Name}");
>     }
> }
> 
> // 场景生命周期封装（Unity 中可替换为 MonoBehaviour）
> public class SceneScope : IDisposable
> {
>     public SceneScope() { }
>     
>     public void Register<T>(T service) where T : notnull
>         => ScopedServiceLocator.RegisterScene(service);
>     
>     public void Dispose()
>     {
>         ScopedServiceLocator.ClearScene();
>     }
> }
> 
> // ========== 使用示例 ==========
> public class SceneAudio : ISceneService, IAudio
> {
>     public void PlaySFX(string name) => Console.WriteLine($"[SceneAudio] {name}");
>     public void Dispose() => Console.WriteLine("SceneAudio disposed");
> }
> 
> // 全局注册
> ScopedServiceLocator.RegisterGlobal<IAudio>(new AudioManager());
> 
> // 场景开始时
> using (var scope = new SceneScope())
> {
>     scope.Register(new SceneAudio());
>     // 场景内使用
>     var audio = ScopedServiceLocator.Get<IAudio>(); // 获取 SceneAudio
>     audio.PlaySFX("battle");
> } // 离开 using：自动 Dispose SceneAudio
> 
> // 回到全局
> var globalAudio = ScopedServiceLocator.Get<IAudio>(); // 获取 AudioManager
> ```
> 
> Unity 适配：将 `SceneScope` 改为 `MonoBehaviour`，在 `OnDestroy` 中调用 `ClearScene()`；或使用 `SceneManager.sceneUnloaded` 事件。

> [!tip]- 练习 3 参考答案
> 
> | 维度 | DI 容器 | Service Locator | 根本原因 |
> | --- | --- | --- | --- |
> | **编译期错误发现** | ✅ 强。启动时构建完整依赖图，缺失服务立即抛出 | ❌ 弱。延迟到 `Get<T>()` 调用时才检查，可能遗漏路径未触发 | 解析时机：构造时 vs 使用时 |
> | **运行时灵活性** | ⚠️ 中等。需预注册，动态替换需重新配置 | ✅ 强。运行时任意注册、替换、撤销 | 绑定时机：启动固定 vs 运行时可变 |
> | **测试便利性** | ✅ 强。构造函数直接传入 Mock，无容器也可测 | ⚠️ 中等。需预注册 Mock，或提供 `Clear`+`Register` 辅助 | 依赖显式度：参数 vs 隐藏 |
> 
> **决策树：**
> 
> ```
> 该服务是否需要频繁单元测试？
> ├── 是 → 该服务是否依赖关系复杂（>3 个协作对象）？
> │       ├── 是 → DI 容器（自动解析图）
> │       └── 否 → 纯构造函数注入（无需容器）
> └── 否 → 该服务是否运行时动态变化（MOD、热插拔）？
>         ├── 是 → Service Locator + 接口
>         └── 否 → 接口化 Singleton（简单明确）
> ```
> 
> **游戏场景映射：**
> - **业务逻辑（Player, Enemy, Skill）**：DI 容器。依赖复杂，需大量测试，启动时配置固定。
> - **底层音频/输入**：接口化 Singleton 或 Locator。调用点极多，实现极少变化，Locator 提供跨平台切换（FMOD/Wwise/UnityAudio）。
> - **MOD 系统/插件**：Locator。运行时动态加载，DI 容器无法预注册未知类型。
> - **场景特定服务（LevelManager, SpawnController）**：Scoped DI。生命周期绑定场景，卸载自动清理。
> 
> 关键洞察：DI 容器与 Locator 并非互斥。成熟项目常混合：容器管理业务对象，Locator 提供底层服务查找，两者通过**接口契约**隔离。

> [!note] 答案使用方式
> 如果你的实现通过了测试或达到了题目要求，就是正确的。参考答案展示的是典型路径，但架构问题常有多种合理方案。重点验证：练习1 是否消除了静态依赖；练习2 的场景服务是否正确隔离与清理；练习3 的分析是否触及「解析时机」这一核心差异。若你的方案满足这些目标，即使代码结构不同，也是正确的。
>
> ---

## 4. 扩展阅读

- [Nystrom — Singleton · Game Programming Patterns](https://gameprogrammingpatterns.com/singleton.html) — 游戏开发领域最经典的 Singleton 批判与重构指南
- [Nystrom — Service Locator · Game Programming Patterns](https://gameprogrammingpatterns.com/service-locator.html) — Service Locator 的完整设计，包含与 Singleton 的对比和空对象模式
- [VContainer — Unity DI Container](https://vcontainer.hadashikick.jp/) — 现代 Unity DI 方案，支持 `LifetimeScope` 场景作用域、代码优先配置
- [Extenject — Unity DI Framework (GitHub)](https://github.com/Mathijs-Bakker/Extenject) — 前身 Zenject，Unity DI 生态的先驱，文档丰富的场景上下文示例

---

## 常见陷阱

- **把 Service Locator 当「穷人的 DI」到处用**。Locator 的 `Get<T>()` 调用散布在业务逻辑中，比 Singleton 更隐蔽：至少 `Instance` 是显式的全局访问点，而 Locator 伪装成「解耦」。正确做法：业务逻辑层强制构造函数注入，仅在底层子系统或真正的动态服务边界使用 Locator。

- **在静态构造函数 / `Awake` 中分散注册服务**。这导致启动顺序脆弱——`Player.Awake` 在 `AudioManager.Awake` 之前执行就会崩溃。正确做法：集中到**单一 Composition Root**（如 `GameStartup` 类或 `LifetimeScope`），显式控制初始化顺序，所有注册在首帧逻辑开始前完成。

- **生命周期错配：全局 Locator 持有场景对象引用**。`Services.Register<IAudio>(sceneObject.GetComponent<AudioController>())` 后，场景卸载时该对象仍被全局字典引用，导致跨场景泄漏或 `MissingReferenceException`。正确做法：全局服务只注册真正持久的对象；场景服务使用 `ScopedServiceLocator` 或 DI 容器的场景作用域，卸载时自动清理。