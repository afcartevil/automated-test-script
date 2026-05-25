---
name: vib-adapt-rotor-driver
description: Guides Transsion/MTK ERM rotor vibrator driver adaptation via regulator-vibrator.c—DWS PMIC/LDO, DTS in *_touch.dtsi, and KO/ProjectConfig. Use when adapting 转子马达驱动、ERM、regulator-vibrator、vib-supply、min-volt/max-volt、probe failed、port 参考机型；上电验证用 fc-vib-rotor。
disable-model-invocation: false
---

# 转子马达驱动适配

## 范围

- **转子 ERM**：`drivers/leds/regulator-vibrator.c`，`led_classdev` 控 PMIC LDO。
- **非本 skill**：LRA/RichTap → `vib-adapt-projectconfig`、`vib-adapt-haptic-rc`。
- **DTS 位置**：板级在 SoC `*.dts`；机型覆盖在 `arch/arm64/boot/dts/mediatek/tp/*_touch.dtsi`。
- **上电验证**：`func-check` → **`fc-vib-rotor`**（probe + `duration`/`activate` sysfs）。

| 项 | 转子 | LRA |
|----|------|-----|
| compatible | `regulator-vibrator` | 厂商 haptic |
| sysfs | `leds/vibrator` | `vibrator_single` / `vibrator_l`/`r` |
| 宏控 | `CUSTOM_KERNEL_VIBRATOR`，无 `TRAN_RICHTAP_SUPPORT` | Richtap 宏 |

## 工作流

```
确认 ERM → DWS(VIBR LDO/GPIO) → DTS(touch dtsi) → KO/宏控 → fc-vib-rotor
```

## 驱动与 DTS 要点

**Probe 依赖**（`regulator-vibrator.c`）：

| 属性 | 说明 |
|------|------|
| `vib-supply` | regulator 名 `"vib"` |
| `min-volt` / `max-volt` | µV，min ≤ max |
| `label` | LED 名，常为 `vibrator` |

**板级**（SoC dts，勿在 touch dtsi 重复整节点）：

```dts
regulator_vibrator: regulator-vibrator {
    compatible = "regulator-vibrator";
    label = "vibrator";
    min-volt = <2800000>;
    max-volt = <3500000>;
    vib-supply = <&mt6368_vibr>;
};
```

**机型覆盖**（`*_touch.dtsi`）：

```dts
&regulator_vibrator {
    min-volt = <3000000>;
    max-volt = <3500000>;
};
```

规则：参考同平台 `tran_*_touch.dtsi`；只改电压/supply；默认 3.0–3.5 V；LDO 定义见 `vib-adapt-dts-regulator`。

失败日志：`get regulator`、`get max-volt failed`、`min > max`、`probe failed`。

## DWS（必查）

在 Meta/vendor DWS 核对 **VIBR LDO** 与 `vib-supply` 一致；电压档覆盖 DTS min/max；若有 GPIO 使能则为输出且电平与硬件一致。

## 编译

- `CONFIG_LEDS_REGULATOR_VIBRATOR` + **`regulator-vibrator` KO**（`drivers/leds/BUILD.bazel`）
- `ProjectConfig.mk`：`CUSTOM_KERNEL_VIBRATOR` 非 `no`；转子机勿开 `TRAN_RICHTAP_SUPPORT`

## Fail 速查

| 现象 | 处理 |
|------|------|
| supply / regulator | PMIC dtsi、`vib-supply`、DWS |
| 电压解析失败 | 改 `&regulator_vibrator` |
| 无 KO | 宏控 / defconfig / KO 列表 |
| probe OK 不振 | DWS 电压、OC 日志、硬件 |

## 输出（adaptation-debug）

```markdown
**马达类型**：转子 ERM
**skill**：vib-adapt-rotor-driver

### 修改
- DWS：…
- DTS：`…/tran_*_touch.dtsi`
- 编译：…

### 验证
- 烧录后执行 **fc-vib-rotor**
```

## 参考

- 仓库路径：`~/.cursor/kb/tp-vib-harness/references/vibrator-path-reference-20260520.md`（表内 **转子** 行；根树 `kernel_device_modules-6.12/`）
- 功能检查：`fc-vib-rotor`
