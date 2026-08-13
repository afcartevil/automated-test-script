---
name: flow_power_standby_long_dou
description: DOU 长待机分析接口。默认调用固定 WiFi 待机，功耗阈值 25mA。
---

## 定位

本 skill 作为 **DOU 长待机** 编排的**可调用接口**（`flow_power_standby_long_dou`）。

- **默认调用**：`standby_type=WIFI`，**`threshold_ma=25`**（省略入参即此口径；勿按通用 `standby_long` 默认 DATA/30）
- **仅拆机实测**：高低功耗窗与**平均功耗**均**只**来自 pt5；**禁止**调用 `base_batteryinfo` / 整机电量路径
- **平均功耗**：取 `base_standby_pt5` 输出的 **`stdby_curr_ma`**（唯一来源）；不得用手算电量曲线或其它日志估算替代
- pt5 解析失败：**不阻塞**，以降级为「整段用户时间窗」继续步骤 3 起的归因逻辑；此时平均功耗记 `N/A`

## 适用场景

一晚/长时段待机分析，定位持锁、频繁唤醒、LPM 阻塞、持续数传等根因。由上游 DOU 编排传入必填参数后调用。

## 输入

### 必填（三项，缺一则阻塞并向调用方索取）

| 参数 | 说明 | 格式 / 示例 |
|------|------|-------------|
| **`sleep_time_start`** | 灭屏/分析开始时间 | `YYYY-MM-DD HH:MM:SS`，例 `2026-06-10 22:45:02` |
| **`sleep_time_end`** | 灭屏/分析结束时间 | 同上 |
| **`pt5_path`** | `.pt5` 文件路径（文件或其所在目录） | 绝对路径或工作区内路径 |

> 分析总时间窗 **仅** 使用用户/编排传入的 `sleep_time_start` ~ `sleep_time_end`，**不要**再用 kernel standby 自动截取灭屏段覆盖该窗。

### 可选 / 编排约定

- **工作区**：`temp/<DATE>/<KEY>/`（已 `converted/` 则优先）
- **`platform`**：`MTK` 或 `QCOM`（高通）；**省略时默认 `MTK`**
- **`standby_type`**：**默认调用只按 `WIFI`**（步骤 7~8 走 WiFi 数传）；仅编排**显式**传入 `DATA` 或有明确 DATA 证据时才用 `DATA`
- **`log_path`**：优先 `converted/APLog/`（MTK）；高通优先 `downloads/.../mobilelog/` 或 `converted/` 下含 `kernellogcat-log.*` 的目录
- **`threshold_ma`**：**默认 `25`（WiFi）**；仅 `DATA` 时为 `30`。用于报告对照；**不因未达标而强制阻塞**

```bash
# triage 脚本在通用长待机 flow 下（本目录无 scripts/）；可选，非必跑
python ../standby_long/scripts/jira_triage.py --workspace temp/<DATE>/<KEY>
# 【DOU 默认】省略 standby_type → 固定 WIFI / threshold_ma=25
# triage 无明确证据时也可能返回 DATA：【忽略】仍按 WIFI / 25
# 仅明确 DATA 证据或编排显式传入 DATA 时才用 DATA / 30
```

## platform（本 flow 专属）

| `platform` | 说明 | 步骤 1/4 kernel | 步骤 3 CPU |
|---|---|---|---|
| **省略 / `MTK`** | 默认；MediaTek APLog + `linli_666` | `base_kernel_standby` | `base_cpuinfo` |
| **`QCOM` / `高通`** | 高通 `kernellogcat-log.*` | `base_kernel_standby_q` | `base_cpuinfo_q` |

高通 skill 路径：

- Kernel：[base_kernel_standby_q/SKILL.md](../../base/kernel_standby_q/SKILL.md) → `scripts/wakeup_source_q.py`
- CPU：[base_cpuinfo_q/SKILL.md](../../base/cpuinfo_q/SKILL.md) → `scripts/cpuinfo_q.py`

```bash
# 编排层可在工作区 jira_info.json 增加 platform 字段，或由 Agent 显式传入
# platform 省略 → MTK
```

## standby_type 与功耗阈值

> **默认调用（本接口主路径）**：固定 **`WIFI` + `threshold_ma=25`**。  
> 与通用 `standby_long`（常默认 DATA/30）不同；**不要**因 triage 默认 DATA 而改成 30mA。

| 条件 | `standby_type` | `threshold_ma` |
|---|---|---|
| **默认调用 / 省略入参** | **`WIFI`** | **`25`** |
| 编排显式传入 `WIFI`，或 `WiFi ON` | `WIFI` | `25` |
| 编排显式传入 `DATA`，或 `Mobile data ON` + `WiFi OFF` | `DATA` | `30` |
| triage 返回默认 DATA（无明确证据） | **仍按 `WIFI`** | **`25`** |

## 前置建议

**MTK（`platform` 省略或 `MTK`）**

- `APLog` 先执行 `base_mtk_kernellog_convert`，确保已生成 `*_linli_666.txt`
- Windows 深路径须先 `base_prepare_workspace`：`converted/APLog/`、`converted/bugreports/`、`converted/NTLog/`

**高通（`platform=QCOM` / `高通`）**

- 日志目录含 `mobilelog/kernellogcat-log.*`
- **无需** `base_mtk_kernellog_convert`；`base_prepare_workspace` 仍可用于整理 `downloads/` 深路径
- 分析时间窗**仅**用入参 `sleep_time_*`；`base_kernel_standby_q` 只统计 `Pending Wakeup Sources:`（不做灭屏分段 / 电源键统计）

**共用**

- 步骤 8 数传工具检测见 `base_wifi_data` / `base_modem_data`
- **`base_standby_pt5`** 依赖 Cursor **PT5 MCP**，见 [base_standby_pt5/SKILL.md](../../base/standby_pt5/SKILL.md)
- **显式禁止**：任何路径下调用 **`base_batteryinfo`**

## 判定标准

### 1 功耗阈值与等级（报告对照）

- **默认（WiFi）标准**：`<25mA`（本接口默认调用一律用此阈值）
- SIM/数据标准（仅显式 `DATA`）：`<=30mA`
- Wi-Fi 等级：`25-35mA => Critical`，`>35mA => Block`
- SIM/数据等级：`30-40mA => Critical`，`>40mA => Block`

> 有 `stdby_curr_ma` 时写入等级；无 pt5 结果时等级写 `N/A`，**继续后续步骤**。

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

当 `base_cpuinfo`（MTK）或 `base_cpuinfo_q`（高通）检出异常进程时，最终结论里**必须明确输出具体进程/应用**，不能只写“CPU 高”。

**MTK / 高通**：均按包名（`Package`）输出，见 `base_cpuinfo` / `base_cpuinfo_q`。高通 `kernellogcat` 中的 comm 常被截断（如 `facebook.katana`、`.lark.transsion`），报告为 Time / Load / PID / Package；包名不全时结合 bugreport / `ps` 还原。

最少输出字段：应用/进程名、PID、总异常持续时长、至少 1 个关键异常时间段、平均负载、最大/最小负载。

```text
CPU异常Top进程：
1. <package/process> (PID <pid>)
   - 总异常时长: <xx.xmin>
   - 关键时间段: <start ~ end>
   - Avg Load: <xx.xx%>
   - Max/Min Load: <xx.xx%> / <xx.xx%>
```

归因要求：

- 有高低窗：高异常低无异常 → **差异主进程**；均异常 → 取更重者为**共性主进程**
- 无高低窗（pt5 失败、整段单窗）：按单窗异常进程输出，记 `attribution_hint=单窗降级`
- 包名截断时结合 bugreport / PID 还原；否则保留截断名 + PID + 负载片段

### 3 26M/LPM 主模块判定（仅 MTK）

> **高通**：本节不适用；改用 `base_kernel_standby_q` 的 **`pending_wakeup_sources_top3`** 作为唤醒阻塞主因依据；责任模块取 Top1。

- 当 `26M_LPM_abnormal=Yes` 时，按 `system_lpm_blocked.count` 次数最高模块为主模块；建议带 Top3
- 有高低窗：共有阻塞 → 共性主模块；仅高窗增强 → 差异主模块
- 单窗降级：直接取该窗 Top1 为主模块

## 归因大类（主因必选一项，按优先级排序）

**MTK**

- AP suspend 失败（系统无法进入休眠）
- 可 suspend，但 26M/LPM 异常（`26M_off_pct` 长期为 0 或偏低）
- 可 suspend，但被频繁唤醒（Wakeup Reasons / R12 主导）
- 应用数传为主（`R12_CONN2AP` / `R12_AP2AP_PEER` + netlog 证据）

**高通（`platform=QCOM`）**

- Pending Wakeup 阻塞为主（`IPA_CLIENT_*` / `timerfd` / `rmnet_*` 等 **Top3**；主因取 Top1）
- 应用 CPU 负载异常（`base_cpuinfo_q` 异常应用）
- 应用数传为主（`base_modem_data` / bugreport 数传证据 + Pending Wakeup 含蜂窝关键字）
- ~~测试流程干扰（电源键）~~：**当前 `wakeup_source_q` 不输出** `screen_wakeup` / `power_button_evidence_count`；勿作主因依据

## 执行流程（严格顺序）

**进入本 flow 后**：

1. 校验必填：`sleep_time_start`、`sleep_time_end`、`pt5_path`；缺则向调用方索取后返回。
2. 确认 **`standby_type` / `threshold_ma`**：**默认调用固定 `WIFI` / `25`**。仅当编排显式传入 `DATA`，或描述有明确 DATA 证据（如 Mobile data ON + WiFi OFF）时改为 `DATA` / `30`。可选 triage（`../standby_long/scripts/jira_triage.py`）若仅为默认 DATA（无明确证据），**忽略，仍按 `WIFI` / `25`**。
3. 确认 **`platform`**（省略=`MTK`）；记 `standby_mode=disassembled`。

### 步骤明细

0. （前置，由编排完成亦可）`base_prepare_workspace` → **`base_mtk_kernellog_convert`（仅 MTK，按需）**。

1. **确认分析总时间窗**（用户/接口入参，非 kernel 自动截取）：
   - `sleep_time_start` / `sleep_time_end` 已校验
   - 可选：对整窗跑一次 kernel standby（时间窗**仅基线，不改写**起止时间）

   **MTK（默认）** — `base_kernel_standby`：

   ```bash
   python ../../base/kernel_standby/scripts/wakeup_source.py -d temp/<DATE>/<KEY>/converted/APLog \
     -t "<sleep_time_start>" "<sleep_time_end>"
   ```

   **高通** — `base_kernel_standby_q`：

   ```bash
   python ../../base/kernel_standby_q/scripts/wakeup_source_q.py -d <mobilelog_dir> \
     -t "<sleep_time_start>" "<sleep_time_end>"
   ```

2. **功耗与子窗口（仅 pt5；失败不阻塞）**：

   ```bash
   python ../../base/standby_pt5/scripts/base_pt5.py "<pt5_path>" --tool standby --format json
   ```

   - **成功**：写入
     - `min_power_time_start` / `min_power_time_end` / `min_power_value`
     - `max_power_time_start` / `max_power_time_end` / `max_power_value`
     - `stdby_curr_ma`、`base_curr_ma`、`capture_time_start` / `capture_time_end`、`pt5_file`
     - `power_window_source=pt5`、`pt5_ok=true`
     - **平均功耗**：flow 上下文 `avg_current_ma` / 报告「平均功耗」**= `stdby_curr_ma`**（来自本步 pt5，禁止其它来源）
     - 若 `max_power_value ≤ threshold_ma`：可输出「功耗满足标准」并结束（可选门禁；编排可关闭）
   - **失败**（文件无效 / MCP 失败 / 无有效子窗）：
     - **禁止**转 `base_batteryinfo`，**禁止**用日志估算平均功耗
     - `pt5_ok=false`，结论写明「pt5 解析失败，整段时间窗降级；平均功耗 N/A」
     - `power_window_source=full_window`
     - 将 `min_*` / `max_*` **均设为** `sleep_time_start` ~ `sleep_time_end`（单窗；`min/max_power_value` 写 `N/A`）
     - `stdby_curr_ma` / `avg_current_ma` 写 `N/A`
     - **继续**步骤 3，不得中止 flow

3. 调用 CPU 负载分析（时间窗：`pt5_ok=true` → 分别对 `max_power_time_*`、`min_power_time_*`；`pt5_ok=false` → `sleep_time_*` 单窗）：

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

   - 提取 §2.1 规定字段；包名不完整则补全
   - flow 分别记入 `cpu_analysis_result_max` / `cpu_analysis_result_min`（单窗则标明）

4. 调用 kernel standby 分析高低功耗窗口（时间窗策略同步骤 3）：

   **MTK** — `base_kernel_standby`（`-t` + `--format json`）：
   - 产出 `summary`：`AP_suspend_failed`、`frequent_wakeup`、`26M_LPM_abnormal` / `26M_LPM_reason`、…
   - 产出 `stats`：`system_lpm_blocked.count`、`top_wakeup_sources`、…

   **高通** — `base_kernel_standby_q`（`-t` + `--format json`）：
   - 产出 `summary`：`pending_wakeup_sources_top3`、`pending_wakeup_hit_count`
   - 产出 `stats`：`pending_wakeup_sources.count`
   - **不产出**（当前脚本不可用）：`screen_wakeup`、`power_button_evidence_count`、`screen_segments[]` — 勿依赖

   - flow 分别记入 `kernel_analysis_result_max` / `kernel_analysis_result_min`（或单窗）

5. 调用 `base_bugreport_standby` 扫描 `converted/bugreports/`；定责窗为 `sleep_time_*`。

6. 对比策略：
   - `pt5_ok=true` 且 `min_power_value` 达标：优先**差异项**
   - `pt5_ok=true` 且 `min_power_value` 也超标：优先**共性项**
   - `pt5_ok=false`：`attribution_hint=单窗降级（整段时间窗）`，按共性/整窗证据归因
   - 结论须写清 `attribution_hint`

7. `DATA`：`base_networkinfo` 分析高功耗窗（失败时的单窗即 `sleep_time_*`）；先 `--probe`，缺失则 skip；`--fallback nearest`。

8. 数传（按 `standby_type` 二选一；时间窗同步骤 7）：
   - `WIFI` → `base_wifi_data` → `wifi_network_info`
   - `DATA` → `base_modem_data` → `data_network_info`
   - 缺 tshark/mergecap：记「数传量化阻塞」，继续基于 pt5（若有）+ kernel/CPU/bugreport 阶段性归因

9. 汇总唯一主因、责任模块/应用、机制、下一步 owner。
   - 按 **`platform`** 选用归因大类（MTK：§26M/R12；高通：Pending Wakeup / 异常应用 CPU / 数传）
   - MTK 主因 `26M/LPM`：取 `system_lpm_blocked.count` Top1
   - 高通主因 Pending Wakeup：责任模块取 `pending_wakeup_sources_top3` 的 **Top1**
   - 数传与唤醒阻塞并存：分条写清，禁止混写

## 待实现技能，先跳过

- 检索 JIRA 同类型问题作参考
- kernel/main/sys 错误日志（WIFI、MD 等）

## 门禁

| 条件 | 处理 |
|------|------|
| 缺 `sleep_time_start` / `sleep_time_end` / `pt5_path` 任一 | **阻塞**，向调用方索取；禁止猜灭屏段 |
| `platform` 省略 | 默认 `MTK`；高通须显式 `QCOM`，并走 `base_kernel_standby_q` / `base_cpuinfo_q` |
| `standby_type` 省略（默认调用） | 固定 **`WIFI` / `25mA`**；`DATA`/`30` 仅显式传入或有明确 DATA 证据 |
| 用 kernel standby 自动截取覆盖用户时间窗 | **禁止** |
| 调用 `base_batteryinfo` 填平均功耗 | **禁止**；平均功耗仅来自 pt5 `stdby_curr_ma` |
| pt5 解析失败 | **不阻塞**；高低窗降级为整段用户时间窗，平均功耗记 `N/A` |
| MTK 主因 `26M/LPM` | 责任模块取 `system_lpm_blocked.count` Top1 |
| 高通主因 Pending Wakeup | 责任模块取 `pending_wakeup_sources_top3` Top1 |
| 高通依赖 screen/电源键/segments | **禁止**（当前 `wakeup_source_q` 不输出） |
| 数传与唤醒阻塞并存 | 分条写清，禁止混写 |
| 缺 tshark/mergecap | 记「数传量化阻塞」，继续阶段性归因 |
| 无关键证据 | 禁止写「确认根因」 |

## 调用约定（供 DOU 编排）

### 其它 Skill 如何调用本接口

本仓库 skill **不是**可 import 的 Python API，而是 **Agent 读 `SKILL.md` 后按 SOP 执行**。上游 skill 按下面做即可：

1. **在上游 `SKILL.md` 写明分支**：命中「DOU 长待机 / 拆机长时段」时，转去执行本接口，不要自己重写步骤 2~9。
2. **先备齐必填三项**，再让 Agent：
   - `Read` 本文件：`analysis/domain/power/flow/standby_long_dou/SKILL.md`
   - 严格按本文「执行流程」跑完，并把「输出模板」全文交回上游
3. **参数用明确键值传入**（写入上游上下文或用户消息），禁止让本接口再猜灭屏段：

```text
# 上游伪代码（编排层 / 上游 skill 步骤里写清楚）
call: flow_power_standby_long_dou
  skill_path: analysis/domain/power/flow/standby_long_dou/SKILL.md
  sleep_time_start: "2026-06-10 22:45:02"   # 必填 YYYY-MM-DD HH:MM:SS
  sleep_time_end:   "2026-06-11 06:00:00"   # 必填
  pt5_path:         "D:/data/xxx.pt5"       # 必填
  workspace:        "temp/<DATE>/<KEY>"     # 可选，建议传
  platform:         "MTK" | "QCOM"          # 可选；省略=MTK
  standby_type:     "WIFI"                  # 可选；省略=WIFI/25；DATA 须显式传入
```

4. **接收返回**：本接口输出模板全文 + `pt5_ok` / `power_window_source` / `attribution_hint` / `stdby_curr_ma`（平均功耗）。上游可嵌入总报告，勿改写归因主因除非有额外证据。
5. **职责边界**：
   - 上游负责：定场景、准备 `converted/`、收集/校验三项必填、决定是否继续其它 DOU 流程
   - 本接口负责：按 `platform` 分流 pt5 平均电流与高低窗、CPU/kernel/bugreport/数传与唯一主因
   - 上游 **不要** 再调 `base_batteryinfo` 填平均功耗
   - MTK → `base_cpuinfo` + `base_kernel_standby`；高通 → `base_cpuinfo_q` + `base_kernel_standby_q`

### 上游 SKILL 片段示例

```markdown
## 分支：DOU 长待机
当判定为长时段拆机待机时：
1. 向用户或前置步骤取得 sleep_time_start / sleep_time_end / pt5_path
2. 传入 platform（MTK 可省略；高通须显式 QCOM）；standby_type 省略则按 WIFI / 25mA
3. Read `../standby_long_dou/SKILL.md`（或绝对路径 …/flow/standby_long_dou/SKILL.md）
4. 按该 skill 执行流程完整跑一遍后，取其「输出模板」作为本段结论
```

### 直接 invoke 清单

```text
invoke flow_power_standby_long_dou
  sleep_time_start: "2026-06-10 22:45:02"
  sleep_time_end:   "2026-06-11 06:00:00"
  pt5_path:         "D:/data/xxx.pt5"
  # 可选
  workspace:        "temp/<DATE>/<KEY>"
  platform:         "MTK" | "QCOM"    # 省略=MTK
  standby_type:     "WIFI" | "DATA"   # 省略=WIFI / threshold_ma=25；DATA 须显式
```

返回：本 skill「输出模板」全文 + 上下文中的 `pt5_ok` / `power_window_source` / `attribution_hint`。

## 输出模板

```text
=== 分析结论 ===
最终结论：<责任模块/应用> + <机制描述> + <下一步 owner 动作> + <根因>

=== 问题描述 ===
接口：flow_power_standby_long_dou（DOU 长待机）
平台：<MTK / QCOM>
待机模式：拆机实测
待机时长：<xx.xxH>
待机时间段：<sleep_time_start>-<sleep_time_end>（用户/编排指定）
平均功耗：<stdby_curr_ma mA 或 N/A>（仅来自 pt5；禁止 batteryinfo）
功耗标准：<默认 25mA（WiFi）；显式 DATA 时 30mA>
pt5 状态：<ok / 失败降级整段时间窗>
高低窗来源：<pt5 / full_window>
attribution_hint：<差异主因 / 共性主因 / 单窗降级>

=== 电量信息 ===
电量跳变：N/A（拆机）
电压跳变：N/A
硬件漏电：N/A
高低功耗窗来源：<pt5 / full_window>
pt5 文件：<pt5_path>
平均功耗（= pt5 stdby_curr_ma）：<stdby_curr_ma mA 或 N/A>
最低功耗窗口：<min_start>-<min_end>，<min_power_value mA 或 N/A>
最高功耗窗口：<max_start>-<max_end>，<max_power_value mA 或 N/A>

=== 系统休眠唤醒状态信息 ===
（MTK）
AP suspend 失败：<Yes/No>（字段 AP_suspend_failed）
频繁唤醒：<Yes/No>
26M/LPM 异常：<Yes/No>
26M/LPM 异常原因：<按 blocked 次数写主模块；建议带 Top3；无则写 No>
屏幕唤醒：<Yes/No>

（高通 — 对齐 wakeup_source_q）
Pending Wakeup Sources Top3：<name(count); ... 或 No>
pending_wakeup_hit_count：<n>
屏幕唤醒：N/A（当前脚本不输出）
电源键证据次数：N/A（当前脚本不输出）
screen_segments：N/A（当前脚本不输出）

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
