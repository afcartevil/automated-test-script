---
name: base_batteryinfo
description: 电池信息
---
## 适用场景
使用 `batteryinfo.py` 计算电池信息，支持以下功能：

- 统计电池信息
- 支持按时间范围筛选
- 支持手动指定电池容量
- 自动从日志中提取电池容量默认值
- 电量去重，只记录有变化的值
- 计算平均电流
- 生成结构化分析摘要（供下游SKILL输入）

## 前置条件

- 无额外 Python 三方库依赖
- `-d/--directory` 指向的目录中，除了 `events_log_*` 外，还应能找到已转换的 `*_linli_666.txt` 或 `merged_kernel_log`
- 如果目录里只有原始 `kernel_log_*`，必须先执行 `base_mtk_kernellog_convert`
- Windows 下若原始解压路径过深，先执行 `base_prepare_workspace`，再对 `temp/<DATE>/<KEY>/converted/APLog/` 运行

## 执行方式

在技能目录下执行（或使用仓库内脚本的绝对路径）：

```bash
python batteryinfo.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 指定日志路径（包含 `events_log_*`，且可递归找到 `*_linli_666.txt` 或 `merged_kernel_log`） | 必须指定 |
| `--start START_TIME` | 指定待机开始时间（格式：YYYY-MM-DD HH:MM:SS） | 可选 |
| `--end END_TIME` | 指定待机结束时间（格式：YYYY-MM-DD HH:MM:SS） | 可选 |
| `-c CAPACITY`, `--capacity CAPACITY` | 指定电池容量(mAh) | 可选，若未指定，则自动从日志中提取fc信息作为默认值 |
| `-s STANDBY`, `--standby-threshold STANDBY` | 指定待机电流阈值(mA)，同时作为PASS/FAIL平均电流阈值 | 可选，默认25 |
| `-H HARDWARE`, `--hardware-threshold HARDWARE` | 指定硬件放电异常阈值(mA) | 可选，默认3000 |
| `--format {text,json}` | `json` 时输出 `analyze_battery_data` **原生分段结构**（`META`/`THRESHOLD`/…）；各领域 flow 自行解读 | 可选，默认 text |

## 使用示例

```bash
# 仅指定日志路径，使用自动提取的电池容量
python batteryinfo.py -d E:\path\to\folder

# 手动指定电池容量为5000mAh
python batteryinfo.py -d E:\path\to\folder -c 5000

# 指定开始时间和结束时间，统计该时间范围内的信息
python batteryinfo.py -d E:\path\to\folder --start "2026-03-04 17:42:14" --end "2026-03-05 09:09:57"

# 仅指定开始时间，统计开始时间之后的信息
python batteryinfo.py -d E:\path\to\folder --start "2026-03-04 17:42:14"

# 仅指定结束时间，统计结束时间之前的信息
python batteryinfo.py -d E:\path\to\folder --end "2026-03-05 09:09:57"

# 指定自定义阈值参数：-s 30 表示待机电流阈值为30mA，同时作为PASS/FAIL平均电流阈值，-h 3000 表示硬件放电异常阈值为3000mA
python batteryinfo.py -d E:\path\to\folder -s 30 -h 3000
```

## 输出说明

执行脚本后，会输出详细电池信息和结构化分析摘要：

### 详细电池信息

```
使用电池容量: 5000 mAh

===== 详细电池信息 =====
--------------------------------------------------------------------------------------------------------------------------------------
开始时间                  结束时间                  电量(%)  电压(V)   温度(℃)  瞬时电流(mA)    平均电流(mA)     充电状态
--------------------------------------------------------------------------------------------------------------------------------------
2026-03-11 19:02:29.000   2026-03-11 19:02:29.000  73      4.180V   32        -110           0.000           无
2026-03-11 19:02:29.000   2026-03-11 19:14:52.000  74      4.210V   32        500           166.667         a
2026-03-11 19:14:52.000   2026-03-11 19:22:16.000  77      4.240V   31        420           138.889         u
2026-03-11 19:22:16.000   2026-03-11 19:34:56.000  79      4.260V   32        80            83.333          无
--------------------------------------------------------------------------------------------------------------------------------------
```

**输出字段说明**：
- 开始时间：第一条记录使用自身时间，后续记录使用上一次电量记录的时间（格式：YYYY-MM-DD HH:MM:SS.f）
- 结束时间：当前电量记录的时间（格式：YYYY-MM-DD HH:MM:SS.f）
- 电量(%)：电池电量百分比（只显示电量变化的记录）
- 电压(V)：电池电压（伏特，保留3位小数）
- 温度(℃)：电池温度
- 瞬时电流(mA)：瞬时电流值
- 平均电流(mA)：根据电量变化和时间差计算的区间平均电流（第一条记录为0）
- 充电状态：充电状态标识

**输出规则**：
- 如果用户指定了开始/结束时间，则只显示该时间范围内的记录
- 从第一条电量记录开始显示（或用户指定的开始时间）
- 只记录电量有变化的记录，相同电量的记录会被合并

### 结构化分析摘要（供下游SKILL输入）

```
=== 结构化分析摘要(供下游SKILL输入) ===
[META]
analysis_start=2026-03-11 19:02:29 (电量: 73%)
analysis_end=2026-03-11 19:34:56 (电量: 79%)
analysis_duration_h=0.54

[THRESHOLD]
standby_current_threshold_ma=25
hardware_discharge_abnormal_threshold_ma=3000

[JUMP_CHECK]
has_soc_or_voltage_jump=true
jump_count=1
jump_1_time=2026-03-11 19:14:52
jump_1_detail=SOC 73->74 (变化1); VOLT 4.180V->4.210V; AVG_CURRENT 0.0->166.7;

[HARDWARE_ABNORMAL]
has_discharge_over_3a=false
abnormal_count=0
abnormal_detail=none

[POWER_SEGMENT]
pass_duration_h=0.3
pass_avg_current_ma=83.33
fail_duration_h=0.24
fail_avg_current_ma=152.78
min_power_window_start=2026-03-11 19:22:16
min_power_window_end=2026-03-11 19:34:56
min_power_window_avg_current_ma=83.33
max_power_window_start=2026-03-11 19:02:29
max_power_window_end=2026-03-11 19:14:52
max_power_window_avg_current_ma=166.67
```

**结构化摘要字段说明**：

| 字段 | 说明 |
|---|---|
| `analysis_start` | 待机开始时间（如果有充电状态记录，使用最后一条充电结束后的第一条记录；否则使用去重后数据的第一条记录，并显示对应电量） |
| `analysis_end` | 待机结束时间（去重后数据的最后一条电量信息对应的时间，并显示对应电量） |
| `analysis_duration_h` | 待机持续时间（小时） |
| `standby_current_threshold_ma` | 待机电流阈值（mA），同时作为PASS/FAIL平均电流阈值 |
| `hardware_discharge_abnormal_threshold_ma` | 硬件放电异常阈值（mA） |
| `has_soc_or_voltage_jump` | 是否有电量/电压跳变 |
| `jump_count` | 跳变次数 |
| `jump_N_time` | 第N次跳变的时间 |
| `jump_N_detail` | 第N次跳变详情（SOC、VOLT、AVG_CURRENT、CHG_STATE变化） |
| `has_discharge_over_3a` | 瞬时电流是否超过3A |
| `abnormal_count` | 异常次数 |
| `abnormal_detail` | 异常详情 |
| `pass_duration_h` | PASS持续总时间（平均电流≤standby_current_threshold_ma） |
| `pass_avg_current_ma` | PASS加权平均电流阈值|
| `fail_duration_h` | FAIL持续总时间（平均电流>standby_current_threshold_ma） |
| `fail_avg_current_ma` | FAIL加权平均电流阈值|
| `min_power_window_start/end` | 平均功耗最小窗口的开始/结束时间（排除 `>hardware_discharge_abnormal_threshold_ma` 的尖峰段） |
| `min_power_window_avg_current_ma` | 最小平均电流值 |
| `max_power_window_start/end` | 平均功耗最大窗口的开始/结束时间（排除 `>hardware_discharge_abnormal_threshold_ma` 的尖峰段） |
| `max_power_window_avg_current_ma` | 最大平均电流值 |

**平均电流计算公式**：
```
平均电流(mA) = 电池容量(mAh) × (上一次电量 - 当前电量) / 100 / 时间差(小时)
```

**充电状态说明**：
- `u`：USB充电
- `a`：AC充电
- `无`：没有充电

**跳变检测规则**：
满足以下任一条件视为跳变：
1. 电量变化≥2（即电量变化的绝对值≥2）
2. 电压变化>0.2V（即电压变化的绝对值>0.2V）
3. 平均电流变化≥2000mA（即平均电流变化的绝对值≥2000mA）
