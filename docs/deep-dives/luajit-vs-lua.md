# LuaJIT vs Lua 深度对比剖析

> 深度等级: 第 7 层
> 关联学习计划: Kimi_Agent_游戏引擎学习路线 (stage01_foundation, stage04_engine_systems)
> 分析日期: 2026-06-02

---

## 第 1 层: 直觉理解

**Lua** 是 PUC-Rio（巴西天主教大学）设计的轻量嵌入式脚本语言。它的标准实现（常称 PUC Lua）是一个用纯 ANSI C 写的解释器，编译后体积约 200KB，能在几乎所有平台上运行。

**LuaJIT** 是 Mike Pall 一人为 Lua 写的 Just-In-Time 编译器。它兼容 Lua 5.1 语法，但内部是一个完全不同的野兽——它把 Lua 代码的热路径直接编译成 x86/ARM/MIPS 原生机器码。

**类比**: Lua (PUC) 像一个万能翻译官，到哪里都能工作，但逐句翻译需要时间。LuaJIT 像一个同声传译专家——第一次听时做笔记（profile），听到重复模式（热循环）就提前把整段话翻译好写在小纸条上（编译为机器码），下次直接念纸条，速度接近母语。代价是这个专家只精通某些"方言"（Lua 5.1），后来的新表达方式他不会。

---

## 第 2 层: 使用场景

### Lua (PUC Lua 5.4/5.5) 适用场景

- **嵌入式脚本**：你的 C/C++ 应用需要脚本扩展能力，但不需要极致性能。
- **跨平台可移植性优先**：目标包括微控制器、嵌入式设备、奇怪架构。
- **需要最新语言特性**：Lua 5.4 引入的整数子类型、const 变量、to-be-closed 变量、分代 GC；Lua 5.5 引入的全局变量声明、60% 大数组内存节省。
- **Neovim 插件开发**：Neovim 在解释模式下使用 Lua（虽然也兼容 LuaJIT）。
- **你控制宿主应用且能随时重编译**：Lua 版本升级通常需要重新编译 C 宿主。

### LuaJIT 适用场景

- **高性能网络中间件**：OpenResty（Nginx + LuaJIT）、Kong API Gateway、Apache APISIX。
- **游戏引擎脚本**：LÖVE2D、Defold、Solar2D（Corona）。
- **实时数据处理**：包处理、日志解析、流式计算。
- **需要通过 FFI 直接调用 C 库**：无需写 C 绑定代码，3 行 FFI 声明即可调用任意 C 函数。
- **你对性能有硬性要求且能接受 Lua 5.1 方言**。

### 不适用场景（反面教材）

- 用 LuaJIT 来跑一个只需要启动时执行一次的配置脚本——JIT 编译的开销大于收益。
- 用 PUC Lua 来做高频交易的数据处理——你的延迟预算会被解释器吃完。
- 假设 LuaJIT 能跑最新的 Lua 5.4/5.5 代码——`goto` 关键字、整数类型、const 变量等都会导致语法错误或行为差异。

### 决策树

```
需要调用 C 库且不想写绑定？
  ├── 是 → LuaJIT（FFI 是无替代品的杀手特性）
  └── 否 → 继续
需要极致性能（接近 C 的速度）？
  ├── 是 → LuaJIT
  └── 否 → 继续
需要 Lua 5.2+ 的语言特性？
  ├── 是 → PUC Lua 5.4+ 或 Luau
  └── 否 → 继续
需要跑在微控制器 / 奇怪架构上？
  ├── 是 → PUC Lua
  └── 否 → LuaJIT（性能默认更好）
```

---

## 第 3 层: 版本与特性矩阵

### 语言标准对应关系

| 特性 | PUC Lua 5.1 | PUC Lua 5.4 | PUC Lua 5.5 | LuaJIT 2.1 |
|------|:-----------:|:-----------:|:-----------:|:----------:|
| 基础语义 | ✅ | ✅ | ✅ | ✅ (5.1 兼容) |
| `goto` / `::labels::` | ❌ | ✅ | ✅ | ✅ (从 5.2 移植) |
| `_ENV` 环境系统 | ❌ | ✅ | ✅ | ❌ (破坏 ABI) |
| 整数子类型 (`//` 运算符) | ❌ | ✅ | ✅ | ❌ |
| `const` 局部变量 | ❌ | ✅ | ✅ | ❌ |
| to-be-closed 变量 | ❌ | ✅ | ✅ | ❌ |
| 分代 GC | ❌ | ✅ | ✅ | ❌ (增量标记-清除) |
| 全局变量声明 | ❌ | ❌ | ✅ | ❌ |
| for 循环变量只读 | ❌ | ❌ | ✅ | ❌ |
| 位运算 (`&`, `\|`, `~`) | ❌ | ✅ | ✅ | ✅ (通过 `bit.*` 库) |
| UTF-8 支持 | ❌ | ✅ (utf8 库) | ✅ | 部分 (源码解析) |
| 16 进制浮点字面量 | ❌ | ✅ | ✅ | ✅ |
| `\z` 字符串转义 | ❌ | ✅ | ✅ | ✅ |
| `\u{XXX}` Unicode 转义 | ❌ | ✅ | ✅ | ✅ |

### LuaJIT 独有扩展

| 特性 | 说明 |
|------|------|
| **FFI Library** | 从纯 Lua 调用任意 C 函数、操作 C 数据结构 |
| **bit.\* 库** | 内建位运算（`bit.band`, `bit.bor`, `bit.bxor` 等） |
| **jit.\* 库** | JIT 编译器控制（`jit.on()`, `jit.off()`, `jit.flush()` 等） |
| **table.new(narr, nhash)** | 预分配大小的 table，避免渐进式扩容 |
| **table.clear(tab)** | 清空 table 但保留已分配的数组/哈希空间 |
| **string.dump 剥离模式** | 生成无调试信息的字节码（`string.dump(f, true)`） |
| **Fully Resumable VM** | 协程可在 `pcall`、迭代器、元方法中 yield |
| **64-bit 文件偏移** | `io.*` 函数支持 >2GB 文件 |
| **增强 PRNG** | Tausworthe 算法，周期 2²²³，优于 ANSI `rand()` |
| **C++ 异常互操作** | GCC/Clang/MSVC 下与 C++ 异常完全互操作 |
| **集成 Profiler** | `-jp` 命令行选项和 `jit.profile` API |

---

## 第 4 层: 行为契约

### 执行模型

| 维度 | PUC Lua | LuaJIT |
|------|---------|--------|
| 执行单元 | 基于寄存器的字节码解释器 | 解释器 + Trace Compiler |
| JIT 触发 | 无 | 热循环计数归零时触发 |
| 编译产物 | 字节码（平台无关） | 原生机器码（平台相关） |
| 退出编译 | N/A | Guard 失败 → Side Trace → 解释器回退 |
| 尾调用优化 | ✅ (语法保证) | ✅ (JIT 可进一步优化) |

### 垃圾回收

| 维度 | PUC Lua 5.4 | PUC Lua 5.5 | LuaJIT 2.1 |
|------|:-----------:|:-----------:|:----------:|
| 算法 | 分代 GC | 分代 GC + 增量 Major GC | 增量标记-清除 |
| Stop-the-world | 仅在 Minor GC | 已消除（增量 Major） | 增量，停顿短 |
| `collectgarbage("step")` | ✅ | ✅ | ✅ |
| `collectgarbage("generational")` | ✅ | ✅ | ❌ |
| `collectgarbage("incremental")` | ✅ | ✅ | ✅ (默认) |

**LuaJIT GC 的特性**：LuaJIT 2.1 使用增量标记-清除，但实现上与 PUC Lua 的增量 GC 不同——它是为低延迟设计的，步进粒度更细。LuaJIT 还有 `LJ_GC64` 模式（64 位平台上使用 64 位 GC 对象引用），可支持更大的堆。

### 数值系统 (关键差异！)

```
PUC Lua 5.3+:  所有数字默认有两种子类型
               - integer (64-bit signed)
               - float   (64-bit IEEE-754 double)
               # 运算符返回整数长度
               // 运算符执行整数除法

LuaJIT 2.1:    所有数字默认是 double (64-bit IEEE-754)
               - 通过 FFI 可使用 int64_t / uint64_t
               - # 运算符返回浮点数长度
               - 没有 // 运算符（使用 math.floor(a/b) 代替）
               - tonumber() 可解析 "0x", "0b", 十六进制浮点数
```

**数值差异导致的坑**：

```lua
-- PUC Lua 5.3+
local x = 9007199254740993  -- 超过 2^53，作为 integer 精确存储
print(x)  --> 9007199254740993

-- LuaJIT 2.1
local x = 9007199254740993  -- 存入 double，精度丢失
print(x)  --> 9.007199254741e+15  (近似值)
```

### 线程安全

两个实现都是**单线程执行模型**。Lua State 不是线程安全的——每个 `lua_State` 必须在同一时间只能被一个线程访问。多线程方案：

- PUC Lua：多 `lua_State` + 消息传递（如 `lua-lanes`）
- LuaJIT：同上 + FFI 可以调用 C 的线程原语

### 内存限制

| 维度 | PUC Lua | LuaJIT (non-LJ_GC64) | LuaJIT (LJ_GC64) |
|------|---------|----------------------|-------------------|
| 最大堆大小 | ~2GB (取决于 OS) | ~1-2GB (32 位 GC 引用) | ~128TB (理论上) |
| 单个字符串最大 | ~2GB | ~2GB | ~2GB |
| Trace 数量上限 | N/A | ~1000 (可配置) | ~1000 (可配置) |

---

## 第 5 层: 实现原理

### PUC Lua VM 架构

```
源代码 → 词法/语法分析 → 字节码 → 基于寄存器的解释器
                                    ↓
                    ┌─────── 每个指令 = opcode + operands
                    │        例如: ADD R0 R1 R2  (R0 = R1 + R2)
                    │        FORLOOP R0 target_PC
                    │        GETTABLE R0 R1 R2  (R0 = R1[R2])
                    │
                    └─────── 主循环伪代码:
                             while (true) {
                                 Instruction i = *pc++;
                                 switch (GET_OPCODE(i)) {
                                     case OP_ADD:
                                         ra = RA(i); rb = RB(i); rc = RC(i);
                                         setobjs2s(L, ra, luaV_add(L, rb, rc));
                                         break;
                                     case OP_CALL: ...
                                 }
                             }
```

PUC Lua 的字节码是 32-bit 定长指令，包含 6-bit opcode + 3 个操作数字段。解释器是一个巨大的 C `switch` 语句（用 `goto` 实现 threaded code 以提升分支预测）。

### LuaJIT VM 架构

LuaJIT 有两层执行路径：

```
源代码 → 字节码 → 解释器（手写汇编！）
                ↓   ↓   ↓   (热计数递减)
                │   │   └── hotcount == 0 → 进入 JIT 编译
                │   └────── hotcount > 0  → 继续解释
                └────────── JIT 编译入口: trace_start()

JIT 编译流水线:
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Trace 录制    │ → │ IR 生成+优化  │ → │ 汇编生成     │
│ (lj_record.c) │   │ (lj_opt_*.c) │   │ (lj_asm.c)   │
└──────────────┘   └──────────────┘   └──────────────┘
      ↓                    ↓                    ↓
  记录每个字节码        SSA 形式 IR         原生机器码
  的实际执行路径       + FOLD 引擎          + 寄存器分配
  (Guard 插入)         常量折叠/代数简化     (线性扫描)
```

#### Trace Compiler 工作流

**Phase 1 — 热路径检测**：每个字节码指令关联一个 `hotcount`。每执行一次递减，归零时触发 JIT：

```
hotcount 初始值: JIT_P_hotloop = 56 (循环/函数调用)
                 JIT_P_hotexit = 10 (退出到 side trace)
```

**Phase 2 — Trace 录制**（`lj_record.c`）：解释器进入 "录制模式"，执行的实际控制流路径被记录为 SSA 形式 IR。**每个分支点插入 Guard**——如果后续执行走不同的分支，Guard 失败，退出到解释器或 Side Trace。

```
录制中的关键操作:
- 遇到条件跳转 → 插入 Guard，记录当前走的分支
- 遇到函数调用 → 尝试内联或记录为 "blacklisted"
- 遇到 table 访问 → 记录 key 类型、hash 结果
- 遇到 FFI 调用 → 特殊处理 (lj_ffrecord.c)
- 关键点插入 Snapshot → 退出时恢复解释器状态
```

**Phase 3 — IR 优化**（`lj_opt_fold.c` 等）：FOLD 引擎是 IR 优化的核心。它使用**哈希表匹配 IR 模式**，在 IR 发射时立即应用优化：

```
优化模式示例:
ADD x, 0    → x              (加法单位元消除)
MUL x, 1    → x              (乘法单位元消除)
SUB x, x    → 0              (相同操作数消除)
AND x, x    → x              (幂等性)
NOT NOT x   → x              (双重否定消除)
常量折叠:   ADD 3, 5 → 8    (编译时计算)
CSE:        相同子表达式去重
循环优化:   循环不变量外提 (lj_opt_loop.c)
PHI 节点:   处理循环中的变量版本
```

**Phase 4 — 汇编生成**（`lj_asm.c`）：优化后的 IR 转换为原生机器码。使用**线性扫描寄存器分配**（非图着色，速度快但可能溢出）：

```
IR 指令 → x86/x64/ARM/MIPS 指令序列
- SSA 解构 → 寄存器分配 → 指令选择 → 指令调度 → 代码发射
- 每个 Guard 编译为条件跳转指令
- Snapshot 元数据嵌入指令流中（用于退出时状态恢复）
```

### 核心差异总结

| 层次 | PUC Lua | LuaJIT |
|------|---------|--------|
| 解释器实现 | C 语言 `switch/goto` | 手写汇编 (DynASM 宏) |
| 字节码格式 | 32-bit 定长 | 与 PUC Lua 5.1 兼容但有扩展 |
| 优化策略 | 无运行时优化 | Trace Compiler + FOLD 引擎 |
| 函数调用 | C 调用约定 | 可内联 + Fast Function 快速路径 |
| 表访问 | 哈希查找 | JIT 编译为直接内存访问（类型稳定时） |
| 数值运算 | 每次装箱到 Lua Number | JIT 编译为寄存器中的原生浮点运算 |

---

## 第 6 层: 源码分析

> 引用源码基于 LuaJIT v2.1 (commit `659a6169`)，PUC Lua 5.4.8。

### 6.1 解释器主循环对比

**PUC Lua 5.4 — `lvm.c` 中的 switch-based 解释器**

Lua 5.4 的解释器使用 `switch` dispatch（某些编译选项下可改为 `goto` threaded code）：

```c
// lvm.c (简化)
void luaV_execute(lua_State *L, CallInfo *ci) {
    // ...
    for (;;) {
        Instruction i = *pc++;
        switch (GET_OPCODE(i)) {
            case OP_ADD: {
                TValue *rb = RKB(i);
                TValue *rc = RKC(i);
                // 处理整数和浮点数子类型
                if (ttisinteger(rb) && ttisinteger(rc)) {
                    // 整数加法路径 (5.3+)
                } else {
                    // 浮点数加法路径
                }
                break;
            }
            case OP_CALL: { /* ... */ }
            // ... ~80 个 opcode
        }
    }
}
```

关键观察：每次操作都要检查类型（integer vs float vs string 元方法），分支预测压力大。

**LuaJIT 2.1 — `src/vm_x86.dasc` 中的手写汇编解释器**

LuaJIT 使用 **DynASM**（内嵌在 `vm_*.dasc` 文件中的汇编 DSL，在构建时由 `dynasm.lua` 转换为机器码）：

```asm
;; src/vm_x86.dasc (简化，x86-64 版本)
|->vm_loop:                     ; 主解释器循环入口
|  mov eax, [BASE+PC]           ; 加载下一条指令
|  mov eax, [eax]               ; 取出 32-bit 指令字
|  mov PC, [BASE+PC+8]          ; PC++ (8 字节步进)
|  movzx ecx, ah                ; 提取 opcode (9 bits in LJ)
|  shr eax, 16                  ; 提取操作数 A
|  movzx ebx, al                ; 提取操作数 B
|  jmp [DISPATCH+ecx*8]         ; 通过跳转表 dispatch
|
|.macro ins_ADD                 ; ADD 指令的汇编实现
|  mov edx, [BASE+rb]           ; rb = 操作数B的TValue
|  movsd xmm0, [edx]            ; 加载为 double (LJ 无整数子类型!)
|  mov edx, [BASE+rc]
|  addsd xmm0, [edx]            ; SSE2 浮点加法，单条指令!
|  movsd [BASE+ra], xmm0        ; 存储结果
|  jmp ->vm_loop                ; 回到主循环
|.endmacro
```

关键差异：
- LuaJIT 的 ADD 在解释模式下就假设 `double` 操作数（无类型分支！），通过 SSE2 寄存器直接运算。
- 使用跳转表而非 switch——分支预测更友好。
- 没有整数子类型的复杂分支。

### 6.2 Trace 录制入口

```c
// src/lj_trace.c (LuaJIT v2.1, commit 659a6169)
/* Start a new trace. */
void LJ_FASTCALL lj_trace_start(lua_State *L, BCIns bc)
{
  jit_State *J = L2J(L);
  // 检查：是否已经在录制？JIT 是否被禁用？
  if (J->state != LJ_TRACE_IDLE || J->cur.traceno != 0) return;
  // 分配 trace 编号
  J->cur.traceno = lj_trace_new(J);
  // 设置状态为 "录制中"
  J->state = LJ_TRACE_START;
  // 开始录制...
  lj_record_start(J, bc);
}
```

录制阶段的关键：**每个分支点插入 Guard IR 指令**。Guard 在 IR 中以 `IR_GUARD` 标记，汇编阶段编译为条件跳转：

```
IR 示例：
001  >  int TABL  #1    #0    ; 加载表
002  >  int FLOAD  #2    #0    ; 获取 array 部分大小
003  >  int BGE    #2    #3    ; Guard: 索引 >= 大小? → exit
004     int AREF   #1    #3    ; 数组引用
005     num ALOAD  #4         ; 加载元素 (double)
```

`>` 标记表示 Guard 指令。如果后续执行中索引超出 array 部分（Guard 003 失败），JIT 代码退出回到解释器。

### 6.3 FOLD 引擎核心

```c
// src/lj_opt_fold.c (简化)
/* FOLD 规则表：每个 IR 操作码对应一组简化规则 */
static TRef fold_simplify(jit_State *J, IRIns *ir, TRef left, TRef right)
{
    switch (ir->o) {
    case IR_ADD:
        // x + 0 → x
        if (ir_kval(right)->n == 0) return left;
        // 常量折叠: C1 + C2 → C3
        if (ir_isk(left) && ir_isk(right))
            return lj_ir_knum(J, ir_knum(left)->n + ir_knum(right)->n);
        break;
    case IR_MUL:
        // x * 1 → x
        if (ir_kval(right)->n == 1.0) return left;
        // x * 0 → 0  (注意 NaN!)
        if (ir_kval(right)->n == 0.0 && !LJ_DUALNUM && ir_kval(left)->n != 0.0)
            return right;
        break;
    case IR_BAND:
        // x & 0 → 0
        // x & -1 → x
        // x & x → x (CSE)
        break;
    // ... 数百条规则
    }
    return 0;  // no simplification
}
```

FOLD 引擎利用了 IR 设计的 SSA 特性：每个值只有唯一定义点，使得**公共子表达式消除（CSE）**高效且安全。

### 6.4 FFI 的 JIT 集成

FFI 调用在 JIT 编译时的处理是 LuaJIT 最精妙的设计之一（`src/lj_ffrecord.c`）：

```c
// FFI 函数调用的 Trace 录制（简化）
static void recff_c_call(jit_State *J, CTState *cts, cTValue *tv)
{
    // 1. 解析 C 函数签名（从 ffi.cdef 声明中）
    CType *ct = ctype_raw(cts, tv->id);
    // 2. 为每个参数生成对应的 IR 指令
    for (int i = 0; i < ctype_nparams(ct); i++) {
        // 参数转换: Lua Number → C int/double/...
        emit_ffi_arg(J, ctype_param(ct, i));
    }
    // 3. 发射 CALL 指令（直接调用 C 函数指针，无中间层！）
    emit_ir(J, IR_CALL, ref, ...);
    // 4. 处理返回值转换
    emit_ffi_ret(J, ctype_ret(ct));
}
```

这意味着 JIT 编译后的 FFI 调用**没有虚拟机开销**——直接 `call` 到 C 函数地址，参数在寄存器中传递。

---

## 第 7 层: 对比与边界

### 7.1 性能对比

> 基准数据综合多个公开 benchmark（Lua-Benchmarks、Scimark、API7 测试）。测试环境: AMD FX-8300 / Intel i5。

| Benchmark | PUC Lua 5.4.2 | LuaJIT 2.1 (interp) | LuaJIT 2.1 (JIT on) | 加速比 (JIT vs PUC) |
|-----------|:-------------:|:-------------------:|:-------------------:|:-------------------:|
| 斐波那契 (递归) | 3.69s | 1.52s | 0.81s | **4.6×** |
| 矩阵乘法 500×500 | 8.21s | 2.83s | 0.62s | **13.2×** |
| 字符串拼接 | 0.95s | 0.72s | 0.68s | 1.4× |
| JSON 解析 | 0.42s | 0.31s | 0.29s | 1.5× |
| SciMark (C=100) | — | — | — | **~20×** |
| 纯数值循环 | 2.11s | 0.89s | 0.12s | **17.6×** |

**性能规律**：

- **数值密集型代码**：LuaJIT 的加速最显著（10–50×），因为数值运算直接编译为 SSE/AVX 寄存器操作，零装箱开销。
- **字符串操作**：加速有限（1.2–2×），因为字符串分配和内存复制是瓶颈。
- **表操作**：类型稳定时（同类型 key/value），JIT 可编译为直接内存访问，加速 3-10×；类型不稳定时回退到解释器。
- **FFI 调用**：JIT 编译后**零开销**——直接 `call` 指令，等同于 C 的调用开销。

### 7.2 架构特性对比

| 维度 | PUC Lua | LuaJIT | 说明 |
|------|:-------:|:------:|------|
| **二进制体积** | ~200KB | ~500KB | LJ 包含 JIT 编译器 + 多架构后端 |
| **内存占用 (空闲)** | ~20KB | ~130KB | LJ 预分配 trace/JIT 结构 |
| **启动速度** | 极快 | 快 | LJ 有更多初始化工作 |
| **C API 兼容性** | 标准 | ABI 兼容 Lua 5.1 | C 模块无需重编译 |
| **平台支持** | 几乎所有 | x86/x64/ARM/ARM64/MIPS/PPC | LJ 架构支持有限但覆盖主流 |
| **JIT 架构后端** | N/A | x86/x64, ARM, ARM64, MIPS, PPC | 手写汇编 (DynASM) |
| **可调试性** | 标准调试钩子 | 调试钩子 + JIT 信息 | LJ 在 JIT 代码中可以定位源码行 |

### 7.3 生态系统

| 维度 | PUC Lua | LuaJIT |
|------|---------|--------|
| **包管理器** | LuaRocks (全部) | LuaRocks (5.1 兼容 + LJ 专用) |
| **Web 框架** | 有限 | **OpenResty** (Nginx + LJ) |
| **API 网关** | — | Kong, APISIX |
| **游戏引擎** | — | LÖVE2D, Defold, Solar2D |
| **编辑器** | Neovim, Hammerspoon | Neovim (可切换) |
| **数据库** | — | Tarantool (内嵌 LJ) |
| **Redis 脚本** | — | Redis Lua 脚本 (LJ fork) |
| **机器学习** | — | Torch (PyTorch 前身) |
| **C 互操作库** | Lua C API / tolua / SWIG | **FFI** (不需要额外库) |

### 7.4 设计取舍 — 为什么选择各自的实现

| 设计决策 | PUC Lua 的选择与原因 | LuaJIT 的选择与原因 |
|----------|---------------------|---------------------|
| **数值系统** | 整数 + 浮点数双表示 | 纯 double (FFI 补足) |
| | 原因: 语义清晰，位操作自然 | 原因: 简化 JIT，避免类型检查 Guard |
| **GC 算法** | 分代 GC (5.4+) | 增量标记-清除 |
| | 原因: 新生对象短命，分代理高效 | 原因: 低延迟优于高吞吐 |
| **字节码** | 32-bit 定长，~80 个 opcode | Lua 5.1 格式 + 扩展 |
| | 原因: 简单、可移植 | 原因: 兼容性优先 |
| **语言演进** | 积极演进 (5.1→5.5) | 冻结在 5.1 + 选择性移植 |
| | 原因: 学术项目，有演进需求 | 原因: 维护者有限，稳定性优先 |
| **解释器实现** | ANSI C | 手写汇编 (DynASM) |
| | 原因: 极致可移植性 | 原因: 极致性能 |

### 7.5 极限情况分析

**JIT 编译失败场景（"NYI" — Not Yet Implemented）**：

并不是所有 Lua 代码都能被 JIT 编译。以下情况会**终止 trace 录制**并回退到解释器：

- `string.gmatch` / `string.gsub` 带函数参数
- `coroutine` 的某些操作
- `debug.*` 函数调用
- `setfenv` / `getfenv`
- 深层递归（超过 trace 限制）
- 某些 table 元方法组合

可以运行时检测：`jit.util.traceinfo()` 或命令行 `-jv` (verbose mode) 可以显示哪些 trace 失败了。

**LuaJIT 的黑色艺术**：要让代码被有效 JIT 编译，需要遵循一些"JIT 友好"的编写模式——这被称为 "LuaJIT 的黑色艺术"：
- 保持变量类型稳定（不要在同一变量上混用 number 和 string）
- 对表使用数组部分（`t[1]`, `t[2]`...），JIT 可以编译为 O(1) 访问
- 避免在热路径上使用 NYI 操作

### 7.6 维护现状与社区

| | PUC Lua | LuaJIT |
|---|---------|--------|
| **主要维护者** | PUC-Rio 学术团队 | 社区 (原 Mike Pall) |
| **最近大版本** | 5.5 (2025-12) | 2.1 正式版 (2024) |
| **开发节奏** | 5 年一大版本 | 慢（核心 JIT 很少改动） |
| **Bus Factor** | ~3 人学术团队 | 低（JIT 核心极难修改） |
| **积极维护** | ✅ 是 | 有限（社区驱动） |

> 2026 年视野：Lua 生态已分裂为三大方言——PUC Lua 5.5（正统演进路径）、LuaJIT（高性能但冻结在 5.1）、Luau（Roblox 的分支，带渐进类型系统）。选择哪种取决于宿主应用。参见：[Lua in 2026: Why Lua 5.5, LuaJIT, and Luau Are Three Different Languages Now](https://www.birjob.com/blog/lua-5-5-luajit-luau-dialect-split-2026)。

---

## 常见面试题

### 1. LuaJIT 比 PUC Lua 快多少？为什么？

**通常 3–50 倍不等**，取决于代码特征。核心原因：
- JIT 编译消除了解释开销（每条指令从多次 C 调用 → 1 条机器指令）
- 数值运算直接在寄存器中完成（PUC Lua 每次运算都要装箱/拆箱）
- 表访问编译为直接内存偏移（类型稳定时）
- 循环不变量外提、常量折叠、死代码消除等编译优化

### 2. LuaJIT 为什么不能支持 Lua 5.3+ 的整数类型？

因为这会**从根本上改变 IR 设计**——LuaJIT 的 IR 和优化流水线深度依赖"所有数字是 double"这个假设。引入整数子类型意味着每个运算都需要类型分派，增加 Guard 数量和编译复杂度。FFI 已经提供了 C 整数类型支持作为替代方案。

### 3. LuaJIT 的 FFI 和 PUC Lua 的 C API 有什么区别？

- **C API**：你需要写 C 代码（编译为 `.so`/`.dll`），在 C 端手动管理 Lua Stack。
- **FFI**：纯 Lua 代码，3 行声明就可以直接调用任意 C 函数，**不需要编译**。JIT 编译后调用开销为零。

### 4. 什么是 Trace Compiler 的 "Trace Abort"？

当录制一条 trace 时，如果遇到无法处理的字节码（NYI 操作），录制中止（"abort"），代码回退到解释器。这可能导致性能下降，因为那条路径永远不会被 JIT。需要通过 `-jv` 诊断哪些操作导致了 abort，然后改写代码避开或接受现状。

### 5. LuaJIT 被称为"死项目"，为什么还在用？

"死"更多是指**核心 JIT 架构不再剧烈演进**——不是因为坏，而是因为 Mike Pall 的设计足够正确。6 年未修改的核心 JIT 流水线依然领先于所有其他脚本运行时。对用户来说，这意味着：
- **零破坏性变更**：2018 年写的 LuaJIT 代码在 2026 年完全不变
- **稳定性极致**：6 年零回退
- **体积固定**：没有依赖膨胀

这被称为从 "actively maintained" 到 "finished" 的状态转变。

---

## 延伸主题

- **LuaJIT 内部**：[LuaJIT DeepWiki — JIT Compilation System](https://deepwiki.com/LuaJIT/LuaJIT/2-jit-compilation-system) — 完整的 IR、Trace、汇编流水线文档
- **OpenResty**：LuaJIT 在 web 服务端的最大部署——Nginx + LuaJIT 的非阻塞 I/O 模型
- **LuaJIT FFI**：[FFI Semantics](https://luajit.org/ext_ffi_semantics.html) — 类型映射、回调、内存布局
- **Luau**：Roblox 的 Lua 分支，带渐进类型系统和原生代码生成——Lua 生态的第三条路径
- **Lua 5.5 GC 设计**：增量 Major GC 如何消除 Stop-the-world 停顿
- **Trace Compiler 理论**：与 Method-based JIT (V8, HotSpot) 的对比
- **Lua GC 对比**：分代 GC (Lua 5.4+) vs 增量 GC (LuaJIT) vs RC + Cycle Detection (Luau)
