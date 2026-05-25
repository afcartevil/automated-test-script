---
name: qualcomm-adsp-usb-pd-analysis
description: "Qualcomm-ADSP-USB/PD: 基于battman/usbtypec架构分析USB Type-C/PD，覆盖TCPC IRQ→LPM(TCPM/PE/PRL)→DPM→PPM→pmic_glink | TCPC/PD/PPS/role_swap/hard_reset/UCSI/ADSP/TypeC插拔 | 当用户报告Qualcomm平台PD协商失败、插拔异常、role swap失败时使用"
---

# Qualcomm ADSP USB-PD 分析

## 适用范围

聚焦 Qualcomm `ADSP` 侧 `battman/usbtypec` 架构，不展开 `kernel` 侧实现。

**与 Charging skill 的分界**：本 skill 覆盖 `TCPC`→`LPM`→`DPM/PPM`→`pmic_glink` 的 PD 与端口语义；`APSD`、`QC/UFCS/RFC`、`ICM` 充电状态机由 `qualcomm-adsp-charging-analysis` 负责。二者在 **`dpm_handle_cable_event()`** 与 **`charger_detection_notify()`** 处交汇。若现象同时涉及「PD/通知」与「充电类型/ICM」，先用 **`qualcomm-adsp-power-usb-triage`** 归位。

主路径：
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/usbtypec/tcpc`
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/usbtypec/lpm`
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/usbtypec/dpm`
- `nonpart/LPAIDSP.HT.1.0.1/adsp_proc/core/battman/framework/pmicglink`

包含：
- PMIC PDPhy/Type-C IRQ 到 TCPC 状态机
- `LPM` 内 `TCPM/PE/PRL_RX/PRL_TX/PRL_HR`
- `DPM` 请求与状态聚合
- `PPM` 的 `UCSI mailbox/CCI`
- `pmic_glink` 到 `APSS` 的通知出口

不包含：
- `kernel` 侧 `typec/dwc3/usb_role_switch/gadget`（深挖时转 `qualcomm-msm-kernel-usb-ucsi-analysis` / `qualcomm-msm-kernel-charging-supply-analysis` / `qualcomm-msm-kernel-dwc3-role-gadget-analysis`，交界见 `qualcomm-kernel-adsp-bridge`）
- Android framework / UsbService 细节
- 充电策略与 battery gauge 细节

## 日志与事件锚点（便于 grep）

优先在 ADSP 日志中检索：

- `USBPD_LPM_EVENT_ALERT`、`USBPD_LPM_EVENT_PM_REQUEST`、`USBPD_LPM2DPM_NOTIFY`
- `tcpm_get_events_from_alert`、`ALERT_CC_STATUS`、`ALERT_POWER_STATUS`、`HARDRESET`
- `dpm_set_request_to_lpm`、`PmReq`、`PE_PM_REQUEST_RTN`
- `lpm_async_event_update`、`ConnectorStatusChange`、`ppm_handle_async_event_update`
- `pmic_glink`、`UCSI`、`CCI`

## 固定入口

必须先从这几个入口开始：

1. `tcpc/platforms/src/PmicTccPlatform_Schg_PDPhy_R1_IRQ.c`
   - `TypecOrRid_det_Cb()`
   - `CCStChgIrq_Cb()`
   - `VbusStChgIrq_Cb()`
   - `MsgReceivedIrq_Cb()` / `MsgSentIrq_Cb()` / `SignalReceivedIrq_Cb()`
2. `tcpc/statemachine/src/PmicTccStateMachine.c`
   - `PmicTccStateMachine_SignalThread()`
   - `PmicTccStateMachine_Main_Thread()`
3. `lpm/src/lpm.c`
   - `lpm_mainloop()`
   - `lpm_update_new_events_to_queue()`
   - `lpm_process_event()`
   - `lpm_notify_dpm()`
4. `dpm/src/dpm.c`
   - `dpm_set_request_to_lpm()`
   - `dpm_queue_lpm_async_event()`
   - `dpm_queue_lpm_rtn4request_event()`
   - `dpm_handle_cable_event()`
5. `dpm/src/ppm.c`
   - `ppm_handle_async_event_update()`
   - `ppm_state_process_command_main()`
   - `ppm_notify_opm()`

`pmic_glink` 关键出口：
- `framework/pmicglink/inc/pmic_glink.h`
- `framework/pmicglink/inc/pmic_glink_msg.h`

## 模块边界

- `TCPC`：接 PMIC PDPhy/Type-C IRQ，维护 `TCPCI` 视图，向 `LPM` 提供 `ALERT`
- `LPM`：协议执行核心，包含 `TCPM/PE/PRL_RX/PRL_TX/PRL_HR`
- `DPM`：设备策略、端口状态聚合、LPM 请求入口
- `PPM`：`UCSI/OPM` 语义层，维护 `mailbox/CCI`
- `pmic_glink`：`ADSP -> APSS` 的通知通道

## 三条主线

### 1. ALERT 线

适用现象：
- 插拔异常
- PD 消息收发异常
- hard reset / FRS
- TCPC alert 有日志但上层无动作

固定路径：
- `USBPD_LPM_EVENT_ALERT`
- `tcpm_get_events_from_alert()`
- 子事件展开：
  - `ALERT_CC_STATUS`
  - `ALERT_POWER_STATUS`
  - `ALERT_RECEIVE_SOP_MESSAGE_STATUS`
  - `ALERT_TRANSMIT_SOP_MESSAGE_SUCCESSFUL/FAILED/DISCARDED`
  - `ALERT_RECEIVE_HARDRESET_STATUS`
  - `ALERT_TRANSMIT_SIGNAL_COMPLETE`
  - `ALERT_RECEIVE_FAST_ROLE_SWAP`

关键判断：
- 先看 `TCPM` 是否打开 `bAlertForwarding`
- `CC_STATUS/POWER_STATUS` 先由 `TCPM` 处理
- `RECEIVE_SOP` 落 `PRL_RX`
- `TRANSMIT_*` 落 `PRL_TX`
- `HARDRESET` 落 `PRL_HR`
- `PE` 不是直接解 `TCPCI ALERT` 的第一站

### 2. PM_REQUEST 线

适用现象：
- role swap
- soft reset / hard reset 请求
- get src/snk caps
- PPS 状态获取
- LPD / TrySNK / FRS 使能

固定路径：
- `dpm_set_request_to_lpm()`
- `RequestBuffer`
- `USBPD_LPM_EVENT_PM_REQUEST`
- `lpm_add_dpm_request_event()`
- 分流到：
  - `PE` 协议执行类
  - `TCPM` 本地控制类
  - 本地上下文更新类
- `PE_PM_REQUEST_RTN`
- `dpm_queue_lpm_rtn4request_event()`
- `ppm_state_process_command_main()`

关键判断：
- 必看 `PmReq.Type`
- 必看 `PmReq.State`
- `WAIT` 不等于失败，通常表示 defer
- `GET_PPS_STATUS` 结果优先回 `DPM/PwrMgr`，不一定走 `PPM`

### 3. ASYNC_EVENT 线

适用现象：
- ADSP 内部状态变了，但 AP 没看到
- ConnectorStatus / UCSI 状态不同步
- PDO/RDO/partner type 更新异常
- PAN/AltMode 与普通状态通知相互阻塞

固定路径：
- `lpm_async_event_update()`
- `lpm_async_event_update_from_tcpm()`
- `lpm_async_event_update_from_pe()`
- `USBPD_LPM2DPM_NOTIFY_PORT_STATUS_CHANGE`
- `USBPD_DPM_EVENT_LPM_ASYNC_EVENT`
- `dpm_queue_lpm_async_event()`
- `dpm_handle_cable_event()`
- `ppm_handle_async_event_update()`
- `ppm_set_cci_for_connector_change()`
- `ppm_notify_opm()`

关键判断：
- `TCPM` 提供基础连接语义：`ConnectStatus/PowerDirection/PowerOpMode/PartnerType`
- `PE` 提供 PD 语义：`RDO/PDO/AltMode/BatteryChargingStatus/ExternalSupplyChange`
- 若 `PAN` pending，普通 async 可能延后
- `PPM` 还会受 `NotifyEn`、holdoff、pending async 缓存影响

## 分析步骤

```text
Qualcomm ADSP USB-PD 排查清单
- [ ] 先判定问题主线：ALERT / PM_REQUEST / ASYNC_EVENT
- [ ] 从 TCPC IRQ 或 DPM request 固定入口起步，不要跳过入口层
- [ ] 在 LPM 中确认事件落点：TCPM / PRL_RX / PRL_TX / PRL_HR / PE
- [ ] 若是 PM_REQUEST，检查 PmReq.Type / PmReq.State / defer queue
- [ ] 若是 ASYNC_EVENT，检查 ConnectorStatusChange 由 TCPM 还是 PE 产生
- [ ] 检查 DPM 是否已更新 PwrMgr.PortStatus
- [ ] 检查 PPM 是否因 NotifyEn / holdoff / pending PAN 阻塞了对外通知
- [ ] 最后再确认是否进入 pmic_glink 出口
```

## 快速分流规则

1. 命中 `CC/VBUS/alert/receive_sop/hardreset/frs`
   - 优先走 `ALERT` 线
2. 命中 `set_uor/set_pdr/get_pdos/pps/request/swap/softreset`
   - 优先走 `PM_REQUEST` 线
3. 命中 `ConnectorStatusChange/AsyncEvent/CCI/ConnectorChangeIndicator/NotifyEn`
   - 优先走 `ASYNC_EVENT` 线
4. 若现象是“请求发出后状态没更新”
   - 先看 `PM_REQUEST`，再看 `ASYNC_EVENT`
5. 若现象是“线缆/协议事件发生了但栈没跑”
   - 先看 `ALERT`，优先检查 `bAlertForwarding`

## 输出模板

```markdown
## 主线判定
- 主线：ALERT / PM_REQUEST / ASYNC_EVENT
- 入口函数：<function>

## 模块落点
- TCPC/TCPM：<state or event>
- PRL/PE：<state or event>
- DPM/PPM：<state or event>

## 关键状态
- bAlertForwarding：<true/false>
- PmReq.Type / PmReq.State：<value or none>
- ConnectorStatusChange：<bitmask>
- PDContractState：<state>

## 对外通知
- DPM 已更新：<yes/no>
- PPM 已处理：<yes/no>
- glink 已发送：<yes/no>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<file/function/log>
```

## 约束

- 不能跳过 `TCPC IRQ` / `DPM request` 固定入口直接猜结论
- 必须分清 `ALERT`、`PM_REQUEST`、`ASYNC_EVENT` 三条主线
- 必须区分 `TCPM` 基础连接语义 与 `PE` 的 PD 协议语义
- 若问题已经落到 **msm-kernel**（`ucsi_glink`、`qti_battery_charger`、`dwc3` 等），停止使用本 skill 深挖，转入下方 kernel skill

## 转交

- 现象横跨 PD 与充电识别、需先定主线：`qualcomm-adsp-power-usb-triage`
- 若问题主轴变成 `BC1.2/APSD`、`QC/HVDCP`、`UFCS`、`RFC`、`TFCP`、`ICM`，转交 `qualcomm-adsp-charging-analysis`
- **固件已闭环但 AP/kernel 不同步**：先 `qualcomm-kernel-adsp-bridge`，再 **`qualcomm-msm-kernel-usb-ucsi-analysis`**（UCSI/CCI/connector）或 **`qualcomm-msm-kernel-charging-supply-analysis`**（usb/batt psy、充电类型），若命中 role/gadget 枚举异常转 **`qualcomm-msm-kernel-dwc3-role-gadget-analysis`**

## 附加资料

- 详细链路时序、典型现象映射、关键状态变量见 [reference.md](reference.md)
