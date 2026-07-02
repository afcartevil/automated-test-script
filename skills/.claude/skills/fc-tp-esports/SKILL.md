---
name: fc-tp-esports
description: Func-check skill for Transsion TP esports control import via adb getprop and esports proc nodes. Use when func-check needs 电竞操控、电竞引擎、tp_esports10/20/30、game_mode、tp_transient_report_rate_switch、esports-engine 是否导入。
---

# FC: 电竞操控导入检查

核对 **ODM 属性** 与 **内核电竞 proc 节点** 是否已导入。节点清单来自 `transsion_node.c`（`FEATURE_ESPORT`）与 `Trantp.cpp` HAL 路径定义（OpenGrok `tOS_mtk_A16_trunk`）。

## 前置条件

- 设备已通过 `adb devices` 连接
- 建议 `fc-tp-driver` Pass（TP 驱动已 probe）
- 设备亮屏、TP 非 suspend（写节点时驱动会拒绝 suspend 态）

## 检查属性（OR）

以下**任一**为真即满足属性门控（`true` 或 `1`）：

| 属性（新） | 属性（旧，Android 36 前） | 版本 |
|-----------|-------------------------|------|
| `ro.tr_game.tp_esports10.feature.support` | `ro.os_game_tp_esports10.support` | 电竞操控 1.0 |
| `ro.tr_game.tp_esports20.feature.support` | `ro.os_game_tp_esports20.support` | 电竞操控 2.0 |
| `ro.tr_game.tp_esports30.feature.support` | `ro.os_game_tp_esports30.support` | 电竞操控 3.0 |

来源：`TranBuild.java` 中 `TRAN_GAME_TP_ESPORTS10/20/30_SUPPORT`。

## 检查节点（FEATURE_ESPORT）

`tran_proc_node_create()` 在 `is_support_feature(FEATURE_ESPORT)` 为真时创建（DTS `touchscreen,esports-engine`）：

| proc 路径 | 内核 cmd | 读写说明 |
|-----------|----------|----------|
| `/proc/game_mode` | `LOCK_POINT_SWITCH` | 写 `0–5`；读含 `Gear position` 或档位数字 |
| `/proc/game_state` | `SET_GAME_MODE` | 写 `0/1`；读当前游戏态整数 |
| `/proc/tp_transient_report_rate_switch` | `TRANSIENT_SAMPLING_RATE_SWITCH` | 写 `0/1`；读瞬时采样率开关 |
| `/proc/tp_micro_control_accuracy` | `MICRO_CONTROL_ACCURACY` | 写 `0–5`；读微操精度档位 |

可选（`FEATURE_DYNAMIC_REPORT_RATE`，DTS `touchscreen,dynamic-report-rate-support`）：

| proc 路径 | 说明 |
|-----------|------|
| `/proc/tp_report_rate_switch` | 动态报点率；节点缺失标 N/A，不单独 Fail |

## 检查步骤

### 方式 A：脚本（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-esports\scripts\check_tp_esports.py"
```

仅查属性、跳过写节点：

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-esports\scripts\check_tp_esports.py" --skip-write
```

退出码 `0` = Pass，`1` = Fail。

### 方式 B：手工 adb

```bash
adb shell getprop ro.tr_game.tp_esports10.feature.support
adb shell getprop ro.tr_game.tp_esports20.feature.support
adb shell getprop ro.tr_game.tp_esports30.feature.support

adb shell ls -l /proc/game_mode /proc/game_state /proc/tp_transient_report_rate_switch /proc/tp_micro_control_accuracy

adb shell cat /proc/game_mode
adb shell cat /proc/game_state
adb shell cat /proc/tp_transient_report_rate_switch
adb shell cat /proc/tp_micro_control_accuracy

# 写回安全值 0（亮屏态）
adb shell "echo 0 > /proc/game_state"
adb shell "echo 0 > /proc/tp_transient_report_rate_switch"
adb shell "echo 0 > /proc/tp_micro_control_accuracy"
adb shell "echo 0 > /proc/game_mode"
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | 上表属性**至少一项**为 `true`/`1`；4 个 FEATURE_ESPORT 节点均存在；`cat` 无 `Permission denied`/`No such file`；写测试（默认）对 4 节点 `echo 0` 成功 |
| Fail | 三项属性均未开启；或任一必查节点缺失；或读/写被拒绝 |

## 输出格式

```
## 功能检查：电竞操控导入

**skill**: fc-tp-esports
**结果**: Pass / Fail
**检测到版本**: esports10 / esports20 / esports30 / unknown

| 检查项 | 期望 | 实际 | Pass/Fail |
|--------|------|------|-----------|
| esports 属性 | 任一 true/1 | ... | ... |
| /proc/game_mode | 存在且可读写 | ... | ... |
| ... | ... | ... | ... |

### 下一步
（Pass：结束；Fail：见 Fail 后续）
```

## Fail 后续

- 属性未开：核对 ODM `PRODUCT_*_PROPERTIES` / 参考机 `getprop` 打包
- 节点缺失：`tp-adapt-smart-sampling`（`&touch` 的 `touchscreen,esports-engine`）
- 节点只读/Permission denied：`fc-tp-selinux`
- 驱动未加载：`fc-tp-driver`

## Harness 路由

- func-check：`func-check-registry.md` → `fc-tp-esports`
- adaptation-debug：`routing-table.md` TP 区 → 先 `fc-tp-esports`，Fail → `tp-adapt-smart-sampling`
