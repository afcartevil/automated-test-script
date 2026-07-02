---
name: fc-vib-lra-features
description: Func-check skill for Transsion LRA vibration feature import via adb getprop — ringtone infinite adjustment, self-developed vibration SDK, ringtone sync, PUBG/FreeFire HQ haptics, scene vibration. Pass when each feature's required ro.tr_vibrate.* props are enabled per SKILL matrix. Use when func-check needs 铃声无极振动、自研振动SDK、铃声随振、PUBG、freefire、高品质振动、场景振动、交互场景震感、真实触感、notification_lra、vibrate30_z、vibrate10/20/30 导入核对。
---

# FC: LRA 振动功能导入检查

核对 LRA 机型铃声无极振动调节、自研振动 SDK、铃声随振、PUBG/FreeFire 高品质振动、交互场景震感、真实触感等功能的 ODM 属性是否**已导入**。

**判定依据**：下方「功能-属性矩阵」表。每行所需属性**全部**开启才 Pass；任一缺失或未开启则该行 Fail。

> 修改映射关系时，同步更新 [scripts/feature_matrix.py](scripts/feature_matrix.py)（脚本读取同一矩阵）。

## 前置条件

- 设备已通过 `adb devices` 连接
- 确认为 **LRA / RichTap** 线性马达机型（非转子 ERM）

## 属性开启判定

| 属性 | Pass 条件 |
|------|-----------|
| `ro.tr_vibrate.notification_lra` | 值**不为空**即可 |
| 其余 `*.feature.support` 等 | `true` 或 `1` |
| 其余属性为空、`false`、`0` 等 | 未开启 |

## 功能-属性矩阵

**结果由本表决定。** 每行「所需属性」列内属性须**全部**开启，对应功能才 Pass。

| 功能 | 轴向 | 所需属性（全部开启才 Pass） |
|------|------|----------------------------|
| 铃声无极振动调节 | X | `ro.tr_vibrate.vibrate30.feature.support` |
| 铃声无极振动调节 | Z | `ro.tr_vibrate.vibrate30_z.feature.support`、`ro.tr_vibrate.realvib05.feature.support` |
| 触感反馈无极振动调节 | X | `ro.tr_vibrate.vibrate30.feature.support` |
| 触感反馈无极振动调节 | Z | `ro.tr_vibrate.vibrate30_z.feature.support`、`ro.tr_vibrate.realvib05.feature.support` |
| 自研振动 SDK | X | `ro.tr_vibrate.vibrate30.feature.support` |
| 自研振动 SDK | Z | `ro.tr_vibrate.vibrate30_z.feature.support` |
| 铃声随振 | X | `ro.tr_vibrate.notification_lra`、`ro.tr_vibrate.vibrate30.feature.support` |
| 铃声随振 | Z | `ro.tr_vibrate.vibrate30_z.feature.support`、`ro.tr_vibrate.notification_lra` |
| PUBG/FreeFire 高品质振动 | X | `ro.tr_vibrate.vibrate10.feature.support`、`ro.tr_vibrate.vibrate20.feature.support`、`ro.tr_vibrate.vibrate30.feature.support` |
| PUBG/FreeFire 高品质振动 | Z | `ro.tr_vibrate.vibrate30_z.feature.support` |
| 交互场景震感（场景振动） | X | `ro.tr_vibrate.vibrate10.feature.support`、`ro.tr_vibrate.vibrate20.feature.support`、`ro.tr_vibrate.vibrate30.feature.support` |
| 交互场景震感（场景振动） | Z | `ro.tr_vibrate.vibrate30_z.feature.support` |
| 真实触感 | — | `ro.tr_vibrate.realvib05.feature.support` |

### 属性速查（涉及哪些功能）

| 属性 | 关联功能 |
|------|----------|
| `ro.tr_vibrate.vibrate10.feature.support` | X 轴交互场景震感、X 轴 PUBG/FreeFire |
| `ro.tr_vibrate.vibrate20.feature.support` | X 轴交互场景震感、X 轴 PUBG/FreeFire |
| `ro.tr_vibrate.vibrate30.feature.support` | X 轴铃声无极、X 轴触感反馈无极、自研 SDK（X）、X 轴铃声随振、X 轴交互场景震感、X 轴 PUBG/FreeFire |
| `ro.tr_vibrate.vibrate30_z.feature.support` | Z 轴铃声无极、Z 轴触感反馈无极、自研 SDK（Z）、Z 轴铃声随振、Z 轴交互场景震感、Z 轴 PUBG/FreeFire |
| `ro.tr_vibrate.notification_lra` | X/Z 轴铃声随振 |
| `ro.tr_vibrate.realvib05.feature.support` | Z 轴铃声无极、Z 轴触感反馈无极、真实触感（X/Z） |

## 检查步骤

### 方式 A：脚本（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-vib-lra-features\scripts\check_vib_lra_features.py"
```

退出码 `0` = Pass（检测完成），`1` = 执行失败（如 adb 不可用）。

### 方式 B：手工 adb

```bash
adb shell getprop ro.tr_vibrate.vibrate10.feature.support
adb shell getprop ro.tr_vibrate.vibrate20.feature.support
adb shell getprop ro.tr_vibrate.vibrate30.feature.support
adb shell getprop ro.tr_vibrate.vibrate30_z.feature.support
adb shell getprop ro.tr_vibrate.notification_lra
adb shell getprop ro.tr_vibrate.realvib05.feature.support
```

再按「功能-属性矩阵」逐行判定。

## Pass / Fail

| 结果 | 条件 |
|------|------|
| **Pass** | 导入检测流程执行成功（默认模式） |
| **Fail** | 仅在脚本执行失败（如 adb 不可用）时返回 |

默认为**导入检测模式**：逐行给出 Pass/Fail，允许部分功能未导入。

单项 Fail = 该行「所需属性」有缺失或未开启，不影响脚本总结果 Pass。

## 输出格式

```
## 功能检查：LRA 振动功能导入

**skill**: fc-vib-lra-features
**结果**: Pass

| 功能 | 轴向 | 所需属性 | 实际 | Pass/Fail |
|------|------|----------|------|-----------|
| 铃声无极振动调节 | X | vibrate30 | vibrate30='true' | Pass |
| ... | ... | ... | ... | ... |

=== 汇总 ===
- 已导入功能数: N
- 未导入功能数: M
- 已导入: ...
- 未导入或不完整: ...

RESULT: Pass - 导入检测完成。
```

## Fail 后续（单项 Fail 时参考）

- `vib-adapt-projectconfig`：核对 `vibrator.mk` / `ProjectConfig.mk` 及 `PRODUCT_*_PROPERTIES` 是否导入对应 `ro.tr_vibrate.*`
- 属性源未在本仓时：对照已量产参考机 `getprop` 与 ODM 属性打包脚本
- 硬件未 probe：先 `fc-vib-driver`，再重跑本 skill

## Harness 路由

- func-check：`func-check-registry.md` → `fc-vib-lra-features`
- adaptation-debug：`routing-table.md` 马达区 → 先 `fc-vib-lra-features`，Fail → `vib-adapt-projectconfig`

