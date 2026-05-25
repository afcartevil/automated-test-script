---
name: transsion-dcp-fastcharge-probe
description: “Transsion-快充探测: 分析BC1.2得到DCP后快充探测与算法选型，区分tchg_alg五套算法选型 | DCP/pe5/pd/hvdcp20/tc30/pe20/tfcp_adapter/PPS | 当用户报告快充算法选型异常、RFC失败后PD/PPS接管问题、hvdcp20/tc30未起来时使用”
---

# Transsion DCP 后快充探测

## 适用范围

聚焦 **BC1.2 结果已稳定为 DCP**（或 **`tc_algo_protocol_process()` 已允许尝试 PE5/PDC**）之后，系统如何继续探测不同快充协议，并最终选择 **哪一套 `tchg_alg` 在跑**；若选中 **`pe5`**，再进一步分析其 **内部 `support_ta` adapter 探测顺序**。

包含：
- **外层：`tc_charger` 的 `support_alg` 与 `tchg_alg` 轮询**
  - `drivers/power/supply/transsion/tc_charger.c`：`tc_charger_parse_dt()` 读取 `support_alg`，`charger_init_algo()` 中 `get_tchg_alg_by_name()` + `tchg_alg_id()`
  - `drivers/power/supply/transsion/tc_basic_charger.c`：`tc_algo_protocol_process()` 按 `data->alg[]` 顺序调用 `tchg_alg_is_algo_ready()` / `tchg_alg_start_algo()`，设置 `data->running_algo`
  - `drivers/power/supply/transsion/tc_charger.h`：`enum alg_id_enum` 与 `alg_name_array[]`（`pe5` / `tc30` / `pd` / `hvdcp20` / `pe20`）
- **内层：仅当 `pe5` 被选中时，PE5 内部的 adapter 探测**
  - `drivers/power/supply/transsion/pca_tfcp_ta.c`
  - `drivers/power/supply/transsion/tc_pd_adapter.c`
  - `drivers/power/supply/transsion/tc_hvdcp30_adapter.c`
  - `drivers/power/supply/transsion/tc_pe5.c`
  - `drivers/power/supply/transsion/tc_pe5_hal.c`
  - `drivers/power/supply/transsion/tc_pd_hal.c`
  - `support_ta` 顺序、`authenticate_ta()`、`adapter_name -> PE50_*` 映射
- **与 DPDM/开关相关的执行辅助（需要交叉阅读时）**
  - `drivers/power/supply/transsion/tran_usb_ctrl.c`：`hvdcp20` / `tc30` 的 GPIO/开关控制路径（常与 `TRAN_PROP_USB_CTRL_*` 通知联动）

不包含：
- `tc_chg_type_det.c` 内部 BC1.2 端口识别细节
- `tc_charger.c` 的 vote 聚合与主控线程（见 `transsion-charger-orchestrator`）
- **PE5 已选型后的调压调流、tc_pe50.dtsi 参数与 V/I 闭环**（见 `transsion-pe5-vi-tuning`）
- 原生 TCPC/PD policy engine 细节
- USB 角色桥接与 MTU3 枚举细节

## 固定入口

### A. 先判断“哪套 `tchg_alg` 在竞争/在跑”（`support_alg`）

1. `tc_charger.c`：`tc_charger_parse_dt()` 打印的 `support alg(%s)` 列表
2. `tc_charger.c`：`charger_init_algo()` 中 `get_tchg_alg_by_name(desc->support_alg[i])` 是否 success
3. `tc_basic_charger.c`：`tc_algo_protocol_process()` 日志里对每个 `alg` 的 `tchg_alg_is_algo_ready()` 状态
4. `tc_charger.h`：核对 `alg_name_array[]` 与 `enum alg_id_enum` 是否与 dtsi 字符串一致（`pe5` / `tc30` / `pd` / `hvdcp20` / `pe20`）

### B. 仅在确认主路径是 `pe5` 时，再下钻 PE5 内部 `support_ta`

1. `tc_pe5.c` 的 `pe50_is_ta_rdy()`
2. `tc_pe5.c` 的 `pe50_check_algo_name()`
3. `tc_pe5_hal.c` 的 `pe50_hal_init_hardware()`
4. `tc_pe5_hal.c` 的 `pe50_hal_authenticate_ta()`

按协议分支补查：
- RFC: `pca_tfcp_is_rfc_ta()` / `pca_tfcp_authenticate_ta()`
- PPS: `tc_pd_adapter.c` 的 `PD_TYPE_TIMEOUT` / `tc_pd_connect_changed()`
- HVDCP30: `tc_hvdcp30_mode_check()` / `tc_hvdcp30_authenticate_ta()`

### C. 若问题落在 `hvdcp20` / `tc30` / `pe20` / `pd`（非 PE5 内部 adapter 名）

- `tc_hvdcp20.c` / `tc_tc30.c` / `tc_pe20.c` / `tc_pd.c`：各自 `tchg_alg_device_register("<name>")` 与 `tchg_alg_is_algo_ready()` 状态机
- 需要结合 `tran_usb_ctrl.c` 核对握手/升压/复位是否实际作用到 D+/D- 或开关通道

## 总体主链

```text
BC1.2 -> alias_type / port stat 稳定（tc_chg_type_det）
-> tc_basic_charger.c: tc_algo_protocol_process()
-> 按 dtsi support_alg 顺序填充的 data->alg[] 逐个 tchg_alg_is_algo_ready()
-> 选中 data->running_algo（可能是 pe5 / pd / hvdcp20 / tc30 / pe20 之一）

若 running_algo == pe5:
-> tc_pe5.c: pe50_is_ta_rdy()
-> iterate hal->support_ta order（tfcp_adapter / pd_adapter / hvdcp30_adapter）
-> per-adapter authenticate_ta()
-> choose running_ta / running_spec
-> pe50_check_algo_name()
-> PE50_RFC / PE50_PPS / PE50_QC3
```

## 为什么要区分「五套 `tchg_alg`」与「PE5 内三类 adapter」

- dtsi 里的 `support_alg = "pe5", "pd", "hvdcp20", "tc30", "pe20"` 描述的是 **`tc_charger` 这一层的算法模块注册表**，代码侧通过 `tchg_alg_device_register(name)` / `get_tchg_alg_by_name(name)` 对齐（见 `tc_charger.h` 的 `alg_name_array[]`）。
- 之前 skill 里写的 `tfcp_adapter` / `pd_adapter` / `hvdcp30_adapter` 属于 **`pe5` 模块内部的 TA 适配器列表**，由 **`support_ta`** 控制顺序；它解决的是 **“PE5 这条路径里 RFC / PPS / QC3 谁先认证成功”**，并不能覆盖 **`hvdcp20` / `tc30` / `pe20` / 独立 `pd` 算法模块** 的探测路径。
- 因此：排查“为什么只跑了 PE5、没跑 hvdcp20/tc30/pe20”时，**优先看 `tc_algo_protocol_process()` 对 `data->alg[]` 的遍历结果**，而不是只看 `support_ta`。

## 五套 `tchg_alg`（`support_alg`）各自关注点（外层）

下列名称与 `tc_charger.h` 中 `alg_name_array[]` 一致，应与 dtsi 字符串一一对应：

| `support_alg` 字符串 | 典型实现文件 | 说明 |
| --- | --- | --- |
| `pe5` | `tc_pe5.c` | PE5.0 主路径；内部再按 `support_ta` 在 RFC / PPS / QC3 间选型 |
| `pd` | `tc_pd.c` | 独立的 PD/PPS `tchg_alg` 模块（与 `pe5` 内 `pd_adapter` 不是同一层级概念） |
| `hvdcp20` | `tc_hvdcp20.c` | QC2.0/HVDCP20 类升压握手（常配合 `tran_usb_ctrl` 做 DPDM/开关动作） |
| `tc30` | `tc_tc30.c` | TC30 协议栈（常配合 `charger_dev_set_tc30_oneshot()` 一类 charger ops） |
| `pe20` | `tc_pe20.c` / `tc_pe20_hal.c` | PE2.0：`support_pe20_by_switch` 决定走 charger `send_ta20_current_pattern` 或软件 `pe20_set_current_pattern`，算法层仍以 VBUS 验收；可选 `set_pe20_efficiency_table` |

外层选择逻辑（简化）：`tc_algo_protocol_process()` 从 `i = 0` 开始遍历 `data->alg[i]`，调用 `tchg_alg_is_algo_ready()`；满足 `ALG_READY/ALG_RUNNING` 时 `tchg_alg_start_algo()` 并设置 `data->running_algo`。**遍历顺序由 `support_alg` 在 probe 时填充 `data->alg[]` 的顺序决定**。

### `pe5`（`tc_pe5.c`）：作为 `tchg_alg` 的就绪门控（与内层 `support_ta` 的关系）

`support_alg` 里选中 **`pe5`** 时，`tc_charger` 先看到的是 **`pe50_is_algo_ready()`** / **`pe50_start_algo()`**（`tc_pe5.c` 注册为 `tchg_alg`），**不是**直接等价于「某一路 `tfcp_adapter` 已握手成功」。内层 **`support_ta` 顺序与 `authenticate_ta()`** 是在 **`pe50_is_ta_rdy()`** 及其调用的各 adapter 里完成的。

1. **`pe50_is_algo_ready()`（外层）典型门控**（在调用 `pe50_is_ta_rdy()` 之前/之后）  
   - 未 init、异常策略：`pe50_algo_abnormal_check()` 不通过 → 常返回 **`ALG_TA_CHECKING`**。  
   - **旁路 / bypass**：若 `TRAN_PROP_SUPPORT_ALLROUND_BYPASS` 且 `TRAN_PROP_GET_BYPASS_EN` 为真 → **跳过 PE50**（`ALG_TA_CHECKING`）。  
   - **gauge 固件升级**、**双电运行模式** 等 → 可能 `ALG_TA_CHECKING` / `ALG_TA_NOT_SUPPORT`。  
   - **`run_once`** 与 **`PE50_RESET_NOTIFY`**：限制重复进入，需 detach/hardreset 通知清标志后才再跑。  
   - 调用 **`pe50_is_ta_rdy(info)`**：此处才进入 **`support_ta` 顺序 + 各 adapter 认证**；若未得到 **`ALG_READY`**，整体不算就绪。  
   - **电芯电压窗口**：`pe50_get_adc(VBAT)` 需在 `start_vbat_min~start_vbat_max`，否则 **`ALG_NOT_READY`**。  
   - 已在跑：`pe50_is_algo_running` → **`ALG_RUNNING`**。

2. **`pe50_start_algo()`（外层启动）**  
   - 要求 `data->inited && data->ta_ready`；否则 **`ALG_INIT_FAIL`**。  
   - **`pe50_hal_enable_sw_vbusovp(alg, false)`** 后调 **`pe50_start()`**。

3. **与内层三 adapter 小节的衔接**  
   - 排查「**为什么 `tc_algo_protocol_process` 永远轮不到 PE5 就绪**」：先看本节门控（bypass、gauge、vbat、`pe50_is_ta_rdy` 返回值）。  
   - 排查「**PE5 已就绪但 RFC/PPS/QC3 行为不对**」：再下钻下面 **「PE5 内三类 adapter」** 与 `support_ta` 顺序。

4. **外层排查清单**  
   - [ ] 日志中 `pe50_is_algo_ready` / `pe50_is_ta_rdy` 的返回是否为 `ALG_READY`。  
   - [ ] 是否被 bypass / gauge / dual batt / `run_once` 卡住。  
   - [ ] VBAT ADC 是否在 `start_vbat_*` 窗口内。  
   - [ ] `pe50_start_algo` 是否因 `ta_ready==false` 失败。

### `hvdcp20`（`tc_hvdcp20.c`）：握手机制与「握手是否成功」的判据

本算法的「握手」**不是**在 `tc_hvdcp20.c` 里逐比特实现 QC2.0 D+/D- 状态机，而是：

1. **抽象为对 `usb_control` 设备的属性下发**  
   `tc_hvdcp20_hal.c` 的 `ta_dev_set_usb_ctrl_hvdcp20()` 通过 `tran_dev_set_prop(..., TRAN_PROP_USB_CTRL_HVDCP20, val)` 把目标档位（如 `HVDCP20_NONE` / `HVDCP20_9V` / `HVDCP20_SWITCH_*`）交给 `tran_usb_ctrl.c`。  
   `tran_usb_ctrl_hvdcp20_setting_handler()` 再根据 dts 的 `hvdcp20_control_type` 走 **开关 IC / GPIO / 开关+GPIO / coupler** 等路径，完成复位、握手、升压、切档等硬件动作（日志里可见 `hvdcp20 handshake` / `boost 9v` / `switch 5v|9v` 等）。

2. **算法侧探测 TA 的主序列**（`__hvdcp20_check_charger()` → `hvdcp20_detect_ta()`）  
   - 先 `hvdcp20_reset_ta_none_check_volt()`：等价于 `ta_dev_set_usb_ctrl_hvdcp20(HVDCP20_NONE)`，把 TA 拉回基线。  
   - 再 `hvdcp20_detect_ta()`：**临时关闭常规 VBUS OVP**（`hvdcp20_hal_enable_vbus_ovp(false)`），调用 `hvdcp20_set_ta_vchr(HVDCP20_9V)` 请求 9V 档；探测结束或失败时 **恢复 OVP**。  
   - `hvdcp20_set_ta_vchr()` 在设置前后读 `hvdcp20_hal_get_vbus()`，用 **测量 VBUS 与目标档位的 `chr_volt` 差是否小于 1V（1000000µV）** 作为「握手/升压是否生效」的软件判据；成功后再设 MIVR 等。

3. **何时认为「可以进入握手」**（`_hvdcp20_is_algo_ready()`）  
   - `hvdcp20_hal_get_charger_type()` 必须为 **`TC_DCP`**，否则置 `ALG_TA_NOT_SUPPORT`。  
   - 若电量/电芯电压超过阈值则 `ALG_NOT_READY`（不进入握手）。  
   - 状态机需为 `ALG_READY`。

4. **握手正确与否的排查清单（本 skill 必须能覆盖）**  
   - [ ] `tc_algo_protocol_process()` 是否已轮到 `hvdcp20` 且 `tchg_alg_is_algo_ready()` 为 `ALG_READY`（否则根本不会 `start_algo`）。  
   - [ ] `usb_control` 设备是否存在：`ta_dev_set_usb_ctrl_hvdcp20()` 若 `tran_get_by_name("usb_control")` 失败则无法下发握手。  
   - [ ] `tran_usb_ctrl` 节点 `hvdcp20_control_type` 是否为 `NOT_SUPPORT`（若是则 handler 空操作，VBUS 不会变）。  
   - [ ] 探测阶段是否出现 OVP 关闭/恢复：`hvdcp20_detect_ta()` 内 `enable_vbus_ovp(false/true)`。  
   - [ ] 日志中 `hvdcp20_set_ta_vchr` 的 `ret`、`vchr_before/vchr_after` 与 `delta`：**`delta < 1V` 且 `_hvdcp20_set_ta_vchr` 返回 0** 视为本层判定成功。  
   - [ ] 若 `delta` 大但 `tran_usb_ctrl` 无报错：怀疑 **测量点/通路**（`hvdcp20_hal_get_vbus`）与 **实际 DPDM 是否接到 charger** 不一致。  
   - [ ] 运行中 `__hvdcp20_run()` 若 VBUS 与 `org_chr_volt` 偏离 **>1.5V** 会判定 **HVDCP20 leave unexpectedly** 并 `hvdcp20_leave()`。

### `tc30`（`tc_tc30.c`）：握手机制与「握手是否成功」的判据

结构与 `hvdcp20` 相同：**不在 `tc_tc30.c` 内实现完整比特级协议**，而是通过 `usb_control` 抽象档位 + **VBUS 实测验收**；平台差异在 `tran_usb_ctrl.c` 与 charger IC 的 `set_tc30_oneshot` ops。

1. **档位枚举（与 `tran_usb_ctrl` / charger ops 共用）**  
   见 `tc_common_class.h`：`TC30_NONE`、`TC30_7V5`、`TC30_SWITCH_5V`、`TC30_SWITCH_7V5`。探测阶段首次请求的是 **`TC30_7V5`**（与 `hvdcp20` 首次请求 `HVDCP20_9V` 不同）。

2. **下发路径**  
   `tc_tc30_hal.c` 的 `ta_dev_set_usb_ctrl_tc30()` → `tran_dev_set_prop(..., TRAN_PROP_USB_CTRL_TC30, val)` → `tran_usb_ctrl_tc30_setting_handler()`，由 dts **`tc30_control_type`** 选择：纯开关 IC、**oneshot（内部调 `charger_dev_set_tc30_oneshot()` 切 5V/7.5V）**、GPIO 切 pinctrl、或 GPIO+was4783 并额外发 `TRAN_PROP_USB_CTRL_TC30_TA` 等。

3. **算法侧探测主序列**（`__tc30_check_charger()` → `tc30_detect_ta()`）  
   - `tc30_reset_ta_none_check_volt()`：`ta_dev_set_usb_ctrl_tc30(TC30_NONE)`。  
   - `tc30_detect_ta()`：**关 OVP** → `tc30_set_ta_vchr(TC30_7V5)` → 失败/返回路径上 **恢复 OVP**。  
   - `tc30_set_ta_vchr()`：前后读 `tc30_hal_get_vbus()`，**`|vbus - 目标 chr_volt| < 1V` 且 `_tc30_set_ta_vchr` 成功** 视为握手/升压成功。  
   - 成功后 `tc30_inform_related_module()`：向 **`port_burn`** 置 `TRAN_PROP_IS_TC30_TA`（用于端口烧机/相关策略模块识别 TC30 TA）。

4. **何时允许进入握手**（`_tc30_is_algo_ready()`）  
   - `tc30_hal_get_charger_type()` 为 **`TC_DCP`**，否则 `ALG_TA_NOT_SUPPORT`。  
   - 状态为 `ALG_READY`，且 SOC/Vbat 未触发 `ALG_NOT_READY`。

5. **运行期切档与异常**（`__tc30_run()`）  
   - 若 VBUS 与当前期望 `org_chr_volt` 偏离 **>1V**，认为 **TC30 leave unexpectedly**，`tc30_leave()`。  
   - 按 `tc30_hal_get_charger_current_limit()` 与 `chr_volt_chg_cur[]`、`recover_7v5_gap` 在 **`TC30_SWITCH_5V` ↔ `TC30_SWITCH_7V5`** 间切换（再调用 `tc30_set_ta_vchr()`）。

6. **握手正确与否的排查清单（本 skill 必须能覆盖）**  
   - [ ] `running_algo` 是否为 `tc30` 且 `tchg_alg_is_algo_ready()` 为 `ALG_READY`。  
   - [ ] `usb_control` 是否存在、`tc30_control_type` 是否非 `NOT_SUPPORT`。  
   - [ ] `tc30_detect_ta()` 是否执行 OVP 关断/恢复。  
   - [ ] `tc30_set_ta_vchr` 日志中 **`TC30_7V5` 探测** 的 `delta` 是否 <1V。  
   - [ ] oneshot 平台：primary_charger 的 `set_tc30_oneshot` 是否实现且被调用。  
   - [ ] 是否出现 `port_burn` / `TRAN_PROP_IS_TC30_TA` 置位（若业务依赖 TA 识别）。  

### `pe20`（`tc_pe20.c`）：握手机制与「握手是否成功」的判据

与 `hvdcp20`/`tc30` 的「`usb_control` 档位 + VBUS 验收」部分相似，但 **PE20 的协议脉冲核心在 `tc_pe20_hal.c`**：`ta_dev_set_usb_ctrl_pe20()` **不一定**走 `tran_usb_ctrl`，而是由 dtsi **`support_pe20_by_switch`** 在 **「充电 IC 硬件发码」** 与 **「软件拉输入电流脉冲」** 两路径间切换。

1. **档位枚举**  
   `tc_common_class.h`：`PE20_NONE`、`PE20_9V`（探测阶段首次请求 **`PE20_9V`**，与 `hvdcp20` 首次 9V 类似，与 `tc30` 首次 7.5V 不同）。

2. **`ta_dev_set_usb_ctrl_pe20()` 实际做什么**（`tc_pe20_hal.c`）  
   - 目标电压来自 `pe20->chr_volt[value]`（由 **pe20 节点 `chr_volt` 数组**解析，缺省会 probe 失败）。  
   - **`value == PE20_NONE`（复位）**  
     - `support_pe20_by_switch`：**`charger_dev_reset_ta(hal->chg1_dev)`**  
     - 否则：`pe20_reset_ta()`（拉输入电流到 0 并延时，相当于软件 reset 序列）  
   - **`value == PE20_9V`（发握手/升压请求）**  
     - `support_pe20_by_switch`：**`charger_dev_send_ta20_current_pattern(chg1_dev, uV)`**（由具体 charger 驱动实现 PE2.0 脉冲）  
     - 否则：**`pe20_set_current_pattern(alg, uV)`** —— 在 HAL 里用 **`pe20_hal_set_input_current()` 交替 0/800mA** 等产生 **Pump Express 电流码**，并对 **脉冲间隔** 做范围校验（代码中 `cptime` 与 `30~65ms`、`180~240ms` 等门限）；失败会 **重试最多 3 次**。  
   - 若 `support_pe20_by_switch` 为真，成功后 **`rerun_election(chg1_aicr_vote)`**，避免 AICR 投票与 TA 脉冲冲突。

3. **算法层仍用 VBUS 验收**（`tc_pe20.c`）  
   `pe20_detect_ta()`：**关 OVP** → `pe20_set_ta_vchr(PE20_9V)` → 失败则恢复 OVP。  
   `pe20_set_ta_vchr()`：与另外几套算法相同，**`|VBUS - chr_volt| < 1V` 且底层成功** 视为本层「握手/升压成功」，再设 MIVR。

4. **何时允许进入握手**（`_pe20_is_algo_ready()`）  
   - `pe20_hal_get_charger_type()`（即 `tc_get_alias_type()`）为 **`TC_DCP`**，否则 `ALG_TA_NOT_SUPPORT`。  
   - `ALG_READY` 且 SOC/Vbat 未触发 `ALG_NOT_READY`。

5. **运行期**（`__pe20_run()`）  
   - 与 `tc30`/`hvdcp20` 不同：**无** 5V/9V 档位轮询切档逻辑；主要监控 VBUS 是否相对 `org_chr_volt` 偏离 **>1V**（判 **PE20 leave unexpectedly**），以及高 SOC + 小电流时 `pe20_leave()` 结束。

6. **与充电 IC 的其它耦合**  
   - 部分平台在 charger 驱动里实现 **`set_pe20_efficiency_table`**（如 `charger_dev_set_pe20_efficiency_table`），用于 **PE2.0 调压码/效率表**，与上述握手配合，排查时需打开对应 `primary_chg` 驱动。

7. **握手正确与否的排查清单（本 skill 必须能覆盖）**  
   - [ ] `running_algo` 是否为 `pe20` 且 `tchg_alg_is_algo_ready()` 为 `ALG_READY`。  
   - [ ] pe20 节点 **`chr_volt` / `chr_volt_mivr` 等 dtsi 是否齐全**（否则算法 probe 直接失败）。  
   - [ ] **`support_pe20_by_switch`**：若为真，查 **`charger_dev_send_ta20_current_pattern` / `charger_dev_reset_ta`** 是否在 primary_chg 实现且返回成功；若为假，查 **`pe20_set_current_pattern`** 是否通过间隔校验、是否进入 `retry`。  
   - [ ] `pe20_detect_ta` 是否 **OVP 关断/恢复**。  
   - [ ] `pe20_set_ta_vchr` 日志里 **`PE20_9V` 的 VBUS delta** 是否 <1V。  
   - [ ] `support_pe20_by_switch` 为真时是否出现 **`rerun_election(chg1_aicr)`** 相关侧效应（AICR 被拉低导致脉冲异常等）。

## PE5 内三类 adapter 的检测差异（内层，仅 `pe5`）

### RFC / TFCP

- 入口：`pca_tfcp_is_rfc_ta()`
- 前置条件：
  - `tc_get_alias_type() == TC_DCP`
  - 不是 `TC_NON_STD`
  - `tc_get_pd_type()` 不能已经是 `PE_READY_*`
- 探测动作：
  - `TRAN_PROP_USB_CTRL_RFC = RFC_HANDSHAKE`
- 完成标志：
  - `tfcp_ta_det_done`
- 认证入口：
  - `pca_tfcp_authenticate_ta()`
- 结果解释约束（必须遵守）：
  - `rfc_handshake_by_cp_ic ... failed` / `rfc control by cp ic failed(-22)` **不能单独用来证明“CP 路径不稳定”**。
  - 若已知当前充电器**不支持 RFC**，上述失败应先按“能力不匹配导致 RFC 探测失败”处理（可接受现象）。
  - 仅在已确认“充电器支持 RFC”且仍失败时，才可升级为 CP/RFC 路径异常结论。
  - 若日志中无法确认充电器 RFC 能力，输出必须显式写明：**“RFC 能力未知，当前失败不构成 CP 不稳定证据”**。

### PE5 内 `pd_adapter`（与「独立 `pd` 算法」分工）

背景：RFC（`tfcp_adapter`）不跑或失败后，`support_ta` 按顺序继续；轮到 **`pd_adapter`** 时，PD 协议栈往往已经可以继续协商，但 **PE5 对「是否用本 adapter 做 PE5 快充」的判定与独立 `pd` 算法不同**。

#### 1) `tc_pe5.c`：`pd_adapter` 专用门控（先于 `authenticate_ta`）

`pe50_is_ta_rdy()` 遍历 `support_ta` 时，若当前 adapter 名为 **`pd_adapter`**，**不会立刻 `authenticate_ta`**，而是先调用 **`pe50_hal_is_pd_adapter_ready()`**：

- 返回 **`ALG_READY`**：才进入后续按 `support_spec` 的 **`pe50_hal_authenticate_ta()`**。
- 返回 **`ALG_TA_CHECKING`**：`pe50_is_ta_rdy()` **直接返回**（整轮 PE5 保持「等 PD」），典型对应 `pd_adapter` 的 `PD_TYPE_TIMEOUT` 仍为 **`TC_PD_CONNECT_NONE`**（协商尚未落定）。
- 返回 **`ALG_TA_NOT_SUPPORT`**：**跳过本 adapter**（`continue` 到 `support_ta` 下一项或结束），即 **PE5 本轮不会走 `pd_adapter`**。

#### 2) `tc_pe5_hal.c`：PE5 侧「放开 PD」的判据 **仅限 APDO/PPS**

`pe50_hal_is_pd_adapter_ready()` 从 `pd_adapter` 读取 **`PD_TYPE_TIMEOUT`**，**仅当**：

- `type == TC_PD_CONNECT_PE_READY_SNK_APDO`

才返回 **`ALG_READY`**。  
其余非 `NONE` 状态一律 **`ALG_TA_NOT_SUPPORT`**（与独立 `pd` 算法的 ready 条件 **不一致**）。

因此：**在 PE5 内层，`pd_adapter` 被选中并成功认证时，语义上对应「PD 已协商到 SNK APDO（PPS 能力可用）」**；`pe50_check_algo_name()` 里也把 **`pd_adapter` 映射为 `PE50_PPS`**（命名表示 **PE5 走 PPS/APDO 规格**，不是泛指所有 PD）。

#### 3) 无 PPS（仅固定 PDO 等）时谁跑「纯 PD」

若对端 **只有固定 PDO / PD3.0 无 APDO**，`pe50_hal_is_pd_adapter_ready()` 会 **NOT_SUPPORT**，PE5 **不会**占用 `pd_adapter` 这条路径。

此时由 **`support_alg` 中独立的 `pd` 模块**（`tc_pd.c`）承担 **`pd_hal_is_pd_adapter_ready()`**：  
在 **`TC_PD_CONNECT_PE_READY_SNK`、`TC_PD_CONNECT_PE_READY_SNK_PD30`、`TC_PD_CONNECT_PE_READY_SNK_APDO`** 等状态下均可 **`ALG_READY`**（与 PE5 的「仅 APDO」区分）。

**外层调度要点**：`tc_algo_protocol_process()` 按 **`support_alg` 顺序** 轮询；若配置为 **`pe5` 在前、`pd` 在后**，常见情况是 **PE5 先占用决策**（RFC 等），**仅当 PE5 未吃掉 PD/PPS 或轮询到 `pd` 算法模块** 时，独立 `pd` 才会成为 `running_algo`。排查时要同时看 **内层 `support_ta`** 与 **外层 `support_alg` 顺序**。

#### 4) 与 `tc_pd_adapter.c` 的关系

`pd_adapter` 的 `PD_TYPE_TIMEOUT` 由 `tc_pd_adapter.c` 根据 **`pd_type` 超时与协商进度** 更新（见 `pd_get_property(PD_TYPE_TIMEOUT)`）；PE5 与独立 `pd` 都依赖 **同一 `pd_adapter` 设备**，但 **读 ready 的判定函数不同**（`pe50_hal_*` vs `pd_hal_*`）。

#### 5) 排查清单（PD / PPS 分流）

- [ ] `pe50_hal_is_pd_adapter_ready` 与 `pd_hal_is_pd_adapter_ready` 的 **返回值** 是否被混用（同一时刻可能对 PE5 为 NOT_SUPPORT、对独立 `pd` 为 READY）。  
- [ ] `PD_TYPE_TIMEOUT` / `TC_PD_CONNECT_*` 实际值：**是否已到 `PE_READY_SNK_APDO`**。  
- [ ] `support_ta` 顺序：RFC 失败后是否轮到 `pd_adapter`；是否被 `ALG_TA_CHECKING` 长期卡住。  
- [ ] `support_alg` 是否包含独立 `pd` 且顺序靠后；若仅固定 PDO，是否 **`running_algo` 最终为 `pd` 而非 PE5**。  
- [ ] `pe50_check_algo_name`：`pd_adapter` → **`PE50_PPS`**（命名与「纯 PD」区分）。

### HVDCP30 / QC3

- 入口：`tc_hvdcp30_mode_check()`
- 前置条件：
  - `tc_get_alias_type() == TC_DCP`
  - 不是 `TC_NON_STD`
  - `tc_get_pd_type()` 不能已经是 `PE_READY_*`
- 探测动作：
  - `TRAN_PROP_USB_CTRL_HVDCP30 = HVDCP30_HANDSHAKE`
- 认证入口：
  - `tc_hvdcp30_authenticate_ta()`

## 选型规则

### 外层：`support_alg` -> `data->running_algo`

- `support_alg` 在 `tc_charger_parse_dt()` 读入，在 `charger_init_algo()` 中 `get_tchg_alg_by_name()` 绑定到 `data->alg[]`
- `tc_algo_protocol_process()` 决定 **`running_algo` 指向哪一套 `tchg_alg`**
- **非标场景**：`alias_type == TC_NON_STD` 时，代码会限制仅尝试 `PE5_ID` 与 `PDC_ID`（见 `tc_algo_protocol_process()` 对 `alg->alg_id` 的判断），这会直接表现为 **`hvdcp20` / `tc30` / `pe20` 被跳过**

### 内层：仅 `pe5`：`support_ta` -> `tfcp_adapter` / `pd_adapter` / `hvdcp30_adapter`

- `support_ta` 顺序来自 pe5 节点 dts，并由 `pe50_hal_init_hardware()` 读入 `hal->adapters[]`
- `pe50_is_ta_rdy()` 会按 `support_ta` 顺序逐个尝试 adapter
- 对 `pd_adapter` 会额外检查 **`pe50_hal_is_pd_adapter_ready()`**（**仅 `TC_PD_CONNECT_PE_READY_SNK_APDO` 为 READY**；与独立 `pd` 算法的 `pd_hal_is_pd_adapter_ready()` 不同）
- 首个认证成功的 adapter 会成为 `running_ta`
- 最终通过 `adapter_name` 映射为：
  - `tfcp_adapter` -> `PE50_RFC`
  - `pd_adapter` -> `PE50_PPS`（**仅表示 PE5 在 APDO/PPS 能力下选中该 adapter**；非 PPS 的纯 PD 见 `support_alg` 的 `pd` / `tc_pd.c`）
  - `hvdcp30_adapter` -> `PE50_QC3`

## 分析步骤

```text
DCP 后快充探测排查清单
- [ ] 先做 **log-first 失败分层**（不依赖 DTS）：
  - A层（协议下发前/下发时失败）：如 `set target_volt ... failed, ret < 0`
  - B层（协议下发成功但验收失败）：如 `vchr_after` 与目标 `delta` 超限
  - C层（资格门控失败）：如 `ALG_TA_NOT_SUPPORT` / `ALG_TA_CHECKING`
  - 只有先判定 A/B/C 层，才能决定是否需要 DTS
- [ ] 先确认 BC1.2 结果是否已经稳定为 DCP（以及是否 NON_STD，影响外层算法白名单）
- [ ] 先看外层：tc_charger dtsi 的 support_alg 顺序与 charger_init_algo() 是否全部 get 成功
- [ ] 跟踪 tc_algo_protocol_process()：每个 tchg_alg 的 is_algo_ready 状态与最终 running_algo
- [ ] 若 running_algo 不是 pe5：按对应模块深挖（tc_pd / tc_hvdcp20 / tc_tc30 / tc_pe20）
- [ ] 若 running_algo == hvdcp20：按上一节「hvdcp20 握手机制」核对 `TRAN_PROP_USB_CTRL_HVDCP20`、`usb_control`、`hvdcp20_control_type`、VBUS delta 与 OVP 行为
- [ ] 若 running_algo == tc30：按上一节「tc30 握手机制」核对 `TRAN_PROP_USB_CTRL_TC30`、`tc30_control_type`、`TC30_7V5` 探测 delta、OVP、`charger_dev_set_tc30_oneshot` 与 `TRAN_PROP_IS_TC30_TA`
- [ ] 若 running_algo == pe20：按上一节「pe20 握手机制」核对 `support_pe20_by_switch`、`pe20_set_current_pattern` vs `charger_dev_send_ta20_current_pattern`、`chr_volt` dtsi、`PE20_9V` 与 VBUS delta、OVP
- [ ] 若 `running_algo == pe20` 且日志出现 `pe20 set target_volt ... failed, ret=-1`：
  - 先判分支：`support_pe20_by_switch=true/false`（两条路径优先级相同，禁止只盯 switch 分支）
  - **switch=true（charger 硬件发码）**：立即补查 `mt6375-chg ... detach` / `failed to wait pe`；对齐 `mt6375_run_pe()`：`pwr_rdy == false` 会 `detach` 并返回 `-EPERM(-1)`
  - **switch=false（软件电流脉冲）**：立即补查 `pe20_set_current_pattern` 的时间窗/重试日志与失败点（`retry`、间隔校验失败、`pe20 chg unknown, return` 等）
  - 两分支都要回到 `pe20_set_ta_vchr` 的 `vchr_before/vchr_after/delta` 验收，确认是“下发失败”还是“下发成功但升压无效”
  - 该场景优先归因到 **当前分支的 runtime 执行通路**，不是先归因 DTS 参数
- [ ] 仅当 running_algo == pe5：先按上一节「pe5 外层 tchg_alg 就绪门控」核对 `pe50_is_algo_ready` / bypass / vbat / `ta_ready`，再检查内层 `support_ta` 顺序与 `pe50_is_ta_rdy()`
- [ ] 若关心 PD/PPS：核对「PE5 内 `pd_adapter`」仅 APDO 就绪 vs「独立 `pd`（`tc_pd.c`）」对固定 PDO/PD3 的 READY 条件，并对照 `support_alg` 顺序是否落到 `pd` 模块
- [ ] 检查是否因为 NON_STD / PD ready 导致 PE5 内 RFC 或 HVDCP30 被直接跳过
- [ ] 分别检查 RFC / PPS / HVDCP30 的 authenticate_ta() 返回值（内层）
- [ ] 确认 running_ta、running_spec、adapter_name、PE50_*（内层）
- [ ] 区分“外层算法未选中”与“内层 adapter 探测失败/被插队”
```

## 输出模板

```markdown
## 分域结论
- 主域：<transsion-dcp-fastcharge-probe / transsion-charger-orchestrator>
- 次域：<skill list 或 none>

## 触发点
- 输入触发：<DCP / fast charge / RFC / PPS / QC3>
- 首个命中函数：<function>

## 探测路径
- DCP/端口前提：<是否已成立 / 是否 NON_STD>
- support_alg 顺序：<pe5 / pd / hvdcp20 / tc30 / pe20>
- 外层轮询：<tc_algo_protocol_process 对每个 tchg_alg 的 is_algo_ready 状态>
- 当前 running_algo：<pe5 / pd / hvdcp20 / tc30 / pe20 / none>
- （仅 pe5）adapter 顺序：<support_ta list>
- （仅 pe5）当前尝试：<tfcp / pd / hvdcp30>
- （仅 pe5）认证结果：<ALG_READY / ALG_TA_CHECKING / ALG_TA_NOT_SUPPORT>

## 选型结果
- data->running_algo：<tchg_alg 名称>
- （仅 pe5）running_ta：<adapter index/name>
- （仅 pe5）running_spec：<spec>
- （仅 pe5）adapter_name：<name>
- （仅 pe5）映射：<PE50_RFC / PE50_PPS / PE50_QC3 / none>

## 失败分层
- A 资格门控：<通过/失败 + 证据>
- B 执行路径：<通过/失败 + 证据>
- C 验收路径：<通过/失败 + 证据>

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 转交条件

- 若 DCP 结果本身还不稳定，转交 `transsion-bc12-type-detect`
- 若协议/adapter 已确定，问题转为 **PE5 初始 VTA/ITA、软启动、热限流、FFC 分段与 TA 能力跟踪**，转交 `transsion-pe5-vi-tuning`（并需目标机种 `tc_pe50.dtsi`）
- 若问题在 `tc_charger` 主线程/vote/插入唤醒是否与算法联动，转交 `transsion-charger-orchestrator`
- 若问题核心是客制化入口（低功率增强/旁路/差旅）是否触发，先转交 `transsion-charger-orchestrator`；本 skill 作为次域验证协议竞选后果
- 若 PD 原生 `PE_READY/APDO` 本身异常，转交 `mediatek-pd-typec-protocol-6-12`
- 若已确认不是 PE5 内 `support_ta` 问题，而是 **`hvdcp20` / `tc30` / `pe20` / 独立 `pd` 模块** 的 `tchg_alg` 状态机或 `tran_usb_ctrl` 执行路径，仍保留在本 skill，但应在输出中明确“外层算法模块”而非仅写 PE50

## 约束

- 回答时必须同时给出“探测动作”和“最终选型动作”，不能只说某协议支持或不支持
- 不能把 `adapter 检测成功` 和 `PE50 最终选中` 混为一谈
- 不能把 `support_ta`（PE5 内层）与 `support_alg`（tc_charger 外层）混为一谈；涉及 dtsi 时必须说明指的是哪一个列表
- 必须明确 `support_alg` 顺序是否影响 **`data->running_algo`**
- 在分析 PE5 时，必须明确 `support_ta` 顺序是否影响 **PE5 内 `tfcp/pd/hvdcp30` 的优先级**
- **禁止**在已有明确 runtime 错误链（函数名+返回码+前后文）时，先向用户索取 DTS 再下结论
- DTS 仅在以下场景允许作为主证据：
  - probe/parse 明确报错（如 `failed parse ...` / 数组缺失）
  - 需要解释目标电压/电流/MIVR阈值为何被设置为某值
  - 日志没有进入算法关键路径（无 `start_algo` / 无 `set_ta_vchr`）导致无法定位
- 若日志已出现 `ret < 0` 的直接失败点，必须先把**失败函数链与返回码语义**解释完整，再决定是否需要补 DTS
- 分析 `pe20` 时，必须先声明当前分支：`support_pe20_by_switch=true`（charger `send_ta20_current_pattern`）或 `false`（`pe20_set_current_pattern` 软件脉冲），并给出该分支下的**首要日志锚点**；不得遗漏另一分支的关键日志策略
- 看到 RFC 相关失败日志（如 `rfc_handshake_by_cp_ic failed`）时，必须先核对“该充电器是否声明支持 RFC”；若未声明，必须在结论中标注“能力未知/不支持 RFC 的正常失败”，禁止直接推导为 CP 通路不稳定
- 该规则对所有协议统一适用（RFC / PPS / PD fixed PDO / QC2.0 / QC3 / TC30 / PE2.0 等）：**握手失败日志只证明“本次协商未成功”，不能单独推出“协议栈或链路异常”**
- 若对端协议能力未知，结论必须显式标注“能力未知，当前仅能判定协商失败”；仅在“对端明确支持该协议且仍失败”时，才可升级为异常结论
