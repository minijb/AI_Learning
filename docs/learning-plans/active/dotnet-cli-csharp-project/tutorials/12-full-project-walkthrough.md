---
title: "综合实战 — 构建完整多层项目"
updated: 2026-06-10
tags: [dotnet, cli, walkthrough, multi-layer, project-structure, 实战]
---

# 综合实战 — 构建完整多层项目

> 所属计划: [[plan|dotnet CLI 与 C# 工程构建]]
> 预计耗时: 90 分钟
> 前置知识: [[01-dotnet-env-setup|01]] [[02-dotnet-new|02]] [[03-dotnet-build-run-clean|03]] [[04-dotnet-add-remove|04]] [[05-dotnet-sln|05]] [[06-csproj-and-sln-deep-dive|06]] [[07-dotnet-test|07]] [[08-dotnet-publish-pack|08]] [[09-multi-targeting|09]] [[10-dotnet-tool|10]] [[11-dotnet-ef|11]]

---

## 1. 概念讲解

### 本次实战的目标

用**纯 dotnet CLI** 从零搭建一个真实的多层 C# 解决方案：**BookStore** — 一个模拟书店管理系统。你将经历一个完整开发周期：

1. 创建解决方案骨架（`sln`、`global.json`、`Directory.Build.props`）
2. 创建三个项目（Core 类库、Data 类库、App 控制台）
3. 添加项目引用和 NuGet 包
4. 编写领域模型、EF Core 上下文、仓储、控制台入口
5. 为 Core 和 Data 编写单元测试
6. 执行 EF Core 数据库迁移
7. 发布控制台应用、打包类库

### 解决方案结构

```
BookStore/
├── BookStore.sln
├── global.json                       # SDK 版本锁定
├── Directory.Build.props             # 共享 MSBuild 属性
├── src/
│   ├── BookStore.Core/               # classlib — 领域模型、接口
│   │   ├── BookStore.Core.csproj
│   │   ├── Models/
│   │   │   └── Book.cs
│   │   └── Interfaces/
│   │       └── IBookRepository.cs
│   ├── BookStore.Data/               # classlib — EF Core 实现
│   │   ├── BookStore.Data.csproj
│   │   ├── BookStoreDbContext.cs
│   │   └── BookRepository.cs
│   └── BookStore.App/                # console — 应用入口
│       ├── BookStore.App.csproj
│       └── Program.cs
├── tests/
│   ├── BookStore.Core.Tests/         # xunit 测试 Core
│   │   ├── BookStore.Core.Tests.csproj
│   │   └── BookTests.cs
│   └── BookStore.Data.Tests/         # xunit 测试 Data
│       ├── BookStore.Data.Tests.csproj
│       └── BookRepositoryTests.cs
└── .config/
    └── dotnet-tools.json             # 本地工具清单 (dotnet-ef)
```

### 分层职责

| 层 | 项目 | 职责 | 依赖 |
|---:|------|------|------|
| **领域** | `BookStore.Core` | 实体模型、接口定义 | 无外部依赖 |
| **数据** | `BookStore.Data` | EF Core 上下文、仓储实现 | → Core |
| **应用** | `BookStore.App` | 控制台入口、业务编排 | → Data（传递依赖 Core） |
| **测试** | `*.Tests` | 单元测试 | → 被测试项目 + xunit |

> [!note] 依赖方向
> App → Data → Core。Core 不依赖任何人，Data 依赖 Core 的接口和模型，App 依赖 Data（并传递依赖 Core）。这是经典的 **依赖倒置** 的物理体现：高层模块依赖抽象（Core 的接口），低层模块（Data）实现抽象。

---

## 2. 代码示例

### 步骤 1：创建解决方案骨架

```bash
# 创建工作目录
mkdir BookStore
cd BookStore

# 创建空白解决方案
dotnet new sln -n BookStore
```

输出：
```
The template "Solution File" was created successfully.
```

```bash
# 创建 global.json — 锁定 SDK 版本
dotnet new globaljson --sdk-version 8.0.300 --roll-forward latestPatch
```

`global.json` 生成内容：

```json
{
  "sdk": {
    "version": "8.0.300",
    "rollForward": "latestPatch",
    "allowPrerelease": false
  }
}
```

> [!tip] `rollForward: latestPatch` 的含义
> 如果机器上是 `8.0.301`、`8.0.302` 等补丁版本，允许自动使用。配置文件中的 `latestPatch` 确保团队使用同一 SDK 主/次版本，仅补丁号可浮动。

```bash
# 创建 Directory.Build.props — 共享 MSBuild 属性
```

创建文件 `Directory.Build.props`（项目根目录）：

```xml
<Project>
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <Authors>BookStore Team</Authors>
    <Company>BookStore Inc.</Company>
  </PropertyGroup>
</Project>
```

> [!important] `Directory.Build.props` 的作用域
> 放在解决方案根目录后，**所有子目录中的 `.csproj` 都会自动导入**这个文件。无需在每个项目文件中重复 `<TargetFramework>`、`<Nullable>` 等公共属性。这是 DRY 原则在 MSBuild 层面的体现。

### 步骤 2：创建项目

```bash
# 进入 src 子目录
mkdir src
cd src

# 创建类库项目
dotnet new classlib -n BookStore.Core -o BookStore.Core
dotnet new classlib -n BookStore.Data -o BookStore.Data

# 创建控制台项目
dotnet new console -n BookStore.App -o BookStore.App

# 返回根目录
cd ..

# 创建测试目录和项目
mkdir tests
cd tests

dotnet new xunit -n BookStore.Core.Tests -o BookStore.Core.Tests
dotnet new xunit -n BookStore.Data.Tests -o BookStore.Data.Tests

cd ..
```

验证项目结构：

```bash
dotnet sln list
```

输出（此时项目尚未添加到解决方案）：
```
No projects found in the solution.
```

### 步骤 3：添加项目到解决方案（带解决方案文件夹）

```bash
# 添加项目并放入解决方案文件夹
dotnet sln BookStore.sln add src/BookStore.Core/BookStore.Core.csproj     --solution-folder src
dotnet sln BookStore.sln add src/BookStore.Data/BookStore.Data.csproj     --solution-folder src
dotnet sln BookStore.sln add src/BookStore.App/BookStore.App.csproj       --solution-folder src
dotnet sln BookStore.sln add tests/BookStore.Core.Tests/BookStore.Core.Tests.csproj --solution-folder tests
dotnet sln BookStore.sln add tests/BookStore.Data.Tests/BookStore.Data.Tests.csproj --solution-folder tests
```

验证：

```bash
dotnet sln list
```

输出：
```
Project(s)
----------
src/BookStore.Core/BookStore.Core.csproj
src/BookStore.Data/BookStore.Data.csproj
src/BookStore.App/BookStore.App.csproj
tests/BookStore.Core.Tests/BookStore.Core.Tests.csproj
tests/BookStore.Data.Tests/BookStore.Data.Tests.csproj
```

> [!tip] 解决方案文件夹是虚拟分组
> `--solution-folder src` 在 `.sln` 文件中创建虚拟文件夹，不影响磁盘上的目录结构。在 Visual Studio 或 Rider 中打开时，项目会按 `src` 和 `tests` 分组显示。

### 步骤 4：添加项目引用

```bash
# Data → Core
dotnet add src/BookStore.Data/BookStore.Data.csproj reference src/BookStore.Core/BookStore.Core.csproj

# App → Data
dotnet add src/BookStore.App/BookStore.App.csproj reference src/BookStore.Data/BookStore.Data.csproj
```

> [!note] 测试项目的引用在步骤 9 中添加。

验证引用链：

```bash
dotnet list src/BookStore.App/BookStore.App.csproj reference
```

输出：
```
Project reference(s)
--------------------
..\BookStore.Data\BookStore.Data.csproj
```

### 步骤 5：添加 NuGet 包

```bash
# Data 项目 — EF Core SQLite 提供程序
dotnet add src/BookStore.Data/BookStore.Data.csproj package Microsoft.EntityFrameworkCore.Sqlite

# App 项目 — Serilog 日志库（控制台 sink）
dotnet add src/BookStore.App/BookStore.App.csproj package Serilog.Sinks.Console

# Core 项目不添加外部包 — 保持纯净
```

验证包引用：

```bash
dotnet list src/BookStore.Data/BookStore.Data.csproj package
```

输出：
```
Top-level Package                     Requested   Resolved
> Microsoft.EntityFrameworkCore.Sqlite 8.0.*       8.0.x
```

### 步骤 6：编写领域模型 — BookStore.Core

> [!warning] 每个文件都需要手动创建
> `dotnet new classlib` 只创建了 `Class1.cs`。后续所有代码文件都需手动创建。以下用 `dotnet new` 创建工作区后，用文本编辑器添加文件。

**`src/BookStore.Core/Models/Book.cs`**：

```csharp
namespace BookStore.Core.Models;

/// <summary>
/// 书籍领域实体。
/// </summary>
public class Book
{
    public int Id { get; set; }
    public string Title { get; set; } = string.Empty;
    public string Author { get; set; } = string.Empty;
    public string Isbn { get; set; } = string.Empty;
    public decimal Price { get; set; }
    public int Stock { get; set; }

    /// <summary>
    /// 是否有库存可供销售。
    /// </summary>
    public bool IsAvailable => Stock > 0;

    /// <summary>
    /// 扣减库存。返回是否成功。
    /// </summary>
    public bool TrySell(int quantity = 1)
    {
        if (quantity <= 0) return false;
        if (Stock < quantity) return false;
        Stock -= quantity;
        return true;
    }

    /// <summary>
    /// 补货。
    /// </summary>
    public void Restock(int quantity)
    {
        if (quantity <= 0) return;
        Stock += quantity;
    }
}
```

**`src/BookStore.Core/Interfaces/IBookRepository.cs`**：

```csharp
using BookStore.Core.Models;

namespace BookStore.Core.Interfaces;

/// <summary>
/// 书籍仓储接口 — 定义数据访问契约。
/// 具体实现（EF Core / 内存 / API 客户端）放在 Data 层。
/// </summary>
public interface IBookRepository
{
    Task<Book?> GetByIdAsync(int id);
    Task<IEnumerable<Book>> GetAllAsync();
    Task<IEnumerable<Book>> SearchByTitleAsync(string keyword);
    Task AddAsync(Book book);
    Task UpdateAsync(Book book);
    Task DeleteAsync(int id);
    Task SaveChangesAsync();
}
```

> [!important] 为什么接口放 Core 而不是 Data？
> 接口是**契约**，属于领域层。Data 层实现契约。App 层只依赖接口，不依赖具体实现。这是依赖倒置原则（DIP）的核心：高层模块（App）不依赖低层模块（Data），二者都依赖抽象（Core 中的接口）。

### 步骤 7：编写数据访问层 — BookStore.Data

**`src/BookStore.Data/BookStoreDbContext.cs`**：

```csharp
using BookStore.Core.Models;
using Microsoft.EntityFrameworkCore;

namespace BookStore.Data;

public class BookStoreDbContext : DbContext
{
    public DbSet<Book> Books => Set<Book>();

    public BookStoreDbContext(DbContextOptions<BookStoreDbContext> options)
        : base(options)
    {
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Book>(entity =>
        {
            entity.HasKey(b => b.Id);
            entity.Property(b => b.Title).IsRequired().HasMaxLength(200);
            entity.Property(b => b.Author).IsRequired().HasMaxLength(100);
            entity.Property(b => b.Isbn).IsRequired().HasMaxLength(13);
            entity.HasIndex(b => b.Isbn).IsUnique();
            entity.Property(b => b.Price).HasColumnType("decimal(10,2)");
        });

        // 种子数据
        modelBuilder.Entity<Book>().HasData(
            new Book { Id = 1, Title = "CLR via C#", Author = "Jeffrey Richter",
                       Isbn = "9780735667457", Price = 59.99m, Stock = 10 },
            new Book { Id = 2, Title = "Pro ASP.NET Core 8", Author = "Adam Freeman",
                       Isbn = "9781633434563", Price = 49.99m, Stock = 5 },
            new Book { Id = 3, Title = "C# in Depth", Author = "Jon Skeet",
                       Isbn = "9781617294532", Price = 44.99m, Stock = 3 }
        );
    }
}
```

**`src/BookStore.Data/BookRepository.cs`**：

```csharp
using BookStore.Core.Interfaces;
using BookStore.Core.Models;
using Microsoft.EntityFrameworkCore;

namespace BookStore.Data;

public class BookRepository : IBookRepository
{
    private readonly BookStoreDbContext _context;

    public BookRepository(BookStoreDbContext context)
    {
        _context = context;
    }

    public async Task<Book?> GetByIdAsync(int id)
        => await _context.Books.FindAsync(id);

    public async Task<IEnumerable<Book>> GetAllAsync()
        => await _context.Books.ToListAsync();

    public async Task<IEnumerable<Book>> SearchByTitleAsync(string keyword)
        => await _context.Books
            .Where(b => b.Title.Contains(keyword))
            .ToListAsync();

    public async Task AddAsync(Book book)
    {
        await _context.Books.AddAsync(book);
    }

    public Task UpdateAsync(Book book)
    {
        _context.Books.Update(book);
        return Task.CompletedTask;
    }

    public Task DeleteAsync(int id)
    {
        var book = _context.Books.Find(id);
        if (book is not null)
            _context.Books.Remove(book);
        return Task.CompletedTask;
    }

    public async Task SaveChangesAsync()
        => await _context.SaveChangesAsync();
}
```

### 步骤 8：编写控制台应用 — BookStore.App

**`src/BookStore.App/Program.cs`**：

```csharp
using BookStore.Core.Interfaces;
using BookStore.Core.Models;
using BookStore.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Serilog;

// ── 日志配置 ──
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Information()
    .WriteTo.Console()
    .CreateLogger();

try
{
    // ── DI 容器 ──
    var services = new ServiceCollection();

    services.AddDbContext<BookStoreDbContext>(options =>
        options.UseSqlite("Data Source=bookstore.db"));

    services.AddScoped<IBookRepository, BookRepository>();

    var provider = services.BuildServiceProvider();

    // ── 初始化数据库 ──
    using (var scope = provider.CreateScope())
    {
        var db = scope.ServiceProvider.GetRequiredService<BookStoreDbContext>();
        await db.Database.EnsureCreatedAsync();
    }

    Log.Information("BookStore database initialized.");

    // ── 业务操作 ──
    using (var scope = provider.CreateScope())
    {
        var repo = scope.ServiceProvider.GetRequiredService<IBookRepository>();

        // 查询所有书籍
        var books = (await repo.GetAllAsync()).ToList();
        Log.Information("Found {Count} books:", books.Count);

        foreach (var book in books)
        {
            Log.Information("  [{Id}] \"{Title}\" by {Author} — ${Price} (Stock: {Stock})",
                book.Id, book.Title, book.Author, book.Price, book.Stock);
        }

        // 卖出一本
        var target = await repo.GetByIdAsync(1);
        if (target is not null && target.TrySell())
        {
            await repo.UpdateAsync(target);
            await repo.SaveChangesAsync();
            Log.Information("Sold one copy of \"{Title}\". Remaining stock: {Stock}",
                target.Title, target.Stock);
        }

        // 添加新书
        var newBook = new Book
        {
            Title = "Domain-Driven Design",
            Author = "Eric Evans",
            Isbn = "9780321125217",
            Price = 54.99m,
            Stock = 7
        };
        await repo.AddAsync(newBook);
        await repo.SaveChangesAsync();
        Log.Information("Added new book: \"{Title}\" (Id: {Id})", newBook.Title, newBook.Id);
    }
}
catch (Exception ex)
{
    Log.Fatal(ex, "Application terminated unexpectedly");
}
finally
{
    await Log.CloseAndFlushAsync();
}
```

> [!tip] `EnsureCreatedAsync` vs Migration
> `EnsureCreatedAsync` 快速创建数据库和表（适合开发和 Demo）。生产环境应使用 `dotnet ef migrations`（见步骤 11）。

现在运行它：

```bash
dotnet run --project src/BookStore.App/BookStore.App.csproj
```

预期输出：

```
[HH:mm:ss INF] BookStore database initialized.
[HH:mm:ss INF] Found 3 books:
[HH:mm:ss INF]   [1] "CLR via C#" by Jeffrey Richter — $59.99 (Stock: 10)
[HH:mm:ss INF]   [2] "Pro ASP.NET Core 8" by Adam Freeman — $49.99 (Stock: 5)
[HH:mm:ss INF]   [3] "C# in Depth" by Jon Skeet — $44.99 (Stock: 3)
[HH:mm:ss INF] Sold one copy of "CLR via C#". Remaining stock: 9
[HH:mm:ss INF] Added new book: "Domain-Driven Design" (Id: 4)
```

### 步骤 9：编写单元测试

首先添加测试项目的引用：

```bash
dotnet add tests/BookStore.Core.Tests/BookStore.Core.Tests.csproj reference src/BookStore.Core/BookStore.Core.csproj

dotnet add tests/BookStore.Data.Tests/BookStore.Data.Tests.csproj reference src/BookStore.Data/BookStore.Data.csproj
```

**`tests/BookStore.Core.Tests/BookTests.cs`**：

```csharp
using BookStore.Core.Models;

namespace BookStore.Core.Tests;

public class BookTests
{
    [Fact]
    public void TrySell_WhenStockAvailable_ReturnsTrueAndDecrementsStock()
    {
        // Arrange
        var book = new Book { Stock = 5 };

        // Act
        var result = book.TrySell(2);

        // Assert
        Assert.True(result);
        Assert.Equal(3, book.Stock);
    }

    [Fact]
    public void TrySell_WhenStockInsufficient_ReturnsFalseAndPreservesStock()
    {
        var book = new Book { Stock = 1 };

        var result = book.TrySell(2);

        Assert.False(result);
        Assert.Equal(1, book.Stock);
    }

    [Fact]
    public void TrySell_WithZeroQuantity_ReturnsFalse()
    {
        var book = new Book { Stock = 5 };

        var result = book.TrySell(0);

        Assert.False(result);
    }

    [Fact]
    public void TrySell_WithNegativeQuantity_ReturnsFalse()
    {
        var book = new Book { Stock = 5 };

        var result = book.TrySell(-1);

        Assert.False(result);
    }

    [Fact]
    public void Restock_IncreasesStock()
    {
        var book = new Book { Stock = 3 };

        book.Restock(5);

        Assert.Equal(8, book.Stock);
    }

    [Fact]
    public void Restock_WithNegativeQuantity_DoesNotChangeStock()
    {
        var book = new Book { Stock = 3 };

        book.Restock(-2);

        Assert.Equal(3, book.Stock);
    }

    [Fact]
    public void IsAvailable_WhenStockPositive_ReturnsTrue()
    {
        var book = new Book { Stock = 1 };
        Assert.True(book.IsAvailable);
    }

    [Fact]
    public void IsAvailable_WhenStockZero_ReturnsFalse()
    {
        var book = new Book { Stock = 0 };
        Assert.False(book.IsAvailable);
    }
}
```

**`tests/BookStore.Data.Tests/BookRepositoryTests.cs`**：

```csharp
using BookStore.Core.Interfaces;
using BookStore.Core.Models;
using BookStore.Data;
using Microsoft.EntityFrameworkCore;

namespace BookStore.Data.Tests;

public class BookRepositoryTests : IDisposable
{
    private readonly BookStoreDbContext _context;
    private readonly IBookRepository _repository;

    public BookRepositoryTests()
    {
        var options = new DbContextOptionsBuilder<BookStoreDbContext>()
            .UseSqlite("Data Source=:memory:")   // 内存数据库 — 每次测试独立
            .Options;

        _context = new BookStoreDbContext(options);
        _context.Database.OpenConnection();       // 保持连接使内存数据库存活
        _context.Database.EnsureCreated();

        _repository = new BookRepository(_context);
    }

    public void Dispose()
    {
        _context.Database.CloseConnection();
        _context.Dispose();
    }

    [Fact]
    public async Task AddAsync_PersistsBook()
    {
        var book = new Book
        {
            Title = "Test Book",
            Author = "Test Author",
            Isbn = "1234567890123",
            Price = 29.99m,
            Stock = 10
        };

        await _repository.AddAsync(book);
        await _repository.SaveChangesAsync();

        var result = await _repository.GetByIdAsync(book.Id);
        Assert.NotNull(result);
        Assert.Equal("Test Book", result!.Title);
    }

    [Fact]
    public async Task GetAllAsync_ReturnsSeedData()
    {
        var books = (await _repository.GetAllAsync()).ToList();

        Assert.NotEmpty(books);
        Assert.Contains(books, b => b.Title == "CLR via C#");
    }

    [Fact]
    public async Task SearchByTitleAsync_FindsMatchingBooks()
    {
        var results = (await _repository.SearchByTitleAsync("ASP.NET")).ToList();

        Assert.Single(results);
        Assert.Equal("Pro ASP.NET Core 8", results[0].Title);
    }

    [Fact]
    public async Task DeleteAsync_RemovesBook()
    {
        await _repository.DeleteAsync(2); // seed data ID 2
        await _repository.SaveChangesAsync();

        var result = await _repository.GetByIdAsync(2);
        Assert.Null(result);
    }
}
```

> [!tip] SQLite 内存数据库用于测试
> `Data Source=:memory:` 创建完全在内存中的 SQLite 数据库，速度极快。调用 `OpenConnection()` 后保持连接，否则内存数据库会被销毁。每个测试类创建新实例，测试之间完全隔离。

### 步骤 10：运行测试

```bash
dotnet test
```

预期输出（省略构建日志）：

```
Passed!  - Failed:     0, Passed:    12, Skipped:     0, Total:    12, Duration: X s
```

> [!tip] 单独运行某个项目的测试
> ```bash
> dotnet test tests/BookStore.Core.Tests/BookStore.Core.Tests.csproj
> ```

### 步骤 11：EF Core 迁移

首先安装本地工具：

```bash
# 在项目根目录执行
dotnet new tool-manifest

# 安装 dotnet-ef 为本地工具
dotnet tool install dotnet-ef
```

这会创建 `.config/dotnet-tools.json`：

```json
{
  "version": 1,
  "isRoot": true,
  "tools": {
    "dotnet-ef": {
      "version": "8.0.0",
      "commands": ["dotnet-ef"]
    }
  }
}
```

> [!tip] 本地工具 vs 全局工具
> 本地工具（`dotnet new tool-manifest` + `dotnet tool install`）将工具版本锁定在仓库中，团队成员 `dotnet tool restore` 即可获得相同版本。全局工具（`dotnet tool install -g`）是机器级别的，不随仓库版本控制。

创建初始迁移：

```bash
dotnet ef migrations add InitialCreate --project src/BookStore.Data/BookStore.Data.csproj --startup-project src/BookStore.App/BookStore.App.csproj
```

输出：
```
Build started...
Build succeeded.
Done. To undo this action, use 'ef migrations remove'
```

> [!note] 为什么需要 `--startup-project`？
> EF Core 工具需要一个可执行项目来解析 `DbContext` 的依赖注入配置。`BookStore.Data` 是类库，不能直接运行。`--startup-project` 指向控制台项目 `BookStore.App`。

查看生成的迁移文件：

```bash
dir src\BookStore.Data\Migrations\
```

输出：
```
InitialCreate.cs
BookStoreDbContextModelSnapshot.cs
```

应用迁移：

```bash
dotnet ef database update --project src/BookStore.Data/BookStore.Data.csproj --startup-project src/BookStore.App/BookStore.App.csproj
```

> [!warning] 迁移后不要再调用 `EnsureCreatedAsync`
> `EnsureCreatedAsync` 和 Migration 是两种互斥的数据库初始化策略。生产代码中应移除 `EnsureCreatedAsync`，改用 `context.Database.Migrate()`。

更新 `Program.cs` 中的数据库初始化：

```csharp
// 将
await db.Database.EnsureCreatedAsync();
// 替换为
await db.Database.MigrateAsync();
```

### 步骤 12：发布应用

```bash
# 发布为单文件可执行程序
dotnet publish src/BookStore.App/BookStore.App.csproj -c Release -o ./publish --self-contained false -p:PublishSingleFile=true
```

输出：
```
BookStore.App -> D:\BookStore\publish\BookStore.App.exe
BookStore.App -> D:\BookStore\publish\BookStore.App.dll
...
```

> [!tip] `--self-contained false` 的含义
> 不打包 .NET 运行时，目标机器需要安装对应版本的 .NET Runtime。输出文件很小（几百 KB）。如果目标机器没有运行时，改用 `--self-contained true`，但输出会包含 ~70 MB 的运行时文件。

运行发布后的应用：

```bash
./publish/BookStore.App.exe
```

### 步骤 13：打包类库

```bash
# 打包 Core
dotnet pack src/BookStore.Core/BookStore.Core.csproj -c Release -o ./nupkgs

# 打包 Data
dotnet pack src/BookStore.Data/BookStore.Data.csproj -c Release -o ./nupkgs
```

输出：
```
Successfully created package 'D:\BookStore\nupkgs\BookStore.Core.1.0.0.nupkg'.
Successfully created package 'D:\BookStore\nupkgs\BookStore.Data.1.0.0.nupkg'.
```

---

## 3. 练习

### 练习 1：添加分类功能

扩展 BookStore：为书籍添加 `Category`（分类）。

**任务：**

1. 在 `BookStore.Core` 中创建 `Models/Category.cs` 实体（包含 `Id` 和 `Name`）
2. 在 `Book` 实体中添加 `CategoryId` 外键和 `Category?` 导航属性
3. 更新 `BookStoreDbContext` — 添加 `DbSet<Category>` 和在 `OnModelCreating` 中配置关系
4. 创建迁移并更新数据库：`dotnet ef migrations add AddCategory`
5. 在 `Program.cs` 中查询"某个分类下的所有书籍"并打印
6. 为 `Category` 和新的查询功能写 2 个单元测试

### 练习 2：添加 ASP.NET Core Web API 前端

为已有的三层架构添加一个 Web API 入口。

**任务：**

1. 用 `dotnet new webapi` 创建 `src/BookStore.Api/` 项目
2. 添加对 `BookStore.Data` 的项目引用
3. 在 `Program.cs` 中注册 `BookStoreDbContext`（用 SQLite 连接字符串）和 `IBookRepository`
4. 创建 `Controllers/BooksController.cs`：
   - `GET /api/books` — 返回所有书籍
   - `GET /api/books/{id}` — 返回单本书籍
   - `POST /api/books` — 添加新书
5. 用 `dotnet run` 启动，用浏览器或 `curl` 访问 `http://localhost:5000/api/books`
6. 写一个集成测试，使用 `WebApplicationFactory<T>` 测试 `GET /api/books`

### 练习 3：Docker 化部署

将发布后的 App 打包为 Docker 镜像。

**任务：**

1. 创建 `Dockerfile`，使用多阶段构建：
   - 阶段 1：`mcr.microsoft.com/dotnet/sdk:8.0` 编译项目
   - 阶段 2：`mcr.microsoft.com/dotnet/runtime:8.0` 运行
2. 构建镜像：`docker build -t bookstore-app .`
3. 运行容器：`docker run --rm bookstore-app`
4. 思考：为什么 `-p:PublishSingleFile=true` 在 Docker 中不是必需的？（提示：Docker 镜像自带运行时）
5. 优化 Dockerfile 以利用层缓存（先 `dotnet restore`，再复制源码）

---


## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> **添加 Category 分类功能**：
>
> **1. 创建 `Category` 实体 (`src/BookStore.Core/Models/Category.cs`)**：
>
> ```csharp
> namespace BookStore.Core.Models;
>
> public class Category
> {
>     public int Id { get; set; }
>     public string Name { get; set; } = string.Empty;
>
>     // 导航属性：一个分类有多本书
>     public ICollection<Book> Books { get; set; } = new List<Book>();
> }
> ```
>
> **2. 修改 `Book` 实体 — 添加外键和导航属性**：
>
> ```csharp
> // 在 Book.cs 中添加
> public int? CategoryId { get; set; }
> public Category? Category { get; set; }
> ```
>
> **3. 更新 `BookStoreDbContext.OnModelCreating` — 配置关系**：
>
> ```csharp
> // 在 OnModelCreating 中添加
> modelBuilder.Entity<Book>(entity =>
> {
>     // ... 已有配置 ...
>
>     // 新增：Book → Category 的多对一关系
>     entity.HasOne(b => b.Category)
>           .WithMany(c => c.Books)
>           .HasForeignKey(b => b.CategoryId)
>           .OnDelete(DeleteBehavior.SetNull);
> });
>
> // 添加 Category 种子数据
> modelBuilder.Entity<Category>().HasData(
>     new Category { Id = 1, Name = ".NET" },
>     new Category { Id = 2, Name = "Web" },
>     new Category { Id = 3, Name = "Design" }
> );
>
> // 更新 Book 种子数据，关联 CategoryId
> // 将 CLR via C# 的种子数据中添加 CategoryId = 1
> ```
>
> **并在 DbContext 中暴露 DbSet**：
>
> ```csharp
> public DbSet<Category> Categories => Set<Category>();
> ```
>
> **4. 创建迁移并更新数据库**：
>
> ```bash
> dotnet ef migrations add AddCategory --project src/BookStore.Data --startup-project src/BookStore.App
> dotnet ef database update --project src/BookStore.Data --startup-project src/BookStore.App
> ```
>
> **5. 在 `Program.cs` 中查询"某分类下的所有书籍"**：
>
> ```csharp
> // 查询 .NET 分类下所有书籍（CategoryId = 1）
> var dotnetBooks = await _context.Books
>     .Include(b => b.Category)
>     .Where(b => b.CategoryId == 1)
>     .ToListAsync();
>
> Log.Information("Books in '.NET' category ({Count}):", dotnetBooks.Count);
> foreach (var b in dotnetBooks)
>     Log.Information("  - \"{Title}\" by {Author}", b.Title, b.Author);
> ```
>
> **6. 单元测试（2个）**：
>
> ```csharp
> // tests/BookStore.Core.Tests/CategoryTests.cs
> using BookStore.Core.Models;
>
> namespace BookStore.Core.Tests;
>
> public class CategoryTests
> {
>     [Fact]
>     public void Category_BooksCollection_IsInitiallyEmpty()
>     {
>         var category = new Category { Name = ".NET" };
>         Assert.Empty(category.Books);
>     }
>
>     [Fact]
>     public void Book_CategoryNavigation_CanBeAssigned()
>     {
>         var category = new Category { Name = "Web" };
>         var book = new Book
>         {
>             Title = "ASP.NET in Action",
>             Category = category,
>             CategoryId = category.Id
>         };
>         Assert.Equal("Web", book.Category!.Name);
>     }
> }
> ```

> [!tip]- 练习 2 参考答案
> **添加 ASP.NET Core Web API 前端**：
>
> ```bash
> # 1. 创建 API 项目
> dotnet new webapi -n BookStore.Api -o src/BookStore.Api --use-controllers false
> ```
>
> ```bash
> # 2. 添加项目引用（Api → Data）
> dotnet add src/BookStore.Api/BookStore.Api.csproj reference src/BookStore.Data/BookStore.Data.csproj
>
> # 3. 加入解决方案
> dotnet sln BookStore.sln add src/BookStore.Api/BookStore.Api.csproj --solution-folder src
> ```
>
> **3. 修改 `src/BookStore.Api/Program.cs`**：
>
> ```csharp
> using BookStore.Core.Interfaces;
> using BookStore.Data;
> using Microsoft.EntityFrameworkCore;
>
> var builder = WebApplication.CreateBuilder(args);
>
> // 注册 EF Core
> builder.Services.AddDbContext<BookStoreDbContext>(options =>
>     options.UseSqlite("Data Source=bookstore.db"));
>
> // 注册仓储
> builder.Services.AddScoped<IBookRepository, BookRepository>();
>
> // 注册控制器
> builder.Services.AddControllers();
>
> var app = builder.Build();
>
> // 初始化数据库
> using (var scope = app.Services.CreateScope())
> {
>     var db = scope.ServiceProvider.GetRequiredService<BookStoreDbContext>();
>     await db.Database.MigrateAsync();
> }
>
> app.MapControllers();
> app.Run();
> ```
>
> **4. 创建 `src/BookStore.Api/Controllers/BooksController.cs`**：
>
> ```csharp
> using BookStore.Core.Interfaces;
> using BookStore.Core.Models;
> using Microsoft.AspNetCore.Mvc;
>
> namespace BookStore.Api.Controllers;
>
> [ApiController]
> [Route("api/[controller]")]
> public class BooksController : ControllerBase
> {
>     private readonly IBookRepository _repo;
>
>     public BooksController(IBookRepository repo)
>     {
>         _repo = repo;
>     }
>
>     [HttpGet]
>     public async Task<ActionResult<IEnumerable<Book>>> GetAll()
>     {
>         var books = await _repo.GetAllAsync();
>         return Ok(books);
>     }
>
>     [HttpGet("{id}")]
>     public async Task<ActionResult<Book>> GetById(int id)
>     {
>         var book = await _repo.GetByIdAsync(id);
>         return book is null ? NotFound() : Ok(book);
>     }
>
>     [HttpPost]
>     public async Task<ActionResult<Book>> Create(Book book)
>     {
>         await _repo.AddAsync(book);
>         await _repo.SaveChangesAsync();
>         return CreatedAtAction(nameof(GetById), new { id = book.Id }, book);
>     }
> }
> ```
>
> ```bash
> # 5. 启动 API 并测试
> dotnet run --project src/BookStore.Api
> # 在另一终端：
> curl http://localhost:5000/api/books
> # 预期：返回 JSON 数组，包含种子数据中的书籍
>
> curl http://localhost:5000/api/books/1
> # 预期：返回 CLR via C# 的 JSON
>
> curl -X POST http://localhost:5000/api/books \
>   -H "Content-Type: application/json" \
>   -d '{"title":"New Book","author":"Author","isbn":"1234567890123","price":29.99,"stock":5}'
> # 预期：返回 201 Created + 新书 JSON（含自动生成的 Id）
> ```
>
> **6. 集成测试（使用 `WebApplicationFactory`）**：
>
> 首先，给 API 项目添加 `InternalsVisibleTo`（在 `.csproj` 中）使测试能访问 `Program`：
>
> ```xml
> <ItemGroup>
>   <InternalsVisibleTo Include="BookStore.Api.Tests" />
> </ItemGroup>
> ```
>
> 然后添加 `Microsoft.AspNetCore.Mvc.Testing` 包到测试项目：
>
> ```bash
> dotnet new xunit -n BookStore.Api.Tests -o tests/BookStore.Api.Tests
> dotnet add tests/BookStore.Api.Tests/BookStore.Api.Tests.csproj reference src/BookStore.Api/BookStore.Api.csproj
> dotnet add tests/BookStore.Api.Tests/BookStore.Api.Tests.csproj package Microsoft.AspNetCore.Mvc.Testing
> ```
>
> ```csharp
> // tests/BookStore.Api.Tests/BooksApiTests.cs
> using System.Net;
> using System.Net.Http.Json;
> using BookStore.Core.Models;
> using Microsoft.AspNetCore.Mvc.Testing;
>
> namespace BookStore.Api.Tests;
>
> public class BooksApiTests : IClassFixture<WebApplicationFactory<Program>>
> {
>     private readonly HttpClient _client;
>
>     public BooksApiTests(WebApplicationFactory<Program> factory)
>     {
>         _client = factory.CreateClient();
>     }
>
>     [Fact]
>     public async Task GetBooks_ReturnsOkAndBooks()
>     {
>         var response = await _client.GetAsync("/api/books");
>
>         Assert.Equal(HttpStatusCode.OK, response.StatusCode);
>         var books = await response.Content.ReadFromJsonAsync<List<Book>>();
>         Assert.NotNull(books);
>         Assert.NotEmpty(books);
>     }
> }
> ```

> [!tip]- 练习 3 参考答案
> **Docker 化部署**：
>
> **1. 创建 `Dockerfile`（多阶段构建 + 层缓存优化）**：
>
> ```dockerfile
> # ── 阶段 1：SDK 编译 ──
> FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
> WORKDIR /src
>
> # 先复制 .csproj 文件（不含源码）以便利用 Docker 层缓存
> COPY src/BookStore.Core/BookStore.Core.csproj   src/BookStore.Core/
> COPY src/BookStore.Data/BookStore.Data.csproj   src/BookStore.Data/
> COPY src/BookStore.App/BookStore.App.csproj     src/BookStore.App/
>
> # 单独 restore — 只要 .csproj 不变，此层就被缓存
> RUN dotnet restore src/BookStore.App/BookStore.App.csproj
>
> # 复制剩余源码
> COPY . .
>
> # 发布为 Release
> RUN dotnet publish src/BookStore.App/BookStore.App.csproj \
>     -c Release -o /app --no-restore
>
> # ── 阶段 2：运行时镜像 ──
> FROM mcr.microsoft.com/dotnet/runtime:8.0 AS runtime
> WORKDIR /app
> COPY --from=build /app .
>
> ENTRYPOINT ["dotnet", "BookStore.App.dll"]
> ```
>
> ```bash
> # 2. 构建镜像
> docker build -t bookstore-app .
>
> # 3. 运行容器
> docker run --rm bookstore-app
> # 预期：看到与 dotnet run 相同的输出 — 列出书籍、卖出、添加新书
> ```
>
> **4. 为什么 `-p:PublishSingleFile=true` 在 Docker 中不是必需的？**
>
> Docker 镜像本身已经包含了 .NET 运行时（`mcr.microsoft.com/dotnet/runtime:8.0`），所以不需要把运行时内嵌到应用里。`PublishSingleFile` 的意义在于让**没有安装 .NET 的裸机**能直接运行；在 Docker 中，运行时就在镜像里，单文件发布反而会增大镜像体积（每个层都包含重复的运行时文件），且没有额外好处。
>
> **5. 层缓存优化分析**：
>
> 上面的 Dockerfile 已经应用了核心缓存策略：
> - **先 `COPY` .csproj → `RUN dotnet restore`**：只要项目文件（依赖声明）不变，restore 层就被缓存
> - **再 `COPY . .` → `RUN dotnet publish`**：只有源码变更时才重新编译
> - 这比"一次性 COPY 全部然后 restore + build"快很多——修改一行 C# 代码时，restore 步骤直接从缓存读取，只重新编译变更的源文件。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。
## 4. 扩展阅读

- [[11-dotnet-ef|dotnet ef — EF Core CLI 工具深入]] — EF Core 迁移、`dotnet ef dbcontext` 命令详解
- [[10-dotnet-tool|dotnet tool — 全局与本地工具]] — 工具清单、`dotnet tool restore`、工具搜索
- [[08-dotnet-publish-pack|dotnet publish / pack — 发布与打包]] — 单文件发布、裁剪、NuGet 元数据
- [[09-multi-targeting|多目标框架与条件编译]] — 让 Core 类库同时支持 `net8.0` 和 `netstandard2.0`
- [Microsoft: Solution-level `--solution-folder`](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-sln) — `dotnet sln add` 的 `--solution-folder` 参数文档
- [Microsoft: `Directory.Build.props`](https://learn.microsoft.com/en-us/visualstudio/msbuild/customize-by-directory) — MSBuild 目录级属性继承机制
- [Microsoft: `global.json` overview](https://learn.microsoft.com/en-us/dotnet/core/tools/global-json) — SDK 版本选择和 `rollForward` 策略
- [Microsoft: Testing with SQLite in-memory](https://learn.microsoft.com/en-us/ef/core/testing/testing-without-the-database#sqlite-in-memory) — EF Core 测试最佳实践
- [Microsoft: NuGet pack with dotnet CLI](https://learn.microsoft.com/en-us/nuget/create-packages/creating-a-package-dotnet-cli) — `dotnet pack` 生成 `.nupkg` 的完整指南
- [Microsoft: .NET Docker samples](https://github.com/dotnet/dotnet-docker/tree/main/samples) — 官方 .NET Docker 示例仓库
- [David Fowler: .NET Architecture Guides](https://github.com/davidfowl/AspNetCoreDiagnosticScenarios) — ASP.NET Core 架构与 DI 最佳实践

---

## 5. 常见陷阱

> [!danger] `#1` — 忘记 `--solution-folder` 导致解决方案扁平化
> 4+ 个项目全部平铺在 `.sln` 根节点下，没有 `src/` 和 `tests/` 分组，IDE 中难以导航。
>
> ```bash
> # ❌ 没有分组
> dotnet sln add src/BookStore.Core/BookStore.Core.csproj
> # ✅ 带解决方案文件夹
> dotnet sln add src/BookStore.Core/BookStore.Core.csproj --solution-folder src
> ```

> [!danger] `#2` — 引用链错误：App 直接引用 Core
> 虽然能编译通过（因为 Data 传递依赖了 Core），但这违反了分层架构的意图。App 引入 Core 的类型意味着你可以绕过 Repository 直接操作领域逻辑，破坏了 Data 层的封装。
>
> ```bash
> # ❌ App 可以绕过 Data 直接访问 Core（甚至直接操作 DbContext）
> dotnet add src/BookStore.App reference src/BookStore.Core
> # ✅ App 只依赖 Data
> dotnet add src/BookStore.App reference src/BookStore.Data
> ```

> [!danger] `#3` — SQLite 内存数据库连接关闭导致表消失
> 测试中如果忘记 `OpenConnection()`，`EnsureCreated()` 创建的表会在数据库连接关闭后立即消失，导致后续查询抛出 `SQLite Error 1: 'no such table'`。
>
> ```csharp
> // ❌ 未保持连接 — 表创建后立即丢失
> var options = new DbContextOptionsBuilder<TestDbContext>()
>     .UseSqlite("Data Source=:memory:")
>     .Options;
> using var ctx = new TestDbContext(options);
> ctx.Database.EnsureCreated();  // 表已创建
> // 此时连接未打开 — SQLite 可能随时销毁内存数据库
>
> // ✅ 手动打开并保持连接
> var connection = new SqliteConnection("Data Source=:memory:");
> connection.Open();
> var options = new DbContextOptionsBuilder<TestDbContext>()
>     .UseSqlite(connection)
>     .Options;
> ```

> [!danger] `#4` — EF Core 迁移命令缺少 `--startup-project`
> `BookStore.Data` 是类库，没有 `Program.cs` 入口。不指定 `--startup-project` 会导致 EF Core 工具无从获知 `DbContext` 的配置方式。
>
> ```bash
> # ❌ 类库缺少入口点，命令会失败
> dotnet ef migrations add InitialCreate --project src/BookStore.Data
> # ✅ 指定启动项目
> dotnet ef migrations add InitialCreate --project src/BookStore.Data \
>     --startup-project src/BookStore.App
> ```

> [!danger] `#5` — `Directory.Build.props` 中设置 `<TargetFramework>` 但个别项目覆盖
> `Directory.Build.props` 提供默认值，但子项目 `.csproj` 中的 `<TargetFramework>` 会覆盖它。如果一个项目需要不同目标框架（例如 `netstandard2.0`），确保在它的 `.csproj` 中显式设置。覆盖不会报错，但可能产生难以追踪的编译错误。
>
> ```xml
> <!-- Directory.Build.props：为所有项目设置默认 TFM -->
> <PropertyGroup>
>   <TargetFramework>net8.0</TargetFramework>
> </PropertyGroup>
>
> <!-- 某个项目的 .csproj：显式覆盖 -->
> <PropertyGroup>
>   <TargetFramework>netstandard2.0</TargetFramework> <!-- 覆盖 net8.0 -->
> </PropertyGroup>
> ```

> [!danger] `#6` — 测试项目忘记引用被测试项目
> 创建 xunit 测试项目后，`dotnet new xunit` 自动添加了 xunit 包引用，但**不会**自动引用你的源代码项目。必须手动 `dotnet add reference`。
>
> ```bash
> # ❌ 测试项目中 `Book` 类型找不到 — 缺少项目引用
> # ✅ 添加引用
> dotnet add tests/BookStore.Core.Tests reference src/BookStore.Core
> ```

> [!danger] `#7` — NuGet 包版本冲突
> 当 `BookStore.Data` 引用了 `Microsoft.EntityFrameworkCore.Sqlite 8.0.0`，而 `BookStore.App` 引用了同一个包的不同版本（例如 `7.0.0`），`dotnet build` 会发出警告或编译失败。
>
> ```bash
> # 诊断包版本冲突
> dotnet list package --include-transitive
> # 统一版本 — 检查 csproj 中的 PackageReference Version
> ```

> [!warning] `#8` — 未提交 `dotnet-tools.json` 到版本控制
> `.config/dotnet-tools.json` 记录了团队使用的本地工具（如 `dotnet-ef`）。如果忘记提交到 Git，其他开发者克隆仓库后运行 `dotnet ef` 会报错"找不到工具"。团队成员应执行 `dotnet tool restore` 自动安装清单中的工具。
