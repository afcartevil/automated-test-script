---
name: base_cpuinfo_q
description: 高通平台 CPU 负载分析。
---

## 适用场景

面向 **高通（QCOM）** 平台 `kernellogcat-log.*` 日志，解析内核 CPU 负载并检测异常应用：

- 递归搜索 `kernellogcat-log.YYYYMMDD-HHMMSS(.xx)`，按**文件名时间**排序后合并分析
- 搜索关键字 **`: [K]      `**（`[K]` 后含 **6 个空格**，含冒号与空格）
- 解析负载行：`%` 前数字为负载，其后第一个数字为 **PID**，再后为包名/comm（如 `facebook.katana`）
- 按包名分组统计；自适应异常应用检测（与 `cpuinfo.py` 相同阈值）
- 生成报告到 `temp/.../analysis/`（默认 `cpuinfo_q_report.txt`）

> MTK 平台请使用 `base/cpuinfo`（`cpuinfo.py` + `linli_666`）。

## 日志输入

| 类型 | 文件名模式 | 说明 |
|------|-----------|------|
| **kernel** | `kernellogcat-log.YYYYMMDD-HHMMSS(.xx)` | 唯一必需输入；多文件按文件名时间升序合并 |

示例文件名：`kernellogcat-log.20260612-071957` → `2026-06-12 07:19:57`

示例负载行：

```text
07-22 23:48:20.776445  root 16037 16037 I         : [K]       89%        23850             .lark.transsion           8986709259(ns)                 650
```

| 字段 | 含义 |
|------|------|
| `07-22 23:48:20` | 时间（年份取自首个 kernellogcat 文件名） |
| `89%` | 负载 |
| `23850` | **进程 PID** |
| `.lark.transsion` / `facebook.katana` | 包名（comm） |

## 前置条件

无特殊依赖。

## 执行方式

```bash
python scripts/cpuinfo_q.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 日志目录（含 `kernellogcat-log.*`） | 必须指定 |
| `-t START END`, `--time START END` | 时间窗（`YYYY-MM-DD HH:MM:SS`） | 可选；可只给 START 或 END |
| `-o DIR`, `--output-dir DIR` | 报告输出目录 | 可选 |
| `--report-name NAME` | 报告文件名，默认 `cpuinfo_q_report.txt` | 可选 |

## 使用示例

```bash
# 分析 mobilelog 目录
python scripts/cpuinfo_q.py -d "E:/jiradata/.../mobilelog"

# 指定时间窗（如 pt5 高功耗子窗）
python scripts/cpuinfo_q.py -d "E:/jiradata/.../mobilelog" \
  -t "2026-06-26 00:55:24" "2026-06-26 01:05:28" \
  -o "<repo>/temp/<DATE>/<KEY>/analysis" --report-name cpu_max_q_report.txt
```

## 输出说明

### 终端输出

有异常应用时打印 `Anomaly Applications Detection` 摘要；无异常时：

```text
No anomaly applications detected (All apps avg load <= 10% or burst too short)
```

### 报告文件结构（对齐 cpuinfo.py）

- `=== Cpus Usage ===`
- `=== Package Statistics ===`（按打印次数 / 平均负载排序）
- `=== Package: <name> ===`（时间、负载、PID 明细）
- `=== Anomaly Applications Detection ===`

### 输出目录约定

- 未指定 `-o` 时：`<repo>/temp/<当天日期>/<输入目录名>/analysis/`
- 建议与 flow 工作区对齐：`temp/<DATE>/<KEY>/analysis/`

## 异常应用检测标准

与 `cpuinfo.py` 自适应口径一致：

| 条件 | 阈值 |
|------|------|
| 常规 | 10min 窗内平均负载 **>10%**，持续 **>10min**，打印密度 ≥1 次/5min |
| 突发高负载 | 平均 **>50%** 且持续 **>3min** |
| 极端负载 | 平均 **>100%** 且持续 **>1min** |

连续异常时间段会自动合并；含 `binder` 的包名会被过滤。

## 注意事项

- 目录下无 `kernellogcat-log.*` 时脚本退出并报错。
- 文件排序依据文件名时间戳，不是修改时间。
- 只统计负载 **>0%** 的采样点。
- 短/长待机 flow 高低功耗窗分析：对 `max_power_time_*` / `min_power_time_*` 分别调用并传 `-t`。
