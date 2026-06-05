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
