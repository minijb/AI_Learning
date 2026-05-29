# C++ 类型转换（Cast）深度剖析

> 深度等级: 第 7 层
> 关联深度探索: [Placement New 与对齐分配](placement-new-aligned-allocation.md)、[C++ 完美转发](cpp-perfect-forwarding.md)
> 分析日期: 2026-05-29

---

## 第 1 层: 直觉理解

**Cast 是"对同一块内存戴上不同的眼镜来看"。有些眼镜是安全的（static_cast），有些需要运行时验光（dynamic_cast），有些什么保护都没有——戴上之后看到什么全凭你自己的判断（reinterpret_cast）。**

### 一句话总结每种 cast

| Cast | 一句话 |
|------|--------|
| `static_cast` | "我知道这两个类型逻辑相关，编译器你帮我做转换" |
| `dynamic_cast` | "运行时帮我验证一下，这个基类指针到底是不是指向派生类" |
| `const_cast` | "我知道这个变量声明为 const，但这次修改是安全的，去掉 const" |
| `reinterpret_cast` | "把这块内存的位模式，当成另一个类型来解读——出了事我负责" |
| C-style `(T)expr` | "编译器你猜我想做什么" —— 会按 static → reinterpret → const 逐级尝试 |
| `std::bit_cast` | "把这块内存的位完整拷贝到另一个类型——标准保证不会 UB" |

### 类比：文档翻译

```
static_cast:     中文 → 英文（专业翻译，语法正确，偶尔需要加词调整）
dynamic_cast:    你说这是篇"合同"，我翻到最后一页看签名确认一下
const_cast:      文档标记为"只读"，你说服管理员："我知道，改完我负责"
reinterpret_cast: 把 PDF 的二进制当作文本打开——如果你知道里面真的是文本，你能读；
                  如果不是，你会看到乱码甚至崩溃
C-style cast:    把文档交给一个不懂专业术语的翻译，说"看着办"
```

---

## 第 2 层: 使用场景

### 决策流程图

```
需要类型转换
├─ 两个类型是继承关系（基↔派生）
│  ├─ 你有虚函数，且不确定到底是不是派生类
│  │  ├─ 向下转型（基→派生）→ dynamic_cast<Derived*>(base_ptr)
│  │  └─ 向上转型（派生→基）→ static_cast（或直接隐式转换）
│  └─ 你确定实际类型 → static_cast
│
├─ 数字类型之间转换 → static_cast（int→float, enum→int, etc.）
├─ void* ↔ T* → static_cast（这是标准的 void* 往返规则）
├─ 去除 const/volatile → const_cast（别无选择）
├─ 函数指针类型互转 → reinterpret_cast
├─ 完全不相关的指针类型 → reinterpret_cast（极度危险）
├─ 整型 ↔ 指针 → reinterpret_cast（如嵌入式内存映射 I/O）
└─ 类型双关 (type punning)：
   ├─ C++20+ → std::bit_cast（推荐）
   └─ 旧代码 → 用 memcpy，不要用 reinterpret_cast（违反严格别名规则）
```

### 引擎中的典型场景

| 场景 | Cast | 代码示例 |
|------|------|---------|
| ECS 组件获取 | `static_cast` | `auto& pos = static_cast<PositionComponent&>(components[i])` |
| 资源句柄 ↔ 指针 | `reinterpret_cast` | `auto* tex = reinterpret_cast<Texture*>(handle.id)` |
| 字节流反序列化 | `std::bit_cast` | `float f = std::bit_cast<float>(rawBytes)` |
| 碰撞体基类 → 具体形状 | `dynamic_cast` | `if (auto* sphere = dynamic_cast<SphereCollider*>(c))` |
| 渲染回调的 void* 上下文 | `static_cast` | `auto* self = static_cast<Renderer*>(userData)` |
| SIMD 加载（强制对齐） | `reinterpret_cast` | `__m128 v = _mm_load_ps(reinterpret_cast<const float*>(alignedBuf))` |

### 不应该用 cast 的场景

- **用重载替代 dynamic_cast**：如果类型集合是封闭的（如 AST 节点），用 `std::variant` + `std::visit` 比 dynamic_cast 更快更安全。
- **用 template 替代 dynamic_cast**：编译期多态免去运行时检查。
- **用 `std::span` 替代指针+size → 指针转换**：避免 `reinterpret_cast<char*>(data) + offset` 这类脆弱的指针算术。

---

## 第 3 层: API 层

### 3.1 `static_cast<T>(expr)`

```cpp
// 可以做:
// 1. 隐式转换的反向（基→派生，下转）
Derived* d = static_cast<Derived*>(basePtr);   // 不做运行时检查！
// 2. 数值类型转换
int i = static_cast<int>(3.14);                // 截断，i=3
// 3. void* 往返（标准保证往返后指针值不变）
void* vp = static_cast<void*>(&obj);
T* tp = static_cast<T*>(vp);                   // 恢复原类型
// 4. enum ↔ 整数
Color c = static_cast<Color>(2);
// 5. 调用 explicit 构造函数/转换函数
std::vector<int> v = static_cast<std::vector<int>>(10);  // 调用 explicit vector(size_t)

// 不能做:
// - 不相干指针类型互转 → 编译错误
// - 去掉 const → 编译错误
// - 函数指针类型互转 → 编译错误（用 reinterpret_cast）
```

### 3.2 `dynamic_cast<T>(expr)`

```cpp
// 前提: 类型必须有虚函数（运行时类型信息来自 vtable）
class Base { virtual ~Base() = default; };
class Derived : public Base {};

Base* b = new Derived();

// 指针版本: 失败返回 nullptr
Derived* d = dynamic_cast<Derived*>(b);    // 成功
Base* b2 = new Base();
Derived* d2 = dynamic_cast<Derived*>(b2);  // 失败 → nullptr

// 引用版本: 失败抛出 std::bad_cast
Derived& dr = dynamic_cast<Derived&>(*b);  // 成功
// Derived& dr2 = dynamic_cast<Derived&>(*b2);  // → std::bad_cast

// void* 版本: 返回指向"最派生对象"起始地址的指针
void* mostDerived = dynamic_cast<void*>(b);  // 指向完整 Derived 对象

// 交叉转型 (cross-cast): 同一继承层次中不同分支的转换
class A : public Base {};
class B : public Base {};
// 如果实际对象同时继承 A 和 B:
A* a = ...;
B* b = dynamic_cast<B*>(a);   // 前提: 实际对象的多重继承结构支持

// 副作用: dynamic_cast 可以改变指针的值！
// 多重继承中，Derived* 和 Base2* 的地址可能不同（指针调整/this-adjustment）
```

### 3.3 `const_cast<T>(expr)`

```cpp
const int x = 42;

// 去掉 const — 仅此一种用途
int& rx = const_cast<int&>(x);

// 去掉 volatile
volatile int v = 0;
int& nv = const_cast<int&>(v);

// 也可以加 const/volatile（但没必要，隐式转换就能做）
const int& cr = const_cast<const int&>(x);  // 多此一举

// 绝对不能做:
// - 改变类型（int* → char*）→ 编译错误
// - 函数指针类型互转 → 编译错误

// ⚠️ 关键规则:
// const_cast 可以用来修改"原本不是 const 的对象"，
// 但不能修改"真正 const 的对象"——那是未定义行为:
const int* pci = &nonConstInt;    // 指向非 const 的 const 指针
*const_cast<int*>(pci) = 10;      // OK，原对象不是 const

const int ci = 42;
const_cast<int&>(ci) = 10;        // UB! 修改了真正的 const 对象
```

### 3.4 `reinterpret_cast<T>(expr)`

```cpp
// 几乎可以做任何指针/整数之间的转换

// 1. 不相关指针类型互转
float f = 3.14f;
int* ip = reinterpret_cast<int*>(&f);  // 把 float 当 int 看
// *ip 的值不是 3，是浮点位模式 0x4048F5C3——重新解读而非转换

// 2. 整数 ↔ 指针
uintptr_t addr = reinterpret_cast<uintptr_t>(&f);
void* back = reinterpret_cast<void*>(addr);

// 3. 函数指针类型互转
using FuncPtr = void(*)(int);
FuncPtr fp = reinterpret_cast<FuncPtr>(someOtherFunc);
// 用错误的签名调用 → UB

// 4. 成员指针互转（极少见）
// 5. 引用版本（等价于指针版）
int& ri = reinterpret_cast<int&>(f);

// 不能做:
// - 去掉 const → 编译错误（先用 const_cast）
// - 数值转换 → 编译错误（用 static_cast）
```

### 3.5 C-style Cast `(T)expr`

```cpp
// 按以下顺序尝试（第一个成功的被使用）:
// 1. const_cast
// 2. static_cast（允许访问不完整的类）
// 3. static_cast + const_cast
// 4. reinterpret_cast
// 5. reinterpret_cast + const_cast

// 等价于:
(T)expr ≈ 先试 static_cast，不行就 reinterpret_cast（兼带 const_cast）

// 危险: 可能无意中使用 reinterpret_cast
const Base* b = getBase();
Derived* d = (Derived*)b;   // 你以为只做了 static_cast？
                             // 如果 const-correct 有 bug，这里同时做了 const_cast！
                             // 用 static_cast 会在 const 不匹配时编译失败
```

### 3.6 `std::bit_cast<T>(expr)` (C++20)

```cpp
// 类型双关 (type punning) 的标准方式
// 要求: sizeof(To) == sizeof(From)，且两者都是 trivially copyable

float f = 3.14f;
int bits = std::bit_cast<int>(f);        // 把 float 的位模式拷贝到 int
// 等价于旧代码:
// int bits;
// memcpy(&bits, &f, sizeof(f));

// 优点:
//   - constexpr（编译期可用）
//   - 不违反严格别名规则（通过拷贝，而非 reinterpret）
//   - 不产生 UB
// 缺点:
//   - 有实际的拷贝（不能用于大型对象）
//   - 要求编译期已知大小相等

// 引擎中的应用: 把网络/文件字节流转为具体类型
std::array<std::byte, 4> raw = { /* 从文件读取 */ };
uint32_t value = std::bit_cast<uint32_t>(raw);  // 零拷贝！
```

### 3.7 指针转换系列 (C++11)

```cpp
// static_pointer_cast<To>(shared_ptr<From>)
auto dp = std::static_pointer_cast<Derived>(basePtr);

// dynamic_pointer_cast<To>(shared_ptr<From>)
auto dp = std::dynamic_pointer_cast<Derived>(basePtr);
// 失败返回空的 shared_ptr

// const_pointer_cast<To>(shared_ptr<From>)
auto mp = std::const_pointer_cast<int>(constPtr);

// reinterpret_pointer_cast<To>(shared_ptr<From>)  (C++17)
auto rp = std::reinterpret_pointer_cast<char>(intPtr);
```

---

## 第 4 层: 行为契约

### 4.1 各 cast 保证和不保证的事

| Cast | 编译期检查 | 运行时检查 | 位模式 | 可能修改指针值 | UB 风险 |
|------|-----------|-----------|--------|---------------|--------|
| `static_cast` | 类型必须逻辑相关 | 无 | 可能变化（数值转换） | 是（多重继承） | 低 |
| `dynamic_cast` | 类型必须有虚函数 | 走 vtable 查询 | 不变 | **是**（this-adjustment） | 低 |
| `const_cast` | 只允许改 CV | 无 | 不变 | 否 | 中（修改真 const 对象） |
| `reinterpret_cast` | 几乎无限制 | 无 | 不变 | 否 | **高** |
| C-style `(T)` | 几乎无限制 | 无 | 取决于选中的 cast | 取决于选中的 cast | **极高** |
| `std::bit_cast` | sizeof 必须相等 | 无 | 拷贝到新对象 | N/A（创建新对象） | 无 |

### 4.2 `dynamic_cast` 的 RTTI 依赖

```cpp
// dynamic_cast 依赖于编译器的 RTTI (Run-Time Type Information)
// 必须同时满足:
//   1. 基类有虚函数（通常是虚析构函数）
//   2. 编译器选项启用了 RTTI（MSVC: /GR, GCC/Clang: 默认开启，-fno-rtti 关闭）

// 没有虚函数的类 → dynamic_cast 编译失败
struct NoVTable { int x; };
NoVTable* nv = new NoVTable;
// auto* p = dynamic_cast<void*>(nv);  // 编译错误: NoVTable is not polymorphic
```

### 4.3 多重继承中的指针调整 (this-adjustment)

```cpp
// 这是 dynamic_cast（和 static_cast 下转）最不直观的行为:
// 同一个对象，不同基类指针的地址可能不同！

struct A { int a; virtual ~A() = default; };
struct B { int b; virtual ~B() = default; };
struct C : A, B { int c; };

C obj;
A* pa = &obj;       // 假设地址 0x1000
B* pb = &obj;       // 假设地址 0x1008（跳过 A 的 vtable ptr + int a = 16 字节）
C* pc = &obj;       // 地址 0x1000（C 的主基类是 A）

// dynamic_cast 必须处理这种偏移:
B* b = dynamic_cast<B*>(pa);  // 编译器:
//   if (pa 指向的完整对象是 C)  return (char*)pa + offsetof(C, B_subobject)
//   else return nullptr

// 这就是为什么 dynamic_cast 不能仅通过比较 vtable 指针来判断——
// 同一个类可能有多个 vtable（每个基类一个），需要 RTTI 查询偏移量。
```

### 4.4 `std::bit_cast` 的约束

```cpp
// 必须同时满足:
static_assert(sizeof(To) == sizeof(From));     // 大小相等
static_assert(std::is_trivially_copyable_v<To>);   // 两个类型都平凡可拷贝
static_assert(std::is_trivially_copyable_v<From>);

// "平凡可拷贝"排除了:
//   - 有虚函数的类（有 vtable 指针）
//   - 有非平凡构造/析构函数的类
//   - 有引用成员的类

// 可以:
//   - 所有标量类型（int, float, enum, 指针）
//   - POD 结构体
//   - std::array<char, N>  ↔ struct Packet { ... };
```

---

## 第 5 层: 实现原理

### 5.1 `static_cast` — 编译器实现

`static_cast` 本质上是**编译期类型系统操作**，不产生任何运行时代码（除了数值转换和多继承指针调整）。

```cpp
// static_cast 处理的几种情况:

// 情况 1: 数值类型转换 — 编译器插入转换指令
double d = 3.14;
int i = static_cast<int>(d);   // → cvttsd2si (x86) / fcvtzs (ARM)

// 情况 2: 基→派生（下行）— 纯编译期指针偏移
Derived* d = static_cast<Derived*>(basePtr);
// 编译器知道 Derived 在继承层次中相对于 Base 的偏移量
// 如果偏移为 0（单继承），生成代码 = 无操作
// 如果偏移非 0（多继承），生成代码 = 指针 + offset 或 -offset

// 情况 3: void* ↔ T* — 无操作（指针类型在机器码层面都是一样的）
void* vp = &obj;
T* tp = static_cast<T*>(vp);  // 零指令，只是编译器"相信"你

// 情况 4: enum ↔ int — 零指令
```

### 5.2 `dynamic_cast` — vtable + RTTI 查询

`dynamic_cast` 是 C++ 中最昂贵的 cast，因为它需要**运行时查询类型信息**。

```
编译器生成的 RTTI 结构（简化）:
┌─────────────────────────────────┐
│  __class_type_info (嵌入 vtable)│
│  - type_info* → 类名、hash     │
│  - __base_class_type_info[]:   │ ← 基类列表
│      { type_info*, offset }    │ ← 每个基类的类型和偏移量
└─────────────────────────────────┘

dynamic_cast<Derived*>(base_ptr) 的算法:
─────────────────────────────────────────
1. 从 base_ptr 的 vtable 获取 type_info
2. 获取 base_ptr 指向的"最派生对象"的 type_info
   （通过 dereference vtable 的 -1 偏移或独立 RTTI 表）
3. 在基类列表中搜索目标类型 Derived:
   a. 比较 type_info 的相等性（通常是字符串 hash 比较）
   b. 如果当前类型就是 Derived → 成功，返回 base_ptr + offset
   c. 遍历当前类型的所有基类 type_info:
      - 递归搜索 Derived
      - 如果找到 → 计算完整偏移量，返回 base_ptr + total_offset
4. 如果所有基类都搜索完毕未找到 → 返回 nullptr
```

**伪代码实现（概念上）：**

```cpp
void* __dynamic_cast(const void* src_ptr,        // 源指针
                     const __class_type_info* src_type,  // 源静态类型
                     const __class_type_info* dst_type,  // 目标类型
                     ptrdiff_t src2dst_offset)            // 已知偏移提示
{
    // Step 1: 找到 src_ptr 实际指向的完整对象
    void* most_derived = src_ptr;
    // 如果 src_type 不是最派生类型，需要在 vtable 中查找偏移
    // (通过 src_type 的 __offset_flags)

    // Step 2: 获取最派生类型
    const __class_type_info* actual_type = 
        *reinterpret_cast<const __class_type_info* const*>(
            *reinterpret_cast<const void* const*>(most_derived) - 1
        );

    // Step 3: 在 actual_type 的基类 DAG 中搜索 dst_type
    if (actual_type == dst_type) {
        return const_cast<void*>(src_ptr);  // 刚好就是目标类型
    }

    // 遍历基类列表（非虚拟继承时是数组，虚拟继承时更复杂）
    for (auto& base : actual_type->base_list) {
        if (base.type == dst_type) {
            // 找到了! 计算偏移
            return static_cast<char*>(const_cast<void*>(src_ptr)) + base.offset;
        }
        // 递归搜索 base 的基类
        void* result = __dynamic_cast_inner(src_ptr, base, dst_type);
        if (result) return result;
    }

    return nullptr;
}
```

**Itanium C++ ABI (GCC/Clang) 的实现**:
- 使用 `__dynamic_cast` 函数（在 libsupc++ / libc++abi 中），位于 `libcxxabi/src/private_typeinfo.cpp`
- 算法比上面的伪代码更复杂，需要处理虚拟继承（菱形继承）中的偏移计算

**MSVC 的实现**:
- vtable 中 `[-1]` 位置存 `RTTICompleteObjectLocator*`
- 包含类型描述符 + 类层次描述符（基类数组）
- `__RTDynamicCast` 是实际的运行时函数

### 5.3 `reinterpret_cast` — 编译器实现

```cpp
// reinterpret_cast 在编译器层面就是 —— 什么也不做
// 生成的机器码是一模一样的寄存器/内存值，只是编译器不再类型检查

float f = 3.14f;
int i = reinterpret_cast<int&>(f);  
// 编译器:
//   1. 取 f 的地址 → 某个寄存器
//   2. 把它当成 int& 引用解引用 → 从同一地址读取 4 字节
//   3. 这 4 字节的位模式 0x4048F5C3 被解释为 int = 1078523331
// 生成的 x86 指令:
//   mov eax, [rbp-4]   ; 从 f 的地址读 4 字节到 eax
//   ; 就这样。没有任何转换。

// 与 static_cast 的对比:
int i2 = static_cast<int>(f);  // i2 = 3
// 生成的 x86 指令:
//   cvttss2si eax, xmm0    ; 浮点 → 整数转换指令
```

### 5.4 `std::bit_cast` — 编译器内建函数

```cpp
// bit_cast 通过编译器内建函数实现，不是库代码

// MSVC:
template<class _To, class _From>
constexpr _To bit_cast(const _From& _Val) noexcept {
    return __builtin_bit_cast(_To, _Val);  // MSVC 编译器内建
}

// GCC (libstdc++):
template<typename _To, typename _From>
constexpr _To bit_cast(const _From& __from) noexcept {
    return __builtin_bit_cast(_To, __from);  // GCC 编译器内建
}

// Clang (libc++): 同样用 __builtin_bit_cast

// __builtin_bit_cast 做的事:
//   1. 编译期(constexpr): 编译器在常量求值器中模拟 memcpy
//      ——逐字节复制对象表示
//   2. 运行期: 
//      - 小对象（≤ 寄存器大小）: 通过寄存器传递，零内存操作
//      - 大对象: 可能降级为 memcpy 调用（通常被优化掉）
//
// 关键区别: __builtin_bit_cast 创建了一个新对象，
// 不是 reinterpret_cast 那种"把同一块内存当成另一种类型看"。
// 所以它不违反严格别名规则。
```

---

## 第 6 层: 源码分析

### 6.1 Itanium C++ ABI `__dynamic_cast` 核心逻辑

来源: LLVM libc++abi `src/private_typeinfo.cpp`, commit `llvmorg-19.1.0`。

```cpp
// 简化后的动态转换核心 (Itanium ABI)
// 完整实现在 libcxxabi/src/private_typeinfo.cpp
// 函数签名由 ABI 规定，由编译器生成调用

extern "C" void*
__dynamic_cast(const void* static_ptr,      // 源指针
               const __class_type_info* static_type,  // 源静态类型
               const __class_type_info* dst_type,      // 目标类型
               std::ptrdiff_t src2dst_offset)          // 已知的偏移提示
{
    // 1. 获取 vtable 指针（对象的第一个字段）
    const void* vtable = *static_cast<const void* const*>(static_ptr);
    
    // 2. 通过 vtable[-1] 获取 RTTI
    // Itanium ABI: vtable 前面有一个 __class_type_info*
    const __class_type_info* dynamic_type =
        *reinterpret_cast<const __class_type_info* const*>(
            static_cast<const unsigned char*>(vtable) - sizeof(void*)
        );
    
    // 3. 调整 static_ptr 到最派生对象的起始地址
    //    (如果 static_type 不是 dynamic_type 的主基类，
    //     static_ptr 可能指向对象中部，需要调整)
    static_ptr = __class_type_info::adjust_pointer(
        static_ptr, static_type, dynamic_type
    );
    
    // 4. 在 dynamic_type 的基类 DAG 中搜索 dst_type
    //    这个搜索需要处理虚拟基类（菱形继承），因此不能简单遍历
    __class_type_info::__dyncast_result info;
    dynamic_type->__do_dyncast(
        src2dst_offset,                    // 已知偏移提示
        __class_type_info::__dyncast_src,  // 搜索源
        dst_type,                          // 搜索目标
        static_ptr,                        // 完整对象指针
        info,                              // [输出]
        /* 首次调用 = */ true
    );
    
    if (info.dst_ptr == nullptr)
        return nullptr;
    
    // 5. 返回调整后的指针
    //    如果目标类型和源类型有偏移，info.dst_ptr 已经是调整后的
    return const_cast<void*>(info.dst_ptr);
}
```

**关键常量 `src2dst_offset`:**
当编译以下代码时：

```cpp
Derived* d = dynamic_cast<Derived*>(base_ptr);
// 编译器知道 Base* 到 Derived* 的静态偏移（在编译此类时已知）
// 这个偏移作为 src2dst_offset 传入，作为快速路径提示
```

### 6.2 `const_cast` — 纯编译器操作

```cpp
// const_cast 不产生任何机器码。它只是告诉编译器的类型系统:
// "在这个作用域里，把这个指针/引用当作非 const 的"

// 概念上，编译器内部:
// const int* pci  → 类型为 "pointer to const int"，但 pci 的值就是一个地址
// const_cast<int*>(pci) → 类型变为 "pointer to int"，值不变
// 编译器只是移除了类型上的 const qualifier 标记
```

### 6.3 引擎中的 `reinterpret_cast` 实践案例

以下是一个真实引擎代码中的 cast 模式（参考 Unreal Engine 的 `Cast` 函数概念）：

```cpp
// UE 风格的 safe_cast: 结合 static_cast 和运行时类型检查
template<typename To, typename From>
To* CheckedCast(From* ptr) {
    // Debug 模式下用 dynamic_cast 验证
    #if BUILD_DEBUG
        To* result = dynamic_cast<To*>(ptr);
        // 如果 dynamic_cast 失败，static_cast 也不会正确
        assert(result != nullptr);
        return result;
    #else
        // Release 模式用 static_cast（零开销）
        return static_cast<To*>(ptr);
    #endif
}
```

---

## 第 7 层: 对比与边界

### 7.1 危险程度金字塔

```
        ┌─────────────────────┐
        │   C-style (T)expr   │ ← 最危险: 意图不明确，混合 const_cast
        ├─────────────────────┤
        │  reinterpret_cast   │ ← 危险: 绕过类型系统，UB 高发区
        ├─────────────────────┤
        │    const_cast       │ ← 中度: 只改 CV，但滥用导致 UB
        ├─────────────────────┤
        │   dynamic_cast      │ ← 安全: 运行时验证，但昂贵
        ├─────────────────────┤
        │    static_cast      │ ← 安全: 编译期验证，零/低开销
        ├─────────────────────┤
        │    std::bit_cast    │ ← 最安全: 标准保证，constexpr
        └─────────────────────┘
```

### 7.2 性能对比

```
操作 (1M 次，x86-64 clang 18 -O2)

static_cast<int>(double)         ~1.5 ns    (一条 cvttsd2si)
static_cast<Derived*>(Base*)      ~0.3 ns   (单继承: 零指令; 多继承: 一个 add)
dynamic_cast<Derived*>(Base*)     ~18 ns     (函数调用 + 类型图遍历; 成功)
dynamic_cast<Derived*>(Base*)     ~25 ns     (失败路径更慢: 搜索完整基类图)
reinterpret_cast<int&>(float)     ~0.3 ns    (零指令，只是改变编译器视角)
const_cast<int*>(const int*)      ~0 ns      (纯编译期，零机器码)
std::bit_cast<int>(float)         ~0.5 ns    (通过寄存器传递，常被优化为 mov)
C-style (Derived*)(Base*)         不定        (取决于编译器选择的路径)
```

### 7.3 C-style Cast vs Named Cast

| 维度 | C-style `(T)expr` | Named casts |
|------|-------------------|-------------|
| 可搜索性 | 几乎无法 grep `(int)` | `grep static_cast` 立刻找到 |
| 意图表达 | 模糊（"转换"） | 精确（静态、动态、去 const、重解释） |
| 意外 const_cast | 可能 | 不可能（除非显式用 const_cast） |
| 意外 reinterpret_cast | 可能 | 不可能（除非显式用 reinterpret_cast） |
| 代码审查 | 需要人工跟踪类型推导确定实际行为 | 一眼看出 |
| 编译器警告 | 无法区分危险/安全转换 | 可以对 reinterpret_cast 添加警告 |

**规则: 永远不要用 C-style cast。** 如果发现自己在写 `(T)expr`，停下来，写出对应的 named cast。唯一例外是与 C API 互操作时的回调 void* 转换（但即使那边，`static_cast` 也够用）。

### 7.4 `reinterpret_cast` 合法的场景（极少数）

```cpp
// 1. 标准明确允许: 对象指针 → char* / std::byte*（检查对象表示）
T obj;
std::byte* bytes = reinterpret_cast<std::byte*>(&obj);
// 可以读取 sizeof(T) 个字节来检查对象表示

// 2. 往返转换: T1* → T2* → T1*（但在中间的 T2* 解引用仍然是 UB）
//    用于 opaque 句柄/类型擦除

// 3. 函数指针 → 不同签名的函数指针
//    前提: 调用时转换回原签名，否则 UB

// 4. 整数 ↔ 指针往返
//    用 uintptr_t（保证能存下一个指针）:
void* ptr = ...;
uintptr_t addr = reinterpret_cast<uintptr_t>(ptr);
// ... 存储/传输 addr ...
void* back = reinterpret_cast<void*>(addr);
// 标准保证: back == ptr
```

### 7.5 `reinterpret_cast` 不能做的事（常见误解）

```cpp
// ❌ 类型双关 (type punning) — 违反严格别名规则
float f = 3.14f;
int i = *reinterpret_cast<int*>(&f);  // UB! 用 std::bit_cast

// ❌ 直接 reinterpret_cast 去掉 const
const int* p = &x;
int* q = reinterpret_cast<int*>(p);  // 编译错误
// 正确: int* q = const_cast<int*>(p);

// ❌ 在对象构造前/析构后访问其内存
// ❌ 用 reinterpret_cast 做对齐转换
//    (如: char buf[8]; int* p = reinterpret_cast<int*>(buf + 1);)
//    用 std::align 或手动对齐
```

### 7.6 `std::bit_cast` vs `reinterpret_cast` vs `memcpy`

```cpp
// 三种"重新解释位模式"的方式:

float f = 3.14f;

// 方式 1: reinterpret_cast — UB (严格别名违规)
int i1 = *reinterpret_cast<int*>(&f);          // 危险!

// 方式 2: memcpy — 合法，但不 constexpr
int i2;
std::memcpy(&i2, &f, sizeof(f));               // 安全，但运行期

// 方式 3: std::bit_cast — 合法 + constexpr (C++20)
int i3 = std::bit_cast<int>(f);                 // 最佳!

// 反汇编对比 (x86-64 -O2):
// 方式 1: mov eax, [rbp-4]                     ; 一条 mov
// 方式 2: mov eax, [rbp-4]                     ; 被优化成同样的 mov！
// 方式 3: mov eax, [rbp-4]                     ; 也被优化成同样的 mov！

// 但方式 1 是 UB，编译器可能在你没注意到的时候"优化"掉你的代码。
// 方式 2 和 3 合法，编译器保证正确。
```

### 7.7 设计取舍：为什么 C++ 有这么多 cast

这是 C++ 设计哲学的体现——**不给你不想要的东西，但给知道自己在做什么的人后门**：

- **static_cast**: "我知道这个转换在逻辑上是合理的" —— 编译器帮你验证基本约束
- **dynamic_cast**: "我需要在运行时确认假设" —— 为代价换取安全性
- **const_cast**: "我需要修改一个接口声明为 const 但实际上不 const 的对象" —— 给库作者的后门
- **reinterpret_cast**: "我知道自己在做类型系统不允许但内存布局允许的事" —— 系统编程的逃生舱
- **C-style cast**: 历史的遗留，逐级尝试，名字里没有"安全"

---

## 常见面试题

### Q1: `static_cast` 和 `dynamic_cast` 的核心区别是什么？

- `static_cast`: 编译期类型检查，无运行时开销，不验证实际类型。下行转型时不检查指针是否真正指向派生类——错了就是 UB。
- `dynamic_cast`: 运行时通过 vtable/RTTI 验证实际类型。失败时指针版本返回 `nullptr`，引用版本抛出 `std::bad_cast`。要求类有虚函数。多重继承中会自动计算正确的指针偏移。

### Q2: 下面的代码有问题吗？

```cpp
const int x = 42;
int* p = const_cast<int*>(&x);
*p = 100;
```

有。`x` 是真正的 const 对象（可能被放在只读内存段），修改它是未定义行为。`const_cast` 只能用于"去除指向非 const 对象的 const 指针的 const"。

### Q3: 为什么 `dynamic_cast<void*>` 有特殊含义？

它返回指向"最派生对象"起始地址的指针。这在需要比较两个指针是否指向同一个完整对象时有用（比如 engine 中的对象 ID 系统）。普通的 `dynamic_cast<Base*>` 可能返回调整后的指针（指向子对象），而 `dynamic_cast<void*>` 总是返回完整对象的起始地址。

### Q4: C++20 的 `std::bit_cast` 和 `reinterpret_cast` 选哪个？

永远选 `std::bit_cast` 用于类型双关（type punning）。它不违反严格别名规则，constexpr 可用，且编译器生成相同质量的代码。`reinterpret_cast` 的引用解引用形式做类型双关是 UB。

### Q5: 在`-fno-rtti` 环境下，`dynamic_cast` 会发生什么？

编译错误。`dynamic_cast` 完全依赖 RTTI，关闭后无法使用。游戏引擎热路径中几乎从不使用 `dynamic_cast`——这正是原因之一（减少二进制体积 + 避免运行时查询）。替代方案：用虚函数多态、`type` 枚举标记、或用 `std::variant` + `std::visit`。

---

## 延伸主题

- **RTTI 内部机制** — vtable 布局、`type_info` 结构、MSVC vs Itanium ABI 的差异
- **严格别名规则 (Strict Aliasing)** — 为什么 `reinterpret_cast` 做 type punning 是 UB 的深层原因
- **`std::launder`** — 当你 placement new 了新对象后，如何让编译器"忘记"旧指针的 provenance
- **`std::variant` + `std::visit`** — 类型安全的、编译期枚举的替代 dynamic_cast 方案
- **`offsetof` + `container_of`** — 引擎中从成员指针反推对象指针的宏技巧（Linux 内核风格）
- **虚继承的指针调整** — 为什么虚基类的 `dynamic_cast` 比普通多重继承更贵
