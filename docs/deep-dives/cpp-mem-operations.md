# C++ mem 系列操作 深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 游戏引擎开发工程师
> 分析日期: 2026-05-29

---

`memcpy`、`memmove`、`memset`、`memcmp`、`memchr` 是 C 标准库中最底层的字节操作函数。它们看起来简单——"不就是拷贝/设置/比较字节吗"——但底层实现在过去 40 年中经历了从逐字节循环到 SIMD、非时态存储、甚至页表映射的极致优化。游戏引擎中大量使用这些函数来操作组件数组、序列化缓冲、GPU 数据传输。

---

## 第 1 层: 直觉理解

**一句话**：mem 系列操作是以字节为单位处理原始内存的命令，无视类型系统。

**类比**：想象你有一排信箱（内存地址）。每个信箱里放一张纸条（一个字节）。

| 操作 | 类比 |
|------|------|
| `memcpy(dst, src, n)` | 把 `n` 个信箱里的纸条，抄一份放到另一排信箱 |
| `memmove(dst, src, n)` | 同上，但源和目标信箱可能有重叠——用临时中转或改变抄写顺序来保证正确 |
| `memset(dst, val, n)` | 把 `n` 个信箱里的纸条全部换成同一个值 |
| `memcmp(a, b, n)` | 逐个信箱比较，找到第一个不同的纸条 |
| `memchr(buf, val, n)` | 逐个信箱找，第一个放着指定纸条的是哪个 |

**核心区别**：它们操作的是**原始字节**（`void*`），不关心内存中实际对象的类型。这与 C++ 的对象语义（构造/析构/类型安全）形成对立——这也是为什么现代 C++ 推荐 `std::copy`、`std::fill`、`std::equal` 等类型安全的替代。

---

## 第 2 层: 使用场景

### 典型场景

| 场景 | 函数 | 引擎中的实例 |
|------|------|------------|
| 组件数组扩容时搬迁 | `memmove` | ECS 组件数组 realloc，源和目标可能重叠 |
| 顶点缓冲上传 | `memcpy` | `glBufferSubData` 前把顶点数据拷入 staging buffer |
| 网络包清零 | `memset` | 发送缓冲复用前归零敏感字段 |
| 序列化缓冲比较 | `memcmp` | 增量保存：判断是否与上一帧相同 |
| 二进制搜索 | `memchr` | 在序列化数据中找分隔符 |

### 不适用场景

| 不该用 | 原因 | 替代 |
|--------|------|------|
| 拷贝非平凡对象（有虚函数、`std::string` 成员等） | `memcpy` 不调用构造/析构函数，也不处理虚表指针 | `std::copy` / placement new |
| 设置非 POD 数组 | `memset` 到非零值可能破坏对象内部状态（如 `std::string` 的 SSO buffer） | `std::fill` |
| 比较有 padding 的 struct | `memcmp` 会对比 padding 字节（值未定义） | 逐字段比较或 `operator==` |
| 跨线程共享缓冲 | 无同步的 `memcpy`/`memset` 不是原子的 | 原子操作或锁 |

### 决策流程

```
需要操作原始字节？
  ├─ 复制
  │   ├─ 源和目标可能重叠？ → memmove
  │   └─ 保证不重叠？       → memcpy
  ├─ 填充
  │   └─ 设置连续内存为某值？ → memset
  ├─ 比较
  │   ├─ 需要知道哪个字节不同？ → memcmp
  │   └─ 只想知道是否相等？（C++23）→ memcmpeq（更高效）
  └─ 搜索
      └─ 找特定字节？ → memchr
```

---

## 第 3 层: API 层

### 函数签名

```cpp
#include <cstring>

// 复制 n 字节从 src 到 dst。src 和 dst 不能重叠。
void* memcpy(void* dst, const void* src, size_t n);

// 复制 n 字节从 src 到 dst。正确处理重叠（如同先拷到临时缓冲区）。
void* memmove(void* dst, const void* src, size_t n);

// 把 dst 的前 n 字节设为 (unsigned char)val。
void* memset(void* dst, int val, size_t n);

// 比较 s1 和 s2 的前 n 字节。返回值符号由第一个不同字节的差值决定。
int memcmp(const void* s1, const void* s2, size_t n);

// 在 s 的前 n 字节中搜索值为 (unsigned char)val 的第一个字节。
void* memchr(const void* s, int val, size_t n);

// C++23: 类似 memcmp，但只关心相等/不等（零/非零），允许提前终止优化。
int memcmpeq(const void* s1, const void* s2, size_t n);
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `dst` | `void*` | 目标地址。`memcpy`/`memmove`/`memset` 都返回它 |
| `src` / `s1` / `s2` | `const void*` | 源地址。`memcpy` 中不可与 `dst` 重叠 |
| `n` | `size_t` | 操作的字节数。`n=0` 时所有函数都是合法 no-op |
| `val` | `int` | 被转为 `unsigned char`，即只取低 8 位 |

### 返回值

| 函数 | 返回值 |
|------|--------|
| `memcpy` / `memmove` / `memset` | 返回 `dst` 指针（允许链式调用：`memcpy(buf, memset(tmp, 0, sz), sz)`） |
| `memcmp` | 负数（`s1 < s2`）、零（相等）、正数（`s1 > s2`） |
| `memchr` | 指向找到的字节的指针，或 `nullptr`（未找到） |

---

## 第 4 层: 行为契约

### memcpy

| 维度 | 契约 |
|------|------|
| **前置条件** | `dst` 和 `src` 各指向至少 `n` 字节的有效内存；两者**不可重叠** |
| **后置条件** | `dst[0..n-1]` == `src[0..n-1]`；`src` 内容不变 |
| **UB 条件** | `dst` 或 `src` 为 `nullptr` 且 `n > 0`；重叠（具体行为未定义——可能部分拷贝、可能崩溃） |
| **别名豁免** | `memcpy` 是 C 标准明确豁免 TBAA 的函数——编译器必须假设它可以改变任何对象，无论类型 |

### memmove

| 维度 | 契约 |
|------|------|
| **前置条件** | `dst` 和 `src` 各指向至少 `n` 字节的有效内存；**允许重叠** |
| **行为等价** | 效果等同于先把 `src[0..n-1]` 拷到临时缓冲区，再从临时缓冲区拷到 `dst` |
| **实际实现** | 不真正分配临时缓冲区——根据重叠方向选择正向/反向拷贝 |
| **后置条件** | `dst[0..n-1]` == 调用前 `src[0..n-1]`（即使重叠也正确） |

### memset

| 维度 | 契约 |
|------|------|
| **前置条件** | `dst` 指向至少 `n` 字节有效内存 |
| **val 转换** | `val` 被 `(unsigned char)val` 截断为 8 位，然后复制到每个字节 |
| **UB** | `n > 0` 且 `dst == nullptr` |

### memcmp

| 维度 | 契约 |
|------|------|
| **比较方式** | 字节被解释为 `unsigned char`；第一个不同字节的差值 `s1[i] - s2[i]` 决定返回值符号 |
| **提前终止** | 找到不同字节后立即返回，不比较剩余字节 |
| **零长度** | `n == 0` 返回 `0` |

### memchr

| 维度 | 契约 |
|------|------|
| **搜索** | 返回第一个匹配的字节的指针，或 `nullptr` |
| **零长度** | `n == 0` 返回 `nullptr` |

### 线程安全

全部 mem 系列函数**对共享内存没有同步保证**。多个线程同时读写同一块内存需要外部同步。函数本身不持有任何内部状态，多线程调用不同地址是安全的。

---

## 第 5 层: 实现原理

### 5.1 memcpy / memmove 的统一框架

所有现代 `memcpy` 实现按以下**分层策略**工作：

```
┌─────────────────────────────────────────────┐
│  第 0 层: 阈值分发                          │
│  小于阈值(如 16B) → 逐字节/逐字拷贝          │
│  中等(16B~256B)  → SIMD 寄存器拷贝           │
│  大块(>256B)     → 页拷贝 + SIMD + 非时态存储 │
└─────────────────────────────────────────────┘
```

#### 核心伪代码（通用 memcpy）

```
function memcpy(dst, src, n):
    if n == 0: return dst

    // ——— 阶段 1: 前导字节 — 对齐 dst ———
    while n > 0 and (dst & (word_size - 1)):
        *dst++ = *src++
        n--

    // ——— 阶段 2: 主体 — 按最大宽度拷贝 ———
    words = n / word_size    // word_size = 8, 16, 32, 或更大的 SIMD 宽度
    while words > 0:
        *((word_t*)dst) = *((word_t*)src)
        dst += word_size; src += word_size
        words--

    // ——— 阶段 3: 尾部 — 逐字节拷贝剩余 ———
    n = n % word_size
    while n > 0:
        *dst++ = *src++
        n--

    return dst
```

实际 glibc 实现在阶段 2 中分多个子阶段：页拷贝（数 KB/次）→ SIMD（32B/次）→ 字（8B/次）→ 字节（1B/次）。

#### 对齐技巧：src 和 dst 不对齐时

当 `src` 和 `dst` 对齐到不同偏移时（如 `src` 在地址 3，`dst` 在地址 0，word_size=4），不能用简单的字拷贝。技巧是**合并 (merge)**：

```
src 的字节序列:  [A B C D] [E F G H] ...
                  ↑ src

偏移量: sh1 = src % 4 = 3,  sh2 = 4 - sh1 = 1

第 1 次写入 dst: 读取 src[0..3] (A B C D) → 右移 sh2=1 字节 → 得到 0 A B C
                                        但 dst 需要 [A B C D] 的结尾部分
                实际: 先读 pad 字节 + src[0..2]，再组合

第 2 次写入 dst: 读取 src[0..3] → 左移 sh1=3 字节 → 取 A 的高 3 位
                 读取 src[4..7] → 右移 sh2=1 字节 → 取 E F G 的低 1 位
                 OR 两者 → 得到完整的 [A B C D]
```

这需要每次循环读 2 个字来写 1 个字。但通过寄存器缓存上次读取的高位部分，实际不会把 `src` 读完 2 遍。

### 5.2 memmove 的重叠处理

`memmove` 的核心是对重叠方向的判断：

```
function memmove(dst, src, n):
    if dst == src or n == 0:
        return dst

    if dst < src:
        // 正向拷贝: dst 的写入位置在 src 读取位置之前 → 不会覆盖未读数据
        // [src___]      src 在前面
        //    [dst___]   dst 在后面
        memcpy(dst, src, n)

    else:  // dst > src
        // 反向拷贝: dst 的写入位置在 src 之后 → 从末尾开始拷
        // [src___]
        //       [dst___]
        while n > 0:
            n--
            ((char*)dst)[n] = ((char*)src)[n]

    return dst
```

**关键直觉**：
- `dst < src`：正向拷贝安全（写入永远在读取位置之前）
- `dst > src`：反向拷贝安全（从尾部开始，写入永远在已读取位置之后）
- 两种情况下，"已读未写"的数据都不会被覆盖

### 5.3 memset 的实现策略

```
function memset(dst, val, n):
    byte = (unsigned char)val

    // ——— 阶段 1: 小缓冲区 → 逐字节 ———
    if n < small_threshold:
        while n--: *((char*)dst)++ = byte
        return dst

    // ——— 阶段 2: 构建"字模式" ———
    // 把单个字节扩展为一个字: val=0xAB → word=0xABABABABABABABAB
    word = byte
    word |= word << 8
    word |= word << 16
    word |= word << 32          // 64 位

    // ——— 阶段 3: 对齐 dst ———
    while n > 0 and (dst & (word_size - 1)):
        *((char*)dst)++ = byte; n--

    // ——— 阶段 4: 按字填充 ———
    while n >= word_size:
        *((word_t*)dst) = word
        dst += word_size; n -= word_size

    // ——— 阶段 5: 尾部 ———
    while n--: *((char*)dst)++ = byte

    // ——— 阶段 6 (可选): 大块用非时态存储 ———
    // 超过 LLC 缓存大小的 memset 用 non-temporal stores 绕过缓存，避免污染
    return dst
```

**非时态存储 (Non-Temporal Stores)**：对于超大缓冲区（数 MB），正常的字写入会逐出缓存中所有有用数据。`movnti`（x86）/ `dc zva`（AArch64）指令绕过 CPU 缓存，直接写入内存。

### 5.4 memcmp 的实现策略

- **小块**（<32B）：直接用通用寄存器比较，或加载到 AVX2 ymm 寄存器后 mask 多余字节
- **中块**（32~256B）：用 `vpcmpeqb` + `vpmovmskb` → 位掩码 → `tzcnt` 找第一个不同位
- **大块**（>256B）：循环展开 4 路比较 + 树归约（AND 后再检查），减少分支

### 5.5 memchr 的实现策略

- 逐字节扫描，但有优化：用 SIMD 比较指令（`vpcmpeqb`）一次比较 32 字节
- 用位掩码 + `tzcnt` 定位第一个匹配位置

---

## 第 6 层: 源码分析

### 6.1 glibc 通用 memcpy（C 实现）

来源: [glibc/string/memcpy.c](https://codebrowser.dev/glibc/glibc/string/memcpy.c.html) (glibc 2.38)

```c
// 核心结构: 分页 → 分字 → 分字节
void *
memcpy(void *dstpp, const void *srcpp, size_t len) {
  unsigned long int dstp = (long int) dstpp;
  unsigned long int srcp = (long int) srcpp;

  // 按页拷贝 (PAGE_SIZE = 通常 4096)
  if (len >= OP_T_THRES) {       // OP_T_THRES = 页面拷贝的阈值
    // 对齐 dst
    while (dstp % OPSIZ != 0) { *((byte *)dstp++) = *((byte *)srcp++); len--; }
    // 按页拷贝
    size_t pages = len / PAGE_SIZE;
    while (pages--) {
      PAGE_COPY_FWD(dstp, srcp);  // 平台特定的整页拷贝(可能是 vm_copy)
      dstp += PAGE_SIZE; srcp += PAGE_SIZE;
    }
    len %= PAGE_SIZE;
  }

  // 按字拷贝 (OPSIZ = 8 在 64 位平台)
  size_t words = len / OPSIZ;
  while (words--) {
    *((op_t *)dstp)++ = *((op_t *)srcp)++;
  }
  len %= OPSIZ;

  // 尾部逐字节
  while (len--) { *((byte *)dstp)++ = *((byte *)srcp)++; }

  return dstpp;
}
```

### 6.2 glibc x86_64 memmove-vec-unaligned-erms.S（汇编实现）

来源: [glibc/sysdeps/x86_64/multiarch/memmove-vec-unaligned-erms.S](https://codebrowser.dev/glibc/glibc/sysdeps/x86_64/multiarch/memmove-vec-unaligned-erms.S)

这是现代 x86_64 上实际运行的 memmove 路径。关键逻辑（伪代码形式）：

```asm
; 入口: rdi=dst, rsi=src, rdx=n
; 分支 1: 小拷贝 (< 16 字节)
    cmp    rdx, 16
    jb     L(small)

; 分支 2: 大块 → 用 REP MOVSB (ERMS=Enhanced REP MOVSB)
; 如果 CPU 支持 ERMS (Ivy Bridge+)
L(erms):
    mov    rax, rsi           ; 保存返回值
    cmp    rdx, 4096          ; 但如果正向拷贝且不重叠，大块用 REP MOVSB
    ; ... 重叠判断 ...
    rep movsb                 ; 硬件加速的字节拷贝

; 分支 3: 重叠 → 反向拷贝
L(backward):
    ; 从末尾开始逐 SIMD 寄存器拷贝
    vmovdqu ymm0, [rsi+rdx-32]
    vmovdqu [rdi+rdx-32], ymm0
    ; ... 循环 ...

; 分支 4: 正向拷贝（含不对齐处理）
L(forward):
    ; 对齐处理 + SIMD 循环 + 尾部
```

**关键指令 `rep movsb`**：现代 Intel CPU（Ivy Bridge+）有 ERMS（Enhanced REP MOVSB）功能，`rep movsb` 不再缓慢——CPU 内部检测到后切换到类似 DMA 的高速拷贝模式，对于大块拷贝性能接近甚至超过手写 SIMD。

### 6.3 glibc memcmp AVX2 路径

来源: [glibc/sysdeps/x86_64/multiarch/memcmp-avx2-movbe.S](https://codebrowser.dev/glibc/glibc/sysdeps/x86_64/multiarch/memcmp-avx2-movbe.S)

核心算法（参考伪代码）：

```asm
; 小块 (<32B): 特殊处理
    cmp    rdx, 32
    jb     L(less_32bytes)

; 中块 (32~256B): 内联展开 4 轮
    vmovdqu   ymm2, [rsi + 32]
    vpcmpeqb  ymm2, ymm2, [rdi + 32]   ; 比较 32 字节
    vpmovmskb eax, ymm2                ; 结果转位掩码
    inc       eax                       ; 反转 (全相等 → 0)
    jne       L(diff_found)
    ; ... 重复 3 次 ...

; 大块 (>256B): 循环
L(loop):
    vmovdqu   ymm1, [rsi + rdi*1]
    vpcmpeqb  ymm1, ymm1, [rdi]
    ; ... 4 路展开 ...
    vpand     ymm5, ymm2, ymm1          ; 树归约: AND 多路结果
    vpand     ymm6, ymm4, ymm3
    vpand     ymm7, ymm6, ymm5
    vpmovmskb ecx, ymm7                ; 一次检查 128 字节
    inc       ecx
    jne       L(diff_found_loop)
    ; ... 循环 ...
```

**树归约优化**：展开 4 路（每路 32B = 128B/轮），用 `vpand`（可运行在 3 个 CPU 端口）归约结果，再用 1 次 `vpmovmskb`（只能运行在 1 个端口）检查，减少瓶颈指令的频率。

### 6.4 memset 的非时态存储优化

来源: [glibc commit 5bf0ab8](https://github.com/bminor/glibc/commit/5bf0ab80573d66e4ae5d94b094659094336da90f) (RHEL patch for large memset)

```asm
; 大块 memset 的关键路径
L(nt_stores):
    ; 先填满一个 ZMM 寄存器 (512 位)
    vpbroadcastb zmm0, eax            ; 广播字节 → 64 字节模式
    ; 循环: 每次写 256 字节 (4 × 64B)
L(nt_loop):
    vmovntdq [rdi], zmm0              ; 非时态存储, 绕过缓存
    vmovntdq [rdi + 64], zmm0
    vmovntdq [rdi + 128], zmm0
    vmovntdq [rdi + 192], zmm0
    add    rdi, 256
    sub    rdx, 256
    ja     L(nt_loop)
    sfence                             ; 内存屏障, 确保非时态存储完成
```

**性能数据**（Nadav Rotem 的 memset benchmark，i7-6700HQ @ 2.6GHz）：
- 小缓冲（<8KB）：`rep stosb` 和手写 AVX 持平
- 中等缓冲（8KB~1MB）：`rep stosb` 最快（CPU 微码优化）
- 大缓冲（>1MB）：AVX 非时态存储最快，比 `rep stosb` 快 ~40%

---

## 第 7 层: 对比与边界

### 7.1 memcpy vs memmove

| 维度 | memcpy | memmove |
|------|--------|---------|
| 重叠处理 | 不允许（UB） | 正确处理 |
| 性能 | 略快（少一次分支判断） | 略慢（需分支判断重叠方向） |
| 实际差距 | ~0.5-2% （几乎无法测量） | 基准 |
| 何时用 | 确定不重叠（不同 buffer、new 分配的内存） | 不确定是否重叠（数组搬迁、ring buffer） |

**引擎实践建议**：**默认用 `memmove`**。性能差异微不足道，但重叠带来的 UB 可能导致难以追踪的 Bug（只在特定大小/对齐组合下表现异常）。

### 7.2 mem 系列 vs C++ 替代品

| C 函数 | C++ 替代 | 优势 |
|--------|---------|------|
| `memcpy` | `std::copy` / `std::memcpy` | 类型安全，对平凡可拷贝类型自动退化为 `memcpy` |
| `memmove` | `std::copy_backward` / `std::move` (迭代器) | 正确处理重叠 + 类型安全 |
| `memset` | `std::fill` / `std::fill_n` | 类型安全，对 `char` 自动退化为 `memset` |
| `memcmp` | `std::equal` / `std::lexicographical_compare` | 类型安全，但不保证与 `memcmp` 相同性能 |
| `memchr` | `std::find` | 类型安全 |

**谁更快？** 在 Release 模式下（`-O2`/`-O3`），主流的三大编译器（GCC、Clang、MSVC）都能将 `std::copy`/`std::fill` 对 POD 类型的调用**内联并优化为等效的 mem 系列调用**。两者性能基本一致。

### 7.3 不同场景的 memcpy 优化策略对比

| 策略 | 适用大小 | 原理 | 额外代价 |
|------|---------|------|---------|
| 逐字节 | <16B | 避免函数调用和分支 | 无 |
| `rep movsb` (ERMS) | 128B~4KB | CPU 微码优化 | 无 |
| SSE/AVX 对齐 | 128B~256KB | 寄存器宽度 × 展开 4~8 路 | 对齐处理 |
| 非时态存储 | >1MB | 绕过缓存写内存 | 需要 `sfence` 屏障 |
| 页表映射 | >4KB (macOS) | `vm_copy` 延迟到 page fault | Copy-on-write 开销 |

### 7.4 严格别名规则（TBAA）豁免

`memcpy` 和 `memmove` 在 C 标准中**明确豁免了 TBAA 约束**。这是它们在引擎中扮演关键角色的技术原因：

```cpp
// 这不是 UB——memcpy 可以"看到"任何对象的字节
float f = 3.14f;
int i;
std::memcpy(&i, &f, sizeof(float));  // 合法: 获取 float 的字节表示

// 这也不是 UB——通过 memcpy 写入不会触发 TBAA
int src = 42;
float dst;
std::memcpy(&dst, &src, sizeof(float));  // 合法（虽然值是 garbage）

// 这才是 UB——通过不兼容的指针类型直接写入
*reinterpret_cast<float*>(&src) = 3.14f;  // UB!
```

这也是为什么我们在 ObjectPool 实现中推荐用 `memcpy` 替代 `reinterpret_cast<T**>` 解引用——前者被标准担保合法，后者形式上是 UB。

### 7.5 平台差异速查

| 特性 | x86_64 (glibc) | AArch64 (glibc) | macOS (libSystem) | Windows (ucrt) |
|------|---------------|-----------------|-------------------|----------------|
| 小 memcpy | `rep movsb` / SSE | `ldp`/`stp` 指令对 | `rep movsb` | `rep movsb` / SSE |
| 大 memcpy | AVX2 + NT stores | SVE (可变宽度 SIMD) | `vm_copy` (整页) | AVX2 + NT stores |
| memcmp SIMD | AVX2 `vpcmpeqb` | NEON `cmeq` + `pmax` | AVX2 `vpcmpeqb` | SSE4.2 `pcmpestri` |

---

## 常见面试题

**Q1: `memcpy` 和 `memmove` 的区别是什么？什么时候必须用 `memmove`？**

A: `memcpy` 要求源和目标不重叠（否则 UB）；`memmove` 正确处理重叠。当不确定是否重叠时（如数组内移动元素、ring buffer），必须用 `memmove`。实现上，`memmove` 通过检测 `dst` 和 `src` 的相对位置决定正向或反向拷贝。

**Q2: 为什么用 `memset` 给 `int` 数组设零是安全的，但设其他值不安全？**

A: `memset` 按字节设置。设零：每个字节都是 `0x00`，组合成 `int` 正好是 `0`。设 `1`：每个字节 `0x01`，组合成 `int` 是 `0x01010101`（16843009），不是 `1`。

**Q3: C++ 中如何安全地获取一个对象的字节表示？**

A: 用 `std::memcpy` 把对象拷贝到 `char`/`std::byte` 数组。不要用 `reinterpret_cast` 直接访问——它违反严格别名规则。

**Q4: 在大块内存上，`memset` 怎样避免污染 CPU 缓存？**

A: 用非时态存储（NT stores）：`movnti`（x86）或 `dc zva`（AArch64）指令直接写入内存控制器，绕过各级 CPU 缓存。之后需要一个内存屏障（`sfence`）确保写入完成。

**Q5: `memcmp` 能否安全比较有 padding 的 struct？为什么？**

A: **不能**。C/C++ 标准不保证 padding 字节的值（它们可以是任何值，且每次可能不同）。即使两个 struct 的成员字段完全相同，padding 可能不同，导致 `memcmp` 返回非零。应当逐字段比较，或用 `#pragma pack` 消除 padding（代价是可能的性能损失）。

---

## 延伸主题

- **`std::bit_cast` (C++20)**：替代 `memcpy` 做类型双关，更安全且 `constexpr`
- **`std::copy` / `std::fill` 的编译器优化**：编译器如何识别并退化为 mem 系列函数
- **ERMS / FSRM (Fast Short REP MOVSB)**：CPU 微码层面的 memcpy 加速
- **DMA 拷贝**：绕过 CPU 直接在外设和内存间传输数据
- **`mmap` + `memcpy`**：文件 I/O 的内存映射优化
- **`std::launder` (C++17)**：placement new 后的指针清洗，与 memcpy 的 TBAA 豁免相关但不重叠
