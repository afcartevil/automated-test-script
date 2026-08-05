---
name: flow_power_standby_long
description: 分析一晚或长时段待机功耗问题，输出明确责任归因（系统/模块/应用）与下一步动作。用于待机超标、频繁唤醒、26M/LPM异常、持锁/数传问题定位。
---

## 适用场景
用于一晚/长时段待机分析，定位功耗超标根源：持锁、频繁唤醒、LPM 阻塞、持续数传。

## 输入

- **工作区**：`temp/<DATE>/<KEY>/`（编排层已准备好 `converted/`）
- **`standby_type`**：`WIFI` 或 `DATA`（见下节推断）
- **`log_path`**：优先 `converted/APLog/`（及 `converted/NTLog/`、`converted/bugreports/`）

编排层 `base_jirainfo` 读到的 `summary` / `description` 供本 flow 推断 `standby_type` 与阈值

## standby_type 与功耗阈值（本 flow 专属）

读 JIRA 字段后在本 flow 内推断（实现：`scripts/jira_triage.py`）：

| 条件（summary/description） | `standby_type` | `threshold_ma` |
|---|---|---|
| `Mobile data ON` + `WiFi OFF` / 移动数据开 + WiFi关 | `DATA` | `30` |
| `WiFi ON` | `WIFI` | `25` |
| `SIM Complex Standby` 等未写明网络开关 | `DATA` | `30` |

`jira_triage.py` 示例（**推荐**从工作区读 `jira_info.json`，勿把长 description 塞进命令行）：

```bash
python scripts/jira_triage.py --workspace temp/<DATE>/<KEY>
# → {"standby_type":"DATA","threshold_ma":30,"key":"X6879OS161-2804"}
```

## 前置建议

- `APLog` 先执行 `base_mtk_kernellog_convert`，确保已生成 `*_linli_666.txt`
- Windows 深路径日志包（尤其飞书下载后多层解压目录）须先由编排调用 `base_prepare_workspace`，使用：
  - `temp/<DATE>/<KEY>/converted/APLog/`
  - `temp/<DATE>/<KEY>/converted/bugreports/`
  - `temp/<DATE>/<KEY>/converted/NTLog/`
- 步骤 8 数传（`base_wifi_data` / `base_modem_data`）的主机工具检测见各 base skill 前置条件，本 flow 不再重复。
- 若工作区或日志路径下存在 **`.pt5`** 且能正常解析高低功耗子窗，视为**拆机实测**，步骤 2 **仅**调用 **`base_standby_pt5`**，**禁止**再调用 `base_batteryinfo`；依赖 Cursor **PT5 MCP** 服务，配置见 [base_standby_pt5/SKILL.md](../../base/standby_pt5/SKILL.md)。
- 无 `.pt5` 或 pt5 解析失败时，步骤 2 走 **`base_batteryinfo`**（整机电量统计路径）。

## 判定标准

### 1 功耗阈值与等级
- Wi-Fi 待机标准：`<25mA`
- SIM/数据待机标准：`<=30mA`
- Wi-Fi 等级：`25-35mA => Critical`，`>35mA => Block`
- SIM/数据等级：`30-40mA => Critical`，`>40mA => Block`

### 2 应用异常辅助阈值（用于定责）
- `wakelock`：灭屏累计持锁 `<=5min`（灭屏音频播放除外）
- `CPU`：10 分钟内平均负载 `<=10%`；**突发高负载**：>50% 持续 >3min 或 >100% 持续 >1min 也视为异常
- `network`：总流量 `<50MB/h`
- `network tx`（5s 周期统计）：
  - IM/SMS/Email：发送包 `<60 次/h`
  - 其他类型：发送包 `<30 次/h`
- `alarm`：禁止循环 alarm；禁止准确可唤醒 alarm；`<12 次/h`；建议心跳 `>=5min`
- `JobScheduler`：唤醒间隔 `>=30s`
- `GPS`：使用时长 `<3min`（导航/轨迹/离线下载等除外）
- `BT scan`：累计扫描时长 `<5min/h`
- `Wi-Fi scan`：次数 `<=4 次/h` 且累计扫描时长 `<=3min/h`

### 2.1 CPU 异常输出要求

当 `base_cpuinfo` 检出异常进程时，最终结论里**必须明确输出具体进程/应用**，不能只写“CPU 高”。

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
- 若包名被截断，继续结合 bugreport / PID / ActivityManager 证据还原；实在无法还原时，也必须保留截断名 + PID + 负载片段。

### 3 26M/LPM 主模块判定
- 当 `26M_LPM_abnormal=Yes` 时，必须结合 `base_kernel_standby.stats.system_lpm_blocked.count` 判定主阻塞模块。
- 规则：按阻塞次数从高到低排序，**次数最高的模块** 作为 `26M/LPM` 主模块。
- 输出要求：
  - `26M/LPM 异常原因` 需至少写出主模块；建议同时保留 Top3 计数，例如 `scp(838) > md(664) > conn(33)`。
  - 若主模块与次主模块计数接近，结论中写成“主模块 + 陪同模块”，避免误写成唯一责任。
- 归因口径：
  - 若高低功耗窗口都存在 26M 阻塞，优先比较**共性主模块**。
  - 若仅高功耗窗口出现明显 26M 阻塞增强，优先比较**差异主模块**。

## 归因大类（主因必选一项，按优先级排序）
- AP suspend 失败（系统无法进入休眠）
- 可 suspend，但 26M/LPM 异常（`26M_off_pct` 长期为 0 或偏低）
- 可 suspend，但被频繁唤醒（Wakeup Reasons / R12 主导）
- 应用数传为主（`R12_CONN2AP` / `R12_AP2AP_PEER` + netlog 证据）

## 执行流程（严格顺序）

**进入本 flow 后**：先 `run_python` `jira_triage.py --workspace <工作区根>` 得到 `standby_type` / `threshold_ma`。

1. 调用 `base_kernel_standby` 获取待机总时间窗：`sleep_time_start`、`sleep_time_end`。
2. 功耗与子窗口（**拆机 pt5 / 整机 batteryinfo 二选一**）：

   **2a. 预检 `.pt5`**

   在工作区根、`downloads/`、`log_path`（`converted/APLog/` 等）下递归查找 `*.pt5`（多候选取修改时间最新，规则同 `base_standby_pt5`）。

   **路径 A — 拆机实测（有 pt5 且解析成功）**

   - 调用 **`base_standby_pt5`**（`python base/standby_pt5/scripts/base_pt5.py <工作区根或 log_path> --tool standby`），从 stdout 写入 flow 上下文：
     - `min_power_time_start` / `min_power_time_end` / `min_power_value`
     - `max_power_time_start` / `max_power_time_end` / `max_power_value`
     - `stdby_curr_ma`、`base_curr_ma`、`capture_time_start` / `capture_time_end`、`pt5_file`
   - 记 `standby_mode=disassembled`、`power_window_source=pt5`
   - **禁止调用 `base_batteryinfo`**（拆机无电量曲线，不做电量跳变/漏电判定）
   - 平均功耗取 `stdby_curr_ma`；提前结束门禁：若 `max_power_value ≤ threshold_ma`，输出「功耗满足标准」，结束

   **路径 B — 整机电量统计（无 pt5，或 pt5 解析失败）**

   - 记 `standby_mode=integrated`、`power_window_source=batteryinfo`
   - pt5 存在但 MCP/解析失败时，结论写明「pt5 不可用，降级 batteryinfo」
   - 调用 **`base_batteryinfo`** 分析总时间窗：以步骤 1 的 `sleep_time_start` ~ `sleep_time_end` 为 `--start` / `--end`，`-s` 传 `threshold_ma`
   - 若电量统计跳变：输出「电量统计异常优先」，结束
   - 若存在漏电：输出「漏电优先」，结束
   - 提取最低功耗窗口：`min_power_time_start/end`、`min_power_value`
   - 提取最高功耗窗口：`max_power_time_start/end`、`max_power_value`
   - 若 `max_power_value ≤ threshold_ma`：输出「功耗满足标准」，结束

3. 调用 `base_cpuinfo` 分析高低功耗窗口，分别得到 `cpu_analysis_result_max/min`。
   - 若发现异常进程，必须从 `cpuinfo` 报告中提取“应用/进程名、PID、总异常持续时长、关键时间段、平均负载、最大/最小负载”。
   - 若包名不完整，需继续结合 bugreport / 进程映射补充完整应用名，或至少保留 `PID + 截断包名`。
4. 调用 `base_kernel_standby` 分析高低功耗窗口，分别得到 `kernel_analysis_result_max/min`。
5. 调用 `base_bugreport_standby` 扫描 `converted/bugreports/`；结果记入 `bugreport_analysis_result`。
6. 对比策略：
   - 若 `min_power_value` 达标：优先看高低窗口“差异项”（更可能是问题触发点）。
   - 若 `min_power_value` 也超标：优先看高低窗口“共性项”（更可能是持续根因）。
   - 结论须引用 `attribution_hint`：`共性主因` vs `差异主因 + 共性底噪`。
7. `DATA`待机场景：调用 `base_networkinfo` 分析高功耗窗口（`-d` 传工作区根或 `converted/APLog/`）；先 `--probe` 确认 `radio_log_*` 就绪，缺失则 **skip** 并在结论写明；窗口无记录时使用 `--fallback nearest`。
8. 有数传问题（**按 `standby_type` 二选一**）：
   - `WIFI`待机场景：调用 `base_wifi_data` 分析`max_power_time_start`和`max_power_time_end`时段日志的数传信息，记录`wifi_network_info`。
   - `DATA`待机场景：调用 `base_modem_data` 分析`max_power_time_start`和`max_power_time_end`时段日志的数传信息，记录`data_network_info`。
   - 若蜂窝数传脚本因缺少 tshark/mergecap 失败，必须在结论中显式记录「数传量化阻塞」，但仍继续基于 battery + kernel 证据输出阶段性归因。
9. 汇总并给出唯一主因归类、责任模块/应用、机制描述、下一步 owner 动作。
   - 若主因落在 `26M/LPM 异常`，责任模块默认取 `system_lpm_blocked.count` 中阻塞次数最高的模块。
   - 若结论同时包含数传与 26M 阻塞，需分别写清”应用侧主链路”和”26M 主阻塞模块”，避免二者混写。

## 待实现技能，先跳过
- 检索JIRA,获取是否有同类型问题，提取用户结论，作为参考。
- kernel/main/sys 错误日志（WIFI、MD 等模块异常/应用异常）

## 门禁

| 条件 | 处理 |
|------|------|
| 工作区无 `converted/APLog/`（及必要日志） | 标注「日志不足」，禁止编造根因 |
| 存在可解析 `.pt5`（拆机实测） | **禁止**调用 `base_batteryinfo`；平均功耗仅取 `stdby_curr_ma` |
| `max_power_value ≤ threshold_ma` | 可输出「功耗满足标准」并提前结束 |
| 整机路径电量跳变 / 漏电 | 优先结案对应项，禁止跳过 |
| CPU 检出异常进程 | 结论必须含进程名/PID/时长/时间段/负载；禁止只写「CPU 高」 |
| 主因落在 `26M/LPM 异常` | 责任模块取 `system_lpm_blocked.count` Top1；建议保留 Top3 |
| 数传与 26M 并存 | 分条写清，禁止混写 |
| 蜂窝数传缺 tshark/mergecap | 记「数传量化阻塞」，继续基于 battery + kernel 阶段性归因 |
| 无关键证据 | 禁止写「确认根因」 |

## 输出模板
```text
=== 分析结论 ===
最终结论：<责任模块/应用> + <机制描述> + <下一步 owner 动作> + <根因>

=== 问题描述 ===
待机模式：<拆机实测 / 整机电量统计>
待机时长：<xx.xxH>
待机时间段：<start>-<end>
平均功耗：<xx.xxmA>（拆机取 stdby_curr_ma；整机取 batteryinfo 平均电流）
功耗标准：<25mA 或 30mA>
功耗超标时长：<xx.xxh>（拆机无则写 N/A）

=== 电量信息 ===
电量跳变：<Yes/No；拆机写 N/A>
电压跳变：<Yes/No；拆机写 N/A>
硬件漏电：<描述，无则写 No；拆机写 N/A>
功耗达标时长：<xx.xxh；拆机写 N/A>
功耗超标时长：<xx.xxh；拆机写 N/A>
高低功耗窗来源：<pt5 / batteryinfo>
pt5 文件：<path 或 N/A>
pt5 实测平均电流：<stdby_curr_ma mA 或 N/A>

=== 系统休眠唤醒状态信息 ===
AP suspend 失败：<Yes/No>
频繁唤醒：<Yes/No>
26M/LPM 异常：<Yes/No>
26M/LPM 异常原因：<按 blocked 次数写主模块；建议带 Top3，例如 scp(838) > md(664) > conn(33)；无则写 No>
屏幕唤醒：<Yes/No>

=== CPU 负载信息 ===
CPU 负载异常：<Yes/No>
CPU 负载异常原因：<描述，无则写 No>
CPU异常Top进程：
- <package/process> (PID <pid>)：持续 <xx.xmin>，<start ~ end> Avg=<xx.xx%> Max=<xx.xx%> Min=<xx.xx%>

=== 网络信息 ===
网络制式：<如 LTE>
CA：<如 CA-A>
小区：<cell id>
band：<如 [8]>
信号强度：<如 -70dBm>
信号质量：<如 90%>
信号制式：<如 GSM>

=== WIFI 数传信息 ===
WIFI 数传频率(次/h)：<数值>
数传时长(h)：<数值>
WIFI 数传功耗(mA)：<数值>

=== 蜂窝数传信息 ===
蜂窝数传频率(次/h)：<数值>
数传时长(h)：<数值>
蜂窝数传功耗(mA)：<数值>
```
