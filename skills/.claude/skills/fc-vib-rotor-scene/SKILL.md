---
name: fc-vib-rotor-scene
description: Func-check skill for Transsion ERM rotor three-level / scene haptic import via adb getprop. Pass（已导入）when properties are empty/disabled or option≠single; Fail only when option=single and all 6 feature/algo props enabled. Use when func-check needs 转子马达、三档振动、交互场景震感、通知类振动、vibrator.option、vibrate10/20/30、vibrate30_z、realvib05、vibrator.algo 导入核对。
---

# FC: 转子马达场景震感导入检查

核对转子 ERM 机型三档振动、交互场景震感、通知类振动相关 ODM 属性是否处于**已导入**状态。

## 转子机导入态说明

转子 ERM 机型**不依赖** LRA 那套 `vibrate10/20/30` feature 开关；属性为空或未开启是**正常已导入**状态，表示 ODM 未错误打入线性马达/4D 属性包。

| 场景 | 导入状态 |
|------|----------|
| 7 项属性均为空 | **已导入**（Pass） |
| `vibrator.option` 非 `single`，且 feature/algo 未全开 | **已导入**（Pass） |
| `vibrator.option` 为 `single`，且 6 项 feature/algo **全部**开启 | **未导入或不完整**（Fail） |

**禁止**将「属性为空」解读为「未导入」。空 = 转子机正确导入态。

## 判定说明

| 总结果 | 含义 |
|--------|------|
| **Pass** | 三档振动 / 场景震感**已导入** |
| **Fail** | 三档振动 / 场景震感**未导入或不完整**（异常属性组合） |

单项 Pass = 该属性满足转子机已导入条件；**不要**将单项 Pass 理解为「该项未导入」。

## 前置条件

- 设备已通过 `adb devices` 连接
- 确认为 **转子 ERM**（非 LRA/RichTap）；硬件验证见 `fc-vib-rotor`

## 检查属性

### `ro.vendor.tran.vibrator.option`

| 实际值 | 结果 | 说明 |
|--------|------|------|
| 空（属性不存在 / `getprop` 无输出） | **Pass** | 转子机正常已导入 |
| 任意非 `single` 值 | **Pass** | 非异常组合 |
| `single` | 见总结果 | 仅当 6 项 feature 全开时总结果 Fail |

### 以下 6 项 feature / algo 属性

| 属性 | Pass（已导入） | Fail |
|------|----------------|------|
| `ro.tr_vibrate.vibrate10.feature.support` | 空、`false`、`0` 等禁用值 | `true`、`1` 或其它非禁用值 |
| `ro.tr_vibrate.vibrate20.feature.support` | 同上 | 同上 |
| `ro.tr_vibrate.vibrate30.feature.support` | 同上 | 同上 |
| `ro.vendor.tran.vibrator.algo` | 空、`false`、`0` 等禁用值 | 非空且非禁用值 |
| `ro.tr_vibrate.vibrate30_z.feature.support` | 空、`false`、`0` 等禁用值 | `true`、`1` 或其它非禁用值 |
| `ro.tr_vibrate.realvib05.feature.support` | 空、`false`、`0` 等禁用值 | `true`、`1` 或其它非禁用值 |

### 总结果

| 结果 | 条件 |
|------|------|
| **Pass（已导入）** | `vibrator.option` 为空或非 `single`；或任一 feature/algo 属性未开启 |
| **Fail（未导入或不完整）** | `vibrator.option` 为 `single`，**且**上表 6 项**全部**开启 |

## 检查步骤

### 方式 A：脚本（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-vib-rotor-scene\scripts\check_vib_rotor_scene.py"
```

退出码 `0` = Pass（已导入），`1` = Fail（未导入或不完整）。

### 方式 B：手工 adb

```bash
adb shell getprop ro.vendor.tran.vibrator.option
adb shell getprop ro.tr_vibrate.vibrate10.feature.support
adb shell getprop ro.tr_vibrate.vibrate20.feature.support
adb shell getprop ro.tr_vibrate.vibrate30.feature.support
adb shell getprop ro.vendor.tran.vibrator.algo
adb shell getprop ro.tr_vibrate.vibrate30_z.feature.support
adb shell getprop ro.tr_vibrate.realvib05.feature.support
```

## 输出格式

```
## 功能检查：转子马达三档振动/场景震感导入

**skill**: fc-vib-rotor-scene
**结果**: Pass（已导入）/ Fail（未导入或不完整）

| 检查项 | 期望（已导入） | 实际 | Pass/Fail |
|--------|----------------|------|-----------|
| ro.vendor.tran.vibrator.option | 空或非 single | ... | ... |
| ro.tr_vibrate.vibrate10.feature.support | 未开启/空 | ... | ... |
| ... | ... | ... | ... |

### 结论
（Pass：三档振动已导入，结束；Fail：见 Fail 后续）
```

输出时**总结果与导入状态必须一致**：Pass 即写「已导入」，禁止再写「属性为空故未导入」。

## Fail 后续

Fail 表示 `option=single` 且 6 项 feature 全开，属**异常属性组合**（疑似误导入 LRA/4D 属性包到转子机）：

- 核对 ODM `PRODUCT_*_PROPERTIES` / `vibrator.mk`：移除或关闭误打的 `ro.tr_*`、`ro.vendor.tran.vibrator.*`
- 对照已量产转子参考机 `getprop`，确认属性源
- 宏控：`CUSTOM_KERNEL_VIBRATOR` 开、`TRAN_RICHTAP_SUPPORT` 关 → `vib-adapt-rotor-driver` / `vib-adapt-projectconfig`

## Harness 路由

- func-check：`func-check-registry.md` → `fc-vib-rotor-scene`
- adaptation-debug：`routing-table.md` 马达区 → 先 `fc-vib-rotor-scene`，Fail → ODM 属性打包核对 / `vib-adapt-projectconfig`
