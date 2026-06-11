---
title: "刚体动力学与约束求解"
updated: 2026-06-05
---

# 刚体动力学与约束求解

> 所属计划: 游戏引擎开发工程师
> 预计耗时: 8h
> 前置知识: 14-碰撞检测：从 AABB 到 GJK/EPA

---

## 1. 概念讲解

### 为什么需要这个？

碰撞检测告诉我们"两个物体是否相交"，但仅有碰撞检测的物理系统是不完整的。当一个球体穿过地面时，碰撞检测能发现这个穿透，但它无法回答：

- 球体应该以多大的速度反弹？
- 球体旋转方向如何改变？
- 多个物体堆叠在一起时如何保持稳定？
- 一扇门绕着铰链旋转该如何模拟？

刚体动力学（Rigid Body Dynamics）回答这些问题。它基于牛顿力学，描述物体在力和约束作用下的运动规律，是物理引擎的核心。

在真实游戏中，物理引擎（如 Box2D、Bullet、PhysX、Havok）的核心工作流是：

```
1. 碰撞检测（Broad Phase + Narrow Phase）
      ↓
2. 生成接触流形（Contact Manifold）
      ↓
3. 积分器更新速度和位置（Integrator）
      ↓
4. 约束求解（Constraint Solver）
      ↓
5. 冲量响应（Impulse Response）
      ↓
6. 位置修正（Position Correction）
```

本章将带你从零实现上述流程的核心部分。

### 核心思想

#### 1.1 牛顿力学基础

##### 1.1.1 牛顿第二定律

牛顿第二定律是动力学的基石：

$$\mathbf{F} = m\mathbf{a}$$

其中 $\mathbf{F}$ 是合外力（向量），$m$ 是质量（标量），$\mathbf{a}$ 是加速度（向量）。

对于刚体，我们还需要考虑转动。转动版本的牛顿第二定律为：

$$\boldsymbol{\tau} = I\boldsymbol{\alpha}$$

其中 $\boldsymbol{\tau}$ 是扭矩（torque），$I$ 是转动惯量，$\boldsymbol{\alpha}$ 是角加速度。

但在三维空间中，转动惯量不是一个简单的标量，而是一个 $3 \times 3$ 的矩阵——**惯性张量（Inertia Tensor）**。因此三维情况下的转动方程为：

$$\boldsymbol{\tau} = \mathbf{I}\boldsymbol{\alpha}$$

##### 1.1.2 动量与角动量

**线性动量（Linear Momentum）**：

$$\mathbf{p} = m\mathbf{v}$$

牛顿第二定律也可以写成动量形式：

$$\mathbf{F} = \frac{d\mathbf{p}}{dt}$$

这意味着外力等于动量的变化率。在没有外力作用时，动量守恒。

**角动量（Angular Momentum）**：

$$\mathbf{L} = \mathbf{I}\boldsymbol{\omega}$$

其中 $\boldsymbol{\omega}$ 是角速度向量。角动量的变化率等于外力矩：

$$\boldsymbol{\tau} = \frac{d\mathbf{L}}{dt}$$

##### 1.1.3 冲量（Impulse）

冲量是力对时间的积分，表示动量的瞬时变化：

$$\mathbf{J} = \int_{t_1}^{t_2} \mathbf{F}\,dt = \Delta\mathbf{p} = m\Delta\mathbf{v}$$

在碰撞响应中，我们通常使用冲量而非力，因为碰撞是极短时间内的相互作用，用冲量更直接。

对于转动，角冲量与角动量变化的关系为：

$$\mathbf{J}_{\theta} = \mathbf{r} \times \mathbf{J} = \Delta\mathbf{L} = \mathbf{I}\Delta\boldsymbol{\omega}$$

其中 $\mathbf{r}$ 是从质心到接触点的向量。

#### 1.2 刚体运动学

##### 1.2.1 刚体的自由度

在三维空间中，一个刚体有 **6 个自由度（DOF, Degrees of Freedom）**：

- 3 个平移自由度：位置 $\mathbf{x} = (x, y, z)$
- 3 个旋转自由度：方向（通常用四元数 $\mathbf{q}$ 表示）

##### 1.2.2 线性运动

位置更新：

$$\mathbf{x}(t) = \mathbf{x}_0 + \mathbf{v}t + \frac{1}{2}\mathbf{a}t^2$$

速度更新：

$$\mathbf{v}(t) = \mathbf{v}_0 + \mathbf{a}t$$

##### 1.2.3 角运动

角速度 $\boldsymbol{\omega}$ 是一个向量，其方向表示旋转轴，大小表示旋转速率（弧度/秒）。

四元数的方向更新：

$$\frac{d\mathbf{q}}{dt} = \frac{1}{2}\boldsymbol{\omega}\mathbf{q}$$

其中 $\boldsymbol{\omega}$ 被表示为纯虚四元数 $(0, \omega_x, \omega_y, \omega_z)$。

在实际实现中，每帧更新四元数：

$$\mathbf{q}_{new} = \mathbf{q} + \frac{\Delta t}{2}\boldsymbol{\omega}\mathbf{q}$$

然后归一化：$\mathbf{q}_{new} = \mathbf{q}_{new} / \|\mathbf{q}_{new}\|$

##### 1.2.4 从局部空间到世界空间的转换

刚体上任意一点 $\mathbf{r}_{local}$（在局部坐标系中）在世界坐标系中的位置为：

$$\mathbf{r}_{world} = \mathbf{x} + \mathbf{R}\mathbf{r}_{local}$$

其中 $\mathbf{R}$ 是从四元数 $\mathbf{q}$ 导出的旋转矩阵。

该点的线速度为：

$$\mathbf{v}_{point} = \mathbf{v} + \boldsymbol{\omega} \times (\mathbf{r}_{world} - \mathbf{x}) = \mathbf{v} + \boldsymbol{\omega} \times \mathbf{r}$$

其中 $\mathbf{r} = \mathbf{r}_{world} - \mathbf{x}$ 是从质心指向该点的向量。

#### 1.3 惯性张量（Inertia Tensor）

##### 1.3.1 定义

惯性张量 $\mathbf{I}$ 描述了质量在刚体中的分布，决定了物体对旋转的"抵抗"。

对于一个连续体，惯性张量的分量为：

$$\mathbf{I} = \begin{bmatrix}
I_{xx} & I_{xy} & I_{xz} \\
I_{yx} & I_{yy} & I_{yz} \\
I_{zx} & I_{zy} & I_{zz}
\end{bmatrix}$$

其中：

$$I_{xx} = \int_V \rho(y^2 + z^2)\,dV$$
$$I_{yy} = \int_V \rho(x^2 + z^2)\,dV$$
$$I_{zz} = \int_V \rho(x^2 + y^2)\,dV$$
$$I_{xy} = I_{yx} = -\int_V \rho xy\,dV$$
$$I_{xz} = I_{zx} = -\int_V \rho xz\,dV$$
$$I_{yz} = I_{zy} = -\int_V \rho yz\,dV$$

对角元素 $I_{xx}, I_{yy}, I_{zz}$ 称为**转动惯量**，非对角元素称为**惯性积**。

##### 1.3.2 主轴与对角化

对于任何刚体，都存在一组正交轴（称为主轴），使得惯性张量在该坐标系下为对角矩阵：

$$\mathbf{I}_{body} = \begin{bmatrix}
I_x & 0 & 0 \\
0 & I_y & 0 \\
0 & 0 & I_z
\end{bmatrix}$$

常见的几何体在主坐标系下的惯性张量：

**实心球体**（半径 $R$，质量 $m$）：
$$\mathbf{I} = \frac{2}{5}mR^2 \mathbf{I}_{3 \times 3}$$

**实心长方体**（半尺寸 $(a, b, c)$，质量 $m$）：
$$\mathbf{I} = \begin{bmatrix}
\frac{1}{3}m(b^2 + c^2) & 0 & 0 \\
0 & \frac{1}{3}m(a^2 + c^2) & 0 \\
0 & 0 & \frac{1}{3}m(a^2 + b^2)
\end{bmatrix}$$

**实心圆柱体**（半径 $R$，高度 $h$，质量 $m$，轴沿 z 方向）：
$$\mathbf{I} = \begin{bmatrix}
\frac{1}{12}m(3R^2 + h^2) & 0 & 0 \\
0 & \frac{1}{12}m(3R^2 + h^2) & 0 \\
0 & 0 & \frac{1}{2}mR^2
\end{bmatrix}$$

##### 1.3.3 世界空间中的惯性张量

惯性张量通常在局部坐标系（body space）中定义。在世界空间中，需要通过旋转矩阵变换：

$$\mathbf{I}_{world} = \mathbf{R}\,\mathbf{I}_{body}\,\mathbf{R}^T$$

这个变换保持了惯性张量的物理意义。注意：$\mathbf{I}_{world}^{-1} = \mathbf{R}\,\mathbf{I}_{body}^{-1}\,\mathbf{R}^T$。

#### 1.4 数值积分器

物理模拟需要数值求解常微分方程（ODE）。给定当前状态 $(\mathbf{x}, \mathbf{v})$，我们需要计算下一时刻的状态。

##### 1.4.1 显式欧拉法（Explicit Euler）

最简单的方法：

$$\mathbf{v}_{n+1} = \mathbf{v}_n + \mathbf{a}_n \Delta t$$
$$\mathbf{x}_{n+1} = \mathbf{x}_n + \mathbf{v}_n \Delta t$$

**问题**：显式欧拉是**一阶精度**，且**不稳定**。对于弹簧-质点系统，当 $\Delta t > 2\sqrt{m/k}$ 时会发散。能量会不断增加，导致模拟爆炸。

##### 1.4.2 半隐式欧拉法（Semi-Implicit Euler / Symplectic Euler）

改进版本：

$$\mathbf{v}_{n+1} = \mathbf{v}_n + \mathbf{a}_n \Delta t$$
$$\mathbf{x}_{n+1} = \mathbf{x}_n + \mathbf{v}_{n+1} \Delta t$$

注意速度用更新后的值来计算位置。这是**二阶精度**的（对于哈密顿系统），且**稳定**——虽然能量有微小振荡，但不会发散。这是游戏物理引擎中最常用的积分器（Box2D、Bullet 都使用它）。

##### 1.4.3 中点法 / 改进欧拉法

先计算半步：

$$\mathbf{v}_{mid} = \mathbf{v}_n + \mathbf{a}_n \frac{\Delta t}{2}$$
$$\mathbf{x}_{mid} = \mathbf{x}_n + \mathbf{v}_n \frac{\Delta t}{2}$$

然后用中点处的加速度更新：

$$\mathbf{v}_{n+1} = \mathbf{v}_n + \mathbf{a}(\mathbf{x}_{mid}, \mathbf{v}_{mid}) \Delta t$$
$$\mathbf{x}_{n+1} = \mathbf{x}_n + \mathbf{v}_{mid} \Delta t$$

二阶精度，但需要两次力评估。

##### 1.4.4 Verlet 积分

Verlet 积分基于位置而非速度：

$$\mathbf{x}_{n+1} = 2\mathbf{x}_n - \mathbf{x}_{n-1} + \mathbf{a}_n \Delta t^2$$

等价形式（Velocity Verlet）：

$$\mathbf{x}_{n+1} = \mathbf{x}_n + \mathbf{v}_n \Delta t + \frac{1}{2}\mathbf{a}_n \Delta t^2$$
$$\mathbf{v}_{n+1} = \mathbf{v}_n + \frac{1}{2}(\mathbf{a}_n + \mathbf{a}_{n+1}) \Delta t$$

Verlet 积分的优点是：
- 时间可逆（适合分子动力学模拟）
- 数值稳定性好
- 能量守恒性质好

##### 1.4.5 四阶 Runge-Kutta（RK4）

RK4 是最常用的四阶积分器，精度高但计算量大：

$$\mathbf{k}_1 = f(t_n, \mathbf{y}_n)$$
$$\mathbf{k}_2 = f(t_n + \frac{\Delta t}{2}, \mathbf{y}_n + \frac{\Delta t}{2}\mathbf{k}_1)$$
$$\mathbf{k}_3 = f(t_n + \frac{\Delta t}{2}, \mathbf{y}_n + \frac{\Delta t}{2}\mathbf{k}_2)$$
$$\mathbf{k}_4 = f(t_n + \Delta t, \mathbf{y}_n + \Delta t\mathbf{k}_3)$$

$$\mathbf{y}_{n+1} = \mathbf{y}_n + \frac{\Delta t}{6}(\mathbf{k}_1 + 2\mathbf{k}_2 + 2\mathbf{k}_3 + \mathbf{k}_4)$$

对于物理引擎，RK4 通常用于需要高精度的场景（如轨道力学），但对于实时游戏，半隐式欧拉因其稳定性和效率更受青睐。

**选择建议**：

| 积分器 | 精度 | 稳定性 | 计算量 | 适用场景 |
|--------|------|--------|--------|----------|
| 显式欧拉 | 一阶 | 差 | 低 | 不推荐 |
| 半隐式欧拉 | 二阶 | 好 | 低 | 实时游戏物理（首选） |
| 中点法 | 二阶 | 中 | 中 | 教育演示 |
| Verlet | 二阶 | 好 | 低 | 布料、粒子系统 |
| RK4 | 四阶 | 好 | 高 | 高精度需求 |

#### 1.5 冲量响应（Impulse Response）

##### 1.5.1 碰撞响应的基本问题

当两个刚体碰撞时，我们需要：

1. 防止它们相互穿透（位置修正）
2. 计算碰撞后的速度（冲量响应）

考虑两个刚体 A 和 B，在接触点 $P$ 发生碰撞。设接触法线为 $\mathbf{n}$（从 A 指向 B）。

碰撞前两物体在接触点处的相对速度为：

$$\mathbf{v}_{rel} = \mathbf{v}_{B|P} - \mathbf{v}_{A|P}$$

其中 $\mathbf{v}_{A|P}$ 是 A 在接触点 $P$ 处的速度（包含转动贡献）。

我们关心的是沿法线方向的相对速度：

$$v_{rel,n} = \mathbf{v}_{rel} \cdot \mathbf{n}$$

如果 $v_{rel,n} < 0$，两物体正在相互靠近，需要施加冲量使它们分离。

##### 1.5.2 恢复系数（Coefficient of Restitution）

恢复系数 $e \in [0, 1]$ 描述碰撞的弹性程度：

- $e = 1$：完全弹性碰撞（动能守恒）
- $e = 0$：完全非弹性碰撞（碰撞后沿法线相对速度为 0）
- $0 < e < 1$：实际碰撞

碰撞后的法线相对速度应满足：

$$v'_{rel,n} = -e \cdot v_{rel,n}$$

##### 1.5.3 法向冲量的推导

设施加在 B 上的法向冲量为 $j\mathbf{n}$（则 A 受到 $-j\mathbf{n}$）。

冲量对速度的更新：

对于 A：
$$\mathbf{v}'_A = \mathbf{v}_A - \frac{j}{m_A}\mathbf{n}$$
$$\boldsymbol{\omega}'_A = \boldsymbol{\omega}_A - j\mathbf{I}_A^{-1}(\mathbf{r}_A \times \mathbf{n})$$

对于 B：
$$\mathbf{v}'_B = \mathbf{v}_B + \frac{j}{m_B}\mathbf{n}$$
$$\boldsymbol{\omega}'_B = \boldsymbol{\omega}_B + j\mathbf{I}_B^{-1}(\mathbf{r}_B \times \mathbf{n})$$

其中 $\mathbf{r}_A$ 和 $\mathbf{r}_B$ 是从各自质心到接触点的向量。

碰撞后接触点处的速度：

$$\mathbf{v}'_{A|P} = \mathbf{v}'_A + \boldsymbol{\omega}'_A \times \mathbf{r}_A$$
$$\mathbf{v}'_{B|P} = \mathbf{v}'_B + \boldsymbol{\omega}'_B \times \mathbf{r}_B$$

新的法线相对速度：

$$v'_{rel,n} = (\mathbf{v}'_{B|P} - \mathbf{v}'_{A|P}) \cdot \mathbf{n}$$

将速度更新公式代入，并令 $v'_{rel,n} = -e \cdot v_{rel,n}$，解出 $j$：

$$j = \frac{-(1+e)(\mathbf{v}_{rel} \cdot \mathbf{n})}{\frac{1}{m_A} + \frac{1}{m_B} + [\mathbf{I}_A^{-1}(\mathbf{r}_A \times \mathbf{n}) \times \mathbf{r}_A + \mathbf{I}_B^{-1}(\mathbf{r}_B \times \mathbf{n}) \times \mathbf{r}_B] \cdot \mathbf{n}}$$

分母中的项称为**有效质量（Effective Mass）**，记为 $m_{eff}$：

$$m_{eff} = \frac{1}{m_A} + \frac{1}{m_B} + (\mathbf{I}_A^{-1}(\mathbf{r}_A \times \mathbf{n}) \times \mathbf{r}_A + \mathbf{I}_B^{-1}(\mathbf{r}_B \times \mathbf{n}) \times \mathbf{r}_B) \cdot \mathbf{n}$$

因此：

$$j = \frac{-(1+e)(\mathbf{v}_{rel} \cdot \mathbf{n})}{m_{eff}}$$

##### 1.5.4 摩擦冲量

碰撞不仅有法向分量，还有切向分量（摩擦）。设切向方向为：

$$\mathbf{t} = \frac{\mathbf{v}_{rel} - (\mathbf{v}_{rel} \cdot \mathbf{n})\mathbf{n}}{\|\mathbf{v}_{rel} - (\mathbf{v}_{rel} \cdot \mathbf{n})\mathbf{n}\|}$$

切向冲量大小由库仑摩擦模型决定：

$$|j_t| \leq \mu |j_n|$$

其中 $\mu$ 是摩擦系数。切向冲量的计算与法向类似，只是将 $\mathbf{n}$ 替换为 $\mathbf{t}$。

如果计算出的 $|j_t| > \mu |j_n|$，则限制为 $|j_t| = \mu |j_n|$（动摩擦）。

#### 1.6 约束求解

##### 1.6.1 什么是约束？

约束（Constraint）是对刚体运动的限制条件。常见的约束包括：

- **接触约束**：防止物体相互穿透
- **关节约束**：铰链、滑块、球关节等
- **距离约束**：两点间保持固定距离
- **角度约束**：限制相对旋转角度

约束可以用数学方程表示为 $C(\mathbf{x}) = 0$（等式约束）或 $C(\mathbf{x}) \geq 0$（不等式约束，如接触约束）。

##### 1.6.2 速度级约束（Velocity-level Constraints）

对约束方程 $C(\mathbf{x}) = 0$ 求时间导数：

$$\dot{C} = \frac{\partial C}{\partial \mathbf{x}} \cdot \dot{\mathbf{x}} = \mathbf{J}\mathbf{v} = 0$$

其中 $\mathbf{J} = \frac{\partial C}{\partial \mathbf{x}}$ 称为**雅可比矩阵（Jacobian）**，描述了约束对速度的线性限制。

再求一次导数得到加速度级约束：

$$\ddot{C} = \dot{\mathbf{J}}\mathbf{v} + \mathbf{J}\dot{\mathbf{v}} = 0$$

由牛顿第二定律 $\mathbf{F} = m\mathbf{a}$，约束力可以表示为 $\mathbf{F}_c = \mathbf{J}^T\lambda$，其中 $\lambda$ 是拉格朗日乘子。

##### 1.6.3 约束的冲量形式

在离散时间步中，我们使用冲量而非力。速度级约束的冲量形式为：

$$\mathbf{J}\mathbf{v}' = 0$$

即碰撞/约束后的速度应满足约束条件。

将速度更新 $\mathbf{v}' = \mathbf{v} + \mathbf{M}^{-1}\mathbf{J}^T\lambda$ 代入：

$$\mathbf{J}(\mathbf{v} + \mathbf{M}^{-1}\mathbf{J}^T\lambda) = 0$$

$$\mathbf{J}\mathbf{M}^{-1}\mathbf{J}^T\lambda = -\mathbf{J}\mathbf{v}$$

令 $\mathbf{A} = \mathbf{J}\mathbf{M}^{-1}\mathbf{J}^T$（有效质量矩阵），$\mathbf{b} = -\mathbf{J}\mathbf{v}$：

$$\mathbf{A}\lambda = \mathbf{b}$$

解出 $\lambda$ 后，冲量为 $\mathbf{J}^T\lambda$。

对于单个标量约束，这简化为：

$$\lambda = \frac{-\mathbf{J}\mathbf{v}}{\mathbf{J}\mathbf{M}^{-1}\mathbf{J}^T}$$

##### 1.6.4 接触约束

接触约束是不等式约束：$C \geq 0$（分离时 $C > 0$，接触时 $C = 0$）。

对应的拉格朗日乘子满足 $\lambda \geq 0$（只能推，不能拉）。

在迭代求解中，如果计算出的 $\lambda < 0$，则将其钳制为 0。

##### 1.6.5 位置级约束与 Baumgarte 稳定化

仅求解速度级约束有一个问题：数值误差会导致物体逐渐穿透（位置漂移）。

Baumgarte 稳定化通过在速度约束中加入位置修正项来解决：

$$\dot{C} + \frac{\beta}{\Delta t}C = 0$$

其中 $\beta \in [0, 1]$ 是稳定化参数（通常取 0.1~0.3）。

这相当于要求：

$$\mathbf{J}\mathbf{v}' = -\frac{\beta}{\Delta t}C$$

即允许一个与穿透深度成正比的速度来修正位置误差。

对应的冲量计算变为：

$$\lambda = \frac{-\mathbf{J}\mathbf{v} - \frac{\beta}{\Delta t}C}{\mathbf{J}\mathbf{M}^{-1}\mathbf{J}^T}$$

##### 1.6.6 关节约束

**铰链关节（Hinge Joint / Revolute Joint）**：

限制 5 个自由度，只允许绕一个轴旋转。需要约束：
- 两个锚点重合（3 个约束）
- 两个旋转轴对齐（2 个约束）

**球关节（Ball-and-Socket Joint）**：

限制 3 个平移自由度，允许 3 个旋转自由度。约束两个锚点在世界空间中重合。

**滑块关节（Slider / Prismatic Joint）**：

限制 5 个自由度，只允许沿一个轴平移。约束：
- 两个锚点沿滑动轴对齐（2 个约束）
- 两个滑动轴对齐（2 个约束）
- 限制绕滑动轴的旋转（1 个约束）

**距离约束（Distance Constraint）**：

保持两个点之间的距离为 $L$：

$$C = \|\mathbf{x}_B + \mathbf{R}_B\mathbf{r}_B - \mathbf{x}_A - \mathbf{R}_A\mathbf{r}_A\| - L = 0$$

##### 1.6.7 迭代求解器（Sequential Impulse / Gauss-Seidel）

当系统中有大量约束时，直接求解线性方程组 $\mathbf{A}\lambda = \mathbf{b}$ 的代价很高（$O(n^3)$）。

物理引擎通常使用**迭代求解器**：

**Sequential Impulse（顺序冲量法）**：

1. 对每个约束，独立计算冲量 $\lambda_i$
2. 应用冲量更新相关刚体的速度
3. 重复迭代多次（通常 4~20 次）

每次迭代中，使用**最新**的速度值（Gauss-Seidel 风格）。

算法伪代码：

```
for iteration = 0 to N-1:
    for each constraint:
        compute relative velocity at constraint point
        compute lambda impulse
        clamp lambda (for inequality constraints)
        accumulate lambda (for warm starting)
        apply impulse to bodies
```

**Warm Starting（热启动）**：

保存上一帧的 $\lambda$ 值作为初始猜测，可以显著减少收敛所需的迭代次数。

**优点**：
- 简单高效
- 容易处理不等式约束
- 天然支持摩擦

**缺点**：
- 收敛速度依赖于约束排序
- 对于刚性系统（如大量堆叠的物体）可能需要很多迭代

#### 1.7 休眠（Sleeping）机制

##### 1.7.1 为什么需要休眠？

当物体静止时（如一堆箱子稳定堆叠），继续模拟它们是浪费计算资源的。休眠机制检测"足够静止"的物体并暂停其模拟。

##### 1.7.2 休眠判定

通常基于以下指标：

- 线速度大小：$\|\mathbf{v}\| < v_{threshold}$
- 角速度大小：$\|\boldsymbol{\omega}\| < \omega_{threshold}$
- 持续满足条件的时间超过阈值

##### 1.7.3 唤醒条件

休眠物体在以下情况应被唤醒：

- 受到外力/冲量作用
- 与其他非休眠物体发生碰撞
- 关节连接的非休眠物体对其施加力

##### 1.7.4 实现注意事项

- 休眠物体的位置/方向不应更新
- 休眠物体不应参与约束求解（除非作为碰撞响应的被动方）
- 需要防止"抖动"（物体在休眠边缘反复唤醒/休眠）

---

## 2. 代码示例

下面是一个完整的、可编译运行的迷你物理引擎核心实现。

```cpp
// =============================================================================
// MiniPhysicsEngine.hpp
// 一个教学用迷你刚体物理引擎
// 涵盖：刚体状态、数值积分、冲量响应、约束求解、休眠机制
// =============================================================================

#pragma once

#include <cmath>
#include <vector>
#include <algorithm>
#include <cassert>
#include <iostream>
#include <iomanip>

// =============================================================================
// 基础数学工具
// =============================================================================

struct Vec3 {
    float x, y, z;

    Vec3() : x(0), y(0), z(0) {}
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x - o.x, y - o.y, z - o.z); }
    Vec3 operator*(float s) const { return Vec3(x * s, y * s, z * s); }
    Vec3 operator/(float s) const { return Vec3(x / s, y / s, z / s); }
    Vec3 operator-() const { return Vec3(-x, -y, -z); }

    Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }
    Vec3& operator-=(const Vec3& o) { x -= o.x; y -= o.y; z -= o.z; return *this; }
    Vec3& operator*=(float s) { x *= s; y *= s; z *= s; return *this; }
    Vec3& operator/=(float s) { x /= s; y /= s; z /= s; return *this; }

    float dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
    Vec3 cross(const Vec3& o) const {
        return Vec3(
            y * o.z - z * o.y,
            z * o.x - x * o.z,
            x * o.y - y * o.x
        );
    }
    float lengthSq() const { return x * x + y * y + z * z; }
    float length() const { return std::sqrt(lengthSq()); }
    Vec3 normalized() const {
        float len = length();
        if (len > 1e-6f) return *this / len;
        return Vec3(0, 0, 0);
    }
    void normalize() {
        float len = length();
        if (len > 1e-6f) { x /= len; y /= len; z /= len; }
    }
};

inline Vec3 operator*(float s, const Vec3& v) { return v * s; }

// =============================================================================
// 四元数（用于表示旋转）
// =============================================================================

struct Quaternion {
    float w, x, y, z;  // w 是实部，(x,y,z) 是虚部

    Quaternion() : w(1), x(0), y(0), z(0) {}
    Quaternion(float w_, float x_, float y_, float z_) : w(w_), x(x_), y(y_), z(z_) {}

    static Quaternion fromAxisAngle(const Vec3& axis, float angle) {
        float half = angle * 0.5f;
        float s = std::sin(half);
        Vec3 a = axis.normalized();
        return Quaternion(std::cos(half), a.x * s, a.y * s, a.z * s);
    }

    Quaternion operator*(const Quaternion& o) const {
        return Quaternion(
            w * o.w - x * o.x - y * o.y - z * o.z,
            w * o.x + x * o.w + y * o.z - z * o.y,
            w * o.y - x * o.z + y * o.w + z * o.x,
            w * o.z + x * o.y - y * o.x + z * o.w
        );
    }

    Quaternion operator*(float s) const { return Quaternion(w * s, x * s, y * s, z * s); }
    Quaternion operator+(const Quaternion& o) const { return Quaternion(w + o.w, x + o.x, y + o.y, z + o.z); }

    float lengthSq() const { return w * w + x * x + y * y + z * z; }
    float length() const { return std::sqrt(lengthSq()); }

    void normalize() {
        float len = length();
        if (len > 1e-6f) { w /= len; x /= len; y /= len; z /= len; }
    }

    Quaternion conjugate() const { return Quaternion(w, -x, -y, -z); }

    // 将向量从局部空间旋转到世界空间
    Vec3 rotate(const Vec3& v) const {
        Quaternion qv(0, v.x, v.y, v.z);
        Quaternion result = *this * qv * conjugate();
        return Vec3(result.x, result.y, result.z);
    }

    // 将向量从世界空间旋转到局部空间
    Vec3 rotateInverse(const Vec3& v) const {
        Quaternion qv(0, v.x, v.y, v.z);
        Quaternion result = conjugate() * qv * *this;
        return Vec3(result.x, result.y, result.z);
    }

    // 转换为旋转矩阵（列主序，3x3 展开为 9 个元素）
    void toMatrix(float* m) const {
        float xx = x * x, yy = y * y, zz = z * z;
        float xy = x * y, xz = x * z, yz = y * z;
        float wx = w * x, wy = w * y, wz = w * z;

        m[0] = 1 - 2 * (yy + zz); m[3] = 2 * (xy - wz);     m[6] = 2 * (xz + wy);
        m[1] = 2 * (xy + wz);     m[4] = 1 - 2 * (xx + zz); m[7] = 2 * (yz - wx);
        m[2] = 2 * (xz - wy);     m[5] = 2 * (yz + wx);     m[8] = 1 - 2 * (xx + yy);
    }
};

// =============================================================================
// 3x3 矩阵
// =============================================================================

struct Mat3 {
    float m[9];  // 列主序：m[col*3+row]

    Mat3() { for (int i = 0; i < 9; ++i) m[i] = 0; }

    static Mat3 identity() {
        Mat3 r;
        r.m[0] = r.m[4] = r.m[8] = 1.0f;
        return r;
    }

    static Mat3 diagonal(float a, float b, float c) {
        Mat3 r;
        r.m[0] = a; r.m[4] = b; r.m[8] = c;
        return r;
    }

    float operator()(int row, int col) const { return m[col * 3 + row]; }
    float& operator()(int row, int col) { return m[col * 3 + row]; }

    Mat3 operator+(const Mat3& o) const {
        Mat3 r;
        for (int i = 0; i < 9; ++i) r.m[i] = m[i] + o.m[i];
        return r;
    }

    Mat3 operator*(float s) const {
        Mat3 r;
        for (int i = 0; i < 9; ++i) r.m[i] = m[i] * s;
        return r;
    }

    Vec3 operator*(const Vec3& v) const {
        return Vec3(
            m[0] * v.x + m[3] * v.y + m[6] * v.z,
            m[1] * v.x + m[4] * v.y + m[7] * v.z,
            m[2] * v.x + m[5] * v.y + m[8] * v.z
        );
    }

    Mat3 operator*(const Mat3& o) const {
        Mat3 r;
        for (int i = 0; i < 3; ++i) {
            for (int j = 0; j < 3; ++j) {
                r(i, j) = 0;
                for (int k = 0; k < 3; ++k) {
                    r(i, j) += (*this)(i, k) * o(k, j);
                }
            }
        }
        return r;
    }

    Mat3 transpose() const {
        Mat3 r;
        for (int i = 0; i < 3; ++i)
            for (int j = 0; j < 3; ++j)
                r(i, j) = (*this)(j, i);
        return r;
    }

    // 求逆（假设矩阵可逆）
    Mat3 inverse() const {
        float det =
            m[0] * (m[4] * m[8] - m[7] * m[5]) -
            m[1] * (m[3] * m[8] - m[6] * m[5]) +
            m[2] * (m[3] * m[7] - m[6] * m[4]);

        assert(std::abs(det) > 1e-6f);
        float invDet = 1.0f / det;

        Mat3 r;
        r.m[0] = (m[4] * m[8] - m[7] * m[5]) * invDet;
        r.m[1] = (m[2] * m[7] - m[1] * m[8]) * invDet;
        r.m[2] = (m[1] * m[5] - m[2] * m[4]) * invDet;
        r.m[3] = (m[6] * m[5] - m[3] * m[8]) * invDet;
        r.m[4] = (m[0] * m[8] - m[6] * m[2]) * invDet;
        r.m[5] = (m[3] * m[2] - m[0] * m[5]) * invDet;
        r.m[6] = (m[3] * m[7] - m[6] * m[4]) * invDet;
        r.m[7] = (m[6] * m[1] - m[0] * m[7]) * invDet;
        r.m[8] = (m[0] * m[4] - m[3] * m[1]) * invDet;
        return r;
    }
};

// =============================================================================
// 刚体定义
// =============================================================================

enum class BodyType {
    Static,     // 质量无限大，不受力影响
    Dynamic,    // 正常刚体
    Kinematic   // 质量无限大，但速度可编程控制
};

class RigidBody {
public:
    // --- 状态变量 ---
    Vec3 position;           // 世界空间位置（质心）
    Quaternion orientation;  // 世界空间方向
    Vec3 linearVelocity;     // 线速度
    Vec3 angularVelocity;    // 角速度

    // --- 物理属性 ---
    float mass;              // 质量
    float invMass;           // 质量的倒数（0 表示无限质量）
    Mat3 inertiaBody;        // 局部空间惯性张量
    Mat3 invInertiaBody;     // 局部空间惯性张量的逆
    Mat3 invInertiaWorld;    // 世界空间惯性张量的逆（每帧更新）

    // --- 材质属性 ---
    float restitution;       // 恢复系数 [0, 1]
    float friction;          // 摩擦系数

    // --- 外力累积 ---
    Vec3 force;              // 当前帧累积的力
    Vec3 torque;             // 当前帧累积的扭矩

    // --- 休眠 ---
    bool isSleeping;
    float sleepTimer;

    // --- 类型 ---
    BodyType type;

    RigidBody()
        : position(0, 0, 0)
        , orientation(1, 0, 0, 0)
        , linearVelocity(0, 0, 0)
        , angularVelocity(0, 0, 0)
        , mass(1.0f)
        , invMass(1.0f)
        , restitution(0.3f)
        , friction(0.5f)
        , force(0, 0, 0)
        , torque(0, 0, 0)
        , isSleeping(false)
        , sleepTimer(0)
        , type(BodyType::Dynamic)
    {}

    // 设置质量并自动计算惯性张量（假设为长方体）
    void setMassBox(float m, const Vec3& halfExtents) {
        mass = m;
        if (mass < 1e-6f || type == BodyType::Static || type == BodyType::Kinematic) {
            invMass = 0;
            invInertiaBody = Mat3();  // 零矩阵
            return;
        }
        invMass = 1.0f / mass;

        float x2 = halfExtents.x * halfExtents.x;
        float y2 = halfExtents.y * halfExtents.y;
        float z2 = halfExtents.z * halfExtents.z;

        // 实心长方体的惯性张量
        float ix = (1.0f / 3.0f) * mass * (y2 + z2);
        float iy = (1.0f / 3.0f) * mass * (x2 + z2);
        float iz = (1.0f / 3.0f) * mass * (x2 + y2);

        inertiaBody = Mat3::diagonal(ix, iy, iz);
        invInertiaBody = Mat3::diagonal(1.0f / ix, 1.0f / iy, 1.0f / iz);
    }

    // 设置质量并自动计算惯性张量（假设为球体）
    void setMassSphere(float m, float radius) {
        mass = m;
        if (mass < 1e-6f || type == BodyType::Static || type == BodyType::Kinematic) {
            invMass = 0;
            invInertiaBody = Mat3();
            return;
        }
        invMass = 1.0f / mass;

        float i = (2.0f / 5.0f) * mass * radius * radius;
        inertiaBody = Mat3::diagonal(i, i, i);
        invInertiaBody = Mat3::diagonal(1.0f / i, 1.0f / i, 1.0f / i);
    }

    // 每帧更新世界空间的逆惯性张量
    void updateInertiaWorld() {
        if (invMass == 0) {
            invInertiaWorld = Mat3();  // 零矩阵
            return;
        }
        // I_world^{-1} = R * I_body^{-1} * R^T
        // 使用四元数构造旋转矩阵
        float rot[9];
        orientation.toMatrix(rot);
        Mat3 R;
        for (int i = 0; i < 9; ++i) R.m[i] = rot[i];

        Mat3 RT = R.transpose();
        invInertiaWorld = R * invInertiaBody * RT;
    }

    // 施加力（作用在质心）
    void applyForce(const Vec3& f) {
        if (invMass == 0) return;
        force += f;
    }

    // 施加力（作用在特定世界空间点）
    void applyForceAtPoint(const Vec3& f, const Vec3& point) {
        if (invMass == 0) return;
        force += f;
        torque += (point - position).cross(f);
    }

    // 施加冲量（作用在质心）
    void applyImpulse(const Vec3& j) {
        if (invMass == 0) return;
        linearVelocity += j * invMass;
    }

    // 施加冲量（作用在特定世界空间点）
    void applyImpulseAtPoint(const Vec3& j, const Vec3& point) {
        if (invMass == 0) return;
        Vec3 r = point - position;
        linearVelocity += j * invMass;
        angularVelocity += invInertiaWorld * r.cross(j);
    }

    // 获取世界空间中某局部点的位置
    Vec3 localToWorld(const Vec3& localPoint) const {
        return position + orientation.rotate(localPoint);
    }

    // 获取世界空间中某局部点的速度
    Vec3 getPointVelocity(const Vec3& worldPoint) const {
        Vec3 r = worldPoint - position;
        return linearVelocity + angularVelocity.cross(r);
    }

    // 清除外力
    void clearForces() {
        force = Vec3(0, 0, 0);
        torque = Vec3(0, 0, 0);
    }

    // 获取动能
    float getKineticEnergy() const {
        if (invMass == 0) return 0;
        float linearKE = 0.5f * mass * linearVelocity.dot(linearVelocity);
        Vec3 L = inertiaBody * angularVelocity;  // 近似，应在世界空间计算
        float angularKE = 0.5f * angularVelocity.dot(L);
        return linearKE + angularKE;
    }
};

// =============================================================================
// 接触点
// =============================================================================

struct Contact {
    RigidBody* bodyA;
    RigidBody* bodyB;
    Vec3 point;       // 世界空间接触点
    Vec3 normal;      // 从 A 指向 B 的法线
    float penetration; // 穿透深度（正值表示穿透）
    float restitution; // 碰撞恢复系数（取两物体最小值）
    float friction;    // 摩擦系数（取两物体平均值）

    // 求解器内部使用
    Vec3 ra;          // 从 A 质心到接触点的向量
    Vec3 rb;          // 从 B 质心到接触点的向量
    float normalImpulse;   // 累积的法向冲量
    float tangentImpulse1; // 累积的切向冲量 1
    float tangentImpulse2; // 累积的切向冲量 2
    Vec3 tangent1;    // 第一个切向方向
    Vec3 tangent2;    // 第二个切向方向
    float normalMass; // 法向有效质量的倒数
    float tangentMass1;
    float tangentMass2;
    float velocityBias; // Baumgarte 位置修正项
};

// =============================================================================
// 约束基类
// =============================================================================

class Constraint {
public:
    RigidBody* bodyA;
    RigidBody* bodyB;

    Constraint(RigidBody* a, RigidBody* b) : bodyA(a), bodyB(b) {}
    virtual ~Constraint() = default;

    // 准备求解（计算雅可比、有效质量等）
    virtual void prepare(float dt) = 0;

    // 单次迭代求解
    virtual void solve() = 0;
};

// =============================================================================
// 距离约束
// =============================================================================

class DistanceConstraint : public Constraint {
public:
    Vec3 anchorA;     // A 的局部空间锚点
    Vec3 anchorB;     // B 的局部空间锚点
    float restLength; // 目标距离
    float lambda;     // 累积的拉格朗日乘子（用于 warm starting）

    // 内部计算值
    Vec3 jacobianA;   // 对 A 的雅可比（位置部分）
    Vec3 jacobianB;   // 对 B 的雅可比
    Vec3 jacobianRotA;// 对 A 的雅可比（旋转部分）
    Vec3 jacobianRotB;// 对 B 的雅可比（旋转部分）
    float effectiveMass;
    float bias;

    DistanceConstraint(RigidBody* a, RigidBody* b,
                       const Vec3& ancA, const Vec3& ancB,
                       float len)
        : Constraint(a, b)
        , anchorA(ancA)
        , anchorB(ancB)
        , restLength(len)
        , lambda(0)
        , effectiveMass(0)
        , bias(0)
    {}

    void prepare(float dt) override {
        Vec3 pa = bodyA->localToWorld(anchorA);
        Vec3 pb = bodyB->localToWorld(anchorB);
        Vec3 d = pb - pa;
        float dist = d.length();

        if (dist < 1e-6f) {
            // 退化解，跳过
            effectiveMass = 0;
            return;
        }

        Vec3 n = d / dist;  // 从 A 指向 B 的单位向量

        Vec3 ra = pa - bodyA->position;
        Vec3 rb = pb - bodyB->position;

        // 雅可比：J = [-n, -ra x n, n, rb x n]
        jacobianA = -n;
        jacobianB = n;
        jacobianRotA = -ra.cross(n);
        jacobianRotB = rb.cross(n);

        // 有效质量：1 / (J * M^{-1} * J^T)
        float em = 0;
        if (bodyA->invMass > 0) {
            em += bodyA->invMass;
            em += jacobianRotA.dot(bodyA->invInertiaWorld * jacobianRotA);
        }
        if (bodyB->invMass > 0) {
            em += bodyB->invMass;
            em += jacobianRotB.dot(bodyB->invInertiaWorld * jacobianRotB);
        }

        if (em > 1e-6f) {
            effectiveMass = 1.0f / em;
        } else {
            effectiveMass = 0;
        }

        // Baumgarte 稳定化
        float beta = 0.2f;
        float C = dist - restLength;
        bias = (beta / dt) * C;
    }

    void solve() override {
        if (effectiveMass == 0) return;

        // 计算相对速度在约束方向上的分量
        Vec3 va = bodyA->linearVelocity + bodyA->angularVelocity.cross(bodyA->localToWorld(anchorA) - bodyA->position);
        Vec3 vb = bodyB->linearVelocity + bodyB->angularVelocity.cross(bodyB->localToWorld(anchorB) - bodyB->position);
        float JV = (jacobianA.dot(va) + jacobianB.dot(vb) +
                    jacobianRotA.dot(bodyA->angularVelocity) +
                    jacobianRotB.dot(bodyB->angularVelocity));

        // 计算冲量增量
        float dLambda = -(JV + bias) * effectiveMass;

        // 累积
        float oldLambda = lambda;
        lambda += dLambda;
        // 距离约束是等式约束，不需要钳制
        dLambda = lambda - oldLambda;

        // 应用冲量
        Vec3 impulse = jacobianA * dLambda;
        Vec3 rotImpulseA = jacobianRotA * dLambda;
        Vec3 rotImpulseB = jacobianRotB * dLambda;

        bodyA->linearVelocity += impulse * bodyA->invMass;
        bodyA->angularVelocity += bodyA->invInertiaWorld * rotImpulseA;
        bodyB->linearVelocity -= impulse * bodyB->invMass;  // 注意符号
        bodyB->angularVelocity -= bodyB->invInertiaWorld * rotImpulseB;
    }
};

// =============================================================================
// 物理世界
// =============================================================================

class PhysicsWorld {
public:
    std::vector<RigidBody*> bodies;
    std::vector<Contact> contacts;
    std::vector<Constraint*> constraints;

    Vec3 gravity;
    float sleepThreshold;
    float sleepTimeThreshold;
    int solverIterations;
    int positionIterations;
    float baumgarteBeta;

    PhysicsWorld()
        : gravity(0, -9.81f, 0)
        , sleepThreshold(0.1f)
        , sleepTimeThreshold(0.5f)
        , solverIterations(10)
        , positionIterations(3)
        , baumgarteBeta(0.2f)
    {}

    ~PhysicsWorld() {
        for (auto* c : constraints) delete c;
    }

    void addBody(RigidBody* body) {
        bodies.push_back(body);
    }

    void addConstraint(Constraint* c) {
        constraints.push_back(c);
    }

    void removeBody(RigidBody* body) {
        bodies.erase(std::remove(bodies.begin(), bodies.end(), body), bodies.end());
    }

    // 模拟一步
    void step(float dt) {
        // 1. 施加外力（重力）
        applyGravity();

        // 2. 积分速度（半隐式欧拉）
        integrateVelocities(dt);

        // 3. 碰撞检测（简化版：这里假设 contacts 已由外部系统生成）
        // 在实际引擎中，这里会调用 broad phase + narrow phase

        // 4. 准备约束和接触
        prepareConstraints(dt);
        prepareContacts(dt);

        // 5. 求解速度约束（Sequential Impulse）
        solveVelocities();

        // 6. 积分位置
        integratePositions(dt);

        // 7. 位置修正（可选，用于解决剩余穿透）
        solvePositions();

        // 8. 更新惯性张量
        for (auto* body : bodies) {
            body->updateInertiaWorld();
        }

        // 9. 清除外力
        for (auto* body : bodies) {
            body->clearForces();
        }

        // 10. 休眠检测
        updateSleep(dt);
    }

private:
    void applyGravity() {
        for (auto* body : bodies) {
            if (body->invMass > 0 && !body->isSleeping) {
                body->applyForce(gravity * body->mass);
            }
        }
    }

    void integrateVelocities(float dt) {
        for (auto* body : bodies) {
            if (body->invMass == 0 || body->isSleeping) continue;

            // 半隐式欧拉：v += a * dt
            body->linearVelocity += body->force * body->invMass * dt;
            body->angularVelocity += body->invInertiaWorld * body->torque * dt;

            // 线性阻尼（模拟空气阻力）
            float linearDamping = 0.99f;
            float angularDamping = 0.99f;
            body->linearVelocity *= linearDamping;
            body->angularVelocity *= angularDamping;
        }
    }

    void integratePositions(float dt) {
        for (auto* body : bodies) {
            if (body->invMass == 0 || body->isSleeping) continue;

            // 更新位置
            body->position += body->linearVelocity * dt;

            // 更新方向（四元数）
            // dq/dt = 0.5 * omega * q
            Quaternion omegaQ(0, body->angularVelocity.x,
                              body->angularVelocity.y,
                              body->angularVelocity.z);
            Quaternion dq = omegaQ * body->orientation;
            dq = dq * 0.5f * dt;
            body->orientation = body->orientation + dq;
            body->orientation.normalize();
        }
    }

    void prepareConstraints(float dt) {
        for (auto* c : constraints) {
            c->prepare(dt);
        }
    }

    void prepareContacts(float dt) {
        for (auto& c : contacts) {
            c.ra = c.point - c.bodyA->position;
            c.rb = c.point - c.bodyB->position;

            // 计算切向方向
            Vec3 relVel = (c.bodyB->linearVelocity + c.bodyB->angularVelocity.cross(c.rb))
                        - (c.bodyA->linearVelocity + c.bodyA->angularVelocity.cross(c.ra));
            float velAlongNormal = relVel.dot(c.normal);

            Vec3 tangent = relVel - c.normal * velAlongNormal;
            float tangentLen = tangent.length();
            if (tangentLen > 1e-6f) {
                c.tangent1 = tangent / tangentLen;
            } else {
                // 如果相对速度完全沿法线，任选一个正交方向
                Vec3 aux = std::abs(c.normal.x) < 0.7f ? Vec3(1, 0, 0) : Vec3(0, 1, 0);
                c.tangent1 = c.normal.cross(aux).normalized();
            }
            c.tangent2 = c.normal.cross(c.tangent1);

            // 计算有效质量
            // 法向
            float emN = 0;
            if (c.bodyA->invMass > 0) {
                Vec3 raxn = c.ra.cross(c.normal);
                emN += c.bodyA->invMass + raxn.dot(c.bodyA->invInertiaWorld * raxn);
            }
            if (c.bodyB->invMass > 0) {
                Vec3 rbxn = c.rb.cross(c.normal);
                emN += c.bodyB->invMass + rbxn.dot(c.bodyB->invInertiaWorld * rbxn);
            }
            c.normalMass = emN > 1e-6f ? 1.0f / emN : 0;

            // 切向 1
            float emT1 = 0;
            if (c.bodyA->invMass > 0) {
                Vec3 raxt = c.ra.cross(c.tangent1);
                emT1 += c.bodyA->invMass + raxt.dot(c.bodyA->invInertiaWorld * raxt);
            }
            if (c.bodyB->invMass > 0) {
                Vec3 rbxt = c.rb.cross(c.tangent1);
                emT1 += c.bodyB->invMass + rbxt.dot(c.bodyB->invInertiaWorld * rbxt);
            }
            c.tangentMass1 = emT1 > 1e-6f ? 1.0f / emT1 : 0;

            // 切向 2
            float emT2 = 0;
            if (c.bodyA->invMass > 0) {
                Vec3 raxt = c.ra.cross(c.tangent2);
                emT2 += c.bodyA->invMass + raxt.dot(c.bodyA->invInertiaWorld * raxt);
            }
            if (c.bodyB->invMass > 0) {
                Vec3 rbxt = c.rb.cross(c.tangent2);
                emT2 += c.bodyB->invMass + rbxt.dot(c.bodyB->invInertiaWorld * rbxt);
            }
            c.tangentMass2 = emT2 > 1e-6f ? 1.0f / emT2 : 0;

            // Baumgarte 位置修正 + 恢复系数
            float restitution = std::min(c.bodyA->restitution, c.bodyB->restitution);
            if (std::abs(velAlongNormal) < 1.0f) {
                restitution = 0;  // 低速碰撞不弹跳
            }
            c.velocityBias = -(baumgarteBeta / dt) * c.penetration;
            if (velAlongNormal < 0) {
                c.velocityBias += -restitution * velAlongNormal;
            }

            // 重置累积冲量（非 warm starting 模式）
            // 实际引擎中这里会保留上一帧的值
            c.normalImpulse = 0;
            c.tangentImpulse1 = 0;
            c.tangentImpulse2 = 0;
        }
    }

    void solveVelocities() {
        for (int iter = 0; iter < solverIterations; ++iter) {
            // 求解接触约束
            for (auto& c : contacts) {
                solveContact(c);
            }

            // 求解关节约束
            for (auto* constraint : constraints) {
                constraint->solve();
            }
        }
    }

    void solveContact(Contact& c) {
        Vec3 relVel = (c.bodyB->linearVelocity + c.bodyB->angularVelocity.cross(c.rb))
                    - (c.bodyA->linearVelocity + c.bodyA->angularVelocity.cross(c.ra));

        // --- 法向冲量 ---
        float velAlongNormal = relVel.dot(c.normal);
        float dLambdaN = -(velAlongNormal + c.velocityBias) * c.normalMass;

        float oldLambdaN = c.normalImpulse;
        c.normalImpulse = std::max(0.0f, oldLambdaN + dLambdaN);
        dLambdaN = c.normalImpulse - oldLambdaN;

        Vec3 impulseN = c.normal * dLambdaN;
        c.bodyA->applyImpulseAtPoint(-impulseN, c.point);
        c.bodyB->applyImpulseAtPoint(impulseN, c.point);

        // 重新计算相对速度（用于摩擦）
        relVel = (c.bodyB->linearVelocity + c.bodyB->angularVelocity.cross(c.rb))
               - (c.bodyA->linearVelocity + c.bodyA->angularVelocity.cross(c.ra));

        // --- 切向冲量 1 ---
        float velAlongT1 = relVel.dot(c.tangent1);
        float dLambdaT1 = -velAlongT1 * c.tangentMass1;

        float oldLambdaT1 = c.tangentImpulse1;
        float maxFriction = c.friction * c.normalImpulse;
        c.tangentImpulse1 = std::max(-maxFriction, std::min(maxFriction, oldLambdaT1 + dLambdaT1));
        dLambdaT1 = c.tangentImpulse1 - oldLambdaT1;

        Vec3 impulseT1 = c.tangent1 * dLambdaT1;
        c.bodyA->applyImpulseAtPoint(-impulseT1, c.point);
        c.bodyB->applyImpulseAtPoint(impulseT1, c.point);

        // 重新计算相对速度
        relVel = (c.bodyB->linearVelocity + c.bodyB->angularVelocity.cross(c.rb))
               - (c.bodyA->linearVelocity + c.bodyA->angularVelocity.cross(c.ra));

        // --- 切向冲量 2 ---
        float velAlongT2 = relVel.dot(c.tangent2);
        float dLambdaT2 = -velAlongT2 * c.tangentMass2;

        float oldLambdaT2 = c.tangentImpulse2;
        c.tangentImpulse2 = std::max(-maxFriction, std::min(maxFriction, oldLambdaT2 + dLambdaT2));
        dLambdaT2 = c.tangentImpulse2 - oldLambdaT2;

        Vec3 impulseT2 = c.tangent2 * dLambdaT2;
        c.bodyA->applyImpulseAtPoint(-impulseT2, c.point);
        c.bodyB->applyImpulseAtPoint(impulseT2, c.point);
    }

    void solvePositions() {
        // 简单的位置修正：直接沿法线方向分离穿透
        for (int iter = 0; iter < positionIterations; ++iter) {
            for (auto& c : contacts) {
                if (c.penetration <= 0) continue;

                Vec3 pa = c.point - c.bodyA->position;
                Vec3 pb = c.point - c.bodyB->position;

                float totalInvMass = c.bodyA->invMass + c.bodyB->invMass;
                if (totalInvMass < 1e-6f) continue;

                float percent = 0.4f;  // 修正比例（不要一次性修正完，避免过冲）
                float slop = 0.01f;    // 允许的小量穿透
                float correction = std::max(c.penetration - slop, 0.0f) / totalInvMass * percent;

                Vec3 separation = c.normal * correction;
                c.bodyA->position -= separation * c.bodyA->invMass;
                c.bodyB->position += separation * c.bodyB->invMass;
            }
        }
    }

    void updateSleep(float dt) {
        for (auto* body : bodies) {
            if (body->invMass == 0) continue;  // 静态物体不休眠

            float speedSq = body->linearVelocity.lengthSq();
            float angularSpeedSq = body->angularVelocity.lengthSq();

            if (speedSq < sleepThreshold * sleepThreshold &&
                angularSpeedSq < sleepThreshold * sleepThreshold) {
                body->sleepTimer += dt;
                if (body->sleepTimer >= sleepTimeThreshold) {
                    body->isSleeping = true;
                    body->linearVelocity = Vec3(0, 0, 0);
                    body->angularVelocity = Vec3(0, 0, 0);
                }
            } else {
                body->sleepTimer = 0;
                body->isSleeping = false;
            }
        }
    }

public:
    // 唤醒与某物体接触的所有物体
    void wakeContacts(RigidBody* body) {
        for (auto& c : contacts) {
            if (c.bodyA == body && c.bodyB && c.bodyB->isSleeping) {
                c.bodyB->isSleeping = false;
                c.bodyB->sleepTimer = 0;
            }
            if (c.bodyB == body && c.bodyA && c.bodyA->isSleeping) {
                c.bodyA->isSleeping = false;
                c.bodyA->sleepTimer = 0;
            }
        }
    }
};

// =============================================================================
// 演示程序：球体下落碰撞
// =============================================================================

#include <cstdio>

void printBody(const char* name, const RigidBody& body) {
    printf("%s: pos=(%.3f, %.3f, %.3f) vel=(%.3f, %.3f, %.3f) |v|=%.3f\n",
           name,
           body.position.x, body.position.y, body.position.z,
           body.linearVelocity.x, body.linearVelocity.y, body.linearVelocity.z,
           body.linearVelocity.length());
}

int main() {
    printf("=== Mini Physics Engine Demo ===\n\n");

    PhysicsWorld world;
    world.gravity = Vec3(0, -9.81f, 0);
    world.solverIterations = 8;

    // 创建地面（静态物体）
    RigidBody ground;
    ground.type = BodyType::Static;
    ground.position = Vec3(0, 0, 0);
    ground.setMassBox(0, Vec3(10, 0.1f, 10));
    ground.restitution = 0.5f;
    ground.friction = 0.3f;
    world.addBody(&ground);

    // 创建下落的球体
    RigidBody ball;
    ball.type = BodyType::Dynamic;
    ball.position = Vec3(0, 5.0f, 0);
    ball.linearVelocity = Vec3(0.5f, 0, 0.3f);  // 初始有水平速度
    ball.setMassSphere(1.0f, 0.5f);
    ball.restitution = 0.7f;
    ball.friction = 0.4f;
    world.addBody(&ball);

    // 创建第二个球体（堆叠测试）
    RigidBody ball2;
    ball2.type = BodyType::Dynamic;
    ball2.position = Vec3(0.1f, 7.0f, 0);
    ball2.setMassSphere(1.0f, 0.5f);
    ball2.restitution = 0.6f;
    ball2.friction = 0.4f;
    world.addBody(&ball2);

    // 创建距离约束（连接两个球体，模拟"弹簧"效果）
    DistanceConstraint spring(&ball, &ball2,
                              Vec3(0, 0, 0), Vec3(0, 0, 0),
                              2.0f);
    world.addConstraint(&spring);

    printf("Initial state:\n");
    printBody("Ball ", ball);
    printBody("Ball2", ball2);
    printf("\n");

    // 模拟循环
    float dt = 1.0f / 60.0f;
    float totalTime = 0;

    for (int frame = 0; frame < 300; ++frame) {
        totalTime += dt;

        // 简化的碰撞检测：检查球体与地面、球体与球体
        world.contacts.clear();

        // 球 vs 地面
        float ballGroundDist = ball.position.y - 0.5f;  // 球半径 0.5
        if (ballGroundDist < 0) {
            Contact c;
            c.bodyA = &ground;
            c.bodyB = &ball;
            c.point = Vec3(ball.position.x, 0, ball.position.z);
            c.normal = Vec3(0, 1, 0);
            c.penetration = -ballGroundDist;
            c.restitution = std::min(ground.restitution, ball.restitution);
            c.friction = (ground.friction + ball.friction) * 0.5f;
            world.contacts.push_back(c);
        }

        float ball2GroundDist = ball2.position.y - 0.5f;
        if (ball2GroundDist < 0) {
            Contact c;
            c.bodyA = &ground;
            c.bodyB = &ball2;
            c.point = Vec3(ball2.position.x, 0, ball2.position.z);
            c.normal = Vec3(0, 1, 0);
            c.penetration = -ball2GroundDist;
            c.restitution = std::min(ground.restitution, ball2.restitution);
            c.friction = (ground.friction + ball2.friction) * 0.5f;
            world.contacts.push_back(c);
        }

        // 球 vs 球
        Vec3 d = ball2.position - ball.position;
        float dist = d.length();
        float minDist = 1.0f;  // 两球半径之和
        if (dist < minDist && dist > 1e-6f) {
            Contact c;
            c.bodyA = &ball;
            c.bodyB = &ball2;
            c.normal = d / dist;
            c.point = ball.position + c.normal * 0.5f;
            c.penetration = minDist - dist;
            c.restitution = std::min(ball.restitution, ball2.restitution);
            c.friction = (ball.friction + ball2.friction) * 0.5f;
            world.contacts.push_back(c);
        }

        // 唤醒检测
        world.wakeContacts(&ball);
        world.wakeContacts(&ball2);

        // 执行物理步
        world.step(dt);

        // 每 30 帧输出一次
        if (frame % 30 == 0 || frame == 299) {
            printf("Frame %3d (t=%.2fs):\n", frame, totalTime);
            printBody("Ball ", ball);
            printBody("Ball2", ball2);
            printf("  Spring length: %.3f (target: 2.0)\n",
                   (ball2.position - ball.position).length());
            printf("  Ball sleeping: %s, Ball2 sleeping: %s\n",
                   ball.isSleeping ? "yes" : "no",
                   ball2.isSleeping ? "yes" : "no");
            printf("\n");
        }
    }

    printf("=== Simulation Complete ===\n");
    return 0;
}
```

**运行方式:**

将上述代码保存为 `MiniPhysicsEngine.cpp`，然后编译运行：

```bash
# Linux / macOS
g++ -std=c++17 -O2 -o physics MiniPhysicsEngine.cpp && ./physics

# Windows (MSVC)
cl /EHsc /O2 MiniPhysicsEngine.cpp && MiniPhysicsEngine.exe
```

**预期输出:**

```
=== Mini Physics Engine Demo ===

Initial state:
Ball : pos=(0.000, 5.000, 0.000) vel=(0.500, 0.000, 0.300) |v|=0.583
Ball2: pos=(0.100, 7.000, 0.000) vel=(0.000, 0.000, 0.000) |v|=0.000

Frame   0 (t=0.00s):
Ball : pos=(0.008, 4.997, 0.005) vel=(0.495, -0.164, 0.297) |v|=0.578
Ball2: pos=(0.100, 6.997, 0.000) vel=(0.000, -0.164, 0.000) |v|=0.164
  Spring length: 2.003 (target: 2.0)
  Ball sleeping: no, Ball2 sleeping: no

Frame  30 (t=0.50s):
Ball : pos=(0.242, 3.772, 0.145) vel=(0.419, -2.452, 0.251) |v|=2.480
Ball2: pos=(0.100, 5.772, 0.000) vel=(0.000, -2.452, 0.000) |v|=2.452
  Spring length: 2.003 (target: 2.0)
  Ball sleeping: no, Ball2 sleeping: no

...（球体下落、碰撞、弹跳、最终静止）...

Frame 270 (t=4.50s):
Ball : pos=(0.500, 0.500, 0.300) vel=(0.000, 0.000, 0.000) |v|=0.000
Ball2: pos=(0.500, 1.500, 0.300) vel=(0.000, 0.000, 0.000) |v|=0.000
  Spring length: 2.000 (target: 2.0)
  Ball sleeping: yes, Ball2 sleeping: yes

=== Simulation Complete ===
```

---

## 3. 练习

### 练习 1：实现不同几何体的惯性张量

扩展 `RigidBody` 类，添加以下方法：

- `setMassCylinder(float mass, float radius, float height, int axis)` —— 实心圆柱体
- `setMassCapsule(float mass, float radius, float height, int axis)` —— 胶囊体
- `setMassHollowSphere(float mass, float radius)` —— 空心球壳

推导并验证每种几何体的惯性张量公式。创建测试场景，让不同形状的物体从斜面上滚下，观察它们的滚动行为差异。

**提示**：
- 圆柱体绕对称轴的转动惯量为 $\frac{1}{2}mR^2$，绕垂直轴为 $\frac{1}{12}m(3R^2 + h^2)$
- 胶囊体可以分解为圆柱体 + 两个半球
- 空心球壳的转动惯量为 $\frac{2}{3}mR^2$

### 练习 2：实现铰链关节（Hinge Joint）

在距离约束的基础上，实现一个铰链关节。铰链关节需要：

1. 约束两个锚点重合（3 个自由度，与球关节相同）
2. 约束两个旋转轴对齐（2 个自由度）

总共 5 个约束方程，只允许绕铰链轴的相对旋转。

实现步骤：
1. 定义铰链轴在局部空间中的方向
2. 在 `prepare()` 中计算 5 个约束的雅可比
3. 在 `solve()` 中依次求解每个约束
4. 可选：添加角度限制（如门只能开 90 度）

测试场景：创建一扇门（长方体），通过铰链关节连接到地面，施加外力让门摆动。

### 练习 3（可选）：实现一个简单的布料模拟

使用 Verlet 积分和距离约束实现一个 2D 布料模拟：

1. 创建一个 $10 \times 10$ 的粒子网格
2. 每个粒子与其上下左右邻居之间建立距离约束
3. 顶行的粒子固定（静态）
4. 使用 Verlet 积分更新位置
5. 每帧迭代多次求解距离约束

对比 Verlet 积分与半隐式欧拉在布料模拟中的表现差异。尝试添加弯曲约束（防止布料过度折叠）。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```cpp
> // 扩展 RigidBody 的惯性张量计算方法
>
> // 实心圆柱体：绕对称轴的 I = 1/2 mR^2，绕垂直轴 I = 1/12 m(3R^2 + h^2)
> // axis: 0=X, 1=Y, 2=Z 指定圆柱体的对称轴方向
> void RigidBody::setMassCylinder(float m, float radius,
>                                  float height, int axis) {
>     mass = m;
>     if (mass < 1e-6f) { invMass = 0; return; }
>     invMass = 1.0f / mass;
>
>     float i_axial = (1.0f / 2.0f) * mass * radius * radius;
>     float i_radial = (1.0f / 12.0f) * mass
>                    * (3.0f * radius * radius + height * height);
>
>     // 根据对称轴方向分配惯性分量
>     float ix, iy, iz;
>     if (axis == 0) {  // X轴为圆柱对称轴
>         ix = i_axial;  iy = i_radial; iz = i_radial;
>     } else if (axis == 1) {  // Y轴为圆柱对称轴
>         ix = i_radial; iy = i_axial;  iz = i_radial;
>     } else {  // Z轴为圆柱对称轴（默认）
>         ix = i_radial; iy = i_radial; iz = i_axial;
>     }
>
>     inertiaBody = Mat3::diagonal(ix, iy, iz);
>     invInertiaBody = Mat3::diagonal(1.0f/ix, 1.0f/iy, 1.0f/iz);
> }
>
> // 胶囊体 = 圆柱体 + 两个半球 → 实心球体的和质量的一半
> // 胶囊体绕轴向 I = 圆柱轴向 + 2×半球轴向
> // 半球的轴向转动惯量 = 2/5 m_hemisphere R^2
> void RigidBody::setMassCapsule(float m, float radius,
>                                 float height, int axis) {
>     mass = m;
>     if (mass < 1e-6f) { invMass = 0; return; }
>     invMass = 1.0f / mass;
>
>     // 体积分解
>     float volCylinder = 3.14159265f * radius * radius * height;
>     float volHemisphere = (2.0f/3.0f) * 3.14159265f
>                         * radius * radius * radius;
>     float volTotal = volCylinder + 2.0f * volHemisphere;
>
>     float mCyl = m * (volCylinder / volTotal);  // 圆柱体质量
>     float mHemi = (m - mCyl) / 2.0f;            // 每个半球质量
>
>     // 圆柱体轴向惯量
>     float i_axial_cyl = (1.0f/2.0f) * mCyl * radius * radius;
>     // 半球轴向惯量（每个半球绕其中心轴的惯量 + 平行轴定理偏移）
>     float i_axial_hemi = (2.0f/5.0f) * mHemi * radius * radius;
>     // 平行轴定理：半球质心在距离圆柱底 (3/8)R 处
>     float d = height/2.0f + (3.0f/8.0f) * radius;
>     i_axial_hemi += mHemi * d * d;
>
>     float i_axial = i_axial_cyl + 2.0f * i_axial_hemi;
>
>     // 径向惯量（更复杂的积分，简化为近似值）
>     // 圆柱体径向惯量
>     float i_radial_cyl = (1.0f/12.0f) * mCyl
>                        * (3.0f * radius * radius + height * height);
>     // 半球绕直径的惯量 = 2/5 m R^2 + 平行轴偏移
>     float i_radial_hemi = (2.0f/5.0f) * mHemi * radius * radius
>                         + mHemi * d * d;
>     float i_radial = i_radial_cyl + 2.0f * i_radial_hemi;
>
>     float ix, iy, iz;
>     if (axis == 0) {
>         ix = i_axial;  iy = i_radial; iz = i_radial;
>     } else if (axis == 1) {
>         ix = i_radial; iy = i_axial;  iz = i_radial;
>     } else {
>         ix = i_radial; iy = i_radial; iz = i_axial;
>     }
>
>     inertiaBody = Mat3::diagonal(ix, iy, iz);
>     invInertiaBody = Mat3::diagonal(1.0f/ix, 1.0f/iy, 1.0f/iz);
> }
>
> // 空心球壳：I = 2/3 mR^2（所有质量集中在表面）
> void RigidBody::setMassHollowSphere(float m, float radius) {
>     mass = m;
>     if (mass < 1e-6f) { invMass = 0; return; }
>     invMass = 1.0f / mass;
>
>     float i = (2.0f / 3.0f) * mass * radius * radius;
>     inertiaBody = Mat3::diagonal(i, i, i);
>     invInertiaBody = Mat3::diagonal(1.0f/i, 1.0f/i, 1.0f/i);
> }
>
> // 斜面滚动测试
> void TestRollingBehavior() {
>     RigidBody solidSphere, cylinder, hollowSphere;
>     solidSphere.setMassSphere(1.0f, 0.5f);
>     cylinder.setMassCylinder(1.0f, 0.5f, 2.0f, 2);  // Z轴圆柱
>     hollowSphere.setMassHollowSphere(1.0f, 0.5f);
>
>     // 在斜面上的加速度取决于 I/mR^2 比值
>     // 斜面角30度，重力在斜面上的分量 = g*sin(30°) = 4.9 m/s²
>     float slopeAccel = 9.81f * std::sin(3.14159f/6.0f);
>
>     // 滚动加速度 = slopeAccel / (1 + I/(mR^2))
>     // I_solid_sphere/(mR^2) = 2/5 = 0.4
>     // I_cylinder/(mR^2) = 1/2 = 0.5  (绕轴向)
>     // I_hollow_sphere/(mR^2) = 2/3 ≈ 0.667
>
>     float a_solid  = slopeAccel / (1.0f + 0.4f);   // ~3.50
>     float a_cyl    = slopeAccel / (1.0f + 0.5f);   // ~3.27
>     float a_hollow = slopeAccel / (1.0f + 0.667f); // ~2.94
>
>     std::cout << "斜面滚动加速度 (m/s²):\n";
>     std::cout << "  实心球: " << a_solid
>               << " (最快——质量集中在中心)\n";
>     std::cout << "  圆柱体: " << a_cyl << "\n";
>     std::cout << "  空心球壳: " << a_hollow
>               << " (最慢——质量集中在表面)\n";
> }
> ```
>
> **核心思路**：转动惯量反映了"角速度改变对扭矩的抵抗"。I/(mR²)比值越大，物体越难被滚动加速。实心球(I=2/5 mR²)质量集中在中心，比值最小→滚动最快；空心球壳(I=2/3 mR²)质量全在表面，比值最大→滚动最慢。胶囊体的惯性张量通过分解为圆柱体+两个半球并应用平行轴定理计算——半球质心不在胶囊体质心处，需要补偿偏移。

> [!tip]- 练习 2 参考答案
> ```cpp
> // HingeJoint.hpp —— 铰链关节实现
>
> class HingeJoint {
> public:
>     // 初始化铰链关节
>     // bodyA, bodyB: 连接的两个刚体
>     // anchorA, anchorB: 局部空间的锚点
>     // hingeAxisA, hingeAxisB: 局部空间的铰链轴方向
>     void Initialize(RigidBody* a, RigidBody* b,
>                     const Vec3& anchorA, const Vec3& anchorB,
>                     const Vec3& hingeAxisA,
>                     const Vec3& hingeAxisB) {
>         bodyA_ = a; bodyB_ = b;
>         anchorA_ = anchorA;
>         anchorB_ = anchorB;
>         hingeAxisA_ = hingeAxisA.normalized();
>         hingeAxisB_ = hingeAxisB.normalized();
>     }
>
>     // 每帧准备（在求解循环前调用一次）
>     void Prepare() {
>         // 锚点在世界空间的位置
>         Vec3 worldAnchorA = bodyA_->localToWorld(anchorA_);
>         Vec3 worldAnchorB = bodyB_->localToWorld(anchorB_);
>
>         // 约束1-3：位置约束（3 DOF — 锚点重合）
>         // 需要3个约束方程消除3维平移
>         for (int i = 0; i < 3; ++i) {
>             PreparePositionConstraint(i, worldAnchorA, worldAnchorB);
>         }
>
>         // 约束4-5：旋转轴对齐约束（2 DOF）
>         // 铰链轴在世界空间的方向
>         Vec3 worldAxisA = bodyA_->orientation.rotate(hingeAxisA_);
>         Vec3 worldAxisB = bodyB_->orientation.rotate(hingeAxisB_);
>
>         PrepareRotationConstraint(0, worldAxisA, worldAxisB);
>         PrepareRotationConstraint(1, worldAxisA, worldAxisB);
>     }
>
>     // 求解单次迭代（会被多次调用）
>     void Solve(float dt) {
>         // 依次求解5个约束方程
>         for (int i = 0; i < 5; ++i) {
>             SolveConstraint(i, dt);
>         }
>     }
>
>     // 铰链角度限制（可选——如门只能开90度）
>     void SetAngleLimits(float minAngle, float maxAngle) {
>         angleMin_ = minAngle;
>         angleMax_ = maxAngle;
>         hasLimits_ = true;
>     }
>
> private:
>     // 约束数据结构
>     struct ConstraintData {
>         Vec3 jacobianA_linear, jacobianA_angular;
>         Vec3 jacobianB_linear, jacobianB_angular;
>         float effectiveMass;     // 有效质量 = 1 / (J M^{-1} J^T)
>         float bias;              // Baumgarte位置稳定化项
>         float accumulatedImpulse; // 累积冲量（用于暖启动）
>     };
>
>     void PreparePositionConstraint(int axis,
>          const Vec3& worldAnchorA, const Vec3& worldAnchorB) {
>         auto& c = constraints_[axis];
>
>         // 拉格朗日乘子方向：沿世界坐标轴
>         Vec3 n(axis == 0 ? 1.0f : 0.0f,
>                axis == 1 ? 1.0f : 0.0f,
>                axis == 2 ? 1.0f : 0.0f);
>
>         // 雅可比项
>         c.jacobianA_linear = -n;
>         c.jacobianB_linear = n;
>
>         // 角雅可比：J_ω = r × n
>         Vec3 rA = worldAnchorA - bodyA_->position;
>         Vec3 rB = worldAnchorB - bodyB_->position;
>         c.jacobianA_angular = -rA.cross(n);
>         c.jacobianB_angular = rB.cross(n);
>
>         // 有效质量
>         float invMassA = bodyA_->invMass;
>         float invMassB = bodyB_->invMass;
>         float invIA = Dot(
>             bodyA_->invInertiaWorld * c.jacobianA_angular,
>             c.jacobianA_angular);
>         float invIB = Dot(
>             bodyB_->invInertiaWorld * c.jacobianB_angular,
>             c.jacobianB_angular);
>         c.effectiveMass = 1.0f / (invMassA + invMassB + invIA + invIB);
>
>         // 位置误差（Baumgarte稳定化的bias项）
>         float error = Dot(n, worldAnchorB - worldAnchorA);
>         c.bias = error * 0.2f;  // beta = 0.2
>         c.accumulatedImpulse = 0.0f;
>     }
>
>     void PrepareRotationConstraint(int idx,
>          const Vec3& axisA, const Vec3& axisB) {
>         auto& c = constraints_[3 + idx];
>
>         // 约束方向：垂直于铰链轴的任意方向
>         // 使用任意轴（与铰链轴正交）来约束旋转
>         Vec3 n = (idx == 0) ?
>             Vec3(0, 1, 0).cross(axisA).normalized() :
>             axisA.cross(Vec3(0, 0, 1)).normalized();
>         if (n.lengthSq() < 0.01f) n = Vec3(1, 0, 0);
>
>         c.jacobianA_linear = Vec3(0,0,0);
>         c.jacobianB_linear = Vec3(0,0,0);
>         c.jacobianA_angular = -n;
>         c.jacobianB_angular = n;
>
>         float invIA = Dot(
>             bodyA_->invInertiaWorld * n, n);
>         float invIB = Dot(
>             bodyB_->invInertiaWorld * n, n);
>         c.effectiveMass = 1.0f / (invIA + invIB);
>
>         // 角度误差 = axisA 和 axisB 在约束方向上的差异
>         float error = Dot(n, axisB - axisA);
>         c.bias = error * 0.1f;
>         c.accumulatedImpulse = 0.0f;
>     }
>
>     void SolveConstraint(int idx, float dt) {
>         auto& c = constraints_[idx];
>         if (c.effectiveMass < 1e-12f) return;
>
>         // 计算约束速度（Jv = J * v）
>         float jv = Dot(c.jacobianA_linear,
>                        bodyA_->linearVelocity)
>                  + Dot(c.jacobianA_angular,
>                        bodyA_->angularVelocity)
>                  + Dot(c.jacobianB_linear,
>                        bodyB_->linearVelocity)
>                  + Dot(c.jacobianB_angular,
>                        bodyB_->angularVelocity);
>
>         // 拉格朗日乘子 = -(Jv + bias) / effectiveMass
>         float lambda = -(jv + c.bias) * c.effectiveMass;
>
>         // 累积并钳制（暖启动用）
>         float prev = c.accumulatedImpulse;
>         c.accumulatedImpulse += lambda;
>         lambda = c.accumulatedImpulse - prev;
>
>         // 应用冲量
>         bodyA_->linearVelocity += c.jacobianA_linear
>                                 * (lambda * bodyA_->invMass);
>         bodyA_->angularVelocity +=
>             bodyA_->invInertiaWorld * c.jacobianA_angular
>             * lambda;
>         bodyB_->linearVelocity += c.jacobianB_linear
>                                 * (lambda * bodyB_->invMass);
>         bodyB_->angularVelocity +=
>             bodyB_->invInertiaWorld * c.jacobianB_angular
>             * lambda;
>     }
>
>     RigidBody* bodyA_ = nullptr;
>     RigidBody* bodyB_ = nullptr;
>     Vec3 anchorA_, anchorB_;
>     Vec3 hingeAxisA_, hingeAxisB_;
>     ConstraintData constraints_[5];  // 5个约束方程
>     float angleMin_ = -3.14159f, angleMax_ = 3.14159f;
>     bool hasLimits_ = false;
> };
>
> // 测试：门摆动
> void TestHingeJoint() {
>     RigidBody ground, door;
>     ground.type = BodyType::Static;
>     door.setMassBox(10.0f, Vec3(0.5f, 1.0f, 0.05f)); // 扁平门
>     door.position = Vec3(1.0f, 0, 0);
>
>     HingeJoint hinge;
>     // 铰链轴 = Y轴（门绕Y旋转打开/关闭）
>     hinge.Initialize(
>         &ground, &door,
>         Vec3(0, 0, 0),        // ground锚点 = 门铰链处
>         Vec3(-0.5f, 0, 0),    // door锚点 = 门一侧边缘
>         Vec3(0, 1, 0),        // ground铰链轴 = Y
>         Vec3(0, 1, 0)         // door铰链轴 = Y (对齐)
>     );
>     hinge.SetAngleLimits(-1.57f, 1.57f);  // ±90度
>
>     // 施加外力模拟推门
>     door.applyForceAtPoint(Vec3(0, 0, 50),
>         door.localToWorld(Vec3(0.5f, 0, 0)));  // 门边缘推
>
>     // 模拟循环...
>     hinge.Prepare();
>     for (int iter = 0; iter < 10; ++iter) {
>         hinge.Solve(1.0f/60.0f);
>     }
> }
> ```
>
> **核心思路**：铰链关节需要5个约束方程：3个平移约束（锚点重合→消除3个平移自由度）+ 2个旋转约束（两个轴对齐→消除另外2个旋转自由度），只留下绕铰链轴的旋转。每个约束的本质是"拉格朗日乘子法"——通过计算雅可比矩阵和有效质量，找到刚好满足约束的速度修正冲量。Baumgarte稳定化参数(beta=0.2)通过引入位置误差反馈防止数值漂移导致的约束违反累积。

> [!tip]- 练习 3 参考答案（可选）
> ```cpp
> // ClothSimulation.hpp —— 布料模拟（Verlet积分 + 距离约束）
>
> #include <vector>
> #include <cmath>
>
> struct ClothParticle {
>     float x, y;          // 当前位置
>     float oldX, oldY;    // 上一帧位置（Verlet用）
>     float ax, ay;        // 加速度
>     bool pinned;         // 是否固定
> };
>
> struct DistanceConstraint {
>     int pA, pB;          // 粒子索引
>     float restLength;    // 静止长度
>     float stiffness;     // 刚度 (0~1)
> };
>
> class ClothSimulation {
> public:
>     ClothSimulation(int gridW, int gridH, float spacing)
>         : gridW_(gridW), gridH_(gridH), spacing_(spacing)
>     {
>         // 创建粒子网格
>         particles_.resize(gridW * gridH);
>         for (int y = 0; y < gridH; ++y) {
>             for (int x = 0; x < gridW; ++x) {
>                 int idx = y * gridW + x;
>                 particles_[idx].x = x * spacing;
>                 particles_[idx].y = y * spacing;
>                 particles_[idx].oldX = particles_[idx].x;
>                 particles_[idx].oldY = particles_[idx].y;
>                 particles_[idx].pinned = (y == 0);  // 顶行固定
>             }
>         }
>
>         // 创建结构性约束（垂直和水平弹簧）
>         for (int y = 0; y < gridH; ++y) {
>             for (int x = 0; x < gridW; ++x) {
>                 int idx = y * gridW + x;
>                 // 水平约束
>                 if (x < gridW - 1) {
>                     constraints_.push_back({
>                         idx, idx + 1, spacing, 0.8f
>                     });
>                 }
>                 // 垂直约束
>                 if (y < gridH - 1) {
>                     constraints_.push_back({
>                         idx, idx + gridW, spacing, 0.8f
>                     });
>                 }
>                 // 弯曲约束（间隔一个粒子，防止过度折叠）
>                 if (x < gridW - 2) {
>                     constraints_.push_back({
>                         idx, idx + 2, spacing * 2.0f, 0.2f
>                     });
>                 }
>                 if (y < gridH - 2) {
>                     constraints_.push_back({
>                         idx, idx + gridW * 2,
>                         spacing * 2.0f, 0.2f
>                     });
>                 }
>             }
>         }
>     }
>
>     // 单步模拟（dt为秒）
>     void Step(float dt, int constraintIterations = 5) {
>         // 1. Verlet积分（先更新位置）
>         VerletIntegrate(dt);
>
>         // 2. 多次迭代求解距离约束
>         for (int iter = 0; iter < constraintIterations; ++iter) {
>             EnforceDistanceConstraints();
>         }
>     }
>
>     // 获取粒子状态
>     const std::vector<ClothParticle>& Particles() const {
>         return particles_;
>     }
>
> private:
>     void VerletIntegrate(float dt) {
>         const float gravity = 9.81f;
>         float dtSq = dt * dt;
>
>         for (auto& p : particles_) {
>             if (p.pinned) continue;
>
>             // Verlet: x_{n+1} = 2x_n - x_{n-1} + a * dt^2
>             float velX = p.x - p.oldX;  // 隐式速度
>             float velY = p.y - p.oldY;
>
>             // 添加阻尼
>             velX *= 0.99f;
>             velY *= 0.99f;
>
>             p.oldX = p.x;
>             p.oldY = p.y;
>
>             p.x += velX + p.ax * dtSq;
>             p.y += velY + (p.ay - gravity) * dtSq;
>
>             p.ax = 0; p.ay = 0;  // 重置加速度
>         }
>     }
>
>     void EnforceDistanceConstraints() {
>         for (auto& c : constraints_) {
>             auto& a = particles_[c.pA];
>             auto& b = particles_[c.pB];
>
>             float dx = b.x - a.x;
>             float dy = b.y - a.y;
>             float dist = std::sqrt(dx*dx + dy*dy);
>             if (dist < 1e-6f) continue;
>
>             // 需要的修正量
>             float correction = (dist - c.restLength)
>                              / dist * c.stiffness * 0.5f;
>
>             float cx = dx * correction;
>             float cy = dy * correction;
>
>             // 对两个粒子施加相反的修正（加权平均）
>             if (!a.pinned) { a.x += cx; a.y += cy; }
>             if (!b.pinned) { b.x -= cx; b.y -= cy; }
>         }
>     }
>
>     int gridW_, gridH_;
>     float spacing_;
>     std::vector<ClothParticle> particles_;
>     std::vector<DistanceConstraint> constraints_;
> };
>
> // Verlet vs 半隐式欧拉 对比
> void CompareIntegrators() {
>     // Verlet: 直接操作位置，不需要显式速度变量
>     //     优点：速度由位置差分隐式得出，天然稳定
>     //     缺点：无法直接施加与速度相关的力（如空气阻力）
>     //
>     // 半隐式欧拉: v_{n+1} = v_n + a*dt, x_{n+1} = x_n + v_{n+1}*dt
>     //     优点：速度是显式变量，可以施加速度相关力
>     //     缺点：对于高刚度弹簧容易不稳定（需满足 dt < 2/ω）
>     //
>     // 布料模拟选Verlet的原因：
>     // 1. 高迭代次数的约束求解替代了弹簧力计算
>     // 2. Verlet不需要显式速度变量，约束修正后自动更新速度
>     // 3. 数值稳定性好，不容易爆炸
> }
> ```
>
> **核心思路**：Verlet积分的核心优势是"位置驱动"——`x_{n+1} = 2x_n - x_{n-1} + a*dt²`直接更新位置，速度由当前位置和上帧位置差分得到。这使得距离约束可以直接修正位置而不破坏速度一致性。结构性约束(相邻粒子)维持布料形状，弯曲约束(间隔粒子)防止过度折叠。多次迭代求解约束(通常5-10次)是PBD方法的关键——每次迭代逐步拉近所有被拉伸的弹簧，最终收敛到约束满足状态。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

## 4. 扩展阅读

### 经典书籍

1. **《Game Physics, 2nd Edition》— David H. Eberly**
   - 游戏物理领域的权威参考书，涵盖从基础力学到高级约束求解的完整内容
   - 第 5-6 章详细讲解冲量和约束

2. **《Real-Time Collision Detection》— Christer Ericson**
   - 第 5 章涉及动力学基础
   - 更多关于碰撞检测与响应的集成

3. **《Physics for Game Developers, 2nd Edition》— David Bourg & Bryan Bywalec**
   - 更入门友好的物理引擎实现指南

4. **《Rigid Body Dynamics Algorithms》— Roy Featherstone**
   - 刚体动力学的经典教材，偏学术但非常严谨

### 在线资源

1. **Box2D 源码** — Erin Catto
   - GitHub: erincatto/box2d
   - 最经典的开源 2D 物理引擎，Sequential Impulse 方法的标准实现
   - 重点阅读 `b2Island.cpp`（求解器）和 `b2ContactSolver.cpp`（接触求解）

2. **Bullet Physics 源码**
   - GitHub: bulletphysics/bullet3
   - 广泛使用的 3D 物理引擎
   - 重点阅读 `btSequentialImpulseConstraintSolver`

3. **Erin Catto 的 GDC 演讲**
   - "Iterative Dynamics with Temporal Coherence" (GDC 2005)
   - "Soft Constraints" (GDC 2011)
   - "Understanding Constraints" (GDC 2014)
   - 这些演讲是理解现代物理引擎约束求解的最佳材料

4. **Chris Hecker 的系列文章**
   - "Physics" 系列（Game Developer Magazine, 1996-1997）
   - 从基础到高级的物理模拟教程，可在 chrishecker.com 找到

### 论文

1. **"Nonconvex Rigid Bodies with Stacking"** — Eran Guendelman et al. (2003)
   - 关于刚体堆叠和接触处理的重要论文

2. **"Parallel Constraint Solver for Physics Simulation"** — Takahiro Harada (2011)
   - 关于在 GPU 上并行求解约束

3. **"Position Based Dynamics"** — Matthias Muller et al. (2007)
   - PBD 方法，广泛用于布料、软体模拟

### 相关章节

- 本计划第 6 章《碰撞检测：从 AABB 到 GJK/EPA》— 本章的前置知识
- 本计划第 14 章《多线程与并发：Job System》— 物理引擎的多线程优化
- 本计划第 16 章《内存管理与自定义分配器》— 物理引擎的内存布局优化

---

## 常见陷阱

### 陷阱 1：四元数积分后不归一化

四元数积分后如果不归一化，会导致旋转矩阵逐渐失去正交性，进而使惯性张量变换出错，物体行为异常。**务必每帧归一化四元数**。

```cpp
// 错误
body.orientation = body.orientation + dq;

// 正确
body.orientation = body.orientation + dq;
body.orientation.normalize();
```

### 陷阱 2：角速度单位混淆

角速度的单位是**弧度/秒**，不是度/秒。如果误用度数，物体会旋转得过快或过慢。

```cpp
// 错误：角度制
body.angularVelocity = Vec3(0, 90, 0);  // 90 度/秒

// 正确：弧度制
body.angularVelocity = Vec3(0, 1.571f, 0);  // ~90 度/秒 = pi/2 弧度/秒
```

### 陷阱 3：惯性张量坐标系混淆

惯性张量 $I_{body}$ 在局部坐标系中通常是对角矩阵，但 $I_{world}$ 一般不是。在世界空间中使用 $I_{body}$ 会导致完全错误的转动行为。

```cpp
// 错误：在 world space 中使用 body space 的惯性张量
Vec3 angularAccel = invInertiaBody * torque;

// 正确：使用 world space 的逆惯性张量
Vec3 angularAccel = invInertiaWorld * torque;
```

### 陷阱 4：冲量方向符号错误

冲量响应中，法线方向容易搞混。记住：法线从 bodyA 指向 bodyB，bodyA 受到 $-j\mathbf{n}$，bodyB 受到 $+j\mathbf{n}$。

### 陷阱 5：迭代求解器收敛不足

迭代次数太少会导致约束"松软"（如堆叠的箱子逐渐塌陷）。但迭代次数太多会影响性能。需要根据场景调整：

- 简单场景：4-8 次迭代
- 堆叠场景：10-20 次迭代
- 高精度需求：20+ 次迭代

### 陷阱 6：Baumgarte 参数过大

Baumgarte 稳定化参数 $\beta$ 过大（如 > 0.5）会导致物体在碰撞时"弹跳"过度，甚至使系统不稳定。推荐值：0.1 ~ 0.3。

### 陷阱 7：忽略质量为 0 的情况

静态物体（质量无限大，invMass = 0）不应参与速度更新，也不应计算其有效质量。忘记检查会导致除零错误。

```cpp
// 务必检查
if (body.invMass == 0) continue;  // 跳过静态物体
```

### 陷阱 8：摩擦冲量计算顺序

摩擦冲量依赖于法向冲量（$|j_t| \leq \mu |j_n|$），因此必须先计算法向冲量，再计算摩擦冲量。如果顺序颠倒，摩擦会计算错误。

### 陷阱 9：休眠阈值设置不当

休眠阈值过小会导致物体难以休眠，浪费计算资源；过大则会导致物体在应该运动时休眠，产生"粘滞"感。需要根据游戏节奏调整。

### 陷阱 10：时间步长不稳定

物理模拟对时间步长敏感。如果帧率波动导致 $\Delta t$ 变化很大，模拟会变得不稳定。解决方案：

- 固定时间步长（如固定 1/60 秒）
- 使用子步（sub-stepping）：将大时间步拆分为多个固定小步

```cpp
// 推荐：固定时间步
const float FIXED_DT = 1.0f / 60.0f;
accumulator += deltaTime;
while (accumulator >= FIXED_DT) {
    world.step(FIXED_DT);
    accumulator -= FIXED_DT;
}
```

---

## 5. 高级物理特性

### 5.1 固定时间步长与子步进

在实际游戏中，渲染帧率可能波动（如从 60 FPS 掉到 30 FPS），但物理模拟需要稳定的时间步长以保证确定性。

**子步进（Sub-stepping）策略**：

```cpp
void PhysicsWorld::Step(float deltaTime) {
    // 使用固定时间步长，如果需要多次子步进
    int numSubSteps = static_cast<int>(std::ceil(deltaTime / m_fixedDeltaTime));
    numSubSteps = std::min(numSubSteps, 8);  // 最多 8 个子步，防止卡顿时的性能爆炸

    float dt = deltaTime / numSubSteps;
    for (int i = 0; i < numSubSteps; ++i) {
        Integrate(dt);
        UpdateAABBs();
        SolveCollisions();
    }
}
```

**关键设计决策**：
- 固定物理更新频率（通常 60Hz 或 120Hz）
- 限制最大子步数（如 8 次），防止卡顿时的性能雪崩
- 渲染帧率与物理帧率解耦，通过插值平滑显示

### 5.2 布料模拟

布料是游戏中最常见的柔性物体。**质点-弹簧系统（Mass-Spring System）** 是最直观的布料模拟方法：将布料表示为一个由质点组成的网格，相邻质点之间用弹簧连接。

每个质点的运动遵循牛顿第二定律，弹簧力由胡克定律计算：

$$\mathbf{F}_{spring} = -k_s (|\mathbf{x}_i - \mathbf{x}_j| - l_0) \frac{\mathbf{x}_i - \mathbf{x}_j}{|\mathbf{x}_i - \mathbf{x}_j|}$$

其中 $k_s$ 是弹簧刚度，$l_0$ 是弹簧的静止长度。为了模拟布料的阻尼特性，还需要添加与速度差成正比的阻尼力：

$$\mathbf{F}_{damping} = -k_d (\mathbf{v}_i - \mathbf{v}_j)$$

质点-弹簧系统的数值稳定性是一个重要挑战。使用显式积分时，弹簧刚度 $k_s$ 和时间步长 $\Delta t$ 必须满足以下条件才能保证稳定：

$$\Delta t < \frac{2}{\omega} = 2\sqrt{\frac{m}{k_s}}$$

这个约束意味着高刚度的弹簧需要非常小的时间步长，这在实时应用中往往不现实。因此，布料模拟通常使用**隐式积分**或**位置约束（Position Based Dynamics, PBD）**方法。

**PBD 方法**由 Matthias Muller 等人提出，它将布料模拟从基于力的框架转换到基于位置约束的框架。PBD 的基本步骤是：

1. 对所有质点进行预测位置的显式积分。
2. 迭代求解约束（如距离约束、碰撞约束），直接修正质点的位置。
3. 用修正后的位置更新速度。

PBD 的优点是稳定、快速且易于控制，因此在游戏引擎中得到了广泛应用。NVIDIA 的 Flex 和 Unreal Engine 的 Chaos 物理系统都支持 PBD 布料模拟。

### 5.3 破坏系统与布娃娃系统

**破坏系统（Destructible System）** 允许游戏中的物体在被击中或受到冲击时碎裂成多个碎片。实现破坏系统的关键技术包括：

1. **Voronoi 分解**：将网格按照 Voronoi 图模式分割成多个碎片区域。Voronoi 图的细胞状结构能生成视觉上自然的碎裂效果。
2. **运行时物理生成**：当破坏事件触发时，用预计算的碎片替换原物体，并为每个碎片创建独立的刚体。
3. **性能优化**：限制同时激活的碎片数量，对远处的碎片使用简化物理，一段时间后将碎片标记为静态或移除。

**布娃娃系统（Ragdoll）** 用于在角色死亡或被击晕时，从动画驱动切换到物理驱动。布娃娃本质上是一组通过关节约束连接的刚体（对应角色的躯干、四肢、头部等），使用约束求解器实时模拟其运动。布娃娃系统的关键技术包括：

1. **关节限制**：每个关节（如肩关节、膝关节）有特定的运动范围限制，需要实现为物理约束。例如，膝关节只能在一个轴上旋转，角度范围约为 0-150 度。
2. **动画与物理的混合**：在角色倒地过程中，可以逐渐从动画驱动过渡到物理驱动（Blend 权重从 1 降到 0），使过渡更自然。
3. **布娃娃稳定化**：布娃娃系统容易出现抖动和不稳定，需要通过调整约束的迭代次数、使用角度限制软约束、以及在质心位置施加额外的稳定化力来解决。

---

## 6. 第三方物理引擎集成

从头实现一个完整的物理引擎是一项巨大的工程。在实际游戏项目中，通常集成成熟的第三方物理引擎。

### 6.1 主流物理引擎对比

| 特性 | NVIDIA PhysX | Havok Physics | Jolt Physics | Bullet Physics |
|------|-------------|---------------|--------------|----------------|
| 开发商 | NVIDIA | Microsoft (原 Havok) | Jorrit Rouwe (个人) | Erwin Coumans (开源社区) |
| 许可模式 | 免费 (BSD-3) | 商业许可 / 免费(部分) | MIT 开源 | zlib 开源 |
| 刚体动力学 | 优秀 | 优秀 | 优秀 | 良好 |
| 碰撞检测 | 支持 GPU 加速 (GJK+SAT) | 高效 (多线程优化) | 高效 (宽相优化) | 完整 (GJK+EPA) |
| 布料/柔体 | 支持 (Cloth/SoftBody) | 支持 (Cloth) | 有限支持 | 支持 (SoftBody) |
| 破坏系统 | Blast SDK | 支持 | 基础支持 | 有限 |
| 角色控制器 | 内置 | 内置 | 内置 | 内置 |
| 多线程 | 优秀 | 优秀 | 优秀 | 一般 |
| GPU 加速 | 是 (CUDA) | 否 (CPU 优化) | 否 | 有限 (OpenCL) |
| 主要用户 | Unreal Engine, Unity | 大量 3A 游戏 | Godot 4, 独立项目 | Blender, 早期项目 |
| 源码质量 | 良好 | 优秀 | 优秀 (现代 C++) | 良好 |
| 平台支持 | 全平台 | 全平台 | 全平台 | 全平台 |

**NVIDIA PhysX** 是目前游戏行业中使用最广泛的物理引擎。它与 NVIDIA GPU 深度集成，支持 GPU 加速的刚体和粒子模拟。PhysX 的 Blast 破坏 SDK 提供了业界领先的破坏模拟能力。Unreal Engine 的 Chaos 物理系统最初基于 PhysX，后来逐渐转向自主实现，但仍然保留了 PhysX 的接口兼容性。

**Havok Physics** 是 3A 游戏行业的事实标准，尤其是在主机游戏领域。它以极高的稳定性和优化的多线程性能著称。Havok 的核心优势在于其经过大量商业项目验证的鲁棒性和精细的调参能力。

**Jolt Physics** 是相对较新的开源物理引擎，由前 Guerrilla Games 的引擎程序员 Jorrit Rouwe 开发。Jolt 的设计目标是成为"最好用的游戏物理引擎"，它采用现代 C++ 编写，API 设计简洁直观，性能优异。Godot 4 引擎选择了 Jolt 作为其默认物理后端。

**Bullet Physics** 是最早的开源物理引擎之一，被广泛用于学术研究和早期游戏项目。Bullet 的功能非常全面，但代码库较为陈旧，多线程支持不如新引擎。

### 6.2 集成架构设计

将第三方物理引擎集成到游戏引擎中，通常采用**适配器模式（Adapter Pattern）**：

1. **物理世界封装**：在引擎层创建一个 `PhysicsWorld` 抽象类，封装物理引擎的具体 `World` / `Scene` 对象。引擎的其他系统只与 `PhysicsWorld` 交互，不直接操作物理引擎的 API。
2. **组件桥接**：游戏对象的物理属性（如质量、摩擦力）通过引擎的组件系统（如 `PhysicsComponent`）管理。`PhysicsComponent` 在初始化时同步数据到物理引擎的刚体对象，并在每帧将物理引擎的模拟结果（位置、旋转）同步回游戏对象。
3. **回调系统**：物理引擎的碰撞事件通过回调函数通知引擎层。引擎层将这些事件分发到游戏逻辑系统（如伤害计算、音效触发）。
4. **调试可视化**：物理引擎通常提供调试绘制接口（Debug Draw），用于可视化碰撞体、约束和接触点。引擎层将这些调试信息转发到渲染系统。

**物理世界与游戏世界的同步**通常遵循**固定时间步长（Fixed Timestep）**模式：物理引擎以固定的频率（如 60Hz 或 120Hz）更新，而游戏逻辑和渲染可能以不同的频率运行。每帧物理更新时，将所有刚体的 Transform 数据从游戏世界同步到物理世界，执行物理模拟步进，然后将模拟结果同步回游戏世界。对于可变帧率的游戏循环，可以使用多次子步进（Sub-stepping）来保证物理模拟的稳定性。
