---
title: "动画系统：骨骼动画与蒙皮"
updated: 2026-06-05
---

# 动画系统：骨骼动画与蒙皮

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 01-数学基础：线性代数与几何

---

## 1. 概念讲解

### 为什么需要这个？

在早期游戏中，角色动画通过逐帧播放预渲染的模型序列来实现。这种方法简单直接，但存在致命缺陷：

1. **内存爆炸**：一个60fps、1000帧的行走动画需要存储1000个完整模型，每个模型数万个顶点
2. **无法混合**：无法让角色的上半身射击同时下半身奔跑
3. **无法动态响应**：角色无法根据地形实时调整脚步位置
4. **无法复用**：同一个角色模型无法适配不同动画，反之亦然

骨骼动画（Skeletal Animation）彻底解决了这些问题。其核心思想是：**动画数据只驱动少量骨骼的变换，而顶点通过蒙皮（Skinning）过程跟随骨骼运动**。一个角色可能有几万个顶点，但只有几十到几百根骨骼。动画数据从存储顶点位置变成了存储骨骼变换矩阵，数据量压缩了数个数量级。

现代3A游戏的角色动画系统是整个引擎中最复杂的子系统之一，它整合了骨骼动画、蒙皮、混合、状态机、IK、动画压缩、根运动（Root Motion）、动画重定向（Retargeting）等技术。

### 核心思想

骨骼动画的本质是**分层空间变换**。想象一个木偶：每根骨骼是一个关节，关节之间有层级关系（父骨骼带动子骨骼）。动画数据记录了每根骨骼相对于其父骨骼的变换（局部变换），通过层级累积得到每根骨骼在世界空间中的最终变换。然后，每个顶点根据绑定到它的骨骼的变换和权重，计算出自己的最终位置。

---

### 1.1 关键帧动画基础

关键帧动画（Keyframe Animation）是动画数据的原始形式。动画师在时间轴上的关键时间点设置角色姿态（Pose），中间帧由计算机插值生成。

**关键帧数据结构：**

```
AnimationClip:
  - duration: float (秒)
  - frameRate: float (fps)
  - tracks: Track[]

Track (对应一根骨骼的一条属性):
  - boneIndex: int
  - property: Position | Rotation | Scale
  - keyframes: Keyframe[]

Keyframe:
  - time: float
  - value: Vec3 | Quaternion
  - interpolation: Linear | Bezier | Step
```

关键帧之间的插值是动画系统的核心操作。位置通常用线性插值（Lerp），旋转用球面线性插值（Slerp），缩放也用Lerp。

---

### 1.2 骨骼层级与绑定姿态

**骨骼（Bone/Joint）** 是动画系统的基本单元。骨骼不是几何体，而是一个坐标空间的原点加上一个朝向。每根骨骼有一个父骨骼（根骨骼除外），形成树形结构。

```
Skeleton Hierarchy（典型人体骨骼示例）:

Root (Hips)
├── Spine
│   ├── Chest
│   │   ├── Neck
│   │   │   └── Head
│   │   ├── LeftShoulder
│   │   │   └── LeftUpperArm
│   │   │       └── LeftLowerArm
│   │   │           └── LeftHand
│   │   └── RightShoulder
│   │       └── RightUpperArm
│   │           └── RightLowerArm
│   │               └── RightHand
│   └── ...
├── LeftUpperLeg
│   └── LeftLowerLeg
│       └── LeftFoot
└── RightUpperLeg
    └── RightLowerLeg
        └── RightFoot
```

**绑定姿态（Bind Pose / T-Pose / Reference Pose）** 是建模时定义的骨骼默认姿态。所有动画数据都是相对于绑定姿态的偏移。绑定姿态的选择很重要：

- **T-Pose**：双臂平举，常用于角色建模
- **A-Pose**：双臂微张，某些引擎偏好
- **Bind Pose**：导出时的实际姿态

绑定姿态决定了蒙皮权重绘制的基准。顶点在绑定姿态下的位置称为**绑定位置（Bind Position）**。

---

### 1.3 骨骼空间 vs 模型空间 vs 世界空间

理解这三个空间是掌握骨骼动画的关键。

**骨骼空间（Bone/Local Space）**：以某根骨骼自身为原点的坐标系。骨骼的局部变换（Local Transform）描述的是从父骨骼空间到该骨骼空间的变换。

**模型空间（Model/Character Space）**：以角色根节点为原点的坐标系。骨骼的模型变换（Model Transform）描述的是从模型空间到该骨骼空间的变换，通过层级累积父骨骼的变换得到。

**世界空间（World Space）**：以场景原点为原点的坐标系。模型变换再乘以实体的世界变换就得到世界空间中的位置。

**变换层级：**

```
Local Transform (骨骼i) → 乘以 Parent's Model Transform → Model Transform (骨骼i)
Model Transform (骨骼i) → 乘以 Entity World Transform → World Transform (骨骼i)
```

用矩阵表示：

```
M_model(i) = M_local(i) * M_model(parent(i))
M_world(i) = M_model(i) * M_world(entity)
```

注意矩阵乘法的顺序取决于你使用的是列向量（`v' = M * v`）还是行向量（`v' = v * M`）约定。在图形学中，列向量约定更常见（OpenGL、GLSL），所以变换从右向左应用。

---

### 1.4 顶点蒙皮（Vertex Skinning）

蒙皮是将顶点绑定到骨骼并随骨骼运动的过程。每个顶点可以受一根或多根骨骼影响，每根骨骼有一个**权重（Weight）**，所有权重的和为1。

**蒙皮公式（单顶点）：**

```
v_final = Σ(i=0 to N-1) w_i * M_skin_i * v_bind
```

其中：
- `v_bind`：顶点在绑定姿态下的模型空间位置
- `w_i`：第i根骨骼的权重，Σw_i = 1
- `M_skin_i`：第i根骨骼的蒙皮矩阵
- `N`：每顶点最大骨骼数（通常4或8）

**蒙皮矩阵的推导：**

这是蒙皮最核心的数学。蒙皮矩阵将顶点从绑定姿态变换到当前动画姿态。

想象一个顶点在绑定姿态下位于模型空间位置 `v_bind`。在绑定姿态时，骨骼i的模型变换矩阵是 `M_bind(i)`。在当前动画姿态下，骨骼i的模型变换矩阵是 `M_curr(i)`。

顶点先被变换到骨骼i的绑定空间（相对于骨骼i的绑定姿态）：
```
v_in_bone_space = M_bind(i)^(-1) * v_bind
```

然后被变换回当前模型空间：
```
v_transformed = M_curr(i) * v_in_bone_space
              = M_curr(i) * M_bind(i)^(-1) * v_bind
```

所以蒙皮矩阵就是：
```
M_skin(i) = M_curr(i) * M_bind(i)^(-1)
```

这个矩阵有一个直观的理解：它表示"从绑定姿态到当前姿态，骨骼i带来了什么变化"。`M_bind(i)^(-1)` 是绑定姿态时骨骼i的逆变换，它将顶点从模型空间变换到骨骼的局部空间；`M_curr(i)` 将顶点从骨骼局部空间变换回当前模型空间。

**矩阵调色板（Matrix Palette）：**

在GPU上，我们预先计算所有骨骼的蒙皮矩阵，存储在一个uniform数组中：

```glsl
uniform mat4 u_boneMatrices[MAX_BONES];
```

这个数组就是"矩阵调色板"。顶点着色器从中取出对应骨骼的矩阵进行变换。

---

### 1.5 双四元数蒙皮（Dual Quaternion Skinning）

标准线性混合蒙皮（Linear Blend Skinning, LBS）有一个严重问题：**糖果包装效应（Candy Wrapper Effect）**。当关节旋转接近180度时，混合后的矩阵可能产生不合理的缩放和剪切，导致肢体看起来被压扁或扭曲。

**问题根源**：矩阵的线性插值不保持旋转的正交性。两个旋转矩阵的线性组合通常不再是纯旋转矩阵。

**双四元数蒙皮（Dual Quaternion Skinning, DQS）** 解决了这个问题。双四元数是四元数的扩展，可以紧凑地表示刚体变换（旋转+平移）：

```
Q = q_r + ε * q_d
```

其中 `q_r` 是实部（普通四元数，表示旋转），`q_d` 是对偶部（表示平移），`ε` 是对偶单位（ε² = 0）。

双四元数的优势：
1. **刚体变换保持**：双四元数混合后仍然是刚体变换，不会产生缩放/剪切伪影
2. **内存友好**：一个双四元数只占8个float，而矩阵需要12个（4x3）或16个（4x4）
3. **计算高效**：GPU上双四元数蒙皮比矩阵蒙皮更快

双四元数蒙皮的混合公式：

```
Q_blend = Σ w_i * Q_i  (其中Q_i是单位双四元数)
```

混合后需要归一化：`Q_blend = Q_blend / ||Q_blend||`

**何时使用DQS：**
- 角色蒙皮，特别是关节处（肘部、膝盖、肩膀）
- 需要避免体积损失的场合

**何时使用LBS：**
- 非刚体变形（如面部动画、软体）
- 需要缩放/剪切效果的动画

---

### 1.6 动画插值：Lerp 与 Slerp

**线性插值（Lerp）**：用于位置和缩放。

```cpp
Vec3 Lerp(const Vec3& a, const Vec3& b, float t) {
    return a * (1.0f - t) + b * t;
}
```

**球面线性插值（Slerp）**：用于四元数旋转。

Slerp沿四元数球面上的大圆弧插值，保证匀速旋转。

```cpp
Quaternion Slerp(const Quaternion& a, const Quaternion& b, float t) {
    float dot = a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;

    // 如果点积为负，反转一个四元数以走最短路径
    Quaternion bPrime = b;
    if (dot < 0.0f) {
        bPrime = -b;
        dot = -dot;
    }

    // 如果四元数非常接近，用Lerp近似（更快且数值稳定）
    const float DOT_THRESHOLD = 0.9995f;
    if (dot > DOT_THRESHOLD) {
        Quaternion result = a + (bPrime - a) * t;
        result.Normalize();
        return result;
    }

    float theta0 = acosf(dot);        // a和b之间的夹角
    float theta = theta0 * t;          // 当前角度
    float sinTheta = sinf(theta);
    float sinTheta0 = sinf(theta0);

    float s0 = cosf(theta) - dot * sinTheta / sinTheta0;
    float s1 = sinTheta / sinTheta0;

    return a * s0 + bPrime * s1;
}
```

**Nlerp（归一化线性插值）**：Slerp的廉价近似。直接用Lerp然后归一化。对于小角度差异几乎看不出区别，且计算快得多。大多数游戏引擎在运行时动画混合中使用Nlerp，只在导出工具中使用精确的Slerp。

**SLERP 中的近似优化**：当两个四元数非常接近时（点积接近 1），SLERP 退化为线性插值（LERP）加归一化。这是因为当夹角很小时，$\sin(\theta) \approx \theta$，SLERP 和 LERP 的结果几乎相同。这个优化在实际项目中很重要，因为大多数相邻关键帧的四元数都很接近。

```cpp
Quaternion Slerp(const Quaternion& a, const Quaternion& b, float t) {
    float dot = a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;
    Quaternion b2 = b;

    // 如果点积为负，反转一个四元数以选择最短路径
    if (dot < 0.0f) {
        b2 = Quaternion(-b.x, -b.y, -b.z, -b.w);
        dot = -dot;
    }

    // 如果四元数非常接近，使用线性插值（更快且足够精确）
    constexpr float DOT_THRESHOLD = 0.9995f;
    if (dot > DOT_THRESHOLD) {
        Quaternion result = Quaternion(
            a.x + t * (b2.x - a.x),
            a.y + t * (b2.y - a.y),
            a.z + t * (b2.z - a.z),
            a.w + t * (b2.w - a.w)
        );
        result.Normalize();
        return result;
    }

    // 标准 SLERP
    float theta_0 = acosf(dot);
    float theta = theta_0 * t;
    float sin_theta = sinf(theta);
    float sin_theta_0 = sinf(theta_0);

    float s0 = cosf(theta) - dot * sin_theta / sin_theta_0;
    float s1 = sin_theta / sin_theta_0;

    return Quaternion(
        a.x * s0 + b2.x * s1,
        a.y * s0 + b2.y * s1,
        a.z * s0 + b2.z * s1,
        a.w * s0 + b2.w * s1
    );
}
```

---

### 1.7 动画混合（Blending）

动画混合让角色能同时表现多个动画，例如上半身射击+下半身奔跑。

**交叉淡入淡出（Crossfade）**：从一个动画平滑过渡到另一个。

```cpp
Pose Crossfade(const Pose& poseA, const Pose& poseB, float t) {
    Pose result;
    for (int i = 0; i < boneCount; ++i) {
        result.positions[i] = Lerp(poseA.positions[i], poseB.positions[i], t);
        result.rotations[i] = Slerp(poseA.rotations[i], poseB.rotations[i], t);
        result.scales[i] = Lerp(poseA.scales[i], poseB.scales[i], t);
    }
    return result;
}
```

**加法混合（Additive Blending）**：将一个动画的"差异"叠加到基础动画上。例如，在 idle 动画上叠加呼吸动画、瞄准偏移（Aim Offset）等。

加法动画的创建方式：从基础姿态（如 idle）减去，只保留差异。运行时：

```cpp
Pose ApplyAdditive(const Pose& basePose, const Pose& additivePose, float weight) {
    Pose result;
    for (int i = 0; i < boneCount; ++i) {
        // 位置：直接叠加
        result.positions[i] = basePose.positions[i] + additivePose.positions[i] * weight;

        // 旋转：四元数乘法叠加
        Quaternion weightedAdditive = Quaternion::Identity().Slerp(additivePose.rotations[i], weight);
        result.rotations[i] = basePose.rotations[i] * weightedAdditive;

        // 缩放
        result.scales[i] = basePose.scales[i] + (additivePose.scales[i] - Vec3(1,1,1)) * weight;
    }
    return result;
}
```

**分层混合（Layered Blending）**：按骨骼掩码（Bone Mask）选择性地混合。例如只混合上半身：

```cpp
Pose LayeredBlend(const Pose& basePose, const Pose& upperBodyPose,
                  const BoneMask& mask) {
    Pose result = basePose;
    for (int i = 0; i < boneCount; ++i) {
        if (mask.IsActive(i)) {
            float w = mask.GetWeight(i);
            result.positions[i] = Lerp(basePose.positions[i], upperBodyPose.positions[i], w);
            result.rotations[i] = Slerp(basePose.rotations[i], upperBodyPose.rotations[i], w);
        }
    }
    return result;
}
```

**混合树（Blend Tree）**：更复杂的混合结构，支持1D/2D混合空间。例如根据速度和方向参数在 idle、walk、run 之间平滑过渡（类似Unity的Blend Tree或UE的BlendSpace）。

**1D Blend Space**：根据单个参数（如速度）在两个或多个动画之间进行线性插值。例如，角色速度为 0 时播放"Idle"动画，速度为 5 m/s 时播放"Walk"动画，速度为 10 m/s 时播放"Run"动画。中间速度值对应的姿势通过相邻动画姿势的 LERP 计算。

**2D Blend Space**：根据两个参数（如速度和方向）在二维平面上混合多个动画。例如：

```
       方向 = -90 (左)
            |
  WalkLeft | WalkForward | WalkRight
            |     (0)     |
速度 = 0 ---+-------------+--- 速度 = 10
   (Idle)  |             |
  RunLeft  |  RunForward | RunRight
            |
       方向 = 90 (右)
```

2D Blend Space 的实现方式是：将各动画样本放置在二维参数空间中，对于当前参数值，找到包围该点的三角形（Delaunay 三角剖分），然后使用**重心坐标（Barycentric Coordinates）**在三个顶点动画之间进行混合。

**Blend Node 类型**：

| Blend Node 类型 | 功能 | 输出公式 | 应用场景 |
|----------------|------|---------|---------|
| Lerp Blend | 两个动画之间的线性插值 | P_out = (1-t) * P_A + t * P_B | 基于参数的基本混合 |
| Additive | 在基础动画上叠加差异 | P_out = P_base + P_additive | 叠加呼吸、受击反应 |
| Override | 完全覆盖指定关节 | 指定关节用新动画替换 | 上半身射击+下半身行走 |
| Masked Blend | 按骨骼遮罩混合 | 遮罩关节用 A，其余用 B | 上下半身分离动画 |

**动画过渡（Transition）**：

动画过渡处理不同动画状态之间的切换。直接切换会导致视觉上的"跳变"，因此需要**过渡混合（Transition Blend）**：在一段时间内（过渡持续时间），从源动画逐渐混合到目标动画。

过渡的混合权重通常使用**平滑步函数（Smoothstep）** 计算：

$$w(t) = 3\left(\frac{t}{T}\right)^2 - 2\left(\frac{t}{T}\right)^3$$

其中 $t$ 是过渡经过的时间，$T$ 是过渡总时长。这个函数在 $t=0$ 时 $w=0$，在 $t=T$ 时 $w=1$，且在两端的变化率为零，产生平滑的加减速效果。

---

### 1.8 动画状态机（Animation State Machine）

动画状态机（Animation State Machine, ASM）是控制动画逻辑的高层结构。它将动画组织为状态，通过过渡（Transition）连接。

```
[Idle State] --(条件: Speed > 0.1)--> [Walk State]
   ^                                        |
   |                                        |
   +----(条件: Speed == 0)------------------+
```

**核心组件：**

- **State（状态）**：一个播放中的动画片段或混合树
- **Transition（过渡）**：状态之间的连接，包含触发条件和过渡时长
- **Parameter（参数）**：控制状态机的变量（float、int、bool、trigger）
- **Layer（层）**：独立运行的状态机层，支持分层混合

**状态机的实现方式：**

1. **简单状态机**：每个状态输出一个Pose，过渡时交叉淡入淡出
2. **分层状态机**：多个层并行运行，按骨骼掩码混合
3. **行为树/动画图**：更复杂的逻辑，支持条件分支、循环、子状态机

**分层动画（Animation Layering）**：

分层动画允许在同一时刻从多个独立的状态机或动画源播放动画，然后按骨骼遮罩（Bone Mask）和层权重进行组合。这在需要上下半身独立控制时非常有用。

例如，角色的下半身（腿、骨盆）由"移动状态机"控制（处理行走、跑步、跳跃），而上半身（躯干、手臂、头部）由"战斗状态机"控制（处理瞄准、射击、换弹）。两个状态机独立运行，最终通过骨骼遮罩混合成最终姿势。

分层动画的混合公式为：

$$\mathbf{P}_{final}^{(i)} = \begin{cases}
\mathbf{P}_{layer1}^{(i)} & \text{if } mask[i] = 1 \text{ and layer1 is active} \\
\mathbf{P}_{layer2}^{(i)} & \text{if } mask[i] = 0 \text{ and layer2 is active} \\
\text{LERP}(\mathbf{P}_{layer1}^{(i)}, \mathbf{P}_{layer2}^{(i)}, w) & \text{if } mask[i] \in (0, 1)
\end{cases}$$

**高级状态机特性**：

- **子状态机（Sub-state Machine）**：将一组相关状态封装为子状态机，简化主状态机的复杂度。例如，将 Grounded 状态内部的所有子状态（Idle、Walk、Run）封装为一个子状态机。
- **AnyState 转换**：定义可以从任何状态触发的转换（如死亡、受击）。
- **转换中断（Transition Interruption）**：允许在过渡过程中被更高优先级的转换打断。

---

### 1.9 逆运动学（Inverse Kinematics, IK）

正向运动学（FK）：给定关节角度，计算末端位置。
逆运动学（IK）：给定末端目标位置，反推关节角度。

IK在游戏中的典型应用：
- **足部IK**：让脚贴合不平地面
- **手部IK**：让手精确抓住门把手、武器
- **头部/视线IK**：让角色注视目标
- **全身IK**：角色攀爬、与环境互动

**两关节IK（Two-Joint IK）**：最常见的IK问题，例如大腿-小腿-脚。可以用解析法（基于余弦定理）精确求解，比迭代法更快更稳定。

```
已知：
  - 髋关节位置 H
  - 目标脚位置 T
  - 大腿长度 l1
  - 小腿长度 l2

求：
  - 膝关节位置 K
  - 大腿旋转角度 θ1
  - 小腿旋转角度 θ2
```

**解析解步骤：**

设三根骨骼的长度分别为 $L_1$（上臂/大腿）、$L_2$（前臂/小腿），末端需要到达的目标位置为 $\mathbf{P}_{target}$，根关节位置为 $\mathbf{P}_{root}$。定义目标到根的距离为：

$$D = |\mathbf{P}_{target} - \mathbf{P}_{root}|$$

**第一步：求解中间关节角度**

中间关节（肘/膝）的弯曲角度 $\theta$ 可以用余弦定理求解：

$$D^2 = L_1^2 + L_2^2 - 2 L_1 L_2 \cos(\pi - \theta)$$

$$\cos(\theta) = \frac{D^2 - L_1^2 - L_2^2}{2 L_1 L_2}$$

$$\theta = \arccos\left(\frac{D^2 - L_1^2 - L_2^2}{2 L_1 L_2}\right)$$

如果 $D > L_1 + L_2$，目标超出了可达范围，需要归一化到最远点。

**第二步：求解根关节旋转**

根关节需要将第一根骨骼对准目标方向。设目标方向为 $\mathbf{d} = \frac{\mathbf{P}_{target} - \mathbf{P}_{root}}{|\mathbf{P}_{target} - \mathbf{P}_{root}|}$。

在绑定姿势下，第一根骨骼的朝向为 $\mathbf{d}_{bind}$。根关节的旋转为将 $\mathbf{d}_{bind}$ 对齐到 $\mathbf{d}$ 的旋转。

**第三步：应用极向量（Pole Vector）**

**极向量（Pole Vector）** 或 **扭转轴（Twist Axis）** 控制中间关节的弯曲方向。在双骨骼 IK 中，三根骨骼始终位于一个由根位置、目标位置和极向量定义的平面内。极向量通常设置为垂直于地面的方向（如角色的上方），使膝盖或肘部朝正确的方向弯曲。

**CCD IK（Cyclic Coordinate Descent）**：迭代算法，从末端关节向根关节逐次调整，每次让一个关节朝向目标。简单、稳定，适合多关节链。

CCD 算法的工作流程：

1. 从末端关节开始，向根关节方向依次处理每个关节。
2. 对于每个关节，计算使下一关节（沿链向末端方向）更接近目标位置的旋转。
3. 重复步骤 1-2 直到末端关节足够接近目标，或达到最大迭代次数。

单个关节的旋转计算使用简单的几何方法：从当前关节到末端的向量为 $\mathbf{v}_1$，从当前关节到目标的向量为 $\mathbf{v}_2$，关节的旋转就是将 $\mathbf{v}_1$ 对齐到 $\mathbf{v}_2$ 的旋转。

**FABRIK（Forward And Backward Reaching IK）**：另一种迭代算法，先正向（从根到末端）再反向（从末端到根）调整关节位置，最后恢复骨骼长度。比CCD更自然，收敛更快。

FABRIK 的优势在于：

- **不收玫到局部最优**：与 CCD 不同，FABRIK 通常能收敛到全局最优解。
- **直观**：操作的是位置而非角度，更容易理解和调试。
- **支持约束**：可以很容易地添加关节角度限制。

FABRIK 算法步骤：

1. **Forward Reaching（正向到达）**：从末端开始，将末端放到目标位置，然后依次将前面的关节放在保持骨骼长度不变的最近位置。
2. **Backward Reaching（反向到达）**：从根关节开始，将根关节放回原始位置，然后依次将后面的关节放在保持骨骼长度不变的最近位置。
3. 重复步骤 1-2 直到收敛。

---

### 1.10 动画压缩

原始动画数据量巨大。一个60fps、30秒的动画，100根骨骼，每骨骼3个位置+4个旋转+3个缩放 = 10个float/帧/骨骼：

```
100 bones * 10 floats * 4 bytes * 60 fps * 30 sec = 72 MB
```

这只是一个动画片段！现代游戏有数千个动画，必须压缩。

**常用压缩技术：**

1. **曲线采样与关键帧精简**：移除对曲线形状影响小的关键帧。使用误差阈值判断哪些关键帧可以删除。

2. **浮点量化**：将float32压缩为更低位数：
   - 位置：通常16位定点数足够（毫米级精度）
   - 旋转：四元数分量可以量化为16位或甚至8位
   - 缩放：通常变化小，可以更高压缩率

3. **曲线拟合**：用少量控制点的贝塞尔曲线或B样条近似原始动画曲线。

4. **逐骨骼误差控制**：不同骨骼对视觉误差的敏感度不同。手指需要高精度，而躯干可以容忍更大误差。

5. **Additive动画压缩**：加法动画通常幅度小，可以用更高压缩率。

现代引擎（UE5、Unity）的动画压缩系统通常支持多种压缩方案，根据骨骼和通道类型自动选择最优方案。

#### 浮点量化

**浮点量化（Floating-point Quantization）** 是最基础的压缩方法。骨骼的平移和旋转通常用 32 位浮点数存储，但实际精度需求远低于此。

- **平移**：关节的平移范围通常有限（在人体骨骼范围内），可以用 16 位定点数表示，将误差控制在亚毫米级别。
- **旋转**：四元数有 4 个分量，但由于 $x^2 + y^2 + z^2 + w^2 = 1$，只存储 3 个分量，第 4 个通过开方恢复。每个分量可以用 16 位整数表示，将 $[-1, 1]$ 映射到 $[-32768, 32767]$。

Unreal Engine 使用的压缩格式 **Additive Animations** 将动画姿势存储为相对于绑定姿势的差异，差异值通常更小，因此可以用更低的精度表示。

#### 关键帧抽稀（Curve Fitting）

**关键帧抽稀（Keyframe Reduction / Curve Fitting）** 通过移除冗余的关键帧来减少数据量。核心思想是：如果一段动画曲线可以通过相邻关键帧的线性插值（或更高阶插值）在允许误差范围内近似，那么中间的关键帧可以安全移除。

关键帧抽稀算法通常采用**贪心算法**：

1. 保留第一个和最后一个关键帧。
2. 找到当前区间内误差最大的中间关键帧。
3. 如果该最大误差超过阈值，则保留该关键帧，并递归处理左右两个子区间。
4. 如果最大误差低于阈值，则区间内所有中间关键帧都可以移除。

这种方法可以在可控的视觉误差范围内，将关键帧数量减少 50-90%。

#### 动画压缩算法对比

| 压缩方法 | 压缩比 | 解码开销 | 质量损失 | 适用场景 |
|---------|--------|---------|---------|---------|
| 不做压缩 (Raw Floats) | 1x | 无 | 无 | 调试、过场动画 |
| 浮点量化 (16-bit) | ~2x | 极低 | 不可感知 | 所有骨骼动画 |
| 关键帧抽稀 | 2-10x | 低 | 可控 (误差阈值) | 曲线平滑的动画 |
| 逐骨骼自适应精度 | 3-15x | 中 | 不可感知 | 高精度需求项目 |
| 有损变换 (Wavelet) | 5-20x | 中 | 轻微 | 长动画、背景角色 |
| 机器学习压缩 | 10-50x | 高 (GPU) | 轻微 | 未来方向 (研究中) |

**逐骨骼自适应精度**是 Unreal Engine 5 引入的先进压缩方法。其原理基于一个观察：不同关节对视觉误差的敏感度不同。例如，根关节（骨盆）的微小误差会导致整个角色的位置偏移，非常显眼；而手指末端关节的误差几乎不可察觉。因此，可以为每个关节独立设置压缩精度，对视觉敏感的关节使用高精度，对其他关节使用低精度。这种方法可以在几乎不损失视觉质量的情况下达到 5-10 倍的压缩比。

---

## 2. 代码示例

以下是一个完整的C++骨骼动画系统 + GLSL GPU蒙皮着色器。代码使用自包含的数据结构，不依赖特定引擎。

### 2.1 核心数据结构

```cpp
// ============================================================
// Math Primitives
// ============================================================

struct Vec3 {
    float x, y, z;
    Vec3 operator+(const Vec3& o) const { return {x+o.x, y+o.y, z+o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x-o.x, y-o.y, z-o.z}; }
    Vec3 operator*(float s) const { return {x*s, y*s, z*s}; }
};

struct Quaternion {
    float x, y, z, w;
    static Quaternion Identity() { return {0,0,0,1}; }
    float Dot(const Quaternion& o) const {
        return x*o.x + y*o.y + z*o.z + w*o.w;
    }
    Quaternion operator+(const Quaternion& o) const {
        return {x+o.x, y+o.y, z+o.z, w+o.w};
    }
    Quaternion operator*(float s) const {
        return {x*s, y*s, z*s, w*s};
    }
    Quaternion operator-() const {
        return {-x, -y, -z, -w};
    }
    float Length() const {
        return sqrtf(x*x + y*y + z*z + w*w);
    }
    void Normalize() {
        float len = Length();
        if (len > 0.0001f) {
            x /= len; y /= len; z /= len; w /= len;
        }
    }
    // Quaternion multiplication (this * o)
    Quaternion operator*(const Quaternion& o) const {
        return {
            w*o.x + x*o.w + y*o.z - z*o.y,
            w*o.y - x*o.z + y*o.w + z*o.x,
            w*o.z + x*o.y - y*o.x + z*o.w,
            w*o.w - x*o.x - y*o.y - z*o.z
        };
    }
    // Rotate a vector
    Vec3 Rotate(const Vec3& v) const {
        // q * v * q^-1
        Quaternion qv = {v.x, v.y, v.z, 0};
        Quaternion qConj = {-x, -y, -z, w};
        Quaternion result = (*this) * qv * qConj;
        return {result.x, result.y, result.z};
    }
};

// 4x4 Matrix (column-major, OpenGL style)
struct Mat4 {
    float m[16];
    static Mat4 Identity() {
        Mat4 r = {};
        r.m[0] = r.m[5] = r.m[10] = r.m[15] = 1.0f;
        return r;
    }
    static Mat4 FromTRS(const Vec3& t, const Quaternion& r, const Vec3& s) {
        // Convert quaternion to rotation matrix
        float xx = r.x * r.x, yy = r.y * r.y, zz = r.z * r.z;
        float xy = r.x * r.y, xz = r.x * r.z, yz = r.y * r.z;
        float wx = r.w * r.x, wy = r.w * r.y, wz = r.w * r.z;

        Mat4 result = {};
        result.m[0]  = (1.0f - 2.0f * (yy + zz)) * s.x;
        result.m[1]  = (2.0f * (xy + wz)) * s.x;
        result.m[2]  = (2.0f * (xz - wy)) * s.x;
        result.m[3]  = 0.0f;

        result.m[4]  = (2.0f * (xy - wz)) * s.y;
        result.m[5]  = (1.0f - 2.0f * (xx + zz)) * s.y;
        result.m[6]  = (2.0f * (yz + wx)) * s.y;
        result.m[7]  = 0.0f;

        result.m[8]  = (2.0f * (xz + wy)) * s.z;
        result.m[9]  = (2.0f * (yz - wx)) * s.z;
        result.m[10] = (1.0f - 2.0f * (xx + yy)) * s.z;
        result.m[11] = 0.0f;

        result.m[12] = t.x;
        result.m[13] = t.y;
        result.m[14] = t.z;
        result.m[15] = 1.0f;
        return result;
    }
    Mat4 operator*(const Mat4& o) const {
        Mat4 r = {};
        for (int i = 0; i < 4; ++i) {
            for (int j = 0; j < 4; ++j) {
                for (int k = 0; k < 4; ++k) {
                    r.m[i + j*4] += m[i + k*4] * o.m[k + j*4];
                }
            }
        }
        return r;
    }
    Vec3 TransformPoint(const Vec3& v) const {
        float x = m[0]*v.x + m[4]*v.y + m[8]*v.z + m[12];
        float y = m[1]*v.x + m[5]*v.y + m[9]*v.z + m[13];
        float z = m[2]*v.x + m[6]*v.y + m[10]*v.z + m[14];
        float w = m[3]*v.x + m[7]*v.y + m[11]*v.z + m[15];
        return {x/w, y/w, z/w};
    }
    Mat4 Inverted() const {
        // Simplified: assumes affine transform (no perspective)
        // Extract rotation/scale, transpose for inverse
        // Extract translation, negate and transform by inverse rotation
        Mat4 inv = {};
        // Inverse of upper 3x3 = transpose (for orthonormal) or full inverse
        // For general affine: compute cofactor matrix / determinant
        // Here we do a simplified version for rigid transforms
        inv.m[0] = m[0]; inv.m[4] = m[1]; inv.m[8] = m[2];
        inv.m[1] = m[4]; inv.m[5] = m[5]; inv.m[9] = m[6];
        inv.m[2] = m[8]; inv.m[6] = m[9]; inv.m[10] = m[10];
        Vec3 t = {m[12], m[13], m[14]};
        inv.m[12] = -(inv.m[0]*t.x + inv.m[4]*t.y + inv.m[8]*t.z);
        inv.m[13] = -(inv.m[1]*t.x + inv.m[5]*t.y + inv.m[9]*t.z);
        inv.m[14] = -(inv.m[2]*t.x + inv.m[6]*t.y + inv.m[10]*t.z);
        inv.m[15] = 1.0f;
        return inv;
    }
};

// ============================================================
// Skeleton
// ============================================================

static const int MAX_BONES = 128;
static const int MAX_BONE_INFLUENCES = 4;

struct Bone {
    char name[64];
    int parentIndex;  // -1 for root
    Mat4 bindPoseLocal;   // Local transform in bind pose
    Mat4 bindPoseModel;   // Model-space transform in bind pose (precomputed)
    Mat4 bindPoseInverse; // Inverse of bindPoseModel (precomputed)
};

struct Skeleton {
    Bone bones[MAX_BONES];
    int boneCount;

    // Precompute model-space bind pose and inverse bind pose matrices
    void ComputeBindPoseMatrices() {
        for (int i = 0; i < boneCount; ++i) {
            if (bones[i].parentIndex == -1) {
                bones[i].bindPoseModel = bones[i].bindPoseLocal;
            } else {
                bones[i].bindPoseModel = bones[i].bindPoseLocal *
                                         bones[bones[i].parentIndex].bindPoseModel;
            }
            bones[i].bindPoseInverse = bones[i].bindPoseModel.Inverted();
        }
    }

    int FindBoneIndex(const char* name) const {
        for (int i = 0; i < boneCount; ++i) {
            if (strcmp(bones[i].name, name) == 0) return i;
        }
        return -1;
    }
};

// ============================================================
// Pose
// ============================================================

struct Pose {
    Vec3 positions[MAX_BONES];
    Quaternion rotations[MAX_BONES];
    Vec3 scales[MAX_BONES];

    void SetIdentity(int boneCount) {
        for (int i = 0; i < boneCount; ++i) {
            positions[i] = {0,0,0};
            rotations[i] = Quaternion::Identity();
            scales[i] = {1,1,1};
        }
    }

    // Convert pose to model-space matrices
    void ComputeModelMatrices(const Skeleton& skeleton, Mat4 outMatrices[MAX_BONES]) const {
        for (int i = 0; i < skeleton.boneCount; ++i) {
            Mat4 local = Mat4::FromTRS(positions[i], rotations[i], scales[i]);
            if (skeleton.bones[i].parentIndex == -1) {
                outMatrices[i] = local;
            } else {
                outMatrices[i] = local * outMatrices[skeleton.bones[i].parentIndex];
            }
        }
    }
};

// ============================================================
// Animation Clip
// ============================================================

struct Keyframe {
    float time;
    Vec3 value;        // For position/scale
    Quaternion qvalue; // For rotation
};

enum class TrackType { Position, Rotation, Scale };

struct Track {
    int boneIndex;
    TrackType type;
    Keyframe* keyframes;
    int keyframeCount;

    // Sample the track at given time (assumes keyframes sorted by time)
    void Sample(float time, Vec3& outVec, Quaternion& outQuat) const {
        if (keyframeCount == 0) return;
        if (keyframeCount == 1) {
            outVec = keyframes[0].value;
            outQuat = keyframes[0].qvalue;
            return;
        }

        // Find surrounding keyframes
        int frame = 0;
        for (int i = 0; i < keyframeCount - 1; ++i) {
            if (time >= keyframes[i].time && time < keyframes[i+1].time) {
                frame = i;
                break;
            }
        }
        // Handle wrap-around for looping
        if (time >= keyframes[keyframeCount-1].time) {
            frame = keyframeCount - 2;
        }

        const Keyframe& k0 = keyframes[frame];
        const Keyframe& k1 = keyframes[frame + 1];
        float dt = k1.time - k0.time;
        float t = (dt > 0.0001f) ? (time - k0.time) / dt : 0.0f;

        if (type == TrackType::Rotation) {
            outQuat = Slerp(k0.qvalue, k1.qvalue, t);
        } else {
            outVec = Lerp(k0.value, k1.value, t);
        }
    }
};

struct AnimationClip {
    char name[64];
    float duration;     // in seconds
    float frameRate;
    Track* tracks;
    int trackCount;

    // Sample the animation at given time, output a pose
    void Sample(float time, const Skeleton& skeleton, Pose& outPose) const {
        // Loop the animation
        float loopedTime = fmodf(time, duration);
        if (loopedTime < 0) loopedTime += duration;

        // Initialize pose to bind pose (identity local transforms)
        outPose.SetIdentity(skeleton.boneCount);

        for (int i = 0; i < trackCount; ++i) {
            const Track& track = tracks[i];
            int boneIdx = track.boneIndex;

            Vec3 vec;
            Quaternion quat;
            track.Sample(loopedTime, vec, quat);

            switch (track.type) {
                case TrackType::Position:
                    outPose.positions[boneIdx] = vec;
                    break;
                case TrackType::Rotation:
                    outPose.rotations[boneIdx] = quat;
                    break;
                case TrackType::Scale:
                    outPose.scales[boneIdx] = vec;
                    break;
            }
        }
    }
};

// ============================================================
// Skinning: Compute Matrix Palette
// ============================================================

void ComputeMatrixPalette(
    const Skeleton& skeleton,
    const Pose& pose,
    Mat4 outSkinMatrices[MAX_BONES])
{
    // Step 1: Compute current model-space matrices from pose
    Mat4 currModelMatrices[MAX_BONES];
    pose.ComputeModelMatrices(skeleton, currModelMatrices);

    // Step 2: Compute skinning matrix for each bone
    // M_skin = M_curr_model * M_bind_inverse
    for (int i = 0; i < skeleton.boneCount; ++i) {
        outSkinMatrices[i] = skeleton.bones[i].bindPoseInverse * currModelMatrices[i];
        // Note: With column vectors and column-major matrices:
        // v' = M_skin * v_bind
        // M_skin = M_bind_inv * M_curr (if we pre-multiply)
        // Actually: v_bind -> bone space: M_bind_inv * v_bind
        //           bone space -> curr model: M_curr * (M_bind_inv * v_bind)
        // So M_skin = M_curr * M_bind_inv? No wait...
        //
        // Let's re-derive with column vectors (v' = M * v):
        // v_bind is in model space (bind pose)
        // To get it into bone i's local space in bind pose:
        //   v_bone_local = M_bind_inv(i) * v_bind
        // To transform from bone local to current model space:
        //   v_curr = M_curr_model(i) * v_bone_local
        //          = M_curr_model(i) * M_bind_inv(i) * v_bind
        //
        // So skin matrix = M_curr_model(i) * M_bind_inv(i)
        // But matrix multiplication order depends on convention.
        // In our Mat4::operator*, we do standard matrix multiply.
        // With column vectors: v' = A * B * v means apply B then A.
        // So we want: out = currModel * bindInv
        outSkinMatrices[i] = currModelMatrices[i] * skeleton.bones[i].bindPoseInverse;
    }
}

// ============================================================
// Animation Blending
// ============================================================

Pose BlendPoses(const Pose& a, const Pose& b, float t, int boneCount) {
    Pose result;
    for (int i = 0; i < boneCount; ++i) {
        result.positions[i] = Lerp(a.positions[i], b.positions[i], t);
        result.rotations[i] = Nlerp(a.rotations[i], b.rotations[i], t);
        result.scales[i] = Lerp(a.scales[i], b.scales[i], t);
    }
    return result;
}

// ============================================================
// Two-Joint IK (Analytic)
// ============================================================

struct IKResult {
    Quaternion hipRotation;
    Quaternion kneeRotation;
};

// Solve two-joint IK for a leg: hip -> knee -> ankle
// hipPos: current hip position in model space
// kneePos: current knee position in model space
// anklePos: current ankle position in model space
// targetAnkle: desired ankle position in model space
// hipToKneeLen: length of upper leg (thigh)
// kneeToAnkleLen: length of lower leg (shin)
// Returns rotations for hip and knee joints
IKResult SolveTwoJointIK(
    const Vec3& hipPos,
    const Vec3& kneePos,
    const Vec3& anklePos,
    const Vec3& targetAnkle,
    float hipToKneeLen,
    float kneeToAnkleLen)
{
    IKResult result = {Quaternion::Identity(), Quaternion::Identity()};

    Vec3 toTarget = {targetAnkle.x - hipPos.x, targetAnkle.y - hipPos.y, targetAnkle.z - hipPos.z};
    float targetDist = sqrtf(toTarget.x*toTarget.x + toTarget.y*toTarget.y + toTarget.z*toTarget.z);

    // Clamp to reachable range
    float maxReach = hipToKneeLen + kneeToAnkleLen;
    float minReach = fabsf(hipToKneeLen - kneeToAnkleLen);
    if (targetDist > maxReach) targetDist = maxReach;
    if (targetDist < minReach) targetDist = minReach;

    // Law of cosines to find knee angle
    // c² = a² + b² - 2ab*cos(C)
    // targetDist² = thigh² + shin² - 2*thigh*shin*cos(π - kneeBend)
    // cos(π - kneeBend) = (thigh² + shin² - targetDist²) / (2*thigh*shin)
    // -cos(kneeBend) = ...
    // cos(kneeBend) = (targetDist² - thigh² - shin²) / (2*thigh*shin)
    float cosKnee = (targetDist*targetDist - hipToKneeLen*hipToKneeLen
                     - kneeToAnkleLen*kneeToAnkleLen) / (2.0f * hipToKneeLen * kneeToAnkleLen);
    cosKnee = fmaxf(-1.0f, fminf(1.0f, cosKnee));
    float kneeAngle = acosf(cosKnee);

    // Knee rotation is around the bend axis (perpendicular to leg plane)
    // For simplicity, we rotate around the X axis (assuming leg bends forward)
    // In a real implementation, you'd determine the bend axis from skeleton data
    result.kneeRotation = QuaternionFromAxisAngle({1,0,0}, kneeAngle);

    // Hip rotation: need to rotate the leg to point toward target
    // This is a simplified version - real implementation needs proper axis computation
    Vec3 currentLegDir = {anklePos.x - hipPos.x, anklePos.y - hipPos.y, anklePos.z - hipPos.z};
    Vec3 targetLegDir = toTarget;
    // Normalize
    float currLen = sqrtf(currentLegDir.x*currentLegDir.x + currentLegDir.y*currentLegDir.y + currentLegDir.z*currentLegDir.z);
    float targLen = sqrtf(targetLegDir.x*targetLegDir.x + targetLegDir.y*targetLegDir.y + targetLegDir.z*targetLegDir.z);
    if (currLen > 0.0001f && targLen > 0.0001f) {
        currentLegDir.x /= currLen; currentLegDir.y /= currLen; currentLegDir.z /= currLen;
        targetLegDir.x /= targLen; targetLegDir.y /= targLen; targetLegDir.z /= targLen;

        // Rotation from current to target
        Vec3 axis = Cross(currentLegDir, targetLegDir);
        float axisLen = sqrtf(axis.x*axis.x + axis.y*axis.y + axis.z*axis.z);
        if (axisLen > 0.0001f) {
            axis.x /= axisLen; axis.y /= axisLen; axis.z /= axisLen;
            float dot = currentLegDir.x*targetLegDir.x + currentLegDir.y*targetLegDir.y + currentLegDir.z*targetLegDir.z;
            dot = fmaxf(-1.0f, fminf(1.0f, dot));
            float angle = acosf(dot);
            result.hipRotation = QuaternionFromAxisAngle(axis, angle);
        }
    }

    return result;
}

// Helper: axis-angle to quaternion
Quaternion QuaternionFromAxisAngle(const Vec3& axis, float angle) {
    float half = angle * 0.5f;
    float s = sinf(half);
    return {axis.x * s, axis.y * s, axis.z * s, cosf(half)};
}

Vec3 Cross(const Vec3& a, const Vec3& b) {
    return {
        a.y*b.z - a.z*b.y,
        a.z*b.x - a.x*b.z,
        a.x*b.y - a.y*b.x
    };
}

// ============================================================
// CCD IK (Cyclic Coordinate Descent)
// ============================================================

// 计算将 fromDir 旋转到 toDir 所需的四元数
Quaternion RotationFromTo(const Vec3& fromDir, const Vec3& toDir) {
    Vec3 from = fromDir;  // 假设已归一化
    Vec3 to = toDir;      // 假设已归一化

    float cosTheta = from.x * to.x + from.y * to.y + from.z * to.z;
    if (cosTheta > 0.9999f) {
        return Quaternion::Identity();  // 方向相同，无需旋转
    }
    if (cosTheta < -0.9999f) {
        // 方向相反，需要 180 度旋转
        Vec3 axis = (fabsf(from.x) < 0.9f) ? Vec3{1, 0, 0} : Vec3{0, 1, 0};
        axis = Cross(from, axis);
        float axisLen = sqrtf(axis.x*axis.x + axis.y*axis.y + axis.z*axis.z);
        if (axisLen > 1e-6f) {
            axis.x /= axisLen; axis.y /= axisLen; axis.z /= axisLen;
        }
        return QuaternionFromAxisAngle(axis, 3.14159265f);
    }

    Vec3 axis = Cross(from, to);
    float axisLen = sqrtf(axis.x*axis.x + axis.y*axis.y + axis.z*axis.z);
    if (axisLen > 1e-6f) {
        axis.x /= axisLen; axis.y /= axisLen; axis.z /= axisLen;
    }
    float angle = acosf(fmaxf(-1.0f, fminf(1.0f, cosTheta)));
    return QuaternionFromAxisAngle(axis, angle);
}

// CCD IK 求解器
// joints: 从根到末端的关节位置列表（根关节在索引 0）
// target: IK 目标位置
// maxIterations: 最大迭代次数
// threshold: 收敛阈值（末端到目标的距离）
bool SolveCCDIK(
    Vec3* joints,
    int jointCount,
    const Vec3& target,
    int maxIterations = 10,
    float threshold = 0.01f)
{
    if (jointCount < 2) return false;

    Vec3 rootPosition = joints[0];
    float totalChainLength = 0.0f;
    float* boneLengths = new float[jointCount - 1];
    for (int i = 0; i < jointCount - 1; ++i) {
        Vec3 diff = {joints[i+1].x - joints[i].x, joints[i+1].y - joints[i].y, joints[i+1].z - joints[i].z};
        boneLengths[i] = sqrtf(diff.x*diff.x + diff.y*diff.y + diff.z*diff.z);
        totalChainLength += boneLengths[i];
    }

    // 可达性检查
    Vec3 rootToTarget = {target.x - rootPosition.x, target.y - rootPosition.y, target.z - rootPosition.z};
    float rootToTargetDist = sqrtf(rootToTarget.x*rootToTarget.x + rootToTarget.y*rootToTarget.y + rootToTarget.z*rootToTarget.z);
    if (rootToTargetDist > totalChainLength) {
        delete[] boneLengths;
        return false;  // 目标不可达
    }

    for (int iter = 0; iter < maxIterations; ++iter) {
        // 检查是否收敛
        Vec3 endToTarget = {target.x - joints[jointCount-1].x, target.y - joints[jointCount-1].y, target.z - joints[jointCount-1].z};
        float endToTargetDist = sqrtf(endToTarget.x*endToTarget.x + endToTarget.y*endToTarget.y + endToTarget.z*endToTarget.z);
        if (endToTargetDist < threshold) {
            delete[] boneLengths;
            return true;  // 已收敛
        }

        // CCD 核心: 从末端关节开始，逐个关节旋转
        for (int i = jointCount - 2; i >= 0; --i) {
            // 从当前关节到末端的向量
            Vec3 jointToEnd = {joints[jointCount-1].x - joints[i].x, joints[jointCount-1].y - joints[i].y, joints[jointCount-1].z - joints[i].z};
            float jointToEndLen = sqrtf(jointToEnd.x*jointToEnd.x + jointToEnd.y*jointToEnd.y + jointToEnd.z*jointToEnd.z);
            if (jointToEndLen < 1e-6f) continue;
            jointToEnd.x /= jointToEndLen; jointToEnd.y /= jointToEndLen; jointToEnd.z /= jointToEndLen;

            // 从当前关节到目标的向量
            Vec3 jointToTarget = {target.x - joints[i].x, target.y - joints[i].y, target.z - joints[i].z};
            float jointToTargetLen = sqrtf(jointToTarget.x*jointToTarget.x + jointToTarget.y*jointToTarget.y + jointToTarget.z*jointToTarget.z);
            if (jointToTargetLen < 1e-6f) continue;
            jointToTarget.x /= jointToTargetLen; jointToTarget.y /= jointToTargetLen; jointToTarget.z /= jointToTargetLen;

            // 计算旋转
            Quaternion rot = RotationFromTo(jointToEnd, jointToTarget);

            // 应用旋转到当前关节之后的所有关节
            // 简化：重新计算关节位置（保持骨骼长度不变）
            for (int j = i + 1; j < jointCount; ++j) {
                Vec3 offset = {joints[j].x - joints[i].x, joints[j].y - joints[i].y, joints[j].z - joints[i].z};
                // 使用四元数旋转向量
                Quaternion qv = {offset.x, offset.y, offset.z, 0};
                Quaternion qConj = {-rot.x, -rot.y, -rot.z, rot.w};
                Quaternion qRotated = rot * qv * qConj;
                joints[j].x = joints[i].x + qRotated.x;
                joints[j].y = joints[i].y + qRotated.y;
                joints[j].z = joints[i].z + qRotated.z;
            }
        }
    }

    delete[] boneLengths;

    // 最终检查
    Vec3 finalEndToTarget = {target.x - joints[jointCount-1].x, target.y - joints[jointCount-1].y, target.z - joints[jointCount-1].z};
    float finalDist = sqrtf(finalEndToTarget.x*finalEndToTarget.x + finalEndToTarget.y*finalEndToTarget.y + finalEndToTarget.z*finalEndToTarget.z);
    return finalDist < threshold * 10.0f;  // 放宽阈值
}

// ============================================================
// FABRIK (Forward And Backward Reaching IK)
// ============================================================

bool SolveFABRIK(
    Vec3* joints,
    int jointCount,
    const Vec3& target,
    int maxIterations = 10,
    float threshold = 0.01f)
{
    if (jointCount < 2) return false;

    // 保存原始根位置
    Vec3 rootPos = joints[0];

    // 预计算骨骼长度
    float* boneLengths = new float[jointCount - 1];
    float totalChainLength = 0.0f;
    for (int i = 0; i < jointCount - 1; ++i) {
        Vec3 diff = {joints[i+1].x - joints[i].x, joints[i+1].y - joints[i].y, joints[i+1].z - joints[i].z};
        boneLengths[i] = sqrtf(diff.x*diff.x + diff.y*diff.y + diff.z*diff.z);
        totalChainLength += boneLengths[i];
    }

    // 可达性检查
    Vec3 rootToTarget = {target.x - rootPos.x, target.y - rootPos.y, target.z - rootPos.z};
    float rootToTargetDist = sqrtf(rootToTarget.x*rootToTarget.x + rootToTarget.y*rootToTarget.y + rootToTarget.z*rootToTarget.z);
    if (rootToTargetDist > totalChainLength) {
        // 目标不可达，将链拉伸到目标方向
        Vec3 dir = {rootToTarget.x / rootToTargetDist, rootToTarget.y / rootToTargetDist, rootToTarget.z / rootToTargetDist};
        for (int i = 1; i < jointCount; ++i) {
            joints[i].x = joints[i-1].x + dir.x * boneLengths[i-1];
            joints[i].y = joints[i-1].y + dir.y * boneLengths[i-1];
            joints[i].z = joints[i-1].z + dir.z * boneLengths[i-1];
        }
        delete[] boneLengths;
        return false;
    }

    for (int iter = 0; iter < maxIterations; ++iter) {
        // 检查是否收敛
        Vec3 endToTarget = {target.x - joints[jointCount-1].x, target.y - joints[jointCount-1].y, target.z - joints[jointCount-1].z};
        float endToTargetDist = sqrtf(endToTarget.x*endToTarget.x + endToTarget.y*endToTarget.y + endToTarget.z*endToTarget.z);
        if (endToTargetDist < threshold) {
            delete[] boneLengths;
            return true;
        }

        // Forward Reaching: 从末端到根
        joints[jointCount - 1] = target;
        for (int i = jointCount - 2; i >= 0; --i) {
            Vec3 dir = {joints[i].x - joints[i+1].x, joints[i].y - joints[i+1].y, joints[i].z - joints[i+1].z};
            float dist = sqrtf(dir.x*dir.x + dir.y*dir.y + dir.z*dir.z);
            if (dist > 1e-6f) {
                float ratio = boneLengths[i] / dist;
                joints[i].x = joints[i+1].x + dir.x * ratio;
                joints[i].y = joints[i+1].y + dir.y * ratio;
                joints[i].z = joints[i+1].z + dir.z * ratio;
            }
        }

        // Backward Reaching: 从根到末端
        joints[0] = rootPos;
        for (int i = 0; i < jointCount - 1; ++i) {
            Vec3 dir = {joints[i+1].x - joints[i].x, joints[i+1].y - joints[i].y, joints[i+1].z - joints[i].z};
            float dist = sqrtf(dir.x*dir.x + dir.y*dir.y + dir.z*dir.z);
            if (dist > 1e-6f) {
                float ratio = boneLengths[i] / dist;
                joints[i+1].x = joints[i].x + dir.x * ratio;
                joints[i+1].y = joints[i].y + dir.y * ratio;
                joints[i+1].z = joints[i].z + dir.z * ratio;
            }
        }
    }

    delete[] boneLengths;

    Vec3 finalEndToTarget = {target.x - joints[jointCount-1].x, target.y - joints[jointCount-1].y, target.z - joints[jointCount-1].z};
    float finalDist = sqrtf(finalEndToTarget.x*finalEndToTarget.x + finalEndToTarget.y*finalEndToTarget.y + finalEndToTarget.z*finalEndToTarget.z);
    return finalDist < threshold * 10.0f;
}

// ============================================================
// Mesh with Skinning Data
// ============================================================

struct SkinnedVertex {
    Vec3 position;          // Bind pose position in model space
    Vec3 normal;
    Vec2 texCoord;
    uint8_t boneIndices[MAX_BONE_INFLUENCES];  // Which bones affect this vertex
    float boneWeights[MAX_BONE_INFLUENCES];    // Weights (sum to 1.0)
};

struct SkinnedMesh {
    SkinnedVertex* vertices;
    int vertexCount;
    uint32_t* indices;
    int indexCount;
};

// CPU-side skinning (for reference / software rendering)
void SkinMeshCPU(
    const SkinnedMesh& mesh,
    const Mat4 skinMatrices[MAX_BONES],
    Vec3* outPositions,
    Vec3* outNormals)
{
    for (int v = 0; v < mesh.vertexCount; ++v) {
        const SkinnedVertex& sv = mesh.vertices[v];
        Vec3 pos = {0,0,0};
        Vec3 normal = {0,0,0};

        for (int i = 0; i < MAX_BONE_INFLUENCES; ++i) {
            if (sv.boneWeights[i] > 0.0f) {
                uint8_t boneIdx = sv.boneIndices[i];
                float weight = sv.boneWeights[i];

                // Transform position by skin matrix
                Vec3 p = skinMatrices[boneIdx].TransformPoint(sv.position);
                pos.x += p.x * weight;
                pos.y += p.y * weight;
                pos.z += p.z * weight;

                // Transform normal (ignore translation, use upper 3x3)
                // For proper normal transformation with non-uniform scale,
                // we'd use inverse-transpose of upper 3x3
                Mat4 m = skinMatrices[boneIdx];
                Vec3 n = {
                    m.m[0]*sv.normal.x + m.m[4]*sv.normal.y + m.m[8]*sv.normal.z,
                    m.m[1]*sv.normal.x + m.m[5]*sv.normal.y + m.m[9]*sv.normal.z,
                    m.m[2]*sv.normal.x + m.m[6]*sv.normal.y + m.m[10]*sv.normal.z
                };
                normal.x += n.x * weight;
                normal.y += n.y * weight;
                normal.z += n.z * weight;
            }
        }

        outPositions[v] = pos;
        outNormals[v] = normal;
    }
}
```

### 2.2 GLSL GPU 蒙皮着色器

```glsl
// ============================================================
// Vertex Shader - Matrix Palette Skinning
// ============================================================
#version 330 core

// Maximum bones supported
#define MAX_BONES 128

// Input vertex attributes
layout(location = 0) in vec3 a_position;      // Bind pose position
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec2 a_texCoord;
layout(location = 3) in ivec4 a_boneIndices;  // Bone indices (up to 4)
layout(location = 4) in vec4 a_boneWeights;   // Bone weights

// Uniforms
uniform mat4 u_modelMatrix;           // Entity world transform
uniform mat4 u_viewMatrix;
uniform mat4 u_projectionMatrix;
uniform mat4 u_boneMatrices[MAX_BONES];  // Matrix palette (skinning matrices)
uniform mat3 u_normalMatrix;

// Output to fragment shader
out vec3 v_worldPos;
out vec3 v_normal;
out vec2 v_texCoord;

void main() {
    // Skinning: blend vertex position by bone influences
    vec4 skinnedPos = vec4(0.0);
    vec3 skinnedNormal = vec3(0.0);

    for (int i = 0; i < 4; ++i) {
        int boneIdx = a_boneIndices[i];
        float weight = a_boneWeights[i];

        // Skip zero-weight influences
        if (weight > 0.0) {
            mat4 boneMatrix = u_boneMatrices[boneIdx];

            // Transform position
            skinnedPos += boneMatrix * vec4(a_position, 1.0) * weight;

            // Transform normal (use upper 3x3, ignore translation)
            vec3 transformedNormal = mat3(boneMatrix) * a_normal;
            skinnedNormal += transformedNormal * weight;
        }
    }

    // Apply model-world transform
    vec4 worldPos = u_modelMatrix * vec4(skinnedPos.xyz, 1.0);
    v_worldPos = worldPos.xyz;

    // Transform normal to world space
    v_normal = normalize(u_normalMatrix * skinnedNormal);

    // Pass through texture coordinates
    v_texCoord = a_texCoord;

    // Final position
    gl_Position = u_projectionMatrix * u_viewMatrix * worldPos;
}

// ============================================================
// Fragment Shader - Simple Lit
// ============================================================
#version 330 core

in vec3 v_worldPos;
in vec3 v_normal;
in vec2 v_texCoord;

out vec4 fragColor;

uniform vec3 u_lightDir;
uniform vec3 u_lightColor;
uniform vec3 u_ambientColor;
uniform sampler2D u_diffuseTexture;

void main() {
    vec3 normal = normalize(v_normal);
    vec3 lightDir = normalize(-u_lightDir);

    // Diffuse lighting
    float diff = max(dot(normal, lightDir), 0.0);

    // Sample texture
    vec4 texColor = texture(u_diffuseTexture, v_texCoord);

    // Combine ambient + diffuse
    vec3 lighting = u_ambientColor + u_lightColor * diff;
    vec3 finalColor = texColor.rgb * lighting;

    fragColor = vec4(finalColor, texColor.a);
}
```

### 2.3 双四元数蒙皮着色器（GLSL）

```glsl
// ============================================================
// Dual Quaternion Skinning Vertex Shader
// ============================================================
#version 330 core

#define MAX_BONES 128

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec2 a_texCoord;
layout(location = 3) in ivec4 a_boneIndices;
layout(location = 4) in vec4 a_boneWeights;

uniform mat4 u_modelMatrix;
uniform mat4 u_viewMatrix;
uniform mat4 u_projectionMatrix;

// Dual quaternions stored as two vec4s: (rotation_quat, translation_quat)
// Actually a dual quaternion Q = q_r + ε * q_d where |q_r| = 1
// We store q_r in .xyzw and q_d in .xyzw of two consecutive entries
// For simplicity, we use a uniform block or two arrays
uniform vec4 u_dualQuats[MAX_BONES * 2];  // Even: rotation, Odd: dual part

out vec3 v_normal;
out vec2 v_texCoord;

// Quaternion multiplication
vec4 quatMul(vec4 a, vec4 b) {
    return vec4(
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z
    );
}

// Transform a point by a dual quaternion
vec3 dualQuatTransformPoint(vec4 qr, vec4 qd, vec3 p) {
    // v' = qr * (2*qd) * conjugate(qr) + p  [simplified form]
    // More precisely:
    // t = 2 * qd * conjugate(qr)
    // v' = qr * v * conjugate(qr) + t
    // where v = (p, 0) as a quaternion

    vec4 qrc = vec4(-qr.x, -qr.y, -qr.z, qr.w);  // conjugate

    // Rotate point
    vec4 pv = vec4(p, 0.0);
    vec4 rotated = quatMul(quatMul(qr, pv), qrc);

    // Extract translation: t = 2 * qd * conjugate(qr)
    vec4 t = 2.0 * quatMul(qd, qrc);

    return rotated.xyz + t.xyz;
}

// Transform a vector (normal) by dual quaternion (rotation part only)
vec3 dualQuatTransformVector(vec4 qr, vec3 v) {
    vec4 qrc = vec4(-qr.x, -qr.y, -qr.z, qr.w);
    vec4 vv = vec4(v, 0.0);
    vec4 result = quatMul(quatMul(qr, vv), qrc);
    return result.xyz;
}

void main() {
    // Blend dual quaternions
    vec4 blendQr = vec4(0.0);  // Rotation part
    vec4 blendQd = vec4(0.0);  // Dual part

    // First, find the dominant rotation to handle antipodal quaternions
    float maxWeight = a_boneWeights[0];
    int dominantIdx = a_boneIndices[0];

    for (int i = 1; i < 4; ++i) {
        if (a_boneWeights[i] > maxWeight) {
            maxWeight = a_boneWeights[i];
            dominantIdx = a_boneIndices[i];
        }
    }

    vec4 dominantQr = u_dualQuats[dominantIdx * 2];

    for (int i = 0; i < 4; ++i) {
        int idx = a_boneIndices[i];
        float w = a_boneWeights[i];

        if (w > 0.0) {
            vec4 qr = u_dualQuats[idx * 2];
            vec4 qd = u_dualQuats[idx * 2 + 1];

            // Ensure shortest path: flip if dot product with dominant is negative
            if (dot(qr, dominantQr) < 0.0) {
                w = -w;
            }

            blendQr += qr * w;
            blendQd += qd * w;
        }
    }

    // Normalize the blended dual quaternion
    float lenQr = length(blendQr);
    if (lenQr > 0.0001) {
        blendQr /= lenQr;
        blendQd /= lenQr;
    }

    // Ensure qr is unit (should be after normalization but numerical drift happens)
    blendQr = normalize(blendQr);

    // Orthogonalize: qd = qd - (qr·qd)*qr  (ensure qd is orthogonal to qr)
    blendQd = blendQd - dot(blendQr, blendQd) * blendQr;

    // Transform vertex
    vec3 skinnedPos = dualQuatTransformPoint(blendQr, blendQd, a_position);
    vec3 skinnedNormal = dualQuatTransformVector(blendQr, a_normal);

    // Apply world transform
    vec4 worldPos = u_modelMatrix * vec4(skinnedPos, 1.0);
    v_normal = normalize(mat3(u_modelMatrix) * skinnedNormal);
    v_texCoord = a_texCoord;

    gl_Position = u_projectionMatrix * u_viewMatrix * worldPos;
}
```

### 2.4 动画状态机简单实现

```cpp
// ============================================================
// Simple Animation State Machine
// ============================================================

enum class AnimParameterType { Float, Int, Bool, Trigger };

struct AnimParameter {
    char name[32];
    AnimParameterType type;
    union {
        float fValue;
        int iValue;
        bool bValue;
    };
};

struct AnimState {
    char name[32];
    const AnimationClip* clip;
    float playbackSpeed;
    bool loop;
};

struct AnimTransition {
    int fromState;
    int toState;
    float duration;  // Crossfade duration in seconds

    // Condition (simplified: single parameter check)
    char paramName[32];
    enum ConditionType { Greater, Less, Equal, NotEqual, True, False } condition;
    float threshold;

    bool CheckCondition(const AnimParameter* params, int paramCount) const {
        for (int i = 0; i < paramCount; ++i) {
            if (strcmp(params[i].name, paramName) == 0) {
                switch (condition) {
                    case Greater:  return params[i].fValue > threshold;
                    case Less:     return params[i].fValue < threshold;
                    case Equal:    return params[i].iValue == (int)threshold;
                    case NotEqual: return params[i].iValue != (int)threshold;
                    case True:     return params[i].bValue;
                    case False:    return !params[i].bValue;
                }
            }
        }
        return false;
    }
};

struct AnimStateMachine {
    static const int MAX_STATES = 32;
    static const int MAX_TRANSITIONS = 64;
    static const int MAX_PARAMS = 16;

    AnimState states[MAX_STATES];
    int stateCount;

    AnimTransition transitions[MAX_TRANSITIONS];
    int transitionCount;

    AnimParameter parameters[MAX_PARAMS];
    int paramCount;

    int currentState;
    int targetState;
    float stateTime;       // Time in current state
    float transitionTime;  // -1 if not transitioning, else progress [0,1]
    float transitionDuration;

    Pose currentPose;
    Pose sourcePose;       // Pose at start of transition

    void Init() {
        currentState = 0;
        targetState = -1;
        stateTime = 0.0f;
        transitionTime = -1.0f;
        transitionDuration = 0.0f;
    }

    void SetParameterFloat(const char* name, float value) {
        for (int i = 0; i < paramCount; ++i) {
            if (strcmp(parameters[i].name, name) == 0) {
                parameters[i].fValue = value;
                return;
            }
        }
        // Add new
        if (paramCount < MAX_PARAMS) {
            strncpy(parameters[paramCount].name, name, 31);
            parameters[paramCount].type = AnimParameterType::Float;
            parameters[paramCount].fValue = value;
            paramCount++;
        }
    }

    void Update(float deltaTime, const Skeleton& skeleton) {
        // Check for transitions
        if (transitionTime < 0.0f) {
            for (int i = 0; i < transitionCount; ++i) {
                const AnimTransition& trans = transitions[i];
                if (trans.fromState == currentState && trans.CheckCondition(parameters, paramCount)) {
                    // Start transition
                    targetState = trans.toState;
                    transitionTime = 0.0f;
                    transitionDuration = trans.duration;

                    // Capture current pose as source
                    states[currentState].clip->Sample(stateTime, skeleton, sourcePose);
                    break;
                }
            }
        }

        if (transitionTime >= 0.0f) {
            // In transition: crossfade
            transitionTime += deltaTime;
            float t = transitionTime / transitionDuration;

            if (t >= 1.0f) {
                // Transition complete
                currentState = targetState;
                targetState = -1;
                transitionTime = -1.0f;
                stateTime = 0.0f;
            } else {
                // Sample both poses and blend
                Pose targetPose;
                states[currentState].clip->Sample(stateTime, skeleton, currentPose);
                states[targetState].clip->Sample(0.0f, skeleton, targetPose);  // Start from beginning

                currentPose = BlendPoses(sourcePose, targetPose, t, skeleton.boneCount);
                stateTime += deltaTime * states[currentState].playbackSpeed;
            }
        } else {
            // Normal playback
            stateTime += deltaTime * states[currentState].playbackSpeed;
            states[currentState].clip->Sample(stateTime, skeleton, currentPose);
        }
    }
};
```

### 2.5 渲染循环示例

```cpp
// ============================================================
// Main Render Loop Integration
// ============================================================

void RenderSkinnedCharacter(
    const Skeleton& skeleton,
    AnimStateMachine& stateMachine,
    const SkinnedMesh& mesh,
    GLuint shaderProgram,
    GLuint texture,
    const Mat4& viewMatrix,
    const Mat4& projectionMatrix)
{
    // 1. Update animation state machine
    // (This would be done in the game update loop, not render loop)
    // stateMachine.Update(deltaTime, skeleton);

    // 2. Compute skinning matrices from current pose
    Mat4 skinMatrices[MAX_BONES];
    ComputeMatrixPalette(skeleton, stateMachine.currentPose, skinMatrices);

    // 3. Upload skin matrices to GPU
    GLint boneMatrixLoc = glGetUniformLocation(shaderProgram, "u_boneMatrices");
    glUniformMatrix4fv(boneMatrixLoc, skeleton.boneCount, GL_FALSE,
                       (const GLfloat*)skinMatrices);

    // 4. Set other uniforms
    Mat4 modelMatrix = Mat4::Identity();  // Character world transform
    glUniformMatrix4fv(glGetUniformLocation(shaderProgram, "u_modelMatrix"),
                       1, GL_FALSE, modelMatrix.m);
    glUniformMatrix4fv(glGetUniformLocation(shaderProgram, "u_viewMatrix"),
                       1, GL_FALSE, viewMatrix.m);
    glUniformMatrix4fv(glGetUniformLocation(shaderProgram, "u_projectionMatrix"),
                       1, GL_FALSE, projectionMatrix.m);

    // 5. Bind texture and draw
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, texture);

    glBindVertexArray(mesh.vao);
    glDrawElements(GL_TRIANGLES, mesh.indexCount, GL_UNSIGNED_INT, 0);
}
```

**运行方式:**

本代码是一个自包含的动画系统框架，不依赖特定引擎。要运行完整的渲染示例，你需要：

1. **环境要求**：OpenGL 3.3+，GLFW/GLAD（或类似窗口和加载器），C++17编译器

2. **构建命令（CMake示例）**：
```bash
mkdir build && cd build
cmake ..
cmake --build .
./skeletal_animation_demo
```

3. **数据准备**：你需要一个带骨骼和蒙皮权重的模型文件（如从Blender导出的glTF/FBX），以及相应的动画片段。可以使用开源模型如 [Mixamo](https://www.mixamo.com/) 的角色进行测试。

4. **加载器**：建议使用 [Assimp](https://github.com/assimp/assimp) 库加载带有骨骼动画的模型文件。Assimp会自动解析骨骼层级、绑定姿态、顶点权重和动画关键帧。

5. **最小可运行示例**：如果不加载外部模型，可以用代码程序化生成一个简单的"棍子人"（stick figure）骨骼和网格进行测试。

**预期输出:**

运行后应看到一个带动画的人物模型：
- 角色按照动画片段播放骨骼动画
- 顶点正确跟随骨骼运动，没有撕裂或异常拉伸
- 关节处过渡自然，无"糖果包装"伪影（如果使用了双四元数蒙皮）
- 状态机切换时，动画平滑过渡（交叉淡入淡出）

---

## 3. 练习

### 练习 1: 实现矩阵调色板缓存

在上面的代码中，`ComputeMatrixPalette` 每帧都重新计算所有骨骼的模型空间矩阵。优化这个系统：

1. 为每根骨骼添加一个"脏标记"（dirty flag），只有当骨骼的局部变换改变时才重新计算
2. 利用骨骼层级的特性：如果父骨骼没有变化，子骨骼也不需要重新计算（除非子骨骼自身变化）
3. 测量优化前后的性能差异（可以用一个100根骨骼、1000个顶点的场景测试）

**提示**：脏标记需要沿着骨骼层级传播。如果父骨骼脏了，所有子孙骨骼也都脏了。

### 练习 2: 实现 FABRIK 算法

实现完整的FABRIK（Forward And Backward Reaching IK）算法，用于多关节链（不限于两关节）。

要求：
1. 支持任意数量的关节（至少测试5个关节的链条）
2. 实现迭代收敛，设置最大迭代次数和收敛阈值
3. 添加关节角度限制（例如膝盖只能向一个方向弯曲）
4. 在2D平面上可视化IK求解过程（可以用简单的图形API或输出到控制台）

**FABRIK算法步骤**：
- **Forward reaching**：从末端关节开始，将每个关节向目标方向移动，同时保持骨骼长度不变
- **Backward reaching**：从根关节开始，将每个关节向根位置拉回，同时保持骨骼长度不变
- 重复直到收敛或达到最大迭代次数

### 练习 3: 动画压缩器（可选）

实现一个简单的动画压缩工具：

1. 读取一个未压缩的动画片段（位置+旋转+缩放的关键帧序列）
2. 实现**曲线精简**：对于每条动画曲线，使用误差阈值移除冗余关键帧。一个关键帧是"冗余"的，如果移除它后用线性插值重建的曲线与原始曲线的最大误差小于阈值
3. 实现**浮点量化**：将位置量化为16位定点数，将旋转四元数量化为16位整数（每个分量映射到[-1, 1]区间）
4. 计算压缩比（原始大小 / 压缩后大小）和最大重建误差
5. 测试不同误差阈值对压缩比和视觉质量的影响

**进阶**：实现基于曲线的压缩——用少量控制点的Catmull-Rom样条或贝塞尔曲线拟合原始关键帧序列。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // MatrixPaletteCache.hpp —— 带脏标记的矩阵调色板缓存
>
> struct CachedBone {
>     Bone* bone;
>     bool dirty = true;          // 当前帧是否需要重新计算
>     Mat4 cachedModelMatrix;     // 缓存的模型空间矩阵
> };
>
> class MatrixPaletteCache {
> public:
>     void Initialize(Skeleton* skeleton) {
>         skeleton_ = skeleton;
>         cachedBones_.resize(skeleton->boneCount);
>         for (int i = 0; i < skeleton->boneCount; ++i) {
>             cachedBones_[i].bone = &skeleton->bones[i];
>         }
>         InvalidateAll();  // 初始全部脏
>     }
>
>     // 标记某根骨骼的局部变换已改变
>     void MarkDirty(int boneIndex) {
>         // 脏标记沿层级向下传播：父骨骼脏 → 所有子孙也脏
>         MarkDirtyRecursive(boneIndex);
>     }
>
>     // 计算所有需要更新的骨骼矩阵
>     void ComputeMatrices(const Pose& currentPose,
>                          Mat4 outPalette[MAX_BONES]) {
>         for (int i = 0; i < skeleton_->boneCount; ++i) {
>             ComputeBoneMatrix(i, currentPose);
>             outPalette[i] = cachedBones_[i].cachedModelMatrix;
>         }
>     }
>
> private:
>     void MarkDirtyRecursive(int boneIndex) {
>         if (boneIndex < 0 || boneIndex >= skeleton_->boneCount) return;
>         if (cachedBones_[boneIndex].dirty) return;  // 已标记，剪枝
>
>         cachedBones_[boneIndex].dirty = true;
>         dirtyCount_++;
>
>         // 递归标记所有子骨骼为脏
>         for (int i = 0; i < skeleton_->boneCount; ++i) {
>             if (skeleton_->bones[i].parentIndex == boneIndex) {
>                 MarkDirtyRecursive(i);
>             }
>         }
>     }
>
>     void ComputeBoneMatrix(int index, const Pose& pose) {
>         auto& cb = cachedBones_[index];
>         if (!cb.dirty) return;  // 缓存命中——无需重新计算
>
>         // 计算局部变换矩阵
>         Mat4 local = Mat4::FromTRS(
>             pose.positions[index],
>             pose.rotations[index],
>             pose.scales[index]
>         );
>
>         // 层级累积：M_model = M_local * M_parent
>         int parent = skeleton_->bones[index].parentIndex;
>         if (parent == -1) {
>             cb.cachedModelMatrix = local;
>         } else {
>             // 父骨骼必须先被计算（脏标记保证了这一点）
>             ComputeBoneMatrix(parent, pose);
>             cb.cachedModelMatrix =
>                 local * cachedBones_[parent].cachedModelMatrix;
>         }
>
>         cb.dirty = false;
>         dirtyCount_--;
>     }
>
>     void InvalidateAll() {
>         for (auto& cb : cachedBones_) cb.dirty = true;
>         dirtyCount_ = cachedBones_.size();
>     }
>
>     Skeleton* skeleton_ = nullptr;
>     std::vector<CachedBone> cachedBones_;
>     size_t dirtyCount_ = 0;
> };
>
> // 使用示例
> void AnimateWithCache(Pose& pose, MatrixPaletteCache& cache,
>                       Mat4 palette[MAX_BONES]) {
>     // 只有被动画曲线修改过的骨骼才标记为脏
>     // 假设 AnimationPlayer 知道哪些骨骼被修改
>     cache.MarkDirty(modifiedBoneIndex);
>     cache.ComputeMatrices(pose, palette);
>     // 大部分骨骼命中缓存，无需重新计算
> }
> ```
>
> **性能分析**：对于100根骨骼的场景，如果每帧只有10根骨骼被动画修改，脏标记机制可避免90%的矩阵乘法。脏标记沿层级传播确保了正确性：父骨骼变化→所有子孙也变——这是由层级矩阵累积公式决定的，`M_child = M_local_child × M_parent`，父变了子矩阵必然变。

> [!tip]- 练习 2 参考答案
> ```cpp
> // FABRIK.hpp —— Forward And Backward Reaching IK
>
> #include <vector>
> #include <cmath>
> #include <iostream>
>
> struct IKJoint {
>     float x, y;            // 当前位置
>     float angleMin;        // 角度下限（弧度，0=无限制）
>     float angleMax;        // 角度上限
> };
>
> class FABRIKSolver {
> public:
>     void SetJoints(const std::vector<IKJoint>& joints) {
>         joints_ = joints;
>         // 预计算骨骼长度
>         boneLengths_.resize(joints_.size() - 1);
>         for (size_t i = 0; i < boneLengths_.size(); ++i) {
>             float dx = joints_[i+1].x - joints_[i].x;
>             float dy = joints_[i+1].y - joints_[i].y;
>             boneLengths_[i] = std::sqrt(dx*dx + dy*dy);
>         }
>     }
>
>     // 求解 IK：调整关节位置使末端到达目标
>     // 返回 true 表示收敛
>     bool Solve(float targetX, float targetY,
>                int maxIterations = 20,
>                float tolerance = 0.01f) {
>         if (joints_.empty()) return false;
>
>         int n = (int)joints_.size();
>         const IKJoint& endEffector = joints_[n - 1];
>
>         // 检查是否已达到目标
>         float dx = endEffector.x - targetX;
>         float dy = endEffector.y - targetY;
>         if (std::sqrt(dx*dx + dy*dy) <= tolerance) return true;
>
>         // 检查是否可达
>         float totalLength = 0;
>         for (float len : boneLengths_) totalLength += len;
>         float distToTarget = std::sqrt(
>             (targetX - joints_[0].x) * (targetX - joints_[0].x) +
>             (targetY - joints_[0].y) * (targetY - joints_[0].y)
>         );
>         if (distToTarget > totalLength) {
>             // 不可达：拉伸到最大长度方向
>             for (int i = 0; i < n - 1; ++i) {
>                 float r = std::sqrt(
>                     (targetX - joints_[i].x) * (targetX - joints_[i].x) +
>                     (targetY - joints_[i].y) * (targetY - joints_[i].y)
>                 );
>                 float lambda = boneLengths_[i] / r;
>                 joints_[i+1].x = (1 - lambda) * joints_[i].x
>                                + lambda * targetX;
>                 joints_[i+1].y = (1 - lambda) * joints_[i].y
>                                + lambda * targetY;
>             }
>             return false;  // 不可达
>         }
>
>         // FABRIK 迭代
>         for (int iter = 0; iter < maxIterations; ++iter) {
>             // ---- Forward Reaching ----
>             // 将末端关节移到目标
>             joints_[n - 1].x = targetX;
>             joints_[n - 1].y = targetY;
>
>             // 从末端向根方向逐个调整
>             for (int i = n - 2; i >= 0; --i) {
>                 float dx = joints_[i+1].x - joints_[i].x;
>                 float dy = joints_[i+1].y - joints_[i].y;
>                 float dist = std::sqrt(dx*dx + dy*dy);
>                 float lambda = boneLengths_[i] / dist;
>
>                 joints_[i].x = joints_[i+1].x - lambda * dx;
>                 joints_[i].y = joints_[i+1].y - lambda * dy;
>
>                 // 关节角度限制
>                 EnforceAngleLimits(i);
>             }
>
>             // ---- Backward Reaching ----
>             // 固定根关节位置
>             float rootX = joints_[0].x;
>             float rootY = joints_[0].y;
>
>             // 从根向末端逐个调整
>             for (int i = 0; i < n - 1; ++i) {
>                 float dx = joints_[i+1].x - joints_[i].x;
>                 float dy = joints_[i+1].y - joints_[i].y;
>                 float dist = std::sqrt(dx*dx + dy*dy);
>                 if (dist < 1e-6f) continue;
>                 float lambda = boneLengths_[i] / dist;
>
>                 joints_[i+1].x = joints_[i].x + lambda * dx;
>                 joints_[i+1].y = joints_[i].y + lambda * dy;
>
>                 EnforceAngleLimits(i);
>             }
>
>             // 检查收敛
>             float ex = joints_[n-1].x - targetX;
>             float ey = joints_[n-1].y - targetY;
>             if (std::sqrt(ex*ex + ey*ey) <= tolerance) return true;
>         }
>
>         return false;  // 达到最大迭代次数但未收敛
>     }
>
>     // 可视化输出
>     void DebugPrint(float targetX, float targetY) const {
>         std::cout << "Joints: ";
>         for (size_t i = 0; i < joints_.size(); ++i) {
>             std::cout << "(" << joints_[i].x << "," << joints_[i].y << ")";
>             if (i < joints_.size() - 1) std::cout << " -> ";
>         }
>         std::cout << "  Target: (" << targetX << "," << targetY << ")\n";
>     }
>
> private:
>     // 强制关节角度限制（这里简化为方向约束）
>     void EnforceAngleLimits(int jointIndex) {
>         auto& j = joints_[jointIndex];
>         if (j.angleMin == 0 && j.angleMax == 0) return;  // 无限制
>
>         // 计算当前骨骼方向
>         float dx = joints_[jointIndex+1].x - joints_[jointIndex].x;
>         float dy = joints_[jointIndex+1].y - joints_[jointIndex].y;
>         float angle = std::atan2(dy, dx);
>
>         // 钳制角度
>         if (angle < j.angleMin || angle > j.angleMax) {
>             float clamped = std::max(j.angleMin,
>                                      std::min(j.angleMax, angle));
>             float len = std::sqrt(dx*dx + dy*dy);
>             joints_[jointIndex+1].x = joints_[jointIndex].x
>                                     + std::cos(clamped) * len;
>             joints_[jointIndex+1].y = joints_[jointIndex].y
>                                     + std::sin(clamped) * len;
>         }
>     }
>
>     std::vector<IKJoint> joints_;
>     std::vector<float> boneLengths_;
> };
>
> // 测试代码（5关节链）
> void TestFABRIK() {
>     FABRIKSolver solver;
>     std::vector<IKJoint> chain = {
>         {0, 0, 0, 0},           // 根关节（固定）
>         {1, 0, -3.14f, 3.14f},  // 肩
>         {2, 0, -2.0f, 0.5f},    // 肘（膝只能单向弯曲）
>         {3, 0, -2.0f, 0.5f},    // 腕
>         {4, 0, 0, 0},           // 末端执行器
>     };
>     solver.SetJoints(chain);
>
>     // 目标位置（不可达远点）
>     bool ok = solver.Solve(0, 5, 20, 0.01f);
>     solver.DebugPrint(0, 5);
>     std::cout << "Converged: " << (ok ? "yes" : "no") << std::endl;
> }
> ```
>
> **核心思路**：FABRIK 与传统的雅可比矩阵IK不同，它直接操作位置而非角度。Forward阶段从末端向根推进——先把末端放在目标位置，然后依次将每个父关节沿骨骼方向拉近；Backward阶段反向——固定根关节，依次将每个子关节沿骨骼方向推远。两次迭代后末端向目标靠近一点，重复直到收敛。关节角度限制在每次调整后强制施加，防止产生违反关节限定的姿势。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // AnimationCompressor.hpp —— 动画压缩器
>
> #include <vector>
> #include <cmath>
> #include <cstdint>
>
> // 原始关键帧
> struct RawKeyframe {
>     float time;
>     float posX, posY, posZ;
>     float rotX, rotY, rotZ, rotW;
>     float sclX, sclY, sclZ;
> };
>
> // 压缩后的关键帧
> struct CompressedKeyframe {
>     float time;
>     int16_t posX, posY, posZ;  // 量化到16位
>     int16_t rotX, rotY, rotZ, rotW;
>     int16_t sclX, sclY, sclZ;
> };
>
> class AnimationCompressor {
> public:
>     // 曲线精简：移除冗余关键帧
>     // 如果移除某帧后用线性插值重建的曲线误差 < threshold，则该帧为冗余
>     static std::vector<RawKeyframe> SimplifyCurve(
>         const std::vector<RawKeyframe>& input,
>         float positionThreshold = 0.01f,
>         float rotationThreshold = 0.001f)  // 四元数分量误差
>     {
>         if (input.size() <= 2) return input;
>
>         std::vector<RawKeyframe> result;
>         result.push_back(input.front());  // 保留首帧
>
>         size_t lastKept = 0;
>         for (size_t i = 1; i < input.size() - 1; ++i) {
>             // 在线性插值重建中，i帧的误差有多大？
>             float maxPosErr = ComputeInterpolationError(
>                 input[lastKept], input[i + 1],
>                 input[i], 'p', positionThreshold);
>             float maxRotErr = ComputeInterpolationError(
>                 input[lastKept], input[i + 1],
>                 input[i], 'r', rotationThreshold);
>
>             // 如果任一误差超过阈值，保留该帧
>             if (maxPosErr > positionThreshold ||
>                 maxRotErr > rotationThreshold) {
>                 result.push_back(input[i]);
>                 lastKept = i;
>             }
>         }
>         result.push_back(input.back());  // 保留尾帧
>         return result;
>     }
>
>     // 量化：浮点→16位定点
>     static CompressedKeyframe Quantize(const RawKeyframe& raw,
>         float posRange = 100.0f)   // 假设模型大小不超过±100
>     {
>         CompressedKeyframe c;
>         c.time = raw.time;
>
>         // 位置：映射到 [-range, range] → [-32767, 32767]
>         c.posX = floatToInt16(raw.posX, posRange);
>         c.posY = floatToInt16(raw.posY, posRange);
>         c.posZ = floatToInt16(raw.posZ, posRange);
>
>         // 旋转：四元数分量在 [-1, 1] → [-32767, 32767]
>         c.rotX = floatToInt16(raw.rotX, 1.0f);
>         c.rotY = floatToInt16(raw.rotY, 1.0f);
>         c.rotZ = floatToInt16(raw.rotZ, 1.0f);
>         c.rotW = floatToInt16(raw.rotW, 1.0f);
>
>         // 缩放：通常在 [0, 10] 范围
>         c.sclX = floatToInt16(raw.sclX, 10.0f);
>         c.sclY = floatToInt16(raw.sclY, 10.0f);
>         c.sclZ = floatToInt16(raw.sclZ, 10.0f);
>
>         return c;
>     }
>
>     // 反量化
>     static RawKeyframe Dequantize(const CompressedKeyframe& c,
>         float posRange = 100.0f)
>     {
>         RawKeyframe r;
>         r.time = c.time;
>         r.posX = int16ToFloat(c.posX, posRange);
>         r.posY = int16ToFloat(c.posY, posRange);
>         r.posZ = int16ToFloat(c.posZ, posRange);
>         r.rotX = int16ToFloat(c.rotX, 1.0f);
>         r.rotY = int16ToFloat(c.rotY, 1.0f);
>         r.rotZ = int16ToFloat(c.rotZ, 1.0f);
>         r.rotW = int16ToFloat(c.rotW, 1.0f);
>         r.sclX = int16ToFloat(c.sclX, 10.0f);
>         r.sclY = int16ToFloat(c.sclY, 10.0f);
>         r.sclZ = int16ToFloat(c.sclZ, 10.0f);
>         return r;
>     }
>
>     // 压缩比计算
>     static float CompressionRatio(
>         const std::vector<RawKeyframe>& original,
>         const std::vector<CompressedKeyframe>& compressed)
>     {
>         float originalSize = original.size() * sizeof(RawKeyframe);
>         float compSize = compressed.size() * sizeof(CompressedKeyframe);
>         return originalSize / compSize;
>     }
>
> private:
>     static float ComputeInterpolationError(
>         const RawKeyframe& a, const RawKeyframe& b,
>         const RawKeyframe& actual, char component,
>         float threshold)
>     {
>         float t = (actual.time - a.time) / (b.time - a.time);
>         float maxErr = 0;
>         if (component == 'p') {
>             auto interp = [](float v0, float v1, float t)
>                 { return v0 + (v1 - v0) * t; };
>             maxErr = std::max(maxErr,
>                 std::abs(actual.posX - interp(a.posX, b.posX, t)));
>             maxErr = std::max(maxErr,
>                 std::abs(actual.posY - interp(a.posY, b.posY, t)));
>             maxErr = std::max(maxErr,
>                 std::abs(actual.posZ - interp(a.posZ, b.posZ, t)));
>         } else {
>             auto interp = [](float v0, float v1, float t)
>                 { return v0 + (v1 - v0) * t; };
>             maxErr = std::max(maxErr,
>                 std::abs(actual.rotX - interp(a.rotX, b.rotX, t)));
>             maxErr = std::max(maxErr,
>                 std::abs(actual.rotY - interp(a.rotY, b.rotY, t)));
>             maxErr = std::max(maxErr,
>                 std::abs(actual.rotZ - interp(a.rotZ, b.rotZ, t)));
>             maxErr = std::max(maxErr,
>                 std::abs(actual.rotW - interp(a.rotW, b.rotW, t)));
>         }
>         return maxErr;
>     }
>
>     static int16_t floatToInt16(float v, float range) {
>         float normalized = v / range;  // [-1, 1]
>         normalized = std::max(-1.0f, std::min(1.0f, normalized));
>         return (int16_t)(normalized * 32767.0f);
>     }
>
>     static float int16ToFloat(int16_t v, float range) {
>         return (float)v / 32767.0f * range;
>     }
> };
> ```
>
> **压缩效果分析**：曲线精简可在关键帧间线性插值误差小于阈值的前提下移除冗余帧，对大段匀速运动的动画（如走路、跑步）压缩效果显著，可达5-10倍。浮点量化将每个float分量从32位压缩到16位，所有分量合并后单帧从13×4=52字节压缩到13×2=26字节（50%压缩）。两者结合可达到10-20倍的总体压缩比。Catmull-Rom样条拟合（进阶方案）可以用更少的控制点重建平滑曲线，压缩比可达50-100倍。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

- [Skinning: Real-Time Rendering, 4th Edition - Chapter 4](https://www.realtimerendering.com/)：实时渲染中关于蒙皮的权威章节
- [Dual Quaternions for Rigid Transformation Blending (Kavan et al., 2008)](https://www.cs.tcd.ie/publications/tech-reports/reports.08/TCD-CS-2008-10.pdf)：双四元数蒙皮的原始论文
- [Animation in Unreal Engine 5](https://docs.unrealengine.com/5.0/en-US/animation-system-overview-in-unreal-engine/)：UE5动画系统官方文档，了解工业级实现
- [Unity Mecanim Animation System](https://docs.unity3d.com/Manual/AnimationOverview.html)：Unity动画系统文档
- [glTF 2.0 Skinning Specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#skins)：了解标准文件格式中的骨骼动画数据布局
- [GDC Talk: Animation Bootcamp](https://www.gdcvault.com/play/1024391/Animation-Bootcamp-Stop-Motion-Animation)：GDC动画技术讲座系列
- [Math for Game Developers: Skeletal Animation](https://www.youtube.com/watch?v=5R5E5zqd_vA)：YouTube上的骨骼动画数学讲解
- [Ozz Animation Library](https://github.com/guillaumeblanc/ozz-animation)：开源C++动画库，包含动画压缩、采样、混合等完整实现
- [Gameplay Animation at Naughty Dog](https://www.youtube.com/watch?v=7fb1F9bH3aY)：《最后生还者》的动画系统GDC分享

---

## 常见陷阱

- **矩阵乘法顺序搞反**：列向量约定（OpenGL/GLSL）下，变换从右向左应用。`M = M_local * M_parent` 表示先应用父变换，再应用局部变换。如果看到骨骼朝错误方向运动，首先检查矩阵乘法顺序。

- **四元数插值不选最短路径**：两个表示相同旋转的四元数 `q` 和 `-q` 是等价的。插值时如果点积为负，应该翻转其中一个，否则插值会绕远路（走大于180度的弧）。

- **蒙皮矩阵计算错误**：`M_skin = M_curr * M_bind_inv` 的推导容易搞混。记住蒙皮矩阵的作用：先把顶点从绑定姿态的模型空间变换到骨骼的局部空间（`M_bind_inv`），再从骨骼局部空间变换到当前姿态的模型空间（`M_curr`）。

- **忽略法线变换的非均匀缩放**：如果骨骼变换包含非均匀缩放，法线需要用逆转置矩阵（inverse-transpose of upper 3x3）变换，否则光照会出错。对于纯旋转+均匀缩放，普通矩阵变换即可。

- **权重不归一化**：顶点权重之和必须严格等于1.0。如果DCC工具导出的权重有微小误差，在着色器中应该重新归一化：`weight /= totalWeight`。

- **GPU bone limit超标**：OpenGL ES 2.0的uniform数量有限（通常128 vec4），一个mat4占4个vec4，所以最多32根骨骼。现代桌面OpenGL支持更多，但仍需注意。如果骨骼太多，考虑在CPU上预混合部分骨骼，或使用纹理存储骨骼矩阵（texture buffer object）。

- **动画循环时的时间跳跃**：`fmod(time, duration)` 处理循环时，如果动画只有一帧或duration为0，会导致除零或采样错误。始终添加保护性检查。

- **IK目标不可达时不处理**：IK求解时，如果目标超出可达范围（例如腿不够长），必须将目标限制在可达范围内，否则会产生NaN或异常旋转。

- **双四元数混合后不重新归一化**：双四元数线性混合后必须归一化实部（旋转四元数），否则变换不再是刚体变换。同时需要正交化对偶部，确保它与实部正交。
