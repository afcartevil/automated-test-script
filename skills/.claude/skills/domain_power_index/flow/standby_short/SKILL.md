---
name: flow_power_standby_short
description: 分析短待机（10min/1h 灭屏）功耗问题，输出明确责任归因（系统/模块/应用）与下一步动作。适用于拆机短待机超标、频繁唤醒、26M/LPM异常、持锁/数传问题定位。
---

## 适用场景

用于 **短待机** 功耗分析（仅两种规格）：

- **10 min 灭屏待机**（日志有效区间：**8.5~11.5 min**，目标 10 min ±1.5 min）
- **1 h 灭屏待机**（日志有效区间：**55~65 min**，目标 60 min ±5 min）

典型问题：短待机超标、频繁唤醒、26M/LPM 异常、持锁、后台数传。

## 输入

- **工作区**：`temp/<DATE>/<KEY>/`（编排层已准备好 `converted/`、`downloads/`）
- **`platform`**：`MTK` 或 `QCOM`（高通）；**省略时默认 `MTK`**
- **`standby_type`**：`WIFI` 或 `DATA`（见下节；**仅影响**网络/数传步骤，**不改变**短待机电流等级阈值）
- **`log_path`**：优先 `converted/APLog/`（MTK）；高通优先 `downloads/.../mobilelog/` 或 `converted/` 下含 `kernellogcat-log.*` 的目录
- **`Stdby_Curr`**：短待机实测平均电流（mA），优先由 **`base_standby_pt5`** 解析；备选 JIRA 描述 / 手动录入（见步骤 1）

编排层 `base_jirainfo` 读到的 `summary` / `description` 供本 flow 推断 `standby_type`；「10min/1h」字样仅作**人工复核**，**不替代**日志自动判定 `standby_duration_spec`。

## platform（本 flow 专属）

| `platform` | 说明 | 步骤 2 规格时长 | 步骤 3 CPU | 步骤 4 kernel |
|---|---|---|---|---|
| **省略 / `MTK`** | 默认；MediaTek APLog + `linli_666` | `base_kernel_standby` → `screen_segments` | `base_cpuinfo` | `base_kernel_standby` |
| **`QCOM` / `高通`** | 高通 `kernellogcat-log.*` | pt5 `capture_time_*` 映射 §2 | `base_cpuinfo_q` | `base_kernel_standby_q` |

高通 skill 路径：

- Kernel：[base_kernel_standby_q/SKILL.md](../../base/kernel_standby_q/SKILL.md) → `scripts/wakeup_source_q.py`
- CPU：[base_cpuinfo_q/SKILL.md](../../base/cpuinfo_q/SKILL.md) → `scripts/cpuinfo_q.py`

```bash
# 编排层可在工作区 jira_info.json 增加 platform 字段，或由 Agent 显式传入
# platform 省略 → MTK
```

## standby_type（本 flow 专属）

读 JIRA 字段后在本 flow 内推断（实现：`scripts/jira_triage.py`，**仅取** `standby_type`，**不使用** `threshold_ma`）：

| 条件（summary/description） | `standby_type` |
|---|---|
| `Mobile data ON` + `WiFi OFF` / 移动数据开 + WiFi关 | `DATA` |
| `WiFi ON` | `WIFI` |
| `SIM Complex Standby` 等未写明网络开关 | `DATA` |

`jira_triage.py` 示例（**推荐**从工作区读 `jira_info.json`，勿把长 description 塞进命令行）：

```bash
python scripts/jira_triage.py --workspace temp/<DATE>/<KEY>
# → 使用 standby_type；短待机电流等级见 §1，与 standby_type 无关
```

## 前置建议

**MTK（`platform` 省略或 `MTK`）**

- `APLog` 先执行 `base_mtk_kernellog_convert`，确保已生成 `*_linli_666.txt`
- Windows 深路径日志包须先由编排调用 `base_prepare_workspace`，使用 `converted/APLog/`、`converted/bugreports/`、`converted/NTLog/`

**高通（`platform=QCOM` / `高通`）**

- 日志目录含 `mobilelog/kernellogcat-log.*`（及可选 `systemlogcat-log.*`）
- **无需** `base_mtk_kernellog_convert`；`base_prepare_workspace` 仍可用于整理 `downloads/` 深路径
- **`base_kernel_standby_q` 仅统计 Pending Wakeup**，**不**产出灭屏分段 / 电源键；步骤 2 规格判定改用 pt5 `capture_time_*`（见执行流程）

**共用**

- `downloads/` 内应有与用例匹配的 **`.pt5`**（`Stdby_Curr`、高低功耗子窗、**高通规格判定**的主来源）
- `base_standby_pt5` 依赖 Cursor **PT5 MCP** 服务，配置见 [base_standby_pt5/SKILL.md](../../base/standby_pt5/SKILL.md)
- 步骤 8 数传（`base_wifi_data` / `base_modem_data`）的主机工具检测见各 base skill 前置条件，本 flow 不再重复

## 判定标准

### 1 短待机功耗等级（Wi-Fi/DATA 统一，基于 `Stdby_Curr`）

指标：**10 min / 1 h 灭屏待机平均电流** `Stdby_Curr`（与长待机 25/30 mA **不同**）。

| 等级 | 别名 | 判定条件（`Stdby_Curr`，mA） | 处理 |
|---|---|---:|---|
| 达标 | — | **≤ 60** | **提前结束**：输出「功耗满足标准」 |
| Major (C) | C 类 / Major | **60 < Stdby_Curr ≤ 70** | 继续归因 |
| Critical (B) | B 类 / Critical | **70 < Stdby_Curr ≤ 80** | 继续归因 |
| Block (A) | A 类 / Block | **> 80** | 继续归因 |

边界：`=60` 归入达标；`=70` 归入 Major(C)；`=80` 归入 Critical(B)。

### 2 短待机规格自动判定（`standby_duration_spec`）

由日志灭屏时长 `standby_duration_min` 自动映射（**无需手填**）：

| `standby_duration_min` | `standby_duration_spec` | 说明 |
|---|---|---|
| **8.5~11.5 min** | `10min` | 10 min ±1.5 min |
| **55~65 min** | `1h` | 60 min ±5 min |
| 其余 | 无法判定 | flow **提前结束**（输出「待机时长无效需复测」），禁止继续归因 |

> **§2 编号说明**：`§2` 为待机**时长规格**判定；`§2.1` / `§2.2` 为**应用异常辅助阈值**（与 §2 并列，非其子节）；`§2.3`~`§2.4`、`§3` 为证据来源与 26M 规则。  
> **平台差异**：MTK 用 kernel `screen_segments` 量时长；高通当前脚本无分段，用 pt5 `capture_time_*` 时长映射同一张表。

### 2.1 应用异常辅助阈值 — 10 min（`standby_duration_spec = 10min`）

测试窗口约 **10 min**（日志有效区间 **8.5~11.5 min**）。按 **次/10min、时长/10min** 口径定标。定责时**只套用本表**；勿与 §2.2 混用。

| 维度 | 阈值（项目定标） |
|---|---|
| `wakelock` | 测试窗内累计持锁 **≤ 2 min**（灭屏音频除外） |
| `CPU` | 测试窗内平均负载 **≤ 20%**；**突发高负载**：>50% 持续 >3min 或 >100% 持续 >1min 亦视为异常 |
| `network` | 总流量 **< 15 MB / 10min** |
| `network tx`（5s 周期） | IM/SMS/Email **< 10 次/10min**；其他 **< 10 次/10min** |
| `alarm` | 禁止循环 alarm；禁止精确可唤醒 alarm；**< 3 次/10min**；建议心跳 **≥ 5 min** |
| `JobScheduler` | 唤醒间隔 **≥ 30 s** |
| `GPS` | 测试窗内累计 **< 2 min**（导航/轨迹/离线下载等除外） |
| `BT scan` | 测试窗内累计扫描 **< 1 min** |
| `Wi-Fi scan` | 测试窗内累计扫描 **< 1 min** |

### 2.2 应用异常辅助阈值 — 1 h（`standby_duration_spec = 1h`）

测试窗口约 **1 h**（日志有效区间 **55~65 min**）。多数维度与「每小时」口径对齐。定责时**只套用本表**；勿与 §2.1 混用。

| 维度 | 阈值（项目定标） |
|---|---|
| `wakelock` | 测试窗内累计持锁 **≤ 5 min**（灭屏音频除外） |
| `CPU` | **10 min 内**平均负载 **≤ 15%**（可用滑动窗）；**突发高负载**：>50% 持续 >3min 或 >100% 持续 >1min 亦视为异常 |
| `network` | 总流量 **< 50 MB/h** |
| `network tx`（5s 周期） | IM/SMS/Email **< 60 次/h**；其他 **< 30 次/h** |
| `alarm` | 禁止循环/精确可唤醒；**< 12 次/h**；建议心跳 **≥ 5 min** |
| `JobScheduler` | 唤醒间隔 **≥ 30 s** |
| `GPS` | 测试窗内累计 **< 3 min**（导航等除外） |
| `BT scan` | 测试窗内累计扫描 **< 5 min** |
| `Wi-Fi scan` | 测试窗内累计扫描 **< 3 min** 且 **≤ 4 次/h** |

### 2.3 证据来源

| 维度 | MTK（默认） | 高通（`platform=QCOM`） |
|---|---|---|
| `wakelock`、`alarm`、`GPS`、`JobScheduler` 等 | `base_bugreport_standby`（窗口 `sleep_time_*`） | 同左 |
| `CPU` | `base_cpuinfo`（`-t` 高低窗或 `sleep_time_*`） | **`base_cpuinfo_q`**（`-d` 指向 `mobilelog/` 等含 `kernellogcat-log.*` 目录） |
| `network` / `network tx` | NTLog、`base_wifi_data` / `base_modem_data` | 同左 |
| 灭屏分段 / 规格时长 | `base_kernel_standby` → `stats.screen_segments[]` | **不用** kernel 分段；用 pt5 `capture_time_*` 映射 §2 |
| 唤醒阻塞 | `base_kernel_standby`（R12 / suspend） | **`base_kernel_standby_q`** → `pending_wakeup_sources_top3` |
| 26M / R12 / suspend 细节 | `base_kernel_standby` | 高通通常无此类关键字；以 **Pending Wakeup Top3** 替代，不阻塞 |

**选用规则**：根据步骤 2 确认的 `standby_duration_spec`，只套用 **§2.1** 或 **§2.2** 之一。

### 2.4 CPU 异常输出要求

当 `base_cpuinfo`（MTK）或 `base_cpuinfo_q`（高通）检出异常时，最终结论里**必须明确输出具体进程/应用**，不能只写「CPU 高」。

**MTK / 高通**：均按包名（`Package`）输出，见 `base_cpuinfo` / `base_cpuinfo_q`；高通报告内另附原始 `Thread` 列供核对。

**高通 comm 还原**：`cpuinfo_q.py` 将截断 comm（如 `ogle.android.gm`）还原为包名（如 `com.google.android.gm`）；若还原不准，结合 PID 与 bugreport 复核。

最少输出字段：

- 应用/进程名
- PID
- 总异常持续时长
- 至少 1 个关键异常时间段
- 该时间段平均负载
- 最大/最小负载

推荐格式：

```text
CPU异常Top进程：
1. <package/process> (PID <pid>)
   - 总异常时长: <xx.xmin>
   - 关键时间段: <start ~ end>
   - Avg Load: <xx.xx%>
   - Max/Min Load: <xx.xx%> / <xx.xx%>
```

归因要求：

- 若高功耗窗口异常、低功耗窗口无异常：将其作为**差异主进程**写入最终结论。
- 若高低窗口均异常：比较持续时长与平均负载，选择影响更重的进程作为**共性主进程**。
- 若包名被截断，继续结合 bugreport / PID 证据还原；实在无法还原时，也必须保留截断名 + PID + 负载片段。

### 3 26M/LPM 主模块判定（仅 MTK）

> **高通**：本节不适用；改用 `base_kernel_standby_q` 的 **`pending_wakeup_sources_top3`** 作为唤醒阻塞主因依据。

- 当 `26M_LPM_abnormal=Yes` 时，必须结合 `base_kernel_standby.stats.system_lpm_blocked.count` 判定主阻塞模块。
- 规则：按阻塞次数从高到低排序，**次数最高的模块** 作为 `26M/LPM` 主模块。
- 输出要求：
  - `26M_LPM_reason` / 报告「26M/LPM 异常原因」需至少写出主模块；建议同时保留 Top3 计数，例如 `scp(838) > md(664) > conn(33)`。
  - 若主模块与次主模块计数接近，结论中写成「主模块 + 陪同模块」，避免误写成唯一责任。
- 归因口径：
  - 若高低功耗窗口都存在 26M 阻塞，优先比较**共性主模块**。
  - 若仅高功耗窗口出现明显 26M 阻塞增强，优先比较**差异主模块**。

## 归因大类（主因必选一项，按优先级排序）

**MTK**

- AP suspend 失败（系统无法进入休眠）
- 可 suspend，但 26M/LPM 异常（`26M_off_pct` 长期为 0 或偏低）
- 可 suspend，但被频繁唤醒（Wakeup Reasons / R12 主导）
- 应用数传为主（`R12_CONN2AP` / `R12_AP2AP_PEER` + netlog 证据）

**高通（`platform=QCOM`）**

- Pending Wakeup 阻塞为主（`IPA_CLIENT_*` / `timerfd` / `rmnet_*` 等 Top3；主因取 Top1）
- 应用 CPU 负载异常（`base_cpuinfo_q` 异常应用）
- 应用数传为主（`base_modem_data` / bugreport 数传证据 + Pending Wakeup 含 `rmnet_*` / `IPA_CLIENT_APPS_WAN_*` 等）
- ~~测试流程干扰（电源键）~~：**当前 `wakeup_source_q` 不输出** `screen_wakeup` / `power_button_evidence_count`；**勿作主因依据**

## 执行流程（严格顺序）

**进入本 flow 后**：先 `run_python` `scripts/jira_triage.py --workspace <工作区根>`，产出 `standby_type`（**勿用** `threshold_ma`；步骤 7~8 分支**必用**）。确认 **`platform`**（省略=`MTK`）。高低功耗窗 **仅** 来自 `base_standby_pt5`。

0. （前置）下载 → `base_prepare_workspace` → **`base_mtk_kernellog_convert`（仅 MTK，按需）**。

1. 调用 `base_standby_pt5` 解析 `.pt5`（**先于**日志灭屏段解析，无需 `sleep_time_*`）：
   - 在 `downloads/`（或路径参数指定）查找并解析 `.pt5`
   - 产出（stdout text / `--format json`）：
     - `stdby_curr_ma`（flow 记为 **`Stdby_Curr`**）
     - `base_curr_ma`
     - `capture_time_start` / `capture_time_end`
     - `min_power_time_start` / `min_power_time_end` / `min_power_value`
     - `max_power_time_start` / `max_power_time_end` / `max_power_value`
     - `pt5_file`
   - 若无 pt5 且无 JIRA/手动 `Stdby_Curr`：**阻塞**，结束
   - **本步不做「功耗满足标准」提前结束**（须步骤 2 确认 `standby_duration_spec` 有效后再判定）

2. 判定短待机规格并写入 `sleep_time_*`（平台分流；**须**得到有效 `standby_duration_spec` 后再做 ≤60 提前结束）：

   **MTK（默认）** — `base_kernel_standby`（`-d` 全量 `converted/APLog/`，不带 `-t`）：

   ```bash
   python ../../base/kernel_standby/scripts/wakeup_source.py -d temp/<DATE>/<KEY>/converted/APLog
   ```

   - 消费 `stats.screen_segments[]`（`start_off`、`end_on`、`duration_s`）及「详细唤醒信息」灭屏→亮屏分段表
   - 筛选符合 **8.5~11.5 min** 或 **55~65 min** 的有效 OFF 段，flow 写入 `sleep_time_start`、`sleep_time_end`、`standby_duration_min`、`standby_duration_spec`；记 `duration_source=kernel_screen_segments`
   - **0 段**：输出「待机时长无效需复测」，**提前结束**（结论列出各段 `duration_s`）
   - **1 段**：直接采用该段 `start_off`~`end_on`
   - **≥2 段**：
     - 有步骤 1 `capture_time_*`：与各 OFF 段求重叠，选用重叠最大段
     - **无** `capture_time_*`（仅手动 `Stdby_Curr`）：无法可靠选段 → 按「无法判定」**提前结束**，结论写明「缺 pt5 capture_time，多灭屏段无法对齐」

   **高通** — **不**用 `wakeup_source_q` 做灭屏分段（脚本无 `screen_segments`）：

   - **优先**：有步骤 1 `capture_time_start` / `capture_time_end`：
     - `sleep_time_*` = `capture_time_*`
     - `standby_duration_min` = 采集时长（分钟）
     - 按 §2 映射 `standby_duration_spec`；记 `duration_source=pt5_capture`
     - 映射为「无法判定」→ 输出「待机时长无效需复测」，**提前结束**
   - **否则**（无 pt5 / 无 capture）：规格无法判定 → **提前结束**（高通短待机规格依赖 pt5 采集窗；禁止臆造 10min/1h）
   - 本步**可跳过**对 `wakeup_source_q` 的全窗调用；Pending Wakeup 统计留到步骤 4（带 `-t`）

   **共用 — 提前结束门禁**（仅当 `standby_duration_spec` 为 `10min` 或 `1h`）：
   - 若 `stdby_curr_ma ≤ 60`（或手动 `Stdby_Curr ≤ 60`）：输出「功耗满足标准」，结束

3. 调用 CPU 负载分析高低功耗窗口（`-t` 分别为 `max_power_time_*`、`min_power_time_*`；无 pt5 高低窗时降级 `sleep_time_*` 单窗）：

   **MTK** — `base_cpuinfo`：

   ```bash
   python ../../base/cpuinfo/scripts/cpuinfo.py -d temp/<DATE>/<KEY>/converted/APLog \
     -t "<max_power_time_start>" "<max_power_time_end>" -o temp/<DATE>/<KEY>/analysis --report-name cpu_max_report.txt
   python ../../base/cpuinfo/scripts/cpuinfo.py -d temp/<DATE>/<KEY>/converted/APLog \
     -t "<min_power_time_start>" "<min_power_time_end>" -o temp/<DATE>/<KEY>/analysis --report-name cpu_min_report.txt
   ```

   **高通** — `base_cpuinfo_q`：

   ```bash
   python ../../base/cpuinfo_q/scripts/cpuinfo_q.py -d <mobilelog_dir> \
     -t "<max_power_time_start>" "<max_power_time_end>" -o temp/<DATE>/<KEY>/analysis --report-name cpu_max_q_report.txt
   python ../../base/cpuinfo_q/scripts/cpuinfo_q.py -d <mobilelog_dir> \
     -t "<min_power_time_start>" "<min_power_time_end>" -o temp/<DATE>/<KEY>/analysis --report-name cpu_min_q_report.txt
   ```

   - MTK 产出：报告 `cpuinfo_report.txt`；终端 **Anomaly Applications Detection**；字段 `Package`、`PID`、…
   - 高通产出：报告 `cpuinfo_q_report.txt`；终端 **Anomaly Applications Detection**；字段 `Package`、`PID`、…（明细含原始 `Thread`）
   - flow 分别记入 `cpu_analysis_result_max` / `cpu_analysis_result_min`
   - 异常判定对照 **§2.1 或 §2.2**；须提取 §2.4 字段

4. 调用 kernel standby 分析高低功耗窗口（`-t` 同步骤 3；无 pt5 高低窗时降级 `sleep_time_*` 单窗）：

   **MTK** — `base_kernel_standby`（`-t` + `--format json`）：
   - 产出 `summary`：`AP_suspend_failed`、`frequent_wakeup`、`26M_LPM_abnormal`、`26M_LPM_reason`、`screen_wakeup`、…
   - 产出 `stats`：`wakeup_count`、`26m_off_pct_avg`、`top_wakeup_sources`、`system_lpm_blocked.count`、`screen_segments[]`、…

   **高通** — `base_kernel_standby_q`（`-t` + `--format json`）：
   - 产出 `summary`：`pending_wakeup_sources_top3`、`pending_wakeup_hit_count`
   - 产出 `stats`：`pending_wakeup_sources.count`
   - **不产出**（当前脚本不可用）：`screen_wakeup`、`power_button_evidence_count`、`screen_segments[]` — 勿依赖

   - flow 分别记入 `kernel_analysis_result_max` / `kernel_analysis_result_min`

5. 调用 `base_bugreport_standby` 扫描 `converted/bugreports/`（`-d`）：
   - 产出 `summary`：`bugreport_summary`、`top_locks`、`power_rank`、`raw_evidence`
   - 产出 `stats`：`power_rank_top`、`kernel_lock_duration_top`、`partial_lock_duration_top`（及对应 `*_count`）
   - flow 记入 `bugreport_analysis_result`；持锁/alarm 定责窗口为 `sleep_time_*`

6. 对比策略（flow 内逻辑）：
   - 若 `min_power_value ≤ 60 mA`：优先看高低窗口 **差异项**（步骤 3~5 的 max 窗异常、min 窗无异常）
   - 若 `min_power_value` 也超标：优先看高低窗口 **共性项**
   - 结论须引用 `attribution_hint`：`共性主因` vs `差异主因 + 共性底噪`

7. `DATA` 场景：调用 `base_networkinfo` 分析高功耗窗口（`-d` 传工作区根或 `converted/APLog/`）：
   - 先 `--probe`，产出 `scan_dir`、`radio_log_count`、`radio_log_files`、`ready`；`ready=false` 则 **skip**
   - `-t` 为 `max_power_time_*`（无高低窗时用 `sleep_time_*`）；窗口无记录时使用 `--fallback nearest`
   - 产出：`card1`/`card2`、`service_state_data[]`（`network_type`、`is_ca` 等）、`ps_cellular_data[]`（`pci`、`bands` 等）、`data_quality`

8. 有数传嫌疑（**按 `standby_type` 二选一**；满足**任一**即触发）：
   - **共用**：network/数传超 §2.1/§2.2，或 bugreport 指向持续后台流量
   - **MTK 附加**：`R12_CONN2AP` / `R12_AP2AP_PEER` 突出
   - **高通附加**：Pending Wakeup Top3/计数含 `rmnet_*` / `IPA_CLIENT_APPS_WAN_*` / `qcom_rx_wakelock` 等数传相关源
   - `WIFI`：调用 `base_wifi_data`（`-t` 同步骤 7 时间窗），产出 `Start_time`、`End_time`、`WiFi_transfer_power`；flow 记入 `wifi_network_info`
   - `DATA`：调用 `base_modem_data`（`-t` 同上；建议 `--format json`），产出 `start_time`、`end_time`、`data_transfer_power_ma`、`freq_per_h`、`transfer_duration_h`、`packet_count`；flow 记入 `data_network_info`
   - 缺 tshark/mergecap：结论写明「数传量化阻塞」，继续基于 pt5/kernel/CPU/bugreport 阶段性归因

9. 汇总并给出唯一主因归类、责任模块/应用、机制描述、下一步 owner 动作。
   - 整合步骤 3~8 证据，按 `standby_duration_spec` 对照 **§2.1 或 §2.2** 应用异常阈值
   - 按 **`platform`** 选用归因大类（MTK：§26M/R12；高通：Pending Wakeup / 异常应用 CPU / 数传）
   - MTK 主因 `26M/LPM 异常`：责任模块取 `kernel_analysis_result_*.stats.system_lpm_blocked.count` Top1
   - 高通主因：责任模块取 `pending_wakeup_sources_top3` Top1（如 `IPA_CLIENT_APPS_LAN_CONS`）
   - 数传与唤醒阻塞并存：分条写清，禁止混写

## 待实现技能，先跳过

- 检索 JIRA 同类型问题作参考
- kernel/main/sys 错误日志（WIFI、MD 等）

## 门禁

| 条件 | 处理 |
|------|------|
| 工作区无可用 APLog / mobilelog | 标注「日志不足」，禁止编造根因 |
| `platform` 省略 | 默认 `MTK`；高通须显式 `QCOM`，并走 `base_kernel_standby_q` / `base_cpuinfo_q` |
| 灭屏段 / 采集窗无法判定 10min/1h | **提前结束**（「待机时长无效需复测」）；禁止继续编造归因 |
| MTK 多段且无 `capture_time_*` | **提前结束**；结论写明缺 pt5 采集时间无法选段 |
| 高通无 `capture_time_*` | **提前结束**；高通规格依赖 pt5 采集窗 |
| 高通依赖 screen/电源键/segments | **禁止**（当前 `wakeup_source_q` 不输出） |
| CPU 检出异常 | 结论必须输出 Package（或 PID+截断名）级 Top；禁止只写「CPU 高」 |
| MTK 主因 `26M/LPM` | 责任模块取 `system_lpm_blocked.count` Top1 |
| 高通主因 Pending Wakeup | 责任模块取 `pending_wakeup_sources_top3` Top1 |
| 数传与唤醒阻塞并存 | 分条写清，禁止混写 |
| 缺 tshark/mergecap | 记「数传量化阻塞」，继续基于 pt5/kernel/CPU/bugreport 阶段性归因 |
| 无关键证据 | 禁止写「确认根因」 |

## 输出模板

```text
=== 分析结论 ===
最终结论：<责任模块/应用> + <机制描述> + <下一步 owner 动作> + <根因>

=== 问题描述 ===
平台：<MTK / QCOM>
待机类型：<WIFI/DATA>
短待机规格：<10min / 1h>（standby_duration_spec；MTK=灭屏段 / QCOM=pt5 capture）
待机时长：<xx.xx min>
待机时间段：<sleep_time_start>-<sleep_time_end>
实测平均电流 Stdby_Curr：<xx.x> mA
Stdby_Curr 取值来源：<pt5 / JIRA描述 / 手动录入>
短待机功耗标准：达标 ≤60mA；Major(C) 60~70mA；Critical(B) 70~80mA；Block(A) >80mA
功耗等级：<达标 / Major(C) / Critical(B) / Block(A)>

=== 功耗子窗口（pt5）===
最低功耗窗口：<min_power_time_start>-<min_power_time_end>，<min_power_value> mA
最高功耗窗口：<max_power_time_start>-<max_power_time_end>，<max_power_value> mA
pt5 文件：<path 或 N/A>
高低窗对比策略：<差异主因 / 共性主因 / 单窗降级（无 pt5 子窗）>

=== 时长与规格（步骤2，pt5 采集时间见步骤1）===
时长来源：<kernel_screen_segments / pt5_capture>
符合要求的 OFF 段数量：<0 / 1 / ≥2 / N/A（高通）>
时长有效性判定：<MTK: 0→无效停止 / 1→直接写入 / ≥2→capture 匹配；QCOM: capture 映射 §2>
本次分析选用段：<段#n / 唯一段 / pt5_capture 整窗>
pt5 匹配说明：<N/A 或 capture 时间范围与匹配依据>
灭屏段列表：（仅 MTK；高通写 N/A）
- 段#<n>：<start> ~ <end>，时长 <xx.xx> min，判定规格 <10min/1h/无法判定>，<符合/不符合>，<选用/未选用>
自动判定规格：<10min / 1h / 无法判定>
判定：<通过（规格有效） / 不通过（提前结束）>

=== 系统休眠唤醒状态信息 ===
（MTK）
AP suspend 失败：<Yes/No>（字段 AP_suspend_failed）
频繁唤醒：<Yes/No>
26M/LPM 异常：<Yes/No>（字段 26M_LPM_abnormal）
26M/LPM 异常原因：<Top3 或 No>（字段 26M_LPM_reason）
屏幕唤醒：<Yes/No>

（高通 QCOM）
Pending Wakeup Top3：<name(count), ... 或 No>
pending_wakeup_hit_count：<int>
（勿填 screen_wakeup / power_button：脚本不产出）

=== CPU 负载信息 ===
CPU 负载异常：<Yes/No>
应用异常阈值套用：<§2.1 10min / §2.2 1h>
CPU异常Top（高功耗窗，MTK / QCOM 均写 Package）：
- <package|thread> (PID <pid>)：持续 <xx.xmin>，<start ~ end> Avg=<xx.xx%> Max=<xx.xx%> Min=<xx.xx%>
CPU异常Top（低功耗窗，若有差异）：
- ...

=== 网络信息 ===
网络制式：<如 LTE>
CA：<如 CA-A>
小区：<cell id>
band：<如 [8]>
信号强度：<如 -70dBm>
信号质量：<如 90%>
信号制式：<如 GSM>

=== WIFI 数传信息 ===
WIFI 数传频率：<10min 规格写 次/10min；1h 规格写 次/h>
数传时长：<10min 规格写 min；1h 规格写 h>
WIFI 数传功耗(mA)：<数值>

=== 蜂窝数传信息 ===
蜂窝数传频率：<10min 规格写 次/10min；1h 规格写 次/h>
数传时长：<10min 规格写 min；1h 规格写 h>
蜂窝数传功耗(mA)：<数值>
```
