---
title: "行为树调试、可视化与性能优化"
updated: 2026-06-05
---

# 行为树调试、可视化与性能优化

> 所属计划: State Machines & Behavior Trees for Game AI
> 预计耗时: 120min
> 前置知识: [[08-bt-unity-csharp]], [[09-bt-unreal-cpp]], [[10-bt-lua]]（以及 06-bt-fundamentals、07-bt-node-types）

---

## 1. 概念讲解

### 为什么行为树难以调试？

行为树的调试难度来自其运行模型的三个特性：

**一、逐帧状态而非单一"当前状态"。** FSM 有一个明确的当前状态——你可以打印 `CurrentState.Name` 并立刻知道 AI 在做什么。行为树没有这个概念。每帧从根节点开始深度优先遍历，可能在遍历到第 7 层时某条路径返回 `Running`，另一条路径在第 3 层返回 `Failure`。要在某一帧理解 AI 的决策，你必须追踪**整条活跃执行路径**——从根到当前正在运行的叶子节点。

**二、深层嵌套。** 生产级行为树动辄 5-10 层嵌套。一个 `Selector` 里包含若干 `Sequence`，每个 `Sequence` 又包含 `Decorator` 包裹的子树，子树内部还有自己的 `Selector`/`Sequence`。在这样一个嵌套结构中，如果 AI 做出了意外的行为（比如该攻击时却在巡逻），你需要回答的问题不是"它在哪个状态"，而是"为什么 Selector 选择了第三个子树而不是第一个？第一个子树中哪个条件返回了 Failure？"

**三、时间维度。** 行为树的 bug 往往不是"这一帧错了"，而是"前面若干帧的某个条件导致了后续行为偏差"。例如：NPC 在第 42 帧因为 `HasTarget` 为 false 而切换到巡逻，第 43 帧目标出现了，但标准 Selector 不会重新评估前面的条件（它已经在巡逻子树上 Running 了）。要定位这个 bug，你需要知道第 42 帧发生了什么——而日志里可能有 60 帧×50 个节点=3000 条 tick 记录。

这三种特性意味着调试行为树需要**专门的工具和方法**，而非简单的 `Debug.Log`。

### 调试策略总览

| 策略 | 适用场景 | 代价 | 工具/技术 |
|:------|:---------|:-----|:----------|
| **结构化日志** | 开发期日常调试 | 低（需手动添加） | 带缩进的 per-node tick 日志、BB 值快照 |
| **可视化调试器** | AI 行为"看起来不对"时 | 中（需开发调试工具） | Scene View 绘制树状态、Editor Window 实时面板 |
| **快照导出** | 偶发 bug、需离线分析 | 中（存储开销） | 整棵树 + BB 状态导出为 JSON/自定义格式 |
| **录制与回放** | 难以复现的时序 bug | 高（录制全部帧的完整状态） | 逐帧录制 tick 序列，离线回放 |
| **Profiler 集成** | 性能瓶颈排查 | 低（需标记代码段） | UE Insights、Unity Profiler marker、自定义 instrumentation |

实际工作流通常是：日志确认问题 → 可视化观察行为 → 录制回放定位精确帧 → Profiler 优化性能。

### Unreal Engine 调试工具链

UE 的行为树系统自带一套成熟的调试工具链。

#### Gameplay Debugger

按下 `'`（撇号键）激活 Gameplay Debugger，切换到 AI 类别（小键盘 `3` 或在 GDT 面板中选择）。你会看到：

- **行为树树形叠加层**：屏幕左侧显示当前运行的 BT 的树形结构，活跃节点高亮
- **Blackboard 值**：所有 Blackboard Key 的当前值实时显示
- **AI Perception 信息**：感知到的 Actor、上次感知时间、感知类型（视觉/听觉/伤害）
- **EQS 查询可视化**：如果使用了 Environment Query System，查询点和评分会以彩色球体渲染在场景中

Gameplay Debugger 的核心优势是**无需重新编译或添加代码**——所有内置 BT 的信息自动暴露。

#### Visual Logger

Visual Logger（Window → Developer Tools → Visual Logger）提供**时间轴视角**的 AI 调试。它记录过去若干秒内每一帧的：

- 行为树状态（哪些节点被激活/停用）
- Blackboard 值的变化时间线
- AI 移动路径（点线渲染）
- 自定义 Log 分类（`UE_VLOG` 宏）

你可以拖动时间轴滑块回放 AI 在过去几秒内的行为，结合场景中的可视化箭头和路径，精确定位"NPC 为什么在那个时间点决定转弯"这类时空问题。

#### Behavior Tree Debugger 窗口

Window → Developer Tools → Behavior Tree Debugger 打开专属调试面板。选中一个运行中的 AI（在 World Outliner 中点击或在视口中点击），面板显示：

- 完整树结构，活跃路径上的节点用不同颜色标记
- 每个 Task 节点的当前状态（Inactive / Active / Aborted）
- Service 节点的下次 Tick 倒计时
- Decorator 的条件评估结果（通过/不通过/未评估）

双击任意节点可跳转到 Behavior Tree 资产中的对应位置。

#### AI Debug Text 渲染

对于不需要完整 GDT 的场景，UE 提供了轻量级的 `DrawDebugString`：

```cpp
// 在 Task 或 Service 的 Tick 中
FString DebugText = FString::Printf(TEXT("Task: %s | State: %d"),
    *GetNodeName(), (int32)CurrentState);
DrawDebugString(GetWorld(), Owner->GetPawn()->GetActorLocation(),
    DebugText, nullptr, FColor::Green, 0.0f, true);
```

文字会渲染在 AI 头顶上方的世界中。配合 `FColor` 编码状态（绿=Running、蓝=Success、红=Failure），可以在一屏内同时观察多个 AI 的行为。

### Unity 调试工具链

Unity 没有内置的行为树调试器，但你可以构建自己的工具。

#### Custom Gizmos/Handles

利用 `OnDrawGizmos` 或 `Handles` 在 Scene View 中绘制行为树状态。核心思路：遍历树结构，为每个节点计算屏幕空间位置，绘制带颜色编码的矩形/圆形，连线表示父子关系。

> 完整实现见[示例 A](#示例-a-unity-scene-view-运行时行为树可视化)。

#### Editor Window 实时面板

通过 `EditorWindow` + `EditorApplication.update` 创建非播放模式也可见的调试窗口。窗口显示：
- 选中 AI 的行为树结构（树形文本或 GUI 树形控件）
- 每个节点的状态、上次 Tick 耗时、累计 Tick 次数
- Blackboard 键值对表格

> 完整实现见[示例 B](#示例-b-unity-editor-window-bt-调试器面板)。

#### Runtime Inspector

利用第三方 Inspector 插件（如 Runtime Inspector & Hierarchy）在运行时查看 `BehaviorTreeRunner` 组件上的字段——前提是你的节点在运行时暴露了调试属性。

更实用的做法是在 `BTNode` 基类中预留调试接口：

```csharp
public abstract class BTNode
{
    // Debug info — populated during Tick, never used in logic
    public BTNodeState LastState { get; protected set; }
    public float LastTickTimeMs { get; protected set; }
    public int TickCount { get; protected set; }
    public string DebugName => GetType().Name;

    public BTNodeState Tick()
    {
        var sw = Stopwatch.StartNew();
        var result = OnTick();
        sw.Stop();
        LastState = result;
        LastTickTimeMs = (float)sw.Elapsed.TotalMilliseconds;
        TickCount++;
        return result;
    }

    protected abstract BTNodeState OnTick();
}
```

### 可视化技术

无论引擎，行为树可视化的核心模式是相通的。

#### 活跃节点高亮

遍历整棵树，标记哪些节点在当前的活跃路径上。活跃路径上的节点以更亮的颜色/更粗的边框渲染。非活跃路径上的节点可以半透明或完全不显示。

判断节点是否在活跃路径上的规则：
- 一个 Composite 的子节点中，**当前正在 tick 且返回 Running 的那个**及其祖先链在活跃路径上
- Sequence 中：当前活跃子节点之前的所有子节点（已 Success）也在路径上（它们已完成）
- Selector 中：当前活跃子节点之前的所有子节点（已 Failure 且被跳过）也在路径上（它们被评估过但不满足）

#### 状态颜色编码

这是行为树可视化最重要的惯例：

| 颜色 | 含义 | 使用场景 |
|:-----|:-----|:---------|
| 🟢 绿色 | Success | 条件满足、动作完成 |
| 🔴 红色 | Failure | 条件不满足、动作失败 |
| 🟡 黄色 | Running | 动作执行中（跨帧） |
| ⚪ 灰色/白色 | Inactive / 未评估 | 该帧未被 Tick 的节点 |

在 Scene View 中绘制时，用这些颜色填充节点矩形或连线。在 Editor Window 中，用彩色文本或图标。

#### Tick 计数与计时

在节点旁边显示两个关键指标：
- **Tick Count**：该节点自树启动以来被 tick 的总次数。用于发现"某个条件被过于频繁地检查"或"某个节点从未被 tick"
- **Last Tick Time**：上一次 tick 花费的毫秒数。用于定位性能热点

#### 计时热力图（Timing Heatmap）

将节点的渲染颜色从其逻辑状态切换为**性能热力图**，用颜色梯度表示每个节点的平均 Tick 耗时：

| 耗时 | 颜色 | 含义 |
|:-----|:-----|:-----|
| < 0.01ms | 白色 | 几乎瞬时 |
| 0.01–0.1ms | 绿色 | 正常 |
| 0.1–0.5ms | 黄色 | 注意 |
| 0.5–2ms | 橙色 | 警告 |
| > 2ms | 红色 | 性能热点 |

一键切换"状态模式"和"热力图模式"是面试中展示调试工具设计能力的加分项。

#### Blackboard 值叠加

在树的可视化中，将 Blackboard 中与当前子树相关的 Key 值显示在对应节点旁边。例如在 `Attack` 节点旁边显示 `Target=Enemy_07, Distance=3.2m`。这使得"数据 → 决策"的映射一目了然。

### 性能优化

行为树性能优化不是"让代码跑得更快"——它是**以可控的响应性损失换取 CPU 预算**的权衡工程。

#### Tick 频率降低

不是所有 AI 都需要每帧思考。一个距离玩家 200 米的守卫 NPC，每 0.5 秒（30 帧）更新一次决策完全足够。实现方案：

```csharp
// In BehaviorTreeRunner.Update()
_frameCounter++;
if (_frameCounter % _tickIntervalFrames != 0) return;
_root.Tick();
```

关键：降低 tick 频率意味着 AI 对事件的响应延迟增加。补偿方案是**事件唤醒**——当关键事件发生时（如受到伤害、感知到玩家），强制立即 Tick 并重置计数器。

#### AI LOD 系统

将 AI 按距离分层，不同层级使用不同复杂度的决策系统：

| LOD 等级 | 距离 | 决策系统 | Tick 频率 | 典型 CPU 预算 |
|:---------|:-----|:---------|:----------|:-------------|
| LOD 0（全精度） | < 30m | 完整行为树 | 每帧 | ~0.3ms/agent |
| LOD 1（简化） | 30–80m | 简化 FSM（3-5 状态） | 每 10 帧 | ~0.05ms/agent |
| LOD 2（休眠） | > 80m | 禁用 AI 更新 | — | ~0ms |
| LOD 2 事件唤醒 | > 80m + 受伤害 | 临时恢复 LOD 0，3 秒后退回 | 每帧（临时） | — |

> 完整实现见[练习 2](#练习-2-实现-ai-lod-系统)。

**注意**：LOD 切换必须平滑——从 LOD 0 降到 LOD 1 时，FSM 的初始状态应该从 BT 的最后活跃行为推导出来，避免 NPC 突然"重置"到巡逻。

#### 节点池化

对于频繁创建/销毁的 AI 实体（波次刷怪），预分配行为树节点实例到对象池：

```csharp
public class BTNodePool
{
    private Stack<Selector> _selectorPool = new();
    private Stack<Sequence> _sequencePool = new();
    // ... per-type pools

    public T Rent<T>() where T : BTNode, new()
    {
        // Return from pool or create new
    }

    public void Return(BTNode node)
    {
        node.Reset();  // clear runtime state
        // Push back to type-specific pool
    }
}
```

**重要**：池化的是节点实例的**内存**，而非节点的逻辑状态。`Reset()` 必须清理所有 per-agent 状态（`_currentChildIndex`、`_isMoving`、计时器等），否则会产生跨生命周期的状态污染——这是池化 bug 的第一大来源。

#### Blackboard Key 缓存

Blackboard 的 `Dictionary<string, object>` 查找有哈希开销。对于高频访问的 Key（如 `Target`、`Health`），将 Key 在初始化时转换为整数索引：

```csharp
public class Blackboard
{
    // Slow path: first access
    public T Get<T>(string key)
    {
        int index = GetOrCreateIndex(key);
        return (T)_values[index];
    }

    // Fast path: pre-cached index
    public T Get<T>(int keyIndex)
    {
        return (T)_values[keyIndex];
    }
}

// Usage in a Task
public class AttackTask : BTTask
{
    private int _targetKeyIndex = -1;  // cached at init

    public override void OnInitialize(Blackboard bb)
    {
        _targetKeyIndex = bb.GetKeyIndex("Target");
    }

    protected override BTNodeState OnTick()
    {
        var target = Blackboard.Get<Transform>(_targetKeyIndex);  // O(1) array access
        // ...
    }
}
```

#### Parallel 节点的评估预算

Parallel 节点同时 tick 所有子节点，在大规模场景中可能成为性能瓶颈。为 Parallel 节点设置**评估预算**：

- **Tick Budget（ms）**：如果本轮子节点 tick 的总时间超过预算，剩余子节点推迟到下一帧
- **Child Limit**：限制同时活跃的子节点数量上限

```csharp
public class Parallel : CompositeNode
{
    public float TickBudgetMs = 0.5f;  // max 0.5ms per frame for this node

    public override BTNodeState Tick()
    {
        float elapsed = 0f;
        foreach (var child in _children)
        {
            var sw = Stopwatch.StartNew();
            var status = child.Tick();
            elapsed += (float)sw.Elapsed.TotalMilliseconds;

            if (elapsed > TickBudgetMs && status == BTNodeState.Running)
            {
                // Defer remaining children to next frame
                _lastDeferredChildIndex = currentIndex;
                return BTNodeState.Running;
            }
        }
        return EvaluatePolicy();
    }
}
```

#### 内存优化：per-node 实例数据

行为树最大的内存开销来自每个 agent 持有的整棵树实例。优化手段：

1. **共享不可变数据**：树的拓扑结构（父子关系、节点类型）是只读的，可以被同类型的所有 agent 共享。只有运行时状态（`_currentChildIndex`、计时器、`_isMoving`）是 per-agent 的。
2. **状态分离存储**：将运行时状态存储在一个扁平的 `NativeArray<byte>` 中，每个节点的状态通过 `nodeIndex * stride` 偏移访问。这与 UE 的 `UBTNode::GetInstanceMemorySize` 模式一致。
3. **惰性初始化**：大型子树（如 Boss 的多阶段行为）不在一开始就实例化，而是在第一次被 tick 到时才分配。

### 性能剖析（Profiling）

#### UE Insights

UE 的行为树系统已经内置了 Trace Channel。在 `UBehaviorTreeComponent::TickComponent` 的调用栈中，每个 `BTTask::ExecuteTask` 和 `BTService::TickNode` 都有对应的 trace event。启动 Unreal Insights 录制后，你可以在时间轴中看到：

- 每个 AI 的 BT Tick 耗时在整个帧中的占比
- 哪个 Task 最耗时（展开调用树）
- Service 的 Tick 间隔是否与配置一致
- Observer Abort 触发的额外 Tick 开销

#### Unity Profiler

对于自研行为树框架，你需要手动添加 Profiler Marker：

```csharp
using UnityEngine.Profiling;

public override BTNodeState Tick()
{
    Profiler.BeginSample($"BT.{DebugName}");
    var result = OnTick();
    Profiler.EndSample();
    return result;
}
```

在 Unity Profiler 的 CPU Usage 模块中，你可以按 `BT.` 前缀过滤，查看所有行为树节点的耗时层次结构。

**注意 Deep Profile 的陷阱**：Unity 的 Deep Profiling 模式会为**每一个方法调用**插入 instrumentation，开销巨大（可能使帧时间翻倍）。在 Deep Profile 下观察到的 BT Tick 耗时不能直接等同于实际性能。建议使用 `Profiler.BeginSample/EndSample` 手动打点替代 Deep Profile。

#### 自定义 Instrumentation

对于跨引擎或自研引擎场景，构建轻量级的 instrumentation 层：

```csharp
public struct BTProfilerSample : IDisposable
{
    private string _name;
    private long _startTicks;

    public BTProfilerSample(string name)
    {
        _name = name;
        _startTicks = Stopwatch.GetTimestamp();
    }

    public void Dispose()
    {
        long elapsed = Stopwatch.GetTimestamp() - _startTicks;
        double ms = elapsed * 1000.0 / Stopwatch.Frequency;
        BTProfiler.Record(_name, ms);
    }
}

// Usage in node
public override BTNodeState Tick()
{
    using var _ = new BTProfilerSample(DebugName);
    return OnTick();
}
```

`BTProfiler.Record` 将数据写入环形缓冲区，在 Editor Window 中以柱状图或火焰图的形式展示。

---

## 2. 代码示例

### 示例 A: Unity Scene View 运行时行为树可视化

**目的**：在 Scene View 中绘制当前选中 AI 的行为树状态，节点颜色编码（Success/Failure/Running），连线表示父子关系。

```csharp
// BTDebugVisualizer.cs — Attach to an empty GameObject or use [ExecuteAlways]
using UnityEngine;
using UnityEditor;
using System.Collections.Generic;

[ExecuteAlways]
public class BTDebugVisualizer : MonoBehaviour
{
    [Tooltip("AI entity whose behavior tree to visualize")]
    public BehaviorTreeRunner TargetAI;

    [Header("Layout")]
    public float NodeWidth = 120f;
    public float NodeHeight = 30f;
    public float HorizontalSpacing = 30f;
    public float VerticalSpacing = 20f;
    public Vector3 WorldOffset = new(0, 2.5f, 0);

    [Header("Display")]
    public bool ShowOnlyActivePath = false;
    public bool ShowTickCount = true;
    public bool ShowTimingHeatmap = false;

    // Internal state
    private Dictionary<BTNode, Rect> _nodeRects = new();

    void OnDrawGizmos()
    {
        if (TargetAI == null || TargetAI.Root == null) return;
        _nodeRects.Clear();

        Vector3 rootPos = TargetAI.transform.position + WorldOffset;
        float totalWidth = CalculateSubtreeWidth(TargetAI.Root);
        float startX = rootPos.x - totalWidth / 2f;

        DrawNode(TargetAI.Root, new Vector3(startX, rootPos.y, rootPos.z), 0, totalWidth);
    }

    float CalculateSubtreeWidth(BTNode node)
    {
        if (node is CompositeNode composite && composite.Children.Count > 0)
        {
            float total = 0f;
            foreach (var child in composite.Children)
                total += CalculateSubtreeWidth(child) + HorizontalSpacing;
            return Mathf.Max(total - HorizontalSpacing, NodeWidth);
        }
        return NodeWidth;
    }

    float DrawNode(BTNode node, Vector3 position, int depth, float subtreeWidth)
    {
        if (node == null) return subtreeWidth;

        // Determine if this node is on the active execution path
        bool isActive = IsNodeOnActivePath(node, TargetAI.Root);

        if (ShowOnlyActivePath && !isActive) return subtreeWidth;

        // Choose color based on state or timing
        Color nodeColor;
        if (ShowTimingHeatmap)
            nodeColor = GetTimingHeatmapColor(node.LastTickTimeMs);
        else
            nodeColor = GetStateColor(node.LastState, isActive);

        // Draw background rect and border
        Rect rect = new(position.x - NodeWidth / 2f, position.y - NodeHeight / 2f,
            NodeWidth, NodeHeight);
        _nodeRects[node] = rect;

        Vector3 center = position;
        Gizmos.color = nodeColor;
        Gizmos.DrawCube(center, new Vector3(NodeWidth * 0.8f, NodeHeight * 0.8f, 0.1f));

        // Draw node name text
        string label = node.DebugName;
#if UNITY_EDITOR
        Handles.Label(center + Vector3.up * NodeHeight * 0.7f, label,
            isActive ? EditorStyles.whiteBoldLabel : EditorStyles.whiteLabel);
        if (ShowTickCount)
        {
            string stats = $"T:{node.TickCount} {node.LastTickTimeMs:F2}ms";
            Handles.Label(center + Vector3.down * NodeHeight * 0.7f, stats,
                EditorStyles.miniLabel);
        }
#endif

        // Draw children for composite nodes
        if (node is CompositeNode composite && composite.Children.Count > 0)
        {
            float childStartX = position.x - subtreeWidth / 2f;
            float childY = position.y - VerticalSpacing - NodeHeight;
            float childSubtreeTotalWidth = 0f;

            // Calculate width proportions for each child's subtree
            float[] childWidths = new float[composite.Children.Count];
            for (int i = 0; i < composite.Children.Count; i++)
                childWidths[i] = CalculateSubtreeWidth(composite.Children[i]);
            float totalChildWidth = 0f;
            foreach (float w in childWidths) totalChildWidth += w + HorizontalSpacing;
            totalChildWidth -= HorizontalSpacing;

            float cursorX = position.x - totalChildWidth / 2f;
            for (int i = 0; i < composite.Children.Count; i++)
            {
                float cw = childWidths[i];
                Vector3 childPos = new(cursorX + cw / 2f, childY, position.z);

                // Draw connection line
                Gizmos.color = isActive ? Color.yellow : Color.gray;
                Gizmos.DrawLine(
                    new Vector3(position.x, position.y - NodeHeight / 2f, position.z),
                    new Vector3(childPos.x, childPos.y + NodeHeight / 2f, childPos.z));

                DrawNode(composite.Children[i], childPos, depth + 1, cw);
                cursorX += cw + HorizontalSpacing;
            }
        }

        return subtreeWidth;
    }

    // Walk the tree to determine if `target` is an ancestor or the active
    // leaf on the current execution path
    bool IsNodeOnActivePath(BTNode target, BTNode current)
    {
        if (current == target) return true;
        if (current is CompositeNode composite)
        {
            int activeIdx = composite.ActiveChildIndex;
            if (activeIdx >= 0 && activeIdx < composite.Children.Count)
                return IsNodeOnActivePath(target, composite.Children[activeIdx]);
        }
        if (current is DecoratorNode decorator && decorator.Child != null)
            return IsNodeOnActivePath(target, decorator.Child);
        return false;
    }

    Color GetStateColor(BTNodeState state, bool isActive)
    {
        if (!isActive) return new Color(0.3f, 0.3f, 0.3f, 0.5f);
        return state switch
        {
            BTNodeState.Success => Color.green,
            BTNodeState.Failure => Color.red,
            BTNodeState.Running => Color.yellow,
            _ => Color.gray
        };
    }

    Color GetTimingHeatmapColor(float ms)
    {
        if (ms < 0.01f) return Color.white;
        if (ms < 0.1f) return Color.green;
        if (ms < 0.5f) return Color.yellow;
        if (ms < 2.0f) return new Color(1f, 0.5f, 0f); // orange
        return Color.red;
    }
}
```

**使用方式**：将此脚本挂载到场景中的空 GameObject，在 Inspector 中拖入目标 AI 的 `BehaviorTreeRunner` 引用。Scene View 中会以 3D 盒子和连线绘制行为树。切换 `ShowTimingHeatmap` 可以在逻辑状态和性能热力图之间切换。

> **设计要点**：`CalculateSubtreeWidth` 的递归计算确保了子节点在父节点下方均匀分布，不会重叠。`IsNodeOnActivePath` 通过追踪 Composite 节点的 `ActiveChildIndex`（运行中 Composite 必须维护此字段）精确判定活跃路径。

---

### 示例 B: Unity Editor Window BT 调试器面板

**目的**：提供非运行模式也可查看的 Editor Window，在 Play Mode 中以表格和树形结构实时展示行为树状态、Blackboard 值、Tick 历史。

```csharp
// BTDebuggerWindow.cs — Place in an Editor/ folder
using UnityEngine;
using UnityEditor;
using System.Collections.Generic;
using System.Linq;

public class BTDebuggerWindow : EditorWindow
{
    [MenuItem("Window/AI/Behavior Tree Debugger")]
    public static void ShowWindow()
    {
        GetWindow<BTDebuggerWindow>("BT Debugger");
    }

    // Tracked target
    private BehaviorTreeRunner _target;
    private Vector2 _treeScroll, _bbScroll, _historyScroll;

    // Tick history ring buffer
    private Queue<(float time, string activeNode, BTNodeState state)> _tickHistory = new();
    private const int MaxHistoryEntries = 200;

    private bool _autoRefresh = true;
    private bool _showFullTree = false;
    private float _refreshInterval = 0.1f;
    private float _lastRefreshTime;

    void OnEnable()
    {
        EditorApplication.update += OnEditorUpdate;
    }

    void OnDisable()
    {
        EditorApplication.update -= OnEditorUpdate;
    }

    void OnEditorUpdate()
    {
        if (!_autoRefresh || _target == null) return;
        if (Time.realtimeSinceStartup - _lastRefreshTime < _refreshInterval) return;
        _lastRefreshTime = Time.realtimeSinceStartup;
        Repaint();
    }

    void OnGUI()
    {
        EditorGUILayout.Space(5);

        // Target selection
        EditorGUILayout.BeginHorizontal();
        _target = EditorGUILayout.ObjectField("Target AI", _target,
            typeof(BehaviorTreeRunner), true) as BehaviorTreeRunner;
        _autoRefresh = EditorGUILayout.Toggle("Auto Refresh", _autoRefresh);
        EditorGUILayout.EndHorizontal();

        if (_target == null)
        {
            EditorGUILayout.HelpBox(
                "Select a GameObject with a BehaviorTreeRunner component in the scene.",
                MessageType.Info);
            return;
        }

        _showFullTree = EditorGUILayout.Toggle("Show Full Tree", _showFullTree);

        EditorGUILayout.Space(5);

        // Split into two horizontal sections: Tree view + Right panel (BB + History)
        EditorGUILayout.BeginHorizontal();

        // LEFT: Tree view
        EditorGUILayout.BeginVertical(GUILayout.Width(position.width * 0.55f));
        EditorGUILayout.LabelField("Behavior Tree", EditorStyles.boldLabel);
        _treeScroll = EditorGUILayout.BeginScrollView(_treeScroll);
        if (_target.Root != null)
            DrawTreeNode(_target.Root, 0);
        else
            EditorGUILayout.LabelField("(No behavior tree loaded)");
        EditorGUILayout.EndScrollView();
        EditorGUILayout.EndVertical();

        // RIGHT: Blackboard + History
        EditorGUILayout.BeginVertical();
        DrawBlackboardPanel();
        EditorGUILayout.Space(10);
        DrawHistoryPanel();
        EditorGUILayout.EndVertical();

        EditorGUILayout.EndHorizontal();

        // Manual refresh button and recording
        EditorGUILayout.BeginHorizontal();
        if (GUILayout.Button("Refresh Now")) Repaint();
        if (GUILayout.Button("Clear History")) _tickHistory.Clear();
        EditorGUILayout.EndHorizontal();
    }

    void DrawTreeNode(BTNode node, int depth)
    {
        if (node == null) return;

        // Determine active path for highlighting
        bool isActive = IsOnActivePath(node, _target.Root);
        bool isLeaf = node is not CompositeNode;

        // Background color
        Color bgColor = isActive
            ? GetStateColor(node.LastState)
            : new Color(0.25f, 0.25f, 0.25f, 0.3f);
        GUI.backgroundColor = bgColor;

        string indent = new string(' ', depth * 4);
        string icon = node switch
        {
            Selector => "?",
            Sequence => "→",
            Parallel => "∥",
            DecoratorNode => "◇",
            _ => "•"
        };

        string label = $"{indent}{icon} {node.DebugName}";
        if (isLeaf)
            label += $"  [{node.LastState}]  T:{node.TickCount}";

        EditorGUILayout.BeginHorizontal(EditorStyles.helpBox);

        if (Application.isPlaying)
        {
            // Color swatch
            Rect swatchRect = GUILayoutUtility.GetRect(16, 16, GUILayout.Width(16));
            EditorGUI.DrawRect(swatchRect, GetStateColor(node.LastState));
        }

        EditorGUILayout.LabelField(label, isActive ? EditorStyles.boldLabel : EditorStyles.label);

        // Show timing if playing
        if (Application.isPlaying)
        {
            GUILayout.FlexibleSpace();
            string timing = $"{node.LastTickTimeMs:F3}ms";
            EditorGUILayout.LabelField(timing, GUILayout.Width(65));
        }

        EditorGUILayout.EndHorizontal();

        // Push history entry for the active leaf
        if (Application.isPlaying && isActive && isLeaf && node.LastState == BTNodeState.Running)
        {
            RecordTickHistory(node.DebugName, node.LastState);
        }

        // Recursively draw children (respect showFullTree toggle)
        if (node is CompositeNode composite)
        {
            foreach (var child in composite.Children)
            {
                if (_showFullTree || IsOnActivePath(child, _target.Root))
                    DrawTreeNode(child, depth + 1);
            }
        }
        else if (node is DecoratorNode decorator && decorator.Child != null)
        {
            if (_showFullTree || isActive)
                DrawTreeNode(decorator.Child, depth + 1);
        }

        GUI.backgroundColor = Color.white;
    }

    void RecordTickHistory(string nodeName, BTNodeState state)
    {
        var entry = (Time.time, nodeName, state);
        // Deduplicate consecutive same-node Running entries
        if (_tickHistory.Count > 0)
        {
            var last = _tickHistory.Peek();
            if (last.nodeName == nodeName && last.state == state)
                return;
        }
        _tickHistory.Enqueue(entry);
        while (_tickHistory.Count > MaxHistoryEntries)
            _tickHistory.Dequeue();
    }

    void DrawBlackboardPanel()
    {
        EditorGUILayout.LabelField("Blackboard", EditorStyles.boldLabel);
        if (_target.Blackboard == null)
        {
            EditorGUILayout.LabelField("(No Blackboard)");
            return;
        }

        _bbScroll = EditorGUILayout.BeginScrollView(_bbScroll,
            GUILayout.Height(150));
        foreach (var kvp in _target.Blackboard.GetAllEntries())
        {
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.LabelField(kvp.Key, GUILayout.Width(100));
            EditorGUILayout.LabelField(kvp.Value?.ToString() ?? "null");
            EditorGUILayout.EndHorizontal();
        }
        EditorGUILayout.EndScrollView();
    }

    void DrawHistoryPanel()
    {
        EditorGUILayout.LabelField("Tick History", EditorStyles.boldLabel);
        _historyScroll = EditorGUILayout.BeginScrollView(_historyScroll,
            GUILayout.Height(150));
        foreach (var entry in _tickHistory.Reverse().Take(50))
        {
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.LabelField($"{entry.time:F2}s", GUILayout.Width(50));
            GUI.backgroundColor = GetStateColor(entry.state);
            EditorGUILayout.LabelField(entry.activeNode);
            GUI.backgroundColor = Color.white;
            EditorGUILayout.EndHorizontal();
        }
        EditorGUILayout.EndScrollView();
    }

    bool IsOnActivePath(BTNode target, BTNode current)
    {
        if (current == target) return true;
        if (current is CompositeNode c && c.ActiveChildIndex >= 0
            && c.ActiveChildIndex < c.Children.Count)
            return IsOnActivePath(target, c.Children[c.ActiveChildIndex]);
        if (current is DecoratorNode d && d.Child != null)
            return IsOnActivePath(target, d.Child);
        return false;
    }

    Color GetStateColor(BTNodeState state)
    {
        return state switch
        {
            BTNodeState.Success => new Color(0.3f, 0.8f, 0.3f),
            BTNodeState.Failure => new Color(0.9f, 0.3f, 0.3f),
            BTNodeState.Running => new Color(1f, 0.85f, 0.2f),
            _ => Color.gray
        };
    }
}
```

**设计要点**：
- `OnEditorUpdate` 以可配置的频率刷新（默认 0.1s），避免每 Editor 帧都 Rebuild GUI 造成的卡顿
- Tick 历史记录使用去重逻辑（连续的同节点同状态只记一次），避免缓冲区被同一帧的多次 repaint 填满
- "Show Full Tree" 开关默认关闭——只显示活跃路径，大幅减少视觉噪音

---

### 示例 C: UE C++ 自定义 AI 调试类别与 DrawDebugString

**目的**：创建自定义 Debug Category，在 AI Task 执行期间在世界上绘制调试文字，并通过 Gameplay Debugger 扩展显示自定义信息。

```cpp
// AIDebugHelpers.h
#pragma once

#include "CoreMinimal.h"
#include "GameplayDebuggerCategory.h"

// Custom debug category for our game's AI system.
// Extends the built-in GameplayDebugger with project-specific info.
class FGameplayDebuggerCategory_MyAI : public FGameplayDebuggerCategory
{
public:
    FGameplayDebuggerCategory_MyAI();

    // Collect data for the currently selected actor (called every frame for debugged actor)
    virtual void CollectData(APlayerController* OwnerPC, AActor* DebugActor) override;

    // Render on-screen overlay
    virtual void DrawData(APlayerController* OwnerPC,
        FGameplayDebuggerCanvasContext& CanvasContext) override;

    // Create the category instance (called by the debugger subsystem)
    static TSharedRef<FGameplayDebuggerCategory> MakeInstance();

protected:
    struct FRepData
    {
        FString CurrentTaskName;
        FString CurrentBehaviorName;
        FString BlackboardSummary;
        float BTTimeThisFrameMs = 0.0f;
        int32 NumActiveServices = 0;
        FVector LastMoveDestination = FVector::ZeroVector;
        bool bHasTarget = false;

        void Serialize(FArchive& Ar);
    };
    FRepData DataPack;
};
```

```cpp
// AIDebugHelpers.cpp
#include "AIDebugHelpers.h"
#include "AIController.h"
#include "BehaviorTree/BehaviorTreeComponent.h"
#include "BehaviorTree/BlackboardComponent.h"
#include "GameFramework/PlayerController.h"

FGameplayDebuggerCategory_MyAI::FGameplayDebuggerCategory_MyAI()
{
    // Show this category alongside the built-in BehaviorTree category
    SetDataPackReplication<FRepData>(&DataPack);

    // Category appears in the debugger panel
    bShowCategoryName = true;
    bShowDataPackReplication = true;
}

TSharedRef<FGameplayDebuggerCategory>
FGameplayDebuggerCategory_MyAI::MakeInstance()
{
    return MakeShareable(new FGameplayDebuggerCategory_MyAI());
}

void FGameplayDebuggerCategory_MyAI::CollectData(APlayerController* OwnerPC,
    AActor* DebugActor)
{
    DataPack = FRepData(); // reset

    if (!DebugActor) return;

    APawn* DebugPawn = Cast<APawn>(DebugActor);
    if (!DebugPawn) return;

    AAIController* AIController = Cast<AAIController>(DebugPawn->GetController());
    if (!AIController) return;

    UBehaviorTreeComponent* BTComp =
        Cast<UBehaviorTreeComponent>(AIController->GetBrainComponent());
    if (!BTComp) return;

    // Extract current task name from the active node stack
    const UBTNode* ActiveNode = BTComp->GetActiveNode();
    DataPack.CurrentTaskName = ActiveNode
        ? ActiveNode->GetNodeName() : TEXT("(None)");

    // Behavior tree asset name
    if (BTComp->GetRootTree())
        DataPack.CurrentBehaviorName = BTComp->GetRootTree()->GetName();

    // Blackboard summary
    UBlackboardComponent* BB = AIController->GetBlackboardComponent();
    if (BB)
    {
        DataPack.BlackboardSummary = FString::Printf(
            TEXT("Target: %s | Alerted: %s | MoveSpeed: %.0f"),
            *BB->GetValueAsName("TargetActor").ToString(),
            BB->GetValueAsBool("IsAlerted") ? TEXT("Yes") : TEXT("No"),
            BB->GetValueAsFloat("MoveSpeed"));
    }

    // Last move destination from Blackboard
    if (BB)
        DataPack.LastMoveDestination = BB->GetValueAsVector("MoveToLocation");

    DataPack.bHasTarget = BB && BB->GetValueAsObject("TargetActor") != nullptr;
}

void FGameplayDebuggerCategory_MyAI::DrawData(APlayerController* OwnerPC,
    FGameplayDebuggerCanvasContext& CanvasContext)
{
    CanvasContext.Printf(TEXT("{green}=== My AI Debug ==={white}"));
    CanvasContext.Printf(TEXT("Behavior: {yellow}%s"), *DataPack.CurrentBehaviorName);
    CanvasContext.Printf(TEXT("Active Task: {yellow}%s"), *DataPack.CurrentTaskName);
    CanvasContext.Printf(TEXT("BT Time: {yellow}%.3fms"), DataPack.BTTimeThisFrameMs);
    CanvasContext.Printf(TEXT("Blackboard: %s"), *DataPack.BlackboardSummary);

    if (DataPack.bHasTarget)
        CanvasContext.Printf(TEXT("Target: {red}[ACQUIRED]{white}"));
    else
        CanvasContext.Printf(TEXT("Target: {gray}(none)"));
}

void FGameplayDebuggerCategory_MyAI::FRepData::Serialize(FArchive& Ar)
{
    Ar << CurrentTaskName;
    Ar << CurrentBehaviorName;
    Ar << BlackboardSummary;
    Ar << BTTimeThisFrameMs;
    Ar << NumActiveServices;
    Ar << LastMoveDestination;
    Ar << bHasTarget;
}
```

**注册自定义类别**——在你的 GameModule 的 `StartupModule` 中添加：

```cpp
// MyGameModule.cpp
#include "GameplayDebugger.h"
#include "AIDebugHelpers.h"

void FMyGameModule::StartupModule()
{
    // Register custom AI debug category
    IGameplayDebugger& Debugger = IGameplayDebugger::Get();
    Debugger.RegisterCategory("MyAI",
        IGameplayDebugger::FOnGetCategory::CreateStatic(
            &FGameplayDebuggerCategory_MyAI::MakeInstance),
        EGameplayDebuggerCategoryState::EnabledInGameAndSimulate,
        5); // sort order — after built-in BT category (which is 4)
}

void FMyGameModule::ShutdownModule()
{
    if (IGameplayDebugger::IsAvailable())
        IGameplayDebugger::Get().UnregisterCategory("MyAI");
}
```

**在 Task 中使用 DrawDebugString**：

```cpp
// In your custom BTTask::TickTask
void UBTTask_MyAttack::TickTask(UBehaviorTreeComponent& OwnerComp,
    uint8* NodeMemory, float DeltaSeconds)
{
    Super::TickTask(OwnerComp, NodeMemory, DeltaSeconds);

    AAIController* AIController = OwnerComp.GetAIOwner();
    if (!AIController) return;

    APawn* Pawn = AIController->GetPawn();
    if (!Pawn) return;

    // Draw current task state above the AI's head
    FVector HeadLocation = Pawn->GetActorLocation() + FVector(0, 0, 120.0f);
    FString DebugMsg = FString::Printf(TEXT("[%s] %.1fs elapsed"),
        *GetNodeName(), GetElapsedTime(NodeMemory));

    DrawDebugString(GetWorld(), HeadLocation, DebugMsg,
        nullptr, FColor::Cyan, 0.0f, true, 1.2f);

    // Draw line to attack target if applicable
    UBlackboardComponent* BB = OwnerComp.GetBlackboardComponent();
    if (AActor* Target = Cast<AActor>(BB->GetValueAsObject("TargetActor")))
    {
        DrawDebugLine(GetWorld(), Pawn->GetActorLocation(),
            Target->GetActorLocation(), FColor::Red,
            false, -1.0f, 0, 2.0f);
    }
}
```

**使用方式**：在运行时按 `'` 打开 Gameplay Debugger，小键盘数字键或顶部标签切换到 "MyAI" 类别。自定义 Task 的 `DrawDebugString` 在世界空间中始终可见（不需要打开 GDT）。

---

## 3. 练习

### 练习 1: 添加 per-node Tick 计数和计时 instrumentation

**目标**：在你基于 Tutorial 08 构建的 C# 行为树框架中，为每个节点添加 Tick 计数和计时统计，并将结果渲染为简易的 profiler 叠加层。

**步骤**：

1. 在 `BTNode` 基类中添加 `TickCount`、`TotalTickTimeMs`、`LastTickTimeMs` 字段，在 `Tick()` 方法中使用 `Stopwatch` 测量耗时
2. 创建一个 `BTProfilerOverlay` 类，使用 `OnGUI()` 在屏幕左上角渲染一个紧凑的 profiler 面板：
   - 以表格形式列出 Top 10 最耗时的节点类型（按 `TotalTickTimeMs` 降序排列）
   - 每行显示：节点名称、Tick 次数、总耗时、平均耗时、最大单次耗时
3. 添加一个快捷键（如 `F1`）切换 profiler 面板的显示/隐藏
4. 添加 `Reset()` 方法将统计归零，绑定到另一个快捷键（如 `F2`）

**验收标准**：
- 在场景中放置 3+ 个运行不同行为树的 AI，profiler 叠加层正确聚合所有 AI 的统计
- `Reset` 后统计归零，新的 tick 重新开始累积
- 可以通过对比不同节点类型的平均耗时，定位性能热点

**提示**：使用 `GUILayout.BeginArea` 锁定叠加层在屏幕左上角；用 `Stopwatch.GetTimestamp() / (double)Stopwatch.Frequency * 1000.0` 获取高精度毫秒级时间戳。

---

### 练习 2: 实现 AI LOD 系统

**目标**：为你的 AI 系统实现三层 LOD——基于与玩家（或 Camera）的距离动态切换决策复杂度。

**步骤**：

1. 定义 `AILODLevel` 枚举：`FullBT`（< `FullDistance`）、`SimplifiedFSM`（< `SimplifiedDistance`）、`Disabled`（> `SimplifiedDistance`）
2. 在 `BehaviorTreeRunner` 中添加距离检查和 LOD 切换逻辑：
   - 每 0.5 秒检查一次距离（不要每帧检查——本身就有开销）
   - 当 LOD 变化时，执行平滑过渡：
     - LOD 0 → LOD 1：从 BT 的当前活跃行为推导 FSM 初始状态（如 BT 正在 Attack → FSM 的 Combat 状态）
     - LOD 1 → LOD 0：FSM 退出当前状态，BT 从根重新评估
3. 实现简化 FSM：设计一个 3-5 状态的轻量 FSM，覆盖战斗/移动/待机/受伤等核心行为，行为逻辑与完整 BT 保持一致但决策更简单
4. 添加事件唤醒：即使 AI 处于 `Disabled` 状态，当它受到伤害时，临时升到 `FullBT` 并在 3 秒后降回
5. 使用 Scene View Gizmos 渲染每个 AI 头顶的 LOD 等级标签（绿/黄/灰）

**验收标准**：
- 远离玩家的 AI（LOD 1/Disabled）每帧 CPU 开销明显低于近处 AI（LOD 0）
- LOD 切换时 AI 行为无跳变（不会突然重置到巡逻）
- 对远处 AI 造成伤害后，该 AI 正确切换到 FullBT 并开始战斗行为

---

### 练习 3（选做）: 录制与回放完整 BT Trace

**目标**：实现行为树的"时间旅行调试"——录制 60 秒内每一帧每一节点的 Tick 状态和 Blackboard 值，然后离线逐帧回放。

**步骤**：

1. 定义 trace 数据结构：

```csharp
[Serializable]
public struct BTFrameTrace
{
    public int FrameNumber;
    public float GameTime;
    public List<BTNodeTrace> NodeTraces;
}

[Serializable]
public struct BTNodeTrace
{
    public string NodeName;
    public int NodeInstanceId;
    public BTNodeState State;
    public float TickTimeMs;
}

[Serializable]
public struct BTFullTrace
{
    public List<BTFrameTrace> Frames;
    public Dictionary<int, Dictionary<string, string>> BlackboardSnapshots; // frame -> key/values
}
```

2. 在 `BehaviorTreeRunner` 中添加录制模式——当录制启用时，在 `Tick()` 返回前将当前帧的节点状态追加到 `BTFullTrace`
3. 实现 `BTReplayWindow`（Editor Window）：
   - 加载录制的 trace 文件
   - 时间轴滑块（0s 到录制时长）
   - 在当前选中帧渲染完整的树状态和 Blackboard 快照
   - "播放/暂停"按钮以 1x/0.5x/0.1x 速度自动推进
   - 单帧前进/后退按钮
4. 使用此工具调试具体的 AI bug——例如"为什么 NPC 在第 420 帧停止了追击"

**验收标准**：
- 录制 60fps × 60s = 3600 帧数据不会导致明显帧率下降（录制开销 < 5% 帧时间）
- 回放时可以在任意帧间跳转并看到正确的树状态
- 能够定位至少一个时序相关的 AI bug

---

## 4. 扩展阅读

- **Unreal Engine AI Debugging Docs** — [Gameplay Debugger](https://docs.unrealengine.com/5.3/en-US/gameplay-debugger-in-unreal-engine/), [Visual Logger](https://docs.unrealengine.com/5.3/en-US/visual-logger-in-unreal-engine/), [Behavior Tree Debugger](https://docs.unrealengine.com/5.3/en-US/behavior-tree-in-unreal-engine---debugging/)
- **Unity Gizmos & Handles API** — [Gizmos](https://docs.unity3d.com/ScriptReference/Gizmos.html), [Handles](https://docs.unity3d.com/ScriptReference/Handles.html), [EditorWindow](https://docs.unity3d.com/ScriptReference/EditorWindow.html)
- **GDC Talks on Game AI Profiling**:
  - *"AI and Performance: Case Studies from The Last of Us Part II"* (Naughty Dog, GDC 2021) — profiling techniques for large-scale AI systems with BT, perception, and pathfinding integration
  - *"Building a Better Centaur: AI for Horizon Forbidden West"* (Guerrilla, GDC 2023) — LOD systems, off-screen AI optimization, and the balance between behavior fidelity and performance
- **DOTS/ECS AI Performance Patterns** — Unity's [DOTS Best Practices](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/) for large-scale AI: `IJobEntity`-based BT evaluation, burst-compiled node tick, `EntityCommandBuffer` for structural changes
- **Bungie's Halo 2 AI Debugging** — The original GDC 2005 talk by Damian Isla heavily discusses the need for AI visualization; the tools they built (in-engine tree inspector, per-node state overlay) directly inspired UE's Gameplay Debugger
- **BehaviorTree.CPP** on GitHub — The open-source C++ behavior tree library has a built-in `TreeRecorder` and `TreeVisualizer` (Groot2 companion editor) that are instructive to study for architecture patterns

---

## 常见陷阱

### 1. Debug Drawing 在 Shipping Build 中的性能代价

**症状**：Development Build 中 AI 行为正常，Shipping Build 中帧率明显更高——但 Shipping Build 中 AI 行为出现不可复现的 bug。

**根因**：没有用条件编译包裹所有 debug drawing 代码。`DrawDebugString`、`Handles.Label`、`OnDrawGizmos` 在 Shipping Build 中虽然功能正确，但仍然消耗 CPU 构建字符串和调用空操作 API。

**解法**：

```csharp
#if UNITY_EDITOR || DEVELOPMENT_BUILD
    DrawDebugInfo();
#endif
```

在 UE 中使用 `#if !UE_BUILD_SHIPPING` 或 `UE_BUILD_TEST`。确保所有 debug 数据收集（如 `Stopwatch` 测量、字符串格式化）也在条件编译内——数据的生产本身可能比绘制更昂贵。

### 2. Deep Profile 的开销扭曲了真实性能

**症状**：在 Unity Profiler 的 Deep Profile 模式下，`Selector.Tick()` 占用 60% 的帧时间。关闭 Deep Profile 后，实际只有 5%。

**根因**：Deep Profile 为**每一个方法调用**（包括 getter/setter、属性访问、`List<T>.get_Item`）插入 instrumentation。在行为树的深度递归调用链中，每帧可能有数百次方法调用——instrumentation 本身的开销远大于实际逻辑。

**解法**：
- 优先使用手动 `Profiler.BeginSample/EndSample` 标记关键代码段，而非全量 Deep Profile
- 如果需要 Deep Profile 级粒度，只在单帧内做 snapshot profiling，而非持续录制
- 对自研 instrumentation 系统，在统计函数中添加最小耗时过滤——只记录和显示 > 0.001ms 的节点

### 3. LOD 切换时的视觉 Pop-in

**症状**：摄像机向 AI 靠近时，AI 突然从"原地站立"（LOD 1 的简化 FSM 只有待机动画）切换到"持枪瞄准"（LOD 0 的完整 BT 检测到玩家后进入战斗）。玩家明显感知到 AI 状态的突变。

**根因**：LOD 切换是瞬间的——简化 FSM 没有维护"对这个 AI 当前应该做什么"的精确信息，切换到 BT 后必须重新评估。

**解法**：
- LOD 1 下降时，将简化 FSM 的状态信息写入 Blackboard（如 `LastActiveBehavior = "Patrol"`），LOD 0 恢复时 BT 读取此信息作为初始提示
- 将 LOD 切换距离设置得足够远，使 Pop-in 发生在玩家视野之外（或渲染距离之外）
- 在切换时使用交叉渐变（lerp），而不是瞬间切换——例如 LOD 1 FSM 的动画播放完当前循环后再切换到 BT 控制

### 4. 大量 AI 同时启用可视化时的视觉混乱

**症状**：场景中有 20+ 个 AI，每个都打开了 Scene View 调试可视化（Gizmos/Handles），Scene View 被密集的彩色盒子和连线淹没，完全无法阅读任何单个 AI 的状态。

**根因**：可视化系统没有过滤机制——默认显示所有 AI 的完整树。

**解法**：
- **只可视化选中对象**：`OnDrawGizmos` 中检查 `Selection.activeGameObject == this.gameObject`，非选中 AI 不绘制
- **距离过滤**：只在玩家一定范围内的 AI 渲染调试信息
- **LOD 感知**：LOD 2 的 AI 完全不绘制；LOD 1 的 AI 只在头顶绘制一个简单的状态图标
- **Debug Category 开关**：提供独立的"显示树结构"、"显示 Blackboard"、"显示计时热力图"开关，AI 工程师根据需要组合

### 5. `foreach` 在 Composite 节点的 GC 分配

**症状**：使用 Unity Profiler 发现 `Selector.Tick()` 和 `Sequence.Tick()` 每帧产生 40B×节点数的 GC 分配，导致周期性 GC spike。

**根因**：尽管 `List<T>.GetEnumerator()` 是值类型且不产生堆分配，但如果 `_children` 字段声明为 `IEnumerable<BTNode>` 或 `IList<BTNode>`，编译器会装箱枚举器。此外，lambda 表达式捕获、字符串拼接（调试日志中常见）也会产生 GC 分配。

**解法**：
- 将 `_children` 声明为 `List<BTNode>` 或 `BTNode[]`，避免接口类型
- 对于数组，C# 编译器将 `foreach` 编译为等效的 `for` 循环，零分配
- Debug 日志使用条件编译包裹，确保 Shipping Build 中不产生字符串分配
- 在 Tick 热路径中永远不使用 `string.Format`、`$` 字符串插值或 `+` 拼接——改用 `StringBuilder` 缓存并复用

---

> **下一步**: 完成本教程后，所有行为树核心系列（06-13）已完结。如果你计划深入研究 UE 的 Blackboard 系统，可回溯 Tutorial 11-12。否则，建议进入后续计划中的感知系统（Perception）或寻路系统（Pathfinding/NavMesh）专题。
