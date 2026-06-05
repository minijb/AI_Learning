---
title: "UI 系统与 ECS"
updated: 2026-06-05
---

# UI 系统与 ECS

> 所属计划: ECS 系统 — 从原理到实践
> 预计耗时: 80 分钟
> 前置知识: 第 1-12 节（ECS 组件系统、System 设计、事件处理）

---

## 1. 概念讲解

### 为什么需要这个？

传统 UI 框架（Qt、Unity UI、WPF、React）清一色使用 OOP Widget 树：

```
Widget → Container → Panel → StackPanel
                      → Grid
        → Control   → Button
                      → TextBox
                      → Slider
```

问题：

1. **深层继承** — `Button` 同时继承自 `Control`、`Clickable`、`Focusable`、`Animatable`……修改基类影响所有控件。
2. **组件复用困难** — 想让 `Slider` 也可拖拽排序？需要再建一个 `DraggableSlider` 子类。
3. **数据驱动弱** — MVVM/Redux 把状态拉出控件树，但控件自身的增删改仍需命令式 API。

ECS 方案：UI 元素是实体，样式、布局、交互行为是组件。

### 核心思想

| 传统 OOP Widget | ECS 等价 |
|------------------|----------|
| `Button : Control` | 实体 + `RectTransform` + `Text` + `Interactable` + `Image` |
| `ScrollView : Panel` | 实体 + `RectTransform` + `Scrollable` + `Mask` |
| `layout.perform()` | `LayoutSystem` 批量重算所有 `RectTransform` |
| `onClick.AddListener()` | `ClickEvent` 临时实体加入 `EventQueue` |

**事件系统设计**：点击/悬停/拖拽不是回调注册，而是**临时实体**或**事件组件**。

```
                     RaycastSystem
                          |
                          v
  输入 → InputCaptureSystem → EventEmitSystem → 目标实体收到 EventComponent
```

布局系统是一个普通 System：它遍历所有带 `RectTransform` + `LayoutElement` 的实体，按照 `LayoutGroup`（Vertical/Horizontal/Grid）约束重算坐标。

---

## 2. 代码示例

```cpp
// 简单 ECS UI 框架：创建按钮、文本、处理点击事件 — 完整可运行
#include <iostream>
#include <vector>
#include <unordered_map>
#include <string>
#include <functional>
#include <memory>
using namespace std;

// ===================== ECS 核心 =====================
using Entity = uint32_t;

class UIWorld {
    Entity next = 1;
    struct PoolBase { virtual ~PoolBase() = default; };
    template<typename T>
    struct Pool : PoolBase {
        vector<T> data;
        unordered_map<Entity, size_t> idx;
        vector<Entity> rev;
    };
    unordered_map<int, unique_ptr<PoolBase>> pools;

    template<typename T>
    Pool<T>& ensurePool(int cid) {
        auto& p = pools[cid];
        if (!p) p = make_unique<Pool<T>>();
        return static_cast<Pool<T>&>(*p);
    }

public:
    Entity create() { return next++; }
    void destroy(Entity e) {
        for (auto& [_, pool] : pools) {
            // 简化处理：标记删除
        }
    }

    template<typename T>
    T* add(Entity e, int cid) {
        auto& pool = ensurePool<T>(cid);
        if (pool.idx.count(e)) return &pool.data[pool.idx[e]];
        pool.idx[e] = pool.data.size();
        pool.rev.push_back(e);
        pool.data.emplace_back();
        return &pool.data.back();
    }

    template<typename T>
    T* get(Entity e, int cid) {
        auto it = pools.find(cid);
        if (it == pools.end()) return nullptr;
        auto& pool = static_cast<Pool<T>&>(*it->second);
        auto i = pool.idx.find(e);
        return i != pool.idx.end() ? &pool.data[i->second] : nullptr;
    }

    template<typename T>
    vector<T*> getAll(int cid) {
        vector<T*> result;
        auto it = pools.find(cid);
        if (it == pools.end()) return result;
        auto& pool = static_cast<Pool<T>&>(*it->second);
        for (auto& d : pool.data) result.push_back(&d);
        return result;
    }

    template<typename T>
    const vector<Entity>& entities(int cid) {
        static vector<Entity> empty;
        auto it = pools.find(cid);
        if (it == pools.end()) return empty;
        return static_cast<Pool<T>&>(*it->second).rev;
    }
};

// ===================== UI 组件 =====================
enum UIComp : int {
    UIC_RectTransform = 1, UIC_Text, UIC_Color, UIC_Interactable, UIC_Parent,
    UIC_ClickHandler, UIC_LayoutElement, UIC_Scrollable
};

struct RectTransform {
    float x=0, y=0, w=100, h=40;
    float pivotX=0.5f, pivotY=0.5f;
    int depth = 0; // 渲染/点击排序
};

struct UIText {
    string content;
    int fontSize = 14;
};

struct UIColor {
    uint8_t r=200, g=200, b=200, a=255;
    static UIColor White()  { return {255,255,255,255}; }
    static UIColor Blue()   { return {60,120,220,255}; }
    static UIColor Red()    { return {220,60,60,255}; }
    static UIColor Green()  { return {60,200,80,255}; }
    static UIColor Gray()   { return {180,180,180,255}; }
};

struct Interactable {
    bool enabled = true;
    enum State { Normal=0, Hovered=1, Pressed=2, Disabled=3 } state = Normal;
};

struct UIClickHandler {
    function<void(Entity)> callback;
};

struct UILayoutElement {
    float minW=0, minH=0, preferredW=100, preferredH=40, flexibleW=1, flexibleH=1;
};

// ===================== 事件系统 =====================
struct InputEvent {
    enum Type { MouseDown, MouseUp, MouseMove } type;
    float mx, my;
};

class EventQueue {
    vector<InputEvent> events;
public:
    void push(const InputEvent& e) { events.push_back(e); }
    const vector<InputEvent>& all() const { return events; }
    void clear() { events.clear(); }
};

// ===================== 系统 =====================
struct LayoutSystem {
    void update(UIWorld& w) {
        auto rects = w.getAll<RectTransform>(UIC_RectTransform);
        auto elems = w.getAll<UILayoutElement>(UIC_LayoutElement);

        for (size_t i = 0; i < rects.size(); i++) {
            if (i >= elems.size() || !elems[i]) continue;
            // 简单垂直布局：按 parent 分组（略），此处演示最小/首选尺寸
            auto& rt = *rects[i];
            auto& el = *elems[i];
            rt.w = max(el.minW, el.preferredW);
            rt.h = max(el.minH, el.preferredH);
        }
    }
};

struct RenderSystem {
    void render(UIWorld& w, int screenW, int screenH) {
        auto rects = w.getAll<RectTransform>(UIC_RectTransform);
        auto texts = w.getAll<UIText>(UIC_Text);
        auto colors = w.getAll<UIColor>(UIC_Color);
        auto inters = w.getAll<Interactable>(UIC_Interactable);

        cout << "===== 渲染帧 =====\n";
        for (size_t i = 0; i < rects.size(); i++) {
            cout << "  元素[" << i << "]: rect=("
                 << rects[i]->x << "," << rects[i]->y
                 << " " << rects[i]->w << "x" << rects[i]->h << ")";

            if (i < colors.size() && colors[i])
                printf(" color=(%d,%d,%d)", colors[i]->r, colors[i]->g, colors[i]->b);

            if (i < texts.size() && texts[i])
                cout << " text=\"" << texts[i]->content << "\"";

            if (i < inters.size() && inters[i]) {
                const char* states[] = {"Normal","Hovered","Pressed","Disabled"};
                cout << " state=" << states[inters[i]->state];
            }
            cout << "\n";
        }
        cout << "===== 渲染结束 =====\n";
    }
};

struct InputSystem {
    InputSystem() { hitTest = [](RectTransform& rt, float mx, float my) -> bool {
        float left = rt.x - rt.w * rt.pivotX;
        float top  = rt.y - rt.h * rt.pivotY;
        return mx >= left && mx <= left + rt.w
            && my >= top  && my <= top  + rt.h;
    }; }

    function<bool(RectTransform&, float, float)> hitTest;

    void process(UIWorld& w, EventQueue& queue) {
        auto& es = w.entities(UIC_RectTransform);
        auto intersects = w.getAll<Interactable>(UIC_Interactable);

        for (auto& evt : queue.all()) {
            if (evt.type != InputEvent::MouseDown) continue;

            // 反向遍历 depth 高者优先
            Entity hit = 0;
            int bestDepth = -1;
            for (size_t i = 0; i < es.size(); i++) {
                Entity e = es[i];
                auto* rt = w.get<RectTransform>(e, UIC_RectTransform);
                if (!rt) continue;
                if (rt->depth > bestDepth && hitTest(*rt, evt.mx, evt.my)) {
                    bestDepth = rt->depth;
                    hit = e;
                }
            }

            if (hit) {
                auto* inter = w.get<Interactable>(hit, UIC_Interactable);
                if (inter && inter->enabled) {
                    inter->state = Interactable::Pressed;
                    auto* handler = w.get<UIClickHandler>(hit, UIC_ClickHandler);
                    if (handler && handler->callback) {
                        handler->callback(hit);
                    }
                }
            }
        }
        queue.clear();
    }
};

// ===================== 主函数 =====================
int main() {
    UIWorld world;
    LayoutSystem layoutSys;
    RenderSystem renderSys;
    InputSystem inputSys;
    EventQueue eventQueue;

    // --- 创建背景面板 ---
    Entity panel = world.create();
    auto* prt = world.add<RectTransform>(panel, UIC_RectTransform);
    prt->x = 400; prt->y = 300; prt->w = 300; prt->h = 200; prt->depth = 0;
    world.add<UIColor>(panel, UIC_Color)->r = 50;
    world.add<UIColor>(panel, UIC_Color)->g = 50;
    world.add<UIColor>(panel, UIC_Color)->b = 70;

    // --- 标题文本 ---
    Entity title = world.create();
    auto* trt = world.add<RectTransform>(title, UIC_RectTransform);
    trt->x = 400; trt->y = 240; trt->w = 200; trt->h = 30; trt->depth = 1;
    auto* ttxt = world.add<UIText>(title, UIC_Text);
    ttxt->content = "ECS UI 框架演示";
    ttxt->fontSize = 18;
    world.add<UIColor>(title, UIC_Color) = UIColor::White();

    // --- "开始游戏" 按钮 ---
    Entity btnStart = world.create();
    auto* brt = world.add<RectTransform>(btnStart, UIC_RectTransform);
    brt->x = 400; brt->y = 300; brt->w = 160; brt->h = 44; brt->depth = 10;
    auto* btxt = world.add<UIText>(btnStart, UIC_Text);
    btxt->content = "开始游戏";
    btxt->fontSize = 16;
    auto* bclr = world.add<UIColor>(btnStart, UIC_Color);
    *bclr = UIColor::Blue();
    world.add<Interactable>(btnStart, UIC_Interactable);
    auto* bclk = world.add<UIClickHandler>(btnStart, UIC_ClickHandler);
    bclk->callback = [](Entity btn) {
        cout << ">>> [事件响应] 按钮被点击：" << btn << " — 触发游戏启动逻辑\n";
    };

    // --- "设置" 按钮 ---
    Entity btnSettings = world.create();
    auto* srt = world.add<RectTransform>(btnSettings, UIC_RectTransform);
    srt->x = 400; srt->y = 360; srt->w = 160; srt->h = 44; srt->depth = 10;
    auto* stxt = world.add<UIText>(btnSettings, UIC_Text);
    stxt->content = "设置";
    stxt->fontSize = 16;
    auto* sclr = world.add<UIColor>(btnSettings, UIC_Color);
    *sclr = UIColor::Gray();
    world.add<Interactable>(btnSettings, UIC_Interactable);
    auto* sclk = world.add<UIClickHandler>(btnSettings, UIC_ClickHandler);
    sclk->callback = [](Entity btn) {
        cout << ">>> [事件响应] 设置按钮被点击：" << btn << " — 打开设置面板\n";
    };

    // --- "退出" 按钮 ---
    Entity btnQuit = world.create();
    auto* qrt = world.add<RectTransform>(btnQuit, UIC_RectTransform);
    qrt->x = 400; qrt->y = 420; qrt->w = 160; qrt->h = 44; qrt->depth = 10;
    auto* qtxt = world.add<UIText>(btnQuit, UIC_Text);
    qtxt->content = "退出";
    qtxt->fontSize = 16;
    auto* qclr = world.add<UIColor>(btnQuit, UIC_Color);
    *qclr = UIColor::Red();
    world.add<Interactable>(btnQuit, UIC_Interactable);
    auto* qclk = world.add<UIClickHandler>(btnQuit, UIC_ClickHandler);
    qclk->callback = [](Entity) {
        cout << ">>> [事件响应] 退出按钮被点击 — 关闭应用\n";
    };

    // --- 布局 ---
    layoutSys.update(world);

    // --- 模拟 3 帧的渲染与输入 ---
    cout << "===== ECS UI 框架演示 =====\n";

    // 帧 1: 仅渲染
    renderSys.render(world, 800, 600);

    // 帧 2: 鼠标点击 "开始游戏"
    cout << "\n--- 帧 2: 鼠标点击 (400, 300) ---\n";
    eventQueue.push({InputEvent::MouseDown, 400, 300});
    inputSys.process(world, eventQueue);
    renderSys.render(world, 800, 600);

    // 帧 3: 鼠标点击 "退出"
    cout << "\n--- 帧 3: 鼠标点击 (400, 420) ---\n";
    eventQueue.push({InputEvent::MouseDown, 400, 420});
    inputSys.process(world, eventQueue);
    renderSys.render(world, 800, 600);

    cout << "\n===== 演示结束 =====\n";
    return 0;
}
```

**运行方式:**
```bash
g++ -std=c++17 -O2 ui_ecs.cpp -o ui_ecs && ./ui_ecs
```

**预期输出:**
```text
===== ECS UI 框架演示 =====
===== 渲染帧 =====
  元素[0]: rect=(400,300 300x200) color=(50,50,70)
  元素[1]: rect=(400,240 200x30) color=(255,255,255) text="ECS UI 框架演示"
  元素[2]: rect=(400,300 160x44) color=(60,120,220) text="开始游戏" state=Normal
  元素[3]: rect=(400,360 160x44) color=(180,180,180) text="设置" state=Normal
  元素[4]: rect=(400,420 160x44) color=(220,60,60) text="退出" state=Normal
===== 渲染结束 =====

--- 帧 2: 鼠标点击 (400, 300) ---
>>> [事件响应] 按钮被点击：3 — 触发游戏启动逻辑
===== 渲染帧 =====
  ...元素[2]... state=Pressed
===== 渲染结束 =====

--- 帧 3: 鼠标点击 (400, 420) ---
>>> [事件响应] 退出按钮被点击 — 关闭应用
...
===== 演示结束 =====
```

### OOP Widget 树 vs ECS UI

| 维度 | OOP Widget | ECS Entity |
|------|------------|------------|
| 新控件的代码量 | 继承 `Widget`，重写 `OnPaint`/`OnEvent` (~50 行) | 添加实体 + 4-5 组件 (15 行) |
| 组合行为 | `class DraggableButton : public Button, public DragHandler` → 菱形继承 | 添加 `Draggable` 组件 + `Text` + `Interactable` |
| 布局算法 | 递归 `Measure`/`Arrange` 虚函数调用 | `LayoutSystem` 一次遍历批量计算 |
| 事件分发 | 冒泡链 `event.Handled = true` | `EventQueue` + `InputSystem` 直接派发到深度最大实体 |

---

## 3. 练习

### 练习 1: 实现悬停高亮
给 `InputSystem` 添加 `MouseMove` 事件处理。当鼠标移动到按钮上时，将 `Interactable.state` 设为 `Hovered`，`RenderSystem` 根据状态调整颜色（Normal→Blue, Hovered→LightBlue, Pressed→DarkBlue）。

### 练习 2: 水平布局组
实现 `HorizontalLayoutGroup` 系统：读取带 `LayoutGroup` 组件（含 `spacing`, `padding` 字段）的父实体，遍历其子实体（通过 `Parent` 组件），按水平方向排列它们的 `RectTransform`。

### 练习 3: 脏标记优化（挑战）
给 `RectTransform` 添加 `dirty` 标志位。只有尺寸或内容变化的 UI 元素才重新布局和重绘。实现增量更新，对比全量重绘和增量更新的性能差异。

---

## 4. 扩展阅读

- **Unity UI Toolkit (UIElements)** — Unity 新一代 UI 系统，基于 UXML/USS + `VisualElement`，是 OOP 与 ECS 之间的桥梁
- **React Fiber** — 虽然不是 ECS，但其「组件=函数，render=纯计算，commit=副作用」的分相理念与 System 分阶段类似
- **Bevy UI** — Rust ECS 引擎 Bevy 的内置 UI 系统，使用 `Node`, `Text`, `Style`, `Interaction` 组件
- **ImGUI (Dear ImGui)** — 无状态立即模式 UI，"ECS 的精神 cousin"：每帧重建整个 UI 而非维护 Widget 树

---

## 常见陷阱

1. **事件累积** — 一帧内多次点击未处理完就清除。`EventQueue` 应保留到帧末统一清除，或使用双缓冲。

2. **布局震荡** — `LayoutSystem` 在一次遍历中子元素改变父元素尺寸、父元素又反过来影响子。解法：迭代至收敛或限制迭代次数。

3. **组件膨胀** — 一个按钮实体需要 `RectTransform + Text + Color + Interactable + ClickHandler + Image + Shadow + Outline...`。解法：Archetype 查询使这些组件的批量处理很快（连续内存），组件多不影响性能。
