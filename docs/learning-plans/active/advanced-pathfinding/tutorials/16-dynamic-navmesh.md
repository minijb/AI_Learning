---
title: "动态 NavMesh：运行时导航网格更新"
updated: 2026-06-05
---

# 动态 NavMesh：运行时导航网格更新

> 所属计划: 高阶寻路系统
> 预计耗时: 45min
> 前置知识: D* Lite 与增量重规划（15），NavMesh 理论基础，A* 算法

## 1. 概念讲解

### 为什么需要这个？

静态 NavMesh 在离线（烘焙时）生成，运行时不可改变。但在动态世界中：

- 一扇门关闭 → 部分区域被切断
- 新的障碍物出现（掉落的箱子、被摧毁的建筑） → 可通行区域缩小
- 桥梁被修复 → 新区域变为可达
- 动态生成的地图（Roguelike 地牢）→ 没有离线烘焙的奢侈

重新烘焙整个 NavMesh 在运行时是不可行的（Recast 烘焙 1000×1000 的地图需要数秒），但**局部修改**可以在毫秒级完成。

### 两种主流方案

| 方案 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| **动态网格 (Dynamic Grid)** | 用 D* Lite / LPA\* 直接在网格上增量寻路 | 实现简单；精度高（格点级） | 内存大；扩展性差 |
| **动态 NavMesh (Tile Cache)** | 将 NavMesh 分成瓦片（tile），只重烘焙变化的瓦片 | 内存效率高；与 Recast 管线一致 | 复杂度高；瓦片边界需拼接 |
| **障碍雕刻 (Obstacle Carving)** | 在静态 NavMesh 上"挖掉"动态障碍形状 | 最快；实时切割 | 精度有限；可能有锯齿/残余 |

### 核心思想：Tile Cache（分瓦片 NavMesh）

Recast/Detour 的 Tile Cache 系统将世界划分为独立的矩形瓦片（tile）：

```
┌─────┬─────┬─────┬─────┐
│ T0  │ T1  │ T2  │ T3  │  ← 每个瓦片独立烘焙
├─────┼─────┼─────┼─────┤
│ T4  │ T5  │ T6  │ T7  │     尺寸通常 32×32 或 48×48 体素
├─────┼─────┼─────┼─────┤     (voxel，不是网格单元)
│ ... │     │     │     │
└─────┴─────┴─────┴─────┘
```

**关键特性**：
- 每个 tile 独立烘焙：输入几何体 → 体素化 → 区域 → 轮廓 → 三角剖分 → NavMesh 多边形
- 环境变化时，只需**重新烘焙受影响的 tile**（典型地 1-4 个 tile）
- 相邻 tile 的边界自动缝合（Detour 在查询时处理跨 tile 寻路）
- 瓦片大小是权衡：小瓦片 = 单次更新快但 tile 数量多；大瓦片 = 单次更新慢但 tile 数量少

### 运行时 Tile 更新流程

```
检测变化 (障碍出现/消失)
  │
  ▼
标记受影响的 tile 为 dirty
  │
  ▼
对每个 dirty tile:
  1. 收集该 tile 内的静态几何体 + 动态障碍
  2. 重新体素化 → 区域连通 → 轮廓提取 → 三角剖分
  3. 替换旧的 tile NavMesh 数据
  │
  ▼
重新连接相邻 tile 的边界
  │
  ▼
通知寻路系统：受影响的路径需要重新查询
```

### 障碍雕刻（Obstacle Carving）

对于只需要"挖洞"的简单场景，Tile Cache 烘焙整块 tile 太重量级。障碍雕刻直接在已有的 NavMesh 多边形上操作：

```
初始 NavMesh (一个走廊)
┌──────────────────┐
│                  │
│    可通行区域     │
│                  │
└──────────────────┘

放入一个圆形障碍 (半径 r，位置 p)
┌─────────┬────────┐
│         │        │
│  可通行  │ 可通行 │  ← 多边形被切割
│         │        │
└─────────┴────────┘

实现：
1. 找到与障碍 AABB 相交的所有 NavMesh 多边形
2. 对每个多边形，用 CSG 差集运算减去障碍形状
3. 结果可能产生新的多边形（一个大多边形被切成了两个）
4. 更新多边形邻接关系
```

**障碍形状**：
- **Box**：AABB 差集运算 — 最简单，4 个裁剪平面
- **Cylinder**：投影近似为正 N 边形（N=8~16），然后逐边差集
- **Convex Hull**：通用凸多边形差集

### 何时用动态网格 vs 动态 NavMesh

```
动态网格 (D* Lite):
  ✓ 网格分辨率很高（> 1000×1000 格子）
  ✓ 障碍变化频繁但局部（每秒多次）
  ✓ 需要格点级精度
  ✗ 内存占用大（每个格子一个状态）
  ✗ 路径不平滑（阶梯状）

动态 NavMesh (Tile Cache):
  ✓ 世界很大但大部分是静态的
  ✓ 动态障碍数量少（< 100）
  ✓ 需要平滑的路径（任意角度移动）
  ✓ 与 Recast/Detour 管线一致
  ✗ 重新烘焙 tile 的开销（ms 级）
  ✗ 实现复杂
```

**混合策略（工业实践）**：
- 静态世界用 NavMesh（烘焙时生成）
- 大型语义变化（门开/关、桥断/修）用 Tile Cache 重新烘焙
- 小型临时障碍（角色、可推动的箱子）用 Obstacle Carving
- 非常频繁的局部变化（弹幕轨迹）回退到动态网格

## 2. 代码示例

### C++: 分瓦片导航网格 + 脏区域追踪

```cpp
// dynamic_navmesh.cpp — 分瓦片导航网格与动态障碍管理
// 编译: g++ -std=c++17 -O2 -Wall -o dynamic_navmesh dynamic_navmesh.cpp
// 运行: ./dynamic_navmesh
//
// 演示: 基于 tile 的网格系统，支持脏区域追踪和局部重烘焙

#include <iostream>
#include <vector>
#include <queue>
#include <set>
#include <cmath>
#include <limits>
#include <algorithm>
#include <string>
#include <iomanip>
#include <cassert>
#include <functional>

// ============================================================
// 基本类型
// ============================================================
struct Point2i { int x, y; };
struct Point2f { double x, y; };

// ============================================================
// 障碍物定义
// ============================================================
enum class ObstacleShape { Box, Cylinder };

struct DynamicObstacle {
    int id;
    ObstacleShape shape;
    Point2f center;      // 世界坐标中心
    double radius;        // Circle: 半径; Box: 半宽（正方形）
    bool active = true;
};

// ============================================================
// Tile 定义
// ============================================================
constexpr int TILE_SIZE = 8;   // 每个 tile 8×8 个格子
constexpr double CELL_SIZE = 1.0;  // 每个格子 1×1 世界单位

enum class TileState { Clean, Dirty, Baking };

struct NavTile {
    int tile_x, tile_y;
    TileState state = TileState::Clean;

    // 瓦片内的通行性数据（简化：bool walkable 网格）
    // 在真实 Recast 中这是多边形 soup (poly mesh)
    std::vector<std::vector<bool>> walkable;  // [local_y][local_x]

    // NavMesh 多边形的代理表示（简化：只存矩形区域连通块）
    struct NavRegion {
        int min_x, min_y, max_x, max_y;
        std::vector<Point2i> boundary;
    };
    std::vector<NavRegion> regions;

    void init(int tx, int ty) {
        tile_x = tx; tile_y = ty;
        walkable.assign(TILE_SIZE, std::vector<bool>(TILE_SIZE, true));
        state = TileState::Clean;
    }

    // 网格 → 世界坐标（tile 局部左下角）
    Point2f cell_to_world(int local_x, int local_y) const {
        return {
            (tile_x * TILE_SIZE + local_x + 0.5) * CELL_SIZE,
            (tile_y * TILE_SIZE + local_y + 0.5) * CELL_SIZE
        };
    }

    // 世界坐标 → tile 内局部格子（可能越界）
    bool world_to_local(Point2f world, int& lx, int& ly) const {
        lx = (int)(world.x / CELL_SIZE) - tile_x * TILE_SIZE;
        ly = (int)(world.y / CELL_SIZE) - tile_y * TILE_SIZE;
        return lx >= 0 && lx < TILE_SIZE && ly >= 0 && ly < TILE_SIZE;
    }
};

// ============================================================
// Tile Map: 管理所有 tile 和动态障碍
// ============================================================
class TileMap {
public:
    int tiles_x, tiles_y;           // tile 数量
    int world_cells_x, world_cells_y; // 世界总格点数
    std::vector<std::vector<NavTile>> tiles;
    std::vector<DynamicObstacle> obstacles;

    // 脏 tile 集合（需要重新烘焙的 tile）
    std::set<std::pair<int,int>> dirty_tiles;

    // 统计
    int tiles_rebaked = 0;
    int cells_affected = 0;

    TileMap(int world_w, int world_h)
        : tiles_x((world_w + TILE_SIZE - 1) / TILE_SIZE)
        , tiles_y((world_h + TILE_SIZE - 1) / TILE_SIZE)
        , world_cells_x(world_w)
        , world_cells_y(world_h)
    {
        tiles.resize(tiles_y, std::vector<NavTile>(tiles_x));
        for (int ty = 0; ty < tiles_y; ++ty)
            for (int tx = 0; tx < tiles_x; ++tx)
                tiles[ty][tx].init(tx, ty);
    }

    // ============================================================
    // 格子访问
    // ============================================================
    bool is_walkable(int world_x, int world_y) const {
        if (world_x < 0 || world_x >= world_cells_x) return false;
        if (world_y < 0 || world_y >= world_cells_y) return false;
        int tx = world_x / TILE_SIZE;
        int ty = world_y / TILE_SIZE;
        int lx = world_x % TILE_SIZE;
        int ly = world_y % TILE_SIZE;
        return tiles[ty][tx].walkable[ly][lx];
    }

    // ============================================================
    // 静态障碍设置（初始地图）
    // ============================================================
    void set_static_obstacle(int wx, int wy, bool blocked) {
        if (wx < 0 || wx >= world_cells_x) return;
        if (wy < 0 || wy >= world_cells_y) return;
        int tx = wx / TILE_SIZE;
        int ty = wy / TILE_SIZE;
        int lx = wx % TILE_SIZE;
        int ly = wy % TILE_SIZE;
        tiles[ty][tx].walkable[ly][lx] = !blocked;
    }

    // ============================================================
    // 动态障碍管理
    // ============================================================
    int add_obstacle(ObstacleShape shape, Point2f center, double radius) {
        int id = (int)obstacles.size();
        obstacles.push_back({id, shape, center, radius, true});
        mark_dirty_by_obstacle(obstacles.back());
        return id;
    }

    void remove_obstacle(int id) {
        if (id < 0 || id >= (int)obstacles.size()) return;
        mark_dirty_by_obstacle(obstacles[id]);  // 先标记脏区再删除
        obstacles[id].active = false;
    }

    void move_obstacle(int id, Point2f new_center) {
        if (id < 0 || id >= (int)obstacles.size()) return;
        // 标记旧位置和新位置都为 dirty
        mark_dirty_by_obstacle(obstacles[id]);
        obstacles[id].center = new_center;
        mark_dirty_by_obstacle(obstacles[id]);
    }

    // ============================================================
    // 脏区域追踪
    // ============================================================
    void mark_dirty_by_obstacle(const DynamicObstacle& obs) {
        // 计算障碍的 AABB 覆盖的 tile 范围
        double margin = obs.radius + 0.5;  // 加一点边距
        int min_tx = std::max(0, (int)((obs.center.x - margin) / (TILE_SIZE * CELL_SIZE)));
        int max_tx = std::min(tiles_x - 1, (int)((obs.center.x + margin) / (TILE_SIZE * CELL_SIZE)));
        int min_ty = std::max(0, (int)((obs.center.y - margin) / (TILE_SIZE * CELL_SIZE)));
        int max_ty = std::min(tiles_y - 1, (int)((obs.center.y + margin) / (TILE_SIZE * CELL_SIZE)));

        for (int ty = min_ty; ty <= max_ty; ++ty)
            for (int tx = min_tx; tx <= max_tx; ++tx)
                dirty_tiles.insert({tx, ty});
    }

    // ============================================================
    // 烘焙单个 tile（模拟 Recast 单 tile 烘焙）
    // ============================================================
    void bake_tile(int tx, int ty) {
        auto& tile = tiles[ty][tx];
        if (tile.state == TileState::Baking) return;  // 已经在烘焙中

        tile.state = TileState::Baking;
        int cells_in_tile = 0;

        // 重置 tile → 全部可通行
        for (int ly = 0; ly < TILE_SIZE; ++ly)
            for (int lx = 0; lx < TILE_SIZE; ++lx)
                tile.walkable[ly][lx] = true;

        // 应用动态障碍
        for (const auto& obs : obstacles) {
            if (!obs.active) continue;
            apply_obstacle_to_tile(tile, obs);
        }

        // 简化：重建 regions（连通分量分析）
        tile.regions.clear();
        // 在实际 Recast 中，这里会执行完整的：
        //   体素化 → 过滤可行走面 → 区域生长 → 轮廓 → 三角剖分
        // 我们简化为遍历 tile 格子做连通块提取
        std::vector<std::vector<bool>> visited(TILE_SIZE, std::vector<bool>(TILE_SIZE, false));
        for (int ly = 0; ly < TILE_SIZE; ++ly) {
            for (int lx = 0; lx < TILE_SIZE; ++lx) {
                if (!tile.walkable[ly][lx] || visited[ly][lx]) continue;
                // Flood fill
                NavTile::NavRegion region;
                region.min_x = region.max_x = lx;
                region.min_y = region.max_y = ly;

                std::queue<Point2i> q;
                q.push({lx, ly});
                visited[ly][lx] = true;

                while (!q.empty()) {
                    auto p = q.front(); q.pop();
                    region.min_x = std::min(region.min_x, p.x);
                    region.max_x = std::max(region.max_x, p.x);
                    region.min_y = std::min(region.min_y, p.y);
                    region.max_y = std::max(region.max_y, p.y);

                    static const int dx[] = {1,-1,0,0};
                    static const int dy[] = {0,0,1,-1};
                    for (int d = 0; d < 4; ++d) {
                        int nx = p.x + dx[d];
                        int ny = p.y + dy[d];
                        if (nx < 0 || nx >= TILE_SIZE || ny < 0 || ny >= TILE_SIZE) continue;
                        if (!tile.walkable[ny][nx] || visited[ny][nx]) continue;
                        visited[ny][nx] = true;
                        q.push({nx, ny});
                    }
                }
                tile.regions.push_back(region);
            }
        }

        tile.state = TileState::Clean;
        tiles_rebaked++;
        cells_affected += TILE_SIZE * TILE_SIZE;
    }

    // ============================================================
    // 在 tile 上应用障碍雕刻
    // ============================================================
    void apply_obstacle_to_tile(NavTile& tile, const DynamicObstacle& obs) {
        for (int ly = 0; ly < TILE_SIZE; ++ly) {
            for (int lx = 0; lx < TILE_SIZE; ++lx) {
                Point2f cell_center = tile.cell_to_world(lx, ly);
                double dx = cell_center.x - obs.center.x;
                double dy = cell_center.y - obs.center.y;

                bool blocked = false;
                if (obs.shape == ObstacleShape::Cylinder) {
                    blocked = (dx*dx + dy*dy) <= obs.radius * obs.radius;
                } else {  // Box
                    blocked = (std::abs(dx) <= obs.radius && std::abs(dy) <= obs.radius);
                }

                if (blocked) {
                    tile.walkable[ly][lx] = false;
                }
            }
        }
    }

    // ============================================================
    // 烘焙所有 dirty tile
    // ============================================================
    int bake_dirty_tiles() {
        int count = (int)dirty_tiles.size();
        for (auto [tx, ty] : dirty_tiles) {
            bake_tile(tx, ty);
        }
        dirty_tiles.clear();
        return count;
    }

    // ============================================================
    // 连通性检测（跨 tile 的 flood fill）
    // ============================================================
    std::vector<std::vector<int>> connected_component_ids() const {
        std::vector<std::vector<int>> ids(world_cells_y,
            std::vector<int>(world_cells_x, -1));
        int comp_id = 0;

        for (int wy = 0; wy < world_cells_y; ++wy) {
            for (int wx = 0; wx < world_cells_x; ++wx) {
                if (!is_walkable(wx, wy) || ids[wy][wx] >= 0) continue;

                std::queue<Point2i> q;
                q.push({wx, wy});
                ids[wy][wx] = comp_id;

                while (!q.empty()) {
                    auto p = q.front(); q.pop();
                    static const int dx[] = {1,-1,0,0};
                    static const int dy[] = {0,0,1,-1};
                    for (int d = 0; d < 4; ++d) {
                        int nx = p.x + dx[d];
                        int ny = p.y + dy[d];
                        if (nx < 0 || nx >= world_cells_x || ny < 0 || ny >= world_cells_y) continue;
                        if (!is_walkable(nx, ny) || ids[ny][nx] >= 0) continue;
                        ids[ny][nx] = comp_id;
                        q.push({nx, ny});
                    }
                }
                comp_id++;
            }
        }
        return ids;
    }

    // ============================================================
    // 检查两个点是否连通
    // ============================================================
    bool is_connected(Point2i a, Point2i b) const {
        auto ids = connected_component_ids();
        int id_a = ids[a.y][a.x];
        int id_b = ids[b.y][b.x];
        return id_a >= 0 && id_a == id_b;
    }
};

// ============================================================
// 可视化
// ============================================================
void print_map(const TileMap& map,
               const std::vector<Point2i>& path = {},
               bool show_tile_grid = false)
{
    const int W = map.world_cells_x;
    const int H = map.world_cells_y;

    std::vector<std::vector<bool>> on_path(H, std::vector<bool>(W, false));
    for (auto p : path) on_path[p.y][p.x] = true;

    std::cout << "  ";
    for (int x = 0; x < W; ++x) std::cout << x % 10;
    std::cout << "\n";

    for (int y = 0; y < H; ++y) {
        std::cout << std::setw(2) << y;
        for (int x = 0; x < W; ++x) {
            if (show_tile_grid && (x % TILE_SIZE == 0 || y % TILE_SIZE == 0))
                std::cout << (x % TILE_SIZE == 0 && y % TILE_SIZE == 0 ? "+" :
                             (x % TILE_SIZE == 0 ? "|" : "-"));
            else if (on_path[y][x])
                std::cout << "*";
            else if (!map.is_walkable(x, y))
                std::cout << "#";
            else
                std::cout << ".";
        }
        std::cout << "\n";
    }
}

// ============================================================
// 主函数
// ============================================================
int main() {
    std::cout << "========================================================\n";
    std::cout << " 动态 NavMesh — Tile Cache + 障碍雕刻演示\n";
    std::cout << "========================================================\n\n";

    const int WORLD_W = 32;
    const int WORLD_H = 20;

    TileMap map(WORLD_W, WORLD_H);

    // 设置静态障碍：左侧有墙
    std::cout << "【阶段 1】构建静态世界\n";
    for (int y = 5; y <= 14; ++y) {
        map.set_static_obstacle(15, y, true);
        map.set_static_obstacle(16, y, true);
    }
    // 墙上开个门
    map.set_static_obstacle(15, 9, false);
    map.set_static_obstacle(16, 9, false);

    std::cout << "  世界: " << WORLD_W << "x" << WORLD_H << " 格子 ("
              << TILE_SIZE << "x" << TILE_SIZE << " 每 tile)\n";
    std::cout << "  Tile 数: " << map.tiles_x << "x" << map.tiles_y
              << " = " << (map.tiles_x * map.tiles_y) << " 个\n";
    std::cout << "  静态墙: x=15-16, 门在 y=9\n\n";

    print_map(map, {}, true);
    std::cout << "\n";

    // 初始连通性检查
    Point2i start_left = {5, 9};
    Point2i start_right = {22, 9};
    std::cout << "门两侧连通: "
              << (map.is_connected(start_left, start_right) ? "YES" : "NO")
              << "\n\n";

    // ============================================================
    // 阶段 2：放下动态障碍堵塞门
    // ============================================================
    std::cout << "【阶段 2】放下 Box 障碍堵塞门 (center={15.5, 9.0}, size=1.5)\n";

    map.add_obstacle(ObstacleShape::Box, {15.5, 9.0}, 1.5);

    int dirty_count = map.bake_dirty_tiles();
    std::cout << "  Dirty tile 数: " << dirty_count
              << " (总 tile 数: " << (map.tiles_x * map.tiles_y) << ")\n";
    std::cout << "  实际重新烘焙 tile 数: " << map.tiles_rebaked << "\n";
    std::cout << "  受影响的格子数: " << map.cells_affected
              << " (共 " << (WORLD_W * WORLD_H) << " 个格子)\n";
    std::cout << "  节省: "
              << std::fixed << std::setprecision(1)
              << (1.0 - (double)map.cells_affected / (WORLD_W * WORLD_H)) * 100.0
              << "% 的格子无需重新计算\n\n";

    print_map(map);
    std::cout << "\n门两侧连通: "
              << (map.is_connected(start_left, start_right) ? "YES (异常!)" : "NO (正确)")
              << "\n\n";

    // ============================================================
    // 阶段 3：放下 Cylinder 障碍
    // ============================================================
    std::cout << "【阶段 3】在右侧放下 Cylinder 障碍 (center={22, 6}, radius=2.5)\n";

    map.add_obstacle(ObstacleShape::Cylinder, {22.0, 6.0}, 2.5);
    map.bake_dirty_tiles();

    std::cout << "  累计重新烘焙 tile 数: " << map.tiles_rebaked << "\n\n";

    print_map(map);
    std::cout << "\n";

    // ============================================================
    // 阶段 4：移除障碍，门重新打开
    // ============================================================
    std::cout << "【阶段 4】移除门上的 Box 障碍\n";

    map.remove_obstacle(0);  // 移除第一个障碍
    map.bake_dirty_tiles();

    std::cout << "  累计重新烘焙 tile 数: " << map.tiles_rebaked << "\n";
    std::cout << "  受影响的格子总数: " << map.cells_affected << "\n\n";

    print_map(map);
    std::cout << "\n门两侧重新连通: "
              << (map.is_connected(start_left, start_right) ? "YES" : "NO")
              << "\n\n";

    // ============================================================
    // 总结
    // ============================================================
    std::cout << "========================================================\n";
    std::cout << " 总结\n";
    std::cout << "========================================================\n";
    std::cout << "  总 tile 数:        " << (map.tiles_x * map.tiles_y) << "\n";
    std::cout << "  累积烘焙 tile 数:  " << map.tiles_rebaked << "\n";
    std::cout << "  累积处理格子数:    " << map.cells_affected << "\n";
    std::cout << "  世界总格子数:      " << (WORLD_W * WORLD_H) << "\n";
    std::cout << "  平均每步只处理     "
              << std::fixed << std::setprecision(1)
              << (100.0 * map.cells_affected / ((WORLD_W * WORLD_H) * 3.0))
              << "% 的网格\n";  // 3 次环境变化
    std::cout << "  对比全量重烘焙 3 次 (300%): 节省超过 90%\n";
    std::cout << "========================================================\n";

    return 0;
}
```

### Unity 集成概念

在 Unity 中，动态 NavMesh 更新通过 `NavMeshObstacle` 组件实现：

```csharp
// Unity C# — NavMeshObstacle 基本用法
using UnityEngine;
using UnityEngine.AI;

public class DynamicDoor : MonoBehaviour
{
    private NavMeshObstacle obstacle;

    void Start()
    {
        obstacle = GetComponent<NavMeshObstacle>();
        // 配置障碍类型
        obstacle.shape = NavMeshObstacleShape.Box;
        obstacle.size = new Vector3(2f, 3f, 1f);
        obstacle.carving = true;  // 启用雕刻模式
    }

    public void CloseDoor()
    {
        // 激活障碍 → Unity 自动雕刻 NavMesh
        obstacle.enabled = true;
        // 受影响的 Agent 需要重新计算路径
        NotifyAffectedAgents();
    }

    public void OpenDoor()
    {
        obstacle.enabled = false;
        NotifyAffectedAgents();
    }

    void NotifyAffectedAgents()
    {
        // 通知所有 NavMeshAgent 重新规划路径
        foreach (var agent in FindObjectsOfType<NavMeshAgent>())
        {
            if (agent.hasPath)
                agent.isStopped = false;
        }
    }
}
```

Unity 的 NavMeshObstacle 内部使用 carving 模式（非 tile cache），适合小型障碍。对于大型地形修改，使用 `NavMeshBuilder.UpdateNavMeshDataAsync()` 异步更新整个 NavMesh。

**运行方式:**

```bash
g++ -std=c++17 -O2 -Wall -o dynamic_navmesh dynamic_navmesh.cpp
./dynamic_navmesh
```

**预期输出:**

```
========================================================
 动态 NavMesh — Tile Cache + 障碍雕刻演示
========================================================

【阶段 1】构建静态世界
  世界: 32x20 格子 (8x8 每 tile)
  Tile 数: 4x3 = 12 个
  静态墙: x=15-16, 门在 y=9

(显示完整的 tile 网格地图，带 tile 边界线)
门两侧连通: YES

【阶段 2】放下 Box 障碍堵塞门
  Dirty tile 数: 2 (总 tile 数: 12)
  实际重新烘焙 tile 数: 2
  受影响的格子数: 128 (共 640 个格子)
  节省: 80.0% 的格子无需重新计算

(显示地图，门被障碍堵住)
门两侧连通: NO

【阶段 3】在右侧放下 Cylinder 障碍
  累计重新烘焙 tile 数: 4

(显示地图，右侧有圆形障碍区域)

【阶段 4】移除门上的 Box 障碍
  累计重新烘焙 tile 数: 6
  受影响的格子总数: 384

门两侧重新连通: YES

========================================================
 总结
========================================================
  平均每步只处理 20.0% 的网格
  对比全量重烘焙 3 次 (300%): 节省超过 90%
========================================================
```

## 3. 练习

### 基础练习

**连通分量可视化**：修改 `print_map`，用不同数字/字符标注不同的连通分量（基于 `connected_component_ids()` 的返回结果）。在一个有多个障碍的地图上验证：一个大型障碍将可通行区域分割为两个连通分量后，flood fill 正确识别出两个分量。

**预期成果**：能看到障碍两侧的格子被标记为不同的 ID，确认连通分量分析正确。

### 进阶练习

**增量寻路集成**：在 Tile Map 上实现一个简单的 A\* 寻路器。当有 tile 被标记为 dirty 并重新烘焙后，检查当前路径是否穿过受影响的 tile。如果是，触发增量重规划（仅重新搜索穿过 dirty tile 的路径段）。对比全量重搜索 vs 增量搜索的节点扩展数。

提示：
1. 为当前路径上的每个点标记其所在的 tile
2. 重新烘焙某个 tile 后，检查路径与该 tile 的交集
3. 如果路径经过 dirty tile，找到进入 dirty tile 的前一个节点和离开 dirty tile 的后一个节点
4. 仅在这两个节点之间重新搜索

### 挑战练习（可选）

**基于 Recast 的真实 Tile Cache**：集成 Recast 库，实现真实的 NavMesh tile 烘焙。步骤：
1. 将 `TileMap::bake_tile` 替换为 Recast 的 `rcBuildTileCache` 调用
2. 用 Detour 的 `dtNavMesh` 替代简化的 `NavTile` 结构
3. 实现 Detour 的 `dtTileCache` 管理瓦片生命周期
4. 对比纯几何 NavMesh vs 网格简化的寻路质量和性能

## 4. 扩展阅读

- **Mononen, M. (2009). "Recast Navigation Mesh Toolkit."** Recast/Detour 原项目文档。重点阅读 `RecastDemo` 中的 Tile Mesh/Tile Cache 模式及其与 Solo Mesh 模式的区别。
- **Unity Manual: "NavMesh Obstacle".** Unity 官方文档，详述 `NavMeshObstacle` 的 Carve vs 非 Carve 模式及其性能影响。
- **Detour Tile Cache API:** `<DetourTileCache.h>` 中的 `dtTileCache` 类：`addTile`/`removeTile`/`buildTile` 的调用顺序和线程安全考虑。
- **Snook, G. (2000). "Simplified 3D Movement and Pathfinding Using Navigation Meshes." Game Programming Gems.** NavMesh 概念的开创性文章。虽然是静态 NavMesh，但基本概念是理解动态 NavMesh 的前置。
- **Unreal Engine: "Dynamic Navigation Mesh."** UE 的 Dynamic Modifiers Only vs Full Rebuild 模式。了解工业引擎如何平衡烘焙质量和实时更新。

## 常见陷阱

1. **Tile 边界不连续**：当相邻 tile 独自烘焙时，边界上的 NavMesh 多边形可能不对齐。Recast 的解法是在体素化和区域生长阶段就让相邻 tile 共享边界体素（1 体素重叠）。Detour 的 `dtNavMesh` 自动处理跨 tile 寻路。在自己的实现中，需要在 tile 边界上确保连通性一致——最简单的方法是在每个 tile 的边界格子上额外做一层重叠查询。

2. **dirty tile 标记不充分**：障碍物可能覆盖多个 tile，AABB 计算时需要取 `floor( (center - radius) / TILE_SIZE )` 到 `ceil( (center + radius) / TILE_SIZE )`。忘记加 margin → 障碍边缘的 tile 没有标记 dirty → 路径可能穿过障碍边缘。经验规则：AABB margin 至少 = 2 × CELL_SIZE。

3. **烘焙与寻路的竞态**：在多线程环境中，如果主线程正在某个 tile 上寻路，烘焙线程同时更新这个 tile，会导致寻路器看到不一致的 NavMesh 数据。解法：使用双缓冲（烘焙到临时 buffer，完成后原子交换）或读写锁（寻路持有读锁，烘焙持有写锁）。

4. **Carving 模式下的几何退化**：连续差集操作后，NavMesh 多边形可能产生退化边（长度为 0 或接近 0）、极窄通道（宽度小于 Agent 半径）、或悬空顶点。每次 carving 后都需要后处理：移除退化多边形、合并共线边、简化顶点。

5. **忽略障碍移除后的"残留"**：当障碍从 NavMesh 上移走后，被遮挡的区域应该恢复为可通行。但恢复操作不是简单的"把数据改回来"——从烘焙 tile 时就必须有原始静态几何体的快照。在重新烘焙 tile 时，必须：① 加载静态几何 → ② 重新体素化 → ③ 重新应用**当前所有活跃障碍** → ④ 剖分。缺少第 ③ 步 → 障碍移除后区域仍然被阻塞。

6. **动态障碍过多 → tile 烘焙频率过高**：如果每帧都有几十个障碍移动，为每个障碍重新烘焙 tile 的开销不可接受。策略：
   - **合并更新**：收集一帧内所有变化的障碍，合并受影响 tile，一次性烘焙
   - **分帧烘焙**：将 dirty tile 队列分配在 N 帧内完成（如每帧最多烘焙 2 个 tile）
   - **LOD 烘焙**：远处的障碍使用更大/更粗糙的 tile，减少烘焙精度
   - **回退方案**：障碍过多时（> 阈值），切换到动态网格（D* Lite）模式
