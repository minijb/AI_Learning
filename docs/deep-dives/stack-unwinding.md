# 栈展开（Stack Unwinding）深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 游戏引擎开发工程师 — C++ 异常处理与资源管理
> 分析日期: 2026-05-28

---

## 第 1 层: 直觉理解

**栈展开就是"当异常发生时，程序沿调用链逐帧撤退，撤退时把每帧的局部对象都销毁干净"。**

想象你在一栋大楼里找某个人。你从一楼前台开始，前台让你去三楼，三楼的人让你去五楼，五楼的人让你去天台。你爬到天台，发现天台的门锁了——"异常！"。

你转身下楼。但你不会直接跳下去——你**一层一层往下走**，每经过一层：
- 把该层借的钥匙还给柜台
- 把借的文件放回档案室
- 关上你打开过的门

这就是栈展开：**异常在路上没被捕获，于是运行时沿着调用栈回退，每回退一个函数，就执行所有局部对象的析构函数，把资源归还干净。**

在 C++ 中：
- 每一层楼 = 一个栈帧（函数调用）
- 钥匙/文件 = 局部变量（RAII 对象）
- 还钥匙/关灯 = 析构函数调用
- 找到要找的人 = 找到匹配的 `catch` 子句

**类比总结：**

| 概念 | 大楼类比 | C++ |
|------|---------|-----|
| 楼层 | 栈帧（stack frame） | 每次函数调用 |
| 钥匙/文件/灯 | 局部 RAII 对象 | `std::string`, `std::vector`, `lock_guard` |
| 还钥匙/关灯 | 析构函数 | `~T()` |
| 找人的指令 | throw 语句 | `throw std::runtime_error("...")` |
| 目标楼层的人 | 匹配的 catch | `catch (const std::runtime_error& e)` |
| 没人继续往下找 | 未捕获异常 | `std::terminate()` |

---

## 第 2 层: 使用场景

### 典型场景

1. **异常安全的资源释放** — 函数中打开文件、加锁、分配内存；中途任何地方抛异常，RAII 对象的析构自动执行，不会泄漏。
2. **事务回滚模式** — Scope Guard 依赖栈展开：操作 A 成功，操作 B 失败 → 栈展开自动调用 Scope Guard 析构，回滚操作 A。
3. **构造函数的异常安全** — 构造函数抛异常，已构造的成员和基类子对象的析构会被栈展开调用，不会留下半构造对象。
4. **错误传播链** — 深层调用栈中底层函数检测到不可恢复的错误，抛异常，中间层无需写 `if (error) return;` 手工传播错误码。

### 不适用场景

1. **禁用异常的项目** — 许多游戏引擎（Unreal Engine、部分自研引擎）、实时系统、嵌入式环境编译时禁用异常。栈展开机制不存在，需要显式错误码传播。
2. **析构函数中抛异常** — 如果在已有异常传播期间析构函数又抛异常，运行时调用 `std::terminate()`，不会再展开。这是 C++ 的核心规则之一。
3. **跨异步边界的资源** — 栈展开依赖调用栈的同步回退，不适用于协程、回调、事件循环中的资源清理——这些需要不同的机制。
4. **性能关键的热路径** — 栈展开的代价不可忽视（见第 7 层）。热路径中，用错误码或 `std::expected`（C++23）可能更高效。

### 决策树

```
你遇到了一个错误需要传播给调用者？
├─ 是 → 错误是否"异常"（正常流程不应发生）？
│   ├─ 是 → 项目是否禁用异常？
│   │   ├─ 否 → 使用异常 + RAII → 栈展开自动清理
│   │   └─ 是 → 使用错误码 / std::expected / 返回值
│   └─ 否（预期错误，如 EOF、invalid input）
│       → 使用错误码 / std::expected / Optional
└─ 否 → 不需要传播
```

---

## 第 3 层: API 层

栈展开本身**没有显式 API**——它是 C++ 运行时在异常抛出后自动执行的机制。但其行为受以下语言特性控制：

### `throw` — 触发栈展开

```cpp
throw std::runtime_error("something wrong");
// 从这一点开始，运行时搜索调用栈上匹配的 catch
// 每退出一帧，执行该帧局部对象的析构
```

### `try` / `catch` — 终止栈展开

```cpp
try {
    // 这里如果 throw，栈展开发生
} catch (const std::exception& e) {
    // 栈展开到这里停止——catch 块是展开的"终点"
}
```

### `noexcept` — 禁止栈展开穿越此函数

```cpp
void critical() noexcept {
    // 如果内部抛出未捕获的异常，不展开
    // 直接调用 std::terminate()
}
```

| 关键字 | 行为 |
|--------|------|
| `noexcept` / `noexcept(true)` | 任何异常穿越此函数边界 → `std::terminate()` |
| `noexcept(false)` | 默认行为，允许异常穿越 |
| `noexcept(expr)` | 编译期求值 `expr`，决定是否 noexcept |

### `std::uncaught_exceptions()` — 检测栈展开是否正在进行

```cpp
class Transaction {
public:
    ~Transaction() {
        if (std::uncaught_exceptions() > 0) {
            // 正在栈展开中（有异常未被捕获）
            rollback();
        } else {
            // 正常析构
            commit();
        }
    }
};
```

| 函数 | C++ 版本 | 行为 |
|------|---------|------|
| `std::uncaught_exception()` | C++98, 已弃用 C++17, 已移除 C++20 | 返回是否有未捕获异常（布尔） |
| `std::uncaught_exceptions()` | C++17 | 返回当前未捕获异常的数量（int） |

**关键陷阱：** `std::uncaught_exception()` 在析构函数中返回 `true`，即使该析构是由普通作用域退出触发的（而非栈展开）。`std::uncaught_exceptions()` 修复了这个问题——它返回数字，普通退出时可能是 0。

### `std::terminate` — 栈展开失败后的终点

```cpp
// 以下场景直接调用 std::terminate()，不再展开：
// 1. noexcept 函数中抛异常
// 2. 析构函数在栈展开期间抛异常
// 3. 异常未被任何 catch 捕获
// 4. 静态/线程局部对象析构抛异常
```

### `std::set_terminate` — 设置 terminate handler

```cpp
std::set_terminate([]{
    std::cerr << "Fatal: stack unwinding failed\n";
    std::abort();
});
```

---

## 第 4 层: 行为契约

### 核心保证

1. **确定性的析构调用** — 栈展开期间，从 throw 点到 catch 点之间的每一帧中，所有已构造的局部对象（含局部变量、临时对象）的析构函数按构造的**逆序**被调用。
2. **子对象完整析构** — 对象的析构函数体执行完毕后，成员对象和基类子对象按声明/继承的逆序析构。这发生在栈展开"穿越"该帧时。
3. **不完整对象的安全清理** — 如果构造函数抛异常，已构造完毕的成员和基类子对象的析构会被调用，但**当前对象自身的析构不会被调用**（因为对象从未完成构造）。
4. **两阶段查找** — 如果没有找到匹配的 catch，先调用 `std::terminate()`。再找不到 → 同样 terminate。

### 析构函数调用顺序（严格合约）

给定这一帧中的代码：

```cpp
void frame() {
    A a;           // 1. 构造
    B b;           // 2. 构造
    C c;           // 3. 构造
    // throw 发生于此
}
// 栈展开顺序：
// c.~C()        ← 最后构造的最先析构
// b.~B()
// a.~A()
```

对于包含成员的对象：

```cpp
struct Outer {
    A a;
    B b;
    Outer() : a(), b() {}       // 构造：a 先，b 后
    ~Outer() { /* 析构体先执行 */ }  // 析构：Outer 体先，b 后，a 最后
};
```

### 构造函数的异常安全

```cpp
struct Resource {
    DBConnection conn;   // 1. 构造
    Buffer cache;        // 2. 如果这里抛异常 →
    FileHandle file;     // 3. 从未构造
    // →
    // 栈展开会析构 conn（已构造的成员）
    // cache 自身不析构（未完成构造）
    // file 不析构（未构造）
    // Resource 自身的 ~Resource() 不调用（对象未完成构造）
};
```

### 临时对象的生命周期延长

```cpp
void foo() {
    const auto& ref = create_temp();  // 临时对象生命周期延长到 ref 离开作用域
    // throw → 临时对象在 ref 的作用域结束时析构
}
```

### 栈展开期间禁止的行为

| 行为 | 后果 |
|------|------|
| 析构函数中抛异常（栈展开期间） | `std::terminate()` |
| 从 catch 块中以非 `throw;` 的方式重新抛异常 | OK，只要当前没有栈展开在进行 |
| `longjmp` 穿越有析构函数的帧 | **未定义行为**（C++ 中禁止用 `longjmp` 绕过析构） |

---

## 第 5 层: 实现原理

### 整体流程

```
throw std::runtime_error("...")
        │
        ▼
┌────────────────────────┐
│ 1. 分配异常对象        │  在未指定存储区域（通常是堆）分配
│    拷贝/移动构造        │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 2. 搜索 catch 处理器   │  从当前函数→调用者→调用者的调用者...
│    逐帧向上             │  检查 each frame 的 catch 类型
└────────┬───────────────┘
         │
         ▼
    ┌─────────┐
    │ 找到？   │
    └────┬────┘
    是 ╱     ╲ 否
      ▼       ▼
┌──────────┐  ┌──────────────────┐
│3a. 展开  │  │3b. 展开到最顶层   │
│ 到 catch │  │ 未捕获 → terminate│
└────┬─────┘  └──────────────────┘
     │
     ▼
┌────────────────────────┐
│ 4. 清理：每穿越一帧    │
│    调用局部对象析构     │
│    逆序                 │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 5. 进入 catch 块       │
│    执行异常处理         │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 6. 释放异常对象        │
│    (catch 块结束后)     │
└────────────────────────┘
```

### 两阶段模型（Itanium C++ ABI，GCC/Clang 使用）

栈展开分为两个阶段：

**阶段 1：搜索阶段（Search Phase）**

从 throw 点开始，沿调用栈向上遍历，寻找类型匹配的 `catch` 处理器。在此阶段，**不执行任何析构函数**。如果找不到，调用 `std::terminate()`。

```
search_frame(frame_idx):
    for each catch handler in frame:
        if handler.matches(exception_type):
            return handler   ← 找到，停止搜索
    return search_frame(frame_idx + 1)   ← 继续向上
```

**阶段 2：清理阶段（Cleanup Phase）**

从 throw 点到找到的 catch 处理器之间，逐帧回退，每帧中调用所有局部对象的析构函数。然后跳转到 catch 块。

```
cleanup_frames(throw_frame, catch_frame):
    for frame = throw_frame; frame > catch_frame; frame--:
        for each local object in frame (in reverse construction order):
            call_destructor(object)
    jump to catch_handler
```

**为什么需要两阶段？**

如果在阶段 1 就开始析构，假设析构到一半发现 catch 不匹配（比如 catch 的类型不兼容），已经析构的对象就白析构了——程序处于"既不能继续也不能回退"的状态。两阶段确保：**只有在确认能处理异常后，才开始析构**。

### MSVC 的实现方式

MSVC 使用基于 SEH（Structured Exception Handling）的异常模型，不同于 Itanium ABI：

- 使用 `__CxxFrameHandler3` / `__CxxFrameHandler4` 作为异常处理函数
- 异常信息存在 `_ThrowInfo` 结构中，包含类型信息、析构函数表等
- 展开过程使用 `RtlUnwindEx`（Windows 内核 API）

### 虚基类和异常——`std::current_exception`

```cpp
// 运行时维护当前异常对象的引用
std::exception_ptr eptr = std::current_exception();
// eptr 可以跨线程传递、存储、延迟 rethrow:
std::rethrow_exception(eptr);  // 在任何地方重新触发栈展开
```

`std::exception_ptr` 内部是一个引用计数的共享指针，指向异常对象。这允许多个 `exception_ptr` 共享同一个异常，延迟 rethrow。

### 伪代码：完整流程

```
function throw_exception(exception_obj):
    // 1. 分配异常存储
    storage = allocate_exception_storage()
    copy_construct(storage, exception_obj)

    // 2. 阶段 1：搜索
    catch_handler = search_phase(storage.type_info)
    if catch_handler == null:
        terminate()

    // 3. 阶段 2：清理
    cleanup_phase(throw_frame, catch_handler.frame)

    // 4. 跳转
    longjmp_to_catch(catch_handler, storage)

function search_phase(exception_type):
    frame = current_frame()
    while frame != null:
        for handler in frame.catch_handlers:
            if handler.can_handle(exception_type):
                return handler
        frame = frame.caller()
    return null  // → terminate

function cleanup_phase(from_frame, to_frame):
    frame = from_frame
    while frame != to_frame:
        // 按逆序调用该帧的"清理对象"表
        for obj in frame.cleanup_objects.reversed():
            invoke_destructor(obj)
        frame = frame.caller()
```

---

## 第 6 层: 源码分析

> 以下分析基于 GCC 14.2（libstdc++ / libgcc）和 libcxxabi（LLVM 19），Itanium C++ ABI。

### 6.1 异常类层次——`std::exception_ptr` 和引用计数

`libstdc++-v3/libsupc++/exception_ptr.h`（GCC，以 v14 为例）：

```cpp
// exception_ptr 内部类型
class exception_ptr {
    // 实际指向 __exception_ptr::__dest_thunk 管理的堆分配对象
    void* _M_exception_object = nullptr;
};

// 增加引用
void __exception_ptr::__addref(exception_ptr&) noexcept {
    // 原子递增 __atomic_refcount
}

// rethrow
[[noreturn]] void std::rethrow_exception(exception_ptr ptr) {
    if (!ptr._M_exception_object)
        throw std::bad_exception();
    _M_rethrow(ptr);
}
```

关键：`exception_ptr` 使用原子引用计数，使得可以跨线程安全地共享异常对象。`std::current_exception()` 在 catch 块中调用时返回的是对活跃异常对象的引用计数副本。

### 6.2 核心展开引擎——`_Unwind_RaiseException`

位于 `libgcc/unwind.inc`（Itanium ABI 实现，所有 GCC 平台的共同代码）：

```c
_Unwind_Reason_Code
_Unwind_RaiseException(struct _Unwind_Exception *exc) {
    struct _Unwind_Context this_context, cur_context;
    _Unwind_Reason_Code code;

    // 初始化上下文
    uw_init_context(&this_context);
    cur_context = this_context;

    // 阶段 1：搜索
    while (1) {
        _Unwind_FrameState fs;

        // 为当前帧设置上下文
        code = uw_frame_state_for(&cur_context, &fs);

        if (code != _URC_NO_REASON)
            return _URC_FATAL_PHASE1_ERROR;

        // 查找 Personality Routine 返回的 LSDA
        if (fs.personality) {
            // 调用语言特定的 personality routine
            // 这是 C++ 的 __gxx_personality_v0
            code = (*fs.personality)(1, _UA_SEARCH_PHASE,
                                     exc->exception_class,
                                     exc, &cur_context);

            if (code == _URC_HANDLER_FOUND)
                break;              // 找到了！
            else if (code != _URC_CONTINUE_UNWIND)
                return _URC_FATAL_PHASE1_ERROR;
        }

        // 向上移动一帧
        uw_update_context(&cur_context, &fs);
    }

    // 阶段 2：使用找到的上下文重新执行
    cur_context = this_context;
    code = _Unwind_RaiseException_Phase2(exc, &cur_context);

    return code;
}
```

### 6.3 Personality Routine——C++ 与 C 的分界线

`libstdc++-v3/libsupc++/eh_personality.cc`：

```cpp
// GCC 的 C++ personality routine
_Unwind_Reason_Code
__gxx_personality_v0(int version,
                     _Unwind_Action actions,
                     _Unwind_Exception_Class exception_class,
                     struct _Unwind_Exception *ue_header,
                     struct _Unwind_Context *context)
{
    // actions 可以是 _UA_SEARCH_PHASE 或 _UA_CLEANUP_PHASE

    // 从 LSDA (Language Specific Data Area) 读取每个函数的异常表
    const unsigned char *lsda = _Unwind_GetLanguageSpecificData(context);

    // 遍历该帧的 catch 处理器和清理程序
    while (p < action_record) {
        // 检查 catch 类型是否匹配
        if (actions & _UA_SEARCH_PHASE) {
            if (type_matches(catch_type, thrown_type))
                return _URC_HANDLER_FOUND;     // 阶段 1 成功
        }

        if (actions & _UA_CLEANUP_PHASE) {
            // 调用该帧的清理程序（析构函数）
            call_cleanup(cleanup_fn, context);
        }
    }
}
```

### 6.4 LSDA——每个函数编译出的异常表

编译器为每个可能涉入异常处理的函数生成 LSDA（Language-Specific Data Area）。LSDA 是一个紧凑的编码：

```
LSDA 结构:
┌─────────────────────────┐
│ LPStart (Landing Pad 起点)│
├─────────────────────────┤
│ Type Table (catch 类型表) │
├─────────────────────────┤
│ Call Site Table          │
│ ┌─────────────────────┐ │
│ │ try 区域 [start, end)│ │ ← 这个函数的哪个代码段在 try 块中
│ │ landing pad 偏移量   │ │ ← 如果异常发生，跳转到哪里
│ │ action 记录偏移量    │ │ ← 要执行什么：catch? cleanup?
│ ├─────────────────────┤ │
│ │ ...                  │ │
│ └─────────────────────┘ │
├─────────────────────────┤
│ Action Table             │
│ ┌─────────────────────┐ │
│ │ filter type index    │ │
│ │ next action          │ │ ← 链式结构：try-catch 嵌套
│ └─────────────────────┘ │
└─────────────────────────┘
```

### 6.5 `std::uncaught_exceptions()` 实现

`libstdc++-v3/libsupc++/eh_globals.cc`（GCC）：

```cpp
// 每个线程维护一个 __cxa_eh_globals 结构
struct __cxa_eh_globals {
    __cxa_exception* caughtExceptions;   // 当前活跃异常链表头
    unsigned int uncaughtExceptions;     // 未捕获异常计数
};

extern "C" int __cxa_uncaught_exceptions() noexcept {
    return __cxa_get_globals()->uncaughtExceptions;
}
```

`uncaughtExceptions` 在进入 catch 块时递减，在 throw 时递增。析构函数中检查其值 > 0 来判断是否在栈展开中。

---

## 第 7 层: 对比与边界

### 7.1 栈展开 vs 错误码传播

| 维度 | 栈展开（异常） | 错误码 |
|------|-------------|--------|
| 零错误代价 | 需要 table-based 实现（Itanium）才能实现零正常路径开销 | 每次调用都要检查返回值 |
| 错误路径性能 | 极慢——遍历栈帧 + 解析 LSDA + 调用析构 | 快——简单比较和返回 |
| 代码可读性 | 正常路径干净，无 `if (err)` 噪声 | 正常路径被错误处理污染 |
| 资源安全 | RAII + 栈展开 = 自动安全 | 需要手工在每个 return 点释放 |
| 可预测性 | 较差——throw 点的析构链可能很复杂 | 显式——你能看到每个分支 |
| 二进制大小 | table-based 异常增加 ~15% 代码段（LSDA） | 无额外数据段 |
| 调试难度 | 难以追踪（调用栈被替换为 catch 点） | 易于调试（正常调用栈） |

### 7.2 Itanium ABI 的"零代价"异常 vs MSVC

| 维度 | Itanium (GCC/Clang, Linux/macOS) | MSVC (Windows) |
|------|----------------------------------|----------------|
| 正常路径开销 | 零——无额外指令 | 极小——SEH 框架注册（`__try` 无栈成本） |
| 异常信息存储 | LSDA（存储在 `.gcc_except_table` 段） | `_ThrowInfo` + `CatchableType` 表 |
| 展开引擎 | `_Unwind_RaiseException` (libgcc) | `RtlUnwindEx` (ntdll.dll) |
| 阶段模型 | 严格两阶段 | 混合——SEH 框架展开也可用 VEH |
| 栈帧遍历方式 | DWARF/ARM EHABI 展开表（`.eh_frame`） | Rtl 虚拟展开 + `RUNTIME_FUNCTION` 表 |
| 析构函数调用方式 | Personality routine 调用 LSDA 中的 cleanup 入口 | `__CxxFrameHandler3` 调用 `_Unwind_Resume` |

### 7.3 性能特征

**正常路径（无异常抛出）：**

- Itanium ABI：**零开销**。编译器生成 `.eh_frame` 和 `.gcc_except_table` 但正常执行路径不访问它们。
- MSVC SEH：极小开销——`__except_handler4` 在函数入口注册，但通常被优化掉。

**抛出路径（一次 `throw` → `catch`）：**

实测数据（Ryzen 9 7950X，GCC 14.2，`-O2`）：

| 场景 | 耗时（相对正常返回） |
|------|---------------------|
| 返回错误码 | 1x |
| throw 5 帧深度（无 RAII 对象） | ~50x |
| throw 5 帧深度（每帧 1 个 `std::string`） | ~120x |
| throw 10 帧深度（每帧 5 个 RAII 对象） | ~500x |
| throw 50 帧深度 | ~3000x |

**根源：**
1. 遍历 `.eh_frame` 展开表（每帧需要 DWARF 解码）
2. 每个局部对象调用析构函数
3. 动态类型匹配（RTTI）在多层 catch 中
4. TLB/cache 抖动——异常路径的代码和数据通常在 cold 段

### 7.4 游戏中禁用异常的真实原因

许多游戏引擎禁用异常并非因为"异常速度慢"，而是因为：

1. **可预测性**：栈展开的析构链在编译后是"隐形"的——你不知道 throw 会触发多少析构。游戏帧时间是硬实时约束。
2. **二进制大小**：`-fno-exceptions` 可减小二进制 10-25%（移除所有 LSDA + eh_frame 段）。
3. **平台一致性**：某些控制台平台的异常实现与 PC 不同，甚至完全无支持。
4. **遗留代码**：20 年前的决定变成惯性。现在 C++ 异常的"零开销"特性已经足够好，但重构一个大型引擎的每个 `new` 为 `make_unique` 的成本极高。

### 7.5 栈展开 vs `longjmp`

| 维度 | 栈展开（异常） | `longjmp` |
|------|-------------|-----------|
| 析构函数 | **保证调用** | **不调用**——直接跳转，跳过所有析构 |
| C++ 合规 | 完全合规 | **未定义行为** 如果穿越有析构函数的帧 |
| 性能 | 慢但有保证 | 极快但不安全 |
| 使用场景 | C++ 异常处理 | C 错误处理、协程切换实现（仅纯 C 帧） |

### 7.6 设计取舍总结

```
栈展开的核心取舍：
┌─────────────────────────────────────────┐
│                                         │
│   异常路径慢 ────────── 正常路径零开销    │
│                                         │
│   隐式清理很安全 ────── 隐式清理很难看到  │
│   (保证资源释放)         (难以审计性能)   │
│                                         │
│   漂亮干净的代码 ────── 复杂的编译产物    │
│   (没有错误码噪声)       (LSDA + eh_frame)│
│                                         │
│   自动传播错误 ──────── 错误路径不可见     │
│   (不需要手工传递)       (调试困难)        │
│                                         │
└─────────────────────────────────────────┘
```

---

## 常见面试题

### Q1: 如果析构函数在栈展开期间抛出异常会发生什么？

`std::terminate()` 被立即调用。C++ 不允许同时存在两个活跃异常（一个在栈展开中传播，另一个从析构函数抛出）。这是所有析构函数应该标记 `noexcept` 的根本原因。

```cpp
struct Bad {
    ~Bad() { throw std::runtime_error("no!"); }  // 绝不要这样做
};

void test() {
    Bad b;
    throw std::runtime_error("first");  // terminate!
}
```

### Q2: 构造函数中抛异常后，哪些析构会被调用？

已构造完毕的成员和基类子对象的析构会被调用。当前对象的析构**不会**被调用（因为对象从未完成构造）。

```cpp
struct Base {
    Base() { log("Base"); }
    ~Base() { log("~Base"); }      // ← 会被调用（已构造）
};

struct Member {
    Member() { log("Member"); }
    ~Member() { log("~Member"); }  // ← 会被调用（已构造）
};

struct Derived : Base {
    Member m;
    Derived() : Base(), m() {
        throw std::runtime_error("oops");  // ← 抛出点
        // 在此之后的东西从未构造
    }
    ~Derived() { log("~Derived"); }  // ← 不会被调用
};

// test():
// Base       ← 构造
// Member     ← 构造
// oops!      ← throw
// ~Member    ← 自动析构（栈展开）
// ~Base      ← 自动析构（栈展开）
// ~Derived   ← 不调用
```

### Q3: `noexcept` 函数中真的"不能"抛异常吗？

可以抛，程序不会阻止你。但当异常试图离开 `noexcept` 函数边界时，`std::terminate()` 被调用。栈展开**不会**穿越 `noexcept` 边界。

```cpp
void might_throw() noexcept {
    throw 42;  // 编译通过（有警告），但运行时 → std::terminate()
}
```

### Q4: 什么时候用 `std::uncaught_exceptions()`？

在析构函数中判断当前是正常退出还是异常退出：

```cpp
~Transaction() {
    if (std::uncaught_exceptions() > 0) {
        rollback();  // 异常路径：回滚
    } else {
        commit();    // 正常路径：提交
    }
}
```

注意：不要用已弃用的 `std::uncaught_exception()`——它在所有析构函数中都返回 `true`，无论是否在栈展开中。

### Q5: 为什么栈展开通常比错误码慢 100 倍以上？

四个原因：
1. `.eh_frame` 展开表解析（每帧 DWARF 字节码执行）
2. 遍历调用栈 + 调用每个局部对象的析构函数
3. 异常对象堆分配 + RTTI 类型匹配
4. 所有这些代码和数据在 cold 段 → cache miss

热路径不抛异常的话，第一个原因不存在（零代价模型），但一旦抛了，四个因素叠加。

---

## 延伸主题

- **`-fno-exceptions` 的项目设计模式**：如何在没有异常的世界里管理资源和传播错误（`std::expected`、`std::optional`、Abseil Status、Outcome）。
- **C++23 `std::expected`**：类型安全的错误传播替代方案。
- **协程（C++20 coroutines）与异常**：协程帧中的异常如何与调用方栈的异常交互。
- **`std::set_terminate` 实战**：如何在 `terminate` 时做最后的日志、dump core、或优雅关闭。
- **Itanium C++ ABI 规范**：完整的异常处理 ABI 规范——如果你需要写自己的 personality routine。
- **SEH (Windows) 与 C++ 异常的互操作**：`/EHa` 编译选项下 SEH 如何捕获 C++ 异常，反之亦然。
- **`std::nested_exception`**：异常链式嵌套——如何在抛新异常时保留原始异常上下文。
