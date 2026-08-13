---
name: base_cpuinfo
description: CPU负载信息分析
---

## 适用场景
使用 `cpuinfo.py` 分析CPU负载信息，支持以下功能：

- 搜索包含 linli_666 文件的日志
- 搜索关键字 "[K] " 获取CPU相关信息
- 提取 Cpus Usage 信息（CPU核心使用率）
- 提取线程负载信息（包含 "ns" 关键字的行）
- 按包名分组统计线程负载信息
- 检测异常应用（10分钟内平均负载超过10%）
- 合并连续的异常时间段
- 生成详细报告文件（默认写入 `temp/.../analysis/`，不写回 skill 目录）

## 前置条件

无特殊依赖

## 执行方式

在技能目录下执行（或使用仓库内脚本的绝对路径）：

```bash
python cpuinfo.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 指定日志路径（包含linli_666文件的文件夹路径） | 必须指定 |
| `-t START END`, `--time START END` | 指定开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS） | 可选，若只指定一个时间，则视为开始时间；若第一个时间为空，则视为只指定结束时间 |
| `-o DIR`, `--output-dir DIR` | 指定报告输出目录，建议传 `temp/<DATE>/<JIRA_KEY>/analysis/` | 可选 |
| `--report-name NAME` | 指定报告文件名，默认 `cpuinfo_report.txt` | 可选 |

## 使用示例

```bash
# 仅指定日志路径，统计所有信息
python cpuinfo.py -d E:\path\to\folder

# 指定开始时间和结束时间，统计该时间范围内的信息
python cpuinfo.py -d E:\path\to\folder -t "2026-05-11 19:00:00" "2026-05-12 09:00:00"

# 显式指定输出目录到 temp 工作区
python cpuinfo.py -d E:\path\to\folder -t "2026-05-11 19:00:00" "2026-05-12 09:00:00" -o <repo>\temp\<DATE>\<JIRA_KEY>\analysis --report-name cpu_max_report.txt

# 仅指定开始时间，统计开始时间之后的信息
python cpuinfo.py -d E:\path\to\folder -t "2026-05-11 19:00:00"

# 仅指定结束时间，统计结束时间之前的信息
python cpuinfo.py -d E:\path\to\folder -t "" "2026-05-12 09:00:00"

# 在技能目录下执行
cd scripts
python cpuinfo.py -d E:\jiradata\...\mobilelog\APLog_xxx -t "2026-05-11 19:00:00" "2026-05-12 09:00:00"
```

## 输出说明

执行脚本后，详细报告默认写入 `temp/<DATE>/<JIRA_KEY>/analysis/<report-name>`；若显式传 `-o/--output-dir`，则写到指定目录。终端仍只输出异常应用检测结果，并在结束时打印最终报告路径。

### 输出目录约定

- 推荐与 `base_download` 保持同一工作区口径：
  - 下载：`temp/<DATE>/<JIRA_KEY>/downloads/`
  - CPU 报告：`temp/<DATE>/<JIRA_KEY>/analysis/`
- 当 `-d/--directory` 已指向 `temp/<DATE>/<JIRA_KEY>/converted/...` 下的日志目录时，脚本会自动把报告落到对应 `analysis/`
- 当输入目录不在 `temp/` 工作区下时，脚本会回退到 `temp/<DATE>/<输入目录名>/analysis/`

### 终端输出：Anomaly Applications Detection（异常应用检测）
检测异常应用（10分钟内平均负载超过10%），格式为：
```
==========================================================================================
Detected anomaly applications (Avg Load > 10% over 10 minutes):
==========================================================================================
Package: com.google.android.gms   PID: 5678  Total anomaly duration: 25.5min

Duration     Time Range                     Print Count  Avg Load   Max Load   Min Load
------------------------------------------------------------------------------------------
10.5min      2026-03-11 19:05:21 ~ 19:15:51  21          35.67%     45.00%     28.00%
15.0min      2026-03-11 19:20:00 ~ 19:35:00  30          38.50%     50.00%     30.00%

==========================================================================================
```

无异常应用时，终端输出：
```
No anomaly applications detected (All apps avg load <= 10% within 10 minutes)
```

### 报告文件内容（如 `cpuinfo_report.txt`）
报告文件包含完整的分析结果：
- Cpus Usage 信息
- Package Statistics（按包名统计）
- 每个包的详细信息
- Anomaly Applications Detection（异常应用检测）

## 异常应用检测标准

脚本使用以下标准检测异常应用：

| 标准 | 阈值 | 说明 |
|------|------|------|
| **时间窗口** | 10分钟 | 检测10分钟内的平均负载 |
| **平均负载阈值** | >10% | 平均负载超过10%视为异常 |
| **打印密度** | ≥1次/5分钟 | 每5分钟至少有一次打印 |
| **持续时间** | >10分钟 | 持续时间超过10分钟 |

## 输出字段说明

### Package Statistics 字段
- **Package**: 包名
- **Load Print Count**: 负载打印次数
- **Avg Load**: 平均负载（百分比）

### Anomaly Applications 字段
- **Duration**: 异常持续时间（分钟）
- **Time Range**: 时间范围（开始时间 ~ 结束时间）
- **Print Count**: 打印次数
- **Avg Load**: 平均负载（百分比）
- **Max Load**: 最高负载（百分比）
- **Min Load**: 最低负载（百分比）

## 注意事项

- 脚本会递归搜索指定文件夹及其子文件夹中包含 "linli_666" 的文件
- 脚本会自动按文件修改时间排序
- 终端仅输出异常应用检测结果，完整分析内容保存在 `temp/.../analysis/` 下的报告文件
- 异常应用检测会自动合并连续的异常时间段
- 只统计负载不为0的数据点（筛选掉负载为0的项）