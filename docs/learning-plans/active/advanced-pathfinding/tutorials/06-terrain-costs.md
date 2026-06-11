---
title: "地形感知与移动代价"
updated: 2026-06-05
---

# 地形感知与移动代价

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: 网格数据结构 (05)，A* 寻路 (03)，基本的游戏地形概念

## 1. 概念讲解

### 为什么需要这个？

简单寻路只区分"能走/不能走"（二值网格）。但在真实游戏中，不同地形有不同的穿越代价：

- **道路** → 快速（代价 1.0）
- **草地** → 正常（代价 1.5）
- **森林** → 较慢（代价 3.0）
- **沼泽** → 很慢（代价 6.0）
- **浅水** → 慢且可能只有特定单位能走（代价 8.0，且需要"涉水"能力）
- **陡坡** → 额外惩罚（基础代价 + 斜率因子）

如果不考虑这些，寻路算法会选择穿越"沼泽+爬坡"的直线路径，而绕远路走平地可能实际更快。这在策略游戏（RTS）、开放世界 RPG 中尤其重要——地形代价直接影响战术决策。

### 核心思想

#### 代价模型：从二值到连续

```cpp
// 朴素模型
bool walkable;  // 只能表达"能走/不能走"

// 生产级模型
double base_cost;     // 基础穿越代价 (≥ 1.0)
double slope_penalty; // 坡度惩罚 (0.0 = 平地, 越大越陡)
double soft_cost;     // 可叠加的软惩罚 (影响图/动态事件)
```

寻路算法仍用 `g(n) + cost(n)` 扩展，**不需要改动算法本身**——代价变化完全编码在数据层。

#### 代价组合：多层叠加

生产环境中代价通常来自多个独立数据层：

```
final_cost = base_cost      // 基础地形类型
           × slope_factor   // 坡度影响（乘法）
           + soft_modifier  // 影响图/动态惩罚（加法）
           + agent_modifier // 单位特定（骑兵不能过森林）
```

关键设计决策：**加法还是乘法**？

- **乘法**（`base × slowdown`）→ 适合"减速"效果（沼泽让人走慢 3 倍）
- **加法**（`base + penalty`）→ 适合"额外开销"（爬坡多消耗体力，但不影响基础速度比）
- 实践中常**混用**：核心惩罚用乘法，特殊效果用加法。

#### 影响图 (Influence Maps) 作为代价层

影响图是一种**动态代价叠加层**——它不是地形本身的属性，而是游戏逻辑施加的软约束：

```
使用场景:
- 敌人视野覆盖区域 → 提升代价，单位绕开
- 友军聚集区域 → 降低代价，引导分散
- 近期发生过战斗的区域 → 提升代价，AI 绕开危险区
- 资源丰富区域 → 降低代价，工人/采集单位被吸引
```

实现：维护一个与网格等大的 `float[] influence` 数组，在寻路时加到基础代价上。

#### 代价曲线：非均匀缩放与梯度

单纯的数值代价无法表达"把单位推到路中央"的效果。更高级的做法是**代价梯度**——代价不仅在格子上不同，且在格子内有方向性：

```
路中央 cost=1.0 —— 路边 cost=1.3 —— 路外 cost=3.0
         ↑ 梯度指向路中央
```

这可以通过对 cost map 做高斯模糊（模糊惩罚，在 27 中深入）来实现。

## 2. 代码示例

### CostMap：多层代价合成 + 影响图

```cpp
// terrain_costs.cpp — 地形类型→代价映射, 多层组合, 影响图
// 编译: g++ -std=c++17 -O2 -Wall -o terrain_costs terrain_costs.cpp
// 运行: ./terrain_costs

#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <iomanip>
#include <string>
#include <unordered_map>
#include <cassert>
#include <functional>

// ============================================================
// 地形类型枚举
// ============================================================
enum class TerrainType : uint8_t {
    Road       = 0,
    Grass      = 1,
    Forest     = 2,
    Swamp      = 3,
    ShallowWater = 4,
    DeepWater  = 5,
    Mountain   = 6,
    Sand       = 7,
    COUNT
};

const char* terrain_name(TerrainType t) {
    switch (t) {
        case TerrainType::Road:    return "道路";
        case TerrainType::Grass:   return "草地";
        case TerrainType::Forest:  return "森林";
        case TerrainType::Swamp:   return "沼泽";
        case TerrainType::ShallowWater: return "浅水";
        case TerrainType::DeepWater:    return "深水";
        case TerrainType::Mountain:     return "山地";
        case TerrainType::Sand:         return "沙地";
        default: return "未知";
    }
}

// ============================================================
// 地形配置表：每个地形的基础属性
// ============================================================
struct TerrainConfig {
    double base_cost;        // 基础穿越代价
    bool walkable_default;   // 默认是否可通行
    double slope_sensitivity;// 对坡度的敏感度 (0=不受坡度影响)

    static constexpr double INF = std::numeric_limits<double>::infinity();
};

// 全局地形配置表 — 数据驱动而非硬编码
const TerrainConfig TERRAIN_DB[] = {
    //  base_cost, walkable, slope_sensitivity
    { 0.8, true,  0.1  }, // Road    — 道路：很快，坡度影响小
    { 1.0, true,  0.3  }, // Grass   — 草地：基准
    { 2.5, true,  1.0  }, // Forest  — 森林：较慢，坡度明显影响
    { 5.0, true,  2.0  }, // Swamp   — 沼泽：很慢，坡度加重
    { 4.0, true,  0.5  }, // ShallowWater — 浅水：慢，需涉水能力
    { INF, false, 0.0  }, // DeepWater — 深水：不可通行
    { INF, false, 0.0  }, // Mountain  — 山地：不可通行
    { 1.8, true,  0.8  }, // Sand     — 沙地：稍慢
};

// ============================================================
// 高度图 (Height Map) — 用于坡度计算
// ============================================================
class HeightMap {
    int rows_, cols_;
    std::vector<float> heights_;  // SoA 平坦数组

public:
    HeightMap(int r, int c) : rows_(r), cols_(c), heights_(r * c, 0.0f) {}

    int rows() const { return rows_; }
    int cols() const { return cols_; }

    size_t idx(int x, int y) const { return y * cols_ + x; }
    bool in_bounds(int x, int y) const {
        return x >= 0 && x < rows_ && y >= 0 && y < cols_;
    }

    float height_at(int x, int y) const { return heights_[idx(x, y)]; }
    void set_height(int x, int y, float h) { heights_[idx(x, y)] = h; }

    // 计算从 (x,y) 到 (nx,ny) 的坡度 (0.0 = 平, 1.0 = 45°, >1.0 更陡)
    double slope_to(int x, int y, int nx, int ny) const {
        float h1 = height_at(x, y);
        float h2 = height_at(nx, ny);
        // 假设相邻格子水平距离 = 1.0
        // slope = Δh / Δhorizontal = |h2 - h1|
        return std::abs(h2 - h1);
    }
};

// ============================================================
// CostMap: 多层代价合成
// ============================================================
class CostMap {
public:
    int rows, cols;

private:
    std::vector<double>      base_cost_;    // 来自地形类型
    std::vector<TerrainType> terrain_type_; // 底层地形
    std::vector<bool>        walkable_;
    std::vector<double>      influence_;    // 影响图 (软惩罚，0.0 默认)
    const HeightMap*         heightmap_;

public:
    CostMap(int r, int c, const HeightMap* hm = nullptr)
        : rows(r), cols(c),
          base_cost_(r * c, 1.0),
          terrain_type_(r * c, TerrainType::Grass),
          walkable_(r * c, true),
          influence_(r * c, 0.0),
          heightmap_(hm)
    {}

    size_t idx(int x, int y) const { return y * cols + x; }
    bool in_bounds(int x, int y) const {
        return x >= 0 && x < rows && y >= 0 && y < cols;
    }

    // ---- 设置地形 ----
    void set_terrain(int x, int y, TerrainType t) {
        size_t i = idx(x, y);
        terrain_type_[i] = t;
        base_cost_[i]   = TERRAIN_DB[static_cast<int>(t)].base_cost;
        walkable_[i]    = TERRAIN_DB[static_cast<int>(t)].walkable_default;
    }

    TerrainType terrain_at(int x, int y) const { return terrain_type_[idx(x, y)]; }
    double base_cost_at(int x, int y)   const { return base_cost_[idx(x, y)]; }
    bool   walkable_at(int x, int y)    const { return walkable_[idx(x, y)]; }

    // ---- 影响图操作 ----
    double influence_at(int x, int y) const { return influence_[idx(x, y)]; }
    void set_influence(int x, int y, double v) { influence_[idx(x, y)] = v; }

    // 在整个区域施加衰减影响（高斯衰减）
    void apply_radial_influence(int cx, int cy, int radius, double strength) {
        for (int y = cy - radius; y <= cy + radius; ++y) {
            for (int x = cx - radius; x <= cx + radius; ++x) {
                if (!in_bounds(x, y)) continue;
                double dx = x - cx, dy = y - cy;
                double dist = std::sqrt(dx * dx + dy * dy);
                if (dist > radius) continue;
                double falloff = 1.0 - dist / radius; // 线性衰减
                influence_[idx(x, y)] += strength * falloff;
            }
        }
    }

    void clear_influence() { std::fill(influence_.begin(), influence_.end(), 0.0); }

    // ---- 最终代价计算：多层合成 ----
    double final_cost(int x, int y, int nx, int ny) const {
        if (!walkable_at(nx, ny)) return INFINITY;

        size_t ni = idx(nx, ny);

        // Layer 1: 目标格子的基础地形代价
        double cost = base_cost_[ni];

        // Layer 2: 坡度惩罚（如果高度图存在）
        if (heightmap_) {
            double slope = heightmap_->slope_to(x, y, nx, ny);
            double sensitivity = TERRAIN_DB[static_cast<int>(terrain_type_[ni])].slope_sensitivity;
            // 上坡惩罚：上升比下降更费力
            double dh = heightmap_->height_at(nx, ny) - heightmap_->height_at(x, y);
            double slope_cost = slope * sensitivity;
            if (dh > 0) slope_cost *= 1.5; // 上坡 ×1.5
            cost += slope_cost;
        }

        // Layer 3: 影响图软惩罚（加法）
        cost += influence_[ni];

        // Layer 4: 确保最小值 — 我们不希望代价降到 0 以下
        cost = std::max(cost, 0.1);

        return cost;
    }

    // 简化的最终代价（不考虑方向，用于启发函数）
    double final_cost_simple(int x, int y) const {
        if (!walkable_at(x, y)) return INFINITY;
        double cost = base_cost_[idx(x, y)];
        cost += influence_[idx(x, y)];
        return std::max(cost, 0.1);
    }

    // 批量计算影响图均值（调试用）
    double average_influence() const {
        double sum = 0;
        for (double v : influence_) sum += v;
        return sum / influence_.size();
    }
};

// ============================================================
// 单位/Agent 特定代价修饰器
// ============================================================
struct AgentTraits {
    double speed_multiplier = 1.0;   // 全局速度倍率
    bool can_swim = false;           // 能否通过深水
    double forest_penalty = 1.0;     // 森林额外惩罚 (骑兵 > 步兵)
    double mountain_cost = INFINITY; // 山地能否通行

    static constexpr double INF = std::numeric_limits<double>::infinity();
};

double agent_adjusted_cost(const CostMap& map, int x, int y,
                            int nx, int ny, const AgentTraits& traits) {
    double base = map.final_cost(x, y, nx, ny);
    if (std::isinf(base)) return base;

    TerrainType tt = map.terrain_at(nx, ny);

    // 骑兵在森林中更慢
    if (tt == TerrainType::Forest)
        base *= traits.forest_penalty;

    // 不能游泳的单位遇到深水 → 不可通行
    if (tt == TerrainType::DeepWater && !traits.can_swim)
        return INFINITY;

    // 全局速度倍率 (不影响寻路决策本身，但需要反映在 g 值中)
    base /= traits.speed_multiplier;

    return base;
}

// ============================================================
// 可视化与演示
// ============================================================
void print_cost_grid(const CostMap& map, bool show_influence = false) {
    std::cout << "\n";
    for (int x = 0; x < map.rows; ++x) {
        for (int y = 0; y < map.cols; ++y) {
            if (!map.walkable_at(x, y)) {
                std::cout << " ###";
            } else if (show_influence && map.influence_at(x, y) > 0.5) {
                std::cout << " Inf";
            } else {
                switch (map.terrain_at(x, y)) {
                    case TerrainType::Road:    std::cout << "  R "; break;
                    case TerrainType::Grass:   std::cout << "  G "; break;
                    case TerrainType::Forest:  std::cout << "  F "; break;
                    case TerrainType::Swamp:   std::cout << "  S "; break;
                    case TerrainType::ShallowWater: std::cout << " ~W "; break;
                    case TerrainType::DeepWater: std::cout << " ~~ "; break;
                    case TerrainType::Mountain: std::cout << " /\\ "; break;
                    case TerrainType::Sand: std::cout << "  . "; break;
                    default: std::cout << " ?? "; break;
                }
            }
        }
        std::cout << "\n";
    }
}

// ============================================================
// Unity 编辑器集成示例 (概念+伪代码)
// ============================================================
void show_unity_integration() {
    std::cout << "\n========================================================\n";
    std::cout << "Unity 编辑器集成 — 绘制地形代价\n";
    std::cout << "========================================================\n\n";

    std::cout << R"(概念代码 (C#):
// TerrainCostPainter.cs — Editor 工具
using UnityEngine;
using UnityEditor;

public class TerrainCostPainter : EditorWindow
{
    private CostMapData costMap;  // ScriptableObject 引用
    private TerrainType paintType = TerrainType.Grass;
    private int brushSize = 1;

    [MenuItem("Tools/Terrain Cost Painter")]
    static void Open() => GetWindow<TerrainCostPainter>();

    void OnEnable() { SceneView.duringSceneGui += OnSceneGUI; }
    void OnDisable() { SceneView.duringSceneGui -= OnSceneGUI; }

    void OnSceneGUI(SceneView view)
    {
        // 1. 获取鼠标在地面上的投影位置
        // 2. 转换为网格坐标
        // 3. 按 brushSize 设置 costMap 中对应格子的 terrain_type
        // 4. 重绘 Scene View
    }

    void OnGUI()
    {
        // 工具面板：选择地形类型、画刷大小
        paintType = (TerrainType)EditorGUILayout.EnumPopup("Terrain", paintType);
        brushSize = EditorGUILayout.IntSlider("Brush Size", brushSize, 1, 10);
        if (GUILayout.Button("Bake Cost Map")) BakeMap();
    }

    void BakeMap()
    {
        // 将作者数据 (terrain_type[]) 导出为寻路引擎可用的 cost 数组
        costMap.Bake();
    }
}

// CostMapData.cs — ScriptableObject
[CreateAssetMenu(menuName = "Navigation/Cost Map Data")]
public class CostMapData : ScriptableObject
{
    public int width, height;
    public int[] terrainTypes;  // 序列化到 .asset 文件

    public void Bake()
    {
        // 将 terrainTypes[] → float[] costs
        // 写入 StreamingAssets/nav_data.bin
    }
}
)";
}

// ============================================================
// 主程序
// ============================================================
int main() {
    constexpr int ROWS = 16, COLS = 24;

    std::cout << "========================================================\n";
    std::cout << "地形感知与移动代价\n";
    std::cout << "网格: " << ROWS << "×" << COLS << "\n";
    std::cout << "========================================================\n\n";

    // 创建高度图（有起伏的地形）
    HeightMap hm(ROWS, COLS);
    for (int x = 0; x < ROWS; ++x) {
        for (int y = 0; y < COLS; ++y) {
            // 模拟一个中间高、四周低的小山丘
            float cx = ROWS / 2.0f, cy = COLS / 2.0f;
            float dx = x - cx, dy = y - cy;
            float dist = std::sqrt(dx * dx + dy * dy);
            hm.set_height(x, y, std::max(0.0f, 10.0f - dist * 1.5f));
        }
    }

    // 创建代价地图
    CostMap map(ROWS, COLS, &hm);

    // 绘制地形
    // ——道路：两条交叉的主路
    for (int i = 0; i < COLS; ++i) map.set_terrain(7, i, TerrainType::Road);
    for (int i = 0; i < ROWS; ++i) map.set_terrain(i, 11, TerrainType::Road);

    // ——河流：一条水平河流
    for (int i = 2; i < 20; ++i) map.set_terrain(4, i, TerrainType::ShallowWater);

    // ——深水区（不可通行）
    for (int i = 5; i < 8; ++i) map.set_terrain(3, i, TerrainType::DeepWater);

    // ——森林区域
    for (int x = 9; x < 14; ++x)
        for (int y = 0; y < 8; ++y)
            map.set_terrain(x, y, TerrainType::Forest);

    // ——沼泽区域
    for (int x = 10; x < 14; ++x)
        for (int y = 14; y < 22; ++y)
            map.set_terrain(x, y, TerrainType::Swamp);

    // ——山地（不可通行）
    for (int x = 0; x < 3; ++x)
        for (int y = 18; y < 24; ++y)
            map.set_terrain(x, y, TerrainType::Mountain);

    // ——沙地
    for (int y = 0; y < 5; ++y) map.set_terrain(0, y, TerrainType::Sand);

    std::cout << "--- 地形布局 (R=道路 G=草地 F=森林 S=沼泽 ~W=浅水 ~~=深水 /\\=山地 .=沙地 ###=不可通行) ---\n";
    print_cost_grid(map);

    // ---- 显示基础代价 ----
    std::cout << "\n--- 各类型基础代价 ---\n";
    std::cout << std::fixed << std::setprecision(1);
    for (int t = 0; t < static_cast<int>(TerrainType::COUNT); ++t) {
        std::cout << "  " << std::setw(12) << terrain_name(static_cast<TerrainType>(t))
                  << ": " << TERRAIN_DB[t].base_cost
                  << " (slope_sens=" << TERRAIN_DB[t].slope_sensitivity << ")\n";
    }

    // ---- 坡度分析 ----
    std::cout << "\n--- 坡度对代价的影响 (从 (7,11) 出发向四周) ---\n";
    int cx = 7, cy = 11;
    std::cout << "  中心点 (" << cx << "," << cy << ") 高度=" << hm.height_at(cx, cy)
              << " 地形=" << terrain_name(map.terrain_at(cx, cy)) << "\n";
    const int DIRS[4][2] = {{1,0}, {-1,0}, {0,1}, {0,-1}};
    const char* DIR_NAMES[4] = {"下", "上", "右", "左"};
    for (int d = 0; d < 4; ++d) {
        int nx = cx + DIRS[d][0];
        int ny = cy + DIRS[d][1];
        if (map.in_bounds(nx, ny)) {
            double cost = map.final_cost(cx, cy, nx, ny);
            double slope = hm.slope_to(cx, cy, nx, ny);
            std::cout << "  向" << DIR_NAMES[d] << " (" << nx << "," << ny << "): "
                      << "height=" << hm.height_at(nx, ny)
                      << " slope=" << std::fixed << std::setprecision(2) << slope
                      << " cost=" << cost << "\n";
        }
    }

    // ---- 影响图演示 ----
    std::cout << "\n--- 影响图: 在 (10,6) 周围施加 '危险区域' 惩罚 (radius=3) ---\n";
    map.apply_radial_influence(10, 6, 3, 5.0);
    std::cout << "  平均影响值: " << map.average_influence() << "\n";
    std::cout << "  (10,6) 最终代价: " << map.final_cost_simple(10, 6) << "\n";
    std::cout << "  (10,8) 最终代价 (距影响中心 2 格): " << map.final_cost_simple(10, 8) << "\n";
    std::cout << "  (10,15) 最终代价 (距影响中心远): " << map.final_cost_simple(10, 15) << "\n";

    // ---- Agent 特定代价 ----
    std::cout << "\n--- Agent 特定代价 ---\n";
    AgentTraits cavalry = {1.0, false, 2.0, INFINITY}; // 骑兵：不能过水，森林双倍惩罚
    AgentTraits infantry = {1.0, false, 1.0, 100.0};   // 步兵：森林正常
    AgentTraits scout = {1.3, true, 0.8, 3.0};         // 侦察兵：速度快，可游泳

    int test_points[][2] = {{10, 3}, {4, 3}, {4, 5}};
    for (auto [tx, ty] : test_points) {
        int nx = tx + 1, ny = ty; // 向下走一格
        std::cout << "  (" << tx << "," << ty << ") → (" << nx << "," << ny << "): "
                  << terrain_name(map.terrain_at(nx, ny)) << "\n";
        std::cout << "    基础: " << map.final_cost(tx, ty, nx, ny) << "\n";
        std::cout << "    骑兵: " << agent_adjusted_cost(map, tx, ty, nx, ny, cavalry) << "\n";
        std::cout << "    步兵: " << agent_adjusted_cost(map, tx, ty, nx, ny, infantry) << "\n";
        std::cout << "    侦察兵: " << agent_adjusted_cost(map, tx, ty, nx, ny, scout) << "\n";
    }

    // ---- Unity 集成 ----
    show_unity_integration();

    std::cout << "\nDone.\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 -Wall -o terrain_costs terrain_costs.cpp
./terrain_costs
```

**预期输出:**
```
========================================================
地形感知与移动代价
网格: 16×24
========================================================

--- 地形布局 ---
  .  .  .  .  .  G  G  G  G  G  G  R  G  G  G  G  G  G  G  G /\\ /\\ /\\ /\\
  G  G  G  G  G  G  G  G  G  G  G  R  G  G  G  G  G  G  G  G /\\ /\\ /\\ /\\
  G  G  G  G  G  G  G  G  G  G  G  R  G  G  G  G  G  G  G  G /\\ /\\ /\\ /\\
  G  G  G  G  G ~W ~W ~W ~W ~W ~W  R ~W ~W ~W ~W ~W ~W ~W ~W /\\ /\\ /\\ /\\
  G  G ~~ ~~ ~~  G  G  G  G  G  G  R  G  G  G  G  G  G  G  G  G  G  G  G
  ...
--- 各类型基础代价 ---
  道路: 0.8
  草地: 1.0
  森林: 2.5
  ...

--- 坡度对代价的影响 ---
  向下: slope=0.xx cost=1.xx
  ...

--- 影响图 ---
  平均影响值: 0.xx
  ...

--- Unity 编辑器集成 ---
...
```

## 3. 练习

### 基础练习
1. **添加新地形类型**：在 `TerrainType` 枚举中加入 `Ice`（冰面），设置其 `base_cost=0.6`、`slope_sensitivity=0.5`。在 demo 地图中加入一小块冰面区域，观察代价变化。
2. **手算坡度代价**：给定高度图 `h[0][0]=0, h[0][1]=3, h[1][0]=1, h[1][1]=5`，手动计算从 `(0,0)` 走到 `(1,1)`（经过 `(0,1)` 或 `(1,0)` 之一）的两条路径的累计代价。验证代码输出是否一致。

### 进阶练习
1. **实现指数衰减影响图**：修改 `apply_radial_influence` 用 `exp(-dist² / (2σ²))`（高斯衰减）替代线性衰减。对比两种衰减在 5 格半径下的效果。
2. **多层影响图**：扩展 `CostMap` 支持多个命名的影响图层（用 `std::unordered_map<std::string, std::vector<double>>`），每个可独立设置和清除。寻路时将所有激活层叠加。
3. **代价值的启发函数适配**：修改 03 中的 A* 启发函数，使其考虑地形的最小代价（`h * min_terrain_cost`），这样在代价差异大的地图上仍保持可容许性。

### 挑战练习（可选）
1. **实现基于斜率的方向性代价**：不只在进入格子时计算坡度代价，而是根据"上坡/下坡/横穿"三个方向给出不同代价。横穿斜坡（垂直于梯度方向）代价应低于直上直下。
2. **动态影响图扩散**：实现一个"影响传播"系统——每个 tick，影响值向邻居扩散并衰减。用于模拟"气味/热量/危险信号"的传播。

## 3.5 参考答案

> [!tip]- 练习 1 参考答案（添加冰面地形）
> 修改三步：枚举、TERRAIN_DB、demo 地图。
>
> **第一步：枚举中添加 Ice 成员**
> ```cpp
> enum class TerrainType : uint8_t {
>     Road       = 0,
>     Grass      = 1,
>     Forest     = 2,
>     Swamp      = 3,
>     ShallowWater = 4,
>     DeepWater  = 5,
>     Mountain   = 6,
>     Sand       = 7,
>     Ice        = 8,  // 新增
>     COUNT
> };
> ```
>
> **第二步：TERRAIN_DB 中追加冰面配置**
> ```cpp
> // 在 Sand 条目之后追加
> const TerrainConfig TERRAIN_DB[] = {
>     { 0.8, true,  0.1  }, // Road
>     { 1.0, true,  0.3  }, // Grass
>     { 2.5, true,  1.0  }, // Forest
>     { 5.0, true,  2.0  }, // Swamp
>     { 4.0, true,  0.5  }, // ShallowWater
>     { INF, false, 0.0  }, // DeepWater
>     { INF, false, 0.0  }, // Mountain
>     { 1.8, true,  0.8  }, // Sand
>     { 0.6, true,  0.5  }, // Ice — 滑行快但坡度敏感度适中
> };
> ```
>
> **第三步：`terrain_name()` 添加分支**
> ```cpp
> case TerrainType::Ice: return "冰面";
> ```
>
> **第四步：`print_cost_grid()` 添加冰面显示字符**
> ```cpp
> case TerrainType::Ice:  std::cout << "  I "; break;
> ```
>
> **第五步：在 main() 中绘制冰面区域**
> ```cpp
> // ——冰面区域（地图左上角）
> for (int x = 1; x < 4; ++x)
>     for (int y = 1; y < 5; ++y)
>         map.set_terrain(x, y, TerrainType::Ice);
> ```
>
> **预期效果：** 冰面区域显示 `I`，代价 0.6——比道路 (0.8) 还快，但坡度敏感度 0.5 意味着若是斜坡地，惩罚会高于道路的 0.1。这反映冰面滑行快但上坡更费力的物理直觉。

> [!tip]- 练习 2 参考答案（手算坡度代价）
> **给定高度图：** `h[0][0]=0, h[0][1]=3, h[1][0]=1, h[1][1]=5`
>
> **路径 A：** `(0,0) → (0,1) → (1,1)`  (先右后下)
>
> - 第一步 `(0,0)→(0,1)`：`slope = |3 - 0| = 3.0`。假设地形为草地 (`sensitivity=0.3`)，上坡 `dh=3>0` → `slope_cost = 3.0 × 0.3 × 1.5 = 1.35`。基础代价 = 1.0。总代价 = `1.0 + 1.35 = 2.35`。
> - 第二步 `(0,1)→(1,1)`：`slope = |5 - 3| = 2.0`。上坡 `dh=2>0` → `slope_cost = 2.0 × 0.3 × 1.5 = 0.9`。总代价 = `1.0 + 0.9 = 1.9`。
> - **累计：** `2.35 + 1.9 = 4.25`
>
> **路径 B：** `(0,0) → (1,0) → (1,1)`  (先下后右)
>
> - 第一步 `(0,0)→(1,0)`：`slope = |1 - 0| = 1.0`。上坡 `dh=1>0` → `slope_cost = 1.0 × 0.3 × 1.5 = 0.45`。总代价 = `1.0 + 0.45 = 1.45`。
> - 第二步 `(1,0)→(1,1)`：`slope = |5 - 1| = 4.0`。上坡 `dh=4>0` → `slope_cost = 4.0 × 0.3 × 1.5 = 1.8`。总代价 = `1.0 + 1.8 = 2.8`。
> - **累计：** `1.45 + 2.8 = 4.25`
>
> **结论：** 两条路径在草地地形下累计代价相等（4.25），因为坡度代价是累加的。但如果第二步的 `(1,1)` 是森林 (`sensitivity=1.0`)：路径 A 第二步 `slope_cost = 2.0 × 1.0 × 1.5 = 3.0` → `1.0 + 3.0 = 4.0`，累计 `2.35 + 4.0 = 6.35`；路径 B 第二步 `slope_cost = 4.0 × 1.0 × 1.5 = 6.0` → `1.0 + 6.0 = 7.0`，累计 `1.45 + 7.0 = 8.45`。此时路径 A 更优——地形敏感度放大了坡度差异。

> [!tip]- 练习 3 参考答案（高斯衰减影响图）
> 将 `apply_radial_influence` 中的线性衰减替换为高斯衰减：
>
> ```cpp
> void apply_radial_influence_gaussian(int cx, int cy, int radius, double strength) {
>     const double sigma = radius / 3.0;  // σ = r/3 使 3σ ≈ radius
>     const double two_sigma_sq = 2.0 * sigma * sigma;
>     for (int y = cy - radius; y <= cy + radius; ++y) {
>         for (int x = cx - radius; x <= cx + radius; ++x) {
>             if (!in_bounds(x, y)) continue;
>             double dx = x - cx, dy = y - cy;
>             double dist_sq = dx * dx + dy * dy;
>             if (std::sqrt(dist_sq) > radius) continue;
>             double falloff = std::exp(-dist_sq / two_sigma_sq); // 高斯核
>             influence_[idx(x, y)] += strength * falloff;
>         }
>     }
> }
> ```
>
> **对比（radius=5, strength=5.0）：**
>
> | 距中心距离 | 线性衰减 (1-d/r) | 高斯衰减 (σ=1.67) |
> |---|---|---|
> | 0 (中心) | 5.0 × 1.0 = 5.0 | 5.0 × 1.0 = 5.0 |
> | 1 格 | 5.0 × 0.8 = 4.0 | 5.0 × 0.835 = 4.18 |
> | 2 格 | 5.0 × 0.6 = 3.0 | 5.0 × 0.487 = 2.44 |
> | 3 格 | 5.0 × 0.4 = 2.0 | 5.0 × 0.200 = 1.00 |
> | 4 格 | 5.0 × 0.2 = 1.0 | 5.0 × 0.057 = 0.29 |
> | 5 格 | 5.0 × 0.0 = 0.0 | 5.0 × 0.011 = 0.06 |
>
> **关键区别：** 线性衰减在边界处截断（突然从 0.2 跳到 0），产生"断崖"；高斯衰减平滑过渡到 0，中心附近惩罚更集中，远处衰减更快。在游戏中，高斯衰减更适合模拟"气味/热量"等物理扩散现象——影响集中在源头附近，不会线性延伸到远处造成不自然的绕行。

> [!tip]- 练习 4 参考答案（多层影响图）
> 扩展 `CostMap` 支持命名图层：
>
> ```cpp
> class CostMap {
> public:
>     // ... 原有成员 ...
>
> private:
>     std::unordered_map<std::string, std::vector<double>> layers_;
>     std::vector<bool> layer_active_;  // 每个图层是否激活
>     std::vector<std::string> layer_names_; // 保持插入顺序
>
> public:
>     // 创建一个命名影响图层
>     void create_layer(const std::string& name) {
>         if (layers_.find(name) != layers_.end()) return; // 已存在
>         layers_[name] = std::vector<double>(rows * cols, 0.0);
>         layer_names_.push_back(name);
>         layer_active_.push_back(true);
>     }
>
>     void set_layer_active(const std::string& name, bool active) {
>         for (size_t i = 0; i < layer_names_.size(); ++i) {
>             if (layer_names_[i] == name) { layer_active_[i] = active; return; }
>         }
>     }
>
>     void set_layer_value(const std::string& name, int x, int y, double v) {
>         auto it = layers_.find(name);
>         if (it != layers_.end()) it->second[idx(x, y)] = v;
>     }
>
>     double layer_value(const std::string& name, int x, int y) const {
>         auto it = layers_.find(name);
>         return (it != layers_.end()) ? it->second.at(idx(x, y)) : 0.0;
>     }
>
>     void clear_layer(const std::string& name) {
>         auto it = layers_.find(name);
>         if (it != layers_.end()) std::fill(it->second.begin(), it->second.end(), 0.0);
>     }
>
>     void clear_all_layers() {
>         for (auto& [name, layer] : layers_) std::fill(layer.begin(), layer.end(), 0.0);
>     }
>
>     void clear_all_layers() {
>         for (auto& [name, layer] : layers_) std::fill(layer.begin(), layer.end(), 0.0);
>     }
>
>     // 获取所有激活层的叠加值（取代原有的 influence_）
>     double combined_influence_at(int x, int y) const {
>         double total = 0.0;
>         for (size_t i = 0; i < layer_names_.size(); ++i) {
>             if (!layer_active_[i]) continue;
>             total += layers_.at(layer_names_[i])[idx(x, y)];
>         }
>         // 限制上限，防止堆叠溢出
>         constexpr double MAX_INFLUENCE = 100.0;
>         return std::clamp(total, -MAX_INFLUENCE, MAX_INFLUENCE);
>     }
> };
> ```
>
> **使用示例：**
> ```cpp
> map.create_layer("enemy_threat");
> map.create_layer("resource_rich");
> map.create_layer("recent_combat");
>
> // 施加敌人威胁（提高代价，AI 绕开）
> map.set_layer_value("enemy_threat", 10, 6, 8.0);
> // 施加资源吸引（降低代价，工人被吸引）
> map.set_layer_value("resource_rich", 5, 12, -3.0);
> // 停用某个图层（不影响寻路）
> map.set_layer_active("recent_combat", false);
> ```
>
> **设计要点：**
> - `layer_active_` 允许临时停用而不丢失数据——战斗中禁用"资源吸引"，战斗结束重新激活
> - `clamp` 防止多个图层叠加到极端值导致路径完全绕行
> - `layer_names_` 保持插入顺序，用于 UI 列表展示
> - 可进一步扩展为每个图层带独立衰减函数（线性/高斯/自定义）

> [!tip]- 练习 5 参考答案（启发函数适配地形代价）
> A* 的启发函数必须保持**可容许性**（never overestimate）。当地形代价 > 1.0 时，用曼哈顿距离 × 1.0 会低估，A* 退化为 Dijkstra。修正方法：
>
> ```cpp
> double heuristic_with_terrain(int x1, int y1, int x2, int y2, double min_cost) {
>     // octile 距离（8 方向启发）——比曼哈顿更精确
>     int dx = std::abs(x1 - x2);
>     int dy = std::abs(y1 - y2);
>     double straight = std::min(dx, dy);
>     double diagonal = std::abs(dx - dy);
>     // 对角线步长 ≈ sqrt(2)
>     double octile = straight * 1.41421356 + diagonal * 1.0;
>     return octile * min_cost;
> }
>
> // 在 A* 调用处：
> // min_cost = CostMap 中全局最小可通行代价（例如 0.6 for Ice）
> double h = heuristic_with_terrain(current.x, current.y, goal.x, goal.y, 0.6);
> ```
>
> **进阶：不同区域使用不同 min_cost**
>
> 如果地图上最小代价的格子远在别处（如冰面在角落但 A* 搜索区域在森林里），用全局 `min_cost = 0.6` 会严重低估→退化。更好的做法是用**当前搜索区域的局部 min_cost**，或直接用目标格子的实际 `base_cost` 做启发（虽然可能违反可容许性，但在实践中常可获得 10-50x 加速且路径质量可接受）：
>
> ```cpp
> // 权衡：用目标格子的实际代价做启发——技术上不可容许但实践中常用
> double h = octile_distance * map.final_cost_simple(goal.x, goal.y);
> ```
>
> **关键公式：** `h = heuristic_distance × min_possible_step_cost`，其中 `min_possible_step_cost` 越小（等于 0.6 而非 0.8），搜索越像 Dijkstra；越大（接近实际均值），搜索越快但可能非最优。

> [!tip]- 练习 6 参考答案（方向性坡度代价，可选）
> 将坡度代价按方向分解为上坡、下坡、横穿：
>
> ```cpp
> // 计算方向性坡度代价
> double directional_slope_cost(int x, int y, int nx, int ny) const {
>     if (!heightmap_) return 0.0;
>
>     float h_cur = heightmap_->height_at(x, y);
>     float h_next = heightmap_->height_at(nx, ny);
>     double dh = h_next - h_cur;
>     double slope = std::abs(dh);
>
>     // 梯度方向的法向量投影 —— 判断横穿程度
>     // 简化：dx/dy 在 0..1 之间，对角线 = 横穿（较省力），直线 = 正向
>     int dx = std::abs(nx - x);
>     int dy = std::abs(ny - y);
>     double move_magnitude = std::sqrt(dx * dx + dy * dy);
>     if (move_magnitude < 0.001) return 0.0;
>
>     // 沿梯度方向的投影（0=横穿, 1=直上直下）
>     double grad_dot_move = (dx / move_magnitude) * (dh == 0 ? 0 : (dh > 0 ? 1 : -1));
>     double forwardness = std::abs(grad_dot_move);
>
>     // 横穿因子：forwardness=1 时全惩罚, forwardness=0 时大幅减少
>     constexpr double TRAVERSE_FACTOR = 0.3; // 横穿只承担 30% 惩罚
>     double effective_factor = forwardness + TRAVERSE_FACTOR * (1.0 - forwardness);
>
>     double sensitivity = TERRAIN_DB[static_cast<int>(terrain_type_[idx(nx, ny)])].slope_sensitivity;
>     double base = slope * sensitivity;
>     if (dh > 0) base *= 1.5; // 上坡加成
>
>     return base * effective_factor;
> }
> ```
>
> **核心思路：** 计算移动方向与坡度梯度方向的夹角。直上直下（`forwardness≈1`）全惩罚；横穿（`forwardness≈0`）只承担 30%。这让 AI 优先选择"贴着斜坡走"而非"硬爬山"。使用 `grad_dot_move` 的绝对值是因为无论上坡还是下坡，横穿都省力。

> [!tip]- 练习 7 参考答案（动态影响图扩散，可选）
> 每个 tick 让影响值向邻居扩散并衰减：
>
> ```cpp
> class InfluenceDiffusion {
>     std::vector<double> buffer_;   // 读缓冲区
>     std::vector<double> value_;    // 写缓冲区（当前值）
>     int rows_, cols_;
>
> public:
>     InfluenceDiffusion(int r, int c) : rows_(r), cols_(c),
>         buffer_(r * c, 0.0), value_(r * c, 0.0) {}
>
>     double& at(int x, int y) { return value_[idx(x, y)]; }
>     size_t idx(int x, int y) const { return y * cols_ + x; }
>
>     // 每个 tick 调用一次：扩散 + 衰减
>     void tick(double decay_factor = 0.95, double diffusion_rate = 0.2) {
>         // 交换双缓冲
>         std::swap(buffer_, value_);
>
>         const int DIRS[4][2] = {{1,0}, {-1,0}, {0,1}, {0,-1}};
>         for (int y = 0; y < cols_; ++y) {
>             for (int x = 0; x < rows_; ++x) {
>                 double self = buffer_[idx(x, y)];
>                 double neighbor_sum = 0.0;
>                 int n_count = 0;
>                 for (int d = 0; d < 4; ++d) {
>                     int nx = x + DIRS[d][0], ny = y + DIRS[d][1];
>                     if (nx >= 0 && nx < rows_ && ny >= 0 && ny < cols_) {
>                         neighbor_sum += buffer_[idx(nx, ny)];
>                         ++n_count;
>                     }
>                 }
>                 double neighbor_avg = n_count > 0 ? neighbor_sum / n_count : 0.0;
>                 // 向邻居均值靠拢（扩散）+ 自身衰减
>                 value_[idx(x, y)] = (self * (1.0 - diffusion_rate)
>                                    + neighbor_avg * diffusion_rate) * decay_factor;
>             }
>         }
>     }
> };
> ```
>
> **使用示例（集成到 CostMap）：**
> ```cpp
> // 每帧调用（或每 N 帧）
> diffusion.tick(0.98, 0.15);  // decay_factor=0.98 缓慢衰减, diffusion_rate=0.15
>
> // 读取扩散后的值叠加到寻路代价上
> double influence = diffusion.at(x, y);
> double final_cost = map.final_cost(x, y, nx, ny) + influence;
> ```
>
> **参数指南：**
> - `decay_factor`：0.95→快速消失（几秒），0.995→持续很久（几十秒）。选值取决于游戏节奏。
> - `diffusion_rate`：0.1→慢扩散，0.5→快扩散。过高会导致"震荡"（值来回跳）。
> - 双缓冲是关键——扩散属于"全网格卷积"类操作，读写必须分开。
> - 可扩展为**异步扩散**：不每帧全量更新，而是分帧只更新部分格子（如隔行扫描），降低 CPU 开销。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- **《AI Game Programming Wisdom》系列**："Terrain Reasoning for Tactical Decisions" (Vol.2) — 讲地形代价如何影响 AI 战术决策，不仅限于寻路。
- **Influence Maps (Alex J. Champandard)**：经典文章 "The Core Mechanics of Influence Mapping"，详细讲解多层影响图的博弈论基础。
- **Amit Patel's Game Programming**："Hexagonal Grids" 中有一节关于 hexagonal terrain costs 的特殊处理。
- **Unreal Engine Navigation System**：`UNavArea` 和 `UNavAreaMeta` 类 — Unreal 的地形代价模型，每个 NavArea 可以指定 enter cost 和 traversal cost，并且支持基于 Agent 的过滤（`CanBeNavArea`）。
- **Unity NavMesh Areas**：`NavMesh.GetAreaCost()` / `NavMesh.SetAreaCost()` — Unity 内置的代价系统，NavMesh Surface 上可画不同的 area type 并设置各自代价。

## 常见陷阱

1. **代价为 0 的格子**：如果 `base_cost = 0`，寻路算法会在该格子上无限循环（零代价移动没有任何惩罚）。必须强制 `cost ≥ ε > 0`（如 0.001）。我们的 `final_cost` 用了 `max(cost, 0.1)`。

2. **启发函数不考虑地形代价**：如果在 A* 中仍用简单曼哈顿距离（假设每步代价 = 1），但实际地形代价是 5.0 — 启发函数严重低估 → A* 退化为 Dijkstra。**对策**：`h = heuristic_distance * min_possible_cost`。

3. **坡度惩罚的双向不对称**：如果 A→B 的代价 ≠ B→A 的代价（如上坡 vs 下坡），A* 需要**有向图**支持。大多数寻路实现是无向的——注意选择。

4. **影响图堆叠溢出**：多个影响源同时施加在同一个格子上，可能导致代价极大，路径完全绕行。**对策**：给影响图设上限 `clamp(influence, -max_influence, +max_influence)`。

5. **浮点比较**：`if (cost == INFINITY)` 不可靠。用 `std::isinf(cost)` 或 `cost >= LARGE_VALUE / 2`。
