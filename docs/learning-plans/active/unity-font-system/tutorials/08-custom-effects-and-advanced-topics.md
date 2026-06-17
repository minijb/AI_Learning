---
title: 自定义 Shader、Sprite Asset 与高级主题
updated: 2026-06-17
tags: [unity, font, textmeshpro, textcore, shader, sprite-asset, stylesheet]
aliases: [Custom Font Effects]
---

# 自定义 Shader、Sprite Asset 与高级主题

> 所属计划: [[plan|Unity 字体系统学习计划]]
> 预计耗时: 90 min
> 前置知识: [[04-sdf-rendering-and-shaders|SDF 渲染与 Shader 特效]], [[07-performance-optimization|性能优化与调试]]

---

## 1. 概念讲解

TextMeshPro / TextCore 把“字体”拆成了三个可独立扩展的层：

1. **Font Asset（字形数据 + Atlas）**：决定有哪些字、字长什么样。
2. **Material + Shader**：决定字怎么画、用什么特效。
3. **Text Component / Text Generator**：决定文本内容、布局、网格。

只要保持 Atlas 不变，只换 Material，就能让同一套字形呈现出完全不同的视觉效果。这就是 **Material Preset** 的核心思想。再进一步，修改 Shader 本身，就可以实现项目专属的文字效果。

### 为什么需要自定义？

- 内置 Shader 的描边、阴影、发光已经够用 90% 的场景，但无法做“随文字位置渐变”“波浪扭曲”“角色名字按稀有度变色”等 gameplay 驱动效果。
- 图标/表情需要像普通字符一样混排在文本流里，而不是每张图单独做一个 `Image`。
- 富文本标签写死在大段文本中难以维护，Text Style Sheet 可以把样式抽成可复用资源。

### Material Preset

TMP 为每个 Font Asset 自动生成一个默认 Material。右键该 Material 选择 **Create > TextMeshPro > Material Preset**，即可得到一个共享同一份 Atlas 但 Shader 属性不同的 Material。例如：

- 同一个 SDF 字体，可以有一个“默认白字”、一个“金色描边标题”、一个“暗色阴影聊天”预设。
- 切换预设不会重建 atlas，只切换 material，开销极低。

### Sprite Asset

TMP 可以把任意 Texture2D 切成若干 sprite，并作为特殊 glyph 插入文本。每个 sprite 有 Unicode 值或名字，支持富文本：

```text
<sprite index=0>
<sprite name="icon_coin">
```
渲染时，Text Generator 会把 sprite 当成一个 quad，从 sprite atlas 采样。注意：sprite 需要和字体使用同一个 material 才能 batch；跨 material 的 sprite 会破坏 batch。

### Text Style Sheet

Text Style Sheet（`TMP_StyleSheet`）允许你定义自定义富文本标签：

```text
<style=Rare>传说武器</style>
```
在 Style Sheet 里，`Rare` 可以展开为：

```text
<color=#ffaa00><b>传说武器</b></color>
```
这样美术/策划改颜色时只需要改资源文件，不用改所有字符串。

### MSDF（Multi-channel Signed Distance Field）

标准 SDF 在尖锐拐角处容易变圆，因为单通道距离场会丢失拐角信息。MSDF 用 RGB 三个通道分别存储不同方向的边界距离，能在同样小的 atlas 下保持更锐利的拐角。

Unity 内置 TMP 目前**不直接生成 MSDF**，但社区已有实现：

- [MerlinVR/Unity-MSDF-Fonts](https://github.com/MerlinVR/Unity-MSDF-Fonts)
- [InitialPrefabs/InitialPrefabs.Msdf](https://github.com/InitialPrefabs/InitialPrefabs.Msdf)

如果项目需要超大标题、Logo 级文字，MSDF 值得评估。

---

## 2. 代码示例

### 示例 A：创建并应用 Material Preset

```csharp
using TMPro;
using UnityEngine;

public class MaterialPresetSwitcher : MonoBehaviour
{
    [SerializeField] private TMP_Text tmpText;
    [SerializeField] private Material[] presets; // 在 Inspector 中拖入多个 Preset

    public void SwitchTo(int index)
    {
        if (tmpText == null || presets == null || presets.Length == 0)
            return;

        index = Mathf.Clamp(index, 0, presets.Length - 1);
        tmpText.fontSharedMaterial = presets[index];
        // 注意：fontSharedMaterial 修改共享 material；
        // 如果只想影响当前组件，使用 tmpText.fontMaterial。
    }
}
```
**运行方式：**

1. 创建一个 TMP 字体和一个 Material Preset（金色描边）。
2. 把两个 Material 拖到 `presets` 数组。
3. 运行后调用 `SwitchTo(0/1)` 观察效果切换。

**预期输出：** 文本在不重建 atlas 的情况下切换视觉风格。

---

### 示例 B：创建 TMP Sprite Asset 并在文本中使用

```csharp
using TMPro;
using UnityEditor;
using UnityEngine;

public static class SpriteAssetCreator
{
#if UNITY_EDITOR
    [MenuItem("Assets/Create/TMP Sprite Asset From Selection")]
    public static void CreateFromSelection()
    {
        Texture2D tex = Selection.activeObject as Texture2D;
        if (tex == null)
        {
            Debug.LogWarning("请先选中一张 Texture2D。");
            return;
        }

        string path = AssetDatabase.GetAssetPath(tex);
        string outPath = path.Replace(".png", "_Sprite Asset.asset");

        TMP_SpriteAsset spriteAsset = ScriptableObject.CreateInstance<TMP_SpriteAsset>();
        spriteAsset.spriteSheet = tex;
        spriteAsset.material = new Material(Shader.Find("TextMeshPro/Sprite"));
        spriteAsset.material.mainTexture = tex;

        // 手动添加一个示例 sprite（实际项目中可用 Sprite Editor 批量切图）
        TMP_Sprite sprite = new TMP_Sprite
        {
            name = "icon_coin",
            hashCode = TMP_TextUtilities.GetSimpleHashCode("icon_coin"),
            unicode = 0xE000, // 私有使用区，避免与普通字符冲突
            x = 0,
            y = 0,
            width = 64,
            height = 64,
            pivot = new Vector2(32, 32),
            spriteAsset = spriteAsset
        };
        spriteAsset.spriteInfoList.Add(sprite);

        AssetDatabase.CreateAsset(spriteAsset, outPath);
        AssetDatabase.AddObjectToAsset(spriteAsset.material, spriteAsset);
        AssetDatabase.SaveAssets();
    }
#endif
}
```
**运行方式：**

1. 准备一张 64×64 的 PNG，选中它。
2. 点击菜单 `Assets > Create > TMP Sprite Asset From Selection`。
3. 选中生成的 Sprite Asset，在 `TMP_Text` 的 **Sprite Asset** 字段引用它。
4. 在文本框输入：

```text
获得 <sprite name="icon_coin"> x100
```
**预期输出：** 金币图标与文字在同一行渲染。

---

### 示例 C：自定义 SDF Shader（描边颜色随 UV 渐变）

```shaderlab
Shader "Custom/TMP Gradient Outline"
{
    Properties
    {
        _FaceTex ("Face Texture", 2D) = "white" {}
        _FaceColor ("Face Color", Color) = (1,1,1,1)
        _OutlineColor1 ("Outline Color 1", Color) = (1,0,0,1)
        _OutlineColor2 ("Outline Color 2", Color) = (0,0,1,1)
        _OutlineWidth ("Outline Width", Range(0,1)) = 0.1
        _FaceDilate ("Face Dilate", Range(-1,1)) = 0
        _GradientAngle ("Gradient Angle", Range(0,6.283)) = 0
    }

    SubShader
    {
        Tags { "Queue"="Transparent" "IgnoreProjector"="True" "RenderType"="Transparent" }
        Lighting Off
        Cull Off
        ZWrite Off
        ZTest [unity_GUIZTestMode]
        Blend SrcAlpha OneMinusSrcAlpha

        Pass
        {
            Name "FORWARD"
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile __ UNITY_UI_CLIP_RECT
            #include "UnityCG.cginc"
            #include "UnityUI.cginc"
            #include "Assets/TextMesh Pro/Shaders/TMPro_Properties.cginc"
            #include "Assets/TextMesh Pro/Shaders/TMPro.cginc"

            struct appdata_t
            {
                float4 vertex   : POSITION;
                fixed4 color    : COLOR;
                float2 texcoord0 : TEXCOORD0;
                float2 texcoord1 : TEXCOORD1;
            };

            struct v2f
            {
                float4 vertex   : SV_POSITION;
                fixed4 color    : COLOR;
                float2 texcoord0 : TEXCOORD0;
                float2 texcoord1 : TEXCOORD1;
                float4 worldPosition : TEXCOORD2;
            };

            uniform float4 _ClipRect;
            fixed4 _OutlineColor1;
            fixed4 _OutlineColor2;
            float _OutlineWidth;
            float _GradientAngle;

            v2f vert(appdata_t v)
            {
                v2f OUT;
                OUT.worldPosition = v.vertex;
                OUT.vertex = UnityObjectToClipPos(v.vertex);
                OUT.color = v.color;
                OUT.texcoord0 = v.texcoord0;
                OUT.texcoord1 = v.texcoord1;
                return OUT;
            }

            fixed4 frag(v2f IN) : SV_Target
            {
                float d = tex2D(_MainTex, IN.texcoord0).a;

                // 基于 UV 生成渐变
                float t = (IN.texcoord0.x * cos(_GradientAngle) +
                           IN.texcoord0.y * sin(_GradientAngle)) * 0.5 + 0.5;
                fixed4 outlineCol = lerp(_OutlineColor1, _OutlineColor2, t);

                // Soft threshold：face
                float faceAlpha = smoothstep(_OutlineWidth, _OutlineWidth + 0.05, d);
                // Outline 区域
                float outlineAlpha = smoothstep(0.0, _OutlineWidth, d) * (1.0 - faceAlpha);

                fixed4 c = lerp(outlineCol, _FaceColor * IN.color, faceAlpha);
                c.a = saturate(faceAlpha + outlineAlpha) * IN.color.a;

                #ifdef UNITY_UI_CLIP_RECT
                c.a *= UnityGet2DClipping(IN.worldPosition.xy, _ClipRect);
                #endif

                return c;
            }
            ENDCG
        }
    }
}
```
> [!warning] 简化版 Shader 说明
> 上面是一个教学级简化实现，没有包含 TMP 内置 shader 的完整功能（如软边、阴影、Clip Rect 的完整支持）。生产环境建议复制 `TextMeshPro/SDF Mobile` 或 `TextMeshPro/SDF` 并在其基础上修改，而不是从零写。

**运行方式：**

1. 在 Project 窗口右键 `Create > Shader > Unlit Shader`，命名为 `Custom/TMP Gradient Outline`。
2. 用上面代码替换内容。
3. 选中一个 TMP Font Asset，右键 `Create > TextMeshPro > Material Preset`。
4. 把新建 Material 的 Shader 改为 `Custom/TMP Gradient Outline`。
5. 在 TMP 文本上切换该 material，调整 `_OutlineColor1/2` 与 `_GradientAngle`。

**预期输出：** 文字边缘出现随 UV 方向线性渐变的描边。

---

## 3. 练习

### 练习 1: 批量创建 Material Preset

写一段 Editor 脚本，为选中的 TMP_FontAsset 一次性创建 3 个 Material Preset：

- `Title`：白色面 + 黑色 0.15 描边。
- `Common`：浅灰色面，无描边。
- `Rare`：金色面 + 深红色 0.1 描边。

提示：使用 `Material.Instantiate` 复制默认 material，然后修改 `shaderKeywords` 和 shader 属性。

### 练习 2: Sprite Asset 批量切图

准备一张 256×64 的横向图标条（4 个 64×64 图标）。写一个编辑器脚本把它切成 4 个 sprite，并按顺序命名为 `icon_0` 到 `icon_3`，生成 `TMP_SpriteAsset`。

### 练习 3（可选）: 自定义 Shader 添加闪烁描边

基于示例 C，让描边颜色随时间正弦变化。要求在 Shader 中使用 `_Time.y` 实现，无需每帧修改 material。

---

## 3.5 参考答案

> [!tip]- 练习 1 参考答案
> ```csharp
> #if UNITY_EDITOR
> using TMPro;
> using UnityEditor;
> using UnityEngine;
>
> public static class PresetBatchCreator
> {
>     [MenuItem("Assets/Create/TMP Material Presets/Title-Common-Rare")]
>     public static void CreatePresets()
>     {
>         TMP_FontAsset font = Selection.activeObject as TMP_FontAsset;
>         if (font == null)
>         {
>             Debug.LogWarning("请选中一个 TMP_FontAsset。");
>             return;
003e         }
>
>         string path = AssetDatabase.GetAssetPath(font);
>         string dir = System.IO.Path.GetDirectoryName(path);>
>         Material Create(string name, Color face, Color outline, float width)
>         {
>             Material mat = new Material(font.material);
>             mat.name = $"{font.name} - {name}";
>             mat.SetColor("_FaceColor", face);
>             mat.SetColor("_OutlineColor", outline);
>             mat.SetFloat("_OutlineWidth", width);
>             string p = System.IO.Path.Combine(dir, mat.name + ".mat");
>             AssetDatabase.CreateAsset(mat, p);
>             return mat;
>         }
>
>         Create("Title", Color.white, Color.black, 0.15f);
>         Create("Common", new Color(0.85f, 0.85f, 0.85f), Color.clear, 0f);
>         Create("Rare", new Color(1f, 0.84f, 0f), new Color(0.5f, 0f, 0f), 0.1f);
>         AssetDatabase.SaveAssets();
>     }
> }
> #endif
> ```
> 如果你的实现创建了三个共享同一 atlas 的 material 并能在 Inspector 中调整颜色，就是正确的。

> [!tip]- 练习 2 参考答案
> 核心思路是按列/行切分：
> ```csharp
> #if UNITY_EDITOR
> using System.Collections.Generic;
> using TMPro;
> using UnityEditor;
> using UnityEngine;
>
> public static class SpriteAssetSlicer
> {
>     [MenuItem("Assets/Create/TMP Sprite Asset/Slice 4 Icons")]
>     public static void Slice()
>     {
>         Texture2D tex = Selection.activeObject as Texture2D;
>         if (tex == null || tex.width != 256 || tex.height != 64)
>         {
>             Debug.LogWarning("需要 256x64 的纹理。");
>             return;
>         }
>
>         string path = AssetDatabase.GetAssetPath(tex);
>         string outPath = path.Replace(".png", "_Sprites.asset");
>
>         TMP_SpriteAsset asset = ScriptableObject.CreateInstance<TMP_SpriteAsset>();
>         asset.spriteSheet = tex;
>         asset.material = new Material(Shader.Find("TextMeshPro/Sprite"));
>         asset.material.mainTexture = tex;
>
>         List<TMP_Sprite> sprites = new List<TMP_Sprite>();
>         int cols = tex.width / 64;
>         for (int i = 0; i < cols; i++)
>         {
>             TMP_Sprite s = new TMP_Sprite
>             {
>                 name = $"icon_{i}",
>                 hashCode = TMP_TextUtilities.GetSimpleHashCode($"icon_{i}"),
>                 unicode = (uint)(0xE000 + i),
>                 x = i * 64,
>                 y = 0,
>                 width = 64,
>                 height = 64,
>                 pivot = new Vector2(32, 32),
>                 spriteAsset = asset
>             };
>             sprites.Add(s);
>         }
>         asset.spriteInfoList = sprites;
>
>         AssetDatabase.CreateAsset(asset, outPath);
>         AssetDatabase.AddObjectToAsset(asset.material, asset);
>         AssetDatabase.SaveAssets();
>     }
> }
> #endif
> ```
> 命名和 UV 计算只要与纹理实际布局一致即可。

> [!tip]- 练习 3 参考答案（可选）
> 在 Shader 的 fragment 函数中加入时间项：> ```hlsl
> float flash = sin(_Time.y * 4.0) * 0.5 + 0.5;
> fixed4 outlineCol = lerp(_OutlineColor1, _OutlineColor2, flash);\u> ```
> 不需要 C# 脚本；shader 自身读取 `_Time.y`。

> [!note] 答案使用方式
> 先独立完成练习，再展开查看参考答案。参考答案不是唯一解——如果你的实现通过了测试或达到了题目要求，就是正确的。

---

## 4. 扩展阅读

- [TextMeshPro Shaders documentation](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/Shaders.html)
- [TextMeshPro Sprite Asset documentation](https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.2/manual/Sprites.html)
- [TextMeshPro Style Sheets documentation](https://docs.unity3d.com/Packages/com.unity.textmeshpro@4.0/manual/StyleSheets)
- [MerlinVR/Unity-MSDF-Fonts](https://github.com/MerlinVR/Unity-MSDF-Fonts) — 社区 MSDF 实现。
- [InitialPrefabs/InitialPrefabs.Msdf](https://github.com/InitialPrefabs/InitialPrefabs.Msdf) — 另一 MSDF 方案。
- Viktor Chlumský, "Shape Decomposition for Multi-Channel Distance Fields" — MSDF 原理论文。

---

## 常见陷阱

- **Material Preset 误用 `fontMaterial`**：`fontMaterial` 会为当前文本实例化一份私有 material，适合运行时修改颜色；如果只是想切换共享预设，用 `fontSharedMaterial` 更省内存。
- **Sprite 没有绑定到 Text 组件**：必须在 TMP 组件的 **Sprite Asset** 字段引用，否则 `<sprite>` 标签不会解析。
- **Sprite 与字体使用不同 Shader**：会导致 extra draw call。尽量让 sprite asset 的 material 使用 `TextMeshPro/Sprite` 且与字体在同一个 Canvas batch 条件内。
- **自定义 Shader 丢失 Clip Rect**：UI 中若文字超出 Mask，需要保留 `UNITY_UI_CLIP_RECT` 相关代码。
- **MSDF 不需要更大的 atlas**：MSDF 的优势是在相同 atlas 大小下更锐利，而不是为了锐利必须放大 atlas；错误地增大 atlas 会浪费内存。
