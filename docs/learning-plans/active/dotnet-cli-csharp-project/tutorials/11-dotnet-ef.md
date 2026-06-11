---
title: "dotnet ef — EF Core CLI 工具"
updated: 2026-06-10
tags: [dotnet, ef-core, cli, migrations, database]
---

# `dotnet ef` — EF Core CLI 工具

> 预计耗时: 60min | 前置: [[08-dotnet-publish-pack]] | 类型: 进阶
> 学习目标: 使用 `dotnet ef` 管理数据库迁移、从现有数据库反向生成模型、理解设计时工厂模式

---

## 概念讲解

### 什么是 `dotnet ef`

`dotnet ef` 是 Entity Framework Core 的命令行工具，用于在**设计时（design-time）**管理数据库 schema。它不是 .NET SDK 的内置命令，而是通过 `dotnet tool` 安装的全局或本地工具。

> [!note] `dotnet ef` ≠ 运行时
> `dotnet ef` 只在开发时使用 —— 生成迁移、更新数据库、反向工程 scaffolding。生产环境中通常通过代码调用 `context.Database.Migrate()` 自动执行迁移，而非手动运行 CLI。

### 为什么需要 CLI 工具

- **版本控制数据库 schema**：迁移文件是 C# 代码，可放入 Git 跟踪
- **团队协作**：每个开发者通过迁移同步数据库结构变更
- **自动化部署**：CI/CD 流水线中生成 SQL 脚本，由 DBA 审核后执行
- **现有数据库适配**：通过 `scaffold` 从已有数据库生成 C# 模型和 `DbContext`

### EF Core 工作流（Code First）

```mermaid
flowchart LR
    A[编写 Model 类] --> B[创建/修改 DbContext]
    B --> C[dotnet ef migrations add]
    C --> D[审查生成的迁移代码]
    D --> E[dotnet ef database update]
    E --> F[数据库 schema 同步完成]
```

> [!tip] Database First 与 Code First
> EF Core 支持两种工作流：
> - **Code First**：先写 C# 模型 → 生成迁移 → 应用到数据库（本教程主要路线）
> - **Database First**：已有数据库 → `dotnet ef dbcontext scaffold` 生成模型（反向工程）

---

## 安装 EF Core CLI

### 全局安装（推荐）

```bash
dotnet tool install --global dotnet-ef
```

验证安装：

```bash
dotnet ef --version
```

预期输出示例：

```
Entity Framework Core .NET Command-line Tools
8.0.0
```

### 更新与卸载

```bash
# 更新到最新版本
dotnet tool update --global dotnet-ef

# 卸载
dotnet tool uninstall --global dotnet-ef
```

### 本地安装（项目级）

```bash
# 在项目目录下创建 manifest（如尚未存在）
dotnet new tool-manifest

# 本地安装
dotnet tool install dotnet-ef
```

本地安装后，通过 `dotnet tool run dotnet-ef` 调用，或配置 `.config/dotnet-tools.json`。

### 项目依赖

`dotnet ef` 还需要项目中引用 EF Core 包：

```bash
# 以 SQLite 为例
dotnet add package Microsoft.EntityFrameworkCore.Sqlite
dotnet add package Microsoft.EntityFrameworkCore.Design
```

> [!warning] `Microsoft.EntityFrameworkCore.Design` 必不可少
> 缺少此包会导致 `dotnet ef` 报错：`Unable to create an object of type 'AppDbContext'`。此包提供设计时服务（如 migration 生成器），在运行时并非必需，因此通常标记为 `PrivateAssets`。

---

## `dotnet ef` 命令全景

运行 `dotnet ef --help` 查看完整命令树：

```
Commands:
  database    Commands to manage the database.
  dbcontext   Commands to manage DbContext types.
  migrations  Commands to manage migrations.
```

| 命令 | 用途 |
|------|------|
| `dotnet ef migrations add <name>` | 创建新迁移 |
| `dotnet ef migrations remove` | 删除最后一个迁移 |
| `dotnet ef migrations list` | 列出所有迁移 |
| `dotnet ef migrations script` | 生成 SQL 脚本 |
| `dotnet ef database update` | 将迁移应用到数据库 |
| `dotnet ef database drop` | 删除数据库 |
| `dotnet ef dbcontext info` | 显示 DbContext 信息 |
| `dotnet ef dbcontext scaffold` | 从现有数据库反向生成模型 |
| `dotnet ef dbcontext list` | 列出项目中的 DbContext 类型 |
| `dotnet ef dbcontext optimize` | 生成编译后的模型（性能优化） |

每个命令都支持 `--project`、`--startup-project`、`--context` 等通用选项来指定目标项目。

---

## 数据库上下文与模型设置

在深入 CLI 命令之前，先建立示例项目。以下使用 SQLite —— 无需安装外部数据库服务。

### 创建项目

```bash
dotnet new console -n EfDemo
cd EfDemo
dotnet add package Microsoft.EntityFrameworkCore.Sqlite
dotnet add package Microsoft.EntityFrameworkCore.Design
```

### 定义模型

```csharp
// Models/Author.cs
namespace EfDemo.Models;

public class Author
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public string? Bio { get; set; }
    public List<Book> Books { get; set; } = new();
}
```

```csharp
// Models/Book.cs
namespace EfDemo.Models;

public class Book
{
    public int Id { get; set; }
    public string Title { get; set; } = string.Empty;
    public int Year { get; set; }
    public decimal Price { get; set; }

    public int AuthorId { get; set; }
    public Author Author { get; set; } = null!;
}
```

### 定义 DbContext

```csharp
// Data/AppDbContext.cs
using Microsoft.EntityFrameworkCore;
using EfDemo.Models;

namespace EfDemo.Data;

public class AppDbContext : DbContext
{
    public DbSet<Author> Authors => Set<Author>();
    public DbSet<Book> Books => Set<Book>();

    protected override void OnConfiguring(DbContextOptionsBuilder options)
        => options.UseSqlite("Data Source=app.db");
}
```

> [!note] `OnConfiguring` vs `AddDbContext`
> 生产代码通常在 `Program.cs` 或 `Startup` 中通过 `builder.Services.AddDbContext<AppDbContext>(...)` 配置连接字符串。`OnConfiguring` 方式适用于简单场景和 CLI 工具的独立运行。

---

## 设计时 DbContext 工厂

### 问题

`dotnet ef` 命令在**设计时**运行，不会执行 `Program.cs` 的 `Main` 方法，因此无法使用依赖注入容器。EF Core 需要一个方式在无 DI 环境下创建 `DbContext` 实例。

### 解决方案：`IDesignTimeDbContextFactory<T>`

实现此接口，告诉 CLI 工具如何创建 DbContext：

```csharp
// Data/AppDbContextFactory.cs
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace EfDemo.Data;

public class AppDbContextFactory : IDesignTimeDbContextFactory<AppDbContext>
{
    public AppDbContext CreateDbContext(string[] args)
    {
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseSqlite("Data Source=app.db")
            .Options;

        return new AppDbContext(options);
    }
}
```

> [!tip] `args` 参数
> `args` 是传递给 CLI 命令的额外参数（通过 `--` 分隔符传递，如 `dotnet ef migrations add Init -- --verbose`）。你可以在工厂中解析这些参数来切换环境或连接字符串。

### 备选方案

如果 DbContext 有**无参构造函数**或在 `Program.cs` 的函数中通过 `CreateHostBuilder` 构建，CLI 也可以自动发现 —— 但显式实现 `IDesignTimeDbContextFactory<T>` 是最可靠的方式。

---

## `dotnet ef migrations add` — 创建迁移

### 基本用法

```bash
dotnet ef migrations add InitialCreate
```

CLI 会：

1. 扫描项目中的 `DbContext`（通过工厂或直接构造）
2. 对比模型与当前数据库 schema 的快照
3. 生成两个文件到 `Migrations/` 目录：

```
Migrations/
├── 20260610120000_InitialCreate.cs    # 迁移操作（Up/Down）
├── 20260610120000_InitialCreate.Designer.cs  # 模型快照元数据
└── AppDbContextModelSnapshot.cs        # 当前完整模型快照
```

### 迁移代码解读

```csharp
// Migrations/20260610120000_InitialCreate.cs（简化）
public partial class InitialCreate : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "Authors",
            columns: table => new
            {
                Id = table.Column<int>(nullable: false)
                    .Annotation("Sqlite:Autoincrement", true),
                Name = table.Column<string>(nullable: false),
                Bio = table.Column<string>(nullable: true)
            },
            constraints: table => table.PrimaryKey("PK_Authors", x => x.Id));

        migrationBuilder.CreateTable(
            name: "Books",
            columns: table => new
            {
                Id = table.Column<int>(nullable: false)
                    .Annotation("Sqlite:Autoincrement", true),
                Title = table.Column<string>(nullable: false),
                Year = table.Column<int>(nullable: false),
                Price = table.Column<decimal>(nullable: false),
                AuthorId = table.Column<int>(nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Books", x => x.Id);
                table.ForeignKey(
                    name: "FK_Books_Authors_AuthorId",
                    column: x => x.AuthorId,
                    principalTable: "Authors",
                    principalColumn: "Id",
                    onDelete: ReferentialAction.Cascade);
            });
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropTable(name: "Books");
        migrationBuilder.DropTable(name: "Authors");
    }
}
```

### 常用选项

```bash
# 指定输出目录
dotnet ef migrations add InitialCreate --output-dir Data/Migrations

# 指定迁移类的命名空间
dotnet ef migrations add InitialCreate --namespace EfDemo.Data.Migrations

# 同时指定
dotnet ef migrations add InitialCreate \
    --output-dir Data/Migrations \
    --namespace EfDemo.Data.Migrations
```

### 修改模型后追加迁移

假设给 `Book` 添加 `ISBN` 属性：

```csharp
public string? ISBN { get; set; }
```

运行：

```bash
dotnet ef migrations add AddBookISBN
```

CLI 对比快照，只生成新增列的 `ALTER TABLE` 操作：

```csharp
protected override void Up(MigrationBuilder migrationBuilder)
{
    migrationBuilder.AddColumn<string>(
        name: "ISBN",
        table: "Books",
        nullable: true);
}
```

---

## `dotnet ef migrations remove` — 删除最后一个迁移

```bash
dotnet ef migrations remove
```

> [!warning] 仅删除未应用到数据库的迁移
> 如果迁移已通过 `database update` 应用到数据库，必须先用 `database update <前一个迁移名>` 回滚，然后才能 `remove`。否则报错：`The migration 'xxx' has already been applied to the database.`

### 工作流

```bash
# 1. 创建了一个不满意的迁移（尚未 update）
dotnet ef migrations add BadMigration

# 2. 回退迁移文件（删除 Migrations/ 中的对应文件，重置快照）
dotnet ef migrations remove

# 3. 修正模型后重新生成
dotnet ef migrations add CorrectMigration
```

### 已应用迁移的移除流程

```bash
# 先回滚到前一个迁移
dotnet ef database update PreviousMigration

# 再移除
dotnet ef migrations remove
```

---

## `dotnet ef migrations list` — 列出所有迁移

```bash
dotnet ef migrations list
```

输出示例：

```
20260610120000_InitialCreate
20260610130000_AddBookISBN
20260610140000_AddPublisher
```

每一行是一个迁移名称（按时间戳排序）。配合 `--json` 输出机器可读格式：

```bash
dotnet ef migrations list --json
```

---

## `dotnet ef migrations script` — 生成 SQL 脚本

### 基本用法（从第一个迁移到最新）

```bash
dotnet ef migrations script
```

### 指定迁移范围

```bash
# 从 InitialCreate 到 AddBookISBN（含）
dotnet ef migrations script InitialCreate AddBookISBN

# 从零（数据库为空）到 AddBookISBN
dotnet ef migrations script 0 AddBookISBN
```

### 输出到文件

```bash
dotnet ef migrations script -o migrate.sql
```

### 生成幂等脚本（生产环境推荐）

```bash
dotnet ef migrations script --idempotent -o migrate.sql
```

> [!tip] 幂等脚本
> 幂等脚本包含 `IF NOT EXISTS` 检查，可以安全地重复执行。适用于 CI/CD 流水线：无论当前数据库处于哪个迁移版本，执行脚本后都会达到最新状态。

生成内容示例：

```sql
CREATE TABLE IF NOT EXISTS "__EFMigrationsHistory" (
    "MigrationId" TEXT NOT NULL,
    "ProductVersion" TEXT NOT NULL
);

-- 后续的 CREATE TABLE IF NOT EXISTS / ALTER TABLE 等
```

---

## `dotnet ef database update` — 应用迁移

### 基本用法（应用到最新迁移）

```bash
dotnet ef database update
```

这会：
1. 检查 `__EFMigrationsHistory` 表（不存在则创建）
2. 对比已应用的迁移记录
3. 依次执行未应用的迁移的 `Up()` 方法

### 回滚到指定迁移

```bash
# 回滚到 InitialCreate（不含）
dotnet ef database update InitialCreate

# 或者回滚到数据库为空
dotnet ef database update 0
```

回滚时，CLI 按逆序执行每个迁移的 `Down()` 方法。

> [!warning] 回滚可能丢数据
> `Down()` 中的 `DropTable`、`DropColumn` 等操作**不可逆地删除数据**。生产环境应使用 SQL 脚本审核后再执行，避免直接 `update` 回滚。

### 连接字符串覆盖

```bash
dotnet ef database update --connection "Data Source=staging.db"
```

---

## `dotnet ef database drop` — 删除数据库

```bash
dotnet ef database drop
```

### 跳过确认提示

```bash
dotnet ef database drop --force
```

### 仅删除（不检查迁移）

```bash
dotnet ef database drop --force --no-connect
```

`--no-connect`：不尝试连接数据库，直接删文件（对 SQLite 等文件数据库有效）。

---

## `dotnet ef dbcontext info` — 查看 DbContext 信息

```bash
dotnet ef dbcontext info
```

输出示例：

```
Provider: Microsoft.EntityFrameworkCore.Sqlite
Database: app.db
Context: EfDemo.Data.AppDbContext
ConnectionString: Data Source=app.db
```

配合 `--json` 获取结构化输出，方便脚本解析：

```bash
dotnet ef dbcontext info --json
```

---

## `dotnet ef dbcontext scaffold` — 反向工程

从**现有数据库**生成 C# 模型和 `DbContext`。

### 基本用法

```bash
dotnet ef dbcontext scaffold "Data Source=existing.db" Microsoft.EntityFrameworkCore.Sqlite
```

参数顺序：`<连接字符串> <provider>`

### 常用选项

```bash
dotnet ef dbcontext scaffold \
    "Data Source=existing.db" \
    Microsoft.EntityFrameworkCore.Sqlite \
    --output-dir Models \
    --context-dir Data \
    --context MyAppDbContext \
    --namespace EfDemo.Models \
    --context-namespace EfDemo.Data \
    --force \
    --no-onconfiguring \
    --table Authors \
    --table Books
```

| 选项 | 说明 |
|------|------|
| `--output-dir` | 实体类输出目录 |
| `--context-dir` | DbContext 类输出目录 |
| `--context` | DbContext 类名（默认数据库名+Context） |
| `--namespace` | 实体类的命名空间 |
| `--context-namespace` | DbContext 的命名空间 |
| `--force` | 覆盖已有文件 |
| `--no-onconfiguring` | 不在 DbContext 中生成 `OnConfiguring`（连接字符串改由外部注入） |
| `--table` | 只生成指定表（可重复使用） |
| `--no-pluralize` | 禁用复数化（表名 `Authors` → 类名 `Author`，而非复数化的 `Authors`） |
| `--use-database-names` | 表名和列名保持数据库原始命名，不做 C# 风格转换 |

### 生成结果示例

假设数据库有表 `Authors (Id, Name, Bio)` 和 `Books (Id, Title, Year, AuthorId)`：

生成的 `Author.cs`：

```csharp
public partial class Author
{
    public long Id { get; set; }
    public string Name { get; set; } = null!;
    public string? Bio { get; set; }
    public virtual ICollection<Book> Books { get; set; } = new List<Book>();
}
```

生成的 `AppDbContext.cs`：

```csharp
public partial class AppDbContext : DbContext
{
    public virtual DbSet<Author> Authors { get; set; }
    public virtual DbSet<Book> Books { get; set; }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Book>(entity =>
        {
            entity.HasOne(d => d.Author)
                .WithMany(p => p.Books)
                .HasForeignKey(d => d.AuthorId);
        });
    }
}
```

> [!note] `partial` 类
> scaffold 生成的类都标记为 `partial`，你可以在同名 `partial` 文件中添加自定义逻辑，重新生成时不会被覆盖。

---

## 完整可运行示例

以下从头到尾构建一个 SQLite 控制台应用，使用 `dotnet ef` 管理迁移。

### 步骤 1：创建项目并添加包

```bash
mkdir EfDemo && cd EfDemo
dotnet new console
dotnet add package Microsoft.EntityFrameworkCore.Sqlite
dotnet add package Microsoft.EntityFrameworkCore.Design
```

### 步骤 2：编写模型

创建 `Models/` 目录，添加以下文件：

`Models/Author.cs`：

```csharp
namespace EfDemo.Models;

public class Author
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public string? Bio { get; set; }
    public List<Book> Books { get; set; } = new();
}
```

`Models/Book.cs`：

```csharp
namespace EfDemo.Models;

public class Book
{
    public int Id { get; set; }
    public string Title { get; set; } = string.Empty;
    public int Year { get; set; }
    public decimal Price { get; set; }

    public int AuthorId { get; set; }
    public Author Author { get; set; } = null!;
}
```

### 步骤 3：编写 DbContext 与工厂

`Data/AppDbContext.cs`：

```csharp
using Microsoft.EntityFrameworkCore;
using EfDemo.Models;

namespace EfDemo.Data;

public class AppDbContext : DbContext
{
    public DbSet<Author> Authors => Set<Author>();
    public DbSet<Book> Books => Set<Book>();

    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }
}
```

`Data/AppDbContextFactory.cs`：

```csharp
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace EfDemo.Data;

public class AppDbContextFactory : IDesignTimeDbContextFactory<AppDbContext>
{
    public AppDbContext CreateDbContext(string[] args)
    {
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseSqlite("Data Source=app.db")
            .Options;

        return new AppDbContext(options);
    }
}
```

### 步骤 4：创建初始迁移

```bash
dotnet ef migrations add InitialCreate --output-dir Data/Migrations
```

预期输出：

```
Build succeeded.
Done. To undo this action, use 'ef migrations remove'
```

检查生成的文件：

```
Data/Migrations/
├── 20260610XXXXXX_InitialCreate.cs
├── 20260610XXXXXX_InitialCreate.Designer.cs
└── AppDbContextModelSnapshot.cs
```

### 步骤 5：应用到数据库

```bash
dotnet ef database update
```

预期输出：

```
Build succeeded.
Applying migration '20260610XXXXXX_InitialCreate'.
Done.
```

此时项目根目录出现 `app.db` —— SQLite 数据库文件。

### 步骤 6：修改模型并追加迁移

给 `Book` 添加属性：

```csharp
// Models/Book.cs — 添加
public string? ISBN { get; set; }
public Genre Genre { get; set; }
```

添加枚举：

```csharp
// Models/Genre.cs
namespace EfDemo.Models;

public enum Genre
{
    Fiction,
    NonFiction,
    Science,
    Technology,
    Biography
}
```

更新 `AppDbContext` 注册枚举为字符串存储：

```csharp
// Data/AppDbContext.cs — 在类内添加
protected override void OnModelCreating(ModelBuilder modelBuilder)
{
    modelBuilder.Entity<Book>()
        .Property(b => b.Genre)
        .HasConversion<string>();
}
```

追加迁移：

```bash
dotnet ef migrations add AddBookDetails --output-dir Data/Migrations
```

应用：

```bash
dotnet ef database update
```

### 步骤 7：编写种子数据与查询

`Program.cs`：

```csharp
using EfDemo.Data;
using EfDemo.Models;
using Microsoft.EntityFrameworkCore;

// 创建 DbContext
var options = new DbContextOptionsBuilder<AppDbContext>()
    .UseSqlite("Data Source=app.db")
    .Options;

using var db = new AppDbContext(options);

// 确保数据库已创建
db.Database.EnsureCreated();

// 种子数据（幂等检查）
if (!db.Authors.Any())
{
    var author = new Author
    {
        Name = "Robert C. Martin",
        Bio = "Software engineer and author",
        Books = new List<Book>
        {
            new() { Title = "Clean Code", Year = 2008, Price = 39.99m, Genre = Genre.Technology },
            new() { Title = "Clean Architecture", Year = 2017, Price = 34.99m, Genre = Genre.Technology }
        }
    };
    db.Authors.Add(author);
    db.SaveChanges();
    Console.WriteLine("Seed data inserted.");
}

// 查询：列出所有书籍及其作者
var books = db.Books.Include(b => b.Author).ToList();
foreach (var book in books)
{
    Console.WriteLine($"{book.Title} by {book.Author.Name} ({book.Year}) — ${book.Price} [{book.Genre}]");
}

// 查询：按作者分组计数
var authorCounts = db.Authors
    .Select(a => new { a.Name, BookCount = a.Books.Count })
    .ToList();

Console.WriteLine("\nAuthor book counts:");
foreach (var ac in authorCounts)
    Console.WriteLine($"  {ac.Name}: {ac.BookCount} book(s)");
```

运行：

```bash
dotnet run
```

预期输出：

```
Seed data inserted.
Clean Code by Robert C. Martin (2008) — $39.99 [Technology]
Clean Architecture by Robert C. Martin (2017) — $34.99 [Technology]

Author book counts:
  Robert C. Martin: 2 book(s)
```

### 步骤 8：生成 SQL 脚本

```bash
dotnet ef migrations script -o migrate.sql
```

检查生成的 `migrate.sql`：

```sql
CREATE TABLE IF NOT EXISTS "__EFMigrationsHistory" ( ... );
CREATE TABLE "Authors" ( ... );
CREATE TABLE "Books" ( ... );
INSERT INTO "__EFMigrationsHistory" ...;
ALTER TABLE "Books" ADD "ISBN" TEXT NULL;
ALTER TABLE "Books" ADD "Genre" TEXT NOT NULL DEFAULT 'Fiction';
```

---

## 练习

### 练习 1：添加新实体并迁移

为上面的 `EfDemo` 项目添加 `Publisher` 实体（属性：`Id`、`Name`、`Country`），与 `Book` 建立一对多关系。完成以下步骤：

1. 创建 `Models/Publisher.cs`
2. 更新 `Book` 添加 `PublisherId` 导航属性
3. 更新 `AppDbContext` 添加 `DbSet<Publisher>`
4. 创建并应用迁移
5. 更新 `Program.cs` 添加 Publisher 种子数据
6. 运行并验证

> [!tip] 提示
> 一对多关系：`Publisher` 有一个 `List<Book>`，`Book` 有一个 `PublisherId` 和 `Publisher` 导航属性。

### 练习 2：反向工程现有数据库

1. 使用 SQLite 命令行或工具创建一个 `legacy.db`，内含表 `Employees(Id INTEGER PRIMARY KEY, Name TEXT, Department TEXT, Salary REAL)`
2. 在新项目中通过 `dotnet ef dbcontext scaffold` 生成模型和 DbContext
3. 编写查询列出 Department 为 "Engineering" 的员工
4. 修改模型（如添加 `HireDate` 列），使用 migration 更新 schema

### 练习 3：脚本驱动的迁移部署

1. 从练习 1 的最终状态，生成幂等 SQL 脚本
2. 删除 `app.db`（模拟全新部署环境）
3. 使用 `sqlite3` 命令行工具执行脚本重建数据库
4. 运行应用验证数据完整性

---

## 扩展阅读

- [EF Core 官方文档 — Migrations Overview](https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/)
- [EF Core CLI Reference](https://learn.microsoft.com/en-us/ef/core/cli/dotnet)
- [Design-Time DbContext Creation](https://learn.microsoft.com/en-us/ef/core/cli/dbcontext-creation)
- [SQLite EF Core Provider](https://learn.microsoft.com/en-us/ef/core/providers/sqlite/)
- [EF Core Power Tools (GUI 可视化工具)](https://github.com/ErikEJ/EFCorePowerTools)
- [.NET Data Community Standups — EF Core](https://www.youtube.com/playlist?list=PLdo4fOcmZ0oX7zYgVc6SvFPN_YrBnRcEM)

---

## 常见陷阱

### `dotnet-ef` 未安装

**症状**：

```
Could not execute because the specified command or file was not found.
```

**解决**：

```bash
dotnet tool install --global dotnet-ef
```

或检查 `~/.dotnet/tools` 是否在 `PATH` 中。

### 错误的启动项目

**症状**：

```
Unable to create an object of type 'AppDbContext'.
```

**原因**：`dotnet ef` 默认使用当前目录的项目作为启动项目。如果 DbContext 在类库中而启动项目是控制台应用，需要显式指定：

```bash
dotnet ef migrations add Init --startup-project ../MyApp --project ../MyData
```

- `--project`：包含 DbContext 的项目
- `--startup-project`：包含 `Program.cs` 及依赖注入配置的项目

### 缺少 `IDesignTimeDbContextFactory<T>`

**症状**：

```
Unable to create an object of type 'AppDbContext'.
No parameterless constructor was found.
```

**解决**：实现 `IDesignTimeDbContextFactory<T>` 或在 `Program.cs` 中使用 `CreateHostBuilder` 模式。

> [!tip] 工厂实现模板
> 本教程 [[#设计时 DbContext 工厂]] 部分提供了完整的工厂实现，按需复制修改即可。

### 迁移冲突

**症状**：

```
The migration 'XXX' was not found.
The model snapshot has diverged from the migrations.
```

**原因**：多人同时在分支上创建迁移，合并后时间戳重叠或模型快照不一致。

**解决步骤**：

```bash
# 1. 回滚到合并前的最后一个公共迁移
dotnet ef database update LastCommonMigration

# 2. 删除冲突的迁移文件
dotnet ef migrations remove  # 重复直到干净

# 3. 重新生成合并后的迁移
dotnet ef migrations add MergeMigration
```

或者，在合并前团队约定：避免并行创建迁移；或者使用 `--output-dir` 将迁移隔离到不同目录。

### 迁移包含危险操作

**症状**：生成的 `Up()` 方法包含 `DropColumn`、`DropTable`、`AlterColumn`（类型变更）等可能丢失数据的操作。

**解决**：始终审查生成的迁移代码后再应用。对于生产数据库：

```bash
# 生成 SQL 预览（不应用）
dotnet ef migrations script LastAppliedMigration -o review.sql

# 人工审核 review.sql 后再决定
```

### SQLite 不支持的迁移操作

SQLite 对 schema 变更的支持有限。以下操作在 SQLite 迁移中会失败：

- `ALTER COLUMN`（修改列类型）
- `DROP COLUMN`（.NET 6 之前的 EF Core + SQLite）
- `DROP CONSTRAINT`

**解决**：对于 SQLite，优先使用「重建表」策略：

```csharp
// EF Core 自动处理 — 生成重建表迁移
// 如果手动编写迁移，确保 Up 中包含表重建逻辑
migrationBuilder.DropTable("Temp_Books"); // 先删临时表
migrationBuilder.Sql("INSERT INTO Books SELECT * FROM Temp_Books");
```

### 环境变量与连接字符串

**症状**：迁移工厂中硬编码连接字符串，导致不同环境（开发/测试/生产）配置混乱。

**解决**：在工厂中读取环境变量或配置文件：

```csharp
public AppDbContext CreateDbContext(string[] args)
{
    var connectionString = Environment.GetEnvironmentVariable("CONNECTION_STRING")
        ?? "Data Source=app.db";

    var options = new DbContextOptionsBuilder<AppDbContext>()
        .UseSqlite(connectionString)
        .Options;

    return new AppDbContext(options);
}
```

生产部署时应使用 `dotnet ef migrations script` 生成 SQL，而非直接运行 `database update`。
