# 学习资源: State Machines & Behavior Trees for Game AI

## 官方文档

- [Unreal Engine Behavior Tree 文档](https://docs.unrealengine.com/en-US/InteractiveExperiences/ArtificialIntelligence/BehaviorTrees/)
- [Unreal Engine AI Perception 文档](https://docs.unrealengine.com/en-US/InteractiveExperiences/ArtificialIntelligence/AIPerception/)
- [Unreal Engine Environment Query System (EQS)](https://docs.unrealengine.com/en-US/InteractiveExperiences/ArtificialIntelligence/EQS/)
- [Unreal Engine StateTree (UE5)](https://docs.unrealengine.com/5.0/en-US/state-tree-in-unreal-engine/)
- [Unity Navigation & Pathfinding](https://docs.unity3d.com/Manual/Navigation.html)
- [Unity Behavior (Unity 6 BT package)](https://docs.unity3d.com/Packages/com.unity.behavior@1.0/manual/)
- [Lua 5.4 参考手册](https://www.lua.org/manual/5.4/)

## 推荐书籍

- **Game AI Pro 1/2/3** (Steven Rabin 编) — 游戏 AI 行业圣经，多章涵盖 FSM/BT/GOAP/Utility/HTN 的实际工程实践
- **Programming Game AI by Example** (Mat Buckland) — 经典入门，含有完整的 FSM 和消息系统实现
- **Artificial Intelligence for Games (3rd Edition)** (Ian Millington) — 综合性教材，覆盖决策系统全谱系
- **Behavioral Mathematics for Game AI** (Dave Mark) — Utility AI 的数学基础
- **Game Programming Patterns** (Robert Nystrom) — State 模式章节是 FSM 实现的必读
- **Behavior Trees in Robotics and AI: An Introduction** (Colledanchise & Ögren) — 行为树形式化理论的学术专著

## GDC 演讲 (Game Developers Conference)

- **Damian Isla (2005)** — *Managing Complexity in Halo 2 AI* — 行为树在游戏中的首次公开介绍
- **Damian Isla (2008)** — *Halo 3: Building a Better Battlefield* — 行为树的工程进化
- **Jeff Orkin (2006)** — *Three States and a Plan: The A.I. of F.E.A.R.* — GOAP 起源演讲
- **Dave Mark (2010-2019)** — 多场关于 Infinite Axis Utility System 的演讲
- **Mika Vehkala (2011)** — *Killzone 3 AI* — HTN 在 AAA 中的实践
- **Matthew Gallant (2017)** — *Deconstructing the AI of Horizon Zero Dawn*
- **Tommy Thompson** — AI and Games YouTube 频道，大量游戏 AI 案例分析

## 在线教程与博客

- [Chris Simpson — Behavior Trees for AI: How They Work](https://www.gamedeveloper.com/programming/behavior-trees-for-ai-how-they-work)
- [Bjoern Knafla — 行为树系列文章](https://www.bsknight.com/)
- [A Practical Guide to AI Decision-Making in Unity](https://unity.com/how-to/ai-and-machine-learning-games)
- [Game AI Pro 官网 — 部分章节在线](http://www.gameaipro.com/)

## 开源项目

- **BehaviorTree.CPP** — 工业级 C++ 行为树库，非游戏专用但设计思路可参考
- **Panda BT** — 轻量级 C++ 行为树编辑器框架
- **Unity Behavior Designer** (付费) — 最流行的 Unity 行为树插件，值得研究其架构
- **Unreal Engine Lyra Sample** (Epic 官方) — 包含 UE5 AI 系统的最佳实践示例
- **UE4/UE5 ShooterGame** (Epic 示例) — 包含完整的 BT + EQS AI 实现

## 面试准备资源

- Glassdoor / Levels.fyi — 搜索 "gameplay programmer"、"AI programmer" 面试题
- GDC Vault — 所有 GDC AI Summit 演讲录像
- LinkedIn — 关注 AAA 工作室的 AI 程序员，看他们的分享和技术栈
- GameDev.net / r/gameai — 行业讨论与面经

## 工具与调试

- **Unreal Engine Gameplay Debugger** (`'` 键) — AI 行为可视化
- **Unreal Engine Visual Logger** — 录制并回放 AI 决策
- **Unity Gizmos / Handles API** — 自定义 AI 调试可视化
- **Unity Profiler (Deep Profile)** — AI 性能分析
- **Unreal Insights** — 多线程 AI 性能分析
- **RenderDoc / PIX** — GPU 调试工具（AI 可视化也依赖渲染）
