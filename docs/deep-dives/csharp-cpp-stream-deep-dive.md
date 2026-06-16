---
title: "C# Stream 与 C++ iostream 深度剖析"
updated: 2026-06-13
tags: [csharp, cpp, stream, iostream, decorator, io, dotnet, stl]
aliases: ["Stream 深度剖析"]
---

# C# Stream 与 C++ iostream 深度剖析

> 深度等级: 第 7 层
> 关联学习计划: [[design-patterns-csharp|设计模式 (C#)]] — 装饰器模式
> 分析日期: 2026-06-13

---

## 第 1 层: 直觉理解

`Stream`（流）是**字节/字符的连续管道**。

- **C# `System.IO.Stream`**：把“能从某处读取字节”或“能向某处写入字节”的任何东西抽象成统一接口。`FileStream` 是文件，`MemoryStream` 是内存，`NetworkStream` 是网络，`CryptoStream` 是加密层。
- **C++ `iostream` 体系**：`std::istream` / `std::ostream` 负责**格式化/非格式化 I/O**，而真正的字节搬运由 `std::streambuf` 完成。`std::cin`、`std::cout`、文件流、字符串流最终都落到一个 `streambuf` 上。

> 类比：把 I/O 想象成快递分拣流水线。
> - **C# Stream**：每一件包裹都是 `byte[]`，整条流水线由一节一节可替换的传送带组成（文件带、内存带、加密带、压缩带），每节都遵守同一个接口，可以任意拼接。
> - **C++ iostream**：流水线分为两层——`streambuf` 是仓库里的叉车（真正搬运字节），`iostream` 是贴标签、称重、扫码的工位（格式化、操作符重载）。

---

## 第 2 层: 使用场景

### 什么时候用

| 场景 | C# 推荐类型 | C++ 推荐类型 |
|------|------------|-------------|
| 读写磁盘文件 | `FileStream` | `std::fstream` / `std::ifstream` / `std::ofstream` |
| 内存中临时缓冲 | `MemoryStream` | `std::stringstream` / `std::istringstream` / `std::ostringstream` |
| 网络套接字 | `NetworkStream` | 自定义 `std::streambuf` 或 Boost.Asio |
| 压缩/加密数据 | `GZipStream`、`CryptoStream`、`DeflateStream` | 自定义 `std::streambuf` 或 Boost.Iostreams |
| 减少系统调用次数 | `BufferedStream` | `std::ios::sync_with_stdio(false)` / 自定义缓冲 `streambuf` |
| 文本行读写 | `StreamReader` / `StreamWriter` | `std::getline`、`operator<<`、`operator>>` |

### 什么时候不用

- **需要随机访问二进制结构体字段**：`Stream` 的 `Position`/`Seek` 对网络流、加密流无效；C++ `fstream` 虽可 `seekp`/`seekg`，但对所有 `streambuf` 不通用。直接 `mmap` 或内存指针更高效。
- **极高性能零拷贝**：每多一层 `Stream` 装饰器就多一次 `Buffer.BlockCopy` 或加密变换。需要 `Span<T>`、`Memory<T>`、`ReadOnlySequence<T>` 或 C++ `std::span`。
- **需要保留被包装对象的精确类型信息**：装饰器把具体类型“抹平”为 `Stream`/`istream`，如需调用 `FileStream` 的特定 API，只能显式持有引用。

### 决策流程

```text
是否需要跨来源统一处理字节 I/O?
    ├─ 否 → 使用具体 API（File.ReadAllBytes、Win32 ReadFile、POSIX read）
    └─ 是 → 需要装饰/组合能力吗?
            ├─ 是 → C# 用 Stream 装饰链；C++ 用 streambuf/iostream 体系或 Boost.Iostreams
            └─ 否 → C# 用具体 Stream；C++ 用具体 fstream/stringstream
```

---

## 第 3 层: API 层

### C# `System.IO.Stream` 抽象接口

```csharp
public abstract class Stream : MarshalByRefObject, IDisposable, IAsyncDisposable
{
    public abstract bool CanRead { get; }
    public abstract bool CanWrite { get; }
    public abstract bool CanSeek { get; }
    public virtual  bool CanTimeout => false;

    public abstract long Length { get; }
    public abstract long Position { get; set; }

    public abstract int  Read(byte[] buffer, int offset, int count);
    public virtual  int  Read(Span<byte> buffer);
    public virtual  int  ReadByte();

    public abstract void Write(byte[] buffer, int offset, int count);
    public virtual  void Write(ReadOnlySpan<byte> buffer);
    public virtual  void WriteByte(byte value);

    public abstract long Seek(long offset, SeekOrigin origin);
    public abstract void SetLength(long value);
    public abstract void Flush();

    public virtual void CopyTo(Stream destination, int bufferSize);
    public virtual Task CopyToAsync(Stream destination, int bufferSize, CancellationToken cancellationToken);

    public virtual ValueTask DisposeAsync();
    protected virtual void Dispose(bool disposing);
}
```

关键派生类：

| 类型 | 角色 | 典型组合 |
|------|------|----------|
| `FileStream` | ConcreteComponent | `new FileStream(...)` |
| `MemoryStream` | ConcreteComponent | 内存缓冲 |
| `BufferedStream` | ConcreteDecorator | `new BufferedStream(fs)` |
| `CryptoStream` | ConcreteDecorator | `new CryptoStream(fs, aes.CreateEncryptor(), CryptoStreamMode.Write)` |
| `GZipStream` / `DeflateStream` | ConcreteDecorator | `new GZipStream(fs, CompressionMode.Compress)` |
| `StreamReader` / `StreamWriter` | 适配器（文本→字节） | `new StreamReader(fs, Encoding.UTF8)` |

### C++ `iostream` 体系

```cpp
// 高层：格式化/非格式化接口
class std::ios_base;
class std::basic_ios<CharT, Traits>;
class std::basic_istream<CharT, Traits>;   // >>
class std::basic_ostream<CharT, Traits>;   // <<
class std::basic_iostream<CharT, Traits>;  // 同时继承 istream/ostream

// 低层：字节/字符缓冲与设备抽象
class std::basic_streambuf<CharT, Traits>;

// 具体类
typedef std::basic_istream<char>      std::istream;
typedef std::basic_ostream<char>      std::ostream;
typedef std::basic_iostream<char>     std::iostream;
typedef std::basic_filebuf<char>      std::filebuf;
typedef std::basic_stringbuf<char>    std::stringbuf;
typedef std::basic_fstream<char>      std::fstream;
typedef std::basic_stringstream<char> std::stringstream;
```

`basic_streambuf` 核心公共 API：

| 函数 | 作用 |
|------|------|
| `sgetc()` | 查看当前字符但不移动读指针 |
| `sbumpc()` | 读取并移动读指针 |
| `snextc()` | 移动读指针并查看下一个字符 |
| `sgetn(s, n)` | 批量读取 `n` 个字符 |
| `sputc(c)` | 写入单个字符 |
| `sputn(s, n)` | 批量写入 `n` 个字符 |
| `sungetc()` / `sputbackc(c)` | 回退字符 |
| `pubseekoff` / `pubseekpos` | 定位 |
| `pubsetbuf` | 设置缓冲区 |
| `pubsync()` | 刷新缓冲区到外部设备 |

> [!tip] 重点
> C# 的 `Stream` 把“读写字节数组”作为一等公民；C++ 的 `iostream` 把“单个字符操作”作为一等公民，批量读写通过 `streambuf` 的 `sgetn`/`sputn` 完成。

---

## 第 4 层: 行为契约

### C# Stream 契约

| 能力 | 查询 | 违反后果 |
|------|------|----------|
| 可读 | `CanRead == true` | `Read` 抛 `NotSupportedException` |
| 可写 | `CanWrite == true` | `Write` 抛 `NotSupportedException` |
| 可定位 | `CanSeek == true` | `Seek` / `Position` / `Length` 抛 `NotSupportedException` |
| 可超时 | `CanTimeout == true` | 访问 `ReadTimeout`/`WriteTimeout` 抛 `InvalidOperationException` |

- **`Read` 不一定填满缓冲区**：返回 `0` 表示流结束（EOF），否则返回实际读取字节数，可能小于 `count`。
- **`Flush` 语义**：把已写入但未提交到底层设备的数据推出去；对 `CryptoStream` 必须调用 `FlushFinalBlock()` 才能输出填充块。
- **Dispose 传播**：默认 `BufferedStream`、`CryptoStream` 会在 Dispose 时调用内部流的 Dispose，可用 `leaveOpen` 参数关闭。
- **线程安全**：.NET `Stream` 不保证线程安全；并发读写需外部加锁或依赖具体实现（如 `FileStream` 在 .NET 6+ 的异步并发行为）。

### C++ iostream / streambuf 契约

- **状态位** (`std::ios_base::iostate`)：`goodbit`、`eofbit`、`failbit`、`badbit`。
  - `operator>>` 失败会设置 `failbit`，不会抛异常（除非 `exceptions()` 开启）。
  - 到达 EOF 设置 `eofbit`，不一定同时设置 `failbit`。
- **格式化 vs 非格式化**：
  - 格式化：`cin >> x`、`cout << x`，受 `locale`、`width`、`precision` 影响。
  - 非格式化：`istream::read`、`ostream::write`、`streambuf::sgetn`/`sputn`，直接搬运字节。
- **缓冲策略**：`streambuf` 默认有内部缓冲区；`std::unitbuf`、`std::flush`、`std::endl` 会触发 `sync()`。
- **定位分离**：`seekg`（get 区）和 `seekp`（put 区）在文件流中通常共享同一位置，但在 `stringbuf` 等实现中可以独立。

---

## 第 5 层: 实现原理

### C# Stream：装饰器模式 + 统一的字节数组接口

```text
+---------------------------------------------------------+
|  Client                                                |
|  bs.Write(data)                                        |
+---------------------------------------------------------+
          │
          ▼
+---------------------------------------------------------+
|  BufferedStream (ConcreteDecorator)                    |
|  维护 _buffer[_bufferSize], _readPos, _readLen, _writePos |
|  小写先攒进 buffer，大写直接透传底层                      |
+---------------------------------------------------------+
          │
          ▼
+---------------------------------------------------------+
|  CryptoStream (ConcreteDecorator)                      |
|  维护 _inputBuffer[_inputBlockSize], _outputBuffer[_outputBlockSize] |
|  凑够块 → ICryptoTransform.TransformBlock → 写入底层      |
+---------------------------------------------------------+
          │
          ▼
+---------------------------------------------------------+
|  FileStream (ConcreteComponent)                        |
|  调用 OS API（Windows CreateFile/ReadFile/WriteFile）    |
+---------------------------------------------------------+
```

### C++ iostream：双层职责分离

```text
+----------------------------------------------------+
|  std::ostream                                      |
|  operator<< 格式化 → 调用 rdbuf()->sputc/sputn     |
+----------------------------------------------------+
          │
          ▼
+----------------------------------------------------+
|  std::streambuf                                    |
|  get 区：eback() ≤ gptr() < egptr()                |
|  put 区：pbase() ≤ pptr() < epptr()                |
|  缓冲区耗尽 → 调用虚函数 underflow() / overflow()  |
+----------------------------------------------------+
          │
          ▼
+----------------------------------------------------+
|  std::filebuf / std::stringbuf                     |
|  真正与文件/字符串交互                              |
+----------------------------------------------------+
```

关键算法：

- **读取**：`sbumpc()` 检查 `gptr() < egptr()`，有直接返回；否则调用虚函数 `uflow()`（默认 `underflow()` + 移动指针）。
- **写入**：`sputc(c)` 检查 `pptr() < epptr()`，有空位直接写；否则调用虚函数 `overflow(c)`。
- **批量读取 `xsgetn`**：先拷贝缓冲区剩余，再调用 `underflow()` 补充，循环直到 `n` 个字符或 EOF。
- **批量写入 `xsputn`**：先填满当前 put 区，触发 `overflow()`  flush，再处理剩余。

---

## 第 6 层: 源码分析

### .NET `Stream` 基类

源码来自 `dotnet/runtime` main 分支（`src/libraries/System.Private.CoreLib/src/System/IO/Stream.cs`）。

抽象能力声明：

```csharp
public abstract partial class Stream : MarshalByRefObject, IDisposable, IAsyncDisposable
{
    public static readonly Stream Null = new NullStream();

    public abstract bool CanRead { get; }
    public abstract bool CanWrite { get; }
    public abstract bool CanSeek { get; }
    public virtual  bool CanTimeout => false;

    public abstract long Length { get; }
    public abstract long Position { get; set; }

    public virtual int ReadTimeout
    {
        get => throw new InvalidOperationException(SR.InvalidOperation_TimeoutsNotSupported);
        set => throw new InvalidOperationException(SR.InvalidOperation_TimeoutsNotSupported);
    }

    public virtual int WriteTimeout
    {
        get => throw new InvalidOperationException(SR.InvalidOperation_TimeoutsNotSupported);
        set => throw new InvalidOperationException(SR.InvalidOperation_TimeoutsNotSupported);
    }

    // ...
}
```

`CopyTo` 默认实现使用 `ArrayPool<byte>.Shared.Rent`，避免大对象堆（LOH）分配：

```csharp
public virtual void CopyTo(Stream destination, int bufferSize)
{
    ValidateCopyToArguments(destination, bufferSize);
    if (!CanRead)
    {
        if (CanWrite)
            ThrowHelper.ThrowNotSupportedException_UnreadableStream();
        ThrowHelper.ThrowObjectDisposedException_StreamClosed(GetType().Name);
    }

    byte[] buffer = ArrayPool<byte>.Shared.Rent(bufferSize);
    try
    {
        int bytesRead;
        while ((bytesRead = Read(buffer, 0, buffer.Length)) != 0)
        {
            destination.Write(buffer, 0, bytesRead);
        }
    }
    finally
    {
        ArrayPool<byte>.Shared.Return(buffer);
    }
}
```

### `BufferedStream` 的缓冲策略

源码同样来自 `System.Private.CoreLib/src/System/IO/BufferedStream.cs`。

缓冲不变式（class invariant）：

```csharp
/// Class Invariants:
/// The class has one buffer, shared for reading & writing.
/// It can only be used for one or the other at any point in time - not both.
/// The following should be true:
/// <![CDATA[
///   * 0 <= _readPos <= _readLen < _bufferSize
///   * 0 <= _writePos < _bufferSize
///   * _readPos == _readLen && _readPos > 0 implies the read buffer is valid, but we're at the end of the buffer.
///   * _readPos == _readLen == 0 means the read buffer contains garbage.
///   * Either _writePos can be greater than 0, or _readLen & _readPos can be greater than zero,
///     but neither can be greater than 0 at the same time.
///  ]]>
```

读路径：优先从内部 buffer 拷贝，不足时再去底层读，且一次只读一个 buffer 大小：

```csharp
public override int Read(byte[] buffer, int offset, int count)
{
    ValidateBufferArguments(buffer, offset, count);
    EnsureNotClosed();
    EnsureCanRead();

    int bytesFromBuffer = ReadFromBuffer(buffer, offset, count);

    if (bytesFromBuffer == count)
        return bytesFromBuffer;

    int alreadySatisfied = bytesFromBuffer;
    if (bytesFromBuffer > 0)
    {
        count -= bytesFromBuffer;
        offset += bytesFromBuffer;
    }

    _readPos = _readLen = 0;
    if (_writePos > 0)
        FlushWrite();

    // 请求大于 buffer 时直接透传，避免无意义的二次拷贝
    if (count >= _bufferSize)
    {
        return _stream.Read(buffer, offset, count) + alreadySatisfied;
    }

    EnsureBufferAllocated();
    _readLen = _stream.Read(_buffer, 0, _bufferSize);

    bytesFromBuffer = ReadFromBuffer(buffer, offset, count);
    return bytesFromBuffer + alreadySatisfied;
}
```

写路径：小写入先进入 `_buffer`，满后 `FlushWrite()` 一次性写入底层：

```csharp
private void FlushWrite()
{
    Debug.Assert(_stream != null);
    Debug.Assert(_readPos == 0 && _readLen == 0);
    Debug.Assert(_buffer != null && _bufferSize >= _writePos);

    _stream.Write(_buffer, 0, _writePos);
    _writePos = 0;
    _stream.Flush();
}
```

### `CryptoStream` 的分块变换

源码来自 `System.Security.Cryptography/src/System/Security/Cryptography/CryptoStream.cs`。

构造时根据 `CryptoStreamMode` 决定可读或可写，并分配输入/输出块缓冲区：

```csharp
public CryptoStream(Stream stream, ICryptoTransform transform, CryptoStreamMode mode, bool leaveOpen)
{
    ArgumentNullException.ThrowIfNull(transform);

    _stream = stream;
    _transform = transform;
    _leaveOpen = leaveOpen;

    switch (mode)
    {
        case CryptoStreamMode.Read:
            if (!_stream.CanRead)
                throw new ArgumentException(SR.Argument_StreamNotReadable, nameof(stream));
            _canRead = true;
            break;
        case CryptoStreamMode.Write:
            if (!_stream.CanWrite)
                throw new ArgumentException(SR.Argument_StreamNotWritable, nameof(stream));
            _canWrite = true;
            break;
        default:
            throw new ArgumentException(SR.Argument_InvalidValue, nameof(mode));
    }

    _inputBlockSize = _transform.InputBlockSize;
    _inputBuffer = new byte[_inputBlockSize];
    _outputBlockSize = _transform.OutputBlockSize;
    _outputBuffer = new byte[_outputBlockSize];
}
```

读路径核心逻辑：先消耗 `_outputBuffer` 中已解密的字节；不够则从底层读并调用 `TransformBlock`；读到 EOF 时调用 `TransformFinalBlock`：

```csharp
private async ValueTask<int> ReadAsyncCore(Memory<byte> buffer, CancellationToken cancellationToken, bool useAsync)
{
    while (true)
    {
        if (_outputBufferIndex != 0)
        {
            int bytesToCopy = Math.Min(_outputBufferIndex, buffer.Length);
            if (bytesToCopy != 0)
            {
                new ReadOnlySpan<byte>(_outputBuffer, 0, bytesToCopy).CopyTo(buffer.Span);
                _outputBufferIndex -= bytesToCopy;
                _outputBuffer.AsSpan(bytesToCopy).CopyTo(_outputBuffer);
                CryptographicOperations.ZeroMemory(_outputBuffer.AsSpan(_outputBufferIndex, bytesToCopy));
            }
            return bytesToCopy;
        }

        if (_finalBlockTransformed)
        {
            Debug.Assert(_inputBufferIndex == 0);
            return 0;
        }

        // ... 从 _stream 读取至少一个输入块 ...
        if (bytesRead <= 0)
        {
            _outputBuffer = _transform.TransformFinalBlock(_inputBuffer, 0, _inputBufferIndex);
            _outputBufferIndex = _outputBuffer.Length;
            _finalBlockTransformed = true;
        }
        else
        {
            _outputBufferIndex = _transform.TransformBlock(_inputBuffer, 0, _inputBufferIndex, _outputBuffer, 0);
        }

        _inputBufferIndex = 0;
    }
}
```

写路径核心逻辑：先把零散字节凑成 `_inputBlockSize` 的整数倍，再 `TransformBlock` 写入底层，最后通过 `FlushFinalBlock()` 输出填充：

```csharp
public void FlushFinalBlock() =>
    FlushFinalBlockAsync(useAsync: false, default).AsTask().GetAwaiter().GetResult();

private async ValueTask FlushFinalBlockAsync(bool useAsync, CancellationToken cancellationToken)
{
    if (_finalBlockTransformed)
        throw new NotSupportedException(SR.Cryptography_CryptoStream_FlushFinalBlockTwice);
    _finalBlockTransformed = true;

    if (_canWrite)
    {
        byte[] finalBytes = _transform.TransformFinalBlock(_inputBuffer!, 0, _inputBufferIndex);
        if (useAsync)
            await _stream.WriteAsync(new ReadOnlyMemory<byte>(finalBytes), cancellationToken).ConfigureAwait(false);
        else
            _stream.Write(finalBytes, 0, finalBytes.Length);
    }

    // 如果内层还是 CryptoStream，递归 FlushFinalBlock
    if (_stream is CryptoStream innerCryptoStream)
    {
        if (!innerCryptoStream.HasFlushedFinalBlock)
            await innerCryptoStream.FlushFinalBlockAsync(useAsync, cancellationToken).ConfigureAwait(false);
    }
    else
    {
        if (useAsync)
            await _stream.FlushAsync(cancellationToken).ConfigureAwait(false);
        else
            _stream.Flush();
    }

    // 清零明文/密文材料
    if (_inputBuffer != null)
        Array.Clear(_inputBuffer);
    if (_outputBuffer != null)
        Array.Clear(_outputBuffer);
}
```

### C++ `libstdc++` `basic_streambuf`

源码来自 `gcc-mirror/gcc` master 分支（`libstdc++-v3/include/std/streambuf`）。

`basic_streambuf` 维护六个指针，把 get/put 区映射到同一块字符数组：

```cpp
template<typename _CharT, typename _Traits>
class basic_streambuf
{
protected:
    char_type* _M_in_beg;     // Start of get area.      (eback)
    char_type* _M_in_cur;     // Current read area.     (gptr)
    char_type* _M_in_end;     // End of get area.       (egptr)
    char_type* _M_out_beg;    // Start of put area.     (pbase)
    char_type* _M_out_cur;    // Current put area.      (pptr)
    char_type* _M_out_end;    // End of put area.       (epptr)

    locale _M_buf_locale;

public:
    // 单字符读取
    int_type sbumpc()
    {
        int_type __ret;
        if (__builtin_expect(this->gptr() < this->egptr(), true))
        {
            __ret = traits_type::to_int_type(*this->gptr());
            this->gbump(1);
        }
        else
            __ret = this->uflow();
        return __ret;
    }

    // 单字符查看
    int_type sgetc()
    {
        int_type __ret;
        if (__builtin_expect(this->gptr() < this->egptr(), true))
            __ret = traits_type::to_int_type(*this->gptr());
        else
            __ret = this->underflow();
        return __ret;
    }

    // 单字符写入
    int_type sputc(char_type __c)
    {
        int_type __ret;
        if (__builtin_expect(this->pptr() < this->epptr(), true))
        {
            *this->pptr() = __c;
            this->pbump(1);
            __ret = traits_type::to_int_type(__c);
        }
        else
            __ret = this->overflow(traits_type::to_int_type(__c));
        return __ret;
    }

    // 批量写入入口
    streamsize sputn(const char_type* __s, streamsize __n)
    { return this->xsputn(__s, __n); }

    // 批量读取入口
    streamsize sgetn(char_type* __s, streamsize __n)
    { return this->xsgetn(__s, __n); }

protected:
    virtual int_type underflow()
    { return traits_type::eof(); }

    virtual int_type overflow(int_type /* __c */ = traits_type::eof())
    { return traits_type::eof(); }

    virtual streamsize xsgetn(char_type* __s, streamsize __n);
    virtual streamsize xsputn(const char_type* __s, streamsize __n);

    // 定位虚函数
    virtual pos_type seekoff(off_type, ios_base::seekdir,
                             ios_base::openmode = ios_base::in | ios_base::out)
    { return pos_type(off_type(-1)); }

    virtual pos_type seekpos(pos_type,
                             ios_base::openmode = ios_base::in | ios_base::out)
    { return pos_type(off_type(-1)); }

    virtual int sync() { return 0; }
};
```

`filebuf` 会在派生类中重写 `underflow()`（从文件读入 get 区）和 `overflow()`（把 put 区写入文件）。`stringstream` 则把 get/put 区绑定到 `std::string` 的内部字符数组。

---

## 第 7 层: 对比与边界

### C# Stream vs C++ iostream

| 维度 | C# `System.IO.Stream` | C++ `iostream` / `streambuf` |
|------|----------------------|------------------------------|
| 抽象对象 | 任意字节序列 | 字符流 + 格式化 I/O |
| 设计模式 | **装饰器模式**：所有派生类共享 `Stream` 接口，可任意嵌套 | **职责分离**：`streambuf` 负责设备，`iostream` 负责格式 |
| 基本单元 | `byte[]` / `Span<byte>` / `Memory<byte>` | `char_type`（默认 `char`/`wchar_t`） |
| 装饰能力 | 极强：`BufferedStream`、`CryptoStream`、`GZipStream` 都是官方装饰器 | 较弱：标准库没有现成装饰 streambuf；Boost.Iostreams 填补空白 |
| 定位模型 | `SeekOrigin.Begin/Current/End`，`CanSeek` 统一查询 | `seekg` / `seekp` 分离，由 `streambuf` 的 `seekoff`/`seekpos` 实现 |
| 文本处理 | `StreamReader`/`StreamWriter` 是独立适配器 | `>>` / `<<` 直接集成在 `istream`/`ostream` |
| 异步 | 一等支持：`ReadAsync`、`WriteAsync`、`CopyToAsync` | C++20 前无标准异步 iostream；依赖 Asio 等库 |
| 异常策略 | 操作直接抛异常 | 默认设置状态位（`failbit`/`badbit`），可选抛异常 |
| 资源管理 | `IDisposable` / `using` | RAII：流对象析构自动关闭文件 |
| 类型安全 | 运行时检查 `CanRead`/`CanWrite` | 编译期通过 `istream`/`ostream`/`iostream` 类型约束 |

### 性能特征

| 操作 | C# Stream | C++ iostream |
|------|-----------|--------------|
| 单字节读写 | 慢（每次虚方法调用 + 可能同步） | 慢（每次虚方法调用） |
| 批量读写 | 快（`Span`/`Memory` 减少分配） | 快（`streambuf::sgetn`/`sputn`） |
| 装饰层开销 | 每层一次 `Read`/`Write` 委托 + 可能缓冲拷贝 | 自定义 filter streambuf 可做到零拷贝传递 |
| 零拷贝 | `CopyTo` 仍需 `ArrayPool` 缓冲；真正零拷贝用 `MemoryMappedFile` 或管道 | 可实现自定义 `streambuf` 直接操作外部缓冲区 |
| 大文件 | `FileStream` 支持 `FileOptions.SequentialScan`、预读 | `std::ios::binary` + 自定义 buffer 大小 |

### 设计取舍

- **C# 的选择**：用一个扁平的 `Stream` 接口统一所有字节 I/O，并通过装饰器动态组合。优点是生态一致；缺点是单字节 API 性能一般，且装饰链过深时堆栈调试困难。
- **C++ 的选择**：把“格式化工位”和“搬运叉车”拆开。`iostream` 提供优雅的运算符重载，`streambuf` 提供可扩展的设备抽象。缺点是标准库缺少现成装饰 streambuf，做压缩/加密过滤需要自己实现或使用 Boost。

---

## 常见面试题

1. `BufferedStream` 在什么情况下会“失效”——即并没有减少系统调用次数？
2. `CryptoStream` 为什么必须在 `Dispose` 前调用 `FlushFinalBlock()`？如果漏掉会怎样？
3. C# 的 `Stream.CopyTo` 默认缓冲区大小是多少？为什么选这个值？
4. C++ 中 `cin >>` 失败时为什么循环不会自动清空错误状态？如何正确处理输入错误？
5. C++ `streambuf` 的 `underflow()` 和 `uflow()` 有什么区别？

## 面试题参考答案

> [!tip]- 题目 1 参考答案
> `BufferedStream` 在以下情况会失效或收益很低：
> - 每次读写都大于等于 `_bufferSize`，`Read`/`Write` 直接透传底层，不经过内部 buffer。
> - 读写交替频繁，每次写之前都要 `FlushRead()`（底层可定位）或抛异常（底层不可定位）。
> - 多线程并发访问，`BufferedStream` 本身不是线程安全，外部加锁会让小读写也串行化。
> 源码中 `if (count >= _bufferSize) return _stream.Read(buffer, offset, count);` 就是这条短路路径。

> [!tip]- 题目 2 参考答案
> 分组加密（如 AES-CBC）要求输入长度是块大小的整数倍。写入数据不足一块时，`CryptoStream` 把它们暂存在 `_inputBuffer` 里，不会立即写出。
> `FlushFinalBlock()` 调用 `ICryptoTransform.TransformFinalBlock()` 生成最后一个块（含 PKCS 填充），并写入底层流。如果漏掉：
> - 解密方会拿到不完整数据，最后一块缺失，解密失败或抛 `CryptographicException`。
> - 加密方 `MemoryStream` 里的密文也会缺少尾部。

> [!tip]- 题目 3 参考答案
> 默认缓冲区大小是 `81920` 字节（80 KiB）。
> 这是“小于 LOH 阈值 85 KiB 的最大 4096 倍数”。虽然现代 .NET 的 `ArrayPool` 会把它向上取整到 131072（128 KiB，进入 LOH），但因为 buffer 短命且会被池化复用，性能收益仍然明显。源码注释明确说明了这段历史。

> [!tip]- 题目 4 参考答案
> `operator>>` 失败会设置 `failbit`，但不会自动清空。下一次 `cin >> x` 会立即失败，因为流状态仍是错误的。
> 正确处理：
> ```cpp
> if (!(cin >> x)) {
>     cin.clear();                 // 清除错误位
>     cin.ignore(numeric_limits<streamsize>::max(), '\n'); // 丢弃错误输入
> }
> ```
> 注意：直接用 `while (cin >> x)` 时，如果输入结束会设置 `eofbit`，循环自然结束，这是正常用法；但遇到类型不匹配时需要手动恢复状态。

> [!tip]- 题目 5 参考答案
> - `underflow()`：在 get 区耗尽时被调用，负责从外部设备补充数据到 get 区，并返回第一个可用字符，但不移动读指针。
> - `uflow()`：默认实现是 `underflow()` + `gbump(1)`，即补充数据并消费掉第一个字符。
> `sgetc()` 在缓冲区非空时直接返回 `*gptr()`；为空时调用 `underflow()`。`sbumpc()` 在缓冲区非空时返回并 `gbump(1)`；为空时调用 `uflow()`。

---

## 延伸主题

- [[12-decorator|装饰器模式]] — 本深度探索的上下文起点
- [[13-proxy|代理模式]] — 与装饰器结构相似但意图不同
- C# `Span<T>` / `Memory<T>` / `ReadOnlySequence<T>` — 比 `Stream` 更底层的零拷贝抽象
- C++ Boost.Iostreams — 在 C++ 中实现类似 C# Stream 的装饰器链
- C++ `<=>`（C++23 `std::print`）— 现代 C++ 格式化 I/O 的演进
- .NET `FileStream` 的 `RandomAccess` / `MemoryMappedFile` — 高性能文件 I/O 的替代路径
