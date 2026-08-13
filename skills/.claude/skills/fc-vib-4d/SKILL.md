---
name: fc-vib-4d
description: Func-check skill for Transsion 4D game haptic feature properties via adb getprop. Use when func-check needs 4D震感、四围振动、vibrate10/20/30 feature、four_d_vibration.support，或核对 ro.tr_vibrate.* / ro.tr_game.four_d_vibration.support 是否已开启。
---

# FC: 4D 技能震感属性检查

## 前置条件

- 设备已通过 `adb devices` 连接

## 检查属性

| 属性 | Pass 取值 |
|------|-----------|
| `ro.tr_vibrate.vibrate10.feature.support` | `true` |
| `ro.tr_vibrate.vibrate20.feature.support` | `true` |
| `ro.tr_vibrate.vibrate30.feature.support` | `true` |
| `ro.tr_game.four_d_vibration.support` | `true` 或 `1`（部分 ODM 打包为 `1`） |

四项**全部**满足才 Pass。

## 检查步骤

### 方式 A：脚本（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-vib-4d\scripts\check_vib_4d_props.py"
```

退出码 `0` = Pass，`1` = Fail。

### 方式 B：手工 adb

```bash
adb shell getprop ro.tr_vibrate.vibrate10.feature.support
adb shell getprop ro.tr_vibrate.vibrate20.feature.support
adb shell getprop ro.tr_vibrate.vibrate30.feature.support
adb shell getprop ro.tr_game.four_d_vibration.support
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 上表四项均满足 |
| Fail | 任一为空、为 `false`/`0`，或 vibrate 系列非 `true` |

## 输出格式

```
## 功能检查：4D 技能震感属性

**skill**: fc-vib-4d
**结果**: Pass / Fail

| 检查项 | 期望 | 实际 | Pass/Fail |
|--------|------|------|-----------|
| ro.tr_vibrate.vibrate10.feature.support | true | ... | ... |
| ... | ... | ... | ... |

### 下一步
（Pass：结束；Fail：见 Fail 后续）
```

## Fail 后续

- `vib-adapt-projectconfig`：核对 `vibrator.mk` / `ProjectConfig.mk` 及 `PRODUCT_*_PROPERTIES` 是否导入 4D / vibrate 相关 `ro.tr_*` 属性
- 属性源未在本仓时：对照已量产参考机 `getprop` 与 ODM 属性打包脚本

## Harness 路由

- func-check：`func-check-registry.md` → `fc-vib-4d`
- adaptation-debug：`routing-table.md` 马达区 → 先 `fc-vib-4d`，Fail → `vib-adapt-projectconfig`
