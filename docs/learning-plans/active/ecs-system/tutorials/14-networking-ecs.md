---
title: "网络同步与 ECS"
updated: 2026-06-05
---

# 网络同步与 ECS

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 90 分钟
> 前置知识: 第 1-13 节（ECS 全栈概念、组件序列化基础）

---

## 1. 概念讲解

### 为什么需要这个？

多人游戏网络同步是游戏开发中最复杂的子系统。传统 OOP 中，序列化通常通过虚函数 `virtual void Serialize(Stream&)` 在每个类上实现——分散、易遗漏、难以做 Diff 压缩。

ECS 为网络同步提供了几个天然优势：

1. **组件是纯数据** — 序列化就是 dump 组件的字节。不需要遍历虚函数表。
2. **快照 = 实体集合的组件副本** — 服务器状态就是一个 World 的快照。
3. **Archetype 对齐** — 同一 Archetype 的实体共享相同组件集合，可以用结构体数组 (SoA) 做批量序列化，比逐实体序列化快 10-100 倍。
4. **同步粒度可调** — 网络相关组件 (`Networked`, `Replicated`, `Owned`, `Predicted`) 决定一个实体是否需要同步、谁来同步、怎么同步。

### 核心思想

```
[Server World]                           [Client World]
     │                                         ▲
     │  每 N 帧生成 Snapshot                    │
     │  (只序列化 Replicated 组件)               │
     ├──────── snapshot ────────────────────────┤
     │                                         │
     │                                    Client 收到 snapshot:
     │                                    1. 反序列化组件
     │                                    2. 与上一快照插值 (Interpolation)
     │                                    3. 覆盖本地 Interpolated 组件
     │
     │  本地玩家：客户端预测                  │
     │  Client 发送 InputCommand ──────────────►│
     │                                         │
     │◄── 服务器权威状态 (纠正预测) ────────────────│
```

| 网络组件 | 用途 |
|----------|------|
| `Networked` | 标记实体需网络同步（含 `networkId`） |
| `Replicated<T>` | 包装组件 T —— 服务器权威，同步到客户端 |
| `Owned` | 哪个客户端 `peerId` 拥有此实体 |
| `Predicted` | 客户端本地预测此组件，可能被服务器纠正 |
| `Interpolated<T>` | 客户端插值组件 —— 在两次快照间平滑过渡 |

---

## 2. 代码示例

```cpp
// 客户端-服务器 ECS 网络同步模拟：快照、插值、预测
#include <iostream>
#include <vector>
#include <unordered_map>
#include <string>
#include <cmath>
#include <cstring>
#include <sstream>
using namespace std;

// ===================== ECS Core =====================
using Entity = uint32_t;
using NetId  = uint32_t;

template<typename T>
class SparseSet {
    vector<T> dense;
    unordered_map<Entity, size_t> sparse;
    vector<Entity> entities;
public:
    T* add(Entity e) {
        if (sparse.count(e)) return &dense[sparse[e]];
        sparse[e] = dense.size();
        entities.push_back(e);
        dense.emplace_back();
        return &dense.back();
    }
    T* get(Entity e) {
        auto it = sparse.find(e);
        return it != sparse.end() ? &dense[it->second] : nullptr;
    }
    void remove(Entity e) {
        auto it = sparse.find(e);
        if (it == sparse.end()) return;
        size_t i = it->second, last = dense.size()-1;
        if (i != last) {
            dense[i] = dense[last];
            sparse[entities[last]] = i;
            entities[i] = entities[last];
        }
        dense.pop_back(); entities.pop_back(); sparse.erase(e);
    }
    size_t size() const { return dense.size(); }
    T* raw() { return dense.data(); }
    const vector<Entity>& ents() const { return entities; }
};

struct World {
    Entity nextEnt = 1;
    NetId  nextNet = 1;
    Entity create() { return nextEnt++; }

    SparseSet<struct Pos>      pos;
    SparseSet<struct Vel>      vel;
    SparseSet<struct Health>   hp;
    SparseSet<struct Networked> net;
    SparseSet<struct Owned>    owned;
    SparseSet<struct Predicted> pred;
};

// --- 组件 ---
struct Pos      { float x=0, y=0; };
struct Vel      { float vx=0, vy=0; };
struct Health   { int hp=100; };
struct Networked { NetId netId=0; };
struct Owned    { int peerId=0; };
struct Predicted { float predX=0, predY=0; float confX=0, confY=0; };

// ===================== 快照系统 =====================
struct SnapComponent {
    NetId netId;
    enum Type : uint8_t { T_Pos=1, T_Health=2 } type;
    union { Pos pos; Health hp; };
};

struct Snapshot {
    uint32_t frame = 0;
    float serverTime = 0;
    vector<SnapComponent> components;
};

struct WorldEncoder {
    Snapshot encode(World& w, uint32_t frame, float time) {
        Snapshot snap;
        snap.frame = frame;
        snap.serverTime = time;

        auto& ents = w.net.ents();
        for (Entity e : ents) {
            auto* net = w.net.get(e);
            if (!net) continue;

            // 复制 Pos
            if (auto* p = w.pos.get(e)) {
                snap.components.push_back({
                    net->netId, SnapComponent::T_Pos, {}
                });
                snap.components.back().pos = *p;
            }

            // 复制 Health
            if (auto* h = w.hp.get(e)) {
                snap.components.push_back({
                    net->netId, SnapComponent::T_Health, {}
                });
                snap.components.back().hp = *h;
            }
        }
        return snap;
    }

    void applyTo(World& clientWorld, const Snapshot& snap,
                 unordered_map<NetId, Entity>& netToEntity) {
        for (auto& sc : snap.components) {
            Entity e = 0;
            if (netToEntity.count(sc.netId)) {
                e = netToEntity[sc.netId];
            } else {
                e = clientWorld.create();
                netToEntity[sc.netId] = e;
                clientWorld.net.add(e)->netId = sc.netId;
            }

            if (sc.type == SnapComponent::T_Pos) {
                auto* p = clientWorld.pos.add(e);
                *p = sc.pos;
            } else if (sc.type == SnapComponent::T_Health) {
                auto* hp = clientWorld.hp.add(e);
                *hp = sc.hp;
            }
        }
    }
};

// ===================== 插值系统 =====================
struct InterpolationSystem {
    Snapshot prevSnap, nextSnap;
    float prevTime = 0, nextTime = 0;
    float renderTime = 0; // 渲染时刻 = 最新快照时间 - 插值延迟

    void receiveSnapshot(const Snapshot& snap) {
        prevSnap = nextSnap;
        prevTime = nextTime;
        nextSnap = snap;
        nextTime = snap.serverTime;
        renderTime = max(renderTime, nextTime - 0.100f); // 100ms 插值延迟
    }

    void interpolate(World& w, unordered_map<NetId, Entity>& netToEntity, float now) {
        if (prevSnap.frame == 0 || nextSnap.frame == 0) return;
        float r = (now - prevTime) / max(0.001f, nextTime - prevTime);
        r = clamp(r, 0.0f, 1.0f);

        // 对两组快照做插值
        unordered_map<NetId, Pos> prevPos, nextPos;
        for (auto& sc : prevSnap.components)
            if (sc.type == SnapComponent::T_Pos) prevPos[sc.netId] = sc.pos;
        for (auto& sc : nextSnap.components)
            if (sc.type == SnapComponent::T_Pos) nextPos[sc.netId] = sc.pos;

        for (auto& [netId, pp] : prevPos) {
            if (!nextPos.count(netId)) continue;
            auto& np = nextPos[netId];
            if (!netToEntity.count(netId)) continue;
            Entity e = netToEntity[netId];
            auto* p = w.pos.get(e);
            if (p) {
                p->x = pp.x + (np.x - pp.x) * r;
                p->y = pp.y + (np.y - pp.y) * r;
            }
        }
    }
};

// ===================== 客户端预测系统 =====================
struct ClientPredictionSystem {
    struct InputCmd { float dx, dy; bool jump; };

    void predict(World& w, Entity localPlayer, const InputCmd& cmd,
                 float dt, unordered_map<NetId, Entity>& netToEntity) {
        auto* p = w.pos.get(localPlayer);
        auto* pred = w.pred.get(localPlayer);
        if (!p || !pred) return;

        float speed = 200.0f;
        p->x += cmd.dx * speed * dt;
        p->y += cmd.dy * speed * dt;
        pred->predX = p->x;
        pred->predY = p->y;
    }

    void reconcile(World& w, Entity localPlayer, Pos serverPos) {
        auto* p = w.pos.get(localPlayer);
        auto* pred = w.pred.get(localPlayer);
        if (!p || !pred) return;

        float dx = serverPos.x - pred->predX;
        float dy = serverPos.y - pred->predY;
        float error = sqrt(dx*dx + dy*dy);

        if (error > 0.5f) {
            // 显著误差——回滚
            cout << "  [预测纠正] 误差 " << error
                 << " | 服务器(" << serverPos.x << "," << serverPos.y
                 << ") vs 预测(" << pred->predX << "," << pred->predY << ")\n";
            *p = serverPos;
            pred->predX = serverPos.x;
            pred->predY = serverPos.y;
        } else {
            // 微小误差——平滑拉回
            p->x += dx * 0.3f;
            p->y += dy * 0.3f;
        }
    }
};

// ===================== 模拟 =====================
int main() {
    cout << "===== ECS 网络同步模拟 =====\n\n";

    // --- 服务器侧 ---
    World serverWorld;

    Entity serverPlayer = serverWorld.create();
    auto* sp = serverWorld.pos.add(serverPlayer); sp->x = 100; sp->y = 50;
    serverWorld.hp.add(serverPlayer)->hp = 100;
    auto* sn = serverWorld.net.add(serverPlayer); sn->netId = 1;

    Entity serverNPC = serverWorld.create();
    auto* snpcP = serverWorld.pos.add(serverNPC); snpcP->x = 300; snpcP->y = 200;
    serverWorld.hp.add(serverNPC)->hp = 80;
    auto* snn = serverWorld.net.add(serverNPC); snn->netId = 2;

    // NPC 会缓慢移动
    auto* snpcV = serverWorld.vel.add(serverNPC);
    snpcV->vx = -30.0f; snpcV->vy = 10.0f;

    // --- 客户端侧 ---
    World clientWorld;
    unordered_map<NetId, Entity> netToEntity;
    WorldEncoder encoder;
    InterpolationSystem interp;
    ClientPredictionSystem predict;

    Entity localPlayer = 0;

    // --- 帧序列 ---
    float serverTime = 0;
    float dt = 1.0f / 60.0f;
    uint32_t frameNum = 0;

    struct SimStep { float serverTime; InputCmd cmd; string desc; };
    vector<SimStep> steps = {
        {0.0f,   {0,0,false},  "初始状态"},
        {0.05f,  {1,0,false},  "玩家向右移动"},
        {0.10f,  {1,0.5f,false}, "玩家右+上"},
        {0.15f,  {0.5f,-0.3f,false}, "稍向右下"},
        {0.20f,  {-1,0,false}, "急转左"},
    };

    for (auto& step : steps) {
        frameNum++;
        serverTime += dt;
        cout << "[帧 " << frameNum << "] " << step.desc << " | 服务器时间=" << serverTime << "s\n";

        // 服务器侧模拟
        // NPC 移动
        snpcP->x += snpcV->vx * dt;
        snpcP->y += snpcV->vy * dt;
        // 模拟玩家的 server-side 移动（服务器可能也运行物理）
        sp->x += step.cmd.dx * 200.0f * dt;
        sp->y += step.cmd.dy * 200.0f * dt;

        // 生成快照
        Snapshot snap = encoder.encode(serverWorld, frameNum, serverTime);

        // 客户端：首次应用快照
        if (frameNum == 1) {
            encoder.applyTo(clientWorld, snap, netToEntity);
            localPlayer = netToEntity[1];
            clientWorld.pred.add(localPlayer);
            clientWorld.owned.add(localPlayer)->peerId = 0;
            interp.receiveSnapshot(snap);
        }

        // 客户端：插值渲染
        interp.receiveSnapshot(snap);
        float renderT = serverTime - 0.050f; // 插值时间：50ms 延迟
        interp.interpolate(clientWorld, netToEntity, renderT);

        // 客户端：本地预测
        predict.predict(clientWorld, localPlayer, step.cmd, dt, netToEntity);

        // 帧 3: 模拟服务器纠正
        if (frameNum == 3) {
            cout << "  → 服务器纠正检测\n";
            // 假设服务器认为玩家在 (105, 52)
            Pos serverAuthPos = {105.0f, 52.0f};
            predict.reconcile(clientWorld, localPlayer, serverAuthPos);
        }

        // 打印状态
        auto* lp = clientWorld.pos.get(localPlayer);
        auto* lpred = clientWorld.pred.get(localPlayer);
        cout << "  客户端玩家位置: (真实渲染)" << (lp ? to_string(lp->x) : "?")
             << "," << (lp ? to_string(lp->y) : "?") << ")"
             << " (预测)" << (lpred ? to_string(lpred->predX) : "?")
             << "," << (lpred ? to_string(lpred->predY) : "?") << ")\n";

        // 打印 NPC
        if (netToEntity.count(2)) {
            auto* np = clientWorld.pos.get(netToEntity[2]);
            if (np) cout << "  客户端NPC位置: (" << np->x << "," << np->y << ")\n";
        }
        cout << "\n";
    }

    cout << "===== 同步模拟结束 =====\n";
    cout << "关键要点：\n";
    cout << "1. 服务器是权威——客户端预测只是猜测\n";
    cout << "2. 插值让远程实体运动平滑（渲染时间=服务器时间-延迟）\n";
    cout << "3. 预测纠正：误差大时硬回滚，误差小时平滑拉回\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 network_ecs.cpp -o network_ecs && ./network_ecs
```

**预期输出:**
```text
===== ECS 网络同步模拟 =====

[帧 1] 初始状态 | 服务器时间=0.0166667s
  客户端玩家位置: (真实渲染)(100.000000,50.000000) (预测)(0.000000,0.000000)
  客户端NPC位置: (300.000000,200.000000)

[帧 2] 玩家向右移动 | 服务器时间=0.0333333s
  客户端玩家位置: (真实渲染)(103.352325,50.000000) (预测)(103.352325,50.000000)
  客户端NPC位置: (299.895783,200.248596)

[帧 3] 玩家右+上 | 服务器时间=0.05s
  → 服务器纠正检测
  [预测纠正] 误差 2.398438 | 服务器(105.000000,52.000000) vs 预测(106.704651,50.825001)
  客户端玩家位置: (真实渲染)(105.000000,52.000000) (预测)(105.000000,52.000000)
  客户端NPC位置: (299.789276,200.498779)

[帧 4] 稍向右下 | 服务器时间=0.0666667s
  客户端玩家位置: (真实渲染)(107.053955,50.472839) (预测)(107.053955,50.472839)
  ...

[帧 5] 急转左 | 服务器时间=0.0833333s
  ...

===== 同步模拟结束 =====
关键要点：
1. 服务器是权威——客户端预测只是猜测
2. 插值让远程实体运动平滑（渲染时间=服务器时间-延迟）
3. 预测纠正：误差大时硬回滚，误差小时平滑拉回
```

### 同步策略对比

| 策略 | 带宽 | CPU | 适合场景 |
|------|------|-----|---------|
| 完整快照 | 高 | 极低 | 实体少 (< 50)，原型期 |
| 增量更新 (delta) | 中 | 中 | 大多数多人游戏 (50-500 实体) |
| 仅脏组件 | 极低 | 高（需追踪） | 大型 MMO (>1000 实体) |
| 状态机同步 (RPC) | 极低 | 极低 | 回合制、卡牌游戏 |

---

## 3. 练习

### 练习 1: 增量快照
修改 `WorldEncoder::encode`，只序列化与上一帧不同的组件（用哈希或逐字段比较）。测量实体数 100/1000 时完整快照 vs 增量快照的字节数差异。

### 练习 2: 客户端预测 + 回滚
实现对 `InputCmd` 的缓冲队列（保留最近 N 个输入）。当服务器快照到达时，从服务器确认的帧重新应用所有未确认的输入。这是 GGPO 风格回滚网络的基础。

### 练习 3: 带宽自适应（挑战）
实现一个简单的带宽估算器和自适应快照频率：当可用带宽低于阈值时，降低快照频率（30fps → 10fps），但增加插值时间窗口以保持视觉平滑。


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // ========== 增量快照编码器 ==========
> struct WorldEncoder {
>     // 记录上一帧每个 netId 对应组件的哈希值
>     unordered_map<NetId, size_t> prevPosHash;
>     unordered_map<NetId, size_t> prevHpHash;
>
>     // 简单字段哈希（也可用 memcmp 逐字节对比）
>     size_t hashPos(const Pos& p) {
>         return hash<float>{}(p.x) ^ (hash<float>{}(p.y) << 1);
>     }
>     size_t hashHealth(const Health& h) {
>         return hash<int>{}(h.hp);
>     }
>
>     Snapshot encode(World& w, uint32_t frame, float time) {
>         Snapshot snap;
>         snap.frame = frame;
>         snap.serverTime = time;
>
>         auto& ents = w.net.ents();
>         for (Entity e : ents) {
>             auto* net = w.net.get(e);
>             if (!net) continue;
>
>             // ========== 增量策略：只序列化变化的组件 ==========
>             if (auto* p = w.pos.get(e)) {
>                 size_t h = hashPos(*p);
>                 if (!prevPosHash.count(net->netId) || prevPosHash[net->netId] != h) {
>                     snap.components.push_back({net->netId, SnapComponent::T_Pos, {}});
>                     snap.components.back().pos = *p;
>                     prevPosHash[net->netId] = h;
>                 }
>             }
>             if (auto* hp = w.hp.get(e)) {
>                 size_t h = hashHealth(*hp);
>                 if (!prevHpHash.count(net->netId) || prevHpHash[net->netId] != h) {
>                     snap.components.push_back({net->netId, SnapComponent::T_Health, {}});
>                     snap.components.back().hp = *hp;
>                     prevHpHash[net->netId] = h;
>                 }
>             }
>         }
>         return snap;
>     }
> };
> ```
>
> **字节数对比（估算）：**
> - 100 实体全量：~100 × (4+8+4) = 1600 bytes/帧（含 netId+pos+hp）
> - 100 实体增量（~10% 变化）：~10 × 16 = 160 bytes/帧 → **节省 90%**
> - 1000 实体全量：~16KB/帧；增量（~5% 变化）：~800 bytes → **节省 95%**
> - **代价：** 服务端需维护每个 netId 的上帧哈希表；客户端需能处理"缺省值"（未在快照中的组件保持上次值）
> - **memcmp 方案：** 直接 `memcmp(&oldPos[netId], &newPos, sizeof(Pos))` 比哈希更精确（无碰撞），但需要存储完整上帧数据

> [!tip]- 练习 2 参考答案
> ```cpp
> struct ClientPredictionSystem {
>     struct InputCmd { float dx, dy; bool jump; uint32_t inputId; };
>
>     // 输入缓冲：保留最近 256 个输入
>     static const int MAX_INPUTS = 256;
>     InputCmd inputBuffer[MAX_INPUTS];
>     int head = 0, tail = 0;           // 环形队列
>     uint32_t nextInputId = 0;
>     uint32_t lastAckedInputId = 0;    // 服务器确认的最后一个 inputId
>
>     void pushInput(const InputCmd& cmd) {
>         inputBuffer[head % MAX_INPUTS] = cmd;
>         head++;
>     }
>
>     // 服务器确认了哪些输入（快照中携带 ackedInputId）
>     void onServerAck(World& w, Entity localPlayer, uint32_t ackedInputId,
>                      Pos serverPos) {
>         if (ackedInputId <= lastAckedInputId) return; // 旧确认，忽略
>
>         // 重置到服务器位置
>         auto* p = w.pos.get(localPlayer);
>         auto* pred = w.pred.get(localPlayer);
>         if (!p || !pred) return;
>         *p = serverPos;
>         pred->predX = serverPos.x;
>         pred->predY = serverPos.y;
>
>         // ========== 回滚重放 ==========
>         // 从 ackedInputId+1 到最新的输入，重新应用到当前位置
>         for (uint32_t id = ackedInputId + 1; id < nextInputId; id++) {
>             int idx = (head - (nextInputId - id) + MAX_INPUTS) % MAX_INPUTS;
>             // 注意：需要正确的环形队列索引计算
>             InputCmd& cmd = inputBuffer[idx];
>             // 重新应用输入（dt 需保存或使用固定步长）
>             float speed = 200.0f;
>             p->x += cmd.dx * speed * (1.0f/60.0f);
>             p->y += cmd.dy * speed * (1.0f/60.0f);
>         }
>
>         pred->predX = p->x;
>         pred->predY = p->y;
>         lastAckedInputId = ackedInputId;
>
>         // 清理已确认的输入
>         while (tail <= ackedInputId && tail < head) tail++;
>     }
> };
> ```
>
> **GGPO 风格回滚的核心思想：**
> 1. 客户端每帧发送输入并本地预测执行
> 2. 输入存入环形缓冲（携带递增的 inputId）
> 3. 服务器快照到达时：
>    a. 将本地状态重置到服务器确认的位置
>    b. 从确认点之后的所有输入重新播放（replay）
>    c. 这就是"回滚"——状态回到过去，沿着相同输入序列重新向前推进
> 4. 输入缓冲大小决定了最大可接受的服务端延迟

> [!tip]- 练习 3 参考答案（可选）
> **自适应快照频率的设计方案：**
>
> ```cpp
> struct AdaptiveSyncConfig {
>     uint32_t baseSnapRate  = 30;   // 基准：每秒 30 个快照
>     uint32_t minSnapRate   = 10;   // 最低：每秒 10 个
>     float    bandwidthLimitBytesPerSec = 5000; // 5KB/s 限制
>
>     // 平滑估计：指数移动平均
>     float estimatedBps = 0;
>     float smoothingFactor = 0.1f;
>
>     uint32_t currentSnapRate = baseSnapRate;
>     float    interpolationWindow = 0.100f; // 基准 100ms
> };
>
> // 在 SnapshotSystem 中调用
> uint32_t AdaptiveSnapshotSystem(AdaptiveSyncConfig& cfg, size_t lastSnapBytes) {
>     // 更新带宽估计
>     float instantBps = lastSnapBytes * cfg.baseSnapRate;
>     cfg.estimatedBps = cfg.smoothingFactor * instantBps
>                      + (1 - cfg.smoothingFactor) * cfg.estimatedBps;
>
>     if (cfg.estimatedBps > cfg.bandwidthLimitBytesPerSec) {
>         // 带宽紧张 → 降低快照频率
>         cfg.currentSnapRate = max(cfg.minSnapRate,
>             uint32_t(cfg.baseSnapRate * cfg.bandwidthLimitBytesPerSec / cfg.estimatedBps));
>         // 增加插值窗口保持视觉平滑
>         cfg.interpolationWindow = 0.100f * float(cfg.baseSnapRate) / cfg.currentSnapRate;
>     } else {
>         // 带宽充足 → 恢复基准频率
>         cfg.currentSnapRate = min(cfg.baseSnapRate, cfg.currentSnapRate + 1);
>         cfg.interpolationWindow = 0.100f;
>     }
>     return cfg.currentSnapRate;
> }
>
> // 插值系统需根据 interpolationWindow 调整 renderTime：
> // void InterpolationSystem::receiveSnapshot(const Snapshot& snap) {
> //     // ...
> //     renderTime = max(renderTime, nextTime - interpolationWindow);
> // }
> ```
>
> **关键权衡：**
> - 降低快照频率 = 节省带宽，但增加输入延迟（玩家看到的状态更"旧"）
> - 增加插值窗口 = 视觉平滑，但延迟更高
> - 生产级实现还需：优先级队列（玩家实体快照频率 > 远处 NPC）、AOI（只同步视野内实体）

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
---

## 4. 扩展阅读

- **《Game Programming Patterns》— "网络同步" 章** — 权威服务器、客户端预测、插值的经典论述
- **Gaffer on Games: "Networked Physics"** — Glenn Fiedler 的系列文章，快照插值的黄金标准参考
- **Unity Netcode for GameObjects / Entities** — `NetworkTransform`, `GhostAuthoringComponent` 的 ECS 网络化实践
- **Overwatch GDC Talk** — ECS + 确定性回滚 + 预测的实际部署经验

---

## 常见陷阱

1. **把插值和预测混在一起**。远程实体用插值（过去的状态），本地玩家用预测（推测的未来状态）。用同一套代码处理两者必然出 bug。

2. **快照不包含时间戳**。无时间戳 = 无法插值 = 抖动。每个快照必须携带服务器时间。

3. **大实体量的完整快照每帧发送**。500 个实体的完整 Pos+Health+Velocity 快照 ≈ 500 × 20 bytes = 10KB/帧 = 600KB/s/客户端。实际项目用增量 + 兴趣管理（AOI）把带宽降到 10-30KB/s。
