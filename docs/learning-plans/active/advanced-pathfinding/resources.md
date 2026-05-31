# 学习资源汇总: 高阶寻路系统

> 书籍、论文、开源库、博客、视频 — 按阶段分类

---

## 书籍

| 书名 | 作者 | 覆盖范围 | 难度 |
|------|------|----------|------|
| *Artificial Intelligence: A Modern Approach (4th)* | Russell & Norvig | 第3-4章: 经典搜索算法理论 | 中 |
| *Game AI Pro* 系列 (1-4) | Steve Rabin 等 | 工业级游戏 AI 实践，含多篇寻路专题 | 中-高 |
| *Programming Game AI by Example* | Mat Buckland | 第8章: A* 与 Steering Behaviors 实战 | 初-中 |
| *AI for Games (3rd)* | Ian Millington | 第4章: 寻路全系列（A*→NavMesh→Crowd） | 中 |
| *Behavioral Mathematics for Game AI* | Dave Mark | 效用函数、代价建模数学基础 | 高 |

## 论文（按阶段）

### 基础与 A*
- Hart, Nilsson, Raphael (1968) — *A Formal Basis for the Heuristic Determination of Minimum Cost Paths* — A* 原始论文
- Patel, Amit — *Amit's A* Pages* (stanford.edu) — A* 最佳在线教程

### JPS & 搜索加速
- Harabor, Grastien (2011) — *Online Graph Pruning for Pathfinding on Grid Maps* — JPS 原始论文
- Botea, Müller, Schaeffer (2004) — *Near Optimal Hierarchical Path-Finding* — HPA* 原始论文
- Geisberger et al. (2008) — *Contraction Hierarchies: Faster and Simpler Hierarchical Routing in Road Networks*

### 任意角度 & 连续空间
- Nash et al. (2007) — *Theta*: Any-Angle Path Planning on Grids*
- Demyen, Buro (2006) — *Efficient Triangulation-Based Pathfinding* — Funnel Algorithm

### 动态环境
- Koenig, Likhachev (2005) — *Fast Replanning for Navigation in Unknown Terrain* — D* Lite
- Koenig, Likhachev, Furcy (2004) — *Lifelong Planning A** — LPA*

### NavMesh & Recast/Detour
- Mononen (2009) — *Recast Navigation Mesh Construction Toolkit* (AI Game Programming Wisdom 4)
- Kallmann, Kapadia (2016) — *Geometric and Discrete Path Planning for Interactive Virtual Worlds*

### ORCA & 局部避障
- van den Berg et al. (2008) — *Reciprocal Velocity Obstacles for Real-Time Multi-Agent Navigation* — RVO
- van den Berg et al. (2011) — *Reciprocal n-Body Collision Avoidance* — ORCA

### Flow Field
- Emerson (2013) — *Crowd Pathfinding and Steering Using Flow Field Tiles* — 文明系列技术

### GPU
- Bleiweiss (2008) — *GPU Accelerated Pathfinding* (Graphics Hardware)

## 开源库

| 库 | 语言 | 定位 | 链接 |
|----|------|------|------|
| **RecastNavigation** | C++ | Recast + Detour 官方实现 | github.com/recastnavigation/recastnavigation |
| **Detour** | C++ | Recast 项目中的运行时模块 | 同上 |
| **RVO2** | C++ | ORCA 官方参考实现 | gamma.cs.unc.edu/RVO2/ |
| **SharpNav** | C# | Recast/Detour 的 C# 移植 | github.com/Robmaister/SharpNav |
| **DotRecast** | C# | .NET 版 Recast/Detour | github.com/ikpil/DotRecast |
| **Pathfinding** | C# | A* 系列算法 Unity 实现 | arongranberg.com/astar/ |
| **Unity NavMesh Components** | C# | Unity 官方 NavMesh 扩展 | github.com/Unity-Technologies/NavMeshComponents |

## 在线工具与可视化

| 资源 | 描述 | 链接 |
|------|------|------|
| **Amit's A* Pages** | 最完整的 A* 教程含交互式演示 | theory.stanford.edu/~amitp/GameProgramming/ |
| **Pathfinding Visualizer** | 浏览器内算法对比可视化 | clementmihailescu.github.io/Pathfinding-Visualizer/ |
| **Red Blob Games** | 六边形网格 + 寻路可视化教程 | redblobgames.com |
| **Qiao's PathFinding.js** | 网页端多算法对比 | qiao.github.io/PathFinding.js/visual/ |

## 视频与课程

| 资源 | 作者 | 内容 |
|------|------|------|
| *A* Pathfinding (E01: algorithm explanation)* | Sebastian Lague (YouTube) | A* 从零实现，Unity 可视化 |
| *GDC — Navigation Meshes* | various | GDC Vault 上每年都有 NavMesh 相关演讲 |
| *MIT 6.034 Artificial Intelligence* | Patrick Winston | 图搜索理论课（免费 OCW） |
| *CS50 AI* | Harvard | 搜索算法入门（含寻路） |

## Unity 专项

| 资源 | 内容 |
|------|------|
| Unity Manual — Navigation System | Unity 内置 NavMesh 文档 |
| Unity ECS Samples | 官方的 Entities 示例项目 |
| DOTS Navigation Package | Unity 的 DOTS 寻路包（预览） |
| Code Monkey — Pathfinding in Unity | YouTube 系列教程 |

---

## 推荐阅读顺序

1. **入门**: Amit's A* Pages → *Programming Game AI by Example* 第8章
2. **深入**: *AI for Games* 第4章 → GDC NavMesh talks → RecastNavigation 源码
3. **前沿**: *Game AI Pro* 系列 → ORCA/RVO 论文 → GPU 寻路论文
