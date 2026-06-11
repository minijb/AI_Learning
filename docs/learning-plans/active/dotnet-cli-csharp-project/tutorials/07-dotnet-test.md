---
title: "dotnet test — 单元测试"
updated: 2026-06-10
tags: [dotnet, cli, test, xunit, unit-testing]
---

# dotnet test — 单元测试

> 所属计划: [[../plan|dotnet CLI 与 C# 工程构建]]
> 预计耗时: 60 分钟
> 前置知识: [[06-csproj-and-sln-deep-dive|项目文件结构深入]]

---

## 1. 概念讲解

### 为什么需要单元测试

单元测试是对代码中**最小可测试单元**（通常是方法）进行隔离验证的自动化测试。在 .NET 生态中，单元测试不是可选的"加分项"——它是 CI/CD 流水线的基石、重构的安全网，以及代码设计的"活文档"。

`dotnet test` 是 .NET SDK 内置的测试运行命令。它不绑定任何特定测试框架，而是通过适配器模式支持多种框架。

### 三大测试框架对比

.NET 有三个主流测试框架。它们的功能趋同，但设计哲学和生态各有侧重：

| 维度 | **xUnit** | **NUnit** | **MSTest** |
|------|-----------|-----------|------------|
| 定位 | 现代化，为 .NET Core 而生 | 老牌经典，源自 JUnit 移植 | 微软官方，深度 VS 集成 |
| 测试标识 | `[Fact]` / `[Theory]` | `[Test]` / `[TestCase]` | `[TestMethod]` |
| 初始化/清理 | 构造函数 + `IDisposable` | `[SetUp]` / `[TearDown]` | `[TestInitialize]` / `[TestCleanup]` |
| 参数化测试 | `[Theory]` + `[InlineData]` | `[TestCase]` + 属性参数 | `[DataTestMethod]` + `[DataRow]` |
| 断言模型 | `Assert` 静态类 | `Assert.That` + 约束模型 | `Assert` 静态类 |
| 生命周期 | 每个测试方法 → 新建实例 | 可用 `[SetUp]` 复用夹具 | 每个测试方法 → 新建实例 |
| 扩展性 | 强（内置依赖注入支持） | 强（丰富的扩展点） | 中等（VS 集成优先） |
| 适用场景 | **默认推荐**，新项目首选 | 历史项目，跨平台延续 | VS 重度用户，Azure DevOps |

> [!tip] 选型建议
> **新项目默认选 xUnit**。它是 .NET 团队自己用于测试 ASP.NET Core 和 EF Core 的框架，与现代 .NET 的理念最契合。NUnit 的优势在于遗留项目迁移和丰富的约束模型；MSTest 的优势在于与 Visual Studio Enterprise 的深度集成（如 Live Unit Testing）。

### 框架的生命周期差异

这是一个关键差异，直接影响测试代码的写法：

```csharp
// ═══════════════════════ xUnit 生命周期 ═══════════════════════
// 每个 [Fact] 执行时，xUnit 会 new 一个新的 CalculatorTests 实例。
// 构造函数 = SetUp, IDisposable.Dispose = TearDown。
public class CalculatorTests : IDisposable
{
    private readonly Calculator _calc;

    public CalculatorTests()           // ← 每个测试都跑一次
    {
        _calc = new Calculator();
    }

    [Fact]
    public void Add_TwoNumbers_ReturnsSum()
    {
        Assert.Equal(3, _calc.Add(1, 2));
    }

    public void Dispose()              // ← 每个测试都跑一次
    {
        // 清理资源
    }

    // 共享夹具（所有测试共享同一个实例）：实现 IClassFixture<T>
}

// ═══════════════════════ NUnit 生命周期 ═══════════════════════
// [SetUp] 和 [TearDown] 是独立的特性方法。
[TestFixture]
public class CalculatorTests
{
    private Calculator _calc;

    [SetUp]
    public void Setup() { _calc = new Calculator(); }

    [TearDown]
    public void Teardown() { /* 清理 */ }

    [Test]
    public void Add_TwoNumbers_ReturnsSum()
    {
        Assert.That(_calc.Add(1, 2), Is.EqualTo(3));
    }

    // 共享夹具：[OneTimeSetUp] / [OneTimeTearDown]
}

// ═══════════════════════ MSTest 生命周期 ═══════════════════════
[TestClass]
public class CalculatorTests
{
    private Calculator _calc;

    [TestInitialize]
    public void Setup() { _calc = new Calculator(); }

    [TestCleanup]
    public void Cleanup() { /* 清理 */ }

    [TestMethod]
    public void Add_TwoNumbers_ReturnsSum()
    {
        Assert.AreEqual(3, _calc.Add(1, 2));
    }

    // 共享夹具：[ClassInitialize] / [ClassCleanup]（需要是静态方法）
}
```

> [!note] xUnit 的"反模式"设计
> xUnit 刻意不使用 `[SetUp]` / `[TearDown]` 特性——它认为如果你的测试需要这些，说明测试类承担了太多职责，应该拆分。构造函数 + `IDisposable` 迫使你把它当成**普通的 C# 对象**来设计，而不是依赖框架魔法。这减少了测试间的耦合，也更容易调试。

---

## 2. 创建测试项目

### 三种模板

```bash
# xUnit（推荐）
dotnet new xunit -n MyLib.Tests

# NUnit
dotnet new nunit -n MyLib.Tests

# MSTest
dotnet new mstest -n MyLib.Tests
```

执行后得到的三者 `.csproj` 差异：

```xml
<!-- xUnit 模板生成的 .csproj -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <IsPackable>false</IsPackable>   <!-- 测试项目不需要打包 -->
    <IsTestProject>true</IsTestProject>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="coverlet.collector" Version="6.0.2" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />
    <PackageReference Include="xunit" Version="2.9.2" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2" />
  </ItemGroup>

  <ItemGroup>
    <Using Include="Xunit" />
  </ItemGroup>
</Project>
```

每个模板都包含三个核心 NuGet 包：

| 包 | 作用 | 框架无关 |
|----|------|---------|
| `Microsoft.NET.Test.Sdk` | `dotnet test` 的入口点，发现和执行测试 | 所有框架都需要 |
| `<Framework>`（如 `xunit`） | 测试框架本身：特性、断言、运行器 API | 框架专属 |
| `<Framework>.runner.visualstudio` | Visual Studio 测试适配器 → `dotnet test` 可运行 | 框架专属 |

> [!note] `IsTestProject` 属性
> .NET 8+ 引入的 `<IsTestProject>true</IsTestProject>` 属性。它让 `dotnet test` 能更快地发现测试项目，而不需要扫描所有项目来检查是否引用了测试 SDK。从 .NET 8 模板开始，新测试项目默认包含此属性。

---

## 3. `dotnet test` 命令详解

### 3.1 基本用法

```bash
# 在当前目录或解决方案中运行所有测试
dotnet test

# 运行指定项目的测试
dotnet test tests/MyLib.Tests

# 指定解决方案中运行
dotnet test MySolution.sln
```

输出示例：

```
  Determining projects to restore...
  All projects are up-to-date for restore.
  MyLib.Tests -> D:\src\MyLib.Tests\bin\Debug\net9.0\MyLib.Tests.dll
Test run for D:\src\MyLib.Tests\bin\Debug\net9.0\MyLib.Tests.dll (.NETCoreApp,Version=v9.0)
VSTest version 17.11.1 (x64)

Starting test execution, please wait...
A total of 1 test files matched the specified pattern.

Passed!  - Failed:     0, Passed:     8, Skipped:     0, Total:     8, Duration: 45 ms
```

### 3.2 过滤测试：`--filter`

`--filter` 使用 VSTest 的过滤表达式语法。最常用的模式：

```bash
# 按完全限定名（类名.方法名）模糊匹配 → 运行包含 "Add" 的测试
dotnet test --filter "FullyQualifiedName~Add"

# 按完全限定名精确匹配
dotnet test --filter "FullyQualifiedName=MyLib.Tests.CalculatorTests.Add_TwoNumbers_ReturnsSum"

# 按测试类名过滤（注意：这是 FullyQualifiedName 的子串匹配）
dotnet test --filter "FullyQualifiedName~CalculatorTests"

# 按 Trait（特性分类）过滤
dotnet test --filter "Category=Integration"
dotnet test --filter "Category!=Slow"           # 排除慢测试
dotnet test --filter "Category=Unit|Category=Integration"  # 组合：OR 用 |

# 组合多个条件
dotnet test --filter "FullyQualifiedName~Calculator&Category=Unit"
```

> [!tip] Trait 过滤的工作原理
> 在 xUnit 中，`[Trait("Category", "Integration")]` 特性会被 VSTest 解释为 `Category=Integration`。在 NUnit 中对应 `[Category("Integration")]`；在 MSTest 中对应 `[TestCategory("Integration")]`。

常用过滤运算符：

| 运算符 | 含义 | 示例 |
|--------|------|------|
| `=` | 精确等于 | `Category=Unit` |
| `!=` | 不等于 | `Category!=Slow` |
| `~` | 包含（子串） | `FullyQualifiedName~Add` |
| `\|` | 或（OR） | `Name~Add\|Name~Subtract` |
| `&` | 与（AND） | `Category=Unit&Name~Calculator` |

### 3.3 配置和输出选项

```bash
# 指定配置（Debug/Release）
dotnet test -c Release

# 使用特定日志器
dotnet test --logger "console;verbosity=detailed"      # 控制台详细输出
dotnet test --logger "trx;LogFileName=TestResults.trx"  # TRX 文件
dotnet test --logger "html;LogFileName=TestResults.html" # HTML（需要额外包）

# 多个日志器
dotnet test --logger "console;verbosity=detailed" --logger "trx"

# 跳过编译和还原（已确认代码没有变化时，加速反复执行）
dotnet test --no-build --no-restore
```

**TRX（Test Results XML）** 是 MSTest 时代的遗留格式，但被所有框架支持。它是 Azure DevOps / TeamCity 等 CI 系统解析测试结果的标准格式。

### 3.4 代码覆盖率：`coverlet`

coverlet 是 .NET 跨平台代码覆盖率工具。两种集成方式：

**方式一：coverlet.collector（推荐，模板自带）**

`dotnet new xunit` 模板已包含 `coverlet.collector` 包。运行时加上 `--collect` 参数：

```bash
# 收集覆盖率数据，输出 coverage.cobertura.xml
dotnet test --collect:"XPlat Code Coverage"

# 输出示例：
# Attachments:
#   D:\src\MyLib.Tests\TestResults\<guid>\coverage.cobertura.xml
```

**方式二：coverlet.msbuild（更灵活）**

```bash
# 先安装工具
dotnet tool install -g coverlet.console

# 或添加 MSBuild 集成包
dotnet add package coverlet.msbuild

# 运行
dotnet test /p:CollectCoverage=true /p:CoverletOutputFormat=cobertura
```

常用 coverlet MSBuild 参数：

```bash
# 生成多种格式
dotnet test /p:CollectCoverage=true \
            /p:CoverletOutputFormat="cobertura,json" \
            /p:CoverletOutput="./TestResults/"

# 排除某些程序集
dotnet test /p:CollectCoverage=true \
            /p:Exclude="[*]MyLib.Models.*"

# 设置覆盖率门槛（不达标则测试失败）
dotnet test /p:CollectCoverage=true \
            /p:Threshold=80 \
            /p:ThresholdType=line
```

### 3.5 生成 HTML 覆盖率报告

cobertura XML 本身是人类可读的 XML 格式。如需 HTML 可视化报告，使用 `reportgenerator`：

```bash
# 安装工具
dotnet tool install -g dotnet-reportgenerator-globaltool

# 运行测试并收集覆盖率
dotnet test --collect:"XPlat Code Coverage"

# 生成 HTML 报告
reportgenerator \
    -reports:"**/coverage.cobertura.xml" \
    -targetdir:"coveragereport" \
    -reporttypes:Html

# Windows 上打开
start coveragereport/index.html
```

---

## 4. 编写 xUnit 测试

### 4.1 `[Fact]` — 无参数测试

`[Fact]` 表示一个**不需要外部数据**的测试方法。每个 `[Fact]` 方法 = 一个测试用例：

```csharp
using Xunit;

namespace MyLib.Tests;

public class CalculatorTests
{
    private readonly Calculator _calc = new();

    [Fact]
    public void Add_TwoPositiveNumbers_ReturnsSum()
    {
        // Arrange: 准备数据
        int a = 1, b = 2;

        // Act: 执行被测方法
        int result = _calc.Add(a, b);

        // Assert: 验证结果
        Assert.Equal(3, result);
    }

    [Fact]
    public void Divide_ByZero_ThrowsDivideByZeroException()
    {
        // 验证异常
        var ex = Assert.Throws<DivideByZeroException>(
            () => _calc.Divide(10, 0));

        Assert.Equal("Cannot divide by zero.", ex.Message);
    }

    [Fact]
    public void Divide_ValidInput_DoesNotThrow()
    {
        // 验证不抛异常
        var exception = Record.Exception(() => _calc.Divide(10, 2));
        Assert.Null(exception);
    }
}
```

> [!tip] AAA 模式
> Arrange-Act-Assert（准备-执行-断言）是单元测试的事实标准结构。每个测试方法应清晰展示这三步，不要混在一起。

### 4.2 `[Theory]` + `[InlineData]` — 参数化测试

`[Theory]` 表示一个**需要外部数据驱动**的测试。配合 `[InlineData]`，一个方法可以覆盖多组输入：

```csharp
public class CalculatorTests
{
    private readonly Calculator _calc = new();

    [Theory]
    [InlineData(1, 1, 2)]
    [InlineData(0, 0, 0)]
    [InlineData(-1, 1, 0)]
    [InlineData(-5, -3, -8)]
    [InlineData(100, 200, 300)]
    public void Add_VariousInputs_ReturnsExpected(
        int a, int b, int expected)
    {
        int result = _calc.Add(a, b);
        Assert.Equal(expected, result);
    }

    [Theory]
    [InlineData(10, 2, 5)]
    [InlineData(9, 3, 3)]
    [InlineData(0, 5, 0)]
    [InlineData(-10, 2, -5)]
    public void Divide_ValidDivisor_ReturnsExpected(
        double a, double b, double expected)
    {
        double result = _calc.Divide(a, b);
        Assert.Equal(expected, result, precision: 6);
    }
}
```

运行 `dotnet test` 时，每个 `[InlineData]` 会生成一个独立的测试用例。测试运行器输出会显示：

```
Passed MyLib.Tests.CalculatorTests.Add_VariousInputs_ReturnsExpected(a: 1, b: 1, expected: 2)
Passed MyLib.Tests.CalculatorTests.Add_VariousInputs_ReturnsExpected(a: 0, b: 0, expected: 0)
Passed MyLib.Tests.CalculatorTests.Add_VariousInputs_ReturnsExpected(a: -1, b: 1, expected: 0)
...
```

### 4.3 `[Theory]` + `[MemberData]` / `[ClassData]` — 复杂数据源

当测试数据不适合硬编码在特性中时：

```csharp
// 方式一：[MemberData] — 引用本类或其他类的静态属性/方法
public class CalculatorTests
{
    public static IEnumerable<object[]> DivideData =>
        new List<object[]>
        {
            new object[] { 10, 2, 5 },
            new object[] { 9, 3, 3 },
            new object[] { 100, 4, 25 }
        };

    [Theory]
    [MemberData(nameof(DivideData))]
    public void Divide_MemberData_ReturnsExpected(
        double a, double b, double expected)
    {
        Assert.Equal(expected, _calc.Divide(a, b), precision: 6);
    }
}

// 方式二：[ClassData] — 专门的测试数据类
public class CalculatorTestData : TheoryData<int, int, int>
{
    public CalculatorTestData()
    {
        Add(1, 1, 2);
        Add(0, 0, 0);
        Add(-1, 1, 0);
        Add(100, 200, 300);
    }
}

[Theory]
[ClassData(typeof(CalculatorTestData))]
public void Add_ClassData_ReturnsExpected(int a, int b, int expected)
{
    Assert.Equal(expected, _calc.Add(a, b));
}
```

### 4.4 常用断言速查

```csharp
// 相等性
Assert.Equal(expected, actual);                // 值相等（对于对象：.Equals）
Assert.Same(expectedObj, actualObj);           // 引用相等
Assert.NotEqual(expected, actual);

// 布尔
Assert.True(condition);
Assert.False(condition);

// 空值
Assert.Null(obj);
Assert.NotNull(obj);

// 集合
Assert.Empty(collection);
Assert.NotEmpty(collection);
Assert.Contains(item, collection);
Assert.DoesNotContain(item, collection);
Assert.Single(collection);                     // 恰好一个元素

// 异常
Assert.Throws<TException>(() => action());
var ex = Assert.Throws<TException>(() => action());  // 捕获并检查异常消息
Assert.ThrowsAsync<TException>(() => asyncAction()); // 异步异常

// 范围
Assert.InRange(value, low, high);
Assert.NotInRange(value, low, high);

// 类型
Assert.IsType<ExpectedType>(obj);              // 严格类型
Assert.IsAssignableFrom<IInterface>(obj);      // 可赋值类型

// 浮点数（必须指定精度）
Assert.Equal(0.33333, 1.0 / 3.0, precision: 5);

// 字符串
Assert.StartsWith("prefix", str);
Assert.EndsWith("suffix", str);
Assert.Contains("substring", str);
Assert.Matches(@"\d{3}-\d{4}", phoneNumber);   // 正则
```

### 4.5 跳过测试

```csharp
[Fact(Skip = "Not implemented yet")]
public void FutureFeature_DoesSomething() { }

[Theory(Skip = "Bug #42: rounding issue")]
[InlineData(1, 1)]
public void ComplexCalc(int a, int b) { }

// 条件跳过：使用 Trait 配合 --filter 在命令行排除
[Trait("Category", "Slow")]
[Fact]
public void LongRunningIntegrationTest() { }
// 运行: dotnet test --filter "Category!=Slow"  跳过慢测试
```

---

## 5. 引用被测库

测试项目需要引用它要测试的类库项目：

```bash
# 方式一：项目引用（推荐，开发阶段）
dotnet add tests/MyLib.Tests reference src/MyLib

# 方式二：Package 引用（测试已发布的 NuGet 包）
dotnet add tests/MyLib.Tests package MyLib
```

添加后 `.csproj` 中多出：

```xml
<ItemGroup>
  <ProjectReference Include="..\..\src\MyLib\MyLib.csproj" />
</ItemGroup>
```

> [!warning] 项目引用路径是相对的
> `<ProjectReference>` 中的路径是相对于测试项目 `.csproj` 位置的。移动项目文件后必须同步更新。推荐使用 `..\` 相对路径遍历到解决方案根目录，如 `..\..\src\MyLib\MyLib.csproj`。

---

## 6. 完整实战示例

### 场景：创建一个 Calculator 类库并用 xUnit 测试

#### 步骤

```bash
# 1. 创建解决方案
mkdir CalculatorDemo && cd CalculatorDemo
dotnet new sln -n CalculatorDemo

# 2. 创建类库项目
dotnet new classlib -n CalculatorLib -o src/CalculatorLib

# 3. 创建 xUnit 测试项目
dotnet new xunit -n CalculatorLib.Tests -o tests/CalculatorLib.Tests

# 4. 将两个项目加入解决方案
dotnet sln add src/CalculatorLib
dotnet sln add tests/CalculatorLib.Tests

# 5. 测试项目引用类库
dotnet add tests/CalculatorLib.Tests reference src/CalculatorLib
```

#### `src/CalculatorLib/Calculator.cs`

```csharp
namespace CalculatorLib;

public class Calculator
{
    public int Add(int a, int b) => a + b;

    public int Subtract(int a, int b) => a - b;

    public int Multiply(int a, int b) => a * b;

    public double Divide(double a, double b)
    {
        if (b == 0)
            throw new DivideByZeroException("Cannot divide by zero.");
        return a / b;
    }

    public bool IsPrime(int number)
    {
        if (number < 2) return false;
        for (int i = 2; i <= Math.Sqrt(number); i++)
        {
            if (number % i == 0) return false;
        }
        return true;
    }
}
```

#### `tests/CalculatorLib.Tests/CalculatorTests.cs`

（模板生成的 `UnitTest1.cs` 可以删除或重命名。）

```csharp
using CalculatorLib;

namespace CalculatorLib.Tests;

public class CalculatorTests
{
    private readonly Calculator _calc = new();

    // ═══════════════ Fact 测试 ═══════════════

    [Fact]
    public void Add_TwoPositiveNumbers_ReturnsSum()
    {
        int result = _calc.Add(2, 3);
        Assert.Equal(5, result);
    }

    [Fact]
    public void Subtract_ResultIsNegative_ReturnsNegative()
    {
        int result = _calc.Subtract(3, 10);
        Assert.Equal(-7, result);
    }

    [Fact]
    public void Multiply_ByZero_ReturnsZero()
    {
        int result = _calc.Multiply(99, 0);
        Assert.Equal(0, result);
    }

    [Fact]
    public void Divide_ByZero_ThrowsDivideByZeroException()
    {
        var ex = Assert.Throws<DivideByZeroException>(
            () => _calc.Divide(10, 0));
        Assert.Equal("Cannot divide by zero.", ex.Message);
    }

    // ═══════════════ Theory 测试 ═══════════════

    [Theory]
    [InlineData(1, 1, 2)]
    [InlineData(0, 0, 0)]
    [InlineData(-1, 1, 0)]
    [InlineData(-5, -3, -8)]
    [InlineData(int.MaxValue, 1, int.MinValue)] // 溢出：演示行为
    public void Add_MultipleInputs_ReturnsExpected(
        int a, int b, int expected)
    {
        int result = _calc.Add(a, b);
        Assert.Equal(expected, result);
    }

    [Theory]
    [InlineData(10, 2, 5.0)]
    [InlineData(1, 3, 1.0 / 3.0)]
    [InlineData(-10, 4, -2.5)]
    public void Divide_MultipleInputs_ReturnsExpected(
        double a, double b, double expected)
    {
        double result = _calc.Divide(a, b);
        Assert.Equal(expected, result, precision: 6);
    }

    [Theory]
    [InlineData(2, true)]
    [InlineData(3, true)]
    [InlineData(4, false)]
    [InlineData(17, true)]
    [InlineData(18, false)]
    [InlineData(1, false)]   // 1 不是质数
    [InlineData(0, false)]   // 0 不是质数
    [InlineData(-7, false)]  // 负数不是质数
    public void IsPrime_VariousNumbers_ReturnsCorrect(
        int number, bool expected)
    {
        bool result = _calc.IsPrime(number);
        Assert.Equal(expected, result);
    }

    // ═══════════════ 带 Trait 分类的测试 ═══════════════

    [Fact]
    [Trait("Category", "EdgeCase")]
    public void Add_MaxValuePlusOne_OverflowsToMinValue()
    {
        // 演示 unchecked 溢出行为：int.MaxValue + 1 = int.MinValue
        int result = _calc.Add(int.MaxValue, 1);
        Assert.Equal(int.MinValue, result);
    }
}
```

#### 运行测试

```bash
# 运行全部测试
dotnet test

# 只看 EdgeCase 分类
dotnet test --filter "Category=EdgeCase"

# 只运行 IsPrime 相关测试
dotnet test --filter "FullyQualifiedName~IsPrime"

# 详细控制台输出 + TRX 报告
dotnet test --logger "console;verbosity=detailed" --logger "trx"
```

预期输出（17 个测试全部通过）：

```
Passed!  - Failed:     0, Passed:    17, Skipped:     0, Total:    17
```

#### 生成覆盖率报告

```bash
# 收集覆盖率
dotnet test --collect:"XPlat Code Coverage"

# 安装报告生成器（首次）
dotnet tool install -g dotnet-reportgenerator-globaltool

# 生成 HTML 报告
reportgenerator \
    -reports:"tests/**/coverage.cobertura.xml" \
    -targetdir:"coveragereport" \
    -reporttypes:Html

# 查看
# Windows: start coveragereport/index.html
# macOS:   open coveragereport/index.html
# Linux:   xdg-open coveragereport/index.html
```

---

## 7. 练习

### 练习 1：为 StringUtils 编写测试

创建一个 `StringUtils` 类，包含以下方法，然后编写完整的 xUnit 测试：

```csharp
public static class StringUtils
{
    // 反转字符串
    public static string Reverse(string input);

    // 判断是否为回文（忽略大小写和空格）
    public static bool IsPalindrome(string input);

    // 统计单词数（按空格分割）
    public static int WordCount(string input);
}
```

要求：
- 对每个方法至少写 2 个 `[Fact]` 测试和 1 个 `[Theory]` 测试
- 覆盖边界情况：空字符串、null、单字符、超长字符串
- 使用 `[Trait("Category", "String")]` 标记所有测试

### 练习 2：测试驱动开发（TDD）练习

用 TDD 方式实现一个 `TemperatureConverter` 类：

1. **先写测试**（测试先于实现）：
   - `CelsiusToFahrenheit(0)` → 32
   - `CelsiusToFahrenheit(100)` → 212
   - `CelsiusToFahrenheit(-40)` → -40
   - `FahrenheitToCelsius(32)` → 0
   - `FahrenheitToCelsius(212)` → 100
   - `FahrenheitToCelsius(-40)` → -40

2. 先运行 `dotnet test`，观察测试**失败**（红色阶段）
3. 实现 `TemperatureConverter` 使测试通过（绿色阶段）
4. 如有可能，重构实现使其更清晰（重构阶段）

### 练习 3：测试异步代码

创建一个 `FileService` 类：

```csharp
public class FileService
{
    // 异步写入文件（返回写入字节数），文件已存在时抛异常
    public Task<int> WriteTextAsync(string path, string content);

    // 异步读取文件内容
    public Task<string> ReadTextAsync(string path);
}
```

编写 xUnit 测试：

- 用 `Assert.ThrowsAsync<T>()` 测试写入已存在文件的异常
- 用临时文件路径（`Path.GetTempFileName()`）避免污染项目目录
- 用 `IDisposable` 清理临时文件
- 确保读写往返一致性：写入后读回的内容与写入一致

---

## 8. 扩展阅读

- [xUnit.net 官方文档](https://xunit.net/docs/getting-started/netcore/cmdline) — 从命令行开始使用 xUnit
- [dotnet test 命令参考 — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-test) — `dotnet test` 的完整参数列表
- [VSTest `--filter` 选项 — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/testing/selective-unit-tests) — 过滤表达式语法详解
- [coverlet GitHub 仓库](https://github.com/coverlet-coverage/coverlet) — 覆盖率工具文档和高级配置
- [ReportGenerator 文档](https://reportgenerator.io/) — 将覆盖率 XML 转换为可视化 HTML 报告
- [NUnit 官方文档](https://docs.nunit.org/) — NUnit 框架完整指南
- [MSTest 官方文档](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-mstest-intro) — MSTest 入门教程
- [单元测试最佳实践 — Microsoft Learn](https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices) — 测试命名、结构、反模式指南
- [ASP.NET Core 集成测试](https://learn.microsoft.com/en-us/aspnet/core/test/integration-tests) — WebApplicationFactory 与集成测试
- [xUnit 理论数据源 — xUnit.net](https://xunit.net/docs/getting-started/netcore/cmdline#theory-data) — `[MemberData]`、`[ClassData]`、自定义数据源

---

## 9. 常见陷阱

### 陷阱 1：测试项目没有引用被测库

```bash
# 症状：测试代码中 using 语句报红，编译失败
error CS0246: The type or namespace name 'CalculatorLib' could not be found

# 原因：忘记添加项目引用
# 解决：
dotnet add tests/MyLib.Tests reference src/MyLib
```

这在刚创建好测试项目时最容易出现。你创建了测试项目、写了测试代码，但忘记把它们"连起来"。

### 陷阱 2：忘记 `[Fact]` 或 `[Theory]` 特性

```csharp
// ❌ 不是测试——xUnit 不会发现它
public void Add_TwoNumbers_ReturnsSum()
{
    Assert.Equal(3, _calc.Add(1, 2));
}

// ✅ 加上 [Fact] 后才是测试
[Fact]
public void Add_TwoNumbers_ReturnsSum()
{
    Assert.Equal(3, _calc.Add(1, 2));
}
```

没有 `[Fact]` / `[Theory]` / `[Test]` / `[TestMethod]` 标记的方法只是普通方法，`dotnet test` 不会执行它。测试会静默跳过——不是失败，是直接没跑。

> [!tip] 如何发现
> 运行 `dotnet test` 后看 Total 数量。如果你写了 5 个测试但 Total 只显示 3，检查是否漏掉了特性。

### 陷阱 3：`[Fact]` 与 `[Theory]` 用错

```csharp
// ❌ [Fact] 不能有参数
[Fact]
public void Add_MultipleValues(int a, int b, int expected)  // 编译错误
{
    Assert.Equal(expected, _calc.Add(a, b));
}

// ✅ [Theory] 才可以带参数
[Theory]
[InlineData(1, 1, 2)]
[InlineData(2, 3, 5)]
public void Add_MultipleValues(int a, int b, int expected)
{
    Assert.Equal(expected, _calc.Add(a, b));
}
```

`[Fact]` = 无参数、无数据源、总是运行一次。`[Theory]` = 有参数、需数据源、每个数据行运行一次。

### 陷阱 4：async void 测试永远不被等待

```csharp
// ❌ async void 导致测试立即返回，断言不执行
[Fact]
public async void FetchData_ReturnsExpected()  // async void！
{
    var data = await _service.FetchDataAsync();
    Assert.NotNull(data);
    // 测试总是通过，因为 Assert 还没执行测试就已经结束了
}

// ✅ async Task — xUnit 会等待它完成
[Fact]
public async Task FetchData_ReturnsExpected()
{
    var data = await _service.FetchDataAsync();
    Assert.NotNull(data);
}
```

> [!warning] async void 是"火后不理"
> `async void` 方法启动异步操作后立即返回，调用者无法等待它完成。xUnit 看到方法返回后就判定"测试通过"，而你的断言可能还没执行——甚至已经在后台抛了异常但被 `SynchronizationContext` 吞掉。**永远在测试中用 `async Task`，不是 `async void`。**

### 陷阱 5：异步测试死锁（SynchronizationContext 问题）

```csharp
// ❌ 在 xUnit 测试中用 .Result 或 .Wait() —— 可能死锁
[Fact]
public void GetData_ReturnsSomething()
{
    var data = _service.GetDataAsync().Result;  // 死锁！
    Assert.NotNull(data);
}

// ✅ 改为 async Task
[Fact]
public async Task GetData_ReturnsSomething()
{
    var data = await _service.GetDataAsync();
    Assert.NotNull(data);
}
```

原因：xUnit 不使用 `SynchronizationContext`（与 ASP.NET 不同），所以 `.Result` 理论上不会像在 ASP.NET 中那样死锁。但在某些场景（如自定义 `TaskScheduler`、某些 mock 库）下仍可能死锁。**规则很简单：async 方法就用 `await`**。

### 陷阱 6：浮点数直接用 `Assert.Equal`

```csharp
// ❌ 浮点数直接比较——精度误差导致测试不稳定
[Fact]
public void Divide_OneThird_ReturnsExpected()
{
    double result = _calc.Divide(1, 3);
    Assert.Equal(0.3333333333333333, result); // 可能失败！
}

// ✅ 指定精度
[Fact]
public void Divide_OneThird_ReturnsExpected()
{
    double result = _calc.Divide(1, 3);
    Assert.Equal(1.0 / 3.0, result, precision: 6);
}
```

### 陷阱 7：测试依赖执行顺序

```csharp
// ❌ 假设测试按顺序执行——在 xUnit 中不保证
private int _counter = 0;

[Fact]
public void Test1_Increment()
{
    _counter++;
    Assert.Equal(1, _counter);   // 如果 Test2 先跑了，这里就是 2！
}

[Fact]
public void Test2_Increment()
{
    _counter++;
    Assert.Equal(2, _counter);
}
```

xUnit 为每个测试方法创建**新的测试类实例**，因此实例字段 `_counter` 在每个测试中都是独立初始化的。以上代码即使看起来有问题，实际上不会跨测试共享状态——但如果使用了 `IClassFixture<T>` 共享夹具，则要注意并发问题。

> [!important] 单元测试的黄金规则
> **每个测试必须独立**。不依赖执行顺序、不依赖共享可变状态、不依赖外部资源（数据库、网络、文件系统）。如果一个测试的失败会导致其他测试也失败，你的测试设计有问题。

### 陷阱 8：`dotnet test` 找不到测试

```bash
# 症状
No test is available in ... Make sure that test discoverer & executors
are registered and platform & framework version settings are appropriate.

# 常见原因：
# 1. 测试项目未引用 Microsoft.NET.Test.Sdk
# 2. xunit.runner.visualstudio 版本与 SDK 不兼容
# 3. 项目不是 <IsTestProject>true</IsTestProject>（.NET 8+）
# 4. 在 sln 目录外运行但指定的路径无法解析到测试项目

# 解决：检查 .csproj 中的包引用和 SDK
```
