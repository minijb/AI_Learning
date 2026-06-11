---
title: "原型模式 Prototype"
updated: 2026-06-08
tags: [design-patterns, creational, prototype, cloning, csharp, record, cpp]
---

# 原型模式 Prototype

> 所属计划: [[design-patterns-csharp|设计模式 (C#)]]
> 预计耗时: 50 分钟
> 前置知识: [[02-creational-intro|创建型模式总览 + 简单工厂]]

---

## 1. 概念讲解

### 为什么需要克隆？

大多数创建型模式围绕 `new` 展开——工厂决定"new 哪个类"、Builder 决定"new 的步骤"。但有一种场景它们处理不好：

> 你需要一个和现有对象**几乎一样**但略有不同的新对象，"从零 new + 赋值"太繁琐，而对象的状态又是在运行时逐步累积的。

**原型模式的核心思想**：不通过 `new` 创建对象，而是**复制（克隆）一个已有对象（原型）**，然后按需调整。

```mermaid
flowchart TD
    New[传统: new + 逐个赋值] -->|复杂对象| Pain[状态散落各处<br/>容易漏赋值<br/>耦合创建细节]
    Clone[原型: 克隆 + 微调] -->|复杂对象| Win[一次 Copy<br/>只改差异字段<br/>不关心内部结构]

    style Pain fill:#f96,stroke:#333
    style Win fill:#6f9,stroke:#333
```

### 浅拷贝 vs 深拷贝

这是原型模式最核心的抉择，**搞错代价巨大**：

| | 浅拷贝 (Shallow Copy) | 深拷贝 (Deep Copy) |
|------|---------|--------|
| **复制内容** | 值类型字段 + 引用（不复制引用指向的对象） | 值类型字段 + 递归复制引用指向的对象 |
| **效果** | 新旧对象**共享**引用类型成员 | 新旧对象**完全独立** |
| **性能** | 极快（一次内存拷贝） | 慢（递归遍历对象图） |
| **适用** | 对象没有可变引用类型字段 | 需要完全独立的副本 |

```mermaid
flowchart TD
    Need{修改副本会不会<br/>影响原对象?}
    Need -->|不会| Shallow[浅拷贝 OK]
    Need -->|会 — 有可变引用字段| Deep{引用嵌套深度?}
    Deep -->|一层| Manual[手动逐层 Clone]
    Deep -->|多层/复杂| Strategy{性能要求?}
    Strategy -->|高| ExprTree[编译表达式树深拷贝]
    Strategy -->|中| Json[System.Text.Json 序列化]
    Strategy -->|低| Manual2[手动递归 Clone]
```

> [!warning] MemberwiseClone 是浅拷贝
> `object.MemberwiseClone()` 只做浅拷贝。新手最常见的 bug：以为 `Clone()` 返回的是独立副本，结果修改副本的 `List<T>.Items` 把原对象也改了。

### GoF 经典结构

```mermaid
classDiagram
    class IPrototype {
        <<interface>>
        +Clone() IPrototype
    }
    class ConcretePrototypeA {
        -_data : int
        -_list : List~string~
        +Clone() ConcretePrototypeA
    }
    class ConcretePrototypeB {
        -_name : string
        -_config : Config
        +Clone() ConcretePrototypeB
    }
    class Client {
        +Operation(prototype: IPrototype)
    }

    IPrototype <|.. ConcretePrototypeA : shallow copy
    IPrototype <|.. ConcretePrototypeB : deep copy
    Client --> IPrototype
```

### Prototype Registry 变体

当系统中有多种预配置的原型时，用 Registry（通常是一个 `Dictionary<string, IPrototype>`）集中管理：

```mermaid
classDiagram
    class PrototypeRegistry {
        -_items : Dictionary~string, IPrototype~
        +Register(key: string, prototype: IPrototype)
        +Unregister(key: string)
        +Create(key: string) IPrototype
    }
    class IPrototype {
        <<interface>>
        +Clone() IPrototype
    }
    class ConcretePrototypeA
    class ConcretePrototypeB

    PrototypeRegistry o-- IPrototype : stores
    IPrototype <|.. ConcretePrototypeA
    IPrototype <|.. ConcretePrototypeB
    PrototypeRegistry ..> IPrototype : clones via Clone()
```

---

## 2. 代码示例

### 示例 1：经典 ICloneable + MemberwiseClone（浅拷贝）

```csharp
using System.Text.Json;

// ============================================
// 1. ICloneable 浅拷贝 — 最简单的原型
// ============================================
public class Resume : ICloneable
{
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
    public int Age { get; set; }
    public List<string> Skills { get; set; } = new();

    public object Clone()
    {
        // MemberwiseClone() 是浅拷贝：Skills 引用被共享！
        return MemberwiseClone();
    }

    // 类型安全的克隆方法
    public Resume CloneTyped() => (Resume)MemberwiseClone();

    public void Print()
    {
        Console.WriteLine($"Name: {Name}, Email: {Email}, Age: {Age}");
        Console.WriteLine($"Skills: [{string.Join(", ", Skills)}]");
    }
}

// 演示浅拷贝的问题
var original = new Resume
{
    Name = "张三",
    Email = "zhangsan@example.com",
    Age = 28,
    Skills = new List<string> { "C#", "SQL" }
};

var shallow = original.CloneTyped();
Console.WriteLine("=== 浅拷贝演示 ===");
Console.WriteLine("--- 修改值类型字段 (int Age) ---");
shallow.Age = 30;
Console.WriteLine($"original.Age = {original.Age}"); // 28 — 独立，OK
Console.WriteLine($"shallow.Age   = {shallow.Age}"); // 30

Console.WriteLine("\n--- 修改引用类型字段 (List<string> Skills) ---");
shallow.Skills.Add("JavaScript");
// Skills 被共享！两者指向同一个 List
Console.WriteLine($"original.Skills = [{string.Join(", ", original.Skills)}]");
Console.WriteLine($"shallow.Skills   = [{string.Join(", ", shallow.Skills)}]");
// 输出：两者都有 "JavaScript"！
```

**运行方式:**
```bash
dotnet new console -n PrototypeShallowDemo
# 将上述代码放入 Program.cs
dotnet run --project PrototypeShallowDemo
```

**预期输出:**
```text
=== 浅拷贝演示 ===
--- 修改值类型字段 (int Age) ---
original.Age = 28
shallow.Age   = 30

--- 修改引用类型字段 (List<string> Skills) ---
original.Skills = [C#, SQL, JavaScript]
shallow.Skills   = [C#, SQL, JavaScript]
```

### 示例 2：System.Text.Json 深拷贝

`BinaryFormatter` 在 .NET 5+ 已被标记为 `[Obsolete]` 且在 .NET 8+ 默认禁用（安全漏洞 CVE）。现代替代方案：**System.Text.Json 序列化往返**。

```csharp
using System.Text.Json;

// ============================================
// 2. System.Text.Json 深拷贝
// ============================================
public class Document : ICloneable
{
    public string Title { get; set; } = "";
    public string Content { get; set; } = "";
    public List<string> Tags { get; set; } = new();
    public DocumentMetadata Metadata { get; set; } = new();

    // 浅拷贝（有问题）
    public object Clone() => MemberwiseClone();

    // System.Text.Json 深拷贝
    public Document DeepClone()
    {
        var json = JsonSerializer.Serialize(this);
        return JsonSerializer.Deserialize<Document>(json)
            ?? throw new InvalidOperationException("Deserialization returned null");
    }

    public void Print()
    {
        Console.WriteLine($"Title: {Title}");
        Console.WriteLine($"Tags: [{string.Join(", ", Tags)}]");
        Console.WriteLine($"Metadata.Author: {Metadata.Author}");
    }
}

public class DocumentMetadata
{
    public string Author { get; set; } = "";
    public DateTime CreatedAt { get; set; } = DateTime.Now;
}

// 演示
var doc = new Document
{
    Title = "设计模式笔记",
    Content = "原型模式...",
    Tags = new List<string> { "design-patterns", "csharp" },
    Metadata = new DocumentMetadata { Author = "张三" }
};

var deep = doc.DeepClone();
Console.WriteLine("=== System.Text.Json 深拷贝演示 ===");
Console.WriteLine("--- 修改 Tags ---");
deep.Tags.Add("dotnet");
Console.WriteLine($"doc.Tags  = [{string.Join(", ", doc.Tags)}]");  // 没有 "dotnet"
Console.WriteLine($"deep.Tags = [{string.Join(", ", deep.Tags)}]"); // 有 "dotnet"

Console.WriteLine("\n--- 修改 Metadata ---");
deep.Metadata.Author = "李四";
Console.WriteLine($"doc.Metadata.Author  = {doc.Metadata.Author}");  // 张三
Console.WriteLine($"deep.Metadata.Author = {deep.Metadata.Author}"); // 李四
```

> [!tip] JsonSerializer 深拷贝的代价
> 序列化往返比 `MemberwiseClone` 慢 50-200 倍。但它简单、可靠、无需手写递归 Clone，适合非热路径的对象复制。

**其他深度拷贝方案：**
- **表达式树编译** (`Expression<Func<T, T>>`)：最快的手写方案，无反射开销，适合性能敏感场景
- **手写递归 Clone**：完全控制，零依赖，但维护成本高
- **第三方库**：`DeepCloner`（NuGet: `Force.DeepCloner`）用 IL emit 生成高性能深拷贝

### 示例 3：C# `record` 的 `with` 表达式 — 现代原型

C# 9+ 的 `record` 类型天然是原型模式的最佳实现：不可变 + `with` 表达式 = 克隆并修改。

```csharp
// ============================================
// 3. record + with 表达式 — 现代 C# 原型
// ============================================

// record 默认是不可变的引用类型
public record EmployeeRecord(
    string Name,
    string Department,
    decimal Salary,
    List<string>? Certifications = null  // 注意：List 仍是引用类型！
);

// 演示
var emp1 = new EmployeeRecord("张三", "Engineering", 50000m);
Console.WriteLine("=== record with 表达式演示 ===");

// with 创建副本，只改 Department
var emp2 = emp1 with { Department = "Architecture" };
Console.WriteLine($"emp1: {emp1}");
Console.WriteLine($"emp2: {emp2}");

// with 表达式在 record 中是浅拷贝！
// 如果 record 包含可变引用类型字段，仍然共享引用
var emp3 = new EmployeeRecord("李四", "DevOps", 60000m,
    new List<string> { "AWS", "Kubernetes" });
var emp4 = emp3 with { Name = "李四 (升职)" };

emp4.Certifications!.Add("Docker");
Console.WriteLine($"\nemp3.Certifications: [{string.Join(", ", emp3.Certifications)}]");
Console.WriteLine($"emp4.Certifications: [{string.Join(", ", emp4.Certifications)}]");
// 两者都有 "Docker" — with 做的是浅拷贝！

// 解决方案：在 with 中手动深拷贝引用字段
var emp5 = emp3 with
{
    Name = "李四 (安全副本)",
    Certifications = new List<string>(emp3.Certifications!)  // 手动深拷贝 List
};
emp5.Certifications.Add("Terraform");
Console.WriteLine($"\nemp3.Certifications (after safe copy): [{string.Join(", ", emp3.Certifications)}]");
Console.WriteLine($"emp5.Certifications (modified):         [{string.Join(", ", emp5.Certifications)}]");
```

**运行方式:**
```bash
# record 需要 .NET 6+ 且启用 C# 10
dotnet new console -n PrototypeRecordDemo --framework net8.0
dotnet run --project PrototypeRecordDemo
```

**预期输出:**
```text
=== record with 表达式演示 ===
emp1: EmployeeRecord { Name = 张三, Department = Engineering, Salary = 50000, Certifications =  }
emp2: EmployeeRecord { Name = 张三, Department = Architecture, Salary = 50000, Certifications =  }

emp3.Certifications: [AWS, Kubernetes, Docker]
emp4.Certifications: [AWS, Kubernetes, Docker]

emp3.Certifications (after safe copy): [AWS, Kubernetes, Docker]
emp5.Certifications (modified):         [AWS, Kubernetes, Docker, Terraform]
```

> [!tip] record vs class 的选择
> - **需要频繁克隆 + 不可变语义** → `record` + `with`
> - **需要深拷贝嵌套对象** → 手写 Clone 或用 JsonSerializer
> - **记录 DTO / 消息 / 值对象** → `record` 是 C# 的首选
> - **record struct** (C# 10+) → 值类型，`with` 表达式也是值拷贝（天然深拷贝），但有 16 字节以上不宜复制的限制

### 示例 4：Prototype Registry（原型注册表）

```csharp
// ============================================
// 4. Prototype Registry — 预配置原型的字典
// ============================================

public interface IShape : ICloneable
{
    string Name { get; }
    void Draw();
    new IShape Clone();  // 隐藏 object.Clone()，返回类型安全的 IShape
}

public class Circle : IShape
{
    public string Name => "Circle";
    public int Radius { get; set; }
    public string Color { get; set; } = "Black";

    public Circle(int radius, string color)
    {
        Radius = radius;
        Color = color;
    }

    public object Clone() => MemberwiseClone();
    IShape IShape.Clone() => (Circle)MemberwiseClone();
    public void Draw() => Console.WriteLine($"  ○ Circle (r={Radius}, color={Color})");
}

public class Rectangle : IShape
{
    public string Name => "Rectangle";
    public int Width { get; set; }
    public int Height { get; set; }
    public string Color { get; set; } = "Black";

    public Rectangle(int width, int height, string color)
    {
        Width = width;
        Height = height;
        Color = color;
    }

    public object Clone() => MemberwiseClone();
    IShape IShape.Clone() => (Rectangle)MemberwiseClone();
    public void Draw() => Console.WriteLine($"  ▭ Rectangle (w={Width}, h={Height}, color={Color})");
}

// --- 原型注册表 ---
public class ShapeRegistry
{
    private readonly Dictionary<string, IShape> _prototypes = new();

    public void Register(string key, IShape prototype)
    {
        _prototypes[key] = prototype;
    }

    public void Unregister(string key)
    {
        _prototypes.Remove(key);
    }

    public IShape Create(string key)
    {
        if (!_prototypes.TryGetValue(key, out var prototype))
        {
            throw new ArgumentException($"No prototype registered for key: {key}");
        }
        return prototype.Clone();
    }

    public IEnumerable<string> Keys => _prototypes.Keys;
}

// --- 使用 ---
var registry = new ShapeRegistry();

// 注册预配置原型 (只注册一次)
registry.Register("small-red-circle",   new Circle(5, "Red"));
registry.Register("big-blue-circle",     new Circle(20, "Blue"));
registry.Register("green-square",         new Rectangle(10, 10, "Green"));
registry.Register("yellow-wide-rect",     new Rectangle(30, 10, "Yellow"));

Console.WriteLine("=== Prototype Registry 演示 ===\n");

// 创建时只需指定 key，通过 Clone 获取
var shape1 = registry.Create("small-red-circle");
var shape2 = registry.Create("big-blue-circle");
var shape3 = registry.Create("yellow-wide-rect");

// 克隆后可以修改，不影响原型
var customCircle = registry.Create("small-red-circle");
((Circle)customCircle).Radius = 8;
((Circle)customCircle).Color = "Purple";

Console.WriteLine("Cloned shapes:");
shape1.Draw();
shape2.Draw();
shape3.Draw();
Console.WriteLine("Customized clone:");
customCircle.Draw();

// 验证原型未被修改
Console.WriteLine("\nOriginal prototype still intact:");
var fresh = registry.Create("small-red-circle");
fresh.Draw(); // 仍然是 r=5, Red
```

**运行方式:**
```bash
dotnet new console -n PrototypeRegistryDemo
dotnet run --project PrototypeRegistryDemo
```

**预期输出:**
```text
=== Prototype Registry 演示 ===

Cloned shapes:
  ○ Circle (r=5, color=Red)
  ○ Circle (r=20, color=Blue)
  ▭ Rectangle (w=30, h=10, color=Yellow)
Customized clone:
  ○ Circle (r=8, color=Purple)

Original prototype still intact:
  ○ Circle (r=5, color=Red)
```

---


---

## C++ 实现

C++ 中用纯虚 `clone()` 声明原型接口。`unique_ptr` 返回克隆体所有权。需特别注意深拷贝 vs 浅拷贝：`std::vector` 等容器的拷贝构造是深拷贝（值语义），但裸指针成员只拷贝指针本身。

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <vector>

using namespace std;

// === 抽象原型 ===
struct Shape {
    virtual unique_ptr<Shape> clone() const = 0;
    virtual void draw() const = 0;
    virtual string describe() const = 0;
    virtual ~Shape() = default;
};

// === 具体原型: Rectangle ===
struct Rectangle : Shape {
    int width, height;
    string color;

    Rectangle(int w, int h, string c)
        : width(w), height(h), color(move(c)) {}

    unique_ptr<Shape> clone() const override {
        // 拷贝构造产生独立副本 — 所有成员是值类型，天然深拷贝
        return make_unique<Rectangle>(*this);
    }

    void draw() const override {
        cout << "Rectangle(" << width << "x" << height
             << ", " << color << ")" << endl;
    }

    string describe() const override {
        return "Rectangle " + to_string(width) + "x" + to_string(height);
    }
};

// === 具体原型: Circle ===
struct Circle : Shape {
    int radius;
    string fillColor;

    Circle(int r, string c) : radius(r), fillColor(move(c)) {}

    unique_ptr<Shape> clone() const override {
        return make_unique<Circle>(*this);
    }

    void draw() const override {
        cout << "Circle(r=" << radius << ", " << fillColor << ")" << endl;
    }

    string describe() const override {
        return "Circle r=" + to_string(radius);
    }
};

// === 示例: 带容器的原型 — 理解深拷贝 vs 浅拷贝 ===
struct Polygon : Shape {
    vector<pair<int, int>> points;   // vector 的拷贝构造是深拷贝
    string* label = nullptr;          // 裸指针 — 默认拷贝只复制指针！

    Polygon(initializer_list<pair<int, int>> pts)
        : points(pts) {}

    // 自定义拷贝构造: 对裸指针做深拷贝
    Polygon(const Polygon& other)
        : points(other.points)  // vector 自动深拷贝
        , label(other.label ? new string(*other.label) : nullptr) {}

    Polygon& operator=(const Polygon& other) {
        if (this != &other) {
            points = other.points;
            delete label;
            label = other.label ? new string(*other.label) : nullptr;
        }
        return *this;
    }

    ~Polygon() { delete label; }

    unique_ptr<Shape> clone() const override {
        return make_unique<Polygon>(*this);  // 调用拷贝构造 → 深拷贝
    }

    void draw() const override {
        cout << "Polygon(" << points.size() << " vertices";
        if (label) cout << ", label: " << *label;
        cout << ")" << endl;
    }

    string describe() const override {
        return "Polygon(" + to_string(points.size()) + " pts)";
    }
};

// === 原型注册表 ===
class ShapeRegistry {
    unordered_map<string, unique_ptr<Shape>> prototypes;
public:
    void add(const string& key, unique_ptr<Shape> proto) {
        prototypes[key] = move(proto);
    }

    unique_ptr<Shape> create(const string& key) {
        auto it = prototypes.find(key);
        if (it == prototypes.end())
            throw runtime_error("Unknown shape: " + key);
        return it->second->clone();
    }
};

// === main / usage ===
int main() {
    // 直接克隆
    auto rect1 = make_unique<Rectangle>(100, 50, "red");
    auto rect2 = rect1->clone();  // 独立副本
    rect1->draw();  // Rectangle(100x50, red)
    rect2->draw();  // Rectangle(100x50, red)

    auto circle1 = make_unique<Circle>(30, "blue");
    auto circle2 = circle1->clone();
    circle2->draw();  // Circle(r=30, blue)

    // 容器深拷贝演示
    auto poly1 = make_unique<Polygon>(
        initializer_list<pair<int, int>>{{0,0}, {10,0}, {10,10}});
    poly1->label = new string("Triangle");

    auto poly2 = poly1->clone();  // 深拷贝 — 新的 vector + 新的 string
    *poly2->label = "Copy";       // 修改克隆体的 label 不影响原对象

    poly1->draw();  // Polygon(3 vertices, label: Triangle)
    poly2->draw();  // Polygon(3 vertices, label: Copy)

    // 注册表模式
    ShapeRegistry registry;
    registry.add("rect", make_unique<Rectangle>(200, 100, "green"));
    registry.add("circle", make_unique<Circle>(15, "yellow"));

    auto s1 = registry.create("rect");
    auto s2 = registry.create("circle");
    s1->draw();
    s2->draw();
}
```

**编译运行:**
```bash
g++ -std=c++17 -o prog main.cpp && ./prog
```

> [!note] C++ 深浅拷贝要点
> - **值类型成员**（`int`, `string`, `vector<T>`, `unique_ptr<T>`）的默认拷贝构造是深拷贝——C++ 的值语义天然安全。
> - **裸指针**（`T*`）和 `shared_ptr<T>` 是浅拷贝——它们共享指向的对象。如需深拷贝裸指针，必须自定义拷贝构造/赋值。
> - `make_unique<Rectangle>(*this)` 调用 `Rectangle` 的拷贝构造，生成完全独立的副本。
> - 与 C# 的 `MemberwiseClone()` 是浅拷贝不同，C++ 的默认拷贝构造对所有成员逐成员拷贝——`vector` 成员是完整的深拷贝。
## 3. 练习

### 练习 1：实现复杂嵌套对象的深拷贝

有一份游戏角色配置对象，包含嵌套的装备、技能列表。请实现它的深拷贝。

```csharp
public class GameCharacter
{
    public string Name { get; set; } = "";
    public int Level { get; set; }
    public Equipment Weapon { get; set; } = new();
    public Equipment Armor { get; set; } = new();
    public List<Skill> Skills { get; set; } = new();
}

public class Equipment
{
    public string Name { get; set; } = "";
    public int Durability { get; set; }
    public List<string> Enchantments { get; set; } = new();
}

public class Skill
{
    public string Name { get; set; } = "";
    public int Level { get; set; }
}
```

**要求：**
1. 实现 `GameCharacter DeepClone()` 方法（用手写递归，不用 JsonSerializer）
2. 编写测试：修改副本的 `Weapon.Enchantments` 和 `Skills` 列表，验证原对象不受影响
3. 处理 `null` 引用（例如 Armor 可以为空）

### 练习 2：构建文档模板的原型注册表

设计一个文档模板系统，支持从预定义模板创建新文档。

```csharp
public interface IDocumentTemplate : ICloneable
{
    string TemplateName { get; }
    string Category { get; }
    IDocumentTemplate CloneTemplate();
}
```

**要求：**
1. 实现三种模板：`InvoiceTemplate`（含公司信息、税率）、`ReportTemplate`（含页眉页脚）、`ContractTemplate`（含双方信息）
2. 实现 `TemplateRegistry`，支持按 Category 查询和按名称创建
3. 克隆后的模板应能独立修改（浅拷贝即可，因为模板字段都是值类型或 `string`）
4. 添加"预置模板加载"功能（启动时从配置加载默认模板集）

### 练习 3：性能对比 Benchmark（可选）

创建一个 BenchmarkDotNet 基准测试，比较三种深拷贝方式对同一个复杂对象的性能：

1. `MemberwiseClone()`（浅拷贝，但可测量原生性能基线）
2. `JsonSerializer` 往返
3. 手写递归 `Clone()` 方法

**要求：**
1. 使用 `BenchmarkDotNet` NuGet 包
2. 测试对象至少包含 5 层嵌套，含 `List<T>`、`Dictionary<K,V>`、自定义引用类型
3. 同时测量内存分配（`MemoryDiagnoser`）
4. 分析结果，说明何时该用哪种方案

> [!tip] BenchmarkDotNet 快速上手
> ```csharp
> [MemoryDiagnoser]
> public class CloneBenchmark
> {
>     private ComplexObject _source = null!;
>
>     [GlobalSetup]
>     public void Setup() { _source = CreateComplexObject(); }
>
>     [Benchmark(Baseline = true)]
>     public ComplexObject MemberwiseClone() => _source.ShallowClone();
>
>     [Benchmark]
>     public ComplexObject JsonClone() => _source.JsonDeepClone();
>
>     [Benchmark]
>     public ComplexObject ManualClone() => _source.ManualDeepClone();
> }
> ```

> 使用 BenchmarkDotNet 的结果来回答：是否值得为原型模式引入序列化依赖？

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```csharp
> using System;
> using System.Collections.Generic;
> using System.Linq;
>
> // ============================================
> // 手写递归深拷贝实现
> // ============================================
> public class GameCharacter
> {
>     public string Name { get; set; } = "";
>     public int Level { get; set; }
>     public Equipment? Weapon { get; set; }
>     public Equipment? Armor { get; set; }
>     public List<Skill> Skills { get; set; } = new();
>
>     /// <summary>手写递归深拷贝：完全独立的副本</summary>
>     public GameCharacter DeepClone()
>     {
>         var clone = new GameCharacter
>         {
>             Name = this.Name,
>             Level = this.Level,
>             // 深拷贝嵌套对象（处理 null）
>             Weapon = this.Weapon?.DeepClone(),
>             Armor = this.Armor?.DeepClone(),
>             // 深拷贝 List：创建新列表 + 每个元素递归克隆
>             Skills = this.Skills.Select(s => s.DeepClone()).ToList()
>         };
>         return clone;
>     }
> }
>
> public class Equipment
> {
>     public string Name { get; set; } = "";
>     public int Durability { get; set; }
>     public List<string> Enchantments { get; set; } = new();
>
>     /// <summary>深拷贝装备：Enchantments 需要新 List</summary>
>     public Equipment DeepClone()
>     {
>         return new Equipment
>         {
>             Name = this.Name,
>             Durability = this.Durability,
>             // 字符串是不可变的，只需浅拷贝 List 本身
>             Enchantments = new List<string>(this.Enchantments)
>         };
>     }
> }
>
> public class Skill
> {
>     public string Name { get; set; } = "";
>     public int Level { get; set; }
>
>     public Skill DeepClone()
>     {
>         return new Skill
>         {
>             Name = this.Name,
>             Level = this.Level
>         };
>     }
> }
>
>
> // ============================================
> // 验证测试
> // ============================================
> static void TestDeepClone()
> {
>     var original = new GameCharacter
>     {
>         Name = "勇者",
>         Level = 50,
>         Weapon = new Equipment
>         {
>             Name = "圣剑",
>             Durability = 100,
>             Enchantments = new List<string> { "火属性", "光属性" }
>         },
>         Armor = null, // 故意为 null — 测试空引用处理
>         Skills = new List<Skill>
>         {
>             new Skill { Name = "劈斩", Level = 5 },
>             new Skill { Name = "火球术", Level = 3 }
>         }
>     };
>
>     var clone = original.DeepClone();
>
>     // 修改副本的引用类型字段
>     clone.Weapon!.Enchantments.Add("冰属性");
>     clone.Weapon.Name = "魔剑";
>     clone.Skills[0].Level = 10;
>     clone.Skills.Add(new Skill { Name = "治疗", Level = 1 });
>
>     // 验证原对象不受影响
>     Console.WriteLine("=== 原对象 ===");
>     Console.WriteLine($"Weapon.Name: {original.Weapon!.Name}");         // 圣剑
>     Console.WriteLine($"Enchantments: [{string.Join(", ", original.Weapon.Enchantments)}]");
>     // 火属性, 光属性（没有冰属性）
>     Console.WriteLine($"Skills[0].Level: {original.Skills[0].Level}");  // 5
>     Console.WriteLine($"Skills.Count: {original.Skills.Count}");        // 2
>     Console.WriteLine($"Armor: {original.Armor?.Name ?? "null"}");      // null
>
>     Console.WriteLine("\n=== 副本 ===");
>     Console.WriteLine($"Weapon.Name: {clone.Weapon.Name}");             // 魔剑
>     Console.WriteLine($"Enchantments: [{string.Join(", ", clone.Weapon.Enchantments)}]");
>     // 火属性, 光属性, 冰属性
>     Console.WriteLine($"Skills[0].Level: {clone.Skills[0].Level}");     // 10
>     Console.WriteLine($"Skills.Count: {clone.Skills.Count}");           // 3
>     Console.WriteLine($"Armor: {clone.Armor?.Name ?? "null"}");         // null
>
>     // 关键断言
>     System.Diagnostics.Debug.Assert(
>         original.Weapon.Enchantments.Count == 2,
>         "原对象的 Enchantments 不应被修改");
>     System.Diagnostics.Debug.Assert(
>         original.Skills.Count == 2,
>         "原对象的 Skills 列表不应被修改");
> }
> ```

> [!tip]- 练习 2 参考答案
> ```csharp
> using System;
> using System.Collections.Generic;
> using System.Linq;
>
> // ============================================
> // 1. 文档模板接口
> // ============================================
> public interface IDocumentTemplate : ICloneable
> {
>     string TemplateName { get; }
>     string Category { get; }
>     IDocumentTemplate CloneTemplate();
> }
>
> // ============================================
> // 2. 三种具体模板
> // ============================================
> public class InvoiceTemplate : IDocumentTemplate
> {
>     public string TemplateName { get; set; } = "";
>     public string Category => "发票";
>     public string CompanyName { get; set; } = "";
>     public string TaxId { get; set; } = "";
>     public decimal TaxRate { get; set; } = 0.13m;
>     public string BankAccount { get; set; } = "";
>
>     public object Clone() => MemberwiseClone();
>     public IDocumentTemplate CloneTemplate() =>
>         (InvoiceTemplate)MemberwiseClone();
> }
>
> public class ReportTemplate : IDocumentTemplate
> {
>     public string TemplateName { get; set; } = "";
>     public string Category => "报告";
>     public string Header { get; set; } = "";
>     public string Footer { get; set; } = "";
>     public string FontFamily { get; set; } = "SimSun";
>     public int FontSize { get; set; } = 12;
>
>     public object Clone() => MemberwiseClone();
>     public IDocumentTemplate CloneTemplate() =>
>         (ReportTemplate)MemberwiseClone();
> }
>
> public class ContractTemplate : IDocumentTemplate
> {
>     public string TemplateName { get; set; } = "";
>     public string Category => "合同";
>     public string PartyA { get; set; } = "";    // 甲方
>     public string PartyB { get; set; } = "";    // 乙方
>     public string GoverningLaw { get; set; } = "中华人民共和国法律";
>     public List<string> Clauses { get; set; } = new();
>
>     // 合同模板的 CloneTemplate 需要深拷贝 Clauses 列表
>     // （Invoice/Report 的字段都是值类型/string，浅拷贝够用）
>     public object Clone()
>     {
>         var clone = (ContractTemplate)MemberwiseClone();
>         clone.Clauses = new List<string>(this.Clauses);
>         return clone;
>     }
>     public IDocumentTemplate CloneTemplate() =>
>         (ContractTemplate)Clone();
> }
>
> // ============================================
> // 3. 模板注册表
> // ============================================
> public class TemplateRegistry
> {
>     private readonly Dictionary<string, IDocumentTemplate> _templates = new();
>
>     public void Register(IDocumentTemplate template)
>     {
>         if (template == null)
>             throw new ArgumentNullException(nameof(template));
>         _templates[template.TemplateName] = template;
>     }
>
>     public void Unregister(string templateName)
>     {
>         _templates.Remove(templateName);
>     }
>
>     /// <summary>按模板名称创建（克隆）</summary>
>     public IDocumentTemplate Create(string templateName)
>     {
>         if (!_templates.TryGetValue(templateName, out var prototype))
>             throw new KeyNotFoundException(
>                 $"模板 '{templateName}' 不存在");
>         return prototype.CloneTemplate();
>     }
>
>     /// <summary>按类别查询所有模板名</summary>
>     public IEnumerable<string> GetTemplateNamesByCategory(string category)
>     {
>         return _templates.Values
>             .Where(t => t.Category == category)
>             .Select(t => t.TemplateName);
>     }
>
>     /// <summary>列出所有分类</summary>
>     public IEnumerable<string> GetAllCategories()
>     {
>         return _templates.Values
>             .Select(t => t.Category)
>             .Distinct();
>     }
> }
>
> // ============================================
> // 4. 预置模板加载
> // ============================================
> public static class DefaultTemplates
> {
>     public static TemplateRegistry LoadDefaults()
>     {
>         var registry = new TemplateRegistry();
>
>         registry.Register(new InvoiceTemplate
>         {
>             TemplateName = "标准发票",
>             CompanyName = "示例科技有限公司",
>             TaxId = "91110000MA00000000",
>             TaxRate = 0.13m,
>             BankAccount = "6222 0000 0000 0000 000"
>         });
>
>         registry.Register(new InvoiceTemplate
>         {
>             TemplateName = "出口发票",
>             CompanyName = "示例科技有限公司",
>             TaxId = "91110000MA00000000",
>             TaxRate = 0.00m,  // 出口零税率
>             BankAccount = "6222 0000 0000 0000 001"
>         });
>
>         registry.Register(new ReportTemplate
>         {
>             TemplateName = "周报",
>             Header = "每周工作汇报",
>             Footer = "—— 示例科技内部文档 ——"
>         });
>
>         registry.Register(new ContractTemplate
>         {
>             TemplateName = "销售合同",
>             PartyA = "示例科技有限公司",
>             PartyB = "（待填写）",
>             Clauses = new List<string>
>             {
>                 "第一条: 标的物",
>                 "第二条: 付款方式",
>                 "第三条: 违约责任"
>             }
>         });
>
>         return registry;
>     }
> }
>
>
> // ============================================
> // 验证测试
> // ============================================
> static void TestTemplateRegistry()
> {
>     var registry = DefaultTemplates.LoadDefaults();
>
>     // 按类别查询
>     Console.WriteLine("=== 发票模板 ===");
>     foreach (var name in registry.GetTemplateNamesByCategory("发票"))
>         Console.WriteLine($"  - {name}");
>
>     // 克隆并修改
>     var invoice = (InvoiceTemplate)registry.Create("标准发票");
>     invoice.CompanyName = "客户定制公司";
>     invoice.TaxRate = 0.06m;
>
>     // 再克隆一个 — 原型不变
>     var invoice2 = (InvoiceTemplate)registry.Create("标准发票");
>     Console.WriteLine($"\ninvoice2.CompanyName: {invoice2.CompanyName}");
>     // "示例科技有限公司" — 原型未被污染
>
>     // 验证合同模板的 Clauses 独立
>     var contract1 = (ContractTemplate)registry.Create("销售合同");
>     contract1.Clauses.Add("第四条: 保密条款");
>     var contract2 = (ContractTemplate)registry.Create("销售合同");
>     Console.WriteLine($"contract1.Clauses: {contract1.Clauses.Count} 条"); // 4
>     Console.WriteLine($"contract2.Clauses: {contract2.Clauses.Count} 条"); // 3
> }
> ```

> [!tip]- 练习 3 参考答案（可选）
> 以下为 BenchmarkDotNet 基准测试的完整实现。使用前需安装 NuGet 包：
> ```bash
> dotnet add package BenchmarkDotNet
> ```
>
> ```csharp
> using System;
> using System.Collections.Generic;
> using System.Linq;
> using System.Text.Json;
> using BenchmarkDotNet.Attributes;
> using BenchmarkDotNet.Running;
> using BenchmarkDotNet.Columns;
> using BenchmarkDotNet.Configs;
>
> // ============================================
> // 复杂测试对象定义（5+ 层嵌套）
> // ============================================
> public class ComplexObject
> {
>     public int Id { get; set; }
>     public string Name { get; set; } = "";
>     public DateTime CreatedAt { get; set; }
>     public List<Order> Orders { get; set; } = new();
>     public Dictionary<string, ConfigEntry> Config { get; set; } = new();
>     public MetaInfo Meta { get; set; } = new();
>
>     public ComplexObject ShallowClone() => (ComplexObject)MemberwiseClone();
>
>     public ComplexObject JsonDeepClone()
>     {
>         var json = JsonSerializer.Serialize(this);
>         return JsonSerializer.Deserialize<ComplexObject>(json)!;
>     }
>
>     public ComplexObject ManualDeepClone()
>     {
>         var clone = (ComplexObject)MemberwiseClone();
>         clone.Name = this.Name;
>         clone.Orders = this.Orders.Select(o => o.DeepClone()).ToList();
>         clone.Config = new Dictionary<string, ConfigEntry>(
>             this.Config.Select(kv =>
>                 new KeyValuePair<string, ConfigEntry>(kv.Key, kv.Value.DeepClone())));
>         clone.Meta = this.Meta.DeepClone();
>         return clone;
>     }
> }
>
> public class Order
> {
>     public string OrderId { get; set; } = "";
>     public decimal Amount { get; set; }
>     public List<OrderItem> Items { get; set; } = new();
>
>     public Order DeepClone()
>     {
>         var clone = (Order)MemberwiseClone();
>         clone.Items = this.Items.Select(i => i.DeepClone()).ToList();
>         return clone;
>     }
> }
>
> public class OrderItem
> {
>     public string ProductName { get; set; } = "";
>     public int Quantity { get; set; }
>     public PriceInfo Price { get; set; } = new();
>
>     public OrderItem DeepClone()
>     {
>         var clone = (OrderItem)MemberwiseClone();
>         clone.Price = this.Price.DeepClone();
>         return clone;
>     }
> }
>
> public class PriceInfo
> {
>     public decimal UnitPrice { get; set; }
>     public string Currency { get; set; } = "CNY";
>     public Discount? Discount { get; set; }
>
>     public PriceInfo DeepClone()
>     {
>         var clone = (PriceInfo)MemberwiseClone();
>         if (this.Discount != null)
>             clone.Discount = new Discount
>             {
>                 Rate = this.Discount.Rate,
>                 Reason = this.Discount.Reason
>             };
>         return clone;
>     }
> }
>
> public class Discount
> {
>     public decimal Rate { get; set; }
>     public string Reason { get; set; } = "";
> }
>
> public class ConfigEntry
> {
>     public string Value { get; set; } = "";
>     public DateTime UpdatedAt { get; set; }
>
>     public ConfigEntry DeepClone()
>     {
>         return (ConfigEntry)MemberwiseClone();
>     }
> }
>
> public class MetaInfo
> {
>     public string CreatedBy { get; set; } = "";
>     public List<string> Tags { get; set; } = new();
>     public NestedData Nested { get; set; } = new();
>
>     public MetaInfo DeepClone()
>     {
>         var clone = (MetaInfo)MemberwiseClone();
>         clone.Tags = new List<string>(this.Tags);
>         clone.Nested = this.Nested.DeepClone();
>         return clone;
>     }
> }
>
> public class NestedData
> {
>     public string Data { get; set; } = "";
>     public List<int> Values { get; set; } = new();
>
>     public NestedData DeepClone()
>     {
>         var clone = (NestedData)MemberwiseClone();
>         clone.Values = new List<int>(this.Values);
>         return clone;
>     }
> }
>
> // ============================================
> // BenchmarkDotNet 基准测试
> // ============================================
> [MemoryDiagnoser]
> [RankColumn]
> public class CloneBenchmark
> {
>     private ComplexObject _source = null!;
>
>     [GlobalSetup]
>     public void Setup()
>     {
>         _source = CreateComplexObject();
>     }
>
>     [Benchmark(Baseline = true)]
>     public ComplexObject MemberwiseClone() => _source.ShallowClone();
>
>     [Benchmark]
>     public ComplexObject JsonSerializerClone() => _source.JsonDeepClone();
>
>     [Benchmark]
>     public ComplexObject ManualDeepClone() => _source.ManualDeepClone();
>
>     private static ComplexObject CreateComplexObject()
>     {
>         var obj = new ComplexObject
>         {
>             Id = 1,
>             Name = "测试对象",
>             CreatedAt = DateTime.UtcNow,
>             Meta = new MetaInfo
>             {
>                 CreatedBy = "system",
>                 Tags = new List<string> { "critical", "production" },
>                 Nested = new NestedData
>                 {
>                     Data = "layer-5-data",
>                     Values = new List<int> { 1, 2, 3, 4, 5 }
>                 }
>             }
>         };
>
>         // 填充 Orders（含嵌套）
>         for (int i = 0; i < 20; i++)
>         {
>             var order = new Order
>             {
>                 OrderId = $"ORD-{i:D4}",
>                 Amount = 100m + i * 10
>             };
>             for (int j = 0; j < 3; j++)
>             {
>                 order.Items.Add(new OrderItem
>                 {
>                     ProductName = $"产品-{i}-{j}",
>                     Quantity = j + 1,
>                     Price = new PriceInfo
>                     {
>                         UnitPrice = 10.5m + j,
>                         Discount = j > 0 ? new Discount { Rate = 0.1m, Reason = "批量" } : null
>                     }
>                 });
>             }
>             obj.Orders.Add(order);
>         }
>
>         // 填充 Config
>         for (int i = 0; i < 10; i++)
>         {
>             obj.Config[$"key-{i}"] = new ConfigEntry
>             {
>                 Value = $"value-{i}",
>                 UpdatedAt = DateTime.UtcNow
>             };
>         }
>
>         return obj;
>     }
> }
>
> // Program.cs 入口:
> // BenchmarkRunner.Run<CloneBenchmark>();
> ```
>
> **性能分析（典型结果趋势）：**
>
> | 方案 | 耗时（参考） | 内存分配 | 适用场景 |
> |------|-------------|----------|---------|
> | MemberwiseClone | 最快（基线） | 最低 | **不保证深拷贝**，仅当对象无可变引用字段时安全 |
> | 手写递归 Clone | 基线的 2-5 倍 | 低 | 对象结构已知、性能敏感、零依赖 |
> | JsonSerializer | 基线的 50-200 倍 | 高（序列化 + 反序列化全量字符串） | 通用、可靠、一行代码、适合非热路径 |
>
> **结论：**
> 1. **MemberwiseClone 不是深拷贝** — 它比手写深拷贝快，是因为它不做任何引用类型的克隆。直接比较"性能"无意义。
> 2. 手写递归深拷贝在性能上远优于 JsonSerializer（通常快 20-50 倍），且内存分配少得多。
> 3. JsonSerializer 深拷贝适合**非热路径**（如配置加载、请求级对象复制），不推荐用于每帧/每秒高频调用。
> 4. 如果对象结构稳定不会频繁变更，**值得**手写深拷贝来避免序列化依赖；但如果对象字段频繁增删，JsonSerializer 的零维护成本可能更划算。
> 5. 生产环境推荐优先级：**record + with（不可变对象）> 手写 Clone > JsonSerializer > 第三方库**。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。


## 4. 扩展阅读

- [[06-builder|建造者模式]] — Builder 分步构建 vs Prototype 一次克隆，两种"复杂对象创建"的不同思路
- [[03-singleton|单例模式]] — 原型模式的 Registry 变体常与 Singleton 结合使用
- [[04-factory-method|工厂方法模式]] — Factory Method + Prototype：用工厂产出原型，用 Clone 生产实例
- [Refactoring.Guru — Prototype](https://refactoring.guru/design-patterns/prototype) — UML 类图与时序图的权威解读
- [Microsoft Docs — ICloneable](https://learn.microsoft.com/en-us/dotnet/api/system.icloneable) — `ICloneable` 的官方设计说明（含为什么不推荐）
- [Microsoft Docs — Records](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/builtin-types/record) — C# `record` 和 `with` 表达式详解
- [.NET Blog — BinaryFormatter 弃用](https://devblogs.microsoft.com/dotnet/binaryformatter-security-guide/) — 官方安全指南和迁移建议
- [SharpLab — `with` 表达式编译结果](https://sharplab.io/) — 在线查看 C# 编译器如何生成 Clone 代码

---

## 常见陷阱

### 1. `ICloneable` 不指定浅/深拷贝

> `ICloneable` 接口只要求实现 `Clone()`，但**不规定是浅拷贝还是深拷贝**，调用者无法从接口得知行为。

**错误做法：** 依赖 `ICloneable` 并假设它做了深拷贝。
```csharp
public void Process(ICloneable source)
{
    var copy = (MyType)source.Clone();
    copy.Items.Clear(); // 可能清空了原对象的 Items！
}
```

**正确做法：** 在自己定义的接口中明确语义或改用泛型方法：
```csharp
public interface IDeepCloneable<T>
{
    T DeepClone();
}

public interface IShallowCloneable<T>
{
    T ShallowClone();
}
```

### 2. `MemberwiseClone` 只做浅拷贝

`object.MemberwiseClone()` 逐位复制值类型字段，但对引用类型只复制引用——新旧对象共享同一个 `List<T>`、`Dictionary<K,V>`、自定义类等引用成员。

**正确做法：** 在 `Clone()` 中显式处理引用类型字段：
```csharp
public MyClass DeepClone()
{
    var clone = (MyClass)MemberwiseClone();
    clone.Items = new List<string>(this.Items);          // 浅拷贝 List 元素
    clone.Config = this.Config.DeepClone();               // 递归深拷贝嵌套对象
    clone.Map = new Dictionary<string, int>(this.Map);   // 浅拷贝 Dictionary
    return clone;
}
```

### 3. `BinaryFormatter` 已在 .NET 中被弃用

`BinaryFormatter` 从 .NET 5 开始标记 `[Obsolete]`，.NET 8+ 默认抛出 `PlatformNotSupportedException`（安全漏洞 CVE：反序列化可执行任意代码）。

**替代方案：**

| 方案 | 性能 | 适用场景 |
|------|------|---------|
| `System.Text.Json` | 中 | 通用深拷贝、跨平台 |
| 手写递归 Clone | 快 | 对象结构已知且简单 |
| 表达式树编译 | 最快 | 性能敏感路径 |
| `Force.DeepCloner` (NuGet) | 快 | 第三方依赖可接受 |
| `record` + `with` | 最快 | 不可变对象、DTO |

### 4. 循环引用导致深拷贝卡死

当对象图中存在循环引用（A 引用 B，B 也引用 A），递归深拷贝会陷入无限循环。

```csharp
public class Node
{
    public string Name { get; set; } = "";
    public Node? Parent { get; set; }
    public List<Node> Children { get; set; } = new();

    // ❌ 递归深拷贝：Parent → Children → Parent → ... StackOverflow!
    public Node DeepClone()
    {
        var clone = (Node)MemberwiseClone();
        clone.Children = Children.Select(c => c.DeepClone()).ToList();
        foreach (var child in clone.Children)
            child.Parent = clone;
        return clone;
    }
}
```

**解决方案：** 维护已克隆对象映射表（`Dictionary<object, object>` 或 `ConditionalWeakTable<object, object>`），遇到已克隆对象时直接返回引用：

```csharp
public Node DeepClone(Dictionary<object, object>? cloneMap = null)
{
    cloneMap ??= new Dictionary<object, object>(ReferenceEqualityComparer.Instance);

    if (cloneMap.TryGetValue(this, out var existing))
        return (Node)existing;

    var clone = (Node)MemberwiseClone();
    cloneMap[this] = clone;

    clone.Children = Children.Select(c => c.DeepClone(cloneMap)).ToList();
    foreach (var child in clone.Children)
        child.Parent = clone;

    return clone;
}
```

> 使用 `ReferenceEqualityComparer.Instance` 避免 Equals 被重写时误判（例如某个类重写了 Equals 导致两个不同实例被判为"相同"）。

### 5. 将 `record` 的 `with` 当作深拷贝

`with` 表达式在 `record` 中做的是**浅拷贝**。如果 record 包含可变引用类型属性，`with` 后的新对象仍与原对象共享该引用：

```csharp
var a = new MyRecord(new List<string> { "x" });
var b = a with { };  // 浅拷贝！
b.Items.Add("y");
// a.Items 也变成了 ["x", "y"]
```

### 6. 原型注册表泄露可变状态

注册表中的原型被多方克隆使用，如果原型的引用类型成员被意外修改，所有后续 Clone 都会继承被污染的状态。

**正确做法：** 注册原型后将它们视为**只读**；或使用不可变类型（`record`、`IReadOnlyList<T>`、`ImmutableArray<T>`）作为原型。
