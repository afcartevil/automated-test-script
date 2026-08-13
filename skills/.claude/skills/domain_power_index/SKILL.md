---
name: domain_power_index
description: 功耗领域技能索引：base 原子能力与 flow 场景分析。包内分流见 analysis/SKILL.md。
---

# 功耗领域（power）

> 包内分流：[analysis/SKILL.md](../../SKILL.md)；仓库入口 [tran_sw_skillhub/SKILL.md](../../../SKILL.md)。

## base（原子能力）

| 目录 | name |
|------|------|
| `base/precondition_check` | `base_precondition_check` |
| `base/jira_testcase_parse` | `base_jira_testcase_parse` |
| `base/modem_data` | `base_modem_data` |
| `base/wifi_data` | `base_wifi_data` |
| `base/cpuinfo` | `base_cpuinfo` |
| `base/cpuinfo_q` | `base_cpuinfo_q` |
| `base/networkinfo` | `base_networkinfo` |
| `base/batteryinfo` | `base_batteryinfo` |
| `base/standby_pt5` | `base_standby_pt5` |
| `base/kernel_standby` | `base_kernel_standby` |
| `base/kernel_standby_q` | `base_kernel_standby_q` |
| `base/bugreport_standby` | `base_bugreport_standby` |

## flow（场景流程，执行时打开对应 SKILL.md）

| 目录 | name | 场景 |
|------|------|------|
| `flow/standby_long` | `flow_power_standby_long` | 长待机 |
| `flow/standby_long_dou` | `flow_power_standby_long_dou` | DOU 长待机（拆机 pt5；默认 WiFi / 25mA） |
| `flow/standby_short` | `flow_power_standby_short` | 短待机 |
| `flow/dou` | `flow_power_dou` | DOU 对比 |
| `flow/game` | `flow_power_game` | 游戏功耗澄清 |

## 工作区

`temp/<DATE>/<KEY|session>/` 下 `downloads/`、`converted/`、`analysis/`。
