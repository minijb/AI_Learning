# 音频引擎基础

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 5h
> 前置知识: 无

---

## 1. 概念讲解

### 1.1 数字音频基础

在深入游戏音频引擎之前，必须先理解声音是如何在计算机中表示的。

#### 模拟信号与数字信号

声音在物理世界中是连续的声波——空气分子的疏密变化。这种连续变化的信号称为**模拟信号**。计算机无法直接存储连续信号，必须将其转换为离散的数字形式，这个过程称为**模数转换（ADC, Analog-to-Digital Conversion）**。反过来，将数字信号还原为模拟声波的过程称为**数模转换（DAC, Digital-to-Analog Conversion）**。

#### 采样率（Sample Rate）

采样率表示每秒钟对模拟信号进行采样的次数，单位是赫兹（Hz）。根据**奈奎斯特-香农采样定理**，为了完整还原一个频率为 f 的信号，采样率必须至少为 2f。

人类听觉范围大约是 20Hz ~ 20kHz，因此：

| 采样率 | 可还原的最高频率 | 常见用途 |
|--------|------------------|----------|
| 22050 Hz | 11025 Hz | 语音、低质量音频 |
| 44100 Hz | 22050 Hz | CD 音质标准 |
| 48000 Hz | 24000 Hz | 专业音频、游戏行业标准 |
| 96000 Hz | 48000 Hz | 高分辨率音频、后期制作 |

游戏引擎通常使用 **48000 Hz**，因为它能被大多数常见帧率（30fps、60fps）整除，便于音频与视频同步。

#### 位深度（Bit Depth）

位深度表示每个采样点用多少位来存储振幅信息。位深度决定了**动态范围**（最轻和最响声音之间的差距）和**信噪比**。

| 位深度 | 动态范围 | 常见用途 |
|--------|----------|----------|
| 8-bit | ~48 dB | 复古游戏音效 |
| 16-bit | ~96 dB | CD 音质标准 |
| 24-bit | ~144 dB | 专业录音、游戏引擎内部处理 |
| 32-bit float | ~1500 dB | 游戏引擎混音管线（防止中间计算溢出）|

#### PCM 格式

**PCM（Pulse Code Modulation，脉冲编码调制）** 是最基础的数字音频格式。它直接存储每个采样点的振幅值，不做任何压缩。

一个 PCM 数据流的结构：

```
[采样点0-左声道][采样点0-右声道][采样点1-左声道][采样点1-右声道]...
```

这种交错存储的方式称为 **interleaved PCM**。对于 16-bit 立体声 48000Hz 的音频，每秒的数据量是：

```
48000 采样/秒 × 2 声道 × 2 字节/采样 = 192000 字节/秒 ≈ 187.5 KB/s
```

一分钟的未压缩立体声音频约需 **11 MB** 存储空间。

#### 音频缓冲区与双缓冲机制

音频播放是一个**实时性要求极高**的任务。如果播放器在应该输出下一批采样数据时还没有准备好，就会产生**爆音（pop/click）**或**卡顿**。为了解决这个问题，音频系统使用**缓冲区（Buffer）**来平滑数据流。

**单缓冲的问题：**

如果只有一个缓冲区，CPU 填充缓冲区和声卡读取缓冲区必须严格串行执行。CPU 填充时声卡只能等待，声卡播放时 CPU 也只能等待，效率极低且容易产生间隙。

**双缓冲机制（Double Buffering）：**

```
时间轴 →

缓冲区 A: [播放中]       [填充中]       [播放中]
缓冲区 B: [填充中]       [播放中]       [填充中]
          ↑              ↑              ↑
        声卡读A        声卡读B        声卡读A
        CPU填B         CPU填A         CPU填B
```

双缓冲的核心思想是：
1. 准备两个大小相同的音频缓冲区
2. 声卡播放缓冲区 A 的同时，CPU 填充缓冲区 B
3. 声卡播放完 A 后，切换到播放 B，同时 CPU 填充 A
4. 循环往复，实现无缝播放

缓冲区的大小是一个关键权衡：
- **缓冲区太小**（如 128 采样）：延迟低，但 CPU 填充压力大，容易欠载
- **缓冲区太大**（如 8192 采样）：延迟高（>100ms），游戏中音画不同步

游戏引擎通常选择 **512~2048 采样** 的缓冲区大小，在延迟和稳定性之间取得平衡。

---

### 1.2 音频文件格式

#### WAV（Waveform Audio File Format）

WAV 是微软和 IBM 开发的一种容器格式，基于 RIFF（Resource Interchange File Format）规范。

**结构：**

```
RIFF Chunk
├── "RIFF" 标识符 (4 bytes)
├── 文件大小 (4 bytes)
├── "WAVE" 格式标识 (4 bytes)
│
├── fmt Chunk
│   ├── "fmt " 标识符 (4 bytes)
│   ├── 子块大小 (4 bytes) — 通常为 16 (PCM)
│   ├── 音频格式 (2 bytes) — 1 = PCM
│   ├── 声道数 (2 bytes)
│   ├── 采样率 (4 bytes)
│   ├── 字节率 (4 bytes) — 采样率 × 声道数 × 位深度/8
│   ├── 块对齐 (2 bytes) — 声道数 × 位深度/8
│   └── 位深度 (2 bytes)
│
└── data Chunk
    ├── "data" 标识符 (4 bytes)
    ├── 数据大小 (4 bytes)
    └── PCM 采样数据 (...)
```

WAV 文件通常存储未压缩的 PCM 数据，因此文件较大但解码极快（直接内存映射即可播放）。游戏中的短音效（如枪声、跳跃声）通常使用 WAV 格式。

#### OGG Vorbis

OGG 是一种开源的容器格式，Vorbis 是其常用的有损音频编码格式。

**特点：**
- 有损压缩，压缩率约为 1:10（相比未压缩 PCM）
- 开源、免专利费
- 支持变比特率（VBR）
- 解码复杂度中等

游戏中的背景音乐（BGM）通常使用 OGG 格式，因为它在文件大小和音质之间取得了良好平衡。

#### MP3（MPEG-1 Audio Layer III）

MP3 是最广泛使用的有损音频压缩格式。

**特点：**
- 有损压缩，压缩率约为 1:10 ~ 1:12
- 专利保护期已过（2017年），现在可自由使用
- 解码复杂度中等
- 每帧独立解码，支持随机定位

MP3 的一个特殊限制是：编码时在帧边界填充了静音（gap），导致循环播放时会出现"咔哒"声。OGG 没有这个问题，因此游戏中的循环音乐更推荐使用 OGG。

---

### 1.3 音频播放流程

游戏音频引擎的核心播放流程可以概括为三个阶段：

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  音频资源   │ →  │    解码     │ →  │    混音     │ →  │    输出     │
│ (WAV/OGG)   │    │ (PCM 数据)  │    │ (混合多路)  │    │ (声卡播放)  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

#### 解码（Decoding）

将压缩的音频文件（OGG、MP3）转换为原始的 PCM 数据流。解码可以在以下时机进行：

1. **加载时完全解码**：游戏启动时将整个音频文件解码为 PCM 存入内存。适合短音效。
2. **流式解码**：每次只解码一小段（如 1 秒），播放完再解码下一段。适合长音乐。

#### 混音（Mixing）

游戏中通常同时播放多个声音（背景音乐 + 多个音效）。混音器将这些声音混合成一路或两路（立体声）输出。

混音的基本数学原理是**采样值相加**：

```cpp
// 两个声音混音
mixed_sample = sample_a * volume_a + sample_b * volume_b;
```

需要注意：
- 多个声音相加可能**溢出**（超过 16-bit 的 -32768~32767 范围），因此混音通常在 32-bit float 空间进行，最后再做裁剪（clamping）或压缩（compression）。
- 混音后需要**归一化**（Normalization）或**动态范围压缩**（DRC），防止整体音量过大。

#### 输出（Output）

将混音后的 PCM 数据送入操作系统的音频 API（如 Windows 的 WASAPI、macOS 的 Core Audio、Linux 的 ALSA/PulseAudio），最终到达声卡。

---

### 1.4 软件混音器（Software Mixer）

#### 为什么需要软件混音器？

早期的声卡（如 Sound Blaster）有硬件混音功能，可以同时播放多个音频通道。但现代声卡通常只支持 1~2 路硬件播放通道，因此需要在软件层面实现混音。

#### 多声道混合

软件混音器维护一个**声音实例（Voice）**列表，每个实例代表一个正在播放的声音：

```cpp
struct Voice {
    float* pcm_data;      // PCM 数据指针
    size_t position;      // 当前播放位置（采样点索引）
    size_t length;        // 总长度
    float volume;         // 音量 (0.0 ~ 1.0)
    float pan;            // 声像 (-1.0 = 左, 0.0 = 中, 1.0 = 右)
    bool looping;         // 是否循环
    bool active;          // 是否正在播放
};
```

每帧（每个音频回调周期），混音器遍历所有活跃的声音实例，将它们的采样值混合到输出缓冲区：

```cpp
for (每个输出采样点) {
    float left = 0.0f, right = 0.0f;

    for (每个活跃的声音实例) {
        // 读取当前采样点
        float sample = voice.pcm_data[voice.position];

        // 应用声像
        float left_gain  = voice.volume * (1.0f - voice.pan) * 0.5f;
        float right_gain = voice.volume * (1.0f + voice.pan) * 0.5f;

        left  += sample * left_gain;
        right += sample * right_gain;

        // 推进播放位置
        voice.position++;
        if (voice.position >= voice.length && voice.looping) {
            voice.position = 0;
        }
    }

    // 写入输出缓冲区
    output[left_channel]  = left;
    output[right_channel] = right;
}
```

#### 音量控制与分贝

音频中音量通常用**分贝（dB, decibel）**表示，因为人耳对声音的感知是对数尺度的。

```
dB = 20 × log10(amplitude_ratio)
```

| 振幅比例 | 分贝值 | 感知 |
|----------|--------|------|
| 1.0 | 0 dB | 原始音量 |
| 0.5 | -6 dB | 明显变轻 |
| 0.25 | -12 dB | 更轻 |
| 0.1 | -20 dB | 很轻 |
| 0.0 | -∞ dB | 静音 |

在代码中，通常使用**线性振幅**（0.0 ~ 1.0）进行混音计算，但在用户界面或配置文件中显示分贝值。

---

### 1.5 3D 音频

3D 音频是游戏音频引擎的核心功能之一，它让声音具有空间感——玩家能感知声音从哪个方向传来、距离多远。

#### 距离衰减（Distance Attenuation）

现实中，声音强度随距离平方反比衰减：

```
I ∝ 1 / d²
```

但在游戏中，纯物理衰减往往效果不佳（太远就听不到了）。因此游戏引擎使用**距离模型（Distance Model）**：

**1. 反距离模型（Inverse Distance）：**

```
gain = reference_distance / (reference_distance + rolloff_factor × (distance - reference_distance))
```

**2. 线性距离模型（Linear Distance）：**

```
gain = (1 - rolloff_factor × (distance - reference_distance) / (max_distance - reference_distance))
```

**3. 指数距离模型（Exponential Distance）：**

```
gain = pow(distance / reference_distance, -rolloff_factor)
```

参数说明：
- `reference_distance`：参考距离，在此距离内音量不衰减
- `max_distance`：最大可听距离，超过此距离音量保持最小值
- `rolloff_factor`：衰减系数，越大衰减越快

#### 多普勒效应（Doppler Effect）

当声源和听者相对运动时，听到的声音频率会发生变化：

```
f' = f × (v_sound ± v_listener) / (v_sound ∓ v_source)
```

在游戏中，多普勒效应用于增强速度感：
- 汽车从身边呼啸而过，引擎声从高变低
- 子弹飞过头顶的"嗖嗖"声

实现方式是通过**改变播放速率（pitch shifting）**来模拟频率变化。

#### HRTF（Head-Related Transfer Function）

**HRTF（头部相关传递函数）** 是实现逼真 3D 定位音频的核心技术。

人耳判断声音方向依赖以下线索：

1. **双耳时间差（ITD, Interaural Time Difference）**：声音到达两只耳朵的时间差。对低频声音（< 1.5kHz）最有效。

2. **双耳强度差（ILD, Interaural Level Difference）**：头部遮挡导致的声音强度差。对高频声音最有效。

3. **频谱滤波（Spectral Filtering）**：外耳（耳廓）对不同方向来的声音有不同的滤波效果。

HRTF 就是将这些效应编码为一组滤波器。对于每个水平角度（azimuth）和垂直角度（elevation），都有一套左右耳的滤波器。

```
输入声音 → [左耳 HRTF 滤波器] → 左声道输出
         → [右耳 HRTF 滤波器] → 右声道输出
```

HRTF 的挑战在于每个人的耳廓形状不同，通用的 HRTF 数据集（如 MIT Media Lab 的 KEMAR 假人头测量数据）对某些人效果很好，对另一些人则定位模糊。

---

### 1.6 音频流式加载

对于长音频（如背景音乐、过场动画配音），完全加载到内存会消耗大量 RAM。音频流式加载解决了这个问题。

#### 流式加载原理

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  磁盘文件   │ →   │  解码缓冲区  │ →   │  播放缓冲区  │
│  (OGG/MP3)  │     │  (PCM, 2秒) │     │  (PCM, 0.5秒)│
└─────────────┘     └─────────────┘     └─────────────┘
       ↑                                      ↓
       └──────── 异步读取/解码 ───────────────┘
```

工作流程：
1. 预读取并解码一小段音频（如 2 秒）到解码缓冲区
2. 将其中一部分（如 0.5 秒）复制到播放缓冲区开始播放
3. 在播放的同时，后台线程继续从磁盘读取并解码更多数据
4. 当播放缓冲区即将耗尽时，从解码缓冲区补充数据

#### 双缓冲在流式加载中的应用

流式加载通常使用**环形缓冲区（Ring Buffer）**：

```cpp
template<size_t SIZE>
class RingBuffer {
    float buffer[SIZE];
    size_t write_pos = 0;  // 写入位置
    size_t read_pos = 0;   // 读取位置

public:
    size_t writable() const {
        return (read_pos - write_pos - 1 + SIZE) % SIZE;
    }

    size_t readable() const {
        return (write_pos - read_pos + SIZE) % SIZE;
    }

    void write(const float* data, size_t count) {
        for (size_t i = 0; i < count; i++) {
            buffer[(write_pos + i) % SIZE] = data[i];
        }
        write_pos = (write_pos + count) % SIZE;
    }

    void read(float* out, size_t count) {
        for (size_t i = 0; i < count; i++) {
            out[i] = buffer[(read_pos + i) % SIZE];
        }
        read_pos = (read_pos + count) % SIZE;
    }
};
```

环形缓冲区允许读写并发进行而不需要数据搬移。

---

### 1.7 音频事件系统

游戏中的音频不是孤立播放的，需要与游戏逻辑紧密配合。音频事件系统将音频播放抽象为**事件驱动**的模型。

#### 基本概念

```
游戏事件 ──→ 音频事件系统 ──→ 音频引擎
  │                              │
  │                              │
  ▼                              ▼
"玩家开火"    →   Play("weapon_pistol_fire")   →   加载/播放对应音频
"进入菜单"    →   Play("ui_menu_open")          →   播放 UI 音效
"爆炸发生"    →   Play3D("explosion", pos)      →   在 3D 空间中播放
```

#### 音频事件系统的组成

1. **音频事件（Audio Event）**：一个可播放的音频单元，包含：
   - 音频资源引用（WAV/OGG 文件）
   - 默认音量、音高、循环设置
   - 3D 音频参数（衰减模型、最大距离等）
   - 随机变体（多个音频文件随机选择播放）

2. **音频实例（Audio Instance）**：一个正在播放的声音。一个音频事件可以同时有多个实例（如多个敌人同时开枪）。

3. **音频总线（Audio Bus）**：用于分组管理音频。常见分组：
   - Master（主总线）
   - SFX（音效总线）
   - Music（音乐总线）
   - Voice（语音总线）
   - UI（UI 音效总线）

   每个总线可以独立控制音量和效果（如给 Music 总线加低通滤波器实现"水下"效果）。

4. **音频参数（Audio Parameter）**：运行时动态控制音频的属性。例如：
   - `RPM`：引擎转速，控制引擎声的音高和音量
   - `Surface`：地面材质，控制脚步声切换
   - `Health`：玩家生命值，控制心跳声的强度

#### 动态混音（Dynamic Mixing）与快照（Snapshot）

**动态混音**根据游戏状态自动调整各总线的音量和效果。例如：
- 当角色进入战斗时，音乐的音量提升，环境音的音量降低
- 当角色对话时，所有其他音频的音量被"闪避（Duck）"降低
- 当角色进入水下区域时，所有音频应用低通滤波器

**快照（Snapshot）**保存混音器完整状态的预设，可以在游戏过程中快速切换。例如：
- "室内"快照：提升混响效果、降低高频响应
- "水下"快照：应用低通滤波和特殊的混响参数
- "战斗"快照：提升音乐音量，降低环境音音量

快照的切换可以平滑过渡（在数百毫秒内渐变），避免突兀的音量跳变。

#### 音频中间件对比

现代游戏项目通常使用**音频中间件（Audio Middleware）**而非直接使用底层音频 API（如 XAudio2、OpenAL、Core Audio）。音频中间件提供了更高层次的抽象，使音频设计师可以独立于程序员工作。

| 特性 | Audiokinetic Wwise | Firelight FMOD | Unity Audio | Unreal Audio |
|------|-------------------|----------------|-------------|--------------|
| 定位 | 行业标准 | 广泛使用的替代方案 | 内置 | 内置 |
| 事件驱动 | 是 (Event-based) | 是 | 基础支持 | 基础支持 |
| 3D 音频 | HRTF/Surround | HRTF/Surround | 基础 3D | 基础 3D |
| 混音系统 | 专业级 | 专业级 | 基础 | 基础 |
| 音频中间件 SDK | 完善 | 完善 | N/A | N/A |
| 实时参数控制 (RTPC) | 完善 | 完善 | 有限 | 有限 |
| 音频动态混音 | 优秀 | 优秀 | 基础 | 基础 |
| 分析工具 | 优秀 | 良好 | 基础 | 基础 |
| 许可模式 | 商业/免费(收入限制) | 商业/免费(收入限制) | 免费 | 免费 |

**Wwise** 是游戏音频行业的标准中间件，被绝大多数 3A 游戏采用。它的核心设计理念是**事件驱动（Event-Driven）**：游戏代码不直接播放音频文件，而是触发**事件（Event）**，事件在 Wwise 的编辑器中定义，包含完整的音频逻辑（播放哪些声音、应用哪些效果、响应哪些参数）。这种解耦使音频设计师可以独立调整游戏的音频体验。

**Wwise 的 RTPC（Real-Time Parameter Control）**系统允许游戏代码实时推送参数值（如玩家血量、车辆速度、环境湿度），这些参数在 Wwise 内部驱动音频属性的动态变化。例如，可以将"玩家血量"参数映射到低通滤波器的截止频率——血量越低，声音越沉闷。

---

### 1.8 音频库简介

#### OpenAL

**OpenAL（Open Audio Library）** 是一个跨平台的 3D 音频 API，设计灵感来自 OpenGL。

**特点：**
- 跨平台（Windows、macOS、Linux、iOS、Android）
- 原生支持 3D 音频（位置、速度、方向、距离衰减）
- 支持 EFX（Effects Extension）扩展，可添加混响、滤波器等效果
- 使用"源（Source）- 缓冲（Buffer）- 听者（Listener）"模型

**缺点：**
- 官方维护已停滞（OpenAL Soft 是活跃的开源实现）
- API 较为底层，需要手动管理缓冲区和解码

#### miniaudio

**miniaudio** 是一个单头文件的 C/C++ 音频库，由 David Reid（mackron）开发。

**特点：**
- 单头文件（miniaudio.h），零依赖
- 跨平台，自动选择最佳后端（WASAPI、Core Audio、ALSA、PulseAudio 等）
- 内置解码器：WAV、MP3、FLAC、Vorbis
- 内置 3D 音频和 HRTF 支持
- 内置混音器和效果管线
- 支持流式加载

**适用场景：** 独立游戏、小型引擎、快速原型开发。

#### SDL_mixer

**SDL_mixer** 是 SDL（Simple DirectMedia Layer）的音频扩展库。

**特点：**
- 基于 SDL，跨平台
- 支持 WAV、OGG、MP3、FLAC、MOD 等格式
- 提供简单的混音功能（最多同时播放 N 个声道）
- 支持音乐播放和音效播放分离

**缺点：**
- 3D 音频支持有限
- 功能相对简单，不适合复杂的音频需求

#### FMOD 和 Wwise（商业方案）

- **FMOD**：广泛用于独立游戏和商业游戏，提供完整的音频中间件解决方案
- **Wwise（Audiokinetic）**：行业标准，提供强大的音频设计工具和运行时引擎

---

### 1.9 音频 DSP 基础

**DSP（Digital Signal Processing，数字信号处理）** 是音频效果的核心。

#### 滤波器（Filter）

滤波器改变音频信号的频谱特性。

**低通滤波器（Low-Pass Filter, LPF）**：
- 允许低频通过，衰减高频
- 用途：模拟"水下"效果、远距离声音、闷住的音效

**高通滤波器（High-Pass Filter, HPF）**：
- 允许高频通过，衰减低频
- 用途：去除低频噪声、模拟电话音质

**带通滤波器（Band-Pass Filter, BPF）**：
- 只允许特定频段通过
- 用途：模拟无线电、对讲机效果

简单的**一阶低通滤波器**实现：

```cpp
// y[n] = α × x[n] + (1 - α) × y[n-1]
// α = 1 / (1 + 2π × fc / fs)
// fc = 截止频率, fs = 采样率

class LowPassFilter {
    float alpha;
    float prev_output = 0.0f;

public:
    LowPassFilter(float cutoff_freq, float sample_rate) {
        float rc = 1.0f / (2.0f * 3.14159265f * cutoff_freq);
        float dt = 1.0f / sample_rate;
        alpha = dt / (rc + dt);
    }

    float process(float input) {
        prev_output = alpha * input + (1.0f - alpha) * prev_output;
        return prev_output;
    }
};
```

#### 混响（Reverb）

混响模拟声音在空间中反射的效果，让声音听起来像是在特定环境中（大厅、洞穴、小房间）。

混响的核心组件：
1. **预延迟（Pre-delay）**：直达声与第一次反射之间的时间差
2. **早期反射（Early Reflections）**：前几次清晰的反射声
3. **混响尾音（Reverb Tail）**：密集的后期反射，逐渐衰减

实现方式通常使用**延迟线（Delay Line）**和**全通滤波器（All-Pass Filter）**网络，如 Schroeder 混响或 Freeverb 算法。

---

### 为什么需要这个？

没有音频引擎的游戏是"哑巴"的。音频不仅提供反馈（射击的枪声、受伤的呻吟），还承载关键的游戏信息（敌人的脚步声提示方位、背景音乐营造氛围）。一个优秀的音频引擎能够：

1. **同时管理数百个声音**：游戏场景中可能有几十个敌人、环境音效、UI 反馈同时发声
2. **实现空间音频**：让玩家通过声音判断敌人的位置和距离
3. **动态适应游戏状态**：战斗时音乐激昂，探索时音乐舒缓
4. **控制内存使用**：短音效常驻内存，长音乐流式加载
5. **提供音频效果**：混响让洞穴听起来像洞穴，滤波器模拟水下听觉

---

### 核心思想

游戏音频引擎的核心思想是**将音频播放抽象为资源管理 + 实时混音 + 空间定位 + 效果处理**的管线。理解数字音频的基本表示（采样率、位深度、PCM），掌握音频播放的双缓冲机制，学会使用软件混音器合并多路声音，利用距离衰减和 HRTF 实现 3D 定位，通过流式加载管理长音频的内存占用，最后借助音频事件系统将这一切与游戏逻辑无缝连接。

---

## 2. 代码示例

本节的示例使用 **miniaudio** 库，因为它是一个零依赖的单头文件库，非常适合学习和原型开发。

### 示例 1：播放 WAV 文件

```cpp
// audio_playback.cpp
// 编译: g++ -o audio_playback audio_playback.cpp -ldl -lpthread -lm
// 需要: miniaudio.h (从 https://github.com/mackron/miniaudio 下载)

#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"

#include <stdio.h>
#include <stdlib.h>

// 数据回调函数：miniaudio 每次需要音频数据时调用此函数
void data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount)
{
    // 从设备的用户数据中获取解码器
    ma_decoder* pDecoder = (ma_decoder*)pDevice->pUserData;
    if (pDecoder == NULL) {
        return;
    }

    // 从解码器读取 PCM 数据直接输出到声卡
    // 这是最简单的播放方式，没有混音
    ma_decoder_read_pcm_frames(pDecoder, pOutput, frameCount, NULL);

    (void)pInput;  // 不使用输入（录音）
}

int main(int argc, char** argv)
{
    // 检查命令行参数
    if (argc < 2) {
        printf("Usage: %s <audio_file>\n", argv[0]);
        printf("Supports: WAV, MP3, FLAC, OGG\n");
        return 1;
    }

    const char* filename = argv[1];

    // ===== 第一步：初始化解码器 =====
    ma_decoder decoder;
    ma_result result;

    // 配置解码器
    ma_decoder_config decoderConfig = ma_decoder_config_init(
        ma_format_f32,    // 输出格式：32-bit float（混音的标准格式）
        2,                // 输出声道数：立体声
        48000             // 输出采样率：48kHz
    );

    // 初始化解码器，从文件读取
    result = ma_decoder_init_file(filename, &decoderConfig, &decoder);
    if (result != MA_SUCCESS) {
        printf("Failed to initialize decoder for '%s' (error: %d)\n", filename, result);
        return 1;
    }

    printf("Successfully loaded: %s\n", filename);
    printf("  Sample Rate: %d Hz\n", decoder.outputSampleRate);
    printf("  Channels: %d\n", decoder.outputChannels);
    printf("  Format: %s\n",
        decoder.outputFormat == ma_format_f32 ? "32-bit float" :
        decoder.outputFormat == ma_format_s16 ? "16-bit signed" :
        decoder.outputFormat == ma_format_s24 ? "24-bit signed" :
        decoder.outputFormat == ma_format_s32 ? "32-bit signed" : "unknown");

    // ===== 第二步：配置并初始化播放设备 =====
    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_playback);
    deviceConfig.playback.format   = decoder.outputFormat;     // 使用与解码器相同的格式
    deviceConfig.playback.channels = decoder.outputChannels;   // 使用与解码器相同的声道数
    deviceConfig.sampleRate        = decoder.outputSampleRate; // 使用与解码器相同的采样率
    deviceConfig.dataCallback      = data_callback;            // 设置数据回调
    deviceConfig.pUserData         = &decoder;                 // 将解码器传给回调函数

    ma_device device;
    result = ma_device_init(NULL, &deviceConfig, &device);
    if (result != MA_SUCCESS) {
        printf("Failed to initialize playback device (error: %d)\n", result);
        ma_decoder_uninit(&decoder);
        return 1;
    }

    printf("Audio device initialized: %s\n", device.playback.name);
    printf("Buffer size: %d frames\n", device.playback.internalPeriodSizeInFrames);

    // ===== 第三步：开始播放 =====
    result = ma_device_start(&device);
    if (result != MA_SUCCESS) {
        printf("Failed to start playback device (error: %d)\n", result);
        ma_device_uninit(&device);
        ma_decoder_uninit(&decoder);
        return 1;
    }

    printf("\nPlaying... Press Enter to stop.\n");
    getchar();

    // ===== 清理 =====
    ma_device_uninit(&device);
    ma_decoder_uninit(&decoder);

    printf("Playback stopped.\n");
    return 0;
}
```

**运行方式:**
```bash
# 1. 下载 miniaudio.h
wget https://raw.githubusercontent.com/mackron/miniaudio/master/miniaudio.h

# 2. 编译（Linux/macOS）
g++ -o audio_playback audio_playback.cpp -ldl -lpthread -lm

# 3. 运行（准备一个 WAV 或 OGG 文件）
./audio_playback ./sounds/music.ogg
```

**Windows (MSVC):**
```bash
cl.exe audio_playback.cpp
audio_playback.exe ./sounds/music.wav
```

**预期输出:**
```text
Successfully loaded: ./sounds/music.ogg
  Sample Rate: 48000 Hz
  Channels: 2
  Format: 32-bit float
Audio device initialized: 默认输出设备
Buffer size: 960 frames

Playing... Press Enter to stop.
```

---

### 示例 2：简单的软件混音器

```cpp
// audio_mixer.cpp
// 一个简单的软件混音器，可以同时播放多个声音并独立控制音量
// 编译: g++ -o audio_mixer audio_mixer.cpp -ldl -lpthread -lm

#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// 最大同时播放的声音数
#define MAX_VOICES 32

// 声音实例状态
struct Voice {
    float* pcmData;           // PCM 数据（32-bit float，interleaved 立体声）
    ma_uint64 totalFrames;    // 总帧数
    ma_uint64 position;       // 当前播放位置（帧索引）
    float volume;             // 音量 (0.0 ~ 1.0)
    float pan;                // 声像 (-1.0 = 全左, 0.0 = 居中, 1.0 = 全右)
    bool active;              // 是否正在播放
    bool looping;             // 是否循环
};

// 混音器上下文
struct MixerContext {
    Voice voices[MAX_VOICES];
    ma_uint32 voiceCount;
    float masterVolume;       // 主音量
};

// 将分贝转换为线性振幅
float db_to_linear(float db) {
    return powf(10.0f, db / 20.0f);
}

// 将线性振幅转换为分贝
float linear_to_db(float linear) {
    if (linear <= 0.0f) return -100.0f;
    return 20.0f * log10f(linear);
}

// 加载 WAV 文件到内存（返回 32-bit float PCM 数据）
float* load_audio_file(const char* filename, ma_uint64* outFrameCount,
                       ma_uint32* outChannels, ma_uint32* outSampleRate)
{
    ma_decoder decoder;
    ma_decoder_config config = ma_decoder_config_init(ma_format_f32, 0, 48000);

    ma_result result = ma_decoder_init_file(filename, &config, &decoder);
    if (result != MA_SUCCESS) {
        printf("Failed to load '%s' (error: %d)\n", filename, result);
        return NULL;
    }

    // 获取文件信息
    *outChannels = decoder.outputChannels;
    *outSampleRate = decoder.outputSampleRate;

    // 计算总帧数
    ma_uint64 totalFrames;
    ma_decoder_get_length_in_pcm_frames(&decoder, &totalFrames);
    *outFrameCount = totalFrames;

    // 分配内存并读取所有 PCM 数据
    ma_uint64 frameCountRead;
    float* pcmData = (float*)malloc((size_t)(totalFrames * decoder.outputChannels * sizeof(float)));
    ma_decoder_read_pcm_frames(&decoder, pcmData, totalFrames, &frameCountRead);

    ma_decoder_uninit(&decoder);

    printf("Loaded '%s': %llu frames, %d channels, %d Hz\n",
           filename, totalFrames, *outChannels, *outSampleRate);

    return pcmData;
}

// 播放一个声音，返回 voice ID（-1 表示失败）
int play_sound(MixerContext* mixer, float* pcmData, ma_uint64 frameCount,
               float volume, float pan, bool looping)
{
    // 找一个空闲的 voice
    for (int i = 0; i < MAX_VOICES; i++) {
        if (!mixer->voices[i].active) {
            mixer->voices[i].pcmData = pcmData;
            mixer->voices[i].totalFrames = frameCount;
            mixer->voices[i].position = 0;
            mixer->voices[i].volume = volume;
            mixer->voices[i].pan = pan;
            mixer->voices[i].looping = looping;
            mixer->voices[i].active = true;
            mixer->voiceCount++;
            return i;
        }
    }
    printf("Warning: No free voice slots available!\n");
    return -1;
}

// 停止一个声音
void stop_sound(MixerContext* mixer, int voiceId) {
    if (voiceId >= 0 && voiceId < MAX_VOICES) {
        mixer->voices[voiceId].active = false;
        mixer->voiceCount--;
    }
}

// 设置声音音量
void set_voice_volume(MixerContext* mixer, int voiceId, float volume) {
    if (voiceId >= 0 && voiceId < MAX_VOICES) {
        mixer->voices[voiceId].volume = volume;
    }
}

// 设置声音声像
void set_voice_pan(MixerContext* mixer, int voiceId, float pan) {
    if (voiceId >= 0 && voiceId < MAX_VOICES) {
        // 限制在 [-1, 1] 范围内
        if (pan < -1.0f) pan = -1.0f;
        if (pan > 1.0f) pan = 1.0f;
        mixer->voices[voiceId].pan = pan;
    }
}

// 混音回调函数
void mixer_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount)
{
    MixerContext* mixer = (MixerContext*)pDevice->pUserData;
    float* output = (float*)pOutput;

    // 先清空输出缓冲区
    memset(output, 0, (size_t)(frameCount * 2 * sizeof(float)));

    // 对每个活跃的声音进行混音
    for (int v = 0; v < MAX_VOICES; v++) {
        Voice& voice = mixer->voices[v];
        if (!voice.active) continue;

        // 计算声像增益
        // pan = -1: 左声道 100%，右声道 0%
        // pan =  0: 左右各 50%
        // pan =  1: 左声道 0%，右声道 100%
        float leftGain = voice.volume * (1.0f - voice.pan) * 0.5f * mixer->masterVolume;
        float rightGain = voice.volume * (1.0f + voice.pan) * 0.5f * mixer->masterVolume;

        for (ma_uint32 f = 0; f < frameCount; f++) {
            if (voice.position >= voice.totalFrames) {
                if (voice.looping) {
                    voice.position = 0;
                } else {
                    voice.active = false;
                    mixer->voiceCount--;
                    break;
                }
            }

            // 读取当前帧的左右声道采样
            float leftSample = voice.pcmData[voice.position * 2 + 0];
            float rightSample = voice.pcmData[voice.position * 2 + 1];

            // 混音：将当前声音叠加到输出缓冲区
            output[f * 2 + 0] += leftSample * leftGain;
            output[f * 2 + 1] += rightSample * rightGain;

            voice.position++;
        }
    }

    // 软裁剪（Soft Clipping）：防止混音后音量超过 [-1, 1] 产生爆音
    // 使用 tanh 函数进行软裁剪，比硬裁剪更自然
    for (ma_uint32 f = 0; f < frameCount * 2; f++) {
        output[f] = tanhf(output[f]);
    }

    (void)pInput;
}

int main(int argc, char** argv)
{
    if (argc < 3) {
        printf("Usage: %s <sound1.wav> <sound2.wav> [sound3.wav ...]\n", argv[0]);
        printf("  Loads multiple sounds and demonstrates mixing.\n");
        return 1;
    }

    // 初始化混音器
    MixerContext mixer = {};
    mixer.masterVolume = 0.7f;  // 主音量设为 70%，给混音留余量

    // 加载所有声音文件
    const int maxSounds = argc - 1;
    float* soundData[maxSounds];
    ma_uint64 soundFrameCounts[maxSounds];
    ma_uint32 soundChannels[maxSounds];
    ma_uint32 soundSampleRates[maxSounds];

    for (int i = 0; i < maxSounds; i++) {
        soundData[i] = load_audio_file(argv[i + 1], &soundFrameCounts[i],
                                       &soundChannels[i], &soundSampleRates[i]);
        if (soundData[i] == NULL) {
            // 清理已加载的资源
            for (int j = 0; j < i; j++) {
                free(soundData[j]);
            }
            return 1;
        }
    }

    // 初始化音频设备
    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_playback);
    deviceConfig.playback.format   = ma_format_f32;
    deviceConfig.playback.channels = 2;  // 立体声输出
    deviceConfig.sampleRate        = 48000;
    deviceConfig.dataCallback      = mixer_callback;
    deviceConfig.pUserData         = &mixer;

    ma_device device;
    ma_result result = ma_device_init(NULL, &deviceConfig, &device);
    if (result != MA_SUCCESS) {
        printf("Failed to initialize device (error: %d)\n", result);
        for (int i = 0; i < maxSounds; i++) free(soundData[i]);
        return 1;
    }

    ma_device_start(&device);

    // ===== 演示混音功能 =====
    printf("\n=== Mixer Demo ===\n");
    printf("Active voices: %d/%d\n\n", mixer.voiceCount, MAX_VOICES);

    // 播放第一个声音（背景音乐），循环播放，居中
    int bgm = play_sound(&mixer, soundData[0], soundFrameCounts[0], 0.5f, 0.0f, true);
    printf("[1] Started BGM (voice %d), volume=0.5, pan=0.0, looping=true\n", bgm);
    printf("    Press Enter to add sound effect...\n");
    getchar();

    // 播放第二个声音（音效），不循环，偏左
    if (maxSounds > 1) {
        int sfx1 = play_sound(&mixer, soundData[1], soundFrameCounts[1], 0.8f, -0.5f, false);
        printf("[2] Started SFX (voice %d), volume=0.8, pan=-0.5, looping=false\n", sfx1);
    }
    printf("    Press Enter to add another sound effect...\n");
    getchar();

    // 播放第三个声音（音效），不循环，偏右
    if (maxSounds > 2) {
        int sfx2 = play_sound(&mixer, soundData[2], soundFrameCounts[2], 0.8f, 0.5f, false);
        printf("[3] Started SFX (voice %d), volume=0.8, pan=0.5, looping=false\n", sfx2);
    }
    printf("    Press Enter to stop all sounds...\n");
    getchar();

    // 停止所有声音
    for (int i = 0; i < MAX_VOICES; i++) {
        mixer.voices[i].active = false;
    }
    mixer.voiceCount = 0;
    printf("[4] All sounds stopped.\n");

    // 演示动态音量变化
    printf("\n=== Dynamic Volume Demo ===\n");
    int fadeVoice = play_sound(&mixer, soundData[0], soundFrameCounts[0], 0.0f, 0.0f, true);
    printf("[5] Starting fade-in demo...\n");

    // 简单演示：主线程中动态改变音量
    // 实际游戏中应该在游戏循环中更新
    for (float vol = 0.0f; vol <= 1.0f; vol += 0.05f) {
        set_voice_volume(&mixer, fadeVoice, vol);
        printf("    Volume: %.0f%% (%+.1f dB)\n", vol * 100.0f, linear_to_db(vol));
        ma_sleep(100);  // 等待 100ms
    }

    printf("\nPress Enter to exit.\n");
    getchar();

    // 清理
    ma_device_uninit(&device);
    for (int i = 0; i < maxSounds; i++) {
        free(soundData[i]);
    }

    return 0;
}
```

**运行方式:**
```bash
# 编译
g++ -o audio_mixer audio_mixer.cpp -ldl -lpthread -lm

# 运行（准备 2-3 个音频文件）
./audio_mixer ./sounds/bgm.ogg ./sounds/sfx_shoot.wav ./sounds/sfx_explosion.wav
```

**预期输出:**
```text
Loaded './sounds/bgm.ogg': 2880000 frames, 2 channels, 48000 Hz
Loaded './sounds/sfx_shoot.wav': 44100 frames, 2 channels, 48000 Hz
Loaded './sounds/sfx_explosion.wav': 96000 frames, 2 channels, 48000 Hz

=== Mixer Demo ===
Active voices: 0/32

[1] Started BGM (voice 0), volume=0.5, pan=0.0, looping=true
    Press Enter to add sound effect...

[2] Started SFX (voice 1), volume=0.8, pan=-0.5, looping=false
    Press Enter to add another sound effect...

[3] Started SFX (voice 2), volume=0.8, pan=0.5, looping=false
    Press Enter to stop all sounds...

[4] All sounds stopped.

=== Dynamic Volume Demo ===
[5] Starting fade-in demo...
    Volume: 0% (-100.0 dB)
    Volume: 5% (-26.0 dB)
    ...
    Volume: 100% (0.0 dB)

Press Enter to exit.
```

---

### 示例 3：3D 定位音频

```cpp
// audio_3d.cpp
// 3D 定位音频演示：一个听者在原点，多个声源在 3D 空间中移动
// 编译: g++ -o audio_3d audio_3d.cpp -ldl -lpthread -lm

#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

// 3D 向量
struct Vec3 {
    float x, y, z;

    Vec3(float x = 0, float y = 0, float z = 0) : x(x), y(y), z(z) {}

    float length() const {
        return sqrtf(x * x + y * y + z * z);
    }

    Vec3 normalized() const {
        float len = length();
        if (len < 0.0001f) return Vec3(0, 0, 0);
        return Vec3(x / len, y / len, z / len);
    }

    Vec3 operator-(const Vec3& other) const {
        return Vec3(x - other.x, y - other.y, z - other.z);
    }
};

// 3D 音频源
struct AudioSource3D {
    float* pcmData;
    ma_uint64 totalFrames;
    ma_uint64 position;
    Vec3 position3D;        // 世界空间位置
    float baseVolume;       // 基础音量
    float minDistance;      // 最小距离（此距离内不衰减）
    float maxDistance;      // 最大可听距离
    float rolloffFactor;    // 衰减系数
    bool active;
    bool looping;
};

// 听者
struct AudioListener {
    Vec3 position;
    Vec3 forward;   // 朝向（Z轴方向）
    Vec3 up;        // 上方向
};

// 3D 音频引擎上下文
struct AudioEngine3D {
    static const int MAX_SOURCES = 16;
    AudioSource3D sources[MAX_SOURCES];
    AudioListener listener;
    float masterVolume;
};

// 计算距离衰减（使用反距离模型）
float calculate_distance_attenuation(const Vec3& sourcePos, const Vec3& listenerPos,
                                      float minDist, float maxDist, float rolloff)
{
    float distance = (sourcePos - listenerPos).length();

    if (distance <= minDist) {
        return 1.0f;  // 在最小距离内，不衰减
    }
    if (distance >= maxDist) {
        return 0.0f;  // 超过最大距离，静音
    }

    // 反距离模型
    float attenuation = minDist / (minDist + rolloff * (distance - minDist));

    // 限制在 [0, 1] 范围内
    if (attenuation > 1.0f) attenuation = 1.0f;
    if (attenuation < 0.0f) attenuation = 0.0f;

    return attenuation;
}

// 计算声像（pan）和音量比例
// 返回左右声道增益
void calculate_spatial_pan(const Vec3& sourcePos, const AudioListener& listener,
                           float* outLeftGain, float* outRightGain)
{
    // 计算从听者到声源的方向向量
    Vec3 toSource = sourcePos - listener.position;
    Vec3 dir = toSource.normalized();

    // 将方向转换到听者的局部坐标系
    // 简化的 2D 投影：只考虑 XZ 平面（水平面）
    // 左声道增益取决于声源在听者左侧的分量

    // 计算听者的右方向（forward × up）
    Vec3 right(
        listener.forward.y * listener.up.z - listener.forward.z * listener.up.y,
        listener.forward.z * listener.up.x - listener.forward.x * listener.up.z,
        listener.forward.x * listener.up.y - listener.forward.y * listener.up.x
    );

    // 点积：dir 在 right 方向上的投影
    // > 0 表示在右侧，< 0 表示在左侧
    float dotRight = dir.x * right.x + dir.y * right.y + dir.z * right.z;

    // 将 [-1, 1] 映射到声像
    // 使用平方曲线让中间区域更自然
    float pan = dotRight;  // -1 = 左, 1 = 右

    // 使用余弦分布让声像更自然
    float angle = pan * 3.14159265f * 0.25f;  // 映射到 [-45°, 45°]
    *outLeftGain  = cosf(angle + 3.14159265f * 0.25f) * 1.4142f;  // √2
    *outRightGain = cosf(angle - 3.14159265f * 0.25f) * 1.4142f;

    // 归一化
    float sum = *outLeftGain + *outRightGain;
    if (sum > 0.0f) {
        *outLeftGain /= sum;
        *outRightGain /= sum;
    }
}

// 3D 音频回调
void audio_3d_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount)
{
    AudioEngine3D* engine = (AudioEngine3D*)pDevice->pUserData;
    float* output = (float*)pOutput;

    // 清空输出
    memset(output, 0, (size_t)(frameCount * 2 * sizeof(float)));

    // 处理每个活跃的声源
    for (int s = 0; s < AudioEngine3D::MAX_SOURCES; s++) {
        AudioSource3D& source = engine->sources[s];
        if (!source.active) continue;

        // 计算距离衰减
        float attenuation = calculate_distance_attenuation(
            source.position3D, engine->listener.position,
            source.minDistance, source.maxDistance, source.rolloffFactor
        );

        if (attenuation <= 0.0f) {
            // 声源太远，跳过但继续推进位置（如果很近的话需要同步）
            // 实际引擎中可能需要更复杂的处理
            continue;
        }

        // 计算空间声像
        float leftPan, rightPan;
        calculate_spatial_pan(source.position3D, engine->listener, &leftPan, &rightPan);

        // 最终增益 = 基础音量 × 距离衰减 × 主音量 × 声像
        float leftGain = source.baseVolume * attenuation * engine->masterVolume * leftPan * 2.0f;
        float rightGain = source.baseVolume * attenuation * engine->masterVolume * rightPan * 2.0f;

        for (ma_uint32 f = 0; f < frameCount; f++) {
            if (source.position >= source.totalFrames) {
                if (source.looping) {
                    source.position = 0;
                } else {
                    source.active = false;
                    break;
                }
            }

            float leftSample = source.pcmData[source.position * 2 + 0];
            float rightSample = source.pcmData[source.position * 2 + 1];

            output[f * 2 + 0] += leftSample * leftGain;
            output[f * 2 + 1] += rightSample * rightGain;

            source.position++;
        }
    }

    // 软裁剪
    for (ma_uint32 f = 0; f < frameCount * 2; f++) {
        if (output[f] > 1.0f) output[f] = 1.0f;
        if (output[f] < -1.0f) output[f] = -1.0f;
    }

    (void)pInput;
}

// 加载音频文件
float* load_audio(const char* filename, ma_uint64* outFrames) {
    ma_decoder decoder;
    ma_decoder_config config = ma_decoder_config_init(ma_format_f32, 2, 48000);

    if (ma_decoder_init_file(filename, &config, &decoder) != MA_SUCCESS) {
        return NULL;
    }

    ma_uint64 frames;
    ma_decoder_get_length_in_pcm_frames(&decoder, &frames);
    *outFrames = frames;

    float* data = (float*)malloc((size_t)(frames * 2 * sizeof(float)));
    ma_decoder_read_pcm_frames(&decoder, data, frames, NULL);
    ma_decoder_uninit(&decoder);

    return data;
}

int main(int argc, char** argv)
{
    if (argc < 2) {
        printf("Usage: %s <audio_file>\n", argv[0]);
        printf("Demonstrates 3D positional audio with moving sources.\n");
        return 1;
    }

    // 加载音频
    ma_uint64 frameCount;
    float* audioData = load_audio(argv[1], &frameCount);
    if (!audioData) {
        printf("Failed to load audio file.\n");
        return 1;
    }

    // 初始化 3D 音频引擎
    AudioEngine3D engine = {};
    engine.masterVolume = 0.8f;
    engine.listener = AudioListener{
        Vec3(0, 0, 0),      // 听者在原点
        Vec3(0, 0, 1),      // 朝向 +Z
        Vec3(0, 1, 0)       // 上方 +Y
    };

    // 初始化音频设备
    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_playback);
    deviceConfig.playback.format   = ma_format_f32;
    deviceConfig.playback.channels = 2;
    deviceConfig.sampleRate        = 48000;
    deviceConfig.dataCallback      = audio_3d_callback;
    deviceConfig.pUserData         = &engine;

    ma_device device;
    if (ma_device_init(NULL, &deviceConfig, &device) != MA_SUCCESS) {
        printf("Failed to init device.\n");
        free(audioData);
        return 1;
    }

    ma_device_start(&device);

    // ===== 3D 音频演示 =====
    printf("=== 3D Audio Demo ===\n");
    printf("Listener at (0, 0, 0), facing +Z\n\n");

    // 创建声源 1：在左侧循环播放
    engine.sources[0].pcmData = audioData;
    engine.sources[0].totalFrames = frameCount;
    engine.sources[0].position = 0;
    engine.sources[0].position3D = Vec3(-5, 0, 0);  // 左侧 5 米
    engine.sources[0].baseVolume = 1.0f;
    engine.sources[0].minDistance = 1.0f;
    engine.sources[0].maxDistance = 20.0f;
    engine.sources[0].rolloffFactor = 1.0f;
    engine.sources[0].active = true;
    engine.sources[0].looping = true;

    printf("[1] Source 0: Left side (-5, 0, 0), looping\n");
    printf("    Press Enter to add a moving source...\n");
    getchar();

    // 创建声源 2：在右侧
    engine.sources[1].pcmData = audioData;
    engine.sources[1].totalFrames = frameCount;
    engine.sources[1].position = 0;
    engine.sources[1].position3D = Vec3(5, 0, 0);  // 右侧 5 米
    engine.sources[1].baseVolume = 1.0f;
    engine.sources[1].minDistance = 1.0f;
    engine.sources[1].maxDistance = 20.0f;
    engine.sources[1].rolloffFactor = 1.0f;
    engine.sources[1].active = true;
    engine.sources[1].looping = true;

    printf("[2] Source 1: Right side (5, 0, 0), looping\n");
    printf("    Press Enter to start moving sources...\n");
    getchar();

    // 模拟声源移动
    printf("\n[3] Moving sources in a circle around listener...\n");
    float angle = 0.0f;
    const float radius = 5.0f;
    const int steps = 60;  // 转一圈，每步 100ms = 6 秒一圈

    for (int i = 0; i < steps; i++) {
        angle += 2.0f * 3.14159265f / steps;

        // 声源 0：逆时针转
        engine.sources[0].position3D = Vec3(
            cosf(angle) * radius,
            0,
            sinf(angle) * radius
        );

        // 声源 1：顺时针转，距离更远
        engine.sources[1].position3D = Vec3(
            cosf(-angle * 1.5f) * radius * 1.5f,
            0,
            sinf(-angle * 1.5f) * radius * 1.5f
        );

        float dist0 = (engine.sources[0].position3D - engine.listener.position).length();
        float dist1 = (engine.sources[1].position3D - engine.listener.position).length();

        printf("\rFrame %2d/60 | Src0: (%.1f, %.1f, %.1f) d=%.1fm | Src1: (%.1f, %.1f, %.1f) d=%.1fm",
               i + 1,
               engine.sources[0].position3D.x,
               engine.sources[0].position3D.y,
               engine.sources[0].position3D.z,
               dist0,
               engine.sources[1].position3D.x,
               engine.sources[1].position3D.y,
               engine.sources[1].position3D.z,
               dist1);
        fflush(stdout);

        ma_sleep(100);
    }

    printf("\n\n[4] Sources stopped.\n");
    engine.sources[0].active = false;
    engine.sources[1].active = false;

    printf("Press Enter to exit.\n");
    getchar();

    // 清理
    ma_device_uninit(&device);
    free(audioData);

    return 0;
}
```

**运行方式:**
```bash
# 编译
g++ -o audio_3d audio_3d.cpp -ldl -lpthread -lm

# 运行
./audio_3d ./sounds/engine_loop.ogg
```

**预期输出:**
```text
=== 3D Audio Demo ===
Listener at (0, 0, 0), facing +Z

[1] Source 0: Left side (-5, 0, 0), looping
    Press Enter to add a moving source...

[2] Source 1: Right side (5, 0, 0), looping
    Press Enter to start moving sources...

[3] Moving sources in a circle around listener...
Frame 60/60 | Src0: (5.0, 0.0, 0.0) d=5.0m | Src1: (-0.0, 0.0, -7.5) d=7.5m

[4] Sources stopped.
Press Enter to exit.
```

---

### 示例 4：音频事件系统（简化版）

```cpp
// audio_event_system.cpp
// 简化的音频事件系统演示
// 编译: g++ -o audio_event_system audio_event_system.cpp -ldl -lpthread -lm

#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// ========== 音频事件系统核心 ==========

#define MAX_EVENTS 64
#define MAX_INSTANCES 32
#define MAX_BUSES 8

// 音频总线类型
enum BusType {
    BUS_MASTER = 0,
    BUS_SFX,
    BUS_MUSIC,
    BUS_VOICE,
    BUS_UI,
    BUS_COUNT
};

// 音频事件定义
struct AudioEventDef {
    const char* name;           // 事件名称（如 "weapon_fire"）
    const char* filename;       // 音频文件路径
    float defaultVolume;        // 默认音量
    float defaultPitch;         // 默认音高变化
    bool is3D;                  // 是否是 3D 音频
    float minDistance;          // 3D 最小距离
    float maxDistance;          // 3D 最大距离
    BusType bus;                // 所属总线
};

// 音频实例
struct AudioInstance {
    int eventId;                // 对应的事件 ID
    float* pcmData;             // PCM 数据
    ma_uint64 totalFrames;
    ma_uint64 position;
    float volume;               // 当前音量
    float pitch;                // 当前音高（播放速率倍率）
    float pan;                  // 声像
    Vec3 position3D;            // 3D 位置
    bool active;
    bool looping;
};

// 音频总线
struct AudioBus {
    const char* name;
    float volume;               // 总线音量
    bool muted;                 // 是否静音
};

// 音频引擎
struct AudioEventEngine {
    AudioEventDef events[MAX_EVENTS];
    int eventCount;

    AudioInstance instances[MAX_INSTANCES];
    int instanceCount;

    AudioBus buses[MAX_BUSES];

    ma_device device;
};

// 3D 向量（复用之前的定义）
struct Vec3 {
    float x, y, z;
    Vec3(float x = 0, float y = 0, float z = 0) : x(x), y(y), z(z) {}
    float length() const { return sqrtf(x*x + y*y + z*z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x-o.x, y-o.y, z-o.z); }
};

// 初始化音频引擎
void init_engine(AudioEventEngine* engine) {
    engine->eventCount = 0;
    engine->instanceCount = 0;

    // 初始化总线
    const char* busNames[] = {"Master", "SFX", "Music", "Voice", "UI"};
    for (int i = 0; i < BUS_COUNT; i++) {
        engine->buses[i].name = busNames[i];
        engine->buses[i].volume = 1.0f;
        engine->buses[i].muted = false;
    }
}

// 注册音频事件
int register_event(AudioEventEngine* engine, const char* name, const char* filename,
                   float volume, BusType bus, bool is3D = false,
                   float minDist = 1.0f, float maxDist = 100.0f) {
    if (engine->eventCount >= MAX_EVENTS) return -1;

    int id = engine->eventCount++;
    engine->events[id].name = name;
    engine->events[id].filename = filename;
    engine->events[id].defaultVolume = volume;
    engine->events[id].defaultPitch = 1.0f;
    engine->events[id].is3D = is3D;
    engine->events[id].minDistance = minDist;
    engine->events[id].maxDistance = maxDist;
    engine->events[id].bus = bus;

    return id;
}

// 加载音频事件的所有资源
bool load_event_resources(AudioEventEngine* engine) {
    // 简化版：实际项目中应该在初始化时批量加载
    // 这里假设 PCM 数据在播放时按需加载
    return true;
}

// 触发音频事件（播放一个声音）
int trigger_event(AudioEventEngine* engine, int eventId, float volume = -1.0f,
                  const Vec3& pos = Vec3()) {
    if (eventId < 0 || eventId >= engine->eventCount) return -1;

    // 找一个空闲实例
    int instanceId = -1;
    for (int i = 0; i < MAX_INSTANCES; i++) {
        if (!engine->instances[i].active) {
            instanceId = i;
            break;
        }
    }
    if (instanceId < 0) {
        printf("Warning: No free audio instances!\n");
        return -1;
    }

    AudioEventDef& evt = engine->events[eventId];
    AudioInstance& inst = engine->instances[instanceId];

    // 加载音频数据（简化版：每次都从文件加载）
    // 实际引擎应该缓存已加载的数据
    ma_decoder decoder;
    ma_decoder_config config = ma_decoder_config_init(ma_format_f32, 2, 48000);
    if (ma_decoder_init_file(evt.filename, &config, &decoder) != MA_SUCCESS) {
        printf("Failed to load: %s\n", evt.filename);
        return -1;
    }

    ma_uint64 frames;
    ma_decoder_get_length_in_pcm_frames(&decoder, &frames);
    inst.pcmData = (float*)malloc((size_t)(frames * 2 * sizeof(float)));
    ma_decoder_read_pcm_frames(&decoder, inst.pcmData, frames, NULL);
    ma_decoder_uninit(&decoder);

    inst.eventId = eventId;
    inst.totalFrames = frames;
    inst.position = 0;
    inst.volume = (volume >= 0.0f) ? volume : evt.defaultVolume;
    inst.pitch = evt.defaultPitch;
    inst.pan = 0.0f;
    inst.position3D = pos;
    inst.active = true;
    inst.looping = false;

    engine->instanceCount++;

    printf("[Audio] Play '%s' (bus: %s, vol: %.2f)\n",
           evt.name, engine->buses[evt.bus].name, inst.volume);

    return instanceId;
}

// 停止实例
void stop_instance(AudioEventEngine* engine, int instanceId) {
    if (instanceId < 0 || instanceId >= MAX_INSTANCES) return;
    if (engine->instances[instanceId].active) {
        free(engine->instances[instanceId].pcmData);
        engine->instances[instanceId].active = false;
        engine->instanceCount--;
    }
}

// 设置总线音量
void set_bus_volume(AudioEventEngine* engine, BusType bus, float volume) {
    if (bus >= 0 && bus < BUS_COUNT) {
        engine->buses[bus].volume = volume;
    }
}

// 静音/取消静音总线
void mute_bus(AudioEventEngine* engine, BusType bus, bool mute) {
    if (bus >= 0 && bus < BUS_COUNT) {
        engine->buses[bus].muted = mute;
    }
}

// 音频回调
void event_engine_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount) {
    AudioEventEngine* engine = (AudioEventEngine*)pDevice->pUserData;
    float* output = (float*)pOutput;

    memset(output, 0, (size_t)(frameCount * 2 * sizeof(float)));

    // 按总线分组混音
    float busBuffers[BUS_COUNT][2048 * 2];  // 假设 frameCount <= 2048
    for (int b = 0; b < BUS_COUNT; b++) {
        memset(busBuffers[b], 0, (size_t)(frameCount * 2 * sizeof(float)));
    }

    // 将每个实例混音到对应总线
    for (int i = 0; i < MAX_INSTANCES; i++) {
        AudioInstance& inst = engine->instances[i];
        if (!inst.active) continue;

        AudioEventDef& evt = engine->events[inst.eventId];
        AudioBus& bus = engine->buses[evt.bus];

        if (bus.muted) continue;

        float busVol = bus.volume * engine->buses[BUS_MASTER].volume;
        float leftGain = inst.volume * busVol * (1.0f - inst.pan) * 0.5f;
        float rightGain = inst.volume * busVol * (1.0f + inst.pan) * 0.5f;

        // 音高变化：通过改变采样步进来实现
        float pitchStep = inst.pitch;
        float samplePos = (float)inst.position;

        for (ma_uint32 f = 0; f < frameCount; f++) {
            ma_uint64 pos = (ma_uint64)samplePos;
            if (pos >= inst.totalFrames) {
                if (inst.looping) {
                    samplePos = 0;
                    pos = 0;
                } else {
                    inst.active = false;
                    engine->instanceCount--;
                    break;
                }
            }

            // 线性插值采样（处理非整数位置）
            float frac = samplePos - (float)pos;
            ma_uint64 nextPos = (pos + 1 < inst.totalFrames) ? pos + 1 : pos;

            float leftSample = inst.pcmData[pos * 2 + 0] * (1.0f - frac)
                             + inst.pcmData[nextPos * 2 + 0] * frac;
            float rightSample = inst.pcmData[pos * 2 + 1] * (1.0f - frac)
                              + inst.pcmData[nextPos * 2 + 1] * frac;

            busBuffers[evt.bus][f * 2 + 0] += leftSample * leftGain;
            busBuffers[evt.bus][f * 2 + 1] += rightSample * rightGain;

            samplePos += pitchStep;
        }

        inst.position = (ma_uint64)samplePos;
    }

    // 将所有总线混音到主输出
    float masterVol = engine->buses[BUS_MASTER].muted ? 0.0f : engine->buses[BUS_MASTER].volume;
    for (int b = 1; b < BUS_COUNT; b++) {  // 从 1 开始，跳过 Master
        for (ma_uint32 f = 0; f < frameCount * 2; f++) {
            output[f] += busBuffers[b][f];
        }
    }

    // 应用主音量并裁剪
    for (ma_uint32 f = 0; f < frameCount * 2; f++) {
        output[f] = tanhf(output[f] * masterVol);
    }

    (void)pInput;
}

// ========== 使用示例 ==========

int main(int argc, char** argv) {
    printf("=== Audio Event System Demo ===\n\n");

    AudioEventEngine engine;
    init_engine(&engine);

    // 注册游戏音频事件
    // 注意：这里使用占位文件名，实际运行时需要替换为真实音频文件
    int evtShoot = register_event(&engine, "weapon_shoot", "./sounds/shoot.wav",
                                   0.8f, BUS_SFX, false);
    int evtExplosion = register_event(&engine, "explosion", "./sounds/explosion.wav",
                                       1.0f, BUS_SFX, true, 2.0f, 50.0f);
    int evtBGM = register_event(&engine, "bgm_battle", "./sounds/battle.ogg",
                                 0.5f, BUS_MUSIC, false);
    int evtClick = register_event(&engine, "ui_click", "./sounds/click.wav",
                                   0.6f, BUS_UI, false);
    int evtVoice = register_event(&engine, "npc_greet", "./sounds/greet.wav",
                                   1.0f, BUS_VOICE, false);

    printf("Registered %d audio events:\n", engine.eventCount);
    for (int i = 0; i < engine.eventCount; i++) {
        printf("  [%d] %s -> %s (bus: %s)\n", i,
               engine.events[i].name,
               engine.events[i].filename,
               engine.buses[engine.events[i].bus].name);
    }

    // 初始化音频设备
    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_playback);
    deviceConfig.playback.format   = ma_format_f32;
    deviceConfig.playback.channels = 2;
    deviceConfig.sampleRate        = 48000;
    deviceConfig.dataCallback      = event_engine_callback;
    deviceConfig.pUserData         = &engine;

    if (ma_device_init(NULL, &deviceConfig, &engine.device) != MA_SUCCESS) {
        printf("Failed to init audio device.\n");
        return 1;
    }
    ma_device_start(&engine.device);

    printf("\n--- Game Simulation ---\n");
    printf("(Note: This demo requires actual audio files to produce sound)\n\n");

    // 模拟游戏场景
    printf("[Game] Battle starts, playing BGM...\n");
    trigger_event(&engine, evtBGM);

    printf("[Game] Player clicks UI...\n");
    trigger_event(&engine, evtClick);

    printf("[Game] Player fires weapon...\n");
    trigger_event(&engine, evtShoot);

    printf("[Game] Explosion at position (10, 0, 5)...\n");
    trigger_event(&engine, evtExplosion, 1.0f, Vec3(10, 0, 5));

    printf("[Game] NPC speaks...\n");
    trigger_event(&engine, evtVoice);

    printf("\n--- Bus Control Demo ---\n");
    printf("Current bus volumes:\n");
    for (int i = 0; i < BUS_COUNT; i++) {
        printf("  %s: %.0f%% %s\n", engine.buses[i].name,
               engine.buses[i].volume * 100.0f,
               engine.buses[i].muted ? "(MUTED)" : "");
    }

    printf("\nMuting Music bus...\n");
    mute_bus(&engine, BUS_MUSIC, true);

    printf("Setting SFX volume to 50%%...\n");
    set_bus_volume(&engine, BUS_SFX, 0.5f);

    printf("\nPress Enter to stop and exit.\n");
    getchar();

    // 清理
    for (int i = 0; i < MAX_INSTANCES; i++) {
        if (engine.instances[i].active) {
            free(engine.instances[i].pcmData);
        }
    }
    ma_device_uninit(&engine.device);

    printf("Audio engine shut down.\n");
    return 0;
}
```

**运行方式:**
```bash
g++ -o audio_event_system audio_event_system.cpp -ldl -lpthread -lm
./audio_event_system
```

---

## 3. 练习

### 练习 1：实现音频流式加载

将示例 1 的完整加载改为流式加载。要求：

1. 创建一个环形缓冲区（Ring Buffer），大小为 4 秒音频数据
2. 在后台线程中持续从 OGG 文件解码数据填充环形缓冲区
3. 在音频回调中从环形缓冲区读取数据播放
4. 处理缓冲区欠载（underflow）的情况：当读取速度跟不上播放速度时，输出静音并打印警告

**提示：**
- 使用 `std::thread` 创建后台解码线程
- 使用 `std::mutex` 保护环形缓冲区的读写位置
- 音频回调中不要做任何可能阻塞的操作（如文件 I/O、锁等待）

### 练习 2：为混音器添加效果器

在示例 2 的软件混音器基础上，添加以下 DSP 效果：

1. **低通滤波器**：为每个声音实例添加可选的低通滤波器， cutoff 频率可配置
2. **简单的延迟效果（Echo）**：在 Master 总线上添加一个延迟效果，产生回声
3. **音量渐变（Fade In/Out）**：实现 `fade_in()` 和 `fade_out()` 函数，在指定时间内平滑改变音量

**延迟效果实现思路：**
```cpp
// 延迟线
class DelayLine {
    float* buffer;
    size_t size;
    size_t writePos;
    float feedback;      // 反馈系数 (0.0 ~ 0.9)
    float wetMix;        // 湿声比例

public:
    float process(float input) {
        float delayed = buffer[writePos];
        buffer[writePos] = input + delayed * feedback;
        writePos = (writePos + 1) % size;
        return input * (1.0f - wetMix) + delayed * wetMix;
    }
};
```

### 练习 3（可选）：实现多普勒效应

在示例 3 的 3D 音频引擎中添加多普勒效应：

1. 为每个声源添加速度向量 `velocity`
2. 在每次更新声源位置时，计算声源与听者的相对速度
3. 根据多普勒公式调整播放音高（pitch）：

```
pitch = (v_sound + v_listener) / (v_sound - v_source)
```

其中：
- `v_sound`：声速（空气中约 343 m/s）
- `v_listener`：听者在声源方向上的速度分量
- `v_source`：声源在听者方向上的速度分量

4. 创建一个测试场景：一个声源以不同速度从听者身边掠过，验证音高变化效果

---

## 4. 扩展阅读

- **miniaudio 官方文档**: https://miniaud.io/docs/manual/index.html — 详细的 API 参考和教程
- **OpenAL Soft**: https://openal-soft.org/ — OpenAL 的开源实现，支持 HRTF
- **The Audio Programming Book** by Richard Boulanger — 音频编程经典教材
- **Game Audio Programming** by Guy Somberg — 游戏音频编程专著
- **Digital Signal Processing** by Steven W. Smith — 免费在线 DSP 教材：https://www.dspguide.com/
- **Wwise 官方文档**: https://www.audiokinetic.com/library/edge/ — 商业音频中间件参考
- **FMOD 文档**: https://www.fmod.com/docs/2.02/api/ — 另一主流商业音频中间件
- **Steam Audio**: https://valvesoftware.github.io/steam-audio/ — Valve 开源的空间音频 SDK
- **MIT KEMAR HRTF 数据**: http://sound.media.mit.edu/resources/KEMAR.html — HRTF 测量数据集

---

## 常见陷阱

- **音频回调中做阻塞操作**：音频回调运行在实时线程中，任何阻塞操作（文件 I/O、内存分配、锁等待）都会导致爆音。所有数据应在回调外准备好。

- **忽略采样率转换**：如果音频文件的采样率与设备采样率不一致，直接播放会导致音高错误（如 44.1kHz 文件在 48kHz 设备上播放会变快变高）。应使用重采样（resampling）或让音频库自动处理。

- **混音溢出**：多个声音同时播放时，采样值相加可能超过 [-1, 1] 范围，产生刺耳的爆音。应在 32-bit float 空间混音，最后做软裁剪或压缩。

- **缓冲区大小选择不当**：缓冲区太小（< 256 采样）容易导致欠载爆音；太大（> 4096 采样）导致音画不同步。游戏通常选择 512~2048 采样。

- **3D 音频使用欧氏距离而非游戏逻辑距离**：游戏中的"距离"可能不是真实世界的米。应确保音频引擎使用的距离单位与游戏世界一致，或添加适当的缩放因子。

- **忘记处理音频设备断开**：在移动设备或热插拔场景下，音频设备可能随时断开。应监听设备变化事件并优雅地重新初始化。

- **MP3 循环播放的间隙问题**：MP3 格式在帧边界有填充，循环播放时会产生"咔哒"声。循环音效应使用 WAV 或 OGG 格式。

- **内存泄漏**：音频数据通常较大，忘记释放解码后的 PCM 数据会导致严重的内存泄漏。建议使用智能指针或音频资源管理器统一管理生命周期。

- **音量和频率的线性/对数混淆**：人耳对音量的感知是对数的，但对音高（频率）的感知近似线性。调整音量应使用分贝或指数曲线，调整音高可以使用线性插值。
