---
name: base_kernel_standby
description: Kernel 待机总入口：统一分析 suspend 失败、R12 唤醒、26M/LPM 异常。
---

## 适用场景

面向 AP/kernel 日志（如含 `linli_666` 的合并日志），统一处理 SOP「系统休眠唤醒状态」相关证据：
- `PM: suspend entry`、`Pending Wakeup Sources`、`aborting suspend`、`active wakeup source:`
- `suspend wake up by`（兼容旧平台 `[SPM] wake up by`）
- `R12_*`、`26M_off_pct`、`System LPM is blocked by`、`CCIF_MD wakeup source`

## 执行方式（建议）

```bash
python scripts/wakeup_source.py [options]
```

## 子能力约定（当前方案）

- `kernel-block`：聚焦 suspend 失败链路（谁导致睡不下去）
- `wakeup`：聚焦唤醒源与 R12 统计
- `full`：综合输出（默认）

> 说明：即使底层脚本目前仍是单入口，也应按上述语义组织输出，确保与 domain 编排对接稳定。

## 参数说明（兼容现有脚本）

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 指定日志路径（APLog 目录，含 `kernel_log_*`） | 必须指定 |
| `--file FILE` | 指定单个日志文件路径（将直接读取该文件内容） | 与 `-d/--directory`、`--stdin` 互斥，三选一 |
| `--stdin` | 从标准输入读取日志内容（适合管道 / 上层编排把合并日志直接喂入） | 与 `-d/--directory`、`--file` 互斥，三选一 |
| `-t START END`, `--time START END` | 指定开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS） | 可选，若只指定一个时间，则视为开始时间；若第一个时间为空，则视为只指定结束时间 |
| `--format {text,json}` | 输出格式：`text`（默认）或 `json` | 可选 |
| `--field FIELD` | JSON 输出时仅选择 `summary` 中的字段，可重复 | 仅在 `--format json` 生效；省略则输出全量（summary/stats/evidence/meta） |

## 使用示例

```bash
# 1) 推荐：分析 APLog 解包目录（兼容旧用法）
python scripts/wakeup_source.py -d "D:/aplog_dir"

# 2) 带时间范围筛选
python scripts/wakeup_source.py -d "D:/aplog_dir" -t "2026-05-08 10:00:00" "2026-05-08 12:00:00"

# 3) 直接分析单个日志文件
python scripts/wakeup_source.py --file "D:/logs/kernel_log_113__2026_0305_085522_linli_666.txt"
python scripts/wakeup_source.py --file "D:/logs/sys_log_304__2026_0426_141115.txt"

# 4) 结构化 JSON 输出（全量：summary/stats/evidence/meta）
python scripts/wakeup_source.py -d "D:/aplog_dir" --format json

# 5) flow 高低功耗窗对比：仅取 summary 关键字段
python scripts/wakeup_source.py -d "D:/aplog_dir" -t "2026-05-08 10:00:00" "2026-05-08 12:00:00" --format json \
  --field AP_suspend_failed --field frequent_wakeup --field 26M_LPM_abnormal --field 26M_LPM_reason
```

## 输出说明

执行脚本后，会输出详细唤醒信息和结构化分析摘要：

### 详细唤醒信息（灭屏->亮屏分段）

生成一张 **“灭屏->亮屏”分段表**，用于定位“哪一段被灭屏/为什么灭屏/该段是否休眠异常”。

```
===== 详细唤醒信息 =====
--------------------------------------------------------------------------------------------------------------------------------------
开始时间                  结束时间                  屏幕  时长(s)    电源键    休眠状态     频繁唤醒      26M/LPM异常     26M/LPM异常原因
--------------------------------------------------------------------------------------------------------------------------------------
2026-03-11 19:14:52.000   2026-03-11 19:22:16.000  ON     444       Yes        No           No         No            No
2026-03-11 19:22:16.000   2026-03-12 09:34:56.000  OFF  43960       Yes        Yes          Yes        No            con
2026-03-12 09:34:56.000   2026-03-12 09:44:56.000  ON     600       No         No           No         Yes           
--------------------------------------------------------------------------------------------------------------------------------------
```

**字段口径**：

- **灭屏开始时间 / 亮屏时间**：从**kernel_log（kernel log）**日志里解析 `tc_screen_notifier_callback: screen off`（灭屏）与 `tc_screen_notifier_callback: screen on`（亮屏）相关行的时间戳后配对得到。
- **时长(s)**：亮屏时间 - 灭屏时间。
- **AP suspend**：该片段是否存在“睡不下去”的证据（片段内出现 suspend fail 且片段内未出现 suspend wake up by）。
- **频繁唤醒**：该片段内 `suspend wake up by` 计数达到阈值（当前实现为 >=20）。
- **26M/LPM 异常/原因**：该片段内出现 `System LPM is blocked by` 则判定异常，并输出原因；否则 `No`。
- **电源键**：该片段内电源键证据行计数，用于确认是否按过电源键。
  - `power_key`：**sys_log（Android log）** 片段内命中 `POWER_BUTTON` / `WAKE_REASON_POWER_BUTTON` / `android.policy:POWER` 证据（优先级最高）
  - `notification`：片段内唤醒源含网络/闹钟/Modem 等关键词（粗判为通知/系统事件）
  - `unknown`：无法归类
**输出规则**：
- 从第二条信息记录开始显示，第一条记录作为起始时间
- 只记录信息有变化的记录，相同的记录会被合并


## 结构化分析摘要（供下游SKILL输入）

当下游需要稳定解析（而不是依赖自然语言/多行统计输出）时，建议消费以下“分段 + key=value”的结构化摘要。

> 说明：脚本已支持 `--format json` 输出结构化结果（更适合程序消费）；本段提供一个 text 侧的等价协议，便于统一编排与兼容旧链路。

```text
=== 结构化分析摘要(供下游SKILL输入) ===
[META]
analysis_start=2026-05-01 18:10:38
analysis_end=2026-05-02 08:10:38
analysis_duration_h=1

[THRESHOLD]
standby_26m_off_pct_threshold=70
hardware_discharge_abnormal_threshold_ma=3000

[SUMMARY]
AP_suspend_failed=<Yes/No>
frequent_wakeup=<Yes/No>
frequent_wakeup_reason=<No or Top3=...; total=...>
26M_LPM_abnormal=<Yes/No>
26M_LPM_reason=<No or Top3=...; total=...>
screen_wakeup=<Yes/No>
screen_wakeup_type=<No or power_key/notification/unknown>
screen_wakeup_detail=<No or Top3=...; total=...>
power_button_evidence_count=<int>

[STATS]
wakeup_count=<int>
26M_off_pct_avg=<float% or empty>
top_wakeup_sources=<name(count,ratio%), ... or No>
ccif_md_top=<name(count), ... or No>
system_lpm_blocked_top=<name(count), ... or No>
```

**字段说明与来源映射**：

- **`[META]`**
  - `analysis_base_year`：用于解析无年份时间戳的基准年份（来自脚本 `meta.base_year`）
  - `analysis_start / analysis_end`：若命令使用 `-t/--time` 指定，则为该时间窗；否则可为空（来自 `meta.start_time / meta.end_time`）
  - `analysis_duration_h`：根据唤醒样本时间跨度估算（来自 `stats.duration_hours`；无数据可为空）

- **`[SUMMARY]`**
  - 对应脚本 JSON 的 `summary.*`：
    - `AP_suspend_failed`（`Yes` = suspend 失败）
    - `frequent_wakeup`
    - `frequent_wakeup_reason`
    - `26M_LPM_abnormal` / `26M_LPM_reason`
      - `26M_LPM_reason` 中的 `Top3=...; total=...` 来自 `System LPM is blocked by` 的模块计数汇总。
      - 若下游需要确定 **26M/LPM 主要阻塞模块**，默认按阻塞次数排序，取计数最高的模块作为主模块；其余模块保留为陪同模块。
      - 若多个模块计数接近或并列，仍需输出 Top3 计数，避免过度简化为单模块结论。
    - `screen_wakeup`
    - `screen_wakeup_type`：亮屏触发来源粗分类（优先判 `power_key`；否则按网络/闹钟/Modem 等关键词判 `notification`；其余为 `unknown`）
    - `screen_wakeup_detail`：用于佐证的 Top3 唤醒源摘要（便于下游落库/展示）
    - `power_button_evidence_count`：**来源于 sys_log（Android log），不来自 kernel_log**。时间窗内命中 `POWER_BUTTON` / `WAKE_REASON_POWER_BUTTON` / `android.policy:POWER` 的行数（用于确认是否按过电源键）。若仅提供 kernel_log，可能为 0（属预期）。

- **`[STATS]`**
  - `wakeup_count`：唤醒条目数量（来自 `stats.wakeup_count`）
  - `26M_off_pct_avg`：26M 休眠比平均值（来自 `stats.pct_stats.avg`；无样本可为空）
  - `top_wakeup_sources`：唤醒源 TopN（来自 `stats.wakeup_sources.count`）
  - `ccif_md_top`：`CCIF_MD wakeup source` TopN（来自 `stats.ccif_md_wakeup_source`）
  - `system_lpm_blocked_top`：`System LPM is blocked by` TopN（来自 `stats.system_lpm_blocked.count`）
    - 下游若要落“26M/LPM 异常原因”，优先消费该字段并按计数确定主阻塞模块，例如 `scp(838) > md(664) > conn(33)` 时主模块写 `scp`。


## 注意事项

- 若目录下无 `kernel_log_*` 且无合并后的 `linli_666` 日志，先调用 `base_mtk_kernellog_convert` 或确认解包路径。
- 输出中需区分：R12 唤醒（kernel）与 partial wakelock（bugreport）。
 