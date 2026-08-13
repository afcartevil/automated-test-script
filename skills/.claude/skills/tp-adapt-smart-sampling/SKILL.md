---
name: tp-adapt-smart-sampling
description: Guides Transsion/MTK smart touch sampling rate (智能触控采样率) DTS adaptation—touchscreen,esports-engine and touchscreen,dynamic-report-rate-support on &touch, plus vendor IC report-rate properties. Use when porting 电竞引擎、报点率切换、report rate、esports-engine、dynamic-report-rate、瞬时采样率、游戏模式触控采样率，或智能触控采样率配置不生效。
---

# 智能触控采样率 DTS 适配

两层 DTS：`&touch`（core 功能开关）+ vendor IC 子节点（IC 报点率能力）。实现链路见下节；OpenGrok / 源码细节见 [reference.md](reference.md)。

## 代码实现链路

```text
Framework/游戏服务
  → /dev/tppolldrv ioctl（transsion_aidl_interface.c）
  → is_support_feature() 读 g_tran_ts.features
  → ctr->ops->set_ts_mode(cmd, state)          // vendor，如 focaltech set_ts_mode
  → fts_esport_feature_switch()                // 写 IC 寄存器 FTS_REG_TRAN_ESPROTS
```

**DTS 落地（probe 时）**

```text
&touch DTS
  → tran_parse_dt() → parse_touch_feature()   // transsion_core.c
  → g_tran_ts.features.esport / dynamic_report_rate
```

| DTS 属性 | 影响 |
|----------|------|
| `touchscreen,esports-engine = <N>` | `features.esport`；门控 `FEATURE_ESPORT`（瞬时采样率、锁点等 ioctl） |
| `touchscreen,dynamic-report-rate-support` | `features.dynamic_report_rate`；门控 `FEATURE_DYNAMIC_REPORT_RATE` |

亮屏恢复：`tp_state_recovery()` 会重放 `REPORT_RATE_SWITCH` / `TRANSIENT_SAMPLING_RATE_SWITCH` 等状态（`transsion_core.c`）。

另有 proc 路径：`/proc/tp_report_rate_switch`、`/proc/tp_transient_report_rate_switch`（`transsion_node.c`）同样可走 `set_ts_mode`。

## 前置

- `fc-tp-driver` Pass
- 参考机型：同 TP IC + 同分支的 `tran_*_touch.dtsi`

## 改 DTS

**1. `&touch`**

```dts
touchscreen,dynamic-report-rate-support;
touchscreen,esports-engine = <1>;   /* 1–4；缺或 >4 → esport=0 */
```

**2. Vendor IC** — Focaltech：`focaltech,switch-report-support;`（`focaltech_core.c` 解析到 `pdata`）

## 验证

```bash
adb shell ls -l /proc/tp_report_rate_switch /proc/tp_transient_report_rate_switch
adb shell dmesg | grep -iE "report rate|esport|tran_report_rate"
```

- `fc-tp-esports`（属性 + 电竞 proc 读写，推荐）
- `fc-tp-driver` / `fc-tp-touch`；proc 权限 → `fc-tp-selinux`

## 故障分流

| 现象 | 排查 |
|------|------|
| 采样率不切换 | `&touch` 缺 `esports-engine`；vendor 缺 `switch-report-support` |
| ioctl 无效 | `is_support_feature(FEATURE_ESPORT)` 为 0（DTS 未配/非法） |
| 仅动态报点率无效 | 缺 `dynamic-report-rate-support` |
| 有日志无手感 | `fts_esport_feature_switch` / 固件 |
| 触摸异常 | `tp-adapt-bringup` |

## 关联

`tp-adapt-bringup` · `tool-opengrok` · `fc-tp-selinux`
