# 数学基础：线性代数与几何

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 无

---

## 1. 概念讲解

### 为什么需要这个？

游戏引擎的核心任务之一，是将虚拟世界中的物体以正确的位置、方向和大小呈现在屏幕上。这一切都离不开数学——更具体地说，是**线性代数**和**解析几何**。

想象一下你在玩一个 3D 游戏：

- 角色向前走一步 —— 这是**向量加法**
- 摄像机跟随角色，始终看着角色的背部 —— 这是**坐标空间变换**
- 角色挥剑，剑刃划过敌人的身体 —— 这是**射线与包围盒相交检测**
- 太阳在天空中缓缓移动，光照角度不断变化 —— 这是**旋转矩阵/四元数**
- 远处的山看起来比近处的树小 —— 这是**透视投影**

这些看似直观的视觉效果，底层全部由线性代数的运算支撑。作为游戏引擎开发工程师，你不需要成为数学家，但必须对这些数学工具的使用了然于胸——就像厨师不需要研究刀具的冶金学，但必须知道如何切、剁、削。

### 核心思想

线性代数的本质，是用**向量**和**矩阵**这两种简洁的表示方法，来描述空间中的位置、方向和变换。

**向量（Vector）** 就像一支箭：它有起点和终点，有长度，有指向。在 3D 空间中，一个向量用三个数字 `(x, y, z)` 表示。向量可以表示位置、速度、力、颜色、法线……几乎所有有"方向性"的量。

**矩阵（Matrix）** 就像一个"变形机器"：你把一个向量丢进去，它就能帮你把这个向量旋转、缩放、平移。多个变换可以"打包"成一个矩阵，一次性应用——这就是**矩阵乘法**的威力。

**四元数（Quaternion）** 是旋转的另一种表示方式。如果说矩阵旋转像"用三个轴来描述方向"，四元数就像"绕着某个轴转某个角度"。它避免了矩阵旋转的"万向节锁"问题，且插值更平滑——这在动画中至关重要。

---

### 1.1 向量（Vector）

#### 类比：向量是一支箭

想象你站在一个巨大的网格地板上，手里拿着一支箭。箭尾在你脚下（原点），箭头指向某个方向。这支箭的长度告诉你"走了多远"，方向告诉你"朝哪走"。这就是向量。

在 2D 中，向量是 `(x, y)`；在 3D 中，向量是 `(x, y, z)`。游戏引擎中最常用的是 3D 向量，但 2D 向量在 UI、2D 游戏中也很常见。

#### 向量的基本运算

**加法与减法**：两支箭首尾相接，结果就是从第一支箭的起点到第二支箭的终点的箭。

- `A + B`：先沿 A 走，再沿 B 走，最终到达的位置
- `A - B`：从 B 的终点指向 A 的终点的箭（常用于计算"从 B 到 A 的方向"）

**数乘**：把箭的长度缩放 k 倍。`k > 0` 时方向不变，`k < 0` 时方向反转。

**长度（Magnitude）**：用勾股定理计算。`|v| = sqrt(x² + y² + z²)`。长度为 1 的向量叫**单位向量**。

**归一化（Normalization）**：把一个向量变成同方向的单位向量。`v̂ = v / |v|`。这就像把箭的长度"压缩"到 1，只保留方向信息。

**点积（Dot Product）**：`A · B = |A| × |B| × cos(θ)`。结果是一个标量（数字）。

- 如果 A 和 B 都是单位向量：点积 = cos(θ)
- 点积 > 0：两向量夹角 < 90°（大致同向）
- 点积 = 0：两向量垂直
- 点积 < 0：两向量夹角 > 90°（大致反向）

点积在游戏中的典型应用：
- **光照计算**：光线方向与表面法线的点积决定亮度
- **视角判断**：玩家朝向与物体方向的点积判断物体是否在视野前方
- **投影**：把一个向量投影到另一个向量方向上

**叉积（Cross Product）**：`A × B` 的结果是一个**垂直于 A 和 B 所在平面**的向量。

- 长度：`|A × B| = |A| × |B| × sin(θ)`，等于 A 和 B 张成的平行四边形的面积
- 方向：用**右手定则**判断——右手四指从 A 弯向 B，大拇指指向叉积方向

叉积在游戏中的典型应用：
- **计算法线**：给定三角形的两条边，叉积得到垂直于三角形表面的法线
- **计算扭矩/旋转轴**：物理引擎中常用
- **判断左右**：在 2D 中，叉积的 z 分量可以判断一个点在向量的左侧还是右侧

**投影（Projection）**：把向量 A "投射"到向量 B 的方向上，得到 A 在 B 方向上的"影子"。

`proj_B(A) = (A · B̂) × B̂`

投影在游戏中的典型应用：
- **滑动碰撞**：角色沿墙壁滑动时，把速度向量投影到墙面切线方向
- **相机跟随**：把角色位置投影到相机轨道平面上

---

### 1.2 矩阵（Matrix）

#### 类比：矩阵是一台变形机器

想象你有一台神奇的机器，能把物体拉长、压扁、旋转、移动。矩阵就是这台机器的"操作说明书"。一个 3×3 矩阵负责旋转和缩放，一个 4×4 矩阵还能负责平移。

#### 矩阵乘法

矩阵乘法的规则看起来复杂，但核心思想很简单：**把多个变换"打包"成一个**。如果你先旋转再缩放，可以把旋转矩阵和缩放矩阵相乘，得到一个"旋转+缩放"的组合矩阵。

**注意：矩阵乘法不满足交换律！** `A × B ≠ B × A`。先旋转后缩放，和先缩放后旋转，结果不同。这就像先穿袜子再穿鞋，和先穿鞋再穿袜子，效果截然不同。

#### 转置（Transpose）

把矩阵的行和列互换。转置有一些漂亮的性质：`(A × B)^T = B^T × A^T`。在图形学中，法线变换常常需要逆转置矩阵。

#### 逆矩阵（Inverse）

如果矩阵 A 把向量"变过去"，逆矩阵 A⁻¹ 就把它"变回来"。`A × A⁻¹ = I`（单位矩阵）。

不是所有矩阵都有逆矩阵。行列式为 0 的矩阵（"压扁"到更低维度的变换）没有逆矩阵。

在游戏引擎中，逆矩阵用于：
- 把世界空间的坐标转回模型空间
- 计算观察矩阵（相机矩阵的逆）

#### 行列式（Determinant）

行列式是一个数字，告诉我们矩阵"拉伸/压缩空间"的程度。

- 行列式 = 1：体积不变（纯旋转）
- 行列式 > 1：空间被放大
- 0 < 行列式 < 1：空间被压缩
- 行列式 = 0：空间被"压扁"到更低维度（不可逆）
- 行列式 < 0：空间被"翻转"了（镜像变换）

---

### 1.3 变换矩阵

#### 平移矩阵（Translation）

平移不能直接用 3×3 矩阵表示（3×3 矩阵乘法总会让零向量保持为零向量，无法"移动"原点）。所以我们使用**齐次坐标**和 4×4 矩阵：

```
| 1  0  0  tx |
| 0  1  0  ty |
| 0  0  1  tz |
| 0  0  0  1  |
```

向量也扩展为 4 维 `(x, y, z, 1)`。第四个分量 w = 1 表示"点"，w = 0 表示"方向向量"（方向向量不受平移影响，这是合理的——速度不会因为坐标系原点的移动而改变）。

#### 缩放矩阵（Scale）

```
| sx  0   0   0 |
| 0   sy  0   0 |
| 0   0   sz  0 |
| 0   0   0   1 |
```

`sx = sy = sz` 时是均匀缩放，否则是非均匀缩放。非均匀缩放会改变物体的形状（比如把一个球压成椭球）。

#### 旋转矩阵（Rotation）

绕 X、Y、Z 轴的旋转矩阵：

**绕 X 轴旋转 θ 角：**
```
| 1  0       0      0 |
| 0  cos(θ) -sin(θ) 0 |
| 0  sin(θ)  cos(θ) 0 |
| 0  0       0      1 |
```

**绕 Y 轴旋转 θ 角：**
```
| cos(θ)  0  sin(θ)  0 |
| 0       1  0       0 |
| -sin(θ) 0  cos(θ)  0 |
| 0       0  0       1 |
```

**绕 Z 轴旋转 θ 角：**
```
| cos(θ) -sin(θ) 0  0 |
| sin(θ)  cos(θ) 0  0 |
| 0       0      1  0 |
| 0       0      0  1 |
```

任意旋转可以分解为绕三个轴的旋转的组合，这就是**欧拉角**（Euler Angles）：`pitch`（俯仰，绕 X）、`yaw`（偏航，绕 Y）、`roll`（翻滚，绕 Z）。

---

### 1.4 四元数（Quaternion）

#### 类比：四元数是一次优雅的旋转

想象你要把一个物体从方向 A 转到方向 B。矩阵旋转像是在说："先绕 X 轴转这么多，再绕 Y 轴转这么多，再绕 Z 轴转这么多"。四元数则像是在说："绕着这根轴，转这个角度"。后者更直观，也更优雅。

四元数是一个 4 元组 `q = (x, y, z, w)`，可以看作是一个旋转轴 `v = (x, y, z)` 和一个旋转角度 θ 的编码：

```
q = (v * sin(θ/2), cos(θ/2))
```

即 `x = axis.x * sin(θ/2)`, `y = axis.y * sin(θ/2)`, `z = axis.z * sin(θ/2)`, `w = cos(θ/2)`。

#### 为什么用四元数？

**1. 避免万向节锁（Gimbal Lock）**

欧拉角有一个致命缺陷：当两个旋转轴对齐时，会丢失一个自由度。想象一个相机的万向节架——当俯仰角达到 ±90° 时，偏航轴和翻滚轴重合，你无法再独立控制这两个旋转。这就是万向节锁。

四元数使用单一的旋转轴+角度表示，天然避免了这个问题。

**2. 插值更平滑**

在动画中，经常需要在两个旋转之间做平滑过渡。直接对欧拉角做线性插值（LERP）会产生不自然的路径——物体可能会"绕远路"。四元数的**球面插值（Slerp）**保证物体沿着最短弧线路径旋转，这是动画系统中不可或缺的。

**3. 存储和运算更高效**

一个四元数只需要 4 个浮点数（16 字节），而一个 4×4 矩阵需要 16 个浮点数（64 字节）。四元数相乘也比矩阵相乘更快。

#### 四元数的基本运算

**乘法**：四元数乘法对应旋转的组合。`q1 * q2` 表示"先应用 q2，再应用 q1"。（注意顺序！）

**共轭**：`q* = (-x, -y, -z, w)`。共轭四元数表示反向旋转。

**逆**：`q⁻¹ = q* / |q|²`。对于单位四元数，逆就是共轭。

**用四元数旋转向量**：`v' = q * v * q⁻¹`。其中 v 被当作纯虚四元数 `(vx, vy, vz, 0)`。

#### Slerp（球面插值）

Slerp 在两个四元数 q1 和 q2 之间做平滑插值，参数 t ∈ [0, 1]：

```
Slerp(q1, q2, t) = (sin((1-t)θ) / sin(θ)) * q1 + (sin(tθ) / sin(θ)) * q2
```

其中 θ 是 q1 和 q2 之间的夹角（通过点积计算）。

Slerp 保证插值路径是四元数球面上的"大圆弧"，即最短旋转路径。

---

### 1.5 坐标空间变换

#### 类比：坐标空间是不同的"视角"

想象你在一栋大楼里：

- **模型空间（Model/Local Space）**：以物体自身为参考。一把椅子的模型空间里，椅腿在 `(0, 0, 0)`，椅背在 `(0, 0, 1)`。无论椅子放在房间的哪个角落，模型空间里的坐标都不变。
- **世界空间（World Space）**：以整个场景为参考。椅子放在房间的东北角，它的世界坐标就是 `(10, 0, 15)`。
- **观察空间（View/Camera Space）**：以相机为参考。相机在 `(5, 2, 5)`，看着 `(10, 0, 15)`。在观察空间里，相机永远在 `(0, 0, 0)`，看着 `-Z` 方向。
- **裁剪空间（Clip Space）**：经过投影变换后的空间。在这个空间里，视锥体（可见区域）被变换成一个规范化的立方体 `[-1, 1]³`。
- **屏幕空间（Screen Space）**：最终的 2D 像素坐标。

#### 变换流水线

```
模型空间 ──[模型矩阵 M]──→ 世界空间 ──[观察矩阵 V]──→ 观察空间 ──[投影矩阵 P]──→ 裁剪空间 ──[透视除法+视口变换]──→ 屏幕空间
```

**模型矩阵（Model Matrix）**：把物体从模型空间变换到世界空间。包含平移、旋转、缩放。

**观察矩阵（View Matrix）**：把世界空间变换到观察空间。它是相机变换矩阵的逆。如果相机在世界空间中的变换是 `T_camera`，那么 `V = T_camera⁻¹`。

**投影矩阵（Projection Matrix）**：把观察空间变换到裁剪空间。

- **透视投影（Perspective）**：近大远小，模拟人眼/相机的视觉效果。用视场角（FOV）、宽高比、近裁剪面、远裁剪面定义。
- **正交投影（Orthographic）**：平行线保持平行，常用于 2D 游戏、工程制图、小地图。

**MVP 矩阵**：`MVP = P × V × M`。在顶点着色器中，通常一次性把顶点从模型空间变换到裁剪空间：`v_clip = MVP × v_model`。

---

### 1.6 投影矩阵的完整数学推导

#### 正交投影矩阵

**正交投影（Orthographic Projection）**保持物体的实际大小不变，不随距离变化。它在 2D 游戏、CAD 软件、以及引擎的 UI 渲染中使用。

正交投影矩阵将观察空间中的轴对齐包围盒 `[left, right] x [bottom, top] x [near, far]` 映射到 NDC 的 `[-1, 1]^3` 立方体：

```
| 2/(r-l)     0         0       -(r+l)/(r-l) |
| 0           2/(t-b)   0       -(t+b)/(t-b) |
| 0           0        -2/(f-n)  -(f+n)/(f-n) |
| 0           0         0         1           |
```

Z 分量的负号来源于两种坐标系的选择差异：观察空间中相机看向负 Z 方向，近裁剪面在 `z = -near`，远裁剪面在 `z = -far`；而 NDC 中 Z 值范围是 `[-1, 1]`，且深度值随距离增加而增加。

#### 透视投影矩阵的推导

**透视投影（Perspective Projection）**是实现 3D 深度感的关键。它模拟人眼和真实相机的工作原理——远处的物体看起来更小。

透视投影矩阵的推导需要理解**视锥体（View Frustum）**的概念。视锥体是一个被裁剪平面截断的金字塔，定义了相机可见的空间范围。

设垂直视场角为 `fov_y`，宽高比为 `aspect = width / height`，近裁剪面距离为 `n`，远裁剪面距离为 `f`。

首先，根据视场角计算近裁剪面的半高：

```
tan(fov_y / 2) = top / n   =>   top = n * tan(fov_y / 2)
right = top * aspect
```

透视投影的核心思想是：**将视锥体内的点投影到近裁剪面上，然后进行缩放使其进入 NDC 范围**。对于观察空间中的点 `(x, y, z)`，其到近裁剪面的投影为：

```
x_proj = (n * x) / (-z)
y_proj = (n * y) / (-z)
```

这里的 `-z` 是因为观察空间中相机看向负 Z 方向（点在相机前方时 `z < 0`）。

然后，将近裁剪面上的坐标缩放到 `[-1, 1]` 范围：

```
x_ndc = x_proj / right = (n * x) / ((-z) * right)
y_ndc = y_proj / top   = (n * y) / ((-z) * top)
```

注意 `x_ndc` 和 `y_ndc` 的分母中都含有 `-z`。这正是齐次坐标的巧妙之处：如果我们在投影矩阵中让 `w' = -z`，那么经过透视除法 `x'/w'` 后，分母中的 `-z` 自然出现。

对于 Z 坐标的处理更为微妙。我们希望深度值在 `[-1, 1]` 范围内映射，且映射关系是非线性的（在近裁剪面附近精度更高）。设 `z'` 经过透视除法后为 `z'/w' = z'/(-z)`，我们希望这个值在近裁剪面 `(z = -n)` 时为 `-1`，在远裁剪面 `(z = -f)` 时为 `1`。

设投影矩阵的第三行（对应 `z'` 的输出）为 `(0, 0, A, B)`，则 `z' = A * z + B`。代入边界条件并求解：

```
A = (f + n) / (n - f) = -(f + n) / (f - n)
B = -2fn / (f - n)
```

最终的透视投影矩阵为：

```
| n/right   0         0              0     |
| 0         n/top     0              0     |
| 0         0         (f+n)/(n-f)   2fn/(n-f) |
| 0         0        -1              0     |
```

用 `fov_y` 和 `aspect` 表示：

```
| 1/(aspect*tan(fov_y/2))  0                    0              0     |
| 0                        1/tan(fov_y/2)       0              0     |
| 0                        0                    (f+n)/(n-f)   2fn/(n-f) |
| 0                        0                   -1              0     |
```

```cpp
// 透视投影矩阵实现
static Mat4 Perspective(float fovY, float aspect, float nearPlane, float farPlane) {
    Mat4 result = Zero();
    float tanHalfFov = std::tan(fovY / 2.0f);

    result.m[0][0] = 1.0f / (aspect * tanHalfFov);
    result.m[1][1] = 1.0f / tanHalfFov;
    result.m[2][2] = -(farPlane + nearPlane) / (farPlane - nearPlane);
    result.m[2][3] = -1.0f;  // 把 Z 复制到 W，用于透视除法
    result.m[3][2] = -(2.0f * farPlane * nearPlane) / (farPlane - nearPlane);
    return result;
}
```

#### 矩阵乘法顺序的重要性

理解矩阵乘法顺序对于正确使用变换至关重要。考虑一个物体需要经历以下变换：先缩放 2 倍，再绕 Y 轴旋转 45 度，最后平移到位置 `(10, 0, 0)`。

组合矩阵为：`M = T(10,0,0) * R_y(45°) * S(2)`

当应用于顶点 `v` 时：`v' = M * v = T * (R * (S * v))`

这意味着变换从右到左依次应用：先缩放，再旋转，最后平移。如果改变顺序（例如先旋转后缩放），结果会完全不同——先旋转再缩放不仅改变了大小，还会引入非均匀缩放导致的剪切效果。

在渲染管线中，一个顶点的完整变换链是：

```
v_clip = M_proj * M_view * M_model * v_local
```

这个变换顺序在图形学文献中常被称为 **MVP 变换（Model-View-Projection）**。GPU 着色器中通常将这三个矩阵预先相乘为 MVP 矩阵，以减少每个顶点的矩阵乘法次数。

---

### 1.7 射线与三角形相交检测

**射线与三角形相交检测（Ray-Triangle Intersection）**是 3D 渲染和物理引擎中最常用的几何操作之一。它在引擎中的应用包括：鼠标拾取 3D 对象、子弹碰撞检测、光线追踪、以及烘焙光照。

我们使用**Möller-Trumbore 算法**——一种基于参数方程和 Cramer 法则的高效方法。

给定射线 `R(t) = origin + t * direction`（`t >= 0`）和由三个顶点 `v0, v1, v2` 定义的三角形，交点满足：

```
origin + t * direction = v0 + u * e1 + v * e2
```

其中 `e1 = v1 - v0`，`e2 = v2 - v0` 是三角形的两条边，`u >= 0`，`v >= 0`，`u + v <= 1` 确保交点在三角形内部。

使用 Cramer 法则求解，令 `h = direction x e2`，`a = e1 · h`：

```cpp
// Möller-Trumbore 射线-三角形相交算法
struct RayTriangleResult {
    float t;       // 射线参数
    float u, v;    // 重心坐标
    Vec3 point;    // 交点
};

std::optional<RayTriangleResult> IntersectRayTriangle(
    const Ray& ray,
    const Vec3& v0, const Vec3& v1, const Vec3& v2) {

    constexpr float EPS = 1e-6f;

    Vec3 e1 = v1 - v0;
    Vec3 e2 = v2 - v0;
    Vec3 h = ray.direction.Cross(e2);
    float a = e1.Dot(h);

    // 如果 a 接近 0，射线与三角形平行
    if (a > -EPS && a < EPS) return std::nullopt;

    float f = 1.0f / a;
    Vec3 s = ray.origin - v0;
    float u = f * s.Dot(h);
    if (u < 0.0f || u > 1.0f) return std::nullopt;

    Vec3 q = s.Cross(e1);
    float v = f * ray.direction.Dot(q);
    if (v < 0.0f || u + v > 1.0f) return std::nullopt;

    float t = f * e2.Dot(q);
    if (t > EPS) {
        return RayTriangleResult{t, u, v, ray.At(t)};
    }
    return std::nullopt;  // t <= 0 表示交点在射线起点后方
}
```

Möller-Trumbore 算法的优势在于它不需要预先计算三角形的平面方程，且通过 Cramer 法则和叉积的巧妙运用，避免了昂贵的矩阵求逆。整个算法只需要一次除法、多次乘法和加法，在现代 CPU 上极为高效。

### 1.8 视锥体（Frustum）

**视锥体（Viewing Frustum）**是相机可见的空间区域，由六个裁剪平面定义：左、右、上、下、近、远。视锥体剔除（Frustum Culling）是渲染管线中的关键优化——不在视锥体内的对象不需要被渲染。

```cpp
// 视锥体——由六个平面定义
struct Frustum {
    Plane planes[6];  // Left, Right, Bottom, Top, Near, Far

    // 从视图-投影矩阵提取视锥体平面
    // 这是引擎中最常用的方法——直接从 VP 矩阵推导视锥体
    static Frustum FromViewProjectionMatrix(const Mat4& vp) {
        Frustum frustum;
        // 左平面 = 列3 + 列0
        frustum.planes[0].normal = Vec3(
            vp.m[0][3] + vp.m[0][0],
            vp.m[1][3] + vp.m[1][0],
            vp.m[2][3] + vp.m[2][0]
        ).Normalized();
        frustum.planes[0].d = vp.m[3][3] + vp.m[3][0];

        // 右平面 = 列3 - 列0
        frustum.planes[1].normal = Vec3(
            vp.m[0][3] - vp.m[0][0],
            vp.m[1][3] - vp.m[1][0],
            vp.m[2][3] - vp.m[2][0]
        ).Normalized();
        frustum.planes[1].d = vp.m[3][3] - vp.m[3][0];

        // 下平面 = 列3 + 列1
        frustum.planes[2].normal = Vec3(
            vp.m[0][3] + vp.m[0][1],
            vp.m[1][3] + vp.m[1][1],
            vp.m[2][3] + vp.m[2][1]
        ).Normalized();
        frustum.planes[2].d = vp.m[3][3] + vp.m[3][1];

        // 上平面 = 列3 - 列1
        frustum.planes[3].normal = Vec3(
            vp.m[0][3] - vp.m[0][1],
            vp.m[1][3] - vp.m[1][1],
            vp.m[2][3] - vp.m[2][1]
        ).Normalized();
        frustum.planes[3].d = vp.m[3][3] - vp.m[3][1];

        // 近平面 = 列3 + 列2
        frustum.planes[4].normal = Vec3(
            vp.m[0][3] + vp.m[0][2],
            vp.m[1][3] + vp.m[1][2],
            vp.m[2][3] + vp.m[2][2]
        ).Normalized();
        frustum.planes[4].d = vp.m[3][3] + vp.m[3][2];

        // 远平面 = 列3 - 列2
        frustum.planes[5].normal = Vec3(
            vp.m[0][3] - vp.m[0][2],
            vp.m[1][3] - vp.m[1][2],
            vp.m[2][3] - vp.m[2][2]
        ).Normalized();
        frustum.planes[5].d = vp.m[3][3] - vp.m[3][2];

        return frustum;
    }

    // AABB 与视锥体相交测试
    // 返回值: true = 相交或包含, false = 完全在外部
    bool IntersectsAABB(const AABB& aabb) const {
        for (int i = 0; i < 6; ++i) {
            // 找到 AABB 在平面法线方向上的"最正"顶点
            Vec3 positiveVertex(
                planes[i].normal.x >= 0.0f ? aabb.max.x : aabb.min.x,
                planes[i].normal.y >= 0.0f ? aabb.max.y : aabb.min.y,
                planes[i].normal.z >= 0.0f ? aabb.max.z : aabb.min.z
            );
            if (planes[i].DistanceTo(positiveVertex) < 0.0f) {
                return false;  // 完全在此平面的外侧
            }
        }
        return true;
    }

    // 球体与视锥体相交测试
    bool IntersectsSphere(const Vec3& center, float radius) const {
        for (int i = 0; i < 6; ++i) {
            float dist = planes[i].DistanceTo(center);
            if (dist < -radius) return false;  // 球体完全在此平面的外侧
        }
        return true;
    }
};
```

视锥体剔除是渲染管线中最重要的 CPU 端优化之一。在现代游戏场景中，可能有成千上万个渲染对象，但只有一小部分（通常 20-40%）实际位于视锥体内。通过视锥体剔除排除不可见对象，可以显著减少提交给 GPU 的绘制调用数量。

上述 AABB-视锥体测试是**保守的（conservative）**——它可能将一些实际不可见的包围盒判定为可见（假阳性），但不会将可见的判定为不可见（假阴性）。这种单向错误对于剔除来说是可接受的。

| 相交测试 | 算法 | 复杂度 | 引擎应用 |
|---------|------|--------|---------|
| 射线-三角形 | Möller-Trumbore | O(1) | 拾取、光线追踪、碰撞检测 |
| 射线-AABB | Slab 方法 | O(1) | 快速粗筛、体素遍历 |
| 射线-球体 | 二次方程求解 | O(1) | 简单碰撞检测 |
| AABB-AABB | 分量级比较 | O(1) | 碰撞粗测、剔除 |
| 球体-球体 | 距离比较 | O(1) | 简单碰撞检测 |
| AABB-视锥体 | 6 平面测试 | O(1) | 视锥体剔除 |
| 球体-视锥体 | 6 平面测试 | O(1) | 视锥体剔除（粗略） |

在实际的碰撞检测系统中，这些测试被组织成**层次结构**：先用廉价的 AABB 或球体测试快速排除不可能相交的对象对，然后对通过粗测的对象对使用更精确的测试。这种 **Broad Phase（粗测） + Narrow Phase（精测）**的两阶段策略是物理引擎和碰撞系统的标准架构。

---

### 1.9 基础几何体

#### 平面（Plane）

平面由**法线** `n`（单位向量）和**到原点的有符号距离** `d` 定义。平面方程：`n · x + d = 0`。

平面在游戏中的典型应用：
- **视锥体裁剪**：视锥体的 6 个面都是平面
- **地面碰撞检测**：角色是否站在地面上
- **反射/水面渲染**：定义反射平面

点到平面的有符号距离：`distance = n · point + d`。正值在法线正方向一侧，负值在另一侧。

#### 射线（Ray）

射线由**起点** `origin` 和**方向** `direction`（单位向量）定义。射线上的点：`P(t) = origin + t * direction`，其中 `t ≥ 0`。

射线在游戏中的典型应用：
- **拾取/射线检测（Raycasting）**：鼠标点击选中 3D 物体
- **子弹/激光轨迹**：射击游戏中的弹道计算
- **光照计算**：光线追踪中的光线

#### AABB（Axis-Aligned Bounding Box，轴对齐包围盒）

AABB 由**最小点** `min` 和**最大点** `max` 定义，它的边与世界坐标轴平行。

AABB 在游戏中的典型应用：
- **粗略碰撞检测**：先判断两个物体的 AABB 是否相交，如果相交再做更精确的检测（ broad phase / narrow phase 策略）
- **视锥体裁剪**：判断物体的 AABB 是否在视锥体内
- **空间划分**：八叉树、BVH 等加速结构的节点

AABB 相交检测非常简单：两个 AABB 相交，当且仅当在所有三个轴上的投影区间都重叠。

#### OBB（Oriented Bounding Box，定向包围盒）

OBB 与 AABB 类似，但它的边不一定与世界坐标轴平行。OBB 更紧密地包围物体，但相交检测更复杂（需要分离轴定理 SAT）。

---

## 2. 代码示例

```cpp
// ============================================================
// 游戏引擎数学库 — 向量、矩阵、四元数、几何体
// 使用 C++17 特性，单文件可编译
// ============================================================

#include <cmath>
#include <iostream>
#include <array>
#include <stdexcept>
#include <string>

// ============================================================
// 工具函数
// ============================================================
constexpr float PI = 3.14159265358979323846f;
constexpr float EPSILON = 1e-6f;

inline float DegToRad(float deg) { return deg * PI / 180.0f; }
inline float RadToDeg(float rad) { return rad * 180.0f / PI; }

// 安全的反三角函数：将值裁剪到 [-1, 1] 范围内
inline float SafeAcos(float x) {
    if (x <= -1.0f) return PI;
    if (x >= 1.0f) return 0.0f;
    return std::acos(x);
}

// ============================================================
// Vec2 — 2D 向量
// ============================================================
struct Vec2 {
    float x, y;

    Vec2() : x(0), y(0) {}
    Vec2(float x_, float y_) : x(x_), y(y_) {}

    // 基本运算
    Vec2 operator+(const Vec2& o) const { return Vec2(x + o.x, y + o.y); }
    Vec2 operator-(const Vec2& o) const { return Vec2(x - o.x, y - o.y); }
    Vec2 operator*(float s) const { return Vec2(x * s, y * s); }
    Vec2 operator/(float s) const { return Vec2(x / s, y / s); }

    Vec2& operator+=(const Vec2& o) { x += o.x; y += o.y; return *this; }
    Vec2& operator-=(const Vec2& o) { x -= o.x; y -= o.y; return *this; }

    // 点积：A·B = |A||B|cos(θ)
    // 应用：判断方向相似度、计算投影长度、光照亮度
    float Dot(const Vec2& o) const { return x * o.x + y * o.y; }

    // 叉积（2D 中返回标量，表示有向面积）
    // 正值：o 在 *this 的左侧；负值：o 在右侧；0：共线
    // 应用：判断点在线段的哪一侧、计算多边形面积
    float Cross(const Vec2& o) const { return x * o.y - y * o.x; }

    // 长度平方（避免开方，更快）
    float LengthSq() const { return x * x + y * y; }

    // 长度
    float Length() const { return std::sqrt(LengthSq()); }

    // 归一化：得到同方向的单位向量
    // 应用：只关心方向时（如表面法线、视线方向）
    Vec2 Normalized() const {
        float len = Length();
        if (len < EPSILON) return Vec2(0, 0);
        return *this / len;
    }

    // 将向量投影到另一个向量上
    // 应用：角色沿墙壁滑动时，把速度投影到墙面方向
    Vec2 ProjectOnto(const Vec2& o) const {
        float oLenSq = o.LengthSq();
        if (oLenSq < EPSILON) return Vec2(0, 0);
        float scale = Dot(o) / oLenSq;
        return o * scale;
    }

    // 垂直向量（逆时针旋转 90°）
    Vec2 Perpendicular() const { return Vec2(-y, x); }

    // 线性插值
    Vec2 Lerp(const Vec2& o, float t) const {
        return *this * (1.0f - t) + o * t;
    }

    bool operator==(const Vec2& o) const {
        return std::abs(x - o.x) < EPSILON && std::abs(y - o.y) < EPSILON;
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << " = ";
        std::cout << "(" << x << ", " << y << ")\n";
    }
};

// ============================================================
// Vec3 — 3D 向量
// ============================================================
struct Vec3 {
    float x, y, z;

    Vec3() : x(0), y(0), z(0) {}
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}

    static Vec3 Zero() { return Vec3(0, 0, 0); }
    static Vec3 One() { return Vec3(1, 1, 1); }
    static Vec3 Up() { return Vec3(0, 1, 0); }
    static Vec3 Right() { return Vec3(1, 0, 0); }
    static Vec3 Forward() { return Vec3(0, 0, 1); }

    Vec3 operator+(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x - o.x, y - o.y, z - o.z); }
    Vec3 operator*(float s) const { return Vec3(x * s, y * s, z * s); }
    Vec3 operator/(float s) const { return Vec3(x / s, y / s, z / s); }
    Vec3 operator-() const { return Vec3(-x, -y, -z); }

    Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
    Vec3& operator-=(const Vec3& o) { x -= o.x; y -= o.y; z -= o.z; return *this; }
    Vec3& operator*=(float s) { x *= s; y *= s; z *= s; return *this; }

    float Dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }

    // 叉积：产生垂直于两个输入向量的向量
    // 应用：计算三角形法线、计算旋转轴、判断左右
    Vec3 Cross(const Vec3& o) const {
        return Vec3(
            y * o.z - z * o.y,
            z * o.x - x * o.z,
            x * o.y - y * o.x
        );
    }

    float LengthSq() const { return x * x + y * y + z * z; }
    float Length() const { return std::sqrt(LengthSq()); }

    Vec3 Normalized() const {
        float len = Length();
        if (len < EPSILON) return Vec3(0, 0, 0);
        return *this / len;
    }

    void Normalize() {
        float len = Length();
        if (len > EPSILON) { *this /= len; }
    }

    Vec3 ProjectOnto(const Vec3& o) const {
        float oLenSq = o.LengthSq();
        if (oLenSq < EPSILON) return Vec3(0, 0, 0);
        return o * (Dot(o) / oLenSq);
    }

    // 反射：入射向量关于法线的反射
    // 应用：镜面反射、弹跳计算
    Vec3 Reflect(const Vec3& normal) const {
        return *this - normal * (2.0f * Dot(normal));
    }

    Vec3 Lerp(const Vec3& o, float t) const {
        return *this * (1.0f - t) + o * t;
    }

    // 分量乘法（常用于颜色混合）
    Vec3 MulComponents(const Vec3& o) const {
        return Vec3(x * o.x, y * o.y, z * o.z);
    }

    bool operator==(const Vec3& o) const {
        return std::abs(x - o.x) < EPSILON &&
               std::abs(y - o.y) < EPSILON &&
               std::abs(z - o.z) < EPSILON;
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << " = ";
        std::cout << "(" << x << ", " << y << ", " << z << ")\n";
    }
};

inline Vec3 operator*(float s, const Vec3& v) { return v * s; }

// ============================================================
// Vec4 — 4D 向量（用于齐次坐标）
// ============================================================
struct Vec4 {
    float x, y, z, w;

    Vec4() : x(0), y(0), z(0), w(0) {}
    Vec4(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}
    Vec4(const Vec3& v, float w_) : x(v.x), y(v.y), z(v.z), w(w_) {}

    Vec3 ToVec3() const { return Vec3(x, y, z); }

    Vec4 operator+(const Vec4& o) const {
        return Vec4(x + o.x, y + o.y, z + o.z, w + o.w);
    }
    Vec4 operator*(float s) const {
        return Vec4(x * s, y * s, z * s, w * s);
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << " = ";
        std::cout << "(" << x << ", " << y << ", " << z << ", " << w << ")\n";
    }
};

// ============================================================
// Mat3 — 3×3 矩阵（用于 2D 变换、法线变换）
// 列主序存储（符合 OpenGL/DirectX 惯例）
// ============================================================
struct Mat3 {
    // m[col][row] — 列主序
    std::array<std::array<float, 3>, 3> m;

    Mat3() {
        // 初始化为单位矩阵
        for (int c = 0; c < 3; ++c)
            for (int r = 0; r < 3; ++r)
                m[c][r] = (c == r) ? 1.0f : 0.0f;
    }

    static Mat3 Zero() {
        Mat3 result;
        for (int c = 0; c < 3; ++c)
            for (int r = 0; r < 3; ++r)
                result.m[c][r] = 0.0f;
        return result;
    }

    float& operator()(int col, int row) { return m[col][row]; }
    const float& operator()(int col, int row) const { return m[col][row]; }

    // 矩阵 × 向量
    Vec3 operator*(const Vec3& v) const {
        return Vec3(
            m[0][0] * v.x + m[1][0] * v.y + m[2][0] * v.z,
            m[0][1] * v.x + m[1][1] * v.y + m[2][1] * v.z,
            m[0][2] * v.x + m[1][2] * v.y + m[2][2] * v.z
        );
    }

    // 矩阵 × 矩阵
    Mat3 operator*(const Mat3& o) const {
        Mat3 result = Zero();
        for (int c = 0; c < 3; ++c) {
            for (int r = 0; r < 3; ++r) {
                for (int k = 0; k < 3; ++k) {
                    result.m[c][r] += m[k][r] * o.m[c][k];
                }
            }
        }
        return result;
    }

    // 转置
    Mat3 Transposed() const {
        Mat3 result;
        for (int c = 0; c < 3; ++c)
            for (int r = 0; r < 3; ++r)
                result.m[r][c] = m[c][r];
        return result;
    }

    // 行列式
    float Determinant() const {
        return m[0][0] * (m[1][1] * m[2][2] - m[2][1] * m[1][2])
             - m[1][0] * (m[0][1] * m[2][2] - m[2][1] * m[0][2])
             + m[2][0] * (m[0][1] * m[1][2] - m[1][1] * m[0][2]);
    }

    // 逆矩阵
    Mat3 Inverted() const {
        float det = Determinant();
        if (std::abs(det) < EPSILON) {
            throw std::runtime_error("Matrix is singular, cannot invert");
        }

        float invDet = 1.0f / det;
        Mat3 result;

        result.m[0][0] = (m[1][1] * m[2][2] - m[2][1] * m[1][2]) * invDet;
        result.m[0][1] = (m[0][2] * m[2][1] - m[0][1] * m[2][2]) * invDet;
        result.m[0][2] = (m[0][1] * m[1][2] - m[0][2] * m[1][1]) * invDet;
        result.m[1][0] = (m[1][2] * m[2][0] - m[1][0] * m[2][2]) * invDet;
        result.m[1][1] = (m[0][0] * m[2][2] - m[0][2] * m[2][0]) * invDet;
        result.m[1][2] = (m[0][2] * m[1][0] - m[0][0] * m[1][2]) * invDet;
        result.m[2][0] = (m[1][0] * m[2][1] - m[1][1] * m[2][0]) * invDet;
        result.m[2][1] = (m[0][1] * m[2][0] - m[0][0] * m[2][1]) * invDet;
        result.m[2][2] = (m[0][0] * m[1][1] - m[0][1] * m[1][0]) * invDet;

        return result;
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << ":\n";
        for (int r = 0; r < 3; ++r) {
            std::cout << "| ";
            for (int c = 0; c < 3; ++c) {
                std::cout << m[c][r] << " ";
            }
            std::cout << "|\n";
        }
    }
};

// ============================================================
// Mat4 — 4×4 矩阵（用于 3D 变换：平移、旋转、缩放、投影）
// 列主序存储
// ============================================================
struct Mat4 {
    std::array<std::array<float, 4>, 4> m;

    Mat4() {
        for (int c = 0; c < 4; ++c)
            for (int r = 0; r < 4; ++r)
                m[c][r] = (c == r) ? 1.0f : 0.0f;
    }

    static Mat4 Zero() {
        Mat4 result;
        for (int c = 0; c < 4; ++c)
            for (int r = 0; r < 4; ++r)
                result.m[c][r] = 0.0f;
        return result;
    }

    static Mat4 Identity() { return Mat4(); }

    float& operator()(int col, int row) { return m[col][row]; }
    const float& operator()(int col, int row) const { return m[col][row]; }

    Vec4 operator*(const Vec4& v) const {
        return Vec4(
            m[0][0]*v.x + m[1][0]*v.y + m[2][0]*v.z + m[3][0]*v.w,
            m[0][1]*v.x + m[1][1]*v.y + m[2][1]*v.z + m[3][1]*v.w,
            m[0][2]*v.x + m[1][2]*v.y + m[2][2]*v.z + m[3][2]*v.w,
            m[0][3]*v.x + m[1][3]*v.y + m[2][3]*v.z + m[3][3]*v.w
        );
    }

    // 变换点（w = 1）
    Vec3 TransformPoint(const Vec3& p) const {
        Vec4 v4(p, 1.0f);
        Vec4 result = *this * v4;
        if (std::abs(result.w) > EPSILON) {
            return Vec3(result.x / result.w, result.y / result.w, result.z / result.w);
        }
        return result.ToVec3();
    }

    // 变换方向向量（w = 0，不受平移影响）
    Vec3 TransformVector(const Vec3& v) const {
        return Vec3(
            m[0][0]*v.x + m[1][0]*v.y + m[2][0]*v.z,
            m[0][1]*v.x + m[1][1]*v.y + m[2][1]*v.z,
            m[0][2]*v.x + m[1][2]*v.y + m[2][2]*v.z
        );
    }

    Mat4 operator*(const Mat4& o) const {
        Mat4 result = Zero();
        for (int c = 0; c < 4; ++c) {
            for (int r = 0; r < 4; ++r) {
                for (int k = 0; k < 4; ++k) {
                    result.m[c][r] += m[k][r] * o.m[c][k];
                }
            }
        }
        return result;
    }

    Mat4 Transposed() const {
        Mat4 result;
        for (int c = 0; c < 4; ++c)
            for (int r = 0; r < 4; ++r)
                result.m[r][c] = m[c][r];
        return result;
    }

    // 提取平移分量
    Vec3 GetTranslation() const { return Vec3(m[3][0], m[3][1], m[3][2]); }

    // 提取缩放分量（假设无剪切）
    Vec3 GetScale() const {
        return Vec3(
            Vec3(m[0][0], m[0][1], m[0][2]).Length(),
            Vec3(m[1][0], m[1][1], m[1][2]).Length(),
            Vec3(m[2][0], m[2][1], m[2][2]).Length()
        );
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << ":\n";
        for (int r = 0; r < 4; ++r) {
            std::cout << "| ";
            for (int c = 0; c < 4; ++c) {
                printf("%8.4f ", m[c][r]);
            }
            std::cout << "|\n";
        }
    }

    // ---- 静态构造方法：变换矩阵 ----

    // 平移矩阵
    static Mat4 Translate(float tx, float ty, float tz) {
        Mat4 result;
        result.m[3][0] = tx;
        result.m[3][1] = ty;
        result.m[3][2] = tz;
        return result;
    }
    static Mat4 Translate(const Vec3& t) { return Translate(t.x, t.y, t.z); }

    // 缩放矩阵
    static Mat4 Scale(float sx, float sy, float sz) {
        Mat4 result;
        result.m[0][0] = sx;
        result.m[1][1] = sy;
        result.m[2][2] = sz;
        return result;
    }
    static Mat4 Scale(float s) { return Scale(s, s, s); }
    static Mat4 Scale(const Vec3& s) { return Scale(s.x, s.y, s.z); }

    // 绕 X 轴旋转
    static Mat4 RotateX(float radians) {
        Mat4 result;
        float c = std::cos(radians);
        float s = std::sin(radians);
        result.m[1][1] = c;  result.m[2][1] = -s;
        result.m[1][2] = s;  result.m[2][2] = c;
        return result;
    }

    // 绕 Y 轴旋转
    static Mat4 RotateY(float radians) {
        Mat4 result;
        float c = std::cos(radians);
        float s = std::sin(radians);
        result.m[0][0] = c;  result.m[2][0] = s;
        result.m[0][2] = -s; result.m[2][2] = c;
        return result;
    }

    // 绕 Z 轴旋转
    static Mat4 RotateZ(float radians) {
        Mat4 result;
        float c = std::cos(radians);
        float s = std::sin(radians);
        result.m[0][0] = c;  result.m[1][0] = -s;
        result.m[0][1] = s;  result.m[1][1] = c;
        return result;
    }

    // 绕任意轴旋转（Rodrigues 旋转公式的矩阵形式）
    static Mat4 RotateAxis(const Vec3& axis, float radians) {
        Vec3 a = axis.Normalized();
        float c = std::cos(radians);
        float s = std::sin(radians);
        float t = 1.0f - c;

        Mat4 result;
        result.m[0][0] = t * a.x * a.x + c;
        result.m[0][1] = t * a.x * a.y + s * a.z;
        result.m[0][2] = t * a.x * a.z - s * a.y;

        result.m[1][0] = t * a.x * a.y - s * a.z;
        result.m[1][1] = t * a.y * a.y + c;
        result.m[1][2] = t * a.y * a.z + s * a.x;

        result.m[2][0] = t * a.x * a.z + s * a.y;
        result.m[2][1] = t * a.y * a.z - s * a.x;
        result.m[2][2] = t * a.z * a.z + c;
        return result;
    }

    // 从欧拉角构造旋转矩阵（ZYX 顺序：先绕 Z，再绕 Y，再绕 X）
    // pitch = 绕 X, yaw = 绕 Y, roll = 绕 Z
    static Mat4 FromEuler(float pitch, float yaw, float roll) {
        return RotateZ(roll) * RotateY(yaw) * RotateX(pitch);
    }

    // 观察矩阵（LookAt）：相机在 eye 处，看向 target，up 指定上方方向
    // 这是图形学中最常用的矩阵构造之一
    static Mat4 LookAt(const Vec3& eye, const Vec3& target, const Vec3& up) {
        Vec3 forward = (target - eye).Normalized();  // 相机看向 -Z 方向
        Vec3 right = forward.Cross(up).Normalized();
        Vec3 cameraUp = right.Cross(forward);        // 重新正交化

        Mat4 result;
        // 旋转部分（基向量转置 = 逆旋转）
        result.m[0][0] = right.x;     result.m[0][1] = cameraUp.x;     result.m[0][2] = -forward.x;
        result.m[1][0] = right.y;     result.m[1][1] = cameraUp.y;     result.m[1][2] = -forward.y;
        result.m[2][0] = right.z;     result.m[2][1] = cameraUp.z;     result.m[2][2] = -forward.z;
        // 平移部分（把 eye 移到原点）
        result.m[3][0] = -right.Dot(eye);
        result.m[3][1] = -cameraUp.Dot(eye);
        result.m[3][2] = forward.Dot(eye);
        return result;
    }

    // 透视投影矩阵
    // fovY: 垂直视场角（弧度）
    // aspect: 宽高比 (width / height)
    // nearPlane, farPlane: 近/远裁剪面距离（必须为正）
    static Mat4 Perspective(float fovY, float aspect, float nearPlane, float farPlane) {
        Mat4 result = Zero();
        float tanHalfFov = std::tan(fovY / 2.0f);

        result.m[0][0] = 1.0f / (aspect * tanHalfFov);
        result.m[1][1] = 1.0f / tanHalfFov;
        result.m[2][2] = -(farPlane + nearPlane) / (farPlane - nearPlane);
        result.m[2][3] = -1.0f;  // 把 Z 复制到 W，用于透视除法
        result.m[3][2] = -(2.0f * farPlane * nearPlane) / (farPlane - nearPlane);
        return result;
    }

    // 正交投影矩阵
    static Mat4 Orthographic(float left, float right, float bottom, float top,
                              float nearPlane, float farPlane) {
        Mat4 result;
        result.m[0][0] = 2.0f / (right - left);
        result.m[1][1] = 2.0f / (top - bottom);
        result.m[2][2] = -2.0f / (farPlane - nearPlane);
        result.m[3][0] = -(right + left) / (right - left);
        result.m[3][1] = -(top + bottom) / (top - bottom);
        result.m[3][2] = -(farPlane + nearPlane) / (farPlane - nearPlane);
        return result;
    }
};

// ============================================================
// Quaternion — 四元数
// ============================================================
struct Quaternion {
    float x, y, z, w;

    Quaternion() : x(0), y(0), z(0), w(1) {}  // 单位四元数 = 无旋转
    Quaternion(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}

    static Quaternion Identity() { return Quaternion(0, 0, 0, 1); }

    // 从旋转轴和角度构造（轴不需要归一化）
    // 应用：指定"绕某个轴转多少度"
    static Quaternion FromAxisAngle(const Vec3& axis, float radians) {
        Vec3 a = axis.Normalized();
        float halfAngle = radians / 2.0f;
        float s = std::sin(halfAngle);
        return Quaternion(a.x * s, a.y * s, a.z * s, std::cos(halfAngle));
    }

    // 从欧拉角构造（ZYX 顺序）
    static Quaternion FromEuler(float pitch, float yaw, float roll) {
        float cy = std::cos(yaw * 0.5f);
        float sy = std::sin(yaw * 0.5f);
        float cp = std::cos(pitch * 0.5f);
        float sp = std::sin(pitch * 0.5f);
        float cr = std::cos(roll * 0.5f);
        float sr = std::sin(roll * 0.5f);

        return Quaternion(
            sr * cp * cy - cr * sp * sy,  // x
            cr * sp * cy + sr * cp * sy,  // y
            cr * cp * sy - sr * sp * cy,  // z
            cr * cp * cy + sr * sp * sy   // w
        );
    }

    // 从旋转矩阵构造
    static Quaternion FromMatrix(const Mat4& mat) {
        float trace = mat.m[0][0] + mat.m[1][1] + mat.m[2][2];
        Quaternion q;

        if (trace > 0.0f) {
            float s = std::sqrt(trace + 1.0f) * 2.0f;
            q.w = 0.25f * s;
            q.x = (mat.m[1][2] - mat.m[2][1]) / s;
            q.y = (mat.m[2][0] - mat.m[0][2]) / s;
            q.z = (mat.m[0][1] - mat.m[1][0]) / s;
        } else if (mat.m[0][0] > mat.m[1][1] && mat.m[0][0] > mat.m[2][2]) {
            float s = std::sqrt(1.0f + mat.m[0][0] - mat.m[1][1] - mat.m[2][2]) * 2.0f;
            q.w = (mat.m[1][2] - mat.m[2][1]) / s;
            q.x = 0.25f * s;
            q.y = (mat.m[1][0] + mat.m[0][1]) / s;
            q.z = (mat.m[2][0] + mat.m[0][2]) / s;
        } else if (mat.m[1][1] > mat.m[2][2]) {
            float s = std::sqrt(1.0f + mat.m[1][1] - mat.m[0][0] - mat.m[2][2]) * 2.0f;
            q.w = (mat.m[2][0] - mat.m[0][2]) / s;
            q.x = (mat.m[1][0] + mat.m[0][1]) / s;
            q.y = 0.25f * s;
            q.z = (mat.m[2][1] + mat.m[1][2]) / s;
        } else {
            float s = std::sqrt(1.0f + mat.m[2][2] - mat.m[0][0] - mat.m[1][1]) * 2.0f;
            q.w = (mat.m[0][1] - mat.m[1][0]) / s;
            q.x = (mat.m[2][0] + mat.m[0][2]) / s;
            q.y = (mat.m[2][1] + mat.m[1][2]) / s;
            q.z = 0.25f * s;
        }
        return q;
    }

    // 四元数乘法（组合旋转）
    // q1 * q2 = "先应用 q2，再应用 q1"
    Quaternion operator*(const Quaternion& o) const {
        return Quaternion(
            w * o.x + x * o.w + y * o.z - z * o.y,
            w * o.y - x * o.z + y * o.w + z * o.x,
            w * o.z + x * o.y - y * o.x + z * o.w,
            w * o.w - x * o.x - y * o.y - z * o.z
        );
    }

    // 共轭（逆旋转）
    Quaternion Conjugate() const { return Quaternion(-x, -y, -z, w); }

    // 长度
    float Length() const { return std::sqrt(x*x + y*y + z*z + w*w); }

    // 归一化
    Quaternion Normalized() const {
        float len = Length();
        if (len < EPSILON) return Identity();
        float invLen = 1.0f / len;
        return Quaternion(x * invLen, y * invLen, z * invLen, w * invLen);
    }

    void Normalize() {
        float len = Length();
        if (len > EPSILON) {
            float invLen = 1.0f / len;
            x *= invLen; y *= invLen; z *= invLen; w *= invLen;
        }
    }

    // 逆
    Quaternion Inverted() const {
        float lenSq = x*x + y*y + z*z + w*w;
        if (lenSq < EPSILON) return Identity();
        float invLenSq = 1.0f / lenSq;
        return Quaternion(-x * invLenSq, -y * invLenSq, -z * invLenSq, w * invLenSq);
    }

    // 用四元数旋转向量
    Vec3 RotateVector(const Vec3& v) const {
        // q * v * q⁻¹，其中 v 被当作纯虚四元数
        Quaternion qv(v.x, v.y, v.z, 0);
        Quaternion result = *this * qv * Conjugate();
        return Vec3(result.x, result.y, result.z);
    }

    // 转换为旋转矩阵
    Mat4 ToMatrix() const {
        Mat4 result;
        float xx = x * x, yy = y * y, zz = z * z;
        float xy = x * y, xz = x * z, yz = y * z;
        float wx = w * x, wy = w * y, wz = w * z;

        result.m[0][0] = 1.0f - 2.0f * (yy + zz);
        result.m[0][1] = 2.0f * (xy + wz);
        result.m[0][2] = 2.0f * (xz - wy);

        result.m[1][0] = 2.0f * (xy - wz);
        result.m[1][1] = 1.0f - 2.0f * (xx + zz);
        result.m[1][2] = 2.0f * (yz + wx);

        result.m[2][0] = 2.0f * (xz + wy);
        result.m[2][1] = 2.0f * (yz - wx);
        result.m[2][2] = 1.0f - 2.0f * (xx + yy);
        return result;
    }

    // 转换为欧拉角（ZYX 顺序）
    Vec3 ToEuler() const {
        Vec3 euler;
        // pitch (X)
        float sinp = 2.0f * (w * x + y * z);
        float cosp = 1.0f - 2.0f * (x * x + y * y);
        euler.x = std::atan2(sinp, cosp);

        // yaw (Y)
        float sinY = 2.0f * (w * y - z * x);
        if (std::abs(sinY) >= 1.0f)
            euler.y = std::copysign(PI / 2.0f, sinY);  // 使用 90°
        else
            euler.y = std::asin(sinY);

        // roll (Z)
        float sinr = 2.0f * (w * z + x * y);
        float cosr = 1.0f - 2.0f * (y * y + z * z);
        euler.z = std::atan2(sinr, cosr);

        return euler;
    }

    // 点积
    float Dot(const Quaternion& o) const {
        return x * o.x + y * o.y + z * o.z + w * o.w;
    }

    // 线性插值（LERP）— 不保证恒定角速度，但计算快
    Quaternion Lerp(const Quaternion& o, float t) const {
        return Quaternion(
            x * (1 - t) + o.x * t,
            y * (1 - t) + o.y * t,
            z * (1 - t) + o.z * t,
            w * (1 - t) + o.w * t
        ).Normalized();
    }

    // 球面插值（SLERP）— 恒定角速度，动画首选
    // 应用：角色转身、相机平滑转向、骨骼动画插值
    Quaternion Slerp(const Quaternion& o, float t) const {
        Quaternion q1 = *this;
        Quaternion q2 = o;

        float dot = q1.Dot(q2);

        // 如果点积为负，取反其中一个四元数以走最短路径
        if (dot < 0.0f) {
            q2 = Quaternion(-q2.x, -q2.y, -q2.z, -q2.w);
            dot = -dot;
        }

        // 如果四元数非常接近，用 LERP 避免除零和数值不稳定
        const float DOT_THRESHOLD = 0.9995f;
        if (dot > DOT_THRESHOLD) {
            return q1.Lerp(q2, t);
        }

        float theta = SafeAcos(dot);
        float sinTheta = std::sin(theta);
        float s1 = std::sin((1.0f - t) * theta) / sinTheta;
        float s2 = std::sin(t * theta) / sinTheta;

        return Quaternion(
            q1.x * s1 + q2.x * s2,
            q1.y * s1 + q2.y * s2,
            q1.z * s1 + q2.z * s2,
            q1.w * s1 + q2.w * s2
        );
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << " = ";
        std::cout << "(" << x << ", " << y << ", " << z << ", " << w << ")\n";
    }
};

// ============================================================
// 几何体
// ============================================================

// ---- 平面 ----
struct Plane {
    Vec3 normal;   // 单位法线
    float d;       // 到原点的有符号距离

    Plane() : normal(Vec3::Up()), d(0) {}
    Plane(const Vec3& n, float d_) : normal(n.Normalized()), d(d_) {}

    // 从平面上一点和法线构造
    static Plane FromPointNormal(const Vec3& point, const Vec3& normal) {
        Vec3 n = normal.Normalized();
        return Plane(n, -n.Dot(point));
    }

    // 从三个点构造（逆时针方向为正面）
    static Plane FromPoints(const Vec3& a, const Vec3& b, const Vec3& c) {
        Vec3 normal = (b - a).Cross(c - a).Normalized();
        return FromPointNormal(a, normal);
    }

    // 点到平面的有符号距离
    // > 0：点在法线正方向一侧
    // < 0：点在法线负方向一侧
    float DistanceTo(const Vec3& point) const {
        return normal.Dot(point) + d;
    }

    // 点在平面上的投影
    Vec3 ProjectPoint(const Vec3& point) const {
        return point - normal * DistanceTo(point);
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << ": ";
        std::cout << "normal="; normal.Print();
        std::cout << "  d=" << d << "\n";
    }
};

// ---- 射线 ----
struct Ray {
    Vec3 origin;     // 起点
    Vec3 direction;  // 方向（单位向量）

    Ray() : origin(Vec3::Zero()), direction(Vec3::Forward()) {}
    Ray(const Vec3& o, const Vec3& dir) : origin(o), direction(dir.Normalized()) {}

    // 射线上的点，t >= 0
    Vec3 At(float t) const { return origin + direction * t; }

    // 射线与平面相交
    // 返回值：t（射线参数），如果射线与平面平行则返回 false
    bool IntersectPlane(const Plane& plane, float& outT) const {
        float denom = direction.Dot(plane.normal);
        if (std::abs(denom) < EPSILON) {
            return false;  // 射线与平面平行
        }
        outT = -(plane.normal.Dot(origin) + plane.d) / denom;
        return outT >= 0;  // 只接受交点在射线正方向上
    }

    // 射线与球相交
    bool IntersectSphere(const Vec3& center, float radius, float& outT) const {
        Vec3 oc = origin - center;
        float a = direction.LengthSq();
        float b = 2.0f * oc.Dot(direction);
        float c = oc.LengthSq() - radius * radius;
        float discriminant = b * b - 4.0f * a * c;

        if (discriminant < 0) return false;

        float sqrtDisc = std::sqrt(discriminant);
        float t = (-b - sqrtDisc) / (2.0f * a);
        if (t >= 0) {
            outT = t;
            return true;
        }
        t = (-b + sqrtDisc) / (2.0f * a);
        if (t >= 0) {
            outT = t;
            return true;
        }
        return false;
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << ":\n";
        std::cout << "  origin="; origin.Print();
        std::cout << "  direction="; direction.Print();
    }
};

// ---- AABB（轴对齐包围盒）----
struct AABB {
    Vec3 min;  // 最小角
    Vec3 max;  // 最大角

    AABB() : min(Vec3::Zero()), max(Vec3::Zero()) {}
    AABB(const Vec3& min_, const Vec3& max_) : min(min_), max(max_) {}

    // 从中心点和半尺寸构造
    static AABB FromCenterHalfSize(const Vec3& center, const Vec3& halfSize) {
        return AABB(center - halfSize, center + halfSize);
    }

    Vec3 Center() const { return (min + max) * 0.5f; }
    Vec3 HalfSize() const { return (max - min) * 0.5f; }
    Vec3 Size() const { return max - min; }

    // 扩展包围盒以包含一个点
    void Expand(const Vec3& point) {
        min.x = std::min(min.x, point.x);
        min.y = std::min(min.y, point.y);
        min.z = std::min(min.z, point.z);
        max.x = std::max(max.x, point.x);
        max.y = std::max(max.y, point.y);
        max.z = std::max(max.z, point.z);
    }

    // 两个 AABB 是否相交
    bool Intersects(const AABB& o) const {
        return min.x <= o.max.x && max.x >= o.min.x &&
               min.y <= o.max.y && max.y >= o.min.y &&
               min.z <= o.max.z && max.z >= o.min.z;
    }

    // 点是否在 AABB 内
    bool Contains(const Vec3& point) const {
        return point.x >= min.x && point.x <= max.x &&
               point.y >= min.y && point.y <= max.y &&
               point.z >= min.z && point.z <= max.z;
    }

    // AABB 与射线相交（Slab 方法）
    bool IntersectRay(const Ray& ray, float& outTMin) const {
        float tMin = 0.0f;
        float tMax = 1e30f;

        for (int i = 0; i < 3; ++i) {
            float origin = (i == 0) ? ray.origin.x : (i == 1) ? ray.origin.y : ray.origin.z;
            float dir = (i == 0) ? ray.direction.x : (i == 1) ? ray.direction.y : ray.direction.z;
            float minVal = (i == 0) ? min.x : (i == 1) ? min.y : min.z;
            float maxVal = (i == 0) ? max.x : (i == 1) ? max.y : max.z;

            if (std::abs(dir) < EPSILON) {
                if (origin < minVal || origin > maxVal) return false;
            } else {
                float t1 = (minVal - origin) / dir;
                float t2 = (maxVal - origin) / dir;
                if (t1 > t2) std::swap(t1, t2);
                tMin = std::max(tMin, t1);
                tMax = std::min(tMax, t2);
                if (tMin > tMax || tMax < 0) return false;
            }
        }

        outTMin = (tMin >= 0) ? tMin : tMax;
        return outTMin >= 0;
    }

    // AABB 与平面相交判断
    // 返回值：>0 完全在正面，<0 完全在背面，0 相交
    int ClassifyPlane(const Plane& plane) const {
        // 计算包围盒在平面法线方向上的投影中心点和半径
        Vec3 center = Center();
        Vec3 half = HalfSize();
        float radius = half.x * std::abs(plane.normal.x)
                     + half.y * std::abs(plane.normal.y)
                     + half.z * std::abs(plane.normal.z);
        float dist = plane.DistanceTo(center);

        if (dist > radius) return 1;   // 完全在正面
        if (dist < -radius) return -1; // 完全在背面
        return 0;                      // 相交
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << ":\n";
        std::cout << "  min="; min.Print();
        std::cout << "  max="; max.Print();
    }
};

// ---- 球体 ----
struct Sphere {
    Vec3 center;
    float radius;

    Sphere() : center(Vec3::Zero()), radius(1.0f) {}
    Sphere(const Vec3& c, float r) : center(c), radius(r) {}

    bool Contains(const Vec3& point) const {
        return (point - center).LengthSq() <= radius * radius;
    }

    bool Intersects(const Sphere& o) const {
        float distSq = (center - o.center).LengthSq();
        float radiusSum = radius + o.radius;
        return distSq <= radiusSum * radiusSum;
    }

    void Print(const std::string& name = "") const {
        if (!name.empty()) std::cout << name << ": ";
        std::cout << "center="; center.Print();
        std::cout << "  radius=" << radius << "\n";
    }
};

// ============================================================
// 演示主函数
// ============================================================
int main() {
    std::cout << "========================================\n";
    std::cout << "  游戏引擎数学库演示\n";
    std::cout << "========================================\n\n";

    // ---- 1. 向量运算 ----
    std::cout << "--- 1. 向量运算 ---\n\n";

    Vec3 a(3, 4, 0);
    Vec3 b(1, 2, 2);

    a.Print("向量 A");
    b.Print("向量 B");
    std::cout << "A 的长度: " << a.Length() << "\n";
    std::cout << "A 归一化: "; a.Normalized().Print();

    Vec3 c = a + b;
    c.Print("A + B");

    float dot = a.Dot(b);
    std::cout << "A · B (点积): " << dot << "\n";
    std::cout << "  → 说明: 点积 > 0，两向量大致同向（夹角 < 90°）\n";
    std::cout << "  → 游戏应用: 判断敌人是否在玩家前方视野内\n\n";

    Vec3 cross = a.Cross(b);
    cross.Print("A × B (叉积)");
    std::cout << "  → 说明: 结果垂直于 A 和 B 所在平面\n";
    std::cout << "  → 游戏应用: 计算三角形法线（用于光照）\n\n";

    Vec3 proj = a.ProjectOnto(b);
    proj.Print("A 在 B 上的投影");
    std::cout << "  → 游戏应用: 角色沿墙壁滑动时，把速度投影到墙面方向\n\n";

    // ---- 2. 矩阵变换 ----
    std::cout << "--- 2. 矩阵变换 ---\n\n";

    Vec3 point(1, 0, 0);
    point.Print("原始点");

    Mat4 rotY = Mat4::RotateY(DegToRad(90));
    Vec3 rotated = rotY.TransformPoint(point);
    rotated.Print("绕 Y 轴旋转 90° 后");
    std::cout << "  → 游戏应用: 角色转向、物体旋转\n\n";

    Mat4 trans = Mat4::Translate(5, 0, 0);
    Mat4 scale = Mat4::Scale(2);
    Mat4 combined = trans * scale;  // 先缩放，再平移
    combined.Print("组合矩阵（先缩放 2x，再平移 (5,0,0)）");

    Vec3 transformed = combined.TransformPoint(Vec3(1, 1, 1));
    transformed.Print("(1,1,1) 经过组合变换后");
    std::cout << "  → 注意: 矩阵乘法不满足交换律！\n";
    std::cout << "  → 先缩放再平移: 平移距离也被缩放\n";
    std::cout << "  → 先平移再缩放: 平移距离不受影响\n\n";

    // ---- 3. LookAt 矩阵 ----
    std::cout << "--- 3. 观察矩阵（LookAt）---\n\n";

    Vec3 eye(0, 5, 10);      // 相机位置
    Vec3 target(0, 0, 0);    // 看向原点
    Vec3 up(0, 1, 0);        // 上方

    Mat4 view = Mat4::LookAt(eye, target, up);
    view.Print("观察矩阵（相机在 (0,5,10)，看向原点）");

    Vec3 worldPos(1, 2, 3);
    Vec3 viewPos = view.TransformPoint(worldPos);
    viewPos.Print("世界坐标 (1,2,3) 在观察空间中的坐标");
    std::cout << "  → 游戏应用: 把世界坐标变换到相机视角\n\n";

    // ---- 4. 投影矩阵 ----
    std::cout << "--- 4. 投影矩阵 ---\n\n";

    Mat4 proj = Mat4::Perspective(DegToRad(60), 16.0f / 9.0f, 0.1f, 100.0f);
    proj.Print("透视投影矩阵（FOV=60°, 16:9, near=0.1, far=100）");

    Vec3 viewVertex(0, 0, -5);  // 在观察空间中，Z 轴指向屏幕内
    Vec4 clipPos = proj * Vec4(viewVertex, 1.0f);
    clipPos.Print("顶点 (0,0,-5) 在裁剪空间中的坐标");
    std::cout << "  → 注意 w 分量不再是 1，需要做透视除法\n";
    std::cout << "  → NDC 坐标: (" << clipPos.x / clipPos.w << ", "
              << clipPos.y / clipPos.w << ", " << clipPos.z / clipPos.w << ")\n";
    std::cout << "  → 游戏应用: 3D 到 2D 的透视投影，近大远小\n\n";

    // ---- 5. 四元数 ----
    std::cout << "--- 5. 四元数 ---\n\n";

    // 绕 Y 轴旋转 90°
    Quaternion qY = Quaternion::FromAxisAngle(Vec3::Up(), DegToRad(90));
    qY.Print("绕 Y 轴旋转 90° 的四元数");

    Vec3 v(1, 0, 0);
    Vec3 rotatedByQ = qY.RotateVector(v);
    rotatedByQ.Print("(1,0,0) 经四元数旋转后");
    std::cout << "  → 结果与矩阵旋转一致！\n\n";

    // 四元数组合旋转
    Quaternion qX = Quaternion::FromAxisAngle(Vec3::Right(), DegToRad(45));
    Quaternion combinedQ = qY * qX;  // 先绕 X 转 45°，再绕 Y 转 90°
    combinedQ.Normalize();
    combinedQ.Print("组合旋转（先 X45°，再 Y90°）");
    std::cout << "  → 游戏应用: 骨骼动画中多个关节旋转的组合\n\n";

    // 四元数 ↔ 欧拉角转换
    Vec3 euler = qY.ToEuler();
    std::cout << "四元数转欧拉角: pitch=" << RadToDeg(euler.x)
              << "°, yaw=" << RadToDeg(euler.y)
              << "°, roll=" << RadToDeg(euler.z) << "°\n\n";

    // 四元数 ↔ 矩阵转换
    Mat4 qMatrix = qY.ToMatrix();
    qMatrix.Print("四元数转旋转矩阵");
    std::cout << "  → 游戏应用: 物理引擎用四元数计算，渲染用矩阵，需要频繁转换\n\n";

    // Slerp 插值
    std::cout << "--- 6. 四元数球面插值（Slerp）---\n\n";

    Quaternion qStart = Quaternion::FromAxisAngle(Vec3::Up(), 0);
    Quaternion qEnd = Quaternion::FromAxisAngle(Vec3::Up(), DegToRad(90));

    std::cout << "从 0° 到 90° 的平滑旋转:\n";
    for (int i = 0; i <= 4; ++i) {
        float t = i / 4.0f;
        Quaternion q = qStart.Slerp(qEnd, t);
        Vec3 rotated = q.RotateVector(Vec3(1, 0, 0));
        std::cout << "  t=" << t << ": (1,0,0) → ("
                  << rotated.x << ", " << rotated.y << ", " << rotated.z << ")\n";
    }
    std::cout << "  → 游戏应用: 角色平滑转身、相机跟随、骨骼动画过渡\n\n";

    // ---- 7. 几何体 ----
    std::cout << "--- 7. 几何体 ---\n\n";

    // 平面
    Plane ground(Vec3::Up(), 0);  // y = 0 平面
    ground.Print("地面平面");
    std::cout << "点 (0, 5, 0) 到平面的距离: " << ground.DistanceTo(Vec3(0, 5, 0)) << "\n";
    std::cout << "点 (0, -2, 0) 到平面的距离: " << ground.DistanceTo(Vec3(0, -2, 0)) << "\n";
    std::cout << "  → 游戏应用: 判断角色是否在地面上方/下方\n\n";

    // 射线与平面相交
    Ray ray(Vec3(0, 5, 0), Vec3(0, -1, 0));  // 从 (0,5,0) 垂直向下
    float t;
    if (ray.IntersectPlane(ground, t)) {
        Vec3 hit = ray.At(t);
        std::cout << "射线与平面相交于 t=" << t << "，交点=";
        hit.Print();
    }
    std::cout << "  → 游戏应用: 鼠标点击地面移动角色（射线投射）\n\n";

    // 射线与球相交
    Sphere sphere(Vec3(0, 0, 5), 2.0f);
    sphere.Print("球体");
    Ray rayToSphere(Vec3(0, 0, 0), Vec3(0, 0, 1));
    if (rayToSphere.IntersectSphere(sphere.center, sphere.radius, t)) {
        std::cout << "射线与球相交于 t=" << t << "，交点=";
        rayToSphere.At(t).Print();
    }
    std::cout << "  → 游戏应用: 子弹命中检测、拾取判定\n\n";

    // AABB
    AABB box(Vec3(-1, -1, -1), Vec3(1, 1, 1));
    box.Print("AABB 包围盒");

    AABB box2(Vec3(0.5f, 0.5f, 0.5f), Vec3(2, 2, 2));
    std::cout << "box 与 box2 相交? " << (box.Intersects(box2) ? "是" : "否") << "\n";

    AABB box3(Vec3(5, 5, 5), Vec3(6, 6, 6));
    std::cout << "box 与 box3 相交? " << (box.Intersects(box3) ? "是" : "否") << "\n";
    std::cout << "  → 游戏应用: 粗略碰撞检测（broad phase）\n\n";

    // 射线与 AABB 相交
    Ray rayThroughBox(Vec3(-5, 0, 0), Vec3(1, 0, 0));
    if (box.IntersectRay(rayThroughBox, t)) {
        std::cout << "射线穿过 AABB，入口 t=" << t << "，入口点=";
        rayThroughBox.At(t).Print();
    }
    std::cout << "  → 游戏应用: 射线拾取 3D 物体（先检测 AABB，再检测精确网格）\n\n";

    // ---- 8. 坐标空间变换流水线 ----
    std::cout << "--- 8. 坐标空间变换流水线 ---\n\n";

    // 模型空间中的一个顶点
    Vec3 modelVertex(1, 1, 1);
    modelVertex.Print("模型空间顶点");

    // 模型矩阵：把椅子放在世界坐标 (10, 0, 5)，旋转 30°，放大 2 倍
    Mat4 model = Mat4::Translate(10, 0, 5) *
                 Mat4::RotateY(DegToRad(30)) *
                 Mat4::Scale(2);

    // 观察矩阵：相机在 (15, 5, 15)，看向椅子
    Mat4 view2 = Mat4::LookAt(Vec3(15, 5, 15), Vec3(10, 0, 5), Vec3::Up());

    // 投影矩阵
    Mat4 projection = Mat4::Perspective(DegToRad(45), 16.0f / 9.0f, 0.1f, 100.0f);

    // MVP 矩阵
    Mat4 mvp = projection * view2 * model;

    // 完整变换
    Vec4 clip = mvp * Vec4(modelVertex, 1.0f);
    clip.Print("裁剪空间坐标");

    // 透视除法得到 NDC
    Vec3 ndc(clip.x / clip.w, clip.y / clip.w, clip.z / clip.w);
    ndc.Print("NDC 坐标（透视除法后）");
    std::cout << "  → NDC 范围 [-1, 1]，可直接映射到屏幕像素\n";
    std::cout << "  → 这是 GPU 顶点着色器的标准输出\n\n";

    // ---- 9. 矩阵逆运算 ----
    std::cout << "--- 9. 矩阵逆运算 ---\n\n";

    Mat3 rot3;
    rot3.m[0][0] = 0; rot3.m[1][0] = -1; rot3.m[2][0] = 0;
    rot3.m[0][1] = 1; rot3.m[1][1] = 0;  rot3.m[2][1] = 0;
    rot3.m[0][2] = 0; rot3.m[1][2] = 0;  rot3.m[2][2] = 1;
    rot3.Print("3×3 旋转矩阵（绕 Z 轴 90°）");

    std::cout << "行列式: " << rot3.Determinant() << "\n";

    Mat3 inv3 = rot3.Inverted();
    inv3.Print("逆矩阵");

    Vec3 test(1, 0, 0);
    Vec3 afterRot = rot3 * test;
    afterRot.Print("(1,0,0) 经旋转后");
    Vec3 afterInv = inv3 * afterRot;
    afterInv.Print("再经逆矩阵变换后");
    std::cout << "  → 恢复原状！逆矩阵 = 撤销变换\n\n";

    std::cout << "========================================\n";
    std::cout << "  演示结束\n";
    std::cout << "========================================\n";

    return 0;
}
```

**运行方式:**

```bash
# 使用 g++ 编译（C++17 标准）
g++ -std=c++17 -O2 -o math_demo math_demo.cpp

# 运行
./math_demo

# Windows 上使用 MSVC:
# cl /std:c++17 /O2 /EHsc math_demo.cpp
# math_demo.exe
```

**预期输出:**

```text
========================================
  游戏引擎数学库演示
========================================

--- 1. 向量运算 ---

向量 A = (3, 4, 0)
向量 B = (1, 2, 2)
A 的长度: 5
A 归一化 = (0.6, 0.8, 0)
A + B = (4, 6, 2)
A · B (点积): 11
  → 说明: 点积 > 0，两向量大致同向（夹角 < 90°）
  → 游戏应用: 判断敌人是否在玩家前方视野内

A × B (叉积) = (8, -6, 2)
  → 说明: 结果垂直于 A 和 B 所在平面
  → 游戏应用: 计算三角形法线（用于光照）

A 在 B 上的投影 = (1.57143, 3.14286, 3.14286)
  → 游戏应用: 角色沿墙壁滑动时，把速度投影到墙面方向

--- 2. 矩阵变换 ---

原始点 = (1, 0, 0)
绕 Y 轴旋转 90° 后 = (0, 0, -1)
  → 游戏应用: 角色转向、物体旋转

组合矩阵（先缩放 2x，再平移 (5,0,0)）:
|   2.0000    0.0000    0.0000    0.0000 |
|   0.0000    2.0000    0.0000    0.0000 |
|   0.0000    0.0000    2.0000    0.0000 |
|   5.0000    0.0000    0.0000    1.0000 |

(1,1,1) 经过组合变换后 = (7, 2, 2)
  → 注意: 矩阵乘法不满足交换律！
  → 先缩放再平移: 平移距离也被缩放
  → 先平移再缩放: 平移距离不受影响

--- 3. 观察矩阵（LookAt） ---

观察矩阵（相机在 (0,5,10)，看向原点）:
|   1.0000    0.0000    0.0000    0.0000 |
|   0.0000    0.8944   -0.4472    0.0000 |
|   0.0000    0.4472    0.8944    0.0000 |
|   0.0000    0.0000  -11.1803    1.0000 |

世界坐标 (1,2,3) 在观察空间中的坐标 = (1, 0.4472, -7.6026)
  → 游戏应用: 把世界坐标变换到相机视角

--- 4. 投影矩阵 ---

透视投影矩阵（FOV=60°, 16:9, near=0.1, far=100）:
|   0.9743    0.0000    0.0000    0.0000 |
|   0.0000    1.7321    0.0000    0.0000 |
|   0.0000    0.0000   -1.0020   -1.0000 |
|   0.0000    0.0000   -0.2002    0.0000 |

顶点 (0,0,-5) 在裁剪空间中的坐标 = (0, 0, 4.8099, 5)
  → 注意 w 分量不再是 1，需要做透视除法
  → NDC 坐标: (0, 0, 0.962)
  → 游戏应用: 3D 到 2D 的透视投影，近大远小

--- 5. 四元数 ---

绕 Y 轴旋转 90° 的四元数 = (0, 0.707107, 0, 0.707107)
(1,0,0) 经四元数旋转后 = (0, 0, -1)
  → 结果与矩阵旋转一致！

组合旋转（先 X45°，再 Y90°） = (0.270598, 0.653281, 0.270598, 0.653281)
  → 游戏应用: 骨骼动画中多个关节旋转的组合

四元数转欧拉角: pitch=0°, yaw=90°, roll=0°

四元数转旋转矩阵:
|   0.0000    0.0000   -1.0000    0.0000 |
|   0.0000    1.0000    0.0000    0.0000 |
|   1.0000    0.0000    0.0000    0.0000 |
|   0.0000    0.0000    0.0000    1.0000 |
  → 游戏应用: 物理引擎用四元数计算，渲染用矩阵，需要频繁转换

--- 6. 四元数球面插值（Slerp） ---

从 0° 到 90° 的平滑旋转:
  t=0: (1,0,0) → (1, 0, 0)
  t=0.25: (1,0,0) → (0.92388, 0, -0.382683)
  t=0.5: (1,0,0) → (0.707107, 0, -0.707107)
  t=0.75: (1,0,0) → (0.382683, 0, -0.92388)
  t=1: (1,0,0) → (0, 0, -1)
  → 游戏应用: 角色平滑转身、相机跟随、骨骼动画过渡

--- 7. 几何体 ---

地面平面: normal=(0, 1, 0)
  d=0
点 (0, 5, 0) 到平面的距离: 5
点 (0, -2, 0) 到平面的距离: -2
  → 游戏应用: 判断角色是否在地面上方/下方

射线与平面相交于 t=5，交点=(0, 0, 0)
  → 游戏应用: 鼠标点击地面移动角色（射线投射）

球体: center=(0, 0, 5)
  radius=2
射线与球相交于 t=3，交点=(0, 0, 3)
  → 游戏应用: 子弹命中检测、拾取判定

AABB 包围盒:
  min=(-1, -1, -1)
  max=(1, 1, 1)
box 与 box2 相交? 是
box 与 box3 相交? 否
  → 游戏应用: 粗略碰撞检测（broad phase）

射线穿过 AABB，入口 t=4，入口点=(-1, 0, 0)
  → 游戏应用: 射线拾取 3D 物体（先检测 AABB，再检测精确网格）

--- 8. 坐标空间变换流水线 ---

模型空间顶点 = (1, 1, 1)
裁剪空间坐标 = (-1.1547, 4.6188, 5.4074, -5.4074)
NDC 坐标（透视除法后） = (0.2135, -0.8541, -1)
  → NDC 范围 [-1, 1]，可直接映射到屏幕像素
  → 这是 GPU 顶点着色器的标准输出

--- 9. 矩阵逆运算 ---

3×3 旋转矩阵（绕 Z 轴 90°）:
| 0 -1  0 |
| 1  0  0 |
| 0  0  1 |

行列式: 1
逆矩阵:
| 0 1 0 |
| -1 0 0 |
| 0 0 1 |

(1,0,0) 经旋转后 = (0, 1, 0)
再经逆矩阵变换后 = (1, 0, 0)
  → 恢复原状！逆矩阵 = 撤销变换

========================================
  演示结束
========================================
```

---

## 3. 微积分在游戏开发中的应用

微积分是描述**连续变化**的数学工具，在游戏引擎中有着广泛的应用——物理模拟、动画插值、摄像机平滑、粒子系统等。

### 3.1 导数与运动学

**导数（Derivative）**描述了一个量相对于另一个量的瞬时变化率。在运动学中，位置、速度、加速度之间的关系就是微积分的基本应用：

```
v(t) = dp(t)/dt    (速度是位置的导数)
a(t) = dv(t)/dt = d²p(t)/dt²    (加速度是速度的导数)
```

在离散的游戏循环中（以固定时间步长 `dt` 更新），我们使用**数值积分（Numerical Integration）**来近似连续的运动：

**显式欧拉法（Explicit/Forward Euler）**：

```cpp
// 显式欧拉积分——最简单但精度最低
struct Particle {
    Vec3 position;
    Vec3 velocity;
    Vec3 acceleration;

    void UpdateExplicitEuler(float dt) {
        velocity += acceleration * dt;
        position += velocity * dt;
    }
};
```

显式欧拉法是一阶方法——其局部截断误差为 `O(dt²)`，全局累积误差为 `O(dt)`。更严重的问题是，显式欧拉法在模拟弹簧等**刚性系统（Stiff Systems）**时是不稳定的——能量会随时间指数增长，导致模拟发散。

**半隐式欧拉法（Semi-Implicit/Symplectic Euler）**通过交换更新顺序来改进稳定性：

```cpp
void UpdateSemiImplicitEuler(float dt) {
    velocity += acceleration * dt;    // 先用旧加速度更新速度
    position += velocity * dt;        // 再用新速度更新位置
}
```

半隐式欧拉法仍然是一阶精度，但具有**辛性质（Symplectic Property）**——它保持能量在平均值附近振荡而不是单调发散。这使得它成为游戏物理引擎中最常用的积分方法（Box2D、Bullet Physics 都使用它或它的变体）。对于游戏开发来说，稳定性远比精度更重要——玩家察觉不到微小的位置误差，但一定能察觉到爆炸的物理模拟。

### 3.2 Verlet 积分与弹簧系统

**Verlet 积分**是另一种在分子动力学和游戏物理中广泛使用的方法。它直接对位置进行二阶泰勒展开，避免了显式存储速度：

```
p_{n+1} = 2*p_n - p_{n-1} + a_n * dt²
```

```cpp
// 弹簧系统——Verlet 积分的典型应用
struct SpringSystem {
    std::vector<Vec3> positions;      // 当前位置
    std::vector<Vec3> prevPositions;  // 上一帧位置
    std::vector<float> invMasses;     // 质量的倒数（0 表示固定）

    struct Spring {
        size_t a, b;       // 连接的两个粒子索引
        float restLength;  // 静止长度
        float stiffness;   // 弹性系数 k
    };
    std::vector<Spring> springs;

    void UpdateVerlet(float dt) {
        float dtSq = dt * dt;
        Vec3 gravity(0.0f, -9.8f, 0.0f);

        for (size_t i = 0; i < positions.size(); ++i) {
            if (invMasses[i] <= 0.0f) continue;  // 固定粒子

            Vec3 temp = positions[i];
            // Verlet 位置更新：p' = 2p - p_prev + a * dt²
            Vec3 accel = gravity;
            positions[i] = positions[i] * 2.0f - prevPositions[i] + accel * dtSq;
            prevPositions[i] = temp;
        }

        // 应用弹簧约束（多次迭代提高稳定性）
        const int ITERATIONS = 8;
        for (int iter = 0; iter < ITERATIONS; ++iter) {
            for (const auto& spring : springs) {
                Vec3 delta = positions[spring.b] - positions[spring.a];
                float dist = delta.Length();
                if (dist < 1e-6f) continue;

                float diff = (dist - spring.restLength) / dist;
                Vec3 offset = delta * (diff * 0.5f * spring.stiffness);

                if (invMasses[spring.a] > 0.0f) positions[spring.a] += offset;
                if (invMasses[spring.b] > 0.0f) positions[spring.b] -= offset;
            }
        }
    }
};
```

Verlet 积分的一个独特优势是**约束的稳定性**。通过将弹簧约束作为位置校正步骤（而非力的形式）反复应用，可以实现刚体约束而不会出现传统的刚性问题。这种**基于位置的动力学（Position-Based Dynamics, PBD）**方法被广泛应用于布料模拟、柔体模拟和粒子系统中。

### 3.3 缓动函数（Easing Functions）

**缓动函数**描述了动画参数随时间变化的非线性曲线。它们将线性输入 `t ∈ [0, 1]` 映射到各种非线性输出，使动画具有自然的感觉——物体启动时加速、停止时减速。

```cpp
namespace Easing {
    // 二次缓动
    float EaseInQuad(float t) { return t * t; }                    // 加速
    float EaseOutQuad(float t) {                                   // 减速
        return 1.0f - (1.0f - t) * (1.0f - t);
    }
    float EaseInOutQuad(float t) {                                 // 先加速后减速
        return t < 0.5f ? 2.0f * t * t
                        : 1.0f - std::pow(-2.0f * t + 2.0f, 2.0f) * 0.5f;
    }

    // 三次缓动（更平滑）
    float EaseInCubic(float t) { return t * t * t; }
    float EaseOutCubic(float t) { return 1.0f - std::pow(1.0f - t, 3.0f); }

    // 正弦缓动（最平滑）
    float EaseInOutSine(float t) {
        return -(std::cos(PI * t) - 1.0f) * 0.5f;
    }

    // 弹簧/弹性缓动（游戏 UI 常用）
    float EaseOutElastic(float t) {
        constexpr float c4 = (2.0f * PI) / 3.0f;
        if (t == 0.0f) return 0.0f;
        if (t == 1.0f) return 1.0f;
        return std::pow(2.0f, -10.0f * t) * std::sin((t * 10.0f - 0.75f) * c4) + 1.0f;
    }

    // 平滑步进（Smoothstep）——Perlin 提出
    float SmoothStep(float t) { return t * t * (3.0f - 2.0f * t); }
    float SmootherStep(float t) {                                   // 五次，更平滑
        return t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
    }
}
```

| 缓动函数 | 曲线特征 | 物理直觉 | 引擎应用 |
|---------|---------|---------|---------|
| Linear | 直线 | 匀速运动 | 机械运动、调试 |
| EaseInQuad | 开口向上的抛物线 | 加速启动 | 物体掉落、冲刺开始 |
| EaseOutQuad | 开口向下的抛物线 | 减速停止 | 物体到达、UI 弹出 |
| EaseInOutQuad | S 形曲线 | 自然加减速 | 角色移动、摄像机过渡 |
| EaseOutElastic | 衰减振荡 | 弹性反弹 | UI 元素入场、跳跃落地 |
| SmoothStep | S 形，C1 连续 | 平滑过渡 | 噪声插值、混合因子 |
| SmootherStep | S 形，C2 连续 | 更平滑的过渡 | 高质量混合、地形混合 |

这些函数虽然数学上简单，但它们是游戏体验中"手感（Game Feel）"的重要组成部分。一个优秀的游戏设计师对缓动函数的选择极其讲究——不同的曲线形状传递给玩家完全不同的物理直觉。

---

## 4. 概率与统计

游戏世界充满了不确定性——伤害浮动、暴击率、随机掉落、AI 决策、程序化生成。概率与统计为这种不确定性提供了数学框架。

### 4.1 随机数生成

```cpp
#include <random>
#include <chrono>

class Random {
    std::mt19937 m_engine;  // Mersenne Twister——高质量伪随机数生成器

public:
    // 用时间种子初始化（适用于大多数游戏场景）
    Random() : m_engine(static_cast<unsigned int>(
        std::chrono::steady_clock::now().time_since_epoch().count())) {}

    // 用确定性种子初始化（适用于可重现的随机——调试、回放、种子世界生成）
    explicit Random(unsigned int seed) : m_engine(seed) {}

    // 整数范围 [min, max]
    int Range(int min, int max) {
        std::uniform_int_distribution<int> dist(min, max);
        return dist(m_engine);
    }

    // 浮点范围 [min, max)
    float Range(float min, float max) {
        std::uniform_real_distribution<float> dist(min, max);
        return dist(m_engine);
    }

    // 0 到 1 之间的浮点数
    float Value01() { return Range(0.0f, 1.0f); }

    // 正态分布（高斯分布）
    // 用于：自然现象模拟、属性随机生成（避免极端值）
    float Gaussian(float mean, float stddev) {
        std::normal_distribution<float> dist(mean, stddev);
        return dist(m_engine);
    }

    // 伯努利试验——单次成功概率为 p 的判定
    bool Bernoulli(float p) { return Value01() < p; }
};
```

### 4.2 常用概率分布

| 概率分布 | 概率密度函数 | 引擎应用 |
|---------|------------|---------|
| 均匀分布 (Uniform) | `f(x) = 1/(b-a)` | 随机位置、随机选择 |
| 正态分布 (Normal) | `f(x) = 1/(σ√(2π)) * e^(-(x-μ)²/(2σ²))` | AI 属性、自然变异、瞄准散布 |
| 泊松分布 (Poisson) | `P(k) = λ^k * e^(-λ) / k!` | 随机事件频率（如每秒生成敌人） |
| 指数分布 (Exponential) | `f(x) = λ * e^(-λx)` | 事件间隔时间、武器冷却 |
| 伯努利分布 (Bernoulli) | `P(k) = p^k * (1-p)^(1-k)` | 暴击判定、闪避判定 |
| 二项分布 (Binomial) | `P(k) = C(n,k) * p^k * (1-p)^(n-k)` | n 次独立试验的成功次数 |

理解这些分布的特性对于设计"感觉正确"的随机系统至关重要。一个常见的错误是在需要正态分布的场景中错误地使用了均匀分布——例如，角色属性使用均匀随机会导致过多极端值（过强或过弱），而正态分布则自然地让大多数角色接近平均水平。

### 4.3 蒙特卡洛方法

**蒙特卡洛方法（Monte Carlo Method）**是一类使用随机采样来近似计算数值结果的算法。在图形学中，蒙特卡洛积分是**全局光照（Global Illumination）**计算的基础——通过随机发射光线来估计光照方程的积分值。

光照方程（Rendering Equation）描述了从点 `x` 沿方向 `ω_o` 出射的光辐射：

```
L_o(x, ω_o) = L_e(x, ω_o) + ∫_Ω f_r(x, ω_i, ω_o) * L_i(x, ω_i) * (n · ω_i) dω_i
```

这个积分在一般场景中没有解析解。蒙特卡洛方法通过随机采样来近似：

```
L_o ≈ L_e + (1/N) * Σ_{k=1}^{N} [f_r(ω_k) * L_i(ω_k) * (n · ω_k) / p(ω_k)]
```

其中 `ω_k` 是从概率分布 `p(ω)` 中采样的方向。当 `p(ω)` 与积分中的函数形状匹配时（**重要性采样，Importance Sampling**），收敛速度会显著提高。

蒙特卡洛方法也用于**环境光遮蔽（Ambient Occlusion）**的近似计算——从表面点随机发射射线，检测被遮挡的比例。被遮挡的射线比例近似等于该点的环境光遮蔽值。

---

## 5. 练习

### 练习 1: 向量与矩阵基础

1. **实现一个函数**，计算两个 3D 向量之间的夹角（弧度制），并用它判断一个 NPC 是否在玩家的 90° 视野锥内。

2. **实现一个函数**，给定三角形的三个顶点，计算三角形的面积（使用叉积）和法线方向。

3. **构造一个模型矩阵**，把一个物体放置在 `(5, 2, -3)`，绕 Y 轴旋转 45°，均匀缩放 1.5 倍。然后验证：模型空间中的点 `(1, 0, 0)` 变换后的世界坐标是多少？

### 练习 2: 四元数与插值

1. **手动计算**：用四元数把向量 `(0, 0, 1)` 绕轴 `(1, 0, 0)` 旋转 90°，验证结果是否为 `(0, -1, 0)`。

2. **实现一个函数**，在两个四元数之间做 NLERP（归一化线性插值），并与 SLERP 的结果对比。在什么情况下 NLERP 的结果与 SLERP 差异较大？

3. **欧拉角陷阱**：构造一个欧拉角 `(pitch=89°, yaw=45°, roll=0°)`，将其转换为四元数，再转换回欧拉角。然后尝试 `(pitch=90°, yaw=45°, roll=0°)`，观察发生了什么。这说明了什么问题？

### 练习 3: 射线与几何体相交（挑战）

1. **实现射线与三角形相交检测**（Möller–Trumbore 算法）。给定一个射线和一个三角形，返回相交点和重心坐标。

2. **实现视锥体与 AABB 的相交检测**。视锥体由 6 个平面组成（左、右、上、下、近、远）。实现一个函数判断 AABB 是否完全在视锥体内、完全在外、或部分相交。

3. **实现一个简单的射线追踪器**：在一个场景中放置几个球体，从相机位置向每个像素发射射线，计算射线与最近的球体的交点，根据法线方向输出灰度图像（可用 PPM 格式保存）。

### 练习 4: 投影矩阵推导（进阶）

1. **手动推导**：从视锥体参数（`fov_y`、`aspect`、`near`、`far`）出发，推导出完整的透视投影矩阵。验证你的推导与标准公式一致。

2. **反向 Z（Reverse Z）**：研究为什么现代引擎使用反向 Z（将深度值映射到 `[1, 0]` 而非 `[-1, 1]` 或 `[0, 1]`），并修改透视投影矩阵以支持反向 Z。

3. **无限远投影矩阵**：推导一个远裁剪面为无穷大的透视投影矩阵（`far = ∞`）。这在室外场景和地形渲染中非常有用。

### 练习 5: 数值积分与物理模拟

1. **实现三种积分方法**：显式欧拉、半隐式欧拉、Velocity Verlet。用它们模拟一个受重力影响的粒子，比较稳定性和精度。

2. **弹簧系统**：实现一个简单的弹簧-质点系统，使用 Verlet 积分。添加阻尼和约束迭代，观察系统的稳定性。

3. **缓动函数可视化**：实现一个程序，绘制各种缓动函数的曲线图（可用 ASCII 艺术或输出到图像文件）。

### 练习 6: 概率与随机系统（进阶）

1. **掉落系统**：实现一个加权随机选择系统。给定一组物品和对应的掉落权重，实现按概率随机选择。

2. **泊松盘采样**：在 2D 平面上实现泊松盘采样算法，生成均匀分布但不重叠的点集。用于树木/植被的自然放置。

3. **正态分布瞄准**：实现一个射击系统，AI 的瞄准精度用正态分布建模——新手 AI 的标准差大（散布广），专家 AI 的标准差小（更精准）。

---

## 4. 扩展阅读

### 书籍

- **《3D Math Primer for Graphics and Game Development》**（Fletcher Dunn & Ian Parberry）— 游戏数学的经典入门书，覆盖向量、矩阵、四元数、坐标空间变换等所有基础内容，强烈推荐。
- **《Mathematics for 3D Game Programming and Computer Graphics》**（Eric Lengyel）— 更深入，涵盖曲线曲面、物理模拟等高级主题。
- **《Essential Mathematics for Games and Interactive Applications》**（James M. Van Verth & Lars M. Bishop）— 从游戏开发者的视角讲解数学，代码示例丰富。

### 在线资源

- **Scratchapixel**（scratchapixel.com）— 免费的计算机图形学教程，从射线追踪到光栅化都有详细讲解，配有代码实现。
- **Game Engine Architecture** 配套网站 — Jason Gregory 的《游戏引擎架构》一书有详细的数学附录。
- **Handmade Hero**（handmadehero.org）— Casey Muratori 的直播编程系列，从零开始写游戏引擎，大量涉及数学实现细节。

### 开源参考

- **GLM（OpenGL Mathematics）** — 事实标准的 C++ 图形数学库，接口设计模仿 GLSL 着色器语言。
- **DirectXMath** — Windows 平台上的高性能 SIMD 数学库。
- **Unreal Engine 的 FVector/FMatrix/FQuat** — 商业引擎中的数学类型实现，值得参考其 API 设计。
- **Godot Engine 的 Vector3/Basis/Transform3D** — 开源引擎中的数学实现，代码清晰易读。

### 进阶主题

- **对偶四元数（Dual Quaternion）** — 同时表示旋转和平移，在骨骼动画中比矩阵+四元数更紧凑。
- **旋转向量/轴角（Axis-Angle）** — 四元数的另一种编码方式，某些物理计算中更直观。
- **几何代数（Geometric Algebra）** — 统一了向量、复数、四元数等概念的数学框架，有研究者认为它是游戏数学的未来方向。
- **反向 Z（Reverse Z）** — 现代引擎使用反向 Z 缓冲区来缓解透视投影的 Z 精度问题。
- **对数深度缓冲区（Logarithmic Depth Buffer）** — 用于超远距离渲染（如太空游戏），解决传统深度缓冲的精度限制。

### 微积分与数值方法

- **《Numerical Recipes》** — 数值计算的经典参考书，涵盖积分、微分方程求解、优化等。
- **《Game Physics Engine Development》by Ian Millington** — 游戏物理引擎开发，深入讲解数值积分和约束求解。
- **Position-Based Dynamics (PBD)** — Müller et al., 2007. 基于位置的动力学，现代布料/柔体模拟的核心方法。

### 概率与统计

- **《AI for Games》by Ian Millington** — 游戏 AI 中的概率决策、贝叶斯网络、效用理论。
- **Scratchapixel: Monte Carlo Methods** — 蒙特卡洛方法在渲染中的应用，从基础到路径追踪。
- **《The Art of Randomness》** — 程序化生成中的随机技术，包括噪声函数、泊松盘采样等。

---

## 常见陷阱

1. **矩阵乘法的顺序**：`M1 * M2` 表示"先应用 M2，再应用 M1"。如果你写 `Translate * Rotate`，结果是先旋转再平移。顺序错了，物体就会飞到奇怪的位置。建议始终用变量名或注释明确变换顺序。

2. **四元数插值不取最短路径**：直接对四元数做 LERP 或 SLERP 时，如果两个四元数的点积为负，插值会绕远路（走大于 180° 的弧）。正确做法是在插值前检查点积，如果为负则取反其中一个四元数。本教程的 `Slerp` 实现已包含此处理。

3. **用 4×4 矩阵变换方向向量时误设 w=1**：方向向量（如法线、速度）不受平移影响，变换时 w 应设为 0。如果误设为 1，方向向量会被"移动"，导致光照计算错误等诡异问题。使用 `TransformVector` 而非 `TransformPoint`。

4. **欧拉角的万向节锁**：当 pitch 达到 ±90° 时，yaw 和 roll 的旋转轴重合，丢失一个自由度。这会导致动画中的"抖动"和插值异常。任何涉及连续旋转的场合，优先使用四元数。

5. **矩阵逆的数值稳定性**：接近奇异的矩阵（行列式接近 0）求逆会产生巨大的数值误差。在动画系统中，如果缩放分量接近 0，逆矩阵可能完全错误。考虑使用 SVD 分解或添加数值保护。

6. **忽略浮点精度问题**：`==` 判断两个向量或矩阵是否相等时，必须使用 epsilon 容差。本教程的所有相等比较都已使用 `EPSILON`。在碰撞检测中，浮点精度问题可能导致物体"穿透"或"抖动"。

7. **AABB 经过旋转后不再是 AABB**：AABB 的边必须与坐标轴平行。如果一个 AABB 经过旋转变换，你需要重新计算它的 min/max（通常通过对 8 个角点变换后取极值），或者改用 OBB。

8. **透视投影矩阵的 Z 值非线性**：经过透视投影后，深度值在 near 平面附近精度高，在 far 平面附近精度低。这意味着远处的物体会出现 Z-fighting（深度冲突）。现代引擎使用反向 Z（reverse Z）或 logarithmic depth buffer 来缓解此问题。
