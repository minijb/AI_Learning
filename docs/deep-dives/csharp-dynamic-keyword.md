---
title: "C# dynamic 关键字深度剖析"
updated: 2026-06-23
tags: [csharp, dynamic, dlr, call-site, runtime, dotnet, late-binding]
aliases: ["C# dynamic", "DLR 深度剖析", "dynamic 关键字", "动态类型"]
---

# C# `dynamic` 关键字深度剖析

> 深度等级: 第 7 层
> 关联学习计划: 无（独立知识点，与 [[csharp-cpp-stream-deep-dive|C# Stream]]、[[csharp-record-with|record/with]] 同属 C# 语言机制）
> 分析日期: 2026-06-23

---

## 第 1 层: 直觉理解

`dynamic` 是一个**编译器开关**——它告诉 C# 编译器：“这一行先别管类型，运行时再算。”

静态类型像**出门前查天气预报决定穿什么**：编译时（出门前）就确认了每件衣服（类型）合身。`dynamic` 像**带着一整个衣柜出门，到现场再换**：编译器允许你写 `d.Foo()`，不检查 `Foo` 到底存不存在，等程序真正跑到那一行时，运行时才去翻箱倒柜找 `Foo`。

一句话：**`dynamic` 把“类型检查”这件事从编译时推迟到运行时。**

> [!important] dynamic 不是动态类型语言
> 用了 `dynamic` 的 C# 依然是**强类型 + 静态类型**语言。`dynamic` 本质上是 `object` 加上“请运行时帮我绑定”的元数据标记。C# 没有“变成 Python”，只是在这个特定变量上**临时闭上了编译器的眼睛**。

---

## 第 2 层: 使用场景

### 什么时候用

| 场景 | 为什么用 `dynamic` | 替代方案 |
|------|-------------------|---------|
| COM 互操作（Excel/Word 自动化） | 消除 `((Excel.Range)sheet.Cells[1,1]).Value2` 这类痛苦转型 | `dynamic` 让 COM 调用像写脚本 |
| 消费动态语言（IronPython/IronRuby） | Python 对象没有 C# 能识别的静态接口 | 必须用 `dynamic` |
| 解析结构未知的 JSON/配置 | Newtonsoft.Json 早期用 `dynamic` 直接点 `j.Data.Name` | `JsonElement`、`JsonNode`（现代） |
| 鸭子类型（Duck Typing） | 多个不相关类型都有 `Draw()` 方法，想统一调用 | 泛型约束、接口 |
| 反射的语法糖 | `d.Foo(1)` 比 `type.InvokeMember(...)` 干净 | 表达式树、源生成器 |

### 什么时候不用

- **性能关键路径**：每个动态调用点有额外绑定开销（哪怕缓存命中也有一次委托间接调用）。
- **公共 API 契约**：`dynamic` 把类型安全从“编译期保证”降级为“运行时赌博”，库的调用方失去 IDE 提示和编译期检查。
- **能用 `var` / 泛型解决时**：`var` 是编译期类型推断，零运行时开销，永远优先。
- **需要 IDE 智能提示 / 重构 / 跳转**：`dynamic` 变量上按 `.` 无任何成员提示，重命名也追踪不到。
- **NativeAOT / Trim 场景**：`dynamic` 依赖反射，会触发 `IL2026`（`RequiresUnreferencedCode`）裁剪警告，AOT 下可能绑定失败。

### 决策流程

```text
需要访问的成员，编译时能确定类型吗?
    ├─ 能 → 用 var / 具体类型 / 泛型（永远首选）
    └─ 不能 → 是 COM 对象吗?
              ├─ 是 → 用 dynamic（这是它的本职工作）
              └─ 否 → 是动态语言 / 未知 JSON 吗?
                        ├─ 是 → 用 dynamic（或更现代的 JsonNode）
                        └─ 否 → 只是为了少写反射代码吗?
                                  ├─ 是 → 想清楚：值得用运行时开销换这点糖吗?
                                  └─ 否 → 大概率不该用 dynamic
```

> [!tip] 一个判断准则
> 如果你写下 `dynamic` 后，心里清楚运行时它“大概率”是什么类型——那它八成不该是 `dynamic`，应该用 `var` 或接口。`dynamic` 的合理场景是你**真的不知道**运行时会是什么（COM、动态语言、未知结构）。

---

## 第 3 层: API 层

### 3.1 `dynamic` 关键字本身

`dynamic` 不是类，不是类型别名，它是 C# 编译器的一种**上下文关键字**，出现在类型位置时，告诉编译器“这里按运行时绑定处理”。

```csharp
dynamic d = 5;          // d 的静态类型是 dynamic，运行时类型是 int
d = "hello";             // 合法，运行时类型变成 string
d = new Foo();           // 合法
d.Bar();                 // 编译通过，运行时才检查 Bar 是否存在
d.NonExistent();         // 编译通过，运行时抛 RuntimeBinderException
```

### 3.2 隐式转换

`dynamic` 与**任意类型**之间可双向隐式转换：

```csharp
dynamic d = 10;          // int → dynamic（隐式）
int i = d;               // dynamic → int（隐式，运行时检查）
```

### 3.3 与 `object`、`var` 的核心区别

| 维度 | `object o = 5;` | `var v = 5;` | `dynamic d = 5;` |
|------|----------------|-------------|------------------|
| 静态类型 | `object` | `int`（编译器推断） | `dynamic` |
| `o.ToString()` | 编译通过（object 有该方法） | 编译通过 | 编译通过 |
| `o.Foo()` | **编译错误**（object 无 Foo） | 若 int 无 Foo 则编译错误 | 编译通过，**运行时**才检查 |
| 类型检查时机 | 编译期 | 编译期 | 运行期 |
| 运行时开销 | 装箱/拆箱 | 无 | DLR 绑定（首次）+ 委托调用 |
| 能否重新赋值为别的类型 | 能（装箱） | 否（v 是 int） | 能 |

> [!warning] var 不是 dynamic
> 这是初学者最常犯的混淆。`var` 是**编译期**类型推断，`var x = 5;` 之后 `x` 永远是 `int`，和写成 `int x = 5;` 完全等价、零开销。`var` 关键字只在源码层面存在，编译后消失。

### 3.4 方法重载解析中的 `dynamic`

当 `dynamic` 实参参与重载解析时，编译器会在**所有**候选重载中选择一个能在运行时绑定的；若实参是 `dynamic`，对应的形参位置会被当作“通配”。

```csharp
void M(int x)      { /* A */ }
void M(string x)   { /* B */ }

dynamic d = 5;
M(d);   // 运行时绑定到 M(int) → A

d = "hi";
M(d);   // 运行时绑定到 M(string) → B
```

> [!warning] 重载决议的陷阱
> 如果所有重载都需要在编译期决定的类型信息，`dynamic` 实参可能让编译器退而选择 `object` 重载，或抛出 `RuntimeBinderException`。把 `dynamic` 喂给泛型方法时，类型参数会被推断为 `dynamic`，传染整个调用链。

### 3.5 `ExpandoObject` — 开箱即用的动态对象

```csharp
using System.Dynamic;

dynamic person = new ExpandoObject();
person.Name = "Alice";
person.Age = 30;
person.SayHi = (Action)(() => Console.WriteLine($"Hi, I'm {person.Name}"));

person.SayHi();          // 输出: Hi, I'm Alice

// 可增删成员，还可当字典用（实现 IDictionary<string, object>）
var dict = (IDictionary<string, object>)person;
dict.Remove("Age");
```

适用：配置对象、临时数据载体、原型设计。**不适用**：需要类型安全、性能、或被持久化/序列化契约约束的场景。

### 3.6 `DynamicObject` — 自定义动态行为

继承 `DynamicObject` 可精确控制每个动态操作的语义：

```csharp
public class PropertyBag : DynamicObject
{
    private readonly Dictionary<string, object> _data = new();

    // 拦截 d.Foo（取成员）
    public override bool TryGetMember(GetMemberBinder binder, out object result)
        => _data.TryGetValue(binder.Name, out result);

    // 拦截 d.Foo = x（设成员）
    public override bool TrySetMember(SetMemberBinder binder, object value)
    {
        _data[binder.Name] = value;
        return true;
    }

    // 拦截 d(1, 2)（像函数一样调用对象）
    public override bool TryInvoke(InvokeBinder binder, object[] args, out object result)
    {
        result = null;
        return false;
    }

    // 还有 TryInvokeMember / TryGetIndex / TrySetIndex / TryBinaryOperation / TryUnaryOperation / TryConvert
}
```

### 3.7 `IDynamicMetaObjectProvider` — 最底层接口

`DynamicObject` 实现的接口。直接实现它可返回 `Expression`（表达式树），把动态操作编译为 IL——这是 DLR 与各语言互操作的基石，自定义难度高，极少在业务代码中使用。

### 3.8 `Microsoft.CSharp.RuntimeBinder.Binder` — 绑定器工厂

C# 编译器为每个动态操作生成的代码会调用此工厂创建绑定器。主要方法（均为静态）：

| 方法 | 对应操作 | 示例 |
|------|---------|------|
| `Binder.InvokeMember` | `d.Foo(args)` | 方法调用 |
| `Binder.GetMember` | `d.Prop` | 取属性/字段 |
| `Binder.SetMember` | `d.Prop = x` | 设属性/字段 |
| `Binder.GetIndex` | `d[i]` | 索引取值 |
| `Binder.SetIndex` | `d[i] = x` | 索引赋值 |
| `Binder.UnaryOperation` | `-d`、`d++` | 一元运算 |
| `Binder.BinaryOperation` | `d + e`、`d == e` | 二元运算 |
| `Binder.Convert` | `(int)d` | 类型转换 |
| `Binder.Invoke` | `d(args)` | 委托/可调用对象调用 |

---

## 第 4 层: 行为契约

### 前置条件

- 目标对象在运行时**确实存在**被引用的成员（方法/属性/索引器/运算符），且访问修饰符允许调用方访问。
- 若引用 `Microsoft.CSharp` 程序集（.NET Core / .NET 5+ 在某些场景需显式 NuGet 引用，多数 SDK 项目模板已隐含）。
- NativeAOT / 裁剪场景下，相关类型的元数据未被裁剪。

### 后置条件

- 绑定成功：调用按目标类型的真实成员语义执行，返回值类型为 `dynamic`（即继续推迟到运行时）。
- 绑定失败：抛出 `Microsoft.CSharp.RuntimeBinder.RuntimeBinderException`。

### 不变量

- `dynamic` 变量的**静态类型**始终是 `dynamic`（底层是 `object`），但**运行时类型**随赋值变化。
- `dynamic` 具有**传染性**：任何包含 `dynamic` 操作数的表达式，其结果类型也是 `dynamic`（如 `dynamic + int` → `dynamic`）。
- `dynamic` 实参传入泛型方法时，类型参数被推断为 `dynamic`，传染整个泛型调用。

### 异常列表

| 异常 | 触发场景 |
|------|---------|
| `RuntimeBinderException` | 成员不存在、参数不匹配、访问修饰符拒绝、运算符未定义 |
| `RuntimeBinderInternalCompilerException` | DLR 绑定器内部错误（极少见，属框架 bug） |
| `NullReferenceException` | `dynamic d = null; d.Foo();` 时 d 为 null |
| `DivideByZeroException` 等 | 绑定成功后，操作本身的运行时异常正常传播 |

### 线程安全声明

`dynamic` 关键字本身**不提供任何线程安全保证**。两点需注意：

1. 每个动态调用点的 `CallSite<T>` 缓存是线程安全的（DLR 用原子操作更新 `Target` 委托），多线程调用同一调用点不会损坏缓存。
2. 但被调用的目标对象本身的线程安全性，与是否用 `dynamic` 无关——`dynamic` 不加锁、不排队。

> [!warning] dynamic 不消除竞态
> `(d as SomeType)?.DoStuff()` 改成 `d.DoStuff()` 不会变得“更线程安全”。`dynamic` 只改变绑定时机，不改变并发语义。

---

## 第 5 层: 实现原理

### 5.1 DLR（Dynamic Language Runtime）登场

`dynamic` 的魔法全部来自 **DLR**——一组位于 `System.Dynamic.*` / `System.Linq.Expressions` / `Microsoft.CSharp` 的库，它本质上是“运行时迷你编译器 + 多级缓存”。

DLR 三个核心角色：

| 角色 | 职责 | 所在 |
|------|------|------|
| **CallSite（调用点）** | 每个动态操作在源码中的位置，缓存绑定结果 | `System.Runtime.CompilerServices.CallSite<T>` |
| **Binder（绑定器）** | “在这一刻，这个对象上的这个操作该映射到什么代码” | `Microsoft.CSharp.RuntimeBinder.Binder` |
| **Expression Tree（表达式树）** | 绑定结果被编译成可执行的委托 | `System.Linq.Expressions` |

### 5.2 绑定流程（伪代码）

```text
执行 d.Foo(42):
  1. 取出调用点的缓存 CallSite site = <SiteContainer>.<>p__SiteFoo
  2. 若 site == null:
       site = CallSite<Func<CallSite, object, int, object>>.Create(
                  Binder.InvokeMember(...))   // 创建绑定器，先不绑定
  3. 调用委托: result = site.Target(site, d, 42)
  4. site.Target 内部:
       a. 检查 L0 缓存（单条最近绑定）是否匹配 d 的运行时类型
          ├─ 匹配 → 直接执行缓存的委托，返回（最快路径）
          └─ 不匹配 → 进入 Update（更新流程）
       b. Update: 调用 Binder，用反射查 d 的真实类型是否有 Foo(int)
          ├─ 找到 → 编译成新的 Expression Tree → 委托
          │         存入 L1/L2 多态缓存，更新 L0 的 Target
          │         执行新委托，返回
          └─ 找不到 → 抛 RuntimeBinderException
```

### 5.3 多态内联缓存（Polymorphic Inline Cache, PIC）

这是 `dynamic` 性能能“基本可用”的关键，与 V8 引擎用的是同一类技术。

- **L0 缓存**：`CallSite<T>.Target`，**单条**最近绑定的委托（无类型判断，直接调）。
- **L1 缓存**：调用点上的多态缓存，存若干条“类型 → 委托”规则（带类型测试）。
- **L2 缓存**：Binder 上的全局缓存，跨调用点共享。

为什么叫“多态内联缓存”：

- **多态**：一个调用点可缓存**多种**运行时类型对应的绑定。
- **内联**：缓存就在调用点本身上，就地命中。
- **缓存**：三级，命中率从高到低。

```text
效果:
  d = 5;  d++;  d++;  d++; ...    // 第一次绑定后，后续全是 L0 命中，接近原生++
  d = 5; d++; d = "x"; d++; ...   // 在 int/string 间切换，命中 L1，稍慢但仍远快于反射
  类型频繁变化 → 缓存频繁失效 → 接近每次都重新绑定（最坏情况）
```

### 5.4 复杂度分析

| 情况 | 单次调用开销 |
|------|------------|
| L0 缓存命中（同一类型连续调用） | 常数级，约一次委托间接调用，接近直接调用 |
| L1/L2 缓存命中（少数类型轮换） | 常数级 + 类型测试，略慢 |
| 首次绑定 / 缓存未命中 | 反射查元数据 + 编译表达式树，显著开销（微秒级） |
| 最坏（类型高度发散，缓存反复失效） | 接近每次都重新绑定 |

> [!info] 为什么 dynamic 比裸反射快
> 传统 `MethodInfo.Invoke` 每次都做参数装箱、可见性检查、安全检查。`dynamic` 把这些一次性做完后**编译成强类型委托**缓存，后续调用绕过反射走直接委托。所以“热路径上反复动态调用”时，`dynamic` 显著快于裸反射；但“每个对象类型都不同、缓存打不中”时退化。

---

## 第 6 层: 源码分析

> 以下源码基于 **dotnet/runtime** 仓库（以 .NET 8 为参考版本）及 C# 编译器的真实代码生成结果。引用的关键类型：
> - `System.Runtime.CompilerServices.CallSite<T>` — 源文件 `CallSite.cs`，程序集 `System.Dynamic.Runtime.dll`
> - `Microsoft.CSharp.RuntimeBinder.Binder` — 程序集 `Microsoft.CSharp.dll`

### 6.1 编译器为动态操作生成了什么

源代码：

```csharp
dynamic d = 100;
d++;
```

编译器实际生成的等价 C#（简化自真实反编译结果，参考 szKarlen 的 DLR 深度分析）：

```csharp
object d = 100;
object arg = d;

if (Program.<dynamicMethod>o__SiteContainerd.<>p__Sitee == null)
{
    Program.<dynamicMethod>o__SiteContainerd.<>p__Sitee =
        CallSite<Func<CallSite, object, object>>.Create(
            Binder.UnaryOperation(
                CSharpBinderFlags.None,
                ExpressionType.Increment,
                typeof(Program),
                new CSharpArgumentInfo[]
                {
                    CSharpArgumentInfo.Create(CSharpArgumentInfoFlags.None, null)
                }));
}

d = Program.<dynamicMethod>o__SiteContainerd.<>p__Sitee.Target(
        Program.<dynamicMethod>o__SiteContainerd.<>p__Sitee, arg);
```

关键观察：

1. **`dynamic d` 变成了 `object d`**——证实第 1 层的论断，`dynamic` 底层就是 `object` 加绑定元数据。
2. 编译器生成一个**静态容器类** `<dynamicMethod>o__SiteContainerd`，里面是各调用点的 `CallSite` 字段。这些字段在静态方法体中是 `static`，在实例方法中是实例字段——调用点缓存因此随作用域生命周期存在。
3. **惰性创建**：`CallSite` 首次使用时 `Create`，之后复用。
4. **`Target` 委托**：实际执行的就是 `Target(site, arg)`——这就是第 5 层说的 L0 缓存。

### 6.2 `CallSite<T>` 的结构

```csharp
public sealed class CallSite<T> : CallSite where T : class
{
    public T Target;              // L0 缓存：当前生效的绑定委托
    public T Update { get; }      // 缓存未命中时，触发重新绑定的委托
    public static CallSite<T> Create(CallSiteBinder binder);
}
```

设计要点：

- `Target` 是泛型委托（如 `Func<CallSite, object, object>`），**签名在编译期就由操作类型确定**——这就是为什么缓存命中的委托能高效执行：参数类型、返回类型都已强类型化，无运行时装箱（相对于裸反射）。
- `Update` 是“兜底委托”：当 `Target` 发现当前对象类型不匹配缓存时，`Target` 内部转调 `Update`，由 `Update` 调用 `Binder` 重新解析，然后把新委托**原子地写回 `Target`**。

`Create` 的核心：

```csharp
public static CallSite<T> Create(CallSiteBinder binder)
{
    if (!typeof(T).IsSubclassOf(typeof(MulticastDelegate)))
        throw Error.TypeMustBeDerivedFromSystemDelegate();
    return new CallSite<T>(binder);
}
```

### 6.3 Binder 如何决定绑定

`Microsoft.CSharp.RuntimeBinder.Binder` 的工厂方法（如 `InvokeMember`）返回一个 `CallSiteBinder` 子类。它的工作是：

1. 用反射读取目标对象的运行时类型。
2. 运行 C# 的**成员查找规则**（可见性、扩展方法、运算符重载、隐式转换……）——注意：这是“迷你版 C# 编译器”在运行时跑了一遍语义分析。
3. 产出一棵 `Expression`（表达式树），等价于“如果编译时知道类型，会生成的代码”。
4. DLR 把这棵树**编译成委托**，装进 `CallSite.Target`。

> [!note] 为什么运行时需要“迷你 C# 编译器”
> 因为动态绑定的目标是**复现 C# 语言的重载解析规则**——比如 `d + e` 要按 C# 的二元运算符查找规则（用户定义运算符、内置运算符、可空提升……）。这套规则极其复杂，不可能用几行反射写完，所以 DLR 复用了 Roslyn 之前的 C# 语义分析组件。

### 6.4 自定义绑定的入口：`IDynamicMetaObjectProvider`

当目标对象自己实现了 `IDynamicMetaObjectProvider`（如 `DynamicObject`、`ExpandoObject`、IronPython 对象），Binder 会把绑定权**交给对象自己**：

```csharp
public interface IDynamicMetaObjectProvider
{
    DynamicMetaObject GetMetaObject(Expression parameter);
}
```

`DynamicMetaObject` 携带一棵 `Expression`——对象自己决定 `d.Foo` 应该变成什么代码。这就是 IronPython 能让 C# 调用 Python 对象的底层机制：Python 对象实现 `IDynamicMetaObjectProvider`，返回符合 Python 语义的表达式树。

---

## 第 7 层: 对比与边界

### 7.1 `dynamic` vs `var` vs `object`（最常被混为一谈的三者）

| 维度 | `object` | `var` | `dynamic` |
|------|----------|-------|-----------|
| 类型检查时机 | 编译期 | 编译期（推断后） | 运行期 |
| 静态类型 | `object` | 推断出的真实类型 | `dynamic`（底层 `object`） |
| 值类型存储 | 装箱 | 直接 | 装箱（底层 object） |
| `d.Foo()` 若成员不存在 | 编译错误 | 编译错误 | **运行时** `RuntimeBinderException` |
| IDE 智能提示 | 仅 object 成员 | 完整 | 无 |
| 重构/重命名追踪 | 支持 | 支持 | 不支持 |
| 运行时开销 | 装箱/拆箱 | 无 | DLR 绑定 |
| 适用 | 通用基类/集合异构 | 编译期类型推断 | 运行期才知类型 |

### 7.2 `dynamic` vs 反射

| 维度 | `dynamic` | `MethodInfo.Invoke` 反射 |
|------|-----------|------------------------|
| 首次调用开销 | 高（编译表达式树） | 高（可见性检查、装箱） |
| 重复同类型调用 | **接近直接调用**（缓存命中） | 每次都走反射，慢 |
| 语法可读性 | `d.Foo(1)` | `mi.Invoke(d, new object[]{1})` |
| 编译期检查 | 无 | 无 |
| 灵活性 | 受 C# 语义约束 | 任意（可调 private、跳过可见性） |
| AOT/Trim 友好 | 不友好（IL2026 警告） | 不友好 |

> [!tip] 性能经验法则（近似值，随场景波动）
> 设直接调用为 1×，缓存命中的 `dynamic` 约 1.5–3×，裸 `MethodInfo.Invoke` 约 50–100×。若需高性能反射，现代 .NET 推荐 `Expression.Compile` 成委托缓存，或用源生成器在编译期生成调用代码（零运行时反射）。

### 7.3 `dynamic` vs 泛型

| 场景 | `dynamic` | 泛型 |
|------|-----------|------|
| 多个类型有同名方法 | `d.Foo()` 鸭子调用 | 定义接口 `IFoo`，约束 `where T : IFoo` |
| 类型安全 | 无 | 有 |
| 性能 | 运行时绑定 | 编译期单态化/虚调用，最优 |
| 表达能力 | 强（任意成员） | 弱（需接口/约束声明） |
| AOT 友好 | 否 | 是 |

**结论**：能用泛型 + 接口表达“鸭子类型”时，永远优于 `dynamic`。`dynamic` 的合理位置是“接口方案不可行”（如 COM、跨语言、真正未知的结构）。

### 7.4 已知局限与坑

> [!warning] dynamic 的硬限制
> 1. **扩展方法**：`dynamic` 变量上看不到扩展方法（绑定器不扫描扩展方法命名空间）。需显式当静态方法调用 `MyExtensions.Foo(d)`。
> 2. **不能作为约束**：不能写 `where T : dynamic`，也不能让类继承 `dynamic`。
> 3. **Lambda/匿名函数**：`Func<int> f = () => 1; dynamic d = f;` 合法；但 `dynamic d = x => x + 1;`（直接赋 lambda）**编译错误**——lambda 无法隐式转 `dynamic`，需显式声明委托类型。
> 4. **方法组**：`dynamic d = obj.ToString;`（方法组）编译错误，需 `new Func<string>(obj.ToString)`。
> 5. **传染性**：`dynamic` 一旦混入表达式，结果类型被传染为 `dynamic`，可能让后续本应编译期检查的代码静默退化为运行时检查。
> 6. **AOT/裁剪**：`dynamic` 依赖反射，NativeAOT 下产生 `IL2026` 警告，裁剪后可能绑定失败。

### 7.5 设计取舍：为什么 C# 要加 `dynamic`

C# 4.0（2010）引入 `dynamic` 的主要动机是 **Office COM 互操作**。在 `dynamic` 之前，写 Excel 自动化代码充斥着：

```csharp
((Excel.Range)((Excel.Worksheet)workbook.Sheets[1]).Cells[1, 1]).Value2 = "data";
```

有了 `dynamic`：

```csharp
dynamic sheet = workbook.Sheets[1];
sheet.Cells[1, 1].Value2 = "data";
```

附带收益是与 IronPython/IronRuby 互操作、JSON 解析的便利。代价是引入了 DLR 的复杂性和运行时开销。现代 .NET 更推崇 `System.Text.Json` 的 `JsonNode`、源生成器、接口约束等**编译期确定**的方案，`dynamic` 在新代码中的份额在下降。

---

## 常见面试题

1. `dynamic` 和 `var` 有什么区别？什么时候该用哪个？
2. 下面代码会发生什么？为什么？
   ```csharp
   dynamic d = 5;
   d = "hello";
   d++;
   ```
3. `dynamic` 在运行时是如何找到成员的？为什么它比直接反射 `MethodInfo.Invoke` 快？
4. `dynamic` 变量能调用扩展方法吗？为什么？
5. `dynamic` 会影响 NativeAOT / 程序集裁剪吗？为什么？

---

## 面试题参考答案

> [!tip]- 题目 1 参考答案
> **`var` 是编译期类型推断，`dynamic` 是运行期绑定。**
>
> `var x = 5;` 与 `int x = 5;` 完全等价，编译后 `var` 消失，`x` 静态类型永远是 `int`，调用不存在的方法编译期就报错，零运行时开销。`dynamic d = 5;` 则让编译器放弃对 `d` 的编译期检查，任何 `d.Foo()` 都编译通过，运行时才解析。
>
> **选择准则**：编译期就知道类型 → 一律用 `var`（或显式类型）；只有运行期才知道类型（COM、IronPython、结构未知的 JSON）才考虑 `dynamic`。能用泛型/接口表达鸭子类型时，永远优于 `dynamic`。

> [!tip]- 题目 2 参考答案
> **前两行成功，第三行抛 `RuntimeBinderException`。**
>
> - `d = 5;`：运行时类型为 `int`。
> - `d = "hello";`：`dynamic` 可重新赋任意类型，运行时类型变为 `string`。
> - `d++;`：编译通过（编译器对 `dynamic` 不检查 `++` 运算符），运行时 DLR 尝试在 `string` 上绑定 `++` 运算——`string` 没有定义 `++` 运算符，绑定失败，抛 `RuntimeBinderException`。
>
> 这正说明 `dynamic` 把本该编译期发现的错误推迟到了运行期。如果写 `var s = "hello"; s++;`，编译期就会直接报错。

> [!tip]- 题目 3 参考答案
> **通过 DLR 的 CallSite + Binder + 多级缓存实现，缓存命中后走预编译的强类型委托，绕过了反射的逐次开销。**
>
> 机制：
> 1. 编译器为每个动态操作生成一个 `CallSite<T>` 调用点。
> 2. 首次调用时，`Binder`（`Microsoft.CSharp.RuntimeBinder`）用反射查目标类型的成员，按 C# 语义规则解析，生成一棵表达式树并**编译成委托**，存入缓存。
> 3. `CallSite` 有 L0（`Target`，单条最近绑定）/ L1 / L2 三级缓存（多态内联缓存，PIC，与 V8 同类技术）。
>
> 为什么比裸反射快：`MethodInfo.Invoke` 每次都做可见性检查、参数装箱、安全检查；`dynamic` 把这些一次性做完后编译成强类型委托缓存，后续命中 L0 时只剩一次委托间接调用，接近直接调用。代价是首次绑定开销大、类型频繁变化时缓存失效会退化。

> [!tip]- 题目 4 参考答案
> **不能直接调用。** 在 `dynamic` 变量上调用的成员，DLR 的 C# 绑定器不会扫描扩展方法的命名空间——它只查找实例成员。`d.MyExtension()` 会编译通过，运行时抛 `RuntimeBinderException`（找不到实例方法）。
>
> 变通：把扩展方法当普通静态方法显式调用：
>
> ```csharp
> MyExtensions.MyExtension(d);
> ```
>
> 这也是 `dynamic` 的一个已知硬限制，详见第 7.4 节。

> [!tip]- 题目 5 参考答案
> **会，且通常有 IL2026（`RequiresUnreferencedCode`）裁剪警告。**
>
> `dynamic` 的运行时绑定依赖**反射**读取目标类型的成员元数据。程序集裁剪（Trimming）和 NativeAOT 会移除“看似没人用”的类型/成员元数据，但 DLR 的绑定器是在运行时才决定查哪些类型——裁剪器无法静态分析出这些类型会被用到，于是可能把它们裁掉。
>
> 后果：发布为 AOT/裁剪应用后，原本能绑定的成员可能因元数据被裁而抛 `RuntimeBinderException` 或 `MissingMetadataException`。ILLink 分析器会针对 `dynamic` 调用产生 `IL2026` 警告提醒开发者。现代 .NET 推荐在 AOT 场景用源生成器、`System.Text.Json` 的源生成模式等编译期确定的方案替代 `dynamic`。

---

## 延伸主题

- [[csharp-record-with|C# record 与 with 表达式]] — 另一类“编译器帮你生成代码”的语言特性，但方向相反（编译期确定，零运行时开销）
- [[csharp-cpp-stream-deep-dive|C# Stream 深度剖析]] — 同属“抽象 + 多态分发”机制，对比编译期多态（虚方法）与运行期多态（dynamic）
- **DLR 与 IronPython 互操作** — `IDynamicMetaObjectProvider` 如何让 C# 调用动态语言对象
- **`System.Text.Json` 的 `JsonNode` / `JsonProperty`** — 现代替代 `dynamic` 解析未知 JSON 的类型安全方案
- **源生成器（Source Generators）与 `Expression.Compile`** — 高性能反射替代方案，编译期/一次性编译期生成调用代码
- **多态内联缓存（PIC）** — 同一思想在 V8、LuaJIT、JVM 中的体现，跨语言对比动态调度优化
