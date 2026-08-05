---
name: base_kernel_standby_q
description: 高通平台 Kernel 待机：递归合并 kernellogcat-log，统计 Pending Wakeup Sources Top3。
---

## 适用场景

面向 **高通（QCOM）** 平台 `kernellogcat-log.*` 日志，统计休眠阻塞唤醒源：

- 递归搜索 `kernellogcat-log.YYYYMMDD-HHMMSS(.xx)`，按**文件名时间**排序后合并
- 仅搜索关键字 **`Pending Wakeup Sources:`**
- 关键字后的文本即为唤醒源（支持 `[timerfd]`、`IPA_CLIENT_*`、`rmnet_ctl` 等）
- 统计并输出 **Top3** 唤醒源

> 高通日志**不含** MTK 的 `suspend wake up by` / `R12_*` / `System LPM is blocked by`；不输出 `AP_suspend_failed`、`26M_LPM_*` 等字段。  
> MTK 平台请使用 `base/kernel_standby`。

## 日志输入

| 类型 | 文件名模式 | 说明 |
|------|-----------|------|
| **kernel** | `kernellogcat-log.YYYYMMDD-HHMMSS(.xx)` | 主输入；多文件按文件名时间升序合并 |

示例：`kernellogcat-log.20260612-071957` → `2026-06-12 07:19:57`

示例行：

```text
06-12 07:10:27.692273  1000  4120  4120 I PM      : PM: Pending Wakeup Sources: IPA_CLIENT_APPS_LAN_CONS
06-12 07:11:32.120883  1000  4120  4120 I PM      : PM: Pending Wakeup Sources: IPA_CLIENT_APPS_WAN_LOW_LAT_CONS rmnet_ipa%d rmnet_ctl
```

## 执行方式

```bash
python scripts/wakeup_source_q.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 日志目录（递归查找 `kernellogcat-log.*`） | 与 `--file`、`--stdin` 互斥 |
| `--file FILE` | 单个日志文件 | 与 `-d`、`--stdin` 互斥 |
| `--stdin` | 从标准输入读取 | 与 `-d`、`--file` 互斥 |
| `-t START END`, `--time START END` | 时间窗（`YYYY-MM-DD HH:MM:SS`） | 可选；可只给 START 或 END |
| `--format {text,json}` | 输出格式 | 可选，默认 `text` |
| `--field FIELD` | JSON 仅输出 summary 字段 | 仅 `--format json` |

`--field` 可选：`pending_wakeup_sources_top3`、`pending_wakeup_hit_count`

## 使用示例

```bash
# 分析 mobilelog 目录
python scripts/wakeup_source_q.py -d "E:/jiradata/.../mobilelog"

# 带时间窗
python scripts/wakeup_source_q.py -d "E:/jiradata/.../mobilelog" \
  -t "2026-06-12 07:00:00" "2026-06-12 09:00:00"

# JSON 仅取 Top3
python scripts/wakeup_source_q.py -d "E:/jiradata/.../mobilelog" --format json \
  --field pending_wakeup_sources_top3
```

## 输出说明

### 文本输出

```text
===== Pending Wakeup Sources Top3 =====
1. timerfd: 510 (43.29%)
2. IPA_CLIENT_APPS_LAN_CONS: 136 (11.54%)
3. qcom_rx_wakelock: 96 (8.15%)
total_source_hits=1178
pending_line_hits=830

=== 结构化分析摘要(供下游SKILL输入) ===
[SUMMARY]
pending_wakeup_sources_top3=Top3=timerfd(510), IPA_CLIENT_APPS_LAN_CONS(136), qcom_rx_wakelock(96); total=1178
pending_wakeup_hit_count=830
```

### JSON 摘要字段

| 字段 | 说明 |
|------|------|
| `pending_wakeup_sources_top3` | Top3 字符串 |
| `pending_wakeup_hit_count` | 命中 `Pending Wakeup Sources:` 的行数 |
| `stats.pending_wakeup_sources.count` | 各唤醒源完整计数 |

## 注意事项

- 目录下无 `kernellogcat-log.*` 时脚本报错退出。
- 文件排序依据文件名时间戳，不是修改时间。
- 同一行多个唤醒源（如 `[timerfd] [timerfd]` 或 `A B C`）分别计数。
- `PM:` 与 `Abort:` 前缀行只要含 `Pending Wakeup Sources:` 均纳入统计。
