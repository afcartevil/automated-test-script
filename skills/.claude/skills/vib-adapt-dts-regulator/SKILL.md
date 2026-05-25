---
name: vib-adapt-dts-regulator
description: Adds or adjusts vibrator supply voltage in DTS using the regulator_vibrator naming pattern, placement alongside TP touch dtsi merges, default 3–3 V when unspecified. Use when editing device trees for vibration/LDO/regulator wiring, MTK/Transsion TP or touch dtsi folders, mentions regulator_vibrator, vibrator regulator, min-microvolt/max-microvolt, or haptic power DTS.
disable-model-invocation: false
---

# DTS：`regulator_vibrator` 马达供电电压配置

## 适用场景

- 在工程中为线性马达/haptic/vibrator 配置或修改供电 regulator 的设备树段落。
- 节点名遵循 **`regulator_vibrator`**（与用户约定一致）。
- **配置位置**：通常在 **TP（触控/touchpanel）合并或同路径的 dtsi** 内（例如与 `*_touch.dtsi`、`tp` 关联目录或 vendor touch 补丁中的同一层级片段），与用户说明的「放在 tp 目录下」一致；若当前工程别处已定义同名节点则优先合并到该项目既有文件中，避免重复定义。

## 电压约定（未说明时）

- **最小电压与最大电压均配置为 3 V**。
- 设备树中电压单位为 **微伏（µV）**：`3 V` → **`<3000000>`**。
- 未说明时同时设置：
  - `regulator-min-microvolt = <3000000>;`
  - `regulator-max-microvolt = <3000000>;`

若用户另行给出电压，则按用户数值换算为 µV（例如 2.8 V → `<2800000>`），并同时更新 min/max（固定输出时 min 与 max 通常相同）。

## 编写步骤

1. **定位文件**：在工程 mediatek/touch/TP 相关 dtsi 或 `*_touch.dtsi` 及 include 链中查找是否已有 `regulator_vibrator` 或 vibrator 电源节点；有则只改电压与必要属性，无则新增。
2. **节点形态**：按工程现有 PMIC/LDO 写法书写（常见为某 PMIC 子节点或 `regulator-fixed`/`regulator-ldo` 等），**保留项目既有 `compatible`、父节点与 phandle 命名习惯**；保证标签或节点引用名与用户约定 **`regulator_vibrator`** 一致（若工程用 label，例如 `regulator_vibrator: xxx { ... }`）。
3. **必填电气属性**（在 regulator 节点上）：
   - `regulator-min-microvolt`
   - `regulator-max-microvolt`
   - 未说明时二者均为 `<3000000>`。
4. **消费者关联**：确认 vibrator/haptic 驱动对应节点里 `vcc-supply = <&regulator_vibrator>;`（或工程实际使用的 supply 属性名）指向该 regulator；若新增 regulator，需同步添加或修正该引用。
5. **校验**：`dtc` 或工程内置 dts 编译无重复 label、无未解析 phandle；电压范围满足所用 PMIC 数据手册允许范围。

## 示例（结构示意，需按项目 PMIC 父节点替换）

```dts
/* 未说明电压时：min/max 均为 3 V */
regulator_vibrator: vibrator-vdd {
	regulator-name = "regulator_vibrator";
	regulator-min-microvolt = <3000000>;
	regulator-max-microvolt = <3000000>;
	/* 其余属性继承工程同一批 LDO 的写法，如 enable GPIO、parent supply 等 */
};
```

## 输出给用户的说明

- 明确写出**修改了哪个 dtsi 文件**、**节点路径/label**、**min/max 微伏值**。
- 若工程约束不允许 3 V，应说明需用户确认 PMIC 与马达规格后再改。

## 附加资源

- 各平台 PMIC 节点结构差异大时，见 [reference.md](reference.md)。
