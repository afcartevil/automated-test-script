# 智能触控采样率 — 源码参考

分支 `tOS_mtk_A16_trunk`，根路径 `kernel/kernel_device_modules-6.12/drivers/input/touchscreen/transsion/`。

## OpenGrok

```text
python opengrok_query.py --branch tOS_mtk_A16_trunk --full esports-engine --path dts/mediatek/tp --top 10
python opengrok_query.py --branch tOS_mtk_A16_trunk --def parse_touch_feature --json
```

参考 dtsi：`tran_mt6878_cm7_touch.dtsi`、`tran_mt6897_cm8_touch.dtsi`。

## 关键文件

| 文件 | 职责 |
|------|------|
| `core/transsion_core.c` | `parse_touch_feature()`、`tp_state_recovery()` |
| `core/transsion_aidl_interface.c` | `/dev/tppolldrv` ioctl、`is_support_feature()` |
| `core/transsion_node.c` | `/proc/tp_report_rate_switch`、`/proc/tp_transient_report_rate_switch` |
| `vendor/focaltech/ft3683g_spi/focaltech_transsion.c` | `set_ts_mode()` → `fts_esport_feature_switch()` |
| `vendor/focaltech/ft3683g_spi/focaltech_core.c` | 解析 `focaltech,switch-report-support` |

## DTS 解析（`parse_touch_feature`）

- `touchscreen,esports-engine` → `features.esport`（1–4；缺或 >4 置 0）
- `touchscreen,dynamic-report-rate-support` → `features.dynamic_report_rate`

## ioctl 门控与下发

| 处理函数 | 门控 | vendor cmd |
|----------|------|------------|
| `ioctl_transient_rate_handle` | `FEATURE_ESPORT` | `TRANSIENT_SAMPLING_RATE_SWITCH` |
| `ioctl_game_mode_handle` | `FEATURE_ESPORT` | `LOCK_POINT_SWITCH` |
| `ioctl_report_rate_handle` | `FEATURE_DYNAMIC_REPORT_RATE` | trunk 空桩，仅能力判断 |

ioctl / proc / `tp_state_recovery()` 最终均 `ctr->ops->set_ts_mode(cmd, state)`。

## Vendor（Focaltech）

`set_ts_mode()` 中 `REPORT_RATE_SWITCH` 等电竞 cmd 统一进 `fts_esport_feature_switch()`，写 `FTS_REG_TRAN_ESPROTS`。需 DTS `focaltech,switch-report-support` + 固件支持。
